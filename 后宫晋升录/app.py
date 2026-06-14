"""
后宫晋升录 · Web 后端
Flask + SQLite
职责：花名册（只读）、宫廷公报（只读）、陷害面板、夺嫡、结盟、书信、秘密
"""

import sqlite3, json, os, random, string
from datetime import datetime
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, g)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hougong_secret_change_me")

DB_PATH = os.path.join(os.path.dirname(__file__), "hougong.db")

# ─── 陷害方案定义 ──────────────────────────────────────────────
INTRIGUE_METHODS = {
    "吹枕边风": {"scheme_req": 10, "silver": 0,   "favor": 80,  "desc": "目标宠爱-30，1天侍寝-30%"},
    "诬告":     {"scheme_req": 20, "silver": 0,   "favor": 100, "desc": "目标德行-20，威严-30"},
    "下毒":     {"scheme_req": 30, "silver": 0,   "favor": 150, "desc": "目标健康-30~50"},
    "构陷失宠": {"scheme_req": 25, "silver": 0,   "favor": 200, "desc": "目标宠爱归零，威严-40"},
    "截财":     {"scheme_req": 30, "silver": 0,   "favor": 250, "desc": "针对NPC，自动获宠效果-50%，持续2天"},
    "落胎":     {"scheme_req": 40, "silver": 0,   "favor": 300, "desc": "目标孕期专属，强制流产，健康-50"},
}

# ─── 数据库 ────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), "r", encoding="utf-8") as f:
        get_db().executescript(f.read())
    get_db().commit()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur

# ─── 工具 ──────────────────────────────────────────────────────
RANK_ORDER = {
    "秀女":0,"答应":1,"常在":2,"贵人":3,
    "嫔":4,"妃":5,"贵妃":6,"皇贵妃":7,"皇后":8
}

RANK_SLOTS = {
    "皇后":1,"皇贵妃":1,"贵妃":2,"妃":4,
    "嫔":6,"贵人":"∞","常在":"∞","答应":"∞","秀女":"∞"
}

def get_game_state():
    row = query("SELECT * FROM game_state WHERE id=1", one=True)
    return dict(row) if row else {}

def get_concubine_by_qq(qq):
    row = query("SELECT * FROM concubines WHERE qq=?", (qq,), one=True)
    return dict(row) if row else None

def get_all_concubines():
    rows = query("SELECT * FROM concubines WHERE status NOT IN ('dead','eliminated') ORDER BY rank_order DESC, sacred_favor DESC")
    return [dict(r) for r in rows]

def get_all_npcs():
    rows = query("SELECT * FROM npc_concubines WHERE is_alive=1 ORDER BY rank_order DESC")
    return [dict(r) for r in rows]

def get_heirs(mother_qq=None):
    if mother_qq:
        rows = query("SELECT * FROM heirs WHERE mother_qq=? ORDER BY born_day", (mother_qq,))
    else:
        rows = query("SELECT * FROM heirs WHERE is_alive=1 AND gender='皇子' ORDER BY prestige_score DESC")
    return [dict(r) for r in rows]

def hp_bar(val, max_val=100, length=10):
    filled = round(max(0, min(1, val / max_val)) * length)
    return "█" * filled + "░" * (length - filled)

def current_day():
    gs = get_game_state()
    return gs.get("day_num", 0)

