"""2026-10-07：妃位以上养皇子/嫔位以上养公主、催产丹、避孕、梳洗容貌上限 65"""
import time
import unittest
import test_heirs

game = test_heirs.game


class RaiseRankMiscTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def test_min_rank_by_gender(self):
        self.assertEqual(game.raise_min_rank({'gender': '皇子'}), 6)
        self.assertEqual(game.raise_min_rank({'gender': '公主'}), 5)

    def test_pin_cannot_entrust_target_for_son(self):
        pin = self.player('嫔', rank=5)
        self.assertNotIn(pin, [t['id'] for t in game.entrust_candidates(game.get_consort(self.tgt), 6)])
        game.add_affinity(self.tgt, pin, 60)
        self.assertIn(pin, [t['id'] for t in game.entrust_candidates(game.get_consort(self.tgt), 5)])

    def test_cuisheng_shortens_pregnancy(self):
        game.run('UPDATE consorts SET pregnant_since=?, pregnancy_started_ts=? WHERE id=?', (game.cur_day(), time.time(), self.atk))
        game.inv_add(self.atk, 'cuisheng', 1)
        self.login(self.atk)
        before = game.get_consort(self.atk)['pregnancy_started_ts']
        self.client.post('/shop/use/cuisheng')
        self.assertAlmostEqual(before - game.get_consort(self.atk)['pregnancy_started_ts'], 6 * 3600, delta=1)

    def test_contraception_needs_two_births(self):
        self.login(self.atk)
        self.client.post('/contraception')
        self.assertEqual(game.get_consort(self.atk)['contraception'], 0)
        self.heir(self.atk); self.heir(self.atk)
        self.client.post('/contraception')
        c = game.get_consort(self.atk)
        self.assertEqual(c['contraception'], 1)
        self.assertEqual(game.pregnancy_chance(c), 0.0)
        game.run('UPDATE consorts SET pregnancy_misses=11 WHERE id=?', (self.atk,))
        self.assertEqual(game.pregnancy_chance(game.get_consort(self.atk)), 0.0, '避孕时保底也不生效')

    def test_own_grooming_caps_at_65(self):
        game.run('UPDATE consorts SET energy=8, silver=500, appearance=64 WHERE id=?', (self.atk,))
        c = game.get_consort(self.atk)
        game.do_groom(c, game.action_config(c, 'groom'))
        self.assertEqual(game.get_consort(self.atk)['appearance'], 65)
        c = game.get_consort(self.atk)
        game.do_groom(c, game.action_config(c, 'groom'))
        self.assertEqual(game.get_consort(self.atk)['appearance'], 65)

    def test_influence_decays_only_above_rank_requirement(self):
        need = game.PROMOTE_INFLUENCE.get(game.get_consort(self.atk)['rank'], 0)
        game.run('UPDATE consorts SET influence=?, entered_day=-100 WHERE id=?', (need + 5, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need + 4)
        game.run('UPDATE consorts SET influence=? WHERE id=?', (need, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need)
        game.run("UPDATE consorts SET influence=?, status='cold' WHERE id=?", (need + 5, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need + 5)

    def test_new_arts_and_no_repeat_perform(self):
        self.assertIn('琵琶', game.ARTS); self.assertIn('笛子', game.ARTS)
        for a in game.ARTS: self.assertIn(a, game.BANQUET_PIECES); self.assertIn(a, game.BANQUET_PROPS)
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.login(self.atk)
        self.client.post('/act/perform', data=dict(art='琵琶'))
        self.assertEqual(game.get_consort(self.atk)['last_perform_art'], '琵琶')
        game.run('DELETE FROM daily_counters')
        energy = game.get_consort(self.atk)['energy']
        self.client.post('/act/perform', data=dict(art='琵琶'))
        self.assertEqual(game.get_consort(self.atk)['energy'], energy, '同一样才艺连着献被拒绝，不扣精力')
        self.client.post('/act/perform', data=dict(art='笛子'))
        self.assertEqual(game.get_consort(self.atk)['last_perform_art'], '笛子')


if __name__ == '__main__':
    unittest.main()
