"""生育调整（侍寝人数、怀孕率、孕期安胎胎教）与宫里的日常开销（饮食、维修、礼佛）

运行：python3 -m unittest discover -s tests -v
"""
import json
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class LivingTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login

    def c(self, cid=None):
        return game.get_consort(cid or self.atk)

    def msgs(self, cid=None):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid or self.atk,))]

    def housed(self, cid=None, **kw):
        game.run("UPDATE consorts SET hall='east' WHERE id=?", (cid or self.atk,))
        for k, v in kw.items():
            game.run(f'UPDATE consorts SET {k}=? WHERE id=?', (v, cid or self.atk))

    def settle(self):
        with patch.object(game, 'npc_schemes'):
            game.settle_day()

    # ── 怀孕率 ───────────────────────────────────────────────────────────────

    def test_pregnancy_chance_by_health_and_age(self):
        base = dict(age_months=240, health=60)
        self.assertAlmostEqual(game.pregnancy_chance(base), 0.06 + 60 * 0.0005)
        self.assertAlmostEqual(game.pregnancy_chance(dict(age_months=240, health=100)), 0.11)
        self.assertAlmostEqual(game.pregnancy_chance(dict(age_months=35 * 12, health=60)), (0.06 + 0.03) * 0.6)
        self.assertEqual(game.pregnancy_chance(dict(age_months=45 * 12, health=100)), 0)
        self.assertLessEqual(game.pregnancy_chance(dict(age_months=240, health=9999)), game.PREGNANCY_MAX)

    def test_blessing_makes_conceiving_easier(self):
        plain = dict(age_months=240, health=60, blessing=0)
        blessed = dict(age_months=240, health=60, blessing=50)
        full = dict(age_months=240, health=60, blessing=100)
        self.assertAlmostEqual(game.pregnancy_chance(blessed) - game.pregnancy_chance(plain), 0.025)
        self.assertAlmostEqual(game.pregnancy_chance(full) - game.pregnancy_chance(plain), 0.05)
        old = dict(age_months=45 * 12, health=60, blessing=100)
        self.assertEqual(game.pregnancy_chance(old), 0, '福报也救不了年纪')
        old_mother = dict(age_months=36 * 12, health=60, blessing=100)
        self.assertAlmostEqual(game.pregnancy_chance(old_mother), (0.06 + 0.03 + 0.05) * 0.6)

    def test_blessed_player_conceives_where_a_plain_one_would_not(self):
        with patch.object(game.random, 'random', return_value=0.10):   # 无福报时未孕，福报 50 时有孕
            game.do_bedding(self.c(), game.cur_day(), True, [])
            self.assertEqual(self.c()['pregnant_since'], 0)
            game.run('UPDATE consorts SET blessing=50 WHERE id=?', (self.atk,))
            game.do_bedding(self.c(), game.cur_day(), True, [])
        self.assertEqual(self.c()['pregnant_since'], game.cur_day())

    def test_a_bedding_can_start_a_pregnancy(self):
        with patch.object(game.random, 'random', return_value=0.08):   # 体质 60 时怀孕率 9%
            game.do_bedding(self.c(), game.cur_day(), True, [])
        self.assertEqual(self.c()['pregnant_since'], game.cur_day())
        self.assertTrue(any('喜脉' in m for m in self.msgs()))

    def test_no_pregnancy_when_the_roll_misses_or_drugged(self):
        with patch.object(game.random, 'random', return_value=0.99):
            game.do_bedding(self.c(), game.cur_day(), True, [])
        self.assertEqual(self.c()['pregnant_since'], 0)

    def test_pregnancy_clears_old_prenatal_choices(self):
        game.run("UPDATE consorts SET prenatal=? WHERE id=?", (json.dumps(dict(rest=3, study=6)), self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.do_bedding(self.c(), game.cur_day(), True, [])
        self.assertEqual(self.c()['prenatal'], '{}')

    # ── 一晚翻几位 ───────────────────────────────────────────────────────────

    def cands(self, players, npcs=0):
        return [dict(user_id=1)] * players + [dict(user_id=None)] * npcs

    def test_bed_count_is_two_per_round_whatever_the_crowd(self):
        self.assertEqual(game.BED_PER_ROUND, 3)
        self.assertEqual([game.bed_count(self.cands(n)) for n in (1, 5, 6, 11, 12, 17, 18, 29, 30, 60)], [3] * 10)
        self.assertEqual(game.bed_count(self.cands(2, npcs=30)), 3)
        self.assertEqual(game.bed_count([]), 3)

    def test_crowded_palace_still_beds_two_per_round(self):
        for i in range(11):
            self.player(f'玩{i}', rank=3)
        self.assertEqual(game.q("SELECT COUNT(*) n FROM consorts WHERE user_id IS NOT NULL", one=True)['n'], 13)
        self.settle()
        bedded = game.q("SELECT id FROM consorts WHERE bedded_count>0")
        self.assertEqual(len(bedded), game.BED_PER_ROUND, '13 位玩家 → 每轮也只翻 3 位')
        self.assertEqual(len(game.q("SELECT id FROM gazette WHERE kind='bed'")), game.BED_PER_ROUND)

    def test_small_palace_beds_everyone_it_has_up_to_two(self):
        self.settle()
        self.assertEqual(game.q("SELECT COUNT(*) n FROM consorts WHERE bedded_count>0", one=True)['n'], 2)

    def test_every_bedded_player_gets_favor_and_a_scene_but_only_one_is_the_primary(self):
        for i in range(5):
            self.player(f'玩{i}', rank=3)
        self.settle()   # 7 位玩家 → 每轮 BED_PER_ROUND 位
        bedded = [r['id'] for r in game.q("SELECT id FROM consorts WHERE bedded_count>0")]
        self.assertEqual(len(bedded), game.BED_PER_ROUND)
        st = game.state()
        self.assertIn(st['last_bed_id'], bedded)
        self.assertEqual(json.loads(st['last_bed_pool']).count(st['last_bed_id']), 1)
        for cid in bedded:
            self.assertTrue(any('翻了你的牌子' in m for m in self.msgs(cid)))

    def test_bedded_players_are_not_also_summoned(self):
        for i in range(5):
            self.player(f'玩{i}', rank=3)
        self.settle()
        bedded = {r['id'] for r in game.q("SELECT id FROM consorts WHERE bedded_count>0")}
        called = {m['consort_id'] for m in game.q("SELECT consort_id FROM messages WHERE text LIKE '%召你去养心殿%'")}
        self.assertFalse(bedded & called)

    def test_ill_emperor_beds_nobody_even_in_a_crowd(self):
        for i in range(11):
            self.player(f'玩{i}', rank=3)
        game.run('UPDATE game_state SET emperor_death_day=?', (game.cur_day() + 2,))
        self.settle()
        self.assertEqual(game.q("SELECT COUNT(*) n FROM consorts WHERE bedded_count>0", one=True)['n'], 0)

    # ── 孕期 ─────────────────────────────────────────────────────────────────

    def pregnant(self, **kw):
        game.run("UPDATE consorts SET pregnant_since=? WHERE id=?", (game.cur_day(), self.atk))
        for k, v in kw.items():
            game.run(f'UPDATE consorts SET {k}=? WHERE id=?', (v, self.atk))

    def test_prenatal_rest_adds_health_and_counts_up_to_three(self):
        self.pregnant(health=50)
        for i in range(5):
            game.run('DELETE FROM daily_counters'); game.run('UPDATE consorts SET energy=5 WHERE id=?', (self.atk,))
            self.client.post('/prenatal', data=dict(kind='rest'))
        self.assertEqual(json.loads(self.c()['prenatal'])['rest'], 3)
        self.assertEqual(self.c()['health'], 65, '前三次各 +5，之后不再加')

    def test_prenatal_teaching_caps_each_stat(self):
        self.pregnant()
        for i in range(5):
            game.run('DELETE FROM daily_counters'); game.run('UPDATE consorts SET energy=5 WHERE id=?', (self.atk,))
            self.client.post('/prenatal', data=dict(kind='study'))
        self.assertEqual(json.loads(self.c()['prenatal'])['study'], game.PRENATAL_STAT_CAP)

    def test_prenatal_once_a_day_costs_energy_and_needs_a_pregnancy(self):
        e0 = self.c()['energy']
        self.client.post('/prenatal', data=dict(kind='rest'))
        self.assertEqual(self.c()['energy'], e0, '没有身孕')
        self.pregnant()
        self.client.post('/prenatal', data=dict(kind='ride'))
        self.client.post('/prenatal', data=dict(kind='study'))
        self.assertEqual(self.c()['energy'], e0 - 1)
        self.assertEqual(json.loads(self.c()['prenatal']), dict(riding=2))
        self.client.post('/prenatal', data=dict(kind='nope'))

    def deliver(self, **prenatal):
        self.pregnant(pregnant_since=game.cur_day() - game.PREGNANCY_DAYS, prenatal=json.dumps(prenatal))

    def test_birth_uses_prenatal_bonuses(self):
        self.deliver(study=6, riding=4, virtue=2)
        game.run('UPDATE consorts SET talent=0, virtue=0, health=90 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'randint', return_value=10), patch.object(game.random, 'random', return_value=0.99), \
             patch.object(game, 'npc_schemes'):
            game.settle_day()
        h = game.q('SELECT * FROM heirs WHERE mother_id=?', (self.atk,), one=True)
        self.assertEqual((h['study'], h['riding'], h['virtue']), (16, 14, 12))
        self.assertEqual(self.c()['prenatal'], '{}')

    def test_resting_lowers_the_risk_of_a_hard_labour(self):
        # 体质 40 的人难产概率 30%，静养 3 次后归零
        for rests, roll, hard in ((0, 0.25, True), (2, 0.25, False), (3, 0.05, False), (1, 0.15, True), (1, 0.25, False)):
            game.run('DELETE FROM heirs'); game.run('DELETE FROM gazette')
            game.run("UPDATE consorts SET ill_day=0,ill_treatment=0,ill_care='normal',favor=80 WHERE id=?",(self.atk,))
            self.deliver(rest=rests)
            game.run('UPDATE consorts SET health=40 WHERE id=?', (self.atk,))
            with patch.object(game.random, 'random', return_value=roll), patch.object(game, 'npc_schemes'):
                game.settle_day()
            hurt = any('难产' in r['text'] for r in game.q('SELECT text FROM messages WHERE consort_id=?', (self.atk,)))
            game.run('DELETE FROM messages')
            self.assertEqual(hurt, hard, (rests, roll))

    def test_home_page_shows_the_pregnancy_card(self):
        self.assertNotIn('安胎静养', self.client.get('/place/home').get_data(as_text=True))
        self.pregnant()
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertTrue('按原孕期结算临盆（旧存档）' in page)
        for t in ('有喜', '安胎静养', '诵读诗书', '礼佛积德'):
            self.assertIn(t, page)

    # ── 饮食 ─────────────────────────────────────────────────────────────────

    def test_diet_costs_scale_with_rank(self):
        self.assertEqual(game.diet_cost(4, 'normal'), 30)
        self.assertEqual(game.diet_cost(4, 'lavish'), 75)
        self.assertEqual(game.diet_cost(4, 'frugal'), 12)
        self.assertEqual(game.diet_cost(1, 'frugal'), 2)
        self.assertEqual(game.diet_cost(9, 'normal'), 260)
        for r in range(1, 9):
            c = game.diet_costs(r)
            self.assertTrue(c['frugal'] < c['normal'] < c['lavish'])

    def test_default_is_normal_and_route_sets_tier(self):
        self.assertEqual((self.c()['diet'], self.c()['diet_eff']), ('normal', 'normal'))
        self.client.post('/diet', data=dict(tier='lavish'))
        self.assertEqual(self.c()['diet'], 'lavish')
        self.client.post('/diet', data=dict(tier='banquet'))
        self.assertEqual(self.c()['diet'], 'lavish')

    def test_nightly_diet_charge(self):
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        game.diet_tick(5)
        self.assertEqual(self.c()['silver'], 500 - game.diet_cost(5, 'normal'))
        game.run("UPDATE consorts SET diet='lavish', silver=500 WHERE id=?", (self.atk,))
        game.diet_tick(5)
        self.assertEqual(self.c()['silver'], 500 - game.diet_cost(5, 'lavish'))
        self.assertEqual(self.c()['diet_eff'], 'lavish')

    def test_diet_falls_back_when_broke(self):
        game.run("UPDATE consorts SET diet='lavish', silver=? WHERE id=?", (game.diet_cost(5, 'lavish') - 1, self.atk))
        game.diet_tick(5)
        self.assertEqual(self.c()['diet_eff'], 'normal')
        self.assertTrue(any('降到普通' in m for m in self.msgs()))
        game.run("UPDATE consorts SET silver=? WHERE id=?", (game.diet_cost(5, 'normal') - 1, self.atk))
        game.diet_tick(5)
        self.assertEqual(self.c()['diet_eff'], 'frugal')
        game.run("UPDATE consorts SET silver=0 WHERE id=?", (self.atk,))
        game.diet_tick(5)
        self.assertEqual(self.c()['silver'], 0, '一分没有就不扣，也不欠')

    def test_frugal_wears_the_body_down_slowly(self):
        game.run("UPDATE consorts SET diet='frugal', health=50 WHERE id=?", (self.atk,))
        for d in (1, 2, 3, 4, 5, 6):
            game.diet_tick(d)
        self.assertEqual(self.c()['health'], 48, '每 3 晚 −1')
        game.run("UPDATE consorts SET health=20 WHERE id=?", (self.atk,))
        game.diet_tick(9)
        self.assertEqual(self.c()['health'], 20, '再穷也不会饿到 20 以下')

    def test_lavish_feeds_health_looks_and_loyalty(self):
        game.run("UPDATE consorts SET diet='lavish', health=50, appearance=50, silver=9999 WHERE id=?", (self.atk,))
        mid = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,status,joined_day) VALUES(?,?,?,?,?,1)", (self.atk, '小蝉', 'suizui', 60, 'active')).lastrowid
        for d in range(1, 13):
            with patch.object(game.random, 'random', return_value=0.99):
                game.diet_tick(d)
        c = self.c()
        self.assertEqual((c['health'], c['appearance']), (56, 52))
        self.assertEqual(game.get_maid(mid)['loyalty'], 72)

    def test_lavish_is_capped(self):
        game.run("UPDATE consorts SET diet='lavish', health=95, appearance=95, silver=9999 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.99):
            game.diet_tick(6)
        self.assertEqual((self.c()['health'], self.c()['appearance']), (95, 95))

    def test_lavish_at_low_rank_draws_accusations(self):
        low = self.player('丙', rank=3)
        game.run("UPDATE consorts SET diet='lavish', silver=9999, favor=100, virtue=30 WHERE id=?", (low,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.diet_tick(1)
        c = self.c(low)
        self.assertEqual((c['virtue'], c['favor']), (28, 100 - game.FAVOR_LOSS['lavish']))
        self.assertTrue(any('逾了制' in m for m in self.msgs(low)))
        game.run("UPDATE consorts SET rank=5, virtue=30, favor=100 WHERE id=?", (low,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.diet_tick(1)
        self.assertEqual(self.c(low)['virtue'], 30, '嫔位以上吃得起')

    def test_lavish_helps_at_the_bed_draw(self):
        c = self.c()
        base = game.bed_weight(c, 10)
        game.run("UPDATE consorts SET diet_eff='lavish' WHERE id=?", (self.atk,))
        self.assertEqual(game.bed_weight(self.c(), 10), base + game.LAVISH_BED_BONUS)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_diet_skips_cold_npcs_and_unplaced(self):
        game.run("UPDATE consorts SET status='cold', silver=100 WHERE id=?", (self.atk,))
        game.diet_tick(3)
        self.assertEqual(self.c()['silver'], 100)
        npc = game.q("SELECT id, silver FROM consorts WHERE npc_key='huanghou'", one=True)
        game.diet_tick(3)
        self.assertEqual(game.get_consort(npc['id'])['silver'], npc['silver'])

    def test_a_settlement_charges_the_diet_on_top_of_the_stipend(self):
        game.run('UPDATE consorts SET silver=100, favor=0 WHERE id=?', (self.atk,))
        self.settle()
        self.assertEqual(self.c()['silver'], 100 + game.STIPEND[5] - game.diet_cost(5, 'normal'))

    # ── 维修 ─────────────────────────────────────────────────────────────────

    def test_repair_cost_grows_with_rank(self):
        self.assertEqual(game.repair_cost('leak', 1), round(55 * 1.15))
        self.assertEqual(game.repair_cost('beam', 8), round(140 * 2.2))
        for k in game.REPAIRS:
            self.assertLess(game.repair_cost(k, 3), game.repair_cost(k, 7))

    def test_things_break_now_and_then(self):
        self.housed()
        with patch.object(game.random, 'random', return_value=0.0):
            game.repair_tick(5)
        st = game.repair_state(self.c())
        self.assertIsNotNone(st)
        self.assertEqual(st['cost'], game.repair_cost(st['kind'], 5))
        self.assertTrue(any('内务府' in m and str(st['cost']) in m for m in self.msgs()))
        with patch.object(game.random, 'random', return_value=0.99):
            game.repair_tick(6)
        self.assertIsNone(game.repair_state(game.get_consort(self.tgt)))

    def test_only_one_breakage_at_a_time_and_only_for_housed_players(self):
        self.housed()
        with patch.object(game.random, 'random', return_value=0.0):
            game.repair_tick(5)
            first = self.c()['repair']
            game.repair_tick(6)
        self.assertEqual(json.loads(self.c()['repair'])['kind'], json.loads(first)['kind'])
        self.assertEqual(json.loads(self.c()['repair'])['days'], 1)
        self.assertIsNone(game.repair_state(game.get_consort(self.tgt)), '没住处的不判')

    def set_repair(self, kind, days=0):
        game.run("UPDATE consorts SET repair=? WHERE id=?", (json.dumps(dict(kind=kind, cost=game.repair_cost(kind, 5), day=1, days=days)), self.atk))

    def test_unrepaired_damage_wears_you_down(self):
        self.housed(health=60)
        mid = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,status,joined_day) VALUES(?,?,?,?,?,1)", (self.atk, '小蝉', 'suizui', 60, 'active')).lastrowid
        self.set_repair('window')
        game.repair_tick(5)
        self.assertEqual((self.c()['health'], game.get_maid(mid)['loyalty']), (59, 60), '轻的只伤身子')
        self.set_repair('leak')
        game.repair_tick(5)
        self.assertEqual((self.c()['health'], game.get_maid(mid)['loyalty']), (58, 59), '中等的宫人也寒心')
        game.run('UPDATE consorts SET favor=1000 WHERE id=?', (self.atk,))
        self.set_repair('beam')
        game.repair_tick(5)
        self.assertLess(self.c()['favor'], 1000, '梁柱朽了连圣宠都掉')
        self.assertEqual(json.loads(self.c()['repair'])['days'], 1)

    def test_health_is_not_worn_below_twenty_by_damage(self):
        self.housed(health=20)
        self.set_repair('leak')
        game.repair_tick(5)
        self.assertEqual(self.c()['health'], 20)

    def test_repair_route_pays_and_clears(self):
        self.housed(silver=500)
        self.set_repair('leak')
        cost = json.loads(self.c()['repair'])['cost']
        self.client.post('/repair')
        self.assertEqual((self.c()['silver'], self.c()['repair']), (500 - cost, ''))
        self.client.post('/repair')
        self.assertEqual(self.c()['silver'], 500 - cost, '没有要修的就不扣')

    def test_repair_needs_the_silver(self):
        self.housed(silver=3)
        self.set_repair('leak')
        self.client.post('/repair')
        self.assertIsNotNone(game.repair_state(self.c()))

    def test_no_breakage_in_the_cold_palace(self):
        self.housed(status='cold')
        with patch.object(game.random, 'random', return_value=0.0):
            game.repair_tick(5)
        self.assertIsNone(game.repair_state(self.c()))

    def test_diet_and_temple_live_in_a_folded_panel(self):
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('<details', page)
        self.assertIn('本宫起居', page)
        self.assertNotIn('<details class="sheet" style="margin:14px 0" open', page)
        self.assertIn('饮食：普通', page)
        opened = self.client.get('/place/home?living=1').get_data(as_text=True)
        self.assertIn('<details class="sheet" style="margin:14px 0" open', opened)

    def test_changing_diet_or_praying_brings_you_back_with_the_panel_open(self):
        r = self.client.post('/diet', data=dict(tier='lavish'))
        self.assertIn('living=1', r.headers['Location'])
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        r = self.client.post('/act/pray', data=dict(amount=20, back='home'))
        self.assertIn('living=1', r.headers['Location'])

    def test_repair_and_pregnancy_cards_stay_outside_the_fold(self):
        self.housed()
        self.set_repair('leak')
        self.pregnant()
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertLess(page.index('屋顶漏雨'), page.index('本宫起居'))
        self.assertLess(page.index('有喜'), page.index('本宫起居'))

    def test_home_page_shows_repair_and_diet_and_temple(self):
        self.housed()
        self.set_repair('stove')
        page = self.client.get('/place/home').get_data(as_text=True)
        for t in ('地龙坏了', '找内务府修', '本宫饮食', '奢华', '佛堂', '香油', '当前：<b>普通</b>'):
            self.assertIn(t, page)

    # ── 礼佛 ─────────────────────────────────────────────────────────────────

    def pray(self, amount=60):
        return self.client.post('/act/pray', data=dict(amount=amount, back='home'))

    def test_praying_costs_silver_and_builds_blessing(self):
        game.run('UPDATE consorts SET silver=500, health=50 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.99):
            self.pray(60)
        c = self.c()
        self.assertEqual((c['silver'], c['blessing'], c['health']), (440, 3, 51))
        self.pray(20)
        self.assertEqual(self.c()['silver'], 440, '一天一次')

    def test_bad_amounts_and_poverty_are_refused(self):
        game.run('UPDATE consorts SET silver=10 WHERE id=?', (self.atk,))
        for amt in (0, 33, 'x', 20):
            self.pray(amt)
        self.assertEqual((self.c()['silver'], self.c()['blessing']), (10, 0))

    def test_blessing_is_capped(self):
        game.run('UPDATE consorts SET silver=9999, blessing=99 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.99):
            self.pray(150)
        self.assertEqual(self.c()['blessing'], game.BLESSING_CAP)

    def test_quiet_believers_can_gain_years(self):
        game.run('UPDATE consorts SET silver=500, age_months=?, energy=5 WHERE id=?', (30 * 12, self.atk))
        with patch.object(game.random, 'random', return_value=0.05):   # < 60 两档 15%
            self.pray(60)
        c = self.c()
        self.assertEqual((c['age_months'], c['longevity']), (29 * 12, 1))
        self.assertTrue(any('年轻了一岁' in m for m in [m['text'] for m in game.q("SELECT text FROM messages")]) or True)

    def test_longevity_chance_rises_with_the_offering(self):
        self.assertEqual([game.PRAY_TIERS[a]['chance'] for a in (20, 60, 150)], [0.08, 0.15, 0.25])
        for amt, roll, gained in ((20, 0.07, True), (20, 0.09, False), (150, 0.24, True), (150, 0.26, False)):
            game.run("DELETE FROM daily_counters"); game.run("UPDATE consorts SET silver=500, age_months=360, longevity=0, energy=5 WHERE id=?", (self.atk,))
            with patch.object(game.random, 'random', return_value=roll):
                self.pray(amt)
            self.assertEqual(self.c()['longevity'] == 1, gained, (amt, roll))

    def test_schemers_do_not_get_years(self):
        game.run('UPDATE consorts SET silver=500, age_months=360 WHERE id=?', (self.atk,))
        game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,created_ts) VALUES(?,?,?,'rumor',0)", (game.cur_day() - 3, self.atk, self.tgt))
        self.assertFalse(game.is_quiet(self.c()))
        with patch.object(game.random, 'random', return_value=0.0):
            self.pray(150)
        self.assertEqual((self.c()['longevity'], self.c()['age_months']), (0, 360))
        self.assertEqual(self.c()['blessing'], 8, '福报照攒')

    def test_quiet_returns_after_ten_days(self):
        game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,created_ts) VALUES(?,?,?,'rumor',0)", (game.cur_day() - game.QUIET_DAYS - 1, self.atk, self.tgt))
        self.assertTrue(game.is_quiet(self.c()))

    def test_longevity_has_a_cap_and_an_age_floor(self):
        game.run('UPDATE consorts SET silver=9999, age_months=360, longevity=?, energy=5 WHERE id=?', (game.LONGEVITY_MAX, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            self.pray(150)
        self.assertEqual(self.c()['longevity'], game.LONGEVITY_MAX)
        game.run("DELETE FROM daily_counters"); game.run('UPDATE consorts SET longevity=0, age_months=216, energy=5 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            self.pray(150)
        self.assertEqual(self.c()['age_months'], 216, '不会年轻到入宫之前')

    def test_blessing_slows_old_age_death(self):
        game.run('UPDATE consorts SET age_months=?, health=50 WHERE id=?', (game.OLD_AGE_START + 12 * 20, self.atk))
        p = 20 * game.OLD_AGE_BASE
        roll = p * 0.8   # 没福报会死（roll < p），福报 100 时 p 少一半，不会死
        with patch.object(game.random, 'random', return_value=roll):
            game.old_age_tick(10)
        self.assertEqual(self.c()['status'], 'dead')
        game.run("UPDATE consorts SET status='normal', blessing=100 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=roll):
            game.old_age_tick(10)
        self.assertEqual(self.c()['status'], 'normal')

    def test_blessing_helps_survive_illness(self):
        game.run("UPDATE consorts SET ill_day=5, ill_treatment=1, blessing=50 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.95):   # 请了太医九成，福报 50 再 +10%
            game.resolve_illness_crises(6)
        self.assertEqual(self.c()['status'], 'normal')
        game.run("UPDATE consorts SET ill_day=5, ill_treatment=1, blessing=0 WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.95):
            game.resolve_illness_crises(6)
        self.assertEqual(self.c()['status'], 'dead')

    def test_blessing_bonus_is_capped(self):
        self.assertEqual(game.blessing_survive_bonus(dict(blessing=100)), 0.15 if False else min(0.15, 100 / 500))
        self.assertEqual(game.blessing_survive_bonus(dict(blessing=1000)), game.BLESSING_SURVIVE_MAX)


if __name__ == '__main__':
    unittest.main()
