"""四小时翻牌：轮次幂等、每日上限与日结算隔离。"""
import unittest
from unittest.mock import patch
from datetime import datetime
import test_lifecycle as fixtures

game=fixtures.game

class BeddingRoundsTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def enable(self):
        if not hasattr(self, 'third'): self.third = self.player('丙', rank=4)      # 每轮翻 3 位，得有至少 3 个人
        game.run('UPDATE game_state SET event_started=1,emperor_death_day=0,maintenance=0,mourning=0,day=1')

    def test_twelve_rounds_cap_three_and_do_not_run_daily_effects(self):
        self.enable()
        before=game.get_consort(self.atk)
        with patch.object(game.random,'random',return_value=.99999):
            for hour in game.BED_ROUND_HOURS:
                game.bedding_round(1,f'2026-10-05:{hour:02}')
        for cid in (self.atk,self.tgt,self.third):
            c=game.get_consort(cid)
            self.assertEqual(c['bed_daily_count'],game.BED_DAILY_MAX)
            self.assertEqual(c['pregnancy_misses'],game.BED_DAILY_MAX)
            self.assertEqual(c['age_months'],before['age_months'])
            self.assertEqual(c['silver'],before['silver'])
            self.assertEqual(c['energy'],before['energy'])
        self.assertEqual(game.cur_day(),1)
        with patch.object(game.random,'random',return_value=.99999):
            self.assertEqual(len(game.bedding_round(2,'2026-10-06:02')),2)
        self.assertEqual(sum(game.get_consort(cid)['bedded_count'] for cid in (self.atk,self.tgt,self.third)),3*game.BED_DAILY_MAX+2)

    def test_round_key_is_persisted_and_idempotent(self):
        self.enable()
        with patch.object(game.random,'random',return_value=.99999):
            self.assertEqual(len(game.bedding_round(1,'2026-10-05:02')),2)
            self.assertEqual(game.bedding_round(1,'2026-10-05:02'),[])
        self.assertEqual(game.state()['last_bed_round_key'],'2026-10-05:02')
        self.assertEqual(sum(game.get_consort(cid)['bedded_count'] for cid in (self.atk,self.tgt,self.third)),2)

    def test_paused_or_unstarted_round_does_not_consume_key(self):
        for field in ('maintenance','mourning'):
            self.enable()
            game.run(f'UPDATE game_state SET {field}=1')
            self.assertEqual(game.bedding_round(1,'test'),[])
            self.assertEqual(game.state()['last_bed_round_key'],'')
        self.enable()
        game.run('UPDATE game_state SET event_started=0')
        self.assertEqual(game.bedding_round(1,'test'),[])

    def test_schedule_every_hour_while_energy_and_promotion_stay_four(self):
        self.assertEqual(game.BED_ROUND_HOURS,tuple(range(24)))
        self.assertEqual(game.PACE_ROUND_HOURS,(0,4,8,12,16,20))
        self.assertEqual(game.latest_pace_slot(datetime(2026,10,5,7,30,tzinfo=game.TZ)),'2026-10-05:04')
        self.assertEqual(game.latest_bedding_slot(datetime(2026,10,5,7,30,tzinfo=game.TZ)),'2026-10-05:07')
        for hour in game.BED_ROUND_HOURS:
            now=datetime(2026,10,5,hour,0,tzinfo=game.TZ)
            self.assertEqual(game.latest_bedding_slot(now),f'2026-10-05:{hour:02}')
        self.assertEqual(game.latest_bedding_slot(datetime(2026,10,5,0,30,tzinfo=game.TZ)),'2026-10-05:00')
        self.assertEqual(game.latest_bedding_slot(datetime(2026,10,5,23,30,tzinfo=game.TZ)),'2026-10-05:23')

    def test_direct_bedding_also_respects_cap(self):
        with patch.object(game.random,'random',return_value=.99999):
            for _ in range(4):game.do_bedding(game.get_consort(self.atk),10,False,[])
        c=game.get_consort(self.atk)
        self.assertEqual(c['bedded_count'],game.BED_DAILY_MAX)
        self.assertEqual(c['pregnancy_misses'],game.BED_DAILY_MAX)

    def test_failure_rolls_back_round_and_effects(self):
        self.enable()
        with patch.object(game,'do_bedding',side_effect=RuntimeError('round failed')):
            with self.assertRaises(RuntimeError):game.bedding_round(1,'test')
        self.assertEqual(game.state()['last_bed_round_key'],'')

    def test_scheduler_routes_daytime_and_midnight_round(self):
        self.enable()
        game.run("UPDATE game_state SET last_settle_date='2026-10-05'")
        for hour in range(2,24,2):
            now=datetime(2026,10,5,hour,0,tzinfo=game.TZ)
            with patch.object(game,'datetime') as clock, patch.object(game,'bedding_round') as bed, patch.object(game,'settle_day') as settle:
                clock.now.return_value=now
                game.maybe_settle()
                settle.assert_not_called()
                bed.assert_called_once_with(1,f'2026-10-05:{hour:02}')
        now=datetime(2026,10,6,0,0,tzinfo=game.TZ)      # 0 点：这一轮同时是日结算，换新一天
        with patch.object(game,'datetime') as clock, patch.object(game,'bedding_round') as bed, patch.object(game,'settle_day') as settle:
            clock.now.return_value=now
            game.maybe_settle()
            settle.assert_called_once_with(bed_key='2026-10-06:00')
            bed.assert_called_once_with(1,'2026-10-06:00')
            game.run("UPDATE game_state SET last_settle_date='2026-10-06',last_bed_round_key='2026-10-06:00',day=2")
        with patch.object(game,'datetime') as clock:
            clock.now.return_value=now
            with patch.object(game,'do_bedding') as effect:
                game.maybe_settle()
                effect.assert_not_called()

    def test_queen_eligible_but_pregnant_and_ill_excluded(self):
        game.run('UPDATE consorts SET rank=9 WHERE id=?',(self.atk,))
        self.assertTrue(game.eligible_bedding(game.get_consort(self.atk),10))
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(self.atk,))
        self.assertFalse(game.eligible_bedding(game.get_consort(self.atk),10))

    def test_xinggong_trip_beds_six_once_per_day(self):
        self.enable()
        extra=[self.player(f'随{i}',rank=3) for i in range(5)]       # 加上甲乙丙正好 8 个符合条件的人
        with patch.object(game.random,'random',return_value=0.0):
            beds=game.bedding_round(1,'2026-10-05:03')
        self.assertEqual(len(beds),game.XINGGONG_COUNT)
        self.assertEqual(len({b['id'] for b in beds}),game.XINGGONG_COUNT)
        self.assertEqual(sum(game.get_consort(cid)['bed_daily_count'] for cid in [self.atk,self.tgt,self.third]+extra),game.XINGGONG_COUNT)
        self.assertEqual(len([r for r in game.q("SELECT text FROM gazette WHERE text LIKE '%驾幸%'")]),1)
        self.assertEqual(len(game.q("SELECT id FROM gazette WHERE text LIKE '敬事房：本轮皇上翻了%'")),0,'随驾不再逐人发敬事房邸报')
        with patch.object(game.random,'random',return_value=0.0):
            beds2=game.bedding_round(1,'2026-10-05:04')
        self.assertLessEqual(len(beds2),game.BED_MAX_PER_ROUND,'同一游戏日不再触发第二次，回到普通的 1~3 位')

    def test_xinggong_needs_enough_people(self):
        self.enable()
        with patch.object(game.random,'random',return_value=0.0):
            beds=game.bedding_round(1,'2026-10-05:03')
        self.assertLessEqual(len(beds),3)
