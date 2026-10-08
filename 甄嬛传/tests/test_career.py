"""皇子的志向：8 岁起选夺嫡 / 艺术家 / 科学家 / 皇商

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class CareerTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def prince(self, mother, age_years=9, **cols):
        day = game.cur_day()
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,health_max,health) VALUES(?,?,'皇子',9,?,100,80)",
                       (mother, mother, day - age_years * game.HEIR_DAYS_PER_YEAR)).lastrowid
        for k, v in cols.items(): game.run(f"UPDATE heirs SET {k}=? WHERE id=?", (v, hid))
        return hid

    def pick(self, hid, career):
        return self.client.post(f'/heirs/{hid}/career', data={'career': career})

    def test_can_pick_only_from_eight_for_own_prince(self):
        young = self.prince(self.atk, age_years=7)
        self.pick(young, 'artist')
        self.assertEqual(game.get_heir(young)['career'], '')
        ok = self.prince(self.atk, age_years=8)
        self.pick(ok, 'scientist')
        self.assertEqual(game.get_heir(ok)['career'], 'scientist')
        other = self.prince(self.tgt)
        self.pick(other, 'artist')
        self.assertEqual(game.get_heir(other)['career'], '', '不是自己抚养的孩子不能替他选')
        self.pick(ok, 'nonsense')
        self.assertEqual(game.get_heir(ok)['career'], 'scientist')

    def test_switching_resets_skill_and_throne_clears_career(self):
        hid = self.prince(self.atk)
        self.pick(hid, 'artist')
        game.run("UPDATE heirs SET career_skill=40 WHERE id=?", (hid,))
        self.pick(hid, 'merchant')
        self.assertEqual((game.get_heir(hid)['career'], game.get_heir(hid)['career_skill']), ('merchant', 0))
        self.pick(hid, 'throne')
        self.assertEqual(game.get_heir(hid)['career'], '')

    def test_training_costs_and_raises_skill_and_needs_a_career(self):
        hid = self.prince(self.atk)
        silver = game.get_consort(self.atk)['silver']
        self.client.post(f'/heirs/raise/{hid}', data={'opt': 'career'})
        self.assertEqual(game.get_heir(hid)['career_skill'], 0, '没选路不能钻研')
        self.pick(hid, 'artist')
        self.client.post(f'/heirs/raise/{hid}', data={'opt': 'career'})
        self.assertGreaterEqual(game.get_heir(hid)['career_skill'], game.CAREER_TRAIN_GAIN)
        self.assertEqual(game.get_consort(self.atk)['silver'], silver - game.CAREER_TRAIN_SILVER)

    def test_career_prince_is_not_a_rival_and_gets_no_title(self):
        hid = self.prince(self.atk, age_years=13)
        self.assertIn(hid, [h['id'] for h in game.rival_princes()])
        self.pick(hid, 'scientist')
        self.assertNotIn(hid, [h['id'] for h in game.rival_princes()])
        day = game.cur_day()
        game.run("UPDATE heirs SET born_day=? WHERE id=?", (day - game.HEIR_ADULT_AGE_DAYS - 1, hid))
        game.heir_adult_tick(day)
        h = game.get_heir(hid)
        self.assertTrue(h['adult_day'])
        self.assertEqual(h['title'], '', '选了路的皇子不封爵')
        self.assertEqual(h['ambition'], 0)

    def test_adult_career_prince_pays_nightly_and_produces_works(self):
        hid = self.prince(self.atk, age_years=14, career='artist', career_skill=80, adult_day=1)
        before = game.get_consort(self.atk)['silver']
        favor = game.get_consort(self.atk)['favor']
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_career_tick(1 + game.CAREER_WORK_INTERVAL)
        self.assertEqual(game.get_consort(self.atk)['silver'], before + game.career_income(game.get_heir(hid)))
        self.assertGreater(game.get_consort(self.atk)['favor'], favor, '艺术家出作品，抚养人圣宠上涨')
        self.assertEqual(game.get_heir(hid)['career_work_day'], 1 + game.CAREER_WORK_INTERVAL)

    def test_throne_prince_unaffected_by_career_tick(self):
        hid = self.prince(self.atk, age_years=14, adult_day=1, title='贝勒')
        before = game.get_consort(self.atk)['silver']
        game.heir_career_tick(10)
        self.assertEqual(game.get_consort(self.atk)['silver'], before)

    def test_heirs_page_renders_career_panel(self):
        hid = self.prince(self.atk)
        body = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('志向', body)
        self.pick(hid, 'artist')
        body = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('习画抚琴', body)
