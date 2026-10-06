import unittest
import test_lifecycle as fixtures

game=fixtures.game

class FamilyTypeTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown

    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def account(self,name):
        return game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)',(name,'test')).lastrowid

    def test_same_type_gets_distinct_persistent_origins(self):
        a=self.account('家族甲');b=self.account('家族乙')
        game.create_family(a,'林','hanlin')
        game.create_family(b,'赵','hanlin')
        first=game.family_row(a);second=game.family_row(b)
        self.assertNotEqual(first['background'],second['background'])
        self.assertEqual(first['tier'],second['tier'])
        self.assertNotIn(first['background'],game.family_origin_options('hanlin'))
        game.init_db()
        self.assertEqual(game.family_row(a)['background'],first['background'])

    def test_taken_background_is_rejected_at_signup(self):
        first=self.account('已立家');new=self.account('新家')
        origin=game.family_origin_options('merchant')[0]
        game.create_family(first,'宋','merchant',origin)
        with self.client.session_transaction() as sess:sess['uid']=new
        response=self.client.post('/create',data={'step':'family','surname':'郭','family':'merchant','background_merchant':origin})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(game.family_row(new))
        self.assertTrue('已被其他玩家选走' in response.get_data(as_text=True))

    def test_selected_origin_is_used(self):
        uid=self.account('新家')
        origin=game.family_origin_options('physician')[2]
        with self.client.session_transaction() as sess:sess['uid']=uid
        self.client.post('/create',data={'step':'family','surname':'邓','family':'physician','background_physician':origin})
        self.assertEqual(game.family_row(uid)['background'],origin)
        self.assertEqual(game.family_row(uid)['tier'],'physician')
