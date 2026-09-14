"""作业：每天从已解锁学科稳定随机布置2—3门，跨日未交会扣经验。

随机种子包含玩家和日期，因此反复查看不会刷新作业；连续缺席时按作业日设置
扣分上限，避免解锁科目越多的玩家一次被扣得越惨。

二年级起改成概率制：固定3门，每次提交只有HOMEWORK_SUCCESS_RATE的概率成功；
第一次提交免费，失败后每次重试要扣HOMEWORK_RETRY_STAMINA_COST点体力，
体力耗尽仍未成功也不算"没交"，不会触发逾期扣分（当天试过就不罚）。
第HOMEWORK_PITY_ATTEMPTS次提交保底必过，不会出现纯粹靠运气一直卡关交不出的情况。
"""

import random

from plugins.hp_core import storage as core_storage

from . import storage, subjects

HOMEWORK_EXP = 4
HOMEWORK_PENALTY = 4
HOMEWORK_DAILY_PENALTY_CAP = 8
HOMEWORK_COMPLETION_GALLEONS = 8
HOMEWORK_MIN_COUNT = 2
HOMEWORK_MAX_COUNT = 3

HOMEWORK_PROBABILITY_MIN_GRADE = 2
HOMEWORK_FIXED_COUNT = 3
HOMEWORK_SUCCESS_RATE = 0.1
HOMEWORK_PITY_ATTEMPTS = 20
HOMEWORK_SUCCESS_EXP = 10
HOMEWORK_RETRY_STAMINA_COST = 6


class HomeworkError(Exception):
    pass


def _unlocked_subject_keys(grade: int) -> list[str]:
    return [key for key, _, unlock_grade, _ in subjects.SUBJECTS if grade >= unlock_grade]


def settle_overdue(uid: str, day: int) -> tuple[int, int]:
    """返回（结算门数，实际总扣分），每个缺席日最多扣固定上限。"""
    return core_storage.settle_homework_with_daily_cap(
        uid, day, HOMEWORK_PENALTY, HOMEWORK_DAILY_PENALTY_CAP
    )


def ensure_today(uid: str, grade: int, day: int) -> None:
    unlocked = _unlocked_subject_keys(grade)
    rng = random.Random(f"hogwarts-homework:{uid}:{day}")
    if grade >= HOMEWORK_PROBABILITY_MIN_GRADE:
        count = min(len(unlocked), HOMEWORK_FIXED_COUNT)
    else:
        count = min(len(unlocked), rng.randint(HOMEWORK_MIN_COUNT, HOMEWORK_MAX_COUNT))
    for key in rng.sample(unlocked, count):
        core_storage.ensure_homework(uid, key, day)


def _sync(uid: str, grade: int, day: int) -> tuple[int, int]:
    """惰性同步：先结算过去逾期的，再补发今天该有的。"""
    overdue_count, overdue_penalty = settle_overdue(uid, day)
    ensure_today(uid, grade, day)
    return overdue_count, overdue_penalty


def submit(uid: str, subject_input: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise HomeworkError("你还没有分院，先发「/入学」完成入学测试。")

    found = subjects.find(subject_input.strip())
    if not found:
        raise HomeworkError("没有这门课。")
    key, name, unlock_grade, _ = found
    if player["grade"] < unlock_grade:
        raise HomeworkError(f"「{name}」你还没解锁，交不了这门课的作业。")

    day = core_storage.get_current_day() or 1
    overdue_count, overdue_penalty = _sync(uid, player["grade"], day)

    row = core_storage.get_homework(uid, key, day)
    if not row:
        raise HomeworkError(f"今天没有布置「{name}」作业，先用「/今日作业」查看。")
    if row["status"] != "pending":
        raise HomeworkError(f"「{name}」今天的作业已经交过了。")

    if player["grade"] < HOMEWORK_PROBABILITY_MIN_GRADE:
        core_storage.complete_homework(uid, key, day)
        total_exp = core_storage.add_subject_exp(uid, key, HOMEWORK_EXP)
        completion_reward = storage.claim_homework_completion_reward(
            uid, day, HOMEWORK_COMPLETION_GALLEONS
        )
        return {
            "subject": name,
            "success": True,
            "exp_gained": HOMEWORK_EXP,
            "total_exp": total_exp,
            "overdue_settled": overdue_count,
            "overdue_penalty": overdue_penalty,
            "completion_reward": HOMEWORK_COMPLETION_GALLEONS if completion_reward else 0,
        }

    # 二年级起概率制：第一次提交免费，失败后再交就是"重试"，要扣体力。
    if row["attempts"] > 0:
        fresh = core_storage.sync_stamina(uid)
        if fresh["stamina"] < HOMEWORK_RETRY_STAMINA_COST:
            raise HomeworkError(
                f"体力不够了，重试「{name}」需要{HOMEWORK_RETRY_STAMINA_COST}点体力，"
                f"当前体力{fresh['stamina']}/{core_storage.STAMINA_MAX}。"
            )
        core_storage.spend_stamina(uid, HOMEWORK_RETRY_STAMINA_COST)

    attempt_no = row["attempts"] + 1
    core_storage.record_homework_attempt(uid, key, day)
    pity = attempt_no >= HOMEWORK_PITY_ATTEMPTS
    if not (pity or random.random() < HOMEWORK_SUCCESS_RATE):
        return {
            "subject": name,
            "success": False,
            "exp_gained": 0,
            "overdue_settled": overdue_count,
            "overdue_penalty": overdue_penalty,
            "completion_reward": 0,
            "attempts_left_to_pity": HOMEWORK_PITY_ATTEMPTS - attempt_no,
        }

    core_storage.complete_homework(uid, key, day)
    total_exp = core_storage.add_subject_exp(uid, key, HOMEWORK_SUCCESS_EXP)
    completion_reward = storage.claim_homework_completion_reward(
        uid, day, HOMEWORK_COMPLETION_GALLEONS
    )
    return {
        "subject": name,
        "success": True,
        "exp_gained": HOMEWORK_SUCCESS_EXP,
        "total_exp": total_exp,
        "overdue_settled": overdue_count,
        "overdue_penalty": overdue_penalty,
        "completion_reward": HOMEWORK_COMPLETION_GALLEONS if completion_reward else 0,
        "pity": pity,
    }


def list_today(uid: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise HomeworkError("你还没有分院，先发「/入学」完成入学测试。")

    day = core_storage.get_current_day() or 1
    overdue_count, overdue_penalty = _sync(uid, player["grade"], day)

    rows = core_storage.list_today_homework(uid, day)
    by_key = {r["subject"]: r["status"] for r in rows}
    pending, done = [], []
    for key, name, unlock_grade, _ in subjects.SUBJECTS:
        if key not in by_key:
            continue
        (pending if by_key[key] == "pending" else done).append(name)
    return {
        "pending": pending,
        "done": done,
        "overdue_settled": overdue_count,
        "overdue_penalty": overdue_penalty,
    }
