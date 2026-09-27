"""查案翻案 + 构陷皇子：接上 v1.4 记下的冤案，和夺嫡里唯一还没做的手段

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class AppealTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def make_case(self, victim, convicted, culprit=None, drug='lihun', day=None, closed_day=None):
        day = day or game.cur_day()
        closed_day = closed_day if closed_day is not None else day
        culprit = culprit if culprit is not None else convicted
        cid = game.run("""INSERT INTO cases(day,victim_id,culprit_id,drug,status,closed_day,convicted_id,wrongful,created_ts)
                          VALUES(?,?,?,?,?,?,?,?,0)""",
                       (day, victim, culprit, drug, 'convicted', closed_day, convicted, int(culprit != convicted))).lastrowid
        return cid

    # ── 翻案资格 ─────────────────────────────────────────────────────────────

    def test_only_the_convicted_or_her_sisters_can_appeal(self):
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        cid = self.make_case(self.tgt, self.atk, culprit=999, closed_day=game.cur_day() - 10)
        case = game.q('SELECT * FROM cases WHERE id=?', (cid,), one=True)
        self.assertFalse(game.can_appeal(game.get_consort(self.tgt), case), '受害人自己不能替被定罪的人申诉')
        self.assertTrue(game.can_appeal(game.get_consort(self.atk), case))
        boss = self.player('丙', rank=6)
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,1)", (min(self.atk, boss), max(self.atk, boss), 60))
        self.assertTrue(game.can_appeal(game.get_consort(boss), case), '姐妹能替她申诉')

    def test_needs_the_case_closed_long_enough(self):
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        cid = self.make_case(self.tgt, self.atk, culprit=999, closed_day=game.cur_day() - (game.APPEAL_MIN_DAYS_CLOSED - 1))
        case = game.q('SELECT * FROM cases WHERE id=?', (cid,), one=True)
        self.assertFalse(game.can_appeal(game.get_consort(self.atk), case))

    def test_open_or_unsolved_or_overturned_cases_cannot_be_appealed(self):
        for status in ('open', 'unsolved', 'overturned'):
            cid = self.make_case(self.tgt, self.atk, culprit=999, closed_day=game.cur_day() - 10)
            game.run('UPDATE cases SET status=? WHERE id=?', (status, cid))
            case = game.q('SELECT * FROM cases WHERE id=?', (cid,), one=True)
            self.assertFalse(game.can_appeal(game.get_consort(self.atk), case), status)

    # ── 翻案结算 ─────────────────────────────────────────────────────────────

    def appeal(self, roll=0.0):
        with patch.object(game.random, 'random', return_value=roll):
            return self.client.post(f'/cases/{self.cid}/appeal')

    def setup_wrongful(self, drug='lihun'):
        game.run("UPDATE consorts SET status='cold', silver=500, energy=5 WHERE id=?", (self.atk,))
        self.cid = self.make_case(self.tgt, self.atk, culprit=self.player('丙', rank=4), drug=drug, closed_day=game.cur_day() - 10)
        self.login(self.atk)

    def test_wrongful_conviction_overturns_and_releases_from_cold(self):
        self.setup_wrongful()
        self.appeal(0.0)
        self.assertEqual(game.q('SELECT status FROM cases WHERE id=?', (self.cid,), one=True)['status'], 'overturned')
        c = game.get_consort(self.atk)
        self.assertEqual(c['status'], 'normal')
        self.assertTrue(any('沉冤得雪' in t['text'] for t in game.q('SELECT text FROM gazette')))

    def test_overturning_confined_conviction_lifts_it(self):
        game.run("UPDATE consorts SET status='confined', status_until_day=99, silver=500, energy=5 WHERE id=?", (self.atk,))
        self.cid = self.make_case(self.tgt, self.atk, culprit=self.player('丙', rank=4), drug='rumor', closed_day=game.cur_day() - 10)
        self.login(self.atk)
        self.appeal(0.0)
        c = game.get_consort(self.atk)
        self.assertEqual((c['status'], c['status_until_day']), ('normal', 0))

    def test_overturning_hanshui_restores_rank_if_slot_free(self):
        game.run("UPDATE consorts SET status='normal', rank=4, silver=500, energy=5 WHERE id=?", (self.atk,))
        self.cid = self.make_case(self.tgt, self.atk, culprit=self.player('丙', rank=4), drug='hanshui', closed_day=game.cur_day() - 10)
        self.login(self.atk)
        self.appeal(0.0)
        self.assertEqual(game.get_consort(self.atk)['rank'], 5)

    def test_the_real_culprit_takes_the_hit_when_wrongful_overturns(self):
        self.setup_wrongful()
        culprit_id = game.q('SELECT culprit_id FROM cases WHERE id=?', (self.cid,), one=True)['culprit_id']
        game.run('UPDATE consorts SET favor=200, trust=50 WHERE id=?', (culprit_id,))
        self.appeal(0.0)
        c = game.get_consort(culprit_id)
        self.assertLess(c['favor'], 200)
        self.assertEqual(c['trust'], 40)
        self.assertTrue(any('苗头渐渐指向你' in t for t in self.msgs(culprit_id)))

    def test_wrongful_appeal_can_still_fail_and_sets_a_cooldown(self):
        self.setup_wrongful()
        self.appeal(0.999)
        case = game.q('SELECT * FROM cases WHERE id=?', (self.cid,), one=True)
        self.assertEqual(case['status'], 'convicted')
        self.assertEqual(case['appeal_ready_day'], game.cur_day() + game.APPEAL_INTERVAL)
        r = self.appeal(0.0)   # 冷却中，抽不到签也不该成
        self.assertEqual(game.q('SELECT status FROM cases WHERE id=?', (self.cid,), one=True)['status'], 'convicted')

    def test_rightful_conviction_almost_always_fails_the_appeal(self):
        """真凶自己想脱罪：翻案概率很低，撞上高概率的骰子也该失败"""
        game.run("UPDATE consorts SET status='cold', silver=500, energy=5 WHERE id=?", (self.atk,))
        self.cid = self.make_case(self.tgt, self.atk, culprit=self.atk, closed_day=game.cur_day() - 10)   # 真被定了罪
        self.login(self.atk)
        self.appeal(0.5)   # 0.5 远超真凶脱罪的概率上限
        self.assertEqual(game.q('SELECT status FROM cases WHERE id=?', (self.cid,), one=True)['status'], 'convicted')

    def test_appeal_costs_silver_and_energy_regardless_of_outcome(self):
        self.setup_wrongful()
        s0, e0 = game.get_consort(self.atk)['silver'], game.get_consort(self.atk)['energy']
        self.appeal(0.999)
        c = game.get_consort(self.atk)
        self.assertEqual((c['silver'], c['energy']), (s0 - game.APPEAL_SILVER, e0 - game.APPEAL_ENERGY))

    def test_appeal_needs_the_silver(self):
        self.setup_wrongful()
        game.run('UPDATE consorts SET silver=10 WHERE id=?', (self.atk,))
        self.appeal(0.0)
        self.assertEqual(game.q('SELECT status FROM cases WHERE id=?', (self.cid,), one=True)['status'], 'convicted')

    def test_cases_page_shows_appeal_button_only_when_eligible(self):
        self.setup_wrongful()
        page = self.client.get('/cases').get_data(as_text=True)
        self.assertIn('翻案', page)
        self.login(self.tgt)
        page = self.client.get('/cases').get_data(as_text=True)
        self.assertNotIn('翻案（', page)


class FramePrinceTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def prince(self, mother, age_years=13, **kw):
        kw.setdefault('title', '')
        return self.heir(mother, gender='皇子', born=game.cur_day() - age_years * 2, zhuazhou='book', **kw)

    def row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def setUp_(self):
        pass

    def frame(self, target, roll=0.0, roll2=0.99):
        game.run('UPDATE consorts SET rank=6, silver=1000, energy=5 WHERE id=?', (self.atk,))
        seq = iter([roll, roll2])
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            return self.client.post('/succession/move', data=dict(move='frame', target_id=target))

    def test_needs_pin_rank(self):
        game.run('UPDATE consorts SET rank=5, silver=1000, energy=5 WHERE id=?', (self.atk,))
        hid = self.prince(self.tgt)
        self.client.post('/succession/move', data=dict(move='frame', target_id=hid))
        self.assertEqual(self.row(hid)['status'], '')

    def test_cannot_frame_own_child_or_the_child_you_foster(self):
        own = self.prince(self.atk)
        fostered = self.prince(self.tgt, caretaker=self.atk)
        self.frame(own)
        self.frame(fostered)
        self.assertEqual((self.row(own)['status'], self.row(fostered)['status']), ('', ''))

    def test_success_deposes_the_prince_and_demotes_the_caretaker(self):
        boss = self.player('丙', rank=6)
        hid = self.prince(boss)
        self.frame(hid, roll=0.0)
        h = self.row(hid)
        self.assertEqual(h['status'], 'deposed')
        self.assertEqual(game.get_consort(boss)['rank'], 5)
        self.assertTrue(any('圈禁出局' in t for t in self.msgs(boss)))
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%图谋不轨%'"))

    def test_deposed_prince_drops_out_of_the_race(self):
        hid = self.prince(self.tgt)
        self.frame(hid, roll=0.0)
        self.assertNotIn(hid, [h['id'] for h in game.rival_princes()])

    def test_failure_costs_silver_but_leaves_the_prince_alone(self):
        game.run('UPDATE consorts SET rank=6, silver=1600, energy=5 WHERE id=?', (self.atk,))
        hid = self.prince(self.tgt)
        seq = iter([0.99, 0.99])
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            self.client.post('/succession/move', data=dict(move='frame', target_id=hid))
        self.assertEqual(self.row(hid)['status'], '')
        self.assertEqual(game.get_consort(self.atk)['silver'], 1600 - game.SUCCESSION_MOVES['frame']['silver'])

    def test_failure_can_expose_the_schemer(self):
        hid = self.prince(self.tgt)
        t0 = game.get_consort(self.atk)['trust']
        self.frame(hid, roll=0.99, roll2=0.0)
        c = game.get_consort(self.atk)
        self.assertEqual(c['trust'], t0 - game.FRAME_PRINCE_CAUGHT_TRUST)
        self.assertTrue(any('构陷' in t for t in self.msgs(self.tgt)))

    def test_higher_scheme_raises_success_but_is_capped(self):
        boss = self.player('丙', rank=6)
        hid = self.prince(boss)
        game.run('UPDATE consorts SET scheme=100 WHERE id=?', (self.atk,))
        p = min(0.75, game.FRAME_PRINCE_BASE + 100 * game.FRAME_PRINCE_PER_SCHEME)
        self.assertLessEqual(p, 0.75)
        self.frame(hid, roll=p - 0.001)
        self.assertEqual(self.row(hid)['status'], 'deposed')

    def test_needs_a_target(self):
        game.run('UPDATE consorts SET rank=6, silver=1000, energy=5 WHERE id=?', (self.atk,))
        r = self.client.post('/succession/move', data=dict(move='frame', target_id=0))
        self.assertEqual(game.get_consort(self.atk)['silver'], 1000)


if __name__ == '__main__':
    unittest.main()
