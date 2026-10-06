import unittest
from datetime import datetime
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game

class TwicePromotionTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def eligible(self, rank=1):
        game.run("UPDATE consorts SET rank=?,rank_since_day=1,title='',favor=1000,virtue=100,influence=200 WHERE id=?", (rank,self.atk))

    def tick(self,hour):
        with patch.object(game,'datetime') as clock, patch.object(game,'resolve_births'), patch.object(game,'bedding_round'), patch.object(game,'energy_tick'), patch.object(game,'maybe_banquet'):
            clock.now.return_value=datetime(2026,10,7,hour,0,tzinfo=game.TZ)
            game.maybe_settle()

    def test_noon_runs_once_and_does_not_advance_day_or_pay(self):
        self.eligible()
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        before=game.get_consort(self.atk)
        self.tick(11)
        self.assertEqual(game.get_consort(self.atk)['rank'],1)
        self.tick(12)
        self.tick(13)
        after=game.get_consort(self.atk)
        self.assertEqual(after['rank'],2)
        self.assertEqual(game.cur_day(),10)
        self.assertEqual(after['silver'],before['silver'])
        self.assertEqual(after['age_months'],before['age_months'])
        with patch.object(game,'resolve_promotions',wraps=game.resolve_promotions) as promote:
            self.tick(23)
            promote.assert_called_once_with(10)
        self.assertEqual(game.get_consort(self.atk)['rank'],2)
        self.assertEqual(game.cur_day(),11)

    def test_rank_can_gain_title_and_existing_title_is_kept(self):
        self.eligible()
        with patch.object(game.random,'random',return_value=.29):game.resolve_promotions(10)
        c=game.get_consort(self.atk)
        self.assertTrue(c['title'])
        self.assertTrue(game.q("SELECT id FROM messages WHERE consort_id=? AND text LIKE '%赐封号%'",(self.atk,)))
        title=c['title']
        game.run('UPDATE consorts SET rank_since_day=1 WHERE id=?',(self.atk,))
        game.resolve_promotions(10)
        self.assertEqual(game.get_consort(self.atk)['title'],title)

    def test_no_title_roll_still_promotes_and_pin_guarantees_title(self):
        self.eligible()
        with patch.object(game.random,'random',return_value=.30):game.resolve_promotions(10)
        self.assertEqual(game.get_consort(self.atk)['title'],'')
        self.eligible(4)
        with patch.object(game.random,'random',return_value=.99):game.resolve_promotions(10)
        self.assertEqual(game.get_consort(self.atk)['rank'],5)
        self.assertTrue(game.get_consort(self.atk)['title'])

    def test_settled_today_and_maintenance_block_extra_noon(self):
        self.eligible()
        game.run("UPDATE game_state SET event_started=1,maintenance=0,last_settle_date='2026-10-07'")
        self.tick(21)
        self.assertEqual(game.get_consort(self.atk)['rank'],1)
        game.run("UPDATE game_state SET last_settle_date='',maintenance=1")
        self.tick(12)
        self.assertEqual(game.get_consort(self.atk)['rank'],1)

    def test_mourning_and_rank_wait_remain(self):
        self.eligible()
        game.run('UPDATE game_state SET mourning=1')
        self.assertEqual(game.resolve_promotions(10),[])
        game.run('UPDATE game_state SET mourning=0')
        game.run('UPDATE consorts SET rank_since_day=10 WHERE id=?',(self.atk,))
        self.assertEqual(game.resolve_promotions(10),[])
