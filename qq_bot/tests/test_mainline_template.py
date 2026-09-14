"""成长册网页模板字段与后端返回结构保持一致。"""

import tempfile
import unittest
from pathlib import Path

from flask import render_template

import web_app
from plugins.hp_core import storage as core


class MainlineTemplateTest(unittest.TestCase):
    def setUp(self):
        # base.html 的全局上下文会查当前游戏天数，这里必须给一个独立、有效的
        # 测试库，不能依赖别的测试用例遗留下来的 core.DB_PATH（那个临时目录
        # 跑完就被清掉了，全量跑测试时顺序一变就会踩到"打不开数据库文件"）。
        self.box = tempfile.TemporaryDirectory(prefix="hp-mainline-template-")
        core.DB_PATH = Path(self.box.name) / "hogwarts.db"
        core.init_db()

    def tearDown(self):
        self.box.cleanup()

    def test_entries_are_rendered(self):
        book = {
            "entries": [{
                "key": "first_light", "grade": 1, "title": "第一束魔杖光",
                "requirement": "学会「荧光闪烁」", "reward": 10,
                "completed": False, "claimed": False, "progress": "0/1",
            }],
            "newly_claimed": [], "reward": 0, "grade": 1,
        }
        with web_app.app.test_request_context("/mainline"):
            html = render_template("web/mainline.html", book=book)
        self.assertIn("第一束魔杖光", html)
        self.assertIn("进度 0/1", html)


if __name__ == "__main__":
    unittest.main()
