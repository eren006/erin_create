"""Isolated acceptance checks for the 100 concrete character origin stories."""
import json
import os
import time

import app as game


ROOT = os.path.dirname(os.path.abspath(__file__))
TEST_DB = os.path.join(ROOT, "_verify_background_stories.db")


def remove_sqlite(path):
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def run_verification():
    stories = game.CHARACTER_BACKGROUNDS
    assert list(stories) == [f"bg{i:03d}" for i in range(1, 101)]
    assert len({row["name"] for row in stories.values()}) == 100
    assert len({row["desc"] for row in stories.values()}) == 100
    fixed_names = ("乔岚", "陈策", "阿鹭", "宋芽", "许苗", "罗小川",
                   "卓玛", "周姨", "顾遥", "叶南", "林川", "小满",
                   "韩叔", "老周", "闻舟", "方婆婆", "沈星")
    for row in stories.values():
        assert len(row["desc"]) >= 120
        assert "北辰" in row["desc"]
        assert "你出生在" in row["desc"] and "灾变前" in row["desc"]
        assert not any(name in row["desc"] for name in fixed_names)

    remove_sqlite(TEST_DB)
    game.DB_PATH = TEST_DB
    game.init_db()
    ts = int(time.time())
    with game.app.app_context():
        db = game.get_db()
        password = game.generate_password_hash("verify-pass", method="pbkdf2:sha256")
        db.execute("""INSERT INTO users(username,password_hash,approved,created_ts)
                      VALUES('story_verify',?,1,?)""", (password, ts))
        user_id = db.execute("SELECT id FROM users").fetchone()["id"]
        db.execute("""INSERT INTO characters(user_id,name,created_ts,last_action_ts)
                      VALUES(?,'故事验收员',?,?)""", (user_id, ts, ts))
        db.commit()

    client = game.app.test_client()
    with client:
        assert client.post("/login", data={
            "username": "story_verify", "password": "verify-pass"}).status_code == 302
        creation = client.get("/profile")
        assert creation.status_code == 200
        assert "100段具体身世".encode() in creation.data
        assert "SELECTED MEMORY".encode() in creation.data
        assert stories["bg001"]["desc"].encode() in creation.data

        response = client.post("/profile", data={
            "avatar_key": "avatar-01",
            "nickname": "旧闻",
            "face_claim": "",
            "background_key": "bg100",
            "trait_a": "optimist",
            "trait_b": "careful",
            "bio": "",
        })
        assert response.status_code == 302
        with game.app.app_context():
            saved = game.get_db().execute(
                "SELECT background_key FROM character_profiles").fetchone()
            assert saved["background_key"] == "bg100"
        locked = client.get("/profile")
        assert locked.status_code == 200
        assert "身世记录".encode() in locked.data
        assert stories["bg100"]["desc"].encode() in locked.data

    result = {
        "one_hundred_stable_keys": "PASS",
        "one_hundred_unique_stories": "PASS",
        "anonymous_life_histories": "PASS",
        "creation_preview": "PASS",
        "saved_profile_compatibility": "PASS",
    }
    remove_sqlite(TEST_DB)
    return result


if __name__ == "__main__":
    print(json.dumps(run_verification(), ensure_ascii=False, sort_keys=True))
