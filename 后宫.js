"use strict";
// ==UserScript==
// @name         家族经营养成 (完全重设计)
// @author       长日将尽
// @version      9.0.0
// @description  从农民到宰相，多代家族经营养成游戏
// @license      Apache-2
// ==/UserScript==

let ext = seal.ext.find("FamilyTycoon");
if (!ext) {
    ext = seal.ext.new("FamilyTycoon", "长日将尽", "9.0.0");
    seal.ext.register(ext);
}

const DATA_KEY = "family_tycoon_data";

// ========== 常量定义 ==========

// 官位等级系统
const FAMILY_RANKS = [
    { rank: 0, name: "农民", minAsset: 0, minGeneration: 1, minAge: 16, reqAttr: {} },
    { rank: 1, name: "小商人", minAsset: 1000, minGeneration: 1, minAge: 18, reqAttr: { wit: 50 } },
    { rank: 2, name: "地主", minAsset: 5000, minGeneration: 1, minAge: 20, reqAttr: { wit: 100, charm: 80 } },
    { rank: 3, name: "县令", minAsset: 20000, minGeneration: 2, minAge: 25, reqAttr: { wit: 200, talent: 150 } },
    { rank: 4, name: "州刺史", minAsset: 50000, minGeneration: 2, minAge: 30, reqAttr: { wit: 400, prestige: 300 } },
    { rank: 5, name: "侍郎", minAsset: 100000, minGeneration: 3, minAge: 35, reqAttr: { wit: 600, talent: 400, prestige: 500 } },
    { rank: 6, name: "宰相", minAsset: 200000, minGeneration: 3, minAge: 40, reqAttr: { wit: 1000, talent: 800, prestige: 1000 } }
];

// 官位收入（每年，以12个月计）
const RANK_INCOME = [100, 200, 500, 1000, 2000, 3000, 5000];

// 生命周期规则
const AGE_RULES = {
    adulthood: 16,
    reproductionMin: 16,
    reproductionMax: 50,
    deathMin: 60,
    deathMax: 80,
    maxChildren: 3
};

// 生活成本
const MONTHLY_COSTS = {
    base: 50,
    perMember: 30,
    perChild: 50
};

// 教育成本
const EDUCATION_COSTS = {
    wit: { cost: 50, gain: 2 },
    talent: { cost: 50, gain: 2 },
    charm: { cost: 30, gain: 1 }
};

// 姓氏与名字库
const SURNAMES = [
    "张", "刘", "李", "王", "赵", "孙", "周", "吴", "郑", "陈",
    "冯", "曾", "曹", "萧", "何", "邓", "范", "杨", "段", "罗"
];

const NAMES_MALE = [
    "三", "四", "五", "六", "七", "八", "九", "十", "云", "雨",
    "风", "雷", "鹤", "龙", "虎", "山", "河", "海", "天", "乾"
];

const NAMES_FEMALE = [
    "娟", "莹", "燕", "娥", "琼", "兰", "芳", "荣", "英", "茵",
    "雪", "月", "梦", "香", "芙", "妹", "文", "丽", "岚", "霞"
];

// ========== Phase 2：趣味系统常量 ==========

// 科举等级系统
const EXAM_STAGES = [
    { stage: 0, name: "童生", reqAge: 12, reqWit: 80, reqTalent: 70 },
    { stage: 1, name: "秀才", reqAge: 16, reqWit: 150, reqTalent: 130 },
    { stage: 2, name: "举人", reqAge: 20, reqWit: 250, reqTalent: 200 },
    { stage: 3, name: "进士", reqAge: 25, reqWit: 400, reqTalent: 350 }
];

// 产业系统
const INDUSTRIES = {
    farm: { name: "田地", cost: 2000, baseIncome: 500, maxOwn: 5 },
    shop: { name: "商铺", cost: 3000, baseIncome: 800, maxOwn: 3 }
};

// 书院成本
const SCHOOL_COST = 50; // 年50文

