"""宫人：挑人赐名、月钱与忠心、差使、小事、发落与散去

运行：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('game_maids', ROOT / 'app.py')
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


class MaidTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB_PATH = str(Path(self.temp.name) / 'test.db')
        game.app.config['TESTING'] = True
        game.MAID_CRAFT_MAX = 0      # 宫人闲时做东西是随机的，这里关掉；专门的用例在 test_maid_craft
        game.init_db()
        self.ctx = game.app.app_context()
        self.ctx.push()
        game.run('UPDATE game_state SET day=10')
        game.run("UPDATE consorts SET status='cold'")   # NPC 全部靠边，免得干扰
        self.me = self.player('甲', rank=6)
        self.other = self.player('乙', rank=4)
        self.client = game.app.test_client()
        self.login(self.me)

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def player(self, name, rank=4):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name, 'test')).lastrowid
        return game.run('''INSERT INTO consorts(user_id,surname,given,rank,status,entered_day,rank_since_day,
                           family,personality,silver,age_months,recap_seen_day,palace) VALUES(?,?,?,?,'normal',1,1,?,?,2000,240,9,?)''',
                        (uid, name, name + '儿', rank, next(iter(game.FAMILIES)), next(iter(game.PERSONALITIES)),
                         name + '宫')).lastrowid

    def login(self, cid):
        with self.client.session_transaction() as sess:
            sess['uid'] = game.get_consort(cid)['user_id']

    def maid(self, owner, name, trait='zhonghou', loyalty=60, joined=1):
        return game.run('''INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts)
                           VALUES(?,?,?,?,?,0)''', (owner, name, trait, loyalty, joined)).lastrowid

    def pick(self, name, idx=0):
        return self.client.post('/maids/pick', data={'idx': idx, 'name': name})

    def test_pick_name_rules_and_quota(self):
        self.assertEqual(self.client.get('/maids').status_code, 200)
        for bad in ('阿', 'ab', '三个字'):   # 蕴仪是皇后的名
            self.pick(bad)
        self.assertEqual(len(game.active_maids(self.me)), 0)
        self.pick('春桃')
        self.assertEqual(game.active_maids(self.me)[0]['name'], '春桃')
        # 同名不行，哪怕那个宫人已经不在了
        game.maid_leave(game.active_maids(self.me)[0]['id'], 'dead', '测试')
        self.pick('春桃')
        self.assertEqual(len(game.active_maids(self.me)), 0)
        for n in ('夏荷', '秋菊', '冬梅', '腊梅'):
            self.pick(n)
        self.assertEqual(len(game.active_maids(self.me)), 4)   # 妃位份例 4 个
        self.pick('迎春')
        self.assertEqual(len(game.active_maids(self.me)), 4)

    def test_wage_loyalty_and_trait_bounds(self):
        a = self.maid(self.me, '春桃', 'tancai', 70)
        b = self.maid(self.me, '夏荷', 'zhonghou', 41)
        game.maid_upkeep(10)
        self.assertEqual(game.get_consort(self.me)['silver'], 1998)
        self.assertEqual(game.get_maid(a)['loyalty'], 70)       # 贪财封顶 70
        self.assertEqual(game.get_maid(b)['loyalty'], 42)
        game.run("UPDATE consorts SET silver=1 WHERE id=?", (self.me,))
        game.maid_upkeep(11)
        self.assertEqual(game.get_maid(b)['loyalty'], 40)        # 发不出钱 -5，但忠厚不低于 40
        self.assertIn('月钱', game.q("SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC", (self.me,), one=True)['text'])
        game.run("UPDATE consorts SET silver=100, status='confined' WHERE id=?", (self.me,))
        game.maid_upkeep(12)
        self.assertEqual(game.get_maid(a)['loyalty'], 63)        # 禁足 -2（刚才 -5 到 65）

    def test_spy_uses_an_errand_not_energy(self):
        r = self.client.post('/act/spy', data={'target_id': self.other, 'back': 'social'})
        self.assertIsNone(game.q("SELECT 1 FROM daily_counters WHERE consort_id=? AND key='spy'", (self.me,), one=True))
        self.maid(self.me, '春桃', 'jiling')
        energy = game.get_consort(self.me)['energy']
        self.client.post('/act/spy', data={'target_id': self.other, 'back': 'social'})
        me = game.get_consort(self.me)
        self.assertEqual(me['energy'], energy)
        self.assertEqual(me['silver'], 1970)
        self.assertEqual(len(game.free_errand_maids(me)), 0)

    def test_rumor_bonus_from_gossipy_maid(self):
        atk, tgt, cfg = game.get_consort(self.me), game.get_consort(self.other), game.INTRIGUES['rumor']
        base = game.intrigue_success_p(atk, tgt, cfg)
        self.maid(self.me, '春桃', 'suizui')
        self.assertAlmostEqual(game.intrigue_success_p(atk, tgt, cfg), min(0.85, base + 0.10))

    def test_punish_kills_a_maid_and_names_the_culprit(self):
        victim = self.maid(self.other, '春桃', trait='tancai', joined=1)      # 忠厚的宫人有一半机会被保下来，这里用别的特质
        fresh = self.maid(self.other, '夏荷', trait='tancai', joined=9)       # 刚来 1 天，动不得
        self.client.post('/intrigue/submit', data={'method': 'punish', 'target_id': self.other})
        it = game.q("SELECT * FROM intrigues WHERE method='punish'", one=True)
        self.assertIsNotNone(it)
        self.assertEqual(game.get_consort(self.me)['punish_ready_day'], game.cur_day() + game.PUNISH_COOLDOWN)
        with patch.object(game.random, 'random', return_value=0.0):
            self.assertEqual(game.resolve_intrigue(it)[0], 'success')
        self.assertEqual(game.get_maid(victim)['status'], 'dead')
        self.assertEqual(game.get_maid(fresh)['status'], 'active')
        self.assertEqual(game.get_maid(fresh)['loyalty'], 55)
        note = game.q("SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC", (self.other,), one=True)['text']
        self.assertIn(game.display_name(game.get_consort(self.me)), note)
        self.assertIn('春桃', game.q("SELECT text FROM gazette ORDER BY id DESC", one=True)['text'])
        # 冷却：出手的人 PUNISH_COOLDOWN 天一次，对方宫里同样时间内也不会再被发落
        game.run("UPDATE consorts SET punish_ready_day=0 WHERE id=?", (self.me,))
        self.assertIn('没了人', game.punish_block(game.get_consort(self.me), game.get_consort(self.other), 11))
        # 位分差不够
        self.assertIn('两级', game.punish_block(game.get_consort(self.other), game.get_consort(self.me), 30))

    def test_death_scatters_maids_and_memorial_lists_them(self):
        m = self.maid(self.me, '春桃')
        game.die(self.me, '测试')
        self.assertEqual(game.get_maid(m)['status'], 'gone')
        page = self.client.get('/memorial').get_data(as_text=True)
        self.assertIn('春桃', page)

    def test_small_event_flow(self):
        m = self.maid(self.me, '春桃', loyalty=60)
        game.run("UPDATE consorts SET maid_event=? WHERE id=?",
                 (json.dumps(dict(key='mother_ill', maid=m, day=10)), self.me))
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('老娘病了', page)
        self.client.post('/maids/event', data={'opt': 0})
        self.assertEqual(game.get_consort(self.me)['silver'], 1990)
        self.assertEqual(game.get_maid(m)['loyalty'], 70)
        self.assertIn('mother_ill', game.get_maid(m)['seen_events'])
        self.assertEqual(game.get_consort(self.me)['maid_event'], '')
        # 同一件事同一个宫人不会再来
        for _ in range(30):
            game.run("UPDATE consorts SET maid_event='' WHERE id=?", (self.me,))
            game.run("DELETE FROM daily_counters WHERE key='maid_event_roll'")
            with patch.object(game.random, 'random', return_value=0.0):
                game.roll_maid_event(game.get_consort(self.me))
            ev = json.loads(game.get_consort(self.me)['maid_event'] or '{}')
            self.assertNotEqual(ev.get('key'), 'mother_ill')

    def test_gossip_reports_what_someone_did_today(self):
        m = game.get_maid(self.maid(self.me, '春桃'))
        game.daily_inc(self.other, 'greet')
        self.assertIn('请了安', game.maid_gossip(game.get_consort(self.me), m))

    def test_nightly_settlement_runs_with_maids(self):
        self.maid(self.me, '春桃')
        game.settle_day()
        self.assertEqual(game.get_maid(1)['loyalty'], 61)

    def test_admin_can_rename(self):
        self.maid(self.me, '春桃')
        with self.client.session_transaction() as sess:
            sess['admin'] = True
        self.assertEqual(self.client.get('/admin').status_code, 200)
        self.client.post('/admin/maid_rename', data={'old': '春桃', 'new': '秋月'})
        self.assertEqual(game.get_maid(1)['name'], '秋月')


if __name__ == '__main__':
    unittest.main()
