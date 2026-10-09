import unittest
import test_lifecycle as fixtures
game=fixtures.game
class ColdChildrenTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def child(self,adult=0):
        return game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,adult_day) VALUES(?,?,'皇子',2,10,?)",(self.tgt,self.atk,adult)).lastrowid

    def test_cold_releases_children_and_bonus_cancels_claims(self):
        hid=self.child();adult=self.child(1)
        game.adopt_bonus_grant(self.atk,hid)
        before=game.get_consort(self.atk)['influence']
        game.run('UPDATE heirs SET foster_request_to=? WHERE id=?',(self.atk,hid))
        game.run('INSERT INTO heir_claims(consort_id,heir_id,day) VALUES(?,?,10)',(self.atk,hid))
        game.run('INSERT INTO custody_battles(heir_id,challenger_id,defender_id,started_day) VALUES(?,?,?,10)',(hid,self.tgt,self.atk))
        game.send_to_cold(self.atk)
        h=game.get_heir(hid)
        self.assertEqual(h['caretaker_id'],0)
        self.assertEqual(h['mother_id'],self.tgt)
        self.assertEqual(h['adopt_bonus_to'],0)
        self.assertEqual(h['foster_request_to'],0)
        self.assertEqual(game.get_consort(self.atk)['influence'],before-game.ADOPT_INFLUENCE)
        self.assertEqual(game.get_heir(adult)['caretaker_id'],self.atk)
        self.assertFalse(game.q('SELECT * FROM heir_claims WHERE consort_id=?',(self.atk,)))
        self.assertEqual(game.q('SELECT status FROM custody_battles WHERE heir_id=?',(hid,),one=True)['status'],'void')
        game.reconcile_cold_children()
        self.assertEqual(game.get_consort(self.atk)['influence'],before-game.ADOPT_INFLUENCE)

    def test_legacy_cold_caretakers_repaired_and_cannot_reclaim(self):
        hid=self.child()
        game.run("UPDATE consorts SET status='cold',rank=10 WHERE id=?",(self.atk,))
        self.assertEqual(game.reconcile_cold_children(),1)
        self.login(self.atk)
        self.client.post(f'/succession/claim/{hid}')
        self.assertEqual(game.get_heir(hid)['caretaker_id'],0)
        self.assertEqual(game.reconcile_cold_children(),0)
