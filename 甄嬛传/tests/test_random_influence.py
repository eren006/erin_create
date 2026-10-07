import unittest
from unittest.mock import patch
import test_lifecycle as fixtures

game=fixtures.game
class RandomInfluenceTests(unittest.TestCase):
    setUp=fixtures.LifecycleTests.setUp
    tearDown=fixtures.LifecycleTests.tearDown
    player=fixtures.LifecycleTests.player
    login=fixtures.LifecycleTests.login

    def entrant(self):
        uid=game.run('INSERT INTO users(username,password_hash,created_ts) VALUES(?,?,0)',('随机','x')).lastrowid
        with self.client.session_transaction() as sess:sess['uid']=uid
        return uid

    def test_roll_is_visible_before_family_and_fixed(self):
        uid=self.entrant()
        self.assertIn('先抽天资',self.client.get('/create').get_data(as_text=True))
        first=game.entry_stat_roll(uid)
        for k,(lo,hi) in game.RANDOM_STAT_RANGES.items():self.assertTrue(lo<=first[k]<=hi)
        with patch.object(game.random,'randint',return_value=999):self.client.get('/create')
        self.assertEqual(game.entry_stat_roll(uid),first)
        game.init_db();self.assertEqual(game.entry_stat_roll(uid),first)

    def test_stats_are_server_generated_and_modifiers_are_small(self):
        uid=self.entrant();roll=game.entry_stat_roll(uid)
        family=next(iter(game.FAMILIES));personality=next(iter(game.PERSONALITIES))
        game.create_family(uid,'壬',family)
        self.client.post('/create',data=dict(given='随机',age=20,personality=personality,appearance=999999))
        c=game.q('SELECT * FROM consorts WHERE user_id=?',(uid,),one=True)
        for key in roll:
            modifier=max(-10,min(10,game.FAMILIES[family]['mods'].get(key,0)+game.PERSONALITIES[personality]['mods'].get(key,0)))
            self.assertEqual(c[key],roll[key]+modifier)

    def test_influence_blocks_and_then_allows_promotion(self):
        game.run('UPDATE consorts SET influence=0,favor=500,virtue=80 WHERE id=?',(self.tgt,))
        with patch.object(game.random,'random',return_value=.999):game.settle_day()
        self.assertEqual(game.get_consort(self.tgt)['rank'],4)
        game.run('UPDATE consorts SET influence=25 WHERE id=?',(self.tgt,))
        with patch.object(game.random,'random',return_value=.999):game.settle_day()
        self.assertEqual(game.get_consort(self.tgt)['rank'],5)
        self.assertEqual(game.get_consort(self.tgt)['influence'],25-game.INFLUENCE_DECAY+game.PROMOTE_INFLUENCE_REWARD)      # 晋嫔额外奖励势力（当晚先衰减 1 点）

    def test_success_gains_once_per_victim_and_pending_plan(self):
        game.run('UPDATE consorts SET influence=0 WHERE id=?',(self.atk,))
        iid=game.run("INSERT INTO intrigues(attacker_id,target_id,method,day,created_ts) VALUES(?,?,'rumor',10,0)",(self.atk,self.tgt)).lastrowid
        it=game.q('SELECT * FROM intrigues WHERE id=?',(iid,),one=True)
        with patch.object(game.random,'random',return_value=0):game.resolve_intrigue(it)
        self.assertEqual(game.get_consort(self.atk)['influence'],5)
        with patch.object(game.random,'random',return_value=0):game.resolve_intrigue(game.q('SELECT * FROM intrigues WHERE id=?',(iid,),one=True))
        self.assertEqual(game.get_consort(self.atk)['influence'],5)
        game.gain_intrigue_influence(it)
        self.assertEqual(game.get_consort(self.atk)['influence'],5)

    def test_greeting_is_small_nonharmful_source(self):
        before=game.get_consort(self.atk)['influence']
        self.client.post('/act/greet');self.client.post('/act/greet')
        self.assertEqual(game.get_consort(self.atk)['influence'],before+1)
