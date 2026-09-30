"""网页手机·实名拉黑（对话页「⋯」菜单）：新插件才显示、只对名单里的真人、拉黑立刻对网页发送生效、满 2 小时才能解除、
交给机器人后按回报标 done、再拉一次不重新计时、匿名对话/未知号码/自己没有这个菜单
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_block_test.py ；全部通过时最后一行打印 ALL OK。
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
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,))
c.commit()
app = A.app; app.testing = True
A._PHONE_MIN_GAP_MS = 0
ROSTER = [{"name": n, "npc": False} for n in ("林晚", "周屿", "沈知意")]
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def sync(blocks=None, block_write=True, done=None):
    snap = {"game_day": "D2", "roster": ROSTER, "feature_off": {}, "blocks": blocks or [],
            "rules": {"sms_enabled": True, "gift_enabled": True, "chaos": {"dailyLimit": 20}, "mail_cooldown_min": 0,
                      "gift_cooldown_min": 0, "gift_daily_limit": 20, "gift_mode": 0, "gift_window": None},
            "counts": {"sms": {}, "gift": {}}, "last": {"sms": {}, "gift": {}}}
    if block_write:
        snap["block_write"] = True
    r = app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN},
                               json={"after": 10 ** 9, "snapshot": snap, "block_ops_done": done or []})
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def menu(cl, other):
    return cl.get("/p/me/" + other).get_data(as_text=True).split('id="threadMenu"')[1].split("</dialog>")[0]
def block(cl, target, action="block", silent=False, csrf=None):
    cl.post("/p/me/block", data={"csrf": csrf or cl.csrf, "target": target, "action": action, "silent": "1" if silent else ""})
    with cl.session_transaction() as s: return s.get("phone_flash") or ""
def send(cl, to, text):
    cl.post("/p/me/send", data={"to": to, "text": text, "kind": "sms", "csrf": cl.csrf})
    with cl.session_transaction() as s: return s.get("phone_flash") or ""

lin, zy, sz = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001")

# 旧插件（快照没有 block_write）：菜单里没有拉黑，直接 POST 也不行
sync(block_write=False)
ok("静默拉黑" not in menu(lin, "周屿"), "old plugin: no menu")
ok("不能拉黑" in block(lin, "周屿"), "old plugin: rejected")

# 新插件：名单里的真人有；自己、未知号码没有
sync()
m = menu(lin, "周屿"); ok("拉黑" in m and "静默拉黑" in m and "解除拉黑" not in m, "menu shown")
ok("静默拉黑" not in menu(lin, "林晚"), "no menu for self")
ok("静默拉黑" not in menu(lin, "未知号码"), "no menu for unknown")
ok("不能拉黑" in block(lin, "路人"), "not in roster")
ok("页面过期" in block(lin, "周屿", csrf="bad"), "csrf")

# 沈知意静默拉黑林晚：立刻对网页生效——林晚发过去看起来成功，沈知意收不到
ok("已拉黑「林晚」（静默）" in block(sz, "林晚", silent=True), "silent block")
m = menu(sz, "林晚"); ok("解除拉黑" in m and "还要等 120 分钟" in m and "disabled" in m and "已拉黑（静默）" in m, m)
n0 = c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0]
send(lin, "沈知意", "你在吗")
ok(c.execute("SELECT COUNT(*) FROM extra_events").fetchone()[0] == n0, "silent: not delivered")
ok("你在吗" not in sz.get("/p/me/林晚").get_data(as_text=True), "silent: recipient blind")
# 还没满 2 小时不能解除
ok("还要等" in block(sz, "林晚", action="unblock"), "unblock too early")
# 换成不静默：不重新计时；林晚再发被明确拒绝
ok("不静默" in block(sz, "林晚"), "switch to loud")
ok("已经拉黑" in block(sz, "林晚"), "same mode again")
ok("已拒绝你的联络" in send(lin, "沈知意", "x"), "loud block tells sender")

# 交给机器人：回包里有这两条；机器人写进名单（下一份快照带上 since）并回报 done
d = sync()
ops = d["block_ops"]; ok([(o["action"], o["silent"]) for o in ops] == [("block", True), ("block", False)], ops)
since = ops[0]["ts"]
d = sync(blocks=[{"blocker": "沈知意", "blocked": "林晚", "silent": False, "since": since}], done=[o["id"] for o in ops])
ok(d["block_ops"] == [] and "还要等" in menu(sz, "林晚") and "已拉黑（不静默）" in menu(sz, "林晚"), "applied")

# 满 2 小时：可以解除；解除立刻对网页生效，交给机器人
old = int(time.time() * 1000) - 2 * 3600 * 1000 - 1000
sync(blocks=[{"blocker": "沈知意", "blocked": "林晚", "silent": False, "since": old}])
m = menu(sz, "林晚"); ok("解除拉黑" in m and "还要等" not in m, m)
ok("已取消拉黑" in block(sz, "林晚", action="unblock"), "unblock")
ok("静默拉黑" in menu(sz, "林晚"), "menu back to block options")
send(lin, "沈知意", "又来了")
ok(c.execute("SELECT COUNT(*) FROM extra_events WHERE content='又来了' AND to_role='沈知意'").fetchone()[0] == 1, "delivered after unblock")
ok("你并没有拉黑" in block(sz, "林晚", action="unblock"), "nothing to unblock")
d = sync(blocks=[{"blocker": "沈知意", "blocked": "林晚", "silent": False, "since": old}])
ok([o["action"] for o in d["block_ops"]] == ["unblock"], d["block_ops"])

# 群里早就拉黑了（快照里有，since 很久以前）：网页显示已拉黑，可以直接解除
sync(blocks=[{"blocker": "周屿", "blocked": "沈知意", "silent": True, "since": old}], done=[o["id"] for o in d["block_ops"]])
ok("已拉黑（静默）" in menu(zy, "沈知意") and "还要等" not in menu(zy, "沈知意"), "group block visible")

# 匿名对话没有实名拉黑（只有自己的「拉黑并结束」）
c.execute("INSERT INTO phone_aliases (show_id, owner_role, target_role, alias_name, created_at) VALUES (?,?,?,?,?)",
          (SID, "林晚", "周屿", "小狐狸", int(time.time() * 1000))); c.commit()
ok("静默拉黑" not in menu(lin, "周屿＠小狐狸"), "alias owner: no real-name block")
ok("静默拉黑" not in menu(zy, "小狐狸"), "alias recipient: no real-name block")
print("ALL OK")
