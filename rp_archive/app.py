import io, os, json, functools
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, abort, send_file)
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "rp_archive_secret_key_change_me")

DB_PATH    = os.path.join(os.path.dirname(__file__), "rp_data.db")
VIEW_PASS  = os.environ.get("RP_VIEW_PASSWORD", "")
API_TOKEN  = os.environ.get("RP_API_TOKEN", "")


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
        if request.form.get("password") == VIEW_PASS:
            session["logged_in"] = True
            return redirect(url_for("home"))
        error = "密码错误，请重试。"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

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
    db.close()
    sessions_list = _enrich_sessions(rows)
    return render_template("date.html", game_day=game_day, sessions=sessions_list)

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

    db.close()
    return render_template("session.html", sess=sess, rp=rp, events=events_list,
                           ts_to_str=ts_to_str)

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
@require_login
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
@require_login
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
@require_login
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
    db.close()
    sessions_list = [s for s in _enrich_sessions(rows) if role_name in s["participants"]]
    return render_template("character.html", role_name=role_name, sessions=sessions_list)

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

    return render_template("character_interactions.html",
                           role_name=role_name,
                           lovemails=lovemails, smss=smss, gifts=gifts)

@app.route("/search")
@require_login
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("home"))
    return redirect(url_for("character_view", role_name=q))


# ── API routes ───────────────────────────────────────────────────────────────

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
    if sid:
        db.execute("""
            INSERT OR IGNORE INTO sessions
              (id, group_id, platform, game_day, game_time, place, subtype,
               participants, start_ts, end_ts, forced, total_replies, total_words, stats)
            VALUES (?,?,'',' ','','','','[]',?,0,0,0,0,'{}')
        """, (sid, data.get("group_id", ""), timestamp))

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
    return s

def _enrich_sessions(rows):
    return [_enrich_session(dict(r)) for r in rows]


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5001, debug=False)
