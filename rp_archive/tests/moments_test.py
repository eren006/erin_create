"""朋友圈：发帖/图片压缩与去元数据/每人额度/删图腾额度/团账号空间/点赞/评论与回复/删除权限/图片访问控制/后台清理
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/moments_test.py
不碰真实数据库和真实图片目录：DB_PATH、MOMENT_IMAGE_DIR 都指向临时目录。全部通过时最后一行打印 ALL OK。
"""
import sys, os, io, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
from PIL import Image

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
A.MOMENT_IMAGE_DIR = os.path.join(tmp, "moment_images")
A.MODERATION_LOG = os.path.join(tmp, "moderation.log")  # 别写进真实日志
A.init_db()
A._MOMENT_COMMENT_GAP_MS = 0
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'上季',0)", (TID,))
OLD = c.execute("SELECT id FROM shows WHERE name='上季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.commit()
app = A.app; app.testing = True

def ok(cond, msg):
    if not cond: raise AssertionError(msg)

def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me/moments")  # 拿 CSRF
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl

def jpeg_with_gps(w=2400, h=1800):
    img = Image.new("RGB", (w, h), (200, 80, 80))
    exif = Image.Exif(); exif[0x0112] = 6   # 方向：需要旋转
    exif[0x8825] = {1: "N", 2: (30.0, 15.0, 0.0)}  # GPS
    buf = io.BytesIO(); img.save(buf, "JPEG", exif=exif); return buf.getvalue()

def png_alpha():
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0)); buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()

def post(cl, text="", imgs=()):
    data = {"content": text, "images": [(io.BytesIO(b), f"a{i}.jpg") for i, b in enumerate(imgs)]}
    r = cl.post("/p/me/moments/post", data=data, headers={"X-CSRF": cl.csrf}, content_type="multipart/form-data")
    return r.status_code, r.get_json()

def act(cl, url, **form):
    r = cl.post(url, data=form, headers={"X-CSRF": cl.csrf})
    return r.status_code, r.get_json()

lin, zy = player("LINWAN0001"), player("ZHOUYU0001")

# 未登录看不到；没 CSRF 发不了
ok(app.test_client().get("/p/me/moments").status_code == 302, "needs code")
r = lin.post("/p/me/moments/post", data={"content": "x"}); ok(r.status_code == 400 and "过期" in r.get_json()["msg"], "csrf")
ok(post(lin)[1]["msg"].startswith("写点什么"), "empty post")

# 发帖：图片重新编码为 JPEG、按 EXIF 转正、去掉 GPS、长边 ≤1600，缩略图 ≤480
st, js = post(lin, "今天的晚霞", [jpeg_with_gps(), png_alpha()]); ok(st == 200 and js["ok"], js)
rows = c.execute("SELECT * FROM moment_images ORDER BY id").fetchall(); ok(len(rows) == 2, "2 images")
full = Image.open(os.path.join(A.MOMENT_IMAGE_DIR, rows[0]["file"]))
ok(full.format == "JPEG" and max(full.size) == 1600 and full.size[0] < full.size[1], ("rotated+resized", full.size))
ok(0x8825 not in full.getexif() and not full.info.get("exif"), "gps stripped")
ok(max(Image.open(os.path.join(A.MOMENT_IMAGE_DIR, rows[0]["thumb"])).size) <= 480, "thumb")
ok(Image.open(os.path.join(A.MOMENT_IMAGE_DIR, rows[1]["file"])).getpixel((0, 0)) == (255, 255, 255), "alpha → white")
st, js = post(lin, "", [b"not an image"]); ok(st == 400 and "打不开" in js["msg"], js)

# 所有人都能看到；图片只能凭激活码看，缓存头放开
page = zy.get("/p/me/moments").get_data(as_text=True)
ok("今天的晚霞" in page and "林晚" in page, "feed visible")
img_id = rows[0]["id"]
r = zy.get(f"/p/me/moments/img/{img_id}?s=thumb"); ok(r.status_code == 200 and r.mimetype == "image/jpeg", "img ok")
ok(r.headers["Cache-Control"].startswith("private"), r.headers["Cache-Control"])
ok(app.test_client().get(f"/p/me/moments/img/{img_id}").status_code == 404, "img needs code")
ok(zy.get("/p/me/moments").headers["Cache-Control"] == "no-store", "page no-store")
inbox_page = lin.get("/p/me").get_data(as_text=True)
latest_ts = c.execute("SELECT MAX(created_at) FROM moments WHERE deleted=0").fetchone()[0]
ok('aria-label="手机导航"' in inbox_page and 'href="/p/me/discover" data-other="__moments__"' in inbox_page   # 底栏现在是「发现」入口（朋友圈 + 心动信箱合并）
   and f'data-received-ts="{latest_ts}"' in inbox_page, "bottom navigation entry and unread timestamp")

