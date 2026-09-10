"""年龄、孕期、毒害—救治—死亡—重新入宫 的回归测试

运行：python3 -m unittest discover -s tests -v
"""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('game', ROOT / 'app.py')
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB_PATH = str(Path(self.temp.name) / 'test.db')
        game.app.config['TESTING'] = True
        game.init_db()
        self.ctx = game.app.app_context()
        self.ctx.push()
        game.run('UPDATE game_state SET day=10')
        game.run("UPDATE consorts SET status='cold'")   # NPC 全部靠边，免得干扰
        self.atk = self.player('甲', rank=5)
        self.tgt = self.player('乙', rank=4)
        self.client = game.app.test_client()
        self.login(self.atk)

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def player(self, name, rank=4):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name, 'test')).lastrowid
        return game.run('''INSERT INTO consorts(user_id,surname,given,rank,status,entered_day,rank_since_day,
                           family,personality,silver,age_months,recap_seen_day) VALUES(?,?,?,?,'normal',1,1,?,?,2000,240,9)''',
                        (uid, name, '测试', rank, next(iter(game.FAMILIES)), next(iter(game.PERSONALITIES)))).lastrowid

    def login(self, cid):
        with self.client.session_transaction() as sess:
            sess['uid'] = game.get_consort(cid)['user_id']

    def plan_poison(self):
        response = self.client.post('/intrigue/submit', data={'method': 'lethal', 'target_id': self.tgt})
        self.assertEqual(response.status_code, 302)
        it = game.q("SELECT * FROM intrigues WHERE method='lethal' ORDER BY id DESC", one=True)
        self.assertIsNotNone(it)
        return it

    def poison(self):
        it = self.plan_poison()
        with patch.object(game.random, 'random', return_value=0.0):
            self.assertEqual(game.resolve_intrigue(it)[0], 'success')

    def test_poison_treatment_death_and_rebirth(self):
        self.assertEqual(game.get_consort(self.atk)['silver'], 2000)
        self.poison()
        self.assertEqual(game.get_consort(self.atk)['silver'], 1500)
        self.assertTrue(game.is_sick(game.get_consort(self.tgt)))
        with patch.object(game.random, 'random', return_value=0.99):
            game.resolve_poison_crises(10)   # 当晚中毒，当晚不判
        self.assertNotEqual(game.get_consort(self.tgt)['status'], 'dead')
        self.login(self.tgt)
        before = game.get_consort(self.tgt)['silver']
        self.client.post(f'/treat/{self.tgt}')
        self.client.post(f'/treat/{self.tgt}')   # 重复请不重复扣钱
        self.assertEqual(game.get_consort(self.tgt)['poison_treatment'], 1)
        self.assertEqual(game.get_consort(self.tgt)['silver'], before - game.TREAT_COST)
        with patch.object(game.random, 'random', return_value=0.99):   # 0.99 > 九成，照样救不回
            game.resolve_poison_crises(11)
        dead = game.get_consort(self.tgt)
        self.assertEqual(dead['status'], 'dead')
        self.assertEqual(self.client.get('/').location, '/memorial')
        for route in ('/shop/buy/renshen', '/act/rest', '/intrigue/submit'):
            self.assertEqual(self.client.post(route).location, '/memorial')
        uid = dead['user_id']
        game.run('UPDATE users SET lethal_ready_day=99 WHERE id=?', (uid,))
        self.assertEqual(self.client.get('/memorial').status_code, 200)
        self.client.post('/rebirth')
        self.assertIsNone(game.get_consort(self.tgt)['user_id'])
        self.assertEqual(game.get_consort(self.tgt)['archived_user_id'], uid)
        form = {'surname': '新', 'given': '秀女', 'age': 18,
                'family': next(iter(game.FAMILIES)), 'personality': next(iter(game.PERSONALITIES))}
        self.client.post('/create', data=form)
        new = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        self.assertEqual(new['age_months'], 216)
        self.assertEqual(new['status'], 'xiunv')
        # 死了重建不重置毒害冷却
        self.assertEqual(game.q('SELECT lethal_ready_day FROM users WHERE id=?', (uid,), one=True)[0], 99)

    def test_untreated_odds_and_survival_protection(self):
        self.poison()
        with patch.object(game.random, 'random', return_value=0.30):   # 没请太医：0.30 < 三成五，活
            game.resolve_poison_crises(11)
        c = game.get_consort(self.tgt)
        self.assertEqual(c['status'], 'normal')
        self.assertEqual(c['poisoned_day'], 0)
        self.assertGreaterEqual(c['health'], 35)
        self.assertEqual(c['protected_until_day'], 11 + game.RESCUE_PROTECT_DAYS)
        game.run('UPDATE users SET lethal_ready_day=0')
        self.assertIsNotNone(game.lethal_block(game.get_consort(self.atk), c, 12))
        self.assertIsNone(game.lethal_block(game.get_consort(self.atk), c, 15))

    def test_death_frees_slot_and_sisters(self):
        game.run('UPDATE consorts SET rank=8 WHERE id=?', (self.tgt,))
        self.assertFalse(game.slot_free(8))
        game.run('INSERT INTO relations(a_id,b_id,sister) VALUES(?,?,1)', (self.atk, self.tgt))
        self.assertIn(self.tgt, game.sisters_of(self.atk))
        game.die(self.tgt, '测试')
        self.assertNotIn(self.tgt, game.sisters_of(self.atk))
        self.assertTrue(game.slot_free(8))
        self.assertNotIn(self.tgt, [c['id'] for c in game.intrigue_targets(game.get_consort(self.atk))])

    def test_age_and_pregnancy_two_days(self):
        game.run("UPDATE consorts SET pregnant_since=10 WHERE id=?", (self.tgt,))
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()   # 诊出喜脉当晚
            self.assertEqual(len(game.q('SELECT * FROM heirs')), 0)
            game.settle_day()   # 第二晚
            self.assertEqual(len(game.q('SELECT * FROM heirs')), 0)
            game.settle_day()   # 第三晚临盆
        self.assertEqual(len(game.q('SELECT * FROM heirs')), 1)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 0)
        self.assertEqual(game.get_consort(self.tgt)['age_months'], 258)
        self.assertEqual(game.get_consort(self.tgt)['health'], 70)   # 年龄不再扣体质
        self.assertEqual(game.age_text(258), '21岁半')

    def test_no_pregnancy_after_45(self):
        game.run("UPDATE consorts SET age_months=?, favor=5000 WHERE id=?", (45 * 12, self.tgt))
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.settle_day()
        c = game.get_consort(self.tgt)
        self.assertEqual(c['bedded_count'], 1)
        self.assertEqual(c['pregnant_since'], 0)

    def test_atomic_settlement_rolls_back(self):
        before = [tuple(c) for c in game.q('SELECT * FROM consorts ORDER BY id')]
        with patch.object(game, 'npc_schemes', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                game.settle_day()
        self.assertEqual(game.cur_day(), 10)
        self.assertEqual(before, [tuple(c) for c in game.q('SELECT * FROM consorts ORDER BY id')])
        with patch.object(game, 'add_silver', side_effect=RuntimeError('midway')):
            with self.assertRaises(RuntimeError): game.settle_day()
        self.assertEqual(game.cur_day(), 10)
        self.assertEqual(before, [tuple(c) for c in game.q('SELECT * FROM consorts ORDER BY id')])
        self.assertEqual(len(game.q('SELECT * FROM gazette')), 0)

    def test_cooldown_survives_cancel(self):
        it = self.plan_poison()
        self.client.post(f'/intrigue/cancel/{it["id"]}')
        self.assertEqual(game.get_consort(self.atk)['silver'], 2000)   # 银子退回
        game.run('UPDATE game_state SET day=11')
        self.client.post('/intrigue/submit', data={'method': 'lethal', 'target_id': self.tgt})
        self.assertEqual(len(game.q("SELECT * FROM intrigues WHERE method='lethal'")), 1)   # 冷却没重置

    def test_failed_poison_punishment_and_ally_rescue(self):
        it = self.plan_poison()
        with patch.object(game.random, 'random', side_effect=[0.99, 0.0]):
            self.assertEqual(game.resolve_intrigue(it)[0], 'caught')
        self.assertEqual(game.get_consort(self.atk)['status'], 'cold')
        self.assertEqual(game.get_consort(self.tgt)['poisoned_day'], 0)
        game.run('UPDATE consorts SET poisoned_day=10 WHERE id=?', (self.tgt,))
        ally = self.player('丙')
        self.login(ally)
        self.client.post(f'/treat/{self.tgt}')   # 没交情，请不动
        self.assertEqual(game.get_consort(self.tgt)['poison_treatment'], 0)
        game.add_affinity(ally, self.tgt, 30)
        self.client.post(f'/treat/{self.tgt}')
        self.assertEqual(game.get_consort(self.tgt)['poison_treatment'], 1)
        self.assertEqual(game.get_consort(ally)['silver'], 2000 - game.TREAT_COST)

    def test_dead_stop_aging_and_admin_cannot_revive(self):
        game.die(self.tgt, '测试')
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()
        dead = game.get_consort(self.tgt)
        self.assertEqual(dead['age_months'], 240)
        self.assertEqual(dead['silver'], 2000)
        self.assertEqual(dead['energy'], 0)
        with self.client.session_transaction() as sess: sess['admin'] = True
        self.assertEqual(self.client.get('/admin').status_code, 200)
        self.client.post(f'/admin/edit/{self.tgt}', data={'favor': 10, 'silver': 20, 'rank': 4, 'status': 'normal'})
        self.assertEqual(game.get_consort(self.tgt)['status'], 'dead')

    def test_render_pages_and_poison_alert(self):
        for route in ('/', '/intrigue', '/shop', '/social', '/ranks', '/heirs', '/memorial', '/gazette', '/letters',
                      '/place/home', '/place/jingren', '/place/garden', '/place/yangxin'):
            self.assertEqual(self.client.get(route).status_code, 200, route)
        self.poison()
        self.login(self.tgt)
        body = self.client.get('/').get_data(as_text=True)
        self.assertIn('你中毒了', body)
        self.assertIn('请太医', body)

    def test_newcomer_and_already_poisoned_guards(self):
        game.run('UPDATE consorts SET entered_day=9 WHERE id=?', (self.tgt,))
        self.client.post('/intrigue/submit', data={'method': 'lethal', 'target_id': self.tgt})
        self.assertEqual(len(game.q('SELECT * FROM intrigues')), 0)
        game.run('UPDATE consorts SET entered_day=1, poisoned_day=9 WHERE id=?', (self.tgt,))
        self.client.post('/intrigue/submit', data={'method': 'lethal', 'target_id': self.tgt})
        self.assertEqual(len(game.q('SELECT * FROM intrigues')), 0)


class EmperorTests(unittest.TestCase):
    """侍寝/召见场景、信任、口谕、昨夜宫中、书信"""
    setUp = LifecycleTests.setUp
    tearDown = LifecycleTests.tearDown
    player = LifecycleTests.player
    login = LifecycleTests.login

    def test_bed_and_audience_create_scenes_and_recap(self):
        c3 = self.player('丙')
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()
        scenes = [game.get_scene(game.get_consort(i)) for i in (self.atk, self.tgt, c3)]
        kinds = sorted((s['key'], s.get('bed')) for s in scenes if s)
        self.assertEqual(kinds, [('audience', 0), ('audience', 0), ('audience', 1)])   # 1 侍寝 + 2 召见
        st = game.state()
        self.assertTrue(game.json.loads(st['last_bed_pool']))
        # 早上先进「昨夜宫中」，看完再去定夺场景
        self.assertEqual(self.client.get('/').location, '/recap')
        body = self.client.get('/recap').get_data(as_text=True)
        self.assertIn('绿头牌', body)
        self.assertEqual(self.client.post('/recap/seen').location, '/')
        self.assertEqual(self.client.get('/').location, '/scene')
        self.assertIn('就这么办', self.client.get('/scene').get_data(as_text=True))
        game.run('UPDATE consorts SET scheme=90, virtue=90, talent=90, appearance=90 WHERE id=?', (self.atk,))
        before = game.get_consort(self.atk)
        with patch.object(game.random, 'randint', return_value=40):   # 属性和运气都顶格，哪道题都必成
            r = self.client.post('/scene', data={'opt': 2})             # 直言
        self.assertEqual(r.status_code, 200)
        after = game.get_consort(self.atk)
        self.assertGreater(after['trust'], before['trust'])
        self.assertEqual(after['pending_scene'], '')
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_scene_expires_at_next_settlement(self):
        game.start_scene(self.atk, 'garden_emperor')
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.tgt,))
        game.run("UPDATE consorts SET status='confined', status_until_day=99 WHERE id=?", (self.atk,))
        game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['pending_scene'], '')

    def test_audience_weight_favors_the_unseen(self):
        a, b = game.get_consort(self.atk), game.get_consort(self.tgt)
        game.run('UPDATE consorts SET last_audience_day=9 WHERE id=?', (self.atk,))
        game.run('UPDATE consorts SET last_audience_day=0 WHERE id=?', (self.tgt,))
        wa = game.audience_weight(game.get_consort(self.atk), 10)
        wb = game.audience_weight(game.get_consort(self.tgt), 10)
        self.assertEqual(wa, 10 + 20 * 0.3 + 1 * 4)
        self.assertEqual(wb, 10 + 20 * 0.3 + 10 * 4)

    def test_plead_in_bed_uses_trust(self):
        game.run("UPDATE consorts SET status='confined', status_until_day=15 WHERE id=?", (self.tgt,))
        game.run('INSERT INTO relations(a_id,b_id,sister) VALUES(?,?,1)', (self.atk, self.tgt))
        game.start_scene(self.atk, 'audience', prompt=0, bed=1)
        opts = game.scene_view(game.get_consort(self.atk), game.get_scene(game.get_consort(self.atk)))[2]
        self.assertTrue(opts[-1].get('plead'))
        game.run('UPDATE consorts SET trust=80 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'randint', return_value=0):   # 信任 80 + 0 ≥ 50，成
            self.client.post('/scene', data={'opt': len(opts) - 1, 'target_id': self.tgt})
        self.assertEqual(game.get_consort(self.tgt)['status_until_day'], 14)

    def test_edicts_follow_real_events(self):
        game.run("UPDATE consorts SET status='confined', status_until_day=10 WHERE id=?", (self.tgt,))
        game.run("UPDATE consorts SET entered_day=2, last_audience_day=9 WHERE id=?", (self.atk,))   # 避开入宫周年、久未见驾
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()
        e = game.q("SELECT text FROM messages WHERE consort_id=? AND kind='edict'", (self.tgt,), one=True)
        self.assertIn('可想明白了', e['text'])
        # 没发生什么的人不发口谕
        self.assertIsNone(game.q("SELECT 1 FROM messages WHERE consort_id=? AND kind='edict'", (self.atk,), one=True))

    def test_anniversary_edict_quotes_dianxuan(self):
        game.run("UPDATE consorts SET entered_day=1, dianxuan_quote='「家母常说，素净是女子本分。」' WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.tgt,))
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()   # 第 10 天夜里，入宫满十个半年 = 五年
        e = game.q("SELECT text FROM messages WHERE consort_id=? AND kind='edict'", (self.atk,), one=True)
        self.assertIn('你入宫五年了', e['text'])
        self.assertIn('素净是女子本分', e['text'])

    def test_trust_halves_rumor_and_shapes_expose(self):
        game.run('UPDATE consorts SET favor=100, trust=60 WHERE id=?', (self.tgt,))
        it = dict(id=0, method='rumor', attacker_id=self.atk, target_id=self.tgt)
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_intrigue(it)
        self.assertEqual(game.get_consort(self.tgt)['favor'], 93)   # 信任 ≥50：只折 7.5%
        a, t = game.get_consort(self.atk), game.get_consort(self.tgt)
        game.run('UPDATE consorts SET trust=20 WHERE id=?', (self.atk,))
        low = game.intrigue_success_p(game.get_consort(self.atk), t, game.INTRIGUES['expose'])
        game.run('UPDATE consorts SET trust=60 WHERE id=?', (self.atk,))
        high = game.intrigue_success_p(game.get_consort(self.atk), t, game.INTRIGUES['expose'])
        self.assertAlmostEqual(high - low, 0.2, places=5)   # 告发人信任每 +1，成功率 +0.5%

    def test_letters_and_affinity_cap(self):
        game.inv_add(self.atk, 'ruyi', 1)
        self.client.post('/letters/send', data={'to_id': self.tgt, 'body': '姐姐安好', 'silver': 30, 'item': 'ruyi'})
        self.client.post('/letters/send', data={'to_id': self.tgt, 'body': '再写一封'})
        self.assertEqual(len(game.q('SELECT * FROM letters')), 2)
        self.assertEqual(game.relation(self.atk, self.tgt)['affinity'], 17)   # 第一封 +2，玉如意 +15，第二封不加
        self.assertEqual(game.get_consort(self.tgt)['silver'], 2030)
        self.assertEqual(game.inv_qty(self.tgt, 'ruyi'), 0)                   # 玉如意送出即用掉
        self.login(self.tgt)
        body = self.client.get('/letters').get_data(as_text=True)
        self.assertIn('姐姐安好', body)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.tgt,))
        self.client.post('/letters/send', data={'to_id': self.atk, 'body': '救我', 'silver': 5})
        self.assertEqual(len(game.q('SELECT * FROM letters')), 2)             # 冷宫送不出东西
        self.client.post('/letters/send', data={'to_id': self.atk, 'body': '救我'})
        self.assertEqual(len(game.q('SELECT * FROM letters')), 3)             # 只写信可以


class MigrationTests(unittest.TestCase):
    def test_old_schema_migration_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            game.DB_PATH = str(Path(directory) / 'old.db')
            schema = (ROOT / 'schema.sql').read_text()
            fields = ('age_months', 'poisoned_day', 'poison_treatment', 'protected_until_day',
                      'death_day', 'death_reason', 'archived_user_id', 'lethal_ready_day', 'trust', 'pending_scene',
                      'recap_seen_day', 'last_audience_day', 'last_promote_day', 'dianxuan_quote', 'is_night')
            schema = '\n'.join(line for line in schema.splitlines() if not any(line.strip().startswith(f + ' ') for f in fields))
            with sqlite3.connect(game.DB_PATH) as db: db.executescript(schema)
            game.init_db()
            game.init_db()
            with sqlite3.connect(game.DB_PATH) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM consorts').fetchone()[0], len(game.NPCS))
                self.assertEqual(db.execute('SELECT age_months FROM consorts LIMIT 1').fetchone()[0], 240)


if __name__ == '__main__': unittest.main()
