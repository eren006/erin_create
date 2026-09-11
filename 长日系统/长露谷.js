// ==UserScript==
// @name         长露谷
// @author       长日将尽
// @version      2.4.1
// @description  【Beta测试版，数值/规则可能随时调整】种地(32种作物)、浇水、养殖(鸡/羊/牛)、钓鱼、酿酒、做饭(25道菜谱)、逛商店的群互动小游戏，成就墙+家园装饰，四季日历+天气生态联动+浮动市场+节日活动+看电视解锁菜谱，作物/动物/酒/菜到期主动提醒，还能互相偷菜/送礼
// @license      MIT
// ==/UserScript==

// 注意：版本号是 2.4.x，但代码内容底子是 v1.9.1 的原样回退。
// 2.x 之后加的地牢/防刷屏/指令包装层等改动导致「农场帮助」在群里收不到，排查未果，
// 直接回退到已知可用的 1.9.1；版本号只能递增（否则装了 2.x 的人收不到这次更新），
// 所以标成 2.4.0。被回退掉的 2.3.0 全部内容保存在 git 提交 42c84dc，需要时可取回。
// 2.4.1：修了送礼/偷菜在"@机器人才能触发指令"群里误把机器人自己当目标的 bug。

/**
 * 数据存储
 *   farm_epoch  游戏历元时间戳（string），日历/天气/市场都从这个时间点起算
 *   farm_data   { "platform:uid": PlayerState }
 *   farm_world  { dayIndex, weather, prices, rainApplied }  全群共用的天气与市场行情
 *
 * PlayerState:
 *   roleName                   昵称
 *   coins                      金币（全群共用同一份，不管在哪个群操作都是同一个农场）
 *   groups: [ groupId, ... ]   这个人用农场功能碰过的所有群（去重），只用来决定"农场排行"在
 *                              哪些群能看到他，不影响提醒——提醒看的是下面 Plot/AnimalState 各自的 groupId
 *   plots: [ null | Plot, ... ]  长度在 BASE_PLOTS ~ MAX_PLOTS 之间（扩地会增加）
 *   animals: { "鸡": AnimalState, "羊": AnimalState, "牛": AnimalState }
 *   ingredients: { 名称: 数量 }  原料仓库，收菜/收取养殖产出时顺手攒的，喂给酒窖/厨房用
 *   goods: { 名称: 数量 }        成品仓库，收酒/出锅存进来的酒/菜，靠「卖成品」变现或「送礼」流通
 *   brewery / kitchen: Facility   酒窖 / 厨房，结构一样，见下方 Facility
 *   debt: { amount, paidOff }   继承长露谷背的欠款，没有期限也不计息
 *   totalEarned                终身累计赚取的金币（只涨不跌，花钱/被偷不影响），决定等级，见 calcLevel()
 *   learnedRecipes: [ 菜谱名, ... ]   已解锁的菜谱，新玩家只有 STARTER_RECIPES；其余靠「看电视」解锁
 *   lastTvDay                  上次「看电视」的虚拟日，每天只能看一次
 *   lastFishAt                 上次钓鱼时间戳
 *   stealDay / stealCount      偷菜每日限次计数（stealDay 是游戏虚拟日，不是现实日期）
 *   plantedCrops / caughtFish  终身种过的作物名 / 钓到过的鱼名（去重数组），只用于成就墙统计
 *   lifetimeGifts / lifetimeSteals   终身送礼/偷菜次数（不像stealCount那样每天重置），只用于成就墙
 *   banner                     自定义招牌文字，纯观赏
 *   equippedDecoration         佩戴中的徽记（emoji，见 DECORATIONS），纯观赏
 *
 * Plot:
 *   crop            作物名（CROPS 的 key）
 *   plantedAt       种下时间戳
 *   matureAt        成熟时间戳
 *   notified        是否已经提醒过成熟
 *   lastWateredAt   上次浇水时间戳（浇水冷却用）
 *   groupId         种下时所在的群——成熟提醒、被偷通知都发到这个群，不受你之后跑去别的群操作影响
 *
 * AnimalState: { count, pool, nextAt, groupId }
 *   groupId 是最近一次"买动物"这个类型时所在的群，产出提醒发到这个群。
 *
 * Facility（酒窖/厨房共用结构）: { unlocked, slots: [ null | Slot, ... ] }
 *   Slot: { output, value, readyAt, notified, groupId }
 *   output/value 在开始酿酒/做饭那一刻就算好锁定，不受之后市场浮动影响；
 *   groupId 是开始那一刻所在的群，完成提醒发到这个群（跟 Plot 的路由规则一致）。
 *   成品到期后「收酒」「出锅」不再直接换钱，而是存进 goods 仓库，靠「卖成品」/「送礼」处理。
 *
 * 日历：全群共用一套虚拟历法，SEASON_DAYS 天一季，四季循环。
 * 已经种下的作物即使跨季也会正常长成（不会因换季枯死），
 * 只是「种地」时只能选当前季节能种的作物。
 *
 * 天气与市场：每个虚拟日只在第一次被访问时（定时器或任意指令）重新生成一次，
 * 之后同一天内保持不变。天气生态联动：雨天免费帮所有玩家的生长中作物浇一次水
 * + 钓鱼空军率减半；晴天动物产出 ×SUNNY_ANIMAL_BOOST。
 *
 * 节日：每次真正"换季"（不含插件冷启动那次基准记录）时，定时器给所有已存档的
 * 玩家发一笔节日礼金，并给每个出现过的群各推一条节日公告。
 *
 * 主线：新玩家继承长露谷时背 DEBT_INITIAL 金币欠款，用「还债」还清即可——没有期限、不计利息，
 * 慢慢赚慢慢还都行。真正的长线目标是等级：totalEarned（终身累计赚取金币，只涨不跌）决定 1~100
 * 级，每个等级对应一个称号，Lv.100 是"世界首富"。所有赚钱的地方都要经过 earnCoins()，
 * 不要绕过去直接 p.coins += x，否则升级会算不准。
 */

let ext = seal.ext.find('changri_farm');
if (!ext) {
    ext = seal.ext.new('changri_farm', '长日将尽', '2.4.1');
    seal.ext.register(ext);
    ext.autoActive = true;
}
ext.autoActive = true;

// ========================
// 配置：基础
// ========================

const START_COINS = 30;
const BASE_PLOTS = 4;
const MAX_PLOTS = 8;
const EXPAND_BASE_COST = 50;
const EXPAND_STEP_COST = 40;

const WATER_COOLDOWN = 2 * 60 * 60 * 1000;   // 每块地浇水冷却 2 小时
const WATER_BOOST_RATIO = 0.2;               // 浇一次减少 20% 剩余生长时间

const STEAL_SHARE = 0.4;
const STEAL_DAILY_LIMIT = 3;

// ========================
// 配置：地牢（星露谷矿井风格）—— 单指令=下探一层，回合制自动结算，不做逐回合直播文本，
// 每层结果都控制在几百字节以内，避免重蹈"农场帮助"那条超长消息被平台静默丢弃的覆辙。
// ========================

const DUNGEON_DAILY_FLOOR_LIMIT = 5;   // 每天最多下探的层数（不是"进入地牢"的次数，是层数预算）
const DUNGEON_CHECKPOINT_INTERVAL = 5; // 每5层一个电梯存档点，参照星露谷矿井
const DUNGEON_MAX_FLOOR = 30;          // 目前开放到第30层（6个存档点），后续可加深
const DUNGEON_EVENT_CHANCE = 0.15;     // 不打斗、直接挖到矿脉/宝箱的概率
const DUNGEON_MAX_ROUNDS = 15;         // 单场战斗回合数上限，防止极端情况下死循环/消息过长
const DUNGEON_HIT_CHANCE = 0.9;
const DUNGEON_CRIT_CHANCE = 0.1;
const DUNGEON_CRIT_MULT = 1.5;

// 玩家战斗力直接从等级派生，不单独做装备/加点系统——跟"等级是唯一成长轴"的整体设计保持一致。
const DUNGEON_BASE_HP = 40;
const DUNGEON_HP_PER_LEVEL = 3;
const DUNGEON_BASE_ATK = 6;
const DUNGEON_ATK_PER_LEVEL = 0.6;

// 怪物按楼层区间分桶，越深越强，每个桶对应一个存档点区间。
const DUNGEON_MONSTER_TIERS = [
    { maxFloor: 5, names: ['史莱姆', '洞穴蝙蝠'], hp: 18, atk: 4, coinMin: 8, coinMax: 18 },
    { maxFloor: 10, names: ['骷髅兵', '巨型蜘蛛'], hp: 34, atk: 7, coinMin: 15, coinMax: 32 },
    { maxFloor: 15, names: ['石头人', '毒沼史莱姆'], hp: 55, atk: 11, coinMin: 26, coinMax: 55 },
    { maxFloor: 20, names: ['幽灵', '熔岩蟹'], hp: 82, atk: 16, coinMin: 42, coinMax: 85 },
    { maxFloor: 25, names: ['暗影骑士', '冰霜巨魔'], hp: 115, atk: 22, coinMin: 65, coinMax: 130 },
    { maxFloor: 30, names: ['深渊守卫', '远古巨龙'], hp: 160, atk: 30, coinMin: 100, coinMax: 200 },
];

// 稀有材料掉落表：金币每次通关都有，这个是叠加在金币之上的小概率额外收获，
// 挖矿事件和打赢怪物都会roll一次。走现有 goods 仓库，靠「卖成品」「送礼」流通，
// 不需要新开指令或新的仓库字段（value 在 goodsValue() 里查）。
const DUNGEON_LOOT = {
    '粗糙矿石': { value: 15, chance: 0.12 },
    '闪光矿石': { value: 45, chance: 0.045 },
    '幽晶石': { value: 130, chance: 0.012 },
    '龙鳞碎片': { value: 350, chance: 0.003 },
};
const DUNGEON_LOOT_NAMES = Object.keys(DUNGEON_LOOT);

function newDungeonState() {
    return { floor: 0, hp: null, bestFloor: 0, day: null, floorsToday: 0, lifetimeRuns: 0 };
}

function dungeonPlayerStats(p) {
    const level = calcLevel(p.totalEarned);
    return {
        maxHp: DUNGEON_BASE_HP + level * DUNGEON_HP_PER_LEVEL,
        atk: DUNGEON_BASE_ATK + level * DUNGEON_ATK_PER_LEVEL,
    };
}

function dungeonMonsterFor(floor) {
    const tier = DUNGEON_MONSTER_TIERS.find(t => floor <= t.maxFloor) || DUNGEON_MONSTER_TIERS[DUNGEON_MONSTER_TIERS.length - 1];
    const name = tier.names[Math.floor(Math.random() * tier.names.length)];
    return { name, hp: tier.hp, atk: tier.atk, coinMin: tier.coinMin, coinMax: tier.coinMax };
}

function rollDungeonLoot() {
    const r = Math.random();
    let cum = 0;
    for (const name of DUNGEON_LOOT_NAMES) {
        cum += DUNGEON_LOOT[name].chance;
        if (r < cum) return name;
    }
    return null;
}

// 双方轮流攻击直到一方倒下或回合数封顶（封顶视为玩家见势不妙撤退，不算失败也没有收获）。
// playerCombat.hp 传入的是"这一轮探险剩余的HP"，不是满血——层与层之间不自动回血，
// 只有开新一轮下潜（新的一天/力竭之后）才会回满，这是刻意保留的张力，参照星露谷矿井。
function resolveDungeonBattle(playerCombat, monster) {
    let pHp = playerCombat.hp;
    let mHp = monster.hp;
    let rounds = 0;
    while (pHp > 0 && mHp > 0 && rounds < DUNGEON_MAX_ROUNDS) {
        rounds++;
        if (Math.random() < DUNGEON_HIT_CHANCE) {
            const crit = Math.random() < DUNGEON_CRIT_CHANCE;
            mHp -= Math.round(playerCombat.atk * (crit ? DUNGEON_CRIT_MULT : 1));
        }
        if (mHp <= 0) break;
        if (Math.random() < DUNGEON_HIT_CHANCE) {
            const crit = Math.random() < DUNGEON_CRIT_CHANCE;
            pHp -= Math.round(monster.atk * (crit ? DUNGEON_CRIT_MULT : 1));
        }
    }
    if (mHp <= 0) return { win: true, fled: false, roundsUsed: rounds, playerHpLeft: Math.max(0, pHp) };
    if (pHp <= 0) return { win: false, fled: false, roundsUsed: rounds, playerHpLeft: 0 };
    return { win: false, fled: true, roundsUsed: rounds, playerHpLeft: Math.max(0, pHp) };
}

// ========================
// 配置：四季日历 / 天气 / 市场
// ========================

const DAY_MS = 24 * 60 * 60 * 1000;
const SEASON_DAYS = 5;                 // 每季 5 天（现实时间）
const SEASONS = ['春', '夏', '秋', '冬'];
const RAIN_CHANCE = 0.3;
const MARKET_MIN_MULT = 0.8;
const MARKET_MAX_MULT = 1.3;

const FESTIVALS = {
    '春': { name: '春耕祭', desc: '万物复苏，农场主们互相赠送种子迎接新一季。', bonus: 20 },
    '夏': { name: '丰水节', desc: '雨水充沛的季节到来，河水上涨，鱼群格外活跃。', bonus: 20 },
    '秋': { name: '丰收祭', desc: '稻谷飘香的季节，集市上人声鼎沸。', bonus: 20 },
    '冬': { name: '藏冬节', desc: '天寒地冻，农场主们围炉夜话，互赠年货。', bonus: 20 },
};

