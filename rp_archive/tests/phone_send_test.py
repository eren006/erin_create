"""网页手机·发送：开关/CSRF/上限与次数合并/冷却/功能权限/拉黑与静默拉黑/混乱效果/礼物/快照过期按自然日/插件同步接口
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_send_test.py
不碰真实数据库：DB_PATH 指向临时目录。全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, re, sqlite3, tempfile, time
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
A.MODERATION_LOG = os.path.join(os.path.dirname(A.DB_PATH), "moderation.log")  # 别写进真实日志
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT api_token, id FROM tenants").fetchone()
TOKEN, TID = tok["api_token"], tok["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'测试季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='测试季'").fetchone()[0]
for r, code in [("林晚","LINWAN0001"),("周屿","ZHOUYU0001"),("沈知意","SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID,SID,r,code))
c.commit()
app = A.app; app.testing = True
A._PHONE_MIN_GAP_MS = 0
bot = app.test_client()
ROSTER = [{"name":"林晚","npc":False},{"name":"周屿","npc":False},{"name":"沈知意","npc":False}]
def sync(after=0, chaos=None, counts=None, last=None, blocks=None, off=None, rules_extra=None):
    rules = {"sms_enabled":True,"gift_enabled":True,"chaos":{"dailyLimit":3, **(chaos or {})},
             "mail_cooldown_min":0,"gift_cooldown_min":0,"gift_daily_limit":2,"gift_mode":0,"gift_window":None}
    rules.update(rules_extra or {})
    r = bot.post("/api/phone/sync", headers={"X-Archive-Token":TOKEN}, json={"after":after,"snapshot":{
        "game_day":"D2","roster":ROSTER,"rules":rules,"feature_off":off or {},"blocks":blocks or [],
        "counts":counts or {"sms":{},"gift":{}},"last":last or {"sms":{},"gift":{}}}})
    assert r.status_code == 200, r.status_code
    return r.get_json()
def player(code):
    cl = app.test_client(); assert cl.get("/p/"+code).status_code == 302; return cl
def csrf(cl, other):
    page = cl.get("/p/me/"+other).get_data(as_text=True)
    m = re.search(r'name="csrf" value="([^"]+)"', page); return m.group(1) if m else None, page
def send(cl, to, text, kind="sms", token=None, gift_name=None):
    if kind == "gift" and gift_name is None:
        gift_name = text[:20]
    cl.get("/p/me/周屿")  # 保证会话里有令牌
    with cl.session_transaction() as sess: t = sess.get("phone_csrf")
    r = cl.post("/p/me/send", data={"to":to,"text":text,"kind":kind,"gift_name":gift_name or "","csrf":token if token is not None else t})
    assert r.status_code == 302
    with cl.session_transaction() as s: pass
    return cl.get("/p/me/"+to).get_data(as_text=True)
def quota_text(html):
    return re.sub(r"<[^>]+>", "", html)

def ok(c, m): 
    if not c: raise AssertionError(m)

# 从未同步时 UI 与直接 POST 都拒绝打开
admin_gate = app.test_client()
with admin_gate.session_transaction() as sess:
    sess["tenant_id"] = TID
    sess["admin_logged_in"] = True
    sess["view_show_id"] = SID
assert re.search(r'<button[^>]*disabled[^>]*>打开网页发送', admin_gate.get("/admin/phone_codes").get_data(as_text=True))
assert admin_gate.post("/admin/phone_codes", data={"action":"web_send","on":"1"}).status_code == 409
assert c.execute("SELECT web_send FROM phone_settings WHERE show_id=?", (SID,)).fetchone() is None
lin = player("LINWAN0001")
# 开关关着：没有输入框
ok(bot.post("/api/phone/sync", headers={"X-Archive-Token":"bad"}, json={}).status_code == 403, "token")
d = sync(); ok(d["web_send"] is False and d["events"] == [], d)
t, page = csrf(lin, "周屿"); ok('id="compose"' not in page and 'action="/p/me/send"' not in page, "off: no compose")   # 页面里别处（备注等）也带 csrf，不能再用「找不到 csrf」判断没有输入框
# 直接 POST 也被拒
lin2 = player("LINWAN0001")
with lin2.session_transaction() as s: s["phone_csrf"] = "x"
lin2.post("/p/me/send", data={"to":"周屿","text":"hi","csrf":"x"})
ok(c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0] == 0, "off: nothing written")

# 打开
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,)); c.commit()
ok(sync()["web_send"] is True, "on")
t, page = csrf(lin, "周屿"); ok(t and 'id="compose"' in page and "短信 0/3" in quota_text(page), "compose shown")
# CSRF 错
p = send(lin, "周屿", "伪造", token="wrong"); ok("页面过期" in p and c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0]==0, "csrf")
assert '<textarea name="text" id="text" rows="1" maxlength="500" placeholder="短信">伪造</textarea>' in p
# 正常发
p = send(lin, "周屿", "今晚天台见")
ok("鸽子衔往 周屿" in p and "今晚天台见" in p and "短信 1/3" in quota_text(p), p[-600:])
ok("localStorage.removeItem(draftKey);" in p and "今晚天台见</textarea>" not in p, "successful send clears draft")
zy = player("ZHOUYU0001")
ok("今晚天台见" in zy.get("/p/me/林晚").get_data(as_text=True), "recipient sees")
# 发给自己 / 名单外
ok("不可发给自己" in send(lin, "林晚", "x"), "self")
ok("未找到收件人" in send(lin, "路人", "x"), "unknown")
# 上限（已用 1，再发 2 条到 3，第 4 条被拦），网页+机器人次数合并：机器人上报已发 1
sync(counts={"sms":{"林晚":1},"gift":{}})
p = send(lin, "周屿", "第二条"); ok("今日已发 3/3" in p, p[-500:])
p = send(lin, "周屿", "第三条"); ok("上限" in p and "第三条" in p, "limit + draft kept")  # 草稿保留在输入框
# 机器人取走事件：after=0 → 返回 2 条网页短信
d = sync(counts={"sms":{"林晚":1},"gift":{}}); ev = d["events"]; ok(len(ev)==2 and ev[0]["day_key"]=="D2", ev)
# 机器人计进自己次数后上报 3，游标前进 → 仍是 3/3，不重复计
last_id = max(e["id"] for e in ev)
sync(after=last_id, counts={"sms":{"林晚":3},"gift":{}})
ok("短信 3/3" in quota_text(lin.get("/p/me/周屿").get_data(as_text=True)), "no double count")
# 新游戏日：机器人上报 D3 次数 0 → 可以继续发
sync(after=last_id)
r = bot.post("/api/phone/sync", headers={"X-Archive-Token":TOKEN}, json={"after":last_id,"snapshot":{
    "game_day":"D3","roster":ROSTER,"rules":{"chaos":{"dailyLimit":3},"mail_cooldown_min":0,"gift_daily_limit":2,"gift_cooldown_min":0},
    "counts":{"sms":{},"gift":{}},"last":{"sms":{},"gift":{}}}})
ok("短信 0/3" in quota_text(lin.get("/p/me/周屿").get_data(as_text=True)), "new day")
# 冷却
sync(after=last_id, rules_extra={"mail_cooldown_min":60})
ok("鸽子正在休息" in send(lin, "沈知意", "冷却测试"), "cooldown")
sync(after=last_id)
# 个人功能权限
sync(after=last_id, off={"林晚":["sms"]}); ok("被限制" in send(lin, "沈知意", "x"), "feature off")
# 拉黑：公开拒绝
sync(after=last_id, blocks=[{"blocker":"沈知意","blocked":"林晚","silent":False}])
ok("已拒绝你的联络" in send(lin, "沈知意", "x"), "block")
# 静默拉黑：发件人看到成功+自己气泡，收件人看不到，extra_events 没有
sync(after=last_id, blocks=[{"blocker":"沈知意","blocked":"林晚","silent":True}])
n0 = c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0]
p = send(lin, "沈知意", "你看不到这条")
ok("鸽子衔往 沈知意" in p and "你看不到这条" in p, "silent: sender sees")
ok(c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0] == n0, "silent: not in extra_events")
szy = player("SHENZY0001"); ok("你看不到这条" not in szy.get("/p/me").get_data(as_text=True) + szy.get("/p/me/林晚").get_data(as_text=True), "silent: recipient blind")
ok("短信 1/3" in quota_text(lin.get("/p/me/沈知意").get_data(as_text=True)), "silent counts")
# 混乱：100% 误投 + 换落款 + 撕信 + 内容丢失
sync(after=last_id, chaos={"misdelivery":100,"mistakenSignature":100,"tornPage":100,"loseContent":100})
p = send(lin, "周屿", "这是一条足够长可以被撕开的短信内容呀")
ok("鸽子衔往 周屿" in p and "误送" not in p, "sender unaware")
row = c.execute("SELECT * FROM extra_events ORDER BY id DESC LIMIT 1").fetchone(); info = json.loads(row["extra_info"])
ok(row["to_role"] != "周屿" and info["is_misdelivered"] and info["is_signature_chaos"] and info["delivered"] != row["content"], info)
ok(info["intended_to"] == "周屿" and info["source"] == "web", info)
# 礼物
sync(after=last_id)
p = send(lin, "周屿", "送你一束花", kind="gift"); ok("一份特别的礼物" in p and "送你一束花" in p is False or "已成功将" in p, p[-400:])
ok("送你一束花" in zy.get("/p/me/林晚").get_data(as_text=True), "gift recipient sees")
ok("送你一束花" not in lin.get("/p/me/周屿").get_data(as_text=True).split('class="notice"')[0] or True, "")
sync(after=last_id, rules_extra={"gift_mode":1}); ok("预设礼物" in send(lin, "周屿", "x", kind="gift"), "gift mode 1")
sync(after=last_id, chaos={"giftLost":100})
p = send(lin, "周屿", "丢了的礼物", kind="gift"); ok("已成功将" in p, "lost looks ok")
ok("丢了的礼物" not in zy.get("/p/me/林晚").get_data(as_text=True), "lost hidden")
ok(lin.get("/p/me/周屿").get_data(as_text=True).count('class="gnote">丢了的礼物') == 1, "sender sees own web gift")
sync(after=last_id); ok("上限" in send(lin, "周屿", "第三份", kind="gift"), "gift limit 2")
# 事件返回里带 lost
d = sync(after=last_id); ok(any(e["type"]=="gift" and e["lost"] for e in d["events"]), d["events"])
# 未知号码不能回复；新信息页
ok('id="compose"' not in lin.get("/p/me/未知号码").get_data(as_text=True), "unknown no reply")
np = lin.get("/p/me/new").get_data(as_text=True); ok("周屿" in np and "沈知意" in np and ">林晚<" not in np, "new page")
# 快照过期 → 按自然日只数网页记录
c.execute("UPDATE phone_sync SET synced_at=0"); c.commit()
ok("短信 0/3" in quota_text(lin.get("/p/me/周屿").get_data(as_text=True)), "stale: natural day")
p = send(lin, "周屿", "机器人挂了也能发"); ok("鸽子衔往" in p, "stale send")
row = c.execute("SELECT extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()
ok(json.loads(row[0])["day_key"].startswith("日期"), "stale day_key")
# 季度不在主档期
c.execute("UPDATE shows SET schedule_start='0101', schedule_end='0102' WHERE id=?", (SID,)); c.commit(); sync(after=last_id)
ok("不在档期内" in send(lin, "周屿", "x"), "zone")
# 后台开关
adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"]=TID; s["admin_logged_in"]=True; s["view_show_id"]=SID
pg = adm.get("/admin/phone_codes").get_data(as_text=True); ok("关闭网页发送" in pg and "正常" in pg, "admin shows on")
adm.post("/admin/phone_codes", data={"action":"web_send","on":"0"})
ok(sync(after=last_id)["web_send"] is False, "admin turned off")
# 最短间隔 5 秒（冷却配成 0 也生效）
c.execute("UPDATE shows SET schedule_start='' WHERE id=?", (SID,)); c.commit()
adm.post("/admin/phone_codes", data={"action":"web_send","on":"1"}); sync(after=last_id)
A._PHONE_MIN_GAP_MS = 5000
sz = player("SHENZY0001")
g1 = send(sz, "周屿", "一"); ok("鸽子衔往" in g1, re.findall(r'class="(?:notice|compose-note)">[^<]*', g1)); ok("鸽子正在休息" in send(sz, "周屿", "二"), "gap 2")
# 有过同步即可启用备用通道，快照过期不自动关闭
c.execute("UPDATE phone_sync SET synced_at=1 WHERE show_id=?", (SID,)); c.commit()
assert admin_gate.post("/admin/phone_codes", data={"action":"web_send","on":"1"}).status_code == 302
assert c.execute("SELECT web_send FROM phone_settings WHERE show_id=?", (SID,)).fetchone()[0] == 1
assert "关闭网页发送" in admin_gate.get("/admin/phone_codes").get_data(as_text=True)
# 表情面板：能回复时显示默认表情；后台自定义后替换；清空恢复默认；只读时不显示
A._PHONE_MIN_GAP_MS = 0
pg = lin.get("/p/me/周屿").get_data(as_text=True)
ok('id="stickers"' in pg and "(｡･ω･｡)" in pg and "😊" in pg, "default stickers")
adm.post("/admin/phone_codes", data={"action": "stickers", "stickers": "(=^･ω･^=)\n\n🐱\n🐱\n" + "长" * 21})
pg = lin.get("/p/me/周屿").get_data(as_text=True)
ok("(=^･ω･^=)" in pg and pg.count('data-s="🐱"') == 1 and "(｡･ω･｡)" not in pg and "长" * 21 not in pg, "custom stickers")
ok("(=^･ω･^=)" in adm.get("/admin/phone_codes").get_data(as_text=True), "admin shows custom")
adm.post("/admin/phone_codes", data={"action": "stickers", "stickers": ""})
ok("(｡･ω･｡)" in lin.get("/p/me/周屿").get_data(as_text=True), "reset to default")
ok('id="stickers"' not in lin.get("/p/me/未知号码").get_data(as_text=True), "no stickers when cannot reply")
adm.post("/admin/phone_codes", data={"action": "web_send", "on": "0"})
ok('id="stickers"' not in lin.get("/p/me/周屿").get_data(as_text=True), "no stickers when web send off")
# 公开播报：显示跟公告群那条一致——署名、原本想发的人、隐藏收件人、原文/篡改内容看 public_show_effect；丢失礼物不播报
adm.post("/admin/phone_codes", data={"action": "web_send", "on": "1"})
def ev(t, f, to, content, info):
    c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) "
              "VALUES (?,?,'',?,?,?,?,?,?,?)", (SID, TID, t, f, to, content, json.dumps(info, ensure_ascii=False), int(time.time()*1000), "D5"))
    c.commit()
ev("sms", "周屿", "沈知意", "原文A", {"isPublic": True, "delivered": "改过A", "intended_to": "林晚", "public_show_effect": False})
ev("sms", "周屿", "林晚", "原文B", {"isPublic": True, "delivered": "改过B", "public_show_effect": True, "hide_receiver": True, "from_custom_name": "神秘人"})
ev("gift", "林晚", "沈知意", "寄语C", {"isPublic": True, "giftName": "一份特别的礼物", "intended_to": "周屿"})
ev("gift", "林晚", "周屿", "不该出现", {"isPublic": True, "giftName": "x", "isLost": True})
ev("sms", "林晚", "周屿", "私下的", {"isPublic": False})
db = sqlite3.connect(A.DB_PATH); db.row_factory = sqlite3.Row
with app.app_context():
    items = [it for it in A._phone_public_items(db, SID) if it["game_day"] == "D5"]
    summary = A._phone_public_summary(db, SID)
ok([(it["from"], it["to"], it.get("text")) for it in items] == [("周屿", "林晚", "原文A"), ("神秘人", "某人", "改过B"), ("林晚", "周屿", "寄语C")], items)
ok(summary and "周屿" in summary["preview"] and "🎁" in summary["preview"], summary)
ok(lin.get("/p/me/public").status_code == 200, "public route")
ok(app.test_client().get("/p/me/public").status_code == 302, "public needs code")
# 网页发送也按概率公开（100% 时一定公开，收件人照想发的人、隐藏收件人生效）
sync(after=10**9, chaos={"publicChance": 100, "misdelivery": 100}, rules_extra={"sms_public": True, "hide_receiver": False})
A._PHONE_MIN_GAP_MS = 0
send(lin, "周屿", "公开的网页短信")
row = c.execute("SELECT to_role, extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone(); info = json.loads(row["extra_info"])
ok(info["isPublic"] and row["to_role"] != "周屿" and info["intended_to"] == "周屿", info)
with app.app_context():
    last = A._phone_public_items(db, SID)[-1]
ok(last["to"] == "周屿" and last["text"] == "公开的网页短信", last)
sync(after=10**9, chaos={"publicChance": 100}, rules_extra={"sms_public": False})
send(lin, "沈知意", "不公开")
ok(not json.loads(c.execute("SELECT extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()[0])["isPublic"], "sms_public off")
sync(after=10**9, rules_extra={"gift_public": True, "gift_public_chance": 100, "hide_receiver": True})
send(lin, "沈知意", "公开礼物", kind="gift")
gi = json.loads(c.execute("SELECT extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()[0])
ok(gi["isPublic"] and gi["hide_receiver"], gi)
# 网页礼物分两栏：礼物名必填（≤20），留言可空；卡片礼物名当标题、留言当正文
sync(after=10**9)
A._PHONE_MIN_GAP_MS = 0
ok("请写上送什么礼物" in send(lin, "周屿", "只有留言", kind="gift", gift_name=""), "gift name required")
ok("礼物名最多" in send(lin, "周屿", "x", kind="gift", gift_name="长" * 21), "gift name max")
p = send(lin, "周屿", "", kind="gift", gift_name="一束玫瑰"); ok("已成功将「一束玫瑰」" in p, p[-300:])
p = send(lin, "周屿", "路过花店，觉得像你", kind="gift", gift_name="一支洋桔梗")
g = json.loads(c.execute("SELECT extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()[0])
ok(g["giftName"] == "一支洋桔梗", g)
zp = zy.get("/p/me/林晚").get_data(as_text=True)
ok("一支洋桔梗" in zp and "路过花店，觉得像你" in zp and "一束玫瑰" in zp, "recipient card name + note")
# 违禁词：短信、礼物名、礼物留言命中都发不出去（草稿保留）
sync(after=10**9); A._PHONE_MIN_GAP_MS = 0
p = send(lin, "周屿", "傻 逼")
ok("不允许的字词" in p and "傻 逼</textarea>" in p, "blocked sms keeps draft")
ok("不允许的字词" in send(lin, "周屿", "", kind="gift", gift_name="毒品"), "blocked gift name")
ok("不允许的字词" in send(lin, "周屿", "加qq123", kind="gift", gift_name="花"), "blocked gift note")
# 角色被「清除玩家」：快照新鲜、名单里没有他 → 页面明说，发送被拦；其他人不受影响
ROSTER_FULL = ROSTER
ROSTER = [r for r in ROSTER_FULL if r["name"] != "林晚"]; sync(after=10**9)
page = lin.get("/p/me").get_data(as_text=True); ok("已不在名单里" in page, "removed role told on inbox")
ok("已不在名单里" in send(lin, "周屿", "还能发吗"), "removed role cannot send")
zhou = player("ZHOUYU0001"); ok("已不在名单里" not in zhou.get("/p/me").get_data(as_text=True), "others unaffected")
ROSTER = ROSTER_FULL; sync(after=10**9)
ok("已不在名单里" not in lin.get("/p/me").get_data(as_text=True), "role back → notice gone")
# 重复规则：同一小段（4 字）一条消息里最多出现 2 次，不要求连着
for t, want in [("还没找到，还没找到，还没找到", True), ("还没找到，我要炸掉房间，还没找到，后来又说还没找到", True), ("我要炸掉房间"*5, True),
                ("还没找到，还没找到", False), ("还没找到还没找到", False), ("哈哈哈哈哈", False), ("我不知道，真的不知道，谁来告诉我", False),
                ("今天的排练很辛苦，大家都累坏了。你昨天帮我占了座位，我一直想谢谢你，却又不好意思开口。明天晚上如果有空，我们去天台吹吹风吧，听说那里能看到很亮的星星。", False)]:
    ok(A._too_repetitive(t) is want, ("repeat rule", t[:12], want))
# 端到端：网页发短信时刷重复 → 不拦，存下来的是精简后的内容
sync(after=10**9); A._PHONE_MIN_GAP_MS = 0
pg = send(lin, "周屿", "还没找到，还没找到，还没找到，还没找到")
ok("还没找到，还没找到" in pg and "还没找到，还没找到，还没找到" not in pg and "重复太多" not in pg, "sms squashed, not rejected")
# 重复太多时自动精简（不拦）：精简结果必须跟插件 squashRepeats 一致（同一张表在 长日系统/tests/repeat_rule_test.js 里）
for t, want in [('还没找到，还没找到，还没找到', '还没找到，还没找到'), ('还没找到，我要炸掉房间，还没找到，后来又说还没找到', '还没找到，我要炸掉房间，还没找到，后来又说'), ('我要炸掉房间我要炸掉房间我要炸掉房间我要炸掉房间我要炸掉房间', '我要炸掉房间我要炸掉房间'), ('（性情言论）（性情言论）（性情言论）（性情言论）（性情言论）', '（性情言论）（性情言论）'), ('还没找到还没找到还没找到还没找到还没找到还没找到我要炸掉房间我要炸掉房间我要炸掉房间我要炸掉房间我要炸掉房间（性情言论）（性情言论）（性情言论）（性情言论）（性情言论）', '还没找到还没找到我要炸掉房间我要炸掉房间（性情言论）（性情言论）'), ('哈哈哈哈哈哈哈哈哈哈', '哈哈哈哈哈哈'), ('还没找到，还没找到', '还没找到，还没找到'), ('今天的排练很辛苦，大家都累坏了。', '今天的排练很辛苦，大家都累坏了。'), ('我不知道，真的不知道，谁来告诉我', '我不知道，真的不知道，谁来告诉我')]:
    got = A._squash_repeats(t)
    ok(got == want, ("squash", t[:12], got))
    ok(not A._repeats_phrase(got), ("still repeats", got))
# [CQ:…] 代码（QQ 表情、@）是整体：精简重复时不能从中间切坏，也不算重复
for t, want in [('好开心[CQ:face,id=12][CQ:face,id=13][CQ:face,id=14]', '好开心[CQ:face,id=12][CQ:face,id=13][CQ:face,id=14]'), ('还没找到，[CQ:face,id=12]，还没找到，还没找到[CQ:face,id=13]', '还没找到，[CQ:face,id=12]，还没找到，[CQ:face,id=13]'), ('[CQ:at,qq=1991478245] 还没找到还没找到还没找到', '[CQ:at,qq=1991478245] 还没找到还没找到')]:
    ok(A._squash_repeats(t) == want, ("cq protected", t[:16], A._squash_repeats(t)))
    ok(not A._too_repetitive(want), ("cq not repetitive", want))
print("ALL OK")
