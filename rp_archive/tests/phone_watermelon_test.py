"""Watermelon registration, authenticated score lifecycle and local physics regression."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as A
A.DB_PATH = os.path.join(tempfile.mkdtemp(), 'watermelon.db')
A.init_db()
c = sqlite3.connect(A.DB_PATH)
tid = c.execute('SELECT id FROM tenants').fetchone()[0]
c.execute('UPDATE shows SET is_current=0')
c.execute("INSERT INTO shows (tenant_id,name,is_current) VALUES (?,'西瓜测试',1)", (tid,))
sid = c.execute("SELECT id FROM shows WHERE name='西瓜测试'").fetchone()[0]
c.execute('INSERT INTO phone_codes (tenant_id,show_id,role_name,code) VALUES (?,?,?,?)', (tid,sid,'测试玩家','MELON00001'))
c.commit()
A.app.testing = True
player = A.app.test_client()
assert player.get('/p/MELON00001').status_code == 302
assert '合成大西瓜' in player.get('/p/me/games').get_data(as_text=True)
page = player.get('/p/me/games/watermelon').get_data(as_text=True)
assert 'phone-watermelon.js' in page and '按住顶部水果' in page
assert 'id="wmAim"' not in page and 'id="wmDrop"' not in page
with player.session_transaction() as session:
    csrf = session['phone_csrf']
headers = {'X-CSRF': csrf}
assert not player.post('/p/me/games/watermelon/score',json={'score':4}).get_json()['ok']
assert player.post('/p/me/games/watermelon/restart',headers=headers).get_json()['ok']
with player.session_transaction() as session:
    session['game_start_watermelon'] = time.time() - 10
result = player.post('/p/me/games/watermelon/score',json={'score':121},headers=headers).get_json()
assert result['ok'] and result['new_best'] and result['best'] == 121 and result['rank'] == 1
with player.session_transaction() as session:
    session['game_start_watermelon'] = time.time() - 10
result = player.post('/p/me/games/watermelon/score',json={'score':4},headers=headers).get_json()
assert result['ok'] and not result['new_best'] and result['best'] == 121
assert not player.post('/p/me/games/watermelon/score',json={'score':99999999},headers=headers).get_json()['ok']
assert c.execute("SELECT score FROM game_scores WHERE game='watermelon'").fetchone()[0] == 121
assert c.execute("SELECT COUNT(*) FROM game_scores WHERE game='2048'").fetchone()[0] == 0
assert A.app.test_client().get('/p/me/games/watermelon').status_code == 302
for game in ('2048','snake','whack'):
    assert player.get('/p/me/games/'+game).status_code == 200
subprocess.run(['node',str(Path(__file__).with_name('phone_watermelon_physics_test.cjs'))],check=True)
print('ALL OK')
