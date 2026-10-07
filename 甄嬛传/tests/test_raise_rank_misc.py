"""2026-10-07：妃位以上养皇子/嫔位以上养公主、催产丹、避孕、梳洗容貌上限 65"""
import time
import unittest
import test_heirs

game = test_heirs.game


class RaiseRankMiscTests(unittest.TestCase):
    setUp = test_heirs.fixtures.LifecycleTests.setUp
    tearDown = test_heirs.fixtures.LifecycleTests.tearDown
    player = test_heirs.fixtures.LifecycleTests.player
    login = test_heirs.fixtures.LifecycleTests.login
    heir = test_heirs.HeirTests.heir

    def test_min_rank_by_gender(self):
        self.assertEqual(game.raise_min_rank({'gender': '皇子'}), 6)
        self.assertEqual(game.raise_min_rank({'gender': '公主'}), 5)

    def test_pin_cannot_entrust_target_for_son(self):
        pin = self.player('嫔', rank=5)
        self.assertNotIn(pin, [t['id'] for t in game.entrust_candidates(game.get_consort(self.tgt), 6)])
        game.add_affinity(self.tgt, pin, 60)
        self.assertIn(pin, [t['id'] for t in game.entrust_candidates(game.get_consort(self.tgt), 5)])

    def test_cuisheng_shortens_pregnancy(self):
        game.run('UPDATE consorts SET pregnant_since=?, pregnancy_started_ts=? WHERE id=?', (game.cur_day(), time.time(), self.atk))
        game.inv_add(self.atk, 'cuisheng', 1)
        self.login(self.atk)
        before = game.get_consort(self.atk)['pregnancy_started_ts']
        self.client.post('/shop/use/cuisheng')
        self.assertAlmostEqual(before - game.get_consort(self.atk)['pregnancy_started_ts'], 6 * 3600, delta=1)

    def test_contraception_needs_two_births(self):
        self.login(self.atk)
        self.client.post('/contraception')
        self.assertEqual(game.get_consort(self.atk)['contraception'], 0)
        self.heir(self.atk); self.heir(self.atk)
        self.client.post('/contraception')
        c = game.get_consort(self.atk)
        self.assertEqual(c['contraception'], 1)
        self.assertEqual(game.pregnancy_chance(c), 0.0)
        game.run('UPDATE consorts SET pregnancy_misses=11 WHERE id=?', (self.atk,))
        self.assertEqual(game.pregnancy_chance(game.get_consort(self.atk)), 0.0, '避孕时保底也不生效')

    def test_own_grooming_caps_at_65(self):
        game.run('UPDATE consorts SET energy=8, silver=500, appearance=64 WHERE id=?', (self.atk,))
        c = game.get_consort(self.atk)
        game.do_groom(c, game.action_config(c, 'groom'))
        self.assertEqual(game.get_consort(self.atk)['appearance'], 65)
        c = game.get_consort(self.atk)
        game.do_groom(c, game.action_config(c, 'groom'))
        self.assertEqual(game.get_consort(self.atk)['appearance'], 65)

    def test_influence_decays_only_above_rank_requirement(self):
        need = game.PROMOTE_INFLUENCE.get(game.get_consort(self.atk)['rank'], 0)
        game.run('UPDATE consorts SET influence=?, entered_day=-100 WHERE id=?', (need + 5, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need + 4)
        game.run('UPDATE consorts SET influence=? WHERE id=?', (need, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need)
        game.run("UPDATE consorts SET influence=?, status='cold' WHERE id=?", (need + 5, self.atk))
        game.influence_check(game.get_consort(self.atk), game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], need + 5)

    def test_new_arts_and_no_repeat_perform(self):
        self.assertIn('琵琶', game.ARTS); self.assertIn('笛子', game.ARTS)
        for a in game.ARTS: self.assertIn(a, game.BANQUET_PIECES); self.assertIn(a, game.BANQUET_PROPS)
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.login(self.atk)
        self.client.post('/act/perform', data=dict(art='琵琶'))
        self.assertEqual(game.get_consort(self.atk)['last_perform_art'], '琵琶')
        game.run('DELETE FROM daily_counters')
        energy = game.get_consort(self.atk)['energy']
        self.client.post('/act/perform', data=dict(art='琵琶'))
        self.assertEqual(game.get_consort(self.atk)['energy'], energy, '同一样才艺连着献被拒绝，不扣精力')
        self.client.post('/act/perform', data=dict(art='笛子'))
        self.assertEqual(game.get_consort(self.atk)['last_perform_art'], '笛子')

    def test_banquet_winner_gets_harder_to_win_again(self):
        from unittest.mock import patch
        c = game.get_consort(self.atk)
        with patch.object(game.random, 'uniform', return_value=10):
            fresh = game.banquet_score(c, '琴', 0)[0]
            game.run('UPDATE consorts SET banquet_wins=2 WHERE id=?', (self.atk,))
            stale = game.banquet_score(game.get_consort(self.atk), '琴', 0)[0]
            game.run('UPDATE consorts SET banquet_wins=9 WHERE id=?', (self.atk,))
            capped = game.banquet_score(game.get_consort(self.atk), '琴', 0)[0]
        self.assertEqual(fresh - stale, 2 * game.BANQUET_STALE_PER_WIN)
        self.assertEqual(fresh - capped, game.BANQUET_STALE_MAX)

    def test_arts_notice_once_and_kneel_gazette(self):
        n = lambda: game.q("SELECT COUNT(*) n FROM gazette WHERE text LIKE '%才艺上新%'", one=True)['n']
        game.gazette('占位')
        game.run('UPDATE game_state SET arts_notice_version=0')
        game.init_db(); game.init_db()
        self.assertEqual(n(), 1)

    def test_yinzhen_back_charge_once(self):
        game.inv_add(self.atk, 'yinzhen', 2)
        game.run('UPDATE consorts SET silver=1000 WHERE id=?', (self.atk,))
        game.run('UPDATE game_state SET yinzhen_price_version=0')
        game.init_db(); game.init_db()
        self.assertEqual(game.get_consort(self.atk)['silver'], 1000 - 2 * (game.YINZHEN_PRICE - game.YINZHEN_OLD_PRICE))

    def test_chastise_feed_names_the_victim(self):
        low = self.player('小答应', rank=2)
        game.run('UPDATE consorts SET energy=8 WHERE id=?', (self.atk,))
        self.login(self.atk)
        self.client.post('/act/chastise', data=dict(target_id=low, mode='kneel'))
        txt = ' '.join(r['text'] for r in game.q('SELECT text FROM daily_feed'))
        self.assertIn(game.display_name(game.get_consort(low)), txt)
        self.assertIn('罚', txt)

    def test_garden_tan_starts_on_oct_8(self):
        from datetime import datetime
        from unittest.mock import patch
        self.assertFalse(game.garden_tan_on(datetime(2026, 10, 7, 23, 59, tzinfo=game.TZ)))
        self.assertTrue(game.garden_tan_on(datetime(2026, 10, 8, 0, 0, tzinfo=game.TZ)))
        game.run('UPDATE consorts SET silver=500, appearance=50 WHERE id=?', (self.atk,))
        self.login(self.atk)
        with patch.object(game, 'garden_tan_on', return_value=True), patch.object(game.random, 'random', return_value=0.0):
            self.client.post('/garden/plant', data=dict(crop='baicai', slot=1))
        self.assertEqual(game.get_consort(self.atk)['appearance'], 50 - game.GARDEN_TAN_LOSS)

    def test_garden_sell_daily_cap(self):
        game.run('UPDATE consorts SET silver=0 WHERE id=?', (self.atk,))
        game.stock_add(self.atk, 'lingzhi', 20)      # 35 两一个，共 700
        self.login(self.atk)
        self.client.post('/garden/sell', data=dict(crop='all'))
        self.assertEqual(game.get_consort(self.atk)['silver'], 385)      # 11 个，再多一个就超 400
        self.assertEqual(game.stock_of(self.atk)['lingzhi'], 9)
        self.client.post('/garden/sell', data=dict(crop='all'))
        self.assertEqual(game.get_consort(self.atk)['silver'], 385)

    def test_birth_gender_pref(self):
        from unittest.mock import patch
        game.run("UPDATE consorts SET birth_gender_pref='皇子' WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET pregnant_since=?,pregnancy_started_ts=1,prenatal='{}' WHERE id=?", (game.cur_day(), self.atk))
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else __import__('random').Random(1).choice(seq)):
            game.resolve_births(game.cur_day(), False)
        self.assertTrue(all(h['gender'] == '皇子' for h in game.q('SELECT gender FROM heirs WHERE mother_id=?', (self.atk,))))

    def test_adopt_influence_granted_and_revoked(self):
        mother = self.player('生母', rank=3)
        hid = self.heir(mother, caretaker=0, born=game.cur_day())
        game.run('UPDATE consorts SET influence=10 WHERE id=?', (self.atk,))
        game.run('INSERT INTO heir_claims (consort_id, heir_id, day) VALUES (?,?,?)', (self.atk, hid, game.cur_day()))
        game.heir_orphan_tick(game.cur_day())
        self.assertEqual(game.get_consort(self.atk)['influence'], 10 + game.ADOPT_INFLUENCE)
        self.assertEqual(game.q('SELECT adopt_bonus_to FROM heirs WHERE id=?', (hid,), one=True)['adopt_bonus_to'], self.atk)
        game.adopt_bonus_revoke(hid)
        self.assertEqual(game.get_consort(self.atk)['influence'], 10)
        game.adopt_bonus_revoke(hid)
        self.assertEqual(game.get_consort(self.atk)['influence'], 10, '只扣一次')
        own = self.heir(self.atk)
        game.adopt_bonus_grant(self.atk, own)
        self.assertEqual(game.get_consort(self.atk)['influence'], 10, '生母自己带不算收养')


if __name__ == '__main__':
    unittest.main()
