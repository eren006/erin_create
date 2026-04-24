"use strict";
// ==UserScript==
// @name         神域进化·诸神文明
// @author       长日将尽 (声望与建筑版)
// @version      2.1.0
// @description  扮演神明，发展文明，争夺信徒，从原始走向宇宙，成就至高神格
// @timestamp    1731234567
// @license      Apache-2
// ==/UserScript==

let ext = seal.ext.find("GodCivGame");
if (!ext) {
    ext = seal.ext.new("GodCivGame", "长日将尽", "2.1.0");
    seal.ext.register(ext);
}

// ========== 数据存储键 ==========
const GODS_DATA_KEY = "gods_civ_data_v2";
const ADMINS_KEY = "gods_admins";
const PLUNDER_HISTORY_KEY = "plunder_history_v2";
const ARTIFACT_KEY = "gods_artifacts";
const EVENT_COOLDOWN_KEY = "event_cooldown";

// ========== 常量定义 ==========
const ENERGY_RECOVERY_INTERVAL = 20 * 60 * 1000; // 20分钟
const ENERGY_PER_INTERVAL = 15;
const CULTIVATE_ENERGY_COST = 10;
const DEVELOP_ENERGY_COST = 8;
const PLUNDER_ENERGY_COST = 15;
const PLUNDER_COOLDOWN = 60 * 60 * 1000; // 1小时
const EVENT_COOLDOWN_TIME = 30 * 60 * 1000; // 30分钟随机事件冷却

// 神格等级所需累计消耗信仰（经验值）
const DIVINE_LEVEL_REQUIREMENTS = [
    0,      // 1级
    500,    // 2级
    1200,   // 3级
    2200,   // 4级
    3600,   // 5级
    5500,   // 6级
    8000,   // 7级
    11500,  // 8级
    16000,  // 9级
    22000   // 10级
];

// ========== 科技时代定义 ==========
const TECH_AGES = [
    { id: 0, name: "原始时代", desc: "茹毛饮血，信仰初萌", 
      faithCost: 0, popCost: 0, 
      cultivateBonus: 0, popGrowthBonus: 0, plunderBonus: 0, defenseBonus: 0,
      unlockFeatures: ["基础耕种", "人口发展"] },
    { id: 1, name: "农耕时代", desc: "刀耕火种，文明曙光",
      faithCost: 500, popCost: 20,
      cultivateBonus: 0.2, popGrowthBonus: 0.1, plunderBonus: 0, defenseBonus: 0.05,
      unlockFeatures: ["灌溉技术", "简易城墙"] },
    { id: 2, name: "城邦时代", desc: "城池林立，诸神争霸",
      faithCost: 1500, popCost: 50,
      cultivateBonus: 0.4, popGrowthBonus: 0.2, plunderBonus: 0.1, defenseBonus: 0.1,
      unlockFeatures: ["军队", "神庙"] },
    { id: 3, name: "帝国时代", desc: "铁骑横扫，万邦来朝",
      faithCost: 4000, popCost: 120,
      cultivateBonus: 0.7, popGrowthBonus: 0.3, plunderBonus: 0.2, defenseBonus: 0.15,
      unlockFeatures: ["铁器", "法典"] },
    { id: 4, name: "工业时代", desc: "蒸汽轰鸣，信仰工业化",
      faithCost: 10000, popCost: 300,
      cultivateBonus: 1.0, popGrowthBonus: 0.5, plunderBonus: 0.3, defenseBonus: 0.2,
      unlockFeatures: ["工厂", "铁路"] },
    { id: 5, name: "信息时代", desc: "网络互联，全球信仰",
      faithCost: 20000, popCost: 800,
      cultivateBonus: 1.5, popGrowthBonus: 0.8, plunderBonus: 0.4, defenseBonus: 0.25,
      unlockFeatures: ["互联网", "卫星"] },
    { id: 6, name: "星际时代", desc: "殖民群星，神域扩展",
      faithCost: 40000, popCost: 2000,
      cultivateBonus: 2.2, popGrowthBonus: 1.2, plunderBonus: 0.5, defenseBonus: 0.3,
      unlockFeatures: ["星际飞船", "外星接触"] },
    { id: 7, name: "宇宙时代", desc: "统御银河，创世之力",
      faithCost: 80000, popCost: 5000,
      cultivateBonus: 3.0, popGrowthBonus: 1.5, plunderBonus: 0.6, defenseBonus: 0.35,
      unlockFeatures: ["戴森球", "维度穿梭"] }
];

// 神格等级加成系数（每级额外增加）
const DIVINE_LEVEL_BONUS = {
    cultivate: 0.05,   // 每级+5%耕种收益
    plunder: 0.04,     // 每级+4%掠夺成功率
    defense: 0.03      // 每级+3%防御（减少被掠夺损失）
};

// ========== 阵营定义 ==========
const ALIGNMENTS = {
    good: { name: "善良", minPiety: 20, title: "圣光使者", artifact: "仁慈之冠", artifactDesc: "信仰恢复速度+15%，随机事件正面效果+20%", effect: { faithRegen: 0.15, eventBonus: 0.2 } },
    neutral: { name: "中立", minPiety: -20, maxPiety: 19, title: "平衡行者", artifact: "均衡之环", artifactDesc: "耕种收益+5%，掠夺成功率+5%", effect: { cultivateBonus: 0.05, plunderBonus: 0.05 } },
    evil: { name: "邪恶", maxPiety: -21, title: "暗影主宰", artifact: "恐惧之盔", artifactDesc: "掠夺成功率+15%，军队攻击力+10%", effect: { plunderBonus: 0.15, armyAttackBonus: 0.1 } }
};

// 阵营专属神器ID（会自动给予）
const ALIGNMENT_ARTIFACTS = {
    good: "mercy_crown",
    neutral: "balance_ring",
    evil: "fear_helm"
};

