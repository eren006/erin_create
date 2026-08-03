"""Isolated acceptance test for tactical combat and aftermath choices."""
import os
import time
from unittest.mock import patch

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_combat_deployment.db")


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
                      VALUES('combat_verify',?,1,?)""", (password, ts))
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO characters
                      (user_id,name,hp,hunger,thirst,stat_str,stat_spd,stat_luck,
                       protected_until_ts,created_ts,last_action_ts)
                      VALUES(?,'战术验收员',100,100,100,5,20,5,0,?,?)""",
                   (user_id, ts - 5 * game.DAY_SECONDS, ts))
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','brave','careful','avatar-01',?,?)""",
                   (char_id, ts, ts))
        db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                      VALUES(?,'bandage',2)""", (char_id,))
        db.commit()
        ch = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
        game.begin_combat(ch, "fast", 80)
        db.execute("""UPDATE characters SET combat_intent='pounce',combat_terrain='hallway'
                      WHERE id=?""", (char_id,))
        db.commit()

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "combat_verify", "password": "verify-pass"}).status_code == 302
        page = client.get("/encounter")
        assert page.status_code == 200
        for text in ("敌人意图", "稳守", "瞄准 / 蓄力", "脱离战斗"):
            assert text.encode() in page.data

        with game.app.app_context():
            before = game.get_db().execute(
                "SELECT hp FROM characters WHERE id=?", (char_id,)).fetchone()["hp"]
        with patch.object(game.random, "random", return_value=0.1):
            response = client.post("/action/combat/guard")
        assert response.status_code == 302
        with game.app.app_context():
            db = game.get_db()
            guarded = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert 0 < before - guarded["hp"] <= 4
            assert guarded["combat_round_no"] == 2

            db.execute("""UPDATE characters SET equipped_weapon='crossbow',weapon_durability=100,
                          pending_zombie_type='tank',pending_zombie_hp=100,combat_max_hp=100,
                          combat_round_no=1,combat_intent='smash',combat_terrain='road',
                          combat_reload=0,combat_status='' WHERE id=?""", (char_id,))
            db.commit()
        with patch.object(game.random, "random", return_value=0.9):
            client.post("/action/combat/quick")
        with game.app.app_context():
            assert game.get_db().execute(
                "SELECT combat_reload FROM characters WHERE id=?", (char_id,)
            ).fetchone()["combat_reload"] == 1
        client.post("/action/combat/reload")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("SELECT combat_reload FROM characters WHERE id=?",
                              (char_id,)).fetchone()["combat_reload"] == 0
            db.execute("""UPDATE characters SET equipped_weapon='fist',pending_zombie_type='normal',
                          pending_zombie_hp=1,combat_max_hp=10,combat_round_no=1,
                          combat_intent='bite',combat_terrain='road',combat_status=''
                          WHERE id=?""", (char_id,))
            db.commit()
        with patch.object(game.random, "random", return_value=0.9):
            response = client.post("/action/combat/quick")
        assert response.headers["Location"].endswith("/combat/reward")
        reward_page = client.get("/combat/reward")
        assert "深度搜刮".encode() in reward_page.data
        with game.app.app_context():
            db = game.get_db()
            db.execute("""UPDATE map_regions SET noise=20,threat=20
                          WHERE region_x=0 AND region_y=0""")
            db.commit()
        client.post("/combat/reward", data={"choice": "clean"})
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            region = db.execute("""SELECT * FROM map_regions
                                   WHERE region_x=0 AND region_y=0""").fetchone()
            assert not state["pending_combat_reward"]
            assert region["noise"] == 16 and region["threat"] == 17

        # Defense stance is persisted through the real player route.
        with game.app.app_context():
            db = game.get_db()
            db.execute("""INSERT INTO houses(owner_user_id,tile_x,tile_y,built_ts)
                          VALUES(?,0,0,?)""", (user_id, ts))
            db.commit()
        client.post("/action/house_raid_stance", data={"stance": "storage"})
        with game.app.app_context():
            assert game.get_db().execute(
                "SELECT raid_stance FROM houses WHERE owner_user_id=?", (user_id,)
            ).fetchone()["raid_stance"] == "storage"

    result = {
        "intent_telegraph_ui": "PASS",
        "guard_counterplay": "PASS",
        "crossbow_reload_cycle": "PASS",
        "aftermath_choice": "PASS",
        "regional_cleanup_effect": "PASS",
        "offline_raid_stance": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