// 随机事件库
const RANDOM_EVENTS = [
    {
        name: "大旱",
        trigger: "farm",
        effect: (family) => {
            family.asset = Math.max(0, family.asset - 500);
            return "☠️ 田地遭遇大旱，损失500文！";
        }
    },
    {
        name: "丰收年",
        trigger: "farm",
        effect: (family) => {
            let gain = 800;
            family.asset += gain;
            return `🌾 田地迎来丰收年，获得${gain}文！`;
        }
    },
    {
        name: "意外之财",
        trigger: "any",
        effect: (family) => {
            family.asset += 1000;
            return "💰 捡到一只遗失的钱袋，获得1000文！";
        }
    },
    {
        name: "瘟疫",
        trigger: "any",
        effect: (family) => {
            let aliveMems = family.members.filter(m => m.alive);
            if (aliveMems.length > 0) {
                let target = aliveMems[Math.floor(Math.random() * aliveMems.length)];
                target.health = Math.max(10, target.health - 30);
                return `🤒 ${target.name}染上瘟疫，体质-30`;
            }
            return "";
        }
    },
    {
        name: "神童降世",
        trigger: "birth",
        effect: (family, child) => {
            if (child) {
                child.wit = Math.floor(child.wit * 1.3);
                child.talent = Math.floor(child.talent * 1.3);
                return `✨ ${child.name}聪慧异常，天赋超群！`;
            }
            return "";
        }
    }
];

// ========== 数据读写 ==========

function getFamilies() {
    let data = ext.storageGet(DATA_KEY);
    return data ? JSON.parse(data) : {};
}

function saveFamilies(families) {
    ext.storageSet(DATA_KEY, JSON.stringify(families));
}

// ========== 工具函数 ==========

function generateMemberId() {
    return "m_" + Date.now() + "_" + Math.floor(Math.random() * 10000);
}

function getRandomName(gender) {
    const surname = SURNAMES[Math.floor(Math.random() * SURNAMES.length)];
    const nameList = gender === "male" ? NAMES_MALE : NAMES_FEMALE;
    const name = nameList[Math.floor(Math.random() * nameList.length)];
    return surname + name;
}

function createInitialMember(familyName, familyId) {
    return {
        id: generateMemberId(),
        name: getRandomName("male"),
        generation: 1,
        birth: 0,
        age: 30,
        alive: true,
        gender: "male",
        isHead: true,
        rank: 0,
        charm: 60,
        wit: 70,
        talent: 60,
        prestige: 0,
        health: 80,
        spouse: null,
        children: [],
        deathAge: Math.floor(Math.random() * 20 + 60),
        educationInvest: { wit: 0, talent: 0, charm: 0 },
        // 科举系统
        examLevel: 0,
        examName: "无",
        // 书院系统
        inSchool: false,
        schoolYear: 0,
        academicProgress: 0
    };
}

function createInitialFamily(familyName, familyId) {
    const headMember = createInitialMember(familyName, familyId);
    return {
        familyId: familyId,
        familyName: familyName,
        headId: headMember.id,
        rank: 0,
        asset: 1000,
        prestige: 0,
        age: 0,
        members: [headMember],
        events: [],
        // 产业系统
        industries: [],
        pendingIncome: 0,
        // 事件系统
        lastEventYear: -1
    };
}

function updateFamilyAge(family) {
    family.age += 1;
    let events = [];

    // 处理成员年龄更新、学业进度、死亡
    for (let member of family.members) {
        if (!member.alive) continue;
        member.age += 1;

        // 学业进度（在校期间）
        if (member.inSchool && member.age >= 6 && member.age < 16) {
            member.academicProgress += Math.floor((member.wit + member.talent) / 10);

            // 学业满100自动毕业
            if (member.academicProgress >= 100) {
                member.inSchool = false;
                member.academicProgress = 0;
                member.examLevel = 1;
                member.examName = "秀才";
                events.push(`📚 ${member.name}从书院毕业，获得秀才身份！`);
            }
        }

        // 检查死亡
        if (member.age >= member.deathAge) {
            member.alive = false;
            events.push(`☠️ ${member.name}(${member.age}岁)去世了`);

            if (member.children.length > 0) {
                let heir = family.members.find(m => m.id === member.children[0]);
                if (heir && heir.alive) {
                    events.push(`   长子${heir.name}继承了遗产`);
                }
            }
        }
    }

    // 计算官位收入
    let income = 0;
    for (let member of family.members) {
        if (member.alive && member.rank >= 0) {
            income += RANK_INCOME[member.rank];
        }
    }
    family.asset += Math.floor(income / 12);

    // 计算产业收入
    let industryIncome = 0;
    for (let ind of family.industries) {
        let manager = family.members.find(m => m.id === ind.manager && m.alive);
        if (manager) {
            let managerBonus = ind.type === "farm"
                ? (1 + manager.wit / 1000)
                : (1 + manager.charm / 1000);
            industryIncome += Math.floor(ind.baseIncome * managerBonus / 12);
        }
    }
    family.pendingIncome = industryIncome;
    family.asset += industryIncome;

    // 计算家族支出（书院费用）
    let cost = MONTHLY_COSTS.base;
    let childCount = 0;
    for (let member of family.members) {
        if (member.alive) {
            cost += MONTHLY_COSTS.perMember;
            if (member.age < 16) childCount++;
            if (member.inSchool) cost += SCHOOL_COST / 12;
        }
    }
    cost += childCount * MONTHLY_COSTS.perChild;
    family.asset -= cost;

    // 随机事件触发（10%概率）
    if (family.lastEventYear !== family.age && Math.random() < 0.1) {
        let possibleEvents = RANDOM_EVENTS.filter(e => {
            if (e.trigger === "any") return true;
            if (e.trigger === "farm") return family.industries.some(i => i.type === "farm");
            return false;
        });

        if (possibleEvents.length > 0) {
            let evt = possibleEvents[Math.floor(Math.random() * possibleEvents.length)];
            let result = evt.effect(family);
            if (result) events.push(result);
            family.lastEventYear = family.age;
        }
    }

    if (events.length > 0) {
        family.events = events.concat(family.events || []).slice(0, 50);
    }
}

