import random
import time
from . import storage


# 竞选棋盘的位置描述，哈利波特风格
BOARD_POSITIONS = [
    "📍 起始位置：霍格沃茨城堡前的庭院",
    "🗝️ 第一关卡：已滑梯的守卫室",
    "📚 第二关卡：禁书区的阴暗走廊",
    "🧪 第三关卡：斯内普的魔药教室",
    "🐉 第四关卡：禁林的古老秘密",
    "✨ 第五关卡：霍格沃茨城堡的高塔",
    "👑 第六关卡：校长办公室的门前",
    "🏆 最终位置：成为一年级新人王！",
]

BOARD_WIDTH = len(BOARD_POSITIONS)


def roll_dice() -> tuple[int, int]:
    """掷两个骰子。"""
    die1 = random.randint(1, 6)
    die2 = random.randint(1, 6)
    return die1, die2


def can_duel(duel_data: dict) -> tuple[bool, str]:
    """检查是否可以进行竞选。"""
    last_duel_at = duel_data.get("last_duel_at", 0)
    now = int(time.time())
    cooldown_seconds = 3 * 3600  # 3小时

    if last_duel_at == 0:
        return True, ""

    elapsed = now - last_duel_at
    if elapsed < cooldown_seconds:
        remaining = cooldown_seconds - elapsed
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return False, f"⏳ 需要再等待 {hours}小时{minutes}分钟才能再次参赛"

    return True, ""


def perform_duel(uid: str) -> dict:
    """执行一次竞选对决。返回结果字典。"""
    duel_data = storage.init_or_get_freshman_duel(uid)

    can_go, cooldown_msg = can_duel(duel_data)
    if not can_go:
        return {"ok": False, "message": cooldown_msg}

    die1, die2 = roll_dice()
    steps = die1 + die2

    current_progress = duel_data.get("progress", 0)
    new_progress = min(current_progress + steps, BOARD_WIDTH - 1)
    points_gained = steps
    new_score = duel_data.get("score", 0) + points_gained

    storage.update_freshman_duel(uid, new_score, new_progress)

    # 构建结果消息
    current_position = BOARD_POSITIONS[current_progress]
    new_position = BOARD_POSITIONS[new_progress]

    message = f"🎲 竞选新人王骰子对决\n"
    message += f"骰子结果：{die1} + {die2} = {steps}\n"
    message += f"位置变化：{current_position}\n"
    message += f"→ {new_position}\n"
    message += f"获得积分：{points_gained}分\n"
    message += f"当前总分：{new_score}分"

    if new_progress == BOARD_WIDTH - 1:
        message += f"\n\n🏆 恭喜！你已经到达终点，成为一年级新人王候选人！"

    return {
        "ok": True,
        "message": message,
        "die1": die1,
        "die2": die2,
        "steps": steps,
        "old_progress": current_progress,
        "new_progress": new_progress,
        "score": new_score,
    }


def get_leaderboard() -> str:
    """获取排名信息。"""
    rankings = storage.get_freshman_duel_rankings()

    if not rankings:
        return "📊 竞选排名：暂无参赛者"

    message = "📊 一年级新人王竞选排名：\n"
    for i, entry in enumerate(rankings, 1):
        # 需要从hp_core的players表获取玩家名字
        from plugins.hp_core import storage as core_storage
        player = core_storage.get_player(entry["uid"])
        name = player["name"] if player else f"玩家{entry['uid'][-4:]}"
        position_desc = BOARD_POSITIONS[min(entry["progress"], BOARD_WIDTH - 1)]
        message += f"{i}. {name}: {entry['score']}分 - {position_desc}\n"

    return message
