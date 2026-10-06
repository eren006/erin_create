import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game
class MaintenancePauseTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    login=fixtures.LifecycleTests.login
    player=fixtures.LifecycleTests.player

    def test_paused_posts_do_not_change_player_or_queue(self):
        game.run('UPDATE game_state SET maintenance=1')
        before=dict(game.get_consort(self.atk))
        for path,data in [('/act/study',{}),('/intrigue/submit',dict(method='rumor',target_id=self.tgt)),('/create',dict(given='新人')),('/heirs/reclaim/1',{})]:
            r=self.client.post(path,data=data)
            self.assertEqual(r.status_code,503)
            self.assertEqual(r.headers['Retry-After'],'60')
        self.assertEqual(dict(game.get_consort(self.atk)),before)
        self.assertFalse(game.q('SELECT * FROM intrigues'))

    def test_players_cannot_resume_game_through_admin_endpoint(self):
        game.run('UPDATE game_state SET maintenance=1')
        self.client.post('/admin/emperor',data={'act':'maintenance_off'})
        self.assertEqual(game.state()['maintenance'],1)

    def test_admin_can_pause_and_resume_preserving_day(self):
        day=game.cur_day()
        with self.client.session_transaction() as sess:sess['admin']=True
        self.client.post('/admin/emperor',data={'act':'maintenance_on'})
        self.assertEqual(game.state()['maintenance'],1)
        self.assertEqual(self.client.get('/admin').status_code,200)
        with patch.object(game,'maybe_settle') as settle:game.run_settle_cycle();settle.assert_not_called()
        self.client.post('/admin/emperor',data={'act':'maintenance_off'})
        self.assertEqual(game.state()['maintenance'],0)
        self.assertEqual(game.cur_day(),day)
        before=game.get_consort(self.atk)['energy']
        self.client.post('/act/study',data={'art':'画'})
        self.assertLess(game.get_consort(self.atk)['energy'],before)

    def test_readonly_pages_remain_available(self):
        game.run('UPDATE game_state SET maintenance=1')
        for path in ('/','/help','/heirs','/social'):
            r=self.client.get(path);self.assertEqual(r.status_code,200)
            self.assertIn('玩家不能操作',r.get_data(as_text=True))
