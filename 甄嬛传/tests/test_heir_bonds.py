"""孩子之间交好（玩耍、交情档位、切磋、淡忘）+ 新增的几条志向奖励

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HeirBondTests(fixtures.unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def kid(self, mother, caretaker=None, gender='皇子', age_years=6, **cols):
        day = game.cur_day()
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,health_max,health,study,riding,virtue) VALUES(?,?,?,9,?,100,80,20,20,20)",
                       (mother, caretaker if caretaker is not None else mother, gender, day - age_years * game.HEIR_DAYS_PER_YEAR)).lastrowid
        for k, v in cols.items(): game.run(f"UPDATE heirs SET {k}=? WHERE id=?", (v, hid))
        return hid

    def play(self, hid, tid):
        return self.client.post(f'/heirs/{hid}/play', data={'target_id': tid})

    def test_play_raises_bond_costs_energy_and_notifies_other_caretaker(self):
        mine, theirs = self.kid(self.atk), self.kid(self.tgt, gender='公主')
        e = game.get_consort(self.atk)['energy']
        self.play(mine, theirs)
        self.assertEqual(game.get_consort(self.atk)['energy'], e - game.HEIR_PLAY_ENERGY)
        self.assertGreaterEqual(game.heir_bond_value(mine, theirs), game.HEIR_BOND_PLAY)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%玩得投缘%'", (self.tgt,), one=True))
        rel = game.relation(self.atk, self.tgt)
        self.assertTrue(rel and rel['affinity'] >= 1, '两位抚养人好感也近了')

    def test_same_pair_once_a_day_and_two_plays_per_child(self):
        mine, a, b, c3 = self.kid(self.atk), self.kid(self.tgt), self.kid(self.tgt), self.kid(self.tgt)
        self.play(mine, a); v = game.heir_bond_value(mine, a)
        self.play(mine, a)
        self.assertEqual(game.heir_bond_value(mine, a), v, '同一个玩伴一天一回')
        self.play(mine, b); self.play(mine, c3)
        self.assertEqual(game.heir_bond_value(mine, c3), 0, '一个孩子一天最多两回')

    def test_rejects_other_peoples_child_too_young_and_adult(self):
        other, mine, baby, grown = self.kid(self.tgt), self.kid(self.atk), self.kid(self.tgt, age_years=1), self.kid(self.tgt, adult_day=1)
        self.play(other, mine)
        self.assertEqual(game.heir_bond_value(other, mine), 0, '不是自己抚养的孩子')
        self.play(mine, baby); self.play(mine, grown)
        self.assertEqual((game.heir_bond_value(mine, baby), game.heir_bond_value(mine, grown)), (0, 0))

    def test_tiers_and_sparring_and_decay(self):
        a, b = self.kid(self.atk, study=60), self.kid(self.tgt, study=20)
        x, y = game.pair(a, b)
        game.run("INSERT INTO heir_bonds(a_id,b_id,bond,last_play_day) VALUES(?,?,?,?)", (x, y, game.HEIR_BOND_CLOSE, game.cur_day()))
        self.assertEqual(game.heir_bond_tier(game.HEIR_BOND_CLOSE), '至交')
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game.random, 'choice', return_value='study'):
            game.heir_bond_tick(game.cur_day())
        self.assertEqual(game.get_heir(b)['study'], 21, '落后的一方切磋长一点')
        self.assertEqual(game.get_heir(a)['exam_bonus'], 3)
        game.run("UPDATE heir_bonds SET last_play_day=? WHERE a_id=? AND b_id=?", (game.cur_day() - game.HEIR_BOND_DECAY_DAYS, x, y))
        game.heir_bond_tick(game.cur_day())
        self.assertEqual(game.heir_bond_value(a, b), game.HEIR_BOND_CLOSE - 1)

    def test_deleting_a_heir_removes_bonds(self):
        a, b = self.kid(self.atk), self.kid(self.tgt)
        self.play(a, b)
        game.heir_delete(b)
        self.assertEqual(game.q("SELECT COUNT(*) n FROM heir_bonds", one=True)['n'], 0)

    def test_page_shows_bond_and_play_form(self):
        a, b = self.kid(self.atk), self.kid(self.tgt)
        self.play(a, b)
        body = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('去找玩伴', body)
        self.assertIn('交好', body)

    def test_new_careers_give_their_rewards(self):
        base = game.get_consort(self.atk)
        game.run("UPDATE consorts SET influence=10, virtue=50, health=50, blessing=0 WHERE id=?", (self.atk,))
        for career, col in (('general', 'influence'), ('scholar', 'virtue'), ('physician', 'health'), ('monk', 'blessing')):
            h = self.kid(self.atk, age_years=14, career=career, career_skill=80, adult_day=1)
            before = game.get_consort(self.atk)[col]
            game.career_reward(game.get_heir(h), self.atk, '某某', '宗师')
            self.assertGreater(game.get_consort(self.atk)[col], before, career)
        self.assertGreaterEqual(len(game.CAREERS), 7)


class AllyTests(HeirBondTests):
    """阵营助力：至交的皇子投靠另一位的夺嫡阵营"""

    def prince(self, mother, age_years=13, **cols):
        return self.kid(mother, age_years=age_years, **cols)

    def close(self, a, b, bond=None):
        x, y = game.pair(a, b)
        game.run("INSERT OR REPLACE INTO heir_bonds(a_id,b_id,bond,last_play_day) VALUES(?,?,?,?)", (x, y, bond or game.HEIR_BOND_CLOSE, game.cur_day()))

    def join(self, ally, leader):
        return self.client.post(f'/heirs/{ally}/ally', data={'leader_id': leader})

    def test_needs_close_bond_and_adds_support_and_faction(self):
        me, boss = self.prince(self.atk), self.prince(self.tgt)
        self.join(me, boss)
        self.assertEqual(game.ally_leader_id(me), 0, '交情不够')
        self.close(me, boss)
        s0, f0 = game.heir_standing(game.get_heir(boss)), game.heir_faction_count(game.get_heir(boss))
        self.join(me, boss)
        self.assertEqual(game.ally_leader_id(me), boss)
        self.assertGreater(game.heir_standing(game.get_heir(boss)), s0 - 1)
        self.assertEqual(game.heir_faction_count(game.get_heir(boss)), f0 + 1)
        self.assertNotIn(me, [h['id'] for h in game.rival_princes()], '助力者不上夺嫡榜')
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%愿投到%'", (self.tgt,), one=True))

    def test_faction_holds_at_most_three_and_no_chains(self):
        boss = self.prince(self.tgt)
        kids = [self.prince(self.atk) for _ in range(4)]
        for k in kids:
            self.close(k, boss); game.run("INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,1)", (k, boss)) if False else None
        for k in kids[:3]: self.join(k, boss)
        self.join(kids[3], boss)
        self.assertEqual(len(game.allies_of(boss)), game.ALLY_MAX, '最多三位')
        self.assertIsNotNone(game.ally_block(game.get_heir(kids[3]), game.get_heir(boss)))
        other = self.prince(self.tgt)
        self.close(boss, other)
        self.assertIsNotNone(game.ally_block(game.get_heir(boss), game.get_heir(other)), '带着助力者的不能再投别人')
        self.assertIsNotNone(game.ally_block(game.get_heir(other), game.get_heir(kids[0])), '不能投靠别人阵营里的助力者')

    def test_leave_has_cooldown_and_leader_can_dismiss(self):
        me, boss = self.prince(self.atk), self.prince(self.tgt)
        self.close(me, boss); self.join(me, boss)
        self.client.post(f'/heirs/{me}/ally/leave')
        self.assertEqual(game.ally_leader_id(me), 0)
        self.assertGreater(game.get_heir(me)['ally_ready_day'], game.cur_day())
        self.join(me, boss)
        self.assertEqual(game.ally_leader_id(me), 0, '冷却期内不能再投靠')
        game.run("UPDATE heirs SET ally_ready_day=0 WHERE id=?", (me,))
        self.join(me, boss)
        self.login(self.tgt)
        self.client.post(f'/heirs/{me}/ally/leave')
        self.assertEqual(game.ally_leader_id(me), 0, '主人的抚养人可以请他出去')

    def test_tick_drops_stale_allies_and_crowning_rewards(self):
        me, boss = self.prince(self.atk), self.prince(self.tgt)
        self.close(me, boss); self.join(me, boss)
        self.close(me, boss, bond=game.HEIR_BOND_FRIEND - 1)
        game.heir_ally_tick(game.cur_day())
        self.assertEqual(game.ally_leader_id(me), 0, '交情淡了自动退出')
        self.close(me, boss); self.join(me, boss)
        game.run("UPDATE heirs SET career='artist' WHERE id=?", (boss,))
        game.heir_ally_tick(game.cur_day())
        self.assertEqual(game.ally_leader_id(me), 0, '阵营主人改走别的志向，阵营散了')

    def test_page_renders_ally_forms(self):
        me, boss = self.prince(self.atk), self.prince(self.tgt)
        self.close(me, boss)
        self.assertIn('投靠阵营', self.client.get('/heirs').get_data(as_text=True))
        self.join(me, boss)
        self.assertIn('助力于', self.client.get('/heirs').get_data(as_text=True))
        self.assertEqual(self.client.get('/succession').status_code, 200)


class EndingTests(AllyTests):
    """开匾结局：志向、阵营、公主婚事"""

    def winner_row(self, hid):
        return game.get_heir(hid)

    def test_career_prince_in_winner_camp_becomes_rich_prince_else_commoner(self):
        boss = self.prince(self.tgt)
        rich = self.prince(self.atk, career='artist', career_skill=80, adult_day=1, age_years=15)
        plain = self.prince(self.atk, career='artist', career_skill=10, adult_day=1, age_years=15)
        loser_boss = self.prince(self.tgt)
        wrong = self.prince(self.atk, career='scientist', adult_day=1, age_years=15)
        game.run("INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,1)", (rich, boss))
        game.run("INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,1)", (wrong, loser_boss))
        day = game.cur_day(); win = self.winner_row(boss)
        text, kind = game.heir_ending(game.get_heir(rich), win, day, set())
        self.assertEqual(kind, 'rich'); self.assertIn('亲王', text); self.assertIn('画师王爷', text); self.assertIn('宗师', text)
        text, kind = game.heir_ending(game.get_heir(plain), win, day, set())
        self.assertEqual(kind, 'commoner'); self.assertIn('宗人', text)
        text, kind = game.heir_ending(game.get_heir(wrong), win, day, set())
        self.assertEqual(kind, 'commoner'); self.assertIn('押错了阵营', text)

    def test_throne_prince_endings(self):
        boss, ally, loner = self.prince(self.tgt), self.prince(self.atk, adult_day=1, age_years=15, title='贝勒'), self.prince(self.atk, adult_day=1, age_years=15, title='贝勒')
        game.run("INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,1)", (ally, boss))
        day, win = game.cur_day(), self.winner_row(boss)
        self.assertEqual(game.heir_ending(game.get_heir(boss), win, day, set())[1], 'throne')
        self.assertEqual(game.heir_ending(game.get_heir(ally), win, day, set())[1], 'rich')
        self.assertEqual(game.heir_ending(game.get_heir(loner), win, day, set())[1], 'prince')
        self.assertEqual(game.heir_ending(game.get_heir(loner), win, day, {loner})[1], 'jailed')

    def test_princess_endings_follow_marriage_and_harmony(self):
        win = self.winner_row(self.prince(self.tgt))
        day = game.cur_day()
        single = self.kid(self.atk, gender='公主', age_years=5)
        self.assertEqual(game.heir_ending(game.get_heir(single), win, day, set())[1], 'single')
        wife = self.kid(self.atk, gender='公主', age_years=18, marriage='capital', marry_day=3, title='和硕公主')
        game.run("INSERT INTO princess_courtships(heir_id,harmony,family_fortune) VALUES(?,?,?)", (wife, 80, 70))
        text, tier = game.heir_ending(game.get_heir(wife), win, day, set())
        self.assertEqual(tier, 'bliss'); self.assertIn('儿女绕膝', text)
        game.run("UPDATE princess_courtships SET harmony=20, family_fortune=20 WHERE heir_id=?", (wife,))
        self.assertEqual(game.heir_ending(game.get_heir(wife), win, day, set())[1], 'sad')
        mongol = self.kid(self.atk, gender='公主', age_years=18, marriage='mongol', marry_day=3, title='固伦公主')
        self.assertIn('远嫁蒙古', game.heir_ending(game.get_heir(mongol), win, day, set())[0])

    def test_end_reign_writes_endings_into_edict_and_kids(self):
        boss = self.prince(self.tgt, adult_day=1, age_years=16)
        mine = self.prince(self.atk, career='physician', career_skill=60, adult_day=1, age_years=16)
        game.run("INSERT INTO heir_allies(ally_id,leader_id,since_day) VALUES(?,?,1)", (mine, boss))
        from unittest.mock import patch
        with patch.object(game, 'choose_successor', return_value=game.get_heir(boss)):
            rid = game.end_reign(game.cur_day())
        reign = game.q("SELECT * FROM reigns WHERE id=?", (rid,), one=True)
        self.assertIn('诸皇嗣的归宿', reign['edict'])
        self.assertIn('医王爷', reign['edict'])


class HeirsPageOrderTests(HeirBondTests):
    def test_my_children_and_adopted_ones_come_first_then_others(self):
        other = self.kid(self.tgt, age_years=5, name='弘乙')
        adopted = self.kid(self.tgt, caretaker=self.atk, age_years=5, name='弘丙')      # 别人生的，我领养来抚养
        mine = self.kid(self.atk, age_years=5, name='弘甲')
        entrusted = self.kid(self.atk, caretaker=self.tgt, age_years=5, name='弘丁')      # 我生的，托付给别人养
        rows = game.q("SELECT h.* FROM heirs h ORDER BY h.id")
        ordered = sorted(rows, key=lambda h: 0 if self.atk in (h['caretaker_id'], h['mother_id']) else 1)
        self.assertEqual({r['id'] for r in ordered[:3]}, {adopted, mine, entrusted})
        self.assertEqual(ordered[3]['id'], other)
        body = self.client.get('/heirs').get_data(as_text=True)
        import re
        pos = {i: re.search(re.escape(game.heir_label(game.get_heir(i))), body) for i in (adopted, mine, entrusted, other)}
        self.assertTrue(all(pos.values()))
        self.assertGreater(pos[other].start(), max(pos[i].start() for i in (adopted, mine, entrusted)), '别人的孩子排在自己的和领养的之后')
