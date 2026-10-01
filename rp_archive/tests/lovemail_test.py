"""心动信（网页手机）：规则/次数跟着插件快照走、网页投信交给机器人、撤回（网页的 / 已在信池里的）、收件人只看到署名、往期
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/lovemail_test.py ；全部通过时最后一行打印 ALL OK。
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
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,'ADMINCODE1')", (TID, SID))
c.commit()

app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter")
    cl.get("/p/me/lovemail")
    with cl.session_transaction() as s: cl.csrf = s["phone_csrf"]
    return cl
def page(cl, view="inbox"):
    return cl.get("/p/me/lovemail?view=" + view).get_data(as_text=True)
def body(html):
    return html.split('<div class="scroll lm-page"')[1].split("</main>")[0].split("PHONE_AVATARS")[0]
def send(cl, to, content, signature=""):
    cl.post("/p/me/lovemail", data={"csrf": cl.csrf, "to": to, "content": content, "signature": signature})
    with cl.session_transaction() as s: return s.get("lm_flash", "") or ""
def revoke(cl, ts=0, web_id=0):
    cl.post("/p/me/lovemail", data={"csrf": cl.csrf, "action": "revoke", "ts": ts, "web_id": web_id})
    with cl.session_transaction() as s: return s.get("lm_flash", "") or ""

ROSTER = [{"name": n, "npc": False} for n in ("林晚", "周屿", "沈知意")]
RULES = {"enabled": True, "has_day": True, "window": None, "limit": 2, "delivery_time": "22:00"}
def sync(lovemail=None, rules=None, feature_off=None, done=None, revoke_done=None, game_day="D2"):
    snap = {"game_day": game_day, "roster": ROSTER, "feature_off": feature_off or {},
            "rules": {"lovemail": rules} if rules is not None else {}}
    if lovemail is not None:
        snap["lovemail"] = lovemail
    r = app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN},
                               json={"snapshot": snap, "lovemail_done": done or [], "lovemail_revoke_done": revoke_done or []})
    ok(r.status_code == 200, r.get_data(as_text=True)); return r.get_json()

lin, zy, sz = player("LINWAN0001"), player("ZHOUYU0001"), player("SHENZY0001")

# 旧版插件（快照里没有 rules.lovemail）：页面提示升级，收件箱不显示入口，投不了
sync(rules=None)
ok("等机器人升级" in page(lin, "write"), "needs plugin upgrade")
ok('href="/p/me/lovemail"' in lin.get("/p/me").get_data(as_text=True), "nav tab always there")
ok("升级" in send(lin, "周屿", "你好"), "cannot send before upgrade")

# 新版快照：林晚今天群里已投 1 封（上限 2），信池里有她群里投的一封
GROUP_TS = 1700000000111
POOL = [{"from": "林晚", "to": "沈知意", "content": "群里投的信", "signature": "小猫", "game_day": "D2", "ts": GROUP_TS, "web_id": 0}]
sync(rules=RULES, lovemail={"counts": {"林晚": 1}, "pending": POOL})
w = page(lin, "write")
ok("已投 1/2" in w and "22:00 派送" in w and "投进信箱" in w and "disabled" not in w.split("投进信箱")[0].split("<button")[-1], "write page open")
ok("群里投的信" in page(lin, "sent") and "群里投的信" not in page(sz, "sent"), "pending only for sender")

# 校验：收件人必须在名单里、不能空、字数、署名字数、违禁词、CQ 码
ok("找不到这个收件人" in send(lin, "路人", "你好"), "unknown receiver")
ok("写点什么" in send(lin, "周屿", "   "), "empty")
ok("最多 500 字" in send(lin, "周屿", "长" * 501), "too long")
ok("署名最多 20 字" in send(lin, "周屿", "你好", "名" * 21), "sig too long")
ok("不允许的字词" in send(lin, "周屿", "加vx聊"), "blocked")
ok("CQ" in send(lin, "周屿", "[CQ:image,file=x]"), "cq code")

# 投一封 → 用满当天上限；再投被拒
msg = send(lin, "周屿", "今晚的月亮很好看", "不告诉你")
ok("已投进「周屿」的信箱" in msg and "22:00" in msg and "还能投 0 封" in msg, msg)
ok("上限 2 封" in send(lin, "周屿", "再来一封"), "daily cap (group + web)")
ok("今晚的月亮很好看" in page(lin, "sent"), "web letter pending")

# 机器人同步：拿到这封（带投递时间），标成已交出；同一封没回报前会重复给（插件靠 seen 去重）
d = sync(rules=RULES, lovemail={"counts": {"林晚": 1}, "pending": POOL})
ok(len(d["lovemails"]) == 1 and d["lovemails"][0]["from_role"] == "林晚" and d["lovemails"][0]["signature"] == "不告诉你", d)
WEB = d["lovemails"][0]
ok(c.execute("SELECT handed_at FROM phone_lovemails WHERE id=?", (WEB["id"],)).fetchone()[0] > 0, "handed")
# 插件已放进信池（快照里带 web_id）并回报 done：变 taken，页面不重复显示，次数按快照算
POOL2 = POOL + [{"from": "林晚", "to": "周屿", "content": WEB["content"], "signature": "不告诉你", "game_day": "D2",
                 "ts": WEB["timestamp"], "web_id": WEB["id"]}]
d = sync(rules=RULES, lovemail={"counts": {"林晚": 2}, "pending": POOL2}, done=[WEB["id"]])
ok(d["lovemails"] == [], "taken not handed again")
ok(page(lin, "sent").count("今晚的月亮很好看") == 1 and "已投 2/2" in page(lin, "write"), "no double count")

# 撤回信池里的信（网页投的已被取走 → 按投递时间撤）：生成撤回请求，页面显示撤回中；机器人处理后回报
ok("撤回已提交" in revoke(lin, ts=WEB["timestamp"]), "revoke taken web letter")
ok("撤回中" in page(lin, "sent"), "revoking shown")
ok("撤回已提交" in revoke(lin, ts=GROUP_TS), "revoke group letter")
ok("找不到这封信" in revoke(lin, ts=123), "revoke unknown")
ok("找不到这封信" in revoke(zy, ts=GROUP_TS), "cannot revoke others' letter")
d = sync(rules=RULES, lovemail={"counts": {"林晚": 2}, "pending": POOL2})
ok(sorted(r["ts"] for r in d["lovemail_revokes"]) == sorted([WEB["timestamp"], GROUP_TS]), d)
d = sync(rules=RULES, lovemail={"counts": {"林晚": 0}, "pending": []}, revoke_done=[r["id"] for r in d["lovemail_revokes"]])
ok(d["lovemail_revokes"] == [] and "撤回中" not in page(lin, "sent") and "已投 0/2" in page(lin, "write"), "revoke done")

# 网页投的、还没交给机器人：直接作废，不产生撤回请求
ok("已投进" in send(lin, "沈知意", "还没交出去的信"), "send again after revoke")
wid = c.execute("SELECT id FROM phone_lovemails WHERE content='还没交出去的信'").fetchone()[0]
ok("已撤回" in revoke(lin, web_id=wid), "revoke unhanded")
ok("还没交出去的信" not in page(lin, "sent") and "已投 0/2" in page(lin, "write"), "unhanded revoke frees quota")
ok(sync(rules=RULES, lovemail={"counts": {}, "pending": []})["lovemails"] == [], "revoked never handed")
ok(c.execute("SELECT COUNT(*) FROM phone_lovemail_revokes WHERE done=0").fetchone()[0] == 0, "no revoke request")
ok("交给邮差" in revoke(sz, web_id=wid), "cannot revoke others' web letter")

# 派送后（机器人 POST /api/event）：收件人看到内容和署名、看不到发件人；寄件人「寄出的」里看到寄给谁
ev = {"type": "lovemail", "from_role": "林晚", "from_custom_name": "不告诉你", "to_role": "周屿", "content": "今晚的月亮很好看",
      "extra_info": {"signature": "不告诉你", "isPublic": True}, "game_day": "D2", "timestamp": WEB["timestamp"]}
ok(app.test_client().post("/api/event", headers={"X-Archive-Token": TOKEN}, json=ev).get_json()["ok"], "event")
zb = body(page(zy))
ok("今晚的月亮很好看" in zb and "不告诉你" in zb and "林晚" not in zb and "飘落到了公告区" in zb, "recipient anonymous")
_nav = zy.get("/p/me").get_data(as_text=True)
ok('data-also="__lovemail__" data-also-ts="' in _nav and 'data-also-ts="0"' not in _nav, "unread marker on nav tab")   # 心动信箱并进了底栏「发现」，未读时间戳是 data-also-ts
ok("收到的 1" in page(zy), "recipient count")
ok("寄给 周屿" in page(lin, "sent") and "已派送" in page(lin, "sent"), "sender history")
ok("今晚的月亮很好看" not in body(page(sz)) and "今晚的月亮很好看" not in page(sz, "sent"), "bystander sees nothing")

# 不能投的各种情况
sync(rules=RULES, lovemail={"counts": {}, "pending": []}, feature_off={"林晚": ["lovemail"]})
ok("已被管理员关闭" in page(lin, "write"), "feature off")
sync(rules=dict(RULES, enabled=False), lovemail={"counts": {}, "pending": []})
ok("心动信箱已关闭" in page(lin, "write"), "toggle off")
sync(rules=dict(RULES, limit=0), lovemail={"counts": {}, "pending": []})
ok("D2 的心动信投稿已关闭" in page(lin, "write"), "day closed")
sync(rules=dict(RULES, has_day=False), lovemail={"counts": {}, "pending": []})
ok("还没设置游戏天数" in page(lin, "write"), "no game day")
h = A.datetime.now(A.TZ_BEIJING).hour
sync(rules=dict(RULES, window={"start": (h + 1) % 24, "end": (h + 2) % 24 or 24}), lovemail={"counts": {}, "pending": []})
ok("开放时间" in page(lin, "write"), "window")
sync(rules=RULES, lovemail={"counts": {}, "pending": []})
c.execute("UPDATE phone_sync SET synced_at=? WHERE show_id=?", (int(time.time() * 1000) - 11 * 60 * 1000, SID)); c.commit()
ok("机器人暂时没连上" in page(lin, "write") and "没连上" in send(lin, "周屿", "离线时投"), "stale snapshot")

# 页面过期、管理身份、没登录
sync(rules=RULES, lovemail={"counts": {}, "pending": []})
lin.post("/p/me/lovemail", data={"csrf": "bad", "to": "周屿", "content": "x"})
with lin.session_transaction() as s: ok("页面过期" in s["lm_flash"], "csrf")
adm = app.test_client(); adm.get("/p/ADMINCODE1")
ok(adm.get("/p/me/lovemail").status_code == 302, "admin redirected")
ok(app.test_client().get("/p/me/lovemail").status_code == 302, "needs code")
print("ALL OK")
