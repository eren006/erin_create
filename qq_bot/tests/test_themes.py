import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nonebot

nonebot.init()

from plugins.hp_school import themes


class ThemeShopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hp-themes-")
        self.db_path = Path(self.temp.name) / "themes.db"

        def connect():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

        self.connect = connect
        self.patcher = patch.object(themes, "get_conn", connect)
        self.patcher.start()
        conn = connect()
        conn.execute(
            "CREATE TABLE players(uid TEXT PRIMARY KEY, galleons INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO players VALUES ('student', 80, 0)")
        conn.commit()
        conn.close()
        themes.init_db()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_buy_deducts_40_and_unlocks_game(self):
        result = themes.buy("student", "great_hall")
        self.assertEqual(result["price"], 40)
        conn = self.connect()
        balance = conn.execute("SELECT galleons FROM players WHERE uid='student'").fetchone()[0]
        conn.close()
        self.assertEqual(balance, 40)
        self.assertEqual(themes.get_owned_theme("student", "great_hall")["game_name"], "漂浮蜡烛")

    def test_cannot_buy_twice_or_equip_unowned_theme(self):
        themes.buy("student", "great_hall")
        with self.assertRaises(themes.ThemeError):
            themes.buy("student", "great_hall")
        with self.assertRaises(themes.ThemeError):
            themes.equip("student", "forest")

    def test_equip_and_return_to_classic(self):
        themes.buy("student", "potions")
        themes.equip("student", "potions")
        self.assertEqual(themes.get_equipped("student"), "potions")
        themes.equip("student", "")
        self.assertEqual(themes.get_equipped("student"), "")

    def test_scores_keep_best_and_count_every_completed_game(self):
        themes.buy("student", "forest")
        first = themes.record_score("student", "forest", 3)
        second = themes.record_score("student", "forest", 2)
        self.assertTrue(first["new_best"])
        self.assertFalse(second["new_best"])
        board = themes.leaderboard("forest")
        self.assertEqual(board[0]["best_score"], 3)
        self.assertEqual(board[0]["last_score"], 2)
        self.assertEqual(board[0]["plays"], 2)

    def test_score_requires_ownership_and_valid_range(self):
        with self.assertRaises(themes.ThemeError):
            themes.record_score("student", "potions", 2)
        themes.buy("student", "potions")
        with self.assertRaises(themes.ThemeError):
            themes.record_score("student", "potions", 4)

    def test_christmas_theme_automatically_covers_every_term_end(self):
        for day in (4, 8, 12, 16, 21, 25, 30):
            self.assertEqual(themes.seasonal_theme_for_day(day), "christmas")
        for day in (1, 3, 5, 20, 29):
            self.assertEqual(themes.seasonal_theme_for_day(day), "")


if __name__ == "__main__":
    unittest.main()
