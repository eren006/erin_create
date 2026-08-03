"""《第十三声钟响》全服分支主线回归测试。"""

import tempfile
import unittest
from pathlib import Path

import nonebot

nonebot.init()

from plugins.hp_core import storage as core
from plugins.hp_school import story_mainline


class _AlwaysOffer:
    @staticmethod
    def random():
        return 0.0


class StoryMainlineTest(unittest.TestCase):
    def setUp(self):
        self.original_db_path = core.DB_PATH
        self.box = tempfile.TemporaryDirectory(prefix="hp-story-")
        core.DB_PATH = Path(self.box.name) / "hogwarts.db"
        core.init_db()
        story_mainline.init_db()
        now = core.now()
        conn = core.get_conn()
        conn.execute(
            "INSERT INTO players(uid,name,house,grade,stamina,stamina_updated_at,galleons,created_at,updated_at) "
            "VALUES('u','测试生','拉文克劳',1,50,?,0,?,?)", (now, now, now)
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        core.DB_PATH = self.original_db_path
        self.box.cleanup()

    def test_daily_offer_happens_only_once_per_day(self):
        self.assertEqual(story_mainline.daily_offer(1, _AlwaysOffer()), 1)
        self.assertEqual(story_mainline.daily_offer(1, _AlwaysOffer()), 0)
        task = story_mainline.task_for("u")
        self.assertTrue(task["eligible"])
        self.assertEqual(task["phase"].number, 1)

    def test_choice_is_atomic_rewards_once_and_advances(self):
        story_mainline.daily_offer(1, _AlwaysOffer())
        result = story_mainline.choose("u", "b")
        self.assertEqual(result["reward"], 10)
        self.assertFalse(result["advanced"])
        self.assertEqual(core.get_player("u")["galleons"], 10)
        with self.assertRaises(story_mainline.StoryError):
            story_mainline.choose("u", "A")
        self.assertEqual(core.get_player("u")["galleons"], 10)

        advanced = story_mainline.check_and_advance(force=True)
        self.assertEqual(advanced["winning"], "B")
        self.assertEqual(story_mainline.progress()["phase"], 2)
        conn = core.get_conn()
        evidence = conn.execute(
            "SELECT state_value FROM story_state WHERE story_id=? AND state_key='evidence'",
            (story_mainline.STORY_ID,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(evidence, 1)

    def test_phase_cannot_advance_without_votes(self):
        self.assertIsNone(story_mainline.check_and_advance(force=True))
        self.assertEqual(story_mainline.progress()["phase"], 1)

    def test_final_phase_creates_world_and_personal_endings(self):
        conn = core.get_conn()
        conn.execute("UPDATE story_mainline SET phase=20 WHERE story_id=?", (story_mainline.STORY_ID,))
        conn.execute("INSERT INTO story_eligibility VALUES('u',?,20,1)", (story_mainline.STORY_ID,))
        for key, value in (("evidence", 10), ("public_truth", 8),
                           ("voluntary_memory", 1), ("heard_echo", 1), ("ending_rebirth", 5)):
            conn.execute(
                "INSERT INTO story_state VALUES(?,?,?) ON CONFLICT(story_id,state_key) "
                "DO UPDATE SET state_value=excluded.state_value",
                (story_mainline.STORY_ID, key, value),
            )
        conn.commit()
        conn.close()

        story_mainline.choose("u", "C")
        result = story_mainline.check_and_advance(force=True)
        self.assertIsNone(result["next_phase"])
        progress = story_mainline.progress("u")
        self.assertFalse(progress["active"])
        self.assertEqual(progress["ending_key"], "rebirth")
        self.assertEqual(progress["personal_ending"]["personal_tag"], "echo_friend")


if __name__ == "__main__":
    unittest.main()