# ─── 登录 ──────────────────────────────────────────────────────
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        qq   = (request.form.get("qq")   or "").strip().replace(" ", "")
        name = (request.form.get("name") or "").strip()
        player = get_concubine_by_qq(qq)
        if not player or player["name"] != name:
            return render_template("login.html", error="QQ号或角色名有误，请确认。")
        session["qq"]   = qq
        session["name"] = name
        return redirect(url_for("intrigue"))
    return render_template("login.html", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "qq" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─── 花名册（只读）────────────────────────────────────────────
@app.route("/")
def index():
    gs      = get_game_state()
    players = get_all_concubines()
    npcs    = get_all_npcs()
    rumors  = query(
        "SELECT content FROM daily_log WHERE log_type='rumor' AND day_num=? ORDER BY id DESC LIMIT 3",
        (gs.get("day_num", 0),)
    )
    rumors = [dict(r) for r in rumors]
    return render_template("index.html", gs=gs, players=players, npcs=npcs,
                           slot_info=RANK_SLOTS, rumors=rumors)

# ─── 宫廷公报（只读）──────────────────────────────────────────
@app.route("/gazette")
def gazette():
    gs         = get_game_state()
    day_filter = request.args.get("day", type=int)
    day_list   = [r[0] for r in query("SELECT DISTINCT day_num FROM daily_log ORDER BY day_num DESC LIMIT 30")]
    if day_filter:
        logs = query("SELECT * FROM daily_log WHERE day_num=? ORDER BY id DESC", (day_filter,))
    else:
        logs = query("SELECT * FROM daily_log ORDER BY day_num DESC, id DESC LIMIT 200")
    logs = [dict(r) for r in logs]
    return render_template("gazette.html", gs=gs, logs=logs, day_list=day_list, day_filter=day_filter)

# ─── 陷害面板 ──────────────────────────────────────────────────
@app.route("/intrigue", methods=["GET"])
@login_required
def intrigue():
    qq   = session["qq"]
    me   = get_concubine_by_qq(qq)
    if not me:
        return redirect(url_for("logout"))
    gs   = get_game_state()
    # 合并目标列表
    targets = []
    for p in get_all_concubines():
        if p["qq"] != qq:
            targets.append({"name": p["name"], "rank": p["rank"],
                            "qq": p["qq"], "npc_id": None})
    for n in get_all_npcs():
        targets.append({"name": n["name"], "rank": n["rank"],
                        "qq": None, "npc_id": n["id"]})
    queue = query(
        "SELECT * FROM intrigue_queue WHERE attacker_qq=? AND status='pending' ORDER BY submitted_at DESC",
        (qq,)
    )
    queue = [dict(r) for r in queue]
    history = query(
        "SELECT * FROM intrigue_queue WHERE attacker_qq=? AND status='executed' ORDER BY executed_at DESC LIMIT 20",
        (qq,)
    )
    history = [dict(r) for r in history]
    pending = len(queue) > 0
    return render_template("intrigue.html",
        gs=gs, me=me, targets=targets,
        methods=INTRIGUE_METHODS,
        methods_json=json.dumps(INTRIGUE_METHODS),
        queue=queue, history=history, pending=pending)

@app.route("/intrigue/submit", methods=["POST"])
@login_required
def intrigue_submit():
    qq     = session["qq"]
    player = get_concubine_by_qq(qq)
    if not player:
        return jsonify({"ok": False, "msg": "角色不存在"})

    gs = get_game_state()
    if gs.get("game_phase") == "ended":
        return jsonify({"ok": False, "msg": "游戏已结束"})

    data        = request.get_json(force=True)
    method      = data.get("method", "")
    target_qq   = data.get("target_qq")   # 玩家目标
    target_npc  = data.get("target_npc_id")  # NPC id（字符串）
    weapon      = int(data.get("weapon_bonus", 0))

    if method not in INTRIGUE_METHODS:
        return jsonify({"ok": False, "msg": "无效手段"})
    m = INTRIGUE_METHODS[method]

    # 确定目标
    if target_qq:
        target = get_concubine_by_qq(target_qq)
        if not target:
            return jsonify({"ok": False, "msg": "目标不存在"})
        t_name  = target["name"]
        t_npc   = None
        # 落胎检查
        if method == "落胎" and target["status"] != "pregnant":
            return jsonify({"ok": False, "msg": "落胎仅对孕期目标有效"})
    elif target_npc:
        npc_id = int(target_npc)
        npc = query("SELECT * FROM npc_concubines WHERE id=? AND is_alive=1", (npc_id,), one=True)
        if not npc:
            return jsonify({"ok": False, "msg": "目标NPC不存在"})
        t_name = dict(npc)["name"] + dict(npc)["title"]
        t_npc  = npc_id
        target_qq = None
        if method == "落胎":
            return jsonify({"ok": False, "msg": "落胎不可对NPC使用"})
    else:
        return jsonify({"ok": False, "msg": "请选择目标"})

    # 消耗检查
    if player["scheme"] < m["scheme_req"]:
        return jsonify({"ok": False, "msg": f"心计不足，需{m['scheme_req']}（当前{player['scheme']:.0f}）"})
    if player["silver"] < m["silver"]:
        return jsonify({"ok": False, "msg": f"银两不足，需{m['silver']}两"})
    if player["sacred_favor"] < m["favor"]:
        return jsonify({"ok": False, "msg": f"圣宠不足，需{m['favor']}（当前{player['sacred_favor']}）"})

    # 每天同一目标同一手段限一次
    existing = query(
        "SELECT id FROM intrigue_queue WHERE attacker_qq=? AND target_qq=? AND method=? AND execute_day=? AND status='pending'",
        (qq, target_qq or "", method, gs.get("day_num", 0) + 1), one=True
    )
    if existing:
        return jsonify({"ok": False, "msg": "今日已对该目标使用过此手段，明日再来。"})

    # 扣费
    execute("UPDATE concubines SET silver=silver-?, sacred_favor=sacred_favor-?, updated_at=? WHERE qq=?",
            (m["silver"], m["favor"], datetime.now().isoformat(), qq))

    # 写入队列
    execute("""INSERT INTO intrigue_queue
               (attacker_qq,attacker_name,target_qq,target_npc_id,target_name,
                method,weapon_bonus,cost_scheme,cost_silver,cost_favor,execute_day)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (qq, player["name"], target_qq, t_npc, t_name,
             method, weapon, m["scheme_req"], m["silver"], m["favor"],
             gs.get("day_num", 0) + 1))

    return jsonify({"ok": True, "msg": f"已提交「{method}」针对{t_name}，将于下次日结算执行。"})

@app.route("/intrigue/cancel/<int:item_id>", methods=["POST"])
@login_required
def intrigue_cancel(item_id):
    qq = session["qq"]
    row = query("SELECT * FROM intrigue_queue WHERE id=? AND attacker_qq=? AND status='pending'",
                (item_id, qq), one=True)
    if not row:
        return jsonify({"ok": False, "msg": "找不到该记录或已执行"})
    row = dict(row)
    # 退还消耗
    execute("UPDATE concubines SET silver=silver+?, sacred_favor=sacred_favor+?, updated_at=? WHERE qq=?",
            (row["cost_silver"], row["cost_favor"], datetime.now().isoformat(), qq))
    execute("UPDATE intrigue_queue SET status='cancelled' WHERE id=?", (item_id,))
    return jsonify({"ok": True, "msg": "已取消，已退还银两/圣宠。"})


# ─── 秘密 ──────────────────────────────────────────────────────
@app.route("/secret")
@login_required
def secret_page():
    qq     = session["qq"]
    player = get_concubine_by_qq(qq)
    gs     = get_game_state()
    sec    = query("SELECT * FROM secrets WHERE qq=?", (qq,), one=True)
    return render_template("secret.html", gs=gs, player=player,
                           secret=dict(sec) if sec else None)

@app.route("/secret/confess", methods=["POST"])
@login_required
def secret_confess():
    qq     = session["qq"]
    player = get_concubine_by_qq(qq)
    sec    = query("SELECT * FROM secrets WHERE qq=? AND confessed=0", (qq,), one=True)
    if not sec:
        return jsonify({"ok": False, "msg": "无秘密可坦白，或已坦白过。"})
    sec = dict(sec)
    if sec["secret_type"] == "无秘密":
        return jsonify({"ok": False, "msg": "你本无秘密，无需坦白。"})
    day = current_day()
    execute("UPDATE secrets SET confessed=1, confessed_day=? WHERE qq=?", (day, qq))
    # 坦白奖励：惩罚减半，宠爱+30
    execute("UPDATE concubines SET love=MIN(100, love+30), updated_at=? WHERE qq=?",
            (datetime.now().isoformat(), qq))
    execute("""INSERT INTO daily_log (day_num,log_type,title,content,affected,is_major)
               VALUES(?,?,?,?,?,?)""",
            (day, "secret", "秘密坦白",
             f"{player['name']}向皇上坦白了秘密：{sec['secret_type']}，诚意感人，宠爱+30。",
             qq, 0))
    return jsonify({"ok": True, "msg": f"已坦白「{sec['secret_type']}」，惩罚减半，宠爱+30。"})

# ─── 夺嫡 ──────────────────────────────────────────────────────
@app.route("/heirs")
def heirs_page():
    qq  = session.get("qq")
    gs  = get_game_state()
    all_alive = query("SELECT * FROM heirs WHERE is_alive=1 ORDER BY prestige_score DESC")
    all_alive = [dict(r) for r in all_alive]
    for h in all_alive:
        if h["mother_qq"]:
            m = get_concubine_by_qq(h["mother_qq"])
            h["mother_rank"]       = m["rank"] if m else "秀女"
            h["mother_rank_order"] = RANK_ORDER.get(h["mother_rank"], 0)
        else:
            h["mother_rank"]       = "在位NPC"
            h["mother_rank_order"] = 3
        rank_bonus        = h["mother_rank_order"] * 5
        h["total_score"]  = h["talent"] * 0.4 + h["prestige_score"] * 0.3 + rank_bonus * 0.2
    princes    = sorted([h for h in all_alive if h["gender"] == "皇子"],
                        key=lambda x: x["total_score"], reverse=True)
    princesses = [h for h in all_alive if h["gender"] == "公主"]
    player     = get_concubine_by_qq(qq) if qq else None
    return render_template("heirs.html",
        gs=gs, princes=princes, princesses=princesses, player=player)

@app.route("/heirs/support", methods=["POST"])
@login_required
def heirs_support():
    qq     = session["qq"]
    player = get_concubine_by_qq(qq)
    gs     = get_game_state()
    if gs.get("game_phase") not in ("dying", "ended"):
        return jsonify({"ok": False, "msg": "夺嫡尚未开始（皇上弥留时开放）"})
    data    = request.get_json(force=True)
    heir_id = int(data.get("heir_id", 0))
    amount  = int(data.get("silver", data.get("amount", 0)))
    if amount <= 0:
        return jsonify({"ok": False, "msg": "请输入有效金额"})
    if player["silver"] < amount:
        return jsonify({"ok": False, "msg": f"银两不足（当前{player['silver']}两）"})
    heir = query("SELECT * FROM heirs WHERE id=? AND is_alive=1 AND gender='皇子'",
                 (heir_id,), one=True)
    if not heir:
        return jsonify({"ok": False, "msg": "皇子不存在"})
    execute("UPDATE concubines SET silver=silver-?, updated_at=? WHERE qq=?",
            (amount, datetime.now().isoformat(), qq))
    execute("UPDATE heirs SET support_silver=support_silver+?, prestige_score=prestige_score+? WHERE id=?",
            (amount, amount * 0.1, heir_id))
    return jsonify({"ok": True, "msg": f"已投入{amount}两支持{dict(heir)['name']}皇子。"})

# ─── 海豹同步接口（内部）──────────────────────────────────────
@app.route("/api/sync", methods=["POST"])
def api_sync():
    """海豹插件日结算后调用，批量写入玩家数据"""
    auth = request.headers.get("X-Sync-Key", "")
    if auth != os.environ.get("SYNC_KEY", "hougong_sync_key"):
        return jsonify({"ok": False, "msg": "unauthorized"}), 401
    data = request.get_json(force=True)

    # 同步玩家
    for p in data.get("players", []):
        existing = get_concubine_by_qq(p["qq"])
        if existing:
            execute("""UPDATE concubines SET
                name=?,title=?,rank=?,rank_order=?,age=?,
                appearance=?,talent=?,scheme=?,health=?,virtue=?,
                sacred_favor=?,love=?,prestige=?,silver=?,stamina=?,stamina_max=?,
                status=?,pregnant_day=?,love_stage=?,low_love_days=?,
                bedridden_days=?,prestige_warning=?,updated_at=?
                WHERE qq=?""",
                (p.get("name"), p.get("title",""), p.get("rank"), p.get("rank_order",0),
                 p.get("age",14), p.get("appearance",50), p.get("talent",20),
                 p.get("scheme",20), p.get("health",70), p.get("virtue",30),
                 p.get("sacred_favor",0), p.get("love",0),
                 p.get("prestige",0), p.get("silver",0), p.get("stamina",100),
                 p.get("stamina_max",100), p.get("status","normal"),
                 p.get("pregnant_day",0), p.get("love_stage","陌路"),
                 p.get("low_love_days",0), p.get("bedridden_days",0),
                 p.get("prestige_warning",0), datetime.now().isoformat(), p["qq"]))
        else:
            execute("""INSERT OR IGNORE INTO concubines
                (qq,name,title,rank,rank_order,family_tier,family_type,personality,
                 age,appearance,talent,scheme,health,virtue,
                 sacred_favor,love,prestige,silver,stamina,stamina_max,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["qq"],p.get("name"),p.get("title",""),p.get("rank","秀女"),
                 p.get("rank_order",0),p.get("family_tier",1),
                 p.get("family_type",""),p.get("personality",""),
                 p.get("age",14),p.get("appearance",50),p.get("talent",20),
                 p.get("scheme",20),p.get("health",70),p.get("virtue",30),
                 p.get("sacred_favor",0),p.get("love",0),
                 p.get("prestige",0),p.get("silver",0),p.get("stamina",100),
                 p.get("stamina_max",100),p.get("status","normal")))

    # 同步玩家秘密（Seal端注册时生成，随玩家数据一并推送）
    for p in data.get("players", []):
        if not p.get("secret_type"):
            continue
        existing_sec = query("SELECT id FROM secrets WHERE qq=?", (p["qq"],), one=True)
        if not existing_sec:
            execute("""INSERT OR IGNORE INTO secrets (qq, secret_type, penalty_desc, is_revealed)
                       VALUES (?, ?, ?, ?)""",
                    (p["qq"], p["secret_type"], p.get("secret_penalty", ""),
                     1 if p.get("secret_revealed") else 0))
        else:
            execute("""UPDATE secrets SET is_revealed=? WHERE qq=? AND is_revealed=0""",
                    (1 if p.get("secret_revealed") else 0, p["qq"]))

    # 同步NPC
    for n in data.get("npcs", []):
        execute("""INSERT OR REPLACE INTO npc_concubines
            (id,name,title,rank,rank_order,age,appearance,talent,scheme,health,virtue,
             love,prestige,sacred_favor,behavior,attend_priority,intrigue_chance,
             is_alive,pregnant_day,sons_count)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (n["id"],n["name"],n.get("title",""),n["rank"],n.get("rank_order",0),
             n.get("age",20),n.get("appearance",60),n.get("talent",50),
             n.get("scheme",50),n.get("health",70),n.get("virtue",40),
             n.get("love",50),n.get("prestige",100),n.get("sacred_favor",0),
             n.get("behavior","defensive"),n.get("attend_priority",5),
             n.get("intrigue_chance",0),1 if n.get("is_alive",True) else 0,
             n.get("pregnant_day",0),n.get("sons_count",0)))

    # 同步游戏状态
    gs = data.get("game_state")
    if gs:
        execute("""INSERT OR REPLACE INTO game_state
            (id,day_num,emperor_health,emperor_stage,emperor_mood,emperor_pref,
             favored_qq,favored_name,game_phase,attend_slots,attend_slots_max,season,last_settlement)
            VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (gs.get("day_num",0),gs.get("emperor_health",100),
             gs.get("emperor_stage","龙体康健"),gs.get("emperor_mood","平和"),
             gs.get("emperor_pref",""),gs.get("favored_qq"),gs.get("favored_name"),
             gs.get("game_phase","active"),gs.get("attend_slots",5),
             gs.get("attend_slots_max",5),gs.get("season","春"),
             gs.get("last_settlement")))

    # 写入日志
    for log in data.get("logs", []):
        execute("""INSERT INTO daily_log (day_num,log_type,title,content,affected,is_major)
                   VALUES(?,?,?,?,?,?)""",
                (log.get("day_num",0),log.get("log_type","event"),
                 log.get("title",""),log.get("content",""),
                 log.get("affected",""),1 if log.get("is_major") else 0))

    # 同步子嗣
    for h in data.get("heirs", []):
        existing = query("SELECT id FROM heirs WHERE id=?", (h["id"],), one=True)
        if not existing:
            execute("""INSERT OR IGNORE INTO heirs
                (id,mother_qq,mother_npc_id,mother_name,name,gender,age,talent,
                 prestige_score,support_silver,health,is_alive,stage,born_day)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (h["id"],h.get("mother_qq"),h.get("mother_npc_id"),
                 h.get("mother_name",""),h.get("name",""),h.get("gender","皇子"),
                 h.get("age",0),h.get("talent",20),h.get("prestige_score",0),
                 h.get("support_silver",0),h.get("health",80),
                 1 if h.get("is_alive",True) else 0,
                 h.get("stage","幼年"),h.get("born_day",1)))
        else:
            execute("""UPDATE heirs SET age=?,talent=?,prestige_score=?,
                health=?,is_alive=?,stage=? WHERE id=?""",
                (h.get("age",0),h.get("talent",20),h.get("prestige_score",0),
                 h.get("health",80),1 if h.get("is_alive",True) else 0,
                 h.get("stage","幼年"),h["id"]))

    # 执行陷害队列（日结算调用时触发）
    if data.get("execute_intrigue"):
        _execute_intrigue_queue(gs.get("day_num",0) if gs else 0)

    return jsonify({"ok": True})

def _execute_intrigue_queue(day_num):
    """执行当天的陷害队列"""
    pending = query(
        "SELECT * FROM intrigue_queue WHERE status='pending' AND execute_day<=?",
        (day_num,)
    )
    for row in pending:
        row = dict(row)
        _apply_intrigue(row, day_num)

def _apply_intrigue(row, day_num):
    method         = row["method"]
    attacker_qq    = row["attacker_qq"]
    attacker_name  = row["attacker_name"]
    target_qq      = row["target_qq"]
    target_npc_id  = row["target_npc_id"]
    weapon_bonus   = row.get("weapon_bonus", 0)

    attacker = get_concubine_by_qq(attacker_qq)
    if not attacker:
        execute("UPDATE intrigue_queue SET status='executed',result='fail',result_detail='攻击者已不存在',executed_at=? WHERE id=?",
                (datetime.now().isoformat(), row["id"]))
        return

    # 目标
    if target_qq:
        target = get_concubine_by_qq(target_qq)
        if not target or target["status"] in ("dead","eliminated"):
            execute("UPDATE intrigue_queue SET status='executed',result='fail',result_detail='目标已不存在',executed_at=? WHERE id=?",
                    (datetime.now().isoformat(), row["id"]))
            return
        t_scheme = target["scheme"]
        t_table  = "concubines"
        t_where  = f"qq='{target_qq}'"
    elif target_npc_id:
        npc = query("SELECT * FROM npc_concubines WHERE id=?", (target_npc_id,), one=True)
        if not npc or not dict(npc)["is_alive"]:
            execute("UPDATE intrigue_queue SET status='executed',result='fail',result_detail='目标NPC不存在',executed_at=? WHERE id=?",
                    (datetime.now().isoformat(), row["id"]))
            return
        target   = dict(npc)
        t_scheme = target["scheme"]
        t_table  = "npc_concubines"
        t_where  = f"id={target_npc_id}"
    else:
        return

    # 发现率
    a_scheme    = attacker["scheme"]
    discover_p  = max(0.05, 0.35 - (a_scheme - t_scheme) * 0.003) - weapon_bonus * 0.01
    discovered  = random.random() < discover_p

    ts = datetime.now().isoformat()
    if discovered:
        # 攻击者受惩罚
        penalties = {
            "吹枕边风":   ("sacred_favor", -30),
            "诬告":       ("prestige",     -40),
            "下毒":       ("health",       -20),
            "构陷失宠":   ("sacred_favor", -200),
            "截财":       ("prestige",     -50),
            "落胎":       ("health",       -30),
        }
        col, val = penalties.get(method, ("sacred_favor", -30))
        execute(f"UPDATE concubines SET {col}=MAX(0,{col}+?),updated_at=? WHERE qq=?",
                (val, ts, attacker_qq))
        detail = f"被目标{row['target_name']}发现！遭受反制。"
        result = "found"
        # NPC反击
        if target_npc_id and t_scheme >= 70:
            execute("UPDATE concubines SET prestige=MAX(0,prestige-50),updated_at=? WHERE qq=?",
                    (ts, attacker_qq))
            detail += " NPC反击，威严额外-50。"
        log_content = f"{attacker_name}对{row['target_name']}使用「{method}」，被发现！{detail}"
    else:
        # 执行效果
        if method == "吹枕边风":
            execute(f"UPDATE {t_table} SET love=MAX(0,love-30),updated_at=? WHERE {t_where}", (ts,))
        elif method == "诬告":
            execute(f"UPDATE {t_table} SET virtue=MAX(0,virtue-20),prestige=MAX(0,prestige-30),updated_at=? WHERE {t_where}", (ts,))
        elif method == "下毒":
            dmg = random.randint(30, 50)
            execute(f"UPDATE {t_table} SET health=MAX(1,health-?),updated_at=? WHERE {t_where}", (dmg, ts))
        elif method == "构陷失宠":
            execute(f"UPDATE {t_table} SET love=0,prestige=MAX(0,prestige-40),updated_at=? WHERE {t_where}", (ts,))
        elif method == "截财" and target_npc_id:
            pass  # NPC自动获宠效果在日结算中处理
        elif method == "落胎" and target_qq:
            tgt = get_concubine_by_qq(target_qq)
            if tgt and tgt["status"] == "pregnant":
                execute("UPDATE concubines SET status='normal',pregnant_day=0,health=MAX(1,health-50),love=MAX(0,love-40),prestige=MAX(0,prestige-50),updated_at=? WHERE qq=?",
                        (ts, target_qq))
        detail = "执行成功。"
        result = "success"
        log_content = f"{attacker_name}对{row['target_name']}使用「{method}」，成功！"

    execute("UPDATE intrigue_queue SET status='executed',result=?,result_detail=?,executed_at=? WHERE id=?",
            (result, detail, ts, row["id"]))
    execute("""INSERT INTO daily_log (day_num,log_type,title,content,affected,is_major)
               VALUES(?,?,?,?,?,?)""",
            (day_num, "intrigue_result", "宫廷暗流", log_content,
             f"{attacker_qq},{target_qq or target_npc_id}", 0))

# ─── 秘密查询接口（供海豹读取）────────────────────────────────
@app.route("/api/intrigue_results/<qq>")
def api_intrigue_results(qq):
    """海豹拉取针对该玩家的陷害结果"""
    rows = query(
        "SELECT * FROM intrigue_queue WHERE target_qq=? AND status='executed' AND result IS NOT NULL ORDER BY executed_at DESC LIMIT 10",
        (qq,)
    )
    return jsonify([dict(r) for r in rows])

@app.route("/api/pending_intrigue/<int:day>")
def api_pending_intrigue(day):
    """海豹日结算时拉取待执行陷害"""
    rows = query(
        "SELECT * FROM intrigue_queue WHERE status='pending' AND execute_day<=?", (day,)
    )
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    with app.app_context():
        if not os.path.exists(DB_PATH):
            init_db()
    app.run(host="0.0.0.0", port=5004, debug=False)
