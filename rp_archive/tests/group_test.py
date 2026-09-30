"""网页群聊：跟网页发送一起开关、建群（至少再拉 2 人）、一条算 1 次短信（跟短信共用上限/冷却，插件取走后不重复算）、
混乱效果（发件人看原文）、化名发言、拉黑（真名发言看不到、化名不受影响）、公开播报、拉人/改名/退群、入群前的消息看不到、
不能送礼、管理员删除
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/group_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, re, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT api_token, id FROM tenants").fetchone(); TOKEN, TID = tok["api_token"], tok["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'测试季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='测试季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001"), ("苏念", "SUNIAN0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,'ADMINCODE1')", (TID, SID))
c.commit()
app = A.app; app.testing = True
A._PHONE_MIN_GAP_MS = 0
ROSTER = [{"name": n, "npc": False} for n in ("林晚", "周屿", "沈知意", "苏念")]
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(chaos=None, blocks=None, counts=None, group_after=0, public=False, cooldown=0):
    snap = {"game_day": "D2", "roster": ROSTER, "feature_off": {}, "blocks": blocks or [], "block_write": True,
            "rules": {"sms_enabled": True, "gift_enabled": True, "chaos": {"dailyLimit": 3, **(chaos or {})},
                      "mail_cooldown_min": cooldown, "gift_cooldown_min": 0, "gift_daily_limit": 20, "gift_mode": 0,
                      "gift_window": None, "sms_public": public},
            "counts": counts or {"sms": {}, "gift": {}}, "last": {"sms": {}, "gift": {}}}
    r = app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN},
                               json={"after": 0, "group_after": group_after, "snapshot": snap})
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def flash(cl):
    with cl.session_transaction() as s: return s.get("phone_flash") or ""
def create(cl, members, name=""):
    r = cl.post("/p/me/g/new", data={"csrf": cl.csrf, "name": name, "member": members})
    m = re.search(r"/p/me/g/(\d+)$", r.headers.get("Location", ""))
    return int(m.group(1)) if m else flash(cl)
def gsend(cl, gid, text, alias=""):
    cl.post(f"/p/me/g/{gid}/send", data={"csrf": cl.csrf, "text": text, "alias": alias}); return flash(cl)
def manage(cl, gid, action, value=""):
    cl.post(f"/p/me/g/{gid}/manage", data={"csrf": cl.csrf, "action": action, "value": value}); return flash(cl)
def chat(cl, gid):
    html = cl.get(f"/p/me/g/{gid}").get_data(as_text=True)
    return html.split('class="chat"')[1].split('id="compose"')[0] if 'class="chat"' in html else html
def text_of(html):
    return re.sub(r"<[^>]+>", "", html)

lin, zy, sz, sn = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001"), player("SUNIAN0001")

# 网页发送关着：建群页提示，直接 POST 也建不了
sync()
ok("网页发送没有开放" in lin.get("/p/me/g/new").get_data(as_text=True), "closed page")
ok("❌" in str(create(lin, ["周屿", "沈知意"])), "closed: cannot create")
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,)); c.commit()
sync()

# 新信息页有「发起群聊」；至少再拉 2 人；名单外的人不行
ok("发起群聊" in lin.get("/p/me/new").get_data(as_text=True), "entry")
ok("至少再选 2 个人" in create(lin, ["周屿"]), "need 2")
ok("名单里的人" in create(lin, ["周屿", "路人"]), "roster only")
ok("不允许的字词" in create(lin, ["周屿", "沈知意"], name="加vx群"), "blocked name")
gid = create(lin, ["周屿", "沈知意"], name="天台小分队"); ok(isinstance(gid, int), gid)
for cl in (lin, zy, sz):
    ok("天台小分队" in cl.get("/p/me").get_data(as_text=True), "inbox row")
ok("天台小分队" not in sn.get("/p/me").get_data(as_text=True), "non-member no row")
ok(sn.get(f"/p/me/g/{gid}").status_code == 302, "non-member cannot open")
ok("林晚 发起了群聊" in text_of(chat(zy, gid)), "sys msg")
page = zy.get(f"/p/me/g/{gid}").get_data(as_text=True)
ok('id="compose"' in page and 'id="giftToggle"' not in page and "群聊 · 3 人" in page, "compose without gift")

# 发一条：大家看到、算 1 次短信（跟私聊短信一起算上限 3）
ok("已发到群聊「天台小分队」" in gsend(lin, gid, "今晚天台见") and "1/3" in flash(lin), flash(lin))
ok("今晚天台见" in chat(zy, gid) and "林晚" in text_of(chat(zy, gid)), "member sees")
lin.post("/p/me/send", data={"csrf": lin.csrf, "to": "周屿", "text": "私聊一条", "kind": "sms"})
ok("2/3" in flash(lin), "shares quota with sms: " + flash(lin))
ok("已发到" in gsend(lin, gid, "第三条"), "third")
ok("上限(3)" in gsend(lin, gid, "第四条"), "daily cap")

# 冷却跟短信共用
sync(cooldown=60)
ok("已发到" in gsend(zy, gid, "我来了"), "zy first")
ok("鸽子正在休息" in gsend(zy, gid, "再来"), "cooldown shared")
sync()

# 插件同步：下发群消息；取走后（group_after 覆盖）按快照次数算，不重复
d = sync(); ids = [e["id"] for e in d["group_events"]]
ok([e["from_role"] for e in d["group_events"]] == ["林晚", "林晚", "周屿"], d["group_events"])
sync(group_after=max(ids), counts={"sms": {"林晚": 3, "周屿": 1}, "gift": {}})
ok("上限(3)" in gsend(lin, gid, "还是上限"), "cap after bot took them")
ok("已发到" in gsend(zy, gid, "第二条") and "2/3" in flash(zy), "zy counted once: " + flash(zy))

# 混乱效果：别人看到被改过的，发件人看原文；落款错乱换成别人
sync(group_after=max(ids), chaos={"loseContent": 100}, counts={"sms": {"林晚": 0, "周屿": 0}, "gift": {}})
ok("已发到" in gsend(sz, gid, "这是一句很长很长的话啊"), "sz send")
ok("这是一句很长很长的话啊" in chat(sz, gid), "sender sees original")
ok("……" in chat(zy, gid) and "这是一句很长很长的话啊" not in chat(zy, gid), "others see eroded")
sync(group_after=max(ids), chaos={"mistakenSignature": 100}, counts={"sms": {"沈知意": 0}, "gift": {}})
gsend(sz, gid, "换落款测试")
row = c.execute("SELECT signature FROM phone_group_msgs WHERE content='换落款测试'").fetchone()
ok(row["signature"] not in ("沈知意", ""), "signature swapped")

# 化名：别人只看到化名；自己看到提示；不能冒用名单里的名字
sync(group_after=max(ids), counts={"sms": {}, "gift": {}})
ok("不能用" in gsend(sz, gid, "冒充", alias="周屿"), "alias cannot be roster name")
ok("已发到" in gsend(sz, gid, "猜猜我是谁", alias="小狐狸"), "alias send")
zc = chat(zy, gid); seg = zc.split("猜猜我是谁")[0][-400:]
ok("小狐狸" in seg and "沈知意" not in seg, "alias hides real name")
ok("以化名「小狐狸」发送" in chat(sz, gid), "sender sees alias tag")

# 拉黑：周屿拉黑沈知意 → 真名发言看不到，化名发言照样看得到
sync(group_after=max(ids), blocks=[{"blocker": "周屿", "blocked": "沈知意", "silent": True, "since": 1}])
zc = chat(zy, gid)
ok("换落款测试" not in zc and "这是一句" not in zc and "猜猜我是谁" in zc, "blocked real-name msgs hidden")
ok("换落款测试" in chat(lin, gid), "others still see")

# 公开播报
sync(group_after=max(ids), chaos={"publicChance": 100}, public=True)
gsend(lin, gid, "大家晚安")
pub = sn.get("/p/me/public").get_data(as_text=True)
ok("群聊「天台小分队」" in pub and "大家晚安" in pub, "public broadcast")
sync(group_after=max(ids))

# 拉人：苏念进群后只看到之后的消息；改名；退群
ok("拉进群" in manage(zy, gid, "add", "苏念"), "add")
ok("已经在群里" in manage(zy, gid, "add", "苏念"), "add twice")
sc = chat(sn, gid); ok("周屿 拉 苏念 进了群" in sc and "今晚天台见" not in sc, "new member sees only after join")
ok("群名已修改" in manage(sn, gid, "rename", "夜猫子"), "rename")
ok("夜猫子" in lin.get("/p/me").get_data(as_text=True) and "苏念 把群名改成了「夜猫子」" in text_of(chat(lin, gid)), "renamed")
ok("已退出" in manage(sz, gid, "leave"), "leave")
ok(f"/p/me/g/{gid}" not in sz.get("/p/me").get_data(as_text=True) and sz.get(f"/p/me/g/{gid}").status_code == 302, "left: gone")
ok("沈知意 退出了群聊" in text_of(chat(lin, gid)), "leave notice")
ok("不在这个群" in gsend(sz, gid, "我还能发吗"), "left cannot send")

# 群聊不能送礼：按私聊接口往群 key 送也不行
lin.post("/p/me/send", data={"csrf": lin.csrf, "to": f"__group__{gid}", "text": "x", "gift_name": "花", "kind": "gift"})
ok("未找到收件人" in flash(lin), "no gift to group: " + flash(lin))

# 每天最多建 5 个群
for i in range(5):
    ok(isinstance(create(sn, ["周屿", "林晚"], name=f"群{i}"), int), "create more")
ok("明天再来" in create(sn, ["周屿", "林晚"], name="群6"), "daily create cap")

# 管理员删群消息
adm = app.test_client(); adm.get("/p/ADMINCODE1"); adm.get("/p/admin")
with adm.session_transaction() as s: t = s["phone_csrf"]
mid = c.execute("SELECT id FROM phone_group_msgs WHERE content='大家晚安'").fetchone()[0]
r = adm.post("/p/admin/delete", data={"target": f"group:{mid}"}, headers={"X-CSRF": t})
ok(r.get_json()["ok"], r.get_json())
ok("大家晚安" not in chat(zy, gid) and "大家晚安" not in sn.get("/p/me/public").get_data(as_text=True), "deleted")
print("ALL OK")
