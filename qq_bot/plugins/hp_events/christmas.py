"""圣诞节：舞会 + 圣诞树。

每个学年的最后一天是圣诞节（Day 4/8/12/16/21/25/30）——正好和学年结业撞在一起，
"考完试就是圣诞舞会"这个节奏比另找一天更顺。

舞会有现实时间窗口（默认当天 20:00–23:00），窗口之外只能做准备工作：
邀舞伴、设计礼服。窗口一开才能出席。
圣诞树是全服共同进度，挂装饰不花体力但有冷却，攒满之后所有参与过的人一起领礼物。
"""

from __future__ import annotations

import random
import time

from plugins.hp_core import storage as core_storage

from . import grading, storage

storage.init_christmas()

BALL_START_HOUR = 20
BALL_END_HOUR = 23

TREE_ORNAMENTS = [
    ("星星", "一颗歪歪扭扭但很努力的锡纸星星"),
    ("彩球", "会自己变换颜色的玻璃彩球"),
    ("糖果拐杖", "薄荷味的，据说有人偷咬过一口"),
    ("小雪人", "施了咒的雪人，会对路过的人挥手"),
    ("金铃铛", "碰一下会响半分钟"),
    ("蜡烛", "永远不会烧完，也不会点着树"),
    ("槲寄生", "挂高一点，不然底下总有人排队"),
    ("猫头鹰挂饰", "很像你的猫头鹰，就是不会叫"),
]
ORNAMENTS_BY_NAME = {name: (name, desc) for name, desc in TREE_ORNAMENTS}

TREE_HANG_POINTS_MIN = 2  # 挂哪种装饰不影响点数，每次挂上去现掷一个2-5的随机点数
TREE_HANG_POINTS_MAX = 5

TREE_GOAL_PER_PLAYER = 25  # 目标 = 全校人数 × 这个数，人多目标才高
TREE_GOAL_MIN = 60
HANG_COOLDOWN_SECONDS = 30 * 60
TREE_REWARD_GALLEONS = 40

# 树点亮的瞬间额外给贡献前三名颁奖，跟人人都能领的参与礼（TREE_REWARD_GALLEONS）分开算，
# 奖励重复挂饰的人，不是随便挂一个就跟拼手速的人拿一样多。
TREE_RANK_REWARDS = [
    ("圣诞树装饰冠军", 150),
    ("圣诞树装饰亚军", 90),
    ("圣诞树装饰季军", 50),
]
TREE_RANK_TITLE_PREFIX = "tree_decorator_rank"

ROBE_COLORS = ["午夜蓝", "祖母绿", "酒红", "银白", "墨黑", "香槟金", "淡紫", "雪青", "赭石", "孔雀蓝"]
ROBE_STYLES = ["长摆礼袍", "立领礼服", "束腰长裙", "双排扣礼服", "斗篷式礼袍", "简约直筒", "缀满褶皱的裙撑", "剪裁利落的三件套"]
ROBE_ACCESSORIES = ["月光石胸针", "家传怀表", "一枝白山茶", "银线绣的袖口", "会转的星盘吊坠", "母亲留下的丝质围巾", "什么都不戴", "一顶歪戴的礼帽"]

BALL_TITLE_BEST_DRESSED = "舞会之星"


class ChristmasError(Exception):
    pass


# ======================== 时间 ========================


def christmas_days() -> set[int]:
    return set(grading.GRADE_END_DAY.values())


def is_christmas(day: int) -> bool:
    return day in christmas_days()


def next_christmas(day: int) -> int | None:
    later = sorted(d for d in christmas_days() if d >= day)
    return later[0] if later else None


def ball_window_state(now_ts: float | None = None) -> dict:
    """舞会窗口状态。窗口按现实时间的小时算，圣诞节当天 20:00–23:00。"""
    day = core_storage.get_current_day() or 1
    hour = time.localtime(now_ts or time.time()).tm_hour
    today_is_christmas = is_christmas(day)
    is_open = today_is_christmas and BALL_START_HOUR <= hour < BALL_END_HOUR
    return {
        "day": day,
        "is_christmas": today_is_christmas,
        "is_open": is_open,
        "hour": hour,
        "start_hour": BALL_START_HOUR,
        "end_hour": BALL_END_HOUR,
        "next_christmas": next_christmas(day),
    }


def _require_player(uid: str, who: str = "你"):
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise ChristmasError(f"{who}还没有完成入学手续。")
    return player


# ======================== 礼服 ========================


