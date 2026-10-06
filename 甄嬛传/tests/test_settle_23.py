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

    def test_boundary_is_23(self):
        self.assertEqual(game.SETTLE_HOUR,23)
        self.assertFalse(game.past_settle_time(datetime(2026,10,6,22,59,tzinfo=game.TZ)))
        self.assertTrue(game.past_settle_time(datetime(2026,10,6,23,0,tzinfo=game.TZ)))

    def test_banquet_reward_precedes_daily_settlement_on_late_restart(self):
        game.run("UPDATE game_state SET event_started=1,maintenance=0,last_settle_date=''")   # 初始化时按真实钟点定，过了 23 点会写成今天，这里显式清掉
        calls=[]
        now=datetime(2026,10,6,23,5,tzinfo=game.TZ)
        def banquet(_):
            calls.append('banquet')
            game.run('UPDATE consorts SET favor=favor+100 WHERE id=?',(self.atk,))
        def settle(**_):
            calls.append('settle')
            self.assertGreaterEqual(game.get_consort(self.atk)['favor'],100)
        with patch.object(game,'datetime') as clock,patch.object(game,'bedding_round',side_effect=lambda *_:calls.append('bedding')),patch.object(game,'energy_tick'),patch.object(game,'resolve_births'),patch.object(game,'maybe_banquet',side_effect=banquet),patch.object(game,'settle_day',side_effect=settle):
            clock.now.return_value=now;game.maybe_settle()
        self.assertEqual(calls,['bedding','banquet','settle'])

    def test_at_22_no_daily_settlement(self):
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        with patch.object(game,'datetime') as clock,patch.object(game,'bedding_round'),patch.object(game,'energy_tick'),patch.object(game,'resolve_births'),patch.object(game,'maybe_banquet') as banquet,patch.object(game,'settle_day') as settle:
            clock.now.return_value=datetime(2026,10,6,22,0,tzinfo=game.TZ)
            game.maybe_settle();banquet.assert_called_once();settle.assert_not_called()
