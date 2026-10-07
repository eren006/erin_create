"""菜园、新年宴会、每日差事

运行：python3 -m unittest discover -s tests -v
"""
import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('game_garden', ROOT / 'app.py')
game = importlib.util.module_from_spec(spec)
spec.loader.exec_module(game)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB_PATH = str(Path(self.temp.name) / 'test.db')
        game.app.config['TESTING'] = True
        game.init_db()
        self.ctx = game.app.app_context()
        self.ctx.push()
        game.run('UPDATE game_state SET day=10')
        self.me = self.player('甲')
        self.other = self.player('乙')
        self.client = game.app.test_client()
        self.login(self.me)

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def player(self, name, favor=90, rank=4):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name, 'test')).lastrowid
        return game.run('''INSERT INTO consorts(user_id,surname,given,rank,status,entered_day,rank_since_day,
                           family,personality,silver,age_months,recap_seen_day,favor,energy) VALUES(?,?,?,?,'normal',1,1,?,?,500,240,9,?,8)''',
                        (uid, name, name + '儿', rank, next(iter(game.FAMILIES)), next(iter(game.PERSONALITIES)), favor)).lastrowid

    def login(self, cid):
        with self.client.session_transaction() as sess:
            sess['uid'] = game.get_consort(cid)['user_id']

    def me_row(self): return game.get_consort(self.me)


class GardenTests(Base):
    def test_pages_render(self):
        for route in ('/garden', '/banquet', '/quests'):
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_plant_costs_seed_and_takes_time(self):
        s0 = self.me_row()['silver']
        self.client.post('/garden/plant', data=dict(slot=1, crop='luobo'))
        self.assertEqual(self.me_row()['silver'], s0 - game.CROPS['luobo']['seed'])
        self.client.post('/garden/harvest', data=dict(slot='all'))
        self.assertEqual(game.stock_of(self.me), {}, '没熟不能收')

    def test_cannot_plant_on_taken_or_missing_plot(self):
        self.client.post('/garden/plant', data=dict(slot=1, crop='luobo'))
        s1 = self.me_row()['silver']
        self.client.post('/garden/plant', data=dict(slot=1, crop='qingcai'))
        self.client.post('/garden/plant', data=dict(slot=5, crop='qingcai'))
        self.assertEqual(self.me_row()['silver'], s1)

    def test_water_once_and_harvest_when_ready(self):
        self.client.post('/garden/plant', data=dict(slot=1, crop='qingcai'))
        before = game.q('SELECT ready_ts FROM garden_plots WHERE consort_id=?', (self.me,), one=True)['ready_ts']
        self.client.post('/garden/water', data=dict(slot=1))
        after = game.q('SELECT ready_ts FROM garden_plots WHERE consort_id=?', (self.me,), one=True)['ready_ts']
        self.assertLess(after, before)
        self.client.post('/garden/water', data=dict(slot=1))
        self.assertEqual(game.q('SELECT ready_ts FROM garden_plots WHERE consort_id=?', (self.me,), one=True)['ready_ts'], after, '每茬只能浇一次')
        game.run('UPDATE garden_plots SET ready_ts=0')
        self.client.post('/garden/harvest', data=dict(slot='all'))
        n = game.stock_of(self.me)['qingcai']
        self.assertIn(n, (3, 4))
        self.assertIsNone(game.q('SELECT 1 FROM garden_plots', one=True))

    def test_sell_gift_and_tribute(self):
        game.stock_add(self.me, 'baicai', 5)
        s0 = self.me_row()['silver']
        self.client.post('/garden/sell', data=dict(crop='baicai'))
        self.assertEqual(game.stock_of(self.me), {})
        self.assertEqual(self.me_row()['silver'], s0 + 5 * game.CROPS['baicai']['sell'])
        game.stock_add(self.me, 'baicai', 3)
        self.client.post('/garden/gift', data=dict(crop='baicai', target_id=self.other))
        self.assertEqual(game.stock_of(self.me)['baicai'], 2)
        self.assertEqual(game.relation(self.me, self.other)['affinity'], game.GARDEN_GIFT_AFFINITY)
        f0 = self.me_row()['favor']
        self.client.post('/garden/tribute', data=dict(crop='baicai'))
        self.client.post('/garden/tribute', data=dict(crop='baicai'))
        self.assertEqual(game.stock_of(self.me)['baicai'], 1, '进献一天一次')
        self.assertGreater(self.me_row()['favor'], f0)

    def test_expand_plots(self):
        game.run('UPDATE consorts SET silver=5000 WHERE id=?', (self.me,))
        self.client.post('/garden/expand')
        self.assertEqual(self.me_row()['garden_plots'], game.GARDEN_BASE_PLOTS + 1)
        for _ in range(5): self.client.post('/garden/expand')
        self.assertEqual(self.me_row()['garden_plots'], game.GARDEN_MAX_PLOTS)


