"""网页手机·查看：激活码进门/视角（误送/改内容/撕信不透露）/重置与季度结束失效/爆破限流/后台生成与手动添加
用法（仓库根目录）：rp_archive/venv/bin/python3 rp_archive/tests/phone_view_test.py
不碰真实数据库：DB_PATH 指向临时目录。全部通过时最后一行打印 ALL OK。
"""
import sys, os, json, re, sqlite3, tempfile
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "t.db")
from werkzeug.security import generate_password_hash
A.init_db()
c = sqlite3.connect(A.DB_PATH)
h = generate_password_hash("dev", method="pbkdf2:sha256")
c.execute("INSERT INTO tenants (username, view_password_hash, admin_password_hash, api_token) VALUES ('dev',?,?,'tok')", (h,h))
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (1,'第三季',1)")
for r in ["林晚","周屿","沈知意"]:
    c.execute("INSERT INTO players (show_id,tenant_id,qq,role_name,sessions_count,total_replies,total_words,last_updated) VALUES (1,1,?,?,0,0,0,0)", (r,r))
T=1790000000000
ev=[("sms","林晚","沈知意","明天早餐一起吗",{"delivered":"明天早餐一起吗","signature":"落款：林晚","intended_to":"周屿","is_misdelivered":True},"D2",1),
    ("sms","沈知意","周屿","我讨厌下雨天",{"delivered":"我喜欢下雨天","signature":"落款：林晚","is_content_chaos":True,"is_signature_chaos":True},"D2",2),
    ("sms","周屿","林晚","秘密前半",{"delivered":"秘密前半\n（信纸的后半页不知去向……）","signature":"落款：周屿","is_torn":True,"torn_holder":"沈知意","torn_second_half":"秘密后半"},"D2",3),
    ("gift","周屿","沈知意","",{"giftName":"黑伞"},"D2",4),
    ("gift","林晚","周屿","",{"giftName":"丢的礼物","isLost":True},"D2",5)]
for t,f,to,ct,info,d,m in ev:
    c.execute("INSERT INTO extra_events (show_id,tenant_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) VALUES (1,1,'',?,?,?,?,?,?,?)",(t,f,to,ct,json.dumps(info,ensure_ascii=False),T+m*60000,d))
c.commit()
app=A.app; app.testing=True
adm=app.test_client()
with adm.session_transaction() as s: s["tenant_id"]=1; s["admin_logged_in"]=True
r=adm.post("/admin/phone_codes", data={"action":"generate_all"}); assert r.status_code==302
page=adm.get("/admin/phone_codes").get_data(as_text=True)
codes=dict(c.execute("SELECT role_name, code FROM phone_codes").fetchall()); print("codes", codes)
assert all(len(v)==10 for v in codes.values()) and len(codes)==3
def inbox(role):
    cl=app.test_client()
    r=cl.get("/p/"+codes[role].lower()); assert r.status_code==302 and r.location.endswith("/p/me"), r.status_code
    h=cl.get("/p/me"); assert h.headers["Cache-Control"]=="no-store" and h.headers["Referrer-Policy"]=="no-referrer"
    body=h.get_data(as_text=True); assert codes[role] not in body
    return cl, body
