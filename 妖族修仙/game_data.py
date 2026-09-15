# 境界表与物种数据 —— 纯静态设计数据,不掺业务逻辑

# ── 境界表:蒙昧 → 化形 → 夺相 → 归真,4大境 x 3小阶 ──────────────────────────────
# yao_power_required: 到达该境界所需的累计妖力(吞噬/狩猎/打坐获得)
# 归真·归真 是本表终点,到达后才能尝试"神兽显灵"仪式(见 SPECIES 的 divine_beast)

STAGES = [
    {'index': 0,  'major': '蒙昧境', 'minor': '兽息', 'yao_power_required': 0,
     'desc': '尚是一头懵懂的灵兽,刚刚生出一星灵智,还不能开口人言。'},
    {'index': 1,  'major': '蒙昧境', 'minor': '凝灵', 'yao_power_required': 80,
     'desc': '体内凝出一缕妖丹雏形,开始能听懂人语。'},
    {'index': 2,  'major': '蒙昧境', 'minor': '通性', 'yao_power_required': 200,
     'desc': '心性初开,能简单发声,举止仍带兽性。'},
    {'index': 3,  'major': '化形境', 'minor': '显形', 'yao_power_required': 400,
     'desc': '第一次短暂化出半人形,耳、尾等兽征难以完全隐去,维持时间很短。'},
    {'index': 4,  'major': '化形境', 'minor': '挂相', 'yao_power_required': 650,
     'desc': '半人形能维持数个时辰,但仍需刻意收束心神,人形值消耗较快。'},
    {'index': 5,  'major': '化形境', 'minor': '稳形', 'yao_power_required': 950,
     'desc': '半人形近乎能撑满一整日,但情绪剧烈波动仍会导致当场破功。'},
    {'index': 6,  'major': '夺相境', 'minor': '摄魂', 'yao_power_required': 1300,
     'desc': '借吞噬所得之力,第一次化出完整人形,足以骗过寻常人的眼睛。'},
    {'index': 7,  'major': '夺相境', 'minor': '易容', 'yao_power_required': 1700,
     'desc': '人形愈发精细逼真,连长期相处之人也难看出破绽。'},
    {'index': 8,  'major': '夺相境', 'minor': '定相', 'yao_power_required': 2200,
     'desc': '人形趋于稳定,维持人形值的日常消耗大幅降低。'},
    {'index': 9,  'major': '归真境', 'minor': '蜕变', 'yao_power_required': 2800,
     'desc': '真身开始超脱最初的兽躯轮廓,不再是单纯的"更强的动物"。'},
    {'index': 10, 'major': '归真境', 'minor': '觉醒', 'yao_power_required': 3500,
     'desc': '此前吞噬、克制、放纵的每一次抉择开始显形——妖性与人性,哪一面更重已初见端倪。'},
    {'index': 11, 'major': '归真境', 'minor': '归真', 'yao_power_required': 4500,
     'desc': '立于蜕变前夜,只差一步"归真仪式",最终走向由人性/妖性的积累决定。'},
]

MAX_STAGE_INDEX = len(STAGES) - 1

def stage_by_index(index):
    if index is None:
        index = 0
    index = max(0, min(index, MAX_STAGE_INDEX))
    return STAGES[index]

def stage_display_name(index):
    st = stage_by_index(index)
    return f"{st['major']}·{st['minor']}"

# ── 归真结局分支:歸真·歸真 满境后,依据人性值决定最终形态 ─────────────────────────
# 人性(humanity) 0-100,妖性 = 100 - humanity

ENDING_DIVINE_HUMANITY_MIN = 70   # >= 此值可尝试"神兽显灵"
ENDING_FERAL_HUMANITY_MAX  = 30   # <= 此值会滑向"堕入凶兽"
# 介于两者之间: "隐世人形" —— 永远维持人形,放弃向神兽突破的可能,换取安稳

ENDING_KEYS = ('divine', 'feral', 'hidden')

# ── 七种起始物种,归真境圆满后可尝试突破为对应神兽 ────────────────────────────────

SPECIES = {
    'dog':    {'label': '犬',  'start_desc': '灵犬转世,忠勇机警。',
               'divine_beast': '天犬', 'divine_desc': '司掌天时警讯的上古神犬,可噬日月之光。'},
    'cat':    {'label': '猫',  'start_desc': '灵猫成精,机敏善伏。',
               'divine_beast': '貔貅', 'divine_desc': '吞金纳财、镇煞辟邪的祥瑞神兽。'},
    'rabbit': {'label': '兔',  'start_desc': '玉兔血脉,温顺灵秀。',
               'divine_beast': '玉兔', 'divine_desc': '广寒宫捣药的月中灵兔,与月华相通。'},
    'bird':   {'label': '雀',  'start_desc': '灵雀啼晓,性喜自由。',
               'divine_beast': '朱雀', 'divine_desc': '南方火德之神鸟,浴火而生,司掌重生。'},
    'fox':    {'label': '狐',  'start_desc': '狐族血脉,聪慧善媚。',
               'divine_beast': '九尾天狐', 'divine_desc': '九尾天狐,通晓人心,魅惑与守护一体两面。'},
    'snake':  {'label': '蛇',  'start_desc': '灵蛇修行,蛰伏隐忍。',
               'divine_beast': '应龙', 'divine_desc': '生双翼、御风雨的上古真龙一脉。'},
    'turtle': {'label': '龟',  'start_desc': '灵龟长寿,沉稳内敛。',
               'divine_beast': '玄武', 'divine_desc': '北方水德之神兽,龟蛇合体,司掌岁月与守护。'},
}

SPECIES_ORDER = ['dog', 'cat', 'rabbit', 'bird', 'fox', 'snake', 'turtle']

def species_label(key):
    info = SPECIES.get(key)
    return info['label'] if info else key

# ── 成就(声明式,condition 支持 stage_reached / humanity_at_least / humanity_at_most) ──

ACHIEVEMENTS = [
    {'key': 'awakened', 'name': '灵智初开', 'description': '完成角色创建,踏上化形之路。',
     'condition': {'type': 'stage_reached', 'value': 0}, 'reward': {'yao_power': 20}},
    {'key': 'first_shapeshift', 'name': '半兽初显', 'description': '境界突破至化形境·显形,第一次化出半人形。',
     'condition': {'type': 'stage_reached', 'value': 3}, 'reward': {'yao_power': 50}},
    {'key': 'full_human_form', 'name': '夺相有成', 'description': '境界突破至夺相境·摄魂,首次化出完整人形。',
     'condition': {'type': 'stage_reached', 'value': 6}, 'reward': {'yao_power': 100}},
    {'key': 'threshold_of_truth', 'name': '归真在望', 'description': '境界突破至归真境·蜕变,真身开始超脱兽躯。',
     'condition': {'type': 'stage_reached', 'value': 9}, 'reward': {'yao_power': 150}},
    {'key': 'compassionate', 'name': '心存善念', 'description': '人性值达到 80 以上。',
     'condition': {'type': 'humanity_at_least', 'value': 80}, 'reward': {'yao_power': 30}},
    {'key': 'feral_drift', 'name': '兽性渐盛', 'description': '人性值跌至 20 以下,妖性开始压过人性。',
     'condition': {'type': 'humanity_at_most', 'value': 20}, 'reward': {'yao_power': 30}},
]