class BanquetTests(Base):
    def test_enter_costs_energy_once_per_night(self):
        self.client.post('/banquet/enter', data=dict(piece='琴|0'))
        self.assertEqual(self.me_row()['energy'], 8 - game.BANQUET_ENERGY)
        self.client.post('/banquet/enter', data=dict(piece='棋|0'))
        self.assertEqual(self.me_row()['energy'], 8 - game.BANQUET_ENERGY)
        self.assertEqual(game.q('SELECT art FROM banquet_entries WHERE consort_id=?', (self.me,), one=True)['art'], '琴')

    def test_rehearse_adds_proficiency_up_to_max(self):
        self.client.post('/banquet/rehearse')
        self.assertEqual(self.me_row()['energy'], 8, '没报名不能排练')
        self.client.post('/banquet/enter', data=dict(piece='琴|0'))
        for _ in range(4): self.client.post('/banquet/rehearse')
        self.assertEqual(game.arts_of(self.me_row()).get('琴'), game.BANQUET_REHEARSE_MAX)

    @patch.object(game, 'check_achievements', return_value=[])   # 成就赏银会改银子数，这里只看本身的奖励
    def test_banquet_runs_once_at_22_and_pays_winner(self, _ach):
        game.run("UPDATE consorts SET talent=100 WHERE id=?", (self.me,))
        game.run("UPDATE consorts SET talent=1 WHERE id=?", (self.other,))
        game.run("UPDATE consorts SET arts=? WHERE id=?", ('{"琴": 15}', self.me))
        self.client.post('/banquet/enter', data=dict(piece='琴|0'))
        self.login(self.other)
        self.client.post('/banquet/enter', data=dict(piece='舞|0'))
        date = game.banquet_date()
        s0 = {i: game.get_consort(i)['silver'] for i in (self.me, self.other)}
        game.maybe_banquet(datetime(2100, 1, 1, 21, 59, tzinfo=game.TZ))
        self.assertIsNone(game.q('SELECT place FROM banquet_entries', one=True)['place'], '22 点前不开席')
        # banquet_date 按当前真实时间算，开席日用报名那一晚的日期
        with patch.object(game, 'datetime') as dt:
            dt.now.return_value = datetime.fromisoformat(date + 'T22:05:00+08:00')
            game.maybe_banquet(dt.now.return_value)
            game.maybe_banquet(dt.now.return_value)
        places = {r['consort_id']: r['place'] for r in game.q('SELECT * FROM banquet_entries')}
        self.assertEqual(places[self.me], 1)
        self.assertEqual(places[self.other], 2)
        self.assertEqual(game.get_consort(self.me)['silver'], s0[self.me] + game.BANQUET_REWARDS[1][1])
        self.assertEqual(game.arts_of(game.get_consort(self.me))['琴'], 16, '献艺也涨熟练度，且只开一次席')


    def test_hard_piece_needs_proficiency_or_rehearsal(self):
        game.run('UPDATE consorts SET talent=50 WHERE id=?', (self.me,))
        c = self.me_row()
        with patch.object(game.random, 'uniform', return_value=0):
            raw, stumble = game.banquet_score(c, '琴', 0, tier=3)
            self.assertTrue(stumble)
            ok, stumble2 = game.banquet_score(c, '琴', 0, tier=1)
            self.assertFalse(stumble2)
            self.assertLess(raw, ok, '没练熟硬上难档要扣分')
            game.run("UPDATE consorts SET arts=? WHERE id=?", ('{"琴": 6}', self.me))
            _, s_rehearsed = game.banquet_score(self.me_row(), '琴', 1, tier=3)   # 6 + 1*2 = 8 = 精通
            self.assertFalse(s_rehearsed, '排练补上熟练度就够格')

    def test_enter_records_tier_and_custom_title(self):
        self.client.post('/banquet/enter', data=dict(piece='琴|2', title='霓裳一曲'))
        e = game.q('SELECT * FROM banquet_entries WHERE consort_id=?', (self.me,), one=True)
        self.assertEqual((e['art'], e['tier'], e['piece']), ('琴', 3, '霓裳一曲'))

    def test_enter_rejects_bad_piece_and_blocked_title(self):
        self.client.post('/banquet/enter', data=dict(piece='琴|9'))
        self.client.post('/banquet/enter', data=dict(piece='剑|0'))
        with patch.object(game, 'blocked_hit', return_value='某词'):
            self.client.post('/banquet/enter', data=dict(piece='琴|0', title='违规'))
        self.assertIsNone(game.q('SELECT 1 FROM banquet_entries', one=True))
        self.assertEqual(self.me_row()['energy'], 8)

    def test_art_levels(self):
        self.assertEqual(game.art_level(0), '生疏')
        self.assertEqual(game.art_level(2), '入门')
        self.assertEqual(game.art_level(game.ART_MASTERY), '精通')
        self.assertEqual(game.art_level(15), '大成')


