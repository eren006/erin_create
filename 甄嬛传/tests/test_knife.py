"""借华妃的刀（设计文档九点二十二节）

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle

game = test_lifecycle.game


class KnifeContentTests(unittest.TestCase):
    def test_debt_texts_format(self):
        names = dict(t='乙贵人', x='丙常在', m='春桃', p='甲嫔')
        kinds = set()
        for key, d in game.KNIFE_DEBTS.items():
            kinds.add(d['kind'])
            for f in ('ask', 'ok', 'broken'):
                d[f].format(**names)
            self.assertIn(d['days'], (1, 2, 3), key)
        self.assertEqual(kinds, {'silver', 'hobby', 'nogreet', 'rumor', 'seek', 'maid'})
        for lines in game.KNIFE_ASK.values():
            for l in lines: l.format(**names)
        for l in list(game.KNIFE_HIT_LINES.values()) + game.KNIFE_BETRAY + [game.KNIFE_COVER]:
            l.format(**names)

    def test_betray_chance_range(self):
        self.assertAlmostEqual(game.knife_betray_p(30), 0.50)
        self.assertAlmostEqual(game.knife_betray_p(45), 0.35)
        self.assertAlmostEqual(game.knife_betray_p(59), 0.21)
        self.assertAlmostEqual(game.knife_betray_p(80), 0.21)


class KnifeTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    tearDown = test_lifecycle.LifecycleTests.tearDown
    player = test_lifecycle.LifecycleTests.player
    login = test_lifecycle.LifecycleTests.login

    def befriend(self, aff=65):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key IN ('huafei','huanghou')")
        hf = game.npc_row('huafei')
        game.add_affinity(self.atk, hf['id'], aff - game.bond(self.atk, 'huafei'))
        return hf

    def borrow(self, roll=0.99):
        with patch.object(game.random, 'random', return_value=roll):
            return self.client.post('/knife/borrow', data={'target_id': self.tgt})

    def debt(self):
        return game.q('SELECT * FROM knife_debts WHERE consort_id=? ORDER BY id DESC', (self.atk,), one=True)

    def resolve(self, result):
        """把华妃那条阴谋直接判成某个结果，再跑一遍借刀的夜间结算"""
        d = self.debt()
        game.run("UPDATE intrigues SET status='done', result=? WHERE id=?", (result, d['intrigue_id']))
        game.knife_hits_tick(10)
        return self.debt()

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_needs_intimate(self):
        self.befriend(50)
        self.borrow()
        self.assertIsNone(self.debt())

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_borrow_costs_and_queues_intrigue(self):
        hf = self.befriend()
        before = game.get_consort(self.atk)['silver']
        self.borrow()
        d = self.debt()
        self.assertEqual(d['status'], 'hit')
        self.assertEqual(game.get_consort(self.atk)['silver'], before - game.KNIFE_COST)
        self.assertEqual(game.bond(self.atk, 'huafei'), game.KNIFE_AFTER_BOND)
        it = game.q('SELECT * FROM intrigues WHERE id=?', (d['intrigue_id'],), one=True)
        self.assertEqual((it['attacker_id'], it['target_id'], it['status']), (hf['id'], self.tgt, 'pending'))
        self.assertEqual(it['method'], 'frame')                     # 乙是贵人（rank 4），栽赃
        self.assertEqual(game.daily_count(self.atk, 'npc_visit'), 1)
        self.assertTrue(game.knife_block_reason(game.get_consort(self.atk)))   # 当天不能再借

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_refuse_keeps_silver(self):
        self.befriend()
        before = game.get_consort(self.atk)['silver']
        self.borrow(roll=0.0)
        self.assertIsNone(self.debt())
        self.assertEqual(game.get_consort(self.atk)['silver'], before)
        self.assertEqual(game.daily_count(self.atk, 'npc_visit'), 1)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_success_creates_debt_and_silver_payment(self):
        self.befriend()
        self.borrow()
        with patch.object(game.random, 'choice', side_effect=lambda seq: 'silver80' if 'silver80' in seq else seq[0]):
            d = self.resolve('success')
        self.assertEqual((d['status'], d['debt'], d['start_day'], d['due_day']), ('owed', 'silver80', 11, 12))
        before = game.get_consort(self.atk)['silver']
        self.client.post('/knife/pay')
        self.assertEqual(self.debt()['status'], 'paid')
        self.assertEqual(game.get_consort(self.atk)['silver'], before - 80)
        self.assertEqual(game.bond(self.atk, 'huafei'), game.KNIFE_AFTER_BOND)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_overdue_breaks_and_huafei_turns(self):
        self.befriend()
        self.borrow()
        with patch.object(game.random, 'choice', side_effect=lambda seq: 'silver120' if 'silver120' in seq else seq[0]):
            self.resolve('success')
        game.knife_debts_tick(10)
        self.assertEqual(self.debt()['status'], 'owed')
        game.knife_debts_tick(11)
        self.assertEqual(self.debt()['status'], 'broken')
        self.assertEqual(game.bond(self.atk, 'huafei'), game.KNIFE_BROKEN_BOND)
        game.run('UPDATE consorts SET favor=0 WHERE id=?', (self.atk,))
        self.assertEqual(game.huafei_likely_target(exclude_id=self.tgt)['id'], self.atk)   # 记恨上了

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_nogreet_debt(self):
        self.befriend()
        self.borrow()
        with patch.object(game.random, 'choice', side_effect=lambda seq: 'nogreet' if 'nogreet' in seq else seq[0]):
            self.resolve('success')
        game.run('UPDATE consorts SET greet_day=11 WHERE id=?', (self.atk,))
        game.knife_debts_tick(11)
        self.assertEqual(self.debt()['status'], 'broken')

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_rumor_and_seek_debts_auto_complete(self):
        c3 = self.player('丙', rank=3)
        self.befriend()
        self.borrow()
        with patch.object(game.random, 'choice', side_effect=lambda seq: 'rumor' if 'rumor' in seq else seq[0]):
            d = self.resolve('success')
        self.assertEqual(d['x_id'], c3)
        game.run("INSERT INTO intrigues (day, attacker_id, target_id, method, created_ts) VALUES (11, ?, ?, 'rumor', 0)", (self.atk, c3))
        game.knife_debts_tick(11)
        self.assertEqual(self.debt()['status'], 'paid')

    def test_maid_debt_only_when_you_have_maids(self):
        c = game.get_consort(self.atk)
        for _ in range(30):
            key, _, _ = game.knife_pick_debt(c, self.tgt)
            self.assertNotEqual(game.KNIFE_DEBTS[key]['kind'], 'maid')
            self.assertNotEqual(game.KNIFE_DEBTS[key]['kind'], 'hobby')

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_caught_cover_or_betray(self):
        self.befriend()
        self.borrow()
        with patch.object(game.random, 'random', return_value=0.99):
            d = self.resolve('caught')
        self.assertEqual(d['status'], 'covered')
        game.run('DELETE FROM knife_debts'); game.run("DELETE FROM daily_counters")
        self.befriend()
        self.borrow()
        trust = game.get_consort(self.atk)['trust']
        with patch.object(game.random, 'random', return_value=0.0):
            d = self.resolve('caught')
        self.assertEqual(d['status'], 'exposed')
        self.assertEqual(game.get_consort(self.atk)['trust'], max(0, trust - 15))
        self.assertEqual(game.get_consort(self.atk)['status'], 'confined')        # 栽赃败露：禁足
        msg = game.q("SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC", (self.tgt,), one=True)['text']
        self.assertIn(game.display_name(game.get_consort(self.atk)), msg)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_fizzle_no_debt(self):
        self.befriend()
        self.borrow()
        self.assertEqual(self.resolve('fizzle')['status'], 'void')
        self.assertFalse(game.knife_open_debt(self.atk))

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_full_night_and_pages(self):
        self.befriend()
        self.assertEqual(self.client.get('/social').status_code, 200)
        self.borrow()
        game.settle_day()
        self.assertIn(self.debt()['status'], ('owed', 'void', 'covered', 'exposed'))
        self.assertEqual(self.client.get('/social').status_code, 200)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_every_debt_renders(self):
        self.befriend()
        game.run("INSERT INTO hobby_items (kind, style, maker_id, holder_id, created_day) VALUES ('painting','山水',?,?,5)", (self.atk, self.atk))
        for key in game.KNIFE_DEBTS:
            game.run('DELETE FROM knife_debts')
            game.run("""INSERT INTO knife_debts (consort_id, victim_id, day, status, debt, x_id, start_day, due_day)
                        VALUES (?,?,10,'owed',?,?,11,12)""", (self.atk, self.tgt, key, self.tgt))
            r = self.client.get('/social')
            self.assertEqual(r.status_code, 200, key)
            self.assertIn('欠华妃的人情', r.get_data(as_text=True), key)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_huanghou_warns_huafei_friends(self):
        self.befriend(35)
        game.run('UPDATE consorts SET scheme=90 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'randint', return_value=40):
            r = self.client.post('/npc/visit', data={'npc': 'huanghou', 'opt': 1}, follow_redirects=True)
        body = r.get_data(as_text=True)
        self.assertTrue(any(w[:12] in body for w in game.HUANGHOU_WARN))


if __name__ == '__main__':
    unittest.main()
