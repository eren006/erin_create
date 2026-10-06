import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game

class PregnancyClockTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def conceive(self):
        game.run("UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?",(self.atk,))

    def test_exact_24_hours_and_idempotent(self):
        self.conceive()
        with patch.object(game.time,'time',return_value=186399):game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],0)
        before=game.get_consort(self.atk)
        with patch.object(game.time,'time',return_value=186400):
            game.resolve_births(10,False)
            game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],1)
        after=game.get_consort(self.atk)
        self.assertEqual(after['pregnant_since'],0)
        self.assertEqual(after['pregnancy_started_ts'],0)
        self.assertEqual(after['age_months'],before['age_months'])
        self.assertEqual(after['energy'],before['energy'])
        self.assertEqual(game.cur_day(),10)

    def test_progress_stages(self):
        self.conceive()
        for elapsed,percent,stage in ((0,0,'初孕'),(8*3600,33,'安胎'),(16*3600,66,'待产'),(86400,100,'临盆')):
            with patch.object(game.time,'time',return_value=100000+elapsed):
                progress=game.pregnancy_progress(game.get_consort(self.atk))
            self.assertEqual(progress['percent'],percent)
            self.assertIn(stage,progress['stage'])

    def test_maintenance_delays_birth_until_resume(self):
        self.conceive()
        game.run('UPDATE game_state SET event_started=1,maintenance=1')
        with patch.object(game.time,'time',return_value=186400),patch.object(game,'bedding_round'),patch.object(game,'settle_day'):
            game.maybe_settle()
            self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],0)
            game.run('UPDATE game_state SET maintenance=0')
            game.maybe_settle()
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],1)

    def test_miscarried_pregnancy_does_not_deliver(self):
        self.conceive()
        game.run('UPDATE consorts SET pregnant_since=0 WHERE id=?',(self.atk,))
        with patch.object(game.time,'time',return_value=186400):game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],0)

    def test_legacy_birth_only_in_daily_settlement(self):
        game.run('UPDATE consorts SET pregnant_since=8 WHERE id=?',(self.atk,))
        game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],0)
        game.resolve_births(10)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs',one=True)['n'],1)

    def test_new_pregnancy_page_shows_process_and_due_time(self):
        self.conceive()
        started=game.time.time()-8*3600
        game.run('UPDATE consorts SET pregnancy_started_ts=? WHERE id=?',(started,self.atk))
        with patch.object(game.time,'time',return_value=started+8*3600):
            page=self.client.get('/place/home').get_data(as_text=True)
        for label in ('安胎·胎息渐稳','孕期进度 33%','16小时0分钟','预计临盆','安胎静养'):
            self.assertTrue(label in page,label)

    def test_bedding_records_real_diagnosis_time(self):
        with patch.object(game.time,'time',return_value=100000),patch.object(game.random,'random',return_value=0):
            game.do_bedding(game.get_consort(self.atk),10,True,[])
        self.assertEqual(game.get_consort(self.atk)['pregnancy_started_ts'],100000)