// 神器库（新增阵营专属）
const ARTIFACTS = [
    { id: "agri_hammer", name: "丰收之锤", desc: "耕种信仰收益+20%", effect: { type: "cultivate", value: 0.2 } },
    { id: "pop_scepter", name: "繁衍权杖", desc: "人口增长速度+15%", effect: { type: "popGrowth", value: 0.15 } },
    { id: "war_shield", name: "战神壁垒", desc: "掠夺防御+25%", effect: { type: "defense", value: 0.25 } },
    { id: "luck_coin", name: "幸运金币", desc: "随机事件正面效果+30%", effect: { type: "eventBonus", value: 0.3 } },
    { id: "tech_scroll", name: "智慧卷轴", desc: "科技升级消耗-10%", effect: { type: "techCostReduce", value: 0.1 } },
    { id: "faith_cup", name: "圣杯", desc: "信仰自动恢复+5/小时", effect: { type: "faithRegen", value: 5 } },
    // 阵营专属神器
    { id: "mercy_crown", name: "仁慈之冠", desc: "信仰恢复速度+15%，随机事件正面效果+20%", effect: { type: "faithRegenPercent", value: 0.15, eventBonus: 0.2 } },
    { id: "balance_ring", name: "均衡之环", desc: "耕种收益+5%，掠夺成功率+5%", effect: { type: "cultivate", value: 0.05, plunderBonus: 0.05 } },
    { id: "fear_helm", name: "恐惧之盔", desc: "掠夺成功率+15%，军队攻击力+10%", effect: { type: "plunderBonus", value: 0.15, armyAttackBonus: 0.1 } }
];

// ========== 信仰建筑定义 ==========
const BUILDINGS = {
    cathedral: { name: "大圣堂", desc: "增加信仰自动恢复", baseCost: { faith: 1000, pop: 50 }, upgradeCost: { faith: 500, pop: 20 }, effect: (level) => ({ faithRegen: 2 + level * 1 }) },
    arena: { name: "演武场", desc: "增加军队攻击力", baseCost: { faith: 800, pop: 40 }, upgradeCost: { faith: 400, pop: 15 }, effect: (level) => ({ armyAttackPercent: 5 + level * 3 }) },
    observatory: { name: "观星台", desc: "提高随机事件触发概率", baseCost: { faith: 1200, pop: 60 }, upgradeCost: { faith: 600, pop: 25 }, effect: (level) => ({ eventChanceBonus: 0.05 + level * 0.02 }) }
};

// ========== 随机事件库（按阵营倾向调整权重）==========
const BASE_RANDOM_EVENTS = [
    { name: "丰收之年", desc: "风调雨顺，信仰丰收", 
      effect: (god) => { let gain = Math.floor(god.population * 0.2); god.faith += gain; return `信仰 +${gain}`; },
      weight: 15, minPop: 10, positive: true },
    { name: "瘟疫横行", desc: "疾病肆虐，信徒减少", 
      effect: (god) => { let loss = Math.floor(god.population * 0.1); god.population = Math.max(1, god.population - loss); return `信徒 -${loss}`; },
      weight: 10, minPop: 20, positive: false },
    { name: "神谕显现", desc: "神迹降临，神力充沛", 
      effect: (god) => { god.divinePower = Math.min(god.maxDivinePower, god.divinePower + 30); return `神力 +30`; },
      weight: 12, positive: true },
    { name: "异端叛乱", desc: "部分信徒背叛，信仰流失", 
      effect: (god) => { let loss = Math.floor(god.faith * 0.15); god.faith = Math.max(0, god.faith - loss); return `信仰 -${loss}`; },
      weight: 8, minFaith: 200, positive: false },
    { name: "陨石坠落", desc: "天降神石，土地扩张", 
      effect: (god) => { god.land += 2; return `神土 +2 亩`; },
      weight: 6, positive: true },
    { name: "英雄诞生", desc: "传奇英雄出现，信徒激增", 
      effect: (god) => { let gain = Math.floor(god.population * 0.3); god.population += gain; return `信徒 +${gain}`; },
      weight: 8, minPop: 30, positive: true },
    { name: "神殿宝藏", desc: "发现古代神器碎片", 
      effect: (god) => { let faithGain = 300 + getRandomInt(0, 700); god.faith += faithGain; return `信仰 +${faithGain}`; },
      weight: 5, positive: true, artifactChance: 0.3 },
    { name: "天灾蝗虫", desc: "庄稼被毁，耕种收益下降", 
      effect: (god) => { let debuff = { type: "cultivate", value: -0.3, duration: 2 }; god.tempDebuffs = god.tempDebuffs || []; god.tempDebuffs.push(debuff); return `未来2次耕种收益 -30%`; },
      weight: 7, positive: false }
];

// ========== 辅助函数 ==========
function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function getLevelName(level) {
    const names = ["见习神明", "下位神明", "中位神明", "上位神明", "大神明", "主神", "至高神", "创世神", "宇宙主宰", "绝对神"];
    return names[level - 1] || "超脱者";
}

function isAdmin(ctx, userId) {
    // 优先使用新版按平台存储的管理员列表
    const adminListData = ext.storageGet("a_adminList");
    if (adminListData) {
        const adminListByPlatform = JSON.parse(adminListData);
        const platform = ctx.endPoint.platform;
        if (adminListByPlatform[platform] && adminListByPlatform[platform].includes(userId.split(':')[1] || userId)) {
            return true;
        }
    }
    // 回退到旧版简单数组（兼容之前的数据）
    const oldAdminList = ext.storageGet(ADMINS_KEY);
    if (oldAdminList) {
        const admins = JSON.parse(oldAdminList);
        return admins.includes(userId);
    }
    return false;
}

function getCurrentAgeBonus(god) {
    const age = TECH_AGES.find(a => a.id === god.techAge);
    return age || TECH_AGES[0];
}

// 根据神性值获取阵营
function getAlignment(piety) {
    if (piety >= 20) return ALIGNMENTS.good;
    if (piety <= -21) return ALIGNMENTS.evil;
    return ALIGNMENTS.neutral;
}

// 更新阵营并自动给予/移除阵营神器
function updateAlignment(god) {
    const oldAlign = getAlignment(god.piety);
    const newAlign = getAlignment(god.piety);
    if (oldAlign.name !== newAlign.name) {
        // 移除旧阵营神器
        const oldArtifactId = ALIGNMENT_ARTIFACTS[oldAlign.name === "善良" ? "good" : (oldAlign.name === "邪恶" ? "evil" : "neutral")];
        if (oldArtifactId && god.artifacts.includes(oldArtifactId)) {
            god.artifacts = god.artifacts.filter(id => id !== oldArtifactId);
        }
        // 添加新阵营神器
        const newArtifactId = ALIGNMENT_ARTIFACTS[newAlign.name === "善良" ? "good" : (newAlign.name === "邪恶" ? "evil" : "neutral")];
        if (newArtifactId && !god.artifacts.includes(newArtifactId)) {
            god.artifacts.push(newArtifactId);
        }
        return true;
    }
    return false;
}