class QuestTests(Base):
    def test_four_stable_quests_per_day(self):
        a = [x['key'] for x in game.quests_today(self.me_row())]
        self.assertEqual(len(set(a)), game.QUEST_COUNT)
        self.assertEqual(a, [x['key'] for x in game.quests_today(self.me_row())])

    def test_claim_requires_done_and_pays_once(self):
        x = game.quests_today(self.me_row())[0]
        s0 = self.me_row()['silver']
        self.client.post('/quests/claim', data=dict(key=x['key']))
        self.assertEqual(self.me_row()['silver'], s0, '没办完不能领')
        game.daily_inc(self.me, x['counter'], x['goal'])
        self.client.post('/quests/claim', data=dict(key=x['key']))
        self.client.post('/quests/claim', data=dict(key=x['key']))
        self.assertEqual(self.me_row()['silver'], s0 + x['silver'])

    @patch.object(game, 'check_achievements', return_value=[])   # 成就赏银会改银子数，这里只看本身的奖励
    def test_all_bonus(self, _ach):
        s0 = self.me_row()['silver']
        game.run('UPDATE consorts SET energy=3 WHERE id=?', (self.me,))
        total = 0
        for x in game.quests_today(self.me_row()):
            game.daily_inc(self.me, x['counter'], x['goal'])
            self.client.post('/quests/claim', data=dict(key=x['key']))
            total += x['silver']
        self.client.post('/quests/claim', data=dict(key='all'))
        self.client.post('/quests/claim', data=dict(key='all'))
        self.assertEqual(self.me_row()['silver'], s0 + total + game.QUEST_ALL_BONUS['silver'])
        self.assertEqual(self.me_row()['energy'], 3 + game.QUEST_ALL_BONUS['energy'])


