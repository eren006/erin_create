"""使计一提交就判定（实时结算）；截宠仍等翻牌轮"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class IntrigueRealtimeTests(unittest.TestCase):
    def setUp(self):
        fixtures.LifecycleTests.setUp(self)
        game.INTRIGUE_REALTIME = True
        game.run("UPDATE consorts SET entered_day=1 WHERE id IN (?,?)", (self.atk, self.tgt))

    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def submit(self, method='rumor', **extra):
        return self.client.post('/intrigue/submit', data=dict(method=method, target_id=self.tgt, **extra), follow_redirects=True)

    def row(self, method='rumor'):
        return game.q("SELECT * FROM intrigues WHERE method=? ORDER BY id DESC", (method,), one=True)

    def test_rumor_is_decided_the_moment_it_is_submitted(self):
        with patch.object(game.random, 'random', return_value=0.0):
            page = self.submit().get_data(as_text=True)
        it = self.row()
        self.assertEqual((it['status'], it['result']), ('done', 'success'))
        self.assertIn('得手了', page)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%流言%'", (self.tgt,), one=True), '被害的人立刻收到通知')
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '流言四起：%'", one=True))

    def test_successful_harm_lowers_mood_once_and_clamps_at_zero(self):
        for initial in (50, 5):
            with self.subTest(initial=initial):
                game.run("DELETE FROM daily_counters")
                game.run("DELETE FROM intrigues")
                game.run("UPDATE consorts SET mood=? WHERE id=?", (initial, self.tgt))
                with patch.object(game.random, 'random', return_value=0.0):
                    self.submit()
                it = self.row()
                self.assertEqual(it['result'], 'success')
                expected = max(0, initial - game.MOOD_HARM_LOSS)
                self.assertEqual(game.get_consort(self.tgt)['mood'], expected)
                game.resolve_intrigue(it)
                self.assertEqual(game.get_consort(self.tgt)['mood'], expected)

    def test_failure_and_caught_show_up_at_once_too(self):
        before = game.get_consort(self.tgt)['mood']
        with patch.object(game.random, 'random', side_effect=[0.99, 0.0] + [0.5] * 30):
            page = self.submit().get_data(as_text=True)
        self.assertEqual(self.row()['result'], 'caught')
        self.assertEqual(game.get_consort(self.tgt)['mood'], before)
        self.assertIn('被当场拿住', page)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%败露%'", (self.atk,), one=True))

    def test_steal_still_waits_for_the_bedding_round(self):
        page = self.submit('steal').get_data(as_text=True)
        it = self.row('steal')
        self.assertEqual(it['status'], 'pending')
        self.assertIn('截宠要等', page)

    def test_done_intrigues_still_count_against_the_daily_target_cap(self):
        c3, c4 = self.player('丙'), self.player('丁')
        game.run("UPDATE consorts SET entered_day=1")
        for who in (self.atk, c3):
            self.login(who)
            game.run("DELETE FROM daily_counters")
            with patch.object(game.random, 'random', return_value=0.99):
                self.client.post('/intrigue/submit', data=dict(method='rumor', target_id=self.tgt))
        self.assertEqual(len(game.q("SELECT * FROM intrigues WHERE target_id=? AND status='done'", (self.tgt,))), game.INTRIGUE_TARGET_DAILY_MAX)
        self.login(c4)
        self.client.post('/intrigue/submit', data=dict(method='rumor', target_id=self.tgt))
        self.assertEqual(len(game.q("SELECT * FROM intrigues WHERE attacker_id=?", (c4,))), 0, '今天盯着她的人已经够多了')

    def test_conspiracy_is_decided_when_the_partner_says_yes(self):
        pal = self.player('戊')
        game.run("UPDATE consorts SET energy=8, entered_day=1 WHERE id IN (?,?)", (self.atk, pal))
        game.add_affinity(self.atk, pal, 70)
        self.client.post('/intrigue/submit', data=dict(method='rumor', target_id=self.tgt, partner_id=pal))
        iv = self.row()
        self.assertEqual(iv['status'], 'invited')
        self.login(pal)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post(f"/intrigue/conspire/{iv['id']}/accept")
        self.assertEqual(self.row()['status'], 'done')
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%合谋%成了%'", (pal,), one=True))

    def test_managed_consort_intrigue_is_decided_at_once(self):
        cid = game.spawn_managed_consort('夏', '知意')
        game.run("UPDATE consorts SET energy=8, silver=1000 WHERE id=?", (cid,))
        with patch.object(game.random, 'choices', side_effect=lambda pop, weights=None, k=1: [pop[0]]), \
             patch.object(game.random, 'random', return_value=0.0):
            self.assertTrue(game.bot_intrigue(game.get_consort(cid)))
        it = game.q("SELECT * FROM intrigues WHERE attacker_id=?", (cid,), one=True)
        self.assertEqual((it['status'], it['result']), ('done', 'success'))

    def test_switch_off_restores_waiting_for_settlement(self):
        game.INTRIGUE_REALTIME = False
        self.submit()
        self.assertEqual(self.row()['status'], 'pending')
        with patch.object(game.random, 'random', return_value=0.0):
            game.settle_day(bed_key='x')
        self.assertEqual(self.row()['status'], 'done')

    def test_settlement_does_not_resolve_twice(self):
        with patch.object(game.random, 'random', return_value=0.0):
            self.submit()
            favor = game.get_consort(self.tgt)['favor']
            before = len(game.q("SELECT * FROM gazette WHERE text LIKE '流言四起：%'"))
            game.settle_day(bed_key='x')
        self.assertEqual(len(game.q("SELECT * FROM gazette WHERE text LIKE '流言四起：%'")), before)

    def test_drug_is_decided_at_once_too(self):
        game.inv_add(self.atk, 'yanzhi')
        game.run("UPDATE consorts SET entered_day=1, scheme=100 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET scheme=1, trust=0, virtue=10 WHERE id=?", (self.tgt,))
        before = game.get_consort(self.tgt)['appearance']
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/intrigue/submit', data=dict(method='drug', target_id=self.tgt, drug='yanzhi', agent_maid_id=0))
        it = self.row('drug')
        self.assertIsNotNone(it)
        self.assertEqual(it['status'], 'done')
        self.assertEqual(it['result'], 'success')
        self.assertLess(game.get_consort(self.tgt)['appearance'], before, '药效当场生效')


if __name__ == '__main__':
    unittest.main()