// 计算实际耕种收益（加入建筑加成）
function calcCultivateGain(god) {
    let base = god.land * 2 + getRandomInt(5, 15);
    const age = getCurrentAgeBonus(god);
    let bonus = 1 + age.cultivateBonus;
    bonus += (god.divineLevel - 1) * DIVINE_LEVEL_BONUS.cultivate;
    // 神器加成
    if (god.artifacts && god.artifacts.includes("agri_hammer")) bonus += 0.2;
    if (god.artifacts && god.artifacts.includes("balance_ring")) bonus += 0.05;
    // 临时减益
    let debuff = 1;
    if (god.tempDebuffs) {
        const cultDebuff = god.tempDebuffs.find(d => d.type === "cultivate");
        if (cultDebuff) {
            debuff += cultDebuff.value;
            cultDebuff.duration--;
            if (cultDebuff.duration <= 0) god.tempDebuffs = god.tempDebuffs.filter(d => d !== cultDebuff);
        }
    }
    return Math.floor(base * bonus * debuff);
}

// 计算发展人口消耗与增长（加入建筑加成）
function calcDevelopCost(god) {
    let baseCost = 50;
    let growth = Math.floor(god.population * 0.1) + 5;
    const age = getCurrentAgeBonus(god);
    let costReduce = 1 - (age.popGrowthBonus * 0.5);
    let cost = Math.floor(baseCost * costReduce);
    if (god.artifacts && god.artifacts.includes("pop_scepter")) growth = Math.floor(growth * 1.15);
    return { cost, growth };
}

// 掠夺成功率计算（加入阵营加成）
function calcPlunderChance(attacker, defender) {
    let base = 0.4;
    base += (attacker.divineLevel - 1) * DIVINE_LEVEL_BONUS.plunder;
    base -= (defender.divineLevel - 1) * DIVINE_LEVEL_BONUS.defense;
    const ageAtt = getCurrentAgeBonus(attacker);
    const ageDef = getCurrentAgeBonus(defender);
    base += ageAtt.plunderBonus - ageDef.defenseBonus;
    // 神器加成
    if (attacker.artifacts && attacker.artifacts.includes("war_shield")) base += 0.1;
    if (defender.artifacts && defender.artifacts.includes("war_shield")) base -= 0.15;
    if (attacker.artifacts && attacker.artifacts.includes("fear_helm")) base += 0.15;
    if (attacker.artifacts && attacker.artifacts.includes("balance_ring")) base += 0.05;
    // 阵营加成（邪恶掠夺成功率+5%）
    const alignAtt = getAlignment(attacker.piety);
    if (alignAtt.name === "邪恶") base += 0.05;
    return Math.min(0.9, Math.max(0.1, base));
}

// 掠夺收获
function calcPlunderGain(attacker, defender, success) {
    if (!success) return { faith: 0, pop: 0 };
    let stealFaith = Math.floor(defender.faith * 0.2);
    let stealPop = Math.floor(defender.population * 0.1);
    stealFaith = Math.min(stealFaith, attacker.maxDivinePower * 2);
    return { faith: stealFaith, pop: stealPop };
}

// 计算信仰自动恢复速率（加入建筑和阵营神器）
function calcFaithRegen(god) {
    let regen = 0;
    if (god.buildings && god.buildings.cathedral) {
        regen += BUILDINGS.cathedral.effect(god.buildings.cathedral).faithRegen;
    }
    if (god.artifacts && god.artifacts.includes("faith_cup")) regen += 5;
    if (god.artifacts && god.artifacts.includes("mercy_crown")) regen += Math.floor(god.maxDivinePower * 0.15);
    return regen;
}

// 计算军队攻击力加成（加入建筑和阵营神器）
function calcArmyAttackBonus(god) {
    let bonus = 0;
    if (god.buildings && god.buildings.arena) {
        bonus += BUILDINGS.arena.effect(god.buildings.arena).armyAttackPercent;
    }
    if (god.artifacts && god.artifacts.includes("fear_helm")) bonus += 10;
    return bonus;
}

// 计算随机事件权重调整（阵营影响）
function getAdjustedEventWeights(god) {
    const align = getAlignment(god.piety);
    let multiplier = 1.0;
    if (align.name === "善良") multiplier = 1.3;  // 正面事件权重提高30%
    if (align.name === "邪恶") multiplier = 0.7;  // 正面事件权重降低30%
    return BASE_RANDOM_EVENTS.map(ev => ({
        ...ev,
        weight: ev.positive ? ev.weight * multiplier : ev.weight / multiplier
    }));
}

// 检查胜利条件
function checkVictory(god) {
    if (god.techAge >= 7 && god.population >= 10000 && god.faith >= 50000) {
        if (!god.victoryAchieved) {
            god.victoryAchieved = true;
            god.victoryTime = Date.now();
            return true;
        }
    }
    return false;
}

// ========== 神谕提醒系统 ==========
class DivineReminder {
    constructor(ext) {
        this.ext = ext;
        this.reminders = new Map();
        this.reminderClock = null;
        this.loadReminders();
        this.startReminderClock();
    }
    getReminderId() { return 'DR' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5).toUpperCase(); }
    loadReminders() {
        try {
            const stored = this.ext.storageGet('divineReminders') || '{}';
            const records = JSON.parse(stored);
            for (const id in records) if (records[id].remindTime > Date.now()) this.reminders.set(id, records[id]);
        } catch(e) {}
    }
    saveReminders() {
        const records = {};
        for (const [id, r] of this.reminders.entries()) records[id] = r;
        this.ext.storageSet('divineReminders', JSON.stringify(records));
    }
    startReminderClock() {
        if (this.reminderClock) return;
        this.reminderClock = setInterval(() => this.checkReminders(), 10000);
    }
    checkReminders() {
        const now = Date.now();
        const toRemove = [];
        for (const [id, r] of this.reminders.entries()) {
            if (r.remindTime <= now && !r.delivered) {
                this.sendReminder(r);
                r.delivered = true;
                toRemove.push(id);
            }
        }
        toRemove.forEach(id => this.reminders.delete(id));
        if (toRemove.length) this.saveReminders();
    }
    sendReminder(reminder) {
        const { endpointId, groupId, userId, message } = reminder.data;
        const atCQ = groupId ? `[CQ:at,qq=${userId.split(':')[1] || userId}] ` : '';
        const fullMsg = `${atCQ}🏛️【神谕提醒】\n\n${message}`;
        const endpoints = seal.getEndPoints();
        for (let ep of endpoints) {
            if (ep.userId === endpointId) {
                const msg = seal.newMessage();
                if (groupId) { msg.messageType = 'group'; msg.groupId = groupId; msg.sender.userId = userId; }
                else { msg.messageType = 'private'; msg.sender.userId = userId; }
                const ctx = seal.createTempCtx(ep, msg);
                seal.replyToSender(ctx, msg, fullMsg);
                break;
            }
        }
    }
    addReminder(params) {
        const id = this.getReminderId();
        const reminder = { id, remindTime: Date.now() + (params.cooldownSeconds * 1000), delivered: false, data: { endpointId: params.endpointId, groupId: params.groupId || null, userId: params.userId, message: params.message } };
        this.reminders.set(id, reminder);
        this.saveReminders();
        return id;
    }
    removeReminder(id) { return this.reminders.delete(id); }
    formatRemainingTime(ms) { const m = Math.floor(ms/60000); const s = Math.floor((ms%60000)/1000); return m>0?`${m}分${s}秒`:`${s}秒`; }
}
let divineReminder = null;
function startDivineReminder() { if(!divineReminder) divineReminder = new DivineReminder(ext); return divineReminder; }
setTimeout(() => startDivineReminder(), 1000);

