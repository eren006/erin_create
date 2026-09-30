"""匿名对话（化名）：新信息页勾选匿名建化名、双方视角、回复送回化名主人、真名绝不外泄、每人对同一人最多 3 个化名、
同一收件人下化名不重名、次数跟短信共用、拉黑按真实身份、网页发送关着时不能用、管理员能看到真名
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/alias_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
A.MOMENT_IMAGE_DIR = os.path.join(tmp, "moment_images")
A.MODERATION_LOG = os.path.join(tmp, "moderation.log")
A.init_db()
A._PHONE_MIN_GAP_MS = 0
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT id, api_token FROM tenants").fetchone(); TID, TOKEN = tok["id"], tok["api_token"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,)); c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(limit=20, blocks=None, chaos=None):
    app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "snapshot": {
        "game_day": "D1", "roster": [{"name": n} for n in ("林晚", "周屿", "沈知意")],
        "rules": {"chaos": {"dailyLimit": limit, "publicChance": 0, **(chaos or {})}, "mail_cooldown_min": 0, "sms_public": True},
        "blocks": blocks or [], "counts": {"sms": {}, "gift": {}}, "last": {"sms": {}, "gift": {}}}})
def player(code):
    cl = app.test_client(); cl.get("/p/" + code); cl.get("/p/me/new")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def alias(cl, to, name):
    with cl.session_transaction() as s: s.pop("phone_flash", None)
    r = cl.post("/p/me/alias", data={"to": to, "alias": name, "csrf": cl.csrf})
    with cl.session_transaction() as s: flash = s.get("phone_flash")
    return r.location, flash
def send(cl, to, text):
    cl.post("/p/me/send", data={"to": to, "text": text, "kind": "sms", "csrf": cl.csrf})
    with cl.session_transaction() as s: return s.get("phone_flash", "")

sync()
lin, zy, sz = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001")
ok("匿名发起" in lin.get("/p/me/new").get_data(as_text=True), "new page has alias option")

# 林晚用「小狐狸」给周屿发：进到「周屿＠小狐狸」对话
loc, _ = alias(lin, "周屿", "小狐狸"); ok(loc.endswith("/p/me/%E5%91%A8%E5%B1%BF%EF%BC%A0%E5%B0%8F%E7%8B%90%E7%8B%B8"), loc)
msg = send(lin, "周屿＠小狐狸", "猜猜我是谁"); ok("衔往 周屿" in msg, msg)
ev = c.execute("SELECT * FROM extra_events ORDER BY id DESC LIMIT 1").fetchone(); info = json.loads(ev["extra_info"])
ok(ev["to_role"] == "周屿" and not info.get("is_misdelivered") and info["public_from"] == "小狐狸", "delivered to target")
lp = lin.get("/p/me").get_data(as_text=True); ok("化名·小狐狸" in lp, "owner inbox shows alias tag")
ok("你的化名：小狐狸" in lin.get("/p/me/周屿＠小狐狸").get_data(as_text=True), "owner thread title")

# 周屿那边：对话叫「小狐狸」，看不到「林晚」
zin = zy.get("/p/me").get_data(as_text=True); ok("小狐狸" in zin, "target inbox")
zt = zy.get("/p/me/小狐狸").get_data(as_text=True)
body = zt.split("<body>")[1].split("PHONE_AVATARS")[0]
ok("猜猜我是谁" in zt and "林晚" not in body and 'id="compose"' in zt and "匿名" in zt, "target thread anonymous + can reply")
ok('id="giftToggle"' not in zt, "no gifts in alias thread")

# 周屿回复 → 送到林晚的「周屿＠小狐狸」；回执不露真名
msg = send(zy, "小狐狸", "你是谁呀"); ok("衔往 小狐狸" in msg and "林晚" not in msg, msg)
ev = c.execute("SELECT * FROM extra_events ORDER BY id DESC LIMIT 1").fetchone(); ok(ev["from_role"] == "周屿" and ev["to_role"] == "林晚", dict(ev))
lt = lin.get("/p/me/周屿＠小狐狸").get_data(as_text=True); ok("你是谁呀" in lt and "猜猜我是谁" in lt, "reply reaches owner")
ok("你是谁呀" not in lin.get("/p/me/周屿").get_data(as_text=True), "not mixed into real-name thread")
ok("猜猜我是谁" not in sz.get("/p/me").get_data(as_text=True), "bystander sees nothing")
ok("林晚" not in sz.get("/p/me/public").get_data(as_text=True).split("<body>")[1].split("PHONE_AVATARS")[0], "public never shows real name")

# 规则：最多 3 个化名；同一收件人下别人不能用同名；不能用角色名/保留字
ok(alias(lin, "周屿", "小狐狸")[0].endswith("%E5%B0%8F%E7%8B%90%E7%8B%B8"), "reuse own alias")
alias(lin, "周屿", "路人甲"); alias(lin, "周屿", "路人乙")
ok("最多用 3 个化名" in (alias(lin, "周屿", "路人丙")[1] or ""), "max 3")
ok("被别人用了" in (alias(sz, "周屿", "小狐狸")[1] or ""), "unique per target")
ok(alias(sz, "林晚", "小狐狸")[1] is None, "same name to another target ok")
ok("不能用" in (alias(lin, "沈知意", "周屿")[1] or ""), "roster name forbidden")
ok("不能用" in (alias(lin, "沈知意", "点歌台")[1] or ""), "reserved")
ok("不允许的字词" in (alias(lin, "沈知意", "加vx")[1] or ""), "blocklist")
ok("选一个" in (alias(lin, "林晚", "自己")[1] or ""), "not self")

# 次数跟短信共用
sync(limit=3)
send(lin, "周屿", "普通短信")  # 已发 1 条匿名 + 这条 = 2
_m = send(lin, "周屿＠小狐狸", "第三条"); ok("今日已发 3/3" in _m, _m)
ok("上限" in send(lin, "周屿＠小狐狸", "第四条"), "limit hits alias")

# 群里按真实身份的拉黑不影响匿名对话（不然能用拉黑反查化名是谁）
sync(limit=50, blocks=[{"blocker": "周屿", "blocked": "林晚", "silent": False}])
ok("衔往 周屿" in send(lin, "周屿＠小狐狸", "照样送到"), "real block ignored")
ok("照样送到" in zy.get("/p/me/小狐狸").get_data(as_text=True), "target still receives")
sync(limit=50, blocks=[{"blocker": "林晚", "blocked": "周屿", "silent": True}])
ok("衔往 小狐狸" in send(zy, "小狐狸", "我也照样回"), "real block ignored on reply")
ok("我也照样回" in lin.get("/p/me/周屿＠小狐狸").get_data(as_text=True), "owner still receives reply")

# 化名拉黑：周屿「拉黑并结束」→ 双方都不能发；林晚看到「对方结束了」；第三人不能结束；2 小时后才能解除
sync(limit=50)
ok("拉黑并结束" in zy.get("/p/me/小狐狸").get_data(as_text=True), "block button")
zy.post("/p/me/alias/block", data={"key": "小狐狸", "csrf": zy.csrf})
ok("对话已经结束" in send(lin, "周屿＠小狐狸", "还在吗"), "owner blocked")
ok("对话已经结束" in send(zy, "小狐狸", "再见"), "target blocked too")
ok("对方结束了这段匿名对话" in lin.get("/p/me/周屿＠小狐狸").get_data(as_text=True), "owner sees ended")
zp = zy.get("/p/me/小狐狸").get_data(as_text=True); ok("分钟后可解除" in zp and 'id="compose"' not in zp, "blocker sees wait")
lin.post("/p/me/alias/block", data={"key": "周屿＠小狐狸", "csrf": lin.csrf, "action": "unblock"})
ok(c.execute("SELECT blocked_by FROM phone_aliases WHERE alias_name='小狐狸' AND target_role='周屿'").fetchone()[0] == "target", "only blocker unblocks")
zy.post("/p/me/alias/block", data={"key": "小狐狸", "csrf": zy.csrf, "action": "unblock"})
ok(c.execute("SELECT blocked_by FROM phone_aliases WHERE alias_name='小狐狸' AND target_role='周屿'").fetchone()[0] == "target", "2h cooldown")
c.execute("UPDATE phone_aliases SET blocked_at=blocked_at-2*3600*1000-1000 WHERE alias_name='小狐狸' AND target_role='周屿'"); c.commit()
zy.post("/p/me/alias/block", data={"key": "小狐狸", "csrf": zy.csrf, "action": "unblock"})
ok("衔往 周屿" in send(lin, "周屿＠小狐狸", "又能聊了"), "unblocked after 2h")
ok(c.execute("SELECT COUNT(*) FROM phone_aliases WHERE owner_role='林晚' AND target_role='周屿'").fetchone()[0] == 3, "blocked alias still counts")

# 混乱效果跟群里一样：误送到第三人时，第三人收到化名对话、能回，回复落到化名主人的对话里（落款是真正回复的人）
sync(limit=50, chaos={"misdelivery": 100})
for _ in range(10):
    send(lin, "周屿＠小狐狸", "误送测试")
    last = c.execute("SELECT to_role FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()[0]
    if last == "沈知意":
        break
ok(last == "沈知意", "misdelivered to 沈知意 at least once")
sp = sz.get("/p/me/小狐狸").get_data(as_text=True); ok("误送测试" in sp and 'id="compose"' in sp and "拉黑并结束" not in sp, "bystander can reply, cannot end")
sync(limit=50)
ok("衔往 小狐狸" in send(sz, "小狐狸", "你认错人啦"), "bystander replies")
lp2 = lin.get("/p/me/周屿＠小狐狸").get_data(as_text=True); ok("你认错人啦" in lp2 and "沈知意" in lp2, "reply lands in owner thread signed by real replier")
sync(limit=50, chaos={"tornPage": 100})
send(lin, "周屿＠小狐狸", "这是一条足够长可以被撕开的匿名信件内容")
ev = c.execute("SELECT extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone(); inf = json.loads(ev[0])
ok(inf["is_torn"], "torn")
holder = player({"林晚": "LINWAN0001", "周屿": "ZHOUYU0001", "沈知意": "SHENZY0001"}[inf["torn_holder"]])
ok("……" + inf["torn_second_half"] in holder.get("/p/me/小狐狸").get_data(as_text=True) or inf["torn_holder"] == "林晚", "torn half to holder under alias")
sync(limit=50)

# 网页发送关着：不能建化名、不能发
c.execute("UPDATE phone_settings SET web_send=0"); c.commit()
ok("%E6%96%B0" not in (alias(lin, "沈知意", "新化名")[0] or "") and c.execute("SELECT COUNT(*) FROM phone_aliases WHERE alias_name='新化名'").fetchone()[0] == 0, "off: no alias")
ok("没有开放" in send(zy, "小狐狸", "x"), "off: no send")

# 管理员看得到真名
c.execute("INSERT INTO phone_admin_codes (show_id, tenant_id, code) VALUES (?,?,'ADMINCODE1')", (SID, TID)); c.commit()
adm = app.test_client(); adm.get("/p/ADMINCODE1")
ok("林晚 用化名「小狐狸」" in adm.get("/p/admin/as/周屿/小狐狸").get_data(as_text=True), "admin sees real name")
print("ALL OK")
