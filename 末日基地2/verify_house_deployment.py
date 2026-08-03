"""Isolated production-deployment acceptance test for the house defense loop."""
import json
import os
import sqlite3
import time

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_house_deployment.db")
OLD_DB = os.path.join(ROOT, "_verify_house_old_schema.db")


def remove_sqlite(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def verify_old_schema_migration():
    remove_sqlite(OLD_DB)
    db = sqlite3.connect(OLD_DB)
    db.execute(
        """CREATE TABLE houses(
           id INTEGER PRIMARY KEY,owner_user_id INTEGER,tile_x INTEGER,tile_y INTEGER,
           has_workbench INTEGER DEFAULT 0,built_ts INTEGER DEFAULT 0,
           abandoned INTEGER DEFAULT 0,abandoned_ts INTEGER DEFAULT 0)"""
    )
    db.commit()
    db.close()
    game.DB_PATH = OLD_DB
    game.init_db()
    db = sqlite3.connect(OLD_DB)
    columns = {row[1] for row in db.execute("PRAGMA table_info(houses)")}
    raid_table = db.execute(
        """SELECT COUNT(*) FROM sqlite_master
           WHERE type='table' AND name='house_raid_logs'"""
    ).fetchone()[0]
    expected = {"level", "hp", "max_hp", "auto_defense",
                "auto_defense_damaged", "last_raid_ts"}
    assert expected <= columns
    assert raid_table == 1
    assert db.execute(
        """SELECT COUNT(*) FROM sqlite_master
           WHERE type='table' AND name='map_regions'"""
    ).fetchone()[0] == 1
    assert db.execute(
        """SELECT COUNT(*) FROM sqlite_master
           WHERE type='table' AND name='power_grids'"""
    ).fetchone()[0] == 1
    db.close()
    remove_sqlite(OLD_DB)


def verify_live_code_paths():
    remove_sqlite(TEST_DB)
    game.DB_PATH = TEST_DB
    game.init_db()
    ts = int(time.time())
    with game.app.app_context():
        db = game.get_db()
        password = game.generate_password_hash("verify-pass", method="pbkdf2:sha256")
        db.execute(
            """INSERT INTO users(username,password_hash,approved,created_ts)
               VALUES('deploy_verify',?,1,?)""",
            (password, ts),
        )
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute(
            """INSERT INTO characters
               (user_id,name,hp,tile_x,tile_y,protected_until_ts,created_ts,last_action_ts)
               VALUES(?,?,100,0,0,0,?,?)""",
            (user_id, "部署验收员", ts - 4 * game.DAY_SECONDS, ts),
        )
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute(
            """INSERT INTO character_profiles
               (character_id,nickname,face_claim,background_key,trait_a,trait_b,
                avatar_key,bio,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                char_id,
                "",
                "验收",
                "bg001",
                "optimist",
                "careful",
                "avatar-01",
                "",
                ts,
                ts,
            ),
        )
        db.execute(
            """INSERT INTO houses
               (owner_user_id,tile_x,tile_y,has_workbench,level,hp,max_hp,
                auto_defense,built_ts)
               VALUES(?,0,0,1,1,20,80,0,?)""",
            (user_id, ts),
        )
        house_id = db.execute("SELECT id FROM houses").fetchone()["id"]
        for key in ("wood", "stone", "metal", "parts", "electronics"):
            db.execute(
                """INSERT INTO character_inventory(character_id,resource_key,amount)
                   VALUES(?,?,500)""",
                (char_id, key),
            )
        db.commit()

    client = game.app.test_client()
    with client:
        login = client.post(
            "/login",
            data={"username": "deploy_verify", "password": "verify-pass"},
        )
        assert login.status_code == 302
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "房屋防线".encode("utf-8") in dashboard.data
        assert "最近夜袭战报".encode("utf-8") not in dashboard.data

        # Repair is a real route: it consumes materials and restores structure HP.
        client.post("/action/repair_house")
        with game.app.app_context():
            db = game.get_db()
            house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            wood = db.execute(
                """SELECT amount FROM character_inventory
                   WHERE character_id=? AND resource_key='wood'""",
                (char_id,),
            ).fetchone()["amount"]
            assert house["hp"] == 80
            assert wood == 493

        # Lv1→Lv2→Lv3 are real solo routes; Lv3 is the solo cap.
        client.post("/action/upgrade_house")
        client.post("/action/upgrade_house")
        with game.app.app_context():
            db = game.get_db()
            house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            assert (house["level"], house["hp"], house["max_hp"]) == (3, 220, 220)
        client.post("/action/upgrade_house")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute(
                "SELECT level FROM houses WHERE id=?", (house_id,)
            ).fetchone()["level"] == 3
            db.execute(
                """INSERT INTO shelters(name,tile_x,tile_y,tier,created_ts)
                   VALUES('部署联防站',5,5,2,?)""",
                (ts,),
            )
            shelter_id = db.execute("SELECT id FROM shelters").fetchone()["id"]
            db.execute(
                "UPDATE characters SET shelter_id=? WHERE id=?",
                (shelter_id, char_id),
            )
            db.commit()

        # Shelter Lv2 unlocks the actual Lv4 upgrade and auto-defense.
        client.post("/action/upgrade_house")
        with game.app.app_context():
            db = game.get_db()
            house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            assert (house["level"], house["hp"], house["max_hp"], house["auto_defense"]) == (
                4,
                320,
                320,
                1,
            )
            db.execute(
                """INSERT INTO house_inventory(house_id,resource_key,amount)
                   VALUES(?,'ammo',1)""",
                (house_id,),
            )
            db.execute(
                """UPDATE power_grids SET generator_level=2,charge=10,mode='balanced',updated_ts=?
                   WHERE owner_type='house' AND owner_id=?""",
                (ts, house_id),
            )
            db.commit()

        # A real night raid consumes ammo, weakens but never erases the attack,
        # damages structure, and creates a visible report.
        with game.app.app_context():
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            db = game.get_db()
            raid = db.execute(
                "SELECT * FROM house_raid_logs WHERE house_id=? ORDER BY id DESC",
                (house_id,),
            ).fetchone()
            ammo = db.execute(
                """SELECT amount FROM house_inventory
                   WHERE house_id=? AND resource_key='ammo'""",
                (house_id,),
            ).fetchone()["amount"]
            house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            power = db.execute("""SELECT charge FROM power_grids
                                  WHERE owner_type='house' AND owner_id=?""",
                               (house_id,)).fetchone()["charge"]
            assert ammo == 0
            assert power == 7
            assert raid["counter_damage"] > 0
            assert raid["structure_damage"] >= 1
            assert house["hp"] < house["max_hp"]
        dashboard = client.get("/")
        assert "最近夜袭战报".encode("utf-8") in dashboard.data
        assert "自动反击削弱".encode("utf-8") in dashboard.data

        # Lv5 remains locked at shelter Lv3, unlocks at Lv4, and uses 40% counterfire.
        with game.app.app_context():
            db = game.get_db()
            db.execute("UPDATE houses SET hp=max_hp WHERE id=?", (house_id,))
            db.execute("UPDATE shelters SET tier=3")
            db.commit()
        client.post("/action/upgrade_house")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute(
                "SELECT level FROM houses WHERE id=?", (house_id,)
            ).fetchone()["level"] == 4
            db.execute("UPDATE shelters SET tier=4")
            db.commit()
        client.post("/action/upgrade_house")
        with game.app.app_context():
            db = game.get_db()
            house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
            assert (house["level"], house["hp"], house["max_hp"], house["auto_defense"]) == (
                5,
                450,
                450,
                1,
            )
            db.execute(
                """UPDATE house_inventory SET amount=1
                   WHERE house_id=? AND resource_key='ammo'""",
                (house_id,),
            )
            db.execute("""UPDATE power_grids SET charge=10
                          WHERE owner_type='house' AND owner_id=?""", (house_id,))
            db.commit()
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            latest = game.get_db().execute(
                "SELECT * FROM house_raid_logs WHERE house_id=? ORDER BY id DESC",
                (house_id,),
            ).fetchone()
            assert latest["counter_damage"] == int(
                latest["attack_strength"] * game.HOUSE_LEVELS[5]["counter"]
            )
            assert latest["structure_damage"] >= 1

        # Once structure HP is zero, the next raid attacks the resident and kills.
        with game.app.app_context():
            db = game.get_db()
            db.execute("UPDATE houses SET hp=0 WHERE id=?", (house_id,))
            db.execute("UPDATE characters SET hp=5 WHERE id=?", (char_id,))
            db.commit()
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            character = game.get_db().execute(
                "SELECT status,hp FROM characters WHERE id=?", (char_id,)
            ).fetchone()
            assert character["status"] == "dead"
            assert character["hp"] == 0

    result = {
        "migration": "PASS",
        "dashboard": "PASS",
        "repair_route": "PASS",
        "levels_1_to_5": "PASS",
        "solo_cap_and_shelter_gates": "PASS",
        "level4_and_level5_auto_defense": "PASS",
        "ammo_consumption": "PASS",
        "raid_report": "PASS",
        "breach_and_death": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    try:
        verify_old_schema_migration()
        print(json.dumps(verify_live_code_paths(), ensure_ascii=False, sort_keys=True))
    finally:
        remove_sqlite(TEST_DB)
        remove_sqlite(OLD_DB)
