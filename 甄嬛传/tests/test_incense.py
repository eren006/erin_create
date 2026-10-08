"""寿康宫添香活动：每半个时辰一次，+5~10，满 100 赏 100 两和一份随机药

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class IncenseTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def burn(self):
        return self.client.post('/incense/burn')

    def test_flow_to_reward(self):
        cid = self.player('添香', 3)
        self.login(cid)
        self.assertEqual(self.client.get('/incense').status_code, 200)
        game.start_incense()
        silver = game.get_consort(cid)['silver']
        t = [1000.0]
        with patch.object(game, 'now_ts', lambda: t[0]):
            self.burn()
            row = game.incense_row(game.active_incense(), cid)
            self.assertTrue(5 <= row['progress'] <= 10)
            self.burn()                                    # 冷却内再点：不涨
            self.assertEqual(game.incense_row(game.active_incense(), cid)['progress'], row['progress'])
            for _ in range(30):
                t[0] += game.INCENSE_COOLDOWN + 1
                self.burn()
        row = game.incense_row(game.active_incense(), cid)
        self.assertEqual(row['progress'], 100)
        self.assertIn(row['reward'], game.INCENSE_DRUGS)
        self.assertEqual(game.get_consort(cid)['silver'], silver + 100)
        self.assertEqual(game.inv_qty(cid, row['reward']), 1)
        with patch.object(game, 'now_ts', lambda: t[0] + 10 ** 6):
            self.burn()                                    # 满了不再发第二份
        self.assertEqual(game.get_consort(cid)['silver'], silver + 100)
        self.assertEqual(game.inv_qty(cid, row['reward']), 1)

    def test_confined_cannot_burn(self):
        cid = self.player('禁足', 3)
        game.run("UPDATE consorts SET status='confined' WHERE id=?", (cid,))
        self.login(cid)
        game.start_incense()
        self.burn()
        self.assertIsNone(game.incense_row(game.active_incense(), cid))

    def test_expires_after_48h(self):
        cid = self.player('到期', 3)
        self.login(cid)
        t = [5000.0]
        with patch.object(game, 'now_ts', lambda: t[0]):
            game.start_incense()
            self.assertIsNotNone(game.active_incense())
            t[0] += 48 * 3600 - 1
            self.assertIsNotNone(game.active_incense())
            t[0] += 2
            self.assertIsNone(game.active_incense())
            self.burn()                                    # 过期后点不动
            self.assertEqual(game.q('SELECT COUNT(*) n FROM incense_progress', one=True)['n'], 0)
            game.start_incense()                           # 过期的旧轮不挡着开新一轮
            self.assertIsNotNone(game.active_incense())

    def test_nav_only_when_active(self):
        cid = self.player('导航', 3)
        self.login(cid)
        self.assertNotIn('href="/incense"', self.client.get('/').get_data(as_text=True))
        game.start_incense()
        self.assertIn('href="/incense"', self.client.get('/').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
