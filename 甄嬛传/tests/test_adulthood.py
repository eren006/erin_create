"""皇嗣成年：皇子封爵开府、孝敬、差事、替母求情，公主指婚，见设计文档九点六节 E

运行：python3 -m unittest discover -s tests -v
"""
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


def favor_only(h):
    return h['favor']


class AdulthoodTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def row(self, hid):
        return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def grown(self, mother, **kw):
        """出生满七次结算，今晚满十四岁"""
        kw.setdefault('born', game.cur_day() - game.HEIR_ADULT_AGE_DAYS)
        return self.heir(mother, **kw)

    def adult_prince(self, mother, title='郡王', **kw):
        return self.grown(mother, adult_day=game.cur_day() - 1, title=title, **kw)

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    # ── 皇子封爵 ─────────────────────────────────────────────────────────────

    @patch.object(game, 'heir_standing', favor_only)   # 这里只测门槛，圣眷公式另有用例
    def test_prince_title_by_favor(self):
        for favor, title in [(100, '亲王'), (80, '亲王'), (79, '郡王'), (60, '郡王'), (59, '贝勒'), (40, '贝勒'), (39, '贝子'), (0, '贝子')]:
            hid = self.grown(self.atk, favor=favor)
            game.heir_adult_tick(game.cur_day())
            h = self.row(hid)
            self.assertEqual(h['title'], title, f'圣眷 {favor}')
            self.assertEqual(h['adult_day'], game.cur_day())

    def test_not_adult_a_day_early(self):
        hid = self.heir(self.atk, born=game.cur_day() - game.HEIR_ADULT_AGE_DAYS + 1)
        game.heir_adult_tick(game.cur_day())
        self.assertEqual(self.row(hid)['adult_day'], 0)

    @patch.object(game, 'heir_standing', favor_only)   # 这里只测门槛，圣眷公式另有用例
    def test_coming_of_age_fires_once_and_notifies_parents(self):
        hid = self.grown(self.tgt, caretaker=self.atk, favor=65)
        game.heir_adult_tick(game.cur_day())
        first = dict(self.row(hid))
        game.heir_adult_tick(game.cur_day() + 1)
        self.assertEqual(self.row(hid)['adult_day'], first['adult_day'])
        self.assertTrue(any('封为郡王' in m for m in self.msgs(self.atk)))
        self.assertTrue(any('封为郡王' in m for m in self.msgs(self.tgt)))

    def test_adult_is_not_raised_or_rehomed_or_given_events(self):
        hid = self.adult_prince(self.atk)
        self.client.post(f'/heirs/raise/{hid}', data=dict(opt='study'))
        self.assertEqual(self.row(hid)['study'], 20)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        self.player('丙', rank=6)
        game.heir_rehome_tick(game.cur_day())
        self.assertEqual(self.row(hid)['caretaker_id'], self.atk, '成年皇子不再换抚养人')

    # ── 孝敬 ─────────────────────────────────────────────────────────────────

    def test_filial_silver_all_to_single_parent(self):
        hid = self.adult_prince(self.atk, title='亲王')
        s0 = game.get_consort(self.atk)['silver']
        game.heir_filial_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + game.FILIAL_SILVER['亲王'])

    def test_filial_silver_split_by_affinity(self):
        hid = self.adult_prince(self.tgt, caretaker=self.atk, title='亲王', mother_affinity=25, caretaker_affinity=75)
        s_atk, s_tgt = game.get_consort(self.atk)['silver'], game.get_consort(self.tgt)['silver']
        game.heir_filial_tick(game.cur_day())
        total = game.FILIAL_SILVER['亲王']
        got_tgt = game.get_consort(self.tgt)['silver'] - s_tgt
        got_atk = game.get_consort(self.atk)['silver'] - s_atk
        self.assertEqual(got_tgt + got_atk, total, '一分不多一分不少')
        self.assertGreater(got_atk, got_tgt, '跟养母情分高，养母分得多')
        self.assertEqual(got_tgt, round(total * 25 / 100))

    def test_filial_dead_parent_gets_nothing_other_gets_all(self):
        hid = self.adult_prince(self.tgt, caretaker=self.atk, title='贝勒')
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (self.tgt,))
        s = game.get_consort(self.atk)['silver']
        game.heir_filial_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['silver'], s + game.FILIAL_SILVER['贝勒'])

    def test_princess_and_untitled_do_not_pay(self):
        self.adult_prince(self.atk, title='', gender='皇子')
        self.grown(self.atk, gender='公主', adult_day=1, title='固伦公主', marriage='mongol')
        s = game.get_consort(self.atk)['silver']
        game.heir_filial_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['silver'], s)

    # ── 替母求情 ──────────────────────────────────────────────────────────────

    def confine(self, cid, until):
        game.run("UPDATE consorts SET status='confined', status_until_day=? WHERE id=?", (until, cid))

    def test_prince_pleads_for_confined_mother(self):
        hid = self.adult_prince(self.atk)
        self.confine(self.atk, game.cur_day() + 3)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_plead_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status_until_day'], game.cur_day() + 2)
        self.assertEqual(self.row(hid)['plead_ready_day'], game.cur_day() + game.PRINCE_PLEAD_INTERVAL)

    def test_plead_releases_when_time_is_up(self):
        self.adult_prince(self.atk)
        self.confine(self.atk, game.cur_day() + 1)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_plead_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_plead_failure_still_starts_cooldown(self):
        hid = self.adult_prince(self.atk)
        self.confine(self.atk, game.cur_day() + 3)
        with patch.object(game.random, 'random', return_value=0.999):
            game.heir_plead_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status_until_day'], game.cur_day() + 3)
        self.assertEqual(self.row(hid)['plead_ready_day'], game.cur_day() + game.PRINCE_PLEAD_INTERVAL)

    def test_plead_respects_cooldown_and_ignores_healthy_mother(self):
        hid = self.adult_prince(self.atk, plead_ready_day=game.cur_day() + 3)
        self.confine(self.atk, game.cur_day() + 3)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_plead_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status_until_day'], game.cur_day() + 3, '冷却中不求')
        game.run("UPDATE consorts SET status='normal', status_until_day=0 WHERE id=?", (self.atk,))
        game.run('UPDATE heirs SET plead_ready_day=0 WHERE id=?', (hid,))
        game.heir_plead_tick(game.cur_day())
        self.assertEqual(self.row(hid)['plead_ready_day'], 0, '母亲好好的，不占用冷却')

    def test_plead_favor_raises_success_chance(self):
        hid = self.adult_prince(self.atk, favor=100)
        self.confine(self.atk, game.cur_day() + 3)
        game.run('UPDATE consorts SET trust=0 WHERE id=?', (self.atk,))
        # 信任 0 时基础 30%，圣眷 100 再加 30% → 掷 0.5 该成功
        with patch.object(game.random, 'random', return_value=0.5):
            game.heir_plead_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['status_until_day'], game.cur_day() + 2)

    # ── 差事 ─────────────────────────────────────────────────────────────────

    def test_errand_issued_on_interval_only(self):
        hid = self.adult_prince(self.atk)   # adult_day = 今天 - 1
        game.heir_errand_tick(game.cur_day())   # 差 1 天，没到
        self.assertEqual(self.row(hid)['errand'], '')
        game.heir_errand_tick(game.cur_day() + 2)   # 差 3 天
        self.assertTrue(self.row(hid)['errand'])
        self.assertTrue(any('差事' in m for m in self.msgs(self.atk)))

    def test_errand_not_resolved_on_the_night_it_is_issued(self):
        hid = self.adult_prince(self.atk)
        day = game.cur_day() + 2
        game.heir_errand_tick(day)
        first = self.row(hid)['errand']
        game.heir_errand_tick(day)
        self.assertEqual(self.row(hid)['errand'], first)
        self.assertEqual(self.row(hid)['favor'], 0)

    def put_errand(self, hid, day, approach=None, key='relief'):
        data = dict(key=key, day=day)
        if approach: data['approach'] = approach
        game.run('UPDATE heirs SET errand=? WHERE id=?', (game.json.dumps(data), hid))

    def test_steady_is_default_when_no_approach_chosen(self):
        hid = self.adult_prince(self.atk, favor=10, virtue=50)
        self.put_errand(hid, game.cur_day() - 1)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 10 + game.ERRAND_APPROACHES['steady']['win'])
        self.assertEqual(self.row(hid)['errand'], '', '交差后清空；今晚不在派差的日子里')

    def test_grab_wins_big_or_loses_big(self):
        ap = game.ERRAND_APPROACHES['grab']
        hid = self.adult_prince(self.atk, favor=10, virtue=50)
        self.put_errand(hid, game.cur_day() - 1, 'grab')
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 10 + ap['win'])
        self.put_errand(hid, game.cur_day() - 1, 'grab')
        with patch.object(game.random, 'random', return_value=0.999):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 10 + ap['win'] + ap['lose'])

    def test_favor_never_goes_negative(self):
        hid = self.adult_prince(self.atk, favor=2)
        self.put_errand(hid, game.cur_day() - 1, 'grab')
        with patch.object(game.random, 'random', return_value=0.999):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(hid)['favor'], 0)

    def test_stat_shifts_success_chance(self):
        # 赈灾看品行：品行 100 时 steady 成功率 0.65+0.2 = 0.85，品行 0 时 0.65-0.2 = 0.45（先取 0.15 下限之上）
        good = self.adult_prince(self.atk, favor=0, virtue=100)
        bad = self.adult_prince(self.atk, favor=0, virtue=0)
        for hid in (good, bad):
            self.put_errand(hid, game.cur_day() - 1, 'steady')
        with patch.object(game.random, 'random', return_value=0.6):
            game.heir_errand_tick(game.cur_day())
        self.assertGreater(self.row(good)['favor'], 0)
        self.assertEqual(self.row(bad)['favor'], 0)

    def test_shift_burdens_a_rival_on_success(self):
        ap = game.ERRAND_APPROACHES['shift']
        me = self.adult_prince(self.atk, favor=10, virtue=50)
        rival = self.adult_prince(self.tgt, favor=30)
        self.put_errand(me, game.cur_day() - 1, 'shift')
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(me)['favor'], 10 + ap['win'])
        self.assertEqual(self.row(rival)['favor'], 30 + ap['rival'])
        self.assertTrue(any('推来' in m for m in self.msgs(self.tgt)))

    def test_shift_without_rival_falls_back_to_steady(self):
        me = self.adult_prince(self.atk, favor=10, virtue=50)
        self.put_errand(me, game.cur_day() - 1, 'shift')
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_errand_tick(game.cur_day())
        self.assertEqual(self.row(me)['favor'], 10 + game.ERRAND_APPROACHES['steady']['win'])

    def test_caretaker_chooses_approach_via_route(self):
        hid = self.adult_prince(self.atk)
        self.put_errand(hid, game.cur_day())
        self.client.post(f'/heirs/errand/{hid}', data=dict(approach='grab'))
        self.assertEqual(game.json.loads(self.row(hid)['errand'])['approach'], 'grab')
        self.client.post(f'/heirs/errand/{hid}', data=dict(approach='shift'))   # 没有别的阿哥，推不了
        self.assertEqual(game.json.loads(self.row(hid)['errand'])['approach'], 'grab')
        self.login(self.tgt)
        self.client.post(f'/heirs/errand/{hid}', data=dict(approach='steady'))
        self.assertEqual(game.json.loads(self.row(hid)['errand'])['approach'], 'grab', '别人替他选不了')

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_npc_caretaker_princes_choose_for_themselves(self):
        npc = game.q("SELECT id FROM consorts WHERE npc_key IS NOT NULL LIMIT 1", one=True)['id']
        hid = self.adult_prince(npc)
        game.heir_errand_tick(game.cur_day() + 2)
        self.assertIn('approach', game.json.loads(self.row(hid)['errand']))

    # ── 公主指婚 ─────────────────────────────────────────────────────────────

    def test_princess_eligible_mother_gets_to_choose(self):
        game.run('UPDATE consorts SET trust=? WHERE id=?', (game.MARRY_MIN_TRUST, self.atk))
        hid = self.grown(self.atk, gender='公主', favor=game.MARRY_MIN_FAVOR)
        game.heir_adult_tick(game.cur_day())
        h = self.row(hid)
        self.assertEqual(h['marriage'], 'choice')
        self.assertEqual(h['title'], '')

    def test_princess_ineligible_is_sent_to_mongolia_without_bonus(self):
        game.run('UPDATE consorts SET trust=? WHERE id=?', (game.MARRY_MIN_TRUST - 1, self.atk))
        hid = self.grown(self.atk, gender='公主', favor=90)
        game.heir_adult_tick(game.cur_day())
        h = self.row(hid)
        self.assertEqual((h['marriage'], h['title']), ('mongol', '固伦公主'))
        self.assertEqual(game.get_consort(self.atk)['trust'], game.MARRY_MIN_TRUST - 1)

    @patch.object(game, 'heir_standing', favor_only)   # 这里只测门槛，圣眷公式另有用例
    def test_princess_low_favor_also_sent_away(self):
        game.run('UPDATE consorts SET trust=90 WHERE id=?', (self.atk,))
        hid = self.grown(self.atk, gender='公主', favor=game.MARRY_MIN_FAVOR - 1)
        game.heir_adult_tick(game.cur_day())
        self.assertEqual(self.row(hid)['marriage'], 'mongol')

    def test_mother_picks_mongolia_gets_trust(self):
        game.run('UPDATE consorts SET trust=60 WHERE id=?', (self.atk,))
        hid = self.grown(self.atk, gender='公主', adult_day=game.cur_day(), marriage='choice', favor=70)
        self.client.post(f'/heirs/marry/{hid}', data=dict(kind='mongol'))
        h = self.row(hid)
        self.assertEqual((h['marriage'], h['title']), ('mongol', '固伦公主'))
        self.assertEqual(game.get_consort(self.atk)['trust'], 60 + game.MONGOL_TRUST_GAIN)
        self.assertEqual(h['marry_day'], game.cur_day())

    def test_mother_picks_capital(self):
        hid = self.grown(self.atk, gender='公主', adult_day=game.cur_day(), marriage='choice', favor=70)
        self.client.post(f'/heirs/marry/{hid}', data=dict(kind='capital'))
        h = self.row(hid)
        self.assertEqual((h['marriage'], h['title']), ('capital', '和硕公主'))

    def test_only_caretaker_can_choose_and_only_once(self):
        hid = self.grown(self.atk, gender='公主', adult_day=game.cur_day(), marriage='choice', favor=70)
        self.login(self.tgt)
        self.client.post(f'/heirs/marry/{hid}', data=dict(kind='capital'))
        self.assertEqual(self.row(hid)['marriage'], 'choice')
        self.login(self.atk)
        self.client.post(f'/heirs/marry/{hid}', data=dict(kind='capital'))
        self.client.post(f'/heirs/marry/{hid}', data=dict(kind='mongol'))
        self.assertEqual(self.row(hid)['marriage'], 'capital', '定了就不能改')

    def test_undecided_marriage_defaults_to_capital_after_deadline(self):
        hid = self.grown(self.atk, gender='公主', adult_day=game.cur_day() - game.MARRY_CHOICE_DAYS + 1, marriage='choice')
        game.heir_marriage_deadline_tick(game.cur_day())
        self.assertEqual(self.row(hid)['marriage'], 'choice')
        game.heir_marriage_deadline_tick(game.cur_day() + 1)
        self.assertEqual(self.row(hid)['marriage'], 'capital')

    def test_capital_marriage_halves_mothers_favor_decay(self):
        self.grown(self.tgt, caretaker=self.atk, gender='公主', adult_day=1, marriage='capital', title='和硕公主')
        self.assertEqual(game.capital_mother_ids(), {self.tgt, self.atk})

    def test_family_letters_every_seven_days_for_mongol_marriage(self):
        hid = self.grown(self.atk, gender='公主', adult_day=1, marriage='mongol', title='固伦公主', marry_day=10)
        for d in range(10, 10 + game.MONGOL_LETTER_INTERVAL):
            game.heir_family_letter_tick(d)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters WHERE to_id=?', (self.atk,), one=True)['n'], 0)
        game.heir_family_letter_tick(10 + game.MONGOL_LETTER_INTERVAL)
        letter = game.q('SELECT * FROM letters WHERE to_id=?', (self.atk,), one=True)
        self.assertIsNotNone(letter)
        self.assertEqual(letter['from_id'], 0)
        self.assertIn('固伦公主', letter['sender_label'])
        page = self.client.get('/letters').get_data(as_text=True)
        self.assertIn('固伦公主', page)
        self.assertNotIn('<b>内务府</b>', page.split('收到的')[1] if '收到的' in page else page)

    def test_capital_princess_sends_no_letters(self):
        self.grown(self.atk, gender='公主', adult_day=1, marriage='capital', title='和硕公主', marry_day=10)
        game.heir_family_letter_tick(10 + game.MONGOL_LETTER_INTERVAL)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM letters WHERE to_id=?', (self.atk,), one=True)['n'], 0)

    # ── 页面 ─────────────────────────────────────────────────────────────────

    def test_pages_render_marriage_and_errand_controls(self):
        hid = self.grown(self.atk, gender='公主', adult_day=game.cur_day(), marriage='choice')
        prince = self.adult_prince(self.atk)
        self.put_errand(prince, game.cur_day())
        page = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('留京下嫁', page)
        self.assertIn('抚蒙古', page)
        self.assertIn('赈灾', page)
        self.assertIn('稳妥办理', page)
        self.assertNotIn('推给别的阿哥', page, '没有别的阿哥可推时不给这个选项')
        home = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('等你拿主意', home)

    def test_full_settle_runs_adult_tick_without_error(self):
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IS NOT NULL")
        self.grown(self.atk, favor=70)
        self.grown(self.atk, gender='公主', favor=70)
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        self.assertEqual(game.q("SELECT COUNT(*) n FROM heirs WHERE adult_day>0", one=True)['n'], 2)

    def test_persona_grows_up_with_adulthood(self):
        for pers in game.HEIR_PERSONALITIES:
            kid = self.row(self.heir(self.atk, personality=pers))
            adult = self.row(self.adult_prince(self.atk, personality=pers))
            pk, pa = game.heir_persona(kid), game.heir_persona(adult)
            self.assertEqual(pk['name'], pa['name'])          # 大类不变
            self.assertEqual(pa['tag'], game.heir_persona(adult)['tag'])
            self.assertIn(pa['tag'], [t for t, _ in game.HEIR_PERSONA_ADULT[pers]['tags']])
            self.assertNotIn(pa['tag'], [t for t, _ in game.HEIR_PERSONA[pers]['tags']])
            self.assertNotIn('乳母', pa['text'])


if __name__ == '__main__':
    unittest.main()
