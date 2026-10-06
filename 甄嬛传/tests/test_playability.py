"""统一时间线、自由日常与成长补偿的行为回归。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class PlayabilityTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_exhausted_player_can_greet_and_visit_once(self):
        third = self.player('丙')
        game.run('UPDATE consorts SET energy=0 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=.99):
            self.client.post('/act/greet')
        self.assertEqual(game.daily_count(self.atk, 'greet'), 1)
        self.client.post('/act/visit', data={'target_id': self.tgt})
        self.assertGreater(game.relation(self.atk, self.tgt)['affinity'], 0)
        self.client.post('/act/visit', data={'target_id': third})
        self.assertEqual(game.daily_count(self.atk, 'visit'), 1)
        self.assertEqual(game.get_consort(self.atk)['energy'], 0)

    def test_invalid_visit_does_not_consume_free_visit(self):
        self.client.post('/act/visit', data={'target_id': 999999})
        self.assertEqual(game.action_config(game.get_consort(self.atk), 'visit')['energy'], 0)
        self.client.post('/act/visit', data={'target_id': self.tgt})
        self.assertEqual(game.action_config(game.get_consort(self.atk), 'visit')['energy'], 1)

    def test_study_provides_progress_without_matching_preference(self):
        game.run("UPDATE game_state SET emperor_pref='琴'")
        before = game.get_consort(self.atk)['favor']
        self.client.post('/act/study', data={'art': '画'})
        self.assertEqual(game.get_consort(self.atk)['favor'], before + round(game.STUDY_FAVOR_GAIN * (1.1 if game.get_consort(self.atk)['personality']=='gentle' else 1)))

    def test_unseen_player_precedes_favored_recent_player(self):
        game.run('UPDATE consorts SET last_audience_day=9,trust=100 WHERE id=?', (self.atk,))
        game.run('UPDATE consorts SET last_audience_day=5,trust=0 WHERE id=?', (self.tgt,))
        pool = [game.get_consort(self.atk), game.get_consort(self.tgt)]
        self.assertEqual(game.pick_audience(pool, 10)['id'], self.tgt)

    def test_pregnancy_pity_counts_only_effective_attempts_and_resets(self):
        with patch.object(game.random, 'random', return_value=.99):
            for i in range(11):
                game.do_bedding(game.get_consort(self.atk), 10+i//2, False, [])
                self.assertEqual(game.get_consort(self.atk)['pregnant_since'], 0)
            game.do_bedding(game.get_consort(self.atk), 15, False, [])
        c = game.get_consort(self.atk)
        self.assertEqual(c['pregnant_since'], 15)
        self.assertEqual(c['pregnancy_misses'], 0)

    def test_pity_does_not_bypass_fertility_age_limit(self):
        game.run('UPDATE consorts SET age_months=540,pregnancy_misses=3 WHERE id=?', (self.atk,))
        self.assertEqual(game.pregnancy_chance(game.get_consort(self.atk)), 0)

    def test_favored_player_can_make_hobby_with_no_energy(self):
        game.run('UPDATE consorts SET energy=0,favor=500 WHERE id=?', (self.atk,))
        self.client.post('/hobby/start', data={'kind': 'flower', 'style': 0})
        self.assertIsNotNone(game.current_hobby_project(self.atk))
        self.client.post('/hobby/act')
        self.assertEqual(game.current_hobby_project(self.atk)['stage'], 1)
        self.client.post('/hobby/act')   # 一天可以打理好几次，第二步就做成了
        self.assertIsNone(game.current_hobby_project(self.atk))
        self.assertEqual(game.get_consort(self.atk)['energy'], 0, '雅趣不占精力')

    def test_family_emperor_consort_and_child_share_growth_rate(self):
        game.run('UPDATE game_state SET day=1,reign_start_day=1')
        game.run('UPDATE consorts SET age_months=216,entered_day=1 WHERE id=?', (self.atk,))
        uid = game.get_consort(self.atk)['user_id']
        game.create_family(uid, '测试', next(iter(game.FAMILIES)))
        before_head = game.family_row(uid)['head_age_months']
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,zhuazhou) VALUES(?,?,'皇子',7,0,'book')", (self.atk,self.atk)).lastrowid
        before_emperor = game.emperor_age_years()
        before_child = game.heir_age_years(game.q('SELECT * FROM heirs WHERE id=?',(hid,),one=True))
        with patch.object(game.random, 'random', return_value=.99), patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(game.emperor_age_years()-before_emperor, 2)
        self.assertEqual(game.get_consort(self.atk)['age_months']-216,24)
        self.assertEqual(game.family_row(uid)['head_age_months']-before_head,24)
        self.assertEqual(game.heir_age_years(game.q('SELECT * FROM heirs WHERE id=?',(hid,),one=True))-before_child,2)

    def test_newborn_can_reach_succession_and_adulthood_in_fifteen_days(self):
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,zhuazhou) VALUES(?,?,'皇子',7,3,'book')", (self.atk,self.atk)).lastrowid
        h = game.q('SELECT * FROM heirs WHERE id=?',(hid,),one=True)
        self.assertEqual(game.heir_age_years(h,9),12)
        self.assertEqual(game.heir_age_years(h,10),14)
        game.run('UPDATE game_state SET day=10')
        game.heir_adult_tick(10)
        self.assertEqual(game.q('SELECT adult_day FROM heirs WHERE id=?',(hid,),one=True)['adult_day'],10)

    def test_new_field_migration_is_idempotent(self):
        game.init_db()
        game.run('UPDATE consorts SET pregnancy_misses=2 WHERE id=?',(self.atk,))
        game.init_db()
        self.assertEqual(game.get_consort(self.atk)['pregnancy_misses'],2)

    def test_successor_keeps_his_actual_age(self):
        game.run('UPDATE game_state SET day=15')
        game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,zhuazhou) VALUES(?,?,'皇子',7,3,'book')", (self.atk,self.atk))
        game.end_reign(15)
        self.assertEqual(game.state()['emperor_start_age'],24)

    def test_fourteen_year_adulthood_boundary_and_last_day_window(self):
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,zhuazhou) VALUES(?,?,'皇子',7,8,'book')", (self.atk,self.atk)).lastrowid
        game.run('UPDATE game_state SET day=14')
        game.heir_adult_tick(14)
        self.assertEqual(game.q('SELECT adult_day FROM heirs WHERE id=?',(hid,),one=True)['adult_day'],0)
        game.run('UPDATE game_state SET day=15')
        game.heir_adult_tick(15)
        self.assertEqual(game.q('SELECT adult_day FROM heirs WHERE id=?',(hid,),one=True)['adult_day'],15)
        self.assertEqual(game.HEIR_ADULT_AGE_YEARS,14)
