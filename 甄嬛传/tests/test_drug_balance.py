import unittest
from unittest.mock import patch
import test_drugs

game=test_drugs.game

class DrugBalanceTests(unittest.TestCase):
    setUp=test_drugs.DrugTests.setUp
    tearDown=test_drugs.DrugTests.tearDown
    player=test_drugs.DrugTests.player
    login=test_drugs.DrugTests.login
    plan=test_drugs.DrugTests.plan
    apply=test_drugs.DrugTests.apply

    def test_temporary_stat_restored_at_exact_expiry_once(self):
        for drug,stat in (('yanzhi','appearance'),('yachan','talent')):
            game.run('UPDATE consorts SET drugged_day=0,drugged_until_day=0 WHERE id=?',(self.tgt,))
            uid=game.get_consort(self.atk)['user_id'];game.run('UPDATE users SET drug_ready_day=0 WHERE id=?',(uid,))
            before=game.get_consort(self.tgt)[stat]
            with patch.object(game.time,'time',return_value=100000):
                self.assertEqual(self.apply(drug)[1],'success')
            self.assertEqual(game.get_consort(self.tgt)[stat],before-5)
            with patch.object(game.time,'time',return_value=186399):
                self.assertIsNotNone(game.affliction(self.tgt,drug))
                game.resolve_realtime_drugs(10)
            with patch.object(game.time,'time',return_value=186400):
                game.resolve_realtime_drugs(10);game.resolve_realtime_drugs(10)
                self.assertIsNone(game.affliction(self.tgt,drug))
            self.assertEqual(game.get_consort(self.tgt)[stat],before)

    def test_fake_pregnancy_cannot_create_heir(self):
        with patch.object(game.time,'time',return_value=100000):self.assertEqual(self.apply('chunxin')[1],'success')
        with patch.object(game.time,'time',return_value=186399):game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT count(*) n FROM heirs',one=True)['n'],0)
        with patch.object(game.time,'time',return_value=186400):game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT count(*) n FROM heirs',one=True)['n'],0)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],0)
        self.assertEqual(game.get_consort(self.tgt)['trust'],15)
        self.assertEqual(game.get_consort(self.tgt)['status_until_day'],11)

    def test_slow_poison_first_hit_then_daily_until_cured(self):
        before=game.get_consort(self.tgt)['health']
        self.assertEqual(self.apply('qingsi')[1],'success')
        for day in (10,10,11,11,12,13):game.tick_drugs(day)      # 同一天只扣一次：10、11、12、13 共四天
        self.assertEqual(game.get_consort(self.tgt)['health'],before-game.SLOW_POISON_FIRST-3*game.SLOW_POISON_TICK)
        self.assertIsNotNone(game.affliction(self.tgt,'qingsi'),'没解毒就不会自己停')

    def test_dream_only_triggers_once(self):
        self.assertEqual(self.apply('jingmeng')[1],'success')
        game.run('UPDATE consorts SET favor=100,trust=20 WHERE id=?',(self.tgt,))
        with patch.object(game.random,'random',return_value=.99):
            game.do_bedding(game.get_consort(self.tgt),10,False,[])
            self.assertEqual(game.get_consort(self.tgt)['favor'],100-game.FAVOR_LOSS['dream'])
            self.assertEqual(game.get_consort(self.tgt)['trust'],17)
            game.do_bedding(game.get_consort(self.tgt),10,False,[])
        self.assertGreater(game.get_consort(self.tgt)['favor'],100-game.FAVOR_LOSS['dream'])

    def test_hanshui_antidote_keeps_pregnancy_and_48h_limit(self):
        game.run('UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000 WHERE id=?',(self.tgt,))
        game.inv_add(self.tgt,'antai')
        before=game.get_consort(self.tgt)['health']
        with patch.object(game.time,'time',return_value=100000):self.assertEqual(self.apply('hanshui')[1],'success')
        self.assertEqual(game.get_consort(self.tgt)['health'],before-10)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],10)
        self.assertEqual(game.inv_qty(self.tgt,'antai'),0)
        with patch.object(game.time,'time',return_value=272799):self.assertIsNotNone(game.affliction(self.tgt,'hanshui'))
        with patch.object(game.time,'time',return_value=272800):self.assertIsNone(game.affliction(self.tgt,'hanshui'))

    def test_nameless_delays_case_instead_of_permanent_immunity(self):
        with patch.object(game.time,'time',return_value=100000):self.assertEqual(self.apply('wuming','yanzhi')[1],'success')
        self.assertEqual(len(game.q('SELECT * FROM cases')),0)
        with patch.object(game.time,'time',return_value=186400):
            game.resolve_realtime_drugs(10);game.resolve_realtime_drugs(10)
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)

    def test_hanshui_miscarriage_probability_has_both_outcomes(self):
        for roll,expected in ((.49,0),(.50,10)):
            game.run('UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000,drugged_day=0,drugged_until_day=0 WHERE id=?',(self.tgt,))
            uid=game.get_consort(self.atk)['user_id'];game.run('UPDATE users SET drug_ready_day=0 WHERE id=?',(uid,))
            it=self.plan('hanshui')
            with patch.object(game.random,'random',side_effect=[0,roll]):
                self.assertEqual(game.resolve_drug(it)[0],'success')
            self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],expected)

    def test_legacy_temporary_damage_migration_restores_original_loss(self):
        game.run('UPDATE consorts SET appearance=30 WHERE id=?',(self.tgt,))
        aid=game.run("INSERT INTO afflictions(consort_id,drug,start_day,until_day) VALUES(?,'yanzhi',9,11)",(self.tgt,)).lastrowid
        game.run('UPDATE game_state SET drug_balance_version=0')
        with patch.object(game.time,'time',return_value=200000):
            game.migrate_drug_balance(game.get_db())
            game.get_db().commit()
            game.resolve_realtime_drugs(10)
            game.resolve_realtime_drugs(10)
        self.assertEqual(game.get_consort(self.tgt)['appearance'],40)
        self.assertEqual(game.q('SELECT status FROM afflictions WHERE id=?',(aid,),one=True)[0],'done')
