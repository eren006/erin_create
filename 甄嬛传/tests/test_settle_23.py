import unittest
from unittest.mock import patch
from datetime import datetime
import test_lifecycle as fixtures

game=fixtures.game

class Settle23Tests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_boundary_is_midnight(self):
        self.assertEqual(game.SETTLE_HOUR,0)
        self.assertTrue(game.past_settle_time(datetime(2026,10,6,0,0,tzinfo=game.TZ)))
        self.assertTrue(game.past_settle_time(datetime(2026,10,6,12,30,tzinfo=game.TZ)))   # 错过 0 点也能补结算：按「今天还没结算」判

    def test_banquet_at_22_runs_before_midnight_settlement(self):
        game.run("UPDATE game_state SET event_started=1,maintenance=0,last_settle_date='2026-10-06'")
        calls=[]
        def banquet(_): calls.append('banquet')
        def settle(**_): calls.append('settle')
        with patch.object(game,'datetime') as clock,patch.object(game,'bedding_round'),patch.object(game,'energy_tick'),patch.object(game,'resolve_births'),patch.object(game,'maybe_banquet',side_effect=banquet),patch.object(game,'settle_day',side_effect=settle):
            clock.now.return_value=datetime(2026,10,6,22,0,tzinfo=game.TZ);game.maybe_settle()
            clock.now.return_value=datetime(2026,10,7,0,0,tzinfo=game.TZ);game.maybe_settle()
        self.assertEqual(calls,['banquet','banquet','settle'])

    def test_at_22_no_daily_settlement(self):
        game.run("UPDATE game_state SET event_started=1,maintenance=0,last_settle_date='2026-10-06'")
        with patch.object(game,'datetime') as clock,patch.object(game,'bedding_round'),patch.object(game,'energy_tick'),patch.object(game,'resolve_births'),patch.object(game,'maybe_banquet') as banquet,patch.object(game,'settle_day') as settle:
            clock.now.return_value=datetime(2026,10,6,22,0,tzinfo=game.TZ)
            game.maybe_settle();banquet.assert_called_once();settle.assert_not_called()
