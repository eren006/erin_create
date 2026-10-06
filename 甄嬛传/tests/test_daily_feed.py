"""日常消息：明面上的日常记下来，使计、买药、打探这类暗事不记"""
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class DailyFeedTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def rows(self):
        return [r['text'] for r in game.q("SELECT * FROM daily_feed ORDER BY id")]

    def test_public_actions_are_recorded(self):
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.client.post('/act/greet')
        self.client.post('/act/garden')
        self.assertTrue(any('晨省' in t for t in self.rows()))
        self.assertTrue(any('御花园' in t for t in self.rows()))

    def test_visit_names_the_target(self):
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.client.post('/act/visit', data={'target_id': self.tgt})
        self.assertTrue(any(game.display_name(game.get_consort(self.tgt)) in t and '坐了坐' in t for t in self.rows()))

    def test_secret_things_are_not_recorded(self):
        game.run('UPDATE consorts SET energy=8, silver=2000 WHERE id=?', (self.atk,))
        for key in ('spy', 'eyes', 'schemestudy'):
            self.client.post(f'/act/{key}', data={'target_id': self.tgt})
        self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        game.inv_add(self.atk, 'lihun')
        self.client.post('/intrigue/submit', data={'method': 'drug', 'drug': 'lihun', 'target_id': self.tgt})
        self.assertEqual(self.rows(), [])
        self.assertNotIn('spy', game.FEED_TEXT)
        self.assertNotIn('eyes', game.FEED_TEXT)
        self.assertNotIn('schemestudy', game.FEED_TEXT)

    def test_failed_action_is_not_recorded(self):
        game.run('UPDATE consorts SET energy=0 WHERE id=?', (self.atk,))
        self.client.post('/act/garden')
        self.assertEqual(self.rows(), [])

    def test_page_renders_and_old_rows_are_cleaned(self):
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.client.post('/act/greet')
        html = self.client.get('/daily').get_data(as_text=True)
        self.assertIn('晨省', html)
        game.run("INSERT INTO daily_feed (day,consort_id,text,created_ts) VALUES (1,?,'很久以前的事',0)", (self.atk,))
        game.settle_day()
        self.assertFalse(any('很久以前' in t for t in self.rows()))


if __name__ == '__main__':
    unittest.main()
