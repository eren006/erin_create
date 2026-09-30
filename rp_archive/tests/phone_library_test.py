"""检索/本机收藏数据源的视角隔离、身份校验和原对话定位；只用临时数据库。"""
import json, os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), "library.db")
A.init_db()
c = sqlite3.connect(A.DB_PATH)
tid = c.execute("SELECT id FROM tenants LIMIT 1").fetchone()[0]
c.execute("UPDATE shows SET is_current=0")
sid = c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'检索测试',1)", (tid,)).lastrowid
for role, code in [('甲','AAAAAAAAAB'),('乙','BBBBBBBBBC'),('丙','CCCCCCCCCD')]:
    c.execute("INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)", (tid,sid,role,code))
def event(kind, frm, to, text, info):
    c.execute("INSERT INTO extra_events (tenant_id,show_id,session_id,type,from_role,to_role,content,extra_info,timestamp,game_day) VALUES (?,?,'',?,?,?,?,?,1000,'D1')",
              (tid,sid,kind,frm,to,text,json.dumps(info)))
event('sms','丙','乙','不能给乙看的原文',{'delivered':'乙收到的改写','signature':'落款：甲'})
event('sms','甲','丙','甲想写给乙',{'intended_to':'乙','signature':'落款：甲','is_misdelivered':True})
event('sms','丙','乙','前半张纸',{'is_torn':True,'torn_holder':'甲','torn_second_half':'后半张纸','signature':'落款：丙'})
event('gift','甲','乙','丢失礼物秘密',{'giftName':'不可见礼物','isLost':True})
event('gift','甲','乙','<script>alert(1)</script>',{'giftName':'白色围巾'})
c.commit()
A.app.testing=True
client=A.app.test_client()
assert client.get('/p/me/library').status_code==302
assert client.get('/p/me/library/data').status_code==401
client.get('/p/BBBBBBBBBC')
r=client.get('/p/me/library/data')
assert r.status_code==200 and r.headers['Cache-Control']=='no-store'
records=r.json['records']; texts=[m['text'] for m in records]
assert '乙收到的改写' in texts and '不能给乙看的原文' not in texts
assert '甲想写给乙' not in texts and '丢失礼物秘密' not in texts and '后半张纸' not in texts
changed=next(m for m in records if m['text']=='乙收到的改写')
assert changed['other']=='甲' and changed['signature']=='落款：甲'
assert any(m['other']=='未知号码' for m in records)
assert all('id' not in m and 'extra_info' not in m and len(m['key'])==32 for m in records)
assert all(set(m)=={'key','other','mine','kind','text','gift_name','signature','day','time','ts','url'} for m in records)
for m in records:
    page=client.get(m['url'].split('#')[0]).get_data(as_text=True)
    assert 'id="message-'+m['key']+'"' in page
    assert '<script>alert(1)</script>' not in page
for view in ('search','saved','profile'):
    assert client.get('/p/me/library?view='+view).status_code==200
key=changed['key']
other=A.app.test_client(); other.get('/p/AAAAAAAAAB')
assert key not in [m['key'] for m in other.get('/p/me/library/data').json['records']]
c.execute("DELETE FROM phone_codes WHERE role_name='乙'");c.commit()
assert client.get('/p/me/library/data').status_code==401
c.execute("UPDATE shows SET is_current=0 WHERE id=?",(sid,));c.commit()
assert other.get('/p/me/library/data').status_code==401
print('LIBRARY OK')
