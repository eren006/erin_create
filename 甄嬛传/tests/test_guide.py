"""教引嬷嬷：新人引导线四步、遇事提点、跳过、老档迁移，见设计文档九点十一节

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class GuideStepTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def maid(self, owner, name='春桃'):
        return game.run("INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,'zhonghou',60,1,0)",
                        (owner, name)).lastrowid

    def test_dianxuan_starts_guide_at_step_zero(self):
        cid = self.player('新')
        game.run("UPDATE consorts SET status='xiunv', rank=0 WHERE id=?", (cid,))
        self.login(cid)
        qs = game.dianxuan_questions_for(cid)
        with patch.object(game.random, 'choice', return_value=('翊坤宫', 'east')), patch.object(game.random, 'random', return_value=.99):
            self.client.post('/dianxuan', data={q['key']: 0 for q in qs})
        c = game.get_consort(cid)
        self.assertEqual(c['guide_step'], 0)
        self.assertTrue(any('小主头一日进宫' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))))

    def test_step_zero_completes_on_picking_maid(self):
        game.run('UPDATE consorts SET guide_step=0 WHERE id=?', (self.atk,))
        silver0 = game.get_consort(self.atk)['silver']
        self.client.post('/maids/pick', data={'idx': 0, 'name': '春桃'})
        c = game.get_consort(self.atk)
        self.assertEqual(c['guide_step'], 1)
        self.assertEqual(c['silver'], silver0 + game.GUIDE_REWARD)
        self.assertTrue(any('像个样子了' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (self.atk,))))

    def test_step_one_needs_all_three_before_advancing(self):
        game.run('UPDATE consorts SET guide_step=1 WHERE id=?', (self.atk,))
        self.client.post('/act/greet')
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 1, '只做了一件，步子不该推进')
        game.run("DELETE FROM daily_counters WHERE consort_id=? AND key='study'", (self.atk,))
        self.client.post('/act/study', data={'art': game.ARTS[0]})
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 1)
        with patch.object(game.random, 'choices', return_value=['quiet']):
            self.client.post('/act/garden')
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 2, '三件都做了才推进到第二步')

    def test_step_three_or_group_either_side_completes_it(self):
        game.run('UPDATE consorts SET guide_step=3, silver=2000 WHERE id=?', (self.atk,))
        self.client.post('/act/eyes')
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 4, '安眼线也算过了第三步')

    def test_step_three_via_inspect_instead(self):
        game.run('UPDATE consorts SET guide_step=3 WHERE id=?', (self.atk,))
        self.maid(self.atk)
        self.client.post('/agents/act', data=dict(action='inspect'))
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 4)

    def test_letter_and_gazette_progress_step_two(self):
        game.run('UPDATE consorts SET guide_step=2, entered_day=1 WHERE id=?', (self.atk,))
        game.run('UPDATE game_state SET day=20')   # 满足附件的入宫 5 天门槛（这里只是发个信，不附东西也不受影响）
        self.client.post('/letters/send', data=dict(to_id=self.tgt, body='问候一声'))
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 2)
        self.client.get('/gazette')
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 2, '还差串门这一项')
        self.client.post('/act/visit', data={'target_id': self.tgt})
        self.assertEqual(game.get_consort(self.atk)['guide_step'], 3)

    def test_skip_hides_banner_and_stops_progress(self):
        game.run('UPDATE consorts SET guide_step=0 WHERE id=?', (self.atk,))
        self.client.post('/guide/skip')
        c = game.get_consort(self.atk)
        self.assertEqual(c['guide_step'], -1)
        self.assertIsNone(game.guide_view(c))
        self.client.post('/maids/pick', data={'idx': 0, 'name': '春桃'})
        self.assertEqual(game.get_consort(self.atk)['guide_step'], -1, '跳过之后不再计进度、不再发银子')

    def test_finished_guide_has_no_banner(self):
        game.run(f'UPDATE consorts SET guide_step=? WHERE id=?', (len(game.GUIDE_STEPS), self.atk))
        self.assertIsNone(game.guide_view(game.get_consort(self.atk)))
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_old_schema_backfills_skip_for_existing_players(self):
        import sqlite3
        from pathlib import Path
        old = str(Path(self.temp.name) / 'older.db')
        schema = (fixtures.ROOT / 'schema.sql').read_text()
        schema = '\n'.join(line for line in schema.splitlines()
                           if not line.strip().startswith(('guide_step ', 'guide_progress ', 'guide_tips ')))
        with sqlite3.connect(old) as db:
            db.executescript(schema)
            uid = db.execute('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', ('老玩家', 'x')).lastrowid
            db.execute("""INSERT INTO consorts(user_id,surname,given,rank,status,entered_day,rank_since_day,
                          family,personality,created_ts) VALUES(?,?,?,4,'normal',1,1,?,?,0)""",
                       (uid, '老', '玩家', next(iter(game.FAMILIES)), next(iter(game.PERSONALITIES))))
        original = game.DB_PATH
        game.DB_PATH = old
        game.init_db()
        with game.app.app_context():
            row = game.q("SELECT guide_step FROM consorts WHERE surname='老'", one=True)
            self.assertEqual(row['guide_step'], -1, '老档里已经在游戏里的角色不该突然冒出新人引导')
        game.DB_PATH = original


class GuideTipTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def tips_of(self, cid):
        return game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))

    def test_tip_shows_once(self):
        game.guide_tip(self.atk, 'poisoned', '第一句')
        game.guide_tip(self.atk, 'poisoned', '第二句，不该出现')
        texts = [m['text'] for m in self.tips_of(self.atk)]
        self.assertEqual(sum('许嬷嬷：' in t for t in texts), 1)
        self.assertTrue(any('第一句' in t for t in texts))
        self.assertFalse(any('第二句' in t for t in texts))

    def test_poisoned_tip_fires_via_poison_player(self):
        game.poison_player(self.atk, game.cur_day())
        self.assertTrue(any('快请太医' in m['text'] for m in self.tips_of(self.atk)))

    def test_cold_tip_fires_via_send_to_cold(self):
        game.send_to_cold(self.atk)
        self.assertTrue(any('冷宫的日子不好熬' in m['text'] for m in self.tips_of(self.atk)))

    def test_maid_death_tip_fires_on_dead_status(self):
        mid = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,'zhonghou',60,1,0)",
                       (self.atk, '秋菊')).lastrowid
        game.maid_leave(mid, 'dead', '试毒身亡')
        self.assertTrue(any('宫里的人来来去去' in m['text'] for m in self.tips_of(self.atk)))

    def test_maid_leave_gone_does_not_trigger_tip(self):
        mid = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,joined_day,created_ts) VALUES(?,?,'zhonghou',60,1,0)",
                       (self.atk, '秋菊')).lastrowid
        game.maid_leave(mid, 'gone', '遣散')
        self.assertFalse(any('宫里的人来来去去' in m['text'] for m in self.tips_of(self.atk)))

    def test_case_tip_fires_for_victim_and_suspect(self):
        game.run("UPDATE consorts SET entered_day=1 WHERE id IN (?,?)", (self.atk, self.tgt))
        game.run('UPDATE game_state SET day=20')
        it_id = game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,drug,item_used,created_ts) VALUES(20,?,?,'drug','yanzhi','yanzhi',0)",
                         (self.atk, self.tgt)).lastrowid
        game.open_drug_case(game.q('SELECT * FROM intrigues WHERE id=?', (it_id,), one=True))
        self.assertTrue(any('案子上了身' in m['text'] for m in self.tips_of(self.tgt)))

    def test_bed_and_pregnancy_tips_fire_at_settlement(self):
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertTrue(any('头一回侍寝' in m['text'] for m in self.tips_of(self.atk) + self.tips_of(self.tgt)))


if __name__ == '__main__':
    unittest.main()