function calculateCurrentRank(member, family) {
    for (let i = FAMILY_RANKS.length - 1; i >= 0; i--) {
        const req = FAMILY_RANKS[i];
        if (member.age >= req.minAge && family.asset >= req.minAsset &&
            countGeneration(family, member) >= req.minGeneration) {
            let canPromote = true;
            for (let attr in req.reqAttr) {
                if ((member[attr] || 0) < req.reqAttr[attr]) {
                    canPromote = false;
                    break;
                }
            }
            if (canPromote) return i;
        }
    }
    return -1;
}

function countGeneration(family, member) {
    return member.generation;
}

// ========== 指令实现 ==========

// 【创建家族】
const cmd_createFamily = seal.ext.newCmdItemInfo();
cmd_createFamily.name = '创建家族';
cmd_createFamily.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    if (families[msg.sender.userId]) {
        return seal.replyToSender(ctx, msg, "👑 您已有家族，不可重复创建。");
    }

    const familyName = argv.args[0] || "新生家族";
    const family = createInitialFamily(familyName, msg.sender.userId);
    families[msg.sender.userId] = family;
    saveFamilies(families);

    let reply = `🏛️ **【家族创建成功】**\n`;
    reply += `家族名：${family.familyName}\n`;
    reply += `族长：${family.members[0].name}（30岁农民）\n`;
    reply += `初始资产：1000文\n\n`;
    reply += `📖 提示：使用 .查看族谱 了解家族信息`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看族谱】