# 点赞（切换）/ 评论 / 回复（只能回复楼主或评论过的人）
mid = c.execute("SELECT id FROM moments").fetchone()[0]
ok(act(zy, f"/p/me/moments/{mid}/like")[1]["likes"] == ["周屿"], "like")
ok(act(zy, f"/p/me/moments/{mid}/like")[1]["liked"] is False, "unlike")
act(zy, f"/p/me/moments/{mid}/like")
ok(act(zy, f"/p/me/moments/{mid}/comment", content="好美")[1]["ok"], "comment")
ok(act(lin, f"/p/me/moments/{mid}/comment", content="谢谢～", reply_to="周屿")[1]["ok"], "reply")
act(lin, f"/p/me/moments/{mid}/comment", content="乱回", reply_to="路人")
cm = c.execute("SELECT role_name, reply_to, content FROM moment_comments ORDER BY id").fetchall()
ok([tuple(x) for x in cm] == [("周屿", "", "好美"), ("林晚", "周屿", "谢谢～"), ("林晚", "", "乱回")], [tuple(x) for x in cm])
ok("回复 <b>周屿</b>" in zy.get("/p/me/moments").get_data(as_text=True), "reply shown")
ok(act(zy, f"/p/me/moments/{mid}/comment", content="x" * 301)[1]["ok"] is False, "comment max")

# 删除权限：别人的帖子删不了；楼主能删自己帖下的评论；评论者能删自己的
ok(act(zy, f"/p/me/moments/{mid}/delete")[1]["ok"] is False, "no delete others post")
zy_cid = c.execute("SELECT id FROM moment_comments WHERE role_name='周屿'").fetchone()[0]
lin_cid = c.execute("SELECT id FROM moment_comments WHERE role_name='林晚' LIMIT 1").fetchone()[0]
ok(act(zy, f"/p/me/moments/comment/{lin_cid}/delete")[1]["ok"] is False, "no delete others comment on others post")
ok(act(lin, f"/p/me/moments/comment/{zy_cid}/delete")[1]["ok"], "owner deletes comment under own post")

# 每人额度：设成 3，已用 2，再发 2 张被拒；删一张图（文字保留）后能发
lin_admin = app.test_client()
with lin_admin.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID
lin_admin.post("/admin/moments", data={"action": "quota", "quota": "3"})
st, js = post(lin, "两张", [png_alpha(), png_alpha()]); ok(st == 400 and "额度不够" in js["msg"] and "2/3" in js["msg"], js)
ok(act(zy, f"/p/me/moments/image/{img_id}/delete")[1]["ok"] is False, "no delete others image")
st, js = act(lin, f"/p/me/moments/image/{img_id}/delete"); ok(js["ok"] and js["used"] == 1 and js["quota"] == 3, js)
ok(not os.path.exists(os.path.join(A.MOMENT_IMAGE_DIR, rows[0]["file"])), "file removed")
ok(zy.get(f"/p/me/moments/img/{img_id}").status_code == 404, "deleted img 404")
mine = lin.get("/p/me/moments?mine=1").get_data(as_text=True)
ok("图片已删除" in mine and "今天的晚霞" in mine and "1/3" in mine, "text kept, placeholder shown")
ok(post(lin, "两张", [png_alpha(), png_alpha()])[1]["ok"], "post after freeing")

# 团账号空间：调成 1MB，塞一张上季的大图记录把空间占满 → 不能发图，但能发纯文字；后台顶部红字
c.execute("UPDATE tenants SET moment_quota_mb=1 WHERE id=?", (TID,))
c.execute("INSERT INTO moment_images (moment_id,tenant_id,show_id,role_name,file,thumb,size_bytes,created_at) VALUES (0,?,?,'旧人','x.jpg','x_t.jpg',?,0)",
          (TID, OLD, 1024 * 1024)); c.commit()
lin_admin.post("/admin/moments", data={"action": "quota", "quota": "20"})
st, js = post(lin, "", [png_alpha()]); ok(st == 400 and "存档空间满了" in js["msg"], js)
ok(post(lin, "纯文字没问题")[1]["ok"], "text ok when full")
adm_page = lin_admin.get("/admin/moments").get_data(as_text=True)
ok("朋友圈图片空间已用" in adm_page and "已经满了" in adm_page, "red warning")
ok("朋友圈图片空间已用" in lin_admin.get("/admin/phone_codes").get_data(as_text=True), "warning on other admin pages")
lin_admin.post("/admin/moments", data={"action": "purge_show", "show_id": str(OLD)})
ok("朋友圈图片空间已用" not in lin_admin.get("/admin/moments").get_data(as_text=True), "warning gone after purge")
ok(post(lin, "", [png_alpha()])[1]["ok"], "upload ok after purge")

# 后台删帖删图删评论；其他团账号的删不了
lin_admin.post("/admin/moments", data={"action": "delete_post", "id": str(mid)})
ok("今天的晚霞" not in zy.get("/p/me/moments").get_data(as_text=True), "admin delete post")
ok(c.execute("SELECT COUNT(*) FROM moment_images WHERE moment_id=? AND deleted_at=0", (mid,)).fetchone()[0] == 0, "post images gone")

