"""咒语目录：三门实操课各自的咒语清单，按列表顺序依次学习。

上课攒进度，每 LESSONS_PER_SPELL 次课学会一个。学会是永久的，不受学年经验衰减影响——
放个假不会忘掉怎么挥魔杖。年级不够的咒语会被跳过，等到年级够了再回头学。

category：
  attack/defence/control/blast —— 决斗四系，参与克制循环
  ace —— 王牌咒，无视克制，每场限一次
  utility —— 非战斗咒，有各自的实际用途或者纯收藏
"""

LESSONS_PER_SPELL = 2
SPELL_SUBJECTS = ("charms", "defence", "transfiguration")

# (key, 中文名, 原文名, 学科, 最低年级, category, 说明)
SPELLS: list[tuple[str, str, str, str, int, str, str]] = [
    # ── 魔咒学：控制系 + 大部分生活咒 ──
    ("wingardium", "悬浮咒", "Wingardium Leviosa", "charms", 1, "utility", "让东西飘起来。第一节魔咒课的经典项目。"),
    ("lumos", "荧光闪烁", "Lumos", "charms", 1, "utility", "杖尖发光。禁林探险时能看清路，降低遇险概率。"),
    ("scourgify", "清理一新", "Scourgify", "charms", 2, "utility", "清除污渍——也包括别人给你下的恶作剧。"),
    ("expelliarmus", "除你武器", "Expelliarmus", "charms", 2, "control", "缴械咒。决斗场上最实用的一招。"),
    ("reparo", "修复如初", "Reparo", "charms", 3, "utility", "修复损坏的东西，包括打坏的扫帚。"),
    ("alohomora", "阿拉霍洞开", "Alohomora", "charms", 3, "utility", "开锁咒。用途你懂的。"),
    ("petrificus", "统统石化", "Petrificus Totalus", "charms", 4, "control", "全身束缚咒，命中后能封锁对方下一回合的一系咒语。"),
    ("muffliato", "闭耳塞听", "Muffliato", "charms", 6, "utility", "让旁人听不见你说话。混血王子的小发明。"),
    # ── 黑魔法防御术：攻击系 + 防御系 + 王牌 ──
    ("protego", "盔甲护身", "Protego", "defence", 1, "defence", "基础护盾，能挡下正面攻击。"),
    ("stupefy", "昏昏倒地", "Stupefy", "defence", 2, "attack", "昏迷咒。决斗里最标准的攻击手段。"),
    ("impedimenta", "障碍重重", "Impedimenta", "defence", 3, "attack", "阻碍咒，减缓对方动作。"),
    ("protego_maxima", "大盾咒", "Protego Maxima", "defence", 4, "defence", "强化护盾，格挡的同时反弹一点消耗给对方。"),
    ("expecto_patronum", "呼神护卫", "Expecto Patronum", "defence", 5, "ace", "守护神咒。无视克制关系，每场决斗限用一次。"),
    ("sectumsempra", "神锋无影", "Sectumsempra", "defence", 6, "attack", "混血王子的禁咒，威力极大，但用出来是要担风险的。"),
    # ── 变形术：强击系 + 变形类 ──
    ("diffindo", "四分五裂", "Diffindo", "transfiguration", 1, "utility", "切割咒。课堂上用来裁东西，打架也不是不行。"),
    ("vera_verto", "变形咒", "Vera Verto", "transfiguration", 2, "utility", "把动物变成水杯。经典的课堂项目。"),
    ("reducto", "炸炸胀", "Reducto", "transfiguration", 3, "blast", "粉碎咒。能直接炸穿护盾。"),
    ("evanesco", "消隐无踪", "Evanesco", "transfiguration", 4, "utility", "让东西彻底消失。考试常考。"),
    ("confringo", "惊爆咒", "Confringo", "transfiguration", 5, "blast", "爆炸咒，命中后让对方之后的咒语都更费力。"),
    ("avifors", "飞鸟群群", "Avifors", "transfiguration", 6, "blast", "变出一群鸟扑向对手，防不胜防。"),
    # ── 禁林专属：课上学不到，只能在禁林里打赢对应的怪之后学会 ──
    ("arania_exumai", "蛛网速速禁锢", "Arania Exumai", "forest", 0, "blast", "驱散蛛群的咒语。第一次打退阿拉戈克的族群时学会。"),
    ("riddikulus", "滑稽滑稽", "Riddikulus", "forest", 0, "control", "把恐惧变成笑料。第一次战胜博格特时学会。"),
    ("incarcerous", "速速禁锢", "Incarcerous", "forest", 0, "control", "凭空变出绳索捆住对手。第一次放倒巨怪时学会。"),
    ("homorphus", "人形显身", "Homorphus", "forest", 0, "defence", "让变形的东西现出人形。第一次逼退狼人时学会。"),
    (
        "corporeal_patronus",
        "实体守护神",
        "Corporeal Patronus",
        "forest",
        0,
        "ace",
        "完全成形的守护神。在禁林最深处驱散摄魂怪之后才真正掌握。",
    ),
]

