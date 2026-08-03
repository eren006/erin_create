"""Isolated acceptance test for the unified power/noise/population loop."""
import json
import os
import sqlite3
import time

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_power_deployment.db")


def cleanup():
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(TEST_DB + suffix)
        except FileNotFoundError:
            pass


def amount(db, table, id_col, id_value, key):
    row = db.execute(
        f"SELECT amount FROM {table} WHERE {id_col}=? AND resource_key=?",
        (id_value, key)).fetchone()
    return row["amount"] if row else 0


def verify():
    cleanup()
    game.DB_PATH = TEST_DB
    game.init_db()
    ts = int(time.time())
    with game.app.app_context():
        db = game.get_db()
        password = game.generate_password_hash("verify-pass", method="pbkdf2:sha256")
        db.execute("""INSERT INTO users(username,password_hash,approved,created_ts)
                      VALUES('power_verify',?,1,?)""", (password, ts))
        uid = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO characters
                      (user_id,name,hp,wallet,storage_capacity,tile_x,tile_y,
                       protected_until_ts,created_ts,last_action_ts)
                      VALUES(?,'电网验收员',100,100,2000,0,0,0,?,?)""",
                   (uid, ts - 5 * game.DAY_SECONDS, ts))
        cid = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','optimist','careful','avatar-01',?,?)""",
                   (cid, ts, ts))
        db.execute("""INSERT INTO houses
                      (owner_user_id,tile_x,tile_y,has_workbench,level,hp,max_hp,
                       auto_defense,built_ts)
                      VALUES(?,0,0,1,4,320,320,1,?)""", (uid, ts))
        hid = db.execute("SELECT id FROM houses").fetchone()["id"]
        db.execute("""INSERT INTO personal_homesteads
                      (character_id,has_kitchen,created_ts) VALUES(?,1,?)""", (cid, ts))
        for key in ("wood", "metal", "parts", "electronics", "fish_meat", "herb"):
            db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                          VALUES(?,?,200)""", (cid, key))
        for key, value in (("fuel", 5), ("ammo", 5)):
            db.execute("""INSERT INTO house_inventory(house_id,resource_key,amount)
                          VALUES(?,?,?)""", (hid, key, value))
        db.execute("""UPDATE merchant_stock SET price=5,stock_amount=5
                      WHERE resource_key='fuel'""")
        db.commit()

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "power_verify", "password": "verify-pass"}).status_code == 302
        assert "房屋电网".encode() in client.get("/").data
        assert client.get("/homestead").status_code == 200
        merchant_page = client.get("/merchant")
        assert merchant_page.status_code == 200 and "回收燃油".encode() in merchant_page.data
        client.post("/action/merchant_buy", data={"resource_key": "fuel", "amount": 1})
        with game.app.app_context():
            assert amount(game.get_db(), "character_inventory", "character_id", cid, "fuel") == 1

        # Lv1 hand power: fuel-free, daily-limited and genuinely noisy.
        client.post("/power/upgrade", data={"target": "house"})
        with game.app.app_context():
            db = game.get_db()
            grid = db.execute("""SELECT * FROM power_grids
                                 WHERE owner_type='house' AND owner_id=?""", (hid,)).fetchone()
            assert grid["generator_level"] == 1
            before_noise = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"]
        client.post("/power/generate", data={"target": "house"})
        with game.app.app_context():
            db = game.get_db()
            grid = db.execute("SELECT * FROM power_grids WHERE owner_type='house' AND owner_id=?",
                              (hid,)).fetchone()
            after_noise = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"]
            assert grid["charge"] == 5
            assert after_noise - before_noise == 2
        client.post("/power/generate", data={"target": "house"})
        with game.app.app_context():
            assert game.get_db().execute(
                "SELECT charge FROM power_grids WHERE owner_type='house' AND owner_id=?",
                (hid,)).fetchone()["charge"] == 5

        # Lv2 consumes stored fuel; quiet mode trades output for lower noise.
        with game.app.app_context():
            db = game.get_db()
            db.execute("UPDATE world_state SET day_count=2 WHERE id=1")
            db.commit()
        client.post("/power/upgrade", data={"target": "house"})
        client.post("/power/mode", data={"target": "house", "mode": "quiet"})
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE power_grids SET charge=0,last_generation_day=0
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.commit()
            fuel_before = amount(db, "house_inventory", "house_id", hid, "fuel")
            noise_before = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"]
        client.post("/power/generate", data={"target": "house"})
        with game.app.app_context():
            db = game.get_db()
            grid = db.execute("SELECT * FROM power_grids WHERE owner_type='house' AND owner_id=?",
                              (hid,)).fetchone()
            assert grid["charge"] == 12
            assert amount(db, "house_inventory", "house_id", hid, "fuel") == fuel_before - 1
            assert db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"] - noise_before == 6

        # Defense reserve blocks ordinary equipment but critical defenses can drain it.
        client.post("/power/mode", data={"target": "house", "mode": "defense"})
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE power_grids SET charge=8
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.commit()
            assert not game.consume_power("house", hid, 3, "普通设备", cid)
            assert game.consume_power("house", hid, 3, "夜袭防御", cid, critical=True)
            assert game.get_db().execute(
                "SELECT charge FROM power_grids WHERE owner_type='house' AND owner_id=?",
                (hid,)).fetchone()["charge"] == 5

        # Cooking uses one power and noise1; without power it falls back to wood and noise5.
        client.post("/power/mode", data={"target": "house", "mode": "balanced"})
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE power_grids SET charge=2
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.commit()
            noise_before = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"]
        client.post("/homestead/cook", data={"recipe_key": "grilled_fish"})
        with game.app.app_context():
            db = game.get_db()
            assert db.execute(
                "SELECT charge FROM power_grids WHERE owner_type='house' AND owner_id=?",
                (hid,)).fetchone()["charge"] == 1
            assert db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"] - noise_before == 1
            wood_before = amount(db, "character_inventory", "character_id", cid, "wood")
            db.execute("""UPDATE power_grids SET charge=0
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.commit()
            noise_before = db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"]
        client.post("/homestead/cook", data={"recipe_key": "grilled_fish"})
        with game.app.app_context():
            db = game.get_db()
            assert amount(db, "character_inventory", "character_id", cid, "wood") == wood_before - 1
            assert db.execute(
                "SELECT noise FROM map_regions WHERE region_x=0 AND region_y=0").fetchone()["noise"] - noise_before == 5

        # Auto-defense requires both power and ammunition; losing either leaves ammo untouched.
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE power_grids SET charge=3
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.execute("UPDATE houses SET hp=max_hp WHERE id=?", (hid,))
            db.commit()
            ammo_before = amount(db, "house_inventory", "house_id", hid, "ammo")
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            db = game.get_db()
            assert amount(db, "house_inventory", "house_id", hid, "ammo") == ammo_before - 1
            assert db.execute(
                "SELECT charge FROM power_grids WHERE owner_type='house' AND owner_id=?",
                (hid,)).fetchone()["charge"] == 0
            db.execute("UPDATE houses SET hp=max_hp WHERE id=?", (hid,))
            db.commit()
            ammo_before = amount(db, "house_inventory", "house_id", hid, "ammo")
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            db = game.get_db()
            latest = db.execute(
                "SELECT summary FROM house_raid_logs WHERE house_id=? ORDER BY id DESC",
                (hid,)).fetchone()["summary"]
            assert amount(db, "house_inventory", "house_id", hid, "ammo") == ammo_before
            assert "断电未启动" in latest

        # Damaged grids have a real repair route.
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE power_grids SET damaged=1,charge=0
                          WHERE owner_type='house' AND owner_id=?""", (hid,))
            db.commit()
        client.post("/power/repair", data={"target": "house"})
        with game.app.app_context():
            assert game.get_db().execute(
                "SELECT damaged FROM power_grids WHERE owner_type='house' AND owner_id=?",
                (hid,)).fetchone()["damaged"] == 0

            # A shelter uses the same grid: furnace and greenhouse consume power,
            # then the final point is reserved for one powered watchtower at night.
            db = game.get_db()
            db.execute("""INSERT INTO shelters
                          (name,tile_x,tile_y,tier,defense_tower,has_furnace,
                           has_greenhouse,created_ts)
                          VALUES('电力联防站',5,5,2,1,1,1,?)""", (ts,))
            sid = db.execute("SELECT id FROM shelters WHERE name='电力联防站'").fetchone()["id"]
            db.execute("""INSERT INTO power_grids
                          (owner_type,owner_id,generator_level,charge,mode,updated_ts)
                          VALUES('shelter',?,2,5,'balanced',?)""", (sid, ts))
            for key, value in (("raw_water", 10), ("wood", 10), ("rare_seed", 1)):
                db.execute("""INSERT INTO shelter_inventory(shelter_id,resource_key,amount)
                              VALUES(?,?,?)""", (sid, key, value))
            db.execute("""UPDATE characters SET tile_x=5,tile_y=5,shelter_id=?
                          WHERE id=?""", (sid, cid))
            db.commit()
            shelter_wood = amount(db, "shelter_inventory", "shelter_id", sid, "wood")
        client.post("/action/furnace_start")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute(
                "SELECT charge FROM power_grids WHERE owner_type='shelter' AND owner_id=?",
                (sid,)).fetchone()["charge"] == 3
            assert amount(db, "shelter_inventory", "shelter_id", sid, "wood") == shelter_wood
        client.post("/action/plant_seed")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute(
                "SELECT charge FROM power_grids WHERE owner_type='shelter' AND owner_id=?",
                (sid,)).fetchone()["charge"] == 1
            assert amount(db, "shelter_inventory", "shelter_id", sid, "prized_herb") == 2
            db.execute("""UPDATE power_grids SET mode='defense'
                          WHERE owner_type='shelter' AND owner_id=?""", (sid,))
            db.commit()
            raw = sqlite3.connect(TEST_DB)
            raw.row_factory = sqlite3.Row
            game._resolve_night_raid(raw)
            raw.close()
            db = game.get_db()
            assert db.execute(
                "SELECT charge FROM power_grids WHERE owner_type='shelter' AND owner_id=?",
                (sid,)).fetchone()["charge"] == 0
            assert db.execute("""SELECT COUNT(*) c FROM power_logs
                                 WHERE owner_type='shelter' AND owner_id=?
                                   AND detail LIKE '%瞭望塔%'""", (sid,)).fetchone()["c"] == 1

    result = {
        "shared_grid_schema": "PASS",
        "generator_upgrade_and_daily_limit": "PASS",
        "fuel_consumption": "PASS",
        "quiet_mode_tradeoff": "PASS",
        "defense_power_reserve": "PASS",
        "electric_vs_fire_cooking": "PASS",
        "powered_auto_defense": "PASS",
        "blackout_keeps_ammo": "PASS",
        "grid_damage_and_repair": "PASS",
        "powered_water_furnace": "PASS",
        "powered_greenhouse": "PASS",
        "powered_watchtower": "PASS",
        "dashboard_power_controls": "PASS",
    }
    cleanup()
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
    finally:
        cleanup()
