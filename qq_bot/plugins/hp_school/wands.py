"""奥利凡德魔杖目录。选杖按木材→杖芯→长度三步进行。"""

import random

WOODS = (
    "冬青木", "葡萄藤木", "山楂木", "柳木", "紫杉木", "榆木",
    "樱桃木", "黑胡桃木", "白蜡木", "柏木", "红橡木", "月桂木",
)
CORES = ("凤凰尾羽", "独角兽尾毛", "龙的心弦", "雷鸟尾羽", "夜骐尾毛")
LENGTHS = ("九又四分之三英寸", "十英寸", "十又四分之一英寸", "十一英寸", "十一又二分之一英寸", "十二英寸")
FLEXIBILITIES = ("柔韧", "相当有弹性", "略有弹性", "坚硬", "不易弯曲")

# description 是奥利凡德公开讲出的木材性情；signals 用于把问卷答案与木材暗中配对。
WOOD_PROFILES = {
    "冬青木": {
        "description": "偏爱身处险境仍愿意保护他人的巫师，也常与需要克服怒火与冲动的人相伴。",
        "houses": ("格兰芬多",),
        "signals": ("傲罗", "嫉恶如仇", "讲义气", "黑魔法防御", "决斗", "敢想敢做"),
    },
    "葡萄藤木": {
        "description": "目光长远，追求更高目标；它选择的主人往往能看见别人忽略的可能。",
        "houses": ("拉文克劳",),
        "signals": ("学者", "看书", "钻研", "魔法史", "古老传说", "天马行空"),
    },
    "山楂木": {
        "description": "最理解内心矛盾的人，尤其适合外表与真正性情并不完全相同的巫师。",
        "houses": ("斯莱特林", "赫奇帕奇"),
        "signals": ("嘴硬心软", "表面冷漠", "完美主义", "混血", "不太合群"),
    },
    "柳木": {
        "description": "有治疗与守护的天性，却常被那些低估自己、仍有潜力尚未发现的人吸引。",
        "houses": ("赫奇帕奇",),
        "signals": ("治疗师", "温柔耐心", "照顾人", "乐于助人", "神奇动物", "花草"),
    },
    "紫杉木": {
        "description": "极其罕见而强大，从不选择平庸的主人；它既可能追随守护者，也可能追随危险人物。",
        "houses": ("斯莱特林",),
        "signals": ("黑魔法", "野心勃勃", "孤儿院", "禁忌", "城府很深", "独来独往"),
    },
    "榆木": {
        "description": "偏爱举止从容、判断准确且富有魔法天赋的人，不喜欢慌乱和无谓的失误。",
        "houses": ("拉文克劳", "斯莱特林"),
        "signals": ("逻辑至上", "完美主义", "魔法部", "精打细算", "规矩不能破"),
    },
    "樱桃木": {
        "description": "拥有不容小觑的力量，常选择意志坚定、敢于承担后果的巫师。",
        "houses": ("格兰芬多",),
        "signals": ("争强好胜", "敢想敢做", "魁地奇", "决斗", "爱出风头"),
    },
    "黑胡桃木": {
        "description": "最适合洞察敏锐而诚实面对自己的人；若主人自欺，它便很难发挥力量。",
        "houses": ("拉文克劳", "斯莱特林"),
        "signals": ("观察力", "谨慎多疑", "城府", "逻辑", "记者", "小道消息"),
    },
    "白蜡木": {
        "description": "忠于最初选择的主人，青睐固执、勇敢且不会轻易改变信念的人。",
        "houses": ("格兰芬多",),
        "signals": ("固执", "讲原则", "讲义气", "傲罗", "不服输"),
    },
    "柏木": {
        "description": "与勇气有关，但不是鲁莽；它偏爱愿意牺牲自己、在危急时刻挺身而出的人。",
        "houses": ("格兰芬多", "赫奇帕奇"),
        "signals": ("乐于助人", "嫉恶如仇", "照顾人", "单亲", "祖父母", "孤儿院"),
    },
    "红橡木": {
        "description": "反应敏锐，适合思维与动作同样迅速、喜欢临场发挥的巫师。",
        "houses": ("格兰芬多", "拉文克劳"),
        "signals": ("好奇心", "社交", "巡演团", "四处游历", "恶作剧", "看心情"),
    },
    "月桂木": {
        "description": "无法忍受懒惰，却会回应光荣、进取与成就欲，也很难被主人以外的人驯服。",
        "houses": ("斯莱特林",),
        "signals": ("目标明确", "野心", "要职", "家境优渥", "效率", "收藏稀有"),
    },
}

