"""上课：消耗体力并增加课堂疲劳，获得学科经验和魔咒进度。

每天全科共享8点疲劳上限，每完成一节计分课疲劳+1；同一门课每天前3节计分。
全科上限没跟着单科上限一起涨，所以解锁科目一多，根本没法每门都上够——
必须挑重点，这也是低年级不可能所有学科都拿高分的原因。
疲劳满后，三门实操课仍能继续加练魔咒，但不再获得学科经验和课堂表现奖励。
"""

from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage

from . import subjects

DAILY_GLOBAL_LIMIT = 8  # 玩家侧显示为疲劳值上限
DAILY_LIMIT_PER_SUBJECT = 3
DAILY_EXP_LESSONS = DAILY_LIMIT_PER_SUBJECT  # 保留给旧调用方；现在允许上的课都会计分
EXP_PER_LESSON = 8

# 年级切换日：与 hp_events.grading.GRADE_END_DAY（1:4,2:8,3:12,4:16,5:21,6:25,7:30）
# 各+1，即每个年级最后一天结束后的第一天。日历轮询(hp_events.CALENDAR_POLL_MINUTES=30分钟)
# 要等这一天开始后才会跑学年结算，跳天和结算之间有个最长30分钟的空档——这段时间里
# 玩家的年级字段还没被推到下一级。这里用同样30分钟的宽限期直接封住上课入口，
# 免得有人卡这个空档用旧年级的身份把课蹭了，导致新年级的第一天数据对不上。
NEW_GRADE_START_DAYS = {5, 9, 13, 17, 22, 26, 31}
SETTLEMENT_GRACE_SECONDS = 30 * 60


def in_settlement_grace_window(day: int) -> bool:
    return day in NEW_GRADE_START_DAYS and core_storage.seconds_since_beijing_midnight() < SETTLEMENT_GRACE_SECONDS


def stamina_cost_for_grade(grade: int) -> int:
    """年级越高课业越重，上一节课耗的体力也跟着涨：2年级8点，每升一级+1点。"""
    return 6 + grade


class LessonError(Exception):
    pass


