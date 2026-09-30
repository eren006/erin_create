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

# 进门 → 管理首页；/p/me 也跳管理首页
m = app.test_client(); r = m.get("/p/" + ACODE); ok(r.status_code == 302 and r.location.endswith("/p/admin"), r.location)
ok(m.get("/p/me").location.endswith("/p/admin"), "inbox redirects admin")
idx = m.get("/p/admin").get_data(as_text=True); ok(all(n in idx for n in ("林晚", "周屿", "沈知意")), "roles listed")
with m.session_transaction() as s: m.csrf = s["phone_csrf"]

# 玩家码进不了管理页；管理删除接口玩家调不了
lin = app.test_client(); lin.get("/p/LINWAN0001"); lin.get("/p/me/周屿")
with lin.session_transaction() as s: lin.csrf = s["phone_csrf"]
ok(lin.get("/p/admin").location.endswith("/p"), "player blocked from admin")
ok(lin.post("/p/admin/delete", data={"target": "event:1"}, headers={"X-CSRF": lin.csrf}).status_code == 401, "player cannot delete")
pl = lin.get("/p/me/周屿").get_data(as_text=True)
ok('class="admin-note"' not in pl and "实际：" not in pl and "adminConfirm" not in pl, "player sees no admin notes")

# 以林晚视角：林晚手机里「周屿」对话挂着误送的那条，管理员小字写出实际去向
inbox = m.get("/p/admin/as/林晚").get_data(as_text=True)
ok("以 林晚 的视角" in inbox and "/p/admin/as/%E6%9E%97%E6%99%9A/%E5%91%A8%E5%B1%BF" in inbox, "admin inbox links rewritten")
t = m.get("/p/admin/as/林晚/周屿").get_data(as_text=True)
ok("误送，本来给周屿" in t and "实际：林晚 → 沈知意" in t and "原文：原来的话" in t and "管理删除" in t, "admin notes")
ok('id="compose"' not in t, "admin read-only thread")

# 管理身份不能发：短信、朋友圈、点歌、头像
ok(m.post("/p/me/send", data={"to": "周屿", "text": "x", "csrf": m.csrf}).location.endswith("/p/admin"), "no sms")
ok("不能发" in m.post("/p/me/moments/post", data={"content": "x"}, headers={"X-CSRF": m.csrf}).get_json()["msg"], "no moment")
ok("不能发" in m.post("/p/me/song", data={"song_id": "1"}, headers={"X-CSRF": m.csrf}).get_json()["msg"], "no song")
ok("不能发" in m.post("/p/me/avatar", headers={"X-CSRF": m.csrf}).get_json()["msg"], "no avatar")

def adel(target, cl=m):
    return cl.post("/p/admin/delete", data={"target": target}, headers={"X-CSRF": cl.csrf}).get_json()
ok(adel("event:1")["ok"], "delete sms")
ok(adel("event:1")["ok"] is False, "second delete: already gone")
sz = app.test_client(); sz.get("/p/SHENZY0001"); ok("明天早餐一起吗" not in sz.get("/p/me").get_data(as_text=True), "deleted for recipient")
ok(c.execute("SELECT COUNT(*) FROM extra_events WHERE id=1").fetchone()[0] == 0, "event gone")
ok(m.post("/p/admin/delete", data={"target": "event:2"}).get_json()["ok"] is False, "needs csrf")

# 朋友圈 / 评论 / 图片 / 头像 / 点歌
def png():
    b = io.BytesIO(); Image.new("RGB", (50, 50), (1, 2, 3)).save(b, "PNG"); return b.getvalue()
lin.get("/p/me/moments")
with lin.session_transaction() as s: lin.csrf = s["phone_csrf"]
lin.post("/p/me/moments/post", data={"content": "我的朋友圈", "images": [(io.BytesIO(png()), "a.png")]},
         headers={"X-CSRF": lin.csrf}, content_type="multipart/form-data")
mid = c.execute("SELECT id FROM moments").fetchone()[0]
lin.post(f"/p/me/moments/{mid}/comment", data={"content": "一条评论"}, headers={"X-CSRF": lin.csrf})
mp = m.get("/p/me/moments").get_data(as_text=True)
ok("管理删除" in mp and 'id="mcOpen"' not in mp and "管理身份" in mp, "admin moments page")
iid = c.execute("SELECT id FROM moment_images").fetchone()[0]
cid = c.execute("SELECT id FROM moment_comments").fetchone()[0]
ok(adel(f"image:{iid}")["ok"] and c.execute("SELECT deleted_at FROM moment_images WHERE id=?", (iid,)).fetchone()[0] > 0, "image")
ok(adel(f"comment:{cid}")["ok"] and "一条评论" not in lin.get("/p/me/moments").get_data(as_text=True), "comment")
ok(adel(f"moment:{mid}")["ok"] and "我的朋友圈" not in lin.get("/p/me/moments").get_data(as_text=True).split("moments-feed")[-1], "moment")
lin.post("/p/me/avatar", data={"avatar": (io.BytesIO(png()), "a.png")}, headers={"X-CSRF": lin.csrf}, content_type="multipart/form-data")
ok("删头像" in m.get("/p/admin").get_data(as_text=True), "avatar delete button")
ok(adel("avatar:林晚")["ok"] and lin.get("/p/me/avatar/林晚").status_code == 404, "avatar")
c.execute("""INSERT INTO song_requests (tenant_id, show_id, from_role, to_role, song_id, song_name, created_at)
             VALUES (?,?,'周屿','林晚',1,'晴天',?)""", (TID, SID, int(time.time() * 1000))); c.commit()
pub = m.get("/p/me/public").get_data(as_text=True); ok("点歌人：周屿" in pub and "实际：周屿 → 林晚" in pub, "public admin notes")
ok("点歌人" not in lin.get("/p/me/public").get_data(as_text=True), "player public has no admin notes")
sgid = c.execute("SELECT id FROM song_requests").fetchone()[0]
ok(adel(f"song:{sgid}")["ok"] and "晴天" not in lin.get("/p/me/public").get_data(as_text=True), "song")
log = open(A.MODERATION_LOG, encoding="utf-8").read(); ok(log.count("ADMIN\t删除") >= 6, log)

# 重置管理员码：旧码立即失效
adm.post("/admin/phone_codes", data={"action": "admin_code"})
ok(m.get("/p/admin").location.endswith("/p"), "old admin code invalid")
print("ALL OK")
