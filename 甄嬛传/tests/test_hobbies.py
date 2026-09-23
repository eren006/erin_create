"""雅趣：起意打磨成了三步、精力/免费门槛、兼修解锁、寝宫陈设、书信赠物

运行：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('game_hobbies', ROOT / 'app.py')
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


class HobbyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB_PATH = str(Path(self.temp.name) / 'test.db')
        game.app.config['TESTING'] = True
        game.init_db()
        self.ctx = game.app.app_context()
        self.ctx.push()
        game.run('UPDATE game_state SET day=10')
        self.me = self.player('甲', favor=90)     # 圣宠 >= HOBBY_FREE_FAVOR，占精力
        self.other = self.player('乙', favor=90)
        self.client = game.app.test_client()
        self.login(self.me)

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def player(self, name, favor=0, rank=4):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name, 'test')).lastrowid
        return game.run('''INSERT INTO consorts(user_id,surname,given,rank,status,entered_day,rank_since_day,
                           family,personality,silver,age_months,recap_seen_day,favor) VALUES(?,?,?,?,'normal',1,1,?,?,2000,240,9,?)''',
                        (uid, name, name + '儿', rank, next(iter(game.FAMILIES)), next(iter(game.PERSONALITIES)), favor)).lastrowid

    def login(self, cid):
        with self.client.session_transaction() as sess:
            sess['uid'] = game.get_consort(cid)['user_id']

    def finish_project(self, cid, kind, style=0, start_day=10):
        """走完起意→打磨→成了三步，返回做出的 hobby_items 行。手动跳天不会像结算那样回满精力，这里补上"""
        game.run('UPDATE consorts SET energy=? WHERE id=?', (game.ENERGY_MAX, cid))
        game.run('UPDATE game_state SET day=?', (start_day,))
        self.client.post('/hobby/start', data=dict(kind=kind, style=style))
        game.run('UPDATE game_state SET day=?', (start_day + 1,))
        self.client.post('/hobby/act')
        game.run('UPDATE game_state SET day=?', (start_day + 2,))
        self.client.post('/hobby/act')
        return game.q('SELECT * FROM hobby_items WHERE maker_id=? ORDER BY id DESC', (cid,), one=True)

    def test_pages_render(self):
        for route in ('/hobby', '/room'):
            self.assertEqual(self.client.get(route).status_code, 200, route)
        self.assertEqual(self.client.get(f'/room/{self.other}').status_code, 200)

    def test_three_steps_and_energy_cost_when_favored(self):
        e0 = game.get_consort(self.me)['energy']
        self.client.post('/hobby/start', data=dict(kind='flower', style=0))
        proj = game.current_hobby_project(self.me)
        self.assertEqual(proj['stage'], 0)
        self.assertEqual(game.get_consort(self.me)['energy'], e0 - game.HOBBY_ENERGY)

        game.run('UPDATE game_state SET day=11')
        self.client.post('/hobby/act')
        self.assertEqual(game.current_hobby_project(self.me)['stage'], 1)
        self.assertEqual(game.get_consort(self.me)['energy'], e0 - 2 * game.HOBBY_ENERGY)

        game.run('UPDATE game_state SET day=12')
        self.client.post('/hobby/act')
        self.assertIsNone(game.current_hobby_project(self.me))   # 完成后项目结项
        item = game.q('SELECT * FROM hobby_items WHERE maker_id=?', (self.me,), one=True)
        self.assertEqual((item['kind'], item['style'], item['holder_id']), ('flower', game.HOBBIES['flower']['styles'][0], self.me))

    def test_free_when_out_of_favor(self):
        game.run('UPDATE consorts SET favor=? WHERE id=?', (game.HOBBY_FREE_FAVOR - 1, self.me))
        e0 = game.get_consort(self.me)['energy']
        self.client.post('/hobby/start', data=dict(kind='flower', style=0))
        self.assertEqual(game.get_consort(self.me)['energy'], e0, '失宠时雅趣不占精力')

    def test_cannot_start_second_project_or_act_twice_same_day(self):
        self.client.post('/hobby/start', data=dict(kind='flower', style=0))
        self.client.post('/hobby/start', data=dict(kind='painting', style=0))
        self.assertEqual(game.current_hobby_project(self.me)['kind'], 'flower')
        self.client.post('/hobby/act')
        stage = game.current_hobby_project(self.me)['stage']
        self.client.post('/hobby/act')
        self.assertEqual(game.current_hobby_project(self.me)['stage'], stage, '同一天不能再打理')

    def test_no_stat_or_favor_reward_from_hobby(self):
        before = game.get_consort(self.me)
        self.finish_project(self.me, 'flower')
        after = game.get_consort(self.me)
        for k in ('appearance', 'talent', 'scheme', 'virtue', 'health', 'favor'):
            self.assertEqual(before[k], after[k], f'雅趣不该改 {k}')

    def test_second_kind_locked_until_three_items(self):
        r = self.client.get('/hobby')
        self.assertIn('莳花', r.get_data(as_text=True))
        self.finish_project(self.me, 'flower', style=0, start_day=10)
        self.assertNotIn('兼修', self.client.get('/hobby').get_data(as_text=True))
        self.client.post('/hobby/start', data=dict(kind='painting', style=0))
        self.assertIsNone(game.current_hobby_project(self.me), '没解锁书画之前不能开书画的项目')
        self.finish_project(self.me, 'flower', style=1, start_day=20)
        self.finish_project(self.me, 'flower', style=2, start_day=30)
        self.assertIn('兼修', self.client.get('/hobby').get_data(as_text=True))
        self.client.post('/hobby/unlock', data=dict(kind='painting'))
        self.assertEqual(sorted(game.hobby_unlocked_kinds(game.get_consort(self.me))), ['flower', 'painting'])
        self.client.post('/hobby/start', data=dict(kind='painting', style=0))
        self.assertEqual(game.current_hobby_project(self.me)['kind'], 'painting')

    def test_display_swap_and_undisplay(self):
        it1 = self.finish_project(self.me, 'flower', style=0, start_day=10)
        it2 = self.finish_project(self.me, 'flower', style=1, start_day=20)
        self.client.post('/hobby/display', data=dict(item_id=it1['id'], slot='window'))
        self.assertEqual(game.q('SELECT item_id FROM displays WHERE consort_id=? AND slot=?',
                                (self.me, 'window'), one=True)['item_id'], it1['id'])
        self.client.post('/hobby/display', data=dict(item_id=it2['id'], slot='window'))
        self.assertEqual(game.q('SELECT item_id FROM displays WHERE consort_id=? AND slot=?',
                                (self.me, 'window'), one=True)['item_id'], it2['id'], '同一格换新的不报错')
        self.client.post('/hobby/undisplay/window')
        self.assertIsNone(game.q('SELECT 1 FROM displays WHERE consort_id=? AND slot=?', (self.me, 'window'), one=True))

    def test_cannot_display_others_item(self):
        it = self.finish_project(self.me, 'flower', style=0, start_day=10)
        self.login(self.other)
        self.client.post('/hobby/display', data=dict(item_id=it['id'], slot='desk'))
        self.assertIsNone(game.q('SELECT 1 FROM displays WHERE consort_id=? AND slot=?', (self.other, 'desk'), one=True))

    def test_gift_transfers_item_clears_own_display_and_gives_affinity(self):
        it = self.finish_project(self.me, 'flower', style=0, start_day=10)
        self.client.post('/hobby/display', data=dict(item_id=it['id'], slot='desk'))
        r = self.client.post('/letters/send', data=dict(to_id=self.other, body='一点心意', hobby_item_id=it['id']))
        self.assertEqual(r.status_code, 302)
        gifted = game.q('SELECT * FROM hobby_items WHERE id=?', (it['id'],), one=True)
        self.assertEqual(gifted['holder_id'], self.other)
        self.assertIsNone(game.q('SELECT 1 FROM displays WHERE consort_id=? AND item_id=?', (self.me, it['id']), one=True))
        rel = game.relation(self.me, self.other)
        self.assertEqual(rel['affinity'], 2 + game.HOBBY_GIFT_AFFINITY, '每天第一封信 +2，附自己做的作品再 +10')
        history = json.loads(gifted['history'])
        self.assertEqual(history[-1], {'from': self.me, 'to': self.other, 'day': game.cur_day()})

    def test_cannot_regift_item_no_longer_held(self):
        it = self.finish_project(self.me, 'flower', style=0, start_day=10)
        self.client.post('/letters/send', data=dict(to_id=self.other, body='送一次', hobby_item_id=it['id']))
        self.client.post('/letters/send', data=dict(to_id=self.other, body='再送一次', hobby_item_id=it['id']))
        holder = game.q('SELECT holder_id FROM hobby_items WHERE id=?', (it['id'],), one=True)['holder_id']
        self.assertEqual(holder, self.other, '东西已经不在甲手里，第二次送不出去，持有人不变')

    def test_item_and_stat_gift_are_mutually_exclusive(self):
        it = self.finish_project(self.me, 'flower', style=0, start_day=10)
        game.inv_add(self.me, 'ruyi', 1)
        r = self.client.post('/letters/send', data=dict(to_id=self.other, body='都送', item='ruyi', hobby_item_id=it['id']))
        self.assertEqual(game.q('SELECT holder_id FROM hobby_items WHERE id=?', (it['id'],), one=True)['holder_id'], self.me)
        self.assertEqual(game.inv_qty(self.me, 'ruyi'), 1, '一次只能附一样，两样都填就该都不成功')

    def test_cold_palace_cannot_gift(self):
        it = self.finish_project(self.me, 'flower', style=0, start_day=10)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.me,))
        self.client.post('/letters/send', data=dict(to_id=self.other, body='冷宫也想送', hobby_item_id=it['id']))
        self.assertEqual(game.q('SELECT holder_id FROM hobby_items WHERE id=?', (it['id'],), one=True)['holder_id'], self.me)

    def test_quality_improves_with_experience(self):
        # 同一个骰子结果，做过的次数越多，品级越容易往上走——品级只看经验和运气，不看属性
        with patch.object(game.random, 'random', return_value=0.10):
            self.assertEqual(game.roll_hobby_quality(self.me, 'flower'), '普通')
            for _ in range(10):
                game.run("""INSERT INTO hobby_items (kind,style,quality,maker_id,holder_id,created_day,history)
                            VALUES ('flower','x','普通',?,?,1,'[]')""", (self.me, self.me))
            self.assertEqual(game.roll_hobby_quality(self.me, 'flower'), '精巧')

    def test_admin_reset_clears_hobby_tables(self):
        self.finish_project(self.me, 'flower', style=0, start_day=10)
        it = game.q('SELECT * FROM hobby_items WHERE maker_id=?', (self.me,), one=True)
        self.client.post('/hobby/display', data=dict(item_id=it['id'], slot='desk'))
        with self.client.session_transaction() as sess: sess['admin'] = True
        self.client.post('/admin/reset', data={'confirm': '重开'})
        for t in ('hobby_projects', 'hobby_items', 'displays'):
            self.assertFalse(game.q(f'SELECT 1 FROM {t}'), t)


if __name__ == '__main__':
    unittest.main()
