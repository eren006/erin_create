"""圣宠待遇：收入、风险与医疗时长。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game
class FavorCareTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def set_care(self,favor,streak=2):
        game.run('UPDATE consorts SET favor=?,unfavored_days=?,health=60 WHERE id=?',(favor,streak,self.atk))
        return game.get_consort(self.atk)

    def test_income_tiers_for_guiren(self):
        game.run('UPDATE consorts SET rank=4 WHERE id=?',(self.atk,))
        self.assertEqual(game.favor_stipend(self.set_care(150)),127)
        self.assertEqual(game.favor_stipend(self.set_care(40)),75)
        self.assertEqual(game.favor_stipend(self.set_care(39)),52)
        self.assertEqual(game.favor_stipend(self.set_care(0,1)),75)

    def test_newcomer_protection_and_cold_palace(self):
        c=self.set_care(0)
        game.run('UPDATE consorts SET entered_day=9 WHERE id=?',(self.atk,));c=game.get_consort(self.atk)
        self.assertEqual(game.favor_care_tier(c),'normal')
        self.assertEqual(game.ordinary_illness_chance(c,10),0)
        game.run("UPDATE consorts SET status='cold' WHERE id=?",(self.atk,))
        self.assertEqual(game.favor_stipend(game.get_consort(self.atk)),0)

    def test_base_illness_risk_and_recovery_protection(self):
        for favor,prob in [(150,.10),(40,.15),(0,.20)]:
            self.assertEqual(game.ordinary_illness_chance(self.set_care(favor),10),prob)
        game.run('UPDATE consorts SET protected_until_day=10 WHERE id=?',(self.atk,))
        self.assertEqual(game.ordinary_illness_chance(game.get_consort(self.atk),10),0)

    def cure(self,hours):
        with patch.object(game,'now_ts',return_value=100000):game.illness_cure_tick()
        with patch.object(game,'now_ts',return_value=100000+hours*3600-1):game.illness_cure_tick()
        self.assertTrue(game.get_consort(self.atk)['ill_day'])
        with patch.object(game,'now_ts',return_value=100000+hours*3600):game.illness_cure_tick()

    def test_hot_automatic_doctor_and_fast_recovery(self):
        self.set_care(150);silver=game.get_consort(self.atk)['silver']
        game.fall_ill(self.atk,10,'风寒')
        c=game.get_consort(self.atk);self.assertEqual(c['ill_treatment'],1)
        self.assertEqual(c['silver'],silver)
        game.run('UPDATE consorts SET health=20 WHERE id=?',(self.atk,))
        self.cure(6)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])
        self.assertEqual(game.get_consort(self.atk)['health'],50)

    def test_low_treated_recovers_six_hours_after_treatment(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        self.client.post(f'/treat/{self.atk}')
        with patch.object(game.random,'random',return_value=.99):
            game.resolve_illness_crises(11)          # 请了太医：夜里不掷生死
            self.assertTrue(game.get_consort(self.atk)['ill_day'])
        self.cure(6)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_untreated_low_risk_and_sister_paid_treatment(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        game.add_affinity(self.tgt,self.atk,50)
        self.login(self.tgt);silver=game.get_consort(self.tgt)['silver']
        self.client.post(f'/treat/{self.atk}')
        self.assertEqual(game.get_consort(self.tgt)['silver'],silver-game.treat_cost(game.get_consort(self.atk)))
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'],1)
        with patch.object(game.random,'random',return_value=.99):game.resolve_illness_crises(12)
        self.assertEqual(game.get_consort(self.atk)['status'],'normal')      # 请了太医的不会病死
        self.cure(6)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_untreated_low_dies_next_night(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒')
        with patch.object(game.random,'random',return_value=.21):game.resolve_illness_crises(11)
        self.assertEqual(game.get_consort(self.atk)['status'],'dead')

    def test_regaining_favor_upgrades_ongoing_care(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒');self.set_care(150)
        with patch.object(game.random,'random',return_value=.79):game.resolve_illness_crises(11)
        self.assertEqual(game.get_consort(self.atk)['ill_care'],'hot')      # 重新得宠，升级成免费诊治
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'],1)
        self.cure(6)
        self.assertFalse(game.get_consort(self.atk)['ill_day'])

    def test_income_streak_grace_then_recovers(self):
        self.set_care(0,0)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['unfavored_days'],1)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.favor_care_tier(game.get_consort(self.atk)),'low')
        self.set_care(80)
        with patch.object(game.random,'random',return_value=.999), patch.object(game,'do_bedding'):game.settle_day()
        self.assertEqual(game.get_consort(self.atk)['unfavored_days'],0)

    def test_pages_explain_income_and_care(self):
        self.set_care(150)
        for path in ('/','/help'):
            r=self.client.get(path)
            self.assertEqual(r.status_code,200)
            self.assertIn('待遇',r.get_data(as_text=True))

    def test_hot_regained_before_doctor_visit_is_free(self):
        self.set_care(0);game.fall_ill(self.atk,10,'风寒');self.set_care(150)
        silver=game.get_consort(self.atk)['silver']
        self.client.post(f'/treat/{self.atk}')
        self.assertEqual(game.get_consort(self.atk)['silver'],silver)
        self.assertEqual(game.get_consort(self.atk)['ill_care'],'hot')
        self.assertEqual(game.get_consort(self.atk)['ill_treatment'],1)


    def test_ranked_tiers_with_enough_players(self):
        ids=[self.atk]+[self.player(f'排{i}',rank=3) for i in range(9)]       # 凑够 10 个在宫玩家
        others=[i for i in ids if i!=self.atk]
        game.run("UPDATE consorts SET status='cold' WHERE user_id IS NOT NULL AND id NOT IN (%s)"%','.join('?'*len(ids)),ids)
        for i,cid in enumerate(ids): game.run('UPDATE consorts SET favor=?,unfavored_days=2,entered_day=1 WHERE id=?',(100+i*10,cid))
        game.refresh_care_tiers()
        tiers={cid:game.favor_care_tier(game.get_consort(cid)) for cid in ids}
        self.assertEqual(sorted(tiers.values()).count('hot'),2,'10 人取前 25% = 2 人')
        self.assertEqual(sorted(tiers.values()).count('low'),2,'后 25% = 2 人')
        self.assertEqual(tiers[ids[-1]],'hot');self.assertEqual(tiers[ids[0]],'low')
        game.run('UPDATE consorts SET favor=30 WHERE id=?',(ids[-1],))      # 排第一但圣宠低于门槛
        for cid in ids[:-1]: game.run('UPDATE consorts SET favor=5 WHERE id=?',(cid,))
        game.refresh_care_tiers()
        self.assertEqual(game.favor_care_tier(game.get_consort(ids[-1])),'normal','前 25% 但圣宠不到门槛不算得宠')

    def test_few_players_fall_back_to_fixed_lines(self):
        self.assertEqual(game.favor_care_tier(self.set_care(150)),'hot')
        self.assertEqual(game.favor_care_tier(self.set_care(39)),'low')

    def test_gazette_top_lists_favorites(self):
        self.set_care(150)
        r=self.client.get('/gazette')
        self.assertEqual(r.status_code,200)
        html=r.get_data(as_text=True)
        self.assertIn('圣眷最隆',html)
        self.assertIn(game.display_name(game.get_consort(self.atk)),html)

    def test_gazette_lists_todays_most_bedded(self):
        game.run('UPDATE consorts SET bed_daily_day=?,bed_daily_count=3 WHERE id=?',(game.cur_day(),self.atk))
        html=self.client.get('/gazette').get_data(as_text=True)
        self.assertIn('今日最宠幸',html)
        self.assertIn('3 次',html)

    def test_skin_unique_visible_and_validated(self):
        self.login(self.atk)
        r=self.client.post('/skin',data={'skin':'林 青霞'},follow_redirects=True)
        self.assertEqual(game.get_consort(self.atk)['skin'],'林青霞')
        self.assertIn('林青霞',self.client.get('/').get_data(as_text=True))
        self.assertIn('林青霞',self.client.get('/ranks').get_data(as_text=True))
        self.assertIn('林青霞',self.client.get('/gazette').get_data(as_text=True))
        self.login(self.tgt)
        self.client.post('/skin',data={'skin':'林青 霞'})
        self.assertEqual(game.get_consort(self.tgt)['skin'],'','重复的被拒')
        self.client.post('/skin',data={'skin':'一二三四五六七八九十一二三'})
        self.assertEqual(game.get_consort(self.tgt)['skin'],'','太长被拒')
        self.client.post('/skin',data={'skin':'张曼玉'})
        self.assertEqual(game.get_consort(self.tgt)['skin'],'张曼玉')
        self.login(self.atk)
        self.client.post('/skin',data={'skin':''})
        self.assertEqual(game.get_consort(self.atk)['skin'],'','留空清掉')

    def test_skin_form_moves_to_bottom_after_set(self):
        self.login(self.atk)
        html=self.client.get('/').get_data(as_text=True)
        self.assertLess(html.index('name="skin"'),html.index('退出'))
        self.assertLess(html.index('name="skin"'),html.index('me-top"') if 'me-top"' in html else len(html))
        game.run("UPDATE consorts SET skin='周迅' WHERE id=?",(self.atk,))
        html=self.client.get('/').get_data(as_text=True)
        self.assertGreater(html.index('name="skin"'),html.index('<section class="me-top">'))
        self.assertLess(html.index('name="skin"'),html.index('退出'))

    def test_low_influence_demotes_after_two_nights_and_warns(self):
        game.run('UPDATE consorts SET rank=4, influence=1, entered_day=1, influence_low_days=0, status=? WHERE id=?',('normal',self.atk))
        html=self.client.get('/').get_data(as_text=True) if self.login(self.atk) is None or True else ''
        self.assertIn('势力不足，有降位风险',html)
        game.influence_check(game.get_consort(self.atk),10)
        self.assertEqual(game.get_consort(self.atk)['rank'],4,'第一晚只记一晚')
        self.assertEqual(game.get_consort(self.atk)['influence_low_days'],1)
        self.assertIn('今晚结算还不够就降为',self.client.get('/').get_data(as_text=True))
        game.influence_check(game.get_consort(self.atk),11)
        self.assertEqual(game.get_consort(self.atk)['rank'],3,'连着两晚降一级')
        self.assertEqual(game.get_consort(self.atk)['influence_low_days'],0)

    def test_enough_influence_resets_counter_and_newcomers_exempt(self):
        game.run('UPDATE consorts SET rank=4, influence=1, entered_day=1, influence_low_days=1 WHERE id=?',(self.atk,))
        game.run('UPDATE consorts SET influence=50 WHERE id=?',(self.atk,))
        game.influence_check(game.get_consort(self.atk),10)
        self.assertEqual(game.get_consort(self.atk)['influence_low_days'],0)
        game.run('UPDATE consorts SET influence=1, entered_day=9 WHERE id=?',(self.atk,))
        for d in (10,11): game.influence_check(game.get_consort(self.atk),d)
        self.assertEqual(game.get_consort(self.atk)['rank'],4,'新人前 3 天不查')

    def test_influence_demotion_squeezes_worst_when_lower_rank_full(self):
        game.run("UPDATE consorts SET status='cold' WHERE rank IN (4,5) AND id!=?", (self.atk,))
        guis=[self.player(f'贵{i}',rank=4) for i in range(game.RANK_SLOTS[4])]
        for i,cid in enumerate(guis): game.run('UPDATE consorts SET favor=?, influence=50 WHERE id=?',(50+i,cid))
        game.run('UPDATE consorts SET rank=5, influence=0, entered_day=1, favor=500, influence_low_days=1 WHERE id=?',(self.atk,))
        game.influence_check(game.get_consort(self.atk),20)
        self.assertEqual(game.get_consort(self.atk)['rank'],4,'嫔降为贵人')
        self.assertEqual(game.get_consort(guis[0])['rank'],3,'贵人满员，圣宠最低的被挤下去')
        self.assertEqual(sum(1 for cid in guis+[self.atk] if game.get_consort(cid)['rank']==4),game.RANK_SLOTS[4])