def design_robe(uid: str, color: str, style: str, accessory: str) -> dict:
    _require_player(uid)
    for value, pool, label in (
        (color, ROBE_COLORS, "颜色"),
        (style, ROBE_STYLES, "款式"),
        (accessory, ROBE_ACCESSORIES, "配饰"),
    ):
        if value not in pool:
            raise ChristmasError(f"没有这个{label}。可选：{'、'.join(pool)}")

    year = _year_of(core_storage.get_current_day() or 1)
    storage.save_robe(uid, year, color, style, accessory)
    return {
        "color": color,
        "style": style,
        "accessory": accessory,
        "描述": describe_robe(color, style, accessory),
    }


def describe_robe(color: str, style: str, accessory: str) -> str:
    if accessory == "什么都不戴":
        return f"一身{color}的{style}，没有任何多余的装饰。"
    return f"一身{color}的{style}，配{accessory}。"


def _year_of(day: int) -> int:
    for grade, end in sorted(grading.GRADE_END_DAY.items()):
        if day <= end:
            return grade
    return 7


def get_robe(uid: str) -> dict | None:
    day = core_storage.get_current_day() or 1
    row = storage.get_robe(uid, _year_of(day))
    if not row:
        return None
    return {
        "color": row["color"],
        "style": row["style"],
        "accessory": row["accessory"],
        "描述": describe_robe(row["color"], row["style"], row["accessory"]),
    }


# ======================== 舞伴 ========================


def invite_partner(uid: str, target_uid: str) -> dict:
    _require_player(uid)
    if target_uid == uid:
        raise ChristmasError("一个人去也没问题，但不用给自己发邀请。")
    _require_player(target_uid, "对方")

    day = core_storage.get_current_day() or 1
    if not is_christmas(day):
        nxt = next_christmas(day)
        raise ChristmasError(
            f"今天不是圣诞节，舞会还没到。{'下一次在第' + str(nxt) + '天。' if nxt else ''}"
        )
    year = _year_of(day)
    if storage.get_ball_partner(uid, year):
        raise ChristmasError("你已经有舞伴了。")
    if storage.get_ball_partner(target_uid, year):
        raise ChristmasError("对方已经答应别人了。")
    if storage.get_ball_invite_from(uid, year):
        raise ChristmasError("你已经发出过一份邀请了，等对方回应，或者先撤回。")

    storage.create_ball_invite(uid, target_uid, year)
    return {"target": target_uid}


def withdraw_invite(uid: str) -> dict:
    day = core_storage.get_current_day() or 1
    row = storage.get_ball_invite_from(uid, _year_of(day))
    if not row:
        raise ChristmasError("你没有待回应的邀请。")
    storage.delete_ball_invite(uid, _year_of(day))
    return {"target": row["target_uid"]}


def respond_invite(uid: str, inviter_uid: str, accept: bool) -> dict:
    day = core_storage.get_current_day() or 1
    year = _year_of(day)
    row = storage.get_ball_invite(inviter_uid, uid, year)
    if not row:
        raise ChristmasError("没有这个人发给你的邀请。")
    storage.delete_ball_invite(inviter_uid, year)
    if not accept:
        return {"accepted": False, "inviter": inviter_uid}

    if storage.get_ball_partner(uid, year) or storage.get_ball_partner(inviter_uid, year):
        raise ChristmasError("有一方已经有舞伴了，这份邀请失效了。")
    storage.set_ball_partner(inviter_uid, uid, year)
    return {"accepted": True, "inviter": inviter_uid}


def get_partner(uid: str) -> str | None:
    day = core_storage.get_current_day() or 1
    return storage.get_ball_partner(uid, _year_of(day))


# ======================== 出席 ========================

ATTEND_AFFECTION = 25
ATTEND_HOUSE_POINTS = 2