class KitchenTests(Base):
    def test_cook_consumes_ingredients_and_limit(self):
        game.stock_add(self.me, 'qingcai', 3)
        self.client.post('/garden/cook', data=dict(dish='qingchao'))
        self.assertEqual(game.stock_of(self.me), {'d_qingchao': 1})
        self.client.post('/garden/cook', data=dict(dish='qingchao'))
        self.assertEqual(game.stock_of(self.me), {'d_qingchao': 1}, '食材不够不能做')

    def test_eat_energy_dish_and_daily_cap(self):
        game.run('UPDATE consorts SET energy=2 WHERE id=?', (self.me,))
        game.stock_add(self.me, 'd_baicaijiao', 4)
        for _ in range(4): self.client.post('/garden/eat', data=dict(dish='baicaijiao'))
        self.assertEqual(self.me_row()['energy'], 8, '精力封顶')
        self.assertEqual(game.stock_of(self.me)['d_baicaijiao'], 4 - game.EAT_DAILY_MAX)

    def test_banquet_dish_needs_entry_and_adds_buff(self):
        game.stock_add(self.me, 'd_nangua_geng', 3)
        self.client.post('/garden/eat', data=dict(dish='nangua_geng'))
        self.assertEqual(game.stock_of(self.me)['d_nangua_geng'], 3, '没报节目不能吃宴前小食')
        self.client.post('/banquet/enter', data=dict(piece='琴|0'))
        self.client.post('/garden/eat', data=dict(dish='nangua_geng'))
        e = game.q('SELECT * FROM banquet_entries WHERE consort_id=?', (self.me,), one=True)
        self.assertEqual(e['buff'], game.DISHES['nangua_geng']['eat']['buff'])
        with patch.object(game.random, 'uniform', return_value=0):
            plain, _ = game.banquet_score(self.me_row(), '琴', 0, 1, 0)
            buffed, _ = game.banquet_score(self.me_row(), '琴', 0, 1, e['buff'])
        self.assertGreater(buffed, plain)

    def test_dish_gift_tribute_and_sell_prices(self):
        game.stock_add(self.me, 'd_babao', 3)
        self.client.post('/garden/gift', data=dict(crop='d_babao', target_id=self.other))
        self.assertEqual(game.relation(self.me, self.other)['affinity'], game.DISHES['babao']['gift'])
        s0 = self.me_row()['silver']
        self.client.post('/garden/tribute', data=dict(crop='d_babao'))
        self.assertEqual(game.stock_of(self.me)['d_babao'], 1)
        self.client.post('/garden/sell', data=dict(crop='d_babao'))
        self.assertEqual(self.me_row()['silver'], s0 + game.DISHES['babao']['sell'])

    def test_tribute_same_item_blocked_for_three_days(self):
        game.stock_add(self.me, 'baicai', 5)
        game.stock_add(self.me, 'luobo', 5)
        self.client.post('/garden/tribute', data=dict(crop='baicai'))
        for day, crop, expect in ((11, 'baicai', 4), (12, 'baicai', 4), (13, 'luobo', 4), (14, 'baicai', 3)):
            game.run('UPDATE game_state SET day=?', (day,))
            self.client.post('/garden/tribute', data=dict(crop=crop))
            self.assertEqual(game.stock_of(self.me)['baicai'], expect, f'第 {day} 天进献{crop}')

    def test_tribute_favor_fades_with_consecutive_days(self):
        self.assertEqual(game.tribute_factor(self.me), 1)
        for day in (6, 7, 8):
            game.run('INSERT INTO daily_counters (consort_id, key, day, count) VALUES (?,?,?,1)', (self.me, 'g_tribute', day))
        game.run('UPDATE game_state SET day=9')
        self.assertAlmostEqual(game.tribute_factor(self.me), 0.4)
        for day in (4, 5):
            game.run('INSERT INTO daily_counters (consort_id, key, day, count) VALUES (?,?,?,1)', (self.me, 'g_tribute', day))
        self.assertAlmostEqual(game.tribute_factor(self.me), game.TRIBUTE_FATIGUE_FLOOR, msg='最低 4 折')
        game.run('UPDATE game_state SET day=20')
        self.assertEqual(game.tribute_factor(self.me), 1, '隔了好几天就恢复')

    def test_sell_all_keeps_dishes(self):
        game.stock_add(self.me, 'qingcai', 2)
        game.stock_add(self.me, 'd_babao', 1)
        self.client.post('/garden/sell', data=dict(crop='all'))
        self.assertEqual(game.stock_of(self.me), {'d_babao': 1})

    def test_garden_page_with_dishes_renders(self):
        game.stock_add(self.me, 'd_babao', 1)
        self.assertEqual(self.client.get('/garden').status_code, 200)


