"""选贡品：固定顺序、配额、独占领取、8小时接力和陈设权限。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class TributeTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def start(self, low_rank=4):
        game.run('UPDATE consorts SET rank=5,favor=100 WHERE id=?', (self.atk,))
        game.run('UPDATE consorts SET rank=?,favor=200 WHERE id=?', (low_rank, self.tgt))
        return game.start_tribute()

    def available(self, eid):
        return game.q('SELECT * FROM tribute_items WHERE event_id=? AND holder_id=0 ORDER BY id', (eid,))

    def choose(self, eid, ids=(), **extra):
        return self.client.post('/tribute/choose', data={'event_id': str(eid), 'item_id': [str(x) for x in ids], **extra}, follow_redirects=True)

    def test_catalog_has_seventy_six_unique_items_and_five_grades(self):
        eid = self.start()
        items = self.available(eid)
        self.assertEqual(len(items), 76)
        self.assertEqual(len({i['name'] for i in items}), 76)
        self.assertEqual({i['grade'] for i in items}, set(range(1, 6)))
        self.assertEqual(game.active_tribute()['timeout_hours'], 8)

    def test_rank_then_favor_order_and_snapshot_quotas(self):
        third = self.player('第三位', rank=5)
        game.run('UPDATE consorts SET favor=300 WHERE id=?', (third,))
        eid = self.start()
        queue = game.q('SELECT * FROM tribute_turns WHERE event_id=? ORDER BY position', (eid,))
        self.assertEqual([r['consort_id'] for r in queue], [third, self.atk, self.tgt])
        self.assertEqual([r['quota'] for r in queue], [3, 3, 2])
        game.run('UPDATE consorts SET rank=10 WHERE id=?', (self.tgt,))
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], third)

    def test_wrong_turn_does_not_claim_and_overquota_is_atomic(self):
        eid = self.start()
        ids = [i['id'] for i in self.available(eid)[:4]]
        self.login(self.tgt)
        self.choose(eid, ids[:1])
        self.assertEqual(len(self.available(eid)), 76)
        self.login(self.atk)
        self.choose(eid, ids)
        self.assertEqual(len(self.available(eid)), 76)
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.atk)

    def test_confirm_claims_transfers_and_announces_once(self):
        eid = self.start()
        ids = [i['id'] for i in self.available(eid)[:3]]
        silver, energy = game.get_consort(self.atk)['silver'], game.get_consort(self.atk)['energy']
        page = self.choose(eid, ids).get_data(as_text=True)
        self.assertEqual(len(self.available(eid)), 73)
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.tgt)
        self.assertEqual((game.get_consort(self.atk)['silver'], game.get_consort(self.atk)['energy']), (silver, energy))
        self.choose(eid, ids)
        self.assertEqual(game.q("SELECT COUNT(*) n FROM daily_feed WHERE consort_id=? AND text LIKE '选贡品：%'", (self.atk,), one=True)['n'], 1)
        self.assertIn('我领到的贡品', page)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '轮到你选贡品了%'", (self.tgt,), one=True))

    def test_low_rank_can_only_choose_one(self):
        eid = self.start(low_rank=3)
        self.assertEqual(game.q('SELECT quota FROM tribute_turns WHERE event_id=? AND consort_id=?', (eid, self.tgt), one=True)['quota'], 1)
        self.choose(eid, **{'pass': '1'})
        self.login(self.tgt)
        ids = [i['id'] for i in self.available(eid)[:2]]
        self.choose(eid, ids)
        self.assertEqual(len(self.available(eid)), 76)
        self.choose(eid, ids[:1])
        self.assertIsNone(game.active_tribute())
        self.assertEqual(len(self.available(eid)), 75)

    def test_duplicate_foreign_or_claimed_items_do_not_partially_claim(self):
        eid = self.start()
        ids = [i['id'] for i in self.available(eid)[:2]]
        for bad in ([ids[0], ids[0]], [ids[0], 999999]):
            self.choose(eid, bad)
            self.assertEqual(len(self.available(eid)), 76)
        self.choose(eid, ids[:1])
        self.login(self.tgt)
        self.choose(eid, ids[:1])
        self.assertEqual(len(self.available(eid)), 75)

    def test_eight_hour_timeout_carries_to_next_batch_and_restarts_timer(self):
        with patch.object(game, 'now_ts', return_value=100000): eid = self.start()
        with patch.object(game, 'now_ts', return_value=100000 + 8*3600 - 1): game.tribute_tick()
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.atk)
        with patch.object(game, 'now_ts', return_value=100000 + 8*3600):
            game.tribute_tick()
            game.tribute_tick()
        event = game.active_tribute()
        self.assertEqual({t['consort_id'] for t in game.tribute_group(event)}, {self.atk, self.tgt})      # 没选的并入下一批，一起挑
        self.assertEqual(event['turn_started_ts'], 100000 + 8*3600)

    def test_dead_current_skipped_and_repeat_start_rejected(self):
        eid = self.start()
        with self.assertRaises(game.Reject): game.start_tribute()
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (self.atk,))
        game.tribute_tick()
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.tgt)

    def test_items_display_in_own_room_visible_to_visitors_and_removable(self):
        eid = self.start(); ids = [i['id'] for i in self.available(eid)[:2]]
        self.choose(eid, ids)
        self.client.post('/tribute/display', data={'item_id': ids[0], 'slot': 'desk'})
        name = game.q('SELECT name FROM tribute_items WHERE id=?', (ids[0],), one=True)['name']
        self.assertIn(name, self.client.get('/room').get_data(as_text=True))
        self.login(self.tgt)
        self.client.post('/tribute/display', data={'item_id': ids[0], 'slot': 'wall'})
        self.client.post('/tribute/undisplay', data={'item_id': ids[0]})
        self.assertEqual(game.q('SELECT display_slot FROM tribute_items WHERE id=?', (ids[0],), one=True)['display_slot'], 'desk')
        self.assertIn(name, self.client.get(f'/room/{self.atk}').get_data(as_text=True))
        self.login(self.atk)
        self.client.post('/tribute/display', data={'item_id': ids[1], 'slot': 'desk'})
        self.assertEqual(game.q('SELECT display_slot FROM tribute_items WHERE id=?', (ids[0],), one=True)['display_slot'], '')
        self.client.post('/tribute/undisplay', data={'item_id': ids[1]})
        self.assertEqual(game.q('SELECT holder_id FROM tribute_items WHERE id=?', (ids[1],), one=True)['holder_id'], self.atk)

    def test_old_event_form_cannot_claim_from_new_event(self):
        eid = self.start()
        game.run("UPDATE tribute_events SET status='closed' WHERE id=?", (eid,))
        new = game.start_tribute()
        self.choose(eid, [self.available(new)[0]['id']])
        self.assertEqual(len(self.available(new)), 76)

    def test_guiren_can_choose_two_but_not_three(self):
        eid = self.start()
        self.choose(eid, **{'pass': '1'})
        self.login(self.tgt)
        ids = [i['id'] for i in self.available(eid)[:3]]
        self.choose(eid, ids)
        self.assertEqual(len(self.available(eid)), 76)
        self.choose(eid, ids[:2])
        self.assertEqual(len(self.available(eid)), 74)

    def test_grades_hidden_until_confirmation_then_revealed_in_feed(self):
        eid = self.start()
        before = self.client.get('/tribute').get_data(as_text=True)
        for grade, word in game.TRIBUTE_GRADES.items():
            self.assertNotIn(f'{word} · {grade}等', before)
        self.assertIn('品级待揭晓', before)
        item = self.available(eid)[0]
        after = self.choose(eid, [item['id']]).get_data(as_text=True)
        self.assertIn(f"{game.TRIBUTE_GRADES[item['grade']]} · {item['grade']}等", after)
        announcement = game.q("SELECT text FROM daily_feed WHERE consort_id=? AND text LIKE '选贡品：%'", (self.atk,), one=True)['text']
        self.assertIn(game.TRIBUTE_GRADES[item['grade']], announcement)

    def test_home_reminder_only_for_current_person_and_disappears_after_choice(self):
        eid = self.start()
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('轮到你选贡品了！', home)
        self.assertIn('现在去选贡品', home)
        self.login(self.tgt)
        self.assertNotIn('轮到你选贡品了！', self.client.get('/').get_data(as_text=True))
        self.login(self.atk)
        self.choose(eid, [self.available(eid)[0]['id']])
        self.assertNotIn('轮到你选贡品了！', self.client.get('/').get_data(as_text=True))
        self.login(self.tgt)
        self.assertIn('轮到你选贡品了！', self.client.get('/').get_data(as_text=True))

    def test_home_reminder_expires_and_moves_to_next_person(self):
        with patch.object(game, 'now_ts', return_value=100000): self.start()
        with patch.object(game, 'now_ts', return_value=100000 + 8*3600):
            for who in (self.atk, self.tgt):      # 嫔这批超时，并入贵人这批，两人一起挑，按贵人批的 4 小时重新计时
                reminder = game.tribute_home_reminder(game.get_consort(who))
                self.assertEqual((reminder['hours'], reminder['minutes']), (4, 0))

    def test_same_rank_choose_together_first_confirm_wins_and_conflict_asks_to_reselect(self):
        third = self.player('第三位', rank=5)
        eid = self.start()
        group = [t['consort_id'] for t in game.tribute_group(game.active_tribute())]
        self.assertEqual(set(group), {self.atk, third})
        for who in (self.atk, third):
            self.login(who)
            self.assertIn('轮到你选贡品了！', self.client.get('/').get_data(as_text=True))
        ids = [i['id'] for i in self.available(eid)[:3]]
        self.login(self.atk)
        self.choose(eid, [ids[0]])
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], third)      # 这一批还没选完，不换人
        self.login(third)
        page = self.choose(eid, [ids[0], ids[1]]).get_data(as_text=True)
        self.assertIn('先选走', page)
        self.assertIn('请重新选择', page)
        self.assertEqual(len(self.available(eid)), 75)                                          # 一件都没领，整单作废
        self.assertEqual(game.q('SELECT status FROM tribute_turns WHERE consort_id=?', (third,), one=True)['status'], 'waiting')
        self.choose(eid, [ids[1]])
        self.assertEqual(len(self.available(eid)), 74)
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.tgt)      # 两人都选完才轮到下一批
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '轮到你选贡品了%'", (self.tgt,), one=True))

    def test_same_rank_timeout_carries_the_whole_group_to_the_next(self):
        third = self.player('第三位', rank=5)
        with patch.object(game, 'now_ts', return_value=100000): eid = self.start()
        with patch.object(game, 'now_ts', return_value=100000 + 8*3600):
            game.tribute_tick()
        statuses = {r['consort_id']: r['status'] for r in game.q('SELECT * FROM tribute_turns WHERE event_id=?', (eid,))}
        self.assertEqual((statuses[self.atk], statuses[third]), ('waiting', 'waiting'))      # 没选的不作废，顺延到下一批
        self.assertEqual({t['consort_id'] for t in game.tribute_group(game.active_tribute())}, {self.atk, third, self.tgt})

    def test_pass_in_a_group_waits_for_the_others(self):
        third = self.player('第三位', rank=5)
        eid = self.start()
        self.choose(eid, **{'pass': '1'})
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], third)
        self.login(third)
        self.choose(eid, [self.available(eid)[0]['id']])
        self.assertEqual(game.tribute_current(game.active_tribute())['consort_id'], self.tgt)

    def test_legacy_event_without_rank_snapshot_is_grouped_after_backfill(self):
        third = self.player('第三位', rank=5)
        eid = self.start()
        game.run("UPDATE tribute_turns SET rank=0 WHERE event_id=?", (eid,))      # 模拟升级前开启的旧活动
        self.assertEqual(len(game.tribute_group(game.active_tribute())), 1)         # 补快照前一人一批
        db = game.get_db()
        game.backfill_tribute_ranks(db); db.commit()
        group = {t['consort_id'] for t in game.tribute_group(game.active_tribute())}
        self.assertEqual(group, {self.atk, third})

    def test_every_batch_carries_unpicked_players_to_the_next_after_timeout(self):
        high = self.player('嫔乙', rank=5)
        low = self.player('常在乙', rank=3)
        with patch.object(game, 'now_ts', return_value=100000):
            eid = self.start(low_rank=3)
        first = {t['consort_id'] for t in game.tribute_group(game.active_tribute())}
        self.assertIn(high, first)
        rank_first = game.q('SELECT rank FROM tribute_turns WHERE event_id=? AND consort_id=?', (eid, high), one=True)['rank']
        self.assertNotEqual(rank_first, game.TRIBUTE_MERGE_RANK)
        with patch.object(game, 'now_ts', return_value=100000 + 8 * 3600): game.tribute_tick()
        statuses = {r['consort_id']: r['status'] for r in game.q('SELECT * FROM tribute_turns WHERE event_id=?', (eid,))}
        self.assertEqual(statuses[high], 'waiting', '超时没选的不再作废，而是顺延到下一批')
        self.assertIn(high, {t['consort_id'] for t in game.tribute_group(game.active_tribute())})

    def test_guiren_batch_merges_into_next_batch_after_four_hours(self):
        a = self.player('贵人甲', rank=4)
        low = self.player('常在乙', rank=3)
        with patch.object(game, 'now_ts', return_value=100000):
            eid = self.start(low_rank=4)
            game.run('UPDATE tribute_turns SET status="done" WHERE event_id=? AND consort_id=?', (eid, self.atk))
            game.tribute_advance(game.active_tribute())
        group = {t['consort_id'] for t in game.tribute_group(game.active_tribute())}
        self.assertEqual(group, {self.tgt, a})
        with patch.object(game, 'now_ts', return_value=100000 + 4*3600 - 1): game.tribute_tick()
        self.assertEqual({t['consort_id'] for t in game.tribute_group(game.active_tribute())}, {self.tgt, a})
        with patch.object(game, 'now_ts', return_value=100000 + 4*3600): game.tribute_tick()
        event = game.active_tribute()
        merged = {t['consort_id'] for t in game.tribute_group(event)}
        self.assertEqual(merged, {self.tgt, a, low})                          # 没选的贵人并入常在这一批
        statuses = {r['consort_id']: r['status'] for r in game.q('SELECT * FROM tribute_turns WHERE event_id=?', (eid,))}
        self.assertEqual((statuses[self.tgt], statuses[a], statuses[low]), ('waiting', 'waiting', 'waiting'))
        self.assertEqual(event['turn_started_ts'], 100000 + 4*3600)           # 整批重新计时
        self.assertEqual(game.q('SELECT quota FROM tribute_turns WHERE event_id=? AND consort_id=?', (eid, a), one=True)['quota'], 2)      # 配额不变
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%并入下一批%'", (a,), one=True))
        self.login(self.tgt)
        ids = [i['id'] for i in self.available(eid)[:2]]
        with patch.object(game, 'now_ts', return_value=100000 + 4*3600 + 60):
            self.choose(eid, ids)
        self.assertEqual(len(self.available(eid)), 74)

    def test_guiren_batch_with_no_next_batch_is_skipped_after_four_hours(self):
        with patch.object(game, 'now_ts', return_value=100000):
            eid = self.start(low_rank=4)
            game.run('UPDATE tribute_turns SET status="done" WHERE event_id=? AND consort_id=?', (eid, self.atk))
            game.tribute_advance(game.active_tribute())
        with patch.object(game, 'now_ts', return_value=100000 + 4*3600): game.tribute_tick()
        self.assertIsNone(game.active_tribute())

if __name__ == '__main__': unittest.main()
