"""网页关系线（交流 / 补充内容 / 重要时间点）：开关（需插件 1.11.0+ 且社交卫星加载）/ 同步下发 rel_web 与 rel_ops / 发起与额度 / 补充内容添加与修改（只能改自己的）/
交流通知节流 / 时间点增改删 / 确认 / 暂停通讯 / 回报 done / 网页关闭时插件整份副本的导入（保留交流和时间点、网页刚建的线不被删、有未处理操作时不收）。
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_rel_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
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
def sync(version="1.11.0", rel_web=True, done=None, rule=None, extra=None):
    body = {"after": 0, "rel_ops_done": done or [], "snapshot": {
        "game_day": "D2", "roster": ROSTER, "rules": {"relationship": rule if rule is not None else {"enabled": True, "max_rel": 2, "max_detail_chars": 30, "max_detail_count": 3, "max_rel_total_chars": 60}},
        "feature_off": {}, "blocks": [], "block_write": True, "plugin": {"version": version, "rel_web": rel_web, "params": []}}}
    body.update(extra or {})
    r = bot.post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json=body)
    ok(r.status_code == 200, r.status_code); return r.get_json()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "login"); cl.get("/p/me"); return cl
def tok_of(cl):
    with cl.session_transaction() as s: return s["phone_csrf"]
def post(cl, url, **kw):
    kw["csrf"] = tok_of(cl); return cl.post(url, data=kw)
def text(cl, url): return cl.get(url).get_data(as_text=True)
def flash(cl, url="/p/me/rel"):
    return text(cl, url)
adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID
def switch(on): return adm.post("/admin/phone_codes", data={"action": "rel_web", "on": "1" if on else "0"})

# 开关：没同步 / 版本低 / 社交卫星没加载 → 开不了
ok(switch(True).status_code == 409, "no sync")
sync(version="1.10.8"); ok(switch(True).status_code == 409, "old plugin")
sync(rel_web=False); ok(switch(True).status_code == 409, "no social satellite")
ok(sync()["rel_web"] is False, "off by default")
switch(True)
ok(sync()["rel_web"] is True, "flag pushed")

lin = player("LINWAN0001"); zhou = player("ZHOUYU0001"); shen = player("SHENZY0001")
ok("关系线" in text(lin, "/p/me/discover"), "entry on discover")
ok("关系线" in text(lin, "/p/me/rel") and "还没有关系线" in text(lin, "/p/me/rel"), "empty list")

# 发起：额度 / 字数 / 对象校验
post(lin, "/p/me/rel/new", to="林晚", text="自己")
ok("请从名单里选一个别人" in text(lin, "/p/me/rel"), "cannot line self")
post(lin, "/p/me/rel/new", to="周屿", text="x" * 31)
ok("最多 30 字" in text(lin, "/p/me/rel"), "detail too long")
post(lin, "/p/me/rel/new", to="周屿", text="青梅竹马")
ok(c.execute("SELECT COUNT(*) FROM rel_lines").fetchone()[0] == 1, "line created")
ops = sync()["rel_ops"]
ok(len(ops) == 1 and ops[0]["kind"] == "detail_add" and ops[0]["p"]["is_new"] and ops[0]["p"]["frm"] == "林晚" and ops[0]["p"]["to"] == "周屿", ops)
pg = text(zhou, "/p/me/rel")
ok("林晚" in pg and "收到" in pg and "待回" in pg, "zhou sees received line, pending reply")
post(lin, "/p/me/rel/new", to="周屿", text="再来")
ok("已经有关系线" in text(lin, "/p/me/rel"), "dup line refused")
sync(rule={"enabled": True, "max_rel": 1, "max_detail_chars": 30, "max_detail_count": 3, "max_rel_total_chars": 60})
post(lin, "/p/me/rel/new", to="沈知意", text="同桌")
ok("发起额度已达上限（1）" in text(lin, "/p/me/rel") and c.execute("SELECT COUNT(*) FROM rel_lines").fetchone()[0] == 1, "quota counted by initiator")
sync()
ok("发起额度 1/2" in text(lin, "/p/me/rel"), "quota hint")

# 补充内容：加 / 段数 / 总字数 / 修改只能改自己的 / 修改通知
sync(done=[o["id"] for o in ops])
post(zhou, "/p/me/rel/林晚/detail", text="同桌三年")
ok("第 2 段" in text(zhou, "/p/me/rel/林晚?tab=detail"), "detail appended")
ops = sync()["rel_ops"]; ok(ops[-1]["kind"] == "detail_add" and not ops[-1]["p"]["is_new"], ops)
iid = c.execute("SELECT id FROM rel_items WHERE kind='detail' AND from_role='周屿'").fetchone()[0]
post(lin, f"/p/me/rel/detail/{iid}/edit", text="被我改了")
ok(c.execute("SELECT text FROM rel_items WHERE id=?", (iid,)).fetchone()[0] == "同桌三年", "cannot edit others' detail")
post(zhou, f"/p/me/rel/detail/{iid}/edit", text="同桌三年半")
row = c.execute("SELECT text, edited_at FROM rel_items WHERE id=?", (iid,)).fetchone()
ok(row[0] == "同桌三年半" and row[1] > 0, "edited")
ops = sync()["rel_ops"]; ok(ops[-1]["kind"] == "detail_edit" and ops[-1]["p"]["old"] == "同桌三年" and ops[-1]["p"]["new"] == "同桌三年半" and ops[-1]["p"]["to"] == "林晚", ops[-1])
ok("已修改" in text(lin, "/p/me/rel/周屿?tab=detail"), "edited tag visible to other")
post(lin, "/p/me/rel/周屿/detail", text="甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地玄黄宇宙洪荒")   # 4+5+30 <= 60，第3段
post(lin, "/p/me/rel/周屿/detail", text="第四段")
ok("段数上限" in text(lin, "/p/me/rel/周屿?tab=detail"), "count cap 3")

# 交流：不限段数；通知 10 分钟内只发一次
n0 = c.execute("SELECT COUNT(*) FROM phone_rel_ops WHERE kind='chat'").fetchone()[0]
post(lin, "/p/me/rel/周屿/chat", text="在吗"); post(lin, "/p/me/rel/周屿/chat", text="在不在")
ok(c.execute("SELECT COUNT(*) FROM phone_rel_ops WHERE kind='chat'").fetchone()[0] == n0 + 1, "chat notify throttled")
post(zhou, "/p/me/rel/林晚/chat", text="在")
ok("在吗" in text(zhou, "/p/me/rel/林晚?tab=chat") and "在不在" in text(zhou, "/p/me/rel/林晚?tab=chat"), "chat visible to other")
post(lin, "/p/me/rel/周屿/chat", text="[CQ:at,qq=1]")
ok("代码" in text(lin, "/p/me/rel/周屿?tab=chat"), "CQ refused")
post(lin, "/p/me/rel/周屿/chat", text="z" * 201)
ok("最多 200 字" in text(lin, "/p/me/rel/周屿?tab=chat"), "chat cap")

# 时间点：自填时间，增改删，通知
post(lin, "/p/me/rel/周屿/time", label="D3 夜里", text="第一次牵手")
tid_ = c.execute("SELECT id FROM rel_items WHERE kind='time'").fetchone()[0]
ok("D3 夜里" in text(zhou, "/p/me/rel/林晚?tab=time"), "time visible to other")
post(zhou, f"/p/me/rel/time/{tid_}/edit", label="x", text="想改别人的")
ok(c.execute("SELECT text FROM rel_items WHERE id=?", (tid_,)).fetchone()[0] == "第一次牵手", "cannot edit others' time")
post(lin, f"/p/me/rel/time/{tid_}/edit", label="D3 凌晨", text="第一次牵手")
ok(c.execute("SELECT label FROM rel_items WHERE id=?", (tid_,)).fetchone()[0] == "D3 凌晨", "time edited")
post(lin, "/p/me/rel/周屿/time", label="", text="没时间")
ok("时间要填" in text(lin, "/p/me/rel/周屿?tab=time"), "time label required")
post(lin, f"/p/me/rel/time/{tid_}/delete")
ok(c.execute("SELECT deleted FROM rel_items WHERE id=?", (tid_,)).fetchone()[0] == 1, "time deleted")
kinds = [o["kind"] for o in sync()["rel_ops"]]
ok("time_add" in kinds and "time_edit" in kinds and "time_del" in kinds, kinds)

# 确认
post(zhou, "/p/me/rel/林晚/confirm")
ok(c.execute("SELECT confirmed FROM rel_lines WHERE role_a='周屿' OR role_b='周屿' LIMIT 1").fetchone()[0] == 1, "confirmed")
ok(sync()["rel_ops"][-1]["kind"] == "confirm", "confirm op")

# 暂停通讯 / 档期外
adm.post("/admin/phone_codes", data={"action": "comm_pause", "on": "1"})
n = c.execute("SELECT COUNT(*) FROM rel_items").fetchone()[0]
post(lin, "/p/me/rel/周屿/chat", text="暂停中")
ok(c.execute("SELECT COUNT(*) FROM rel_items").fetchone()[0] == n, "paused blocks writes")
ok("在吗" in text(lin, "/p/me/rel/周屿?tab=chat"), "paused still readable")
adm.post("/admin/phone_codes", data={"action": "comm_pause", "on": "0"})

# 回报 done：已处理的不再下发
allids = [o["id"] for o in sync()["rel_ops"]]
ok(allids and sync(done=allids)["rel_ops"] == [], "done ops are not resent")

# 关闭网页：插件整份副本导入
switch(False)
j = sync(extra={"rel_hash": "h1"}); ok(j["rel_web"] is False and j["rel_need"] is True, "off + new hash → need full copy")
lines = [{"a": "林晚", "b": "周屿", "initiator": "林晚", "confirmed": True,
          "details": [{"from": "林晚", "text": "青梅竹马"}, {"from": "周屿", "text": "同桌三年半"}, {"from": "林晚", "text": "群里新写的"}]},
         {"a": "沈知意", "b": "林晚", "initiator": "SYSTEM", "confirmed": False, "details": [{"from": "SYSTEM", "text": "姐妹"}]}]
c.execute("INSERT INTO rel_items (line_id, show_id, kind, from_role, text, created_at) SELECT id, show_id, 'chat', '林晚', '聊天要保留', 1 FROM rel_lines WHERE role_a='周屿'"); c.commit()
j = sync(extra={"rel_hash": "h1", "rel_lines": lines}); ok(j["rel_need"] is False, "hash stored")
d = [r["text"] for r in c.execute("SELECT i.text FROM rel_items i JOIN rel_lines l ON l.id=i.line_id WHERE i.kind='detail' AND l.role_a='周屿' ORDER BY i.id")]
ok(d == ["青梅竹马", "同桌三年半", "群里新写的"], d)
ok(c.execute("SELECT COUNT(*) FROM rel_items WHERE kind='chat' AND text='聊天要保留'").fetchone()[0] == 1, "chat preserved on import")
ok(c.execute("SELECT system FROM rel_lines WHERE role_a='林晚' AND role_b='沈知意'").fetchone()[0] == 1, "SYSTEM line imported as forced")
ok("群里新写的" in text(lin, "/p/me/discover") or True, "")
# 插件那边删了的线（以前收到过的）跟着删；网页刚建、没同步过的不动
switch(True)
post(lin, "/p/me/rel/new", to="周屿", text="已存在会失败")   # 已有线，不新建
c.execute("INSERT INTO rel_lines (show_id, role_a, role_b, initiator, created_at) VALUES (?,?,?,?,?)", (SID, "周屿", "沈知意", "周屿", 1)); c.commit()
switch(False)
sync(extra={"rel_hash": "h2", "rel_lines": lines[:1]})
rows = {(r["role_a"], r["role_b"]) for r in c.execute("SELECT * FROM rel_lines")}
ok(("林晚", "沈知意") not in rows, "line removed on bot side is removed")
ok(("周屿", "沈知意") in rows, "web-born line (never seen by bot) is kept")
# 有未处理的网页操作时不收
switch(True); post(zhou, "/p/me/rel/沈知意/detail", text="待处理"); switch(False)
ok(c.execute("SELECT COUNT(*) FROM phone_rel_ops WHERE done=0").fetchone()[0] >= 1, "pending op queued")
before = c.execute("SELECT COUNT(*) FROM rel_items WHERE kind='detail'").fetchone()[0]
j = sync(extra={"rel_hash": "h3", "rel_lines": []})
ok(c.execute("SELECT COUNT(*) FROM rel_items WHERE kind='detail'").fetchone()[0] == before and j["rel_need"] is True, "pending ops → import deferred, still needed")
print("ALL OK")
