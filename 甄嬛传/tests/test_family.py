"""家族系统：立家、送人入宫、辈分与照拂、家主、家里来求助、联络与生意、家里送钱、夺嫡助力、族谱，见设计文档九点九节

运行：python3 -m unittest discover -s tests -v
"""
import json
import unittest
from unittest.mock import patch
import test_heirs

game = test_heirs.game


class FamilyTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    # ── 夹具 ─────────────────────────────────────────────────────────────────

    def uid(self, cid):
        return game.consort_uid(game.get_consort(cid))

    def fam(self, cid, surname=None, tier='dali', **kw):
        """给这位玩家的账号立家，可以直接改家里的数"""
        uid = self.uid(cid)
        game.create_family(uid, surname or f"甲{uid}", tier)
        for k, v in kw.items():
            game.run(f'UPDATE families SET {k}=? WHERE user_id=?', (v, uid))
        return uid

    def frow(self, uid):
        return game.family_row(uid)

    def new_user(self, name='新人'):
        uid = game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)', (name, 'x')).lastrowid
        with self.client.session_transaction() as sess:
            sess['uid'] = uid
        return uid

    def past_member(self, uid, reign_no=1, given='前人', reason='病逝', peak=5, status='dead', **kw):
        fields = dict(user_id=None, archived_user_id=uid, surname='甲', given=given, rank=peak, status=status, entered_day=1,
                      rank_since_day=1, family='dali', personality='gentle', silver=0, age_months=240, recap_seen_day=1,
                      reign_no=reign_no, death_day=5, death_reason=reason, peak_rank=peak, seq=1)
        fields.update(kw)
        cols = ','.join(fields)
        return game.run(f"INSERT INTO consorts({cols}) VALUES({','.join('?' * len(fields))})", list(fields.values())).lastrowid

    def msgs(self, cid):
        return [m['text'] for m in game.q('SELECT text FROM messages WHERE consort_id=?', (cid,))]

    def set_day(self, d):
        game.run('UPDATE game_state SET day=?', (d,))

    def prince(self, mother, age_years=13, **kw):
        kw.setdefault('title', '')
        return self.heir(mother, gender='皇子', born=game.cur_day() - age_years * game.HEIR_DAYS_PER_YEAR, zhuazhou='book', **kw)

    def create_member(self, given='新', age=20, per='gentle', **extra):
        data = dict(given=given, age=age, personality=per, **{k: 0 for k in game.STAT_KEYS})
        data.update(extra)
        return self.client.post('/create', data=data)

    # ── 立家 ─────────────────────────────────────────────────────────────────

    def test_new_user_sees_family_step_with_three_free_surnames(self):
        self.new_user()
        page = self.client.get('/create').get_data(as_text=True)
        self.assertIn('立家', page)
        self.assertEqual(len(game.suggest_surnames()), 3)
        self.assertFalse(any(game.surname_taken(s) for s in game.suggest_surnames()))

    def test_create_family_sets_head_and_office_by_tier(self):
        uid = self.new_user()
        self.client.post('/create', data={'step': 'family', 'surname': '江', 'family': 'general'})
        f = self.frow(uid)
        self.assertEqual((f['surname'], f['tier'], f['prestige'], f['estate']), ('江', 'general', 0, 0))
        self.assertEqual((f['head_role'], f['head_gen'], f['head_office']), ('父亲', 0, game.TIER_OFFICE['general']))
        self.assertTrue(46 <= f['head_age_months'] // 12 <= 56)
        self.assertTrue(f['head_name'].startswith('江'))

    def test_custom_surname_wins_over_radio(self):
        uid = self.new_user()
        self.client.post('/create', data={'step': 'family', 'surname': '江', 'surname_custom': '欧阳', 'family': 'dali'})
        self.assertEqual(self.frow(uid)['surname'], '欧阳')

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_surname_must_be_free_and_short(self):
        uid = self.new_user()
        other = self.new_user('别人')
        game.create_family(other, '林', 'dali')
        for bad in ('西林觉罗', '富察', '马佳', '林', '欧阳欧', ''):
            self.client.post('/create', data={'step': 'family', 'surname': bad, 'family': 'dali'})
        with self.client.session_transaction() as sess: sess['uid'] = uid
        self.assertIsNone(self.frow(uid))
        for bad in ('西林觉罗', '富察', '林'):
            self.assertTrue(game.surname_taken(bad))

    def test_blocked_word_surname_rejected(self):
        uid = self.new_user()
        with patch.object(game, 'blocked_hit', return_value='某词'):
            self.client.post('/create', data={'step': 'family', 'surname': '江', 'family': 'dali'})
        self.assertIsNone(self.frow(uid))

    def test_family_choice_is_permanent(self):
        uid = self.new_user()
        self.client.post('/create', data={'step': 'family', 'surname': '江', 'family': 'dali'})
        self.client.post('/create', data={'step': 'family', 'surname': '沈', 'family': 'merchant'})
        f = self.frow(uid)
        self.assertEqual((f['surname'], f['tier']), ('江', 'dali'))

    # ── 送人入宫 ─────────────────────────────────────────────────────────────

    def enter_palace(self, uid):
        cid = game.q("SELECT id FROM consorts WHERE user_id=? AND status='xiunv'", (uid,), one=True)['id']
        qs = game.dianxuan_questions_for(cid)
        with patch.object(game.random, 'randint', return_value=0):
            self.client.post('/dianxuan', data={q['key']: 0 for q in qs})
        return cid

    def test_first_member_takes_family_surname_and_is_eldest(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.create_member('云')
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        self.assertEqual((c['surname'], c['given'], c['family'], c['seq'], c['reign_no'], c['entry_age'], c['lineage']),
                         ('江', '云', 'dali', 1, 1, 20, '长女'))
        self.assertEqual(c['age_months'], 240)
        self.assertEqual(c['silver'], game.FAMILIES['dali']['silver'])

    def test_member_cannot_dodge_name_or_age_rules(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.create_member('云', age=17)
        self.create_member('云', per='nope')
        self.assertFalse(game.q('SELECT 1 FROM consorts WHERE user_id=?', (uid,), one=True))
        game.run("INSERT INTO consorts(surname,given,rank,status,entered_day,rank_since_day,family,personality,silver,age_months,recap_seen_day) VALUES('江','云',4,'normal',1,1,'dali','gentle',1,240,1)")
        self.create_member('云')
        self.assertFalse(game.q('SELECT 1 FROM consorts WHERE user_id=?', (uid,), one=True), '同名的不行')

    def test_prestige_adds_start_silver_and_dianxuan_bonus(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        game.run('UPDATE families SET prestige=70 WHERE user_id=?', (uid,))
        self.create_member('云')
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        self.assertEqual(c['silver'], game.FAMILIES['dali']['silver'] + 70)
        self.assertEqual(game.family_dx_bonus(self.frow(uid), ''), 3)
        game.run('UPDATE families SET prestige=999 WHERE user_id=?', (uid,))
        self.assertEqual(game.family_dx_bonus(self.frow(uid), ''), game.PRESTIGE_DX_MAX)
        self.assertEqual(game.family_dx_bonus(self.frow(uid), 'dowager'), game.PRESTIGE_DX_MAX + game.DOWAGER_DX_BONUS)

    def test_start_silver_from_prestige_is_capped(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        game.run('UPDATE families SET prestige=500 WHERE user_id=?', (uid,))
        self.create_member('云')
        self.assertEqual(game.q('SELECT silver FROM consorts WHERE user_id=?', (uid,), one=True)['silver'],
                         game.FAMILIES['dali']['silver'] + game.PRESTIGE_SILVER_MAX)

    def test_gate_blocks_fifth_daughter_and_mourning(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.set_day(20)
        for i in range(3):
            self.past_member(uid, given=f'前{i}', death_day=1)
        self.assertEqual(game.family_gate(uid), (True, ''))
        self.past_member(uid, given='前3', death_day=19)
        ok, why = game.family_gate(uid)
        self.assertFalse(ok)
        self.assertIn('门庭凋零', why)
        self.assertEqual(self.client.get('/create').status_code, 302)

    def test_gate_mourning_period(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.set_day(19)
        self.past_member(uid, death_day=19)
        self.assertFalse(game.family_gate(uid)[0], '死的当天不行')
        self.set_day(19 + game.FAMILY_MOURN_DAYS)
        self.assertTrue(game.family_gate(uid)[0], '治丧期满就能送下一位')

    def test_gate_counts_only_this_reign(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        for i in range(4): self.past_member(uid, reign_no=1, given=f'旧{i}')
        game.run('UPDATE game_state SET reign_no=2')
        self.assertTrue(game.family_gate(uid)[0], '换了一届，人数清零')

    # ── 辈分、上一辈的照拂 ───────────────────────────────────────────────────

    def test_lineage_among_sisters(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        inh = game.family_inheritance(uid, 1)
        self.assertEqual(game.make_lineage([], inh), '长女')
        a = game.get_consort(self.past_member(uid, given='云'))
        self.assertEqual(game.make_lineage([a], inh), '云之妹')
        b = game.get_consort(self.past_member(uid, given='霜'))
        self.assertEqual(game.make_lineage([a, b], inh), '霜的堂妹')

    def test_next_reign_is_niece_of_the_most_honoured(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, given='平常', reason='先帝驾崩，迁居寿康宫，安享晚年', peak=7)
        self.past_member(uid, given='太后', reason='先帝驾崩，圣母皇太后', peak=5)
        self.past_member(uid, given='妃子', reason='先帝驾崩，太妃', peak=6)
        game.run('UPDATE game_state SET reign_no=2')
        inh = game.family_inheritance(uid, 2)
        self.assertEqual((inh['patron'], inh['depth'], inh['relative']['given']), ('dowager', 1, '太后'))
        self.assertEqual(game.make_lineage([], inh), '前朝太后甲太后之侄女'.replace('甲', '甲'))

    def test_patron_kinds_by_previous_fate(self):
        for reason, patron in (('先帝驾崩，太妃', 'concubine'), ('先帝驾崩，皇贵太妃', 'concubine'),
                               ('先帝驾崩，押错了阿哥，新帝记了一笔', 'disgraced'),
                               ('先帝驾崩，所抚养的阿哥被圈禁，失势', 'disgraced'),
                               ('先帝驾崩，迁居寿康宫，安享晚年', ''), ('中毒身亡', '')):
            uid = self.new_user(f'u{patron}{reason[:6]}')
            game.create_family(uid, f's{uid}', 'dali')
            self.past_member(uid, reason=reason)
            game.run('UPDATE game_state SET reign_no=2')
            self.assertEqual(game.family_inheritance(uid, 2)['patron'], patron, reason)
            game.run('UPDATE game_state SET reign_no=1')

    def test_two_reigns_later_is_grand_niece_without_patron(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, reign_no=1, given='太后', reason='先帝驾崩，圣母皇太后')
        game.run('UPDATE game_state SET reign_no=3')
        inh = game.family_inheritance(uid, 3)
        self.assertEqual((inh['patron'], inh['depth']), ('', 2))
        self.assertIn('侄孙女', game.make_lineage([], inh))
        game.run('UPDATE game_state SET reign_no=5')
        self.assertIn('族中晚辈', game.make_lineage([], game.family_inheritance(uid, 5)))

    def test_new_reign_member_gets_lineage_and_patron_on_creation(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, given='太后', reason='先帝驾崩，圣母皇太后')
        game.run('UPDATE game_state SET reign_no=2')
        self.create_member('云')
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        self.assertEqual((c['patron'], c['reign_no'], c['seq']), ('dowager', 2, 1))
        self.assertIn('侄女', c['lineage'])

    def test_dowager_niece_gets_trust_and_score_and_disgraced_gets_less(self):
        for patron, trust in (('dowager', game.TRUST_DOWAGER), ('disgraced', game.TRUST_DISGRACED), ('', game.TRUST_START)):
            uid = self.new_user(f'x{patron}')
            game.create_family(uid, f's{uid}', 'dali')
            self.create_member('云')
            game.run("UPDATE consorts SET patron=? WHERE user_id=?", (patron, uid))
            cid = self.enter_palace(uid)
            self.assertEqual(game.get_consort(cid)['trust'], trust + (5 if game.get_consort(cid)['entry_origin'] == 'east_palace' else 0), patron)
            self.assertEqual(game.get_consort(cid)['peak_rank'], game.get_consort(cid)['rank'])

    def test_dowager_niece_is_summoned_on_the_interval_and_targeted_more(self):
        c = self.player('丙', rank=3)
        game.run("UPDATE consorts SET patron='dowager', entered_day=3 WHERE id=?", (c,))
        f = game.get_consort(c)['favor']
        game.family_patron_tick(3 + game.DOWAGER_AUDIENCE_INTERVAL - 1)
        self.assertEqual(game.get_consort(c)['favor'], f)
        game.family_patron_tick(3 + game.DOWAGER_AUDIENCE_INTERVAL)
        self.assertEqual(game.get_consort(c)['favor'], f + game.DOWAGER_AUDIENCE_FAVOR)
        self.assertTrue(any('慈宁宫' in m for m in self.msgs(c)))

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_shoukang_reveals_an_npc_secret_once_a_week(self):
        c = self.player('丙', rank=3)
        game.run("UPDATE consorts SET patron='concubine' WHERE id=?", (c,))
        game.run("UPDATE consorts SET secret='lover' WHERE npc_key='huafei'")
        self.login(c)
        self.client.post('/act/shoukang')
        known = game.q('SELECT COUNT(*) n FROM known_secrets WHERE knower_id=?', (c,), one=True)['n']
        self.assertEqual(known, 1)
        game.run('DELETE FROM daily_counters')
        self.client.post('/act/shoukang')
        self.assertEqual(game.q('SELECT COUNT(*) n FROM known_secrets WHERE knower_id=?', (c,), one=True)['n'], 1, '一周内再去没用')
        self.assertIn('寿康宫', self.client.get('/place/home').get_data(as_text=True))
        self.login(self.atk)
        self.assertNotIn('寿康宫', self.client.get('/place/home').get_data(as_text=True))

    # ── 姐姐留下的东西 ───────────────────────────────────────────────────────

    def test_dowry_is_thirty_percent_up_to_cap_and_taken_once(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        prev = self.past_member(uid, silver=5000, death_day=1)
        self.set_day(10)
        self.create_member('云')
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        self.assertEqual(c['silver'], game.FAMILIES['dali']['silver'] + game.DOWRY_MAX)
        self.assertEqual(game.get_consort(prev)['silver'], 0)
        self.assertEqual(json.loads(c['inherit'])['from'], prev)

    def test_stats_and_legacy_influence_are_inherited(self):
        uid = self.new_user()
        game.create_family(uid, '沈', 'dali')
        prev = self.past_member(uid, silver=100, death_day=1)
        game.run("UPDATE consorts SET appearance=100,talent=40,scheme=10,virtue=60,health=80,peak_rank=7 WHERE id=?", (prev,))
        self.set_day(10)
        self.create_member('云')
        c = game.q('SELECT * FROM consorts WHERE user_id=?', (uid,), one=True)
        inh = json.loads(c['inherit'])
        self.assertEqual(inh['stats'], dict(appearance=5, talent=2, scheme=0, virtue=3, health=4))      # 5%，每项最多 +5
        self.assertEqual(inh['influence'], 10)
        self.assertEqual(game.legacy_influence(4), 0)
        self.assertEqual(game.legacy_influence(5), 5)
        self.assertEqual(game.legacy_influence(9), 10)
        before = game.get_consort(c['id'])['influence']
        game.apply_inheritance(game.get_consort(c['id']))
        self.assertEqual(game.get_consort(c['id'])['influence'], before + 10)

    def test_small_estate_dowry(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, silver=300, death_day=1)
        self.set_day(10)
        self.create_member('云')
        self.assertEqual(game.q('SELECT silver FROM consorts WHERE user_id=?', (uid,), one=True)['silver'],
                         game.FAMILIES['dali']['silver'] + int(300 * game.DOWRY_RATIO))

    def test_sworn_sisters_start_friendly_but_not_sworn(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        prev = self.past_member(uid, death_day=1)
        friend = self.player('闺蜜', rank=4)
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,1)", (min(prev, friend), max(prev, friend), 60))
        self.set_day(10)
        self.create_member('云')
        cid = self.enter_palace(uid)
        rel = game.relation(cid, friend)
        self.assertEqual(rel['affinity'], game.FELLOW_AFFINITY)
        self.assertFalse(rel['sister'], '要重新结拜')

    def test_farewell_letter_names_the_culprit(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        prev = self.past_member(uid, death_day=1, culprit_id=self.tgt)
        self.set_day(10)
        self.create_member('云')
        cid = self.enter_palace(uid)
        letter = game.q('SELECT * FROM letters WHERE to_id=?', (cid,), one=True)
        self.assertIn(game.full_name(game.get_consort(self.tgt)), letter['body'])
        self.assertIn('遗书', letter['sender_label'])

    def test_no_letter_without_a_known_culprit(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, death_day=1)
        self.set_day(10)
        self.create_member('云')
        cid = self.enter_palace(uid)
        self.assertFalse(game.q('SELECT 1 FROM letters WHERE to_id=?', (cid,), one=True))

    def test_eyes_record_the_culprit_for_the_letter(self):
        game.run("UPDATE consorts SET eyes_until_day=99 WHERE id=?", (self.tgt,))
        game.inv_add(self.atk, 'lihun')
        game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,created_ts) VALUES(9,?,?,'rumor',0)", (self.atk, self.tgt))
        it = game.q('SELECT * FROM intrigues ORDER BY id DESC', one=True)
        with patch.object(game.random, 'random', return_value=0.0):
            game.resolve_intrigue(it)
        self.assertEqual(game.get_consort(self.tgt)['culprit_id'], self.atk)

    def test_heirloom_maid_follows_a_sister(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        prev = self.past_member(uid, death_day=1)
        good = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,status,joined_day,left_day,left_reason) VALUES(?,?,?,?,?,1,5,'主子没了，散去')",
                        (prev, '小蝉', 'suizui', 90, 'gone')).lastrowid
        game.run("INSERT INTO maids(owner_id,name,trait,loyalty,status,joined_day,left_day,left_reason) VALUES(?,?,?,?,?,1,5,'主子没了，散去')",
                 (prev, '小鹊', 'suizui', 79, 'gone'))
        self.assertEqual([m['id'] for m in game.heirloom_maids(uid)], [good], '忠心不到 80 的不算')
        self.set_day(10)
        self.create_member('云', heirloom_maid=good)
        cid = self.enter_palace(uid)
        m = game.get_maid(good)
        self.assertEqual((m['owner_id'], m['status']), (cid, 'active'))

    def test_heirloom_maid_of_someone_elses_family_is_refused(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.past_member(uid, death_day=1)
        stranger = game.run("INSERT INTO maids(owner_id,name,trait,loyalty,status,joined_day,left_day,left_reason) VALUES(?,?,?,?,?,1,5,'主子没了，散去')",
                            (self.tgt, '别家的', 'suizui', 95, 'gone')).lastrowid
        self.set_day(10)
        self.create_member('云', heirloom_maid=stranger)
        self.assertFalse(game.q('SELECT 1 FROM consorts WHERE user_id=?', (uid,), one=True))

    # ── 姨母与孩子 ───────────────────────────────────────────────────────────

    def test_maternal_aunt_is_kin_and_can_visit_and_reclaim(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        sister = self.past_member(uid, status='dead', peak=3)
        game.run("UPDATE consorts SET reign_no=1")
        aunt = self.player('姨', rank=6)
        game.run("UPDATE consorts SET user_id=?, archived_user_id=NULL WHERE id=?", (uid, aunt))
        foster = self.player('丙', rank=6)
        hid = self.heir(sister, caretaker=foster, mother_affinity=30, caretaker_affinity=60, born=game.cur_day() - 2)      # 还没成年（14 岁 = 3.5 天）
        self.login(aunt)
        h = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertTrue(game.maternal_kin(game.get_consort(aunt), h))
        self.client.post(f'/heirs/visit/{hid}')
        self.assertEqual(game.q('SELECT mother_affinity FROM heirs WHERE id=?', (hid,), one=True)['mother_affinity'], 30 + game.HEIR_VISIT_GAIN)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post(f'/heirs/reclaim/{hid}')
        game.run('UPDATE custody_battles SET challenger_progress=90 WHERE heir_id=?', (hid,))
        self.client.post(f'/heirs/custody/{hid}', data={'action':'bond'})
        self.assertEqual(game.q('SELECT caretaker_id FROM heirs WHERE id=?', (hid,), one=True)['caretaker_id'], aunt)

    def test_stranger_and_other_reign_sister_are_not_kin(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        sister = self.past_member(uid, reign_no=1)
        hid = self.heir(sister, caretaker=self.atk)
        h = game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)
        self.assertFalse(game.maternal_kin(game.get_consort(self.tgt), h))
        later = self.player('后人', rank=5)
        game.run("UPDATE consorts SET user_id=?, reign_no=2 WHERE id=?", (uid, later))
        self.assertFalse(game.maternal_kin(game.get_consort(later), h), '上一届的姐姐，这一届是姑母辈，不算姨母')

    # ── 名望 ─────────────────────────────────────────────────────────────────

    def test_rank_prestige_only_counts_first_time(self):
        uid = self.fam(self.atk)
        game.run('UPDATE consorts SET rank=4, prestige_top=4, user_id=user_id WHERE id=?', (self.atk,))
        game.set_rank(self.atk, 5)
        self.assertEqual(self.frow(uid)['prestige'], 5)
        game.set_rank(self.atk, 4)
        game.set_rank(self.atk, 5)
        self.assertEqual(self.frow(uid)['prestige'], 5, '降了再升不重复算')
        game.set_rank(self.atk, game.RANK_GUIFEI)
        self.assertEqual(self.frow(uid)['prestige'], sum(game.PRESTIGE_RANK_GAIN[r] for r in range(5, game.RANK_GUIFEI + 1)))
        self.assertEqual(game.get_consort(self.atk)['peak_rank'], game.RANK_GUIFEI)

    def test_births_cold_secret_and_old_age_move_prestige(self):
        uid = self.fam(self.atk, prestige=50)
        c = game.get_consort(self.atk)
        game.add_prestige(c, game.PRESTIGE_BORN_PRINCE)
        game.send_to_cold(self.atk)
        self.assertEqual(self.frow(uid)['prestige'], 50 + 5 + game.PRESTIGE_COLD)
        game.run("UPDATE consorts SET secret='book' WHERE id=?", (self.atk,))
        game.apply_secret_penalty(self.atk, confessed=True)
        self.assertEqual(self.frow(uid)['prestige'], 45, '自己坦白不扣')
        game.apply_secret_penalty(self.atk, confessed=False)
        self.assertEqual(self.frow(uid)['prestige'], 45 + game.PRESTIGE_EXPOSED)

    def test_old_age_death_adds_prestige(self):
        uid = self.fam(self.atk)
        game.run('UPDATE consorts SET age_months=?, health=100 WHERE id=?', (game.OLD_AGE_START + 12 * 40, self.atk))
        with patch.object(game.random, 'random', return_value=0.0):
            game.old_age_tick(10)
        self.assertEqual(game.get_consort(self.atk)['status'], 'dead')
        self.assertEqual(self.frow(uid)['prestige'], game.PRESTIGE_OLD_AGE)

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_npcs_have_no_prestige_and_no_family(self):
        npc = game.q("SELECT * FROM consorts WHERE npc_key='huafei'", one=True)
        game.add_prestige(npc, 10)
        game.set_rank(npc['id'], 7)   # 不报错
        self.assertEqual(game.q('SELECT COUNT(*) n FROM families', one=True)['n'], 0)

    def test_prince_title_gives_the_family_prestige_once(self):
        uid = self.fam(self.atk)
        hid = self.heir(self.atk, born=game.cur_day() - 32, favor=200)
        game.heir_adult_tick(game.cur_day())
        self.assertEqual(game.q('SELECT title FROM heirs WHERE id=?', (hid,), one=True)['title'], '亲王')
        self.assertEqual(self.frow(uid)['prestige'], game.PRESTIGE_PRINCE_TITLE)

    def test_family_label_counts_the_heads_office_too(self):
        low = dict(prestige=0, head_office=0)
        general = dict(prestige=0, head_office=7)
        top = dict(prestige=40, head_office=9)
        self.assertEqual([game.family_label(f) for f in (low, general, top)], ['寒门', '小康之家', '望族'])

    def test_prestige_labels(self):
        self.assertEqual([game.prestige_label(p) for p in (0, 19, 20, 59, 60, 119, 120)],
                         ['寒门', '寒门', '小康之家', '小康之家', '望族', '望族', '簪缨世家'])

    # ── 家主 ─────────────────────────────────────────────────────────────────

    def test_head_ages_with_the_shared_clock(self):
        uid = self.fam(self.atk, head_age_months=50 * 12)
        with patch.object(game.random, 'random', return_value=0.999):
            game.family_tick(10)
        self.assertEqual(self.frow(uid)['head_age_months'], 50 * 12 + game.AGE_MONTHS_PER_DAY)

    def test_old_head_dies_and_brother_takes_over_with_lower_office(self):
        uid = self.fam(self.atk, head_age_months=70 * 12, head_office=6)
        old = self.frow(uid)['head_name']
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_tick(10)
        f = self.frow(uid)
        self.assertEqual((f['head_role'], f['head_gen'], f['head_office']), ('兄长', 1, 5))
        self.assertTrue(24 <= f['head_age_months'] // 12 <= 36)
        self.assertTrue(any('病逝' in m for m in self.msgs(self.atk)))
        self.assertTrue(game.q("SELECT 1 FROM family_log WHERE user_id=? AND text LIKE '%病逝%'", (uid,), one=True))

    def test_head_succession_chain_and_office_floor(self):
        uid = self.fam(self.atk, head_office=1)
        roles = []
        for _ in range(5):
            f = self.frow(uid)
            game.head_dies(f, 10)
            roles.append(self.frow(uid)['head_role'])
        self.assertEqual(roles, ['兄长', '侄子', '族叔', '族叔', '族叔'])
        self.assertEqual(self.frow(uid)['head_office'], 0)

    def test_young_head_does_not_die_of_old_age(self):
        uid = self.fam(self.atk, head_age_months=40 * 12)
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_tick(10)
        self.assertEqual(self.frow(uid)['head_gen'], 0)   # 0.0 不会触发死亡（概率 0），只会升迁

    def test_head_falls_ill_recovers_and_dies_faster_when_ill(self):
        uid = self.fam(self.atk, head_age_months=52 * 12)
        seq = iter([0.0])   # 第一次判「病倒」
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.999)):
            game.family_tick(10)
        self.assertEqual(self.frow(uid)['head_ill_day'], 10)
        self.assertTrue(any('病倒' in m for m in self.msgs(self.atk)))
        with patch.object(game.random, 'random', return_value=0.05):   # < 康复 10%
            game.family_tick(11)
        self.assertEqual(self.frow(uid)['head_ill_day'], 0)
        game.run('UPDATE families SET head_ill_day=10 WHERE user_id=?', (uid,))
        with patch.object(game.random, 'random', return_value=0.15):   # 没康复，却 < 病中 20% 的死亡率
            game.family_tick(12)
        self.assertEqual(self.frow(uid)['head_gen'], 1)

    def test_head_promotion_and_demotion(self):
        uid = self.fam(self.atk, head_office=4, head_age_months=40 * 12)      # 一晚涨四岁，两晚后还不到 50 岁，不掷病
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_tick(10)
        f = self.frow(uid)
        self.assertEqual((f['head_office'], f['prestige']), (5, 3))
        self.assertTrue(any('升任' in m for m in self.msgs(self.atk)))
        game.run('UPDATE families SET head_office=4, prestige=10 WHERE user_id=?', (uid,))
        seq = iter([0.999, 0.999, 0.0])   # 不病、不死，升迁没中，降职中了
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.999)):
            game.family_tick(11)
        f = self.frow(uid)
        self.assertEqual((f['head_office'], f['prestige']), (3, 7))

    def test_office_never_leaves_its_range(self):
        uid = self.fam(self.atk, head_office=game.OFFICE_MAX, head_age_months=45 * 12)
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_tick(10)
        self.assertLessEqual(self.frow(uid)['head_office'], game.OFFICE_MAX)
        self.assertGreaterEqual(self.frow(uid)['head_office'], 0)

    # ── 家里来求助 ───────────────────────────────────────────────────────────

    def make_request(self, uid, kind, cid=None, **data):
        return game.run("INSERT INTO family_requests(user_id,consort_id,kind,day,expires_day,data) VALUES(?,?,?,?,?,?)",
                        (uid, cid or self.atk, kind, game.cur_day(), game.cur_day() + game.REQUEST_DAYS, json.dumps(data))).lastrowid

    def answer(self, rid, answer='yes', **extra):
        return self.client.post(f'/family/request/{rid}', data=dict(answer=answer, **extra))

    def test_requests_arrive_on_a_cooldown_and_only_one_at_a_time(self):
        uid = self.fam(self.atk)
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_request_tick(10)
            game.family_request_tick(11)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM family_requests', one=True)['n'], 1)
        self.assertTrue(any('家里来信' in m for m in self.msgs(self.atk)))

    def test_no_request_without_a_living_member(self):
        uid = self.fam(self.atk)
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (self.atk,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_request_tick(10)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM family_requests', one=True)['n'], 0)

    def test_request_kinds_follow_the_situation(self):
        uid = self.fam(self.atk, head_office=game.OFFICE_MAX)
        kinds = set()
        for i in range(60):
            game.run('DELETE FROM family_requests'); game.run('UPDATE families SET request_day=0')
            with patch.object(game.random, 'random', return_value=0.0):
                game.family_request_tick(10 + i * 5)
            kinds.add(game.q('SELECT kind FROM family_requests', one=True)['kind'])
        self.assertNotIn('promotion', kinds, '一品再升没有了')
        self.assertNotIn('illness', kinds, '没病就不会来要医药钱')
        self.assertNotIn('backing', kinds, '没有阿哥就不问站队')
        self.assertTrue({'trouble', 'debt'} <= kinds)

    def test_promotion_request_pays_and_may_promote(self):
        uid = self.fam(self.atk, head_office=3, prestige=0)
        rid = self.make_request(uid, 'promotion', cost=200)
        s0 = game.get_consort(self.atk)['silver']
        seq = iter([0.0, 0.99])   # 打点成功，没被参
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            self.answer(rid)
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 - 200)
        f = self.frow(uid)
        self.assertEqual((f['head_office'], f['prestige']), (4, 3))
        self.assertEqual(game.q('SELECT status FROM family_requests WHERE id=?', (rid,), one=True)['status'], 'done')
        self.answer(rid)   # 不能回第二次
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 - 200)

    def test_promotion_can_fail_and_get_scolded(self):
        uid = self.fam(self.atk, head_office=3)
        rid = self.make_request(uid, 'promotion', cost=100)
        with patch.object(game.random, 'random', return_value=0.99):
            self.answer(rid)
        self.assertEqual(self.frow(uid)['head_office'], 3)
        rid = self.make_request(uid, 'promotion', cost=100)
        seq = iter([0.99, 0.0])
        t0 = game.get_consort(self.atk)['trust']
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.99)):
            self.answer(rid)
        self.assertEqual(self.frow(uid)['prestige'], 0)
        self.assertEqual(game.get_consort(self.atk)['trust'], max(0, t0 - 3))

    def test_promotion_needs_the_silver(self):
        uid = self.fam(self.atk, head_office=3)
        game.run('UPDATE consorts SET silver=10 WHERE id=?', (self.atk,))
        rid = self.make_request(uid, 'promotion', cost=200)
        self.answer(rid)
        self.assertEqual(game.q('SELECT status FROM family_requests WHERE id=?', (rid,), one=True)['status'], 'open')

    def test_trouble_intercede_success_and_failure(self):
        uid = self.fam(self.atk, head_office=5)
        rid = self.make_request(uid, 'trouble')
        e0 = game.get_consort(self.atk)['energy']
        with patch.object(game.random, 'random', return_value=0.0):
            self.answer(rid)
        self.assertEqual(game.get_consort(self.atk)['energy'], e0 - 1)
        self.assertEqual((self.frow(uid)['head_office'], self.frow(uid)['prestige']), (5, 1))
        rid = self.make_request(uid, 'trouble')
        with patch.object(game.random, 'random', return_value=0.999):
            self.answer(rid)
        self.assertEqual((self.frow(uid)['head_office'], self.frow(uid)['prestige']), (4, 0))

    def test_trouble_declined_costs_the_head_a_rank(self):
        uid = self.fam(self.atk, head_office=5, prestige=10)
        self.answer(self.make_request(uid, 'trouble'), 'no')
        self.assertEqual((self.frow(uid)['head_office'], self.frow(uid)['prestige']), (4, 8))

    def test_debt_and_illness_requests(self):
        uid = self.fam(self.atk, head_ill_day=5, prestige=5)
        s0 = game.get_consort(self.atk)['silver']
        self.answer(self.make_request(uid, 'debt', cost=70))
        self.assertEqual((game.get_consort(self.atk)['silver'], self.frow(uid)['prestige']), (s0 - 70, 6))
        self.answer(self.make_request(uid, 'illness', cost=120))
        self.assertEqual((game.get_consort(self.atk)['silver'], self.frow(uid)['head_ill_day']), (s0 - 190, 0))
        self.answer(self.make_request(uid, 'debt', cost=70), 'no')
        self.assertEqual(self.frow(uid)['prestige'], 6 + 1 - 1)

    def test_illness_declined_leaves_the_head_ill(self):
        uid = self.fam(self.atk, head_ill_day=5)
        self.answer(self.make_request(uid, 'illness', cost=120), 'no')
        self.assertEqual(self.frow(uid)['head_ill_day'], 5)

    def test_unanswered_requests_lapse_with_consequences(self):
        uid = self.fam(self.atk, head_office=5, prestige=10)
        rid = self.make_request(uid, 'trouble')
        with patch.object(game.random, 'random', return_value=0.999):
            game.family_request_tick(game.cur_day() + game.REQUEST_DAYS - 1)
        self.assertEqual(game.q('SELECT status FROM family_requests WHERE id=?', (rid,), one=True)['status'], 'open')
        with patch.object(game.random, 'random', return_value=0.999):
            game.family_request_tick(game.cur_day() + game.REQUEST_DAYS)
        self.assertEqual(game.q('SELECT status FROM family_requests WHERE id=?', (rid,), one=True)['status'], 'lapsed')
        self.assertEqual((self.frow(uid)['head_office'], self.frow(uid)['prestige']), (4, 8))

    def test_others_cannot_answer_my_request(self):
        uid = self.fam(self.atk, head_office=3)
        rid = self.make_request(uid, 'debt', cost=70)
        self.fam(self.tgt)
        self.login(self.tgt)
        self.answer(rid)
        self.assertEqual(game.q('SELECT status FROM family_requests WHERE id=?', (rid,), one=True)['status'], 'open')

    # ── 联络：送银子、支取、家书、荐官 ────────────────────────────────────────────

    def test_send_silver_home_goes_to_estate_and_earns_prestige(self):
        uid = self.fam(self.atk)
        s0 = game.get_consort(self.atk)['silver']
        self.client.post('/family/send', data=dict(amount=250))
        f = self.frow(uid)
        self.assertEqual((f['estate'], f['prestige'], game.get_consort(self.atk)['silver']), (250, 2, s0 - 250))
        self.client.post('/family/send', data=dict(amount=100))
        self.assertEqual(self.frow(uid)['estate'], 250, '一天只能送一次')

    def test_send_limits(self):
        uid = self.fam(self.atk)
        for amt in (5, 501, 'x'):
            self.client.post('/family/send', data=dict(amount=amt))
        game.run('UPDATE consorts SET silver=20 WHERE id=?', (self.atk,))
        self.client.post('/family/send', data=dict(amount=100))
        self.assertEqual(self.frow(uid)['estate'], 0)

    def test_withdraw_from_estate_with_cooldown_and_cap(self):
        uid = self.fam(self.atk, estate=500)
        s0 = game.get_consort(self.atk)['silver']
        self.client.post('/family/withdraw', data=dict(amount=300))
        self.assertEqual(self.frow(uid)['estate'], 500)
        self.client.post('/family/withdraw', data=dict(amount=150))
        self.assertEqual((self.frow(uid)['estate'], game.get_consort(self.atk)['silver']), (350, s0 + 150))
        self.client.post('/family/withdraw', data=dict(amount=50))
        self.assertEqual(self.frow(uid)['estate'], 350, '刚取过')
        self.set_day(game.cur_day() + game.WITHDRAW_INTERVAL)
        self.client.post('/family/withdraw', data=dict(amount=999))
        self.assertEqual(self.frow(uid)['estate'], 350, '超过家底')
        self.client.post('/family/withdraw', data=dict(amount=200))
        self.assertEqual(self.frow(uid)['estate'], 150)

    def test_estate_survives_the_daughter(self):
        uid = self.fam(self.atk, estate=200)
        game.die(self.atk, '病逝')
        self.assertEqual(self.frow(uid)['estate'], 200)

    @unittest.skip("旧版家书揭露固定 NPC 秘密；固定 NPC 已取消")
    def test_family_letter_can_reveal_a_secret_or_give_silver(self):
        uid = self.fam(self.atk)
        game.run("UPDATE consorts SET secret='scar' WHERE id=?", (self.tgt,))
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/family/letter')
        self.assertEqual(game.q('SELECT COUNT(*) n FROM known_secrets WHERE knower_id=?', (self.atk,), one=True)['n'], 1)
        game.run('DELETE FROM daily_counters')
        s0 = game.get_consort(self.atk)['silver']
        with patch.object(game.random, 'random', return_value=0.5):
            self.client.post('/family/letter')
        self.assertTrue(20 <= game.get_consort(self.atk)['silver'] - s0 <= 60)

    def test_family_letter_once_a_day_and_costs_energy(self):
        self.fam(self.atk)
        e0 = game.get_consort(self.atk)['energy']
        with patch.object(game.random, 'random', return_value=0.9):
            self.client.post('/family/letter')
            self.client.post('/family/letter')
        self.assertEqual(game.get_consort(self.atk)['energy'], e0 - 1)

    def test_petition_success_failure_and_scolding(self):
        uid = self.fam(self.atk, head_office=4)
        s0 = game.get_consort(self.atk)['silver']
        with patch.object(game.random, 'random', return_value=0.99):
            self.client.post('/family/petition')
        self.assertEqual((self.frow(uid)['head_office'], game.get_consort(self.atk)['silver']), (4, s0 - game.PETITION_COST))
        self.client.post('/family/petition')
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 - game.PETITION_COST, '七天内不能再来')
        self.set_day(game.cur_day() + game.PETITION_INTERVAL)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/family/petition')
        f = self.frow(uid)
        self.assertEqual(f['head_office'], 5)
        self.assertEqual(f['prestige'], 3 - 8 if 3 - 8 > 0 else 0)   # 成功 +3，同时被参 −8，名望不低于 0

    def test_petition_stops_at_top_rank(self):
        uid = self.fam(self.atk, head_office=game.OFFICE_MAX)
        s0 = game.get_consort(self.atk)['silver']
        self.client.post('/family/petition')
        self.assertEqual(game.get_consort(self.atk)['silver'], s0)

    def test_high_prestige_makes_scolding_rarer(self):
        low = game.scold_chance(0.2, {'prestige': 0})
        high = game.scold_chance(0.2, {'prestige': 200})
        huge = game.scold_chance(0.2, {'prestige': 9999})
        self.assertEqual((low, high, huge), (0.2, 0.1, 0.1))

    def test_cold_palace_and_dead_cannot_contact_family(self):
        uid = self.fam(self.atk, estate=100)
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (self.atk,))
        self.client.post('/family/withdraw', data=dict(amount=50))
        self.assertEqual(self.frow(uid)['estate'], 100)

    # ── 生意 ─────────────────────────────────────────────────────────────────

    def start_venture(self, kind='silk', amount=100):
        return self.client.post('/family/venture', data=dict(kind=kind, amount=amount))

    def test_venture_locks_principal_and_matures(self):
        uid = self.fam(self.atk)
        s0 = game.get_consort(self.atk)['silver']
        self.start_venture('silk', 100)
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 - 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        self.assertEqual(v['mature_day'], game.cur_day() + game.VENTURES['silk']['days'])
        game.family_venture_tick(v['mature_day'] - 1)
        self.assertEqual(game.q('SELECT status FROM family_ventures', one=True)['status'], 'open')
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_venture_tick(v['mature_day'])
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + 25)
        self.assertEqual(game.q('SELECT status FROM family_ventures', one=True)['status'], 'done')
        self.assertTrue(any('结账' in m for m in self.msgs(self.atk)))

    def test_at_most_two_open_ventures_and_limits(self):
        self.fam(self.atk)
        game.run('UPDATE consorts SET energy=5 WHERE id=?', (self.atk,))
        self.start_venture('silk', 100)
        self.start_venture('salt', 100)
        self.start_venture('usury', 100)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM family_ventures', one=True)['n'], game.VENTURE_MAX_OPEN)
        game.run("DELETE FROM family_ventures")
        for amt in (49, 401):
            self.start_venture('silk', amt)
        self.start_venture('nope', 100)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM family_ventures', one=True)['n'], 0)

    def test_riskier_ventures_pay_more_per_day(self):
        """险大的生意每天的期望收益该更高，不然没人会选：绸缎庄 < 盐引 < 印子钱（2026-10-05 起三门生意都 1 天结账，不再限制每天收益上限）"""
        per_day = {k: sum(p * r for p, r in v['outcomes']) / v['days'] for k, v in game.VENTURES.items()}
        self.assertLess(per_day['silk'], per_day['salt'])
        self.assertLess(per_day['salt'], per_day['usury'])
        self.assertGreater(per_day['silk'], 0.02)

    def test_every_venture_outcome_table_sums_to_one(self):
        for k, v in game.VENTURES.items():
            self.assertAlmostEqual(sum(p for p, _ in v['outcomes']), 1.0, msg=k)

    def test_venture_outcomes_by_roll(self):
        self.fam(self.atk)
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        for kind, roll, expect in (('salt', 0.0, 200), ('salt', 0.5, 110), ('salt', 0.8, 50), ('salt', 0.95, 0),
                                   ('usury', 0.0, 300), ('usury', 0.5, 110), ('usury', 0.9, 0), ('silk', 0.99, 70)):
            game.run('DELETE FROM family_ventures'); game.run('DELETE FROM daily_counters'); game.run('UPDATE consorts SET energy=5, silver=1000 WHERE id=?', (self.atk,))
            self.start_venture(kind, 100)
            v = game.q('SELECT * FROM family_ventures', one=True)
            seq = iter([roll])
            with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.999)):   # 后面的「被参」骰子一律不中
                game.family_venture_tick(v['mature_day'])
            self.assertEqual(game.get_consort(self.atk)['silver'], 900 + expect, (kind, roll))

    def test_merchant_family_earns_more(self):
        uid = self.fam(self.atk, tier='merchant')
        self.start_venture('silk', 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        s0 = game.get_consort(self.atk)['silver']
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_venture_tick(v['mature_day'])
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + 100 + round(25 * 1.15))

    def test_risky_venture_can_get_the_family_scolded(self):
        uid = self.fam(self.atk, prestige=30)
        game.run('UPDATE consorts SET trust=50 WHERE id=?', (self.atk,))
        self.start_venture('salt', 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        seq = iter([0.0, 0.0])   # 赚了，也被参了
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.999)):
            game.family_venture_tick(v['mature_day'])
        self.assertEqual(self.frow(uid)['prestige'], 22)
        self.assertEqual(game.get_consort(self.atk)['trust'], 44)
        self.assertTrue(any('参了一本' in m for m in self.msgs(self.atk)))

    def test_usury_scandal_is_costly(self):
        uid = self.fam(self.atk, prestige=40, estate=300)
        game.run('UPDATE consorts SET trust=50, favor=200 WHERE id=?', (self.atk,))
        self.start_venture('usury', 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        seq = iter([0.9, 0.0])   # 血本无归，还东窗事发
        with patch.object(game.random, 'random', side_effect=lambda: next(seq, 0.999)):
            game.family_venture_tick(v['mature_day'])
        f = self.frow(uid)
        self.assertEqual((f['prestige'], f['estate']), (25, 150))
        c = game.get_consort(self.atk)
        self.assertEqual((c['trust'], c['favor']), (42, 200 - game.FAVOR_LOSS['usury']))

    def test_safe_venture_never_scolded(self):
        uid = self.fam(self.atk, prestige=0)
        self.start_venture('silk', 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_venture_tick(v['mature_day'])
        self.assertEqual(self.frow(uid)['prestige'], 0)

    def test_payout_goes_to_estate_if_she_died_meanwhile(self):
        uid = self.fam(self.atk, estate=10)
        self.start_venture('silk', 100)
        v = game.q('SELECT * FROM family_ventures', one=True)
        game.die(self.atk, '病逝')
        with patch.object(game.random, 'random', return_value=0.0):
            game.family_venture_tick(v['mature_day'])
        self.assertEqual(self.frow(uid)['estate'], 10 + 125)

    # ── 家里送钱 ─────────────────────────────────────────────────────────────

    def test_remit_amount_needs_a_prospering_family(self):
        base = dict(tier='dali', head_ill_day=0)
        self.assertEqual(game.remit_amount(dict(base, head_office=1, prestige=29)), 0)
        self.assertEqual(game.remit_amount(dict(base, head_office=2, prestige=0)), 2 * game.REMIT_PER_OFFICE)
        self.assertEqual(game.remit_amount(dict(base, head_office=1, prestige=30)), game.REMIT_PER_OFFICE + 30 // game.REMIT_PRESTIGE_DIV)
        self.assertEqual(game.remit_amount(dict(base, head_office=9, prestige=5000)), game.REMIT_MAX)
        self.assertEqual(game.remit_amount(dict(base, head_office=4, prestige=0, tier='merchant')), int(4 * game.REMIT_PER_OFFICE * 1.2))
        self.assertEqual(game.remit_amount(dict(base, head_office=4, prestige=0, head_ill_day=3)), 4 * game.REMIT_PER_OFFICE // 2, '家主病着，减半')

    def test_remit_arrives_on_the_interval(self):
        uid = self.fam(self.atk, head_office=5, prestige=20)
        s0 = game.get_consort(self.atk)['silver']
        game.family_remit_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + 5 * game.REMIT_PER_OFFICE + 20 // game.REMIT_PRESTIGE_DIV)
        game.family_remit_tick(game.cur_day())      # 每 12 小时一次，不再按天数隔几天发
        self.assertEqual(game.get_consort(self.atk)['silver'], s0 + 2 * (5 * game.REMIT_PER_OFFICE + 20 // game.REMIT_PRESTIGE_DIV))
        self.assertTrue(any('体己' in m for m in self.msgs(self.atk)))

    def test_no_remit_for_a_poor_family_or_an_empty_palace(self):
        uid = self.fam(self.atk, head_office=0, prestige=0)
        s0 = game.get_consort(self.atk)['silver']
        game.family_remit_tick(10)
        self.assertEqual(game.get_consort(self.atk)['silver'], s0)
        game.run('UPDATE families SET head_office=6 WHERE user_id=?', (uid,))
        game.run("UPDATE consorts SET status='dead' WHERE id=?", (self.atk,))
        game.family_remit_tick(10)   # 没人在宫里，不报错

    def test_stipend_alone_is_not_enough_to_get_rich(self):
        """俸禄够不上花销才逼着人去外面想办法：这里只确认俸禄表存在且逐级递增，不做数值断言"""
        vals = [game.STIPEND[r] for r in sorted(game.STIPEND)]
        self.assertEqual(vals, sorted(vals))

    # ── 夺嫡里的家族 ─────────────────────────────────────────────────────────

    def test_faction_counts_players_by_account_not_by_tier(self):
        uid_a, uid_b = self.fam(self.atk), self.fam(self.tgt)
        hid = self.prince(self.atk, caretaker=self.tgt)
        self.assertEqual(game.heir_faction_count(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), 2)
        other = self.player('丙', rank=4)
        game.run("UPDATE consorts SET user_id=NULL, archived_user_id=? WHERE id=?", (uid_a, other))
        game.run('UPDATE relations SET sister=0')
        game.run("INSERT INTO relations(a_id,b_id,affinity,sister) VALUES(?,?,?,1)", (min(self.atk, other), max(self.atk, other), 50))
        self.assertEqual(game.heir_faction_count(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), 2, '同一账号的姐妹算一家')

    def test_default_backing_is_the_familys_own_prince(self):
        uid = self.fam(self.atk)
        mine = self.prince(self.atk)
        self.prince(self.tgt)
        self.assertEqual(game.family_backing_id(self.frow(uid)), mine)

    def test_no_prince_means_no_backing(self):
        uid = self.fam(self.atk)
        self.assertEqual(game.family_backing_id(self.frow(uid)), 0)
        self.prince(self.atk, age_years=11)
        self.assertEqual(game.family_backing_id(self.frow(uid)), 0, '十二岁以下的不算')

    def test_family_office_lifts_the_prince_it_backs(self):
        uid = self.fam(self.atk, head_office=6)
        hid = self.prince(self.atk, study=0, riding=0, virtue=0)
        game.run('UPDATE consorts SET rank=1, trust=0 WHERE id=?', (self.atk,))
        self.assertEqual(game.heir_standing(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), 6)
        uid2 = self.fam(self.tgt, head_office=9)
        game.run('UPDATE families SET backing_heir_id=? WHERE user_id=?', (hid, uid2))
        self.assertEqual(game.heir_standing(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), 15, '6+9 = 15，封顶 15')
        game.run('UPDATE families SET head_office=9 WHERE user_id=?', (uid,))
        self.assertEqual(game.family_support(game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)), game.SUPPORT_CAP)

    def test_backing_route_costs_and_locks_and_can_be_scolded(self):
        uid = self.fam(self.atk, head_office=5, prestige=10)
        a, b = self.prince(self.tgt, age_years=13), self.prince(self.tgt, age_years=14)
        s0 = game.get_consort(self.atk)['silver']
        with patch.object(game.random, 'random', return_value=0.999):
            self.client.post('/family/backing', data=dict(heir_id=a))
        f = self.frow(uid)
        self.assertEqual((f['backing_heir_id'], game.get_consort(self.atk)['silver']), (a, s0 - game.BACKING_COST))
        self.client.post('/family/backing', data=dict(heir_id=b))
        self.assertEqual(self.frow(uid)['backing_heir_id'], a, '七天内不能改')
        self.set_day(game.cur_day() + game.BACKING_LOCK_DAYS)
        with patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/family/backing', data=dict(heir_id=b))
        f = self.frow(uid)
        self.assertEqual((f['backing_heir_id'], f['head_office'], f['prestige']), (b, 4, 5), '表了态又被参结党，降一级')

    def test_backing_request_sets_the_choice(self):
        uid = self.fam(self.atk)
        a = self.prince(self.tgt, age_years=13)
        rid = self.make_request(uid, 'backing', options=[a])
        self.answer(rid, heir_id=999)
        self.assertEqual(self.frow(uid)['backing_heir_id'], 0)
        self.answer(rid, heir_id=a)
        self.assertEqual(self.frow(uid)['backing_heir_id'], a)

    def test_backing_request_only_when_princes_exist_and_no_choice_yet(self):
        uid = self.fam(self.atk)
        kinds = set()
        a = self.prince(self.tgt, age_years=13)
        for i in range(80):
            game.run('DELETE FROM family_requests'); game.run('UPDATE families SET request_day=0')
            with patch.object(game.random, 'random', return_value=0.0):
                game.family_request_tick(10 + i * 5)
            kinds.add(game.q('SELECT kind FROM family_requests', one=True)['kind'])
        self.assertIn('backing', kinds)
        game.run('UPDATE families SET backing_heir_id=?', (a,))
        kinds = set()
        for i in range(80):
            game.run('DELETE FROM family_requests'); game.run('UPDATE families SET request_day=0')
            with patch.object(game.random, 'random', return_value=0.0):
                game.family_request_tick(500 + i * 5)
            kinds.add(game.q('SELECT kind FROM family_requests', one=True)['kind'])
        self.assertNotIn('backing', kinds)

    def test_winning_and_losing_backers_rise_and_fall_at_the_plaque(self):
        game.run('UPDATE consorts SET rank=1, trust=0')
        winner = self.prince(self.atk, favor=90)
        loser = self.prince(self.tgt, favor=10)
        uid_a = self.fam(self.atk, head_office=4, prestige=20)
        uid_b = self.fam(self.tgt, head_office=4, prestige=20)
        uid_c = self.fam(self.player('丙', rank=4), head_office=4, prestige=20, backing_heir_id=0)
        game.settle_family_backing(game.succession_favorite(game.cur_day())[0], game.cur_day())
        a, b, c = self.frow(uid_a), self.frow(uid_b), self.frow(uid_c)
        self.assertEqual((a['head_office'], a['prestige']), (4 + game.BACKING_WIN_OFFICE, 20 + game.BACKING_WIN_PRESTIGE))
        self.assertEqual((b['head_office'], b['prestige']), (4 - game.BACKING_LOSE_OFFICE, 20 - game.BACKING_LOSE_PRESTIGE))
        self.assertEqual((c['head_office'], c['prestige']), (4, 20), '没儿子、没表态的家族不受影响')
        self.assertTrue(game.q("SELECT 1 FROM family_log WHERE user_id=? AND honor=1 AND text LIKE '%站对了%'", (uid_a,), one=True))

    def test_backing_is_reset_after_the_reign(self):
        uid = self.fam(self.atk, backing_heir_id=7, backing_day=3)
        game.settle_family_backing(None, game.cur_day())
        self.assertEqual((self.frow(uid)['backing_heir_id'], self.frow(uid)['backing_day']), (0, 0))

    # ── 换届时的家族账 ───────────────────────────────────────────────────────

    def test_end_reign_records_honours_and_prestige_and_dowager(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        uid_a, uid_b = self.fam(self.atk, prestige=10), self.fam(self.tgt, prestige=10)
        hid = self.prince(self.atk, caretaker=self.tgt, favor=90, mother_affinity=20, caretaker_affinity=80, name='承稷')
        princess = self.heir(self.atk, gender='公主', born=1, title='固伦公主', adult_day=1, marriage='mongol')
        prince2 = self.prince(self.atk, age_years=17, adult_day=1, title='亲王', favor=1)
        game.end_reign(game.cur_day())
        b = game.q('SELECT * FROM family_pool WHERE last_user_id=?', (uid_b,), one=True)      # 新帝登基，家族退回家族池，名望留在家族身上
        self.assertEqual(b['prestige'], 10 + game.PRESTIGE_DOWAGER + game.BACKING_WIN_PRESTIGE, '养母成太后，家里又押对了')
        self.assertEqual(game.q('SELECT dowager_uid FROM game_state', one=True)['dowager_uid'], uid_b)
        honors_a = [r['text'] for r in game.q('SELECT text FROM family_log WHERE user_id=? AND honor=1', (uid_a,))]
        honors_b = [r['text'] for r in game.q('SELECT text FROM family_log WHERE user_id=? AND honor=1', (uid_b,))]
        self.assertTrue(any('太妃' in t for t in honors_a))
        self.assertTrue(any('太后' in t for t in honors_b))
        self.assertTrue(any('固伦公主' in t for t in honors_a), honors_a)
        self.assertTrue(any('亲王' in t for t in honors_a), honors_a)

    def test_end_reign_marks_survivors_and_writes_kids(self):
        self.fam(self.atk)
        hid = self.prince(self.atk, favor=90, name='承稷')
        dead = self.player('丙', rank=4)
        game.die(dead, '病逝')
        game.end_reign(game.cur_day())
        c = game.get_consort(self.atk)
        self.assertEqual((c['status'], c['survived']), ('dead', 1))
        self.assertEqual(game.get_consort(dead)['survived'], 0)
        self.assertIn('承稷', game.q('SELECT kids FROM consorts WHERE id=?', (self.atk,), one=True)['kids'])

    def test_disgraced_fate_for_the_parents_of_an_imprisoned_prince(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        winner = self.prince(self.tgt, favor=90)
        loser = self.prince(self.atk, age_years=17, adult_day=1, title='贝勒', ambition=90, faction=6, favor=1)
        uid = self.fam(self.atk)
        game.end_reign(game.cur_day())
        fates = {f['cid']: f['fate'] for f in json.loads(game.q('SELECT fates FROM reigns', one=True)['fates'])}
        self.assertIn('失势', fates[self.atk])
        self.assertEqual(game.member_class(game.get_consort(self.atk)), 'disgraced')

    def test_next_reign_niece_is_the_dowagers_when_her_aunt_was_dowager(self):
        game.run('UPDATE consorts SET rank=6, trust=0 WHERE id IN (?,?)', (self.atk, self.tgt))
        uid = self.fam(self.atk)
        self.prince(self.atk, favor=90, name='承稷')
        game.end_reign(game.cur_day())
        self.assertEqual(game.member_class(game.get_consort(self.atk)), 'dowager')
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        inh = game.family_inheritance(uid, 2)
        self.assertEqual((inh['patron'], inh['depth']), ('dowager', 1))

    def test_new_reign_gate_resets_and_family_persists(self):
        uid = self.fam(self.atk, prestige=33, estate=44)
        for i in range(3): self.past_member(uid, given=f'前{i}', death_day=1)
        game.end_reign(game.cur_day())
        f = game.q('SELECT * FROM family_pool WHERE last_user_id=?', (uid,), one=True)      # 家族退回家族池，名望、家底都留着
        self.assertEqual((f['prestige'], f['estate']), (33, 44))
        self.assertIsNone(self.frow(uid))
        game.run("UPDATE game_state SET reign_no=2")
        with patch.object(game.random, 'random', return_value=0.0):
            offers = game.ensure_family_offers(uid)
        self.assertTrue(any(o['surname'] == f['surname'] for o in offers))      # 它可能再被抽到，抽到了还是那份名望
        mine = next(o for o in offers if o['surname'] == f['surname'])
        self.assertIsNone(game.take_family_offer(uid, mine['id']))
        self.assertEqual((self.frow(uid)['prestige'], self.frow(uid)['estate']), (33, 44))
        self.assertTrue(game.family_gate(uid)[0])

    # ── 族谱与各家 ───────────────────────────────────────────────────────────

    def test_clan_page_groups_by_reign_and_shows_everything(self):
        uid = self.fam(self.atk, surname='沈', prestige=25)
        game.run("UPDATE consorts SET surname='沈', given='云', lineage='长女', entry_age=19, peak_rank=6, kids='[\"承稷（皇子）\"]', title='恭' WHERE id=?", (self.atk,))
        self.past_member(uid, reign_no=1, given='前人', reason='中毒身亡')
        self.past_member(uid, reign_no=1, given='太后', reason='先帝驾崩，圣母皇太后', survived=1)
        game.family_log_add(uid, '沈云成为圣母皇太后', 1)
        page = self.client.get('/clan').get_data(as_text=True)
        for t in ('沈氏族谱', '望族', '第 1 届', '沈云', '长女', '承稷（皇子）', '历两朝', '中毒身亡', '家族荣耀', '成为圣母皇太后', '在宫中'):
            self.assertIn(t, page)

    def test_anyone_can_read_another_clan_but_not_its_purse(self):
        uid = self.fam(self.atk, surname='沈', estate=777)
        self.fam(self.tgt, surname='顾')
        self.login(self.tgt)
        page = self.client.get(f'/clan/{uid}').get_data(as_text=True)
        self.assertIn('沈氏族谱', page)
        self.assertNotIn('家底', page)
        self.assertEqual(self.client.get('/clan/99999').status_code, 302)

    def test_clans_list_shows_all_families(self):
        self.fam(self.atk, surname='沈')
        self.fam(self.tgt, surname='顾')
        page = self.client.get('/clans').get_data(as_text=True)
        self.assertIn('沈氏', page)
        self.assertIn('顾氏', page)
        self.assertIn('你家', page)

    def test_family_page_renders_with_all_sections(self):
        uid = self.fam(self.atk, estate=50)
        self.prince(self.tgt, age_years=13)
        self.make_request(uid, 'debt', cost=70)
        page = self.client.get('/family').get_data(as_text=True)
        for t in ('家主', '家里来信', '送银子回家', '支取家底', '写家书', '替家主荐官', '家里的生意', '绸缎庄', '印子钱', '夺嫡里的家里'):
            self.assertIn(t, page)

    def test_family_page_shows_backing_request_options(self):
        uid = self.fam(self.atk)
        a = self.prince(self.tgt, age_years=13)
        self.make_request(uid, 'backing', options=[a])
        page = self.client.get('/family').get_data(as_text=True)
        self.assertIn('站这一位', page)
        self.assertIn('观望', page)

    def test_dead_daughter_can_still_view_family_and_clan(self):
        uid = self.fam(self.atk)
        game.die(self.atk, '病逝')
        self.assertEqual(self.client.get('/family').status_code, 200)
        self.assertEqual(self.client.get('/clan').status_code, 200)

    def test_family_without_a_live_daughter_cannot_act(self):
        uid = self.fam(self.atk, estate=100)
        game.die(self.atk, '病逝')
        self.client.post('/family/withdraw', data=dict(amount=50))
        self.assertEqual(self.frow(uid)['estate'], 100)

    # ── 老档迁移 ─────────────────────────────────────────────────────────────

    def test_migration_gives_legacy_users_a_family_and_numbers_their_daughters(self):
        uid = self.uid(self.atk)
        first = self.past_member(uid, given='头一位', peak=3, lineage='')
        second = self.past_member(uid, given='第二位', peak=4, lineage='')
        game.run('UPDATE consorts SET surname=?, lineage=?, seq=0 WHERE id=?', ('沈', '', self.atk))
        game.run('DELETE FROM families')
        game.init_db()
        f = self.frow(uid)
        self.assertIsNotNone(f)
        self.assertEqual(f['tier'], game.get_consort(first)['family'])
        rows = {r['id']: r for r in game.q('SELECT * FROM consorts WHERE user_id=? OR archived_user_id=? ORDER BY id', (uid, uid))}
        lineages = [rows[i]['lineage'] for i in sorted(rows)]
        self.assertEqual(lineages[0], '长女')
        self.assertTrue(lineages[1].endswith('之妹'))
        self.assertTrue(lineages[2].endswith('的堂妹'))
        self.assertEqual([rows[i]['seq'] for i in sorted(rows)], [1, 2, 3])
        game.init_db()   # 幂等
        self.assertEqual(game.q('SELECT COUNT(*) n FROM families WHERE user_id=?', (uid,), one=True)['n'], 1)

    def test_migration_skips_users_without_characters(self):
        uid = game.run("INSERT INTO users(username,password_hash,created_ts) VALUES('空',?,0)", ('x',)).lastrowid
        game.init_db()
        self.assertIsNone(self.frow(uid))

    # ── 整晚结算 ─────────────────────────────────────────────────────────────

    def test_full_settle_runs_family_ticks(self):
        uid = self.fam(self.atk, head_office=5, prestige=30, head_age_months=50 * 12)
        self.set_day(3)
        s0 = game.get_consort(self.atk)['silver']
        with patch.object(game, 'npc_schemes'):
            game.settle_day()
        f = self.frow(uid)
        self.assertTrue(f['head_age_months'] > 50 * 12 or f['head_gen'] == 1, '家主长了半岁，或者刚好在这一晚没了')

    def test_admin_page_and_reset_still_work_with_families(self):
        self.fam(self.atk)
        with self.client.session_transaction() as sess: sess['admin'] = True
        self.assertEqual(self.client.get('/admin').status_code, 200)
        self.client.post('/admin/reset', data={'confirm': '重开', 'keep_users': '1'})
        self.assertEqual(self.client.get('/admin').status_code, 200)

    # ── 后台 ─────────────────────────────────────────────────────────────────

    def admin(self):
        with self.client.session_transaction() as sess: sess['admin'] = True

    def test_admin_lists_families_and_edits_them(self):
        uid = self.fam(self.atk, surname='沈')
        self.admin()
        page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('各家族', page)
        self.assertIn('沈氏', page)
        self.client.post(f'/admin/family/{uid}', data=dict(act='edit', prestige=88, estate=1234, office=7, age=61))
        f = self.frow(uid)
        self.assertEqual((f['prestige'], f['estate'], f['head_office'], f['head_age_months']), (88, 1234, 7, 61 * 12))

    def test_admin_family_edit_rejects_junk_and_needs_admin(self):
        uid = self.fam(self.atk)
        self.client.post(f'/admin/family/{uid}', data=dict(act='edit', prestige=1, estate=1, office=1, age=40))
        self.assertNotEqual(self.frow(uid)['prestige'], 1, '没登录后台不行')
        self.admin()
        self.client.post(f'/admin/family/{uid}', data=dict(act='edit', prestige='x', estate=1, office=1, age=40))
        self.assertEqual(self.frow(uid)['prestige'], 0)
        self.client.post(f'/admin/family/{uid}', data=dict(act='edit', prestige=5, estate=1, office=99, age=40))
        self.assertEqual(self.frow(uid)['head_office'], game.OFFICE_MAX, '越界的收回范围内')
        self.assertEqual(self.client.post('/admin/family/99999', data=dict(act='edit')).status_code, 302)

    def test_admin_can_make_head_ill_recover_or_die(self):
        uid = self.fam(self.atk, head_office=6)
        self.admin()
        self.client.post(f'/admin/family/{uid}', data=dict(act='head_ill'))
        self.assertTrue(self.frow(uid)['head_ill_day'])
        self.client.post(f'/admin/family/{uid}', data=dict(act='head_ill'))
        self.assertFalse(self.frow(uid)['head_ill_day'])
        self.client.post(f'/admin/family/{uid}', data=dict(act='head_dies'))
        f = self.frow(uid)
        self.assertEqual((f['head_role'], f['head_office']), ('兄长', 5))

    def test_footer_links_to_admin_login(self):
        page = self.client.get('/clans').get_data(as_text=True)
        self.assertIn('/admin/login', page)
        self.admin()
        self.assertIn('href="/admin"', self.client.get('/clans').get_data(as_text=True))

    # ── 试玩里发现的问题 ─────────────────────────────────────────────────────

    def test_dianxuan_announces_the_real_age(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.create_member('云', age=21)
        page = self.client.get('/dianxuan').get_data(as_text=True)
        self.assertIn('年二十一', page)
        self.assertNotIn('年十五', page)

    def test_entering_the_palace_points_the_newcomer_at_the_family_page(self):
        uid = self.new_user()
        game.create_family(uid, '江', 'dali')
        self.create_member('云')
        cid = self.enter_palace(uid)
        self.assertTrue(any('家里' in m and ('嬷嬷' in m) for m in self.msgs(cid)))

    def test_create_pages_show_the_heads_starting_office(self):
        self.new_user()
        page = self.client.get('/create').get_data(as_text=True)
        self.assertIn('家主起点', page)
        self.assertIn('家主起点：参将', page)


if __name__ == '__main__':
    unittest.main()


class EmpressRankTests(unittest.TestCase):
    """皇后位是普通位分：跟其他位分一样按圣宠/德行/名额晋封，没有专门的扳倒机制，见九点十七节"""
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login

    def promote(self, cid, prestige_top=10):
        game.run('UPDATE consorts SET rank=10, prestige_top=?, favor=?, virtue=?, influence=?, rank_since_day=1 WHERE id=?',
                 (prestige_top, game.PROMOTE_FAVOR[11], game.PROMOTE_VIRTUE[11], game.PROMOTE_INFLUENCE[11] + 20, cid))
        # 晋位本身不靠掷骰，但同一次结算里家主升迁、时疫这些不相关的概率事件会消耗全局的 random 状态——
        # 不摁住它们，这条用例会不会 flaky 全看别的测试文件先跑了几次随机数，摁到 0.99 让那些支线都不触发
        with patch.object(game, 'npc_schemes'), patch.object(game.random, 'random', return_value=0.99):
            game.settle_day()

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_cannot_reach_empress_while_the_npc_holds_the_slot(self):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key='huanghou'")
        self.promote(self.atk)
        self.assertEqual(game.get_consort(self.atk)['rank'], 10, 'npc 占着唯一的名额')

    def test_reaches_empress_once_the_slot_is_free(self):
        game.run("UPDATE consorts SET status='cold' WHERE npc_key='huanghou'")
        self.promote(self.atk)
        c = game.get_consort(self.atk)
        self.assertEqual(c['rank'], 11)
        self.assertEqual(game.display_name(c), '皇后')

    def test_only_one_empress_slot(self):
        game.run("UPDATE consorts SET status='cold' WHERE npc_key='huanghou'")
        self.promote(self.atk)
        self.assertEqual(game.get_consort(self.atk)['rank'], 11)
        self.promote(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['rank'], 10, '名额已经被占了')

    def test_reaching_empress_grants_family_prestige_once(self):
        game.run("UPDATE consorts SET status='cold' WHERE npc_key='huanghou'")
        uid = game.consort_uid(game.get_consort(self.atk))
        game.create_family(uid, '沈', 'dali')
        self.promote(self.atk, prestige_top=10)   # 之前几级的名望已经拿过了，只看这一步新加的
        self.assertEqual(game.family_row(uid)['prestige'], game.PRESTIGE_RANK_GAIN[11])

    def test_no_venture_outcome_is_break_even(self):
        for k, v in game.VENTURES.items():
            self.assertNotIn(0.0, [r for _, r in v['outcomes']], f'{k} 不该再有持平')
            self.assertTrue(any(0 < r < 0.5 for _, r in v['outcomes']), f'{k} 要有「小赚」档')
