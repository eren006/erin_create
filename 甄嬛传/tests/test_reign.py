"""皇上的寿数、病重、驾崩开匾、换届、下一届开局，见设计文档九点六节 G

运行：python3 -m unittest discover -s tests -v
"""
import json
import sqlite3
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class ReignTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def st(self):
        return game.state()

    def login_uid(self, uid):
        """换届后角色的 user_id 已清空，只能按账号登录"""
        with self.client.session_transaction() as sess:
            sess['uid'] = uid

    def uid_of(self, cid):
        c = game.get_consort(cid)
        return c['user_id'] or c['archived_user_id']

    def set_day(self, day):
        game.run('UPDATE game_state SET day=?', (day,))

    def prince(self, mother, age_years=13, **kw):
        kw.setdefault('title', '')
        return self.heir(mother, gender='皇子', born=game.cur_day() - age_years * 2, zhuazhou='book', **kw)

    def row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def gaz(self):
        return [r['text'] for r in game.q('SELECT text FROM gazette')]

    def start_illness(self, day=None):
        day = day or game.cur_day()
        game.fall_emperor_ill(day - 1, day + game.ILL_DAYS - 1)   # 昨晚定下的：从今天起病重三天

    def reign_row(self):
        return game.q('SELECT * FROM reigns ORDER BY id DESC', one=True)

    # ── 寿数与病重 ───────────────────────────────────────────────────────────

    def test_default_reign_state(self):
        st = self.st()
        self.assertEqual((st['reign_no'], st['emperor_start_age'], st['emperor_death_day'], st['mourning']), (1, 45, 0, 0))
        self.set_day(11)
        self.assertEqual(game.emperor_age_years(), 50)   # 每晚半岁

    def test_no_death_risk_before_sixty(self):
        self.set_day(31)   # 45 + 15 = 60 岁整，还没有风险
        with patch.object(game.random, 'random', return_value=0.0):
            self.assertFalse(game.emperor_tick(31))
        self.assertEqual(self.st()['emperor_death_day'], 0)

    def test_hazard_grows_with_age_after_sixty(self):
        self.set_day(41)   # 65 岁：风险 (65-60) × 0.5% = 2.5%
        with patch.object(game.random, 'random', return_value=0.02):
            game.emperor_tick(41)
        self.assertEqual(self.st()['emperor_death_day'], 44, '掷中后 3 天驾崩')
        game.run('UPDATE game_state SET emperor_death_day=0')
        with patch.object(game.random, 'random', return_value=0.03):
            game.emperor_tick(41)
        self.assertEqual(self.st()['emperor_death_day'], 0)

    def test_forced_before_max_reign_days(self):
        d = 1 + game.MAX_REIGN_DAYS - game.ILL_DAYS   # 第 67 天
        self.set_day(d)
        with patch.object(game.random, 'random', return_value=0.999):
            game.emperor_tick(d)
        self.assertEqual(self.st()['emperor_death_day'], 1 + game.MAX_REIGN_DAYS)

    def test_ill_window_is_three_days_ending_on_death_day(self):
        game.run('UPDATE game_state SET emperor_death_day=20')
        flags = {d: game.emperor_ill(day=d) for d in (16, 17, 18, 19, 20)}
        self.assertEqual(flags, {16: False, 17: False, 18: True, 19: True, 20: True})

    def test_illness_notifies_players_and_posts_gazette(self):
        self.start_illness()
        self.assertTrue(any('病重' in m for m in self.msgs(self.atk)))
        self.assertTrue(any('龙体违和' in t for t in self.gaz()))

    def test_ill_emperor_stops_bed_and_audience(self):
        game.run('UPDATE game_state SET emperor_death_day=? ', (game.cur_day() + 2,))   # 今天已在病重的三天里
        self.assertTrue(game.emperor_ill())
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(game.q('SELECT SUM(bedded_count) n FROM consorts', one=True)['n'], 0)
        self.assertFalse(any('翻了' in t or '召见' in t for t in self.gaz()))

    def test_healthy_emperor_still_beds_someone(self):
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(game.q('SELECT SUM(bedded_count) n FROM consorts', one=True)['n'], 1)

    # ── 侍疾 ─────────────────────────────────────────────────────────────────

    def test_attend_only_when_ill_and_helps_princes(self):
        hid = self.prince(self.atk, favor=5)
        game.run('UPDATE consorts SET trust=10 WHERE id=?', (self.atk,))
        self.client.post('/act/attend')
        self.assertEqual(game.get_consort(self.atk)['trust'], 10, '皇上没病，侍不了疾')
        self.start_illness()
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/act/attend')
        self.assertEqual(game.get_consort(self.atk)['trust'], 10 + game.ATTEND_TRUST_GAIN)
        self.assertEqual(self.row(hid)['favor'], 5 + game.ATTEND_HEIR_GAIN)

    def test_attend_can_fail_without_penalty(self):
        self.start_illness()
        game.run('UPDATE consorts SET trust=10 WHERE id=?', (self.atk,))
        with patch.object(game.random, 'random', return_value=0.999):
            self.client.post('/act/attend')
        self.assertEqual(game.get_consort(self.atk)['trust'], 10)

    def test_seek_blocked_while_ill(self):
        self.start_illness()
        silver = game.get_consort(self.atk)['silver']
        self.client.post('/act/seek')
        self.assertEqual(game.get_consort(self.atk)['silver'], silver)

    def test_attend_button_only_shows_when_ill(self):
        self.assertNotIn('侍疾', self.client.get('/place/yangxin').get_data(as_text=True))
        self.start_illness()
        self.assertIn('侍疾', self.client.get('/place/yangxin').get_data(as_text=True))

    # ── 开匾 ─────────────────────────────────────────────────────────────────

    def test_highest_standing_takes_the_plaque(self):
        game.run('UPDATE consorts SET rank=1, trust=0')
        a = self.prince(self.atk, favor=90)
        b = self.prince(self.tgt, favor=30)
        self.assertEqual(game.choose_successor(game.cur_day())['id'], a, '测试夹具让胜面最大的赢')
        self.assertEqual(game.succession_favorite(game.cur_day())[0]['id'], a)

    # ── 开匾抽签 ─────────────────────────────────────────────────────────────

    def two_princes(self, fa, fb, **kw):
        game.run('UPDATE consorts SET rank=1, trust=0')
        a = self.prince(self.atk, favor=fa, study=0, riding=0, virtue=0, **kw)
        b = self.prince(self.tgt, favor=fb, study=0, riding=0, virtue=0)
        return a, b

    def test_odds_follow_standing_squared(self):
        a, b = self.two_princes(100, 50)
        odds = {h['id']: p for h, p in game.succession_odds(game.cur_day())}
        self.assertAlmostEqual(odds[a], 0.8)
        self.assertAlmostEqual(odds[b], 0.2)
        self.assertAlmostEqual(sum(odds.values()), 1.0)

    def test_crown_prince_has_a_weight_bonus(self):
        a, b = self.two_princes(50, 50)
        game.run("UPDATE heirs SET status='crown' WHERE id=?", (a,))
        odds = {h['id']: p for h, p in game.succession_odds(game.cur_day())}
        self.assertAlmostEqual(odds[a], 1.3 / 2.3)

    def test_weak_prince_can_still_win_the_lottery(self):
        import random as _r
        a, b = self.two_princes(100, 50)
        odds = game.succession_odds(game.cur_day())
        rng = _r.Random(7)
        wins = sum(1 for _ in range(4000) if rng.choices([h['id'] for h, _ in odds], weights=[p for _, p in odds])[0] == b)
        self.assertTrue(0.16 < wins / 4000 < 0.24, wins)

    def test_choose_successor_draws_with_the_odds_as_weights(self):
        a, b = self.two_princes(100, 50)
        seen = {}
        def spy(items, weights):
            seen.update(zip([h['id'] for h in items], weights))
            return items[1]
        with patch.object(game, 'pick_weighted', spy):
            self.assertEqual(game.choose_successor(game.cur_day())['id'], b, '抽签抽到谁就是谁')
        self.assertAlmostEqual(seen[a], 0.8)

    def test_forgery_makes_the_odds_certain(self):
        a, b = self.two_princes(100, 1)
        game.run('UPDATE heirs SET forged=1 WHERE id=?', (b,))
        odds = {h['id']: p for h, p in game.succession_odds(game.cur_day())}
        self.assertEqual((odds[a], odds[b]), (0.0, 1.0))

    def test_no_princes_no_odds(self):
        self.assertEqual(game.succession_odds(game.cur_day()), [])
        self.assertEqual(game.succession_favorite(game.cur_day()), (None, 0.0))

    def test_peek_reports_the_chance_not_a_certainty(self):
        self.two_princes(100, 50)
        game.run('UPDATE consorts SET rank=5 WHERE id=?', (self.atk,))   # 窥匾要嫔位以上
        chance = round(game.succession_favorite(game.cur_day())[1] * 100)
        self.assertGreater(chance, 70)
        with patch.object(game.random, 'random', return_value=0.0):
            r = self.client.post('/succession/move', data=dict(move='peek'), follow_redirects=True)
        page = r.get_data(as_text=True)
        self.assertIn(f'胜面约 {chance}%', page)
        self.assertIn('圣意难测', page)

    def test_forged_prince_beats_higher_standing(self):
        game.run('UPDATE consorts SET rank=1, trust=0')
        a = self.prince(self.atk, favor=90)
        b = self.prince(self.tgt, favor=30, forged=1)
        self.assertEqual(game.choose_successor(game.cur_day())['id'], b)

    def test_no_eligible_prince_means_adoption(self):
        self.prince(self.atk, age_years=11, favor=99)
        self.prince(self.atk, age_years=14, favor=99, status='deposed')
        self.assertIsNone(game.choose_successor(game.cur_day()))

    def test_peek_reveals_current_leader_sometimes(self):
        a = self.prince(self.tgt, favor=90)
        silver = game.get_consort(self.atk)['silver']
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/succession/move', data=dict(move='peek'))
        self.assertEqual(game.get_consort(self.atk)['silver'], silver - game.SUCCESSION_MOVES['peek']['silver'])
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_peek_can_land_you_in_the_cold_palace(self):
        with patch.object(game.random, 'random', return_value=game.PEEK_LEARN + 0.01):
            self.client.post('/succession/move', data=dict(move='peek'))
        self.assertEqual(game.get_consort(self.atk)['status'], 'cold')

    def test_peek_needs_pin_rank(self):
        low = self.player('丙', rank=4)
        self.login(low)
        self.client.post('/succession/move', data=dict(move='peek'))
        self.assertEqual(game.get_consort(low)['silver'], 2000)

    def make_boss(self, rank=7, scheme=100, name='丙'):
        boss = self.player(name, rank=rank)
        game.run('UPDATE consorts SET scheme=? WHERE id=?', (scheme, boss))
        self.login(boss)
        return boss

    def test_forge_success_marks_prince_and_uses_the_one_attempt(self):
        boss = self.make_boss()
        hid = self.prince(boss, favor=1)
        self.start_illness()
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/succession/move', data=dict(move='forge', target_id=hid))
        self.assertEqual(self.row(hid)['forged'], 1)
        uid = game.get_consort(boss)['user_id']
        self.assertEqual(game.q('SELECT forge_used FROM users WHERE id=?', (uid,), one=True)['forge_used'], 1)
        silver = game.get_consort(boss)['silver']
        self.client.post('/succession/move', data=dict(move='forge', target_id=hid))
        self.assertEqual(game.get_consort(boss)['silver'], silver, '一辈子只能试一次')

    def test_forge_failure_is_fatal(self):
        boss = self.make_boss()
        hid = self.prince(boss)
        self.start_illness()
        with patch.object(game.random, 'random', return_value=0.99):
            self.client.post('/succession/move', data=dict(move='forge', target_id=hid))
        self.assertEqual(game.get_consort(boss)['status'], 'dead')
        self.assertEqual(self.row(hid)['forged'], 0)

    def test_forge_needs_illness_rank_and_own_child(self):
        boss = self.make_boss()
        mine = self.prince(boss)
        theirs = self.prince(self.tgt)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/succession/move', data=dict(move='forge', target_id=mine))   # 皇上没病
            self.assertEqual(self.row(mine)['forged'], 0)
            self.start_illness()
            self.client.post('/succession/move', data=dict(move='forge', target_id=theirs))   # 别人的孩子
            self.assertEqual(self.row(theirs)['forged'], 0)
        low = self.make_boss(rank=6, name='丁')   # 妃，不够格
        kid = self.prince(low)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/succession/move', data=dict(move='forge', target_id=kid))
        self.assertEqual(self.row(kid)['forged'], 0)

    # ── 换届 ─────────────────────────────────────────────────────────────────

    def scene(self):
        """甲生母、乙养母，阿哥圣眷最高；丙明站他，丁明站别人，戊暗站他"""
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        self.hid = self.prince(self.atk, caretaker=self.tgt, favor=90, mother_affinity=30, caretaker_affinity=70, name='承稷')
        self.rival = self.prince(self.atk, favor=10, ambition=90, adult_day=1, title='贝勒', faction=6)
        self.fan = self.player('丙', rank=4)
        self.foe = self.player('丁', rank=4)
        self.spy = self.player('戊', rank=4)
        day = game.cur_day()
        for cid, kind, hid, since in ((self.fan, 'open', self.hid, day - 13), (self.foe, 'open', self.rival, day - 8),
                                      (self.spy, 'secret', self.hid, day - 8)):
            game.run('INSERT INTO stances(consort_id,kind,heir_id,since_day) VALUES(?,?,?,?)', (cid, kind, hid, since))

    def test_end_reign_records_edict_and_fates(self):
        self.scene()
        game.end_reign(game.cur_day())
        r = self.reign_row()
        self.assertEqual((r['reign_no'], r['end_day']), (1, 10))
        self.assertEqual(r['successor'], '承稷')
        edict = json.loads(r['edict'])
        self.assertIn('传位于承稷', edict[0])
        self.assertTrue(any('圣母皇太后' in l for l in edict), '养母情分高，成太后')
        self.assertTrue(any('太妃' in l for l in edict), '生母封太妃')
        fates = {f['name'].split('·')[-1]: f['fate'] for f in json.loads(r['fates'])}
        by_cid = {f['cid']: f['fate'] for f in json.loads(r['fates'])}
        self.assertEqual(by_cid[self.tgt], '圣母皇太后')
        self.assertEqual(by_cid[self.atk], '太妃')
        self.assertEqual(by_cid[self.fan], '皇贵太妃', '明站 13 天')
        self.assertIn('押错', by_cid[self.foe])
        self.assertIn('暗中相助', by_cid[self.spy])
        self.assertTrue(any('圈禁' in l for l in edict), '野心 90、党羽多的落选皇子被圈禁')

    def test_support_title_by_days(self):
        self.assertEqual([game.support_title(d) for d in (0, 5, 6, 11, 12, 30)], ['太妃', '太妃', '贵太妃', '贵太妃', '皇贵太妃', '皇贵太妃'])

    def test_mother_becomes_dowager_when_child_closer_to_her(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        self.prince(self.atk, caretaker=self.tgt, favor=90, mother_affinity=80, caretaker_affinity=20)
        game.end_reign(game.cur_day())
        by_cid = {f['cid']: f['fate'] for f in json.loads(self.reign_row()['fates'])}
        self.assertEqual((by_cid[self.atk], by_cid[self.tgt]), ('圣母皇太后', '太妃'))
        self.assertIn(game.full_name(game.get_consort(self.atk)), self.st()['dowager'])

    def test_dead_parent_cannot_be_dowager(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        self.prince(self.atk, caretaker=self.tgt, favor=90, mother_affinity=90, caretaker_affinity=10)
        game.run("UPDATE consorts SET status='dead', death_day=5, death_reason='病逝', archived_user_id=user_id WHERE id=?", (self.atk,))
        game.end_reign(game.cur_day())
        by_cid = {f['cid']: f['fate'] for f in json.loads(self.reign_row()['fates'])}
        self.assertEqual(by_cid[self.tgt], '圣母皇太后')
        self.assertIn('病逝', by_cid[self.atk])

    def test_adoption_when_no_prince_of_age(self):
        game.end_reign(game.cur_day())
        r = self.reign_row()
        self.assertIn('自宗室过继', json.loads(r['edict'])[0])
        self.assertEqual(r['dowager'], '')
        self.assertEqual(self.st()['dowager'], '')
        self.assertTrue(self.st()['emperor_name'])

    def test_end_reign_archives_players_and_resets_world(self):
        self.scene()
        game.run("INSERT INTO letters(from_id,to_id,day,body,created_ts) VALUES(?,?,?,?,?)", (self.atk, self.tgt, 5, '姐姐安好', 0))
        game.run("INSERT INTO inventory(consort_id,item_key,qty) VALUES(?,?,1)", (self.atk, 'qinpu'))
        uid = game.get_consort(self.atk)['user_id']
        game.end_reign(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual((c['status'], c['user_id'], c['archived_user_id']), ('dead', None, uid))
        self.assertIn('先帝驾崩', c['death_reason'])
        for t in ('letters', 'inventory', 'stances', 'messages'):
            self.assertEqual(game.q(f'SELECT COUNT(*) n FROM {t}', one=True)['n'], 0, t)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM users', one=True)['n'], 5, '账号保留')
        mine = game.q('SELECT * FROM reign_letters WHERE user_id=?', (uid,))
        self.assertEqual([m['body'] for m in mine], ['姐姐安好'])
        self.assertEqual(mine[0]['from_name'], '甲妃', '存档时用的是当时的称呼')

    def test_end_reign_installs_next_reign(self):
        self.scene()
        day = game.cur_day()
        game.end_reign(day)
        st = self.st()
        self.assertEqual((st['reign_no'], st['day'], st['reign_start_day'], st['emperor_start_age'], st['mourning'], st['emperor_death_day']),
                         (2, day + 1, day + 2, 40, 1, 0))
        self.assertEqual(st['emperor_name'], '承稷')
        self.assertTrue(st['era_name'])
        traits = json.loads(st['emperor_traits'])
        self.assertEqual(traits['personality'], 'clever')
        npc = game.q("SELECT * FROM consorts WHERE npc_key='huanghou'", one=True)
        self.assertEqual(npc['surname'], '富察', '第二届换甲套人设')
        self.assertEqual(game.q('SELECT COUNT(*) n FROM consorts WHERE npc_key IS NOT NULL', one=True)['n'], 8)
        heirs = {h['npc_key']: h for h in game.q('SELECT * FROM heirs')}
        self.assertEqual(set(heirs), {'third', 'fourth', 'princess'})
        self.assertEqual(game.heir_age_years(heirs['third'], day + 2), 12)
        self.assertEqual(game.heir_age_years(heirs['fourth'], day + 2), 8)
        self.assertEqual(game.heir_age_years(heirs['princess'], day + 2), 10)
        self.assertEqual(heirs['fourth']['caretaker_id'], 0)
        self.assertEqual(heirs['fourth']['orphan_deadline_day'], day + 2 + game.NPC_ORPHAN_DEADLINE_DAYS)
        self.assertEqual(game.get_consort(heirs['third']['mother_id'])['npc_key'], 'qifei')
        self.assertEqual(game.get_consort(heirs['princess']['mother_id'])['npc_key'], 'caoguiren')
        self.assertTrue(all(h['name'] for h in heirs.values()))

    def test_third_reign_uses_the_other_persona_set(self):
        self.assertEqual([n['surname'] for n in game.npcs_for_reign(1)][:1], ['乌拉那拉'])
        self.assertEqual(game.npcs_for_reign(2)[0]['surname'], '富察')
        self.assertEqual(game.npcs_for_reign(3)[0]['surname'], '马佳')
        self.assertEqual(game.npcs_for_reign(4)[0]['surname'], '富察')
        for no in (2, 3):
            for n in game.npcs_for_reign(no):   # 位分、封号、住处不变，别的代码按这些认人
                base = next(b for b in game.NPCS if b['npc_key'] == n['npc_key'])
                self.assertEqual((n['title'], n['rank'], n['palace'], n['hall']), (base['title'], base['rank'], base['palace'], base['hall']))

    def test_init_db_restart_does_not_duplicate_new_reign_npcs(self):
        self.scene()
        game.end_reign(game.cur_day())
        game.init_db()
        self.assertEqual(game.q('SELECT COUNT(*) n FROM consorts WHERE npc_key IS NOT NULL', one=True)['n'], 8)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs', one=True)['n'], 3)
        self.assertEqual(game.q("SELECT surname FROM consorts WHERE npc_key='huanghou'", one=True)['surname'], '富察')

    def test_xiunv_waiting_for_selection_is_kept(self):
        game.run("UPDATE consorts SET status='xiunv', entered_day=0 WHERE id=?", (self.tgt,))
        game.end_reign(game.cur_day())
        self.assertEqual(game.get_consort(self.tgt)['status'], 'xiunv')

    def test_records_pick_top_players(self):
        game.run('UPDATE consorts SET bedded_count=7 WHERE id=?', (self.tgt,))
        game.run('UPDATE consorts SET rank=8 WHERE id=?', (self.atk,))
        self.heir(self.tgt, gender='皇子')
        game.end_reign(game.cur_day())
        rec = json.loads(self.reign_row()['records'])
        self.assertTrue(any('侍寝最多' in r and '7 次' in r for r in rec))
        self.assertTrue(any('位分最高' in r and '皇贵妃' in r for r in rec))
        self.assertTrue(any('养大皇嗣最多' in r for r in rec))

    def test_events_from_gazette_go_into_the_edict(self):
        game.gazette('圣旨：某某晋为某嫔。', 'decree')
        game.gazette('敬事房：今夜皇上翻了牌子。', 'bed')
        game.end_reign(game.cur_day())
        edict = json.loads(self.reign_row()['edict'])
        self.assertTrue(any('某某晋为某嫔' in l for l in edict))
        self.assertFalse(any('敬事房' in l for l in edict))

    # ── 国丧与下一届 ─────────────────────────────────────────────────────────

    def test_settle_on_death_day_ends_the_reign(self):
        self.scene()
        d = game.cur_day()
        game.run('UPDATE game_state SET emperor_death_day=?', (d,))
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        st = self.st()
        self.assertEqual((st['reign_no'], st['mourning'], st['day']), (2, 1, d + 1))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM reigns', one=True)['n'], 1)

    def test_settle_before_death_day_does_not(self):
        d = game.cur_day()
        game.run('UPDATE game_state SET emperor_death_day=?', (d + 1,))
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(self.st()['reign_no'], 1)

    def test_mourning_blocks_creation_then_next_settle_opens_the_new_reign(self):
        self.scene()
        d = game.cur_day()
        uid = self.uid_of(self.atk)
        game.end_reign(d)
        self.login_uid(uid)
        r = self.client.get('/create')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/reigns', r.headers['Location'])
        with patch.object(game, 'npc_schemes'):
            game.settle_day()   # 国丧这一天的结算，只是收尾
        st = self.st()
        self.assertEqual((st['mourning'], st['day']), (0, d + 2))
        self.assertEqual(st['day'], st['reign_start_day'])
        self.assertEqual(self.client.get('/create').status_code, 200)

    def test_mourning_day_settle_does_nothing_else(self):
        self.scene()
        game.end_reign(game.cur_day())
        heirs_before = [dict(h) for h in game.q('SELECT * FROM heirs ORDER BY id')]
        with patch.object(game, 'npc_schemes') as ns:
            game.settle_day()
        ns.assert_not_called()
        self.assertEqual([dict(h) for h in game.q('SELECT * FROM heirs ORDER BY id')], heirs_before)

    def test_players_without_a_character_can_open_reigns_and_memorial(self):
        self.scene()
        game.run("INSERT INTO letters(from_id,to_id,day,body,created_ts) VALUES(?,?,?,?,?)", (self.tgt, self.atk, 5, '妹妹保重', 0))
        uid, other_uid = self.uid_of(self.atk), None
        game.end_reign(game.cur_day())
        self.login_uid(uid)
        page = self.client.get('/reigns').get_data(as_text=True)
        self.assertIn('传位于承稷', page)
        self.assertIn('圣母皇太后', page)
        self.assertIn('妹妹保重', page, '自己的信留着')
        self.assertIn('（你）', page)
        other = self.player('己', rank=4)
        self.login(other)
        self.assertNotIn('妹妹保重', self.client.get('/reigns').get_data(as_text=True), '别人的信看不到')
        self.assertEqual(self.client.get('/memorial').status_code, 200)

    def test_header_shows_era_and_mourning(self):
        self.scene()
        uid = self.uid_of(self.atk)
        game.end_reign(game.cur_day())
        self.login_uid(uid)
        page = self.client.get('/reigns').get_data(as_text=True)
        self.assertIn('国丧', page)
        self.assertIn(self.st()['era_name'] + '朝', page)

    def test_new_reign_players_start_fresh(self):
        self.scene()
        game.end_reign(game.cur_day())
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        newbie = self.player('庚', rank=1)
        game.run('UPDATE consorts SET entered_day=? WHERE id=?', (self.st()['day'], newbie))
        self.assertEqual(game.reign_players(self.st())[0]['id'], newbie, '上一届的角色不算这一届')

    # ── 新帝的脾气 ───────────────────────────────────────────────────────────

    def set_traits(self, **kw):
        game.run('UPDATE game_state SET emperor_traits=?', (json.dumps(kw),))

    def test_traits_default_to_neutral(self):
        self.assertEqual(game.emperor_traits(), {})
        self.assertEqual(game.promote_virtue_need(5), game.PROMOTE_VIRTUE[5])

    def test_scholar_emperor_prizes_talent(self):
        c = game.get_consort(self.atk)
        base = game.bed_weight(c, 10)
        self.set_traits(study=60)
        self.assertAlmostEqual(game.bed_weight(c, 10), base + c['talent'] * 0.1)

    def test_martial_emperor_prizes_health(self):
        c = game.get_consort(self.atk)
        base = game.bed_weight(c, 10)
        self.set_traits(riding=60)
        self.assertAlmostEqual(game.bed_weight(c, 10), base + c['health'] * 0.2)

    def test_virtuous_emperor_lowers_promotion_virtue_line(self):
        self.set_traits(virtue=60)
        self.assertEqual(game.promote_virtue_need(5), int(game.PROMOTE_VIRTUE[5] * 0.9))
        self.set_traits(virtue=59)
        self.assertEqual(game.promote_virtue_need(5), game.PROMOTE_VIRTUE[5])

    def test_stubborn_emperor_slows_trust_gain_but_not_loss(self):
        game.run('UPDATE consorts SET trust=50 WHERE id=?', (self.atk,))
        self.set_traits(personality='stubborn')
        game.add_trust(self.atk, 10)
        self.assertEqual(game.get_consort(self.atk)['trust'], 57)
        game.add_trust(self.atk, -10)
        self.assertEqual(game.get_consort(self.atk)['trust'], 47)

    def test_clever_emperor_makes_exams_harder(self):
        kid = self.prince(self.atk, age_years=10, study=40, exam_bonus=15)
        game.start_scene(self.atk, 'exam', heir=kid, prompt=0)
        self.set_traits(personality='clever')
        with patch.object(game.random, 'randint', return_value=0):
            self.client.post('/scene', data=dict(opt=1))   # 40 + 15 = 55 ≥ 45，但聪敏皇上 dc +5 = 50，仍然能过
        self.assertGreater(self.row(kid)['favor'], 0)
        kid2 = self.prince(self.atk, age_years=10, study=32, exam_bonus=15)
        game.run('UPDATE consorts SET pending_scene=?', ('',))
        game.start_scene(self.atk, 'exam', heir=kid2, prompt=0)
        with patch.object(game.random, 'randint', return_value=0):
            self.client.post('/scene', data=dict(opt=1))   # 32 + 15 = 47 ≥ 45 但 < 50
        self.assertEqual(self.row(kid2)['favor'], 0)

    # ── 后台 ─────────────────────────────────────────────────────────────────

    def admin(self):
        with self.client.session_transaction() as sess:
            sess['admin'] = True

    def test_admin_start_age_ill_postpone_recover(self):
        self.admin()
        self.client.post('/admin/emperor', data=dict(act='start_age', age='50'))
        self.assertEqual(self.st()['emperor_start_age'], 50)
        self.client.post('/admin/emperor', data=dict(act='start_age', age='5'))
        self.assertEqual(self.st()['emperor_start_age'], 50, '不合理的年龄不收')
        d = game.cur_day()
        self.client.post('/admin/emperor', data=dict(act='ill'))
        self.assertEqual(self.st()['emperor_death_day'], d + game.ILL_DAYS - 1)
        self.assertTrue(game.emperor_ill(), '白天触发，今天起就是病重')
        self.client.post('/admin/emperor', data=dict(act='postpone'))
        self.assertEqual(self.st()['emperor_death_day'], d + game.ILL_DAYS)
        self.client.post('/admin/emperor', data=dict(act='recover'))
        self.assertEqual(self.st()['emperor_death_day'], 0)

    def test_admin_end_now_and_skip_mourning(self):
        self.admin()
        self.client.post('/admin/emperor', data=dict(act='end_now'))
        self.assertEqual((self.st()['reign_no'], self.st()['mourning']), (2, 1))
        d = game.cur_day()
        self.client.post('/admin/emperor', data=dict(act='skip_mourning'))
        self.assertEqual((self.st()['mourning'], self.st()['day']), (0, d + 1))

    def test_admin_page_renders_emperor_panel(self):
        self.admin()
        page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('立即驾崩', page)
        self.assertIn('龙体安康', page)

    def test_admin_reset_goes_back_to_first_reign_and_takes_start_age(self):
        self.scene()
        game.end_reign(game.cur_day())
        self.admin()
        self.client.post('/admin/reset', data={'confirm': '重开', 'keep_users': '1', 'start_age': '52'})
        st = self.st()
        self.assertEqual((st['reign_no'], st['emperor_start_age'], st['mourning']), (1, 52, 0))
        self.assertEqual(game.q('SELECT COUNT(*) n FROM reigns', one=True)['n'], 0)
        self.assertEqual(game.q("SELECT surname FROM consorts WHERE npc_key='huanghou'", one=True)['surname'], '乌拉那拉')
        self.assertEqual({h['npc_key'] for h in game.q('SELECT * FROM heirs')}, {'third', 'fourth'})

    def test_full_playthrough_of_a_reign(self):
        """从头到尾：一路结算到驾崩，再到新一届开局"""
        game.run("UPDATE consorts SET status='normal' WHERE npc_key IS NOT NULL")
        with patch.object(game, 'npc_schemes'):
            for _ in range(game.MAX_REIGN_DAYS + 3):
                if self.st()['reign_no'] > 1: break
                game.settle_day()
        self.assertEqual(self.st()['reign_no'], 2, '最晚第 70 天必定驾崩')
        self.assertLessEqual(self.reign_row()['end_day'], 1 + game.MAX_REIGN_DAYS)


if __name__ == '__main__':
    unittest.main()
