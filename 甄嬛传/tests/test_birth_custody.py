"""嫔位以下的生母不能亲自抚养：孩子一出生就进皇嗣养育所（抓周前可托付、晋嫔可领回）"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class BirthCustodyTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def deliver(self, cid):
        game.run("UPDATE consorts SET pregnant_since=?,pregnancy_started_ts=100000,prenatal='{}' WHERE id=?", (game.cur_day(), cid))
        with patch.object(game.time, 'time', return_value=186400):
            game.resolve_births(game.cur_day(), False)
        return game.q("SELECT * FROM heirs WHERE mother_id=? ORDER BY id DESC", (cid,), one=True)

    def keep_low(self, cid):
        game.run("UPDATE consorts SET influence=0 WHERE id=?", (cid,))      # 不让母凭子贵把她晋到嫔位

    def test_low_rank_mother_does_not_raise_her_own_child(self):
        self.keep_low(self.tgt)
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else seq[0]):
            h = self.deliver(self.tgt)             # tgt 是贵人（四级）
        self.assertEqual(h['caretaker_id'], 0)
        self.assertTrue(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%不能亲自抚养%'", (self.tgt,), one=True))
        self.assertTrue(game.q("SELECT 1 FROM gazette WHERE text LIKE '%送入皇嗣养育所%'", one=True))

    def test_pin_and_above_keep_their_own_child(self):
        h = self.deliver(self.atk)             # atk 是嫔（五级）
        self.assertEqual(h['caretaker_id'], self.atk)
        self.assertFalse(game.q("SELECT 1 FROM messages WHERE consort_id=? AND text LIKE '%不能亲自抚养%'", (self.atk,), one=True))

    def test_mother_promoted_to_pin_by_the_birth_keeps_her_child(self):
        game.run("UPDATE consorts SET influence=200 WHERE id=?", (self.tgt,))
        with patch.object(game.random, 'choice', side_effect=lambda seq: '皇子' if seq == ['皇子', '公主'] else seq[0]):
            h = self.deliver(self.tgt)
        self.assertEqual(game.get_consort(self.tgt)['rank'], 5)
        self.assertEqual(h['caretaker_id'], self.tgt)

    def test_heirs_page_shows_the_nursery_and_offers_entrust(self):
        self.keep_low(self.tgt)
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else seq[0]):
            self.deliver(self.tgt)
        game.run("UPDATE consorts SET recap_seen_day=99 WHERE id=?", (self.tgt,))
        self.login(self.tgt)
        html = self.client.get('/heirs').get_data(as_text=True)
        self.assertIn('皇嗣养育所', html)
        self.assertNotIn('（自己养）', html)
        self.assertIn('托付', html)

    def test_entrust_from_the_nursery_works_end_to_end(self):
        self.keep_low(self.tgt)
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else seq[0]):
            h = self.deliver(self.tgt)
        game.add_affinity(self.tgt, self.atk, 50)
        self.login(self.tgt)
        self.client.post(f"/heirs/entrust/{h['id']}", data={'target_id': self.atk})
        self.assertEqual(game.get_heir(h['id'])['foster_request_to'], self.atk)
        self.login(self.atk)
        self.client.post(f"/heirs/entrust_reply/{h['id']}", data={'reply': 'yes'})
        after = game.get_heir(h['id'])
        self.assertEqual(after['caretaker_id'], self.atk)
        self.assertEqual(after['mother_id'], self.tgt)

    def test_after_zhuazhou_no_more_entrust(self):
        self.keep_low(self.tgt)
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else seq[0]):
            h = self.deliver(self.tgt)
        game.add_affinity(self.tgt, self.atk, 50)
        game.run("UPDATE heirs SET zhuazhou='seal' WHERE id=?", (h['id'],))
        self.login(self.tgt)
        self.client.post(f"/heirs/entrust/{h['id']}", data={'target_id': self.atk})
        self.assertEqual(game.get_heir(h['id'])['foster_request_to'], 0)

    def test_twins_of_a_low_rank_mother_both_go_to_the_nursery(self):
        game.TWIN_CHANCE = 1
        self.keep_low(self.tgt)
        with patch.object(game.random, 'choice', side_effect=lambda seq: '公主' if seq == ['皇子', '公主'] else seq[0]):
            self.deliver(self.tgt)
        kids = game.q("SELECT * FROM heirs WHERE mother_id=?", (self.tgt,))
        self.assertEqual(len(kids), 2)
        self.assertTrue(all(k['caretaker_id'] == 0 for k in kids))


if __name__ == '__main__':
    unittest.main()
