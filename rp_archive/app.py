import io, os, json, functools, secrets, time, hmac, logging, traceback
from collections import defaultdict
from datetime import datetime, date as _date
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort, send_file, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "rp_archive_secret_key_change_me")


# ── 错误日志 ──────────────────────────────────────────────────────────────────
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_err_handler = logging.FileHandler(os.path.join(_log_dir, "error.log"), encoding="utf-8")
_err_handler.setLevel(logging.ERROR)
_err_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s]\n%(message)s\n" + "-"*60
))
_logger = logging.getLogger("rp_archive")
_logger.setLevel(logging.ERROR)
_logger.addHandler(_err_handler)

@app.errorhandler(404)
def handle_404(e):
    return render_template("error.html", code=404,
        title="你走丢了",
        lead="这里什么都没有。",
        body="我感应到你偏离了轨迹——这个地址不存在，或者已经从记忆里消失了。别担心，我来把你送回去。"), 404

@app.errorhandler(500)
def handle_500(e):
    _logger.error("500 Internal Server Error\nURL: %s %s\n%s",
                  request.method, request.url, traceback.format_exc())
    return render_template("error.html", code=500,
        title="系统发生了偏折",
        lead="核心出现了一道裂缝。",
        body="某个地方出了问题，我已经记录下这次异常并会着手修复。你现在能做的，是先回到安全的地方。"), 500

@app.template_filter("fromjson")
def _fromjson(s):
    try: return json.loads(s or "{}")
    except Exception: return {}

DB_PATH         = os.path.join(os.path.dirname(__file__), "rp_data.db")
SUPERADMIN_PASS = os.environ.get("SUPERADMIN_PASS",
                  os.environ.get("RP_ADMIN_PASSWORD", "pDynLBeLGEjd"))
PLAYERS_PER_PAGE = 50

