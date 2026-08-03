import os, random, time, sqlite3, math
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session as S, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "modaya2_secret_2026")
app.permanent_session_lifetime = timedelta(days=30)

DB_PATH = os.path.join(os.path.dirname(__file__), "modaya2.db")
now_ts = lambda: int(time.time())
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")

# ── 数值配置(全部对应 数值设计.md,改平衡直接改这里)────────────────────────────

DAY_SECONDS = 3600
DAY_RATIO = 0.7
NIGHT_SECONDS = int(DAY_SECONDS * (1 - DAY_RATIO))
NEWBIE_PROTECTION_SECONDS = DAY_SECONDS * 2
MAX_RESPAWNS = 3
STAT_CAP = 20
STAT_GROWTH_CHANCE = 0.08
LEVEL_CAP = 30
PERSONAL_STORAGE_BASE = 150

AVATAR_OPTIONS = {
    "avatar-01": "冷静侦察者",
    "avatar-02": "沉默工程师",
    "avatar-03": "暮色游侠",
    "avatar-04": "黑夜联络员",
    "avatar-05": "冷艳研究员",
    "avatar-06": "暖阳医护",
    "avatar-07": "克制外科医",
    "avatar-08": "不羁领航员",
}
_BACKGROUND_ORIGINS = [
    ("从诊所长大的照顾者", "一间总有消毒水味的小诊所楼上", "你很早就学会分辨疼痛、恐惧和真正的危险", "遇到混乱时反而会安静下来，习惯先照顾最需要帮助的人", "判断伤势并在有限条件下处理创口", "一只缺角的旧听诊器"),
    ("被火场塑造的守护者", "工厂区一排拥挤的家属楼里", "警报、夜班和邻里互助构成了你的童年", "你是那种明知危险仍会回头确认有没有人掉队的人", "观察建筑结构、寻找出口并组织撤离", "一枚被烟熏黑的旧臂章"),
    ("习惯追问真相的观察者", "治安混乱的旧城区", "你从小就知道表面说法和真实发生的事往往不同", "你不轻易相信别人，却会为自己认定的人追查到底", "从脚印、物品位置和言语矛盾中还原经过", "一本写满坐标和疑问的硬皮册"),
    ("替别人记住故事的记录者", "车站附近一间狭小的出租屋", "来往旅客的离别与重逢让你对陌生人的人生充满好奇", "你是愿意倾听的人，也害怕有人死去后连名字都不再被提起", "整理信息、记录证词并从零碎消息中找到联系", "一支电量时好时坏的录音笔"),
    ("相信土地仍会回应的耕作者", "远离城区的农田与防风林之间", "四季、歉收和重复劳作教会你耐心比运气更可靠", "你看起来沉默固执，却总会悄悄把更好的那份食物留给别人", "辨认种子、保存食物并让贫瘠土地重新产出", "一只装着旧种子的黄铜盒"),
    ("把废物重新变成工具的修理者", "铁路和维修厂包围的工人社区", "你小时候最喜欢拆开坏掉的东西，再想办法把它装回去", "你不擅长安慰人，但相信认真修好一盏灯也算一种承诺", "拼装机械、恢复供电并判断设备还能坚持多久", "一把磨得发亮的旧扳手"),
    ("总想走到地图之外的远行者", "靠近山林的偏远小镇", "雾、岔路和漫长的独处让你很早就拥有自己的方向感", "你喜欢观察胜过说话，对未知保持好奇，也懂得何时撤退", "根据天气、地形和动物痕迹寻找安全路线", "一台装着最后一卷胶片的相机"),
    ("用一顿饭维系生活的人", "一间前店后家的小饭馆里", "你在油烟、碗筷声和不同客人的口味中长大", "你相信人在最狼狈的时候也应该吃上一口热的，因此很少让身边的人空着肚子", "分配食材、保存余粮并用有限材料做出像样的饭", "一本沾着油渍的家常菜谱"),
    ("在旧知识里寻找答案的教书人", "书多得放不下的普通家庭", "阅读和争论是你从小习惯的生活方式", "你耐心、克制，有时过分相信道理，但从不会放弃教会别人如何自己判断", "整理知识、解释复杂问题并设计容易记住的计划", "一叠写满批注的旧讲义"),
    ("把身体练成最后依靠的行动者", "公共体育场旁的普通住宅区", "清晨训练、失败和伤病几乎贯穿了你的成长", "你好胜却不轻视弱者，真正危急时往往会主动承担最累的那一段路", "长距离移动、控制体力并在极限下保持动作稳定", "一枚没有机会正式领取的完赛牌"),
]
_BACKGROUND_INCIDENTS = [
    ("没等到的人", "灾变发生时，你赶到撤离站等待一个对你很重要的人，直到最后一辆车离开也没有等到", "你只在空座位下找到一件属于对方的小东西，从此无法确认那个人究竟死去、迷路还是先一步离开", "你拒绝把失踪当成死亡，之后每到一个聚居地都会查看名单和留言", "漫长等待让你害怕再次对人作出承诺", "北辰可能保存着更完整的撤离记录，这是你继续赶路的理由"),
    ("封锁楼里的第一夜", "灾变后的第一夜，你与一群互不相识的人被困在封锁建筑的高层", "恐慌让人们争抢出口，而你第一次发现活人也可能比门外的怪物更危险", "你帮助仍愿意合作的人找到维护通道，并在天亮前一起离开", "那一夜让你不再轻易相信群体，却仍本能地保护弱小者", "有人交给你一张残缺的北辰频率表，像是一份没有说出口的托付"),
    ("走过半座死城", "最初的临时据点失守后，你靠双脚穿过了半座城市", "与你同行的人一个个因为受伤、争执或选择不同道路而离开，最后只剩你独自抵达城外", "你把沿途安全地点画成简陋地图，也开始习惯在每个路口准备第二条退路", "独行让你变得可靠，也让你很难主动依赖别人", "地图最远处标着一座北辰中继塔，你一直想亲眼确认它是否还在工作"),
    ("听见无人回应的广播", "你曾在废弃设备旁连续守了十七个夜晚，只为听清一段重复出现的广播", "广播没有姓名，只播报天气、坐标和一句不要放弃，随后在某个夜晚突然中断", "你记录下所有杂音和停顿，逐渐学会从信号变化判断远方是否还有人活动", "你害怕希望只是自动设备留下的循环，却更害怕从未追过去", "那组坐标属于北辰线路，因此你把寻找信号源当成自己的长期目标"),
    ("在地下活过七天", "尸群经过城区时，你和几名陌生人在没有照明的地下空间躲了七天", "食物逐渐见底后，每一次分配都暴露出人的自私、善意和恐惧", "你坚持留下最后一份水给病人，也因此第一次差点饿死", "从那以后你会储藏物资，却厌恶只顾自己活下去的选择", "离开前，有人在墙上刻下北辰仍亮着灯；你不知道真假，但一直记得"),
    ("断桥另一边", "撤离途中，唯一能离开城区的桥在你身后坍塌", "你活了下来，却与桥另一边所有熟悉的人彻底失去联系", "你曾试着沿河寻找回去的路，最终不得不承认当时的自己没有能力跨越尸群", "无法回头成为你最深的遗憾，也让你总想为别人保留一条退路", "最后收到的模糊无线电只提到北辰，你希望那里能找到另一侧幸存者的消息"),
    ("暴雨里的陌生人", "一个暴雨夜，你冒险进入翻覆车辆救出了一名完全陌生的伤员", "体力耗尽后你短暂失去意识，醒来时对方已经离开，没有姓名，也没有解释", "对方只留下一枚通往旧设施的钥匙，证明那场救援并非幻觉", "你因此相信善意未必会得到答案，但仍可能在陌生人之间传递", "钥匙属于北辰地下设施，你想知道获救的人为何拥有它"),
    ("只带走一样东西", "救援仓库发生火灾时，你只能在物资和私人纪念物之间选择一样带走", "你选择了那件记录过去的东西，药品、名单和其他人的希望则被火吞没", "此后你开始反复怀疑当时的选择，也更加执着于提前准备和整理物资", "你珍惜旧日记忆，却害怕这种珍惜有一天再次害死别人", "纪念物中藏着一个北辰徽记，像是在提醒你过去仍有尚未读懂的部分"),
    ("没有地图的冬天", "第一个冬天，你被大雪困在一个地图上找不到的荒村", "那里没有可靠电力，安静的空房里却藏着疾病、饥饿和没有离开的感染者", "你靠拆家具、存雪水和观察烟囱熬到开春，也学会独自埋葬死者", "这个冬天让你能忍受孤独，却开始害怕毫无声音的房间", "废弃车站里留着一张北辰方向的旧车票，你把它保存至今"),
    ("替两个人守到黎明", "你曾与一个最重要的人约定轮流守夜，等待远处每隔九秒出现一次的微光", "一次外出之后，对方再也没有回来，你不知道那是死亡、背叛还是不得已的失散", "你仍按照约定替两个人守完了那一夜，并从此保留一个空着的位置", "你很难重新接受亲密关系，因为害怕又一次独自完成共同的约定", "你相信那束规律的光来自北辰，也相信失散的人可能曾向那里前进"),
]
CHARACTER_BACKGROUNDS = {}
for _oi, (_origin, _birth, _upbringing, _nature, _skill, _keepsake) in enumerate(_BACKGROUND_ORIGINS):
    for _ii, (_incident, _event, _loss, _choice, _wound, _goal) in enumerate(_BACKGROUND_INCIDENTS):
        _key = f"bg{_oi * 10 + _ii + 1:03d}"
        CHARACTER_BACKGROUNDS[_key] = {
            "name": f"{_origin}｜{_incident}",
            "desc": (
                f"你出生在{_birth}。{_upbringing}。灾变前，你逐渐成为{_origin}：{_nature}，"
                f"同时也擅长{_skill}。{_event}。{_loss}；后来，{_choice}。"
                f"这段经历留下了一个改变你的地方：{_wound}。你如今仍带着{_keepsake}，"
                f"因为{_goal}。"
            ),
        }

CHARACTER_TRAITS = {
    "strong_back": {"name": "💪 强健背脊", "desc": "随身容量+30"},
    "light_foot": {"name": "🪽 脚步轻快", "desc": "移动耗时-10%"},
    "iron_stomach": {"name": "🥤 铁胃", "desc": "喝生水中毒率打7折"},
    "optimist": {"name": "🍀 乐观主义", "desc": "每日手气稀有发现率提高5%"},
    "animal_friend": {"name": "🐾 动物之友", "desc": "每次投喂额外+5好感"},
    "field_medic": {"name": "🩹 战地医护", "desc": "救援送药额外恢复10HP"},
    "homebody": {"name": "🏠 恋家", "desc": "获得庇护所贡献时+20%"},
    "scavenger": {"name": "🎒 拾荒直觉", "desc": "采集时额外物资概率略高"},
    "brave": {"name": "🔥 胆大", "desc": "探索事件成功率+5%"},
    "careful": {"name": "🔍 谨慎", "desc": "遭遇丧尸概率降低8%"},
    "radio_mind": {"name": "📻 无线电迷", "desc": "寻宝掷骰出现1时自动改为2"},
    "community": {"name": "🤝 热心肠", "desc": "完成救援时额外获得5贡献"},
    "night_owl": {"name": "🌙 夜猫子", "desc": "黑夜移动不受天气额外减速"},
    "cook_soul": {"name": "🍲 会过日子", "desc": "熟食食用效果额外+5"},
    "tough": {"name": "🧱 坚韧", "desc": "夜袭受到的伤害略微降低"},
    "storyteller": {"name": "📖 讲故事的人", "desc": "完成支线额外获得2钱包"},
}

RESOURCES = {
    # key: (中文名, 稀有度, 刷新小时数或None=不刷新)
    # 十八节:15人左右的体量下，原来24/144小时的刷新周期供给跟不上消耗，砍到12/36小时；
    # 且刷新不再要求资源点恰好见底(见action_gather对depleted_ts的注释)，隔够时间就回满。
    "wood":       ("🪵 木材", "normal", 12),
    "stone":      ("🪨 石头", "normal", 12),
    "raw_food":   ("🍖 生鲜", "normal", 12),
    "raw_water":  ("💧 生水", "normal", 12),
    "herb":       ("🌿 药草", "normal", 12),
    "cloth":      ("🧵 布/纤维", "normal", 12),
    "metal":      ("⚙️ 金属", "rare", 36),
    "ammo":       ("🔫 弹药", "rare", 36),
    "parts":      ("🔩 机械零件", "rare", 36),
    "silver_scrap": ("🥈 银质废料", "rare", 36),
    "electronics":("💾 电子元件", "landmark", None),
    "old_gem":    ("🔮 旧世界宝石", "landmark", None),
    "resonance_material": ("💎 终局特殊材料", "landmark", None),
}

# 装备/医疗类消耗品不是地图资源,单独给个显示名字典(随身携带列表要用)
ITEM_NAMES = {k: v[0] for k, v in RESOURCES.items()}
ITEM_NAMES.update({"bandage": "🩹 绷带", "first_aid": "🧰 急救包", "clean_water": "🚰 净水",
                   "emergency_food": "🥫 应急食品",
                   "ring_simple": "💍 简易承诺戒指", "ring_gem": "💎 旧世界宝石戒指",
                   "ring_northstar": "📡 北辰共鸣戒指",
                   "northstar_beacon": "📡 北辰归航信标"})
ITEM_NAMES.update({
    "fish_meat": "🐟 处理好的鱼肉", "egg": "🥚 鸡蛋", "milk": "🥛 羊奶",
    "rabbit_fur": "🐇 兔毛", "vegetable": "🥬 新鲜蔬菜", "fruit": "🍎 野果", "grain": "🌾 谷物",
})

RING_RECIPES = {
    "ring_simple": {"name": ITEM_NAMES["ring_simple"], "workbench": "basic",
                    "cost": {"silver_scrap": 3, "metal": 8}},
    "ring_gem": {"name": ITEM_NAMES["ring_gem"], "workbench": "basic",
                 "cost": {"silver_scrap": 5, "old_gem": 1, "electronics": 1}},
    "ring_northstar": {"name": ITEM_NAMES["ring_northstar"], "workbench": "advanced",
                       "cost": {"silver_scrap": 8, "old_gem": 2, "resonance_material": 1}},
}
MARRIAGE_AFFINITY_REQUIRED = 20
MAX_CHILDREN_PER_COUPLE = 3

CHILD_GROWTH_EVENTS = {
    6: {
        "title": "第一次独自系紧鞋带",
        "choices": {
            "medic": ("教他先救人", "智慧+2；孩子开始留意伤口与药品。", "stat_int"),
            "scout": ("教他先观察道路", "速度+2；孩子学会在行动前寻找退路。", "stat_spd"),
            "builder": ("教他修好身边的东西", "力量+2；孩子相信坏掉不等于报废。", "stat_str"),
        },
    },
    12: {
        "title": "第一次提出不同意见",
        "choices": {
            "kind": ("让他保留善意", "幸运+2；他选择帮助一个没有回报的陌生人。", "stat_luck"),
            "brave": ("让他直面危险", "力量+2；他决定不再躲在大人身后。", "stat_str"),
            "wise": ("让他自己判断", "智慧+2；你第一次真正尊重了他的决定。", "stat_int"),
        },
    },
    18: {
        "title": "成年夜的去留",
        "choices": {
            "home": ("成为家族守灯人", "智慧+2；他答应无论谁远行，家里都会有灯。", "stat_int"),
            "ranger": ("成为荒原远行者", "速度+2；地图边缘成了他新的起点。", "stat_spd"),
            "signal": ("接入北辰线路", "幸运+2；他把自己的呼号写进家族无线电。", "stat_luck"),
        },
    },
}

EXPEDITION_ROUTES = {
    "suburb": {"name": "🏚️ 近郊补给线", "duration": 20 * 60, "cost": {"raw_food": 1, "clean_water": 1}, "danger": .06,
               "rewards": ["wood", "stone", "cloth", "raw_food", "vegetable", "fruit", "grain"]},
    "hospital": {"name": "🏥 封锁医院", "duration": 40 * 60, "cost": {"raw_food": 2, "clean_water": 2}, "danger": .13,
                 "rewards": ["herb", "bandage", "first_aid", "old_gem"]},
    "industrial": {"name": "🏭 工业废区", "duration": 60 * 60, "cost": {"raw_food": 3, "clean_water": 3}, "danger": .2,
                   "rewards": ["metal", "parts", "silver_scrap", "electronics"]},
}

SHELTER_LIFE_EVENT_DEFS = {
    "birthday": {"title": "🎂 废土生日", "description": "有人记得今天是一个成员的生日。",
                 "options": {"feast": "拿出食物庆祝", "radio": "点一首旧歌", "quiet": "安静留一盏灯"}},
    "stranger": {"title": "🚪 雨夜敲门", "description": "一名浑身湿透的陌生人请求留宿一夜。",
                 "options": {"welcome": "允许留宿", "screen": "先检查伤势", "refuse": "隔门送补给"}},
    "broken_radio": {"title": "📻 公共频道失灵", "description": "庇护所的公共收音机突然只剩杂音。",
                     "options": {"repair": "一起修理", "listen": "记录杂波规律", "story": "改成故事之夜"}},
    "children": {"title": "🗺️ 孩子们的秘密地图", "description": "几个孩子画了一张没人见过的附近地图。",
                 "options": {"escort": "陪他们确认路线", "praise": "把地图挂起来", "teach": "补上一堂安全课"}},
    "underground": {"title": "🔦 地下的敲击声", "description": "储藏室下方传来规律的三短两长。",
                    "options": {"dig": "谨慎挖开入口", "signal": "用同样节奏回应", "seal": "先封锁区域"}},
}

HOMESTEAD_STATIONS = {
    "kitchen": {"name": "🍳 废土厨房", "cost": {"wood": 15, "metal": 6}},
    "brewery": {"name": "🫙 饮品与发酵台", "cost": {"wood": 12, "metal": 4, "cloth": 3}},
    "sewing": {"name": "🧵 缝纫工作台", "cost": {"wood": 10, "metal": 4, "cloth": 8}},
    "livestock": {"name": "🐓 小型畜牧棚", "cost": {"wood": 25, "metal": 8}},
}

FOOD_RECIPES = {
    "grilled_fish": {"name": "🐟 香草烤鱼", "skill": 0, "cost": {"fish_meat": 1, "herb": 1}, "hunger": 42, "recreation": 5},
    "egg_stew": {"name": "🥚 蔬菜炖蛋", "skill": 2, "cost": {"egg": 2, "vegetable": 1}, "hunger": 48, "recreation": 6},
    "milk_soup": {"name": "🥛 奶香浓汤", "skill": 4, "cost": {"milk": 1, "vegetable": 2}, "hunger": 55, "recreation": 7},
    "family_hotpot": {"name": "🍲 家族火锅", "skill": 7, "cost": {"fish_meat": 2, "egg": 2, "vegetable": 2, "herb": 1}, "hunger": 80, "recreation": 12},
    "child_meal": {"name": "🧒 儿童营养餐", "skill": 5, "cost": {"egg": 1, "milk": 1, "vegetable": 1}, "hunger": 50, "recreation": 8},
}

DRINK_RECIPES = {
    "herbal_tea": {"name": "🍵 荒原草药茶", "skill": 0, "cost": {"clean_water": 1, "herb": 1}, "thirst": 35, "heal": 3, "recreation": 4},
    "fruit_water": {"name": "🍎 浸渍果饮", "skill": 2, "cost": {"clean_water": 1, "fruit": 2}, "thirst": 45, "heal": 0, "recreation": 6},
    "milk_tonic": {"name": "🥛 温热奶饮", "skill": 4, "cost": {"milk": 1, "herb": 1}, "thirst": 38, "heal": 8, "recreation": 7},
    "grain_brew": {"name": "🫙 谷物发酵饮", "skill": 6, "cost": {"grain": 2, "clean_water": 1}, "thirst": 50, "heal": 5, "recreation": 10},
}

CLOTHING_RECIPES = {
    "raincoat": {"name": "🌧️ 拼接雨衣", "skill": 0, "cost": {"cloth": 12, "rabbit_fur": 1},
                 "effect": "恶劣天气远征风险-10%", "combat_defense": 0.03},
    "winter_coat": {"name": "🧥 荒原保暖外套", "skill": 3, "cost": {"cloth": 18, "rabbit_fur": 2, "pelt": 2},
                    "effect": "远征受伤风险-12%", "combat_defense": 0.05},
    "family_jacket": {"name": "🪡 家族徽记夹克", "skill": 6, "cost": {"cloth": 20, "rabbit_fur": 2, "pelt": 2, "silver_scrap": 1},
                      "effect": "与家人远征风险-15%", "combat_defense": 0.06},
    "scout_outfit": {"name": "🥾 侦察者套装", "skill": 8, "cost": {"cloth": 24, "rabbit_fur": 4, "parts": 2},
                     "effect": "远征时间-10%", "combat_defense": 0.04},
    "child_outfit": {"name": "🧸 儿童防护服", "skill": 4, "cost": {"cloth": 10, "rabbit_fur": 2},
                     "effect": "可赠予孩子，探索风险永久小幅降低", "combat_defense": 0},
}

LIVESTOCK_TYPES = {
    "chicken": {"name": "🐓 鸡", "price": 15, "adult_age": 2, "produce_key": "egg", "produce_name": "鸡蛋", "produce_days": 1},
    "rabbit": {"name": "🐇 兔", "price": 18, "adult_age": 2, "produce_key": "rabbit_fur", "produce_name": "兔毛", "produce_days": 2},
    "goat": {"name": "🐐 山羊", "price": 30, "adult_age": 3, "produce_key": "milk", "produce_name": "羊奶", "produce_days": 1},
}
ITEM_NAMES.update({k: v["name"] for k, v in FOOD_RECIPES.items()})
ITEM_NAMES.update({k: v["name"] for k, v in DRINK_RECIPES.items()})
ITEM_NAMES.update({k: v["name"] for k, v in CLOTHING_RECIPES.items()})

SURVIVAL_WORKSHOP_STATIONS = {
    "water_tester": {"name": "🧪 便携污染检测台", "cost": {"parts": 5, "electronics": 1, "metal": 8}},
    "ammo_press": {"name": "🗜️ 手动弹药复装机", "cost": {"parts": 8, "metal": 15, "wood": 5}},
}
WATER_CONTAMINATION = {
    "safe": {"name": "✅ 未检出明显污染", "treatment": "直接装瓶", "cost": {}},
    "bio": {"name": "🦠 细菌污染", "treatment": "煮沸消毒", "cost": {"wood": 1}},
    "chemical": {"name": "☣️ 化学污染", "treatment": "活性介质过滤", "cost": {"cloth": 2, "herb": 1}},
    "radiation": {"name": "☢️ 辐射颗粒", "treatment": "多层沉降过滤", "cost": {"cloth": 3, "parts": 1}},
}
RUIN_PARTS = {
    "furniture": {"name": "🪑 拆旧家具", "damage": 15, "noise": 1, "danger": 0, "low_risk": True,
                  "loot": [("wood", 4, 7), ("cloth", 1, 3)]},
    "doorframe": {"name": "🚪 撬门框与管线", "damage": 22, "noise": 3, "danger": .12,
                  "loot": [("metal", 3, 6), ("parts", 1, 2), ("spent_casing", 1, 3)]},
    "appliance": {"name": "📺 拆废弃电器", "damage": 25, "noise": 2, "danger": .09,
                  "loot": [("parts", 2, 4), ("electronics", 1, 1), ("gun_oil", 1, 2),
                           ("fuel", 1, 2)]},
    "safe": {"name": "🔐 强开保险柜", "damage": 35, "noise": 5, "danger": .24,
             "loot": [("ammo", 2, 5), ("gunpowder", 1, 3), ("old_gem", 1, 1)]},
}
ITEM_NAMES.update({
    "spent_casing": "🟡 回收弹壳", "gunpowder": "🧨 可用火药", "gun_oil": "🛢️ 枪械保养油",
    "fuel": "⛽ 回收燃油",
})

# 二节图纸等级门槛表(数值设计二节),workbench: basic=个人房子工作台 / advanced=庇护所高级工作台
BLUEPRINTS = {
    "bow":       {"name": "🏹 弓箭",     "level": 5,  "workbench": "basic",    "cost": {"wood": 10, "cloth": 5},                "type": "weapon"},
    "crossbow":  {"name": "🎯 弩",       "level": 12, "workbench": "advanced", "cost": {"wood": 15, "metal": 15, "cloth": 5},   "type": "weapon"},
    "gun":       {"name": "🔫 简易枪械", "level": 20, "workbench": "advanced", "cost": {"metal": 30, "parts": 10},              "type": "weapon"},
    "rifle":     {"name": "💥 制式武器", "level": 28, "workbench": "advanced", "cost": {"metal": 50, "parts": 30, "electronics": 10}, "type": "weapon"},
    "armor_basic":      {"name": "🥋 基础护甲", "level": 3,  "workbench": "basic",    "cost": {"cloth": 20, "metal": 10},              "type": "armor", "tier": 1},
    "armor_reinforced": {"name": "🛡️ 强化护甲", "level": 10, "workbench": "advanced", "cost": {"cloth": 40, "metal": 25},              "type": "armor", "tier": 2},
    "armor_advanced":   {"name": "🦺 高级护甲", "level": 18, "workbench": "advanced", "cost": {"cloth": 60, "metal": 50, "parts": 10}, "type": "armor", "tier": 3},
    "backpack":  {"name": "🎒 背包",     "level": 15, "workbench": "basic",    "cost": {"cloth": 20, "metal": 10},              "type": "backpack"},
    "bandage":   {"name": "🩹 绷带",     "level": 4,  "workbench": "basic",    "cost": {"cloth": 5, "herb": 3},                 "type": "medical", "heal": 20},
    "first_aid": {"name": "🧰 急救包",   "level": 10, "workbench": "advanced", "cost": {"cloth": 10, "herb": 8},                "type": "medical", "heal": 50},
    "antidote":  {"name": "💊 解毒剂",   "level": 6,  "workbench": "basic",    "cost": {"herb": 10, "cloth": 3, "clean_water": 5}, "type": "medical", "heal": 10, "cures_poison": True},
    "antiseptic": {"name": "💊 消炎药",  "level": 5,  "workbench": "basic",    "cost": {"herb": 6, "cloth": 3},                 "type": "medical", "heal": 0, "infection_relief": 15},
    "fishing_rod": {"name": "🎣 鱼竿",   "level": 2,  "workbench": "basic",    "cost": {"wood": 15, "cloth": 5},                "type": "tool"},
    "radar":     {"name": "📡 便携雷达", "level": 18, "workbench": "advanced", "cost": {"metal": 25, "parts": 12, "electronics": 2}, "type": "tool"},
    "cooked_food": {"name": "🍲 熟食",   "level": 6,  "workbench": "basic",    "cost": {"raw_food": 2, "herb": 1},               "type": "food", "hunger": 35},
}
ITEM_NAMES.update({k: v["name"] for k, v in BLUEPRINTS.items()})

# 二十七节:仓库存取下拉列表原来是手写的一份清单，漏了消炎药/枪械保养油/鱼获/蔬果等一大批
# 后来加的物品——玩家反馈"东西放不进箱子"，根源是这份清单没跟上。改成动态生成:凡是能进
# character_inventory的都能存取，只排除装备槽位物品(武器/护甲/背包/鱼竿，这些不是堆叠物品)
# 和终局任务道具(北辰归航信标，不该被转移)。
STORAGE_EXCLUDED_KEYS = {"northstar_beacon"}  # 鱼竿现在是普通背包物品了,也能存/送人；归航信标是唯一结局道具,继续禁止转移

def storage_transferable_keys():
    # 二十九节:武器/护甲/背包做好以后先进背包(不再自动装备),所以也能像其他物资一样存仓库给别人用。
    excluded = STORAGE_EXCLUDED_KEYS | set(VEHICLES)
    return sorted(k for k in ITEM_NAMES if k not in excluded)

# 二十九节:交通工具——造一次就一直有效(不像武器/护甲会磨损),移动时省体力、跳过负重/天气
# 减速、且冷却极短甚至为0。max_tiles是"最多能跳几格"，玩家自己选1~max_tiles之间的格数，
# 不想跳那么远(比如想precisely停在某个资源点)可以选更少，体力/冷却不随格数变化。
VEHICLES = {
    "bicycle":  {"name": "🚲 自行车",  "level": 3,  "workbench": "basic",
                 "cost": {"wood": 20, "metal": 10}, "max_tiles": 2, "stamina_cost": 2, "cooldown_seconds": 5},
    "motorcycle": {"name": "🏍️ 摩托车", "level": 10, "workbench": "advanced",
                   "cost": {"metal": 40, "parts": 15, "fuel": 5}, "max_tiles": 3, "stamina_cost": 2, "cooldown_seconds": 2},
    "offroad":  {"name": "🚙 越野车",  "level": 18, "workbench": "advanced",
                 "cost": {"metal": 80, "parts": 30, "fuel": 15}, "max_tiles": 4, "stamina_cost": 1, "cooldown_seconds": 0},
}
ITEM_NAMES.update({k: v["name"] for k, v in VEHICLES.items()})

# 钓鱼:图鉴用的鱼种表,difficulty(1-10)驱动小游戏的鱼速度/乱动幅度/判定条大小
FISH_SPECIES = {
    "mutant_carp":     {"name": "🐟 变异鲤鱼",   "rarity": "common",    "difficulty": 2,  "value": 3},
    "rot_perch":       {"name": "🐠 腐水鲈鱼",   "rarity": "common",    "difficulty": 3,  "value": 4},
    "glow_eel":        {"name": "🐍 荧光鳗",     "rarity": "uncommon",  "difficulty": 5,  "value": 9},
    "iron_gar":        {"name": "🐡 铁鳞雀鳝",   "rarity": "uncommon",  "difficulty": 5,  "value": 10},
    "acid_catfish":    {"name": "🦈 强酸鲶鱼",   "rarity": "rare",      "difficulty": 7,  "value": 22},
    "phantom_koi":     {"name": "🎏 幽灵锦鲤",   "rarity": "rare",      "difficulty": 8,  "value": 26},
    "leviathan_spawn": {"name": "🐋 深渊幼鲲",   "rarity": "legendary", "difficulty": 10, "value": 60},
}
FISH_RARITY_WEIGHTS = {"common": 55, "uncommon": 28, "rare": 14, "legendary": 6}
FISH_RARITY_NAMES = {"common": "常见", "uncommon": "少见", "rare": "稀有", "legendary": "传说"}
WATER_TILE_CHANCE = 0.15
ITEM_NAMES.update({k: v["name"] for k, v in FISH_SPECIES.items()})
ITEM_NAMES.update({"rare_seed": "🌱 稀有种子", "prized_herb": "🌟 珍稀药草"})
ITEM_NAMES.update({"cooked_food": "🍲 熟食", "animal_dung": "💩 动物粪便", "fertilizer": "🧪 肥料",
                    "pelt": "🦫 兽皮", "radar": "📡 便携雷达"})
SELLABLE_FISH_VALUES = {k: v["value"] for k, v in FISH_SPECIES.items()}

# 八.3 护甲减伤 + 十六.1 感染度减免,简化成三档(完整版是每级+5%的连续曲线)
ARMOR_TIERS = {
    0: {"dmg_reduction": 0.0, "infection_reduction": 0.0},
    1: {"dmg_reduction": 0.10, "infection_reduction": 0.10},
    2: {"dmg_reduction": 0.20, "infection_reduction": 0.20},
    3: {"dmg_reduction": 0.30, "infection_reduction": 0.30},
}

# 五节武器基础伤害("优良"档基准值)
WEAPON_DAMAGE = {"fist": 5, "bow": 12, "crossbow": 22, "gun": 35, "rifle": 55}
MELEE_WEAPONS = {"fist"}
BASIC_WORKBENCH_COST = {"wood": 30, "metal": 10}
ADVANCED_WORKBENCH_COST = {"wood": 80, "metal": 60, "research_points": 20}
BACKPACK_CAP = 3
BACKPACK_BONUS = 100

HOUSE_COST = {"wood": 20, "stone": 10}
HOUSE_INVENTORY_CAP = 80
# 二十六节:储物箱不需要工作台，随时随地能造，给房子仓库扩容；封顶数量避免无限叠加。
STORAGE_CRATE_COST = {"wood": 15, "cloth": 5}
STORAGE_CRATE_BONUS = 40
STORAGE_CRATE_CAP = 5  # 房子仓库的储物箱数量上限
SHELTER_STORAGE_CRATE_CAP = 20  # 庇护所是多人共用仓库,储物箱上限比单人房子高一大截
# 二十九节:超大仓库——庇护所Lv3+才能建,一次性建好就是+500容量,不能叠加(跟储物箱那种
# 小额、可重复叠加的扩容是两条路,给不想造20个储物箱的人一个一步到位的选项)。
MEGA_WAREHOUSE_LEVEL_REQUIRED = 3
MEGA_WAREHOUSE_BONUS = 500
MEGA_WAREHOUSE_COST = {"wood": 300, "metal": 150, "cloth": 100, "parts": 50}

# 二十九节:被动资源采集机——必须建在自己所属的庇护所(不能建在个人房子里,普通采集始终手动)，
# 不用人守着，按小时结算产出。金属版是旧的"打矿机"改造，木头/石头是新增的同类设施；
# 三者都能升级，等级门槛只在建造时检查一次。
EXTRACTOR_LEVEL_CAP = 3
EXTRACTOR_INTERVAL_SECONDS = 3600
EXTRACTOR_TYPES = {
    "metal_driller": {"name": "⛏️ 打矿机", "resource_key": "metal", "level_required": 5},
    "auto_lumberjack": {"name": "🪓 自动伐木机", "resource_key": "wood", "level_required": 3},
    "auto_quarry": {"name": "🪨 自动采石机", "resource_key": "stone", "level_required": 3},
    # 研究站产出直接进庇护所的research_points字段(不是仓库物资)，还额外要求庇护所本身
    # 等级达到shelter_tier_required——不然全庇护所唯一的科研点来源还是只有打丧尸。
    "research_station": {"name": "🧪 研究站", "resource_key": "research_points",
                         "level_required": 1, "shelter_tier_required": 2},
}
EXTRACTOR_LEVELS = {
    "metal_driller": {
        1: {"yield_per_hour": 4,  "cost": {"wood": 30, "stone": 20, "parts": 5}},
        2: {"yield_per_hour": 7,  "cost": {"metal": 40, "parts": 10}},
        3: {"yield_per_hour": 11, "cost": {"metal": 80, "parts": 25}},
    },
    "auto_lumberjack": {
        1: {"yield_per_hour": 5,  "cost": {"wood": 20, "stone": 10, "parts": 3}},
        2: {"yield_per_hour": 9,  "cost": {"wood": 60, "parts": 8}},
        3: {"yield_per_hour": 14, "cost": {"wood": 120, "metal": 20, "parts": 15}},
    },
    "auto_quarry": {
        1: {"yield_per_hour": 5,  "cost": {"wood": 15, "stone": 25, "parts": 3}},
        2: {"yield_per_hour": 9,  "cost": {"stone": 60, "parts": 8}},
        3: {"yield_per_hour": 14, "cost": {"stone": 120, "metal": 20, "parts": 15}},
    },
    "research_station": {
        1: {"yield_per_hour": 1, "cost": {"wood": 40, "metal": 20, "electronics": 2}},
        2: {"yield_per_hour": 2, "cost": {"metal": 60, "parts": 20, "electronics": 5}},
        3: {"yield_per_hour": 3, "cost": {"metal": 100, "parts": 40, "electronics": 10}},
    },
}
# 旧字段名保留给一次性迁移脚本用(把老版本"打矿机"的房子数据搬进resource_extractors)。
METAL_DRILLER_INTERVAL_SECONDS = EXTRACTOR_INTERVAL_SECONDS
METAL_DRILLER_YIELD_PER_HOUR = EXTRACTOR_LEVELS["metal_driller"][1]["yield_per_hour"]

# 二十九节:驱赶器——庇护所Lv2+才能建,压低所在区域(以及升级后周边区域)噪声/长期威胁的
# 上限,不是清零而是降低天花板;radius以"区域"(5x5格)为单位算切比雪夫距离,0=只罩自己所在
# 区域,1=再罩周围8个区域,以此类推。同一片区域如果被多个驱赶器覆盖,取最严格(最低)的那个上限。
REPELLER_LEVEL_REQUIRED = 2  # 庇护所自身等级门槛
REPELLER_LEVEL_CAP = 3
REPELLER_LEVELS = {
    1: {"radius": 0, "noise_cap": 60, "threat_cap": 50, "cost": {"wood": 40, "metal": 20, "parts": 10}},
    2: {"radius": 1, "noise_cap": 45, "threat_cap": 35, "cost": {"metal": 60, "parts": 25, "electronics": 3}},
    3: {"radius": 2, "noise_cap": 30, "threat_cap": 20, "cost": {"metal": 120, "parts": 50, "electronics": 10}},
}

def repeller_cap_for_region(region_x, region_y):
    """返回(noise_cap, threat_cap)。没有驱赶器覆盖时维持原来的100上限。"""
    noise_cap, threat_cap = 100, 100
    for shelter in q("""SELECT tile_x,tile_y,repeller_level FROM shelters
                        WHERE abandoned=0 AND repeller_level>0"""):
        info = REPELLER_LEVELS.get(shelter["repeller_level"])
        if not info:
            continue
        srx, sry = region_coords(shelter["tile_x"], shelter["tile_y"])
        if max(abs(region_x - srx), abs(region_y - sry)) <= info["radius"]:
            noise_cap = min(noise_cap, info["noise_cap"])
            threat_cap = min(threat_cap, info["threat_cap"])
    return noise_cap, threat_cap

def house_inventory_cap_for(house):
    return HOUSE_INVENTORY_CAP + (house["storage_crates"] if house else 0) * STORAGE_CRATE_BONUS

def shelter_inventory_cap_for(shelter):
    base = SHELTER_TIERS[shelter["tier"]][1] if shelter else 0
    crate_bonus = (shelter["storage_crates"] if shelter else 0) * STORAGE_CRATE_BONUS
    mega_bonus = MEGA_WAREHOUSE_BONUS if (shelter and shelter["has_mega_warehouse"]) else 0
    return base + crate_bonus + mega_bonus

def shelter_extractor_state(shelter_id):
    """给dashboard渲染用:这个庇护所每种采集机建了没有/当前等级/下一级要多少材料。"""
    rows = {r["kind"]: r for r in q(
        "SELECT * FROM resource_extractors WHERE owner_type='shelter' AND owner_id=?", (shelter_id,))}
    state = {}
    for kind, info in EXTRACTOR_TYPES.items():
        row = rows.get(kind)
        level = row["level"] if row else 0
        next_level = level + 1
        state[kind] = {
            "info": info,
            "built": bool(row),
            "level": level,
            "cur_yield": EXTRACTOR_LEVELS[kind][level]["yield_per_hour"] if row else 0,
            "maxed": bool(row) and level >= EXTRACTOR_LEVEL_CAP,
            "next_cost": (EXTRACTOR_LEVELS[kind][1]["cost"] if not row
                         else EXTRACTOR_LEVELS[kind].get(next_level, {}).get("cost")),
            "next_yield": (EXTRACTOR_LEVELS[kind][1]["yield_per_hour"] if not row
                          else EXTRACTOR_LEVELS[kind].get(next_level, {}).get("yield_per_hour")),
        }
    return state
HOUSE_LEVELS = {
    1: {"name": "临时木屋", "max_hp": 80,  "armor": 0,  "counter": 0.00,
        "cost": {}, "shelter_tier": 0},
    2: {"name": "加固住所", "max_hp": 140, "armor": 3,  "counter": 0.00,
        "cost": {"wood": 30, "stone": 20}, "shelter_tier": 0},
    3: {"name": "独立安全屋", "max_hp": 220, "armor": 7,  "counter": 0.00,
        "cost": {"wood": 50, "stone": 40, "metal": 15}, "shelter_tier": 0},
    4: {"name": "联网哨戒屋", "max_hp": 320, "armor": 11, "counter": 0.25,
        "cost": {"wood": 80, "stone": 60, "metal": 35, "parts": 10}, "shelter_tier": 2},
    5: {"name": "末日堡垒住宅", "max_hp": 450, "armor": 16, "counter": 0.40,
        "cost": {"wood": 120, "stone": 100, "metal": 60, "parts": 25, "electronics": 3},
        "shelter_tier": 4},
}
HOUSE_LEVEL_CAP = max(HOUSE_LEVELS)
HOUSE_SOLO_LEVEL_CAP = 3
HOUSE_REPAIR_AMOUNT = 60
HOUSE_AUTO_REPAIR_COST = {"metal": 12, "parts": 5, "electronics": 1}
HOUSE_RAID_STEALABLE = {
    "wood", "stone", "raw_food", "raw_water", "herb", "cloth", "metal", "ammo",
    "parts", "silver_scrap", "electronics", "clean_water", "cooked_food",
    "emergency_food", "bandage", "first_aid", "vegetable", "fruit", "grain", "fuel",
}

GENERATOR_LEVELS = {
    0: {"name": "未接入电网", "capacity": 0, "output": 0, "noise": 0,
        "fuel": 0, "cost": {}},
    1: {"name": "🚲 脚踏发电机", "capacity": 8, "output": 5, "noise": 2,
        "fuel": 0, "cost": {"wood": 8, "metal": 12, "parts": 4}},
    2: {"name": "⛽ 燃油发电机", "capacity": 24, "output": 16, "noise": 10,
        "fuel": 1, "cost": {"metal": 30, "parts": 12, "electronics": 1}},
    3: {"name": "☀️ 太阳能储能阵列", "capacity": 40, "output": 10, "noise": 0,
        "fuel": 0, "cost": {"metal": 45, "parts": 18, "electronics": 4}},
}
POWER_MODES = {
    "quiet": ("静默供电", "发电噪声-40%、产出-25%，普通设备可使用全部电量"),
    "balanced": ("均衡供电", "标准发电效率，设备按需取电"),
    "defense": ("战备保电", "普通设备会保留最后6点电力，供夜袭自动反击或瞭望塔使用"),
}
POWER_DEFENSE_RESERVE = 6
SHELTER_COST = {"wood": 100, "metal": 50, "stone": 80}
SHELTER_LEVEL_REQUIRED = 5

SHELTER_TIERS = {
    # tier: (人数上限, 仓库容量)
    1: (3, 500), 2: (5, 800), 3: (8, 1200), 4: (12, 1800), 5: (16, 2600), 6: (20, 3600),
}

# 数值设计三节:庇护所升级成本(材料+科研点数),之前只定了数值没接代码
SHELTER_UPGRADE_COST = {
    2: {"materials": {"wood": 150, "metal": 80}, "research_points": 30},
    3: {"materials": {"wood": 300, "metal": 150, "cloth": 50}, "research_points": 80},
    4: {"materials": {"wood": 500, "metal": 300, "parts": 20}, "research_points": 150},
    5: {"materials": {"wood": 800, "metal": 500, "parts": 50}, "research_points": 300},
    6: {"materials": {"metal": 800, "parts": 100, "electronics": 20}, "research_points": 500},
}
SHELTER_TIER_CAP = 6

# 六节:炉子把生水煮成净水,只有庇护所能建
FURNACE_COST = {"wood": 40, "metal": 20}
FURNACE_BATCH_INPUT = {"raw_water": 10}
FURNACE_FALLBACK_WOOD = 2
FURNACE_BATCH_OUTPUT = 10
FURNACE_BATCH_SECONDS = 30 * 60

# 五节:庇护所自带田地,按天产出(DAY_SECONDS=1游戏天,呼应"每人每天至少4份生鲜"的产量基准)
FARM_HARVEST_SECONDS = DAY_SECONDS
FARM_YIELD_PER_PLOT = 5
FARM_INT_YIELD_BONUS_PER_POINT = 0.03  # 数值设计:智慧影响种田产量,INT20封顶约+60%
FARM_HARVEST_XP = 5

# B档62条:温室,解锁稀有作物种植位(没有天气系统,"恶劣天气不减产"那半条效果先搁置)
GREENHOUSE_COST = {"wood": 60, "metal": 30, "research_points": 40}
# B档63条:稀有种子,采集时低概率额外获得,种下产出高级药剂原料
RARE_SEED_DROP_CHANCE = 0.02
RARE_SEED_YIELD = 2
EMERGENCY_FOOD_DROP_CHANCE = 0.04
# 二十九节:终局特殊材料再加一条来源——处理传说级鱼获必定附带掉落，给钓鱼玩法一条路，
# 不用只靠每日手气和远方地标节点这两个纯运气来源。传说鱼本身只有3%遇到率，
# 真正的门槛已经在"抓到"这一步，处理时不该再乘一层概率变相加倍稀释。
LEGENDARY_FISH_RESONANCE_CHANCE = 1.0

# 十四.1:系统收购点,是钱包货币目前唯一的来源,地标级材料不可变卖(避免绕开"必须去远处"的终局节奏)
SELL_RATE = 1
SELLABLE_RESOURCES = [k for k in (
    "wood", "stone", "raw_food", "raw_water", "herb", "cloth", "metal", "ammo", "parts", "silver_scrap",
    # 农场/畜牧产出容易堆积用不完,开放给系统收购点换钱包货币,顺便腾随身/仓库容量。
    "egg", "milk", "rabbit_fur", "vegetable", "fruit", "grain",
)]

# 三节:废弃建筑保留一段时间后自动拆除清空,地块恢复空地(数值留到落地阶段,先取三节建议的默认值7天)
BUILDING_ABANDON_CLEANUP_SECONDS = 7 * DAY_SECONDS

# 11.3:解药研发,数值设计没定具体门槛,这次一并补上(一次性解锁门槛 + 每次使用的材料)
VACCINE_UNLOCK_RESEARCH = 200
VACCINE_UNLOCK_MATERIALS = {"herb": 100, "cloth": 50}
VACCINE_DOSE_COST = {"herb": 10, "prized_herb": 1}

# 十六.3:防御建筑,三种可以各自叠加,防御值线性相加
DEFENSE_BUILDINGS = {
    "wall":  {"name": "🧱 围墙",   "value": 20, "cost": {"wood": 60, "stone": 40}},
    "trap":  {"name": "🪤 陷阱",   "value": 10, "cost": {"wood": 20, "metal": 10}},
    "tower": {"name": "🗼 瞭望塔", "value": 15, "cost": {"wood": 50, "metal": 30}},
}

# 十六.2:负重影响移动/回程耗时
MOVE_COOLDOWN_SECONDS = 20
MOVE_WEIGHT_SLOW_70 = 0.15
MOVE_WEIGHT_SLOW_90 = 0.35
STAMINA_MAX = 100
STAMINA_RECOVERY_SECONDS = 60
# 二十一节:直接喝生水的中毒率，铁胃特质在此基础上打7折(和改动前的相对折扣保持一致)
RAW_WATER_POISON_CHANCE = 0.15
RAW_WATER_POISON_CHANCE_IRON_STOMACH = 0.10
# 直接吃生鲜(不煮熟)同理也有食物中毒风险，和生水保持同一档概率；煮成熟食(cooked_food)就没有这个风险。
RAW_FOOD_POISON_CHANCE = 0.15
RAW_FOOD_POISON_CHANCE_IRON_STOMACH = 0.10
POISON_DURATION_SECONDS = 3 * 3600
# 应急食品饥饿值恢复量是普通生鲜的两倍，用"更干更咸、吃完更渴"做平衡
EMERGENCY_FOOD_THIRST_COST = 15
STAMINA_COSTS = {
    "move": 4, "gather": 7, "fish": 6, "ruin": 10, "expedition": 12,
    "quick": 3, "guard": 3, "aim": 1, "reload": 1,
    "item": 1, "terrain": 3, "pet": 0, "signal": 1, "flee": 4,
    "plant_tree": 4, "dig_quarry": 4, "draw_water": 3,
}
DRAW_WATER_YIELD = (3, 5)

# 二十四节:种树/挖石头——不依赖地图资源点的稳定木材/石头来源，原地种下/挖开，
# 等一段真实时间后回来收获；收获不再额外收体力(参考钓鱼/炼炉"开始收费、收获免费"的模式)。
TREE_GROW_SECONDS = 1200
QUARRY_GROW_SECONDS = 1200
TREE_WOOD_YIELD = (5, 9)
QUARRY_STONE_YIELD = (4, 7)

# 二十五节:自动吃喝开关——离线也不用怕饿死，包里有对应东西就按优先级自动吃/喝一份，
# 直到吃饱/喝够或者包里没有了为止。生水不自动喝，生鲜也不自动吃，怕睡着的时候被自动下毒。
# 这个门槛特意设得不低于感染度被动缓解的门槛(INFECTION_RECOVERY_WELLFED_THRESHOLD)，
# 不然开着自动吃喝的人饥饿/口渴长期卡在50出头，永远达不到感染度缓解要求的门槛，等于白开。
AUTO_EAT_HUNGER_THRESHOLD = 75
AUTO_EAT_THIRST_THRESHOLD = 75
# 个人生活工坊做出来的熟食/饮品(FOOD_RECIPES/DRINK_RECIPES)也算数,和图纸熟食/应急食品/净水一起按
# 恢复量从小到大排序,优先吃/喝便宜的,贵重的留着手动享用加成效果(自动吃喝只补数值,不触发那些加成)。
AUTO_EAT_FOOD_PRIORITY = sorted(
    [("cooked_food", BLUEPRINTS["cooked_food"]["hunger"]), ("emergency_food", 50)] +
    [(k, v["hunger"]) for k, v in FOOD_RECIPES.items()],
    key=lambda pair: pair[1])
AUTO_DRINK_PRIORITY = sorted(
    [("clean_water", 25)] + [(k, v["thirst"]) for k, v in DRINK_RECIPES.items()],
    key=lambda pair: pair[1])

# 十二节:归途装置(数值设计七节已有数字)
ENDGAME_MATERIAL_KEY = "resonance_material"
ENDGAME_MATERIAL_NEEDED = 20
ENDGAME_UNLOCK_TIER = 6
ENDGAME_UNLOCK_RESEARCH = 800
ENDGAME_BUILD_COST = {"metal": 1000, "parts": 300, "electronics": 100}

# 个人八章主线的真正通关物。第八章只解锁设计图，组装完成才结算角色通关。
NORTHSTAR_FINAL_ITEM_KEY = "northstar_beacon"
NORTHSTAR_FINAL_COST = {
    "metal": 25,
    "parts": 12,
    "electronics": 3,
    "old_gem": 1,
    "resonance_material": 3,
}

# B档60条:狩猎陷阱(和防御用的"陷阱"是两码事,这个是产食物的)
HUNTING_TRAP_COST = {"wood": 5, "metal": 3}  # 小成本,呼应"投入低"
HUNTING_TRAP_COOLDOWN_SECONDS = 12 * 3600
HUNTING_TRAP_RARE_CHANCE = 0.05

# B档:驯养系统(MVP,数值设计六节已有数字)
ANIMAL_PEN_COST = {"wood": 50, "metal": 20}
WILD_ANIMAL_ENCOUNTER_CHANCE = 0.06
TAME_AFFINITY_THRESHOLD = 100
TAME_FEED_GAIN = 10
TAME_SPOOK_CHANCE = 0.05
TAME_ZOMBIE_RISK_PER_HOUR = 0.03
ANIMALS = {
    "small_pack":  {"name": "🐐 小型驮兽", "tier": "small",  "storage_bonus": 80},
    "mid_fighter": {"name": "🐺 中型战斗兽", "tier": "mid",   "combat_bonus": 0.15},
    "big_producer":{"name": "🐂 大型生产兽", "tier": "big",   "daily_parts": (1, 2)},
}
COMPOST_INPUT = {"animal_dung": 5}
COMPOST_OUTPUT_KEY = "fertilizer"
COMPOST_YIELD_BOOST = 0.20

# B档59条:流动商人,钱包货币目前唯一的消耗出口(之前只有来源没有去处)
MERCHANT_REFRESH_SECONDS = 6 * 3600
MERCHANT_RESOURCES = ([k for k, v in RESOURCES.items() if v[1] == "rare"] +
                      ["fuel"])  # 燃油是发电的可选加速资源；脚踏发电仍保证无燃油也能运作。
MERCHANT_PRICE = 2
MERCHANT_STOCK_MIN = 20
MERCHANT_STOCK_MAX = 50

# 十六.5 丧尸生态：数值之外，每种敌人还有可预告、可反制的行为。
ZOMBIE_TYPES = {
    "normal": {"hp_mult": 1.0, "dmg_mult": 1.0, "spd": 10, "infect": 5,
               "name": "🧟 游荡者", "hint": "行动普通，会抓住猎物阻止逃跑。"},
    "fast":   {"hp_mult": 0.8, "dmg_mult": 0.8, "spd": 18, "infect": 3,
               "name": "🏃 迅捷者", "hint": "速度极快，扑击必须格挡。"},
    "tank":   {"hp_mult": 2.2, "dmg_mult": 1.15, "spd": 6, "infect": 5,
               "name": "🧟‍♂️ 肿胀巨尸", "hint": "正面减伤，冲撞后会暴露弱点。"},
    "screamer": {"hp_mult": 0.9, "dmg_mult": 0.65, "spd": 12, "infect": 4,
                 "name": "📢 尖啸者", "hint": "尖叫会提高区域威胁并强化后续攻击。"},
    "spitter": {"hp_mult": 1.1, "dmg_mult": 0.75, "spd": 9, "infect": 7,
                "name": "☣️ 污染者", "hint": "吐出污染液，格挡只能减伤，不能完全防感染。"},
}

def zombie_weight_by_distance(dist):
    if dist < 20:
        return {"normal": 82, "fast": 9, "tank": 2, "screamer": 4, "spitter": 3}
    if dist < 60:
        return {"normal": 52, "fast": 20, "tank": 12, "screamer": 9, "spitter": 7}
    return {"normal": 28, "fast": 22, "tank": 25, "screamer": 12, "spitter": 13}

COMBAT_TERRAINS = {
    "road": {"name": "🛣️ 开阔公路", "desc": "容易脱离；步枪能发挥远距离优势。",
             "flee": .10, "rifle": 1.18, "melee": 1.0},
    "hallway": {"name": "🚪 狭窄楼道", "desc": "难以逃跑；近战和弩更容易封住通道。",
                "flee": -.10, "crossbow": 1.15, "melee": 1.15},
    "ruins": {"name": "🏚️ 坍塌废墟", "desc": "掩体能削弱远程污染，但碎石妨碍移动。",
              "flee": -.05, "infection": .75, "gun": .92, "rifle": .92, "melee": 1.0},
    "rooftop": {"name": "🏙️ 断裂屋顶", "desc": "视野良好，弓与枪械更精准；退路有限。",
                "flee": -.08, "bow": 1.15, "gun": 1.10, "rifle": 1.12, "melee": .9},
    "woods": {"name": "🌲 枯树林", "desc": "树木遮蔽枪线，弓箭安静而灵活。",
              "flee": .04, "bow": 1.18, "gun": .90, "rifle": .88, "melee": 1.0},
}

ZOMBIE_INTENTS = {
    "normal": [
        ("bite", "🦷 准备扑上来撕咬", "普通攻击，并带来感染。", 65),
        ("grab", "✋ 正在伸手抓住你", "伤害较低，但会降低下一次逃跑率。", 35),
    ],
    "fast": [
        ("slash", "🩸 绕向侧面快速抓击", "较快的普通攻击。", 55),
        ("pounce", "⚠️ 压低身体准备扑击", "高伤攻击；稳守可以大幅化解。", 45),
    ],
    "tank": [
        ("smash", "👊 抬起沉重的手臂", "沉重攻击。", 55),
        ("charge", "⚠️ 蓄力准备冲撞", "伤害很高；稳守后它会暴露弱点。", 45),
    ],
    "screamer": [
        ("claw", "🩸 慌乱地挥动手臂", "较弱的抓击。", 45),
        ("scream", "📢 胸腔鼓起，准备尖叫", "不直接造成伤害，但会增加威胁并强化它。", 55),
    ],
    "spitter": [
        ("swipe", "🦴 拖着身体靠近", "近身抓击。", 45),
        ("spit", "☣️ 喉部开始涌出污染液", "感染很高；废墟掩体和稳守能部分化解。", 55),
    ],
}

RAID_STANCES = {
    "balanced": ("均衡防守", "不偏重任何目标，按标准方式结算。"),
    "storage": ("死守仓库", "失窃比例大幅降低，但房屋额外承受少量结构伤害。"),
    "facility": ("保护设施", "防线被突破时有较高概率保住设施。"),
    "conserve": ("节省弹药", "本夜不启动自动反击，保存房屋弹药与电力。"),
    "lure": ("主动诱敌", "房屋受损降低，但角色承担更多风险，并额外降低区域威胁。"),
}

INJURY_DEFS = {
    "bleeding": {"name": "🩸 撕裂伤", "effect": "攻击伤害-10%，绷带或急救包可以处理。",
                 "item": "bandage"},
    "sprain": {"name": "🦶 扭伤", "effect": "脱离战斗概率-12%，需要急救包固定。",
               "item": "first_aid"},
    "bruised": {"name": "🫁 胸腹挫伤", "effect": "稳守效果略微下降，需要急救包处理。",
                "item": "first_aid"},
}

def zombie_base_strength(dist, day_count):
    # 数值设计五节
    return 10 + dist * 0.8 + day_count * 0.3

# ── 数据库 ─────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_db(e=None):
    db = getattr(g, "_db", None)
    if db:
        db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    return cur.fetchone() if one else cur.fetchall()

def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    # CREATE TABLE IF NOT EXISTS 不会给线上旧表补列；房屋防御升级需要显式迁移。
    house_columns = {row[1] for row in db.execute("PRAGMA table_info(houses)")}
    for name, ddl in {
        "level": "INTEGER DEFAULT 1",
        "hp": "INTEGER DEFAULT 80",
        "max_hp": "INTEGER DEFAULT 80",
        "auto_defense": "INTEGER DEFAULT 0",
        "auto_defense_damaged": "INTEGER DEFAULT 0",
        "raid_stance": "TEXT DEFAULT 'balanced'",
        "last_raid_ts": "INTEGER DEFAULT 0",
        "storage_crates": "INTEGER DEFAULT 0",
        "has_metal_driller": "INTEGER DEFAULT 0",
        "metal_driller_ready_ts": "INTEGER DEFAULT 0",
        "custom_name": "TEXT DEFAULT ''",
    }.items():
        if name not in house_columns:
            db.execute(f"ALTER TABLE houses ADD COLUMN {name} {ddl}")
    db.execute("""UPDATE houses SET level=COALESCE(level,1),hp=COALESCE(hp,80),
                  max_hp=COALESCE(max_hp,80),auto_defense=COALESCE(auto_defense,0),
                  auto_defense_damaged=COALESCE(auto_defense_damaged,0),
                  raid_stance=COALESCE(raid_stance,'balanced'),
                  last_raid_ts=COALESCE(last_raid_ts,0)""")
    # 二十九节:老版本打矿机是挂在houses.has_metal_driller上的，统一迁移进resource_extractors表，
    # 迁移后新建/升级都走新系统；INSERT OR IGNORE保证这段迁移可以在每次启动时重复执行也不会出错。
    for old_driller in db.execute("""SELECT id, metal_driller_ready_ts FROM houses
                                     WHERE has_metal_driller=1""").fetchall():
        db.execute("""INSERT OR IGNORE INTO resource_extractors (owner_type,owner_id,kind,level,ready_ts)
                      VALUES ('house',?,?,1,?)""",
                   (old_driller["id"], "metal_driller", old_driller["metal_driller_ready_ts"] or 0))
    # 二十九节:鱼竿从characters.has_fishing_rod这个开关字段改成普通背包物品(能存仓库给别人)，
    # 老玩家已经有的鱼竿在这里一次性搬进背包，然后把开关清掉，保证这段迁移只生效一次。
    for old_owner in db.execute("SELECT id FROM characters WHERE has_fishing_rod=1").fetchall():
        db.execute("""INSERT INTO character_inventory(character_id,resource_key,amount) VALUES(?,'fishing_rod',1)
                      ON CONFLICT(character_id,resource_key) DO UPDATE SET amount=amount+1""", (old_owner["id"],))
        db.execute("UPDATE characters SET has_fishing_rod=0 WHERE id=?", (old_owner["id"],))
    shelter_columns = {row[1] for row in db.execute("PRAGMA table_info(shelters)")}
    if "storage_crates" not in shelter_columns:
        db.execute("ALTER TABLE shelters ADD COLUMN storage_crates INTEGER DEFAULT 0")
    if "has_workbench" not in shelter_columns:
        db.execute("ALTER TABLE shelters ADD COLUMN has_workbench INTEGER DEFAULT 0")
    if "repeller_level" not in shelter_columns:
        db.execute("ALTER TABLE shelters ADD COLUMN repeller_level INTEGER DEFAULT 0")
    if "has_mega_warehouse" not in shelter_columns:
        db.execute("ALTER TABLE shelters ADD COLUMN has_mega_warehouse INTEGER DEFAULT 0")
    mail_columns = {row[1] for row in db.execute("PRAGMA table_info(player_mail)")}
    if "action_type" not in mail_columns:
        db.execute("ALTER TABLE player_mail ADD COLUMN action_type TEXT DEFAULT ''")
    if "action_ref" not in mail_columns:
        db.execute("ALTER TABLE player_mail ADD COLUMN action_ref INTEGER DEFAULT 0")
    quest_columns = {row[1] for row in db.execute("PRAGMA table_info(dynamic_personal_quests)")}
    if "notified" not in quest_columns:
        db.execute("ALTER TABLE dynamic_personal_quests ADD COLUMN notified INTEGER DEFAULT 0")
        # 老支线里已经达标、但一直没人手动去日志页领取的(比如"庇护所留下的后续"这种)，
        # 这里一次性补发提醒邮件，不用等玩家凑巧再触发一次同类型进度才会收到通知。
        for backlog in db.execute("""SELECT * FROM dynamic_personal_quests
                                     WHERE status='active' AND progress>=target""").fetchall():
            reward_text = (f"钱包+{backlog['reward_amount']}" if backlog["reward_key"] == "wallet"
                           else f"{ITEM_NAMES.get(backlog['reward_key'], backlog['reward_key'])}x{backlog['reward_amount']}")
            db.execute("""INSERT INTO player_mail(from_character_id,from_name,to_character_id,subject,body,
                          action_type,action_ref,created_ts)
                          VALUES(0,'系统',?,?,?,'claim_dynamic_quest',?,?)""",
                      (backlog["character_id"], f"🎯 支线完成：{backlog['title']}",
                       f"{backlog['description']}\n\n已经达成目标，奖励：{reward_text}。",
                       backlog["id"], now_ts()))
        db.execute("UPDATE dynamic_personal_quests SET notified=1 WHERE status='active' AND progress>=target")
    character_columns = {row[1] for row in db.execute("PRAGMA table_info(characters)")}
    for name, ddl in {
        "stamina": "INTEGER DEFAULT 100",
        "stamina_updated_ts": "INTEGER DEFAULT 0",
        "combat_max_hp": "INTEGER DEFAULT 0",
        "combat_round_no": "INTEGER DEFAULT 0",
        "combat_intent": "TEXT DEFAULT ''",
        "combat_terrain": "TEXT DEFAULT ''",
        "combat_aim": "INTEGER DEFAULT 0",
        "combat_reload": "INTEGER DEFAULT 0",
        "combat_enemy_buff": "INTEGER DEFAULT 0",
        "combat_status": "TEXT DEFAULT ''",
        "combat_tactic_used": "INTEGER DEFAULT 0",
        "combat_pet_used": "INTEGER DEFAULT 0",
        "combat_signal_used": "INTEGER DEFAULT 0",
        "combat_advantage": "INTEGER DEFAULT 0",
        "pending_combat_reward": "TEXT DEFAULT ''",
        "pending_tree_started_ts": "INTEGER DEFAULT 0",
        "pending_quarry_started_ts": "INTEGER DEFAULT 0",
        "auto_eat_enabled": "INTEGER DEFAULT 0",
        "infection_relief_started_ts": "INTEGER DEFAULT 0",
        "equipped_vehicle": "TEXT",
    }.items():
        if name not in character_columns:
            db.execute(f"ALTER TABLE characters ADD COLUMN {name} {ddl}")
    db.execute("""UPDATE characters SET combat_max_hp=COALESCE(combat_max_hp,0),
                  stamina=MIN(100,MAX(0,COALESCE(stamina,100))),
                  stamina_updated_ts=COALESCE(stamina_updated_ts,0),
                  combat_round_no=COALESCE(combat_round_no,0),
                  combat_intent=COALESCE(combat_intent,''),
                  combat_terrain=COALESCE(combat_terrain,''),
                  combat_aim=COALESCE(combat_aim,0),
                  combat_reload=COALESCE(combat_reload,0),
                  combat_enemy_buff=COALESCE(combat_enemy_buff,0),
                  combat_status=COALESCE(combat_status,''),
                  combat_tactic_used=COALESCE(combat_tactic_used,0),
                  combat_pet_used=COALESCE(combat_pet_used,0),
                  combat_signal_used=COALESCE(combat_signal_used,0),
                  combat_advantage=COALESCE(combat_advantage,0),
                  pending_combat_reward=COALESCE(pending_combat_reward,'')""")
    if not db.execute("SELECT 1 FROM world_state WHERE id=1").fetchone():
        db.execute("INSERT INTO world_state (id, day_count, day_started_ts, last_tick_ts) VALUES (1,1,?,?)",
                    (now_ts(), now_ts()))
    # 旧世界不会等到下一次商人整批刷新才出现燃油；迁移完成后立刻保证一批可购买库存。
    db.execute("""INSERT OR IGNORE INTO merchant_stock(resource_key,price,stock_amount)
                  VALUES('fuel',?,20)""", (MERCHANT_PRICE,))
    db.commit()
    db.close()

# ── 登录辅助 ───────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        user = current_user() if S.get("user_id") else None
        if not user:
            S.clear()
            return redirect(url_for("login"))
        if not user["approved"]:
            return redirect(url_for("pending_approval"))
        return f(*a, **kw)
    return wrapper

def current_user():
    uid = S.get("user_id")
    if not uid:
        return None
    return q("SELECT * FROM users WHERE id=?", (uid,), one=True)

@app.context_processor
def inject_is_admin():
    user = current_user()
    announcements = q("SELECT * FROM server_announcements ORDER BY id DESC LIMIT 8") if user else []
    ch = current_character() if user else None
    unread_mail = (q("SELECT COUNT(*) c FROM player_mail WHERE to_character_id=? AND is_read=0",
                     (ch["id"],), one=True)["c"] if ch else 0)
    return {"is_admin": bool(user and user["username"] == ADMIN_USERNAME),
            "server_announcements": announcements, "display_name": display_name,
            "objective_label_for": objective_label_for, "unread_mail_count": unread_mail}

def current_character():
    uid = S.get("user_id")
    if not uid:
        return None
    return q("SELECT * FROM characters WHERE user_id=? AND status='alive' ORDER BY id DESC LIMIT 1",
              (uid,), one=True)

def profile_for(character_id):
    return q("SELECT * FROM character_profiles WHERE character_id=?", (character_id,), one=True)

def display_name(ch):
    if not ch:
        return ""
    nickname = ch["nickname"] if "nickname" in ch.keys() else None
    if nickname is None:
        profile = profile_for(ch["id"])
        nickname = profile["nickname"] if profile else ""
    return f"{ch['name']}（{nickname}）" if nickname else ch["name"]

def has_trait(ch, trait_key):
    profile = profile_for(ch["id"])
    return bool(profile and trait_key in (profile["trait_a"], profile["trait_b"]))

def settle_stamina(ch):
    """按真实时间温和恢复体力；不会因为离线而产生负面结算。"""
    ts = now_ts()
    current = max(0, min(STAMINA_MAX, ch["stamina"]))
    updated = ch["stamina_updated_ts"] or ts
    recovered = max(0, (ts - updated) // STAMINA_RECOVERY_SECONDS)
    if recovered:
        current = min(STAMINA_MAX, current + recovered)
        next_updated = ts if current >= STAMINA_MAX else updated + recovered * STAMINA_RECOVERY_SECONDS
        run("UPDATE characters SET stamina=?,stamina_updated_ts=? WHERE id=?",
            (current, next_updated, ch["id"]))
        return q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    if not ch["stamina_updated_ts"]:
        run("UPDATE characters SET stamina_updated_ts=? WHERE id=?", (ts, ch["id"]))
        return q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    return ch

def change_stamina(ch, amount, reason=""):
    ch = settle_stamina(ch)
    before = ch["stamina"]
    after = max(0, min(STAMINA_MAX, before + amount))
    if after != before:
        run("UPDATE characters SET stamina=?,stamina_updated_ts=? WHERE id=?",
            (after, now_ts(), ch["id"]))
        if reason:
            log_action(ch["id"], "stamina", f"{reason} {after-before:+d}")
    return q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True), after - before

def spend_stamina(ch, cost, reason=""):
    fresh, changed = change_stamina(ch, -max(0, cost), reason)
    return fresh, -changed

def restore_stamina(ch, amount, reason=""):
    fresh, changed = change_stamina(ch, max(0, amount), reason)
    return fresh, changed

def stamina_state(value):
    if value >= 70:
        return ("🟢 精力充足", "身体状态很好，适合远行。")
    if value >= 30:
        return ("🟡 有些疲惫", "仍能正常行动，最好开始考虑返程。")
    if value > 0:
        return ("🟠 过度劳累", "采集与攻击效率下降，逃跑更困难，也更容易受伤。")
    return ("🔴 体力透支", "仍可行动，但效率、脱离能力和伤势风险都会明显恶化。")

def need_character(f):
    @wraps(f)
    def wrapper(*a, **kw):
        ch = current_character()
        if not ch:
            return redirect(url_for("new_character"))
        return f(ch, *a, **kw)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        user = current_user()
        if not user or user["username"] != ADMIN_USERNAME:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

# ── 世界状态 ───────────────────────────────────────────────────────────────

def get_world_state():
    return q("SELECT * FROM world_state WHERE id=1", one=True)

def is_night(ws=None):
    ws = ws or get_world_state()
    elapsed = (now_ts() - ws["day_started_ts"]) % DAY_SECONDS
    return elapsed >= int(DAY_SECONDS * DAY_RATIO)

# ── 区域噪声、长期威胁与夜袭预警 ─────────────────────────────────────────

REGION_SIZE = 5
REGION_NOISE_DECAY_PER_DAY = 8
# 威胁衰减原来是-3/天，但衰减公式里"噪声残留"最多能给威胁反加6(lingering，noise封顶100时
# 100//15=6)，只要区域噪声长期不低(几乎所有活跃区域都是这样)，净变化就是持平甚至倒涨——
# 玩家反馈"威胁只会涨不会跌，时间久了全图变红"，根源就在这，衰减必须明显盖过lingering的上限。
REGION_THREAT_DECAY_PER_DAY = 10
NIGHT_RAID_WARNING_SECONDS = 15 * 60
# 二十节:夜袭原来每个昼夜循环(现实约1小时)都结算一次，玩家反馈"必须时刻在线"；
# 改成每隔几个循环才真正打一次，其余夜晚只是氛围性的"平静夜"，不结算不预警。
NIGHT_RAID_EVERY_N_DAYS = 4

def is_raid_night(day_count):
    return day_count % NIGHT_RAID_EVERY_N_DAYS == 0

# 二十三节:玩家反馈想要一段现实时间的"安全窗口"，凌晨0点到早上10点(北京时间)不结算
# 夜袭，不用大半夜爬起来守家。这里用的是真实时钟小时，不是游戏内昼夜。固定按UTC+8算，
# 不依赖运行服务器的操作系统时区设置(避免部署环境的时区配置漂移导致这个安全窗口跟着偏移)。
NIGHT_RAID_QUIET_HOUR_START = 0
NIGHT_RAID_QUIET_HOUR_END = 10
NIGHT_RAID_QUIET_TZ_OFFSET_SECONDS = 8 * 3600

def in_night_raid_quiet_hours(ts=None):
    ts = now_ts() if ts is None else ts
    hour = time.gmtime(ts + NIGHT_RAID_QUIET_TZ_OFFSET_SECONDS).tm_hour
    return NIGHT_RAID_QUIET_HOUR_START <= hour < NIGHT_RAID_QUIET_HOUR_END

def region_coords(x, y):
    return x // REGION_SIZE, y // REGION_SIZE

def ensure_map_region(x, y):
    rx, ry = region_coords(x, y)
    ws = get_world_state()
    baseline = min(55, 8 + (abs(rx) + abs(ry)) * 3)
    run("""INSERT OR IGNORE INTO map_regions
           (region_x,region_y,noise,threat,last_decay_day,updated_ts)
           VALUES(?,?,0,?,?,?)""", (rx, ry, baseline, ws["day_count"], now_ts()))
    return q("SELECT * FROM map_regions WHERE region_x=? AND region_y=?",
             (rx, ry), one=True)

def region_threat_for_position(x, y):
    return ensure_map_region(x, y)

def region_threat_label(value):
    if value < 20:
        return "🟢 平静"
    if value < 40:
        return "🟡 被注视"
    if value < 60:
        return "🟠 活跃"
    if value < 80:
        return "🔴 危险"
    return "☣️ 尸群聚集"

def add_region_noise(ch, amount, reason, event_key="activity", x=None, y=None):
    if amount <= 0:
        return
    px = ch["tile_x"] if x is None else x
    py = ch["tile_y"] if y is None else y
    region = ensure_map_region(px, py)
    threat_added = max(1, int(math.ceil(amount * .6)))
    noise_cap, threat_cap = repeller_cap_for_region(region["region_x"], region["region_y"])
    run("""UPDATE map_regions
           SET noise=MIN(?,noise+?),threat=MIN(?,threat+?),updated_ts=?
           WHERE region_x=? AND region_y=?""",
        (noise_cap, amount, threat_cap, threat_added, now_ts(), region["region_x"], region["region_y"]))
    run("""INSERT INTO region_threat_events
           (region_x,region_y,character_id,event_key,noise_added,threat_added,detail,created_ts)
           VALUES(?,?,?,?,?,?,?,?)""",
        (region["region_x"], region["region_y"], ch["id"], event_key,
         amount, threat_added, reason, now_ts()))

# ── 统一电网：个人房屋和庇护所使用同一套发电、储能与战备逻辑 ─────────────

def ensure_power_grid(owner_type, owner_id):
    if owner_type not in ("house", "shelter") or not owner_id:
        return None
    run("""INSERT OR IGNORE INTO power_grids
           (owner_type,owner_id,generator_level,charge,mode,updated_ts)
           VALUES(?,?,0,0,'balanced',?)""", (owner_type, owner_id, now_ts()))
    return q("""SELECT * FROM power_grids
                WHERE owner_type=? AND owner_id=?""",
             (owner_type, owner_id), one=True)

def power_capacity(grid):
    if not grid:
        return 0
    return GENERATOR_LEVELS.get(grid["generator_level"], GENERATOR_LEVELS[0])["capacity"]

def consume_power(owner_type, owner_id, amount, detail, character_id=None,
                  critical=False):
    """原子扣电。战备模式会为普通设备保留夜袭用电；critical可动用全部储能。"""
    grid = ensure_power_grid(owner_type, owner_id)
    if not grid or grid["damaged"] or amount <= 0:
        return False
    reserve = (POWER_DEFENSE_RESERVE
               if grid["mode"] == "defense" and not critical else 0)
    if grid["charge"] - amount < reserve:
        return False
    cur = run("""UPDATE power_grids SET charge=charge-?,updated_ts=?
                 WHERE owner_type=? AND owner_id=? AND damaged=0 AND charge-?>=?""",
              (amount, now_ts(), owner_type, owner_id, amount, reserve))
    if not cur.rowcount:
        return False
    run("""INSERT INTO power_logs
           (owner_type,owner_id,character_id,event_key,power_change,detail,created_ts)
           VALUES(?,?,?,'consume',?,?,?)""",
        (owner_type, owner_id, character_id, -amount, detail, now_ts()))
    return True

def house_here_for(ch):
    return q("""SELECT * FROM houses
                WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0""",
             (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)

def homestead_home_here(ch):
    """个人生活工坊认"家"：自己的房子，或者房子已经改建成庇护所后、自己所属且站在里面的那个庇护所。
    返回(kind, row, local_ref)，kind是'house'/'shelter'/None。"""
    house = house_here_for(ch)
    if house:
        return "house", house, ("house_inventory", "house_id", house["id"])
    shelter = _my_shelter_here(ch)
    if shelter:
        return "shelter", shelter, ("shelter_inventory", "shelter_id", shelter["id"])
    return None, None, None

def local_power_for_character(ch):
    """个人生活设施接自己"家"(房子或所属庇护所)的电网；必须真正回家才能使用。"""
    kind, home, _ = homestead_home_here(ch)
    return (home, ensure_power_grid(kind, home["id"])) if home else (None, None)

def seconds_until_night_raid(ws=None):
    ws = ws or get_world_state()
    elapsed = (now_ts() - ws["day_started_ts"]) % DAY_SECONDS
    night_start = int(DAY_SECONDS * DAY_RATIO)
    return 0 if elapsed >= night_start else night_start - elapsed

def night_raid_forecast(ch, house=None, shelter=None, ws=None):
    ws = ws or get_world_state()
    region = region_threat_for_position(ch["tile_x"], ch["tile_y"])
    base = zombie_base_strength(
        dist_from_origin(ch["tile_x"], ch["tile_y"]), ws["day_count"])
    predicted = max(1, int(round(base * (1 + region["threat"] / 100))))
    if shelter and shelter["tile_x"] == ch["tile_x"] and shelter["tile_y"] == ch["tile_y"]:
        members = q("""SELECT COUNT(*) AS c FROM characters
                       WHERE shelter_id=? AND status='alive'""",
                    (shelter["id"],), one=True)["c"]
        predicted = int(round(predicted * (1 + members * .15)))
        grid = q("""SELECT * FROM power_grids
                    WHERE owner_type='shelter' AND owner_id=?""",
                 (shelter["id"],), one=True)
        powered_towers = (min(shelter["defense_tower"], grid["charge"])
                          if grid and not grid["damaged"] else 0)
        defense = (members * 10 + shelter["defense_walls"] * 20 +
                   shelter["defense_traps"] * 10 + shelter["defense_tower"] * 5 +
                   powered_towers * 10)
        exposed = max(0, predicted - defense)
    elif house:
        info = HOUSE_LEVELS.get(house["level"], HOUSE_LEVELS[1])
        remaining = predicted
        stance = house["raid_stance"] if house["raid_stance"] in RAID_STANCES else "balanced"
        if (stance != "conserve" and house["hp"] > 0 and
                house["auto_defense"] and info["counter"] > 0):
            grid = q("""SELECT * FROM power_grids
                        WHERE owner_type='house' AND owner_id=?""",
                     (house["id"],), one=True)
            ammo = q("""SELECT amount FROM house_inventory
                        WHERE house_id=? AND resource_key='ammo'""",
                     (house["id"],), one=True)
            if grid and not grid["damaged"] and grid["charge"] >= 3 and ammo and ammo["amount"] > 0:
                remaining = max(1, remaining - max(1, int(remaining * info["counter"])))
        if stance == "storage":
            remaining += 2
        elif stance == "lure":
            remaining = max(1, int(math.ceil(remaining * .75)))
        exposed = max(1, remaining - info["armor"]) if house["hp"] > 0 else predicted
    else:
        exposed = predicted
    risk = "低" if exposed <= 5 else ("中" if exposed <= 15 else ("高" if exposed <= 30 else "极高"))
    return {"region": region, "strength": predicted, "exposed": exposed,
            "risk": risk, "label": region_threat_label(region["threat"])}

# ── 地图/地块 ─────────────────────────────────────────────────────────────

def dist_from_origin(x, y):
    return max(abs(x), abs(y))

def compass_direction(dx, dy):
    """中文方位习惯东/西在前、北/南在后(比如"东北"不是"北东")。"""
    if dx == 0 and dy == 0:
        return "就在脚下"
    parts = []
    if dx > 0:
        parts.append("东")
    elif dx < 0:
        parts.append("西")
    if dy > 0:
        parts.append("北")
    elif dy < 0:
        parts.append("南")
    return "".join(parts)

def get_or_create_tile(x, y):
    tile = q("SELECT * FROM world_tiles WHERE x=? AND y=?", (x, y), one=True)
    if tile:
        return tile
    is_origin = (x == 0 and y == 0)
    roll = random.random()
    is_water = (not is_origin) and roll < WATER_TILE_CHANCE
    run("INSERT INTO world_tiles (x, y, discovered_ts, has_building, is_water) VALUES (?,?,?,0,?)",
        (x, y, now_ts(), 1 if is_water else 0))
    # 出生点小区永远是空地,不生成资源点/水域,方便新手起步不被抢
    if not is_origin and not is_water and roll < WATER_TILE_CHANCE + 0.5:
        _spawn_resource_nodes(x, y)
    return q("SELECT * FROM world_tiles WHERE x=? AND y=?", (x, y), one=True)

def _spawn_resource_nodes(x, y):
    dist = dist_from_origin(x, y)
    # 距离梯度:越远资源总量上限越高、稀有资源占比越高(四节/8.1)
    # 木材/布/金属在配方里被用到的次数远超同档的其他资源(木材36处、布24处、金属43处，
    # 对比石头9处、弹药2处)，玩家反馈这几样明显不够拿。木材和布在池子里重复放增加刷到概率，
    # 布之前甚至完全没有进过地图刷新池，只能靠废墟/战斗掉落，这里给它一个正常的地图来源。
    pool = ["wood", "wood", "cloth", "stone", "raw_food", "raw_water", "herb"]
    if dist >= 15:
        pool += ["metal", "metal", "ammo", "parts", "silver_scrap"]
    if dist >= 40 and random.random() < 0.1:
        landmark_roll = random.random()
        pool.append("electronics" if landmark_roll < 0.55 else ("old_gem" if landmark_roll < 0.82 else "resonance_material"))
    n = random.randint(1, 2)
    chosen_keys = set(random.sample(pool, min(n, len(pool))))
    for key in chosen_keys:
        rarity = RESOURCES[key][1]
        base = 20 if rarity == "normal" else (10 if rarity == "rare" else 3)
        if key in ("wood", "metal"):
            base = int(base * 1.5)  # 需求量最大的两种资源，单点上限也高一些
        max_amt = base + dist // 5
        run("""INSERT INTO resource_nodes (tile_x, tile_y, resource_key, rarity, max_amount, current_amount)
               VALUES (?,?,?,?,?,?)""", (x, y, key, rarity, max_amt, max_amt))

def tile_resource_nodes(x, y):
    return q("SELECT * FROM resource_nodes WHERE tile_x=? AND tile_y=? AND gone_forever=0", (x, y))

def tile_is_buildable(x, y):
    tile = q("SELECT * FROM world_tiles WHERE x=? AND y=?", (x, y), one=True)
    if tile and tile["has_building"]:
        return False, "这块地已经有建筑了"
    if tile and tile["is_water"]:
        return False, "这块地是水域,不能盖建筑"
    nodes = tile_resource_nodes(x, y)
    if nodes:
        return False, "这块地是资源点,不能盖建筑(九.4)"
    return True, ""

def tile_is_inhabited(x, y):
    """有房子或庇护所的地块——has_building在两者建造时都会置1，藏点不该建在这种"显眼"的地方。"""
    tile = q("SELECT has_building FROM world_tiles WHERE x=? AND y=?", (x, y), one=True)
    return bool(tile and tile["has_building"])

# ── 库存辅助 ───────────────────────────────────────────────────────────────

def inv_total(table, id_col, id_val):
    row = q(f"SELECT COALESCE(SUM(amount),0) AS t FROM {table} WHERE {id_col}=?", (id_val,), one=True)
    return row["t"]

def inv_add(table, id_col, id_val, resource_key, delta):
    db = get_db()
    row = db.execute(f"SELECT amount FROM {table} WHERE {id_col}=? AND resource_key=?", (id_val, resource_key)).fetchone()
    if row:
        new_amt = max(0, row["amount"] + delta)
        db.execute(f"UPDATE {table} SET amount=? WHERE {id_col}=? AND resource_key=?", (new_amt, id_val, resource_key))
    else:
        db.execute(f"INSERT INTO {table} ({id_col}, resource_key, amount) VALUES (?,?,?)",
                    (id_val, resource_key, max(0, delta)))
    db.commit()

def char_inv_capacity(ch):
    cap = ch["storage_capacity"]
    if has_trait(ch, "strong_back"):
        cap += 30
    if _animal_bonus_active(ch, "small_pack"):
        cap += ANIMALS["small_pack"]["storage_bonus"]
    return cap

def char_inv_list(char_id):
    return q("SELECT * FROM character_inventory WHERE character_id=? AND amount>0 ORDER BY resource_key", (char_id,))

def log_action(char_id, action, detail=""):
    run("INSERT INTO action_log (character_id, action, detail, created_ts) VALUES (?,?,?,?)",
        (char_id, action, detail, now_ts()))

# ── 家族与传承辅助 ────────────────────────────────────────────────────────

def bond_pair(char_a, char_b):
    return (min(char_a, char_b), max(char_a, char_b))

def bond_for(char_a, char_b):
    a, b = bond_pair(char_a, char_b)
    return q("SELECT * FROM player_bonds WHERE char_a=? AND char_b=?", (a, b), one=True)

def add_bond_affinity(char_a, char_b, amount):
    if not char_a or not char_b or char_a == char_b:
        return
    a, b = bond_pair(char_a, char_b)
    run("""INSERT INTO player_bonds(char_a,char_b,affinity) VALUES(?,?,?)
           ON CONFLICT(char_a,char_b) DO UPDATE SET affinity=MAX(0,affinity+?)""",
        (a, b, max(0, amount), amount))

def spouse_for(character_id):
    bond = q("""SELECT * FROM player_bonds
                WHERE married=1 AND (char_a=? OR char_b=?) LIMIT 1""",
             (character_id, character_id), one=True)
    if not bond:
        return None
    spouse_id = bond["char_b"] if bond["char_a"] == character_id else bond["char_a"]
    return q("SELECT * FROM characters WHERE id=?", (spouse_id,), one=True)

# 十九节:结伴同行——不占用庇护所名额、不要求羁绊值的临时搭档关系。
COMPANION_FLEE_BONUS = 0.08

def companion_bond_row(char_a, char_b):
    a, b = bond_pair(char_a, char_b)
    return q("SELECT * FROM companion_bonds WHERE char_a=? AND char_b=?", (a, b), one=True)

def companion_for(character_id):
    """当前生效的结伴对象(角色行)，没有就返回None。一个人同时只能有一个结伴对象。"""
    bond = q("""SELECT * FROM companion_bonds
                WHERE status='active' AND (char_a=? OR char_b=?) LIMIT 1""",
             (character_id, character_id), one=True)
    if not bond:
        return None
    other_id = bond["char_b"] if bond["char_a"] == character_id else bond["char_a"]
    return q("SELECT * FROM characters WHERE id=? AND status='alive'", (other_id,), one=True)

def child_age_days(child):
    return max(0, (now_ts() - child["born_ts"]) // DAY_SECONDS)

def child_stage(child):
    age = child_age_days(child)
    if age < 2:
        return "襁褓期"
    if age < 6:
        return "幼年期"
    if age < 12:
        return "少年期"
    return "成年期"

def _child_need_request(db_, child_id, age, need_key, message):
    db_.execute("""INSERT OR IGNORE INTO child_help_requests
                   (child_id,age_day,need_key,message,status,created_ts)
                   VALUES(?,?,?,?, 'open',?)""", (child_id, age, need_key, message, now_ts()))

def _settle_child_needs(db_, child, age):
    """每岁结算生活照料：6岁前必须由父母照顾；6岁后会先尝试自理。"""
    if child["status"] != "alive" or child["last_needs_age"] >= age:
        return
    if age == 0:
        db_.execute("UPDATE children SET last_needs_age=0 WHERE id=?", (child["id"],))
        return
    previous_age = max(0, age - 1)
    cared = db_.execute("""SELECT 1 FROM child_care_logs
                           WHERE child_id=? AND survivor_day=? LIMIT 1""",
                        (child["id"], previous_age)).fetchone()
    if age < 6:
        if not cared:
            _child_need_request(db_, child["id"], age, "care",
                                f"{child['name']}还不到6岁，需要父母准备食物和净水。")
            db_.execute("UPDATE children SET hp=MAX(1,hp-5) WHERE id=?", (child["id"],))
    elif not cared:
        inv = {r["resource_key"]: r["amount"] for r in db_.execute(
            "SELECT * FROM child_inventory WHERE child_id=? AND amount>0", (child["id"],)).fetchall()}
        food_key = "raw_food" if inv.get("raw_food", 0) else ("emergency_food" if inv.get("emergency_food", 0) else "")
        water_key = "clean_water" if inv.get("clean_water", 0) else ("raw_water" if inv.get("raw_water", 0) else "")
        if food_key and water_key:
            for key in (food_key, water_key):
                db_.execute("UPDATE child_inventory SET amount=MAX(0,amount-1) WHERE child_id=? AND resource_key=?",
                            (child["id"], key))
            db_.execute("UPDATE children SET hp=MIN(100,hp+3),care_points=care_points+1 WHERE id=?",
                        (child["id"],))
            db_.execute("""INSERT INTO child_exploration_logs
                           (child_id,age_day,outcome,detail,hp_change,created_ts)
                           VALUES(?,?,'self_care',?,3,?)""",
                        (child["id"], age, f"{child['name']}用自己攒下的物资照顾好了自己。", now_ts()))
        else:
            if not food_key:
                _child_need_request(db_, child["id"], age, "food",
                                    f"{child['name']}的食物用完了，正在向父母求助。")
            if not water_key:
                _child_need_request(db_, child["id"], age, "water",
                                    f"{child['name']}的饮水用完了，正在向父母求助。")
            db_.execute("UPDATE children SET hp=MAX(1,hp-3) WHERE id=?", (child["id"],))
    if child["hp"] < 45:
        _child_need_request(db_, child["id"], age, "medicine",
                            f"{child['name']}伤得很重，需要父母送来药品。")
    db_.execute("UPDATE children SET last_needs_age=? WHERE id=?", (age, child["id"]))

def eligible_heirs_for_user(user_id):
    return q("""SELECT c.*, p.name AS parent_name, p.id AS deceased_parent_id,
                       p.wallet AS parent_wallet, p.shelter_id AS parent_shelter_id
                FROM children c
                JOIN characters p ON p.id=c.parent_a OR p.id=c.parent_b
                WHERE p.user_id=? AND p.status='dead' AND c.status='alive'
                  AND c.successor_character_id IS NULL
                ORDER BY c.born_ts""", (user_id,))

def album_add(character_id, event_key, title, story_text, related_character_id=None, child_id=None):
    run("""INSERT INTO family_album
           (character_id,related_character_id,child_id,event_key,title,story_text,created_ts)
           VALUES(?,?,?,?,?,?,?)""",
        (character_id, related_character_id, child_id, event_key, title, story_text, now_ts()))

def close_relation(char_a, char_b, role):
    a, b = bond_pair(char_a, char_b)
    return q("""SELECT * FROM close_relationships
                WHERE char_a=? AND char_b=? AND role=?""", (a, b, role), one=True)

# 经历线索卡片原来只显示氛围文案，没写清楚具体要做什么，玩家反馈"不知道要干嘛"。
OBJECTIVE_LABELS = {
    "rescue": "完成1次附近救援(去帮HP过低或感染度过高、正在发SOS的其他玩家送医疗用品——需要真的有人处于这个状态,纯靠自己刷不出来)",
    "move": "累计移动{target}次",
    "map_note": "在地图上留一条标记/记录",
    "radio": "完成1次私人无线电联络(幸存者羁绊页面)",
    "craft": "制作1件装备或图纸物品",
    "fortune": "抽1次每日手气",
    "gather": "采集/带回{target}份物资(任意来源:采集、种树挖矿、拆废墟等都算)",
}

def objective_label_for(objective_key, target):
    template = OBJECTIVE_LABELS.get(objective_key, objective_key)
    return template.format(target=target) if "{target}" in template else template

def maybe_create_dynamic_quest(character_id, source_key, title, description,
                               objective_key, target=1, reward_key="wallet", reward_amount=10):
    existing = q("""SELECT 1 FROM dynamic_personal_quests
                    WHERE character_id=? AND source_key=? AND status='active'""",
                 (character_id, source_key), one=True)
    if not existing:
        run("""INSERT INTO dynamic_personal_quests
               (character_id,source_key,title,description,objective_key,target,reward_key,reward_amount,created_ts)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (character_id, source_key, title, description, objective_key, target,
             reward_key, reward_amount, now_ts()))

def progress_dynamic_quests(character_id, objective_key, amount=1):
    run("""UPDATE dynamic_personal_quests
           SET progress=MIN(target,progress+?)
           WHERE character_id=? AND objective_key=? AND status='active'""",
        (amount, character_id, objective_key))
    # 达标就立刻发邮件提醒+带领取按钮,不用再指望玩家自己想起去日志页翻找。notified防止同一条支线重复发信。
    for quest in q("""SELECT * FROM dynamic_personal_quests
                      WHERE character_id=? AND objective_key=? AND status='active'
                      AND progress>=target AND notified=0""", (character_id, objective_key)):
        run("UPDATE dynamic_personal_quests SET notified=1 WHERE id=?", (quest["id"],))
        reward_text = (f"钱包+{quest['reward_amount']}" if quest["reward_key"] == "wallet"
                       else f"{ITEM_NAMES.get(quest['reward_key'], quest['reward_key'])}x{quest['reward_amount']}")
        send_system_mail(character_id, "系统", f"🎯 支线完成：{quest['title']}",
                         f"{quest['description']}\n\n已经达成目标，奖励：{reward_text}。",
                         action_type="claim_dynamic_quest", action_ref=quest["id"])

def ensure_shelter_life_event(shelter_id, day_count):
    existing = q("""SELECT * FROM shelter_life_events
                    WHERE shelter_id=? AND day_count=?""", (shelter_id, day_count), one=True)
    if existing:
        return existing
    key = random.Random(f"shelter-life:{shelter_id}:{day_count}").choice(list(SHELTER_LIFE_EVENT_DEFS))
    info = SHELTER_LIFE_EVENT_DEFS[key]
    run("""INSERT OR IGNORE INTO shelter_life_events
           (shelter_id,day_count,event_key,title,description)
           VALUES(?,?,?,?,?)""", (shelter_id, day_count, key, info["title"], info["description"]))
    return q("""SELECT * FROM shelter_life_events
                WHERE shelter_id=? AND day_count=?""", (shelter_id, day_count), one=True)

def homestead_for(character_id):
    run("""INSERT OR IGNORE INTO personal_homesteads(character_id,created_ts)
           VALUES(?,?)""", (character_id, now_ts()))
    return q("SELECT * FROM personal_homesteads WHERE character_id=?", (character_id,), one=True)

def livestock_age(animal):
    return max(0, (now_ts() - animal["born_ts"]) // DAY_SECONDS)

def equipped_outfit(character_id):
    return q("""SELECT outfit_key FROM personal_outfits
                WHERE character_id=? AND equipped=1 LIMIT 1""", (character_id,), one=True)

def outfit_combat_defense(character_id):
    """穿戴的服装叠加在护甲减伤上的额外战斗减伤(乘法叠加,不会顶替护甲)。"""
    outfit = equipped_outfit(character_id)
    if not outfit:
        return 0.0
    return CLOTHING_RECIPES.get(outfit["outfit_key"], {}).get("combat_defense", 0)

def survival_workshop_for(character_id):
    run("""INSERT OR IGNORE INTO personal_survival_workshops(character_id,created_ts)
           VALUES(?,?)""", (character_id, now_ts()))
    return q("SELECT * FROM personal_survival_workshops WHERE character_id=?", (character_id,), one=True)

def can_access_cache(ch, cache):
    if cache["owner_user_id"] == ch["user_id"] or cache["owner_character_id"] == ch["id"]:
        return True
    if cache["access_mode"] != "family":
        return False
    owner = cache["owner_character_id"]
    married = bond_for(ch["id"], owner)
    close = q("""SELECT 1 FROM close_relationships WHERE status='accepted'
                 AND ((char_a=? AND char_b=?) OR (char_a=? AND char_b=?))""",
              (ch["id"], owner, owner, ch["id"]), one=True)
    return bool((married and married["married"]) or close)

def ensure_ruin_site(ch):
    site = q("SELECT * FROM ruin_sites WHERE tile_x=? AND tile_y=?",
             (ch["tile_x"], ch["tile_y"]), one=True)
    if site:
        return site
    tile = get_or_create_tile(ch["tile_x"], ch["tile_y"])
    if (tile["is_water"] or tile["has_building"] or
            tile_resource_nodes(ch["tile_x"], ch["tile_y"]) or
            (ch["tile_x"] == 0 and ch["tile_y"] == 0)):
        return None
    site_types = ["废弃公寓", "封锁商店", "烧毁维修站", "坍塌办公楼", "遗弃检查站"]
    site_type = random.Random(f"ruin:{ch['tile_x']}:{ch['tile_y']}").choice(site_types)
    cur = run("""INSERT OR IGNORE INTO ruin_sites
                 (tile_x,tile_y,site_type,discovered_by,discovered_ts)
                 VALUES(?,?,?,?,?)""",
              (ch["tile_x"], ch["tile_y"], site_type, ch["id"], now_ts()))
    site = q("SELECT * FROM ruin_sites WHERE tile_x=? AND tile_y=?",
             (ch["tile_x"], ch["tile_y"]), one=True)
    if cur.rowcount:
        for part_key in RUIN_PARTS:
            run("INSERT INTO ruin_compartments(site_id,part_key) VALUES(?,?)", (site["id"], part_key))
    return site

def _child_exploration(db_, child, age):
    """孩子每个成长日最多探索一次。失约照顾不致死，照顾值只温和降低风险。"""
    if child["status"] != "alive" or age < 6 or child["last_explore_age"] >= age:
        return
    care = child["care_points"]
    skill = child["stat_spd"] + child["stat_luck"] + min(10, age)
    danger = max(0.035, 0.12 - care * 0.002 - skill * 0.002)
    severe = max(0.008, 0.035 - care * 0.001 - age * 0.002)
    if db_.execute("SELECT 1 FROM child_outfits WHERE child_id=?", (child["id"],)).fetchone():
        danger *= .82
        severe *= .82
    roll = random.random()
    outcome, detail, hp_change, resource_key, amount = "safe", "", 0, "", 0
    if roll < severe:
        damage = random.randint(28, 52)
        hp_change = -damage
        new_hp = max(0, child["hp"] - damage)
        if new_hp <= 0:
            outcome = "death"
            detail = "在废弃高架下遭遇游荡尸群。孩子没能从这次远行回来。"
            db_.execute("""UPDATE children SET hp=0,status='dead',death_reason=?,
                           last_explore_age=? WHERE id=?""", (detail, age, child["id"]))
        else:
            outcome = "severe"
            detail = f"在塌陷建筑里遭遇危险，带着重伤回家（-{damage}HP）。"
            db_.execute("UPDATE children SET hp=?,last_explore_age=? WHERE id=?",
                        (new_hp, age, child["id"]))
    elif roll < severe + danger:
        damage = random.randint(6, 20)
        hp_change = -damage
        detail = f"翻越废墟时受了伤，但自己找到了回家的路（-{damage}HP）。"
        db_.execute("UPDATE children SET hp=MAX(1,hp-?),last_explore_age=? WHERE id=?",
                    (damage, age, child["id"]))
        outcome = "hurt"
    elif roll < 0.64:
        resource_key = random.choice(["wood", "stone", "raw_food", "raw_water", "herb",
                                      "cloth", "metal", "parts", "silver_scrap"])
        amount = random.randint(1, 2 + min(3, age // 3))
        detail = f"沿着旧路探索后平安回来，带回了{ITEM_NAMES[resource_key]}x{amount}。"
        db_.execute("""INSERT INTO child_inventory(child_id,resource_key,amount) VALUES(?,?,?)
                       ON CONFLICT(child_id,resource_key) DO UPDATE SET amount=amount+?""",
                    (child["id"], resource_key, amount, amount))
        stat_col = random.choice(["stat_str", "stat_spd", "stat_int", "stat_luck"])
        db_.execute(f"UPDATE children SET {stat_col}=MIN(20,{stat_col}+1),last_explore_age=? WHERE id=?",
                    (age, child["id"]))
        outcome = "found"
    else:
        details = [
            "远远观察了一支迁徙尸群，记下路线后安全返家。",
            "在废弃车站发现了别人的生活痕迹，但没有贸然靠近。",
            "把家附近一条隐蔽小路画进了自己的地图。",
            "听见远处的无线电杂音，决定等更有把握时再追踪。",
        ]
        detail = random.choice(details)
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        db_.execute("""UPDATE children SET tile_x=tile_x+?,tile_y=tile_y+?,
                       last_explore_age=? WHERE id=?""", (dx, dy, age, child["id"]))
    db_.execute("""INSERT INTO child_exploration_logs
                   (child_id,age_day,outcome,detail,hp_change,resource_key,amount,created_ts)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (child["id"], age, outcome, detail, hp_change, resource_key, amount, now_ts()))
    if outcome in ("hurt", "severe", "death"):
        for parent_id in (child["parent_a"], child["parent_b"]):
            exists = db_.execute("""SELECT 1 FROM dynamic_personal_quests
                                    WHERE character_id=? AND source_key=? AND status='active'""",
                                 (parent_id, f"child-danger:{child['id']}:{age}")).fetchone()
            if not exists:
                db_.execute("""INSERT INTO dynamic_personal_quests
                               (character_id,source_key,title,description,objective_key,target,
                                reward_key,reward_amount,created_ts)
                               VALUES(?,?,?,?,?,5,'wallet',14,?)""",
                            (parent_id, f"child-danger:{child['id']}:{age}",
                             "孩子没有按时回来",
                             f"{child['name']}在{age}岁探索时遭遇危险。沿着孩子留下的路线搜集5份补给。",
                             "gather", now_ts()))
            if outcome == "death":
                db_.execute("""INSERT INTO family_album
                               (character_id,child_id,event_key,title,story_text,created_ts)
                               VALUES(?,?,'child_loss','没有等到的归途',?,?)""",
                            (parent_id, child["id"],
                             f"{child['name']}在{age}岁的远行中没能回来。家族相册保留了最后一条路线。",
                             now_ts()))

# ── v0.3:日目标 / 庇护所社区循环 ─────────────────────────────────────────

DAILY_GOALS = {
    "gather":     {"name": "搜集物资", "target": 8, "unit": "份"},
    "move":       {"name": "探索地图", "target": 2, "unit": "步"},
    "northstar":  {"name": "推进北辰线路", "target": 1, "unit": "次"},
    "fortune":    {"name": "进行废土手气", "target": 1, "unit": "次"},
    "recreation": {"name": "给自己留一点时间", "target": 1, "unit": "次"},
}
DAILY_GOAL_COUNT = 3
DAILY_GOAL_WALLET_REWARD = 10
DAILY_GOAL_XP_REWARD = 5

STORY_CHAPTERS = {
    1: {"title": "第一章 · 最后一辆撤离车", "story": "撤离车已经远去，北辰却仍在杂波中重复你的坐标。先走出去，再活着回来。",
        "min_day": 1, "requirements": [("northstar_action", "完成第一次信号校准", 1), ("move", "离开小区探索", 2)]},
    2: {"title": "第二章 · 给自己留一盏灯", "story": "一张地图只有去处，没有归处。你需要留下一个能被称为“家”的角落。",
        "min_day": 2, "requirements": [("northstar_action", "累计校准北辰信号", 2), ("home", "建立房屋或布置个人角落", 1)]},
    3: {"title": "第三章 · 喝下去之前", "story": "北辰坐标穿过一片污染带。辨认一口水能不能喝，是比勇敢更早学会的事。",
        "min_day": 3, "requirements": [("northstar_action", "累计校准北辰信号", 3), ("safe_water", "亲手获得一份安全净水", 1)]},
    4: {"title": "第四章 · 地图上还有别人", "story": "墙上的警告和无线电里的呼号证明：你不是这张地图上唯一留下痕迹的人。",
        "min_day": 4, "requirements": [("northstar_action", "累计校准北辰信号", 4),
                                     ("contact", "完成一次私人联络", 1), ("map_note", "留下地图情报", 1)]},
    5: {"title": "第五章 · 旧城不会白白死去", "story": "废墟里的每一块金属都曾属于某种生活。拆下它，再让它成为能保护你的东西。",
        "min_day": 5, "requirements": [("northstar_action", "累计校准北辰信号", 5),
                                     ("ruin", "完成一次废墟拆解", 1), ("prepare", "完成一次整备或制造", 1)]},
    6: {"title": "第六章 · 你开始有所牵挂", "story": "北辰问你：如果线路恢复，你最先想让谁听见？答案可以是人，也可以是一直跟着你的动物。",
        "min_day": 6, "requirements": [("northstar_action", "累计校准北辰信号", 6), ("connection", "积累三次关系经历", 3)]},
    7: {"title": "第七章 · 守门尸群", "story": "信号源外围的尸群终于暴露位置。你可以撤退和准备，但这道门必须亲手穿过。",
        "min_day": 7, "requirements": [("northstar_action", "累计校准北辰信号", 7), ("combat", "击败北辰守门丧尸", 1)]},
    8: {"title": "终章 · 你要把声音留给谁", "story": "路、物资、技术、牵挂和战斗终于连成同一段人生。最后一次广播将由你决定。",
        "min_day": 8, "requirements": [("northstar_action", "完成八次信号校准", 8),
                                     ("move", "累计探索道路", 12), ("gather", "累计带回物资", 40),
                                     ("prepare", "累计完成整备", 2), ("connection", "累计关系经历", 3),
                                     ("combat", "累计击败丧尸", 3)]},
}

DAILY_PLANS = {
    "expedition": {"name": "🧭 远行日", "desc": "移动冷却-10%，采集额外+1，战斗脱离率+8%。"},
    "prepare": {"name": "🔧 整备日", "desc": "废墟拆解收获提高，武器磨损降低，稳守效果更强。"},
    "life": {"name": "🏠 生活日", "desc": "饭菜、饮品和照顾动物提供更多精神余裕，饮食额外恢复体力。"},
    "contact": {"name": "📻 联络日", "desc": "私人无线电联络额外获得1点信任。"},
    "recover": {"name": "🕯️ 休养日", "desc": "选择时立即恢复HP、精神余裕和30点体力。"},
}

NORTHSTAR_ACTIONS = {
    "scout": {
        "name": "🧭 侦察信号坐标",
        "outcomes": [("wood", 3, "你沿信号边缘找到一条安全路线，并带回木材。"),
                     ("raw_food", 2, "你在坐标附近发现尚未腐坏的密封食材。"),
                     ("wallet", 5, "你从废弃收费站找到仍可流通的旧货币。")]},
    "decode": {
        "name": "📻 破解广播杂波",
        "outcomes": [("parts", 1, "你拆出一枚可用于校准频率的机械零件。"),
                     ("wallet", 6, "你解出一段旧时代物资兑换码。"),
                     ("clean_water", 1, "广播指向一处仍有存货的净水柜。")]},
    "search": {
        "name": "🔦 搜索失联中继站",
        "outcomes": [("bandage", 1, "你在中继站急救箱里找到一卷绷带。"),
                     ("emergency_food", 1, "你从值班室夹层找到一份应急食品。"),
                     ("wallet", 7, "你回收了中继站里仍有价值的旧部件。")]},
}

def survivor_day(ch):
    return max(1, (now_ts() - ch["created_ts"]) // DAY_SECONDS + 1)

def daily_plan_for(ch):
    return q("""SELECT * FROM daily_plans WHERE character_id=? AND survivor_day=?""",
             (ch["id"], survivor_day(ch)), one=True)

def has_daily_plan(ch, plan_key):
    plan = daily_plan_for(ch)
    return bool(plan and plan["plan_key"] == plan_key)

RECREATION_DAILY_DECAY = 6
RECREATION_ACTIVITIES = {
    "quiet": ("🕯️ 安静休息", "什么也不完成，只让呼吸慢下来。", 10),
    "corner": ("🏠 整理房间角落", "擦去灰尘，把仍珍惜的东西放回原位。", 12),
    "album": ("📸 整理末日相册", "把一路留下的照片和故事重新排好。", 12),
    "radio": ("📻 听一段旧广播", "在杂波和旧歌之间确认世界仍有声音。", 11),
    "family": ("👨‍👩‍👧 和家人待一会儿", "不谈补给和路线，只分享今天发生的小事。", 14),
    "animal": ("🐾 陪伴动物", "给熟悉的伙伴梳毛，听它在身边呼吸。", 13),
}

def wellbeing_for(character_id, ch=None):
    if ch is None:
        ch = q("SELECT * FROM characters WHERE id=?", (character_id,), one=True)
    day = survivor_day(ch) if ch else 1
    run("""INSERT OR IGNORE INTO character_wellbeing
           (character_id,recreation,last_settled_day,updated_ts) VALUES(?,70,?,?)""",
        (character_id, day, now_ts()))
    return q("SELECT * FROM character_wellbeing WHERE character_id=?", (character_id,), one=True)

def recreation_gain(ch, amount, reason=""):
    if amount <= 0:
        return 0
    before = wellbeing_for(ch["id"], ch)
    new_value = min(100, before["recreation"] + amount)
    gained = new_value - before["recreation"]
    state = "stable" if new_value >= 30 else ("strained" if new_value >= 15 else "critical")
    run("""UPDATE character_wellbeing SET recreation=?,mental_state=?,updated_ts=?
           WHERE character_id=?""", (new_value, state, now_ts(), ch["id"]))
    if gained and reason:
        log_action(ch["id"], "recreation_gain", f"{reason} +{gained}")
    return gained

def recreation_state(value):
    if value >= 70:
        return ("🌤️ 充实", "精神有余裕，今天不需要再特意安排娱乐。")
    if value >= 30:
        return ("🕯️ 平稳", "还能维持自己的节奏；生活活动会自然补充娱乐。")
    if value >= 15:
        return ("🌫️ 紧绷", "长期只有生存任务，注意力已经开始变窄。")
    if value > 0:
        return ("⚠️ 濒临崩溃", "每天结算时有小概率发生精神崩溃。")
    return ("🆘 精神枯竭", "崩溃概率明显上升；严重事故可能致命。")

def set_combat_preparation(ch, kind, recipe_key):
    """吃下的料理/饮品在角色当天转化为一次温和战备，不另耗行动次数。"""
    if kind not in ("food", "drink"):
        return
    day = survivor_day(ch)
    run("""INSERT INTO character_combat_preparations
           (character_id,survivor_day,food_key,drink_key,updated_ts)
           VALUES(?,?,?,?,?)
           ON CONFLICT(character_id) DO UPDATE SET
             survivor_day=excluded.survivor_day,
             food_key=CASE WHEN ?='food' THEN ? ELSE
                       CASE WHEN character_combat_preparations.survivor_day=excluded.survivor_day
                            THEN character_combat_preparations.food_key ELSE '' END END,
             drink_key=CASE WHEN ?='drink' THEN ? ELSE
                        CASE WHEN character_combat_preparations.survivor_day=excluded.survivor_day
                             THEN character_combat_preparations.drink_key ELSE '' END END,
             updated_ts=excluded.updated_ts""",
        (ch["id"], day, recipe_key if kind == "food" else "",
         recipe_key if kind == "drink" else "", now_ts(),
         kind, recipe_key, kind, recipe_key))

def combat_preparation_for(ch):
    row = q("""SELECT * FROM character_combat_preparations
               WHERE character_id=? AND survivor_day=?""",
            (ch["id"], survivor_day(ch)), one=True)
    food = FOOD_RECIPES.get(row["food_key"]) if row and row["food_key"] else None
    drink = DRINK_RECIPES.get(row["drink_key"]) if row and row["drink_key"] else None
    if row and row["food_key"] == "cooked_food":
        food = {"name": ITEM_NAMES["cooked_food"], "skill": 0}
    return {
        "row": row, "food": food, "drink": drink,
        "damage_bonus": min(.14, .06 + food.get("skill", 0) * .01) if food else 0,
        "guard_bonus": min(.08, .03 + food.get("skill", 0) * .006) if food else 0,
        "crit_bonus": min(.12, .04 + drink.get("skill", 0) * .01) if drink else 0,
        "flee_bonus": min(.10, .04 + drink.get("skill", 0) * .008) if drink else 0,
    }

def active_injuries(character_id):
    return q("""SELECT * FROM character_injuries
                WHERE character_id=? AND status='active' ORDER BY id""",
             (character_id,))

def has_active_injury(character_id, injury_key):
    return bool(q("""SELECT 1 FROM character_injuries
                     WHERE character_id=? AND injury_key=? AND status='active'""",
                  (character_id, injury_key), one=True))

def treat_injuries(character_id, item_key):
    allowed = ("bleeding",) if item_key == "bandage" else tuple(INJURY_DEFS)
    placeholders = ",".join("?" for _ in allowed)
    cur = run(f"""UPDATE character_injuries SET status='treated',treated_ts=?
                   WHERE character_id=? AND status='active'
                     AND injury_key IN ({placeholders})""",
              (now_ts(), character_id, *allowed))
    return cur.rowcount

def maybe_add_combat_injury(ch, intent, guarded, source_name):
    if guarded:
        return None
    injury_key = {"bite": "bleeding", "pounce": "sprain",
                  "charge": "bruised", "spit": "bleeding"}.get(intent)
    stamina_risk = .10 if ch["stamina"] <= 0 else (.06 if ch["stamina"] < 30 else 0)
    if not injury_key or random.random() >= .16 + stamina_risk or has_active_injury(ch["id"], injury_key):
        return None
    run("""INSERT INTO character_injuries
           (character_id,injury_key,source_text,created_ts)
           VALUES(?,?,?,?)""", (ch["id"], injury_key, f"{source_name}的攻击", now_ts()))
    return injury_key

RADIO_NPCS = {
    "qiao": {"name": "乔医生", "call": "白塔-7", "unlock": 1, "aura": "克制、可靠",
             "lines": ["先报伤势，再说英雄主义。", "今天有人在北边点了一盏灯。至少不是所有信号都在骗人。", "我把你的频率写进值班本了。别让我划掉。"]},
    "yan": {"name": "严野", "call": "灰狼", "unlock": 1, "aura": "嘴硬的废土向导",
            "lines": ["路不会消失，只会被沙盖住。", "你走过的坐标我看了，方向还算聪明。", "真到北辰那天，记得给我留个能停车的位置。"]},
    "ning": {"name": "宁遥", "call": "纸鸢", "unlock": 2, "aura": "温柔的旧城教师",
             "lines": ["今天的孩子们学会了写自己的名字。", "广播里听见你的脚步声了，很轻。", "如果世界会重新开始，我希望第一课不是如何躲藏。"]},
    "luo": {"name": "骆冰", "call": "零度", "unlock": 3, "aura": "冷静的气象员",
            "lines": ["风向变了，明天别走低地。", "我不相信预兆，只相信气压和重复出现的信号。", "北辰附近的云层有规律，那下面一定还有东西在运转。"]},
    "su": {"name": "苏弦", "call": "旧唱片", "unlock": 4, "aura": "神秘的广播主持人",
           "lines": ["下一首歌不存在了，所以我用口哨代替。", "有人托我问候你，但没留下名字。", "等线路恢复，我想做第一期真正有人听的节目。"]},
    "he": {"name": "何砚", "call": "铆钉", "unlock": 5, "aura": "寡言的机械师",
            "lines": ["坏掉不等于报废。人也一样。", "你带回来的零件型号，我十年前修过。", "北辰的中继机不是死了，只是缺一个肯爬上去的人。"]},
    "mei": {"name": "梅朔", "call": "夜航", "unlock": 6, "aura": "真假难辨的情报贩子",
             "lines": ["免费情报：今晚别相信三短一长的敲门声。", "我卖过你的坐标，也替你买了回来。扯平。", "北辰最后一段密钥，我可能见过。也可能只是想让你继续听。"]},
    "an": {"name": "安禾", "call": "归巢", "unlock": 7, "aura": "失踪多年的搜救员",
            "lines": ["收到请回答。这里还有一个活人。", "你的声音和我记忆里某个人很像。", "如果你抵达北辰，替所有没能回去的人回答一次。"]},
}

EXPERIENCE_TAGS = {
    "first_steps": ("👣 小区之外", "第一次离开出生点"),
    "roadworn": ("🛣️ 风尘旅人", "累计移动10步"),
    "scavenger_50": ("🎒 废墟拾荒者", "累计采集50份物资"),
    "first_blood": ("🩸 第一次还手", "亲手击败第一只丧尸"),
    "scarred": ("🩹 留疤的人", "曾在重伤状态下活下来"),
    "rescuer": ("🆘 应答者", "完成过一次玩家救援"),
    "home_maker": ("🕯️ 有灯的房间", "亲手建成个人房子"),
    "northstar": ("📡 北辰联络员", "完成八章北辰主线"),
}

ROOM_CORNERS = {
    "photo_wall": ("🖼️ 褪色照片墙", "墙上贴着旧世界照片，边角被反复摩挲。"),
    "radio_desk": ("📻 收音机工作台", "每一段杂波都被记在摊开的笔记本里。"),
    "plant": ("🌱 铁罐植物", "一株不知名的绿芽从旧罐头盒里探出来。"),
    "weapon_rack": ("🗡️ 整齐武器架", "工具和武器按使用顺序安静排列。"),
    "pet_nest": ("🐾 伙伴的小窝", "旧毯子上残留着熟悉的体温。"),
    "books": ("📚 旧书角", "几本缺页的书被防水布仔细包好。"),
    "map_table": ("🗺️ 路线地图桌", "地图上每一个圈都代表一次平安归来。"),
    "music": ("🎵 手摇唱机", "唱针偶尔跳动，但仍能放完半首旧歌。"),
}

STORY_CHOICE_OPTIONS = {
    1: [("answer", "回应陌生信号", "你选择让对方知道这里还有活人。"), ("listen", "保持静默监听", "你先学会辨认危险，再决定相信谁。")],
    2: [("lamp", "为归来的人留灯", "你把家理解成一盏等人回来的灯。"), ("lock", "为最坏的时候上锁", "你把家理解成一道保护重要之物的门。")],
    3: [("share_water", "标记安全水源", "你愿意让后来者也喝到干净的水。"), ("reserve_water", "保留净水路线", "你先确保自己和牵挂的人能够活下去。")],
    4: [("faith", "先相信呼号", "你愿意冒一点风险，让陌生声音成为关系。"), ("proof", "先验证坐标", "你用证据抵抗废土制造的假希望。")],
    5: [("memory", "保留废墟旧物", "你认为旧世界留下的不只有可拆卸材料。"), ("utility", "全部用于整备", "你相信活下来才有资格纪念过去。")],
    6: [("promise", "说出想让谁听见", "你承认牵挂会让人脆弱，也会让人回家。"), ("protect", "把名字留在心里", "你选择用行动保护牵挂，而不把名字交给电波。")],
    7: [("hold", "守住入口", "你选择成为后来者可以依靠的门。"), ("breakthrough", "主动突破", "你选择把危险终结在抵达之前。")],
    8: [("broadcast", "向所有频率广播", "你把北辰变成所有幸存者都能找到的灯。"), ("home", "只向归途频道回答", "你把最后一句话留给仍在寻找你的人。")],
}

def award_tag(character_id, tag_key, detail=""):
    if tag_key in EXPERIENCE_TAGS:
        run("""INSERT OR IGNORE INTO character_tags(character_id,tag_key,detail,earned_ts)
               VALUES(?,?,?,?)""", (character_id, tag_key, detail, now_ts()))

def remember_location(character_id, x, y, note=""):
    run("""INSERT INTO character_location_memories
           (character_id,tile_x,tile_y,first_visited_ts,last_visited_ts,visit_count,last_memory)
           VALUES(?,?,?,?,?,1,?)
           ON CONFLICT(character_id,tile_x,tile_y) DO UPDATE SET
             last_visited_ts=excluded.last_visited_ts,visit_count=visit_count+1,
             last_memory=CASE WHEN excluded.last_memory<>'' THEN excluded.last_memory ELSE last_memory END""",
        (character_id, x, y, now_ts(), now_ts(), note))

def current_mood(ch, weather):
    wellbeing = wellbeing_for(ch["id"], ch)
    if wellbeing["recreation"] < 15:
        return ("⚠️ 神经紧绷", "你开始把每一阵杂音都听成威胁。现在最重要的不是多完成一件事，而是停下来。")
    if wellbeing["recreation"] < 30:
        return ("🌫️ 心事重重", "身体还能行动，精神却已经很久没有真正松开。")
    if ch["hp"] <= 35:
        return ("🩹 咬牙坚持", "伤口提醒你放慢一点，但你还没有准备倒下。")
    if ch["infection"] >= 50:
        return ("☣️ 忐忑", "每一次发冷都让你想起感染意味着什么。")
    if ch["hunger"] < 30 or ch["thirst"] < 30:
        return ("🥀 疲惫", "身体比广播更诚实地要求一次休息。")
    if ch["tamed_animal_key"]:
        return ("🐾 有所牵挂", "回头时总能看见一个熟悉的影子，废土没那么空了。")
    if weather["key"] in ("storm", "fog"):
        return ("🌫️ 警觉", "坏天气让远处的一切都像某种伏击。")
    moods = [("🕯️ 平静", "今天至少还有一盏灯为你亮着。"),
             ("📡 期待", "杂波深处似乎有人正准备回答。"),
             ("🧭 专注", "下一段路已经在脑海里走过很多遍。")]
    return random.Random(f"mood:{ch['id']}:{survivor_day(ch)}").choice(moods)

def refresh_experience_tags(ch):
    counters = {r["counter_key"]: r["value"] for r in q(
        "SELECT * FROM story_counters WHERE character_id=?", (ch["id"],))}
    if counters.get("move", 0) >= 1:
        award_tag(ch["id"], "first_steps")
    if counters.get("move", 0) >= 10:
        award_tag(ch["id"], "roadworn")
    if counters.get("gather", 0) >= 50:
        award_tag(ch["id"], "scavenger_50")
    if counters.get("combat", 0) >= 1:
        award_tag(ch["id"], "first_blood")
    if counters.get("rescue", 0) >= 1:
        award_tag(ch["id"], "rescuer")
    if ch["hp"] <= 40:
        award_tag(ch["id"], "scarred")
SIDE_QUESTS = {
    "sq_move": {"name": "道路测绘", "event": "move", "target": 8, "desc": "移动探索8步"},
    "sq_gather": {"name": "补充库存", "event": "gather", "target": 25, "desc": "采集25份物资"},
    "sq_craft": {"name": "工作台值班", "event": "craft", "target": 2, "desc": "完成2次制作"},
    "sq_deposit": {"name": "社区后勤", "event": "deposit", "target": 20, "desc": "向庇护所仓库存入20份物资"},
    "sq_event": {"name": "沿途见闻", "event": "world_event", "target": 2, "desc": "处理2次探索事件"},
    "sq_note": {"name": "共享情报", "event": "map_note", "target": 2, "desc": "留下2条地图留言"},
    "sq_rescue": {"name": "生命线", "event": "rescue", "target": 1, "desc": "完成1次附近救援"},
    "sq_disaster": {"name": "前线轮班", "event": "disaster", "target": 3, "desc": "参与3次全服灾害行动"},
    "sq_commission": {"name": "靠谱的交付者", "event": "commission", "target": 1, "desc": "完成1份玩家委托"},
    "sq_radio": {"name": "追踪杂波", "event": "radio", "target": 4, "desc": "进行4次无线电寻宝"},
    "sq_visit": {"name": "邻里往来", "event": "visit", "target": 2, "desc": "拜访2次庇护所"},
    "sq_fish": {"name": "今天吃鱼", "event": "fish", "target": 2, "desc": "钓到2条鱼"},
}

def active_daily_goal_keys(character_id, day_count):
    keys = list(DAILY_GOALS)
    rng = random.Random(f"modaya2:{character_id}:{day_count}")
    rng.shuffle(keys)
    return keys[:DAILY_GOAL_COUNT]

def record_daily_progress(character_id, goal_key, amount=1):
    day = get_world_state()["day_count"]
    if goal_key not in active_daily_goal_keys(character_id, day):
        return
    run("""INSERT INTO daily_goal_progress(character_id,day_count,goal_key,progress)
           VALUES(?,?,?,?)
           ON CONFLICT(character_id,day_count,goal_key)
           DO UPDATE SET progress=progress+excluded.progress""",
        (character_id, day, goal_key, max(0, amount)))
    info = DAILY_GOALS[goal_key]
    row = q("""SELECT * FROM daily_goal_progress
               WHERE character_id=? AND day_count=? AND goal_key=?""",
            (character_id, day, goal_key), one=True)
    if row and row["progress"] >= info["target"] and not row["claimed"]:
        cur = run("""UPDATE daily_goal_progress SET claimed=1
                     WHERE character_id=? AND day_count=? AND goal_key=? AND claimed=0""",
                  (character_id, day, goal_key))
        if cur.rowcount:
            run("UPDATE characters SET wallet=wallet+? WHERE id=?",
                (DAILY_GOAL_WALLET_REWARD, character_id))
            fresh = q("SELECT * FROM characters WHERE id=?", (character_id,), one=True)
            if fresh:
                grant_xp(fresh, DAILY_GOAL_XP_REWARD)
                log_action(character_id, "daily_suggestion_complete",
                           f"{goal_key}: wallet+{DAILY_GOAL_WALLET_REWARD}, xp+{DAILY_GOAL_XP_REWARD}")

def ensure_side_quests(character_id, exclude=()):
    active = q("SELECT * FROM side_quests WHERE character_id=? AND status='active'", (character_id,))
    existing = {r["quest_key"] for r in active}
    available = [k for k in SIDE_QUESTS if k not in existing and k not in set(exclude)]
    random.shuffle(available)
    selected = []
    solo_core = ["sq_move", "sq_gather", "sq_note"]
    if not active:
        selected = [k for k in solo_core if k in available][:2]
    elif not existing.intersection(solo_core):
        selected = [next((k for k in solo_core if k in available), "")]
        selected = [k for k in selected if k]
    selected += [k for k in available if k not in selected][:max(0, 3 - len(active) - len(selected))]
    for key in selected:
        info = SIDE_QUESTS[key]
        run("""INSERT INTO side_quests(character_id,quest_key,target,created_ts)
               VALUES(?,?,?,?)""", (character_id, key, info["target"], now_ts()))

def record_long_progress(character_id, event_key, amount=1):
    amount = max(0, amount)
    if amount <= 0:
        return
    run("""INSERT INTO story_counters(character_id,counter_key,value) VALUES(?,?,?)
           ON CONFLICT(character_id,counter_key) DO UPDATE SET value=value+excluded.value""",
        (character_id, event_key, amount))
    progress_dynamic_quests(character_id, event_key, amount)
    ensure_side_quests(character_id)
    for key, info in SIDE_QUESTS.items():
        if info["event"] == event_key:
            run("""UPDATE side_quests SET progress=MIN(target,progress+?)
                   WHERE character_id=? AND quest_key=? AND status='active'""",
                (amount, character_id, key))

def _story_counter_floor(character_id, key, value):
    if value <= 0:
        return
    run("""INSERT INTO story_counters(character_id,counter_key,value) VALUES(?,?,?)
           ON CONFLICT(character_id,counter_key) DO UPDATE SET value=MAX(value,excluded.value)""",
        (character_id, key, value))

def backfill_story_integration(ch):
    """把旧版本已经发生的生活经历映射到新章节，升级后不要求玩家重做。"""
    home = q("""SELECT
                (SELECT COUNT(*) FROM character_room_corners WHERE character_id=?) +
                (SELECT COUNT(*) FROM houses WHERE owner_user_id=? AND abandoned=0) AS c""",
             (ch["id"], ch["user_id"]), one=True)["c"]
    safe_water = q("""SELECT
                      (SELECT COUNT(*) FROM tested_water_samples
                       WHERE character_id=? AND status='treated') +
                      (SELECT COALESCE(SUM(amount),0) FROM character_inventory
                       WHERE character_id=? AND resource_key='clean_water') AS c""",
                   (ch["id"], ch["id"]), one=True)["c"]
    contact = q("SELECT COUNT(*) AS c FROM npc_contact_logs WHERE character_id=?",
                (ch["id"],), one=True)["c"]
    ruin = q("SELECT COUNT(*) AS c FROM ruin_dismantle_logs WHERE character_id=?",
             (ch["id"],), one=True)["c"]
    crafting = q("""SELECT
                    (SELECT COUNT(*) FROM life_crafting_logs WHERE character_id=?) +
                    (SELECT COUNT(*) FROM weapon_maintenance WHERE character_id=?) +
                    (SELECT COUNT(*) FROM supply_caches WHERE owner_character_id=?) AS c""",
                 (ch["id"], ch["id"], ch["id"]), one=True)["c"] + ruin
    connection = contact + q("""SELECT
                   (SELECT COUNT(*) FROM bond_interactions WHERE from_char=?) +
                   (SELECT COUNT(*) FROM child_care_logs WHERE parent_character_id=?) AS c""",
                 (ch["id"], ch["id"]), one=True)["c"]
    for key, value in {
        "home": home, "safe_water": safe_water, "contact": contact,
        "ruin": ruin, "prepare": crafting, "connection": connection,
    }.items():
        _story_counter_floor(ch["id"], key, value)

def daily_goals_for(ch, day_count):
    rows = {r["goal_key"]: r for r in q(
        "SELECT * FROM daily_goal_progress WHERE character_id=? AND day_count=?",
        (ch["id"], day_count))}
    result = []
    for key in active_daily_goal_keys(ch["id"], day_count):
        info = DAILY_GOALS[key]
        row = rows.get(key)
        progress = min(info["target"], row["progress"] if row else 0)
        result.append({"key": key, **info, "progress": progress,
                       "claimed": bool(row and row["claimed"])})
    return result

def add_shelter_feed(shelter_id, entry_type, author_name, content, character_id=None):
    run("""INSERT INTO shelter_feed(shelter_id,character_id,entry_type,author_name,content,created_ts)
           VALUES(?,?,?,?,?,?)""",
        (shelter_id, character_id, entry_type, author_name, content, now_ts()))

WORLD_EVENT_CHANCE = 0.12
WORLD_EVENTS = {
    "locked_store": {
        "title": "🔒 被锁住的便利店",
        "text": "卷帘门后似乎还有没被搬空的货架。强行破门可能惊动附近的丧尸，也可以从侧窗寻找入口。",
        "choices": [("force", "用力量破门"), ("inspect", "用智慧找入口"), ("leave", "安全离开")],
    },
    "radio_signal": {
        "title": "📻 断续的求救信号",
        "text": "废弃收音机里传出一串坐标和重复杂音。它可能指向物资，也可能只是诱饵。",
        "choices": [("decode", "分析信号"), ("follow", "凭幸运追踪"), ("leave", "关闭收音机")],
    },
    "field_cache": {
        "title": "🎒 路边的旧背包",
        "text": "背包压在一具无法辨认的遗骸下面，拉链完好，周围却有新鲜拖痕。",
        "choices": [("quick", "快速拿走"), ("careful", "仔细检查"), ("leave", "不碰它")],
    },
}

WORLD_GOAL_DEFS = [
    {"key": "wood_drive", "name": "重建外围路障", "resource_key": "wood", "target": 180,
     "description": "全服提交木材，修复通往远方的道路。"},
    {"key": "food_drive", "name": "建立应急粮仓", "resource_key": "raw_food", "target": 140,
     "description": "全服提交生鲜，为下一次灾害储备口粮。"},
    {"key": "legend_fish", "name": "传说目标：深渊幼鲲", "resource_key": None, "target": 3,
     "description": "全服合力钓到3条传说级深渊幼鲲。"},
    {"key": "elite_hunt", "name": "传说目标：重装尸群", "resource_key": None, "target": 12,
     "description": "全服击败12只高血量丧尸。"},
    {"key": "landmark_search", "name": "传说目标：失落地标", "resource_key": None, "target": 8,
     "description": "从地标资源点带回8批珍贵发现。"},
]
WORLD_GOAL_CYCLE_DAYS = 7

WEATHER_TYPES = [
    {"key": "clear", "name": "☀️ 晴朗", "text": "视野良好，适合远行。", "move": 1.0, "danger": 1.0},
    {"key": "rain", "name": "🌧️ 冷雨", "text": "道路湿滑，移动稍慢。", "move": 1.15, "danger": 1.0},
    {"key": "fog", "name": "🌫️ 毒雾", "text": "视野很差，遭遇危险的概率上升。", "move": 1.10, "danger": 1.3},
    {"key": "storm", "name": "⛈️ 风暴", "text": "不适合远行，赶路明显变慢。", "move": 1.35, "danger": 1.15},
    {"key": "cold", "name": "❄️ 寒潮", "text": "行动迟缓，但丧尸也不活跃。", "move": 1.20, "danger": 0.8},
]

def weather_for_day(day_count):
    rng = random.Random(f"modaya2-weather:{day_count}")
    return rng.choices(WEATHER_TYPES, weights=[38, 24, 14, 10, 14], k=1)[0]

def ensure_world_goal(day_count):
    cycle_id = (day_count - 1) // WORLD_GOAL_CYCLE_DAYS
    row = q("SELECT * FROM world_goals WHERE cycle_id=?", (cycle_id,), one=True)
    if row:
        return row
    info = WORLD_GOAL_DEFS[cycle_id % len(WORLD_GOAL_DEFS)]
    run("""INSERT OR IGNORE INTO world_goals(cycle_id,goal_key,resource_key,target)
           VALUES(?,?,?,?)""", (cycle_id, info["key"], info["resource_key"], info["target"]))
    return q("SELECT * FROM world_goals WHERE cycle_id=?", (cycle_id,), one=True)

def world_goal_info(goal):
    return next(x for x in WORLD_GOAL_DEFS if x["key"] == goal["goal_key"])

def add_world_goal_progress(goal_key, amount):
    ws = get_world_state()
    goal = ensure_world_goal(ws["day_count"])
    if goal["goal_key"] != goal_key or goal["completed"]:
        return
    cur = run("""UPDATE world_goals SET progress=MIN(target,progress+?)
                 WHERE cycle_id=? AND completed=0""", (max(0, amount), goal["cycle_id"]))
    if not cur.rowcount:
        return
    fresh = q("SELECT * FROM world_goals WHERE cycle_id=?", (goal["cycle_id"],), one=True)
    if fresh["progress"] >= fresh["target"] and not fresh["completed"]:
        run("UPDATE world_goals SET completed=1,completed_ts=? WHERE cycle_id=?",
            (now_ts(), fresh["cycle_id"]))
        info = world_goal_info(fresh)
        run("""INSERT OR IGNORE INTO world_news(day_count,title,content,created_ts)
               VALUES(?,?,?,?)""",
            (ws["day_count"], "全服共同目标完成",
             f"所有幸存者共同完成了「{info['name']}」，参与者让这个世界稍微安全了一点。",
             now_ts()))
        run("UPDATE characters SET wallet=wallet+15 WHERE status='alive'")
        announce(f"🏆 全服共同完成「{info['name']}」，所有当前幸存者获得15钱包货币。")

def maybe_trigger_world_event(ch):
    if random.random() >= WORLD_EVENT_CHANCE:
        return False
    key = random.choice(list(WORLD_EVENTS))
    run("""INSERT OR REPLACE INTO pending_world_events(character_id,event_key,tile_x,tile_y,created_ts)
           VALUES(?,?,?,?,?)""", (ch["id"], key, ch["tile_x"], ch["tile_y"], now_ts()))
    return True

SHELTER_REWARDS = {
    "supply_pack": {"name": "🥫 后勤补给包", "cost": 40, "repeatable": True},
    "banner_patch": {"name": "🚩 贡献者旗章", "cost": 60, "repeatable": False},
    "map_marker": {"name": "🗺️ 彩色地图标记", "cost": 80, "repeatable": False},
    "animal_collar": {"name": "🐾 动物纪念项圈", "cost": 100, "repeatable": False},
    "radio_badge": {"name": "📻 无线电老兵徽章", "cost": 120, "repeatable": False},
}
RADIO_EVENT_DURATION = 3 * DAY_SECONDS
RADIO_EVENT_COOLDOWN = 4 * DAY_SECONDS
RADIO_ROLLS_PER_DAY = 6
RADIO_BOARD_LENGTH = 30
DISASTER_ACTIONS_PER_DAY = 3
DISASTER_CYCLE_DAYS = 7
DISASTER_DEFS = [
    {"key": "horde", "name": "🧟 巨型迁徙尸潮", "hp": 500},
    {"key": "toxic_nest", "name": "☣️ 毒雾感染巢穴", "hp": 620},
    {"key": "war_machine", "name": "🤖 失控军用机器人", "hp": 760},
]
FORTUNE_RESULTS = {
    "steady": [
        ("wood", 3, "在一处干燥屋檐下找到保存完好的木料。"),
        ("raw_food", 2, "翻出两份还能吃的密封食材。"),
        ("herb", 2, "认出墙角长着可以入药的植物。"),
        ("clean_water", 2, "找到两瓶没有开封的净水。"),
    ],
    "bold_common": [
        ("ammo", 2, "顺着旧弹壳找到一小盒弹药。"),
        ("parts", 2, "拆下一组仍能使用的机械零件。"),
        ("emergency_food", 2, "在夹墙里发现两罐应急食品。"),
    ],
    "bold_rare": [
        ("electronics", 1, "在烧毁的控制台深处发现完好的电子元件！"),
        ("first_aid", 1, "打开一只几乎崭新的军用急救包！"),
        ("resonance_material", 1, "捡到一块发出微弱共鸣的特殊材料！"),
    ],
}

def announce(content):
    run("INSERT INTO server_announcements(content,created_ts) VALUES(?,?)", (content, now_ts()))
    run("""DELETE FROM server_announcements WHERE id NOT IN
           (SELECT id FROM server_announcements ORDER BY id DESC LIMIT 80)""")

def add_shelter_contribution(ch, points):
    if not ch["shelter_id"] or points <= 0:
        return
    if has_trait(ch, "homebody"):
        points = max(1, int(round(points * 1.2)))
    run("""INSERT INTO shelter_contributions(character_id,shelter_id,points) VALUES(?,?,?)
           ON CONFLICT(character_id,shelter_id) DO UPDATE SET points=points+excluded.points""",
        (ch["id"], ch["shelter_id"], points))

def ensure_radio_event():
    ts = now_ts()
    active = q("SELECT * FROM radio_events WHERE status='active' ORDER BY id DESC LIMIT 1", one=True)
    if active and ts >= active["ends_ts"]:
        run("UPDATE radio_events SET status='ended' WHERE id=?", (active["id"],))
        active = None
    if active:
        return active
    last = q("SELECT * FROM radio_events ORDER BY id DESC LIMIT 1", one=True)
    if last and ts < last["ends_ts"] + RADIO_EVENT_COOLDOWN:
        return None
    run("""INSERT INTO radio_events(name,status,starts_ts,ends_ts)
           VALUES('📻 废土无线电寻宝','active',?,?)""", (ts, ts + RADIO_EVENT_DURATION))
    event = q("SELECT * FROM radio_events ORDER BY id DESC LIMIT 1", one=True)
    announce("📻 新一轮「废土无线电寻宝」开始了，三日内每天可行动6次。")
    return event

def ensure_world_disaster(day_count):
    cycle = (day_count - 1) // DISASTER_CYCLE_DAYS
    row = q("SELECT * FROM world_disasters WHERE cycle_id=?", (cycle,), one=True)
    if row:
        if row["status"] == "active" and now_ts() >= row["ends_ts"]:
            run("UPDATE world_disasters SET status='failed' WHERE cycle_id=?", (cycle,))
            announce(f"{row['name']}仍未被完全解决，但幸存者们守住了主要聚居地。")
            return q("SELECT * FROM world_disasters WHERE cycle_id=?", (cycle,), one=True)
        return row
    info = DISASTER_DEFS[cycle % len(DISASTER_DEFS)]
    run("""INSERT OR IGNORE INTO world_disasters
           (cycle_id,disaster_key,name,hp,max_hp,status,starts_ts,ends_ts)
           VALUES(?,?,?,?,?,'active',?,?)""",
        (cycle, info["key"], info["name"], info["hp"], info["hp"],
         now_ts(), now_ts() + DISASTER_CYCLE_DAYS * DAY_SECONDS))
    announce(f"⚠️ 全服灾害出现：{info['name']}。战斗、后勤、医疗和侦查都能参与。")
    return q("SELECT * FROM world_disasters WHERE cycle_id=?", (cycle,), one=True)

# ── 生存效率(十六.4:饥饿/口渴打折打在产出数量上) ─────────────────────────

def survival_efficiency(ch):
    lowest = min(ch["hunger"], ch["thirst"])
    if lowest <= 0:
        efficiency = 0.5   # 极端情况下不至于完全拿不到东西,但很惨
    elif lowest < 20:
        efficiency = 0.7
    elif lowest < 50:
        efficiency = 0.9
    else:
        efficiency = 1.0
    wellbeing = wellbeing_for(ch["id"], ch)
    if wellbeing["recreation"] < 15:
        efficiency *= .9
    if ch["stamina"] <= 0:
        efficiency *= .70
    elif ch["stamina"] < 30:
        efficiency *= .85
    return efficiency

def maybe_grow_stat(ch, stat_col):
    if ch[stat_col] >= STAT_CAP:
        return
    if random.random() < STAT_GROWTH_CHANCE:
        run(f"UPDATE characters SET {stat_col}={stat_col}+1 WHERE id=?", (ch["id"],))

def grant_xp(ch, amount):
    xp = ch["xp"] + amount
    level = ch["level"]
    bp = ch["blueprint_points"]
    while level < LEVEL_CAP and xp >= level * 100:
        xp -= level * 100
        level += 1
        bp += 1
    run("UPDATE characters SET xp=?, level=?, blueprint_points=? WHERE id=?", (xp, level, bp, ch["id"]))

# ── 感染/HP/死亡 ──────────────────────────────────────────────────────────

# 吃饱喝足(饥饿/口渴都到这个门槛以上)时，感染度会往下掉，但只降到这个下限为止——
# 剩下的部分(下限到0)仍然只能靠庇护所解药清零，被动手段不能完全免疫感染。
# 原来是"每个tick按概率掷骰子"，玩家反馈明明一直吃饱喝足却经常大半个小时不触发——
# 概率模型本身没错(30分钟期望值≈每小时86%触发一次)，但"期望"不是"保证"，运气不好真的
# 会连续不触发，体感很差。改成确定性计时:连续达标满INTERVAL秒必定触发一次，不再掷骰子。
INFECTION_RECOVERY_WELLFED_THRESHOLD = 75
INFECTION_RECOVERY_FLOOR = 20
INFECTION_RECOVERY_AMOUNT = 5
INFECTION_RECOVERY_INTERVAL_SECONDS = 25 * 60

# HP原来完全没有自然回复，只能靠医疗品；同样卡在"医疗品要等级"这个问题上，
# 调快到每7.5分钟左右1点。不看饥饿/口渴，那两个不达标时本身已经在扣HP了。
HP_PASSIVE_REGEN_INTERVAL_SECONDS = 300

def apply_infection(ch, amount):
    new_val = min(100, ch["infection"] + amount)
    run("UPDATE characters SET infection=? WHERE id=?", (new_val, ch["id"]))
    if new_val >= 100:
        kill_character(ch["id"], reason="感染度到顶")

def apply_damage(ch, amount):
    new_hp = ch["hp"] - amount
    if new_hp <= 0:
        run("UPDATE characters SET hp=0 WHERE id=?", (ch["id"],))
        kill_character(ch["id"], reason="HP归零")
    else:
        run("UPDATE characters SET hp=? WHERE id=?", (new_hp, ch["id"]))

def kill_character(char_id, reason=""):
    ch = q("SELECT * FROM characters WHERE id=?", (char_id,), one=True)
    if not ch or ch["status"] != "alive":
        return
    # 十.2:随身物品掉落在死亡地点,变成遗物点
    for item in char_inv_list(char_id):
        run("INSERT INTO death_loot (tile_x, tile_y, resource_key, amount, dropped_ts) VALUES (?,?,?,?,?)",
            (ch["tile_x"], ch["tile_y"], item["resource_key"], item["amount"], now_ts()))
    run("DELETE FROM character_inventory WHERE character_id=?", (char_id,))
    run("UPDATE characters SET status='dead', death_ts=? WHERE id=?", (now_ts(), char_id))
    # 一节:庇护所成员位置立刻空出(不做额外表维护,shelter_id留空即可,人数用JOIN实时算)
    log_action(char_id, "death", reason)
    living_heirs = q("""SELECT 1 FROM children WHERE status='alive'
                        AND successor_character_id IS NULL
                        AND (parent_a=? OR parent_b=?) LIMIT 1""",
                     (char_id, char_id), one=True)
    # 有存活孩子时房屋进入家族托管，等待继承人；没有后代才按普通死亡废弃。
    if not living_heirs:
        run("UPDATE houses SET abandoned=1, abandoned_ts=? WHERE owner_user_id=? AND abandoned=0",
            (now_ts(), ch["user_id"]))
    user = q("SELECT * FROM users WHERE id=?", (ch["user_id"],), one=True)
    new_count = user["respawn_count"] + 1
    if living_heirs:
        run("UPDATE users SET respawn_count=?, permadead=0 WHERE id=?", (new_count, user["id"]))
    elif new_count > MAX_RESPAWNS:
        run("UPDATE users SET respawn_count=?, permadead=1 WHERE id=?", (new_count, user["id"]))
    else:
        run("UPDATE users SET respawn_count=? WHERE id=?", (new_count, user["id"]))
    # 十.1:庇护所成员数降到0才废弃,这里只需检查该角色所在庇护所是否已空
    if ch["shelter_id"]:
        # 五节:死亡通知,给同庇护所还活着的成员看
        when = time.strftime("%m-%d %H:%M", time.localtime(now_ts()))
        run("INSERT INTO shelter_notifications (shelter_id, message, created_ts) VALUES (?,?,?)",
            (ch["shelter_id"], f"{ch['name']} 于 {when} 在坐标({ch['tile_x']},{ch['tile_y']}) 死亡(死因:{reason})", now_ts()))
        remaining = q("SELECT COUNT(*) AS c FROM characters WHERE shelter_id=? AND status='alive'",
                       (ch["shelter_id"],), one=True)
        if remaining["c"] == 0:
            run("UPDATE shelters SET abandoned=1, abandoned_ts=? WHERE id=?", (now_ts(), ch["shelter_id"]))

# ── 战斗(十六.5-16.8) ─────────────────────────────────────────────────────

def roll_zombie_type(dist):
    weights = zombie_weight_by_distance(dist)
    keys, w = zip(*weights.items())
    return random.choices(keys, weights=w, k=1)[0]

def choose_zombie_intent(ztype):
    intents = ZOMBIE_INTENTS[ztype]
    return random.choices([x[0] for x in intents],
                          weights=[x[3] for x in intents], k=1)[0]

def combat_intent_info(ztype, intent):
    return next(({"key": key, "name": name, "desc": desc}
                 for key, name, desc, _ in ZOMBIE_INTENTS[ztype]
                 if key == intent),
                {"key": "bite", "name": "🦷 准备攻击", "desc": "即将发动普通攻击。"})

def choose_combat_terrain(ch):
    weather = weather_for_day(get_world_state()["day_count"])["key"]
    choices = ["road", "hallway", "ruins", "rooftop", "woods"]
    weights = [30, 20, 24, 10, 16]
    if weather in ("rain", "storm"):
        weights = [18, 27, 28, 5, 22]
    return random.choices(choices, weights=weights, k=1)[0]

def begin_combat(ch, ztype, zhp):
    terrain = choose_combat_terrain(ch)
    intent = choose_zombie_intent(ztype)
    run("""UPDATE characters
           SET pending_zombie_type=?,pending_zombie_hp=?,combat_max_hp=?,
               combat_round_no=1,combat_intent=?,combat_terrain=?,combat_aim=0,
               combat_reload=0,combat_enemy_buff=0,combat_status='',
               combat_tactic_used=0,combat_pet_used=0,combat_signal_used=0,
               combat_advantage=0,
               pending_combat_reward=''
           WHERE id=?""",
        (ztype, zhp, zhp, intent, terrain, ch["id"]))

def maybe_trigger_encounter(ch):
    dist = dist_from_origin(ch["tile_x"], ch["tile_y"])
    weather = weather_for_day(get_world_state()["day_count"])
    region = region_threat_for_position(ch["tile_x"], ch["tile_y"])
    regional_risk = region["threat"] * .0015 + region["noise"] * .0007
    chance = min(0.75, (0.10 + dist * 0.003) * weather["danger"] + regional_risk)
    if has_trait(ch, "careful"):
        chance *= 0.92
    if random.random() < chance:
        ztype = roll_zombie_type(dist)
        ws = get_world_state()
        strength = zombie_base_strength(dist, ws["day_count"]) * ZOMBIE_TYPES[ztype]["hp_mult"]
        zhp = max(5, int(strength))
        begin_combat(ch, ztype, zhp)
        return True
    return False

def maybe_trigger_wild_animal(ch):
    # 驯养MVP:已经有宠物或正在驯服中的,不会再遇到新的
    if ch["tamed_animal_key"] or ch["pending_tame_key"]:
        return False
    if random.random() < WILD_ANIMAL_ENCOUNTER_CHANCE:
        animal_key = random.choice(list(ANIMALS.keys()))
        run("UPDATE characters SET pending_tame_key=?, pending_tame_affinity=0 WHERE id=?", (animal_key, ch["id"]))
        return True
    return False

def ensure_combat_state(ch):
    """兼容升级前已处于遭遇中的角色，以及旧入口直接写入的遭遇。"""
    if not ch["pending_zombie_type"]:
        return ch
    updates = {}
    if not ch["combat_max_hp"]:
        updates["combat_max_hp"] = max(1, ch["pending_zombie_hp"])
    if not ch["combat_round_no"]:
        updates["combat_round_no"] = 1
    if not ch["combat_intent"]:
        updates["combat_intent"] = choose_zombie_intent(ch["pending_zombie_type"])
    if not ch["combat_terrain"]:
        updates["combat_terrain"] = choose_combat_terrain(ch)
    if updates:
        clause = ",".join(f"{key}=?" for key in updates)
        run(f"UPDATE characters SET {clause} WHERE id=?",
            (*updates.values(), ch["id"]))
        ch = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    return ch

def combat_flee_rate(ch, zinfo):
    terrain = COMBAT_TERRAINS.get(ch["combat_terrain"], COMBAT_TERRAINS["road"])
    status_penalty = .18 if ch["combat_status"] == "grabbed" else 0
    injury_penalty = .12 if has_active_injury(ch["id"], "sprain") else 0
    plan_bonus = .08 if has_daily_plan(ch, "expedition") else 0
    wellbeing = wellbeing_for(ch["id"], ch)
    morale_bonus = .04 if wellbeing["recreation"] >= 70 else 0
    prep_bonus = combat_preparation_for(ch)["flee_bonus"]
    advantage = .14 if ch["combat_advantage"] else 0
    companion_bonus = COMPANION_FLEE_BONUS if companion_for(ch["id"]) else 0
    stamina_penalty = .15 if ch["stamina"] <= 0 else (.08 if ch["stamina"] < 30 else 0)
    return max(0.05, min(0.90, 0.40 + (ch["stat_spd"] - zinfo["spd"]) * 0.02 +
                               terrain.get("flee", 0) + plan_bonus + morale_bonus +
                               prep_bonus + advantage + companion_bonus - status_penalty -
                               injury_penalty - stamina_penalty))

def combat_preview(ch):
    ch = ensure_combat_state(ch)
    zinfo = ZOMBIE_TYPES[ch["pending_zombie_type"]]
    tier = ARMOR_TIERS[ch["armor_tier"] if ch["armor_durability"] > 0 else 0]
    outfit_defense = outfit_combat_defense(ch["id"])
    intent = combat_intent_info(ch["pending_zombie_type"], ch["combat_intent"])
    intent_mult = {"pounce": 1.55, "charge": 1.8, "grab": .65,
                   "spit": .45, "scream": 0}.get(ch["combat_intent"], 1)
    predicted = max(0, int(8 * zinfo["dmg_mult"] * intent_mult *
                           (1 + ch["combat_enemy_buff"] * .18) *
                           (1 - tier["dmg_reduction"]) * (1 - outfit_defense)))
    weapon = ch["equipped_weapon"] if ch["weapon_durability"] > 0 else "fist"
    ammo = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key='ammo'""",
             (ch["id"],), one=True)
    noise = 9 if weapon == "rifle" else (7 if weapon == "gun" else
            (3 if weapon in ("bow", "crossbow") else 1))
    prep = combat_preparation_for(ch)
    wellbeing = wellbeing_for(ch["id"], ch)
    injuries = active_injuries(ch["id"])
    plan = daily_plan_for(ch)
    animal_profile = q("""SELECT * FROM tamed_animal_profiles
                          WHERE character_id=?""", (ch["id"],), one=True)
    animal_active = bool(ch["tamed_animal_key"] and
                         _animal_bonus_active(ch, ch["tamed_animal_key"]))
    return {
        "intent": intent,
        "expected_damage": predicted,
        "guarded_damage": int(math.ceil(predicted * .45)),
        "flee_rate": int(round(combat_flee_rate(ch, zinfo) * 100)),
        "player_first": ch["stat_spd"] >= zinfo["spd"],
        "weapon": weapon,
        "weapon_name": "徒手" if weapon == "fist" else BLUEPRINTS[weapon]["name"],
        "ammo": ammo["amount"] if ammo else 0,
        "noise": noise,
        "terrain": COMBAT_TERRAINS.get(ch["combat_terrain"], COMBAT_TERRAINS["road"]),
        "preparation": prep,
        "focused": wellbeing["recreation"] >= 70,
        "injuries": injuries,
        "plan": DAILY_PLANS.get(plan["plan_key"]) if plan else None,
        "animal_profile": animal_profile if animal_active else None,
        "animal_key": ch["tamed_animal_key"] if animal_active else None,
        "can_signal": ch["hp"] <= 40 or ch["infection"] >= 60,
    }

def _combat_weapon_attack(ch, action, logs):
    weapon_key = ch["equipped_weapon"] if ch["weapon_durability"] > 0 else "fist"
    if weapon_key in ("gun", "rifle"):
        ammo = q("""SELECT amount FROM character_inventory
                    WHERE character_id=? AND resource_key='ammo'""",
                 (ch["id"],), one=True)
        if not ammo or ammo["amount"] <= 0:
            logs.append("枪膛空了，只能改用徒手。")
            weapon_key = "fist"
        else:
            inv_add("character_inventory", "character_id", ch["id"], "ammo", -1)
    if weapon_key == "crossbow" and ch["combat_reload"]:
        logs.append("弩弦还没有装好，这一回合无法射击。")
        return 0, weapon_key, False

    combat_noise = 9 if weapon_key == "rifle" else (7 if weapon_key == "gun" else
                   (3 if weapon_key in ("bow", "crossbow") else 1))
    add_region_noise(ch, combat_noise,
                     f"{display_name(ch)}在战斗中使用了{ITEM_NAMES.get(weapon_key, '徒手')}。",
                     "combat")
    base = WEAPON_DAMAGE.get(weapon_key or "fist", 5)
    if weapon_key in MELEE_WEAPONS:
        base += ch["stat_str"] * 2
    terrain = COMBAT_TERRAINS.get(ch["combat_terrain"], COMBAT_TERRAINS["road"])
    base *= terrain.get(weapon_key, terrain.get("melee", 1) if weapon_key == "fist" else 1)
    if weapon_key == "rifle" and ch["combat_round_no"] == 1:
        base *= 1.35
        logs.append("远距离第一枪取得了优势。")
    if ch["pending_zombie_type"] == "tank" and weapon_key not in ("crossbow", "rifle"):
        base *= .78
        logs.append("巨尸的肿胀组织吸收了一部分伤害。")
    if ch["combat_status"] == "exposed":
        base *= 1.5
        run("UPDATE characters SET combat_status='' WHERE id=?", (ch["id"],))
        logs.append("你抓住了它冲撞后的破绽。")
    if _animal_bonus_active(ch, "mid_fighter"):
        base *= 1 + ANIMALS["mid_fighter"]["combat_bonus"]
    prep = combat_preparation_for(ch)
    base *= 1 + prep["damage_bonus"]
    if ch["combat_advantage"]:
        base *= 1.25
        run("UPDATE characters SET combat_advantage=0 WHERE id=?", (ch["id"],))
        logs.append("你把刚才创造的战术优势压进这一击。")
    if has_active_injury(ch["id"], "bleeding"):
        base *= .90

    crit_rate = min(.30, ch["stat_luck"] * .006) + prep["crit_bonus"]
    if wellbeing_for(ch["id"], ch)["recreation"] >= 70:
        crit_rate += .05
    if weapon_key == "bow":
        crit_rate += .08
    crit = random.random() < crit_rate
    aimed = bool(ch["combat_aim"])
    multiplier = .62 if action == "guard" else 1.0
    if aimed:
        multiplier *= 1.65
        crit = crit or random.random() < .35
        run("UPDATE characters SET combat_aim=0 WHERE id=?", (ch["id"],))
    dmg = base * multiplier * (1.5 if crit else 1.0) * survival_efficiency(ch)
    if weapon_key == "bow":
        dmg += 2  # 安静武器用稳定的创口伤害补偿面板较低。
    if weapon_key == "crossbow":
        run("UPDATE characters SET combat_reload=1 WHERE id=?", (ch["id"],))
    if weapon_key and weapon_key != "fist" and ch["weapon_durability"] > 0:
        maintained = q("""SELECT maintained_battles FROM weapon_maintenance
                          WHERE character_id=?""", (ch["id"],), one=True)
        wear = random.randint(1, 2) if maintained and maintained["maintained_battles"] > 0 else random.randint(2, 5)
        if has_daily_plan(ch, "prepare"):
            wear = max(1, wear - 1)
        run("UPDATE characters SET weapon_durability=MAX(0, weapon_durability-?) WHERE id=?",
            (wear, ch["id"]))
    interrupted = weapon_key == "gun" and random.random() < .35
    logs.append(f"你用{'徒手' if weapon_key=='fist' else BLUEPRINTS[weapon_key]['name']}打出 {dmg:.0f} 点伤害"
                f"{'（瞄准）' if aimed else ''}{'（暴击！）' if crit else ''}。")
    return dmg, weapon_key, interrupted

def _enemy_resolves_intent(ch, zinfo, guarded, logs):
    intent = ch["combat_intent"] or "bite"
    buff = ch["combat_enemy_buff"]
    if intent == "scream":
        add_region_noise(ch, 8, f"{zinfo['name']}的尖叫引来了更多尸影。", "zombie_scream")
        run("""UPDATE characters SET combat_enemy_buff=MIN(3,combat_enemy_buff+1)
               WHERE id=?""", (ch["id"],))
        logs.append("尖叫穿过街区：区域噪声+8，它接下来的攻击也更凶狠。")
        return
    dmg_mult = {"grab": .65, "pounce": 1.55, "charge": 1.8,
                "spit": .45}.get(intent, 1.0) * (1 + buff * .18)
    infect_mult = 1.8 if intent == "spit" else 1.0
    guard_mult = 1.0
    if guarded:
        guard_mult = .45 - combat_preparation_for(ch)["guard_bonus"]
        if has_daily_plan(ch, "prepare"):
            guard_mult -= .07
        if has_active_injury(ch["id"], "bruised"):
            guard_mult += .12
        guard_mult = max(.25, min(.70, guard_mult))
    if intent in ("pounce", "charge") and guarded:
        guard_mult = .28
        if intent == "charge":
            run("UPDATE characters SET combat_status='exposed' WHERE id=?", (ch["id"],))
            logs.append("你顶住冲撞，巨尸失去平衡，下一击将命中弱点。")
    terrain = COMBAT_TERRAINS.get(ch["combat_terrain"], COMBAT_TERRAINS["road"])
    if intent == "spit":
        infect_mult *= terrain.get("infection", 1)
    damage, infection = _zombie_hits_player(
        ch, zinfo, dmg_mult=dmg_mult * guard_mult,
        infect_mult=infect_mult * (.70 if guarded else 1))
    if intent == "grab":
        run("UPDATE characters SET combat_status='grabbed' WHERE id=?", (ch["id"],))
        logs.append("它抓住了你的衣服，下一次逃跑率会降低。")
    logs.append(f"{zinfo['name']}命中：HP-{damage}"
                f"{f'、感染+{infection}' if infection else ''}。")
    injury_key = maybe_add_combat_injury(ch, intent, guarded, zinfo["name"])
    if injury_key:
        logs.append(f"这次攻击留下了{INJURY_DEFS[injury_key]['name']}："
                    f"{INJURY_DEFS[injury_key]['effect']}")

def _finish_combat_victory(ch, ztype, zinfo, weapon_key, logs):
    run("""UPDATE characters SET pending_zombie_type=NULL,pending_zombie_hp=0,
           pending_combat_reward=?,combat_intent='',combat_aim=0,combat_reload=0,
           combat_enemy_buff=0,combat_status='' WHERE id=?""", (ztype, ch["id"]))
    grant_xp(ch, 10)
    record_daily_progress(ch["id"], "combat", 1)
    record_long_progress(ch["id"], "combat", 1)
    run("UPDATE family_heirlooms SET battle_count=battle_count+1 WHERE owner_character_id=?",
        (ch["id"],))
    run("""UPDATE weapon_maintenance SET maintained_battles=MAX(0,maintained_battles-1)
           WHERE character_id=?""", (ch["id"],))
    if weapon_key in ("gun", "rifle"):
        inv_add("character_inventory", "character_id", ch["id"], "spent_casing", random.randint(1, 2))
        if random.random() < .25:
            inv_add("character_inventory", "character_id", ch["id"], "gunpowder", 1)
    award_tag(ch["id"], "first_blood", zinfo["name"])
    remember_location(ch["id"], ch["tile_x"], ch["tile_y"], f"你在这里击败了{zinfo['name']}。")
    elite_kill = ztype in ("tank", "screamer", "spitter")
    if elite_kill:
        add_world_goal_progress("elite_hunt", 1)
    if ch["tamed_animal_key"] and _animal_bonus_active(ch, ch["tamed_animal_key"]):
        run("""UPDATE tamed_animal_profiles SET battles_won=battles_won+1
               WHERE character_id=?""", (ch["id"],))
        if ch["combat_pet_used"]:
            recreation_gain(ch, 1, "与动物伙伴并肩作战")
    log_action(ch["id"], "combat_win", zinfo["name"])
    maybe_grow_stat(ch, "stat_str")
    if ch["shelter_id"]:
        # 科研点原来打一只普通丧尸只给1点，庇护所升级/疫苗/终局装置动辄要几十到几百点，
        # 唯一来源还只有这一条，玩家反馈太苛刻。普通丧尸提到2点，精英丧尸(tank/screamer/spitter)
        # 本来就更难打，给3点作为额外奖励。
        run("UPDATE shelters SET research_points=research_points+? WHERE id=?",
            (3 if elite_kill else 2, ch["shelter_id"]))
    logs.append(f"击败了{zinfo['name']}！获得10点经验。先决定如何处理战场。")

def _combat_terrain_action(ch, logs):
    terrain = ch["combat_terrain"] or "road"
    run("UPDATE characters SET combat_tactic_used=1 WHERE id=?", (ch["id"],))
    if terrain == "road":
        run("UPDATE characters SET combat_advantage=1,combat_status='' WHERE id=?", (ch["id"],))
        logs.append("你借废车拉开距离：脱离率提高，下一次攻击也会获得增伤。")
        return 0, False, True
    if terrain == "hallway":
        damage = 6 + ch["stat_int"] * .35
        add_region_noise(ch, 1, f"{display_name(ch)}踢倒楼道杂物阻断追击。", "combat_tactic")
        logs.append(f"你踢倒柜架封住楼道，造成{damage:.0f}点伤害并打断敌人。")
        return damage, True, False
    if terrain == "ruins":
        run("UPDATE characters SET combat_advantage=1 WHERE id=?", (ch["id"],))
        logs.append("你滑进断墙后的掩体：本回合稳守，并取得下一击优势。")
        return 0, False, True
    if terrain == "rooftop":
        damage = 8 + ch["stat_luck"] * .5
        add_region_noise(ch, 2, f"{display_name(ch)}从屋顶推落碎砖。", "combat_tactic")
        logs.append(f"你推落一片碎砖，造成{damage:.0f}点伤害。")
        return damage, False, False
    run("UPDATE characters SET combat_aim=1,combat_advantage=1 WHERE id=?", (ch["id"],))
    logs.append("你绕树消失在视线中：本回合稳守，下一击同时获得瞄准和伏击优势。")
    return 0, False, True

def _combat_pet_action(ch, logs):
    key = ch["tamed_animal_key"]
    profile = q("SELECT * FROM tamed_animal_profiles WHERE character_id=?", (ch["id"],), one=True)
    name = profile["custom_name"] if profile else ANIMALS[key]["name"]
    run("UPDATE characters SET combat_pet_used=1 WHERE id=?", (ch["id"],))
    if key == "mid_fighter":
        damage = 9 + min(9, (profile["battles_won"] if profile else 0) * .3)
        logs.append(f"{name}扑住敌人的侧面，造成{damage:.0f}点伤害并打断这一回合。")
        return damage, True, False
    if key == "small_pack":
        run("UPDATE characters SET combat_advantage=1,combat_status='' WHERE id=?", (ch["id"],))
        logs.append(f"{name}把你从敌人手边拖开：解除抓取，脱离率和下一击提高。")
        return 0, False, True
    damage = 6
    logs.append(f"{name}低头撞开敌人，造成{damage}点伤害并打断这一回合。")
    return damage, True, False

def _combat_signal_action(ch, logs):
    existing = q("""SELECT 1 FROM rescue_signals
                    WHERE requester_character_id=? AND status='open'""",
                 (ch["id"],), one=True)
    run("UPDATE characters SET combat_signal_used=1 WHERE id=?", (ch["id"],))
    if existing:
        logs.append("你的救援坐标仍在广播。本回合退到掩体后等待回应。")
    elif ch["hp"] <= 40 or ch["infection"] >= 60:
        run("""INSERT INTO rescue_signals
               (requester_character_id,requester_name,tile_x,tile_y,message,created_ts)
               VALUES(?,?,?,?,?,?)""",
            (ch["id"], display_name(ch), ch["tile_x"], ch["tile_y"],
             "遭遇战中受伤，需要附近幸存者送药或接应", now_ts()))
        logs.append("你发出带坐标的战斗求援。视野范围内的玩家已能在地图看见，本回合按稳守结算。")
    else:
        logs.append("当前伤势还没有达到紧急求援标准。")
    return 0, False, True

def combat_round(ch, action):
    """轻量战术回合：quick/guard/aim/reload/item/flee。"""
    ch = ensure_combat_state(ch)
    ztype = ch["pending_zombie_type"]
    zinfo = ZOMBIE_TYPES[ztype]
    zhp = ch["pending_zombie_hp"]
    logs = []
    if action == "fight":
        action = "quick"
    if action not in ("quick", "guard", "aim", "reload", "item", "terrain",
                      "pet", "signal", "flee"):
        logs.append("无法识别这个战斗动作。")
        return logs
    ch, stamina_spent = spend_stamina(
        ch, STAMINA_COSTS.get(action, 0), f"战斗动作:{action}")
    if stamina_spent:
        logs.append(f"这一回合消耗体力{stamina_spent}，剩余{ch['stamina']}。")
    if ch["stamina"] < 30:
        logs.append("疲劳正在拖慢你的反应：伤害与脱离能力下降，受伤风险提高。")

    if action == "flee":
        flee_rate = combat_flee_rate(ch, zinfo)
        if random.random() < flee_rate:
            run("""UPDATE characters SET pending_zombie_type=NULL,pending_zombie_hp=0,
                   combat_intent='',combat_aim=0,combat_reload=0,combat_enemy_buff=0,
                   combat_status='' WHERE id=?""", (ch["id"],))
            logs.append(f"你成功从{zinfo['name']}手里逃脱,没有拿到任何经验/战利品。")
            return logs
        logs.append(f"脱离失败！{zinfo['name']}截住了退路。")
        if ch["combat_status"] == "grabbed":
            run("UPDATE characters SET combat_status='' WHERE id=?", (ch["id"],))
        _enemy_resolves_intent(ch, zinfo, False, logs)
        fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
        if fresh and fresh["status"] == "alive":
            run("""UPDATE characters SET combat_round_no=combat_round_no+1,
                   combat_intent=? WHERE id=?""", (choose_zombie_intent(ztype), ch["id"]))
        return logs

    guarded = action == "guard"
    player_first = guarded or action in ("aim", "reload", "item", "terrain", "pet", "signal") or ch["stat_spd"] >= zinfo["spd"]
    order = ["player", "zombie"] if player_first else ["zombie", "player"]
    interrupted = False
    weapon_key = ch["equipped_weapon"] if ch["weapon_durability"] > 0 else "fist"
    for side in order:
        if side == "player":
            if action == "aim":
                run("UPDATE characters SET combat_aim=1 WHERE id=?", (ch["id"],))
                logs.append("你稳住呼吸瞄准弱点：下一次攻击伤害与暴击率提高。")
                continue
            if action == "reload":
                if weapon_key != "crossbow" or not ch["combat_reload"]:
                    logs.append("当前武器不需要装填。")
                else:
                    run("UPDATE characters SET combat_reload=0 WHERE id=?", (ch["id"],))
                    logs.append("你踩住弩臂重新上弦，下一回合可以射击。")
                continue
            if action == "item":
                injuries = active_injuries(ch["id"])
                required_item = next((INJURY_DEFS[row["injury_key"]]["item"] for row in injuries), None)
                item = q("""SELECT resource_key,amount FROM character_inventory
                            WHERE character_id=? AND resource_key IN ('bandage','first_aid')
                            AND amount>0 ORDER BY CASE resource_key WHEN 'bandage' THEN 0 ELSE 1 END
                            LIMIT 1""", (ch["id"],), one=True)
                if required_item:
                    preferred = q("""SELECT resource_key,amount FROM character_inventory
                                     WHERE character_id=? AND resource_key=? AND amount>0""",
                                  (ch["id"], required_item), one=True)
                    item = preferred or item
                if not item:
                    logs.append("背包里没有能在战斗中使用的医疗物品。")
                else:
                    heal = BLUEPRINTS[item["resource_key"]]["heal"]
                    inv_add("character_inventory", "character_id", ch["id"], item["resource_key"], -1)
                    run("UPDATE characters SET hp=MIN(100,hp+?) WHERE id=?", (heal, ch["id"]))
                    treated = treat_injuries(ch["id"], item["resource_key"])
                    logs.append(f"你使用{ITEM_NAMES[item['resource_key']]}，HP+{heal}"
                                f"{f'，处理伤势x{treated}' if treated else ''}。")
                continue
            if action in ("terrain", "pet", "signal"):
                if action == "terrain":
                    if ch["combat_tactic_used"]:
                        logs.append("这个地形机会已经用过了。")
                        continue
                    dmg, interrupted, tactic_guard = _combat_terrain_action(ch, logs)
                elif action == "pet":
                    if ch["combat_pet_used"] or not ch["tamed_animal_key"] or not _animal_bonus_active(ch, ch["tamed_animal_key"]):
                        logs.append("当前没有可以执行指令的动物伙伴。")
                        continue
                    dmg, interrupted, tactic_guard = _combat_pet_action(ch, logs)
                else:
                    if ch["combat_signal_used"]:
                        logs.append("本场战斗已经广播过求援坐标。")
                        continue
                    dmg, interrupted, tactic_guard = _combat_signal_action(ch, logs)
                guarded = guarded or tactic_guard
                zhp -= dmg
                logs.append(f"{zinfo['name']}剩余HP约{max(0, zhp):.0f}。")
                if zhp <= 0:
                    _finish_combat_victory(ch, ztype, zinfo, weapon_key, logs)
                    return logs
                continue
            fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
            dmg, weapon_key, interrupted = _combat_weapon_attack(fresh, action, logs)
            zhp -= dmg
            logs.append(f"{zinfo['name']}剩余HP约{max(0, zhp):.0f}。")
            if zhp <= 0:
                _finish_combat_victory(ch, ztype, zinfo, weapon_key, logs)
                return logs
        else:
            if interrupted:
                logs.append("你的行动打断了敌人这一回合的意图。")
                continue
            hit_rate = .82 if ch["combat_intent"] in ("pounce", "charge", "spit") else .75
            if random.random() < hit_rate:
                fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
                _enemy_resolves_intent(fresh, zinfo, guarded, logs)
            else:
                logs.append(f"{zinfo['name']}的动作落空了。")
            alive = q("SELECT status FROM characters WHERE id=?", (ch["id"],), one=True)
            if not alive or alive["status"] != "alive":
                return logs
    run("""UPDATE characters SET pending_zombie_hp=?,combat_round_no=combat_round_no+1,
           combat_intent=? WHERE id=?""",
        (max(0, zhp), choose_zombie_intent(ztype), ch["id"]))
    return logs

def _zombie_hits_player(ch, zinfo, dmg_mult=1.0, infect_mult=1.0):
    fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    tier = ARMOR_TIERS[fresh["armor_tier"] if fresh["armor_durability"] > 0 else 0]
    outfit_defense = outfit_combat_defense(fresh["id"])
    dmg = max(0, int(round(8 * zinfo["dmg_mult"] * dmg_mult *
                           (1 - tier["dmg_reduction"]) * (1 - outfit_defense))))
    infect = max(0, int(round(zinfo["infect"] * infect_mult *
                              (1 - tier["infection_reduction"]))))
    apply_damage(fresh, dmg)
    if fresh["armor_durability"] > 0:
        run("UPDATE characters SET armor_durability=MAX(0, armor_durability-?) WHERE id=?",
            (random.randint(2, 5), ch["id"]))
    fresh2 = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    if fresh2 and fresh2["status"] == "alive":
        apply_infection(fresh2, infect)
    return dmg, infect

# ── 路由:认证 ─────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("用户名和密码不能为空")
            return redirect(url_for("register"))
        if q("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            flash("用户名已存在")
            return redirect(url_for("register"))
        approved = 1 if username == ADMIN_USERNAME else 0  # 试玩阶段:管理员账号自己免批准,否则先有人批不了别人
        cur = run("INSERT INTO users (username, password_hash, approved, created_ts) VALUES (?,?,?,?)",
                   (username, generate_password_hash(password, method="pbkdf2:sha256"), approved, now_ts()))
        S["user_id"] = cur.lastrowid
        if not approved:
            return redirect(url_for("pending_approval"))
        return redirect(url_for("new_character"))
    return render_template("register.html")

@app.route("/pending")
def pending_approval():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if user["approved"]:
        return redirect(url_for("dashboard"))
    return render_template("pending.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码错误")
            return redirect(url_for("login"))
        if user["permadead"]:
            flash("这个账号已经永久死亡(重开次数用尽),不能再玩了")
            return redirect(url_for("login"))
        S["user_id"] = user["id"]
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    S.clear()
    return redirect(url_for("login"))

# ── 路由:角色创建 ─────────────────────────────────────────────────────────

@app.route("/character/new", methods=["GET", "POST"])
@login_required
def new_character():
    user = current_user()
    if user["permadead"]:
        flash("账号已永久死亡,不能再创建新角色")
        return redirect(url_for("logout"))
    if current_character():
        return redirect(url_for("dashboard"))
    if eligible_heirs_for_user(user["id"]):
        return redirect(url_for("heirs_view"))
    if request.method == "POST":
        name = request.form.get("name", "").strip() or f"幸存者{user['id']}"
        ts = now_ts()
        cur = run("""INSERT INTO characters (user_id, name, tile_x, tile_y, protected_until_ts, created_ts, last_action_ts)
                     VALUES (?,?,0,0,?,?,?)""", (user["id"], name, ts + NEWBIE_PROTECTION_SECONDS, ts, ts))
        get_or_create_tile(0, 0)
        remember_location(cur.lastrowid, 0, 0, "你在这里醒来，第一次听见北辰信号。")
        flash("身份建立完成。接下来选择皮相、经历与特质。")
        return redirect(url_for("profile_view"))
    return render_template("new_character.html", respawn_count=user["respawn_count"], max_respawns=MAX_RESPAWNS)

@app.route("/heirs")
@login_required
def heirs_view():
    if current_character():
        return redirect(url_for("dashboard"))
    heirs = eligible_heirs_for_user(current_user()["id"])
    if not heirs:
        return redirect(url_for("new_character"))
    cards = []
    for child in heirs:
        cards.append({"row": child, "age": child_age_days(child), "stage": child_stage(child),
                      "inventory": q("SELECT * FROM child_inventory WHERE child_id=? AND amount>0",
                                     (child["id"],))})
    return render_template("heirs.html", heirs=cards, item_names=ITEM_NAMES)

@app.route("/heirs/<int:child_id>/claim", methods=["POST"])
@login_required
def heir_claim(child_id):
    user = current_user()
    if current_character():
        return redirect(url_for("dashboard"))
    child = q("""SELECT c.*, p.id AS deceased_parent_id,p.name AS parent_name,
                        p.wallet AS parent_wallet,p.shelter_id AS parent_shelter_id
                 FROM children c JOIN characters p ON p.id=c.parent_a OR p.id=c.parent_b
                 WHERE c.id=? AND c.status='alive' AND c.successor_character_id IS NULL
                   AND p.user_id=? AND p.status='dead'
                 ORDER BY p.death_ts DESC LIMIT 1""", (child_id, user["id"]), one=True)
    if not child:
        flash("这个继承人已经无法选择")
        return redirect(url_for("heirs_view"))
    ts = now_ts()
    age = child_age_days(child)
    inherited_wallet = max(0, child["parent_wallet"] // 4)
    cur = run("""INSERT INTO characters
                 (user_id,name,stat_str,stat_spd,stat_int,stat_luck,hp,level,wallet,
                  tile_x,tile_y,shelter_id,protected_until_ts,created_ts,last_action_ts)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (user["id"], child["name"], child["stat_str"], child["stat_spd"],
               child["stat_int"], child["stat_luck"], max(25, child["hp"]),
               max(1, min(10, age)), inherited_wallet, child["tile_x"], child["tile_y"],
               child["parent_shelter_id"], ts + DAY_SECONDS, child["born_ts"], ts))
    new_id = cur.lastrowid
    run("""UPDATE children SET status='heir',successor_character_id=? WHERE id=?""",
        (new_id, child_id))
    for item in q("SELECT * FROM child_inventory WHERE child_id=? AND amount>0", (child_id,)):
        inv_add("character_inventory", "character_id", new_id, item["resource_key"], item["amount"])
    parent_profile = profile_for(child["deceased_parent_id"])
    if parent_profile:
        run("""INSERT INTO character_profiles
               (character_id,nickname,face_claim,background_key,trait_a,trait_b,avatar_key,bio,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (new_id, "", parent_profile["face_claim"], parent_profile["background_key"],
             child["trait_a"] or parent_profile["trait_a"],
             child["trait_b"] or parent_profile["trait_b"], parent_profile["avatar_key"],
             f"我是{child['parent_name']}留下的孩子。如今，我接过这条仍未走完的路。", ts, ts))
    else:
        run("""INSERT INTO character_profiles
               (character_id,nickname,face_claim,background_key,trait_a,trait_b,avatar_key,bio,created_ts,updated_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (new_id, "", "", "bg001", child["trait_a"] or "optimist",
             child["trait_b"] or "careful", "avatar-01",
             f"我是{child['parent_name']}留下的孩子，接过了家族未走完的路。", ts, ts))
    parent_id = child["deceased_parent_id"]
    parent_state = q("SELECT * FROM story_states WHERE character_id=?", (parent_id,), one=True)
    if parent_state:
        run("""INSERT INTO story_states(character_id,chapter,completed,updated_ts)
               VALUES(?,?,?,?)""", (new_id, parent_state["chapter"], parent_state["completed"], ts))
    for counter in q("SELECT * FROM story_counters WHERE character_id=?", (parent_id,)):
        run("""INSERT INTO story_counters(character_id,counter_key,value) VALUES(?,?,?)""",
            (new_id, counter["counter_key"], counter["value"]))
    for choice in q("SELECT * FROM story_choices WHERE character_id=?", (parent_id,)):
        run("""INSERT INTO story_choices
               (character_id,chapter,choice_key,choice_label,trace_text,chosen_ts)
               VALUES(?,?,?,?,?,?)""",
            (new_id, choice["chapter"], choice["choice_key"], choice["choice_label"],
             choice["trace_text"], choice["chosen_ts"]))
    for relic in q("SELECT * FROM family_heirlooms WHERE owner_character_id=?", (parent_id,)):
        run("""UPDATE family_heirlooms
               SET owner_character_id=?,generation=generation+1 WHERE id=?""",
            (new_id, relic["id"]))
        run("""INSERT INTO heirloom_history(heirloom_id,character_id,event_text,created_ts)
               VALUES(?,?,?,?)""",
            (relic["id"], new_id, f"由{child['parent_name']}传给{child['name']}", ts))
    # 生活工坊也属于家：设施、衣柜和畜牧棚里的动物随继承人继续存在。
    run("UPDATE personal_homesteads SET character_id=? WHERE character_id=?", (new_id, parent_id))
    run("UPDATE personal_outfits SET character_id=? WHERE character_id=?", (new_id, parent_id))
    run("UPDATE personal_livestock SET character_id=? WHERE character_id=?", (new_id, parent_id))
    run("""UPDATE supply_caches SET owner_character_id=?,owner_user_id=?
           WHERE owner_character_id=?""", (new_id, user["id"], parent_id))
    run("UPDATE personal_survival_workshops SET character_id=? WHERE character_id=?", (new_id, parent_id))
    run("UPDATE weapon_maintenance SET character_id=? WHERE character_id=?", (new_id, parent_id))
    run("DELETE FROM drink_batches WHERE character_id=?", (parent_id,))
    album_add(new_id, "inheritance", "接过火种",
              f"{child['name']}在{child['parent_name']}倒下后接过家族身份与北辰线路。",
              parent_id, child_id)
    run("UPDATE houses SET abandoned=0,abandoned_ts=0 WHERE owner_user_id=?", (user["id"],))
    run("UPDATE users SET permadead=0 WHERE id=?", (user["id"],))
    remember_location(new_id, child["tile_x"], child["tile_y"],
                      f"你在这里接过了{child['parent_name']}留下的地图。")
    announce(f"🕯️ {child['name']}继承了{child['parent_name']}未走完的路，家族火种仍在延续。")
    flash(f"你现在以{child['name']}继续游戏。孩子自己的物资、属性与家族房屋已继承，北辰主线选择也被保留。")
    return redirect(url_for("dashboard"))

# ── 语言 cosplay 角色档案 ────────────────────────────────────────────────

@app.route("/profile", methods=["GET", "POST"])
@login_required
@need_character
def profile_view(ch):
    profile = profile_for(ch["id"])
    if request.method == "POST":
        nickname = " ".join((request.form.get("nickname") or "").strip().split())[:12]
        face_claim = " ".join((request.form.get("face_claim") or "").strip().split())[:30]
        bio = (request.form.get("bio") or "").strip()[:500]
        avatar_key = request.form.get("avatar_key")
        if avatar_key not in AVATAR_OPTIONS:
            flash("请选择一个有效头像")
            return redirect(url_for("profile_view"))
        if profile:
            run("""UPDATE character_profiles
                   SET nickname=?,face_claim=?,avatar_key=?,bio=?,updated_ts=?
                   WHERE character_id=?""",
                (nickname, face_claim, avatar_key, bio, now_ts(), ch["id"]))
            flash("角色档案已更新")
        else:
            background_key = request.form.get("background_key")
            trait_a = request.form.get("trait_a")
            trait_b = request.form.get("trait_b")
            if background_key not in CHARACTER_BACKGROUNDS:
                flash("请选择一段人物背景")
                return redirect(url_for("profile_view"))
            if trait_a not in CHARACTER_TRAITS or trait_b not in CHARACTER_TRAITS or trait_a == trait_b:
                flash("请选择两个不同的有效特质")
                return redirect(url_for("profile_view"))
            run("""INSERT INTO character_profiles
                   (character_id,nickname,face_claim,background_key,trait_a,trait_b,avatar_key,bio,created_ts,updated_ts)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (ch["id"], nickname, face_claim, background_key, trait_a, trait_b,
                 avatar_key, bio, now_ts(), now_ts()))
            fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
            announce(f"📇 新的幸存者档案已登记：{display_name(fresh)}")
            flash("角色档案登记完成。背景与特质已经锁定，其他内容随时可以修改。")
        return redirect(url_for("dashboard"))
    refresh_experience_tags(ch)
    tags = q("SELECT * FROM character_tags WHERE character_id=? ORDER BY earned_ts", (ch["id"],))
    room = q("SELECT * FROM character_room_corners WHERE character_id=?", (ch["id"],), one=True)
    choices = q("SELECT * FROM story_choices WHERE character_id=? ORDER BY chapter", (ch["id"],))
    return render_template("profile.html", ch=ch, profile=profile, avatars=AVATAR_OPTIONS,
                           backgrounds=CHARACTER_BACKGROUNDS, traits=CHARACTER_TRAITS,
                           tags=tags, tag_defs=EXPERIENCE_TAGS, room=room,
                           room_corners=ROOM_CORNERS, story_choices=choices)

@app.route("/room-corner", methods=["POST"])
@login_required
@need_character
def room_corner_set(ch):
    key = request.form.get("corner_key")
    note = " ".join((request.form.get("custom_note") or "").strip().split())[:80]
    if key not in ROOM_CORNERS:
        flash("没有这个房间布置")
    else:
        run("""INSERT INTO character_room_corners(character_id,corner_key,custom_note,updated_ts)
               VALUES(?,?,?,?)
               ON CONFLICT(character_id) DO UPDATE SET
                 corner_key=excluded.corner_key,custom_note=excluded.custom_note,
                 updated_ts=excluded.updated_ts""",
            (ch["id"], key, note, now_ts()))
        record_long_progress(ch["id"], "home", 1)
        flash(f"房间角落已布置为「{ROOM_CORNERS[key][0]}」")
    return redirect(url_for("profile_view"))

@app.route("/radio-npcs")
@login_required
@need_character
def radio_npcs(ch):
    age_day = survivor_day(ch)
    relations = {r["npc_key"]: r for r in q(
        "SELECT * FROM npc_relationships WHERE character_id=?", (ch["id"],))}
    contacted = q("""SELECT * FROM npc_contact_logs
                     WHERE character_id=? AND survivor_day=?""",
                  (ch["id"], age_day), one=True)
    npc_rows = []
    for key, info in RADIO_NPCS.items():
        rel = relations.get(key)
        trust = rel["trust"] if rel else 0
        npc_rows.append({"key": key, **info, "relation": rel, "trust": trust,
                         "stage": "可以托付" if trust >= 15 else ("逐渐熟悉" if trust >= 7 else "信号陌生"),
                         "unlocked": age_day >= info["unlock"]})
    return render_template("radio_npcs.html", ch=ch, npcs=npc_rows,
                           contacted=contacted, survivor_day=age_day)

@app.route("/radio-npc/<npc_key>/contact", methods=["POST"])
@login_required
@need_character
def radio_npc_contact(ch, npc_key):
    info = RADIO_NPCS.get(npc_key)
    age_day = survivor_day(ch)
    if not info or age_day < info["unlock"]:
        flash("这个频率还没有出现")
        return redirect(url_for("radio_npcs"))
    if q("""SELECT 1 FROM npc_contact_logs
            WHERE character_id=? AND survivor_day=?""", (ch["id"], age_day), one=True):
        flash("今天已经进行过一次私人无线电联络")
        return redirect(url_for("radio_npcs"))
    rel = q("""SELECT * FROM npc_relationships
               WHERE character_id=? AND npc_key=?""", (ch["id"], npc_key), one=True)
    count = rel["contact_count"] if rel else 0
    line = info["lines"][min(count, len(info["lines"]) - 1)]
    trust_gain = random.Random(f"npc:{ch['id']}:{npc_key}:{age_day}").randint(2, 4)
    cur = run("""INSERT OR IGNORE INTO npc_contact_logs
                 (character_id,survivor_day,npc_key,line,created_ts) VALUES(?,?,?,?,?)""",
              (ch["id"], age_day, npc_key, line, now_ts()))
    if cur.rowcount:
        run("""INSERT INTO npc_relationships(character_id,npc_key,trust,contact_count,last_line,updated_ts)
               VALUES(?,?,?,1,?,?)
               ON CONFLICT(character_id,npc_key) DO UPDATE SET
                 trust=trust+excluded.trust,contact_count=contact_count+1,
                 last_line=excluded.last_line,updated_ts=excluded.updated_ts""",
            (ch["id"], npc_key, trust_gain, line, now_ts()))
        old_trust = rel["trust"] if rel else 0
        if has_daily_plan(ch, "contact"):
            trust_gain += 1
            run("""UPDATE npc_relationships SET trust=trust+1
                   WHERE character_id=? AND npc_key=?""", (ch["id"], npc_key))
        new_trust = old_trust + trust_gain
        if old_trust < 7 <= new_trust:
            objective = {
                "qiao": "rescue", "yan": "move", "ning": "map_note", "luo": "move",
                "su": "radio", "he": "craft", "mei": "fortune", "an": "rescue",
            }[npc_key]
            maybe_create_dynamic_quest(
                ch["id"], f"npc:{npc_key}:trusted", f"{info['name']}的私人委托",
                f"{info['call']}开始信任你，并把一件只会托付给熟人的事交给你。",
                objective, 1 if objective not in ("move", "radio") else 3, "wallet", 15)
        if old_trust < 15 <= new_trust:
            unlocked = run("""INSERT OR IGNORE INTO shelter_reward_unlocks
                              (character_id,reward_key,unlocked_ts) VALUES(?,?,?)""",
                           (ch["id"], f"npc_trusted:{npc_key}", now_ts()))
            if unlocked.rowcount:
                run("UPDATE characters SET wallet=wallet+10 WHERE id=?", (ch["id"],))
                album_add(ch["id"], "npc_trust", f"{info['call']}交付的私人呼号",
                          f"{info['name']}把你写进了可信频率名单，并留下只属于你们的备用呼号。")
        gained = recreation_gain(ch, 3, "私人无线电联络")
        record_long_progress(ch["id"], "contact", 1)
        record_long_progress(ch["id"], "connection", 1)
        flash(f"{info['call']} / {info['name']}：{line}（信任+{trust_gain}，娱乐+{gained}）")
    return redirect(url_for("radio_npcs"))

@app.route("/bedtime-broadcast", methods=["POST"])
@login_required
@need_character
def bedtime_broadcast(ch):
    age_day = survivor_day(ch)
    existing = q("""SELECT * FROM bedtime_broadcasts
                    WHERE character_id=? AND survivor_day=?""",
                 (ch["id"], age_day), one=True)
    if existing:
        flash("今天的临睡前广播已经听过了")
        return redirect(url_for("dashboard"))
    weather = weather_for_day(get_world_state()["day_count"])
    mood_name, _ = current_mood(ch, weather)
    latest_npc = q("""SELECT l.*,r.last_line FROM npc_contact_logs l
                      LEFT JOIN npc_relationships r
                        ON r.character_id=l.character_id AND r.npc_key=l.npc_key
                      WHERE l.character_id=? ORDER BY l.created_ts DESC LIMIT 1""",
                   (ch["id"],), one=True)
    fragments = [
        f"“这里是第{age_day}夜。{weather['name']}覆盖了旧城，远处仍有三盏灯。”",
        f"“归途频道记录：一名心境{mood_name}的幸存者仍在回应。”",
        "“若你听见两次短鸣和一次长鸣，请不要害怕，那是有人在说晚安。”",
    ]
    if latest_npc:
        npc = RADIO_NPCS[latest_npc["npc_key"]]
        fragments.append(f"“{npc['call']}留下夜间口信：{latest_npc['line']}”")
    text = random.Random(f"bed:{ch['id']}:{age_day}").choice(fragments)
    run("""INSERT OR IGNORE INTO bedtime_broadcasts
           (character_id,survivor_day,broadcast_text,created_ts) VALUES(?,?,?,?)""",
        (ch["id"], age_day, text, now_ts()))
    gained = recreation_gain(ch, 4, "临睡前广播")
    _, stamina_gain = restore_stamina(ch, 8, "临睡前广播")
    flash(f"{text}（娱乐+{gained}、体力+{stamina_gain}）")
    return redirect(url_for("dashboard"))

@app.route("/recreation", methods=["POST"])
@login_required
@need_character
def recreation_action(ch):
    age_day = survivor_day(ch)
    key = request.form.get("activity_key")
    info = RECREATION_ACTIVITIES.get(key)
    if not info:
        flash("没有这种休息方式")
        return redirect(url_for("dashboard"))
    if q("""SELECT 1 FROM recreation_activities
            WHERE character_id=? AND survivor_day=?""", (ch["id"], age_day), one=True):
        flash("今天已经认真休息过一次；其他生活活动仍可以自然恢复娱乐")
        return redirect(url_for("dashboard"))
    if key == "corner" and not q(
            "SELECT 1 FROM character_room_corners WHERE character_id=?", (ch["id"],), one=True):
        flash("先在角色档案里布置一个属于自己的房间角落")
        return redirect(url_for("dashboard"))
    if key == "album" and not q(
            "SELECT 1 FROM family_album WHERE character_id=? LIMIT 1", (ch["id"],), one=True):
        flash("相册里还没有故事；一次远征、家庭事件或传承会留下记录")
        return redirect(url_for("dashboard"))
    if key == "family" and not (spouse_for(ch["id"]) or q(
            """SELECT 1 FROM children WHERE status='alive'
               AND (parent_a=? OR parent_b=?)""", (ch["id"], ch["id"]), one=True)):
        flash("现在还没有能一起度过这段时间的家人")
        return redirect(url_for("dashboard"))
    if key == "animal":
        has_livestock = q("""SELECT 1 FROM personal_livestock
                             WHERE character_id=? AND status='alive' LIMIT 1""",
                          (ch["id"],), one=True)
        if not ch["tamed_animal_key"] and not has_livestock:
            flash("现在还没有动物伙伴陪在身边")
            return redirect(url_for("dashboard"))
    label, detail, amount = info
    recent = q("""SELECT activity_key FROM recreation_activities
                  WHERE character_id=? ORDER BY survivor_day DESC LIMIT 2""",
               (ch["id"],))
    repeats = sum(1 for row in recent if row["activity_key"] == key)
    effective_amount = max(4, amount - repeats * 3)
    if repeats:
        detail += " 同一种休息最近用得较多，恢复有所降低。"
    cur = run("""INSERT OR IGNORE INTO recreation_activities
                 (character_id,survivor_day,activity_key,gain,detail,created_ts)
                 VALUES(?,?,?,?,?,?)""",
              (ch["id"], age_day, key, effective_amount, detail, now_ts()))
    if cur.rowcount:
        gained = recreation_gain(ch, effective_amount, label)
        stamina_restore = {
            "quiet": 22, "corner": 18, "album": 12,
            "family": 14, "animal": 14,
        }.get(key, 12)
        _, stamina_gain = restore_stamina(ch, stamina_restore, label)
        record_daily_progress(ch["id"], "recreation", 1)
        record_long_progress(ch["id"], "recreation", 1)
        if key in ("family", "animal"):
            record_long_progress(ch["id"], "connection", 1)
        flash(f"{detail} 娱乐+{gained}、体力+{stamina_gain}。")
    return redirect(url_for("dashboard"))

@app.route("/daily-plan", methods=["POST"])
@login_required
@need_character
def daily_plan_choose(ch):
    key = request.form.get("plan_key")
    if key not in DAILY_PLANS:
        flash("没有这种今日计划")
        return redirect(url_for("story_view"))
    age_day = survivor_day(ch)
    cur = run("""INSERT OR IGNORE INTO daily_plans
                 (character_id,survivor_day,plan_key,created_ts) VALUES(?,?,?,?)""",
              (ch["id"], age_day, key, now_ts()))
    if not cur.rowcount:
        flash("今天的生活方向已经决定；明天可以重新选择")
    else:
        bonus = ""
        if key == "recover":
            run("UPDATE characters SET hp=MIN(100,hp+8) WHERE id=?", (ch["id"],))
            gained = recreation_gain(ch, 10, "选择休养日")
            _, stamina_gain = restore_stamina(ch, 30, "选择休养日")
            bonus = f" HP+8、精神余裕+{gained}、体力+{stamina_gain}。"
        record_long_progress(ch["id"], "daily_plan", 1)
        flash(f"今天定为「{DAILY_PLANS[key]['name']}」。{DAILY_PLANS[key]['desc']}{bonus}")
    return redirect(url_for("story_view"))

# ── 路由:主控制台 ─────────────────────────────────────────────────────────

@app.route("/")
@login_required
@need_character
def dashboard(ch):
    ch = settle_stamina(ch)
    profile = profile_for(ch["id"])
    if not profile:
        return redirect(url_for("profile_view"))
    run("""INSERT OR IGNORE INTO character_location_memories
           (character_id,tile_x,tile_y,first_visited_ts,last_visited_ts,visit_count,last_memory)
           VALUES(?,?,?,?,?,1,'你曾在这里停留。')""",
        (ch["id"], ch["tile_x"], ch["tile_y"], now_ts(), now_ts()))
    refresh_experience_tags(ch)
    if q("SELECT 1 FROM pending_world_events WHERE character_id=?", (ch["id"],), one=True):
        return redirect(url_for("world_event"))
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    if ch["pending_combat_reward"]:
        return redirect(url_for("combat_reward"))
    if ch["pending_tame_key"]:
        return redirect(url_for("taming"))
    tile = get_or_create_tile(ch["tile_x"], ch["tile_y"])
    outfit_row = equipped_outfit(ch["id"])
    equipped_outfit_info = CLOTHING_RECIPES.get(outfit_row["outfit_key"]) if outfit_row else None
    nodes = tile_resource_nodes(ch["tile_x"], ch["tile_y"])
    inventory = char_inv_list(ch["id"])
    inv_map = {i["resource_key"]: i["amount"] for i in inventory}
    equippable_items = [i for i in inventory
                        if i["resource_key"] in BLUEPRINTS
                        and BLUEPRINTS[i["resource_key"]]["type"] in ("weapon", "armor", "backpack")]
    house = q("SELECT * FROM houses WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0",
              (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    house_level_info = HOUSE_LEVELS.get(house["level"], HOUSE_LEVELS[1]) if house else None
    house_next_info = None
    house_upgrade_ready = False
    house_upgrade_reason = ""
    house_repair_materials = {}
    house_ammo = 0
    house_raid_logs = []
    house_power = None
    house_power_logs = []
    if house:
        house_power = ensure_power_grid("house", house["id"])
        house_power_logs = q("""SELECT * FROM power_logs
                                WHERE owner_type='house' AND owner_id=?
                                ORDER BY id DESC LIMIT 5""", (house["id"],))
        if house["level"] < HOUSE_LEVEL_CAP:
            house_next_info = HOUSE_LEVELS[house["level"] + 1]
            house_upgrade_ready, house_upgrade_reason = house_upgrade_access(
                ch, house["level"] + 1)
        house_repair_materials = house_repair_cost(house)
        ammo_row = q("""SELECT amount FROM house_inventory
                        WHERE house_id=? AND resource_key='ammo'""",
                     (house["id"],), one=True)
        house_ammo = ammo_row["amount"] if ammo_row else 0
        house_raid_logs = q("""SELECT * FROM house_raid_logs
                               WHERE house_id=? ORDER BY id DESC LIMIT 5""",
                            (house["id"],))
    house_inventory_list = (q("""SELECT * FROM house_inventory WHERE house_id=? AND amount>0
                                 ORDER BY resource_key""", (house["id"],))
                            if house else [])
    shelter = q("SELECT * FROM shelters WHERE tile_x=? AND tile_y=? AND abandoned=0",
                (ch["tile_x"], ch["tile_y"]), one=True)
    my_shelter = None
    my_shelter_member_count = 0
    shelter_power = None
    shelter_power_logs = []
    shelter_inventory_list = []
    if ch["shelter_id"]:
        my_shelter = q("SELECT * FROM shelters WHERE id=?", (ch["shelter_id"],), one=True)
        if my_shelter["tile_x"] == ch["tile_x"] and my_shelter["tile_y"] == ch["tile_y"]:
            shelter_inventory_list = q("""SELECT * FROM shelter_inventory WHERE shelter_id=? AND amount>0
                                          ORDER BY resource_key""", (my_shelter["id"],))
        shelter_power = ensure_power_grid("shelter", my_shelter["id"])
        shelter_power_logs = q("""SELECT * FROM power_logs
                                  WHERE owner_type='shelter' AND owner_id=?
                                  ORDER BY id DESC LIMIT 5""", (my_shelter["id"],))
        my_shelter_member_count = q("SELECT COUNT(*) AS c FROM characters WHERE shelter_id=? AND status='alive'",
                                     (ch["shelter_id"],), one=True)["c"]
        shelter_notifications = q("""SELECT * FROM shelter_notifications WHERE shelter_id=?
                                      ORDER BY id DESC LIMIT 5""", (ch["shelter_id"],))
        seed_row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key='rare_seed'",
                     (ch["shelter_id"],), one=True)
        shelter_rare_seed_count = seed_row["amount"] if seed_row else 0
        resonance_row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?",
                          (ch["shelter_id"], ENDGAME_MATERIAL_KEY), one=True)
        shelter_resonance_count = resonance_row["amount"] if resonance_row else 0
        dung_row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key='animal_dung'",
                     (ch["shelter_id"],), one=True)
        shelter_dung_count = dung_row["amount"] if dung_row else 0
        fert_row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key='fertilizer'",
                     (ch["shelter_id"],), one=True)
        shelter_fertilizer_count = fert_row["amount"] if fert_row else 0
    else:
        shelter_notifications = []
        shelter_rare_seed_count = 0
        shelter_resonance_count = 0
        shelter_dung_count = 0
        shelter_fertilizer_count = 0
    ws = get_world_state()
    weather_today = weather_for_day(ws["day_count"])
    weather_tomorrow = weather_for_day(ws["day_count"] + 1)
    current_region = region_threat_for_position(ch["tile_x"], ch["tile_y"])
    current_region_events = q("""SELECT * FROM region_threat_events
                                 WHERE region_x=? AND region_y=?
                                 ORDER BY id DESC LIMIT 5""",
                              (current_region["region_x"], current_region["region_y"]))
    raid_night = is_raid_night(ws["day_count"]) and not in_night_raid_quiet_hours()
    raid_eta = seconds_until_night_raid(ws)
    raid_warning = raid_night and 0 < raid_eta <= NIGHT_RAID_WARNING_SECONDS
    raid_forecast = night_raid_forecast(ch, house=house, shelter=shelter, ws=ws)
    animal_profile = q("SELECT * FROM tamed_animal_profiles WHERE character_id=?",
                       (ch["id"],), one=True)
    if ch["tamed_animal_key"] and not animal_profile:
        run("""INSERT OR IGNORE INTO tamed_animal_profiles
               (character_id,animal_key,custom_name,tamed_ts) VALUES(?,?,?,?)""",
            (ch["id"], ch["tamed_animal_key"], ANIMALS[ch["tamed_animal_key"]]["name"], now_ts()))
        animal_profile = q("SELECT * FROM tamed_animal_profiles WHERE character_id=?",
                           (ch["id"],), one=True)
    daily_goals = daily_goals_for(ch, ws["day_count"])
    fortune_today = q("""SELECT * FROM daily_fortune_draws
                         WHERE character_id=? AND day_count=?""",
                      (ch["id"], ws["day_count"]), one=True)
    shelter_feed = []
    shelter_feast = None
    if my_shelter:
        shelter_feed = q("""SELECT * FROM shelter_feed WHERE shelter_id=?
                            ORDER BY id DESC LIMIT 12""", (my_shelter["id"],))
        feast_target = max(6, my_shelter_member_count * 3)
        run("""INSERT OR IGNORE INTO shelter_feasts(shelter_id,day_count,target)
               VALUES(?,?,?)""", (my_shelter["id"], ws["day_count"], feast_target))
        shelter_feast = q("""SELECT * FROM shelter_feasts WHERE shelter_id=? AND day_count=?""",
                          (my_shelter["id"], ws["day_count"]), one=True)
    buildable, reason = tile_is_buildable(ch["tile_x"], ch["tile_y"])
    combat_log = S.pop("last_combat_log", None)
    xp_needed = ch["level"] * 100 if ch["level"] < LEVEL_CAP else None
    medical_items = [i for i in inventory if BLUEPRINTS.get(i["resource_key"], {}).get("type") == "medical"]
    unlocked_keys = {r["blueprint_key"] for r in q("SELECT blueprint_key FROM character_blueprints WHERE character_id=?", (ch["id"],))}
    if ch["hp"] <= 40:
        award_tag(ch["id"], "scarred", "曾在重伤状态下继续行动")
    mood = current_mood(ch, weather_today)
    wellbeing = wellbeing_for(ch["id"], ch)
    injuries = active_injuries(ch["id"])
    room = q("SELECT * FROM character_room_corners WHERE character_id=?", (ch["id"],), one=True)
    recreation_today = q("""SELECT * FROM recreation_activities
                             WHERE character_id=? AND survivor_day=?""",
                          (ch["id"], survivor_day(ch)), one=True)
    recreation_options = []
    has_family = bool(spouse_for(ch["id"]) or q(
        """SELECT 1 FROM children WHERE status='alive' AND (parent_a=? OR parent_b=?)""",
        (ch["id"], ch["id"]), one=True))
    has_animal_companion = bool(ch["tamed_animal_key"] or q(
        """SELECT 1 FROM personal_livestock WHERE character_id=? AND status='alive' LIMIT 1""",
        (ch["id"],), one=True))
    for key, info in RECREATION_ACTIVITIES.items():
        available = (key != "corner" or bool(room))
        available = available and (key != "album" or bool(q(
            "SELECT 1 FROM family_album WHERE character_id=? LIMIT 1", (ch["id"],), one=True)))
        available = available and (key != "family" or has_family)
        available = available and (key != "animal" or has_animal_companion)
        recreation_options.append({"key": key, "label": info[0], "detail": info[1],
                                   "gain": info[2], "available": available})
    bedtime = q("""SELECT * FROM bedtime_broadcasts
                   WHERE character_id=? AND survivor_day=?""",
                (ch["id"], survivor_day(ch)), one=True)
    return render_template("dashboard.html", ch=ch, tile=tile, nodes=nodes, inventory=inventory,
                            unlocked_blueprints=unlocked_keys,
                            basic_workbench_here=bool((house and house["has_workbench"]) or
                                                      (shelter and ch["shelter_id"] == shelter["id"] and shelter["has_workbench"])),
                            advanced_workbench_here=bool(shelter and shelter["has_advanced_workbench"] and ch["shelter_id"] == shelter["id"]),
                            house=house, shelter=shelter, my_shelter=my_shelter,
                            house_level_info=house_level_info,
                            house_next_info=house_next_info,
                            house_upgrade_ready=house_upgrade_ready,
                            house_upgrade_reason=house_upgrade_reason,
                            house_repair_materials=house_repair_materials,
                            house_repair_amount=HOUSE_REPAIR_AMOUNT,
                            house_ammo=house_ammo, house_raid_logs=house_raid_logs,
                            house_inventory_list=house_inventory_list,
                            house_inventory_total=sum(i["amount"] for i in house_inventory_list),
                            house_inventory_cap=house_inventory_cap_for(house),
                            storage_crate_cost=STORAGE_CRATE_COST,
                            storage_crate_cap=STORAGE_CRATE_CAP,
                            shelter_storage_crate_cap=SHELTER_STORAGE_CRATE_CAP,
                            storage_crate_bonus=STORAGE_CRATE_BONUS,
                            storage_transferable_keys=storage_transferable_keys(),
                            shelter_extractors=(shelter_extractor_state(my_shelter["id"])
                                                if my_shelter and my_shelter["tile_x"] == ch["tile_x"]
                                                and my_shelter["tile_y"] == ch["tile_y"] else {}),
                            extractor_level_cap=EXTRACTOR_LEVEL_CAP,
                            repeller_levels=REPELLER_LEVELS,
                            repeller_level_cap=REPELLER_LEVEL_CAP,
                            repeller_level_required=REPELLER_LEVEL_REQUIRED,
                            mega_warehouse_bonus=MEGA_WAREHOUSE_BONUS,
                            mega_warehouse_cost=MEGA_WAREHOUSE_COST,
                            mega_warehouse_level_required=MEGA_WAREHOUSE_LEVEL_REQUIRED,
                            vehicles=VEHICLES,
                            equipped_vehicle_info=VEHICLES.get(ch["equipped_vehicle"]),
                            move_stamina_cost=(VEHICLES[ch["equipped_vehicle"]]["stamina_cost"]
                                               if ch["equipped_vehicle"] in VEHICLES
                                               else STAMINA_COSTS["move"]),
                            shelter_inventory_list=shelter_inventory_list,
                            shelter_inventory_total=sum(i["amount"] for i in shelter_inventory_list),
                            shelter_inventory_cap=shelter_inventory_cap_for(my_shelter),
                            house_power=house_power, house_power_logs=house_power_logs,
                            house_level_cap=HOUSE_LEVEL_CAP,
                            house_solo_level_cap=HOUSE_SOLO_LEVEL_CAP,
                            house_auto_repair_cost=HOUSE_AUTO_REPAIR_COST,
                            raid_stances=RAID_STANCES,
                            my_shelter_member_count=my_shelter_member_count,
                            shelter_power=shelter_power, shelter_power_logs=shelter_power_logs,
                            generator_levels=GENERATOR_LEVELS, power_modes=POWER_MODES,
                            power_defense_reserve=POWER_DEFENSE_RESERVE,
                            resources=RESOURCES, item_names=ITEM_NAMES, night=is_night(ws), day_count=ws["day_count"],
                            protected=now_ts() < ch["protected_until_ts"],
                            buildable=buildable, buildable_reason=reason,
                            house_cost=HOUSE_COST, shelter_cost=SHELTER_COST,
                            shelter_level_required=SHELTER_LEVEL_REQUIRED,
                            combat_log=combat_log, xp_needed=xp_needed,
                            shelter_tiers=SHELTER_TIERS, blueprints=BLUEPRINTS,
                            basic_workbench_cost=BASIC_WORKBENCH_COST, advanced_workbench_cost=ADVANCED_WORKBENCH_COST,
                            medical_items=medical_items, now_ts=now_ts(),
                            furnace_cost=FURNACE_COST, furnace_batch_input=FURNACE_BATCH_INPUT,
                            furnace_batch_output=FURNACE_BATCH_OUTPUT, farm_yield_per_plot=FARM_YIELD_PER_PLOT,
                            sellable_resources=SELLABLE_RESOURCES, sell_rate=SELL_RATE,
                            shelter_notifications=shelter_notifications, inv_map=inv_map,
                            fish_species=FISH_SPECIES,
                            shelter_upgrade_cost=SHELTER_UPGRADE_COST,
                            shelter_tier_cap=SHELTER_TIER_CAP, greenhouse_cost=GREENHOUSE_COST,
                            shelter_rare_seed_count=shelter_rare_seed_count,
                            farm_int_bonus_per_point=FARM_INT_YIELD_BONUS_PER_POINT,
                            defense_buildings=DEFENSE_BUILDINGS,
                            vaccine_unlock_research=VACCINE_UNLOCK_RESEARCH, vaccine_unlock_materials=VACCINE_UNLOCK_MATERIALS,
                            vaccine_dose_cost=VACCINE_DOSE_COST,
                            endgame_material_key=ENDGAME_MATERIAL_KEY, endgame_material_needed=ENDGAME_MATERIAL_NEEDED,
                            endgame_unlock_tier=ENDGAME_UNLOCK_TIER, endgame_unlock_research=ENDGAME_UNLOCK_RESEARCH,
                            endgame_build_cost=ENDGAME_BUILD_COST, shelter_resonance_count=shelter_resonance_count,
                            hunting_trap_cost=HUNTING_TRAP_COST, animal_pen_cost=ANIMAL_PEN_COST, animals=ANIMALS,
                            shelter_dung_count=shelter_dung_count, shelter_fertilizer_count=shelter_fertilizer_count,
                            compost_input=COMPOST_INPUT, compost_yield_boost=COMPOST_YIELD_BOOST,
                            daily_goals=daily_goals, daily_goal_wallet_reward=DAILY_GOAL_WALLET_REWARD,
                            daily_goal_xp_reward=DAILY_GOAL_XP_REWARD,
                            shelter_feed=shelter_feed, shelter_feast=shelter_feast,
                            weather_today=weather_today, weather_tomorrow=weather_tomorrow,
                            animal_profile=animal_profile, fortune_today=fortune_today,
                            profile=profile, inventory_capacity=char_inv_capacity(ch),
                            mood=mood, bedtime=bedtime, survivor_day=survivor_day(ch),
                            current_region=current_region,
                            current_region_label=region_threat_label(current_region["threat"]),
                            current_region_events=current_region_events,
                            raid_eta=raid_eta, raid_warning=raid_warning,
                            raid_night=raid_night, raid_night_every=NIGHT_RAID_EVERY_N_DAYS,
                            raid_forecast=raid_forecast,
                            night_raid_warning_seconds=NIGHT_RAID_WARNING_SECONDS,
                            room=room, room_corners=ROOM_CORNERS,
                            wellbeing=wellbeing, recreation_state=recreation_state(wellbeing["recreation"]),
                            recreation_today=recreation_today, recreation_options=recreation_options,
                            injuries=injuries, injury_defs=INJURY_DEFS,
                            stamina_state=stamina_state(ch["stamina"]),
                            stamina_costs=STAMINA_COSTS,
                            stamina_recovery_seconds=STAMINA_RECOVERY_SECONDS,
                            infection_recovery_threshold=INFECTION_RECOVERY_WELLFED_THRESHOLD,
                            infection_recovery_floor=INFECTION_RECOVERY_FLOOR,
                            infection_recovery_minutes=round(INFECTION_RECOVERY_INTERVAL_SECONDS / 60, 1),
                            infection_recovery_amount=INFECTION_RECOVERY_AMOUNT,
                            hp_regen_minutes=round(HP_PASSIVE_REGEN_INTERVAL_SECONDS / 60, 1),
                            raw_water_poison_chance=(RAW_WATER_POISON_CHANCE_IRON_STOMACH
                                                     if has_trait(ch, "iron_stomach")
                                                     else RAW_WATER_POISON_CHANCE),
                            raw_food_poison_chance=(RAW_FOOD_POISON_CHANCE_IRON_STOMACH
                                                    if has_trait(ch, "iron_stomach")
                                                    else RAW_FOOD_POISON_CHANCE),
                            emergency_food_thirst_cost=EMERGENCY_FOOD_THIRST_COST,
                            equipped_outfit_info=equipped_outfit_info,
                            equippable_items=equippable_items,
                            tree_grow_seconds=TREE_GROW_SECONDS,
                            quarry_grow_seconds=QUARRY_GROW_SECONDS,
                            auto_eat_hunger_threshold=AUTO_EAT_HUNGER_THRESHOLD)

@app.route("/injury/<int:injury_id>/treat", methods=["POST"])
@login_required
@need_character
def injury_treat(ch, injury_id):
    injury = q("""SELECT * FROM character_injuries
                  WHERE id=? AND character_id=? AND status='active'""",
               (injury_id, ch["id"]), one=True)
    if not injury or injury["injury_key"] not in INJURY_DEFS:
        flash("这处伤势已经处理，或不属于当前角色")
        return redirect(url_for("dashboard"))
    item = INJURY_DEFS[injury["injury_key"]]["item"]
    have = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key=?""",
             (ch["id"], item), one=True)
    if not have or have["amount"] <= 0:
        flash(f"需要{ITEM_NAMES[item]}才能处理这处伤势")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], item, -1)
    treated = treat_injuries(ch["id"], item)
    flash(f"使用{ITEM_NAMES[item]}，处理了{treated}处伤势")
    return redirect(url_for("dashboard"))

@app.route("/encounter")
@login_required
@need_character
def encounter(ch):
    if not ch["pending_zombie_type"]:
        return redirect(url_for("combat_reward") if ch["pending_combat_reward"] else url_for("dashboard"))
    ch = settle_stamina(ch)
    ch = ensure_combat_state(ch)
    zinfo = ZOMBIE_TYPES[ch["pending_zombie_type"]]
    preview = combat_preview(ch)
    combat_log = S.pop("last_combat_log", None)
    medical = q("""SELECT resource_key,amount FROM character_inventory
                   WHERE character_id=? AND resource_key IN ('bandage','first_aid')
                   AND amount>0""", (ch["id"],))
    return render_template("encounter.html", ch=ch, zinfo=zinfo, preview=preview,
                           medical=medical, item_names=ITEM_NAMES,
                           injury_defs=INJURY_DEFS, combat_log=combat_log,
                           stamina_costs=STAMINA_COSTS)

def _combat_action_response(ch, action):
    logs = combat_round(ch, action)
    S["last_combat_log"] = logs
    ch2 = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    if not ch2 or ch2["status"] != "alive":
        return redirect(url_for("dashboard"))
    if ch2["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    if ch2["pending_combat_reward"]:
        return redirect(url_for("combat_reward"))
    return redirect(url_for("dashboard"))

@app.route("/action/combat/<action>", methods=["POST"])
@login_required
@need_character
def action_combat(ch, action):
    if not ch["pending_zombie_type"]:
        return redirect(url_for("dashboard"))
    return _combat_action_response(ch, action)

@app.route("/action/fight", methods=["POST"])
@login_required
@need_character
def action_fight(ch):
    return _combat_action_response(ch, "quick")

@app.route("/action/flee", methods=["POST"])
@login_required
@need_character
def action_flee(ch):
    return _combat_action_response(ch, "flee")

@app.route("/combat/reward", methods=["GET", "POST"])
@login_required
@need_character
def combat_reward(ch):
    ztype = ch["pending_combat_reward"]
    if not ztype:
        return redirect(url_for("encounter") if ch["pending_zombie_type"] else url_for("dashboard"))
    zinfo = ZOMBIE_TYPES.get(ztype, ZOMBIE_TYPES["normal"])
    if request.method == "GET":
        return render_template("combat_reward.html", ch=ch, zinfo=zinfo)
    choice = request.form.get("choice")
    if choice not in ("withdraw", "search", "clean"):
        flash("没有这种现场处置方式")
        return redirect(url_for("combat_reward"))
    # 先原子清除待结算标记，阻止刷新或重复提交反复领取。
    cur = run("""UPDATE characters SET pending_combat_reward=''
                 WHERE id=? AND pending_combat_reward=?""", (ch["id"], ztype))
    if not cur.rowcount:
        return redirect(url_for("dashboard"))
    if choice == "withdraw":
        flash("你没有被地上的东西拖住，带着胜利平安撤离。")
        log_action(ch["id"], "combat_aftermath", "立即撤离")
        return redirect(url_for("dashboard"))
    region = region_threat_for_position(ch["tile_x"], ch["tile_y"])
    if choice == "clean":
        run("""UPDATE map_regions SET noise=MAX(0,noise-4),threat=MAX(0,threat-3),
               updated_ts=? WHERE region_x=? AND region_y=?""",
            (now_ts(), region["region_x"], region["region_y"]))
        inv_add("character_inventory", "character_id", ch["id"], "spent_casing", 1)
        record_long_progress(ch["id"], "prepare", 1)
        recreation_gain(ch, 1, "确认战场重新安静")
        log_action(ch["id"], "combat_aftermath", "清理痕迹")
        flash("你清理了血迹和弹壳：区域噪声-4、威胁-3，回收1枚弹壳，并推进准备类任务。")
        return redirect(url_for("dashboard"))

    add_region_noise(ch, 3, f"{display_name(ch)}在战斗现场进行了深度搜刮。", "combat_search")
    common = ["cloth", "herb", "raw_food", "wood", "spent_casing"]
    rare = ["ammo", "parts", "gunpowder", "gun_oil", "metal"]
    finds = []
    rolls = 3 if ztype in ("tank", "screamer", "spitter") else 2
    for index in range(rolls):
        pool = rare if (index == rolls - 1 and (ztype != "normal" or random.random() < .35)) else common
        key = random.choice(pool)
        amount = random.randint(1, 2)
        inv_add("character_inventory", "character_id", ch["id"], key, amount)
        finds.append(f"{ITEM_NAMES.get(key, key)}x{amount}")
    themed_loot = {
        "tank": ("metal", 2),
        "screamer": ("electronics", 1),
        "spitter": ("herb", 2),
        "runner": ("cloth", 2),
    }.get(ztype)
    if themed_loot:
        inv_add("character_inventory", "character_id", ch["id"], themed_loot[0], themed_loot[1])
        finds.append(f"{ITEM_NAMES.get(themed_loot[0], themed_loot[0])}x{themed_loot[1]}（敌人特性掉落）")
    record_long_progress(ch["id"], "gather", 1)
    log_action(ch["id"], "combat_aftermath", "深度搜刮：" + "、".join(finds))
    if random.random() < .22:
        fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
        next_type = roll_zombie_type(dist_from_origin(ch["tile_x"], ch["tile_y"]))
        strength = zombie_base_strength(dist_from_origin(ch["tile_x"], ch["tile_y"]),
                                         get_world_state()["day_count"])
        begin_combat(fresh, next_type, max(5, int(strength * ZOMBIE_TYPES[next_type]["hp_mult"])))
        flash("你找到" + "、".join(finds) + "，但翻找声引来了新的敌人！")
        return redirect(url_for("encounter"))
    flash("你冒险搜遍现场，找到：" + "、".join(finds) + "。区域噪声+3。")
    return redirect(url_for("dashboard"))

# ── 路由:探索/采集 ────────────────────────────────────────────────────────

DIRECTIONS = {"n": (0, 1), "s": (0, -1), "e": (1, 0), "w": (-1, 0)}

@app.route("/action/move", methods=["POST"])
@login_required
@need_character
def action_move(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    if ch["pending_tame_key"]:
        return redirect(url_for("taming"))
    ts = now_ts()
    if ts < ch["move_cooldown_until_ts"]:
        flash(f"还在赶路,再等{ch['move_cooldown_until_ts'] - ts}秒")
        return redirect(url_for("dashboard"))
    d = request.form.get("dir")
    if d not in DIRECTIONS:
        flash("方向不对")
        return redirect(url_for("dashboard"))
    dx, dy = DIRECTIONS[d]
    vehicle = VEHICLES.get(ch["equipped_vehicle"])
    if vehicle:
        requested_steps = request.form.get("steps", type=int) or vehicle["max_tiles"]
        steps = max(1, min(vehicle["max_tiles"], requested_steps))
    else:
        steps = 1
    nx, ny = ch["tile_x"] + dx * steps, ch["tile_y"] + dy * steps
    get_or_create_tile(nx, ny)
    if vehicle:
        # 交通工具直接跳到目的地,不逐格结算,也跳过负重/天气减速——这是"省体力、没冷却"的实现方式。
        cooldown = vehicle["cooldown_seconds"]
        ch, stamina_spent = spend_stamina(ch, vehicle["stamina_cost"], f"骑{vehicle['name']}")
    else:
        # 十六.2:负重影响移动耗时,按随身储物占容量的比例分档
        cap = char_inv_capacity(ch)
        carried = inv_total("character_inventory", "character_id", ch["id"])
        ratio = carried / cap if cap else 0
        slow = MOVE_WEIGHT_SLOW_90 if ratio >= 0.9 else (MOVE_WEIGHT_SLOW_70 if ratio >= 0.7 else 0)
        weather = weather_for_day(get_world_state()["day_count"])
        weather_move = 1.0 if has_trait(ch, "night_owl") and is_night() else weather["move"]
        cooldown = int(MOVE_COOLDOWN_SECONDS * (1 + slow) * weather_move)
        if has_daily_plan(ch, "expedition"):
            cooldown = int(cooldown * .9)
        if has_trait(ch, "light_foot"):
            cooldown = int(cooldown * 0.9)
        ch, stamina_spent = spend_stamina(ch, STAMINA_COSTS["move"], "地图移动")
    run("UPDATE characters SET tile_x=?, tile_y=?, last_action_ts=?, move_cooldown_until_ts=? WHERE id=?",
        (nx, ny, ts, ts + cooldown, ch["id"]))
    record_daily_progress(ch["id"], "move", 1)
    record_long_progress(ch["id"], "move", 1)
    move_noise = 2 if ch["stamina"] <= 0 else 1
    add_region_noise(ch, move_noise,
                     f"{display_name(ch)}穿过了这片区域"
                     f"{'，疲惫的脚步留下更多动静' if move_noise > 1 else ''}。",
                     "move", nx, ny)
    remember_location(ch["id"], nx, ny, "你沿北辰信号来到这里。")
    if (nx, ny) != (0, 0):
        award_tag(ch["id"], "first_steps")
    moved_total = q("""SELECT value FROM story_counters
                       WHERE character_id=? AND counter_key='move'""",
                    (ch["id"],), one=True)
    if moved_total and moved_total["value"] >= 10:
        award_tag(ch["id"], "roadworn")
    log_action(ch["id"], "move", f"移动到({nx},{ny})")
    if ch["stamina"] < 30:
        flash(f"赶路消耗体力{stamina_spent}，当前{ch['stamina']}/100；疲劳会降低效率并增加风险。")
    maybe_grow_stat(ch, "stat_spd")
    ch2 = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    if maybe_trigger_world_event(ch2):
        return redirect(url_for("world_event"))
    if now_ts() >= ch2["protected_until_ts"]:  # 新手保护期内不触发遭遇
        if maybe_trigger_encounter(ch2):
            return redirect(url_for("encounter"))
        if maybe_trigger_wild_animal(ch2):
            return redirect(url_for("taming"))
    return redirect(url_for("dashboard"))

@app.route("/action/gather", methods=["POST"])
@login_required
@need_character
def action_gather(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    if ch["pending_tame_key"]:
        return redirect(url_for("taming"))
    node_id = request.form.get("node_id", type=int)
    node = q("SELECT * FROM resource_nodes WHERE id=? AND tile_x=? AND tile_y=?",
              (node_id, ch["tile_x"], ch["tile_y"]), one=True)
    if not node or node["current_amount"] <= 0:
        flash("这个资源点已经空了")
        return redirect(url_for("dashboard"))
    eff = survival_efficiency(ch)
    base_amt = min(5, node["current_amount"])
    gain = max(1, int(base_amt * eff))
    if has_daily_plan(ch, "expedition"):
        gain = min(node["current_amount"], gain + 1)
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    room = cap - carried
    if room <= 0:
        flash("随身储物已经满了,先回家存起来")
        return redirect(url_for("dashboard"))
    gain = min(gain, room)
    ts = now_ts()
    # 十四.2:先落库者得——用一条原子UPDATE...WHERE current_amount>=gain代替"先读后写",
    # 避免两个人同时点同一个资源点时,俩人都读到旧值、都各自扣出同一份存量
    if node["rarity"] == "landmark":
        cur = run("""UPDATE resource_nodes SET current_amount=0, gone_forever=1
                     WHERE id=? AND gone_forever=0 AND current_amount>0""", (node["id"],))
    else:
        # depleted_ts 现在记录"最近一次被采集"而不是"刚好清零"，配合下面刷新逻辑，
        # 哪怕一直没人把它挖到刚好是0，隔了够久也会自动回满，不用死等最后一点被拿走。
        cur = run("""UPDATE resource_nodes SET current_amount=current_amount-?,
                        depleted_ts=?
                     WHERE id=? AND current_amount>=?""",
                  (gain, ts, node["id"], gain))
    if cur.rowcount == 0:
        flash("手慢了,这份资源刚被人抢走了,再试一次")
        return redirect(url_for("dashboard"))
    ch, stamina_spent = spend_stamina(ch, STAMINA_COSTS["gather"], "采集资源")
    inv_add("character_inventory", "character_id", ch["id"], node["resource_key"], gain)
    grant_xp(ch, 2)
    record_daily_progress(ch["id"], "gather", gain)
    record_long_progress(ch["id"], "gather", gain)
    gather_noise = (5 if node["rarity"] == "landmark" else 3) + (2 if ch["stamina"] <= 0 else 0)
    add_region_noise(ch, gather_noise,
                     f"{display_name(ch)}采集了{RESOURCES[node['resource_key']][0]}。",
                     "gather")
    gathered_total = q("""SELECT value FROM story_counters
                          WHERE character_id=? AND counter_key='gather'""",
                       (ch["id"],), one=True)
    if gathered_total and gathered_total["value"] >= 50:
        award_tag(ch["id"], "scavenger_50")
    log_action(ch["id"], "gather", f"{node['resource_key']} x{gain}")
    if node["rarity"] == "landmark":
        add_world_goal_progress("landmark_search", 1)
    maybe_grow_stat(ch, "stat_int")
    if random.random() < 0.03:
        maybe_grow_stat(ch, "stat_luck")
    bonus_msgs = []
    scavenger_bonus = 0.03 if has_trait(ch, "scavenger") else 0
    if random.random() < RARE_SEED_DROP_CHANCE + scavenger_bonus and inv_total("character_inventory", "character_id", ch["id"]) < cap:
        inv_add("character_inventory", "character_id", ch["id"], "rare_seed", 1)
        bonus_msgs.append("意外挖到一颗🌱稀有种子")
    if random.random() < EMERGENCY_FOOD_DROP_CHANCE + scavenger_bonus and inv_total("character_inventory", "character_id", ch["id"]) < cap:
        inv_add("character_inventory", "character_id", ch["id"], "emergency_food", 1)
        bonus_msgs.append("翻出一份🥫应急食品")
    bonus_msg = (" + " + "、".join(bonus_msgs)) if bonus_msgs else ""
    fatigue_msg = f"；体力-{stamina_spent}，剩余{ch['stamina']}" + (
        "，过度劳累正在降低收益并增加噪声" if ch["stamina"] < 30 else "")
    flash(f"采集到 {RESOURCES[node['resource_key']][0]} x{gain}{bonus_msg}{fatigue_msg}")
    return redirect(url_for("dashboard"))

# ── 路由:种树/挖石头(不依赖地图资源点，安静不产生噪声) ───────────────────

@app.route("/action/plant-tree", methods=["POST"])
@login_required
@need_character
def action_plant_tree(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    tile = get_or_create_tile(ch["tile_x"], ch["tile_y"])
    if tile["is_water"]:
        flash("水域没法种树")
        return redirect(url_for("dashboard"))
    if ch["pending_tree_started_ts"]:
        flash("已经种下一棵树了，等它长好再来")
        return redirect(url_for("dashboard"))
    ch, spent = spend_stamina(ch, STAMINA_COSTS["plant_tree"], "种树")
    run("UPDATE characters SET pending_tree_started_ts=? WHERE id=?", (now_ts(), ch["id"]))
    flash(f"种下一棵树，大约{TREE_GROW_SECONDS // 60}分钟后回来收获；体力-{spent}")
    return redirect(url_for("dashboard"))

@app.route("/action/harvest-tree", methods=["POST"])
@login_required
@need_character
def action_harvest_tree(ch):
    if not ch["pending_tree_started_ts"]:
        flash("这里没有你种下的树")
        return redirect(url_for("dashboard"))
    elapsed = now_ts() - ch["pending_tree_started_ts"]
    if elapsed < TREE_GROW_SECONDS:
        remaining = TREE_GROW_SECONDS - elapsed
        flash(f"树还没长好，再等{remaining // 60}分{remaining % 60}秒")
        return redirect(url_for("dashboard"))
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    room = cap - carried
    if room <= 0:
        flash("随身储物已经满了，先回家存起来")
        return redirect(url_for("dashboard"))
    amount = min(room, random.randint(*TREE_WOOD_YIELD))
    inv_add("character_inventory", "character_id", ch["id"], "wood", amount)
    run("UPDATE characters SET pending_tree_started_ts=0 WHERE id=?", (ch["id"],))
    record_daily_progress(ch["id"], "gather", amount)
    record_long_progress(ch["id"], "gather", amount)
    grant_xp(ch, 2)
    log_action(ch["id"], "gather", f"种树收获 wood x{amount}")
    flash(f"收获了木材x{amount}")
    return redirect(url_for("dashboard"))

@app.route("/action/dig-quarry", methods=["POST"])
@login_required
@need_character
def action_dig_quarry(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    tile = get_or_create_tile(ch["tile_x"], ch["tile_y"])
    if tile["is_water"]:
        flash("水域没法挖石头")
        return redirect(url_for("dashboard"))
    if ch["pending_quarry_started_ts"]:
        flash("已经挖开一处矿坑了，等它出料再来")
        return redirect(url_for("dashboard"))
    ch, spent = spend_stamina(ch, STAMINA_COSTS["dig_quarry"], "挖石头")
    run("UPDATE characters SET pending_quarry_started_ts=? WHERE id=?", (now_ts(), ch["id"]))
    flash(f"挖开一处矿坑，大约{QUARRY_GROW_SECONDS // 60}分钟后回来收获；体力-{spent}")
    return redirect(url_for("dashboard"))

@app.route("/action/harvest-quarry", methods=["POST"])
@login_required
@need_character
def action_harvest_quarry(ch):
    if not ch["pending_quarry_started_ts"]:
        flash("这里没有你挖开的矿坑")
        return redirect(url_for("dashboard"))
    elapsed = now_ts() - ch["pending_quarry_started_ts"]
    if elapsed < QUARRY_GROW_SECONDS:
        remaining = QUARRY_GROW_SECONDS - elapsed
        flash(f"矿坑还没出料，再等{remaining // 60}分{remaining % 60}秒")
        return redirect(url_for("dashboard"))
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    room = cap - carried
    if room <= 0:
        flash("随身储物已经满了，先回家存起来")
        return redirect(url_for("dashboard"))
    amount = min(room, random.randint(*QUARRY_STONE_YIELD))
    inv_add("character_inventory", "character_id", ch["id"], "stone", amount)
    run("UPDATE characters SET pending_quarry_started_ts=0 WHERE id=?", (ch["id"],))
    record_daily_progress(ch["id"], "gather", amount)
    record_long_progress(ch["id"], "gather", amount)
    grant_xp(ch, 2)
    log_action(ch["id"], "gather", f"挖石头收获 stone x{amount}")
    flash(f"挖到了石头x{amount}")
    return redirect(url_for("dashboard"))

@app.route("/action/draw-water", methods=["POST"])
@login_required
@need_character
def action_draw_water(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    tile = get_or_create_tile(ch["tile_x"], ch["tile_y"])
    if not tile["is_water"]:
        flash("这里不是水域,没法打水")
        return redirect(url_for("dashboard"))
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    room = cap - carried
    if room <= 0:
        flash("随身储物已经满了,先回家存起来")
        return redirect(url_for("dashboard"))
    ch, spent = spend_stamina(ch, STAMINA_COSTS["draw_water"], "打水")
    amount = min(room, random.randint(*DRAW_WATER_YIELD))
    inv_add("character_inventory", "character_id", ch["id"], "raw_water", amount)
    record_daily_progress(ch["id"], "gather", amount)
    record_long_progress(ch["id"], "gather", amount)
    flash(f"打了生水x{amount}；体力-{spent}")
    return redirect(url_for("dashboard"))

# ── 路由:钓鱼(星露谷式小游戏 + 图鉴) ───────────────────────────────────────

def _pick_fish():
    rarity = random.choices(list(FISH_RARITY_WEIGHTS.keys()), weights=list(FISH_RARITY_WEIGHTS.values()), k=1)[0]
    pool = [k for k, v in FISH_SPECIES.items() if v["rarity"] == rarity]
    return random.choice(pool)

FISHING_SESSION_TIMEOUT = 120  # 超过这么久没交结果,视为放弃,允许重新钓

@app.route("/fishing")
@login_required
@need_character
def fishing(ch):
    ch = settle_stamina(ch)
    if ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    tile = q("SELECT * FROM world_tiles WHERE x=? AND y=?", (ch["tile_x"], ch["tile_y"]), one=True)
    if not tile or not tile["is_water"]:
        flash("这里不是水域,没法钓鱼")
        return redirect(url_for("dashboard"))
    if not q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key='fishing_rod' AND amount>0""", (ch["id"],), one=True):
        flash("要先做一把鱼竿(在背包里)才能钓鱼")
        return redirect(url_for("dashboard"))
    # 上一局超时没交结果,视为放弃,清掉重新分配
    if ch["pending_fish_key"] and now_ts() - ch["pending_fish_started_ts"] > FISHING_SESSION_TIMEOUT:
        run("UPDATE characters SET pending_fish_key=NULL, pending_fish_started_ts=0 WHERE id=?", (ch["id"],))
        ch = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    if not ch["pending_fish_key"]:
        ch, stamina_spent = spend_stamina(ch, STAMINA_COSTS["fish"], "钓鱼")
        fish_key = _pick_fish()
        run("UPDATE characters SET pending_fish_key=?, pending_fish_started_ts=? WHERE id=?",
            (fish_key, now_ts(), ch["id"]))
        if ch["stamina"] < 30:
            flash(f"抛竿消耗体力{stamina_spent}，当前{ch['stamina']}/100；疲劳让操作更吃力。")
    else:
        fish_key = ch["pending_fish_key"]
    fish = FISH_SPECIES[fish_key]
    return render_template("fishing.html", ch=ch, fish_key=fish_key, fish=fish, rarity_names=FISH_RARITY_NAMES)

@app.route("/action/fishing_result", methods=["POST"])
@login_required
@need_character
def action_fishing_result(ch):
    fish_key = ch["pending_fish_key"]
    if not fish_key:
        flash("没有正在进行的钓鱼")
        return redirect(url_for("dashboard"))
    success = request.form.get("result") == "success"
    run("UPDATE characters SET pending_fish_key=NULL, pending_fish_started_ts=0 WHERE id=?", (ch["id"],))
    if not success:
        flash(f"{FISH_SPECIES[fish_key]['name']} 挣脱跑掉了")
        return redirect(url_for("dashboard"))
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    if carried >= cap:
        flash(f"抓到了{FISH_SPECIES[fish_key]['name']},但随身储物满了,只能眼睁睁看它跑掉")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], fish_key, 1)
    row = q("SELECT * FROM character_fish_log WHERE character_id=? AND fish_key=?", (ch["id"], fish_key), one=True)
    if row:
        run("UPDATE character_fish_log SET catch_count=catch_count+1 WHERE character_id=? AND fish_key=?",
            (ch["id"], fish_key))
        first_catch = False
    else:
        run("INSERT INTO character_fish_log (character_id, fish_key, catch_count, first_caught_ts) VALUES (?,?,1,?)",
            (ch["id"], fish_key, now_ts()))
        first_catch = True
    grant_xp(ch, 3)
    record_long_progress(ch["id"], "fish", 1)
    recreation_gain(ch, 2, "安静钓鱼")
    if fish_key == "leviathan_spawn":
        add_world_goal_progress("legend_fish", 1)
        announce(f"🐋 {display_name(ch)} 钓到了传说级深渊幼鲲！")
    maybe_grow_stat(ch, "stat_luck")
    flash(f"抓到了{FISH_SPECIES[fish_key]['name']}!" + ("(图鉴新纪录)" if first_catch else ""))
    return redirect(url_for("dashboard"))

@app.route("/fish_log")
@login_required
@need_character
def fish_log(ch):
    caught = {r["fish_key"]: r for r in q("SELECT * FROM character_fish_log WHERE character_id=?", (ch["id"],))}
    return render_template("fish_log.html", ch=ch, fish_species=FISH_SPECIES, caught=caught,
                            rarity_names=FISH_RARITY_NAMES)

# ── 路由:地图总览(14.3:建筑对全服可见) ─────────────────────────────────────

MAP_RADIUS = 5
RADAR_MAP_RADIUS = 10

@app.route("/map")
@login_required
@need_character
def map_view(ch):
    cx, cy = ch["tile_x"], ch["tile_y"]
    has_radar = bool(q("""SELECT 1 FROM character_inventory
                         WHERE character_id=? AND resource_key='radar' AND amount>0""",
                       (ch["id"],), one=True))
    radius = RADAR_MAP_RADIUS if has_radar else MAP_RADIUS
    lo_x, hi_x, lo_y, hi_y = cx - radius, cx + radius, cy - radius, cy + radius
    tiles = {(r["x"], r["y"]): r for r in
             q("SELECT * FROM world_tiles WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?", (lo_x, hi_x, lo_y, hi_y))}
    houses_here = {(r["tile_x"], r["tile_y"]) for r in
                   q("""SELECT tile_x, tile_y FROM houses WHERE abandoned=0
                        AND tile_x BETWEEN ? AND ? AND tile_y BETWEEN ? AND ?""", (lo_x, hi_x, lo_y, hi_y))}
    shelters_here = {(r["tile_x"], r["tile_y"]): r for r in
                      q("""SELECT tile_x, tile_y, name, completed_ending FROM shelters WHERE abandoned=0
                           AND tile_x BETWEEN ? AND ? AND tile_y BETWEEN ? AND ?""", (lo_x, hi_x, lo_y, hi_y))}
    nearest_shelter = None
    nearest_shelter_distance = None
    nearest_shelter_direction = None
    for s in q("SELECT id,name,tile_x,tile_y FROM shelters WHERE abandoned=0"):
        d = max(abs(s["tile_x"] - cx), abs(s["tile_y"] - cy))
        if nearest_shelter_distance is None or d < nearest_shelter_distance:
            nearest_shelter, nearest_shelter_distance = s, d
            nearest_shelter_direction = compass_direction(s["tile_x"] - cx, s["tile_y"] - cy)
    players_here = {}
    for r in q("""SELECT c.id,c.name,c.tile_x,c.tile_y,p.nickname FROM characters c
                  LEFT JOIN character_profiles p ON p.character_id=c.id
                  WHERE c.status='alive' AND c.id<>? AND c.tile_x BETWEEN ? AND ? AND c.tile_y BETWEEN ? AND ?""",
               (ch["id"], lo_x, hi_x, lo_y, hi_y)):
        player = dict(r)
        player["display_name"] = f"{r['name']}（{r['nickname']}）" if r["nickname"] else r["name"]
        players_here.setdefault((r["tile_x"], r["tile_y"]), []).append(player)
    resources_here = {}
    for r in q("""SELECT tile_x, tile_y, resource_key, current_amount FROM resource_nodes
                  WHERE gone_forever=0 AND tile_x BETWEEN ? AND ? AND tile_y BETWEEN ? AND ?""",
               (lo_x, hi_x, lo_y, hi_y)):
        resources_here.setdefault((r["tile_x"], r["tile_y"]), []).append(
            {"key": r["resource_key"], "name": RESOURCES[r["resource_key"]][0], "amount": r["current_amount"]})
    grid = []
    regions = {}
    for y in range(hi_y, lo_y - 1, -1):
        row = []
        for x in range(lo_x, hi_x + 1):
            t = tiles.get((x, y))
            region_key = region_coords(x, y)
            if region_key not in regions:
                regions[region_key] = ensure_map_region(x, y)
            region = regions[region_key]
            row.append({
                "x": x, "y": y, "is_me": (x == cx and y == cy),
                "discovered": bool(t), "is_water": bool(t and t["is_water"]),
                "has_house": (x, y) in houses_here, "shelter": shelters_here.get((x, y)),
                "players": players_here.get((x, y), []),
                "resources": resources_here.get((x, y), []),
                "is_origin": (x == 0 and y == 0),
                "region": region,
                "region_label": region_threat_label(region["threat"]),
            })
        grid.append(row)
    notes = q("""SELECT * FROM map_notes WHERE tile_x=? AND tile_y=?
                 ORDER BY id DESC LIMIT 10""", (cx, cy))
    rescue_signals = q("""SELECT * FROM rescue_signals WHERE status='open'
                          AND tile_x BETWEEN ? AND ? AND tile_y BETWEEN ? AND ?
                          ORDER BY id DESC""", (lo_x, hi_x, lo_y, hi_y))
    location_memory = q("""SELECT * FROM character_location_memories
                           WHERE character_id=? AND tile_x=? AND tile_y=?""",
                        (ch["id"], cx, cy), one=True)
    current_region = ensure_map_region(cx, cy)
    region_events = q("""SELECT * FROM region_threat_events
                         WHERE region_x=? AND region_y=?
                         ORDER BY id DESC LIMIT 8""",
                      (current_region["region_x"], current_region["region_y"]))
    companion = companion_for(ch["id"])
    companion_distance = (max(abs(cx - companion["tile_x"]), abs(cy - companion["tile_y"]))
                          if companion else None)
    my_houses = []
    for idx, h in enumerate(q("""SELECT id,tile_x,tile_y,custom_name FROM houses
                                 WHERE owner_user_id=? AND abandoned=0 ORDER BY id""",
                              (ch["user_id"],)), start=1):
        my_houses.append({
            "id": h["id"],
            "label": h["custom_name"] or f"家{idx}",
            "tile_x": h["tile_x"], "tile_y": h["tile_y"],
            "is_here": h["tile_x"] == cx and h["tile_y"] == cy,
            "distance": max(abs(h["tile_x"] - cx), abs(h["tile_y"] - cy)),
            "direction": compass_direction(h["tile_x"] - cx, h["tile_y"] - cy),
        })
    return render_template("map.html", ch=ch, grid=grid, radius=radius, has_radar=has_radar,
                           notes=notes, rescue_signals=rescue_signals,
                           location_memory=location_memory,
                           current_region=current_region,
                           current_region_label=region_threat_label(current_region["threat"]),
                           region_events=region_events, region_size=REGION_SIZE,
                           companion=companion, companion_distance=companion_distance,
                           nearest_shelter=nearest_shelter,
                           nearest_shelter_distance=nearest_shelter_distance,
                           nearest_shelter_direction=nearest_shelter_direction,
                           my_houses=my_houses)

@app.route("/map/note", methods=["POST"])
@login_required
@need_character
def map_note_post(ch):
    content = " ".join((request.form.get("content") or "").strip().split())
    if not content:
        flash("地图留言不能为空")
    elif len(content) > 80:
        flash("地图留言最多80个字")
    else:
        run("""INSERT INTO map_notes(character_id,author_name,tile_x,tile_y,content,created_ts)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(character_id,tile_x,tile_y)
               DO UPDATE SET author_name=excluded.author_name,content=excluded.content,
                             created_ts=excluded.created_ts""",
            (ch["id"], display_name(ch), ch["tile_x"], ch["tile_y"], content, now_ts()))
        record_long_progress(ch["id"], "map_note", 1)
        flash("已把情报留在当前地块")
    return redirect(url_for("map_view"))

# ── 路由:邮箱(纯文字，不带物品/货币附件) ─────────────────────────────────

MAIL_BODY_MAX_LEN = 300
MAIL_SUBJECT_MAX_LEN = 40

def send_system_mail(to_character_id, from_name, subject, body, action_type="", action_ref=0):
    """给系统通知复用同一套邮箱,from_character_id留空、显示名固定成"系统"。
    action_type/action_ref可选,用来在邮件里内嵌一个操作按钮(目前只有claim_dynamic_quest)。"""
    run("""INSERT INTO player_mail(from_character_id,from_name,to_character_id,subject,body,
           action_type,action_ref,created_ts)
           VALUES(0,?,?,?,?,?,?,?)""",
        (from_name, to_character_id, subject, body, action_type, action_ref, now_ts()))

@app.route("/mail")
@login_required
@need_character
def mail_view(ch):
    inbox = q("""SELECT * FROM player_mail WHERE to_character_id=?
                 ORDER BY id DESC LIMIT 50""", (ch["id"],))
    sent = q("""SELECT p.*, c.name AS to_name FROM player_mail p
                LEFT JOIN characters c ON c.id=p.to_character_id
                WHERE p.from_character_id=? ORDER BY p.id DESC LIMIT 50""", (ch["id"],))
    unread_ids = [m["id"] for m in inbox if not m["is_read"]]
    if unread_ids:
        run(f"""UPDATE player_mail SET is_read=1
                WHERE id IN ({",".join("?" * len(unread_ids))})""", unread_ids)
    players = q("""SELECT c.*, p.nickname FROM characters c
                   LEFT JOIN character_profiles p ON p.character_id=c.id
                   WHERE c.status='alive' AND c.id<>? ORDER BY c.name""", (ch["id"],))
    return render_template("mail.html", ch=ch, inbox=inbox, sent=sent, players=players,
                           body_max=MAIL_BODY_MAX_LEN, subject_max=MAIL_SUBJECT_MAX_LEN)

@app.route("/mail/send", methods=["POST"])
@login_required
@need_character
def mail_send(ch):
    to_id = request.form.get("to_character_id", type=int)
    subject = " ".join((request.form.get("subject") or "").strip().split())[:MAIL_SUBJECT_MAX_LEN]
    body = " ".join((request.form.get("body") or "").strip().split())[:MAIL_BODY_MAX_LEN]
    target = q("SELECT * FROM characters WHERE id=? AND status='alive'", (to_id,), one=True) if to_id else None
    if not target or target["id"] == ch["id"]:
        flash("收件人不存在")
    elif not body:
        flash("信件内容不能为空")
    else:
        run("""INSERT INTO player_mail(from_character_id,from_name,to_character_id,subject,body,created_ts)
               VALUES(?,?,?,?,?,?)""",
            (ch["id"], display_name(ch), target["id"], subject, body, now_ts()))
        flash(f"已把信寄给{display_name(target)}。邮箱只能传文字,不能夹带物资——东西要面对面交易或走补给藏点。")
    return redirect(url_for("mail_view"))

# ── 路由:吃喝 ─────────────────────────────────────────────────────────────

@app.route("/action/toggle-auto-eat", methods=["POST"])
@login_required
@need_character
def action_toggle_auto_eat(ch):
    new_val = 0 if ch["auto_eat_enabled"] else 1
    run("UPDATE characters SET auto_eat_enabled=? WHERE id=?", (new_val, ch["id"]))
    flash("已开启自动吃喝：包里有熟食/应急食品/净水,以及个人生活工坊做的饭菜饮品,都会按恢复量从小到大自动吃到不饿、喝到不渴"
          "（不会碰生水和生鲜，怕自动吃出中毒；只补数值，不会触发手动享用才有的娱乐/体力/战斗加成）"
          if new_val else "已关闭自动吃喝")
    return redirect(url_for("dashboard"))

@app.route("/action/consume", methods=["POST"])
@login_required
@need_character
def action_consume(ch):
    kind = request.form.get("kind")  # food / emergency_food / raw_water / clean_water / cooked_food
    resource_key = {"food": "raw_food", "raw_water": "raw_water", "clean_water": "clean_water",
                     "cooked_food": "cooked_food", "emergency_food": "emergency_food"}.get(kind)
    if not resource_key:
        flash("参数不对")
        return redirect(url_for("dashboard"))
    have = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
             (ch["id"], resource_key), one=True)
    if not have or have["amount"] <= 0:
        flash("身上没有这个东西")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], resource_key, -1)
    if kind == "food":
        new_val = min(100, ch["hunger"] + 25)
        poison_chance = (RAW_FOOD_POISON_CHANCE_IRON_STOMACH if has_trait(ch, "iron_stomach")
                         else RAW_FOOD_POISON_CHANCE)
        if random.random() < poison_chance:
            run("UPDATE characters SET hunger=?,poison_until_ts=? WHERE id=?",
                (new_val, now_ts() + POISON_DURATION_SECONDS, ch["id"]))
            flash(f"直接吃了生鲜,饥饿值恢复25,但吃出食物中毒了!({int(poison_chance*100)}%概率)")
        else:
            run("UPDATE characters SET hunger=? WHERE id=?", (new_val, ch["id"]))
            flash("直接吃了生鲜,饥饿值恢复25,这次没有中毒")
    elif kind == "emergency_food":
        new_hunger = min(100, ch["hunger"] + 50)
        new_thirst = max(0, ch["thirst"] - EMERGENCY_FOOD_THIRST_COST)
        run("UPDATE characters SET hunger=?,thirst=? WHERE id=?", (new_hunger, new_thirst, ch["id"]))
        flash(f"吃了一份应急食品,饥饿值恢复50,但太干太咸,口渴值-{EMERGENCY_FOOD_THIRST_COST}")
    elif kind == "cooked_food":
        cooked_gain = BLUEPRINTS["cooked_food"]["hunger"] + (5 if has_trait(ch, "cook_soul") else 0)
        new_val = min(100, ch["hunger"] + cooked_gain)
        run("UPDATE characters SET hunger=? WHERE id=?", (new_val, ch["id"]))
        set_combat_preparation(ch, "food", "cooked_food")
        fun = recreation_gain(ch, 4, "吃一顿热饭")
        _, stamina_gain = restore_stamina(ch, 8, "吃一顿热饭")
        flash(f"吃了一份熟食,饥饿值恢复{cooked_gain}，娱乐+{fun}、体力+{stamina_gain}；"
              "今日战斗伤害与防守小幅提高")
    elif kind == "clean_water":
        new_val = min(100, ch["thirst"] + 25)
        run("UPDATE characters SET thirst=? WHERE id=?", (new_val, ch["id"]))
        flash("喝了一份净水,口渴值恢复25,绝对安全")
    else:
        new_val = min(100, ch["thirst"] + 25)
        run("UPDATE characters SET thirst=? WHERE id=?", (new_val, ch["id"]))
        poison_chance = (RAW_WATER_POISON_CHANCE_IRON_STOMACH if has_trait(ch, "iron_stomach")
                         else RAW_WATER_POISON_CHANCE)
        if random.random() < poison_chance:
            run("UPDATE characters SET poison_until_ts=? WHERE id=?", (now_ts() + POISON_DURATION_SECONDS, ch["id"]))
            flash(f"直接喝了生水,口渴值恢复25,但中毒了!({int(poison_chance*100)}%概率)")
        else:
            flash("直接喝了生水,口渴值恢复25,这次没有中毒")
    return redirect(url_for("dashboard"))

@app.route("/action/boil-water", methods=["POST"])
@login_required
@need_character
def action_boil_water(ch):
    """前期即可使用的简易煮水；检测台仍负责辨认污染并以更合适材料处理。"""
    cost = {"raw_water": 1, "wood": 1}
    if not _has_enough(ch, cost):
        flash("简易煮水需要生水x1和木材x1")
    else:
        _deduct(ch, cost)
        inv_add("character_inventory", "character_id", ch["id"], "clean_water", 1)
        record_long_progress(ch["id"], "safe_water", 1)
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 2)
        flash("你用简易火堆煮沸了一份生水，得到净水x1。检测台仍能处理更复杂污染。")
    return redirect(url_for("dashboard"))

# ── 路由:炉子(六节:生水→净水) ────────────────────────────────────────────

def _my_shelter_here(ch):
    shelter = q("SELECT * FROM shelters WHERE tile_x=? AND tile_y=? AND abandoned=0",
                (ch["tile_x"], ch["tile_y"]), one=True)
    if shelter and ch["shelter_id"] == shelter["id"]:
        return shelter
    return None

@app.route("/action/build_furnace", methods=["POST"])
@login_required
@need_character
def action_build_furnace(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能建炉子")
    elif shelter["has_furnace"]:
        flash("这个庇护所已经有炉子了")
    elif not _has_enough_with_local(ch, FURNACE_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in FURNACE_COST.items()))
    else:
        _deduct_with_local(ch, FURNACE_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_furnace=1 WHERE id=?", (shelter["id"],))
        add_region_noise(ch, 8, f"{display_name(ch)}安装了庇护所净水炉。", "build")
        flash("炉子建好了")
    return redirect(url_for("dashboard"))

@app.route("/action/furnace_start", methods=["POST"])
@login_required
@need_character
def action_furnace_start(ch):
    shelter = _my_shelter_here(ch)
    if not shelter or not shelter["has_furnace"]:
        flash("这里没有炉子")
        return redirect(url_for("dashboard"))
    if shelter["furnace_ready_ts"]:
        flash("炉子正在煮/已经煮好了,先去收")
        return redirect(url_for("dashboard"))
    for k, need in FURNACE_BATCH_INPUT.items():
        row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?", (shelter["id"], k), one=True)
        if not row or row["amount"] < need:
            flash("庇护所仓库里的材料不够:需要 " + "、".join(f"{RESOURCES[kk][0]}{vv}" for kk, vv in FURNACE_BATCH_INPUT.items()))
            return redirect(url_for("dashboard"))
    powered = consume_power("shelter", shelter["id"], 2, "净水炉批次",
                            character_id=ch["id"])
    if not powered:
        wood = q("""SELECT amount FROM shelter_inventory
                    WHERE shelter_id=? AND resource_key='wood'""",
                 (shelter["id"],), one=True)
        if not wood or wood["amount"] < FURNACE_FALLBACK_WOOD:
            flash(f"净水炉需要电力2；当前无法供电，改烧火需要庇护所木材x{FURNACE_FALLBACK_WOOD}")
            return redirect(url_for("dashboard"))
        inv_add("shelter_inventory", "shelter_id", shelter["id"],
                "wood", -FURNACE_FALLBACK_WOOD)
    for k, need in FURNACE_BATCH_INPUT.items():
        inv_add("shelter_inventory", "shelter_id", shelter["id"], k, -need)
    run("UPDATE shelters SET furnace_ready_ts=? WHERE id=?", (now_ts() + FURNACE_BATCH_SECONDS, shelter["id"]))
    noise = 1 if powered else 6
    add_region_noise(ch, noise,
                     f"{display_name(ch)}用{'电热净水炉' if powered else '木柴炉火'}处理整批饮水。",
                     "life")
    flash(f"开始煮水，{'消耗电力2' if powered else f'烧掉木材{FURNACE_FALLBACK_WOOD}'}；"
          f"{FURNACE_BATCH_SECONDS//60}分钟后回来收")
    return redirect(url_for("dashboard"))

@app.route("/action/furnace_collect", methods=["POST"])
@login_required
@need_character
def action_furnace_collect(ch):
    shelter = _my_shelter_here(ch)
    if not shelter or not shelter["furnace_ready_ts"]:
        flash("炉子里没有正在煮的东西")
        return redirect(url_for("dashboard"))
    if now_ts() < shelter["furnace_ready_ts"]:
        remain = shelter["furnace_ready_ts"] - now_ts()
        flash(f"还没煮好,还要等{remain//60+1}分钟")
        return redirect(url_for("dashboard"))
    cap = shelter_inventory_cap_for(shelter)
    total = inv_total("shelter_inventory", "shelter_id", shelter["id"])
    output = min(FURNACE_BATCH_OUTPUT, max(0, cap - total))
    inv_add("shelter_inventory", "shelter_id", shelter["id"], "clean_water", output)
    run("UPDATE shelters SET furnace_ready_ts=0 WHERE id=?", (shelter["id"],))
    flash(f"收了{output}份净水" + ("(仓库快满了,溢出部分没收到)" if output < FURNACE_BATCH_OUTPUT else ""))
    return redirect(url_for("dashboard"))

# ── 路由:田地(五节:庇护所自带田地,按天产出) ─────────────────────────────

@app.route("/action/farm_harvest", methods=["POST"])
@login_required
@need_character
def action_farm_harvest(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能种田")
        return redirect(url_for("dashboard"))
    if now_ts() < shelter["farm_ready_ts"]:
        remain = shelter["farm_ready_ts"] - now_ts()
        flash(f"作物还没成熟,还要等{remain//60+1}分钟")
        return redirect(url_for("dashboard"))
    int_bonus = 1 + min(ch["stat_int"], 20) * FARM_INT_YIELD_BONUS_PER_POINT
    fert_row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?",
                 (shelter["id"], COMPOST_OUTPUT_KEY), one=True)
    used_fertilizer = bool(fert_row and fert_row["amount"] > 0)
    fert_bonus = (1 + COMPOST_YIELD_BOOST) if used_fertilizer else 1
    yield_amt = int(FARM_YIELD_PER_PLOT * shelter["farmland_plots"] * int_bonus * fert_bonus)
    cap = shelter_inventory_cap_for(shelter)
    total = inv_total("shelter_inventory", "shelter_id", shelter["id"])
    output = min(yield_amt, max(0, cap - total))
    inv_add("shelter_inventory", "shelter_id", shelter["id"], "raw_food", output)
    # 生活工坊食材归实际收获者，普通田地产蔬菜/谷物，温室还会有野果。
    kitchen_crop = random.choice(["vegetable", "grain"] + (["fruit"] if shelter["has_greenhouse"] else []))
    crop_amount = max(1, output // 4) if output > 0 else 0
    if crop_amount:
        inv_add("character_inventory", "character_id", ch["id"], kitchen_crop, crop_amount)
    if used_fertilizer:
        inv_add("shelter_inventory", "shelter_id", shelter["id"], COMPOST_OUTPUT_KEY, -1)
    run("UPDATE shelters SET farm_ready_ts=? WHERE id=?", (now_ts() + FARM_HARVEST_SECONDS, shelter["id"]))
    grant_xp(ch, FARM_HARVEST_XP)
    maybe_grow_stat(ch, "stat_int")
    flash(f"收获了{output}份生鲜" + (f"，并挑出{ITEM_NAMES[kitchen_crop]}x{crop_amount}" if crop_amount else "") +
          ("(用掉1份肥料,产量+20%)" if used_fertilizer else "") +
          ("(仓库快满了,溢出部分没收到)" if output < yield_amt else ""))
    return redirect(url_for("dashboard"))

@app.route("/action/build_greenhouse", methods=["POST"])
@login_required
@need_character
def action_build_greenhouse(ch):
    shelter = _my_shelter_here(ch)
    material_cost = {k: v for k, v in GREENHOUSE_COST.items() if k != "research_points"}
    if not shelter:
        flash("要在自己所属的庇护所地块才能建温室")
    elif shelter["has_greenhouse"]:
        flash("这个庇护所已经有温室了")
    elif shelter["research_points"] < GREENHOUSE_COST["research_points"]:
        flash(f"科研点数不够,需要{GREENHOUSE_COST['research_points']}点(打赢丧尸会给所属庇护所+1)")
    elif not _has_enough_with_local(ch, material_cost, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in material_cost.items()))
    else:
        _deduct_with_local(ch, material_cost, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_greenhouse=1, research_points=research_points-? WHERE id=?",
            (GREENHOUSE_COST["research_points"], shelter["id"]))
        add_region_noise(ch, 12, f"{display_name(ch)}搭建了温室骨架与管线。", "build")
        flash("温室建好了,现在能种稀有种子了")
    return redirect(url_for("dashboard"))

@app.route("/action/plant_seed", methods=["POST"])
@login_required
@need_character
def action_plant_seed(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能种稀有种子")
        return redirect(url_for("dashboard"))
    if not shelter["has_greenhouse"]:
        flash("没有温室,种不了稀有种子")
        return redirect(url_for("dashboard"))
    row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key='rare_seed'", (shelter["id"],), one=True)
    if not row or row["amount"] < 1:
        flash("庇护所仓库里没有稀有种子")
        return redirect(url_for("dashboard"))
    powered = consume_power("shelter", shelter["id"], 2, "温室补光与循环泵",
                            character_id=ch["id"])
    inv_add("shelter_inventory", "shelter_id", shelter["id"], "rare_seed", -1)
    yield_amount = RARE_SEED_YIELD if powered else max(1, RARE_SEED_YIELD - 1)
    inv_add("shelter_inventory", "shelter_id", shelter["id"], "prized_herb", yield_amount)
    grant_xp(ch, 8)
    maybe_grow_stat(ch, "stat_luck")
    flash(f"种下的稀有种子结出了{yield_amount}份珍稀药草；" +
          ("温室电力-2，补光和循环正常" if powered else "当前未供电，只维持了最低产量"))
    return redirect(url_for("dashboard"))

@app.route("/action/compost", methods=["POST"])
@login_required
@need_character
def action_compost(ch):
    """B档61条:动物粪便→肥料,依赖驯养系统产出的副产品(见 run_tick 里的被动产出)。"""
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能堆肥")
        return redirect(url_for("dashboard"))
    for k, need in COMPOST_INPUT.items():
        row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?", (shelter["id"], k), one=True)
        if not row or row["amount"] < need:
            flash("庇护所仓库里的材料不够:需要 " + "、".join(f"{ITEM_NAMES[kk]}{vv}" for kk, vv in COMPOST_INPUT.items()))
            return redirect(url_for("dashboard"))
    for k, need in COMPOST_INPUT.items():
        inv_add("shelter_inventory", "shelter_id", shelter["id"], k, -need)
    inv_add("shelter_inventory", "shelter_id", shelter["id"], COMPOST_OUTPUT_KEY, 1)
    flash(f"堆好了1份{ITEM_NAMES[COMPOST_OUTPUT_KEY]},下次收获田地时会自动用掉,产量+{int(COMPOST_YIELD_BOOST*100)}%")
    return redirect(url_for("dashboard"))

# ── 路由:解药研发(11.3:每个庇护所各自独立研发) ─────────────────────────────

@app.route("/action/unlock_vaccine", methods=["POST"])
@login_required
@need_character
def action_unlock_vaccine(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能研发解药")
    elif shelter["has_vaccine"]:
        flash("这个庇护所已经研发出解药了")
    elif shelter["research_points"] < VACCINE_UNLOCK_RESEARCH:
        flash(f"科研点数不够,需要{VACCINE_UNLOCK_RESEARCH}点(打赢丧尸会给所属庇护所+1)")
    elif not _has_enough_with_local(ch, VACCINE_UNLOCK_MATERIALS, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in VACCINE_UNLOCK_MATERIALS.items()))
    else:
        _deduct_with_local(ch, VACCINE_UNLOCK_MATERIALS, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_vaccine=1, research_points=research_points-? WHERE id=?",
            (VACCINE_UNLOCK_RESEARCH, shelter["id"]))
        flash("解药研发出来了!以后能在这个庇护所里清除感染度")
    return redirect(url_for("dashboard"))

@app.route("/action/use_vaccine", methods=["POST"])
@login_required
@need_character
def action_use_vaccine(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能用解药")
        return redirect(url_for("dashboard"))
    if not shelter["has_vaccine"]:
        flash("这个庇护所还没研发出解药")
        return redirect(url_for("dashboard"))
    if ch["infection"] <= 0:
        flash("感染度已经是0了,不用打解药")
        return redirect(url_for("dashboard"))
    for k, need in VACCINE_DOSE_COST.items():
        row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?", (shelter["id"], k), one=True)
        if not row or row["amount"] < need:
            flash("庇护所仓库里的材料不够:需要 " + "、".join(f"{ITEM_NAMES[kk]}{vv}" for kk, vv in VACCINE_DOSE_COST.items()))
            return redirect(url_for("dashboard"))
    for k, need in VACCINE_DOSE_COST.items():
        inv_add("shelter_inventory", "shelter_id", shelter["id"], k, -need)
    run("UPDATE characters SET infection=0 WHERE id=?", (ch["id"],))
    flash("打了解药,感染度清零了(九.2:这是唯一的清除手段,HP不会跟着恢复)")
    return redirect(url_for("dashboard"))

# ── 路由:防御建筑(十六.3:围墙/陷阱/瞭望塔,各自可叠加) ───────────────────────

DEFENSE_COLUMN = {"wall": "defense_walls", "trap": "defense_traps", "tower": "defense_tower"}

@app.route("/action/build_defense", methods=["POST"])
@login_required
@need_character
def action_build_defense(ch):
    kind = request.form.get("kind")
    if kind not in DEFENSE_BUILDINGS:
        flash("没有这种防御建筑")
        return redirect(url_for("dashboard"))
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能建防御建筑")
        return redirect(url_for("dashboard"))
    info = DEFENSE_BUILDINGS[kind]
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in info["cost"].items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, info["cost"], local_ref)
    col = DEFENSE_COLUMN[kind]
    run(f"UPDATE shelters SET {col}={col}+1 WHERE id=?", (shelter["id"],))
    add_region_noise(ch, {"wall": 10, "trap": 6, "tower": 12}[kind],
                     f"{display_name(ch)}修建了{info['name']}。", "build")
    flash(f"造了一个{info['name']},防御值+{info['value']}(可以接着叠加)")
    return redirect(url_for("dashboard"))

# ── 路由:终局装置(十二节:归途装置) ─────────────────────────────────────────

@app.route("/action/build_endgame_device", methods=["POST"])
@login_required
@need_character
def action_build_endgame_device(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能建终局装置")
    elif shelter["has_endgame_device"]:
        flash("这个庇护所已经建过终局装置了")
    elif shelter["tier"] < ENDGAME_UNLOCK_TIER:
        flash(f"庇护所要先升到Lv{ENDGAME_UNLOCK_TIER}(顶级)才能建终局装置")
    elif shelter["research_points"] < ENDGAME_UNLOCK_RESEARCH:
        flash(f"科研点数不够,需要{ENDGAME_UNLOCK_RESEARCH}点")
    elif not _has_enough_with_local(ch, ENDGAME_BUILD_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in ENDGAME_BUILD_COST.items()))
    else:
        _deduct_with_local(ch, ENDGAME_BUILD_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_endgame_device=1, research_points=research_points-? WHERE id=?",
            (ENDGAME_UNLOCK_RESEARCH, shelter["id"]))
        flash(f"归途装置建好了!接下来往庇护所仓库存够{ENDGAME_MATERIAL_NEEDED}份{ITEM_NAMES[ENDGAME_MATERIAL_KEY]}就能激活")
    return redirect(url_for("dashboard"))

@app.route("/action/activate_endgame_device", methods=["POST"])
@login_required
@need_character
def action_activate_endgame_device(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能激活终局装置")
        return redirect(url_for("dashboard"))
    if not shelter["has_endgame_device"]:
        flash("还没建终局装置")
        return redirect(url_for("dashboard"))
    if shelter["completed_ending"]:
        flash("这个庇护所已经完结过了")
        return redirect(url_for("dashboard"))
    row = q("SELECT amount FROM shelter_inventory WHERE shelter_id=? AND resource_key=?",
             (shelter["id"], ENDGAME_MATERIAL_KEY), one=True)
    have = row["amount"] if row else 0
    if have < ENDGAME_MATERIAL_NEEDED:
        flash(f"{ITEM_NAMES[ENDGAME_MATERIAL_KEY]}还不够,现在{have}/{ENDGAME_MATERIAL_NEEDED}")
        return redirect(url_for("dashboard"))
    inv_add("shelter_inventory", "shelter_id", shelter["id"], ENDGAME_MATERIAL_KEY, -ENDGAME_MATERIAL_NEEDED)
    run("UPDATE shelters SET completed_ending=1 WHERE id=?", (shelter["id"],))
    run("INSERT INTO shelter_notifications (shelter_id, message, created_ts) VALUES (?,?,?)",
        (shelter["id"], f"🎆 「{shelter['name']}」激活了归途装置,你们做到了!(十二.2:可以继续正常生活,不强制退出)", now_ts()))
    flash("🎆 归途装置激活了!你们完成了主线")
    return redirect(url_for("dashboard"))

# ── 路由:狩猎陷阱(B档60条,和防御用的"陷阱"是两回事) ───────────────────────

@app.route("/action/build_hunting_trap", methods=["POST"])
@login_required
@need_character
def action_build_hunting_trap(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能放陷阱")
    elif shelter["has_hunting_trap"]:
        flash("这个庇护所已经有狩猎陷阱了")
    elif not _has_enough_with_local(ch, HUNTING_TRAP_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in HUNTING_TRAP_COST.items()))
    else:
        _deduct_with_local(ch, HUNTING_TRAP_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_hunting_trap=1, hunting_trap_ready_ts=? WHERE id=?", (now_ts(), shelter["id"]))
        flash("狩猎陷阱放好了,过一阵子回来收")
    return redirect(url_for("dashboard"))

@app.route("/action/collect_hunting_trap", methods=["POST"])
@login_required
@need_character
def action_collect_hunting_trap(ch):
    shelter = _my_shelter_here(ch)
    if not shelter or not shelter["has_hunting_trap"]:
        flash("这里没有狩猎陷阱")
        return redirect(url_for("dashboard"))
    if now_ts() < shelter["hunting_trap_ready_ts"]:
        remain = shelter["hunting_trap_ready_ts"] - now_ts()
        flash(f"陷阱还没到时间,还要等{remain//60+1}分钟")
        return redirect(url_for("dashboard"))
    food_gain = random.randint(1, 2)
    inv_add("shelter_inventory", "shelter_id", shelter["id"], "raw_food", food_gain)
    bonus = ""
    if random.random() < HUNTING_TRAP_RARE_CHANCE:
        inv_add("shelter_inventory", "shelter_id", shelter["id"], "pelt", 1)
        bonus = " + 1张兽皮"
    run("UPDATE shelters SET hunting_trap_ready_ts=? WHERE id=?",
        (now_ts() + HUNTING_TRAP_COOLDOWN_SECONDS, shelter["id"]))
    flash(f"收陷阱:{food_gain}份生鲜{bonus}")
    return redirect(url_for("dashboard"))

# ── 路由:驯养(B档,MVP版:遇到→喂食→驯服→兽栏) ───────────────────────────────

@app.route("/taming")
@login_required
@need_character
def taming(ch):
    if not ch["pending_tame_key"]:
        return redirect(url_for("dashboard"))
    animal = ANIMALS[ch["pending_tame_key"]]
    return render_template("taming.html", ch=ch, animal=animal,
                            threshold=TAME_AFFINITY_THRESHOLD, feed_gain=TAME_FEED_GAIN)

@app.route("/action/tame_feed", methods=["POST"])
@login_required
@need_character
def action_tame_feed(ch):
    if not ch["pending_tame_key"]:
        flash("没有正在驯服的动物")
        return redirect(url_for("dashboard"))
    have = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key='raw_food'", (ch["id"],), one=True)
    if not have or have["amount"] < 1:
        flash("身上没有生鲜可以喂")
        return redirect(url_for("taming"))
    inv_add("character_inventory", "character_id", ch["id"], "raw_food", -1)
    animal = ANIMALS[ch["pending_tame_key"]]
    if random.random() < TAME_SPOOK_CHANCE:
        run("UPDATE characters SET pending_tame_key=NULL, pending_tame_affinity=0 WHERE id=?", (ch["id"],))
        flash(f"{animal['name']}被吓跑了,驯服失败")
        return redirect(url_for("dashboard"))
    new_affinity = ch["pending_tame_affinity"] + TAME_FEED_GAIN
    if has_trait(ch, "animal_friend"):
        new_affinity += 5
    if new_affinity >= TAME_AFFINITY_THRESHOLD:
        run("""UPDATE characters SET pending_tame_key=NULL, pending_tame_affinity=0,
               tamed_animal_key=?, animal_collect_ready_ts=? WHERE id=?""",
            (ch["pending_tame_key"], now_ts() + 86400, ch["id"]))
        run("""INSERT OR REPLACE INTO tamed_animal_profiles
               (character_id,animal_key,custom_name,tamed_ts,battles_won,resources_produced)
               VALUES(?,?,?,?,0,0)""",
            (ch["id"], ch["pending_tame_key"], animal["name"], now_ts()))
        grant_xp(ch, 15)
        maybe_grow_stat(ch, "stat_luck")
        flash(f"驯服成功!{animal['name']}跟你回家了(要带回庇护所兽栏才能发挥作用)")
        return redirect(url_for("dashboard"))
    run("UPDATE characters SET pending_tame_affinity=? WHERE id=?", (new_affinity, ch["id"]))
    flash(f"喂了一份生鲜,好感度{new_affinity}/{TAME_AFFINITY_THRESHOLD}")
    return redirect(url_for("taming"))

@app.route("/action/tame_flee", methods=["POST"])
@login_required
@need_character
def action_tame_flee(ch):
    run("UPDATE characters SET pending_tame_key=NULL, pending_tame_affinity=0 WHERE id=?", (ch["id"],))
    flash("放弃了这次驯服")
    return redirect(url_for("dashboard"))

@app.route("/action/build_animal_pen", methods=["POST"])
@login_required
@need_character
def action_build_animal_pen(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能建兽栏")
    elif shelter["has_animal_pen"]:
        flash("这个庇护所已经有兽栏了")
    elif not _has_enough_with_local(ch, ANIMAL_PEN_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in ANIMAL_PEN_COST.items()))
    else:
        _deduct_with_local(ch, ANIMAL_PEN_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_animal_pen=1 WHERE id=?", (shelter["id"],))
        flash("兽栏建好了,驯服的动物带回来才能发挥作用")
    return redirect(url_for("dashboard"))

def _animal_bonus_active(ch, animal_key):
    """驯服的动物必须带回庇护所兽栏才有效果(五节已确认)。"""
    if ch["tamed_animal_key"] != animal_key or not ch["shelter_id"]:
        return False
    shelter = q("SELECT has_animal_pen FROM shelters WHERE id=?", (ch["shelter_id"],), one=True)
    return bool(shelter and shelter["has_animal_pen"])

@app.route("/animal/rename", methods=["POST"])
@login_required
@need_character
def animal_rename(ch):
    name = " ".join((request.form.get("name") or "").strip().split())
    if not ch["tamed_animal_key"]:
        flash("你还没有驯服的动物")
    elif not name or len(name) > 20:
        flash("动物名字需要1-20个字")
    else:
        run("UPDATE tamed_animal_profiles SET custom_name=? WHERE character_id=?", (name, ch["id"]))
        flash(f"以后它就叫「{name}」了")
    return redirect(url_for("dashboard"))

# ── 路由:系统收购点(十四.1:钱包货币唯一来源) ───────────────────────────────

@app.route("/action/sell", methods=["POST"])
@login_required
@need_character
def action_sell(ch):
    resource_key = request.form.get("resource_key")
    amount = request.form.get("amount", type=int) or 0
    is_fish = resource_key in FISH_SPECIES
    if (resource_key not in SELLABLE_RESOURCES and not is_fish) or amount <= 0:
        flash("这个东西不能卖给系统收购点")
        return redirect(url_for("dashboard"))
    have = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
             (ch["id"], resource_key), one=True)
    if not have or have["amount"] < amount:
        flash("身上没有这么多")
        return redirect(url_for("dashboard"))
    rate = SELLABLE_FISH_VALUES[resource_key] if is_fish else SELL_RATE
    inv_add("character_inventory", "character_id", ch["id"], resource_key, -amount)
    run("UPDATE characters SET wallet=wallet+? WHERE id=?", (amount * rate, ch["id"]))
    flash(f"卖了{amount}份{ITEM_NAMES[resource_key]},换到{amount*rate}钱包货币")
    return redirect(url_for("dashboard"))

@app.route("/merchant")
@login_required
@need_character
def merchant(ch):
    stock = q("SELECT * FROM merchant_stock WHERE stock_amount>0 ORDER BY resource_key")
    return render_template("merchant.html", ch=ch, stock=stock,
                           resources=RESOURCES, item_names=ITEM_NAMES)

@app.route("/action/merchant_buy", methods=["POST"])
@login_required
@need_character
def action_merchant_buy(ch):
    resource_key = request.form.get("resource_key")
    amount = request.form.get("amount", type=int) or 0
    row = q("SELECT * FROM merchant_stock WHERE resource_key=?", (resource_key,), one=True)
    if not row or amount <= 0:
        flash("商人没有卖这个")
        return redirect(url_for("merchant"))
    if row["stock_amount"] < amount:
        flash(f"商人只剩{row['stock_amount']}份了")
        return redirect(url_for("merchant"))
    cost = amount * row["price"]
    if ch["wallet"] < cost:
        flash(f"钱包货币不够,需要{cost}")
        return redirect(url_for("merchant"))
    cap = char_inv_capacity(ch)
    carried = inv_total("character_inventory", "character_id", ch["id"])
    if carried + amount > cap:
        flash("随身储物放不下了")
        return redirect(url_for("merchant"))
    cur = run("UPDATE merchant_stock SET stock_amount=stock_amount-? WHERE resource_key=? AND stock_amount>=?",
              (amount, resource_key, amount))
    if cur.rowcount == 0:
        flash("手慢了,商人的货刚被人买走了")
        return redirect(url_for("merchant"))
    run("UPDATE characters SET wallet=wallet-? WHERE id=?", (cost, ch["id"]))
    inv_add("character_inventory", "character_id", ch["id"], resource_key, amount)
    flash(f"花{cost}钱包货币,买了{amount}份{ITEM_NAMES.get(resource_key, resource_key)}")
    return redirect(url_for("merchant"))

# ── 路由:建造 ─────────────────────────────────────────────────────────────

def _has_enough(ch, cost):
    for k, need in cost.items():
        row = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
                 (ch["id"], k), one=True)
        if not row or row["amount"] < need:
            return False
    return True

def _deduct(ch, cost):
    for k, need in cost.items():
        inv_add("character_inventory", "character_id", ch["id"], k, -need)

def _has_enough_with_local(ch, cost, local_ref=None):
    """同_has_enough，但local_ref=(table,id_col,id_val)时随身不够可以补用房子/庇护所仓库。"""
    for k, need in cost.items():
        row = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
                (ch["id"], k), one=True)
        total = row["amount"] if row else 0
        if local_ref:
            table, id_col, id_val = local_ref
            local_row = q(f"SELECT amount FROM {table} WHERE {id_col}=? AND resource_key=?",
                         (id_val, k), one=True)
            total += local_row["amount"] if local_row else 0
        if total < need:
            return False
    return True

def _deduct_with_local(ch, cost, local_ref=None):
    """优先扣随身携带，不够的部分从local_ref(房子/庇护所仓库)里补扣。"""
    for k, need in cost.items():
        row = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
                (ch["id"], k), one=True)
        carried = row["amount"] if row else 0
        use_carried = min(carried, need)
        if use_carried:
            inv_add("character_inventory", "character_id", ch["id"], k, -use_carried)
        remaining = need - use_carried
        if remaining and local_ref:
            table, id_col, id_val = local_ref
            inv_add(table, id_col, id_val, k, -remaining)

def house_repair_cost(house):
    level = max(1, min(HOUSE_LEVEL_CAP, house["level"]))
    cost = {"wood": 5 + level * 2, "stone": 3 + level}
    if level >= 3:
        cost["metal"] = (level - 2) * 2
    return cost

def house_upgrade_access(ch, next_level):
    required_tier = HOUSE_LEVELS[next_level]["shelter_tier"]
    if not required_tier:
        return True, ""
    if not ch["shelter_id"]:
        return False, f"需要先加入或建立庇护所，并把庇护所升到Lv{required_tier}"
    shelter = q("SELECT * FROM shelters WHERE id=? AND abandoned=0",
                (ch["shelter_id"],), one=True)
    if not shelter or shelter["tier"] < required_tier:
        have = shelter["tier"] if shelter else 0
        return False, f"需要所属庇护所达到Lv{required_tier}（当前Lv{have}）"
    return True, ""

@app.route("/action/build_house", methods=["POST"])
@login_required
@need_character
def action_build_house(ch):
    buildable, reason = tile_is_buildable(ch["tile_x"], ch["tile_y"])
    if not buildable:
        flash(reason)
        return redirect(url_for("dashboard"))
    if not _has_enough(ch, HOUSE_COST):
        flash("材料不够:需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in HOUSE_COST.items()))
        return redirect(url_for("dashboard"))
    _deduct(ch, HOUSE_COST)
    run("""INSERT INTO houses
           (owner_user_id,tile_x,tile_y,level,hp,max_hp,auto_defense,built_ts)
           VALUES(?,?,?,1,80,80,0,?)""",
        (ch["user_id"], ch["tile_x"], ch["tile_y"], now_ts()))
    add_region_noise(ch, 14, f"{display_name(ch)}搭建了一座新的房屋。", "build")
    record_long_progress(ch["id"], "home", 1)
    run("UPDATE world_tiles SET has_building=1 WHERE x=? AND y=?", (ch["tile_x"], ch["tile_y"]))
    award_tag(ch["id"], "home_maker")
    remember_location(ch["id"], ch["tile_x"], ch["tile_y"], "你在这里建起了属于自己的房间。")
    grant_xp(ch, 20)
    maybe_grow_stat(ch, "stat_int")
    flash("临时木屋建好了。它能挡住一段时间的夜袭，但不是永久安全区。")
    return redirect(url_for("dashboard"))

@app.route("/action/upgrade_house", methods=["POST"])
@login_required
@need_character
def action_upgrade_house(ch):
    house = q("""SELECT * FROM houses
                 WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0""",
              (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    if not house:
        flash("要站在自己的房屋所在地才能升级")
        return redirect(url_for("dashboard"))
    if house["level"] >= HOUSE_LEVEL_CAP:
        flash("这栋房屋已经达到最高等级")
        return redirect(url_for("dashboard"))
    if house["hp"] < house["max_hp"]:
        flash("先把房屋修满，再进行结构升级")
        return redirect(url_for("dashboard"))
    next_level = house["level"] + 1
    access, reason = house_upgrade_access(ch, next_level)
    if not access:
        flash(reason)
        return redirect(url_for("dashboard"))
    info = HOUSE_LEVELS[next_level]
    local_ref = ("house_inventory", "house_id", house["id"])
    if not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("升级材料不足(随身+房子仓库合计)：需要" + "、".join(
            f"{RESOURCES[k][0]}{v}" for k, v in info["cost"].items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, info["cost"], local_ref)
    run("""UPDATE houses SET level=?,hp=?,max_hp=?,auto_defense=?,auto_defense_damaged=0
           WHERE id=?""",
        (next_level, info["max_hp"], info["max_hp"],
         1 if info["counter"] > 0 else 0, house["id"]))
    add_region_noise(ch, 10 + next_level * 2,
                     f"{display_name(ch)}把房屋升级到了Lv{next_level}。", "build")
    record_long_progress(ch["id"], "home", 1)
    record_long_progress(ch["id"], "prepare", 1)
    grant_xp(ch, 10)
    log_action(ch["id"], "house_upgrade", f"房屋升级到Lv{next_level} {info['name']}")
    extra = "，自动反击系统已经接通" if info["counter"] > 0 else ""
    flash(f"房屋升级为Lv{next_level}「{info['name']}」，耐久提升到{info['max_hp']}{extra}。")
    return redirect(url_for("dashboard"))

@app.route("/action/rename_house", methods=["POST"])
@login_required
@need_character
def action_rename_house(ch):
    house_id = request.form.get("house_id", type=int)
    name = request.form.get("name", "").strip()[:12]
    house = q("SELECT * FROM houses WHERE id=? AND owner_user_id=? AND abandoned=0",
              (house_id, ch["user_id"]), one=True)
    if not house:
        flash("找不到这栋房子")
        return redirect(url_for("map_view"))
    run("UPDATE houses SET custom_name=? WHERE id=?", (name, house["id"]))
    flash(f"房子改名为「{name}」了" if name else "已清空这栋房子的自定义名字")
    return redirect(url_for("map_view"))

@app.route("/action/repair_house", methods=["POST"])
@login_required
@need_character
def action_repair_house(ch):
    house = q("""SELECT * FROM houses
                 WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0""",
              (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    if not house:
        flash("要回到自己的房屋才能维修")
        return redirect(url_for("dashboard"))
    if house["hp"] >= house["max_hp"]:
        flash("房屋结构目前完好，不需要维修")
        return redirect(url_for("dashboard"))
    cost = house_repair_cost(house)
    local_ref = ("house_inventory", "house_id", house["id"])
    if not _has_enough_with_local(ch, cost, local_ref):
        flash("维修材料不足(随身+房子仓库合计)：需要" + "、".join(
            f"{RESOURCES[k][0]}{v}" for k, v in cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost, local_ref)
    restored = min(HOUSE_REPAIR_AMOUNT, house["max_hp"] - house["hp"])
    run("UPDATE houses SET hp=MIN(max_hp,hp+?) WHERE id=?", (restored, house["id"]))
    add_region_noise(ch, 4, f"{display_name(ch)}维修了受损房屋。", "repair")
    record_long_progress(ch["id"], "prepare", 1)
    log_action(ch["id"], "house_repair", f"房屋耐久+{restored}")
    flash(f"房屋耐久恢复{restored}点。")
    return redirect(url_for("dashboard"))

@app.route("/action/repair_house_auto_defense", methods=["POST"])
@login_required
@need_character
def action_repair_house_auto_defense(ch):
    house = q("""SELECT * FROM houses
                 WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0""",
              (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    if not house or house["level"] < 4:
        flash("这里没有可以维修的自动反击系统")
    elif not house["auto_defense_damaged"]:
        flash("自动反击系统目前工作正常")
    elif house["hp"] <= 0:
        flash("先恢复房屋结构，才能维修自动反击系统")
    elif not _has_enough_with_local(ch, HOUSE_AUTO_REPAIR_COST, ("house_inventory", "house_id", house["id"])):
        flash("维修自动反击系统需要(随身+房子仓库合计)" + "、".join(
            f"{RESOURCES[k][0]}{v}" for k, v in HOUSE_AUTO_REPAIR_COST.items()))
    else:
        _deduct_with_local(ch, HOUSE_AUTO_REPAIR_COST, ("house_inventory", "house_id", house["id"]))
        run("""UPDATE houses SET auto_defense=1,auto_defense_damaged=0
               WHERE id=?""", (house["id"],))
        add_region_noise(ch, 6, f"{display_name(ch)}重新校准了自动反击系统。", "repair")
        record_long_progress(ch["id"], "prepare", 1)
        flash("自动反击系统已恢复，重新装入房屋弹药后即可值守。")
    return redirect(url_for("dashboard"))

@app.route("/action/house_raid_stance", methods=["POST"])
@login_required
@need_character
def action_house_raid_stance(ch):
    house = house_here_for(ch)
    stance = request.form.get("stance")
    if not house:
        flash("要回到自己的房屋才能安排夜袭防守")
    elif stance not in RAID_STANCES:
        flash("没有这种防守方针")
    else:
        run("UPDATE houses SET raid_stance=? WHERE id=?", (stance, house["id"]))
        record_long_progress(ch["id"], "prepare", 1)
        log_action(ch["id"], "raid_stance", RAID_STANCES[stance][0])
        flash(f"本屋夜袭方针已设为「{RAID_STANCES[stance][0]}」。离线时也会自动执行。")
    return redirect(url_for("dashboard"))

def _power_target_here(ch, target):
    if target == "house":
        house = house_here_for(ch)
        return ("house", house["id"], house, "house_inventory", "house_id") if house else None
    if target == "shelter":
        shelter = _my_shelter_here(ch)
        return ("shelter", shelter["id"], shelter, "shelter_inventory", "shelter_id") if shelter else None
    return None

@app.route("/power/upgrade", methods=["POST"])
@login_required
@need_character
def power_upgrade(ch):
    target = _power_target_here(ch, request.form.get("target"))
    if not target:
        flash("必须站在自己的房屋或所属庇护所，才能建设电网")
        return redirect(url_for("dashboard"))
    owner_type, owner_id, _, inv_table, inv_id_col = target
    grid = ensure_power_grid(owner_type, owner_id)
    local_ref = (inv_table, inv_id_col, owner_id)
    next_level = grid["generator_level"] + 1
    info = GENERATOR_LEVELS.get(next_level)
    if not info:
        flash("这套电网已经升级到最高等级")
    elif grid["damaged"]:
        flash("先修复损坏的电网，才能继续升级")
    elif not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("发电设备材料不足(随身+当前仓库合计)：" + "、".join(
            f"{ITEM_NAMES.get(k, RESOURCES.get(k, (k,))[0])}{v}"
            for k, v in info["cost"].items()))
    else:
        _deduct_with_local(ch, info["cost"], local_ref)
        run("""UPDATE power_grids SET generator_level=?,charge=MIN(charge,?),
               updated_ts=? WHERE owner_type=? AND owner_id=?""",
            (next_level, info["capacity"], now_ts(), owner_type, owner_id))
        add_region_noise(ch, 7 + next_level * 2,
                         f"{display_name(ch)}安装了{info['name']}。", "power_build")
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 6)
        flash(f"{info['name']}已经接入，最大储能{info['capacity']}点")
    return redirect(url_for("dashboard"))

@app.route("/power/generate", methods=["POST"])
@login_required
@need_character
def power_generate(ch):
    target = _power_target_here(ch, request.form.get("target"))
    if not target:
        flash("必须回到对应建筑才能发电")
        return redirect(url_for("dashboard"))
    owner_type, owner_id, _, inventory_table, inventory_id_col = target
    grid = ensure_power_grid(owner_type, owner_id)
    info = GENERATOR_LEVELS.get(grid["generator_level"], GENERATOR_LEVELS[0])
    day = get_world_state()["day_count"]
    if not grid["generator_level"]:
        flash("这里还没有发电设备")
    elif grid["damaged"]:
        flash("发电设备已经损坏，需要先维修")
    elif grid["last_generation_day"] >= day:
        flash("今天已经完成过一次发电与储能，明天才能再次结算")
    elif grid["charge"] >= info["capacity"]:
        flash("储能已经充满")
    else:
        fuel_needed = info["fuel"]
        if fuel_needed:
            fuel = q(f"""SELECT amount FROM {inventory_table}
                         WHERE {inventory_id_col}=? AND resource_key='fuel'""",
                     (owner_id,), one=True)
            if not fuel or fuel["amount"] < fuel_needed:
                flash(f"{info['name']}需要建筑仓库中的{ITEM_NAMES['fuel']}x{fuel_needed}")
                return redirect(url_for("dashboard"))
            inv_add(inventory_table, inventory_id_col, owner_id, "fuel", -fuel_needed)
        output = info["output"]
        noise = info["noise"]
        if grid["generator_level"] == 3:
            solar_factor = {"clear": 1.0, "cold": .8, "rain": .55,
                            "fog": .45, "storm": .25}[weather_for_day(day)["key"]]
            output = max(2, int(round(output * solar_factor)))
        if grid["mode"] == "quiet":
            output = max(1, int(math.floor(output * .75)))
            noise = int(math.ceil(noise * .6))
        gained = min(output, info["capacity"] - grid["charge"])
        run("""UPDATE power_grids SET charge=charge+?,last_generation_day=?,updated_ts=?
               WHERE owner_type=? AND owner_id=?""",
            (gained, day, now_ts(), owner_type, owner_id))
        run("""INSERT INTO power_logs
               (owner_type,owner_id,character_id,event_key,power_change,detail,created_ts)
               VALUES(?,?,?,'generate',?,?,?)""",
            (owner_type, owner_id, ch["id"], gained,
             f"{info['name']}完成一次发电，储能+{gained}。", now_ts()))
        if noise:
            add_region_noise(ch, noise,
                             f"{display_name(ch)}启动{info['name']}，发动机声传遍附近。",
                             "power_generation")
        flash(f"发电完成，储能+{gained}" +
              (f"，区域噪声+{noise}" if noise else "，没有产生明显噪声"))
    return redirect(url_for("dashboard"))

@app.route("/power/mode", methods=["POST"])
@login_required
@need_character
def power_mode(ch):
    target = _power_target_here(ch, request.form.get("target"))
    mode = request.form.get("mode")
    if not target or mode not in POWER_MODES:
        flash("无法调整这套电网")
    else:
        owner_type, owner_id, _, _, _ = target
        ensure_power_grid(owner_type, owner_id)
        run("""UPDATE power_grids SET mode=?,updated_ts=?
               WHERE owner_type=? AND owner_id=?""",
            (mode, now_ts(), owner_type, owner_id))
        flash(f"电网已切换为「{POWER_MODES[mode][0]}」")
    return redirect(url_for("dashboard"))

@app.route("/power/repair", methods=["POST"])
@login_required
@need_character
def power_repair(ch):
    target = _power_target_here(ch, request.form.get("target"))
    cost = {"metal": 8, "parts": 3}
    if not target:
        flash("必须回到对应建筑维修电网")
    else:
        owner_type, owner_id, _, inv_table, inv_id_col = target
        grid = ensure_power_grid(owner_type, owner_id)
        local_ref = (inv_table, inv_id_col, owner_id)
        if not grid["damaged"]:
            flash("电网目前工作正常")
        elif not _has_enough_with_local(ch, cost, local_ref):
            flash("维修电网需要(随身+当前仓库合计)金属x8、机械零件x3")
        else:
            _deduct_with_local(ch, cost, local_ref)
            run("""UPDATE power_grids SET damaged=0,updated_ts=?
                   WHERE owner_type=? AND owner_id=?""",
                (now_ts(), owner_type, owner_id))
            add_region_noise(ch, 4, f"{display_name(ch)}重新接通了受损电网。", "repair")
            flash("电网已经恢复供电")
    return redirect(url_for("dashboard"))

@app.route("/action/build_shelter", methods=["POST"])
@login_required
@need_character
def action_build_shelter(ch):
    name = request.form.get("name", "").strip() or f"{ch['name']}的庇护所"
    if ch["level"] < SHELTER_LEVEL_REQUIRED:
        flash(f"需要个人等级达到{SHELTER_LEVEL_REQUIRED}级才能建庇护所")
        return redirect(url_for("dashboard"))
    buildable, reason = tile_is_buildable(ch["tile_x"], ch["tile_y"])
    if not buildable:
        flash(reason)
        return redirect(url_for("dashboard"))
    house = house_here_for(ch)
    local_ref = ("house_inventory", "house_id", house["id"]) if house else None
    if not _has_enough_with_local(ch, SHELTER_COST, local_ref):
        flash("材料不够(随身+房子仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in SHELTER_COST.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, SHELTER_COST, local_ref)
    cur = run("INSERT INTO shelters (name, tile_x, tile_y, tier, farm_ready_ts, created_ts) VALUES (?,?,?,1,?,?)",
               (name, ch["tile_x"], ch["tile_y"], now_ts(), now_ts()))
    add_region_noise(ch, 24, f"{display_name(ch)}建立了庇护所「{name}」。", "build")
    run("UPDATE world_tiles SET has_building=1 WHERE x=? AND y=?", (ch["tile_x"], ch["tile_y"]))
    run("UPDATE characters SET shelter_id=? WHERE id=?", (cur.lastrowid, ch["id"]))
    grant_xp(ch, 50)
    add_shelter_feed(cur.lastrowid, "chronicle", "系统", f"{display_name(ch)} 建立了这座庇护所。")
    announce(f"🏘️ {display_name(ch)} 在坐标({ch['tile_x']},{ch['tile_y']})建立了庇护所「{name}」。")
    flash(f"庇护所「{name}」建好了,你是第一个成员")
    return redirect(url_for("dashboard"))

@app.route("/action/upgrade_house_to_shelter", methods=["POST"])
@login_required
@need_character
def action_upgrade_house_to_shelter(ch):
    """把自己的房子原地改建成庇护所——tile_is_buildable会因为房子本身占着地块而拒绝
    正常建庇护所的流程，所以这条路必须是独立的：直接复用房子的地块，房子仓库剩下的
    物资原样搬进新庇护所仓库，不浪费；房子本身连同电网/仓库/维修记录一并清空。"""
    name = request.form.get("name", "").strip() or f"{ch['name']}的庇护所"
    house = house_here_for(ch)
    if not house:
        flash("这里没有你的房子,不能原地改建")
        return redirect(url_for("dashboard"))
    if ch["level"] < SHELTER_LEVEL_REQUIRED:
        flash(f"需要个人等级达到{SHELTER_LEVEL_REQUIRED}级才能建庇护所")
        return redirect(url_for("dashboard"))
    local_ref = ("house_inventory", "house_id", house["id"])
    if not _has_enough_with_local(ch, SHELTER_COST, local_ref):
        flash("材料不够(随身+房子仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in SHELTER_COST.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, SHELTER_COST, local_ref)
    carried_crates = house["storage_crates"]
    carried_workbench = house["has_workbench"]
    cur = run("""INSERT INTO shelters (name, tile_x, tile_y, tier, farm_ready_ts, storage_crates, has_workbench, created_ts)
                 VALUES (?,?,?,1,?,?,?,?)""",
               (name, ch["tile_x"], ch["tile_y"], now_ts(), carried_crates, carried_workbench, now_ts()))
    shelter_id = cur.lastrowid
    for item in q("SELECT * FROM house_inventory WHERE house_id=?", (house["id"],)):
        if item["amount"] > 0:
            inv_add("shelter_inventory", "shelter_id", shelter_id, item["resource_key"], item["amount"])
    run("""UPDATE resource_extractors SET owner_type='shelter', owner_id=?
           WHERE owner_type='house' AND owner_id=?""", (shelter_id, house["id"]))
    run("DELETE FROM power_logs WHERE owner_type='house' AND owner_id=?", (house["id"],))
    run("DELETE FROM power_grids WHERE owner_type='house' AND owner_id=?", (house["id"],))
    run("DELETE FROM house_raid_logs WHERE house_id=?", (house["id"],))
    run("DELETE FROM house_inventory WHERE house_id=?", (house["id"],))
    run("DELETE FROM houses WHERE id=?", (house["id"],))
    run("UPDATE characters SET shelter_id=? WHERE id=?", (shelter_id, ch["id"]))
    add_region_noise(ch, 24, f"{display_name(ch)}把房子改建成了庇护所「{name}」。", "build")
    grant_xp(ch, 50)
    add_shelter_feed(shelter_id, "chronicle", "系统", f"{display_name(ch)} 把个人房子改建成了这座庇护所。")
    announce(f"🏘️ {display_name(ch)} 在坐标({ch['tile_x']},{ch['tile_y']})把房子改建成了庇护所「{name}」。")
    crate_note = f"；房子原有的{carried_crates}个储物箱也带过来了,庇护所仓库容量+{carried_crates * STORAGE_CRATE_BONUS}" if carried_crates else ""
    workbench_note = "；基础工作台也带过来了" if carried_workbench else ""
    flash(f"房子改建成庇护所「{name}」了,你是第一个成员;房子仓库剩下的物资已经原样搬进庇护所仓库{crate_note}{workbench_note}")
    return redirect(url_for("dashboard"))

# ── 路由:工作台 ───────────────────────────────────────────────────────────

@app.route("/action/build_workbench", methods=["POST"])
@login_required
@need_character
def action_build_workbench(ch):
    house = q("SELECT * FROM houses WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0",
              (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    shelter = q("SELECT * FROM shelters WHERE tile_x=? AND tile_y=? AND abandoned=0",
                (ch["tile_x"], ch["tile_y"]), one=True)
    kind = request.form.get("kind")  # basic / advanced
    if kind == "basic":
        # 房子和自己所属的庇护所都能装基础工作台——不然只建了庇护所、没建过房子的人
        # 永远没有基础工作台可用，图纸/修理全部卡死，只能先啃高级工作台的科研点门槛。
        my_shelter_here = shelter if (shelter and ch["shelter_id"] == shelter["id"]) else None
        if not house and not my_shelter_here:
            flash("要在自己的房子或所属庇护所地块才能建基础工作台")
        elif (house and house["has_workbench"]) or (my_shelter_here and my_shelter_here["has_workbench"]):
            flash("这里已经有基础工作台了")
        else:
            target_kind = "house" if house else "shelter"
            target_row = house if house else my_shelter_here
            local_ref = (f"{target_kind}_inventory", f"{target_kind}_id", target_row["id"])
            if not _has_enough_with_local(ch, BASIC_WORKBENCH_COST, local_ref):
                flash("材料不够(随身+当前仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in BASIC_WORKBENCH_COST.items()))
            else:
                _deduct_with_local(ch, BASIC_WORKBENCH_COST, local_ref)
                run(f"UPDATE {target_kind}s SET has_workbench=1 WHERE id=?", (target_row["id"],))
                add_region_noise(ch, 6, f"{display_name(ch)}安装了基础工作台。", "build")
                flash("基础工作台建好了")
    else:
        if not shelter or ch["shelter_id"] != shelter["id"]:
            flash("要在自己所属的庇护所地块才能建高级工作台")
        elif shelter["has_advanced_workbench"]:
            flash("这个庇护所已经有高级工作台了")
        elif shelter["research_points"] < ADVANCED_WORKBENCH_COST["research_points"]:
            flash(f"科研点数不够,需要{ADVANCED_WORKBENCH_COST['research_points']}点(打赢丧尸会给所属庇护所+1科研点数)")
        elif not _has_enough_with_local(ch, {k: v for k, v in ADVANCED_WORKBENCH_COST.items() if k != "research_points"},
                                        ("shelter_inventory", "shelter_id", shelter["id"])):
            flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in ADVANCED_WORKBENCH_COST.items() if k != "research_points"))
        else:
            _deduct_with_local(ch, {k: v for k, v in ADVANCED_WORKBENCH_COST.items() if k != "research_points"},
                               ("shelter_inventory", "shelter_id", shelter["id"]))
            run("UPDATE shelters SET has_advanced_workbench=1, research_points=research_points-? WHERE id=?",
                (ADVANCED_WORKBENCH_COST["research_points"], shelter["id"]))
            add_region_noise(ch, 10, f"{display_name(ch)}安装了高级工作台。", "build")
            flash("高级工作台建好了")
    return redirect(url_for("dashboard"))

@app.route("/action/build_storage_crate", methods=["POST"])
@login_required
@need_character
def action_build_storage_crate(ch):
    house = house_here_for(ch)
    if not house:
        flash("这里没有你的房子,不能造储物箱")
    elif house["storage_crates"] >= STORAGE_CRATE_CAP:
        flash(f"这栋房子的储物箱已经到上限{STORAGE_CRATE_CAP}个了")
    elif not _has_enough_with_local(ch, STORAGE_CRATE_COST, ("house_inventory", "house_id", house["id"])):
        flash("材料不够(随身+房子仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in STORAGE_CRATE_COST.items()))
    else:
        _deduct_with_local(ch, STORAGE_CRATE_COST, ("house_inventory", "house_id", house["id"]))
        run("UPDATE houses SET storage_crates=storage_crates+1 WHERE id=?", (house["id"],))
        new_cap = HOUSE_INVENTORY_CAP + (house["storage_crates"] + 1) * STORAGE_CRATE_BONUS
        flash(f"造了个储物箱,不需要工作台。房子仓库容量+{STORAGE_CRATE_BONUS},现在是{new_cap}")
    return redirect(url_for("dashboard"))

@app.route("/action/build_shelter_storage_crate", methods=["POST"])
@login_required
@need_character
def action_build_shelter_storage_crate(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能造储物箱")
    elif shelter["storage_crates"] >= SHELTER_STORAGE_CRATE_CAP:
        flash(f"这个庇护所的储物箱已经到上限{SHELTER_STORAGE_CRATE_CAP}个了")
    elif not _has_enough_with_local(ch, STORAGE_CRATE_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in STORAGE_CRATE_COST.items()))
    else:
        _deduct_with_local(ch, STORAGE_CRATE_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET storage_crates=storage_crates+1 WHERE id=?", (shelter["id"],))
        updated_shelter = q("SELECT * FROM shelters WHERE id=?", (shelter["id"],), one=True)
        flash(f"造了个储物箱,不需要工作台。庇护所仓库容量+{STORAGE_CRATE_BONUS},现在是{shelter_inventory_cap_for(updated_shelter)}")
    return redirect(url_for("dashboard"))

@app.route("/action/build_mega_warehouse", methods=["POST"])
@login_required
@need_character
def action_build_mega_warehouse(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能建超大仓库")
    elif shelter["has_mega_warehouse"]:
        flash("这个庇护所已经建过超大仓库了,只能建一次")
    elif shelter["tier"] < MEGA_WAREHOUSE_LEVEL_REQUIRED:
        flash(f"庇护所要先升到Lv{MEGA_WAREHOUSE_LEVEL_REQUIRED}才能建超大仓库")
    elif not _has_enough_with_local(ch, MEGA_WAREHOUSE_COST, ("shelter_inventory", "shelter_id", shelter["id"])):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in MEGA_WAREHOUSE_COST.items()))
    else:
        _deduct_with_local(ch, MEGA_WAREHOUSE_COST, ("shelter_inventory", "shelter_id", shelter["id"]))
        run("UPDATE shelters SET has_mega_warehouse=1 WHERE id=?", (shelter["id"],))
        updated_shelter = q("SELECT * FROM shelters WHERE id=?", (shelter["id"],), one=True)
        flash(f"超大仓库建好了,一次性+{MEGA_WAREHOUSE_BONUS}容量,现在是{shelter_inventory_cap_for(updated_shelter)}")
    return redirect(url_for("dashboard"))

@app.route("/action/build_extractor", methods=["POST"])
@login_required
@need_character
def action_build_extractor(ch):
    kind = request.form.get("kind")
    info = EXTRACTOR_TYPES.get(kind)
    shelter = _my_shelter_here(ch)
    if not info:
        flash("没有这种采集机")
        return redirect(url_for("dashboard"))
    if not shelter:
        flash("要在自己所属的庇护所地块才能装被动采集机(只有庇护所能自动采集,普通采集始终手动)")
        return redirect(url_for("dashboard"))
    if q("""SELECT 1 FROM resource_extractors WHERE owner_type='shelter' AND owner_id=? AND kind=?""",
         (shelter["id"], kind), one=True):
        flash(f"这个庇护所已经有{info['name']}了")
        return redirect(url_for("dashboard"))
    if ch["level"] < info["level_required"]:
        flash(f"需要个人等级达到{info['level_required']}级才能装{info['name']}")
        return redirect(url_for("dashboard"))
    if shelter["tier"] < info.get("shelter_tier_required", 0):
        flash(f"庇护所要先升到Lv{info['shelter_tier_required']}才能装{info['name']}")
        return redirect(url_for("dashboard"))
    cost = EXTRACTOR_LEVELS[kind][1]["cost"]
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, cost, local_ref):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost, local_ref)
    run("""INSERT INTO resource_extractors (owner_type,owner_id,kind,level,ready_ts)
           VALUES ('shelter',?,?,1,?)""", (shelter["id"], kind, now_ts() + EXTRACTOR_INTERVAL_SECONDS))
    yield_amt = EXTRACTOR_LEVELS[kind][1]["yield_per_hour"]
    if info["resource_key"] == "research_points":
        flash(f"{info['name']}装好了,每小时自动产出{yield_amt}点科研点(直接加进庇护所,没有容量上限)")
    else:
        flash(f"{info['name']}装好了,每小时自动产出{yield_amt}份{RESOURCES[info['resource_key']][0]}到庇护所仓库(超过仓库容量的部分会溢出损失)")
    return redirect(url_for("dashboard"))

@app.route("/action/upgrade_extractor", methods=["POST"])
@login_required
@need_character
def action_upgrade_extractor(ch):
    kind = request.form.get("kind")
    info = EXTRACTOR_TYPES.get(kind)
    shelter = _my_shelter_here(ch)
    if not info:
        flash("没有这种采集机")
        return redirect(url_for("dashboard"))
    if not shelter:
        flash("要在自己所属的庇护所地块才能升级采集机")
        return redirect(url_for("dashboard"))
    row = q("""SELECT * FROM resource_extractors WHERE owner_type='shelter' AND owner_id=? AND kind=?""",
            (shelter["id"], kind), one=True)
    if not row:
        flash(f"这个庇护所还没有{info['name']}")
        return redirect(url_for("dashboard"))
    next_level = row["level"] + 1
    if next_level > EXTRACTOR_LEVEL_CAP:
        flash(f"{info['name']}已经是最高等级了")
        return redirect(url_for("dashboard"))
    cost = EXTRACTOR_LEVELS[kind][next_level]["cost"]
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, cost, local_ref):
        flash("升级材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost, local_ref)
    run("""UPDATE resource_extractors SET level=? WHERE owner_type='shelter' AND owner_id=? AND kind=?""",
        (next_level, shelter["id"], kind))
    yield_amt = EXTRACTOR_LEVELS[kind][next_level]["yield_per_hour"]
    unit = "点科研点" if info["resource_key"] == "research_points" else "份"
    flash(f"{info['name']}升到Lv{next_level}了,每小时产出提升到{yield_amt}{unit}")
    return redirect(url_for("dashboard"))

@app.route("/action/build_repeller", methods=["POST"])
@login_required
@need_character
def action_build_repeller(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能装驱赶器")
        return redirect(url_for("dashboard"))
    if shelter["repeller_level"] > 0:
        flash("这个庇护所已经有驱赶器了,只能升级")
        return redirect(url_for("dashboard"))
    if shelter["tier"] < REPELLER_LEVEL_REQUIRED:
        flash(f"庇护所要先升到Lv{REPELLER_LEVEL_REQUIRED}才能装驱赶器")
        return redirect(url_for("dashboard"))
    cost = REPELLER_LEVELS[1]["cost"]
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, cost, local_ref):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost, local_ref)
    run("UPDATE shelters SET repeller_level=1 WHERE id=?", (shelter["id"],))
    info = REPELLER_LEVELS[1]
    flash(f"驱赶器装好了,这片区域的噪声/长期威胁上限压到{info['noise_cap']}/{info['threat_cap']},会慢慢降下来")
    return redirect(url_for("dashboard"))

@app.route("/action/upgrade_repeller", methods=["POST"])
@login_required
@need_character
def action_upgrade_repeller(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能升级驱赶器")
        return redirect(url_for("dashboard"))
    if shelter["repeller_level"] <= 0:
        flash("这个庇护所还没有驱赶器")
        return redirect(url_for("dashboard"))
    next_level = shelter["repeller_level"] + 1
    if next_level > REPELLER_LEVEL_CAP:
        flash("驱赶器已经是最高等级了")
        return redirect(url_for("dashboard"))
    cost = REPELLER_LEVELS[next_level]["cost"]
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, cost, local_ref):
        flash("升级材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost, local_ref)
    run("UPDATE shelters SET repeller_level=? WHERE id=?", (next_level, shelter["id"]))
    info = REPELLER_LEVELS[next_level]
    flash(f"驱赶器升到Lv{next_level}了,覆盖范围扩大到周边{info['radius']}圈区域,"
          f"上限压到{info['noise_cap']}/{info['threat_cap']}")
    return redirect(url_for("dashboard"))

@app.route("/action/build_vehicle", methods=["POST"])
@login_required
@need_character
def action_build_vehicle(ch):
    key = request.form.get("vehicle_key")
    info = VEHICLES.get(key)
    if not info:
        flash("没有这种交通工具")
        return redirect(url_for("dashboard"))
    if ch["equipped_vehicle"] == key:
        flash(f"已经有一辆{info['name']}了")
        return redirect(url_for("dashboard"))
    if ch["level"] < info["level"]:
        flash(f"需要个人等级达到{info['level']}级才能造{info['name']}")
        return redirect(url_for("dashboard"))
    if not _workbench_available(ch, info["workbench"]):
        need = "个人房子或所属庇护所的基础工作台" if info["workbench"] == "basic" else "所属庇护所的高级工作台"
        flash(f"这里没有{need},不能造{info['name']}")
        return redirect(url_for("dashboard"))
    _, _, local_ref = _workbench_local_ref(ch, info["workbench"])
    if not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("材料不够(随身+当前仓库合计):需要 " + "、".join(f"{ITEM_NAMES.get(k,k)}{v}" for k, v in info["cost"].items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, info["cost"], local_ref)
    run("UPDATE characters SET equipped_vehicle=? WHERE id=?", (key, ch["id"]))
    grant_xp(ch, 10)
    flash(f"造好了{info['name']}并直接骑上——移动一次最多跳{info['max_tiles']}格(自己选1~{info['max_tiles']}格),"
          f"体力只要{info['stamina_cost']},冷却{info['cooldown_seconds']}秒")
    return redirect(url_for("dashboard"))

# ── 路由:图纸/装备制作(二节 + 八.3 + 十六.1) ───────────────────────────────

def _workbench_available(ch, workbench_kind):
    if workbench_kind == "basic":
        house = house_here_for(ch)
        if house and house["has_workbench"]:
            return True
        shelter = _my_shelter_here(ch)
        return bool(shelter and shelter["has_workbench"])
    shelter = q("SELECT * FROM shelters WHERE tile_x=? AND tile_y=? AND abandoned=0",
                (ch["tile_x"], ch["tile_y"]), one=True)
    return bool(shelter and shelter["has_advanced_workbench"] and ch["shelter_id"] == shelter["id"])

def _workbench_local_ref(ch, workbench_kind):
    """返回(owner_type, row, local_ref)，用于制作/修理时算材料够不够、扣哪个仓库、接哪个电网。
    basic工作台优先房子；房子不在但站在自己所属、也有基础工作台的庇护所里(房子改建过来的)一样算。"""
    if workbench_kind == "advanced":
        shelter = _my_shelter_here(ch)
        return ("shelter", shelter, ("shelter_inventory", "shelter_id", shelter["id"])) if shelter else (None, None, None)
    house = house_here_for(ch)
    if house:
        return "house", house, ("house_inventory", "house_id", house["id"])
    shelter = _my_shelter_here(ch)
    if shelter and shelter["has_workbench"]:
        return "shelter", shelter, ("shelter_inventory", "shelter_id", shelter["id"])
    return None, None, None

# ── 路由:关系、婚姻、孩子与传承 ────────────────────────────────────────────

@app.route("/family")
@login_required
@need_character
def family_view(ch):
    spouse = spouse_for(ch["id"])
    pending = q("""SELECT f.*, a.name AS from_name, b.name AS to_name
                   FROM family_proposals f
                   JOIN characters a ON a.id=f.from_char
                   JOIN characters b ON b.id=f.to_char
                   WHERE f.status='pending' AND (f.from_char=? OR f.to_char=?)
                   ORDER BY f.id DESC""", (ch["id"], ch["id"]))
    players = q("""SELECT c.*, p.nickname FROM characters c
                   LEFT JOIN character_profiles p ON p.character_id=c.id
                   WHERE c.status='alive' AND c.id<>? ORDER BY c.name""", (ch["id"],))
    bonds = {}
    for player in players:
        bonds[player["id"]] = bond_for(ch["id"], player["id"])
    children = q("""SELECT DISTINCT c.* FROM children c
                    LEFT JOIN child_guardians g ON g.child_id=c.id AND g.status='accepted'
                    WHERE c.parent_a=? OR c.parent_b=? OR g.guardian_character_id=?
                    ORDER BY c.born_ts""", (ch["id"], ch["id"], ch["id"]))
    child_cards = []
    for child in children:
        chosen_growth = {r["milestone"]: r for r in q(
            "SELECT * FROM child_growth_choices WHERE child_id=?", (child["id"],))}
        child_cards.append({
            "row": child, "age": child_age_days(child), "stage": child_stage(child),
            "is_parent": child["parent_a"] == ch["id"] or child["parent_b"] == ch["id"],
            "inventory": q("SELECT * FROM child_inventory WHERE child_id=? AND amount>0", (child["id"],)),
            "logs": q("""SELECT * FROM child_exploration_logs WHERE child_id=?
                         ORDER BY id DESC LIMIT 6""", (child["id"],)),
            "requests": q("""SELECT * FROM child_help_requests WHERE child_id=? AND status='open'
                              ORDER BY id DESC""", (child["id"],)),
            "growth": chosen_growth,
        })
    inv_map = {r["resource_key"]: r["amount"] for r in char_inv_list(ch["id"])}
    close_relations = q("""SELECT r.*,a.name AS a_name,b.name AS b_name
                           FROM close_relationships r JOIN characters a ON a.id=r.char_a
                           JOIN characters b ON b.id=r.char_b
                           WHERE r.char_a=? OR r.char_b=?""", (ch["id"], ch["id"]))
    sworn_ids = set()
    for rel in close_relations:
        if rel["role"] == "sworn_family" and rel["status"] == "accepted":
            sworn_ids.add(rel["char_b"] if rel["char_a"] == ch["id"] else rel["char_a"])
    guardians = q("""SELECT g.*,c.name AS child_name,p.name AS guardian_name
                     FROM child_guardians g JOIN children c ON c.id=g.child_id
                     JOIN characters p ON p.id=g.guardian_character_id
                     WHERE c.parent_a=? OR c.parent_b=?""", (ch["id"], ch["id"]))
    companion = companion_for(ch["id"])
    companion_distance = (max(abs(ch["tile_x"] - companion["tile_x"]),
                              abs(ch["tile_y"] - companion["tile_y"]))
                          if companion else None)
    companion_pending = q("""SELECT b.*, a.name AS a_name, c2.name AS b_name
                             FROM companion_bonds b JOIN characters a ON a.id=b.char_a
                             JOIN characters c2 ON c2.id=b.char_b
                             WHERE b.status='pending' AND (b.char_a=? OR b.char_b=?)""",
                          (ch["id"], ch["id"]))
    return render_template("family.html", ch=ch, spouse=spouse, pending=pending,
                           players=players, bonds=bonds, children=child_cards,
                           inv_map=inv_map, item_names=ITEM_NAMES, ring_recipes=RING_RECIPES,
                           affinity_required=MARRIAGE_AFFINITY_REQUIRED,
                           max_children=MAX_CHILDREN_PER_COUPLE,
                           growth_events=CHILD_GROWTH_EVENTS,
                           close_relations=close_relations, sworn_ids=sworn_ids,
                           guardians=guardians, companion=companion,
                           companion_distance=companion_distance,
                           companion_pending=companion_pending,
                           companion_flee_bonus=COMPANION_FLEE_BONUS)

@app.route("/family/ring/craft", methods=["POST"])
@login_required
@need_character
def family_craft_ring(ch):
    ring_key = request.form.get("ring_key")
    recipe = RING_RECIPES.get(ring_key)
    if not recipe:
        flash("没有这种戒指")
    elif not _workbench_available(ch, recipe["workbench"]):
        flash("需要在对应的工作台旁制作戒指")
    else:
        _, _, ring_local_ref = _workbench_local_ref(ch, recipe["workbench"])
        if not _has_enough_with_local(ch, recipe["cost"], ring_local_ref):
            flash("戒指材料不足(随身+当前仓库合计)")
            return redirect(url_for("family_view"))
        _deduct_with_local(ch, recipe["cost"], ring_local_ref)
        inv_add("character_inventory", "character_id", ch["id"], ring_key, 1)
        record_daily_progress(ch["id"], "craft", 1)
        record_long_progress(ch["id"], "craft", 1)
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 3)
        flash(f"你亲手做成了{recipe['name']}。它现在可以被用于求婚。")
    return redirect(url_for("family_view"))

@app.route("/family/bond/<int:target_id>", methods=["POST"])
@login_required
@need_character
def family_bond_action(ch, target_id):
    target = q("SELECT * FROM characters WHERE id=? AND status='alive'", (target_id,), one=True)
    kind = request.form.get("kind")
    gains = {"talk": 5, "meal": 10, "supplies": 8}
    costs = {"meal": "cooked_food", "supplies": "emergency_food"}
    if not target or target["id"] == ch["id"] or kind not in gains:
        flash("这次互动无法完成")
        return redirect(url_for("family_view"))
    age_day = survivor_day(ch)
    if q("""SELECT 1 FROM bond_interactions WHERE from_char=? AND to_char=? AND survivor_day=?""",
         (ch["id"], target_id, age_day), one=True):
        flash("今天已经主动和这名玩家相处过了，明天再聊吧")
        return redirect(url_for("family_view"))
    cost_key = costs.get(kind)
    if cost_key:
        have = q("""SELECT amount FROM character_inventory
                    WHERE character_id=? AND resource_key=?""", (ch["id"], cost_key), one=True)
        if not have or have["amount"] < 1:
            flash(f"需要1份{ITEM_NAMES[cost_key]}")
            return redirect(url_for("family_view"))
        inv_add("character_inventory", "character_id", ch["id"], cost_key, -1)
    run("""INSERT INTO bond_interactions(from_char,to_char,survivor_day,kind,created_ts)
           VALUES(?,?,?,?,?)""", (ch["id"], target_id, age_day, kind, now_ts()))
    add_bond_affinity(ch["id"], target_id, gains[kind])
    record_long_progress(ch["id"], "connection", 1)
    action_name = {"talk": "无线电谈心", "meal": "分享热饭", "supplies": "赠送补给"}[kind]
    flash(f"你和{display_name(target)}完成了「{action_name}」，羁绊+{gains[kind]}。")
    return redirect(url_for("family_view"))

@app.route("/family/propose/<int:target_id>", methods=["POST"])
@login_required
@need_character
def family_propose(ch, target_id):
    target = q("SELECT * FROM characters WHERE id=? AND status='alive'", (target_id,), one=True)
    ring_key = request.form.get("ring_key")
    bond = bond_for(ch["id"], target_id) if target else None
    ring = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key=?""", (ch["id"], ring_key), one=True)
    if not target or target["id"] == ch["id"]:
        flash("求婚对象已经不在了")
    elif spouse_for(ch["id"]) or spouse_for(target_id):
        flash("你们其中一方已经有伴侣")
    elif not bond or bond["affinity"] < MARRIAGE_AFFINITY_REQUIRED:
        flash(f"羁绊需要达到{MARRIAGE_AFFINITY_REQUIRED}才能求婚")
    elif ring_key not in RING_RECIPES or not ring or ring["amount"] < 1:
        flash("需要一枚亲手准备的戒指")
    elif q("""SELECT 1 FROM family_proposals WHERE proposal_type='marriage'
              AND status='pending' AND (from_char=? OR to_char=? OR from_char=? OR to_char=?)""",
           (ch["id"], ch["id"], target_id, target_id), one=True):
        flash("其中一方已有尚未回应的求婚")
    else:
        inv_add("character_inventory", "character_id", ch["id"], ring_key, -1)
        run("""INSERT INTO family_proposals
               (proposal_type,from_char,to_char,ring_key,created_ts)
               VALUES('marriage',?,?,?,?)""", (ch["id"], target_id, ring_key, now_ts()))
        flash(f"你把{ITEM_NAMES[ring_key]}交给了{display_name(target)}，等待对方回应。")
    return redirect(url_for("family_view"))

@app.route("/family/child/request", methods=["POST"])
@login_required
@need_character
def family_child_request(ch):
    spouse = spouse_for(ch["id"])
    child_name = " ".join((request.form.get("child_name") or "").strip().split())[:16]
    if not spouse or spouse["status"] != "alive":
        flash("只有双方都存活的伴侣才能共同决定迎接孩子")
    elif not child_name:
        flash("请先给孩子取一个名字")
    elif q("""SELECT COUNT(*) AS c FROM children
              WHERE (parent_a=? AND parent_b=?) OR (parent_a=? AND parent_b=?)""",
           (ch["id"], spouse["id"], spouse["id"], ch["id"]), one=True)["c"] >= MAX_CHILDREN_PER_COUPLE:
        flash(f"每个家庭最多养育{MAX_CHILDREN_PER_COUPLE}个孩子")
    elif q("""SELECT 1 FROM family_proposals WHERE proposal_type='child'
              AND status='pending' AND ((from_char=? AND to_char=?) OR (from_char=? AND to_char=?))""",
           (ch["id"], spouse["id"], spouse["id"], ch["id"]), one=True):
        flash("你们已经有一个待确认的孩子计划")
    else:
        run("""INSERT INTO family_proposals
               (proposal_type,from_char,to_char,child_name,created_ts)
               VALUES('child',?,?,?,?)""", (ch["id"], spouse["id"], child_name, now_ts()))
        flash(f"已向{display_name(spouse)}发出共同养育「{child_name}」的确认。")
    return redirect(url_for("family_view"))

@app.route("/family/proposal/<int:proposal_id>/<decision>", methods=["POST"])
@login_required
@need_character
def family_proposal_decide(ch, proposal_id, decision):
    proposal = q("SELECT * FROM family_proposals WHERE id=? AND status='pending'",
                 (proposal_id,), one=True)
    if not proposal or proposal["to_char"] != ch["id"] or decision not in ("accept", "reject"):
        flash("这份请求已经失效")
        return redirect(url_for("family_view"))
    sender = q("SELECT * FROM characters WHERE id=? AND status='alive'",
               (proposal["from_char"],), one=True)
    if decision == "reject":
        if proposal["proposal_type"] == "marriage" and proposal["ring_key"]:
            inv_add("character_inventory", "character_id", proposal["from_char"],
                    proposal["ring_key"], 1)
        run("UPDATE family_proposals SET status='rejected',resolved_ts=? WHERE id=?",
            (now_ts(), proposal_id))
        flash("你拒绝了这份请求；戒指已经退还。")
        return redirect(url_for("family_view"))
    if not sender:
        flash("对方已经无法回应了")
        return redirect(url_for("family_view"))
    if proposal["proposal_type"] == "marriage":
        if spouse_for(ch["id"]) or spouse_for(sender["id"]):
            flash("其中一方已经有伴侣，这份求婚失效")
            return redirect(url_for("family_view"))
        a, b = bond_pair(ch["id"], sender["id"])
        run("""INSERT INTO player_bonds(char_a,char_b,affinity,married,married_ts)
               VALUES(?,?,?,1,?)
               ON CONFLICT(char_a,char_b) DO UPDATE SET married=1,married_ts=?,separated_ts=0""",
            (a, b, MARRIAGE_AFFINITY_REQUIRED, now_ts(), now_ts()))
        run("UPDATE family_proposals SET status='accepted',resolved_ts=? WHERE id=?",
            (now_ts(), proposal_id))
        announce(f"💍 {display_name(ch)}与{display_name(sender)}在废土中成为了伴侣。")
        album_add(ch["id"], "marriage", "废土婚礼",
                  f"{display_name(ch)}与{display_name(sender)}交换戒指，在仍有杂音的频道里许下承诺。",
                  sender["id"])
        album_add(sender["id"], "marriage", "废土婚礼",
                  f"{display_name(sender)}与{display_name(ch)}交换戒指，在仍有杂音的频道里许下承诺。",
                  ch["id"])
        flash("你接受了求婚。戒指与这一刻已经写进家族记录。")
    else:
        if not spouse_for(ch["id"]) or spouse_for(ch["id"])["id"] != sender["id"]:
            flash("你们已不再是伴侣，这份计划失效")
            return redirect(url_for("family_view"))
        pa, pb = bond_pair(ch["id"], sender["id"])
        profiles = [profile_for(pa), profile_for(pb)]
        trait_pool = [t for p in profiles if p for t in (p["trait_a"], p["trait_b"])]
        traits = random.sample(trait_pool, min(2, len(set(trait_pool)))) if trait_pool else ["optimist", "careful"]
        while len(traits) < 2:
            candidate = random.choice(list(CHARACTER_TRAITS))
            if candidate not in traits:
                traits.append(candidate)
        parents = [q("SELECT * FROM characters WHERE id=?", (pa,), one=True),
                   q("SELECT * FROM characters WHERE id=?", (pb,), one=True)]
        stats = [max(0, min(20, round((parents[0][col] + parents[1][col]) / 2) + random.randint(-1, 2)))
                 for col in ("stat_str", "stat_spd", "stat_int", "stat_luck")]
        ts = now_ts()
        child_cur = run("""INSERT INTO children
               (parent_a,parent_b,name,born_ts,stat_str,stat_spd,stat_int,stat_luck,
                trait_a,trait_b,tile_x,tile_y,created_ts)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pa, pb, proposal["child_name"], ts, *stats, traits[0], traits[1],
             ch["tile_x"], ch["tile_y"], ts))
        run("UPDATE family_proposals SET status='accepted',resolved_ts=? WHERE id=?",
            (ts, proposal_id))
        announce(f"🕯️ {display_name(ch)}与{display_name(sender)}的家庭迎来了{proposal['child_name']}。")
        for parent, other in ((ch, sender), (sender, ch)):
            album_add(parent["id"], "birth", "新生命",
                      f"{proposal['child_name']}出生了。{display_name(parent)}与{display_name(other)}第一次在末日里谈起未来。",
                      other["id"], child_cur.lastrowid)
        flash(f"{proposal['child_name']}来到了这个世界。6岁前需要父母每天照顾。")
    return redirect(url_for("family_view"))

@app.route("/family/child/<int:child_id>/care", methods=["POST"])
@login_required
@need_character
def family_child_care(ch, child_id):
    child = q("SELECT * FROM children WHERE id=? AND status='alive'", (child_id,), one=True)
    can_care = bool(child and (child["parent_a"] == ch["id"] or child["parent_b"] == ch["id"] or
                    q("""SELECT 1 FROM child_guardians WHERE child_id=?
                         AND guardian_character_id=? AND status='accepted'""",
                      (child_id, ch["id"]), one=True)))
    kind = request.form.get("kind")
    age = child_age_days(child) if child else -1
    if not child or not can_care or kind not in ("feed", "story", "train", "medicine"):
        flash("无法完成这次照顾")
    elif q("""SELECT 1 FROM child_care_logs
              WHERE child_id=? AND parent_character_id=? AND survivor_day=?""",
           (child_id, ch["id"], age), one=True):
        flash("今天已经照顾过这个孩子了")
    else:
        costs = {
            "feed": {"raw_food": 1, "clean_water": 1},
            "medicine": {"bandage": 1},
        }
        cost = costs.get(kind, {})
        if cost and not _has_enough(ch, cost):
            flash("照顾所需物资不足：" + "、".join(f"{ITEM_NAMES[k]}x{v}" for k, v in cost.items()))
            return redirect(url_for("family_view"))
        if cost:
            _deduct(ch, cost)
        if kind == "feed":
            run("UPDATE children SET hp=MIN(100,hp+12),care_points=care_points+2 WHERE id=?", (child_id,))
        elif kind == "medicine":
            run("UPDATE children SET hp=MIN(100,hp+25),care_points=care_points+1 WHERE id=?", (child_id,))
        elif kind == "story":
            run("UPDATE children SET stat_int=MIN(20,stat_int+1),care_points=care_points+1 WHERE id=?", (child_id,))
        else:
            stat = random.choice(("stat_str", "stat_spd"))
            run(f"UPDATE children SET {stat}=MIN(20,{stat}+1),care_points=care_points+1 WHERE id=?", (child_id,))
        run("""INSERT INTO child_care_logs(child_id,parent_character_id,survivor_day,care_kind,created_ts)
               VALUES(?,?,?,?,?)""", (child_id, ch["id"], age, kind, now_ts()))
        run("""UPDATE child_help_requests SET status='resolved',resolved_ts=?
               WHERE child_id=? AND status='open'""", (now_ts(), child_id))
        record_long_progress(ch["id"], "connection", 1)
        flash(f"你照顾了{child['name']}。孩子记住的不是数值，而是有人回来。")
    return redirect(url_for("family_view"))

@app.route("/family/child/<int:child_id>/growth", methods=["POST"])
@login_required
@need_character
def family_child_growth(ch, child_id):
    child = q("""SELECT * FROM children WHERE id=? AND status='alive'
                 AND (parent_a=? OR parent_b=?)""", (child_id, ch["id"], ch["id"]), one=True)
    milestone = request.form.get("milestone", type=int)
    choice_key = request.form.get("choice_key")
    event = CHILD_GROWTH_EVENTS.get(milestone)
    if not child or not event or child_age_days(child) < milestone or choice_key not in event["choices"]:
        flash("这个成长选择还没有开放")
    elif q("""SELECT 1 FROM child_growth_choices WHERE child_id=? AND milestone=?""",
           (child_id, milestone), one=True):
        flash("这个成长节点已经留下选择，不能重写")
    else:
        label, story, stat_col = event["choices"][choice_key]
        run("""INSERT INTO child_growth_choices
               (child_id,milestone,choice_key,choice_label,story_text,chosen_by,chosen_ts)
               VALUES(?,?,?,?,?,?,?)""",
            (child_id, milestone, choice_key, label, story, ch["id"], now_ts()))
        run(f"UPDATE children SET {stat_col}=MIN(20,{stat_col}+2) WHERE id=?", (child_id,))
        album_add(ch["id"], "growth", event["title"],
                  f"{child['name']}在{milestone}岁时，家里选择「{label}」。{story}", child_id=child_id)
        flash(f"{child['name']}的成长选择已经记录：{label}")
    return redirect(url_for("family_view"))

@app.route("/family/relation/<int:target_id>/<role>", methods=["POST"])
@login_required
@need_character
def family_relation_request(ch, target_id, role):
    target = q("SELECT * FROM characters WHERE id=? AND status='alive'", (target_id,), one=True)
    role_names = {"best_friend": "挚友", "sworn_family": "义亲"}
    bond = bond_for(ch["id"], target_id) if target else None
    if not target or role not in role_names or target_id == ch["id"]:
        flash("无法建立这种关系")
    elif not bond or bond["affinity"] < 30:
        flash("需要羁绊达到30才能发出正式关系请求")
    elif close_relation(ch["id"], target_id, role):
        flash("这份关系请求已经存在")
    else:
        a, b = bond_pair(ch["id"], target_id)
        run("""INSERT INTO close_relationships
               (char_a,char_b,role,status,requested_by,created_ts)
               VALUES(?,?,?,'pending',?,?)""", (a, b, role, ch["id"], now_ts()))
        flash(f"已向{display_name(target)}发出成为{role_names[role]}的请求")
    return redirect(url_for("family_view"))

@app.route("/family/relation/<int:target_id>/<role>/<decision>", methods=["POST"])
@login_required
@need_character
def family_relation_decide(ch, target_id, role, decision):
    rel = close_relation(ch["id"], target_id, role)
    if not rel or rel["status"] != "pending" or rel["requested_by"] == ch["id"] or decision not in ("accept", "reject"):
        flash("这份关系请求已经失效")
    else:
        status = "accepted" if decision == "accept" else "rejected"
        run("""UPDATE close_relationships SET status=?,resolved_ts=?
               WHERE char_a=? AND char_b=? AND role=?""",
            (status, now_ts(), rel["char_a"], rel["char_b"], role))
        if status == "accepted":
            other = q("SELECT * FROM characters WHERE id=?", (target_id,), one=True)
            role_name = "挚友" if role == "best_friend" else "义亲"
            album_add(ch["id"], role, f"成为{role_name}",
                      f"{display_name(ch)}与{display_name(other)}决定以{role_name}相称。", target_id)
            album_add(target_id, role, f"成为{role_name}",
                      f"{display_name(other)}与{display_name(ch)}决定以{role_name}相称。", ch["id"])
        flash("关系回应已经记录")
    return redirect(url_for("family_view"))

@app.route("/family/guardian/<int:child_id>/<int:guardian_id>", methods=["POST"])
@login_required
@need_character
def family_guardian_request(ch, child_id, guardian_id):
    child = q("""SELECT * FROM children WHERE id=? AND status='alive'
                 AND (parent_a=? OR parent_b=?)""", (child_id, ch["id"], ch["id"]), one=True)
    guardian = q("SELECT * FROM characters WHERE id=? AND status='alive'", (guardian_id,), one=True)
    relation = close_relation(ch["id"], guardian_id, "sworn_family") if guardian else None
    if not child or not guardian or not relation or relation["status"] != "accepted":
        flash("只有已经确认的义亲才能被邀请为孩子监护人")
    else:
        run("""INSERT OR IGNORE INTO child_guardians
               (child_id,guardian_character_id,status,requested_by,created_ts)
               VALUES(?,?,'pending',?,?)""", (child_id, guardian_id, ch["id"], now_ts()))
        flash(f"已邀请{display_name(guardian)}成为{child['name']}的监护人")
    return redirect(url_for("family_view"))

@app.route("/family/guardian/<int:child_id>/<decision>", methods=["POST"])
@login_required
@need_character
def family_guardian_decide(ch, child_id, decision):
    row = q("""SELECT * FROM child_guardians WHERE child_id=? AND guardian_character_id=?
               AND status='pending'""", (child_id, ch["id"]), one=True)
    if not row or decision not in ("accept", "reject"):
        flash("监护请求已失效")
    else:
        run("""UPDATE child_guardians SET status=?,resolved_ts=?
               WHERE child_id=? AND guardian_character_id=?""",
            ("accepted" if decision == "accept" else "rejected", now_ts(), child_id, ch["id"]))
        flash("监护关系回应已经记录")
    return redirect(url_for("family_view"))

@app.route("/family/separate", methods=["POST"])
@login_required
@need_character
def family_separate(ch):
    bond = q("""SELECT * FROM player_bonds WHERE married=1 AND (char_a=? OR char_b=?)""",
             (ch["id"], ch["id"]), one=True)
    if bond:
        run("""UPDATE player_bonds SET married=0,separated_ts=?
               WHERE char_a=? AND char_b=?""", (now_ts(), bond["char_a"], bond["char_b"]))
        flash("伴侣关系已经结束；你们与孩子的亲子关系仍然保留。")
    return redirect(url_for("family_view"))

@app.route("/companion/request/<int:target_id>", methods=["POST"])
@login_required
@need_character
def companion_request(ch, target_id):
    target = q("SELECT * FROM characters WHERE id=? AND status='alive'", (target_id,), one=True)
    if not target or target_id == ch["id"]:
        flash("无法向对方发出结伴请求")
    elif companion_for(ch["id"]):
        flash("你已经有结伴对象了，先结束当前的结伴关系")
    elif companion_for(target_id):
        flash("对方已经有结伴对象了")
    else:
        row = companion_bond_row(ch["id"], target_id)
        if row and row["status"] == "pending":
            flash("你们之间已经有一份待回应的结伴请求")
        else:
            a, b = bond_pair(ch["id"], target_id)
            run("""INSERT INTO companion_bonds(char_a,char_b,status,requested_by,created_ts)
                   VALUES(?,?,'pending',?,?)
                   ON CONFLICT(char_a,char_b) DO UPDATE
                   SET status='pending',requested_by=?,created_ts=?,resolved_ts=0""",
                (a, b, ch["id"], now_ts(), ch["id"], now_ts()))
            flash(f"已向{display_name(target)}发出结伴请求，不需要庇护所也不需要羁绊值。")
    return redirect(url_for("family_view"))

@app.route("/companion/respond/<int:from_id>/<decision>", methods=["POST"])
@login_required
@need_character
def companion_respond(ch, from_id, decision):
    row = companion_bond_row(ch["id"], from_id)
    if not row or row["status"] != "pending" or row["requested_by"] == ch["id"] or decision not in ("accept", "reject"):
        flash("这份结伴请求已经失效")
        return redirect(url_for("family_view"))
    sender = q("SELECT * FROM characters WHERE id=? AND status='alive'", (from_id,), one=True)
    if decision == "reject" or not sender:
        run("UPDATE companion_bonds SET status='ended',resolved_ts=? WHERE char_a=? AND char_b=?",
            (now_ts(), row["char_a"], row["char_b"]))
        flash("已拒绝这份结伴请求")
        return redirect(url_for("family_view"))
    if companion_for(ch["id"]) or companion_for(from_id):
        run("UPDATE companion_bonds SET status='ended',resolved_ts=? WHERE char_a=? AND char_b=?",
            (now_ts(), row["char_a"], row["char_b"]))
        flash("其中一方已经有结伴对象了，这份请求已失效")
        return redirect(url_for("family_view"))
    run("UPDATE companion_bonds SET status='active',resolved_ts=? WHERE char_a=? AND char_b=?",
        (now_ts(), row["char_a"], row["char_b"]))
    flash(f"你和{display_name(sender)}结伴同行了——能在地图上看到彼此位置，遇袭时也更容易脱身。")
    return redirect(url_for("family_view"))

@app.route("/companion/end", methods=["POST"])
@login_required
@need_character
def companion_end(ch):
    partner = companion_for(ch["id"])
    if not partner:
        flash("你现在没有结伴对象")
    else:
        a, b = bond_pair(ch["id"], partner["id"])
        run("UPDATE companion_bonds SET status='ended',resolved_ts=? WHERE char_a=? AND char_b=?",
            (now_ts(), a, b))
        flash(f"已结束与{display_name(partner)}的结伴关系，随时可以再结伴。")
    return redirect(url_for("family_view"))

# ── 路由:个人生存技术 ─────────────────────────────────────────────────────

@app.route("/survival-tech")
@login_required
@need_character
def survival_tech_view(ch):
    ch = settle_stamina(ch)
    workshop = survival_workshop_for(ch["id"])
    inventory = char_inv_list(ch["id"])
    inv_map = {r["resource_key"]: r["amount"] for r in inventory}
    samples = q("""SELECT * FROM tested_water_samples WHERE character_id=? AND status='tested'
                   ORDER BY id DESC""", (ch["id"],))
    maintenance = q("SELECT * FROM weapon_maintenance WHERE character_id=?", (ch["id"],), one=True)
    all_caches = q("SELECT * FROM supply_caches ORDER BY id DESC")
    caches = [c for c in all_caches if can_access_cache(ch, c)]
    cache_cards = []
    for cache in caches:
        cache_cards.append({"row": cache,
                            "inventory": q("""SELECT * FROM supply_cache_inventory
                                             WHERE cache_id=? AND amount>0""", (cache["id"],)),
                            "here": cache["tile_x"] == ch["tile_x"] and cache["tile_y"] == ch["tile_y"]})
    ruin = ensure_ruin_site(ch)
    ruin_parts = q("SELECT * FROM ruin_compartments WHERE site_id=? ORDER BY part_key",
                   (ruin["id"],)) if ruin else []
    ruin_logs = q("""SELECT * FROM ruin_dismantle_logs WHERE site_id=?
                     ORDER BY id DESC LIMIT 8""", (ruin["id"],)) if ruin else []
    house_here = house_here_for(ch)
    return render_template("survival_tech.html", ch=ch, workshop=workshop,
                           inventory=inventory, inv_map=inv_map, samples=samples,
                           contamination=WATER_CONTAMINATION, stations=SURVIVAL_WORKSHOP_STATIONS,
                           maintenance=maintenance, caches=cache_cards, ruin=ruin,
                           ruin_parts=ruin_parts, ruin_defs=RUIN_PARTS, ruin_logs=ruin_logs,
                           item_names=ITEM_NAMES, house_here=bool(house_here),
                           stamina_costs=STAMINA_COSTS)

@app.route("/survival-tech/station/build", methods=["POST"])
@login_required
@need_character
def survival_tech_build(ch):
    key = request.form.get("station_key")
    info = SURVIVAL_WORKSHOP_STATIONS.get(key)
    cols = {"water_tester": "has_water_tester", "ammo_press": "has_ammo_press"}
    workshop = survival_workshop_for(ch["id"])
    house = q("""SELECT id FROM houses WHERE owner_user_id=? AND tile_x=? AND tile_y=?
                 AND abandoned=0""", (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
    local_ref = ("house_inventory", "house_id", house["id"]) if house else None
    if not info or key not in cols:
        flash("没有这种设备")
    elif not house:
        flash("需要回到自己的房屋地块安装设备")
    elif workshop[cols[key]]:
        flash("这台设备已经装好了")
    elif not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("安装材料不足(随身+房子仓库合计)")
    else:
        _deduct_with_local(ch, info["cost"], local_ref)
        run(f"UPDATE personal_survival_workshops SET {cols[key]}=1 WHERE character_id=?",
            (ch["id"],))
        flash(f"{info['name']}安装完成")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/water/test", methods=["POST"])
@login_required
@need_character
def survival_water_test(ch):
    workshop = survival_workshop_for(ch["id"])
    if not workshop["has_water_tester"]:
        flash("需要便携污染检测台")
    elif not _has_enough(ch, {"raw_water": 1}):
        flash("背包里没有可以检测的生水")
    else:
        _deduct(ch, {"raw_water": 1})
        dist = dist_from_origin(ch["tile_x"], ch["tile_y"])
        weights = [max(10, 28 - dist // 4), 46, 18 + min(12, dist // 5), 8 + min(18, dist // 4)]
        key = random.choices(["safe", "bio", "chemical", "radiation"], weights=weights, k=1)[0]
        run("""INSERT INTO tested_water_samples
               (character_id,contamination_key,source_x,source_y,tested_ts)
               VALUES(?,?,?,?,?)""", (ch["id"], key, ch["tile_x"], ch["tile_y"], now_ts()))
        run("""UPDATE personal_survival_workshops SET water_skill=water_skill+1
               WHERE character_id=?""", (ch["id"],))
        flash(f"检测完成：{WATER_CONTAMINATION[key]['name']}。现在可以选择对应处理方法。")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/water/<int:sample_id>/treat", methods=["POST"])
@login_required
@need_character
def survival_water_treat(ch, sample_id):
    sample = q("""SELECT * FROM tested_water_samples WHERE id=? AND character_id=?
                  AND status='tested'""", (sample_id, ch["id"]), one=True)
    if not sample:
        flash("这份水样已经处理或丢弃")
    else:
        info = WATER_CONTAMINATION[sample["contamination_key"]]
        if not _has_enough(ch, info["cost"]):
            flash("对应处理材料不足")
        else:
            _deduct(ch, info["cost"])
            inv_add("character_inventory", "character_id", ch["id"], "clean_water", 1)
            run("""UPDATE tested_water_samples SET status='treated',treated_ts=? WHERE id=?""",
                (now_ts(), sample_id))
            remember_location(ch["id"], sample["source_x"], sample["source_y"],
                              f"这里的水样检测为{info['name']}。")
            record_long_progress(ch["id"], "safe_water", 1)
            flash(f"完成「{info['treatment']}」，得到1份净水")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/water/<int:sample_id>/discard", methods=["POST"])
@login_required
@need_character
def survival_water_discard(ch, sample_id):
    run("""UPDATE tested_water_samples SET status='discarded',treated_ts=?
           WHERE id=? AND character_id=? AND status='tested'""",
        (now_ts(), sample_id, ch["id"]))
    flash("水样已经安全丢弃")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/ammo/reload", methods=["POST"])
@login_required
@need_character
def survival_ammo_reload(ch):
    workshop = survival_workshop_for(ch["id"])
    cost = {"spent_casing": 2, "gunpowder": 1, "metal": 1}
    if not workshop["has_ammo_press"]:
        flash("需要手动弹药复装机")
    elif not _has_enough(ch, cost):
        flash("复装需要回收弹壳x2、可用火药x1和金属x1")
    else:
        _deduct(ch, cost)
        amount = 4 + workshop["reload_skill"] // 5
        inv_add("character_inventory", "character_id", ch["id"], "ammo", amount)
        run("""UPDATE personal_survival_workshops SET reload_skill=reload_skill+1
               WHERE character_id=?""", (ch["id"],))
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 3)
        add_region_noise(ch, 7, f"{display_name(ch)}进行了一次弹药复装。", "production")
        flash(f"复装完成，获得弹药x{amount}；复装熟练度+1")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/weapon/clean", methods=["POST"])
@login_required
@need_character
def survival_weapon_clean(ch):
    if not ch["equipped_weapon"] or ch["equipped_weapon"] == "fist":
        flash("当前没有需要保养的武器")
    elif not _has_enough(ch, {"cloth": 1, "gun_oil": 1}):
        flash("需要布料x1和枪械保养油x1")
    else:
        _deduct(ch, {"cloth": 1, "gun_oil": 1})
        repair_gain = 25 if has_daily_plan(ch, "prepare") else 20
        run("UPDATE characters SET weapon_durability=MIN(100,weapon_durability+?) WHERE id=?",
            (repair_gain, ch["id"]))
        run("""INSERT INTO weapon_maintenance(character_id,maintained_battles,clean_count,last_cleaned_ts)
               VALUES(?,3,1,?) ON CONFLICT(character_id) DO UPDATE SET
               maintained_battles=3,clean_count=clean_count+1,last_cleaned_ts=?""",
            (ch["id"], now_ts(), now_ts()))
        record_long_progress(ch["id"], "prepare", 1)
        add_region_noise(ch, 1, f"{display_name(ch)}保养了武器。", "production")
        flash(f"武器已经清洁上油，耐久+{repair_gain}，接下来3场战斗磨损降低")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/cache/create", methods=["POST"])
@login_required
@need_character
def survival_cache_create(ch):
    name = " ".join((request.form.get("custom_name") or "备用补给").strip().split())[:24]
    mode = request.form.get("access_mode")
    if mode not in ("private", "family"):
        mode = "private"
    if q("""SELECT 1 FROM supply_caches WHERE owner_user_id=? AND tile_x=? AND tile_y=?""",
         (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True):
        flash("你已经在这个坐标设置过藏点")
    elif tile_is_inhabited(ch["tile_x"], ch["tile_y"]):
        flash("这里有人住(房子或庇护所),藏点太显眼没意义，换块空地埋吧")
    elif not _has_enough(ch, {"wood": 5, "metal": 2}):
        flash("制作防潮藏箱需要木材x5、金属x2")
    else:
        _deduct(ch, {"wood": 5, "metal": 2})
        run("""INSERT INTO supply_caches
               (owner_character_id,owner_user_id,custom_name,tile_x,tile_y,access_mode,created_ts)
               VALUES(?,?,?,?,?,?,?)""",
            (ch["id"], ch["user_id"], name, ch["tile_x"], ch["tile_y"], mode, now_ts()))
        remember_location(ch["id"], ch["tile_x"], ch["tile_y"], f"你在这里埋下补给藏点「{name}」。")
        record_long_progress(ch["id"], "prepare", 1)
        add_region_noise(ch, 2, f"{display_name(ch)}埋设了一个补给藏点。", "build")
        flash(f"补给藏点「{name}」已经建立，只有允许的人走到这里才能存取")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/cache/<int:cache_id>/transfer", methods=["POST"])
@login_required
@need_character
def survival_cache_transfer(ch, cache_id):
    cache = q("SELECT * FROM supply_caches WHERE id=?", (cache_id,), one=True)
    direction = request.form.get("direction")
    key = request.form.get("resource_key")
    amount = request.form.get("amount", type=int) or 0
    if not cache or not can_access_cache(ch, cache):
        flash("你无权打开这个藏点")
    elif (cache["tile_x"], cache["tile_y"]) != (ch["tile_x"], ch["tile_y"]):
        flash(f"需要先走到藏点坐标({cache['tile_x']},{cache['tile_y']})")
    elif amount <= 0 or key not in ITEM_NAMES:
        flash("请选择有效物资和数量")
    elif direction == "deposit":
        have = q("""SELECT amount FROM character_inventory
                    WHERE character_id=? AND resource_key=?""", (ch["id"], key), one=True)
        total = inv_total("supply_cache_inventory", "cache_id", cache_id)
        if not have or have["amount"] < amount or total + amount > cache["capacity"]:
            flash("随身物资不足，或藏点容量不够")
        else:
            inv_add("character_inventory", "character_id", ch["id"], key, -amount)
            inv_add("supply_cache_inventory", "cache_id", cache_id, key, amount)
            run("""INSERT INTO supply_cache_logs(cache_id,character_id,action_key,detail,created_ts)
                   VALUES(?,?,'deposit',?,?)""",
                (cache_id, ch["id"], f"存入{ITEM_NAMES[key]}x{amount}", now_ts()))
            flash("物资已经藏好")
    elif direction == "withdraw":
        have = q("""SELECT amount FROM supply_cache_inventory
                    WHERE cache_id=? AND resource_key=?""", (cache_id, key), one=True)
        if not have or have["amount"] < amount:
            flash("藏点里的物资不足")
        else:
            inv_add("supply_cache_inventory", "cache_id", cache_id, key, -amount)
            inv_add("character_inventory", "character_id", ch["id"], key, amount)
            run("""INSERT INTO supply_cache_logs(cache_id,character_id,action_key,detail,created_ts)
                   VALUES(?,?,'withdraw',?,?)""",
                (cache_id, ch["id"], f"取出{ITEM_NAMES[key]}x{amount}", now_ts()))
            flash("物资已经取回背包")
    return redirect(url_for("survival_tech_view"))

@app.route("/survival-tech/ruin/dismantle", methods=["POST"])
@login_required
@need_character
def survival_ruin_dismantle(ch):
    ch = settle_stamina(ch)
    site = ensure_ruin_site(ch)
    part_key = request.form.get("part_key")
    info = RUIN_PARTS.get(part_key)
    part = q("""SELECT * FROM ruin_compartments WHERE site_id=? AND part_key=?""",
             (site["id"], part_key), one=True) if site and info else None
    if not site or not part or part["dismantled"]:
        flash("这个部分已经被拆空，或当前位置没有可拆废墟")
        return redirect(url_for("survival_tech_view"))
    ch, stamina_spent = spend_stamina(ch, STAMINA_COSTS["ruin"], "废墟拆解")
    loot_text = []
    loot_total = 0
    for key, lo, hi in info["loot"]:
        amount = random.randint(lo, hi) + (1 if has_daily_plan(ch, "prepare") else 0)
        inv_add("character_inventory", "character_id", ch["id"], key, amount)
        loot_text.append(f"{ITEM_NAMES[key]}x{amount}")
        loot_total += amount
    result = f"{display_name(ch)}完成{info['name']}，带走" + "、".join(loot_text)
    run("""UPDATE ruin_compartments SET dismantled=1,dismantled_by=?,dismantled_ts=?
           WHERE site_id=? AND part_key=?""", (ch["id"], now_ts(), site["id"], part_key))
    run("""UPDATE ruin_sites SET integrity=MAX(0,integrity-?),total_noise=total_noise+?
           WHERE id=?""", (info["damage"], info["noise"], site["id"]))
    run("""INSERT INTO ruin_dismantle_logs
           (site_id,character_id,part_key,noise,result_text,created_ts)
           VALUES(?,?,?,?,?,?)""", (site["id"], ch["id"], part_key, info["noise"], result, now_ts()))
    fatigue_noise = 3 if ch["stamina"] <= 0 else 0
    region_noise = info["noise"] if info.get("low_risk") else max(2, info["noise"] * 2)
    add_region_noise(ch, region_noise + fatigue_noise,
                     f"{display_name(ch)}拆解了废墟中的{info['name']}。", "ruin")
    record_daily_progress(ch["id"], "gather", loot_total)
    record_long_progress(ch["id"], "gather", loot_total)
    record_long_progress(ch["id"], "ruin", 1)
    record_long_progress(ch["id"], "prepare", 1)
    danger = info["danger"] + (.12 if ch["stamina"] <= 0 else (.06 if ch["stamina"] < 30 else 0))
    stamina_text = f"（体力-{stamina_spent}，剩余{ch['stamina']}）"
    if random.random() < danger:
        dist = dist_from_origin(ch["tile_x"], ch["tile_y"])
        ztype = roll_zombie_type(dist)
        strength = max(5, int(zombie_base_strength(dist, get_world_state()["day_count"]) *
                              ZOMBIE_TYPES[ztype]["hp_mult"]))
        run("""UPDATE characters SET pending_zombie_type=?,pending_zombie_hp=? WHERE id=?""",
            (ztype, strength, ch["id"]))
        flash(result + stamina_text + f"。但噪声惊动了{ZOMBIE_TYPES[ztype]['name']}！")
        return redirect(url_for("encounter"))
    flash(result + stamina_text + "。这次噪声没有引来危险。")
    return redirect(url_for("survival_tech_view"))

# ── 路由:个人生活工坊 ─────────────────────────────────────────────────────

@app.route("/homestead")
@login_required
@need_character
def homestead_view(ch):
    home = homestead_for(ch["id"])
    inventory = char_inv_list(ch["id"])
    inv_map = {r["resource_key"]: r["amount"] for r in inventory}
    batch = q("SELECT * FROM drink_batches WHERE character_id=?", (ch["id"],), one=True)
    outfits = q("SELECT * FROM personal_outfits WHERE character_id=? AND amount>0 ORDER BY outfit_key",
                (ch["id"],))
    animals = q("SELECT * FROM personal_livestock WHERE character_id=? ORDER BY status,id",
                (ch["id"],))
    animal_cards = []
    for animal in animals:
        animal_cards.append({
            "row": animal, "age": livestock_age(animal),
            "adult": livestock_age(animal) >= LIVESTOCK_TYPES[animal["species_key"]]["adult_age"],
            "logs": q("""SELECT * FROM livestock_logs WHERE animal_id=?
                         ORDER BY id DESC LIMIT 4""", (animal["id"],)),
        })
    children = q("""SELECT * FROM children WHERE status='alive'
                    AND (parent_a=? OR parent_b=?)""", (ch["id"], ch["id"]))
    child_outfits = {r["child_id"]: r for r in q(
        """SELECT o.* FROM child_outfits o JOIN children c ON c.id=o.child_id
           WHERE c.parent_a=? OR c.parent_b=?""", (ch["id"], ch["id"]))}
    craft_logs = q("""SELECT * FROM life_crafting_logs WHERE character_id=?
                      ORDER BY id DESC LIMIT 12""", (ch["id"],))
    home_kind, home_row, _ = homestead_home_here(ch)
    home_power = ensure_power_grid(home_kind, home_row["id"]) if home_row else None
    return render_template("homestead.html", ch=ch, home=home, inventory=inventory,
                           inv_map=inv_map, batch=batch, outfits=outfits, animals=animal_cards,
                           children=children, child_outfits=child_outfits,
                           craft_logs=craft_logs,
                           stations=HOMESTEAD_STATIONS, food_recipes=FOOD_RECIPES,
                           drink_recipes=DRINK_RECIPES, clothing_recipes=CLOTHING_RECIPES,
                           livestock_types=LIVESTOCK_TYPES, item_names=ITEM_NAMES,
                           fish_species=FISH_SPECIES, house_here=bool(home_row),
                           home_kind=home_kind,
                           home_power=home_power, generator_levels=GENERATOR_LEVELS,
                           now_ts=now_ts(), day_seconds=DAY_SECONDS)

@app.route("/homestead/station/build", methods=["POST"])
@login_required
@need_character
def homestead_build_station(ch):
    station = request.form.get("station")
    info = HOMESTEAD_STATIONS.get(station)
    cols = {"kitchen": "has_kitchen", "brewery": "has_brewery",
            "sewing": "has_sewing", "livestock": "has_livestock"}
    home = homestead_for(ch["id"])
    _, home_row, local_ref = homestead_home_here(ch)
    if not info or station not in cols:
        flash("没有这种生活设施")
    elif not home_row:
        flash("需要站在自己的房屋或所属庇护所地块才能建设个人生活设施")
    elif home[cols[station]]:
        flash("这项设施已经建好了")
    elif not _has_enough_with_local(ch, info["cost"], local_ref):
        flash("建设材料不足(随身+房子仓库合计)")
    else:
        _deduct_with_local(ch, info["cost"], local_ref)
        run(f"UPDATE personal_homesteads SET {cols[station]}=1 WHERE character_id=?", (ch["id"],))
        album_add(ch["id"], "homestead", info["name"], f"{display_name(ch)}在房间里建好了{info['name']}。")
        add_region_noise(ch, 6, f"{display_name(ch)}安装了{info['name']}。", "build")
        flash(f"{info['name']}建好了")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/fish/process", methods=["POST"])
@login_required
@need_character
def homestead_process_fish(ch):
    fish_key = request.form.get("fish_key")
    fish = FISH_SPECIES.get(fish_key)
    have = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key=?""", (ch["id"], fish_key), one=True)
    if not fish or not have or have["amount"] < 1:
        flash("没有这条鱼可以处理")
    else:
        amount = 1 + (1 if fish["rarity"] in ("rare", "legendary") else 0)
        inv_add("character_inventory", "character_id", ch["id"], fish_key, -1)
        inv_add("character_inventory", "character_id", ch["id"], "fish_meat", amount)
        bonus_msg = ""
        if fish["rarity"] == "legendary" and random.random() < LEGENDARY_FISH_RESONANCE_CHANCE:
            inv_add("character_inventory", "character_id", ch["id"], "resonance_material", 1)
            bonus_msg = f"，鱼腹里还带出一块{ITEM_NAMES['resonance_material']}！"
        flash(f"处理了{fish['name']}，获得{ITEM_NAMES['fish_meat']}x{amount}{bonus_msg}")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/cook", methods=["POST"])
@login_required
@need_character
def homestead_cook(ch):
    key = request.form.get("recipe_key")
    recipe = FOOD_RECIPES.get(key)
    home = homestead_for(ch["id"])
    kind, home_row, local_ref = homestead_home_here(ch)
    if not home_row:
        flash("做饭需要回到自己的房屋或所属庇护所；厨房、电网和储藏都在那里")
    elif not recipe or not home["has_kitchen"]:
        flash("需要先建好个人厨房")
    elif home["cooking_skill"] < recipe["skill"]:
        flash(f"烹饪熟练度需要达到{recipe['skill']}")
    elif not _has_enough_with_local(ch, recipe["cost"], local_ref):
        flash("食材不足(随身+当前仓库合计)")
    else:
        powered = consume_power(kind, home_row["id"], 1, "厨房烹饪",
                                character_id=ch["id"])
        if not powered and not _has_enough_with_local(ch, {"wood": 1}, local_ref):
            flash("厨房当前无法取电；使用炉火烹饪还需要木材x1(随身+当前仓库合计)")
            return redirect(url_for("homestead_view"))
        _deduct_with_local(ch, recipe["cost"], local_ref)
        if not powered:
            _deduct_with_local(ch, {"wood": 1}, local_ref)
        inv_add("character_inventory", "character_id", ch["id"], key, 1)
        run("UPDATE personal_homesteads SET cooking_skill=cooking_skill+1 WHERE character_id=?",
            (ch["id"],))
        run("""INSERT INTO life_crafting_logs(character_id,craft_type,recipe_key,detail,created_ts)
               VALUES(?,'cooking',?,?,?)""", (ch["id"], key, f"做出了{recipe['name']}", now_ts()))
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 3)
        noise = 1 if powered else 5
        add_region_noise(ch, noise,
                         f"{display_name(ch)}用{'电灶' if powered else '冒烟炉火'}制作了{recipe['name']}。",
                         "life")
        flash(f"做出了{recipe['name']}，烹饪熟练度+1；"
              f"{'电力-1、噪声+1' if powered else '木材-1、烟火噪声+5'}")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/brew/start", methods=["POST"])
@login_required
@need_character
def homestead_brew_start(ch):
    key = request.form.get("recipe_key")
    recipe = DRINK_RECIPES.get(key)
    home = homestead_for(ch["id"])
    if not recipe or not home["has_brewery"]:
        flash("需要先建好饮品与发酵台")
    elif q("SELECT 1 FROM drink_batches WHERE character_id=?", (ch["id"],), one=True):
        flash("发酵台上已经有一批饮品")
    elif home["brewing_skill"] < recipe["skill"]:
        flash(f"饮品熟练度需要达到{recipe['skill']}")
    elif not _has_enough(ch, recipe["cost"]):
        flash("冲泡或发酵材料不足")
    else:
        _deduct(ch, recipe["cost"])
        duration = 8 * 60 + recipe["skill"] * 2 * 60
        run("""INSERT INTO drink_batches(character_id,recipe_key,ready_ts,started_ts)
               VALUES(?,?,?,?)""", (ch["id"], key, now_ts() + duration, now_ts()))
        add_region_noise(ch, 2, f"{display_name(ch)}启动了饮品发酵台。", "life")
        flash(f"{recipe['name']}已经开始制作，约{duration//60}分钟后可以收取")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/brew/collect", methods=["POST"])
@login_required
@need_character
def homestead_brew_collect(ch):
    batch = q("SELECT * FROM drink_batches WHERE character_id=?", (ch["id"],), one=True)
    if not batch:
        flash("没有正在制作的饮品")
    elif now_ts() < batch["ready_ts"]:
        flash("这批饮品还没有完成")
    else:
        recipe = DRINK_RECIPES[batch["recipe_key"]]
        inv_add("character_inventory", "character_id", ch["id"], batch["recipe_key"], 2)
        run("DELETE FROM drink_batches WHERE character_id=?", (ch["id"],))
        run("UPDATE personal_homesteads SET brewing_skill=brewing_skill+1 WHERE character_id=?",
            (ch["id"],))
        run("""INSERT INTO life_crafting_logs(character_id,craft_type,recipe_key,detail,created_ts)
               VALUES(?,'brewing',?,?,?)""", (ch["id"], batch["recipe_key"], f"完成了两杯{recipe['name']}", now_ts()))
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 3)
        flash(f"收取了{recipe['name']}x2，饮品熟练度+1")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/consume", methods=["POST"])
@login_required
@need_character
def homestead_consume(ch):
    key = request.form.get("item_key")
    recipe = FOOD_RECIPES.get(key) or DRINK_RECIPES.get(key)
    have = q("""SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?""",
             (ch["id"], key), one=True)
    if not recipe or not have or have["amount"] < 1:
        flash("身上没有这份食物或饮品")
    else:
        inv_add("character_inventory", "character_id", ch["id"], key, -1)
        hunger = recipe.get("hunger", 0)
        thirst = recipe.get("thirst", 0)
        heal = recipe.get("heal", 0)
        fun_amount = recipe.get("recreation", 0) + (2 if has_daily_plan(ch, "life") else 0)
        fun = recreation_gain(ch, fun_amount, f"享用{recipe['name']}")
        prep_kind = "food" if key in FOOD_RECIPES else "drink"
        set_combat_preparation(ch, prep_kind, key)
        stamina_restore = (8 + min(8, recipe.get("skill", 0))
                           if prep_kind == "food"
                           else 5 + min(6, recipe.get("skill", 0)))
        if has_daily_plan(ch, "life"):
            stamina_restore += 3
        _, stamina_gain = restore_stamina(ch, stamina_restore, f"享用{recipe['name']}")
        run("""UPDATE characters SET hunger=MIN(100,hunger+?),thirst=MIN(100,thirst+?),
               hp=MIN(100,hp+?) WHERE id=?""", (hunger, thirst, heal, ch["id"]))
        prep_text = "今日战斗伤害与防守提高" if prep_kind == "food" else "今日战斗暴击与脱离率提高"
        flash(f"享用了{recipe['name']}，饥饿+{hunger}、口渴+{thirst}" +
              (f"、HP+{heal}" if heal else "") +
              f"、娱乐+{fun}、体力+{stamina_gain}；{prep_text}")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/sew", methods=["POST"])
@login_required
@need_character
def homestead_sew(ch):
    key = request.form.get("recipe_key")
    recipe = CLOTHING_RECIPES.get(key)
    home = homestead_for(ch["id"])
    if not recipe or not home["has_sewing"]:
        flash("需要先建好缝纫工作台")
    elif home["sewing_skill"] < recipe["skill"]:
        flash(f"缝纫熟练度需要达到{recipe['skill']}")
    elif not _has_enough(ch, recipe["cost"]):
        flash("布料或其他材料不足")
    else:
        _deduct(ch, recipe["cost"])
        run("""INSERT INTO personal_outfits(character_id,outfit_key,amount,crafted_ts)
               VALUES(?,?,1,?) ON CONFLICT(character_id,outfit_key)
               DO UPDATE SET amount=amount+1,crafted_ts=?""",
            (ch["id"], key, now_ts(), now_ts()))
        run("UPDATE personal_homesteads SET sewing_skill=sewing_skill+1 WHERE character_id=?",
            (ch["id"],))
        run("""INSERT INTO life_crafting_logs(character_id,craft_type,recipe_key,detail,created_ts)
               VALUES(?,'sewing',?,?,?)""", (ch["id"], key, f"缝好了{recipe['name']}", now_ts()))
        record_long_progress(ch["id"], "prepare", 1)
        grant_xp(ch, 3)
        flash(f"缝好了{recipe['name']}，缝纫熟练度+1")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/outfit/<outfit_key>/equip", methods=["POST"])
@login_required
@need_character
def homestead_outfit_equip(ch, outfit_key):
    owned = q("""SELECT * FROM personal_outfits WHERE character_id=?
                 AND outfit_key=? AND amount>0""", (ch["id"], outfit_key), one=True)
    if not owned or outfit_key == "child_outfit":
        flash("这件衣服不能由当前角色穿戴")
    else:
        run("UPDATE personal_outfits SET equipped=0 WHERE character_id=?", (ch["id"],))
        run("""UPDATE personal_outfits SET equipped=1 WHERE character_id=? AND outfit_key=?""",
            (ch["id"], outfit_key))
        flash(f"已经换上{CLOTHING_RECIPES[outfit_key]['name']}")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/outfit/child/<int:child_id>", methods=["POST"])
@login_required
@need_character
def homestead_outfit_child(ch, child_id):
    child = q("""SELECT * FROM children WHERE id=? AND status='alive'
                 AND (parent_a=? OR parent_b=?)""", (child_id, ch["id"], ch["id"]), one=True)
    owned = q("""SELECT * FROM personal_outfits WHERE character_id=? AND outfit_key='child_outfit'
                 AND amount>0""", (ch["id"],), one=True)
    if not child or not owned:
        flash("没有可赠送的儿童防护服")
    elif q("SELECT 1 FROM child_outfits WHERE child_id=?", (child_id,), one=True):
        flash("这个孩子已经有防护服了")
    else:
        run("""UPDATE personal_outfits SET amount=amount-1
               WHERE character_id=? AND outfit_key='child_outfit'""", (ch["id"],))
        run("""INSERT INTO child_outfits(child_id,outfit_key,gifted_by,gifted_ts)
               VALUES(?,'child_outfit',?,?)""", (child_id, ch["id"], now_ts()))
        album_add(ch["id"], "child_outfit", "给孩子缝衣服",
                  f"{display_name(ch)}把亲手缝的防护服交给了{child['name']}。", child_id=child_id)
        flash(f"{child['name']}穿上了防护服，今后的自动探索风险会降低")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/livestock/adopt", methods=["POST"])
@login_required
@need_character
def homestead_livestock_adopt(ch):
    species = request.form.get("species_key")
    info = LIVESTOCK_TYPES.get(species)
    name = " ".join((request.form.get("custom_name") or "").strip().split())[:16]
    home = homestead_for(ch["id"])
    count = q("""SELECT COUNT(*) AS c FROM personal_livestock
                 WHERE character_id=? AND status='alive'""", (ch["id"],), one=True)["c"]
    if not info or not home["has_livestock"]:
        flash("需要先建好小型畜牧棚")
    elif count >= 8:
        flash("畜牧棚最多照顾8只动物")
    elif ch["wallet"] < info["price"]:
        flash(f"需要{info['price']}钱包向流动牧人换取幼崽")
    else:
        run("UPDATE characters SET wallet=wallet-? WHERE id=?", (info["price"], ch["id"]))
        cur = run("""INSERT INTO personal_livestock
                     (character_id,species_key,custom_name,born_ts,created_ts)
                     VALUES(?,?,?,?,?)""",
                  (ch["id"], species, name or info["name"], now_ts(), now_ts()))
        run("""INSERT INTO livestock_logs(animal_id,event_key,detail,created_ts)
               VALUES(?,'arrival',?,?)""", (cur.lastrowid, f"{name or info['name']}来到了畜牧棚。", now_ts()))
        flash(f"{name or info['name']}已经住进畜牧棚")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/livestock/<int:animal_id>/feed", methods=["POST"])
@login_required
@need_character
def homestead_livestock_feed(ch, animal_id):
    animal = q("""SELECT * FROM personal_livestock WHERE id=? AND character_id=?
                  AND status='alive'""", (animal_id, ch["id"]), one=True)
    age = livestock_age(animal) if animal else -1
    if not animal:
        flash("这只动物不在畜牧棚里")
    elif animal["fed_age_day"] >= age:
        flash("今天已经喂过了")
    elif not _has_enough(ch, {"raw_food": 1}):
        flash("需要1份生鲜作为饲料")
    else:
        _deduct(ch, {"raw_food": 1})
        run("""UPDATE personal_livestock SET fed_age_day=?,health=MIN(100,health+8)
               WHERE id=?""", (age, animal_id))
        run("""INSERT INTO livestock_logs(animal_id,event_key,detail,created_ts)
               VALUES(?,'feed',?,?)""", (animal_id, f"{animal['custom_name']}今天吃饱了。", now_ts()))
        fun = recreation_gain(ch, 3 if has_daily_plan(ch, "life") else 1, "照顾畜牧棚里的动物")
        record_long_progress(ch["id"], "connection", 1)
        flash(f"喂过{animal['custom_name']}了，娱乐+{fun}")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/livestock/<int:animal_id>/rename", methods=["POST"])
@login_required
@need_character
def homestead_livestock_rename(ch, animal_id):
    name = " ".join((request.form.get("custom_name") or "").strip().split())[:16]
    if name:
        run("""UPDATE personal_livestock SET custom_name=? WHERE id=? AND character_id=?""",
            (name, animal_id, ch["id"]))
        flash("动物的新名字已经记下")
    return redirect(url_for("homestead_view"))

@app.route("/homestead/livestock/breed", methods=["POST"])
@login_required
@need_character
def homestead_livestock_breed(ch):
    species = request.form.get("species_key")
    info = LIVESTOCK_TYPES.get(species)
    current_day = survivor_day(ch)
    animals = q("""SELECT * FROM personal_livestock WHERE character_id=? AND species_key=?
                   AND status='alive' AND born_ts<=?""",
                (ch["id"], species, now_ts() - (info["adult_age"] * DAY_SECONDS) if info else 0)) if info else []
    animals = [a for a in animals if a["fed_age_day"] >= livestock_age(a)]
    count = q("""SELECT COUNT(*) AS c FROM personal_livestock
                 WHERE character_id=? AND status='alive'""", (ch["id"],), one=True)["c"]
    if not info or len(animals) < 2:
        flash("需要两只今天已经喂过的成年同类动物")
    elif count >= 8:
        flash("畜牧棚已经住满了")
    elif q("""SELECT 1 FROM livestock_breeding_logs
              WHERE character_id=? AND species_key=? AND age_day=?""",
           (ch["id"], species, current_day), one=True):
        flash("今天已经安排过这种动物繁育")
    elif not _has_enough(ch, {"raw_food": 2}):
        flash("繁育需要额外准备2份生鲜")
    else:
        _deduct(ch, {"raw_food": 2})
        baby_name = f"小{info['name'].split()[-1]}"
        cur = run("""INSERT INTO personal_livestock
                     (character_id,species_key,custom_name,born_ts,parent_a,parent_b,created_ts)
                     VALUES(?,?,?,?,?,?,?)""",
                  (ch["id"], species, baby_name, now_ts(), animals[0]["id"], animals[1]["id"], now_ts()))
        run("""INSERT INTO livestock_breeding_logs(character_id,species_key,age_day,created_ts)
               VALUES(?,?,?,?)""", (ch["id"], species, current_day, now_ts()))
        run("""INSERT INTO livestock_logs(animal_id,event_key,detail,created_ts)
               VALUES(?,'birth',?,?)""", (cur.lastrowid, f"{baby_name}在畜牧棚出生。", now_ts()))
        album_add(ch["id"], "livestock_birth", "畜牧棚的新生命", f"{baby_name}在个人畜牧棚出生。")
        flash(f"{baby_name}出生了，可以在下方给它改名")
    return redirect(url_for("homestead_view"))

@app.route("/legacy")
@login_required
@need_character
def legacy_view(ch):
    user_chars = q("SELECT * FROM characters WHERE user_id=? ORDER BY id", (ch["user_id"],))
    char_ids = [r["id"] for r in user_chars]
    placeholders = ",".join("?" for _ in char_ids)
    children = q(f"""SELECT c.*,a.name AS parent_a_name,b.name AS parent_b_name
                     FROM children c JOIN characters a ON a.id=c.parent_a
                     JOIN characters b ON b.id=c.parent_b
                     WHERE c.parent_a IN ({placeholders}) OR c.parent_b IN ({placeholders})
                     ORDER BY c.born_ts""", tuple(char_ids + char_ids)) if char_ids else []
    album = q(f"""SELECT * FROM family_album WHERE character_id IN ({placeholders})
                  ORDER BY id DESC LIMIT 80""", tuple(char_ids)) if char_ids else []
    heirlooms = q(f"""SELECT h.*,c.name AS owner_name FROM family_heirlooms h
                      JOIN characters c ON c.id=h.owner_character_id
                      WHERE h.owner_character_id IN ({placeholders}) ORDER BY h.id""",
                  tuple(char_ids)) if char_ids else []
    relations = q("""SELECT r.*,a.name AS a_name,b.name AS b_name
                     FROM close_relationships r JOIN characters a ON a.id=r.char_a
                     JOIN characters b ON b.id=r.char_b
                     WHERE (r.char_a=? OR r.char_b=?) ORDER BY r.created_ts DESC""",
                  (ch["id"], ch["id"]))
    guardian_requests = q("""SELECT g.*,c.name AS child_name,p.name AS requester_name
                             FROM child_guardians g JOIN children c ON c.id=g.child_id
                             JOIN characters p ON p.id=g.requested_by
                             WHERE g.guardian_character_id=? ORDER BY g.created_ts DESC""",
                          (ch["id"],))
    return render_template("legacy.html", ch=ch, generations=user_chars, children=children,
                           album=album, heirlooms=heirlooms, relations=relations,
                           guardian_requests=guardian_requests, item_names=ITEM_NAMES,
                           inventory=char_inv_list(ch["id"]))

@app.route("/legacy/heirloom/create", methods=["POST"])
@login_required
@need_character
def heirloom_create(ch):
    item_key = request.form.get("item_key")
    custom_name = " ".join((request.form.get("custom_name") or "").strip().split())[:28]
    allowed = set(RING_RECIPES) | set(BLUEPRINTS) | {
        NORTHSTAR_FINAL_ITEM_KEY, "old_gem", "electronics", "resonance_material"}
    have = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key=?""", (ch["id"], item_key), one=True)
    equipped_weapon = item_key == ch["equipped_weapon"] and item_key != "fist"
    equipped_armor = item_key == ch["equipped_armor"]
    if (item_key not in allowed or not custom_name or
            not ((have and have["amount"] >= 1) or equipped_weapon or equipped_armor)):
        flash("请选择一件可保存的珍贵物品并为它命名")
    else:
        if equipped_weapon:
            run("""UPDATE characters SET equipped_weapon='fist',weapon_durability=100
                   WHERE id=?""", (ch["id"],))
        elif equipped_armor:
            run("""UPDATE characters SET equipped_armor=NULL,armor_durability=0,armor_tier=0
                   WHERE id=?""", (ch["id"],))
        else:
            inv_add("character_inventory", "character_id", ch["id"], item_key, -1)
        cur = run("""INSERT INTO family_heirlooms
                     (owner_character_id,founder_character_id,custom_name,item_key,story_text,created_ts)
                     VALUES(?,?,?,?,?,?)""",
                  (ch["id"], ch["id"], custom_name, item_key,
                   f"{display_name(ch)}把{ITEM_NAMES.get(item_key,item_key)}保存为家族遗物。", now_ts()))
        run("""INSERT INTO heirloom_history(heirloom_id,character_id,event_text,created_ts)
               VALUES(?,?,?,?)""", (cur.lastrowid, ch["id"], "被选为第一代家族遗物", now_ts()))
        album_add(ch["id"], "heirloom", "家族遗物诞生",
                  f"「{custom_name}」从普通物品变成了等待下一代接过的记忆。")
        record_long_progress(ch["id"], "connection", 1)
        flash(f"故事物品「{custom_name}」已经建立，可以随家族继续传承")
    return redirect(url_for("legacy_view"))

@app.route("/expeditions")
@login_required
@need_character
def expeditions_view(ch):
    ch = settle_stamina(ch)
    active = q("""SELECT * FROM expeditions WHERE character_id=? AND status='active'
                  ORDER BY id DESC LIMIT 1""", (ch["id"],), one=True)
    history = q("""SELECT * FROM expeditions WHERE character_id=? AND status<>'active'
                   ORDER BY id DESC LIMIT 12""", (ch["id"],))
    companions = q("""SELECT c.* FROM characters c JOIN close_relationships r
                      ON (r.char_a=? AND r.char_b=c.id) OR (r.char_b=? AND r.char_a=c.id)
                      WHERE r.status='accepted' AND c.status='alive'""", (ch["id"], ch["id"]))
    adult_children = q("""SELECT * FROM children WHERE status='alive' AND (parent_a=? OR parent_b=?)
                          AND born_ts<=?""", (ch["id"], ch["id"], now_ts() - 18 * DAY_SECONDS))
    quests = q("""SELECT * FROM dynamic_personal_quests WHERE character_id=?
                  ORDER BY status='active' DESC,id DESC""", (ch["id"],))
    return render_template("expeditions.html", ch=ch, routes=EXPEDITION_ROUTES,
                           active=active, history=history, companions=companions,
                           adult_children=adult_children, quests=quests,
                           item_names=ITEM_NAMES, now_ts=now_ts(),
                           stamina_costs=STAMINA_COSTS)

@app.route("/expeditions/start", methods=["POST"])
@login_required
@need_character
def expedition_start(ch):
    ch = settle_stamina(ch)
    route_key = request.form.get("route_key")
    strategy = request.form.get("strategy")
    route = EXPEDITION_ROUTES.get(route_key)
    if strategy not in ("careful", "balanced", "bold"):
        strategy = "balanced"
    if q("SELECT 1 FROM expeditions WHERE character_id=? AND status='active'", (ch["id"],), one=True):
        flash("你已经有一支远征队在外面")
        return redirect(url_for("expeditions_view"))
    if not route or not _has_enough(ch, route["cost"]):
        flash("路线不存在或远征补给不足")
        return redirect(url_for("expeditions_view"))
    companion_id = request.form.get("companion_character_id", type=int)
    child_id = request.form.get("child_id", type=int)
    if companion_id:
        rel = q("""SELECT 1 FROM close_relationships WHERE status='accepted'
                   AND ((char_a=? AND char_b=?) OR (char_a=? AND char_b=?))""",
                (ch["id"], companion_id, companion_id, ch["id"]), one=True)
        if not rel:
            companion_id = None
    if child_id:
        child = q("""SELECT * FROM children WHERE id=? AND status='alive'
                     AND (parent_a=? OR parent_b=?) AND born_ts<=?""",
                  (child_id, ch["id"], ch["id"], now_ts() - 18 * DAY_SECONDS), one=True)
        if not child:
            child_id = None
    _deduct(ch, route["cost"])
    ch, stamina_spent = spend_stamina(ch, STAMINA_COSTS["expedition"], "离线远征")
    duration = route["duration"]
    if strategy == "careful":
        duration = int(duration * 1.25)
    elif strategy == "bold":
        duration = int(duration * .8)
    outfit = equipped_outfit(ch["id"])
    if outfit and outfit["outfit_key"] == "scout_outfit":
        duration = int(duration * .9)
    run("""INSERT INTO expeditions
           (character_id,route_key,strategy,companion_character_id,child_id,depart_ts,return_ts)
           VALUES(?,?,?,?,?,?,?)""",
        (ch["id"], route_key, strategy, companion_id, child_id, now_ts(), now_ts() + duration))
    add_region_noise(ch, 4 if strategy == "careful" else (8 if strategy == "bold" else 6),
                     f"{display_name(ch)}组织了一次{route['name']}远征。", "expedition")
    flash(f"{route['name']}已经出发。体力-{stamina_spent}，剩余{ch['stamina']}；"
          f"可以离线等待，预计{max(1,duration//60)}分钟后返程。")
    return redirect(url_for("expeditions_view"))

@app.route("/dynamic-quest/<int:quest_id>/claim", methods=["POST"])
@login_required
@need_character
def dynamic_quest_claim(ch, quest_id):
    quest = q("""SELECT * FROM dynamic_personal_quests
                 WHERE id=? AND character_id=? AND status='active'""",
              (quest_id, ch["id"]), one=True)
    if not quest or quest["progress"] < quest["target"]:
        flash("这段个人支线还没有完成")
    else:
        if quest["reward_key"] == "wallet":
            run("UPDATE characters SET wallet=wallet+? WHERE id=?", (quest["reward_amount"], ch["id"]))
        else:
            inv_add("character_inventory", "character_id", ch["id"],
                    quest["reward_key"], quest["reward_amount"])
        run("""UPDATE dynamic_personal_quests SET status='claimed',completed_ts=? WHERE id=?""",
            (now_ts(), quest_id))
        album_add(ch["id"], "personal_quest", quest["title"],
                  f"{display_name(ch)}完成了经历自然生出的支线：{quest['description']}")
        flash("个人支线完成，奖励已经领取")
    return redirect(url_for("story_view"))

@app.route("/blueprints")
@login_required
@need_character
def blueprints_list(ch):
    unlocked = {r["blueprint_key"] for r in q("SELECT blueprint_key FROM character_blueprints WHERE character_id=?", (ch["id"],))}
    return render_template("blueprints.html", ch=ch, blueprints=BLUEPRINTS, unlocked=unlocked,
                           resources=RESOURCES, item_names=ITEM_NAMES)

@app.route("/blueprint/<key>/unlock", methods=["POST"])
@login_required
@need_character
def blueprint_unlock(ch, key):
    bp = BLUEPRINTS.get(key)
    if not bp:
        flash("没有这个图纸")
        return redirect(url_for("blueprints_list"))
    if ch["level"] < bp["level"]:
        flash(f"需要{bp['level']}级才能解锁「{bp['name']}」")
        return redirect(url_for("blueprints_list"))
    if ch["blueprint_points"] < 1:
        flash("图纸点数不够(每级升级给1点)")
        return redirect(url_for("blueprints_list"))
    if q("SELECT 1 FROM character_blueprints WHERE character_id=? AND blueprint_key=?", (ch["id"], key), one=True):
        flash("已经解锁过了")
        return redirect(url_for("blueprints_list"))
    run("UPDATE characters SET blueprint_points=blueprint_points-1 WHERE id=?", (ch["id"],))
    run("INSERT INTO character_blueprints (character_id, blueprint_key, unlocked_ts) VALUES (?,?,?)",
        (ch["id"], key, now_ts()))
    flash(f"解锁了图纸「{bp['name']}」")
    return redirect(url_for("blueprints_list"))

@app.route("/action/craft", methods=["POST"])
@login_required
@need_character
def action_craft(ch):
    key = request.form.get("blueprint_key")
    bp = BLUEPRINTS.get(key)
    if not bp:
        flash("没有这个图纸")
        return redirect(url_for("blueprints_list"))
    if not q("SELECT 1 FROM character_blueprints WHERE character_id=? AND blueprint_key=?", (ch["id"], key), one=True):
        flash("还没解锁这个图纸")
        return redirect(url_for("blueprints_list"))
    if not _workbench_available(ch, bp["workbench"]):
        need = "个人房子或所属庇护所的基础工作台" if bp["workbench"] == "basic" else "所属庇护所的高级工作台"
        flash(f"这里没有{need},不能制作")
        return redirect(url_for("dashboard"))
    if key == "fishing_rod" and q("""SELECT amount FROM character_inventory
                                     WHERE character_id=? AND resource_key='fishing_rod' AND amount>0""",
                                  (ch["id"],), one=True):
        flash("已经有鱼竿了,不用再做一根")
        return redirect(url_for("dashboard"))
    if key == "radar" and q("""SELECT amount FROM character_inventory
                               WHERE character_id=? AND resource_key='radar' AND amount>0""",
                            (ch["id"],), one=True):
        flash("你已经有便携雷达了")
        return redirect(url_for("dashboard"))
    # 制作材料随身不够时,可以从当前所在的房子/庇护所仓库里补(工作台判定已经保证人在现场)。
    kind, home_row, local_ref = _workbench_local_ref(ch, bp["workbench"])
    if not _has_enough_with_local(ch, bp["cost"], local_ref):
        flash("材料不够(随身+当前仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in bp["cost"].items()))
        return redirect(url_for("dashboard"))
    powered = bool(home_row and consume_power(
        kind, home_row["id"], 1, f"{'高级' if bp['workbench'] == 'advanced' else '基础'}工作台制作{bp['name']}",
        character_id=ch["id"]))
    _deduct_with_local(ch, bp["cost"], local_ref)
    if bp["type"] in ("weapon", "armor", "backpack"):
        # 武器/护甲/背包做好先进背包(和其他物资一样可以存仓库、给别人用)，不再直接自动装备/生效；
        # 要用得自己从背包点"装备"(action_equip)。
        inv_add("character_inventory", "character_id", ch["id"], key, 1)
        flash(f"做好了「{bp['name']}」,放进背包了——去装备使用,或者存进仓库留给别人")
    elif bp["type"] == "medical":
        inv_add("character_inventory", "character_id", ch["id"], key, 1)
        flash(f"制作了「{bp['name']}」x1,放进随身携带里了")
    elif bp["type"] == "tool" and key == "fishing_rod":
        inv_add("character_inventory", "character_id", ch["id"], "fishing_rod", 1)
        flash("做好了鱼竿,放进背包了,去水域地块试试手气吧")
    elif bp["type"] == "tool" and key == "radar":
        inv_add("character_inventory", "character_id", ch["id"], "radar", 1)
        flash("便携雷达制作完成：大地图视野和救援接收范围扩大到10格")
    elif bp["type"] == "food":
        inv_add("character_inventory", "character_id", ch["id"], key, 1)
        flash(f"做了「{bp['name']}」x1,放进随身携带里了")
    record_daily_progress(ch["id"], "craft", 1)
    record_long_progress(ch["id"], "craft", 1)
    record_long_progress(ch["id"], "prepare", 1)
    grant_xp(ch, 5)
    log_action(ch["id"], "craft", key)
    noise = 2 if powered else (7 if bp["workbench"] == "advanced" else 4)
    add_region_noise(ch, noise,
                     f"{display_name(ch)}用{'通电工作台' if powered else '手动工具'}制作了{bp['name']}。",
                     "production")
    if powered:
        flash("工作台本次消耗电力1，机械噪声受到控制")
    else:
        flash(f"电网未供电，改用手动加工，区域噪声+{noise}")
    return redirect(url_for("dashboard"))

@app.route("/action/equip", methods=["POST"])
@login_required
@need_character
def action_equip(ch):
    key = request.form.get("item_key")
    bp = BLUEPRINTS.get(key)
    if not bp or bp["type"] not in ("weapon", "armor", "backpack"):
        flash("没有这个可以装备的东西")
        return redirect(url_for("dashboard"))
    have = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
             (ch["id"], key), one=True)
    if not have or have["amount"] <= 0:
        flash("背包里没有这个东西")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], key, -1)
    if bp["type"] == "weapon":
        old = ch["equipped_weapon"]
        if old and old != "fist":
            inv_add("character_inventory", "character_id", ch["id"], old, 1)
        run("UPDATE characters SET equipped_weapon=?, weapon_durability=100 WHERE id=?", (key, ch["id"]))
        flash(f"装备了「{bp['name']}」" +
              (f"，换下的「{BLUEPRINTS[old]['name']}」放回背包了" if old and old != "fist" else ""))
    elif bp["type"] == "armor":
        old = ch["equipped_armor"]
        if old:
            inv_add("character_inventory", "character_id", ch["id"], old, 1)
        run("UPDATE characters SET equipped_armor=?, armor_durability=100, armor_tier=? WHERE id=?",
            (key, bp["tier"], ch["id"]))
        flash(f"穿上了「{bp['name']}」" +
              (f"，换下的「{BLUEPRINTS[old]['name']}」放回背包了" if old else ""))
    else:  # backpack
        if ch["backpack_count"] >= BACKPACK_CAP:
            inv_add("character_inventory", "character_id", ch["id"], key, 1)
            flash(f"背包最多叠加{BACKPACK_CAP}件,已经到上限了,这个背包放回你随身携带里了")
            return redirect(url_for("dashboard"))
        run("UPDATE characters SET backpack_count=backpack_count+1, storage_capacity=storage_capacity+? WHERE id=?",
            (BACKPACK_BONUS, ch["id"]))
        flash(f"装上了背包,随身储物容量+{BACKPACK_BONUS}")
    return redirect(url_for("dashboard"))

@app.route("/action/repair", methods=["POST"])
@login_required
@need_character
def action_repair(ch):
    slot = request.form.get("slot")  # weapon / armor
    key = ch["equipped_weapon"] if slot == "weapon" else ch["equipped_armor"]
    if not key or key == "fist":
        flash("没有装备可以修")
        return redirect(url_for("dashboard"))
    bp = BLUEPRINTS.get(key)
    if not _workbench_available(ch, bp["workbench"]):
        need = "个人房子或所属庇护所的基础工作台" if bp["workbench"] == "basic" else "所属庇护所的高级工作台"
        flash(f"这里没有{need},不能修理")
        return redirect(url_for("dashboard"))
    repair_cost = {k: max(1, int(v * 0.3)) for k, v in bp["cost"].items()}
    _, _, local_ref = _workbench_local_ref(ch, bp["workbench"])
    if not _has_enough_with_local(ch, repair_cost, local_ref):
        flash("修理材料不够(随身+当前仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in repair_cost.items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, repair_cost, local_ref)
    col = "weapon_durability" if slot == "weapon" else "armor_durability"
    run(f"UPDATE characters SET {col}=100 WHERE id=?", (ch["id"],))
    record_long_progress(ch["id"], "prepare", 1)
    add_region_noise(ch, 2, f"{display_name(ch)}修理了{bp['name']}。", "production")
    flash(f"「{bp['name']}」修好了,耐久恢复满")
    return redirect(url_for("dashboard"))

@app.route("/action/use_medical", methods=["POST"])
@login_required
@need_character
def action_use_medical(ch):
    key = request.form.get("item_key")
    bp = BLUEPRINTS.get(key)
    if not bp or bp["type"] != "medical":
        flash("这不是医疗用品")
        return redirect(url_for("dashboard"))
    have = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?", (ch["id"], key), one=True)
    if not have or have["amount"] <= 0:
        flash("身上没有这个东西")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], key, -1)
    new_hp = min(100, ch["hp"] + bp["heal"])
    infection_relief = bp.get("infection_relief", 0)
    new_infection = max(0, ch["infection"] - infection_relief)
    cures_poison = bp.get("cures_poison", False) and ch["poison_until_ts"] > 0
    run("UPDATE characters SET hp=?, infection=?%s WHERE id=?" % (",poison_until_ts=0" if cures_poison else ""),
        (new_hp, new_infection, ch["id"]))
    parts = []
    if bp["heal"]:
        parts.append(f"回复{bp['heal']}点HP")
    if infection_relief:
        parts.append(f"感染度-{infection_relief}")
    if cures_poison:
        parts.append("解除中毒状态")
    flash(f"用了「{bp['name']}」，{'、'.join(parts)}（自然恢复很慢，医疗用品仍是最快的办法）")
    return redirect(url_for("dashboard"))

# ── 路由:庇护所公开报名(九.5 / 十四.4) ───────────────────────────────────

@app.route("/shelters")
@login_required
@need_character
def shelters_list(ch):
    rows = q("""SELECT s.*, (SELECT COUNT(*) FROM characters c WHERE c.shelter_id=s.id AND c.status='alive') AS member_count
                FROM shelters s WHERE s.abandoned=0 AND s.completed_ending=0 ORDER BY s.id""")
    tiers = SHELTER_TIERS
    return render_template("shelters.html", ch=ch, shelters=rows, tiers=tiers)

@app.route("/shelter/<int:sid>")
@login_required
@need_character
def shelter_showcase(ch, sid):
    shelter = q("SELECT * FROM shelters WHERE id=? AND abandoned=0", (sid,), one=True)
    if not shelter:
        flash("庇护所不存在")
        return redirect(url_for("shelters_list"))
    members = q("""SELECT c.id,c.name,c.level,c.tile_x,c.tile_y,
                          a.custom_name,a.battles_won,cp.nickname,cp.avatar_key
                   FROM characters c
                   LEFT JOIN tamed_animal_profiles a ON a.character_id=c.id
                   LEFT JOIN character_profiles cp ON cp.character_id=c.id
                   WHERE c.shelter_id=? AND c.status='alive' ORDER BY c.level DESC,c.id""", (sid,))
    feed = q("SELECT * FROM shelter_feed WHERE shelter_id=? ORDER BY id DESC LIMIT 12", (sid,))
    visits = q("""SELECT * FROM shelter_visits WHERE shelter_id=?
                  ORDER BY visited_ts DESC LIMIT 12""", (sid,))
    contribution_total = q("""SELECT COALESCE(SUM(points),0) AS t
                              FROM shelter_contributions WHERE shelter_id=?""", (sid,), one=True)["t"]
    life_event = ensure_shelter_life_event(sid, get_world_state()["day_count"])
    life_votes = q("""SELECT option_key,COUNT(*) AS votes FROM shelter_life_votes
                      WHERE event_id=? GROUP BY option_key""", (life_event["id"],))
    my_life_vote = q("""SELECT * FROM shelter_life_votes
                        WHERE event_id=? AND character_id=?""", (life_event["id"], ch["id"]), one=True)
    return render_template("shelter_showcase.html", ch=ch, shelter=shelter, members=members,
                           feed=feed, visits=visits, contribution_total=contribution_total,
                           tiers=SHELTER_TIERS, life_event=life_event,
                           life_event_def=SHELTER_LIFE_EVENT_DEFS[life_event["event_key"]],
                           life_votes={r["option_key"]: r["votes"] for r in life_votes},
                           my_life_vote=my_life_vote)

@app.route("/shelter/<int:sid>/life-event/vote", methods=["POST"])
@login_required
@need_character
def shelter_life_vote(ch, sid):
    event = q("""SELECT * FROM shelter_life_events WHERE shelter_id=? AND status='open'
                 ORDER BY id DESC LIMIT 1""", (sid,), one=True)
    option = request.form.get("option_key")
    if not event or ch["shelter_id"] != sid:
        flash("只有这个庇护所的成员能参与今天的生活事件")
    elif option not in SHELTER_LIFE_EVENT_DEFS[event["event_key"]]["options"]:
        flash("这个选择不存在")
    else:
        cur = run("""INSERT OR IGNORE INTO shelter_life_votes
                     (event_id,character_id,option_key,voted_ts) VALUES(?,?,?,?)""",
                  (event["id"], ch["id"], option, now_ts()))
        if cur.rowcount:
            run("UPDATE characters SET wallet=wallet+2 WHERE id=?", (ch["id"],))
            recreation_gain(ch, 3, "参与庇护所生活事件")
            maybe_create_dynamic_quest(ch["id"], f"shelter:{event['id']}",
                                       "庇护所留下的后续",
                                       f"你在「{event['title']}」中作出选择，接下来为社区带回5份物资。",
                                       "gather", 5, "wallet", 12)
            flash("你的选择已经写进庇护所今日记录，钱包+2，并产生了一条个人后续支线")
        else:
            flash("今天已经回应过这个事件了")
    return redirect(url_for("shelter_showcase", sid=sid))

@app.route("/shelter/<int:sid>/visit", methods=["POST"])
@login_required
@need_character
def shelter_visit(ch, sid):
    shelter = q("SELECT * FROM shelters WHERE id=? AND abandoned=0", (sid,), one=True)
    message = " ".join((request.form.get("message") or "来过，愿你们平安。").strip().split())[:60]
    day = get_world_state()["day_count"]
    if not shelter:
        flash("庇护所不存在")
    else:
        cur = run("""INSERT OR IGNORE INTO shelter_visits
                     (visitor_character_id,shelter_id,day_count,visitor_name,message,visited_ts)
                     VALUES(?,?,?,?,?,?)""", (ch["id"], sid, day, display_name(ch), message, now_ts()))
        if cur.rowcount:
            run("UPDATE characters SET wallet=wallet+2 WHERE id=?", (ch["id"],))
            add_shelter_feed(sid, "chronicle", "访客记录", f"{display_name(ch)} 来访：{message}")
            record_long_progress(ch["id"], "visit", 1)
            record_long_progress(ch["id"], "connection", 1)
            flash("留下了今日访客签名，钱包+2")
        else:
            flash("今天已经来过这个庇护所了")
    return redirect(url_for("shelter_showcase", sid=sid))

@app.route("/shelter/<int:sid>/join", methods=["POST"])
@login_required
@need_character
def shelter_join(ch, sid):
    if ch["shelter_id"]:
        flash("你已经是某个庇护所的成员了,一次只能加入一个(数值设计八节)")
        return redirect(url_for("shelters_list"))
    shelter = q("SELECT * FROM shelters WHERE id=? AND abandoned=0", (sid,), one=True)
    if not shelter:
        flash("庇护所不存在")
        return redirect(url_for("shelters_list"))
    if shelter["completed_ending"]:
        flash("这个庇护所已经完结了,不再接受新成员加入(十二.2)")
        return redirect(url_for("shelters_list"))
    cap = SHELTER_TIERS[shelter["tier"]][0]
    count = q("SELECT COUNT(*) AS c FROM characters WHERE shelter_id=? AND status='alive'", (sid,), one=True)["c"]
    if count >= cap:
        flash("该庇护所已满,可等待成员退出/死亡后的空位再次申请(十四.4)")
        return redirect(url_for("shelters_list"))
    run("UPDATE characters SET shelter_id=? WHERE id=?", (sid, ch["id"]))
    add_shelter_feed(sid, "chronicle", "系统", f"{display_name(ch)} 加入了庇护所。")
    flash(f"已加入庇护所「{shelter['name']}」")
    return redirect(url_for("dashboard"))

@app.route("/shelter/leave", methods=["POST"])
@login_required
@need_character
def shelter_leave(ch):
    if not ch["shelter_id"]:
        return redirect(url_for("dashboard"))
    sid = ch["shelter_id"]
    run("UPDATE characters SET shelter_id=NULL WHERE id=?", (ch["id"],))
    remaining = q("SELECT COUNT(*) AS c FROM characters WHERE shelter_id=? AND status='alive'", (sid,), one=True)["c"]
    if remaining == 0:
        run("UPDATE shelters SET abandoned=1, abandoned_ts=? WHERE id=?", (now_ts(), sid))
    flash("已退出庇护所")
    return redirect(url_for("dashboard"))

@app.route("/action/upgrade_shelter", methods=["POST"])
@login_required
@need_character
def action_upgrade_shelter(ch):
    shelter = _my_shelter_here(ch)
    if not shelter:
        flash("要在自己所属的庇护所地块才能升级")
        return redirect(url_for("dashboard"))
    if shelter["tier"] >= SHELTER_TIER_CAP:
        flash("庇护所已经是顶级了")
        return redirect(url_for("dashboard"))
    next_tier = shelter["tier"] + 1
    cost = SHELTER_UPGRADE_COST[next_tier]
    if shelter["research_points"] < cost["research_points"]:
        flash(f"科研点数不够,升到Lv{next_tier}需要{cost['research_points']}点(打赢丧尸会给+1)")
        return redirect(url_for("dashboard"))
    local_ref = ("shelter_inventory", "shelter_id", shelter["id"])
    if not _has_enough_with_local(ch, cost["materials"], local_ref):
        flash("材料不够(随身+庇护所仓库合计):需要 " + "、".join(f"{RESOURCES[k][0]}{v}" for k, v in cost["materials"].items()))
        return redirect(url_for("dashboard"))
    _deduct_with_local(ch, cost["materials"], local_ref)
    run("""UPDATE shelters SET tier=?, farmland_plots=?, research_points=research_points-? WHERE id=?""",
        (next_tier, next_tier, cost["research_points"], shelter["id"]))
    add_shelter_feed(shelter["id"], "chronicle", "系统",
                     f"{display_name(ch)} 推动庇护所升级到了 Lv{next_tier}。")
    add_shelter_contribution(ch, 30)
    announce(f"🏗️ 庇护所「{shelter['name']}」升级到了Lv{next_tier}。")
    flash(f"庇护所升到Lv{next_tier}了!容纳人数/仓库容量/田地块数都跟着涨了")
    return redirect(url_for("dashboard"))

# ── 路由:仓库存取(个人携带 <-> 房子/庇护所仓库) ───────────────────────────

def _resolve_transfer_target(ch, target):
    """返回(table,id_col,id_val,storage_row,error_message)。storage_row用于算容量上限。"""
    if target == "house":
        house = q("SELECT * FROM houses WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0",
                   (ch["user_id"], ch["tile_x"], ch["tile_y"]), one=True)
        if not house:
            return None, None, None, None, "这里没有你的房子"
        return "house_inventory", "house_id", house["id"], house, None
    if not ch["shelter_id"]:
        return None, None, None, None, "你不是任何庇护所的成员"
    shelter = q("SELECT * FROM shelters WHERE id=?", (ch["shelter_id"],), one=True)
    if shelter["tile_x"] != ch["tile_x"] or shelter["tile_y"] != ch["tile_y"]:
        return None, None, None, None, "要在庇护所所在地块才能存取共享仓库"
    return "shelter_inventory", "shelter_id", shelter["id"], shelter, None

def _transfer_item(ch, table, id_col, id_val, storage_row, resource_key, amount, direction):
    """单件物资的存/取，成功了直接改库并返回(True,消息)；失败不改任何东西，返回(False,原因)。"""
    if amount <= 0 or resource_key not in ITEM_NAMES:
        return False, "参数不对"
    name = ITEM_NAMES[resource_key]
    if direction == "deposit":
        carried_row = q("SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?",
                         (ch["id"], resource_key), one=True)
        carried_amt = carried_row["amount"] if carried_row else 0
        if carried_amt < amount:
            return False, f"身上没有这么多{name}"
        cap = (shelter_inventory_cap_for(storage_row) if table == "shelter_inventory"
              else house_inventory_cap_for(storage_row))
        total = inv_total(table, id_col, id_val)
        if total + amount > cap:
            return False, f"仓库放不下{name}了(容量上限{cap})"
        inv_add("character_inventory", "character_id", ch["id"], resource_key, -amount)
        inv_add(table, id_col, id_val, resource_key, amount)
        if table == "shelter_inventory":
            record_daily_progress(ch["id"], "deposit", amount)
            record_long_progress(ch["id"], "deposit", amount)
            add_shelter_contribution(ch, min(20, amount))
        return True, f"存入{name}x{amount}"
    store_row = q(f"SELECT amount FROM {table} WHERE {id_col}=? AND resource_key=?",
                  (id_val, resource_key), one=True)
    store_amt = store_row["amount"] if store_row else 0
    if store_amt < amount:
        return False, f"仓库里没有这么多{name}"
    cap = char_inv_capacity(ch)
    carried_total = inv_total("character_inventory", "character_id", ch["id"])
    if carried_total + amount > cap:
        return False, f"随身放不下{name}了"
    inv_add(table, id_col, id_val, resource_key, -amount)
    inv_add("character_inventory", "character_id", ch["id"], resource_key, amount)
    return True, f"取出{name}x{amount}"

@app.route("/inventory/transfer", methods=["POST"])
@login_required
@need_character
def inventory_transfer(ch):
    direction = request.form.get("direction")  # deposit / withdraw
    target = request.form.get("target")  # house / shelter
    resource_key = request.form.get("resource_key")
    amount = request.form.get("amount", type=int) or 0
    table, id_col, id_val, storage_row, error = _resolve_transfer_target(ch, target)
    if error:
        flash(error)
        return redirect(url_for("dashboard"))
    ok, message = _transfer_item(ch, table, id_col, id_val, storage_row, resource_key, amount, direction)
    flash(message)
    return redirect(url_for("dashboard"))

@app.route("/inventory/transfer_bulk", methods=["POST"])
@login_required
@need_character
def inventory_transfer_bulk(ch):
    direction = request.form.get("direction")
    target = request.form.get("target")
    keys = request.form.getlist("items")
    table, id_col, id_val, storage_row, error = _resolve_transfer_target(ch, target)
    if error:
        flash(error)
        return redirect(url_for("dashboard"))
    if not keys:
        flash("没有勾选任何东西")
        return redirect(url_for("dashboard"))
    done, failed = [], []
    for key in keys:
        amount = request.form.get(f"amount_{key}", type=int) or 0
        ok, message = _transfer_item(ch, table, id_col, id_val, storage_row, key, amount, direction)
        (done if ok else failed).append(message)
    parts = []
    if done:
        parts.append("成功:" + "、".join(done))
    if failed:
        parts.append("失败:" + "、".join(failed))
    flash("；".join(parts) if parts else "没有任何操作生效")
    return redirect(url_for("dashboard"))

# ── v0.4/0.5:探索事件、世界协作、委托与附近救援 ──────────────────────────

@app.route("/story")
@login_required
@need_character
def story_view(ch):
    run("INSERT OR IGNORE INTO story_states(character_id,chapter,updated_ts) VALUES(?,1,?)",
        (ch["id"], now_ts()))
    ensure_side_quests(ch["id"])
    backfill_story_integration(ch)
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    chapter = STORY_CHAPTERS.get(state["chapter"])
    age_day = survivor_day(ch)
    today_action = q("""SELECT * FROM story_daily_actions
                        WHERE character_id=? AND survivor_day=?""",
                     (ch["id"], age_day), one=True)
    chapter_choice = q("""SELECT * FROM story_choices
                          WHERE character_id=? AND chapter=?""",
                       (ch["id"], state["chapter"]), one=True)
    counters = {r["counter_key"]: r["value"] for r in q(
        "SELECT * FROM story_counters WHERE character_id=?", (ch["id"],))}
    final_blueprint_unlocked = counters.get("northstar_final_blueprint", 0) >= 1
    final_inventory = {
        r["resource_key"]: r["amount"] for r in q(
            "SELECT resource_key,amount FROM character_inventory WHERE character_id=?",
            (ch["id"],))
    }
    requirements = []
    day_ready = bool(chapter and age_day >= chapter["min_day"])
    ready = day_ready and bool(chapter_choice)
    if chapter:
        for key, label, target in chapter["requirements"]:
            value = min(target, counters.get(key, 0))
            requirements.append({"key": key, "label": label, "target": target, "value": value})
            ready = ready and value >= target
    side_rows = q("""SELECT * FROM side_quests WHERE character_id=? AND status='active'
                     ORDER BY id""", (ch["id"],))
    side_quests = [{"row": r, "info": SIDE_QUESTS[r["quest_key"]]} for r in side_rows]
    ws = get_world_state()
    world_goal = ensure_world_goal(ws["day_count"])
    dynamic_quests = q("""SELECT * FROM dynamic_personal_quests
                          WHERE character_id=? AND status='active' ORDER BY id DESC""",
                       (ch["id"],))
    return render_template("story.html", ch=ch, state=state, chapter=chapter,
                           requirements=requirements, ready=ready, side_quests=side_quests,
                           story_chapters=STORY_CHAPTERS, survivor_day=age_day,
                           day_ready=day_ready, today_action=today_action,
                           northstar_actions=NORTHSTAR_ACTIONS,
                           chapter_choice=chapter_choice,
                           choice_options=STORY_CHOICE_OPTIONS.get(state["chapter"], []),
                           daily_plan=daily_plan_for(ch), daily_plans=DAILY_PLANS,
                           daily_goals=daily_goals_for(ch, ws["day_count"]),
                           dynamic_quests=dynamic_quests,
                           world_goal=world_goal, world_goal_def=world_goal_info(world_goal),
                           final_blueprint_unlocked=final_blueprint_unlocked,
                           final_item_key=NORTHSTAR_FINAL_ITEM_KEY,
                           final_item_name=ITEM_NAMES[NORTHSTAR_FINAL_ITEM_KEY],
                           final_cost=NORTHSTAR_FINAL_COST,
                           final_inventory=final_inventory,
                           final_workbench_ready=_workbench_available(ch, "basic"),
                           item_names=ITEM_NAMES,
                           choice_history=q("""SELECT * FROM story_choices
                                              WHERE character_id=? ORDER BY chapter""",
                                            (ch["id"],)))

@app.route("/story/choice", methods=["POST"])
@login_required
@need_character
def story_choice(ch):
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    if not state or state["completed"]:
        return redirect(url_for("story_view"))
    chapter = state["chapter"]
    options = STORY_CHOICE_OPTIONS[chapter]
    choice_key = request.form.get("choice")
    selected = next((o for o in options if o[0] == choice_key), None)
    if not selected:
        flash("这不是当前章节的选择")
    else:
        cur = run("""INSERT OR IGNORE INTO story_choices
                     (character_id,chapter,choice_key,choice_label,trace_text,chosen_ts)
                     VALUES(?,?,?,?,?,?)""",
                  (ch["id"], chapter, selected[0], selected[1], selected[2], now_ts()))
        flash(selected[2] if cur.rowcount else "这一章的选择已经留下，不能重写。")
    return redirect(url_for("story_view"))

@app.route("/story/daily-action", methods=["POST"])
@login_required
@need_character
def story_daily_action(ch):
    run("INSERT OR IGNORE INTO story_states(character_id,chapter,updated_ts) VALUES(?,1,?)",
        (ch["id"], now_ts()))
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    if state["completed"]:
        flash("北辰线路已经恢复，不需要再校准了")
        return redirect(url_for("story_view"))
    age_day = survivor_day(ch)
    chapter = STORY_CHAPTERS[state["chapter"]]
    if age_day < chapter["min_day"]:
        flash(f"这一章最早在幸存第{chapter['min_day']}天开放")
        return redirect(url_for("story_view"))
    choice = request.form.get("choice")
    if choice not in NORTHSTAR_ACTIONS:
        flash("请选择一项北辰个人行动")
        return redirect(url_for("story_view"))
    if q("""SELECT 1 FROM story_daily_actions
            WHERE character_id=? AND survivor_day=?""", (ch["id"], age_day), one=True):
        flash("今天已经完成过一次北辰个人行动，明天再继续校准")
        return redirect(url_for("story_view"))
    reward_key, amount, outcome = random.choice(NORTHSTAR_ACTIONS[choice]["outcomes"])
    cur = run("""INSERT OR IGNORE INTO story_daily_actions
                 (character_id,survivor_day,action_key,outcome_text,created_ts)
                 VALUES(?,?,?,?,?)""", (ch["id"], age_day, choice, outcome, now_ts()))
    if not cur.rowcount:
        flash("今天已经完成过一次北辰个人行动")
        return redirect(url_for("story_view"))
    if reward_key == "wallet":
        run("UPDATE characters SET wallet=wallet+? WHERE id=?", (amount, ch["id"]))
        reward_text = f"钱包货币x{amount}"
    elif inv_total("character_inventory", "character_id", ch["id"]) < char_inv_capacity(ch):
        inv_add("character_inventory", "character_id", ch["id"], reward_key, amount)
        reward_text = f"{ITEM_NAMES[reward_key]}x{amount}"
    else:
        run("UPDATE characters SET wallet=wallet+3 WHERE id=?", (ch["id"],))
        reward_text = "背包已满，改为钱包货币x3"
    record_long_progress(ch["id"], "northstar_action", 1)
    record_daily_progress(ch["id"], "northstar", 1)
    grant_xp(ch, 5)
    log_action(ch["id"], "northstar_action", choice)
    flash(f"{outcome} 获得{reward_text}，经验+5。")
    return redirect(url_for("story_view"))

@app.route("/story/confront", methods=["POST"])
@login_required
@need_character
def story_confront(ch):
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    counters = {r["counter_key"]: r["value"] for r in q(
        "SELECT * FROM story_counters WHERE character_id=?", (ch["id"],))}
    if not state or state["completed"] or state["chapter"] < 7:
        flash("北辰还没有给出守门尸群的位置")
    elif ch["pending_zombie_type"]:
        return redirect(url_for("encounter"))
    elif counters.get("combat", 0) >= (3 if state["chapter"] == 8 else 1):
        flash("这一章需要清理的尸群已经处理完了")
    else:
        ztype = "normal"
        strength = max(8, int(10 + survivor_day(ch) * .3))
        run("""UPDATE characters SET pending_zombie_type=?,pending_zombie_hp=?
               WHERE id=?""", (ztype, strength, ch["id"]))
        log_action(ch["id"], "story_confront", f"chapter {state['chapter']}")
        flash("你沿北辰标出的路线找到了守门尸群。可以战斗，也可以撤退准备后再来。")
        return redirect(url_for("encounter"))
    return redirect(url_for("story_view"))

@app.route("/story/advance", methods=["POST"])
@login_required
@need_character
def story_advance(ch):
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    if not state or state["completed"]:
        return redirect(url_for("story_view"))
    chapter = STORY_CHAPTERS[state["chapter"]]
    if survivor_day(ch) < chapter["min_day"]:
        flash(f"这一章最早在幸存第{chapter['min_day']}天解锁")
        return redirect(url_for("story_view"))
    counters = {r["counter_key"]: r["value"] for r in q(
        "SELECT * FROM story_counters WHERE character_id=?", (ch["id"],))}
    if not q("""SELECT 1 FROM story_choices WHERE character_id=? AND chapter=?""",
             (ch["id"], state["chapter"]), one=True):
        flash("先做出这一章的决定，它会留在最终广播里")
        return redirect(url_for("story_view"))
    if any(counters.get(key, 0) < target for key, _, target in chapter["requirements"]):
        flash("本章目标还没有全部完成")
        return redirect(url_for("story_view"))
    if state["chapter"] >= max(STORY_CHAPTERS) and counters.get("northstar_final_blueprint", 0) >= 1:
        flash("终章已经完成，北辰归航信标设计图在等你组装")
        return redirect(url_for("story_view"))
    run("UPDATE characters SET wallet=wallet+25 WHERE id=?", (ch["id"],))
    fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
    grant_xp(fresh, 20)
    if state["chapter"] >= max(STORY_CHAPTERS):
        run("""INSERT INTO story_counters(character_id,counter_key,value)
               VALUES(?,'northstar_final_blueprint',1)
               ON CONFLICT(character_id,counter_key) DO UPDATE SET value=1""",
            (ch["id"],))
        run("UPDATE story_states SET updated_ts=? WHERE character_id=?",
            (now_ts(), ch["id"]))
        log_action(ch["id"], "northstar_blueprint", "完成八章并取得北辰归航信标设计图")
        flash("八章广播已经全部完成：钱包+25、经验+20。你取得了「北辰归航信标」设计图；真正组装出信标后才算通关。")
    else:
        run("UPDATE story_states SET chapter=chapter+1,updated_ts=? WHERE character_id=?",
            (now_ts(), ch["id"]))
        flash("主线章节完成：钱包+25、经验+20。新的广播内容已经解锁。")
    return redirect(url_for("story_view"))

@app.route("/story/assemble-final", methods=["POST"])
@login_required
@need_character
def story_assemble_final(ch):
    state = q("SELECT * FROM story_states WHERE character_id=?", (ch["id"],), one=True)
    blueprint = q("""SELECT value FROM story_counters
                     WHERE character_id=? AND counter_key='northstar_final_blueprint'""",
                  (ch["id"],), one=True)
    if not state or state["completed"]:
        return redirect(url_for("story_view"))
    if state["chapter"] < max(STORY_CHAPTERS) or not blueprint or blueprint["value"] < 1:
        flash("先完成北辰八章，才能取得归航信标设计图")
        return redirect(url_for("story_view"))
    if not _workbench_available(ch, "basic"):
        flash("组装归航信标需要当前位置的基础工作台(房子或所属庇护所)")
        return redirect(url_for("story_view"))
    _, _, northstar_local_ref = _workbench_local_ref(ch, "basic")
    if not _has_enough_with_local(ch, NORTHSTAR_FINAL_COST, northstar_local_ref):
        flash("信标材料不足(随身+当前仓库合计)：需要" + "、".join(
            f"{ITEM_NAMES[k]}x{v}" for k, v in NORTHSTAR_FINAL_COST.items()))
        return redirect(url_for("story_view"))
    _deduct_with_local(ch, NORTHSTAR_FINAL_COST, northstar_local_ref)
    inv_add("character_inventory", "character_id", ch["id"], NORTHSTAR_FINAL_ITEM_KEY, 1)
    run("UPDATE story_states SET completed=1,updated_ts=? WHERE character_id=?",
        (now_ts(), ch["id"]))
    run("""INSERT OR IGNORE INTO shelter_reward_unlocks(character_id,reward_key,unlocked_ts)
           VALUES(?,'northstar_title',?)""", (ch["id"], now_ts()))
    record_long_progress(ch["id"], "prepare", 1)
    award_tag(ch["id"], "northstar")
    final_choice = q("""SELECT * FROM story_choices
                        WHERE character_id=? AND chapter=8""", (ch["id"],), one=True)
    ending = ("把北辰变成了向所有幸存者开放的灯塔"
              if final_choice and final_choice["choice_key"] == "broadcast"
              else "让北辰在归途频道为仍在寻找彼此的人守夜")
    album_add(ch["id"], "northstar", "北辰归航信标",
              f"{display_name(ch)}亲手组装了归航信标，{ending}。")
    announce(f"📡 {display_name(ch)} 组装出北辰归航信标，{ending}。")
    flash(f"📡 北辰归航信标开始工作。你正式完成个人主线，{ending}，称号「北辰联络员」已记录。")
    return redirect(url_for("story_view"))

@app.route("/side-quest/<int:quest_id>/claim", methods=["POST"])
@login_required
@need_character
def side_quest_claim(ch, quest_id):
    row = q("""SELECT * FROM side_quests WHERE id=? AND character_id=? AND status='active'""",
            (quest_id, ch["id"]), one=True)
    if not row or row["progress"] < row["target"]:
        flash("支线任务还没有完成")
    else:
        cur = run("""UPDATE side_quests SET status='claimed',completed_ts=?
                     WHERE id=? AND status='active'""", (now_ts(), quest_id))
        if cur.rowcount:
            wallet_reward = 12 if has_trait(ch, "storyteller") else 10
            run("UPDATE characters SET wallet=wallet+? WHERE id=?", (wallet_reward, ch["id"]))
            fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
            grant_xp(fresh, 5)
            ensure_side_quests(ch["id"])
            flash(f"支线完成：钱包+{wallet_reward}、经验+5，并补充了一条新支线")
    return redirect(url_for("story_view"))

@app.route("/side-quest/<int:quest_id>/reroll", methods=["POST"])
@login_required
@need_character
def side_quest_reroll(ch, quest_id):
    age_day = survivor_day(ch)
    row = q("""SELECT * FROM side_quests WHERE id=? AND character_id=? AND status='active'""",
            (quest_id, ch["id"]), one=True)
    if not row:
        flash("这条支线已经不在任务栏里")
    elif q("""SELECT 1 FROM side_quest_rerolls
              WHERE character_id=? AND survivor_day=?""", (ch["id"], age_day), one=True):
        flash("今天已经换过一条支线了")
    else:
        run("""INSERT INTO side_quest_rerolls
               (character_id,survivor_day,old_quest_key,created_ts) VALUES(?,?,?,?)""",
            (ch["id"], age_day, row["quest_key"], now_ts()))
        run("""UPDATE side_quests SET status='dismissed',completed_ts=?
               WHERE id=? AND status='active'""", (now_ts(), quest_id))
        ensure_side_quests(ch["id"], exclude=(row["quest_key"],))
        flash("这条支线已收起并换成新线索；没有奖励，也没有惩罚")
    return redirect(url_for("story_view"))

@app.route("/fortune/draw", methods=["POST"])
@login_required
@need_character
def fortune_draw(ch):
    day = get_world_state()["day_count"]
    style = request.form.get("style")
    if style not in ("steady", "bold"):
        flash("请选择一种搜寻方式")
        return redirect(url_for("dashboard"))
    if q("""SELECT 1 FROM daily_fortune_draws
            WHERE character_id=? AND day_count=?""", (ch["id"], day), one=True):
        flash("今天已经试过手气了")
        return redirect(url_for("dashboard"))
    if style == "steady":
        key, amount, text = random.choice(FORTUNE_RESULTS["steady"])
        result_key = "steady"
    else:
        rare_chance = min(0.40, 0.08 + ch["stat_luck"] * 0.015
                          + (0.05 if has_trait(ch, "optimist") else 0))
        rare = random.random() < rare_chance
        key, amount, text = random.choice(FORTUNE_RESULTS["bold_rare" if rare else "bold_common"])
        result_key = "bold_rare" if rare else "bold_common"
    cur = run("""INSERT OR IGNORE INTO daily_fortune_draws
                 (character_id,day_count,style,result_key,result_text,created_ts)
                 VALUES(?,?,?,?,?,?)""",
              (ch["id"], day, style, result_key, text, now_ts()))
    if not cur.rowcount:
        flash("今天已经试过手气了")
        return redirect(url_for("dashboard"))
    record_long_progress(ch["id"], "fortune", 1)
    record_daily_progress(ch["id"], "fortune", 1)
    inv_add("character_inventory", "character_id", ch["id"], key, amount)
    shared = random.random() < min(0.25, 0.15 + ch["stat_luck"] * 0.005)
    shared_text = ""
    if shared:
        others = q("SELECT id,name FROM characters WHERE status='alive' AND id<>?", (ch["id"],))
        if others:
            other = random.choice(others)
            inv_add("character_inventory", "character_id", other["id"], "emergency_food", 1)
            announce(f"🍀 {display_name(ch)} 的好运顺着无线电传给了{display_name(other)}，对方收到一份应急食品。")
            shared_text = f" 好运还传给了{other['name']}！"
    if result_key == "bold_rare":
        announce(f"✨ {display_name(ch)} 冒险搜寻时走了大运：{text}")
    flash(f"{text} 获得{ITEM_NAMES[key]}x{amount}。{shared_text}")
    return redirect(url_for("dashboard"))

@app.route("/world-event")
@login_required
@need_character
def world_event(ch):
    row = q("SELECT * FROM pending_world_events WHERE character_id=?", (ch["id"],), one=True)
    if not row:
        return redirect(url_for("dashboard"))
    return render_template("world_event.html", ch=ch, event=WORLD_EVENTS[row["event_key"]],
                           event_key=row["event_key"])

@app.route("/world-event/choose", methods=["POST"])
@login_required
@need_character
def world_event_choose(ch):
    row = q("SELECT * FROM pending_world_events WHERE character_id=?", (ch["id"],), one=True)
    if not row:
        return redirect(url_for("dashboard"))
    choice = request.form.get("choice")
    allowed = {k for k, _ in WORLD_EVENTS[row["event_key"]]["choices"]}
    if choice not in allowed:
        flash("没有这个选择")
        return redirect(url_for("world_event"))
    run("DELETE FROM pending_world_events WHERE character_id=?", (ch["id"],))
    if choice == "leave":
        flash("你压下好奇心，安全离开了。")
        return redirect(url_for("dashboard"))
    stat = "stat_str" if choice in ("force", "quick") else ("stat_int" if choice in ("inspect", "decode", "careful") else "stat_luck")
    chance = min(0.9, 0.50 + ch[stat] * 0.025)
    if has_trait(ch, "brave"):
        chance = min(0.95, chance + 0.05)
    if random.random() < chance:
        rewards = {
            "locked_store": ("emergency_food", random.randint(1, 2)),
            "radio_signal": ("parts", random.randint(2, 5)),
            "field_cache": ("bandage", random.randint(1, 2)),
        }
        key, amount = rewards[row["event_key"]]
        inv_add("character_inventory", "character_id", ch["id"], key, amount)
        grant_xp(ch, 4)
        log_action(ch["id"], "world_event", f"{row['event_key']}:success")
        record_long_progress(ch["id"], "world_event", 1)
        flash(f"判断正确！获得{ITEM_NAMES[key]} x{amount}，经验+4")
    else:
        damage = random.randint(4, 10)
        apply_damage(ch, damage)
        log_action(ch["id"], "world_event", f"{row['event_key']}:failed")
        record_long_progress(ch["id"], "world_event", 1)
        flash(f"判断失误，受了{damage}点伤；所幸及时撤了出来。")
    return redirect(url_for("dashboard"))

@app.route("/community")
@login_required
@need_character
def community(ch):
    ws = get_world_state()
    goal = ensure_world_goal(ws["day_count"])
    info = world_goal_info(goal)
    radio_event = ensure_radio_event()
    radio_progress = None
    if radio_event:
        run("""INSERT OR IGNORE INTO radio_event_progress(event_id,character_id,rolls_day)
               VALUES(?,?,?)""", (radio_event["id"], ch["id"], ws["day_count"]))
        run("""UPDATE radio_event_progress SET rolls_day=?,rolls_used=0
               WHERE event_id=? AND character_id=? AND rolls_day<>?""",
            (ws["day_count"], radio_event["id"], ch["id"], ws["day_count"]))
        radio_progress = q("""SELECT * FROM radio_event_progress
                              WHERE event_id=? AND character_id=?""",
                           (radio_event["id"], ch["id"]), one=True)
    disaster = ensure_world_disaster(ws["day_count"])
    disaster_progress = q("""SELECT * FROM disaster_contributions
                              WHERE cycle_id=? AND character_id=? AND day_count=?""",
                           (disaster["cycle_id"], ch["id"], ws["day_count"]), one=True)
    contribution_points = 0
    if ch["shelter_id"]:
        row = q("""SELECT points FROM shelter_contributions
                   WHERE character_id=? AND shelter_id=?""",
                (ch["id"], ch["shelter_id"]), one=True)
        contribution_points = row["points"] if row else 0
    reward_unlocks = {r["reward_key"] for r in q(
        "SELECT reward_key FROM shelter_reward_unlocks WHERE character_id=?", (ch["id"],))}
    news = q("SELECT * FROM world_news ORDER BY day_count DESC,id DESC LIMIT 12")
    commissions = q("SELECT * FROM commissions WHERE status='open' ORDER BY id DESC LIMIT 30")
    return render_template("community.html", ch=ch, goal=goal, goal_info=info, news=news,
                           commissions=commissions, item_names=ITEM_NAMES,
                           resources=RESOURCES, commission_resources=SELLABLE_RESOURCES,
                           contribution_points=contribution_points, shelter_rewards=SHELTER_REWARDS,
                           reward_unlocks=reward_unlocks, radio_event=radio_event,
                           radio_progress=radio_progress, radio_rolls_per_day=RADIO_ROLLS_PER_DAY,
                           radio_board_length=RADIO_BOARD_LENGTH, now_ts=now_ts(),
                           disaster=disaster, disaster_progress=disaster_progress,
                           disaster_actions_per_day=DISASTER_ACTIONS_PER_DAY)

@app.route("/world-goal/contribute", methods=["POST"])
@login_required
@need_character
def world_goal_contribute(ch):
    goal = ensure_world_goal(get_world_state()["day_count"])
    key = goal["resource_key"]
    amount = max(0, min(50, request.form.get("amount", type=int) or 0))
    if goal["completed"] or not key:
        flash("当前目标不接受物资提交")
        return redirect(url_for("community"))
    have = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key=?""", (ch["id"], key), one=True)
    amount = min(amount, goal["target"] - goal["progress"])
    if amount <= 0 or not have or have["amount"] < amount:
        flash("物资数量不足或参数不正确")
        return redirect(url_for("community"))
    inv_add("character_inventory", "character_id", ch["id"], key, -amount)
    add_world_goal_progress(goal["goal_key"], amount)
    record_long_progress(ch["id"], "world_goal", amount)
    add_shelter_contribution(ch, min(25, amount))
    log_action(ch["id"], "world_goal", f"{key} x{amount}")
    flash(f"向全服目标贡献了{ITEM_NAMES[key]} x{amount}")
    return redirect(url_for("community"))

@app.route("/shelter-reward/<reward_key>/redeem", methods=["POST"])
@login_required
@need_character
def shelter_reward_redeem(ch, reward_key):
    reward = SHELTER_REWARDS.get(reward_key)
    if not reward or not ch["shelter_id"]:
        flash("无法兑换这个奖励")
        return redirect(url_for("community"))
    row = q("""SELECT points FROM shelter_contributions
               WHERE character_id=? AND shelter_id=?""",
            (ch["id"], ch["shelter_id"]), one=True)
    points = row["points"] if row else 0
    owned = q("""SELECT 1 FROM shelter_reward_unlocks
                 WHERE character_id=? AND reward_key=?""", (ch["id"], reward_key), one=True)
    if owned and not reward["repeatable"]:
        flash("这个纪念奖励已经兑换过了")
    elif points < reward["cost"]:
        flash("庇护所贡献不够")
    else:
        run("""UPDATE shelter_contributions SET points=points-?
               WHERE character_id=? AND shelter_id=?""",
            (reward["cost"], ch["id"], ch["shelter_id"]))
        if reward_key == "supply_pack":
            inv_add("character_inventory", "character_id", ch["id"], "emergency_food", 3)
        else:
            run("""INSERT OR IGNORE INTO shelter_reward_unlocks(character_id,reward_key,unlocked_ts)
                   VALUES(?,?,?)""", (ch["id"], reward_key, now_ts()))
        flash(f"兑换了{reward['name']}")
    return redirect(url_for("community"))

@app.route("/radio-event/roll", methods=["POST"])
@login_required
@need_character
def radio_event_roll(ch):
    event = ensure_radio_event()
    if not event:
        flash("无线电寻宝暂未开放")
        return redirect(url_for("community"))
    day = get_world_state()["day_count"]
    run("INSERT OR IGNORE INTO radio_event_progress(event_id,character_id,rolls_day) VALUES(?,?,?)",
        (event["id"], ch["id"], day))
    run("""UPDATE radio_event_progress SET rolls_day=?,rolls_used=0
           WHERE event_id=? AND character_id=? AND rolls_day<>?""",
        (day, event["id"], ch["id"], day))
    progress = q("""SELECT * FROM radio_event_progress
                    WHERE event_id=? AND character_id=?""", (event["id"], ch["id"]), one=True)
    if progress["finished"]:
        flash("你已经抵达本届寻宝终点")
    elif progress["rolls_used"] >= RADIO_ROLLS_PER_DAY:
        flash("今天的6次行动已经用完，明天再来")
    else:
        step = random.randint(1, 6)
        if step == 1 and has_trait(ch, "radio_mind"):
            step = 2
        new_pos = min(RADIO_BOARD_LENGTH, progress["position"] + step)
        run("""UPDATE radio_event_progress SET position=?,rolls_used=rolls_used+1
               WHERE event_id=? AND character_id=?""", (new_pos, event["id"], ch["id"]))
        record_long_progress(ch["id"], "radio", 1)
        reward_text = ""
        if new_pos % 7 == 0:
            inv_add("character_inventory", "character_id", ch["id"], "parts", 2)
            reward_text = "，从信号缓存中找到机械零件x2"
        elif new_pos % 5 == 0:
            run("UPDATE characters SET wallet=wallet+5 WHERE id=?", (ch["id"],))
            reward_text = "，捡到5钱包货币"
        if new_pos >= RADIO_BOARD_LENGTH:
            run("""UPDATE radio_event_progress SET finished=1
                   WHERE event_id=? AND character_id=?""", (event["id"], ch["id"]))
            run("UPDATE characters SET wallet=wallet+50 WHERE id=?", (ch["id"],))
            run("""INSERT OR IGNORE INTO shelter_reward_unlocks(character_id,reward_key,unlocked_ts)
                   VALUES(?,'radio_trophy',?)""", (ch["id"], now_ts()))
            announce(f"📻 {display_name(ch)} 抵达无线电寻宝终点，获得纪念奖杯。")
            reward_text += "，抵达终点并获得50钱包货币与纪念奖杯"
        flash(f"无线电指引你前进了{step}格，来到{new_pos}/{RADIO_BOARD_LENGTH}{reward_text}")
    return redirect(url_for("community"))

@app.route("/disaster/action", methods=["POST"])
@login_required
@need_character
def disaster_action(ch):
    day = get_world_state()["day_count"]
    disaster = ensure_world_disaster(day)
    kind = request.form.get("kind")
    if disaster["status"] != "active" or kind not in ("fight", "supply", "medical", "scout"):
        flash("当前无法进行这项灾害行动")
        return redirect(url_for("community"))
    row = q("""SELECT * FROM disaster_contributions
               WHERE cycle_id=? AND character_id=? AND day_count=?""",
            (disaster["cycle_id"], ch["id"], day), one=True)
    if row and row["actions_used"] >= DISASTER_ACTIONS_PER_DAY:
        flash("今天的灾害参与次数已经用完")
        return redirect(url_for("community"))
    costs = {"supply": ("ammo", 2), "medical": ("herb", 2)}
    if kind in costs:
        key, amount = costs[kind]
        have = q("""SELECT amount FROM character_inventory
                    WHERE character_id=? AND resource_key=?""", (ch["id"], key), one=True)
        if not have or have["amount"] < amount:
            flash(f"需要{ITEM_NAMES[key]}x{amount}")
            return redirect(url_for("community"))
        inv_add("character_inventory", "character_id", ch["id"], key, -amount)
    stat_points = {
        "fight": ch["stat_str"], "supply": ch["stat_int"],
        "medical": ch["stat_int"], "scout": max(ch["stat_spd"], ch["stat_luck"]),
    }
    points = 10 + stat_points[kind] * 2
    run("""INSERT INTO disaster_contributions(cycle_id,character_id,day_count,actions_used,total_points)
           VALUES(?,?,?,1,?)
           ON CONFLICT(cycle_id,character_id,day_count)
           DO UPDATE SET actions_used=actions_used+1,total_points=total_points+excluded.total_points""",
        (disaster["cycle_id"], ch["id"], day, points))
    cur = run("""UPDATE world_disasters SET hp=MAX(0,hp-?)
                 WHERE cycle_id=? AND status='active'""", (points, disaster["cycle_id"]))
    add_shelter_contribution(ch, max(2, points // 5))
    record_long_progress(ch["id"], "disaster", 1)
    fresh = q("SELECT * FROM world_disasters WHERE cycle_id=?", (disaster["cycle_id"],), one=True)
    labels = {"fight": "正面战斗", "supply": "运送弹药", "medical": "救治伤员", "scout": "侦查弱点"}
    if cur.rowcount and fresh["hp"] <= 0:
        run("UPDATE world_disasters SET status='defeated' WHERE cycle_id=?", (disaster["cycle_id"],))
        run("UPDATE characters SET wallet=wallet+20 WHERE status='alive'")
        announce(f"🌟 全服合力解决了{disaster['name']}，所有当前幸存者获得20钱包货币。")
        flash(f"{labels[kind]}贡献{points}点，灾害被彻底解决了！")
    else:
        flash(f"{labels[kind]}贡献{points}点，灾害剩余{fresh['hp']}/{fresh['max_hp']}")
    return redirect(url_for("community"))

@app.route("/commission/create", methods=["POST"])
@login_required
@need_character
def commission_create(ch):
    key = request.form.get("resource_key")
    amount = max(0, min(100, request.form.get("amount", type=int) or 0))
    reward = max(0, min(1000, request.form.get("reward", type=int) or 0))
    if key not in SELLABLE_RESOURCES or amount <= 0 or reward <= 0:
        flash("委托内容不正确")
    elif ch["wallet"] < reward:
        flash("钱包不够，委托报酬会在发布时由系统托管")
    else:
        run("UPDATE characters SET wallet=wallet-? WHERE id=?", (reward, ch["id"]))
        run("""INSERT INTO commissions(creator_character_id,creator_name,resource_key,amount,reward,created_ts)
               VALUES(?,?,?,?,?,?)""", (ch["id"], display_name(ch), key, amount, reward, now_ts()))
        flash("委托已发布，报酬已交由系统托管")
    return redirect(url_for("community"))

@app.route("/commission/<int:commission_id>/complete", methods=["POST"])
@login_required
@need_character
def commission_complete(ch, commission_id):
    row = q("SELECT * FROM commissions WHERE id=? AND status='open'", (commission_id,), one=True)
    if not row:
        flash("委托已经失效")
        return redirect(url_for("community"))
    if row["creator_character_id"] == ch["id"]:
        flash("不能完成自己发布的委托")
        return redirect(url_for("community"))
    creator = q("SELECT * FROM characters WHERE id=? AND status='alive'",
                (row["creator_character_id"],), one=True)
    have = q("""SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?""",
             (ch["id"], row["resource_key"]), one=True)
    if not creator:
        flash("发布者已经不在了，请等待委托取消退款")
    elif not have or have["amount"] < row["amount"]:
        flash("你身上没有足够的委托物资")
    else:
        cur = run("""UPDATE commissions SET status='completed',completed_by=?,completed_by_name=?,completed_ts=?
                     WHERE id=? AND status='open'""",
                  (ch["id"], display_name(ch), now_ts(), commission_id))
        if cur.rowcount:
            inv_add("character_inventory", "character_id", ch["id"], row["resource_key"], -row["amount"])
            inv_add("character_inventory", "character_id", creator["id"], row["resource_key"], row["amount"])
            run("UPDATE characters SET wallet=wallet+? WHERE id=?", (row["reward"], ch["id"]))
            record_long_progress(ch["id"], "commission", 1)
            record_long_progress(ch["id"], "connection", 1)
            flash(f"委托完成，获得{row['reward']}钱包货币")
    return redirect(url_for("community"))

@app.route("/commission/<int:commission_id>/cancel", methods=["POST"])
@login_required
@need_character
def commission_cancel(ch, commission_id):
    row = q("""SELECT * FROM commissions WHERE id=? AND creator_character_id=? AND status='open'""",
            (commission_id, ch["id"]), one=True)
    if row:
        cur = run("UPDATE commissions SET status='cancelled' WHERE id=? AND status='open'", (commission_id,))
        if cur.rowcount:
            run("UPDATE characters SET wallet=wallet+? WHERE id=?", (row["reward"], ch["id"]))
            flash("委托已取消，托管报酬已经退回")
    else:
        flash("不能取消这个委托")
    return redirect(url_for("community"))

@app.route("/rescue/request", methods=["POST"])
@login_required
@need_character
def rescue_request(ch):
    existing = q("""SELECT 1 FROM rescue_signals
                    WHERE requester_character_id=? AND status='open'""", (ch["id"],), one=True)
    message = " ".join((request.form.get("message") or "需要药品救援").strip().split())[:80]
    if ch["hp"] > 40 and ch["infection"] < 60:
        flash("只有重伤或感染度较高时才能发出救援信号")
    elif existing:
        flash("你已经有一个正在广播的救援信号")
    else:
        run("""INSERT INTO rescue_signals(requester_character_id,requester_name,tile_x,tile_y,message,created_ts)
               VALUES(?,?,?,?,?,?)""",
            (ch["id"], display_name(ch), ch["tile_x"], ch["tile_y"], message, now_ts()))
        flash("救援信号已发出，视野范围内的玩家能在大地图看到你")
    return redirect(url_for("map_view"))

@app.route("/rescue/<int:signal_id>/complete", methods=["POST"])
@login_required
@need_character
def rescue_complete(ch, signal_id):
    sig = q("SELECT * FROM rescue_signals WHERE id=? AND status='open'", (signal_id,), one=True)
    item = request.form.get("item_key")
    delivery = request.form.get("delivery", "use_now")  # use_now(当场用掉治疗) / give_item(放进对方背包)
    if not sig:
        flash("救援信号已经结束")
    elif sig["requester_character_id"] == ch["id"]:
        flash("不能救援自己")
    elif (sig["tile_x"], sig["tile_y"]) != (ch["tile_x"], ch["tile_y"]):
        flash("需要先移动到求救者所在坐标")
    elif item not in ("bandage", "first_aid"):
        flash("请选择要送出的医疗用品")
    elif delivery not in ("use_now", "give_item"):
        flash("请选择救援方式")
    else:
        have = q("""SELECT amount FROM character_inventory WHERE character_id=? AND resource_key=?""",
                 (ch["id"], item), one=True)
        target = q("SELECT * FROM characters WHERE id=? AND status='alive'",
                   (sig["requester_character_id"],), one=True)
        if not have or have["amount"] <= 0 or not target:
            flash("医疗用品不足，或求救者已经不在了")
        else:
            cur = run("""UPDATE rescue_signals SET status='completed',responder_character_id=?,
                         responder_name=?,completed_ts=? WHERE id=? AND status='open'""",
                      (ch["id"], display_name(ch), now_ts(), signal_id))
            if cur.rowcount:
                inv_add("character_inventory", "character_id", ch["id"], item, -1)
                item_name = BLUEPRINTS[item]["name"]
                if delivery == "give_item" and (inv_total("character_inventory", "character_id", target["id"])
                                                < char_inv_capacity(target)):
                    inv_add("character_inventory", "character_id", target["id"], item, 1)
                    delivery_note = f"把{item_name}放进了对方背包,留给对方自己决定什么时候用"
                    mail_body = f"{display_name(ch)}在你受伤求救时赶到,把{item_name}放进了你的背包,记得自己用。"
                else:
                    if delivery == "give_item":
                        delivery_note_full = "对方背包已经满了,东西没法塞进去,只能当场用掉"
                    heal = BLUEPRINTS[item]["heal"] + (10 if has_trait(ch, "field_medic") else 0)
                    run("UPDATE characters SET hp=MIN(100,hp+?) WHERE id=?", (heal, target["id"]))
                    treated = treat_injuries(target["id"], item)
                    delivery_note = ((delivery_note_full + f",HP+{heal}") if delivery == "give_item"
                                     else f"当场用{item_name}处理了伤势,HP+{heal}")
                    mail_body = (f"{display_name(ch)}在你受伤求救时赶到,当场用{item_name}帮你处理了伤势,HP+{heal}"
                                 f"{f'，处理了{treated}处伤势' if treated else ''}。")
                send_system_mail(target["id"], "系统", "🆘 收到救援", mail_body)
                run("UPDATE characters SET wallet=wallet+10 WHERE id=?", (ch["id"],))
                add_shelter_contribution(ch, 20 if has_trait(ch, "community") else 15)
                record_long_progress(ch["id"], "rescue", 1)
                record_long_progress(ch["id"], "connection", 1)
                award_tag(ch["id"], "rescuer", display_name(target))
                add_bond_affinity(ch["id"], target["id"], 10)
                run("UPDATE family_heirlooms SET rescue_count=rescue_count+1 WHERE owner_character_id=?",
                    (ch["id"],))
                remember_location(ch["id"], ch["tile_x"], ch["tile_y"],
                                  f"你在这里救援了{display_name(target)}。")
                announce(f"🆘 {display_name(ch)} 在坐标({ch['tile_x']},{ch['tile_y']})救援了{display_name(target)}。")
                run("""INSERT OR IGNORE INTO world_news(day_count,title,content,created_ts)
                       VALUES(?,?,?,?)""",
                    (get_world_state()["day_count"], "附近救援",
                     f"{display_name(ch)} 在坐标({ch['tile_x']},{ch['tile_y']})救援了{display_name(target)}。", now_ts()))
                flash(f"救援完成！{delivery_note}；你获得10钱包货币，对方已经收到邮件提醒")
            else:
                flash("另一名玩家刚刚先完成了这次救援")
    return redirect(url_for("map_view"))

@app.route("/rescue/<int:signal_id>/cancel", methods=["POST"])
@login_required
@need_character
def rescue_cancel(ch, signal_id):
    cur = run("""UPDATE rescue_signals SET status='cancelled',completed_ts=?
                 WHERE id=? AND requester_character_id=? AND status='open'""",
              (now_ts(), signal_id, ch["id"]))
    flash("救援信号已取消" if cur.rowcount else "这个信号不能取消")
    return redirect(url_for("map_view"))

# ── v0.3:日目标领取 / 庇护所留言与共同晚餐 ───────────────────────────────

@app.route("/daily-goal/<goal_key>/claim", methods=["POST"])
@login_required
@need_character
def daily_goal_claim(ch, goal_key):
    day = get_world_state()["day_count"]
    if goal_key not in active_daily_goal_keys(ch["id"], day):
        flash("这不是你今天的目标")
        return redirect(url_for("dashboard"))
    info = DAILY_GOALS[goal_key]
    row = q("""SELECT * FROM daily_goal_progress
               WHERE character_id=? AND day_count=? AND goal_key=?""",
            (ch["id"], day, goal_key), one=True)
    if not row or row["progress"] < info["target"]:
        flash("目标还没有完成")
        return redirect(url_for("dashboard"))
    if row["claimed"]:
        flash("这份奖励已经领过了")
        return redirect(url_for("dashboard"))
    cur = run("""UPDATE daily_goal_progress SET claimed=1
                 WHERE character_id=? AND day_count=? AND goal_key=? AND claimed=0""",
              (ch["id"], day, goal_key))
    if cur.rowcount:
        run("UPDATE characters SET wallet=wallet+? WHERE id=?",
            (DAILY_GOAL_WALLET_REWARD, ch["id"]))
        fresh = q("SELECT * FROM characters WHERE id=?", (ch["id"],), one=True)
        grant_xp(fresh, DAILY_GOAL_XP_REWARD)
        flash(f"目标完成：钱包+{DAILY_GOAL_WALLET_REWARD}、经验+{DAILY_GOAL_XP_REWARD}")
    return redirect(url_for("dashboard"))

@app.route("/shelter/message", methods=["POST"])
@login_required
@need_character
def shelter_message(ch):
    content = " ".join((request.form.get("content") or "").strip().split())
    if not ch["shelter_id"]:
        flash("先加入一个庇护所")
    elif not content:
        flash("留言不能为空")
    elif len(content) > 100:
        flash("留言最多100个字")
    else:
        add_shelter_feed(ch["shelter_id"], "message", display_name(ch), content, ch["id"])
        flash("留言已经贴到庇护所公告板")
    return redirect(url_for("dashboard"))

@app.route("/shelter/feast/contribute", methods=["POST"])
@login_required
@need_character
def shelter_feast_contribute(ch):
    shelter = _my_shelter_here(ch)
    amount = max(0, min(20, request.form.get("amount", type=int) or 0))
    if not shelter:
        flash("要在自己所属的庇护所才能参加共同晚餐")
        return redirect(url_for("dashboard"))
    day = get_world_state()["day_count"]
    members = q("SELECT COUNT(*) AS c FROM characters WHERE shelter_id=? AND status='alive'",
                (shelter["id"],), one=True)["c"]
    target = max(6, members * 3)
    run("INSERT OR IGNORE INTO shelter_feasts(shelter_id,day_count,target) VALUES(?,?,?)",
        (shelter["id"], day, target))
    feast = q("SELECT * FROM shelter_feasts WHERE shelter_id=? AND day_count=?",
              (shelter["id"], day), one=True)
    if feast["completed"]:
        flash("今天的共同晚餐已经开过了")
        return redirect(url_for("dashboard"))
    have = q("""SELECT amount FROM character_inventory
                WHERE character_id=? AND resource_key='raw_food'""", (ch["id"],), one=True)
    amount = min(amount, feast["target"] - feast["contributed"])
    if amount <= 0 or not have or have["amount"] < amount:
        flash("生鲜数量不够，或捐献数量不正确")
        return redirect(url_for("dashboard"))
    inv_add("character_inventory", "character_id", ch["id"], "raw_food", -amount)
    run("""UPDATE shelter_feasts SET contributed=contributed+?
           WHERE shelter_id=? AND day_count=?""", (amount, shelter["id"], day))
    feast = q("SELECT * FROM shelter_feasts WHERE shelter_id=? AND day_count=?",
              (shelter["id"], day), one=True)
    add_shelter_feed(shelter["id"], "chronicle", "晚餐记录",
                     f"{display_name(ch)} 为今天的共同晚餐贡献了 {amount} 份生鲜。")
    add_shelter_contribution(ch, amount * 2)
    if feast["contributed"] >= feast["target"]:
        run("""UPDATE shelter_feasts SET completed=1,completed_ts=?
               WHERE shelter_id=? AND day_count=?""", (now_ts(), shelter["id"], day))
        run("""UPDATE characters SET hunger=MIN(100,hunger+25)
               WHERE shelter_id=? AND status='alive'""", (shelter["id"],))
        add_shelter_feed(shelter["id"], "chronicle", "系统",
                         "共同晚餐开席了！全体在世成员恢复25点饥饿值。")
        flash("共同晚餐凑齐了！庇护所全员恢复25点饥饿值")
    else:
        flash(f"已贡献{amount}份生鲜，当前{feast['contributed']}/{feast['target']}")
    return redirect(url_for("dashboard"))

# ── 路由:管理后台(数值设计.md 提到的"先跑、/admin/stats 看数据、再调") ──────

@app.route("/admin")
@admin_required
def admin_home():
    ws = get_world_state()
    pending_users = q("SELECT * FROM users WHERE approved=0 ORDER BY created_ts")
    char_counts = q("""SELECT status, COUNT(*) AS c FROM characters GROUP BY status""")
    user_counts = q("SELECT COUNT(*) AS total, COALESCE(SUM(permadead),0) AS permadead FROM users", one=True)
    houses = q("SELECT COUNT(*) AS total, COALESCE(SUM(abandoned),0) AS abandoned FROM houses", one=True)
    shelters = q("""SELECT id, name, tier, research_points, has_furnace, has_advanced_workbench,
                            defense_walls, defense_traps, defense_tower, abandoned
                     FROM shelters ORDER BY id DESC LIMIT 20""")
    node_counts = q("""SELECT rarity, COUNT(*) AS c, COALESCE(SUM(current_amount),0) AS total_amt
                        FROM resource_nodes WHERE gone_forever=0 GROUP BY rarity""")
    recent_actions = q("""SELECT a.*, c.name AS char_name FROM action_log a
                           LEFT JOIN characters c ON c.id = a.character_id
                           ORDER BY a.id DESC LIMIT 20""")
    recent_deaths = q("""SELECT a.*, c.name AS char_name FROM action_log a
                          LEFT JOIN characters c ON c.id = a.character_id
                          WHERE a.action='death' ORDER BY a.id DESC LIMIT 10""")
    return render_template("admin.html", ws=ws, night=is_night(ws), char_counts=char_counts,
                            user_counts=user_counts, houses=houses, shelters=shelters,
                            node_counts=node_counts, recent_actions=recent_actions, recent_deaths=recent_deaths,
                            pending_users=pending_users,
                            grantable_resources=storage_transferable_keys(), item_names=ITEM_NAMES)

@app.route("/admin/stats")
@admin_required
def admin_stats():
    """只读统计页,汇总现有数据方便调数值,不改任何东西。"""
    alive = q("SELECT * FROM characters WHERE status='alive'")
    n = len(alive) or 1
    avg_level = round(sum(c["level"] for c in alive) / n, 1) if alive else 0
    stat_avgs = {k: round(sum(c[f"stat_{k}"] for c in alive) / n, 2) if alive else 0
                 for k in ("str", "spd", "int", "luck")}
    infection_buckets = {"0": 0, "1-30": 0, "31-70": 0, "71-99": 0, "100(将死)": 0}
    for c in alive:
        v = c["infection"]
        if v == 0: infection_buckets["0"] += 1
        elif v <= 30: infection_buckets["1-30"] += 1
        elif v <= 70: infection_buckets["31-70"] += 1
        elif v < 100: infection_buckets["71-99"] += 1
        else: infection_buckets["100(将死)"] += 1
    wallets = sorted(c["wallet"] for c in alive)
    avg_wallet = round(sum(wallets) / n, 1) if wallets else 0
    respawn_dist = q("""SELECT respawn_count, COUNT(*) AS c FROM users GROUP BY respawn_count ORDER BY respawn_count""")
    permadead_count = q("SELECT COUNT(*) AS c FROM users WHERE permadead=1", one=True)["c"]
    death_causes = q("""SELECT detail, COUNT(*) AS c FROM action_log WHERE action='death'
                         GROUP BY detail ORDER BY c DESC""")
    action_counts = q("SELECT action, COUNT(*) AS c FROM action_log GROUP BY action ORDER BY c DESC")
    equipped_weapons = q("""SELECT equipped_weapon, COUNT(*) AS c FROM characters
                             WHERE status='alive' GROUP BY equipped_weapon""")
    return render_template("admin_stats.html", n=len(alive), avg_level=avg_level, stat_avgs=stat_avgs,
                            infection_buckets=infection_buckets, avg_wallet=avg_wallet,
                            respawn_dist=respawn_dist, max_respawns=MAX_RESPAWNS, permadead_count=permadead_count,
                            death_causes=death_causes, action_counts=action_counts,
                            equipped_weapons=equipped_weapons, blueprints=BLUEPRINTS)

@app.route("/admin/tick", methods=["POST"])
@admin_required
def admin_tick():
    run_tick()
    flash("已手动推进一次tick")
    return redirect(url_for("admin_home"))

@app.route("/admin/unlock_permadead", methods=["POST"])
@admin_required
def admin_unlock_permadead():
    username = request.form.get("username", "").strip()
    user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
    if not user:
        flash("没有这个用户名")
    else:
        run("UPDATE users SET permadead=0 WHERE id=?", (user["id"],))
        flash(f"已解除 {username} 的永久死亡锁定(慎用,这是绕开一节'最多重开3次'规则的后门)")
    return redirect(url_for("admin_home"))

@app.route("/admin/grant_hp", methods=["POST"])
@admin_required
def admin_grant_hp():
    username = request.form.get("username", "").strip()
    amount = request.form.get("amount", type=int) or 0
    user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
    ch = q("SELECT * FROM characters WHERE user_id=? AND status='alive'", (user["id"],), one=True) if user else None
    if not user:
        flash("没有这个用户名")
    elif not ch:
        flash(f"{username} 目前没有存活的角色")
    elif amount <= 0:
        flash("HP数量要大于0")
    else:
        new_hp = min(100, ch["hp"] + amount)
        run("UPDATE characters SET hp=? WHERE id=?", (new_hp, ch["id"]))
        log_action(ch["id"], "admin_grant", f"管理员补HP+{amount}")
        flash(f"已给 {username}({ch['name']}) 的HP+{amount}，当前{new_hp}/100")
    return redirect(url_for("admin_home"))

@app.route("/admin/grant_stamina", methods=["POST"])
@admin_required
def admin_grant_stamina():
    username = request.form.get("username", "").strip()
    amount = request.form.get("amount", type=int) or 0
    user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
    ch = q("SELECT * FROM characters WHERE user_id=? AND status='alive'", (user["id"],), one=True) if user else None
    if not user:
        flash("没有这个用户名")
    elif not ch:
        flash(f"{username} 目前没有存活的角色")
    elif amount <= 0:
        flash("体力数量要大于0")
    else:
        ch = settle_stamina(ch)
        _, gained = restore_stamina(ch, amount, "管理员补体力")
        fresh = q("SELECT stamina FROM characters WHERE id=?", (ch["id"],), one=True)
        flash(f"已给 {username}({ch['name']}) 的体力+{gained}，当前{fresh['stamina']}/100")
    return redirect(url_for("admin_home"))

@app.route("/admin/reduce_infection", methods=["POST"])
@admin_required
def admin_reduce_infection():
    username = request.form.get("username", "").strip()
    amount = request.form.get("amount", type=int) or 0
    user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
    ch = q("SELECT * FROM characters WHERE user_id=? AND status='alive'", (user["id"],), one=True) if user else None
    if not user:
        flash("没有这个用户名")
    elif not ch:
        flash(f"{username} 目前没有存活的角色")
    elif amount <= 0:
        flash("感染度数量要大于0")
    else:
        new_infection = max(0, ch["infection"] - amount)
        run("UPDATE characters SET infection=? WHERE id=?", (new_infection, ch["id"]))
        log_action(ch["id"], "admin_grant", f"管理员降感染度-{amount}")
        flash(f"已给 {username}({ch['name']}) 的感染度-{amount}，当前{new_infection}")
    return redirect(url_for("admin_home"))

@app.route("/admin/grant_resource", methods=["POST"])
@admin_required
def admin_grant_resource():
    username = request.form.get("username", "").strip()
    resource_key = request.form.get("resource_key", "").strip()
    amount = request.form.get("amount", type=int) or 0
    user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
    ch = q("SELECT * FROM characters WHERE user_id=? AND status='alive'", (user["id"],), one=True) if user else None
    if not user:
        flash("没有这个用户名")
    elif not ch:
        flash(f"{username} 目前没有存活的角色")
    elif resource_key not in ITEM_NAMES:
        flash("没有这种材料/物品")
    elif amount <= 0:
        flash("数量要大于0")
    else:
        inv_add("character_inventory", "character_id", ch["id"], resource_key, amount)
        log_action(ch["id"], "admin_grant", f"管理员发放{ITEM_NAMES[resource_key]}x{amount}")
        flash(f"已给 {username}({ch['name']}) 的随身携带里加了{ITEM_NAMES[resource_key]}x{amount}")
    return redirect(url_for("admin_home"))

@app.route("/admin/approve_user", methods=["POST"])
@admin_required
def admin_approve_user():
    uid = request.form.get("user_id", type=int)
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        flash("没有这个账号")
    else:
        run("UPDATE users SET approved=1 WHERE id=?", (uid,))
        flash(f"已批准 {user['username']} 加入试玩")
    return redirect(url_for("admin_home"))

@app.route("/admin/reject_user", methods=["POST"])
@admin_required
def admin_reject_user():
    uid = request.form.get("user_id", type=int)
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not user:
        flash("没有这个账号")
    elif user["username"] == ADMIN_USERNAME:
        flash("不能拒绝管理员账号自己")
    else:
        run("DELETE FROM characters WHERE user_id=?", (uid,))
        run("DELETE FROM users WHERE id=?", (uid,))
        flash(f"已拒绝并删除 {user['username']} 这个申请")
    return redirect(url_for("admin_home"))

@app.route("/admin/reset_world", methods=["POST"])
@admin_required
def admin_reset_world():
    if request.form.get("confirm", "") != "重置":
        flash("请输入「重置」两个字以确认")
        return redirect(url_for("admin_home"))
    result = reset_world_preserve_users()
    flash(f"已重置整个世界：保留{result['users']}个注册账号及其批准状态；"
          f"角色、建筑、地图、关系、任务、库存和日志均已清空。"
          f"重置前备份：{result['backup_name']}")
    return redirect(url_for("admin_home"))

def reset_world_preserve_users():
    """将世界恢复到开服初始状态，只保留注册身份与审核状态。

    所有清理在同一事务内完成：任何一条失败都会整体回滚，不会留下半重置世界。
    """
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    backup_dir = os.path.join(os.path.dirname(DB_PATH), "db_backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_name = f"world_reset_{time.strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join(backup_dir, backup_name)
    backup_db = sqlite3.connect(backup_path)
    try:
        db.backup(backup_db)
    finally:
        backup_db.close()

    # 自动读取实际 schema，今后新增玩法表也会被清空，不再依赖容易漏表的手写名单。
    game_tables = [
        row[0] for row in db.execute(
            """SELECT name FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'
                 AND name NOT IN ('users','world_state')
               ORDER BY name""")
    ]
    ts = now_ts()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("PRAGMA defer_foreign_keys=ON")
        for table in game_tables:
            # 表名来自 sqlite_master，不接收用户输入。
            db.execute(f'DELETE FROM "{table}"')
        # 用户名、密码哈希、批准状态、注册时间和账号ID全部保留；死亡限制回到新服状态。
        db.execute("UPDATE users SET respawn_count=0,permadead=0")
        db.execute("""UPDATE world_state
                      SET day_count=1,day_started_ts=?,last_tick_ts=? WHERE id=1""",
                   (ts, ts))
        # 游戏对象重新从1编号，但users序列必须保留，避免未来新注册撞到现有账号ID。
        if db.execute("""SELECT 1 FROM sqlite_master
                         WHERE type='table' AND name='sqlite_sequence'""").fetchone():
            db.execute("DELETE FROM sqlite_sequence WHERE name<>'users'")
        # 商人也回到统一初始库存，玩家创建新角色后即可使用，不必等第一次后台tick。
        for key in MERCHANT_RESOURCES:
            db.execute("""INSERT INTO merchant_stock(resource_key,price,stock_amount)
                          VALUES(?,?,?)""", (key, MERCHANT_PRICE, MERCHANT_STOCK_MIN))
        db.execute("""INSERT INTO meta(key,value) VALUES('merchant_next_refresh_ts',?)""",
                   (str(ts + MERCHANT_REFRESH_SECONDS),))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"users": user_count, "backup_name": backup_name, "backup_path": backup_path}

# ── 全局 tick(run.py 后台线程调用) ────────────────────────────────────────

def _settle_wellbeing(db_, ch, ts):
    """按角色自己的幸存日结算，离线多日也只做温和追赶；返回是否发生致命事故。"""
    day = max(1, (ts - ch["created_ts"]) // DAY_SECONDS + 1)
    db_.execute("""INSERT OR IGNORE INTO character_wellbeing
                   (character_id,recreation,last_settled_day,updated_ts)
                   VALUES(?,70,?,?)""", (ch["id"], day, ts))
    row = db_.execute("SELECT * FROM character_wellbeing WHERE character_id=?", (ch["id"],)).fetchone()
    if day <= row["last_settled_day"]:
        return False
    recreation = row["recreation"]
    breakdown_count = row["breakdown_count"]
    last_breakdown_day = row["last_breakdown_day"]
    last_text = row["last_breakdown_text"]
    lethal = False
    for settle_day in range(row["last_settled_day"] + 1, day + 1):
        recreation = max(0, recreation - RECREATION_DAILY_DECAY)
        risk = .30 if recreation == 0 else (.18 if recreation < 15 else 0)
        rng = random.Random(f"wellbeing:{ch['id']}:{settle_day}")
        if risk and rng.random() < risk:
            event = rng.choice(("daze", "binge", "destructive", "wander", "panic"))
            if event == "binge":
                food_keys = tuple(FOOD_RECIPES) + tuple(DRINK_RECIPES) + ("cooked_food", "emergency_food")
                placeholders = ",".join("?" for _ in food_keys)
                item = db_.execute(
                    f"""SELECT resource_key FROM character_inventory
                        WHERE character_id=? AND amount>0 AND resource_key IN ({placeholders})
                        ORDER BY amount DESC LIMIT 1""", (ch["id"], *food_keys)).fetchone()
                if item:
                    db_.execute("""UPDATE character_inventory SET amount=MAX(0,amount-1)
                                   WHERE character_id=? AND resource_key=?""",
                                (ch["id"], item["resource_key"]))
                    last_text = f"第{settle_day}天失控进食，消耗了1份{ITEM_NAMES.get(item['resource_key'], item['resource_key'])}。"
                else:
                    db_.execute("UPDATE characters SET hp=MAX(1,hp-5) WHERE id=?", (ch["id"],))
                    last_text = f"第{settle_day}天因找不到食物而彻夜失眠，HP-5。"
            elif event == "destructive":
                db_.execute("""UPDATE characters SET weapon_durability=MAX(0,weapon_durability-15)
                               WHERE id=?""", (ch["id"],))
                last_text = f"第{settle_day}天在崩溃中摔坏装备，武器耐久-15。"
            elif event == "wander":
                damage = rng.randint(6, 15)
                db_.execute("UPDATE characters SET hp=MAX(1,hp-?) WHERE id=?", (damage, ch["id"]))
                last_text = f"第{settle_day}天恍惚游荡到废墟边缘，HP-{damage}。"
            elif event == "panic":
                fresh_hp = db_.execute("SELECT hp FROM characters WHERE id=?", (ch["id"],)).fetchone()["hp"]
                damage = rng.randint(10, 24)
                recently_active = ts - (ch["last_action_ts"] or 0) <= 10 * 60
                if recreation == 0 and fresh_hp <= 12 and recently_active and rng.random() < .05:
                    db_.execute("UPDATE characters SET hp=0 WHERE id=?", (ch["id"],))
                    last_text = f"第{settle_day}天精神崩溃引发了致命事故。"
                    lethal = True
                else:
                    db_.execute("UPDATE characters SET hp=MAX(1,hp-?) WHERE id=?", (damage, ch["id"]))
                    last_text = f"第{settle_day}天惊恐发作时受伤，HP-{damage}（不会由这次普通发作直接归零）。"
            else:
                last_text = f"第{settle_day}天陷入茫然，在房间里坐了很久。"
            breakdown_count += 1
            last_breakdown_day = settle_day
            objective = {
                "daze": "recreation", "binge": "gather", "destructive": "prepare",
                "wander": "safe_water", "panic": "prepare",
            }[event]
            target = 5 if objective == "gather" else 1
            source = f"mental:{settle_day}"
            if not db_.execute("""SELECT 1 FROM dynamic_personal_quests
                                  WHERE character_id=? AND source_key=?""",
                               (ch["id"], source)).fetchone():
                db_.execute("""INSERT INTO dynamic_personal_quests
                               (character_id,source_key,title,description,objective_key,target,
                                reward_key,reward_amount,created_ts)
                               VALUES(?,?,?,?,?,?,'wallet',8,?)""",
                            (ch["id"], source, "把自己重新拼起来",
                             f"{last_text} 这不是纯粹的惩罚：完成一件恢复秩序的小事，让这段经历有后续。",
                             objective, target, ts))
            db_.execute("""INSERT INTO action_log(character_id,action,detail,created_ts)
                           VALUES(?,'mental_break',?,?)""", (ch["id"], last_text, ts))
            if lethal:
                break
    state = "stable" if recreation >= 30 else ("strained" if recreation >= 15 else "critical")
    db_.execute("""UPDATE character_wellbeing SET recreation=?,last_settled_day=?,
                   mental_state=?,breakdown_count=?,last_breakdown_day=?,
                   last_breakdown_text=?,updated_ts=? WHERE character_id=?""",
                (recreation, day, state, breakdown_count, last_breakdown_day,
                 last_text, ts, ch["id"]))
    return lethal

def run_tick():
    """现实每次调用推进一小段时间:昼夜、生存消耗、资源刷新、夜袭、遗物清理。
    内部会调用依赖 Flask g 的 q()/run()/kill_character() 等,调用方必须自己包一层 app.app_context()
    (run.py 的后台tick线程已经这么做;/admin/tick 路由本身就在请求上下文里,天然满足)。"""
    db_ = sqlite3.connect(DB_PATH)
    db_.row_factory = sqlite3.Row
    ts = now_ts()

    ws = db_.execute("SELECT * FROM world_state WHERE id=1").fetchone()
    day_elapsed = ts - ws["day_started_ts"]
    if day_elapsed >= DAY_SECONDS:
        new_day_count = ws["day_count"] + (day_elapsed // DAY_SECONDS)
        new_started = ws["day_started_ts"] + (day_elapsed // DAY_SECONDS) * DAY_SECONDS
        start_ts, end_ts = ws["day_started_ts"], new_started
        deaths = db_.execute("""SELECT COUNT(*) FROM action_log
                               WHERE action='death' AND created_ts>=? AND created_ts<?""",
                             (start_ts, end_ts)).fetchone()[0]
        houses_built = db_.execute("""SELECT COUNT(*) FROM houses
                                     WHERE built_ts>=? AND built_ts<?""", (start_ts, end_ts)).fetchone()[0]
        shelters_built = db_.execute("""SELECT COUNT(*) FROM shelters
                                       WHERE created_ts>=? AND created_ts<?""", (start_ts, end_ts)).fetchone()[0]
        discoveries = db_.execute("""SELECT COUNT(*) FROM world_tiles
                                     WHERE discovered_ts>=? AND discovered_ts<?""", (start_ts, end_ts)).fetchone()[0]
        rescues = db_.execute("""SELECT COUNT(*) FROM rescue_signals
                                WHERE status='completed' AND completed_ts>=? AND completed_ts<?""",
                              (start_ts, end_ts)).fetchone()[0]
        report = (f"昨日新增房屋{houses_built}座、庇护所{shelters_built}座，"
                  f"发现{discoveries}块新地块，完成{rescues}次附近救援，"
                  f"记录到{deaths}名幸存者死亡。")
        db_.execute("""INSERT OR IGNORE INTO world_news(day_count,title,content,created_ts)
                       VALUES(?,?,?,?)""",
                    (ws["day_count"], "昨日生存简报", report, ts))
        for event in db_.execute("""SELECT * FROM shelter_life_events
                                    WHERE status='open' AND day_count<?""",
                                 (new_day_count,)).fetchall():
            votes = db_.execute("""SELECT option_key,COUNT(*) AS c FROM shelter_life_votes
                                   WHERE event_id=? GROUP BY option_key ORDER BY c DESC,option_key""",
                                (event["id"],)).fetchall()
            winner = votes[0]["option_key"] if votes else "无人回应"
            label = SHELTER_LIFE_EVENT_DEFS.get(event["event_key"], {}).get("options", {}).get(winner, winner)
            db_.execute("""UPDATE shelter_life_events SET status='resolved',winning_option=?,resolved_ts=?
                           WHERE id=?""", (winner, ts, event["id"]))
            db_.execute("""INSERT INTO shelter_feed
                           (shelter_id,entry_type,author_name,content,created_ts)
                           VALUES(?,'chronicle','生活记录',?,?)""",
                        (event["shelter_id"], f"{event['title']}最终选择：{label}。", ts))
        db_.execute("UPDATE world_state SET day_count=?, day_started_ts=?, last_tick_ts=? WHERE id=1",
                    (new_day_count, new_started, ts))
        # 每个新日结算一次区域热度。噪声消散较快；长期威胁只会缓慢回落，
        # 而尚未消散的高噪声会继续把附近尸群留在原地。
        for region in db_.execute("SELECT * FROM map_regions").fetchall():
            elapsed_days = max(0, new_day_count - region["last_decay_day"])
            if not elapsed_days:
                continue
            baseline = min(55, 8 + (abs(region["region_x"]) + abs(region["region_y"])) * 3)
            noise = max(0, region["noise"] - REGION_NOISE_DECAY_PER_DAY * elapsed_days)
            lingering = min(8, noise // 15)
            threat = max(
                baseline,
                region["threat"] - REGION_THREAT_DECAY_PER_DAY * elapsed_days + lingering,
            )
            noise_cap, threat_cap = repeller_cap_for_region(region["region_x"], region["region_y"])
            db_.execute("""UPDATE map_regions
                           SET noise=?,threat=?,last_decay_day=?,updated_ts=?
                           WHERE region_x=? AND region_y=?""",
                        (min(noise, noise_cap), min(threat, threat_cap), new_day_count, ts,
                         region["region_x"], region["region_y"]))
        # 人口本身就是持续信号：灯光、脚步、做饭、孩子和牲畜不会完全安静。
        # 结算按角色实际所在区域进行，不会因为加入某庇护所就隔空吸引尸群。
        population = {}
        for resident in db_.execute(
                "SELECT id,tile_x,tile_y FROM characters WHERE status='alive'").fetchall():
            key = region_coords(resident["tile_x"], resident["tile_y"])
            entry = population.setdefault(key, {"adults": 0, "children": 0, "animals": 0})
            entry["adults"] += 1
        for child in db_.execute(
                "SELECT tile_x,tile_y FROM children WHERE status='alive'").fetchall():
            key = region_coords(child["tile_x"], child["tile_y"])
            entry = population.setdefault(key, {"adults": 0, "children": 0, "animals": 0})
            entry["children"] += 1
        for animal in db_.execute(
                """SELECT c.tile_x,c.tile_y FROM personal_livestock a
                   JOIN characters c ON c.id=a.character_id
                   WHERE a.status='alive' AND c.status='alive'""").fetchall():
            key = region_coords(animal["tile_x"], animal["tile_y"])
            entry = population.setdefault(key, {"adults": 0, "children": 0, "animals": 0})
            entry["animals"] += 1
        for (rx, ry), counts in population.items():
            population_noise = min(
                20, counts["adults"] * 2 + counts["children"] +
                int(math.ceil(counts["animals"] / 2)))
            if not population_noise:
                continue
            baseline = min(55, 8 + (abs(rx) + abs(ry)) * 3)
            db_.execute("""INSERT OR IGNORE INTO map_regions
                           (region_x,region_y,noise,threat,last_decay_day,updated_ts)
                           VALUES(?,?,0,?,?,?)""",
                        (rx, ry, baseline, new_day_count, ts))
            threat_added = max(1, int(math.ceil(population_noise * .35)))
            pop_noise_cap, pop_threat_cap = repeller_cap_for_region(rx, ry)
            db_.execute("""UPDATE map_regions SET noise=MIN(?,noise+?),
                           threat=MIN(?,threat+?),last_decay_day=?,updated_ts=?
                           WHERE region_x=? AND region_y=?""",
                        (pop_noise_cap, population_noise, pop_threat_cap, threat_added, new_day_count, ts, rx, ry))
            detail = (f"区域常住人口：成人{counts['adults']}、孩子{counts['children']}、"
                      f"牲畜{counts['animals']}，日常活动形成持续信号。")
            db_.execute("""INSERT INTO region_threat_events
                           (region_x,region_y,character_id,event_key,noise_added,
                            threat_added,detail,created_ts)
                           VALUES(?,?,NULL,'population',?,?,?,?)""",
                        (rx, ry, population_noise, threat_added, detail, ts))
    else:
        db_.execute("UPDATE world_state SET last_tick_ts=? WHERE id=1", (ts,))

    # 生存消耗：每游戏小时约-1，即每个现实小时（一个游戏日）约-24。
    # 用meta保存不足1点的余数，避免60秒tick每次int取整后永远不扣。
    game_hours_per_real_second = 1.0 / (DAY_SECONDS / 24.0)
    last_tick_gap = ts - (ws["last_tick_ts"] or ts)
    remainder_row = db_.execute(
        "SELECT value FROM meta WHERE key='survival_decay_remainder'").fetchone()
    remainder = float(remainder_row["value"]) if remainder_row else 0.0
    decay_total = remainder + max(0, game_hours_per_real_second * last_tick_gap)
    hunger_thirst_decay = int(decay_total)
    new_remainder = decay_total - hunger_thirst_decay
    db_.execute("""INSERT INTO meta(key,value) VALUES('survival_decay_remainder',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (str(new_remainder),))

    for ch in db_.execute("SELECT * FROM characters WHERE status='alive'").fetchall():
        lethal_breakdown = _settle_wellbeing(db_, ch, ts)
        db_.commit()
        if lethal_breakdown:
            db_.close()
            kill_character(ch["id"], reason="娱乐长期枯竭引发的精神崩溃事故")
            db_ = sqlite3.connect(DB_PATH)
            db_.row_factory = sqlite3.Row
            continue
        ch = db_.execute("SELECT * FROM characters WHERE id=?", (ch["id"],)).fetchone()
        hunger = max(0, ch["hunger"] - hunger_thirst_decay)
        thirst = max(0, ch["thirst"] - hunger_thirst_decay)
        hp = ch["hp"]
        if (hunger <= 0 or thirst <= 0) and hunger_thirst_decay:
            hp -= max(1, hunger_thirst_decay // 2)
        if ch["poison_until_ts"] and ts < ch["poison_until_ts"]:
            hp -= 1
        # 离线tick最多把角色压到重伤，不直接饿死；真正的死亡仍来自玩家在线时承担的风险。
        hp = max(1, hp)
        db_.execute("UPDATE characters SET hunger=?, thirst=?, hp=? WHERE id=?", (hunger, thirst, hp, ch["id"]))
        if hp <= 0:
            db_.commit()
            db_.close()
            kill_character(ch["id"], reason="饥饿/口渴/中毒耗尽HP")
            db_ = sqlite3.connect(DB_PATH)
            db_.row_factory = sqlite3.Row
            continue
        # 十七节:感染度没有主动清除手段时太致命,给吃饱喝足的人一点自然缓解，但只降到
        # INFECTION_RECOVERY_FLOOR为止——剩下那部分仍然只能靠庇护所解药清零。
        # 确定性计时(不再掷骰子):连续达标满INTERVAL秒必定-AMOUNT一次；中途掉出达标线就重新计时。
        if ch["infection"] > INFECTION_RECOVERY_FLOOR and hunger >= INFECTION_RECOVERY_WELLFED_THRESHOLD and thirst >= INFECTION_RECOVERY_WELLFED_THRESHOLD:
            started = ch["infection_relief_started_ts"]
            if not started:
                db_.execute("UPDATE characters SET infection_relief_started_ts=? WHERE id=?", (ts, ch["id"]))
            elif ts - started >= INFECTION_RECOVERY_INTERVAL_SECONDS:
                db_.execute("""UPDATE characters SET infection=MAX(?,infection-?),
                               infection_relief_started_ts=? WHERE id=?""",
                           (INFECTION_RECOVERY_FLOOR, INFECTION_RECOVERY_AMOUNT, ts, ch["id"]))
        elif ch["infection_relief_started_ts"]:
            db_.execute("UPDATE characters SET infection_relief_started_ts=0 WHERE id=?", (ch["id"],))
        # 二十二节:HP被动自然回复，很慢，医疗用品仍然是唯一能快速回血的办法。
        if (hp > 0 and hp < 100 and last_tick_gap > 0 and
                random.random() < last_tick_gap / HP_PASSIVE_REGEN_INTERVAL_SECONDS):
            db_.execute("UPDATE characters SET hp=MIN(100,hp+1) WHERE id=?", (ch["id"],))
        # 二十五节:自动吃喝(玩家自己开关)，随身包里有什么就按优先级吃/喝，直到达标或用完为止。
        if ch["auto_eat_enabled"]:
            while hunger < AUTO_EAT_HUNGER_THRESHOLD:
                consumed = False
                for key, gain in AUTO_EAT_FOOD_PRIORITY:
                    row = db_.execute("""SELECT amount FROM character_inventory
                                         WHERE character_id=? AND resource_key=? AND amount>0""",
                                      (ch["id"], key)).fetchone()
                    if row:
                        db_.execute("""UPDATE character_inventory SET amount=amount-1
                                       WHERE character_id=? AND resource_key=?""", (ch["id"], key))
                        hunger = min(100, hunger + gain)
                        if key == "emergency_food":
                            thirst = max(0, thirst - EMERGENCY_FOOD_THIRST_COST)
                        consumed = True
                        break
                if not consumed:
                    break
            while thirst < AUTO_EAT_THIRST_THRESHOLD:
                consumed = False
                for key, gain in AUTO_DRINK_PRIORITY:
                    row = db_.execute("""SELECT amount FROM character_inventory
                                         WHERE character_id=? AND resource_key=? AND amount>0""",
                                      (ch["id"], key)).fetchone()
                    if row:
                        db_.execute("""UPDATE character_inventory SET amount=amount-1
                                       WHERE character_id=? AND resource_key=?""", (ch["id"], key))
                        thirst = min(100, thirst + gain)
                        consumed = True
                        break
                if not consumed:
                    break
            db_.execute("UPDATE characters SET hunger=?, thirst=? WHERE id=?", (hunger, thirst, ch["id"]))

    # 家庭成长：每个年龄日只结算一次需求和一次探索。6岁前不会自理，6岁后先用自己的物资。
    for child in db_.execute("SELECT * FROM children WHERE status='alive'").fetchall():
        age = max(0, (ts - child["born_ts"]) // DAY_SECONDS)
        _settle_child_needs(db_, child, age)
        fresh_child = db_.execute("SELECT * FROM children WHERE id=?", (child["id"],)).fetchone()
        _child_exploration(db_, fresh_child, age)
    db_.commit()

    # 个人畜牧：按动物自己的年龄日结算。漏喂只会降健康并留下求助，不会突然死亡。
    for animal in db_.execute("SELECT * FROM personal_livestock WHERE status='alive'").fetchall():
        age = max(0, (ts - animal["born_ts"]) // DAY_SECONDS)
        if age == 0 and animal["last_settled_age"] < 0:
            db_.execute("UPDATE personal_livestock SET last_settled_age=0 WHERE id=?", (animal["id"],))
        elif age > animal["last_settled_age"]:
            previous_age = age - 1
            if animal["fed_age_day"] < previous_age:
                db_.execute("UPDATE personal_livestock SET health=MAX(1,health-5) WHERE id=?", (animal["id"],))
                db_.execute("""INSERT INTO livestock_logs(animal_id,event_key,detail,created_ts)
                               VALUES(?,'help',?,?)""",
                            (animal["id"], f"{animal['custom_name']}的饲料盆空了，正在等待主人。", ts))
            db_.execute("UPDATE personal_livestock SET last_settled_age=? WHERE id=?", (age, animal["id"]))
        info = LIVESTOCK_TYPES.get(animal["species_key"])
        if (info and age >= info["adult_age"] and animal["fed_age_day"] >= age and
                (animal["last_produce_age"] < 0 or age - animal["last_produce_age"] >= info["produce_days"])):
            amount = 1 if animal["species_key"] != "chicken" else random.randint(1, 2)
            db_.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                           VALUES(?,?,?) ON CONFLICT(character_id,resource_key)
                           DO UPDATE SET amount=amount+?""",
                        (animal["character_id"], info["produce_key"], amount, amount))
            db_.execute("UPDATE personal_livestock SET last_produce_age=? WHERE id=?", (age, animal["id"]))
            db_.execute("""INSERT INTO livestock_logs(animal_id,event_key,detail,created_ts)
                           VALUES(?,'produce',?,?)""",
                        (animal["id"], f"{animal['custom_name']}产出了{info['produce_name']}x{amount}。", ts))
    db_.commit()

    # 离线远征返程：不会在玩家离线时直接杀死角色，最坏会重伤并生成后续支线。
    for expedition in db_.execute("""SELECT * FROM expeditions
                                     WHERE status='active' AND return_ts<=?""", (ts,)).fetchall():
        route = EXPEDITION_ROUTES.get(expedition["route_key"])
        if not route:
            db_.execute("UPDATE expeditions SET status='failed',resolved_ts=? WHERE id=?",
                        (ts, expedition["id"]))
            continue
        danger = route["danger"]
        if expedition["strategy"] == "careful":
            danger *= .55
        elif expedition["strategy"] == "bold":
            danger *= 1.45
        if expedition["companion_character_id"]:
            danger *= .72
        if expedition["child_id"]:
            danger *= .86
        outfit = db_.execute("""SELECT outfit_key FROM personal_outfits
                                WHERE character_id=? AND equipped=1 LIMIT 1""",
                             (expedition["character_id"],)).fetchone()
        if outfit and outfit["outfit_key"] in ("raincoat", "winter_coat"):
            danger *= .9 if outfit["outfit_key"] == "raincoat" else .88
        if outfit and outfit["outfit_key"] == "family_jacket":
            family_companion = bool(expedition["child_id"])
            if expedition["companion_character_id"]:
                pair = sorted((expedition["character_id"], expedition["companion_character_id"]))
                family_companion = family_companion or bool(db_.execute(
                    """SELECT 1 FROM player_bonds
                       WHERE char_a=? AND char_b=? AND married=1""", pair).fetchone())
            if family_companion:
                danger *= .85
        roll = random.random()
        if roll < danger:
            damage = random.randint(8, 34)
            result_key = "hurt"
            result_text = f"远征队遭遇伏击，丢掉大半收获后撤回。你受到{damage}点伤害，但不会因离线结算直接死亡。"
            db_.execute("UPDATE characters SET hp=MAX(1,hp-?) WHERE id=?",
                        (damage, expedition["character_id"]))
            db_.execute("""INSERT INTO dynamic_personal_quests
                           (character_id,source_key,title,description,objective_key,target,
                            reward_key,reward_amount,created_ts)
                           VALUES(?,?,?,?,?,1,'bandage',1,?)""",
                        (expedition["character_id"], f"expedition:{expedition['id']}",
                         "回到失手的路线", "处理一次沿途探索事件，确认伏击者已经离开。",
                         "world_event", ts))
            reward_key, amount = "", 0
            hp_change = -damage
        else:
            reward_key = random.choice(route["rewards"])
            amount = random.randint(2, 5) + (2 if expedition["strategy"] == "bold" else 0)
            result_key = "rare" if reward_key in ("old_gem", "electronics") else "success"
            result_text = f"远征队按计划返程，带回{ITEM_NAMES.get(reward_key,reward_key)}x{amount}。"
            db_.execute("""INSERT INTO character_inventory(character_id,resource_key,amount)
                           VALUES(?,?,?) ON CONFLICT(character_id,resource_key)
                           DO UPDATE SET amount=amount+?""",
                        (expedition["character_id"], reward_key, amount, amount))
            hp_change = 0
            if expedition["child_id"]:
                db_.execute("UPDATE children SET stat_luck=MIN(20,stat_luck+1) WHERE id=?",
                            (expedition["child_id"],))
        db_.execute("""UPDATE expeditions SET status='returned',result_key=?,result_text=?,
                       hp_change=?,reward_key=?,reward_amount=?,resolved_ts=? WHERE id=?""",
                    (result_key, result_text, hp_change, reward_key, amount, ts, expedition["id"]))
        db_.execute("""INSERT INTO family_album
                       (character_id,child_id,event_key,title,story_text,created_ts)
                       VALUES(?,?,'expedition','远征归来',?,?)""",
                    (expedition["character_id"], expedition["child_id"], result_text, ts))
    db_.commit()

    # 驯养:带回兽栏的动物每天被动产出(生产型出零件,任何动物都出一点粪便供堆肥用)
    for ch in db_.execute("""SELECT * FROM characters WHERE status='alive' AND tamed_animal_key IS NOT NULL
                             AND shelter_id IS NOT NULL AND animal_collect_ready_ts<=?""", (ts,)).fetchall():
        shelter = db_.execute("SELECT has_animal_pen FROM shelters WHERE id=?", (ch["shelter_id"],)).fetchone()
        if not shelter or not shelter["has_animal_pen"]:
            continue
        db_.execute("""INSERT INTO shelter_inventory (shelter_id, resource_key, amount) VALUES (?,'animal_dung',1)
                        ON CONFLICT(shelter_id, resource_key) DO UPDATE SET amount=amount+1""", (ch["shelter_id"],))
        produced_total = 1
        if ch["tamed_animal_key"] == "big_producer":
            lo, hi = ANIMALS["big_producer"]["daily_parts"]
            parts_amt = random.randint(lo, hi)
            db_.execute("""INSERT INTO shelter_inventory (shelter_id, resource_key, amount) VALUES (?,'parts',?)
                            ON CONFLICT(shelter_id, resource_key) DO UPDATE SET amount=amount+?""",
                        (ch["shelter_id"], parts_amt, parts_amt))
            produced_total += parts_amt
        db_.execute("""UPDATE tamed_animal_profiles
                       SET resources_produced=resources_produced+? WHERE character_id=?""",
                    (produced_total, ch["id"]))
        db_.execute("UPDATE characters SET animal_collect_ready_ts=? WHERE id=?", (ts + 86400, ch["id"]))
    db_.commit()

    # 资源刷新:按稀有度周期回满(八.1)
    for key, (_, rarity, hours) in RESOURCES.items():
        if hours is None:
            continue
        threshold = ts - hours * 3600
        db_.execute("""UPDATE resource_nodes SET current_amount=max_amount, depleted_ts=0
                       WHERE resource_key=? AND current_amount<max_amount AND depleted_ts>0 AND depleted_ts<?""",
                    (key, threshold))

    # 流动商人:定期刷新库存(B档59条)
    merchant_row = db_.execute("SELECT value FROM meta WHERE key='merchant_next_refresh_ts'").fetchone()
    merchant_next = int(merchant_row[0]) if merchant_row else 0
    if ts >= merchant_next:
        for key in MERCHANT_RESOURCES:
            amt = random.randint(MERCHANT_STOCK_MIN, MERCHANT_STOCK_MAX)
            db_.execute("""INSERT INTO merchant_stock (resource_key, price, stock_amount) VALUES (?,?,?)
                           ON CONFLICT(resource_key) DO UPDATE SET stock_amount=?""", (key, MERCHANT_PRICE, amt, amt))
        new_next = ts + MERCHANT_REFRESH_SECONDS
        if merchant_row:
            db_.execute("UPDATE meta SET value=? WHERE key='merchant_next_refresh_ts'", (str(new_next),))
        else:
            db_.execute("INSERT INTO meta (key, value) VALUES ('merchant_next_refresh_ts', ?)", (str(new_next),))
    db_.commit()

    # 死亡遗物点24小时清理(十.2/数值设计三节)
    db_.execute("DELETE FROM death_loot WHERE dropped_ts < ?", (ts - 24 * 3600,))

    # 二十九节:被动资源采集机(打矿机/自动伐木机/自动采石机)统一产出，按小时结算，
    # 超过仓库容量的部分直接溢出(不阻塞tick)。旧版本挂在houses.has_metal_driller上的记录
    # 已经在init_db里搬进这张表了，这里不用再单独认houses表。
    for ext in db_.execute("SELECT * FROM resource_extractors WHERE ready_ts>0 AND ready_ts<=?", (ts,)).fetchall():
        info = EXTRACTOR_TYPES.get(ext["kind"])
        if not info:
            continue
        level_info = EXTRACTOR_LEVELS[ext["kind"]].get(ext["level"], EXTRACTOR_LEVELS[ext["kind"]][1])
        elapsed_hours = 1 + (ts - ext["ready_ts"]) // EXTRACTOR_INTERVAL_SECONDS
        yield_amount = elapsed_hours * level_info["yield_per_hour"]
        if info["resource_key"] == "research_points":
            # 研究站直接产科研点，那是庇护所自己的一个计数字段，没有"仓库容量"这个概念，不用算溢出。
            if ext["owner_type"] != "shelter":
                continue
            owner = db_.execute("SELECT * FROM shelters WHERE id=? AND abandoned=0", (ext["owner_id"],)).fetchone()
            if not owner:
                continue
            db_.execute("UPDATE shelters SET research_points=research_points+? WHERE id=?",
                       (yield_amount, ext["owner_id"]))
            db_.execute("""UPDATE resource_extractors SET ready_ts=?
                           WHERE owner_type=? AND owner_id=? AND kind=?""",
                        (ext["ready_ts"] + elapsed_hours * EXTRACTOR_INTERVAL_SECONDS,
                         ext["owner_type"], ext["owner_id"], ext["kind"]))
            continue
        if ext["owner_type"] == "house":
            owner = db_.execute("SELECT * FROM houses WHERE id=? AND abandoned=0", (ext["owner_id"],)).fetchone()
            table, id_col = "house_inventory", "house_id"
            cap = house_inventory_cap_for(owner) if owner else 0
        else:
            owner = db_.execute("SELECT * FROM shelters WHERE id=? AND abandoned=0", (ext["owner_id"],)).fetchone()
            table, id_col = "shelter_inventory", "shelter_id"
            cap = shelter_inventory_cap_for(owner) if owner else 0
        if not owner:
            continue
        current_total = db_.execute(f"""SELECT COALESCE(SUM(amount),0) t FROM {table}
                                        WHERE {id_col}=?""", (ext["owner_id"],)).fetchone()["t"]
        room = max(0, cap - current_total)
        actual_yield = min(yield_amount, room)
        if actual_yield:
            db_.execute(f"""INSERT INTO {table}({id_col},resource_key,amount) VALUES(?,?,?)
                           ON CONFLICT({id_col},resource_key) DO UPDATE SET amount=amount+excluded.amount""",
                       (ext["owner_id"], info["resource_key"], actual_yield))
        db_.execute("""UPDATE resource_extractors SET ready_ts=?
                       WHERE owner_type=? AND owner_id=? AND kind=?""",
                    (ext["ready_ts"] + elapsed_hours * EXTRACTOR_INTERVAL_SECONDS,
                     ext["owner_type"], ext["owner_id"], ext["kind"]))

    # 三节/十.1:废弃建筑保留一段时间后自动拆除清空,地块恢复空地
    cleanup_threshold = ts - BUILDING_ABANDON_CLEANUP_SECONDS
    for house in db_.execute("SELECT * FROM houses WHERE abandoned=1 AND abandoned_ts>0 AND abandoned_ts<?",
                              (cleanup_threshold,)).fetchall():
        db_.execute("DELETE FROM power_logs WHERE owner_type='house' AND owner_id=?", (house["id"],))
        db_.execute("DELETE FROM power_grids WHERE owner_type='house' AND owner_id=?", (house["id"],))
        db_.execute("DELETE FROM house_raid_logs WHERE house_id=?", (house["id"],))
        db_.execute("DELETE FROM house_inventory WHERE house_id=?", (house["id"],))
        db_.execute("UPDATE world_tiles SET has_building=0 WHERE x=? AND y=?", (house["tile_x"], house["tile_y"]))
        db_.execute("DELETE FROM houses WHERE id=?", (house["id"],))
    for shelter in db_.execute("SELECT * FROM shelters WHERE abandoned=1 AND abandoned_ts>0 AND abandoned_ts<?",
                                (cleanup_threshold,)).fetchall():
        db_.execute("DELETE FROM power_logs WHERE owner_type='shelter' AND owner_id=?", (shelter["id"],))
        db_.execute("DELETE FROM power_grids WHERE owner_type='shelter' AND owner_id=?", (shelter["id"],))
        db_.execute("DELETE FROM shelter_inventory WHERE shelter_id=?", (shelter["id"],))
        db_.execute("DELETE FROM shelter_notifications WHERE shelter_id=?", (shelter["id"],))
        db_.execute("UPDATE world_tiles SET has_building=0 WHERE x=? AND y=?", (shelter["tile_x"], shelter["tile_y"]))
        db_.execute("DELETE FROM shelters WHERE id=?", (shelter["id"],))

    db_.commit()

    # 北辰无线电会在夜袭前15分钟播报一次；页面上的倒计时仍会逐秒更新。
    live_ws = db_.execute("SELECT * FROM world_state WHERE id=1").fetchone()
    elapsed = (ts - live_ws["day_started_ts"]) % DAY_SECONDS
    night_start = int(DAY_SECONDS * DAY_RATIO)
    raid_eta = 0 if elapsed >= night_start else night_start - elapsed
    warning_key = f"night_warning_day_{live_ws['day_count']}"
    warning_sent = db_.execute("SELECT 1 FROM meta WHERE key=?", (warning_key,)).fetchone()
    raid_night = is_raid_night(live_ws["day_count"]) and not in_night_raid_quiet_hours(ts)
    if raid_night and 0 < raid_eta <= NIGHT_RAID_WARNING_SECONDS and not warning_sent:
        minutes = max(1, int(math.ceil(raid_eta / 60)))
        db_.execute("""INSERT INTO server_announcements(content,created_ts)
                       VALUES(?,?)""",
                    (f"📻 北辰紧急预警：约{minutes}分钟后进入夜袭时段。"
                     "检查房屋耐久、弹药和区域威胁；高噪声会引来更强尸群。", ts))
        db_.execute("INSERT INTO meta(key,value) VALUES(?,?)",
                    (warning_key, str(ts)))
        db_.execute("DELETE FROM server_announcements WHERE created_ts<?",
                    (ts - 2 * DAY_SECONDS,))

    # 夜袭结算(8.2 / 十六.9),只在刚进入夜晚的这次tick触发一次，且只在真正的夜袭日
    now_night = is_night()
    was_night_key = db_.execute("SELECT value FROM meta WHERE key='was_night'").fetchone()
    was_night = was_night_key and was_night_key["value"] == "1"
    if now_night and not was_night and raid_night:
        _resolve_night_raid(db_)
    if was_night_key:
        db_.execute("UPDATE meta SET value=? WHERE key='was_night'", ("1" if now_night else "0",))
    else:
        db_.execute("INSERT INTO meta (key, value) VALUES ('was_night', ?)", ("1" if now_night else "0",))
    db_.commit()
    db_.close()

def _resolve_night_raid(db_):
    ts = now_ts()
    ws = db_.execute("SELECT * FROM world_state WHERE id=1").fetchone()
    raided_regions = set()
    shelter_powered_tower_cache = {}
    for ch in db_.execute("SELECT * FROM characters WHERE status='alive'").fetchall():
        if ts < ch["protected_until_ts"]:
            continue
        dist = dist_from_origin(ch["tile_x"], ch["tile_y"])
        rx, ry = region_coords(ch["tile_x"], ch["tile_y"])
        baseline = min(55, 8 + (abs(rx) + abs(ry)) * 3)
        db_.execute("""INSERT OR IGNORE INTO map_regions
                       (region_x,region_y,noise,threat,last_decay_day,updated_ts)
                       VALUES(?,?,0,?,?,?)""",
                    (rx, ry, baseline, ws["day_count"], ts))
        region = db_.execute("""SELECT * FROM map_regions
                                WHERE region_x=? AND region_y=?""",
                             (rx, ry)).fetchone()
        raided_regions.add((rx, ry))
        strength = zombie_base_strength(
            dist, ws["day_count"]) * (1 + region["threat"] / 100)
        house = db_.execute("""SELECT * FROM houses
                               WHERE owner_user_id=? AND tile_x=? AND tile_y=? AND abandoned=0""",
                            (ch["user_id"], ch["tile_x"], ch["tile_y"])).fetchone()
        shelter = None
        if ch["shelter_id"]:
            shelter = db_.execute("SELECT * FROM shelters WHERE id=?", (ch["shelter_id"],)).fetchone()
        if shelter and shelter["tile_x"] == ch["tile_x"] and shelter["tile_y"] == ch["tile_y"]:
            member_count = db_.execute("SELECT COUNT(*) c FROM characters WHERE shelter_id=? AND status='alive'",
                                        (shelter["id"],)).fetchone()["c"]
            night_strength = strength * (1 + member_count * 0.15)
            # 瞭望塔不通电时只能充当高处哨位（5防御）；每座消耗1电后搜索灯和警报使其达到15。
            powered_towers = shelter_powered_tower_cache.get(shelter["id"])
            if powered_towers is None:
                grid = db_.execute("""SELECT * FROM power_grids
                                      WHERE owner_type='shelter' AND owner_id=?""",
                                   (shelter["id"],)).fetchone()
                powered_towers = 0
                if grid and not grid["damaged"] and shelter["defense_tower"] > 0:
                    powered_towers = min(shelter["defense_tower"], grid["charge"])
                    if powered_towers:
                        db_.execute("""UPDATE power_grids SET charge=charge-?,updated_ts=?
                                       WHERE owner_type='shelter' AND owner_id=?""",
                                    (powered_towers, ts, shelter["id"]))
                        db_.execute("""INSERT INTO power_logs
                                       (owner_type,owner_id,character_id,event_key,power_change,detail,created_ts)
                                       VALUES('shelter',?,?,'consume',?,?,?)""",
                                    (shelter["id"], ch["id"], -powered_towers,
                                     f"夜袭中为{powered_towers}座瞭望塔供电。", ts))
                shelter_powered_tower_cache[shelter["id"]] = powered_towers
            defense = (member_count * 10 + shelter["defense_walls"] * 20 +
                       shelter["defense_traps"] * 10 + shelter["defense_tower"] * 5 +
                       powered_towers * 10)
            if defense < night_strength:
                dmg = int(min(40, (night_strength - defense)))
                traits = db_.execute("SELECT trait_a,trait_b FROM character_profiles WHERE character_id=?",
                                     (ch["id"],)).fetchone()
                if traits and "tough" in (traits["trait_a"], traits["trait_b"]):
                    dmg = max(0, int(dmg * 0.85))
                new_hp = max(0, ch["hp"] - dmg)
                db_.execute("UPDATE characters SET hp=? WHERE id=?", (new_hp, ch["id"]))
        elif house:
            level = max(1, min(HOUSE_LEVEL_CAP, house["level"]))
            info = HOUSE_LEVELS[level]
            stance = house["raid_stance"] if house["raid_stance"] in RAID_STANCES else "balanced"
            attack = max(1, int(round(strength)))
            counter_damage = 0
            ammo_used = False
            power_used = False
            power_missing = False
            structure_damage = 0
            character_damage = 0
            house_hp = max(0, house["hp"])
            # 自动反击必须由仍有耐久的房屋供电，并从房屋仓库消耗1发弹药。
            # 它只能削弱尸群，结算后至少仍保留1点来袭强度。
            if (stance != "conserve" and house_hp > 0 and
                    house["auto_defense"] and info["counter"] > 0):
                ammo = db_.execute("""SELECT amount FROM house_inventory
                                      WHERE house_id=? AND resource_key='ammo'""",
                                   (house["id"],)).fetchone()
                grid = db_.execute("""SELECT * FROM power_grids
                                      WHERE owner_type='house' AND owner_id=?""",
                                   (house["id"],)).fetchone()
                power_ready = bool(grid and not grid["damaged"] and grid["charge"] >= 3)
                if ammo and ammo["amount"] > 0 and power_ready:
                    counter_damage = min(attack - 1, max(1, int(attack * info["counter"])))
                    db_.execute("""UPDATE house_inventory SET amount=amount-1
                                   WHERE house_id=? AND resource_key='ammo'""",
                                (house["id"],))
                    db_.execute("""UPDATE power_grids SET charge=charge-3,updated_ts=?
                                   WHERE owner_type='house' AND owner_id=?""",
                                (ts, house["id"]))
                    db_.execute("""INSERT INTO power_logs
                                   (owner_type,owner_id,character_id,event_key,power_change,detail,created_ts)
                                   VALUES('house',?,?,'consume',-3,?,?)""",
                                (house["id"], ch["id"], "夜袭自动反击系统启动。", ts))
                    ammo_used = True
                    power_used = True
                elif not power_ready:
                    power_missing = True
            remaining = max(1, attack - counter_damage)
            if stance == "storage":
                remaining += 2
            elif stance == "lure":
                remaining = max(1, int(math.ceil(remaining * .75)))
            if house_hp > 0:
                remaining = max(1, remaining - info["armor"])
                structure_damage = min(house_hp, remaining)
                overflow = max(0, remaining - house_hp)
                new_house_hp = max(0, house_hp - structure_damage)
                db_.execute("""UPDATE houses SET hp=?,last_raid_ts=? WHERE id=?""",
                            (new_house_hp, ts, house["id"]))
                if overflow:
                    character_damage = overflow
                    db_.execute("UPDATE characters SET hp=MAX(0,hp-?) WHERE id=?",
                                (character_damage, ch["id"]))
            else:
                # 防线已经归零，房屋不再提供护甲或自动反击；尸群会持续攻击住户。
                character_damage = remaining
                db_.execute("UPDATE characters SET hp=MAX(0,hp-?) WHERE id=?",
                            (character_damage, ch["id"]))
                new_house_hp = 0
                db_.execute("UPDATE houses SET last_raid_ts=? WHERE id=?", (ts, house["id"]))
            parts = [f"夜袭强度{attack}（区域威胁{region['threat']}）",
                     f"方针：{RAID_STANCES[stance][0]}"]
            if ammo_used:
                parts.append(f"自动反击削弱{counter_damage}（弹药-1、电力-3）")
            elif stance == "conserve" and house["auto_defense"]:
                parts.append("按方针保存了自动反击弹药与电力")
            elif power_missing:
                parts.append("自动反击因断电未启动")
            elif house["auto_defense"]:
                parts.append("自动反击缺少弹药")
            if structure_damage:
                parts.append(f"房屋耐久-{structure_damage}")
            if new_house_hp <= 0:
                parts.append("防线已破")
                # 破门后每次至多毁坏一项仍在工作的设施；所有项目均有现成重建/维修入口。
                facilities = []
                if house["has_workbench"]:
                    facilities.append(("houses", "id", house["id"], "has_workbench", "基础工作台"))
                if house["auto_defense"] and info["counter"] > 0:
                    facilities.append(("houses", "id", house["id"], "auto_defense", "自动反击系统"))
                home = db_.execute("""SELECT * FROM personal_homesteads
                                      WHERE character_id=?""", (ch["id"],)).fetchone()
                if home:
                    for column, label in (
                            ("has_kitchen", "烹饪台"), ("has_brewery", "酿造台"),
                            ("has_sewing", "缝纫台"), ("has_livestock", "畜牧棚")):
                        if home[column]:
                            facilities.append(("personal_homesteads", "character_id",
                                               ch["id"], column, label))
                workshop = db_.execute("""SELECT * FROM personal_survival_workshops
                                          WHERE character_id=?""", (ch["id"],)).fetchone()
                if workshop:
                    for column, label in (
                            ("has_water_tester", "污染检测台"),
                            ("has_ammo_press", "弹药复装台")):
                        if workshop[column]:
                            facilities.append(("personal_survival_workshops", "character_id",
                                               ch["id"], column, label))
                power_grid = db_.execute("""SELECT * FROM power_grids
                                            WHERE owner_type='house' AND owner_id=?""",
                                         (house["id"],)).fetchone()
                if power_grid and power_grid["generator_level"] and not power_grid["damaged"]:
                    facilities.append(("power_grids", "owner_id", house["id"],
                                       "grid_damage", "房屋电网"))
                raid_rng = random.Random(
                    f"facility:{house['id']}:{ws['day_count']}:{house['last_raid_ts']}")
                facility_saved = stance == "facility" and raid_rng.random() < .70
                if facilities and not facility_saved:
                    table, id_col, id_value, column, label = raid_rng.choice(facilities)
                    if column == "auto_defense":
                        db_.execute("""UPDATE houses
                                       SET auto_defense=0,auto_defense_damaged=1
                                       WHERE id=?""", (house["id"],))
                    elif column == "grid_damage":
                        db_.execute("""UPDATE power_grids SET damaged=1,charge=0,updated_ts=?
                                       WHERE owner_type='house' AND owner_id=?""",
                                    (ts, house["id"]))
                    else:
                        db_.execute(
                            f"UPDATE {table} SET {column}=0 WHERE {id_col}=?",
                            (id_value,))
                    parts.append(f"{label}被毁")
                elif facilities and facility_saved:
                    parts.append("抢修小组保住了设施")

                # 只抢常规、可补充资源；北辰信标、戒指、遗物等主线/家族物品永不进入名单。
                loot_rows = db_.execute(
                    """SELECT resource_key,amount FROM house_inventory
                       WHERE house_id=? AND amount>0""", (house["id"],)).fetchall()
                loot_rows = [r for r in loot_rows
                             if r["resource_key"] in HOUSE_RAID_STEALABLE]
                raid_rng.shuffle(loot_rows)
                stolen = []
                for loot in loot_rows[:3]:
                    rate = raid_rng.uniform(.04, .10) if stance == "storage" else raid_rng.uniform(.12, .28)
                    amount = min(loot["amount"], max(1, int(math.ceil(loot["amount"] * rate))))
                    db_.execute("""UPDATE house_inventory SET amount=MAX(0,amount-?)
                                   WHERE house_id=? AND resource_key=?""",
                                (amount, house["id"], loot["resource_key"]))
                    label = ITEM_NAMES.get(
                        loot["resource_key"],
                        RESOURCES.get(loot["resource_key"], (loot["resource_key"],))[0])
                    stolen.append(f"{label}x{amount}")
                if stolen:
                    parts.append("仓库失窃" + "、".join(stolen))
            if stance == "lure":
                lure_damage = max(1, int(math.ceil(attack * .10)))
                character_damage += lure_damage
                db_.execute("UPDATE characters SET hp=MAX(0,hp-?) WHERE id=?",
                            (lure_damage, ch["id"]))
                db_.execute("""UPDATE map_regions
                               SET noise=MAX(0,noise-4),threat=MAX(0,threat-4),updated_ts=?
                               WHERE region_x=? AND region_y=?""",
                            (ts, rx, ry))
                parts.append(f"主动诱敌使角色HP-{lure_damage}、区域威胁额外-4")
            if character_damage:
                parts.append(f"角色HP-{character_damage}")
            summary = "；".join(parts) + "。"
            db_.execute("""INSERT INTO house_raid_logs
                           (house_id,character_id,day_count,attack_strength,counter_damage,
                            structure_damage,character_damage,summary,created_ts)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (house["id"], ch["id"], ws["day_count"], attack, counter_damage,
                         structure_damage, character_damage, summary, ts))
            db_.execute("""INSERT INTO action_log(character_id,action,detail,created_ts)
                           VALUES(?,'house_raid',?,?)""", (ch["id"], summary, ts))
        else:
            dmg = int(min(30, strength))
            traits = db_.execute("SELECT trait_a,trait_b FROM character_profiles WHERE character_id=?",
                                 (ch["id"],)).fetchone()
            if traits and "tough" in (traits["trait_a"], traits["trait_b"]):
                dmg = max(0, int(dmg * 0.85))
            new_hp = max(0, ch["hp"] - dmg)
            db_.execute("UPDATE characters SET hp=? WHERE id=?", (new_hp, ch["id"]))
    # 一次尸潮会消耗掉部分聚集尸群，但不会让区域瞬间安全。
    for rx, ry in raided_regions:
        db_.execute("""UPDATE map_regions
                       SET noise=MAX(0,noise-3),threat=MAX(0,threat-5),updated_ts=?
                       WHERE region_x=? AND region_y=?""", (ts, rx, ry))
    db_.commit()
    for row in db_.execute("SELECT id, hp FROM characters WHERE status='alive' AND hp<=0").fetchall():
        db_.commit()
        kill_character(row["id"], reason="夜袭")
