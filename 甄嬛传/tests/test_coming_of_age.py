"""12 岁成年：一夜长成 16 岁，并随机得到一个不重复的长相

运行：python3 -m unittest discover -s tests -v
"""
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class ComingOfAgeTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def kid(self, mother, gender='皇子', age=12, **cols):
        day = game.cur_day()
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,health_max,health) VALUES(?,?,?,9,?,100,80)",
                       (mother, mother, gender, day - age / game.AGE_YEARS_PER_DAY)).lastrowid
        for k, v in cols.items(): game.run(f"UPDATE heirs SET {k}=? WHERE id=?", (v, hid))
        return hid

    def test_adult_age_is_twelve_and_jumps_to_sixteen(self):
        self.assertEqual((game.HEIR_ADULT_AGE_YEARS, game.HEIR_COMING_AGE), (12, 16))
        hid = self.kid(self.atk)
        self.assertEqual(game.heir_age_years(game.get_heir(hid)), 12)
        game.heir_adult_tick(game.cur_day())
        h = game.get_heir(hid)
        self.assertTrue(h['adult_day'])
        self.assertEqual(game.heir_age_years(h), game.HEIR_COMING_AGE)

    def test_not_adult_before_twelve(self):
        hid = self.kid(self.atk, age=11)
        game.heir_adult_tick(game.cur_day())
        self.assertEqual(game.get_heir(hid)['adult_day'], 0)

    def test_princess_can_petition_right_after_coming_of_age(self):
        hid = self.kid(self.atk, gender='公主')
        game.heir_adult_tick(game.cur_day())
        h = game.get_heir(hid)
        self.assertEqual(h['marriage'], 'choice')
        self.assertGreaterEqual(game.heir_age_years(h), 16)
        self.assertTrue(game.q('SELECT 1 FROM princess_courtships WHERE heir_id=?', (hid,), one=True))

    def test_prince_gets_a_male_look_princess_a_female_one(self):
        p, q_ = self.kid(self.atk), self.kid(self.atk, gender='公主')
        game.heir_adult_tick(game.cur_day())
        self.assertIn(game.get_heir(p)['look_ref'], game.HEIR_LOOKS['皇子'])
        self.assertIn(game.get_heir(q_)['look_ref'], game.HEIR_LOOKS['公主'])

    def test_look_never_repeats_a_consort_skin_or_another_childs_look(self):
        taken = game.HEIR_LOOKS['皇子'][:-1]
        for i, name in enumerate(taken):
            game.run("UPDATE consorts SET skin=? WHERE id=?", (name, self.atk if i == 0 else self.tgt)) if False else None
        game.run("UPDATE consorts SET skin=? WHERE id=?", (game.HEIR_LOOKS['皇子'][0], self.atk))
        looks = set()
        for _ in range(len(game.HEIR_LOOKS['皇子']) - 1):
            hid = self.kid(self.tgt)
            game.heir_adult_tick(game.cur_day())
        got = [r['look_ref'] for r in game.q("SELECT look_ref FROM heirs WHERE look_ref!=''")]
        self.assertEqual(len(got), len(set(got)), '孩子之间不重复')
        self.assertNotIn(game.HEIR_LOOKS['皇子'][0], got, '不和妃嫔的皮相重复')
        extra = self.kid(self.tgt)
        game.heir_adult_tick(game.cur_day())
        self.assertEqual(game.get_heir(extra)['look_ref'], '', '名单用光了就先空着')

    def test_consort_cannot_take_a_childs_look_as_skin(self):
        hid = self.kid(self.atk)
        game.heir_adult_tick(game.cur_day())
        look = game.get_heir(hid)['look_ref']
        self.client.post('/skin', data={'skin': look})
        self.assertEqual(game.get_consort(self.atk)['skin'], '')

    def test_gazette_announces_the_look_at_the_moment_of_coming_of_age(self):
        hid = self.kid(self.atk)
        game.heir_adult_tick(game.cur_day())
        look = game.get_heir(hid)['look_ref']
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE ?", ('%成年，眉眼长开了%' + look + '%',), one=True))

    def test_gazette_announces_when_a_consort_sets_a_skin(self):
        self.client.post('/skin', data={'skin': '某某某'})
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%皮相定下了：像某某某%'", one=True))
        before = game.q("SELECT COUNT(*) n FROM gazette", one=True)['n']
        self.client.post('/skin', data={'skin': ''})
        self.assertEqual(game.q("SELECT COUNT(*) n FROM gazette", one=True)['n'], before, '清空不发公告')

    def test_heirs_page_shows_the_look(self):
        hid = self.kid(self.atk)
        game.heir_adult_tick(game.cur_day())
        body = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('像' + game.get_heir(hid)['look_ref'], body)


class EmperorLookTests(ComingOfAgeTests):
    def test_new_emperor_keeps_his_look_and_losers_are_cleared(self):
        boss = self.kid(self.tgt, age=16, adult_day=1, look_ref=game.HEIR_LOOKS['皇子'][0], name='承稷')
        loser = self.kid(self.atk, age=16, adult_day=1, look_ref=game.HEIR_LOOKS['皇子'][1])
        from unittest.mock import patch
        with patch.object(game, 'choose_successor', return_value=game.get_heir(boss)):
            game.end_reign(game.cur_day())
        self.assertEqual(game.state()['emperor_look'], game.HEIR_LOOKS['皇子'][0])
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs', one=True)['n'], 0, '王爷公主的长相随孩子一起清空')
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE ?", ('%新帝眉眼像' + game.HEIR_LOOKS['皇子'][0] + '%',), one=True))

    def test_sons_cannot_repeat_the_emperors_look(self):
        emperor_look = game.HEIR_LOOKS['皇子'][0]
        game.run("UPDATE game_state SET emperor_look=?", (emperor_look,))
        got = []
        for _ in range(len(game.HEIR_LOOKS['皇子'])):
            hid = self.kid(self.tgt)
            game.heir_adult_tick(game.cur_day())
        got = [r['look_ref'] for r in game.q("SELECT look_ref FROM heirs WHERE look_ref!=''")]
        self.assertNotIn(emperor_look, got)
        self.assertEqual(len(got), len(game.HEIR_LOOKS['皇子']) - 1, '其余的名字都分得出去，唯独皇帝那个留着')

    def test_consort_cannot_take_the_emperors_look_as_skin(self):
        game.run("UPDATE game_state SET emperor_look=?", (game.HEIR_LOOKS['公主'][0],))
        self.client.post('/skin', data={'skin': game.HEIR_LOOKS['公主'][0]})
        self.assertEqual(game.get_consort(self.atk)['skin'], '')