# ── Config schema ────────────────────────────────────────────────────────────
CONFIG_SCHEMA = [
    {"section": "基础", "fields": [
        {"key": "love_show_name",         "label": "恋综名",      "type": "text",   "default": ""},
        {"key": "global_days",            "label": "当前游戏日",   "type": "text",   "default": "D1", "note": "如 D1 / D2 / D3"},
        {"key": "auto_day_reset_enabled", "label": "自动天数推进", "type": "bool",   "default": "false"},
        {"key": "item_pool_mode",         "label": "道具池模式",   "type": "select", "default": "自由池", "options": ["自由池", "抽取池"]},
    ]},
    {"section": "群组 ID", "fields": [
        {"key": "adminAnnounceGroupId",  "label": "公告群",     "type": "text",    "default": "", "note": "群号，留空不广播"},
        {"key": "song_group_id",         "label": "戏群（兼作拍卖展示群）", "type": "text",    "default": ""},
        {"key": "background_group_id",   "label": "后台群",     "type": "text",    "default": ""},
        {"key": "water_group_id",        "label": "水群",       "type": "text",    "default": ""},
        {"key": "fupan_routing_enabled", "label": "复盘群分流",  "type": "bool",    "default": "false", "note": "启用后复盘消息按天数路由到对应群"},
        {"key": "fupan_routing_groups",  "label": "分流群配置",  "type": "routing", "default": "", "note": "格式：D1:群号 D2:群号"},
        {"key": "announceFrequency",     "label": "公告触发频率","type": "number",  "default": "5", "note": "每 N 条互动触发一次公告广播"},
        {"key": "drop_hide_receiver",    "label": "掉落/曝光隐藏收件人", "type": "bool", "default": "false", "note": "开启后礼物掉落/短信公开/心动信曝光的播报中收件人显示为「某人」"},
    ]},
    {"section": "功能开关", "json_parent": "global_feature_toggle", "fields": [
        {"key": "enable_general_gift",        "label": "普通礼物",          "type": "bool", "default": "true"},
        {"key": "enable_general_appointment", "label": "普通邀约",          "type": "bool", "default": "true"},
        {"key": "enable_chaos_letter",        "label": "短信",              "type": "bool", "default": "true"},
        {"key": "enable_wish_system",         "label": "心愿系统",          "type": "bool", "default": "true"},
        {"key": "enable_lovemail",            "label": "心动信",            "type": "bool", "default": "false"},
        {"key": "enable_wechat",              "label": "微信",              "type": "bool", "default": "false"},
        {"key": "enable_direct_letter",       "label": "发送信件（写信综）", "type": "bool", "default": "false"},
    ]},
    {"section": "邀约", "fields": [
        {"key": "enable_join_existing_appointment", "label": "允许加入已有私约", "type": "bool",   "default": "false"},
        {"key": "require_fupan_before_end",         "label": "强制转发复盘",     "type": "bool",   "default": "false"},
        {"key": "group_expire_hours",               "label": "小群过期（小时）", "type": "number", "default": "48"},
    ]},
    {"section": "邀约时长（分钟）", "json_parent": "appointment_duration_config", "fields": [
        {"key": "phone",   "label": "电话门槛", "type": "number", "default": "29"},
        {"key": "private", "label": "私密门槛", "type": "number", "default": "59"},
    ]},
    {"section": "寄信", "fields": [
        {"key": "mailCooldown",             "label": "寄信冷却（分钟）", "type": "number", "default": "60"},
        {"key": "allow_custom_letter_sign", "label": "寄信自定义名字",  "type": "bool",   "default": "false"},
        {"key": "letter_public_send",       "label": "寄信公开发送",    "type": "bool",   "default": "false"},
    ]},
    {"section": "礼物", "fields": [
        {"key": "giftCooldown",             "label": "送礼冷却（分钟）",  "type": "number", "default": "30"},
        {"key": "gift_public_send",         "label": "礼物公开发送",      "type": "bool",   "default": "false"},
        {"key": "giftPublicChance",         "label": "礼物公开概率（%）", "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "giftDailyLimit",           "label": "每日礼物上限",      "type": "number", "default": "100"},
        {"key": "shop_refresh_hours",       "label": "礼品店刷新（小时）","type": "number", "default": "24"},
        {"key": "allow_custom_gift_sign",      "label": "送礼自定义名字",      "type": "bool",   "default": "false"},
    ]},
    {"section": "心动信", "fields": [
        {"key": "lovemail_default_limit",  "label": "每日上限",     "type": "number", "default": "3"},
        {"key": "lovemail_delivery_time",  "label": "送达时间",     "type": "text",   "default": "22:00"},
        {"key": "lovemail_expose",         "label": "曝光",         "type": "bool",   "default": "false"},
        {"key": "lovemail_expose_chance",  "label": "曝光概率（%）","type": "number", "default": "10", "min": 0, "max": 100},
    ]},
    {"section": "发送信件", "fields": [
        {"key": "direct_letter_daily_limit", "label": "每日上限",       "type": "number", "default": "5"},
        {"key": "direct_letter_cooldown",    "label": "发信冷却（分钟）","type": "number", "default": "0"},
        {"key": "direct_letter_min_chars",   "label": "最低字数",       "type": "number", "default": "0"},
        {"key": "direct_letter_reward",      "label": "写信币赏金",     "type": "number", "default": "0"},
    ]},
    {"section": "心愿系统", "fields": [
        {"key": "wish_public_send",      "label": "心愿公开提醒",          "type": "bool",   "default": "true"},
        {"key": "wish_bounty_enabled",   "label": "悬赏功能",              "type": "bool",   "default": "true"},
        {"key": "wish_max_concurrent",   "label": "最大同时心愿数",         "type": "number", "default": "3"},
        {"key": "wish_daily_post_limit", "label": "每日发布上限（0=不限）", "type": "number", "default": "0"},
        {"key": "wish_daily_pick_limit", "label": "每日接取上限（0=不限）", "type": "number", "default": "0"},
    ]},
    {"section": "关系系统", "fields": [
        {"key": "relationship_system_enabled", "label": "关系系统",     "type": "bool",   "default": "false"},
        {"key": "max_relationships_per_user",  "label": "每人最大关系数","type": "number", "default": "5"},
    ]},
    {"section": "目击系统", "json_parent": "sighting_system_config", "fields": [
        {"key": "enabled",                "label": "启用目击",       "type": "bool",   "default": "false"},
        {"key": "send_to_all",            "label": "双向通知",       "type": "bool",   "default": "true"},
        {"key": "max_reports_per_day",    "label": "每日最大目击数", "type": "number", "default": "5"},
        {"key": "include_ended_meetings", "label": "包含已结束场次", "type": "bool",   "default": "false"},
        {"key": "time_overlap_threshold", "label": "时间重叠阈值",   "type": "number", "default": "0.3"},
    ]},
    {"section": "场所系统", "json_parent": "place_system_config", "fields": [
        {"key": "enabled",                "label": "启用场所系统", "type": "bool", "default": "false"},
        {"key": "require_key_by_default", "label": "默认需要钥匙", "type": "bool", "default": "false"},
    ]},
    {"section": "私人房间", "fields": [
        {"key": "allow_private_rooms",    "label": "允许私人房间", "type": "bool",   "default": "true"},
    ]},
    {"section": "短信效果配置（% · 0=关闭）", "json_parent": "chaos_letter_config", "fields": [
        {"key": "misdelivery",       "label": "误送",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "blackoutText",      "label": "黑化文字",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "loseContent",       "label": "内容丢失",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "antonymReplace",    "label": "词语替换",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "reverseOrder",      "label": "逆序",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "mistakenSignature", "label": "署名错乱",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "poeticSignature",   "label": "诗意署名",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "dailyLimit",        "label": "每日上限",          "type": "number", "default": "5"},
        {"key": "publicChance",      "label": "播报概率（%）",     "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "publicShowEffect",  "label": "公开时显示扰乱效果","type": "bool",   "default": "false"},
        {"key": "giftLost",          "label": "礼物丢失（%）",     "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "giftMisdelivery",   "label": "礼物误送（%）",     "type": "number", "default": "0",  "min": 0, "max": 100},
    ]},
    {"section": "道具", "fields": [
        {"key": "item_tracker_success_rate",   "label": "追踪器成功率（%）",  "type": "number", "default": "70", "min": 0, "max": 100},
        {"key": "item_tracker_show_partner",   "label": "追踪器显示伙伴",    "type": "bool",   "default": "true"},
        {"key": "item_tracker_time_restrict",  "label": "追踪器时间限制",    "type": "bool",   "default": "true"},
        {"key": "apply_item_notification",     "label": "施加道具提醒",      "type": "bool",   "default": "true"},
        {"key": "apply_item_expose_rate",      "label": "施加暴露概率（%）", "type": "number", "default": "0", "min": 0, "max": 100},
        {"key": "apply_item_hours",            "label": "施加可用时段",      "type": "text",   "default": ""},
        {"key": "shop_gift_catalog_on_receive","label": "收到即入图鉴",      "type": "bool",   "default": "false"},
    ]},
    {"section": "拍卖", "fields": [
        {"key": "auction_allow_anon",      "label": "允许匿名出价",   "type": "bool", "default": "true"},
        {"key": "auction_broadcast",       "label": "出价播报",       "type": "bool", "default": "true"},
        {"key": "auction_show_top_bidder", "label": "展示最高出价者", "type": "bool", "default": "true"},
        {"key": "auction_currency",        "label": "拍卖货币",       "type": "text", "default": "金币"},
    ]},
    {"section": "监听参数", "json_parent": "monitor_settings", "fields": [
        {"key": "enabled",                "label": "启用监听系统",       "type": "bool",   "default": "true"},
        {"key": "auto_monitor_all_groups","label": "自动监控所有群组",   "type": "bool",   "default": "true"},
        {"key": "min_words_phone",        "label": "电话最低字数",       "type": "number", "default": "20"},
        {"key": "min_words_private",      "label": "私密最低字数",       "type": "number", "default": "150"},
        {"key": "min_words_wish",         "label": "心愿最低字数",       "type": "number", "default": "150"},
        {"key": "min_words_official",     "label": "官约最低字数",       "type": "number", "default": "150"},
        {"key": "timeout_phone",          "label": "电话超时（小时）",   "type": "number", "default": "1"},
        {"key": "timeout_private",        "label": "私密超时（小时）",   "type": "number", "default": "3"},
        {"key": "timeout_wish",           "label": "心愿超时（小时）",   "type": "number", "default": "3"},
        {"key": "timeout_official",       "label": "官约超时（小时）",   "type": "number", "default": "3"},
    ]},
    {"section": "公开链接", "fields": [
        {"key": "public_show_sms",      "label": "公开短信",   "type": "bool", "default": "true"},
        {"key": "public_show_gift",     "label": "公开礼物",   "type": "bool", "default": "true"},
        {"key": "public_show_lovemail", "label": "公开心动信", "type": "bool", "default": "true"},
    ]},
]

def _cfg_db_key(section, field_key):
    jp = section.get("json_parent")
    return f"{jp}__{field_key}" if jp else field_key

def get_flat_config(db, show_id):
    rows = db.execute("SELECT key, value FROM site_config WHERE show_id=?", (show_id,)).fetchall()
    return {r["key"]: r["value"] for r in rows}

def assemble_bot_config(flat):
    result = {}
    for sec in CONFIG_SCHEMA:
        jp = sec.get("json_parent")
        if jp:
            obj = {}
            for f in sec["fields"]:
                raw = flat.get(_cfg_db_key(sec, f["key"]), str(f["default"]))
                if f["type"] == "bool":
                    obj[f["key"]] = raw in ("true", "1", "True")
                elif f["type"] == "number":
                    try:
                        obj[f["key"]] = float(raw) if "." in str(raw) else int(raw)
                    except (ValueError, TypeError):
                        obj[f["key"]] = f["default"]
                else:
                    obj[f["key"]] = raw
            # timeout fields in monitor_settings are stored as hours in UI, bot expects ms
            if jp == "monitor_settings":
                for tkey in ("timeout_phone", "timeout_private", "timeout_wish", "timeout_official"):
                    if tkey in obj and isinstance(obj[tkey], (int, float)):
                        obj[tkey] = int(obj[tkey] * 3_600_000)
            result[jp] = json.dumps(obj, ensure_ascii=False)
        else:
            for f in sec["fields"]:
                result[f["key"]] = flat.get(f["key"], str(f["default"]))
    # 透传 blob 键（机器人以 JSON 字符串形式存储，原样透传）
    for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                     "end_game_bonus_templates", "end_game_draw_config"):
        val = flat.get(blob_key)
        if val:
            result[blob_key] = val
    return result


# ── DB ───────────────────────────────────────────────────────────────────────

def get_db():
    try:
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
        return g.db
    except RuntimeError:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def _col_names(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def _migrate(conn):
    # ── 1. tenants 表 ───────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            username            TEXT UNIQUE NOT NULL,
            view_password_hash  TEXT NOT NULL,
            admin_password_hash TEXT NOT NULL,
            api_token           TEXT UNIQUE NOT NULL,
            display_name        TEXT DEFAULT '',
            created_at          INTEGER DEFAULT 0
        )
    """)

    # ── 2. 旧数据表加 tenant_id ──────────────────────────────────────────────
    if "tenant_id" not in _col_names(conn, "sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id)")
    if "tenant_id" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")
    if "tenant_id" not in _col_names(conn, "extra_events"):
        conn.execute("ALTER TABLE extra_events ADD COLUMN tenant_id INTEGER NOT NULL DEFAULT 1")

    if "tenant_id" not in _col_names(conn, "site_config"):
        conn.execute("DROP TABLE IF EXISTS site_config_v2")
        conn.execute("""
            CREATE TABLE site_config_v2 (
                tenant_id INTEGER NOT NULL DEFAULT 1,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (tenant_id, key)
            )
        """)
        conn.execute("INSERT INTO site_config_v2(tenant_id,key,value) SELECT 1,key,value FROM site_config")
        conn.execute("DROP TABLE site_config")
        conn.execute("ALTER TABLE site_config_v2 RENAME TO site_config")

    if "tenant_id" not in _col_names(conn, "players"):
        conn.execute("""
            CREATE TABLE players_v2 (
                tenant_id      INTEGER NOT NULL DEFAULT 1,
                qq             TEXT NOT NULL,
                role_name      TEXT NOT NULL DEFAULT '',
                show_name      TEXT DEFAULT '',
                sessions_count INTEGER DEFAULT 0,
                total_replies  INTEGER DEFAULT 0,
                total_words    INTEGER DEFAULT 0,
                last_updated   INTEGER DEFAULT 0,
                PRIMARY KEY (tenant_id, qq)
            )
        """)
        conn.execute("""
            INSERT INTO players_v2
            SELECT 1,qq,role_name,show_name,sessions_count,total_replies,total_words,last_updated
            FROM players
        """)
        conn.execute("DROP TABLE players")
        conn.execute("ALTER TABLE players_v2 RENAME TO players")

    # ── 3. 创建默认租户（如不存在）──────────────────────────────────────────
    if conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0] == 0:
        view_pw  = os.environ.get("RP_VIEW_PASSWORD", "") or "viewer"
        admin_pw = os.environ.get("RP_ADMIN_PASSWORD", "pDynLBeLGEjd")
        token    = secrets.token_urlsafe(24)
        now      = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO tenants (username,view_password_hash,admin_password_hash,api_token,display_name,created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("default", generate_password_hash(view_pw), generate_password_hash(admin_pw), token, "默认团", now)
        )
        print(f"\n[rp_archive] ✅ 默认租户已创建  username=default  api_token={token}\n")

    # ── 4. shows 表 ─────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id           INTEGER NOT NULL,
            name                TEXT NOT NULL DEFAULT '第一季',
            description         TEXT DEFAULT '',
            is_current          INTEGER DEFAULT 0,
            public_view_enabled INTEGER DEFAULT 0,
            public_token        TEXT UNIQUE,
            created_at          INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shows_tenant ON shows(tenant_id)")

    # 为每个租户创建默认季
    for (tid,) in conn.execute("SELECT id FROM tenants").fetchall():
        if not conn.execute("SELECT id FROM shows WHERE tenant_id=?", (tid,)).fetchone():
            conn.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,0,?,?)",
                (tid, "第一季", secrets.token_urlsafe(24), int(time.time() * 1000))
            )

    # ── 5. 数据表加 show_id ──────────────────────────────────────────────────
    if "show_id" not in _col_names(conn, "sessions"):
        conn.execute("ALTER TABLE sessions ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE sessions SET show_id=(
                SELECT id FROM shows WHERE tenant_id=sessions.tenant_id ORDER BY id LIMIT 1)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_show ON sessions(show_id)")

    if "show_id" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE rp_entries SET show_id=(
                SELECT show_id FROM sessions WHERE sessions.id=rp_entries.session_id LIMIT 1)
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rp_show ON rp_entries(show_id)")

    if "show_id" not in _col_names(conn, "extra_events"):
        conn.execute("ALTER TABLE extra_events ADD COLUMN show_id INTEGER")
        conn.execute("""
            UPDATE extra_events SET show_id=(
                SELECT show_id FROM sessions WHERE sessions.id=extra_events.session_id LIMIT 1)
            WHERE session_id != ''
        """)
        conn.execute("""
            UPDATE extra_events SET show_id=(
                SELECT id FROM shows WHERE tenant_id=extra_events.tenant_id ORDER BY id LIMIT 1)
            WHERE show_id IS NULL
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_show ON extra_events(show_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_show_type ON extra_events(show_id,type)")

    # site_config: (tenant_id,key) → (show_id,key)
    if "show_id" not in _col_names(conn, "site_config"):
        conn.execute("""
            CREATE TABLE site_config_v3 (
                show_id   INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL,
                key       TEXT NOT NULL,
                value     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (show_id, key)
            )
        """)
        conn.execute("""
            INSERT INTO site_config_v3(show_id,tenant_id,key,value)
            SELECT COALESCE((SELECT id FROM shows WHERE tenant_id=sc.tenant_id ORDER BY id LIMIT 1),0),
                   sc.tenant_id,sc.key,sc.value
            FROM site_config sc
        """)
        conn.execute("DROP TABLE site_config")
        conn.execute("ALTER TABLE site_config_v3 RENAME TO site_config")

    # players: (tenant_id,qq) → (show_id,qq)
    if "show_id" not in _col_names(conn, "players"):
        conn.execute("""
            CREATE TABLE players_v3 (
                show_id        INTEGER NOT NULL,
                tenant_id      INTEGER NOT NULL,
                qq             TEXT NOT NULL,
                role_name      TEXT NOT NULL DEFAULT '',
                show_name      TEXT DEFAULT '',
                sessions_count INTEGER DEFAULT 0,
                total_replies  INTEGER DEFAULT 0,
                total_words    INTEGER DEFAULT 0,
                last_updated   INTEGER DEFAULT 0,
                PRIMARY KEY (show_id, qq)
            )
        """)
        conn.execute("""
            INSERT INTO players_v3
            SELECT COALESCE((SELECT id FROM shows WHERE tenant_id=p.tenant_id ORDER BY id LIMIT 1),0),
                   p.tenant_id,p.qq,p.role_name,p.show_name,
                   p.sessions_count,p.total_replies,p.total_words,p.last_updated
            FROM players p
        """)
        conn.execute("DROP TABLE players")
        conn.execute("ALTER TABLE players_v3 RENAME TO players")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_players_show ON players(show_id,role_name)")

    # ── 6. known_groups 表 ──────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id     INTEGER NOT NULL,
            tenant_id   INTEGER NOT NULL,
            group_id    TEXT NOT NULL,
            name        TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_known_groups_show ON known_groups(show_id)")
    if "set_name" not in _col_names(conn, "known_groups"):
        conn.execute("ALTER TABLE known_groups ADD COLUMN set_name TEXT NOT NULL DEFAULT ''")

    # ── 6b. known_group_sets 表（群号组名单独存储，支持空组）────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_group_sets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id    INTEGER NOT NULL,
            tenant_id  INTEGER NOT NULL DEFAULT 1,
            set_name   TEXT NOT NULL,
            created_at INTEGER NOT NULL DEFAULT 0,
            UNIQUE(show_id, set_name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_known_group_sets_show ON known_group_sets(show_id)")

    # ── 8. config_history 表 ───────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id     INTEGER NOT NULL,
            tenant_id   INTEGER NOT NULL,
            config_data TEXT NOT NULL,
            operator    TEXT DEFAULT '',
            created_at  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_config_history_show ON config_history(show_id, created_at)")

    # ── config_templates 表 ─────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL,
            name        TEXT NOT NULL,
            config_data TEXT NOT NULL,
            created_at  INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cfg_tpl_tenant ON config_templates(tenant_id)")

    # ── 7. reward_records 表 ────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reward_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id        INTEGER NOT NULL,
            tenant_id      INTEGER NOT NULL,
            session_id     TEXT DEFAULT '',
            game_day       TEXT DEFAULT '',
            player_qq      TEXT DEFAULT '',
            role_name      TEXT DEFAULT '',
            reward_data    TEXT DEFAULT '{}',
            distributed_at INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reward_records_show ON reward_records(show_id)")

    # ── 9. blacklist 表 ─────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  INTEGER NOT NULL,
            qq         TEXT NOT NULL DEFAULT '',
            role_name  TEXT DEFAULT '',
            content    TEXT DEFAULT '',
            tags       TEXT DEFAULT '',
            added_by   TEXT DEFAULT '',
            created_at INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_tenant ON blacklist(tenant_id)")

    # ── 10. players 加回复时间累计列 ────────────────────────────────────────
    if "reply_time_sum" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN reply_time_sum  INTEGER NOT NULL DEFAULT 0")
    if "reply_time_count" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN reply_time_count INTEGER NOT NULL DEFAULT 0")

    # ── 11. players 加 is_npc 标记列 ─────────────────────────────────────────
    if "is_npc" not in _col_names(conn, "players"):
        conn.execute("ALTER TABLE players ADD COLUMN is_npc INTEGER NOT NULL DEFAULT 0")

    # ── 12. rp_entries 加 reply_time_ms 列并回填历史数据 ──────────────────────
    if "reply_time_ms" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN reply_time_ms INTEGER")
        # 回填：对每条 entry，找同 session 内上一条不同角色的 entry，计算时间差
        entries = conn.execute(
            "SELECT id, session_id, role_name, timestamp FROM rp_entries WHERE timestamp > 0 ORDER BY session_id, seq"
        ).fetchall()
        # 按 session 分组，追踪每个 session 里最后一条不同角色的 timestamp
        last_other: dict = {}  # session_id → {role_name → last_ts_of_other_roles}
        for e in entries:
            eid, sid, role, ts = e["id"], e["session_id"], e["role_name"], e["timestamp"]
            if sid not in last_other:
                last_other[sid] = {}
            # 找这个 session 里，其他角色最近一条的 ts
            others = [t for r, t in last_other[sid].items() if r != role]
            if others:
                prev_ts = max(others)
                diff = ts - prev_ts
                if 0 < diff < 7_200_000:  # 0~2小时内有效
                    conn.execute("UPDATE rp_entries SET reply_time_ms=? WHERE id=?", (diff, eid))
            # 更新这个角色在这个 session 的最后 ts
            last_other[sid][role] = ts
        print(f"[migrate] rp_entries reply_time_ms 回填完成，共 {len(entries)} 条")

    # ── 13. rp_entries 加 is_excluded 标记列 ─────────────────────────────────
    if "is_excluded" not in _col_names(conn, "rp_entries"):
        conn.execute("ALTER TABLE rp_entries ADD COLUMN is_excluded INTEGER NOT NULL DEFAULT 0")

    # ── 14. shows 加档期三列（MMDD 格式，空串 = 不限制）──────────────────────
    if "schedule_start" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN schedule_start TEXT NOT NULL DEFAULT ''")
    if "schedule_end" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN schedule_end TEXT NOT NULL DEFAULT ''")
    if "supplement_end" not in _col_names(conn, "shows"):
        conn.execute("ALTER TABLE shows ADD COLUMN supplement_end TEXT NOT NULL DEFAULT ''")

    conn.commit()

def init_db():
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with open(schema, encoding="utf-8") as f:
            conn.executescript(f.read())
        _migrate(conn)
    finally:
        conn.close()

def ts_to_str(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

def fmt_seconds(secs):
    secs = int(secs)
    return f"{secs//60}分{secs%60}秒" if secs >= 60 else f"{secs}秒"


# ── Auth ─────────────────────────────────────────────────────────────────────

def current_tenant_id():
    return session.get("tenant_id")

def get_show_id():
    """当前管理员正在查看的季 ID（存于 session）。"""
    sid = session.get("view_show_id")
    if sid:
        return sid
    tid = current_tenant_id()
    if not tid:
        return None
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tid,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? ORDER BY id", (tid,)).fetchone()
    if row:
        session["view_show_id"] = row["id"]
        return row["id"]
    return None

def get_current_show_id_for_tenant(tenant_id):
    """API 用：找该租户当前活跃季的 ID。"""
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)).fetchone()
    return row["id"] if row else None

def get_current_show_for_tenant(tenant_id):
    """API 用：返回当前活跃季的完整行（dict），含档期字段。"""
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT * FROM shows WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)).fetchone()
    return dict(row) if row else None

# ── 档期时区工具 ──────────────────────────────────────────────────────────────
def _parse_mmdd(mmdd, ref_year=None):
    """将 "MMDD" 字符串解析为 date 对象；格式不合法则返回 None。"""
    if not mmdd or len(mmdd) != 4:
        return None
    try:
        year = ref_year or _date.today().year
        return _date(year, int(mmdd[:2]), int(mmdd[2:]))
    except (ValueError, TypeError):
        return None

def _schedule_zone(show, now_ts_ms=None):
    """
    返回当前时刻相对于该季档期所处的区段：
      'pre'        – schedule_start 之前（不记录）
      'main'       – schedule_start ~ schedule_end（正常记录）
      'supplement' – schedule_end+1 ~ supplement_end（只记录场次，不计弧长）
      'post'       – supplement_end 之后（不记录）

    未设置档期（schedule_start 为空）→ 始终返回 'main'。
    """
    if not show:
        return 'main'
    start_str = show.get("schedule_start") or ""
    if not start_str:
        return 'main'

    if now_ts_ms:
        today = datetime.fromtimestamp(now_ts_ms / 1000).date()
    else:
        today = _date.today()

    year  = today.year
    start = _parse_mmdd(start_str, year)
    end   = _parse_mmdd(show.get("schedule_end") or start_str, year)
    supp  = _parse_mmdd(show.get("supplement_end") or "", year)

    if not start or not end:
        return 'main'

    if today < start:
        return 'pre'
    if today <= end:
        return 'main'
    if supp and today <= supp:
        return 'supplement'
    return 'post'

@app.context_processor
def inject_show_context():
    if not session.get("tenant_id"):
        return {}
    tid   = current_tenant_id()
    db    = get_db()
    shows = [dict(s) for s in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)
    ).fetchall()]
    sid   = get_show_id()
    cur   = next((s for s in shows if s["id"] == sid), None)
    return {"all_shows": shows, "current_show_id": sid, "current_show": cur}

