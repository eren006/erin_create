"""早产儿体质长得慢；孩子生病（0~14 岁每岁一掷，请太医/养育所后果）

运行：python3 -m unittest discover -s tests -v
"""
import json
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class PrematureHeirTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def heir(self, mother, premature):
        return game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,premature,health_max,health) VALUES(?,?,'皇子',9,1,?,100,40)",
                        (mother, mother, 1 if premature else 0)).lastrowid

    def test_grow_weight_health_lower_for_premature(self):
        mother = self.player('母', 4)
        seen = {}
        for flag in (0, 1):
            hid = self.heir(mother, flag)
            game.run("UPDATE heirs SET born_day=? WHERE id=?", (game.cur_day() - 20, hid))
            captured = []
            def fake(pop, weights=None):
                captured.append(dict(zip(pop, weights)))
                return [pop[0]]
            with patch.object(game.random, 'choices', fake):
                game.heir_grow_stats(game.cur_day())
            seen[flag] = captured[0]
            game.run("DELETE FROM heirs WHERE id=?", (hid,))
        self.assertEqual(seen[0]['health'], 1)
        self.assertEqual(seen[1]['health'], game.HEIR_PREMATURE_GROW_WEIGHT)
        self.assertEqual(seen[1]['study'], 1)

    # ── 孩子生病 ─────────────────────────────────────────────────────────────

    def sick(self, mother, key, caretaker=None, **cols):
        hid = self.heir(mother, cols.pop('premature', False))
        game.run("UPDATE heirs SET caretaker_id=?, illness=?, ill_deadline_ts=?, ill_rolls=99 WHERE id=?",
                 (mother if caretaker is None else caretaker, key, 1.0, hid))
        for k, v in cols.items(): game.run(f"UPDATE heirs SET {k}=? WHERE id=?", (v, hid))
        return hid

    def test_ill_chance_rises_with_low_health_and_prematurity(self):
        base = dict(health=100, premature=0)
        self.assertAlmostEqual(game.heir_ill_chance(base), game.HEIR_ILL_BASE)
        self.assertGreater(game.heir_ill_chance(dict(health=40, premature=0)), game.heir_ill_chance(base))
        self.assertAlmostEqual(game.heir_ill_chance(dict(health=100, premature=1)), game.HEIR_ILL_BASE * game.HEIR_ILL_PREMATURE_MULT)
        self.assertLessEqual(game.heir_ill_chance(dict(health=1, premature=1)), game.HEIR_ILL_CAP)

    def test_roll_every_six_hours_until_adult_and_legacy_not_backfilled(self):
        mother = self.player('母', 4)
        new = self.heir(mother, False); old = self.heir(mother, False); grown = self.heir(mother, False)
        day = game.cur_day()
        game.run("UPDATE heirs SET born_day=?, ill_rolls=-1 WHERE id=?", (day - 3, new))     # 6 岁，新生儿起算
        game.run("UPDATE heirs SET born_day=?, ill_rolls=-2 WHERE id=?", (day - 3, old))     # 老档：只记当前格
        game.run("UPDATE heirs SET born_day=?, ill_rolls=29 WHERE id=?", (day - 20, grown))  # 早已掷满 14 岁
        with patch.object(game.random, 'random', lambda: 0.0):
            game.heir_illness_tick(day)
        self.assertNotEqual(game.get_heir(new)['illness'], '')
        self.assertEqual(game.get_heir(old)['illness'], '')
        self.assertEqual(game.get_heir(old)['ill_rolls'], 12)      # 6 岁 = 第 12 格
        self.assertEqual(game.get_heir(grown)['illness'], '')

    def test_six_hour_roll_chance_keeps_the_yearly_rate(self):
        h = dict(health=60, premature=0)
        yearly = game.heir_ill_chance(h)
        per = game.heir_ill_roll_chance(h)
        self.assertLess(per, yearly)
        self.assertAlmostEqual(1 - (1 - per) ** game.HEIR_ILL_ROLLS_PER_YEAR, yearly)

    def test_one_roll_per_six_hours_not_per_hour(self):
        mother = self.player('母', 4)
        hid = self.heir(mother, False)
        game.run("UPDATE heirs SET born_ts=?, ill_rolls=-1 WHERE id=?", (game.now_ts() - 6 * 3600 * 4.5, hid))   # 4 个半 6 小时 = 第 4 格
        calls = []
        with patch.object(game.random, 'random', side_effect=lambda: calls.append(1) or 0.99):
            game.heir_illness_tick(game.cur_day()); game.heir_illness_tick(game.cur_day())
        self.assertEqual(len(calls), 1, '同一格内每小时的重复调用不再掷')
        self.assertEqual(game.get_heir(hid)['ill_rolls'], 4)

    def test_heirs_page_shows_illness_countdown_and_outcomes(self):
        mother = self.player('母', 4)
        well = self.heir(mother, False)
        game.run("UPDATE heirs SET caretaker_id=?, born_ts=?, ill_rolls=5 WHERE id=?", (mother, game.now_ts() - 3600 * 7.5, well))
        ill = self.sick(mother, 'cold', ill_deadline_ts=game.now_ts() + 2.5 * 3600)
        self.login(mother)
        body = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('下次患病判定', body)
        self.assertIn('没人医治的结算倒计时', body)
        v = game.heir_ill_view(game.get_heir(well))
        self.assertAlmostEqual(v['secs'], 3600 * 4.5, delta=5)      # 7.5 小时，下一格在第 12 小时
        self.assertEqual(game.heir_ill_view(game.get_heir(ill))['secs'] // 3600, 2)

    def test_outcome_percentages_sum_to_100(self):
        for caretaker in (7, 0):
            for sev in (None, True, False):
                out = game.heir_ill_outcomes(dict(health=70, caretaker_id=caretaker), sev)
                self.assertLessEqual(abs(sum(p for _, p in out) - 100), 1, (caretaker, sev, out))

    def test_treat_costs_silver_and_cures(self):
        mother = self.player('母', 4)
        hid = self.sick(mother, 'cold')
        self.login(mother)
        before = game.get_consort(mother)['silver']
        with patch.object(game.random, 'random', lambda: 0.5):      # 避开请了太医也 3% 夭折的那一档
            self.client.post(f'/heirs/treat/{hid}')
        self.assertEqual(game.get_heir(hid)['illness'], '')
        self.assertEqual(game.get_consort(mother)['silver'], before - game.HEIR_ILLNESSES['cold']['cost'])

    def test_death_leaves_a_grave_a_sad_letter_and_a_gazette(self):
        mother = self.player('母', 4)
        hid = self.sick(mother, 'cold')
        game.run("UPDATE heirs SET ordinal=2,name='弘晟' WHERE id=?", (hid,))
        before_letters = game.q('SELECT COUNT(*) n FROM letters WHERE to_id=?', (mother,), one=True)['n']
        with patch.object(game.random, 'random', lambda: 0.0):
            game.heir_illness_tick(game.cur_day())
        self.assertIsNone(game.get_heir(hid))
        grave = game.q('SELECT * FROM birth_losses WHERE mother_id=?', (mother,), one=True)
        self.assertTrue(grave['epitaph'] and grave['label'] and grave['place'])
        self.assertIn('风寒', grave['epitaph'])
        letter = game.q('SELECT * FROM letters WHERE to_id=? ORDER BY id DESC', (mother,), one=True)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters WHERE to_id=?', (mother,), one=True)['n'], before_letters + 1)
        self.assertEqual(letter['from_id'], 0)
        self.assertTrue(letter['sender_label'])
        self.assertIn(grave['label'], letter['body'])
        self.login(mother)
        page = self.client.get('/graveyard').get_data(as_text=True)
        self.assertEqual(grave['ordinal'], 2)
        self.assertEqual(grave['name'], '弘晟')
        self.assertIn('二皇子 · 弘晟', page)
        self.assertIn(grave['epitaph'], page)
        self.assertIn('你的孩子', page)
        self.assertIn('墓地', self.client.get('/heirs').get_data(as_text=True))

    def test_premature_birth_death_is_recorded_too(self):
        mother = self.player('母', 4)
        game.run("UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?", (mother,))
        with patch.object(game.time, 'time', return_value=100000 + int(game.PRETERM_START_HOURS * 3600) + 60), patch.object(game, 'preterm_chance', return_value=1), \
             patch.object(game, 'preterm_child_death_chance', return_value=1), patch.object(game, 'preterm_crisis_chance', return_value=0), patch.object(game, 'TWIN_CHANCE', 0):
            game.resolve_births(10, False)
        grave = game.q('SELECT * FROM birth_losses WHERE mother_id=?', (mother,), one=True)
        self.assertIn('早产', grave['label'])
        self.assertTrue(game.q('SELECT 1 FROM letters WHERE to_id=?', (mother,), one=True))

    def test_treated_child_still_has_a_three_percent_death_chance(self):
        mother = self.player('母', 4)
        self.assertEqual(game.HEIR_ILL_TREATED_DEATH, 0.03)
        hid = self.sick(mother, 'cold')
        self.login(mother)
        before = game.get_consort(mother)['silver']
        with patch.object(game.random, 'random', lambda: 0.02):
            self.client.post(f'/heirs/treat/{hid}')
        self.assertIsNone(game.get_heir(hid), '请了太医也有 3% 没救回来')
        self.assertEqual(game.get_consort(mother)['silver'], before - game.HEIR_ILLNESSES['cold']['cost'], '银子照花')
        self.assertTrue(game.q("SELECT 1 FROM birth_losses WHERE mother_id=? AND reason LIKE '%宫中%'", (mother,), one=True))

    def test_treat_needs_silver_and_caretaker(self):
        mother = self.player('母', 4); other = self.player('旁人', 4)
        hid = self.sick(mother, 'cold')
        game.run("UPDATE consorts SET silver=0 WHERE id=?", (mother,))
        self.login(mother); self.client.post(f'/heirs/treat/{hid}')
        self.assertEqual(game.get_heir(hid)['illness'], 'cold')
        self.login(other); self.client.post(f'/heirs/treat/{hid}')
        self.assertEqual(game.get_heir(hid)['illness'], 'cold')

    def test_orphanage_severe_can_die_and_is_recorded(self):
        mother = self.player('母', 4)
        hid = self.sick(mother, 'fright', caretaker=0)
        with patch.object(game.random, 'random', lambda: 0.0):
            game.heir_illness_tick(game.cur_day())
        self.assertIsNone(game.get_heir(hid))
        self.assertTrue(game.q("SELECT 1 FROM birth_losses WHERE mother_id=? AND reason LIKE '%急惊风%'", (mother,), one=True))

    def test_orphanage_death_rate_is_thirty_percent_for_any_illness(self):
        mother = self.player('母', 4)
        self.assertEqual(game.HEIR_ILL_ORPHAN_DEATH, 0.30)
        cold = self.sick(mother, 'cold', caretaker=0, health=100)
        with patch.object(game.random, 'random', lambda: 0.29):      # 轻症也会夭折
            game.heir_illness_tick(game.cur_day())
        self.assertIsNone(game.get_heir(cold))
        surv = self.sick(mother, 'cold', caretaker=0, health=100)
        with patch.object(game.random, 'random', lambda: 0.31):
            game.heir_illness_tick(game.cur_day())
        self.assertIsNotNone(game.get_heir(surv))
        view = game.heir_ill_outcomes(dict(health=100, caretaker_id=0))
        self.assertEqual(dict(view)['夭折'], 30)      # 页面上显示的夭折率就是 30%，轻重症一样
        self.assertEqual(dict(game.heir_ill_outcomes(dict(health=100, caretaker_id=0), True))['夭折'], 30)
        self.assertEqual(dict(game.heir_ill_outcomes(dict(health=100, caretaker_id=0), False))['夭折'], 30)

    def test_orphanage_severe_can_become_weak(self):
        mother = self.player('母', 4)
        hid = self.sick(mother, 'fright', caretaker=0, health=40)
        with patch.object(game.random, 'random', lambda: 0.6):     # 体质 40：死亡线 0.47、病弱线 0.99，0.6 落在病弱
            game.heir_illness_tick(game.cur_day())
        h = game.get_heir(hid)
        self.assertEqual((h['illness'], h['health_max']), ('', 100 - game.HEIR_ILL_WEAK['cap']))
        self.assertEqual(h['health'], 40 - game.HEIR_ILL_WEAK['health'])

    def test_orphanage_light_weak_half_the_time(self):
        mother = self.player('母', 4)
        self.assertEqual(game.HEIR_ILL_ORPHAN_LIGHT_WEAK, 0.5)
        hid = self.sick(mother, 'cold', caretaker=0, health=100)
        with patch.object(game.random, 'random', lambda: 0.79):      # 死亡线 0.30，病弱线 0.80
            game.heir_illness_tick(game.cur_day())
        self.assertEqual(game.get_heir(hid)['health_max'], 100 - game.HEIR_ILL_WEAK['cap'])
        hid2 = self.sick(mother, 'cold', caretaker=0, health=100)
        with patch.object(game.random, 'random', lambda: 0.81):
            game.heir_illness_tick(game.cur_day())
        self.assertEqual(game.get_heir(hid2)['health_max'], 100)

    def test_raised_untreated_has_a_ten_percent_death_chance(self):
        mother = self.player('母', 4)
        self.assertEqual(game.HEIR_ILL_RAISED_DEATH, 0.10)
        dead = self.sick(mother, 'cold', health=100)
        with patch.object(game.random, 'random', lambda: 0.09):
            game.heir_illness_tick(game.cur_day())
        self.assertIsNone(game.get_heir(dead), '宫里养着的孩子，病了不请太医有 10% 夭折')
        self.assertTrue(game.q("SELECT 1 FROM birth_losses WHERE mother_id=? AND reason LIKE '%宫中%'", (mother,), one=True))
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%风寒%' AND (text LIKE '%夭折%' OR text LIKE '%薨%' OR text LIKE '%没有熬过%')", one=True))
        alive = self.sick(mother, 'smallpox', health=100)
        with patch.object(game.random, 'random', lambda: 0.11):
            game.heir_illness_tick(game.cur_day())
        self.assertIsNotNone(game.get_heir(alive))
        self.assertEqual(dict(game.heir_ill_outcomes(dict(health=100, caretaker_id=mother)))['夭折'], 10)

    def test_raised_severe_untreated_survivors_are_weakened(self):
        mother = self.player('母', 4)
        hid = self.sick(mother, 'smallpox', health=40)
        with patch.object(game.random, 'random', lambda: 0.11):
            game.heir_illness_tick(game.cur_day())
        h = game.get_heir(hid)
        self.assertIsNotNone(h)
        self.assertEqual(h['health_max'], 100 - game.HEIR_ILL_WEAK['cap'])

    def test_raised_light_untreated_half_weak_else_small_loss(self):
        mother = self.player('母', 4)
        self.assertEqual(game.HEIR_ILL_RAISED_LIGHT_WEAK, 0.5)
        hid = self.sick(mother, 'cold', health=100)
        with patch.object(game.random, 'random', lambda: 0.59):      # 死亡线 0.10，病弱线 0.60
            game.heir_illness_tick(game.cur_day())
        h = game.get_heir(hid)
        self.assertEqual((h['illness'], h['health_max']), ('', 100 - game.HEIR_ILL_WEAK['cap']))
        hid2 = self.sick(mother, 'cold', health=100)
        with patch.object(game.random, 'random', lambda: 0.61):
            game.heir_illness_tick(game.cur_day())
        h2 = game.get_heir(hid2)
        self.assertEqual((h2['health_max'], h2['health']), (100, 100 - game.HEIR_ILL_LIGHT_HEALTH))

    def test_heirs_page_shows_illness_and_button(self):
        mother = self.player('母', 4)
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (mother,))
        hid = self.sick(mother, 'cold')
        game.run("UPDATE heirs SET ill_deadline_ts=? WHERE id=?", (game.now_ts() + 3600, hid))
        self.login(mother)
        html = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('风寒', html)
        self.assertIn('请太医医治', html)


if __name__ == '__main__':
    unittest.main()
