import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game = fixtures.game
PRETERM_T = 100000 + int(game.PRETERM_START_HOURS * 3600)      # 孕期走到可能早产的那一刻


class PretermTests(unittest.TestCase):
    setUp = fixtures.LifecycleTests.setUp
    tearDown = fixtures.LifecycleTests.tearDown
    player = fixtures.LifecycleTests.player
    login = fixtures.LifecycleTests.login

    def pregnant(self):
        game.run("UPDATE consorts SET health=80,pregnant_since=10,pregnancy_started_ts=100000,prenatal='{}',silver=2000 WHERE id=?", (self.atk,))

    def deliver(self, child_death=0, crisis=0, twins=0):
        self.pregnant()
        with patch.object(game.time,'time',return_value=PRETERM_T), patch.object(game,'preterm_chance',return_value=1), patch.object(game,'preterm_child_death_chance',return_value=child_death), patch.object(game,'preterm_crisis_chance',return_value=crisis), patch.object(game,'TWIN_CHANCE',twins), patch.object(game.random,'random',return_value=0):
            game.resolve_births(10, False)

    def test_survivor_has_permanently_lower_health_cap(self):
        self.deliver()
        h = game.q('SELECT * FROM heirs WHERE mother_id=?', (self.atk,), one=True)
        self.assertEqual(h['premature'], 1)
        self.assertTrue(90 <= h['health_max'] <= 95)
        self.assertEqual(h['health_max'], 100 - h['preterm_health_loss'])
        game.run('UPDATE heirs SET health=100 WHERE id=?', (h['id'],))
        self.assertEqual(game.get_heir(h['id'])['health'], h['health_max'])

    def test_mother_rescue_cost_and_permanent_stacking_cap(self):
        self.deliver(crisis=1)
        for expected in (85,70):
            with patch.object(game.time,'time',return_value=164801):
                if expected == 70: game.enter_birth_crisis(self.atk)
                before = game.get_consort(self.atk)['silver']
                self.login(self.atk)
                self.client.post('/birth/rescue')
                c = game.get_consort(self.atk)
                self.assertEqual(c['silver'], before - 500)
                self.assertEqual((c['health_max'],c['birth_crisis']), (expected,0))
                game.add_stat(self.atk,'health',100)
                self.assertEqual(game.get_consort(self.atk)['health'],expected)
                self.client.post('/birth/rescue')
                self.assertEqual(game.get_consort(self.atk)['silver'],before-500)

    def test_regular_healing_cannot_replace_expensive_rescue(self):
        self.deliver(crisis=1)
        game.add_stat(self.atk,'health',100)
        self.assertLessEqual(game.get_consort(self.atk)['health'],10)
        game.run('UPDATE consorts SET silver=499 WHERE id=?', (self.atk,))
        with patch.object(game.time,'time',return_value=164801):
            self.login(self.atk)
            self.client.post('/birth/rescue')
        self.assertEqual(game.get_consort(self.atk)['birth_crisis'],1)
        with patch.object(game.time,'time',return_value=PRETERM_T+43200): game.dying_tick()
        self.assertEqual(game.get_consort(self.atk)['status'],'dead')

    def test_child_death_record_without_live_heir_or_naming_reward(self):
        self.deliver(child_death=1)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs WHERE mother_id=?', (self.atk,),one=True)['n'],0)
        self.assertEqual(game.birth_count(self.atk),1)
        self.assertEqual(game.get_consort(self.atk)['pregnant_since'],0)
        self.assertTrue(game.q('SELECT 1 FROM birth_losses WHERE mother_id=?',(self.atk,),one=True))

    def test_no_early_check_before_three_quarters_and_only_once_per_slot(self):
        self.pregnant()
        with patch.object(game.time,'time',return_value=PRETERM_T - 1), patch.object(game,'preterm_chance') as probability:
            game.resolve_births(10,False); probability.assert_not_called()
        with patch.object(game.time,'time',return_value=PRETERM_T), patch.object(game,'preterm_chance',return_value=0) as probability:
            game.resolve_births(10,False); game.resolve_births(10,False)
            self.assertEqual(probability.call_count,1)

    def test_twins_can_have_one_survivor(self):
        self.pregnant()
        with patch.object(game.time,'time',return_value=PRETERM_T), patch.object(game,'preterm_chance',return_value=1), patch.object(game,'preterm_crisis_chance',return_value=0), patch.object(game,'preterm_child_death_chance',side_effect=[1,0]), patch.object(game,'TWIN_CHANCE',1), patch.object(game.random,'random',return_value=0):
            game.resolve_births(10,False)
        self.assertEqual(game.q('SELECT COUNT(*) n FROM heirs WHERE mother_id=?',(self.atk,),one=True)['n'],1)
        self.assertEqual(game.birth_count(self.atk),2)