// ========================
// 配置：作物
// ========================

// 平衡公式（改/加作物时按这个套，别再拍脑袋写 sell）：
//   时薪(growHours) = 14 + 1.2 × min(growHours, 6)     ← 越慢时薪越高，6小时后封顶，避免长作物收益失控
//   sell = cost + 时薪 × growHours，四舍五入取整
// 这样同一季里每种作物都落在约 14~21 金/小时区间，快作物省时间、慢作物省操作次数+时薪略高，
// 不会出现"越贵越亏"（v1.3.0 曾经的问题：玉米11.5/h、西瓜11/h 全面输给便宜的番茄/辣椒16/h）。
const CROPS = {
    // 春
    '萝卜': { season: '春', cost: 3, growMs: 20 * 60 * 1000, sell: 8 },
    '豌豆': { season: '春', cost: 4, growMs: 30 * 60 * 1000, sell: 11 },
    '韭菜': { season: '春', cost: 5, growMs: 25 * 60 * 1000, sell: 11 },
    '土豆': { season: '春', cost: 6, growMs: 45 * 60 * 1000, sell: 17 },
    '芦笋': { season: '春', cost: 6, growMs: 35 * 60 * 1000, sell: 15 },
    '洋葱': { season: '春', cost: 9, growMs: 1 * 60 * 60 * 1000, sell: 24 },
    '樱桃': { season: '春', cost: 20, growMs: 2 * 60 * 60 * 1000, sell: 53 },
    '草莓': { season: '春', cost: 15, growMs: 1.5 * 60 * 60 * 1000, sell: 39 },
    // 夏
    '秋葵': { season: '夏', cost: 6, growMs: 35 * 60 * 1000, sell: 15 },
    '黄瓜': { season: '夏', cost: 7, growMs: 40 * 60 * 1000, sell: 17 },
    '茄子': { season: '夏', cost: 9, growMs: 50 * 60 * 1000, sell: 22 },
    '番茄': { season: '夏', cost: 10, growMs: 1 * 60 * 60 * 1000, sell: 25 },
    '辣椒': { season: '夏', cost: 16, growMs: 1.5 * 60 * 60 * 1000, sell: 40 },
    '玉米': { season: '夏', cost: 12, growMs: 2 * 60 * 60 * 1000, sell: 45 },
    '蓝莓': { season: '夏', cost: 30, growMs: 3 * 60 * 60 * 1000, sell: 83 },
    '西瓜': { season: '夏', cost: 50, growMs: 10 * 60 * 60 * 1000, sell: 262 },
    // 秋
    '花生': { season: '秋', cost: 7, growMs: 45 * 60 * 1000, sell: 18 },
    '红薯': { season: '秋', cost: 8, growMs: 1 * 60 * 60 * 1000, sell: 23 },
    '高粱': { season: '秋', cost: 18, growMs: 3 * 60 * 60 * 1000, sell: 71 },
    '南瓜': { season: '秋', cost: 25, growMs: 5 * 60 * 60 * 1000, sell: 125 },
    '苹果': { season: '秋', cost: 28, growMs: 4 * 60 * 60 * 1000, sell: 103 },
    '葡萄': { season: '秋', cost: 32, growMs: 4.5 * 60 * 60 * 1000, sell: 119 },
    '栗子': { season: '秋', cost: 35, growMs: 7 * 60 * 60 * 1000, sell: 183 },
    '核桃': { season: '秋', cost: 40, growMs: 6 * 60 * 60 * 1000, sell: 167 },
    // 冬
    '白菜': { season: '冬', cost: 4, growMs: 30 * 60 * 1000, sell: 11 },
    '大葱': { season: '冬', cost: 5, growMs: 40 * 60 * 1000, sell: 15 },
    '冬枣': { season: '冬', cost: 7, growMs: 50 * 60 * 1000, sell: 20 },
    '冬笋': { season: '冬', cost: 9, growMs: 1.25 * 60 * 60 * 1000, sell: 28 },
    '山药': { season: '冬', cost: 12, growMs: 1.5 * 60 * 60 * 1000, sell: 36 },
    '荸荠': { season: '冬', cost: 16, growMs: 2.5 * 60 * 60 * 1000, sell: 59 },
    '甘蔗': { season: '冬', cost: 20, growMs: 3 * 60 * 60 * 1000, sell: 73 },
    '芋头': { season: '冬', cost: 22, growMs: 4 * 60 * 60 * 1000, sell: 97 },
};
const CROP_NAMES = Object.keys(CROPS);

function cropsInSeason(season) { return CROP_NAMES.filter(n => CROPS[n].season === season); }

// ========================
// 配置：养殖
// ========================

const ANIMALS = {
    '鸡': { emoji: '🐔', cost: 15, interval: 90 * 60 * 1000, price: 6, cap: 6, product: '蛋', collectCmd: '捡蛋', collectVerb: '捡' },
    '羊': { emoji: '🐑', cost: 40, interval: 4 * 60 * 60 * 1000, price: 22, cap: 4, product: '羊毛', collectCmd: '剪羊毛', collectVerb: '剪' },
    '牛': { emoji: '🐄', cost: 70, interval: 6 * 60 * 60 * 1000, price: 40, cap: 3, product: '牛奶', collectCmd: '挤牛奶', collectVerb: '挤' },
};
const ANIMAL_NAMES = Object.keys(ANIMALS);

// ========================
// 配置：钓鱼
// ========================

// v1.3.0 的数值期望收益≈23.4金/次（30分钟冷却≈46.9金/小时），零成本零风险，
// 完爆种地/养殖（最好的作物也就~20金/小时还要占地/占养殖位）。这里整体砍到期望≈7.8金/次
// （≈15.5金/小时），跟作物的 14~21金/小时区间对齐，钓鱼保留"小概率大奖"的爽感但不再是最优解。
const FISH_COOLDOWN = 30 * 60 * 1000;
const FISH_EMPTY_CHANCE = 0.25;
const FISH_TABLE = [
    { name: '小鱼干', chance: 0.30, min: 1, max: 3 },
    { name: '鲫鱼', chance: 0.25, min: 3, max: 6 },
    { name: '鲤鱼', chance: 0.18, min: 5, max: 11 },
    { name: '草鱼', chance: 0.12, min: 9, max: 16 },
    { name: '鲈鱼', chance: 0.08, min: 14, max: 25 },
    { name: '锦鲤', chance: 0.05, min: 28, max: 53 },
    { name: '金色锦鲤', chance: 0.02, min: 70, max: 140 },
];

function rollFish() {
    const r = Math.random();
    let cum = 0;
    for (const f of FISH_TABLE) {
        cum += f.chance;
        if (r < cum) return f;
    }
    return FISH_TABLE[FISH_TABLE.length - 1];
}
function randInt(min, max) { return min + Math.floor(Math.random() * (max - min + 1)); }

// ========================
// 配置：加工（酒窖 / 厨房）—— 后期内容，把种地/养殖的产出深加工成更值钱的成品
// ========================

// 原料仓库：收菜/捡蛋/剪羊毛/挤牛奶时，除了照常拿金币，还会额外攒 1 份同名原料到 p.ingredients，
// 专门喂给下面两个加工站用，不影响、不占用现有的卖钱流程。

// 酒窖：任意作物都能酿，耗时按该作物生长时间的倍数算，产出价值也按基准售价的倍数算——
// 慢工出细活，越贵的作物酿出来的酒越值钱，但也压得更久。
const BREWERY_UNLOCK_COST = 150;   // 建酒窖一次性花费（送1个酒桶槽位）
const BARREL_BASE_COST = 80;       // 之后每加一个酒桶槽位的起步价
const BARREL_STEP_COST = 40;       // 每多买一个再涨这么多
const MAX_BARRELS = 4;
const WINE_TIME_MULT = 4;          // 酿造耗时 = 作物 growMs × 4
const WINE_VALUE_MULT = 3;         // 成酒价值 = 作物基准 sell × 3（不受市场浮动影响，锁定在酿造那一刻的基准价）

// 厨房：固定菜谱，可能要凑好几种原料，产出比原料价值高但不像酒窖那样跟生长时间挂钩，
// 定位是"轻量转化"——公式：菜谱产出 ≈ 所需原料的基准总值 × 2.2，cookMs 按需要的原料贵贱手动调。
const KITCHEN_UNLOCK_COST = 60;    // 建厨房一次性花费（送1个灶台槽位）
const STOVE_BASE_COST = 35;        // 之后每加一个灶台槽位的起步价
const STOVE_STEP_COST = 20;
const MAX_STOVES = 4;

// 只有这两道是新玩家一开始就会的，其余菜谱要靠「看电视」慢慢解锁——
// 见下方"看电视"配置和 p.learnedRecipes。
const STARTER_RECIPES = ['煎蛋', '田园浓汤'];

const RECIPES = {
    '煎蛋':       { need: { '蛋': 1 },                                     cookMs: 10 * 60 * 1000, value: 14 },
    '田园浓汤':   { need: { '萝卜': 1, '土豆': 1 },                         cookMs: 20 * 60 * 1000, value: 55 },
    '咸味饼干':   { need: { '面粉': 1, '盐': 1 },                           cookMs: 15 * 60 * 1000, value: 29 },
    '甜面包':     { need: { '面粉': 2, '糖': 1 },                           cookMs: 30 * 60 * 1000, value: 57 },
    '奶酪':       { need: { '牛奶': 1 },                                    cookMs: 30 * 60 * 1000, value: 88 },
    '面包':       { need: { '面粉': 2, '蛋': 1 },                           cookMs: 40 * 60 * 1000, value: 48 },
    '羊毛毯':     { need: { '羊毛': 2 },                                    cookMs: 45 * 60 * 1000, value: 97 },
    '果酱':       { need: { '草莓': 1, '糖': 1 },                           cookMs: 25 * 60 * 1000, value: 108 },
    '蔬菜沙拉':   { need: { '萝卜': 1, '番茄': 1, '黄瓜': 1 },               cookMs: 25 * 60 * 1000, value: 110 },
    '香草冰淇淋': { need: { '牛奶': 1, '糖': 1, '香料': 1 },                 cookMs: 60 * 60 * 1000, value: 150 },
    '农场大餐':   { need: { '蛋': 1, '牛奶': 1, '羊毛': 1 },                 cookMs: 90 * 60 * 1000, value: 150 },
    '蛋糕':       { need: { '面粉': 2, '糖': 2, '蛋': 2, '牛奶': 1 },        cookMs: 2 * 60 * 60 * 1000, value: 194 },
    '巧克力蛋糕': { need: { '巧克力': 2, '面粉': 2, '蛋': 1, '牛奶': 1 },    cookMs: 2 * 60 * 60 * 1000, value: 246 },
    '南瓜派':     { need: { '南瓜': 1, '面粉': 1, '糖': 1 },                 cookMs: 2.5 * 60 * 60 * 1000, value: 315 },
    '长露谷盛宴': { need: { '蛋': 2, '牛奶': 2, '面粉': 2, '糖': 2, '巧克力': 1, '香料': 1 }, cookMs: 3 * 60 * 60 * 1000, value: 376 },
    '奶油浓汤':   { need: { '奶油': 1, '土豆': 1, '萝卜': 1 },               cookMs: 30 * 60 * 1000, value: 86 },
    '酵母面包卷': { need: { '面粉': 2, '酵母': 1 },                          cookMs: 35 * 60 * 1000, value: 55 },
    '樱桃酱':     { need: { '樱桃': 1, '糖': 1 },                            cookMs: 30 * 60 * 1000, value: 139 },
    '蜜烤山药':   { need: { '山药': 1, '蜂蜜': 1 },                          cookMs: 35 * 60 * 1000, value: 112 },
    '香草布丁':   { need: { '牛奶': 1, '香草': 1, '糖': 1 },                 cookMs: 60 * 60 * 1000, value: 154 },
    '蓝莓松饼':   { need: { '蓝莓': 1, '面粉': 1, '蛋': 1 },                 cookMs: 90 * 60 * 1000, value: 213 },
    '苹果挞':     { need: { '苹果': 1, '面粉': 1, '奶油': 1 },               cookMs: 2 * 60 * 60 * 1000, value: 275 },
    '葡萄司康':   { need: { '葡萄': 1, '面粉': 1, '奶油': 1 },               cookMs: 2 * 60 * 60 * 1000, value: 310 },
    '核桃派':     { need: { '核桃': 1, '面粉': 1, '蜂蜜': 1 },               cookMs: 2.5 * 60 * 60 * 1000, value: 418 },
    '丰收盛宴':   { need: { '苹果': 1, '葡萄': 1, '核桃': 1, '蜂蜜': 1, '奶油': 1 }, cookMs: 4 * 60 * 60 * 1000, value: 920 },
};
const RECIPE_NAMES = Object.keys(RECIPES);

function fmtIngredients(need) {
    return Object.entries(need).map(([n, c]) => `${n}×${c}`).join('+');
}

// ========================
// 配置：商店（直接花钱买原料，比自己种/养贵；镇上限定的原料只能这里买）
// ========================

const SHOP_MARKUP = 1.8; // 商店直接买"农场也产得出"的原料，价格=基准值×1.8

