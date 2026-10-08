"""孩子生病：不养在身边的生母也要收到一条提醒（写得可怜一点）。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class HeirIllNoticeTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def heir(self, caretaker):
        hid = game.run("INSERT INTO heirs(mother_id,caretaker_id,gender,ordinal,born_day,health_max,health) VALUES(?,?,'皇子',9,1,100,70)",
                       (self.atk, caretaker)).lastrowid
        return game.get_heir(hid)

    def ill(self, h, severe=False):
        with patch.object(game.random, 'random', return_value=0.0 if severe else 0.99):
            game.heir_fall_ill(h, game.cur_day())

    def last(self, cid):
        return game.q("SELECT text FROM messages WHERE consort_id=? ORDER BY id DESC", (cid,), one=True)['text']

    def count(self, cid):
        return game.q("SELECT COUNT(*) n FROM messages WHERE consort_id=? AND text LIKE '%病了%'", (cid,), one=True)['n']

    def test_mother_raising_her_own_child_gets_one_normal_notice(self):
        self.ill(self.heir(self.atk))
        self.assertEqual(self.count(self.atk), 1)
        self.assertIn('请太医', self.last(self.atk))

    def test_mother_gets_pitiful_notice_when_child_is_raised_by_someone_else(self):
        self.ill(self.heir(self.tgt))
        self.assertIn('请太医', self.last(self.tgt))                  # 抚养人收到操作提示
        mother = self.last(self.atk)
        self.assertIn('不在你身边', mother)
        self.assertIn('额娘', mother)
        self.assertIn(game.display_name(game.get_consort(self.tgt)), mother)
        self.assertEqual(self.count(self.atk), 1)

    def test_mother_gets_pitiful_notice_for_children_in_the_nursery(self):
        self.ill(self.heir(0), severe=True)
        mother = self.last(self.atk)
        self.assertIn('养育所', mother)
        self.assertIn('额娘', mother)
        self.assertIn('凶多吉少', mother)


if __name__ == '__main__':
    unittest.main()
