"""宫人的用处：每日差使菜单、忠心护主/泄密、体己人、特质"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class MaidUseTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def maid(self, owner, name='春桃', trait='tancai', loyalty=60):
        return game.run('INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,?,?,1,0)',
                        (owner, name, trait, loyalty)).lastrowid

    def act(self, key, **data):
        return self.client.post(f'/act/{key}', data=dict(back='maids', **data))

    def me(self): return game.get_consort(self.atk)

    # ── 每日差使 ───────────────────────────────────────────────────────────

    def test_snack_gives_health_and_bed_bonus_and_uses_an_errand(self):
        self.maid(self.atk)
        game.run('UPDATE consorts SET health=50, seek_bonus=0 WHERE id=?', (self.atk,))
        self.act('maid_snack')
        self.assertEqual(self.me()['health'], 51)
        self.assertEqual(self.me()['seek_bonus'], 6)
        self.assertEqual(game.free_errand_maids(self.me()), [])

    def test_errand_needs_a_free_maid_and_each_maid_goes_once_a_day(self):
        self.maid(self.atk)
        self.act('maid_snack')
        h = self.me()['health']
        self.act('maid_snack')          # 唯一的宫人已经派出去了
        self.assertEqual(self.me()['health'], h)
        self.maid(self.atk, '夏荷')      # 再添一个就又能派一次
        self.act('maid_snack')
        self.assertEqual(self.me()['health'], h + 1)

    def test_no_maid_no_errand(self):
        h = self.me()['health']
        self.act('maid_snack')
        self.assertEqual(self.me()['health'], h)

    def test_scribe_costs_20_and_boosts_bed_chance(self):
        self.maid(self.atk)
        game.run('UPDATE consorts SET silver=100, seek_bonus=0 WHERE id=?', (self.atk,))
        self.act('maid_scribe')
        self.assertEqual(self.me()['silver'], 80)
        self.assertEqual(self.me()['seek_bonus'], 15)

    def test_shop_errand_gives_ten_percent_off_for_the_day(self):
        self.maid(self.atk)
        item = next(k for k, v in game.ITEMS.items() if v['price'] >= 40)
        price = game.ITEMS[item]['price']
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        self.assertEqual(game.shop_price(self.me(), game.ITEMS[item]), price)
        self.act('maid_shop')
        cheaper = game.shop_price(self.me(), game.ITEMS[item])
        self.assertEqual(cheaper, round(price * 0.9))
        before = self.me()['silver']
        self.client.post(f'/shop/buy/{item}')
        self.assertEqual(self.me()['silver'], before - cheaper)

    def test_watch_lowers_intrigue_success_against_me_by_8_percent(self):
        self.maid(self.tgt)
        cfg = game.INTRIGUES['rumor']
        atk, tgt = game.get_consort(self.atk), game.get_consort(self.tgt)
        base = game.intrigue_success_p(atk, tgt, cfg)
        self.login(self.tgt)
        self.act('maid_watch')
        guarded = game.intrigue_success_p(atk, game.get_consort(self.tgt), cfg)
        self.assertAlmostEqual(base - guarded, game.MAID_WATCH_GUARD * game.INTRIGUE_CUT_RATIO)

    def test_gossip_returns_a_line_and_tancai_buys_a_second_one(self):
        self.player('丙')
        self.maid(self.atk, trait='suizui')
        game.run('UPDATE consorts SET silver=100 WHERE id=?', (self.atk,))
        self.act('maid_gossip')
        self.assertEqual(self.me()['silver'], 100)
        self.maid(self.atk, '夏荷', trait='tancai')
        game.run("DELETE FROM daily_counters")
        game.run("UPDATE maids SET trait='tancai'")
        self.act('maid_gossip')
        self.assertEqual(self.me()['silver'], 90, '贪财的宫人多花 10 两买第二则')

    def test_snack_and_shop_errands_show_in_daily_feed_but_not_scribe_watch_gossip(self):
        for n in '甲乙丙丁':
            self.maid(self.atk, n)
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        self.player('戊')
        for k in ('maid_snack', 'maid_shop', 'maid_scribe', 'maid_watch'):
            self.act(k)
        texts = [r['text'] for r in game.q("SELECT text FROM daily_feed")]
        self.assertTrue(any('点心' in t for t in texts))
        self.assertTrue(any('内务府' in t for t in texts))
        self.assertEqual(len(texts), 2)

    # ── 忠心护主 / 泄密 / 体己人 ─────────────────────────────────────────────

    def test_loyal_maids_guard_and_cap_at_9_percent(self):
        for i in range(5): self.maid(self.tgt, f'宫{i}', loyalty=70)
        self.assertAlmostEqual(game.maid_defense(self.tgt), 0.09)
        game.run("DELETE FROM maids")
        self.maid(self.tgt, '甲', loyalty=70)
        self.assertAlmostEqual(game.maid_defense(self.tgt), 0.03)

    def test_disloyal_maids_leak_and_it_offsets_guard(self):
        self.maid(self.tgt, '甲', loyalty=20)
        self.assertAlmostEqual(game.maid_defense(self.tgt), -0.02)
        for i in range(5): self.maid(self.tgt, f'宫{i}', loyalty=10)
        self.assertAlmostEqual(game.maid_defense(self.tgt), -0.06)
        self.maid(self.tgt, '乙', loyalty=70)
        self.assertAlmostEqual(game.maid_defense(self.tgt), 0.03 - 0.06)

    def test_guard_actually_lowers_attack_success(self):
        cfg = game.INTRIGUES['rumor']
        atk = game.get_consort(self.atk)
        base = game.intrigue_success_p(atk, game.get_consort(self.tgt), cfg)
        self.maid(self.tgt, '甲', loyalty=70); self.maid(self.tgt, '乙', loyalty=70)
        self.assertAlmostEqual(base - game.intrigue_success_p(atk, game.get_consort(self.tgt), cfg), 0.06 * game.INTRIGUE_CUT_RATIO)

    def test_heart_maids_skip_wages(self):
        game.run('UPDATE consorts SET silver=100, status="normal" WHERE id=?', (self.atk,))
        self.maid(self.atk, '体己', loyalty=85)
        self.maid(self.atk, '寻常', loyalty=60)
        game.maid_upkeep(game.cur_day())
        self.assertEqual(self.me()['silver'], 100 - game.MAID_WAGE)

    # ── 特质 ───────────────────────────────────────────────────────────────

    def test_zuijin_on_the_target_side_makes_spying_harder(self):
        mine = dict(trait='tancai')
        c, t = game.get_consort(self.atk), game.get_consort(self.tgt)
        base = game.spy_success_p(c, t, mine)
        self.maid(self.tgt, trait='zuijin')
        self.assertAlmostEqual(base - game.spy_success_p(c, game.get_consort(self.tgt), mine), 0.15)

    def test_shouqiao_helps_grooming_and_practice(self):
        game.run('UPDATE consorts SET appearance=40, talent=40 WHERE id=?', (self.atk,))
        self.maid(self.atk, trait='shouqiao')
        free = lambda cfg: dict(cfg, energy=0, silver=0)
        game.do_groom(self.me(), free(game.ACTIONS['groom']))
        self.assertEqual(self.me()['appearance'], 40 + 2 + 1)      # 容貌 <70 本来 +2，手巧再 +1
        with self.client.application.test_request_context('/', method='POST', data={'art': game.ARTS[0]}):
            game.do_study(self.me(), free(game.ACTIONS['study']))
        self.assertEqual(self.me()['talent'], 40 + 2 + 1)          # 才艺 <60 本来 +2，手巧再 +1

    def test_zhonghou_maid_may_be_saved_from_punishment(self):
        pun = game.get_consort(self.atk)
        game.run('UPDATE consorts SET rank=7 WHERE id=?', (self.atk,))
        mid = self.maid(self.tgt, '春桃', trait='zhonghou')
        self.maid(self.tgt, '夏荷', trait='zhonghou')
        game.run('UPDATE maids SET joined_day=1')
        self.login(self.atk)
        self.client.post('/intrigue/submit', data={'method': 'punish', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='punish'", one=True)
        self.assertIsNotNone(it)
        with patch.object(game.random, 'random', return_value=0.0):      # 得手，且忠厚的宫人被保下来
            self.assertEqual(game.resolve_intrigue(it)[0], 'success')
        self.assertEqual(len(game.active_maids(self.tgt)), 2)
        note = game.q("SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC", (self.tgt,), one=True)['text']
        self.assertIn('保下了一条命', note)

    def test_traits_descriptions_match_the_new_uses(self):
        for k in game.MAID_TRAITS:
            self.assertTrue(game.MAID_TRAITS[k]['desc'])
        self.assertIn('梳妆', game.MAID_TRAITS['shouqiao']['desc'])
        self.assertIn('守夜', game.MAID_TRAITS['zuijin']['desc'])
        self.assertIn('探风声', game.MAID_TRAITS['suizui']['desc'])
        self.assertIn('多打听', game.MAID_TRAITS['tancai']['desc'])
        self.assertIn('保下来', game.MAID_TRAITS['zhonghou']['desc'])

    def test_maids_page_renders_with_errand_menu(self):
        self.maid(self.atk)
        html = self.client.get('/maids').get_data(as_text=True)
        self.assertIn('今日差使', html)
        self.assertIn('御膳房取点心', html)
        self.assertIn('护主', html)


if __name__ == '__main__':
    unittest.main()
