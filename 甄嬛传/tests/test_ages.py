"""年龄：妃嫔每 6 小时涨一岁（0/6/12/18 点）；孩子按出生时刻每 6 小时一岁（2026-10-09 起一天四年）"""
import unittest
from datetime import datetime, timedelta
import test_lifecycle as fixtures

game = fixtures.game

YEAR_HOURS = 24 / game.AGE_YEARS_PER_DAY      # 一岁几小时（现在是 6）


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

    def test_heir_gains_one_year_every_year_hours_from_birth(self):
        y = YEAR_HOURS
        for hours, years in ((0, 0), (y * 0.4, 0), (y * 0.99, 0), (y * 1.02, 1), (y * 1.99, 1), (y * 2.02, 2), (y * 3.1, 3), (y * 14.1, 14)):
            self.assertEqual(game.heir_age_years(self.row(self.heir(hours))), years, hours)

    def test_zhuazhou_happens_at_one_year_not_at_midnight(self):
        young = self.heir(YEAR_HOURS * 0.5); due = self.heir(YEAR_HOURS * 1.1)
        game.heir_age_events(game.cur_day())
        self.assertEqual(self.row(young)['zhuazhou'], '')
        self.assertNotEqual(self.row(due)['zhuazhou'], '')
        stamp = self.row(due)['zhuazhou']
        game.heir_age_events(game.cur_day())      # 再跑一次不会重复抓周
        self.assertEqual(self.row(due)['zhuazhou'], stamp)

    def test_unnamed_heir_gets_a_name_at_two_years(self):
        young = self.heir(YEAR_HOURS * 1.7); old = self.heir(YEAR_HOURS * 2.1)
        game.heir_age_events(game.cur_day())
        self.assertEqual(self.row(young)['name'], '')
        self.assertNotEqual(self.row(old)['name'], '')

    def test_old_day_based_heirs_still_use_day_count(self):
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day) VALUES(?,?,'皇子',9,?)", (self.atk, self.atk, game.cur_day() - 3)).lastrowid
        self.assertEqual(game.heir_age_years(self.row(hid)), 3 * game.AGE_YEARS_PER_DAY)

    def test_consort_age_tick_adds_one_year_at_each_slot_once(self):
        before = game.get_consort(self.atk)['age_months']
        game.run("UPDATE game_state SET last_age_key=''")
        day = datetime(2026, 10, 5, 0, 0, tzinfo=game.TZ)
        game.age_tick(day + timedelta(hours=5, minutes=59))      # 0 点那一格先涨一岁（这里是第一次跑）
        first = game.get_consort(self.atk)['age_months']
        self.assertEqual(first, before + 12)
        game.age_tick(day + timedelta(hours=5, minutes=59, seconds=30))      # 同一格不重复
        self.assertEqual(game.get_consort(self.atk)['age_months'], first)
        for h in (6, 12, 18):
            game.age_tick(day + timedelta(hours=h, minutes=2))
        self.assertEqual(game.get_consort(self.atk)['age_months'], first + 36)
        game.age_tick(day + timedelta(days=1, minutes=1))
        self.assertEqual(game.get_consort(self.atk)['age_months'], first + 48)

    def test_time_scale_migration_backfills_once(self):
        game.run("UPDATE game_state SET time_scale_version=0, day=5, age_switch_day=0, age_switch_ts=0, last_age_key=''")
        game.run("UPDATE consorts SET age_months=240 WHERE id=?", (self.atk,))
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,born_ts) VALUES(?,?,'皇子',9,2,0)", (self.atk, self.atk)).lastrowid
        db = game.get_db()
        game.migrate_time_scale(db); db.commit()
        age = game.get_consort(self.atk)['age_months']
        self.assertGreaterEqual(age - 240, 24 * 4)      # 过了 4 天，每天补两年
        game.migrate_time_scale(db); db.commit()
        self.assertEqual(game.get_consort(self.atk)['age_months'], age, '只补一次')
        self.assertEqual(game.state()['age_switch_day'], 5)
        # 老档孩子：补上之后的年龄 = 旧年龄 + 补的 4 天 × 2 年
        self.assertAlmostEqual(game.heir_age_years(self.row(hid), 5), (5 - 2) * game.OLD_AGE_YEARS_PER_DAY + 4 * game.OLD_AGE_YEARS_PER_DAY, delta=1)


if __name__ == '__main__':
    unittest.main()
