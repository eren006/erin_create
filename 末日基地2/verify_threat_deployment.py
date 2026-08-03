"""Isolated acceptance test for regional threat, warnings, breach damage and looting."""
import json
import os
import sqlite3
import time
from unittest.mock import patch

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_threat_deployment.db")


def remove_sqlite(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def run_verification():
    remove_sqlite(TEST_DB)
    game.DB_PATH = TEST_DB
    game.init_db()
    ts = int(time.time())
    with game.app.app_context():
        db = game.get_db()
        password = game.generate_password_hash("verify-pass", method="pbkdf2:sha256")
        db.execute("""INSERT INTO users(username,password_hash,approved,created_ts)
                      VALUES('threat_verify',?,1,?)""", (password, ts))
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO characters
                      (user_id,name,hp,tile_x,tile_y,protected_until_ts,created_ts,last_action_ts)
                      VALUES(?, '噪声验收员',100,0,0,0,?,?)""",
                   (user_id, ts - 5 * game.DAY_SECONDS, ts))
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','optimist','careful','avatar-01',?,?)""",
                   (char_id, ts, ts))
        db.execute("""INSERT INTO houses
                      (owner_user_id,tile_x,tile_y,has_workbench,level,hp,max_hp,
                       auto_defense,built_ts)
                      VALUES(?,0,0,1,4,1,320,1,?)""", (user_id, ts))
        house_id = db.execute("SELECT id FROM houses").fetchone()["id"]
        db.execute("""INSERT INTO personal_homesteads
                      (character_id,has_kitchen,has_brewery,has_sewing,has_livestock,created_ts)
                      VALUES(?,1,1,1,1,?)""", (char_id, ts))
        db.execute("""INSERT INTO personal_survival_workshops
                      (character_id,has_water_tester,has_ammo_press,created_ts)
                      VALUES(?,1,1,?)""", (char_id, ts))
        for key, amount in (("wood", 100), ("ammo", 20), ("northstar_beacon", 1)):
            db.execute("""INSERT INTO house_inventory(house_id,resource_key,amount)
                          VALUES(?,?,?)""", (house_id, key, amount))
        for key in ("metal", "parts", "electronics"):
            db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                          VALUES(?,?,100)""", (char_id, key))
        db.execute("""INSERT INTO map_regions
                      (region_x,region_y,noise,threat,last_decay_day,updated_ts)
                      VALUES(0,0,80,100,1,?)""", (ts,))
        db.commit()

        before_base = game.zombie_base_strength(0, 1)
        raw = sqlite3.connect(TEST_DB)
        raw.row_factory = sqlite3.Row
        game._resolve_night_raid(raw)
        raw.close()
        db = game.get_db()
        raid = db.execute("""SELECT * FROM house_raid_logs
                             WHERE house_id=? ORDER BY id DESC""", (house_id,)).fetchone()
        assert raid["attack_strength"] >= int(before_base * 1.9)
        assert "区域威胁100" in raid["summary"]
        assert "仓库失窃" in raid["summary"]
        assert db.execute("""SELECT amount FROM house_inventory
                             WHERE house_id=? AND resource_key='wood'""",
                          (house_id,)).fetchone()["amount"] < 100
        assert db.execute("""SELECT amount FROM house_inventory
                             WHERE house_id=? AND resource_key='northstar_beacon'""",
                          (house_id,)).fetchone()["amount"] == 1
        house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
        home = db.execute("SELECT * FROM personal_homesteads WHERE character_id=?",
                          (char_id,)).fetchone()
        workshop = db.execute("""SELECT * FROM personal_survival_workshops
                                 WHERE character_id=?""", (char_id,)).fetchone()
        facility_values = [
            house["has_workbench"], house["auto_defense"],
            home["has_kitchen"], home["has_brewery"], home["has_sewing"], home["has_livestock"],
            workshop["has_water_tester"], workshop["has_ammo_press"],
        ]
        assert facility_values.count(0) == 1
        assert db.execute("""SELECT threat FROM map_regions
                             WHERE region_x=0 AND region_y=0""").fetchone()["threat"] == 95

        # A repairable automatic-defense failure uses the real player route.
        db.execute("""UPDATE houses SET hp=100,auto_defense=0,auto_defense_damaged=1
                      WHERE id=?""", (house_id,))
        db.commit()

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "threat_verify", "password": "verify-pass"}).status_code == 302
        with game.app.app_context():
            before_noise = game.get_db().execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0"
            ).fetchone()["noise"]
        client.post("/action/move", data={"dir": "e"})
        with game.app.app_context():
            db = game.get_db()
            after_noise = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0"
            ).fetchone()["noise"]
            assert after_noise == min(100, before_noise + 1)
            assert db.execute("""SELECT COUNT(*) c FROM region_threat_events
                                 WHERE event_key='move'""").fetchone()["c"] == 1
            db.execute("""UPDATE characters
                          SET tile_x=0,tile_y=0,pending_zombie_type=NULL,pending_zombie_hp=0
                          WHERE id=?""", (char_id,))
            db.execute("DELETE FROM pending_world_events WHERE character_id=?", (char_id,))
            db.commit()
        client.post("/action/repair_house_auto_defense")
        with game.app.app_context():
            db = game.get_db()
            repaired = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            assert (repaired["auto_defense"], repaired["auto_defense_damaged"]) == (1, 0)

            # Put the world five minutes before night: one tick creates one radio bulletin.
            # day_count must land on an actual raid night (see NIGHT_RAID_EVERY_N_DAYS) or
            # the warning is intentionally suppressed.
            warning_started = int(time.time()) - (
                int(game.DAY_SECONDS * game.DAY_RATIO) - 300)
            db.execute("""UPDATE world_state
                          SET day_count=?,day_started_ts=?,last_tick_ts=? WHERE id=1""",
                       (game.NIGHT_RAID_EVERY_N_DAYS, warning_started, int(time.time()) - 1))
            db.execute("DELETE FROM meta WHERE key LIKE 'night_warning_day_%'")
            db.commit()
        # This test must pass regardless of the real wall-clock hour it runs at, so force
        # outside the 00:00-10:00 Beijing-time raid quiet window for both the tick
        # resolution and the subsequent dashboard/map render below.
        with patch.object(game, "in_night_raid_quiet_hours", return_value=False):
            with game.app.app_context():
                game.run_tick()
                game.run_tick()
                count = game.get_db().execute(
                    """SELECT COUNT(*) c FROM server_announcements
                       WHERE content LIKE '%北辰紧急预警%'""").fetchone()["c"]
                assert count == 1
            dashboard = client.get("/")
            map_page = client.get("/map")
        assert dashboard.status_code == 200 and map_page.status_code == 200, (
            dashboard.status_code, dashboard.headers.get("Location"),
            map_page.status_code, map_page.headers.get("Location"))
        assert "尸群正在接近".encode() in dashboard.data
        assert "raid-countdown".encode() in dashboard.data
        assert "所在区域".encode() in map_page.data
        assert "威胁地图".encode() in dashboard.data

        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE map_regions SET noise=50,threat=70,last_decay_day=1
                          WHERE region_x=0 AND region_y=0""")
            rollover_started = int(time.time()) - game.DAY_SECONDS - 10
            db.execute("""UPDATE world_state SET day_count=1,day_started_ts=?,last_tick_ts=?
                          WHERE id=1""",
                       (rollover_started, int(time.time()) - 1))
            old_day = db.execute("SELECT day_count FROM world_state WHERE id=1").fetchone()["day_count"]
            db.commit()
            game.run_tick()
            region = game.get_db().execute(
                "SELECT * FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()
            assert region["noise"] == 44
            # 衰减(-10)加噪声残留(lingering,+2)再加1名常住人口的每日信号(+1)：70-10+2+1=63。
            # 净变化必须是真实下降，不能被lingering完全抵消(这正是这版特意修的问题)。
            assert region["threat"] == 63
            assert region["last_decay_day"] > old_day
            assert game.get_db().execute(
                """SELECT COUNT(*) c FROM region_threat_events
                   WHERE event_key='population'""").fetchone()["c"] >= 1

    result = {
        "regional_threat_multiplier": "PASS",
        "activity_and_daily_decay": "PASS",
        "single_radio_warning": "PASS",
        "live_countdown_ui": "PASS",
        "map_threat_overlay": "PASS",
        "breach_facility_damage": "PASS",
        "replaceable_resource_looting": "PASS",
        "story_item_protection": "PASS",
        "auto_defense_repair": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
    finally:
        remove_sqlite(TEST_DB)
