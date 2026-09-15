"""日历调度的编排逻辑：年级切换（学年测验+全员升级+经验衰减）、Day30毕业结算。

只负责"某一天该发生什么"，不负责怎么把消息发出去——那是 __init__.py 里
挂 apscheduler 定时任务的活，这里只返回结构化的事件数据。
"""

from plugins.hp_core import storage as core_storage

from . import creatures, gnomes, grading, newsletter, prefect, quidditch

GRADE_END_DAY = grading.GRADE_END_DAY
DECAY_RATE = 0.15  # 每学年切换只留15%经验，逼着每学期重新好好上课，不是混日子躺赢老本
MVP_TITLE_PREFIX = "quidditch_mvp"
HOUSE_MVP_TITLE_PREFIX = "house_contributor"


def _award_quidditch_mvps(grade_ended: int) -> dict[str, dict | None]:
    """每学年结算时自动颁：算出各院当学年MVP、解锁称号，然后把赛季分清零。"""
    awards: dict[str, dict | None] = {}
    for house in core_storage.HOUSES:
        mvp = quidditch.get_mvp(house)
        if mvp:
            title_key = f"{MVP_TITLE_PREFIX}_g{grade_ended}_{house}"
            core_storage.unlock_title(mvp["uid"], title_key)
            awards[house] = {"uid": mvp["uid"], "position": mvp["position"], "score": mvp["season_score"]}
        else:
            awards[house] = None
    quidditch.reset_season_scores()
    return awards


def _award_house_contributors(grade_ended: int) -> dict[str, dict | None]:
    """每学年结算时自动颁"学院个人奖"：给各院对学院分贡献最多的人解锁称号，然后清零重新计贡献。"""
    awards: dict[str, dict | None] = {}
    for house in core_storage.HOUSES:
        top = core_storage.top_house_contributor(house)
        if top:
            title_key = f"{HOUSE_MVP_TITLE_PREFIX}_g{grade_ended}_{house}"
            core_storage.unlock_title(top["uid"], title_key)
            awards[house] = {"uid": top["uid"], "points": top["points"]}
        else:
            awards[house] = None
    core_storage.reset_house_contributions()
    return awards


def _run_year_end(day_ended: int, grade_ended: int) -> dict:
    uids = core_storage.list_sorted_uids()
    per_player = []
    for uid in uids:
        results = grading.run_exam(uid, grade_ended, day_ended)
        if results:
            per_player.append({"uid": uid, "results": results})

    mvp_awards = _award_quidditch_mvps(grade_ended)
    house_contributor_awards = _award_house_contributors(grade_ended)

    next_grade = min(grade_ended + 1, 7)
    core_storage.advance_all_grades(next_grade)
    core_storage.decay_all_subject_exp(DECAY_RATE)

    return {
        "grade_ended": grade_ended,
        "next_grade": next_grade,
        "student_count": len(uids),
        "per_player": per_player,
        "mvp_awards": mvp_awards,
        "house_contributor_awards": house_contributor_awards,
    }


def _run_graduation(day: int) -> dict:
    uids = core_storage.list_sorted_uids()
    per_player = []
    for uid in uids:
        results = grading.run_exam(uid, 7, day)
        if results:
            per_player.append({"uid": uid, "results": results})
    mvp_awards = _award_quidditch_mvps(7)
    house_board = core_storage.house_leaderboard()
    top_house = house_board[0] if house_board else None
    house_contributor_awards = _award_house_contributors(7)
    student_board = core_storage.student_leaderboard(limit=1)
    top_student = student_board[0] if student_board else None
    return {
        "house_board": house_board,
        "house_contributor_awards": house_contributor_awards,
        "top_house": top_house,
        "top_student": top_student,
        "mvp_awards": mvp_awards,
        "student_count": len(uids),
        "per_player": per_player,
    }


def process_day(day: int) -> list[dict]:
    """day这一天要处理的事件（可能是空列表——大部分日子什么都不触发）。"""
    events = []
    if day == prefect.NOMINATE_DAY:
        nominated = prefect.nominate()
        events.append({"type": "prefect_nomination", "data": {"candidates": nominated}})
    if day == prefect.CLOSE_DAY:
        events.append({"type": "prefect_result", "data": {"winners": prefect.close_election()}})
    if day == gnomes.AWARD_DAY:
        champion = gnomes.award_champion()
        if champion:
            events.append({"type": "gnome_award", "data": champion})
    if day == creatures.AWARD_DAY:
        champion = creatures.award_champion()
        if champion:
            events.append({"type": "creature_award", "data": champion})
    for grade, end_day in GRADE_END_DAY.items():
        # 结算要等这个年级的最后一天(end_day)完整过完才算数，所以触发点是end_day+1
        # 的开头，而不是end_day当天——否则day==end_day一到（当天0点后的轮询就会撞上），
        # 大家会在圣诞节当天一早就被直接推去下一年级，圣诞节本身反而变成了"新生"在过。
        if day != end_day + 1:
            continue
        if grade == 7:
            events.append({"type": "graduation", "data": _run_graduation(end_day)})
        else:
            events.append({"type": "year_end", "data": _run_year_end(end_day, grade)})
        events.append({"type": "yearbook", "data": {"text": newsletter.publish(end_day)}})
    return events
