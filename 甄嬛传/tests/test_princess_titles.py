import unittest
from unittest.mock import patch
import test_coming_of_age as fixtures

game = fixtures.game

class PrincessTitlesTests(fixtures.ComingOfAgeTests):
    def test_visits_gain_and_daily_limit(self):
        hid = self.kid(self.atk, gender='公主', age=5, emperor_affinity=37)
        before = game.get_consort(self.atk)['energy']
        with patch.object(game.random, 'randint', return_value=3):
            self.client.post(f'/heirs/{hid}/emperor-visit')
        h = game.get_heir(hid)
        self.assertEqual(h['emperor_affinity'], 40)
        self.assertTrue(h['title'].startswith('和硕'))
        self.assertTrue(h['princess_epithet'])
        self.assertEqual(game.get_consort(self.atk)['energy'], before - 1)
        self.assertEqual(game.daily_count(self.atk, f'empvisit:{hid}'), 1)

    def test_up_to_four_visits_a_day_each_costing_one_energy(self):
        hid = self.kid(self.atk, gender='公主', age=5)
        game.run('UPDATE consorts SET energy=9 WHERE id=?', (self.atk,))
        game.run('UPDATE heirs SET emperor_affinity=0 WHERE id=?', (hid,))
        for _ in range(game.PRINCESS_VISIT_DAILY + 2):
            self.client.post(f'/heirs/{hid}/emperor-visit')
        self.assertEqual(game.daily_count(self.atk, f'empvisit:{hid}'), game.PRINCESS_VISIT_DAILY)
        self.assertEqual(game.get_consort(self.atk)['energy'], 9 - game.PRINCESS_VISIT_DAILY, '第 5、6 次被拒，不扣精力')
        self.assertIn(f'{game.PRINCESS_VISIT_DAILY}/{game.PRINCESS_VISIT_DAILY}', self.client.get('/heirs').get_data(as_text=True))

    def test_promotion_keeps_epithet_and_marriage_does_not_confer(self):
        hid = self.kid(self.atk, gender='公主', emperor_affinity=40)
        game.confer_princess(game.get_heir(hid))
        epithet = game.get_heir(hid)['princess_epithet']
        game.run('UPDATE heirs SET emperor_affinity=80 WHERE id=?', (hid,))
        game.confer_princess(game.get_heir(hid))
        self.assertEqual(game.get_heir(hid)['title'], '固伦'+epithet+'公主')
        other = self.kid(self.atk, gender='公主')
        game.marry_off(game.get_heir(other), 'mongol', False)
        self.assertEqual(game.get_heir(other)['title'], '')

    def test_cannot_visit_someone_elses_child(self):
        hid = self.kid(self.tgt, gender='公主', age=5)
        before = game.get_consort(self.atk)['energy']
        self.client.post(f'/heirs/{hid}/emperor-visit')
        self.assertEqual(game.get_heir(hid)['emperor_affinity'], 0)
        self.assertEqual(game.get_consort(self.atk)['energy'], before)

    def test_names_unique_within_reign_and_emperor_forbidden(self):
        hid = self.kid(self.atk, gen_word='弘', name_choices='历')
        game.run("UPDATE game_state SET emperor_name='弘历'")
        self.client.post('/heirs', data={'heir_id':hid,'pick':'历'})
        self.assertEqual(game.get_heir(hid)['name'], '')
        game.run("UPDATE heirs SET name_choices='昀' WHERE id=?", (hid,))
        self.kid(self.tgt, name='弘昀', gen_word='弘')
        self.client.post('/heirs', data={'heir_id':hid,'pick':'昀'})
        self.assertEqual(game.get_heir(hid)['name'], '')
        self.assertNotIn('昀', game.get_heir(hid)['name_choices'])

    def test_history_thresholds(self):
        for gender, title, expected in [('公主','',False),('公主','和硕淑慎公主',True),('皇子','贝勒',False),('皇子','郡王',True),('皇子','亲王',True)]:
            hid=self.kid(self.atk, gender=gender, title=title)
            self.assertEqual(game.heir_history_eligible(game.get_heir(hid)), expected)

    def test_history_only_titled_and_winner_allies(self):
        import json
        winner = self.kid(self.atk, age=16, adult_day=1, name='弘胜')
        ally = self.kid(self.atk, age=16, adult_day=1, name='弘助', title='贝子', favor=0)
        omitted = self.kid(self.atk, gender='公主', age=5, name='璟无')
        included = self.kid(self.atk, gender='公主', age=5, name='璟荣', title='和硕淑慎公主')
        game.run('INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,?)', (ally,winner,game.cur_day()))
        with patch.object(game, 'choose_successor', return_value=game.get_heir(winner)):
            game.end_reign(game.cur_day())
        edict = '\n'.join(json.loads(game.q('SELECT edict FROM reigns ORDER BY id DESC LIMIT 1',one=True)['edict']))
        self.assertIn('弘助', edict)
        self.assertIn('晋封亲王', edict)
        self.assertIn('璟荣', edict)
        self.assertNotIn('璟无', edict)
