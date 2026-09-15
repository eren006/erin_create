# 九霄仙门 —— 境界表 / 门内档位表 / 称号生成 / 资质(灵根·血脉·传承·仙骨) · 纯静态设计数据,不掺业务逻辑

import random

# ── 境界表:单轴修为阶梯,炼气→筑基→金丹→元婴→化神→合体→大乘 ──────────────────────

REALMS = [
    {'name': '炼气一层', 'exp': 0,      'major': '炼气'},
    {'name': '炼气二层', 'exp': 150,    'major': '炼气'},
    {'name': '炼气三层', 'exp': 400,    'major': '炼气'},
    {'name': '筑基初期', 'exp': 800,    'major': '筑基'},
    {'name': '筑基中期', 'exp': 1500,   'major': '筑基'},
    {'name': '筑基后期', 'exp': 2600,   'major': '筑基'},
    {'name': '金丹初期', 'exp': 4500,   'major': '金丹'},
    {'name': '金丹中期', 'exp': 7000,   'major': '金丹'},
    {'name': '金丹后期', 'exp': 12000,  'major': '金丹'},
    # 金丹之后(元婴起)整体拉长约1.5倍——后期角色打坐加成叠得多,单次收益早已不是这条曲线
    # 刚设计时的量级,不拉长的话金丹之后会明显比前面几个大境界快。金丹后期又单独上调到12000后,
    # 后面各档跟着小涨一截,免得金丹后期突然比元婴初期近太多,曲线接不顺。
    {'name': '元婴初期', 'exp': 24000,  'major': '元婴'},
    {'name': '元婴中期', 'exp': 35000,  'major': '元婴'},
    {'name': '元婴后期', 'exp': 49000,  'major': '元婴'},
    # 化神起,每档之间的修为差距统一翻倍(原26000/36000/48000/65000/81000/126000 全部×2),
    # 渡劫这条路本就该磨得更久,呼应上面 BREAKTHROUGH_CHANCE 化神起-20%那条改动。
    {'name': '化神初期', 'exp': 68000,  'major': '化神'},
    {'name': '化神中期', 'exp': 120000, 'major': '化神'},
    {'name': '化神后期', 'exp': 192000, 'major': '化神'},
    {'name': '合体初期', 'exp': 288000, 'major': '合体'},
    {'name': '合体中期', 'exp': 418000, 'major': '合体'},
    {'name': '合体后期', 'exp': 580000, 'major': '合体'},
    {'name': '大乘圆满', 'exp': 832000, 'major': '大乘'},
]

MAX_REALM_INDEX = len(REALMS) - 1
MAJOR_REALMS = ['炼气', '筑基', '金丹', '元婴', '化神', '合体', '大乘']

# 突破大境界(如炼气→筑基)的成功率,按当前所在大境界下标索引;境界越高越难突破。
# 化神(4)起再统一-20个百分点,渡劫化神之后的路本就该比前面更难走。
BREAKTHROUGH_CHANCE = {0: 1.0, 1: 0.9, 2: 0.75, 3: 0.6, 4: 0.25, 5: 0.10, 6: 0.05}

# 打坐基础修为随大境界的倍率:境界差距是几何级增长的(约每级×2.5~3),若单次收益不跟着涨,
# 后期一次突破要点几千次才够,体验会从"修仙"退化成"点击疲劳"。按大境界下标索引,乘算生效。
BASE_EXP_REALM_MULT = {0: 1, 1: 2.5, 2: 6, 3: 15, 4: 35, 5: 80, 6: 160}

def realm_by_index(index):
    index = max(0, min(index or 0, MAX_REALM_INDEX))
    return REALMS[index]

def realm_major_idx(index):
    return MAJOR_REALMS.index(realm_by_index(index)['major'])

# ── 突破仪式:修为攒够后手动触发的独立动作,不再是打坐时的隐形副骰 ──────────────────
# 失败不扣修为(只扣心境+耗体力),且带保底:连续失败达到 GUARANTEE_STREAK 后,下一次必成,
# 保证"不会无限卡关"；心境濒临失控时,失败还可能触发心魔小事件,但每个事件都留一条稳妥选择。

BREAKTHROUGH_STAMINA_COST = 20
BREAKTHROUGH_FAIL_MIND_PENALTY = 5      # 单纯突破失败的心境代价;保底封顶3次,故最多损失15点(不含心魔)
BREAKTHROUGH_PITY_INCREMENT_PCT = 15    # 每连续失败一次,下次尝试成功率 +15 个百分点
BREAKTHROUGH_PITY_GUARANTEE_STREAK = 3  # 连续失败达到3次后,第4次尝试必定成功("绝境顿悟")
BREAKTHROUGH_ASSIST_CONTRIBUTION_COST = 60  # 花贡献向丹房求援一枚"护脉丹",一次性+15%成功率
BREAKTHROUGH_ASSIST_BONUS_PCT = 15
BREAKTHROUGH_ASSIST_MIND_PROTECT = 3    # 护脉丹额外效果:即使突破仍失败,心境损失也减免3点(5→2)

# 保底阶段的叙事包装,界面同时显示准确概率,不只是干巴巴的失败次数计数器
PITY_STAGE_FLAVOR = {0: '', 1: '灵机渐明', 2: '道心凝练', 3: '绝境顿悟'}

def pity_stage_label(streak, guarantee_streak):
    return PITY_STAGE_FLAVOR.get(min(streak, guarantee_streak), '绝境顿悟')

MIND_DEMON_TRIGGER_MIND_THRESHOLD = 25  # 突破失败后,心境低于此值才可能触发心魔
MIND_DEMON_TRIGGER_CHANCE = 0.4

# 心魔事件:与探索事件同构(text+choices,每个choice有success_rate/success/fail两组奖惩),
# 但每个事件都保留一条 success_rate=1.0 的稳妥选择,不会把玩家逼上纯博概率的独木桥。
# 通用池人人可触发;个性池按角色境遇(有师父/有道侣/身负血脉)额外加入候选,让心魔更贴角色。
MIND_DEMON_EVENTS_GENERIC = [
    {'key': 'demon_doubt', 'text': '突破受挫的刹那,一缕心魔自识海深处悄然滋生,反复低语着你的不堪与不甘。',
     'choices': [
        {'key': 'suppress', 'label': '强行镇压心魔', 'success_rate': 0.5,
         'success': {'mind_state': 20}, 'fail': {'mind_state': -8}},
        {'key': 'accept', 'label': '坦然接纳,与之对话', 'success_rate': 1.0,
         'success': {'mind_state': 10}, 'fail': {}}]},
    {'key': 'demon_fear', 'text': '心魔幻化作你最恐惧的模样,张牙舞爪,试图动摇你的道心。',
     'choices': [
        {'key': 'face', 'label': '直面恐惧,与之一战', 'success_rate': 0.55,
         'success': {'mind_state': 18, 'physique': 1}, 'fail': {'mind_state': -8}},
        {'key': 'chant', 'label': '闭目诵持本命心经', 'success_rate': 1.0,
         'success': {'mind_state': 8, 'stamina': -5}, 'fail': {}}]},
    {'key': 'demon_temptation', 'text': '心魔化作一道旁门捷径,声称可助你速成大道,只是代价隐晦不明。',
     'choices': [
        {'key': 'refuse', 'label': '断然拒绝', 'success_rate': 1.0,
         'success': {'mind_state': 10}, 'fail': {}},
        {'key': 'listen', 'label': '姑且一听,窥探虚实', 'success_rate': 0.4,
         'success': {'exp': 15, 'mind_state': 5}, 'fail': {'mind_state': -10}}]},
    {'key': 'demon_despair', 'text': '屡屡受挫的沮丧几乎将你淹没,心魔趁虚而入,低语着"放弃罢"。',
     'choices': [
        {'key': 'push', 'label': '咬牙撑过去', 'success_rate': 0.6,
         'success': {'mind_state': 15}, 'fail': {'mind_state': -6}},
        {'key': 'rest', 'label': '放下执念,先歇息静养', 'success_rate': 1.0,
         'success': {'mind_state': 8, 'stamina': 10}, 'fail': {}}]},
]
MIND_DEMON_EVENT_MENTOR = {
    'key': 'demon_mentor', 'text': '心魔化作你的模样,质问你:若无师父悉心指点,你当真能走到今天吗?',
    'choices': [
        {'key': 'trust_self', 'label': '师父引路,道却是自己走的', 'success_rate': 0.55,
         'success': {'mind_state': 18}, 'fail': {'mind_state': -8}},
        {'key': 'grateful', 'label': '坦然承认师恩,不必自欺', 'success_rate': 1.0,
         'success': {'mind_state': 10, 'reputation': 2}, 'fail': {}}]}
MIND_DEMON_EVENT_COMPANION = {
    'key': 'demon_companion', 'text': '心魔幻化道侣模样,含泪逼问:大道与情意,你只能择其一。',
    'choices': [
        {'key': 'both', 'label': '道侣亦是道,不必取舍', 'success_rate': 0.5,
         'success': {'mind_state': 20}, 'fail': {'mind_state': -8}},
        {'key': 'firm', 'label': '心知是幻象,一笑置之', 'success_rate': 1.0,
         'success': {'mind_state': 10}, 'fail': {}}]}
MIND_DEMON_EVENT_BLOODLINE = {
    'key': 'demon_bloodline', 'text': '体内先祖血脉之意悄然苏醒,意图借你突破之际夺舍此身。',
    'choices': [
        {'key': 'resist', 'label': '强压先祖意志,守住本心', 'success_rate': 0.5,
         'success': {'mind_state': 20, 'physique': 1}, 'fail': {'mind_state': -8}},
        {'key': 'commune', 'label': '静心与之沟通,寻求共存', 'success_rate': 1.0,
         'success': {'mind_state': 10}, 'fail': {}}]}
MIND_DEMON_EVENTS = MIND_DEMON_EVENTS_GENERIC + [
    MIND_DEMON_EVENT_MENTOR, MIND_DEMON_EVENT_COMPANION, MIND_DEMON_EVENT_BLOODLINE]

def pick_mind_demon_event(has_mentor, has_companion, has_bloodline):
    pool = list(MIND_DEMON_EVENTS_GENERIC)
    if has_mentor:
        pool.append(MIND_DEMON_EVENT_MENTOR)
    if has_companion:
        pool.append(MIND_DEMON_EVENT_COMPANION)
    if has_bloodline:
        pool.append(MIND_DEMON_EVENT_BLOODLINE)
    return random.choice(pool)

# ── 渡劫:大境界跨越时的专属描述,金丹起全宗广播,大乘圆满是全宗瞩目的天劫高潮 ──────────

TRIBULATION_FLAVOR = {
    '筑基': '气机自涌,灵气如潮水般涌入四肢百骸,脱去凡胎。',
    '金丹': '丹田气旋骤然凝实,一点金光透体而出,金丹已成。',
    '元婴': '识海之中元婴虚影初现,已具阳神出窍、离体重塑之能。',
    '化神': '天地灵气不受控地向其汇聚,神魂与虚空隐隐共鸣。',
    '合体': '虚空似有异动,灵气化作实质缠身,神魂肉身渐趋合一。',
    '大乘': '九霄之上乌云骤聚,紫雷接连劈落,一劫接一劫,强渡九重天劫方成大乘圆满!',
}
MAJOR_BROADCAST_MIN_IDX = 2  # 大境界下标(0炼气...6大乘),达到此值起,突破全宗广播

# ── 护法:突破时可邀一人陪同,效果按关系而非个人,不叠加同类,与护脉丹(贡献辅助)可共存 ──

GUARDIAN_TYPES = {
    'mentor':    {'label': '师父陪同', 'desc': '突破率+5%,失败时另减免2点心境',
                  'chance_bonus_pct': 5, 'mind_protect': 2},
    'companion': {'label': '道侣陪同', 'desc': '失败时另减免3点心境',
                  'chance_bonus_pct': 0, 'mind_protect': 3},
    'sworn':     {'label': '义结金兰陪同', 'desc': '突破率+5%',
                  'chance_bonus_pct': 5, 'mind_protect': 0},
    'peer':      {'label': '同峰同门陪同', 'desc': '突破率+3%',
                  'chance_bonus_pct': 3, 'mind_protect': 0},
}
GUARDIAN_ORDER = ['mentor', 'companion', 'sworn', 'peer']

# ── 凝丹:筑基→金丹不再是常规突破,而是"选品质备料→渡劫"的专属大关,直接取代那一次突破 ──
# 品质在渡劫成功那一刻定型,伴随终身(可后期重金升炼),随机性只决定"这次渡劫成不成",
# 不决定"能不能选高品质"——想冲极品金丹,备够料就能试,试不成也保底,不会被纯运气卡死。

DAN_STAMINA_COST = 25
DAN_PITY_INCREMENT_PCT = 15
DAN_PITY_GUARANTEE_STREAK = 4
DAN_FAIL_MIND_PENALTY = 5
DAN_WARD_MATERIAL = 'jindan_ward'      # 辅助材料:渡劫时可选消耗,提高这次成功率
DAN_WARD_CHANCE_BONUS_PCT = 10
DAN_CORE_MATERIAL = 'jindan_core'      # 突破核心:筑基秘境(赤炎洞窟)稳定积累或兑换获得
DAN_FORTUNE_MATERIAL = 'jindan_fortune'  # 奇遇材料:只从秘境仙缘产出,极品金丹专用,不设兑换
DAN_CORE_EXCHANGE = {'from': 'chiyan_ore', 'rate': 20}   # 20个赤炎矿核 兑 1个金丹引,保底不必靠运气
DAN_WARD_EXCHANGE = {'from': 'chiyan_ore', 'rate': 6}
DAN_CORE_CONTRIBUTION_COST = 200  # 花贡献兑金丹引,给完全不碰秘境的人留一条路,一辈子仅此一次

DAN_QUALITIES = {
    'low':  {'label': '下品金丹', 'base_chance': 0.85,
             'cost': {'low': 10, 'mid': 5},
             'bonus': {'attack': 2, 'defense': 2, 'exp_bonus_pct': 0}},
    'mid':  {'label': '中品金丹', 'base_chance': 0.65,
             'cost': {'mid': 15, 'high': 5, 'jindan_core': 1},
             'bonus': {'attack': 5, 'defense': 5, 'exp_bonus_pct': 2}},
    'high': {'label': '上品金丹', 'base_chance': 0.45,
             'cost': {'high': 15, 'jindan_core': 3},
             'bonus': {'attack': 10, 'defense': 10, 'exp_bonus_pct': 4}},
    'top':  {'label': '极品金丹', 'base_chance': 0.25,
             'cost': {'high': 10, 'jindan_core': 5, 'jindan_fortune': 1},
             'bonus': {'attack': 18, 'defense': 18, 'exp_bonus_pct': 7}},
}
DAN_QUALITY_ORDER = ['low', 'mid', 'high', 'top']
DAN_UPGRADE_LINGSHI_COST = 800    # 后期花大价钱把已成型的金丹品质升一级,材料同该品质本身的cost

def dan_pity_bonus_pct(streak):
    return min(streak, DAN_PITY_GUARANTEE_STREAK) * DAN_PITY_INCREMENT_PCT

DAN_NATURAL_CHANCE_CAP_PCT = 60  # 不吃护丹符时,连续失败加成最多把成功率顶到这个数——本身底子(下品/中品)已经超过此值的不受影响,
# 只封顶上品/极品靠连续失败堆起来的部分;想再往上冲只能靠护丹符(DAN_WARD_CHANCE_BONUS_PCT)。

def dan_natural_chance(quality_key, streak):
    base = DAN_QUALITIES[quality_key]['base_chance']
    return max(base, min(DAN_NATURAL_CHANCE_CAP_PCT / 100, base + dan_pity_bonus_pct(streak) / 100))

DAN_SUCCESS_FLAVORS = ['丹田金光大盛,气机骤然收束,金丹一朝凝就!', '一声轻鸣自丹田传出,金丹终于凝形!',
                       '悬着的心骤然落地,道基稳固,金丹凝就!']
DAN_FAIL_FLAVORS = ['金丹迟迟不肯凝形,气机涣散,只得作罢', '眼看金丹将成,却在最后一线功亏一篑',
                    '灵气几番凝而复散,金丹终究未能落定']

# ── 化婴:金丹→元婴取代常规突破,拆成"备料→心魔试炼→碎丹→渡雷劫"四段,只有最后渡劫才是
# 真正随机的关卡,前三段做完就锁定进度,渡劫哪怕失败也不会打回原形,只需再渡一次 ────────

INFANT_STAMINA_COST = 30
INFANT_PITY_INCREMENT_PCT = 15
INFANT_PITY_GUARANTEE_STREAK = 4
INFANT_TRIBULATION_BASE_CHANCE = 0.5
INFANT_FAIL_WEAKEN_HOURS = 4          # 渡劫失败后的虚弱状态持续时间,可用丹药或等时间恢复
INFANT_RECOVER_LINGSHI_COST = 150     # 服丹立即清除虚弱,不必干等
INFANT_FAIL_MIND_PENALTY = 6
INFANT_GATHER_COST = {'high': 20, 'yuanying_core': 3}
INFANT_WARD_MATERIAL = 'yuanying_ward'
INFANT_WARD_CHANCE_BONUS_PCT = 10
INFANT_CORE_MATERIAL = 'yuanying_core'    # 突破核心:金丹秘境(古修洞府)稳定积累或兑换获得
INFANT_FORTUNE_MATERIAL = 'yuanying_fortune'
INFANT_CORE_EXCHANGE = {'from': 'guxiu_rune', 'rate': 20}
INFANT_WARD_EXCHANGE = {'from': 'guxiu_rune', 'rate': 6}
INFANT_CORE_CONTRIBUTION_COST = 200  # 花贡献兑元婴引,与金丹引那条路同一规格,给不碰秘境的人留路,一辈子仅此一次

# 灵巧/防御/气血/本命法宝都折算成渡劫成功率或减伤的加成,不额外做一套战斗系统
INFANT_AGILITY_CHANCE_PER_POINT = 0.005
INFANT_DEFENSE_MIND_MITIGATION_PER_POINT = 0.02   # 防御越高,渡劫失败的心境损失打折越多
INFANT_DEFENSE_MIND_MITIGATION_CAP_PCT = 50
INFANT_ARTIFACT_CORE_CHANCE_PER_LEVEL = 0.5       # 本命法宝(尤其防护方向)按等级给渡劫加成
INFANT_TRIAL_BOLD_MIND_COST = 5
INFANT_TRIAL_BUFF_CHANCE_BONUS_PCT = 8   # 心魔试炼选"直面"拿到的渡劫临时加成

def infant_pity_bonus_pct(streak):
    return min(streak, INFANT_PITY_GUARANTEE_STREAK) * INFANT_PITY_INCREMENT_PCT

INFANT_SUCCESS_FLAVORS = ['雷光在识海中炸开又骤然平息,元婴稳稳凝立!', '天雷淬体而过,金丹尽碎,元婴破丹而出!',
                          '劫云散尽,元婴端坐丹田,气息焕然一新!']
INFANT_FAIL_FLAVORS = ['雷劫将至未至,一道天雷擦身而过,你侥幸未死却也元气大伤',
                       '心魔于雷光中乘隙而入,你勉强按下心神,雷劫未能渡过',
                       '天雷骤然改道,劈碎了你几分准备,只得铩羽而归']

# ── 化神:元婴→化神同样取代常规突破,沿用凝丹那套"选品级备料→渡劫"两段式;
# 品级材料改从元婴门槛秘境(葬剑遗址)积累/兑换,呼应"对应境界秘境"的原则 ─────────────────

SHEN_STAMINA_COST = 35
SHEN_PITY_INCREMENT_PCT = 15
SHEN_PITY_GUARANTEE_STREAK = 4
SHEN_FAIL_MIND_PENALTY = 6
SHEN_WARD_MATERIAL = 'shenhua_ward'
SHEN_WARD_CHANCE_BONUS_PCT = 10
SHEN_CORE_MATERIAL = 'shenhua_core'
SHEN_CORE_EXCHANGE = {'from': 'zangjian_shard', 'rate': 20}
SHEN_WARD_EXCHANGE = {'from': 'zangjian_shard', 'rate': 6}
# 渡厄珠:化神的硬性门槛材料,不设兑换,只在葬剑遗址仙缘·闯关成功时概率巧遇;
# 没有这一味就凑不齐化神的准备材料,元婴期需要前往秘境寻觅仙缘,不能纯靠兑换堆出来。
SHEN_GATE_MATERIAL = 'du_e_zhu'

# 不再分品级——原先低/中/上/极品四档,极品那档要卡"化神奇珍"这个只能在葬剑遗址小概率巧遇的
# 稀有材料,门槛太刁钻。现在只有一档,取消化神奇珍,改用"渡厄珠"当硬性门槛材料。
SHEN_QUALITIES = {
    'standard': {'label': '化神', 'base_chance': 0.40,
                 'cost': {'zangjian_shard': 15, 'shenhua_core': 3, 'du_e_zhu': 1},
                 'bonus': {'attack': 22, 'defense': 22, 'exp_bonus_pct': 6}},
}
SHEN_QUALITY_ORDER = ['standard']
SHEN_UPGRADE_LINGSHI_COST = 1500

def shen_pity_bonus_pct(streak):
    return min(streak, SHEN_PITY_GUARANTEE_STREAK) * SHEN_PITY_INCREMENT_PCT

SHEN_SUCCESS_FLAVORS = ['神魂淬炼而出金光,化神一朝功成!', '识海骤然澄澈,神魂脱胎换骨!', '一道清明贯穿识海,化神大成!']
SHEN_FAIL_FLAVORS = ['神魂几度欲凝还散,终究未能功成', '识海中灵光乍现又骤然熄灭,只得重新蛰伏',
                     '神魂淬炼功亏一篑,只得暂且作罢']

# ── 合体:化神→合体沿用化婴那套"备料→试炼→融合→天劫"四段式;门槛材料改从化神门槛秘境
# 九幽渊(realm_req化神起)取,呼应"对应境界秘境"的原则,不再借用化神那档的化神引 ──────────

HETI_STAMINA_COST = 40
HETI_PITY_INCREMENT_PCT = 15
HETI_PITY_GUARANTEE_STREAK = 4
HETI_TRIBULATION_BASE_CHANCE = 0.5
HETI_FAIL_WEAKEN_HOURS = 5
HETI_RECOVER_LINGSHI_COST = 250
HETI_FAIL_MIND_PENALTY = 7
HETI_GATHER_COST = {'zangjian_shard': 20, 'heti_core': 5, 'jiuyou_crystal': 3, 'top': 2}
HETI_WARD_MATERIAL = 'heti_ward'
HETI_WARD_CHANCE_BONUS_PCT = 10
HETI_CORE_MATERIAL = 'heti_core'
# 合体引比化神引金贵得多:除了九幽渊稳定积累的幽渊魂晶,还要搭上游历传说奇遇才出的器灵丝,
# 逼着玩家不能只闷头刷秘境,也得去人间走一走碰运气。
HETI_CORE_EXCHANGE = {'jiuyou_crystal': 15, 'artifact_soul_thread': 5}
HETI_WARD_EXCHANGE = {'zangjian_shard': 6}

HETI_AGILITY_CHANCE_PER_POINT = 0.005
HETI_DEFENSE_MIND_MITIGATION_PER_POINT = 0.02
HETI_DEFENSE_MIND_MITIGATION_CAP_PCT = 50
HETI_ARTIFACT_CORE_CHANCE_PER_LEVEL = 0.5
HETI_TRIAL_BOLD_MIND_COST = 6
HETI_TRIAL_BUFF_CHANCE_BONUS_PCT = 8
# 子嗣及冠及笄(realm_idx>=6,见 OFFSPRING_STAGE_BY_REALM)后视作真正独当一面,渡合体天劫时
# 每位+5%成功率,亲情这一项在95%常规上限之外单独结算,不受该上限压制;
# 但子嗣数量本身没有硬上限,单独给这一项加个+20%的封顶,防止子嗣多的人无限堆到接近保底。
HETI_CHILD_ADULT_REALM_IDX = 6
HETI_CHILD_ADULT_CHANCE_BONUS_PCT = 5
HETI_CHILD_ADULT_CHANCE_BONUS_MAX_PCT = 20

def heti_pity_bonus_pct(streak):
    return min(streak, HETI_PITY_GUARANTEE_STREAK) * HETI_PITY_INCREMENT_PCT

HETI_SUCCESS_FLAVORS = ['天雷贯体而过,神魔二相轰然相融!', '劫云破碎,你于雷光中傲然而立,合体大成!',
                        '雷劫尽渡,本我与真我终归为一!']
HETI_FAIL_FLAVORS = ['天雷猝然改道,狠狠劈中要害,你狼狈脱身', '本我与真我在雷光中再度分裂,合体功亏一篑',
                     '劫云翻涌,一道天雷擦身而过,你元气大伤']

BREAKTHROUGH_MATERIAL_LABELS = {
    'jindan_core': '金丹引', 'jindan_ward': '护丹符', 'jindan_fortune': '金丹奇药',
    'yuanying_core': '元婴引', 'yuanying_ward': '护婴符', 'yuanying_fortune': '元婴异宝',
    'shenhua_core': '化神引', 'shenhua_ward': '护神符', 'du_e_zhu': '渡厄珠',
    'heti_ward': '合体护符', 'heti_core': '合体引',
}

# ── 门内档位表:外门→普通→内门→亲传(拜师入峰)→执事→长老(名额有限)→掌门(唯一,仅继任产生) ──

RANKS = [
    {'tier': 0, 'key': 'outer',    'label': '外门弟子', 'realm_req': 0,  'contribution_req': 0,    'reputation_req': 0,
     'exam_success_rate': None, 'seat_cap': None},
    {'tier': 1, 'key': 'regular',  'label': '普通弟子', 'realm_req': 3,  'contribution_req': 30,   'reputation_req': 10,
     'exam_success_rate': 1.0,  'seat_cap': None},
    {'tier': 2, 'key': 'inner',    'label': '内门弟子', 'realm_req': 6,  'contribution_req': 150,  'reputation_req': 40,
     'exam_success_rate': 0.8,  'seat_cap': None},
    {'tier': 3, 'key': 'mentee',   'label': '亲传弟子', 'realm_req': 9,  'contribution_req': 500,  'reputation_req': 100,
     'exam_success_rate': 0.6,  'seat_cap': None},
    {'tier': 4, 'key': 'steward',  'label': '执事',     'realm_req': 10, 'contribution_req': 900,  'reputation_req': 200,
     'exam_success_rate': 0.5,  'seat_cap': None},
    {'tier': 5, 'key': 'elder',    'label': '长老',     'realm_req': 12, 'contribution_req': 2000, 'reputation_req': 400,
     'exam_success_rate': 0.4,  'seat_cap': 7},
    {'tier': 6, 'key': 'leader',   'label': '掌门',     'realm_req': None, 'contribution_req': None, 'reputation_req': None,
     'exam_success_rate': None, 'seat_cap': 1},
]

MAX_EXAM_TIER = 5  # 掌门(tier 6)不可通过考核获得,只能由长老继任产生
MAX_DISCIPLES_PER_PEAK = 5
PEAK_TRANSFER_CONTRIBUTION_COST = 500  # 一生仅一次转峰机会,原峰专属功法作废;由掌门峰转出免费,视为纠错
PROMOTION_EXAM_DAILY_LIMIT = 2
CULTIVATE_COOLDOWN_SECONDS = 180
MENTOR_EXP_BONUS_PCT = 15  # 有师父在身,修炼修为收益加成百分比

# 打坐单次基础修为区间(乘境界倍率前);频率(冷却)不变,单纯调低每次产出,减慢整体修炼节奏
CULTIVATE_BASE_EXP_MIN = 14
CULTIVATE_BASE_EXP_MAX = 28
CULTIVATE_BASE_EXP_AVG = (CULTIVATE_BASE_EXP_MIN + CULTIVATE_BASE_EXP_MAX) / 2

# 打坐本身只受冷却限制,不耗体力——若不加节制,肝人一天能点出几十天的进度,把偶尔上线的人甩开一大截。
# 跟宗门委托同一套"每日前N次全额、之后打折"的软上限,而不是硬顶死,晚间多点几下仍有所得,不会觉得被卡死;
# 超过软上限后冷却也相应拉长,双重降低"多肝"的边际性价比,而不是只削数值。
CULTIVATE_DIMINISH_AFTER = 30
CULTIVATE_DIMINISH_MULT = 0.05
CULTIVATE_DIMINISH_COOLDOWN_MULT = 2.0
CULTIVATE_DIMINISH_HARD_CAP_EXTRA = 10  # 软上限之后最多再给10次的折扣收益,过了硬顶当天彻底不再产出

# 打坐提示语按大境界分池随机抽取,只换文案不改数值,避免高频点击时提示语一成不变显得"复读"。
# 下标对应 MAJOR_REALMS 的索引(炼气0→大乘6)。
CULTIVATE_FLAVORS = {
    0: ['吐纳之间,浊气渐消,灵息渐盈', '气息在丹田中缓缓流转', '打坐片刻,周身暖意渐生', '灵气如溪,涓涓汇入四肢百骸'],
    1: ['经脉隐隐发烫,道基又厚了几分', '灵气凝而不散,绕丹田游走一周', '气海微微翻涌,渐有波澜', '周身若有若无的道韵悄然浮动'],
    2: ['金丹微微一颤,似有回应', '丹田深处金光一闪即逝', '灵气化液,滋养周身经脉', '恍惚间似闻雷鸣,一闪即逝'],
    3: ['元婴稳坐丹田,气息与之共鸣', '神识微漾,似触到了某种边界', '灵气化风,绕元婴周身流转', '恍惚间似闻婴啼,转瞬即散'],
    4: ['神魂微颤,天地灵气竟自来朝', '识海泛起涟漪,灵光乍现', '体内灵气奔涌如江海', '恍惚间窥见一线天机,旋即消散'],
    5: ['本我与真我隐隐共鸣', '周身罡风自生,衣袍猎猎作响', '灵气化雷,在经脉中游走轰鸣', '天地灵气竟为之一滞,似在回避'],
    6: ['天地共鸣,灵气自四面八方汇聚而来', '周身隐有大道气象自然流露', '恍惚间似有仙音入耳', '灵气浩荡如潮,涌入体内亦不见满溢'],
}

# ── 峰:固定8峰,7长老峰+1掌门峰,创建时一次性写入 peaks 表,不再由玩家自主开峰 ────────

LEADER_PEAK_NAME = '凌霄峰'
ELDER_PEAK_NAMES = ['紫霄峰', '云海峰', '天枢峰', '玄穹峰', '太虚峰', '星阑峰', '沧澜峰']

# ── 开服NPC长老:7峰各配NPC长老候选池,免得开服头几天弟子拜入峰后无人可拜、无师可承;
# 待真实弟子考核达标、通过长老考核后即可将其顶替(见 app.py 的 is_npc 处理),不是永久占位。
# 每峰配两个候选人,后台补位时优先避开该峰上一任NPC的名字,免得"退隐"之后又立刻回锅 ──

NPC_ELDER_PROFILES = {
    '紫霄峰': [
        {'name': '苏挽月', 'gender': 'f', 'realm_idx': 12,
         'bio': '驯兽如友,座下灵宠皆通人性,峰中弟子人人以获她一句夸赞为荣。'},
        {'name': '柳惊蛰', 'gender': 'm', 'realm_idx': 13,
         'bio': '早年游历荒野驯服过一头凶兽,如今说起当年的伤疤反倒眉飞色舞。'},
    ],
    '云海峰': [
        {'name': '陆无尘', 'gender': 'm', 'realm_idx': 13,
         'bio': '一剑之下再无二话,峰规甚严,却最惜有剑骨之才的后辈。'},
        {'name': '霍青鸾', 'gender': 'f', 'realm_idx': 12,
         'bio': '出剑快、收剑更快,峰中弟子私下都说她的剑鞘比剑本身还神秘。'},
    ],
    '天枢峰': [
        {'name': '云若微', 'gender': 'f', 'realm_idx': 12,
         'bio': '丹炉三十载不熄火,尝遍百草,连坊市掌柜见了都要退避三分。'},
        {'name': '葛长庚', 'gender': 'm', 'realm_idx': 13,
         'bio': '炼丹走的是险中求胜的路子,炸炉次数比出丹次数还多,却屡屡有意外之喜。'},
    ],
    '玄穹峰': [
        {'name': '铁玄机', 'gender': 'm', 'realm_idx': 12,
         'bio': '打铁四十年,手上老茧比脸上皱纹还多,一句"凑合"是他对徒弟最高的评价。'},
        {'name': '容素心', 'gender': 'f', 'realm_idx': 13,
         'bio': '出身炼器世家,手上功夫一丝不苟,峰中弟子都怕她验收器物时的眼神。'},
    ],
    '太虚峰': [
        {'name': '沈知微', 'gender': 'f', 'realm_idx': 14,
         'bio': '闭关多过露面,偶尔现身也只与弟子谈道,从不多言旁事。'},
        {'name': '卫长风', 'gender': 'm', 'realm_idx': 12,
         'bio': '性子随和,打坐修行却极有章法,峰中弟子有难题多半会先去找他。'},
    ],
    '星阑峰': [
        {'name': '叶惊鸿', 'gender': 'm', 'realm_idx': 13,
         'bio': '来去如风,踪迹难寻,峰中弟子常说见他一面比进秘境还难。'},
        {'name': '姜白鹭', 'gender': 'f', 'realm_idx': 12,
         'bio': '探秘归来总爱带些稀奇玩意分给弟子,峰中气氛也因她活络不少。'},
    ],
    '沧澜峰': [
        {'name': '顾清欢', 'gender': 'f', 'realm_idx': 12,
         'bio': '广结善缘,三教九流皆有交情,峰中大小消息没有她不知道的。'},
        {'name': '慕容川', 'gender': 'm', 'realm_idx': 13,
         'bio': '嘴上总挂着"人情留一线",峰里峰外的人缘都是这么一点点攒出来的。'},
    ],
}

def pick_npc_elder_profile(peak_name, exclude_name=None):
    """从某峰的NPC长老候选池里挑一个,优先避开 exclude_name(通常是该峰刚退位的NPC)。"""
    pool = NPC_ELDER_PROFILES.get(peak_name)
    if not pool:
        return None
    candidates = [p for p in pool if p['name'] != exclude_name] or pool
    return random.choice(candidates)

# ── 峰特性:不同峰专精不同方向,弟子拜入后自动享有对应加成,选峰即选修行路线 ────────────

PEAK_SPECIALTIES = {
    '紫霄峰': {'theme': '灵宠峰', 'desc': '峰中豢养灵兽成风,弟子皆可收养灵宠、亲自训养使其成长。', 'pet': True},
    '云海峰': {'theme': '剑修峰', 'desc': '剑意纵横,弟子突破境界的成功率格外高。',
               'breakthrough_bonus_pct': 10},
    '天枢峰': {'theme': '丹道峰', 'desc': '丹炉常年不熄,弟子在宗门商店购物享有折扣,亦可亲自炼丹搏取厚报。',
               'shop_discount_pct': 20, 'alchemy': True},
    '玄穹峰': {'theme': '炼器峰', 'desc': '器械精良,弟子完成宗门委托收益更高,亦可亲自炼器搏取厚报。',
               'commission_bonus_pct': 15, 'forge': True},
    '太虚峰': {'theme': '修真峰', 'desc': '灵气浓郁至极,弟子打坐修炼收益冠绝诸峰。',
               'exp_bonus_pct': 15},
    '星阑峰': {'theme': '探秘峰', 'desc': '轻功卓绝,弟子入秘境时探索点数更足、遁符更多。',
               'mystic_stamina_bonus': 2, 'mystic_charm_bonus': 1},
    '沧澜峰': {'theme': '交际峰', 'desc': '广结善缘,弟子获取宗门声望的效率更高。',
               'reputation_bonus_pct': 50},
    '凌霄峰': {'theme': '掌门峰', 'desc': '掌门亲传,兼修各家之长,弟子修为、突破、委托、声望皆有加成。',
               'exp_bonus_pct': 10, 'breakthrough_bonus_pct': 5,
               'commission_bonus_pct': 10, 'reputation_bonus_pct': 20},
}

def peak_specialty(peak_name):
    return PEAK_SPECIALTIES.get(peak_name, {})

# ── 峰专属功法:拜入某峰即自动习得该峰唯一功法,与通用三式并列可选,选峰=选修行路线 ──────
# 字段含义与 CULTIVATE_METHODS 一致(exp_mult/mind_delta/mishap_pct/cooldown_mult/epiphany_pct)

PEAK_TECHNIQUES = {
    '紫霄峰': {'key': 'zixiao_linghu',   'label': '灵犀共鸣诀', 'exp_mult': 1.35, 'mind_delta': 1,
               'mishap_pct': 0,    'cooldown_mult': 1.0, 'epiphany_pct': 0,
               'element': 'wood',  'atk_mod': 1.0, 'def_mod': 1.0},
    '云海峰': {'key': 'yunhai_jianxin',  'label': '剑心通明诀', 'exp_mult': 1.5,  'mind_delta': -1,
               'mishap_pct': 0.05, 'cooldown_mult': 1.0, 'epiphany_pct': 0.08,
               'element': 'metal', 'atk_mod': 1.15, 'def_mod': 0.9},
    '天枢峰': {'key': 'tianshu_ningdan', 'label': '凝丹诀',     'exp_mult': 1.3,  'mind_delta': 2,
               'mishap_pct': 0,    'cooldown_mult': 1.0, 'epiphany_pct': 0,
               'element': 'fire',  'atk_mod': 1.0, 'def_mod': 1.0},
    '玄穹峰': {'key': 'xuanqiong_cuiti', 'label': '淬体炼形诀', 'exp_mult': 1.35, 'mind_delta': 1,
               'mishap_pct': 0,    'cooldown_mult': 1.0, 'epiphany_pct': 0,
               'element': 'earth', 'atk_mod': 0.9, 'def_mod': 1.2},
    '太虚峰': {'key': 'taixu_guiyi',     'label': '太虚归一诀', 'exp_mult': 1.7,  'mind_delta': 0,
               'mishap_pct': 0.05, 'cooldown_mult': 1.0, 'epiphany_pct': 0.05,
               'element': None,    'atk_mod': 1.0, 'def_mod': 1.0},
    '星阑峰': {'key': 'xinglan_jifeng',  'label': '疾风回气诀', 'exp_mult': 1.15, 'mind_delta': 1,
               'mishap_pct': 0,    'cooldown_mult': 0.6, 'epiphany_pct': 0,
               'element': 'wood',  'atk_mod': 1.05, 'def_mod': 0.95},
    '沧澜峰': {'key': 'canglan_tongxin', 'label': '同心共修诀', 'exp_mult': 1.25, 'mind_delta': 4,
               'mishap_pct': 0,    'cooldown_mult': 1.0, 'epiphany_pct': 0,
               'element': 'water', 'atk_mod': 0.95, 'def_mod': 1.05},
    '凌霄峰': {'key': 'lingxiao_guixu',  'label': '九霄归墟诀', 'exp_mult': 1.6,  'mind_delta': 1,
               'mishap_pct': 0,    'cooldown_mult': 1.0, 'epiphany_pct': 0.1,
               'element': None,    'atk_mod': 1.08, 'def_mod': 0.95},
}
PEAK_TECHNIQUES_BY_KEY = {t['key']: t for t in PEAK_TECHNIQUES.values()}

def peak_technique(peak_name):
    return PEAK_TECHNIQUES.get(peak_name)

# ── 功法篇章:功法效果随大境界"多修一篇"而增长,不需要额外操作,纯粹跟着境界走 ───────────

TECHNIQUE_CHAPTER_PCT_PER_MAJOR = 5  # 每提升一个大境界,功法修为倍率再+5%(炼气0%→大乘30%)

def technique_chapter_pct(realm_idx):
    return realm_major_idx(realm_idx) * TECHNIQUE_CHAPTER_PCT_PER_MAJOR

# 篇章×熟练度×契合度三层是相乘关系,叠加师徒/羁绊/血脉等本就相加的加成后,后期差距会被
# 放得很大;这里给三层相乘的结果封顶,只砍最顶端的极限值,不影响熟练度不够时的正常曲线。
TECHNIQUE_LAYER_MULT_CAP = 1.4

# ── 功法契合度:自己峰的功法天然契合;机缘习得的旁门功法看五行是否匹配变异体质 ──────────

TECHNIQUE_OWN_PEAK_AFFINITY = 95       # 自己峰的根本功法,固定"天作之合"档(本命功法理应是最高契合)
TECHNIQUE_LEARNED_BASE_AFFINITY = 50   # 机缘习得的旁门功法基础"尚算契合"档
TECHNIQUE_ELEMENT_MATCH_BONUS = 25     # 五行匹配变异体质时的加成

TECHNIQUE_AFFINITY_BANDS = [
    (0, 49, '勉强可修', -10), (50, 69, '尚算契合', 0), (70, 89, '如鱼得水', 5), (90, 100, '天作之合', 10),
]

def technique_affinity_band(score):
    for lo, hi, label, pct in TECHNIQUE_AFFINITY_BANDS:
        if lo <= score <= hi:
            return label, pct
    return TECHNIQUE_AFFINITY_BANDS[1][2], TECHNIQUE_AFFINITY_BANDS[1][3]

# ── 功法熟练度:0-100,用得越多越熟练,顿悟额外加经验 ───────────────────────────────

TECHNIQUE_MASTERY_MAX = 100
TECHNIQUE_MASTERY_GAIN = 1
TECHNIQUE_MASTERY_EPIPHANY_GAIN = 5
TECHNIQUE_MASTERY_BANDS = [
    (0, 9, 50), (10, 24, 70), (25, 49, 85), (50, 74, 100), (75, 99, 110), (100, 100, 120),
]

def technique_mastery_pct(mastery):
    mastery = max(0, min(mastery or 0, TECHNIQUE_MASTERY_MAX))
    for lo, hi, pct in TECHNIQUE_MASTERY_BANDS:
        if lo <= mastery <= hi:
            return pct
    return 100

TECHNIQUE_MASTERY_NEAR_PERFECT_LO = 95
TECHNIQUE_MASTERY_NEAR_PERFECT_HI = 99
TECHNIQUE_MASTERY_NEAR_PERFECT_TEXT = '此诀你已近乎信手拈来,真意仿佛近在咫尺,只差一线便可大成'

# ── 入定连击:连续以同一功法打坐会渐入佳境,换功法即断,每日/每小境界皆重新开始 ────────────

MEDITATION_STREAK_STEP_PCT = 2
MEDITATION_STREAK_MAX_BONUS_PCT = 20

def meditation_streak_bonus_pct(streak):
    return min(MEDITATION_STREAK_MAX_BONUS_PCT, max(0, streak) * MEDITATION_STREAK_STEP_PCT)

# ── 功法机缘:内门弟子起,打坐时小概率习得一门本峰以外的功法,长老概率翻倍 ──────────────

TECHNIQUE_INHERITANCE_ROLL_CHANCE = 0.005
TECHNIQUE_INHERITANCE_ELDER_MULT = 2

# ── 功法偏差:修炼契合度不足的旁门功法会攒偏差,自己峰的功法(恒70契合)永远不会累积 ──────

TECHNIQUE_DEVIATION_GAIN = 2
TECHNIQUE_DEVIATION_MAX = 100
TECHNIQUE_DEVIATION_BANDS = [(0, 19, 0), (20, 39, 5), (40, 100, 10)]
# 偏差不再单独叠加心魔触发概率,而是拉低"识海稳固"(见 spirit_sea_stability),
# 让触发心魔的门槛本身变松,不跟触发概率重复计算同一件事

def technique_deviation_exp_penalty_pct(deviation):
    deviation = deviation or 0
    for lo, hi, pct in TECHNIQUE_DEVIATION_BANDS:
        if lo <= deviation <= hi:
            return pct
    return 10

# ── 轻量遭遇战:最多4回合(僵持可追击2回合),只有气血/攻势/护体/灵力四个数值,不做命中/闪避/
# 暴击/速度/多件装备词条;灵力每场独立重置为100点,不与日常修炼资源共用,不落库,靠事件hidden
# 字段传递(跟现有探索事件同一路数)。首版只给云海峰一门技能配招,其余峰打通后再批量补。

COMBAT_REALM_POWER = [
    100, 125, 155,        # 炼气 初/中/后
    220, 275, 340,        # 筑基
    500, 625, 775,        # 金丹
    1150, 1440, 1780,     # 元婴
    2700, 3375, 4185,     # 化神
    6500, 8125, 10075,    # 合体
    16000,                # 大乘圆满
]

def combat_realm_power(realm_idx):
    realm_idx = max(0, min(realm_idx or 0, len(COMBAT_REALM_POWER) - 1))
    return COMBAT_REALM_POWER[realm_idx]

# ── 神识:炼气期只有"灵觉"文字提示,不显示数值;筑基起正式解锁,数值刻意压在三位数以内,
# 不跟着境界系数一起膨胀到几万——它只负责"看得更远、发现得更多",不参与伤害计算。

SPIRIT_SENSE_UNLOCK_REALM_IDX = 3  # 筑基初期起正式显示神识
SPIRIT_SENSE_TABLE = [
    0, 0, 0,                 # 炼气(未解锁,只有灵觉)
    30, 40, 50,               # 筑基
    70, 85, 100,              # 金丹
    130, 155, 180,            # 元婴
    230, 270, 310,            # 化神
    380, 440, 500,            # 合体
    650,                      # 大乘圆满
]

def spirit_sense(realm_idx):
    realm_idx = max(0, min(realm_idx or 0, len(SPIRIT_SENSE_TABLE) - 1))
    return SPIRIT_SENSE_TABLE[realm_idx]

def spirit_sense_unlocked(realm_idx):
    return (realm_idx or 0) >= SPIRIT_SENSE_UNLOCK_REALM_IDX

# 灵觉:炼气期的"神识预告",纯文字,不给数值,为筑基后的正式解锁做铺垫
LINGJUE_TRIGGER_PCT_BY_BAND = {'心如止水': 30, '心境平和': 20, '心有杂念': 10}
LINGJUE_EVENTS = [
    '你忽然感到林中似乎有什么东西正在注视自己。',
    '打坐时你察觉到周遭灵气流向有些异常。',
    '你隐约觉得随身玉简中似乎藏着什么禁制,一时又说不清。',
    '你莫名感到一阵不安,仿佛有人正在远处窥视。',
    '识海深处忽然传来一阵轻微震动,不知是何预兆。',
]

def roll_lingjue_text(mind_band_label):
    chance = LINGJUE_TRIGGER_PCT_BY_BAND.get(mind_band_label, 20) / 100
    if random.random() < chance:
        return random.choice(LINGJUE_EVENTS)
    return None

# 识海稳固:不新增字段,直接由心境-偏差算出,只影响"能不能扛住心魔",不碰修为/突破那两条已有的心境效果
SPIRIT_SEA_DEVIATION_WEIGHT = 0.5

def spirit_sea_stability(mind_state, technique_deviation):
    return max(0, min(100, round((mind_state or 0) - (technique_deviation or 0) * SPIRIT_SEA_DEVIATION_WEIGHT)))

# 识破/智取:神识越高,看得越清楚——识破怪物机制+首回合伤害减免;智取成功率正式接上神识差
REVEAL_CHANCE_BASE = 0.60
REVEAL_CHANCE_PER_POINT = 0.01
REVEAL_ROUND1_DAMAGE_REDUCTION_PCT = 20
PERSUADE_CHANCE_BASE = 0.50
PERSUADE_CHANCE_PER_POINT = 0.008

def reveal_chance(own_sense, target_sense):
    return max(0.20, min(0.95, REVEAL_CHANCE_BASE + (own_sense - target_sense) * REVEAL_CHANCE_PER_POINT))

def persuade_chance(own_sense, target_sense):
    return max(0.30, min(0.90, PERSUADE_CHANCE_BASE + (own_sense - target_sense) * PERSUADE_CHANCE_PER_POINT))

COMBAT_MP_START = 100
COMBAT_BASIC_MP_REGEN = 10
COMBAT_DEFEND_MP_REGEN = 10
COMBAT_DEFEND_DAMAGE_REDUCTION_PCT = 30
COMBAT_ROUND_LIMIT = 4
COMBAT_PURSUIT_ROUND_LIMIT = 2
COMBAT_PURSUIT_DAMAGE_MULT = 1.2
COMBAT_PURSUIT_REWARD_MULT = 1.1
COMBAT_DAMAGE_RANDOM_RANGE = (0.9, 1.1)
COMBAT_STACK_MAX = 3

def combat_stats(realm_idx, physique, atk_mod=1.0, def_mod=1.0):
    power = combat_realm_power(realm_idx)
    return {
        'max_hp': round(power * (1 + (physique or 0) / 100)),
        'attack': round(power * 0.30 * atk_mod),
        'defense': round(power * 0.20 * def_mod),
    }

def combat_damage(attack, power_mult, defender_defense, attacker_realm_idx, ignore_defense_pct=0):
    standard_defense = combat_realm_power(attacker_realm_idx) * 0.20
    effective_defense = max(0, defender_defense * (1 - ignore_defense_pct / 100))
    reduction = max(0.0, min(0.6, effective_defense / (effective_defense + standard_defense))) if standard_defense else 0
    dmg = attack * power_mult * (1 - reduction) * random.uniform(*COMBAT_DAMAGE_RANDOM_RANGE)
    return max(1, round(dmg))

# 招式效果类型:首版只实现测试招式实际用到的几种,以后按需扩充,不预先造十种占位
# self_reduce:本回合受到的反击伤害按比例减免 / ignore_defense:本次攻击无视敌方部分护体
# multi_hit:连续命中N次(各自结算伤害) / consume_stacks:消耗层数,每层追加伤害
# heal_hp:按本次伤害的百分比回复自身气血(封顶气血上限)
# 八峰各给一套完整配招,同一模板(防御式/破防或治疗式/连击式/终式)换皮,靠效果类型分配和数值
# 差异做出不同打法,不是纯粹数值高低——跟宗门里"选峰即选路线"的既有设计原则保持一致。
TECHNIQUE_MOVES = {
    'zixiao_linghu': {   # 紫霄峰 灵犀共鸣诀 —— 人兽同心,自愈流
        'basic_label': '灵犀轻击', 'stack_label': '灵犀',
        'moves': [
            {'key': 'yinling', 'label': '一式·引灵', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.15,
             'effect': 'self_reduce', 'effect_value': 20, 'desc': '灵兽护主,本回合受到的反击伤害-20%'},
            {'key': 'tongxinji', 'label': '二式·同心击', 'unlock_mastery': 30, 'mp_cost': 25, 'power_mult': 1.3,
             'effect': 'heal_hp', 'effect_value': 25, 'desc': '人兽同心,回复本次伤害25%为气血'},
            {'key': 'lingshouzhu', 'label': '三式·灵兽助阵', 'unlock_mastery': 50, 'mp_cost': 40, 'power_mult': 0.7,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '人兽合击,连续三次进攻'},
            {'key': 'wanling', 'label': '终式·万灵归心', 'unlock_mastery': 70, 'mp_cost': 55, 'power_mult': 1.9,
             'effect': 'consume_stacks', 'effect_value': 12, 'desc': '消耗全部灵犀,每层伤害+12%'},
        ]},
    'yunhai_jianxin': {   # 云海峰 剑心通明诀 —— 剑修,破防连击
        'basic_label': '云海剑意', 'stack_label': '云势',
        'moves': [
            {'key': 'liufeng', 'label': '一式·流风', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.2,
             'effect': 'self_reduce', 'effect_value': 20, 'desc': '本回合受到的反击伤害-20%'},
            {'key': 'chuanyun', 'label': '三式·穿云', 'unlock_mastery': 30, 'mp_cost': 30, 'power_mult': 1.5,
             'effect': 'ignore_defense', 'effect_value': 30, 'desc': '无视30%护体'},
            {'key': 'fuyu', 'label': '五式·覆雨', 'unlock_mastery': 50, 'mp_cost': 40, 'power_mult': 0.7,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '连续三击'},
            {'key': 'tianqing', 'label': '六式·天倾', 'unlock_mastery': 70, 'mp_cost': 50, 'power_mult': 2.0,
             'effect': 'consume_stacks', 'effect_value': 15, 'desc': '消耗全部云势,每层伤害+15%'},
        ]},
    'tianshu_ningdan': {   # 天枢峰 凝丹诀 —— 丹道/火,唯一持续伤害流派,牺牲防御换绵长灼烧
        'basic_label': '丹火淬体', 'stack_label': '丹意',
        'moves': [
            {'key': 'lihougou', 'label': '一式·离火勾', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.2,
             'effect': 'self_reduce', 'effect_value': 15, 'desc': '丹炉护体,本回合受到的反击伤害-15%'},
            {'key': 'danlugu', 'label': '三式·丹炉固元', 'unlock_mastery': 30, 'mp_cost': 30, 'power_mult': 1.4,
             'effect': 'dot', 'effect_value': 15, 'desc': '点燃丹火,未来2回合每回合额外造成本次伤害15%的灼烧'},
            {'key': 'liyanlian', 'label': '五式·烈焰连击', 'unlock_mastery': 50, 'mp_cost': 40, 'power_mult': 0.75,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '丹火连珠,连续三次进攻'},
            {'key': 'jiuzhuan', 'label': '终式·九转归丹', 'unlock_mastery': 70, 'mp_cost': 55, 'power_mult': 2.1,
             'effect': 'consume_stacks', 'effect_value': 15, 'desc': '凝聚全部丹意,每层伤害+15%'},
        ]},
    'xuanqiong_cuiti': {   # 玄穹峰 淬体炼形诀 —— 炼器/土,淬体自愈
        'basic_label': '铁淬一击', 'stack_label': '器意',
        'moves': [
            {'key': 'gujia', 'label': '一式·固甲', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.1,
             'effect': 'self_reduce', 'effect_value': 25, 'desc': '器甲护体,本回合受到的反击伤害-25%'},
            {'key': 'cuitihuiqi', 'label': '二式·淬体回气', 'unlock_mastery': 30, 'mp_cost': 25, 'power_mult': 1.25,
             'effect': 'heal_hp', 'effect_value': 20, 'desc': '淬体化伤,回复本次伤害20%为气血'},
            {'key': 'lianqi', 'label': '三式·连击式', 'unlock_mastery': 50, 'mp_cost': 40, 'power_mult': 0.7,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '器械连发,连续三次进攻'},
            {'key': 'zhongqing', 'label': '终式·重器归元', 'unlock_mastery': 70, 'mp_cost': 55, 'power_mult': 1.9,
             'effect': 'consume_stacks', 'effect_value': 12, 'desc': '消耗全部器意,每层伤害+12%'},
        ]},
    'taixu_guiyi': {   # 太虚峰 太虚归一诀 —— 修真正统,灵气自愈,稳健蓄力
        'basic_label': '太虚一指', 'stack_label': '灵机',
        'moves': [
            {'key': 'xujing', 'label': '一式·虚静', 'unlock_mastery': 10, 'mp_cost': 18, 'power_mult': 1.1,
             'effect': 'self_reduce', 'effect_value': 20, 'desc': '心境澄明,本回合受到的反击伤害-20%'},
            {'key': 'guiyixiufu', 'label': '二式·归元自愈', 'unlock_mastery': 30, 'mp_cost': 25, 'power_mult': 1.25,
             'effect': 'heal_hp', 'effect_value': 30, 'desc': '灵气归元,回复本次伤害30%为气血'},
            {'key': 'lianhuanzhi', 'label': '三式·连环指', 'unlock_mastery': 50, 'mp_cost': 38, 'power_mult': 0.68,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '灵指连点,连续三次进攻'},
            {'key': 'taixuguiyizhong', 'label': '终式·太虚归一', 'unlock_mastery': 70, 'mp_cost': 55, 'power_mult': 2.0,
             'effect': 'consume_stacks', 'effect_value': 14, 'desc': '万灵归一,每层灵机伤害+14%'},
        ]},
    'xinglan_jifeng': {   # 星阑峰 疾风回气诀 —— 探秘/身法,多段连击
        'basic_label': '疾风一击', 'stack_label': '风势',
        'moves': [
            {'key': 'piaoyi', 'label': '一式·飘逸', 'unlock_mastery': 10, 'mp_cost': 18, 'power_mult': 1.15,
             'effect': 'self_reduce', 'effect_value': 25, 'desc': '身法飘逸,本回合受到的反击伤害-25%'},
            {'key': 'jifengzhi', 'label': '二式·疾风直取', 'unlock_mastery': 30, 'mp_cost': 28, 'power_mult': 1.3,
             'effect': 'ignore_defense', 'effect_value': 25, 'desc': '疾如风,直取要害,无视25%护体'},
            {'key': 'lianfashi', 'label': '三式·连发式', 'unlock_mastery': 50, 'mp_cost': 38, 'power_mult': 0.65,
             'effect': 'multi_hit', 'effect_value': 4, 'desc': '身法迅捷,连续四次进攻'},
            {'key': 'huixuan', 'label': '终式·回旋绝影', 'unlock_mastery': 70, 'mp_cost': 50, 'power_mult': 1.85,
             'effect': 'consume_stacks', 'effect_value': 12, 'desc': '消耗全部风势,每层伤害+12%'},
        ]},
    'canglan_tongxin': {   # 沧澜峰 同心共修诀 —— 交际/水,治愈系
        'basic_label': '同心一击', 'stack_label': '心意',
        'moves': [
            {'key': 'tongqi', 'label': '一式·同气', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.1,
             'effect': 'self_reduce', 'effect_value': 20, 'desc': '同心相护,本回合受到的反击伤害-20%'},
            {'key': 'roushui', 'label': '二式·柔水愈心', 'unlock_mastery': 30, 'mp_cost': 25, 'power_mult': 1.2,
             'effect': 'heal_hp', 'effect_value': 35, 'desc': '以水化情,回复本次伤害35%为气血'},
            {'key': 'lianjishi', 'label': '三式·连击式', 'unlock_mastery': 50, 'mp_cost': 38, 'power_mult': 0.68,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '心意相连,连续三次进攻'},
            {'key': 'wanxin', 'label': '终式·万心归一', 'unlock_mastery': 70, 'mp_cost': 52, 'power_mult': 1.85,
             'effect': 'consume_stacks', 'effect_value': 13, 'desc': '消耗全部心意,每层伤害+13%'},
        ]},
    'lingxiao_guixu': {   # 凌霄峰 九霄归墟诀 —— 掌门峰,兼修各家,数值略高一档
        'basic_label': '九霄一击', 'stack_label': '归墟',
        'moves': [
            {'key': 'jiuxiaohu', 'label': '一式·九霄护体', 'unlock_mastery': 10, 'mp_cost': 20, 'power_mult': 1.2,
             'effect': 'self_reduce', 'effect_value': 22, 'desc': '兼修护体,本回合受到的反击伤害-22%'},
            {'key': 'guixupo', 'label': '二式·归墟破', 'unlock_mastery': 30, 'mp_cost': 30, 'power_mult': 1.5,
             'effect': 'ignore_defense', 'effect_value': 30, 'desc': '兼修各家之长,无视30%护体'},
            {'key': 'lianhuanjue', 'label': '三式·连环诀', 'unlock_mastery': 50, 'mp_cost': 40, 'power_mult': 0.75,
             'effect': 'multi_hit', 'effect_value': 3, 'desc': '诸法合一,连续三次进攻'},
            {'key': 'jiuxiaozhong', 'label': '终式·九霄归墟', 'unlock_mastery': 70, 'mp_cost': 55, 'power_mult': 2.2,
             'effect': 'consume_stacks', 'effect_value': 14, 'desc': '消耗全部归墟,每层伤害+14%'},
        ]},
}

def technique_moves(technique_key):
    return TECHNIQUE_MOVES.get(technique_key, {}).get('moves', [])

# ── 秘境妖物:每种只给一个鲜明机制,不做完整功法系统 ─────────────────────────────────


# 每种妖物/邪修都配一个专属机制、一份跟身份挂钩的额外奖励(而不是清一色只给灵石经验)、
# 以及各自的灵材掉落表——机制、报酬、掉落三条线都不一样,才不会打完感觉都是同一只怪换皮。
MONSTERS = {
    'chiyan_wolf':  {'label': '赤目妖狼', 'realm_idx': 1, 'hp_mult': 0.8, 'atk_mult': 1.1, 'def_mult': 0.7,
                      'ability': 'enrage_after_2_basic',
                      'ability_desc': '连续遭普攻两次后,下次反击伤害+30%',
                      'bonus_reward': {'physique': 1}, 'material_drop': {'low': 0.30}},
    'stone_lizard': {'label': '石甲巨蜥', 'realm_idx': 2, 'hp_mult': 1.2, 'atk_mult': 0.8, 'def_mult': 1.4,
                      'ability': 'first_move_halved',
                      'ability_desc': '首次受到招式伤害时,该次伤害减半',
                      'bonus_reward': {'physique': 2}, 'material_drop': {'low': 0.35}},
    'charm_flower': {'label': '迷魂花妖', 'realm_idx': 3, 'hp_mult': 0.7, 'atk_mult': 0.9, 'def_mult': 0.6,
                      'ability': 'weaken_round2',
                      'ability_desc': '第二回合起,使你下一招威力-30%',
                      'bonus_reward': {'mind_state': -2}, 'material_drop': {'low': 0.25}},
    'gu_sprite':    {'label': '蛊毒山魈', 'realm_idx': 2, 'hp_mult': 0.75, 'atk_mult': 0.85, 'def_mult': 0.9,
                      'ability': 'poison_player',
                      'ability_desc': '沾之即中蛊毒,未来2回合每回合持续掉血',
                      'bonus_reward': {'physique': 1}, 'material_drop': {'low': 0.30, 'mid': 0.05}},
    # 凡间(金丹起):不再是纯妖兽,混入邪修/散修,机制也更狠一些,呼应"越走越远、越走越险"
    'bandit_chief': {'label': '黑风寨悍匪', 'realm_idx': 6, 'hp_mult': 1.0, 'atk_mult': 1.0, 'def_mult': 1.0,
                      'ability': 'enrage_low_hp',
                      'ability_desc': '气血跌破三成后,狗急跳墙,反击伤害+25%',
                      'bonus_reward': {'reputation': 5}, 'material_drop': {'low': 0.30, 'mid': 0.10}},
    'blood_rogue':  {'label': '游脚邪修·血影', 'realm_idx': 7, 'hp_mult': 0.9, 'atk_mult': 1.05, 'def_mult': 0.85,
                      'ability': 'lifesteal',
                      'ability_desc': '邪功吸血,每次反击回复自身伤害量20%的气血',
                      'bonus_reward': {}, 'material_drop': {'mid': 0.25}},
    'blade_rogue':  {'label': '散修盟·刀客', 'realm_idx': 8, 'hp_mult': 1.0, 'atk_mult': 1.1, 'def_mult': 0.95,
                      'ability': 'ignore_player_defense',
                      'ability_desc': '刀法狠辣,每次反击无视你20%护体',
                      'bonus_reward': {'reputation': 8}, 'material_drop': {'mid': 0.30}},
    'iron_rogue':   {'label': '炼体邪修·铁拳', 'realm_idx': 8, 'hp_mult': 1.1, 'atk_mult': 0.9, 'def_mult': 1.1,
                      'ability': 'reflect',
                      'ability_desc': '体表反震,你每次命中都会弹回15%伤害到自己身上',
                      'bonus_reward': {'physique': 3}, 'material_drop': {'mid': 0.25}},
    'soul_rogue':   {'label': '摄魂散修', 'realm_idx': 9, 'hp_mult': 1.1, 'atk_mult': 1.0, 'def_mult': 1.0,
                      'ability': 'ambush_round1',
                      'ability_desc': '惯于偷袭,首回合反击伤害+30%',
                      'bonus_reward': {}, 'material_drop': {'mid': 0.20, 'high': 0.08}},
    # 九幽渊(化神起):渡劫路上境界越高越孤绝,这里的对手不再是人,是深渊本身孕出的存在
    'abyss_wraith': {'label': '幽渊怨灵', 'realm_idx': 12, 'hp_mult': 1.0, 'atk_mult': 1.1, 'def_mult': 0.9,
                      'ability': 'reflect',
                      'ability_desc': '怨气缠身,你每次命中都会弹回15%伤害到自己身上',
                      'bonus_reward': {}, 'material_drop': {'high': 0.30, 'top': 0.08}},
    'jiuyou_beast': {'label': '九幽噬魂兽', 'realm_idx': 13, 'hp_mult': 1.25, 'atk_mult': 1.05, 'def_mult': 1.1,
                      'ability': 'enrage_low_hp',
                      'ability_desc': '气血跌破三成后暴走,反击伤害+25%',
                      'bonus_reward': {'physique': 4}, 'material_drop': {'high': 0.30, 'top': 0.10}},
}
MONSTER_POOL_BY_REGION = {
    'backmountain': ['chiyan_wolf', 'stone_lizard', 'charm_flower', 'gu_sprite'],
    'mortal': ['bandit_chief', 'blood_rogue', 'blade_rogue', 'iron_rogue', 'soul_rogue'],
}

# 遭遇战代价:不致死也不掉修为,只是"负伤",持续一段时间内战斗气血上限打折
INJURY_DURATION_SECONDS = 2 * 3600
INJURY_HP_PENALTY_PCT = 10
INJURY_STAMINA_PENALTY = 10
INJURY_MIND_PENALTY = 2

def encounter_monster_power(monster_key):
    m = MONSTERS[monster_key]
    stats = combat_stats(m['realm_idx'], 0)
    return {
        'label': m['label'],
        'max_hp': round(stats['max_hp'] * m['hp_mult']),
        'attack': round(stats['attack'] * m['atk_mult']),
        'defense': round(stats['defense'] * m['def_mult']),
        'realm_idx': m['realm_idx'],
        'ability': m['ability'],
        'ability_desc': m['ability_desc'],
    }

# ── 秘境:不限时间段,一天最多探索3场(元婴起5场),入内共用一条气血,直到昏迷/主动撤退/体力耗尽。
# 三座秘境按境界分层;深入会提高危险与稀有事件概率,随时可撤退保住已封存的收获——
# "继续深入还是见好就收"才是核心张力,不是连续点随机按钮。

MYSTIC_DAILY_SESSIONS_MAX = 3       # 一天最多探索3场,不限具体时间段
MYSTIC_DAILY_SESSIONS_MAX_HIGH = 5  # 元婴起阅历丰富、心境沉稳,场次上调至5场
MYSTIC_SESSIONS_BONUS_MIN_REALM = 9  # 元婴初期起生效,同 SPIRIT_ROOT_ASCENSION_MIN_REALM 的门槛

def mystic_daily_sessions_max(realm_idx):
    return MYSTIC_DAILY_SESSIONS_MAX_HIGH if realm_idx >= MYSTIC_SESSIONS_BONUS_MIN_REALM else MYSTIC_DAILY_SESSIONS_MAX
MYSTIC_ENTRY_STAMINA_COST = 20  # 入场费,消耗真实体力,与委托共享同一资源池
MYSTIC_STAMINA_START = 10       # 每场限定10点探索点数(与体力无关的场内点数),不因反复进出而刷新
MYSTIC_HEAL_USES_MAX = 2        # 本轮最多服丹回气血2次,避免无限续航
MYSTIC_ESCAPE_CHARMS_START = 1  # 每轮起手自带1张遁符,战斗中可保底脱离
MYSTIC_DEPTH_MAX = 4
MYSTIC_DEPTH_LABELS = {1: '外围', 2: '内层', 3: '核心', 4: '隐藏区域'}
MYSTIC_FAINT_LOSS_PCT = 50      # 昏迷时,未封存的本轮收获打对折(已封存的分文不少、装备永不丢失)
MYSTIC_DEPTH_DANGER_MULT = {1: 1.0, 2: 1.2, 3: 1.5, 4: 2.0}
MYSTIC_HIDDEN_UNLOCK_CHANCE = 0.15  # 核心层触发仙缘事件时,小概率额外发现隐藏区域入口

MYSTIC_ZONES = [
    {'key': 'qinglan', 'label': '青岚药谷', 'realm_req': 0,
     'desc': '云雾缭绕的药谷,灵药遍地,亦有毒虫瘴气潜伏其间。',
     'danger_desc': '毒雾、毒虫', 'monster_keys': ['chiyan_wolf', 'gu_sprite'],
     'material_key': 'qinglan_root', 'material_label': '药谷灵根须'},
    {'key': 'chiyan', 'label': '赤炎洞窟', 'realm_req': 3,
     'desc': '地脉灼热的火窟,矿脉丰饶,烈焰与凶兽横行。',
     'danger_desc': '灼烧、火兽', 'monster_keys': ['stone_lizard', 'charm_flower'],
     'material_key': 'chiyan_ore', 'material_label': '赤炎矿核'},
    {'key': 'guxiu', 'label': '古修洞府', 'realm_req': 6,
     'desc': '前朝修士遗留的洞府群,阵法森严,傀儡犹自值守。',
     'danger_desc': '阵法、傀儡', 'monster_keys': ['bandit_chief', 'blade_rogue', 'iron_rogue'],
     'material_key': 'guxiu_rune', 'material_label': '古修器纹片'},
    {'key': 'zangjian', 'label': '葬剑遗址', 'realm_req': 9,
     'desc': '古战场遗骸遍地,残剑犹自嗡鸣,剑气与执念交织不散。',
     'danger_desc': '剑气、残魂', 'monster_keys': ['blood_rogue', 'soul_rogue'],
     'material_key': 'zangjian_shard', 'material_label': '断剑之魄'},
    {'key': 'jiuyou', 'label': '九幽渊', 'realm_req': 12,
     'desc': '化神以上方能踏足的无光深渊,灵气浓得化不开,亦孕生出不属于人世的凶物。',
     'danger_desc': '深渊凶物、神魂反噬', 'monster_keys': ['abyss_wraith', 'jiuyou_beast'],
     'material_key': 'jiuyou_crystal', 'material_label': '幽渊魂晶'},
    # 灵珠秘境:合体仪式"灵珠秘境"环节专属,hidden=True 不出现在秘境页的常规选择列表里,
    # 只能从合体页的入口进入;heti_stage 不在该环节时 mystic_enter 会拒绝进入,凑够灵珠后
    # 那一环节结束,自然也就再进不去了——不需要额外的"关闭"逻辑。
    {'key': 'lingzhu', 'label': '灵珠秘境', 'realm_req': 14, 'hidden': True,
     'desc': '合体渡劫前,神魂自行开辟出的一方幻境,神魔劫兽盘踞其间,守着凝就本我与真我的灵珠。',
     'danger_desc': '心魔幻象、劫兽反噬', 'monster_keys': ['abyss_wraith', 'jiuyou_beast'],
     'material_key': 'lingzhu_bead', 'material_label': '灵珠'},
]
MYSTIC_ZONES_BY_KEY = {z['key']: z for z in MYSTIC_ZONES}

# 灵珠秘境一生仅此一次(heti_stage==1这一环节),额外限定总入场次数,逼玩家每场都要打得够深——
# 用 mystic_sessions 里 zone_key='lingzhu' 的历史场次数直接算,不新增字段。
HETI_LINGZHU_MAX_ENTRIES = 5
HETI_LINGZHU_REQUIRED = 25

MYSTIC_COMMON_MATERIAL_KEY = 'mystic_dust'
MYSTIC_MATERIAL_LABELS = {
    'mystic_dust': '秘境雾尘', 'qinglan_root': '药谷灵根须', 'chiyan_ore': '赤炎矿核',
    'guxiu_rune': '古修器纹片', 'zangjian_shard': '断剑之魄', 'embryo_core': '胚胎核心',
    'artifact_soul_thread': '器灵丝', 'jiuyou_crystal': '幽渊魂晶', 'lingzhu_bead': '灵珠',
}

# 极品金丹专用的"奇遇材料"不设兑换、不常规掉落,只在对应秘境仙缘·闯关成功时小概率额外拾得——
# 化神的门槛材料"渡厄珠"走同一条路,闯关成功后有25%概率额外拾得。
MYSTIC_ZONE_FORTUNE_DROP = {
    'chiyan':   {'material': DAN_FORTUNE_MATERIAL, 'chance': 0.04},
    'zangjian': {'material': SHEN_GATE_MATERIAL, 'chance': 0.25},
}

# 深度→事件类型权重:越往深处,稀有的"仙缘际遇"概率越高、"无事发生"概率越低
MYSTIC_DEPTH_EVENT_WEIGHTS = {
    1: {'beast': 30, 'herb': 25, 'satchel': 15, 'cultivator': 15, 'nothing': 13, 'fortune': 2},
    2: {'beast': 32, 'herb': 20, 'satchel': 18, 'cultivator': 15, 'nothing': 10, 'fortune': 5},
    3: {'beast': 30, 'herb': 15, 'satchel': 20, 'cultivator': 12, 'nothing': 8,  'fortune': 15},
    4: {'beast': 25, 'herb': 10, 'satchel': 20, 'cultivator': 10, 'nothing': 5,  'fortune': 30},
}

def roll_mystic_event_type(depth):
    weights = MYSTIC_DEPTH_EVENT_WEIGHTS.get(depth, MYSTIC_DEPTH_EVENT_WEIGHTS[1])
    keys = list(weights.keys())
    return random.choices(keys, weights=[weights[k] for k in keys], k=1)[0]

MYSTIC_NOTHING_FLAVORS = [
    '你在草叶间发现一串未干的脚印,似有人先你一步。',
    '风中飘来一丝极淡的灵气波动,转瞬即逝,你记下了大致方位。',
    '你在岩壁上看到几道新鲜的抓痕,不知是何物所留,心中多了几分警惕。',
    '地上散落着几片破碎的符纸,残留的阵纹已看不真切,似有前人在此交手。',
]

# 秘境探索事件的提示语按"结局"分池随机抽取(与突破/打坐同一思路),数值判定完全不变,
# 只是把原本单一固定的一句话换成同类的几句轮换,减少高频探索时的复读感。
MYSTIC_BEAST_FLEE_FLAVORS = ['你掷出一枚遁符,遁光一闪,已从妖兽身旁悄然遁走。',
                             '遁符甫一祭出,你已如轻烟般遁出数丈。',
                             '一道遁光闪过,妖兽扑了个空,只留一声低吼。']
MYSTIC_BEAST_AVOID_FLAVORS = ['你不与其纠缠,绕道而行。', '你不愿节外生枝,悄然避开。',
                              '你放缓脚步,寻隙从旁绕了过去。']
MYSTIC_HERB_WAIT_SUCCESS_FLAVORS = ['你耐心等待,灵药终于成熟,', '你屏息凝神守候片刻,灵药恰好绽放,',
                                    '灵药迎着你的耐心悄然绽开,']
MYSTIC_HERB_WAIT_FAIL_FLAVORS = ['灵药未及采摘便遭异动惊扰,', '你正待下手,四周突然一阵骚动,',
                                 '灵药尚未熟透,一阵异响令你猝不及防,']
MYSTIC_HERB_QUICK_FLAVORS = ['你当机立断,', '你不愿节外生枝,当即下手,', '见机不可失,你迅速出手,']
MYSTIC_SATCHEL_OPEN_SUCCESS_FLAVORS = ['储物袋并无禁制,', '你手法利落地打开储物袋,里面并无异常,',
                                       '储物袋轻轻一震便自行开启,']
MYSTIC_SATCHEL_OPEN_FAIL_FLAVORS = ['储物袋上暗藏禁制,', '你刚一触碰,便觉不妙,', '禁制骤然发动,']
MYSTIC_SATCHEL_PEEK_SUCCESS_FLAVORS = ['你看穿了禁制的破绽,', '你仔细端详片刻,寻得破绽,',
                                       '你耐心拆解片刻,终见分晓,']
MYSTIC_SATCHEL_PEEK_FAIL_FLAVORS = ['你端详半晌,始终看不透其中玄机,决定还是不碰为妙。',
                                    '这储物袋透着几分诡异,你终究不敢轻举妄动。',
                                    '左看右看总觉不对劲,你还是决定原样放下。']
MYSTIC_CULTIVATOR_COOPERATE_FLAVORS = ['两人合力探查,各有所获,', '你与对方相互照应,配合默契,',
                                       '二人分工探查,效率倍增,']
MYSTIC_CULTIVATOR_TRADE_FLAVORS = ['你以{cost}灵石换得对方{label}×2。', '一番讨价还价后,你以{cost}灵石换得{label}×2。',
                                   '你爽快地掏出{cost}灵石,换得对方{label}×2。']
MYSTIC_CULTIVATOR_AVOID_FLAVORS = ['你不愿节外生枝,拱手避让而过。', '你微微一笑,拱手示意,转身离去。',
                                   '你不欲多生事端,径自绕道而行。']
MYSTIC_FORTUNE_BREAKIN_SUCCESS_FLAVORS = ['你破阵而入,寻得洞府造化——器灵丝一缕',
                                          '你觅得阵眼破绽,强行破阵而入,寻得器灵丝一缕',
                                          '你避开重重禁制,悄然潜入,寻得器灵丝一缕']
MYSTIC_FORTUNE_BREAKIN_FAIL_FLAVORS = ['洞府禁制反噬,', '禁制骤然爆发,', '你刚一触及禁制便被狠狠弹开,']
MYSTIC_FORTUNE_SACRIFICE_FLAVORS = ['你献上{label}×3以安其灵,平安得器灵丝一缕。',
                                    '你恭敬献上{label}×3,禁制归于平静,得器灵丝一缕。',
                                    '你以{label}×3为祭,谨慎行事,得器灵丝一缕。']
MYSTIC_FORTUNE_RETREAT_FLAVORS = ['你记下此地方位,不做强求,先行撤出准备,只取走随手可得的一点馈赠。',
                                  '你审时度势,决定见好就收,只捎带走些许馈赠。',
                                  '你不愿孤注一掷,先行撤离,顺手带走些微馈赠。']

# ── 装备:本命法宝(唯一绑定,白板起步,靠温养成长)+ 武器/防具/饰品(可替换,秘境掉落) ──────

EQUIPMENT_SLOTS = ['artifact', 'weapon', 'armor', 'accessory']
EQUIPMENT_SLOT_LABELS = {'artifact': '本命法宝', 'weapon': '武器', 'armor': '防具', 'accessory': '饰品'}

# 配装预设:固定3个槽位,标签玩家自定义(建议如"秘境探索""天魔输出""防御护持"等按需自取),
# 这里只给个默认占位名。本命法宝不参与预设(它是终身绑定的单一实体,不是可替换的装备)。
EQUIPMENT_PRESET_DEFAULT_LABELS = {'p1': '预设一', 'p2': '预设二', 'p3': '预设三'}

ARTIFACT_CORE_UNLOCK_REALM_IDX = 3   # 筑基起可领取胚胎,不靠随机掉落赌运气
ARTIFACT_CORE_ORIENTATIONS = {
    'offense': {'label': '攻伐', 'attack_w': 0.6,  'defense_w': 0.15, 'agility_w': 0.25},
    'defense': {'label': '防护', 'attack_w': 0.15, 'defense_w': 0.6,  'agility_w': 0.25},
    'support': {'label': '辅助', 'attack_w': 0.2,  'defense_w': 0.2,  'agility_w': 0.6},
}
ARTIFACT_CORE_EXP_PER_LEVEL = 100
ARTIFACT_CORE_NURTURE_MATERIAL_COST = {'mystic_dust': 3}       # 通用温养:消耗通用材料,稳定但慢
ARTIFACT_CORE_NURTURE_EXP_GAIN = 30
ARTIFACT_CORE_EQUIPMENT_NURTURE_EXP_GAIN = 15  # 拿过时装备当温养辅料,收益刻意低于通用材料,不是最优解
ARTIFACT_CORE_RARE_NURTURE_MATERIAL_COST = {'embryo_core': 1}  # 稀有温养:消耗核心料,涨幅大很多
ARTIFACT_CORE_RARE_NURTURE_EXP_GAIN = 120
ARTIFACT_CORE_REFORGE_LINGSHI_COST = 500
ARTIFACT_CORE_REFORGE_LEVEL_PENALTY_PCT = 50   # 重铸后等级砍半(向下取整),可重新选方向,本体不变

# 转世炼形:比旧式重铸温和,保留品级与大部分温养成果,但重生成器物名与器灵性格。
ARTIFACT_REBIRTH_LINGSHI_COST = 200
ARTIFACT_REBIRTH_MATERIAL_COST = {'mystic_dust': 9}
ARTIFACT_REBIRTH_LEVEL_PENALTY_PCT = 20

# 稳固升阶:给长期运气不佳的玩家一条确定成长线。超品仍需高阶秘境材料与器灵丝,
# 但不再只能等待5%的单次机缘；若先触发秘境蜕变,则可省下全部升阶成本。
ARTIFACT_CORE_STABLE_UPGRADE_COSTS = {
    'low':  {'to': 'mid',  'lingshi': 250,  'materials': {'embryo_core': 2}},
    'mid':  {'to': 'high', 'lingshi': 600,  'materials': {'embryo_core': 4, 'guxiu_rune': 10}},
    'high': {'to': 'top',  'lingshi': 1200, 'materials': {'embryo_core': 6, 'zangjian_shard': 15,
                                                          'artifact_soul_thread': 2}},
}

# 本命法宝品级:决定"潜力"——温养等级上限、每级加成量都随品级提高。筑基绑定时默认下品(人人可得,
# 不吃机缘也有得练);中品/下品靠玄穹峰弟子炼器就能碰到,上品要靠高等阶炼器师才有像样概率,
# 超品完全不进炼器权重表,只能从高阶秘境的机缘中蜕变而来。
ARTIFACT_CORE_QUALITIES = {
    'low':  {'label': '下品', 'max_level': 20, 'stat_per_level': 4},
    'mid':  {'label': '中品', 'max_level': 26, 'stat_per_level': 5},
    'high': {'label': '上品', 'max_level': 34, 'stat_per_level': 6},
    'top':  {'label': '超品', 'max_level': 45, 'stat_per_level': 8},
}
ARTIFACT_CORE_QUALITY_ORDER = ['low', 'mid', 'high', 'top']

def artifact_core_max_level(quality_key):
    return ARTIFACT_CORE_QUALITIES.get(quality_key, ARTIFACT_CORE_QUALITIES['low'])['max_level']

def artifact_core_stat_bonus(level, orientation_key, quality_key='low'):
    o = ARTIFACT_CORE_ORIENTATIONS.get(orientation_key)
    if not o or not level:
        return {'attack': 0, 'defense': 0, 'agility': 0}
    per_level = ARTIFACT_CORE_QUALITIES.get(quality_key, ARTIFACT_CORE_QUALITIES['low'])['stat_per_level']
    total = level * per_level
    return {'attack': round(total * o['attack_w']), 'defense': round(total * o['defense_w']),
            'agility': round(total * o['agility_w'])}

# 炼器峰弟子的炼化:只能炼出下品/中品/上品(权重按炼器师等阶提升),超品不在权重表内,
# 逼着"要超品就得去高阶秘境搏机缘",不能纯靠蹲在器坊里刷。
FORGE_CORE_QUALITY_ORDER = ['low', 'mid', 'high']
FORGE_CORE_QUALITY_WEIGHTS = {
    1: {'low': 75, 'mid': 23, 'high': 2},
    2: {'low': 55, 'mid': 35, 'high': 10},
    3: {'low': 35, 'mid': 40, 'high': 25},
    4: {'low': 20, 'mid': 40, 'high': 40},
    5: {'low': 10, 'mid': 35, 'high': 55},
}

# 超品本命法宝:葬剑遗址机缘可免费直接蜕变；也可积累高阶秘境材料走稳固升阶保底。
MYSTIC_ARTIFACT_CORE_TOP_ZONE = 'zangjian'
MYSTIC_ARTIFACT_CORE_TOP_CHANCE = 0.05

# ── 本命法宝取名:一个前缀 + 一个器物,绑定后终身不变 ──────────────────────────
# 旧版把两个意象硬接在一起,容易生成“日月山河宫殿”一类堆砌感较重的名字。新版固定为
# “二字前缀+器物”,如“赤霄剑”“玄黄护心镜”；三种方向各有独立的语义池和器型池。

ARTIFACT_CORE_NAME_MOTIFS = {
    'offense': [
        '赤霄', '紫电', '惊雷', '斩月', '逐日', '焚天', '破军', '七杀', '劫火', '霜锋',
        '龙渊', '凤翎', '天刑', '星陨', '裂空', '断岳', '沧溟', '流火', '寒狱', '诛邪',
        '青冥', '九曜', '太白', '离火', '玄戈', '鸣鸿', '照胆', '饮雪', '摧城', '镇魔',
        '伏魔', '荡妖', '屠龙', '吞日', '贯虹', '追魂', '夺魄', '灭度', '寂灭', '无锋',
        '藏锋', '凌云', '乘风', '奔雷', '掣电', '炎阳', '极寒', '朔风', '血煞', '烛龙',
        '金乌', '玄凰', '苍龙', '白虎', '天狼', '贪狼', '廉贞', '武曲', '神锋', '绝影',
        '碎星', '撼岳', '穿云', '落霞', '飞霜', '长虹', '怒涛', '狂澜', '烬海', '雷殛',
    ],
    'defense': [
        '玄黄', '乾坤', '山河', '不动', '镇岳', '承天', '厚土', '归藏', '无垢', '净世',
        '金刚', '太极', '四象', '玄武', '青莲', '须弥', '长生', '护道', '息壤', '定海',
        '灵台', '磐石', '天幕', '月轮', '九宫', '六合', '镇魂', '琉璃', '紫府', '鸿蒙',
        '混元', '两仪', '五岳', '八荒', '周天', '镇海', '镇天', '镇狱', '安魂', '守心',
        '明光', '宝光', '金霞', '紫气', '瑞云', '庆云', '玉清', '上清', '太清', '洞天',
        '福地', '万寿', '延生', '护元', '保命', '辟邪', '禳灾', '御劫', '避尘', '无尘',
        '冰心', '铁壁', '龙鳞', '凤羽', '龟灵', '沧岳', '昆仑', '天柱', '地载', '海纳',
    ],
    'support': [
        '灵犀', '玄机', '造化', '因果', '无相', '太虚', '星河', '月华', '烟霞', '浮光',
        '问心', '照影', '知微', '听风', '衔梦', '引魂', '聚灵', '观星', '衍天', '回春',
        '忘川', '彼岸', '蜃景', '云笈', '天机', '妙音', '流光', '清虚', '洞玄', '万象',
        '玲珑', '如意', '逍遥', '自在', '空明', '澄心', '洗心', '养魂', '蕴灵', '通幽',
        '寻踪', '觅影', '辨真', '破妄', '留影', '传音', '纳海', '藏虚', '袖里', '芥子',
        '春生', '木灵', '甘霖', '和光', '同尘', '清风', '明月', '繁星', '飞花', '流萤',
        '梦华', '浮生', '红尘', '解语', '同心', '牵缘', '司命', '卜天', '灵枢', '秘藏',
    ],
}
ARTIFACT_CORE_NAME_COMMON_MOTIFS = [
    '九霄', '紫霄', '碧落', '黄泉', '苍穹', '云海', '霜雪', '烟雨', '沧海', '晨曦',
    '暮云', '星月', '日月', '阴阳', '轮回', '归墟', '涅槃', '天命', '道心', '真意',
    '太初', '太古', '上古', '洪荒', '无极', '元始', '混沌', '寰宇', '六合', '八极',
    '三清', '五行', '北斗', '南斗', '天罡', '地煞', '紫微', '玉衡', '瑶光', '天璇',
    '扶桑', '若木', '建木', '蓬莱', '方丈', '瀛洲', '昆吾', '瑶池', '云梦', '苍梧',
    '白露', '清霜', '寒烟', '疏影', '清辉', '朝露', '晚照', '流霞', '飞虹', '素光',
]
ARTIFACT_CORE_NAME_VESSELS = {
    'weapon':  [
        '剑', '刀', '枪', '戟', '弓', '钺', '锏', '轮', '刃', '飞梭', '羽扇', '七弦琴',
        '飞剑', '重剑', '双剑', '长刀', '陌刀', '战矛', '神戟', '飞矛', '宝弓', '连弩',
        '双钩', '金锤', '铜锏', '铁鞭', '月轮', '刺轮', '飞针', '剑匣', '剑葫', '玉箫',
    ],
    'seal':    [
        '鼎', '塔', '钟', '印', '碑', '宝阙', '神山', '玉玺', '镇尺', '金斗', '玉台',
        '天门', '宝幢', '法坛', '石阙', '镇碑', '神宫', '金桥', '道台', '玉册',
    ],
    'guard':   [
        '玄甲', '灵盾', '法衣', '莲台', '护心镜', '云罗帕', '金光罩', '璎珞', '道袍',
        '羽衣', '霞帔', '仙衣', '宝甲', '鳞甲', '臂钏', '玉佩', '腰带', '护腕', '华盖',
        '宝伞', '法冠', '金冠', '玉冠', '护符', '命牌', '法障', '天幕',
    ],
    'aid':     [
        '葫芦', '净瓶', '丹炉', '宝镜', '灵灯', '宝珠', '玉铃', '量天尺', '香炉',
        '药鼎', '茶鼎', '玉壶', '金瓶', '玉盏', '灵盘', '宝鉴', '铜镜', '魂灯', '宫灯',
        '铃铛', '玉磬', '木鱼', '念珠', '手串', '如意', '灵泉', '宝匣',
    ],
    'array':   [
        '阵盘', '阵旗', '棋局', '星图', '画卷', '河图', '罗盘', '天书', '地书', '洛书',
        '沙盘', '灵图', '阵图', '云图', '星盘', '算筹', '卦盘', '命盘', '经卷', '符册',
    ],
    'special': [
        '玉简', '判官笔', '缚仙索', '天蚕丝', '傩面', '金蛟剪', '玄钥', '如意',
        '拂尘', '毫笔', '墨砚', '纸伞', '折扇', '古琴', '箜篌', '琵琶', '洞箫', '玉笛',
        '香囊', '锦囊', '灵偶', '傀儡', '面具', '宝钥', '刻刀', '织梭', '同心结', '玲珑锁',
    ],
    'nature':  [
        '真火', '神雷', '玄冰', '灵木', '弱水', '庆云', '灵潮', '剑丸', '雷珠', '火种',
        '冰魄', '风眼', '雷池', '剑气', '刀光', '神砂', '金焰', '寒焰', '罡风', '星砂',
        '月精', '日精', '龙息', '凤火', '云气', '霞光', '灵藤', '花雨',
    ],
}
# 方向→更容易抽到的器物类别(攻伐偏兵器/自然造物;防护偏镇压/防御;辅助偏辅助/阵法/特殊)
ARTIFACT_CORE_NAME_CATEGORIES_BY_ORIENTATION = {
    'offense': ['weapon', 'nature'],
    'defense': ['seal', 'guard'],
    'support': ['aid', 'array', 'special'],
}
ARTIFACT_CORE_NAME_ORIENTATION_BIAS_PCT = 100  # 器型严格贴合方向,避免攻伐法宝抽成护具等语义冲突

def roll_artifact_core_name(orientation_key=None):
    orientation_key = orientation_key if orientation_key in ARTIFACT_CORE_ORIENTATIONS else random.choice(
        list(ARTIFACT_CORE_ORIENTATIONS))
    categories = ARTIFACT_CORE_NAME_CATEGORIES_BY_ORIENTATION.get(orientation_key)
    if categories and random.randint(1, 100) <= ARTIFACT_CORE_NAME_ORIENTATION_BIAS_PCT:
        pool = ARTIFACT_CORE_NAME_VESSELS[random.choice(categories)]
    else:
        pool = [v for vessels in ARTIFACT_CORE_NAME_VESSELS.values() for v in vessels]
    vessel = random.choice(pool)
    motifs = ARTIFACT_CORE_NAME_MOTIFS[orientation_key] + ARTIFACT_CORE_NAME_COMMON_MOTIFS
    return f"{random.choice(motifs)}{vessel}"

ARTIFACT_SPIRIT_PERSONALITIES = {
    'offense': ['骄烈', '嗜战', '刚直', '桀骜', '果决', '嫉恶'],
    'defense': ['忠主', '沉稳', '慈护', '古拙', '坚忍', '寡言'],
    'support': ['灵慧', '顽劣', '温和', '好奇', '通幽', '清静'],
}
ARTIFACT_GROWTH_TITLES = {
    'offense': [(10, '初鸣'), (20, '惊锋'), (30, '破岳'), (40, '凌霄')],
    'defense': [(10, '护主'), (20, '不动'), (30, '镇岳'), (40, '承天')],
    'support': [(10, '通灵'), (20, '知微'), (30, '衍法'), (40, '造化')],
}

def roll_artifact_spirit(orientation_key):
    return random.choice(ARTIFACT_SPIRIT_PERSONALITIES.get(orientation_key, ['沉静']))

def artifact_growth_title(level, orientation_key):
    title = None
    for threshold, label in ARTIFACT_GROWTH_TITLES.get(orientation_key, []):
        if level >= threshold:
            title = label
    return title

# 结丹与化婴的名字由角色自身资质参与生成,同一品级也能留下不同道途印记。
DAO_FRUIT_PREFIXES = {
    'metal': ['庚金', '太白', '藏锋', '玄铁'], 'wood': ['青木', '建木', '长生', '回春'],
    'water': ['玄水', '沧溟', '太阴', '冰魄'], 'fire': ['赤阳', '离火', '金乌', '焚天'],
    'earth': ['玄黄', '厚土', '昆仑', '息壤'], None: ['无垢', '混元', '紫府', '九窍', '太初'],
}
INFANT_FORMS = ['抱剑元婴', '青莲元婴', '雷纹元婴', '无相元婴', '紫府元婴', '玄黄元婴',
                '星辉元婴', '离火元婴', '冰魄元婴', '长生元婴', '太虚元婴', '道胎元婴']

def roll_dan_name(element_key=None, orientation_key=None):
    pool = list(DAO_FRUIT_PREFIXES.get(element_key, DAO_FRUIT_PREFIXES[None]))
    if orientation_key == 'offense': pool += ['风雷', '破军', '剑心']
    elif orientation_key == 'defense': pool += ['不动', '镇岳', '金刚']
    elif orientation_key == 'support': pool += ['灵犀', '天机', '造化']
    return random.choice(pool) + '金丹'

def roll_infant_name(element_key=None, orientation_key=None):
    elemental = {'metal': '庚金元婴', 'wood': '青木元婴', 'water': '玄水元婴',
                 'fire': '赤阳元婴', 'earth': '玄黄元婴'}.get(element_key)
    pool = list(INFANT_FORMS)
    if elemental: pool.append(elemental)
    if orientation_key == 'offense': pool += ['抱剑元婴', '雷纹元婴']
    elif orientation_key == 'defense': pool += ['青莲元婴', '玄黄元婴']
    elif orientation_key == 'support': pool += ['无相元婴', '太虚元婴']
    return random.choice(pool)

TECHNIQUE_INSIGHTS = {
    'metal': ['藏锋', '贯虹', '照胆'], 'wood': ['回春', '生生', '青华'],
    'water': ['听潮', '镜心', '沧浪'], 'fire': ['流火', '炎阳', '焚心'],
    'earth': ['镇岳', '不动', '承天'], None: ['入微', '通玄', '忘我'],
}

def roll_technique_insight(element_key=None):
    return random.choice(TECHNIQUE_INSIGHTS.get(element_key, TECHNIQUE_INSIGHTS[None]))

EQUIPMENT_LORE_FLAVORS = [
    '于{zone}外围一具无名古修遗骸旁所得', '在{zone}石壁暗格中寻得',
    '从{zone}守境妖物的巢穴中取出', '于{zone}核心区域异光显现时所得',
    '在{zone}一场恶战之后偶然发现', '自{zone}尘封多年的宝匣中开启',
]

def roll_equipment_lore(zone_label):
    return random.choice(EQUIPMENT_LORE_FLAVORS).format(zone=zone_label)

# 武器/防具/饰品:固定模板(非随机词条),每座秘境掉落一小批,按境界门槛分高低档——
# 第一版保持精简,不做随机词条/强化石,留给以后再扩展。
EQUIPMENT_DROP_TEMPLATES = {
    'qinglan': [
        {'slot': 'weapon',    'key': 'qinglan_dagger', 'label': '青岚淬毒匕', 'weapon_style': 'blade', 'attack': 6,  'defense': 0,  'agility': 3, 'luck': 0, 'element': 'wood'},
        {'slot': 'weapon',    'key': 'qinglan_hammer', 'label': '药谷承露锤', 'weapon_style': 'heavy', 'attack': 5,  'defense': 4,  'agility': 0, 'luck': 0, 'element': 'wood'},
        {'slot': 'armor',     'key': 'qinglan_robe',   'label': '药谷软甲',   'attack': 0,  'defense': 6,  'agility': 1, 'luck': 0},
        {'slot': 'accessory', 'key': 'qinglan_pouch',  'label': '采药荷包',   'attack': 0,  'defense': 0,  'agility': 2, 'luck': 3},
    ],
    'chiyan': [
        {'slot': 'weapon',    'key': 'chiyan_blade',   'label': '赤炎裂焰刀', 'weapon_style': 'blade', 'attack': 12, 'defense': 0,  'agility': 2, 'luck': 0, 'element': 'fire'},
        {'slot': 'weapon',    'key': 'chiyan_hammer',  'label': '熔岩镇火锤', 'weapon_style': 'heavy', 'attack': 10, 'defense': 6,  'agility': 0, 'luck': 0, 'element': 'fire'},
        {'slot': 'armor',     'key': 'chiyan_plate',   'label': '熔岩甲',     'attack': 0,  'defense': 12, 'agility': 0, 'luck': 0},
        {'slot': 'accessory', 'key': 'chiyan_ring',    'label': '避火戒',     'attack': 0,  'defense': 3,  'agility': 4, 'luck': 2},
    ],
    'guxiu': [
        {'slot': 'weapon',    'key': 'guxiu_sword',    'label': '古修断刃',   'weapon_style': 'sword', 'attack': 20, 'defense': 0,  'agility': 4, 'luck': 0, 'element': 'earth'},
        {'slot': 'weapon',    'key': 'guxiu_halberd',  'label': '傀儡巨戟',   'weapon_style': 'heavy', 'attack': 16, 'defense': 10, 'agility': 0, 'luck': 0, 'element': 'earth'},
        # 前朝修士遗物,并非本区域主属性,但强度对齐同价位的土属性两件——给水灵根弟子留一条秘境入手路
        {'slot': 'weapon',    'key': 'guxiu_water_spear', 'label': '寒潭夺魄枪', 'weapon_style': 'spear',  'attack': 18, 'defense': 2,  'agility': 6, 'luck': 0, 'element': 'water'},
        {'slot': 'weapon',    'key': 'guxiu_water_bow',   'label': '玄冰流光弩', 'weapon_style': 'ranged', 'attack': 15, 'defense': 0,  'agility': 9, 'luck': 0, 'element': 'water'},
        {'slot': 'armor',     'key': 'guxiu_armor',    'label': '傀儡甲片',   'attack': 0,  'defense': 20, 'agility': 0, 'luck': 0},
        {'slot': 'accessory', 'key': 'guxiu_talisman', 'label': '阵眼玉牌',   'attack': 0,  'defense': 4,  'agility': 8, 'luck': 5},
    ],
    'zangjian': [
        {'slot': 'weapon',    'key': 'zangjian_blade',  'label': '残剑吟风', 'weapon_style': 'sword', 'attack': 30, 'defense': 0,  'agility': 6, 'luck': 0, 'element': 'metal'},
        {'slot': 'weapon',    'key': 'zangjian_saber',  'label': '裂魂巨斧', 'weapon_style': 'heavy', 'attack': 24, 'defense': 12, 'agility': 0, 'luck': 0, 'element': 'metal'},
        {'slot': 'armor',     'key': 'zangjian_shroud', 'label': '剑冢裹魂衣', 'attack': 0,  'defense': 30, 'agility': 2, 'luck': 0},
        {'slot': 'accessory', 'key': 'zangjian_ring',   'label': '执念魂戒', 'attack': 4,  'defense': 4,  'agility': 10, 'luck': 6},
    ],
    'jiuyou': [
        {'slot': 'weapon',    'key': 'jiuyou_blade',   'label': '噬魂剑', 'weapon_style': 'sword', 'attack': 48, 'defense': 0,  'agility': 8, 'luck': 0, 'element': 'water'},
        {'slot': 'weapon',    'key': 'jiuyou_hammer',  'label': '幽渊镇魄锤', 'weapon_style': 'heavy', 'attack': 38, 'defense': 16, 'agility': 0, 'luck': 0, 'element': 'water'},
        {'slot': 'armor',     'key': 'jiuyou_armor',   'label': '幽渊神魂甲', 'attack': 0,  'defense': 46, 'agility': 2, 'luck': 0},
        {'slot': 'accessory', 'key': 'jiuyou_pendant', 'label': '噬魂珮', 'attack': 6,  'defense': 6,  'agility': 14, 'luck': 8},
    ],
}
EQUIPMENT_TEMPLATES_BY_KEY = {t['key']: dict(t, zone=zone)
                               for zone, tpls in EQUIPMENT_DROP_TEMPLATES.items() for t in tpls}

# 炼器峰弟子可自行锻造的基础款武器/防具:比秘境里最弱的青岚药谷那档还要再弱一档,
# 给没运气吃到秘境掉落的人一条保底线,不吃随机,炼器师稳定产出。
FORGE_GEAR_MATERIAL_COST = {'low': 3}  # 打造基础装备图纸不再耗体力,改耗通用灵材
EQUIPMENT_BASIC_TEMPLATES = [
    {'slot': 'weapon', 'key': 'forge_basic_blade', 'label': '锻造铁剑', 'weapon_style': 'sword', 'attack': 3, 'defense': 0, 'agility': 1, 'luck': 0, 'element': 'metal'},
    {'slot': 'armor',  'key': 'forge_basic_armor', 'label': '锻造铁甲', 'attack': 0, 'defense': 3, 'agility': 0, 'luck': 0},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone=None) for t in EQUIPMENT_BASIC_TEMPLATES})

# 宗门兵器堂向所有弟子开放的制式武器，确保每条兵道都有稳定入门途径。
SECT_STARTER_WEAPON_COST = 30
SECT_STARTER_WEAPONS = [
    {'slot': 'weapon', 'key': 'sect_iron_sword', 'label': '宗门青锋剑', 'weapon_style': 'sword', 'attack': 3, 'defense': 0, 'agility': 1, 'luck': 0, 'element': 'metal'},
    {'slot': 'weapon', 'key': 'sect_long_blade', 'label': '宗门雁翎刀', 'weapon_style': 'blade', 'attack': 4, 'defense': 0, 'agility': 0, 'luck': 0, 'element': 'water'},
    {'slot': 'weapon', 'key': 'sect_cloud_spear', 'label': '宗门穿云枪', 'weapon_style': 'spear', 'attack': 3, 'defense': 1, 'agility': 0, 'luck': 0, 'element': 'wood'},
    {'slot': 'weapon', 'key': 'sect_mountain_hammer', 'label': '宗门镇山锤', 'weapon_style': 'heavy', 'attack': 3, 'defense': 1, 'agility': 0, 'luck': 0, 'element': 'earth'},
    {'slot': 'weapon', 'key': 'sect_spirit_bow', 'label': '宗门逐风弓', 'weapon_style': 'ranged', 'attack': 2, 'defense': 0, 'agility': 2, 'luck': 0, 'element': 'fire'},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone='sect') for t in SECT_STARTER_WEAPONS})

# 限量一件的强力装备:不进秘境常规掉落池,全宗独一份,先到先得——跟仙骨(IMMORTAL_BONES)
# 同一个"claimed 集合"思路,只是这里靠查 character_equipment 里谁已经领过,不需要额外加字段。
# 只在古修洞府/葬剑遗址(秘境里较高阶的两座)的机缘事件里有小概率触发。
UNIQUE_EQUIPMENT_ZONES = ['guxiu', 'zangjian', 'jiuyou']
UNIQUE_EQUIPMENT_DROP_CHANCE = 0.03
UNIQUE_EQUIPMENT_TEMPLATES = [
    {'slot': 'weapon',    'key': 'unique_tianhen_sword',  'label': '天痕剑', 'weapon_style': 'sword', 'attack': 45, 'defense': 5,  'agility': 8,  'luck': 0, 'element': 'metal'},
    {'slot': 'armor',     'key': 'unique_xuanming_armor', 'label': '玄冥甲', 'attack': 0,  'defense': 45, 'agility': 5,  'luck': 0},
    {'slot': 'accessory', 'key': 'unique_huanri_pendant', 'label': '换日佩', 'attack': 10, 'defense': 10, 'agility': 15, 'luck': 10},
    # 九幽渊同批新增,跟上面三件共用一套"仙缘·闯关成功小概率触发"的旷世奇珍逻辑,数值再上一档
    {'slot': 'weapon',    'key': 'unique_yuming_blade',   'label': '幽冥噬魂刀', 'weapon_style': 'blade', 'attack': 50, 'defense': 4,  'agility': 10, 'luck': 0, 'element': 'water'},
    {'slot': 'armor',     'key': 'unique_jiuyou_scale',   'label': '九幽鳞甲', 'attack': 0,  'defense': 50, 'agility': 6,  'luck': 0},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone='unique') for t in UNIQUE_EQUIPMENT_TEMPLATES})

# 天地精华商城武器:纯展示柜品,金木水火土各一件,不进任何掉落表/锻造配方——只有充值入口真正开放
# 那天才可能买到,现在充值和商城都是摆设,谁也拿不到。
TIANDI_SHOP_WEAPONS = [
    {'slot': 'weapon', 'key': 'tiandi_jinjian',  'label': '太昊真金剑', 'weapon_style': 'sword',
     'attack': 50, 'defense': 5,  'agility': 10, 'luck': 0, 'element': 'metal'},
    {'slot': 'weapon', 'key': 'tiandi_muqiang',  'label': '青冥长生藤枪', 'weapon_style': 'spear',
     'attack': 46, 'defense': 8,  'agility': 8,  'luck': 0, 'element': 'wood'},
    {'slot': 'weapon', 'key': 'tiandi_shuigong', 'label': '玄涛逐月弓', 'weapon_style': 'ranged',
     'attack': 44, 'defense': 0,  'agility': 14, 'luck': 0, 'element': 'water'},
    {'slot': 'weapon', 'key': 'tiandi_huodao',   'label': '烬天焚决刀', 'weapon_style': 'blade',
     'attack': 52, 'defense': 2,  'agility': 6,  'luck': 0, 'element': 'fire'},
    {'slot': 'weapon', 'key': 'tiandi_tuchui',   'label': '息壤镇岳锤', 'weapon_style': 'heavy',
     'attack': 42, 'defense': 16, 'agility': 0,  'luck': 0, 'element': 'earth'},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone='tiandi_shop') for t in TIANDI_SHOP_WEAPONS})
TIANDI_SHOP_WEAPON_COST = 150  # 统一售价,约合人民币15元档位

# 游历人间专属装备:秘境不会掉,只从游历遇险力战取胜/传说奇遇里出,走江湖气而非门派制式的路子
TRAVEL_EQUIPMENT_TEMPLATES = {
    'qingshi': [
        {'slot': 'weapon',    'key': 'qingshi_travel_saber',  'label': '风尘断魂刀',
         'weapon_style': 'blade', 'attack': 10, 'defense': 0, 'agility': 3, 'luck': 1, 'element': 'earth'},
        {'slot': 'armor',     'key': 'qingshi_travel_cloak',  'label': '踏尘游侠衣',
         'attack': 0,  'defense': 8, 'agility': 4, 'luck': 1},
        {'slot': 'accessory', 'key': 'qingshi_travel_charm',  'label': '江湖救急铃',
         'attack': 0,  'defense': 2, 'agility': 2, 'luck': 4},
    ],
}
for _region_key, _tpls in TRAVEL_EQUIPMENT_TEMPLATES.items():
    EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone=f'travel_{_region_key}') for t in _tpls})
TRAVEL_EQUIPMENT_DROP_CHANCE = 0.08  # 遇险力战取胜时,额外有此概率拾得游历专属装备

# 行侠令专属装备:走江湖游侠路子而非门派制式,只从行侠令任务成功时小概率掉落
XIAXIA_EQUIPMENT_DROP_CHANCE = 0.06
XIAXIA_EQUIPMENT_TEMPLATES = [
    {'slot': 'weapon',    'key': 'xiaxia_broken_blade',  'label': '断案惊魂刃',
     'weapon_style': 'blade', 'attack': 12, 'defense': 0, 'agility': 2, 'luck': 2, 'element': 'fire'},
    {'slot': 'armor',     'key': 'xiaxia_ranger_cloak',  'label': '仗义游侠袍',
     'attack': 0,  'defense': 9, 'agility': 3, 'luck': 2},
    {'slot': 'accessory', 'key': 'xiaxia_bell_token',    'label': '侠名令牌',
     'attack': 0,  'defense': 1, 'agility': 1, 'luck': 5},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone='xiaxia') for t in XIAXIA_EQUIPMENT_TEMPLATES})

# ── 兵道熟练:与峰门、个人道途相互独立,实际拿什么兵器取胜就磨炼什么 ─────────────────
WEAPON_DISCIPLINES = {
    'sword': {'label': '剑修', 'stack_label': '剑意', 'flavor': '剑走一线，重在破罡见隙',
              'bonus_key': 'ignore_defense', 'max_bonus': 10, 'basic_label': '御剑·青芒',
              'battle_intro': ['{weapon}在鞘中轻鸣，剑意先你一步锁住了敌手。', '你并指抹过{weapon}剑脊，一线寒芒映入眼底。'],
              'basic_flavors': ['{weapon}破空而去，剑光只在半途一闪，已逼至敌前。', '你并指一引，{weapon}化作一道青虹贯向敌阵。'],
              'victory_flavors': ['你振腕收剑，{weapon}清鸣一声归于身侧。', '敌影倒下时，{weapon}已敛尽锋芒，仿佛从未出鞘。'],
              'equip_flavors': ['{weapon}入手轻鸣，似在试探你这一身剑意。'],
              'level_flavors': ['剑鸣比往日更清越——你与{weapon}之间，已不必再分彼此。']},
    'blade': {'label': '刀修', 'stack_label': '刀势', 'flavor': '刀行决绝，敌弱则一往无前',
              'bonus_key': 'execute_damage', 'max_bonus': 12, 'basic_label': '拔刀·断流',
              'battle_intro': ['你缓缓推出{weapon}半寸，森然刀光已让四周一静。', '你单手按住{weapon}，刀势沉凝，只等一个出鞘的时机。'],
              'basic_flavors': ['{weapon}悍然斩落，刀风贴地卷出一道深痕。', '你踏前半步，借腰背之力挥动{weapon}横断敌前。'],
              'victory_flavors': ['你甩去{weapon}上的煞气，反手收刀。', '这一刀既出便没有回头，敌手倒下时刀势方才散尽。'],
              'equip_flavors': ['{weapon}沉沉坠在掌中，正合一往无前的刀意。'],
              'level_flavors': ['你忽然明白，真正的刀势不在招式，而在出刀前那一念决绝。']},
    'spear': {'label': '枪修', 'stack_label': '枪势', 'flavor': '一点寒芒先至，讲究先声夺人',
              'bonus_key': 'opening_damage', 'max_bonus': 15, 'basic_label': '枪式·惊鸿',
              'battle_intro': ['你横持{weapon}，枪尖微颤，丈外气机尽在锋芒之下。', '你沉肩坠肘，{weapon}前指，先机已被这一枪夺走。'],
              'basic_flavors': ['你拧身送臂，{weapon}如毒龙出洞直取中门。', '{weapon}抖出数点寒星，虚实相叠罩住敌手。'],
              'victory_flavors': ['你顿枪于地，余势沿着{weapon}枪杆嗡然散去。', '你抽枪退步，枪尖仍稳稳指着敌手倒下的方向。'],
              'equip_flavors': ['{weapon}长杆一震，枪尖寒芒正与呼吸同起同落。'],
              'level_flavors': ['枪尖一点寒芒凝而不散，你终于握住了“先至”二字的真意。']},
    'heavy': {'label': '重兵修', 'stack_label': '撼势', 'flavor': '以力破巧，攻守皆如山岳',
              'bonus_key': 'counter_reduce', 'max_bonus': 12, 'basic_label': '重式·撼岳',
              'battle_intro': ['你将{weapon}往肩上一扛，脚下地面随之微微一沉。', '{weapon}落地如钟，沉闷震声把敌意都压低了几分。'],
              'basic_flavors': ['你吐气开声，抡起{weapon}自上而下轰然砸落。', '{weapon}裹着沉重罡风横扫而过，逼得敌手无处借力。'],
              'victory_flavors': ['你把{weapon}拄回地面，四散烟尘这才缓缓落定。', '最后一击余震未止，你已稳稳收住{weapon}的万钧之势。'],
              'equip_flavors': ['你双手接过{weapon}，沉重分量反而令人心安。'],
              'level_flavors': ['举重若轻并非无力，而是万钧之势已尽数收进你的骨血。']},
    'ranged': {'label': '弓修', 'stack_label': '弦意', 'flavor': '神念锁敌，蓄势于弦而制敌于远',
               'bonus_key': 'basic_mp_regen', 'max_bonus': 10, 'basic_label': '灵矢·追风',
               'battle_intro': ['你挽起{weapon}，一缕灵光在空弦之上凝成箭形。', '你侧身搭指，{weapon}尚未拉满，神念已钉住敌手。'],
               'basic_flavors': ['弦声乍响，{weapon}射出的灵矢拖着流光直追敌影。', '你松指放弦，灵矢在半空微折，封死了敌手退路。'],
               'victory_flavors': ['最后一缕弦音散去，你垂下{weapon}，远处敌影应声而倒。', '你收回锁敌神念，{weapon}弓弦仍在指间轻颤。'],
               'equip_flavors': ['你轻拨{weapon}之弦，清越弦音正合神念运转。'],
               'level_flavors': ['心念所至，箭锋便至——弓弦与神识终于连成一线。']},
    'unarmed': {'label': '武修', 'stack_label': '拳罡', 'flavor': '肉身为炉，拳脚便是本命兵刃',
                'bonus_key': 'max_hp', 'max_bonus': 15, 'basic_label': '拳式·开山',
                'battle_intro': ['你沉腰立马，五指缓缓收拢，筋骨间响起细密雷音。', '你空手向前一步，周身气血奔涌，拳锋便是最可信的兵刃。'],
                'basic_flavors': ['你一拳递出，拳罡先于血肉撞上敌手。', '你踏碎脚下浮尘，肩背贯通的一拳悍然轰出。'],
                'victory_flavors': ['你缓缓吐出一口浊气，沸腾气血重归丹田。', '你收拳立定，筋骨雷音渐息，身形仍如山岳。'],
                'equip_flavors': ['你卸下兵刃，活动十指——这一身筋骨便是法宝。'],
                'level_flavors': ['气血奔流如江河，你终于将这具肉身炼成了真正的兵刃。']},
}
WEAPON_MASTERY_THRESHOLDS = [0, 3, 10, 25, 50, 100]
WEAPON_MASTERY_TITLES = ['初窥门径', '登堂入室', '势成于身', '人器相合', '意通神明', '一代宗师']

def weapon_discipline_level(mastery):
    mastery = max(0, mastery or 0)
    return max(i for i, threshold in enumerate(WEAPON_MASTERY_THRESHOLDS) if mastery >= threshold)

def weapon_discipline_bonus(style, mastery):
    info = WEAPON_DISCIPLINES.get(style, WEAPON_DISCIPLINES['unarmed'])
    level = weapon_discipline_level(mastery)
    return round(info['max_bonus'] * level / (len(WEAPON_MASTERY_THRESHOLDS) - 1))

_UNCLASSIFIED_WEAPONS = [t['key'] for t in EQUIPMENT_TEMPLATES_BY_KEY.values()
                         if t.get('slot') == 'weapon' and t.get('weapon_style') not in WEAPON_DISCIPLINES]
if _UNCLASSIFIED_WEAPONS:
    raise ValueError(f"以下武器缺少有效兵道分类: {_UNCLASSIFIED_WEAPONS}")

# 装备分解:按来源产地换算炼器材料,全宗独一份的 unique 装备不可分解(见 equipment_decompose 里的拦截)
EQUIPMENT_DECOMPOSE_YIELD = {
    None: {'low': 2}, 'qinglan': {'low': 3}, 'chiyan': {'mid': 2}, 'guxiu': {'high': 2}, 'zangjian': {'top': 1},
    'jiuyou': {'top': 2},
    'travel_qingshi': {'mid': 2}, 'xiaxia': {'mid': 2},
}

# 灵巧:多重挂钩(闪避/脱身/识破陷阱),不是"换了名字的防御"；伤害/闪避都设了上限,避免高阶战斗失控
MYSTIC_AGILITY_DODGE_CAP = 0.35
MYSTIC_AGILITY_DODGE_PER_POINT = 0.006
MYSTIC_AGILITY_ESCAPE_BONUS_PER_POINT = 0.01
MYSTIC_AGILITY_TRAP_CHECK_BASE = 0.55
MYSTIC_AGILITY_TRAP_CHECK_PER_POINT = 0.01

def mystic_dodge_chance(agility):
    return min(MYSTIC_AGILITY_DODGE_CAP, (agility or 0) * MYSTIC_AGILITY_DODGE_PER_POINT)

def mystic_trap_check_chance(agility):
    return min(0.9, MYSTIC_AGILITY_TRAP_CHECK_BASE + (agility or 0) * MYSTIC_AGILITY_TRAP_CHECK_PER_POINT)

# ── 洞府地图:入门先住宗门公共居所,拜入峰(=有师父)后可搬进本峰弟子居所,与师兄弟同住 ──────
# 只有自己所在的那一个峰会解锁,其余峰的居所永远无法入住(峰归属终身唯一,不需要处理迁出)

CAVE_PEAK_BONUS = {
    '紫霄峰': {'cave_purity': 10},
    '云海峰': {'cave_purity': 15},
    '天枢峰': {'cave_qi': 15},
    '玄穹峰': {'cave_stability': 15},
    '太虚峰': {'cave_qi': 20},
    '星阑峰': {'cave_qi': 5, 'cave_purity': 5},
    '沧澜峰': {'cave_reputation_pct': 10, 'cave_purity': -10},
    '凌霄峰': {'cave_qi': 10, 'cave_purity': 10, 'cave_stability': 10},
}
CAVE_LOCATION_COMMON = 'common'  # 宗门后山公共居所,无加成,人人起步于此

def cave_location_bonus(location_key):
    return CAVE_PEAK_BONUS.get(location_key, {})

# ── 灵宠:物种固定品级,外貌前缀+物种组成个体名;紫霄峰培育,全宗可交易饲养 ────────────

PET_QUALITIES = {
    'low':  {'label': '下品', 'weight': 60, 'max_level': 5,  'base_bonus_pct': 8,  'bonus_per_level': 2},
    'mid':  {'label': '中品', 'weight': 28, 'max_level': 6,  'base_bonus_pct': 10, 'bonus_per_level': 2},
    'high': {'label': '上品', 'weight': 10, 'max_level': 8,  'base_bonus_pct': 12, 'bonus_per_level': 2},
    'top':  {'label': '超品', 'weight': 2,  'max_level': 10, 'base_bonus_pct': 15, 'bonus_per_level': 2},
}
PET_QUALITY_ORDER = ['low', 'mid', 'high', 'top']

PET_TYPES = {
    # 下品:山门附近常见的开灵小兽,容易培育,成长上限较低。
    'linghu':       {'label': '灵狐',   'quality': 'low', 'desc': '机灵亲人,善察细微气息。', 'stat': 'exp'},
    'xuangui':      {'label': '玄龟仔', 'quality': 'low', 'desc': '性情沉稳,常伴主人静修。', 'stat': 'contribution'},
    'fengling_que': {'label': '风铃雀', 'quality': 'low', 'desc': '鸣声清脆,最爱追逐灵风。', 'stat': 'exp'},
    'xunbao_shu':   {'label': '寻宝鼠', 'quality': 'low', 'desc': '嗅觉敏锐,喜欢收集亮物。', 'stat': 'contribution'},
    'qingzhu_she':  {'label': '青竹蛇', 'quality': 'low', 'desc': '隐于竹影,安静而机警。', 'stat': 'exp'},
    'yulu_tu':      {'label': '玉露兔', 'quality': 'low', 'desc': '温顺柔软,亲近灵草晨露。', 'stat': 'contribution'},
    'songyan_li':   {'label': '松烟狸', 'quality': 'low', 'desc': '身法轻灵,喜欢夜间巡游。', 'stat': 'exp'},
    'lingjiao_lu':  {'label': '灵角鹿', 'quality': 'low', 'desc': '气息温和,能安抚躁动灵气。', 'stat': 'contribution'},
    # 中品:血脉已显异象,是紫霄峰较成熟的培育成果。
    'huoyan_hu':    {'label': '火焰狐', 'quality': 'mid', 'desc': '尾生灵焰,性烈而忠诚。', 'stat': 'exp'},
    'yun_he':       {'label': '云鹤',   'quality': 'mid', 'desc': '踏云而行,鸣声清越。', 'stat': 'contribution'},
    'leiying':      {'label': '雷鹰',   'quality': 'mid', 'desc': '羽蕴电芒,目力极佳。', 'stat': 'exp'},
    'hanshuang_lang': {'label': '寒霜狼', 'quality': 'mid', 'desc': '吐息凝霜,极重同伴情义。', 'stat': 'exp'},
    'bibo_li':      {'label': '碧波鲤', 'quality': 'mid', 'desc': '鳞泛碧光,可游于灵泉云海。', 'stat': 'contribution'},
    'jinyu_die':    {'label': '金羽蝶', 'quality': 'mid', 'desc': '振翅洒落细碎灵光。', 'stat': 'contribution'},
    'moyun_bao':    {'label': '墨云豹', 'quality': 'mid', 'desc': '来去无声,身影如墨云。', 'stat': 'exp'},
    'shiyan_hou':   {'label': '石岩猴', 'quality': 'mid', 'desc': '聪敏强健,擅寻山中灵果。', 'stat': 'contribution'},
    # 上品:罕见灵兽,血脉与神通已具雏形。
    'bai_zeli':     {'label': '白泽猊', 'quality': 'high', 'desc': '通灵晓意,能辨吉凶异兆。', 'stat': 'contribution'},
    'qingluan':     {'label': '青鸾',   'quality': 'high', 'desc': '青羽含霞,鸣声可清心神。', 'stat': 'exp'},
    'bixie':        {'label': '辟邪兽', 'quality': 'high', 'desc': '威严护主,不喜邪祟近身。', 'stat': 'contribution'},
    'jiaolong':     {'label': '幼蛟',   'quality': 'high', 'desc': '初具龙形,可引水聚云。', 'stat': 'exp'},
    'lihuo_que':    {'label': '离火雀', 'quality': 'high', 'desc': '羽若流火,浴焰而不伤。', 'stat': 'exp'},
    'tunxing_chan': {'label': '吞星蟾', 'quality': 'high', 'desc': '腹藏星辉,吐纳月华。', 'stat': 'contribution'},
    # 超品:仅极少数培育成功的神兽遗种,物种本身即代表品级。
    'qilin_yi':     {'label': '麒麟遗种', 'quality': 'top', 'desc': '身负麒麟古血,行止自有祥瑞相随。', 'stat': 'contribution'},
    'zhuque_chu':   {'label': '朱雀雏鸟', 'quality': 'top', 'desc': '涅槃真火未盛,已显百鸟朝仪。', 'stat': 'exp'},
    'kunpeng_zai':  {'label': '鲲鹏幼崽', 'quality': 'top', 'desc': '可化鱼鸟二相,吞吐云海。', 'stat': 'exp'},
    'zhulong_zai':  {'label': '烛龙幼兽', 'quality': 'top', 'desc': '双目含晦明之意,血脉古老。', 'stat': 'contribution'},
}
PET_APPEARANCES = [
    '银尾', '金尾', '墨尾', '霜尾', '墨瞳', '赤瞳', '金瞳', '碧瞳', '紫瞳', '踏雪',
    '踏云', '照夜', '流云', '流霞', '流火', '凝霜', '霜鬓', '雪鬓', '金纹', '银纹',
    '雷纹', '云纹', '月白', '玄黑', '青羽', '金羽', '霞翎', '雪翎', '星斑', '月斑',
    '玉角', '金角', '冰角', '赤爪', '墨爪', '雪爪', '灵光', '幽影', '朝露', '晚星',
]
PET_PERSONALITIES = ['亲人', '高傲', '胆小', '沉稳', '顽皮', '忠诚', '贪吃', '机警', '慵懒', '好奇']
PET_HABITS = ['爱叼走丹瓶', '喜欢守在洞府门口', '常在打坐时依偎身旁', '一听雷声便格外兴奋',
              '总爱追逐流萤', '喜欢藏进药圃', '见到陌生人便躲起来', '常对着月亮发呆',
              '会把捡来的小石头献给主人', '喜欢趴在法宝旁睡觉']

def roll_pet_identity():
    return random.choice(PET_APPEARANCES), random.choice(PET_PERSONALITIES), random.choice(PET_HABITS)

def roll_pet_type():
    quality = random.choices(PET_QUALITY_ORDER,
                             weights=[PET_QUALITIES[k]['weight'] for k in PET_QUALITY_ORDER], k=1)[0]
    return random.choice([key for key, pet in PET_TYPES.items() if pet['quality'] == quality])

def pet_quality(pet_key):
    return PET_TYPES.get(pet_key, {}).get('quality', 'low')

def pet_max_level(pet_key):
    return PET_QUALITIES[pet_quality(pet_key)]['max_level']

# 灵宠多养:身边(roster)上限8只,超额先进临时驿站(holding),24小时内不处理自动转灵兽峰(sanctuary)
PET_ROSTER_CAP = 8
PET_HOLDING_HOURS = 24
PET_ADOPT_STAMINA_COST = 30  # 收养耗体力+每日限次,防止零成本无限孵化囤货转卖
PET_ADOPT_DAILY_LIMIT = 1

def pet_image_url(pet_key):
    return f"/static/images/pets/{pet_key}.png"

PET_BASE_BONUS_PCT = PET_QUALITIES['low']['base_bonus_pct']  # 旧调用兼容
PET_BONUS_PER_LEVEL = PET_QUALITIES['low']['bonus_per_level']
PET_MAX_LEVEL = PET_QUALITIES['top']['max_level']             # 全物种理论最高等级
PET_EXP_PER_LEVEL = 100   # 训养积累到多少经验升一级
PET_TRAIN_STAMINA_COST = 15
PET_TRAIN_DAILY_LIMIT = 3
PET_TRAIN_EXP_RANGE = (15, 30)

def pet_bonus_pct(level, pet_key=None):
    quality = PET_QUALITIES[pet_quality(pet_key)]
    level = max(1, min(level or 1, quality['max_level']))
    return quality['base_bonus_pct'] + (level - 1) * quality['bonus_per_level']

# 出战灵宠助战:不分物种方向(exp/contribution),每回合独立判定,命中则按品级+等级那套
# 现成的 pet_bonus_pct 换算成玩家攻击力的百分比追加一次伤害,不单独设一套战斗专属数值。
PET_ASSIST_CHANCE = 0.7

# 出战灵宠练到满级(各品级 max_level 不同,练满代表真正养成了)再给一份固定战斗加成,
# 跟原本的助战伤害是两码事——满级本身就该是个看得见的里程碑,不只是数值曲线的终点。
PET_MAX_LEVEL_COMBAT_ATTACK_BONUS = 10
PET_MAX_LEVEL_COMBAT_DEFENSE_BONUS = 10

# ── 寻找前世:五环节依次收窄性别/时代/身份/气质/结局五个标签;每环节"静心溯忆"攒够进度后
# 三选一,选项按当前剩余候选人现场分组生成(取人数最多的3组),保证不会选出候选为0的死路。
# 全宗候选人共用一份名单,谁先集齐五个标签定下来,那位历史名人就归谁,别人再也选不到——
# 越到后面重名的人越少,才有"这个位置被人占了"的紧张感,不是纯粹的随机抽奖。

PASTLIFE_UNLOCK_REALM_IDX = 6      # 金丹初期起可修习,筑基气血未稳,前尘杂念反倒扰道
PASTLIFE_STAMINA_COST = 15
PASTLIFE_DAILY_LIMIT = 8
PASTLIFE_PROGRESS_RANGE = (20, 35)
PASTLIFE_STAGE_THRESHOLD = 100
PASTLIFE_MATERIAL_TIER_WEIGHTS = {'low': 50, 'mid': 40, 'high': 10}  # 每次静心溯忆必定拾得1份通用灵材,不白费体力

# 静心溯忆额外拾得传承血脉碎片:每次随机拾得某一门(TALENTS任选其一)的碎片,不同门类不可互换;
# 凑齐同一门10片即可合成为那一门传承/血脉,已有传承/血脉的合成后会被顶替——跟"打坐随机觅得传承"
# 是两条互不冲突的获取路。具体是哪一门由 TALENTS 的 key 决定,碎片的 material_key 是 "<talent_key>_shard"。
PASTLIFE_TALENT_SHARD_CHANCE = 0.5
PASTLIFE_TALENT_SHARD_COST = 10
PASTLIFE_SHARD_TRADE_MAX_ACTIVE = 5  # 同时挂出的碎片交换请求上限;创建就要抵押1片碎片,天然防刷

# 强化:已经有传承/血脉的人,再集齐10片"自己那一门"的碎片,可以强化自身,不占用一次性的合成/换门
# 名额,可反复叠加——碎片对已定型的人来说不是没用,只是从"能不能拿到"变成"能不能强化"。
PASTLIFE_TALENT_REINFORCE_COST = 10
PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS = 5
PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS = 5

# 前尘揭晓后的战斗加成:五环节走完不只是个称号,给点实打实的攻防,跟仙骨的加成走同一条叠加线。
# 起名"前世今生"——不是抽象的数值加成,是那段前尘武道随着揭晓真正接入了这具身体,
# 前世的锋芒,今生的力量,叫这个名字才有代入感。
PASTLIFE_COMBAT_BUFF_LABEL = '前世今生'
PASTLIFE_COMBAT_ATTACK_BONUS = 20
PASTLIFE_COMBAT_DEFENSE_BONUS = 20

def pastlife_talent_shard_key(talent_key):
    return f"{talent_key}_shard"

PASTLIFE_DIMENSIONS = ['gender', 'era', 'profession', 'temperament', 'fate']

PASTLIFE_STAGES = [
    {'key': 'gender', 'label': '溯魂启梦', 'desc': '闭目凝神,于混沌识海中初触前尘一丝残影。'},
    {'key': 'era', 'label': '时代回响', 'desc': '残影渐清,依稀可辨那是哪朝哪代的风声鹤唳。'},
    {'key': 'profession', 'label': '身份浮现', 'desc': '一段身份的轮廓浮出水面,却仍雾里看花。'},
    {'key': 'temperament', 'label': '气质映照', 'desc': '前尘之人的言行做派,渐渐与你此刻心境重叠。'},
    {'key': 'fate', 'label': '终局回眸', 'desc': '往事将尽,只差看清那人生最后一程走向何方。'},
]

PASTLIFE_DIMENSION_LABELS = {'gender': '性别', 'era': '时代', 'profession': '身份',
                              'temperament': '气质', 'fate': '结局'}

PASTLIFE_TAG_LABELS = {
    'gender': {'male': '男', 'female': '女'},
    'era': {'xianqin': '先秦', 'qinhan': '秦汉', 'weijin': '魏晋南北朝',
            'suitang': '隋唐', 'songyuan': '宋元', 'mingqing': '明清'},
    'profession': {'diwang': '帝王将相', 'mouchen': '谋臣策士', 'wenren': '文人骚客',
                   'xiake': '侠客游士', 'fangshi': '方士高人', 'qiaoyi': '巧匠医者', 'jiaren': '绝世佳人'},
    'temperament': {'haomai': '豪迈奔放', 'qingleng': '清冷孤高', 'yinren': '隐忍深沉',
                     'kuangfang': '狂放不羁', 'gangzhi': '耿直刚烈', 'fengliu': '风流蕴藉'},
    'fate': {'qingshi': '青史留名', 'weicheng': '壮志未酬', 'guiyin': '归隐山林',
             'gouxian': '横遭构陷', 'yuhua': '羽化超然'},
}

# 三选一按钮上的闪回文案,同一维度下不同取值各配一句,不点破答案、只给方向感
PASTLIFE_CHOICE_FLAVOR = {
    'gender': {'male': '依稀是男子身形,负手立于长风之中',
               'female': '分明是女子身影,衣袂在记忆里翩然而动'},
    'era': {'xianqin': '钟鸣鼎食,诸子百家争鸣的先秦气象',
            'qinhan': '铁马金戈,一统天下的秦汉肃杀',
            'weijin': '清谈玄理,乱世风骨的魏晋气度',
            'suitang': '万国来朝,气象恢弘的隋唐盛景',
            'songyuan': '烟雨楼台,词章婉转的宋元风华',
            'mingqing': '朱墙黛瓦,世情百态的明清烟火'},
    'profession': {'diwang': '庙堂之上,那是帝王将相的威仪',
                   'mouchen': '运筹帷幄,那是谋臣策士的心机',
                   'wenren': '青灯黄卷,那是文人骚客的风骨',
                   'xiake': '仗剑天涯,那是侠客游士的豪情',
                   'fangshi': '观星问道,那是方士高人的玄妙',
                   'qiaoyi': '妙手匠心,那是巧匠医者的执着',
                   'jiaren': '倾城一顾,那是绝世佳人的芳华'},
    'temperament': {'haomai': '豪迈奔放,快意恩仇不拘小节',
                    'qingleng': '清冷孤高,遗世独立不肯从流',
                    'yinren': '隐忍深沉,喜怒不形于色',
                    'kuangfang': '狂放不羁,率性而为惊世骇俗',
                    'gangzhi': '耿直刚烈,宁折不弯一身傲骨',
                    'fengliu': '风流蕴藉,才情过人顾盼生辉'},
    'fate': {'qingshi': '一生功业彪炳,终得青史留名',
             'weicheng': '壮志未酬,徒留后人扼腕',
             'guiyin': '看破浮华,终究归隐山林',
             'gouxian': '横遭构陷,结局令人唏嘘',
             'yuhua': '传说其人早已羽化超然,踪迹难寻'},
}

# 每次"静心溯忆"随机弹一句,按当前所在环节的维度取词,同样不剧透
PASTLIFE_PROGRESS_FLAVORS = {
    'gender': ['识海深处泛起微光,似有一道身影正欲显形。', '恍惚间听见一声轻唤,却看不清是谁在唤你。',
               '闭目凝神,那道残影又清晰了几分。'],
    'era': ['耳边似有编钟长鸣,又似有铁蹄踏破长街。', '眼前光影流转,朝代更迭如走马灯般掠过。',
            '你隐约嗅到了某个时代特有的气息。'],
    'profession': ['一双手的轮廓渐渐清晰——是执笔,还是执剑?', '你仿佛看见了那人平日里最常做的事。',
                   '前尘之人的身份,正一点点浮出水面。'],
    'temperament': ['那人处世的做派,渐渐与你此刻的心境重叠。', '你忽然明白了那人当年为何如此行事。',
                    '喜怒哀乐,竟与你此刻所感隐隐相通。'],
    'fate': ['往事将尽,你隐约看见了那人最后的身影。', '识海中传来一声长叹,不知是喜是悲。',
             '那段前尘,终于要看到结局了。'],
}

# 全宗候选池:60位中国历代真实/半传说人物,五个标签各自分布尽量均衡,一人一份、先到先得。
# epithet 是揭晓时拼进提示语的定语短句,不单独写60句完整揭晓文案,复用同一套模板即可。
PAST_LIFE_FIGURES = {
    'laozi':     {'name': '老子', 'gender': 'male', 'era': 'xianqin', 'profession': 'fangshi',
                  'temperament': 'qingleng', 'fate': 'yuhua', 'epithet': '骑青牛西出函谷、只留下五千言《道德经》便杳无踪迹的太上道祖'},
    'kongzi':    {'name': '孔子', 'gender': 'male', 'era': 'xianqin', 'profession': 'wenren',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '杏坛设教、周游列国的至圣先师'},
    'zhuangzi':  {'name': '庄子', 'gender': 'male', 'era': 'xianqin', 'profession': 'fangshi',
                  'temperament': 'kuangfang', 'fate': 'yuhua', 'epithet': '梦蝶逍遥、齐物忘我的南华真人'},
    'sunwu':     {'name': '孙武', 'gender': 'male', 'era': 'xianqin', 'profession': 'mouchen',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '著《孙子兵法》、兵家至圣的军师'},
    'xishi':     {'name': '西施', 'gender': 'female', 'era': 'xianqin', 'profession': 'jiaren',
                  'temperament': 'fengliu', 'fate': 'yuhua', 'epithet': '浣纱溪畔、沉鱼之貌的绝代佳人'},
    'fanli':     {'name': '范蠡', 'gender': 'male', 'era': 'xianqin', 'profession': 'mouchen',
                  'temperament': 'qingleng', 'fate': 'guiyin', 'epithet': '助越灭吴后泛舟五湖、三聚三散的陶朱公'},
    'jingke':    {'name': '荆轲', 'gender': 'male', 'era': 'xianqin', 'profession': 'xiake',
                  'temperament': 'haomai', 'fate': 'weicheng', 'epithet': '易水送别、图穷匕见的刺秦义士'},
    'quyuan':    {'name': '屈原', 'gender': 'male', 'era': 'xianqin', 'profession': 'wenren',
                  'temperament': 'gangzhi', 'fate': 'weicheng', 'epithet': '行吟泽畔、抱石投江的三闾大夫'},
    'shangyang': {'name': '商鞅', 'gender': 'male', 'era': 'xianqin', 'profession': 'mouchen',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '变法图强、终遭车裂的秦国相'},
    'goujian':   {'name': '勾践', 'gender': 'male', 'era': 'xianqin', 'profession': 'diwang',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '卧薪尝胆、终灭吴国的越王'},
    'luban':     {'name': '鲁班', 'gender': 'male', 'era': 'xianqin', 'profession': 'qiaoyi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '创斧凿墨斗、巧夺天工的百工之祖'},
    'mozi':      {'name': '墨子', 'gender': 'male', 'era': 'xianqin', 'profession': 'fangshi',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '兼爱非攻、止楚攻宋的墨家钜子'},
    'bianque':   {'name': '扁鹊', 'gender': 'male', 'era': 'xianqin', 'profession': 'qiaoyi',
                  'temperament': 'qingleng', 'fate': 'gouxian', 'epithet': '望闻问切、起死回生却遭嫉见害的神医'},
    'mengzi':    {'name': '孟子', 'gender': 'male', 'era': 'xianqin', 'profession': 'wenren',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '继孔子之后的儒家亚圣、民贵君轻'},
    'lianpo':    {'name': '廉颇', 'gender': 'male', 'era': 'xianqin', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '负荆请罪、将相和的主角之一'},
    'linxiangru': {'name': '蔺相如', 'gender': 'male', 'era': 'xianqin', 'profession': 'mouchen',
                   'temperament': 'qingleng', 'fate': 'qingshi', 'epithet': '完璧归赵、渑池之会,以智勇扬名'},
    'jiangziya': {'name': '姜子牙', 'gender': 'male', 'era': 'xianqin', 'profession': 'fangshi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '渭水垂钓遇文王、助周伐纣的开国军师'},
    'baiqi':     {'name': '白起', 'gender': 'male', 'era': 'xianqin', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'gouxian', 'epithet': '战神,长平之战后遭赐死的一代杀神'},
    'wuzixu':    {'name': '伍子胥', 'gender': 'male', 'era': 'xianqin', 'profession': 'xiake',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '过昭关一夜白头、鞭尸雪恨,后被夫差赐死投江'},

    'qinshihuang': {'name': '秦始皇', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                    'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '扫六合、书同文的千古一帝'},
    'xiangyu':   {'name': '项羽', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'weicheng', 'epithet': '力拔山兮气盖世、乌江自刎的西楚霸王'},
    'liubang':   {'name': '刘邦', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '斩白蛇起义、开创大汉的高祖皇帝'},
    'hanxin':    {'name': '韩信', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'yinren', 'fate': 'gouxian', 'epithet': '背水一战、成也萧何败也萧何的兵仙'},
    'zhangliang': {'name': '张良', 'gender': 'male', 'era': 'qinhan', 'profession': 'mouchen',
                   'temperament': 'qingleng', 'fate': 'guiyin', 'epithet': '运筹帷幄、功成身退的谋圣'},
    'wangzhaojun': {'name': '王昭君', 'gender': 'female', 'era': 'qinhan', 'profession': 'jiaren',
                    'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '出塞和亲、青冢留芳的四大美人之一'},
    'sima_qian': {'name': '司马迁', 'gender': 'male', 'era': 'qinhan', 'profession': 'wenren',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '忍辱负重、著《史记》的太史公'},
    'caiwenji':  {'name': '蔡文姬', 'gender': 'female', 'era': 'qinhan', 'profession': 'wenren',
                  'temperament': 'qingleng', 'fate': 'weicheng', 'epithet': '身陷匈奴、终归故土的乱世才女'},
    'huatuo':    {'name': '华佗', 'gender': 'male', 'era': 'qinhan', 'profession': 'qiaoyi',
                  'temperament': 'qingleng', 'fate': 'gouxian', 'epithet': '创五禽戏、发明麻沸散却遭忌见害的神医'},
    'zhangqian': {'name': '张骞', 'gender': 'male', 'era': 'qinhan', 'profession': 'xiake',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '凿空西域、开辟丝路的博望侯'},
    'banzhao':   {'name': '班昭', 'gender': 'female', 'era': 'qinhan', 'profession': 'wenren',
                  'temperament': 'qingleng', 'fate': 'qingshi', 'epithet': '续修《汉书》、学贯古今的一代女史'},
    'zhuowenjun': {'name': '卓文君', 'gender': 'female', 'era': 'qinhan', 'profession': 'wenren',
                   'temperament': 'fengliu', 'fate': 'qingshi', 'epithet': '当垆卖酒、与司马相如私奔的才女'},
    'cailun':    {'name': '蔡伦', 'gender': 'male', 'era': 'qinhan', 'profession': 'qiaoyi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '改进造纸术、泽被千秋的发明家'},
    'weiqing':   {'name': '卫青', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '奴隶出身官至大将军、七击匈奴战功赫赫'},
    'huoqubing': {'name': '霍去病', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'weicheng', 'epithet': '封狼居胥、一生未尝败绩,23岁英年早逝'},
    'yuji':      {'name': '虞姬', 'gender': 'female', 'era': 'qinhan', 'profession': 'jiaren',
                  'temperament': 'fengliu', 'fate': 'gouxian', 'epithet': '霸王别姬、乌江自刎前的绝唱红颜'},
    'xiaohe':    {'name': '萧何', 'gender': 'male', 'era': 'qinhan', 'profession': 'mouchen',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '汉初三杰之一、论功第一的开国丞相'},
    'chenping':  {'name': '陈平', 'gender': 'male', 'era': 'qinhan', 'profession': 'mouchen',
                  'temperament': 'fengliu', 'fate': 'qingshi', 'epithet': '六出奇计定天下的美男子谋士'},
    'suwu':      {'name': '苏武', 'gender': 'male', 'era': 'qinhan', 'profession': 'xiake',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '持节牧羊十九年、不改汉臣气节'},
    'chentang':  {'name': '陈汤', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '矫诏发兵远征郅支、奏出“虽远必诛”的西汉名将'},
    'liguang':   {'name': '李广', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'weicheng', 'epithet': '飞将军,箭术无双却终生难封、含恨自刎'},
    'zhouyafu':  {'name': '周亚夫', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '细柳营治军严明,后遭猜忌下狱绝食而死'},
    'banchao':   {'name': '班超', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '投笔从戎、平定西域三十六国'},
    'liuche':    {'name': '刘彻', 'gender': 'male', 'era': 'qinhan', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '北逐匈奴、独尊儒术,开创汉武盛世的一代雄主皇帝'},

    'caocao':    {'name': '曹操', 'gender': 'male', 'era': 'weijin', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '挟天子以令诸侯、横槊赋诗的魏武帝'},
    'zhugeliang': {'name': '诸葛亮', 'gender': 'male', 'era': 'weijin', 'profession': 'mouchen',
                   'temperament': 'yinren', 'fate': 'weicheng', 'epithet': '鞠躬尽瘁、七出祁山的武侯'},
    'guanyu':    {'name': '关羽', 'gender': 'male', 'era': 'weijin', 'profession': 'xiake',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '过五关斩六将、义薄云天的武圣'},
    'diaochan':  {'name': '貂蝉', 'gender': 'female', 'era': 'weijin', 'profession': 'jiaren',
                  'temperament': 'fengliu', 'fate': 'yuhua', 'epithet': '闭月之貌、周旋于董卓吕布之间的绝色'},
    'jikang':    {'name': '嵇康', 'gender': 'male', 'era': 'weijin', 'profession': 'wenren',
                  'temperament': 'kuangfang', 'fate': 'gouxian', 'epithet': '一曲《广陵散》绝响、竹林七贤之首'},
    'taoyuanming': {'name': '陶渊明', 'gender': 'male', 'era': 'weijin', 'profession': 'wenren',
                    'temperament': 'qingleng', 'fate': 'guiyin', 'epithet': '采菊东篱下、不为五斗米折腰的隐逸诗人'},
    'huamulan':  {'name': '花木兰', 'gender': 'female', 'era': 'weijin', 'profession': 'xiake',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '代父从军、征战沙场十二年的巾帼英雄'},
    'xunguan':   {'name': '荀灌', 'gender': 'female', 'era': 'weijin', 'profession': 'xiake',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '年少率勇士突围求援、解宛城之围的西晋奇女子'},
    'zuchongzhi': {'name': '祖冲之', 'gender': 'male', 'era': 'weijin', 'profession': 'qiaoyi',
                   'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '推算圆周率、名垂科技史的天文学家'},
    'xiedaoyun': {'name': '谢道韫', 'gender': 'female', 'era': 'weijin', 'profession': 'wenren',
                  'temperament': 'qingleng', 'fate': 'qingshi', 'epithet': '"未若柳絮因风起"、咏絮之才名动东晋的才女'},

    'lishimin':  {'name': '李世民', 'gender': 'male', 'era': 'suitang', 'profession': 'diwang',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '开创贞观之治的天可汗'},
    'weizheng':  {'name': '魏征', 'gender': 'male', 'era': 'suitang', 'profession': 'mouchen',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '犯颜直谏、终成一代名相的诤臣'},
    'libai':     {'name': '李白', 'gender': 'male', 'era': 'suitang', 'profession': 'wenren',
                  'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '斗酒诗百篇、飘然出世的诗仙'},
    'dufu':      {'name': '杜甫', 'gender': 'male', 'era': 'suitang', 'profession': 'wenren',
                  'temperament': 'yinren', 'fate': 'weicheng', 'epithet': '穷年忧黎元、笔底波澜的诗圣'},
    'baijuyi':   {'name': '白居易', 'gender': 'male', 'era': 'suitang', 'profession': 'wenren',
                  'temperament': 'fengliu', 'fate': 'qingshi', 'epithet': '一曲《长恨歌》传世、老妪能解的诗魔'},
    'wuzetian':  {'name': '武则天', 'gender': 'female', 'era': 'suitang', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '君临天下、独一无二的一代女帝'},
    'weihou':    {'name': '韦皇后', 'gender': 'female', 'era': 'suitang', 'profession': 'diwang',
                  'temperament': 'kuangfang', 'fate': 'gouxian', 'epithet': '权倾一时、最终败于唐隆政变的中宗皇后'},
    'yangyuhuan': {'name': '杨玉环', 'gender': 'female', 'era': 'suitang', 'profession': 'jiaren',
                   'temperament': 'fengliu', 'fate': 'gouxian', 'epithet': '回眸一笑百媚生、马嵬坡赐死的贵妃'},
    'xuanzang':  {'name': '玄奘', 'gender': 'male', 'era': 'suitang', 'profession': 'fangshi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '西行取经、九死不悔的三藏法师'},
    'shangguan_waner': {'name': '上官婉儿', 'gender': 'female', 'era': 'suitang', 'profession': 'mouchen',
                        'temperament': 'fengliu', 'fate': 'gouxian', 'epithet': '批阅奏章、权倾朝野却卷入政变的巾帼宰相'},

    'sushi':     {'name': '苏轼', 'gender': 'male', 'era': 'songyuan', 'profession': 'wenren',
                  'temperament': 'kuangfang', 'fate': 'guiyin', 'epithet': '一蓑烟雨任平生的东坡居士'},
    'yuefei':    {'name': '岳飞', 'gender': 'male', 'era': 'songyuan', 'profession': 'diwang',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '精忠报国、含冤风波亭的抗金名将'},
    'liqingzhao': {'name': '李清照', 'gender': 'female', 'era': 'songyuan', 'profession': 'wenren',
                   'temperament': 'qingleng', 'fate': 'weicheng', 'epithet': '人比黄花瘦、国破家亡的一代词宗'},
    'xinqiji':   {'name': '辛弃疾', 'gender': 'male', 'era': 'songyuan', 'profession': 'xiake',
                  'temperament': 'haomai', 'fate': 'weicheng', 'epithet': '醉里挑灯看剑、壮志难酬的稼轩居士'},
    'baozheng':  {'name': '包拯', 'gender': 'male', 'era': 'songyuan', 'profession': 'mouchen',
                  'temperament': 'gangzhi', 'fate': 'qingshi', 'epithet': '铁面无私、断案如神的包青天'},
    'shenkuo':   {'name': '沈括', 'gender': 'male', 'era': 'songyuan', 'profession': 'qiaoyi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '著《梦溪笔谈》的博物大家'},
    'guoshoujing': {'name': '郭守敬', 'gender': 'male', 'era': 'songyuan', 'profession': 'qiaoyi',
                    'temperament': 'qingleng', 'fate': 'qingshi', 'epithet': '制授时历、精通水利的一代天文大家'},
    'wentianxiang': {'name': '文天祥', 'gender': 'male', 'era': 'songyuan', 'profession': 'xiake',
                     'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '"留取丹心照汗青"、兵败被俘慷慨就义的忠烈'},
    'lianghongyu': {'name': '梁红玉', 'gender': 'female', 'era': 'songyuan', 'profession': 'diwang',
                    'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '击鼓退金兵的巾帼统帅'},

    'zhuyuanzhang': {'name': '朱元璋', 'gender': 'male', 'era': 'mingqing', 'profession': 'diwang',
                     'temperament': 'kuangfang', 'fate': 'qingshi', 'epithet': '布衣出身、开创大明的洪武帝'},
    'zhenghe':   {'name': '郑和', 'gender': 'male', 'era': 'mingqing', 'profession': 'xiake',
                  'temperament': 'haomai', 'fate': 'qingshi', 'epithet': '七下西洋、扬威异域的三宝太监'},
    'tangbohu':  {'name': '唐伯虎', 'gender': 'male', 'era': 'mingqing', 'profession': 'wenren',
                  'temperament': 'fengliu', 'fate': 'weicheng', 'epithet': '才华横溢却科场失意、放浪江南的风流才子'},
    'caoxueqin': {'name': '曹雪芹', 'gender': 'male', 'era': 'mingqing', 'profession': 'wenren',
                  'temperament': 'qingleng', 'fate': 'weicheng', 'epithet': '披阅十载、著《红楼梦》却穷困而终的旷世文豪'},
    'lishizhen': {'name': '李时珍', 'gender': 'male', 'era': 'mingqing', 'profession': 'qiaoyi',
                  'temperament': 'yinren', 'fate': 'qingshi', 'epithet': '遍尝百草、著《本草纲目》的药圣'},
    'qiujin':    {'name': '秋瑾', 'gender': 'female', 'era': 'mingqing', 'profession': 'xiake',
                  'temperament': 'gangzhi', 'fate': 'gouxian', 'epithet': '鉴湖女侠、慷慨就义的革命志士'},
    'zhangsanfeng': {'name': '张三丰', 'gender': 'male', 'era': 'mingqing', 'profession': 'fangshi',
                     'temperament': 'qingleng', 'fate': 'yuhua', 'epithet': '创太极、相传得道飞升的一代宗师'},
}

def pastlife_stage_index(path_len):
    return min(path_len, len(PASTLIFE_STAGES) - 1)

def pastlife_candidates(path, claimed_keys):
    pool = [k for k in PAST_LIFE_FIGURES if k not in claimed_keys]
    for dim, val in zip(PASTLIFE_DIMENSIONS, path):
        pool = [k for k in pool if PAST_LIFE_FIGURES[k][dim] == val]
    return pool

def pastlife_offer_options(path, claimed_keys):
    """按当前环节对应的维度,把剩余候选人分组,取人数最多的3组现场生成选项——
    保证每个选项选下去之后候选池必然非空,不会出现"选了才发现没人"的死路。"""
    dim = PASTLIFE_DIMENSIONS[len(path)]
    pool = pastlife_candidates(path, claimed_keys)
    groups = {}
    for k in pool:
        val = PAST_LIFE_FIGURES[k][dim]
        groups.setdefault(val, []).append(k)
    ranked = sorted(groups.keys(), key=lambda v: -len(groups[v]))[:3]
    random.shuffle(ranked)
    return [{'value': v, 'label': PASTLIFE_TAG_LABELS[dim][v], 'flavor': PASTLIFE_CHOICE_FLAVOR[dim][v],
             'count': len(groups[v])} for v in ranked]

# ── 宗门节日:后台选类型开启的轻量全宗活动,持续数日,到期自动收尾公布结果 ─────────────
# 没有后台定时任务,到期靠访问时惰性结算,跟天魔入侵/寿元系统同一个思路。
# 已实现的类型会在前台提供玩法并于落幕时结算，其余类型仍为公告占位。

FESTIVAL_DURATION_HOURS = 72
FESTIVAL_TYPES = {
    'kaishan':  {'label': '开山大典', 'desc': '追忆开宗立派之本,全宗共庆。'},
    'dabi':     {'label': '宗门大比', 'desc': '弟子登台比武,以武会友。'},
    'pet_show': {'label': '灵宠品鉴会', 'desc': '弟子携灵宠齐聚一堂,品评风采,不比战力。'},
    'danhui':   {'label': '炼丹大会', 'desc': '丹道峰弟子公开炼丹,以丹会友。'},
    'fabao':    {'label': '法宝鉴赏会', 'desc': '弟子携本命法宝赴会,互相鉴赏切磋。'},
    'zhongqiu': {'label': '中秋观月', 'desc': '合宗共赏皓月，入月宫饼坊试炼十味。'},
    'xinsui':   {'label': '新岁赐福', 'desc': '辞旧迎新,掌门为全宗弟子祈福。'},
    'jiangdao': {'label': '掌门讲道', 'desc': '掌门亲临,为弟子答疑解惑。'},
}
FESTIVAL_TYPES_IMPLEMENTED = {'pet_show', 'kaishan', 'zhongqiu', 'xinsui'}

# ── 开山大典:全宗共同推进典礼进度,每人限选一次职责,职责按当前武器专精给不同的一句史书文字 ──
# 进度只看"选了职责的人数",不看武器/境界高低——开山典礼讲究的是人人都到场,不是比谁更强。

KAISHAN_DUTIES = {
    'guard':   {'label': '执剑守山', 'desc': '镇守山门,迎候八方来客'},
    'welcome': {'label': '迎接新弟子', 'desc': '于山门下奉茶,引新弟子入宗'},
    'incense': {'label': '焚香祭祖', 'desc': '于宗祠焚香,追思开宗先辈'},
    'alchemy': {'label': '炼丹待客', 'desc': '于丹房外设炉,以丹香待客'},
    'forge':   {'label': '锻造宗门碑', 'desc': '协力錾刻新碑,刻录本届盛况'},
}

# {name} 替换为"姓名(称号)"；6种武器专精各给一句,不用{weapon}(典礼上未必带着装备的那件兵刃)。
KAISHAN_DUTY_LINES = {
    'guard': {
        'sword':   '{name}执剑守于山门,剑势森然,过往者皆屏息而行。',
        'blade':   '{name}横刀立于山门,刀锋不出鞘,却已慑退宵小。',
        'spear':   '{name}执枪守于山门,枪意如林,森然肃立。',
        'heavy':   '{name}负重兵镇于山门,如山岳般纹丝不动。',
        'ranged':  '{name}执弓巡守云台,箭矢遥指四方,一览山门内外。',
        'unarmed': '{name}赤手立于山门,拳意内敛,自有一股威压。',
    },
    'welcome': {
        'sword':   '{name}执剑立于道旁,含笑迎每一位新入门的弟子。',
        'blade':   '{name}倚刀而立,笑着为新弟子引路。',
        'spear':   '{name}按枪于侧,朗声唤新弟子近前。',
        'heavy':   '{name}卸下重兵,亲自搀扶远道而来的新弟子。',
        'ranged':  '{name}卸弓在肩,笑意盈盈地为新弟子指路。',
        'unarmed': '{name}拱手相迎,亲手为新入门弟子奉上第一盏灵茶。',
    },
    'incense': {
        'sword':   '{name}按剑肃立于宗祠前,焚香追思开宗先辈。',
        'blade':   '{name}横刀于膝,于宗祠中默然上香。',
        'spear':   '{name}执枪垂首,于列祖牌位前静立焚香。',
        'heavy':   '{name}放下重兵,躬身于宗祠焚香叩拜。',
        'ranged':  '{name}解弓置于一旁,于宗祠中恭敬上香。',
        'unarmed': '{name}净手焚香,于宗祠中默诵开宗祖训。',
    },
    'alchemy': {
        'sword':   '{name}剑不离身,守在丹炉旁为往来同门温一炉客丹。',
        'blade':   '{name}倚刀观炉,笑谈间已炼出满室丹香。',
        'spear':   '{name}枪杖当拄,守着丹炉与同门闲话家常。',
        'heavy':   '{name}以重兵压阵护炉,丹房内外皆是丹香。',
        'ranged':  '{name}卸弓歇于丹房外,与来客分享新炼的客丹。',
        'unarmed': '{name}亲手添炭看火,炼了满炉待客的丹药。',
    },
    'forge': {
        'sword':   '{name}以剑代锤,与同门合力錾刻宗门新碑。',
        'blade':   '{name}挥刀助锻,新碑上的纹路渐渐清晰。',
        'spear':   '{name}执枪压阵,守着炉火助锻宗门新碑。',
        'heavy':   '{name}抡起重兵亲自捶打,新碑轮廓渐渐显现。',
        'ranged':  '{name}在铸剑坊外远远望风护持,助锻新碑。',
        'unarmed': '{name}赤手抡锤,一锤一锤砸出宗门新碑的轮廓。',
    },
}
KAISHAN_LEADER_SUFFIX = '——作为宗门{title},{name}身先士卒,引众弟子入场。'  # join_seq==1时额外附一句

# 进度只看人数,依次解锁4个阶段;阈值刻意压低,小宗门(几个人)也能全部解锁,不是只有大宗门能玩。
KAISHAN_STAGES = [
    {'threshold': 1,  'label': '山门开启', 'text': '山门轰然洞开,典礼正式拉开序幕。'},
    {'threshold': 3,  'label': '焚香祭祖', 'text': '宗祠香烟袅袅,全宗共祭开宗先辈。'},
    {'threshold': 6,  'label': '掌门宣诰', 'text': '{leader}登台宣诰,宗门上下齐声相贺。'},
    {'threshold': 10, 'label': '宗门留影', 'text': '典礼落幕前,全宗共留一影,以志今朝。'},
]
KAISHAN_DUTY_REWARD = {'lingshi': 80, 'contribution': 15}
KAISHAN_LEADER_REWARD_MULT = 1.5  # 大师兄/大师姐(join_seq==1)引领一场,奖励多一半

# 领职责时额外有几率得一份灵材犒赏("努力就有机会"),这是每人各自独立的一次抽奖,
# 不跟其他弟子抢配额——抽中哪个品级就在该品级的上限内随机给一个数量。
KAISHAN_MATERIAL_CHANCE = 0.5
KAISHAN_MATERIAL_QTY_CAPS = {'low': 20, 'mid': 20, 'high': 20}  # 单次抽中该品级时,数量随机落在1~此值
KAISHAN_MATERIAL_TIER_WEIGHTS = {'low': 50, 'mid': 30, 'high': 20}  # 品级越高越稀罕,权重越低
# 上品材料稀有度高,每人整届大典(领职责的一次性附赠+之后反复抽奖全部加总)封顶只能拿这么多;
# 下品/中品不设总量封顶,抽多少算多少。封顶后上品就从候选池里退出,抽奖照样能抽,只是不会再出上品。
KAISHAN_HIGH_MATERIAL_CAP = 20

# 典礼期间(72小时)人人可反复抽奖,每小时限一次,不需要先领职责——概率/品级/数量上限
# 跟领职责那份奖励共用同一套参数,只是这里能一直抽到典礼结束。
KAISHAN_DRAW_COOLDOWN_SECONDS = 3600

def kaishan_duty_line(duty_key, weapon_style, name_label):
    tpl = KAISHAN_DUTY_LINES[duty_key].get(weapon_style, KAISHAN_DUTY_LINES[duty_key]['unarmed'])
    return tpl.format(name=name_label)

def kaishan_stage_index(participant_count):
    """返回当前已解锁到第几个阶段(0-based下标),一个都没解锁则为-1。"""
    idx = -1
    for i, stage in enumerate(KAISHAN_STAGES):
        if participant_count >= stage['threshold']:
            idx = i
    return idx

# ── 中秋观月:邀人赏月需对方回应才成局,也可独自前往;每人本届限赏月一次(发起或接受都算) ──
# 不强制对方必须是道侣/师徒/同峰——邀请名单开放给全宗任意在世弟子,那三种关系只是设计上
# 建议邀的对象,不是硬限制,免得关系空白的新人连这个节日都摸不到边。

ZHONGQIU_LOCATIONS = {
    'peak':  {'label': '峰顶', 'desc': '立于本命峰之巅,夜色四合,月色最先照见此处。'},
    'cloud': {'label': '云海', 'desc': '踏云而立,脚下云海翻涌如银浪。'},
    'cave':  {'label': '洞府', 'desc': '于自家洞府外摆一方矮几,静候月出。'},
    'hill':  {'label': '后山', 'desc': '寻一处后山僻静的老树下,月光筛过枝叶洒落一地。'},
}
ZHONGQIU_ACTIVITIES = {
    'drink': {'label': '对饮', 'desc': '温一壶桂花酿,与人对坐同饮'},
    'talk':  {'label': '论道', 'desc': '就着月色聊一段修行心得'},
    'gift':  {'label': '赠月饼', 'desc': '亲手做一份月饼相赠'},
    'catch': {'label': '互诉近况', 'desc': '说说近来各自的境遇'},
    'wish':  {'label': '许愿', 'desc': '对着月色许下一个心愿'},
}
ZHONGQIU_MOONCAKE_NAMES = ['桂花蜜月饼', '莲蓉双黄酥', '流心奶黄月', '五仁老式酥', '冰皮杏仁月']

# 月饼试炼：每层工序四选一，配方只存在服务端，玩家靠试错记住正确顺序。
ZHONGQIU_BAKE_ATTEMPTS_PER_HOUR = 3
ZHONGQIU_BAKE_RANK_REWARDS = {1: 1000, 2: 600, 3: 300}
ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS = 24  # 前三名出齐后进入一天收尾，不会延长原截止时间
ZHONGQIU_BAKE_STEPS = [
    [('筛粉成霜', '筛粉'), ('烘香灵粉', '烘粉'), ('凝露润粉', '润粉'), ('灵火炒粉', '炒粉')],
    [('桂蜜和面', '桂蜜'), ('月露和面', '月露'), ('灵油和面', '灵油'), ('云泉和面', '云泉')],
    [('文火炒馅', '炒馅'), ('玉杵捣馅', '捣馅'), ('冰雾凝馅', '凝馅'), ('剑气切馅', '切馅')],
    [('月印压模', '月印'), ('兔印压模', '兔印'), ('桂印压模', '桂印'), ('云纹压模', '云印')],
    [('灵火烘焙', '烘焙'), ('月光凝酥', '凝酥'), ('丹炉慢焙', '慢焙'), ('寒泉冰镇', '冰镇')],
]
ZHONGQIU_MOONCAKES = {
    'guihua':   {'name': '桂花蜜月饼',   'icon': '✿', 'recipe': [0, 0, 0, 2, 0], 'eat_text': '桂香在舌尖化开，心境也随之清明。'},
    'lianrong': {'name': '莲蓉双黄酥',   'icon': '◉', 'recipe': [2, 2, 1, 0, 2], 'eat_text': '莲蓉细润，咸蛋黄沙香浑厚。'},
    'liuxin':   {'name': '流心奶黄月',   'icon': '◐', 'recipe': [0, 1, 0, 1, 2], 'eat_text': '暖热的奶黄流心缓缓涌出。'},
    'wuren':    {'name': '五仁老式酥',   'icon': '✹', 'recipe': [3, 2, 3, 3, 0], 'eat_text': '坚果香脆，是一口扎实的旧时味道。'},
    'bingpi':   {'name': '冰皮杏仁月',   'icon': '❄', 'recipe': [2, 3, 2, 1, 3], 'eat_text': '冰皮清凉，杏仁的甜香沁入心脾。'},
    'zishu':    {'name': '紫薯流霞饼',   'icon': '✦', 'recipe': [2, 1, 1, 3, 1], 'eat_text': '紫薯甘香，断面仿佛藏着一缕流霞。'},
    'songzi':   {'name': '松子云腿月',   'icon': '▲', 'recipe': [3, 2, 0, 2, 2], 'eat_text': '松子与云腿咸香交织，余味悠长。'},
    'yutu':     {'name': '玉兔豆沙酥',   'icon': '☾', 'recipe': [0, 3, 1, 1, 0], 'eat_text': '豆沙绵密，玉兔印记也显得格外可爱。'},
    'moli':     {'name': '茉莉茶心月',   'icon': '❀', 'recipe': [1, 3, 3, 0, 1], 'eat_text': '茉莉茶香在甜味之后悠悠回甘。'},
    'xinghe':   {'name': '星河黑芝麻酥', 'icon': '★', 'recipe': [1, 0, 2, 3, 2], 'eat_text': '乌黑酥皮点着银糖，像把一小片星河吃下。'},
}

# 邀约成局那句的开场,按发起人当前武器专精各给一句,后面接互动本身的文字;
# 独自赏月复用同一份开场,只是接的是 ZHONGQIU_SOLO_FLAVORS。
ZHONGQIU_WEAPON_INTRO = {
    'sword':   '月光沿{name}的剑脊缓缓流下。',
    'blade':   '月色为{name}腰间的刀添了一层冷辉。',
    'spear':   '{name}倚枪而立,枪缨在月下轻轻摇晃。',
    'heavy':   '{name}卸下重兵靠在一旁,月光落满肩头。',
    'ranged':  '{name}的弓弦上凝了一层薄薄月霜。',
    'unarmed': '月光落在{name}摊开的掌心里,像是盛了一捧水。',
}
ZHONGQIU_LOCATION_FLAVORS = {
    'peak': ['在本命峰顶，满山云气都沉到脚下。', '峰巅风清，一轮满月仿佛触手可及。'],
    'cloud': ['云海在脚下缓缓涌动，被月光染成了银色。', '二人踏云而立，衣袖间都是清冽月辉。'],
    'cave': ['洞府外的矮几点着一盏小灯，四下安静得只闻虫鸣。', '洞府竹帘半卷，月光沿着石阶一寸寸漫进来。'],
    'hill': ['后山老桂树正盛，细碎花影落了满肩。', '后山少有人来，只有松涛与月色相伴。'],
}
ZHONGQIU_ACTIVITY_FLAVORS = {
    'drink': ['{partner}将温热的桂花酿推到{name}手边，二人碰杯时月影也跟着晃了一晃。', '{name}与{partner}轮流斤酒，谁都没去数今夜究竟喝了几杯。', '酒至微醺，{partner}笑着为{name}又添了半盏。'],
    'talk':  ['{partner}与{name}就着月色聊起这一年的修行，不知不觉已到月上中天。', '{name}先起了个话头，{partner}却由一式剑意一路讲到了天地大道。', '二人将近日所悟一一印证，到最后都若有所得。'],
    'gift':  ['{partner}将{gift_name}放在{name}手边，纸包上还沾着一粒桂花。', '{name}接过{partner}递来的{gift_name}，珍而重之地收进袖中。', '{partner}故作随意地送出{gift_name}，却忍不住偷看{name}的反应。'],
    'catch': ['{partner}与{name}互诉近来的境遇，月色听着，倒也不觉冷清。', '{name}讲起途中的一件趣事，惹得{partner}笑声惊起了枝头的鸟。', '二人把近来的欢喜与烦忧都说了出来，待离去时脚步都轻了些。'],
    'wish':  ['{partner}与{name}相对无言，各自对着月色许下一个心愿。', '{name}与{partner}同时闭上眼，都很有默契地没有追问对方许了什么。', '流星划过时，{partner}轻声说，愿{name}心中所求终能如愿。'],
}
ZHONGQIU_SOLO_FLAVORS = {
    'drink': ['{name}独酌一杯，月色便是今夜的酒友。', '{name}将第二只杯子也斟满，遥敬不在身边的故人。'],
    'talk':  ['{name}对着月亮自言自语了许久，权当与故人对坐论道。', '{name}将一道百思不得其解的难题说给月亮，竟在话音落下时想通了。'],
    'gift':  ['{name}做了一份{gift_name}，没有等到想等的人，便小心收了起来。', '{name}拆开{gift_name}，把最完整的一半留给了明日。'],
    'catch': ['{name}对着月色说了许多近来的心事，说完倒也轻松了不少。', '{name}在夜风里慢慢梳理这一年的得失，月亮始终安静地听着。'],
    'wish':  ['{name}对着月色许下一个心愿，不知今年能否应验。', '{name}将心愿写在纸上又折好，藏进了只有自己知道的地方。'],
}

ZHONGQIU_AFFINITY_GAIN = 4   # 双人赏月且彼此已有羁绊时,affinity各+4;没羁绊则跳过这一项,不硬造
ZHONGQIU_REWARD = {'lingshi': 30, 'mind_state': 3}  # 独自/双人都发,双人不因为多一个人而翻倍

def zhongqiu_moon_line(activity_key, weapon_style, name_label, partner_label=None, gift_name=None,
                        location_key='peak'):
    intro = ZHONGQIU_WEAPON_INTRO.get(weapon_style, ZHONGQIU_WEAPON_INTRO['unarmed']).format(name=name_label)
    pool = ZHONGQIU_ACTIVITY_FLAVORS if partner_label else ZHONGQIU_SOLO_FLAVORS
    location = random.choice(ZHONGQIU_LOCATION_FLAVORS.get(location_key, ZHONGQIU_LOCATION_FLAVORS['peak']))
    body = random.choice(pool[activity_key]).format(name=name_label, partner=partner_label, gift_name=gift_name)
    return f"{location}{intro}{body}"

def zhongqiu_gift_roll():
    rarity_key = random.choices(list(GIFT_RARITIES), weights=[55, 30, 12, 3])[0]
    trait_key = random.choice(list(GIFT_TRAITS))
    prefix = {'plain': '', 'fine': '精制·', 'rare': '灵韵·', 'unique': '天成·'}[rarity_key]
    name = prefix + random.choice(ZHONGQIU_MOONCAKE_NAMES)
    return {'name': name, 'rarity_key': rarity_key, 'trait_key': trait_key}

# ── 新岁赐福:许愿(存快照,下届许愿时回顾是否应验)+ 除岁活动(全宗共享进度,跟开山大典
# 同一个思路)+ 福签/红包(单向赠送,对方自选立即拆或留存)。奖励刻意都是小额/纪念性质,
# 不让"随机到强属性"这种事影响平衡——新岁赐福是个念想,不是刷装备的活动。

XINSUI_WISHES = {
    'realm':   {'label': '境界', 'desc': '愿修为更进一层'},
    'martial': {'label': '兵道', 'desc': '愿兵刃之道更加精深'},
    'romance': {'label': '情缘', 'desc': '愿觅得一段良缘'},
    'safety':  {'label': '平安', 'desc': '愿此后诸事顺遂,平安无虞'},
    'alchemy': {'label': '炼丹', 'desc': '愿丹道更进一步'},
    'pet':     {'label': '灵宠', 'desc': '愿与灵兽的缘分更深'},
}

XINSUI_WISH_BLESSINGS = {
    'realm':   ['愿你修为更进一层,道途坦荡无阻。', '愿你此去突破顺遂,不落人后。'],
    'martial': ['愿你弓开如满月,所念皆有归处。', '愿你兵刃之道更进一层,所向披靡。'],
    'romance': ['愿你此去觅得一段良缘,不负相逢。', '愿你情缘早定,岁岁相伴。'],
    'safety':  ['愿你此后诸事顺遂,平安无虞。', '愿你行走于九霄之间,始终有惊无险。'],
    'alchemy': ['愿你丹炉长明,炼出的每一炉都不负苦心。', '愿你丹道更进一步,妙手回春。'],
    'pet':     ['愿你与灵兽的缘分更深,相伴不离。', '愿你此后所遇灵兽,皆通灵性。'],
}
XINSUI_WISH_REWARD = {'lingshi': 50, 'mind_state': 5}  # 所有愿望统一给这份心意奖励,不因愿望种类拉开差距

XINSUI_ACTIVITIES = {
    'sweep':   {'label': '扫尘', 'desc': '清扫洞府内外,除旧迎新'},
    'lantern': {'label': '挂灯', 'desc': '于殿前廊下挂起一盏新灯'},
    'bell':    {'label': '鸣钟', 'desc': '登钟楼敲响辞旧岁的钟声'},
    'vigil':   {'label': '守岁', 'desc': '于殿中陪同门守岁到天明'},
}
XINSUI_ACTIVITY_LINES = {
    'sweep': {
        'sword':   '{name}以剑代帚,几缕剑气扫尽洞府积尘。',
        'blade':   '{name}倒转刀柄,三两下便清出满院清爽。',
        'spear':   '{name}执枪当帚,连角落的积尘也未放过。',
        'heavy':   '{name}挥动重兵,震落梁上积年的浮尘。',
        'ranged':  '{name}卸弓在肩,仔仔细细扫过廊下每一处。',
        'unarmed': '{name}挽起袖子,亲手清扫了洞府内外。',
    },
    'lantern': {
        'sword':   '{name}以剑挑灯,一盏新灯稳稳挂上殿前廊柱。',
        'blade':   '{name}单手悬灯,借着刀势轻轻一送便挂稳当。',
        'spear':   '{name}以枪杆撑灯,不必踩凳便挂上了高处。',
        'heavy':   '{name}以重兵为架,稳稳托起新灯挂上廊檐。',
        'ranged':  '{name}一箭穿绳,新灯便顺势挂上了枝头。',
        'unarmed': '{name}踮脚伸手,亲手将新灯挂上了殿前廊柱。',
    },
    'bell': {
        'sword':   '{name}拔剑轻叩钟身,钟声混着剑鸣悠悠传开。',
        'blade':   '{name}以刀背撞钟,一声辞旧的钟鸣震彻山门。',
        'spear':   '{name}持枪撞钟,钟声与枪势一同荡开涟漪。',
        'heavy':   '{name}抡起重兵撞钟,钟声浑厚,传出去老远。',
        'ranged':  '{name}张弓引弦,箭矢带动撞木敲响了辞岁钟。',
        'unarmed': '{name}赤手撞钟,钟声混着掌风一同散开。',
    },
    'vigil': {
        'sword':   '{name}按剑而坐,陪着同门守岁到了天明。',
        'blade':   '{name}横刀于膝,与同门围炉守岁一整夜。',
        'spear':   '{name}倚枪打盹,却也硬是撑到了天明。',
        'heavy':   '{name}卸下重兵靠墙而坐,陪同门守岁到破晓。',
        'ranged':  '{name}解弓置于膝上,与同门围炉说笑到天明。',
        'unarmed': '{name}盘膝而坐,陪着同门守岁,直至天光微亮。',
    },
}
XINSUI_STAGES = [
    {'threshold': 1,  'label': '扫尘完毕', 'text': '宗门内外焕然一新,除旧迎新的第一步已经完成。'},
    {'threshold': 3,  'label': '华灯初上', 'text': '一盏盏新灯次第亮起,照亮了整座山门。'},
    {'threshold': 6,  'label': '钟声辞岁', 'text': '辞旧岁的钟声回荡山谷,新岁将至。'},
    {'threshold': 10, 'label': '守岁天明', 'text': '同门围炉守岁至天明,新的一年正式到来。'},
]
XINSUI_ACTIVITY_REWARD = {'lingshi': 30, 'contribution': 10}

XINSUI_BLESSING_NAMES = ['雪纹福签', '朱红福笺', '缠枝锦囊', '烫金拜帖', '梅花小笺']
XINSUI_BLESSING_REWARD = {'lingshi': 20, 'mind_state': 2}  # 拆开时才发,留着不拆就先不生效

def xinsui_activity_line(activity_key, weapon_style, name_label):
    tpl = XINSUI_ACTIVITY_LINES[activity_key].get(weapon_style, XINSUI_ACTIVITY_LINES[activity_key]['unarmed'])
    return tpl.format(name=name_label)

def xinsui_stage_index(participant_count):
    idx = -1
    for i, stage in enumerate(XINSUI_STAGES):
        if participant_count >= stage['threshold']:
            idx = i
    return idx

def xinsui_blessing_roll():
    rarity_key = random.choices(list(GIFT_RARITIES), weights=[55, 30, 12, 3])[0]
    prefix = {'plain': '', 'fine': '精制·', 'rare': '灵韵·', 'unique': '天成·'}[rarity_key]
    name = prefix + random.choice(XINSUI_BLESSING_NAMES)
    return {'name': name, 'rarity_key': rarity_key}

# 许愿是否"应验":每种愿望对应一项可比较的角色状态,拿这一届的快照跟上一届的快照比——
# 没有上一届快照(第一次许愿)就没有回顾可言,不强行判定。
def xinsui_wish_snapshot(char, weapon_mastery_total, dan_quality_idx, has_companion, has_pet):
    return {
        'realm': char['realm_idx'],
        'martial': weapon_mastery_total,
        'romance': 1 if has_companion else 0,
        'safety': 1,
        'alchemy': dan_quality_idx,
        'pet': 1 if has_pet else 0,
    }

def xinsui_wish_fulfilled(wish_key, old_snapshot, new_snapshot):
    if not old_snapshot:
        return None  # 没有上一届记录,不判定
    old_val, new_val = old_snapshot.get(wish_key), new_snapshot.get(wish_key)
    if old_val is None or new_val is None:
        return None
    if wish_key == 'safety':
        return True  # 能活到回顾这一天,平安愿本身就算应验
    return new_val > old_val

# 灵宠品鉴会:6个类别里,前3个能从数据里直接算,后3个是纯主观的东西,没法硬算——
# 干脆随机给,别装作"经历最丰富"是个能量化的指标,那样反而假。
PET_SHOW_CATEGORIES = [
    {'key': 'rarest',     'label': '最稀有灵宠',   'mode': 'auto'},
    {'key': 'top_level',  'label': '培育最高等级', 'mode': 'auto'},
    {'key': 'longest',    'label': '最长陪伴时间', 'mode': 'auto'},
    {'key': 'appearance', 'label': '最特别外貌',   'mode': 'random'},
    {'key': 'history',    'label': '经历最丰富',   'mode': 'random'},
    {'key': 'popular',    'label': '最受欢迎灵宠', 'mode': 'random'},
]
FESTIVAL_PET_SHOW_REWARD = {'lingshi': 300, 'contribution': 40}  # 每个类别得主的奖励

# ── 炼丹(丹道峰专属):独立等阶成长线 + 具体丹方(起手自带/炼丹顿悟/花贡献购买三条获取路) ──
# 炼丹产出的是丹药"物品"(存入 character_pills),可以自己服用生效,也可以卖回宗门换贡献;
# 宗门商店里同类低阶丹药标价更高,自己炼制(哪怕算上失败的损耗)也比直接买划算。

ALCHEMIST_LEVEL_NAMES = ['药徒', '药师', '药宗', '丹师', '丹尊']
ALCHEMIST_MAX_LEVEL = len(ALCHEMIST_LEVEL_NAMES)
ALCHEMIST_LEVEL_UP_EXP = {1: 80, 2: 150, 3: 250, 4: 400}  # 达到下一级所需的当级经验
ALCHEMIST_EXP_ON_SUCCESS = 15
ALCHEMIST_EXP_ON_FAIL = 5
ALCHEMIST_SUCCESS_BONUS_PER_LEVEL = 3   # 每高一级,成功率 +3 个百分点
ALCHEMIST_MAX_SUCCESS_RATE = 95
RECIPE_DISCOVER_CHANCE = 0.08           # 炼丹成功后,顿悟出一个新丹方的概率
ALCHEMY_DIMINISH_AFTER = 5              # 每日前5炉炼丹经验全额,之后打折——不占体力后靠这个防止无限刷等阶
ALCHEMY_DIMINISH_MULT = 0.4
ALCHEMY_RECYCLE_EXP = 3                 # 丹药回炉能拿到的炼丹经验(回炉走这条,卖钱走 alchemy_sell)

def alchemist_level_name(level):
    level = max(1, min(level or 1, ALCHEMIST_MAX_LEVEL))
    return ALCHEMIST_LEVEL_NAMES[level - 1]

def alchemist_exp_to_next(level):
    return ALCHEMIST_LEVEL_UP_EXP.get(level)  # None 代表已满级

# 炼丹不再消耗体力,改为消耗材料(通用灵材阶梯 low/mid/high/top)+ 时间(见 ALCHEMY_DIMINISH_AFTER 软上限)
ALCHEMY_RECIPES = [
    {'key': 'peiyuan_dan',  'label': '培元丹', 'min_level': 1, 'base_success': 90, 'material_cost': {'low': 2},
     'reward': {'exp': 100}, 'unlock': 'starter', 'sell_price': 40},
    {'key': 'naqi_dan',     'label': '纳气丹', 'min_level': 1, 'base_success': 90, 'material_cost': {'low': 2},
     'reward': {'contribution': 40}, 'unlock': 'starter', 'sell_price': 20},
    {'key': 'ningshen_dan', 'label': '凝神丹', 'min_level': 2, 'base_success': 75, 'material_cost': {'low': 3},
     'reward': {'mind_state': 15}, 'unlock': 'discover', 'sell_price': 25},
    {'key': 'yangyuan_dan', 'label': '养元丹', 'min_level': 2, 'base_success': 75, 'material_cost': {'low': 3},
     'reward': {'physique': 3}, 'unlock': 'discover', 'sell_price': 30},
    {'key': 'dingxin_dan',  'label': '定心丹', 'min_level': 3, 'base_success': 60, 'material_cost': {'mid': 2},
     'reward': {'reputation': 10}, 'unlock': 'discover', 'sell_price': 50},
    {'key': 'juqi_dan',     'label': '聚气丹', 'min_level': 3, 'base_success': 60, 'material_cost': {'mid': 2},
     'reward': {'exp': 250}, 'unlock': 'discover', 'sell_price': 60},
    {'key': 'jiuzhuan_huihun_dan', 'label': '九转回魂丹', 'min_level': 4, 'base_success': 40, 'material_cost': {'mid': 3},
     'reward': {'lifespan_years': 30}, 'unlock': 'buy', 'buy_cost': 250, 'sell_price': 100},
    {'key': 'jipin_juling_dan', 'label': '极品聚灵丹', 'min_level': 4, 'base_success': 35, 'material_cost': {'mid': 3},
     'reward': {'exp': 400, 'contribution': 60}, 'unlock': 'discover', 'sell_price': 100},
    {'key': 'tianxin_dan',  'label': '天心丹', 'min_level': 5, 'base_success': 25, 'material_cost': {'high': 2},
     'reward': {'exp': 600, 'mind_state': 25, 'physique': 6}, 'unlock': 'buy', 'buy_cost': 400, 'sell_price': 200},
]

# ── 炼器(炼器峰专属):无固定配方,形态×五行属性×稀有度组合生成,独立等阶影响出货概率 ──
# 40种形态 × 5种属性(变异体质额外有概率炼出对应变异属性,比普通更强)× 5档稀有度,
# 组合生成而非逐条手写,炼器师等阶越高,炼出高稀有度法宝的概率越高。

FORGER_LEVEL_NAMES = ['铁匠', '巧匠', '器师', '器宗', '炼器尊者']
FORGER_MAX_LEVEL = len(FORGER_LEVEL_NAMES)
FORGER_LEVEL_UP_EXP = {1: 80, 2: 150, 3: 250, 4: 400}
FORGER_EXP_ON_SUCCESS = 15
FORGER_EXP_ON_FAIL = 5
FORGE_CORE_MATERIAL_COST = {'mid': 2}  # 炼化本命法宝品级不再耗体力,改耗通用灵材
FORGE_DIMINISH_AFTER = 5               # 每日前5次炼器经验全额,之后打折
FORGE_DIMINISH_MULT = 0.4

def forger_level_name(level):
    level = max(1, min(level or 1, FORGER_MAX_LEVEL))
    return FORGER_LEVEL_NAMES[level - 1]

def forger_exp_to_next(level):
    return FORGER_LEVEL_UP_EXP.get(level)

# ── 炼器尊者秘宝:炼器峰弟子炼到满级(炼器尊者)才能打造的第五件装备,终身绑定,不入行囊/
# 不可交易/不可替换——日常炼器只保底不拼强度,这是这个峰唯一"练到头就能拿到手"的强度回报 ──
FORGE_MASTER_TRINKET_MATERIAL_COST = {'high': 3}
FORGE_MASTER_TRINKET = {
    'key': 'xuanqiong_zunzhe_yin', 'label': '玄穹尊者印',
    'attack': 8, 'defense': 8, 'agility': 10, 'luck': 6,
    'desc': '炼器尊者以毕生技艺淬炼而成的印信,随身携带即通体温养。',
}

# FORGE_RARITIES 仅保留给交易行历史法宝挂单的展示函数用(炼器已改为炼化本命法宝品级,
# 不再产出这种法宝),故不再有 FORGE_FORMS/FORGER_RARITY_WEIGHTS 之类的新产出配置。
FORGE_RARITIES = [
    {'key': 'common',    'label': '凡品', 'base_value': 8,   'sell_price': 15},
    {'key': 'fine',      'label': '精良', 'base_value': 18,  'sell_price': 35},
    {'key': 'rare',      'label': '稀有', 'base_value': 35,  'sell_price': 70},
    {'key': 'epic',      'label': '史诗', 'base_value': 65,  'sell_price': 130},
    {'key': 'legendary', 'label': '传说', 'base_value': 120, 'sell_price': 250},
]
FORGE_RARITY_ORDER = [r['key'] for r in FORGE_RARITIES]

def rank_by_tier(tier):
    tier = max(0, min(tier or 0, len(RANKS) - 1))
    return RANKS[tier]

# ── 称号:按全服入门先后顺序生成"大师兄/二师姐"这类永久称号,与门内档位是两套正交系统 ──

_CN_DIGITS = '零一二三四五六七八九'

def _cn_num(n):
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return '十' + (_CN_DIGITS[n - 10] if n > 10 else '')
    if n < 100:
        tens, rem = divmod(n, 10)
        return _CN_DIGITS[tens] + '十' + (_CN_DIGITS[rem] if rem else '')
    return str(n)

def title_for(join_seq, gender, is_npc=False):
    if is_npc:
        return '长老'
    n = join_seq or 1
    suffix = '师兄' if gender != 'f' else '师姐'
    if n > 99:
        return f'{n}号{suffix}'
    prefix = '大' if n == 1 else _cn_num(n)
    return prefix + suffix

# ── 侠名:行侠令攒出来的进度,纯函数按数值区间返回称号,不落库、不占表,和上面的title_for同一个思路 ──

XIAXIA_TITLE_TIERS = [
    (0,   '初出江湖'), (10,  '古道热肠'), (30,  '侠名初显'), (60,  '义薄云天'), (100, '江湖游侠'),
]

XIAXIA_TITLE_UP_FLAVORS = [
    "{name}行走江湖,侠名传扬,人称「{title}」。",
    "{name}屡屡出手相助,口碑口耳相传,如今已被唤作「{title}」。",
    "茶楼酒肆间渐渐传起{name}的名号,都道一声「{title}」当之无愧。",
    "{name}的义举传到了坊间,往来行商都说宗门出了位「{title}」。",
    "{name}又办成一桩仗义之事,江湖上「{title}」的名声更响了几分。",
    "路人问起{name}是谁,同行的都应一句「那便是{title}啊」。",
    "{name}行侠仗义渐有章法,江湖朋友都开始以「{title}」相称。",
    "宗门外的说书人添了段新故事,主角正是如今人称「{title}」的{name}。",
]

def random_xiaxia_title_up_text(name, title):
    return random.choice(XIAXIA_TITLE_UP_FLAVORS).format(name=name, title=title)

def xiaxia_title(fame):
    label = XIAXIA_TITLE_TIERS[0][1]
    for threshold, name in XIAXIA_TITLE_TIERS:
        if (fame or 0) >= threshold:
            label = name
    return label

# ── 灵根:创角时按权重抽取,决定修炼速度倍率(乘算,天灵根/五灵根这类稀有档位天然占比低) ──

SPIRIT_ROOTS = {
    'heaven': {'label': '天灵根', 'mult': 3.0, 'weight': 3},
    'dual':   {'label': '双灵根', 'mult': 2.0, 'weight': 9},
    'tri':    {'label': '三灵根', 'mult': 1.6, 'weight': 18},
    'quad':   {'label': '四灵根', 'mult': 1.3, 'weight': 30},
    'penta':  {'label': '五灵根', 'mult': 1.0, 'weight': 40},
}
SPIRIT_ROOT_ORDER = ['heaven', 'dual', 'tri', 'quad', 'penta']  # 由稀有到常见,用于展示排序

SPIRIT_ROOT_CREATION_KEYS = ['dual', 'tri', 'quad', 'penta']  # 创角只抽这四档,天灵根开局不可得

def roll_spirit_root():
    keys = SPIRIT_ROOT_CREATION_KEYS
    weights = [SPIRIT_ROOTS[k]['weight'] for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]

def spirit_root_label(key):
    info = SPIRIT_ROOTS.get(key)
    return info['label'] if info else '未知灵根'

# ── 灵根蜕变:天灵根开局不可得,只能靠后期机缘从低档一步步蜕变而来,压低开局灵根带来的差距 ──

SPIRIT_ROOT_ASCENSION_ORDER = ['penta', 'quad', 'tri', 'dual', 'heaven']  # 由弱到强
SPIRIT_ROOT_ASCENSION_MIN_REALM = 9   # 元婴初期起才可能蜕变,契合"后期"的定位
SPIRIT_ROOT_ASCENSION_CHANCE = 0.001  # 每次打坐的触发概率,刻意压低,天灵根应是长期投入后的稀罕造化

def next_spirit_root(key):
    if key not in SPIRIT_ROOT_ASCENSION_ORDER:
        return None
    idx = SPIRIT_ROOT_ASCENSION_ORDER.index(key)
    return SPIRIT_ROOT_ASCENSION_ORDER[idx + 1] if idx + 1 < len(SPIRIT_ROOT_ASCENSION_ORDER) else None

# ── 灵根变异:创角时独立于档位抽取的极稀有标记,叠加在原档位之上,每元素3种变异共15种 ──
# 天生带有变异的人,炼器时有额外概率炼出对应变异属性法宝(比同稀有度的普通法宝更强),
# 变异本身也直接给打坐修为一点固定加成。

ELEMENTS = {
    'metal': {'label': '金', 'stat': 'physique'},
    'wood':  {'label': '木', 'stat': 'exp'},
    'water': {'label': '水', 'stat': 'mind_state'},
    'fire':  {'label': '火', 'stat': 'reputation'},
    'earth': {'label': '土', 'stat': 'contribution'},
}
ELEMENT_ORDER = ['metal', 'wood', 'water', 'fire', 'earth']

# ── 灵根属性:几灵根就带几个五行属性,后续武器按属性匹配才能装备——────────────────────
# 天灵根不绑定具体属性,视为五行皆通(全适配),不受武器属性限制。
SPIRIT_ROOT_ELEMENT_COUNT = {'heaven': 0, 'dual': 2, 'tri': 3, 'quad': 4, 'penta': 5}

def roll_spirit_root_elements(spirit_root):
    count = SPIRIT_ROOT_ELEMENT_COUNT.get(spirit_root, 0)
    if count <= 0:
        return []
    return random.sample(ELEMENT_ORDER, min(count, len(ELEMENT_ORDER)))

def next_spirit_root_elements(current_elements, new_spirit_root):
    """蜕变到新档位时属性随之凝练:从原有属性里随机保留新档位数量的子集。"""
    count = SPIRIT_ROOT_ELEMENT_COUNT.get(new_spirit_root, 0)
    if count <= 0:
        return []
    pool = current_elements or ELEMENT_ORDER
    return random.sample(pool, min(count, len(pool)))

def spirit_root_elements_label(spirit_root, elements_str):
    if spirit_root == 'heaven':
        return '五行皆通'
    if not elements_str:
        return '未知'
    return '·'.join(ELEMENTS[k]['label'] for k in elements_str.split(',') if k in ELEMENTS)

def spirit_root_can_use_element(spirit_root, elements_str, element_key):
    """武器是否可被该灵根使用:武器无属性则不限;天灵根五行皆通;其余灵根需属性在自身范围内。"""
    if not element_key:
        return True
    if spirit_root == 'heaven':
        return True
    return element_key in (elements_str or '').split(',')

ELEMENT_MUTATIONS = {
    'yunte':      {'label': '陨铁',   'element': 'metal'},
    'hanying':    {'label': '寒英',   'element': 'metal'},
    'chensha':    {'label': '辰砂',   'element': 'metal'},
    'youhuang':   {'label': '幽篁',   'element': 'wood'},
    'longxuemu':  {'label': '龙血木', 'element': 'wood'},
    'liulteng':   {'label': '琉璃藤', 'element': 'wood'},
    'xuanbing':   {'label': '玄冰',   'element': 'water'},
    'youquan':    {'label': '幽泉',   'element': 'water'},
    'wangchuan':  {'label': '忘川',   'element': 'water'},
    'yehuo':      {'label': '业火',   'element': 'fire'},
    'chiyan':     {'label': '赤炎',   'element': 'fire'},
    'youmingyan': {'label': '幽冥焰', 'element': 'fire'},
    'xirang':     {'label': '息壤',   'element': 'earth'},
    'xuanhuang':  {'label': '玄黄',   'element': 'earth'},
    'panshi':     {'label': '磐石',   'element': 'earth'},
}
ELEMENT_MUTATION_ROLL_CHANCE = 0.02   # 创角时天生变异的概率,与灵根档位抽取相互独立
ELEMENT_MUTATION_EXP_BONUS_PCT = 5    # 变异体质固定给的打坐修为加成
def roll_element_mutation():
    return random.choice(list(ELEMENT_MUTATIONS.keys())) if random.random() < ELEMENT_MUTATION_ROLL_CHANCE else None

def element_mutation_label(key):
    info = ELEMENT_MUTATIONS.get(key)
    return info['label'] if info else None

# ── 血脉(创角即得,先天)/ 传承(后天机缘,仅无血脉者有资格获得) ──────────────────────
# 二者共用同一套"小成→大成"曲线,只是获得时机不同(天生 vs 后天),保证最终强度对等。
# 血脉创角即可见(不再暗藏觉醒);修为达到 TALENT_AWAKEN_REALM 后,加成自动从小成升级到大成。

TALENT_AWAKEN_REALM = 6  # 金丹初期,约等于内门弟子门槛

# 全部统一为修炼(exp)加成,不再区分"修为向/贡献向"两条线——16门传承血脉数值完全对等,
# 挑哪个纯看名字和喜好,不用再纠结"选了贡献向以后修为会不会亏"。
TALENTS = {
    'qilin':     {'label': '麒麟血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'xuangui':   {'label': '玄龟血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'zhuque':    {'label': '朱雀血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'xuanming':  {'label': '玄冥血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'qinglong':  {'label': '青龙血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'baihu':     {'label': '白虎血脉',   'source': 'bloodline',   'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'sword':     {'label': '上古剑修传承', 'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'pill':      {'label': '丹鼎宗传承',   'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'array':     {'label': '阵道传承',     'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'beast':     {'label': '御兽传承',     'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'forge':     {'label': '玄穹炼器传承', 'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'void':      {'label': '太虚道统传承', 'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'trail':     {'label': '星阑秘境传承', 'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'social':    {'label': '沧澜广缘传承', 'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'talisman':  {'label': '玄符传承',     'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
    'tempest':   {'label': '御风传承',     'source': 'inheritance', 'stat': 'exp', 'minor_pct': 5, 'major_pct': 25},
}
BLOODLINE_KEYS = [k for k, v in TALENTS.items() if v['source'] == 'bloodline']
INHERITANCE_KEYS = [k for k, v in TALENTS.items() if v['source'] == 'inheritance']
BLOODLINE_ROLL_CHANCE = 0.08     # 创角时获得血脉的概率
INHERITANCE_ROLL_CHANCE = 0.05   # 无血脉者,每次打坐修炼获得传承的概率

def roll_bloodline():
    return random.choice(BLOODLINE_KEYS) if random.random() < BLOODLINE_ROLL_CHANCE else None

def talent_stage_pct(talent_key, realm_idx):
    """返回 (加成百分比, 影响的数值类型, 是否已到大成)。"""
    t = TALENTS.get(talent_key)
    if not t:
        return 0, None, False
    is_major = realm_idx >= TALENT_AWAKEN_REALM
    return (t['major_pct'] if is_major else t['minor_pct']), t['stat'], is_major

# ── 仙骨:每种全宗仅1枚,机缘触发,谁先摸到算谁的,加成一步到位不分阶段 ──────────────────
# bonus 是战斗属性固定加成,跟丹药/化神品质那套 DAN_QUALITIES/SHEN_QUALITIES['bonus']同一格式,
# 由 _player_combat_profile 汇总进 attack/defense——仙骨全宗独一份,量级压过极品化神(35/35)。

IMMORTAL_BONES = {
    'dihuang':   {'label': '帝皇骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'longxiang': {'label': '龙象骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'taiyi':     {'label': '太一金骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'qilin':     {'label': '麒麟骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'kunpeng':   {'label': '鲲鹏骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'zhulong':   {'label': '烛龙骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'hundun':    {'label': '混沌骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'jinwu':     {'label': '金乌骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'jiuyou':    {'label': '九幽冥骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'taichu':    {'label': '太初仙骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'xingchen':  {'label': '星辰道骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'xuanhuang': {'label': '玄黄神骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'hongmeng':  {'label': '鸿蒙仙骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'baihu':     {'label': '白虎煞骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'xuanwu':    {'label': '玄武圣骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'zhuque':    {'label': '朱雀炎骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'qinglong':  {'label': '青龙苍骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'riyue':     {'label': '日月玄骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'tianming':  {'label': '天命道骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
    'wuxiang':   {'label': '无相仙骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                  'bonus': {'attack': 40, 'defense': 40}},
}
IMMORTAL_BONE_MEDITATION_KEYS = list(IMMORTAL_BONES.keys())  # 打坐洗髓奇遇只从常规仙骨池里抽
IMMORTAL_BONE_ROLL_CHANCE = 0.01  # 尚无仙骨者,每次打坐修炼触发"洗髓奇遇"的概率

# 九幽渊限定仙骨:另开5枚并入同一个 IMMORTAL_BONES 池子(数值对等,共用 immortal_bone_key 字段、
# 全宗仅一份、已有仙骨者不会再掉),但只从九幽渊击败妖物掉落,不会被上面的打坐随机抽中——
# 靠 IMMORTAL_BONE_MEDITATION_KEYS 把候选范围锁在常规仙骨池,九幽的5枚绕开那条随机线。
JIUYOU_BONE_KEYS = ['yuanshen', 'shihun', 'wuguang', 'nichen', 'anyuan']
IMMORTAL_BONES.update({
    'yuanshen': {'label': '渊神骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                 'bonus': {'attack': 40, 'defense': 40}},
    'shihun':   {'label': '噬魂古骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                 'bonus': {'attack': 40, 'defense': 40}},
    'wuguang':  {'label': '无光神骨', 'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                 'bonus': {'attack': 40, 'defense': 40}},
    'nichen':   {'label': '溺沉骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                 'bonus': {'attack': 40, 'defense': 40}},
    'anyuan':   {'label': '暗渊骨',   'exp_bonus_pct': 50, 'breakthrough_bonus_pct': 15,
                 'bonus': {'attack': 40, 'defense': 40}},
})
JIUYOU_BONE_DROP_CHANCE = 0.10  # 九幽渊击败妖物时的掉落概率,比打坐洗髓奇遇(1%)高不少,毕竟门槛更高

# ── 宗门纪年 / 寿元:流速1小时=1年,寿元上限随大境界提升,但涨幅逐级收敛不搞爆炸增长 ──

SECONDS_PER_YEAR = 3600
STARTING_AGE_YEARS = 16  # 入宗弟子并非婴孩,创角时寿数已从16岁起算,寿元同步扣除这部分

# 角色年龄增长速度是宗门纪年的2倍(半小时=1岁),只影响"人老得多快",纪年/山门辨灵石冷却
# 仍按 SECONDS_PER_YEAR(1小时=1年)走,两者故意分开、不共用一个常量。
AGE_SECONDS_PER_YEAR = SECONDS_PER_YEAR // 2

LIFESPAN_BY_MAJOR = {
    # 金丹之后(元婴起)寿元上限也跟着修为需求同步拉长约1.5倍,不然经验曲线拉长后
    # 寿元反而不够用,后期境界会被寿元卡住走不完。
    '炼气': 80, '筑基': 130, '金丹': 240, '元婴': 390,
    '化神': 510, '合体': 630, '大乘': 750,
}
ASCEND_ON_EXPIRY_MAJOR_IDX = 5  # major_idx>=5(合体/大乘)寿元耗尽记作"渡劫飞升",以下记作"寿终正寝"

# 寿元剩余不到这个比例时提醒一次(按当前大境界寿元上限算,不是固定年数)——新人容易压根不知道
# 寿元在流逝,直到寿终正寝才后知后觉;每个大境界只提醒一次(见 lifespan_warned_realm_idx),
# 突破到下一大境界寿元上限跟着涨,会在新的上限下重新计算、可以再提醒一次
LIFESPAN_WARNING_PCT = 20

# 剩余寿元不到这个固定年数时(不看境界、不看比例),追加一次"大限将至"的最终提醒——
# 此时任何境界都已经很紧迫了,除了私信,还要写进大事记公开示警,让宗内人都知道谁命不久矣。
LIFESPAN_FINAL_WARNING_YEARS = 10

# ── 山门辨灵石:入宗前的小仪式,不是每次点开都能测,要等下一次"年"才能再试一次;
# 第1次60%起,每次+10%,第5次(60+10*4=100%)必过——保底之外全靠手动点,不做惰性自动结算,
# 图的就是"叩石辨灵"这个动作本身的仪式感。冷却直接复用 SECONDS_PER_YEAR,不再另开一套节奏。
SPIRIT_TEST_BASE_CHANCE_PCT = 60
SPIRIT_TEST_STEP_PCT = 10
SPIRIT_TEST_COOLDOWN_SECONDS = SECONDS_PER_YEAR

def spirit_test_chance_pct(attempt_number):
    """attempt_number 从1开始计。"""
    return min(100, SPIRIT_TEST_BASE_CHANCE_PCT + (attempt_number - 1) * SPIRIT_TEST_STEP_PCT)

SPIRIT_TEST_FAIL_FLAVORS = [
    '灵石微光一闪,旋即黯淡——你与山门的缘分还差一线。',
    '辨灵石纹丝不动,似是尚未认可你的根骨。',
    '石面浮起一层薄雾,片刻后又归于沉寂。',
    '你屏息凝神叩石而问,石中灵光只是微微一颤,未能感应。',
]
SPIRIT_TEST_SUCCESS_TEXT = '辨灵石骤然大亮,清光笼罩全身——这份灵根,配入我九霄仙门!'

# ── 主动飞升:大乘圆满起可主动举行仪式;单次尝试失败不致命,可以随时再来——
# 但天劫不会一直等着,大乘圆满起 DACHENG_ASCEND_DEADLINE_SECONDS 内必须渡劫成功,
# 到期前 DACHENG_ASCEND_WARNING_SECONDS 会提醒一次,到期仍未飞升则天劫反噬、身陨道消。

ASCENSION_STAMINA_COST = 40
ASCENSION_BASE_CHANCE = 0.6
ASCENSION_ASSIST_CONTRIBUTION_COST = 100
ASCENSION_ASSIST_BONUS_PCT = 15
ASCENSION_FAIL_MIND_PENALTY = 8
ASCENSION_FLAVOR = '身外九霄雷云翻涌,身内一点道心澄明如镜,尘世牵绊尽数放下——此身当渡此劫,飞升而去。'

DACHENG_ASCEND_DEADLINE_SECONDS = 12 * 3600
DACHENG_ASCEND_WARNING_SECONDS = 2 * 3600
DACHENG_REACHED_FLAVOR = ('你终至大乘圆满,然而九霄之上天劫已在云端积蓄——此劫不会一直等你,'
                           f'{DACHENG_ASCEND_DEADLINE_SECONDS // 3600}小时内必须渡劫飞升,否则天劫反噬,身陨道消。')
DACHENG_WARNING_FLAVOR = (f'距天劫降临只剩{DACHENG_ASCEND_WARNING_SECONDS // 3600}小时,'
                           '再不渡劫飞升,便要身陨道消——速速前往举行飞升仪式。')
DACHENG_DEADLINE_DEATH_LABEL = '大乘圆满迟迟未能渡劫,天劫反噬,身陨道消'

# ── 天庭神职:飞升成功后五选一拜授一方神位,全宗唯一、先到先得,纯展示性质——
# 角色已经退场不再参与任何数值系统,这里只给飞升这个终点添一份仪式感与谈资,不给任何加成。
# 仿"每位各掌一方权柄"的众神格局(不写具体对应哪位神仙,只给神位称谓与执掌之权,留想象空间)。
CELESTIAL_OFFICES = {
    'lei_ting':    {'label': '雷霆之主', 'desc': '掌九天雷霆号令,凡结怨深重、恶贯满盈者,一道天雷可判生死'},
    'gang_feng':   {'label': '罡风之主', 'desc': '掌八荒罡风流转,商旅出行、战阵交锋皆受其势左右'},
    'yun_yu':      {'label': '云雨之主', 'desc': '掌行云布雨、旱涝丰歉之权,农桑一年收成尽系于此'},
    'xing_chen':   {'label': '星辰之主', 'desc': '掌万千星辰运转轨迹,推演天时,预示国运兴衰'},
    'canghai':     {'label': '沧溟之主', 'desc': '掌四海波涛潮汐,行船渡海者皆需祈其庇佑方保平安'},
    'shou_ming':   {'label': '寿命之主', 'desc': '掌众生寿数簿籍,一笔一划间定生死大限'},
    'yinyuan':     {'label': '姻缘之主', 'desc': '掌天下姻缘牵系,红线一系,便是一世纠葛与相守'},
    'wugu':        {'label': '五谷之主', 'desc': '掌五谷生长收成之权,饥荒丰年皆出其手'},
    'yiyao':       {'label': '医药之主', 'desc': '掌天地药理灵方,起死回生、驱病消灾皆赖其能'},
    'binggo':      {'label': '兵戈之主', 'desc': '掌人间兵戈胜负,两军对垒之际暗中拨弄天平'},
    'wenyun':      {'label': '文运之主', 'desc': '掌天下文脉气运,状元及第、才名远播皆系于此'},
    'gongqiao':    {'label': '工巧之主', 'desc': '掌百工技艺造化之权,能工巧匠皆受其点化启悟'},
    'caibo':       {'label': '财帛之主', 'desc': '掌天下财帛流转,商贾兴衰、贫富更迭尽在掌中'},
    'shengsi':     {'label': '生死簿录', 'desc': '掌轮回生死簿录,一入其册,来世去处已然注定'},
    'mengjing':    {'label': '梦境之主', 'desc': '掌众生梦境幻象,善梦示警、恶梦惩戒皆由此出'},
    'yinlu':       {'label': '音律之主', 'desc': '掌天地音律清浊,一曲可安魂定魄,一音可摄心夺志'},
    'shanchuan':   {'label': '山川之主', 'desc': '掌天下名山大川气脉,镇压地脉,调和四方风水'},
    'caomu':       {'label': '草木之主', 'desc': '掌万物草木荣枯之权,春生夏长秋收冬藏皆循其令'},
    'fengyun':     {'label': '风云之主', 'desc': '掌天象风云变幻莫测,阴晴雨雪皆随其意而转'},
    'xiangrui':    {'label': '祥瑞之主', 'desc': '掌人间祥瑞谶纬,麒麟现世、瑞气东来皆其所示'},
    'lingmai':     {'label': '灵脉之主', 'desc': '掌天地灵气流转均衡,修士修行资粮皆源于此'},
    'huode':       {'label': '火德之主', 'desc': '掌天地烈焰之权,炼丹铸器、焚净秽浊皆赖其力'},
    'bingxue':     {'label': '冰雪之主', 'desc': '掌四时霜雪寒暑更迭,极寒之地皆受其辖制'},
    'pantao':      {'label': '蟠桃之主', 'desc': '掌仙家蟠桃胜境,三千年一熟的仙果尽归其守'},
    'yaopu':       {'label': '药圃之主', 'desc': '掌天庭百草药圃,珍稀灵药皆由此悉心培育'},
    'tianji':      {'label': '天机之主', 'desc': '掌天机推演变数,窥探过去未来,趋吉避凶之道尽藏其中'},
    'danding':     {'label': '丹鼎之主', 'desc': '掌天庭丹炉鼎器,九转金丹皆出其手炼就'},
    'fabao':       {'label': '法宝之主', 'desc': '掌天庭法宝库藏,历代仙人遗留至宝皆归其管辖'},
    'xuntian':     {'label': '巡天之主', 'desc': '掌三界巡查之权,善恶功过皆逃不过其耳目'},
    'tianguan':    {'label': '天关之主', 'desc': '掌天地关隘要道,往来仙凡皆需其验放通行'},
    'duhua':       {'label': '度化之主', 'desc': '掌新证道者引渡之责,初入仙班者皆赖其指引前路'},
    'liyue':       {'label': '礼乐之主', 'desc': '掌天庭礼仪典章,朝会宴飨秩序皆由其厘定'},
    'xingcha':     {'label': '星槎之主', 'desc': '掌星槎渡引往来,沟通仙凡两界舟楫之权'},
    'xianghuo':    {'label': '香火之主', 'desc': '掌人间香火供奉,善信祈愿皆经其手上达天听'},
    'dongtian':    {'label': '洞天之主', 'desc': '掌诸洞天福地气数,修行秩序、灵脉分配皆归其理'},
    'gongguo':     {'label': '功过之主', 'desc': '掌仙班功过簿录,赏罚升黜皆据此而定夺'},
    'lingqin':     {'label': '灵禽之主', 'desc': '掌天庭灵禽异兽,珍奇神兽豢养驯化皆系于此'},
    'qiju':        {'label': '起居之主', 'desc': '掌天庭典籍起居注,古今仙闻秘录皆藏其阁不朽'},
    'xuanqiong':   {'label': '玄穹之主', 'desc': '掌玄穹星图布局之权,天象变幻皆由其推演定势'},
    'tianhe':      {'label': '天河之主', 'desc': '掌天河水道漕运,沟通银河两岸舟车皆赖其力'},
}

# ── 天魔入侵:后台手动开启的限时全宗活动,全体角色共享同一头目血量;开启后自带冷却,
# 防止连开,活动本身不设倒计时定时任务,而是每次访问/攻击时惰性检查是否已超时——
# 跟寿元/继任那套 lifespan_tick() 的"没有后台定时任务,靠请求顺手结算"是同一个思路。

INVASION_COOLDOWN_DAYS = 3
INVASION_DURATION_HOURS = 24
INVASION_ATTACK_DAILY_LIMIT = 30  # 讨魔用独立的每日次数,不占日常体力,活动期间够打但不是无限

# 四阶段按 boss_hp/boss_hp_max 比例推进,不是固定时长,打得快就进得快:
# 0 天魔降临(100%~70%,普通阶段) → 1 魔将结阵(70%~40%,三只魔将分摊伤害,可选目标)
# → 2 魔念暴走(40%~10%,攻击有几率反噬心境,防御减轻) → 3 众生破魔(10%~0,伤害加成,冲刺收尾)
INVASION_PHASE_LABELS = ['天魔降临', '魔将结阵', '魔念暴走', '众生破魔']
INVASION_PHASE_1_HP_RATIO = 0.70
INVASION_PHASE_2_HP_RATIO = 0.40
INVASION_PHASE_3_HP_RATIO = 0.10

# 魔将:hp_ratio 相对 boss_hp_max 计算各自血量;存活数量决定对天魔本体造成的伤害折扣——
# 逼着玩家先集火魔将,而不是無视魔将猛攻本体(那样效率反而更低)。
INVASION_ADDS = [
    {'key': 'guard',  'label': '护法魔将', 'hp_ratio': 0.15},
    {'key': 'devour', 'label': '噬灵魔将', 'hp_ratio': 0.13},
    {'key': 'blood',  'label': '血煞魔将', 'hp_ratio': 0.13},
]
INVASION_ADD_SHIELD_MULT = {3: 0.30, 2: 0.60, 1: 0.80, 0: 1.0}  # 存活数→对天魔本体的伤害倍率

INVASION_BACKLASH_CHANCE = 0.25
INVASION_BACKLASH_MIND_PENALTY = 4
INVASION_BACKLASH_DEFENSE_MITIGATION_PER_POINT = 0.02
INVASION_BACKLASH_MITIGATION_CAP_PCT = 50

INVASION_EXECUTE_DAMAGE_MULT = 1.5  # 众生破魔阶段伤害加成

# 个人奖励按"当次入侵内累计有效伤害"分档,档位越高边际收益越低(软上限,不是硬顶),
# 而不是只分"伤害最高的人/其余人"两档——多打多得,但不会让顶尖输出无限拉开差距。
INVASION_REWARD_TIERS = [
    {'min_damage': 1,     'label': '参战', 'reward': {'lingshi': 100,  'contribution': 15}},
    {'min_damage': 300,   'label': '积极', 'reward': {'lingshi': 500,  'contribution': 70}},
    {'min_damage': 1200,  'label': '核心', 'reward': {'lingshi': 1400, 'contribution': 200}},
    {'min_damage': 3000,  'label': '卓越', 'reward': {'lingshi': 2600, 'contribution': 380}},
    {'min_damage': 6000,  'label': '超凡', 'reward': {'lingshi': 4000, 'contribution': 580}},
    {'min_damage': 12000, 'label': '弑魔', 'reward': {'lingshi': 6500, 'contribution': 900}},
]
INVASION_EXPIRE_REWARD_MULT = 0.4  # 超时未剿灭,只按分档奖励的4折结算,以示与成功剿灭的差别

# 单次入侵累计伤害达"弑魔"档且天魔被成功剿灭(非拖到过期),额外获赠全宗顶级饰品——
# 不设全宗唯一限制,打到就有,每次入侵都能再拿一件(可叠加持有多件),用来体现"越打越强"而非一次性收藏。
INVASION_ACCESSORY_MIN_DAMAGE = 12000
INVASION_ACCESSORY_KEY = 'invasion_tianmo_pendant'
INVASION_ACCESSORY_TEMPLATE = {'slot': 'accessory', 'key': INVASION_ACCESSORY_KEY, 'label': '天魔戮魂珮',
                                'attack': 20, 'defense': 20, 'agility': 24, 'luck': 15}
EQUIPMENT_TEMPLATES_BY_KEY[INVASION_ACCESSORY_KEY] = dict(INVASION_ACCESSORY_TEMPLATE, zone='invasion')

INVASION_ATTACK_FLAVORS = [
    '你一剑劈开煞气,狠狠斩在天魔身上!',
    '灵光爆发,你全力一击,天魔发出一声低吼!',
    '你踏空而起,一记重击砸在天魔要害!',
    '你气机激荡,招式尽数打在天魔身上!',
    '你毫不留手,一击贯穿天魔护体煞气!',
]
INVASION_ADD_ATTACK_FLAVORS = [
    '你转而攻向{label},逼其现出破绽!',
    '你集中全力猛攻{label}!',
    '你一招击中{label}要害!',
]
INVASION_BACKLASH_FLAVOR = '魔念骤然反噬,你心神一荡'
INVASION_DEFEATED_FLAVOR = '天魔一声惨嗥,煞气尽散,轰然溃灭!'
INVASION_EXPIRED_FLAVOR = '天魔见势不妙,冲霄而去,消失在云端。'

def lifespan_cap(realm_idx, bonus_years=0):
    major = realm_by_index(realm_idx)['major']
    return LIFESPAN_BY_MAJOR.get(major, 80) + (bonus_years or 0)

def game_year_of(ts, epoch_ts):
    return max(0, (ts - epoch_ts) // SECONDS_PER_YEAR)

# ── 体力/心境/体魄/声望:宗门日常养成的四个新资源 ──────────────────────────────────
# 体力:懒惰结算,每小时回复,委托/探索消耗;心境:0-100三档,影响打坐收益与突破率
# 体魄:累加成长值;声望:累加不可消费,门内晋升的第三道门槛(realm/contribution/reputation 三者都够才能考核)

STAMINA_CAP = 120
STAMINA_REGEN_PER_HOUR = 9  # 原6点/小时×1.5,0→120满血约13.3小时
STAMINA_OVERFLOW_CAP = 180  # 突破/大型剧情等一次性奖励可临时冲到这个上限,但自然回复仍以 STAMINA_CAP 为准

# ── 天地精华:预留的付费货币,消耗口(体力加速/秘境额外场次)已实装,充值入口暂未真正开放,
# 现在所有人余额都是0,只能靠管理员后台手动发放测试;价位/数量档位先按常见小游戏梯度定好。
TIANDI_JINGHUA_TIERS = [
    {'price_cny': 10,  'amount': 100},
    {'price_cny': 30,  'amount': 320},
    {'price_cny': 100, 'amount': 1100},
    {'price_cny': 200, 'amount': 2300},
    {'price_cny': 500, 'amount': 6000},
]
TIANDI_STAMINA_BOOST_COST = 10
TIANDI_STAMINA_BOOST_AMOUNT = 30
TIANDI_STAMINA_BOOST_DAILY_CAP = 5  # 一天最多用精华加速5次
TIANDI_MYSTIC_EXTRA_SESSION_COST = 5
TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP = 2  # 一天最多花精华买2场额外秘境,不能无限堆

# 充值/商城按钮点下去不会真扣钱发货,但要让这一下点得有仪式感,不是干巴巴一句"未开放"——
# 随机弹一句,气氛到了、钱包毫发无伤。
TIANDI_FAKE_BUY_FLAVORS = [
    '叮——柜台后的账房先生冲你眨了眨眼：「心意本尊收到了,可惜银库还没开张,权当练练手感!」',
    '一道金光在指尖一闪而过,随后灰飞烟灭——你分明感受到了一瞬的富贵,虽然什么都没发生。',
    '「滴」一声清脆的音效过后是一片寂静……原来只是听个响。',
    '掌门在云端探出头：「充值口子还没接通呢道友,不过这个『剁手』的手感练得不错!」',
    '你豪气地按下了购买键,天地为之一静,随后照常运转,分毫未损。',
    '账本上悄悄多划了一笔,又悄悄划掉——这单,记在了"以后再说"那一页。',
]

# 充值彩蛋:每个档位每天限点1次(不管中不中,点了就今日变灰),10%概率真的到账10点天地精华——
# 金额固定不看档位,毕竟是彩蛋不是真充值,给多给少全看运气不看你充的哪一档。
TIANDI_EASTER_EGG_CHANCE = 0.10
TIANDI_EASTER_EGG_AMOUNT = 10
TIANDI_EASTER_EGG_FLAVORS = [
    '咦?账房先生的手抖了一下——天地精华真的到账了+10,快去看看,别声张。',
    '「叮」这次的声响不太一样……低头一看,天地精华真的多了10点,像是谁手滑了。',
    '掌门探出头,一脸茫然：「这……这单好像真走账了?算了,就当赏你的,别外传。」',
    '一道金光稳稳落进你的储物袋——这次不是幻觉,天地精华+10,是真的。',
]

MIND_STATE_BANDS = [
    {'min': 81, 'max': 100, 'label': '心如止水', 'exp_pct': 10, 'breakthrough_pct': 5},
    {'min': 21, 'max': 80,  'label': '心境平和', 'exp_pct': 0,  'breakthrough_pct': 0},
    {'min': 0,  'max': 20,  'label': '心有杂念', 'exp_pct': -10, 'breakthrough_pct': -5},
]

def mind_state_band(value):
    value = max(0, min(value or 0, 100))
    for band in MIND_STATE_BANDS:
        if band['min'] <= value <= band['max']:
            return band
    return MIND_STATE_BANDS[1]

# ── 闭关:懒惰结算的挂机选项,收益低于主动打坐但无需在线盯着,期间锁定打坐/委托/探索 ──────
# 基础值同样要乘 BASE_EXP_REALM_MULT(按结算时角色所在大境界),否则后期闭关收益会被打坐甩开

RETREAT_DURATION_HOURS = [1, 4, 8]
RETREAT_EXP_BASE_PER_HOUR = 210     # =CULTIVATE_BASE_EXP_AVG(21)×10,相当于每小时10次打坐的产出;只吃灵根倍率+境界倍率,不叠加打坐方式/心境等百分比加成
RETREAT_CONTRIBUTION_PER_HOUR = 10
RETREAT_EARLY_EXIT_MULT = 0.5       # 提前出关,按已闭关时长打五折结算

# 闭关和打坐共用同一个每日40次封顶计数器;计入额度时按本次闭关实际到手的修为,
# 除以"打坐均值约30点/次"折算成等效点击次数(见 app.py 的 _retreat_diminish_units),
# 而不是按小时数走固定倍率——否则洞府灵气加成会让闭关产出更高却仍按老倍率计费,变相绕开衰减。

# ── 洞府:灵石经济独立于贡献,双向可兑但不对等;品阶推进靠灵石+灵材,不靠抽象经验值 ─────────
# 灵气→闭关产出加成(封顶25%) / 清净→心魔触发概率降低(封顶25pp) / 稳固→突破体力消耗降低,
# 三者都只给已有系统(闭关/心魔/突破)加成,不重新实现一遍,避免和护法/护脉丹的加成叠罗汉。

CONTRIBUTION_TO_LINGSHI_RATE = 10   # 10贡献→1灵石,宗门功勋变现,好换
LINGSHI_TO_CONTRIBUTION_RATE = 20   # 20灵石→1贡献,钱买不到功勋,故意不划算
LINGSHI_EXCHANGE_DAILY_LIMIT = 3    # 灵石→贡献 这个方向每日限次,防止用它绕过晋升门槛的严肃性

MATERIAL_TIERS = ['low', 'mid', 'high', 'top']
MATERIAL_LABELS = {'low': '灵材·下品', 'mid': '灵材·中品', 'high': '灵材·上品', 'top': '灵材·极品'}
MATERIAL_LABELS.update(MYSTIC_MATERIAL_LABELS)
MATERIAL_LABELS.update(BREAKTHROUGH_MATERIAL_LABELS)
MATERIAL_LABELS.update({pastlife_talent_shard_key(tk): f"{t['label']}碎片" for tk, t in TALENTS.items()})

# ── 资源回收:装备分解/材料合成/材料兑换/宗门捐献,给持续产出的材料装备找个出口 ──────────

MATERIAL_SYNTHESIZE_RATIO = 5  # 低阶材料×5 合成 高阶材料×1,沿 MATERIAL_TIERS 阶梯逐级向上

# 秘境地区特产材料囤多了用不完,限额兑换成通用灵材/灵石;每种每日限购次数见 SHOP_DAILY_LIMIT
MATERIAL_EXCHANGE_ITEMS = [
    {'key': 'trade_qinglan_root', 'label': '药谷灵根须兑灵材',
     'material_cost': {'qinglan_root': 5}, 'material': {'key': 'low', 'qty': 2}},
    {'key': 'trade_chiyan_ore', 'label': '赤炎矿核兑灵材',
     'material_cost': {'chiyan_ore': 5}, 'material': {'key': 'mid', 'qty': 2}},
    {'key': 'trade_guxiu_rune', 'label': '古修器纹片兑灵材',
     'material_cost': {'guxiu_rune': 5}, 'material': {'key': 'high', 'qty': 2}},
    {'key': 'trade_zangjian_shard', 'label': '断剑之魄兑灵材',
     'material_cost': {'zangjian_shard': 5}, 'material': {'key': 'top', 'qty': 2}},
    {'key': 'trade_jiuyou_crystal', 'label': '幽渊魂晶兑灵材',
     'material_cost': {'jiuyou_crystal': 4}, 'material': {'key': 'top', 'qty': 2}},
    {'key': 'trade_mystic_dust', 'label': '秘境雾尘兑灵石',
     'material_cost': {'mystic_dust': 5}, 'reward': {'lingshi': 80}},
]
MATERIAL_EXCHANGE_ITEMS_BY_KEY = {i['key']: i for i in MATERIAL_EXCHANGE_ITEMS}

DONATE_RATES = {'low': 1, 'mid': 5, 'high': 25, 'top': 125}  # 宗门捐献:每单位通用灵材兑多少贡献

# realm_req 对应 REALMS 下标;rank_req 是 rank_tier 最低要求(见 RANKS,5=长老,6=掌门),None=不要求
CAVE_TIERS = [
    {'key': 'outer_chamber', 'label': '外门石室', 'realm_req': 1,  'lingshi_cost': 0,    'materials': {},
     'rank_req': None, 'cave_qi': 0,  'cave_purity': 20, 'cave_stability': 20},
    {'key': 'inner_cave',    'label': '内门洞府', 'realm_req': 3,  'lingshi_cost': 200,  'materials': {'low': 5},
     'rank_req': None, 'cave_qi': 10, 'cave_purity': 30, 'cave_stability': 40},
    {'key': 'mentee_manor',  'label': '真传灵府', 'realm_req': 6,  'lingshi_cost': 800,  'materials': {'low': 10, 'mid': 5},
     'rank_req': None, 'cave_qi': 25, 'cave_purity': 45, 'cave_stability': 60},
    {'key': 'elder_mansion', 'label': '长老仙府', 'realm_req': 9,  'lingshi_cost': 2000, 'materials': {'mid': 15, 'high': 5},
     'rank_req': 5, 'cave_qi': 45, 'cave_purity': 60, 'cave_stability': 80},
    {'key': 'peak_lodge',    'label': '峰主道场', 'realm_req': 12, 'lingshi_cost': 4500, 'materials': {'high': 15, 'top': 3},
     'rank_req': 6, 'cave_qi': 70, 'cave_purity': 75, 'cave_stability': 100},
    {'key': 'grotto_heaven', 'label': '洞天福地', 'realm_req': 15, 'lingshi_cost': 8000, 'materials': {'top': 10},
     'rank_req': None, 'cave_qi': 100, 'cave_purity': 90, 'cave_stability': 120},
]
CAVE_MAX_TIER_INDEX = len(CAVE_TIERS) - 1

def cave_tier_info(idx):
    idx = max(0, min(idx or 0, CAVE_MAX_TIER_INDEX))
    return CAVE_TIERS[idx]

# 灵气/清净取值区间→效果,同一套6档区间复用两次(灵气给闭关加成,清净给心魔触发降幅)
CAVE_EFFECT_BANDS = [
    (0, 19, 0), (20, 39, 5), (40, 69, 10), (70, 99, 15), (100, 139, 20), (140, 10 ** 9, 25),
]

def cave_band_pct(value):
    value = value or 0
    for lo, hi, pct in CAVE_EFFECT_BANDS:
        if lo <= value <= hi:
            return pct
    return 0

CAVE_STABILITY_STAMINA_DISCOUNT = [(0, 39, 0), (40, 79, 2), (80, 119, 4), (120, 10 ** 9, 6)]

def cave_stability_stamina_discount(value):
    value = value or 0
    for lo, hi, discount in CAVE_STABILITY_STAMINA_DISCOUNT:
        if lo <= value <= hi:
            return discount
    return 0

# ── 聚灵阵:灵气的主要来源,日耗走懒惰结算,灵石不够会自动停转降级,不会倒欠 ──────────────

CAVE_ARRAY_LEVELS = [
    {'label': '引灵阵',     'cave_qi': 10, 'lingshi_cost': 100,  'materials': {'low': 3},            'daily_upkeep': 0},
    {'label': '小聚灵阵',   'cave_qi': 20, 'lingshi_cost': 300,  'materials': {'low': 8},             'daily_upkeep': 5},
    {'label': '四象聚灵阵', 'cave_qi': 35, 'lingshi_cost': 800,  'materials': {'low': 10, 'mid': 5},  'daily_upkeep': 12},
    {'label': '周天聚灵阵', 'cave_qi': 50, 'lingshi_cost': 2000, 'materials': {'mid': 15, 'high': 5}, 'daily_upkeep': 25},
    {'label': '九霄汇灵大阵', 'cave_qi': 70, 'lingshi_cost': 5000, 'materials': {'high': 10, 'top': 3}, 'daily_upkeep': 50,
     'min_cave_tier': 5},
]
CAVE_ARRAY_MAX_LEVEL = len(CAVE_ARRAY_LEVELS)

def cave_array_info(level):
    level = max(0, min(level or 0, CAVE_ARRAY_MAX_LEVEL))
    return CAVE_ARRAY_LEVELS[level - 1] if level > 0 else None

# ── 药圃:长周期挂机,唯一的灵材来源(秘境上线前),不做偷菜 ─────────────────────────────

CAVE_GARDEN_CROPS = [
    {'key': 'lingcao',   'label': '普通灵草', 'hours': 2,  'lingshi_range': (15, 25),
     'material_drop': {'low': 0.10}, 'min_cave_tier': 0},
    {'key': 'zhuji_yao', 'label': '筑基药材', 'hours': 8,  'lingshi_range': (60, 90),
     'material_drop': {'low': 0.20}, 'min_cave_tier': 1},
    {'key': 'zhenxi_yao','label': '珍稀灵药', 'hours': 24, 'lingshi_range': (200, 300),
     'material_drop': {'low': 0.05, 'mid': 0.30}, 'min_cave_tier': 2},
    {'key': 'tiancai',   'label': '天材地宝', 'hours': 72, 'lingshi_range': (600, 900),
     'material_drop': {'high': 0.50, 'top': 0.10}, 'min_cave_tier': 3},
]
CAVE_GARDEN_CROPS_BY_KEY = {c['key']: c for c in CAVE_GARDEN_CROPS}

# ── 风景/特征/装饰:纯展示层,不给任何数值加成,只是让每座洞府长得不一样 ─────────────────

CAVE_SCENERY_OPTIONS = ['背山面水', '古树参天', '云雾缭绕', '灵溪潺潺', '奇石嶙峋', '竹林掩映', '悬崖飞瀑', '幽谷芝兰']

def roll_cave_scenery():
    return random.choice(CAVE_SCENERY_OPTIONS)

CAVE_NAME_PREFIXES = {
    '背山面水': ['枕山', '观澜', '抱朴'], '古树参天': ['栖木', '听松', '扶桑'],
    '云雾缭绕': ['栖云', '隐雾', '流霞'], '灵溪潺潺': ['听溪', '濯泉', '临水'],
    '奇石嶙峋': ['叠嶂', '石隐', '抱岳'], '竹林掩映': ['幽篁', '听竹', '翠微'],
    '悬崖飞瀑': ['听瀑', '悬泉', '飞白'], '幽谷芝兰': ['芝兰', '空谷', '兰隐'],
}
CAVE_NAME_SUFFIXES = ['洞', '府', '别院', '小筑', '精舍', '道场', '玄居', '云台', '真庐', '静室']

def roll_cave_name(scenery):
    return random.choice(CAVE_NAME_PREFIXES.get(scenery, ['清虚', '自在'])) + random.choice(CAVE_NAME_SUFFIXES)

CAVE_TRAITS = {
    'spring':  {'label': '灵泉', 'decoration_key': 'spring_eye',   'decoration_label': '灵泉眼',
                'lingshi_cost': 200, 'materials': {'low': 3}},
    'geofire': {'label': '地火', 'decoration_key': 'geofire_stove','decoration_label': '地火暖炉',
                'lingshi_cost': 200, 'materials': {'low': 3}},
    'marrow':  {'label': '石髓', 'decoration_key': 'marrow_pillar','decoration_label': '石髓晶柱',
                'lingshi_cost': 300, 'materials': {'mid': 3}},
    'tree':    {'label': '古树', 'decoration_key': 'ancient_tree', 'decoration_label': '悟道古树',
                'lingshi_cost': 300, 'materials': {'mid': 3}},
    'vein':    {'label': '灵脉', 'decoration_key': 'vein_pattern', 'decoration_label': '小型灵脉阵纹',
                'lingshi_cost': 500, 'materials': {'high': 3}},
    'spirit':  {'label': '器灵', 'decoration_key': 'artifact_soul','decoration_label': '器灵神龛',
                'lingshi_cost': 1000, 'materials': {'top': 2}},
}
CAVE_TRAIT_ROLL_CHANCE = 0.15  # 品阶推进(内门洞府起)时,小概率额外触发一个特征

def roll_cave_trait(existing_keys):
    candidates = [k for k in CAVE_TRAITS if k not in existing_keys]
    if not candidates or random.random() >= CAVE_TRAIT_ROLL_CHANCE:
        return None
    return random.choice(candidates)

# ── 打坐三方式:静心吐纳(稳)/引气入体(快但小概率乱气)/深度入定(慢但小概率顿悟) ──────

CULTIVATE_METHODS = {
    'steady':     {'label': '静心吐纳', 'exp_mult': 1.0, 'mind_delta': 2,  'mishap_pct': 0,
                    'cooldown_mult': 1.0, 'epiphany_pct': 0},
    'aggressive': {'label': '引气入体', 'exp_mult': 1.3, 'mind_delta': 0,  'mishap_pct': 0.1,
                    'cooldown_mult': 1.0, 'epiphany_pct': 0},
    'deep':       {'label': '深度入定', 'exp_mult': 1.6, 'mind_delta': 1,  'mishap_pct': 0,
                    'cooldown_mult': 2.0, 'epiphany_pct': 0.15},
}
CULTIVATE_METHOD_ORDER = ['steady', 'aggressive', 'deep']

# ── 每日基础任务:每天随机抽3项,完成任意2项算"当日修行完成",第3项是锦上添花 ───────────
# action 标记这条任务挂靠在哪个已有动作上,由 app.py 的 mark_daily_task() 在对应路由里触发

DAILY_TASKS = [
    {'key': 'morning_meditate', 'label': '晨间吐纳', 'desc': '打坐修炼一次', 'action': 'cultivate',
     'reward': {'exp': 15, 'mind_state': 2}},
    {'key': 'sect_checkin', 'label': '宗门点卯', 'desc': '登录查看宗门动态', 'action': 'checkin',
     'reward': {'contribution': 5, 'reputation': 1}},
    {'key': 'tidy_room', 'label': '整理静室', 'desc': '休整一次', 'action': 'rest',
     'reward': {'stamina': 10}},
    {'key': 'greet_peer', 'label': '请教同门', 'desc': '向一名同门弟子请教', 'action': 'interact',
     'reward': {'reputation': 3}},
    {'key': 'review_method', 'label': '温习功法', 'desc': '打坐修炼一次', 'action': 'cultivate',
     'reward': {'exp': 10, 'physique': 1}},
    {'key': 'patrol', 'label': '山门巡查', 'desc': '完成一次宗门委托', 'action': 'commission',
     'reward': {'contribution': 10, 'reputation': 2}},
    {'key': 'rest_mind', 'label': '调息养神', 'desc': '休整一次', 'action': 'rest',
     'reward': {'mind_state': 4}},
    {'key': 'field_work', 'label': '灵田照料', 'desc': '完成一次宗门委托', 'action': 'commission',
     'reward': {'contribution': 10, 'physique': 1}},
]
DAILY_TASKS_SHOWN = 3
DAILY_TASKS_REQUIRED = 2
DAILY_BONUS_REWARD = {'contribution': 14, 'stamina': 10, 'exp': 20}       # 完成2项
DAILY_FULL_BONUS_REWARD = {'contribution': 7, 'reputation': 2}          # 额外完成第3项

# ── 宗门委托:消耗体力换贡献/声望/体魄,每日前3次全额,之后减半,避免无限刷 ────────────

COMMISSIONS = [
    {'key': 'library', 'label': '清扫藏经阁', 'desc': '整理典籍,静心之余亦有薄酬。',
     'stamina_cost': 10, 'reward': {'contribution': 10, 'mind_state': 1}},
    {'key': 'field',   'label': '照料灵田',   'desc': '侍弄灵田草木,磨炼耐性与体魄。',
     'stamina_cost': 15, 'reward': {'contribution': 14, 'physique': 1}},
    {'key': 'patrol',  'label': '山门巡逻',   'desc': '巡视山门内外,以防宵小。',
     'stamina_cost': 20, 'reward': {'contribution': 18, 'reputation': 2}},
    {'key': 'escort',  'label': '护送药材',   'desc': '押送药材下山,略有风险。',
     'stamina_cost': 25, 'reward': {'contribution': 21, 'reputation': 2}},
    {'key': 'alchemy', 'label': '协助炼丹',   'desc': '为执事打下手炼丹,偶有心得。',
     'stamina_cost': 20, 'reward': {'contribution': 15, 'mind_state': 1}},
    {'key': 'mentor',  'label': '指导新弟子', 'desc': '指点外门新人,积累宗门声望。',
     'stamina_cost': 15, 'reward': {'contribution': 7, 'reputation': 4}},
]
COMMISSION_DIMINISH_AFTER = 3
COMMISSION_DIMINISH_MULT = 0.5
COMMISSION_DIMINISH_STAMINA_MULT = 2  # 超过每日前3次后,不仅收益减半,体力消耗也翻倍,双重劝退无脑刷委托

# ── 打工:懒惰结算的挂机选项,专赚灵石(委托赚的是贡献)——跟闭关同一套模型:
# 选个差事+时长,期间锁定打坐/委托/秘境/闭关等一切其他行动,出工后一次性结算灵石。
# 不吃灵根/境界倍率(灵石跟修为是两套经济,不该被高境界玩家进一步拉开差距)。
LABOR_JOBS = [
    {'key': 'porter',  'label': '码头搬货', 'desc': '在山下渡口帮商船卸货,力气活但来钱快。', 'lingshi_per_hour': 10},
    {'key': 'errand',  'label': '镇上跑腿', 'desc': '替铺子送信送货,走街串巷。', 'lingshi_per_hour': 12},
    {'key': 'stall',   'label': '摆摊叫卖', 'desc': '在集市支个摊子,赚点辛苦钱。', 'lingshi_per_hour': 14},
    {'key': 'scribe',  'label': '代写书信', 'desc': '识文断字,替不识字的乡邻代笔。', 'lingshi_per_hour': 15},
    {'key': 'harvest', 'label': '农户帮工', 'desc': '农忙时节下地帮忙,管饭还给工钱。', 'lingshi_per_hour': 18},
    {'key': 'guard',   'label': '镖行护院', 'desc': '给镖局押货站台,略有风险,工钱也高。', 'lingshi_per_hour': 22},
]
LABOR_DURATION_HOURS = [1, 4, 8]   # 提前收工按实际做工时长照单全付,不额外打折
LABOR_DIMINISH_AFTER_HOURS = 8     # 每日累计打工超过8小时(一个工作日)后,超出部分收益减半
LABOR_DIMINISH_HARD_CAP_EXTRA_HOURS = 3  # 超时之后最多再给3小时的折扣收益,过了硬顶当天彻底不再产出
LABOR_DIMINISH_MULT = 0.5

# ── 行侠令:独立任务板,不靠委托的"刷"也不靠游历/秘境的概率触发,随时能点,但每日限次 ──────
# 带成功率(不藏概率,直接告诉玩家),失败也有安慰奖励(侠名值),不是惩罚性质

XIAXIA_DAILY_CAP = 3

XIAXIA_TASKS = [
    {'key': 'escort_caravan', 'label': '搭救遇袭商旅', 'desc': '山道商队遭劫,货主呼救。',
     'stamina_cost': 15, 'success_rate': 85, 'reward': {'reputation': 3, 'xiaxia_fame': 4},
     'fail_reward': {'xiaxia_fame': 1}},
    {'key': 'stop_forced_marriage', 'label': '拆散强抢民女', 'desc': '恶霸强抢民女,乡邻敢怒不敢言。',
     'stamina_cost': 20, 'success_rate': 70, 'reward': {'reputation': 5, 'xiaxia_fame': 6},
     'fail_reward': {'xiaxia_fame': 2}},
    {'key': 'catch_repeat_offender', 'label': '缉拿采花惯犯', 'desc': '数镇皆有女子失踪,疑与此人有关。',
     'stamina_cost': 25, 'success_rate': 60, 'reward': {'reputation': 6, 'xiaxia_fame': 8},
     'fail_reward': {'xiaxia_fame': 2}},
    {'key': 'escort_elder', 'label': '护送孤老还乡', 'desc': '老者流落异乡,盼归故里。',
     'stamina_cost': 12, 'success_rate': 90, 'reward': {'reputation': 2, 'xiaxia_fame': 3},
     'fail_reward': {'xiaxia_fame': 1}},
    {'key': 'mediate_feud', 'label': '平息械斗纠纷', 'desc': '两村因水源结怨,已聚众械斗。',
     'stamina_cost': 18, 'success_rate': 75, 'reward': {'reputation': 4, 'xiaxia_fame': 5},
     'fail_reward': {'xiaxia_fame': 1}},
    {'key': 'recover_heirloom', 'label': '追回失窃传家宝', 'desc': '盗贼夜入宅院,窃走传家之物。',
     'stamina_cost': 16, 'success_rate': 80, 'reward': {'reputation': 3, 'xiaxia_fame': 4},
     'fail_reward': {'xiaxia_fame': 1}},
    {'key': 'clear_bandits', 'label': '镇压山匪劫道', 'desc': '山匪盘踞要道,商旅苦不堪言。',
     'stamina_cost': 28, 'success_rate': 60, 'reward': {'reputation': 6, 'xiaxia_fame': 8},
     'fail_reward': {'xiaxia_fame': 2}},
    {'key': 'confront_tyrant', 'label': '仗剑除霸', 'desc': '恶霸鱼肉乡里多年,无人敢制。',
     'stamina_cost': 22, 'success_rate': 65, 'reward': {'reputation': 5, 'xiaxia_fame': 7},
     'fail_reward': {'xiaxia_fame': 2}},
]
XIAXIA_TASKS_BY_KEY = {t['key']: t for t in XIAXIA_TASKS}

# ── 行侠奇遇:挂靠在行侠令任务结算后的一次性剧情事件,每个角色每条只会遇到一次 ─────────────
# 走向=一次性奖励+永久小标签(flavor向,不解锁后续玩法),两个选项都给正向奖励不设代价,
# 避免"选了但灵石不够"这类边界情况——首批15条验证体验,通过后再扩到100+条。

STORY_ENCOUNTER_TRIGGER_CHANCE = 0.20

STORY_ENCOUNTERS = [
    {'key': 'found_gold', 'title': '拾金不昧', 'text': '你在路边拾得一袋沉甸甸的银两，失主尚未察觉遗失。',
     'choices': [
         {'key': 'return', 'label': '寻访失主归还', 'reward': {'reputation': 3, 'xiaxia_fame': 2}, 'tag': '拾金不昧'},
         {'key': 'keep', 'label': '收入囊中', 'reward': {'lingshi': 40}, 'tag': '顺手牵羊'},
     ]},
    {'key': 'free_clinic', 'title': '妙手仁心', 'text': '一位病重老者无钱医治，你身上正好带着丹药。',
     'choices': [
         {'key': 'give', 'label': '赠药救人', 'reward': {'xiaxia_fame': 3, 'reputation': 1}, 'tag': '妙手仁心'},
         {'key': 'keep', 'label': '留药自用', 'reward': {'lingshi': 20}, 'tag': '明哲保身'},
     ]},
    {'key': 'bandit_mercy', 'title': '盗亦有道', 'text': '你抓到一个被迫为盗养家糊口的山贼。',
     'choices': [
         {'key': 'release', 'label': '网开一面', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '心怀慈悲'},
         {'key': 'report', 'label': '押送宗门', 'reward': {'contribution': 10}, 'tag': '铁面无私'},
     ]},
    {'key': 'sect_feud', 'title': '江湖恩怨', 'text': '你卷入两派世仇，双方都要求你选边站队。',
     'choices': [
         {'key': 'refuse', 'label': '拒绝介入，劝双方罢手', 'reward': {'xiaxia_fame': 3}, 'tag': '不涉恩怨'},
         {'key': 'help_weak', 'label': '出手相助势弱一方', 'reward': {'reputation': 3}, 'tag': '路见不平'},
     ]},
    {'key': 'sealed_letter', 'title': '一诺千金', 'text': '陌生人临终前托你送一封密信，信中内容不明。',
     'choices': [
         {'key': 'deliver', 'label': '原封不动送达', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '一诺千金'},
         {'key': 'peek', 'label': '拆信查看', 'reward': {'lingshi': 30}, 'tag': '探听隐秘'},
     ]},
    {'key': 'abandoned_infant', 'title': '心系苍生', 'text': '你路遇一名被遗弃在路边的婴孩。',
     'choices': [
         {'key': 'foster', 'label': '送去附近村庄托养', 'reward': {'reputation': 2, 'xiaxia_fame': 1}, 'tag': '心系苍生'},
         {'key': 'leave', 'label': '匆匆离去', 'reward': {'lingshi': 15}, 'tag': '来去匆匆'},
     ]},
    {'key': 'gambling_cheat', 'title': '仗义执言', 'text': '你目睹赌坊老千算计一名良家子弟。',
     'choices': [
         {'key': 'expose', 'label': '出手拆穿', 'reward': {'xiaxia_fame': 3}, 'tag': '仗义执言'},
         {'key': 'ignore', 'label': '置身事外', 'reward': {'lingshi': 20}, 'tag': '事不关己'},
     ]},
    {'key': 'sparring_invite', 'title': '以武会友', 'text': '一位女侠邀你切磋武艺。',
     'choices': [
         {'key': 'full', 'label': '全力应战', 'reward': {'exp': 60}, 'tag': '以武会友'},
         {'key': 'yield', 'label': '谦让三分', 'reward': {'reputation': 2}, 'tag': '谦逊守礼'},
     ]},
    {'key': 'haunted_tomb', 'title': '胆识过人', 'text': '你夜宿义庄，遇宵小装神弄鬼行骗钱财。',
     'choices': [
         {'key': 'expose', 'label': '揭穿骗局', 'reward': {'xiaxia_fame': 2, 'lingshi': 20}, 'tag': '胆识过人'},
         {'key': 'flee', 'label': '连夜离去', 'reward': {'lingshi': 10}, 'tag': '敬而远之'},
     ]},
    {'key': 'old_debt', 'title': '恩怨难断', 'text': '你曾出手相助之人，如今竟已作恶多端，与你再度相遇。',
     'choices': [
         {'key': 'enforce', 'label': '大义灭亲', 'reward': {'reputation': 3}, 'tag': '大义灭亲'},
         {'key': 'spare', 'label': '念及旧情，放他一马', 'reward': {'xiaxia_fame': 1, 'lingshi': 20}, 'tag': '念旧情长'},
     ]},
    {'key': 'ferry_toll', 'title': '乐善好施', 'text': '江边一群旅人被船夫索要高价渡资，滞留岸边。',
     'choices': [
         {'key': 'pay', 'label': '代付船资，渡众人过江', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '乐善好施'},
         {'key': 'ignore', 'label': '自行渡江，不予理会', 'reward': {'lingshi': 15}, 'tag': '独善其身'},
     ]},
    {'key': 'trapped_cultivator', 'title': '急公好义', 'text': '你探得一处藏宝密室，同时发现旁边石室困着一名素不相识的修士。',
     'choices': [
         {'key': 'save_first', 'label': '先救人，再取宝', 'reward': {'xiaxia_fame': 3, 'reputation': 1}, 'tag': '急公好义'},
         {'key': 'loot_first', 'label': '先取宝，再救人', 'reward': {'lingshi': 50}, 'tag': '利字当头'},
     ]},
    {'key': 'famine_relief', 'title': '扶危济困', 'text': '灾荒之地，戏班义演筹粮，所得仍远远不够。',
     'choices': [
         {'key': 'donate', 'label': '慷慨解囊', 'reward': {'reputation': 3, 'xiaxia_fame': 1}, 'tag': '扶危济困'},
         {'key': 'small', 'label': '随缘布施一点', 'reward': {'lingshi': 10}, 'tag': '量力而行'},
     ]},
    {'key': 'border_dispute', 'title': '公正无私', 'text': '两村因灵田灌溉起了冲突，请你出面评理。',
     'choices': [
         {'key': 'fair', 'label': '秉公裁断', 'reward': {'contribution': 8}, 'tag': '公正无私'},
         {'key': 'smooth', 'label': '各打五十大板，和稀泥了事', 'reward': {'lingshi': 20}, 'tag': '和稀泥'},
     ]},
    {'key': 'midnight_knock', 'title': '古道热肠', 'text': '深夜有陌生人叩响你暂居之所的门，自称迷路求宿一晚。',
     'choices': [
         {'key': 'open', 'label': '开门相助', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '古道热肠'},
         {'key': 'refuse', 'label': '闭门不理，心存戒备', 'reward': {'lingshi': 15}, 'tag': '谨慎自持'},
     ]},
    {'key': 'lost_child', 'title': '寻亲送归', 'text': '集市上一名迷路孩童啼哭不止，说不清家在何处。',
     'choices': [
         {'key': 'help', 'label': '带着他四处寻访家人', 'reward': {'reputation': 2, 'xiaxia_fame': 2}, 'tag': '寻亲送归'},
         {'key': 'hand_off', 'label': '交给附近铺子代为照看便离去', 'reward': {'lingshi': 15}, 'tag': '点到为止'},
     ]},
    {'key': 'wounded_beast', 'title': '灵兽疗伤', 'text': '林间发现一只受伤的灵兽幼崽，警惕地看着你。',
     'choices': [
         {'key': 'heal', 'label': '耐心为它疗伤', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '灵兽疗伤'},
         {'key': 'leave', 'label': '不便插手，随它自生自灭', 'reward': {'lingshi': 10}, 'tag': '顺其自然'},
     ]},
    {'key': 'drought_well', 'title': '枯井引水', 'text': '干旱之地村民为争一口尚存水的井几近械斗。',
     'choices': [
         {'key': 'dig', 'label': '出手相助另寻水源', 'reward': {'reputation': 3, 'xiaxia_fame': 2}, 'tag': '枯井引水'},
         {'key': 'mediate', 'label': '劝说双方按需分水', 'reward': {'contribution': 6}, 'tag': '排忧解难'},
     ]},
    {'key': 'forged_ledger', 'title': '账册见伪', 'text': '你无意间发现镇上账房伪造账册，克扣佃户收成。',
     'choices': [
         {'key': 'expose', 'label': '揭发此事', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '明察秋毫'},
         {'key': 'silent', 'label': '不掺和他人生意', 'reward': {'lingshi': 20}, 'tag': '明哲保身'},
     ]},
    {'key': 'flood_rescue', 'title': '洪水救人', 'text': '暴雨引发山洪，几名村民被困于孤岛般的高地。',
     'choices': [
         {'key': 'rescue', 'label': '涉险将他们一一救出', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '洪水救人'},
         {'key': 'report', 'label': '飞速前往镇上报信求援', 'reward': {'lingshi': 20}, 'tag': '及时通报'},
     ]},
    {'key': 'imposter_cultivator', 'title': '识破假仙', 'text': '一名自称"仙人转世"的骗子正在乡里招摇撞骗。',
     'choices': [
         {'key': 'expose', 'label': '当众揭穿其伎俩', 'reward': {'xiaxia_fame': 2, 'reputation': 2}, 'tag': '识破假仙'},
         {'key': 'ignore', 'label': '不理会，任乡民自行分辨', 'reward': {'lingshi': 15}, 'tag': '事不关己'},
     ]},
    {'key': 'blind_musician', 'title': '知音相赠', 'text': '一位盲眼琴师在路边卖艺，曲调凄婉动人。',
     'choices': [
         {'key': 'reward', 'label': '慷慨打赏并聆听整曲', 'reward': {'xiaxia_fame': 1, 'reputation': 1}, 'tag': '知音相赠'},
         {'key': 'pass', 'label': '匆匆路过', 'reward': {'lingshi': 10}, 'tag': '来去匆匆'},
     ]},
    {'key': 'runaway_bride', 'title': '仗义相护', 'text': '一名女子在成亲路上出逃，被家仆追赶得走投无路。',
     'choices': [
         {'key': 'shield', 'label': '出面周旋替她挡下追兵', 'reward': {'xiaxia_fame': 3, 'reputation': 1}, 'tag': '仗义相护'},
         {'key': 'stay_out', 'label': '此乃家事，不便插手', 'reward': {'lingshi': 15}, 'tag': '不涉家事'},
     ]},
    {'key': 'cursed_scroll', 'title': '古卷之谜', 'text': '古董商兜售一卷据说带诅咒的字画，无人敢买。',
     'choices': [
         {'key': 'buy', 'label': '买下并设法化解', 'reward': {'xiaxia_fame': 2, 'lingshi': 10}, 'tag': '古卷之谜'},
         {'key': 'warn', 'label': '提醒旁人不要上当', 'reward': {'reputation': 2}, 'tag': '好言相劝'},
     ]},
    {'key': 'debt_collector', 'title': '止暴制恶', 'text': '恶仆持棍上门讨债，逼得老妇变卖家产。',
     'choices': [
         {'key': 'stop', 'label': '出手制止并替其还清欠债', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '止暴制恶'},
         {'key': 'talk', 'label': '出面周旋宽限些时日', 'reward': {'lingshi': 20}, 'tag': '善加周旋'},
     ]},
    {'key': 'orphan_apprentice', 'title': '收留孤儿', 'text': '一名孤儿苦苦哀求你收他为徒，虽资质平平。',
     'choices': [
         {'key': 'accept', 'label': '暂且收留，教他谋生本领', 'reward': {'reputation': 2, 'xiaxia_fame': 2}, 'tag': '收留孤儿'},
         {'key': 'redirect', 'label': '为他寻一处能安身的营生', 'reward': {'lingshi': 15}, 'tag': '另作安排'},
     ]},
    {'key': 'poisoned_well', 'title': '查明水患', 'text': '村中水井接连有人腹泻，人心惶惶。',
     'choices': [
         {'key': 'investigate', 'label': '查明是上游腐尸污染，清理水源', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '查明水患'},
         {'key': 'warn', 'label': '仅告知村民暂不要饮用', 'reward': {'lingshi': 15}, 'tag': '点到为止'},
     ]},
    {'key': 'counterfeit_pills', 'title': '识破假药', 'text': '游医在集市贩卖的"灵丹"实为普通糖丸。',
     'choices': [
         {'key': 'expose', 'label': '当场拆穿', 'reward': {'xiaxia_fame': 2, 'reputation': 2}, 'tag': '识破假药'},
         {'key': 'quiet_warn', 'label': '私下提醒买主别上当', 'reward': {'lingshi': 15}, 'tag': '暗中提点'},
     ]},
    {'key': 'lost_swordsman', 'title': '解囊相助', 'text': '一名落魄剑客盘缠用尽，滞留客栈无法离去。',
     'choices': [
         {'key': 'fund', 'label': '资助他盘缠', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '解囊相助'},
         {'key': 'spar', 'label': '以切磋之名"输"他银两', 'reward': {'exp': 30}, 'tag': '以武会友'},
     ]},
    {'key': 'haunted_bridge', 'title': '夜探断桥', 'text': '传闻镇外断桥夜半有鬼影出没，无人敢过。',
     'choices': [
         {'key': 'investigate', 'label': '夜探查明真相(实为流民借宿)', 'reward': {'xiaxia_fame': 2, 'lingshi': 15}, 'tag': '夜探断桥'},
         {'key': 'avoid', 'label': '绕道而行，不去招惹', 'reward': {'lingshi': 10}, 'tag': '敬而远之'},
     ]},
    {'key': 'escaped_prisoner', 'title': '明辨冤情', 'text': '一名越狱者向你哭诉自己是被冤枉入狱的。',
     'choices': [
         {'key': 'help_clear', 'label': '助他查明真相洗脱冤屈', 'reward': {'xiaxia_fame': 3, 'reputation': 1}, 'tag': '明辨冤情'},
         {'key': 'turn_in', 'label': '劝他自首以求清白', 'reward': {'contribution': 6}, 'tag': '循规蹈矩'},
     ]},
    {'key': 'drunken_master', 'title': '虚心请教', 'text': '一位醉倒在路边的老者，谈吐间似有高人风范。',
     'choices': [
         {'key': 'tend', 'label': '照料他并虚心求教', 'reward': {'exp': 40}, 'tag': '虚心请教'},
         {'key': 'ignore', 'label': '不便打扰，悄然离去', 'reward': {'lingshi': 10}, 'tag': '不敢造次'},
     ]},
    {'key': 'stray_cat_spirit', 'title': '善待灵猫', 'text': '一只举止灵异的猫在你脚边徘徊不去，似有所求。',
     'choices': [
         {'key': 'feed', 'label': '喂食并善待它', 'reward': {'xiaxia_fame': 1, 'reputation': 1}, 'tag': '善待灵猫'},
         {'key': 'shoo', 'label': '不予理会', 'reward': {'lingshi': 10}, 'tag': '漠然处之'},
     ]},
    {'key': 'burning_inn', 'title': '火场救人', 'text': '客栈突发大火，尚有旅人被困楼上。',
     'choices': [
         {'key': 'rescue', 'label': '冲入火场救人', 'reward': {'xiaxia_fame': 4, 'reputation': 2}, 'tag': '火场救人'},
         {'key': 'organize', 'label': '组织众人取水灭火', 'reward': {'contribution': 8}, 'tag': '临危不乱'},
     ]},
    {'key': 'counterfeit_hero', 'title': '正本清源', 'text': '有人冒你之名在外行骗敛财，坏你名声。',
     'choices': [
         {'key': 'clarify', 'label': '亲自出面澄清，将其揪出', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '正本清源'},
         {'key': 'shrug', 'label': '清者自清，懒得理会', 'reward': {'lingshi': 15}, 'tag': '清者自清'},
     ]},
    {'key': 'widow_land_dispute', 'title': '为弱者言', 'text': '寡妇的田产被族中恶亲霸占，投告无门。',
     'choices': [
         {'key': 'stand_up', 'label': '出面为她讨回公道', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '为弱者言'},
         {'key': 'fund', 'label': '资助她另谋生计', 'reward': {'lingshi': 20}, 'tag': '解囊相助'},
     ]},
    {'key': 'bandit_child', 'title': '不咎既往', 'text': '一名山匪之子隐姓埋名求学，被人发现身世后遭排挤。',
     'choices': [
         {'key': 'protect', 'label': '为他说情，不因出身论人', 'reward': {'xiaxia_fame': 2, 'reputation': 2}, 'tag': '不咎既往'},
         {'key': 'stay_out', 'label': '不便介入他人纷争', 'reward': {'lingshi': 15}, 'tag': '不涉是非'},
     ]},
    {'key': 'plague_village', 'title': '瘟疫援手', 'text': '一处村落暴发时疫，村民恐慌，无人敢近。',
     'choices': [
         {'key': 'aid', 'label': '送医送药，协助隔离救治', 'reward': {'xiaxia_fame': 4, 'reputation': 2}, 'tag': '瘟疫援手'},
         {'key': 'report', 'label': '上报宗门请求医道峰支援', 'reward': {'contribution': 8}, 'tag': '及时通报'},
     ]},
    {'key': 'duel_challenge', 'title': '不战而屈', 'text': '一名后辈为扬名，无理向你挑衅比试。',
     'choices': [
         {'key': 'spar', 'label': '应战并点到为止', 'reward': {'exp': 30}, 'tag': '以武会友'},
         {'key': 'decline', 'label': '一笑置之，不与计较', 'reward': {'reputation': 2}, 'tag': '不战而屈'},
     ]},
    {'key': 'lost_manuscript', 'title': '完璧归赵', 'text': '你拾得一本武学残卷，扉页写着某峰弟子的名字。',
     'choices': [
         {'key': 'return', 'label': '设法寻回原主归还', 'reward': {'reputation': 3, 'xiaxia_fame': 2}, 'tag': '完璧归赵'},
         {'key': 'study', 'label': '研读一番再想办法归还', 'reward': {'exp': 40}, 'tag': '博采众长'},
     ]},
    {'key': 'merchant_scam', 'title': '揭穿骗局', 'text': '一伙商贾以次充好，坑骗刚入行的年轻商户。',
     'choices': [
         {'key': 'expose', 'label': '当场揭穿他们的把戏', 'reward': {'xiaxia_fame': 2, 'reputation': 2}, 'tag': '揭穿骗局'},
         {'key': 'compensate', 'label': '私下补贴受骗商户损失', 'reward': {'lingshi': 20}, 'tag': '暗中补偿'},
     ]},
    {'key': 'abandoned_shrine', 'title': '重修古祠', 'text': '荒废多年的山神祠年久失修，本地人却仍心存敬意。',
     'choices': [
         {'key': 'repair', 'label': '出资协助修缮', 'reward': {'reputation': 3, 'xiaxia_fame': 1}, 'tag': '重修古祠'},
         {'key': 'skip', 'label': '心意到便可，不必破费', 'reward': {'lingshi': 10}, 'tag': '量力而行'},
     ]},
    {'key': 'thief_apology', 'title': '既往不咎', 'text': '一名曾偷过你财物的小贼登门谢罪，愿以劳力偿还。',
     'choices': [
         {'key': 'forgive', 'label': '既往不咎，放他离去', 'reward': {'xiaxia_fame': 2, 'reputation': 1}, 'tag': '既往不咎'},
         {'key': 'employ', 'label': '让他做点活计将功抵过', 'reward': {'lingshi': 20}, 'tag': '将功抵过'},
     ]},
    {'key': 'wandering_monk', 'title': '斋饭结缘', 'text': '一位云游僧人途经此地，衣衫褴褛却神色安然。',
     'choices': [
         {'key': 'offer', 'label': '布施斋饭，与他攀谈', 'reward': {'xiaxia_fame': 1, 'reputation': 2}, 'tag': '斋饭结缘'},
         {'key': 'pass', 'label': '合十致意，匆匆而过', 'reward': {'lingshi': 10}, 'tag': '点到为止'},
     ]},
    {'key': 'flooded_farmland', 'title': '抢收良田', 'text': '暴雨将至，一片良田眼看就要被淹，农户人手不够。',
     'choices': [
         {'key': 'help', 'label': '搭手抢收粮食', 'reward': {'reputation': 2, 'xiaxia_fame': 2}, 'tag': '抢收良田'},
         {'key': 'compensate', 'label': '赔偿他们预估的损失', 'reward': {'lingshi': 30}, 'tag': '慷慨解囊'},
     ]},
    {'key': 'impostor_official', 'title': '拆穿冒官', 'text': '一名假冒官差的骗子正借势敲诈乡民钱财。',
     'choices': [
         {'key': 'expose', 'label': '拆穿其伪装并送官究办', 'reward': {'xiaxia_fame': 3, 'reputation': 2}, 'tag': '拆穿冒官'},
         {'key': 'scare_off', 'label': '出言警告将其吓退', 'reward': {'lingshi': 15}, 'tag': '不战而屈'},
     ]},
    {'key': 'lost_pet', 'title': '寻回灵宠', 'text': '一名孩童哭着满街寻找走失的家养灵兽。',
     'choices': [
         {'key': 'search', 'label': '帮他一同寻找', 'reward': {'reputation': 2, 'xiaxia_fame': 1}, 'tag': '寻回灵宠'},
         {'key': 'buy_new', 'label': '资助他另寻一只', 'reward': {'lingshi': 20}, 'tag': '解囊相助'},
     ]},
    {'key': 'old_rival', 'title': '一笑泯恩仇', 'text': '昔日结怨的对手落魄潦倒，与你狭路相逢。',
     'choices': [
         {'key': 'help', 'label': '不计前嫌，出手相助', 'reward': {'xiaxia_fame': 3, 'reputation': 1}, 'tag': '一笑泯恩仇'},
         {'key': 'walk_away', 'label': '既往不再纠缠，各自珍重', 'reward': {'lingshi': 10}, 'tag': '各自珍重'},
     ]},
    {'key': 'secret_admirer', 'title': '婉拒不伤', 'text': '一名年轻弟子鼓起勇气向你表明心意。',
     'choices': [
         {'key': 'gentle', 'label': '好言婉拒，不伤对方自尊', 'reward': {'reputation': 2}, 'tag': '婉拒不伤'},
         {'key': 'encourage', 'label': '勉励对方专心修行', 'reward': {'xiaxia_fame': 1, 'exp': 20}, 'tag': '勉励后进'},
     ]},
    {'key': 'mountain_hermit', 'title': '虚心问道', 'text': '深山中偶遇一位不问世事的隐世高人，愿指点一二。',
     'choices': [
         {'key': 'learn', 'label': '虚心求教修行心得', 'reward': {'exp': 50}, 'tag': '虚心问道'},
         {'key': 'gift', 'label': '奉上礼物以表敬意', 'reward': {'reputation': 2, 'xiaxia_fame': 1}, 'tag': '以礼相待'},
     ]},
]
STORY_ENCOUNTERS_BY_KEY = {e['key']: e for e in STORY_ENCOUNTERS}

# ── 探索:后山(入门即可)+ 凡间(结成金丹方可出宗门远行),每个事件2个选择,风险收益不同 ──

EXPLORE_REGIONS = [
    {'key': 'backmountain', 'label': '后山', 'stamina_cost': 5, 'unlock_realm': 0, 'daily_limit': 10,
     'encounter_chance': 0.30, 'desc': '宗门后山,安全的历练之地,新弟子的必经之路,偶有妖物出没。'},
    {'key': 'mortal', 'label': '凡间', 'stamina_cost': 25, 'unlock_realm': 6, 'daily_limit': 6,
     'encounter_chance': 0.40, 'desc': '结成金丹,方有能力远行凡间,见识宗门之外的天地,亦有邪修散修出没。'},
]

_BACKMOUNTAIN_EVENTS = [
    {'key': 'herb_guard', 'text': '你在林中发现一株被妖兽守护的百年灵草。', 'choices': [
        {'key': 'fight', 'label': '正面挑战', 'success_rate': 0.5,
         'success': {'contribution': 20, 'physique': 1}, 'fail': {'mind_state': -5}},
        {'key': 'lure', 'label': '设法引开', 'success_rate': 0.7,
         'success': {'contribution': 12}, 'fail': {'stamina': -5}}]},
    {'key': 'injured_cultivator', 'text': '你遇见一名受伤的同门,倒在山道旁。', 'choices': [
        {'key': 'help', 'label': '出手相助', 'success_rate': 0.8,
         'success': {'reputation': 5, 'mind_state': 3}, 'fail': {'stamina': -5}},
        {'key': 'pass', 'label': '记下位置,回报执事', 'success_rate': 1.0,
         'success': {'reputation': 2}, 'fail': {}}]},
    {'key': 'beast_encounter', 'text': '一头低阶妖兽突然从草丛中扑出。', 'choices': [
        {'key': 'fight', 'label': '出手降服', 'success_rate': 0.55,
         'success': {'contribution': 18, 'physique': 2}, 'fail': {'mind_state': -8}},
        {'key': 'flee', 'label': '全身而退', 'success_rate': 0.9,
         'success': {'exp': 5}, 'fail': {'stamina': -10}}]},
    {'key': 'ruins', 'text': '你在乱石间发现一处不起眼的古修遗迹入口。', 'choices': [
        {'key': 'enter', 'label': '深入探查', 'success_rate': 0.4,
         'success': {'exp': 60, 'contribution': 10}, 'fail': {'mind_state': -5}},
        {'key': 'mark', 'label': '记下方位,择日再来', 'success_rate': 1.0,
         'success': {'reputation': 1}, 'fail': {}}]},
    {'key': 'maze_mist', 'text': '你不慎踏入一片迷雾,方向感开始紊乱。', 'choices': [
        {'key': 'push', 'label': '强行突破', 'success_rate': 0.45,
         'success': {'exp': 20}, 'fail': {'stamina': -15}},
        {'key': 'calm', 'label': '静心等待雾散', 'success_rate': 0.85,
         'success': {'mind_state': 3}, 'fail': {'stamina': -5}}]},
    {'key': 'manual_page', 'text': '山涧水边飘来一页残破的功法残页。', 'choices': [
        {'key': 'study', 'label': '当场研习', 'success_rate': 0.5,
         'success': {'exp': 30}, 'fail': {'mind_state': -3}},
        {'key': 'keep', 'label': '收好带回宗门', 'success_rate': 1.0,
         'success': {'contribution': 8}, 'fail': {}}]},
    {'key': 'sect_peer', 'text': '你偶遇一位同门师兄弟,似乎也在探索后山。', 'choices': [
        {'key': 'team', 'label': '结伴同行', 'success_rate': 0.75,
         'success': {'reputation': 4, 'exp': 10}, 'fail': {}},
        {'key': 'alone', 'label': '各自行动', 'success_rate': 1.0,
         'success': {'exp': 8}, 'fail': {}}]},
    {'key': 'hidden_cave', 'text': '藤蔓深处藏着一个隐蔽的山洞。', 'choices': [
        {'key': 'explore', 'label': '进洞查看', 'success_rate': 0.5,
         'success': {'contribution': 25}, 'fail': {'mind_state': -5}},
        {'key': 'skip', 'label': '不予理会', 'success_rate': 1.0,
         'success': {}, 'fail': {}}]},
    {'key': 'waterfall', 'text': '你路过一处灵气充沛的瀑布,似有洗炼之效。', 'choices': [
        {'key': 'bathe', 'label': '入内洗炼', 'success_rate': 0.6,
         'success': {'physique': 2, 'mind_state': 3}, 'fail': {'stamina': -8}},
        {'key': 'rest', 'label': '在旁小憩', 'success_rate': 1.0,
         'success': {'stamina': 5}, 'fail': {}}]},
    {'key': 'trapped_beast', 'text': '一只妖兽幼崽被猎人陷阱困住,苦苦挣扎。', 'choices': [
        {'key': 'free', 'label': '将其放生', 'success_rate': 0.9,
         'success': {'reputation': 3, 'mind_state': 2}, 'fail': {}},
        {'key': 'ignore', 'label': '视而不见', 'success_rate': 1.0,
         'success': {'exp': 5}, 'fail': {}}]},
    {'key': 'landslide', 'text': '山道突发小规模落石,前路受阻。', 'choices': [
        {'key': 'clear', 'label': '合力清理', 'success_rate': 0.6,
         'success': {'physique': 2}, 'fail': {'stamina': -10}},
        {'key': 'detour', 'label': '绕道而行', 'success_rate': 0.95,
         'success': {'exp': 5}, 'fail': {'stamina': -5}}]},
    {'key': 'night_meditation', 'text': '夜色渐深,你在山巅寻得一处灵气汇聚之地。', 'choices': [
        {'key': 'sit', 'label': '就地打坐', 'success_rate': 0.65,
         'success': {'exp': 25, 'mind_state': 5}, 'fail': {'mind_state': -3}},
        {'key': 'return', 'label': '连夜返回宗门', 'success_rate': 1.0,
         'success': {'stamina': 5}, 'fail': {}}]},
]

_MORTAL_EVENTS = [
    {'key': 'market_gossip', 'text': '你在凡间集市听闻一则关于附近宗门的传闻。', 'choices': [
        {'key': 'probe', 'label': '深入打探', 'success_rate': 0.6,
         'success': {'reputation': 6, 'exp': 10}, 'fail': {'stamina': -8}},
        {'key': 'ignore', 'label': '一笑置之', 'success_rate': 1.0,
         'success': {'exp': 8}, 'fail': {}}]},
    {'key': 'caravan_escort', 'text': '一支商队愿出重金,请你护送一程。', 'choices': [
        {'key': 'accept', 'label': '接下委托', 'success_rate': 0.55,
         'success': {'contribution': 35, 'reputation': 3}, 'fail': {'mind_state': -6}},
        {'key': 'decline', 'label': '婉言谢绝', 'success_rate': 1.0,
         'success': {'exp': 10}, 'fail': {}}]},
    {'key': 'black_market', 'text': '黑市角落有人兜售一件来历不明的异宝。', 'choices': [
        {'key': 'buy', 'label': '买下一探究竟', 'success_rate': 0.45,
         'success': {'exp': 70, 'contribution': 15}, 'fail': {'contribution': -10}},
        {'key': 'walk', 'label': '不予理会', 'success_rate': 1.0,
         'success': {}, 'fail': {}}]},
    {'key': 'official_dispute', 'text': '你路过一处纠纷,当地官府与修士起了冲突。', 'choices': [
        {'key': 'mediate', 'label': '出面调解', 'success_rate': 0.6,
         'success': {'reputation': 8, 'mind_state': 3}, 'fail': {'mind_state': -8}},
        {'key': 'leave', 'label': '避而远之', 'success_rate': 1.0,
         'success': {'stamina': 5}, 'fail': {}}]},
    {'key': 'rogue_cultivator', 'text': '一名散修向你发出切磋邀约。', 'choices': [
        {'key': 'duel', 'label': '应战切磋', 'success_rate': 0.5,
         'success': {'physique': 3, 'reputation': 5}, 'fail': {'mind_state': -6, 'stamina': -10}},
        {'key': 'refuse', 'label': '婉拒', 'success_rate': 1.0,
         'success': {'exp': 8}, 'fail': {}}]},
    {'key': 'mortal_plea', 'text': '一位凡人老者跪求你帮忙寻找走失的孩子。', 'choices': [
        {'key': 'help', 'label': '出手相助', 'success_rate': 0.75,
         'success': {'reputation': 10, 'mind_state': 5}, 'fail': {'stamina': -10}},
        {'key': 'pass', 'label': '爱莫能助', 'success_rate': 1.0,
         'success': {}, 'fail': {'mind_state': -3}}]},
    {'key': 'info_broker', 'text': '一名神秘的情报商人愿以低价出售秘闻。', 'choices': [
        {'key': 'trade', 'label': '花钱买情报', 'success_rate': 0.65,
         'success': {'exp': 40, 'reputation': 3}, 'fail': {'contribution': -15}},
        {'key': 'skip', 'label': '不予理会', 'success_rate': 1.0,
         'success': {'exp': 5}, 'fail': {}}]},
    {'key': 'secret_letter', 'text': '你意外截获一封写给他派长老的密信。', 'choices': [
        {'key': 'deliver', 'label': '原样送回,以示光明磊落', 'success_rate': 0.9,
         'success': {'reputation': 8}, 'fail': {}},
        {'key': 'read', 'label': '拆开一探究竟', 'success_rate': 0.4,
         'success': {'exp': 30, 'contribution': 10}, 'fail': {'reputation': -5}}]},
]

EXPLORE_EVENTS = {'backmountain': _BACKMOUNTAIN_EVENTS, 'mortal': _MORTAL_EVENTS}

# ── 宗门商店:用贡献兑换丹药道具,每种每日限购,给贡献一个持续消费出口 ─────────────────

SHOP_ITEMS = [
    {'key': 'mystic_dust_bundle', 'label': '雾尘囊', 'desc': '内含秘境雾尘×3，供本命法宝温养与转世炼形使用。',
     'cost': 60, 'material': {'key': 'mystic_dust', 'qty': 3}},
    {'key': 'huihun_dan',   'label': '九转回魂丹', 'desc': '续命秘药,服之延寿三十年。',
     'cost': 200, 'reward': {'lifespan_years': 30}},
    {'key': 'liaoxin_dan',  'label': '疗心丹',     'desc': '静心凝神,抚平杂念。',
     'cost': 50,  'reward': {'mind_state': 15}},
    {'key': 'peiyuan_dan',  'label': '培元丹',     'desc': '温养根基,略增修为。',
     'cost': 80,  'reward': {'exp': 100}},
    {'key': 'tili_dan',     'label': '体力丹',     'desc': '恢复体力,应急之选。',
     'cost': 40,  'reward': {'stamina': 40}},
    {'key': 'cuiti_dan',    'label': '淬体丹',     'desc': '淬炼体魄,强身健体。',
     'cost': 60,  'reward': {'physique': 3}},
    {'key': 'yangming_tie', 'label': '扬名帖',     'desc': '广而告之,扬名宗门。',
     'cost': 100, 'reward': {'reputation': 10}},
    {'key': 'jiling_dan',   'label': '聚灵丹',     'desc': '以重金广纳天地灵气,凝练成修为,一次性大补,兑换率略逊培元丹。',
     'cost': 300, 'reward': {'exp': 380}},
]
SHOP_DAILY_LIMIT = 3  # 每种道具每日限购次数

# ── 宗门闲话:后台随机挑两(偶尔三)名在世弟子,纯叙事、不发奖励、不落任何数值,只为让大事记/QQ播报
# 多点"日常感",不是每次tick都触发,靠 SECT_GOSSIP_CHANCE 控制"偶尔"的疏密——具体节奏见 run.py。

SECT_GOSSIP_CHANCE = 0.35  # 每次闲话tick真正触发的概率,不是每次都有
SECT_GOSSIP_TRIO_CHANCE = 0.3  # 触发时选三人凑一段的概率,人数够3人才会走这条分支,其余都是两人
SECT_GOSSIP_FLAVORS = [
    # 日常/温馨向
    "{a}与{b}为了同一株将熟的灵药蹲守了大半日,最后却被路过的小妖兽捷足先登,两人相视苦笑。",
    "{a}在演武场上手把手教{b}一式基础剑招,不料{b}悟性极佳,三两下就青出于蓝,惹得{a}又气又笑。",
    "{a}邀{b}对弈一局,棋至中盘{b}竟悔棋三次,{a}佯怒作势要掀棋盘,惹得围观弟子哄笑。",
    "{a}炼丹时手滑多放了一味料,炸得满屋青烟,正巧路过的{b}被熏得涕泪横流,两人事后传为笑谈。",
    "{a}与{b}比拼谁的灵兽更聪明,结果两只灵兽玩到了一处去,反倒把两位主人晾在一旁面面相觑。",
    "深夜{a}路过{b}的洞府,见灯火未熄,进去一看竟是{b}抱着功法典籍睡着了,替其掖了掖衣衫悄悄离去。",
    "{a}怂恿{b}去讨教长老的独门心得,{b}鼓起勇气敲了门,结果长老正在闭关,两人面面相觑一阵傻笑。",
    "{a}与{b}结伴下山采买,回来时多买了两倍的糕点,理由是「怕不够分」,宗门弟子都调侃这两人默契十足。",
    # 拌嘴/争执向(不伤和气,吵完照样一起玩)
    "{a}与{b}为了该轮到谁值守灵田争执不下,吵到面红耳赤,最后还是被路过的执事一句话打发去各领一半差事。",
    "{a}嫌{b}炼器时手法太糙,{b}反讥{a}纸上谈兵,两人当场约斗切磋,一番拳脚下来倒也不打不相识。",
    "{a}与{b}为了谁的功法更胜一筹争得不可开交,最后谁也没说服谁,倒是把旁听的弟子听得津津有味。",
    "{a}指责{b}上次借的灵石还没还,{b}梗着脖子说早就还了,两人对账半天才发现是记错了日子,闹了个乌龙。",
    "{a}与{b}因为一句「你这招式是抄我的」吵得不可开交,直到翻出各自师承才知是巧合,相视一笑泯恩仇。",
    "{a}嘲讽{b}打坐时鼾声扰人清修,{b}反唇相讥说{a}练功时踩落叶的声响更吵,两人互不相让,不多时又和好如初。",
    "{a}与{b}因为该由谁去禀报长老一件糟心事互相推诿,推来推去谁也不肯先开口,场面一度十分滑稽。",
    "{a}偷偷把{b}晾晒的灵药挪了地方「照顾」,结果被{b}发现后追着理论了半个时辰,最后两人抱着灵药相视大笑。",
    # 巧合/趣事向
    "{a}炼制丹药时随手多添了一颗给{b}尝鲜,{b}吃了直呼过瘾,缠着{a}又讨了两颗才肯罢休。",
    "{a}夜里失眠出来透气,正巧撞见同样睡不着的{b},两人索性对坐聊到天明,谁也没提是为何睡不着。",
    "{b}练功时受了点小伤,{a}二话不说翻箱倒柜找出压箱底的伤药,末了还叮嘱好几遍要按时敷。",
    "{a}路过灵田见{b}一个人忙不过来,二话不说卷起袖子就帮着一起收拾,末了两人满身泥土相视而笑。",
    "{a}给{b}讲了个自以为很好笑的笑话,{b}憋着没笑出声,反倒把{a}自己逗笑了。",
    "{a}收到一封家书,读着读着红了眼眶,{b}恰巧路过,什么也没多问,只是陪着坐了半个时辰。",
    "{a}和{b}算是差一步就撞见彼此闭关走火,幸而都是虚惊一场,事后两人相约以后练功要留人在外头照应。",
    "{a}打赌能一口气念完一篇绕口令的功法口诀,{b}起哄怂恿,结果{a}念到一半自己先笑场,惹得{b}也跟着乐。",
    "{a}与{b}为了灵兽该吃哪种草料争论半天,谁也说服不了谁,最后两只灵兽自己叼着草跑开,倒省了这场辩论。",
    "{a}说{b}上次算账少算了自己一份,{b}翻出账本一条条对,对到最后两人反倒笑场,谁也没说清楚是谁的错。",
    "{a}和{b}为了一句「你上次答应我的事还没做」吵了半天,细一问竟是两人各自记错了对象,闹得哭笑不得。",
    "{a}嫌{b}分派的差事太轻松,{b}索性把重活让给{a},结果{a}做到一半直喊后悔,惹得{b}在一旁看戏。",
]

SECT_GOSSIP_TRIO_FLAVORS = [
    "{a}、{b}、{c}三人凑一桌斗起了法宝识货,轮流拿出压箱底的物件互相唬人,到最后谁也没分出高低,倒喝光了一壶茶。",
    "{a}提议{b}和{c}比试一场,自己在旁边当裁判,结果裁判看得起劲,忘了报分,最后三人干脆一起下场混战。",
    "{a}与{b}为了一件小事拌起嘴来,{c}路过想劝架,三言两语没劝住,反倒被两人一起拉着评理,闹得哭笑不得。",
    "深夜{a}、{b}、{c}凑在一处煮茶夜话,聊到宗门旧事,不知不觉聊到了天光将亮,谁都没舍得先散。",
    "{a}炼丹时手滑闯了祸,满屋青烟,{b}和{c}正巧结伴路过,三人一起被熏得涕泪横流,事后倒成了交情。",
    "{a}怂恿{b}去向{c}讨教一门绝活,{b}扭捏半天鼓起勇气开口,{c}却爽快得很,当场倾囊相授,反倒把{a}晾在一边。",
    "{a}、{b}、{c}结伴下山采买,回来时谁都多买了一份给彼此的礼物,撞在一处相视大笑,倒像是提前商量好的。",
    "{a}说漏了{b}的一件糗事,{c}在旁听得津津有味还添油加醋,气得{b}追着两人满院子跑,惹得旁人纷纷侧目。",
    "{a}与{b}比拼谁的灵兽更聪明,{c}在旁边不服气也放出自家灵兽凑热闹,三只灵兽玩到一处,三位主人反倒插不上手。",
    "{a}、{b}、{c}轮流讲各自出身的江湖故事,讲着讲着才发现三人的师承竟绕了一圈能扯上关系,惊得面面相觑。",
]

def random_gossip_text(a_label, b_label):
    return random.choice(SECT_GOSSIP_FLAVORS).format(a=a_label, b=b_label)

def random_gossip_text_trio(a_label, b_label, c_label):
    return random.choice(SECT_GOSSIP_TRIO_FLAVORS).format(a=a_label, b=b_label, c=c_label)

# ── 羁绊:义结金兰(可多个,单个加成小)/ 道侣(唯一,加成较大),双方同意方可缔结 ──────────

BOND_TYPES = {
    'sworn':     {'label': '义结金兰', 'exp_bonus_pct': 3,  'stackable': True,  'cap_pct': 15},
    'companion': {'label': '道侣',     'exp_bonus_pct': 10, 'stackable': False},
}

# 每名角色对每段羁绊每日可主动互动一次；关系收益刻意保持轻量，重点是共同经历与成长感。
# 不发修为——这块只算默契/心境,修为产出统一走打坐/闭关那条走每日衰减额度的路径,不留旁门。
BOND_INTERACTIONS = {
    'greet': {'label': '传音问候', 'stamina_cost': 0, 'affinity_gain': 2, 'mind_gain': 1,
              'flavors': ['{actor}传来一缕灵识，与{partner}说起今日山间的风。',
                          '{actor}隔着云海问候{partner}，短短数语便令道心安定。']},
    'meditate': {'label': '并肩论道', 'stamina_cost': 10, 'affinity_gain': 4, 'mind_gain': 1,
                 'flavors': ['{actor}与{partner}对坐论道，从日落直至洞府灯火初上。',
                             '{actor}为{partner}演化一段行气法门，二人在印证中各有所得。']},
    'spar': {'label': '切磋试招', 'stamina_cost': 12, 'affinity_gain': 5, 'mind_gain': 0,
             'flavors': ['{actor}与{partner}在演武台上拆解百招，收势时相视一笑。',
                         '{actor}邀{partner}切磋，兵刃与护体灵光相触，激起满院清鸣。']},
}
BOND_STAGE_THRESHOLDS = [(0, '初结缘'), (10, '渐相知'), (30, '契若金兰'), (60, '灵犀相印'), (100, '生死相托')]

GIFT_TYPES = {
    'spirit_tea': {'label': '灵茶小罐', 'cost': {'low': 2}, 'base_affinity': 3,
                   'names': ['云雾灵茶', '松间晚露', '青崖春茶']},
    'dao_letter': {'label': '手书道笺', 'cost': {'low': 1}, 'base_affinity': 2,
                   'names': ['流云道笺', '月下短书', '雁回信笺']},
    'weapon_tassel': {'label': '护身剑穗', 'cost': {'low': 2, 'mid': 1}, 'base_affinity': 5,
                      'names': ['听风剑穗', '赤心刀络', '穿云枪穗', '守心武结']},
    'heart_jade': {'label': '同心玉佩', 'cost': {'mid': 2, 'high': 1}, 'base_affinity': 7,
                   'names': ['合鸣玉', '同心佩', '双鱼灵珏']},
}
GIFT_RARITIES = {
    'plain': {'label': '素朴', 'affinity_bonus': 0}, 'fine': {'label': '精巧', 'affinity_bonus': 2},
    'rare': {'label': '灵韵', 'affinity_bonus': 4}, 'unique': {'label': '天成', 'affinity_bonus': 7},
}
GIFT_TRAITS = {
    'warm': {'label': '余温未散', 'desc': '触手时似仍留着制作者的体温', 'affinity_bonus': 1},
    'scented': {'label': '暗香随行', 'desc': '走近时会闻到很淡的山林清香', 'affinity_bonus': 1},
    'resonant': {'label': '灵息共鸣', 'desc': '靠近对方时会泛起微弱灵光', 'affinity_bonus': 2},
    'weathered': {'label': '风尘有痕', 'desc': '表面留着一段远行的痕迹', 'affinity_bonus': 2},
    'heroic': {'label': '侠意长存', 'desc': '其上隐约留有一缕不平则鸣的侠气', 'affinity_bonus': 2},
    'mystic': {'label': '秘境遗韵', 'desc': '深夜会映出不属于人间的微光', 'affinity_bonus': 3},
}
GIFT_SOURCE_LABELS = {'crafted': '亲手制作', 'mystic': '秘境所得', 'travel': '人间游历', 'xiaxia': '行侠所得'}
GIFT_FIND_CHANCES = {'mystic': 0.12, 'travel': 0.10, 'xiaxia': 0.10}

# 护身剑穗可挂在武器上、同心玉佩可佩戴,各给一点小加成——不为战力,图的是"这是XX亲手做的"那份念想。
GIFT_EQUIP_SLOTS = {'weapon_tassel': 'tassel', 'heart_jade': 'jade'}
GIFT_EQUIP_ATTACK_BONUS = 1
GIFT_EQUIP_DEFENSE_BONUS = 1

# ── 道侣婚讯:缔结道侣时全宗广播+双方各得一份心境贺礼,义结金兰无此仪式 ─────────────────

COMPANION_BOND_MIND_GIFT = 8

# ── 子嗣:求子仪式(参考突破仪式的保底模式)+ 被动成长/教养 + 陨落风险 + 结亲代代相传 ────────
# 父母字段是多态的(角色或子嗣自身),理论上代数不受架构限制,只用 OFFSPRING_MAX_GENERATION
# 这一个常量兜底,配合"每代都要重新走一遍成长→结亲→求子"的真实耗时,天然形成节奏刹车。

OFFSPRING_COMPANION_MIN_DAYS = 2             # 结为道侣满2天才能求子,不是结契当天就能生
OFFSPRING_CONCEIVE_STAMINA_COST = 30
OFFSPRING_CONCEIVE_CONTRIBUTION_COST = 40
OFFSPRING_CONCEIVE_BASE_CHANCE = 0.4
OFFSPRING_CONCEIVE_PITY_INCREMENT_PCT = 15   # 每失败一次,下次成功率 +15 个百分点
OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK = 4 # 连续失败4次后,第5次必得("天赐麟儿")
OFFSPRING_CONCEIVE_COOLDOWN_SECONDS = 10  # 只防连点误触,真正的节奏靠下面的每日上限
OFFSPRING_CONCEIVE_DAILY_CAP = 3          # 一天最多求3次,可以连续点,过了当天这3次就得等明天
OFFSPRING_MAX_GENERATION = 2                 # 子嗣=1代,孙辈=2代;孙辈成年后传承线圆满,不再繁衍

OFFSPRING_MARRY_REALM_IDX = 3   # 筑基初期起可结亲(与角色突破用的境界表是同一张)
OFFSPRING_REALM_CAP_IDX = 8     # 金丹后期封顶,子嗣是背景角色,不需要模拟到飞升那么深

OFFSPRING_PASSIVE_EXP_PER_HOUR = 24  # 被动懒结算,不逼玩家肝按钮,纯靠真实时间流逝长大
OFFSPRING_TEACH_STAMINA_COST = 15
OFFSPRING_TEACH_DAILY_LIMIT = 2
OFFSPRING_TEACH_EXP_RANGE = (40, 90)

OFFSPRING_STAGE_BY_REALM = [
    (0, 0, '襁褓'), (1, 2, '幼学'), (3, 5, '束发'), (6, 999, '及冠及笄'),
]

def offspring_stage(realm_idx):
    for lo, hi, label in OFFSPRING_STAGE_BY_REALM:
        if lo <= realm_idx <= hi:
            return label
    return '及冠及笄'

OFFSPRING_FRAIL_REALM_MAX = 2            # 幼学及以下(未至筑基)才有夭折风险
OFFSPRING_FRAIL_WARN_CHANCE = 0.05       # 教养未成年子嗣时,小概率转入"体弱"预警
OFFSPRING_FRAIL_DEATH_CHANCE = 0.35      # 体弱期间选择"冒险教养"时的夭折概率(寻医不会触发此判定)
OFFSPRING_HEAL_CONTRIBUTION_COST = 80    # 寻医花费(宽限期内),100%清除预警,不涉及概率
OFFSPRING_FRAIL_GRACE_HOURS = 48         # 体弱预警后的宽限期,期内寻医价格不变;成长在体弱期间暂停,不会自动恶化
OFFSPRING_FRAIL_HEAL_LATE_MULT = 2       # 超过宽限期后寻医仍100%可救,只是价格翻倍

OFFSPRING_PER_COUPLE_LIFETIME_CAP = 3    # 同一对配偶终身最多养育的子嗣数(含已故),压住人口膨胀的软上限
OFFSPRING_RENAME_COST = 200              # 给子嗣改名,花贡献或灵石任选其一,不像角色自己改名那样免费

MARRIAGE_REVOKE_WINDOW_SECONDS = 3600    # 结亲/应允散修求亲后1小时内,任一方家长仍可撤回

OFFSPRING_TALENT_INHERIT_CHANCE = 0.15       # 单亲持有(仅血脉,传承需后天认可不遗传)时的继承概率
OFFSPRING_TALENT_INHERIT_CHANCE_BOOST = 0.25 # 双亲持有同一血脉时,合并继承概率

OFFSPRING_NPC_MARRIAGE_ROLL_CHANCE = 0.04  # 教养时小概率弹出散修求亲机缘,刻意压低,鼓励宗门内联姻
OFFSPRING_NPC_SPOUSE_SURNAMES = ['云', '风', '霄', '溪', '岚', '澈', '疏', '行']
OFFSPRING_NPC_SPOUSE_GIVEN = ['游子', '逸尘', '孤舟', '慕晴', '听雨', '踏歌', '拂雪', '知微']

def roll_npc_spouse_name():
    return random.choice(OFFSPRING_NPC_SPOUSE_SURNAMES) + random.choice(OFFSPRING_NPC_SPOUSE_GIVEN)

def roll_offspring_spirit_root(root_a, root_b):
    """继承双亲较优灵根概率最高,较弱次之,小概率按创角原始权重完全重骰;
    永远封顶在创角档位(天灵根双亲也按双灵根参与遗传,不会直接遗传天灵根——
    天灵根是后天蜕变的造化,不是稳定血统性状)。双亲同档时合并为单一档位,提升到80%继承。"""
    def clamp_creation(key):
        if not key or key not in SPIRIT_ROOTS:
            return None
        return key if key in SPIRIT_ROOT_CREATION_KEYS else SPIRIT_ROOT_CREATION_KEYS[0]
    a, b = clamp_creation(root_a), clamp_creation(root_b)
    candidates = [c for c in (a, b) if c]
    if not candidates:
        return roll_spirit_root()
    if len(candidates) == 2 and a == b:
        return a if random.random() < 0.8 else roll_spirit_root()
    candidates.sort(key=lambda k: SPIRIT_ROOTS[k]['mult'], reverse=True)
    better, worse = candidates[0], candidates[-1]
    roll = random.random()
    if roll < 0.5:
        return better
    if roll < 0.8:
        return worse
    return roll_spirit_root()

def roll_offspring_talent(talent_a, talent_b):
    """只继承血脉(先天),不继承传承(后天机缘所得,需要认可,不算血统性状)。
    双亲持有同一血脉时合并继承概率;双亲持有不同血脉时各自进入候选池,但最多继承一个。"""
    def bloodline_only(key):
        return key if key and TALENTS.get(key, {}).get('source') == 'bloodline' else None
    ta, tb = bloodline_only(talent_a), bloodline_only(talent_b)
    if ta and tb and ta == tb:
        return ta if random.random() < OFFSPRING_TALENT_INHERIT_CHANCE_BOOST else None
    pool = [t for t in (ta, tb) if t]
    if pool and random.random() < OFFSPRING_TALENT_INHERIT_CHANCE:
        return random.choice(pool)
    return None

# ── 子嗣的性格/爱好:出生即定,纯 flavor,不带数值加成,只在成长阶段跨越时触发一次里程碑通知 ──
# 让"这个孩子"读起来是个具体的人,而不是一串境界数字——代入感主要来自这层文字,不是新数值系统。

OFFSPRING_PERSONALITIES = {
    'steady':   {'label': '沉稳', 'flavor': '举止沉稳,不骄不躁'},
    'clever':   {'label': '机灵', 'flavor': '心思机灵,一点就透'},
    'playful':  {'label': '顽皮', 'flavor': '性子顽皮,坐不住片刻'},
    'gentle':   {'label': '温婉', 'flavor': '性情温婉,待人和气'},
    'valiant':  {'label': '侠气', 'flavor': '一身侠气,好打抱不平'},
    'aloof':    {'label': '孤僻', 'flavor': '不喜言语,独来独往'},
    'studious': {'label': '好学', 'flavor': '手不释卷,好学不倦'},
}
OFFSPRING_HOBBIES = {
    'sword':    {'label': '剑术', 'flavor': '整日舞刀弄剑'},
    'alchemy':  {'label': '丹药', 'flavor': '喜欢摆弄瓶瓶罐罐'},
    'chess':    {'label': '棋艺', 'flavor': '棋盘前一坐就是半天'},
    'zither':   {'label': '抚琴', 'flavor': '得空便抚琴一曲'},
    'beasts':   {'label': '驯兽', 'flavor': '总爱往后山跑,同灵兽玩闹'},
    'painting': {'label': '丹青', 'flavor': '喜执笔作画,涂涂抹抹'},
    'reading':  {'label': '古籍', 'flavor': '一头扎进藏书阁便不肯出来'},
    'fishing':  {'label': '垂钓', 'flavor': '常在溪边一坐就是一下午'},
}
OFFSPRING_ARCHETYPES = {
    ('steady', 'sword'): '守拙剑心', ('clever', 'alchemy'): '百草灵童',
    ('aloof', 'reading'): '闭门书痴', ('valiant', 'beasts'): '山野游侠',
    ('gentle', 'zither'): '清音雅士', ('playful', 'painting'): '泼墨顽童',
    ('studious', 'chess'): '弈道新秀', ('steady', 'fishing'): '溪上隐者',
}
OFFSPRING_ARCHETYPE_FALLBACKS = ['早慧灵童', '山门少侠', '清修幼徒', '自在少年', '仙门新秀']
OFFSPRING_LIFE_EVENTS = [
    '幼年曾误入后山,被一只灵鹤平安送回', '曾在藏书阁枯坐三日,自行读懂一卷残篇',
    '第一次练剑便引得本命法宝轻鸣回应', '在药圃救活一株将枯灵草,自此颇受草木亲近',
    '曾独自照料受伤灵兽直至痊愈', '于溪边捡到一枚无字玉简,一直珍藏至今',
    '幼时亲历长辈渡劫,从此对大道心生向往', '曾在宗门试炼中主动留下照顾受伤同门',
]

def offspring_archetype(personality_key, hobby_key):
    return OFFSPRING_ARCHETYPES.get((personality_key, hobby_key), random.choice(OFFSPRING_ARCHETYPE_FALLBACKS))

def roll_offspring_life_event():
    return random.choice(OFFSPRING_LIFE_EVENTS)

def roll_offspring_personality():
    return random.choice(list(OFFSPRING_PERSONALITIES.keys()))

def roll_offspring_hobby():
    return random.choice(list(OFFSPRING_HOBBIES.keys()))

OFFSPRING_STAGE_MILESTONE_FLAVOR = {
    '幼学': '已能蹒跚学语、满地跑跳',
    '束发': '已知晓修行不易,渐渐懂事',
    '及冠及笄': '已然长大成人,可独当一面',
}

def offspring_stage_flavor(off_name, stage, personality_label, hobby_label):
    milestone = OFFSPRING_STAGE_MILESTONE_FLAVOR.get(stage, '')
    return f"{off_name}已至{stage}{('，' + milestone) if milestone else ''}。性子{personality_label},素来喜好{hobby_label}。"

# ── 满月酒:父母任选一子嗣办一场,全宗广发请柬,持续1天;来宾花灵石赴宴,各自带一件"抓周之物"
# 投入池中,一天结束随机揭晓孩子抓中了谁带的什么、预示着什么。每个子嗣一生只能办这一场,
# 不设重开,免得变成刷屏的日常提款机 ────────────────────────────────────────────

MANYUE_ENTRY_LINGSHI_COST = 50
MANYUE_DURATION_SECONDS = 86400
MANYUE_PHYSIQUE_GAIN_RANGE = (2, 5)
MANYUE_MATERIAL_TIER_WEIGHTS = {'low': 60, 'mid': 30, 'high': 10}
MANYUE_REWARD_WEIGHTS = {'physique': 40, 'material': 40, 'accessory': 20}

# 抓周之物:40件,分8类各5件,每件配一句"预示"的彩头话,只是气氛,不带数值
ZHUAZHOU_ITEMS = {
    # 文道
    'brush':     {'label': '紫毫笔', 'prediction': '日后文采斐然,或入天枢峰修习丹经,亦通诗书。'},
    'scroll':    {'label': '竹简书卷', 'prediction': '博览群书,见识过人,将来必是宗门藏书阁的常客。'},
    'seal':      {'label': '白玉印', 'prediction': '心思缜密,长大后或可执掌宗门文书要务。'},
    'chess':     {'label': '黑白棋子', 'prediction': '心性沉稳,善谋善断,是块下棋论道的好料子。'},
    'guqin':     {'label': '焦尾琴', 'prediction': '天生一副好耳力,将来说不定能谱出流传九霄的曲子。'},
    # 武道
    'woodsword': {'label': '桃木剑', 'prediction': '自幼握剑不撒手,他日必投云海峰习剑。'},
    'smallbow':  {'label': '小竹弓', 'prediction': '眼疾手快,箭术或许青出于蓝。'},
    'spearbell': {'label': '铃铛枪', 'prediction': '虎头虎脑,天生一副冲锋陷阵的架势。'},
    'wristguard':{'label': '藤甲护腕', 'prediction': '皮糙肉厚不怕摔,是块练武的好料子。'},
    'toyarmor':  {'label': '小号皮甲', 'prediction': '骨骼惊奇,将来必成宗门一员猛将。'},
    # 仙缘
    'lingshi_ingot': {'label': '小块灵石', 'prediction': '与灵气天生亲近,说不定是难得一见的好苗子。'},
    'furnace_toy':   {'label': '迷你丹炉', 'prediction': '对炉火格外感兴趣,将来或投天枢峰习炼丹之道。'},
    'talisman_toy':  {'label': '符箓一张', 'prediction': '指尖灵光乍现,兴许与符箓有不解之缘。'},
    'compass':       {'label': '小罗盘', 'prediction': '对天地方位格外敏感,将来或善阵法。'},
    'mirror':        {'label': '铜镜', 'prediction': '镜中灵光流转,似乎能照见几分来日道途。'},
    # 财富
    'ingot':     {'label': '小元宝', 'prediction': '见钱眼开笑得欢,将来说不定是宗门理财好手。'},
    'abacus':    {'label': '小算盘', 'prediction': '拨弄算珠有模有样,天生一副精打细算的脑子。'},
    'pouch':     {'label': '锦囊', 'prediction': '锦囊藏福,家境将来必定殷实。'},
    'ruyi':      {'label': '玉如意', 'prediction': '万事如意的好兆头,一生顺遂少灾祸。'},
    'coinstring':{'label': '铜钱串', 'prediction': '抓着铜钱不撒手,财运亨通指日可待。'},
    # 情缘
    'knot':      {'label': '同心结', 'prediction': '小小年纪就懂得系同心结,长大后姻缘必定顺遂。'},
    'redstring': {'label': '大红绳', 'prediction': '红绳在手,月老看了都要点头。'},
    'fan':       {'label': '团扇', 'prediction': '举止温婉招人疼,将来必是人群中最惹眼的那个。'},
    'sachet':    {'label': '香囊', 'prediction': '身上带香,走到哪儿都招桃花。'},
    'fishjade':  {'label': '双鱼玉佩', 'prediction': '鱼水相依的好兆头,此生情路必定顺畅。'},
    # 医道
    'hoe':       {'label': '小药锄', 'prediction': '抓着药锄不放手,将来说不定是济世救人的好大夫。'},
    'needle':    {'label': '银针一枚', 'prediction': '手指灵巧,悬壶济世的好苗子。'},
    'gourd':     {'label': '药葫芦', 'prediction': '葫芦里的药,将来定能救人无数。'},
    'pillow':    {'label': '脉枕', 'prediction': '小小年纪就懂号脉,是块学医的好料子。'},
    'mugwort':   {'label': '艾草一束', 'prediction': '身带药香,天生与医道有缘。'},
    # 巧艺
    'ruler':     {'label': '鲁班尺', 'prediction': '量天量地量人心,将来或是巧夺天工的匠人。'},
    'inkline':   {'label': '墨斗', 'prediction': '手上有准头,将来必是玄穹峰炼器的好苗子。'},
    'lubanlock': {'label': '鲁班锁', 'prediction': '小手灵巧解锁如飞,天生一副巧匠脑袋。'},
    'embroidery':{'label': '绣花针', 'prediction': '一针一线皆用心,将来手艺必定不凡。'},
    'hammer':    {'label': '小锤', 'prediction': '抡起小锤虎虎生风,是块打铁淬器的好料子。'},
    # 自由侠义
    'strawshoe': {'label': '草鞋一双', 'prediction': '闲不住的性子,将来必定四处云游。'},
    'winegourd': {'label': '酒葫芦', 'prediction': '小小年纪爱不释手,长大后必定豪爽仗义。'},
    'bell':      {'label': '小铜铃', 'prediction': '走到哪儿都叮当作响,是个闲不住的性子。'},
    'flute':     {'label': '竹笛', 'prediction': '笛声清越,或许将来仗剑江湖,笛剑合璧。'},
    'xiaxia_token': {'label': '侠名令牌', 'prediction': '抓着令牌咯咯直笑,将来必是行侠仗义的好苗子。'},
}

# 满月礼:来宾抽中"饰品"档时任选其一,数值都很克制,图个彩头
MANYUE_GIFT_ACCESSORIES = [
    {'slot': 'accessory', 'key': 'manyue_changming_suo', 'label': '长命锁', 'attack': 0, 'defense': 0, 'agility': 1, 'luck': 3},
    {'slot': 'accessory', 'key': 'manyue_pingan_fu',      'label': '平安符', 'attack': 0, 'defense': 2, 'agility': 0, 'luck': 2},
    {'slot': 'accessory', 'key': 'manyue_yin_lingdang',   'label': '银铃铛', 'attack': 0, 'defense': 0, 'agility': 3, 'luck': 1},
    {'slot': 'accessory', 'key': 'manyue_hutou_mao',      'label': '虎头帽', 'attack': 0, 'defense': 3, 'agility': 0, 'luck': 1},
    {'slot': 'accessory', 'key': 'manyue_baijia_yi',      'label': '百家衣', 'attack': 0, 'defense': 1, 'agility': 1, 'luck': 2},
]
EQUIPMENT_TEMPLATES_BY_KEY.update({t['key']: dict(t, zone='manyue') for t in MANYUE_GIFT_ACCESSORIES})

# ── 交易行:寄售制(非拍卖),挂单即托管物品,买家一口价买断;卖方成交扣手续费,
# 给灵石经济一个温和的池外流出,避免左手倒右手的无损套利 ──────────────────────────────

MARKET_LISTING_DAILY_LIMIT = 5    # 每日最多新建挂单数,防刷屏
MARKET_LISTING_MAX_ACTIVE = 10    # 同时在架的挂单数上限
MARKET_TAX_PCT = 5                # 成交时从卖方所得中扣除的手续费
MARKET_MIN_PRICE = 1

# ── 私信:每日发信上限,防止刷屏 ───────────────────────────────────────────────────

MAIL_DAILY_LIMIT = 15

# 信箱只留最近这么多封"已处理"的信(已读且没有待领取附件的),避免系统信越攒越多把信箱撑得没法翻;
# 带未领取附件的信不管多老都不受此限制,不会因为翻不到而白白漏领。
MAIL_INBOX_DISPLAY_LIMIT = 40

# ── 师承称谓:按辈分远近生成"师祖/太师祖"、"徒孙/曾徒孙"这类称呼,链条本身由 ──────────
# discipleships 表天然构成(disciple_id 唯一→每人至多一位在世师父),这里只是取名规则

# ── 拜师:须先入峰,可拜同峰任意师兄姐(含峰主);NPC自动同意,玩家需双向确认。
# 一生只认一位师父,除非师父身故——师父飞升不解除师徒名分,仍算其徒。
# 师父接受时须赐字、赠一件礼物(材料或装备),NPC同意时由宗门代为赐字并薄赠一份见面礼。──────
MENTOR_ZI_POOL = [
    '子轩', '伯言', '仲玉', '子期', '孟怀', '叔夜', '德昭', '景明', '子牧', '仲谋',
    '伯玉', '知微', '若尘', '清源', '云舟', '子归', '怀瑾', '望舒', '子墨', '长风',
    '青崖', '空明', '玄机', '君卿',
]
MENTOR_NPC_GIFT_MATERIAL = 'mystic_dust'
MENTOR_NPC_GIFT_QTY = 3

ANCESTOR_LABELS = ['师父', '师祖', '太师祖', '烈祖', '天祖']
DESCENDANT_LABELS = ['徒弟', '徒孙', '曾徒孙', '玄徒孙']

def ancestor_label(depth):
    return ANCESTOR_LABELS[depth] if depth < len(ANCESTOR_LABELS) else f'第{depth + 1}代先祖'

def descendant_label(gen):
    return DESCENDANT_LABELS[gen] if gen < len(DESCENDANT_LABELS) else f'第{gen + 1}代弟子'

# ── 成就(声明式,condition 支持 realm_reached / rank_reached / has_talent / has_immortal_bone) ──

# 单一触发来源、按 add_dao_progress 默认计数器key(dao_<path_key>)算每日上限的道途,列在这里
# 供首页展示"今日已计入X/Y次",避免玩家拿"今日点了很多次却没涨多少"当成bug——
# freedom(3个来源分开计,total_actions下文单独算)和 defiance(无每日上限)不在此列。
DAO_DAILY_CAPS = {'sword': 5, 'steadfast': 5, 'mercy': 3, 'beasts': 3, 'creation': 5}

DAO_PATHS = {
    'sword':    {'label': '问剑道', 'requirement': '秘境战斗获胜20次', 'target': 20,
                 'bonus_desc': '攻击+8', 'bonus': {'attack': 8}},
    'steadfast': {'label': '守一道', 'requirement': '以峰门功法修炼20次', 'target': 20,
                  'bonus_desc': '打坐修为+5%', 'bonus': {'exp_pct': 5}},
    'mercy':    {'label': '济世道', 'requirement': '完成宗门委托15次', 'target': 15,
                 'bonus_desc': '委托贡献+8%', 'bonus': {'commission_pct': 8}},
    'beasts':   {'label': '万灵道', 'requirement': '训养灵宠12次', 'target': 12,
                 'bonus_desc': '灵宠加成额外+3%', 'bonus': {'pet_pct': 3}},
    'creation': {'label': '造化道', 'requirement': '炼丹、炼器或温养法宝成功25次', 'target': 25,
                 'bonus_desc': '炼制成功率+3%', 'bonus': {'craft_success_pct': 3}},
    'defiance': {'label': '逆命道', 'requirement': '经历突破失败或绝境成功12次', 'target': 12,
                 'bonus_desc': '突破成功率+3%', 'bonus': {'breakthrough_pct': 3}},
    'freedom':  {'label': '逍遥道', 'requirement': '完成探索或秘境行程15次', 'target': 15,
                 'bonus_desc': '灵巧+5', 'bonus': {'agility': 5}},
}

def dao_path_bonus(path_keys, bonus_key):
    return sum(DAO_PATHS[k]['bonus'].get(bonus_key, 0) for k in path_keys if k in DAO_PATHS)

ACHIEVEMENTS = [
    {'key': 'join_sect', 'name': '入门九霄', 'description': '正式拜入九霄仙门,成为外门弟子。',
     'condition': {'type': 'rank_reached', 'value': 0}, 'reward': {'contribution': 10}},
    {'key': 'inner_disciple', 'name': '登堂入室', 'description': '晋升为内门弟子。',
     'condition': {'type': 'rank_reached', 'value': 2}, 'reward': {'contribution': 50}},
    {'key': 'elite_disciple', 'name': '拜入名峰', 'description': '晋升为亲传弟子,拜入长老门下。',
     'condition': {'type': 'rank_reached', 'value': 3}, 'reward': {'contribution': 100, 'exp': 500}},
    {'key': 'become_steward', 'name': '执掌一事', 'description': '晋升为执事,开始接触宗门经营。',
     'condition': {'type': 'rank_reached', 'value': 4}, 'reward': {'contribution': 200, 'reputation': 50}},
    {'key': 'become_elder', 'name': '一峰之主', 'description': '晋升为长老,可开峰收徒。',
     'condition': {'type': 'rank_reached', 'value': 5}, 'reward': {'contribution': 300, 'exp': 2000}},
    {'key': 'reach_jindan', 'name': '金丹有成', 'description': '修为突破至金丹初期。',
     'condition': {'type': 'realm_reached', 'value': 6}, 'reward': {'contribution': 80}},
    {'key': 'reach_yuanying', 'name': '元婴出窍', 'description': '修为突破至元婴初期。',
     'condition': {'type': 'realm_reached', 'value': 9}, 'reward': {'contribution': 200}},
    {'key': 'reach_huashen', 'name': '化神通天', 'description': '修为突破至化神初期。',
     'condition': {'type': 'realm_reached', 'value': 12}, 'reward': {'contribution': 500}},
    {'key': 'reach_heti', 'name': '形神合体', 'description': '修为突破至合体初期。',
     'condition': {'type': 'realm_reached', 'value': 15}, 'reward': {'contribution': 800}},
    {'key': 'reach_dacheng', 'name': '大乘圆满', 'description': '强渡九重天劫,修为臻至大乘圆满,道途至此已臻巅峰。',
     'condition': {'type': 'realm_reached', 'value': 18}, 'reward': {'contribution': 1500, 'reputation': 100}},
    {'key': 'talent_awakened', 'name': '天赋在身', 'description': '拥有血脉或传承之资。',
     'condition': {'type': 'has_talent', 'value': True}, 'reward': {'contribution': 50}},
    {'key': 'talent_grand', 'name': '资质大成', 'description': '血脉/传承加成升级至大成。',
     'condition': {'type': 'talent_major', 'value': True}, 'reward': {'contribution': 150}},
    {'key': 'immortal_bone', 'name': '仙骨在体', 'description': '于洗髓奇遇中觅得一枚仙骨,全宗独一份。',
     'condition': {'type': 'has_immortal_bone', 'value': True}, 'reward': {'contribution': 300}},
    {'key': 'solo_breakthrough', 'name': '孤身问道', 'description': '不邀护法,独自一人突破境界成功。',
     'condition': {'type': 'manual'}, 'reward': {'contribution': 50, 'reputation': 10}},
    {'key': 'ascended_immortal', 'name': '飞升仙去', 'description': '大乘圆满,举行飞升仪式,渡劫飞升,证道成仙。',
     'condition': {'type': 'ascended'}, 'reward': {'contribution': 1000, 'reputation': 200}},
]

# ══ 游历人间:长周期、轻操作、剧情驱动 ══════════════════════════════════════════════
# 定位区分:秘境=短周期高风险资源驱动,游历=长周期轻操作剧情驱动,委托=稳定日常收益,
# 天魔=限时协作活动。游历不像秘境/闭关那样禁止其他操作——纯后台计时+惰性结算,
# 玩家游历途中仍可打坐、炼丹、参加委托等,不加任何 in_retreat() 式的门禁。
#
# 首版只做青石镇1个地区,验证"玩家愿不愿意等、记不记得前情、选项是否真有差异",
# 其余6个地区、多维声望、NPC关系持久化、与副业/秘境联动都留到验证通过后再做。

TRAVEL_POINTS_CAP = 6
TRAVEL_POINTS_REGEN_PER_DAY = 6  # 懒惰结算,和 stamina/stamina_ts 同一套写法,只是速率换成"天";
# 原先2点/天回满要3天太慢,改成6点/天(每4小时1点),空槽24小时内正好回满

# 四档不再靠"槽位数量"堆性价比,而是靠"槽位质量"分工:短途图快、普通是基准、远行选择事件更浓、
# 云游有保底特殊事件——这样价值不会全部收敛到同一档,玩家按上线节奏选,不是无脑冲最高性价比那档。
TRAVEL_DURATIONS = [
    {'key': 'short',  'label': '短途游历', 'hours': 2,  'cost': 1, 'event_slots': 1,
     'choice_weight_mult': 1.0, 'guarantee_special': False},
    {'key': 'normal', 'label': '普通游历', 'hours': 6,  'cost': 2, 'event_slots': 2,
     'choice_weight_mult': 1.0, 'guarantee_special': False},
    {'key': 'long',   'label': '远行游历', 'hours': 12, 'cost': 2, 'event_slots': 2,
     'choice_weight_mult': 1.8, 'guarantee_special': False},
    {'key': 'wander', 'label': '云游四方', 'hours': 24, 'cost': 3, 'event_slots': 3,
     'choice_weight_mult': 1.3, 'guarantee_special': True},
]
TRAVEL_DURATIONS_BY_KEY = {d['key']: d for d in TRAVEL_DURATIONS}

TRAVEL_REGIONS = [
    {'key': 'qingshi', 'label': '青石镇', 'realm_req': 0,
     'desc': '依山傍水的凡人小镇,茶馆酒肆、江湖异闻皆汇于此,是弟子游历的第一站。'},
]
TRAVEL_REGIONS_BY_KEY = {r['key']: r for r in TRAVEL_REGIONS}

# 即时见闻:当场结束不分支,负责填充旅途。reward 支持 apply_reward 的键位,
# 外加两个游历专属键:familiarity(地区熟悉度增量)、material(灵材字典,走 _grant_material)
# 文案基调:小地方的江湖气——悬赏、镖队、踢馆、独行客、血迹、黑市,不写岁月静好的生活流,
# 让"这一路随时可能撞上点什么"的悬念感贯穿始终,即便青石镇只是凡人级别的起点。
TRAVEL_INSTANT_EVENTS = {
    'qingshi': [
        {'key': 'wanted_poster', 'text': '城墙根贴着一张悬赏画像,画中人剑眉入鬓、锋芒毕露,赏银数目不小,你多看了两眼,把那张脸记在心里。',
         'reward': {'familiarity': 4}},
        {'key': 'escort_caravan', 'text': '官道上一支镖队疾驰而过,镖旗猎猎,车辙压得极深,想是又押着什么要紧物件赶路。',
         'reward': {'lingshi': 6, 'familiarity': 3}},
        {'key': 'inn_brag', 'text': '客栈里几个游侠儿正高谈阔论,吹嘘自己如何单枪匹马闯过什么阵仗,你听得半信半疑,倒也听出几分门道。',
         'reward': {'lingshi': 6, 'familiarity': 3}},
        {'key': 'duel_challenge', 'text': '镇口有人摆下"踢馆"的阵仗,拳脚生风,叫嚣着找人比试,围了一圈看热闹的人。',
         'reward': {'reputation': 2, 'familiarity': 3}},
        {'key': 'lone_swordsman', 'text': '一位独臂剑客独坐酒肆一角,不发一言,周身气息却让人不敢轻易招惹,你识趣地绕开了他的桌案。',
         'reward': {'familiarity': 4}},
        {'key': 'bandit_rumor', 'text': '听闻镇外山道近来多了几伙不太平的角色,专挑落单的行商下手,你留了个心眼,绕道而行。',
         'reward': {'familiarity': 3}},
        {'key': 'jianghu_slang', 'text': '你在江湖切口上吃了个小亏,被摊主几句黑话唬得多付了几文钱,索性当作长了见识。',
         'reward': {'lingshi': 4, 'familiarity': 2}},
        {'key': 'hidden_master', 'text': '荒庙借宿一晚,依稀听见隔壁传来练功的绵长呼吸声,天亮时却已人去屋空,只留半个清晰脚印。',
         'reward': {'familiarity': 4}},
        {'key': 'blood_trail', 'text': '山道旁发现一滩尚未干涸的血迹,一路蜿蜒不知去向,你按下心头的好奇,没有追上去。',
         'reward': {'familiarity': 3}},
        {'key': 'night_market', 'text': '夜里的黑市摊子上,有人压低声音兜售几件来路不明的物件,你没多问来历,只捡了件顺眼的。',
         'reward': {'material': {'low': 1}, 'familiarity': 2}},
    ],
}

# 独立选择事件(不牵出连锁奇遇)与连锁奇遇入口共用一套结构:
# choices 里 success_rate/success/fail 缺省分别视为 1.0/{}/{} ；requires 缺省不限制。
# 若某个 choice 带 starts_thread,则该选择成功时会在 TRAVEL_THREADS 里生根,按 next+delay_hours
# 排到对应节点的解锁时间——thread 一旦生根,同一角色不会再抽到这条入口事件(见抽取逻辑)。
TRAVEL_CHOICE_EVENTS = {
    'qingshi': [
        {'key': 'baby_beast', 'text': '草丛里蜷缩着一只受惊的幼年妖兽,浑身发抖,不住地哀鸣。',
         'choices': [
             {'key': 'rescue', 'label': '上前安抚救助', 'success_rate': 0.8,
              'success': {'reputation': 3, 'familiarity': 4}, 'fail': {'mind_state': -3}},
             {'key': 'capture', 'label': '尝试捕捉带走', 'success_rate': 0.5,
              'success': {'material': {'low': 2}, 'familiarity': 2}, 'fail': {'mind_state': -5}},
             {'key': 'scare_off', 'label': '出声驱赶', 'success_rate': 1.0,
              'success': {'familiarity': 2}, 'fail': {}},
             {'key': 'observe', 'label': '静观其变', 'success_rate': 1.0,
              'success': {'familiarity': 3}, 'fail': {}},
         ]},
        {'key': 'street_fight', 'text': '街角两拨人起了争执,言语间火气渐盛,眼看就要动手。',
         'choices': [
             {'key': 'help_one', 'label': '出手帮一方震慑对方', 'requires': {'stat': 'attack', 'min': 10},
              'success_rate': 0.7, 'success': {'reputation': 4, 'familiarity': 3}, 'fail': {'mind_state': -5}},
             {'key': 'mediate', 'label': '出面调解', 'success_rate': 0.6,
              'success': {'reputation': 3, 'familiarity': 3}, 'fail': {'reputation': -2}},
             {'key': 'watch', 'label': '袖手旁观', 'success_rate': 1.0,
              'success': {'familiarity': 2}, 'fail': {}},
         ]},
        {'key': 'wounded_cultivator', 'text': '你在路边发现一名气息紊乱的修士,伤势不轻,似是遭人追杀所致。',
         'choices': [
             {'key': 'treat', 'label': '施以援手救治', 'success_rate': 1.0,
              'success': {'mind_state': 2}, 'fail': {},
              'starts_thread': 'anonymous_letter', 'next': 'letter_arrives', 'delay_hours': 6},
             {'key': 'ask', 'label': '先问明情况再救', 'requires': {'stat': 'agility', 'min': 5},
              'success_rate': 1.0, 'success': {'mind_state': 2, 'familiarity': 2}, 'fail': {},
              'starts_thread': 'anonymous_letter', 'next': 'letter_arrives', 'delay_hours': 6},
             {'key': 'search', 'label': '先搜身查看', 'success_rate': 1.0,
              'success': {'material': {'low': 1}}, 'fail': {},
              'starts_thread': 'anonymous_letter', 'next': 'wary_start', 'delay_hours': 1},
             {'key': 'leave', 'label': '绕道离开', 'success_rate': 1.0, 'success': {}, 'fail': {}},
         ]},
        {'key': 'found_pouch', 'text': '你在一株老树根下发现半只陈旧的储物袋,里面似乎还有东西。',
         'choices': [
             {'key': 'open', 'label': '当场打开查看', 'success_rate': 1.0, 'success': {}, 'fail': {},
              'starts_thread': 'pouch_mystery', 'next': 'deliver_search', 'delay_hours': 4},
             {'key': 'find_owner', 'label': '先设法寻找失主', 'success_rate': 1.0, 'success': {}, 'fail': {},
              'starts_thread': 'pouch_mystery', 'next': 'deliver_search', 'delay_hours': 10},
             {'key': 'hand_in', 'label': '交给宗门处理', 'success_rate': 1.0,
              'success': {'contribution': 15}, 'fail': {}},
         ]},
    ],
}
TRAVEL_CHOICE_EVENTS_BY_KEY = {e['key']: e for pool in TRAVEL_CHOICE_EVENTS.values() for e in pool}

# 连锁奇遇:node 里每个 choice 要么继续(next+delay_hours,可选 effects 作为这一步的即时小奖励),
# 要么终结(outcome: completed/failed + result_text + effects)。节点内选择不吃随机,
# 由 requires(属性门槛)决定能不能选,选了就是确定的分支,不像独立事件那样有成功率。
TRAVEL_THREADS = {
    'anonymous_letter': {
        'label': '无名来信', 'region': 'qingshi',
        'nodes': {
            'wary_start': {
                'text': '你从其怀中搜出一枚玉牌,尚未细看,那修士已悠悠转醒,眼神里满是戒备。',
                'choices': [
                    {'key': 'apologize', 'label': '致歉解释,归还玉牌', 'next': 'letter_arrives', 'delay_hours': 5,
                     'effects': {'reputation': 1}},
                    {'key': 'flee', 'label': '转身离去', 'outcome': 'failed', 'effects': {},
                     'result_text': '你悄然离去,这段际遇就此断了线索。'},
                ]},
            'letter_arrives': {
                'text': '数日后,你收到一封无落款的信,字迹清瘦,似是那位修士所留,信上只有一处地名与一个时辰。',
                'choices': [
                    {'key': 'go', 'label': '依约前往', 'next': 'ambush', 'delay_hours': 2, 'effects': {}},
                    {'key': 'ignore', 'label': '不予理会', 'outcome': 'failed', 'effects': {},
                     'result_text': '你终究没有赴约,这段际遇不了了之。'},
                ]},
            'ambush': {
                'text': '你依约来到城郊破庙,却见那修士被三名黑衣人团团围住,已是伤痕累累。',
                'choices': [
                    {'key': 'protect', 'label': '出手相护', 'requires': {'stat': 'attack', 'min': 15},
                     'outcome': 'completed',
                     'result_text': '你击退黑衣人,那修士含泪道谢,自称"沈某",约定他日必有厚报。',
                     'effects': {'reputation': 15, 'familiarity': 10}},
                    {'key': 'hand_over', 'label': '佯装不识,悄然退开', 'outcome': 'completed',
                     'result_text': '你没有卷入这场纷争,只是远远看着黑衣人将那修士带走,心中五味杂陈。',
                     'effects': {'familiarity': 4}},
                    {'key': 'investigate', 'label': '先探查黑衣人来历', 'requires': {'stat': 'agility', 'min': 8},
                     'outcome': 'completed',
                     'result_text': '你悄悄跟出一段路,认出黑衣人腰间刻着一个陌生宗门的印记,记在心里。',
                     'effects': {'material': {'mid': 2}, 'familiarity': 8}},
                ]},
        }},
    'pouch_mystery': {
        'label': '储物袋疑云', 'region': 'qingshi',
        'nodes': {
            'deliver_search': {
                'text': '储物袋中除了几枚灵石,还有一封写给"阿澜"的家书,字里行间满是牵挂。'
                        '你几经打听,终于在镇东头的绣坊寻到了阿澜其人。',
                'choices': [
                    {'key': 'deliver', 'label': '亲手归还家书', 'outcome': 'completed',
                     'result_text': '阿澜接过家书,泪流满面——写信之人是她多年未见、卧病在床的兄长。'
                                    '她再三道谢,又塞给你几枚灵石作为答谢。',
                     'effects': {'reputation': 10, 'familiarity': 8, 'lingshi': 20}},
                    {'key': 'keep', 'label': '径自留下财物,不再多管', 'outcome': 'completed',
                     'result_text': '你将灵石收入囊中,只当从未发现过这封信。',
                     'effects': {'lingshi': 30}},
                ]},
        }},
}

# 传说奇遇:门槛式触发,不是纯抽奖;达标后概率从低位开始,每次没抽中就往上加,而不是从头到尾固定25%
# (固定25%在达标后平均4次事件就命中,很快就从"传说"变成常规掉落)——命中或达成即永久标记
# (记一行 travel_threads,thread_key=事件key),不会再触发第二次,miss_streak 也随之作废。
TRAVEL_LEGENDARY_FAMILIARITY_REQ = 30
TRAVEL_LEGENDARY_BASE_CHANCE = 0.05
TRAVEL_LEGENDARY_CHANCE_STEP = 0.03
TRAVEL_LEGENDARY_CHANCE_CAP = 0.20
TRAVEL_LEGENDARY_EVENTS = {
    'qingshi': [
        {'key': 'qingshi_secret', 'region': 'qingshi',
         'requires_familiarity': TRAVEL_LEGENDARY_FAMILIARITY_REQ,
         'requires_thread_completed_any': ['anonymous_letter', 'pouch_mystery'],
         'text': '一位鹤发老者引你至镇外古井旁,说起四十年前的一桩旧事——'
                 '当年镇上曾有一位隐世修士在此闭关,临走时留下一缕残念,静待有缘人。'
                 '你依言探入井中,果然摸到一枚温润的玉简。',
         'effects': {'reputation': 20, 'familiarity': 15, 'material': {'artifact_soul_thread': 1}}},
    ],
}
TRAVEL_LEGENDARY_EVENTS_BY_KEY = {e['key']: e for pool in TRAVEL_LEGENDARY_EVENTS.values() for e in pool}

TRAVEL_INSTANT_WEIGHT = 3  # 事件池抽取权重:即时见闻负责填充旅途,选择事件相对稀有
TRAVEL_CHOICE_WEIGHT = 1
TRAVEL_DANGER_WEIGHT = 1

# 熟悉度阶梯:目前先做两级,30解锁传说奇遇资格(见上),50起选择事件权重加成——不是刷够30就到顶,
# 后续再逐步补10/20/70/100那几档(减少重复见闻/危险提示/称号等),先验证这两档有没有感知度
TRAVEL_FAMILIARITY_CHOICE_BOOST_THRESHOLD = 50
TRAVEL_FAMILIARITY_CHOICE_BOOST_MULT = 1.5

TRAVEL_THREAD_STATUS_LABELS = {
    'clue': '线索持有', 'waiting': '等待发展', 'ready': '可以继续',
    'completed': '已完成', 'failed': '已搁浅',
}

# 遇险事件:力战/呼叫宗门求援/设法脱身三选一(选项固定,不逐条写 choices,由 app.py 统一处理)。
# power_mult 配合 combat_realm_power(region.realm_req) 算力战胜率阈值,越大越难打。
TRAVEL_DANGER_EVENTS = {
    'qingshi': [
        {'key': 'bandit_ambush', 'text': '你走在山道上,忽然从林中窜出两名蒙面劫匪,拦住去路,亮出了刀。',
         'power_mult': 0.5},
        {'key': 'night_prowler', 'text': '夜宿荒庙时,一道黑影破窗而入,直取你的储物袋,来势不善。',
         'power_mult': 0.55},
        {'key': 'rogue_cultivator', 'text': '一名散修拦路,自称"此路是我开",不留下买路钱休想过去。',
         'power_mult': 0.6},
    ],
}
TRAVEL_DANGER_EVENTS_BY_KEY = {e['key']: e for pool in TRAVEL_DANGER_EVENTS.values() for e in pool}

# 求援:全宗可见,认领后独占一段时间去完成救援判定,响应者和求援者都有奖励;窗口内无人完成则后备力量兜底
TRAVEL_RESCUE_WINDOW_SECONDS = 30 * 60   # 总求援窗口:超过这个时间还没被"完成"救援,才轮到后备力量兜底
TRAVEL_RESCUE_CLAIM_SECONDS = 3 * 60     # 认领(响应)后独占这份求援的时间,须在此期间完成救援判定,超时释放给别人
TRAVEL_RESCUE_CALLER_REWARD = {'reputation': 5}
TRAVEL_RESCUE_RESCUER_REWARD = {'reputation': 10, 'contribution': 20}
TRAVEL_RESCUE_RESCUER_REPEAT_REWARD = {'contribution': 20}  # 同一天同一对玩家重复互救,声望不再重复给
TRAVEL_RESCUE_ATTEMPT_CONSOLATION = {'contribution': 5}     # 认领后救援判定失败,给点辛苦费,释放认领
TRAVEL_RESCUE_POWER_DISCOUNT_PCT = 20    # 救援者是"带着准备赶来的援手",判定门槛比求援者当场应对时低这么多

# 无人在窗口内完成救援,由宗门后备力量兜底——"同门来救我"的负面兜底版本,不是孤立无援的惩罚,
# 所以代价刻意压得比之前轻很多:6~12小时区间取中,不封死打坐/委托(打折而不是禁止),只封高风险的秘境/再次出行
TRAVEL_MINOR_INJURY_HOURS = 8
TRAVEL_MINOR_INJURY_MIND_PENALTY = 12
TRAVEL_MINOR_INJURY_CULTIVATE_MULT = 0.5    # 轻伤期间打坐收益打对折,不是完全打坐不了
TRAVEL_MINOR_INJURY_COMMISSION_MULT = 0.5   # 委托收益同样打对折
TRAVEL_MINOR_INJURY_LINGSHI_COST = 30       # 固定的医药费,不按身家比例扣,富玩家不会被打成穷玩家
TRAVEL_DANGER_FIGHT_WIN_EFFECTS = {'reputation': 5, 'familiarity': 5, 'material': {'low': 1}}
TRAVEL_DANGER_FIGHT_LOSE_MIND_PENALTY = 8
