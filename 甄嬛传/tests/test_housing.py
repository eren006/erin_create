"""住处分配、迁居、同宫牵连和页面的回归测试。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HousingTests(unittest.TestCase):
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        game.DB_PATH = str(Path(self.temp.name) / 'housing.db')
        game.app.config['TESTING'] = True
        game.init_db()
        self.ctx = game.app.app_context()
        self.ctx.push()
        game.run('UPDATE game_state SET day=10')
        self.client = game.app.test_client()

    def tearDown(self):
        self.ctx.pop()
        self.temp.cleanup()

    def housed(self, name, rank=4, palace='永寿宫', hall='east'):
        cid = self.player(name, rank)
        game.run('UPDATE consorts SET palace=?,hall=? WHERE id=?', (palace, hall, cid))
        return cid

    def npc(self, key):
        return game.q('SELECT * FROM consorts WHERE npc_key=?', (key,), one=True)

    def fill_mains(self):
        ids = []
        for name in game.PALACES:
            if not game.q("SELECT 1 FROM consorts WHERE palace=? AND hall='main' AND status IN ('normal','confined')", (name,), one=True):
                ids.append(self.housed('主'+str(len(ids)), game.MAIN_HALL_MIN_RANK, name, 'main'))
        return ids

    def snapshot(self):
        return {t: [tuple(r) for r in game.q(f'SELECT * FROM {t} ORDER BY id')]
                for t in ('consorts','messages','gazette')}

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_initial_palaces_npcs_and_seven_free_mains(self):
        self.assertEqual(len(game.PALACES), 15)
        self.assertNotIn('承乾宫', game.PALACES)
        self.assertEqual(len([p for p in game.PALACES.values() if p['group']=='东六宫']), 5)
        self.assertEqual(self.npc('caoguiren')['hall'], 'east')
        self.assertEqual(self.npc('xinchangzai')['hall'], 'east')
        occupied = game.q("SELECT COUNT(*) FROM consorts WHERE hall='main'", one=True)[0]
        self.assertEqual(len(game.PALACES)-occupied, 7)
        self.assertFalse(game.q('SELECT * FROM messages'))

    # ── 争正殿 ───────────────────────────────────────────────────────────────

    def contenders(self, mine=300, theirs=100, my_rank=game.MAIN_HALL_MIN_RANK, their_rank=game.MAIN_HALL_MIN_RANK):
        holder = self.housed('正殿', their_rank, '翊坤宫', 'main')
        rival = self.housed('后来', my_rank, '永寿宫', 'west')
        game.run('UPDATE consorts SET favor=?, energy=10, silver=500 WHERE id=?', (mine, rival))
        game.run('UPDATE consorts SET favor=? WHERE id=?', (theirs, holder))
        return rival, holder

    def contend(self, rival, holder):
        self.login(rival)
        return self.client.post('/contend', data=dict(target_id=holder))

    def where(self, cid):
        c = game.get_consort(cid)
        return c['palace'], c['hall']

    def test_higher_favor_takes_the_main_hall_and_swaps_rooms(self):
        rival, holder = self.contenders(300, 100)
        with patch.object(game.random, 'uniform', return_value=1.0):
            self.contend(rival, holder)
        self.assertEqual(self.where(rival), ('翊坤宫', 'main'))
        self.assertEqual(self.where(holder), ('永寿宫', 'west'))
        c = game.get_consort(rival)
        self.assertEqual((c['energy'], c['silver']), (10 - game.CONTEND_ENERGY, 500 - game.CONTEND_SILVER))
        self.assertEqual(game.get_consort(holder)['housing_waiting'], 'main')

    def test_losing_costs_favor_and_changes_no_rooms(self):
        rival, holder = self.contenders(100, 300)
        with patch.object(game.random, 'uniform', return_value=1.0):
            self.contend(rival, holder)
        self.assertEqual(self.where(rival), ('永寿宫', 'west'))
        self.assertEqual(self.where(holder), ('翊坤宫', 'main'))
        self.assertEqual(game.get_consort(rival)['favor'], 100 - game.FAVOR_LOSS['contend_lose'])

    def test_once_a_day_and_new_holder_is_guarded(self):
        rival, holder = self.contenders(300, 100)
        with patch.object(game.random, 'uniform', return_value=1.0):
            self.contend(rival, holder)
            before = self.where(holder)
            self.contend(holder, rival)          # 被挤的人想马上争回来：刚坐稳，不行
        self.assertEqual(self.where(holder), before)
        self.assertEqual(self.where(rival), ('翊坤宫', 'main'))

    def test_cannot_contend_against_higher_rank_pregnant_or_when_already_main(self):
        rival, holder = self.contenders(300, 100, my_rank=game.MAIN_HALL_MIN_RANK, their_rank=game.MAIN_HALL_MIN_RANK + 1)
        self.assertIn('位分', game.contend_error(game.get_consort(rival), game.get_consort(holder)))
        game.run('UPDATE consorts SET rank=? WHERE id=?', (game.MAIN_HALL_MIN_RANK, holder))
        game.run('UPDATE consorts SET pregnant_since=1 WHERE id=?', (holder,))
        self.assertIn('有孕', game.contend_error(game.get_consort(rival), game.get_consort(holder)))
        game.run('UPDATE consorts SET pregnant_since=0 WHERE id=?', (holder,))
        self.assertIsNone(game.contend_error(game.get_consort(rival), game.get_consort(holder)))
        self.assertIsNotNone(game.contend_error(game.get_consort(holder), game.get_consort(rival)), '已经住正殿的不能争')
        low = self.housed('贵人', 4, '储秀宫', 'east')
        self.assertIsNotNone(game.contend_error(game.get_consort(low), game.get_consort(holder)), '没到嫔位不能争')

    def test_home_page_lists_contend_targets_only_for_waiting_pins(self):
        rival, holder = self.contenders()
        self.login(rival)
        page = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('争正殿', page)
        self.login(holder)
        self.assertNotIn('争正殿', self.client.get('/place/home').get_data(as_text=True))

    def test_entry_random_annex_in_npc_palace_and_decree(self):
        cid = self.player('新')
        game.run("UPDATE consorts SET status='xiunv',rank=0 WHERE id=?", (cid,))
        self.login(cid)
        questions = game.dianxuan_questions_for(cid)
        # Questions are not risky; the only random.choice is the room selection.
        data = {q['key']: next(i for i,o in enumerate(q['opts']) if not o.get('risky')) for q in questions}
        with patch.object(game.random, 'choice', return_value=('翊坤宫','east')), patch.object(game.random, 'random', return_value=.99):
            response = self.client.post('/dianxuan', data=data)
        c = game.get_consort(cid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((c['palace'], c['hall']), ('翊坤宫','east'))
        self.assertIn('翊坤宫·东配殿', response.get_data(as_text=True))
        self.assertIn('赐居翊坤宫东配殿', game.q('SELECT text FROM gazette ORDER BY id DESC', one=True)[0])

    def test_annex_before_back_and_full_capacity_no_crash(self):
        for palace in game.PALACES:
            for hall in ('east','west'):
                if not game.q('SELECT 1 FROM consorts WHERE palace=? AND hall=?',(palace,hall),one=True):
                    self.housed(f'{palace}{hall}',1,palace,hall)
        room = game.empty_residence((('east','west'),('back',)))
        self.assertEqual(room[1], 'back')
        for palace in game.PALACES: self.housed(palace+'后',1,palace,'back')
        cid = self.player('待安置',1)
        game.housing_sync()
        self.assertEqual(game.get_consort(cid)['hall'], '')
        self.assertEqual(game.get_consort(cid)['housing_waiting'], 'side')
        before = self.snapshot(); game.housing_sync(); self.assertEqual(before,self.snapshot())
        with patch.object(game,'npc_schemes'), patch.object(game.random,'random',return_value=.99):
            game.settle_day()
        self.assertEqual(game.cur_day(),11)
        # A new selection waits rather than overbooking a room.
        newcomer = self.player('满宫秀女',1)
        game.run("UPDATE consorts SET status='xiunv' WHERE id=?",(newcomer,))
        self.login(newcomer)
        qs=game.dianxuan_questions_for(newcomer)
        self.client.post('/dianxuan',data={q['key']:0 for q in qs})
        self.assertEqual(game.get_consort(newcomer)['status'],'xiunv')

    def test_promote_to_main_and_idempotence(self):
        cid = self.housed('晋封')
        game.set_rank(cid,game.MAIN_HALL_MIN_RANK)
        self.assertEqual(game.get_consort(cid)['hall'],'main')
        self.assertIn('为一宫主位',game.q('SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC',(cid,),one=True)[0])
        before=self.snapshot(); game.housing_sync(); game.housing_sync()
        self.assertEqual(before,self.snapshot())

    def test_wait_notice_once_then_rank_and_favor_priority(self):
        heads=self.fill_mains()
        low=self.housed('低位',game.MAIN_HALL_MIN_RANK,'碎玉轩','east')
        higher=self.housed('高位',game.MAIN_HALL_MIN_RANK+1,'碎玉轩','west')
        favored=self.housed('同位高宠',game.MAIN_HALL_MIN_RANK+1,'碎玉轩','back')
        game.run('UPDATE consorts SET favor=900 WHERE id=?',(low,))
        game.run('UPDATE consorts SET favor=20 WHERE id=?',(favored,))
        game.housing_sync()
        count=game.q('SELECT COUNT(*) FROM messages WHERE consort_id=?',(low,),one=True)[0]
        for _ in range(2): game.housing_sync()
        self.assertEqual(game.q('SELECT COUNT(*) FROM messages WHERE consort_id=?',(low,),one=True)[0],count)
        game.send_to_cold(heads[0])
        self.assertEqual(game.get_consort(favored)['hall'],'main')
        self.assertNotEqual(game.get_consort(higher)['hall'],'main')
        game.die(heads[1],'测试')
        self.assertEqual(game.get_consort(higher)['hall'],'main')
        self.assertNotEqual(game.get_consort(low)['hall'],'main')

    def test_demote_prefers_same_palace_and_then_other_annex(self):
        cid=self.housed('降位',game.MAIN_HALL_MIN_RANK,'永寿宫','main')
        self.housed('东邻',2,'永寿宫','east')
        game.set_rank(cid,4)
        self.assertEqual((game.get_consort(cid)['palace'],game.get_consort(cid)['hall']),('永寿宫','west'))
        # A filled original palace forces a move elsewhere.
        game.run("UPDATE consorts SET rank=?,hall='main' WHERE id=?",(game.MAIN_HALL_MIN_RANK,cid))
        self.housed('西邻',2,'永寿宫','west'); self.housed('后邻',2,'永寿宫','back')
        game.set_rank(cid,4)
        self.assertNotEqual(game.get_consort(cid)['palace'],'永寿宫')
        self.assertIn(game.get_consort(cid)['hall'],('east','west'))

    def test_cold_release_and_death_clear_hall(self):
        cid=self.housed('冷宫',game.MAIN_HALL_MIN_RANK,'永寿宫','main')
        game.send_to_cold(cid)
        self.assertEqual(game.get_consort(cid)['hall'],'')
        game.release_from_cold(cid,'')
        self.assertIn(game.get_consort(cid)['hall'],('east','west'))
        game.die(cid,'测试')
        self.assertEqual(game.get_consort(cid)['hall'],'')
        game.housing_sync()
        self.assertEqual(game.get_consort(cid)['hall'],'')

    def test_admin_rank_status_edits_rehouse(self):
        cid=self.housed('后改')
        with self.client.session_transaction() as session: session['admin']=True
        for rank,status,halls in [(game.MAIN_HALL_MIN_RANK,'normal',('main',)),(4,'normal',('east','west','back')),(4,'cold',('',)),(4,'normal',('east','west','back'))]:
            response=self.client.post(f'/admin/edit/{cid}',data=dict(rank=rank,status=status,favor=0,silver=500))
            self.assertEqual(response.status_code,302)
            self.assertIn(game.get_consort(cid)['hall'],halls)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_sync_repairs_legacy_duplicates_and_keeps_npc_rooms(self):
        cid=self.housed('撞房',4,'启祥宫','east')
        orphan=self.player('旧档',3)
        game.run("UPDATE consorts SET palace='旧宫名',hall='unknown' WHERE id=?",(orphan,))
        game.housing_sync()
        self.assertEqual(self.npc('caoguiren')['hall'],'east')
        self.assertNotEqual((game.get_consort(cid)['palace'],game.get_consort(cid)['hall']),('启祥宫','east'))
        self.assertTrue(game.has_residence(game.get_consort(orphan)))
        rooms=[(c['palace'],c['hall']) for c in game.q("SELECT * FROM consorts WHERE hall!=''")]
        self.assertEqual(len(rooms),len(set(rooms)))
        game.init_db()   # 头一次 init_db 会给老档补家族和辈分，先跑一遍再比
        before=self.snapshot(); game.init_db(); game.housing_sync()
        self.assertEqual(before,self.snapshot())

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_visit_player_or_npc_main_and_exclusions(self):
        head=self.housed('主位',game.MAIN_HALL_MIN_RANK,'永寿宫','main')
        side=self.housed('同宫',2,'永寿宫','east')
        other=self.housed('别宫',2,'碎玉轩','east')
        game.run("UPDATE consorts SET personality='gentle' WHERE id=?",(side,))
        with patch.object(game.random,'random',return_value=0): game.housing_visit(game.get_consort(head))
        self.assertEqual(game.get_consort(side)['favor'],10)
        self.assertEqual(game.get_consort(other)['favor'],0)
        for changes in ("health=24", "health=70,poisoned_day=9", "poisoned_day=0,pregnant_since=9", "pregnant_since=0,status='confined'"):
            game.run(f'UPDATE consorts SET {changes} WHERE id=?',(side,))
            with patch.object(game.random,'random',return_value=0): game.housing_visit(game.get_consort(head))
        self.assertEqual(game.get_consort(side)['favor'],10)
        game.run("UPDATE consorts SET status='normal',palace='翊坤宫' WHERE id=?",(side,))
        with patch.object(game.random,'random',return_value=0): game.housing_visit(self.npc('huafei'))
        self.assertEqual(game.get_consort(side)['favor'],20)
        # A consort in an annex receiving the emperor brings no shared bonus.
        with patch.object(game.random,'random',return_value=0): game.housing_visit(game.get_consort(side))
        self.assertEqual(game.get_consort(side)['favor'],20)

    def test_reports_reuse_daily_counters_without_private_contents(self):
        head=self.housed('主位',game.MAIN_HALL_MIN_RANK,'永寿宫','main')
        side=self.housed('写信',2,'永寿宫','east')
        quiet=self.housed('静居',2,'永寿宫','west')
        elsewhere=self.housed('别宫',2,'碎玉轩','east')
        game.daily_inc(side,'letter',2); game.daily_inc(side,'study'); game.daily_inc(side,'bribe:1')
        game.daily_inc(elsewhere,'garden')
        game.run('UPDATE consorts SET scheme=37, silver=123 WHERE id=?',(side,))
        with patch.object(game.random,'randint',return_value=2): game.housing_reports(10)
        messages=game.q('SELECT * FROM messages WHERE consort_id=?',(head,))
        self.assertEqual(len(messages),1)
        text=messages[0]['text']
        self.assertIn('心计 37',text); self.assertIn('手头 123 两',text); self.assertIn('静居',text)
        self.assertNotIn('写了信',text); self.assertNotIn('别宫',text); self.assertNotIn('bribe',text)
        game.run('DELETE FROM messages WHERE consort_id=?',(head,))
        with patch.object(game.random,'randint',return_value=1): game.housing_reports(10)
        self.assertEqual(game.q('SELECT text FROM messages WHERE consort_id=?',(head,))[0]['text'].count('心计'),1)
        self.assertFalse(game.q('SELECT m.* FROM messages m JOIN consorts c ON c.id=m.consort_id WHERE c.user_id IS NULL'))

    def test_same_palace_frame_bonus_only(self):
        a=self.housed('攻',4,'永寿宫','east'); b=self.housed('守',4,'永寿宫','west')
        ca,cb=game.get_consort(a),game.get_consort(b)
        same=game.intrigue_success_p(ca,cb,game.INTRIGUES['frame'])
        rumor=game.intrigue_success_p(ca,cb,game.INTRIGUES['rumor'])
        game.run("UPDATE consorts SET palace='碎玉轩' WHERE id=?",(b,))
        self.assertAlmostEqual(same-game.intrigue_success_p(ca,game.get_consort(b),game.INTRIGUES['frame']),.10)
        self.assertEqual(rumor,game.intrigue_success_p(ca,game.get_consort(b),game.INTRIGUES['rumor']))

    def test_same_palace_self_drug_has_no_penalty(self):
        a=self.housed('下药',4,'永寿宫','east'); b=self.housed('受药',4,'永寿宫','west')
        self.login(a)
        game.run("UPDATE consorts SET scheme=50,trust=0,virtue=50 WHERE id IN (?,?)",(a,b))
        for palace,expected in [('碎玉轩','caught'),('永寿宫','success')]:
            game.run('UPDATE consorts SET palace=?,drugged_day=0 WHERE id=?',(palace,b))
            game.run("DELETE FROM daily_counters WHERE key='intrigue'")
            game.inv_add(a,'yanzhi')
            with patch.object(game.random,'random',return_value=.45):      # 自己动手 .42 → 失败；同宫 .50 → 成功（提交时就会实时结算，所以提交也要固定掷骰）
                self.client.post('/intrigue/submit',data=dict(method='drug',drug='yanzhi',target_id=b))
                it=game.q('SELECT * FROM intrigues ORDER BY id DESC',one=True)
                self.assertEqual(game.resolve_drug(it)[0],expected)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_discipline_shared_cooldown_pregnancy_and_authorization(self):
        head=self.housed('主位',game.MAIN_HALL_MIN_RANK,'永寿宫','main'); side=self.housed('配殿',2,'永寿宫','east')
        outsider=self.housed('别宫',2,'碎玉轩','east')
        self.login(head)
        post=lambda cid,action: self.client.post(f'/housing/discipline/{cid}',data={'action':action})
        for tid in (head,outsider,self.npc('caoguiren')['id'],999999): post(tid,'kneel')
        self.assertEqual(game.get_consort(head)['discipline_ready_day'],0)
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(side,))
        post(side,'kneel')
        self.assertEqual(game.get_consort(head)['discipline_ready_day'],0)
        post(side,'reward'); post(side,'kneel')
        self.assertEqual(game.get_consort(head)['discipline_ready_day'],13)
        self.assertEqual(game.relation(head,side)['affinity'],5)
        self.assertEqual(game.get_consort(side)['health'],70)
        game.run('UPDATE game_state SET day=13')
        game.run("UPDATE consorts SET pregnant_since=0,status='confined' WHERE id=?",(side,))
        post(side,'kneel'); post(side,'reward')
        self.assertEqual(game.get_consort(side)['health'],62)
        self.assertEqual(game.relation(head,side)['affinity'],0)
        self.assertEqual(game.get_consort(head)['discipline_ready_day'],16)
        self.assertIn(game.display_name(game.get_consort(head)),game.q('SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC',(side,),one=True)[0])
        self.login(side); post(head,'reward')
        self.assertEqual(game.get_consort(side)['discipline_ready_day'],0)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_npc_discipline_chance_cooldown_and_target_guards(self):
        punished=self.housed('受罚',2,'翊坤宫','east')
        pregnant=self.housed('有孕',2,'翊坤宫','west')
        liked=self.housed('相好',2,'翊坤宫','back')
        rewarded=self.housed('受赏',2,'景仁宫','east')
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(pregnant,))
        game.add_affinity(self.npc('huafei')['id'],liked,1)
        with patch.object(game.random,'random',return_value=.25):
            game.npc_housing_discipline(10); game.npc_housing_discipline(11)
        self.assertEqual(game.get_consort(punished)['health'],62)
        self.assertEqual(game.get_consort(pregnant)['health'],70)
        self.assertEqual(game.get_consort(liked)['health'],70)
        self.assertIsNone(game.relation(self.npc('huanghou')['id'],rewarded))
        with patch.object(game.random,'random',return_value=.19): game.npc_housing_discipline(13)
        self.assertEqual(game.get_consort(punished)['health'],54)
        self.assertEqual(game.relation(self.npc('huanghou')['id'],rewarded)['affinity'],5)
        self.assertFalse(game.q('SELECT m.* FROM messages m JOIN consorts c ON c.id=m.consort_id WHERE c.user_id IS NULL'))

    def test_night_sync_and_atomic_rollback(self):
        cid=self.housed('待晋',game.MAIN_HALL_MIN_RANK-1,'永寿宫','east')
        game.run('UPDATE consorts SET favor=320,virtue=60,influence=200 WHERE id=?',(cid,))
        before=self.snapshot()
        with patch.object(game,'issue_edicts',side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError): game.settle_day()
        self.assertEqual(before,self.snapshot())
        with patch.object(game,'npc_schemes'),patch.object(game.random,'random',return_value=.99): game.settle_day()
        self.assertEqual(game.get_consort(cid)['rank'],game.MAIN_HALL_MIN_RANK)
        self.assertEqual(game.get_consort(cid)['hall'],'main')

    def test_pages_map_and_cooldown_buttons(self):
        head=self.housed('主位',game.MAIN_HALL_MIN_RANK,'永寿宫','main'); side=self.housed('配殿',2,'永寿宫','east')
        self.login(head)
        game.run('UPDATE consorts SET discipline_ready_day=13 WHERE id=?',(head,))
        for path in ('/palaces','/place/home','/','/social'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,path)
        home=self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('永寿宫·正殿',home); self.assertIn('第 13 天',home)
        self.assertIn('value="kneel" class="plain" disabled',home)
        self.login(side)
        self.assertIn('永寿宫·东配殿',self.client.get('/').get_data(as_text=True))
        self.assertNotIn('value="kneel"',self.client.get('/place/home').get_data(as_text=True))
        directory=self.client.get('/palaces').get_data(as_text=True)
        self.assertIn('空着',directory); self.assertIn('东六宫',directory); self.assertIn('独院',directory)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_old_schema_adds_housing_fields(self):
        # Use q/run just as runtime code does; rebuild the old shape in a separate database.
        old = str(Path(self.temp.name)/'older.db')
        original=game.DB_PATH
        game.DB_PATH=old
        with game.app.app_context():
            schema=(fixtures.ROOT/'schema.sql').read_text()
            fields=('hall ', 'discipline_ready_day ', 'housing_waiting ')
            schema='\n'.join(line for line in schema.splitlines() if not line.strip().startswith(fields))
            for statement in schema.split(';'):
                # Existing schema comments contain semicolons: use the known table DDL only.
                pass
        # sqlite3 is used solely to construct the fixture, matching MigrationTests.
        import sqlite3
        with sqlite3.connect(old) as db: db.executescript(schema)
        game.init_db(); game.init_db()
        with game.app.app_context():
            fields={r['name'] for r in game.q('PRAGMA table_info(consorts)')}
            self.assertTrue({'hall','discipline_ready_day','housing_waiting'}<=fields)
            self.assertEqual(game.q("SELECT hall FROM consorts WHERE npc_key='huanghou'",one=True)[0],'main')
        game.DB_PATH=original


class StandaloneCourtyardTests(HousingTests):
    def test_four_standalone_courtyards_each_with_four_rooms(self):
        solo = [n for n, p in game.PALACES.items() if p['group'] == '独院']
        self.assertEqual(len(solo), 4)
        self.assertIn('听雨轩', solo); self.assertIn('栖霞阁', solo)
        for n in ('听雨轩', '栖霞阁'):
            self.assertTrue(game.PALACES[n]['desc'] and game.PALACES[n]['main'])
        self.assertEqual(len(game.PALACES), 15)

    def test_new_courtyard_rooms_can_be_assigned(self):
        cid = self.housed('住新院', 2, '听雨轩', 'east')
        self.assertEqual((game.get_consort(cid)['palace'], game.get_consort(cid)['hall']), ('听雨轩', 'east'))
        self.assertTrue(self.client.get('/palaces').status_code in (200, 302))
