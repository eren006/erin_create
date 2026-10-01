"""网页漂流瓶：开关（需插件 1.10.8+）/ 同步下发 bottle_web / 抽人规则（不抽 NPC、自己、拉黑了抛瓶人的）/ 匿名 / 回信与拉黑 / 暂停通讯 / 未同步
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
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001"), ("路人", "NPC0000001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.commit()
app = A.app; app.testing = True
bot = app.test_client()
ROSTER = [{"name": "林晚", "npc": False}, {"name": "周屿", "npc": False}, {"name": "沈知意", "npc": False}, {"name": "路人", "npc": True}]
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(version="1.10.8", blocks=None, roster=None):
    r = bot.post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "snapshot": {
        "game_day": "D2", "roster": roster or ROSTER, "rules": {"sms_enabled": True}, "blocks": blocks or [], "block_write": True,
        "plugin": {"version": version, "params": []}}})
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "login"); cl.get("/p/me"); return cl
def tok_of(cl):
    with cl.session_transaction() as s: return s["phone_csrf"]
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
ok("漂流瓶" in lin.get("/p/me/discover").get_data(as_text=True), "entry on discover")
ok("扔出去" in lin.get("/p/me/bottles").get_data(as_text=True), "page opens")

def throw(cl, text, token=None):
    return cl.post("/p/me/bottles/throw", data={"text": text, "csrf": token or tok_of(cl)})
ok(throw(lin, "有人吗", token="bad").status_code == 302 and c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == 0, "csrf")
ok(throw(lin, "   ").status_code == 302 and c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == 0, "empty")
ok(throw(lin, "x" * 301).status_code == 302 and c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == 0, "too long")
for _ in range(30): throw(lin, "有人能听到我说话吗")
rows = c.execute("SELECT thrower, catcher FROM phone_bottles").fetchall()
ok(len(rows) == 30 and all(r["thrower"] == "林晚" for r in rows), "30 thrown")
ok({r["catcher"] for r in rows} <= {"周屿", "沈知意"}, "never self or NPC: %s" % {r["catcher"] for r in rows})
# 拉黑：周屿拉黑了林晚 → 瓶子不会落到周屿手里
sync(blocks=[{"blocker": "周屿", "blocked": "林晚", "silent": True, "since": 1}])
c.execute("DELETE FROM phone_bottles"); c.execute("DELETE FROM phone_bottle_msgs"); c.commit()
for _ in range(20): throw(lin, "再来一个")
ok({r["catcher"] for r in c.execute("SELECT catcher FROM phone_bottles")} == {"沈知意"}, "blocked catcher excluded")

# 匿名：捡到的人看不到抛瓶人的名字
bid = c.execute("SELECT id FROM phone_bottles ORDER BY id LIMIT 1").fetchone()[0]
pg = shen.get(f"/p/me/bottles/{bid}").get_data(as_text=True)
ok("再来一个" in pg, "catcher sees text")
ok("林晚" not in pg.split("id=\"scroll\"")[1].split("</form>")[0], "thrower anonymous to catcher")
ok(zhou.get(f"/p/me/bottles/{bid}").status_code == 302, "stranger redirected")
# 回信
def reply(cl, bid, text): return cl.post(f"/p/me/bottles/{bid}/reply", data={"text": text, "csrf": tok_of(cl)})
reply(shen, bid, "我听到了")
ok("我听到了" in lin.get(f"/p/me/bottles/{bid}").get_data(as_text=True), "thrower sees reply")
ok("我听到了" in lin.get("/p/me/bottles").get_data(as_text=True), "list preview")
# 拉黑回信：沈知意拉黑了林晚（静默）→ 林晚回信自己看得到、沈知意看不到；非静默 → 拒绝
sync(blocks=[{"blocker": "沈知意", "blocked": "林晚", "silent": True, "since": 1}])
reply(lin, bid, "谢谢你")
ok("谢谢你" in lin.get(f"/p/me/bottles/{bid}").get_data(as_text=True), "silent: sender still sees own")
ok("谢谢你" not in shen.get(f"/p/me/bottles/{bid}").get_data(as_text=True), "silent: other side does not")
adm.post("/admin/phone_codes", data={"action": "admin_code"})
ACODE = c.execute("SELECT code FROM phone_admin_codes WHERE show_id=?", (SID,)).fetchone()[0]
pa = app.test_client(); pa.get("/p/" + ACODE)
pg = pa.get("/p/admin/bottles").get_data(as_text=True)
ok("林晚 → 沈知意" in pg and "谢谢你" in pg and "对方看不到" in pg, "admin sees real names and hidden reply")
ok(lin.get("/p/admin/bottles").status_code == 302, "player cannot open admin bottles")
sync(blocks=[{"blocker": "沈知意", "blocked": "林晚", "silent": False, "since": 1}])
n = c.execute("SELECT COUNT(*) FROM phone_bottle_msgs").fetchone()[0]
reply(lin, bid, "还在吗"); ok(c.execute("SELECT COUNT(*) FROM phone_bottle_msgs").fetchone()[0] == n, "non-silent block rejects")
sync()
# 违禁词
n = c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0]
throw(lin, "加qq123"); ok(c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == n, "blocked word")
# 暂停通讯
c.execute("UPDATE phone_settings SET comm_paused=1 WHERE show_id=?", (SID,)); c.commit()
throw(lin, "暂停中"); ok(c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == n, "paused: throw blocked")
reply(lin, bid, "暂停中回信"); ok("暂停中回信" not in lin.get(f"/p/me/bottles/{bid}").get_data(as_text=True), "paused: reply blocked")
c.execute("UPDATE phone_settings SET comm_paused=0 WHERE show_id=?", (SID,)); c.commit()
# 开关关掉：入口消失，页面回发现
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "0"})
ok(sync()["bottle_web"] is False, "flag off pushed")
ok("🍾" not in lin.get("/p/me/discover").get_data(as_text=True) and lin.get("/p/me/bottles").status_code == 302, "off: hidden")
# 被清除的角色（名单里没了）不能扔
adm.post("/admin/phone_codes", data={"action": "bottle_web", "on": "1"})
sync(roster=[r for r in ROSTER if r["name"] != "林晚"])
n = c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0]
throw(lin, "我还能扔吗"); ok(c.execute("SELECT COUNT(*) FROM phone_bottles").fetchone()[0] == n, "removed role cannot throw")
print("ALL OK")
