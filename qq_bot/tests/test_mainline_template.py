"""成长册网页模板字段与后端返回结构保持一致。"""

import unittest

from flask import render_template

import web_app


class MainlineTemplateTest(unittest.TestCase):
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