def attend(uid: str) -> dict:
    _require_player(uid)
    state = ball_window_state()
    if not state["is_christmas"]:
        nxt = state["next_christmas"]
        raise ChristmasError(
            f"今天不是圣诞节。{'下一场舞会在第' + str(nxt) + '天。' if nxt else '今年的舞会都办完了。'}"
        )
    if not state["is_open"]:
        raise ChristmasError(
            f"舞会还没开场——今晚 {BALL_START_HOUR}:00 到 {BALL_END_HOUR}:00 开放，"
            f"现在是 {state['hour']}:00。先去挑挑礼服、约个舞伴。"
        )

    year = _year_of(state["day"])
    if storage.has_attended_ball(uid, year):
        raise ChristmasError("你已经在舞会上了，不用再进一次。")

    robe = get_robe(uid)
    partner = storage.get_ball_partner(uid, year)
    storage.mark_ball_attended(uid, year, bool(robe))

    player = core_storage.get_player(uid)
    core_storage.add_house_points(player["house"], ATTEND_HOUSE_POINTS, uid)

    result = {
        "robe": robe,
        "partner": partner,
        "house_points": ATTEND_HOUSE_POINTS,
        "partner_attended": False,
        "affection": 0,
    }
    if partner and storage.has_attended_ball(partner, year):
        from plugins.hp_social import romance
        from plugins.hp_social import storage as social_storage

        social_storage.add_affection(partner, uid, ATTEND_AFFECTION, romance.AFFECTION_MAX)
        social_storage.add_affection(uid, partner, ATTEND_AFFECTION, romance.AFFECTION_MAX)
        result["partner_attended"] = True
        result["affection"] = ATTEND_AFFECTION
    return result


def pick_best_dressed(year: int) -> dict | None:
    """舞会散场时评最佳着装：在出席者里按礼服完整度加权随机。"""
    attendees = storage.list_ball_attendees(year)
    dressed = [row for row in attendees if row["has_robe"]]
    if not dressed:
        return None
    winner = random.choice(dressed)
    core_storage.unlock_title(winner["uid"], f"ball_best_dressed_y{year}")
    robe = storage.get_robe(winner["uid"], year)
    return {
        "uid": winner["uid"],
        "robe": describe_robe(robe["color"], robe["style"], robe["accessory"]) if robe else "",
        "title": BALL_TITLE_BEST_DRESSED,
    }


# ======================== 圣诞树 ========================


def tree_goal(year: int | None = None) -> int:
    """目标在第一次有人挂装饰时定死。之后再有人入学也不会改变，
    否则已经装满的树会因为新生加入而退回未完成状态。"""
    if year is None:
        year = _year_of(core_storage.get_current_day() or 1)
    frozen = storage.get_frozen_tree_goal(year)
    if frozen is not None:
        return frozen
    people = len(core_storage.list_sorted_uids())
    return max(TREE_GOAL_MIN, people * TREE_GOAL_PER_PLAYER)


def tree_state() -> dict:
    day = core_storage.get_current_day() or 1
    year = _year_of(day)
    progress = storage.get_tree_progress(year)
    goal = tree_goal(year)
    return {
        "year": year,
        "is_christmas": is_christmas(day),
        "progress": progress,
        "goal": goal,
        "done": progress >= goal,
        "contributors": storage.count_tree_contributors(year),
        "recent": storage.recent_tree_hangs(year, 8),
    }


def _award_tree_top_contributors(year: int) -> list[dict]:
    """树点亮那一刻结算一次贡献榜前三名，颁一次性称号+加隆奖励。"""
    top = storage.tree_contributor_leaderboard(year, len(TREE_RANK_REWARDS))
    awards = []
    for rank, row in enumerate(top):
        title_name, galleons = TREE_RANK_REWARDS[rank]
        core_storage.add_galleons(row["uid"], galleons)
        core_storage.unlock_title(row["uid"], f"{TREE_RANK_TITLE_PREFIX}{rank + 1}_y{year}")
        awards.append(
            {
                "uid": row["uid"],
                "rank": rank + 1,
                "title": title_name,
                "galleons": galleons,
                "points": row["total"],
            }
        )
    return awards


def tree_contributor_leaderboard(year: int | None = None, limit: int = 10) -> list[dict]:
    if year is None:
        year = _year_of(core_storage.get_current_day() or 1)
    return [dict(row) for row in storage.tree_contributor_leaderboard(year, limit)]


