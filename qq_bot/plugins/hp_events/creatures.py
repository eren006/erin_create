"""照料神奇生物：三年级前两天(第9~10天)限定的小游戏，呼应三年级新解锁的保护神奇动物学。

玩法跟抓地精是同一个模子——冷却制、不占体力/每日次数，两天的窗口本身就是天然上限。
每次照料先独立判定一次5%的"珍稀宠物"彩蛋（不管这次照料本身成不成功都有机会撞上），
每人一辈子最多中一次，中了直接进背包，自己发「/领养宠物」正式收养。
常规照料再按稀有度判定遇到哪种生物、给多少加隆。活动结束次日（AWARD_DAY）自动结算，
当时驯养成功总数第一的人拿"海格的得意门生"称号+纪念手册——纯个人排名，不结算学院分。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage

from . import storage

storage.init_db()

CREATURE_START_DAY = 9
CREATURE_END_DAY = 10
AWARD_DAY = 11  # 活动结束后第二天，结算冠军

COOLDOWN_SECONDS = 60 * 60  # 1小时冷却
TAME_CHANCE = 0.7

# (生物名, 权重, 加隆区间)——跟下面RARE_PET_KEYS的限定宠物名字故意错开，
# 免得玩家分不清"今天遇到的生物"和"抽中的稀有宠物"是不是一回事
CREATURE_TIERS = (
    ("康沃尔郡小精灵", 45, (2, 5)),
    ("毛球怪", 30, (5, 10)),
    ("鹰头马身有翼兽", 18, (10, 18)),
    ("夜骐", 7, (20, 30)),
)

FAIL_LINES = (
    "那只生物警惕地盯着你，一转身就窜进了灌木丛，任你怎么叫都不肯出来。",
    "你刚靠近，它就炸了毛，冲你甩了一串警告的吼声，吓得你退了两步。",
    "投喂的时候手一抖，食物撒了一地，它嫌弃地看了你一眼就走了。",
    "它对你毫无兴趣，径自摆摆尾巴走开了，仿佛在说“今天不想理你”。",
    "你按课本上的姿势慢慢靠近，它却完全不按套路出牌，转身就跑。",
)

SUCCESS_LINES = (
    "你耐着性子哄了好一会儿，它终于放松下来，蹭了蹭你的手心。",
    "照着课本上教的姿势慢慢靠近，它意外地很配合，安安静静让你照顾完。",
    "一开始它还有点抗拒，喂了点吃的之后立刻乖了下来。",
    "你小心翼翼地清理了它身上的小伤口，它居然舒服地眯起了眼睛。",
    "它绕着你转了两圈，像是在确认你没有恶意，然后才安心让你靠近。",
)

# 独立于常规驯养结果之外的小概率彩蛋——不管这次照料成不成功都有机会撞上。
# 三只都是对角巷买不到的限定宠物（shop_catalog里category="限定宠物"），
# 中了直接进背包，自己发「/领养宠物」正式收养。
RARE_PET_CHANCE = 0.05
RARE_PET_KEYS = ("pet_niffler", "pet_unicorn_foal", "pet_bowtruckle")
RARE_HIT_LINE = (
    "就在你专心照顾手边这只生物的时候，草丛深处忽然探出一颗脑袋——"
    "一只谁都没见过的{pet_name}歪着头打量了你很久，竟破天荒地跟你走了！"
)

CHAMPION_TITLE = "hagrid_favorite"
CHAMPION_TITLE_NAME = "海格的得意门生"
TROPHY_ITEM_KEY = "trophy_creature_keeper"


class CreatureError(Exception):
    pass


def is_open(day: int) -> bool:
    return CREATURE_START_DAY <= day <= CREATURE_END_DAY


def _require_player(uid: str) -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise CreatureError("你还没有分院，先发「/入学」完成入学测试。")


def get_cooldown_remaining(uid: str) -> int:
    """还要等多少秒才能再照料一次，0表示现在就能照料。"""
    last = storage.get_creature_last_tend(uid)
    if not last:
        return 0
    elapsed = core_storage.now() - last
    return max(0, COOLDOWN_SECONDS - elapsed)


def _roll_rare_pet(uid: str) -> dict | None:
    if storage.has_won_rare_creature(uid):
        return None
    if random.random() >= RARE_PET_CHANCE:
        return None

    from plugins.hp_school import shop_catalog
    from plugins.hp_school import storage as school_storage

    pet_key = random.choice(RARE_PET_KEYS)
    item = shop_catalog.find(pet_key)
    pet_name = item[1] if item else pet_key
    school_storage.add_item(uid, pet_key, 1)
    storage.record_rare_creature_win(uid, pet_key)
    return {"key": pet_key, "name": pet_name, "line": RARE_HIT_LINE.format(pet_name=pet_name)}


def tend(uid: str) -> dict:
    _require_player(uid)
    day = core_storage.get_current_day() or 1
    if not is_open(day):
        raise CreatureError(f"照料神奇生物只在第{CREATURE_START_DAY}~{CREATURE_END_DAY}天开放，现在不是时候。")

    remaining = get_cooldown_remaining(uid)
    if remaining > 0:
        wait_min = remaining // 60 + 1
        raise CreatureError(f"生物们还没休息够，约{wait_min}分钟后可以再照料一次。")

    storage.set_creature_last_tend(uid, core_storage.now())
    storage.increment_creature_daily(uid, day)

    rare_pet = _roll_rare_pet(uid)

    if random.random() >= TAME_CHANCE:
        return {"success": False, "line": random.choice(FAIL_LINES), "rare_pet": rare_pet}

    tier_name, _, (low, high) = random.choices(
        CREATURE_TIERS, weights=[t[1] for t in CREATURE_TIERS], k=1
    )[0]
    reward = random.randint(low, high)
    core_storage.add_galleons(uid, reward)
    total = storage.increment_creature_total(uid)

    return {
        "success": True,
        "line": random.choice(SUCCESS_LINES),
        "tier": tier_name,
        "reward": reward,
        "total": total,
        "rare_pet": rare_pet,
    }


def leaderboard(limit: int = 20) -> list[dict]:
    return storage.creature_leaderboard(limit)


def award_champion() -> dict | None:
    """活动结束后结算冠军，只应该在AWARD_DAY触发一次；已经发过就跳过。
    纯个人排名——驯养成功总数第一颁称号+纪念手册，不结算学院分。
    """
    from plugins.hp_school import storage as school_storage

    top = storage.creature_leaderboard(limit=1)
    if not top or top[0]["total"] <= 0:
        return None
    winner_uid = top[0]["uid"]
    if core_storage.has_title(winner_uid, CHAMPION_TITLE):
        return None
    core_storage.unlock_title(winner_uid, CHAMPION_TITLE)
    school_storage.add_item(winner_uid, TROPHY_ITEM_KEY, 1)

    return {"uid": winner_uid, "total": top[0]["total"]}