def require_login(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("tenant_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def require_admin(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("tenant_id"):
            return redirect(url_for("login"))
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped

def require_superadmin(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("superadmin_logged_in"):
            return redirect(url_for("superadmin_login"))
        return f(*args, **kwargs)
    return wrapped

def get_tenant_from_token():
    token = request.headers.get("X-Archive-Token", "")
    if not token:
        abort(403)
    row = get_db().execute("SELECT id FROM tenants WHERE api_token=?", (token,)).fetchone()
    if not row:
        abort(403)
    return row["id"]


# ── 登录路由 ─────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        tenant   = get_db().execute("SELECT * FROM tenants WHERE username=?", (username,)).fetchone()
        if tenant and check_password_hash(tenant["view_password_hash"], password):
            session["tenant_id"]           = tenant["id"]
            session["tenant_username"]     = tenant["username"]
            session["tenant_display_name"] = tenant["display_name"] or tenant["username"]
            session.pop("view_show_id", None)
            return redirect(url_for("home"))
        error = "用户名或密码错误，请重试。"
    current_user = session.get("tenant_display_name") or session.get("tenant_username")
    return render_template("login.html", error=error, current_user=current_user)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/admin/login", methods=["GET", "POST"])
@require_login
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        tenant   = get_db().execute("SELECT * FROM tenants WHERE id=?", (current_tenant_id(),)).fetchone()
        if tenant and check_password_hash(tenant["admin_password_hash"], password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        error = "后台密钥错误，请重试。"
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

@app.route("/admin/change_password", methods=["POST"])
@require_admin
def admin_change_password():
    tid = current_tenant_id()
    vp  = request.form.get("view_password", "").strip()
    ap  = request.form.get("admin_password", "").strip()
    db  = get_db()
    if vp:
        db.execute("UPDATE tenants SET view_password_hash=? WHERE id=?", (generate_password_hash(vp), tid))
    if ap:
        db.execute("UPDATE tenants SET admin_password_hash=? WHERE id=?", (generate_password_hash(ap), tid))
    db.commit()
    if vp:
        session.clear()
        return redirect(url_for("login"))
    if ap:
        session.pop("admin_logged_in", None)
        return redirect(url_for("admin_login"))
    return redirect(url_for("admin") + "?pwd_changed=1")

@app.route("/admin/backup")
@require_admin
def admin_backup():
    return send_file(DB_PATH, as_attachment=True, download_name="rp_data.db",
                     mimetype="application/octet-stream")


# ── 超管路由 ─────────────────────────────────────────────────────────────────

@app.route("/superadmin/login", methods=["GET", "POST"])
def superadmin_login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), SUPERADMIN_PASS):
            session["superadmin_logged_in"] = True
            return redirect(url_for("superadmin"))
        error = "超管密码错误。"
    return render_template("superadmin_login.html", error=error)

@app.route("/superadmin/logout")
def superadmin_logout():
    session.pop("superadmin_logged_in", None)
    session.pop("superadmin_acting", None)
    session.pop("tenant_id", None)
    session.pop("admin_logged_in", None)
    session.pop("view_show_id", None)
    return redirect(url_for("superadmin_login"))

@app.route("/superadmin/tenant/<int:tid>/enter", methods=["POST"])
@require_superadmin
def superadmin_enter_tenant(tid):
    tenant = get_db().execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
    if not tenant: abort(404)
    session["tenant_id"]           = tenant["id"]
    session["tenant_username"]     = tenant["username"]
    session["tenant_display_name"] = tenant["display_name"] or tenant["username"]
    session["admin_logged_in"]     = True
    session["superadmin_acting"]   = True
    session.pop("view_show_id", None)
    return redirect(url_for("home"))

@app.route("/superadmin/exit_tenant", methods=["POST"])
def superadmin_exit_tenant():
    session.pop("tenant_id", None)
    session.pop("tenant_username", None)
    session.pop("tenant_display_name", None)
    session.pop("admin_logged_in", None)
    session.pop("superadmin_acting", None)
    session.pop("view_show_id", None)
    return redirect(url_for("superadmin"))

@app.route("/superadmin")
@require_superadmin
def superadmin():
    db      = get_db()
    tenants = [dict(t) for t in db.execute("SELECT * FROM tenants ORDER BY created_at DESC").fetchall()]
    for t in tenants:
        tid = t["id"]
        t["session_count"]  = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE tenant_id=?", (tid,)).fetchone()[0]
        t["created_at_str"] = ts_to_str(t.get("created_at"))
        t["shows"]          = [dict(s) for s in db.execute(
            "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()]
    return render_template("superadmin_tenants.html", tenants=tenants,
                           created=request.args.get("created"),
                           deleted=request.args.get("deleted"),
                           error=request.args.get("error"))

@app.route("/superadmin/players")
@require_superadmin
def superadmin_players():
    db  = get_db()
    qq  = request.args.get("qq", "").strip()
    rows = []
    summary = None
    if qq:
        rows = db.execute("""
            SELECT p.qq, p.role_name, p.show_name, p.show_id,
                   p.sessions_count, p.total_replies, p.total_words, p.last_updated,
                   p.reply_time_sum, p.reply_time_count,
                   t.username AS tenant_username, t.display_name AS tenant_display,
                   s.name AS arc_name
            FROM players p
            JOIN tenants t ON p.tenant_id = t.id
            JOIN shows   s ON p.show_id   = s.id
            WHERE p.qq = ? OR p.role_name = ?
            ORDER BY p.last_updated DESC
        """, (qq, qq)).fetchall()
        rows = [dict(r) for r in rows]
        for r in rows:
            r["last_updated_str"] = ts_to_str(r["last_updated"])
            r["is_placeholder"] = (r["qq"] == r["role_name"])
        if rows:
            # 优先用 players 表累计的回复时间（即使 rp_entries 已清空也有数据）
            total_rts = sum(r.get("reply_time_sum", 0)   for r in rows)
            total_rtc = sum(r.get("reply_time_count", 0) for r in rows)
            if total_rtc > 0:
                global_avg_reply = (total_rts / total_rtc) / 1000  # 转秒
            else:
                # 回落：从 rp_entries 实时计算（旧数据兼容）
                role_names = list({r["role_name"] for r in rows if r["role_name"]})
                all_reply_times = []
                if role_names:
                    ph = ",".join("?" * len(role_names))
                    all_entries = db.execute(
                        f"SELECT session_id,role_name,timestamp FROM rp_entries WHERE role_name IN ({ph}) AND timestamp > 0 ORDER BY session_id,seq,timestamp",
                        role_names
                    ).fetchall()
                    by_sess = defaultdict(list)
                    for e in all_entries:
                        by_sess[e["session_id"]].append(dict(e))
                    for entries in by_sess.values():
                        for rn in role_names:
                            times = [
                                (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000
                                for i in range(1, len(entries))
                                if entries[i]["role_name"] == rn and entries[i-1]["role_name"] != rn
                                and 0 < (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000 < 7200
                            ]
                            all_reply_times.extend(times)
                global_avg_reply = sum(all_reply_times) / len(all_reply_times) if all_reply_times else None

            summary = {
                "qq": qq,
                "total_sessions": sum(r["sessions_count"] for r in rows),
                "total_replies":  sum(r["total_replies"]  for r in rows),
                "total_words":    sum(r["total_words"]    for r in rows),
                "arc_count":      len(rows),
                "global_avg_reply": global_avg_reply,
            }

            # ── 按场次类型拆分统计 ────────────────────────────────────────
            _TRACKED = ["私密", "电话", "官约", "心愿"]
            def _empty_subtype(): return {t: {"sessions": 0, "replies": 0, "words": 0} for t in _TRACKED}
            global_subtype = _empty_subtype()
            arc_subtype    = {}   # show_id → {subtype → {...}}
            for r in rows:
                sid_key   = r["show_id"]
                role_name = r["role_name"]
                if not role_name: continue
                arc_subtype[sid_key] = _empty_subtype()
                sess_rows = db.execute(
                    "SELECT subtype, stats FROM sessions WHERE show_id=? AND participants LIKE ?",
                    (sid_key, f'%{json.dumps(role_name, ensure_ascii=False)}%')
                ).fetchall()
                for s in sess_rows:
                    stype = (s["subtype"] or "私密").strip()
                    if stype not in _TRACKED: continue
                    try:
                        role_st = json.loads(s["stats"] or "{}").get(role_name, {})
                        for dest in (global_subtype[stype], arc_subtype[sid_key][stype]):
                            dest["sessions"] += 1
                            dest["replies"]  += role_st.get("replies", 0)
                            dest["words"]    += role_st.get("words",   0)
                    except Exception:
                        pass
    # blacklist records for this QQ (across all tenants)
    bl_records = []
    if qq:
        bl_rows = db.execute("""
            SELECT b.*, t.display_name AS tenant_display, t.username AS tenant_username
            FROM blacklist b
            JOIN tenants t ON b.tenant_id = t.id
            WHERE b.qq = ?
            ORDER BY b.created_at DESC
        """, (qq,)).fetchall()
        bl_records = [dict(r) for r in bl_rows]

    # top players across all tenants (for browse view, 排除 NPC)
    top = db.execute("""
        SELECT qq, SUM(total_replies) AS replies, SUM(total_words) AS words,
               COUNT(*) AS arc_count, MAX(last_updated) AS last_updated
        FROM players WHERE is_npc=0 GROUP BY qq
        ORDER BY words DESC LIMIT 50
    """).fetchall()
    top = [dict(r) for r in top]
    for r in top:
        r["last_updated_str"] = ts_to_str(r["last_updated"])
    return render_template("superadmin_players.html",
                           qq=qq, rows=rows, summary=summary, top=top,
                           fmt_seconds=fmt_seconds, bl_records=bl_records, ts_to_str=ts_to_str,
                           global_subtype=global_subtype if summary else {},
                           arc_subtype=arc_subtype if summary else {},
                           tracked_subtypes=["私密", "电话", "官约", "心愿"])

@app.route("/superadmin/analysis")
@require_superadmin
def superadmin_analysis():
    qq = request.args.get("qq", "").strip()
    return render_template("superadmin_analysis.html", qq=qq)

@app.route("/superadmin/api/all_players")
@require_superadmin
def superadmin_api_all_players():
    """返回所有有 rp_entries 的玩家列表，供分析页 dropdown 使用。"""
    db = get_db()
    # 按 QQ 聚合，同时返回每个 (role_name, show_name) 配对，避免跨租户同名角色混淆
    rows = db.execute("""
        SELECT p.qq,
               COUNT(DISTINCT e.id)  AS entry_count,
               COUNT(DISTINCT p.show_id) AS show_count,
               GROUP_CONCAT(DISTINCT p.role_name || '|' || COALESCE(sh.name,'?')) AS role_shows
        FROM players p
        JOIN rp_entries e ON e.role_name = p.role_name AND e.show_id = p.show_id
        LEFT JOIN shows sh ON p.show_id = sh.id
        WHERE p.qq != '' AND p.is_npc = 0 AND e.timestamp > 0
        GROUP BY p.qq
        ORDER BY entry_count DESC
    """).fetchall()
    result = []
    for r in rows:
        pairs = []
        seen = set()
        for item in (r["role_shows"] or "").split(","):
            if "|" in item and item not in seen:
                seen.add(item)
                role, show = item.split("|", 1)
                pairs.append({"role": role, "show": show})
        result.append({
            "qq": r["qq"],
            "entry_count": r["entry_count"],
            "show_count": r["show_count"],
            "roles": pairs,
        })
    return jsonify({"ok": True, "players": result})

@app.route("/superadmin/api/player_entries")
@require_superadmin
def superadmin_api_player_entries():
    """返回某 QQ 所有 rp_entries 的 JSON，供前端图表使用。"""
    qq = request.args.get("qq", "").strip()
    if not qq:
        return jsonify({"ok": False, "error": "missing qq"}), 400
    db = get_db()
    # 找到该 QQ 的所有 (role_name, show_id) 配对，跨租户但不跨角色
    player_rows = db.execute(
        "SELECT role_name, show_id FROM players WHERE qq=? AND role_name!=''", (qq,)
    ).fetchall()
    if not player_rows:
        return jsonify({"ok": True, "entries": [], "roles": []})

    # 用 (role_name, show_id) 配对过滤，避免不同租户同名角色串数据
    pairs = [(r["role_name"], r["show_id"]) for r in player_rows]
    role_names = list({r["role_name"] for r in player_rows})

    # 构造 WHERE (e.role_name=? AND e.show_id=?) OR ...
    pair_clauses = " OR ".join(["(e.role_name=? AND e.show_id=?)"] * len(pairs))
    pair_params  = [v for p in pairs for v in p]

    entries = db.execute(
        f"""SELECT e.id, e.session_id, e.role_name, e.seq, e.timestamp,
                   e.reply_time_ms, e.is_excluded,
                   length(e.content) AS char_count,
                   s.subtype, s.game_day, e.show_id,
                   sh.name AS show_name
            FROM rp_entries e
            JOIN sessions s ON e.session_id = s.id
            LEFT JOIN shows sh ON e.show_id = sh.id
            WHERE ({pair_clauses}) AND e.timestamp > 0
            ORDER BY e.timestamp ASC""",
        pair_params
    ).fetchall()
    return jsonify({
        "ok": True,
        "roles": role_names,
        "entries": [dict(e) for e in entries]
    })

@app.route("/superadmin/entry/<int:entry_id>/toggle_exclude", methods=["POST"])
@require_superadmin
def superadmin_toggle_exclude(entry_id):
    db = get_db()
    row = db.execute("SELECT is_excluded FROM rp_entries WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    new_val = 0 if row["is_excluded"] else 1
    db.execute("UPDATE rp_entries SET is_excluded=? WHERE id=?", (new_val, entry_id))
    db.commit()
    return jsonify({"ok": True, "is_excluded": new_val})

@app.route("/api/new_season", methods=["POST"])
def api_new_season():
    tid  = get_tenant_from_token()
    data = request.json or {}
    name = (data.get("name") or "").strip()
    mode = (data.get("mode") or "review").strip()   # "review" | "no_review"
    if not name:
        return jsonify({"ok": False, "error": "missing name"}), 400

    # 档期字段（MMDD 格式，可选）
    sched_start = (data.get("schedule_start") or "").strip()
    sched_end   = (data.get("schedule_end")   or "").strip()
    supp_end    = (data.get("supplement_end") or "").strip()

    db = get_db()
    # 把已有 is_current=1 的 show 全部关掉（处理 JSCLEAR 未先结束季度的情况）
    db.execute("UPDATE shows SET is_current=0 WHERE tenant_id=? AND is_current=1", (tid,))
    # 建新 show
    token = secrets.token_urlsafe(24)
    db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,public_view_enabled,public_token,"
        "created_at,schedule_start,schedule_end,supplement_end) "
        "VALUES (?,?,?,1,0,?,?,?,?,?)",
        (tid, name, mode, token, int(time.time() * 1000),
         sched_start, sched_end, supp_end)
    )
    db.commit()
    show = db.execute("SELECT id FROM shows WHERE public_token=?", (token,)).fetchone()
    return jsonify({"ok": True, "show_id": show["id"], "name": name, "mode": mode,
                    "schedule_start": sched_start, "schedule_end": sched_end,
                    "supplement_end": supp_end})

@app.route("/api/current_season", methods=["POST"])
def api_current_season():
    """返回该租户当前活跃 show 的信息，供 bot 初始化 season_show_name。"""
    tid = get_tenant_from_token()
    db  = get_db()
    show = db.execute(
        "SELECT id, name, description FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show:
        # 没有 is_current=1，取最新的
        show = db.execute(
            "SELECT id, name, description FROM shows WHERE tenant_id=? ORDER BY id DESC LIMIT 1", (tid,)
        ).fetchone()
    if not show:
        return jsonify({"ok": False, "error": "no show found"}), 404
    mode = show["description"] if show["description"] in ("review", "no_review") else "review"
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "mode": mode,
                    "schedule_start": show["schedule_start"] or "",
                    "schedule_end":   show["schedule_end"]   or "",
                    "supplement_end": show["supplement_end"] or ""})

@app.route("/api/update_schedule", methods=["POST"])
def api_update_schedule():
    """Bot 用：更新当前活跃季的档期（Token 鉴权）。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show:
        return jsonify({"ok": False, "error": "no active season"}), 404
    data  = request.json or {}
    start = (data.get("schedule_start") or "").strip()
    end   = (data.get("schedule_end")   or "").strip()
    supp  = (data.get("supplement_end") or "").strip()
    for v in (start, end, supp):
        if v and (len(v) != 4 or not v.isdigit()):
            return jsonify({"ok": False, "error": f"格式错误：{v}，需为 MMDD 四位数字"}), 400
    db = get_db()
    db.execute(
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=? WHERE id=?",
        (start, end, supp, show["id"])
    )
    db.commit()
    return jsonify({"ok": True, "show_id": show["id"],
                    "schedule_start": start, "schedule_end": end, "supplement_end": supp})

@app.route("/api/end_season", methods=["POST"])
def api_end_season():
    tid = get_tenant_from_token()
    db  = get_db()
    show = db.execute(
        "SELECT id, name, public_token FROM shows WHERE tenant_id=? AND is_current=1", (tid,)
    ).fetchone()
    if not show:
        return jsonify({"ok": False, "error": "no active season"}), 404
    db.execute("UPDATE shows SET is_current=0 WHERE id=?", (show["id"],))
    db.commit()
    base_url = request.host_url.rstrip("/")
    public_url = f"{base_url}/public/{show['public_token']}" if show["public_token"] else base_url
    return jsonify({"ok": True, "show_id": show["id"], "name": show["name"], "public_url": public_url})

@app.route("/superadmin/cleanup_empty_sessions", methods=["POST"])
@require_superadmin
def superadmin_cleanup_empty_sessions():
    db = get_db()
    # 找出已结束（end_ts>0）且无任何 rp_entries 的 session
    rows = db.execute("""
        SELECT s.id FROM sessions s
        WHERE s.end_ts > 0
        AND (SELECT count(*) FROM rp_entries e WHERE e.session_id = s.id) = 0
    """).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        ph = ",".join("?" * len(ids))
        db.execute(f"DELETE FROM sessions WHERE id IN ({ph})", ids)
        db.commit()
    return jsonify({"ok": True, "deleted": len(ids), "ids": ids})

@app.route("/superadmin/tenant/new", methods=["POST"])
@require_superadmin
def superadmin_tenant_new():
    username     = request.form.get("username", "").strip()
    view_pw      = request.form.get("view_password", "").strip()
    admin_pw     = request.form.get("admin_password", "").strip()
    display_name = request.form.get("display_name", "").strip()
    if not username or not view_pw or not admin_pw:
        return redirect(url_for("superadmin") + "?error=missing_fields")
    token = secrets.token_urlsafe(24)
    now   = int(time.time() * 1000)
    db    = get_db()
    try:
        db.execute(
            "INSERT INTO tenants (username,view_password_hash,admin_password_hash,api_token,display_name,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(view_pw), generate_password_hash(admin_pw),
             token, display_name, now)
        )
        db.commit()
        # 自动为新租户创建第一季
        new_tenant = db.execute("SELECT id FROM tenants WHERE username=?", (username,)).fetchone()
        if new_tenant:
            db.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,0,?,?)",
                (new_tenant["id"], "第一季", secrets.token_urlsafe(24), now)
            )
            db.commit()
    except sqlite3.IntegrityError:
        return redirect(url_for("superadmin") + "?error=duplicate")
    return redirect(url_for("superadmin") + "?created=1")

@app.route("/superadmin/tenant/<int:tid>/delete", methods=["POST"])
@require_superadmin
def superadmin_tenant_delete(tid):
    db = get_db()
    for table in ("sessions", "rp_entries", "extra_events", "players", "site_config"):
        db.execute(f"DELETE FROM {table} WHERE tenant_id=?", (tid,))
    db.execute("DELETE FROM shows   WHERE tenant_id=?", (tid,))
    db.execute("DELETE FROM tenants WHERE id=?",        (tid,))
    db.commit()
    return redirect(url_for("superadmin") + "?deleted=1")

@app.route("/superadmin/tenant/<int:tid>/reset_token", methods=["POST"])
@require_superadmin
def superadmin_tenant_reset_token(tid):
    db = get_db()
    db.execute("UPDATE tenants SET api_token=? WHERE id=?", (secrets.token_urlsafe(24), tid))
    db.commit()
    return redirect(url_for("superadmin") + "?created=1")

@app.route("/superadmin/tenant/<int:tid>/set_password", methods=["POST"])
@require_superadmin
def superadmin_set_password(tid):
    pw_type = request.form.get("pw_type")
    new_pw  = request.form.get("new_password", "").strip()
    if not new_pw or pw_type not in ("view", "admin"):
        return redirect(url_for("superadmin") + "?error=missing_fields")
    col = "view_password_hash" if pw_type == "view" else "admin_password_hash"
    db  = get_db()
    db.execute(f"UPDATE tenants SET {col}=? WHERE id=?", (generate_password_hash(new_pw), tid))
    db.commit()
    return redirect(url_for("superadmin") + "?created=1")


# ── 季管理路由 ───────────────────────────────────────────────────────────────

@app.route("/admin/shows")
@require_admin
def admin_shows():
    tid   = current_tenant_id()
    db    = get_db()
    shows = [dict(s) for s in db.execute(
        "SELECT * FROM shows WHERE tenant_id=? ORDER BY created_at", (tid,)
    ).fetchall()]
    for s in shows:
        s["session_count"] = db.execute(
            "SELECT COUNT(*) FROM sessions WHERE show_id=?", (s["id"],)
        ).fetchone()[0]
        s["created_at_str"] = ts_to_str(s.get("created_at"))
    return render_template("admin_shows.html", shows=shows,
                           current_view=get_show_id(),
                           msg=request.args.get("msg"))

@app.route("/admin/shows/new", methods=["POST"])
@require_admin
def admin_show_new():
    tid  = current_tenant_id()
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    if not name:
        return redirect(url_for("admin_shows") + "?msg=empty_name")
    db  = get_db()
    count = db.execute("SELECT COUNT(*) FROM shows WHERE tenant_id=?", (tid,)).fetchone()[0]
    if count >= 5:
        return redirect(url_for("admin_shows") + "?msg=limit_reached")
    now = int(time.time() * 1000)
    db.execute(
        "INSERT INTO shows (tenant_id,name,description,is_current,public_view_enabled,public_token,created_at) "
        "VALUES (?,?,?,0,0,?,?)",
        (tid, name, desc, secrets.token_urlsafe(24), now)
    )
    db.commit()
    return redirect(url_for("admin_shows") + "?msg=created")

@app.route("/admin/shows/<int:sid>/activate", methods=["POST"])
@require_admin
def admin_show_activate(sid):
    """将指定季设为「当前季」（机器人数据写入此季）。"""
    tid = current_tenant_id()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    db.execute("UPDATE shows SET is_current=0 WHERE tenant_id=?", (tid,))
    db.execute("UPDATE shows SET is_current=1 WHERE id=?", (sid,))
    db.commit()
    session.pop("view_show_id", None)
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_shows") + "?msg=activated")

@app.route("/admin/shows/<int:sid>/view", methods=["POST"])
@require_admin
def admin_show_view(sid):
    """切换管理员当前查看的季。"""
    tid = current_tenant_id()
    if not get_db().execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    session["view_show_id"] = sid
    return redirect(url_for("home"))

@app.route("/admin/shows/<int:sid>/toggle_public", methods=["POST"])
@require_admin
def admin_show_toggle_public(sid):
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    new_state = 0 if row["public_view_enabled"] else 1
    db.execute("UPDATE shows SET public_view_enabled=? WHERE id=?", (new_state, sid))
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True, "enabled": bool(new_state)})
    return redirect(url_for("admin_shows"))

@app.route("/admin/shows/<int:sid>/schedule", methods=["POST"])
@require_admin
def admin_show_schedule(sid):
    """更新该季的档期设置。"""
    tid = current_tenant_id()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    data = request.json or {}
    start = (data.get("schedule_start") or "").strip()
    end   = (data.get("schedule_end")   or "").strip()
    supp  = (data.get("supplement_end") or "").strip()
    # 简单格式校验：空串或 4 位数字
    for v in (start, end, supp):
        if v and (len(v) != 4 or not v.isdigit()):
            return jsonify({"ok": False, "error": f"格式错误：{v}，需为 MMDD 四位数字"}), 400
    db.execute(
        "UPDATE shows SET schedule_start=?, schedule_end=?, supplement_end=? WHERE id=?",
        (start, end, supp, sid)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/admin/shows/<int:sid>/reset_token", methods=["POST"])
@require_admin
def admin_show_reset_token(sid):
    tid = current_tenant_id()
    db  = get_db()
    if not db.execute("SELECT id FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone():
        abort(404)
    db.execute("UPDATE shows SET public_token=? WHERE id=?", (secrets.token_urlsafe(24), sid))
    db.commit()
    return redirect(url_for("admin_shows"))

@app.route("/admin/shows/<int:sid>/delete", methods=["POST"])
@require_admin
def admin_show_delete(sid):
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute("SELECT * FROM shows WHERE id=? AND tenant_id=?", (sid, tid)).fetchone()
    if not row:
        abort(404)
    if row["is_current"]:
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": False, "error": "cannot_delete_current"})
        return redirect(url_for("admin_shows") + "?msg=cannot_delete_current")
    for table in ("sessions", "rp_entries", "extra_events", "players", "site_config"):
        db.execute(f"DELETE FROM {table} WHERE show_id=?", (sid,))
    db.execute("DELETE FROM shows WHERE id=?", (sid,))
    db.commit()
    if session.get("view_show_id") == sid:
        session.pop("view_show_id", None)
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_shows") + "?msg=deleted")


# ── 配置路由 ─────────────────────────────────────────────────────────────────

def _parse_routing_text(text):
    import re
    pairs = re.findall(r'(D\d+)[：:]\s*(\d+)', text or "", re.IGNORECASE)
    return json.dumps({k.upper(): v for k, v in pairs}, ensure_ascii=False)

def _routing_to_display(json_str):
    try:
        m = json.loads(json_str or "{}")
        return " ".join(f"{k}:{v}" for k, v in sorted(m.items()))
    except Exception:
        return ""

@app.route("/admin/config", methods=["GET", "POST"])
@require_admin
def admin_config_page():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    if request.method == "POST":
        new_flat = {}
        for sec in CONFIG_SCHEMA:
            for f in sec["fields"]:
                db_key = _cfg_db_key(sec, f["key"])
                if f["type"] == "bool":
                    value = "true" if request.form.get(db_key) else "false"
                elif f["type"] == "routing":
                    value = _parse_routing_text(request.form.get(db_key, ""))
                else:
                    value = request.form.get(db_key, str(f["default"]))
                new_flat[db_key] = value
        # 保存物品注册表与属性定义（JSON blob，不经过 CONFIG_SCHEMA）
        for blob_key in ("item_registry", "rpg_attr_defs", "sys_attr_presets",
                         "end_game_bonus_templates", "end_game_draw_config",
                         "item_registry_pending"):
            raw = request.form.get(blob_key, "")
            if raw:
                try:
                    json.loads(raw)
                    new_flat[blob_key] = raw
                except json.JSONDecodeError:
                    pass
        # 快照到 config_history
        operator = (session.get("tenant_display_name") or
                    session.get("tenant_username") or "unknown")
        db.execute(
            "INSERT INTO config_history(show_id,tenant_id,config_data,operator,created_at) VALUES(?,?,?,?,?)",
            (sid, tid, json.dumps(new_flat, ensure_ascii=False), operator, int(time.time() * 1000))
        )
        # 写入 site_config（live 存储）
        for db_key, value in new_flat.items():
            db.execute(
                "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
                "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
                (sid, tid, db_key, value)
            )
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
        return redirect(url_for("admin_config_page") + "?saved=1")
    flat = get_flat_config(db, sid)
    routing_display = {}
    for sec in CONFIG_SCHEMA:
        for f in sec["fields"]:
            if f["type"] == "routing":
                db_key = _cfg_db_key(sec, f["key"])
                routing_display[db_key] = _routing_to_display(flat.get(db_key, ""))
    last_sync_ts = flat.get("_last_bot_sync")
    last_sync = ts_to_str(int(last_sync_ts)) if last_sync_ts else None
    item_registry_json       = flat.get("item_registry", "{}")
    attr_defs_json           = flat.get("rpg_attr_defs", "{}")
    pool_defs_json           = flat.get("pool_definitions", "{}")
    end_bonus_templates_json = flat.get("end_game_bonus_templates", "[]")
    item_pending_json        = flat.get("item_registry_pending", "[]")
    tpl_rows = db.execute(
        "SELECT id, name, config_data, created_at FROM config_templates "
        "WHERE tenant_id=? ORDER BY created_at DESC",
        (tid,)
    ).fetchall()
    cfg_templates = [
        {"id": r["id"], "name": r["name"],
         "data": json.loads(r["config_data"]),
         "time_str": ts_to_str(r["created_at"])}
        for r in tpl_rows
    ]
    return render_template("admin_config.html", schema=CONFIG_SCHEMA,
                           flat=flat, routing_display=routing_display,
                           saved=request.args.get("saved"), last_sync=last_sync,
                           item_registry_json=item_registry_json,
                           attr_defs_json=attr_defs_json,
                           pool_defs_json=pool_defs_json,
                           end_bonus_templates_json=end_bonus_templates_json,
                           item_pending_json=item_pending_json,
                           cfg_templates=cfg_templates,
                           tpl_msg=request.args.get("tpl_msg"),
                           tpl_max=_TEMPLATE_MAX)


# ── 配置历史路由 ─────────────────────────────────────────────────────────────

@app.route("/admin/config/history")
@require_admin
def admin_config_history():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    rows = db.execute(
        "SELECT id, config_data, operator, created_at FROM config_history "
        "WHERE show_id=? ORDER BY created_at DESC LIMIT 50",
        (sid,)
    ).fetchall()
    # 提取每条快照的摘要字段供展示
    entries = []
    for r in rows:
        try:
            flat = json.loads(r["config_data"])
        except Exception:
            flat = {}
        entries.append({
            "id":         r["id"],
            "operator":   r["operator"],
            "created_at": r["created_at"],
            "time_str":   ts_to_str(r["created_at"]),
            "show_name":  flat.get("love_show_name", ""),
            "days":       flat.get("global_days", ""),
            "key_count":  len(flat),
        })
    return render_template("admin_config_history.html", entries=entries)


@app.route("/admin/config/history/<int:hid>/rollback", methods=["POST"])
@require_admin
def admin_config_rollback(hid):
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    row = db.execute(
        "SELECT config_data FROM config_history WHERE id=? AND show_id=?",
        (hid, sid)
    ).fetchone()
    if not row:
        abort(404)
    try:
        flat = json.loads(row["config_data"])
    except Exception:
        abort(400)
    # 写回 site_config
    for db_key, value in flat.items():
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, db_key, value)
        )
    # 把这次回滚也记一条快照
    operator = (session.get("tenant_display_name") or
                session.get("tenant_username") or "unknown")
    db.execute(
        "INSERT INTO config_history(show_id,tenant_id,config_data,operator,created_at) VALUES(?,?,?,?,?)",
        (sid, tid, row["config_data"], f"{operator} [回滚自 #{hid}]", int(time.time() * 1000))
    )
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_config_history") + "?rolled=1")


# ── 配置预设路由 ─────────────────────────────────────────────────────────────

_TEMPLATE_EXCLUDE_KEYS = frozenset({
    "item_registry", "item_registry_pending",
    "rpg_attr_defs", "sys_attr_presets",
    "end_game_bonus_templates", "end_game_draw_config",
    "_last_bot_sync",
})
_TEMPLATE_MAX = 5


@app.route("/admin/config/templates/save", methods=["POST"])
@require_admin
def admin_config_template_save():
    tid  = current_tenant_id()
    sid  = get_show_id()
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("admin_config_page") + "?tpl_msg=empty_name")
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM config_templates WHERE tenant_id=?", (tid,)).fetchone()[0] >= _TEMPLATE_MAX:
        return redirect(url_for("admin_config_page") + "?tpl_msg=limit")
    flat = get_flat_config(db, sid)
    data = {k: v for k, v in flat.items() if k not in _TEMPLATE_EXCLUDE_KEYS}
    db.execute(
        "INSERT INTO config_templates(tenant_id,name,config_data,created_at) VALUES(?,?,?,?)",
        (tid, name, json.dumps(data, ensure_ascii=False), int(time.time() * 1000))
    )
    db.commit()
    return redirect(url_for("admin_config_page") + "?tpl_msg=saved")


@app.route("/admin/config/templates/<int:tplid>/delete", methods=["POST"])
@require_admin
def admin_config_template_delete(tplid):
    tid = current_tenant_id()
    db  = get_db()
    db.execute("DELETE FROM config_templates WHERE id=? AND tenant_id=?", (tplid, tid))
    db.commit()
    if request.headers.get("X-Fetch") == "1":
        return jsonify({"ok": True})
    return redirect(url_for("admin_config_page") + "?tpl_msg=deleted")


# ── 数据浏览路由 ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    if not session.get("tenant_id"):
        return render_template("landing.html")
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT game_day, COUNT(*) AS session_count,
               SUM(total_replies) AS total_replies, SUM(total_words) AS total_words,
               MIN(start_ts) AS first_ts
        FROM sessions WHERE show_id=?
        GROUP BY game_day ORDER BY first_ts DESC
    """, (sid,)).fetchall()
    days, incomplete = [], []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        (days if (d["game_day"] or "").strip() else incomplete).append(d)
    return render_template("home.html", days=days, incomplete=incomplete)

@app.route("/date/<game_day>")
@require_login
def date_view(game_day):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE show_id=? AND game_day=? ORDER BY start_ts DESC", (sid, game_day)
    ).fetchall()
    show_names = get_show_names(db, sid)
    return render_template("date.html", game_day=game_day,
                           sessions=_enrich_sessions(rows), show_names=show_names)

@app.route("/session/<path:session_id>")
@require_login
def session_view(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess:
        abort(404)
    sess       = _enrich_session(dict(sess))
    rp         = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, sid)).fetchall()
    events     = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, sid)).fetchall())
    show_names = get_show_names(db, sid)
    is_admin = bool(session.get("admin_logged_in"))
    return render_template("session.html", sess=sess, rp=rp, events=events,
                           show_names=show_names, ts_to_str=ts_to_str,
                           is_admin=is_admin)

