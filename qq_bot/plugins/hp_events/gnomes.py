"""抓地精：二年级前两天(第5~6天)限定的小游戏，德思礼/韦斯莱家除地精的经典桥段。

抓一次要等冷却，不用体力/每日次数这套——两天的时间窗口本身就是天然上限。
抓到之后再判定地精稀有度，稀有度越高加隆越多。活动结束第二天（AWARD_DAY）
自动结算，当时捕获总数排第一的人拿"地精之王"称号+绝版奖杯，此后不会再变
（后续再抓地精只是个人娱乐，不会抢到冠军的奖杯）。
"""

from __future__ import annotations

import random

from plugins.hp_core import storage as core_storage

from . import storage

storage.init_db()

GNOME_START_DAY = 5
GNOME_END_DAY = 6
AWARD_DAY = 7  # 活动结束后第二天，结算冠军

COOLDOWN_SECONDS = 20 * 60  # 20分钟冷却
CATCH_CHANCE = 0.7

# (名字, 权重, 加隆区间)
GNOME_TIERS = (
    ("普通地精", 60, (2, 5)),
    ("肥地精", 25, (5, 10)),
    ("金牙地精", 12, (10, 18)),
    ("传说金地精", 3, (25, 40)),
)

ESCAPE_LINES = (
    "地精从你手里一滑而出，边跑边喊着谁都听不懂的脏话。",
    "你刚抓住它的脚踝，它就一口咬在你手上，疼得你松了手。",
    "地精蜷成一团滚进了灌木丛，怎么找都找不到了。",
    "它一边尖叫一边朝你吐口水，你下意识松了手。",
    "地精比想象中滑溜得多，三两下就挣脱了。",
)

CATCH_LINES = (
    "你死死攥住它的脚踝，抡起来转了几圈，像韦斯莱家那样把它扔了出去。",
    "一把揪住它后颈的皮，任凭它挥舞小拳头也没能挣脱。",
    "地精咬牙切齿地骂着脏话，但还是被你稳稳提在了半空中。",
    "它试图装死蒙混过关，但你没上当，一把拎了起来。",
)

CHAMPION_TITLE = "gnome_king"
CHAMPION_TITLE_NAME = "地精之王"
TROPHY_ITEM_KEY = "trophy_gnome_king"
HOUSE_CHAMPION_HOUSE_POINTS = 15  # 全院捕获数第一的加分，参考魁地奇单场胜利的分值——两天限定活动只结算这一次


class GnomeError(Exception):
    pass


def is_open(day: int) -> bool:
    return GNOME_START_DAY <= day <= GNOME_END_DAY


def _require_player(uid: str) -> None:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise GnomeError("你还没有分院，先发「/入学」完成入学测试。")


def get_cooldown_remaining(uid: str) -> int:
    """还要等多少秒才能再抓一次，0表示现在就能抓。"""
    last = storage.get_gnome_last_catch(uid)
    if not last:
        return 0
    elapsed = core_storage.now() - last
    return max(0, COOLDOWN_SECONDS - elapsed)


def catch(uid: str) -> dict:
    _require_player(uid)
    day = core_storage.get_current_day() or 1
    if not is_open(day):
        raise GnomeError(f"抓地精只在第{GNOME_START_DAY}~{GNOME_END_DAY}天开放，现在不是时候。")

    remaining = get_cooldown_remaining(uid)
    if remaining > 0:
        wait_min = remaining // 60 + 1
        raise GnomeError(f"手还没缓过来，约{wait_min}分钟后可以再抓一次。")

    storage.set_gnome_last_catch(uid, core_storage.now())
    storage.increment_gnome_daily(uid, day)

    if random.random() >= CATCH_CHANCE:
        return {"success": False, "line": random.choice(ESCAPE_LINES)}

    tier_name, _, (low, high) = random.choices(
        GNOME_TIERS, weights=[t[1] for t in GNOME_TIERS], k=1
    )[0]
    reward = random.randint(low, high)
    core_storage.add_galleons(uid, reward)
    total = storage.increment_gnome_total(uid)

    return {
        "success": True,
        "line": random.choice(CATCH_LINES),
        "tier": tier_name,
        "reward": reward,
        "total": total,
    }


def leaderboard(limit: int = 20) -> list[dict]:
    return storage.gnome_leaderboard(limit)


def house_leaderboard() -> list[dict]:
    return storage.gnome_house_leaderboard()


def award_champion() -> dict | None:
    """活动结束后结算冠军，只应该在AWARD_DAY触发一次；已经发过就跳过。

    个人捕获数第一颁称号+奖杯；顺带给捕获总数第一的学院加院分
    （两者不一定是同一个人所在的学院，各自独立算排名）。
    """
    from plugins.hp_school import storage as school_storage

    top = storage.gnome_leaderboard(limit=1)
    if not top or top[0]["total"] <= 0:
        return None
    winner_uid = top[0]["uid"]
    if core_storage.has_title(winner_uid, CHAMPION_TITLE):
        return None
    core_storage.unlock_title(winner_uid, CHAMPION_TITLE)
    school_storage.add_item(winner_uid, TROPHY_ITEM_KEY, 1)

    house_board = storage.gnome_house_leaderboard()
    top_house = house_board[0] if house_board and house_board[0]["total"] > 0 else None
    if top_house:
        core_storage.add_house_points(top_house["house"], HOUSE_CHAMPION_HOUSE_POINTS)

    return {
        "uid": winner_uid,
        "total": top[0]["total"],
        "top_house": top_house["house"] if top_house else None,
        "top_house_total": top_house["total"] if top_house else 0,
        "house_points": HOUSE_CHAMPION_HOUSE_POINTS if top_house else 0,
    }
