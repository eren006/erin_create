import unittest,sqlite3
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game

class RuleMigrationTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_existing_pregnancy_restores_actual_diagnosis(self):
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(self.atk,))
        game.run("INSERT INTO messages(consort_id,day,text,created_ts) VALUES(?,9,'太医诊出了喜脉。',100000)",(self.atk,))
        db=game.get_db()
        with patch.object(game.time,'time',return_value=150000):game.migrate_pregnancy_clocks(db)
        self.assertEqual(game.get_consort(self.atk)['pregnancy_started_ts'],100000)
        with patch.object(game.time,'time',return_value=160000):game.migrate_pregnancy_clocks(db)
        self.assertEqual(game.get_consort(self.atk)['pregnancy_started_ts'],100000)

    def test_missing_record_uses_elapsed_game_days(self):
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(self.atk,))
        with patch.object(game.time,'time',return_value=200000):game.migrate_pregnancy_clocks(game.get_db())
        self.assertEqual(game.get_consort(self.atk)['pregnancy_started_ts'],113600)

    def test_cancel_does_not_start_cooldown(self):
        game.inv_add(self.atk,'wuming')
        game.run('UPDATE consorts SET rank=6 WHERE id=?',(self.atk,))
        self.client.post('/intrigue/submit',data={'method':'drug','drug':'wuming','effect':'yanzhi','target_id':self.tgt})
        it=game.q('SELECT * FROM intrigues',one=True)
        self.client.post('/intrigue/cancel/'+str(it['id']))
        uid=game.get_consort(self.atk)['user_id']
        self.assertEqual(game.q('SELECT drug_ready_day,nameless_ready_day FROM users WHERE id=?',(uid,),one=True)[0],0)
        self.assertEqual(game.inv_qty(self.atk,'wuming'),1)
        self.assertEqual(game.daily_count(self.atk,'intrigue'),1)

    def test_one_day_shield_applies_to_both_sides(self):
        game.inv_add(self.atk,'yanzhi')
        for cid in (self.atk,self.tgt):
            game.run('UPDATE consorts SET entered_day=10 WHERE id=?',(cid,))
            self.assertIsNotNone(game.drug_block(game.get_consort(self.atk),game.get_consort(self.tgt),'yanzhi','yanzhi',0,10))
            game.run('UPDATE consorts SET entered_day=1 WHERE id=?',(cid,))
        self.assertIsNone(game.drug_block(game.get_consort(self.atk),game.get_consort(self.tgt),'yanzhi','yanzhi',0,10))

    def test_success_starts_account_and_target_cooldowns(self):
        for drug,cooldown in (('yanzhi',1),('lihun',2)):
            game.run('UPDATE consorts SET rank=6 WHERE id=?',(self.atk,))
            uid=game.get_consort(self.atk)['user_id']
            game.run('UPDATE users SET drug_ready_day=0,lethal_ready_day=0 WHERE id=?',(uid,))
            game.run('UPDATE consorts SET drugged_day=0,drugged_until_day=0 WHERE id=?',(self.tgt,))
            itid=game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,drug,item_used,created_ts) VALUES(10,?,?,'drug',?,?,0)",(self.atk,self.tgt,drug,drug)).lastrowid
            with patch.object(game.random,'random',return_value=0):
                result=game.resolve_drug(game.q('SELECT * FROM intrigues WHERE id=?',(itid,),one=True))[0]
            self.assertEqual(result,'success')
            self.assertEqual(game.q('SELECT drug_ready_day FROM users WHERE id=?',(uid,),one=True)[0],10+cooldown)
            self.assertEqual(game.get_consort(self.tgt)['drugged_until_day'],10+cooldown)