// ========== 指令实现 ==========

// 注册神祇（新增阵营和建筑字段）
const cmd_register = seal.ext.newCmdItemInfo();
cmd_register.name = '神祇注册';
cmd_register.help = '创建神祇档案\n用法：.神祇注册 <神名>';
cmd_register.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    if (gods[userId]) { seal.replyToSender(ctx, msg, "🏛️ 你已经拥有神格！"); return seal.ext.newCmdExecuteResult(true); }
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 1) { seal.replyToSender(ctx, msg, "❌ 用法：.神祇注册 <神名>"); return seal.ext.newCmdExecuteResult(true); }
    const godName = args.join(" ");
    gods[userId] = {
        godName, userId,
        faith: 100, population: 10, land: 5, divinePower: 50, maxDivinePower: 100,
        divineLevel: 1, totalFaithSpent: 0, techAge: 0,
        lastRecoverTime: Date.now(), lastPlunderTime: 0,
        artifacts: [], victoryAchieved: false, victoryTime: null,
        totalCultivate: 0, totalDevelop: 0, totalPlunderWin: 0, totalPlunderLose: 0,
        tempDebuffs: [], eventLastTime: 0,
        // 新增字段
        piety: 0,                // 神性值 -100~100
        buildings: { cathedral: 0, arena: 0, observatory: 0 }  // 建筑等级
    };
    // 初始化中立阵营神器
    gods[userId].artifacts.push("balance_ring");
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `🏛️ 神域开辟，${godName} 诞生！\n初始信仰100，信徒10，神土5亩，神力50。\n阵营：中立，获得均衡之环。\n使用 .神祇状态 查看详情`);
    return seal.ext.newCmdExecuteResult(true);
};

// 神祇状态（新增阵营、建筑、神性值显示）
const cmd_status = seal.ext.newCmdItemInfo();
cmd_status.name = '神祇状态';
cmd_status.help = '查看神祇详细状态';
cmd_status.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "🏛️ 请先注册 .神祇注册"); return seal.ext.newCmdExecuteResult(true); }
    // 恢复神力
    const now = Date.now();
    const intervals = Math.floor((now - (god.lastRecoverTime||now)) / ENERGY_RECOVERY_INTERVAL);
    if (intervals > 0) {
        god.divinePower = Math.min(god.maxDivinePower, god.divinePower + intervals * ENERGY_PER_INTERVAL);
        god.lastRecoverTime += intervals * ENERGY_RECOVERY_INTERVAL;
        ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    }
    const age = TECH_AGES[god.techAge];
    const align = getAlignment(god.piety);
    let txt = `🏛️ ${god.godName} 的神域\n`;
    txt += `神格：${god.divineLevel}级 ${getLevelName(god.divineLevel)}\n`;
    txt += `时代：${age.name} - ${age.desc}\n`;
    txt += `阵营：${align.name} · ${align.title}  (神性值 ${god.piety})\n`;
    txt += `🙏 信仰：${god.faith}   👥 信徒：${god.population}\n`;
    txt += `🌾 神土：${god.land}亩   ⚡ 神力：${god.divinePower}/${god.maxDivinePower}\n`;
    txt += `📈 战绩：胜 ${god.totalPlunderWin} / 负 ${god.totalPlunderLose}\n`;
    const nextReq = DIVINE_LEVEL_REQUIREMENTS[god.divineLevel] || "MAX";
    txt += `✨ 升级神格需累计消耗信仰：${god.totalFaithSpent}/${nextReq}\n`;
    if (god.artifacts.length) txt += `🏺 神器：${god.artifacts.map(a => ARTIFACTS.find(art=>art.id===a)?.name || a).join(', ')}\n`;
    // 建筑显示
    let buildingTxt = [];
    for (let [key, val] of Object.entries(god.buildings)) {
        if (val > 0) buildingTxt.push(`${BUILDINGS[key].name} Lv.${val}`);
    }
    if (buildingTxt.length) txt += `🏗️ 建筑：${buildingTxt.join(', ')}\n`;
    if (god.victoryAchieved) txt += `🎉 已达成宇宙胜利！入驻名人堂！\n`;
    txt += `💡 指令：.神祇耕种 | .神祇发展人口 | .神祇掠夺 <神名> | .神祇帮助 <神名> | .神祇科技树 | .神祇升级科技 | .神祇升级神格 | .神祇购买神器 | .神祇建造 <建筑> | .神祇升级建筑 <建筑> | .神祇查看建筑 | .神祇排行榜`;
    seal.replyToSender(ctx, msg, txt);
    return seal.ext.newCmdExecuteResult(true);
};

// 耕种（无变化，但需要保留事件触发）
const cmd_cultivate = seal.ext.newCmdItemInfo();
cmd_cultivate.name = '神祇耕种';
cmd_cultivate.help = '消耗神力，获得信仰';
cmd_cultivate.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    if (god.divinePower < CULTIVATE_ENERGY_COST) { seal.replyToSender(ctx, msg, `神力不足，需要${CULTIVATE_ENERGY_COST}`); return seal.ext.newCmdExecuteResult(true); }
    god.divinePower -= CULTIVATE_ENERGY_COST;
    const gain = calcCultivateGain(god);
    god.faith += gain;
    god.totalCultivate++;
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `🌾 你率领信徒耕种神土，获得 ${gain} 信仰！\n剩余神力 ${god.divinePower}/${god.maxDivinePower}`);
    tryTriggerRandomEvent(ctx, msg, userId, god);
    return seal.ext.newCmdExecuteResult(true);
};

