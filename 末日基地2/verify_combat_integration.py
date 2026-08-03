"""Isolated end-to-end checks for combat links to life, pets, medicine and map rescue."""
import json
import os
import time
from unittest.mock import patch

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_combat_integration.db")


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
                      VALUES('combat_links',?,1,?)""", (password, ts))
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO shelters(name,tile_x,tile_y,has_animal_pen,created_ts)
                      VALUES('验收兽栏',0,0,1,?)""", (ts,))
        shelter_id = db.execute("SELECT id FROM shelters").fetchone()["id"]
        db.execute("""INSERT INTO characters
                      (user_id,name,hp,hunger,thirst,stat_str,stat_spd,stat_int,stat_luck,
                       shelter_id,tamed_animal_key,protected_until_ts,created_ts,last_action_ts)
                      VALUES(?,'联动验收员',100,50,50,8,20,8,8,?,'mid_fighter',0,?,?)""",
                   (user_id, shelter_id, ts - game.DAY_SECONDS, ts))
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','brave','careful','avatar-01',?,?)""",
                   (char_id, ts, ts))
        db.execute("""INSERT INTO tamed_animal_profiles
                      (character_id,animal_key,custom_name,tamed_ts)
                      VALUES(?,'mid_fighter','灰耳',?)""", (char_id, ts))
        for key, amount in (("grilled_fish", 1), ("herbal_tea", 1),
                            ("bandage", 2), ("first_aid", 1)):
            db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                          VALUES(?,?,?)""", (char_id, key, amount))
        db.commit()

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "combat_links", "password": "verify-pass"}).status_code == 302

        # Real life-workshop consumption routes create same-day combat preparation.
        client.post("/homestead/consume", data={"item_key": "grilled_fish"})
        client.post("/homestead/consume", data={"item_key": "herbal_tea"})
        with game.app.app_context():
            db = game.get_db()
            ch = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            prep = game.combat_preparation_for(ch)
            assert prep["food"]["name"] == game.FOOD_RECIPES["grilled_fish"]["name"]
            assert prep["drink"]["name"] == game.DRINK_RECIPES["herbal_tea"]["name"]
            assert prep["damage_bonus"] > 0 and prep["crit_bonus"] > 0

            game.begin_combat(ch, "normal", 100)
            db.execute("""UPDATE characters SET combat_terrain='hallway',combat_intent='bite'
                          WHERE id=?""", (char_id,))
            db.commit()

        page = client.get("/encounter")
        assert page.status_code == 200
        for text in ("生存联动", "香草烤鱼", "荒原草药茶", "踢倒柜架封路", "指挥灰耳"):
            assert text.encode() in page.data

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/combat/terrain")
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert state["combat_tactic_used"] == 1
            assert state["pending_zombie_hp"] < 100
            db.execute("""UPDATE characters SET combat_intent='bite',combat_pet_used=0
                          WHERE id=?""", (char_id,))
            db.commit()

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/combat/pet")
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            assert state["combat_pet_used"] == 1

            # A combat injury persists into the dashboard and is cleared by its real route.
            with patch.object(game.random, "random", return_value=0):
                injury_key = game.maybe_add_combat_injury(state, "bite", False, "验收丧尸")
            assert injury_key == "bleeding"
            injury_id = db.execute("""SELECT id FROM character_injuries
                                      WHERE character_id=? AND status='active'""",
                                   (char_id,)).fetchone()["id"]
            db.execute("""UPDATE characters SET pending_zombie_type=NULL,pending_zombie_hp=0,
                          pending_combat_reward='',hp=35 WHERE id=?""", (char_id,))
            db.commit()

        dashboard = client.get("/")
        assert "持续伤势".encode() in dashboard.data and "撕裂伤".encode() in dashboard.data
        client.post(f"/injury/{injury_id}/treat")
        with game.app.app_context():
            db = game.get_db()
            assert db.execute("""SELECT status FROM character_injuries WHERE id=?""",
                              (injury_id,)).fetchone()["status"] == "treated"
            ch = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            game.begin_combat(ch, "normal", 100)
            db.execute("""UPDATE characters SET combat_terrain='road',combat_intent='bite',
                          combat_signal_used=0 WHERE id=?""", (char_id,))
            db.commit()

        with patch.object(game.random, "random", return_value=.99):
            client.post("/action/combat/signal")
        with game.app.app_context():
            db = game.get_db()
            state = db.execute("SELECT * FROM characters WHERE id=?", (char_id,)).fetchone()
            signal = db.execute("""SELECT * FROM rescue_signals
                                   WHERE requester_character_id=? AND status='open'""",
                                (char_id,)).fetchone()
            assert state["combat_signal_used"] == 1
            assert signal and (signal["tile_x"], signal["tile_y"]) == (0, 0)

    result = {
        "cooking_and_drinks_affect_combat": "PASS",
        "terrain_action_executes": "PASS",
        "pet_command_executes": "PASS",
        "injury_persists_and_treats": "PASS",
        "combat_rescue_reaches_map": "PASS",
        "integration_ui_visible": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
