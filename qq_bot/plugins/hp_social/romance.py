"""恋爱系统：送礼物涨好感、确立关系、约会（仅限情侣）、分手、插足。

好感度是单向的——A对B和B对A是两条独立记录，允许单相思。
确立关系要求双向好感度都达标，且双方都是单身；一次只能有一个对象。
性别不做任何限制，男女都可以在一起。
"""

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_school import shop_catalog
from plugins.hp_school import storage as school_storage

from . import storage

storage.init_db()

AFFECTION_MAX = 200
CONFESS_THRESHOLD = 50  # 双向好感度都达到这个数才能确立关系

DATE_STAMINA_COST = 5
DATE_DAILY_LIMIT = 2
DATE_AFFECTION_GAIN = 8
DATE_SUBJECT_EXP = 3

FLIRT_STAMINA_COST = 2
FLIRT_AFFECTION_GAIN = 4

INTERFERE_STAMINA_COST = 10
INTERFERE_DAILY_LIMIT = 1
INTERFERE_SUCCESS_BASE = 0.35
INTERFERE_SELF_GAIN = 20
INTERFERE_COUPLE_LOSS = 25
INTERFERE_FAIL_SELF_LOSS = 10

DATE_ACTIVITIES = {
    "霍格莫德": "charms",
    "图书馆": "transfiguration",
    "黑湖边": "herbology",
    "天文塔": "potions",
    "魁地奇球场": "defence",
}


class RomanceError(Exception):
    pass


def _require_player(uid: str, who: str = "你"):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise RomanceError(f"{who}还没有分院，先发「/入学」完成入学测试。")
    return player


def send_gift(uid: str, item_input: str, target_uid: str) -> dict:
    _require_player(uid)
    if target_uid == uid:
        raise RomanceError("不能送给自己。")
    _require_player(target_uid, "对方")

    item = shop_catalog.find(item_input.strip())
    if not item or item[2] != "礼物":
        raise RomanceError("这不是礼物，去「/对角巷 礼物」看看有什么可以送的。")
    key, name, _, _, _, effect = item

    if not school_storage.remove_item(uid, key, 1):
        raise RomanceError(f"背包里没有「{name}」，先去「/对角巷购买 {name}」。")

    gain = effect["affection"]
    new_value = storage.add_affection(target_uid, uid, gain, AFFECTION_MAX)
    return {"name": name, "gain": gain, "new_value": new_value, "target": target_uid}


FLIRT_LINES = [
    "假装不经意地路过，又假装不经意地回头看了一眼。",
    "在走廊上叫住对方，说了句没什么营养的话，然后就跑了。",
    "把自己那份甜点推了过去，说「我吃不下了」。",
    "上课时隔着半个教室对上视线，先移开目光的是你。",
    "帮对方拎了一路的书，全程没说几句话。",
    "在图书馆同一张桌子坐了一下午，谁都没提这事。",
]


def flirt(uid: str, target_uid: str) -> dict:
    """调情：对同一个人每天一次，涨一点好感度。对每个人各自计次，
    不是每天总共只能调一次——想广撒网也行，就是体力值扛不扛得住的问题。"""
    _require_player(uid)
    if target_uid == uid:
        raise RomanceError("自己跟自己调情，这就有点那什么了。")
    _require_player(target_uid, "对方")

    # 先查体力再记次数，否则体力不够时会白白吃掉当天的调情机会
    player = core_storage.sync_stamina(uid)
    if player["stamina"] < FLIRT_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise RomanceError(
            f"你累得连一句像样的话都组织不出来了。当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"调情需要{FLIRT_STAMINA_COST}点；约{wait_min}分钟后会恢复一轮。"
        )

    day = core_storage.get_current_day() or 1
    if not storage.try_log_flirt(uid, target_uid, day):
        raise RomanceError("今天已经对TA调过情了，明天再来吧，太频繁反而掉价。")

    core_storage.spend_stamina(uid, FLIRT_STAMINA_COST)
    new_value = storage.add_affection(target_uid, uid, FLIRT_AFFECTION_GAIN, AFFECTION_MAX)
    return {
        "target": target_uid,
        "line": random.choice(FLIRT_LINES),
        "gain": FLIRT_AFFECTION_GAIN,
        "new_value": new_value,
    }


def confess(uid: str, target_uid: str) -> dict:
    """确立关系：双向好感度都要达标，双方都必须单身。"""
    _require_player(uid)
    if target_uid == uid:
        raise RomanceError("……你还好吗？")
    _require_player(target_uid, "对方")

    if storage.get_partner(uid):
        raise RomanceError("你已经有对象了，先「/分手」再说。")
    if storage.get_partner(target_uid):
        raise RomanceError("对方已经有对象了。要么放弃，要么试试「/插足 对方QQ号」。")

    mine = storage.get_affection(uid, target_uid)
    theirs = storage.get_affection(target_uid, uid)
    if mine < CONFESS_THRESHOLD or theirs < CONFESS_THRESHOLD:
        raise RomanceError(
            f"感情还不够。你对TA {mine}/{CONFESS_THRESHOLD}，TA对你 {theirs}/{CONFESS_THRESHOLD}，"
            "双向都达标才能在一起。"
        )

    storage.create_relationship(uid, target_uid)
    return {"target": target_uid, "mine": mine, "theirs": theirs}


