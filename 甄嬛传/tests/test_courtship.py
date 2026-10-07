"""公主择婿、权限、每日次数、婚后事件与旧婚事兼容。"""
import unittest
from unittest.mock import patch
import test_adulthood

game = test_adulthood.game


class PrincessCourtshipTests(unittest.TestCase):
    setUp = test_adulthood.AdulthoodTests.setUp
    tearDown = test_adulthood.AdulthoodTests.tearDown
    player = test_adulthood.AdulthoodTests.player
    login = test_adulthood.AdulthoodTests.login
    heir = test_adulthood.AdulthoodTests.heir

    def princess(self, age=14, **kw):
        hid = self.heir(self.atk, gender='公主', born=game.cur_day() - age * game.HEIR_DAYS_PER_YEAR, **kw)
        game.heir_come_of_age(game.get_heir(hid), game.cur_day())
        return hid

    def candidates(self, hid):
        return game.q('SELECT * FROM princess_suitors WHERE heir_id=? AND active=1 ORDER BY id', (hid,))

    def act(self, hid, action, sid=0, **kw):
        return self.client.post(f'/heirs/courtship/{hid}', data=dict(action=action, suitor_id=sid, **kw), follow_redirects=True)

    def next_action(self, hid):
        game.run("DELETE FROM daily_counters WHERE consort_id=0 AND key=?", (f'courtship:{hid}',))
        game.run('UPDATE consorts SET energy=8,silver=1000 WHERE id=?', (self.atk,))

    def test_fourteen_opens_fixed_candidates_without_marriage(self):
        hid = self.princess()
        before = [dict(s) for s in self.candidates(hid)]
        game.ensure_courtship(game.get_heir(hid))
        self.assertEqual(len(before), 3)
        self.assertEqual(before, [dict(s) for s in self.candidates(hid)])
        self.assertEqual(game.get_heir(hid)['marriage'], 'choice')
        html = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('物色夫婿', html)
        self.assertIn(before[0]['name'], html)

    def test_daily_limit_is_shared_between_actions_and_parents(self):
        hid = self.princess()
        sid = self.candidates(hid)[0]['id']
        self.act(hid, 'investigate', sid)
        after = game.get_consort(self.atk)['silver']
        self.act(hid, 'meet', sid)
        self.assertEqual(game.get_consort(self.atk)['silver'], after)
        self.assertEqual(self.candidates(hid)[0]['met'], 0)

    def test_no_petition_before_sixteen_and_no_direct_marriage_bypass(self):
        hid = self.princess()
        sid = self.candidates(hid)[0]['id']
        game.run('UPDATE princess_suitors SET met=1 WHERE id=?', (sid,))
        self.act(hid, 'petition', sid)
        self.client.post(f'/heirs/marry/{hid}', data={'kind': 'capital'})
        self.assertEqual(game.get_heir(hid)['marriage'], 'choice')
        self.assertEqual(game.q('SELECT selected_id FROM princess_courtships WHERE heir_id=?', (hid,), one=True)['selected_id'], 0)

    def test_non_parent_and_foreign_candidate_cannot_be_used(self):
        hid, other = self.princess(), self.princess()
        wrong = self.candidates(other)[0]['id']
        self.act(hid, 'investigate', wrong)
        self.assertEqual(self.candidates(other)[0]['investigated'], 0)
        outsider = self.player('无关人')
        self.login(outsider)
        self.act(hid, 'investigate', self.candidates(hid)[0]['id'])
        self.assertEqual(self.candidates(hid)[0]['investigated'], 0)

    def test_repeat_meeting_does_not_charge_or_refresh(self):
        hid = self.princess()
        sid = self.candidates(hid)[0]['id']
        self.act(hid, 'meet', sid)
        attitude = self.candidates(hid)[0]['attitude']
        self.next_action(hid)
        self.act(hid, 'meet', sid)
        self.assertEqual(game.get_consort(self.atk)['silver'], 1000)
        self.assertEqual(self.candidates(hid)[0]['attitude'], attitude)

    def test_replace_retains_others_and_has_cooldown(self):
        hid = self.princess()
        ids = [s['id'] for s in self.candidates(hid)]
        self.act(hid, 'replace', ids[0])
        after = [s['id'] for s in self.candidates(hid)]
        self.assertEqual(len(after), 3)
        self.assertTrue(set(ids[1:]).issubset(after))
        self.next_action(hid)
        self.act(hid, 'replace', ids[1])
        self.assertEqual(after, [s['id'] for s in self.candidates(hid)])

    def test_petition_locks_then_wedding_keeps_old_benefit_removed(self):
        hid = self.princess(age=16, favor=100)
        sid = self.candidates(hid)[0]['id']
        game.run("UPDATE princess_suitors SET met=1,attitude='中意',kind='noble' WHERE id=?", (sid,))
        game.run('UPDATE consorts SET trust=100 WHERE id=?', (self.atk,))
        self.act(hid, 'petition', sid)
        self.next_action(hid)
        self.act(hid, 'replace', sid)
        self.assertIn(sid, [s['id'] for s in self.candidates(hid)])
        self.act(hid, 'wedding')
        self.assertEqual(game.get_heir(hid)['marriage'], 'choice')
        game.run('UPDATE princess_courtships SET betrothed_day=betrothed_day-1 WHERE heir_id=?', (hid,))
        self.act(hid, 'wedding', dowry='rich')
        self.assertEqual(game.get_heir(hid)['marriage'], 'capital')
        row = game.q('SELECT * FROM princess_courtships WHERE heir_id=?', (hid,), one=True)
        self.assertEqual((row['harmony'], row['dowry'], row['family_fortune']), (75, 300, 65))

    def test_no_deadline_for_player_and_auto_arrangement_without_manager(self):
        hid = self.princess(age=16)
        game.princess_courtship_tick(game.cur_day() + 20)
        self.assertEqual(game.get_heir(hid)['marriage'], 'choice')
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (self.atk,))
        game.princess_courtship_tick(game.cur_day())
        self.assertIn(game.get_heir(hid)['marriage'], ('capital', 'mongol'))

    def test_married_event_cannot_repeat_reward(self):
        hid = self.princess(age=16)
        sid = self.candidates(hid)[0]['id']
        game.run('UPDATE princess_courtships SET selected_id=? WHERE heir_id=?', (sid, hid))
        game.complete_princess_marriage(game.get_heir(hid))
        game.run("UPDATE princess_courtships SET event='aid' WHERE heir_id=?", (hid,))
        self.act(hid, 'help')
        before = game.q('SELECT family_fortune FROM princess_courtships WHERE heir_id=?', (hid,), one=True)[0]
        self.next_action(hid)
        self.act(hid, 'help')
        self.assertEqual(game.q('SELECT family_fortune FROM princess_courtships WHERE heir_id=?', (hid,), one=True)[0], before)

    def test_emperor_selects_best_when_recommendation_threshold_not_met(self):
        hid = self.princess(age=16, favor=0)
        suitors = self.candidates(hid)
        game.run('UPDATE consorts SET trust=0 WHERE id=?', (self.atk,))
        game.run('UPDATE princess_suitors SET virtue=20,study=20,met=1 WHERE heir_id=?', (hid,))
        game.run('UPDATE princess_suitors SET virtue=90,study=90 WHERE id=?', (suitors[1]['id'],))
        self.act(hid, 'petition', suitors[0]['id'])
        row = game.q('SELECT * FROM princess_courtships WHERE heir_id=?', (hid,), one=True)
        self.assertEqual(row['selected_id'], suitors[1]['id'])
        self.assertEqual(row['self_chosen'], 0)

    def test_married_events_create_one_letter_and_wait_for_handling(self):
        hid = self.princess(age=16)
        sid = self.candidates(hid)[0]['id']
        game.run('UPDATE princess_courtships SET selected_id=? WHERE heir_id=?', (sid, hid))
        game.complete_princess_marriage(game.get_heir(hid))
        day = game.cur_day() + 3
        before = game.q('SELECT COUNT(*) n FROM letters', one=True)['n']
        game.princess_courtship_tick(day)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters', one=True)['n'], before + 1)
        game.princess_courtship_tick(day)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters', one=True)['n'], before + 1)

    def test_birth_mother_can_investigate_but_cannot_replace_caretakers_choice(self):
        hid = self.princess(caretaker=self.tgt)
        sid = self.candidates(hid)[0]['id']
        self.act(hid, 'replace', sid)
        self.assertIn(sid, [s['id'] for s in self.candidates(hid)])
        self.act(hid, 'investigate', sid)
        self.assertEqual(self.candidates(hid)[0]['investigated'], 1)

    def test_insufficient_money_does_not_use_daily_opportunity(self):
        hid = self.princess()
        game.run('UPDATE consorts SET silver=0 WHERE id=?', (self.atk,))
        self.act(hid, 'meet', self.candidates(hid)[0]['id'])
        self.assertEqual(game.daily_count(0, f'courtship:{hid}'), 0)

if __name__ == '__main__':
    unittest.main()