def hang(uid: str, ornament_input: str) -> dict:
    _require_player(uid)
    day = core_storage.get_current_day() or 1
    if not is_christmas(day):
        nxt = next_christmas(day)
        raise ChristmasError(
            f"礼堂里还没立起圣诞树。{'下一次在第' + str(nxt) + '天。' if nxt else ''}"
        )

    item = ORNAMENTS_BY_NAME.get(ornament_input.strip())
    if not item:
        raise ChristmasError(
            "没有这种装饰。可挂的：" + "、".join(name for name, _ in TREE_ORNAMENTS)
        )
    name, desc = item
    points = random.randint(TREE_HANG_POINTS_MIN, TREE_HANG_POINTS_MAX)

    year = _year_of(day)
    last = storage.last_tree_hang_at(uid, year)
    now = core_storage.now()
    if last and now - last < HANG_COOLDOWN_SECONDS:
        wait = (HANG_COOLDOWN_SECONDS - (now - last)) // 60 + 1
        raise ChristmasError(f"你刚挂过一个，梯子还有人排队。{wait}分钟后再来。")

    goal = storage.freeze_tree_goal(
        year, max(TREE_GOAL_MIN, len(core_storage.list_sorted_uids()) * TREE_GOAL_PER_PLAYER)
    )
    was_done = storage.get_tree_progress(year) >= goal
    progress = storage.add_tree_hang(uid, year, name, points)
    just_completed = not was_done and progress >= goal
    rank_awards = _award_tree_top_contributors(year) if just_completed else []

    return {
        "ornament": name,
        "desc": desc,
        "points": points,
        "progress": progress,
        "goal": goal,
        "just_completed": just_completed,
        "rank_awards": rank_awards,
    }


def claim_tree_reward(uid: str) -> dict:
    _require_player(uid)
    day = core_storage.get_current_day() or 1
    year = _year_of(day)
    if storage.get_tree_progress(year) < tree_goal(year):
        raise ChristmasError("圣诞树还没装点完，大家再挂几个。")
    if not storage.has_hung_on_tree(uid, year):
        raise ChristmasError("这份礼物是给参与装点的人的——你一个装饰都没挂过。")
    if storage.has_claimed_tree_reward(uid, year):
        raise ChristmasError("你已经领过树下的礼物了。")

    storage.mark_tree_reward_claimed(uid, year)
    core_storage.add_galleons(uid, TREE_REWARD_GALLEONS)

    from plugins.hp_school import storage as school_storage

    gift_key = random.choice(["snack_honeydukes_assortment", "gift_music_box", "gift_quidditch_scarf"])
    school_storage.add_item(uid, gift_key, 1)
    from plugins.hp_school import shop_catalog

    gift = shop_catalog.find(gift_key)
    return {"galleons": TREE_REWARD_GALLEONS, "gift": gift[1] if gift else "一份礼物"}


def tree_reward_state(uid: str) -> dict:
    day = core_storage.get_current_day() or 1
    year = _year_of(day)
    return {
        "participated": storage.has_hung_on_tree(uid, year),
        "claimed": storage.has_claimed_tree_reward(uid, year),
    }


# ======================== 圣诞：大餐 ========================

FEAST_DISHES = [
    ("鼠尾草黄油烤火鸡", "整只火鸡抹了鼠尾草黄油进炉，皮脆得一碰就掉渣"),
    ("白兰地火焰圣诞布丁", "浇一勺白兰地点着端上桌，硬币就趁着火光被搅进了你那份"),
    ("培根卷迷你香肠串", "一口一个，培根卷得整整齐齐，走一圈能顺走一整盘"),
    ("鼠尾草洋葱面包屑填料", "塞在火鸡肚子里焖出来的，比火鸡本身还抢手"),
    ("约克郡布丁佐肉汁", "外壳鼓得像小碗，专门用来接肉汁"),
    ("蜜汁栗子抱子甘蓝", "苦涩的抱子甘蓝被蜂蜜栗子哄得服服帖帖"),
    ("蜂蜜烤防风草根", "长得像胡萝卜，甜得却像糖水煮过"),
    ("蔓越莓酱烤金土豆", "外壳烤得金黄咯吱响，酸甜酱是灵魂"),
    ("陈年车达奶酪拼盘", "配一小块饼干，吃完满手都是奶酪香"),
    ("雪莉酒英式圣诞松糕", "海绵蛋糕吸饱了雪莉酒，一层奶油一层果酱叠上去"),
    ("白兰地黄油百果馅派", "小小一个，馅料甜得发腻，配一勺白兰地黄油刚刚好"),
    ("肉桂热红酒炖梨", "整颗梨炖得酒香扑鼻，小口喝汤最烫嘴"),
    ("巧克力圣诞柴薪蛋糕", "做成木柴的样子，切开全是夹心巧克力"),
    ("肉豆蔻蛋奶热酒", "撒一层现磨肉豆蔻，喝一口浑身都暖"),
]
FEAST_PUDDING_DISH = "白兰地火焰圣诞布丁"
FEAST_EAT_COOLDOWN_SECONDS = 60 * 60
FEAST_SMALL_GIFT_CHANCE = 0.3
FEAST_SMALL_GIFT_POOL = [
    "snack_pumpkin_pasty", "snack_chocolate_frog", "snack_fizzing_whizzbee", "snack_liquorice_wand",
]
FEAST_PUDDING_GALLEONS = 100
FEAST_PUDDING_DRAW_HOUR = 22


