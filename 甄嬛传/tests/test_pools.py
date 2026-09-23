"""精力／差使／查案三个池子的边界，见设计文档九点十节

运行：python3 -m unittest discover -s tests -v
"""
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class PoolTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def maid(self, owner, name='春桃', trait='jiling', loyalty=60):
        return game.run("INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,?,?,1,0)",
                        (owner, name, trait, loyalty)).lastrowid

    # ── 差使：本人卧病不耽误宫人跑腿 ─────────────────────────────────────────

    def test_bribe_ignores_sickness(self):
        self.maid(self.atk)
        theirs = self.maid(self.tgt, name='秋菊')
        game.run('UPDATE consorts SET health=1 WHERE id=?', (self.atk,))   # 卧病
        self.assertTrue(game.is_sick(game.get_consort(self.atk)))
        self.client.post('/agents/act', data=dict(action='bribe', maid_id=theirs))
        self.assertTrue(game.q('SELECT 1 FROM bribes WHERE briber_id=? AND maid_id=?', (self.atk, theirs), one=True),
                        '卧病也能派宫人去收买——是宫人跑腿，不是本人出门')

    def test_inspect_ignores_sickness(self):
        self.maid(self.atk)
        game.run('UPDATE consorts SET health=1 WHERE id=?', (self.atk,))
        before = len(game.free_errand_maids(game.get_consort(self.atk)))
        self.client.post('/agents/act', data=dict(action='inspect'))
        after = len(game.free_errand_maids(game.get_consort(self.atk)))
        self.assertEqual(after, before - 1, '卧病也能派宫人清查，耗掉一次差使')

    # ── 差使：禁足只挡「伸手到别人宫里」，清查自己宫里不受影响 ──────────────────

    def test_confined_blocks_bribe_but_allows_inspect(self):
        self.maid(self.atk)
        theirs = self.maid(self.tgt, name='秋菊')
        game.confine(self.atk, 3)
        self.client.post('/agents/act', data=dict(action='bribe', maid_id=theirs))
        self.assertFalse(game.q('SELECT 1 FROM bribes WHERE briber_id=? AND maid_id=?', (self.atk, theirs), one=True),
                         '禁足在身，宫人出不了门，收买不了别人宫里的人')
        before = len(game.free_errand_maids(game.get_consort(self.atk)))
        self.client.post('/agents/act', data=dict(action='inspect'))
        after = len(game.free_errand_maids(game.get_consort(self.atk)))
        self.assertEqual(after, before - 1, '禁足时清查自己宫里照办，耗掉一次差使')

    def test_confined_blocks_energy_actions_outside_home(self):
        game.confine(self.atk, 3)
        for key in ('greet', 'garden', 'seek', 'visit', 'plead'):
            self.assertNotIn('confined', game.ACTIONS[key]['when'], f'{key} 不该在禁足名单里')
        for key in ('study', 'groom', 'rest', 'eyes'):
            self.assertIn('confined', game.ACTIONS[key]['when'], f'{key} 是本宫的事，禁足该做得了')

    # ── 差使不占精力池 ─────────────────────────────────────────────────────

    def test_spy_and_bribe_do_not_touch_energy(self):
        self.maid(self.atk)
        theirs = self.maid(self.tgt, name='秋菊')
        e0 = game.get_consort(self.atk)['energy']
        self.client.post('/act/spy', data={'target_id': self.tgt, 'back': 'social'})
        self.assertEqual(game.get_consort(self.atk)['energy'], e0)
        game.run("DELETE FROM daily_counters WHERE key LIKE 'errand:%'")   # 腾出宫人再试收买
        self.client.post('/agents/act', data=dict(action='bribe', maid_id=theirs))
        self.assertEqual(game.get_consort(self.atk)['energy'], e0)

    # ── 查案：每案每天最多两项，不占精力也不占差使 ──────────────────────────────

    def test_case_actions_do_not_touch_energy_and_cap_at_two(self):
        game.run("INSERT INTO cases(day,victim_id,culprit_id,drug,created_ts) VALUES(?,?,?,?,0)",
                 (game.cur_day(), self.tgt, self.atk, 'yanzhi'))
        case_id = game.q('SELECT id FROM cases ORDER BY id DESC', one=True)['id']
        game.run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,30)', (case_id, self.atk))
        e0 = game.get_consort(self.atk)['energy']
        self.client.post(f'/cases/{case_id}/act', data=dict(action='plead'))
        self.client.post(f'/cases/{case_id}/act', data=dict(action='pay', silver=20))
        self.assertEqual(game.get_consort(self.atk)['energy'], e0)
        before = game.q('SELECT suspicion FROM case_suspects WHERE case_id=? AND consort_id=?', (case_id, self.atk), one=True)['suspicion']
        self.client.post(f'/cases/{case_id}/act', data=dict(action='accuse', target_id=self.atk))
        after = game.q('SELECT suspicion FROM case_suspects WHERE case_id=? AND consort_id=?', (case_id, self.atk), one=True)['suspicion']
        self.assertEqual(before, after, '每桩案子每天最多两项，第三项办不了')

    # ── 不花任何池子的事：买东西、请太医、写信正文 ─────────────────────────────

    def test_free_actions_never_touch_energy(self):
        e0 = game.get_consort(self.atk)['energy']
        self.client.post('/shop/buy/renshen')
        game.run('UPDATE consorts SET poisoned_day=? WHERE id=?', (game.cur_day(), self.tgt))
        self.client.post(f'/treat/{self.tgt}')
        self.client.post('/letters/send', data=dict(to_id=self.tgt, body='请多保重'))
        self.assertEqual(game.get_consort(self.atk)['energy'], e0)

    # ── 冷宫：差使为空 ─────────────────────────────────────────────────────

    def test_cold_palace_has_no_errand(self):
        self.maid(self.atk)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        self.assertEqual(game.free_errand_maids(game.get_consort(self.atk)), [])

    # ── 书信附件：入宫不满 5 天不能附银子/道具/雅趣作品 ─────────────────────────

    def test_letter_attachment_shield_blocks_then_allows(self):
        game.run('UPDATE consorts SET entered_day=?, silver=1000 WHERE id=?', (game.cur_day() - 4, self.atk))   # 差 1 天
        before = game.get_consort(self.tgt)['silver']
        self.client.post('/letters/send', data=dict(to_id=self.tgt, body='一点心意', silver=100))
        self.assertEqual(game.get_consort(self.tgt)['silver'], before, '入宫不满 5 天，附银子送不出去')

        game.run('UPDATE consorts SET entered_day=? WHERE id=?', (game.cur_day() - 5, self.atk))   # 正好满 5 天
        self.client.post('/letters/send', data=dict(to_id=self.tgt, body='一点心意', silver=100))
        self.assertEqual(game.get_consort(self.tgt)['silver'], before + 100, '满 5 天可以附银子了')

    def test_letter_body_alone_unaffected_by_shield(self):
        game.run('UPDATE consorts SET entered_day=? WHERE id=?', (game.cur_day(), self.atk))   # 刚入宫
        r = self.client.post('/letters/send', data=dict(to_id=self.tgt, body='只是问候一句'))
        self.assertEqual(len(game.q('SELECT * FROM letters WHERE from_id=?', (self.atk,))), 1, '不附东西的信不受影响')


if __name__ == '__main__':
    unittest.main()
