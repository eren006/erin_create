"""交好 NPC（设计文档九点二十一节）：拜访、牵连、各位 NPC 的回报与风险

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle

game = test_lifecycle.game


class BondContentTests(unittest.TestCase):
    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_every_npc_has_full_profile(self):
        self.assertEqual(set(game.NPC_BOND), game.NPC_KEYS)
        for key, cfg in game.NPC_BOND.items():
            self.assertEqual(set(cfg['greet']), {name for _, name in game.BOND_TIERS}, key)
            for tier, lines in cfg['greet'].items():
                self.assertEqual(len(lines), 2, (key, tier))
            self.assertEqual(len(cfg['opts']), 4, key)
            self.assertEqual(len(cfg['perks']), 2, key)
            for o in cfg['opts']:
                if o['stat'] is None:
                    self.assertGreater(o['silver'], 0, key)       # 不看属性的都是送礼
                else:
                    self.assertIn(o['stat'], game.STAT_KEYS, key)
                    self.assertTrue(o['dislike'], key)
                self.assertTrue(o['like'] and o['gain'] > 0, key)

    def test_lines_are_distinct_and_canon_free(self):
        seen = {}
        for key, cfg in game.NPC_BOND.items():
            lines = [l for ls in cfg['greet'].values() for l in ls]
            lines += [o['like'] for o in cfg['opts']] + [o['dislike'] for o in cfg['opts'] if o.get('dislike')]
            for l in lines:
                self.assertNotIn(l, seen, f'{key} 跟 {seen.get(l)} 共用了一句台词')
                seen[l] = key
                for name in ('弘晖', '弘时', '温宜', '宜修', '世兰', '年羹尧', '苏培盛', '剪秋', '颂芝'):
                    self.assertNotIn(name, l, key)


class BondTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    tearDown = test_lifecycle.LifecycleTests.tearDown
    player = test_lifecycle.LifecycleTests.player
    login = test_lifecycle.LifecycleTests.login

    def wake(self, *keys):
        for k in keys:
            game.run("UPDATE consorts SET status='normal' WHERE npc_key=?", (k,))

    def setb(self, key, aff, cid=None):
        npc = game.npc_row(key)
        cur = game.bond(cid or self.atk, key)
        game.add_affinity(cid or self.atk, npc['id'], aff - cur)

    def visit(self, key, opt, roll=40):
        with patch.object(game.random, 'randint', return_value=roll):
            return self.client.post('/npc/visit', data={'npc': key, 'opt': opt})

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_visit_success_costs_energy_and_once_a_day(self):
        self.wake('jingpin')
        game.run('UPDATE consorts SET virtue=60, energy=5 WHERE id=?', (self.atk,))
        self.visit('jingpin', 1)
        self.assertEqual(game.bond(self.atk, 'jingpin'), 7)
        self.assertEqual(game.get_consort(self.atk)['energy'], 4)
        self.visit('jingpin', 1)                             # 一天只能去一位
        self.assertEqual(game.bond(self.atk, 'jingpin'), 7)
        self.assertEqual(self.client.get('/social').status_code, 200)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_snub_and_gift(self):
        self.wake('duanfei')
        game.run('UPDATE consorts SET scheme=10 WHERE id=?', (self.atk,))
        self.visit('duanfei', 2, roll=0)
        self.assertEqual(game.bond(self.atk, 'duanfei'), game.BOND_SNUB)
        game.run("DELETE FROM daily_counters WHERE consort_id=? AND key='npc_visit'", (self.atk,))
        before = game.get_consort(self.atk)['silver']
        self.visit('duanfei', 0)
        self.assertEqual(game.get_consort(self.atk)['silver'], before - 20)
        self.assertEqual(game.bond(self.atk, 'duanfei'), game.BOND_SNUB + 7)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_huanghou_huafei_are_rivals_and_lipin_talks(self):
        self.wake('huanghou', 'huafei', 'lipin')
        game.change_bond(self.atk, 'huafei', 10)
        self.assertEqual(game.bond(self.atk, 'huanghou'), -5)
        game.change_bond(self.atk, 'lipin', 8)
        self.assertEqual(game.bond(self.atk, 'huafei'), 12)
        self.assertEqual(game.bond(self.atk, 'huanghou'), -7)
        game.change_bond(self.atk, 'huafei', -10)            # 掉的时候不牵连
        self.assertEqual(game.bond(self.atk, 'huanghou'), -7)
        self.setb('lipin', 60)
        before = game.bond(self.atk, 'huafei')
        game.change_bond(self.atk, 'huafei', 10)
        self.assertEqual(game.bond(self.atk, 'huafei'), before + 15)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_scene_effect_goes_through_change_bond(self):
        self.wake('huanghou', 'huafei')
        game.apply_effects(self.atk, dict(huafei=10))
        self.assertEqual(game.bond(self.atk, 'huanghou'), -5)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_guards_on_intrigue_success(self):
        self.wake('huanghou', 'huafei', 'caoguiren')
        atk, tgt = game.get_consort(self.tgt), game.get_consort(self.atk)
        cfg = game.INTRIGUES['rumor']
        base = game.intrigue_success_p(atk, tgt, cfg)
        self.setb('huanghou', 30)
        self.assertAlmostEqual(game.intrigue_success_p(atk, tgt, cfg), base - game.BOND_HUANGHOU_GUARD)
        self.setb('huafei', 60)
        self.assertAlmostEqual(game.intrigue_success_p(atk, tgt, cfg), base - game.BOND_HUANGHOU_GUARD - game.BOND_HUAFEI_GUARD)
        self.setb('caoguiren', 60, cid=self.tgt)
        self.assertAlmostEqual(game.intrigue_success_p(atk, tgt, cfg),
                               base - game.BOND_HUANGHOU_GUARD - game.BOND_HUAFEI_GUARD + game.BOND_CAO_BOOST)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_huafei_close_spares_you(self):
        self.wake('huafei')
        game.run('UPDATE consorts SET favor=200 WHERE id=?', (self.atk,))
        self.assertEqual(game.huafei_likely_target(exclude_id=self.tgt)['id'], self.atk)
        self.setb('huafei', 30)
        self.assertIsNone(game.huafei_likely_target(exclude_id=self.tgt))

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_huanghou_intimate_cuts_promotion_need(self):
        self.wake('huanghou')
        c = game.get_consort(self.atk)
        self.assertEqual(game.promote_favor_need(c, 6), game.PROMOTE_FAVOR[6])
        self.setb('huanghou', 60)
        self.assertEqual(game.promote_favor_need(c, 6), round(game.PROMOTE_FAVOR[6] * 0.9))

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_intimate_decays_at_night(self):
        self.wake('jingpin')
        self.setb('jingpin', 65)
        self.setb('jingpin', 20, cid=self.tgt)
        game.npc_bond_tick(10)
        self.assertEqual(game.bond(self.atk, 'jingpin'), 63)
        self.assertEqual(game.bond(self.tgt, 'jingpin'), 20)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_qifei_pleads_once_per_interval(self):
        self.wake('qifei')
        self.setb('qifei', 30)
        game.run("UPDATE consorts SET status='cold', status_until_day=13 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.npc_bond_tick(10)
            game.npc_bond_tick(11)
        self.assertEqual(game.get_consort(self.atk)['status_until_day'], 12)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_caught_angers_huanghou(self):
        self.wake('huanghou')
        self.setb('huanghou', 40)
        game.bond_caught_huanghou(self.atk)
        self.assertEqual(game.bond(self.atk, 'huanghou'), 10)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_duanfei_intimate_names_three_suspects(self):
        self.wake('duanfei')
        self.setb('duanfei', 60)
        c3 = self.player('丙')
        game.run("""INSERT INTO intrigues (day, attacker_id, target_id, method, status, result, created_ts)
                    VALUES (9, ?, ?, 'rumor', 'done', 'success', 0)""", (self.tgt, self.atk))
        line = game.bond_visit_perk(game.get_consort(self.atk), 'duanfei', 60)
        self.assertIn(game.display_name(game.get_consort(self.tgt)), line)
        self.assertIn(game.display_name(game.get_consort(c3)), line)
        self.assertNotIn(game.display_name(game.get_consort(self.tgt)) + '害', line)
        with patch.object(game.random, 'random', return_value=0.99):   # 同一件事不说第二遍
            self.assertEqual(game.bond_visit_perk(game.get_consort(self.atk), 'duanfei', 60), '')

    def test_xinchangzai_warns_count_only(self):
        self.wake('xinchangzai')
        game.run("INSERT INTO intrigues (day, attacker_id, target_id, method, created_ts) VALUES (10, ?, ?, 'rumor', 0)",
                 (self.tgt, self.atk))
        line = game.bond_visit_perk(game.get_consort(self.atk), 'xinchangzai', 60)
        self.assertIn('1 拨', line)
        self.assertNotIn(game.display_name(game.get_consort(self.tgt)), line)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_jingpin_intimate_visit_is_free(self):
        import test_heirs
        self.wake('jingpin')
        jp = game.npc_row('jingpin')
        hid = test_heirs.HeirTests.heir(self, self.atk, caretaker=jp['id'])
        h = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        c = game.get_consort(self.atk)
        self.assertEqual(game.heir_visit_cost(c, h), game.HEIR_VISIT_ENERGY)
        self.setb('jingpin', 60)
        self.assertEqual(game.heir_visit_cost(c, h), 0)


if __name__ == '__main__':
    unittest.main()
