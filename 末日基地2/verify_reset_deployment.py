"""Isolated acceptance test for account-preserving whole-world reset."""
import os
import shutil
import sqlite3
import time

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_ROOT = os.path.join(ROOT, "_verify_reset_workspace")
TEST_DB = os.path.join(TEST_ROOT, "_verify_reset_deployment.db")


def remove_sqlite(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def run_verification():
    if os.path.isdir(TEST_ROOT):
        shutil.rmtree(TEST_ROOT)
    os.makedirs(TEST_ROOT, exist_ok=True)
    remove_sqlite(TEST_DB)
    game.DB_PATH = TEST_DB
    game.init_db()
    ts = int(time.time())
    with game.app.app_context():
        db = game.get_db()
        admin_hash = game.generate_password_hash("admin-pass", method="pbkdf2:sha256")
        player_hash = game.generate_password_hash("player-pass", method="pbkdf2:sha256")
        db.execute("""INSERT INTO users
                      (username,password_hash,respawn_count,permadead,approved,created_ts)
                      VALUES('admin',?,2,0,1,?)""", (admin_hash, ts - 100))
        db.execute("""INSERT INTO users
                      (username,password_hash,respawn_count,permadead,approved,created_ts)
                      VALUES('player',?,3,1,0,?)""", (player_hash, ts - 50))
        admin_id = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
        player_id = db.execute("SELECT id FROM users WHERE username='player'").fetchone()["id"]
        db.execute("""INSERT INTO characters(user_id,name,created_ts)
                      VALUES(?,'旧角色',?)""", (admin_id, ts))
        char_id = db.execute("SELECT id FROM characters").fetchone()["id"]
        db.execute("""INSERT INTO character_profiles
                      (character_id,background_key,trait_a,trait_b,avatar_key,created_ts,updated_ts)
                      VALUES(?,'bg001','brave','careful','avatar-01',?,?)""",
                   (char_id, ts, ts))
        db.execute("""INSERT INTO character_fish_log
                      (character_id,fish_key,catch_count,first_caught_ts)
                      VALUES(?,'mutant_carp',9,?)""", (char_id, ts))
        db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                      VALUES(?,'wood',99)""", (char_id,))
        db.execute("""INSERT INTO world_tiles(x,y,discovered_ts) VALUES(4,5,?)""", (ts,))
        db.execute("""INSERT INTO action_log(character_id,action,detail,created_ts)
                      VALUES(?,'test','old world',?)""", (char_id, ts))
        db.execute("UPDATE world_state SET day_count=17")
        db.execute("""INSERT OR REPLACE INTO meta(key,value)
                      VALUES('old_world_marker','must disappear')""")
        db.execute("""INSERT OR REPLACE INTO merchant_stock(resource_key,price,stock_amount)
                      VALUES('metal',99,1)""")
        db.commit()
        preserved = {
            row["username"]: (row["id"], row["password_hash"], row["approved"], row["created_ts"])
            for row in db.execute("SELECT * FROM users")
        }

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "admin", "password": "admin-pass"}).status_code == 302
        response = client.post("/admin/reset_world", data={"confirm": "重置"},
                               follow_redirects=True)
        assert response.status_code == 200
        page_text = response.data.decode("utf-8")
        assert "保留2个注册账号" in page_text, page_text[:1200]

    with game.app.app_context():
        db = game.get_db()
        users = list(db.execute("SELECT * FROM users ORDER BY id"))
        assert len(users) == 2
        for user in users:
            assert (user["id"], user["password_hash"], user["approved"], user["created_ts"]) == \
                   preserved[user["username"]]
            assert user["respawn_count"] == 0 and user["permadead"] == 0
        assert db.execute("SELECT COUNT(*) c FROM characters").fetchone()["c"] == 0
        assert db.execute("SELECT COUNT(*) c FROM character_fish_log").fetchone()["c"] == 0
        assert db.execute("SELECT COUNT(*) c FROM world_tiles").fetchone()["c"] == 0
        assert db.execute("SELECT COUNT(*) c FROM action_log").fetchone()["c"] == 0
        cleared_tables = [
            row[0] for row in db.execute(
                """SELECT name FROM sqlite_master
                   WHERE type='table' AND name NOT LIKE 'sqlite_%'
                     AND name NOT IN ('users','world_state','merchant_stock','meta')""")
        ]
        assert all(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
                   for table in cleared_tables)
        world = db.execute("SELECT * FROM world_state WHERE id=1").fetchone()
        assert world["day_count"] == 1
        assert db.execute("""SELECT COUNT(*) c FROM meta
                             WHERE key='old_world_marker'""").fetchone()["c"] == 0
        stocks = list(db.execute("SELECT * FROM merchant_stock"))
        assert {row["resource_key"] for row in stocks} == set(game.MERCHANT_RESOURCES)
        assert all(row["price"] == game.MERCHANT_PRICE and
                   row["stock_amount"] == game.MERCHANT_STOCK_MIN for row in stocks)
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        # users自增序列没有回退，新注册账号不能撞已有账号ID。
        db.execute("""INSERT INTO users(username,password_hash,approved,created_ts)
                      VALUES('after_reset','x',1,?)""", (ts,))
        new_id = db.execute("SELECT id FROM users WHERE username='after_reset'").fetchone()["id"]
        assert new_id > max(admin_id, player_id)
        db.rollback()
        test_backup_dir = os.path.join(TEST_ROOT, "db_backups")
        backups = [
            name for name in os.listdir(test_backup_dir)
            if name.startswith("world_reset_") and name.endswith(".db")
        ]
        assert backups
        backup_path = os.path.join(test_backup_dir, sorted(backups)[-1])
        backup = sqlite3.connect(backup_path)
        try:
            assert backup.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 1
            assert backup.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        finally:
            backup.close()
        os.remove(backup_path)

    result = {
        "registered_accounts_preserved": "PASS",
        "approval_and_password_preserved": "PASS",
        "death_limits_reset": "PASS",
        "all_character_progress_cleared": "PASS",
        "fish_log_regression": "PASS",
        "world_day_reset": "PASS",
        "merchant_initial_state": "PASS",
        "pre_reset_backup": "PASS",
        "database_integrity": "PASS",
    }
    remove_sqlite(TEST_DB)
    shutil.rmtree(TEST_ROOT)
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
