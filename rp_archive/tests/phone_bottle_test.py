"""漂流瓶（群里和网页共用一个池子）：开关（需插件 1.10.8+）/ 同步下发 bottle_ops / 群里事件入库 / 网页扔瓶与回信走排队 + 机器人回报入库 /
匿名 / 静默拉黑只有自己看得到 / 暂停通讯 / 违禁词 / 排队上限 / 被清除的角色
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_bottle_test.py ；全部通过时最后一行打印 ALL OK。
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
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(version="1.10.8", done=None, roster=None, sms_enabled=True, feature_off=None, shop=None):
    r = bot.post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "bottle_ops_done": done or [], "snapshot": {
        "game_day": "D2", "roster": roster or ROSTER, "rules": {"sms_enabled": sms_enabled}, "feature_off": feature_off or {}, "blocks": [], "block_write": True,
        "shop": shop, "plugin": {"version": version, "params": []}}})
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "login"); cl.get("/p/me"); return cl
def tok_of(cl):
    with cl.session_transaction() as s: return s["phone_csrf"]
def text(cl, url): return cl.get(url).get_data(as_text=True)
adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID

# 插件版本不够 / 没同步 → 开不了
ok(adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"}).status_code == 409, "no sync: cannot enable")
sync(version="1.10.7")
ok(adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"}).status_code == 409, "old plugin: cannot enable")
ok(sync()["bottle_web"] is False, "flag off by default")
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"})
ok(sync()["bottle_web"] is True, "flag pushed to plugin")

lin = player("LINWAN0001"); zhou = player("ZHOUYU0001"); shen = player("SHENZY0001")
ok("漂流瓶" in text(lin, "/p/me/discover"), "entry on discover")
ok("扔出去" in text(lin, "/p/me/bottles"), "page opens")

# 群里扔的瓶子（插件发 /api/event）：捡瓶人网页上能看到并接着回，抛瓶人看到自己扔的
def event(frm, to, content, bid, action):
    r = bot.post("/api/event", headers={"X-Archive-Token": TOKEN}, json={"type": "drift_bottle", "from_role": frm, "to_role": to, "content": content,
                 "extra_info": {"bottle_id": bid, "action": action}, "timestamp": int(time.time() * 1000)})
    ok(r.status_code == 200 and r.get_json()["ok"], r.get_data(as_text=True))
event("林晚", "周屿", "群里扔的一个瓶子", "7", "throw")
pg = text(zhou, "/p/me/bottles/7"); ok("群里扔的一个瓶子" in pg and "我捡到的" not in pg and "抛瓶人匿名" in pg, "catcher sees group bottle, anonymous")
ok("#7" in text(zhou, "/p/me/bottles") and "我捡到的" in text(zhou, "/p/me/bottles"), "listed for catcher")
ok("你扔出的" in text(lin, "/p/me/bottles/7"), "thrower view")
ok(text(shen, "/p/me/bottles/7") == "" or shen.get("/p/me/bottles/7").status_code == 302, "stranger redirected")
ok(bot.post("/api/event", headers={"X-Archive-Token": TOKEN}, json={"type": "drift_bottle", "from_role": "a", "to_role": "b", "content": "x", "extra_info": {}}).status_code == 400, "bad event rejected")
n_events = c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0]; ok(n_events == 0, "not stored in extra_events (would leak into archive pages)")

# 网页回信：排队 → 机器人下发 → 回报入库
def reply(cl, bid, t, token=None): return cl.post(f"/p/me/bottles/{bid}/reply", data={"text": t, "csrf": token or tok_of(cl)})
reply(zhou, 7, "token错", token="bad"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == 0, "csrf")
reply(zhou, 7, "   "); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == 0, "empty")
reply(zhou, 7, "我捡到了，谢谢")
pg = text(zhou, "/p/me/bottles/7"); ok("我捡到了，谢谢" in pg and "发送中" in pg, "pending shown")
d = sync(); ops = d["bottle_ops"]
ok(len(ops) == 1 and ops[0]["kind"] == "reply" and ops[0]["bottle_id"] == 7 and ops[0]["role"] == "周屿", ops)
ok(len(sync()["bottle_ops"]) == 1, "re-delivered until reported")
d = sync(done=[{"id": ops[0]["id"], "ok": True, "msg": "ok", "bottle_id": 7, "catcher": "", "silent": False}]); ok(d["bottle_ops"] == [], "done → not re-sent")
pg = text(lin, "/p/me/bottles/7"); ok("我捡到了，谢谢" in pg, "thrower sees web reply"); ok("发送中" not in text(zhou, "/p/me/bottles/7"), "no longer pending")
sync(done=[{"id": ops[0]["id"], "ok": True, "msg": "ok", "bottle_id": 7}]); ok(c.execute("SELECT COUNT(*) FROM phone_drift_msgs").fetchone()[0] == 2, "report applied once")

# 静默拉黑：回报 silent → 只有发件人自己看得到
reply(lin, 7, "我再说一句")
op = sync()["bottle_ops"][0]; sync(done=[{"id": op["id"], "ok": True, "msg": "ok", "bottle_id": 7, "silent": True}])
ok("我再说一句" in text(lin, "/p/me/bottles/7"), "silent: sender sees own"); ok("我再说一句" not in text(zhou, "/p/me/bottles/7"), "silent: other does not")
# 非静默拒绝 → 失败提示
reply(lin, 7, "还在吗")
op = sync()["bottle_ops"][0]; sync(done=[{"id": op["id"], "ok": False, "msg": "❌ 周屿 已拒绝你的联络。"}])
ok("没有发出去" in text(lin, "/p/me/bottles/7") and "已拒绝" in text(lin, "/p/me/bottles/7"), "failed reply notice")
ok("还在吗" not in text(zhou, "/p/me/bottles/7"), "failed reply not delivered")

# 网页扔瓶：排队 → 机器人抽人并回报瓶号和捡瓶人 → 入库，捡瓶人网页上看到
def throw(cl, t, token=None): return cl.post("/p/me/bottles/throw", data={"text": t, "csrf": token or tok_of(cl)})
throw(lin, "x", token="bad"); throw(lin, "x" * 301); throw(lin, "   ")
ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops WHERE kind='throw'").fetchone()[0] == 0, "invalid throws rejected")
throw(lin, "网页扔的瓶子")
ok("发送中" in text(lin, "/p/me/bottles"), "pending throw listed")
op = sync()["bottle_ops"][0]; ok(op["kind"] == "throw" and op["content"] == "网页扔的瓶子", op)
sync(done=[{"id": op["id"], "ok": True, "msg": "ok", "bottle_id": 12, "catcher": "沈知意"}])
ok("网页扔的瓶子" in text(shen, "/p/me/bottles/12") and "#12" in text(lin, "/p/me/bottles") and "我扔的" in text(lin, "/p/me/bottles"), "web bottle visible both sides")
ok("发送中" not in text(lin, "/p/me/bottles"), "pending cleared")
# 扔瓶失败（没人可抛）→ 列表里提示
throw(lin, "没人接"); op = sync()["bottle_ops"][0]; sync(done=[{"id": op["id"], "ok": False, "msg": "🌊 大海太安静了"}])
ok("没扔出去" in text(lin, "/p/me/bottles") and "大海太安静" in text(lin, "/p/me/bottles"), "failed throw shown")
# 排队上限
for i in range(7): throw(zhou, f"刷{i}")
ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops WHERE role='周屿' AND done=0").fetchone()[0] == A._BOTTLE_MAX_PENDING, "pending cap")

# 寄信功能关了 / 这个人被限制寄信 → 漂流瓶也不能用（它是匿名短信的一种）
n = c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0]
sync(sms_enabled=False); throw(lin, "寄信关了"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "sms disabled blocks bottle")
ok("寄信功能已关闭" in text(lin, "/p/me/bottles"), "reason shown")
sync(feature_off={"林晚": ["sms"]}); throw(lin, "被限制"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "restricted user blocked")
reply(lin, 7, "被限制回信"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "restricted user cannot reply")
throw(shen, "别人不受影响"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n + 1, "others unaffected")
sync()
# 违禁词 / 暂停通讯
n = c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0]
throw(shen, "加qq123"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "blocked word")
c.execute("UPDATE phone_settings SET comm_paused=1 WHERE show_id=?", (SID,)); c.commit()
throw(shen, "暂停中"); reply(shen, 12, "暂停中回信")
ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "paused: blocked")
c.execute("UPDATE phone_settings SET comm_paused=0 WHERE show_id=?", (SID,)); c.commit()

# 管理员视角：真名 + 对方看不到的
adm.post("/admin/phone_codes", data={"action": "admin_code"})
ACODE = c.execute("SELECT code FROM phone_admin_codes WHERE show_id=?", (SID,)).fetchone()[0]
pa = app.test_client(); pa.get("/p/" + ACODE)
pg = pa.get("/p/admin/bottles").get_data(as_text=True)
ok("林晚 → 周屿" in pg and "林晚 → 沈知意" in pg and "对方看不到" in pg and "群里扔的一个瓶子" in pg, "admin sees real names")
ok(lin.get("/p/admin/bottles").status_code == 302, "player cannot open admin bottles")

# 开关关掉：入口消失；被清除的角色（名单里没了）不能扔
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "0"})
ok(sync()["bottle_web"] is False, "flag off pushed")
ok("🍾" not in text(lin, "/p/me/discover") and lin.get("/p/me/bottles").status_code == 302, "off: hidden")
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"})
sync(roster=[r for r in ROSTER if r["name"] != "林晚"])
n = c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0]
throw(lin, "我还能扔吗"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_ops").fetchone()[0] == n, "removed role cannot throw")
# 使用指南里「现在哪些功能怎么用」：按开关现算
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "0"}); sync()
g = text(lin, "/p/guide"); ok("现在哪些功能怎么用" in g and "群里发「漂流瓶 内容」" in g, "guide: bottle in group when web off")
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"}); sync()
g = text(lin, "/p/guide"); ok("网页（发现 → 漂流瓶）" in g and "群里的「漂流瓶」指令已停用" in g, "guide: bottle on web when switch on")
sync(sms_enabled=False); g = text(lin, "/p/guide"); ok("暂未开放（和寄信共用开关）" in g, "guide: bottle unavailable when 寄信 off")
sync()
ok("现在哪些功能怎么用" in pa.get("/p/guide").get_data(as_text=True), "guide shown to admin phone too")
# 后台「小手机」页：网页礼品店是空的（或跟机器人里的件数对不上）要提醒，不然玩家只会看到「货架上什么都没有」
pg = text(adm, "/admin/phone_codes"); ok("礼品店的礼物两边对不上" in pg and "网页 0 件" in pg, "empty web shop warned")
c.execute("INSERT INTO site_config (show_id, tenant_id, key, value) VALUES (?,?,'preset_gifts',?)", (SID, TID, json.dumps({"#001": {"name": "玫瑰", "content": "一朵"}}))); c.commit()
pg = text(adm, "/admin/phone_codes"); ok("礼品店的礼物两边对不上" not in pg, "no warning once web has gifts (old plugin does not report count)")
sync(shop={"refresh_hours": 24, "gift_count": 5}); pg = text(adm, "/admin/phone_codes")
ok("礼品店的礼物两边对不上" in pg and "机器人 5 件" in pg, "mismatch warned")
sync(shop={"refresh_hours": 24, "gift_count": 1}); ok("礼品店的礼物两边对不上" not in text(adm, "/admin/phone_codes"), "match → no warning")
print("ALL OK")
