import unittest
import test_lifecycle as fixtures

game=fixtures.game
class RegistrationQQTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_number_is_required_and_validated_on_server(self):
        for value in ('','QQ昵称','1234','0123456','1234567890123','１２３４５'):
            self.client.post('/register',data=dict(username='新报名',password='abcd',qq_number=value))
            self.assertFalse(game.q('SELECT 1 FROM users WHERE username=?',('新报名',)))

    def test_valid_qq_is_saved_and_form_required(self):
        page=self.client.get('/register').get_data(as_text=True)
        self.assertIn('name="qq_number"',page)
        self.assertIn('必填',page)
        r=self.client.post('/register',data=dict(username='新报名',password='abcd',qq_number='123456789'))
        self.assertEqual(r.status_code,302)
        self.assertEqual(game.q('SELECT qq_number FROM users WHERE username=?',('新报名',),one=True)[0],'123456789')
        with self.client.session_transaction() as sess: uid=sess['uid'];sess['admin']=True
        game.create_family(uid,'癸',next(iter(game.FAMILIES)))
        self.client.post('/create',data=dict(given='新秀',age=20,personality=next(iter(game.PERSONALITIES))))
        self.assertIn('123456789',self.client.get('/admin').get_data(as_text=True))
        self.assertNotIn('123456789',self.client.get('/social').get_data(as_text=True))
