import unittest
import test_lifecycle as fixtures

game=fixtures.game

class LetterGiftTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def artwork(self,maker=None):
        return game.run("INSERT INTO hobby_items(kind,style,maker_id,holder_id,created_day) VALUES('painting','山水',?,?,10)",(maker or self.atk,self.atk)).lastrowid

    def test_newcomer_own_art_is_selected_and_transferred(self):
        game.run('UPDATE consorts SET entered_day=10 WHERE id=?',(self.atk,))
        iid=self.artwork()
        game.run("INSERT INTO displays(consort_id,slot,item_id) VALUES(?,'desk',?)",(self.atk,iid))
        page=self.client.get(f'/letters?hobby_item={iid}&to={self.tgt}').get_data(as_text=True)
        self.assertTrue(f'value="{iid}" selected' in page)
        self.client.post('/letters/send',data={'to_id':self.tgt,'body':'送你这幅画','hobby_item_id':iid})
        self.assertEqual(game.q('SELECT holder_id FROM hobby_items WHERE id=?',(iid,),one=True)['holder_id'],self.tgt)
        self.assertFalse(game.q('SELECT 1 FROM displays WHERE item_id=?',(iid,),one=True))
        letter=game.q('SELECT * FROM letters WHERE hobby_item_id=?',(iid,),one=True)
        self.assertEqual(letter['to_id'],self.tgt)
        self.login(self.tgt)
        inbox=self.client.get('/letters').get_data(as_text=True)
        self.assertTrue('送你这幅画' in inbox)
        self.assertTrue('作品已送达' in inbox)

    def test_newcomer_cannot_forward_others_art_or_silver(self):
        game.run('UPDATE consorts SET entered_day=10 WHERE id=?',(self.atk,))
        iid=self.artwork(self.tgt)
        before=game.get_consort(self.atk)['silver']
        for extra in ({'hobby_item_id':iid},{'silver':20}):
            self.client.post('/letters/send',data={'to_id':self.tgt,'body':'给你',**extra})
        self.assertEqual(game.q('SELECT holder_id FROM hobby_items WHERE id=?',(iid,),one=True)['holder_id'],self.atk)
        self.assertEqual(game.get_consort(self.atk)['silver'],before)
        self.assertFalse(game.q('SELECT 1 FROM letters',one=True))

    def test_old_player_money_and_item_arrive_immediately(self):
        game.inv_add(self.atk,'renshen',1)
        a=game.get_consort(self.atk)['silver'];b=game.get_consort(self.tgt)['silver']
        self.client.post('/letters/send',data={'to_id':self.tgt,'body':'补养','silver':20,'item':'renshen'})
        self.assertEqual(game.get_consort(self.atk)['silver'],a-20)
        self.assertEqual(game.get_consort(self.tgt)['silver'],b+20)
        self.assertEqual(game.inv_qty(self.tgt,'renshen'),1)
