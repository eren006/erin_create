import unittest
from unittest.mock import patch
import test_lifecycle as fixtures
game=fixtures.game

class PalaceAidTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def admin_start(self):
        with self.client.session_transaction() as s: s['admin']=True
        return self.client.post('/admin/palace_aid')

    def start(self):
        game.run('UPDATE consorts SET rank=? WHERE id=?',(game.RANK_GUIFEI,self.atk))
        self.client.post('/palace_aid/apply')
        self.admin_start()
        return game.palace_aid_latest()

    def test_rank_unique_office_and_admin_gate(self):
        self.admin_start()
        self.assertIsNone(game.palace_aid_latest())
        self.client.post('/palace_aid/apply')
        self.assertIsNone(game.palace_steward())
        event=self.start()
        self.assertIsNotNone(event)
        self.login(self.tgt)
        game.run('UPDATE consorts SET rank=? WHERE id=?',(game.RANK_GUIFEI,self.tgt))
        self.client.post('/palace_aid/apply')
        self.assertEqual(game.palace_steward()['id'],self.atk)
        self.admin_start()
        self.assertEqual(len(game.q('SELECT * FROM palace_aid_events')),1)

    def test_steward_excluded_hourly_accumulation_and_total_cap(self):
        with patch.object(game,'now_ts',return_value=100000):
            event=self.start()
            self.client.post('/palace_aid/work',data={'event_id':event['id']})
            self.assertFalse(game.q('SELECT * FROM palace_aid_progress'))
            self.login(self.tgt)
            for _ in range(2): self.client.post('/palace_aid/work',data={'event_id':event['id'],'task':1})
            row=game.q('SELECT * FROM palace_aid_progress',one=True)
            self.assertEqual(row['times'],1)
            self.assertTrue(6<=row['progress']<=12)
        with patch.object(game,'now_ts',return_value=100000+9*3600):
            for _ in range(12): self.client.post('/palace_aid/work',data={'event_id':event['id'],'task':0})
            row=game.q('SELECT * FROM palace_aid_progress',one=True)
            self.assertEqual(row['times'],10)
            self.assertTrue(60<=row['progress']<=120)
            self.assertIn('核对份例',self.client.get('/palace_aid').get_data(as_text=True))

    def test_deadline_reward_exactly_once_and_stale_round(self):
        with patch.object(game,'now_ts',return_value=100000):
            event=self.start(); self.login(self.tgt)
            self.client.post('/palace_aid/work',data={'event_id':event['id']+1})
            self.assertFalse(game.q('SELECT * FROM palace_aid_progress'))
            self.client.post('/palace_aid/work',data={'event_id':event['id']})
        before=dict(game.get_consort(self.tgt))
        with patch.object(game,'now_ts',return_value=186400):
            self.client.post('/palace_aid/work',data={'event_id':event['id']})
            game.palace_aid_tick(); game.palace_aid_tick()
        after=game.get_consort(self.tgt)
        self.assertEqual(after['influence']-before['influence'],20)
        self.assertEqual(after['virtue']-before['virtue'],5)
        self.assertEqual(after['silver']-before['silver'],300)
        self.assertEqual(game.palace_aid_latest()['winner_id'],self.tgt)
        self.assertEqual(game.q('SELECT times FROM palace_aid_progress',one=True)['times'],1)

    def test_tie_two_winners_and_empty_round(self):
        event=self.start()
        other=self.player('丙')
        third=self.player('丁')
        for cid in (self.tgt,other,third): game.run('INSERT INTO palace_aid_progress VALUES(?,?,80,10)',(event['id'],cid))
        before=sum(game.get_consort(cid)['silver'] for cid in (self.tgt,other,third))
        game.run('UPDATE palace_aid_events SET ends_ts=0')
        game.palace_aid_tick()
        self.assertEqual(sum(game.get_consort(cid)['silver'] for cid in (self.tgt,other,third))-before,600)
        self.admin_start();game.run("UPDATE palace_aid_events SET ends_ts=0 WHERE status='active'")
        game.palace_aid_tick()
        self.assertEqual(game.palace_aid_latest()['winner_id'],0)

    def test_interference_actor_and_target_limits_and_floor(self):
        event=self.start()
        game.run('INSERT INTO palace_aid_progress VALUES(?,?,100,10)',(event['id'],self.tgt))
        data={'event_id':event['id'],'target_id':self.tgt}
        self.client.post('/palace_aid/interfere',data=data)
        self.assertFalse(game.q('SELECT * FROM palace_aid_interference'))
        actors=[self.player('干扰'+str(i)) for i in range(3)]
        for cid in actors[:2]:
            self.login(cid)
            for _ in range(4): self.client.post('/palace_aid/interfere',data=data)
        self.assertEqual(len(game.q('SELECT * FROM palace_aid_interference')),6)
        row=game.q('SELECT * FROM palace_aid_progress',one=True)
        self.assertTrue(58<=row['progress']<=82)
        self.login(actors[2]);self.client.post('/palace_aid/interfere',data=data)
        self.assertEqual(len(game.q('SELECT * FROM palace_aid_interference')),6)
        page=self.client.get('/palace_aid').get_data(as_text=True)
        self.assertIn('宫务排行榜',page)
        game.run('DELETE FROM palace_aid_interference')
        game.run('UPDATE palace_aid_progress SET progress=2')
        self.client.post('/palace_aid/interfere',data=data)
        self.assertEqual(game.q('SELECT progress FROM palace_aid_progress',one=True)['progress'],0)
        self.client.post('/palace_aid/interfere',data=data)
        self.assertEqual(len(game.q('SELECT * FROM palace_aid_interference')),1)

    def test_interference_rejects_self_stale_round_and_deadline(self):
        event=self.start();self.login(self.tgt)
        self.client.post('/palace_aid/work',data={'event_id':event['id']})
        for data in ({'event_id':event['id'],'target_id':self.tgt},{'event_id':event['id'],'target_id':self.atk},{'event_id':event['id']+1,'target_id':self.atk}):
            self.client.post('/palace_aid/interfere',data=data)
        self.assertFalse(game.q('SELECT * FROM palace_aid_interference'))
        game.run('UPDATE palace_aid_events SET ends_ts=0')
        self.client.post('/palace_aid/interfere',data={'event_id':event['id'],'target_id':self.atk})
        self.assertFalse(game.q('SELECT * FROM palace_aid_interference'))
