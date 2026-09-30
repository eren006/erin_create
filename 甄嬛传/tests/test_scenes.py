"""偶遇场景与召见问题池（2026-09-29 扩充）：内容格式、NPC 在场才出、NPC 好感效果

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle

game = test_lifecycle.game
EFFECT_KEYS = set(game.EFFECT_NAMES) | {'seek'} | game.NPC_KEYS


class SceneContentTests(unittest.TestCase):
    """只查数据，不用数据库"""

    def check_opts(self, opts, where):
        self.assertGreaterEqual(len(opts), 2, where)
        for o in opts:
            self.assertIn(o['stat'], (None, *game.CHECK_NAMES), where)
            self.assertTrue(o['win_text'], where)
            self.assertLessEqual(set(o['win']), EFFECT_KEYS, where)
            if o['stat'] is not None:
                self.assertIn('dc', o, where)
                self.assertIn('lose_text', o, where)
                self.assertLessEqual(set(o.get('lose', {})), EFFECT_KEYS, where)

    def test_scene_format(self):
        for key, cfg in game.SCENES.items():
            self.check_opts(cfg['opts'], key)
            if cfg.get('npc'):
                self.assertIn(cfg['npc'], game.NPC_KEYS, key)

    def test_audience_format(self):
        for i, p in enumerate(game.AUDIENCE_PROMPTS):
            self.check_opts(p['opts'], f'audience#{i}')
            # 固定三路：第三项直言，成败都涨信任或至少不扣（EmperorTests 靠这条）
            self.assertGreater(p['opts'][2]['win'].get('trust', 0), 0, f'audience#{i}')

    def test_every_scene_is_reachable(self):
        pools = set(game.EMPEROR_SCENES) | set(game.NPC_SCENES) | set(game.GREET_SCENES) | {'seek_angry', 'yangxin_emperor'}
        self.assertEqual(pools, set(game.SCENES))

    def test_no_canon_only_names(self):
        """NPC 每届换人：场景里只能叫封号，不能写原著人名"""
        for key, cfg in game.SCENES.items():
            blob = cfg['text'] + ''.join(o['text'] + o['win_text'] + o.get('lose_text', '') for o in cfg['opts'])
            for name in ('世兰', '宜修', '年羹尧', '温宜', '三阿哥', '甄嬛', '安陵容'):
                self.assertNotIn(name, blob, key)


class DailyEventContentTests(unittest.TestCase):
    """宫人小事件、孩子小事件：字段只能用 *_event_choose 认得的，占位符只能用 view 里给的"""
    MAID_FIELDS = {'text', 'say', 'silver', 'loyalty', 'loyalty2', 'virtue', 'appearance', 'seek', 'affinity', 'hide', 'gossip'}
    HEIR_FIELDS = {'text', 'say', 'silver', 'mother_health', 'study', 'riding', 'virtue', 'favor', 'affinity',
                   'conceal', 'to_mother_affinity', 'target_affinity'}

    def check(self, events, fields, names):
        for key, ev in events.items():
            ev['text'].format(**names)
            for o in ev['opts']:
                self.assertLessEqual(set(o), fields, key)
                o['text'].format(**names); o['say'].format(**names)
                if o.get('affinity') and fields is self.MAID_FIELDS:
                    self.assertTrue(ev.get('needs_target'), key)
                if o.get('target_affinity'):
                    self.assertTrue(ev.get('needs_target'), key)

    def test_maid_events(self):
        self.check(game.MAID_EVENTS, self.MAID_FIELDS, dict(m='春桃', m2='秋菊', t='华妃'))

    def test_heir_events(self):
        self.check(game.HEIR_EVENTS, self.HEIR_FIELDS, dict(h='大阿哥', t='华妃'))


class ScenePickTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    tearDown = test_lifecycle.LifecycleTests.tearDown
    player = test_lifecycle.LifecycleTests.player
    login = test_lifecycle.LifecycleTests.login

    def test_npc_scene_needs_npc_present(self):
        # setUp 把 NPC 全送进了冷宫：要 NPC 在场的一个都不出，只剩不挑人的
        for _ in range(30):
            self.assertIsNone(game.pick_scene(game.NPC_SCENES))
        self.assertIn(game.pick_scene(game.EMPEROR_SCENES), game.EMPEROR_SCENES)
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='duanfei'")
        for _ in range(10):
            self.assertEqual(game.pick_scene(game.NPC_SCENES), 'yanqing_duanfei')

    def test_npc_affinity_effect(self):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='duanfei'")
        duan = game.q("SELECT * FROM consorts WHERE npc_key='duanfei'", one=True)
        game.start_scene(self.atk, 'yanqing_duanfei')
        game.run('UPDATE consorts SET virtue=90 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'randint', return_value=40):
            body = self.client.post('/scene', data={'opt': 1}).get_data(as_text=True)
        self.assertIn('待你和气了些', body)
        self.assertEqual(game.relation(self.atk, duan['id'])['affinity'], 10)
        self.assertEqual(game.get_consort(self.atk)['trust'], game.get_consort(self.tgt)['trust'])   # 不碰皇上的信任

    def test_scheme_effect_named(self):
        self.assertEqual(game.apply_effects(self.atk, dict(scheme=2)), '心计 +2')

    def test_greet_can_start_new_scenes(self):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='xinchangzai'")
        with patch.object(game.random, 'random', return_value=0.1), \
             patch.object(game.random, 'choice', side_effect=lambda seq: seq[-1]):
            self.client.post('/act/greet')
        sc = game.get_scene(game.get_consort(self.atk))
        self.assertEqual(sc and sc['key'], 'jingren_xinchangzai')


class HeirEventStatTests(unittest.TestCase):
    setUp = test_lifecycle.LifecycleTests.setUp
    tearDown = test_lifecycle.LifecycleTests.tearDown
    player = test_lifecycle.LifecycleTests.player
    login = test_lifecycle.LifecycleTests.login

    def test_riding_event_raises_riding(self):
        import test_heirs
        hid = test_heirs.HeirTests.heir(self, self.atk)
        before = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        game.run('UPDATE consorts SET heir_event=? WHERE id=?',
                 (game.json.dumps(dict(key='riding', heir=hid, day=game.cur_day())), self.atk))
        self.client.post('/heirs/event', data={'opt': 0})
        after = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertEqual(after['riding'], before['riding'] + 3)
        self.assertEqual(game.get_consort(self.atk)['silver'], 2000 - 12)


class ExamContentTests(unittest.TestCase):
    def test_exam_format(self):
        for i, p in enumerate(game.EXAM_PROMPTS):
            p['ask'].format(h='大阿哥')
            self.assertEqual(len(p['opts']), 2, i)
            for o in p['opts']:
                self.assertIn(o['stat'], game.HEIR_CHECK_NAMES, i)
                self.assertLessEqual(set(o['win']) | set(o['lose']), {'heir_favor'}, i)
                self.assertTrue(o['win_text'] and o['lose_text'], i)
            blob = p['ask'] + ''.join(o['text'] + o['win_text'] + o['lose_text'] for o in p['opts'])
            for word in ('兄弟', '男儿'):   # 公主也会被考校
                self.assertNotIn(word, blob, i)


if __name__ == '__main__':
    unittest.main()
