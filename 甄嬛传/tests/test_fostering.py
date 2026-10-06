"""抚养博弈：托付、探视、讨回、抚养人出事后换人，见设计文档九点六节 C

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class FosteringTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def heir_row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def low_mother(self, name='戊'):
        cid = self.player(name, rank=3)   # 答应，贵人以下
        self.login(cid)
        return cid

    # ── 托付 ─────────────────────────────────────────────────────────────────

    def test_entrust_then_accept_moves_custody(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day())
        game.add_affinity(mother, self.atk, 50)
        r = self.client.post(f'/heirs/entrust/{hid}', data=dict(target_id=self.atk))
        self.assertEqual(self.heir_row(hid)['foster_request_to'], self.atk)
        self.assertEqual(self.heir_row(hid)['caretaker_id'], mother, '对方点头之前孩子还在生母身边')
        self.login(self.atk)
        self.client.post(f'/heirs/entrust_reply/{hid}', data=dict(reply='yes'))
        h = self.heir_row(hid)
        self.assertEqual(h['caretaker_id'], self.atk)
        self.assertEqual(h['foster_request_to'], 0)

    def test_entrust_needs_enough_affinity(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day())
        game.add_affinity(mother, self.atk, 39)
        self.client.post(f'/heirs/entrust/{hid}', data=dict(target_id=self.atk))
        self.assertEqual(self.heir_row(hid)['foster_request_to'], 0)

    def test_entrust_target_must_be_pin_or_above(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day())
        game.add_affinity(mother, self.tgt, 80)   # 乙只是贵人
        self.client.post(f'/heirs/entrust/{hid}', data=dict(target_id=self.tgt))
        self.assertEqual(self.heir_row(hid)['foster_request_to'], 0)

    def test_entrust_after_zhuazhou_age_rejected(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day() - game.ZHUAZHOU_AGE_DAYS)
        game.add_affinity(mother, self.atk, 80)
        self.client.post(f'/heirs/entrust/{hid}', data=dict(target_id=self.atk))
        self.assertEqual(self.heir_row(hid)['foster_request_to'], 0)

    def test_high_rank_mother_cannot_entrust(self):
        hid = self.heir(self.atk, born=game.cur_day())   # 甲是嫔
        boss = self.player('丙', rank=6)
        game.add_affinity(self.atk, boss, 80)
        self.client.post(f'/heirs/entrust/{hid}', data=dict(target_id=boss))
        self.assertEqual(self.heir_row(hid)['foster_request_to'], 0)

    def test_refuse_clears_request(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day())
        game.run('UPDATE heirs SET foster_request_to=? WHERE id=?', (self.atk, hid))
        self.login(self.atk)
        self.client.post(f'/heirs/entrust_reply/{hid}', data=dict(reply='no'))
        h = self.heir_row(hid)
        self.assertEqual((h['caretaker_id'], h['foster_request_to']), (mother, 0))

    def test_only_the_named_target_can_reply(self):
        mother = self.low_mother()
        hid = self.heir(mother, born=game.cur_day())
        game.run('UPDATE heirs SET foster_request_to=? WHERE id=?', (self.atk, hid))
        other = self.player('丁', rank=6)
        self.login(other)
        self.client.post(f'/heirs/entrust_reply/{hid}', data=dict(reply='yes'))
        self.assertEqual(self.heir_row(hid)['caretaker_id'], mother)

    def test_accepted_entrust_skips_zhuazhou_reassignment(self):
        mother = self.low_mother()
        other = self.player('丁', rank=6)
        hid = self.heir(mother, caretaker=self.atk, born=8)   # 已托付给甲
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS)
        self.assertEqual(self.heir_row(hid)['caretaker_id'], self.atk, '托付成了，祖制不再另指别人')

    def test_unanswered_request_expires_at_zhuazhou(self):
        mother = self.low_mother()
        self.player('丁', rank=6)
        hid = self.heir(mother, born=8, foster_request_to=self.atk)
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS)
        h = self.heir_row(hid)
        self.assertEqual(h['foster_request_to'], 0)
        self.assertEqual(h['caretaker_id'], 0, '未同意托付时进入养育所')

    # ── 探视 ─────────────────────────────────────────────────────────────────

    def test_visit_raises_mother_affinity_and_costs_energy(self):
        mother = self.low_mother()
        hid = self.heir(mother, caretaker=self.atk, mother_affinity=30, caretaker_affinity=60)
        e0 = game.get_consort(mother)['energy']
        self.client.post(f'/heirs/visit/{hid}')
        h = self.heir_row(hid)
        self.assertEqual(h['mother_affinity'], 30 + game.HEIR_VISIT_GAIN)
        self.assertEqual(h['caretaker_affinity'], 60, '探视只动生母情分')
        self.assertEqual(game.get_consort(mother)['energy'], e0 - game.HEIR_VISIT_ENERGY)

    def test_visit_once_per_day(self):
        mother = self.low_mother()
        hid = self.heir(mother, caretaker=self.atk, mother_affinity=30)
        self.client.post(f'/heirs/visit/{hid}')
        self.client.post(f'/heirs/visit/{hid}')
        self.assertEqual(self.heir_row(hid)['mother_affinity'], 30 + game.HEIR_VISIT_GAIN)

    def test_banned_visit_blocked_for_player_caretaker(self):
        mother = self.low_mother()
        hid = self.heir(mother, caretaker=self.atk, mother_affinity=30, visit_banned=1)
        self.client.post(f'/heirs/visit/{hid}')
        self.assertEqual(self.heir_row(hid)['mother_affinity'], 30)

    def test_caretaker_can_toggle_ban_but_mother_cannot(self):
        mother = self.low_mother()
        hid = self.heir(mother, caretaker=self.atk)
        self.client.post(f'/heirs/ban/{hid}')   # 现在登录的是生母
        self.assertEqual(self.heir_row(hid)['visit_banned'], 0)
        self.login(self.atk)
        self.client.post(f'/heirs/ban/{hid}')
        self.assertEqual(self.heir_row(hid)['visit_banned'], 1)
        self.client.post(f'/heirs/ban/{hid}')
        self.assertEqual(self.heir_row(hid)['visit_banned'], 0)

    def test_visit_exposes_concealed_truth(self):
        mother = self.low_mother()
        hid = self.heir(mother, caretaker=self.atk, caretaker_affinity=60, concealed=1)
        self.client.post(f'/heirs/visit/{hid}')
        h = self.heir_row(hid)
        self.assertEqual(h['caretaker_affinity'], 60 - game.HEIR_EXPOSED_PENALTY)
        self.assertEqual(h['concealed'], 0)
        self.assertTrue(any('说破' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (self.atk,))))

    def test_concealing_in_event_sets_flag(self):
        hid = self.heir(self.tgt, caretaker=self.atk, born=game.cur_day() - 20)
        game.run('UPDATE consorts SET heir_event=? WHERE id=?',
                 (game.json.dumps(dict(key='true_mother', heir=hid, day=game.cur_day())), self.atk))
        self.client.post('/heirs/event', data=dict(opt=1))
        self.assertEqual(self.heir_row(hid)['concealed'], 1)

    # ── 讨回 ─────────────────────────────────────────────────────────────────

    def test_reclaim_success_returns_child(self):
        boss = self.player('丙', rank=6)
        hid = self.heir(self.atk, caretaker=boss, mother_affinity=70, caretaker_affinity=40, visit_banned=1)
        self.client.post(f'/heirs/reclaim/{hid}')
        self.assertEqual(self.heir_row(hid)['caretaker_id'], boss)
        game.run('UPDATE custody_battles SET challenger_progress=90 WHERE heir_id=?',(hid,))
        self.client.post(f'/heirs/custody/{hid}',data={'action':'bond'})
        h=self.heir_row(hid)
        self.assertEqual(h['caretaker_id'],self.atk)
        self.assertEqual(h['caretaker_affinity'],70)
        self.assertEqual(h['visit_banned'],0)

    def test_reclaim_failure_sets_cooldown(self):
        boss = self.player('丙', rank=6)
        hid = self.heir(self.atk, caretaker=boss)
        self.client.post(f'/heirs/reclaim/{hid}')
        self.client.post(f'/heirs/custody/{hid}',data={'action':'yield'})
        h=self.heir_row(hid)
        self.assertEqual(h['caretaker_id'],boss)
        self.assertEqual(h['reclaim_after_day'],game.cur_day()+game.HEIR_RECLAIM_COOLDOWN)
        e=game.get_consort(self.atk)['energy']
        self.client.post(f'/heirs/reclaim/{hid}')
        self.assertEqual(game.get_consort(self.atk)['energy'],e)

    def test_reclaim_needs_pin_rank(self):
        mother = self.low_mother()
        boss = self.player('丁', rank=6)
        hid = self.heir(mother, caretaker=boss)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post(f'/heirs/reclaim/{hid}')
        self.assertEqual(self.heir_row(hid)['caretaker_id'], boss)

    # ── 抚养人进冷宫 / 薨逝 ────────────────────────────────────────────────────

    def test_mother_cold_child_goes_to_someone_else(self):
        boss = self.player('丙', rank=6)
        hid = self.heir(self.atk)   # 甲亲自带着
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        game.heir_rehome_tick(game.cur_day())
        h = self.heir_row(hid)
        self.assertEqual(h['caretaker_id'], 0)
        self.assertEqual(h['caretaker_affinity'], 50)

    def test_mother_dead_child_goes_to_someone_else(self):
        boss = self.player('丙', rank=6)
        hid = self.heir(self.atk)
        game.die(self.atk, '病重不治', memorial_reason='病逝')
        game.heir_rehome_tick(game.cur_day())
        self.assertEqual(self.heir_row(hid)['caretaker_id'], 0)

    def test_foster_cold_child_returns_to_pin_mother(self):
        boss = self.player('丙', rank=6)
        hid = self.heir(self.atk, caretaker=boss, mother_affinity=66, caretaker_affinity=40)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (boss,))
        game.heir_rehome_tick(game.cur_day())
        h = self.heir_row(hid)
        self.assertEqual(h['caretaker_id'], self.atk)
        self.assertEqual(h['caretaker_affinity'], 66)

    def test_foster_dead_low_rank_mother_gets_new_foster(self):
        mother = self.low_mother()
        boss = self.player('丙', rank=6)
        newer = self.player('丁', rank=6)
        hid = self.heir(mother, caretaker=boss)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))   # 甲也是嫔，先让她靠边，免得抢了名额
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (boss,))
        game.heir_rehome_tick(game.cur_day())
        self.assertEqual(self.heir_row(hid)['caretaker_id'], 0, '低位生母的孩子回养育所')

    def test_no_candidate_leaves_child_for_tomorrow(self):
        hid = self.heir(self.atk)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        game.heir_rehome_tick(game.cur_day())   # 没有别的嫔以上，不该报错
        self.assertEqual(self.heir_row(hid)['caretaker_id'], 0)

    def test_heirs_page_renders_actions(self):
        mother = self.low_mother()
        boss = self.player('丙', rank=6)
        game.add_affinity(mother, boss, 60)
        young = self.heir(mother, born=game.cur_day())
        away = self.heir(mother, caretaker=boss, born=game.cur_day() - 6)
        page = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('托付', page)
        self.assertIn('探视', page)
        self.login(boss)
        self.assertIn('不许探视', self.client.get('/heirs').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