class DuetGearTests(Base):
    def enter(self, cid, piece='琴|0'):
        self.login(cid)
        self.client.post('/banquet/enter', data=dict(piece=piece))

    def entry(self, cid):
        return game.q('SELECT * FROM banquet_entries WHERE consort_id=?', (cid,), one=True)

    def test_invite_needs_own_entry_and_accept_links_both(self):
        self.client.post('/banquet/invite', data=dict(target_id=self.other))
        self.assertIsNone(game.q('SELECT 1 FROM banquet_invites', one=True), '自己没报节目不能邀人')
        self.enter(self.me)
        self.client.post('/banquet/invite', data=dict(target_id=self.other))
        inv = game.q('SELECT * FROM banquet_invites', one=True)
        self.login(self.other)
        e0 = game.get_consort(self.other)['energy']
        self.client.post(f"/banquet/accept/{inv['id']}", data=dict(piece='舞|0'))
        self.assertEqual(game.get_consort(self.other)['energy'], e0 - game.BANQUET_ENERGY, '对方答应时同时报节目')
        self.assertEqual(self.entry(self.me)['partner_id'], self.other)
        self.assertEqual(self.entry(self.other)['partner_id'], self.me)

    @patch.object(game, 'check_achievements', return_value=[])   # 成就赏银会改银子数，这里只看本身的奖励
    def test_duet_shares_place_pays_each_and_raises_affinity(self, _ach):
        self.enter(self.me); self.enter(self.other, '舞|0')
        game.run('UPDATE banquet_entries SET partner_id=? WHERE consort_id=?', (self.other, self.me))
        game.run('UPDATE banquet_entries SET partner_id=? WHERE consort_id=?', (self.me, self.other))
        s0 = {i: game.get_consort(i)['silver'] for i in (self.me, self.other)}
        game.run_banquet(game.banquet_date())
        a, b = self.entry(self.me), self.entry(self.other)
        self.assertEqual((a['place'], b['place'], a['score']), (1, 1, b['score']))
        self.assertIn(a['note'].split('；')[0], ('珠联璧合', '合奏时出了岔子，没配合好'))
        for i in (self.me, self.other):
            self.assertEqual(game.get_consort(i)['silver'], s0[i] + game.BANQUET_REWARDS[1][1])
        self.assertEqual(game.relation(self.me, self.other)['affinity'], game.DUET_AFFINITY_AFTER)

    def test_one_sided_link_falls_back_to_solo(self):
        self.enter(self.me); self.enter(self.other, '舞|0')
        game.run('UPDATE banquet_entries SET partner_id=? WHERE consort_id=?', (self.other, self.me))
        game.run_banquet(game.banquet_date())
        self.assertNotEqual(self.entry(self.me)['place'], None)
        self.assertIsNone(game.relation(self.me, self.other), '对方没认，不算合奏')

    def test_decline_and_solo(self):
        self.enter(self.me)
        self.client.post('/banquet/invite', data=dict(target_id=self.other))
        inv = game.q('SELECT * FROM banquet_invites', one=True)
        self.login(self.other)
        self.client.post(f"/banquet/decline/{inv['id']}")
        self.assertEqual(game.q('SELECT status FROM banquet_invites', one=True)['status'], 'declined')

    def test_buy_gear_and_bonus_per_slot_and_art(self):
        game.run('UPDATE consorts SET silver=5000 WHERE id=?', (self.me,))
        for k in ('dress1', 'dress3', 'head2', 'prop_琴_1', 'prop_琴_2', 'prop_舞_2'):
            self.client.post('/banquet/buy', data=dict(gear=k))
        g = game.BANQUET_GEAR
        self.assertEqual(game.gear_bonus(self.me, '琴'), g['dress3']['bonus'] + g['head2']['bonus'] + g['prop_琴_2']['bonus'])
        self.assertEqual(game.gear_bonus(self.me, '书'), g['dress3']['bonus'] + g['head2']['bonus'], '没有对应道具就不加')
        s = game.get_consort(self.me)['silver']
        self.client.post('/banquet/buy', data=dict(gear='dress3'))
        self.assertEqual(game.get_consort(self.me)['silver'], s, '不能重复买')

    def test_cannot_buy_without_silver(self):
        game.run('UPDATE consorts SET silver=1 WHERE id=?', (self.me,))
        self.client.post('/banquet/buy', data=dict(gear='dress1'))
        self.assertEqual(game.gear_owned(self.me), set())

    def test_banquet_page_renders_with_invite_and_gear(self):
        self.enter(self.me)
        self.client.post('/banquet/invite', data=dict(target_id=self.other))
        self.assertEqual(self.client.get('/banquet').status_code, 200)
        self.login(self.other)
        self.assertEqual(self.client.get('/banquet').status_code, 200)


