"""探索踩点：独立于小手机的玩法（玩家入口 /x，管理入口 /admin/explore）。

玩家用小手机同一个激活码进门（独立 cookie explore_auth，路径 /x，和 phone_auth 互不相干）。
管理员在团后台配：地图（一张图 + 图上的点）、踩点处（每处一张掉落表）、每人每天次数（默认一样，可单人改）、临时次数。
踩点 = 扣一次次数 → 按权重从该处掉落表抽一条：线索（进线索板，每人每条只拿一次）/ 物品（必须是注册过的，
排一条「item」快速设置给机器人，约半分钟内进背包）/ 空手。

app.py 末尾 `import explore; explore.register(globals())` 挂载；init_db 末尾调 explore.init_tables(conn)。
前端模板（explore.html / explore_admin.html）与本文件的 JSON 接口约定见 docs/探索踩点_接口约定.md。
"""
import io, json, os, random, secrets, threading, time, uuid
from datetime import datetime, timedelta, timezone

EXPLORE_COOKIE = "explore_auth"
EXPLORE_COOKIE_AGE = 30 * 24 * 60 * 60
EXPLORE_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "explore_images")
_TZ = timezone(timedelta(hours=8))
_visit_lock = threading.Lock()
_NAMES = ("app", "get_db", "get_show_id", "current_tenant_id", "require_admin", "_phone_code_owner", "_phone_signer",
          "_phone_ip_locked", "_phone_note_fail", "_phone_local", "_PHONE_BAD_CODE", "PHONE_ADMIN", "_phone_csrf",
          "_plugin_status", "_admin_grant_item_names", "_admin_role_list", "_moment_process")
G = {}   # register 时从 app.py 拿到的名字

DROP_KINDS = ("clue", "item", "nothing")


