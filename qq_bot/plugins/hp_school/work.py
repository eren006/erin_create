"""霍格沃茨学生打工：消耗体力换取稳定加隆收入。"""

import random

from plugins.hp_core import storage as core_storage

from . import storage

STAMINA_COST = 5
DAILY_LIMIT = 3

# 名称: (最低年级, 最低工资, 最高工资, 叙事)
JOBS = {
    "图书馆整理员": (1, 7, 9, "你把会咬人的书和普通藏书分开，又追回了三本试图逃走的目录。"),
    "温室助手": (1, 7, 10, "你给幼苗换盆、清理会缠人的藤蔓，手套上沾满了带香味的泥土。"),
    "猫头鹰棚帮工": (1, 6, 9, "你送完饲料，又清理了满地羽毛。最后一只猫头鹰总算肯从你头顶下来。"),
    "魔药储藏室盘点": (2, 8, 11, "你核对瓶签，把会冒烟的材料放回阴凉处，期间只打碎了一只空瓶。"),
    "魁地奇球场维护": (2, 8, 12, "你追着乱飞的训练球跑了半个球场，又把看台旗帜重新系牢。"),
    "奖杯陈列室擦拭": (3, 9, 12, "你擦亮几十只会自夸的奖杯，还耐心听完了一座银杯讲述当年的决赛。"),
}


class WorkError(Exception):
    pass


def available_jobs(grade: int) -> list[str]:
    return [name for name, (min_grade, *_rest) in JOBS.items() if grade >= min_grade]


def work(uid: str, job_input: str = "") -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise WorkError("你还没有完成入学手续，费尔奇不会把城堡钥匙交给陌生人。")
    jobs = available_jobs(player["grade"])
    if job_input:
        if job_input not in JOBS:
            raise WorkError("没有这份工作。可选：" + "、".join(jobs))
        if job_input not in jobs:
            raise WorkError(f"「{job_input}」要到{JOBS[job_input][0]}年级才会招人。")
        job = job_input
    else:
        job = random.choice(jobs)

    player = core_storage.sync_stamina(uid)
    _, low, high, story = JOBS[job]
    earnings = random.randint(low, high)
    day = core_storage.get_current_day() or 1
    result = storage.complete_work_atomic(uid, day, STAMINA_COST, earnings, DAILY_LIMIT)
    if result["status"] == "daily_limit":
        raise WorkError("今天的三份零工都做完了。费尔奇摆摆手，让你明天再来。")
    if result["status"] == "insufficient_stamina":
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise WorkError(
            f"你现在只有{player['stamina']}/{core_storage.STAMINA_MAX}体力，连拖把都快举不起来；"
            f"打工需要{STAMINA_COST}点。约{wait_min}分钟后恢复一轮。"
        )
    return {
        "job": job, "story": story, "earnings": earnings,
        "galleons": result["galleons"], "count": result["count"], "daily_limit": DAILY_LIMIT,
    }