class SchemeStudyTests(Base):
    def test_scheme_study_gain_cost_and_daily_cap(self):
        game.run('UPDATE consorts SET scheme=30 WHERE id=?', (self.me,))
        for _ in range(4): self.client.post('/act/schemestudy')
        c = self.me_row()
        self.assertEqual(c['scheme'], 30 + 2, '一天 2 次，低心计必涨')
        self.assertEqual(c['energy'], 8 - 2)

    def test_chance_falls_with_scheme(self):
        self.assertEqual([game.scheme_study_chance(v) for v in (10, 60, 80, 95)], [1.0, 0.6, 0.35, 0.15])
        game.run('UPDATE consorts SET scheme=95 WHERE id=?', (self.me,))
        with patch.object(game.random, 'random', return_value=0.5):
            self.client.post('/act/schemestudy')
        self.assertEqual(self.me_row()['scheme'], 95)
        self.assertEqual(self.me_row()['energy'], 7, '没悟出来也花精力')

    def test_shows_on_home_page(self):
        self.assertIn('读书习谋', self.client.get('/place/home').get_data(as_text=True))


class AnnouncementAndAdventureTests(Base):
    def test_gazette_lists_expecting_players_with_countdown(self):
        self.assertIn('眼下宫里没有人有喜', self.client.get('/gazette').get_data(as_text=True))
        game.run('UPDATE consorts SET pregnant_since=9, pregnancy_started_ts=? WHERE id=?', (game.now_ts() - 3600, self.me))
        page = self.client.get('/gazette').get_data(as_text=True)
        self.assertIn('待产', page)
        self.assertIn('甲儿', page)
        self.assertIn('小时', page)
        self.assertNotIn('眼下宫里没有人有喜', page)

    def test_birth_gazette_announces_gifts(self):
        game.run('UPDATE consorts SET pregnant_since=?, pregnancy_started_ts=0 WHERE id=?', (game.cur_day() - game.PREGNANCY_DAYS, self.me))
        with patch.object(game.random, 'random', return_value=0.99):
            game.resolve_births(game.cur_day())
        txt = [r['text'] for r in game.q("SELECT text FROM gazette WHERE kind='birth'")]
        self.assertTrue(any('诞下' in x and '资质：学问' in x for x in txt), txt)

    def test_adventures_start_scenes_and_resolve(self):
        for key in game.ADVENTURE_GARDEN + game.ADVENTURE_ROAD:
            game.start_scene(self.me, key)
            page = self.client.get('/scene')
            self.assertEqual(page.status_code, 200, key)
            for i in range(len(game.SCENES[key]['opts'])):
                game.start_scene(self.me, key)
                self.client.post('/scene', data=dict(opt=i))
                self.assertFalse(game.get_scene(self.me_row()), (key, i))

    def test_garden_can_roll_an_adventure(self):
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.me,))
        with patch.object(game.random, 'choices', return_value=['adventure']), patch.object(game.random, 'choice', side_effect=lambda x: x[0]):
            self.client.post('/act/garden')
        self.assertEqual(game.get_scene(self.me_row())['key'], game.ADVENTURE_GARDEN[0])


class AchievementRankingTests(Base):
    def test_pages_render(self):
        for route in ('/achievements', '/rankings'):
            self.assertEqual(self.client.get(route).status_code, 200, route)

    def test_award_once_with_silver_and_message(self):
        game.daily_inc(self.me, 'g_harvest', 1)
        s0 = self.me_row()['silver']
        got = game.check_achievements(self.me)
        self.assertIn('g_first', got)
        self.assertEqual(self.me_row()['silver'], s0 + game.ACH_BY_KEY['g_first']['silver'])
        self.assertEqual(game.check_achievements(self.me), [], '只发一次')
        self.assertTrue(any('初试锄头' in m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (self.me,))))

    def test_progress_tracks_banquet_wins_arts_and_scheme(self):
        game.run("INSERT INTO banquet_entries (banquet_date, consort_id, art, piece, place, score) VALUES ('2026-01-01',?,'琴','x',1,9)", (self.me,))
        game.run("UPDATE consorts SET arts=?, scheme=71 WHERE id=?", ('{"琴": 16, "棋": 6, "书": 6, "画": 6}', self.me))
        got = set(game.check_achievements(self.me))
        self.assertTrue({'b_first', 'b_win', 'a_master', 'a_grand', 'a_all', 'schemer'} <= got, got)
        self.assertNotIn('b_win3', got)

    def test_badge_needs_ownership_and_can_be_removed(self):
        self.client.post('/achievements/badge', data=dict(key='b_win'))
        self.assertEqual(self.me_row()['badge'], '')
        game.daily_inc(self.me, 'g_harvest', 1)
        game.check_achievements(self.me)
        self.client.post('/achievements/badge', data=dict(key='g_first'))
        self.assertEqual(game.badge_name(self.me_row()), '初试锄头')
        self.assertIn('初试锄头', self.client.get('/gazette').get_data(as_text=True))
        self.client.post('/achievements/badge', data=dict(key=''))
        self.assertEqual(self.me_row()['badge'], '')

    def test_boards_sort_and_exclude_zero(self):
        game.run('UPDATE consorts SET silver=9000 WHERE id=?', (self.me,))
        game.run("UPDATE consorts SET arts=? WHERE id=?", ('{"琴": 3, "棋": 4}', self.other))
        boards = {b['title']: b for b in game.rankings_boards()}
        self.assertNotIn('财富榜', boards)      # 财富榜、心计榜已隐藏
        self.assertNotIn('心计榜', boards)
        self.assertEqual([r['c']['id'] for r in boards['才艺榜']['rows']], [self.other])
        self.assertEqual(boards['种菜榜']['rows'], [])

    def test_adventure_counter_feeds_achievement(self):
        for _ in range(5):
            game.start_scene(self.me, 'adv_lost_maid')
            self.client.post('/scene', data=dict(opt=2))
        self.assertEqual(game.total_count(self.me, 'adventure'), 5)
        self.assertIn('adv5', game.check_achievements(self.me))

    def test_settle_sweep_awards_everyone(self):
        game.daily_inc(self.other, 'g_harvest', 1)
        for r in game._player_rows(): game.check_achievements(r['id'])
        self.assertIn('g_first', game.achievements_owned(self.other))


