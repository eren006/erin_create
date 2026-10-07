"""年龄：妃嫔零点、中午各涨一岁；孩子按出生时刻每 12 小时一岁"""
import unittest
from datetime import datetime, timedelta
import test_lifecycle as fixtures

game = fixtures.game


class AgeTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def heir(self, hours_old, **kw):
        ts = game.now_ts() - hours_old * 3600
        return game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,born_ts,gen_word) VALUES(?,?,'皇子',9,?, ?, '弘')",
                        (self.atk, self.atk, game.cur_day(), ts)).lastrowid

    def row(self, hid): return game.q('SELECT * FROM heirs WHERE id=?', (hid,), one=True)

    def test_heir_gains_one_year_every_12_hours_from_birth(self):
        for hours, years in ((0, 0), (5, 0), (11.9, 0), (12.1, 1), (23.9, 1), (24.1, 2), (36.5, 3), (168.5, 14)):
            self.assertEqual(game.heir_age_years(self.row(self.heir(hours))), years, hours)

    def test_zhuazhou_happens_at_12_hours_not_at_midnight(self):
        young = self.heir(6); due = self.heir(13)
        game.heir_age_events(game.cur_day())
        self.assertEqual(self.row(young)['zhuazhou'], '')
        self.assertNotEqual(self.row(due)['zhuazhou'], '')
        stamp = self.row(due)['zhuazhou']
        game.heir_age_events(game.cur_day())      # 再跑一次不会重复抓周
        self.assertEqual(self.row(due)['zhuazhou'], stamp)

    def test_unnamed_heir_gets_a_name_at_24_hours(self):
        young = self.heir(20); old = self.heir(25)
        game.heir_age_events(game.cur_day())
        self.assertEqual(self.row(young)['name'], '')
        self.assertNotEqual(self.row(old)['name'], '')

    def test_old_day_based_heirs_still_use_day_count(self):
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day) VALUES(?,?,'皇子',9,?)", (self.atk, self.atk, game.cur_day() - 3)).lastrowid
        self.assertEqual(game.heir_age_years(self.row(hid)), 6)

    def test_consort_noon_tick_adds_one_year_once_per_day(self):
        before = game.get_consort(self.atk)['age_months']
        noon = datetime(2026, 10, 5, 12, 5, tzinfo=game.TZ)
        game.run("UPDATE game_state SET last_noon_age_date=''")
        game.age_noon_tick(datetime(2026, 10, 5, 11, 59, tzinfo=game.TZ))      # 中午之前不涨
        self.assertEqual(game.get_consort(self.atk)['age_months'], before)
        game.age_noon_tick(noon)
        game.age_noon_tick(noon + timedelta(hours=3))      # 同一天第二次不涨
        self.assertEqual(game.get_consort(self.atk)['age_months'], before + 12)
        game.age_noon_tick(noon + timedelta(days=1))
        self.assertEqual(game.get_consort(self.atk)['age_months'], before + 24)


if __name__ == '__main__':
    unittest.main()