// 发展人口
const cmd_develop = seal.ext.newCmdItemInfo();
cmd_develop.name = '神祇发展人口';
cmd_develop.help = '消耗信仰，增加信徒';
cmd_develop.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    if (god.divinePower < DEVELOP_ENERGY_COST) { seal.replyToSender(ctx, msg, `神力不足`); return seal.ext.newCmdExecuteResult(true); }
    const { cost, growth } = calcDevelopCost(god);
    if (god.faith < cost) { seal.replyToSender(ctx, msg, `信仰不足，需要 ${cost}`); return seal.ext.newCmdExecuteResult(true); }
    god.divinePower -= DEVELOP_ENERGY_COST;
    god.faith -= cost;
    god.population += growth;
    god.totalDevelop++;
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `👥 神谕感召，信徒增加了 ${growth} 人！消耗信仰 ${cost}，神力 ${DEVELOP_ENERGY_COST}\n当前信徒 ${god.population}`);
    tryTriggerRandomEvent(ctx, msg, userId, god);
    return seal.ext.newCmdExecuteResult(true);
};

// 掠夺（修改：增加神性值变化）
const cmd_plunder = seal.ext.newCmdItemInfo();
cmd_plunder.name = '神祇掠夺';
cmd_plunder.help = '掠夺其他神祇的信徒和信仰\n用法：.神祇掠夺 <神名>';
cmd_plunder.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const attacker = gods[userId];
    if (!attacker) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 1) { seal.replyToSender(ctx, msg, "❌ 用法：.神祇掠夺 <神名>"); return seal.ext.newCmdExecuteResult(true); }
    const targetName = args.join(" ");
    let defenderId = null, defender = null;
    for (const id in gods) {
        if (gods[id].godName === targetName && id !== userId) { defenderId = id; defender = gods[id]; break; }
    }
    if (!defender) { seal.replyToSender(ctx, msg, `未找到神祇 ${targetName}`); return seal.ext.newCmdExecuteResult(true); }
    const now = Date.now();
    if (now - (attacker.lastPlunderTime || 0) < PLUNDER_COOLDOWN) {
        const remain = Math.ceil((PLUNDER_COOLDOWN - (now - attacker.lastPlunderTime)) / 60000);
        seal.replyToSender(ctx, msg, `⏰ 掠夺冷却中，还需 ${remain} 分钟`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (attacker.divinePower < PLUNDER_ENERGY_COST) { seal.replyToSender(ctx, msg, `神力不足，需要 ${PLUNDER_ENERGY_COST}`); return seal.ext.newCmdExecuteResult(true); }
    attacker.divinePower -= PLUNDER_ENERGY_COST;
    attacker.lastPlunderTime = now;
    const chance = calcPlunderChance(attacker, defender);
    const success = Math.random() < chance;
    let resultMsg = "";
    if (success) {
        const gain = calcPlunderGain(attacker, defender, true);
        attacker.faith += gain.faith;
        attacker.population += gain.pop;
        defender.faith = Math.max(0, defender.faith - gain.faith);
        defender.population = Math.max(1, defender.population - gain.pop);
        attacker.totalPlunderWin++;
        resultMsg = `✅ 掠夺成功！获得 ${gain.faith} 信仰和 ${gain.pop} 信徒！`;
        // 掠夺成功减少神性值（邪恶倾向）
        attacker.piety = Math.max(-100, attacker.piety - 5);
    } else {
        const loss = Math.floor(attacker.faith * 0.1);
        attacker.faith = Math.max(0, attacker.faith - loss);
        attacker.totalPlunderLose++;
        resultMsg = `❌ 掠夺失败！对方神力护体，你损失了 ${loss} 信仰。`;
        attacker.piety = Math.max(-100, attacker.piety - 3); // 失败也略减
    }
    updateAlignment(attacker);
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `⚔️ 你向 ${defender.godName} 发起神战！\n成功率 ${Math.round(chance*100)}%\n${resultMsg}\n剩余神力 ${attacker.divinePower}\n神性值变化：${attacker.piety}`);
    tryTriggerRandomEvent(ctx, msg, userId, attacker);
    return seal.ext.newCmdExecuteResult(true);
};

// 新增：帮助其他神祇（增加神性值）
const cmd_help_god = seal.ext.newCmdItemInfo();
cmd_help_god.name = '神祇帮助';
cmd_help_god.help = '帮助其他神祇，增加神性值\n用法：.神祇帮助 <神名>';
cmd_help_god.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const helper = gods[userId];
    if (!helper) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 1) { seal.replyToSender(ctx, msg, "❌ 用法：.神祇帮助 <神名>"); return seal.ext.newCmdExecuteResult(true); }
    const targetName = args.join(" ");
    let target = null;
    for (const id in gods) {
        if (gods[id].godName === targetName && id !== userId) { target = gods[id]; break; }
    }
    if (!target) { seal.replyToSender(ctx, msg, `未找到神祇 ${targetName}`); return seal.ext.newCmdExecuteResult(true); }
    // 帮助消耗20神力，获得神性值+8，目标获得少量信仰
    if (helper.divinePower < 20) { seal.replyToSender(ctx, msg, `神力不足，需要20`); return seal.ext.newCmdExecuteResult(true); }
    helper.divinePower -= 20;
    helper.piety = Math.min(100, helper.piety + 8);
    target.faith += 50;
    updateAlignment(helper);
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `🤝 你向 ${target.godName} 伸出援手，消耗20神力，帮助其发展信仰。\n神性值 +8，当前 ${helper.piety}，对方获得50信仰。`);
    tryTriggerRandomEvent(ctx, msg, userId, helper);
    return seal.ext.newCmdExecuteResult(true);
};