class NavTabsTests(Base):
    def test_leisure_and_affairs_tabs_on_each_page(self):
        for route, tabs in (('/hobby', ('菜园', '宴会')), ('/garden', ('暇趣', '宴会')), ('/banquet', ('暇趣', '菜园')),
                            ('/quests', ('成就', '榜单')), ('/achievements', ('差事', '榜单')), ('/rankings', ('差事', '成就'))):
            page = self.client.get(route).get_data(as_text=True)
            self.assertIn('class="subtabs"', page, route)
            for t in tabs: self.assertIn(f'>{t}</a>', page, (route, t))

    def test_top_nav_has_one_affairs_entry_not_five(self):
        page = self.client.get('/garden').get_data(as_text=True)
        start = page.index('class="halls halls-sub"')
        nav = page[start:page.index('</nav>', start)]
        self.assertIn('>事务</a>', nav)
        for gone in ('>菜园</a>', '>宴会</a>', '>差事</a>', '>成就</a>', '>榜单</a>'):
            self.assertNotIn(gone, nav)


class FizzleInfluenceTests(Base):
    def test_fizzle_gives_quarter_influence_once_per_target_day(self):
        it = dict(attacker_id=self.me, target_id=self.other, method='rumor', drug='')
        i0 = self.me_row()['influence']
        game.gain_intrigue_influence(it, game.FIZZLE_INFLUENCE_FRACTION)
        self.assertEqual(self.me_row()['influence'], i0 + max(1, round(game.INFLUENCE_GAINS['rumor'] * 0.25)))
        game.gain_intrigue_influence(it)
        self.assertEqual(self.me_row()['influence'], i0 + max(1, round(game.INFLUENCE_GAINS['rumor'] * 0.25)), '同日同一人不重复')

    def test_resolve_fizzle_gives_partial_but_caught_gives_none(self):
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.me,))
        for caught, expect in ((False, True), (True, False)):
            game.run('UPDATE consorts SET influence=0 WHERE id=?', (self.me,))
            game.run("DELETE FROM daily_counters WHERE key LIKE 'influence_target:%'")
            iid = game.run("INSERT INTO intrigues (day, attacker_id, target_id, method, silver_paid, created_ts) VALUES (?,?,?,'steal',60,0)",
                           (game.cur_day(), self.me, self.other)).lastrowid
            it = game.q('SELECT * FROM intrigues WHERE id=?', (iid,), one=True)
            with patch.object(game.random, 'random', side_effect=[0.99, 0.0 if caught else 0.99]):
                game.resolve_intrigue(it, bed_id=self.other)
            self.assertEqual(game.get_consort(self.me)['influence'] > 0, expect, f'caught={caught}')


if __name__ == '__main__':
    unittest.main()
