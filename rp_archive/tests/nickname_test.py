"""微信名：在「我的」里自设，消息列表/对话标题/新信息选人显示成「微信名（真名）」；校验（长度/括号/重名/违禁词/保留词）、
清除、只影响显示（匿名化名、心动信署名不变）、别人看得到、管理身份不能设
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/nickname_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, re, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT api_token, id FROM tenants").fetchone(); TOKEN, TID = tok["api_token"], tok["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'测试季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='测试季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,'ADMINCODE1')", (TID, SID))
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,)); c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "snapshot": {
    "game_day": "D2", "roster": [{"name": n} for n in ("林晚", "周屿", "沈知意")],
    "rules": {"sms_enabled": True, "gift_enabled": True, "chaos": {"dailyLimit": 20}, "mail_cooldown_min": 0, "gift_cooldown_min": 0,
              "gift_daily_limit": 20, "gift_mode": 0}}})
now = int(time.time() * 1000)
c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) VALUES (?,?,?,?,?,?,?,?,?,?)",
          (SID, TID, "", "sms", "周屿", "林晚", "在吗", json.dumps({"delivered": "在吗", "signature": "落款：周屿"}), now, "D2")); c.commit()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def setnick(cl, nick, token=None):
    cl.post("/p/me/nickname", data={"csrf": token or cl.csrf, "nick": nick})
    with cl.session_transaction() as s: return s.get("phone_flash", "")
lin, zy, sz = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001")

# 没设之前只显示真名；「我的」页有设置入口
ok("周屿" in lin.get("/p/me").get_data(as_text=True) and "（周屿）" not in lin.get("/p/me").get_data(as_text=True), "plain before")
ok("微信名" in lin.get("/p/me/library?view=profile").get_data(as_text=True), "settings form")

# 设置成功：周屿设「阿屿」→ 林晚的消息列表/对话标题/新信息里看到「阿屿（周屿）」；周屿自己的「我的」页也提示
ok("微信名已设为「阿屿」" in setnick(zy, "阿屿"), "set")
inbox = lin.get("/p/me").get_data(as_text=True)
ok("阿屿（周屿）" in inbox, "inbox row")
ok("阿屿（周屿）" in lin.get("/p/me/周屿").get_data(as_text=True).split('class="chat"')[0], "thread title")
ok("阿屿（周屿）" in lin.get("/p/me/new").get_data(as_text=True), "new-message picker")
ok('data-name="周屿"' in inbox and 'data-name="阿屿' not in inbox, "avatar still keyed by real name")
ok("阿屿（周屿）" not in sz.get("/p/me/library?view=profile").get_data(as_text=True), "others' settings page unaffected")
ok('value="阿屿"' in zy.get("/p/me/library?view=profile").get_data(as_text=True), "own form prefilled")
ok("阿屿（周屿）" not in lin.get("/p/me/stats").get_data(as_text=True), "scope: not in stats pages")

# 校验
ok("最多 12 个字" in setnick(lin, "一二三四五六七八九十一二三"), "too long")
for bad in ("阿屿（周屿）", "假(周屿)", "【管理员】", "a\nb"):
    ok("不能有括号" in setnick(lin, bad), bad)
ok("已经有人用了" in setnick(lin, "阿屿"), "someone else's nick")
ok("已经有人用了" in setnick(lin, "沈知意"), "someone else's real name")
ok("不能用" in setnick(lin, "管理员"), "reserved")
ok("不允许的字词" in setnick(lin, "加vx"), "blocklist")
ok("页面过期" in setnick(lin, "小晚", token="bad"), "csrf")
ok(c.execute("SELECT COUNT(*) FROM phone_nicknames WHERE role='林晚'").fetchone()[0] == 0, "nothing saved for rejects")

# 自己可以把自己的真名当微信名（等于清除）；改名、清除
ok("已设为「小晚」" in setnick(lin, "小晚"), "lin set")
ok("小晚（林晚）" in zy.get("/p/me").get_data(as_text=True) or "小晚（林晚）" in zy.get("/p/me/new").get_data(as_text=True), "visible to others")
ok("已设为「小周」" in setnick(zy, "小周"), "rename")
ok("阿屿" not in lin.get("/p/me").get_data(as_text=True) and "小周（周屿）" in lin.get("/p/me").get_data(as_text=True), "renamed")
ok("已清除" in setnick(zy, ""), "clear")
ok("（周屿）" not in lin.get("/p/me").get_data(as_text=True), "cleared")
ok("已清除" in setnick(lin, "林晚"), "own real name clears")
# 改完可以立刻复用被清掉的名字
ok("已设为「阿屿」" in setnick(sz, "阿屿"), "freed name reusable")

# 朋友圈：发帖人、点赞列表、评论人和「回复 某某」都显示「微信名（真名）」；识别身份的 data-role 仍然是真名
c.execute("INSERT INTO moments (tenant_id, show_id, role_name, content, game_day, created_at) VALUES (?,?,?,?,?,?)", (TID, SID, "周屿", "天台的风", "D2", now))
mid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute("INSERT INTO moment_likes (moment_id, role_name, created_at) VALUES (?,?,?)", (mid, "林晚", now))
c.execute("INSERT INTO moment_comments (moment_id, role_name, reply_to, content, created_at) VALUES (?,?,?,?,?)", (mid, "林晚", "周屿", "带我一个", now))
c.execute("INSERT INTO moment_comments (moment_id, role_name, reply_to, content, created_at) VALUES (?,?,?,?,?)", (mid, "沈知意", "", "我也去", now)); c.commit()
ok("已设为「屿哥」" in setnick(zy, "屿哥"), "zy nick for moments")   # 前面的清除/复用测试之后，三个人各自重新设
ok("已设为「小晚」" in setnick(lin, "小晚"), "lin nick for moments")
mo = lin.get("/p/me/moments").get_data(as_text=True)
ok('<div class="mname">屿哥（周屿）</div>' in mo, "poster")
ok("♥ 小晚（林晚）" in mo, "likes")
ok("<b>小晚（林晚）</b> 回复 <b>屿哥（周屿）</b>：带我一个" in mo, "comment + reply_to")
ok("<b>阿屿（沈知意）</b>：我也去" in mo, "third person with her own nick")
setnick(sz, "")
ok("<b>沈知意</b>：我也去" in lin.get("/p/me/moments").get_data(as_text=True), "someone without a nick stays plain")
ok('data-role="林晚"' in mo and 'data-role="小晚' not in mo, "data-role stays the real name")
ok(lin.get("/p/me/search?q=天台").get_json()["groups"][0]["items"][0]["title"] == "屿哥（周屿）", "moment in search")
# 匿名化名不受影响：林晚用化名「小狐狸」给周屿发起，周屿那边看到的还是「小狐狸」，不会带出微信名
setnick(lin, "小晚")
lin.post("/p/me/alias", data={"csrf": lin.csrf, "to": "周屿", "alias": "小狐狸"})
lin.post("/p/me/send", data={"csrf": lin.csrf, "to": "周屿＠小狐狸", "text": "猜猜我是谁", "kind": "sms"})
zpage = zy.get("/p/me").get_data(as_text=True)
ok("小狐狸" in zpage, "alias thread appears for recipient")
rows = dict((k, re.sub(r"<[^>]+>", "", v)) for k, v in re.findall(r'<a class="row"[^>]*data-other="([^"]*)".*?<span class="name">(.*?)</span>', zpage, re.S))
ok(rows.get("小狐狸") == "小狐狸", "alias row shows only the alias: " + str(rows))
ok(rows.get("林晚") == "小晚（林晚）", "the ordinary thread with the same person still shows nickname（real name）")
ok("（林晚）" not in zy.get("/p/me/小狐狸").get_data(as_text=True), "alias thread page")

# 管理身份看得到（以玩家视角翻手机），但不能设
adm = app.test_client(); adm.get("/p/ADMINCODE1"); adm.get("/p/admin")
with adm.session_transaction() as s: t = s.get("phone_csrf")
adm.post("/p/me/nickname", data={"csrf": t, "nick": "管理员号"})
ok(c.execute("SELECT COUNT(*) FROM phone_nicknames WHERE nick='管理员号'").fetchone()[0] == 0, "admin cannot set")
ok(app.test_client().post("/p/me/nickname", data={"nick": "x"}).status_code == 302, "needs login")
print("ALL OK")