def init_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS explore_settings (
        show_id INTEGER PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 0,
        default_daily INTEGER NOT NULL DEFAULT 3,
        reset_hour INTEGER NOT NULL DEFAULT 0,
        intro TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS explore_maps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL,
        name TEXT NOT NULL, image TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS explore_spots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, map_id INTEGER NOT NULL,
        name TEXT NOT NULL, desc TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '📍',
        x REAL NOT NULL DEFAULT 50, y REAL NOT NULL DEFAULT 50,
        enabled INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0,
        drops TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS explore_quota (
        show_id INTEGER NOT NULL, role TEXT NOT NULL, daily INTEGER NOT NULL,
        PRIMARY KEY (show_id, role)
    );
    CREATE TABLE IF NOT EXISTS explore_bonus (
        id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, role TEXT NOT NULL,
        amount INTEGER NOT NULL, remaining INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS explore_visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, role TEXT NOT NULL,
        spot_id INTEGER NOT NULL, spot_name TEXT NOT NULL DEFAULT '', day TEXT NOT NULL, ts INTEGER NOT NULL,
        used TEXT NOT NULL DEFAULT 'daily',
        kind TEXT NOT NULL DEFAULT 'nothing', title TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '',
        item_name TEXT NOT NULL DEFAULT '', item_qty INTEGER NOT NULL DEFAULT 0, op_id INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_explore_visits ON explore_visits(show_id, role, day);
    CREATE TABLE IF NOT EXISTS explore_clues (
        id INTEGER PRIMARY KEY AUTOINCREMENT, show_id INTEGER NOT NULL, role TEXT NOT NULL,
        spot_id INTEGER NOT NULL, drop_id TEXT NOT NULL, spot_name TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL, seen INTEGER NOT NULL DEFAULT 0,
        UNIQUE (show_id, role, spot_id, drop_id)
    );
    """)


# ───────────────────────── 规则 ─────────────────────────

def _now_ms():
    return int(time.time() * 1000)


def _day_key(reset_hour=0):
    """自然日（北京时间），reset_hour 点才算新的一天"""
    return (datetime.now(_TZ) - timedelta(hours=reset_hour)).strftime("%Y-%m-%d")


def get_settings(db, sid):
    r = db.execute("SELECT * FROM explore_settings WHERE show_id=?", (sid,)).fetchone()
    if not r:
        return {"enabled": False, "default_daily": 3, "reset_hour": 0, "intro": ""}
    return {"enabled": bool(r["enabled"]), "default_daily": r["default_daily"], "reset_hour": r["reset_hour"], "intro": r["intro"]}


def quota_state(db, sid, role, st=None):
    """{day, daily_limit, daily_used, daily_left, bonus, total}"""
    st = st or get_settings(db, sid)
    day = _day_key(st["reset_hour"])
    row = db.execute("SELECT daily FROM explore_quota WHERE show_id=? AND role=?", (sid, role)).fetchone()
    limit = row["daily"] if row else st["default_daily"]
    used = db.execute("SELECT COUNT(*) FROM explore_visits WHERE show_id=? AND role=? AND day=? AND used='daily'",
                      (sid, role, day)).fetchone()[0]
    bonus = db.execute("SELECT COALESCE(SUM(remaining),0) FROM explore_bonus WHERE show_id=? AND role=?", (sid, role)).fetchone()[0]
    left = max(0, limit - used)
    return {"day": day, "daily_limit": limit, "daily_used": used, "daily_left": left,
            "daily_custom": bool(row), "bonus": bonus, "total": left + bonus}


def _clean_drops(raw, allowed_items=None):
    """掉落表校验。返回 (清洗后的列表, 错误或 None)。allowed_items=None 表示不校验物品名（旧插件没有清单时由调用方决定）"""
    out = []
    if not isinstance(raw, list):
        return [], "掉落表格式不对"
    for d in raw[:30]:
        if not isinstance(d, dict) or d.get("kind") not in DROP_KINDS:
            return [], "掉落类型不对"
        try:
            w = int(d.get("weight", 1))
        except (TypeError, ValueError):
            return [], "权重要填整数"
        if not 1 <= w <= 1000:
            return [], "权重要在 1~1000"
        e = {"id": str(d.get("id") or uuid.uuid4().hex[:8])[:16], "kind": d["kind"], "weight": w}
        if d["kind"] == "clue":
            e["title"] = str(d.get("title") or "").strip()[:30]
            e["text"] = str(d.get("text") or "").strip()[:600]
            if not e["title"] or not e["text"]:
                return [], "线索要有标题和内容"
        elif d["kind"] == "item":
            e["item"] = str(d.get("item") or "").strip()[:40]
            try:
                e["qty"] = int(d.get("qty", 1))
            except (TypeError, ValueError):
                return [], "物品数量要填整数"
            if not 1 <= e["qty"] <= 999:
                return [], "物品数量要在 1~999"
            if allowed_items is not None and e["item"] not in allowed_items:
                return [], f"「{e['item']}」不是注册过的物品，请从下拉里选"
            e["text"] = str(d.get("text") or "").strip()[:200]   # 掉落时的一句话描述（可空）
        else:
            e["text"] = str(d.get("text") or "").strip()[:200]
        out.append(e)
    return out, None


def roll(db, sid, role, spot, plug):
    """从该处掉落表抽一条；排除已拿过的线索，物品在插件不能发/不在注册清单时也排除。返回 drop 或 None（没有新发现）"""
    owned = {r["drop_id"] for r in db.execute("SELECT drop_id FROM explore_clues WHERE show_id=? AND role=? AND spot_id=?",
                                              (sid, role, spot["id"]))}
    cat = plug.get("catalog")
    reg = {i.get("name") for i in cat if isinstance(i, dict)} if cat is not None else None
    pool = []
    for d in json.loads(spot["drops"] or "[]"):
        if d["kind"] == "clue" and d["id"] in owned:
            continue
        if d["kind"] == "item" and (not plug.get("can") or (reg is not None and d["item"] not in reg)):
            continue
        pool.append(d)
    if not pool:
        return None
    return random.choices(pool, weights=[d["weight"] for d in pool], k=1)[0]


def do_visit(db, sid, role, spot_id):
    """踩点一次。返回 (结果 dict, http 状态)"""
    with _visit_lock:
        st = get_settings(db, sid)
        if not st["enabled"]:
            return {"ok": False, "error": "探索还没有开放"}, 403
        spot = db.execute("SELECT s.*, m.name AS map_name FROM explore_spots s JOIN explore_maps m ON m.id=s.map_id "
                          "WHERE s.show_id=? AND s.id=? AND s.enabled=1", (sid, spot_id)).fetchone()
        if not spot:
            return {"ok": False, "error": "这个地方去不了"}, 404
        q = quota_state(db, sid, role, st)
        if q["total"] <= 0:
            return {"ok": False, "error": "今天的次数用完了", "quota": q}, 409
        plug = G["_plugin_status"](db, sid)
        drop = roll(db, sid, role, spot, plug)
        if drop is None:
            return {"ok": True, "kind": "empty", "title": "这里没有新发现了", "text": "该找的都找过了，换个地方看看吧。",
                    "consumed": False, "quota": q}, 200
        now = _now_ms()
        used = "daily"
        if q["daily_left"] <= 0:
            used = "bonus"
            b = db.execute("SELECT id FROM explore_bonus WHERE show_id=? AND role=? AND remaining>0 ORDER BY id LIMIT 1", (sid, role)).fetchone()
            db.execute("UPDATE explore_bonus SET remaining=remaining-1 WHERE id=?", (b["id"],))
        res = {"ok": True, "kind": drop["kind"], "consumed": True, "spot": spot["name"], "text": drop.get("text", "")}
        title, item_name, item_qty, op_id = "", "", 0, 0
        if drop["kind"] == "clue":
            title = drop["title"]
            db.execute("INSERT OR IGNORE INTO explore_clues (show_id, role, spot_id, drop_id, spot_name, title, text, ts) VALUES (?,?,?,?,?,?,?,?)",
                       (sid, role, spot["id"], drop["id"], spot["name"], drop["title"], drop["text"], now))
            res.update(title=title, text=drop["text"])
        elif drop["kind"] == "item":
            item_name, item_qty = drop["item"], drop["qty"]
            cur = db.execute("INSERT INTO phone_admin_ops (show_id, role, kind, name, value, created_at) VALUES (?,?,?,?,?,?)",
                             (sid, role, "item", item_name, str(item_qty), now))
            op_id = cur.lastrowid
            title = f"{item_name} ×{item_qty}"
            res.update(title=title, item={"name": item_name, "qty": item_qty, "op_id": op_id, "status": "pending"})
        else:
            title = "什么也没找到"
            res.update(title=title)
        db.execute("INSERT INTO explore_visits (show_id, role, spot_id, spot_name, day, ts, used, kind, title, text, item_name, item_qty, op_id) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (sid, role, spot["id"], spot["name"], q["day"], now, used, drop["kind"], title, res.get("text", ""), item_name, item_qty, op_id))
        db.commit()
        res["quota"] = quota_state(db, sid, role, st)
        return res, 200


def _item_status(db, op_id):
    if not op_id:
        return ""
    r = db.execute("SELECT done, ok, result FROM phone_admin_ops WHERE id=?", (op_id,)).fetchone()
    if not r:
        return "pending"
    return "pending" if not r["done"] else ("ok" if r["ok"] else "failed")


# ───────────────────────── 玩家端 ─────────────────────────

def _signer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(G["app"].secret_key, salt="explore-auth")


def _current():
    """(show_id, role) 或 None；每次查库，重置激活码/季度结束立即失效；管理员码不能当玩家用"""
    from flask import request
    try:
        code = _signer().loads(request.cookies.get(EXPLORE_COOKIE, ""), max_age=EXPLORE_COOKIE_AGE)
    except Exception:
        return None
    who = G["_phone_code_owner"](G["get_db"](), code) if isinstance(code, str) else None
    return who if who and who[1] != G["PHONE_ADMIN"] else None


def _map_image_url(m):
    from flask import url_for
    return url_for("explore_image", name=m["image"]) if m["image"] else ""


def _maps_payload(db, sid, with_drops=False):
    spots = {}
    for s in db.execute("SELECT * FROM explore_spots WHERE show_id=? ORDER BY sort, id", (sid,)):
        if not with_drops and not s["enabled"]:
            continue
        d = {"id": s["id"], "name": s["name"], "desc": s["desc"], "icon": s["icon"], "x": s["x"], "y": s["y"]}
        if with_drops:
            d.update(enabled=bool(s["enabled"]), drops=json.loads(s["drops"] or "[]"))
        spots.setdefault(s["map_id"], []).append(d)
    return [{"id": m["id"], "name": m["name"], "image": _map_image_url(m), "spots": spots.get(m["id"], [])}
            for m in db.execute("SELECT * FROM explore_maps WHERE show_id=? ORDER BY sort, id", (sid,))]


def _json(obj, status=200):
    from flask import jsonify
    r = jsonify(obj)
    r.status_code = status
    return r


def _player_guard():
    """(who, 错误响应)；JSON 接口用：未登录 401，csrf 不对 403（POST）"""
    from flask import request, session
    import hmac
    who = _current()
    if not who:
        return None, _json({"ok": False, "error": "请先用激活码进入"}, 401)
    if request.method == "POST":
        if not hmac.compare_digest(request.headers.get("X-CSRF", ""), session.get("phone_csrf", "") or "-"):
            return None, _json({"ok": False, "error": "页面过期了，刷新后再试"}, 403)
    return who, None


def entry():
    from flask import request, render_template, redirect, url_for
    if request.method == "POST":
        return _enter(request.form.get("code"))
    if _current():
        return redirect(url_for("explore_home"))
    return render_template("explore.html", mode="entry", error=None)


def _enter(code):
    from flask import render_template, redirect, url_for
    if G["_phone_ip_locked"]():
        return render_template("explore.html", mode="entry", error="输错太多次了，15 分钟后再试"), 429
    code = (code or "").strip().upper()
    who = G["_phone_code_owner"](G["get_db"](), code)
    if not who or who[1] == G["PHONE_ADMIN"]:
        G["_phone_note_fail"]()
        return render_template("explore.html", mode="entry", error=G["_PHONE_BAD_CODE"] if not who else "管理员请在团后台的「探索踩点」里配置"), 404
    resp = redirect(url_for("explore_home"))
    resp.set_cookie(EXPLORE_COOKIE, _signer().dumps(code), max_age=EXPLORE_COOKIE_AGE,
                    httponly=True, samesite="Lax", secure=not G["_phone_local"](), path="/x")
    return resp


def enter_by_code(code):
    """/x/<码>：校验后写 cookie 并跳走，地址栏不留码"""
    return _enter(code)


def home():
    from flask import render_template, redirect, url_for
    who = _current()
    if not who:
        return redirect(url_for("explore_entry"))
    sid, role = who
    return render_template("explore.html", mode="home", role=role, csrf=G["_phone_csrf"](), enabled=get_settings(G["get_db"](), sid)["enabled"])


def logout():
    from flask import redirect, url_for, request, session
    import hmac
    resp = redirect(url_for("explore_entry"))
    if hmac.compare_digest(request.form.get("csrf", ""), session.get("phone_csrf", "") or "-"):
        resp.delete_cookie(EXPLORE_COOKIE, path="/x", httponly=True, samesite="Lax", secure=not G["_phone_local"]())
    return resp


def api_state():
    who, err = _player_guard()
    if err: return err
    sid, role = who
    db = G["get_db"]()
    st = get_settings(db, sid)
    if not st["enabled"]:
        return _json({"ok": True, "enabled": False, "role": role})
    clues = db.execute("SELECT COUNT(*), COALESCE(SUM(1-seen),0) FROM explore_clues WHERE show_id=? AND role=?", (sid, role)).fetchone()
    return _json({"ok": True, "enabled": True, "role": role, "intro": st["intro"], "quota": quota_state(db, sid, role, st),
                  "maps": _maps_payload(db, sid), "clue_count": clues[0], "clue_new": clues[1]})


def api_visit():
    who, err = _player_guard()
    if err: return err
    from flask import request
    sid, role = who
    try:
        spot_id = int((request.get_json(silent=True) or {}).get("spot_id"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "没有选地点"}, 400)
    res, status = do_visit(G["get_db"](), sid, role, spot_id)
    return _json(res, status)


def api_clues():
    who, err = _player_guard()
    if err: return err
    sid, role = who
    db = G["get_db"]()
    rows = db.execute("SELECT c.*, COALESCE(m.name,'') AS map_name FROM explore_clues c "
                      "LEFT JOIN explore_spots s ON s.id=c.spot_id LEFT JOIN explore_maps m ON m.id=s.map_id "
                      "WHERE c.show_id=? AND c.role=? ORDER BY c.ts DESC, c.id DESC", (sid, role)).fetchall()
    return _json({"ok": True, "clues": [{"id": r["id"], "title": r["title"], "text": r["text"], "spot": r["spot_name"],
                                         "map": r["map_name"], "ts": r["ts"], "new": not r["seen"]} for r in rows]})


def api_clues_seen():
    who, err = _player_guard()
    if err: return err
    sid, role = who
    db = G["get_db"]()
    db.execute("UPDATE explore_clues SET seen=1 WHERE show_id=? AND role=?", (sid, role))
    db.commit()
    return _json({"ok": True})


def api_log():
    who, err = _player_guard()
    if err: return err
    sid, role = who
    db = G["get_db"]()
    rows = db.execute("SELECT * FROM explore_visits WHERE show_id=? AND role=? ORDER BY id DESC LIMIT 60", (sid, role)).fetchall()
    return _json({"ok": True, "log": [{"ts": r["ts"], "spot": r["spot_name"], "kind": r["kind"], "title": r["title"], "text": r["text"],
                                       "used": r["used"], "item_status": _item_status(db, r["op_id"]) if r["kind"] == "item" else ""} for r in rows]})


def image(name):
    from flask import send_from_directory, abort
    if not name.replace(".", "").replace("_", "").isalnum() or ".." in name:
        abort(404)
    resp = send_from_directory(EXPLORE_IMAGE_DIR, name, mimetype="image/jpeg", max_age=86400)
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


# ───────────────────────── 管理端（团后台，require_admin） ─────────────────────────

def _admin_guard():
    """JSON 接口：POST 要带 X-CSRF（页面里的 session token）"""
    from flask import request, session
    import hmac
    if request.method == "POST" and not hmac.compare_digest(request.headers.get("X-CSRF", ""), session.get("phone_csrf", "") or "-"):
        return _json({"ok": False, "error": "页面过期了，刷新后再试"}, 403)
    return None


def _body():
    from flask import request
    return request.get_json(silent=True) or {}


def admin_page():
    from flask import render_template
    return render_template("explore_admin.html", csrf=G["_phone_csrf"]())


def admin_state():
    sid, db = G["get_show_id"](), G["get_db"]()
    st = get_settings(db, sid)
    plug = G["_plugin_status"](db, sid)
    roles = []
    for r in G["_admin_role_list"](db, sid):
        if r == "*":
            continue
        q = quota_state(db, sid, r, st)
        roles.append({"role": r, "daily_limit": q["daily_limit"], "custom": q["daily_custom"], "used_today": q["daily_used"],
                      "left_today": q["daily_left"], "bonus": q["bonus"]})
    return _json({"ok": True, "settings": st, "day": _day_key(st["reset_hour"]), "maps": _maps_payload(db, sid, with_drops=True), "roles": roles,
                  "items": [{"group": g, "names": ns} for g, ns in G["_admin_grant_item_names"](db, sid)],
                  "plugin": {"text": plug.get("text"), "can_items": bool(plug.get("can")), "has_catalog": plug.get("catalog") is not None}})


def admin_settings():
    err = _admin_guard()
    if err: return err
    b = _body()
    try:
        daily, hour = int(b.get("default_daily")), int(b.get("reset_hour", 0))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "次数和刷新时间要填整数"}, 400)
    if not (0 <= daily <= 99 and 0 <= hour <= 23):
        return _json({"ok": False, "error": "每天次数 0~99，刷新时间 0~23 点"}, 400)
    sid, db = G["get_show_id"](), G["get_db"]()
    db.execute("INSERT INTO explore_settings (show_id, enabled, default_daily, reset_hour, intro) VALUES (?,?,?,?,?) "
               "ON CONFLICT(show_id) DO UPDATE SET enabled=excluded.enabled, default_daily=excluded.default_daily, "
               "reset_hour=excluded.reset_hour, intro=excluded.intro",
               (sid, 1 if b.get("enabled") else 0, daily, hour, str(b.get("intro") or "").strip()[:300]))
    db.commit()
    return _json({"ok": True})


def admin_map_save():
    err = _admin_guard()
    if err: return err
    b = _body()
    name = str(b.get("name") or "").strip()[:30]
    if not name:
        return _json({"ok": False, "error": "地图要有名字"}, 400)
    sid, db = G["get_show_id"](), G["get_db"]()
    if b.get("id"):
        if not db.execute("SELECT 1 FROM explore_maps WHERE id=? AND show_id=?", (b["id"], sid)).fetchone():
            return _json({"ok": False, "error": "找不到这张地图"}, 404)
        db.execute("UPDATE explore_maps SET name=? WHERE id=?", (name, b["id"]))
        mid = int(b["id"])
    else:
        mid = db.execute("INSERT INTO explore_maps (show_id, name, sort) VALUES (?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM explore_maps WHERE show_id=?))",
                         (sid, name, sid)).lastrowid
    db.commit()
    return _json({"ok": True, "id": mid})


def admin_map_image(mid):
    err = _admin_guard()
    if err: return err
    from flask import request
    sid, db = G["get_show_id"](), G["get_db"]()
    m = db.execute("SELECT * FROM explore_maps WHERE id=? AND show_id=?", (mid, sid)).fetchone()
    f = request.files.get("image")
    if not m or not f:
        return _json({"ok": False, "error": "没有收到图片"}, 400)
    raw = f.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        return _json({"ok": False, "error": "图片太大（上限 12MB）"}, 400)
    try:
        full = G["_moment_process"](raw)[0]
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)
    os.makedirs(EXPLORE_IMAGE_DIR, exist_ok=True)
    name = f"m{mid}_{secrets.token_hex(6)}.jpg"
    with open(os.path.join(EXPLORE_IMAGE_DIR, name), "wb") as fh:
        fh.write(full)
    if m["image"]:
        try: os.remove(os.path.join(EXPLORE_IMAGE_DIR, m["image"]))
        except OSError: pass
    db.execute("UPDATE explore_maps SET image=? WHERE id=?", (name, mid))
    db.commit()
    return _json({"ok": True, "image": _map_image_url({"image": name})})


def admin_map_delete():
    err = _admin_guard()
    if err: return err
    sid, db = G["get_show_id"](), G["get_db"]()
    mid = _body().get("id")
    m = db.execute("SELECT * FROM explore_maps WHERE id=? AND show_id=?", (mid, sid)).fetchone()
    if not m:
        return _json({"ok": False, "error": "找不到这张地图"}, 404)
    db.execute("DELETE FROM explore_spots WHERE map_id=? AND show_id=?", (mid, sid))
    db.execute("DELETE FROM explore_maps WHERE id=?", (mid,))
    db.commit()
    if m["image"]:
        try: os.remove(os.path.join(EXPLORE_IMAGE_DIR, m["image"]))
        except OSError: pass
    return _json({"ok": True})


def admin_spot_save():
    err = _admin_guard()
    if err: return err
    b = _body()
    sid, db = G["get_show_id"](), G["get_db"]()
    name = str(b.get("name") or "").strip()[:30]
    if not name:
        return _json({"ok": False, "error": "地点要有名字"}, 400)
    if not db.execute("SELECT 1 FROM explore_maps WHERE id=? AND show_id=?", (b.get("map_id"), sid)).fetchone():
        return _json({"ok": False, "error": "找不到这张地图"}, 404)
    try:
        x, y = float(b.get("x", 50)), float(b.get("y", 50))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "位置不对"}, 400)
    x, y = min(100.0, max(0.0, x)), min(100.0, max(0.0, y))
    plug = G["_plugin_status"](db, sid)
    names = {n for _, ns in G["_admin_grant_item_names"](db, sid) for n in ns}
    drops, derr = _clean_drops(b.get("drops") or [], names)
    if derr:
        return _json({"ok": False, "error": derr}, 400)
    vals = (int(b["map_id"]), name, str(b.get("desc") or "").strip()[:200], str(b.get("icon") or "📍").strip()[:8] or "📍",
            x, y, 1 if b.get("enabled", True) else 0, json.dumps(drops, ensure_ascii=False))
    if b.get("id"):
        if not db.execute("SELECT 1 FROM explore_spots WHERE id=? AND show_id=?", (b["id"], sid)).fetchone():
            return _json({"ok": False, "error": "找不到这个地点"}, 404)
        db.execute("UPDATE explore_spots SET map_id=?, name=?, desc=?, icon=?, x=?, y=?, enabled=?, drops=? WHERE id=?", vals + (b["id"],))
        spot_id = int(b["id"])
    else:
        spot_id = db.execute("INSERT INTO explore_spots (map_id, name, desc, icon, x, y, enabled, drops, show_id, sort) "
                             "VALUES (?,?,?,?,?,?,?,?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM explore_spots WHERE show_id=?))",
                             vals + (sid, sid)).lastrowid
    db.commit()
    return _json({"ok": True, "id": spot_id, "drops": drops, "warn": "" if plug.get("can") or not any(d["kind"] == "item" for d in drops)
                  else "插件版本太旧，物品暂时发不出去（掉落时会跳过物品）"})


def admin_spot_delete():
    err = _admin_guard()
    if err: return err
    sid, db = G["get_show_id"](), G["get_db"]()
    db.execute("DELETE FROM explore_spots WHERE id=? AND show_id=?", (_body().get("id"), sid))
    db.commit()
    return _json({"ok": True})


def admin_quota():
    """单人每天次数：daily=None 恢复默认"""
    err = _admin_guard()
    if err: return err
    b = _body()
    sid, db = G["get_show_id"](), G["get_db"]()
    roles = [r for r in (b.get("roles") or [b.get("role")]) if r in set(G["_admin_role_list"](db, sid))]
    if not roles:
        return _json({"ok": False, "error": "先选人"}, 400)
    if b.get("daily") is None:
        for r in roles:
            db.execute("DELETE FROM explore_quota WHERE show_id=? AND role=?", (sid, r))
    else:
        try:
            n = int(b["daily"])
        except (TypeError, ValueError):
            return _json({"ok": False, "error": "次数要填整数"}, 400)
        if not 0 <= n <= 99:
            return _json({"ok": False, "error": "每天次数 0~99"}, 400)
        for r in roles:
            db.execute("INSERT INTO explore_quota (show_id, role, daily) VALUES (?,?,?) ON CONFLICT(show_id, role) DO UPDATE SET daily=excluded.daily", (sid, r, n))
    db.commit()
    return _json({"ok": True, "n": len(roles)})


def admin_bonus():
    """临时次数：给选中的人各加 amount 次（用完日常次数后才消耗，不过期；amount 可为负 = 扣掉他现有的临时次数）"""
    err = _admin_guard()
    if err: return err
    b = _body()
    sid, db = G["get_show_id"](), G["get_db"]()
    roles = [r for r in (b.get("roles") or []) if r in set(G["_admin_role_list"](db, sid))]
    try:
        n = int(b.get("amount"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "次数要填整数"}, 400)
    if not roles:
        return _json({"ok": False, "error": "先选人"}, 400)
    if n == 0 or abs(n) > 99:
        return _json({"ok": False, "error": "次数 1~99（扣除填负数）"}, 400)
    now = _now_ms()
    for r in roles:
        if n > 0:
            db.execute("INSERT INTO explore_bonus (show_id, role, amount, remaining, note, created_at) VALUES (?,?,?,?,?,?)",
                       (sid, r, n, n, str(b.get("note") or "").strip()[:60], now))
        else:
            need = -n
            for row in db.execute("SELECT id, remaining FROM explore_bonus WHERE show_id=? AND role=? AND remaining>0 ORDER BY id DESC", (sid, r)).fetchall():
                take = min(need, row["remaining"])
                db.execute("UPDATE explore_bonus SET remaining=remaining-? WHERE id=?", (take, row["id"]))
                need -= take
                if need <= 0:
                    break
    db.commit()
    return _json({"ok": True, "n": len(roles)})


def admin_log():
    sid, db = G["get_show_id"](), G["get_db"]()
    rows = db.execute("SELECT * FROM explore_visits WHERE show_id=? ORDER BY id DESC LIMIT 200", (sid,)).fetchall()
    return _json({"ok": True, "log": [{"ts": r["ts"], "role": r["role"], "spot": r["spot_name"], "kind": r["kind"], "title": r["title"],
                                       "used": r["used"], "item_status": _item_status(db, r["op_id"]) if r["kind"] == "item" else ""} for r in rows]})


def register(ns):
    for k in _NAMES:
        G[k] = ns[k]
    app = G["app"]
    R = app.add_url_rule
    adm = G["require_admin"]
    R("/x", "explore_entry", entry, methods=["GET", "POST"])
    R("/x/home", "explore_home", home)
    R("/x/logout", "explore_logout", logout, methods=["POST"])
    R("/x/img/<name>", "explore_image", image)
    R("/x/api/state", "explore_api_state", api_state)
    R("/x/api/visit", "explore_api_visit", api_visit, methods=["POST"])
    R("/x/api/clues", "explore_api_clues", api_clues)
    R("/x/api/clues/seen", "explore_api_clues_seen", api_clues_seen, methods=["POST"])
    R("/x/api/log", "explore_api_log", api_log)
    R("/x/<code>", "explore_enter_code", enter_by_code)   # 放最后：具体路径优先
    R("/admin/explore", "admin_explore", adm(admin_page))
    R("/admin/explore/api/state", "admin_explore_state", adm(admin_state))
    R("/admin/explore/api/settings", "admin_explore_settings", adm(admin_settings), methods=["POST"])
    R("/admin/explore/api/map", "admin_explore_map", adm(admin_map_save), methods=["POST"])
    R("/admin/explore/api/map/<int:mid>/image", "admin_explore_map_image", adm(admin_map_image), methods=["POST"])
    R("/admin/explore/api/map/delete", "admin_explore_map_delete", adm(admin_map_delete), methods=["POST"])
    R("/admin/explore/api/spot", "admin_explore_spot", adm(admin_spot_save), methods=["POST"])
    R("/admin/explore/api/spot/delete", "admin_explore_spot_delete", adm(admin_spot_delete), methods=["POST"])
    R("/admin/explore/api/quota", "admin_explore_quota", adm(admin_quota), methods=["POST"])
    R("/admin/explore/api/bonus", "admin_explore_bonus", adm(admin_bonus), methods=["POST"])
    R("/admin/explore/api/log", "admin_explore_log", adm(admin_log))

    @app.after_request
    def _explore_headers(resp):
        from flask import request
        if request.path == "/x" or request.path.startswith("/x/"):
            if not resp.headers.get("Cache-Control") or "max-age" not in resp.headers.get("Cache-Control", ""):
                resp.headers["Cache-Control"] = "no-store"
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["X-Robots-Tag"] = "noindex"
        return resp
