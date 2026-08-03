"""禁林的怪物、层数、战利品。

怪物不是盲选出招——每种怪有自己的出招偏好（weights），打多了就能摸出规律，
用克制关系针对它。这是"越了解越强"，不是拼运气。

teaches：第一次打赢这种怪时学会的咒语（禁林专属，课上学不到）。
"""

# 每层的战利品基数，越深越多
GALLEON_PER_DEPTH = 12
EXP_PER_DEPTH = 5

MATERIALS = [
    # (item_key, 名字, 卖出价, 最低出现深度)
    ("mat_knotgrass", "结节草", 6, 1),
    ("mat_leech", "水蛭", 8, 1),
    ("mat_flobberworm", "弗洛伯毛虫黏液", 10, 2),
    ("mat_lacewing", "草蛉", 14, 3),
    ("mat_boomslang", "非洲树蛇皮", 22, 4),
    ("mat_unicorn_hair", "独角兽毛", 30, 5),
    ("mat_acromantula_venom", "八眼巨蛛毒液", 45, 6),
    ("mat_bicorn_horn", "双角兽角粉", 60, 7),
    ("mat_dementor_frost", "摄魂怪的寒霜", 90, 9),
]
MATERIALS_BY_KEY = {m[0]: m for m in MATERIALS}
MATERIALS_BY_NAME = {m[1]: m for m in MATERIALS}

# (key, 名字, 最低深度, 最高深度, HP, 出招偏好, 解锁年级, 第一次打赢学会的咒语, 描述)
MONSTERS = [
    (
        "acromantula",
        "阿拉戈克的族群",
        1,
        2,
        60,
        {"control": 0.4, "attack": 0.45, "defence": 0.15},
        2,
        "arania_exumai",
        "成群的八眼巨蛛从树影里挤出来，蛛丝先到，蛛腿后到。",
    ),
    (
        "boggart",
        "博格特",
        3,
        4,
        85,
        {"attack": 0.25, "control": 0.25, "blast": 0.25, "defence": 0.25},
        3,
        "riddikulus",
        "它变成了你最怕的样子——每一次都不一样，所以永远猜不准下一发是什么。",
    ),
    (
        "troll",
        "山怪",
        5,
        6,
        120,
        {"blast": 0.6, "attack": 0.35, "defence": 0.05},
        4,
        "incarcerous",
        "十二英尺高，抡起木棒的时候连地面都在抖。血厚，耐打，笨。",
    ),
    (
        "werewolf",
        "狼人",
        7,
        8,
        110,
        {"attack": 0.7, "blast": 0.2, "control": 0.1},
        5,
        "homorphus",
        "月光下它抬起头。速度快得离谱，招招都是硬碰硬。",
    ),
    (
        "dementor",
        "摄魂怪",
        9,
        9,
        150,
        {"control": 0.5, "attack": 0.5},
        6,
        "corporeal_patronus",
        "空气一下子冷了下来。你听见了这辈子最不想再听一次的声音。",
    ),
]
MONSTERS_BY_KEY = {m[0]: m for m in MONSTERS}

MAX_DEPTH = 9
DEMENTOR_KEY = "dementor"
# 摄魂怪只怕守护神：其余咒语对它的伤害要打这个折扣
DEMENTOR_RESIST = 0.25
PATRONUS_KEYS = ("expecto_patronum", "corporeal_patronus")


def monster_for_depth(depth: int):
    for m in MONSTERS:
        if m[2] <= depth <= m[3]:
            return m
    return MONSTERS[-1]


def materials_for_depth(depth: int) -> list:
    return [m for m in MATERIALS if m[3] <= depth]


def find_material(name_or_key: str):
    return MATERIALS_BY_KEY.get(name_or_key) or MATERIALS_BY_NAME.get(name_or_key)
