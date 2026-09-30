"""点歌：网页/群里点歌、一律匿名、每日上限（网页和群里一起算）、寄语违禁词、点歌台、公开播报、机器人取走待播与回报
不请求真实的网易云/QQ 音乐：搜歌和查歌函数换成假数据。
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/song_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
A.MOMENT_IMAGE_DIR = os.path.join(tmp, "moment_images")
A.MODERATION_LOG = os.path.join(tmp, "moderation.log")
A.init_db()
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT id, api_token FROM tenants").fetchone(); TID, TOKEN = tok["id"], tok["api_token"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("沈知意", "SHENZY0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
c.commit()

FAKE = {
    "163": [{"platform": "163", "id": 186016, "mid": "", "name": "晴天", "artists": "周杰伦", "album": "叶惠美",
             "cover": "https://p2.music.126.net/x.jpg", "vip": False}],
    "qq":  [{"platform": "qq", "id": 97773, "mid": "0039MnYb0qxYhV", "name": "晴天", "artists": "周杰伦", "album": "叶惠美",
             "cover": "https://y.gtimg.cn/x.jpg", "vip": True}],
}
A._song_search = lambda q, platform="163": [] if q == "搜不到" else FAKE["qq" if platform == "qq" else "163"]
A._song_lookup = lambda platform, key: next((s for s in FAKE[platform] if str(key) in (str(s["id"]), s["mid"])), None)

app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me/song")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def web_song(cl, platform, key, to="", message=""):
    r = cl.post("/p/me/song", data={"platform": platform, "song_id": key, "to": to, "message": message}, headers={"X-CSRF": cl.csrf})
    return r.get_json()
def group_song(from_role, keyword, to="", message="", platform=None):
    return app.test_client().post("/api/song/request", headers={"X-Archive-Token": TOKEN},
                                  json={"from_role": from_role, "keyword": keyword, "to_role": to, "message": message,
                                        "platform": platform}).get_json()

lin, zy, sz = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001")

# 搜索接口要激活码；页面能打开
ok(app.test_client().get("/p/me/song/search?q=晴天").status_code == 401, "search needs code")
ok(lin.get("/p/me/song/search?q=晴天&platform=qq").get_json()["songs"][0]["mid"] == "0039MnYb0qxYhV", "qq search")
ok("匿名点歌" in lin.get("/p/me/song").get_data(as_text=True), "song page")

# 网页点歌（网易云，点给周屿）→ 匿名；周屿的点歌台收到；公开播报里只有「有人」
js = web_song(lin, "163", "186016", to="周屿", message="生日快乐"); ok(js["ok"] and "今日第 1/3 首" in js["msg"], js)
pub = sz.get("/p/me/public").get_data(as_text=True)
ok("有人点给 周屿" in pub and "晴天" in pub and "生日快乐" in pub and "林晚" not in pub.split('id="appearance"')[0].split("<body>")[1].replace("data-name=\"林晚\"", ""), "public anonymous")
zp = zy.get("/p/me/点歌台").get_data(as_text=True); ok("有人为你点了一首歌" in zp and "生日快乐" in zp and "林晚" not in zp.split("<body>")[1].split("PHONE_AVATARS")[0], "recipient anonymous")
ok("点歌台" in zy.get("/p/me").get_data(as_text=True), "inbox thread")
ok("你匿名点给 周屿" in lin.get("/p/me/点歌台").get_data(as_text=True), "sender sees own")
ok("点歌台" not in sz.get("/p/me").get_data(as_text=True), "bystander has no 点歌台 thread")

# 群里点歌：不写平台先网易云；写 QQ 走 QQ；点给大家；次数跟网页一起算（上限 3）
js = group_song("林晚", "晴天", to="大家"); ok(js["ok"] and "给大家" in js["msg"] and "2/3" in js["msg"], js)
js = group_song("林晚", "晴天", platform="qq", message="QQ 版"); ok(js["ok"] and "3/3" in js["msg"], js)
js = web_song(lin, "163", "186016"); ok(not js["ok"] and "今天已经点了 3 首" in js["msg"], js)
ok(not group_song("周屿", "搜不到")["ok"], "not found")
ok("不能点给自己" in group_song("周屿", "晴天", to="周屿")["msg"], "self")
js = group_song("周屿", "晴天", to="小狐狸"); ok(js["ok"] and "给 小狐狸" in js["msg"], js)  # 名单外的称呼可以
ok("有人点给 小狐狸" in sz.get("/p/me/public").get_data(as_text=True), "custom target in public")
ok("点歌台" not in sz.get("/p/me").get_data(as_text=True), "custom target reaches nobody")
ok("最多 20 字" in group_song("周屿", "晴天", to="长" * 21)["msg"], "target too long")
ok("不允许的字词" in group_song("周屿", "晴天", to="加vx")["msg"], "blocked target")
ok("不允许的字词" in group_song("周屿", "晴天", message="加vx")["msg"], "blocked message")
ok(app.test_client().post("/api/song/request", json={}).status_code == 403, "api needs token")

# QQ 的歌：卡片没有播放按钮（不能嵌入），有「在QQ音乐打开」
pub = sz.get("/p/me/public").get_data(as_text=True)
ok("在QQ音乐打开" in pub and "y.qq.com/n/ryqq/songDetail/0039MnYb0qxYhV" in pub and "VIP" in pub, "qq card")
ok('data-song="186016"' in pub, "netease play button")

# 机器人同步：拿到 3 首待播（含平台、id、匿名）→ 回报后不再给
def sync(done=None):
    return app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN},
                                  json={"after": 0, "songs_done": done or [], "snapshot": {"game_day": "D1",
                                        "roster": [{"name": n} for n in ("林晚", "周屿", "沈知意")], "rules": {}}}).get_json()
songs = sync()["songs"]; ok(len(songs) == 4 and {s["platform"] for s in songs} == {"163", "qq"} and "from_role" not in songs[0], songs)
ok(sync(done=[s["id"] for s in songs])["songs"] == [], "acked")
# 超过 2 小时没播的不补发
group_song("周屿", "晴天")
c.execute("UPDATE song_requests SET created_at=created_at-3*3600*1000 WHERE from_role='周屿'"); c.commit()
ok(sync()["songs"] == [], "stale not announced")

# 后台：能看到真实点歌人、改上限、删除
adm = app.test_client()
with adm.session_transaction() as s: s["tenant_id"] = TID; s["admin_logged_in"] = True; s["view_show_id"] = SID
page = adm.get("/admin/phone_codes").get_data(as_text=True); ok("<td>林晚</td>" in page, "admin sees requester")
adm.post("/admin/phone_codes", data={"action": "song_daily", "n": "5"})
ok(web_song(lin, "163", "186016")["ok"], "cap raised")
sid_del = c.execute("SELECT id FROM song_requests WHERE message='生日快乐'").fetchone()[0]
adm.post("/admin/phone_codes", data={"action": "delete_song", "id": str(sid_del)})
ok("生日快乐" not in sz.get("/p/me/public").get_data(as_text=True), "admin delete")

# 不在主档期不能点
c.execute("UPDATE shows SET schedule_start='0101', schedule_end='0102' WHERE id=?", (SID,)); c.commit()
ok("不在档期内" in group_song("沈知意", "晴天")["msg"], "zone")
print("ALL OK")