// 升级神格（无变化）
const cmd_upgrade_divine = seal.ext.newCmdItemInfo();
cmd_upgrade_divine.name = '神祇升级神格';
cmd_upgrade_divine.help = '消耗累计信仰提升神格等级';
cmd_upgrade_divine.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const currentLv = god.divineLevel;
    const required = DIVINE_LEVEL_REQUIREMENTS[currentLv];
    if (!required) { seal.replyToSender(ctx, msg, "已达最高神格！"); return seal.ext.newCmdExecuteResult(true); }
    if (god.totalFaithSpent < required) {
        seal.replyToSender(ctx, msg, `累计消耗信仰不足，需要 ${required}，当前 ${god.totalFaithSpent}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    god.divineLevel++;
    seal.replyToSender(ctx, msg, `✨ 神格晋升！你现在是 ${god.divineLevel}级 ${getLevelName(god.divineLevel)}！\n各项能力获得提升。`);
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    return seal.ext.newCmdExecuteResult(true);
};

// 科技树查看
const cmd_tech_tree = seal.ext.newCmdItemInfo();
cmd_tech_tree.name = '神祇科技树';
cmd_tech_tree.help = '查看当前时代和下一时代需求';
cmd_tech_tree.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const cur = TECH_AGES[god.techAge];
    const next = TECH_AGES[god.techAge + 1];
    let txt = `📜 当前时代：${cur.name} - ${cur.desc}\n`;
    txt += `加成：耕种 +${Math.round(cur.cultivateBonus*100)}% 人口增长 +${Math.round(cur.popGrowthBonus*100)}% 掠夺 +${Math.round(cur.plunderBonus*100)}% 防御 +${Math.round(cur.defenseBonus*100)}%\n`;
    if (next) {
        txt += `\n🔮 下一时代：${next.name}\n需求：信仰 ${next.faithCost}，信徒 ${next.popCost}\n`;
        txt += `将解锁：${next.unlockFeatures.join(', ')}\n`;
    } else {
        txt += `\n✨ 你已经达到宇宙时代！继续壮大信徒，迈向宇宙胜利吧！`;
    }
    seal.replyToSender(ctx, msg, txt);
    return seal.ext.newCmdExecuteResult(true);
};

// 升级科技
const cmd_upgrade_tech = seal.ext.newCmdItemInfo();
cmd_upgrade_tech.name = '神祇升级科技';
cmd_upgrade_tech.help = '消耗信仰和信徒，进入下一个文明时代';
cmd_upgrade_tech.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const next = TECH_AGES[god.techAge + 1];
    if (!next) { seal.replyToSender(ctx, msg, "你已经是最高的宇宙时代！"); return seal.ext.newCmdExecuteResult(true); }
    let costFaith = next.faithCost;
    let costPop = next.popCost;
    if (god.artifacts && god.artifacts.includes("tech_scroll")) {
        costFaith = Math.floor(costFaith * 0.9);
        costPop = Math.floor(costPop * 0.9);
    }
    if (god.faith < costFaith) { seal.replyToSender(ctx, msg, `信仰不足，需要 ${costFaith}`); return seal.ext.newCmdExecuteResult(true); }
    if (god.population < costPop) { seal.replyToSender(ctx, msg, `信徒不足，需要 ${costPop}`); return seal.ext.newCmdExecuteResult(true); }
    god.faith -= costFaith;
    god.population -= costPop;
    god.techAge++;
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    let msgText = `🌌 文明飞跃！你带领信徒进入了 ${next.name}！\n`;
    msgText += `消耗信仰 ${costFaith}，信徒 ${costPop}\n`;
    msgText += `解锁效果：${next.unlockFeatures.join(', ')}`;
    seal.replyToSender(ctx, msg, msgText);
    if (checkVictory(god)) {
        seal.replyToSender(ctx, msg, `🎉🎉🎉 恭喜 ${god.godName} 达成宇宙胜利！诸神为之震撼！你的名字将载入名人堂！🎉🎉🎉`);
    }
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    return seal.ext.newCmdExecuteResult(true);
};

// 购买神器
const cmd_buy_artifact = seal.ext.newCmdItemInfo();
cmd_buy_artifact.name = '神祇购买神器';
cmd_buy_artifact.help = '消耗信仰购买随机神器，增强能力';
cmd_buy_artifact.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const cost = 800;
    if (god.faith < cost) { seal.replyToSender(ctx, msg, `信仰不足，需要 ${cost}`); return seal.ext.newCmdExecuteResult(true); }
    const available = ARTIFACTS.filter(a => !god.artifacts.includes(a.id));
    if (available.length === 0) { seal.replyToSender(ctx, msg, "你已经拥有所有神器！"); return seal.ext.newCmdExecuteResult(true); }
    const artifact = available[Math.floor(Math.random() * available.length)];
    god.faith -= cost;
    god.artifacts.push(artifact.id);
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `🏺 你献祭信仰，获得神器：${artifact.name}！\n${artifact.desc}\n消耗信仰 ${cost}`);
    return seal.ext.newCmdExecuteResult(true);
};

// 排行榜
const cmd_rank = seal.ext.newCmdItemInfo();
cmd_rank.name = '神祇排行榜';
cmd_rank.help = '查看诸神实力排行（按信徒数）';
cmd_rank.solve = function(ctx, msg, argv) {
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const list = Object.values(gods).sort((a,b) => b.population - a.population);
    let txt = "🏆 诸神信徒榜\n";
    for (let i=0; i<Math.min(10, list.length); i++) {
        const g = list[i];
        const align = getAlignment(g.piety);
        txt += `${i+1}. ${g.godName} - 信徒 ${g.population} | 神格 ${g.divineLevel}级 | 时代 ${TECH_AGES[g.techAge].name} | ${align.name}\n`;
    }
    seal.replyToSender(ctx, msg, txt);
    return seal.ext.newCmdExecuteResult(true);
};

// ========== 信仰建筑系统指令 ==========
// 查看建筑
const cmd_view_buildings = seal.ext.newCmdItemInfo();
cmd_view_buildings.name = '神祇查看建筑';
cmd_view_buildings.help = '查看已建造的建筑及其效果';
cmd_view_buildings.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    let txt = `🏗️ ${god.godName} 的神域建筑\n`;
    txt += `════════════════\n`;
    let hasBuilding = false;
    for (let [key, level] of Object.entries(god.buildings)) {
        const b = BUILDINGS[key];
        if (level > 0) {
            hasBuilding = true;
            const eff = b.effect(level);
            let effDesc = "";
            if (key === "cathedral") effDesc = `信仰自动恢复 +${eff.faithRegen}/小时`;
            else if (key === "arena") effDesc = `军队攻击力 +${eff.armyAttackPercent}%`;
            else if (key === "observatory") effDesc = `随机事件概率 +${Math.round(eff.eventChanceBonus*100)}%`;
            txt += `${b.name} Lv.${level} - ${b.desc}\n   效果：${effDesc}\n`;
        }
    }
    if (!hasBuilding) txt += "暂无建筑，使用 .神祇建造 <建筑> 来建造第一座建筑。\n";
    txt += `\n可用建筑：\n`;
    txt += `• 大圣堂 - 增加信仰自动恢复 (消耗1000信仰+50信徒)\n`;
    txt += `• 演武场 - 增加军队攻击力 (消耗800信仰+40信徒)\n`;
    txt += `• 观星台 - 提高随机事件触发概率 (消耗1200信仰+60信徒)\n`;
    txt += `升级指令：.神祇升级建筑 <大圣堂/演武场/观星台>`;
    seal.replyToSender(ctx, msg, txt);
    return seal.ext.newCmdExecuteResult(true);
};

// 建造建筑
const cmd_build = seal.ext.newCmdItemInfo();
cmd_build.name = '神祇建造';
cmd_build.help = '建造信仰建筑\n用法：.神祇建造 <建筑名> (大圣堂/演武场/观星台)';
cmd_build.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 1) { seal.replyToSender(ctx, msg, "❌ 用法：.神祇建造 <大圣堂/演武场/观星台>"); return seal.ext.newCmdExecuteResult(true); }
    const buildingName = args[0];
    let buildingKey = null;
    if (buildingName === "大圣堂") buildingKey = "cathedral";
    else if (buildingName === "演武场") buildingKey = "arena";
    else if (buildingName === "观星台") buildingKey = "observatory";
    else { seal.replyToSender(ctx, msg, "建筑名无效，可选：大圣堂、演武场、观星台"); return seal.ext.newCmdExecuteResult(true); }
    if (god.buildings[buildingKey] > 0) {
        seal.replyToSender(ctx, msg, `你已经拥有${buildingName}，请使用 .神祇升级建筑 来升级。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const b = BUILDINGS[buildingKey];
    const costFaith = b.baseCost.faith;
    const costPop = b.baseCost.pop;
    if (god.faith < costFaith) { seal.replyToSender(ctx, msg, `信仰不足，需要 ${costFaith}`); return seal.ext.newCmdExecuteResult(true); }
    if (god.population < costPop) { seal.replyToSender(ctx, msg, `信徒不足，需要 ${costPop}`); return seal.ext.newCmdExecuteResult(true); }
    god.faith -= costFaith;
    god.population -= costPop;
    god.buildings[buildingKey] = 1;
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `🏗️ 成功建造 ${b.name}！消耗信仰 ${costFaith}，信徒 ${costPop}\n效果：${b.desc}`);
    return seal.ext.newCmdExecuteResult(true);
};

