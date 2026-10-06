import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game

class BanquetCategoryTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_thresholds(self):
        self.assertEqual([game.banquet_category_factor(n) for n in range(1,7)],[1.05,1,.95,.95,.90,.90])

    def test_score_uses_actual_participants(self):
        date='2026-10-05';art=game.ARTS[0]
        for cid in (self.atk,self.tgt):game.run('INSERT INTO banquet_entries(banquet_date,consort_id,art,piece) VALUES(?,?,?,?)',(date,cid,art,'曲'))
        game.run("UPDATE consorts SET status='dead' WHERE id=?",(self.tgt,))
        with patch.object(game,'banquet_score',return_value=(100,False)):game.run_banquet(date)
        self.assertEqual(game.q('SELECT score FROM banquet_entries WHERE consort_id=?',(self.atk,),one=True)[0],105)

    def test_change_does_not_charge_again_and_resets_rehearsal(self):
        date=game.banquet_date();art=game.ARTS[0];other=game.ARTS[1]
        game.run('INSERT INTO banquet_entries(banquet_date,consort_id,art,piece,rehearsed,buff) VALUES(?,?,?,?,2,6)',(date,self.atk,art,'原节目'))
        energy=game.get_consort(self.atk)['energy']
        self.client.post('/banquet/change',data={'piece':other+'|0'})
        e=game.q('SELECT * FROM banquet_entries WHERE consort_id=?',(self.atk,),one=True)
        self.assertEqual(e['art'],other);self.assertEqual(e['rehearsed'],0);self.assertEqual(e['buff'],6)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy)
        game.run('UPDATE banquet_entries SET place=1 WHERE id=?',(e['id'],))
        self.client.post('/banquet/change',data={'piece':art+'|0'})
        self.assertEqual(game.q('SELECT art FROM banquet_entries WHERE id=?',(e['id'],),one=True)[0],other)
