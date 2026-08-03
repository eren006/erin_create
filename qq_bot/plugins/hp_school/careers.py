"""毕业职业选择：根据 N.E.W.T.、魁地奇经历判断资格并给出推荐。"""

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import storage, subjects

BAND_RANK = {"T": 0, "D": 1, "P": 2, "A": 3, "E": 4, "O": 5}

# key: (名称, 签约金, 简介)
CAREERS = {
    "auror": ("傲罗", 160, "进入魔法法律执行司，追捕危险的黑巫师。"),
    "healer": ("圣芒戈治疗师", 140, "在魔法伤病科救治被咒语与魔法生物伤害的人。"),
    "professor": ("霍格沃茨教授", 120, "留在城堡传授知识，也要处理学生制造的各种事故。"),
    "wandmaker": ("魔杖制作师", 150, "研究木材、杖芯与巫师之间难以解释的联系。"),
    "magizoologist": ("神奇动物学家", 130, "前往世界各地观察、保护和记录神奇动物。"),
    "quidditch": ("职业魁地奇球员", 180, "加入职业球队，让看台再次高喊你的名字。"),
    "ministry": ("魔法部职员", 110, "在魔法部开始职业生涯，处理永远批不完的羊皮纸。"),
    "reporter": ("《预言家日报》记者", 100, "追踪魔法界新闻，并努力让标题比事实更加醒目。"),
}


class CareerError(Exception):
    pass


def _exam_bands(uid: str) -> dict[str, str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT subject, band FROM exam_results WHERE uid=? AND grade=7", (uid,)
        ).fetchall()
        return {row["subject"]: row["band"] for row in rows}
    finally:
        conn.close()


def _at_least(bands: dict, subject: str, target: str) -> bool:
    return BAND_RANK.get(bands.get(subject, "T"), 0) >= BAND_RANK[target]


def qualification(uid: str, key: str) -> tuple[bool, str]:
    bands = _exam_bands(uid)
    if not bands:
        return False, "尚未完成N.E.W.T."
    if key == "auror":
        return _at_least(bands, "defence", "E"), "黑魔法防御术N.E.W.T.至少E"
    if key == "healer":
        ok = _at_least(bands, "potions", "A") and _at_least(bands, "herbology", "A")
        return ok, "魔药学、草药学N.E.W.T.至少A"
    if key == "professor":
        return any(band == "O" for band in bands.values()), "任意一门N.E.W.T.取得O"
    if key == "wandmaker":
        ok = _at_least(bands, "charms", "A") and _at_least(bands, "transfiguration", "A")
        return ok, "魔咒学、变形术N.E.W.T.至少A"
    if key == "magizoologist":
        return _at_least(bands, "care_of_magical_creatures", "A"), "保护神奇动物学至少A"
    if key == "quidditch":
        conn = get_conn()
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quidditch_players'"
            ).fetchone()
            row = (
                conn.execute(
                    "SELECT 1 FROM quidditch_players WHERE uid=? AND position!=''", (uid,)
                ).fetchone()
                if exists
                else None
            )
            return row is not None, "拥有霍格沃茨魁地奇球队经历"
        finally:
            conn.close()
    if key == "ministry":
        return True, "完成N.E.W.T."
    return True, "完成N.E.W.T.并愿意追踪新闻"


def list_options(uid: str) -> list[dict]:
    result = []
    for key, (name, bonus, desc) in CAREERS.items():
        qualified, requirement = qualification(uid, key)
        result.append(
            {
                "key": key, "name": name, "bonus": bonus, "desc": desc,
                "qualified": qualified, "requirement": requirement,
            }
        )
    return result


def choose(uid: str, career_input: str) -> dict:
    player = core_storage.get_player(uid)
    if not player or not player["house"]:
        raise CareerError("你还没有完成入学手续。")
    existing = storage.get_career(uid)
    if existing:
        raise CareerError(f"你的职业已经登记为「{CAREERS[existing['career_key']][0]}」，不能重新选择。")
    key = next(
        (key for key, value in CAREERS.items() if career_input in (key, value[0])), None
    )
    if not key:
        raise CareerError("没有这个职业，发送「/职业列表」查看可选方向。")
    qualified, requirement = qualification(uid, key)
    if not qualified:
        raise CareerError(f"你暂时不符合「{CAREERS[key][0]}」的要求：{requirement}。")
    name, bonus, desc = CAREERS[key]
    if not storage.choose_career_atomic(uid, key, bonus):
        raise CareerError("职业已经登记过了，不能重复选择。")
    return {"key": key, "name": name, "bonus": bonus, "desc": desc}


def get(uid: str) -> dict | None:
    row = storage.get_career(uid)
    if not row:
        return None
    name, bonus, desc = CAREERS[row["career_key"]]
    return {"key": row["career_key"], "name": name, "bonus": row["signing_bonus"], "desc": desc}
