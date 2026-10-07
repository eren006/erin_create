"""体质一直衰减，掉到濒死线以下，12 小时内没好转就殒命"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class DyingTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def me(self): return game.get_consort(self.atk)

    def test_decay_has_no_floor_any_more_and_hits_harder_with_age(self):
        self.assertEqual(game.HEALTH_DECAY_FLOOR, 1)
        young = game.health_decay_rate(20 * 12)
        old = game.health_decay_rate(50 * 12)
        self.assertGreater(old, young)
        self.assertGreater(young, 0.5)
        game.run("UPDATE consorts SET health=3, age_months=600 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.health_decay_tick()
        self.assertEqual(self.me()['health'], 1)      # 一直掉到 1，不再停在 20

    def test_dropping_to_the_line_starts_the_clock_and_notifies(self):
        game.run("UPDATE consorts SET health=?, dying_since_ts=0 WHERE id=?", (game.HEALTH_DYING_AT, self.atk))
        game.dying_tick()
        c = self.me()
        self.assertGreater(c['dying_since_ts'], 0)
        self.assertEqual(c['status'], 'normal')
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%濒死%'", (self.atk,), one=True))

    def test_dies_after_12_hours_without_recovery(self):
        game.run("UPDATE consorts SET health=5 WHERE id=?", (self.atk,))
        game.dying_tick()
        game.run("UPDATE consorts SET dying_since_ts=? WHERE id=?", (game.now_ts() - 11 * 3600, self.atk))
        game.dying_tick()
        self.assertEqual(self.me()['status'], 'normal')
        game.run("UPDATE consorts SET dying_since_ts=? WHERE id=?", (game.now_ts() - 12 * 3600 - 5, self.atk))
        game.dying_tick()
        self.assertEqual(self.me()['status'], 'dead')

    def test_recovering_above_the_line_clears_the_clock(self):
        game.run("UPDATE consorts SET health=5 WHERE id=?", (self.atk,))
        game.dying_tick()
        game.run("UPDATE consorts SET health=? WHERE id=?", (game.HEALTH_DYING_AT + 1, self.atk))
        game.dying_tick()
        self.assertEqual(self.me()['dying_since_ts'], 0)
        game.run("UPDATE consorts SET health=5 WHERE id=?", (self.atk,))      # 再掉下去重新计时
        game.dying_tick()
        self.assertGreater(self.me()['dying_since_ts'], game.now_ts() - 5)

    def test_home_page_shows_the_dying_banner(self):
        game.run("UPDATE consorts SET health=4, recap_seen_day=99 WHERE id=?", (self.atk,))
        game.dying_tick()
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('你已濒死', html)

    def test_managed_consort_rests_by_herself(self):
        uid = game.run('UPDATE users SET managed=1 WHERE id=(SELECT user_id FROM consorts WHERE id=?)', (self.atk,))
        game.run("UPDATE consorts SET health=4, energy=8, silver=500 WHERE id=?", (self.atk,))
        game.bot_care(self.me())
        self.assertGreater(self.me()['health'], game.HEALTH_DYING_AT)


if __name__ == '__main__':
    unittest.main()
