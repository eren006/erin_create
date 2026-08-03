"""入学问卷 + 分院测试。

流程：性别 -> 出生环境 -> 性格 -> 兴趣爱好 -> 最喜欢的食物，每步从对应类别里
随机抽3个选项，玩家三选一。除性别外，每个选项都带一个学院暗分向量，四步选完后
按累计暗分最高的学院分院（同分随机决胜）。
"""

import json
import random

from plugins.hp_core import storage as core_storage

from . import catalog, storage, wands

storage.init_db()

STARTING_GALLEONS = 80  # 开学启动资金，至少要覆盖得起最便宜的扫帚(60)；等打工/探索这些正式收入来源做出来后可能要重新平衡


class SortingError(Exception):
    pass


def _pick_offered(options: list) -> list[int]:
    return random.sample(range(len(options)), k=min(3, len(options)))


def resume(uid: str) -> dict | None:
    """如果这个人正卡在问卷中间，原样返回当前该答的那一题（不重新抽选项，
    不清空已经选的部分），没有进行中的会话就返回None。"""
    session = storage.get_session(uid)
    if not session:
        return None
    if session["step"] == 0:
        return {"step": "gender", "label": "性别", "options": list(catalog.GENDERS)}
    if session["step"] in (5, 6, 7):
        return _wand_step_result(session)
    step_index = session["step"] - 1
    if not (0 <= step_index < len(catalog.STEPS)):
        return None
    offered = json.loads(session["offered_json"])
    key, label, options = catalog.STEPS[step_index]
    return {"step": key, "label": label, "options": [options[i][0] for i in offered]}


NAME_MAX_LEN = 12


def start(uid: str, name: str = "") -> dict:
    """被打断了、被别人的消息刷走了、隔了很久才回来点——再发一次/入学不会清空进度，
    而是原样把当时卡住的那一题重新发一遍。只有从没开始过才会真正重置。"""
    player = core_storage.get_player(uid)
    if player and player["house"]:
        raise SortingError(f"你已经分院过了，是{player['house']}的{player['name']}，不用重新测试。")

    existing = resume(uid)
    if existing:
        existing["is_resume"] = True
        existing["name"] = storage.get_session(uid)["name"]
        return existing

    name = name.strip()
    if not name:
        raise SortingError("入学要先起个名字：/入学 你的名字")
    if len(name) > NAME_MAX_LEN:
        raise SortingError(f"名字太长了，最多{NAME_MAX_LEN}个字。")
    if core_storage.is_name_taken(name) or storage.is_pending_name_taken(name, uid):
        raise SortingError(f"「{name}」这个名字已经有人用了，换一个。")

    core_storage.ensure_game_started()  # 第一个触发/入学的人，此刻起算Day1
    storage.start_session(uid, name)
    result = resume(uid)
    result["is_resume"] = False
    result["name"] = name
    return result


def choose_gender(uid: str, position: int) -> dict:
    session = storage.get_session(uid)
    if not session or session["step"] != 0:
        raise SortingError("请先发送「/入学」开始测试。")
    if not (0 <= position < len(catalog.GENDERS)):
        raise SortingError("请点击按钮选择。")
    gender = catalog.GENDERS[position]

    key, label, options = catalog.STEPS[0]
    offered = _pick_offered(options)
    storage.update_session(
        uid,
        step=1,
        gender=gender,
        offered_json=json.dumps(offered),
    )
    return {
        "done": False,
        "picked": gender,
        "step": key,
        "label": label,
        "options": [options[i][0] for i in offered],
    }


def choose_option(uid: str, position: int) -> dict:
    """position：这次展示的3个按钮里的第几个（0/1/2）。"""
    session = storage.get_session(uid)
    if not session or session["step"] < 1:
        raise SortingError("请先发送「/入学」开始测试。")

    step_index = session["step"] - 1
    if not (0 <= step_index < len(catalog.STEPS)):
        raise SortingError("测试已经结束了，不能重复选择。")

    offered = json.loads(session["offered_json"])
    if not (0 <= position < len(offered)):
        raise SortingError("请点击按钮选择，不要用别的方式提交。")

    _, _, options = catalog.STEPS[step_index]
    real_index = offered[position]
    name, house_scores, subject_bonus = options[real_index]

    scores = json.loads(session["scores_json"])
    for house, val in house_scores.items():
        scores[house] = scores.get(house, 0) + val

    bonus = json.loads(session["subject_bonus_json"])
    for subject, val in subject_bonus.items():
        bonus[subject] = bonus.get(subject, 0) + val
    answers = json.loads(session["answers_json"])
    answers[catalog.STEPS[step_index][0]] = name

    # 出生环境决定姓氏，纯氛围用，不参与任何判定
    surname = catalog.SURNAMES.get(name, "") if catalog.STEPS[step_index][0] == "background" else ""

    next_step_index = step_index + 1
    if next_step_index < len(catalog.STEPS):
        nkey, nlabel, noptions = catalog.STEPS[next_step_index]
        offered_next = _pick_offered(noptions)
        extra = {"surname": surname} if surname else {}
        storage.update_session(
            uid,
            step=session["step"] + 1,
            offered_json=json.dumps(offered_next),
            scores_json=json.dumps(scores),
            subject_bonus_json=json.dumps(bonus),
            answers_json=json.dumps(answers, ensure_ascii=False),
            **extra,
        )
        return {
            "done": False,
            "picked": name,
            "surname": surname,
            "step": nkey,
            "label": nlabel,
            "options": [noptions[i][0] for i in offered_next],
        }

    # 四步都选完了：先确定学院，但在奥利凡德选定魔杖前不正式开放游戏。
    house = _resolve_house(scores)
    core_storage.get_or_create_player(uid)
    wand_state = {
        "wood": "",
        "core": "",
        "wood_options": wands.generate_wood_options(answers, house),
    }
    storage.update_session(
        uid,
        step=5,
        scores_json=json.dumps(scores),
        subject_bonus_json=json.dumps(bonus),
        answers_json=json.dumps(answers, ensure_ascii=False),
        pending_house=house,
        wand_options_json=json.dumps(wand_state, ensure_ascii=False),
    )
    day = core_storage.get_current_day()
    full_name = f"{session['name']}·{session['surname']}" if session["surname"] else session["name"]
    return {
        "done": False,
        "needs_wand": True,
        "house_just_selected": True,
        "picked": name,
        "player_name": session["name"],
        "full_name": full_name,
        "house": house,
        "day": day,
        "is_transfer": bool(day and day > 1),
        "subject_bonus": bonus,
        **_wand_step_result(storage.get_session(uid)),
    }