// 升级建筑
const cmd_upgrade_building = seal.ext.newCmdItemInfo();
cmd_upgrade_building.name = '神祇升级建筑';
cmd_upgrade_building.help = '升级信仰建筑\n用法：.神祇升级建筑 <建筑名>';
cmd_upgrade_building.solve = function(ctx, msg, argv) {
    const userId = msg.sender.userId;
    let gods = ext.storageGet(GODS_DATA_KEY);
    gods = gods ? JSON.parse(gods) : {};
    const god = gods[userId];
    if (!god) { seal.replyToSender(ctx, msg, "请先注册"); return seal.ext.newCmdExecuteResult(true); }
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 1) { seal.replyToSender(ctx, msg, "❌ 用法：.神祇升级建筑 <大圣堂/演武场/观星台>"); return seal.ext.newCmdExecuteResult(true); }
    const buildingName = args[0];
    let buildingKey = null;
    if (buildingName === "大圣堂") buildingKey = "cathedral";
    else if (buildingName === "演武场") buildingKey = "arena";
    else if (buildingName === "观星台") buildingKey = "observatory";
    else { seal.replyToSender(ctx, msg, "建筑名无效"); return seal.ext.newCmdExecuteResult(true); }
    const currentLevel = god.buildings[buildingKey];
    if (currentLevel === 0) { seal.replyToSender(ctx, msg, `你没有${buildingName}，请先建造。`); return seal.ext.newCmdExecuteResult(true); }
    const b = BUILDINGS[buildingKey];
    const costFaith = b.upgradeCost.faith;
    const costPop = b.upgradeCost.pop;
    if (god.faith < costFaith) { seal.replyToSender(ctx, msg, `信仰不足，需要 ${costFaith}`); return seal.ext.newCmdExecuteResult(true); }
    if (god.population < costPop) { seal.replyToSender(ctx, msg, `信徒不足，需要 ${costPop}`); return seal.ext.newCmdExecuteResult(true); }
    god.faith -= costFaith;
    god.population -= costPop;
    god.buildings[buildingKey]++;
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    const newLevel = god.buildings[buildingKey];
    seal.replyToSender(ctx, msg, `🏗️ ${b.name} 升级至 Lv.${newLevel}！消耗信仰 ${costFaith}，信徒 ${costPop}\n效果提升。`);
    return seal.ext.newCmdExecuteResult(true);
};

// ========== 随机事件触发函数（修改：使用调整后的权重和建筑加成）==========
function tryTriggerRandomEvent(ctx, msg, userId, god) {
    const now = Date.now();
    if (now - (god.eventLastTime || 0) < EVENT_COOLDOWN_TIME) return;
    // 建筑加成：观星台提高触发概率
    let baseTriggerChance = 0.25;
    if (god.buildings && god.buildings.observatory) {
        baseTriggerChance += BUILDINGS.observatory.effect(god.buildings.observatory).eventChanceBonus;
    }
    if (Math.random() > baseTriggerChance) return;
    const events = getAdjustedEventWeights(god);
    const totalWeight = events.reduce((s, e) => s + e.weight, 0);
    let rand = getRandomInt(1, totalWeight);
    let selected = null;
    for (let e of events) {
        if (rand <= e.weight) { selected = e; break; }
        rand -= e.weight;
    }
    if (!selected) return;
    if (selected.minPop && god.population < selected.minPop) return;
    if (selected.minFaith && god.faith < selected.minFaith) return;
    god.eventLastTime = now;
    const effectMsg = selected.effect(god);
    let artifactMsg = "";
    if (selected.artifactChance && Math.random() < selected.artifactChance) {
        const available = ARTIFACTS.filter(a => !god.artifacts.includes(a.id));
        if (available.length) {
            const art = available[Math.floor(Math.random() * available.length)];
            god.artifacts.push(art.id);
            artifactMsg = `\n🎁 额外获得神器：${art.name}！`;
        }
    }
    ext.storageSet(GODS_DATA_KEY, JSON.stringify(gods));
    seal.replyToSender(ctx, msg, `✨【随机事件】${selected.name}\n${selected.desc}\n结果：${effectMsg}${artifactMsg}`);
}

