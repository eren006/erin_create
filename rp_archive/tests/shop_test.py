"""网页礼品店/图鉴/预设礼物/NPC 标识
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/shop_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A

tmp = tempfile.mkdtemp()
A.DB_PATH = os.path.join(tmp, "t.db")
A.MOMENT_IMAGE_DIR = os.path.join(tmp, "moment_images")
A.MODERATION_LOG = os.path.join(tmp, "moderation.log")
A.init_db()
A._PHONE_MIN_GAP_MS = 0
c = sqlite3.connect(A.DB_PATH); c.row_factory = sqlite3.Row
tok = c.execute("SELECT id, api_token FROM tenants").fetchone(); TID, TOKEN = tok["id"], tok["api_token"]
c.execute("UPDATE shows SET is_current=0")
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'本季',1)", (TID,))
SID = c.execute("SELECT id FROM shows WHERE name='本季'").fetchone()[0]
for r, code in [("林晚", "LINWAN0001"), ("周屿", "ZHOUYU0001"), ("老板", "LAOBAN0001")]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (TID, SID, r, code))
PRESETS = {"#001": {"name": "玫瑰花束", "content": "一束盛开的玫瑰"}, "#002": {"name": "巧克力", "content": "一盒黑巧克力"},
           "#003": {"name": "怀表", "content": "古旧的银色怀表"}}
c.execute("INSERT INTO site_config (show_id, tenant_id, key, value) VALUES (?,?,'preset_gifts',?)", (SID, TID, json.dumps(PRESETS, ensure_ascii=False)))
c.execute("INSERT INTO phone_settings (show_id, web_send) VALUES (?,1)", (SID,))
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)

def sync(catalogs=None, displays=None, shop_after=0, gift_mode=0, on_receive=False):
    return app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 10**9, "shop_after": shop_after, "snapshot": {
        "game_day": "D1", "roster": [{"name": "林晚"}, {"name": "周屿"}, {"name": "老板", "npc": True}],
        "rules": {"chaos": {"dailyLimit": 50}, "mail_cooldown_min": 0, "gift_cooldown_min": 0, "gift_daily_limit": 50, "gift_mode": gift_mode},
        "counts": {"sms": {}, "gift": {}}, "last": {"sms": {}, "gift": {}},
        "catalogs": catalogs or {}, "displays": displays or {}, "shop": {"refresh_hours": 24, "catalog_on_receive": on_receive}}}).get_json()

def player(code):
    cl = app.test_client(); cl.get("/p/" + code); cl.get("/p/me/周屿")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def gift(cl, to, preset_id="", gift_name="", text=""):
    cl.post("/p/me/send", data={"to": to, "kind": "gift", "preset_id": preset_id, "gift_name": gift_name, "text": text, "csrf": cl.csrf})
    with cl.session_transaction() as s: return s.get("phone_flash", "")

lin = player("LINWAN0001")
# 旧插件（快照里没有 catalogs）：礼品店提示要等机器人升级
sync(); c.execute("UPDATE phone_sync SET snapshot=json_remove(snapshot, '$.catalogs')"); c.commit()
ok("要等机器人升级" in lin.get("/p/me/shop").get_data(as_text=True), "old plugin")

# 林晚已有 #001（机器人上报），逛一次：货架刷新成未拥有的一件并收进图鉴，记进 shop_log
sync(catalogs={"林晚": ["#001"]})
page = lin.get("/p/me/shop").get_data(as_text=True); ok("没见过的东西" in page, page[-800:])
row = c.execute("SELECT * FROM phone_shop_log WHERE role_name='林晚'").fetchone()
unlocked = json.loads(row["unlocked"]); ok(row["display_gift"] in ("#002", "#003") and row["display_gift"] in unlocked, dict(row))
# 再逛：同一件，已在图鉴
ok("已经在你的图鉴里了" in lin.get("/p/me/shop").get_data(as_text=True) or "全部" in lin.get("/p/me/shop").get_data(as_text=True), "revisit")
ok(c.execute("SELECT COUNT(*) FROM phone_shop_log").fetchone()[0] == 1, "no extra log on revisit")
# 只看图鉴不抽
book = lin.get("/p/me/shop?view=book").get_data(as_text=True); ok("去货架看看" in book and "玫瑰花束" in book, "book view")
# 机器人同步取走变化；回报游标后不再给
ev = sync(catalogs={"林晚": ["#001"]})["shop_events"]; ok(len(ev) == 1 and ev[0]["role"] == "林晚" and ev[0]["display"], ev)
ok(sync(catalogs={"林晚": ["#001"] + unlocked}, shop_after=ev[0]["id"])["shop_events"] == [], "cursor")

# 送预设礼物：只能送图鉴里的；内容是预设文字；不能附留言（写了也不用）
missing = [g for g in PRESETS if g not in ["#001"] + unlocked]
if missing:
    ok("不在你的图鉴里" in gift(lin, "周屿", preset_id=missing[0]), "not owned")
_m = gift(lin, "周屿", preset_id="#001", text="偷偷写留言"); ok("已成功将「玫瑰花束」" in _m, _m)
g = c.execute("SELECT content, extra_info FROM extra_events ORDER BY id DESC LIMIT 1").fetchone()
ok(g["content"] == "一束盛开的玫瑰" and json.loads(g["extra_info"])["giftName"] == "「玫瑰花束」", dict(g))
zy = player("ZHOUYU0001"); ok("一束盛开的玫瑰" in zy.get("/p/me/林晚").get_data(as_text=True), "recipient sees preset")
# 对话页的图鉴选择器只列已拥有的
tp = lin.get("/p/me/周屿").get_data(as_text=True); ok('data-pid="#001"' in tp and (not missing or f'data-pid="{missing[0]}"' not in tp), "picker owned only")

# 「仅允许预设礼物」：自定义礼物被拒，图鉴礼物照常
sync(catalogs={"林晚": ["#001"] + unlocked}, gift_mode=1)
ok("只能送图鉴里的礼物" in gift(lin, "周屿", gift_name="一束花"), "preset only rejects custom")
ok("已成功将" in gift(lin, "周屿", preset_id="#001"), "preset only allows preset")
ok('从图鉴选一件礼物' in lin.get("/p/me/周屿").get_data(as_text=True), "preset-only UI")

# 收到即入图鉴：多送几次，周屿大概率（每次 50%）解锁 #001
sync(catalogs={"林晚": ["#001"] + unlocked}, on_receive=True)
for _ in range(20):
    gift(lin, "周屿", preset_id="#001")
    if c.execute("SELECT COUNT(*) FROM phone_shop_log WHERE role_name='周屿'").fetchone()[0]:
        break
ok(c.execute("SELECT unlocked FROM phone_shop_log WHERE role_name='周屿'").fetchone()[0] == '["#001"]', "unlock on receive")
ok(c.execute("SELECT COUNT(*) FROM phone_shop_log WHERE role_name='周屿'").fetchone()[0] == 1, "only once")

# NPC 标识：名单里的 NPC 名字旁边有标记；匿名的点歌不会带出来
ok('老板<span class="npc-tag">NPC</span>' in lin.get("/p/me/new").get_data(as_text=True), "npc tag in contacts")
ok('npc-tag">NPC' not in lin.get("/p/me/周屿").get_data(as_text=True).split('<div class="title">')[1][:40], "no tag for player")
print("ALL OK")
