"""上课：消耗体力并增加课堂疲劳，获得学科经验和魔咒进度。

每天全科共享8点疲劳上限，每完成一节计分课疲劳+1；同一门课每天前2节计分。
疲劳满后，三门实操课仍能继续加练魔咒，但不再获得学科经验和课堂表现奖励。
"""

from plugins.hp_core import spells as spell_catalog
from plugins.hp_core import storage as core_storage

from . import subjects

STAMINA_COST = 4
DAILY_GLOBAL_LIMIT = 8  # 玩家侧显示为疲劳值上限
DAILY_LIMIT_PER_SUBJECT = 2
DAILY_EXP_LESSONS = DAILY_LIMIT_PER_SUBJECT  # 保留给旧调用方；现在允许上的课都会计分
EXP_PER_LESSON = 8


class LessonError(Exception):
    pass


def check_lesson_available(uid: str, subject_input: str) -> tuple:
    """只检查能否开课，不消耗体力或次数；课堂事件开始前使用。"""
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise LessonError("你还没有分院，先发「/入学」完成入学测试。")

    found = subjects.find(subject_input.strip())
    if not found:
        names = "、".join(name for _, name, _, _ in subjects.SUBJECTS)
        raise LessonError(f"没有这门课。可选：{names}")
    key, name, unlock_grade, category = found
    if player["grade"] < unlock_grade:
        raise LessonError(f"「{name}」要到{unlock_grade}年级才能上，你现在是{player['grade']}年级。")

    day = core_storage.get_current_day() or 1
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
    if player["stamina"] < STAMINA_COST:
        wait_min = core_storage.seconds_to_next_stamina(player) // 60 + 1
        raise LessonError(
            f"你握着魔杖的手已经有些发沉，当前体力{player['stamina']}/{core_storage.STAMINA_MAX}，"
            f"上完一节课需要{STAMINA_COST}点。先休息一下，约{wait_min}分钟后会恢复一轮体力。"
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

    core_storage.spend_stamina(uid, STAMINA_COST)
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
