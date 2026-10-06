"""托管角色：看起来是玩家，由系统代为日常"""
import unittest
from unittest.mock import patch
from datetime import datetime
import test_lifecycle as fixtures

game = fixtures.game


class ManagedConsortTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def spawn(self, **kw):
        return game.spawn_managed_consort(kw.pop('surname', '夏'), kw.pop('given', '知意'), **kw)

    def at(self, hour):
        return datetime(2026, 10, 7, hour, 30, tzinfo=game.TZ)

    def test_spawn_looks_exactly_like_a_player(self):
        cid = self.spawn()
        c = game.get_consort(cid)
        self.assertEqual((c['status'], c['rank']), ('normal', 4))
        self.assertTrue(c['user_id'])
        self.assertFalse(c['npc_key'], '玩家这边不能有任何 NPC 标记')
        self.assertTrue(c['palace'] and c['hall'])
        self.assertTrue(c['title'], '贵人有封号')
        self.assertTrue(game.family_row(c['user_id']))
        self.assertEqual(game.q("SELECT managed FROM users WHERE id=?", (c['user_id'],), one=True)['managed'], 1)
        self.assertIn('夏', game.full_name(c))
        self.assertFalse(game.q("SELECT 1 FROM gazette WHERE text LIKE '%夏知意%'", one=True), '不留入宫痕迹')

    def test_spawn_rejects_taken_surname_and_name(self):
        self.spawn()
        with self.assertRaises(ValueError): self.spawn(surname='夏', given='别名')
        pid = self.player('丙')
        with self.assertRaises(ValueError): game.spawn_managed_consort('丙', '测试')

    def test_cannot_log_in(self):
        self.spawn()
        username = game.q("SELECT username FROM users WHERE managed=1", one=True)['username']
        client = game.app.test_client()
        r = client.post('/login', data={'username': username, 'password': 'anything'})
        self.assertNotEqual(r.status_code, 302)

    def test_it_joins_the_bedding_pool_and_ranks_like_a_player(self):
        cid = self.spawn()
        self.assertTrue(game.eligible_bedding(game.get_consort(cid), game.cur_day()))
        self.assertIn(cid, [r['id'] for r in game.q("SELECT id FROM consorts WHERE user_id IS NOT NULL")])

    def test_acts_in_daytime_and_writes_to_the_daily_feed(self):
        cid = self.spawn()
        self.player('丁')
        game.run("UPDATE game_state SET event_started=1,maintenance=0")
        done = 0
        with patch.object(game.random, 'random', return_value=0.0):
            for _ in range(6):
                game.bot_tick(self.at(10))
        self.assertGreaterEqual(len(game.q("SELECT 1 FROM daily_feed WHERE consort_id=?", (cid,))), 1)
        self.assertLess(game.get_consort(cid)['energy'], game.ENERGY_MAX)

    def test_sleeps_at_night_and_when_chance_misses(self):
        cid = self.spawn()
        game.run("UPDATE game_state SET event_started=1,maintenance=0")
        with patch.object(game.random, 'random', return_value=0.0):
            game.bot_tick(self.at(3))
        self.assertFalse(game.q("SELECT 1 FROM daily_feed WHERE consort_id=?", (cid,), one=True))
        with patch.object(game.random, 'random', return_value=0.99):
            game.bot_tick(self.at(10))
        self.assertFalse(game.q("SELECT 1 FROM daily_feed WHERE consort_id=?", (cid,), one=True))

    def test_visit_leaves_a_message_for_the_real_player_like_a_human(self):
        cid = self.spawn()
        real = self.player('丁')
        game.run("UPDATE consorts SET energy=8 WHERE id=?", (cid,))
        self.assertTrue(game.bot_do(game.get_consort(cid), 'visit'))
        notes = [r['text'] for r in game.q("SELECT text FROM messages WHERE consort_id IN (?,?,?)", (real, self.atk, self.tgt))
                 if '坐了坐' in r['text']]
        self.assertEqual(len(notes), 1, '随机挑了一位真玩家串门')
        self.assertIn('好感', notes[0])
        self.assertIn(game.display_name(game.get_consort(cid)), notes[0])
        self.assertTrue(any('坐了坐' in r['text'] for r in game.q("SELECT text FROM daily_feed")))

    def test_daily_caps_and_costs_are_respected(self):
        cid = self.spawn()
        game.run("UPDATE consorts SET energy=8 WHERE id=?", (cid,))
        c = game.get_consort(cid)
        self.assertTrue(game.bot_do(c, 'greet'))
        self.assertFalse(game.bot_do(game.get_consort(cid), 'greet'), '晨省一天一次')
        game.run("UPDATE consorts SET energy=0 WHERE id=?", (cid,))
        self.assertFalse(game.bot_do(game.get_consort(cid), 'study'), '没精力不做')

    def test_pending_scenes_never_pile_up(self):
        cid = self.spawn()
        game.run("UPDATE consorts SET energy=8, pending_scene='x' WHERE id=?", (cid,))
        game.bot_do(game.get_consort(cid), 'garden')
        self.assertEqual(game.get_consort(cid)['pending_scene'], '')

    def test_care_calls_the_doctor_and_names_children(self):
        cid = self.spawn()
        game.run("UPDATE consorts SET silver=500, ill_day=?, ill_treatment=0, poisoned_day=0 WHERE id=?", (game.cur_day(), cid))
        game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,gen_word) VALUES(?,?,'皇子',1,?,'弘')", (cid, cid, game.cur_day()))
        game.bot_care(game.get_consort(cid))
        self.assertEqual(game.get_consort(cid)['ill_treatment'], 1)
        h = game.q("SELECT * FROM heirs WHERE mother_id=?", (cid,), one=True)
        self.assertTrue(h['name'].startswith('弘') and len(h['name']) == 2)

    def test_admin_marks_it_but_players_pages_do_not(self):
        cid = self.spawn()
        c = game.get_consort(cid)
        client = game.app.test_client()
        with client.session_transaction() as sess: sess['admin'] = True
        self.assertIn('托管', client.get('/admin').get_data(as_text=True))
        self.login(self.atk)
        page = self.client.get('/ranks').get_data(as_text=True)
        self.assertIn(game.display_name(c), page)
        self.assertNotIn('托管', page)
        self.assertNotIn('NPC', page)

    def test_scheduler_calls_bot_tick_each_minute(self):
        game.run('UPDATE game_state SET event_started=1,maintenance=0')
        game.run("UPDATE game_state SET last_settle_date='2026-10-07'")
        with patch.object(game, 'datetime') as clock, patch.object(game, 'bedding_round'), patch.object(game, 'energy_tick'), \
             patch.object(game, 'resolve_births'), patch.object(game, 'maybe_banquet'), patch.object(game, 'bot_tick') as tick:
            clock.now.return_value = self.at(14)
            game.maybe_settle()
        tick.assert_called_once()

    # ── 害人 ───────────────────────────────────────────────────────────────

    def bot(self, **kw):
        cid = self.spawn(**kw)
        game.run("UPDATE consorts SET energy=8, silver=1000 WHERE id=?", (cid,))
        game.run("UPDATE consorts SET entered_day=1 WHERE id IN (?,?)", (self.atk, self.tgt))
        return cid

    def test_bot_intrigue_submits_a_cheap_intrigue_against_a_real_player_and_pays(self):
        cid = self.bot()
        before = game.get_consort(cid)['silver']
        self.assertTrue(game.bot_intrigue(game.get_consort(cid)))
        it = game.q("SELECT * FROM intrigues WHERE attacker_id=?", (cid,), one=True)
        self.assertIn(it['method'], ('rumor', 'steal', 'frame'))
        self.assertIn(it['target_id'], (self.atk, self.tgt))
        self.assertEqual(it['status'], 'pending')
        self.assertEqual(game.get_consort(cid)['silver'], before - game.INTRIGUES[it['method']]['silver'])
        self.assertEqual(game.daily_count(cid, 'intrigue'), 1)

    def test_at_most_one_a_day_and_never_when_sick_or_confined(self):
        cid = self.bot()
        self.assertTrue(game.bot_intrigue(game.get_consort(cid)))
        self.assertFalse(game.bot_intrigue(game.get_consort(cid)), '一天只谋划一件事')
        game.run("DELETE FROM daily_counters")
        game.run("UPDATE consorts SET status='confined' WHERE id=?", (cid,))
        self.assertFalse(game.bot_intrigue(game.get_consort(cid)))
        game.run("UPDATE consorts SET status='normal', ill_day=? WHERE id=?", (game.cur_day(), cid))
        self.assertFalse(game.bot_intrigue(game.get_consort(cid)))

    def test_new_arrivals_and_other_managed_players_are_never_targets(self):
        cid = self.bot()
        other_bot = game.spawn_managed_consort('商', '雨墨')
        game.run("UPDATE consorts SET entered_day=? WHERE id IN (?,?)", (game.cur_day(), self.atk, self.tgt))   # 今天才入宫，受保护
        self.assertFalse(game.bot_intrigue(game.get_consort(cid)))
        self.assertFalse(game.q("SELECT 1 FROM intrigues WHERE target_id IN (?,?)", (cid, other_bot), one=True))

    def test_grudge_raises_the_weight_of_those_who_attacked_her_and_those_she_attacked(self):
        cid = self.bot()
        targets = [game.get_consort(self.atk), game.get_consort(self.tgt)]
        self.assertEqual(game.bot_grudge_weights(game.get_consort(cid), targets), [1, 1])
        game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,status,created_ts) VALUES(?,?,?,'rumor','done',0)", (game.cur_day(), self.atk, cid))
        game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,status,created_ts) VALUES(?,?,?,'rumor','done',0)", (game.cur_day(), cid, self.tgt))
        self.assertEqual(game.bot_grudge_weights(game.get_consort(cid), targets), [1 + game.BOT_GRUDGE_ATTACKED, 1 + game.BOT_GRUDGE_VICTIM])
        game.run("UPDATE intrigues SET day=? ", (game.cur_day() - game.BOT_GRUDGE_DAYS - 1,))
        self.assertEqual(game.bot_grudge_weights(game.get_consort(cid), targets), [1, 1], '仇不会记一辈子')

    def test_target_choice_ignores_scheme(self):
        cid = self.bot()
        game.run("UPDATE consorts SET scheme=100 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET scheme=5 WHERE id=?", (self.tgt,))
        self.assertEqual(game.bot_grudge_weights(game.get_consort(cid), [game.get_consort(self.atk), game.get_consort(self.tgt)]), [1, 1])

    def test_steal_skips_pregnant_target_and_money_is_topped_up(self):
        cid = self.bot()
        game.run("UPDATE consorts SET pregnant_since=3 WHERE id IN (?,?)", (self.atk, self.tgt))
        with patch.object(game.random, 'choices', side_effect=lambda pop, weights=None, k=1: [('steal' if 'steal' in pop else pop[0])]):
            self.assertFalse(game.bot_intrigue(game.get_consort(cid)))
        game.run("UPDATE consorts SET silver=10 WHERE id=?", (cid,))
        game.bot_care(game.get_consort(cid))
        self.assertEqual(game.get_consort(cid)['silver'], game.BOT_SILVER_FLOOR)

    def test_it_resolves_like_a_player_intrigue_and_can_be_caught(self):
        cid = self.bot()
        with patch.object(game.random, 'choices', side_effect=lambda pop, weights=None, k=1: [pop[0]]):     # 第一个目标、第一种手段（流言）
            self.assertTrue(game.bot_intrigue(game.get_consort(cid)))
        it = game.q("SELECT * FROM intrigues WHERE attacker_id=?", (cid,), one=True)
        self.assertEqual(it['method'], 'rumor')
        virtue = game.get_consort(cid)['virtue']
        with patch.object(game.random, 'random', side_effect=[0.99, 0.0] + [0.5] * 30):     # 失手并被当场拿住
            self.assertEqual(game.resolve_intrigue(it)[0], 'caught')
        self.assertEqual(game.get_consort(cid)['virtue'], virtue - 5, '和玩家一样受罚')
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%败露%'", (cid,), one=True))

    def test_scheduler_gates_are_independent(self):
        cid = self.bot()
        game.run("UPDATE game_state SET event_started=1,maintenance=0")
        with patch.object(game.random, 'random', return_value=0.5):      # 日常和起意都没触发
            with patch.object(game, 'bot_intrigue') as intrigue:
                game.bot_tick(self.at(10))
                intrigue.assert_not_called()
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game, 'bot_intrigue') as intrigue:
            game.bot_tick(self.at(10))
            intrigue.assert_called_once()
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game, 'bot_intrigue') as intrigue:
            game.bot_tick(self.at(3))
            intrigue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
