import unittest
import test_lifecycle as fixtures

game=fixtures.game

class CareerSecretTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def test_confession_cannot_change_secret_or_stats(self):
        game.run("UPDATE consorts SET secret='lover' WHERE id=?",(self.atk,))
        before=tuple(game.get_consort(self.atk))
        self.client.post('/confess')
        self.assertEqual(tuple(game.get_consort(self.atk)),before)
        page=self.client.get('/').get_data(as_text=True)
        self.assertTrue('action="/confess"' not in page)

    def test_merchant_uses_commercial_titles_and_explicit_entry(self):
        uid=game.get_consort(self.atk)['user_id']
        game.create_family(uid,'测试商家','merchant')
        fam=game.family_row(uid)
        self.assertNotIn('品',game.family_career_title(fam,7))
        self.client.post('/family/enter_civil')
        self.assertEqual(game.family_row(uid)['career_path'],'')
        game.run('UPDATE families SET head_office=4,prestige=20 WHERE user_id=?',(uid,))
        before=game.get_consort(self.atk)
        self.client.post('/family/enter_civil')
        fam=game.family_row(uid)
        self.assertEqual(fam['career_path'],'civil')
        self.assertEqual(fam['head_office'],1)
        self.assertEqual(game.get_consort(self.atk)['silver'],before['silver']-200)
        self.client.post('/family/enter_civil')
        self.assertEqual(game.get_consort(self.atk)['silver'],before['silver']-200)

    def test_all_types_have_distinct_tracks(self):
        for tier in game.FAMILIES:
            fam={'tier':tier,'career_path':'','head_office':game.TIER_OFFICE[tier]}
            self.assertTrue(game.family_career_title(fam))
            self.assertEqual(len(game.FAMILY_CAREER_TITLES[tier]),10)
