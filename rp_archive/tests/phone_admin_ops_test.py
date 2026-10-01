"""网页手机管理身份：管理员手机码进门、以任意角色视角查看（带真实情况）、只读、各类删除、权限隔离、重置失效
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_admin_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, io, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
from PIL import Image

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
A.MOMENT_IMAGE_DIR = os.path.join(tmp, "moment_images")
A.MODERATION_LOG = os.path.join(tmp, "moderation.log")
A.init_db()
A._MOMENT_COMMENT_GAP_MS = 0; A._AVATAR_GAP_MS = 0
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
def ev(t, f, to, content, info):
    c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) "
              "VALUES (?,?,'',?,?,?,?,?,?,'D1')", (SID, TID, t, f, to, content, json.dumps(info, ensure_ascii=False), int(time.time() * 1000)))
ev("sms", "林晚", "沈知意", "明天早餐一起吗", {"delivered": "明天早餐一起吗", "signature": "落款：林晚", "intended_to": "周屿", "is_misdelivered": True})
ev("sms", "周屿", "林晚", "原来的话", {"delivered": "被改的话", "signature": "落款：周屿", "is_content_chaos": True})
ev("gift", "周屿", "林晚", "给你", {"giftName": "一束花", "isPublic": True, "intended_to": "林晚"})
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)

adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID
adm.post("/admin/phone_codes", data={"action": "admin_code"})
ACODE = c.execute("SELECT code FROM phone_admin_codes WHERE show_id=?", (SID,)).fetchone()[0]
ok(ACODE in adm.get("/admin/phone_codes").get_data(as_text=True), "admin code shown in backend")


m = app.test_client(); m.get("/p/" + ACODE)
m.get("/p/admin")
with m.session_transaction() as s: m.csrf = s["phone_csrf"]
rpg = {"currencies": [{"name": "金币", "count": 5}], "presets": [], "items": [{"name": "钥匙", "count": 1, "desc": "", "uses": None, "effect": ""}],
       "attrs": [{"name": "体力", "value": 3, "min": 0, "max": 10, "desc": ""}], "equips": []}
c.execute("INSERT INTO phone_reports (show_id, role, data, updated_at) VALUES (?,?,?,?)", (SID, "林晚", json.dumps({"rpg": rpg}), int(time.time())))
c.commit()
pg = m.get("/p/admin/as/林晚/character").get_data(as_text=True)
ok("功能开关" in pg and "发放 / 扣除" in pg, "controls shown")
pg2 = m.get("/p/admin/as/林晚/character?view=attrs").get_data(as_text=True); ok("设为此值" in pg2, "attr form")
def post(**kw):
    kw.setdefault("csrf", m.csrf); return m.post("/p/admin/as/林晚/op", data=kw)
post(kind="attr", name="体力", value="7"); post(kind="item", name="金币", value="3", sign="-"); post(kind="feature", name="sms", value="off")
post(kind="attr", name="体力", value="abc"); post(kind="feature", name="foo", value="off"); post(kind="item", name="x", value="0", sign="+")
post(kind="attr", name="体力", value="1", csrf="bad")
ok(m.post("/p/admin/as/不存在/op", data=dict(kind="attr", name="a", value="1", csrf=m.csrf)).status_code == 302, "unknown role")
ok(c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 3, "only 3 valid ops stored")
lin = app.test_client(); lin.get("/p/LINWAN0001"); lin.get("/p/me")
with lin.session_transaction() as s: lc = s["phone_csrf"]
ok(lin.post("/p/admin/as/林晚/op", data=dict(kind="attr", name="体力", value="9", csrf=lc)).status_code == 302
   and c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 3, "player cannot post ops")
with app.app_context():
    db = A.get_db()
    ops = A._admin_ops_for_bot(db, SID, None); ok(len(ops) == 3 and ops[0]["kind"] == "attr" and ops[0]["value"] == "7", ops)
    ok(len(A._admin_ops_for_bot(db, SID, None)) == 3, "redelivered until done")
    left = A._admin_ops_for_bot(db, SID, [{"id": ops[0]["id"], "ok": True, "msg": "体力 3 → 7"}, {"id": ops[1]["id"], "ok": False, "msg": "背包里没有"}])
    ok([o["id"] for o in left] == [ops[2]["id"]], left)
pg = m.get("/p/admin/as/林晚/character").get_data(as_text=True)
ok("体力 3 → 7" in pg and "背包里没有" in pg and "待执行" in pg, "recent ops shown")

# ── 设置页：插件状态 / 参数 / 批量 ──
c.execute("DELETE FROM phone_admin_ops")
c.execute("INSERT OR REPLACE INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at) VALUES (?,?,?,?,?)",
          (SID, TID, json.dumps({"roster": [{"name": "林晚"}], "plugin": {"version": "1.9.2", "params": []}}), 0, int(time.time() * 1000))); c.commit()
pg = m.get("/p/admin/settings").get_data(as_text=True); ok("1.9.2" in pg and "需要" in pg and "升级到 1.10.4" in pg, "old plugin warned")
def sp(**kw):
    kw.setdefault("csrf", m.csrf); return m.post("/p/admin/settings/op", data=kw)
sp(kind="param", name="dailyLimit", value="9"); ok(c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 0, "old plugin rejects ops")
params = [{"id": "dailyLimit", "label": "寄信每日上限", "section": "寄信", "type": "num", "value": 5, "min": 0, "max": 999, "unit": "封", "note": ""},
          {"id": "t_sms", "label": "寄信功能", "section": "总开关", "type": "bool", "value": True},
          {"id": "lovemail_delivery_time", "label": "心动信派送时间", "section": "心动信", "type": "time", "value": "22:00"}]
c.execute("UPDATE phone_sync SET snapshot=?", (json.dumps({"plugin": {"version": "1.10.4", "params": params}}),)); c.commit()
pg = m.get("/p/admin/settings").get_data(as_text=True)
ok("插件 1.10.4" in pg and "寄信每日上限" in pg and "批量发放" in pg and "心动信派送时间" in pg, "settings page")
ok("设置" in m.get("/p/admin").get_data(as_text=True) and "插件 1.10.4" in m.get("/p/admin").get_data(as_text=True), "nav + chip on index")
sp(kind="param", name="dailyLimit", value="1000"); sp(kind="param", name="dailyLimit", value="x"); sp(kind="param", name="nope", value="1")
sp(kind="param", name="lovemail_delivery_time", value="25:00"); sp(kind="param", name="t_sms", value="maybe")
ok(c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 0, "bad params rejected")
sp(kind="param", name="dailyLimit", value="9"); sp(kind="param", name="t_sms", value="off"); sp(kind="param", name="lovemail_delivery_time", value="21:30")
sp(kind="bulk_item", name="金币", value="5", sign="+", scope="player"); sp(kind="bulk_attr", name="体力", value="2", sign="-", scope="all")
sp(kind="bulk_item", name="金币", value="0", sign="+")
rows = c.execute("SELECT role, kind, name, value FROM phone_admin_ops ORDER BY id").fetchall()
ok(len(rows) == 5, [tuple(r) for r in rows])
ok(tuple(rows[3]) == ("*player", "bulk_item", "金币", "5") and tuple(rows[4]) == ("*all", "bulk_attr", "体力", "-2"), [tuple(r) for r in rows])
ok(lin.post("/p/admin/settings/op", data=dict(kind="param", name="dailyLimit", value="1", csrf=lc)).status_code == 302
   and c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 5, "player cannot post settings")
ok(lin.get("/p/admin/settings").status_code == 302, "player cannot open settings")
pg = m.get("/p/admin/settings").get_data(as_text=True); ok("批量道具" in pg and "待执行" in pg, "settings recent ops")
# ── 发起官约 / 官电：旧版插件拒绝，1.10.6 才收；校验各种坏输入；排队的 value 是 JSON ──
c.execute("DELETE FROM phone_admin_ops")
def of(**kw):
    kw.setdefault("csrf", m.csrf); return m.post("/p/admin/settings/op", data=kw)
ok("发起官约 / 官电" in m.get("/p/admin/official").get_data(as_text=True) and "1.10.7" in m.get("/p/admin/official").get_data(as_text=True), "official form hidden for old plugin")
of(kind="official_call", day="D1", t1="14:00", t2="15:00", people=["林晚", "周屿"])
ok(c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 0, "old plugin rejects official")
c.execute("UPDATE phone_sync SET snapshot=?", (json.dumps({"plugin": {"version": "1.10.7", "params": params}}),)); c.commit()
pg = m.get("/p/admin/official").get_data(as_text=True); ok('name="people"' in pg and "林晚" in pg and "沈知意" in pg, "official form shown")
bad = [dict(kind="official_call", day="1", t1="14:00", t2="15:00", people=["林晚"]),            # 天数格式
       dict(kind="official_call", day="D1", t1="15:00", t2="14:00", people=["林晚"]),           # 结束早于开始
       dict(kind="official_call", day="D1", t1="14:00", t2="", people=["林晚"]),                # 缺结束
       dict(kind="official_appt", day="D1", t1="14:00", t2="15:00", place="", people=["林晚"]),  # 官约没地点
       dict(kind="official_appt", day="D1", t1="14:00", t2="15:00", place="咖啡 厅", people=["林晚"]),  # 地点带空格
       dict(kind="official_call", day="D1", t1="14:00", t2="15:00", people=[]),                 # 没人
       dict(kind="official_call", day="D1", t1="14:00", t2="15:00", people=["不存在的人"])]      # 陌生角色
for b in bad: of(**b)
ok(c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 0, "bad official rejected")
of(kind="official_appt", day="d2", t1="09:00", t2="10:30", place="咖啡厅", people=["林晚", "周屿", "林晚"])
of(kind="official_call", day="D3", t1="20:00", t2="21:00", place="忽略", people=["沈知意"])
rows = c.execute("SELECT role, kind, name, value FROM phone_admin_ops ORDER BY id").fetchall()
ok(len(rows) == 2 and rows[0]["kind"] == "official_appt" and rows[0]["name"] == "官约", [tuple(r) for r in rows])
v0, v1 = json.loads(rows[0]["value"]), json.loads(rows[1]["value"])
ok(v0 == {"day": "D2", "time": "09:00-10:30", "place": "咖啡厅", "participants": ["林晚", "周屿"]}, v0)
ok(v1 == {"day": "D3", "time": "20:00-21:00", "place": "", "participants": ["沈知意"]}, v1)
pg = m.get("/p/admin/settings").get_data(as_text=True); ok("发起官约" in pg and "D2 09:00-10:30 咖啡厅 林晚、周屿" in pg and "待执行" in pg, "official ops listed readable")
ok(lin.post("/p/admin/settings/op", data=dict(kind="official_call", day="D1", t1="14:00", t2="15:00", people=["林晚"], csrf=lc)).status_code == 302
   and c.execute("SELECT COUNT(*) FROM phone_admin_ops").fetchone()[0] == 2, "player cannot post official")

# ── 重复内容检测 ──
for t, want in [("哈哈哈哈哈哈哈", False), ("哈" * 12, True), ("我爱你我爱你我爱你", True), ("我爱你我爱你", False), ("好的好的好的", True),
                ("……………", False), ("今天天气不错，我们去散步吧。晚上一起吃饭？", False), ("ababab", True), ("", False)]:
    ok(A._too_repetitive(t) == want, (t, want))
ok(A._too_repetitive("睡" * 5 + "觉" * 5 + "".join(chr(0x4e00 + i) for i in range(70))) is False, "varied long text ok")
ok(A._too_repetitive("a b " * 40) is True, "long low-variety text")

# ── 升级规则键：保存 / 下发给机器人 ──
lv = {"enabled": True, "max_level": 20, "level_up_rules": {"1": {"description": "一级", "consume": {}, "rewards": {}, "success_rate": 100}}}
r = adm.post("/admin/rpg/save", json={"level_up_rules": lv}); ok(r.get_json()["ok"], "save level rules")
tok = c.execute("SELECT value FROM site_config WHERE show_id=? AND key='level_up_rules'", (SID,)).fetchone()
ok(tok and json.loads(tok["value"]) == lv, "level rules stored")
with app.app_context():
    flat = A.get_flat_config(A.get_db(), SID)
    ok(json.loads(A.assemble_bot_config(flat)["level_up_rules"]) == lv, "level rules pass-through to bot")
pg = adm.get("/admin/rpg").get_data(as_text=True); ok('data-tab="level"' in pg and "var levelRules" in pg and "一级" in pg, "level tab rendered with data")

# ── 催回：管理员一键催 → 小手机标「被催」+ 队列里一条给机器人发群消息 ──
now_ms = int(time.time() * 1000)
rep = lambda role, items: c.execute("INSERT OR REPLACE INTO phone_reports (show_id, role, data, updated_at) VALUES (?,?,?,?)",
                                    (SID, role, json.dumps({"pending": {"pending": items, "rel": [], "rel_n": {}, "letters": []}}), now_ms))
rep("林晚", [{"gid": "5001", "type": "私约", "elapsed_min": 400, "since": 111, "over": True}, {"gid": "5002", "type": "电话", "elapsed_min": 5, "since": 222, "over": False}])
rep("周屿", [{"gid": "5003", "type": "官约", "elapsed_min": 900, "since": 333, "over": True}]); c.commit()
pg = m.get("/p/admin/urge").get_data(as_text=True)
ok("5001" in pg and "5003" in pg and "5002" not in pg, "overdue only by default")
ok("5002" in m.get("/p/admin/urge?all=1").get_data(as_text=True), "all view")
n0 = c.execute("SELECT COUNT(*) FROM phone_admin_ops WHERE kind='urge'").fetchone()[0]
m.post("/p/admin/urge/op", data={"csrf": "bad", "scope": "overdue"})
ok(c.execute("SELECT COUNT(*) FROM phone_urges").fetchone()[0] == 0, "bad csrf rejected")
m.post("/p/admin/urge/op", data={"csrf": m.csrf, "item": ["林晚|s:9999:1", "林晚|s:5001:111"]})   # 伪造项被忽略
ok(c.execute("SELECT COUNT(*) FROM phone_urges").fetchone()[0] == 1, "only real item urged")
q = c.execute("SELECT * FROM phone_admin_ops WHERE kind='urge'").fetchall(); ok(len(q) - n0 == 1 and q[-1]["role"] == "*", "queued one op")
ok(json.loads(q[-1]["value"]) == {"role": "林晚", "gid": "5001", "since": 111}, q[-1]["value"])
m.post("/p/admin/urge/op", data={"csrf": m.csrf, "scope": "overdue"})   # 林晚那条刚催过 → 跳过，只催周屿
ok(c.execute("SELECT COUNT(*) FROM phone_urges").fetchone()[0] == 2, "cooldown skips repeat")
c.execute("INSERT OR IGNORE INTO phone_pending_dismiss (show_id, role, key, created_at) VALUES (?,?,?,?)", (SID, "周屿", "s:5003:333", now_ms)); c.commit()
c.execute("DELETE FROM phone_urges WHERE role='周屿'"); c.commit()
m.post("/p/admin/urge/op", data={"csrf": m.csrf, "item": "周屿|s:5003:333"})
ok(c.execute("SELECT COUNT(*) FROM phone_pending_dismiss WHERE role='周屿'").fetchone()[0] == 0, "urge clears mute")
with app.app_context():
    db = A.get_db(); sm = A._phone_pending_summary(db, SID, "林晚"); ok(sm["urged"] == 1 and sm["count"] == 2, sm)
pp = lin.get("/p/me/stats?view=pending").get_data(as_text=True); ok("管理员催回" in pp and "催你回复" in pp, "player sees urge")
ok("管理员催你回复" in lin.get("/p/me").get_data(as_text=True), "banner on home")
ok(lin.post("/p/admin/urge/op", data={"csrf": lc, "scope": "overdue"}).status_code == 302
   and c.execute("SELECT COUNT(*) FROM phone_urges WHERE role='林晚'").fetchone()[0] == 1, "player cannot urge")

# ── 管理端：官约 / 外观 单独的 App 页 ──
ok("官约" in m.get("/p/admin").get_data(as_text=True) and "外观" in m.get("/p/admin").get_data(as_text=True), "desktop has apps")
ok('id="skinChoices"' in m.get("/p/admin/appearance").get_data(as_text=True), "appearance page")
ok("最近发起" in m.get("/p/admin/official").get_data(as_text=True), "official page lists ops")
ok(app.test_client().get("/p/admin/appearance").status_code == 302 and app.test_client().get("/p/admin/official").status_code == 302, "login required")
print("ALL OK")