// 这几样纯粹是"镇上才有"的原料，种地/养殖永远拿不到，只能靠商店——
// 部分高级菜谱（蛋糕/南瓜派等）刻意设计成必须来商店一趟才能凑齐。
const TOWN_INGREDIENTS = {
    '面粉': 8,
    '糖': 10,
    '盐': 5,
    '酵母': 9,
    '奶油': 14,
    '蜂蜜': 15,
    '香料': 18,
    '香草': 20,
    '巧克力': 25,
};
const TOWN_INGREDIENT_NAMES = Object.keys(TOWN_INGREDIENTS);

// 农产原料（作物/养殖产出）的商店加价价格；镇上限定原料直接查表。
// 查不到就是这样东西没法在商店买（比如已经酿好的酒/做好的菜，那些走「卖成品」「送礼」）。
function shopPrice(name) {
    if (TOWN_INGREDIENTS[name] != null) return TOWN_INGREDIENTS[name];
    if (CROPS[name]) return Math.round(CROPS[name].sell * SHOP_MARKUP);
    const animalCfg = Object.values(ANIMALS).find(a => a.product === name);
    if (animalCfg) return Math.round(animalCfg.price * SHOP_MARKUP);
    return null;
}

// ========================
// 配置：看电视（每天一次，有几率解锁新菜谱）
// ========================

const TV_LEARN_CHANCE = 0.4;

// 成品（酒/菜）的单价始终能从静态配置反推出来（酒=对应作物基准sell×WINE_VALUE_MULT，
// 菜=RECIPES 里写死的 value），不受市场浮动影响，所以不需要每份成品单独存价格，
// p.goods 只要存 { 物品名: 数量 } 就够了，卖/送礼时现算现用。
function goodsValue(itemName) {
    if (RECIPES[itemName]) return RECIPES[itemName].value;
    if (DUNGEON_LOOT[itemName]) return DUNGEON_LOOT[itemName].value;
    if (itemName.endsWith('酒')) {
        const crop = CROPS[itemName.slice(0, -1)];
        if (crop) return Math.round(crop.sell * WINE_VALUE_MULT);
    }
    return 0;
}

// ========================
// 配置：主线 —— 继承长露谷时背的欠款，没有期限也不计利息，什么时候还清都行
// ========================

const DEBT_INITIAL = 500;

// ========================
// 配置：等级 —— 靠"这辈子一共赚过多少钱"（不是当前手里的钱）升级，1~100级，
// 终点是"世界首富"的成就感。花钱、被偷都不会掉级，等级只涨不跌。
// ========================

const MAX_LEVEL = 100;
const LEVEL_BASE = 50;
const LEVEL_EXP = 2.2; // 门槛=LEVEL_BASE×等级^LEVEL_EXP，越往后越难，参考数值见 levelThreshold 注释

// 称号按等级区间分档，只是身份的展示，不解锁任何数值特权——纯粹的成就感/面子系统
const LEVEL_TITLES = [
    { min: 1, max: 4, title: '破产农场主' },
    { min: 5, max: 9, title: '温饱线农场主' },
    { min: 10, max: 19, title: '小有积蓄的农场主' },
    { min: 20, max: 29, title: '小镇殷实户' },
    { min: 30, max: 39, title: '远近闻名的富农' },
    { min: 40, max: 49, title: '长露谷首富' },
    { min: 50, max: 59, title: '郡里的大地主' },
    { min: 60, max: 69, title: '商会座上宾' },
    { min: 70, max: 79, title: '一方巨贾' },
    { min: 80, max: 89, title: '富可敌国' },
    { min: 90, max: 99, title: '传奇富豪' },
    { min: 100, max: 100, title: '世界首富' },
];

// 门槛示例（供设计参考）：Lv2≈230，Lv10≈7930，Lv50≈397150，Lv100≈1990500 累计赚取金币。
function levelThreshold(level) {
    if (level <= 1) return 0;
    return Math.round(LEVEL_BASE * Math.pow(level, LEVEL_EXP));
}
function calcLevel(totalEarned) {
    let level = 1;
    while (level < MAX_LEVEL && totalEarned >= levelThreshold(level + 1)) level++;
    return level;
}
function levelTitle(level) {
    return (LEVEL_TITLES.find(t => level >= t.min && level <= t.max) || LEVEL_TITLES[0]).title;
}

// 所有"赚钱"的地方都要经过这个函数，而不是直接 p.coins += x —— 这样 totalEarned（终身累计收入，
// 只涨不跌，花钱/被偷都不影响）才能真实反映等级进度。返回值：升级了就是新等级，没升级是 null。
function earnCoins(p, amount) {
    if (!p.totalEarned) p.totalEarned = 0;
    const beforeLevel = calcLevel(p.totalEarned);
    p.coins += amount;
    p.totalEarned += amount;
    const afterLevel = calcLevel(p.totalEarned);
    return afterLevel > beforeLevel ? afterLevel : null;
}
function levelUpHint(newLevel) {
    return newLevel ? `\n\n🎉 升级了！现在是 Lv.${newLevel} ${levelTitle(newLevel)}！` : '';
}

// ========================
// 配置：成就墙 —— 汇总种地/养殖/钓鱼/加工/主线各系统的里程碑，check() 现算现查，
// 不需要单独存"是否已解锁"（都是基于永久递增的统计量，不会掉成就）。
// ========================

function seasonsCovered(p) {
    const seasons = new Set((p.plantedCrops || []).map(c => CROPS[c] && CROPS[c].season).filter(Boolean));
    return seasons.size;
}

const ACHIEVEMENTS = [
    { id: 'harvest1', name: '初次丰收', desc: '种下第一株作物', check: p => (p.plantedCrops || []).length >= 1 },
    { id: 'season3', name: '三季务农', desc: '在3个不同季节种过作物', check: p => seasonsCovered(p) >= 3 },
    { id: 'season4', name: '四季轮回', desc: '春夏秋冬都种过作物', check: p => seasonsCovered(p) >= 4 },
    { id: 'crop16', name: '作物收藏家', desc: '种过16种以上作物', check: p => (p.plantedCrops || []).length >= 16 },
    { id: 'cropAll', name: '全能农夫', desc: `种过全部${CROP_NAMES.length}种作物`, check: p => (p.plantedCrops || []).length >= CROP_NAMES.length },
    { id: 'ranch1', name: '小小牧场主', desc: '同时养过鸡、羊、牛', check: p => ANIMAL_NAMES.every(t => p.animals[t].count > 0) },
    { id: 'ranchFull', name: '满编牧场', desc: '任意一种动物养到上限', check: p => ANIMAL_NAMES.some(t => p.animals[t].count >= ANIMALS[t].cap) },
    { id: 'fish1', name: '渔夫初体验', desc: '钓到第一条鱼', check: p => (p.caughtFish || []).length >= 1 },
    { id: 'fishAll', name: '钓鱼收藏家', desc: `钓到全部${FISH_TABLE.length}种鱼`, check: p => (p.caughtFish || []).length >= FISH_TABLE.length },
    { id: 'brewery', name: '酒庄老板', desc: '建好酒窖', check: p => p.brewery.unlocked },
    { id: 'kitchenOpen', name: '厨房初开张', desc: '建好厨房', check: p => p.kitchen.unlocked },
    { id: 'chefAll', name: '大厨传人', desc: `学会全部${RECIPE_NAMES.length}道菜谱`, check: p => p.learnedRecipes.length >= RECIPE_NAMES.length },
    { id: 'gift1', name: '乐于助人', desc: '送过一次礼物', check: p => (p.lifetimeGifts || 0) >= 1 },
    { id: 'steal1', name: '顺手牵羊', desc: '偷过一次菜', check: p => (p.lifetimeSteals || 0) >= 1 },
    { id: 'debtFree', name: '脱离贫困', desc: '还清欠款', check: p => p.debt.paidOff },
    { id: 'lv10', name: '小有所成', desc: '达到 Lv.10', check: p => calcLevel(p.totalEarned) >= 10 },
    { id: 'lv50', name: '一方巨贾', desc: '达到 Lv.50', check: p => calcLevel(p.totalEarned) >= 50 },
    { id: 'lv100', name: '世界首富', desc: '达到 Lv.100', check: p => calcLevel(p.totalEarned) >= 100 },
];

// ========================
// 配置：家园装饰 —— 纯观赏，跟经济数值无关。徽记按成就/等级解锁，招牌是自定义文字。
// ========================

const DEFAULT_DECORATION = '🌱';
const BANNER_MAX_LEN = 12;

const DECORATIONS = {
    '🌱': { name: '新手徽记', hint: '新玩家默认拥有', unlock: () => true },
    '💰': { name: '脱贫纪念章', hint: '还清欠款', unlock: p => p.debt.paidOff },
    '🎣': { name: '渔夫徽记', hint: `钓到全部${FISH_TABLE.length}种鱼`, unlock: p => (p.caughtFish || []).length >= FISH_TABLE.length },
    '🌾': { name: '全能农夫徽记', hint: `种过全部${CROP_NAMES.length}种作物`, unlock: p => (p.plantedCrops || []).length >= CROP_NAMES.length },
    '🍷': { name: '酒庄徽记', hint: '建好酒窖', unlock: p => p.brewery.unlocked },
    '🍳': { name: '大厨徽记', hint: `学会全部${RECIPE_NAMES.length}道菜谱`, unlock: p => p.learnedRecipes.length >= RECIPE_NAMES.length },
    '👑': { name: '首富勋章', hint: `达到 Lv.${MAX_LEVEL}`, unlock: p => calcLevel(p.totalEarned) >= MAX_LEVEL },
};
const DECORATION_EMOJIS = Object.keys(DECORATIONS);

// ========================
// 配置：天气生态联动 —— 让天气不只是"能不能免费浇水"，也牵动钓鱼和养殖
// ========================

const RAIN_FISH_EMPTY_MULT = 0.5;  // 雨天钓鱼空军概率 ×0.5（河水上涨，鱼更活跃）
const SUNNY_ANIMAL_BOOST = 1.2;    // 晴天动物产出 ×1.2（放牧心情好），向上取整

// ========================
// 日历 / 天气 / 市场
// ========================

function getEpoch() {
    let raw = ext.storageGet('farm_epoch');
    let epoch = parseInt(raw);
    if (!raw || isNaN(epoch)) {
        epoch = Date.now();
        ext.storageSet('farm_epoch', String(epoch));
    }
    return epoch;
}

function currentDayIndex() {
    return Math.floor((Date.now() - getEpoch()) / DAY_MS);
}

function getCalendar() {
    const dayIndex = currentDayIndex();
    const yearLen = SEASONS.length * SEASON_DAYS;
    const dayInYear = ((dayIndex % yearLen) + yearLen) % yearLen;
    const year = Math.floor(dayIndex / yearLen) + 1;
    const seasonIdx = Math.floor(dayInYear / SEASON_DAYS);
    const dayInSeason = (dayInYear % SEASON_DAYS) + 1;
    return {
        year, season: SEASONS[seasonIdx], seasonIdx,
        dayInSeason, daysLeftInSeason: SEASON_DAYS - dayInSeason + 1,
    };
}

function rollWeather() { return Math.random() < RAIN_CHANCE ? '雨' : '晴'; }
function rollPrices() {
    const prices = {};
    CROP_NAMES.forEach(n => {
        prices[n] = Math.round((MARKET_MIN_MULT + Math.random() * (MARKET_MAX_MULT - MARKET_MIN_MULT)) * 100) / 100;
    });
    return prices;
}

// 读取/推进全局天气与市场行情。每个虚拟日第一次被访问（无论是定时器还是任意指令）
// 都会重新生成一次，之后同一天内保持不变，避免每次操作价格都在变。
function getWorld() {
    const dayIndex = currentDayIndex();
    let world;
    try { world = JSON.parse(ext.storageGet('farm_world') || 'null'); } catch { world = null; }
    if (!world || world.dayIndex !== dayIndex) {
        world = { dayIndex, weather: rollWeather(), prices: rollPrices(), rainApplied: false };
        ext.storageSet('farm_world', JSON.stringify(world));
    }
    return world;
}
function saveWorld(w) { ext.storageSet('farm_world', JSON.stringify(w)); }

function sellPrice(cropName, world) {
    const base = CROPS[cropName].sell;
    const mult = (world.prices && world.prices[cropName]) || 1;
    return Math.max(1, Math.round(base * mult));
}

// 检查是否发生了"换季"，是的话给所有存档玩家发节日礼金、并给每个出现过的群推一条公告。
// 插件冷启动时（还没有任何基准记录）只记基准，不当成一次换季，避免刚装上就误触发节日。
// 返回值表示 data 是否被改动（玩家金币变化），供调用方决定是否需要 saveData。
function checkFestival(data, eps) {
    const cal = getCalendar();
    const seasonKey = `${cal.year}-${cal.seasonIdx}`;
    const lastKey = ext.storageGet('farm_last_season_key');

    if (!lastKey) {
        ext.storageSet('farm_last_season_key', seasonKey);
        return false;
    }
    if (lastKey === seasonKey) return false;
    ext.storageSet('farm_last_season_key', seasonKey);

    const fest = FESTIVALS[cal.season];
    let changed = false;
    const seenGroups = new Set();

    for (const key in data) {
        // 单条记录处理出错不能中断整批节日发放——一个坏记录不该连累其他人拿不到礼金/收不到公告。
        try {
            const p = data[key];
            earnCoins(p, fest.bonus); // 节日礼金是群发广播，升级提示这里不单独播报，玩家下次查看/赚钱时会看到新等级
            changed = true;

            const platform = key.split(':')[0];
            (p.groups || []).forEach(gid => {
                const gKey = `${platform}|${gid}`;
                if (seenGroups.has(gKey)) return;
                seenGroups.add(gKey);
                pushToGroup(eps, platform, gid,
                    `🎉 ${cal.season}季·${fest.name}\n${fest.desc}\n所有农场主都收到了${fest.bonus}金币的节日礼金！`
                );
            });
        } catch (e) {
            console.error(`[长露谷] 节日发放失败，记录已跳过: ${key}`, e);
        }
    }
    return changed;
}

