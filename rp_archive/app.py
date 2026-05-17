import io, os, json, functools, secrets, time, hmac, logging, traceback
from collections import defaultdict
from datetime import datetime
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
        {"key": "love_show_name",             "label": "恋综名",              "type": "text",   "default": ""},
        {"key": "global_days",                "label": "当前游戏日",           "type": "text",   "default": "D1",   "note": "如 D1 / D2 / D3"},
        {"key": "auto_day_reset_enabled",     "label": "自动天数推进",         "type": "bool",   "default": "false"},
        {"key": "relationship_system_enabled","label": "关系系统",             "type": "bool",   "default": "true"},
        {"key": "max_relationships_per_user", "label": "每人最大关系数",       "type": "number", "default": "5"},
        {"key": "lovemail_default_limit",     "label": "心动信每日上限",       "type": "number", "default": "3"},
        {"key": "item_pool_mode",             "label": "道具池模式",           "type": "select", "default": "自由池", "options": ["自由池", "抽取池"]},
    ]},
    {"section": "群组 ID", "fields": [
        {"key": "adminAnnounceGroupId",  "label": "公告群",     "type": "text",    "default": "", "note": "群号，留空不广播"},
        {"key": "song_group_id",         "label": "戏群",       "type": "text",    "default": ""},
        {"key": "background_group_id",   "label": "后台群",     "type": "text",    "default": ""},
        {"key": "water_group_id",        "label": "水群",       "type": "text",    "default": ""},
        {"key": "auction_display_group", "label": "拍卖展示群", "type": "text",    "default": ""},
        {"key": "fupan_routing_enabled", "label": "复盘群分流", "type": "bool",    "default": "false", "note": "启用后复盘消息按天数路由到对应群"},
        {"key": "fupan_routing_groups",  "label": "分流群配置", "type": "routing", "default": "", "note": "格式：D1:群号 D2:群号"},
    ]},
    {"section": "功能开关", "json_parent": "global_feature_toggle", "fields": [
        {"key": "enable_general_letter",      "label": "普通信件",        "type": "bool", "default": "true"},
        {"key": "enable_general_gift",        "label": "普通礼物",        "type": "bool", "default": "true"},
        {"key": "enable_general_appointment", "label": "普通邀约",        "type": "bool", "default": "true"},
        {"key": "enable_chaos_letter",        "label": "短信",            "type": "bool", "default": "true"},
        {"key": "enable_wish_system",         "label": "心愿系统",        "type": "bool", "default": "true"},
        {"key": "enable_lovemail",            "label": "心动信",          "type": "bool", "default": "true"},
        {"key": "enable_wechat",              "label": "微信",            "type": "bool", "default": "true"},
        {"key": "enable_direct_letter",       "label": "发送信件（写信综）","type": "bool", "default": "false"},
    ]},
    {"section": "公告", "fields": [
        {"key": "letter_public_send",  "label": "寄信公开发送",     "type": "bool",   "default": "false"},
        {"key": "gift_public_send",    "label": "送礼公开发送",     "type": "bool",   "default": "false"},
        {"key": "wish_public_send",    "label": "心愿公开提醒",     "type": "bool",   "default": "false"},
        {"key": "giftPublicChance",    "label": "礼物公开概率（%）", "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "giftDailyLimit",      "label": "每日礼物上限",     "type": "number", "default": "100"},
        {"key": "announceFrequency",   "label": "公告触发频率",     "type": "number", "default": "5"},
    ]},
    {"section": "礼物与互动", "fields": [
        {"key": "allow_private_rooms",      "label": "允许私人房间",       "type": "bool",   "default": "true"},
        {"key": "mailCooldown",             "label": "寄信冷却（分钟）",   "type": "number", "default": "60"},
        {"key": "giftCooldown",             "label": "送礼冷却（分钟）",   "type": "number", "default": "30"},
        {"key": "allow_custom_letter_sign", "label": "寄信自定义名字",    "type": "bool",   "default": "false"},
        {"key": "shop_refresh_hours",       "label": "礼品店刷新（小时）", "type": "number", "default": "24"},
    ]},
    {"section": "邀约", "fields": [
        {"key": "enable_join_existing_appointment", "label": "允许加入已有私约", "type": "bool",   "default": "true"},
        {"key": "require_fupan_before_end",         "label": "复盘强制结束",     "type": "bool",   "default": "true"},
        {"key": "group_expire_hours",               "label": "小群过期（小时）", "type": "number", "default": "48"},
    ]},
    {"section": "邀约时长（分钟）", "json_parent": "appointment_duration_config", "fields": [
        {"key": "phone",   "label": "电话门槛", "type": "number", "default": "29"},
        {"key": "private", "label": "私密门槛", "type": "number", "default": "59"},
    ]},
    {"section": "混沌配置（% · 0=关闭）", "json_parent": "chaos_letter_config", "fields": [
        {"key": "misdelivery",       "label": "误送",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "blackoutText",      "label": "黑化文字",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "loseContent",       "label": "内容丢失",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "antonymReplace",    "label": "词语替换",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "reverseOrder",      "label": "逆序",          "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "mistakenSignature", "label": "署名错乱",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "poeticSignature",   "label": "诗意署名",      "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "dailyLimit",        "label": "每日混沌上限",  "type": "number", "default": "5"},
        {"key": "publicChance",      "label": "播报概率（%）", "type": "number", "default": "50", "min": 0, "max": 100},
        {"key": "giftLost",          "label": "礼物丢失（%）", "type": "number", "default": "0",  "min": 0, "max": 100},
        {"key": "giftMisdelivery",   "label": "礼物误送（%）", "type": "number", "default": "0",  "min": 0, "max": 100},
    ]},
    {"section": "心动信", "fields": [
        {"key": "lovemail_delivery_time",  "label": "送达时间",       "type": "text",   "default": "22:00"},
        {"key": "lovemail_expose",         "label": "曝光",           "type": "bool",   "default": "false"},
        {"key": "lovemail_expose_chance",  "label": "曝光概率（%）",  "type": "number", "default": "10", "min": 0, "max": 100},
    ]},
    {"section": "发送信件", "fields": [
        {"key": "direct_letter_daily_limit", "label": "每日上限",   "type": "number", "default": "5"},
        {"key": "direct_letter_min_chars",   "label": "最低字数",   "type": "number", "default": "0"},
        {"key": "direct_letter_reward",      "label": "写信币赏金", "type": "number", "default": "0"},
    ]},
    {"section": "心愿系统", "fields": [
        {"key": "wish_bounty_enabled",   "label": "悬赏功能",              "type": "bool",   "default": "true"},
        {"key": "wish_max_concurrent",   "label": "最大同时心愿数",         "type": "number", "default": "3"},
        {"key": "wish_daily_post_limit", "label": "每日发布上限（0=不限）", "type": "number", "default": "0"},
        {"key": "wish_daily_pick_limit", "label": "每日接取上限（0=不限）", "type": "number", "default": "0"},
    ]},
    {"section": "目击系统", "json_parent": "sighting_system_config", "fields": [
        {"key": "enabled",               "label": "启用目击",       "type": "bool",   "default": "true"},
        {"key": "send_to_all",           "label": "双向通知",       "type": "bool",   "default": "true"},
        {"key": "max_reports_per_day",   "label": "每日最大目击数", "type": "number", "default": "5"},
        {"key": "include_ended_meetings","label": "包含已结束场次", "type": "bool",   "default": "false"},
        {"key": "time_overlap_threshold","label": "时间重叠阈值",   "type": "number", "default": "0.3"},
    ]},
    {"section": "场所系统", "json_parent": "place_system_config", "fields": [
        {"key": "enabled",               "label": "启用场所系统", "type": "bool", "default": "true"},
        {"key": "require_key_by_default","label": "默认需要钥匙", "type": "bool", "default": "false"},
    ]},
    {"section": "道具", "fields": [
        {"key": "item_tracker_success_rate", "label": "追踪器成功率（%）",  "type": "number", "default": "70", "min": 0, "max": 100},
        {"key": "item_tracker_show_partner", "label": "追踪器显示伙伴",    "type": "bool",   "default": "true"},
        {"key": "item_tracker_time_restrict","label": "追踪器时间限制",    "type": "bool",   "default": "true"},
        {"key": "apply_item_notification",   "label": "施加道具提醒",      "type": "bool",   "default": "true"},
        {"key": "apply_item_expose_rate",    "label": "施加暴露概率（%）", "type": "number", "default": "0", "min": 0, "max": 100},
        {"key": "apply_item_hours",          "label": "施加可用时段",      "type": "text",   "default": ""},
        {"key": "shop_gift_catalog_on_receive","label": "收到即入图鉴",    "type": "bool",   "default": "false"},
    ]},
    {"section": "拍卖", "fields": [
        {"key": "auction_allow_anon",      "label": "允许匿名出价",   "type": "bool", "default": "true"},
        {"key": "auction_broadcast",       "label": "出价播报",       "type": "bool", "default": "true"},
        {"key": "auction_show_top_bidder", "label": "展示最高出价者", "type": "bool", "default": "true"},
        {"key": "auction_currency",        "label": "拍卖货币",       "type": "text", "default": "金币"},
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
            result[jp] = json.dumps(obj, ensure_ascii=False)
        else:
            for f in sec["fields"]:
                result[f["key"]] = flat.get(f["key"], str(f["default"]))
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
            name                TEXT NOT NULL DEFAULT '第一弧',
            description         TEXT DEFAULT '',
            is_current          INTEGER DEFAULT 0,
            public_view_enabled INTEGER DEFAULT 0,
            public_token        TEXT UNIQUE,
            created_at          INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shows_tenant ON shows(tenant_id)")

    # 为每个租户创建默认弧
    for (tid,) in conn.execute("SELECT id FROM tenants").fetchall():
        if not conn.execute("SELECT id FROM shows WHERE tenant_id=?", (tid,)).fetchone():
            conn.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,0,?,?)",
                (tid, "第一弧", secrets.token_urlsafe(24), int(time.time() * 1000))
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


# ── Auth ─────────────────────────────────────────────────────────────────────

def current_tenant_id():
    return session.get("tenant_id")

def get_show_id():
    """当前管理员正在查看的弧 ID（存于 session）。"""
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
    """API 用：找该租户当前活跃弧的 ID。"""
    db  = get_db()
    row = db.execute("SELECT id FROM shows WHERE tenant_id=? AND is_current=1", (tenant_id,)).fetchone()
    if not row:
        row = db.execute("SELECT id FROM shows WHERE tenant_id=? ORDER BY id DESC", (tenant_id,)).fetchone()
    return row["id"] if row else None

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
            SELECT p.qq, p.role_name, p.show_name,
                   p.sessions_count, p.total_replies, p.total_words, p.last_updated,
                   t.username AS tenant_username, t.display_name AS tenant_display,
                   s.name AS arc_name
            FROM players p
            JOIN tenants t ON p.tenant_id = t.id
            JOIN shows   s ON p.show_id   = s.id
            WHERE p.qq = ?
            ORDER BY p.last_updated DESC
        """, (qq,)).fetchall()
        rows = [dict(r) for r in rows]
        for r in rows:
            r["last_updated_str"] = ts_to_str(r["last_updated"])
        if rows:
            summary = {
                "qq": qq,
                "total_sessions": sum(r["sessions_count"] for r in rows),
                "total_replies":  sum(r["total_replies"]  for r in rows),
                "total_words":    sum(r["total_words"]    for r in rows),
                "arc_count":      len(rows),
            }
    # top players across all tenants (for browse view)
    top = db.execute("""
        SELECT qq, SUM(total_replies) AS replies, SUM(total_words) AS words,
               COUNT(*) AS arc_count, MAX(last_updated) AS last_updated
        FROM players GROUP BY qq
        ORDER BY words DESC LIMIT 50
    """).fetchall()
    top = [dict(r) for r in top]
    for r in top:
        r["last_updated_str"] = ts_to_str(r["last_updated"])
    return render_template("superadmin_players.html",
                           qq=qq, rows=rows, summary=summary, top=top)

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
        # 自动为新租户创建第一弧
        new_tenant = db.execute("SELECT id FROM tenants WHERE username=?", (username,)).fetchone()
        if new_tenant:
            db.execute(
                "INSERT INTO shows (tenant_id,name,is_current,public_view_enabled,public_token,created_at) "
                "VALUES (?,?,1,0,?,?)",
                (new_tenant["id"], "第一弧", secrets.token_urlsafe(24), now)
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


# ── 弧管理路由 ───────────────────────────────────────────────────────────────

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
    """将指定弧设为「当前弧」（机器人数据写入此弧）。"""
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
    """切换管理员当前查看的弧。"""
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
    return render_template("admin_config.html", schema=CONFIG_SCHEMA,
                           flat=flat, routing_display=routing_display,
                           saved=request.args.get("saved"))


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
        (days if d["game_day"].strip() else incomplete).append(d)
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
    for table in ("rp_entries", "extra_events", "sessions", "players"):
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

    def fmt_seconds(secs):
        secs = int(secs)
        return f"{secs//60}分{secs%60}秒" if secs >= 60 else f"{secs}秒"

    return render_template("admin_player.html", player=player, player_sessions=player_sessions,
                           timing_stats=timing_stats, fmt_seconds=fmt_seconds, ts_to_str=ts_to_str)


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
    return redirect(url_for("character_view", role_name=q))


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
    days = []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        if d["game_day"].strip():
            days.append(d)
    return render_template("public_home.html", show=show, days=days, token=token)

@app.route("/view/<token>/date/<game_day>")
def public_date(token, game_day):
    show = _get_public_show(token)
    if not show: abort(404)
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE show_id=? AND game_day=? ORDER BY start_ts DESC", (show["id"], game_day)
    ).fetchall()
    show_names = get_show_names(db, show["id"])
    return render_template("public_date.html", show=show, token=token,
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
    events     = _parse_events(db.execute("SELECT * FROM extra_events WHERE session_id=? AND show_id=? ORDER BY timestamp", (session_id, show["id"])).fetchall())
    show_names = get_show_names(db, show["id"])
    return render_template("public_session.html", show=show, token=token,
                           sess=sess, rp=rp, events=events, show_names=show_names, ts_to_str=ts_to_str)

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

@app.route("/api/event", methods=["POST"])
def api_event():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data       = request.json or {}
    event_type = data.get("type", "")
    if event_type not in ("lovemail", "sms", "gift"):
        return jsonify({"ok": False, "error": "invalid type"}), 400
    db = get_db()
    db.execute("""
        INSERT INTO extra_events
          (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (show_id, tid, data.get("session_id") or "", event_type,
          data.get("from_role",""), data.get("to_role",""), data.get("content",""),
          json.dumps(data.get("extra_info",{}), ensure_ascii=False),
          data.get("timestamp",0), data.get("game_day","")))
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
            VALUES (?,?,?,?,'',' ','','','','[]',?,0,0,0,0,'{}')
        """, (sid, show_id, tid, data.get("group_id",""), data.get("timestamp",0)))
    max_seq = db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM rp_entries WHERE session_id=? AND show_id=?", (sid, show_id)
    ).fetchone()[0]
    db.execute("""
        INSERT INTO rp_entries (show_id,tenant_id,session_id,role_name,content,seq,timestamp)
        VALUES (?,?,?,?,?,?,?)
    """, (show_id, tid, sid, data.get("role_name",""), data.get("content",""),
          max_seq+1, data.get("timestamp",0)))
    db.execute(
        "UPDATE sessions SET total_replies=total_replies+1, total_words=total_words+? WHERE id=? AND show_id=?",
        (len(data.get("content","")), sid, show_id)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/session_end", methods=["POST"])
def api_session_end():
    tid     = get_tenant_from_token()
    show_id = get_current_show_id_for_tenant(tid)
    if not show_id: abort(503)
    data = request.json or {}
    sid  = data.get("session_id","")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400
    stats = data.get("stats",{})
    parts = data.get("participants",[])
    db    = get_db()
    db.execute("""
        INSERT OR REPLACE INTO sessions
          (id,show_id,tenant_id,group_id,platform,game_day,game_time,place,subtype,
           participants,start_ts,end_ts,forced,total_replies,total_words,stats)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (sid, show_id, tid,
          data.get("group_id",""), data.get("platform",""),
          data.get("game_day",""), data.get("game_time",""),
          data.get("place",""),    data.get("subtype",""),
          json.dumps(parts, ensure_ascii=False),
          data.get("start_ts",0), data.get("end_ts",0),
          1 if data.get("forced") else 0,
          sum(v.get("replies",0) for v in stats.values()),
          sum(v.get("words",0)   for v in stats.values()),
          json.dumps(stats, ensure_ascii=False)))
    db.commit()
    return jsonify({"ok": True})

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
        elif action == "add_set":
            set_name = request.form.get("set_name","").strip()
            # 群号组本身不需要单独存，首次添加群号时自动创建；这里只做校验
            msg = "set_created" if set_name else None
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
    rows = db.execute(
        "SELECT * FROM known_groups WHERE show_id=? ORDER BY set_name, created_at",
        (sid,)
    ).fetchall()
    # 按 set_name 分组
    from collections import OrderedDict
    sets = OrderedDict()
    for r in rows:
        sn = r["set_name"] or "（未分组）"
        sets.setdefault(sn, []).append(dict(r))
    return render_template("admin_groups.html", sets=sets, msg=msg)


# ── 结戏奖励 Dashboard ────────────────────────────────────────────────────────

def _get_reward_config(db, show_id):
    rows = db.execute(
        "SELECT key,value FROM site_config WHERE show_id=? AND key IN (?,?,?)",
        (show_id, "reward_bonus_templates", "reward_draw_config", "reward_item_registry")
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
            return redirect(url_for("admin_rewards") + "?err=json")
        _save_reward_config_key(db, sid, tid, "reward_item_registry", val)
        db.commit()
    elif section == "bonus":
        raw = request.form.get("bonus_templates_json","").strip()
        try:
            parsed = json.loads(raw)
            val = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            return redirect(url_for("admin_rewards") + "?err=json")
        _save_reward_config_key(db, sid, tid, "reward_bonus_templates", val)
        db.commit()
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


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
