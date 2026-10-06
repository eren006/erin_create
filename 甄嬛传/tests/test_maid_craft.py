"""宫人闲时做的小东西"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class MaidCraftTests(unittest.TestCase):
    def setUp(self):
        fixtures.LifecycleTests.setUp(self)
        game.MAID_CRAFT_MAX = 0.35      # 本文件专门测做东西，把概率上限开回来

    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def maid(self, trait, loyalty=70, owner=None):
        return game.run('INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,?,?,1,0)',
                        (owner or self.atk, '春桃', trait, loyalty)).lastrowid

    def me(self): return game.get_consort(self.atk)

    def upkeep(self, roll=0.0):
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=roll):
            game.maid_upkeep(game.cur_day())

    def test_chance_curve(self):
        self.assertEqual(game.maid_craft_chance(39), 0)
        self.assertAlmostEqual(game.maid_craft_chance(40), 0.12)
        self.assertAlmostEqual(game.maid_craft_chance(70), 0.12 + 30 * 0.003)
        self.assertLessEqual(game.maid_craft_chance(100), 0.35)

    def test_each_trait_makes_its_own_thing(self):
        expect = {'shouqiao': 'xiangnang', 'zhonghou': 'dianxin', 'jiling': 'tiseng', 'zuijin': 'hebao'}
        for trait, key in expect.items():
            game.run('DELETE FROM maids'); game.run('DELETE FROM inventory')
            self.maid(trait)
            self.upkeep()
            self.assertEqual(game.inv_qty(self.atk, key), 1, trait)

    def test_tancai_pays_a_little_silver_and_suizui_brings_gossip(self):
        self.player('丙')
        self.maid('tancai')
        before = 500
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.maid_upkeep(game.cur_day())
        gain = self.me()['silver'] - (before - game.MAID_WAGE)
        self.assertTrue(5 <= gain <= 12, gain)
        game.run('DELETE FROM maids')
        self.maid('suizui')
        self.upkeep()
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%听来一桩事%'", (self.atk,), one=True))

    def test_nothing_when_roll_misses_low_loyalty_sick_or_confined(self):
        self.maid('shouqiao'); self.upkeep(roll=0.99)
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0)
        game.run('DELETE FROM maids'); self.maid('shouqiao', loyalty=30); self.upkeep()
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0)
        game.run('DELETE FROM maids'); mid = self.maid('shouqiao')
        game.run('UPDATE maids SET sick_until_day=? WHERE id=?', (game.cur_day() + 3, mid)); self.upkeep()
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0)
        game.run('DELETE FROM maids'); self.maid('shouqiao')
        game.run("UPDATE consorts SET status='confined' WHERE id=?", (self.atk,))
        self.upkeep()
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0)

    def test_unpaid_maids_make_nothing(self):
        self.maid('shouqiao')
        game.run('UPDATE consorts SET silver=0 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.maid_upkeep(game.cur_day())
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0)

    def test_crafted_items_work_and_are_not_sold(self):
        game.inv_add(self.atk, 'dianxin'); game.inv_add(self.atk, 'tiseng'); game.inv_add(self.atk, 'hebao'); game.inv_add(self.atk, 'xiangnang')
        game.run('UPDATE consorts SET health=50, energy=3, silver=100, seek_bonus=0 WHERE id=?', (self.atk,))
        for k in ('dianxin', 'tiseng', 'hebao', 'xiangnang'):
            self.client.post(f'/shop/use/{k}')
        c = self.me()
        self.assertEqual((c['health'], c['energy'], c['silver'], c['seek_bonus']), (52, 4, 115, 8))
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        self.client.post('/shop/buy/xiangnang')
        self.assertEqual(game.inv_qty(self.atk, 'xiangnang'), 0, '做出来的东西内务府不卖')

    def test_tea_does_not_exceed_energy_cap(self):
        game.inv_add(self.atk, 'tiseng')
        game.run('UPDATE consorts SET energy=? WHERE id=?', (game.ENERGY_MAX, self.atk))
        self.client.post('/shop/use/tiseng')
        self.assertEqual(self.me()['energy'], game.ENERGY_MAX)

    def test_shop_lists_crafted_items_only_when_held(self):
        html = self.client.get('/shop').get_data(as_text=True)
        self.assertNotIn('香囊', html)
        game.inv_add(self.atk, 'xiangnang')
        html = self.client.get('/shop').get_data(as_text=True)
        self.assertIn('香囊', html)
        self.assertIn('宫人所制', html)

    def test_every_craft_target_exists_and_traits_are_covered(self):
        for trait in game.MAID_TRAITS:
            self.assertIn(trait, game.MAID_CRAFT)
        for spec in game.MAID_CRAFT.values():
            if spec['kind'] == 'item':
                self.assertTrue(game.ITEMS[spec['key']].get('craft'))


if __name__ == '__main__':
    unittest.main()
