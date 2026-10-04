"""探索踩点：配置（地图/地点/掉落表校验）、每日次数与个人次数、临时次数、踩点抽取（线索去重/物品入队/只认注册物品）、权限
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/explore_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, io, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
import explore as E
from PIL import Image

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
E.EXPLORE_IMAGE_DIR = os.path.join(tmp, "explore_images")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
TID = c.execute("SELECT id FROM tenants").fetchone()["id"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,?)", (TID, SID, "ADMINCODE1")) if False else None
c.execute("INSERT OR REPLACE INTO phone_sync (show_id, tenant_id, snapshot, cursor, synced_at) VALUES (?,?,?,?,?)",
          (SID, TID, json.dumps({"plugin": {"version": "1.10.9", "params": [], "catalog": [{"name": "钥匙", "type": "物品"}, {"name": "金币", "type": "货币"}]}}), 0, int(time.time() * 1000)))
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)

adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID; s["phone_csrf"] = "tok"
H = {"X-CSRF": "tok"}
def ap(path, **kw): return adm.post("/admin/explore/api/" + path, json=kw, headers=H)

ok(adm.get("/admin/explore").status_code == 200, "admin page")
ok(app.test_client().get("/admin/explore/api/state").status_code == 302, "admin api needs login")
ok(adm.post("/admin/explore/api/settings", json={"default_daily": 3}).status_code == 403, "csrf required")
ok(ap("settings", enabled=True, default_daily=2, reset_hour=0, intro="hi").get_json()["ok"], "settings")
ok(not ap("settings", enabled=True, default_daily=500, reset_hour=0).get_json()["ok"], "bad daily")

mid = ap("map", name="学院").get_json()["id"]
img = io.BytesIO(); Image.new("RGB", (40, 30), (200, 10, 10)).save(img, "PNG"); img.seek(0)
r = adm.post(f"/admin/explore/api/map/{mid}/image", data={"image": (img, "a.png")}, headers=H, content_type="multipart/form-data")
ok(r.get_json()["ok"] and r.get_json()["image"].startswith("/x/img/"), "map image")
ok(adm.get(r.get_json()["image"]).status_code == 200, "image served")

drops = [{"kind": "clue", "weight": 5, "title": "撕碎的信", "text": "信上写着…"}]
bad = ap("spot", map_id=mid, name="图书馆", x=30, y=40, drops=[{"kind": "item", "weight": 1, "item": "不存在", "qty": 1}]).get_json()
ok(not bad["ok"] and "注册" in bad["error"], "unregistered item rejected")
ok(not ap("spot", map_id=mid, name="x", drops=[{"kind": "clue", "weight": 0, "title": "a", "text": "b"}]).get_json()["ok"], "weight 0 rejected")
sp = ap("spot", map_id=mid, name="图书馆", icon="📚", x=30, y=40, drops=drops).get_json(); ok(sp["ok"], "spot saved")
SPOT = sp["id"]
sp2 = ap("spot", map_id=mid, name="后门", x=60, y=70, drops=[{"kind": "item", "weight": 1, "item": "钥匙", "qty": 2}]).get_json(); ok(sp2["ok"], "item spot")
SPOT2 = sp2["id"]
st = adm.get("/admin/explore/api/state").get_json()
ok(st["settings"]["enabled"] and len(st["maps"][0]["spots"]) == 2 and any(r["role"] == "林晚" for r in st["roles"]), "admin state")
ok(any("钥匙" in g["names"] for g in st["items"]), "item catalog in admin state")

# 玩家
p = app.test_client()
ok(p.post("/x", data={"code": "WRONGCODE9"}).status_code == 404, "bad code")
ok(p.get("/x/api/state").status_code == 401, "api needs login")
r = p.get("/x/LINWAN0001"); ok(r.status_code == 302 and "explore_auth" in r.headers.get("Set-Cookie", ""), "enter by code")
ok(p.get("/x/home").status_code == 200, "home")
with p.session_transaction() as s: s["phone_csrf"] = "ptok"
PH = {"X-CSRF": "ptok"}
state = p.get("/x/api/state").get_json()
ok(state["enabled"] and state["quota"]["total"] == 2 and len(state["maps"][0]["spots"]) == 2, "player state")
ok(p.post("/x/api/visit", json={"spot_id": SPOT}).status_code == 403, "visit csrf")
v = p.post("/x/api/visit", json={"spot_id": SPOT}, headers=PH).get_json()
ok(v["ok"] and v["kind"] == "clue" and v["title"] == "撕碎的信" and v["quota"]["daily_left"] == 1, "clue drop")
v = p.post("/x/api/visit", json={"spot_id": SPOT}, headers=PH).get_json()
ok(v["kind"] == "empty" and v["consumed"] is False and v["quota"]["daily_left"] == 1, "same clue not twice, no cost")
v = p.post("/x/api/visit", json={"spot_id": SPOT2}, headers=PH).get_json()
ok(v["kind"] == "item" and v["item"]["name"] == "钥匙" and v["item"]["qty"] == 2 and v["item"]["status"] == "pending", "item drop")
op = c.execute("SELECT role, kind, name, value, done FROM phone_admin_ops WHERE id=?", (v["item"]["op_id"],)).fetchone()
ok(tuple(op) == ("林晚", "item", "钥匙", "2", 0), "item op queued for role")
v = p.post("/x/api/visit", json={"spot_id": SPOT2}, headers=PH); ok(v.status_code == 409, "daily quota used up")
clues = p.get("/x/api/clues").get_json()["clues"]
ok(len(clues) == 1 and clues[0]["new"] and clues[0]["spot"] == "图书馆", "clue board")
p.post("/x/api/clues/seen", headers=PH); ok(not p.get("/x/api/clues").get_json()["clues"][0]["new"], "seen")
# 机器人回报后，记录里显示入包结果
c.execute("UPDATE phone_admin_ops SET done=1, ok=1 WHERE id=?", (op and c.execute("SELECT MAX(id) FROM phone_admin_ops").fetchone()[0],)); c.commit()
lg = p.get("/x/api/log").get_json()["log"]; ok(lg[0]["item_status"] == "ok" and lg[0]["kind"] == "item", "log shows item status")

# 个人次数 / 临时次数
ok(ap("quota", role="林晚", daily=5).get_json()["ok"], "per-person quota")
ok(p.get("/x/api/state").get_json()["quota"]["daily_left"] == 3, "林晚 now has 5-2")
ok(ap("quota", roles=["林晚", "周屿"], daily=None).get_json()["ok"], "reset to default")
ok(p.get("/x/api/state").get_json()["quota"]["daily_left"] == 0, "back to default")
ok(ap("bonus", roles=["林晚"], amount=2, note="补偿").get_json()["ok"], "bonus")
q = p.get("/x/api/state").get_json()["quota"]; ok(q["bonus"] == 2 and q["total"] == 2, "bonus counted")
v = p.post("/x/api/visit", json={"spot_id": SPOT2}, headers=PH).get_json()
ok(v["ok"] and v["quota"]["bonus"] == 1, "bonus consumed after daily used")
ok(ap("bonus", roles=["林晚"], amount=-1).get_json()["ok"] and p.get("/x/api/state").get_json()["quota"]["bonus"] == 0, "bonus deducted")
ok(not ap("bonus", roles=["林晚"], amount=0).get_json()["ok"], "zero bonus rejected")
# 别人互不影响
z = app.test_client(); z.get("/x/ZHOUYU0001")
ok(z.get("/x/api/state").get_json()["quota"]["daily_left"] == 2, "other player unaffected")
# 不是注册物品（目录里去掉）→ 掉落跳过
c.execute("UPDATE phone_sync SET snapshot=?", (json.dumps({"plugin": {"version": "1.10.9", "params": [], "catalog": []}}),)); c.commit()
with z.session_transaction() as s: s["phone_csrf"] = "ztok"
v = z.post("/x/api/visit", json={"spot_id": SPOT2}, headers={"X-CSRF": "ztok"}).get_json()
ok(v["kind"] == "empty" and v["consumed"] is False, "unregistered item never dropped")
# 关闭
ap("settings", enabled=False, default_daily=2, reset_hour=0)
ok(z.post("/x/api/visit", json={"spot_id": SPOT}, headers={"X-CSRF": "ztok"}).status_code == 403, "disabled")
# 管理员码不能当玩家
ok(app.test_client().post("/x", data={"code": "x"}).status_code == 404, "x")
# 删地图连带删地点
ok(ap("map/delete", id=mid).get_json()["ok"] and c.execute("SELECT COUNT(*) FROM explore_spots").fetchone()[0] == 0, "delete map cascades")
print("ALL OK")
