"""书信补全：翻页、标星、按人筛选、删信、管理员群发与领取，见设计文档九点八节

运行：python3 -m unittest discover -s tests -v
"""
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class LetterBoxTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def send(self, frm, to, body='一封信', **extra):
        return game.run("INSERT INTO letters(from_id,to_id,day,body,created_ts) VALUES(?,?,?,?,0)",
                        (frm, to, game.cur_day(), body)).lastrowid

    def test_inbox_pagination(self):
        for i in range(23):
            self.send(self.tgt, self.atk, body=f'第 {i} 封')
        r = self.client.get('/letters')
        body = r.get_data(as_text=True)
        self.assertIn('共 23 封', body)
        self.assertIn('第 22 封', body)      # 最新的在第一页
        self.assertNotIn('第 0 封', body)    # 最早的翻到第二页去了
        r2 = self.client.get('/letters?p=2')
        self.assertIn('第 0 封', r2.get_data(as_text=True))

    def test_starred_pinned_and_excluded_from_page_count(self):
        old = self.send(self.tgt, self.atk, body='很久以前的信')
        for i in range(20):
            self.send(self.tgt, self.atk, body=f'新信 {i}')
        self.client.post(f'/letters/star/{old}')
        body = self.client.get('/letters').get_data(as_text=True)
        self.assertIn('很久以前的信', body, '标星的信不翻页也能看到')
        self.assertIn('共 20 封', body, '标星的信不算进翻页总数')
        # 取消标星
        self.client.post(f'/letters/star/{old}')
        r2 = self.client.get('/letters')
        self.assertIn('共 21 封', r2.get_data(as_text=True))

    def test_star_requires_being_a_party(self):
        lid = self.send(self.tgt, self.atk)
        stranger = self.player('丙')
        self.login(stranger)
        self.client.post(f'/letters/star/{lid}')
        self.assertFalse(game.q('SELECT 1 FROM letter_stars WHERE letter_id=?', (lid,), one=True))

    def test_filter_by_person(self):
        丙 = self.player('丙')
        self.send(self.tgt, self.atk, body='乙写的')
        self.send(丙, self.atk, body='丙写的')
        body = self.client.get(f'/letters?with={self.tgt}').get_data(as_text=True)
        self.assertIn('乙写的', body)
        self.assertNotIn('丙写的', body)

    def test_delete_only_affects_own_side(self):
        lid = self.send(self.atk, self.tgt, body='要被删的信')
        self.client.post(f'/letters/delete/{lid}')   # self.atk 是登录中的发信人
        self.assertNotIn('要被删的信', self.client.get('/letters').get_data(as_text=True))
        self.login(self.tgt)   # 收信人那份还在
        self.assertIn('要被删的信', self.client.get('/letters').get_data(as_text=True))

    def test_delete_removes_own_star_too(self):
        lid = self.send(self.tgt, self.atk)
        self.client.post(f'/letters/star/{lid}')
        self.client.post(f'/letters/delete/{lid}')
        self.assertFalse(game.q('SELECT 1 FROM letter_stars WHERE letter_id=? AND consort_id=?', (lid, self.atk), one=True))

    def test_unread_count_excludes_deleted(self):
        lid = self.send(self.tgt, self.atk)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters WHERE to_id=? AND is_read=0 AND deleted_by_to=0',
                                (self.atk,), one=True)['n'], 1)
        self.client.post(f'/letters/delete/{lid}')
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters WHERE to_id=? AND is_read=0 AND deleted_by_to=0',
                                (self.atk,), one=True)['n'], 0)


class BroadcastTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def admin_login(self):
        with self.client.session_transaction() as sess:
            sess['admin'] = True

    def test_broadcast_to_all_with_attachment_needs_claim(self):
        self.admin_login()
        r = self.client.post('/admin/broadcast', data=dict(body='停服补偿', silver=50, item='', target='all'))
        self.assertEqual(r.status_code, 302)
        rows = game.q('SELECT * FROM letters WHERE is_broadcast=1')
        self.assertEqual({row['to_id'] for row in rows}, {self.atk, self.tgt})
        self.assertTrue(all(row['claimed'] == 0 for row in rows))
        bid = rows[0]['broadcast_id']
        self.assertTrue(all(row['broadcast_id'] == bid for row in rows), '同一批群发共用一个 broadcast_id')

    def test_broadcast_without_attachment_needs_no_claim(self):
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='纯通知', silver=0, item='', target='all'))
        rows = game.q('SELECT * FROM letters WHERE is_broadcast=1')
        self.assertTrue(all(row['claimed'] == 1 for row in rows))

    def test_broadcast_to_selected_players_only(self):
        丙 = self.player('丙')
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='只给乙', silver=10, item='', target='pick', to_ids=[str(self.tgt)]))
        rows = game.q('SELECT to_id FROM letters WHERE is_broadcast=1')
        self.assertEqual({r['to_id'] for r in rows}, {self.tgt})

    def test_claim_delivers_silver_and_item_once(self):
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='补偿', silver=30, item='renshen', target='all'))
        lid = game.q('SELECT id FROM letters WHERE to_id=? AND is_broadcast=1', (self.atk,), one=True)['id']
        self.login(self.atk)
        before = game.get_consort(self.atk)['silver']
        self.client.post(f'/letters/claim/{lid}')
        c = game.get_consort(self.atk)
        self.assertEqual(c['silver'], before + 30)
        self.assertEqual(game.inv_qty(self.atk, 'renshen'), 1)
        # 再领一次拿不到东西
        self.client.post(f'/letters/claim/{lid}')
        self.assertEqual(game.get_consort(self.atk)['silver'], before + 30)

    def test_cannot_delete_unclaimed_broadcast_letter(self):
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='补偿', silver=30, item='', target='all'))
        lid = game.q('SELECT id FROM letters WHERE to_id=? AND is_broadcast=1', (self.atk,), one=True)['id']
        self.login(self.atk)
        self.client.post(f'/letters/delete/{lid}')
        self.assertFalse(game.q('SELECT deleted_by_to FROM letters WHERE id=?', (lid,), one=True)['deleted_by_to'])
        self.client.post(f'/letters/claim/{lid}')
        self.client.post(f'/letters/delete/{lid}')
        self.assertTrue(game.q('SELECT deleted_by_to FROM letters WHERE id=?', (lid,), one=True)['deleted_by_to'])

    def test_dead_consort_cannot_claim_new_character_inherits(self):
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='补偿', silver=40, item='', target='all'))
        lid = game.q('SELECT id FROM letters WHERE to_id=? AND is_broadcast=1', (self.tgt,), one=True)['id']
        uid = game.get_consort(self.tgt)['user_id']
        game.die(self.tgt, '测试')
        self.login(self.tgt)
        self.client.post(f'/letters/claim/{lid}')
        self.assertEqual(game.q('SELECT claimed FROM letters WHERE id=?', (lid,), one=True)['claimed'], 0, '死了的角色领不了')

        # 重生：释放账号，建一个新秀女，走完殿选
        self.client.post('/rebirth')
        self.client.post('/create', data=dict(surname='新', given='人', age=18,
                                               family=next(iter(game.FAMILIES)), personality=next(iter(game.PERSONALITIES)),
                                               **{k: 0 for k in game.STAT_KEYS}))
        new_cid = game.q("SELECT id FROM consorts WHERE user_id=? AND status='xiunv'", (uid,), one=True)['id']
        qs = game.dianxuan_questions_for(new_cid)
        self.client.post('/dianxuan', data={q['key']: 0 for q in qs})
        self.assertEqual(game.get_consort(new_cid)['status'], 'normal')

        before = game.get_consort(new_cid)['silver']
        self.client.post(f'/letters/claim/{lid}')
        self.assertEqual(game.q('SELECT claimed FROM letters WHERE id=?', (lid,), one=True)['claimed'], 1, '归新建的秀女领')
        self.assertEqual(game.get_consort(new_cid)['silver'], before + 40)

    def test_admin_page_shows_claim_stats(self):
        self.admin_login()
        self.client.post('/admin/broadcast', data=dict(body='补偿', silver=10, item='', target='all'))
        lid = game.q('SELECT id FROM letters WHERE to_id=? AND is_broadcast=1', (self.atk,), one=True)['id']
        self.login(self.atk)
        self.client.post(f'/letters/claim/{lid}')
        self.admin_login()
        body = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('1/2', body)

    def test_admin_reset_clears_letter_stars(self):
        lid = game.run("INSERT INTO letters(from_id,to_id,day,body,created_ts) VALUES(?,?,1,'x',0)", (self.atk, self.tgt)).lastrowid
        game.run('INSERT INTO letter_stars(letter_id,consort_id) VALUES(?,?)', (lid, self.tgt))
        self.admin_login()
        self.client.post('/admin/reset', data={'confirm': '重开'})
        self.assertFalse(game.q('SELECT 1 FROM letter_stars'))


if __name__ == '__main__':
    unittest.main()