FOREST_SUBJECT = "forest"  # 这个"学科"不在课程表里，只有禁林能教

SPELLS_BY_KEY = {s[0]: s for s in SPELLS}
SPELLS_BY_NAME = {s[1]: s for s in SPELLS}

# ======================== 决斗数值 ========================
# 四系循环相克：攻击→控制→强击→防御→攻击。顺序出招时，如果你这一发克制对手
# 上一发出的咒语，就吃到克制加成——所以"读对手上一步想干什么"是有意义的。
COUNTERS = {
    "attack": "control",
    "control": "blast",
    "blast": "defence",
    "defence": "attack",
}
COUNTER_DAMAGE_BONUS = 1.5  # 克制成功时伤害/护盾的倍率

DUEL_HP = 100
DUEL_ROUNDS = 5
DUEL_MIN_GRADE = 3  # 三年级开放决斗俱乐部
DUEL_STAMINA_COST = 6
DUEL_DAILY_INITIATE_LIMIT = 3  # 每人每天最多主动发起3次
DUEL_DAILY_RECEIVE_LIMIT = 3  # 每人每天最多被发起3次，免得被人追着打
DUEL_WIN_HOUSE_POINTS = 3  # 比魁地奇(15)低不少，决斗轻量、次数多，不能变成刷分捷径
DUEL_WIN_SUBJECT_EXP = 6
DUEL_LOSE_SUBJECT_EXP = 2  # 输了只是拿得少，不倒扣，也不扣学院分

# spell_key -> {damage, cooldown, shield, lock}
#   damage：直接伤害
#   shield：给自己挂的护盾，抵挡对方下一发的伤害
#   lock：命中后封锁对方下一回合的某一系（控制系专属）
#   cooldown：用完之后要等几个回合才能再用
COMBAT = {
    # 攻击系
    "stupefy": {"damage": 18, "cooldown": 1},
    "impedimenta": {"damage": 14, "cooldown": 1, "lock": "blast"},
    "sectumsempra": {"damage": 32, "cooldown": 3},
    # 防御系
    "protego": {"damage": 0, "shield": 16, "cooldown": 1},
    "protego_maxima": {"damage": 6, "shield": 26, "cooldown": 2},
    # 控制系
    "expelliarmus": {"damage": 12, "cooldown": 1, "lock": "attack"},
    "petrificus": {"damage": 16, "cooldown": 2, "lock": "any"},
    # 强击系
    "reducto": {"damage": 22, "cooldown": 2, "pierce": True},
    "confringo": {"damage": 28, "cooldown": 3, "pierce": True},
    "avifors": {"damage": 24, "cooldown": 2},
    # 王牌：无视克制关系和护盾，每场限一次
    "expecto_patronum": {"damage": 40, "cooldown": 99, "pierce": True, "once": True},
    # 禁林专属
    "arania_exumai": {"damage": 24, "cooldown": 2, "pierce": True},
    "riddikulus": {"damage": 14, "cooldown": 2, "lock": "any"},
    "incarcerous": {"damage": 18, "cooldown": 2, "lock": "attack"},
    "homorphus": {"damage": 4, "shield": 30, "cooldown": 2},
    "corporeal_patronus": {"damage": 48, "cooldown": 99, "pierce": True, "once": True},
}
COMBAT_CATEGORIES = ("attack", "defence", "control", "blast", "ace")


def combat_spells_of(learned_keys) -> list[tuple]:
    """玩家学过的、能在决斗里用的咒语。"""
    return [s for s in SPELLS if s[0] in learned_keys and s[5] in COMBAT_CATEGORIES]


def find(name_or_key: str):
    return SPELLS_BY_KEY.get(name_or_key) or SPELLS_BY_NAME.get(name_or_key)


def spells_of_subject(subject: str) -> list[tuple]:
    """按目录顺序返回该科的咒语清单，这个顺序就是学习顺序。"""
    return [s for s in SPELLS if s[3] == subject]
