"""降位的办法：参奏降位（主动）、失宠太久自动降一级"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class DemotionTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def me(self, cid): return game.get_consort(cid)

    def prep(self, atk_rank=7, tgt_rank=5):
        game.run("UPDATE consorts SET rank=?, silver=2000, energy=8, impeach_ready_day=0, entered_day=1 WHERE id=?", (atk_rank, self.atk))
        game.run("UPDATE consorts SET rank=?, impeached_day=0, entered_day=1, favor=100 WHERE id=?", (tgt_rank, self.tgt))
        self.login(self.atk)

    def impeach(self, roll):
        with patch.object(game, 'INTRIGUE_REALTIME', True), patch.object(game.random, 'random', return_value=roll):
            return self.client.post('/intrigue/submit', data={'method': 'impeach', 'target_id': self.tgt})

    def test_impeach_success_demotes_one_rank_and_cuts_favor(self):
        self.prep()
        self.impeach(0.0)
        t = self.me(self.tgt)
        self.assertEqual(t['rank'], 4)
        self.assertEqual(t['favor'], 100 - game.IMPEACH_FAVOR_LOSS)
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%被参奏失德%'", one=True))
        self.assertEqual(self.me(self.atk)['impeach_ready_day'], game.cur_day() + game.IMPEACH_COOLDOWN)

    def test_impeach_caught_punishes_the_attacker(self):
        self.prep()
        before = self.me(self.atk)
        with patch.object(game, 'INTRIGUE_REALTIME', True), patch.object(game, 'intrigue_success_p', return_value=0.0), patch.object(game, 'intrigue_caught_p', return_value=1.0):
            self.client.post('/intrigue/submit', data={'method': 'impeach', 'target_id': self.tgt})
        self.assertEqual(self.me(self.tgt)['rank'], 5)
        self.assertLess(self.me(self.atk)['virtue'], before['virtue'])

    def test_impeach_is_public_whatever_the_result(self):
        # 成功：邸报公开，对方知道是谁
        self.prep(); self.impeach(0.0)
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%被参奏失德%'", one=True))
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%参你%'", (self.tgt,), one=True))
        # 没成（没人察觉的那种）：照样公开
        game.run("DELETE FROM gazette"); game.run("DELETE FROM messages"); game.run("DELETE FROM intrigues")
        self.prep(); game.run("UPDATE consorts SET rank=5, impeached_day=0 WHERE id=?", (self.tgt,))
        with patch.object(game, 'intrigue_success_p', return_value=0.0), patch.object(game, 'intrigue_caught_p', return_value=0.0):
            self.client_post_impeach()
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%皇上留中不发%'", one=True))
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%压下了%'", (self.tgt,), one=True))
        # 败露：邸报公开
        game.run("DELETE FROM gazette"); game.run("DELETE FROM intrigues")
        self.prep(); game.run("UPDATE consorts SET rank=5, impeached_day=0 WHERE id=?", (self.tgt,))
        with patch.object(game, 'intrigue_success_p', return_value=0.0), patch.object(game, 'intrigue_caught_p', return_value=1.0):
            self.client_post_impeach()
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%参奏降位%败露%'", one=True))

    def client_post_impeach(self):
        with patch.object(game, 'INTRIGUE_REALTIME', True):
            self.client.post('/intrigue/submit', data={'method': 'impeach', 'target_id': self.tgt})

    def divide(self, roll):
        with patch.object(game, 'INTRIGUE_REALTIME', True), patch.object(game.random, 'random', return_value=roll):
            return self.client.post('/intrigue/submit', data={'method': 'divide', 'target_id': self.tgt})

    def test_auto_retaliation_when_victim_can_see_the_culprit(self):
        self.prep(atk_rank=4, tgt_rank=4)
        game.run("UPDATE consorts SET silver=2000, influence=40, eyes_until_day=99999 WHERE id=?", (self.tgt,))
        with patch.object(game, 'AUTO_SCHEME_CONSORTS', {self.tgt}), patch.object(game, 'INTRIGUE_REALTIME', True), \
                patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        back = game.q("SELECT * FROM intrigues WHERE attacker_id=? AND target_id=?", (self.tgt, self.atk))
        self.assertEqual(len(back), 1)
        self.assertIn(back[0]['method'], ('divide', 'rumor'))
        self.assertEqual(back[0]['status'], 'done')

    def test_no_retaliation_without_eyes_or_for_other_players(self):
        self.prep(atk_rank=4, tgt_rank=4)
        game.run("UPDATE consorts SET eyes_until_day=0 WHERE id=?", (self.tgt,))
        with patch.object(game, 'AUTO_SCHEME_CONSORTS', {self.tgt}), patch.object(game, 'INTRIGUE_REALTIME', True), \
                patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/intrigue/submit', data={'method': 'rumor', 'target_id': self.tgt})
        self.assertEqual(len(game.q("SELECT * FROM intrigues WHERE attacker_id=?", (self.tgt,))), 0)

    def test_divide_cuts_target_influence_and_can_push_it_below_the_line(self):
        self.prep(atk_rank=2, tgt_rank=5)
        game.run("UPDATE consorts SET influence=30 WHERE id=?", (self.tgt,))
        before = self.me(self.atk)['influence']
        self.divide(0.0)
        self.assertEqual(self.me(self.tgt)['influence'], 30 - game.DIVIDE_INFLUENCE_LOSS)      # 15，已低于嫔位要求 25
        self.assertEqual(self.me(self.atk)['influence'], before + game.INFLUENCE_GAINS['divide'])
        self.assertEqual(self.me(self.tgt)['rank'], 5)                                        # 当晚不降位，要连着低 2 晚

    def test_divide_blocked_when_target_has_no_influence(self):
        self.prep(atk_rank=2, tgt_rank=5)
        game.run("UPDATE consorts SET influence=0 WHERE id=?", (self.tgt,))
        silver = self.me(self.atk)['silver']
        self.divide(0.0)
        self.assertEqual(self.me(self.atk)['silver'], silver)

    def test_impeach_has_no_rank_requirement_but_has_cooldown(self):
        self.prep(atk_rank=6, tgt_rank=5)
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 4)      # 只高一级也参得动
        self.prep(atk_rank=2, tgt_rank=5)
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 4)      # 答应也能参奏嫔
        self.prep(atk_rank=5, tgt_rank=2)
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 1)      # 对方位分再低也行（妃位及以上另有「不对常在及以下使计」的限制）
        self.prep(atk_rank=7, tgt_rank=2)
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 2)      # 妃位以上打不了常在及以下
        self.prep(atk_rank=7, tgt_rank=5)
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 4)
        game.run("UPDATE consorts SET rank=5 WHERE id=?", (self.tgt,))
        self.impeach(0.0)
        self.assertEqual(self.me(self.tgt)['rank'], 5)      # 冷却中
        self.assertIsNotNone(game.impeach_block(self.me(self.atk), self.me(self.tgt), game.cur_day()))

    def test_impeach_success_resets_influence_to_lower_rank_floor(self):
        self.prep(atk_rank=7, tgt_rank=5)
        game.run("UPDATE consorts SET influence=60 WHERE id=?", (self.tgt,))
        self.impeach(0.0)
        t = self.me(self.tgt)
        self.assertEqual(t['rank'], 4)
        self.assertEqual(t['influence'], game.PROMOTE_INFLUENCE[4])      # 势力回到贵人的最低线

    def settle(self):
        with patch.object(game.random, 'random', return_value=0.99), patch.object(game, 'npc_schemes'):
            game.settle_day()

    def test_big_one_day_favor_drop_demotes_one_rank(self):
        game.run("UPDATE consorts SET rank=5, favor=100, favor_mark=100+?, entered_day=1 WHERE id=?", (game.FAVOR_DROP_DEMOTE + 40, self.tgt))      # 留余量：结算里侍寝、召见会让圣宠回涨几点
        game.run("UPDATE consorts SET favor=500, favor_mark=500 WHERE id=?", (self.atk,))
        self.settle()
        self.assertEqual(self.me(self.tgt)['rank'], 4)
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%圣眷骤衰%'", one=True))
        self.assertEqual(self.me(self.tgt)['favor_mark'], self.me(self.tgt)['favor'])      # 基线重新记

    def test_small_drop_or_no_baseline_or_low_rank_does_not_demote(self):
        game.run("UPDATE consorts SET rank=5, favor=100, favor_mark=100+?, entered_day=1 WHERE id=?", (game.FAVOR_DROP_DEMOTE - 1, self.tgt))
        game.run("UPDATE consorts SET rank=5, favor=100, favor_mark=-1, entered_day=1 WHERE id=?", (self.atk,))
        self.settle()
        self.assertEqual(self.me(self.tgt)['rank'], 5)
        self.assertEqual(self.me(self.atk)['rank'], 5)
        game.run("UPDATE consorts SET rank=2, favor=100, favor_mark=300, entered_day=1 WHERE id=?", (self.tgt,))
        self.settle()
        self.assertEqual(self.me(self.tgt)['rank'], 2)      # 答应不再往下降

if __name__ == '__main__':
    unittest.main()
