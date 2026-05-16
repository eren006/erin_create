import io, os, json, functools
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort, send_file)
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "rp_archive_secret_key_change_me")

DB_PATH    = os.path.join(os.path.dirname(__file__), "rp_data.db")
VIEW_PASS  = os.environ.get("RP_VIEW_PASSWORD", "")
ADMIN_PASS = os.environ.get("RP_ADMIN_PASSWORD", "pDynLBeLGEjd")
API_TOKEN  = os.environ.get("RP_API_TOKEN", "")

# ── Config schema ────────────────────────────────────────────────────────────
# DB key for JSON sub-fields: f"{json_parent}__{field_key}"
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
        {"key": "allow_custom_letter_sign", "label": "寄信自定义名字",    "type": "bool",   "default": "false", "note": "玩家可在信末自填署名而非自动用角色名"},
        {"key": "shop_refresh_hours",       "label": "礼品店刷新（小时）", "type": "number", "default": "24"},
    ]},
    {"section": "邀约", "fields": [
        {"key": "enable_join_existing_appointment", "label": "允许加入已有私约", "type": "bool",   "default": "true",  "note": "允许玩家中途加入他人已开启的私约"},
        {"key": "require_fupan_before_end",         "label": "复盘强制结束",     "type": "bool",   "default": "true",  "note": "结束私约前须先完成复盘发言"},
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
        {"key": "lovemail_delivery_time",  "label": "送达时间",       "type": "text",   "default": "22:00", "note": "如 22:00"},
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
        {"key": "send_to_all",           "label": "双向通知",       "type": "bool",   "default": "true",  "note": "开=双方都收到通知，关=仅通知举报者"},
        {"key": "max_reports_per_day",   "label": "每日最大目击数", "type": "number", "default": "5"},
        {"key": "include_ended_meetings","label": "包含已结束场次", "type": "bool",   "default": "false", "note": "目击检测是否纳入已结束的场次"},
        {"key": "time_overlap_threshold","label": "时间重叠阈值",   "type": "number", "default": "0.3", "note": "0~1 的小数，0.3 = 30%"},
    ]},
    {"section": "场所系统", "json_parent": "place_system_config", "fields": [
        {"key": "enabled",               "label": "启用场所系统", "type": "bool", "default": "true"},
        {"key": "require_key_by_default","label": "默认需要钥匙", "type": "bool", "default": "false", "note": "新建场所时默认须持有钥匙才能进入"},
    ]},
    {"section": "道具", "fields": [
        {"key": "item_tracker_success_rate", "label": "追踪器成功率（%）",   "type": "number", "default": "70", "min": 0, "max": 100},
        {"key": "item_tracker_show_partner", "label": "追踪器显示伙伴",     "type": "bool",   "default": "true",  "note": "成功时是否显示目标当前的同伴"},
        {"key": "item_tracker_time_restrict","label": "追踪器时间限制",     "type": "bool",   "default": "true",  "note": "追踪器是否受施加可用时段限制"},
        {"key": "apply_item_notification",   "label": "施加道具提醒",       "type": "bool",   "default": "true",  "note": "对目标施加道具时是否通知目标"},
        {"key": "apply_item_expose_rate",    "label": "施加暴露概率（%）",  "type": "number", "default": "0", "min": 0, "max": 100, "note": "施加时暴露施加者姓名的概率"},
        {"key": "apply_item_hours",          "label": "施加可用时段",       "type": "text",   "default": "", "note": "如 18-23，留空全天可用"},
        {"key": "shop_gift_catalog_on_receive","label": "收到即入图鉴",     "type": "bool",   "default": "false", "note": "收到礼物后自动解锁该礼物的图鉴条目"},
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

def get_flat_config(db):
    rows = db.execute("SELECT key, value FROM site_config").fetchall()
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


# ── DB helpers ──────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with get_db() as conn:
        with open(schema, encoding="utf-8") as f:
            conn.executescript(f.read())

def _effective_password(db_key, env_fallback):
    db = get_db()
    row = db.execute("SELECT value FROM site_config WHERE key=?", (db_key,)).fetchone()
    db.close()
    stored = row["value"] if row and row["value"] else None
    return stored or env_fallback

def ts_to_str(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


# ── Auth decorators ──────────────────────────────────────────────────────────

def require_login(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

def require_admin(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped

def require_token(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if API_TOKEN and request.headers.get("X-Archive-Token") != API_TOKEN:
            abort(403)
        return f(*args, **kwargs)
    return wrapped


# ── Web routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == _effective_password("view_password", VIEW_PASS):
            session["logged_in"] = True
            return redirect(url_for("home"))
        error = "密码错误，请重试。"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    session.pop("admin_logged_in", None)
    return redirect(url_for("login"))

@app.route("/admin/login", methods=["GET", "POST"])
@require_login
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == _effective_password("admin_password", ADMIN_PASS):
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        error = "后台密钥错误，请重试。"
    return render_template("admin_login.html", error=error)

@app.route("/admin/change_password", methods=["POST"])
@require_admin
def admin_change_password():
    vp = request.form.get("view_password", "").strip()
    ap = request.form.get("admin_password", "").strip()
    db = get_db()
    if vp:
        db.execute("INSERT INTO site_config(key,value) VALUES('view_password',?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (vp,))
    if ap:
        db.execute("INSERT INTO site_config(key,value) VALUES('admin_password',?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (ap,))
    db.commit()
    db.close()
    if vp:
        session.pop("logged_in", None)
        session.pop("admin_logged_in", None)
        return redirect(url_for("login"))
    if ap:
        session.pop("admin_logged_in", None)
        return redirect(url_for("admin_login"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

@app.route("/admin/backup")
@require_admin
def admin_backup():
    return send_file(DB_PATH, as_attachment=True, download_name="rp_data.db",
                     mimetype="application/octet-stream")

def _parse_routing_text(text):
    """Convert 'D1:群号 D2:群号' text → JSON string for bot storage."""
    import re
    pairs = re.findall(r'(D\d+)[：:]\s*(\d+)', text or "", re.IGNORECASE)
    return json.dumps({k.upper(): v for k, v in pairs}, ensure_ascii=False)

def _routing_to_display(json_str):
    """Convert stored JSON → 'D1:群号 D2:群号' display text."""
    try:
        m = json.loads(json_str or "{}")
        return " ".join(f"{k}:{v}" for k, v in sorted(m.items()))
    except Exception:
        return ""

@app.route("/admin/config", methods=["GET", "POST"])
@require_admin
def admin_config_page():
    db = get_db()
    if request.method == "POST":
        for sec in CONFIG_SCHEMA:
            for f in sec["fields"]:
                db_key = _cfg_db_key(sec, f["key"])
                if f["type"] == "bool":
                    value = "true" if request.form.get(db_key) else "false"
                elif f["type"] == "routing":
                    value = _parse_routing_text(request.form.get(db_key, ""))
                else:
                    value = request.form.get(db_key, str(f["default"]))
                db.execute(
                    "INSERT INTO site_config(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (db_key, value)
                )
        db.commit()
        db.close()
        return redirect(url_for("admin_config_page") + "?saved=1")
    flat = get_flat_config(db)
    db.close()
    # Pre-convert routing fields for display
    routing_display = {}
    for sec in CONFIG_SCHEMA:
        for f in sec["fields"]:
            if f["type"] == "routing":
                db_key = _cfg_db_key(sec, f["key"])
                routing_display[db_key] = _routing_to_display(flat.get(db_key, ""))
    return render_template("admin_config.html", schema=CONFIG_SCHEMA,
                           flat=flat, routing_display=routing_display,
                           saved=request.args.get("saved"))

@app.route("/")
@require_login
def home():
    db = get_db()
    rows = db.execute("""
        SELECT game_day,
               COUNT(*) AS session_count,
               SUM(total_replies) AS total_replies,
               SUM(total_words)   AS total_words,
               MIN(start_ts)      AS first_ts
        FROM sessions
        GROUP BY game_day
        ORDER BY first_ts DESC
    """).fetchall()
    db.close()
    days, incomplete = [], []
    for r in rows:
        d = dict(r)
        d["first_date"] = ts_to_str(d["first_ts"])
        if d["game_day"].strip():
            days.append(d)
        else:
            incomplete.append(d)
    return render_template("home.html", days=days, incomplete=incomplete)

@app.route("/date/<game_day>")
@require_login
def date_view(game_day):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM sessions WHERE game_day=? ORDER BY start_ts DESC",
        (game_day,)
    ).fetchall()
    show_names = get_show_names(db)
    db.close()
    sessions_list = _enrich_sessions(rows)
    return render_template("date.html", game_day=game_day, sessions=sessions_list, show_names=show_names)

@app.route("/session/<path:session_id>")
@require_login
def session_view(session_id):
    db = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not sess:
        abort(404)
    sess = _enrich_session(dict(sess))

    rp = db.execute(
        "SELECT * FROM rp_entries WHERE session_id=? ORDER BY seq, timestamp",
        (session_id,)
    ).fetchall()

    events = db.execute(
        "SELECT * FROM extra_events WHERE session_id=? ORDER BY timestamp",
        (session_id,)
    ).fetchall()
    events_list = []
    for e in events:
        e = dict(e)
        try:
            e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception:
            e["extra_info"] = {}
        events_list.append(e)

    show_names = get_show_names(db)
    db.close()
    return render_template("session.html", sess=sess, rp=rp, events=events_list,
                           show_names=show_names, ts_to_str=ts_to_str)

@app.route("/session/<path:session_id>/download")
@require_login
def session_download(session_id):
    db = get_db()
    sess = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not sess:
        abort(404)
    sess = _enrich_session(dict(sess))

    rp = db.execute(
        "SELECT * FROM rp_entries WHERE session_id=? ORDER BY seq, timestamp",
        (session_id,)
    ).fetchall()

    events = db.execute(
        "SELECT * FROM extra_events WHERE session_id=? ORDER BY timestamp",
        (session_id,)
    ).fetchall()
    events_list = []
    for e in events:
        e = dict(e)
        try:
            e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception:
            e["extra_info"] = {}
        events_list.append(e)
    db.close()

    # Determine show_name from stats or participants context
    show_name = '长日将尽'

    lines = []
    lines.append("=" * 40)
    lines.append(f"【 {show_name} · {sess.get('game_day', '')} 场次存档 】")
    lines.append("=" * 40)
    lines.append(f"地点：{sess.get('place') or '未记录'}")
    lines.append(f"时间段：{sess.get('game_time') or '—'}")
    subtype_str = sess.get('subtype') or '私密'
    forced_str = '  【强结】' if sess.get('forced') else ''
    lines.append(f"类型：{subtype_str}{forced_str}")
    lines.append(f"开始：{sess.get('start_str', '')}  结束：{sess.get('end_str') or '—'}")
    participants = sess.get('participants') or []
    lines.append(f"参与者：{', '.join(participants)}")
    lines.append("")
    lines.append("【统计】")
    lines.append(f"总回复：{sess.get('total_replies', 0)}  总字数：{sess.get('total_words', 0)}")
    stats = sess.get('stats') or {}
    for role, st in stats.items():
        replies = st.get('replies', 0)
        words = st.get('words', 0)
        avg = words // replies if replies else 0
        lines.append(f"{role}：{replies}回复 · {words}字 · 均{avg}字/回")
    lines.append("")
    lines.append("=" * 40)
    lines.append("【 RP 正文 】")
    lines.append("=" * 40)
    lines.append("")
    for entry in rp:
        entry = dict(entry)
        lines.append(f"▷ {entry.get('role_name', '')}  {ts_to_str(entry.get('timestamp', 0))}")
        lines.append("─" * 20)
        lines.append(entry.get('content', ''))
        lines.append("")

    lines.append("=" * 40)
    lines.append("【 事件记录 】")
    lines.append("=" * 40)
    if events_list:
        type_labels = {"lovemail": "心动信", "sms": "短信", "gift": "礼物"}
        from itertools import groupby
        events_list.sort(key=lambda e: e.get('type', ''))
        for etype, group in groupby(events_list, key=lambda e: e.get('type', '')):
            label = type_labels.get(etype, etype)
            lines.append(f"\n── {label} ──")
            for e in group:
                lines.append(f"{e.get('from_role', '')} → {e.get('to_role', '')}")
                if e.get('content'):
                    lines.append(e['content'])
    else:
        lines.append("（本场无记录）")

    text = "\n".join(lines)
    buf = io.BytesIO(text.encode("utf-8"))
    buf.seek(0)

    place_part = (sess.get('place') or '场次').replace('/', '_').replace('\\', '_')
    game_day_part = (sess.get('game_day') or 'unknown').replace('/', '_')
    sid_part = str(session_id)[:8]
    filename = f"{game_day_part}_{place_part}_{sid_part}.txt"

    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="text/plain; charset=utf-8")


@app.route("/admin")
@require_admin
def admin():
    db = get_db()
    sessions_count = db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    rp_count       = db.execute("SELECT COUNT(*) FROM rp_entries").fetchone()[0]
    events_count   = db.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0]
    players        = db.execute("SELECT * FROM players ORDER BY sessions_count DESC, last_updated DESC").fetchall()
    players_count  = len(players)
    db.close()
    cleared = request.args.get('cleared')
    return render_template("admin.html",
                           sessions_count=sessions_count,
                           rp_count=rp_count,
                           events_count=events_count,
                           players=[dict(p) for p in players],
                           players_count=players_count,
                           cleared=cleared,
                           ts_to_str=ts_to_str)


@app.route("/admin/clear_all", methods=["POST"])
@require_admin
def admin_clear_all():
    db = get_db()
    db.execute("DELETE FROM rp_entries")
    db.execute("DELETE FROM extra_events")
    db.execute("DELETE FROM sessions")
    db.execute("DELETE FROM players")
    db.commit()
    db.close()
    return redirect(url_for("admin") + "?cleared=1")


@app.route("/admin/player/<qq>")
@require_admin
def admin_player(qq):
    db = get_db()
    player = db.execute("SELECT * FROM players WHERE qq=?", (qq,)).fetchone()
    if player:
        player = dict(player)
    else:
        player = {"qq": qq, "role_name": "", "show_name": "", "sessions_count": 0,
                  "total_replies": 0, "total_words": 0, "last_updated": 0}

    role_name = player.get("role_name", "")
    all_sessions = db.execute("SELECT * FROM sessions ORDER BY start_ts DESC").fetchall()
    player_sessions = []
    for s in all_sessions:
        s = _enrich_session(dict(s))
        if role_name and role_name in s["participants"]:
            player_sessions.append(s)

    # Calculate timing stats per session
    timing_stats = []
    for s in player_sessions:
        sid = s["id"]
        entries = db.execute(
            "SELECT role_name, timestamp FROM rp_entries WHERE session_id=? ORDER BY seq, timestamp",
            (sid,)
        ).fetchall()
        entries = [dict(e) for e in entries]
        reply_times = []
        for i in range(1, len(entries)):
            prev = entries[i - 1]
            curr = entries[i]
            if curr["role_name"] == role_name and prev["role_name"] != role_name:
                diff_ms = curr["timestamp"] - prev["timestamp"]
                if diff_ms > 0:
                    reply_times.append(diff_ms / 1000)
        if reply_times:
            timing_stats.append({
                "session_id": sid,
                "game_day": s.get("game_day", ""),
                "place": s.get("place", ""),
                "avg": sum(reply_times) / len(reply_times),
                "max": max(reply_times),
                "min": min(reply_times),
                "count": len(reply_times),
            })

    def fmt_seconds(secs):
        secs = int(secs)
        if secs >= 60:
            return f"{secs // 60}分{secs % 60}秒"
        return f"{secs}秒"

    db.close()
    return render_template("admin_player.html", player=player,
                           player_sessions=player_sessions,
                           timing_stats=timing_stats,
                           fmt_seconds=fmt_seconds,
                           ts_to_str=ts_to_str)


@app.route("/character/<role_name>")
@require_login
def character_view(role_name):
    db = get_db()
    rows = db.execute("SELECT * FROM sessions ORDER BY start_ts DESC").fetchall()
    show_names = get_show_names(db)
    db.close()
    sessions_list = [s for s in _enrich_sessions(rows) if role_name in s["participants"]]
    return render_template("character.html", role_name=role_name, sessions=sessions_list,
                           show_names=show_names)

@app.route("/interactions")
@require_login
def interactions_index():
    db = get_db()
    rows = db.execute("""
        SELECT role_name,
               SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END) AS lovemails,
               SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END) AS smss,
               SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END) AS gifts
        FROM (
            SELECT from_role AS role_name, type FROM extra_events
            UNION ALL
            SELECT to_role   AS role_name, type FROM extra_events
        )
        GROUP BY role_name
        ORDER BY (SUM(CASE WHEN type='lovemail' THEN 1 ELSE 0 END)
                + SUM(CASE WHEN type='sms'      THEN 1 ELSE 0 END)
                + SUM(CASE WHEN type='gift'     THEN 1 ELSE 0 END)) DESC
    """).fetchall()
    db.close()
    return render_template("interactions_index.html", roles=[dict(r) for r in rows])

@app.route("/character/<role_name>/interactions")
@require_login
def character_interactions(role_name):
    db = get_db()
    rows = db.execute("""
        SELECT e.*, s.game_day AS s_game_day, s.place AS s_place, s.game_time AS s_game_time
        FROM extra_events e
        LEFT JOIN sessions s ON e.session_id = s.id
        WHERE e.from_role = ? OR e.to_role = ?
        ORDER BY e.timestamp DESC
    """, (role_name, role_name)).fetchall()
    show_names = get_show_names(db)
    db.close()

    events = []
    for e in rows:
        e = dict(e)
        try:
            e["extra_info"] = json.loads(e["extra_info"] or "{}")
        except Exception:
            e["extra_info"] = {}
        e["time_str"] = ts_to_str(e["timestamp"])
        e["game_day"] = e["game_day"] or e["s_game_day"] or ""
        events.append(e)

    lovemails = [e for e in events if e["type"] == "lovemail"]
    smss      = [e for e in events if e["type"] == "sms"]
    gifts     = [e for e in events if e["type"] == "gift"]

    # 配对统计
    pairs = {}
    for e in events:
        other = e["to_role"] if e["from_role"] == role_name else e["from_role"]
        if other not in pairs:
            pairs[other] = {"lovemail_sent": 0, "lovemail_recv": 0,
                            "sms_sent": 0, "sms_recv": 0,
                            "gift_sent": 0, "gift_recv": 0}
        suffix = "sent" if e["from_role"] == role_name else "recv"
        pairs[other][f"{e['type']}_{suffix}"] += 1
    pairs_list = sorted(
        [(k, v, sum(v.values())) for k, v in pairs.items()],
        key=lambda x: -x[2]
    )

    # 混沌统计
    chaos_smss  = [e for e in smss  if e.get("extra_info", {}).get("is_chaos")]
    lost_gifts  = [e for e in gifts if e.get("extra_info", {}).get("isLost")]
    chaos_stats = {
        "sms_total":      len(chaos_smss),
        "misdelivered":   sum(1 for e in chaos_smss if e["extra_info"].get("is_misdelivered")),
        "content_chaos":  sum(1 for e in chaos_smss if e["extra_info"].get("is_content_chaos")),
        "sig_chaos":      sum(1 for e in chaos_smss if e["extra_info"].get("is_signature_chaos")),
        "lost_gifts":     len(lost_gifts),
    }

    return render_template("character_interactions.html",
                           role_name=role_name,
                           lovemails=lovemails, smss=smss, gifts=gifts,
                           pairs_list=pairs_list, chaos_stats=chaos_stats,
                           show_names=show_names)

@app.route("/search")
@require_login
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("home"))
    return redirect(url_for("character_view", role_name=q))


# ── API routes ───────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
@require_token
def api_config():
    db = get_db()
    flat = get_flat_config(db)
    db.close()
    return jsonify(assemble_bot_config(flat))

@app.route("/api/event", methods=["POST"])
@require_token
def api_event():
    data      = request.json or {}
    event_type = data.get("type", "")
    if event_type not in ("lovemail", "sms", "gift"):
        return jsonify({"ok": False, "error": "invalid type"}), 400

    sid       = data.get("session_id") or ""
    timestamp = data.get("timestamp", 0)
    game_day  = data.get("game_day", "")

    db = get_db()

    db.execute("""
        INSERT INTO extra_events
          (session_id, type, from_role, to_role, content, extra_info, timestamp, game_day)
        VALUES (?,?,?,?,?,?,?,?)
    """, (sid, event_type,
          data.get("from_role", ""), data.get("to_role", ""),
          data.get("content", ""),
          json.dumps(data.get("extra_info", {}), ensure_ascii=False),
          timestamp, game_day))

    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/rp", methods=["POST"])
@require_token
def api_rp():
    data = request.json or {}
    sid  = data.get("session_id", "")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
    if not existing:
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id, group_id, platform, game_day, game_time, place, subtype,
               participants, start_ts, end_ts, forced, total_replies, total_words, stats)
            VALUES (?,?,'',' ','','','','[]',?,0,0,0,0,'{}')
        """, (sid, data.get("group_id", ""), data.get("timestamp", 0)))

    max_seq = db.execute(
        "SELECT COALESCE(MAX(seq),0) FROM rp_entries WHERE session_id=?", (sid,)
    ).fetchone()[0]

    db.execute("""
        INSERT INTO rp_entries (session_id, role_name, content, seq, timestamp)
        VALUES (?,?,?,?,?)
    """, (sid, data.get("role_name",""), data.get("content",""),
          max_seq + 1, data.get("timestamp", 0)))

    db.execute("""
        UPDATE sessions
        SET total_replies = total_replies + 1,
            total_words   = total_words + ?
        WHERE id=?
    """, (len(data.get("content", "")), sid))

    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/session_end", methods=["POST"])
@require_token
def api_session_end():
    data = request.json or {}
    sid  = data.get("session_id", "")
    if not sid:
        return jsonify({"ok": False, "error": "missing session_id"}), 400

    stats  = data.get("stats", {})
    parts  = data.get("participants", [])
    t_rep  = sum(v.get("replies", 0) for v in stats.values())
    t_wrd  = sum(v.get("words",   0) for v in stats.values())

    db = get_db()
    db.execute("""
        INSERT OR REPLACE INTO sessions
          (id, group_id, platform, game_day, game_time, place, subtype,
           participants, start_ts, end_ts, forced, total_replies, total_words, stats)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (sid,
          data.get("group_id",""), data.get("platform",""),
          data.get("game_day",""), data.get("game_time",""),
          data.get("place",""),    data.get("subtype",""),
          json.dumps(parts, ensure_ascii=False),
          data.get("start_ts", 0), data.get("end_ts", 0),
          1 if data.get("forced") else 0,
          t_rep, t_wrd,
          json.dumps(stats, ensure_ascii=False)))

    # 心动信/短信/礼物已在事件发生时通过 /api/event 实时入库，此处无需处理

    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/update_players", methods=["POST"])
@require_token
def api_update_players():
    data      = request.json or {}
    show_name = data.get("show_name", "")
    players   = data.get("players", [])
    if not isinstance(players, list):
        return jsonify({"ok": False, "error": "players must be a list"}), 400

    import time
    now = int(time.time() * 1000)
    db = get_db()
    count = 0
    for p in players:
        qq        = str(p.get("qq", "")).strip()
        role_name = str(p.get("role_name", "")).strip()
        if not qq or not role_name:
            continue
        db.execute("""
            INSERT INTO players (qq, role_name, show_name, sessions_count, total_replies, total_words, last_updated)
            VALUES (?, ?, ?, 0, 0, 0, ?)
            ON CONFLICT(qq) DO UPDATE SET
                role_name    = excluded.role_name,
                show_name    = excluded.show_name,
                last_updated = excluded.last_updated
        """, (qq, role_name, show_name, now))
        count += 1
    db.commit()
    db.close()
    return jsonify({"ok": True, "count": count})


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_show_names(db):
    rows = db.execute(
        "SELECT role_name, show_name FROM players WHERE show_name IS NOT NULL AND show_name != ''"
    ).fetchall()
    return {r["role_name"]: r["show_name"] for r in rows}

def _enrich_session(s):
    try:
        s["participants"] = json.loads(s.get("participants") or "[]")
    except Exception:
        s["participants"] = []
    try:
        s["stats"] = json.loads(s.get("stats") or "{}")
    except Exception:
        s["stats"] = {}
    s["start_str"] = ts_to_str(s.get("start_ts"))
    s["end_str"]   = ts_to_str(s.get("end_ts"))
    start = s.get("start_ts", 0)
    end   = s.get("end_ts", 0)
    if start and end and end > start:
        mins = (end - start) // 60000
        s["duration_str"] = f"{mins // 60}小时{mins % 60}分" if mins >= 60 else f"{mins}分钟"
    else:
        s["duration_str"] = ""
    return s

def _enrich_sessions(rows):
    return [_enrich_session(dict(r)) for r in rows]


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