@app.route("/session/<path:session_id>/download")
@require_login
def session_download(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess:
        abort(404)
    sess      = _enrich_session(dict(sess))
    flat      = get_flat_config(db, sid)
    show_name = flat.get("love_show_name") or "长日将尽"
    rp        = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, sid)).fetchall()
    events    = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, sid)).fetchall())

    lines = ["=" * 40, f"【 {show_name} · {sess.get('game_day','')} 场次存档 】", "=" * 40]
    lines += [f"地点：{sess.get('place') or '未记录'}", f"时间段：{sess.get('game_time') or '—'}",
              f"类型：{sess.get('subtype') or '私密'}{'  【强结】' if sess.get('forced') else ''}",
              f"开始：{sess.get('start_str','')}  结束：{sess.get('end_str') or '—'}",
              f"参与者：{', '.join(sess.get('participants') or [])}", "", "【统计】",
              f"总回复：{sess.get('total_replies',0)}  总字数：{sess.get('total_words',0)}"]
    for role, st in (sess.get("stats") or {}).items():
        r2, w2 = st.get("replies", 0), st.get("words", 0)
        lines.append(f"{role}：{r2}回复 · {w2}字 · 均{w2//r2 if r2 else 0}字/回")
    lines += ["", "=" * 40, "【 RP 正文 】", "=" * 40, ""]
    for e in rp:
        e = dict(e)
        lines += [f"▷ {e.get('role_name','')}  {ts_to_str(e.get('timestamp',0))}", "─" * 20, e.get("content",""), ""]
    lines += ["=" * 40, "【 事件记录 】", "=" * 40]
    if events:
        from itertools import groupby
        events.sort(key=lambda x: x.get("type",""))
        for etype, grp in groupby(events, key=lambda x: x.get("type","")):
            _etype_names = {'lovemail':'心动信','sms':'短信','gift':'礼物'}
            lines.append(f"\n── {_etype_names.get(etype,etype)} ──")
            for ev in grp:
                lines.append(f"{ev.get('from_role','')} → {ev.get('to_role','')}")
                if ev.get("content"): lines.append(ev["content"])
    else:
        lines.append("（本场无记录）")

    buf      = io.BytesIO("\n".join(lines).encode("utf-8"))
    buf.seek(0)
    place    = (sess.get("place") or "场次").replace("/","_").replace("\\","_")
    filename = f"{(sess.get('game_day') or 'unknown').replace('/','_')}_{place}_{str(session_id)[:8]}.txt"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="text/plain; charset=utf-8")


