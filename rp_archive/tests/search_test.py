"""首页全局搜索 /p/me/search：联系人/群聊、短信礼物（含群聊消息）、心动信（来信只有署名）、朋友圈；只看本人视角，别人的不会搜出来
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/search_test.py ；全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, sqlite3, tempfile, time
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
c.execute("INSERT INTO phone_admin_codes (tenant_id,show_id,code) VALUES (?,?,'ADMINCODE1')", (TID, SID))
c.commit()
app = A.app; app.testing = True
def ok(cond, msg):
    if not cond: raise AssertionError(msg)
app.test_client().post("/api/phone/sync", headers={"X-Archive-Token": TOKEN}, json={"after": 0, "snapshot": {
    "game_day": "D2", "roster": [{"name": n} for n in ("林晚", "周屿", "沈知意")]}})
now = int(time.time() * 1000)
def event(t, frm, to, content, info, day="D2"):
    c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) VALUES (?,?,?,?,?,?,?,?,?,?)",
              (SID, TID, "", t, frm, to, content, json.dumps(info, ensure_ascii=False), now, day)); c.commit()
event("sms", "周屿", "林晚", "今晚天台见，带上吉他", {"delivered": "今晚天台见，带上吉他", "signature": "落款：周屿"})
event("sms", "周屿", "沈知意", "这是别人的秘密吉他", {"delivered": "这是别人的秘密吉他", "signature": "落款：周屿"})
event("gift", "周屿", "林晚", "手写谱", {"giftName": "吉他拨片"})
event("lovemail", "沈知意", "林晚", "我喜欢你的吉他声", {"signature": "猫"})
c.execute("INSERT INTO moments (tenant_id, show_id, role_name, content, game_day, created_at) VALUES (?,?,?,?,?,?)", (TID, SID, "周屿", "练了一下午吉他", "D2", now)); c.commit()
def player(code):
    cl = app.test_client(); ok(cl.get("/p/" + code).status_code == 302, "enter"); return cl
def search(cl, q):
    return {g["key"]: g["items"] for g in cl.get("/p/me/search", query_string={"q": q}).get_json()["groups"]}
lin, zy = player("LINWAN0001"), player("ZHOUYU0001")

# 只看自己能看到的：林晚搜「吉他」→ 短信1条 + 礼物1条 + 心动信1封 + 朋友圈1条；周屿给沈知意的那条不会出现
r = search(lin, "吉他")
ok(set(r) == {"msgs", "lovemail", "moments"}, r.keys())
texts = " ".join(i["pre"] + i["hit"] + i["post"] for i in r["msgs"])
ok(len(r["msgs"]) == 2 and "带上吉他" in texts and "吉他拨片" in texts and "秘密" not in texts, texts)
ok(r["msgs"][0]["hit"] == "吉他" and r["msgs"][0]["url"].startswith("/p/me/") and "#message-" in r["msgs"][0]["url"], r["msgs"][0])
ok(r["lovemail"][0]["meta"].startswith("署名：猫") and "沈知意" not in json.dumps(r["lovemail"], ensure_ascii=False), "lovemail anonymous")
ok(r["moments"][0]["title"] == "周屿", "moments")
# 大小写/空格无关；空关键词空结果；太长截断
ok(search(lin, "  吉他 ") == r or set(search(lin, "  吉他 ")) == set(r), "trim")
ok(app.test_client().get("/p/me/search?q=").status_code == 401, "needs login")
ok(lin.get("/p/me/search?q=").get_json()["groups"] == [], "empty q")
# 联系人：对话里的人、名单里还没聊过的人；自己不在其中
r = search(lin, "沈")
ok(r["people"][0]["title"] == "沈知意" and "开始对话" in r["people"][0]["sub"], r)
ok("people" not in search(lin, "林晚"), "self excluded")
r = search(lin, "周"); ok(r["people"][0]["title"] == "周屿" and r["people"][0]["url"] == "/p/me/%E5%91%A8%E5%B1%BF", r["people"][0])
# 周屿视角：自己发的短信能搜到；群里送出的礼物只进收件人手机，发件人搜不到（同手机里看不到一样），沈知意的心动信搜不到（那是寄给林晚的）
r = search(zy, "吉他"); ok("lovemail" not in r and len(r["msgs"]) == 2 and "吉他拨片" not in json.dumps(r, ensure_ascii=False), {k: len(v) for k, v in r.items()})
# 管理身份拿到空结果
adm = app.test_client(); adm.get("/p/ADMINCODE1"); ok(adm.get("/p/me/search?q=吉他").get_json()["groups"] == [], "admin empty")
# LIKE 特殊字符当普通文字
ok(search(lin, "%") == {} and search(lin, "_") == {}, "wildcards are literal")
print("ALL OK")
