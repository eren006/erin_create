"""空后宫、东宫身份和 NPC 养育所的现行规则。"""
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game

class EmptyCourtTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def test_no_presets_even_after_restart(self):
        self.assertEqual(game.q('SELECT COUNT(*) n FROM consorts WHERE npc_key IS NOT NULL', one=True)['n'], 0)
        self.assertEqual(len(game.q('SELECT * FROM heirs')), 0)
        game.init_db()
        self.assertEqual(len(game.npcs_for_reign(3)), 0)
        self.assertEqual(game.state()['emperor_start_age'], 20)
        self.assertFalse(game.NPC_SCENES)
        self.assertTrue(all(q['key'] != 'huafei' for q in game.DIANXUAN_QUESTIONS))

    def test_low_rank_enters_nursery_not_an_existing_consort(self):
        game.run('UPDATE consorts SET rank=3 WHERE id=?', (self.atk,))
        hid = self.heir(self.atk, born=9)
        game.heir_growth_tick(10)
        self.assertEqual(self.row(hid)['caretaker_id'], 0)
        page = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('皇嗣养育所（NPC）', page)
        self.assertNotIn('申请领养', page)
        self.assertEqual(self.client.post(f'/succession/claim/{hid}').status_code, 302)
        self.assertFalse(game.q('SELECT * FROM heir_claims'))

    def test_nursery_grows_without_claim_and_adulthood_works(self):
        hid = self.heir(self.atk, caretaker=0, born=3, zhuazhou='book')
        before = self.row(hid)['study']
        game.heir_orphan_tick(9)
        self.assertEqual(self.row(hid)['study'], before + 2)
        game.heir_adult_tick(10)
        self.assertEqual(self.row(hid)['adult_day'], 10)
        self.assertEqual(game.heir_age_years(self.row(hid), 10), 14)

    def test_eligible_other_player_adopts_at_settlement(self):
        hid = self.heir(self.tgt, caretaker=0, born=9, zhuazhou='book')
        self.client.post(f'/succession/claim/{hid}')
        self.assertEqual(self.row(hid)['caretaker_id'], 0)
        game.init_db()  # Restart must preserve valid pending applications.
        game.heir_orphan_tick(10)
        self.assertEqual(self.row(hid)['caretaker_id'], self.atk)
        self.assertFalse(game.q('SELECT * FROM heir_claims'))

    def test_promoted_mother_reclaims_without_random_failure(self):
        hid = self.heir(self.atk, caretaker=0, born=9, zhuazhou='book')
        game.run('UPDATE consorts SET rank=4 WHERE id=?', (self.atk,))
        self.client.post(f'/heirs/reclaim/{hid}')
        self.assertEqual(self.row(hid)['caretaker_id'], 0)
        game.run('UPDATE consorts SET rank=5 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=.99):
            self.client.post(f'/heirs/reclaim/{hid}')
        self.assertEqual(self.row(hid)['caretaker_id'], self.atk)

    def test_nursery_visit_preserves_mother_affinity(self):
        hid = self.heir(self.atk, caretaker=0, born=9, zhuazhou='book')
        self.client.post(f'/heirs/visit/{hid}')
        self.assertEqual(self.row(hid)['mother_affinity'], 54)

    def test_expired_claim_cannot_take_an_adult(self):
        hid = self.heir(self.tgt, caretaker=0, born=3, zhuazhou='book')
        self.client.post(f'/succession/claim/{hid}')
        self.assertFalse(game.q('SELECT * FROM heir_claims'))

    def create_entrant(self, name, draw):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name,'test')).lastrowid
        game.create_family(uid, name, next(iter(game.FAMILIES)))
        with self.client.session_transaction() as sess: sess['uid'] = uid
        with patch.object(game.random, 'random', return_value=draw), patch.object(game.random,'randint',side_effect=lambda lo,hi:(lo+hi)//2):
            self.client.post('/create', data=dict(given='新人',age=20,personality=next(iter(game.PERSONALITIES))))
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        return uid, c

    def test_old_companion_bonus_is_small_and_same_rank(self):
        entries=[]
        for name, draw in [('戊',0),('己',.99)]:
            uid,c=self.create_entrant(name,draw)
            with patch.object(game.random,'randint',return_value=0), patch.object(game.random,'choice',side_effect=lambda seq:seq[0]):
                self.client.post('/dianxuan',data={q['key']:0 for q in game.dianxuan_questions_for(c['id'])})
            entries.append(game.get_consort(c['id']))
        old,new=entries
        self.assertEqual(old['entry_origin'],'east_palace')
        self.assertEqual(new['entry_origin'],'new')
        self.assertEqual(old['favor']-new['favor'],10)
        self.assertEqual(old['trust']-new['trust'],5)
        self.assertEqual(old['rank'],new['rank'])
        self.assertEqual(old['silver'],new['silver'])

    def test_account_cannot_reroll_identity(self):
        uid,c=self.create_entrant('庚',.99)
        game.run('DELETE FROM consorts WHERE id=?',(c['id'],))
        with patch.object(game.random,'random',return_value=0):
            self.client.post('/create',data=dict(given='再入',age=20,personality=next(iter(game.PERSONALITIES))))
        self.assertEqual(game.q('SELECT entry_origin FROM consorts WHERE user_id=?',(uid,),one=True)[0],'new')

    def test_no_heir_reign_transition_stays_empty(self):
        game.end_reign(15)
        self.assertEqual(game.state()['reign_no'],2)
        self.assertFalse(game.q('SELECT * FROM heirs'))
        self.assertFalse(game.q('SELECT * FROM consorts WHERE npc_key IS NOT NULL'))

    def test_legacy_npc_scene_is_cleared_on_restart(self):
        game.run('UPDATE consorts SET pending_scene=? WHERE id=?', ('{"key":"garden_huafei"}', self.atk))
        game.init_db()
        self.assertFalse(game.get_consort(self.atk)['pending_scene'])

    def test_multiple_claims_assign_only_one_caretaker(self):
        hid = self.heir(self.tgt, caretaker=0, born=9, zhuazhou='book')
        other = self.player('辛', rank=6)
        for cid in (self.atk, other):
            self.login(cid)
            self.client.post(f'/succession/claim/{hid}')
        game.heir_orphan_tick(10)
        self.assertIn(self.row(hid)['caretaker_id'], (self.atk, other))
        self.assertFalse(game.q('SELECT * FROM heir_claims'))

    def test_restart_preserves_player_audience_scene(self):
        game.run('UPDATE consorts SET pending_scene=? WHERE id=?', ('{"key":"audience","prompt":0}', self.atk))
        game.init_db()
        self.assertEqual(game.get_scene(game.get_consort(self.atk))['key'], 'audience')