// ========================
// 存储：玩家数据
// ========================

function getData() {
    try { return JSON.parse(ext.storageGet('farm_data') || '{}'); } catch { return {}; }
}
function saveData(d) { ext.storageSet('farm_data', JSON.stringify(d)); }

function newAnimalState() { return { count: 0, pool: 0, nextAt: null, groupId: null }; }
function newFacility() { return { unlocked: false, slots: [] }; }

function newDebt() {
    return { amount: DEBT_INITIAL, paidOff: false };
}

function newPlayer(roleName, groupId) {
    return {
        roleName, coins: START_COINS,
        groups: groupId ? [groupId] : [],
        plots: Array.from({ length: BASE_PLOTS }, () => null),
        animals: Object.fromEntries(ANIMAL_NAMES.map(n => [n, newAnimalState()])),
        ingredients: {},
        goods: {},
        brewery: newFacility(),
        kitchen: newFacility(),
        debt: newDebt(),
        totalEarned: 0,
        learnedRecipes: [...STARTER_RECIPES],
        lastTvDay: null,
        lastFishAt: null,
        stealDay: null,
        stealCount: 0,
        plantedCrops: [],
        caughtFish: [],
        lifetimeGifts: 0,
        lifetimeSteals: 0,
        banner: '',
        equippedDecoration: DEFAULT_DECORATION,
        dungeon: newDungeonState(),
    };
}

// 多群统一：同一个 platform:uid 全群共用一份农场数据，不会因为换群操作而分裂或被覆盖。
// groupId 只累加进 p.groups（给"农场排行"用），不会覆盖 Plot/AnimalState 各自记录的来源群，
// 这样提醒才能准确回到"种菜那个群"，而不是被后来的其他操作带偏。
function getPlayer(data, key, roleName, groupId) {
    if (!data[key]) data[key] = newPlayer(roleName, groupId);
    const p = data[key];
    if (!p.animals) p.animals = Object.fromEntries(ANIMAL_NAMES.map(n => [n, newAnimalState()]));
    ANIMAL_NAMES.forEach(n => { if (!p.animals[n]) p.animals[n] = newAnimalState(); });
    if (!p.ingredients) p.ingredients = {};
    if (!p.goods) p.goods = {};
    if (!p.brewery) p.brewery = newFacility();
    if (!p.kitchen) p.kitchen = newFacility();
    if (!p.debt) p.debt = newDebt();
    if (p.totalEarned == null) p.totalEarned = 0;
    if (!p.learnedRecipes) p.learnedRecipes = [...STARTER_RECIPES];
    if (!p.plantedCrops) p.plantedCrops = [];
    if (!p.caughtFish) p.caughtFish = [];
    if (p.lifetimeGifts == null) p.lifetimeGifts = 0;
    if (p.lifetimeSteals == null) p.lifetimeSteals = 0;
    if (p.banner == null) p.banner = '';
    if (!p.equippedDecoration) p.equippedDecoration = DEFAULT_DECORATION;
    if (!p.dungeon) p.dungeon = newDungeonState();
    if (!p.groups) p.groups = [];
    if (roleName) p.roleName = roleName;
    if (groupId && !p.groups.includes(groupId)) p.groups.push(groupId);
    return p;
}

function addIngredient(p, name, amount) {
    p.ingredients[name] = (p.ingredients[name] || 0) + amount;
}

// ========================
// 工具
// ========================

function fmtDuration(ms) {
    if (ms <= 0) return '已成熟';
    const m = Math.ceil(ms / 60000);
    if (m < 60) return `${m}分钟`;
    const h = Math.floor(m / 60), r = m % 60;
    return r ? `${h}小时${r}分钟` : `${h}小时`;
}

function keyOf(platform, uid) { return `${platform}:${uid}`; }
function stripUid(raw) { return raw.replace(/^[a-z]+:/i, ''); }
function stripGroup(raw) { return raw.replace(/^[a-z]+-Group:/i, ''); }

function getCtxInfo(msg) {
    const platform = msg.platform;
    const uid = stripUid(msg.sender.userId);
    const groupId = stripGroup(msg.groupId);
    const roleName = msg.sender.nickname || uid;
    return { platform, uid, groupId, roleName, key: keyOf(platform, uid) };
}

// 取出消息里 @ 到的对象，排除机器人自己和发送者本人。
// 注意：很多群要求"@机器人 才能触发指令"，这种情况下消息里第一个 [CQ:at] 其实是机器人，
// 如果只取第一个匹配会把机器人自己当成偷菜目标，必须过滤掉才能拿到真正 @ 的那个人。
function extractAtTargets(ctx, msg) {
    const botUid = ctx && ctx.endPoint && ctx.endPoint.userId ? stripUid(String(ctx.endPoint.userId)) : null;
    const selfUid = stripUid(msg.sender.userId);
    const uids = [...msg.message.matchAll(/\[CQ:at,qq=(\d+)\]/g)].map(m => m[1]);
    return uids.filter(uid => uid !== botUid && uid !== selfUid);
}

function pushToGroup(eps, platform, groupId, text) {
    try {
        let ep = eps.find(e => e.platform === platform && e.state === 1) || eps.find(e => e.state === 1) || eps[0];
        if (!ep) return;
        const m = seal.newMessage();
        m.messageType = 'group';
        m.groupId = `${platform}-Group:${groupId}`;
        const tempCtx = seal.createTempCtx(ep, m);
        seal.replyToSender(tempCtx, m, text);
    } catch (e) { console.error('[长露谷] 推送失败:', e); }
}

// 浇水加速：把剩余生长时间砍掉 WATER_BOOST_RATIO，返回实际砍掉的毫秒数。
// 手动「浇水」和下雨天的免费浇水共用这个函数，区别只在于是否检查冷却。
function applyWaterBoost(pl, now) {
    const remain = pl.matureAt - now;
    const cut = Math.max(0, Math.round(remain * WATER_BOOST_RATIO));
    pl.matureAt -= cut;
    pl.lastWateredAt = now;
    return cut;
}

// ========================
// 指令：农场帮助
// ========================

let cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = '农场帮助';
cmd_help.help = '查看长露谷全部指令';
cmd_help.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    seal.replyToSender(ctx, msg,
        `🌾 长露谷 ⚠️Beta测试版\n${'─'.repeat(16)}\n` +
        `（数值和规则还在调整，遇到问题欢迎反馈）\n\n` +
        `📜 你继承了长露谷，但背着${DEBT_INITIAL}金币的欠款，「还债」还清就真正是你的了（没有期限，慢慢赚慢慢还）。\n` +
        `真正的长期目标是等级：靠终身累计赚的钱升级，1~100级，Lv.100 是"世界首富"——「等级」查看进度。\n\n` +
        `【种地】\n` +
        `农场日历         季节、本季可种作物、实时收购价\n` +
        `种地 作物名     在空地种下当季作物\n` +
        `浇水 [编号]      给作物浇水加速生长，不填编号=浇所有能浇的地\n` +
        `收菜             收获所有成熟作物\n` +
        `扩地             花金币多开一块地（上限${MAX_PLOTS}块，价格逐次上涨）\n` +
        `\n【养殖】\n` +
        `买动物 类型 [数量]  可养：${ANIMAL_NAMES.join('/')}\n` +
        `${ANIMAL_NAMES.map(n => ANIMALS[n].collectCmd).join(' / ')}  收取对应产出换成金币\n` +
        `\n【商店】原料买卖，镇上限定的面粉/糖/盐/香料/巧克力只能这买：\n` +
        `商店             查看能买的原料和价格\n` +
        `买材料 名称 [数量]  花钱买原料（比自己种/养贵）\n` +
        `\n【加工·后期内容】收菜、收取养殖产出时会顺手留一份原料，可以拿去深加工：\n` +
        `建酒窖 / 买酒桶   解锁酿酒、加酒桶槽位（上限${MAX_BARRELS}个）\n` +
        `酿酒 作物名       消耗1份原料酿酒，耗时更长但更值钱\n` +
        `收酒             收好的酒存进成品仓库\n` +
        `建厨房 / 买灶台   解锁做饭、加灶台槽位（上限${MAX_STOVES}个）\n` +
        `农场菜谱 / 菜谱图鉴  已学会的菜谱 / 全部菜谱的收集进度\n` +
        `看电视           每天一次，有几率解锁新菜谱\n` +
        `做饭 菜名 / 出锅   烹饪已学会的菜、做好的菜存进成品仓库\n` +
        `卖成品 [物品名]   把成品仓库里的酒/菜换成金币，不填=全部卖掉\n` +
        `送礼 @群友 物品名  把成品仓库里的酒/菜送给朋友\n` +
        `\n【钓鱼】\n` +
        `钓鱼             随机钓到不同价值的鱼（冷却${Math.round(FISH_COOLDOWN / 60000)}分钟，雨天空军率减半）\n` +
        `\n【市场与天气】\n` +
        `市场行情         查看今天各作物的实时收购价（每天波动）\n` +
        `农场天气         查看今天天气：雨天免费帮全部作物浇一次水+钓鱼空军率减半，晴天养殖产出+20%\n` +
        `\n【主线与社交】\n` +
        `还债 [数量]      偿还欠款，不填数量=尽量还清，没有期限\n` +
        `欠款进度         查看欠款\n` +
        `等级             查看等级、称号，离下一级还差多少（终身累计赚取决定，1~100级）\n` +
        `成就             长露谷成就墙，汇总各系统的收集/里程碑进度\n` +
        `装饰 / 佩戴装饰 表情 / 设置招牌 文字   查看/佩戴徽记，给农场起招牌（纯观赏）\n` +
        `我的农场         地块/养殖/原料/成品/酒窖/厨房/金币/欠款/等级/天气总览\n` +
        `农场排行         本群财富排行榜（前10名，按终身累计赚取排序）\n` +
        `偷菜 @群友       偷取对方成熟未收的作物一部分（每天最多${STEAL_DAILY_LIMIT}次）\n` +
        `地牢入口         长露谷地底似乎藏着什么……（开发中，暂不可进入）\n` +
        `\n每${SEASON_DAYS}天换一季，春夏秋冬循环，作物随季节变化，换季不会枯死。\n` +
        `换季那天全群会有一次节日活动，所有农场主都能收到节日礼金。\n` +
        `新玩家初始 ${START_COINS} 金币、${BASE_PLOTS} 块地。作物成熟、动物产出、酒/菜做好都会主动@你提醒。`
    );
    return ret;
};
ext.cmdMap['农场帮助'] = cmd_help;

// ========================
// 指令：农场日历
// ========================

let cmd_calendar = seal.ext.newCmdItemInfo();
cmd_calendar.name = '农场日历';
cmd_calendar.help = '查看当前年份/季节与本季可种作物';
cmd_calendar.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const cal = getCalendar();
    const world = getWorld();
    const list = cropsInSeason(cal.season);
    seal.replyToSender(ctx, msg,
        `📅 长露谷历\n${'─'.repeat(16)}\n` +
        `第${cal.year}年 · ${cal.season}季 · 第${cal.dayInSeason}/${SEASON_DAYS}天 · 今日${world.weather}\n` +
        `（${cal.daysLeftInSeason}天后进入下一季）\n\n本季可种：\n` +
        list.map(n => `  ${n}  ${fmtDuration(CROPS[n].growMs)}成熟  种子${CROPS[n].cost}金币  收购价${sellPrice(n, world)}金币`).join('\n')
    );
    return ret;
};
ext.cmdMap['农场日历'] = cmd_calendar;

// ========================
// 指令：种地
// ========================