def break_up(uid: str) -> dict:
    _require_player(uid)
    partner = storage.get_partner(uid)
    if not partner:
        raise RomanceError("你现在没有对象。")
    storage.delete_relationship(uid, partner)
    # 分手后双方好感度各腰斩，留一点余地——真要复合还得重新攒
    new_mine = storage.add_affection(uid, partner, -storage.get_affection(uid, partner) // 2, AFFECTION_MAX)
    new_theirs = storage.add_affection(partner, uid, -storage.get_affection(partner, uid) // 2, AFFECTION_MAX)
    return {"partner": partner, "mine": new_mine, "theirs": new_theirs}


def go_on_date(uid: str, activity: str) -> dict:
    """约会只有情侣能约，直接和自己的对象去，不用指定对象。"""
    _require_player(uid)
    partner = storage.get_partner(uid)
    if not partner:
        raise RomanceError("约会是情侣之间的事。先送礼物攒好感，双方都到50就能「/确立关系 对方QQ号」。")

    if activity not in DATE_ACTIVITIES:
        raise RomanceError(f"没有这个去处。可选：{'、'.join(DATE_ACTIVITIES)}")

    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["dates"] >= DATE_DAILY_LIMIT:
        raise RomanceError(f"今天已经约会{DATE_DAILY_LIMIT}次了，明天再说。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < DATE_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise RomanceError(
            f"以你现在{player['stamina']}/{core_storage.STAMINA_MAX}的体力，恐怕会在约会途中睡着；"
            f"约会需要{DATE_STAMINA_COST}点。约{wait_min}分钟后会恢复一轮。"
        )

    core_storage.spend_stamina(uid, DATE_STAMINA_COST)
    storage.increment_daily(uid, day, "dates")

    subject_key = DATE_ACTIVITIES[activity]
    mine = storage.add_affection(uid, partner, DATE_AFFECTION_GAIN, AFFECTION_MAX)
    theirs = storage.add_affection(partner, uid, DATE_AFFECTION_GAIN, AFFECTION_MAX)
    core_storage.add_subject_exp(uid, subject_key, DATE_SUBJECT_EXP)
    core_storage.add_subject_exp(partner, subject_key, DATE_SUBJECT_EXP)

    return {
        "partner": partner,
        "activity": activity,
        "affection_gain": DATE_AFFECTION_GAIN,
        "mine": mine,
        "theirs": theirs,
        "subject_exp": DATE_SUBJECT_EXP,
        "today_count": daily["dates"] + 1,
        "daily_limit": DATE_DAILY_LIMIT,
    }


def interfere(uid: str, target_uid: str) -> dict:
    """插足：撬别人的墙角。成功率跟"目标对你的好感 vs 目标对现任的好感"有关，
    成功则拆散他们、目标对你好感大涨；失败则目标对你反感，好感倒扣。"""
    _require_player(uid)
    if target_uid == uid:
        raise RomanceError("……你在干什么？")
    _require_player(target_uid, "对方")

    if storage.get_partner(uid):
        raise RomanceError("你自己都有对象了，先「/分手」。")
    rival = storage.get_partner(target_uid)
    if not rival:
        raise RomanceError("对方是单身，不用插足，直接送礼物追就行了。")

    day = core_storage.get_current_day() or 1
    daily = storage.get_daily(uid, day)
    if daily["interferes"] >= INTERFERE_DAILY_LIMIT:
        raise RomanceError(f"今天已经插足过{INTERFERE_DAILY_LIMIT}次了，明天再来。")

    player = core_storage.sync_stamina(uid)
    if player["stamina"] < INTERFERE_STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise RomanceError(
            f"搅乱别人的感情可不是轻松活。当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"至少需要{INTERFERE_STAMINA_COST}点才有精力谋划；约{wait_min}分钟后恢复一轮。"
        )

    core_storage.spend_stamina(uid, INTERFERE_STAMINA_COST)
    storage.increment_daily(uid, day, "interferes")

    my_favour = storage.get_affection(target_uid, uid)
    rival_favour = storage.get_affection(target_uid, rival)
    total = my_favour + rival_favour
    edge = (my_favour / total) if total > 0 else 0.5
    chance = min(0.75, INTERFERE_SUCCESS_BASE * edge * 2)
    success = random.random() < chance

    if success:
        storage.delete_relationship(target_uid, rival)
        storage.add_affection(target_uid, rival, -INTERFERE_COUPLE_LOSS, AFFECTION_MAX)
        storage.add_affection(rival, target_uid, -INTERFERE_COUPLE_LOSS, AFFECTION_MAX)
        new_mine = storage.add_affection(target_uid, uid, INTERFERE_SELF_GAIN, AFFECTION_MAX)
    else:
        new_mine = storage.add_affection(target_uid, uid, -INTERFERE_FAIL_SELF_LOSS, AFFECTION_MAX)

    return {
        "success": success,
        "chance": chance,
        "target": target_uid,
        "rival": rival,
        "target_favour_to_me": new_mine,
    }


def my_romance(uid: str) -> dict:
    _require_player(uid)
    partner = storage.get_partner(uid)
    liked_by_me = storage.list_affection_from(uid)
    likes_me = storage.list_affection_to(uid)
    return {
        "partner": partner,
        "liked_by_me": [(r["to_uid"], r["value"]) for r in liked_by_me],
        "likes_me": [(r["from_uid"], r["value"]) for r in likes_me],
    }
