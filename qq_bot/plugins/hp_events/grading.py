"""学年测验 / O.W.L. / N.E.W.T. 打分。

公式：该科分数 = 90% × 上课进度比例 + 10% × 随机浮动，苦读比运气重要得多。
"上课进度比例" = 这门课的经验 / (LESSONS_FOR_FULL_SCORE × 每节课经验)，
上够 LESSONS_FOR_FULL_SCORE 节计分课，比例就封顶1.0——这是固定目标，跟这个
学年多长、还剩几天都无关，需要的经验因此比"按剩余天数打折"时更多。
但全科每天只共享 lessons.DAILY_GLOBAL_LIMIT 节计分课，解锁的科目一多，
根本没法让每一门都冲到 LESSONS_FOR_FULL_SCORE 节，必须挑重点，
这也是低年级不可能所有学科都拿高分的原因。
作业产出的经验不计入分母，相当于给认真写作业的人一个安全垫，不会让门槛跟着膨胀。

只有五年级(O.W.L.)和七年级(N.E.W.T.)用正式六档评级(O/E/A/P/D/T)，其余年级末只出
简化四档评价，从结构上保证"满分"这个概念只会在高年级出现，不需要另外手写门槛表。
"""

import random

from plugins.hp_core import storage as core_storage
from plugins.hp_school import lessons, subjects

# 对应架构时间轴：年级结束的绝对天数，给日历调度（学年测验/圣诞节）用，跟打分门槛无关
GRADE_END_DAY = {1: 4, 2: 8, 3: 12, 4: 16, 5: 21, 6: 25, 7: 30}
FORMAL_EXAM_GRADES = {5, 7}  # 5=O.W.L.，7=N.E.W.T.

LESSONS_FOR_FULL_SCORE = 10  # 一门课上够这么多节计分课，进度比例就封顶1.0

# 从低到高，(上限, 档位标签)，score落在第一个"小于上限"的区间
# "优秀"门槛拉到0.90：分数=0.9×进度比例+0.1×随机浮动，进度比例满分(1.0)时
# 分数落在[0.90,1.0]，稳进优秀；没上够 LESSONS_FOR_FULL_SCORE 节课就基本没机会靠运气蒙进去。
SIMPLE_BANDS = [(0.30, "不及格"), (0.55, "及格"), (0.90, "良好"), (1.01, "优秀")]
FORMAL_BANDS = [(0.15, "T"), (0.30, "D"), (0.50, "P"), (0.70, "A"), (0.88, "E"), (1.01, "O")]


def _band(score: float, exam_grade: int) -> str:
    bands = FORMAL_BANDS if exam_grade in FORMAL_EXAM_GRADES else SIMPLE_BANDS
    for threshold, label in bands:
        if score < threshold:
            return label
    return bands[-1][1]


def _ratio(uid: str, subject_key: str) -> float:
    theoretical_max = LESSONS_FOR_FULL_SCORE * lessons.EXP_PER_LESSON
    exp = core_storage.get_subject_exp(uid, subject_key)
    return min(1.0, exp / theoretical_max)


def _subject_score(uid: str, subject_key: str) -> float:
    ratio = _ratio(uid, subject_key)
    return min(1.0, max(0.0, 0.9 * ratio + 0.1 * random.random()))


def preview_score_range(uid: str, subject_key: str, grade: int) -> dict:
    """上课页面用的实时预览：按当前进度，预计这学年真正考试时会落在什么分数区间/档位。
    复用 run_exam 同一套换算公式，只是拿掉正式考试才有的±10%随机浮动，
    展示的是这段随机浮动对应的分数区间，而不是等考完才知道结果。"""
    ratio = _ratio(uid, subject_key)
    low = max(0.0, min(1.0, 0.9 * ratio))
    high = max(0.0, min(1.0, 0.9 * ratio + 0.1))
    return {
        "low_pct": round(low * 100),
        "high_pct": round(high * 100),
        "low_band": _band(low, grade),
        "high_band": _band(high, grade),
    }


def run_exam(uid: str, exam_grade: int, exam_day: int) -> list[dict]:
    """对该玩家已解锁的每门学科分别打分并记录，返回本次结果列表。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        return []
    results = []
    for key, name, unlock_grade, category in subjects.SUBJECTS:
        if unlock_grade > exam_grade:
            continue
        score = _subject_score(uid, key)
        band = _band(score, exam_grade)
        core_storage.record_exam_result(uid, key, exam_grade, exam_day, score, band)
        results.append({"subject": name, "score": score, "band": band})
    return results
