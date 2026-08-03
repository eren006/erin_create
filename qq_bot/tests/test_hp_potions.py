"""魔药系统的跨模块回归测试。运行：venv/bin/python -m unittest tests.test_hp_potions"""

import tempfile
import unittest
from pathlib import Path

import nonebot

nonebot.init()

from plugins.hp_core import storage as core

_IMPORT_BOX = tempfile.TemporaryDirectory(prefix="hp-potion-import-")
core.DB_PATH = Path(_IMPORT_BOX.name) / "import.db"
core.init_db()

from plugins.hp_events import forest, storage as event_storage
from plugins.hp_school import lesson_events, potions, storage as school_storage


class PotionSystemTest(unittest.TestCase):
    def setUp(self):
        self.box = tempfile.TemporaryDirectory(prefix="hp-potions-")
        core.DB_PATH = Path(self.box.name) / "hogwarts.db"
        core.init_db()
        school_storage.init_db()
        event_storage.init_db()
        now = core.now()
        conn = core.get_conn()
        conn.execute(
            "INSERT INTO players(uid,name,house,grade,stamina,stamina_updated_at,galleons,created_at,updated_at) "
            "VALUES('u','测试生','拉文克劳',5,50,?,0,?,?)", (now, now, now)
        )
        conn.execute(
            "INSERT INTO players(uid,name,house,grade,stamina,stamina_updated_at,galleons,created_at,updated_at) "
            "VALUES('v','同学','赫奇帕奇',5,50,?,0,?,?)", (now, now, now)
        )
        conn.execute("INSERT INTO subject_exp VALUES('u','potions',200)")
        conn.execute("INSERT INTO game_clock(id,started_at,last_processed_day) VALUES(1,?,0)", (now,))
        conn.execute("INSERT INTO learned_spells VALUES('u','expelliarmus',?)", (now,))
        for key in (
            "mat_knotgrass", "mat_leech", "mat_flobberworm", "mat_lacewing",
            "mat_boomslang", "mat_unicorn_hair", "mat_bicorn_horn",
            "mat_acromantula_venom", "mat_dementor_frost",
        ):
            conn.execute("INSERT INTO inventory VALUES('u',?,10)", (key,))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.box.cleanup()

    def test_brew_is_persistent_atomic_and_not_repeatable(self):
        conn = core.get_conn()
        conn.execute("UPDATE inventory SET quantity=0 WHERE uid='u' AND item_key='mat_leech'")
        conn.commit()
        conn.close()
        with self.assertRaises(potions.PotionError):
            potions.start("u", "提神剂")
        self.assertEqual(school_storage.get_item_quantity("u", "mat_knotgrass"), 10)
        school_storage.add_item("u", "mat_leech", 1)
        first = potions.start("u", "提神剂")
        self.assertEqual(first["step"], 1)
        self.assertEqual(school_storage.get_item_quantity("u", "mat_knotgrass"), 9)
        self.assertTrue(potions.start("u", "")["resumed"])
        potions.choose("u", 2)
        potions.choose("u", 1)
        result = potions.choose("u", 2)
        self.assertEqual(result["quality"], "完美")
        self.assertIn("坩埚学徒", result["earned_titles"])
        self.assertEqual(school_storage.get_item_quantity("u", "potion_energizing"), 2)
        with self.assertRaises(potions.PotionError):
            potions.choose("u", 2)

        self.assertEqual(potions.wear_title("u", "坩埚学徒"), "坩埚学徒")
        self.assertTrue(next(r for r in potions.title_state("u") if r["name"] == "坩埚学徒")["active"])

    def test_first_scored_herbology_lesson_grants_one_daily_material(self):
        first = lesson_events.start("u", "草药学")
        result = lesson_events.resolve("u", first["token"], 0)
        self.assertTrue(result["herbology_material"])
        self.assertEqual(school_storage.get_item_quantity("u", "mat_knotgrass"), 11)
        second = lesson_events.start("u", "草药学")
        result = lesson_events.resolve("u", second["token"], 0)
        self.assertFalse(result["herbology_material"])
        self.assertEqual(school_storage.get_item_quantity("u", "mat_knotgrass"), 11)

    def test_stamina_and_lesson_effects_are_consumed_once(self):
        school_storage.add_item("u", "potion_energizing", 1)
        core.spend_stamina("u", 10)
        self.assertEqual(potions.use("u", "提神剂")["stamina"], 47)
        school_storage.add_item("u", "potion_focus", 1)
        potions.use("u", "振奋药剂")
        self.assertEqual(potions.consume_focus_bonus("u", "potions"), 1)
        self.assertEqual(potions.consume_focus_bonus("u", "potions"), 0)

    def test_mastery_progress_unlocks_collection_and_master_titles(self):
        conn = core.get_conn()
        conn.execute("INSERT INTO potion_mastery VALUES('u','energizing',7,7,2)")
        for key in ("focus", "healing", "protection", "wolfsbane"):
            conn.execute("INSERT INTO potion_mastery VALUES('u',?,1,1,0)", (key,))
        conn.commit()
        conn.close()
        potions.start("u", "提神剂")
        potions.choose("u", 2)
        potions.choose("u", 1)
        result = potions.choose("u", 2)
        self.assertEqual(
            set(result["earned_titles"]),
            {"坩埚学徒", "配方收藏家", "坩埚守望者", "魔药优等生"},
        )
        energizing = next(row for row in potions.list_recipes("u")["rows"] if row["key"] == "energizing")
        self.assertEqual(energizing["mastery_level"], "精通")

    def test_all_forest_effects_reach_active_run(self):
        school_storage.add_item("u", "potion_protection", 1)
        potions.use("u", "防护药剂")
        forest.enter("u")
        run = event_storage.get_active_run("u")
        self.assertEqual(run["my_shield"], 20)

        school_storage.add_item("u", "potion_healing", 2)
        event_storage.update_run(run["id"], my_hp=60)
        self.assertEqual(potions.use("u", "愈合药剂")["hp"], 85)
        with self.assertRaises(potions.PotionError):
            potions.use("u", "愈合药剂")

        event_storage.update_run(run["id"], status="finished")
        event_storage.create_run("u", my_hp=100, depth=6, phase="cleared", monster_key="troll")
        school_storage.add_item("u", "potion_wolfsbane", 1)
        potions.use("u", "狼毒药剂")
        result = forest.go_deeper("u")
        self.assertTrue(result["wolfsbane_potion"])
        run = event_storage.get_active_run("u")
        self.assertEqual(run["monster_key"], "werewolf")
        original_pick = forest._monster_pick
        try:
            forest._monster_pick = lambda monster: "attack"
            attack = forest._monster_turn("u", run, forest.forest_catalog.MONSTERS_BY_KEY["werewolf"])
        finally:
            forest._monster_pick = original_pick
        self.assertEqual(attack["damage"], 14)  # (基础16 + 第7层加成12) / 2

    def test_potion_history_appears_in_newspaper_data(self):
        conn = core.get_conn()
        now = core.now()
        conn.execute(
            "INSERT INTO potion_history(uid,recipe_key,quality,quantity,accident,created_at) "
            "VALUES('u','healing','perfect',2,'',?)", (now,)
        )
        conn.execute(
            "INSERT INTO potion_history(uid,recipe_key,quality,quantity,accident,created_at) "
            "VALUES('u','focus','failed',0,'耳朵里不断冒烟',?)", (now,)
        )
        conn.execute(
            "INSERT INTO potion_trades(sender_uid,receiver_uid,potion_key,quantity,created_at) "
            "VALUES('u','v','focus',2,?)", (now,)
        )
        conn.commit()
        conn.close()
        import newspaper_service
        newspaper_service.DB_PATH = core.DB_PATH
        issue = newspaper_service.build_issue(1)
        self.assertEqual(issue["potion_perfects"][0]["potion"], "愈合药剂")
        self.assertEqual(issue["potion_accidents"][0]["accident"], "耳朵里不断冒烟")
        self.assertEqual(issue["potion_trades"], 2)

    def test_polyjuice_is_cosmetic_and_potion_gift_is_atomic(self):
        school_storage.add_item("u", "potion_polyjuice", 1)
        result = potions.use("u", "复方汤剂", "v")
        self.assertEqual(result["target_name"], "同学")
        self.assertIn("同学", core.get_status_suffix("u"))
        self.assertEqual(core.get_player("u")["name"], "测试生")  # 账号身份没有改变

        school_storage.add_item("u", "potion_focus", 2)
        gifted = potions.gift("u", "v", "振奋药剂", 2)
        self.assertEqual(gifted["quantity"], 2)
        self.assertEqual(school_storage.get_item_quantity("u", "potion_focus"), 0)
        self.assertEqual(school_storage.get_item_quantity("v", "potion_focus"), 2)
        with self.assertRaises(potions.PotionError):
            potions.gift("u", "v", "振奋药剂", 1)
        self.assertEqual(school_storage.get_item_quantity("v", "potion_focus"), 2)

    def test_felix_is_once_per_year_and_grants_atomic_lucky_loot(self):
        conn = core.get_conn()
        conn.execute("UPDATE players SET grade=6 WHERE uid='u'")
        conn.commit()
        conn.close()
        potions.start("u", "福灵剂")
        potions.choose("u", 2)
        potions.choose("u", 2)
        result = potions.choose("u", 2)
        self.assertEqual(result["quantity"], 1)  # 完美也不会复制福灵剂
        with self.assertRaises(potions.PotionError):
            potions.start("u", "福灵剂")

        potions.use("u", "福灵剂")
        run_id = event_storage.create_run(
            "u", my_hp=100, depth=9, phase="combat", monster_key="dementor"
        )
        run = event_storage.get_run(run_id)
        loot = forest._grant_layer_loot("u", run)
        self.assertEqual(loot["lucky_material"], "摄魂怪的寒霜")
        self.assertFalse(potions.consume_effect("u", "felix_felicis"))


if __name__ == "__main__":
    unittest.main()
