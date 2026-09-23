"""夺嫡第一阶段：系统皇子、圣眷公式、党羽、野心、站队、立储/废储、万寿节、手段，见设计文档九点六节 F

运行：python3 -m unittest discover -s tests -v
"""
import sqlite3
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class SuccessionTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def seed(self):
        db = sqlite3.connect(game.DB_PATH)
        game.seed_npc_heirs(db)
        db.commit(); db.close()

    def prince(self, mother, age_years=13, **kw):
        kw.setdefault('title', '')
        return self.heir(mother, gender='皇子', born=game.cur_day() - age_years * 2, zhuazhou='book', **kw)

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def flat_stats(self, hid, **kw):
        """把三项基础属性压成 0，只留累计功绩，方便对圣眷做算术"""
        game.run('UPDATE heirs SET study=0, riding=0, virtue=0 WHERE id=?', (hid,))
        game.run('UPDATE consorts SET trust=0 WHERE id IN (SELECT caretaker_id FROM heirs WHERE id=?)', (hid,))

    # ── 系统皇子 ─────────────────────────────────────────────────────────────

    def test_seed_creates_third_and_fourth_prince_once(self):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='qifei'")
        self.seed(); self.seed()
        rows = game.q('SELECT * FROM heirs WHERE npc_key!=? ORDER BY ordinal', ('',))
        self.assertEqual([r['ordinal'] for r in rows], [3, 4])
        third, fourth = rows
        self.assertEqual(game.get_consort(third['caretaker_id'])['npc_key'], 'qifei', '三阿哥是齐妃所出')
        self.assertEqual((fourth['mother_id'], fourth['caretaker_id']), (0, 0), '四阿哥生母早逝、没人抚养')
        self.assertEqual(game.heir_age_years(third), 14)
        self.assertEqual(game.heir_age_years(fourth), 8)
        self.assertEqual(fourth['orphan_deadline_day'], game.cur_day() + game.NPC_ORPHAN_DEADLINE_DAYS)

    def test_heirs_page_renders_motherless_prince(self):
        self.seed()
        page = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('早逝', page)
        self.assertIn('无人抚养', page)

    # ── 圣眷公式与党羽 ────────────────────────────────────────────────────────

    def test_standing_formula(self):
        game.run('UPDATE consorts SET rank=6, trust=50 WHERE id=?', (self.atk,))   # 妃 +10，信任 50 × 0.1 = 5
        hid = self.prince(self.atk, study=100, riding=50, virtue=100, favor=7)
        self.assertEqual(game.heir_standing(self.row(hid)), 30 + 10 + 30 + 7 + 10 + 5)

    def test_system_princes_merit_is_capped_but_players_children_are_not(self):
        npc = self.prince(0, caretaker=0, study=0, riding=0, virtue=0, favor=200, npc_key='third')
        mine = self.prince(0, caretaker=0, study=0, riding=0, virtue=0, favor=200)
        self.assertEqual(game.heir_standing(self.row(npc)), game.NPC_MERIT_CAP)
        self.assertEqual(game.heir_standing(self.row(mine)), 200)
        low = self.prince(0, caretaker=0, study=0, riding=0, virtue=0, favor=10, npc_key='fourth')
        self.assertEqual(game.heir_standing(self.row(low)), 10, '没到封顶的照实算')

    def test_npc_caretaker_bonus_is_capped(self):
        queen = game.q("SELECT id FROM consorts WHERE npc_key='huanghou'", one=True)['id']
        game.run('UPDATE consorts SET trust=0 WHERE id=?', (queen,))
        npc = self.prince(0, caretaker=queen, study=0, riding=0, virtue=0, favor=0, npc_key='fourth')
        mine = self.prince(0, caretaker=0, study=0, riding=0, virtue=0, favor=0)
        game.run('UPDATE consorts SET rank=9 WHERE id=?', (queen,))
        self.assertEqual(game.heir_standing(self.row(npc)), game.NPC_CARETAKER_BONUS_CAP)
        boss = self.player('丙', rank=8)
        game.run('UPDATE consorts SET trust=0 WHERE id=?', (boss,))
        game.run('UPDATE heirs SET caretaker_id=? WHERE id=?', (boss, mine))
        self.assertEqual(game.heir_standing(self.row(mine)), 20, '玩家抚养的照实给：皇贵妃 +20')

    def test_a_well_raised_player_prince_can_outrank_the_system_princes(self):
        game.run('UPDATE consorts SET rank=6, trust=40 WHERE id=?', (self.atk,))
        npc = self.prince(0, caretaker=0, study=70, riding=65, virtue=70, favor=500, npc_key='fourth')   # 功绩再高也只算 15
        mine = self.prince(self.atk, study=70, riding=65, virtue=70, favor=60)
        self.assertGreater(game.heir_standing(self.row(mine)), game.heir_standing(self.row(npc)))

    def test_standing_without_caretaker_is_stats_plus_merit(self):
        hid = self.prince(0, caretaker=0, study=10, riding=10, virtue=10, favor=5)
        self.assertEqual(game.heir_standing(self.row(hid)), 3 + 2 + 3 + 5)

    def test_faction_counts_distinct_families_stances_and_own_courtiers(self):
        hid = self.prince(self.atk, faction=2)
        game.run("UPDATE consorts SET family='甲家' WHERE id=?", (self.atk,))
        self.assertEqual(game.heir_faction_count(self.row(hid)), 1 + 2)
        game.run("UPDATE consorts SET family='甲家' WHERE id=?", (self.tgt,))
        game.run('UPDATE relations SET sister=0')
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.tgt, 'open', hid, 1))
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.player('丙'), 'secret', hid, 1))
        self.assertEqual(game.heir_faction_count(self.row(hid)), 1 + 1 + 2, '明站的算一个，暗站的不算')

    def test_too_many_courtiers_drains_favor_and_gets_scolded(self):
        hid = self.prince(self.atk, favor=100, faction=game.FACTION_WARN + 1)   # 1 + 6 = 7 个
        game.heir_faction_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 100 - game.FACTION_WARN_LOSS)
        game.run('UPDATE heirs SET faction=? WHERE id=?', (game.FACTION_SCOLD + 1, hid))   # 现在 1 + 9 = 10 个
        before = self.row(hid)['favor']
        game.heir_faction_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], before - game.FACTION_WARN_LOSS - game.FACTION_SCOLD_LOSS)
        again = self.row(hid)['favor']
        game.heir_faction_tick(game.cur_day() + 1)
        self.assertEqual(self.row(hid)['favor'], again - game.FACTION_WARN_LOSS, '训斥 10 天一次，不是天天训')

    def test_few_courtiers_is_free(self):
        hid = self.prince(self.atk, favor=100, faction=1)
        game.heir_faction_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 100)

    # ── 四阿哥抱养 ────────────────────────────────────────────────────────────

    def test_orphan_goes_to_a_claimant(self):
        self.seed()
        fourth = game.q("SELECT * FROM heirs WHERE npc_key='fourth'", one=True)
        self.client.post(f"/succession/claim/{fourth['id']}")
        game.heir_orphan_tick(game.cur_day())
        h = self.row(fourth['id'])
        self.assertEqual(h['caretaker_id'], self.atk)
        self.assertFalse(game.q('SELECT 1 FROM heir_claims'), '抽完清掉排队')

    def test_claim_lottery_weights_by_trust_and_rank(self):
        self.seed()
        fourth = game.q("SELECT * FROM heirs WHERE npc_key='fourth'", one=True)
        game.run('UPDATE consorts SET trust=1, rank=5 WHERE id=?', (self.atk,))
        boss = self.player('丙', rank=8)
        game.run('UPDATE consorts SET trust=99 WHERE id=?', (boss,))
        for cid in (self.atk, boss):
            game.run('INSERT INTO heir_claims(consort_id,heir_id,day) VALUES(?,?,?)', (cid, fourth['id'], 1))
        with patch.object(game.random, 'choices', side_effect=lambda pop, weights: [max(zip(pop, weights), key=lambda x: x[1])[0]]):
            game.heir_orphan_tick(game.cur_day())
        self.assertEqual(self.row(fourth['id'])['caretaker_id'], boss)
        self.assertTrue(any('没有选中' in m for m in self.msgs(self.atk)))

    def test_claim_needs_pin_rank(self):
        self.seed()
        fourth = game.q("SELECT * FROM heirs WHERE npc_key='fourth'", one=True)
        low = self.player('丙', rank=4)
        self.login(low)
        self.client.post(f"/succession/claim/{fourth['id']}")
        self.assertFalse(game.q('SELECT 1 FROM heir_claims'))

    def test_queen_takes_the_orphan_on_deadline_when_nobody_asked(self):
        self.seed()
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='huanghou'")
        fourth = game.q("SELECT * FROM heirs WHERE npc_key='fourth'", one=True)
        game.heir_orphan_tick(fourth['orphan_deadline_day'] - 1)
        self.assertEqual(self.row(fourth['id'])['caretaker_id'], 0)
        game.heir_orphan_tick(fourth['orphan_deadline_day'])
        queen = game.q("SELECT id FROM consorts WHERE npc_key='huanghou'", one=True)
        self.assertEqual(self.row(fourth['id'])['caretaker_id'], queen['id'])

    def test_orphan_can_be_claimed_even_on_the_deadline_day(self):
        self.seed()
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='huanghou'")
        fourth = game.q("SELECT * FROM heirs WHERE npc_key='fourth'", one=True)
        game.run('INSERT INTO heir_claims(consort_id,heir_id,day) VALUES(?,?,?)', (self.atk, fourth['id'], 1))
        game.heir_orphan_tick(fourth['orphan_deadline_day'])
        self.assertEqual(self.row(fourth['id'])['caretaker_id'], self.atk, '有人求就先让人求')

    # ── 野心 ─────────────────────────────────────────────────────────────────

    def test_ambition_set_at_adulthood_by_personality(self):
        hid = self.heir(self.atk, born=game.cur_day() - game.HEIR_ADULT_AGE_DAYS, personality='stubborn')
        game.heir_adult_tick(game.cur_day())
        amb = self.row(hid)['ambition']
        self.assertGreaterEqual(amb, 35 + game.AMBITION_BASE['stubborn'] - 10)
        self.assertLessEqual(amb, 35 + game.AMBITION_BASE['stubborn'] + 10)

    def test_ambitious_prince_makes_friends(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=70)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_ambition_tick(game.cur_day())
        self.assertEqual(self.row(hid)['faction'], 1)

    def test_unambitious_prince_stays_quiet(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=59)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_ambition_tick(game.cur_day())
        self.assertEqual(self.row(hid)['faction'], 0)

    def test_very_ambitious_prince_sows_discord_against_a_brother(self):
        me = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=90)
        brother = self.prince(self.tgt, age_years=14, favor=30)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_ambition_tick(game.cur_day())
        self.assertEqual(self.row(brother)['favor'], 30 - game.DISCORD_LOSS)
        self.assertTrue(any('使了绊子' in m for m in self.msgs(self.atk)))
        self.assertTrue(any('闲话' in m for m in self.msgs(self.tgt)))

    def test_persuade_moves_ambition_and_costs_energy(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=50, caretaker_affinity=80)
        e = game.get_consort(self.atk)['energy']
        self.client.post(f'/heirs/persuade/{hid}', data=dict(kind='calm'))
        self.assertEqual(self.row(hid)['ambition'], 40)
        self.assertEqual(game.get_consort(self.atk)['energy'], e - game.PERSUADE_ENERGY)
        self.client.post(f'/heirs/persuade/{hid}', data=dict(kind='strive'))   # 一天只能劝一次
        self.assertEqual(self.row(hid)['ambition'], 40)

    def test_persuade_low_affinity_may_be_ignored(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=50, caretaker_affinity=10)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post(f'/heirs/persuade/{hid}', data=dict(kind='strive'))
        self.assertEqual(self.row(hid)['ambition'], 50)

    def test_only_caretaker_can_persuade(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=50, caretaker_affinity=80)
        self.login(self.tgt)
        self.client.post(f'/heirs/persuade/{hid}', data=dict(kind='calm'))
        self.assertEqual(self.row(hid)['ambition'], 50)

    def test_ambition_shapes_default_errand_approach(self):
        hot = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=80)
        cold = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=10)
        mid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', ambition=45)
        self.assertEqual(game.errand_default_approach(self.row(hot)), 'grab')
        self.assertEqual(game.errand_default_approach(self.row(cold)), 'shift')
        self.assertEqual(game.errand_default_approach(self.row(mid)), 'steady')

    def test_errand_success_gets_faction_bonus_and_crown_doubles_loss(self):
        hid = self.prince(self.atk, age_years=16, adult_day=1, title='郡王', favor=20, virtue=50, status='crown')
        game.run('UPDATE consorts SET rank=1 WHERE id=?', (self.atk,))
        game.run("UPDATE heirs SET errand=? WHERE id=?", (game.json.dumps(dict(key='relief', day=game.cur_day() - 1, approach='grab')), hid))
        with patch.object(game.random, 'random', return_value=0.999):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 20 + game.ERRAND_APPROACHES['grab']['lose'] * 2)

    # ── 站队 ─────────────────────────────────────────────────────────────────

    def test_open_stance_adds_to_faction_and_is_public(self):
        hid = self.prince(self.tgt, age_years=13)
        before = game.heir_faction_count(self.row(hid))
        self.client.post('/succession/stance', data=dict(kind='open', heir_id=hid))
        self.assertEqual(game.heir_faction_count(self.row(hid)), before + 1)
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%示好%'"))

    def test_secret_stance_is_silent(self):
        hid = self.prince(self.tgt, age_years=13)
        before = game.heir_faction_count(self.row(hid))
        self.client.post('/succession/stance', data=dict(kind='secret', heir_id=hid))
        self.assertEqual(game.heir_faction_count(self.row(hid)), before)
        self.assertFalse(game.q("SELECT 1 FROM gazette WHERE text LIKE '%示好%'"))

    def test_both_sides_bet_is_allowed_but_not_the_same_prince(self):
        a, b = self.prince(self.tgt, age_years=13), self.prince(self.tgt, age_years=14)
        self.client.post('/succession/stance', data=dict(kind='open', heir_id=a))
        self.client.post('/succession/stance', data=dict(kind='secret', heir_id=a))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM stances', one=True)['n'], 1)
        self.client.post('/succession/stance', data=dict(kind='secret', heir_id=b))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM stances', one=True)['n'], 2)

    def test_stance_locked_for_seven_days(self):
        a, b = self.prince(self.tgt, age_years=13), self.prince(self.tgt, age_years=14)
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.atk, 'open', a, game.cur_day() - 3))
        self.client.post('/succession/stance', data=dict(kind='open', heir_id=b))
        self.assertEqual(game.q("SELECT heir_id FROM stances WHERE consort_id=?", (self.atk,), one=True)['heir_id'], a)
        game.run("UPDATE stances SET since_day=?", (game.cur_day() - game.STANCE_LOCK_DAYS,))
        self.client.post('/succession/stance', data=dict(kind='open', heir_id=b))
        self.assertEqual(game.q("SELECT heir_id FROM stances WHERE consort_id=?", (self.atk,), one=True)['heir_id'], b)

    def test_cannot_stand_for_own_child_or_kid_or_deposed(self):
        own = self.prince(self.atk, age_years=13)
        kid = self.prince(self.tgt, age_years=11)
        out = self.prince(self.tgt, age_years=14, status='deposed')
        for hid in (own, kid, out):
            self.client.post('/succession/stance', data=dict(kind='open', heir_id=hid))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM stances', one=True)['n'], 0)

    def test_withdraw_needs_lock_expired(self):
        a = self.prince(self.tgt, age_years=13)
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.atk, 'open', a, game.cur_day()))
        self.client.post('/succession/stance', data=dict(kind='open', withdraw='1'))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM stances', one=True)['n'], 1)
        game.run("UPDATE stances SET since_day=1")
        self.client.post('/succession/stance', data=dict(kind='open', withdraw='1'))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM stances', one=True)['n'], 0)

    def test_secret_gift_costs_silver_and_raises_merit_once_a_day(self):
        hid = self.prince(self.tgt, age_years=13, favor=10)
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.atk, 'secret', hid, 1))
        s = game.get_consort(self.atk)['silver']
        self.client.post('/succession/act', data=dict(act='gift'))
        self.client.post('/succession/act', data=dict(act='gift'))
        self.assertEqual(self.row(hid)['favor'], 12)
        self.assertEqual(game.get_consort(self.atk)['silver'], s - game.STANCE_ACTS['gift']['silver'])

    def test_open_tip_boosts_the_next_exam_only_for_school_age(self):
        kid = self.prince(self.tgt, age_years=13)   # 站队要 12 岁起，考校到 15 岁止，交集是 12~15
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.atk, 'open', kid, 1))
        self.client.post('/succession/act', data=dict(act='tip'))
        self.assertEqual(self.row(kid)['exam_bonus'], 5)

    def test_tip_useless_for_prince_past_exam_age(self):
        big = self.prince(self.tgt, age_years=17, adult_day=1, title='郡王')
        game.run("INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)", (self.atk, 'open', big, 1))
        self.client.post('/succession/act', data=dict(act='tip'))
        self.assertEqual(self.row(big)['exam_bonus'], 0)

    def test_exam_bonus_counts_then_clears(self):
        kid = self.prince(self.atk, age_years=10, study=40, exam_bonus=15)
        game.start_scene(self.atk, 'exam', heir=kid, prompt=0)
        # 学问 40 + 加成 15 + 掷骰 0 = 55；「让他自己从容应答」dc=60 过不了，「替他圆场」dc=45 能过
        with patch.object(game.random, 'randint', return_value=0):
            self.client.post('/scene', data=dict(opt=1))
        self.assertEqual(self.row(kid)['exam_bonus'], 0)
        self.assertGreater(self.row(kid)['favor'], 0)

    # ── 立储与废储 ───────────────────────────────────────────────────────────

    def test_crown_declared_when_clear_frontrunner(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        a = self.prince(self.atk, age_years=13, favor=90)
        self.prince(self.tgt, age_years=13, favor=50)
        game.heir_court_tick(20)   # 20 % 10 == 0
        self.assertEqual(self.row(a)['status'], 'crown')
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%皇太子%'"))

    def test_no_crown_when_lead_too_small_or_too_weak(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        a = self.prince(self.atk, age_years=13, favor=90)
        b = self.prince(self.tgt, age_years=13, favor=80)
        game.heir_court_tick(20)
        self.assertEqual(self.row(a)['status'], '')
        game.run('UPDATE heirs SET favor=10 WHERE id=?', (b,))
        game.run('UPDATE heirs SET favor=50 WHERE id=?', (a,))   # 领先够（三项基础属性给 16），但只有 66，没到 70
        game.heir_court_tick(20)
        self.assertEqual(self.row(a)['status'], '')
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%留中不发%'"))

    def test_court_only_meets_every_ten_days(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id=?', (self.atk,))
        a = self.prince(self.atk, age_years=13, favor=90)
        game.heir_court_tick(21)
        self.assertEqual(self.row(a)['status'], '')

    def test_sole_prince_can_be_crowned(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id=?', (self.atk,))
        a = self.prince(self.atk, age_years=13, favor=90)
        game.heir_court_tick(20)
        self.assertEqual(self.row(a)['status'], 'crown')

    def test_crown_deposed_when_favor_collapses(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id=?', (self.atk,))
        a = self.prince(self.atk, age_years=13, favor=0, status='crown', study=0, riding=0, virtue=0)
        rank0 = game.get_consort(self.atk)['rank']
        game.heir_court_tick(21)   # 圣眷 = 0 + 妃位加成 10 = 10 < 50
        self.assertEqual(self.row(a)['status'], 'deposed')
        self.assertEqual(game.get_consort(self.atk)['rank'], rank0 - 1, '抚养人受牵连降一级')

    def test_deposed_prince_is_out_of_the_race(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id=?', (self.atk,))
        a = self.prince(self.atk, age_years=13, favor=99, status='deposed')
        self.assertEqual(game.rival_princes(), [])
        game.heir_court_tick(20)
        self.assertEqual(self.row(a)['status'], 'deposed')

    def test_sowing_discord_on_crown_is_easier(self):
        crown = self.prince(self.tgt, age_years=13, favor=50, status='crown')
        plain = self.prince(self.tgt, age_years=13, favor=50)
        with patch.object(game.random, 'random', return_value=game.DISCORD_BASE + 0.05):
            game.sow_discord(self.row(crown), 'x')
            game.sow_discord(self.row(plain), 'x')
        self.assertEqual(self.row(crown)['favor'], 50 - game.DISCORD_LOSS, '太子的成功率高 15%')
        self.assertEqual(self.row(plain)['favor'], 50)

    # ── 万寿节 ───────────────────────────────────────────────────────────────

    def test_birthday_best_gift_wins_worst_loses(self):
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        a = self.prince(self.atk, age_years=13, favor=10, study=90, gift='calligraphy')
        b = self.prince(self.tgt, age_years=13, favor=10, study=5, gift='calligraphy')
        with patch.object(game.random, 'randint', return_value=0):
            game.heir_birthday_tick(20)
        self.assertEqual(self.row(a)['favor'], 10 + game.BIRTHDAY_WIN)
        self.assertEqual(self.row(b)['favor'], 10 + game.BIRTHDAY_LOSE)
        self.assertEqual(self.row(a)['gift'], '', '寿礼用完清掉')

    def test_birthday_antique_costs_silver_or_falls_back(self):
        game.run('UPDATE consorts SET rank=1 WHERE id=?', (self.atk,))
        self.prince(self.atk, age_years=13, gift='antique')
        s = game.get_consort(self.atk)['silver']
        game.heir_birthday_tick(20)
        self.assertEqual(game.get_consort(self.atk)['silver'], s - 100)
        game.run('UPDATE consorts SET silver=10 WHERE id=?', (self.atk,))
        game.run("UPDATE heirs SET gift='antique'")
        game.heir_birthday_tick(40)
        self.assertEqual(game.get_consort(self.atk)['silver'], 10, '银子不够就自己写幅字，不扣也不欠')

    def test_birthday_only_on_interval_and_needs_princes(self):
        game.heir_birthday_tick(20)   # 一个皇子都没有，不该报错
        a = self.prince(self.atk, age_years=13, favor=10)
        game.heir_birthday_tick(21)
        self.assertEqual(self.row(a)['favor'], 10)

    def test_lone_prince_does_not_lose_on_birthday(self):
        a = self.prince(self.atk, age_years=13, favor=10)
        game.heir_birthday_tick(20)
        self.assertEqual(self.row(a)['favor'], 10 + game.BIRTHDAY_WIN)

    # ── 手段 ─────────────────────────────────────────────────────────────────

    def test_discord_move_costs_and_can_hurt_target(self):
        hid = self.prince(self.tgt, age_years=13, favor=30)
        s, e = game.get_consort(self.atk)['silver'], game.get_consort(self.atk)['energy']
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/succession/move', data=dict(move='discord', target_id=hid))
        self.assertEqual(self.row(hid)['favor'], 30 - game.DISCORD_LOSS)
        self.assertEqual(game.get_consort(self.atk)['silver'], s - game.SUCCESSION_MOVES['discord']['silver'])
        self.assertEqual(game.get_consort(self.atk)['energy'], e - 1)

    def test_discord_can_expose_the_schemer(self):
        hid = self.prince(self.tgt, age_years=13, favor=30)
        with patch.object(game.random, 'random', return_value=0.0):   # 既成功、也被查到
            self.client.post('/succession/move', data=dict(move='discord', target_id=hid))
        self.assertTrue(any('散布' in m for m in self.msgs(self.tgt)))

    def test_cannot_discord_own_child(self):
        hid = self.prince(self.atk, age_years=13, favor=30)
        self.client.post('/succession/move', data=dict(move='discord', target_id=hid))
        self.assertEqual(self.row(hid)['favor'], 30)

    def test_move_needs_silver_and_energy(self):
        hid = self.prince(self.tgt, age_years=13, favor=30)
        game.run('UPDATE consorts SET silver=5 WHERE id=?', (self.atk,))
        self.client.post('/succession/move', data=dict(move='discord', target_id=hid))
        self.assertEqual(self.row(hid)['favor'], 30)

    def test_bribe_exam_gives_bonus_to_own_school_age_child(self):
        kid = self.prince(self.atk, age_years=9)
        self.client.post('/succession/move', data=dict(move='bribe', target_id=kid))
        self.assertEqual(self.row(kid)['exam_bonus'], game.BRIBE_BONUS)
        other = self.prince(self.tgt, age_years=9)
        self.client.post('/succession/move', data=dict(move='bribe', target_id=other))
        self.assertEqual(self.row(other)['exam_bonus'], 0, '别人的孩子不能买')

    def test_princess_counsel_helps_a_brother_with_cooldown(self):
        princess = self.heir(self.atk, gender='公主', born=game.cur_day() - 26)
        prince = self.prince(self.tgt, age_years=13, favor=10)
        self.client.post('/succession/move', data=dict(move='counsel', princess_id=princess, target_id=prince))
        self.assertEqual(self.row(prince)['favor'], 10 + game.COUNSEL_GAIN)
        self.assertEqual(self.row(princess)['plead_ready_day'], game.cur_day() + game.COUNSEL_INTERVAL)
        self.client.post('/succession/move', data=dict(move='counsel', princess_id=princess, target_id=prince))
        self.assertEqual(self.row(prince)['favor'], 10 + game.COUNSEL_GAIN, '7 天内不能再进')

    def test_young_princess_cannot_counsel(self):
        princess = self.heir(self.atk, gender='公主', born=game.cur_day() - 20)
        prince = self.prince(self.tgt, age_years=13, favor=10)
        self.client.post('/succession/move', data=dict(move='counsel', princess_id=princess, target_id=prince))
        self.assertEqual(self.row(prince)['favor'], 10)

    def test_feud_needs_scheme_and_drains_both(self):
        a, b = self.prince(self.tgt, age_years=13, favor=30), self.prince(self.tgt, age_years=14, favor=30)
        game.run('UPDATE consorts SET scheme=49 WHERE id=?', (self.atk,))
        self.client.post('/succession/move', data=dict(move='feud', target_id=a, other_id=b))
        self.assertEqual(self.row(a)['feud_until_day'], 0)
        game.run('UPDATE consorts SET scheme=50 WHERE id=?', (self.atk,))
        self.client.post('/succession/move', data=dict(move='feud', target_id=a, other_id=b))
        self.assertEqual(self.row(a)['feud_until_day'], game.cur_day() + game.FEUD_DAYS)
        game.heir_feud_tick(game.cur_day())
        self.assertEqual((self.row(a)['favor'], self.row(b)['favor']), (27, 27))
        game.heir_feud_tick(game.cur_day() + game.FEUD_DAYS + 1)
        self.assertEqual(self.row(a)['favor'], 27, '到期就停')

    def test_feud_needs_two_different_princes(self):
        a = self.prince(self.tgt, age_years=13)
        game.run('UPDATE consorts SET scheme=90 WHERE id=?', (self.atk,))
        self.client.post('/succession/move', data=dict(move='feud', target_id=a, other_id=a))
        self.assertEqual(self.row(a)['feud_until_day'], 0)

    def test_gift_route_sets_choice_for_own_prince_only(self):
        mine = self.prince(self.atk, age_years=13)
        theirs = self.prince(self.tgt, age_years=13)
        self.client.post(f'/succession/gift/{mine}', data=dict(gift='fur'))
        self.client.post(f'/succession/gift/{theirs}', data=dict(gift='fur'))
        self.assertEqual(self.row(mine)['gift'], 'fur')
        self.assertEqual(self.row(theirs)['gift'], '')

    # ── 页面与整晚结算 ────────────────────────────────────────────────────────

    def test_succession_page_renders_everything(self):
        self.seed()
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='qifei'")
        mine = self.prince(self.atk, age_years=17, adult_day=1, title='郡王', ambition=70)
        self.heir(self.atk, gender='公主', born=game.cur_day() - 26)
        self.prince(self.tgt, age_years=13)
        page = self.client.get('/succession').get_data(as_text=True)
        for text in ('明着站', '劝他收敛些', '万寿节寿礼', '求皇上把他交给我', '公主进言', '挑拨兄弟', '三阿哥'):
            self.assertIn(text, page)

    def test_full_settle_with_seeded_npc_princes_runs(self):
        self.seed()
        game.run("UPDATE consorts SET status='normal' WHERE npc_key IN ('qifei','huanghou')")
        self.prince(self.atk, age_years=13)
        with patch.object(game, 'npc_schemes'):
            for day in range(3):
                game.run('UPDATE game_state SET day=day+1')
                game.settle_day()
        self.assertTrue(game.q("SELECT 1 FROM heirs WHERE npc_key='third'"))

    def test_nav_has_link(self):
        self.assertIn('夺嫡', self.client.get('/heirs').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
