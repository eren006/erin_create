"""学年测验 / O.W.L. / N.E.W.T. 打分。

公式：该科分数 = 80% × 上课进度比例 + 20% × 随机浮动
"上课进度比例"会按每天全科共享8节、单科最多2节，并结合当时已经解锁的
课程数量计算公平份额，封顶1.0。
作业产出的经验不计入分母，相当于给认真写作业的人一个安全垫，不会让门槛跟着膨胀。

只有五年级(O.W.L.)和七年级(N.E.W.T.)用正式六档评级(O/E/A/P/D/T)，其余年级末只出
简化四档评价，从结构上保证"满分"这个概念只会在高年级出现，不需要另外手写门槛表。
"""

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_school import lessons, subjects

# 对应架构时间轴：年级开始/结束的绝对天数
GRADE_START_DAY = {1: 1, 2: 5, 3: 9, 4: 13, 5: 17, 6: 22, 7: 26}
GRADE_END_DAY = {1: 4, 2: 8, 3: 12, 4: 16, 5: 21, 6: 25, 7: 30}
FORMAL_EXAM_GRADES = {5, 7}  # 5=O.W.L.，7=N.E.W.T.

# 从低到高，(上限, 档位标签)，score落在第一个"小于上限"的区间
SIMPLE_BANDS = [(0.30, "不及格"), (0.55, "及格"), (0.80, "良好"), (1.01, "优秀")]
FORMAL_BANDS = [(0.15, "T"), (0.30, "D"), (0.50, "P"), (0.70, "A"), (0.88, "E"), (1.01, "O")]


def _band(score: float, exam_grade: int) -> str:
    bands = FORMAL_BANDS if exam_grade in FORMAL_EXAM_GRADES else SIMPLE_BANDS
    for threshold, label in bands:
        if score < threshold:
            return label
    return bands[-1][1]


def _subject_score(uid: str, unlock_grade: int, subject_key: str, exam_day: int) -> float:
    unlock_day = GRADE_START_DAY.get(unlock_grade, exam_day)
    # 全科每天只共享8节计分课，所以单科分母按当时已解锁课程数均分额度；
    # 否则三年级10门课会被错误地当成每天理论上能完成20节。
    theoretical_lessons = 0.0
    for day in range(unlock_day, exam_day + 1):
        grade_that_day = next(
            (grade for grade, end_day in GRADE_END_DAY.items() if day <= end_day), 7
        )
        unlocked_count = sum(1 for _, _, grade, _ in subjects.SUBJECTS if grade <= grade_that_day)
        theoretical_lessons += min(
            lessons.DAILY_LIMIT_PER_SUBJECT,
            lessons.DAILY_GLOBAL_LIMIT / max(1, unlocked_count),
        )
    theoretical_max = theoretical_lessons * lessons.EXP_PER_LESSON
    exp = core_storage.get_subject_exp(uid, subject_key)
    ratio = min(1.0, exp / theoretical_max) if theoretical_max > 0 else 0.0
    return min(1.0, max(0.0, 0.8 * ratio + 0.2 * random.random()))


def run_exam(uid: str, exam_grade: int, exam_day: int) -> list[dict]:
    """对该玩家已解锁的每门学科分别打分并记录，返回本次结果列表。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        return []
    results = []
    for key, name, unlock_grade, category in subjects.SUBJECTS:
        if unlock_grade > exam_grade:
            continue
        score = _subject_score(uid, unlock_grade, key, exam_day)
        band = _band(score, exam_grade)
        core_storage.record_exam_result(uid, key, exam_grade, exam_day, score, band)
        results.append({"subject": name, "score": score, "band": band})
    return results
