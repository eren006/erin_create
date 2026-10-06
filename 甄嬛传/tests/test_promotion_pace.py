import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game

class PromotionPaceTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_work_and_aid_are_limited_and_cost_energy(self):
        before=game.get_consort(self.atk)
        health=game.get_consort(self.tgt)['health']
        self.client.post('/act/palace_work')
        self.client.post('/act/palace_work')
        self.client.post('/act/aid',data={'target_id':self.tgt})
        self.client.post('/act/aid',data={'target_id':self.tgt})
        after=game.get_consort(self.atk)
        self.assertEqual(after['influence'],before['influence']+6)
        self.assertEqual(after['energy'],before['energy']-2)
        self.assertEqual(after['silver'],before['silver']-20)
        self.assertEqual(game.get_consort(self.tgt)['health'],health+3)

    def test_invalid_aid_does_not_charge(self):
        before=game.get_consort(self.atk)
        self.client.post('/act/aid',data={'target_id':self.atk})
        after=game.get_consort(self.atk)
        self.assertEqual(after['energy'],before['energy'])
        self.assertEqual(after['silver'],before['silver'])
        self.assertEqual(game.daily_count(self.atk,'aid'),0)

    def test_perform_guarantees_minimum_gain_and_has_daily_limit(self):
        game.run('UPDATE game_state SET emperor_death_day=0')
        before=game.get_consort(self.atk)
        with patch.object(game.random,'random',return_value=.99):
            self.client.post('/act/perform')
            self.client.post('/act/perform')
        after=game.get_consort(self.atk)
        self.assertGreaterEqual(after['favor'],before['favor']+3)
        self.assertEqual(after['energy'],before['energy']-1)
        self.assertEqual(game.daily_count(self.atk,'perform'),1)

    def test_emperor_ill_blocks_perform_without_cost(self):
        game.run('UPDATE game_state SET emperor_death_day=10')
        before=game.get_consort(self.atk)
        self.client.post('/act/perform')
        self.assertEqual(game.get_consort(self.atk)['energy'],before['energy'])
        self.assertEqual(game.daily_count(self.atk,'perform'),0)

    def test_front_rank_wait_and_thresholds(self):
        self.assertEqual(game.PROMOTE_FAVOR,{2:30,3:65,4:110,5:180,6:280,7:420,8:600,9:850})
        for rank in (1,2,3):self.assertEqual(game.promotion_wait_days({'rank':rank}),1)
        for rank in (4,5,6,7,8):self.assertEqual(game.promotion_wait_days({'rank':rank}),2)

    def test_new_actions_visible_in_places(self):
        for route,labels in (('/place/yangxin',('御前展示才艺',)),('/place/jingren',('协办宫务','帮助姐妹'))):
            response=self.client.get(route)
            self.assertEqual(response.status_code,200)
            for label in labels:self.assertIn(label,response.get_data(as_text=True))
