"""嫔位以上的好处：封号三选一、陪皇上批折子、责罚低位妃嫔、月例银"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class Rank5PerkTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def me(self, cid=None): return game.get_consort(cid or self.atk)

    def test_stipend_raised(self):
        self.assertEqual(game.STIPEND[4], 75)
        self.assertEqual(game.STIPEND[5], 200)
        self.assertEqual(game.STIPEND[10], 1000)

    def test_promotion_to_pin_offers_three_titles_and_pick_changes_title(self):
        game.run("UPDATE consorts SET rank=4, title='怡', title_choices='' WHERE id=?", (self.tgt,))
        game.set_rank(self.tgt, 5)
        choices = self.me(self.tgt)['title_choices']
        self.assertEqual(len(choices), 3)
        self.assertNotIn('怡', choices)
        self.login(self.tgt)
        self.client.post('/title_pick', data={'pick': choices[0]})
        c = self.me(self.tgt)
        self.assertEqual((c['title'], c['title_choices']), (choices[0], ''))

    def test_keep_title_clears_choices(self):
        game.run("UPDATE consorts SET rank=4, title='怡' WHERE id=?", (self.tgt,))
        game.set_rank(self.tgt, 5)
        self.login(self.tgt)
        self.client.post('/title_pick', data={'pick': 'keep'})
        c = self.me(self.tgt)
        self.assertEqual((c['title'], c['title_choices']), ('怡', ''))

    def test_pizhe_needs_pin_rank_and_gives_influence(self):
        game.run("UPDATE game_state SET emperor_mood='平和'")
        game.run("UPDATE consorts SET rank=4, energy=5 WHERE id=?", (self.tgt,))
        self.login(self.tgt)
        before = self.me(self.tgt)['influence']
        self.client.post('/act/pizhe')
        self.assertEqual(self.me(self.tgt)['influence'], before)
        game.run("UPDATE consorts SET rank=5, energy=5 WHERE id=?", (self.tgt,))
        trust = self.me(self.tgt)['trust']
        self.client.post('/act/pizhe')
        c = self.me(self.tgt)
        self.assertEqual(c['influence'], before + 4)
        self.assertEqual(c['trust'], trust + 2)

    def test_chastise_penalises_lower_rank_and_adds_influence(self):
        game.run("UPDATE consorts SET rank=5, energy=5 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET rank=4, favor=50, silver=200 WHERE id=?", (self.tgt,))
        self.login(self.atk)
        inf = self.me()['influence']
        self.client.post('/act/chastise', data={'target_id': self.tgt, 'mode': 'fine'})
        self.assertEqual(self.me(self.tgt)['silver'], 200 - game.CHASTISE_FINE)
        self.assertEqual(self.me()['influence'], inf + game.CHASTISE_INFLUENCE)
        self.client.post('/act/chastise', data={'target_id': self.tgt, 'mode': 'kneel'})   # 同一天同一人只罚一次
        self.assertEqual(self.me(self.tgt)['favor'], 50)

    def test_chastise_rejects_pin_or_higher_targets(self):
        game.run("UPDATE consorts SET rank=6, energy=5 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET rank=5, silver=200 WHERE id=?", (self.tgt,))
        self.login(self.atk)
        self.client.post('/act/chastise', data={'target_id': self.tgt, 'mode': 'fine'})
        self.assertEqual(self.me(self.tgt)['silver'], 200)


if __name__ == '__main__':
    unittest.main()
