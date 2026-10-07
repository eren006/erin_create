"""四妃：妃和贵妃之间新加的一档（淑德贤惠），及旧档位分顺延迁移"""
import sqlite3
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class FourConsortTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def me(self, cid): return game.get_consort(cid)

    def test_ladder_order_and_slots(self):
        n = game.RANK_NAMES
        self.assertEqual(n[6:], ['妃', '四妃', '贵妃', '皇贵妃', '皇后'])
        self.assertEqual(game.PLAYER_MAX_RANK, 10)
        self.assertEqual(game.RANK_SLOTS[7], 4)

    def test_four_titles_are_not_in_the_normal_pool(self):
        for t in game.FOUR_CONSORT_TITLES:
            self.assertNotIn(t, game.TITLE_POOL)

    def test_promotion_to_four_gets_a_word_and_shows_title_word_fei(self):
        game.run("UPDATE consorts SET rank=6, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, 7)
        c = self.me(self.atk)
        self.assertEqual(c['title'], '怡')            # 封号不变
        self.assertIn(c['four_word'], game.FOUR_CONSORT_TITLES)
        self.assertEqual(game.display_name(c), '怡' + c['four_word'] + '妃')   # 如：怡德妃

    def test_four_consorts_get_distinct_words(self):
        ids = [self.atk, self.tgt] + [self.player(f'位{i}') for i in range(2)]
        for cid in ids:
            game.run("UPDATE consorts SET rank=6 WHERE id=?", (cid,))
            game.set_rank(cid, 7)
        self.assertEqual({self.me(c)['four_word'] for c in ids}, set(game.FOUR_CONSORT_TITLES))

    def test_dropping_out_of_four_clears_the_word(self):
        game.run("UPDATE consorts SET rank=6, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, 7)
        game.set_rank(self.atk, 6)
        c = self.me(self.atk)
        self.assertEqual((c['title'], c['four_word']), ('怡', ''))
        self.assertEqual(game.display_name(c), '怡妃')

    def test_going_up_to_guifei_frees_the_word_and_uses_plain_name(self):
        game.run("UPDATE consorts SET rank=6, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, 7)
        game.set_rank(self.atk, 8)
        c = self.me(self.atk)
        self.assertEqual(c['four_word'], '')
        self.assertEqual(game.display_name(c), '怡贵妃')

    def test_cold_palace_clears_the_word(self):
        game.run("UPDATE consorts SET rank=6, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, 7)
        game.send_to_cold(self.atk)
        self.assertEqual(self.me(self.atk)['four_word'], '')

    def test_migration_shifts_old_high_ranks_once_and_renames_reserved_titles(self):
        a = self.player('甲甲', rank=5)
        game.run("UPDATE consorts SET rank=7, peak_rank=7, prestige_top=7, title='淑' WHERE id=?", (self.atk,))   # 旧档贵妃，封号被占
        game.run("UPDATE consorts SET rank=8, peak_rank=8, prestige_top=8 WHERE id=?", (self.tgt,))              # 旧档皇贵妃
        game.run("UPDATE consorts SET rank=5, title='惠' WHERE id=?", (a,))                                      # 嫔占着惠
        game.run("UPDATE game_state SET rank_scale=0")
        db = sqlite3.connect(game.DB_PATH)
        game.migrate_rank_scale(db); db.commit()
        game.migrate_rank_scale(db); db.commit()      # 第二次不能再顺延
        db.close()
        self.assertEqual((self.me(self.atk)['rank'], self.me(self.atk)['peak_rank']), (8, 8))
        self.assertEqual(self.me(self.tgt)['rank'], 9)
        self.assertEqual(self.me(a)['rank'], 5)
        for cid in (self.atk, a):
            self.assertNotIn(self.me(cid)['title'], game.FOUR_CONSORT_TITLES)

    def test_promotion_to_pin_and_above_grants_influence_once(self):
        game.run("UPDATE consorts SET rank=4, prestige_top=4, influence=0 WHERE id=?", (self.tgt,))
        game.set_rank(self.tgt, 5)
        self.assertEqual(self.me(self.tgt)['influence'], game.PROMOTE_INFLUENCE_REWARD)
        game.set_rank(self.tgt, 4)
        game.set_rank(self.tgt, 5)
        self.assertEqual(self.me(self.tgt)['influence'], game.PROMOTE_INFLUENCE_REWARD, '降了再升不重复给')
        game.set_rank(self.tgt, 6)
        self.assertEqual(self.me(self.tgt)['influence'], 2 * game.PROMOTE_INFLUENCE_REWARD)


if __name__ == '__main__':
    unittest.main()
