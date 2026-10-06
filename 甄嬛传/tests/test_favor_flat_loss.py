"""扣圣宠一律扣定额，不按比例"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class FlatFavorLossTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def favor(self, cid): return game.get_consort(cid)['favor']

    def test_cut_is_a_fixed_amount_whatever_the_favor(self):
        for start in (30, 100, 300, 800):
            game.run('UPDATE consorts SET favor=? WHERE id=?', (start, self.tgt))
            self.assertEqual(game.cut_favor(self.tgt, 18), min(18, start))
            self.assertEqual(self.favor(self.tgt), start - min(18, start))

    def test_never_below_zero_and_naive_halves(self):
        game.run('UPDATE consorts SET favor=5 WHERE id=?', (self.tgt,))
        self.assertEqual(game.cut_favor(self.tgt, 18), 5)
        self.assertEqual(self.favor(self.tgt), 0)
        game.run("UPDATE consorts SET favor=100, personality='naive' WHERE id=?", (self.tgt,))
        self.assertEqual(game.cut_favor(self.tgt, 18), 9)

    def test_rumor_costs_the_same_for_a_poor_and_a_rich_target(self):
        for favor in (60, 400):
            game.run("DELETE FROM intrigues")
            game.run('UPDATE consorts SET favor=?, trust=10 WHERE id=?', (favor, self.tgt))
            it = dict(id=0, method='rumor', attacker_id=self.atk, target_id=self.tgt)
            with patch.object(game.random, 'random', return_value=0.0):
                game.resolve_intrigue(it)
            self.assertEqual(self.favor(self.tgt), favor - game.FAVOR_LOSS['rumor'])

    def test_frame_and_caught_penalties_are_flat(self):
        game.run('UPDATE consorts SET favor=300, trust=10 WHERE id=?', (self.tgt,))
        it = dict(id=0, method='frame', attacker_id=self.atk, target_id=self.tgt)
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_intrigue(it)
        self.assertEqual(self.favor(self.tgt), 300 - game.FAVOR_LOSS['frame'])
        game.run('UPDATE consorts SET favor=300, trust=40 WHERE id=?', (self.atk,))
        it = dict(id=0, method='rumor', attacker_id=self.atk, target_id=self.tgt)
        with patch.object(game.random, 'random', side_effect=[0.99, 0.0] + [0.5] * 30):
            self.assertEqual(game.resolve_intrigue(it)[0], 'caught')
        self.assertEqual(self.favor(self.atk), 300 - game.FAVOR_LOSS['caught_rumor'])

    def test_no_ratio_wording_left_in_penalty_texts(self):
        import re
        for k, v in game.INTRIGUES.items():
            self.assertFalse(re.search(r'圣宠[^，。]*\d+%', v['desc']), k)
        for k, v in game.SECRETS.items():
            self.assertNotIn('%', v['penalty'] + v['confess'], k)
            self.assertNotIn('折半', v['penalty'])

    def test_secret_penalties_are_flat(self):
        game.run("UPDATE consorts SET secret='lover', favor=300 WHERE id=?", (self.tgt,))
        game.apply_secret_penalty(self.tgt, confessed=False)
        self.assertEqual(self.favor(self.tgt), 300 - game.FAVOR_LOSS['secret_lover'])
        game.run("UPDATE consorts SET secret='lover', favor=300 WHERE id=?", (self.tgt,))
        game.apply_secret_penalty(self.tgt, confessed=True)
        self.assertEqual(self.favor(self.tgt), 300 - game.FAVOR_LOSS['secret_lover_confess'])


if __name__ == '__main__':
    unittest.main()
