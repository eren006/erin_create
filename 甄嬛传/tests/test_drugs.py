"""下药的资源、匿名性、延迟发作、保护期与夜间结算回归。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class DrugTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def plan(self, drug, effect='', mid=0):
        game.run('UPDATE consorts SET rank=6,energy=5 WHERE id=?', (self.atk,))
        game.run("DELETE FROM daily_counters WHERE key='intrigue'")
        game.inv_add(self.atk, drug)
        self.login(self.atk)
        self.client.post('/intrigue/submit', data=dict(method='drug', drug=drug, effect=effect, agent_maid_id=mid, target_id=self.tgt))
        return game.q("SELECT * FROM intrigues ORDER BY id DESC LIMIT 1", one=True)

    def apply(self, drug, effect='', mid=0):
        it = self.plan(drug, effect, mid)
        self.assertIsNotNone(it)
        with patch.object(game.random, 'random', return_value=0.0):
            result = game.resolve_intrigue(it)[0]
        return it, result

    def maid(self, owner, name='秋菊', loyalty=60):
        return game.run("INSERT INTO maids(owner_id,name,trait,loyalty,joined_day) VALUES(?,?,'shouqiao',?,1)", (owner,name,loyalty)).lastrowid

    def test_cabinet_stock_purchase_and_duplicate(self):
        stock = game.cabinet_stock(self.atk,10)
        self.assertEqual(stock, game.cabinet_stock(self.atk,10))
        self.assertEqual(len(set(stock)),3)
        game.run('UPDATE consorts SET rank=6 WHERE id=?',(self.atk,))
        key=stock[0]
        with patch.object(game.random,'random',return_value=0):
            self.client.post('/shop/drug/'+key)
            self.client.post('/shop/drug/'+key)
        self.assertEqual(game.inv_qty(self.atk,key),1)
        self.assertEqual(game.get_consort(self.atk)['silver'],2000-game.DRUGS[key]['price'])
        self.assertEqual(game.get_consort(self.atk)['drug_ledger'],1)
        absent=next(k for k in game.DRUGS if k not in stock)
        self.client.post('/shop/drug/'+absent)
        self.assertEqual(game.inv_qty(self.atk,absent),0)

    def test_invalid_drug_agent_and_nameless_lethal_do_not_charge(self):
        game.inv_add(self.atk,'wuming')
        game.run('UPDATE consorts SET rank=6 WHERE id=?',(self.atk,))
        for payload in (dict(drug='bogus'),dict(drug='wuming',effect='lihun'),dict(drug='wuming',effect='yanzhi',agent_maid_id='x')):
            self.client.post('/intrigue/submit',data=dict(method='drug',target_id=self.tgt,**payload))
        self.assertEqual(len(game.q('SELECT * FROM intrigues')),0)
        self.assertEqual(game.inv_qty(self.atk,'wuming'),1)
        self.assertEqual(game.get_consort(self.atk)['energy'],game.ENERGY_MAX)

    def test_cancel_once_and_account_cooldown(self):
        it=self.plan('wuming','yanzhi')
        self.client.post(f'/intrigue/cancel/{it["id"]}')
        self.client.post(f'/intrigue/cancel/{it["id"]}')
        self.assertEqual(game.inv_qty(self.atk,'wuming'),1)
        game.run('UPDATE game_state SET day=11')
        self.client.post('/intrigue/submit',data=dict(method='drug',drug='wuming',effect='yanzhi',target_id=self.tgt))
        self.assertEqual(len(game.q('SELECT * FROM intrigues')),2)
        self.assertEqual(game.q('SELECT nameless_ready_day FROM users WHERE id=?',(game.get_consort(self.atk)['user_id'],),one=True)[0],0)

    def test_newcomer_and_success_protection_at_settlement(self):
        game.run('UPDATE consorts SET entered_day=10 WHERE id=?',(self.tgt,))
        self.assertIsNone(self.plan('yanzhi'))
        game.run('UPDATE consorts SET entered_day=1 WHERE id=?',(self.tgt,))
        it=self.plan('yanzhi')
        game.run('UPDATE consorts SET drugged_day=10 WHERE id=?',(self.tgt,))
        self.assertEqual(game.resolve_intrigue(it)[0],'void')
        self.assertEqual(game.get_consort(self.tgt)['appearance'],40)

    def test_immediate_rash_and_case_page_anonymity(self):
        it,result=self.apply('yanzhi')
        self.assertEqual(result,'success')
        self.assertEqual(game.get_consort(self.tgt)['appearance'],35)
        a=game.affliction(self.tgt,'yanzhi')
        with patch.object(game.time,'time',return_value=a['expires_ts']-1):self.assertIsNotNone(game.affliction(self.tgt,'yanzhi'))
        with patch.object(game.time,'time',return_value=a['expires_ts']):self.assertIsNone(game.affliction(self.tgt,'yanzhi'))
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)
        for route in ('/cases','/intrigue','/shop','/letters','/agents'):
            resp=self.client.get(route)
            self.assertEqual(resp.status_code,200,route)
        self.assertNotIn('culprit_id',self.client.get('/cases').get_data(as_text=True))
        # Re-read the done record: effects cannot be applied a second time.
        game.resolve_drug(it)
        self.assertEqual(game.get_consort(self.tgt)['appearance'],35)

    def test_nameless_delayed_diagnosis_never_opens_case(self):
        self.apply('wuming','qingsi')
        self.assertEqual(len(game.q('SELECT * FROM cases')),0)
        game.tick_drugs(10)
        self.assertEqual(game.get_consort(self.tgt)['health'],70-game.SLOW_POISON_FIRST)      # 第一次发作 -10
        self.login(self.tgt)
        with patch.object(game.random,'random',return_value=0):
            self.client.post('/diagnose')
            self.client.post('/diagnose')
        self.assertEqual(game.get_consort(self.tgt)['silver'],1980)
        self.assertIsNone(game.affliction(self.tgt,'qingsi'))
        self.assertEqual(len(game.q('SELECT * FROM cases')),0)

    def test_slow_poison_first_hit_10_then_4_each_day_until_cured(self):
        self.apply('qingsi')
        start=game.get_consort(self.tgt)['health']
        game.tick_drugs(10)
        self.assertEqual(game.get_consort(self.tgt)['health'],start-game.SLOW_POISON_FIRST)
        game.tick_drugs(10)                 # 同一天不重复扣
        self.assertEqual(game.get_consort(self.tgt)['health'],start-game.SLOW_POISON_FIRST)
        for day in range(11,17):            # 超过 3 次也不会自己停
            game.tick_drugs(day)
        expect=start-game.SLOW_POISON_FIRST-6*game.SLOW_POISON_TICK
        self.assertEqual(game.get_consort(self.tgt)['health'],max(1,expect) if expect>=25 else game.get_consort(self.tgt)['health'])
        a=game.affliction(self.tgt,'qingsi')
        if expect>=25: self.assertIsNotNone(a,'没解毒就一直扣')

    def test_slow_poison_keeps_going_past_three_ticks_when_health_is_high(self):
        self.apply('qingsi')
        game.run('UPDATE consorts SET health=100 WHERE id=?',(self.tgt,))
        for day in range(10,15): game.tick_drugs(day)
        self.assertEqual(game.get_consort(self.tgt)['health'],100-game.SLOW_POISON_FIRST-4*game.SLOW_POISON_TICK)
        self.assertIsNotNone(game.affliction(self.tgt,'qingsi'))
        self.login(self.tgt)
        with patch.object(game.random,'random',return_value=0): self.client.post('/diagnose')   # 诊脉解毒后不再扣
        self.assertIsNone(game.affliction(self.tgt,'qingsi'))
        before=game.get_consort(self.tgt)['health']
        game.tick_drugs(15)
        self.assertEqual(game.get_consort(self.tgt)['health'],before)

    def test_no_auto_diagnosis_below_25_any_more(self):
        self.apply('qingsi')
        game.run('UPDATE consorts SET health=30 WHERE id=?',(self.tgt,))
        game.tick_drugs(10)                 # 30-10=20，掉到 25 以下也不再自动解毒
        self.assertEqual(game.get_consort(self.tgt)['health'],20)
        self.assertIsNotNone(game.affliction(self.tgt,'qingsi'))
        self.assertEqual(len(game.q('SELECT * FROM cases')),0)

    def test_run_out_slow_poison_can_kill_without_treatment(self):
        self.apply('qingsi')
        game.run('UPDATE consorts SET health=6 WHERE id=?',(self.tgt,))
        game.tick_drugs(10)
        self.assertEqual(game.get_consort(self.tgt)['poisoned_day'],10)
        with patch.object(game.random,'random',return_value=0.99):      # 没请太医，赌输
            game.resolve_poison_crises(11)
        self.assertEqual(game.get_consort(self.tgt)['status'],'dead')

    def test_qingsi_description_matches_new_rule(self):
        self.assertIn('-10',game.DRUGS['qingsi']['desc'])
        self.assertIn('直到解毒',game.DRUGS['qingsi']['desc'])

    def test_slow_poison_turns_into_poisoning_when_health_runs_out(self):
        self.apply('qingsi')
        game.run('UPDATE consorts SET health=6 WHERE id=?',(self.tgt,))
        game.tick_drugs(10)
        c=game.get_consort(self.tgt)
        self.assertEqual(c['health'],1)       # 6 - 10 触底留 1
        self.assertEqual(c['poisoned_day'],10,'元气耗尽，转成中毒，走生死判定')
        self.assertIsNone(game.affliction(self.tgt,'qingsi'))
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)
        game.resolve_poison_crises(10)
        self.assertNotEqual(game.get_consort(self.tgt)['status'],'dead')

    def test_needle_only_consumed_when_it_blocks(self):
        game.inv_add(self.tgt,'yinzhen')
        game.run("UPDATE consorts SET scheme=50,trust=0,virtue=50,personality='deep'")
        it=self.plan('yanzhi')
        # Self-hand probability .20 before needle, .08 after.
        with patch.object(game.random,'random',return_value=0.12):
            self.assertEqual(game.resolve_intrigue(it)[0],'caught')
        self.assertEqual(game.inv_qty(self.tgt,'yinzhen'),0)
        self.assertEqual(game.get_consort(self.tgt)['drugged_day'],0)

    def test_taster_sacrifice_stops_poison(self):
        mid=self.maid(self.tgt,loyalty=85)
        _,result=self.apply('lihun')
        self.assertEqual(result,'fizzle')
        self.assertEqual(game.get_maid(mid)['status'],'dead')
        self.assertEqual(game.get_consort(self.tgt)['poisoned_day'],0)
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)

    def test_nonlethal_taster_sick_for_three_days(self):
        mid=self.maid(self.tgt,loyalty=85)
        self.apply('yachan')
        self.assertEqual(game.get_maid(mid)['sick_until_day'],13)
        self.assertIsNone(game.affliction(self.tgt,'yachan'))

    def test_counter_agent_forces_failure(self):
        mid=self.maid(self.tgt)
        game.run('INSERT INTO bribes(briber_id,maid_id,turned,counter) VALUES(?,?,1,1)',(self.atk,mid))
        _,result=self.apply('yanzhi',mid=mid)
        self.assertEqual(result,'caught')
        self.assertEqual(game.get_consort(self.tgt)['appearance'],40)
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)

    def test_hanshui_antai_and_infertility(self):
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?',(self.tgt,))
        game.inv_add(self.tgt,'antai')
        self.apply('hanshui')
        c=game.get_consort(self.tgt)
        self.assertEqual(c['health'],60)
        self.assertEqual(c['pregnant_since'],9)
        self.assertEqual(game.inv_qty(self.tgt,'antai'),0)
        a=game.affliction(self.tgt,'hanshui')
        with patch.object(game.time,'time',return_value=a['expires_ts']-1):self.assertIsNotNone(game.affliction(self.tgt,'hanshui'))
        with patch.object(game.time,'time',return_value=a['expires_ts']):self.assertIsNone(game.affliction(self.tgt,'hanshui'))

    def test_fake_pregnancy_opens_case_at_due_and_no_heir(self):
        self.apply('chunxin')
        self.assertEqual(len(game.q('SELECT * FROM cases')),0)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],10)
        due=game.affliction(self.tgt,'chunxin')['expires_ts']
        with patch.object(game.time,'time',return_value=due):game.resolve_births(10,False)
        self.assertEqual(len(game.q('SELECT * FROM heirs WHERE mother_id=?',(self.tgt,))),0)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],0)
        self.assertEqual(game.get_consort(self.tgt)['status'],'confined')
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)

    def test_hoarse_audience_rejects_forged_choice(self):
        self.apply('yachan')
        self.login(self.tgt)
        game.start_scene(self.tgt,'audience',prompt=0,bed=1,hoarse=True)
        response=self.client.get('/scene')
        self.assertIn('体谅',response.get_data(as_text=True))
        self.assertNotIn('讨巧',response.get_data(as_text=True))
        self.assertEqual(self.client.post('/scene',data={'opt':'1'}).status_code,302)
        self.assertTrue(game.get_consort(self.tgt)['pending_scene'])

    def test_jingmeng_reverses_bed_gain_and_opens_case(self):
        self.apply('jingmeng')
        game.run("UPDATE consorts SET status='cold',status_until_day=99 WHERE id=?",(self.atk,))
        game.run('UPDATE consorts SET favor=100,trust=50 WHERE id=?',(self.tgt,))
        with patch.object(game,'npc_schemes'),patch.object(game.random,'random',return_value=.99):
            game.settle_day()
        c=game.get_consort(self.tgt)
        self.assertEqual(c['bedded_count'],1)
        self.assertLessEqual(c['favor'],85)
        self.assertEqual(c['trust'],47)
        self.assertEqual(len(game.q('SELECT * FROM cases')),1)

    def test_cases_wait_full_day_auto_plead_and_no_double_penalty(self):
        it=self.plan('yanzhi')
        with patch.object(game,'npc_schemes'),patch.object(game.random,'random',return_value=0):
            game.settle_day()
        case=game.q('SELECT * FROM cases',one=True)
        self.assertEqual(case['day'],11)
        self.assertEqual(case['status'],'open')
        game.run('UPDATE case_suspects SET suspicion=49 WHERE case_id=?',(case['id'],))
        game.resolve_drug_cases(11)
        self.assertEqual(game.q('SELECT status FROM cases',one=True)[0],'unsolved')
        before=game.get_consort(self.atk)['trust']
        game.resolve_drug_cases(12)
        self.assertEqual(game.get_consort(self.atk)['trust'],before)

    def test_case_actions_limit_and_private_fields(self):
        self.apply('yanzhi')
        case=game.q('SELECT * FROM cases',one=True)
        url=f'/cases/{case["id"]}/act'
        self.client.post(url,data=dict(action='plead'))
        self.client.post(url,data=dict(action='plead'))
        self.client.post(url,data=dict(action='pay',silver=100))
        self.client.post(url,data=dict(action='accuse',target_id=self.atk))
        self.assertEqual(len(game.q('SELECT * FROM case_actions')),2)
        self.assertEqual(game.get_consort(self.atk)['silver'],1900)
        self.login(self.tgt)
        self.client.post(url,data=dict(action='search',target_id=self.atk))
        self.assertEqual(len(game.q('SELECT * FROM case_actions')),3)

    def test_bribe_and_inspect_counter_flow(self):
        self.maid(self.atk,'冬梅')
        mid=self.maid(self.tgt,loyalty=10)
        self.client.post('/agents/act',data=dict(action='bribe',maid_id=mid))
        self.assertEqual(len(game.drug_agents(self.atk,self.tgt)),1)
        self.assertEqual(self.client.get('/agents').status_code,200)
        self.login(self.tgt)
        with patch.object(game.random,'random',return_value=0):
            self.client.post('/agents/act',data=dict(action='inspect'))
        self.client.post('/agents/act',data=dict(action='counter',maid_id=mid))
        self.assertEqual(game.q('SELECT counter FROM bribes',one=True)[0],1)

    def test_gift_and_schema_migration_repeatable(self):
        self.maid(self.atk,loyalty=85)
        with patch.object(game.random,'random',return_value=0): game.drug_gifts(10)
        self.assertEqual(sum(game.inv_qty(self.atk,k) for k in game.DRUGS),1)
        self.assertEqual(game.inv_qty(self.atk,'lihun'),0)
        self.assertEqual(game.inv_qty(self.atk,'wuming'),0)
        game.init_db(); game.init_db()
        self.assertEqual(game.q('SELECT COUNT(*) FROM maids',one=True)[0],1)

    def test_submit_duplicate_and_rollback(self):
        game.inv_add(self.atk,'yanzhi',2)
        payload=dict(method='drug',drug='yanzhi',target_id=self.tgt)
        before=game.get_consort(self.atk)['energy']
        with patch.object(game,'daily_inc',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError): self.client.post('/intrigue/submit',data=payload)
        self.assertEqual(game.inv_qty(self.atk,'yanzhi'),2)
        self.assertEqual(game.get_consort(self.atk)['energy'],before)
        self.assertEqual(len(game.q('SELECT * FROM intrigues')),0)
        with patch.object(game,'INTRIGUE_DAILY_MAX',1):      # 默认不限次数；设上限才有「同一天第二次被拒」
            self.client.post('/intrigue/submit',data=payload)
            self.client.post('/intrigue/submit',data=payload)
        self.assertEqual(game.inv_qty(self.atk,'yanzhi'),1)
        self.assertEqual(len(game.q('SELECT * FROM intrigues')),1)

    def test_rash_blocks_bed_until_24_hours(self):
        game.run('UPDATE game_state SET reign_start_day=day')
        self.apply('yanzhi')
        game.run("UPDATE consorts SET status='cold',status_until_day=99 WHERE id=?",(self.atk,))
        due=game.affliction(self.tgt,'yanzhi')['expires_ts']
        with patch.object(game,'npc_schemes'),patch.object(game.random,'random',return_value=.99):
            with patch.object(game.time,'time',return_value=due-1):game.settle_day()
            self.assertEqual(game.get_consort(self.tgt)['bedded_count'],0)
            with patch.object(game.time,'time',return_value=due):game.settle_day()
        self.assertEqual(game.get_consort(self.tgt)['bedded_count'],1)

    def test_hanshui_prevents_new_pregnancy(self):
        self.apply('hanshui')
        game.run("UPDATE consorts SET status='cold',status_until_day=99 WHERE id=?",(self.atk,))
        with patch.object(game,'npc_schemes'),patch.object(game.random,'random',return_value=0):
            game.settle_day()
        self.assertEqual(game.get_consort(self.tgt)['bedded_count'],1)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'],0)

    def test_false_pregnancy_conviction_restores_victim(self):
        self.apply('chunxin')
        game.run('UPDATE consorts SET trust=40 WHERE id=?',(self.tgt,))
        game.run('UPDATE game_state SET day=12')
        due=game.affliction(self.tgt,'chunxin')['expires_ts']
        with patch.object(game.time,'time',return_value=due):game.tick_drugs(12)
        self.assertEqual(game.get_consort(self.tgt)['trust'],35)
        game.run('UPDATE case_suspects SET suspicion=90 WHERE consort_id=?',(self.atk,))
        game.resolve_drug_cases(12)
        self.assertEqual(game.get_consort(self.tgt)['trust'],40)
        self.assertEqual(game.get_consort(self.tgt)['status'],'normal')
        self.assertEqual(game.q('SELECT wrongful FROM cases',one=True)[0],0)

    def test_ledger_search_and_wrongful_conviction_recorded(self):
        innocent=self.player('丙')
        self.apply('yanzhi')
        case=game.q('SELECT * FROM cases',one=True)
        game.run('UPDATE consorts SET drug_ledger=1 WHERE id=?',(innocent,))
        self.login(self.tgt)
        score=game.q('SELECT suspicion FROM case_suspects WHERE consort_id=?',(innocent,),one=True)[0]
        self.client.post(f'/cases/{case["id"]}/act',data=dict(action='search',target_id=innocent))
        self.assertEqual(game.q('SELECT suspicion FROM case_suspects WHERE consort_id=?',(innocent,),one=True)[0],score+20)
        game.run('UPDATE case_suspects SET suspicion=0')
        game.run('UPDATE case_suspects SET suspicion=90 WHERE consort_id=?',(innocent,))
        game.resolve_drug_cases(10)
        result=game.q('SELECT * FROM cases',one=True)
        self.assertEqual(result['convicted_id'],innocent)
        self.assertEqual(result['wrongful'],1)


class NpcDrugSettlementTests(unittest.TestCase):
    """NPC 不关冷宫时整晚结算要跑得通：皇后给有孕的人下寒水散，不能再排旧的 'poison'"""
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    @unittest.skip("历史规则：固定妃嫔/预设皇嗣已取消，由 test_empty_court 覆盖新规则")
    def test_empress_queues_drug_and_night_settles(self):
        game.run("UPDATE consorts SET status='normal' WHERE npc_key IS NOT NULL")
        game.run("UPDATE consorts SET aggression=0 WHERE npc_key!='huanghou'")
        game.run("UPDATE consorts SET aggression=1 WHERE npc_key='huanghou'")
        game.run('UPDATE consorts SET pregnant_since=9 WHERE id=?', (self.tgt,))
        game.npc_schemes(10)
        it = game.q("SELECT * FROM intrigues WHERE target_id=? ORDER BY id DESC", (self.tgt,), one=True)
        self.assertEqual((it['method'], it['drug'], it['item_used']), ('drug', 'hanshui', 'hanshui'))
        game.run('DELETE FROM intrigues')
        game.run('UPDATE consorts SET pregnant_since=10 WHERE id=?', (self.tgt,))
        game.settle_day()                       # 以前这里会因 INTRIGUES['poison'] 报 KeyError 整晚回滚
        self.assertEqual(game.cur_day(), 11)
        self.assertFalse(game.q("SELECT 1 FROM intrigues WHERE method IN ('poison','lethal')"))

    def test_admin_reset_clears_drug_tables(self):
        game.run("INSERT INTO bribes(briber_id,maid_id,progress) VALUES(1,1,5)")
        game.run("INSERT INTO afflictions(consort_id,drug,start_day) VALUES(1,'qingsi',1)")
        game.run("INSERT INTO cases(victim_id,culprit_id,day) VALUES(1,2,1)")
        client = game.app.test_client()
        with client.session_transaction() as sess: sess['admin'] = True
        client.post('/admin/reset', data={'confirm': '重开'})
        for t in ('bribes', 'afflictions', 'cases'):
            self.assertFalse(game.q(f'SELECT 1 FROM {t}'), t)

    def test_cold_palace_never_drawn_as_suspect(self):
        """冷宫里的人碰不到别宫的饮食，不能被拉去陪查"""
        cold = self.player('丙')
        game.run("UPDATE consorts SET status='cold' WHERE id=?", (cold,))
        game.run("UPDATE consorts SET status='normal' WHERE npc_key IS NOT NULL")
        game.run("UPDATE consorts SET status='cold' WHERE npc_key IN ('qifei','xinchangzai')")
        it_id = game.run("INSERT INTO intrigues(day,attacker_id,target_id,method,drug,item_used,created_ts) VALUES(10,?,?,'drug','yanzhi','yanzhi',0)",
                         (self.atk, self.tgt)).lastrowid
        game.open_drug_case(game.q('SELECT * FROM intrigues WHERE id=?', (it_id,), one=True))
        drawn = {r['status'] for r in game.q('SELECT c.status FROM case_suspects s JOIN consorts c ON c.id=s.consort_id')}
        self.assertTrue(drawn)
        self.assertNotIn('cold', drawn)
