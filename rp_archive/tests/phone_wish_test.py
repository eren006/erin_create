"""网页心愿（挂心愿/撤心愿 + 心愿墙）：开关（需插件 1.10.8+ 且社交卫星加载）/ 同步下发 wish_web 与 wish_ops / 心愿墙匿名与「我的」/
挂心愿校验与排队 + 机器人回报 / 撤心愿 / 插件里心愿关闭或被限制 / 暂停通讯 / 违禁词 / 排队上限 / 被清除的角色
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_wish_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, re, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT api_token, id FROM tenants").fetchone()
TOKEN, TID = tok["api_token"], tok["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'测试季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='测试季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.commit()
app = A.app; app.testing = True
bot = app.test_client()
ROSTER = [{"name": "林晚", "npc": False}, {"name": "周屿", "npc": False}, {"name": "沈知意", "npc": False}]
NOW = int(time.time() * 1000)
WISHES = [{"id": "AAA1111", "day": "D2", "time": "14:00-15:00", "place": "咖啡厅", "content": "想喝咖啡", "nick": "小周", "gender": "男", "ts": NOW - 3600_000, "reward": "", "from_role": "周屿"},
          {"id": "BBB2222", "day": "D2", "time": "16:00-17:00", "place": "花园", "content": "想散步", "nick": "", "gender": "女", "ts": NOW - 7200_000, "reward": "玫瑰×1", "from_role": "林晚"},
          {"id": "OLD0000", "day": "D1", "time": "10:00-11:00", "place": "旧", "content": "过期的", "nick": "", "gender": "", "ts": NOW - 25 * 3600_000, "reward": "", "from_role": "周屿"}]
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(version="1.10.8", wish_web=True, done=None, wish_rule=None, feature_off=None, roster=None, wishes=None, sms_enabled=True):
    rules = {"sms_enabled": sms_enabled, "wish": wish_rule if wish_rule is not None else {"enabled": True, "has_day": True}}
    r = bot.post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "wish_ops_done": done or [], "snapshot": {
        "game_day": "D2", "roster": roster or ROSTER, "rules": rules, "feature_off": feature_off or {}, "blocks": [], "block_write": True,
        "wishes": WISHES if wishes is None else wishes, "plugin": {"version": version, "wish_web": wish_web, "params": []}}})
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "login"); cl.get("/p/me"); return cl
def tok_of(cl):
    with cl.session_transaction() as s: return s["phone_csrf"]
def text(cl, url): return cl.get(url).get_data(as_text=True)
adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID

# 开关：没同步 / 版本低 / 社交卫星没加载 → 开不了
ok(adm.post("/admin/phone_codes", data={"action": "wish_web", "on": "1"}).status_code == 409, "no sync")
sync(version="1.10.7"); ok(adm.post("/admin/phone_codes", data={"action": "wish_web", "on": "1"}).status_code == 409, "old plugin")
sync(wish_web=False); ok(adm.post("/admin/phone_codes", data={"action": "wish_web", "on": "1"}).status_code == 409, "no social satellite")
ok(sync()["wish_web"] is False, "off by default")
adm.post("/admin/phone_codes", data={"action": "wish_web", "on": "1"})
ok(sync()["wish_web"] is True, "flag pushed")

lin = player("LINWAN0001"); zhou = player("ZHOUYU0001"); shen = player("SHENZY0001")
ok("心愿" in text(lin, "/p/me/discover"), "entry on discover")
pg = text(lin, "/p/me/wishes")
ok("想喝咖啡" in pg and "想散步" in pg and "过期的" not in pg, "wall shows live wishes only")
ok("小周" in pg and "👨" in pg and "周屿" not in pg.split("漂浮的心愿")[1], "others anonymous (nick+gender, no real name)")
ok(pg.count("撤回</button>") == 1 and pg.count(">摘取</button>") == 1 and "/wishes/AAA1111/pick" in pg and "/wishes/BBB2222/pick" not in pg, "only my wish has withdraw; only others' wishes have pick")
ok("玫瑰×1" in pg, "reward shown")

c.execute("INSERT OR REPLACE INTO phone_reports (show_id, role, data, updated_at) VALUES (?,?,?,?)", (SID, "林晚", json.dumps({"rpg": {"items": [{"name": "玫瑰", "count": 3}, {"name": "空的", "count": 0}], "currencies": [{"name": "金币", "count": 50}]}}), NOW)); c.commit()
ok("玫瑰（有 3）" in text(lin, "/p/me/wishes") and "空的" not in text(lin, "/p/me/wishes") and "金币（有 50）" in text(lin, "/p/me/wishes"), "reward options from bag")
# 挂心愿：校验 → 排队 → 机器人下发 → 回报
def post(cl, **kw):
    d = {"t1": "14:00", "t2": "15:00", "place": "咖啡厅", "content": "想喝咖啡", "nick": "", "csrf": tok_of(cl)}; d.update(kw)
    return cl.post("/p/me/wishes/post", data=d)
n0 = lambda: c.execute("SELECT COUNT(*) FROM phone_wish_ops").fetchone()[0]
post(lin, csrf="bad"); post(lin, t1="15:00", t2="14:00"); post(lin, place="咖 啡"); post(lin, content=""); post(lin, content="".join(chr(0x4e00 + i * 7) for i in range(61)))   # 61 个各不相同的字：超长要拒绝（全是同一个字会被自动精简，不算超长）
post(lin, nick="一二三四五六七八九十十一"); post(lin, content="a|b"); post(lin, content="加qq123")
ok(n0() == 0, "invalid posts rejected")
post(lin, content="想喝咖啡", nick="小林")
ok("处理中" in text(lin, "/p/me/wishes"), "pending shown")
ops = sync()["wish_ops"]
ok(len(ops) == 1 and ops[0]["kind"] == "post" and ops[0]["role"] == "林晚", ops)
pl = json.loads(ops[0]["payload"]); ok(pl == {"time": "14:00-15:00", "place": "咖啡厅", "content": "想喝咖啡", "nick": "小林"}, pl)
ok(len(sync()["wish_ops"]) == 1, "re-delivered until reported")
ok(sync(done=[{"id": ops[0]["id"], "ok": True, "msg": "✅ 心愿已漂走！编号：CCC3333", "wish_id": "CCC3333"}])["wish_ops"] == [], "done → not re-sent")
ok("处理中" not in text(lin, "/p/me/wishes"), "pending cleared")
# 失败回报：显示原因
post(lin, content="第二个"); op = sync()["wish_ops"][0]
sync(done=[{"id": op["id"], "ok": False, "msg": "⚠️ 时间冲突：你在 D2 14:00 已有安排"}])
pg = text(lin, "/p/me/wishes"); ok("没成功" in pg and "时间冲突" in pg, "failed op shown with reason")

# 撤心愿：只能撤自己的
def withdraw(cl, wid): return cl.post(f"/p/me/wishes/{wid}/withdraw", data={"csrf": tok_of(cl)})
n = n0(); withdraw(lin, "AAA1111"); ok(n0() == n, "cannot withdraw others'")
withdraw(lin, "NOPE999"); ok(n0() == n, "unknown id")
withdraw(lin, "BBB2222"); ok(n0() == n + 1, "withdraw queued")
op = sync()["wish_ops"][0]; ok(op["kind"] == "withdraw" and json.loads(op["payload"]) == {"wish_id": "BBB2222"}, op)
sync(done=[{"id": op["id"], "ok": True, "msg": "✅ 已撤回心愿 BBB2222", "wish_id": "BBB2222"}])
sync(wishes=[w for w in WISHES if w["id"] != "BBB2222"])
ok("想散步" not in text(lin, "/p/me/wishes"), "wall follows next snapshot")
sync()

# 悬赏：校验背包 → payload 带 reward
n = n0(); post(lin, reward="没有的东西", reward_count="1"); post(lin, reward="玫瑰", reward_count="4"); post(lin, reward="玫瑰", reward_count="0"); ok(n0() == n, "bad rewards rejected")
post(lin, content="悬赏的心愿", reward="玫瑰", reward_count="2"); op = sync()["wish_ops"][0]
ok(json.loads(op["payload"])["reward"] == {"name": "玫瑰", "count": 2}, op)
sync(done=[{"id": op["id"], "ok": True, "msg": "ok", "wish_id": "DDD4444"}])
sync(wishes=[w for w in WISHES] + [{"id": "DDD4444", "day": "D2", "time": "14:00-15:00", "place": "咖啡厅", "content": "悬赏的心愿", "nick": "", "gender": "女", "ts": NOW, "reward": "玫瑰×2", "from_role": "林晚"}])
sync(wish_rule={"enabled": True, "has_day": True, "bounty_enabled": False}); ok("悬赏（选填" not in text(lin, "/p/me/wishes"), "bounty off hides reward fields")
n = n0(); post(lin, content="悬赏关了", reward="玫瑰", reward_count="1"); ok(n0() == n, "bounty off rejects reward")
sync()

# 摘心愿：顺序与冲突
def pick(cl, wid): return cl.post(f"/p/me/wishes/{wid}/pick", data={"csrf": tok_of(cl)})
n = n0(); pick(lin, "BBB2222"); ok(n0() == n, "cannot pick own wish")
pick(lin, "NOPE999"); ok(n0() == n, "unknown wish")
pick(lin, "OLD0000"); ok(n0() == n, "expired wish")
pick(lin, "AAA1111"); ok(n0() == n + 1, "pick queued")
ok("正在被别人摘取" in text(shen, "/p/me/wishes"), "others see the wish as being claimed")
n = n0(); pick(shen, "AAA1111"); ok(n0() == n, "second pick on a wish that is being claimed is refused at queue time")
# 同一批里有两个人先后摘同一个（站点这边绕过检查直接排队）：机器人按 id 先后处理，先到的在前
c.execute("INSERT INTO phone_wish_ops (show_id, role, kind, payload, created_at) VALUES (?,?,?,?,?)", (SID, "沈知意", "pick", json.dumps({"wish_id": "AAA1111"}), NOW)); c.commit()
ops = sync()["wish_ops"]; ids = [o["id"] for o in ops if o["kind"] == "pick"]
ok(ids == sorted(ids) and len(ids) == 2, "ops delivered in id order: %s" % ids)
first, second = ids
sync(done=[{"id": first, "ok": True, "msg": "🎉 摘取成功！专属小群已建立。 💬 群号：123456", "wish_id": "AAA1111", "gid": "123456"},
           {"id": second, "ok": False, "msg": "心愿不存在或已过期"}])
pg = text(lin, "/p/me/wishes"); ok("群号：123456" in pg and "已完成" in pg, "pick result with group number shown to the picker")
ok("AAA1111" not in text(shen, "/p/me/wishes").split("漂浮的心愿")[1], "picked wish hidden at once (before snapshot catches up)")
ok("心愿不存在或已过期" in text(shen, "/p/me/wishes"), "loser sees failure")
sync(wishes=[w for w in WISHES if w["id"] != "AAA1111"])
# 重复回报不重复处理
sync(done=[{"id": first, "ok": False, "msg": "重复回报", "wish_id": "AAA1111"}]); ok("重复回报" not in text(lin, "/p/me/wishes"), "duplicate report ignored")
# 摘取失败：心愿还在（插件放回去了），不会被藏起来
FRESH = {"id": "FFF6666", "day": "D2", "time": "18:00-19:00", "place": "海边", "content": "看日落", "nick": "", "gender": "男", "ts": NOW, "reward": "", "from_role": "周屿"}
sync(wishes=WISHES + [FRESH])
pick(shen, "FFF6666"); op = sync(wishes=WISHES + [FRESH])["wish_ops"][0]
sync(done=[{"id": op["id"], "ok": False, "msg": "⚠️ 没能建立专属小群，心愿已放回"}], wishes=WISHES + [FRESH])
ok("/wishes/FFF6666/pick" in text(shen, "/p/me/wishes") and "心愿已放回" in text(shen, "/p/me/wishes"), "failed pick: wish stays, reason shown")
sync()

# 排队上限
for i in range(5): post(zhou, content=f"刷{i}")
ok(c.execute("SELECT COUNT(*) FROM phone_wish_ops WHERE role='周屿' AND done=0").fetchone()[0] == A._WISH_MAX_PENDING, "pending cap")
for o in sync()["wish_ops"]: sync(done=[{"id": o["id"], "ok": True, "msg": "x"}])

# 插件里心愿关闭 / 被限制 / 没设天数 / 暂停通讯 / 被清除
def blocked(label, **kw):
    sync(**kw); n = n0(); post(lin, content="被拦住的"); ok(n0() == n, label)
blocked("wish disabled", wish_rule={"enabled": False, "has_day": True})
ok("心愿功能已关闭" in text(lin, "/p/me/wishes"), "reason shown")
blocked("user restricted", feature_off={"林晚": ["wish"]})
blocked("no day", wish_rule={"enabled": True, "has_day": False})
blocked("removed role", roster=[r for r in ROSTER if r["name"] != "林晚"])
sync()
c.execute("UPDATE phone_settings SET comm_paused=1 WHERE show_id=?", (SID,)); c.commit()
n = n0(); post(lin, content="暂停中"); ok(n0() == n, "paused")
c.execute("UPDATE phone_settings SET comm_paused=0 WHERE show_id=?", (SID,)); c.commit()
# 关开关：入口消失
adm.post("/admin/phone_codes", data={"action": "wish_web", "on": "0"})
ok(sync()["wish_web"] is False and "🌠" not in text(lin, "/p/me/discover") and lin.get("/p/me/wishes").status_code == 302, "off: hidden")
print("ALL OK")