def feast_state(uid: str) -> dict:
    day = core_storage.get_current_day() or 1
    year = _year_of(day)
    last = storage.last_feast_eat_at(uid, year)
    now = core_storage.now()
    cooldown_remaining = max(0, FEAST_EAT_COOLDOWN_SECONDS - (now - last)) if last else 0
    return {
        "is_christmas": is_christmas(day),
        "dishes": FEAST_DISHES,
        "eaten": storage.list_feast_dishes_eaten(uid, year),
        "cooldown_remaining": cooldown_remaining,
        "can_eat": is_christmas(day) and cooldown_remaining <= 0,
        "has_pudding_entry": storage.has_pudding_entry(uid, year),
    }


def eat_feast(uid: str, dish: str) -> dict:
    _require_player(uid)
    day = core_storage.get_current_day() or 1
    if not is_christmas(day):
        nxt = next_christmas(day)
        raise ChristmasError(
            f"今天没有圣诞大餐。{'下一次在第' + str(nxt) + '天。' if nxt else ''}"
        )
    valid_names = {name for name, _ in FEAST_DISHES}
    if dish not in valid_names:
        raise ChristmasError("菜单上没有这道菜。可选：" + "、".join(valid_names))

    year = _year_of(day)
    last = storage.last_feast_eat_at(uid, year)
    now = core_storage.now()
    if last and now - last < FEAST_EAT_COOLDOWN_SECONDS:
        wait = (FEAST_EAT_COOLDOWN_SECONDS - (now - last)) // 60 + 1
        raise ChristmasError(f"刚吃过一道菜，肚子还没消化。{wait}分钟后再来。")

    gift_key = ""
    if random.random() < FEAST_SMALL_GIFT_CHANCE:
        gift_key = random.choice(FEAST_SMALL_GIFT_POOL)
        from plugins.hp_school import storage as school_storage
        school_storage.add_item(uid, gift_key, 1)

    storage.add_feast_eat(uid, year, dish, gift_key)
    got_pudding_entry = False
    if dish == FEAST_PUDDING_DISH and not storage.has_pudding_entry(uid, year):
        storage.add_pudding_entry(uid, year)
        got_pudding_entry = True

    gift_name = ""
    if gift_key:
        from plugins.hp_school import shop_catalog
        item = shop_catalog.find(gift_key)
        gift_name = item[1] if item else ""

    return {
        "dish": dish,
        "gift": gift_name,
        "got_pudding_entry": got_pudding_entry,
        "variety": len(storage.list_feast_dishes_eaten(uid, year)),
    }


def feast_leaderboard(year: int | None = None, limit: int = 10) -> list[dict]:
    if year is None:
        year = _year_of(core_storage.get_current_day() or 1)
    return [dict(row) for row in storage.feast_variety_leaderboard(year, limit)]


def draw_pudding_winner(year: int) -> dict | None:
    """从今年吃过圣诞布丁的人里随机抽一个，赢 100 加隆——传统布丁藏硬币的老规矩。
    结果落库防重复抽，同一年只会抽一次。"""
    if storage.get_pudding_draw(year):
        return None
    entrants = storage.list_pudding_entrants(year)
    if not entrants:
        return None
    winner = random.choice(entrants)
    storage.record_pudding_draw(year, winner, FEAST_PUDDING_GALLEONS)
    core_storage.add_galleons(winner, FEAST_PUDDING_GALLEONS)
    return {"winner": winner, "galleons": FEAST_PUDDING_GALLEONS, "year": year}


def maybe_draw_pending_puddings() -> dict | None:
    """没有独立的定时任务进程，靠有人访问网页时顺手结算——
    圣诞节当天22点之后，或者那天已经过去了，就把还没抽的那年布丁奖抽掉。"""
    current_day = core_storage.get_current_day() or 1
    hour = time.localtime().tm_hour
    for day in sorted(christmas_days()):
        if day > current_day:
            break
        if day == current_day and hour < FEAST_PUDDING_DRAW_HOUR:
            continue
        year = _year_of(day)
        if storage.get_pudding_draw(year):
            continue
        result = draw_pudding_winner(year)
        if result:
            return result
    return None