RESONANCE = (
    "杖尖迸出一串温暖的金色火花，橱柜里的盒子轻轻震了一下。",
    "一阵风卷过狭窄的店堂，悬在半空的卷尺像蛇一样缩回角落。",
    "魔杖在你掌心微微发热，远处传来玻璃风铃清脆的一响。",
    "一道银白色光弧掠过天花板，奥利凡德先生的眼睛顿时亮了起来。",
)


def generate_options(stage: str, count: int = 3) -> list[str]:
    pools = {"wood": WOODS, "core": CORES, "length": LENGTHS}
    return random.sample(pools[stage], count)


def generate_wood_options(answers: dict, house: str, count: int = 3) -> list[dict]:
    """至少给出一根与问卷明显呼应的木材，其余保留奥利凡德式的不确定性。"""
    answer_values = [str(value) for value in answers.values()]
    scored = []
    for wood, profile in WOOD_PROFILES.items():
        matched_answer = next(
            (
                answer
                for answer in answer_values
                if any(signal in answer for signal in profile["signals"])
            ),
            "",
        )
        score = (3 if matched_answer else 0) + (1 if house in profile["houses"] else 0)
        scored.append((score, random.random(), wood, matched_answer))
    scored.sort(reverse=True)
    best_score = scored[0][0]
    best_pool = [row for row in scored if row[0] == best_score]
    chosen_best = random.choice(best_pool)
    remaining = [row for row in scored if row[2] != chosen_best[2]]
    chosen = [chosen_best, *random.sample(remaining, count - 1)]
    random.shuffle(chosen)

    result = []
    for score, _, wood, matched_answer in chosen:
        profile = WOOD_PROFILES[wood]
        if matched_answer:
            connection = (
                f"你先前说过自己“{matched_answer}”。{wood}通常不会忽略这样的性情。"
            )
        elif house in profile["houses"]:
            connection = (
                f"分院帽在你身上看见了{house}的特质，而{wood}也常回应同样的东西。"
            )
        else:
            connection = "不过魔杖有时会看见连主人自己都尚未发现的一面。"
        result.append(
            {
                "name": wood,
                "description": profile["description"],
                "connection": connection,
            }
        )
    return result


def choose_flexibility() -> str:
    return random.choice(FLEXIBILITIES)


def describe(wand: dict) -> str:
    return f"{wand['wood']}，{wand['core']}，{wand['length']}，{wand['flexibility']}"


def resonance() -> str:
    return random.choice(RESONANCE)


STAGE_META = {
    "wood": {
        "title": "第一步 · 木材",
        "prompt": "“先听听木材的声音。别只用眼睛看——哪一种让你觉得熟悉？”",
    },
    "core": {
        "title": "第二步 · 杖芯",
        "prompt": "“很好。现在是杖芯，它决定魔杖最深处的性情。把手放近些。”",
    },
    "length": {
        "title": "第三步 · 长度",
        "prompt": "卷尺绕着你的手臂和肩膀飞了一圈。“最后是长度。试着挥动一下，看看哪根最顺手。”",
    },
}

STAGE_REACTIONS = {
    "wood": (
        "奥利凡德用银白色的手指敲了敲木材，侧耳听着回声。“有反应……我们继续。”",
        "木片在你掌心轻轻震了一下。奥利凡德若有所思地眯起眼睛。",
        "附近一排魔杖盒无风自动，发出细碎的沙沙声。“这就对了。”",
    ),
    "core": (
        "杖芯靠近木材时闪过一点微光，像是在彼此试探。",
        "奥利凡德屏住呼吸，将杖芯缓缓嵌入。“非常特别的组合。”",
        "一股暖意沿着指尖掠过。奥利凡德轻声说：“它开始认识你了。”",
    ),
}


def stage_reaction(stage: str) -> str:
    return random.choice(STAGE_REACTIONS[stage])