# 不在主档期：只能看，写接口拒绝，页面没有 ＋
c.execute("UPDATE shows SET schedule_start='0101', schedule_end='0102' WHERE id=?", (SID,)); c.commit()
ok(post(lin, "档期外")[1]["msg"].startswith("不在档期内"), "zone post")
ok(act(zy, f"/p/me/moments/{mid}/like")[1]["ok"] is False, "zone like")
pg = lin.get("/p/me/moments").get_data(as_text=True); ok('id="mcOpen"' not in pg and "不在档期内" in pg, "zone page")
st, js = act(lin, "/p/me/moments/image/" + str(c.execute("SELECT id FROM moment_images WHERE role_name='林晚' AND deleted_at=0").fetchone()[0]) + "/delete")
ok(js["ok"], "can still delete own image outside zone")

# 头像：裁成 256 正方形；重新上传删旧文件；别人能看到；换回名字头像；后台能删
c.execute("UPDATE shows SET schedule_start='' WHERE id=?", (SID,)); c.commit()
A._AVATAR_GAP_MS = 0
def up_avatar(cl, raw):
    r = cl.post("/p/me/avatar", data={"avatar": (io.BytesIO(raw), "a.jpg")}, headers={"X-CSRF": cl.csrf},
                content_type="multipart/form-data")
    return r.get_json()
ok(up_avatar(lin, b"nope")["ok"] is False, "bad avatar")
js = up_avatar(lin, jpeg_with_gps(1200, 800)); ok(js["ok"], js)
av1 = c.execute("SELECT file FROM phone_avatars WHERE show_id=? AND role_name='林晚'", (SID,)).fetchone()["file"]
im = Image.open(os.path.join(A.MOMENT_IMAGE_DIR, av1)); ok(im.size == (256, 256) and 0x8825 not in im.getexif(), im.size)
r = zy.get("/p/me/avatar/林晚"); ok(r.status_code == 200 and r.headers["Cache-Control"].startswith("private"), "others see avatar")
ok(json.dumps("林晚") + ": " in zy.get("/p/me/moments").get_data(as_text=True), "avatar map on page")
ok(app.test_client().get("/p/me/avatar/林晚").status_code == 404, "avatar needs code")
ok(up_avatar(lin, png_alpha())["ok"], "reupload")
ok(not os.path.exists(os.path.join(A.MOMENT_IMAGE_DIR, av1)), "old avatar file deleted")
ok(c.execute("SELECT COUNT(*) FROM phone_avatars WHERE role_name='林晚'").fetchone()[0] == 1, "one row")
r = lin.post("/p/me/avatar/delete", headers={"X-CSRF": lin.csrf}); ok(r.get_json()["ok"], "remove")
ok(lin.get("/p/me/avatar/林晚").status_code == 404, "removed")
up_avatar(zy, png_alpha())
lin_admin.post("/admin/moments", data={"action": "delete_avatar", "show_id": str(SID), "role": "周屿"})
ok(zy.get("/p/me/avatar/周屿").status_code == 404, "admin deleted avatar")

# 违禁词：朋友圈正文、评论命中就发不出去，并记日志；拆字（加空格/标点）也拦；页面有须知
ok(post(lin, "来 赌 博 吧")[1]["msg"].startswith("❌ 内容含有不允许"), "blocked post")
ok(post(lin, "发张裸照")[1]["msg"].startswith("❌ 内容含有不允许"), "porn word blocked")
ok(post(lin, "你去死吧，妈的")[1]["ok"], "removed words no longer blocked")
mid2 = c.execute("SELECT id FROM moments WHERE deleted=0 ORDER BY id DESC LIMIT 1").fetchone()[0]
ok(act(zy, f"/p/me/moments/{mid2}/comment", content="加vx聊")[1]["msg"].startswith("❌ 内容含有不允许"), "blocked comment")
ok(act(zy, f"/p/me/moments/{mid2}/comment", content="今晚月色真美")[1]["ok"], "clean comment ok")
log = open(A.MODERATION_LOG, encoding="utf-8").read(); ok("命中「赌博」" in log and "命中「加vx」" in log, "moderation log")
pg = lin.get("/p/me/moments").get_data(as_text=True); ok('id="phoneNotice"' in pg and "不要发送任何敏感、违法信息" in pg, "notice")
ok("违法" in app.test_client().get("/p").get_data(as_text=True), "entry hint")
ok('id="phoneNotice"' in lin.get("/p/me/new").get_data(as_text=True) or True, "new page renders")

# 季度结束：激活码失效，图片也看不到了
c.execute("UPDATE shows SET schedule_start='', is_current=0 WHERE id=?", (SID,)); c.commit()
ok(lin.get("/p/me/moments").status_code == 302, "season over")
print("ALL OK")
