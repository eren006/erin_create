"""老死与病死：寿终、追封、体虚/冷宫/时疫/产后染病、病重生死判定，见设计文档九点七节

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class OldAgeTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_no_death_roll_before_fifty(self):
        game.run('UPDATE consorts SET age_months=? WHERE id=?', (game.OLD_AGE_START - 6, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_death_roll_at_fifty_with_healthy_body_halves_chance(self):
        game.run('UPDATE consorts SET age_months=?, health=70 WHERE id=?', (game.OLD_AGE_START, self.atk))
        # 刚满 50 岁，体质 >=60 减半：概率约等于 0，用极小的骰子也不该死
        with patch.object(game.random, 'random', return_value=0.0001):
            game.old_age_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_frail_body_doubles_chance_and_dies(self):
        game.run('UPDATE consorts SET age_months=?, health=20, rank=1 WHERE id=?',
                (game.OLD_AGE_START + 12 * 10, self.atk))   # 60 岁，体质 <30 翻倍
        with patch.object(game.random, 'random', return_value=0.05):
            game.old_age_tick(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual(c['status'], 'dead')
        self.assertEqual(c['death_reason'], '寿终')

    def test_reminder_fires_every_five_years_from_fifty_five(self):
        game.run('UPDATE consorts SET age_months=? WHERE id=?', (game.OLD_AGE_REMINDER_START, self.atk))
        with patch.object(game.random, 'random', return_value=0.999):
            game.old_age_tick(game.cur_day())
        self.assertTrue(any('精神短了' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (self.atk,))))

    def test_posthumous_promotion_when_trust_high(self):
        game.run('UPDATE consorts SET age_months=?, rank=5, trust=80 WHERE id=?', (game.OLD_AGE_START + 12 * 20, self.atk))
        before_rank = game.get_consort(self.atk)['rank']
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual(c['status'], 'dead')
        self.assertGreater(c['rank'], before_rank, '信任 >=70，嫔以上寿终追封晋一级')

    def test_posthumous_shi_word_when_trust_mid(self):
        game.run("UPDATE consorts SET age_months=?, rank=5, trust=50, title='安' WHERE id=?",
                (game.OLD_AGE_START + 12 * 20, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual(c['status'], 'dead')
        self.assertEqual(len(c['title']), 2, '信任 40~69，加一个谥字，原有单字封号变两字')
        self.assertTrue(c['title'].startswith('安'))

    def test_low_trust_no_posthumous_honor(self):
        game.run("UPDATE consorts SET age_months=?, rank=5, trust=10, title='安' WHERE id=?",
                (game.OLD_AGE_START + 12 * 20, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual(c['title'], '安', '信任不够，不追封')

    def test_gazette_and_memorial_wording(self):
        game.run('UPDATE consorts SET age_months=? WHERE id=?', (game.OLD_AGE_START + 12 * 20, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(game.cur_day())
        self.assertIn('因寿终薨逝', game.q('SELECT text FROM gazette ORDER BY id DESC', one=True)['text'])
        self.assertEqual(game.get_consort(self.atk)['death_reason'], '寿终')


class IllnessOnsetTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_weak_body_days_in_a_row_falls_ill(self):
        game.run('UPDATE game_state SET day=11')   # 避开 day % EPIDEMIC_INTERVAL == 0 的巧合
        game.run('UPDATE consorts SET health=10 WHERE id=?', (self.atk,))
        day = game.cur_day()
        with patch.object(game.random, 'random', return_value=0.99):   # 不触发冷宫/产后/时疫这些概率事件
            for i in range(1, game.WEAK_SICK_DAYS):
                game.illness_onset_tick(day)
                self.assertEqual(game.get_consort(self.atk)['weak_days'], i)
                self.assertFalse(game.get_consort(self.atk)['ill_day'])
            game.illness_onset_tick(day)
        c = game.get_consort(self.atk)
        self.assertTrue(c['ill_day'], f'连续 {game.WEAK_SICK_DAYS} 天体质 <25，该染病了')
        self.assertEqual(c['weak_days'], 0, '染病后计数器清零')

    def test_weak_days_resets_when_health_recovers(self):
        game.run('UPDATE game_state SET day=11')
        game.run('UPDATE consorts SET health=10, weak_days=2 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.99):
            game.illness_onset_tick(game.cur_day())
        self.assertTrue(game.get_consort(self.atk)['ill_day'])
        game2 = self.player('丙')
        game.run('UPDATE consorts SET health=80, weak_days=2 WHERE id=?', (game2,))
        with patch.object(game.random, 'random', return_value=0.99):
            game.illness_onset_tick(game.cur_day())
        self.assertEqual(game.get_consort(game2)['weak_days'], 0, '体质回升就不再计数')

    def test_cold_palace_can_fall_ill(self):
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(game.cur_day())
        self.assertTrue(game.get_consort(self.atk)['ill_day'])

    def test_postpartum_window_can_fall_ill_then_expires(self):
        game.run('UPDATE game_state SET day=11')   # 避开 day % EPIDEMIC_INTERVAL == 0 的巧合
        day = game.cur_day()
        game.run('UPDATE consorts SET postpartum_until=? WHERE id=?', (day, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(day)
        self.assertTrue(game.get_consort(self.atk)['ill_day'])

        other = self.player('丙')
        game.run('UPDATE consorts SET postpartum_until=? WHERE id=?', (day - 1, other))   # 窗口已过
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(day)
        self.assertFalse(game.get_consort(other)['ill_day'])

    def test_epidemic_only_on_interval_days_and_skips_already_sick(self):
        game.run('UPDATE game_state SET day=?', (game.EPIDEMIC_INTERVAL - 1,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(game.cur_day())
        self.assertFalse(game.get_consort(self.atk)['ill_day'], '不到间隔天数，不该发时疫')
        game.run('UPDATE game_state SET day=?', (game.EPIDEMIC_INTERVAL,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(game.cur_day())
        self.assertTrue(game.get_consort(self.atk)['ill_day'])

    def test_already_poisoned_does_not_also_fall_ill(self):
        game.run('UPDATE consorts SET poisoned_day=? WHERE id=?', (game.cur_day(), self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(game.cur_day())
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_already_ill_not_retriggered(self):
        day = game.cur_day()
        game.fall_ill(self.atk, day, '久病体虚')
        health_after_first = game.get_consort(self.atk)['health']
        with patch.object(game.random, 'random', return_value=0.0):
            game.illness_onset_tick(day)
        self.assertEqual(game.get_consort(self.atk)['health'], health_after_first, '已经病着，不会再扣一次体质')


class IllnessCrisisTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_is_sick_blocks_actions_while_ill(self):
        game.fall_ill(self.atk, game.cur_day(), '久病体虚')
        self.assertTrue(game.is_sick(game.get_consort(self.atk)))

    def test_treat_route_detects_illness_and_heals(self):
        game.fall_ill(self.atk, game.cur_day(), '久病体虚')
        r = self.client.post(f'/treat/{self.atk}')
        self.assertEqual(r.status_code, 302)
        c = game.get_consort(self.atk)
        self.assertEqual(c['ill_treatment'], 1)
        self.assertEqual(c['poison_treatment'], 0)

    def test_untreated_illness_low_survival_treated_high(self):
        game.fall_ill(self.tgt, 10, '久病体虚')
        with patch.object(game.random, 'random', return_value=0.5):   # 落在 35%~90% 之间
            game.resolve_illness_crises(11)
        self.assertEqual(game.get_consort(self.tgt)['status'], 'dead', '没请太医，35% 生还率，0.5 该死了')
        self.assertEqual(game.get_consort(self.tgt)['death_reason'], '病逝')

        other = self.player('丙')
        game.fall_ill(other, 10, '久病体虚')
        game.run('UPDATE consorts SET ill_treatment=1 WHERE id=?', (other,))
        with patch.object(game.random, 'random', return_value=0.5):   # 落在 90% 以内，请了太医该活
            game.resolve_illness_crises(11)
        c = game.get_consort(other)
        self.assertEqual(c['status'], 'normal')
        self.assertEqual(c['ill_day'], 0)
        self.assertGreaterEqual(c['protected_until_day'], 11)

    def test_same_night_onset_not_resolved(self):
        day = game.cur_day()
        game.fall_ill(self.atk, day, '久病体虚')
        with patch.object(game.random, 'random', return_value=0.99):
            game.resolve_illness_crises(day)   # 当晚新病倒的人不该被判
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_recovered_gets_rescue_protection(self):
        game.fall_ill(self.atk, 10, '久病体虚')
        game.run('UPDATE consorts SET ill_treatment=1 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_illness_crises(11)
        c = game.get_consort(self.atk)
        self.assertEqual(c['protected_until_day'], 11 + game.RESCUE_PROTECT_DAYS)

    def test_ally_can_treat_with_enough_affinity(self):
        game.fall_ill(self.tgt, game.cur_day(), '久病体虚')
        game.add_affinity(self.atk, self.tgt, 30)
        r = self.client.post(f'/treat/{self.tgt}')
        self.assertEqual(game.get_consort(self.tgt)['ill_treatment'], 1)
        self.assertEqual(game.get_consort(self.atk)['silver'], 2000 - game.TREAT_COST)

    def test_stranger_cannot_treat(self):
        game.fall_ill(self.tgt, game.cur_day(), '久病体虚')
        self.client.post(f'/treat/{self.tgt}')
        self.assertEqual(game.get_consort(self.tgt)['ill_treatment'], 0)


class MiscarriageDifficultBirthHookTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_difficult_birth_opens_postpartum_window(self):
        game.run('UPDATE consorts SET pregnant_since=?, health=30 WHERE id=?', (game.cur_day() - game.PREGNANCY_DAYS, self.atk))
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game, 'npc_schemes'):
            game.settle_day()
        c = game.get_consort(self.atk)
        self.assertGreaterEqual(c['postpartum_until'], game.cur_day())

    def test_hanshui_miscarriage_opens_postpartum_window(self):
        game.run('UPDATE consorts SET rank=5, entered_day=1 WHERE id IN (?,?)', (self.atk, self.tgt))
        game.run('UPDATE game_state SET day=20')
        game.inv_add(self.atk, 'hanshui')
        game.run('UPDATE consorts SET pregnant_since=10 WHERE id=?', (self.tgt,))
        self.client.post('/intrigue/submit', data={'method': 'drug', 'drug': 'hanshui', 'target_id': self.tgt})
        it = game.q("SELECT * FROM intrigues WHERE method='drug' ORDER BY id DESC", one=True)
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_intrigue(it)
        c = game.get_consort(self.tgt)
        self.assertEqual(c['pregnant_since'], 0)
        self.assertGreaterEqual(c['postpartum_until'], game.cur_day())


class NpcIllnessTests(unittest.TestCase):
    """时疫不该把 NPC 成批带走：太医院自会照看她们"""
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_npc_illness_is_treated_from_the_start(self):
        npc = game.q("SELECT id FROM consorts WHERE npc_key='huanghou'", one=True)['id']
        game.fall_ill(npc, 10, '染上了时疫')
        c = game.get_consort(npc)
        self.assertEqual((c['ill_day'], c['ill_treatment']), (10, 1))
        with patch.object(game.random, 'random', return_value=0.5):   # 请了太医九成能活，0.5 该活
            game.resolve_illness_crises(11)
        self.assertNotEqual(game.get_consort(npc)['status'], 'dead')

    def test_player_illness_still_needs_a_doctor(self):
        c = game.get_consort(self.atk)
        game.fall_ill(self.atk, 10, '染上了时疫')
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'], 0)


if __name__ == '__main__':
    unittest.main()
