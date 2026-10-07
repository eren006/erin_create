"""皇嗣成长第一阶段：出生属性、抓周、教养、小事件，见设计文档九点六节 A~D

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HeirTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def heir(self, mother, caretaker=None, gender='皇子', born=None, **kw):
        caretaker = caretaker if caretaker is not None else mother
        born = born if born is not None else game.cur_day()
        fields = dict(mother_id=mother, caretaker_id=caretaker, gender=gender, ordinal=1, born_day=born,
                     personality='clever', study=20, riding=20, virtue=20, health=60,
                     mother_affinity=50, caretaker_affinity=50)
        fields.update(kw)
        cols = ','.join(fields); qs = ','.join('?' * len(fields))
        return game.run(f'INSERT INTO heirs({cols}) VALUES({qs})', list(fields.values())).lastrowid

    # ── 出生 ─────────────────────────────────────────────────────────────────

    def test_birth_rolls_personality_and_inherits_from_mother(self):
        game.run('UPDATE consorts SET talent=90, virtue=90, health=90, pregnant_since=? WHERE id=?',
                (game.cur_day() - game.PREGNANCY_DAYS, self.atk))
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game.random, 'random', return_value=0.99), patch.object(game.random, 'randint', return_value=20), \
             patch.object(game, 'npc_schemes'):
            game.settle_day()
        h = game.q('SELECT * FROM heirs WHERE mother_id=?', (self.atk,), one=True)
        self.assertIsNotNone(h)
        self.assertIn(h['personality'], game.HEIR_PERSONALITIES)
        self.assertEqual(h['caretaker_id'], self.atk)
        self.assertEqual(h['study'], 20 + 9, '基础值固定为 20，才艺 90 该加 9')
        self.assertEqual(h['virtue'], 20 + 9, '德行 90 该加 9')
        self.assertEqual(h['health'], 60 + 9, '体质 90 该加 9')

    # ── 乳母月钱 / 师傅束脩 ───────────────────────────────────────────────────

    def test_upkeep_nurse_then_tutor_and_unpaid_hurts_affinity(self):
        day = game.cur_day()
        young = self.heir(self.atk, born=day)                       # 刚出生：乳母
        old = self.heir(self.atk, born=day - 8 * game.HEIR_DAYS_PER_YEAR)  # 8 岁：师傅
        self.assertEqual(game.heir_upkeep_cost(game.q('SELECT * FROM heirs WHERE id=?', (young,), one=True), day), game.HEIR_NURSE_WAGE)
        self.assertEqual(game.heir_upkeep_cost(game.q('SELECT * FROM heirs WHERE id=?', (old,), one=True), day), game.HEIR_TUTOR_FEE)
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        game.heir_upkeep(day)
        self.assertEqual(game.get_consort(self.atk)['silver'], 1000 - game.HEIR_NURSE_WAGE - game.HEIR_TUTOR_FEE)
        game.run('UPDATE consorts SET silver=0 WHERE id=?', (self.atk,))
        game.heir_upkeep(day)
        self.assertEqual(game.get_consort(self.atk)['silver'], 0)
        for hid in (young, old):
            self.assertEqual(game.q('SELECT caretaker_affinity a FROM heirs WHERE id=?', (hid,), one=True)['a'], 50 + game.HEIR_UNPAID_AFFINITY)
            self.assertEqual(game.q('SELECT caretaker_id c, unpaid_days u FROM heirs WHERE id=?', (hid,), one=True)['u'], 1)
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        game.heir_upkeep(day)      # 付上了，欠账清零
        for hid in (young, old):
            self.assertEqual(game.q('SELECT unpaid_days u FROM heirs WHERE id=?', (hid,), one=True)['u'], 0)

    def test_two_unpaid_nights_sends_heir_to_orphanage(self):
        day = game.cur_day()
        hid = self.heir(self.atk, born=day)
        game.run('UPDATE consorts SET silver=0 WHERE id=?', (self.atk,))
        game.heir_upkeep(day)
        self.assertEqual(game.get_heir(hid)['caretaker_id'], self.atk, '欠一晚还在')
        game.heir_upkeep(day)
        h = game.get_heir(hid)
        self.assertEqual((h['caretaker_id'], h['unpaid_days']), (0, 0), '连欠两晚抱去养育所')

    def test_upkeep_skips_orphanage_and_adults(self):
        self.heir(self.atk, caretaker=0)
        self.heir(self.atk, adult_day=3)
        game.run('UPDATE consorts SET silver=500 WHERE id=?', (self.atk,))
        game.heir_upkeep(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['silver'], 500)

    # ── 降位挤位 ─────────────────────────────────────────────────────────────

    def test_demote_cascades_when_lower_rank_full(self):
        game.run("UPDATE consorts SET status='cold' WHERE rank IN (4,5) AND id!=?", (self.atk,))
        cap = game.RANK_SLOTS[4]
        low = [self.player(f'贵{i}', rank=4) for i in range(cap)]
        for i, cid in enumerate(low): game.run('UPDATE consorts SET favor=? WHERE id=?', (50 + i, cid))
        top = self.player('嫔甲', rank=5)
        game.run('UPDATE consorts SET favor=200 WHERE id=?', (top,))
        game.demote_rank(top)
        ranks = {cid: game.get_consort(cid)['rank'] for cid in low + [top]}
        self.assertEqual(ranks[low[0]], 3, '圣宠最低的贵人被挤下去')
        self.assertEqual(ranks[top], 4)
        self.assertEqual(sum(1 for r in ranks.values() if r == 4), cap, '贵人名额不超员')

    def test_demote_target_pushed_further_if_worst(self):
        game.run("UPDATE consorts SET status='cold' WHERE rank IN (4,5) AND id!=?", (self.atk,))
        low = [self.player(f'贵{i}', rank=4) for i in range(game.RANK_SLOTS[4])]
        for cid in low: game.run('UPDATE consorts SET favor=80 WHERE id=?', (cid,))
        top = self.player('嫔乙', rank=5)
        game.run('UPDATE consorts SET favor=0 WHERE id=?', (top,))
        game.demote_rank(top)
        self.assertEqual(game.get_consort(top)['rank'], 3)

    def test_labor_risk_grows_with_each_prior_birth(self):
        healthy={'health':80}; weak={'health':40}
        self.assertEqual(game.labor_risk(healthy,0),0.0,'头胎体质好的没有难产风险')
        self.assertAlmostEqual(game.labor_risk(healthy,1),0.20)
        self.assertAlmostEqual(game.labor_risk(healthy,2),0.40)
        self.assertAlmostEqual(game.labor_risk(weak,0),0.30)
        self.assertAlmostEqual(game.labor_risk(weak,2),0.70)
        self.assertAlmostEqual(game.labor_risk(weak,2,rests=2),0.50,msg='安胎静养每次 -10 个点')
        self.assertEqual(game.labor_risk(weak,9),game.LABOR_RISK_CAP,'封顶 80%')
        self.assertEqual(game.labor_risk(healthy,0,rests=3),0.0,'不会变成负数')

    def test_hard_labor_can_kill_mother_but_child_stays(self):
        game.run('UPDATE consorts SET talent=90, virtue=90, health=90, pregnant_since=? WHERE id=?',
                (game.cur_day() - game.PREGNANCY_DAYS, self.atk))
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game, 'labor_risk', return_value=1.0), patch.object(game, 'LABOR_DEATH_CHANCE', 1.0), \
             patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['status'], 'dead')
        self.assertEqual(game.get_consort(self.atk)['death_reason'], '难产')
        self.assertIsNotNone(game.q('SELECT id FROM heirs WHERE mother_id=?', (self.atk,), one=True), '孩子保留')

    def test_hard_labor_without_death_roll_survives(self):
        game.run('UPDATE consorts SET talent=90, virtue=90, health=90, pregnant_since=? WHERE id=?',
                (game.cur_day() - game.PREGNANCY_DAYS, self.atk))
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game, 'labor_risk', return_value=1.0), patch.object(game, 'LABOR_DEATH_CHANCE', 0.0), \
             patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertNotEqual(game.get_consort(self.atk)['status'], 'dead')

    # ── 抓周 ─────────────────────────────────────────────────────────────────

    def test_zhuazhou_grants_stat_and_only_fires_once(self):
        hid = self.heir(self.atk, born=8)
        day = 8 + game.ZHUAZHOU_AGE_DAYS
        before = dict(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True))
        with patch.object(game, 'heir_grow_stats'):      # 满 2 岁的长属性另有用例，这里只看抓周
            game.heir_growth_tick(day)
        after = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertTrue(after['zhuazhou'])
        item = next(i for i in game.ZHUAZHOU_ITEMS if i['key'] == after['zhuazhou'])
        self.assertEqual(after[item['stat']], before[item['stat']] + game.ZHUAZHOU_GAIN)
        # 再跑一次不会重复抓
        snap = dict(after)
        with patch.object(game, 'heir_grow_stats'):
            game.heir_growth_tick(day)
        self.assertEqual(dict(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), snap)

    def test_zhuazhou_before_or_after_the_day_does_not_fire(self):
        hid = self.heir(self.atk, born=8)
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS - 1)
        self.assertFalse(game.q('SELECT zhuazhou FROM heirs WHERE id=?', (hid,), one=True)['zhuazhou'])
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS + 1)
        self.assertFalse(game.q('SELECT zhuazhou FROM heirs WHERE id=?', (hid,), one=True)['zhuazhou'], '错过那天就不再补触发')

    def test_low_rank_mother_loses_custody_at_zhuazhou(self):
        game.run('UPDATE consorts SET rank=3 WHERE id=?', (self.atk,))
        self.player('丙', rank=6)
        hid = self.heir(self.atk, born=8)
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS)
        self.assertEqual(game.q('SELECT caretaker_id FROM heirs WHERE id=?', (hid,), one=True)['caretaker_id'], 0)

    def test_high_rank_mother_keeps_custody_at_zhuazhou(self):
        # self.atk 是 setUp 里的嫔（rank 5），位分够
        hid = self.heir(self.atk, born=8)
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS)
        self.assertEqual(game.q('SELECT caretaker_id FROM heirs WHERE id=?', (hid,), one=True)['caretaker_id'], self.atk)

    def test_zhuazhou_picks_foster_with_fewest_wards(self):
        game.run('UPDATE consorts SET rank=3 WHERE id=?', (self.atk,))
        self.player('丙', rank=6)
        hid = self.heir(self.atk, born=8)
        game.heir_growth_tick(8 + game.ZHUAZHOU_AGE_DAYS)
        self.assertEqual(game.q('SELECT caretaker_id FROM heirs WHERE id=?', (hid,), one=True)['caretaker_id'], 0)

    # ── 教养 ─────────────────────────────────────────────────────────────────

    def test_raise_study_gain_and_energy_cost(self):
        hid = self.heir(self.atk, personality='', study=20)   # 没有性格加成，纯看基础值
        e0 = game.get_consort(self.atk)['energy']
        self.client.post(f'/heirs/raise/{hid}', data=dict(opt='study'))
        h = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertEqual(h['study'], 23)
        self.assertEqual(game.get_consort(self.atk)['energy'], e0 - game.HEIR_RAISE_ENERGY)

    def test_gifts_scale_raise_gain(self):
        low = self.heir(self.atk, personality='', study=20, gift_study=70)
        high = self.heir(self.atk, personality='', study=20, gift_study=140)
        self.client.post(f'/heirs/raise/{low}', data=dict(opt='study'))
        self.client.post(f'/heirs/raise/{high}', data=dict(opt='study'))
        g1 = game.q('SELECT study FROM heirs WHERE id=?', (low,), one=True)['study'] - 20
        g2 = game.q('SELECT study FROM heirs WHERE id=?', (high,), one=True)['study'] - 20
        self.assertEqual((g1, g2), (2, 4), '资质 70% 涨 2、140% 涨 4，基础是 3')

    def test_gift_words_and_roll_range_and_inheritance(self):
        self.assertEqual([game.gift_word(v) for v in (60, 85, 105, 125, 150)], ['平庸', '中人之资', '聪颖', '出众', '天纵'])
        smart = dict(talent=100, health=60, virtue=50)
        dull = dict(talent=0, health=60, virtue=50)
        with patch.object(game.random, 'randint', return_value=0):
            self.assertGreater(game.roll_heir_gifts(smart, {})['study'], game.roll_heir_gifts(dull, {})['study'])
            self.assertGreater(game.roll_heir_gifts(dull, {'study': 100})['study'], game.roll_heir_gifts(dull, {'study': 0})['study'])
        for _ in range(200):
            for v in game.roll_heir_gifts(smart, {'study': 100, 'riding': 100, 'virtue': 100}).values():
                self.assertTrue(game.GIFT_MIN <= v <= game.GIFT_MAX)

    def test_born_heirs_get_gifts_and_birth_note(self):
        game.run('UPDATE consorts SET pregnant_since=? WHERE id=?', (game.cur_day() - game.PREGNANCY_DAYS, self.atk))
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game.random, 'random', return_value=0.99), patch.object(game, 'npc_schemes'):
            game.settle_day()
        h = game.q('SELECT * FROM heirs WHERE mother_id=?', (self.atk,), one=True)
        for k in game.GIFT_STATS:
            self.assertTrue(game.GIFT_MIN <= h['gift_' + k] <= game.GIFT_MAX)
        self.assertTrue(any('根骨' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (self.atk,))))
        self.login(self.atk)
        self.assertEqual(self.client.get('/heirs').status_code, 200)

    def test_personality_multiplier_on_study(self):
        clever = self.heir(self.atk, personality='clever', study=20)
        honest = self.heir(self.atk, personality='honest', study=20)
        self.client.post(f'/heirs/raise/{clever}', data=dict(opt='study'))
        self.client.post(f'/heirs/raise/{honest}', data=dict(opt='study'))
        gain_clever = game.q('SELECT study FROM heirs WHERE id=?', (clever,), one=True)['study'] - 20
        gain_honest = game.q('SELECT study FROM heirs WHERE id=?', (honest,), one=True)['study'] - 20
        self.assertGreater(gain_clever, gain_honest, '聪敏读书 ×1.5，该比憨厚（×0.7）涨得多')

    def test_naughty_doubles_play_affinity(self):
        naughty = self.heir(self.atk, personality='naughty', caretaker_affinity=50)
        plain = self.heir(self.atk, personality='clever', caretaker_affinity=50)
        self.client.post(f'/heirs/raise/{naughty}', data=dict(opt='play'))
        self.client.post(f'/heirs/raise/{plain}', data=dict(opt='play'))
        gain_naughty = game.q('SELECT caretaker_affinity FROM heirs WHERE id=?', (naughty,), one=True)['caretaker_affinity'] - 50
        gain_plain = game.q('SELECT caretaker_affinity FROM heirs WHERE id=?', (plain,), one=True)['caretaker_affinity'] - 50
        self.assertEqual(gain_naughty, gain_plain * 2)

    def test_discipline_loses_affinity_and_stubborn_loses_more(self):
        stubborn = self.heir(self.atk, personality='stubborn', caretaker_affinity=50)
        self.client.post(f'/heirs/raise/{stubborn}', data=dict(opt='discipline'))
        loss = 50 - game.q('SELECT caretaker_affinity FROM heirs WHERE id=?', (stubborn,), one=True)['caretaker_affinity']
        self.assertEqual(loss, 2)   # 基础 -1 ×1.5 取整

    def test_princess_gets_qinqi_option_not_riding(self):
        girl = self.heir(self.atk, gender='公主', study=20, virtue=20, riding=20)
        self.client.post(f'/heirs/raise/{girl}', data=dict(opt='ride'))   # 前端会传 ride，后端要识别成 ride_girl
        h = game.q('SELECT * FROM heirs WHERE id=?', (girl,), one=True)
        self.assertEqual(h['riding'], 20, '公主的骑射不该被这个选项影响')
        self.assertGreater(h['study'], 20)
        self.assertGreater(h['virtue'], 20)

    def test_only_current_caretaker_can_raise(self):
        other = self.player('丙', rank=6)
        hid = self.heir(self.atk)
        self.login(other)
        r = self.client.post(f'/heirs/raise/{hid}', data=dict(opt='study'))
        self.assertEqual(game.q('SELECT study FROM heirs WHERE id=?', (hid,), one=True)['study'], 20)

    def test_once_per_day_per_heir(self):
        hid = self.heir(self.atk, study=20)
        self.client.post(f'/heirs/raise/{hid}', data=dict(opt='study'))
        after_first = game.q('SELECT study FROM heirs WHERE id=?', (hid,), one=True)['study']
        self.client.post(f'/heirs/raise/{hid}', data=dict(opt='study'))
        self.assertEqual(game.q('SELECT study FROM heirs WHERE id=?', (hid,), one=True)['study'], after_first)

    # ── 小事件 ───────────────────────────────────────────────────────────────

    def test_roll_heir_event_only_for_own_wards(self):
        self.heir(self.atk)
        with patch.object(game.random, 'random', return_value=0.0):
            game.roll_heir_event(game.get_consort(self.atk))
        self.assertTrue(game.get_consort(self.atk)['heir_event'])

    def test_no_event_without_heirs(self):
        with patch.object(game.random, 'random', return_value=0.0):
            game.roll_heir_event(game.get_consort(self.atk))
        self.assertFalse(game.get_consort(self.atk)['heir_event'])

    def test_foster_only_event_needs_foster_and_age(self):
        old_enough_foster = self.heir(self.tgt, caretaker=self.atk, born=game.cur_day() - game.HEIR_FOSTER_TALK_AGE_DAYS)
        self_raised = self.heir(self.atk, born=game.cur_day() - game.HEIR_FOSTER_TALK_AGE_DAYS)
        too_young_foster = self.heir(self.tgt, caretaker=self.atk, born=game.cur_day())
        # 强制只抽到 foster_only 事件来验证筛选，而不是随机撞上其它事件
        with patch.dict(game.HEIR_EVENTS, {k: v for k, v in game.HEIR_EVENTS.items() if v.get('foster_only')}, clear=True):
            with patch.object(game.random, 'random', return_value=0.0):
                game.roll_heir_event(game.get_consort(self.atk))
        data = __import__('json').loads(game.get_consort(self.atk)['heir_event'] or '{}')
        self.assertEqual(data.get('heir'), old_enough_foster, '只有满足抱养+年龄条件的孩子才会撞上这类事件')

    def test_event_choose_applies_effect_and_marks_seen(self):
        hid = self.heir(self.atk, caretaker_affinity=50)
        game.run("UPDATE consorts SET heir_event=? WHERE id=?",
                (__import__('json').dumps(dict(key='puppy', heir=hid, day=game.cur_day())), self.atk))
        silver0 = game.get_consort(self.atk)['silver']
        self.client.post('/heirs/event', data=dict(opt=0))   # 「准了（10 两）」
        self.assertEqual(game.get_consort(self.atk)['silver'], silver0 - 10)
        h = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertEqual(h['caretaker_affinity'], 55)
        self.assertIn('puppy', __import__('json').loads(h['seen_events']))
        self.assertEqual(game.get_consort(self.atk)['heir_event'], '')

    def test_target_event_moves_affinity_with_other_player(self):
        other = self.player('丙', rank=6)
        hid = self.heir(self.atk)
        game.run("UPDATE consorts SET heir_event=? WHERE id=?",
                (__import__('json').dumps(dict(key='treat', heir=hid, day=game.cur_day(), target=other)), self.atk))
        before = game.relation(self.atk, other)
        self.client.post('/heirs/event', data=dict(opt=0))   # 「收下」
        after = game.relation(self.atk, other)
        self.assertEqual((after['affinity'] if after else 0) - (before['affinity'] if before else 0), 3)

    def test_fever_event_costs_mother_own_health(self):
        hid = self.heir(self.atk)
        game.run("UPDATE consorts SET heir_event=? WHERE id=?",
                (__import__('json').dumps(dict(key='fever', heir=hid, day=game.cur_day())), self.atk))
        health0 = game.get_consort(self.atk)['health']
        self.client.post('/heirs/event', data=dict(opt=0))   # 「守一夜」
        self.assertEqual(game.get_consort(self.atk)['health'], health0 - 5)

    def test_admin_reset_clears_heirs(self):
        self.heir(self.atk)
        with self.client.session_transaction() as sess: sess['admin'] = True
        self.client.post('/admin/reset', data={'confirm': '重开'})
        self.assertFalse(game.q("SELECT 1 FROM heirs WHERE npc_key=''"), '玩家的孩子清掉')
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs', one=True)['n'], 0, '新开局没有预设皇嗣')

    # ── 2 岁起每岁长 4 点属性 ───────────────────────────────────────────────

    def test_stats_grow_four_points_per_year_from_age_two(self):
        sums = lambda r: sum(r[k] for k in ('study', 'riding', 'virtue', 'health'))
        baby = self.heir(self.atk, born=game.cur_day() - game.HEIR_DAYS_PER_YEAR * 1)     # 1 岁，还不涨
        kid = self.heir(self.atk, born=game.cur_day() - game.HEIR_DAYS_PER_YEAR * 10)     # 10 岁，一次补 2..10 岁共 9 岁
        before = {i: sums(game.get_heir(i)) for i in (baby, kid)}
        game.heir_grow_stats(game.cur_day())
        self.assertEqual(sums(game.get_heir(baby)), before[baby])
        self.assertEqual(sums(game.get_heir(kid)), before[kid] + 4 * 9)
        self.assertEqual(game.get_heir(kid)['attr_years'], 10)
        game.heir_grow_stats(game.cur_day())                                              # 再跑不重复涨
        self.assertEqual(sums(game.get_heir(kid)), before[kid] + 4 * 9)

    def test_stats_growth_stops_at_cap_and_adulthood(self):
        kid = self.heir(self.atk, born=game.cur_day() - game.HEIR_DAYS_PER_YEAR * 10, study=100, riding=100, virtue=100, health=99)
        game.heir_grow_stats(game.cur_day())
        self.assertEqual(game.get_heir(kid)['health'], 100)
        grown = self.heir(self.atk, born=game.cur_day() - game.HEIR_DAYS_PER_YEAR * 10, adult_day=1)
        game.heir_grow_stats(game.cur_day())
        self.assertEqual(game.get_heir(grown)['study'], 20)


class HeirExamHuntTests(unittest.TestCase):
    """皇上考校、随驾秋狝，见设计文档九点六节 D"""
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def heir(self, mother, caretaker=None, gender='皇子', age_years=10, **kw):
        caretaker = caretaker if caretaker is not None else mother
        born = game.cur_day() - age_years * game.HEIR_DAYS_PER_YEAR
        fields = dict(mother_id=mother, caretaker_id=caretaker, gender=gender, ordinal=1, born_day=born,
                     personality='clever', study=20, riding=20, virtue=20, health=60,
                     mother_affinity=50, caretaker_affinity=50)
        fields.update(kw)
        cols = ','.join(fields); qs = ','.join('?' * len(fields))
        return game.run(f'INSERT INTO heirs({cols}) VALUES({qs})', list(fields.values())).lastrowid

    # ── 考校 ─────────────────────────────────────────────────────────────────

    def test_exam_only_fires_on_interval_days(self):
        self.heir(self.atk)
        day = game.cur_day()
        off_day = day if day % game.HEIR_EXAM_INTERVAL == 0 else day + (game.HEIR_EXAM_INTERVAL - day % game.HEIR_EXAM_INTERVAL) + 1
        game.heir_exam_tick(off_day)
        self.assertFalse(game.get_consort(self.atk)['pending_scene'])

    def test_exam_age_window(self):
        day = game.HEIR_EXAM_INTERVAL * 10   # 考校间隔的倍数
        game.run('UPDATE game_state SET day=?', (day,))
        too_young = self.heir(self.atk, age_years=5)
        too_old = self.player('丙', rank=6)
        self.heir(too_old, age_years=16)
        game.heir_exam_tick(day)
        self.assertFalse(game.get_consort(self.atk)['pending_scene'], '5 岁还不到考校的年纪')
        self.assertFalse(game.get_consort(too_old)['pending_scene'], '16 岁已经过了考校的年纪')

    def test_exam_skips_when_caretaker_already_has_a_scene(self):
        day = game.HEIR_EXAM_INTERVAL * 10
        game.run('UPDATE game_state SET day=?', (day,))
        self.heir(self.atk)
        game.start_scene(self.atk, 'audience', prompt=0, bed=1)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_exam_tick(day)
        sc = game.get_scene(game.get_consort(self.atk))
        self.assertEqual(sc['key'], 'audience', '当晚已经有场景在排队，考校不该把它顶掉')

    def test_exam_judges_heir_stat_not_caretaker_stat(self):
        day = game.HEIR_EXAM_INTERVAL * 10
        game.run('UPDATE game_state SET day=?', (day,))
        game.run('UPDATE consorts SET talent=0, scheme=0, virtue=0 WHERE id=?', (self.atk,))   # 抚养人自己属性拉满低
        hid = self.heir(self.atk, study=100, riding=100, virtue=100)   # 孩子属性拉满
        with patch.object(game.random, 'random', return_value=0.0), \
             patch.object(game.random, 'randrange', return_value=0):
            game.heir_exam_tick(day)
        self.login(self.atk)
        r = self.client.post('/scene', data=dict(opt=0))
        h = game.q('SELECT favor FROM heirs WHERE id=?', (hid,), one=True)
        self.assertGreater(h['favor'], 0, '孩子属性拉满，就算抚养人自己属性是 0 也该判定成功')

    def test_exam_gone_heir_does_not_crash(self):
        day = game.HEIR_EXAM_INTERVAL * 10
        game.run('UPDATE game_state SET day=?', (day,))
        hid = self.heir(self.atk)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_exam_tick(day)
        game.run('DELETE FROM heirs WHERE id=?', (hid,))
        self.login(self.atk)
        r = self.client.get('/scene')
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post('/scene', data=dict(opt=0))
        self.assertEqual(r2.status_code, 302)

    # ── 秋狝 ─────────────────────────────────────────────────────────────────

    def test_hunt_only_fires_on_interval_days(self):
        self.heir(self.atk, age_years=13, riding=90)
        day = game.cur_day()
        off_day = day if day % game.HEIR_HUNT_INTERVAL == 0 else day + 1
        while off_day % game.HEIR_HUNT_INTERVAL == 0: off_day += 1
        game.heir_hunt_tick(off_day)
        self.assertFalse(game.q('SELECT 1 FROM heirs WHERE favor>0'))

    def test_hunt_excludes_too_young_and_princesses(self):
        day = game.HEIR_HUNT_INTERVAL * 5
        game.run('UPDATE game_state SET day=?', (day,))
        young = self.heir(self.atk, age_years=11, riding=99)
        girl = self.heir(self.atk, gender='公主', age_years=13, riding=99)
        winner = self.heir(self.atk, age_years=13, riding=50)
        with patch.object(game.random, 'randint', return_value=0):
            game.heir_hunt_tick(day)
        self.assertEqual(game.q('SELECT favor FROM heirs WHERE id=?', (young,), one=True)['favor'], 0)
        self.assertEqual(game.q('SELECT favor FROM heirs WHERE id=?', (girl,), one=True)['favor'], 0)
        self.assertEqual(game.q('SELECT favor FROM heirs WHERE id=?', (winner,), one=True)['favor'], game.HEIR_HUNT_REWARD)

    def test_hunt_no_eligible_princes_does_nothing(self):
        day = game.HEIR_HUNT_INTERVAL * 5
        game.run('UPDATE game_state SET day=?', (day,))
        game.heir_hunt_tick(day)   # 不该报错


if __name__ == '__main__':
    unittest.main()
