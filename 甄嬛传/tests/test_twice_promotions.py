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

    def tick(self,hour,settled=True):
        if settled: game.run("UPDATE game_state SET last_settle_date='2026-10-07'")
        with patch.object(game,'datetime') as clock, patch.object(game,'resolve_births'), patch.object(game,'bedding_round'), patch.object(game,'energy_tick'), patch.object(game,'maybe_banquet'), patch.object(game,'night_event_tick'), patch.object(game,'repair_roll'):      # 夜间突发事件、屋舍损坏是随机扣银子的，和晋封无关，摁住
            clock.now.return_value=datetime(2026,10,7,hour,0,tzinfo=game.TZ)
            game.maybe_settle()

    def test_every_four_hours_checks_once_and_does_not_advance_day_or_pay(self):
        self.eligible()
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        before=game.get_consort(self.atk)
        game.run("UPDATE game_state SET last_age_key='2026-10-05:00'")      # 年龄归 age_tick 管（每 6 小时涨一岁），这里只看晋封不动年龄
        with patch.object(game, 'age_tick'):
            self.tick(4)                      # 04:00 就检查，不再只有中午
        after=game.get_consort(self.atk)
        self.assertEqual(after['rank'],2)
        self.assertEqual(game.cur_day(),10)
        self.assertEqual(after['silver'],before['silver'])
        self.assertEqual(after['age_months'],before['age_months'])
        with patch.object(game,'resolve_promotions',wraps=game.resolve_promotions) as promote:
            self.tick(4)                  # 同一个时点只查一次
            promote.assert_not_called()
            self.tick(8)                  # 下一个时点再查，一次最多晋一级
            promote.assert_called_once_with(10)
        self.assertEqual(game.get_consort(self.atk)['rank'],3)

    def test_settle_minute_is_left_to_the_settlement_itself(self):
        self.eligible()
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        with patch.object(game,'settle_day') as settle, patch.object(game,'resolve_promotions',wraps=game.resolve_promotions) as promote:
            game.run("UPDATE game_state SET last_settle_date=''")
            self.tick(0,settled=False)    # 0 点结算要跑：结算自己查晋封，这里不重复查
            settle.assert_called_once()
            promote.assert_not_called()
        self.assertEqual(game.get_consort(self.atk)['rank'],1)

    def test_midnight_round_still_checks_when_no_settlement_is_due(self):
        self.eligible()
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        self.tick(0)                      # 当天已经结算过（比如换时间表那天），0 点这一轮照常查
        self.assertEqual(game.get_consort(self.atk)['rank'],2)

    def test_no_wait_in_rank_required(self):
        self.eligible()
        game.run('UPDATE consorts SET rank_since_day=10 WHERE id=?',(self.atk,))   # 刚刚才晋的这一级
        self.assertEqual(len(game.resolve_promotions(10)),1)
        self.assertEqual(game.get_consort(self.atk)['rank'],2)

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

    def test_settle_slot_and_maintenance_block_extra_checks(self):
        self.eligible()
        game.run("UPDATE game_state SET event_started=1,maintenance=0,last_settle_date='2026-10-07',last_promo_key='2026-10-07:20'")
        self.tick(20)
        self.assertEqual(game.get_consort(self.atk)['rank'],1)
        game.run("UPDATE game_state SET last_settle_date='',maintenance=1")
        self.tick(12,settled=False)
        self.assertEqual(game.get_consort(self.atk)['rank'],1)

    def test_mourning_blocks_promotion(self):
        self.eligible()
        game.run('UPDATE game_state SET mourning=1')
        self.assertEqual(game.resolve_promotions(10),[])
        game.run('UPDATE game_state SET mourning=0')
        self.assertEqual(len(game.resolve_promotions(10)),1)
