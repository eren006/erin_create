"""玩法说明页：不用登录、数字从游戏常量读出来、链接都在

运行：python3 -m unittest discover -s tests -v
"""
import re
import unittest
import test_lifecycle as fixtures

game = fixtures.game


class HelpTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def page(self, client=None):
        r = (client or self.client).get('/help')
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_help_needs_no_login(self):
        anon = game.app.test_client()
        self.assertIn('玩法说明', self.page(anon))

    def test_every_section_in_the_toc_exists(self):
        page = self.page()
        anchors = re.findall(r'href="#(\w+)"', page)
        self.assertGreaterEqual(len(anchors), 9)
        for a in anchors:
            self.assertIn(f'id="{a}"', page, a)

    def test_numbers_come_from_the_game(self):
        page = self.page()
        for r in range(1, 10):
            self.assertIn(game.RANK_NAMES[r], page)
        self.assertIn(f"{game.STIPEND[8]} 两", page)
        self.assertIn(f"圣宠 {game.PROMOTE_FAVOR[8]}，德行 {game.PROMOTE_VIRTUE[8]}", page)
        self.assertIn(f"精力每天 {game.ENERGY_MAX} 点", page)
        self.assertIn(f"每一届最多送 {game.FAMILY_MAX_MEMBERS} 位", page)
        self.assertIn('23:00', page)
        from unittest.mock import patch
        with patch.object(game, 'BED_COUNT_WEIGHTS', ((1, 0.3), (2, 0.5), (3, 0.2))):      # 测试默认压成固定 2 位，这里换回正式分布
            page = self.page()
        for part in ('30% 翻 1 位', '50% 翻 2 位', '20% 翻 3 位'): self.assertIn(part, page)

    def test_numbers_follow_when_the_game_changes(self):
        from unittest.mock import patch
        with patch.dict(game.STIPEND, {8: 999}), patch.object(game, 'ENERGY_MAX', 9):
            page = self.page()
        self.assertIn('999 两', page)
        self.assertIn('精力每天 9 点', page)

    def test_action_intrigue_diet_and_venture_tables_are_listed(self):
        page = self.page()
        for a in game.ACTIONS.values():
            if a['name'] in ('去养心殿侍疾', '去寿康宫请安'): continue
            self.assertIn(a['name'], page, a['name'])
        for i in game.INTRIGUES.values():
            self.assertIn(i['name'], page)
        for d in game.DIETS.values():
            self.assertIn(d['name'], page)
        for v in game.VENTURES.values():
            self.assertIn(v['name'], page)

    def test_diet_cost_column_matches_the_rule(self):
        page = self.page()
        self.assertIn(f"{game.diet_cost(5, 'normal')} 两", page)
        self.assertIn('例银的 40%', page)
        self.assertIn('例银的 100%', page)
        self.assertIn('例银的 16%', page)

    def test_footer_and_register_link_to_it(self):
        anon = game.app.test_client()
        self.assertIn('href="/help"', anon.get('/login').get_data(as_text=True))
        self.assertIn('先看看玩法说明', anon.get('/register').get_data(as_text=True))
        self.assertIn('href="/help"', self.client.get('/clans').get_data(as_text=True))

    def test_no_template_leftovers(self):
        page = self.page()
        body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', page, flags=re.S)
        for bad in ('{{', '}}', '{%', 'None', 'Undefined'):
            self.assertNotIn(bad, body, bad)

    def test_new_player_gets_pointed_at_the_help_page(self):
        import test_family
        fam = test_family.FamilyTests
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', ('新', 'x')).lastrowid
        with self.client.session_transaction() as sess: sess['uid'] = uid
        game.create_family(uid, '江', 'dali')
        self.client.post('/create', data=dict(given='云', age=20, personality='gentle', **{k: 0 for k in game.STAT_KEYS}))
        cid = game.q("SELECT id FROM consorts WHERE user_id=?", (uid,), one=True)['id']
        from unittest.mock import patch
        with patch.object(game.random, 'randint', return_value=0):
            self.client.post('/dianxuan', data={q['key']: 0 for q in game.dianxuan_questions_for(cid)})
        texts = [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]
        self.assertTrue(any('玩法说明' in t for t in texts))


if __name__ == '__main__':
    unittest.main()


class PacingRescaleHelpTests(unittest.TestCase):
    """30 天活动、一届约 13 天的压缩之后，帮助页和其他模板里手写的天数不该还停在旧数字上"""
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_help_page_reign_and_interval_numbers_are_live(self):
        page = game.app.test_client().get('/help').get_data(as_text=True)
        self.assertIn("皇帝、妃子、孩子同步增长", page)
        self.assertIn(f"一届固定 {game.MAX_REIGN_DAYS} 天", page)
        self.assertIn(f"每 {game.CROWN_INTERVAL} 天一次", page)
        self.assertIn(f"万寿节</b>每 {game.BIRTHDAY_INTERVAL} 天", page)
        self.assertIn(f"每 {game.HEIR_EXAM_INTERVAL} 天考校", page)
        self.assertIn(f"{game.STANCE_LOCK_DAYS} 天内不能改", page)
        self.assertNotIn('60 岁起', page)
        self.assertNotIn('最晚第 70 天', page)

    def test_create_page_dowager_and_concubine_text_is_live(self):
        uid = game.run("INSERT INTO users(username,password_hash,created_ts) VALUES('新家',?,0)", ('x',)).lastrowid
        game.create_family(uid, '沈', 'dali')
        prev = game.run("""INSERT INTO consorts(surname,given,rank,status,entered_day,rank_since_day,family,personality,silver,age_months,recap_seen_day,archived_user_id,death_day,death_reason,reign_no)
                           VALUES('沈','云',5,'dead',1,1,'dali','gentle',0,240,9,?,5,'先帝驾崩，圣母皇太后',1)""", (uid,)).lastrowid
        game.run('UPDATE game_state SET reign_no=2')
        with game.app.test_client() as c:
            with c.session_transaction() as sess: sess['uid'] = uid
            page = c.get('/create').get_data(as_text=True)
        self.assertIn(f"太后每 {game.DOWAGER_AUDIENCE_INTERVAL} 天召你", page)

    def test_heirs_page_mongol_text_is_live(self):
        game.run("""INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,marriage,favor)
                     VALUES(?,?,'公主',1,1,'choice',70)""", (self.atk, self.atk))
        game.run('UPDATE consorts SET trust=60 WHERE id=?', (self.atk,))
        page = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn(f"每 {game.MONGOL_LETTER_INTERVAL} 天收到家书", page)

    def test_succession_page_counsel_text_is_live(self):
        page = self.client.get('/succession').get_data(as_text=True)
        self.assertIn(f"每位公主 {game.COUNSEL_INTERVAL} 天一次", page)