const cmd_showFamily = seal.ext.newCmdItemInfo();
cmd_showFamily.name = '查看族谱';
cmd_showFamily.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    updateFamilyAge(family);
    saveFamilies(families);

    let reply = `🏛️ **【${family.familyName}】族谱**\n`;
    reply += `┌─ 游戏年：${family.age}\n`;
    reply += `├─ 族长：${family.members.find(m => m.isHead)?.name || "无"}\n`;
    reply += `├─ 家族等级：${FAMILY_RANKS[family.rank].name}\n`;
    reply += `├─ 资产：${family.asset}文\n`;
    reply += `├─ 声望：${family.prestige}\n`;
    reply += `└─ 成员数：${family.members.filter(m => m.alive).length}人\n\n`;

    reply += `【成员列表】\n`;
    for (let member of family.members) {
        if (!member.alive) continue;
        const rankName = FAMILY_RANKS[member.rank]?.name || "无";
        reply += `├─ ${member.name} (${member.age}岁 ${rankName}${member.spouse ? " 已婚" : ""})\n`;
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【成员信息】
const cmd_memberInfo = seal.ext.newCmdItemInfo();
cmd_memberInfo.name = '成员信息';
cmd_memberInfo.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const memberName = argv.args[0];
    if (!memberName) return seal.replyToSender(ctx, msg, "请指定成员名字");

    let member = family.members.find(m => m.name === memberName && m.alive);
    if (!member) return seal.replyToSender(ctx, msg, "找不到该成员。");

    const rankName = FAMILY_RANKS[member.rank]?.name || "无";
    let reply = `📋 **【${member.name}】信息**\n`;
    reply += `├─ 年龄：${member.age}岁\n`;
    reply += `├─ 官位：${rankName}\n`;
    reply += `├─ 性别：${member.gender === "male" ? "男" : "女"}\n`;
    reply += `├─ 心计：${member.wit}\n`;
    reply += `├─ 才华：${member.talent}\n`;
    reply += `├─ 容貌：${member.charm}\n`;
    reply += `├─ 体质：${member.health}\n`;
    reply += `├─ 威望：${member.prestige}\n`;
    if (member.spouse) {
        const spouse = family.members.find(m => m.id === member.spouse);
        reply += `├─ 配偶：${spouse?.name || "未知"}\n`;
    }
    if (member.children.length > 0) {
        reply += `└─ 子女：${member.children.map(cid => family.members.find(m => m.id === cid)?.name).join("、")}\n`;
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【生育子女】
const cmd_birthChild = seal.ext.newCmdItemInfo();
cmd_birthChild.name = '生育子女';
cmd_birthChild.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const fatherName = argv.args[0];
    if (!fatherName) return seal.replyToSender(ctx, msg, "请指定父亲名字");

    let father = family.members.find(m => m.name === fatherName && m.alive);
    if (!father) return seal.replyToSender(ctx, msg, "找不到该成员。");

    if (!father.spouse) return seal.replyToSender(ctx, msg, "该成员未婚。");
    if (father.age < AGE_RULES.reproductionMin || father.age > AGE_RULES.reproductionMax) {
        return seal.replyToSender(ctx, msg, `不在生育年龄(${AGE_RULES.reproductionMin}-${AGE_RULES.reproductionMax}岁)。`);
    }

    let children = father.children.length;
    if (children >= AGE_RULES.maxChildren) {
        return seal.replyToSender(ctx, msg, `最多生${AGE_RULES.maxChildren}个孩子。`);
    }

    let cost = 500;
    if (family.asset < cost) return seal.replyToSender(ctx, msg, `资产不足(需${cost}文)。`);

    const gender = Math.random() < 0.5 ? "male" : "female";
    const newMember = {
        id: generateMemberId(),
        name: getRandomName(gender),
        generation: father.generation + 1,
        birth: family.age,
        age: 0,
        alive: true,
        gender: gender,
        isHead: false,
        rank: 0,
        charm: Math.floor((father.charm + (family.members.find(m => m.id === father.spouse)?.charm || 60)) / 2) + Math.floor(Math.random() * 20 - 10),
        wit: Math.floor((father.wit + (family.members.find(m => m.id === father.spouse)?.wit || 70)) / 2) + Math.floor(Math.random() * 20 - 10),
        talent: Math.floor((father.talent + (family.members.find(m => m.id === father.spouse)?.talent || 60)) / 2) + Math.floor(Math.random() * 20 - 10),
        prestige: 0,
        health: 80,
        spouse: null,
        children: [],
        deathAge: Math.floor(Math.random() * 20 + 60),
        educationInvest: { wit: 0, talent: 0, charm: 0 },
        examLevel: 0,
        examName: "无",
        inSchool: false,
        schoolYear: 0,
        academicProgress: 0
    };

    father.children.push(newMember.id);
    family.members.push(newMember);
    family.asset -= cost;
    family.prestige += 5;

    saveFamilies(families);

    const genderStr = gender === "male" ? "男孩" : "女孩";
    seal.replyToSender(ctx, msg, `👶 ${father.name}和${family.members.find(m => m.id === father.spouse)?.name}诞下一位${genderStr}${newMember.name}！(资产-${cost}文)`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【家族升官】
const cmd_promote = seal.ext.newCmdItemInfo();
cmd_promote.name = '家族升官';
cmd_promote.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    let head = family.members.find(m => m.isHead && m.alive);
    if (!head) return seal.replyToSender(ctx, msg, "族长不存在。");

    const nextRank = family.rank + 1;
    if (nextRank >= FAMILY_RANKS.length) {
        return seal.replyToSender(ctx, msg, "👑 已是宰相，无法继续升官。");
    }

    const req = FAMILY_RANKS[nextRank];
    let fails = [];

    if (family.asset < req.minAsset) fails.push(`资产不足(需${req.minAsset}，有${family.asset})`);
    if (head.age < req.minAge) fails.push(`年龄不足(需${req.minAge}岁)`);
    if (countGeneration(family, head) < req.minGeneration) fails.push(`代系不足(需${req.minGeneration}代)`);

    for (let attr in req.reqAttr) {
        if ((head[attr] || 0) < req.reqAttr[attr]) {
            fails.push(`${attr}不足(需${req.reqAttr[attr]})`);
        }
    }

    if (fails.length > 0) {
        return seal.replyToSender(ctx, msg, `❌ 晋升失败：\n- ${fails.join("\n- ")}`);
    }

    family.rank = nextRank;
    family.asset -= 1000;
    family.prestige += 100;
    head.rank = nextRank;

    saveFamilies(families);
    seal.replyToSender(ctx, msg, `🎉 晋升成功！${head.name}成为${req.name}！`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【寻求配婚】
const cmd_matchmaking = seal.ext.newCmdItemInfo();
cmd_matchmaking.name = '寻求配婚';
cmd_matchmaking.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let myFamily = families[msg.sender.userId];
    if (!myFamily) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const childName = argv.args[0];
    const targetQQ = argv.args[1];
    const targetChildName = argv.args[2];

    if (!childName || !targetQQ || !targetChildName) {
        return seal.replyToSender(ctx, msg, "用法：.寻求配婚 <自己孩子名> <目标玩家QQ> <目标孩子名>");
    }

    let myChild = myFamily.members.find(m => m.name === childName && m.alive);
    if (!myChild) return seal.replyToSender(ctx, msg, "找不到您的孩子。");
    if (myChild.age < 16) return seal.replyToSender(ctx, msg, "孩子年龄不足16岁。");
    if (myChild.spouse) return seal.replyToSender(ctx, msg, "孩子已婚。");

    let targetFamily = families[targetQQ];
    if (!targetFamily) return seal.replyToSender(ctx, msg, "对方没有创建家族。");

    let targetChild = targetFamily.members.find(m => m.name === targetChildName && m.alive);
    if (!targetChild) return seal.replyToSender(ctx, msg, "对方没有该孩子。");
    if (targetChild.age < 16) return seal.replyToSender(ctx, msg, "对方孩子年龄不足。");
    if (targetChild.spouse) return seal.replyToSender(ctx, msg, "对方孩子已婚。");

    // 保存配婚请求
    targetFamily.matchingRequests = targetFamily.matchingRequests || [];
    const requestId = "req_" + Date.now();
    targetFamily.matchingRequests.push({
        id: requestId,
        fromQQ: msg.sender.userId,
        fromChildName: childName,
        fromFamilyName: myFamily.familyName,
        toChildName: targetChildName,
        createdAt: family.age
    });

    saveFamilies(families);
    seal.replyToSender(ctx, msg, `✍️ 已向${targetFamily.familyName}提出配婚请求。`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看配婚请求】
const cmd_viewMatching = seal.ext.newCmdItemInfo();
cmd_viewMatching.name = '查看配婚';
cmd_viewMatching.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const requests = family.matchingRequests || [];
    if (requests.length === 0) {
        return seal.replyToSender(ctx, msg, "暂无配婚请求。");
    }

    let reply = `💝 **【配婚请求】**\n`;
    for (let req of requests) {
        reply += `├─ [${req.id}] ${req.fromFamilyName}的${req.fromChildName} ↔️ 您的${req.toChildName}\n`;
    }
    reply += `\n用法：.同意配婚 <请求ID> 或 .拒绝配婚 <请求ID>`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【同意配婚】
const cmd_agreeMatching = seal.ext.newCmdItemInfo();
cmd_agreeMatching.name = '同意配婚';
cmd_agreeMatching.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const requestId = argv.args[0];
    if (!requestId) return seal.replyToSender(ctx, msg, "请指定请求ID");

    const requests = family.matchingRequests || [];
    const reqIdx = requests.findIndex(r => r.id === requestId);
    if (reqIdx === -1) return seal.replyToSender(ctx, msg, "找不到该请求。");

    const req = requests[reqIdx];
    const myChild = family.members.find(m => m.name === req.toChildName);

    let fromFamily = families[req.fromQQ];
    const fromChild = fromFamily.members.find(m => m.name === req.fromChildName);

    if (!myChild || !fromChild) {
        requests.splice(reqIdx, 1);
        saveFamilies(families);
        return seal.replyToSender(ctx, msg, "一方已无法参加配婚。");
    }

    // 配对成功
    myChild.spouse = fromChild.id;
    fromChild.spouse = myChild.id;
    family.prestige += 50;
    fromFamily.prestige += 50;

    requests.splice(reqIdx, 1);
    saveFamilies(families);

    seal.replyToSender(ctx, msg, `💒 ${req.fromFamilyName}的${req.fromChildName}与您的${req.toChildName}成婚！`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【拒绝配婚】
const cmd_rejectMatching = seal.ext.newCmdItemInfo();
cmd_rejectMatching.name = '拒绝配婚';
cmd_rejectMatching.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const requestId = argv.args[0];
    const requests = family.matchingRequests || [];
    const reqIdx = requests.findIndex(r => r.id === requestId);

    if (reqIdx === -1) return seal.replyToSender(ctx, msg, "找不到该请求。");

    const req = requests[reqIdx];
    requests.splice(reqIdx, 1);
    saveFamilies(families);

    seal.replyToSender(ctx, msg, `✗ 已拒绝${req.fromFamilyName}的配婚请求。`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【教育投资】
const cmd_educate = seal.ext.newCmdItemInfo();
cmd_educate.name = '教育投资';
cmd_educate.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const memberName = argv.args[0];
    const attrType = argv.args[1];

    if (!memberName || !attrType) {
        return seal.replyToSender(ctx, msg, "用法：.教育投资 <成员名> <wit/talent/charm>");
    }

    let member = family.members.find(m => m.name === memberName && m.alive);
    if (!member) return seal.replyToSender(ctx, msg, "找不到该成员。");
    if (member.age >= 16) return seal.replyToSender(ctx, msg, "只能教育未成年人。");

    const edu = EDUCATION_COSTS[attrType];
    if (!edu) return seal.replyToSender(ctx, msg, "无效的属性类型。");
    if (family.asset < edu.cost) return seal.replyToSender(ctx, msg, `资产不足(需${edu.cost}文)。`);

    member[attrType] += edu.gain;
    member.educationInvest[attrType] += edu.gain;
    family.asset -= edu.cost;

    saveFamilies(families);
    seal.replyToSender(ctx, msg, `📚 已为${member.name}进行${attrType}教育，${attrType}+${edu.gain}(消耗${edu.cost}文)`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【家族日志】
const cmd_familyLog = seal.ext.newCmdItemInfo();
cmd_familyLog.name = '家族日志';
cmd_familyLog.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const events = family.events || [];
    if (events.length === 0) {
        return seal.replyToSender(ctx, msg, "暂无事件记录。");
    }

    let reply = `📖 **【${family.familyName}日志】**\n`;
    for (let i = 0; i < Math.min(10, events.length); i++) {
        reply += `${events[i]}\n`;
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看排行榜】
const cmd_ranking = seal.ext.newCmdItemInfo();
cmd_ranking.name = '查看排行榜';
cmd_ranking.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    const type = argv.args[0] || "rank";

    let familyList = Object.values(families);
    let sorted = [];

    if (type === "rank" || type === "官位") {
        sorted = familyList.sort((a, b) => b.rank - a.rank);
        let reply = `🏆 【官位排行榜】\n`;
        for (let i = 0; i < Math.min(10, sorted.length); i++) {
            const rankName = FAMILY_RANKS[sorted[i].rank]?.name || "农民";
            reply += `${i + 1}. ${sorted[i].familyName} - ${rankName}\n`;
        }
        seal.replyToSender(ctx, msg, reply);
    } else if (type === "asset" || type === "资产") {
        sorted = familyList.sort((a, b) => b.asset - a.asset);
        let reply = `💰 【资产排行榜】\n`;
        for (let i = 0; i < Math.min(10, sorted.length); i++) {
            reply += `${i + 1}. ${sorted[i].familyName} - ${sorted[i].asset}文\n`;
        }
        seal.replyToSender(ctx, msg, reply);
    } else if (type === "generation" || type === "代系") {
        sorted = familyList.sort((a, b) => {
            const maxGenA = Math.max(...a.members.map(m => m.generation));
            const maxGenB = Math.max(...b.members.map(m => m.generation));
            return maxGenB - maxGenA;
        });
        let reply = `📊 【代系排行榜】\n`;
        for (let i = 0; i < Math.min(10, sorted.length); i++) {
            const maxGen = Math.max(...sorted[i].members.map(m => m.generation));
            reply += `${i + 1}. ${sorted[i].familyName} - 第${maxGen}代\n`;
        }
        seal.replyToSender(ctx, msg, reply);
    }

    return seal.ext.newCmdExecuteResult(true);
};

// 【送子读书】
const cmd_sendSchool = seal.ext.newCmdItemInfo();
cmd_sendSchool.name = '送子读书';
cmd_sendSchool.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const childName = argv.args[0];
    let child = family.members.find(m => m.name === childName && m.alive);
    if (!child) return seal.replyToSender(ctx, msg, "找不到该成员。");
    if (child.age < 6 || child.age > 16) return seal.replyToSender(ctx, msg, "只能送6-16岁的孩子读书。");
    if (child.inSchool) return seal.replyToSender(ctx, msg, "孩子已在校。");

    child.inSchool = true;
    child.schoolYear = 0;
    saveFamilies(families);

    seal.replyToSender(ctx, msg, `📚 ${child.name}已送入书院，开始求学之路！`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看学业】
const cmd_checkAcademic = seal.ext.newCmdItemInfo();
cmd_checkAcademic.name = '查看学业';
cmd_checkAcademic.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    updateFamilyAge(family);
    const childName = argv.args[0];
    let child = family.members.find(m => m.name === childName && m.alive);
    if (!child) return seal.replyToSender(ctx, msg, "找不到该成员。");

    if (!child.inSchool) {
        if (child.examLevel > 0) {
            return seal.replyToSender(ctx, msg, `${child.name}已从书院毕业，现在是【${child.examName}】。`);
        }
        return seal.replyToSender(ctx, msg, `${child.name}尚未入学。`);
    }

    const progress = Math.min(100, child.academicProgress);
    const years = Math.ceil(100 / Math.max(5, (child.wit + child.talent) / 10));
    const eta = Math.max(1, years - child.schoolYear);

    let reply = `📖 【${child.name}的学业】\n`;
    reply += `├─ 状态：在校\n`;
    reply += `├─ 进度：${progress}/100 (█${'█'.repeat(Math.floor(progress/10))}${'░'.repeat(10-Math.floor(progress/10))})\n`;
    reply += `├─ 资质：${child.wit + child.talent}\n`;
    reply += `└─ 预计：${eta}年毕业`;

    saveFamilies(families);
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【购买产业】
const cmd_buyIndustry = seal.ext.newCmdItemInfo();
cmd_buyIndustry.name = '购买产业';
cmd_buyIndustry.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const type = argv.args[0];
    if (!type || !INDUSTRIES[type]) {
        return seal.replyToSender(ctx, msg, "请指定产业类型：farm(田地) 或 shop(商铺)");
    }

    const ind = INDUSTRIES[type];
    const ownCount = family.industries.filter(i => i.type === type).length;

    if (ownCount >= ind.maxOwn) return seal.replyToSender(ctx, msg, `最多只能拥有${ind.maxOwn}个${ind.name}。`);
    if (family.asset < ind.cost) return seal.replyToSender(ctx, msg, `资产不足(需${ind.cost}文)。`);

    family.industries.push({
        id: "ind_" + Date.now(),
        type: type,
        manager: null,
        baseIncome: ind.baseIncome
    });
    family.asset -= ind.cost;
    saveFamilies(families);

    seal.replyToSender(ctx, msg, `✅ 购买${ind.name}成功！(消耗${ind.cost}文)`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看产业】
const cmd_checkIndustry = seal.ext.newCmdItemInfo();
cmd_checkIndustry.name = '查看产业';
cmd_checkIndustry.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    if (family.industries.length === 0) {
        return seal.replyToSender(ctx, msg, "暂无产业。");
    }

    let reply = `🏢 【产业列表】\n`;
    for (let ind of family.industries) {
        const typeName = INDUSTRIES[ind.type].name;
        const managerName = ind.manager ? family.members.find(m => m.id === ind.manager)?.name : "未分配";
        reply += `├─ ${typeName} [${ind.id.substring(0, 8)}]: 管理者${managerName}\n`;
    }
    reply += `\n待收取收益：${family.pendingIncome}文`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【分配管理】
const cmd_assignManager = seal.ext.newCmdItemInfo();
cmd_assignManager.name = '分配管理';
cmd_assignManager.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const indId = argv.args[0];
    const managerName = argv.args[1];

    if (!indId || !managerName) {
        return seal.replyToSender(ctx, msg, "用法：.分配管理 <产业ID> <成员名>");
    }

    let ind = family.industries.find(i => i.id === indId);
    if (!ind) return seal.replyToSender(ctx, msg, "找不到该产业。");

    let manager = family.members.find(m => m.name === managerName && m.alive);
    if (!manager) return seal.replyToSender(ctx, msg, "找不到该成员。");

    ind.manager = manager.id;
    saveFamilies(families);
    seal.replyToSender(ctx, msg, `✅ 已将${INDUSTRIES[ind.type].name}分配给${managerName}管理。`);
    return seal.ext.newCmdExecuteResult(true);
};

// 【科举考试】
const cmd_examTake = seal.ext.newCmdItemInfo();
cmd_examTake.name = '科举考试';
cmd_examTake.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    const memberName = argv.args[0];
    const targetStage = parseInt(argv.args[1]);

    if (!memberName || isNaN(targetStage)) {
        return seal.replyToSender(ctx, msg, "用法：.科举考试 <成员名> <目标等级0-3>");
    }

    let member = family.members.find(m => m.name === memberName && m.alive);
    if (!member) return seal.replyToSender(ctx, msg, "找不到该成员。");

    const req = EXAM_STAGES[targetStage];
    if (!req) return seal.replyToSender(ctx, msg, "无效的目标等级。");
    if (member.examLevel !== targetStage) {
        return seal.replyToSender(ctx, msg, `只能报考下一级别(当前${member.examLevel})。`);
    }

    let fails = [];
    if (member.age < req.reqAge) fails.push(`年龄不足(需${req.reqAge})`);
    if (member.wit < req.reqWit) fails.push(`心计不足(需${req.reqWit})`);
    if (member.talent < req.reqTalent) fails.push(`才华不足(需${req.reqTalent})`);

    if (fails.length > 0) {
        return seal.replyToSender(ctx, msg, `❌ 无法参加考试：\n- ${fails.join("\n- ")}`);
    }

    // 科举成功概率
    let successRate = 0.5 + (member.wit + member.talent) / 2000;
    if (Math.random() < successRate) {
        member.examLevel = targetStage + 1;
        member.examName = EXAM_STAGES[targetStage + 1]?.name || "进士";
        family.prestige += 20;
        saveFamilies(families);
        seal.replyToSender(ctx, msg, `🎉 ${member.name}科举及第！升为【${member.examName}】！`);
    } else {
        seal.replyToSender(ctx, msg, `😢 ${member.name}未能及第，明年再试吧。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

// 【家族概览】
const cmd_familyOverview = seal.ext.newCmdItemInfo();
cmd_familyOverview.name = '家族概览';
cmd_familyOverview.solve = function(ctx, msg, argv) {
    let families = getFamilies();
    let family = families[msg.sender.userId];
    if (!family) return seal.replyToSender(ctx, msg, "👑 您没有创建家族。");

    updateFamilyAge(family);
    saveFamilies(families);

    let scholars = family.members.filter(m => m.alive && m.examLevel > 0).length;
    let industries = family.industries.length;
    let aliveCount = family.members.filter(m => m.alive).length;

    let reply = `🏛️ **【${family.familyName}概览】**\n`;
    reply += `├─ 游戏年：${family.age}\n`;
    reply += `├─ 等级：${FAMILY_RANKS[family.rank].name}\n`;
    reply += `├─ 资产：${family.asset}文 (待收：${family.pendingIncome})\n`;
    reply += `├─ 成员：${aliveCount}人\n`;
    reply += `├─ 进士：${scholars}人\n`;
    reply += `├─ 产业：${industries}个\n`;
    reply += `└─ 声望：${family.prestige}`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// ========== 指令注册 ==========

ext.cmdMap['创建家族'] = cmd_createFamily;
ext.cmdMap['查看族谱'] = cmd_showFamily;
ext.cmdMap['成员信息'] = cmd_memberInfo;
ext.cmdMap['生育子女'] = cmd_birthChild;
ext.cmdMap['家族升官'] = cmd_promote;
ext.cmdMap['寻求配婚'] = cmd_matchmaking;
ext.cmdMap['查看配婚'] = cmd_viewMatching;
ext.cmdMap['同意配婚'] = cmd_agreeMatching;
ext.cmdMap['拒绝配婚'] = cmd_rejectMatching;
ext.cmdMap['教育投资'] = cmd_educate;
ext.cmdMap['家族日志'] = cmd_familyLog;
ext.cmdMap['查看排行榜'] = cmd_ranking;
ext.cmdMap['送子读书'] = cmd_sendSchool;
ext.cmdMap['查看学业'] = cmd_checkAcademic;
ext.cmdMap['购买产业'] = cmd_buyIndustry;
ext.cmdMap['查看产业'] = cmd_checkIndustry;
ext.cmdMap['分配管理'] = cmd_assignManager;
ext.cmdMap['科举考试'] = cmd_examTake;
ext.cmdMap['家族概览'] = cmd_familyOverview;
