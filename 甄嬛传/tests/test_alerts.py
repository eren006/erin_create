"""告警与探针：结算出错、结算拖延、页面 500、备份失败会有人知道

运行：python3 -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class ImmediateThread:
    """让 send_alert_webhook 里的线程当场跑完，方便断言"""
    def __init__(self, target=None, daemon=None, **kw): self.target = target
    def start(self): self.target()


class AlertTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def rows(self):
        return game.q('SELECT * FROM alerts ORDER BY id')

    def admin(self):
        with self.client.session_transaction() as sess: sess['admin'] = True

    # ── 记告警 ───────────────────────────────────────────────────────────────

    def test_alert_is_recorded(self):
        game.raise_alert('settle', 'k1', '结算出错了', '细节')
        r = self.rows()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]['kind'], r[0]['key'], r[0]['message'], r[0]['detail'], r[0]['count'], r[0]['resolved']),
                         ('settle', 'k1', '结算出错了', '细节', 1, 0))

    def test_same_problem_only_counts_up(self):
        for i in range(3): game.raise_alert('settle', 'k1', f'第 {i} 次', 'x')
        r = self.rows()
        self.assertEqual((len(r), r[0]['count'], r[0]['message']), (1, 3, '第 2 次'))

    def test_a_resolved_problem_that_returns_is_a_new_alert(self):
        game.raise_alert('settle', 'k1', 'a')
        game.run('UPDATE alerts SET resolved=1')
        game.raise_alert('settle', 'k1', 'b')
        self.assertEqual(len(self.rows()), 2)

    def test_different_keys_are_separate_alerts(self):
        game.raise_alert('settle', 'k1', 'a'); game.raise_alert('error', 'k2', 'b')
        self.assertEqual(len(self.rows()), 2)

    def test_raise_alert_never_raises(self):
        with patch.object(game.sqlite3, 'connect', side_effect=RuntimeError('磁盘满了')):
            game.raise_alert('settle', 'k1', 'a')   # 不该把原来的错误盖住

    # ── 推送 ─────────────────────────────────────────────────────────────────

    def test_no_webhook_means_no_push(self):
        with patch.object(game, 'ALERT_WEBHOOK', ''), patch.object(game, '_post_webhook') as post:
            game.raise_alert('settle', 'k1', 'a')
        post.assert_not_called()
        self.assertFalse(game.send_alert_webhook('x'))

    def test_push_goes_out_once_then_waits_for_the_cooldown(self):
        with patch.object(game, 'ALERT_WEBHOOK', 'http://x/y'), patch.object(game.threading, 'Thread', ImmediateThread), \
             patch.object(game, '_post_webhook') as post:
            game.raise_alert('settle', 'k1', '结算出错了')
            game.raise_alert('settle', 'k1', '结算出错了')
            self.assertEqual(post.call_count, 1)
            self.assertIn('结算出错了', post.call_args[0][2])
            game.run('UPDATE alerts SET notified_ts=notified_ts-?', (game.ALERT_COOLDOWN + 1,))
            game.raise_alert('settle', 'k1', '结算出错了')
            self.assertEqual(post.call_count, 2)

    def test_push_failure_is_swallowed(self):
        with patch.object(game, 'ALERT_WEBHOOK', 'http://x/y'), patch.object(game.threading, 'Thread', ImmediateThread), \
             patch.object(game, '_post_webhook', side_effect=OSError('连不上')):
            game.raise_alert('settle', 'k1', 'a')
        self.assertEqual(len(self.rows()), 1)

    def test_payload_styles(self):
        self.assertEqual(game.alert_payload('json', 'hi'), {'text': 'hi'})
        self.assertEqual(game.alert_payload('wecom', 'hi'), {'msgtype': 'text', 'text': {'content': 'hi'}})
        self.assertEqual(game.alert_payload('dingtalk', 'hi'), {'msgtype': 'text', 'text': {'content': 'hi'}})
        self.assertEqual(game.alert_payload('feishu', 'hi'), {'msg_type': 'text', 'content': {'text': 'hi'}})
        self.assertEqual(game.alert_payload('whatever', 'hi'), {'text': 'hi'})

    # ── 结算拖延 ─────────────────────────────────────────────────────────────

    def now(self, h, m, day=(2026, 9, 25)):
        return datetime(*day, h, m, tzinfo=game.TZ)

    def test_overdue_minutes(self):
        st = dict(last_settle_date='2026-09-24')
        self.assertEqual(game.settle_overdue_minutes(self.now(20, 59), st), 0, '还没到点')
        self.assertEqual(game.settle_overdue_minutes(self.now(23, 0), st), 0)
        self.assertEqual(game.settle_overdue_minutes(self.now(23, 45), st), 45)
        self.assertEqual(game.settle_overdue_minutes(self.now(23, 59), dict(last_settle_date='2026-09-25')), 0, '今天已结算')

    def test_cycle_records_a_settle_exception_and_does_not_raise(self):
        with patch.object(game, 'maybe_settle', side_effect=ValueError('炸了')):
            game.run_settle_cycle()
        r = self.rows()
        self.assertEqual((r[0]['kind'], r[0]['key']), ('settle', 'settle-exception'))
        self.assertIn('炸了', r[0]['message'])
        self.assertIn('ValueError', r[0]['detail'])

    def test_cycle_repeated_failure_counts_up_instead_of_spamming(self):
        with patch.object(game, 'maybe_settle', side_effect=ValueError('炸了')):
            for _ in range(5): game.run_settle_cycle()
        r = self.rows()
        self.assertEqual((len(r), r[0]['count']), (1, 5))

    def test_cycle_flags_a_late_settlement(self):
        with patch.object(game, 'maybe_settle'), patch.object(game, 'settle_overdue_minutes', return_value=45):
            game.run_settle_cycle()
        r = self.rows()
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]['key'].startswith('settle-overdue:'))
        self.assertIn('45', r[0]['message'])

    def test_cycle_is_quiet_when_all_is_well(self):
        with patch.object(game, 'maybe_settle'), patch.object(game, 'settle_overdue_minutes', return_value=5):
            game.run_settle_cycle()
        self.assertEqual(len(self.rows()), 0)

    def test_cycle_flags_a_slow_settlement(self):
        ticks = iter([0, game.SLOW_SETTLE_SECONDS + 5, 100, 100, 100])
        with patch.object(game, 'maybe_settle'), patch.object(game.time, 'time', lambda: next(ticks)), \
             patch.object(game, 'settle_overdue_minutes', return_value=0):
            game.run_settle_cycle()
        self.assertEqual([r['key'] for r in self.rows()], ['settle-slow'])

    def test_a_real_settle_error_rolls_back_and_is_recorded(self):
        game.run("UPDATE game_state SET last_settle_date='2000-01-01'")
        day = game.cur_day()
        with patch.object(game, 'past_settle_time', return_value=True), patch.object(game, 'heir_growth_tick', side_effect=RuntimeError('npc 炸了')):
            game.run_settle_cycle()
        self.assertEqual(game.cur_day(), day, '结算出错整个回滚，天数不变')
        self.assertEqual(self.rows()[0]['key'], 'settle-exception')

    # ── 备份 ─────────────────────────────────────────────────────────────────

    def test_backup_creates_a_valid_copy_and_prunes(self):
        with tempfile.TemporaryDirectory() as d, patch.object(game, 'BACKUP_KEEP', 2):
            paths = []
            for i in range(4):
                paths.append(game.backup_db(d))
                os.rename(paths[-1], os.path.join(d, f'zhenhuan_20000101_00000{i}.db'))   # 同一秒生成的文件名会相同，手动错开
            left = sorted(os.listdir(d))
            self.assertEqual(len(left), 2)
            import sqlite3
            con = sqlite3.connect(os.path.join(d, left[-1]))
            self.assertTrue(con.execute("SELECT COUNT(*) FROM consorts").fetchone()[0] >= 2)
            con.close()

    # ── 探针 ─────────────────────────────────────────────────────────────────

    def test_healthz_ok(self):
        with patch.object(game, 'settle_overdue_minutes', return_value=0):
            r = self.client.get('/healthz')
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j['ok'])
        self.assertEqual((j['open_alerts'], j['mourning']), (0, False))
        self.assertNotIn('消息', str(j))

    def test_healthz_503_when_settlement_is_late(self):
        with patch.object(game, 'settle_overdue_minutes', return_value=game.SETTLE_OVERDUE_MINUTES):
            r = self.client.get('/healthz')
        self.assertEqual(r.status_code, 503)
        self.assertFalse(r.get_json()['ok'])

    def test_healthz_counts_open_alerts_and_survives_db_errors(self):
        game.raise_alert('error', 'k', 'a')
        with patch.object(game, 'settle_overdue_minutes', return_value=0):
            self.assertEqual(self.client.get('/healthz').get_json()['open_alerts'], 1)
        with patch.object(game, 'state', side_effect=RuntimeError('库坏了')):
            r = self.client.get('/healthz')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()['error'], 'RuntimeError')

    def test_healthz_needs_no_login(self):
        anon = game.app.test_client()
        with patch.object(game, 'settle_overdue_minutes', return_value=0):
            self.assertEqual(anon.get('/healthz').status_code, 200)

    # ── 页面 500 ─────────────────────────────────────────────────────────────

    def test_a_page_crash_is_recorded_and_the_player_sees_a_calm_message(self):
        game.app.config['PROPAGATE_EXCEPTIONS'] = False
        try:
            with patch.object(game, 'render_template', side_effect=KeyError('boom')):
                r = self.client.get('/clans')
        finally:
            game.app.config['PROPAGATE_EXCEPTIONS'] = None
        self.assertEqual(r.status_code, 500)
        self.assertIn('已经记下了', r.get_data(as_text=True))
        a = self.rows()[0]
        self.assertEqual(a['kind'], 'error')
        self.assertIn('/clans', a['message'])
        self.assertIn('KeyError', a['detail'])

    def test_the_same_crash_is_not_recorded_twice(self):
        game.app.config['PROPAGATE_EXCEPTIONS'] = False
        try:
            with patch.object(game, 'render_template', side_effect=KeyError('boom')):
                for _ in range(3): self.client.get('/clans')
        finally:
            game.app.config['PROPAGATE_EXCEPTIONS'] = None
        r = self.rows()
        self.assertEqual((len(r), r[0]['count']), (1, 3))

    # ── 后台 ─────────────────────────────────────────────────────────────────

    def test_admin_shows_alerts_and_a_banner(self):
        game.raise_alert('settle', 'k1', '夜间结算出错：炸了', 'Traceback…')
        self.admin()
        page = self.client.get('/admin').get_data(as_text=True)
        for t in ('告警', '夜间结算出错：炸了', '1 条告警没处理', '已处理', 'ALERT_WEBHOOK'):
            self.assertIn(t, page)

    def test_admin_banner_when_settlement_is_late(self):
        self.admin()
        with patch.object(game, 'settle_overdue_minutes', return_value=50):
            page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('拖了 50 分钟', page)

    def test_admin_can_resolve_one_or_all(self):
        game.raise_alert('settle', 'k1', 'a'); game.raise_alert('error', 'k2', 'b')
        self.admin()
        first = self.rows()[0]['id']
        self.client.post(f'/admin/alerts/resolve/{first}')
        self.assertEqual([r['resolved'] for r in self.rows()], [1, 0])
        self.client.post('/admin/alerts/resolve_all')
        self.assertEqual([r['resolved'] for r in self.rows()], [1, 1])
        self.assertNotIn('条告警没处理', self.client.get('/admin').get_data(as_text=True))

    def test_admin_actions_need_admin(self):
        game.raise_alert('settle', 'k1', 'a')
        anon = game.app.test_client()
        anon.post('/admin/alerts/resolve_all')
        self.assertEqual(self.rows()[0]['resolved'], 0)

    def test_admin_test_push(self):
        self.admin()
        with patch.object(game, 'ALERT_WEBHOOK', ''):
            r = self.client.post('/admin/alerts/test', follow_redirects=True)
            self.assertIn('还没配置', r.get_data(as_text=True))
        with patch.object(game, 'ALERT_WEBHOOK', 'http://x/y'), patch.object(game.threading, 'Thread', ImmediateThread), \
             patch.object(game, '_post_webhook') as post:
            r = self.client.post('/admin/alerts/test', follow_redirects=True)
        post.assert_called_once()
        self.assertIn('测试推送已发出', r.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
