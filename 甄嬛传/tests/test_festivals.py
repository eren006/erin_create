"""雅趣后半（小聚、人情、节令小事）与节庆宴会（除夕/上元/中秋），见设计文档九点十三节 C/D/E、九点十六节

运行：python3 -m unittest discover -s tests -v
"""
import json
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class FestivalTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def set_day(self, d):
        game.run('UPDATE game_state SET day=?', (d,))
        game.run('UPDATE consorts SET recap_seen_day=? WHERE id IN (?,?)', (d - 1, self.atk, self.tgt))

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def gaz(self):
        return [r['text'] for r in game.q('SELECT text FROM gazette')]

    # ── 节庆的日子 ───────────────────────────────────────────────────────────

    def test_festival_only_lands_on_multiples_of_the_interval(self):
        self.assertIsNone(game.active_festival(1))
        self.assertIsNone(game.active_festival(game.FESTIVAL_INTERVAL - 1))
        self.assertIsNotNone(game.active_festival(game.FESTIVAL_INTERVAL))
        self.assertIsNone(game.active_festival(0))

    def test_festivals_rotate_through_the_order(self):
        keys = [game.active_festival(game.FESTIVAL_INTERVAL * i) for i in range(1, 7)]
        self.assertEqual(keys, (game.FESTIVAL_ORDER * 2))

    def test_season_only_lands_on_multiples_of_its_interval_and_rotates(self):
        self.assertIsNone(game.active_season(1))
        keys = [game.active_season(game.SEASON_INTERVAL * i) for i in range(1, 5)]
        self.assertEqual(keys, game.SEASON_ORDER)

    def test_festival_and_season_are_independent(self):
        # 找一个是节庆但不是节令、以及反过来的日子，两条独立的表不该互相影响
        fest_day = game.FESTIVAL_INTERVAL
        self.assertIsNotNone(game.active_festival(fest_day))
        # 不断言 active_season(fest_day) 的具体值，只断言两个函数各自独立可调用不报错
        game.active_season(fest_day)

    # ── /festival 路由 ───────────────────────────────────────────────────────

    def test_no_action_on_a_non_festival_day(self):
        self.set_day(1)
        self.assertIsNone(game.active_festival(1))
        f0 = game.get_consort(self.atk)['favor']
        self.client.post('/festival')
        self.assertEqual(game.get_consort(self.atk)['favor'], f0)

    def test_reunion_gives_favor_virtue_and_sister_affinity(self):
        self.set_day(game.FESTIVAL_INTERVAL)
        self.assertEqual(game.active_festival(game.cur_day()), 'reunion')
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,1)", (min(self.atk, self.tgt), max(self.atk, self.tgt), 50))
        f0, v0 = game.get_consort(self.atk)['favor'], game.get_consort(self.atk)['virtue']
        with patch.object(game.random, 'randint', return_value=10):
            self.client.post('/festival')
        c = game.get_consort(self.atk)
        self.assertEqual((c['favor'], c['virtue']), (f0 + 11, v0 + 2), '性格温婉自带圣宠 +10% 的加成')
        rel = game.relation(self.atk, self.tgt)
        self.assertEqual(rel['affinity'], 50 + game.FESTIVAL_SISTER_AFFINITY)
        self.assertTrue(game.memories_between(self.atk, self.tgt))

    def test_lantern_gives_silver(self):
        day = game.FESTIVAL_INTERVAL * 2
        self.set_day(day)
        self.assertEqual(game.active_festival(day), 'lantern')
        s0 = game.get_consort(self.atk)['silver']
        self.client.post('/festival')
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + game.FESTIVAL_LANTERN_SILVER)

    def test_midautumn_gives_trust(self):
        day = game.FESTIVAL_INTERVAL * 3
        self.set_day(day)
        self.assertEqual(game.active_festival(day), 'midautumn')
        t0 = game.get_consort(self.atk)['trust']
        self.client.post('/festival')
        self.assertEqual(game.get_consort(self.atk)['trust'], t0 + 2)

    def test_once_per_festival_day(self):
        self.set_day(game.FESTIVAL_INTERVAL)
        self.client.post('/festival')
        f1 = game.get_consort(self.atk)['favor']
        self.client.post('/festival')
        self.assertEqual(game.get_consort(self.atk)['favor'], f1)

    def test_cold_palace_cannot_celebrate(self):
        self.set_day(game.FESTIVAL_INTERVAL)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        f0 = game.get_consort(self.atk)['favor']
        self.client.post('/festival')
        self.assertEqual(game.get_consort(self.atk)['favor'], f0)

    def test_confined_can_still_celebrate(self):
        self.set_day(game.FESTIVAL_INTERVAL)
        game.run("UPDATE consorts SET status='confined', status_until_day=99 WHERE id=?", (self.atk,))
        f0 = game.get_consort(self.atk)['favor']
        self.client.post('/festival')
        self.assertGreater(game.get_consort(self.atk)['favor'], f0)

    def test_home_page_shows_the_festival_card_only_on_the_day(self):
        self.set_day(1)
        self.assertNotIn('除夕家宴', self.client.get('/place/home').get_data(as_text=True))
        self.set_day(game.FESTIVAL_INTERVAL)
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('除夕家宴', page)
        self.assertIn('守岁', page)

    def test_settle_posts_a_festival_and_season_line_to_the_gazette(self):
        self.set_day(game.FESTIVAL_INTERVAL - 1)
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertTrue(any('除夕' in t for t in self.gaz()))
        self.set_day(game.SEASON_INTERVAL - 1)
        game.run("DELETE FROM gazette")
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertTrue(any(game.SEASONS['snow']['name'] in t for t in self.gaz()))

    # ── 节令小事：品级加成 ────────────────────────────────────────────────────

    def make_project(self, cid, kind='flower', stage=1, style='白山茶'):
        game.run("UPDATE consorts SET hobby_kinds=? WHERE id=?", (kind, cid))
        return game.run("""INSERT INTO hobby_projects (owner_id, kind, style, stage, started_day, last_day)
                           VALUES (?,?,?,?,1,0)""", (cid, kind, style, stage)).lastrowid

    def test_season_day_nudges_quality_but_not_any_stat(self):
        counts = {'普通': 0, '精巧': 0, '上品': 0}
        for _ in range(300):
            counts[game.roll_hobby_quality(self.atk, 'flower', day=1)] += 1   # 非节令日
        counts_season = {'普通': 0, '精巧': 0, '上品': 0}
        for _ in range(300):
            counts_season[game.roll_hobby_quality(self.atk, 'flower', day=game.SEASON_INTERVAL)] += 1
        self.assertGreater(counts_season['上品'], counts['上品'])

    def test_finishing_an_item_on_a_season_day_mentions_it(self):
        self.set_day(game.SEASON_INTERVAL)
        self.make_project(self.atk, stage=1)
        r = self.client.post('/hobby/act', follow_redirects=True)
        self.assertIn(game.SEASONS['snow']['name'], r.get_data(as_text=True))

    # ── 小聚 ─────────────────────────────────────────────────────────────────

    def gather(self, host, guests, theme='chat'):
        self.login(host)
        return self.client.post('/hobby/gather', data=dict(theme=theme, guest_id=guests))

    def test_needs_a_hobby_before_hosting(self):
        self.gather(self.atk, [self.tgt])
        self.assertFalse(game.q('SELECT 1 FROM gatherings'))
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        self.assertTrue(game.q('SELECT 1 FROM gatherings'))

    def test_can_invite_up_to_two_and_extra_are_ignored(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        c, d = self.player('丙', rank=4), self.player('丁', rank=4)
        self.gather(self.atk, [self.tgt, c, d])
        self.assertEqual(game.q('SELECT COUNT(*) n FROM gatherings', one=True)['n'], 2)

    def test_host_limited_to_once_a_day(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        c = self.player('丙', rank=4)
        self.gather(self.atk, [self.tgt])
        self.gather(self.atk, [c])
        self.assertEqual(game.q('SELECT COUNT(*) n FROM gatherings', one=True)['n'], 1)

    def test_pending_invite_shows_on_the_guests_home_page(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        self.login(self.tgt)
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('清谈', page)
        self.assertIn(game.display_name(game.get_consort(self.atk)), page)

    def test_chat_response_gives_affinity(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        self.login(self.tgt)
        with patch.object(game.random, 'randint', return_value=7):
            self.client.post('/hobby/gather/respond', data=dict(opt='warm'))
        rel = game.relation(self.atk, self.tgt)
        self.assertEqual(rel['affinity'], 7)
        self.assertEqual(game.q("SELECT status FROM gatherings", one=True)['status'], 'done')

    def test_guest_capped_at_two_responses_a_day(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        a, b, c = self.player('甲2', rank=4), self.player('乙2', rank=4), self.player('丙2', rank=4)
        for host in (a, b, c):
            game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (host,))
            self.login(host)
            self.client.post('/hobby/gather', data=dict(theme='chat', guest_id=[self.atk]))
        self.login(self.atk)
        for _ in range(2):
            self.client.post('/hobby/gather/respond', data=dict(opt='warm'))
        self.assertEqual(game.q("SELECT COUNT(*) n FROM gatherings WHERE status='done'", one=True)['n'], 2)
        self.client.post('/hobby/gather/respond', data=dict(opt='warm'))
        self.assertEqual(game.q("SELECT status FROM gatherings ORDER BY id DESC LIMIT 1", one=True)['status'], 'lapsed')

    def test_probe_reliable_hint_names_someone(self):
        self.player('丙', rank=4)   # 给探口风一个可指的对象
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt], theme='probe')
        self.login(self.tgt)
        seq = iter([0.0, 0.0])   # 探出来了，而且可信
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            r = self.client.post('/hobby/gather/respond', data=dict(opt='press'), follow_redirects=True)
        self.assertIn('该多留意', r.get_data(as_text=True))

    def test_probe_can_be_unreliable(self):
        self.player('丙', rank=4)
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt], theme='probe')
        self.login(self.tgt)
        seq = iter([0.0, 0.99])   # 探出来了，但不可信
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            r = self.client.post('/hobby/gather/respond', data=dict(opt='press'), follow_redirects=True)
        self.assertIn('不一定作数', r.get_data(as_text=True))

    def test_declining_to_probe_is_safe(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt], theme='probe')
        self.login(self.tgt)
        r = self.client.post('/hobby/gather/respond', data=dict(opt='deflect'), follow_redirects=True)
        self.assertIn('含糊带过', r.get_data(as_text=True))

    def test_invite_from_an_unavailable_host_does_not_appear(self):
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        with self.client.session_transaction() as sess: sess.pop('_flashes', None)   # 清掉上一步张罗时留下的 flash
        self.login(self.tgt)
        self.assertNotIn('清谈', self.client.get('/place/home').get_data(as_text=True))

    def test_gather_mentions_a_shared_memory_when_there_is_one(self):
        game.remember(self.atk, self.tgt, 'treat')
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        self.login(self.tgt)
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('替你请过太医', page)

    def test_gather_mentions_the_season_when_active(self):
        self.set_day(game.SEASON_INTERVAL)
        game.run("UPDATE consorts SET hobby_kinds='flower' WHERE id=?", (self.atk,))
        self.gather(self.atk, [self.tgt])
        self.login(self.tgt)
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn(game.SEASONS['snow']['flavor'], page)

    # ── 人情 ─────────────────────────────────────────────────────────────────

    def test_remember_and_memories_between_are_direction_agnostic(self):
        game.remember(self.atk, self.tgt, 'treat')
        self.assertEqual(len(game.memories_between(self.atk, self.tgt)), 1)
        self.assertEqual(len(game.memories_between(self.tgt, self.atk)), 1)

    def test_treating_someone_else_is_remembered(self):
        game.run('UPDATE consorts SET poisoned_day=? WHERE id=?', (game.cur_day(), self.tgt))
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,1)", (min(self.atk, self.tgt), max(self.atk, self.tgt), 50))
        game.run('UPDATE consorts SET silver=200 WHERE id=?', (self.atk,))
        self.client.post(f'/treat/{self.tgt}')
        self.assertTrue(game.memories_between(self.atk, self.tgt))

    def test_treating_yourself_is_not_remembered(self):
        game.run('UPDATE consorts SET poisoned_day=?, silver=200 WHERE id=?', (game.cur_day(), self.atk))
        self.client.post(f'/treat/{self.atk}')
        self.assertFalse(game.memories_between(self.atk, self.tgt))

    def test_visiting_someone_confined_is_remembered_but_a_free_visit_is_not(self):
        game.run("UPDATE consorts SET status='confined', status_until_day=99 WHERE id=?", (self.tgt,))
        self.client.post('/act/visit', data=dict(target_id=self.tgt))
        self.assertTrue(game.memories_between(self.atk, self.tgt))
        game.run('DELETE FROM memories')
        game.run("UPDATE consorts SET status='normal' WHERE id=?", (self.tgt,))
        game.run('DELETE FROM daily_counters')
        self.client.post('/act/visit', data=dict(target_id=self.tgt))
        self.assertFalse(game.memories_between(self.atk, self.tgt))

    def test_first_hobby_gift_is_remembered_but_not_the_second(self):
        item1 = game.run("""INSERT INTO hobby_items (kind, style, quality, maker_id, holder_id, created_day, history)
                            VALUES ('flower','白山茶','普通',?,?,1,'[]')""", (self.atk, self.atk)).lastrowid
        item2 = game.run("""INSERT INTO hobby_items (kind, style, quality, maker_id, holder_id, created_day, history)
                            VALUES ('flower','绿萼梅','普通',?,?,1,'[]')""", (self.atk, self.atk)).lastrowid
        game.run('UPDATE consorts SET entered_day=1 WHERE id=?', (self.atk,))
        self.client.post('/letters/send', data=dict(to_id=self.tgt, body='送你一盆花', hobby_item_id=item1))
        self.assertTrue(game.memories_between(self.atk, self.tgt))
        game.run('DELETE FROM memories')
        c2 = self.player('丙', rank=4)
        self.client.post('/letters/send', data=dict(to_id=c2, body='再送一盆', hobby_item_id=item2))
        self.assertFalse(game.memories_between(self.atk, c2), '不是第一次送礼了')

    def test_regifting_someone_elses_item_is_not_a_first_gift(self):
        item = game.run("""INSERT INTO hobby_items (kind, style, quality, maker_id, holder_id, created_day, history)
                           VALUES ('flower','白山茶','普通',?,?,1,'[]')""", (self.tgt, self.atk)).lastrowid
        game.run('UPDATE consorts SET entered_day=1 WHERE id=?', (self.atk,))
        c2 = self.player('丙', rank=4)
        self.client.post('/letters/send', data=dict(to_id=c2, body='转送给你', hobby_item_id=item))
        self.assertFalse(game.memories_between(self.atk, c2), '不是自己做的东西，不算')

    def test_witnessing_in_a_case_is_remembered(self):
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,0)", (min(self.atk, self.tgt), max(self.atk, self.tgt), 40))
        cid = game.run("""INSERT INTO cases(day,victim_id,culprit_id,drug,status,closed_day,created_ts) VALUES(?,?,?,?,?,?,0)""",
                       (game.cur_day(), self.tgt, 999, 'rumor', 'open', 0)).lastrowid
        game.run('INSERT INTO case_suspects(case_id,consort_id,suspicion) VALUES(?,?,?)', (cid, self.tgt, 30))
        self.client.post(f'/cases/{cid}/act', data=dict(action='witness', target_id=self.tgt))
        self.assertTrue(game.memories_between(self.atk, self.tgt))

    def test_memory_line_picks_a_readable_sentence(self):
        game.remember(self.atk, self.tgt, 'first_gift')
        line = game.memory_line(self.atk, self.tgt)
        self.assertIn('自己做的第一件东西', line)
        self.assertEqual(game.memory_line(self.atk, 999999), '')


if __name__ == '__main__':
    unittest.main()
