"""禁足统一半天（12 小时），到点每分钟检查放人"""
import time
import unittest
from unittest.mock import patch
from datetime import datetime
import test_lifecycle as fixtures

game = fixtures.game


class ConfineHalfDayTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def me(self): return game.get_consort(self.atk)

    def test_confine_lasts_twelve_hours_whatever_the_days_argument(self):
        t0 = time.time()
        for days in (1, 2, 3, None):
            game.run("UPDATE consorts SET status='normal', confine_until_ts=0 WHERE id=?", (self.atk,))
            game.confine(self.atk, days)
            c = self.me()
            self.assertEqual(c['status'], 'confined')
            self.assertAlmostEqual(c['confine_until_ts'] - t0, game.CONFINE_HOURS * 3600, delta=5)

    def test_not_released_early_and_released_after_twelve_hours(self):
        game.confine(self.atk)
        game.release_confinements()
        self.assertEqual(self.me()['status'], 'confined')
        with patch.object(game, 'now_ts', return_value=time.time() + 11 * 3600):
            game.release_confinements()
        self.assertEqual(self.me()['status'], 'confined', '11 小时还不放')
        with patch.object(game, 'now_ts', return_value=time.time() + 12 * 3600 + 5):
            game.release_confinements()
        c = self.me()
        self.assertEqual((c['status'], c['confine_until_ts']), ('normal', 0))
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%禁足期满%'", (self.atk,), one=True))

    def test_second_confinement_does_not_shorten_the_first(self):
        game.confine(self.atk)
        first = self.me()['confine_until_ts']
        game.confine(self.atk)
        self.assertGreaterEqual(self.me()['confine_until_ts'], first)

    def test_cold_palace_is_not_affected(self):
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        game.confine(self.atk)
        self.assertEqual(self.me()['status'], 'cold')

    def test_scheduler_releases_every_minute(self):
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        game.confine(self.atk)
        game.run("UPDATE consorts SET confine_until_ts=? WHERE id=?", (time.time() - 1, self.atk))
        game.run("UPDATE game_state SET last_settle_date='2026-10-07'")
        with patch.object(game, 'datetime') as clock, patch.object(game, 'bedding_round'), patch.object(game, 'energy_tick'), \
             patch.object(game, 'resolve_births'), patch.object(game, 'maybe_banquet'):
            clock.now.return_value = datetime(2026, 10, 7, 14, 30, tzinfo=game.TZ)
            game.maybe_settle()
        self.assertEqual(self.me()['status'], 'normal')

    def test_home_page_shows_release_time(self):
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (self.atk,))
        game.confine(self.atk)
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('解禁', html)
        self.assertNotIn('第 None 天', html)

    def test_frame_penalty_text_says_half_day(self):
        self.assertIn('半天', game.INTRIGUES['frame']['desc'])
        self.assertIn('半天', game.INTRIGUES['steal']['desc'])


if __name__ == '__main__':
    unittest.main()
