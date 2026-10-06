"""两人合谋使计：一人发起、另一人确认；加成、费用、败露同罚、门槛"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class ConspiracyTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def make_partner(self, affinity=70):
        self.pal = self.player('丙', rank=5)
        game.add_affinity(self.atk, self.pal, affinity)
        game.run('UPDATE consorts SET energy=8 WHERE id IN (?,?)', (self.atk, self.pal))
        return self.pal

    def invite(self, method='rumor'):
        self.login(self.atk)
        self.client.post('/intrigue/submit', data={'method': method, 'target_id': self.tgt, 'partner_id': self.pal})
        return game.q("SELECT * FROM intrigues WHERE method=? ORDER BY id DESC", (method,), one=True)

    def accept(self, iid, action='accept'):
        self.login(self.pal)
        self.client.post(f'/intrigue/conspire/{iid}/{action}')
        return game.q("SELECT * FROM intrigues WHERE id=?", (iid,), one=True)

    def silver(self, cid): return game.get_consort(cid)['silver']

    def test_invite_costs_nothing_until_accepted(self):
        self.make_partner()
        a0, p0 = self.silver(self.atk), self.silver(self.pal)
        it = self.invite()
        self.assertIsNotNone(it)
        self.assertEqual(it['status'], 'invited')
        self.assertEqual(it['partner_id'], self.pal)
        self.assertEqual((self.silver(self.atk), self.silver(self.pal)), (a0, p0))
        self.login(self.atk)
        self.assertEqual(game.daily_count(self.atk, 'intrigue'), 0)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%邀你合谋%'", (self.pal,), one=True))

    def test_affinity_must_exceed_60(self):
        self.make_partner(affinity=60)
        self.assertIsNone(self.invite())
        game.add_affinity(self.atk, self.pal, 1)
        self.assertIsNotNone(self.invite())

    def test_accept_charges_both_one_and_a_half_times(self):
        self.make_partner()
        a0, p0 = self.silver(self.atk), self.silver(self.pal)
        e0 = game.get_consort(self.atk)['energy']
        it = self.accept(self.invite()['id'])
        cost = game.conspire_cost(game.INTRIGUES['rumor'])
        self.assertEqual(cost, 45)
        self.assertEqual(it['status'], 'pending')
        self.assertEqual((self.silver(self.atk), self.silver(self.pal)), (a0 - cost, p0 - cost))
        self.assertEqual(it['partner_silver'], cost)
        self.assertEqual(game.daily_count(self.atk, 'intrigue'), 1)
        self.assertEqual(game.daily_count(self.pal, 'intrigue'), 1)

    def test_decline_and_cancel_cost_nothing(self):
        self.make_partner()
        a0, p0 = self.silver(self.atk), self.silver(self.pal)
        it = self.accept(self.invite()['id'], 'decline')
        self.assertEqual(it['status'], 'declined')
        self.login(self.atk)
        it2 = self.invite()
        self.client.post(f"/intrigue/cancel/{it2['id']}")
        self.assertEqual(game.q("SELECT status FROM intrigues WHERE id=?", (it2['id'],), one=True)['status'], 'cancelled')
        self.assertEqual((self.silver(self.atk), self.silver(self.pal)), (a0, p0))

    def test_invite_expires_after_a_day(self):
        self.make_partner()
        it = self.invite()
        game.run("UPDATE intrigues SET created_ts=? WHERE id=?", (game.now_ts() - game.CONSPIRE_INVITE_SECONDS - 5, it['id']))
        after = self.accept(it['id'])
        self.assertEqual(after['status'], 'expired')

    def test_cancel_after_accept_refunds_both(self):
        self.make_partner()
        a0, p0 = self.silver(self.atk), self.silver(self.pal)
        it = self.accept(self.invite()['id'])
        self.login(self.atk)
        self.client.post(f"/intrigue/cancel/{it['id']}")
        self.assertEqual((self.silver(self.atk), self.silver(self.pal)), (a0, p0))

    def test_drug_cannot_conspire(self):
        self.make_partner()
        game.inv_add(self.atk, 'lihun')
        self.login(self.atk)
        self.client.post('/intrigue/submit', data={'method': 'drug', 'drug': 'lihun', 'target_id': self.tgt, 'partner_id': self.pal})
        row = game.q("SELECT * FROM intrigues WHERE method='drug' AND partner_id=?", (self.pal,), one=True)
        self.assertIsNone(row)

    def test_partner_already_busy_is_rejected_at_invite(self):
        self.make_partner()
        game.daily_inc(self.pal, 'intrigue')
        self.assertIsNone(self.invite())

    def test_bonus_lets_a_borderline_roll_succeed_and_splits_influence(self):
        self.make_partner()
        it = self.accept(self.invite()['id'])
        atk, tgt = game.get_consort(self.atk), game.get_consort(self.tgt)
        p = game.intrigue_success_p(atk, tgt, game.INTRIGUES['rumor'])
        self.assertLessEqual(p + 0.2, 0.85)
        i_a, i_p = atk['influence'], game.get_consort(self.pal)['influence']
        with patch.object(game.random, 'random', return_value=p + 0.1):
            self.assertEqual(game.resolve_intrigue(it)[0], 'success')
        full = game.INFLUENCE_GAINS['rumor']
        gain_a = game.get_consort(self.atk)['influence'] - i_a
        gain_p = game.get_consort(self.pal)['influence'] - i_p
        self.assertEqual(gain_a, max(1, round(full * 0.5)))
        self.assertEqual(gain_p, gain_a)

    def test_same_roll_fails_without_partner(self):
        self.login(self.atk)
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='rumor'", one=True)
        p = game.intrigue_success_p(game.get_consort(self.atk), game.get_consort(self.tgt), game.INTRIGUES['rumor'])
        with patch.object(game.random, 'random', return_value=p + 0.1):
            self.assertNotEqual(game.resolve_intrigue(it)[0], 'success')

    def test_caught_punishes_both(self):
        self.make_partner()
        it = self.accept(self.invite()['id'])
        v_a, v_p = game.get_consort(self.atk)['virtue'], game.get_consort(self.pal)['virtue']
        with patch.object(game.random, 'random', side_effect=[0.99, 0.0] + [0.5] * 30):
            self.assertEqual(game.resolve_intrigue(it)[0], 'caught')
        self.assertEqual(game.get_consort(self.atk)['virtue'], v_a - 5)
        self.assertEqual(game.get_consort(self.pal)['virtue'], v_p - 5)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%败露%'", (self.pal,), one=True))

    def test_affinity_dropped_before_resolve_falls_back_to_single(self):
        self.make_partner()
        it = self.accept(self.invite()['id'])
        game.add_affinity(self.atk, self.pal, -40)
        p = game.intrigue_success_p(game.get_consort(self.atk), game.get_consort(self.tgt), game.INTRIGUES['rumor'])
        with patch.object(game.random, 'random', return_value=p + 0.1):
            self.assertNotEqual(game.resolve_intrigue(it)[0], 'success')
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%合谋临阵出了岔子%'", (self.pal,), one=True))

    def test_intrigue_page_renders_for_both_sides(self):
        self.make_partner()
        self.login(self.atk)
        html = self.client.get('/intrigue').get_data(as_text=True)
        self.assertIn('合谋人', html)
        it = self.invite()
        self.login(self.pal)
        html = self.client.get('/intrigue').get_data(as_text=True)
        self.assertIn('收到的合谋邀请', html)
        self.accept(it['id'])
        for who in (self.atk, self.pal):
            self.login(who)
            html = self.client.get('/intrigue').get_data(as_text=True)
            self.assertIn('合谋', html)
            self.assertIn('等今夜', html)


if __name__ == '__main__':
    unittest.main()
