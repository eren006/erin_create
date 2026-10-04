"""本机预览探索踩点用：临时库 + 假数据 + 开发登录，不碰任何真实数据。仅本机开发用，别部署（deploy.sh 不会推 tools 之外的东西，但 tools/ 会被推，所以只绑 127.0.0.1）。
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tools/dev_explore_preview.py   （监听 127.0.0.1:5055）
  · 玩家：http://127.0.0.1:5055/x/LINWAN0001（也可 ZHOUYU0001 / SHENZY0001；周屿有 4 条线索、分 2 个地点）
  · 后台：http://127.0.0.1:5055/__dev  （自动登录成管理员并跳到 /admin/explore；探索后台/发放页都在后台里）
  · 小手机管理端「发放」页：访问 http://127.0.0.1:5055/p/ADMINDEV01 进管理员手机，桌面里点「发放」（/p/admin/grant）
"""
import sys, os, io, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A, explore as E
from PIL import Image, ImageDraw
tmp = tempfile.mkdtemp(); A.DB_PATH = os.path.join(tmp, "t.db"); E.EXPLORE_IMAGE_DIR = os.path.join(tmp, "img")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("UPDATE shows SET is_current=0"); c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_admin_codes (show_id, tenant_id, code, created_at) VALUES (?,?,?,?)", (SID, TID, "ADMINDEV01", int(time.time() * 1000)))
c.execute("INSERT OR REPLACE INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at) VALUES (?,?,?,?,?)",
 (SID, TID, json.dumps({"plugin": {"version": "1.10.9", "params": [], "catalog": [{"name": "钥匙", "type": "物品"}, {"name": "金币", "type": "货币"}, {"name": "旧地图", "type": "道具"}]}}), 0, int(time.time()*1000)))
c.commit()
app = A.app
@app.route("/__dev")
def _dev():
    from flask import session, redirect
    session["tenant_id"] = TID; session["admin_logged_in"] = True; session["view_show_id"] = SID
    return redirect("/admin/explore")
with app.test_client() as t:
    with t.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID; s["phone_csrf"] = "tok"
    H = {"X-CSRF": "tok"}
    P = lambda p, **kw: t.post("/admin/explore/api/" + p, json=kw, headers=H).get_json()
    P("settings", enabled=True, default_daily=3, reset_hour=0, intro="雨后的学院，总有人落下些什么。")
    mid = P("map", name="学院")["id"]
    im = Image.new("RGB", (800, 500), (225, 214, 190)); d = ImageDraw.Draw(im)
    for i in range(0, 800, 40): d.line([(i, 0), (i, 500)], fill=(210, 198, 170))
    d.rectangle([120, 100, 320, 260], fill=(180, 160, 130)); d.ellipse([480, 280, 700, 440], fill=(150, 185, 140))
    b = io.BytesIO(); im.save(b, "PNG"); b.seek(0)
    t.post(f"/admin/explore/api/map/{mid}/image", data={"image": (b, "m.png")}, headers=H, content_type="multipart/form-data")
    P("spot", map_id=mid, name="图书馆", icon="📚", desc="安静得能听见翻页声。", x=25, y=30, drops=[
        {"kind": "clue", "weight": 5, "title": "撕碎的信", "text": "信纸被撕成两半，只剩半句：「别让他知道……」"},
        {"kind": "clue", "weight": 3, "title": "借阅卡", "text": "最后一张借阅卡，签名被人刻意涂掉。"},
        {"kind": "item", "weight": 2, "item": "钥匙", "qty": 1}, {"kind": "nothing", "weight": 2, "text": "只有灰尘。"}])
    P("spot", map_id=mid, name="后花园", icon="🌿", desc="雨后的泥土味。", x=65, y=70, drops=[{"kind": "item", "weight": 1, "item": "旧地图", "qty": 1}, {"kind": "nothing", "weight": 1}])
    P("map", name="旧城区")
    P("quota", role="周屿", daily=6); P("bonus", roles=["林晚"], amount=2, note="补偿")
now=int(time.time()*1000)
for i,(sp,sn,ti,tx,off) in enumerate([(1,'图书馆','撕碎的信','信纸被撕成两半，只剩半句：「别让他知道……」',50),(2,'后花园','半埋的脚印','两串脚印通向温室，其中一串明显更深。',40),(1,'图书馆','借阅卡','最后一张借阅卡，签名被人刻意涂掉了。',30),(1,'图书馆','节目单背面','第三幕之前，把钥匙放回原处。',20)]):
    c.execute("INSERT INTO explore_clues (show_id,role,spot_id,drop_id,spot_name,title,text,ts,seen) VALUES (?,?,?,?,?,?,?,?,0)",(SID,'周屿',sp,'d%d'%i,sn,ti,tx,now-off*60000))
c.commit()
from werkzeug.serving import run_simple
run_simple("127.0.0.1", 5055, app, threaded=True)