let cmd_plant = seal.ext.newCmdItemInfo();
cmd_plant.name = '种地';
cmd_plant.help = '种地 作物名\n可种作物随季节变化，发送「农场日历」查看当季可种作物';
cmd_plant.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const cropName = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const crop = CROPS[cropName];
    const cal = getCalendar();

    if (!crop) {
        seal.replyToSender(ctx, msg, `没有「${cropName}」这种作物。发送「农场日历」查看本季可种作物。`);
        return ret;
    }
    if (crop.season !== cal.season) {
        seal.replyToSender(ctx, msg,
            `「${cropName}」是${crop.season}季作物，现在是${cal.season}季，种不了。\n发送「农场日历」看看本季能种什么。`
        );
        return ret;
    }

    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.coins < crop.cost) {
        seal.replyToSender(ctx, msg, `金币不够啦！种${cropName}需要${crop.cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    const emptyIdx = p.plots.findIndex(pl => pl === null);
    if (emptyIdx === -1) {
        seal.replyToSender(ctx, msg, `地都种满啦，先「收菜」腾地方，或者「扩地」开新地！`);
        return ret;
    }

    p.coins -= crop.cost;
    const now = Date.now();
    p.plots[emptyIdx] = { crop: cropName, plantedAt: now, matureAt: now + crop.growMs, notified: false, lastWateredAt: null, groupId };
    if (!p.plantedCrops.includes(cropName)) p.plantedCrops.push(cropName); // 成就墙："种过多少种作物"用这个
    saveData(data);

    seal.replyToSender(ctx, msg, `🌱 在第${emptyIdx + 1}块地种下了${cropName}，约${fmtDuration(crop.growMs)}后成熟。\n剩余金币：${p.coins}`);
    return ret;
};
ext.cmdMap['种地'] = cmd_plant;

// ========================
// 指令：浇水
// ========================

let cmd_water = seal.ext.newCmdItemInfo();
cmd_water.name = '浇水';
cmd_water.help = `浇水 [地块编号]\n给作物浇水加速生长，不填编号=浇所有能浇的地（每块地冷却${fmtDuration(WATER_COOLDOWN)}，减少${Math.round(WATER_BOOST_RATIO * 100)}%剩余生长时间）`;
cmd_water.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const now = Date.now();

    if (raw) {
        const idx = parseInt(raw) - 1;
        if (isNaN(idx) || idx < 0 || idx >= p.plots.length) {
            seal.replyToSender(ctx, msg, `没有第${raw}块地。`);
            return ret;
        }
        const pl = p.plots[idx];
        if (!pl) { seal.replyToSender(ctx, msg, `第${idx + 1}块地是空的，没什么好浇的。`); return ret; }
        if (pl.matureAt <= now) { seal.replyToSender(ctx, msg, `第${idx + 1}块地已经成熟了，快去「收菜」吧。`); return ret; }
        if (pl.lastWateredAt && now - pl.lastWateredAt < WATER_COOLDOWN) {
            seal.replyToSender(ctx, msg, `第${idx + 1}块地刚浇过水，${fmtDuration(WATER_COOLDOWN - (now - pl.lastWateredAt))}后才能再浇。`);
            return ret;
        }
        const cut = applyWaterBoost(pl, now);
        saveData(data);
        seal.replyToSender(ctx, msg, `💧 给第${idx + 1}块地的${pl.crop}浇了水，生长时间缩短了${fmtDuration(cut)}，还有${fmtDuration(pl.matureAt - now)}成熟。`);
        return ret;
    }

    let count = 0;
    const names = [];
    p.plots.forEach((pl, i) => {
        if (!pl || pl.matureAt <= now) return;
        if (pl.lastWateredAt && now - pl.lastWateredAt < WATER_COOLDOWN) return;
        applyWaterBoost(pl, now);
        count++;
        names.push(`第${i + 1}块地(${pl.crop})`);
    });

    if (count === 0) {
        seal.replyToSender(ctx, msg, `没有可以浇水的地块（空地/已成熟/冷却中都不行）。`);
        return ret;
    }
    saveData(data);
    seal.replyToSender(ctx, msg, `💧 浇了${count}块地：${names.join('、')}\n发送「我的农场」查看最新进度。`);
    return ret;
};
ext.cmdMap['浇水'] = cmd_water;

// ========================
// 指令：收菜
// ========================

let cmd_harvest = seal.ext.newCmdItemInfo();
cmd_harvest.name = '收菜';
cmd_harvest.help = '收获所有已成熟的作物';
cmd_harvest.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const now = Date.now();
    const world = getWorld();

    let gained = 0;
    const harvested = [];
    p.plots = p.plots.map(pl => {
        if (pl && pl.matureAt <= now) {
            const sell = sellPrice(pl.crop, world);
            gained += sell;
            harvested.push(`${pl.crop}+${sell}`);
            addIngredient(p, pl.crop, 1); // 顺手留1份原料，可以拿去「酿酒」「做饭」深加工
            return null;
        }
        return pl;
    });

    if (harvested.length === 0) {
        seal.replyToSender(ctx, msg, `暂时没有成熟的作物，发送「我的农场」看看进度吧。`);
        return ret;
    }

    const leveledUp = earnCoins(p, gained);
    saveData(data);
    seal.replyToSender(ctx, msg, `🧺 收获了 ${harvested.join('、')}\n共获得 ${gained} 金币，剩余 ${p.coins} 金币。\n（同时留了原料，「我的农场」可查看仓库）${levelUpHint(leveledUp)}`);
    return ret;
};
ext.cmdMap['收菜'] = cmd_harvest;

// ========================
// 指令：扩地
// ========================

let cmd_expand = seal.ext.newCmdItemInfo();
cmd_expand.name = '扩地';
cmd_expand.help = `扩地\n花金币多开一块地（上限${MAX_PLOTS}块，价格逐次上涨）`;
cmd_expand.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.plots.length >= MAX_PLOTS) {
        seal.replyToSender(ctx, msg, `地已经开垦到上限${MAX_PLOTS}块啦！`);
        return ret;
    }
    const extraOwned = p.plots.length - BASE_PLOTS;
    const cost = EXPAND_BASE_COST + extraOwned * EXPAND_STEP_COST;
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `金币不够！扩地需要${cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= cost;
    p.plots.push(null);
    saveData(data);

    seal.replyToSender(ctx, msg, `🧱 开垦了新地块，现在共有${p.plots.length}块地。花费${cost}金币，剩余${p.coins}金币。`);
    return ret;
};
ext.cmdMap['扩地'] = cmd_expand;

// ========================
// 指令：买动物
// ========================

let cmd_buy_animal = seal.ext.newCmdItemInfo();
cmd_buy_animal.name = '买动物';
cmd_buy_animal.help = `买动物 类型 [数量]\n可养：${ANIMAL_NAMES.join('/')}`;
cmd_buy_animal.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const parts = raw.split(/\s+/).filter(Boolean);
    const typeName = parts[0];
    const cfg = ANIMALS[typeName];
    if (!cfg) {
        seal.replyToSender(ctx, msg, `没有「${typeName || ''}」这种动物。可养：${ANIMAL_NAMES.join('、')}`);
        return ret;
    }
    const count = Math.max(1, parseInt(parts[1]) || 1);

    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const st = p.animals[typeName];

    const room = cfg.cap - st.count;
    if (room <= 0) {
        seal.replyToSender(ctx, msg, `${typeName}舍已经养满${cfg.cap}只啦！`);
        return ret;
    }
    const buyCount = Math.min(count, room);
    const cost = buyCount * cfg.cost;
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `金币不够！买${buyCount}只${typeName}需要${cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= cost;
    st.count += buyCount;
    st.groupId = groupId; // 产出提醒推到最近一次买（补充）这个动物时所在的群
    if (!st.nextAt) st.nextAt = Date.now() + cfg.interval;
    saveData(data);

    seal.replyToSender(ctx, msg, `${cfg.emoji} 买了${buyCount}只${typeName}，现在共有${st.count}只。\n剩余金币：${p.coins}`);
    return ret;
};
ext.cmdMap['买动物'] = cmd_buy_animal;

// ========================
// 指令：捡蛋 / 剪羊毛 / 挤牛奶（同一套逻辑，按动物类型生成）
// ========================

function registerCollectCmd(typeName) {
    const cfg = ANIMALS[typeName];
    const cmd = seal.ext.newCmdItemInfo();
    cmd.name = cfg.collectCmd;
    cmd.help = `收取${typeName}的${cfg.product}并换成金币`;
    cmd.solve = (ctx, msg) => {
        const ret = seal.ext.newCmdExecuteResult(true);
        const { groupId, roleName, key } = getCtxInfo(msg);
        const data = getData();
        const p = getPlayer(data, key, roleName, groupId);
        const st = p.animals[typeName];

        if (st.pool <= 0) {
            seal.replyToSender(ctx, msg, st.count > 0 ? `${cfg.product}仓库是空的，等${typeName}产出吧～` : `你还没有养${typeName}，发送「买动物 ${typeName}」试试。`);
            return ret;
        }

        const amount = st.pool;
        const gained = amount * cfg.price;
        const leveledUp = earnCoins(p, gained);
        addIngredient(p, cfg.product, amount); // 留一份同等数量的原料，可以拿去「做饭」深加工
        st.pool = 0;
        saveData(data);

        seal.replyToSender(ctx, msg, `${cfg.emoji} ${cfg.collectVerb}了${amount}份${cfg.product}，卖了${gained}金币。\n剩余金币：${p.coins}\n（同时留了${amount}份${cfg.product}原料，可以拿去「做饭」）${levelUpHint(leveledUp)}`);
        return ret;
    };
    ext.cmdMap[cfg.collectCmd] = cmd;
}
ANIMAL_NAMES.forEach(registerCollectCmd);

// ========================
// 指令：商店（商店 / 买材料）—— 直接花钱买原料，比自己种/养贵，但省时间；
// 镇上限定的原料（面粉/糖/盐/香料/巧克力）种地/养殖永远拿不到，只能在这买。
// ========================

let cmd_shop = seal.ext.newCmdItemInfo();
cmd_shop.name = '商店';
cmd_shop.help = '查看杂货店能买的原料，发送「买材料 名称 [数量]」购买';
cmd_shop.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const cal = getCalendar();
    const cropLines = cropsInSeason(cal.season).map(n => `  ${n}  ${shopPrice(n)}金币`);
    const animalLines = ANIMAL_NAMES.map(t => `  ${ANIMALS[t].product}  ${shopPrice(ANIMALS[t].product)}金币`);
    const townLines = TOWN_INGREDIENT_NAMES.map(n => `  ${n}  ${TOWN_INGREDIENTS[n]}金币`);
    seal.replyToSender(ctx, msg,
        `🏪 长露谷杂货店\n${'─'.repeat(16)}\n` +
        `【本季作物原料】比自己种贵，但不用等\n${cropLines.join('\n')}\n\n` +
        `【养殖产出】\n${animalLines.join('\n')}\n\n` +
        `【镇上限定，种地/养殖拿不到】\n${townLines.join('\n')}\n\n` +
        `发送「买材料 名称 [数量]」购买。`
    );
    return ret;
};
ext.cmdMap['商店'] = cmd_shop;

let cmd_buy_ingredient = seal.ext.newCmdItemInfo();
cmd_buy_ingredient.name = '买材料';
cmd_buy_ingredient.help = '买材料 名称 [数量]\n花钱直接买原料，价格比自己种/养贵，发送「商店」查看价目表';
cmd_buy_ingredient.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const parts = raw.split(/\s+/).filter(Boolean);
    const name = parts[0];
    const price = shopPrice(name);

    if (price == null) {
        seal.replyToSender(ctx, msg, `杂货店没有「${name || ''}」，发送「商店」看看能买什么。`);
        return ret;
    }
    if (CROPS[name] && CROPS[name].season !== getCalendar().season) {
        seal.replyToSender(ctx, msg, `「${name}」不是当季作物，杂货店现在没有进货，发送「商店」看看现在能买什么。`);
        return ret;
    }

    const count = Math.max(1, parseInt(parts[1]) || 1);
    const cost = price * count;

    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `金币不够！买${count}份${name}需要${cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= cost;
    addIngredient(p, name, count);
    saveData(data);

    seal.replyToSender(ctx, msg, `🛒 买了${count}份${name}，花费${cost}金币。\n剩余金币：${p.coins}`);
    return ret;
};
ext.cmdMap['买材料'] = cmd_buy_ingredient;

// ========================
// 指令：酒窖（建酒窖 / 买酒桶 / 酿酒 / 收酒）
// ========================

let cmd_build_brewery = seal.ext.newCmdItemInfo();
cmd_build_brewery.name = '建酒窖';
cmd_build_brewery.help = `建酒窖\n一次性花${BREWERY_UNLOCK_COST}金币解锁酿酒功能，附送1个酒桶槽位`;
cmd_build_brewery.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.brewery.unlocked) {
        seal.replyToSender(ctx, msg, `酒窖已经建好啦，发送「酿酒 作物名」开始酿造吧。`);
        return ret;
    }
    if (p.coins < BREWERY_UNLOCK_COST) {
        seal.replyToSender(ctx, msg, `金币不够！建酒窖需要${BREWERY_UNLOCK_COST}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= BREWERY_UNLOCK_COST;
    p.brewery.unlocked = true;
    p.brewery.slots = [null];
    saveData(data);

    seal.replyToSender(ctx, msg, `🍷 酒窖建好了！附送1个酒桶。\n发送「酿酒 作物名」用仓库里的原料开始酿造，「买酒桶」可以再加槽位（上限${MAX_BARRELS}个）。\n剩余金币：${p.coins}`);
    return ret;
};
ext.cmdMap['建酒窖'] = cmd_build_brewery;

let cmd_buy_barrel = seal.ext.newCmdItemInfo();
cmd_buy_barrel.name = '买酒桶';
cmd_buy_barrel.help = `买酒桶\n花金币多加一个酒桶槽位（上限${MAX_BARRELS}个，价格逐次上涨）`;
cmd_buy_barrel.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (!p.brewery.unlocked) {
        seal.replyToSender(ctx, msg, `还没有酒窖，先发送「建酒窖」吧。`);
        return ret;
    }
    if (p.brewery.slots.length >= MAX_BARRELS) {
        seal.replyToSender(ctx, msg, `酒桶已经到上限${MAX_BARRELS}个啦！`);
        return ret;
    }

    const extraOwned = p.brewery.slots.length - 1; // 解锁送的那1个不计价
    const cost = BARREL_BASE_COST + extraOwned * BARREL_STEP_COST;
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `金币不够！新酒桶需要${cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= cost;
    p.brewery.slots.push(null);
    saveData(data);

    seal.replyToSender(ctx, msg, `🛢️ 新增了一个酒桶，现在共有${p.brewery.slots.length}个。花费${cost}金币，剩余${p.coins}金币。`);
    return ret;
};
ext.cmdMap['买酒桶'] = cmd_buy_barrel;

let cmd_brew = seal.ext.newCmdItemInfo();
cmd_brew.name = '酿酒';
cmd_brew.help = `酿酒 作物名\n消耗1份该作物的原料，酿造耗时=生长时间×${WINE_TIME_MULT}，成酒价值=基准售价×${WINE_VALUE_MULT}`;
cmd_brew.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const cropName = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const crop = CROPS[cropName];

    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (!p.brewery.unlocked) {
        seal.replyToSender(ctx, msg, `还没有酒窖，先发送「建酒窖」吧。`);
        return ret;
    }
    if (!crop) {
        seal.replyToSender(ctx, msg, `没有「${cropName}」这种作物，任何种过的作物名都可以酿。`);
        return ret;
    }
    if ((p.ingredients[cropName] || 0) < 1) {
        seal.replyToSender(ctx, msg, `原料仓库里没有${cropName}，先「收菜」攒一点吧。`);
        return ret;
    }
    const emptyIdx = p.brewery.slots.findIndex(s => s === null);
    if (emptyIdx === -1) {
        seal.replyToSender(ctx, msg, `酒桶都在酿着呢，先「收酒」腾地方，或者「买酒桶」加新的。`);
        return ret;
    }

    p.ingredients[cropName]--;
    const now = Date.now();
    const brewMs = crop.growMs * WINE_TIME_MULT;
    const value = Math.round(crop.sell * WINE_VALUE_MULT);
    p.brewery.slots[emptyIdx] = { output: `${cropName}酒`, value, readyAt: now + brewMs, notified: false, groupId };
    saveData(data);

    seal.replyToSender(ctx, msg, `🍇 第${emptyIdx + 1}号酒桶开始酿${cropName}酒了，约${fmtDuration(brewMs)}后好，届时能卖${value}金币。`);
    return ret;
};
ext.cmdMap['酿酒'] = cmd_brew;

let cmd_collect_wine = seal.ext.newCmdItemInfo();
cmd_collect_wine.name = '收酒';
cmd_collect_wine.help = '收取所有已经酿好的酒，存进成品仓库（发送「卖成品」换钱或「送礼」送人）';
cmd_collect_wine.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const now = Date.now();

    if (!p.brewery.unlocked) {
        seal.replyToSender(ctx, msg, `还没有酒窖，先发送「建酒窖」吧。`);
        return ret;
    }

    const items = [];
    p.brewery.slots = p.brewery.slots.map(s => {
        if (s && s.readyAt <= now) {
            p.goods[s.output] = (p.goods[s.output] || 0) + 1;
            items.push(s.output);
            return null;
        }
        return s;
    });

    if (items.length === 0) {
        seal.replyToSender(ctx, msg, `暂时没有酿好的酒，发送「我的农场」看看进度吧。`);
        return ret;
    }

    saveData(data);
    seal.replyToSender(ctx, msg, `🍷 收进了成品仓库：${items.join('、')}\n发送「卖成品」换钱，或「送礼 @群友 物品名」送给朋友。`);
    return ret;
};
ext.cmdMap['收酒'] = cmd_collect_wine;

// ========================
// 指令：厨房（建厨房 / 买灶台 / 农场菜谱 / 做饭 / 出锅）
// ========================

let cmd_build_kitchen = seal.ext.newCmdItemInfo();
cmd_build_kitchen.name = '建厨房';
cmd_build_kitchen.help = `建厨房\n一次性花${KITCHEN_UNLOCK_COST}金币解锁做饭功能，附送1个灶台槽位`;
cmd_build_kitchen.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.kitchen.unlocked) {
        seal.replyToSender(ctx, msg, `厨房已经建好啦，发送「做饭 菜名」开始烹饪吧。`);
        return ret;
    }
    if (p.coins < KITCHEN_UNLOCK_COST) {
        seal.replyToSender(ctx, msg, `金币不够！建厨房需要${KITCHEN_UNLOCK_COST}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= KITCHEN_UNLOCK_COST;
    p.kitchen.unlocked = true;
    p.kitchen.slots = [null];
    saveData(data);

    seal.replyToSender(ctx, msg, `🍳 厨房建好了！附送1个灶台。\n发送「农场菜谱」查看菜谱，「做饭 菜名」用仓库里的原料开始烹饪，「买灶台」可以再加槽位（上限${MAX_STOVES}个）。\n剩余金币：${p.coins}`);
    return ret;
};
ext.cmdMap['建厨房'] = cmd_build_kitchen;

let cmd_buy_stove = seal.ext.newCmdItemInfo();
cmd_buy_stove.name = '买灶台';
cmd_buy_stove.help = `买灶台\n花金币多加一个灶台槽位（上限${MAX_STOVES}个，价格逐次上涨）`;
cmd_buy_stove.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (!p.kitchen.unlocked) {
        seal.replyToSender(ctx, msg, `还没有厨房，先发送「建厨房」吧。`);
        return ret;
    }
    if (p.kitchen.slots.length >= MAX_STOVES) {
        seal.replyToSender(ctx, msg, `灶台已经到上限${MAX_STOVES}个啦！`);
        return ret;
    }

    const extraOwned = p.kitchen.slots.length - 1;
    const cost = STOVE_BASE_COST + extraOwned * STOVE_STEP_COST;
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `金币不够！新灶台需要${cost}金币，你只有${p.coins}金币。`);
        return ret;
    }

    p.coins -= cost;
    p.kitchen.slots.push(null);
    saveData(data);

    seal.replyToSender(ctx, msg, `🔥 新增了一个灶台，现在共有${p.kitchen.slots.length}个。花费${cost}金币，剩余${p.coins}金币。`);
    return ret;
};
ext.cmdMap['买灶台'] = cmd_buy_stove;

let cmd_recipes = seal.ext.newCmdItemInfo();
cmd_recipes.name = '农场菜谱';
cmd_recipes.help = '查看已经学会、能做的菜谱';
cmd_recipes.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const known = RECIPE_NAMES.filter(n => p.learnedRecipes.includes(n));
    const lines = known.map(n => {
        const r = RECIPES[n];
        return `  ${n}  需要${fmtIngredients(r.need)}  耗时${fmtDuration(r.cookMs)}  成品值${r.value}金币`;
    });
    seal.replyToSender(ctx, msg,
        `🍳 长露谷菜谱（已学会 ${known.length}/${RECIPE_NAMES.length}）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n` +
        `原料来自「收菜」「捡蛋/剪羊毛/挤牛奶」顺手留下的，或去「商店」直接买。\n` +
        `发送「做饭 菜名」开始，「看电视」有机会学到新菜谱，「菜谱图鉴」查看全部收集进度。`
    );
    return ret;
};
ext.cmdMap['农场菜谱'] = cmd_recipes;

let cmd_recipe_codex = seal.ext.newCmdItemInfo();
cmd_recipe_codex.name = '菜谱图鉴';
cmd_recipe_codex.help = '查看全部菜谱的收集进度，未解锁的显示为？？？';
cmd_recipe_codex.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const lines = RECIPE_NAMES.map(n => {
        if (p.learnedRecipes.includes(n)) {
            const r = RECIPES[n];
            return `✅ ${n}  ${fmtIngredients(r.need)}  值${r.value}金币`;
        }
        return `🔒 ？？？`;
    });
    seal.replyToSender(ctx, msg,
        `📖 长露谷菜谱图鉴（${p.learnedRecipes.length}/${RECIPE_NAMES.length}）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n发送「看电视」有机会解锁新菜谱。`
    );
    return ret;
};
ext.cmdMap['菜谱图鉴'] = cmd_recipe_codex;

let cmd_watch_tv = seal.ext.newCmdItemInfo();
cmd_watch_tv.name = '看电视';
cmd_watch_tv.help = '看电视\n每天一次，有几率从美食节目里学到新菜谱';
cmd_watch_tv.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const today = currentDayIndex();

    if (p.lastTvDay === today) {
        seal.replyToSender(ctx, msg, `今天已经看过电视了，明天再来吧。`);
        return ret;
    }
    p.lastTvDay = today;

    const locked = RECIPE_NAMES.filter(n => !p.learnedRecipes.includes(n));
    if (locked.length === 0) {
        saveData(data);
        seal.replyToSender(ctx, msg, `📺 打开电视，是重播……不过你已经把所有菜谱都学会了！`);
        return ret;
    }

    if (Math.random() < TV_LEARN_CHANCE) {
        const learned = locked[Math.floor(Math.random() * locked.length)];
        p.learnedRecipes.push(learned);
        saveData(data);
        seal.replyToSender(ctx, msg, `📺 电视上正在播美食节目，你学会了新菜谱：「${learned}」！\n发送「农场菜谱」查看做法。`);
        return ret;
    }

    saveData(data);
    seal.replyToSender(ctx, msg, `📺 打开电视，只有广告和天气预报，什么新菜谱都没学到……明天再试试。`);
    return ret;
};
ext.cmdMap['看电视'] = cmd_watch_tv;

let cmd_cook = seal.ext.newCmdItemInfo();
cmd_cook.name = '做饭';
cmd_cook.help = '做饭 菜名\n用原料仓库里的材料烹饪，发送「农场菜谱」查看已学会的配方';
cmd_cook.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const dishName = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const recipe = RECIPES[dishName];

    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (!p.kitchen.unlocked) {
        seal.replyToSender(ctx, msg, `还没有厨房，先发送「建厨房」吧。`);
        return ret;
    }
    if (!recipe) {
        seal.replyToSender(ctx, msg, `没有「${dishName}」这道菜。发送「菜谱图鉴」查看全部配方。`);
        return ret;
    }
    if (!p.learnedRecipes.includes(dishName)) {
        seal.replyToSender(ctx, msg, `还没学会「${dishName}」，发送「看电视」碰碰运气，或「菜谱图鉴」查看收集进度。`);
        return ret;
    }

    const missing = Object.entries(recipe.need).filter(([n, c]) => (p.ingredients[n] || 0) < c);
    if (missing.length > 0) {
        seal.replyToSender(ctx, msg, `原料不够：还差 ${missing.map(([n, c]) => `${n}×${c - (p.ingredients[n] || 0)}`).join('、')}`);
        return ret;
    }

    const emptyIdx = p.kitchen.slots.findIndex(s => s === null);
    if (emptyIdx === -1) {
        seal.replyToSender(ctx, msg, `灶台都在忙，先「出锅」腾地方，或者「买灶台」加新的。`);
        return ret;
    }

    Object.entries(recipe.need).forEach(([n, c]) => { p.ingredients[n] -= c; });
    const now = Date.now();
    p.kitchen.slots[emptyIdx] = { output: dishName, value: recipe.value, readyAt: now + recipe.cookMs, notified: false, groupId };
    saveData(data);

    seal.replyToSender(ctx, msg, `🍳 第${emptyIdx + 1}号灶台开始做${dishName}了，约${fmtDuration(recipe.cookMs)}后好，届时能卖${recipe.value}金币。`);
    return ret;
};
ext.cmdMap['做饭'] = cmd_cook;

let cmd_serve = seal.ext.newCmdItemInfo();
cmd_serve.name = '出锅';
cmd_serve.help = '收取所有已经做好的菜，存进成品仓库（发送「卖成品」换钱或「送礼」送人）';
cmd_serve.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const now = Date.now();

    if (!p.kitchen.unlocked) {
        seal.replyToSender(ctx, msg, `还没有厨房，先发送「建厨房」吧。`);
        return ret;
    }

    const items = [];
    p.kitchen.slots = p.kitchen.slots.map(s => {
        if (s && s.readyAt <= now) {
            p.goods[s.output] = (p.goods[s.output] || 0) + 1;
            items.push(s.output);
            return null;
        }
        return s;
    });

    if (items.length === 0) {
        seal.replyToSender(ctx, msg, `暂时没有做好的菜，发送「我的农场」看看进度吧。`);
        return ret;
    }

    saveData(data);
    seal.replyToSender(ctx, msg, `🍽️ 出锅存进了成品仓库：${items.join('、')}\n发送「卖成品」换钱，或「送礼 @群友 物品名」送给朋友。`);
    return ret;
};
ext.cmdMap['出锅'] = cmd_serve;

// ========================
// 指令：卖成品 / 送礼（酒窖厨房的成品仓库要靠这两个指令变现或流通）
// ========================

let cmd_sell_goods = seal.ext.newCmdItemInfo();
cmd_sell_goods.name = '卖成品';
cmd_sell_goods.help = '卖成品 [物品名] [数量]\n把成品仓库里的酒/菜换成金币，不填物品名=全部卖掉';
cmd_sell_goods.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    const entries = Object.entries(p.goods).filter(([, c]) => c > 0);
    if (entries.length === 0) {
        seal.replyToSender(ctx, msg, `成品仓库是空的，先「收酒」或「出锅」吧。`);
        return ret;
    }

    if (!raw) {
        let gained = 0;
        const sold = entries.map(([name, c]) => {
            gained += goodsValue(name) * c;
            delete p.goods[name];
            return `${name}×${c}`;
        });
        const leveledUp = earnCoins(p, gained);
        saveData(data);
        seal.replyToSender(ctx, msg, `💰 卖掉了 ${sold.join('、')}\n共获得 ${gained} 金币，剩余 ${p.coins} 金币。${levelUpHint(leveledUp)}`);
        return ret;
    }

    const parts = raw.split(/\s+/);
    const itemName = parts[0];
    const owned = p.goods[itemName] || 0;
    if (owned <= 0) {
        seal.replyToSender(ctx, msg, `成品仓库里没有「${itemName}」。`);
        return ret;
    }
    const count = Math.min(owned, Math.max(1, parseInt(parts[1]) || owned));
    const gained = goodsValue(itemName) * count;
    p.goods[itemName] -= count;
    if (p.goods[itemName] <= 0) delete p.goods[itemName];
    const leveledUp = earnCoins(p, gained);
    saveData(data);
    seal.replyToSender(ctx, msg, `💰 卖掉了${itemName}×${count}，获得${gained}金币。\n剩余金币：${p.coins}${levelUpHint(leveledUp)}`);
    return ret;
};
ext.cmdMap['卖成品'] = cmd_sell_goods;

let cmd_gift = seal.ext.newCmdItemInfo();
cmd_gift.name = '送礼';
cmd_gift.help = '送礼 @群友 物品名 [数量]\n把成品仓库里的酒/菜送给朋友';
cmd_gift.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const targets = extractAtTargets(ctx, msg);
    if (targets.length === 0) {
        seal.replyToSender(ctx, msg, `格式：送礼 @群友 物品名 [数量]\n请在指令后@要送的对象。`);
        return ret;
    }
    const targetUid = targets[0];

    const raw = msg.message.replace(/^[。.]\S+\s*/, '').replace(/\[CQ:at,qq=\d+\]/g, '').trim();
    const parts = raw.split(/\s+/).filter(Boolean);
    const itemName = parts[0];

    const { platform, groupId, roleName, key } = getCtxInfo(msg);
    const targetKey = keyOf(platform, targetUid);

    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    const owned = itemName ? (p.goods[itemName] || 0) : 0;
    if (!itemName || owned <= 0) {
        seal.replyToSender(ctx, msg, `你的成品仓库里没有「${itemName || ''}」，发送「我的农场」看看有什么成品。`);
        return ret;
    }

    if (!data[targetKey]) {
        seal.replyToSender(ctx, msg, `对方还没有开垦农场，没法送礼。`);
        return ret;
    }
    const target = getPlayer(data, targetKey, null, null);

    const count = Math.min(owned, Math.max(1, parseInt(parts[1]) || 1));
    p.goods[itemName] -= count;
    if (p.goods[itemName] <= 0) delete p.goods[itemName];
    target.goods[itemName] = (target.goods[itemName] || 0) + count;
    p.lifetimeGifts = (p.lifetimeGifts || 0) + 1; // 成就墙："送过礼物"用这个
    saveData(data);

    seal.replyToSender(ctx, msg, `🎁 送给${target.roleName}了${itemName}×${count}。`);
    pushToGroup(seal.getEndPoints(), platform, groupId,
        `[CQ:at,qq=${targetUid}] 🎁 ${roleName}送了你${itemName}×${count}，「我的农场」可以看到，记得「卖成品」换钱哦。`);
    return ret;
};
ext.cmdMap['送礼'] = cmd_gift;

// ========================
// 指令：钓鱼
// ========================

let cmd_fish = seal.ext.newCmdItemInfo();
cmd_fish.name = '钓鱼';
cmd_fish.help = `钓鱼\n每${Math.round(FISH_COOLDOWN / 60000)}分钟可以钓一次，随机钓到不同价值的鱼`;
cmd_fish.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const now = Date.now();

    if (p.lastFishAt && now - p.lastFishAt < FISH_COOLDOWN) {
        seal.replyToSender(ctx, msg, `鱼竿还没准备好，${fmtDuration(FISH_COOLDOWN - (now - p.lastFishAt))}后再来钓吧。`);
        return ret;
    }

    p.lastFishAt = now;

    const isRain = getWorld().weather === '雨';
    const emptyChance = isRain ? FISH_EMPTY_CHANCE * RAIN_FISH_EMPTY_MULT : FISH_EMPTY_CHANCE;

    if (Math.random() < emptyChance) {
        saveData(data);
        seal.replyToSender(ctx, msg, `🎣 等了半天，什么都没钓到……空军了。`);
        return ret;
    }

    const fish = rollFish();
    const gained = randInt(fish.min, fish.max);
    const leveledUp = earnCoins(p, gained);
    if (!p.caughtFish.includes(fish.name)) p.caughtFish.push(fish.name); // 成就墙："钓到过多少种鱼"用这个
    saveData(data);

    const rainHint = isRain ? '（下雨天，鱼更活跃～）' : '';
    seal.replyToSender(ctx, msg, `🎣 钓到了一条${fish.name}！卖了${gained}金币。${rainHint}\n剩余金币：${p.coins}${levelUpHint(leveledUp)}`);
    return ret;
};
ext.cmdMap['钓鱼'] = cmd_fish;

// ========================
// 指令：市场行情
// ========================

let cmd_market = seal.ext.newCmdItemInfo();
cmd_market.name = '市场行情';
cmd_market.help = '查看今天各作物的实时收购价（每天波动）';
cmd_market.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const world = getWorld();
    const cal = getCalendar();
    const list = cropsInSeason(cal.season);
    const lines = list.map(n => {
        const base = CROPS[n].sell;
        const cur = sellPrice(n, world);
        const pct = Math.round((cur / base - 1) * 100);
        const trend = pct > 0 ? `↑${pct}%` : pct < 0 ? `↓${Math.abs(pct)}%` : '持平';
        return `  ${n}  基准${base} → 今日${cur}（${trend}）`;
    });
    seal.replyToSender(ctx, msg,
        `📈 市场行情（本季·${cal.season}）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n价格每天变化，明天再来看看行情吧。`
    );
    return ret;
};
ext.cmdMap['市场行情'] = cmd_market;

// ========================
// 指令：农场天气
// ========================

let cmd_weather = seal.ext.newCmdItemInfo();
cmd_weather.name = '农场天气';
cmd_weather.help = '查看今天天气，下雨天系统会免费帮全部作物浇一次水';
cmd_weather.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const world = getWorld();
    const desc = world.weather === '雨'
        ? (world.rainApplied ? '🌧️ 今天下雨，系统已经免费帮所有玩家的作物浇过一次水啦。' : '🌧️ 今天下雨，系统稍后会免费帮所有玩家的作物浇一次水。')
        : '☀️ 今天晴天，记得自己发送「浇水」给作物加速生长哦。';
    seal.replyToSender(ctx, msg, `📅 今日天气：${world.weather}\n${desc}`);
    return ret;
};
ext.cmdMap['农场天气'] = cmd_weather;

// ========================
// 指令：农场排行
// ========================

let cmd_rank = seal.ext.newCmdItemInfo();
cmd_rank.name = '农场排行';
cmd_rank.help = '查看本群财富排行榜（前10名，按终身累计赚取排序）';
cmd_rank.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId } = getCtxInfo(msg);
    const data = getData();
    const list = Object.values(data)
        .filter(p => p.groups && p.groups.includes(groupId))
        .sort((a, b) => (b.totalEarned || 0) - (a.totalEarned || 0))
        .slice(0, 10);

    if (list.length === 0) {
        seal.replyToSender(ctx, msg, `本群还没有人开垦农场，发送「种地 作物名」抢占第一吧！`);
        return ret;
    }

    const medals = ['🥇', '🥈', '🥉'];
    const lines = list.map((p, i) => {
        const lvl = calcLevel(p.totalEarned || 0);
        const bannerTag = p.banner ? `「${p.banner}」` : '';
        return `${medals[i] || `${i + 1}.`} ${p.equippedDecoration || DEFAULT_DECORATION}${p.roleName}${bannerTag}　Lv.${lvl} ${levelTitle(lvl)}　💰现金${p.coins}`;
    });
    seal.replyToSender(ctx, msg, `🏆 长露谷财富榜\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n按终身累计赚取排名，花钱不会掉名次。`);
    return ret;
};
ext.cmdMap['农场排行'] = cmd_rank;

// ========================
// 指令：等级（终身累计赚取金币决定，1~100级，Lv.100是世界首富）
// ========================

let cmd_level = seal.ext.newCmdItemInfo();
cmd_level.name = '等级';
cmd_level.help = '查看当前等级、称号和距离下一级还差多少';
cmd_level.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const level = calcLevel(p.totalEarned);
    const title = levelTitle(level);

    if (level >= MAX_LEVEL) {
        seal.replyToSender(ctx, msg,
            `👑 Lv.${MAX_LEVEL} ${title}\n${'─'.repeat(16)}\n终身累计赚取：${p.totalEarned}金币\n\n你已经站在长露谷的顶点了。`
        );
        return ret;
    }

    const curThreshold = levelThreshold(level);
    const nextThreshold = levelThreshold(level + 1);
    const progress = p.totalEarned - curThreshold;
    const need = nextThreshold - curThreshold;

    seal.replyToSender(ctx, msg,
        `📊 Lv.${level} ${title}\n${'─'.repeat(16)}\n终身累计赚取：${p.totalEarned}金币\n` +
        `距离 Lv.${level + 1}（${levelTitle(level + 1)}）还差 ${nextThreshold - p.totalEarned} 金币（${progress}/${need}）`
    );
    return ret;
};
ext.cmdMap['等级'] = cmd_level;

// ========================
// 指令：成就（成就墙，汇总跨系统的收集/里程碑进度）
// ========================

let cmd_achievements = seal.ext.newCmdItemInfo();
cmd_achievements.name = '成就';
cmd_achievements.help = '查看长露谷成就墙';
cmd_achievements.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const done = ACHIEVEMENTS.filter(a => a.check(p));
    const lines = ACHIEVEMENTS.map(a => a.check(p) ? `✅ ${a.name} —— ${a.desc}` : `⬜ ${a.desc}`);

    seal.replyToSender(ctx, msg,
        `🏅 长露谷成就墙（${done.length}/${ACHIEVEMENTS.length}）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n` +
        `部分成就解锁后能在「装饰」里换新徽记，戴上去让「我的农场」和排行榜都更好看。`
    );
    return ret;
};
ext.cmdMap['成就'] = cmd_achievements;

// ========================
// 指令：装饰 / 佩戴装饰 / 设置招牌（家园装饰，纯观赏，跟数值无关）
// ========================

let cmd_decorations = seal.ext.newCmdItemInfo();
cmd_decorations.name = '装饰';
cmd_decorations.help = '查看已解锁/未解锁的徽记装饰';
cmd_decorations.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const lines = DECORATION_EMOJIS.map(e => {
        const d = DECORATIONS[e];
        const unlocked = d.unlock(p);
        const wearing = p.equippedDecoration === e ? '（佩戴中）' : '';
        return unlocked ? `${e} ${d.name}${wearing}` : `🔒 ？？？ —— ${d.hint}`;
    });

    seal.replyToSender(ctx, msg,
        `🎖️ 长露谷装饰\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n发送「佩戴装饰 表情」佩戴已解锁的徽记，「设置招牌 文字」给农场起个招牌。`
    );
    return ret;
};
ext.cmdMap['装饰'] = cmd_decorations;

let cmd_equip = seal.ext.newCmdItemInfo();
cmd_equip.name = '佩戴装饰';
cmd_equip.help = '佩戴装饰 表情\n佩戴一个已解锁的徽记，发送「装饰」查看可选项';
cmd_equip.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const emoji = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    const cfg = DECORATIONS[emoji];
    if (!cfg) {
        seal.replyToSender(ctx, msg, `没有「${emoji}」这个装饰，发送「装饰」查看可选项。`);
        return ret;
    }
    if (!cfg.unlock(p)) {
        seal.replyToSender(ctx, msg, `「${cfg.name}」还没解锁，发送「成就」看看差什么条件。`);
        return ret;
    }

    p.equippedDecoration = emoji;
    saveData(data);
    seal.replyToSender(ctx, msg, `${emoji} 佩戴了「${cfg.name}」，发送「我的农场」看看效果。`);
    return ret;
};
ext.cmdMap['佩戴装饰'] = cmd_equip;

let cmd_banner = seal.ext.newCmdItemInfo();
cmd_banner.name = '设置招牌';
cmd_banner.help = `设置招牌 文字\n给农场起个招牌（最多${BANNER_MAX_LEN}个字），留空清除`;
cmd_banner.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const text = msg.message.replace(/^[。.]\S+\s*/, '').trim().slice(0, BANNER_MAX_LEN);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    p.banner = text;
    saveData(data);
    seal.replyToSender(ctx, msg, text ? `🪧 招牌设置成功：「${text}」` : `🪧 招牌已清除。`);
    return ret;
};
ext.cmdMap['设置招牌'] = cmd_banner;

// ========================
// 指令：还债 / 欠款进度（主线：继承长露谷时背的欠款）
// ========================

let cmd_repay = seal.ext.newCmdItemInfo();
cmd_repay.name = '还债';
cmd_repay.help = '还债 [数量]\n偿还继承长露谷时背的欠款，不填数量=尽量还清';
cmd_repay.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.debt.paidOff) {
        seal.replyToSender(ctx, msg, `欠款早就还清啦，长露谷真正是你的了！`);
        return ret;
    }

    const want = raw ? Math.max(1, parseInt(raw) || 0) : p.debt.amount;
    const pay = Math.min(want, p.coins, p.debt.amount);
    if (pay <= 0) {
        seal.replyToSender(ctx, msg, `你现在没有金币可以还债。`);
        return ret;
    }

    p.coins -= pay;
    p.debt.amount -= pay;
    let extra = '';
    if (p.debt.amount <= 0) {
        p.debt.amount = 0;
        p.debt.paidOff = true;
        extra = `\n\n🎉🎉 欠款还清了！长露谷从今天起真正属于你了。`;
    }
    saveData(data);

    seal.replyToSender(ctx, msg, `💸 偿还了${pay}金币，还剩${p.debt.amount}金币欠款。\n剩余现金：${p.coins}${extra}`);
    return ret;
};
ext.cmdMap['还债'] = cmd_repay;

let cmd_debt_status = seal.ext.newCmdItemInfo();
cmd_debt_status.name = '欠款进度';
cmd_debt_status.help = '查看当前欠款';
cmd_debt_status.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);

    if (p.debt.paidOff) {
        seal.replyToSender(ctx, msg, `🎉 欠款已经还清，长露谷是你的了！`);
        return ret;
    }

    seal.replyToSender(ctx, msg,
        `📜 长露谷欠款\n${'─'.repeat(16)}\n欠款：${p.debt.amount}金币（没有期限，慢慢还也来得及）\n\n发送「还债 [数量]」偿还，不填数量就尽量还清。`
    );
    return ret;
};
ext.cmdMap['欠款进度'] = cmd_debt_status;

// ========================
// 指令：我的农场
// ========================

let cmd_status = seal.ext.newCmdItemInfo();
cmd_status.name = '我的农场';
cmd_status.help = '查看地块、养殖、金币与天气状态';
cmd_status.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const { groupId, roleName, key } = getCtxInfo(msg);
    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    saveData(data);

    const now = Date.now();
    const cal = getCalendar();
    const world = getWorld();

    const plotLines = p.plots.map((pl, i) => {
        if (!pl) return `  ${i + 1}. 空地`;
        const left = pl.matureAt - now;
        if (left <= 0) return `  ${i + 1}. ${pl.crop}（已成熟，待收）`;
        const cd = pl.lastWateredAt ? WATER_COOLDOWN - (now - pl.lastWateredAt) : 0;
        const waterHint = cd > 0 ? `浇水冷却${fmtDuration(cd)}` : '可浇水';
        return `  ${i + 1}. ${pl.crop}（${fmtDuration(left)}后成熟，${waterHint}）`;
    });

    const animalLines = ANIMAL_NAMES.map(type => {
        const cfg = ANIMALS[type];
        const st = p.animals[type];
        if (!st.count) return `  ${cfg.emoji}${type}：还没养（「买动物 ${type}」，${cfg.cost}金币/只）`;
        const left = st.nextAt ? st.nextAt - now : 0;
        return `  ${cfg.emoji}${type}：${st.count}只，${cfg.product}仓库${st.pool}个${left > 0 ? `，${fmtDuration(left)}后再产出` : ''}`;
    });

    const fishLeft = p.lastFishAt ? FISH_COOLDOWN - (now - p.lastFishAt) : 0;
    const fishLine = fishLeft > 0 ? `冷却中，还剩${fmtDuration(fishLeft)}` : '可以出发钓鱼啦';

    const ingredientEntries = Object.entries(p.ingredients || {}).filter(([, c]) => c > 0);
    const ingredientLine = ingredientEntries.length > 0
        ? ingredientEntries.map(([n, c]) => `${n}×${c}`).join('、')
        : '（空的，收菜/收取养殖产出时会顺手留一些）';

    function facilityLines(facility, verb) {
        if (!facility.unlocked) return [`  还没建（发送「建${facility === p.brewery ? '酒窖' : '厨房'}」解锁）`];
        return facility.slots.map((s, i) => {
            if (!s) return `  ${i + 1}. 空置`;
            const left = s.readyAt - now;
            return left <= 0 ? `  ${i + 1}. ${s.output}（已完成，待${verb}）` : `  ${i + 1}. ${s.output}（${fmtDuration(left)}后完成）`;
        });
    }

    const goodsEntries = Object.entries(p.goods || {}).filter(([, c]) => c > 0);
    const goodsLine = goodsEntries.length > 0
        ? goodsEntries.map(([n, c]) => `${n}×${c}`).join('、')
        : '（空的，「收酒」「出锅」会把成品存进来）';

    const debtLine = p.debt.paidOff
        ? '🎉 已还清，长露谷是你的了！'
        : `欠${p.debt.amount}金币，没有期限（发送「欠款进度」看详情）`;

    const level = calcLevel(p.totalEarned);
    const bannerTag = p.banner ? `「${p.banner}」` : '';

    seal.replyToSender(ctx, msg,
        `🌾 ${p.equippedDecoration}${roleName}${bannerTag}的农场　Lv.${level} ${levelTitle(level)}\n${'─'.repeat(16)}\n` +
        `📅 第${cal.year}年${cal.season}季第${cal.dayInSeason}天 · 今日${world.weather}\n` +
        `💰 金币：${p.coins}　📜 ${debtLine}\n\n` +
        `地块（${p.plots.length}/${MAX_PLOTS}）：\n${plotLines.join('\n')}\n\n` +
        `养殖：\n${animalLines.join('\n')}\n\n` +
        `🎣 钓鱼：${fishLine}\n\n` +
        `📦 原料仓库：${ingredientLine}\n\n` +
        `🍷 酒窖：\n${facilityLines(p.brewery, '收').join('\n')}\n\n` +
        `🍳 厨房：\n${facilityLines(p.kitchen, '出锅').join('\n')}\n\n` +
        `🎁 成品仓库：${goodsLine}`
    );
    return ret;
};
ext.cmdMap['我的农场'] = cmd_status;

// ========================
// 指令：偷菜
// ========================

let cmd_steal = seal.ext.newCmdItemInfo();
cmd_steal.name = '偷菜';
cmd_steal.help = `偷菜 @群友\n偷取对方成熟未收的作物一部分（每天最多${STEAL_DAILY_LIMIT}次）`;
cmd_steal.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const targets = extractAtTargets(ctx, msg);
    if (targets.length === 0) {
        seal.replyToSender(ctx, msg, `格式：偷菜 @群友\n请在指令后@要偷的对象（不能@自己或@机器人）。`);
        return ret;
    }
    const targetUid = targets[0];

    const { platform, groupId, roleName, key } = getCtxInfo(msg);
    const targetKey = keyOf(platform, targetUid);

    const data = getData();
    const p = getPlayer(data, key, roleName, groupId);
    const today = currentDayIndex();
    if (p.stealDay !== today) { p.stealDay = today; p.stealCount = 0; }
    if (p.stealCount >= STEAL_DAILY_LIMIT) {
        seal.replyToSender(ctx, msg, `今天已经偷过${STEAL_DAILY_LIMIT}次啦，明天再来吧。`);
        return ret;
    }

    const target = data[targetKey];
    if (!target) {
        seal.replyToSender(ctx, msg, `对方还没有开垦农场。`);
        return ret;
    }

    const now = Date.now();
    const idx = target.plots.findIndex(pl => pl && pl.matureAt <= now);
    if (idx === -1) {
        seal.replyToSender(ctx, msg, `${target.roleName}家暂时没有成熟的作物可偷。`);
        return ret;
    }

    const plot = target.plots[idx];
    const sell = sellPrice(plot.crop, getWorld());
    const stolen = Math.round(sell * STEAL_SHARE);
    const remain = sell - stolen;

    target.plots[idx] = null;
    earnCoins(target, remain); // 被偷方也算"赚到"了剩下这部分，不单独播报升级（对方当下看不到消息）
    const leveledUp = earnCoins(p, stolen);
    p.stealCount++;
    p.lifetimeSteals = (p.lifetimeSteals || 0) + 1; // 成就墙："偷过菜"用这个，跟每日限次的stealCount分开算
    saveData(data);

    seal.replyToSender(ctx, msg, `🕵️ 偷到了${target.roleName}家的${plot.crop}一部分，获得${stolen}金币！\n（今天还能偷${STEAL_DAILY_LIMIT - p.stealCount}次）${levelUpHint(leveledUp)}`);

    pushToGroup(seal.getEndPoints(), platform, plot.groupId,
        `[CQ:at,qq=${targetUid}] 哎呀，你的${plot.crop}被${roleName}偷走了一部分，剩下的${remain}金币已自动收进你的农场。`);

    return ret;
};
ext.cmdMap['偷菜'] = cmd_steal;

// ========================
// 指令：地牢入口 —— 纯悬念，还没有实际玩法，先埋个坑
// ========================

let cmd_dungeon = seal.ext.newCmdItemInfo();
cmd_dungeon.name = '地牢入口';
cmd_dungeon.help = '长露谷地底似乎藏着什么……（地牢系统开发中，暂不可进入）';
cmd_dungeon.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    seal.replyToSender(ctx, msg,
        `🕳️ 长露谷边缘的杂草丛里，一扇锈迹斑斑的石门半掩着，往下延伸的台阶消失在黑暗中。\n` +
        `门上刻着的纹路很旧了，看不出是什么年代的东西。\n\n` +
        `——石门纹丝不动，进不去。\n\n` +
        `（地牢系统开发中，敬请期待）`
    );
    return ret;
};
ext.cmdMap['地牢入口'] = cmd_dungeon;
ext.cmdMap['地牢'] = cmd_dungeon;

// ========================
// 定时检查：换天天气/市场推进 + 下雨免费浇水 + 成熟/产出提醒（每分钟一次）
// ========================

let _farmTimer = null;

function startFarmTimer() {
    if (_farmTimer) clearInterval(_farmTimer);
    _farmTimer = setInterval(() => {
        const now = Date.now();
        const data = getData();
        const eps = seal.getEndPoints();
        let dirty = false;

        const world = getWorld(); // 内部会在换天时自动重新生成天气/价格
        const rainToday = world.weather === '雨' && !world.rainApplied;
        const sunnyBoost = world.weather === '晴';

        if (checkFestival(data, eps)) dirty = true;

        for (const key in data) {
            // 同上：单条记录出错只跳过这一条，不能让后面所有玩家这一分钟都收不到提醒。
            try {
                const p = data[key];
                const [platform, uid] = key.split(':');

                if (rainToday) {
                    let watered = false;
                    p.plots.forEach(pl => {
                        if (pl && pl.matureAt > now) { applyWaterBoost(pl, now); watered = true; }
                    });
                    if (watered) dirty = true;
                }

                p.plots.forEach(pl => {
                    if (pl && !pl.notified && pl.matureAt <= now) {
                        pl.notified = true;
                        dirty = true;
                        if (pl.groupId) {
                            pushToGroup(eps, platform, pl.groupId, `[CQ:at,qq=${uid}] 🌾 你的${pl.crop}熟啦，发送「收菜」收获吧！`);
                        }
                    }
                });

                ANIMAL_NAMES.forEach(type => {
                    const cfg = ANIMALS[type];
                    const st = p.animals && p.animals[type];
                    if (!st || st.count <= 0) return;
                    if (!st.nextAt) { st.nextAt = now + cfg.interval; dirty = true; return; }
                    if (st.nextAt <= now) {
                        const cap = st.count * 3;
                        const produced = sunnyBoost ? Math.ceil(st.count * SUNNY_ANIMAL_BOOST) : st.count;
                        const before = st.pool;
                        st.pool = Math.min(st.pool + produced, cap);
                        st.nextAt = now + cfg.interval;
                        dirty = true;
                        if (st.pool > before && st.groupId) {
                            pushToGroup(eps, platform, st.groupId, `[CQ:at,qq=${uid}] ${cfg.emoji} 你的${type}产出${cfg.product}啦，发送「${cfg.collectCmd}」收取吧！（仓库：${st.pool}）`);
                        }
                    }
                });

                // 酒窖/厨房：跟地块一样，槽位到期后各自 @提醒一次
                if (p.brewery && p.brewery.slots) {
                    p.brewery.slots.forEach(s => {
                        if (s && !s.notified && s.readyAt <= now) {
                            s.notified = true;
                            dirty = true;
                            if (s.groupId) {
                                pushToGroup(eps, platform, s.groupId, `[CQ:at,qq=${uid}] 🍷 你的${s.output}酿好了，发送「收酒」收获吧！`);
                            }
                        }
                    });
                }
                if (p.kitchen && p.kitchen.slots) {
                    p.kitchen.slots.forEach(s => {
                        if (s && !s.notified && s.readyAt <= now) {
                            s.notified = true;
                            dirty = true;
                            if (s.groupId) {
                                pushToGroup(eps, platform, s.groupId, `[CQ:at,qq=${uid}] 🍳 你的${s.output}做好了，发送「出锅」收获吧！`);
                            }
                        }
                    });
                }
            } catch (e) {
                console.error(`[长露谷] 定时检查处理记录失败，已跳过: ${key}`, e);
            }
        }

        if (rainToday) {
            world.rainApplied = true;
            saveWorld(world);
        }
        if (dirty) saveData(data);
    }, 60 * 1000);
}

startFarmTimer();
