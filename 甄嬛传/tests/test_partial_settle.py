"""补结算（partial）：只做换日这类增量项，每晚一次的账不重复算"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class PartialSettleTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def snap(self):
        c = game.get_consort(self.atk)
        return dict(age=c['age_months'], silver=c['silver'], favor=c['favor'], energy=c['energy'])

    def test_partial_skips_nightly_money_age_and_decay_but_changes_day_and_refills_energy(self):
        game.run('UPDATE consorts SET energy=1, favor=200, silver=500 WHERE id=?', (self.atk,))
        game.run("UPDATE game_state SET event_started=1")
        before, day = self.snap(), game.cur_day()
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day(bed_key='x', partial=True)
        after = self.snap()
        self.assertEqual(after['age'], before['age'], '不再长年龄')
        self.assertEqual(after['silver'], before['silver'], '不再发例银、不再扣伙食和宫人月钱')
        self.assertGreaterEqual(after['favor'], before['favor'], '圣宠不再流失（召见仍可能加圣宠）')
        self.assertEqual(after['energy'], game.ENERGY_MAX, '精力回满')
        self.assertEqual(game.cur_day(), day + 1, '换日')

    def test_full_settle_still_does_everything(self):
        game.run('UPDATE consorts SET favor=200, silver=500 WHERE id=?', (self.atk,))
        before = self.snap()
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day(bed_key='x')
        after = self.snap()
        self.assertEqual(after['age'], before['age'], '年龄现在由每 6 小时一次的 age_tick 涨，不再跟结算')
        self.assertLess(after['favor'], before['favor'])

    def test_partial_still_resolves_pending_intrigue(self):
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        self.assertEqual(game.q("SELECT status FROM intrigues", one=True)['status'], 'pending')
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day(bed_key='x', partial=True)
        self.assertEqual(game.q("SELECT status FROM intrigues", one=True)['status'], 'done')

    def test_partial_flag_does_not_leak_into_next_settlement(self):
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day(bed_key='x', partial=True)
        before = self.snap()
        with patch.object(game.random, 'random', return_value=0.99):
            game.settle_day(bed_key='y')
        self.assertEqual(self.snap()['age'], before['age'], '年龄不在结算里涨')


if __name__ == '__main__':
    unittest.main()
