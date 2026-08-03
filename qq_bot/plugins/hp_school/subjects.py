"""学科清单：5门必修（一年级起）+ 4门选修（三年级起解锁）。

key 用于数据库存储和决斗/商店等系统的联动判断，不要改；name 是展示用的中文名。
"""

# (key, name, unlock_grade, 类别)
SUBJECTS: list[tuple[str, str, int, str]] = [
    ("defence", "黑魔法防御术", 1, "必修"),
    ("charms", "魔咒学", 1, "必修"),
    ("transfiguration", "变形术", 1, "必修"),
    ("potions", "魔药学", 1, "必修"),
    ("herbology", "草药学", 1, "必修"),
    ("flying", "飞行课", 2, "选修"),
    ("care_of_magical_creatures", "保护神奇动物学", 3, "选修"),
    ("divination", "占卜学", 3, "选修"),
    ("ancient_runes", "古代符文学", 3, "选修"),
    ("muggle_studies", "麻瓜研究", 3, "选修"),
]

SUBJECTS_BY_KEY = {key: (name, unlock_grade, category) for key, name, unlock_grade, category in SUBJECTS}
SUBJECTS_BY_NAME = {name: (key, unlock_grade, category) for key, name, unlock_grade, category in SUBJECTS}


def find(name_or_key: str) -> tuple[str, str, int, str] | None:
    """按学科名或key查找，找不到返回None。"""
    if name_or_key in SUBJECTS_BY_KEY:
        name, unlock_grade, category = SUBJECTS_BY_KEY[name_or_key]
        return name_or_key, name, unlock_grade, category
    if name_or_key in SUBJECTS_BY_NAME:
        key, unlock_grade, category = SUBJECTS_BY_NAME[name_or_key]
        return key, name_or_key, unlock_grade, category
    return None
