"""登基后重开：家族退回家族池，新一届从 3 个随机家族里挑；名望高的家族殿选有机会直接封嫔

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class FamilyPoolTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login

    def uid(self, cid): return game.get_consort(cid)['user_id']

    def test_archive_keeps_prestige_and_estate_in_the_pool(self):
        u = self.uid(self.atk)
        game.create_family(u, '甲', 'dali')
        game.run("UPDATE families SET prestige=150, estate=321 WHERE user_id=?", (u,))
        game.archive_families()
        self.assertIsNone(game.family_row(u))
        p = game.q("SELECT * FROM family_pool WHERE surname='甲'", one=True)
        self.assertEqual((p['prestige'], p['estate'], p['tier']), (150, 321, 'dali'))

    def test_end_reign_sends_every_family_to_the_pool(self):
        u = self.uid(self.atk)
        game.create_family(u, '乙', 'jizhou')
        game.run("UPDATE families SET prestige=40 WHERE user_id=?", (u,))
        game.end_reign(game.cur_day())
        self.assertIsNone(game.family_row(u))
        self.assertEqual(game.q("SELECT prestige FROM family_pool WHERE surname='乙'", one=True)['prestige'], 40)

    def test_offers_are_three_stable_and_can_include_pool_families(self):
        u = 9999
        for i, name in enumerate('丙丁戊己'):
            game.run("INSERT INTO family_pool(surname,tier,background,prestige) VALUES(?,?,?,?)", (name, 'dali', f'某地{name}', 100 + i))
        game.run("UPDATE game_state SET reign_no=2")
        with patch.object(game.random, 'random', return_value=0.0):      # 全部从池子里抽
            first = game.ensure_family_offers(u)
        self.assertEqual(len(first), 3)
        self.assertTrue(all(o['from_pool'] for o in first))
        again = game.ensure_family_offers(u)
        self.assertEqual([o['id'] for o in first], [o['id'] for o in again], '刷新页面不换候选')
        with patch.object(game.random, 'random', return_value=0.99):      # 全部新立
            fresh = game.ensure_family_offers(10000)
        self.assertEqual(len(fresh), 3)
        self.assertTrue(all(not o['from_pool'] and o['prestige'] == 0 for o in fresh))
        self.assertEqual(len({o['surname'] for o in fresh}), 3)

    def test_taking_a_pool_family_brings_back_its_prestige_and_removes_it_from_the_pool(self):
        u = self.uid(self.atk)
        game.run("INSERT INTO family_pool(surname,tier,background,prestige,estate,head_name,head_age_months) VALUES('庚','general','边关某将门',130,50,'庚大',600)")
        game.run("UPDATE game_state SET reign_no=2")
        with patch.object(game.random, 'random', return_value=0.0):
            offers = game.ensure_family_offers(u)
        pick = next(o for o in offers if o['surname'] == '庚')
        self.assertIsNone(game.take_family_offer(u, pick['id']))
        fam = game.family_row(u)
        self.assertEqual((fam['surname'], fam['prestige'], fam['estate'], fam['head_name']), ('庚', 130, 50, '庚大'))
        self.assertIsNone(game.q("SELECT 1 FROM family_pool WHERE surname='庚'", one=True))
        self.assertEqual(game.q("SELECT COUNT(*) n FROM family_offers WHERE user_id=?", (u,), one=True)['n'], 0)

    def test_a_family_picked_by_someone_else_cannot_be_taken(self):
        a, b = self.uid(self.atk), self.uid(self.tgt)
        game.run("INSERT INTO family_pool(surname,tier,background,prestige) VALUES('辛','dali','某某',90)")
        game.run("UPDATE game_state SET reign_no=2")
        with patch.object(game.random, 'random', return_value=0.0):
            oa = next(o for o in game.ensure_family_offers(a) if o['surname'] == '辛')
            ob = next(o for o in game.ensure_family_offers(b) if o['surname'] == '辛')
        self.assertIsNone(game.take_family_offer(a, oa['id']))
        self.assertIn('被别人选走', game.take_family_offer(b, ob['id']))

    def test_create_page_shows_offers_after_the_first_reign_and_picking_works(self):
        game.run("UPDATE game_state SET reign_no=2")
        game.run("DELETE FROM consorts WHERE id=?", (self.atk,))
        game.run("DELETE FROM families")
        self.login(self.tgt)
        game.run("UPDATE consorts SET status='dead', archived_user_id=user_id, user_id=NULL WHERE id=?", (self.tgt,))
        uid = game.q("SELECT archived_user_id u FROM consorts WHERE id=?", (self.tgt,), one=True)['u']
        with self.client.session_transaction() as s: s['uid'] = uid
        body = self.client.get('/create').get_data(as_text=True)
        self.assertIn('挑一户人家', body)
        offer = game.q("SELECT * FROM family_offers WHERE user_id=? ORDER BY id", (uid,), one=True)
        self.client.post('/create', data={'step': 'pick_family', 'offer_id': offer['id']})
        self.assertEqual(game.family_row(uid)['surname'], offer['surname'])

    def test_pin_chance_only_for_high_prestige_and_capped(self):
        self.assertEqual(game.pin_chance(79), 0.0)
        self.assertAlmostEqual(game.pin_chance(80), game.PIN_CHANCE_BASE)
        self.assertGreater(game.pin_chance(160), game.pin_chance(100))
        self.assertEqual(game.pin_chance(9999), game.PIN_CHANCE_MAX)


if __name__ == '__main__':
    unittest.main()