// 管理员指令：重置数据
const cmd_reset_all = seal.ext.newCmdItemInfo();
cmd_reset_all.name = '神域重置';
cmd_reset_all.help = '【管理员】清空所有神域数据';
cmd_reset_all.solve = function(ctx, msg, argv) {
    if (!isAdmin(ctx, msg.sender.userId)) { seal.replyToSender(ctx, msg, "🔒 管理员专用"); return seal.ext.newCmdExecuteResult(true); }
    ext.storageSet(GODS_DATA_KEY, JSON.stringify({}));
    seal.replyToSender(ctx, msg, "✅ 所有神域数据已重置");
    return seal.ext.newCmdExecuteResult(true);
};

// 注册指令
ext.cmdMap['神祇注册'] = cmd_register;
ext.cmdMap['神祇状态'] = cmd_status;
ext.cmdMap['神祇耕种'] = cmd_cultivate;
ext.cmdMap['神祇发展人口'] = cmd_develop;
ext.cmdMap['神祇掠夺'] = cmd_plunder;
ext.cmdMap['神祇帮助'] = cmd_help_god;
ext.cmdMap['神祇升级神格'] = cmd_upgrade_divine;
ext.cmdMap['神祇科技树'] = cmd_tech_tree;
ext.cmdMap['神祇升级科技'] = cmd_upgrade_tech;
ext.cmdMap['神祇购买神器'] = cmd_buy_artifact;
ext.cmdMap['神祇排行榜'] = cmd_rank;
ext.cmdMap['神祇查看建筑'] = cmd_view_buildings;
ext.cmdMap['神祇建造'] = cmd_build;
ext.cmdMap['神祇升级建筑'] = cmd_upgrade_building;
ext.cmdMap['神域重置'] = cmd_reset_all;

// 帮助指令（更新）
const cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = '神域帮助';
cmd_help.help = '显示所有神域指令';
cmd_help.solve = function(ctx, msg, argv) {
    const helpText = `🏛️ 神域进化·诸神文明 指令大全
════════════════════
📌 基础指令：
.神祇注册 <神名> - 创建神祇
.神祇状态 - 查看详情
.神祇耕种 - 消耗神力得信仰
.神祇发展人口 - 消耗信仰增信徒
.神祇掠夺 <神名> - 抢夺他人 (减神性)
.神祇帮助 <神名> - 帮助他人 (增神性)
.神祇升级神格 - 提升神格等级

📜 文明进化：
.神祇科技树 - 查看时代与需求
.神祇升级科技 - 进入下一时代

🏺 神器系统：
.神祇购买神器 - 随机获得神器

🏗️ 信仰建筑：
.神祇建造 <建筑> - 建造大圣堂/演武场/观星台
.神祇升级建筑 <建筑> - 提升建筑等级
.神祇查看建筑 - 查看建筑效果

🏆 其他：
.神祇排行榜 - 诸神信徒榜
.神域重置 - 管理员清空数据

💡 阵营与神性：掠夺减少神性，帮助增加神性。阵营影响随机事件倾向和专属神器。`;
    seal.replyToSender(ctx, msg, helpText);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['神域帮助'] = cmd_help;

console.log('🏛️ 神域进化·诸神文明 插件已加载（声望与建筑版）');

// ========== 管理员密码 ==========
function getAdminPassword() {
    let pwd = ext.storageGet("god_admin_password");
    if (!pwd) {
        pwd = "chaohui_admin_2025";  // 默认密码，可自行修改
        ext.storageSet("god_admin_password", pwd);
    }
    return pwd;
}

const cmd_grant_admin = seal.ext.newCmdItemInfo();
cmd_grant_admin.name = "授予管理神";
cmd_grant_admin.help = "【管理员】授予指定QQ号临时管理员权限\n用法：.授予管理神 <QQ号> <密码>";
cmd_grant_admin.solve = function(ctx, msg, argv) {
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 2) {
        seal.replyToSender(ctx, msg, "❌ 用法：.授予管理神 <QQ号> <密码>");
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetQQ = args[0];
    const inputPass = args[1];
    const platform = ctx.endPoint.platform;

    const ADMIN_SECRET = getAdminPassword();
    if (inputPass.trim() !== ADMIN_SECRET) {
        seal.replyToSender(ctx, msg, "❌ 密码错误，无法授权管理员");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 读取现有管理员列表（按平台）
    let adminListByPlatform = ext.storageGet("a_adminList");
    adminListByPlatform = adminListByPlatform ? JSON.parse(adminListByPlatform) : {};
    if (!adminListByPlatform[platform]) {
        adminListByPlatform[platform] = [];
    }

    if (!adminListByPlatform[platform].includes(targetQQ)) {
        adminListByPlatform[platform].push(targetQQ);
        ext.storageSet("a_adminList", JSON.stringify(adminListByPlatform));
        seal.replyToSender(ctx, msg, `✅ 成功将 ${targetQQ} 设为 ${platform} 平台的临时管理员`);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 已是管理员`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["授予管理神"] = cmd_grant_admin;

const cmd_revoke_admin = seal.ext.newCmdItemInfo();
cmd_revoke_admin.name = "移除管理神";
cmd_revoke_admin.help = "【管理员】移除指定QQ号的管理员权限\n用法：.移除管理神 <QQ号> <密码>";
cmd_revoke_admin.solve = function(ctx, msg, argv) {
    const args = msg.message.trim().split(/\s+/).slice(1);
    if (args.length < 2) {
        seal.replyToSender(ctx, msg, "❌ 用法：.移除管理神 <QQ号> <密码>");
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetQQ = args[0];
    const inputPass = args[1];
    const platform = ctx.endPoint.platform;

    const ADMIN_SECRET = getAdminPassword();
    if (inputPass.trim() !== ADMIN_SECRET) {
        seal.replyToSender(ctx, msg, "❌ 密码错误");
        return seal.ext.newCmdExecuteResult(true);
    }

    let adminListByPlatform = ext.storageGet("a_adminList");
    adminListByPlatform = adminListByPlatform ? JSON.parse(adminListByPlatform) : {};
    if (adminListByPlatform[platform] && adminListByPlatform[platform].includes(targetQQ)) {
        adminListByPlatform[platform] = adminListByPlatform[platform].filter(qq => qq !== targetQQ);
        ext.storageSet("a_adminList", JSON.stringify(adminListByPlatform));
        seal.replyToSender(ctx, msg, `✅ 已移除 ${targetQQ} 的管理员权限`);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 不是管理员`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["移除管理神"] = cmd_revoke_admin;