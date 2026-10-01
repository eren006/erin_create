"""主题配置：后台权限、季度隔离、预览不保存、文案转义与玩家原文。"""
import sys, tempfile, sqlite3, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as A
A.DB_PATH=str(Path(tempfile.mkdtemp())/'test.db');A.init_db();A.app.testing=True
c=sqlite3.connect(A.DB_PATH);tid=c.execute('SELECT id FROM tenants LIMIT 1').fetchone()[0]
c.execute('UPDATE shows SET is_current=0')
sid=c.execute("INSERT INTO shows(tenant_id,name,is_current) VALUES (?,'主题测试',1)",(tid,)).lastrowid
other=c.execute("INSERT INTO shows(tenant_id,name,is_current) VALUES (?,'其他季度',0)",(tid,)).lastrowid
c.execute("INSERT INTO phone_codes(tenant_id,show_id,role_name,code) VALUES (?,?,'林晚','THEME00001')",(tid,sid));c.commit()
adm=A.app.test_client()
with adm.session_transaction() as s:s['tenant_id']=tid;s['admin_logged_in']=True;s['view_show_id']=sid
assert adm.get('/admin/phone_codes').status_code==200
with adm.session_transaction() as s:csrf=s['theme_csrf']
player=A.app.test_client();player.get('/p/THEME00001')
assert player.post('/admin/phone_codes',data={'action':'phone_theme'}).status_code==302
assert adm.post('/admin/phone_codes',data={'action':'phone_theme','visual':'classic','copy':'classic'}).status_code==403
for key in A.PHONE_THEMES:
 r=adm.post('/admin/phone_codes',data={'action':'phone_theme','theme_csrf':csrf,'visual':key,'copy':key})
 assert r.status_code==302
 text=player.get('/p/me').get_data(as_text=True)
 assert A.PHONE_COPY[key]['messages'] in text
 assert A.PHONE_THEMES[key]['accent'] in text
 assert 'themes[prefs.theme]' in text and 'phone.dataset.wall = prefs.wall' in text
 with A.app.app_context():assert A.phone_theme(other)['visual']=='modern'
before=c.execute('SELECT theme_config FROM phone_settings WHERE show_id=?',(sid,)).fetchone()[0]
assert adm.get('/admin/phone_theme_preview?visual=scifi&copy=classic').status_code==200
assert c.execute('SELECT theme_config FROM phone_settings WHERE show_id=?',(sid,)).fetchone()[0]==before
assert adm.post('/admin/phone_codes',data={'action':'phone_theme','theme_csrf':csrf,'visual':'evil','copy':'modern'}).status_code==400
adm.post('/admin/phone_codes',data={'action':'phone_theme','theme_csrf':csrf,'visual':'modern','copy':'classic','word_messages':'<script>alert(1)</script>'})
text=player.get('/p/me').get_data(as_text=True)
assert '&lt;script&gt;alert(1)&lt;/script&gt;' in text and '<script>alert(1)</script>' not in text
with adm.session_transaction() as s:s['tenant_id']=tid+999
assert adm.post('/admin/phone_codes',data={'action':'phone_theme','theme_csrf':csrf,'visual':'classic','copy':'classic'}).status_code in (302,404)
print('THEMES OK')
