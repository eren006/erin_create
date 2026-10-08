"""皇嗣的容貌（随母亲）与气质（按容貌每 20 一档，每档 10 种里随机一种）"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HeirLooksTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def deliver(self, cid):
        game.run("UPDATE consorts SET pregnant_since=?,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?", (game.cur_day(), cid))
        with patch.object(game.time, 'time', return_value=186400), patch.object(game, 'preterm_chance', return_value=0), patch.object(game, 'TWIN_CHANCE', 0):      # 避开随机早产夭折、双胞胎
            game.resolve_births(game.cur_day(), False)
        return game.q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id DESC", (cid,), one=True)

    def test_library_has_five_tiers_of_ten_unique_temperaments_with_meanings(self):
        self.assertEqual(len(game.TEMPER_TIERS), 5)
        names = []
        for tier in game.TEMPER_TIERS:
            self.assertEqual(len(tier), 10)
            for n, d in tier:
                self.assertTrue(n and d)
                names.append(n)
        self.assertEqual(len(set(names)), 50, '五档里没有重名的气质')

    def test_tier_boundaries_every_twenty(self):
        for app_, tier in ((0, 0), (19, 0), (20, 1), (39, 1), (40, 2), (59, 2), (60, 3), (79, 3), (80, 4), (100, 4), (150, 4), (-5, 0)):
            self.assertEqual(game.temper_tier_of(app_), tier, app_)

    def test_roll_always_stays_inside_the_tier(self):
        for app_ in (5, 25, 45, 65, 95):
            allowed = {n for n, _ in game.TEMPER_TIERS[game.temper_tier_of(app_)]}
            for _ in range(40):
                self.assertIn(game.roll_temperament(app_), allowed)

    def test_newborn_looks_follow_the_mother(self):
        for mother_app in (20, 60, 100):
            game.run("UPDATE consorts SET appearance=? WHERE id=?", (mother_app, self.atk))
            game.run("DELETE FROM heirs")
            h = self.deliver(self.atk)
            self.assertLessEqual(abs(h['appearance'] - mother_app * 0.7), 8.5)
            self.assertEqual(h['temper_tier'], game.temper_tier_of(h['appearance']))
            self.assertIn(h['temperament'], {n for n, _ in game.TEMPER_TIERS[h['temper_tier']]})

    def test_looks_of_beautiful_and_plain_mothers_differ(self):
        game.run("UPDATE consorts SET appearance=100 WHERE id=?", (self.atk,))
        game.run("UPDATE consorts SET appearance=10 WHERE id=?", (self.tgt,))
        pretty = self.deliver(self.atk)
        plain = self.deliver(self.tgt)
        self.assertGreater(pretty['appearance'], plain['appearance'])

    def test_changing_looks_rerolls_only_when_crossing_a_tier(self):
        h = self.deliver(self.atk)
        hid = h['id']
        game.set_heir_appearance(hid, 45)
        first = game.get_heir(hid)['temperament']
        game.set_heir_appearance(hid, 55)            # 同档：气质不变
        self.assertEqual(game.get_heir(hid)['temperament'], first)
        game.set_heir_appearance(hid, 85)            # 跨到最高一档：换成那一档里的
        after = game.get_heir(hid)
        self.assertEqual(after['temper_tier'], 4)
        self.assertIn(after['temperament'], {n for n, _ in game.TEMPER_TIERS[4]})
        game.set_heir_appearance(hid, 500)
        self.assertEqual(game.get_heir(hid)['appearance'], 100)

    def test_old_heirs_are_backfilled(self):
        game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day) VALUES(?,?,'皇子',1,?)", (self.atk, self.atk, game.cur_day()))
        hid = game.q("SELECT id FROM heirs ORDER BY id DESC", one=True)['id']
        self.assertEqual(game.get_heir(hid)['temper_tier'], -1)
        import sqlite3
        db = sqlite3.connect(game.DB_PATH)
        game.migrate_heir_looks(db); db.commit(); db.close()
        h = game.get_heir(hid)
        self.assertGreaterEqual(h['appearance'], 5)
        self.assertTrue(h['temperament'])
        self.assertEqual(h['temper_tier'], game.temper_tier_of(h['appearance']))

    def test_pages_show_looks_and_temperament(self):
        h = self.deliver(self.atk)
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (self.atk,))
        html = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('容貌', html)
        self.assertIn('气质', html)
        self.assertIn(h['temperament'], html)

    # ── 加容貌的办法：教养「梳洗仪容」、自己长开 ───────────────────────────────

    def raised(self, mother_app=40, caretaker_app=50):
        game.run("UPDATE consorts SET appearance=? WHERE id=?", (mother_app, self.atk))
        game.run("DELETE FROM heirs")
        h = self.deliver(self.atk)
        game.run("UPDATE heirs SET caretaker_id=? WHERE id=?", (self.atk, h['id']))
        game.run("UPDATE consorts SET appearance=?, energy=8, silver=500 WHERE id=?", (caretaker_app, self.atk))
        return h['id']

    def groom(self, hid):
        return self.client.post(f'/heirs/raise/{hid}', data={'opt': 'grooming'})

    def test_grooming_costs_and_gives_two_looks(self):
        hid = self.raised()
        game.set_heir_appearance(hid, 30)
        self.groom(hid)
        self.assertEqual(game.get_heir(hid)['appearance'], 32)
        c = game.get_consort(self.atk)
        self.assertEqual((c['silver'], c['energy']), (480, 7))

    def test_a_beautiful_caretaker_teaches_better(self):
        hid = self.raised(caretaker_app=game.HEIR_GROOM_BEAUTY_LINE)
        game.set_heir_appearance(hid, 30)
        self.groom(hid)
        self.assertEqual(game.get_heir(hid)['appearance'], 33)

    def test_grooming_once_a_day_needs_silver_and_stops_at_100(self):
        hid = self.raised()
        game.set_heir_appearance(hid, 30)
        game.run("UPDATE consorts SET energy=20 WHERE id=?", (self.atk,))
        for _ in range(game.HEIR_RAISE_DAILY + 1): self.groom(hid)
        self.assertEqual(game.get_heir(hid)['appearance'], 30 + 2 * game.HEIR_RAISE_DAILY, '一天最多 HEIR_RAISE_DAILY 次')
        game.run("DELETE FROM daily_counters"); game.run("UPDATE consorts SET silver=5 WHERE id=?", (self.atk,))
        self.groom(hid)
        self.assertEqual(game.get_heir(hid)['appearance'], 30 + 2 * game.HEIR_RAISE_DAILY, '银子不够')
        game.run("UPDATE consorts SET silver=500 WHERE id=?", (self.atk,))
        game.set_heir_appearance(hid, 100)
        self.groom(hid)
        self.assertEqual(game.get_heir(hid)['appearance'], 100)
        self.assertEqual(game.get_consort(self.atk)['silver'], 500, '到顶了不扣钱')

    def test_crossing_a_tier_rerolls_temperament_and_tells_the_mother(self):
        hid = self.raised()
        game.set_heir_appearance(hid, 39)
        old = game.get_heir(hid)['temperament']
        self.groom(hid)                      # 39 → 41，跨到第 3 档
        h = game.get_heir(hid)
        self.assertEqual(h['temper_tier'], 2)
        self.assertIn(h['temperament'], {n for n, _ in game.TEMPER_TIERS[2]})
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE ? ", (self.atk, f"%长开了，气质由「{old}」变成了「{h['temperament']}」%"), one=True))

    def test_children_grow_into_their_looks_over_time_and_cap_at_100(self):
        hid = self.raised()
        game.set_heir_appearance(hid, 50)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_looks_grow(10)
        self.assertEqual(game.get_heir(hid)['appearance'], 51)
        with patch.object(game.random, 'random', return_value=0.99):
            game.heir_looks_grow(10)
        self.assertEqual(game.get_heir(hid)['appearance'], 51, '没抽中就不变')
        game.set_heir_appearance(hid, 100)
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_looks_grow(10)
        self.assertEqual(game.get_heir(hid)['appearance'], 100)

    def test_adults_do_not_grow_and_settlement_runs_the_growth(self):
        hid = self.raised()
        game.set_heir_appearance(hid, 50)
        game.run("UPDATE heirs SET adult_day=3 WHERE id=?", (hid,))
        with patch.object(game.random, 'random', return_value=0.0):
            game.heir_looks_grow(10)
        self.assertEqual(game.get_heir(hid)['appearance'], 50)
        game.run("UPDATE heirs SET adult_day=0 WHERE id=?", (hid,))
        with patch.object(game.random, 'random', return_value=0.0), patch.object(game, 'heir_adult_tick'):
            game.heir_growth_tick(game.cur_day())
        self.assertEqual(game.get_heir(hid)['appearance'], 51)

    def test_home_page_offers_the_grooming_button_with_its_price(self):
        hid = self.raised()
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (self.atk,))
        html = self.client.get('/place/home').get_data(as_text=True)
        self.assertIn('梳洗仪容（20 两）', html)


if __name__ == '__main__':
    unittest.main()