WAND_STEP_STAGE = {5: "wood", 6: "core", 7: "length"}


def _load_wand_state(session) -> dict:
    state = json.loads(session["wand_options_json"])
    # 兼容上一版“直接三选一成品魔杖”的未完成会话。
    if isinstance(state, list):
        state = {
            "wood": "",
            "core": "",
            "wood_options": [wand["wood"] for wand in state],
        }
        storage.update_session(
            session["uid"], wand_options_json=json.dumps(state, ensure_ascii=False)
        )
    return state


def _wand_step_result(session, reaction: str = "") -> dict:
    stage = WAND_STEP_STAGE[session["step"]]
    state = _load_wand_state(session)
    options = state[f"{stage}_options"]
    if stage == "wood":
        labels = [option["name"] if isinstance(option, dict) else option for option in options]
        details = [
            (
                f"{option['name']}——{option['description']}"
                + (f"\n　奥利凡德低声补充：{option['connection']}" if option.get("connection") else "")
                if isinstance(option, dict)
                else option
            )
            for option in options
        ]
    else:
        labels = options
        details = []
    meta = wands.STAGE_META[stage]
    return {
        "done": False,
        "needs_wand": True,
        "step": f"wand_{stage}",
        "wand_stage": stage,
        "wand_title": meta["title"],
        "wand_prompt": meta["prompt"],
        "reaction": reaction,
        "house": session["pending_house"],
        # 序号统一由 _build_keyboard 加，这里只给纯标签，避免出现「1. 1. 冬青木」
        "options": list(labels),
        "wand_option_details": details,
        "selected_wood": state.get("wood", ""),
        "selected_core": state.get("core", ""),
        "selected_connection": state.get("wood_connection", ""),
    }


def choose_wand(uid: str, submitted_stage: str, position: int) -> dict:
    session = storage.get_session(uid)
    if not session or session["step"] not in WAND_STEP_STAGE:
        raise SortingError("奥利凡德先生没有在等你。发送「/入学」查看当前入学进度。")
    stage = WAND_STEP_STAGE[session["step"]]
    if submitted_stage != stage:
        raise SortingError("那是上一步留下的旧选择。发送「/入学」回到奥利凡德先生面前。")
    state = _load_wand_state(session)
    options = state[f"{stage}_options"]
    if not 0 <= position < len(options):
        raise SortingError("请从奥利凡德先生这次给出的三个选择中挑选。")

    picked_option = options[position]
    picked = (
        picked_option["name"]
        if stage == "wood" and isinstance(picked_option, dict)
        else picked_option
    )
    if stage == "wood":
        state["wood"] = picked
        if isinstance(picked_option, dict):
            state["wood_connection"] = picked_option.get("connection", "")
        state["core_options"] = wands.generate_options("core")
        storage.update_session(
            uid, step=6, wand_options_json=json.dumps(state, ensure_ascii=False)
        )
        return _wand_step_result(
            storage.get_session(uid), reaction=wands.stage_reaction("wood")
        )
    if stage == "core":
        state["core"] = picked
        state["length_options"] = wands.generate_options("length")
        storage.update_session(
            uid, step=7, wand_options_json=json.dumps(state, ensure_ascii=False)
        )
        return _wand_step_result(
            storage.get_session(uid), reaction=wands.stage_reaction("core")
        )

    wand = {
        "wood": state["wood"],
        "core": state["core"],
        "length": picked,
        "flexibility": wands.choose_flexibility(),
    }
    try:
        result = storage.finalize_enrollment(uid, wand, STARTING_GALLEONS)
    except ValueError as e:
        raise SortingError(str(e)) from e
    day = core_storage.get_current_day()
    full_name = f"{result['name']}·{result['surname']}" if result["surname"] else result["name"]
    return {
        "done": True,
        "player_name": result["name"],
        "full_name": full_name,
        "house": result["house"],
        "wand": result["wand"],
        "wand_desc": wands.describe(result["wand"]),
        "resonance": wands.resonance(),
        "day": day,
        "is_transfer": bool(day and day > 1),
    }


def _resolve_house(scores: dict) -> str:
    if not scores:
        return random.choice(core_storage.HOUSES)
    max_score = max(scores.get(h, 0) for h in core_storage.HOUSES)
    candidates = [h for h in core_storage.HOUSES if scores.get(h, 0) == max_score]
    return random.choice(candidates)