@app.route("/session/<path:session_id>/rp/add", methods=["POST"])
@require_admin
def rp_add(session_id):
    sid  = get_show_id()
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, sid)).fetchone()
    if not sess: abort(404)
    role_name = request.form.get("role_name", "").strip()
    content   = request.form.get("content",   "").strip()
    after_id  = request.form.get("after_id",  "").strip()
    if not role_name or not content:
        return redirect(url_for("session_view", session_id=session_id))
    if after_id:
        after = db.execute("SELECT seq FROM rp_entries WHERE id=? AND session_id=? AND show_id=?",
                           (after_id, session_id, sid)).fetchone()
        if after:
            new_seq = after["seq"] + 1
            db.execute("UPDATE rp_entries SET seq=seq+1 WHERE session_id=? AND show_id=? AND seq>=?",
                       (session_id, sid, new_seq))
        else:
            row = db.execute("SELECT MAX(seq) FROM rp_entries WHERE session_id=? AND show_id=?",
                             (session_id, sid)).fetchone()
            new_seq = (row[0] or 0) + 1
    else:
        row = db.execute("SELECT MAX(seq) FROM rp_entries WHERE session_id=? AND show_id=?",
                         (session_id, sid)).fetchone()
        new_seq = (row[0] or 0) + 1
    db.execute(
        "INSERT INTO rp_entries (session_id, show_id, tenant_id, role_name, content, seq, timestamp) "
        "VALUES (?,?,?,?,?,?,?)",
        (session_id, sid, current_tenant_id(), role_name, content, new_seq, int(time.time() * 1000))
    )
    db.commit()
    return redirect(url_for("session_view", session_id=session_id))

@app.route("/session/<path:session_id>/rp/<int:entry_id>/delete", methods=["POST"])
@require_admin
def rp_delete(session_id, entry_id):
    sid = get_show_id()
    db  = get_db()
    db.execute("DELETE FROM rp_entries WHERE id=? AND session_id=? AND show_id=?",
               (entry_id, session_id, sid))
    db.commit()
    return redirect(url_for("session_view", session_id=session_id))

@app.route("/session/<path:session_id>/rp/<int:entry_id>/edit", methods=["POST"])
@require_admin
def rp_edit(session_id, entry_id):
    sid     = get_show_id()
    content = request.form.get("content", "").strip()
    if content:
        get_db().execute("UPDATE rp_entries SET content=? WHERE id=? AND session_id=? AND show_id=?",
                         (content, entry_id, session_id, sid))
        get_db().commit()
    return redirect(url_for("session_view", session_id=session_id))

# ── 管理后台路由 ─────────────────────────────────────────────────────────────

