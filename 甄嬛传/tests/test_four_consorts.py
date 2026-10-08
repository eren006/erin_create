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
        self.assertEqual(n[6:], ['贵嫔', '九昭', '四妃', '贵妃', '皇贵妃', '皇后'])
        self.assertEqual(game.PLAYER_MAX_RANK, 11)
        self.assertEqual(game.RANK_SLOTS[game.RANK_FOUR], 4)
        self.assertEqual((game.RANK_SLOTS[5], game.RANK_SLOTS[6], game.RANK_SLOTS[7], game.RANK_SLOTS[8]), (4, 3, 9, 4))
        self.assertEqual(len(game.NINE_CONSORT_TITLES), game.RANK_SLOTS[game.RANK_JIUPIN], '九个名号，九个名额，一人一个')

    def test_four_titles_are_not_in_the_normal_pool(self):
        for t in game.FOUR_CONSORT_TITLES:
            self.assertNotIn(t, game.TITLE_POOL)

    def test_promotion_to_four_gets_a_word_and_shows_title_word_fei(self):
        game.run("UPDATE consorts SET rank=7, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, game.RANK_FOUR)
        c = self.me(self.atk)
        self.assertEqual(c['title'], '怡')            # 封号不变
        self.assertIn(c['four_word'], game.FOUR_CONSORT_TITLES)
        self.assertEqual(game.display_name(c), '怡' + c['four_word'] + '妃')   # 如：怡德妃

    def test_four_consorts_get_distinct_words(self):
        ids = [self.atk, self.tgt] + [self.player(f'位{i}') for i in range(2)]
        for cid in ids:
            game.run("UPDATE consorts SET rank=7 WHERE id=?", (cid,))
            game.set_rank(cid, game.RANK_FOUR)
        self.assertEqual({self.me(c)['four_word'] for c in ids}, set(game.FOUR_CONSORT_TITLES))

    def test_dropping_out_of_four_clears_the_word(self):
        game.run("UPDATE consorts SET rank=7, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, game.RANK_FOUR)
        game.set_rank(self.atk, game.RANK_FEI)
        c = self.me(self.atk)
        self.assertEqual((c['title'], c['four_word']), ('怡', ''))
        self.assertIn(c['nine_word'], game.NINE_CONSORT_TITLES)      # 降到九昭，拿到一个九昭名号
        self.assertEqual(game.display_name(c), '怡' + c['nine_word'])

    def test_going_up_to_guifei_frees_the_word_and_uses_plain_name(self):
        game.run("UPDATE consorts SET rank=7, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, game.RANK_FOUR)
        game.set_rank(self.atk, game.RANK_GUIFEI)
        c = self.me(self.atk)
        self.assertEqual(c['four_word'], '')
        self.assertEqual(game.display_name(c), '怡贵妃')

    def test_cold_palace_clears_the_word(self):
        game.run("UPDATE consorts SET rank=7, title='怡' WHERE id=?", (self.atk,))
        game.set_rank(self.atk, game.RANK_FOUR)
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
        self.assertEqual((self.me(self.atk)['rank'], self.me(self.atk)['peak_rank']), (9, 9))      # 旧贵妃 7 → 8（四妃）→ 10 → 9（九昭并入后）
        self.assertEqual(self.me(self.tgt)['rank'], 10)
        self.assertEqual(self.me(a)['rank'], 5)
        for cid in (self.atk, a):
            self.assertNotIn(self.me(cid)['title'], game.FOUR_CONSORT_TITLES)

    def test_nine_words_are_distinct_and_merge_migration_gives_each_holder_one(self):
        ids = [self.atk, self.tgt] + [self.player(f'九{i}') for i in range(3)]
        for cid in ids:
            game.run("UPDATE consorts SET rank=8, peak_rank=8, prestige_top=8, nine_word='' WHERE id=?", (cid,))      # 旧：昭仪档
        old_fei = self.player('旧妃')
        game.run("UPDATE consorts SET rank=7, peak_rank=7, prestige_top=7, nine_word='' WHERE id=?", (old_fei,))      # 旧：妃档
        game.run("UPDATE game_state SET rank_scale=2")
        db = sqlite3.connect(game.DB_PATH)
        game.migrate_rank_scale(db); db.commit(); game.migrate_rank_scale(db); db.commit()
        db.close()
        holders = ids + [old_fei]
        self.assertTrue(all(self.me(c)['rank'] == game.RANK_JIUPIN for c in holders), '妃、昭仪并成九昭')
        words = [self.me(c)['nine_word'] for c in holders]
        self.assertEqual(len(set(words)), len(words), '一人一个，不重复')
        self.assertTrue(all(w in game.NINE_CONSORT_TITLES for w in words))
        self.assertEqual(game.display_name(self.me(old_fei)), self.me(old_fei)['surname'] + self.me(old_fei)['nine_word'] if not self.me(old_fei)['title'] else self.me(old_fei)['title'] + self.me(old_fei)['nine_word'])

    def test_leaving_nine_frees_the_word_for_the_next_one(self):
        a, b = self.atk, self.tgt
        game.run("UPDATE consorts SET rank=6 WHERE id IN (?,?)", (a, b))
        game.set_rank(a, game.RANK_JIUPIN); game.set_rank(b, game.RANK_JIUPIN)
        wa, wb = self.me(a)['nine_word'], self.me(b)['nine_word']
        self.assertNotEqual(wa, wb)
        game.set_rank(a, 6)
        self.assertEqual(self.me(a)['nine_word'], '')

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
