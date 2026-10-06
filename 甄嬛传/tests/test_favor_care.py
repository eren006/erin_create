"""圣宠待遇：收入、风险与医疗时长。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game
class FavorCareTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def set_care(self,favor,streak=2):
        game.run('UPDATE consorts SET favor=?,unfavored_days=?,health=60 WHERE id=?',(favor,streak,self.atk))
        return game.get_consort(self.atk)

    def test_income_tiers_for_guiren(self):
        game.run('UPDATE consorts SET rank=4 WHERE id=?',(self.atk,))
        self.assertEqual(game.favor_stipend(self.set_care(150)),127)
        self.assertEqual(game.favor_stipend(self.set_care(40)),75)
        self.assertEqual(game.favor_stipend(self.set_care(39)),52)
        self.assertEqual(game.favor_stipend(self.set_care(0,1)),75)

    def test_newcomer_protection_and_cold_palace(self):
        c=self.set_care(0)
        game.run('UPDATE consorts SET entered_day=9 WHERE id=?',(self.atk,));c=game.get_consort(self.atk)
        self.assertEqual(game.favor_care_tier(c),'normal')
        self.assertEqual(game.ordinary_illness_chance(c,10),0)
        game.run("UPDATE consorts SET status='cold' WHERE id=?",(self.atk,))
        self.assertEqual(game.favor_stipend(game.get_consort(self.atk)),0)

    def test_base_illness_risk_and_recovery_protection(self):
        for favor,prob in [(150,.02),(40,.03),(0,.05)]:
            self.assertEqual(game.ordinary_illness_chance(self.set_care(favor),10),prob)
        game.run('UPDATE consorts SET protected_until_day=10 WHERE id=?',(self.atk,))
        self.assertEqual(game.ordinary_illness_chance(game.get_consort(self.atk),10),0)

    def test_hot_automatic_doctor_and_fast_recovery(self):
        self.set_care(150);silver=game.get_consort(self.atk)['silver']
        game.fall_ill(self.atk,10,'风寒')
        c=game.get_consort(self.atk);self.assertEqual(c['ill_treatment'],1)
        self.assertEqual(c['silver'],silver)
        game.run('UPDATE consorts SET health=20 WHERE id=?',(self.atk,))
        with patch.object(game.random,'random',return_value=.97):game.resolve_illness_crises(11)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])
        self.assertEqual(game.get_consort(self.atk)['health'],50)

    def test_low_treated_recovers_after_two_nights(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        self.client.post(f'/treat/{self.atk}')
        with patch.object(game.random,'random',return_value=.79):
            game.resolve_illness_crises(11)
            self.assertTrue(game.get_consort(self.atk)['ill_day'])
            game.resolve_illness_crises(12)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_untreated_low_risk_and_sister_paid_treatment(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        game.add_affinity(self.tgt,self.atk,50)
        self.login(self.tgt);silver=game.get_consort(self.tgt)['silver']
        self.client.post(f'/treat/{self.atk}')
        self.assertEqual(game.get_consort(self.tgt)['silver'],silver-game.treat_cost(game.get_consort(self.atk)))
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'],1)
        with patch.object(game.random,'random',return_value=.81):game.resolve_illness_crises(12)
        self.assertEqual(game.get_consort(self.atk)['status'],'dead')

    def test_untreated_low_dies_next_night(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        with patch.object(game.random,'random',return_value=.21):game.resolve_illness_crises(11)
        self.assertEqual(game.get_consort(self.atk)['status'],'dead')

    def test_regaining_favor_upgrades_ongoing_care(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒');self.set_care(150)
        with patch.object(game.random,'random',return_value=.97):game.resolve_illness_crises(11)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_income_streak_grace_then_recovers(self):
        self.set_care(0,0)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['unfavored_days'],1)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.favor_care_tier(game.get_consort(self.atk)),'low')
        self.set_care(80)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['unfavored_days'],0)

    def test_pages_explain_income_and_care(self):
        self.set_care(150)
        for path in ('/','/help'):
            r=self.client.get(path)
            self.assertEqual(r.status_code,200)
            self.assertIn('待遇',r.get_data(as_text=True))

    def test_hot_regained_before_doctor_visit_is_free(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒');self.set_care(150)
        silver=game.get_consort(self.atk)['silver']
        self.client.post(f'/treat/{self.atk}')
        self.assertEqual(game.get_consort(self.atk)['silver'],silver)
        self.assertEqual(game.get_consort(self.atk)['ill_care'],'hot')
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'],1)