@app.route("/admin")
@require_admin
def admin():
    sid  = get_show_id()
    tid  = current_tenant_id()
    page = max(1, request.args.get("page", 1, type=int))
    db   = get_db()

    sessions_count = db.execute("SELECT COUNT(*) FROM sessions     WHERE show_id=?", (sid,)).fetchone()[0]
    rp_count       = db.execute("SELECT COUNT(*) FROM rp_entries   WHERE show_id=?", (sid,)).fetchone()[0]
    events_count   = db.execute("SELECT COUNT(*) FROM extra_events WHERE show_id=?", (sid,)).fetchone()[0]
    total_players  = db.execute("SELECT COUNT(*) FROM players       WHERE show_id=?", (sid,)).fetchone()[0]

    offset  = (page - 1) * PLAYERS_PER_PAGE
    players = db.execute(
        "SELECT * FROM players WHERE show_id=? ORDER BY sessions_count DESC, last_updated DESC LIMIT ? OFFSET ?",
        (sid, PLAYERS_PER_PAGE, offset)
    ).fetchall()
    total_pages = max(1, (total_players + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE)

    return render_template("admin.html",
                           sessions_count=sessions_count, rp_count=rp_count,
                           events_count=events_count, players=[dict(p) for p in players],
                           players_count=total_players, page=page, total_pages=total_pages,
                           cleared=request.args.get("cleared"), ts_to_str=ts_to_str)

@app.route("/admin/clear_all", methods=["POST"])
@require_admin
def admin_clear_all():
    sid = get_show_id()
    db  = get_db()
    for table in ("rp_entries", "extra_events", "sessions"):
        db.execute(f"DELETE FROM {table} WHERE show_id=?", (sid,))
    db.commit()
    return redirect(url_for("admin") + "?cleared=1")

@app.route("/admin/export.json")
@require_admin
def admin_export():
    sid  = get_show_id()
    db   = get_db()
    sessions_raw = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts", (sid,)).fetchall()
    sids = [r["id"] for r in sessions_raw]
    if sids:
        ph         = ",".join("?" * len(sids))
        rp_rows    = db.execute(f"SELECT * FROM rp_entries   WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,seq", [sid]+sids).fetchall()
        event_rows = db.execute(f"SELECT * FROM extra_events WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,timestamp", [sid]+sids).fetchall()
    else:
        rp_rows = event_rows = []

    rp_by, ev_by = defaultdict(list), defaultdict(list)
    for r in rp_rows:
        rp_by[r["session_id"]].append(dict(r))
    for e in event_rows:
        ei = dict(e)
        try: ei["extra_info"] = json.loads(ei.get("extra_info") or "{}")
        except Exception: ei["extra_info"] = {}
        ev_by[e["session_id"]].append(ei)

    out = []
    for s in sessions_raw:
        s = _enrich_session(dict(s))
        s["rp_entries"] = rp_by.get(s["id"], [])
        s["extra_events"] = ev_by.get(s["id"], [])
        out.append(s)

    buf      = io.BytesIO(json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    filename = f"rp_export_{session.get('tenant_username','data')}_{datetime.now().strftime('%Y%m%d')}.json"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/json; charset=utf-8")

@app.route("/admin/player/<qq>")
@require_admin
def admin_player(qq):
    sid = get_show_id()
    db  = get_db()
    player = db.execute("SELECT * FROM players WHERE show_id=? AND qq=?", (sid, qq)).fetchone()
    player = dict(player) if player else {"qq": qq, "role_name": "", "show_name": "", "sessions_count": 0, "total_replies": 0, "total_words": 0, "last_updated": 0}

    role_name = player.get("role_name", "")
    all_sessions = [_enrich_session(dict(s)) for s in
                    db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (sid,)).fetchall()]
    player_sessions = [s for s in all_sessions if role_name and role_name in s["participants"]]

    timing_stats = []
    if player_sessions:
        sids = [s["id"] for s in player_sessions]
        ph   = ",".join("?" * len(sids))
        all_entries = db.execute(
            f"SELECT session_id,role_name,timestamp FROM rp_entries WHERE show_id=? AND session_id IN ({ph}) ORDER BY session_id,seq,timestamp",
            [sid]+sids
        ).fetchall()
        by_sess = defaultdict(list)
        for e in all_entries:
            by_sess[e["session_id"]].append(dict(e))
        for s in player_sessions:
            entries = by_sess[s["id"]]
            times   = [
                (entries[i]["timestamp"] - entries[i-1]["timestamp"]) / 1000
                for i in range(1, len(entries))
                if entries[i]["role_name"] == role_name and entries[i-1]["role_name"] != role_name
                and entries[i]["timestamp"] > entries[i-1]["timestamp"]
            ]
            if times:
                timing_stats.append({"session_id": s["id"], "game_day": s.get("game_day",""),
                                     "place": s.get("place",""), "avg": sum(times)/len(times),
                                     "max": max(times), "min": min(times), "count": len(times)})

    # Hourly activity for this player
    role_name_str = role_name or ""
    hourly_rp = [0] * 24
    if role_name_str:
        rp_ts_rows = db.execute(
            "SELECT timestamp FROM rp_entries WHERE show_id=? AND role_name=? AND timestamp > 0",
            (sid, role_name_str)
        ).fetchall()
        for e in rp_ts_rows:
            try:
                hourly_rp[datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
            except Exception:
                pass
        evt_ts_rows = db.execute(
            "SELECT timestamp FROM extra_events WHERE show_id=? AND from_role=? AND type IN ('sms','gift') AND timestamp > 0",
            (sid, role_name_str)
        ).fetchall()
        for e in evt_ts_rows:
            try:
                hourly_rp[datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
            except Exception:
                pass

    # Per-session player stat from sessions.stats
    session_player_stats = []
    for s in player_sessions:
        st = s.get("stats", {}).get(role_name_str, {})
        session_player_stats.append({
            "session": s,
            "replies": st.get("replies", 0),
            "words":   st.get("words",   0),
        })

    all_times = []
    for t in timing_stats:
        all_times.extend([t["avg"]] * t["count"])
    global_avg_reply = sum(all_times) / len(all_times) if all_times else None

    # 从 session_player_stats 实时算累计（比 players 表存储值更准确）
    computed_replies = sum(s["replies"] for s in session_player_stats)
    computed_words   = sum(s["words"]   for s in session_player_stats)

    return render_template("admin_player.html", player=player, player_sessions=player_sessions,
                           timing_stats=timing_stats, fmt_seconds=fmt_seconds, ts_to_str=ts_to_str,
                           hourly_rp=hourly_rp, max_hourly=max(hourly_rp) or 1,
                           session_player_stats=session_player_stats,
                           global_avg_reply=global_avg_reply,
                           computed_replies=computed_replies, computed_words=computed_words)


@app.route("/admin/stats")
@require_admin
def admin_stats():
    sid = get_show_id()
    db  = get_db()

    sessions = [_enrich_session(dict(s)) for s in
                db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts ASC", (sid,)).fetchall()]
    players  = [dict(p) for p in
                db.execute("SELECT * FROM players WHERE show_id=? AND role_name != '' ORDER BY total_replies DESC", (sid,)).fetchall()]
    player_map = {p["role_name"]: p for p in players}

    # 兜底：从 rp_entries 和 extra_events 收集所有出现过的角色名
    seen = list(player_map.keys())
    for r in db.execute("SELECT DISTINCT role_name FROM rp_entries WHERE show_id=? AND role_name != ''", (sid,)).fetchall():
        if r["role_name"] not in seen: seen.append(r["role_name"])
    for r in db.execute("SELECT DISTINCT from_role FROM extra_events WHERE show_id=? AND from_role != ''", (sid,)).fetchall():
        if r["from_role"] not in seen: seen.append(r["from_role"])
    role_names = seen

    # 从 sessions.stats 实时算每个角色的累计段数/字数/场次
    role_totals = defaultdict(lambda: {"total_replies": 0, "total_words": 0, "participated": 0})
    for s in sessions:
        stats = s.get("stats", {})
        parts = s.get("participants", [])
        for rn, st in stats.items():
            role_totals[rn]["total_replies"] += st.get("replies", 0)
            role_totals[rn]["total_words"]   += st.get("words",   0)
        for rn in parts:
            role_totals[rn]["participated"]  += 1

    # 如果 players 表里没有某个角色，补一个空记录供模板使用；并覆盖 total_replies/total_words
    for rn in role_names:
        if rn not in player_map:
            player_map[rn] = {"role_name": rn, "qq": "", "total_replies": 0, "total_words": 0}
        t = role_totals.get(rn, {})
        player_map[rn]["total_replies"] = t.get("total_replies", 0)
        player_map[rn]["total_words"]   = t.get("total_words",   0)
    players = [player_map[rn] for rn in role_names]

    # Per-player hourly activity (rp_entries + sms/gift，心动信不计入)
    hourly = defaultdict(lambda: [0] * 24)
    for e in db.execute("SELECT role_name, timestamp FROM rp_entries WHERE show_id=? AND timestamp > 0", (sid,)).fetchall():
        try:
            hourly[e["role_name"]][datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
        except Exception:
            pass
    for e in db.execute("SELECT from_role, timestamp FROM extra_events WHERE show_id=? AND type IN ('sms','gift') AND timestamp > 0", (sid,)).fetchall():
        try:
            hourly[e["from_role"]][datetime.fromtimestamp(int(e["timestamp"]) / 1000).hour] += 1
        except Exception:
            pass

    hourly_data = {role: hourly[role] for role in role_names}
    max_hourly  = max((max(v) for v in hourly_data.values() if v), default=1)

    return render_template("admin_stats.html",
                           sessions=sessions, players=players, role_names=role_names,
                           hourly_data=hourly_data, max_hourly=max_hourly,
                           ts_to_str=ts_to_str)



@app.route("/admin/blacklist", methods=["GET", "POST"])
@require_admin
def admin_blacklist():
    tid = current_tenant_id()
    db  = get_db()
    error = None
    success = None

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "delete":
            bid = request.form.get("id", "")
            if bid:
                db.execute("DELETE FROM blacklist WHERE id=? AND tenant_id=?", (bid, tid))
                db.commit()
                success = "已删除"
        else:
            qq        = request.form.get("qq", "").strip()
            role_name = request.form.get("role_name", "").strip()
            content   = request.form.get("content", "").strip()
            tags      = request.form.get("tags", "").strip()
            added_by  = request.form.get("added_by", "").strip()
            if not qq and not role_name:
                error = "QQ 号或角色名至少填写一项"
            else:
                db.execute(
                    "INSERT INTO blacklist (tenant_id,qq,role_name,content,tags,added_by,created_at) VALUES (?,?,?,?,?,?,?)",
                    (tid, qq, role_name, content, tags, added_by, int(time.time() * 1000))
                )
                db.commit()
                success = "已添加"

    records = [dict(r) for r in db.execute(
        "SELECT * FROM blacklist WHERE tenant_id=? ORDER BY created_at DESC", (tid,)
    ).fetchall()]

    return render_template("admin_blacklist.html", records=records, error=error, success=success, ts_to_str=ts_to_str)


# ── 写信综复盘 ───────────────────────────────────────────────────────────────

def _get_letters(db, show_id):
    """返回该档期所有 direct_letter 事件，按时间倒序。"""
    rows = db.execute("""
        SELECT id, from_role, to_role, content, extra_info, timestamp, game_day
        FROM extra_events
        WHERE show_id=? AND type='direct_letter'
        ORDER BY timestamp DESC
    """, (show_id,)).fetchall()
    result = []
    for r in rows:
        ei = {}
        try: ei = json.loads(r["extra_info"] or "{}")
        except Exception: pass
        result.append({
            "id":         r["id"],
            "from_role":  r["from_role"],
            "to_role":    r["to_role"],
            "content":    r["content"],
            "signature":  ei.get("signature", r["from_role"]),
            "date_tag":   ei.get("date_tag", ""),
            "attachment": ei.get("attachment", ""),
            "timestamp":  r["timestamp"],
            "game_day":   r["game_day"],
            "ts_str":     ts_to_str(r["timestamp"]),
        })
    return result

@app.route("/letters")
@require_login
def letters_view():
    db      = get_db()
    show_id = get_show_id()
    flat    = get_flat_config(db, show_id) if show_id else {}
    enabled = flat.get("global_feature_toggle__enable_direct_letter", "false") == "true"
    letters = _get_letters(db, show_id) if show_id else []
    locked  = not letters  # 没有记录就锁页
    # 筛选
    q_from = request.args.get("from", "").strip()
    q_to   = request.args.get("to",   "").strip()
    q_day  = request.args.get("day",  "").strip()
    if not locked:
        if q_from: letters = [l for l in letters if q_from in l["from_role"]]
        if q_to:   letters = [l for l in letters if q_to   in l["to_role"]]
        if q_day:  letters = [l for l in letters if l["game_day"] == q_day]
    all_days    = sorted({l["game_day"] for l in _get_letters(db, show_id)} if show_id else [], reverse=True)
    all_roles   = sorted({l["from_role"] for l in _get_letters(db, show_id)} if show_id else [])
    return render_template("letters.html",
                           letters=letters, locked=locked,
                           enabled=enabled,
                           q_from=q_from, q_to=q_to, q_day=q_day,
                           all_days=all_days, all_roles=all_roles)


# ── 角色 / 互动路由 ──────────────────────────────────────────────────────────

@app.route("/character/<role_name>")
@require_login
def character_view(role_name):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (sid,)).fetchall()
    show_names = get_show_names(db, sid)
    sessions_list = [s for s in _enrich_sessions(rows) if role_name in s["participants"]]
    return render_template("character.html", role_name=role_name, sessions=sessions_list, show_names=show_names)

@app.route("/interactions")
@require_login
def interactions_index():
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT role_name,
               SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END) AS lovemails,
               SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END) AS smss,
               SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END) AS gifts
        FROM (
            SELECT from_role AS role_name, type FROM extra_events WHERE show_id=?
            UNION ALL
            SELECT to_role   AS role_name, type FROM extra_events WHERE show_id=?
        )
        GROUP BY role_name
        ORDER BY (lovemails+smss+gifts) DESC
    """, (sid, sid)).fetchall()
    return render_template("interactions_index.html", roles=[dict(r) for r in rows])

@app.route("/character/<role_name>/interactions")
@require_login
def character_interactions(role_name):
    sid  = get_show_id()
    db   = get_db()
    rows = db.execute("""
        SELECT e.*, s.game_day AS s_game_day
        FROM extra_events e
        LEFT JOIN sessions s ON e.session_id=s.id
        WHERE e.show_id=? AND (e.from_role=? OR e.to_role=?)
        ORDER BY e.timestamp DESC
    """, (sid, role_name, role_name)).fetchall()
    show_names = get_show_names(db, sid)

    events = []
    for e in rows:
        e = dict(e)
        try: e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception: e["extra_info"] = {}
        e["time_str"] = ts_to_str(e["timestamp"])
        e["game_day"]  = e.get("game_day") or e.get("s_game_day") or ""
        events.append(e)

    lovemails = [e for e in events if e["type"] == "lovemail"]
    smss      = [e for e in events if e["type"] == "sms"]
    gifts     = [e for e in events if e["type"] == "gift"]

    pairs = {}
    for e in events:
        other  = e["to_role"] if e["from_role"] == role_name else e["from_role"]
        pairs.setdefault(other, {"lovemail_sent":0,"lovemail_recv":0,"sms_sent":0,"sms_recv":0,"gift_sent":0,"gift_recv":0})
        pairs[other][f"{e['type']}_{'sent' if e['from_role']==role_name else 'recv'}"] += 1
    pairs_list = sorted([(k,v,sum(v.values())) for k,v in pairs.items()], key=lambda x:-x[2])

    chaos_smss = [e for e in smss  if e.get("extra_info",{}).get("is_chaos")]
    lost_gifts = [e for e in gifts if e.get("extra_info",{}).get("isLost")]
    chaos_stats = {
        "sms_total": len(chaos_smss),
        "misdelivered":  sum(1 for e in chaos_smss if e["extra_info"].get("is_misdelivered")),
        "content_chaos": sum(1 for e in chaos_smss if e["extra_info"].get("is_content_chaos")),
        "sig_chaos":     sum(1 for e in chaos_smss if e["extra_info"].get("is_signature_chaos")),
        "lost_gifts": len(lost_gifts),
    }
    return render_template("character_interactions.html", role_name=role_name,
                           lovemails=lovemails, smss=smss, gifts=gifts,
                           pairs_list=pairs_list, chaos_stats=chaos_stats, show_names=show_names)

@app.route("/search")
@require_login
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("home"))
    sid = get_show_id()
    db  = get_db()
    q_lower = q.lower()

    # 收集所有 distinct role_name（来自 sessions 的 participants 字段）
    rows = db.execute("SELECT DISTINCT participants FROM sessions WHERE show_id=?", (sid,)).fetchall()
    all_roles = set()
    for r in rows:
        try:
            parts = json.loads(r["participants"] or "[]")
            all_roles.update(parts)
        except Exception:
            pass

    # 同时收集 players 表中的角色
    player_rows = db.execute("SELECT role_name FROM players WHERE show_id=?", (sid,)).fetchall()
    for r in player_rows:
        if r["role_name"]:
            all_roles.add(r["role_name"])

    # 收集 extra_events 中的发送/接收角色（只有短信记录但无场次的角色也能被搜到）
    event_rows = db.execute(
        "SELECT DISTINCT from_role, to_role FROM extra_events WHERE show_id=?", (sid,)
    ).fetchall()
    for r in event_rows:
        if r["from_role"]: all_roles.add(r["from_role"])
        if r["to_role"]:   all_roles.add(r["to_role"])

    show_names = get_show_names(db, sid)
    # show_name → role_name 反查表（小写）
    show_to_role = {v.lower(): k for k, v in show_names.items()}

    matched = set()
    for role in all_roles:
        if q_lower in role.lower():
            matched.add(role)
        sn = show_names.get(role, "")
        if sn and q_lower in sn.lower():
            matched.add(role)
    # 也从 show_name 反查中匹配
    for sn_lower, role in show_to_role.items():
        if q_lower in sn_lower and role in all_roles:
            matched.add(role)

    matched = sorted(matched)

    if len(matched) == 1:
        return redirect(url_for("character_view", role_name=matched[0]))
    if len(matched) == 0:
        # 无结果也给个页面而不是空角色页
        return render_template("search_results.html", q=q, results=[], show_names=show_names)
    return render_template("search_results.html", q=q, results=matched, show_names=show_names)


# ── 公开视图路由 ─────────────────────────────────────────────────────────────

def _get_public_show(token):
    row = get_db().execute(
        "SELECT * FROM shows WHERE public_token=? AND public_view_enabled=1", (token,)
    ).fetchone()
    return dict(row) if row else None

@app.route("/view/<token>")
def public_home(token):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    rows = db.execute("""
        SELECT game_day, COUNT(*) AS session_count,
               SUM(total_replies) AS total_replies, SUM(total_words) AS total_words,
               MIN(start_ts) AS first_ts
        FROM sessions WHERE show_id=?
        GROUP BY game_day ORDER BY first_ts DESC
    """, (show["id"],)).fetchall()
    # event counts per game_day
    ev_rows = db.execute("""
        SELECT game_day,
               SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END) AS sms_count,
               SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END) AS gift_count,
               SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END) AS lovemail_count
        FROM extra_events WHERE show_id=? AND type IN ('sms','gift','lovemail')
        GROUP BY game_day
    """, (show["id"],)).fetchall()
    ev_by_day = {r["game_day"]: dict(r) for r in ev_rows}
    days = []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        if d["game_day"].strip():
            ev = ev_by_day.get(d["game_day"], {})
            d["sms_count"]      = ev.get("sms_count", 0) or 0
            d["gift_count"]     = ev.get("gift_count", 0) or 0
            d["lovemail_count"] = ev.get("lovemail_count", 0) or 0
            days.append(d)
    return render_template("public_home.html", show=show, days=days, token=token)

@app.route("/view/<token>/date/<game_day>")
def public_date(token, game_day):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    flat = get_flat_config(db, show["id"])
    _true = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    allowed = [t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail)] if ok]
    rows = db.execute(
        "SELECT * FROM sessions WHERE show_id=? AND game_day=? ORDER BY start_ts DESC", (show["id"], game_day)
    ).fetchall()
    day_events = []
    if allowed:
        ph = ",".join("?" * len(allowed))
        ev_rows = db.execute(
            f"SELECT * FROM extra_events WHERE show_id=? AND game_day=? AND type IN ({ph}) ORDER BY timestamp ASC",
            [show["id"], game_day] + allowed
        ).fetchall()
        day_events = _parse_events(ev_rows)
    show_names = get_show_names(db, show["id"])
    return render_template("public_date.html", show=show, token=token,
                           day_events=day_events,
                           game_day=game_day, sessions=_enrich_sessions(rows), show_names=show_names)

@app.route("/view/<token>/session/<path:session_id>")
def public_session_view(token, session_id):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=? AND show_id=?", (session_id, show["id"])).fetchone()
    if not sess: abort(404)
    sess       = _enrich_session(dict(sess))
    rp         = db.execute("SELECT * FROM rp_entries WHERE session_id=? AND show_id=? ORDER BY seq,timestamp", (session_id, show["id"])).fetchall()
    flat       = get_flat_config(db, show["id"])
    _true      = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    allowed   = {t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail)] if ok}
    all_events = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, show["id"])).fetchall())
    events     = [e for e in all_events if e["type"] in allowed]
    show_names = get_show_names(db, show["id"])
    return render_template("public_session.html", show=show, token=token,
                           sess=sess, rp=rp, events=events, show_names=show_names, ts_to_str=ts_to_str)

@app.route("/view/<token>/events")
def public_events(token):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    flat = get_flat_config(db, show["id"])
    _true = ("true", "1", "True")
    show_sms      = flat.get("public_show_sms",      "true") in _true
    show_gift     = flat.get("public_show_gift",     "true") in _true
    show_lovemail = flat.get("public_show_lovemail", "true") in _true
    allowed = [t for t, ok in [("sms", show_sms), ("gift", show_gift), ("lovemail", show_lovemail)] if ok]
    if not allowed:
        events = []
    else:
        ph = ",".join("?" * len(allowed))
        rows = db.execute(
            f"SELECT * FROM extra_events WHERE show_id=? AND type IN ({ph}) ORDER BY timestamp DESC",
            [show["id"]] + allowed
        ).fetchall()
        events = _parse_events(rows)
    counts = {
        "sms":      sum(1 for e in events if e["type"] == "sms"),
        "gift":     sum(1 for e in events if e["type"] == "gift"),
        "lovemail": sum(1 for e in events if e["type"] == "lovemail"),
    }
    return render_template("public_events.html", show=show, token=token,
                           events=events, counts=counts, ts_to_str=ts_to_str,
                           show_sms=show_sms, show_gift=show_gift, show_lovemail=show_lovemail)


@app.route("/view/<token>/character/<role_name>")
def public_character(token, role_name):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    rows = db.execute("SELECT * FROM sessions WHERE show_id=? ORDER BY start_ts DESC", (show["id"],)).fetchall()
    show_names = get_show_names(db, show["id"])
    sessions_list = [s for s in _enrich_sessions(rows) if role_name in s["participants"]]
    return render_template("public_character.html", show=show, token=token,
                           role_name=role_name, sessions=sessions_list, show_names=show_names)


# ── API 路由 ─────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def api_config():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    flat = get_flat_config(get_db(), show_id)
    return jsonify(assemble_bot_config(flat))

@app.route("/api/sync_config", methods=["POST"])
def api_sync_config():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data = request.json or {}
    if not data:
        return jsonify({"ok": False, "error": "empty payload"}), 400
    db = get_db()
    for key, value in data.items():
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (show_id, tid, key, str(value))
        )
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, "_last_bot_sync", str(int(time.time() * 1000)))
    )
    db.commit()
    return jsonify({"ok": True, "synced": len(data)})

@app.route("/api/pending_items", methods=["GET"])
def api_pending_items():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db  = get_db()
    row = db.execute(
        "SELECT value FROM site_config WHERE show_id=? AND key='item_registry_pending'",
        (show_id,)
    ).fetchone()
    pending = []
    if row and row["value"]:
        try:
            pending = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            pending = []
    return jsonify({"pending": pending})

@app.route("/api/event", methods=["POST"])
def api_event():
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data       = request.json or {}
    event_type = data.get("type", "")
    if event_type not in ("lovemail", "sms", "gift", "direct_letter"):
        return jsonify({"ok": False, "error": "invalid type"}), 400

    # 档期门控：仅主档期内的互动事件才写入
    zone = _schedule_zone(show, data.get("timestamp"))
    if zone != 'main':
        return jsonify({"ok": True, "skipped": zone})
    db        = get_db()
    from_role = data.get("from_role","").strip()
    from_qq   = str(data.get("from_qq","")).strip()
    to_role   = data.get("to_role","").strip()
    to_qq     = str(data.get("to_qq","")).strip()
    now       = int(time.time() * 1000)
    extra_info = data.get("extra_info",{})
    # 自定义名字：归属到真实角色，但在 extra_info 中保留显示用名
    from_custom = data.get("from_custom_name","").strip()
    to_custom   = data.get("to_custom_name","").strip()
    if from_custom and from_custom != from_role:
        extra_info["from_custom_name"] = from_custom
    if to_custom and to_custom != to_role:
        extra_info["to_custom_name"] = to_custom
    db.execute("""
        INSERT INTO extra_events
          (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (show_id, tid, data.get("session_id") or "", event_type,
          from_role, to_role, data.get("content",""),
          json.dumps(extra_info, ensure_ascii=False),
          data.get("timestamp",0), data.get("game_day","")))

    def _upsert_event_player(role, qq):
        if not role:
            return
        effective_qq = qq if qq and qq != role else role  # 有真实QQ用真实QQ，否则placeholder
        existing = db.execute(
            "SELECT qq FROM players WHERE show_id=? AND role_name=?", (show_id, role)
        ).fetchone()
        if existing:
            # 如果现有记录是placeholder且现在有真实QQ，升级
            if existing["qq"] == role and effective_qq != role:
                db.execute(
                    "UPDATE players SET qq=?, last_updated=? WHERE show_id=? AND role_name=?",
                    (effective_qq, now, show_id, role)
                )
            else:
                db.execute("UPDATE players SET last_updated=? WHERE show_id=? AND role_name=?",
                           (now, show_id, role))
        else:
            db.execute("""
                INSERT OR IGNORE INTO players
                  (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated)
                VALUES (?,?,?,?,0,0,0,?)
            """, (show_id, tid, effective_qq, role, now))

    # 短信/礼物/写信综：发送方和收件方都注册；心动信不计入活跃
    if event_type in ("sms", "gift", "direct_letter"):
        _upsert_event_player(from_role, from_qq)
        _upsert_event_player(to_role, to_qq)
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/rp", methods=["POST"])
def api_rp():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data = request.json or {}
    sid  = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400
    db = get_db()
    if not db.execute("SELECT id FROM sessions WHERE id=? AND show_id=?", (sid, show_id)).fetchone():
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
               participants,start_ts,end_ts,forced,total_replies,total_words,stats)
            VALUES (?,?,?,?,?,?,?,?,?,'[]',?,0,0,0,0,'{}')
        """, (sid, show_id, tid,
              data.get("group_id",""),
              data.get("platform",""),
              data.get("game_day","") or "",
              data.get("game_time",""),
              data.get("place",""),
              data.get("subtype",""),
              data.get("timestamp",0)))
    max_seq = db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM rp_entries WHERE session_id=? AND show_id=?", (sid, show_id)
    ).fetchone()[0]
    # 计算 reply_time_ms：距同 session 内上一条不同角色的 entry
    cur_ts    = data.get("timestamp", 0)
    role_name_rp = data.get("role_name", "")
    reply_time_ms = None
    if cur_ts and role_name_rp:
        prev_other = db.execute(
            "SELECT timestamp FROM rp_entries WHERE session_id=? AND show_id=? AND role_name!=? AND timestamp>0 ORDER BY seq DESC LIMIT 1",
            (sid, show_id, role_name_rp)
        ).fetchone()
        if prev_other:
            diff = cur_ts - prev_other["timestamp"]
            if 0 < diff < 7_200_000:
                reply_time_ms = diff
    db.execute("""
        INSERT INTO rp_entries (show_id,tenant_id,session_id,role_name,content,seq,timestamp,reply_time_ms)
        VALUES (?,?,?,?,?,?,?,?)
    """, (show_id, tid, sid, role_name_rp, data.get("content",""),
          max_seq+1, cur_ts, reply_time_ms))
    db.execute(
        "UPDATE sessions SET total_replies=total_replies+1, total_words=total_words+? WHERE id=? AND show_id=?",
        (len(data.get("content","")), sid, show_id)
    )

    # 计算本次回复时间（距上一条不同角色的 entry）并累计到 players
    role_name = data.get("role_name", "")
    cur_ts    = data.get("timestamp", 0)
    is_npc    = bool(data.get("is_npc", False))
    # 若 is_npc，标记 players 表
    if role_name and is_npc:
        db.execute(
            "UPDATE players SET is_npc=1 WHERE show_id=? AND role_name=?",
            (show_id, role_name)
        )
    if role_name and cur_ts and not is_npc:
        prev = db.execute(
            "SELECT timestamp FROM rp_entries WHERE session_id=? AND show_id=? AND role_name!=? AND timestamp>0 ORDER BY seq DESC LIMIT 1",
            (sid, show_id, role_name)
        ).fetchone()
        if prev:
            diff_ms = cur_ts - prev["timestamp"]
            if 0 < diff_ms < 7_200_000:  # 0~2小时内视为有效
                db.execute("""
                    UPDATE players
                    SET reply_time_sum=reply_time_sum+?, reply_time_count=reply_time_count+1
                    WHERE show_id=? AND role_name=?
                """, (diff_ms, show_id, role_name))

    db.commit()
    return jsonify({"ok": True})

def _compute_player_totals(db, show_id, role_name):
    """从 sessions.stats 重算指定角色的累计回复数、字数、场次数。"""
    all_sessions = db.execute(
        "SELECT stats, participants FROM sessions WHERE show_id=?", (show_id,)
    ).fetchall()
    total_replies = 0
    total_words   = 0
    sessions_count = 0
    for s in all_sessions:
        try:
            stats = json.loads(s["stats"] or "{}")
            parts = json.loads(s["participants"] or "[]")
        except Exception:
            continue
        if role_name in stats:
            total_replies  += stats[role_name].get("replies", 0)
            total_words    += stats[role_name].get("words",   0)
        if role_name in parts:
            sessions_count += 1
    return total_replies, total_words, sessions_count


def _upsert_players_from_list(db, show_id, tid, players_list):
    """从 [{qq, role_name, is_npc?}] 批量 upsert 玩家表，并从 sessions.stats 重算累计数据。
    若该角色名已有占位行（qq=role_name），将其升级为真实 QQ。
    NPC 玩家：只更新 is_npc 标记，不计弧长统计。"""
    now = int(time.time() * 1000)
    for p in players_list:
        qq        = str(p.get("qq","")).strip()
        role_name = str(p.get("role_name","")).strip()
        is_npc    = bool(p.get("is_npc", False))
        if not qq or not role_name: continue

        if is_npc:
            # NPC：只确保行存在并标记 is_npc=1，不更新弧长数据
            db.execute("""
                INSERT INTO players (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated,is_npc)
                VALUES (?,?,?,?,0,0,0,?,1)
                ON CONFLICT(show_id,qq) DO UPDATE SET
                    role_name=excluded.role_name,
                    is_npc=1
            """, (show_id, tid, qq, role_name, now))
            continue

        total_replies, total_words, sessions_count = _compute_player_totals(db, show_id, role_name)

        # 如果存在以 role_name 为占位 QQ 的行，直接把 QQ 更新为真实值
        placeholder = db.execute(
            "SELECT 1 FROM players WHERE show_id=? AND qq=? AND role_name=?",
            (show_id, role_name, role_name)
        ).fetchone()
        if placeholder and qq != role_name:
            db.execute("""
                UPDATE players SET qq=?, sessions_count=?, total_replies=?, total_words=?, last_updated=?
                WHERE show_id=? AND qq=? AND role_name=?
            """, (qq, sessions_count, total_replies, total_words, now, show_id, role_name, role_name))
        else:
            db.execute("""
                INSERT INTO players (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(show_id,qq) DO UPDATE SET
                    role_name=excluded.role_name,
                    sessions_count=excluded.sessions_count,
                    total_replies=excluded.total_replies,
                    total_words=excluded.total_words,
                    last_updated=excluded.last_updated
            """, (show_id, tid, qq, role_name, sessions_count, total_replies, total_words, now))


@app.route("/api/session_stats", methods=["POST"])
def api_session_stats():
    """实时更新正在进行中的场次 stats（每次有效 RP 回复后 bot 主动推送）。"""
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data  = request.json or {}
    sid   = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    zone = _schedule_zone(show)
    if zone == 'pre':
        return jsonify({"ok": True, "skipped": "pre_schedule"})

    stats = data.get("stats", {})
    db    = get_db()
    total_replies = sum(v.get("replies",0) for v in stats.values())
    total_words   = sum(v.get("words",0)   for v in stats.values())
    stats_json    = json.dumps(stats, ensure_ascii=False)
    existing = db.execute("SELECT id FROM sessions WHERE id=? AND show_id=?", (sid, show_id)).fetchone()
    if existing:
        db.execute("""
            UPDATE sessions SET total_replies=?, total_words=?, stats=?
            WHERE id=? AND show_id=?
        """, (total_replies, total_words, stats_json, sid, show_id))
    else:
        # 场次还未正式建立（session_end 尚未到来），先建占位行
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
               participants,start_ts,end_ts,forced,total_replies,total_words,stats)
            VALUES (?,?,?,?,?,?,?,?,?,'[]',?,0,0,?,?,?)
        """, (sid, show_id, tid,
              data.get("group_id",""),
              data.get("platform",""),
              data.get("game_day","") or "",
              data.get("game_time",""),
              data.get("place",""),
              data.get("subtype",""),
              int(time.time()*1000),
              total_replies, total_words, stats_json))
    # 补戏期只保存场次 stats，不更新玩家弧长
    if zone != 'supplement':
        _upsert_players_from_list(db, show_id, tid, data.get("players", []))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/session_end", methods=["POST"])
