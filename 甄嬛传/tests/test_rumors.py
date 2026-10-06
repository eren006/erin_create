"""流言库：流言得手时邸报写「流言四起：……」，不重复"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class RumorTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_library_is_big_unique_and_every_line_names_the_target(self):
        self.assertGreaterEqual(len(game.RUMORS), 50)
        self.assertEqual(len(set(game.RUMORS)), len(game.RUMORS))
        self.assertTrue(all('{t}' in r and r.count('{t}') == 1 for r in game.RUMORS))
        for r in game.RUMORS:
            self.assertTrue(r.endswith('。'))

    def test_pick_never_repeats_until_exhausted_then_restarts(self):
        seen = [game.pick_rumor('某某') for _ in range(len(game.RUMORS))]
        self.assertEqual(len(set(seen)), len(game.RUMORS), '一轮之内一条都不重复')
        self.assertTrue(all('某某' in s and '{t}' not in s for s in seen))
        again = game.pick_rumor('某某')                 # 用光了，清空重来
        self.assertIn(again, seen)
        self.assertEqual(len(game.q("SELECT * FROM rumor_used")), 1)

    def test_successful_rumor_writes_the_gazette_line(self):
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='rumor'", one=True)
        with patch.object(game.random, 'random', return_value=0.0):
            self.assertEqual(game.resolve_intrigue(it)[0], 'success')
        line = game.q("SELECT text FROM gazette WHERE kind='scandal' ORDER BY id DESC", one=True)['text']
        self.assertTrue(line.startswith('流言四起：'))
        self.assertIn(game.display_name(game.get_consort(self.tgt)), line)
        self.assertEqual(len(game.q("SELECT * FROM rumor_used")), 1)

    def test_two_successful_rumors_get_different_lines(self):
        lines = []
        for _ in range(2):
            game.run("DELETE FROM daily_counters")
            game.run("DELETE FROM intrigues")
            self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
            it = game.q("SELECT * FROM intrigues WHERE method='rumor'", one=True)
            with patch.object(game.random, 'random', return_value=0.0):
                game.resolve_intrigue(it)
            lines.append(game.q("SELECT text FROM gazette WHERE kind='scandal' ORDER BY id DESC", one=True)['text'])
        self.assertNotEqual(lines[0].split('：', 1)[1], lines[1].split('：', 1)[1])

    def test_failed_rumor_does_not_use_up_a_line(self):
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='rumor'", one=True)
        with patch.object(game.random, 'random', return_value=0.99):
            game.resolve_intrigue(it)
        self.assertEqual(len(game.q("SELECT * FROM rumor_used")), 0)

    def test_gazette_page_shows_it(self):
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='rumor'", one=True)
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_intrigue(it)
        self.assertIn('流言四起', self.client.get('/gazette').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
