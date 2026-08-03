"""网页数字QQ账号与机器人 openid 的绑定回归测试。"""

import tempfile
import unittest
from pathlib import Path

from plugins.hp_core import storage as core
from plugins.hp_core import web_binding
import web_auth


class WebBindingTest(unittest.TestCase):
    def setUp(self):
        self.box = tempfile.TemporaryDirectory(prefix="hp-web-binding-")
        db_path = Path(self.box.name) / "hogwarts.db"
        core.DB_PATH = db_path
        web_auth.DB_PATH = db_path
        core.init_db()
        web_binding.init_db()
        web_auth.init_db()
        now = core.now()
        conn = core.get_conn()
        conn.execute(
            "CREATE TABLE player_wands (uid TEXT PRIMARY KEY, wood TEXT NOT NULL, "
            "core TEXT NOT NULL, length TEXT NOT NULL, flexibility TEXT NOT NULL, chosen_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO players(uid,name,house,grade,stamina,stamina_updated_at,galleons,created_at,updated_at) "
            "VALUES('openid-32-character-player-id','测试生','拉文克劳',1,50,?,0,?,?)",
            (now, now, now),
        )
        conn.execute(
            "INSERT INTO player_wands(uid,wood,core,length,flexibility,chosen_at) "
            "VALUES('openid-32-character-player-id','柳木','凤凰尾羽','十一英寸','柔韧',?)",
            (now,),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.box.cleanup()

    def test_binding_code_links_numeric_login_to_openid(self):
        issued = web_binding.issue("openid-32-character-player-id", "123456789")
        with self.assertRaises(web_auth.AuthError):
            web_auth.request_account("987654321", issued["code"], "冒用")
        result = web_auth.request_account("123456789", issued["code"], "测试")
        self.assertEqual(result["name"], "测试生")
        account = web_auth.get_account("123456789")
        self.assertEqual(account["player_uid"], "openid-32-character-player-id")
        web_auth.approve("123456789")
        token = web_auth.login("123456789", web_auth.DEFAULT_PASSWORD)
        session = web_auth.session_user(token)
        self.assertEqual(session["uid"], "123456789")
        self.assertEqual(session["player_uid"], "openid-32-character-player-id")
        with self.assertRaises(web_auth.AuthError):
            web_auth.request_account("123456789", issued["code"], "重复使用")


if __name__ == "__main__":
    unittest.main()