def check_lesson_available(uid: str, subject_input: str) -> tuple:
    """只检查能否开课，不消耗体力或次数；课堂事件开始前使用。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise LessonError("你还没有分院，先发「/入学」完成入学测试。")

    day = core_storage.get_current_day() or 1
    if in_settlement_grace_window(day):
        raise LessonError("教务处还在统计上一学年的成绩，半小时后再来上课。")

    found = subjects.find(subject_input.strip())
    if not found:
        names = "、".join(name for _, name, _, _ in subjects.SUBJECTS)
        raise LessonError(f"没有这门课。可选：{names}")
    key, name, unlock_grade, category = found
    if player["grade"] < unlock_grade:
        raise LessonError(f"「{name}」要到{unlock_grade}年级才能上，你现在是{player['grade']}年级。")

    today_count = core_storage.get_lesson_count(uid, key, day)
    fatigue = core_storage.get_total_scored_lesson_count(uid, day)
    is_spell_subject = key in spell_catalog.SPELL_SUBJECTS
    if fatigue >= DAILY_GLOBAL_LIMIT and not is_spell_subject:
        raise LessonError(
            f"你今天已经在教室之间奔波了太久，疲劳值达到{fatigue}/{DAILY_GLOBAL_LIMIT}。"
            "再听下去，课本上的字恐怕都要开始跳舞了。普通课程已经听不进去了；"
            "如果还握得住魔杖，可以去实操课加练咒语。"
        )
    if today_count >= DAILY_LIMIT_PER_SUBJECT and not is_spell_subject:
        raise LessonError(
            f"教授合上了「{name}」的点名册：这门课今天已经上完{DAILY_LIMIT_PER_SUBJECT}节。"
            "先去试试别的课程吧。"
        )

    player = core_storage.sync_stamina(uid)
    stamina_cost = stamina_cost_for_grade(player["grade"])
    if player["stamina"] < stamina_cost:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise LessonError(
            f"你握着魔杖的手已经有些发沉，当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"{player['grade']}年级的课业更重，上完一节课需要{stamina_cost}点。"
            f"先休息一下，约{wait_min}分钟后会恢复一轮体力。"
        )
    return player, found


def next_spell_for(uid: str, subject: str, grade: int) -> tuple | None:
    """该科下一个要学的咒语：跳过已学会的，也跳过年级不够的（等年级够了会自动回头学）。"""
    learned = core_storage.list_learned_spells(uid)
    for spell in spell_catalog.spells_of_subject(subject):
        if spell[0] in learned:
            continue
        if spell[4] > grade:
            continue
        return spell
    return None


def blocked_spell_for(uid: str, subject: str, grade: int) -> tuple | None:
    """因为年级不够而被跳过的、最靠前的那个咒语，用来给玩家一句提示。"""
    learned = core_storage.list_learned_spells(uid)
    for spell in spell_catalog.spells_of_subject(subject):
        if spell[0] in learned:
            continue
        if spell[4] > grade:
            return spell
    return None


def take_lesson(uid: str, subject_input: str) -> dict:
    player, found = check_lesson_available(uid, subject_input)
    key, name, unlock_grade, category = found

    is_spell_subject = key in spell_catalog.SPELL_SUBJECTS
    day = core_storage.get_current_day() or 1
    today_count = core_storage.get_lesson_count(uid, key, day)
    subject_scored_count = core_storage.get_scored_lesson_count(uid, key, day)
    fatigue_before = core_storage.get_total_scored_lesson_count(uid, day)

    core_storage.spend_stamina(uid, stamina_cost_for_grade(player["grade"]))
    core_storage.increment_lesson_count(uid, key, day)

    gives_exp = (
        subject_scored_count < DAILY_LIMIT_PER_SUBJECT
        and fatigue_before < DAILY_GLOBAL_LIMIT
    )
    score_block_reason = ""
    if gives_exp:
        core_storage.increment_scored_lesson_count(uid, key, day)
        exp_gained = EXP_PER_LESSON
        total_exp = core_storage.add_subject_exp(uid, key, exp_gained)
    else:
        score_block_reason = (
            "subject_limit"
            if subject_scored_count >= DAILY_LIMIT_PER_SUBJECT
            else "fatigue_limit"
        )
        exp_gained = 0
        total_exp = core_storage.get_subject_exp(uid, key)

    result = {
        "subject": name,
        "category": category,
        "exp_gained": exp_gained,
        "total_exp": total_exp,
        "today_count": today_count + 1,
        "fatigue": core_storage.get_total_scored_lesson_count(uid, day),
        "fatigue_max": DAILY_GLOBAL_LIMIT,
        "gives_exp": gives_exp,
        "score_block_reason": score_block_reason,
        "is_spell_subject": is_spell_subject,
        "daily_exp_lessons": DAILY_EXP_LESSONS,
        "daily_limit": DAILY_LIMIT_PER_SUBJECT,
        "learned_spell": None,
        "spell_progress": None,
        "spell_target": None,
        "blocked_spell": None,
        "all_learned": False,
    }
    if not is_spell_subject:
        return result

    target = next_spell_for(uid, key, player["grade"])
    if target is None:
        blocked = blocked_spell_for(uid, key, player["grade"])
        if blocked:
            result["blocked_spell"] = {"name": blocked[1], "min_grade": blocked[4]}
        else:
            result["all_learned"] = True
        return result

    progress = core_storage.get_spell_progress(uid, key) + 1
    if progress >= spell_catalog.LESSONS_PER_SPELL:
        core_storage.learn_spell(uid, target[0])
        core_storage.set_spell_progress(uid, key, 0)
        result["learned_spell"] = {
            "name": target[1],
            "latin": target[2],
            "category": target[5],
            "desc": target[6],
        }
        nxt = next_spell_for(uid, key, player["grade"])
        if nxt:
            result["spell_target"] = nxt[1]
            result["spell_progress"] = 0
        else:
            blocked = blocked_spell_for(uid, key, player["grade"])
            if blocked:
                result["blocked_spell"] = {"name": blocked[1], "min_grade": blocked[4]}
            else:
                result["all_learned"] = True
    else:
        core_storage.set_spell_progress(uid, key, progress)
        result["spell_target"] = target[1]
        result["spell_progress"] = progress
    return result
