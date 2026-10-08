"""罚跪：扣体质；孕妇小概率动胎气（满 18 小时前小产、满 18 小时后提前临盆），害人的一方禁足并扣圣宠。"""
import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game


class KneelShockTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def pregnant(self, hours):
        game.run("UPDATE consorts SET pregnant_since=9, pregnancy_started_ts=?, health=70, favor=100 WHERE id=?", (game.time.time() - hours * 3600, self.tgt))
        game.run("UPDATE consorts SET favor=100, status='normal' WHERE id=?", (self.atk,))

    def shock(self, roll=0.0):
        with patch.object(game.random, 'random', return_value=roll):
            return game.kneel_shock(game.get_consort(self.tgt), game.get_consort(self.atk))

    def test_not_pregnant_only_loses_health(self):
        game.run("UPDATE consorts SET health=70, pregnant_since=0 WHERE id=?", (self.tgt,))
        self.assertEqual(self.shock(), '')
        self.assertEqual(game.get_consort(self.tgt)['health'], 70 - game.KNEEL_HEALTH_LOSS)
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_early_pregnancy_miscarries_and_punisher_is_blamed(self):
        self.pregnant(2)
        self.assertIn('小产', self.shock())
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 0)
        a = game.get_consort(self.atk)
        self.assertEqual(a['status'], 'confined')
        self.assertEqual(a['favor'], 100 - game.KNEEL_HARM_FAVOR_LOSS)

    def test_late_pregnancy_forces_preterm_and_punisher_is_blamed(self):
        self.pregnant(20)
        self.assertIn('提前临盆', self.shock())
        self.assertTrue(game.prenatal_state(game.get_consort(self.tgt)).get('force_preterm'))
        self.assertEqual(game.get_consort(self.atk)['status'], 'confined')
        game.resolve_births(10, False)
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 0)      # 这一轮就生了
        self.assertEqual(len(game.q('SELECT * FROM heirs WHERE mother_id=?', (self.tgt,))) +
                         len(game.q('SELECT * FROM birth_losses WHERE mother_id=?', (self.tgt,))) >= 1, True)

    def test_antai_saves_the_baby_and_nobody_is_blamed(self):
        self.pregnant(2)
        game.inv_add(self.tgt, 'antai')
        self.assertIn('安胎药', self.shock())
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 9)
        self.assertEqual(game.inv_qty(self.tgt, 'antai'), 0)
        self.assertEqual(game.get_consort(self.atk)['status'], 'normal')

    def test_low_roll_miss_does_nothing(self):
        self.pregnant(2)
        self.assertEqual(self.shock(0.99), '')
        self.assertEqual(game.get_consort(self.tgt)['pregnant_since'], 9)


class ItemDailyLimitTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_renshen_shuhen_qinpu_once_a_day(self):
        game.run("UPDATE consorts SET health=50, appearance=50, talent=50 WHERE id=?", (self.atk,))
        self.login(self.atk)
        for key, col, gain in (('renshen', 'health', 15), ('shuhen', 'appearance', 3), ('qinpu', 'talent', 3)):
            game.inv_add(self.atk, key, 2)
            self.client.post(f'/shop/use/{key}')
            self.client.post(f'/shop/use/{key}')
            self.assertEqual(game.get_consort(self.atk)[col], 50 + gain, key)
            self.assertEqual(game.inv_qty(self.atk, key), 1, key)      # 第二次被拒，药不扣
            game.run("DELETE FROM daily_counters")
            self.client.post(f'/shop/use/{key}')
            self.assertEqual(game.get_consort(self.atk)[col], 50 + gain * 2, key)      # 隔天又能用


class HarmLogTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def add(self, method, result, drug='', ts=1000):
        return game.run("INSERT INTO intrigues (day, attacker_id, target_id, method, status, result, created_ts, drug) VALUES (?,?,?,?,'done',?,?,?)",
                        (game.cur_day(), self.atk, self.tgt, method, result, ts, drug)).lastrowid

    def test_names_shown_only_when_known(self):
        self.add('rumor', 'success', ts=1)                 # 得手，没眼线：未知
        self.add('rumor', 'caught', ts=2)                  # 败露：看得到
        self.add('steal', 'success', ts=3)                 # 明面上的事：看得到
        self.add('rumor', 'fizzle', ts=4)                  # 没成没人察觉：不记
        game.run("UPDATE consorts SET eyes_until_day=0 WHERE id=?", (self.tgt,))
        log = game.recent_harm(game.get_consort(self.tgt))
        self.assertEqual(len(log), 3)
        self.assertEqual([h['known'] for h in log], [True, True, False])      # id 倒序
        name = game.display_name(game.get_consort(self.atk))
        self.assertEqual(log[0]['who'], name)
        self.assertEqual(log[2]['who'], '未知')
        game.run("UPDATE consorts SET eyes_until_day=99999 WHERE id=?", (self.tgt,))
        self.assertTrue(all(h['known'] for h in game.recent_harm(game.get_consort(self.tgt))))      # 有眼线全看得到

    def test_pregnancy_drug_is_always_unknown_and_limit_is_ten(self):
        game.run("UPDATE consorts SET eyes_until_day=99999 WHERE id=?", (self.tgt,))
        self.add('drug', 'success', drug='honghua')
        self.add('drug', 'caught', drug='musk')
        for _ in range(12): self.add('rumor', 'success')
        self.assertEqual(len(game.recent_harm(game.get_consort(self.tgt))), 10)
        game.run("DELETE FROM intrigues WHERE method='rumor'")
        log = game.recent_harm(game.get_consort(self.tgt))
        self.assertEqual([h['who'] for h in log], ['未知', '未知'])

    def test_home_page_shows_the_section(self):
        self.add('rumor', 'caught')
        self.login(self.tgt)
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('近来害过我的人', page)
        self.assertIn(game.display_name(game.get_consort(self.atk)), page)


class VirtueSourceTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def test_sutra_and_charity_give_virtue_once_a_day(self):
        game.run("UPDATE consorts SET virtue=30, energy=8, silver=500, status='normal' WHERE id=?", (self.atk,))
        self.login(self.atk)
        for key, cost_silver, cost_energy in (('sutra', 0, 1), ('charity', 40, 0)):
            before = game.get_consort(self.atk)
            self.client.post(f'/act/{key}', data={'back': 'shoukanggong' if key == 'sutra' else 'jingren'})
            after = game.get_consort(self.atk)
            self.assertEqual(after['virtue'], before['virtue'] + 2, key)
            self.assertEqual((before['silver'] - after['silver'], before['energy'] - after['energy']), (cost_silver, cost_energy), key)
            self.client.post(f'/act/{key}')
            self.assertEqual(game.get_consort(self.atk)['virtue'], after['virtue'], key)      # 每天一次

    def test_shoukanggong_place_and_map_tile(self):
        self.login(self.atk)
        page = self.client.get('/place/shoukanggong')
        self.assertEqual(page.status_code, 200)
        self.assertIn('抄经', page.get_data(as_text=True))
        self.assertIn('施粥赈济', self.client.get('/place/jingren').get_data(as_text=True))
        home = self.client.get('/').get_data(as_text=True)
        self.assertIn('寿康宫', home)
        self.assertIn('/place/shoukanggong', home)


if __name__ == '__main__':
    unittest.main()