cl,b=inbox("林晚")
# 林晚 发给周屿但误送到沈知意：林晚看到挂在周屿名下；没有误送提示
assert "周屿" in b and "沈知意" not in b and "误送" not in b, b
t=cl.get("/p/me/周屿").get_data(as_text=True); assert "明天早餐一起吗" in t
# 林晚收到被撕的信：未知号码
assert "未知号码" in b
cl,b=inbox("周屿")
# 周屿收到内容被改+落款换成林晚：显示在林晚名下、看到被改后的内容，看不到原文和真发件人
assert "林晚" in b and "沈知意" not in b, b
t=cl.get("/p/me/林晚").get_data(as_text=True)
assert "我喜欢下雨天" in t and "class=\"sig\">林晚<" in t and "我讨厌" not in t and "沈知意" not in t, t
assert "丢的礼物" not in cl.get("/p/me/林晚").get_data(as_text=True)
# 周屿送出的礼物不出现在自己手机
assert "黑伞" not in b
cl,b=inbox("沈知意")
assert "林晚" in b  # 误收林晚的短信，按落款认人
assert "黑伞" in cl.get("/p/me/周屿").get_data(as_text=True)
assert "……秘密后半" in cl.get("/p/me/周屿").get_data(as_text=True)  # 残页（落款周屿）
assert "我讨厌下雨天" in cl.get("/p/me/周屿").get_data(as_text=True)  # 自己发的原文
# 看别人的：沈知意 打开 /p/me/xxx 只能看到自己相关
assert "明天早餐" in cl.get("/p/me/林晚").get_data(as_text=True)  # 这条她确实收到了
# 重置后旧会话失效
adm.post("/admin/phone_codes", data={"action":"reset","role":"沈知意"})
r=cl.get("/p/me"); assert r.status_code==302 and r.location.endswith("/p"), r.status_code
# 季度结束后失效
cl2,_=inbox("林晚")
c.execute("UPDATE shows SET is_current=0"); c.commit()
assert cl2.get("/p/me").status_code==302
assert app.test_client().get("/p/"+codes["周屿"]).status_code==404
c.execute("UPDATE shows SET is_current=1"); c.commit()
# 爆破限流
A._phone_fails.clear(); bf=app.test_client()
for i in range(10): assert bf.get("/p/AAAAAAAAAA").status_code==404
assert bf.get("/p/"+codes["周屿"]).status_code==429
assert bf.post("/p", data={"code":codes["周屿"]}).status_code==429
A._phone_fails.clear()
# 未登录后台不能生成
assert app.test_client().post("/admin/phone_codes", data={"action":"generate_all"}).status_code==302
assert app.test_client().get("/p/me").status_code==302
# 退出
cl3,_=inbox("周屿"); cl3.post("/p/logout"); assert cl3.get("/p/me").status_code==302
# 旧 /phone 不存在
assert app.test_client().get("/phone").status_code==404
# 手动添加（开季前名单为空的情况）+ 删除
adm.post("/admin/phone_codes", data={"action":"add_roles","names":"新人甲\n新人乙，林晚"})
got=dict(c.execute("SELECT role_name, code FROM phone_codes").fetchall())
assert "新人甲" in got and "新人乙" in got and got["林晚"]==codes["林晚"], got
pg=adm.get("/admin/phone_codes").get_data(as_text=True); assert "新人甲" in pg and got["新人甲"] in pg
nc=app.test_client(); assert nc.get("/p/"+got["新人甲"]).status_code==302
assert "还没有短信和礼物" in nc.get("/p/me").get_data(as_text=True)
adm.post("/admin/phone_codes", data={"action":"delete","role":"新人乙"})
assert "新人乙" not in adm.get("/admin/phone_codes").get_data(as_text=True)
# 只有玩家入口强制 HTTPS，保留路径和查询串；本地仍可 HTTP
secure = app.test_client()
r = secure.get("/p/xxx?x=1", base_url="http://archive.changri.work")
assert r.status_code == 301 and r.location == "https://archive.changri.work/p/xxx?x=1"
assert secure.get("/p", base_url="http://127.0.0.1").status_code == 200
assert secure.post("/api/phone/sync", base_url="http://archive.changri.work", json={}).status_code != 301
with app.test_request_context("/", base_url="http://archive.changri.work"):
    assert A._phone_base_url() == "https://archive.changri.work"
# 手机的记住登录不把整站 session 变成长效 cookie
remember = app.test_client()
with remember.session_transaction() as sess:
    sess["tenant_id"] = 1
r = remember.get("/p/" + codes["林晚"])
cookies = r.headers.getlist("Set-Cookie")
assert any("phone_auth=" in h and "Max-Age=2592000" in h and "HttpOnly" in h and "SameSite=Lax" in h for h in cookies)
assert all("Expires=" not in h and "Max-Age=" not in h for h in cookies if h.startswith("session="))
with remember.session_transaction() as sess:
    assert sess["tenant_id"] == 1 and not sess.permanent and "phone_code" not in sess
fresh = app.test_client()
fresh.set_cookie(A._PHONE_COOKIE, remember.get_cookie(A._PHONE_COOKIE, path="/p").value, path="/p")
assert fresh.get("/p/me").status_code == 200
fresh.set_cookie(A._PHONE_COOKIE, "tampered", path="/p")
assert fresh.get("/p/me").status_code == 302
from unittest.mock import patch
with patch("itsdangerous.timed.time.time", return_value=1):
    expired = A._phone_signer().dumps(codes["林晚"])
fresh.set_cookie(A._PHONE_COOKIE, expired, path="/p")
assert fresh.get("/p/me").status_code == 302
r = app.test_client().get("/p/" + codes["林晚"], base_url="https://archive.changri.work")
assert "Secure" in r.headers["Set-Cookie"]
print("ALL OK")