def api_session_end():
    tid  = get_tenant_from_token()
    show = get_current_show_for_tenant(tid)
    if not show: abort(503)
    show_id = show["id"]
    data = request.json or {}
    sid  = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    # 档期门控
    zone = _schedule_zone(show)
    if zone == 'pre':
        return jsonify({"ok": True, "skipped": "pre_schedule"})

    stats = data.get("stats",{})
    parts = data.get("participants",[])
    db    = get_db()

    # supplement 期间标记场次为"补戏"，方便界面区分
    subtype_val = data.get("subtype","")
    if zone == 'supplement':
        subtype_val = (subtype_val + "|补戏").lstrip("|")

    db.execute("""
        INSERT OR REPLACE INTO sessions
          (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
           participants,start_ts,end_ts,forced,total_replies,total_words,stats)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (sid, show_id, tid,
          data.get("group_id",""), data.get("platform",""),
          data.get("game_day",""), data.get("game_time",""),
          data.get("place",""),    subtype_val,
          json.dumps(parts, ensure_ascii=False),
          data.get("start_ts",0), data.get("end_ts",0),
          1 if data.get("forced") else 0,
          sum(v.get("replies",0) for v in stats.values()),
          sum(v.get("words",0)   for v in stats.values()),
          json.dumps(stats, ensure_ascii=False)))
    # 自动同步玩家数据（无需手动执行「更新玩家数据库」）
    # 补戏期：只保存场次记录，不计弧长
    if zone != 'supplement':
        _upsert_players_from_list(db, show_id, tid, data.get("players", []))
    db.commit()
    return jsonify({"ok": True, "zone": zone})

@app.route("/api/update_players", methods=["POST"])
def api_update_players():
    tid       = get_tenant_from_token()
    show_id   = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data      = request.json or {}
    show_name = data.get("show_name","")
    players   = data.get("players",[])
    if not isinstance(players, list):
        return jsonify({"ok": False, "error": "players must be a list"}), 400
    now = int(time.time() * 1000)
    db  = get_db()
    count = 0
    for p in players:
        qq        = str(p.get("qq","")).strip()
        role_name = str(p.get("role_name","")).strip()
        if not qq or not role_name: continue
        db.execute("""
            INSERT INTO players (show_id,tenant_id,qq,role_name,show_name,sessions_count,total_replies,total_words,last_updated)
            VALUES (?,?,?,?,?,0,0,0,?)
            ON CONFLICT(show_id,qq) DO UPDATE SET
                role_name=excluded.role_name, show_name=excluded.show_name, last_updated=excluded.last_updated
        """, (show_id, tid, qq, role_name, show_name, now))
        count += 1
    db.commit()
    return jsonify({"ok": True, "count": count})


# ── 已知群管理 ───────────────────────────────────────────────────────────────

@app.route("/admin/groups", methods=["GET", "POST"])
@require_admin
def admin_groups():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    msg = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            gid      = request.form.get("group_id","").strip()
            set_name = request.form.get("set_name","").strip()
            note     = request.form.get("name","").strip()
            if gid and set_name:
                existing = db.execute(
                    "SELECT id FROM known_groups WHERE show_id=? AND group_id=? AND set_name=?",
                    (sid, gid, set_name)
                ).fetchone()
                if not existing:
                    db.execute(
                        "INSERT INTO known_groups(show_id,tenant_id,group_id,set_name,name,created_at) VALUES(?,?,?,?,?,?)",
                        (sid, tid, gid, set_name, note, int(time.time()*1000))
                    )
                    db.commit()
                msg = "added"
        elif action == "bulk_add":
            set_name = request.form.get("set_name","").strip()
            raw      = request.form.get("group_ids","")
            if set_name and raw:
                import re
                gids = [g.strip() for g in re.split(r"[\s,，;；]+", raw) if g.strip().isdigit()]
                now  = int(time.time()*1000)
                added = 0
                for gid in gids:
                    existing = db.execute(
                        "SELECT id FROM known_groups WHERE show_id=? AND group_id=? AND set_name=?",
                        (sid, gid, set_name)
                    ).fetchone()
                    if not existing:
                        db.execute(
                            "INSERT INTO known_groups(show_id,tenant_id,group_id,set_name,name,created_at) VALUES(?,?,?,?,?,?)",
                            (sid, tid, gid, set_name, "", now)
                        )
                        added += 1
                if added:
                    db.commit()
                msg = f"bulk_added_{added}"
        elif action == "add_set":
            set_name = request.form.get("set_name","").strip()
            if set_name:
                try:
                    db.execute(
                        "INSERT OR IGNORE INTO known_group_sets(show_id,tenant_id,set_name,created_at) VALUES(?,?,?,?)",
                        (sid, tid, set_name, int(time.time()*1000))
                    )
                    db.commit()
                    msg = "set_created"
                except Exception:
                    msg = None
        elif action == "delete":
            row_id = request.form.get("row_id", type=int)
            if row_id:
                db.execute("DELETE FROM known_groups WHERE id=? AND show_id=?", (row_id, sid))
                db.commit()
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": True})
            msg = "deleted"
        elif action == "delete_set":
            set_name = request.form.get("set_name","").strip()
            if set_name:
                db.execute("DELETE FROM known_groups WHERE show_id=? AND set_name=?", (sid, set_name))
                db.execute("DELETE FROM known_group_sets WHERE show_id=? AND set_name=?", (sid, set_name))
                db.commit()
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": True})
            msg = "set_deleted"
        elif action == "edit":
            row_id = request.form.get("row_id", type=int)
            note   = request.form.get("name","").strip()
            if row_id:
                db.execute("UPDATE known_groups SET name=? WHERE id=? AND show_id=?", (note, row_id, sid))
                db.commit()
            msg = "edited"
    # 所有已创建的组名（含空组）
    set_name_rows = db.execute(
        "SELECT set_name FROM known_group_sets WHERE show_id=? ORDER BY created_at",
        (sid,)
    ).fetchall()
    member_rows = db.execute(
        "SELECT * FROM known_groups WHERE show_id=? ORDER BY set_name, created_at",
        (sid,)
    ).fetchall()
    from collections import OrderedDict
    sets = OrderedDict()
    for r in set_name_rows:
        sets.setdefault(r["set_name"], [])
    for r in member_rows:
        sn = r["set_name"] or "（未分组）"
        sets.setdefault(sn, []).append(dict(r))
    return render_template("admin_groups.html", sets=sets, msg=msg)


# ── 结戏奖励 Dashboard ────────────────────────────────────────────────────────

def _get_reward_config(db, show_id):
    rows = db.execute(
        "SELECT key,value FROM site_config WHERE show_id=? AND key IN (?,?,?,?)",
        (show_id, "reward_bonus_templates", "reward_draw_config",
         "reward_item_registry", "item_registry")
    ).fetchall()
    cfg = {r["key"]: r["value"] for r in rows}
    try:
        bonus_templates = json.loads(cfg.get("reward_bonus_templates") or "[]")
    except Exception:
        bonus_templates = []
    try:
        draw_config = json.loads(cfg.get("reward_draw_config") or "{}")
    except Exception:
        draw_config = {}
    # 优先读主注册表 item_registry，回退到 reward_item_registry（旧数据兼容）
    try:
        item_registry = json.loads(cfg.get("item_registry") or "{}")
    except Exception:
        item_registry = {}
    if not item_registry:
        try:
            item_registry = json.loads(cfg.get("reward_item_registry") or "{}")
        except Exception:
            item_registry = {}
    return bonus_templates, draw_config, item_registry


def _save_reward_config_key(db, show_id, tid, key, value_str):
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, key, value_str)
    )


@app.route("/admin/rewards", methods=["GET"])
@require_admin
def admin_rewards():
    sid = get_show_id()
    db  = get_db()
    bonus_templates, draw_config, item_registry = _get_reward_config(db, sid)
    page    = max(1, request.args.get("page", 1, type=int))
    per_page = 30
    total   = db.execute("SELECT COUNT(*) FROM reward_records WHERE show_id=?", (sid,)).fetchone()[0]
    records = db.execute(
        "SELECT * FROM reward_records WHERE show_id=? ORDER BY distributed_at DESC LIMIT ? OFFSET ?",
        (sid, per_page, (page-1)*per_page)
    ).fetchall()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template("admin_rewards.html",
                           bonus_templates=bonus_templates,
                           draw_config=draw_config,
                           item_registry=item_registry,
                           records=[dict(r) for r in records],
                           total=total, page=page, total_pages=total_pages,
                           ts_to_str=ts_to_str)


@app.route("/admin/rewards/config", methods=["POST"])
@require_admin
def admin_rewards_save_config():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    section = request.form.get("section","")
    if section == "draw":
        enabled = request.form.get("draw_enabled") == "1"
        chance  = max(0, min(100, request.form.get("draw_chance", 0, type=int)))
        count   = max(1, request.form.get("draw_count", 1, type=int))
        val = json.dumps({"enabled": enabled, "chance": chance, "count": count})
        _save_reward_config_key(db, sid, tid, "reward_draw_config", val)
        db.commit()
    elif section == "items":
        raw = request.form.get("item_registry_json","").strip()
        try:
            parsed = json.loads(raw)
            val = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": False, "error": "json_parse"})
            return redirect(url_for("admin_rewards") + "?err=json")
        # 同时写主注册表（机器人拉取）和兼容 key
        _save_reward_config_key(db, sid, tid, "item_registry", val)
        _save_reward_config_key(db, sid, tid, "reward_item_registry", val)
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
    elif section == "bonus":
        raw = request.form.get("bonus_templates_json","").strip()
        try:
            parsed = json.loads(raw)
            val = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            if request.headers.get("X-Fetch") == "1":
                return jsonify({"ok": False, "error": "json_parse"})
            return redirect(url_for("admin_rewards") + "?err=json")
        _save_reward_config_key(db, sid, tid, "reward_bonus_templates", val)
        db.commit()
        if request.headers.get("X-Fetch") == "1":
            return jsonify({"ok": True})
    return redirect(url_for("admin_rewards") + "?saved=1")


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_show_names(db, show_id):
    rows = db.execute(
        "SELECT role_name, show_name FROM players WHERE show_id=? AND show_name IS NOT NULL AND show_name!=''",
        (show_id,)
    ).fetchall()
    return {r["role_name"]: r["show_name"] for r in rows}

def _parse_events(rows):
    result = []
    for e in rows:
        e = dict(e)
        try: e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception: e["extra_info"] = {}
        result.append(e)
    return result

def _enrich_session(s):
    try: s["participants"] = json.loads(s.get("participants") or "[]")
    except Exception: s["participants"] = []
    try: s["stats"] = json.loads(s.get("stats") or "{}")
    except Exception: s["stats"] = {}
    s["start_str"] = ts_to_str(s.get("start_ts"))
    s["end_str"]   = ts_to_str(s.get("end_ts"))
    start, end = s.get("start_ts",0), s.get("end_ts",0)
    if start and end and end > start:
        mins = (end - start) // 60000
        s["duration_str"] = f"{mins//60}小时{mins%60}分" if mins >= 60 else f"{mins}分钟"
    else:
        s["duration_str"] = ""
    return s

def _enrich_sessions(rows):
    return [_enrich_session(dict(r)) for r in rows]


@app.route("/api/groups", methods=["GET"])
def api_groups():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db = get_db()
    rows = db.execute(
        "SELECT group_id, name, description FROM known_groups WHERE show_id=? ORDER BY created_at",
        (show_id,)
    ).fetchall()
    return jsonify({"ok": True, "groups": [dict(r) for r in rows]})


@app.route("/api/group_set/<set_name>", methods=["GET"])
def api_group_set(set_name):
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db   = get_db()
    rows = db.execute(
        "SELECT group_id FROM known_groups WHERE show_id=? AND set_name=? ORDER BY created_at",
        (show_id, set_name)
    ).fetchall()
    return jsonify({"ok": True, "set_name": set_name, "group_ids": [r["group_id"] for r in rows]})


@app.route("/api/reward_result", methods=["POST"])
def api_reward_result():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data    = request.json or {}
    results = data.get("results", [])
    if not isinstance(results, list):
        return jsonify({"ok": False, "error": "results must be a list"}), 400
    db  = get_db()
    now = int(time.time() * 1000)
    for r in results:
        db.execute(
            "INSERT INTO reward_records(show_id,tenant_id,session_id,game_day,player_qq,role_name,reward_data,distributed_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (show_id, tid,
             str(r.get("session_id","")), str(r.get("game_day","")),
             str(r.get("player_qq","")), str(r.get("role_name","")),
             json.dumps(r.get("reward_data",{}), ensure_ascii=False),
             r.get("distributed_at", now))
        )
    db.commit()
    return jsonify({"ok": True, "count": len(results)})


@app.route("/api/reward_config", methods=["GET"])
def api_reward_config():
    """机器人拉取结戏奖励配置（道具注册表 + 奖励模版 + 抽奖配置）。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    db = get_db()
    bonus_templates, draw_config, item_registry = _get_reward_config(db, show_id)
    return jsonify({
        "ok": True,
        "item_registry":     item_registry,
        "bonus_templates":   bonus_templates,
        "draw_config":       draw_config,
    })


# ── 抽取池管理 ──────────────────────────────────────────────────────────────

def _get_pool_data(db, show_id):
    flat = get_flat_config(db, show_id)
    pool_defs = json.loads(flat.get("pool_definitions", "{}") or "{}")
    pool_cfg  = json.loads(flat.get("pool_draw_config", '{"total":null,"pools":{}}') or '{"total":null,"pools":{}}')
    item_registry = json.loads(flat.get("item_registry", "{}") or "{}")
    if not item_registry:
        item_registry = json.loads(flat.get("reward_item_registry", "{}") or "{}")
    return pool_defs, pool_cfg, item_registry


@app.route("/admin/pools", methods=["GET"])
@require_admin
def admin_pools():
    sid = get_show_id()
    db  = get_db()
    pool_defs, pool_cfg, item_registry = _get_pool_data(db, sid)
    flat = get_flat_config(db, sid)
    attr_defs = json.loads(flat.get("rpg_attr_defs", "{}") or "{}")
    return render_template("admin_pools.html",
                           pool_defs=pool_defs,
                           pool_cfg=pool_cfg,
                           item_registry=item_registry,
                           attr_defs=attr_defs)


@app.route("/admin/pools/save", methods=["POST"])
@require_admin
def admin_pools_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    pool_defs = data.get("pool_definitions", {})
    pool_cfg  = data.get("pool_draw_config", {"total": None, "pools": {}})
    for key, val in (("pool_definitions", pool_defs), ("pool_draw_config", pool_cfg)):
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (sid, tid, key, json.dumps(val, ensure_ascii=False))
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/pool_config", methods=["GET"])
def api_pool_config():
    """机器人拉取抽取池配置。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    pool_defs, pool_cfg, _ = _get_pool_data(db, show_id)
    return jsonify({"ok": True, "pool_definitions": pool_defs, "pool_draw_config": pool_cfg})


@app.route("/api/pool_config", methods=["POST"])
def api_pool_config_push():
    """机器人推送本地池子配置到存档服务器（覆盖）。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    db = get_db()
    updates = []
    if "pool_definitions" in data:
        updates.append(("pool_definitions", data["pool_definitions"]))
    if "pool_draw_config" in data:
        updates.append(("pool_draw_config", data["pool_draw_config"]))
    if not updates:
        return jsonify({"ok": False, "error": "missing pool_definitions or pool_draw_config"}), 400
    for key, val in updates:
        db.execute(
            "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
            "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
            (show_id, tid, key, json.dumps(val, ensure_ascii=False))
        )
    db.commit()
    pool_count = len(data.get("pool_definitions", {}))
    return jsonify({"ok": True, "pools": pool_count})


@app.route("/admin/auctions", methods=["GET"])
@require_admin
def admin_auctions():
    sid = get_show_id()
    db  = get_db()
    flat = get_flat_config(db, sid)
    queue    = json.loads(flat.get("auction_queue",    "[]") or "[]")
    snapshot = json.loads(flat.get("auction_snapshot", "{}") or "{}")
    item_registry = json.loads(flat.get("item_registry", "{}") or "{}")
    if not item_registry:
        item_registry = json.loads(flat.get("reward_item_registry", "{}") or "{}")
    return render_template("admin_auctions.html",
                           queue=queue, snapshot=snapshot,
                           item_registry=item_registry)


@app.route("/admin/auctions/save", methods=["POST"])
@require_admin
def admin_auctions_save():
    sid = get_show_id()
    tid = current_tenant_id()
    db  = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    queue = data.get("queue", [])
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (sid, tid, "auction_queue", json.dumps(queue, ensure_ascii=False))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/auction_queue", methods=["GET"])
def api_auction_queue_get():
    """机器人拉取拍卖队列。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    flat  = get_flat_config(db, show_id)
    queue = json.loads(flat.get("auction_queue", "[]") or "[]")
    return jsonify({"ok": True, "queue": queue})


@app.route("/api/auction_queue", methods=["DELETE"])
def api_auction_queue_clear():
    """机器人拉取完毕后清空队列。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    db = get_db()
    tid_w = tid
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid_w, "auction_queue", "[]")
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/auction_snapshot", methods=["POST"])
def api_auction_snapshot():
    """机器人推送拍卖快照到存档服务器。"""
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id:
        abort(503)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "no data"}), 400
    snapshot = data.get("snapshot", {})
    db = get_db()
    db.execute(
        "INSERT INTO site_config(show_id,tenant_id,key,value) VALUES(?,?,?,?) "
        "ON CONFLICT(show_id,key) DO UPDATE SET value=excluded.value",
        (show_id, tid, "auction_snapshot", json.dumps(snapshot, ensure_ascii=False))
    )
    db.commit()
    return jsonify({"ok": True, "count": len(snapshot)})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
