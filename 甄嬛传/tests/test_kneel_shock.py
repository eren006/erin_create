"""罚跪：扣体质；孕妇小概率动胎气（满 18 小时前小产、满 18 小时后提前临盆），害人的一方禁足并扣圣宠。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class KneelShockTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def pregnant(self, hours):
        game.run("UPDATE consorts SET pregnant_since=9, pregnancy_started_ts=?, health=70, favor=100 WHERE id=?", (game.time.time() - hours * 3600, self.tgt))
        game.run("UPDATE consorts SET favor=100, status='normal' WHERE id=?", (self.atk,))

    def shock(self, roll=0.0):
        with patch.object(game.random, 'random', return_value=roll):
            return game.kneel_shock(game.get_consort(self.tgt), game.get_consort(self.atk))

    def test_not_pregnant_only_loses_health(self):
        game.run("UPDATE consorts SET health=70, pregnant_since=0 WHERE id=?", (self.tgt,))
        self.assertEqual(self.shock(), '')
        self.assertEqual(game.get_consort(self.tgt)['health'], 70 - game.KNEEL_HEALTH_LOSS)
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_early_pregnancy_miscarries_and_punisher_is_blamed(self):
        self.pregnant(2)
        self.assertIn('小产', self.shock())
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 0)
        a = game.get_consort(self.atk)
        self.assertEqual(a['status'], 'confined')
        self.assertEqual(a['favor'], 100 - game.KNEEL_HARM_FAVOR_LOSS)

    def test_late_pregnancy_forces_preterm_and_punisher_is_blamed(self):
        self.pregnant(20)
        self.assertIn('提前临盆', self.shock())
        self.assertTrue(game.prenatal_state(game.get_consort(self.tgt)).get('force_preterm'))
        self.assertEqual(game.get_consort(self.atk)['status'], 'confined')
        game.resolve_births(10, False)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 0)      # 这一轮就生了
        self.assertEqual(len(game.q('SELECT * FROM heirs WHERE mother_id=?', (self.tgt,))) +
                         len(game.q('SELECT * FROM birth_losses WHERE mother_id=?', (self.tgt,))) >= 1, True)

    def test_antai_saves_the_baby_and_nobody_is_blamed(self):
        self.pregnant(2)
        game.inv_add(self.tgt, 'antai')
        self.assertIn('安胎药', self.shock())
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 9)
        self.assertEqual(game.inv_qty(self.tgt, 'antai'), 0)
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_low_roll_miss_does_nothing(self):
        self.pregnant(2)
        self.assertEqual(self.shock(0.99), '')
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 9)


if __name__ == '__main__':
    unittest.main()
