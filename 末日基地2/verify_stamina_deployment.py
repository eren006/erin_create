"""Isolated acceptance checks for soft stamina costs, recovery and penalties."""
import json
import os
import time
from unittest.mock import patch

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_stamina_deployment.db")


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
                      VALUES('stamina_verify',?,1,?)""", (password, ts))
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO characters
                      (user_id,name,hp,hunger,thirst,stat_spd,protected_until_ts,
                       has_fishing_rod,created_ts,last_action_ts)
                      VALUES(?,'体力验收员',100,100,100,10,?,1,?,?)""",
                   (user_id, ts + 86400, ts, ts))
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','light_foot','careful','avatar-01',?,?)""",
                   (char_id, ts, ts))
        # 二十九节:鱼竿改成普通背包物品了,has_fishing_rod这个开关字段不再是钓鱼判定依据
        db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                      VALUES(?,'fishing_rod',1)""", (char_id,))
        db.commit()
        assert db.execute("SELECT stamina FROM characters WHERE id=?",
                          (char_id,)).fetchone()["stamina"] == 100

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "stamina_verify", "password": "verify-pass"}).status_code == 302

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/move", data={"dir": "n"})
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert state["tile_y"] == 1 and state["stamina"] == 96
            db.execute("""UPDATE characters SET stamina=3,stamina_updated_ts=?,
                          move_cooldown_until_ts=0 WHERE id=?""", (ts, char_id))
            db.commit()

        # Zero stamina is a soft penalty: movement still succeeds and makes more noise.
        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/move", data={"dir": "n"})
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert state["tile_y"] == 2 and state["stamina"] == 0
            event = db.execute("""SELECT noise_added FROM region_threat_events
                                  WHERE character_id=? AND event_key='move'
                                  ORDER BY id DESC LIMIT 1""", (char_id,)).fetchone()
            assert event["noise_added"] == 2
            db.execute("""INSERT INTO resource_nodes
                          (tile_x,tile_y,resource_key,rarity,max_amount,current_amount)
                          VALUES(0,2,'wood','normal',20,20)""")
            node_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/gather", data={"node_id": node_id})
        with game.app.app_context():
            db = game.get_db()
            wood = db.execute("""SELECT amount FROM character_inventory
                                 WHERE character_id=? AND resource_key='wood'""",
                              (char_id,)).fetchone()["amount"]
            assert wood == 3  # base 5 x zero-stamina efficiency 70%
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert state["stamina"] == 0

            # Real-time recovery catches up lazily.
            elapsed = 2 * game.STAMINA_RECOVERY_SECONDS + 1
            db.execute("""UPDATE characters SET stamina=20,stamina_updated_ts=?
                          WHERE id=?""", (game.now_ts() - elapsed, char_id))
            db.commit()
            recovered = game.settle_stamina(
                db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone())
            assert recovered["stamina"] == 22

            # Exhaustion directly affects combat escape odds and round costs.
            db.execute("""UPDATE characters SET stamina=100,stamina_updated_ts=? WHERE id=?""",
                       (game.now_ts(), char_id))
            db.commit()
            rested = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            game.begin_combat(rested, "normal", 100)
            rested = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            normal_flee = game.combat_flee_rate(rested, game.ZOMBIE_TYPES["normal"])
            db.execute("UPDATE characters SET stamina=0,stamina_updated_ts=? WHERE id=?",
                       (game.now_ts(), char_id))
            db.commit()
            exhausted = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            tired_flee = game.combat_flee_rate(exhausted, game.ZOMBIE_TYPES["normal"])
            assert normal_flee - tired_flee >= .14
            db.execute("""UPDATE characters SET stamina=50,stamina_updated_ts=?,
                          combat_intent='bite' WHERE id=?""", (game.now_ts(), char_id))
            db.commit()

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/combat/guard")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT stamina FROM characters WHERE id=?",
                              (char_id,)).fetchone()["stamina"] == 47
            db.execute("""UPDATE characters SET pending_zombie_type=NULL,pending_zombie_hp=0,
                          pending_combat_reward='',stamina=40,stamina_updated_ts=?,
                          tile_x=20,tile_y=20 WHERE id=?""", (game.now_ts(), char_id))
            db.execute("""INSERT OR REPLACE INTO world_tiles(x,y,discovered_ts,is_water)
                          VALUES(20,20,?,1)""", (game.now_ts(),))
            db.commit()

        # Starting a fishing session costs once; reloading the same session costs nothing.
        assert client.get("/fishing").status_code == 200
        assert client.get("/fishing").status_code == 200
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT stamina FROM characters WHERE id=?",
                              (char_id,)).fetchone()["stamina"] == 34
            db.execute("""UPDATE characters SET pending_fish_key=NULL,pending_fish_started_ts=0,
                          stamina=10,stamina_updated_ts=? WHERE id=?""",
                       (game.now_ts(), char_id))
            db.commit()

        # A real recreation route restores stamina as well as recreation.
        client.post("/recreation", data={"activity_key": "quiet"})
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT stamina FROM characters WHERE id=?",
                              (char_id,)).fetchone()["stamina"] == 32
            db.execute("""UPDATE characters SET tile_x=30,tile_y=30,stamina=50,
                          stamina_updated_ts=? WHERE id=?""", (game.now_ts(), char_id))
            db.execute("""INSERT OR REPLACE INTO world_tiles(x,y,discovered_ts,is_water,has_building)
                          VALUES(30,30,?,0,0)""", (game.now_ts(),))
            db.commit()

        assert client.get("/survival-tech").status_code == 200
        with patch.object(game.random, "random", return_value=.99):
            client.post("/survival-tech/ruin/dismantle", data={"part_key": "furniture"})
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT stamina FROM characters WHERE id=?",
                              (char_id,)).fetchone()["stamina"] == 40
            for key in ("raw_food", "clean_water"):
                db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                              VALUES(?,?,5) ON CONFLICT(character_id,resource_key)
                              DO UPDATE SET amount=5""", (char_id, key))
            db.commit()

        client.post("/expeditions/start", data={"route_key": "suburb", "strategy": "balanced"})
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT stamina FROM characters WHERE id=?",
                              (char_id,)).fetchone()["stamina"] == 28
            assert db.execute("""SELECT 1 FROM expeditions
                                 WHERE character_id=? AND status='active'""",
                              (char_id,)).fetchone()

    result = {
        "schema_default_and_migration": "PASS",
        "movement_cost": "PASS",
        "zero_stamina_still_moves": "PASS",
        "exhaustion_noise_and_yield_penalty": "PASS",
        "real_time_recovery": "PASS",
        "combat_cost_and_flee_penalty": "PASS",
        "fishing_cost_once": "PASS",
        "recreation_restores_stamina": "PASS",
        "ruin_dismantle_cost": "PASS",
        "offline_expedition_cost": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
