"""双方抚养权争夺的真实路由与结算检查。"""
import unittest
import test_heirs

game = test_heirs.game

class CustodyBattleTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def begin(self):
        self.defender = self.player('丙', rank=6)
        self.hid = self.heir(self.atk, caretaker=self.defender, born=game.cur_day(), mother_affinity=70, caretaker_affinity=40, visit_banned=1)
        self.client.post(f'/heirs/reclaim/{self.hid}')
        return self.battle()

    def battle(self):
        return game.q('SELECT * FROM custody_battles WHERE heir_id=?',(self.hid,),one=True)

    def child(self):
        return game.q('SELECT * FROM heirs WHERE id=?',(self.hid,),one=True)

    def act(self, cid, action='bond'):
        self.login(cid)
        return self.client.post(f'/heirs/custody/{self.hid}',data={'action':action})

    def next_day(self):
        game.run('UPDATE game_state SET day=day+1')
        game.run('UPDATE consorts SET energy=5')

    def win(self, cid):
        for _ in range(4):
            self.act(cid, 'provide')
            if self.battle()['status']!='active': return
            if game.daily_count(cid,f'custody:{self.hid}:{self.battle()["started_day"]}')>=2: self.next_day()

    def test_start_preserves_custody_and_notifies_both_progress(self):
        b=self.begin()
        self.assertEqual((b['challenger_progress'],b['defender_progress']),(0,0))
        self.assertEqual(self.child()['caretaker_id'],self.defender)
        self.assertTrue(game.q('SELECT * FROM messages WHERE consort_id=?',(self.defender,)))
        self.login(self.defender)
        page=self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('养母方',page)
        self.assertIn('御前陈情',page)

    def test_challenger_reaches_target_returns_child(self):
        self.begin();self.win(self.atk)
        self.assertEqual(self.battle()['winner_id'],self.atk)
        self.assertEqual(self.child()['caretaker_id'],self.atk)
        self.assertEqual(self.child()['caretaker_affinity'],70)
        self.assertEqual(self.child()['visit_banned'],0)

    def test_defender_reaches_target_keeps_child(self):
        self.begin();self.win(self.defender)
        self.assertEqual(self.battle()['winner_id'],self.defender)
        self.assertEqual(self.child()['caretaker_id'],self.defender)

    def test_daily_limit_applies_separately_and_cannot_spam(self):
        self.begin()
        for _ in range(2): self.act(self.atk)
        progress=self.battle()['challenger_progress'];energy=game.get_consort(self.atk)['energy']
        self.act(self.atk)
        self.assertEqual(self.battle()['challenger_progress'],progress)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy)
        self.act(self.defender)
        self.assertGreater(self.battle()['defender_progress'],0)

    def test_nonparticipant_cannot_advance_or_surrender(self):
        self.begin();energy=game.get_consort(self.tgt)['energy']
        for action in ('bond','yield'): self.act(self.tgt,action)
        self.assertEqual(self.battle()['status'],'active')
        self.assertEqual(self.battle()['challenger_progress'],0)
        self.assertEqual(game.get_consort(self.tgt)['energy'],energy)

    def test_costs_and_insufficient_silver_are_atomic(self):
        self.begin();game.run('UPDATE consorts SET silver=49 WHERE id=?',(self.atk,))
        energy=game.get_consort(self.atk)['energy'];self.act(self.atk,'provide')
        self.assertEqual(game.get_consort(self.atk)['silver'],49)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy)
        self.assertEqual(self.battle()['challenger_progress'],0)
        game.run('UPDATE consorts SET silver=100 WHERE id=?',(self.atk,));self.act(self.atk,'provide')
        self.assertEqual(game.get_consort(self.atk)['silver'],50)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy-1)

    def test_duplicate_start_does_not_reset_progress_or_charge(self):
        self.begin();self.act(self.atk);before=dict(self.battle());energy=game.get_consort(self.atk)['energy']
        self.client.post(f'/heirs/reclaim/{self.hid}')
        self.assertEqual(dict(self.battle()),before)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy)

    def test_adulthood_lead_and_tie_rules(self):
        self.begin();self.act(self.atk)
        game.custody_battle_tick(game.cur_day()+7)
        self.assertEqual(self.battle()['winner_id'],self.atk)
        self.hid=self.heir(self.atk,caretaker=self.defender,born=game.cur_day())
        self.login(self.atk);self.client.post(f'/heirs/reclaim/{self.hid}')
        game.custody_battle_tick(game.cur_day()+7)
        self.assertEqual(self.battle()['winner_id'],self.defender)

    def test_surrender_and_no_rematch_in_cooldown(self):
        self.begin();self.act(self.atk,'yield')
        self.assertEqual(self.battle()['winner_id'],self.defender)
        self.client.post(f'/heirs/reclaim/{self.hid}')
        self.assertEqual(self.battle()['status'],'finished')

    def test_finished_action_cannot_change_result(self):
        self.begin();self.win(self.defender)
        before=dict(self.battle());energy=game.get_consort(self.atk)['energy']
        self.act(self.atk)
        self.assertEqual(dict(self.battle()),before)
        self.assertEqual(game.get_consort(self.atk)['energy'],energy)

    def test_loss_of_caretaker_and_restart(self):
        self.begin();self.act(self.atk);progress=self.battle()['challenger_progress']
        game.init_db()
        self.assertEqual(self.battle()['challenger_progress'],progress)
        game.run("UPDATE consorts SET status='dead' WHERE id=?",(self.defender,))
        game.custody_battle_tick(game.cur_day())
        self.assertEqual(self.child()['caretaker_id'],self.atk)
