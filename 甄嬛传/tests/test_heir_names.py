"""字辈与起名库：皇上点三个字，母亲三选一"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HeirNameTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def birth(self, gender='皇子'):
        game.run("UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?", (self.atk,))
        with patch.object(game.time, 'time', return_value=186400), patch.object(game, 'TWIN_CHANCE', 0), \
             patch.object(game.random, 'choice', side_effect=lambda seq: gender if seq == ['皇子', '公主'] else seq[0]):
            game.resolve_births(10, False)
        return game.q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id DESC", (self.atk,), one=True)

    def test_library_never_contains_a_generation_word_or_duplicates(self):
        import ast, pathlib
        gens = {w for ws in game.NAME_GENERATIONS.values() for w in ws}
        for g, chars in game.NAME_CHARS.items():
            self.assertFalse(gens & set(chars), f'{g}的名字库里不能有字辈')
        self.assertFalse(set(game.NAME_CHARS['皇子']) & set(game.NAME_CHARS['公主']), '儿子和女儿的字库不重叠')
        # dict 字面量里重复的键会被悄悄吞掉，按源码数一遍键
        src = pathlib.Path(game.__file__).read_text(encoding='utf-8')
        node = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'NAME_CHARS')
        for gender, d in zip(node.value.keys, node.value.values):
            keys = [k.value for k in d.keys]
            self.assertEqual(len(keys), len(set(keys)), f'{gender.value}的名字库有重复的字')

    def test_choices_never_offer_a_generation_word(self):
        gens = {w for ws in game.NAME_GENERATIONS.values() for w in ws}
        for gender in ('皇子', '公主'):
            for _ in range(60):
                self.assertFalse(gens & set(game.roll_name_choices(dict(gender=gender, gen_word=game.gen_word_for(1, gender)))))

    def test_library_is_big_enough_and_every_char_has_meaning(self):
        for g, chars in game.NAME_CHARS.items():
            self.assertGreaterEqual(len(chars), 100)
            self.assertTrue(all(len(k) == 1 and v for k, v in chars.items()))

    def test_birth_sets_generation_word_and_three_distinct_choices(self):
        h = self.birth()
        self.assertEqual(h['gen_word'], game.gen_word_for(game.state()['reign_no'], '皇子'))
        self.assertEqual(len(h['name_choices']), 3)
        self.assertEqual(len(set(h['name_choices'])), 3)
        self.assertTrue(all(ch in game.NAME_CHARS['皇子'] for ch in h['name_choices']))
        self.assertEqual(h['name'], '')

    def test_sons_and_daughters_have_different_generation_words(self):
        self.assertNotEqual(game.gen_word_for(1, '皇子'), game.gen_word_for(1, '公主'))
        for r in range(1, 20):
            self.assertNotIn(game.gen_word_for(r, '皇子'), game.NAME_GENERATIONS['公主'])
            self.assertNotIn(game.gen_word_for(r, '皇子'), game.NAME_CHARS['皇子'])
            self.assertNotIn(game.gen_word_for(r, '公主'), game.NAME_CHARS['公主'])
        h = self.birth('公主')
        self.assertEqual(h['gen_word'], game.gen_word_for(game.state()['reign_no'], '公主'))

    def test_princess_chars_come_from_the_princess_pool(self):
        h = self.birth('公主')
        self.assertTrue(all(ch in game.NAME_CHARS['公主'] for ch in h['name_choices']))

    def test_mother_picks_one_and_name_is_generation_plus_char(self):
        h = self.birth()
        pick = h['name_choices'][1]
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': pick})
        after = game.get_heir(h['id'])
        self.assertEqual(after['name'], h['gen_word'] + pick)
        self.assertEqual(after['name_choices'], '')

    def test_cannot_pick_a_char_outside_the_three_or_rename(self):
        h = self.birth()
        outside = next(ch for ch in game.NAME_CHARS['皇子'] if ch not in h['name_choices'])
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': outside})
        self.assertEqual(game.get_heir(h['id'])['name'], '')
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': h['name_choices'][0]})
        first = game.get_heir(h['id'])['name']
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': h['name_choices'][1]})
        self.assertEqual(game.get_heir(h['id'])['name'], first)

    def test_other_mothers_cannot_name_my_child(self):
        h = self.birth()
        other = self.player('丙')
        self.login(other)
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': h['name_choices'][0]})
        self.assertEqual(game.get_heir(h['id'])['name'], '')

    def test_caretaker_sets_nickname_shown_in_brackets(self):
        h = self.birth()
        self.client.post(f"/heirs/{h['id']}/nickname", data={'nickname': ' 团团 '})
        self.assertEqual(game.get_heir(h['id'])['nickname'], '团团')
        self.assertEqual(game.heir_label(game.get_heir(h['id'])), '大阿哥（团团）')
        self.assertIn('（团团）', self.client.get('/heirs').get_data(as_text=True))
        self.client.post(f"/heirs/{h['id']}/nickname", data={'nickname': ''})
        self.assertEqual(game.get_heir(h['id'])['nickname'], '')

    def test_nickname_too_long_or_not_caretaker_rejected(self):
        h = self.birth()
        self.client.post(f"/heirs/{h['id']}/nickname", data={'nickname': '一二三四五'})
        self.assertEqual(game.get_heir(h['id'])['nickname'], '')
        game.run("UPDATE heirs SET caretaker_id=0 WHERE id=?", (h['id'],))
        self.client.post(f"/heirs/{h['id']}/nickname", data={'nickname': '团团'})
        self.assertEqual(game.get_heir(h['id'])['nickname'], '')
        game.run("UPDATE heirs SET caretaker_id=? WHERE id=?", (self.atk, h['id']))
        other = self.player('丙'); self.login(other)
        self.client.post(f"/heirs/{h['id']}/nickname", data={'nickname': '团团'})
        self.assertEqual(game.get_heir(h['id'])['nickname'], '')

    def test_used_chars_are_not_offered_again_within_a_generation(self):
        h = self.birth()
        pick = h['name_choices'][0]
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': pick})
        for _ in range(30):
            nxt = dict(gender='皇子', gen_word=h['gen_word'])
            self.assertNotIn(pick, game.roll_name_choices(nxt))

    def test_old_unnamed_heirs_get_choices_when_mother_opens_page(self):
        h = self.birth()
        game.run("UPDATE heirs SET name_choices='', gen_word='' WHERE id=?", (h['id'],))
        self.client.get('/heirs')
        after = game.get_heir(h['id'])
        self.assertEqual(len(after['name_choices']), 3)
        self.assertTrue(after['gen_word'])

    def test_heirs_page_shows_choices_with_meanings(self):
        h = self.birth()
        html = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('字辈', html)
        self.assertIn(h['gen_word'] + h['name_choices'][0], html)
        self.assertIn(game.NAME_CHARS['皇子'][h['name_choices'][0]], html)

    def test_twins_each_get_their_own_choices(self):
        game.TWIN_CHANCE = 1
        game.run("UPDATE consorts SET pregnant_since=10,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?", (self.atk,))
        with patch.object(game.time, 'time', return_value=186400):
            game.resolve_births(10, False)
        kids = game.q("SELECT * FROM heirs WHERE mother_id=?", (self.atk,))
        self.assertEqual(len(kids), 2)
        self.assertTrue(all(len(k['name_choices']) == 3 for k in kids))

    def test_home_reminds_mother_until_she_names_the_child(self):
        h = self.birth()
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (self.atk,))
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('还没有名字', html)
        self.assertIn('去子嗣页取名', html)
        self.client.post('/heirs', data={'heir_id': h['id'], 'pick': h['name_choices'][0]})
        html = self.client.get('/').get_data(as_text=True)
        self.assertNotIn('还没有名字', html)

    def test_home_has_no_reminder_for_other_players(self):
        self.birth()
        other = self.player('丙')
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (other,))
        self.login(other)
        self.assertNotIn('还没有名字', self.client.get('/').get_data(as_text=True))

    def test_first_prince_is_da_ahge_then_er_and_princess_counts_separately(self):
        h1 = self.birth('皇子')
        self.assertEqual(game.heir_label(dict(h1, name='')), '大阿哥')
        self.assertEqual(h1['ordinal'], 1)
        h2 = self.birth('皇子')
        self.assertEqual((h2['ordinal'], game.heir_label(dict(h2, name=''))), (2, '二阿哥'))
        h3 = self.birth('公主')
        self.assertEqual((h3['ordinal'], game.heir_label(dict(h3, name=''))), (1, '大公主'))
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%诞下大阿哥%'", one=True))

    def test_numbering_restarts_in_a_new_reign(self):
        self.birth('皇子')
        game.run('UPDATE game_state SET reign_start_day=?', (game.cur_day() + 1,))     # 下一届开始，旧皇嗣不再占排行
        h = self.birth('皇子')
        self.assertEqual(h['ordinal'], 1)


if __name__ == '__main__':
    unittest.main()
