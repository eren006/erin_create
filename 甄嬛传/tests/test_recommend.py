"""贵妃以上举荐晋位：对方势力 +5，并多一次晋位判定

运行：python3 -m unittest discover -s tests -v
"""
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class RecommendTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def rec(self, target):
        return self.client.post('/act/recommend', data={'target_id': target})

    def test_needs_rank_and_target_below_consort(self):
        game.run("UPDATE consorts SET rank=8 WHERE id=?", (self.atk,))
        base = game.get_consort(self.tgt)['influence']
        self.rec(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['influence'], base, '妃以下不能举荐')
        game.run("UPDATE consorts SET rank=9 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET rank=9 WHERE id=?", (self.tgt,))
        self.rec(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['influence'], base, '被举荐的必须在贵妃以下')

    def test_adds_influence_and_runs_one_promotion_check_once_a_day(self):
        game.run("UPDATE consorts SET rank=9, energy=5 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET rank=3, influence=0, favor=0 WHERE id=?", (self.tgt,))
        self.rec(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['influence'], game.RECOMMEND_INFLUENCE)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%举荐了你%'", (self.tgt,), one=True))
        self.rec(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['influence'], game.RECOMMEND_INFLUENCE, '每天只能举荐一次')

    def test_promotes_when_requirements_are_met(self):
        game.run("UPDATE consorts SET rank=9, energy=5 WHERE id=?", (self.atk,))
        nxt = 4
        game.run("UPDATE consorts SET rank=3, favor=9999, virtue=100, influence=? WHERE id=?", (game.PROMOTE_INFLUENCE[nxt] - game.RECOMMEND_INFLUENCE, self.tgt))
        self.rec(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['rank'], nxt)

    def test_page_lists_targets_for_high_rank_only(self):
        game.run("UPDATE consorts SET rank=9 WHERE id=?", (self.atk,))
        body = self.client.get('/place/jingren').get_data(as_text=True)
        self.assertIn('举荐晋位', body)
        self.assertIn('举荐谁', body)
