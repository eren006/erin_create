"use strict";
// ==UserScript==
// @name         圣约翰预科高中
// @author       长日将尽
// @version      1.0.0
// @description  体验圣约翰预科高中生活 · 成绩/SAT/社团/恋爱/大学申请
// @timestamp    1750000000
// @license      Apache-2
// ==/UserScript==

let ext = seal.ext.find("StJohnsPrep");
if (!ext) {
    ext = seal.ext.new("StJohnsPrep", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

// ==================== 常量 ====================

const DATA_KEY        = "stjohns_players_v1";
const CONFIG_KEY      = "stjohns_config_v1";
const RELATION_KEY    = "stjohns_relations_v1";
const TWITTER_KEY     = "stjohns_twitter_v1";

const ENERGY_CAP               = 250;
const ENERGY_PER_HOUR          = 30;  // 在校期间每小时恢复精力
const ENERGY_PER_HOUR_HOLIDAY  = 60;  // 假期每小时恢复精力（翻倍）
const ENERGY_START             = 60;

const STRESS_CAP      = 100;
const STRESS_START    = 20;
const STRESS_PASSIVE  = 2;          // 每4小时自然+2
const STRESS_PASSIVE_INTERVAL = 4 * 3600 * 1000;

const POPULARITY_START = 50;
const POPULARITY_CAP   = 150;

const SAT_MIN = 400;
const SAT_MAX = 1600;

const GAME_DURATION_DAYS = 12;      // 12天 = 12个月（9月→8月），第10天起解锁申请

// 冷却时间（毫秒）
const CD = {
    class:       4  * 3600 * 1000,
    selfStudy:   3  * 3600 * 1000,
    satStudy:    3  * 3600 * 1000,
    satExam:     1.5 * 24 * 3600 * 1000,
    artPractice: 4  * 3600 * 1000,
    artPerform:  1.5 * 24 * 3600 * 1000,
    social:      2  * 3600 * 1000,
    post:        1.5 * 3600 * 1000,
    party:       1  * 24 * 3600 * 1000,
    clubActivity:4  * 3600 * 1000,
    election:    3.5 * 24 * 3600 * 1000,
    rest:        2  * 3600 * 1000,
    relax:       4  * 3600 * 1000,
    date:        1  * 24 * 3600 * 1000,
    interact:    2  * 3600 * 1000,  // 对每个人单独计算（好朋友缩短至1h）
    tutor:       4  * 3600 * 1000,  // 对同一人同一科目
    scavenge:    3  * 3600 * 1000,  // 拾物
    tweet:       1  * 3600 * 1000,  // 推特发帖
};

// 精力消耗
const COST = {
    class:       20,
    selfStudy:   10,
    satStudy:    25,
    satExam:     40,
    artPractice: 20,
    artPerform:  40,
    social:      15,
    post:        10,
    party:       30,
    clubActivity:25,
    election:    50,
    rest:        0,
    relax:       20,
    date:        25,
    interact:    10,
    confess:     30,
    tutor:       20,
};

// 压力增量
const STRESS_ADD = {
    class:       5,
    satStudy:    8,
    satExam:     15,
    clubActivity:3,
    election:    20,
};

// 成绩档位
const GRADE_TIERS = ["C", "C+", "B-", "B", "B+", "A-", "A", "A+"];

// 艺术等级
const ART_TIERS = ["初学", "入门", "进阶", "熟练", "精通", "大师"];

// 人气称号
const POPULARITY_TITLES = [
    { min: 0,   label: "透明人" },
    { min: 30,  label: "普通同学" },
    { min: 60,  label: "有点名气" },
    { min: 90,  label: "校园红人" },
    { min: 120, label: "风云人物" },
    { min: 150, label: "圣约翰传说" },
];

// 压力状态
const STRESS_LEVELS = [
    { min: 0,  label: "状态良好",   classDebuff: 0,   satDebuff: 0,   locked: false },
    { min: 40, label: "有点疲惫",   classDebuff: 5,   satDebuff: 0,   locked: false },
    { min: 60, label: "压力较大",   classDebuff: 15,  satDebuff: 30,  locked: false },
    { min: 80, label: "快撑不住了", classDebuff: 25,  satDebuff: 100, locked: false },
    { min: 95, label: "崩溃边缘",   classDebuff: 100, satDebuff: 100, locked: true  },
];

// 关系阶段（好朋友 ≥100 互动冷却缩短至2h）
const RELATION_STAGES = [
    { min: 0,   label: "陌生人" },
    { min: 20,  label: "普通同学" },
    { min: 40,  label: "朋友" },
    { min: 60,  label: "好朋友" },
    { min: 80,  label: "心动中" },
    { min: 100, label: "挚友",   isBestFriend: true },
];

// 学生会职位
const COUNCIL_ROLES = ["班级代表", "干事", "副主席", "主席"];
const COUNCIL_REQ   = { "班级代表": 60, "干事": 75, "副主席": 90, "主席": 110 };
const COUNCIL_REWARD= { "班级代表": 15, "干事": 25, "副主席": 40, "主席": 60 };

// 学年日历：第n天对应的月份与类型（school/winter/summer）
const DAY_CALENDAR = [
    null,
    { month: "九月",   type: "school",  label: "九月·开学季"       },
    { month: "十月",   type: "school",  label: "十月"               },
    { month: "十一月", type: "school",  label: "十一月"             },
    { month: "十二月", type: "school",  label: "十二月·期末季"     },
    { month: "寒假",   type: "winter",  label: "寒假"               },
    { month: "二月",   type: "school",  label: "二月·新学期"       },
    { month: "三月",   type: "school",  label: "三月"               },
    { month: "四月",   type: "school",  label: "四月·春假"         },
    { month: "五月",   type: "school",  label: "五月"               },
    { month: "六月",   type: "school",  label: "六月·期末季"       },
    { month: "七月",   type: "summer",  label: "暑假·七月"         },
    { month: "八月",   type: "summer",  label: "暑假·八月"         },
];

// 随机日常事件（每天首次触发，apply(player)修改数据并返回描述字符串）
const RANDOM_EVENTS = [

    // ── 测验 / 学业 ──
    { id: "quiz_drop", type: "school", weight: 3, apply: function(p) {
        const subj = ALL_SUBJECTS[randInt(0, ALL_SUBJECTS.length - 1)];
        const delta = randInt(-10, 16);
        applyGradeChange(p.grades[subj], delta);
        const openers = [
            subj + "老师走进来，放下一叠试卷。“书收起来，闭卷。”全班陷入死寂。",
            "“本周小测，现在开始。”" + subj + "老师说完就开始发卷，没有任何预兆。",
            subj + "课开头十分钟老师一直没说话，只是把题目写在了黑板上——你意识到这是考试。"
        ];
        return openers[randInt(0, 2)] + "\n" + subj + " " + (delta >= 0 ? "+" : "") + delta + " 进度";
    }},

    { id: "inspire_morning", type: "school", weight: 2, apply: function(p) {
        p.inspiredBonus = true;
        const lines = [
            "昨晚睡前突然想通了一个卡了好几天的知识点，今天上课整个人都自信了很多。",
            "早上莫名其妙早醒了一小时，脑子出奇地清醒，状态从没这么好过。",
            "在图书馆随手翻到一本书，停不下来，读到闭馆才出来——今天灵感大开。"
        ];
        return lines[randInt(0, 2)] + "\n✨ 今天上课进度额外 +30%";
    }},

    { id: "essay_moment", type: "school", weight: 2, apply: function(p) {
        const delta = randInt(8, 16);
        applyGradeChange(p.grades["English"], delta);
        return "English老师把你上周交的essay当范文在全班念了出来。你低着头，但其实在偷偷笑。\nEnglish +" + delta + " 进度";
    }},

    { id: "lab_accident", type: "school", weight: 1, apply: function(p) {
        const delta = randInt(5, 12);
        applyGradeChange(p.grades["Chemistry"], delta);
        const g = randInt(5, 10);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "Chemistry实验课上你的混合物颜色对了，但爆出一声响——老师赶过来，看了看，说“对，就是这个反应”。\nChemistry +" + delta + " 进度，压力 +" + g + "（惊吓）";
    }},

    { id: "found_notes", type: "school", weight: 1, apply: function(p) {
        const subj = ALL_SUBJECTS[randInt(0, ALL_SUBJECTS.length - 1)];
        const delta = randInt(8, 14);
        applyGradeChange(p.grades[subj], delta);
        return "图书馆还书时发现夹着上一个借阅者的笔记，字迹整洁，" + subj + "部分写得极好——你拍下来留着用了。\n" + subj + " +" + delta + " 进度";
    }},

    // ── 社交 / 人气 ──
    { id: "hallway_compliment", type: "school", weight: 2, apply: function(p) {
        const g = randInt(8, 15);
        p.popularity = Math.min(POPULARITY_CAP, p.popularity + g);
        return "走廊上一个平时不怎么说话的人叫住你，说“你上次那个观点……其实挺对的。”你走了很久才反应过来。\n人气 +" + g;
    }},

    { id: "cafeteria_disaster", type: "school", weight: 2, apply: function(p) {
        const l = randInt(6, 14);
        p.popularity = Math.max(0, p.popularity - l);
        return "午餐托盘在最受欢迎的那桌前面打翻了，全场沉默了整整两秒。你捡完之后假装很淡定地走掉，背后有人在笑。\n人气 -" + l;
    }},

    { id: "viral_moment", type: "school", weight: 1, apply: function(p) {
        const g = randInt(15, 25);
        p.popularity = Math.min(POPULARITY_CAP, p.popularity + g);
        return "不知道是谁把你今天随口说的一句话截图发到群里，评论区炸了，都在说“这也太真实了”。\n人气 +" + g;
    }},

    { id: "gossip_target", type: "school", weight: 2, apply: function(p) {
        const l = randInt(5, 12);
        p.popularity = Math.max(0, p.popularity - l);
        const g = randInt(5, 10);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "有人在传一件跟你有关的事，真假参半。你听到第三手版本时已经认不出原版了，懒得解释，但还是烦。\n人气 -" + l + "，压力 +" + g;
    }},

    // ── 压力 / 状态 ──
    { id: "deadline_pile", type: "school", weight: 2, apply: function(p) {
        const g = randInt(10, 18);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "三门作业截止日期撞在一起，College counselor还发来邮件问essay进度。能量饮料已经喝到第二罐了。\n压力 +" + g;
    }},

    { id: "counselor_talk", type: "school", weight: 2, apply: function(p) {
        const g = randInt(8, 15);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "College counselor约谈，问“目标学校想好了吗”。你说了一个名字，她停顿了一下才回答——这让你整个下午心神不宁。\n压力 +" + g;
    }},

    { id: "good_sleep", type: "any", weight: 2, apply: function(p) {
        const d = randInt(10, 18);
        p.stress = Math.max(0, p.stress - d);
        return "昨晚十点就睡了，今天早上八点醒来，脑子里一片空白——那种很舒服的空白。\n压力 -" + d;
    }},

    { id: "bad_sleep", type: "any", weight: 2, apply: function(p) {
        const g = randInt(8, 15);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "躺下来就开始想各种事，凌晨两点还没睡着。今天整个人都飘着，什么都没进脑子。\n压力 +" + g;
    }},

    // ── 社团（情境感知）──
    { id: "club_spotlight", type: "school", weight: 2, apply: function(p) {
        const clubs = Object.keys(p.clubs);
        if (!clubs.length) {
            const g = randInt(5, 10);
            p.stress = Math.min(STRESS_CAP, p.stress + g);
            return "社团招新的摊位摆满了走廊，有人递给你传单，你接过来，然后在转角丢进了垃圾桶。\n压力 +" + g + "（没有归属感）";
        }
        const club = clubs[randInt(0, clubs.length - 1)];
        const g = randInt(10, 20);
        p.popularity = Math.min(POPULARITY_CAP, p.popularity + g);
        return club + "今天贴了活动海报，有人看到后来问你“你也在里面？”——语气有点惊喜。\n人气 +" + g;
    }},

    // ── 恋人/关系（情境感知）──
    { id: "relationship_moment", type: "any", weight: 2, apply: function(p) {
        if (p.partner) {
            const d = randInt(10, 20);
            p.stress = Math.max(0, p.stress - d);
            return "TA在你的locker里塞了张便签纸，什么都没写，只有一个小星星。你站在走廊发了十秒呆。\n压力 -" + d;
        }
        const g = randInt(5, 10);
        p.popularity = Math.min(POPULARITY_CAP, p.popularity + g);
        return "有人在课上一直偷偷看你，你假装没发现，但整节课不自觉地多坐直了一点。\n人气 +" + g;
    }},

    // ── 好日子 ──
    { id: "perfect_day", type: "school", weight: 3, apply: function(p) {
        const subj = ALL_SUBJECTS[randInt(0, ALL_SUBJECTS.length - 1)];
        const delta = randInt(10, 18);
        applyGradeChange(p.grades[subj], delta);
        const d = randInt(5, 10);
        p.stress = Math.max(0, p.stress - d);
        return "食堂今天出了你最喜欢的那道菜，上午最难的那节课答得不错，回宿舍路上天很蓝。有些日子就是什么都对。\n" + subj + " +" + delta + " 进度，压力 -" + d;
    }},

    // ── 假期事件 ──
    { id: "holiday_trip", type: "holiday", weight: 3, apply: function(p) {
        const d = randInt(25, 40);
        const pop = randInt(5, 12);
        p.stress = Math.max(0, p.stress - d);
        p.popularity = Math.min(POPULARITY_CAP, p.popularity + pop);
        const trips = [
            "去了佛罗里达，在沙滩上晒了三天，手机里塞满了照片",
            "跟家人去了芝加哥，吃到了很好吃的deep dish pizza，在Lake Shore Drive吹了很久的风",
            "在纽约城区游荡了一周，去了MoMA，在Central Park坐着看了一个下午的人"
        ];
        return trips[randInt(0, 2)] + "。回来的时候感觉整个人都不一样了。\n压力 -" + d + "，人气 +" + pop + "（假期动态）";
    }},

    { id: "holiday_binge", type: "holiday", weight: 2, apply: function(p) {
        const d = randInt(15, 25);
        p.stress = Math.max(0, p.stress - d);
        return "连续三天什么都没干，刷完了一整部剧，叫了四次外卖，跟家人说“我在休息”。脑子真的空了，很好。\n压力 -" + d;
    }},

    { id: "holiday_study_guilt", type: "holiday", weight: 2, apply: function(p) {
        const subj = ALL_SUBJECTS[randInt(0, ALL_SUBJECTS.length - 1)];
        const delta = randInt(5, 10);
        applyGradeChange(p.grades[subj], delta);
        const g = randInt(5, 10);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "假期里脑子没法完全关掉，翻出课本看了两小时" + subj + "，但同时也在想很多别的事情，越想越多。\n" + subj + " +" + delta + " 进度，压力 +" + g + "（停不下来）";
    }},

    { id: "holiday_family", type: "holiday", weight: 2, apply: function(p) {
        const d = randInt(15, 25);
        p.stress = Math.max(0, p.stress - d);
        return "亲戚聚会今年没人问申请的事——可能是心照不宣，也可能是忘了。总之气氛很好，你吃了很多。\n压力 -" + d;
    }},

    { id: "holiday_common_app", type: "holiday", weight: 1, apply: function(p) {
        const g = randInt(8, 15);
        p.stress = Math.min(STRESS_CAP, p.stress + g);
        return "假期本来应该放松的，但你打开了Common App看了一眼essay进度，然后关掉，然后又打开——循环了三次。\n压力 +" + g;
    }},

    // ── 无事发生 ──
    { id: "nothing", type: "any", weight: 4, apply: function(p) { return ""; }},
];

// 可用科目
const ALL_SUBJECTS = ["English", "Math", "History", "Biology", "Chemistry", "Physics", "ForeignLanguage", "PE", "Art", "Music", "CS"];
const SUBJECT_ALIAS = {
    "english": "English", "英语": "English",
    "math": "Math", "数学": "Math",
    "history": "History", "历史": "History",
    "biology": "Biology", "生物": "Biology",
    "chemistry": "Chemistry", "化学": "Chemistry",
    "physics": "Physics", "物理": "Physics",
    "foreignlanguage": "ForeignLanguage", "fl": "ForeignLanguage", "外语": "ForeignLanguage", "法语": "ForeignLanguage", "西语": "ForeignLanguage",
    "pe": "PE", "体育": "PE",
    "art": "Art", "美术": "Art", "艺术": "Art",
    "music": "Music", "音乐": "Music",
    "cs": "CS", "计算机": "CS", "编程": "CS",
};

// ==================== WebSocket 合并转发模块 ====================

seal.ext.registerStringConfig(ext, "ws地址", "ws://localhost:3001", "OneBot 正向 WS 地址，用于发送合并转发消息");
seal.ext.registerStringConfig(ext, "ws Access token", "", "OneBot Access Token，没有则留空");

const WSM = {
    seq: 0,
    buildUrl: function() {
        let url = seal.ext.getStringConfig(ext, "ws地址") || "";
        const token = seal.ext.getStringConfig(ext, "ws Access token");
        if (url && token) url += (url.includes("?") ? "&" : "?") + "access_token=" + encodeURIComponent(token);
        return url;
    },
    request: function(postData, onResponse, onTimeout, timeoutMs) {
        if (!timeoutMs) timeoutMs = 4000;
        const echo = postData.action + "_" + Date.now() + "_" + (this.seq++);
        postData.echo = echo;
        let payload;
        try { payload = JSON.stringify(postData); } catch(e) { if (onTimeout) onTimeout(); return; }
        const url = this.buildUrl();
        if (!url) { if (onTimeout) onTimeout(); return; }
        let conn;
        try { conn = new WebSocket(url); } catch(e) { if (onTimeout) onTimeout(); return; }
        let done = false;
        const finish = function(reason) {
            if (done) return; done = true; clearTimeout(timer);
            if (conn.readyState === WebSocket.OPEN || conn.readyState === WebSocket.CONNECTING) {
                try { conn.close(1000, reason); } catch(e) {}
            }
        };
        const timer = setTimeout(function() {
            if (!done) { finish("TIMEOUT"); if (onTimeout) onTimeout(); }
        }, timeoutMs);
        conn.onopen = function() {
            try { conn.send(payload); } catch(e) { finish("SEND_ERROR"); if (onTimeout) onTimeout(); }
        };
        conn.onmessage = function(event) {
            let resp;
            try { resp = JSON.parse(event.data); } catch(e) { return; }
            if (resp.post_type === "meta_event") return;
            if (resp.echo !== echo) return;
            finish("DONE");
            try { onResponse(resp); } catch(e) {}
        };
        conn.onerror = function() {};
        conn.onclose = function(event) {
            if (!done) { done = true; clearTimeout(timer); if (onTimeout) onTimeout(); }
        };
    },
    push: function(postData) { this.request(postData, function() {}, null); }
};

function sendForwardMsg(ctx, msg, nodes, fallbackText) {
    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, fallbackText || "请在群内使用此指令。");
        return;
    }
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    WSM.request(
        { action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } },
        function(resp) {
            if (resp.status !== "ok" && resp.retcode !== 0) {
                seal.replyToSender(ctx, msg, fallbackText || "❌ 合并转发发送失败。");
            }
        },
        function() { seal.replyToSender(ctx, msg, fallbackText || "❌ WS 连接失败，请检查 ws地址 配置。"); }
    );
}

// ==================== 存储工具 ====================

function getAllPlayers() {
    const raw = ext.storageGet(DATA_KEY);
    return raw ? JSON.parse(raw) : {};
}

function saveAllPlayers(players) {
    ext.storageSet(DATA_KEY, JSON.stringify(players));
}

function getPlayer(userId) {
    return getAllPlayers()[userId] || null;
}

function savePlayer(userId, data) {
    const all = getAllPlayers();
    all[userId] = data;
    saveAllPlayers(all);
}

function getConfig() {
    const raw = ext.storageGet(CONFIG_KEY);
    const defaults = { announceGroup: null, announceEndpoint: null, adminId: null, gameStartTime: null };
    return raw ? Object.assign(defaults, JSON.parse(raw)) : defaults;
}

function saveConfig(cfg) {
    ext.storageSet(CONFIG_KEY, JSON.stringify(cfg));
}

function getTwitterData() {
    const raw = ext.storageGet(TWITTER_KEY);
    const defaults = { handles: {}, users: {}, twitterGroup: null, twitterEndpoint: null, likeCDs: {}, retweetCDs: {}, replyCDs: {} };
    return raw ? Object.assign(defaults, JSON.parse(raw)) : defaults;
}
function saveTwitterData(data) {
    ext.storageSet(TWITTER_KEY, JSON.stringify(data));
}

function getAllRelations() {
    const raw = ext.storageGet(RELATION_KEY);
    return raw ? JSON.parse(raw) : {};
}

function saveAllRelations(rels) {
    ext.storageSet(RELATION_KEY, JSON.stringify(rels));
}

// ==================== 精力工具 ====================

function calcEnergy(player) {
    const now = Date.now();
    const elapsed = now - (player.lastEnergyTime || now);
    const rate = isHoliday() ? ENERGY_PER_HOUR_HOLIDAY : ENERGY_PER_HOUR;
    const recovered = Math.floor(elapsed / 3600000) * rate;
    const energy = Math.min(ENERGY_CAP, (player.energy || 0) + recovered);
    const lastEnergyTime = (player.lastEnergyTime || now) + Math.floor(elapsed / 3600000) * 3600000;
    return { energy, lastEnergyTime };
}

function refreshEnergy(player) {
    const { energy, lastEnergyTime } = calcEnergy(player);
    player.energy = energy;
    player.lastEnergyTime = lastEnergyTime;
    return player;
}

function spendEnergy(player, amount) {
    refreshEnergy(player);
    if (player.energy < amount) return false;
    player.energy -= amount;
    return true;
}

// ==================== 压力工具 ====================

function calcStress(player) {
    const now = Date.now();
    const elapsed = now - (player.lastStressTime || now);
    const intervals = Math.floor(elapsed / STRESS_PASSIVE_INTERVAL);
    const stress = Math.min(STRESS_CAP, (player.stress || STRESS_START) + intervals * STRESS_PASSIVE);
    const lastStressTime = (player.lastStressTime || now) + intervals * STRESS_PASSIVE_INTERVAL;
    return { stress, lastStressTime };
}

function refreshStress(player) {
    const { stress, lastStressTime } = calcStress(player);
    player.stress = stress;
    player.lastStressTime = lastStressTime;
    return player;
}

function getStressLevel(stress) {
    let level = STRESS_LEVELS[0];
    for (const s of STRESS_LEVELS) {
        if (stress >= s.min) level = s;
    }
    return level;
}

// ==================== 成绩工具 ====================

function initGrades(template) {
    const grades = {};
    for (const subj of ALL_SUBJECTS) {
        const tier = (template.grades && template.grades[subj] !== undefined)
            ? template.grades[subj] : 2; // 默认 B-
        grades[subj] = { tier, progress: 0 };
    }
    return grades;
}

function applyGradeChange(gradeObj, delta) {
    gradeObj.progress += delta;
    let msg = "";
    while (gradeObj.progress >= 100 && gradeObj.tier < GRADE_TIERS.length - 1) {
        gradeObj.progress -= 100;
        gradeObj.tier++;
        msg = `升级！→ ${GRADE_TIERS[gradeObj.tier]} ↑`;
    }
    while (gradeObj.progress < 0 && gradeObj.tier > 0) {
        gradeObj.progress += 100;
        gradeObj.tier--;
        msg = `下降！→ ${GRADE_TIERS[gradeObj.tier]} ↓`;
    }
    if (gradeObj.progress < 0) gradeObj.progress = 0;
    if (gradeObj.progress >= 100 && gradeObj.tier === GRADE_TIERS.length - 1) gradeObj.progress = 99;
    return msg;
}

// ==================== 人气工具 ====================

function popularityTitle(pop) {
    let title = POPULARITY_TITLES[0].label;
    for (const p of POPULARITY_TITLES) {
        if (pop >= p.min) title = p.label;
    }
    return title;
}

// ==================== 冷却工具 ====================

function isOnCooldown(player, key) {
    const cd = CD[key];
    if (!cd) return false;
    const last = (player.cooldowns || {})[key] || 0;
    return Date.now() - last < cd;
}

function setCooldown(player, key) {
    if (!player.cooldowns) player.cooldowns = {};
    player.cooldowns[key] = Date.now();
}

function cdRemaining(player, key) {
    const cd = CD[key];
    const last = (player.cooldowns || {})[key] || 0;
    const remain = cd - (Date.now() - last);
    if (remain <= 0) return "";
    const h = Math.floor(remain / 3600000);
    const m = Math.floor((remain % 3600000) / 60000);
    return h > 0 ? `${h}小时${m}分钟` : `${m}分钟`;
}

// 动态key冷却（用于 class_科目 / club_社团 等不在CD表中的key）
function isOnCooldownMs(player, key, durationMs) {
    const last = (player.cooldowns || {})[key] || 0;
    return Date.now() - last < durationMs;
}
function cdRemainingMs(player, key, durationMs) {
    const last = (player.cooldowns || {})[key] || 0;
    const remain = durationMs - (Date.now() - last);
    if (remain <= 0) return "";
    const h = Math.floor(remain / 3600000);
    const m = Math.floor((remain % 3600000) / 60000);
    return h > 0 ? `${h}小时${m}分钟` : `${m}分钟`;
}

// 解析 @ 提及的第一个用户ID（兼容 msg.at 为字符串数组或对象数组两种格式）
function getAtTarget(msg) {
    const list = msg.at || msg.atList || [];
    if (!list.length) return null;
    const first = list[0];
    return typeof first === "string" ? first : (first?.userId || first?.id || null);
}

// 通过角色英文名查找已注册玩家，返回 {userId, player} 或 null
function getPlayerByName(nameStr) {
    if (!nameStr) return null;
    const key = NAME_TO_KEY[nameStr.trim().toLowerCase()];
    if (!key) return null;
    const all = getAllPlayers();
    for (const uid in all) {
        if (all[uid].charKey === key) return { userId: uid, player: all[uid] };
    }
    return null;
}

// 对某个目标玩家的互动冷却（key: interact_userId）
function isInteractCooldown(player, targetId) {
    const key = `interact_${targetId}`;
    const last = (player.cooldowns || {})[key] || 0;
    return Date.now() - last < CD.interact;
}

function setInteractCooldown(player, targetId) {
    if (!player.cooldowns) player.cooldowns = {};
    player.cooldowns[`interact_${targetId}`] = Date.now();
}

// ==================== 好感度工具 ====================

function getRelation(userA, userB) {
    const all = getAllRelations();
    const key = `${userA}_${userB}`;
    return all[key] || { favor: 0, lastInteract: 0, couple: false, pendingConfess: false };
}

function saveRelation(userA, userB, rel) {
    const all = getAllRelations();
    all[`${userA}_${userB}`] = rel;
    saveAllRelations(all);
}

function getRelationStage(favor) {
    let stage = RELATION_STAGES[0];
    for (const s of RELATION_STAGES) {
        if (favor >= s.min) stage = s;
    }
    return stage;
}

// ==================== 公告推送 ====================

function buildGroupId(endpointUserId, rawGroupNum) {
    var platform = String(endpointUserId || "").split(":")[0] || "QQ";
    var num = String(rawGroupNum).replace(/[^\d]/g, "");
    return platform + "-Group:" + num;
}

function sendAnnouncement(msg) {
    const cfg = getConfig();
    if (!cfg.announceGroup || !cfg.announceEndpoint) return;
    try {
        const endpoints = seal.getEndPoints();
        for (const ep of endpoints) {
            if (ep.userId === cfg.announceEndpoint) {
                const m = seal.newMessage();
                m.messageType = "group";
                m.groupId = buildGroupId(ep.userId, cfg.announceGroup);
                m.sender = { userId: ep.userId };
                const ctx = seal.createTempCtx(ep, m);
                seal.replyToSender(ctx, m, `📢【圣约翰校园快讯】\n${msg}`);
                return;
            }
        }
    } catch (e) {
        console.log("公告推送失败:", e);
    }
}

// ==================== 随机工具 ====================

function randInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

// 上课随机判定（含压力debuff）
function classRoll(stressDebuff) {
    // stressDebuff: 额外走神概率百分比
    const badExtra = stressDebuff / 100;
    const r = Math.random();
    if (r < 0.10 - badExtra * 0.5)        return { label: "开窍了！",  delta: randInt(20, 25) };
    if (r < 0.65 - badExtra * 0.3)        return { label: "认真听讲",  delta: randInt(8, 19) };
    if (r < 0.85 + badExtra * 0.2)        return { label: "走神了",    delta: -randInt(1, 5) };
    return                                        { label: "状态很差",  delta: -randInt(6, 10) };
}

// SAT备考随机（含压力debuff）
function satStudyRoll(stressDebuff) {
    const penalty = stressDebuff / 100;
    const r = Math.random();
    if (r < 0.10 - penalty * 0.3)  return { label: "融会贯通", delta: randInt(30, 50) };
    if (r < 0.70 - penalty * 0.2)  return { label: "认真刷题", delta: randInt(12, 28) };
    if (r < 0.90 + penalty * 0.1)  return { label: "走神了",   delta: randInt(0, 8) };
    return                                 { label: "状态很差", delta: -randInt(5, 15) };
}

// 艺术练习随机
function artPracticeRoll() {
    const r = Math.random();
    if (r < 0.10) return { label: "突破了！",  delta: randInt(20, 25) };
    if (r < 0.70) return { label: "认真练",    delta: randInt(8, 18) };
    if (r < 0.90) return { label: "发呆了",    delta: -randInt(2, 8) };
    return               { label: "状态很差",  delta: -randInt(8, 15) };
}

// 艺术演出随机
function artPerformRoll() {
    const r = Math.random();
    if (r < 0.20) return { label: "大获成功！",  delta: randInt(40, 60) };
    if (r < 0.60) return { label: "表现不错",    delta: randInt(20, 35) };
    if (r < 0.90) return { label: "发挥失常",    delta: -randInt(10, 20) };
    return               { label: "台上出糗…",   delta: -randInt(25, 40) };
}

// ==================== 22人角色模板 ====================
// grades: 各科初始档位索引 0=C 1=C+ 2=B- 3=B 4=B+ 5=A- 6=A 7=A+
// satProf: SAT初始熟练度
// art: { type, tier } 默认艺术方向和起始等级（tier索引）
// defaultClubs: 默认已加入社团
// defaultPath: { school, major } 默认申请目标

const CHARACTERS = {
    // ===== 男生 =====
    "james": {
        firstName: "James", lastName: "Whitfield", fullName: "James Whitfield",
        desc: "全校最受欢迎的男生，本人对此毫无自觉",
        grades: { English:4, Math:3, History:4, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:6, Art:2, Music:2, CS:3 },
        satProf: 1160,
        art: null,
        defaultClubs: ["橄榄球队"],
        defaultPath: { school: "University of Michigan", major: "Sports Science" },
    },
    "noah": {
        firstName: "Noah", lastName: "Park", fullName: "Noah Park",
        desc: "用讽刺掩盖社恐的高智商宅男",
        grades: { English:2, Math:6, History:2, Biology:2, Chemistry:3, Physics:4, ForeignLanguage:2, PE:2, Art:2, Music:2, CS:6 },
        satProf: 1280,
        art: null,
        defaultClubs: ["编程社"],
        defaultPath: { school: "MIT", major: "CS/Engineering" },
    },
    "marcus": {
        firstName: "Marcus", lastName: "Hale", fullName: "Marcus Hale",
        desc: "永远在场、永远最响、永远是话题中心",
        grades: { English:4, Math:3, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:5, Art:3, Music:3, CS:3 },
        satProf: 1160,
        art: null,
        defaultClubs: ["摄影社"],
        defaultPath: { school: "NYU", major: "Film/Media" },
    },
    "connor": {
        firstName: "Connor", lastName: "Walsh", fullName: "Connor Walsh",
        desc: "学校里最好的厨子，立志不上大学",
        grades: { English:3, Math:3, History:3, Biology:4, Chemistry:4, Physics:2, ForeignLanguage:2, PE:4, Art:2, Music:3, CS:3 },
        satProf: 1100,
        art: null,
        defaultClubs: ["烹饪社"],
        defaultPath: { school: "Culinary Institute of America", major: "Culinary Arts" },
    },
    "jasper": {
        firstName: "Jasper", lastName: "Laine", fullName: "Jasper Laine",
        desc: "彻底活在自己世界里的艺术怪孩子",
        grades: { English:3, Math:2, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:3, Art:6, Music:4, CS:3 },
        satProf: 1090,
        art: { type: "绘画", tier: 2 },
        defaultClubs: ["美术社"],
        defaultPath: { school: "Parsons School of Design", major: "Fine Arts/Design" },
    },
    "rafael": {
        firstName: "Rafael", lastName: "Moreno", fullName: "Rafael Moreno",
        desc: "大家都知道他在申藤校，本人假装不在乎",
        grades: { English:3, Math:3, History:2, Biology:6, Chemistry:5, Physics:2, ForeignLanguage:4, PE:2, Art:2, Music:2, CS:2 },
        satProf: 1220,
        art: null,
        defaultClubs: ["模拟联合国", "科学社"],
        defaultPath: { school: "Johns Hopkins", major: "Pre-Med" },
    },
    "oliver": {
        firstName: "Oliver", lastName: "Tran", fullName: "Oliver Tran",
        desc: "极度在乎别人怎么看他，但只有他自己知道",
        grades: { English:4, Math:3, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:3, Art:4, Music:3, CS:4 },
        satProf: 1170,
        art: null,
        defaultClubs: ["摄影社"],
        defaultPath: { school: "Fordham", major: "Business" },
    },
    "eliot": {
        firstName: "Eliot", lastName: "Zhao", fullName: "Eliot Zhao",
        desc: "全校最难读懂的人，不是因为他在装，是因为他真的就这样",
        grades: { English:2, Math:5, History:2, Biology:2, Chemistry:2, Physics:6, ForeignLanguage:2, PE:2, Art:2, Music:3, CS:5 },
        satProf: 1300,
        art: null,
        defaultClubs: ["编程社", "文学杂志社"],
        defaultPath: { school: "Princeton", major: "CS/Engineering" },
    },
    "theo": {
        firstName: "Theo", lastName: "Vasquez", fullName: "Theo Vasquez",
        desc: "像海绵一样吸收周围所有人，还没找到自己的形状",
        grades: { English:4, Math:2, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:6, PE:4, Art:3, Music:3, CS:2 },
        satProf: 1140,
        art: null,
        defaultClubs: ["戏剧社"],
        defaultPath: { school: "NYU", major: "Psychology" },
    },
    "callum": {
        firstName: "Callum", lastName: "Reid", fullName: "Callum Reid",
        desc: "安静但不内向，观察力强到让人有点发毛",
        grades: { English:6, Math:3, History:4, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:3, Art:2, Music:3, CS:3 },
        satProf: 1230,
        art: null,
        defaultClubs: ["校报"],
        defaultPath: { school: "Northwestern", major: "Journalism" },
    },
    "ben": {
        firstName: "Ben", lastName: "Nakamura", fullName: "Ben Nakamura",
        desc: "运动员里最爱看书，书呆子里最能打球",
        grades: { English:5, Math:3, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:2, PE:6, Art:2, Music:3, CS:3 },
        satProf: 1240,
        art: null,
        defaultClubs: ["篮球队", "文学杂志社"],
        defaultPath: { school: "Duke", major: "Political Science" },
    },
    // ===== 女生 =====
    "chloe": {
        firstName: "Chloe", lastName: "Beaumont", fullName: "Chloe Beaumont",
        desc: "自带主角光环但她自己会翻白眼",
        grades: { English:6, Math:2, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:4, PE:3, Art:3, Music:4, CS:2 },
        satProf: 1230,
        art: { type: "戏剧", tier: 1 },
        defaultClubs: ["戏剧社", "文学杂志社"],
        defaultPath: { school: "Northwestern", major: "Theater" },
    },
    "zoe": {
        firstName: "Zoe", lastName: "Hartley", fullName: "Zoe Hartley",
        desc: "学校里跑得最快的人，其他方面一律不争",
        grades: { English:2, Math:3, History:2, Biology:3, Chemistry:3, Physics:3, ForeignLanguage:2, PE:7, Art:2, Music:3, CS:3 },
        satProf: 1150,
        art: null,
        defaultClubs: ["田径队"],
        defaultPath: { school: "University of Michigan", major: "Sports Science" },
    },
    "lily": {
        firstName: "Lily", lastName: "Chen", fullName: "Lily Chen",
        desc: "所有人都喜欢她，她不知道为什么",
        grades: { English:4, Math:3, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:5, PE:3, Art:3, Music:3, CS:3 },
        satProf: 1190,
        art: null,
        defaultClubs: ["摄影社", "环保社"],
        defaultPath: { school: "Fordham", major: "Psychology" },
    },
    "sofia": {
        firstName: "Sofia", lastName: "Reyes", fullName: "Sofia Reyes",
        desc: "永远知道发生了什么，经常说出来，有时候不该说",
        grades: { English:4, Math:2, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:5, PE:3, Art:5, Music:2, CS:3 },
        satProf: 1180,
        art: { type: "摄影", tier: 1 },
        defaultClubs: ["摄影社", "模拟联合国"],
        defaultPath: { school: "Syracuse", major: "Journalism/Media" },
    },
    "vivienne": {
        firstName: "Vivienne", lastName: "Ashby", fullName: "Vivienne Ashby",
        desc: "把所有精力都放在未来上，有时候忘了活在现在",
        grades: { English:4, Math:3, History:6, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:5, PE:2, Art:2, Music:2, CS:3 },
        satProf: 1270,
        art: null,
        defaultClubs: ["模拟联合国", "辩论社"],
        defaultPath: { school: "Georgetown", major: "International Relations" },
    },
    "margot": {
        firstName: "Margot", lastName: "Seo", fullName: "Margot Seo",
        desc: "比实际年龄老很多的新生",
        grades: { English:3, Math:2, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:4, PE:2, Art:3, Music:7, CS:3 },
        satProf: 1140,
        art: { type: "大提琴", tier: 2 },
        defaultClubs: ["管弦乐团"],
        defaultPath: { school: "Juilliard", major: "Music Performance" },
    },
    "nadia": {
        firstName: "Nadia", lastName: "Okafor", fullName: "Nadia Okafor",
        desc: "对不公平有天然的雷达，会当场说出来",
        grades: { English:6, Math:3, History:5, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:4, PE:2, Art:2, Music:2, CS:3 },
        satProf: 1270,
        art: null,
        defaultClubs: ["辩论社", "校报"],
        defaultPath: { school: "Georgetown", major: "Political Science" },
    },
    "wren": {
        firstName: "Wren", lastName: "Nakamura", fullName: "Wren Nakamura",
        desc: "对所有事情都过度投入，包括放弃",
        grades: { English:4, Math:2, History:2, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:2, PE:4, Art:5, Music:5, CS:3 },
        satProf: 1160,
        art: { type: "戏剧", tier: 1 },
        defaultClubs: ["戏剧社"],
        defaultPath: { school: "NYU", major: "Film/Media" },
    },
    "amara": {
        firstName: "Amara", lastName: "Diallo", fullName: "Amara Diallo",
        desc: "新生里最淡定的，因为她见过更大的场面",
        grades: { English:4, Math:2, History:5, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:6, PE:4, Art:2, Music:2, CS:2 },
        satProf: 1240,
        art: null,
        defaultClubs: ["辩论社", "模拟联合国"],
        defaultPath: { school: "Georgetown", major: "International Relations" },
    },
    "jess": {
        firstName: "Jess", lastName: "Kim", fullName: "Jess Kim",
        desc: "所有人的好朋友，但没有最好的朋友",
        grades: { English:4, Math:4, History:3, Biology:3, Chemistry:2, Physics:2, ForeignLanguage:3, PE:3, Art:3, Music:3, CS:3 },
        satProf: 1220,
        art: null,
        defaultClubs: ["摄影社", "环保社"],
        defaultPath: { school: "Boston University", major: "Business" },
    },
    "petra": {
        firstName: "Petra", lastName: "Hoang", fullName: "Petra Hoang",
        desc: "学校里最努力的人，但努力的方向是玩",
        grades: { English:3, Math:3, History:3, Biology:2, Chemistry:2, Physics:2, ForeignLanguage:3, PE:5, Art:4, Music:4, CS:2 },
        satProf: 1110,
        art: null,
        defaultClubs: ["摄影社"],
        defaultPath: { school: "Boston University", major: "Journalism" },
    },
};

// first name → key 映射（不区分大小写）
const NAME_TO_KEY = {};
for (const [key, ch] of Object.entries(CHARACTERS)) {
    NAME_TO_KEY[ch.firstName.toLowerCase()] = key;
}

// 初始化新玩家数据
function createPlayer(userId, charKey) {
    const ch = CHARACTERS[charKey];
    return {
        userId,
        charKey,
        displayName: ch.fullName,
        registeredAt: Date.now(),
        energy: ENERGY_START,
        lastEnergyTime: Date.now(),
        stress: STRESS_START,
        lastStressTime: Date.now(),
        popularity: POPULARITY_START,
        grades: initGrades(ch),
        satProf: ch.satProf,
        satScore: null,
        art: ch.art ? { type: ch.art.type, tier: ch.art.tier, progress: 0 } : null,
        clubs: {},           // clubName → { role: "成员"|"骨干"|"负责人", progress: 0 }
        councilRole: null,
        extracurriculars: {  // 课外活动类别 → 等级 0=无 1=参与 2=骨干 3=领队
            medical: 0, cs: 0, debate: 0, media: 0,
            art: 0, music: 0, sports: 0, culinary: 0, environmental: 0,
        },
        cooldowns: {},
        partner: null,       // userId of partner
        pendingConfess: null,// { from: userId, at: timestamp }
        acceptedList: [],    // [{ school, major, fullName }]
        announcePublic: { sat: true, score: true, breakup: true },
        items: {},
    };
}

// ==================== 社团数据 ====================

const CLUBS = {
    // 开放社团
    "摄影社":     { open: true,  req: {},                         extKey: "media",       extGain: 1 },
    "环保社":     { open: true,  req: {},                         extKey: "environmental",extGain: 1 },
    "烹饪社":     { open: true,  req: {},                         extKey: "culinary",    extGain: 1 },
    "文学杂志社": { open: true,  req: {},                         extKey: "media",       extGain: 1 },
    // 门槛社团
    "辩论社":     { open: false, req: { gradeMin: { English:3 } }, extKey: "debate",     extGain: 1, popularityGain: 6 },
    "模拟联合国": { open: false, req: { gradeMin: { History:3, ForeignLanguage:3 } }, extKey: "debate", extGain: 1, popularityGain: 5 },
    "校报":       { open: false, req: { gradeMin: { English:3 } }, extKey: "media",      extGain: 1, popularityGain: 4 },
    "编程社":     { open: false, req: { gradeMin: { Math:3 } },    extKey: "cs",         extGain: 1 },
    "科学社":     { open: false, req: { gradeAnyMin: { Biology:4, Chemistry:4 } }, extKey: "medical", extGain: 1 },
    "美术社":     { open: false, req: { gradeMin: { Art:3 }, orArtTier: 1 }, extKey: "art", extGain: 1 },
    "管弦乐团":   { open: false, req: { artType: "music", artTier: 1 },       extKey: "music", extGain: 1 },
    "戏剧社":     { open: false, req: { artType: "perform", artTier: 1 },     extKey: "art", extGain: 1, popularityGain: 4 },
    // 高门槛
    "橄榄球队":   { open: false, req: { gradeMin: { PE:5 }, popularityMin: 40 }, extKey: "sports", extGain: 1, popularityGain: 8 },
    "田径队":     { open: false, req: { gradeMin: { PE:5 } },                    extKey: "sports", extGain: 1, popularityGain: 6 },
    "篮球队":     { open: false, req: { gradeMin: { PE:6 }, popularityMin: 50 }, extKey: "sports", extGain: 1, popularityGain: 8 },
};

const CLUB_NAMES = Object.keys(CLUBS);

// 艺术类型归类（用于管弦/戏剧入团检查）
const ART_TYPE_MAP = {
    music:   ["钢琴","小提琴","大提琴","长笛","吉他","声乐","作曲"],
    perform: ["戏剧","舞蹈"],
    visual:  ["绘画","摄影","雕塑","陶艺","数字艺术"],
};

function artCategory(type) {
    for (const [cat, list] of Object.entries(ART_TYPE_MAP)) {
        if (list.includes(type)) return cat;
    }
    return "visual";
}

// 检查社团入门条件
function canJoinClub(player, clubName) {
    const club = CLUBS[clubName];
    if (!club) return { ok: false, reason: "社团不存在" };
    if (player.clubs[clubName]) return { ok: false, reason: "你已经是该社团成员" };

    const req = club.req || {};

    // 成绩门槛（所有满足）
    // 注意：如果有 orArtTier，Art成绩由下方 OR 逻辑单独处理，此处跳过 Art
    if (req.gradeMin) {
        for (const [subj, minTier] of Object.entries(req.gradeMin)) {
            if (req.orArtTier !== undefined && subj === "Art") continue;
            if ((player.grades[subj]?.tier ?? 0) < minTier) {
                return { ok: false, reason: `需要 ${subj} 达到 ${GRADE_TIERS[minTier]} 以上` };
            }
        }
    }
    // 成绩门槛（任意一个满足）
    if (req.gradeAnyMin) {
        const ok = Object.entries(req.gradeAnyMin).some(([subj, minTier]) =>
            (player.grades[subj]?.tier ?? 0) >= minTier
        );
        if (!ok) {
            const subjList = Object.entries(req.gradeAnyMin).map(([s, t]) => `${s}≥${GRADE_TIERS[t]}`).join(" 或 ");
            return { ok: false, reason: `需要 ${subjList}` };
        }
    }
    // 人气门槛
    if (req.popularityMin && player.popularity < req.popularityMin) {
        return { ok: false, reason: `需要人气 ≥ ${req.popularityMin}` };
    }
    // 艺术门槛
    if (req.artType) {
        if (!player.art) return { ok: false, reason: "需要先选择艺术方向" };
        if (artCategory(player.art.type) !== req.artType) {
            return { ok: false, reason: `需要音乐/表演方向的艺术天赋` };
        }
        if (player.art.tier < (req.artTier || 0)) {
            return { ok: false, reason: `需要艺术等级 ≥ ${ART_TIERS[req.artTier]}` };
        }
    }
    // 美术社特殊：Art成绩 ≥ gradeMin.Art 或 视觉艺术天赋 ≥ orArtTier（OR关系）
    if (req.orArtTier !== undefined) {
        const artGrade = player.grades["Art"]?.tier ?? 0;
        const artMinTier = req.gradeMin?.Art ?? 0;
        const hasArt = player.art && artCategory(player.art.type) === "visual" && player.art.tier >= req.orArtTier;
        if (artGrade < artMinTier && !hasArt) {
            return { ok: false, reason: `需要 Art≥${GRADE_TIERS[artMinTier]} 或 视觉艺术天赋≥${ART_TIERS[req.orArtTier]}` };
        }
    }
    return { ok: true };
}

// ==================== 学校/专业数据 ====================

const COLLEGES = {
    // ===== T1 藤校/顶尖 =====
    "Harvard": {
        tier: 1, fullName: "Harvard University",
        majors: {
            "Pre-Med":              { gpa: 3.90, sat: 1520, grades: { Biology:6, Chemistry:6 }, ext: { medical: 3 } },
            "CS":                   { gpa: 3.90, sat: 1540, grades: { Math:7, Physics:5 },      ext: { cs: 3 } },
            "Economics":            { gpa: 3.88, sat: 1520, grades: { Math:6, English:5 },      ext: {} },
            "Political Science":    { gpa: 3.88, sat: 1510, grades: { History:6, English:6 },   ext: { debate: 3 }, council: "干事" },
            "Psychology":           { gpa: 3.88, sat: 1500, grades: { Biology:5, English:5 },   ext: {} },
        },
    },
    "Yale": {
        tier: 1, fullName: "Yale University",
        majors: {
            "Political Science":    { gpa: 3.88, sat: 1510, grades: { History:6, English:6 },   ext: { debate: 2 } },
            "Fine Arts":            { gpa: 3.65, sat: 1380, grades: { Art:5 },                  ext: { art: 3 }, artReq: { type: "visual", tier: 2 } },
            "Drama":                { gpa: 3.50, sat: 1320, grades: {},                         ext: { art: 3 }, artReq: { type: "perform", tier: 3 } },
            "Environmental Science":{ gpa: 3.82, sat: 1490, grades: { Biology:6, Chemistry:5 }, ext: {} },
            "Economics":            { gpa: 3.88, sat: 1520, grades: { Math:6 },                 ext: {} },
        },
    },
    "Columbia": {
        tier: 1, fullName: "Columbia University",
        majors: {
            "Journalism":           { gpa: 3.80, sat: 1480, grades: { English:6 },              ext: { media: 2 } },
            "Political Science":    { gpa: 3.82, sat: 1490, grades: { History:6, English:5 },   ext: { debate: 2 } },
            "CS":                   { gpa: 3.82, sat: 1500, grades: { Math:6 },                 ext: { cs: 2 } },
            "Pre-Med":              { gpa: 3.88, sat: 1520, grades: { Biology:6, Chemistry:6 }, ext: { medical: 3 } },
            "Architecture":         { gpa: 3.78, sat: 1460, grades: { Math:5, Art:5 },          ext: {} },
        },
    },
    "Princeton": {
        tier: 1, fullName: "Princeton University",
        majors: {
            "CS/Engineering":       { gpa: 3.92, sat: 1560, grades: { Math:7, Physics:6 },      ext: { cs: 3 } },
            "Economics":            { gpa: 3.88, sat: 1530, grades: { Math:6, History:5 },      ext: {} },
            "International Relations":{ gpa: 3.88, sat: 1520, grades: { History:6, ForeignLanguage:6 }, ext: { debate: 3 }, council: "干事" },
            "Psychology":           { gpa: 3.82, sat: 1500, grades: { Biology:5 },              ext: {} },
        },
    },
    "MIT": {
        tier: 1, fullName: "MIT",
        majors: {
            "CS/Engineering":       { gpa: 3.93, sat: 1570, grades: { Math:7, Physics:6 },      ext: { cs: 3 } },
            "Architecture":         { gpa: 3.88, sat: 1520, grades: { Math:6, Art:5 },          ext: {} },
            "Environmental Science":{ gpa: 3.82, sat: 1490, grades: { Biology:6, Chemistry:5 }, ext: {} },
        },
    },
    "Stanford": {
        tier: 1, fullName: "Stanford University",
        majors: {
            "CS":                   { gpa: 3.92, sat: 1560, grades: { Math:7 },                 ext: { cs: 3 } },
            "Pre-Med":              { gpa: 3.92, sat: 1550, grades: { Biology:7, Chemistry:6 }, ext: { medical: 3 } },
            "Business":             { gpa: 3.88, sat: 1530, grades: { Math:6, English:5 },      ext: {}, council: "副主席" },
            "Psychology":           { gpa: 3.88, sat: 1510, grades: { Biology:5 },              ext: {} },
        },
    },
    // ===== T2 顶尖非藤 =====
    "Georgetown": {
        tier: 2, fullName: "Georgetown University",
        majors: {
            "International Relations":{ gpa: 3.65, sat: 1400, grades: { History:5, ForeignLanguage:5 }, ext: { debate: 2 } },
            "Political Science":    { gpa: 3.65, sat: 1390, grades: { History:5, English:5 },   ext: { debate: 2 } },
            "Business":             { gpa: 3.60, sat: 1360, grades: { Math:4, English:4 },      ext: {} },
            "Pre-Med":              { gpa: 3.72, sat: 1420, grades: { Biology:5, Chemistry:5 }, ext: { medical: 2 } },
            "Law":                  { gpa: 3.68, sat: 1400, grades: { History:6, English:6 },   ext: { debate: 2 }, council: "班级代表" },
        },
    },
    "Northwestern": {
        tier: 2, fullName: "Northwestern University",
        majors: {
            "Journalism":           { gpa: 3.68, sat: 1420, grades: { English:6 },              ext: { media: 2 }, council: "班级代表" },
            "CS":                   { gpa: 3.72, sat: 1440, grades: { Math:5 },                 ext: { cs: 2 } },
            "Theater":              { gpa: 3.45, sat: 1280, grades: {},                         ext: { art: 2 }, artReq: { type: "perform", tier: 2 } },
            "Psychology":           { gpa: 3.65, sat: 1390, grades: { Biology:4 },              ext: {} },
            "Economics":            { gpa: 3.68, sat: 1410, grades: { Math:5 },                 ext: {} },
        },
    },
    "NYU": {
        tier: 2, fullName: "New York University",
        majors: {
            "Film/Media":           { gpa: 3.45, sat: 1270, grades: { English:5 },              ext: { media: 2 } },
            "Business":             { gpa: 3.55, sat: 1320, grades: { Math:4 },                 ext: {} },
            "CS":                   { gpa: 3.58, sat: 1360, grades: { Math:5 },                 ext: { cs: 2 } },
            "Fine Arts":            { gpa: 3.30, sat: 1180, grades: { Art:5 },                  ext: { art: 2 }, artReq: { type: "visual", tier: 2 } },
            "Psychology":           { gpa: 3.45, sat: 1280, grades: { Biology:4 },              ext: {} },
        },
    },
    "Duke": {
        tier: 2, fullName: "Duke University",
        majors: {
            "Pre-Med":              { gpa: 3.78, sat: 1460, grades: { Biology:6, Chemistry:5 }, ext: { medical: 2 } },
            "CS/Engineering":       { gpa: 3.72, sat: 1450, grades: { Math:6, Physics:5 },      ext: { cs: 2 } },
            "Environmental Science":{ gpa: 3.65, sat: 1390, grades: { Biology:5 },              ext: {} },
            "Political Science":    { gpa: 3.68, sat: 1400, grades: { History:5 },              ext: {} },
        },
    },
    "Johns Hopkins": {
        tier: 2, fullName: "Johns Hopkins University",
        majors: {
            "Pre-Med":              { gpa: 3.82, sat: 1500, grades: { Biology:6, Chemistry:6 }, ext: { medical: 2 } },
            "CS/Engineering":       { gpa: 3.78, sat: 1470, grades: { Math:6, Physics:5 },      ext: { cs: 2 } },
            "International Relations":{ gpa: 3.68, sat: 1410, grades: { History:5, ForeignLanguage:5 }, ext: { debate: 2 } },
            "Psychology":           { gpa: 3.72, sat: 1430, grades: { Biology:5 },              ext: {} },
        },
    },
    // ===== T3 好学校 =====
    "Boston University": {
        tier: 3, fullName: "Boston University",
        majors: {
            "Journalism":           { gpa: 3.20, sat: 1200, grades: { English:4 },              ext: { media: 1 } },
            "Business":             { gpa: 3.20, sat: 1200, grades: { Math:4 },                 ext: {} },
            "CS":                   { gpa: 3.30, sat: 1240, grades: { Math:4 },                 ext: {} },
            "Pre-Med":              { gpa: 3.55, sat: 1320, grades: { Biology:4, Chemistry:4 }, ext: { medical: 1 } },
            "Fine Arts":            { gpa: 3.00, sat: 1080, grades: { Art:4 },                  ext: { art: 1 } },
        },
    },
    "Fordham": {
        tier: 3, fullName: "Fordham University",
        majors: {
            "Business":             { gpa: 3.10, sat: 1160, grades: { Math:3 },                 ext: {} },
            "Law/Political Science":{ gpa: 3.20, sat: 1200, grades: { History:4, English:4 },   ext: { debate: 1 } },
            "Journalism":           { gpa: 3.10, sat: 1160, grades: { English:4 },              ext: { media: 1 } },
            "Psychology":           { gpa: 3.10, sat: 1140, grades: { Biology:3 },              ext: {} },
            "International Relations":{ gpa: 3.20, sat: 1180, grades: { History:4, ForeignLanguage:4 }, ext: {} },
        },
    },
    "Syracuse": {
        tier: 3, fullName: "Syracuse University",
        majors: {
            "Journalism/Media":     { gpa: 2.95, sat: 1120, grades: { English:4 },              ext: { media: 1 } },
            "Architecture":         { gpa: 3.20, sat: 1200, grades: { Math:4 },                 ext: {} },
            "Business":             { gpa: 2.95, sat: 1100, grades: { Math:3 },                 ext: {} },
            "CS":                   { gpa: 3.10, sat: 1160, grades: { Math:4 },                 ext: {} },
            "Fine Arts":            { gpa: 2.75, sat: 1020, grades: { Art:4 },                  ext: { art: 1 } },
        },
    },
    "University of Michigan": {
        tier: 3, fullName: "University of Michigan",
        majors: {
            "CS/Engineering":       { gpa: 3.55, sat: 1360, grades: { Math:5, Physics:4 },      ext: { cs: 2 } },
            "Business":             { gpa: 3.45, sat: 1300, grades: { Math:4 },                 ext: {} },
            "Pre-Med":              { gpa: 3.60, sat: 1350, grades: { Biology:5, Chemistry:4 }, ext: { medical: 1 } },
            "Sports Science":       { gpa: 3.00, sat: 1100, grades: { PE:6 },                   ext: { sports: 3 } },
        },
    },
    "Tufts": {
        tier: 3, fullName: "Tufts University",
        majors: {
            "International Relations":{ gpa: 3.40, sat: 1280, grades: { History:5, ForeignLanguage:5 }, ext: {} },
            "Pre-Med":              { gpa: 3.55, sat: 1320, grades: { Biology:5, Chemistry:4 }, ext: { medical: 1 } },
            "Environmental Science":{ gpa: 3.38, sat: 1250, grades: { Biology:4 },              ext: {} },
            "Psychology":           { gpa: 3.38, sat: 1250, grades: { Biology:4 },              ext: {} },
        },
    },
    // ===== T4 保底/特招 =====
    "SUNY Stony Brook": {
        tier: 4, fullName: "SUNY Stony Brook",
        majors: {
            "CS":                   { gpa: 2.75, sat: 1020, grades: { Math:3 },                 ext: {} },
            "Pre-Med":              { gpa: 3.20, sat: 1160, grades: { Biology:4, Chemistry:3 }, ext: {} },
            "Business":             { gpa: 2.70, sat: 1000, grades: { Math:3 },                 ext: {} },
            "Environmental Science":{ gpa: 2.70, sat: 1000, grades: { Biology:3 },              ext: {} },
        },
    },
    "Culinary Institute of America": {
        tier: 4, fullName: "Culinary Institute of America",
        majors: {
            "Culinary Arts":        { gpa: 2.50, sat: 950,  grades: {},                         ext: { culinary: 3 } },
            "Hospitality Management":{ gpa: 2.50, sat: 960, grades: {},                         ext: { culinary: 1 } },
        },
    },
    "Juilliard": {
        tier: 4, fullName: "The Juilliard School",
        majors: {
            "Music Performance":    { gpa: 2.80, sat: 1040, grades: {},                         ext: { music: 3 }, artReq: { type: "music", tier: 5 } },
            "Drama":                { gpa: 2.80, sat: 1020, grades: {},                         ext: { art: 3 },   artReq: { type: "perform", tier: 4 } },
            "Dance":                { gpa: 2.80, sat: 1000, grades: { PE:5 },                   ext: { sports: 2 }, artReq: { type: "perform", tier: 3 } },
        },
    },
    "Parsons School of Design": {
        tier: 4, fullName: "Parsons School of Design",
        majors: {
            "Fine Arts/Design":     { gpa: 2.75, sat: 1020, grades: { Art:5 },                  ext: { art: 2 }, artReq: { type: "visual", tier: 3 } },
            "Fashion Design":       { gpa: 2.65, sat: 980,  grades: { Art:4 },                  ext: { art: 1 } },
            "Architecture":         { gpa: 2.95, sat: 1060, grades: { Math:3, Art:5 },          ext: {} },
        },
    },
};

const COLLEGE_NAMES = Object.keys(COLLEGES);

// ==================== 拾物系统数据 ====================

const COLLECTIBLES = [
    // common — weight 5
    { id: "old_notes",    name: "旧笔记本",   emoji: "📒", rarity: "common",    weight: 5, desc: "上一届学长留下的英语笔记，密密麻麻全是注释。" },
    { id: "coffee_cup",   name: "联名咖啡杯", emoji: "☕", rarity: "common",    weight: 5, desc: "校园咖啡店限定款，印着校徽，已经不再续售。", effect: { type: "energy", value: 25 } },
    { id: "guitar_pick",  name: "吉他拨片",   emoji: "🎸", rarity: "common",    weight: 5, desc: "管弦乐团练习室地板上捡到的，有个小缺口。" },
    { id: "old_newspaper",name: "旧校报",     emoji: "📰", rarity: "common",    weight: 5, desc: "2019年的校报，头版是一张毕业合影，有人在上面划了名字。" },
    { id: "team_badge",   name: "队徽",       emoji: "🏈", rarity: "common",    weight: 5, desc: "橄榄球队旧版队徽，停产多年，不知从哪里掉出来的。" },
    { id: "pressed_flower",name:"压花书签",   emoji: "🌸", rarity: "common",    weight: 5, desc: "一枝紫藤花，压在《了不起的盖茨比》第87页。" },
    { id: "pencil_box",   name: "复古铅笔盒", emoji: "✏️", rarity: "common",    weight: 5, desc: "里面还有半截橡皮和三支铅笔，其中一支折了。" },
    // rare — weight 2
    { id: "polaroid",     name: "宝丽来照片", emoji: "📸", rarity: "rare",      weight: 2, desc: "照片背面写着 2021/05/12。图像有些模糊，但能看出笑脸。" },
    { id: "trophy_shard", name: "奖杯碎片",   emoji: "🏆", rarity: "rare",      weight: 2, desc: "学生会柜子深处的破碎奖杯，奖项名称已磨损。", effect: { type: "stress", value: -20 } },
    { id: "love_letter",  name: "匿名情书",   emoji: "💌", rarity: "rare",      weight: 2, desc: "夹在图书馆偏僻角落的书里，不知道写给谁，也不知谁写的。" },
    { id: "lab_notebook", name: "实验记录本", emoji: "🔬", rarity: "rare",      weight: 2, desc: "布满奇怪化学符号，最后一页写着 'It works!!'。", effect: { type: "grade", subj: "Chemistry", value: 15 } },
    { id: "sheet_music",  name: "手写乐谱",   emoji: "🎵", rarity: "rare",      weight: 2, desc: "蝇头小字，最后一行有个墨水污点，却是最完整的部分。", effect: { type: "art_progress", value: 20 } },
    { id: "mystery_recipe",name:"神秘食谱",   emoji: "🍕", rarity: "rare",      weight: 2, desc: "Connor坚称这不是他奶奶的配方，但他看到它时表情出卖了他。", effect: { type: "stress", value: -25 } },
    // legendary — weight 1
    { id: "gold_star",    name: "金色星星",   emoji: "⭐", rarity: "legendary", weight: 1, desc: "不知道从哪里来的，但拿在手里有种莫名的安心感。", effect: { type: "all_grades", value: 8 } },
    { id: "mystery_key",  name: "神秘钥匙",   emoji: "🗝️", rarity: "legendary", weight: 1, desc: "没有任何标签，试过所有门都打不开。也许开的是别的什么。" },
    { id: "drama_mask",   name: "戏剧面具",   emoji: "🎭", rarity: "legendary", weight: 1, desc: "上届戏剧社演出道具，内侧铅笔签满了演员名字。", effect: { type: "popularity", value: 20 } },
];
const COLLECTIBLE_MAP = {};
COLLECTIBLES.forEach(function(c) { COLLECTIBLE_MAP[c.id] = c; });

// GPA换算（成绩档位平均 → GPA）
const TIER_TO_GPA = [1.7, 2.0, 2.3, 2.7, 3.0, 3.3, 3.7, 4.0];

function calcGPA(grades) {
    const tiers = ALL_SUBJECTS
        .filter(s => grades[s])
        .map(s => grades[s].tier);
    if (!tiers.length) return 0;
    const avg = tiers.reduce((a, b) => a + b, 0) / tiers.length;
    return TIER_TO_GPA[Math.round(avg)] || (avg * 0.4 + 1.0);
}

// 课外等级标签
const EXT_LABELS = ["无", "参与", "骨干", "领队"];

// ==================== 全局游戏时间（所有玩家共享）====================

function daysElapsed() {
    const start = getConfig().gameStartTime;
    if (!start) return 0;
    return (Date.now() - start) / (24 * 3600 * 1000);
}

// 当前是第几月（1–12），未开学返回 0
function getGameDay() {
    if (!getConfig().gameStartTime) return 0;
    return Math.min(12, Math.max(1, Math.floor(daysElapsed()) + 1));
}

function getDayInfo(day) {
    if (!day || day === 0) return { month: "学期前", type: "pre", label: "【学期尚未开始】" };
    return DAY_CALENDAR[Math.max(1, Math.min(12, day))];
}

function isHoliday() {
    const day = getGameDay();
    if (day === 0) return false;
    const t = getDayInfo(day).type;
    return t === "winter" || t === "summer";
}

// 学期是否已开始
function gameStarted() {
    return !!getConfig().gameStartTime;
}

// ==================== 管理员工具 ====================

function isAdmin(userId) {
    const cfg = getConfig();
    if (!cfg.adminId) return false;
    var strip = function(id) { return String(id || "").replace(/^[A-Za-z0-9_\-]+:/, ""); };
    return cfg.adminId === userId || strip(cfg.adminId) === strip(userId);
}

// ==================== 每日随机事件 ====================

// 每天首次触发随机事件，返回事件描述（空字符串=今天没事件 or 已触发）
function checkDailyEvent(player) {
    const today = getGameDay();
    if (today === 0 || player.lastEventDay === today) return "";
    player.lastEventDay = today;

    const holiday = isHoliday();
    const pool = RANDOM_EVENTS.filter(function(e) {
        return e.type === "any" ||
               (e.type === "school" && !holiday) ||
               (e.type === "holiday" && holiday);
    });
    const total = pool.reduce(function(s, e) { return s + e.weight; }, 0);
    let r = Math.random() * total;
    let chosen = pool[pool.length - 1];
    for (let i = 0; i < pool.length; i++) {
        r -= pool[i].weight;
        if (r <= 0) { chosen = pool[i]; break; }
    }
    const text = chosen.apply(player);
    return text ? `📅【今日事件】${text}` : "";
}

// ==================== 指令：注册 ====================

const cmd_register = seal.ext.newCmdItemInfo();
cmd_register.name = "圣约翰注册";
cmd_register.help = "用法：.圣约翰注册 <英文名>\n例：.圣约翰注册 Noah\n使用22位角色之一的first name注册入学。";
cmd_register.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    if (getPlayer(userId)) {
        seal.replyToSender(ctx, msg, "🏫 你已经注册过圣约翰了！发送 .圣约翰档案 查看状态。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const name = (argv.getArgN(1) || "").trim().toLowerCase();
    if (!name) {
        seal.replyToSender(ctx, msg, "❌ 用法：.圣约翰注册 <英文名>\n可选角色：James · Noah · Marcus · Connor · Jasper · Rafael · Oliver · Eliot · Theo · Callum · Ben · Chloe · Zoe · Lily · Sofia · Vivienne · Margot · Nadia · Wren · Amara · Jess · Petra");
        return seal.ext.newCmdExecuteResult(true);
    }
    const charKey = NAME_TO_KEY[name];
    if (!charKey) {
        seal.replyToSender(ctx, msg, `❌ 没有找到角色"${name}"。\n可选：James · Noah · Marcus · Connor · Jasper · Rafael · Oliver · Eliot · Theo · Callum · Ben · Chloe · Zoe · Lily · Sofia · Vivienne · Margot · Nadia · Wren · Amara · Jess · Petra`);
        return seal.ext.newCmdExecuteResult(true);
    }
    // 检查角色是否已被占用
    const all = getAllPlayers();
    for (const p of Object.values(all)) {
        if (p.charKey === charKey) {
            seal.replyToSender(ctx, msg, `❌ ${CHARACTERS[charKey].fullName} 已被其他玩家注册。`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }
    const player = createPlayer(userId, charKey);
    const ch = CHARACTERS[charKey];
    // 初始化默认社团（直接加入，不消耗精力）
    for (const club of ch.defaultClubs) {
        if (CLUBS[club]) {
            player.clubs[club] = { role: "成员", progress: 0 };
            const extKey = CLUBS[club].extKey;
            if (extKey) player.extracurriculars[extKey] = Math.max(player.extracurriculars[extKey], 1);
        }
    }
    savePlayer(userId, player);

    const defaultPath = ch.defaultPath;
    const artLine = ch.art ? `\n🎨 艺术方向：${ch.art.type}（${ART_TIERS[ch.art.tier]}）` : "";
    seal.replyToSender(ctx, msg,
        `🏫【圣约翰预科高中 · 入学通知】\n\n` +
        `欢迎，${ch.fullName}！\n${ch.desc}\n\n` +
        `📋 初始状态\n` +
        `精力：${ENERGY_START}/${ENERGY_CAP}　压力：${STRESS_START}　人气：${POPULARITY_START}\n` +
        `SAT熟练度：${ch.satProf}${artLine}\n` +
        `默认社团：${ch.defaultClubs.join("、")}\n\n` +
        `🎯 默认路线：${defaultPath.school} · ${defaultPath.major}\n\n` +
        `学年共12个月，六月（第10月）起可申请大学，加油！\n` +
        `输入 .圣约翰档案 查看完整状态，.圣约翰专业 查看所有申请要求。`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰注册"] = cmd_register;

// ==================== 指令：档案 ====================

const cmd_profile = seal.ext.newCmdItemInfo();
cmd_profile.name = "圣约翰档案";
cmd_profile.help = "查看当前角色的完整状态档案。";
cmd_profile.solve = function(ctx, msg, argv) {
    try {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) {
        seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 <英文名> 入学。");
        return seal.ext.newCmdExecuteResult(true);
    }
    try { checkRelationDecay(userId); } catch(e) {}
    player = refreshEnergy(player);
    player = refreshStress(player);
    const eventText = checkDailyEvent(player);
    savePlayer(userId, player);

    const ch = CHARACTERS[player.charKey];
    const gpa = calcGPA(player.grades).toFixed(2);
    const stressLevel = getStressLevel(player.stress);
    const currentDayInfo = getDayInfo(getGameDay());
    const daysLeft = Math.max(0, 10 - getGameDay());
    const applyStatus = !gameStarted() ? "（学期尚未开始）" : getGameDay() >= 10 ? "✅ 可申请大学" : ("距申请还剩 " + daysLeft + " 月");

    // 成绩行
    const gradeLines = ALL_SUBJECTS.map(function(s) {
        const g = player.grades[s];
        const pad = s.length >= 16 ? s : (s + "                ").slice(0, 16);
        return "  " + pad + " " + GRADE_TIERS[g.tier] + " (" + g.progress + "/100)";
    }).join("\n");

    // 社团行
    const clubEntries = Object.keys(player.clubs);
    const clubLines = clubEntries.length
        ? clubEntries.map(function(c) { return "  " + c + " · " + player.clubs[c].role; }).join("\n")
        : "  暂无";

    // 课外
    const extKeys = Object.keys(player.extracurriculars).filter(function(k) { return player.extracurriculars[k] > 0; });
    const extLines = extKeys.map(function(k) { return k + ":" + EXT_LABELS[player.extracurriculars[k]]; }).join("  ");

    // 艺术
    const artLine = player.art
        ? ("\n🎨 " + player.art.type + " · " + ART_TIERS[player.art.tier] + " (" + player.art.progress + "/100)")
        : "";

    // 学生会
    const councilLine = player.councilRole ? ("\n🏛️ 学生会 · " + player.councilRole) : "";

    // 恋人
    const all = getAllPlayers();
    const partnerName = player.partner ? ((all[player.partner] && all[player.partner].displayName) || "???") : "无";

    // 录取列表
    const acceptedList = player.acceptedList || (player.accepted ? [player.accepted] : []);
    const acceptedLine = acceptedList.length
        ? ("\n\n🎓 录取\n" + acceptedList.map(function(a) { return "  ✅ " + a.fullName + " · " + a.major; }).join("\n"))
        : "";

    const dayLabel = currentDayInfo.label + (gameStarted() ? ("（第" + getGameDay() + "月）") : "");
    const energyLine = "⚡ 精力：" + player.energy + "/" + ENERGY_CAP + (isHoliday() ? ("（假期+" + ENERGY_PER_HOUR_HOLIDAY + "/h）") : "");

    seal.replyToSender(ctx, msg,
        (eventText ? eventText + "\n\n" : "") +
        "📋【" + ch.fullName + "的档案】\n" +
        ch.desc + "\n\n" +
        "📅 " + dayLabel + "　" + applyStatus + "\n" +
        energyLine + "\n" +
        "😤 压力：" + player.stress + "/100（" + stressLevel.label + "）\n" +
        "⭐ 人气：" + player.popularity + "（" + popularityTitle(player.popularity) + "）\n" +
        "💕 恋人：" + partnerName + councilLine + "\n\n" +
        "📚 成绩（GPA " + gpa + "）\n" + gradeLines + "\n\n" +
        "📝 SAT：" + (player.satScore !== null ? player.satScore : "未考") + "（熟练度 " + player.satProf + "）\n" +
        (artLine ? artLine + "\n" : "") +
        "\n🎭 社团\n" + clubLines + "\n" +
        (extLines ? "\n🏆 课外：" + extLines : "") +
        acceptedLine
    );
    return seal.ext.newCmdExecuteResult(true);
    } catch(e) {
        seal.replyToSender(ctx, msg, "❌ 档案错误：" + String(e));
        return seal.ext.newCmdExecuteResult(true);
    }
};
ext.cmdMap["圣约翰档案"] = cmd_profile;

// ==================== 指令：精力查询 ====================

const cmd_energy = seal.ext.newCmdItemInfo();
cmd_energy.name = "圣约翰精力";
cmd_energy.help = "查看当前精力值和恢复进度。";
cmd_energy.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) {
        seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。");
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    savePlayer(userId, player);
    const toFull = ENERGY_CAP - player.energy;
    const curRate = isHoliday() ? ENERGY_PER_HOUR_HOLIDAY : ENERGY_PER_HOUR;
    const hoursToFull = Math.ceil(toFull / curRate);
    seal.replyToSender(ctx, msg,
        `⚡ 精力：${player.energy}/${ENERGY_CAP}\n` +
        `😤 压力：${player.stress}/100（${getStressLevel(player.stress).label}）\n` +
        (toFull > 0 ? `约 ${hoursToFull} 小时后满格（每小时 +${curRate}${isHoliday() ? " 假期加速" : ""}）` : "精力已满！")
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰精力"] = cmd_energy;

// ==================== 指令：上课 ====================

const cmd_class = seal.ext.newCmdItemInfo();
cmd_class.name = "圣约翰上课";
cmd_class.help = "用法：.圣约翰上课 <科目>\n可选科目：English Math History Biology Chemistry Physics ForeignLanguage PE Art Music CS";
cmd_class.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    player = refreshEnergy(player);
    player = refreshStress(player);
    const stressLevel = getStressLevel(player.stress);
    if (stressLevel.locked) {
        seal.replyToSender(ctx, msg, `😵 压力值 ${player.stress}/100，处于崩溃边缘，无法上课！\n请先 .圣约翰休息 或 .圣约翰放松 降低压力。`);
        savePlayer(userId, player);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!gameStarted()) {
        seal.replyToSender(ctx, msg, "⏳ 学期尚未开始，请等待管理员使用 .圣约翰开始学期。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const dayInfo = getDayInfo(getGameDay());
    if (dayInfo.type !== "school") {
        seal.replyToSender(ctx, msg, `🏖️ 现在是${dayInfo.label}，学校放假，无法上课。\n假期精力恢复加速（每小时 +${ENERGY_PER_HOUR_HOLIDAY}），好好充电！`);
        savePlayer(userId, player);
        return seal.ext.newCmdExecuteResult(true);
    }

    const eventText = checkDailyEvent(player);
    savePlayer(userId, player); // 立即持久化 lastEventDay 和事件效果，防止早退丢失

    const subjRaw = (argv.getArgN(1) || "").trim().toLowerCase();
    if (!subjRaw) {
        seal.replyToSender(ctx, msg,
            (eventText ? eventText + "\n\n" : "") +
            `📚 可用科目：${ALL_SUBJECTS.join(" · ")}\n用法：.圣约翰上课 <科目>`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const subj = SUBJECT_ALIAS[subjRaw] || ALL_SUBJECTS.find(s => s.toLowerCase() === subjRaw);
    if (!subj) {
        seal.replyToSender(ctx, msg, `❌ 科目"${argv.getArgN(1)}"不存在。\n可选：${ALL_SUBJECTS.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cdKey = `class_${subj}`;
    if (isOnCooldownMs(player, cdKey, CD.class)) {
        const remain = cdRemainingMs(player, cdKey, CD.class);
        seal.replyToSender(ctx, msg,
            (eventText ? eventText + "\n\n" : "") +
            `⏳ ${subj} 课还在冷却中，${remain}后可再上。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!spendEnergy(player, COST.class)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.class} 点，当前 ${player.energy} 点。`);
        savePlayer(userId, player);
        return seal.ext.newCmdExecuteResult(true);
    }

    const roll = classRoll(stressLevel.classDebuff);
    const gradeObj = player.grades[subj];
    let actualDelta = roll.delta;
    let inspiredTag = "";
    if (player.inspiredBonus && actualDelta > 0) {
        actualDelta = Math.round(actualDelta * 1.3);
        delete player.inspiredBonus;
        inspiredTag = " ✨灵感加成";
    }
    const upgradeMsg = applyGradeChange(gradeObj, actualDelta);
    player.stress = Math.min(STRESS_CAP, player.stress + STRESS_ADD.class);

    if (!player.cooldowns) player.cooldowns = {};
    player.cooldowns[cdKey] = Date.now();

    const sign = actualDelta >= 0 ? "+" : "";
    const resultLine = upgradeMsg
        ? `${sign}${actualDelta}${inspiredTag} → 🎉 ${upgradeMsg}`
        : `${sign}${actualDelta}${inspiredTag} → ${subj}: ${GRADE_TIERS[gradeObj.tier]} (${gradeObj.progress}/100)`;

    savePlayer(userId, player);

    let announce = "";
    if (upgradeMsg && upgradeMsg.includes("↑")) {
        const tier = GRADE_TIERS[gradeObj.tier];
        announce = `📚 ${CHARACTERS[player.charKey].fullName} 的 ${subj} 提升至 ${tier}！`;
        if (player.announcePublic?.score !== false) sendAnnouncement(announce);
    }

    seal.replyToSender(ctx, msg,
        (eventText ? eventText + "\n\n" : "") +
        `📚 上课：${subj}\n` +
        `今日状态：${roll.label}\n` +
        `${resultLine}\n` +
        `⚡ 精力剩余：${player.energy}　😤 压力：${player.stress}/100`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰上课"] = cmd_class;

// ==================== 指令：自习 ====================

const cmd_selfstudy = seal.ext.newCmdItemInfo();
cmd_selfstudy.name = "圣约翰自习";
cmd_selfstudy.help = "自习，随机提升某门科目少量进度。消耗10精力，冷却3小时。";
cmd_selfstudy.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    player = refreshStress(player);

    if (getStressLevel(player.stress).locked) {
        seal.replyToSender(ctx, msg, "😵 压力太高，无法自习！请先休息。");
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    if (isOnCooldown(player, "selfStudy")) {
        seal.replyToSender(ctx, msg, `⏳ 自习冷却中，${cdRemaining(player, "selfStudy")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.selfStudy)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.selfStudy} 点，当前 ${player.energy} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const subj = ALL_SUBJECTS[randInt(0, ALL_SUBJECTS.length - 1)];
    const delta = randInt(3, 10);
    const gradeObj = player.grades[subj];
    const upgradeMsg = applyGradeChange(gradeObj, delta);
    setCooldown(player, "selfStudy");
    savePlayer(userId, player);

    seal.replyToSender(ctx, msg,
        `📖 自习中…随机复习了 ${subj}\n` +
        `+${delta}${upgradeMsg ? " → 🎉 " + upgradeMsg : ` → ${subj}: ${GRADE_TIERS[gradeObj.tier]} (${gradeObj.progress}/100)`}\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰自习"] = cmd_selfstudy;

// ==================== 指令：备考SAT ====================

const cmd_sat_study = seal.ext.newCmdItemInfo();
cmd_sat_study.name = "圣约翰备考SAT";
cmd_sat_study.help = "备考SAT，提升SAT熟练度。消耗25精力，冷却3小时。";
cmd_sat_study.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    player = refreshStress(player);
    const sl = getStressLevel(player.stress);

    if (sl.locked) {
        seal.replyToSender(ctx, msg, "😵 压力太高，无法备考！请先休息。");
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    if (isOnCooldown(player, "satStudy")) {
        seal.replyToSender(ctx, msg, `⏳ 备考冷却中，${cdRemaining(player, "satStudy")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.satStudy)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.satStudy} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const roll = satStudyRoll(sl.satDebuff);
    player.satProf = Math.max(SAT_MIN, Math.min(SAT_MAX, player.satProf + roll.delta));
    player.stress = Math.min(STRESS_CAP, player.stress + STRESS_ADD.satStudy);
    setCooldown(player, "satStudy");
    savePlayer(userId, player);

    const sign = roll.delta >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg,
        `📝 备考SAT\n今日状态：${roll.label}\n` +
        `${sign}${roll.delta} → SAT熟练度：${player.satProf}\n` +
        `⚡ 精力剩余：${player.energy}　😤 压力：${player.stress}/100`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰备考SAT"] = cmd_sat_study;

// ==================== 指令：考SAT ====================

const cmd_sat_exam = seal.ext.newCmdItemInfo();
cmd_sat_exam.name = "圣约翰考SAT";
cmd_sat_exam.help = "参加SAT考试。消耗40精力，冷却1.5天。分数=熟练度+随机波动，记录最新成绩。";
cmd_sat_exam.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    player = refreshStress(player);
    const sl = getStressLevel(player.stress);

    if (sl.satDebuff >= 100) {
        seal.replyToSender(ctx, msg, `😤 压力值 ${player.stress}/100，状态太差，无法参加考试！请先降压。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    if (isOnCooldown(player, "satExam")) {
        seal.replyToSender(ctx, msg, `⏳ SAT考试冷却中，${cdRemaining(player, "satExam")}后可再考。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.satExam)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.satExam} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    // 波动：-80~+120，偏正态，65%正向
    const variance = Math.random() < 0.65
        ? randInt(0, 120)
        : -randInt(0, 80);
    const prev = player.satScore;
    const newScore = Math.max(SAT_MIN, Math.min(SAT_MAX, player.satProf + variance));
    player.satScore = newScore;
    player.stress = Math.min(STRESS_CAP, player.stress + STRESS_ADD.satExam);
    setCooldown(player, "satExam");
    savePlayer(userId, player);

    const sign = variance >= 0 ? "+" : "";
    const compareMsg = prev !== null
        ? (newScore > prev ? `↑ 比上次高 ${newScore - prev} 分` : newScore < prev ? `↓ 比上次低 ${prev - newScore} 分` : "与上次持平")
        : "首次考试";

    if (player.announcePublic?.sat !== false) {
        sendAnnouncement(`📝 ${CHARACTERS[player.charKey].fullName} 的SAT成绩：${newScore}分`);
    }

    seal.replyToSender(ctx, msg,
        `📝【SAT考试结果】\n` +
        `熟练度：${player.satProf}　发挥：${sign}${variance}\n` +
        `本次得分：${newScore}　${compareMsg}\n` +
        `⚡ 精力剩余：${player.energy}　😤 压力：${player.stress}/100`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰考SAT"] = cmd_sat_exam;

// ==================== 指令：选艺术方向 ====================

const ART_OPTIONS = ["钢琴","小提琴","大提琴","长笛","吉他","声乐","作曲","绘画","摄影","雕塑","陶艺","数字艺术","戏剧","舞蹈"];

const cmd_art_choose = seal.ext.newCmdItemInfo();
cmd_art_choose.name = "圣约翰选艺术";
cmd_art_choose.help = "用法：.圣约翰选艺术 <方向>\n可选：钢琴 小提琴 大提琴 长笛 吉他 声乐 作曲 绘画 摄影 雕塑 陶艺 数字艺术 戏剧 舞蹈\n注意：只能选一次，选定后不可更改。";
cmd_art_choose.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (player.art) {
        seal.replyToSender(ctx, msg, `🎨 你已选择艺术方向：${player.art.type}（${ART_TIERS[player.art.tier]}）\n艺术方向一经选定不可更改。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const choice = (argv.getArgN(1) || "").trim();
    if (!ART_OPTIONS.includes(choice)) {
        seal.replyToSender(ctx, msg, `❌ 无效方向"${choice}"。\n可选：${ART_OPTIONS.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player.art = { type: choice, tier: 0, progress: 0 };
    savePlayer(userId, player);
    seal.replyToSender(ctx, msg,
        `🎨 艺术方向已选定：${choice}\n` +
        `当前等级：${ART_TIERS[0]}（初学）\n` +
        `使用 .圣约翰练习 提升技艺，.圣约翰演出 获得突破！`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰选艺术"] = cmd_art_choose;

// ==================== 指令：练习 ====================

const cmd_art_practice = seal.ext.newCmdItemInfo();
cmd_art_practice.name = "圣约翰练习";
cmd_art_practice.help = "练习艺术方向，提升天赋等级。消耗20精力，冷却4小时。需先 .圣约翰选艺术 选定方向。";
cmd_art_practice.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!player.art) {
        seal.replyToSender(ctx, msg, "🎨 请先 .圣约翰选艺术 <方向> 选定艺术方向。");
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);

    if (isOnCooldown(player, "artPractice")) {
        seal.replyToSender(ctx, msg, `⏳ 练习冷却中，${cdRemaining(player, "artPractice")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.artPractice)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.artPractice} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const roll = artPracticeRoll();
    const art = player.art;
    art.progress += roll.delta;
    let upgradeMsg = "";
    while (art.progress >= 100 && art.tier < ART_TIERS.length - 1) {
        art.progress -= 100;
        art.tier++;
        upgradeMsg = `🎉 晋级！→ ${ART_TIERS[art.tier]} ↑`;
    }
    if (art.progress < 0) art.progress = 0;
    if (art.tier >= ART_TIERS.length - 1 && art.progress > 99) art.progress = 99;
    setCooldown(player, "artPractice");
    savePlayer(userId, player);

    if (upgradeMsg) sendAnnouncement(`🎵 ${CHARACTERS[player.charKey].fullName} 的 ${art.type} 晋级至「${ART_TIERS[art.tier]}」！`);

    const sign = roll.delta >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg,
        `🎵 练习：${art.type}\n今日状态：${roll.label}\n` +
        `${sign}${roll.delta}${upgradeMsg ? " → " + upgradeMsg : ` → ${ART_TIERS[art.tier]} (${art.progress}/100)`}\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰练习"] = cmd_art_practice;

// ==================== 指令：演出 ====================

const cmd_art_perform = seal.ext.newCmdItemInfo();
cmd_art_perform.name = "圣约翰演出";
cmd_art_perform.help = "参加演出/展览，高风险高回报。消耗40精力，冷却1.5天。";
cmd_art_perform.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!player.art) {
        seal.replyToSender(ctx, msg, "🎨 请先 .圣约翰选艺术 选定方向。");
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);

    if (isOnCooldown(player, "artPerform")) {
        seal.replyToSender(ctx, msg, `⏳ 演出冷却中，${cdRemaining(player, "artPerform")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.artPerform)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.artPerform} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const roll = artPerformRoll();
    const art = player.art;
    art.progress = Math.max(0, art.progress + roll.delta);
    let upgradeMsg = "";
    while (art.progress >= 100 && art.tier < ART_TIERS.length - 1) {
        art.progress -= 100;
        art.tier++;
        upgradeMsg = `🎉 突破！→ ${ART_TIERS[art.tier]} ↑`;
    }
    if (art.tier >= ART_TIERS.length - 1 && art.progress > 99) art.progress = 99;

    // 人气变化
    const popChange = roll.delta >= 20 ? randInt(15, 30) : roll.delta >= 0 ? randInt(3, 10) : -randInt(5, 15);
    player.popularity = Math.max(0, Math.min(POPULARITY_CAP, player.popularity + popChange));

    setCooldown(player, "artPerform");
    savePlayer(userId, player);

    if (upgradeMsg) sendAnnouncement(`🎵 ${CHARACTERS[player.charKey].fullName} 的 ${art.type} 突破至「${ART_TIERS[art.tier]}」！`);

    const sign = roll.delta >= 0 ? "+" : "";
    const popSign = popChange >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg,
        `🎭 演出：${art.type}\n结果：${roll.label}\n` +
        `进度 ${sign}${roll.delta}${upgradeMsg ? " → " + upgradeMsg : ` → ${ART_TIERS[art.tier]} (${art.progress}/100)`}\n` +
        `人气 ${popSign}${popChange} → ${player.popularity}\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰演出"] = cmd_art_perform;

// ==================== 指令：社交/发帖/派对 ====================

const cmd_social = seal.ext.newCmdItemInfo();
cmd_social.name = "圣约翰社交";
cmd_social.help = "随机社交，提升人气。消耗15精力，冷却2小时。";
cmd_social.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    if (isOnCooldown(player, "social")) {
        seal.replyToSender(ctx, msg, `⏳ 社交冷却中，${cdRemaining(player, "social")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.social)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.social} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    const r = Math.random();
    let popChange, desc;
    if (r < 0.65)      { popChange = randInt(3, 12);  desc = "聊得不错，气氛很好！"; }
    else if (r < 0.85) { popChange = randInt(1, 4);   desc = "一般般，没什么特别的。"; }
    else               { popChange = -randInt(2, 5);  desc = "说了句不合时宜的话……"; }
    player.popularity = Math.max(0, Math.min(POPULARITY_CAP, player.popularity + popChange));
    setCooldown(player, "social");
    savePlayer(userId, player);
    const sign = popChange >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg, `💬 社交：${desc}\n人气 ${sign}${popChange} → ${player.popularity}（${popularityTitle(player.popularity)}）\n⚡ 精力剩余：${player.energy}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰社交"] = cmd_social;

const cmd_post = seal.ext.newCmdItemInfo();
cmd_post.name = "圣约翰发帖";
cmd_post.help = "发帖刷存在感，人气随机浮动。消耗10精力，冷却1.5小时。";
cmd_post.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    if (isOnCooldown(player, "post")) {
        seal.replyToSender(ctx, msg, `⏳ 发帖冷却中，${cdRemaining(player, "post")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.post)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.post} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    const r = Math.random();
    let popChange, desc;
    if (r < 0.15)      { popChange = randInt(10, 15); desc = "这条帖子爆了！"; }
    else if (r < 0.65) { popChange = randInt(1, 8);   desc = "反响还不错。"; }
    else if (r < 0.85) { popChange = 0;               desc = "没什么人看……"; }
    else               { popChange = -randInt(5, 10); desc = "发错了什么，评论区开始炸了……"; }
    player.popularity = Math.max(0, Math.min(POPULARITY_CAP, player.popularity + popChange));
    setCooldown(player, "post");
    savePlayer(userId, player);
    const sign = popChange >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg, `📱 发帖：${desc}\n人气 ${sign}${popChange} → ${player.popularity}（${popularityTitle(player.popularity)}）\n⚡ 精力剩余：${player.energy}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰发帖"] = cmd_post;

const cmd_party = seal.ext.newCmdItemInfo();
cmd_party.name = "圣约翰参加派对";
cmd_party.help = "参加派对，大幅提升人气并降低压力。消耗30精力，冷却1天，需人气≥60。";
cmd_party.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (player.popularity < 60) {
        seal.replyToSender(ctx, msg, `❌ 人气不够（当前 ${player.popularity}），需要 ≥60 才会被邀请参加派对。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    player = refreshStress(player);
    if (isOnCooldown(player, "party")) {
        seal.replyToSender(ctx, msg, `⏳ 派对冷却中，${cdRemaining(player, "party")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.party)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.party} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    const r = Math.random();
    let popChange, stressDown, desc;
    if (r < 0.60)      { popChange = randInt(15, 35); stressDown = 20; desc = "玩得很开心！"; }
    else if (r < 0.85) { popChange = randInt(5, 15);  stressDown = 15; desc = "还行，认识了几个新朋友。"; }
    else               { popChange = -randInt(3, 10); stressDown = 5;  desc = "发生了点尴尬的事……"; }
    player.popularity = Math.max(0, Math.min(POPULARITY_CAP, player.popularity + popChange));
    player.stress = Math.max(0, player.stress - stressDown);
    setCooldown(player, "party");
    savePlayer(userId, player);
    const sign = popChange >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg, `🎉 派对：${desc}\n人气 ${sign}${popChange} → ${player.popularity}　压力 -${stressDown} → ${player.stress}/100\n⚡ 精力剩余：${player.energy}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰参加派对"] = cmd_party;

// ==================== 指令：加入社团 ====================

const cmd_join_club = seal.ext.newCmdItemInfo();
cmd_join_club.name = "圣约翰加入";
cmd_join_club.help = "用法：.圣约翰加入 <社团名>\n查看所有社团：.圣约翰社团列表";
cmd_join_club.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!gameStarted()) { seal.replyToSender(ctx, msg, "⏳ 学期尚未开始，请等待管理员使用 .圣约翰开始学期。"); return seal.ext.newCmdExecuteResult(true); }
    if (isHoliday()) {
        seal.replyToSender(ctx, msg, `🏖️ 现在是${getDayInfo(getGameDay()).label}，放假期间无法加入社团。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const clubName = (argv.getArgN(1) || "").trim();
    if (!clubName) {
        seal.replyToSender(ctx, msg, `用法：.圣约翰加入 <社团名>\n所有社团：${CLUB_NAMES.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const check = canJoinClub(player, clubName);
    if (!check.ok) {
        seal.replyToSender(ctx, msg, `❌ 无法加入${clubName}：${check.reason}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player.clubs[clubName] = { role: "成员", progress: 0 };
    const extKey = CLUBS[clubName].extKey;
    if (extKey) player.extracurriculars[extKey] = Math.max(player.extracurriculars[extKey] || 0, 1);
    player.popularity = Math.min(POPULARITY_CAP, player.popularity + 3);
    savePlayer(userId, player);
    sendAnnouncement(`🎭 ${CHARACTERS[player.charKey].fullName} 加入了 ${clubName}！`);
    seal.replyToSender(ctx, msg, `✅ 成功加入 ${clubName}！\n人气 +3 → ${player.popularity}\n使用 .圣约翰社团活动 参加活动提升职位。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰加入"] = cmd_join_club;

// ==================== 指令：社团活动 ====================

const cmd_club_activity = seal.ext.newCmdItemInfo();
cmd_club_activity.name = "圣约翰社团活动";
cmd_club_activity.help = "用法：.圣约翰社团活动 <社团名>\n参加社团活动，提升职位并获得课外等级。消耗25精力，冷却4小时。";
cmd_club_activity.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!gameStarted()) { seal.replyToSender(ctx, msg, "⏳ 学期尚未开始，请等待管理员使用 .圣约翰开始学期。"); return seal.ext.newCmdExecuteResult(true); }
    if (isHoliday()) {
        seal.replyToSender(ctx, msg, `🏖️ 现在是${getDayInfo(getGameDay()).label}，放假期间无法参加社团活动。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const clubName = (argv.getArgN(1) || "").trim();
    if (!clubName || !player.clubs[clubName]) {
        const myClubs = Object.keys(player.clubs);
        if (!myClubs.length) { seal.replyToSender(ctx, msg, "❌ 你还没有加入任何社团。"); return seal.ext.newCmdExecuteResult(true); }
        seal.replyToSender(ctx, msg, `用法：.圣约翰社团活动 <社团名>\n你的社团：${myClubs.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cdKey = `club_${clubName}`;
    if (isOnCooldownMs(player, cdKey, CD.clubActivity)) {
        seal.replyToSender(ctx, msg, `⏳ ${clubName}活动冷却中，${cdRemainingMs(player, cdKey, CD.clubActivity)}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    player = refreshStress(player);
    if (!spendEnergy(player, COST.clubActivity)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.clubActivity} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const club = CLUBS[clubName];
    const membership = player.clubs[clubName];
    const ROLES = ["成员", "骨干", "负责人"];
    const roleIdx = ROLES.indexOf(membership.role);

    membership.progress += randInt(20, 35);
    let promoted = false;
    if (membership.progress >= 100 && roleIdx < 2) {
        membership.progress -= 100;
        membership.role = ROLES[roleIdx + 1];
        promoted = true;
        player.popularity = Math.min(POPULARITY_CAP, player.popularity + (roleIdx === 0 ? 10 : 20));
        const extKey = club.extKey;
        if (extKey) player.extracurriculars[extKey] = Math.min(3, (player.extracurriculars[extKey] || 0) + 1);
    }
    if (membership.progress >= 100 && roleIdx >= 2) membership.progress = 99;

    const popGain = club.popularityGain || randInt(2, 8);
    player.popularity = Math.min(POPULARITY_CAP, player.popularity + (promoted ? 0 : popGain));
    player.stress = Math.min(STRESS_CAP, player.stress + STRESS_ADD.clubActivity);

    if (!player.cooldowns) player.cooldowns = {};
    player.cooldowns[cdKey] = Date.now();
    savePlayer(userId, player);

    if (promoted) {
        sendAnnouncement(`⭐ ${CHARACTERS[player.charKey].fullName} 成为了 ${clubName} 的${membership.role}！`);
    }
    seal.replyToSender(ctx, msg,
        `🎭 ${clubName}活动\n` +
        (promoted
            ? `🎉 晋升！现在是 ${membership.role}！人气大幅提升！\n`
            : `进度：${membership.progress}/100（${membership.role}）\n`) +
        `人气 +${promoted ? "晋升奖励" : popGain} → ${player.popularity}　压力 +${STRESS_ADD.clubActivity}\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰社团活动"] = cmd_club_activity;

// ==================== 指令：我的社团 ====================

const cmd_my_clubs = seal.ext.newCmdItemInfo();
cmd_my_clubs.name = "圣约翰我的社团";
cmd_my_clubs.help = "查看已加入的社团和职位。";
cmd_my_clubs.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    const entries = Object.entries(player.clubs);
    if (!entries.length) {
        seal.replyToSender(ctx, msg, "🎭 你还没有加入任何社团。\n使用 .圣约翰加入 <社团名> 报名！");
        return seal.ext.newCmdExecuteResult(true);
    }
    const lines = entries.map(([c, d]) => `  ${c} · ${d.role}（${d.progress}/100）`).join("\n");
    seal.replyToSender(ctx, msg, `🎭【我的社团】\n${lines}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰我的社团"] = cmd_my_clubs;

// ==================== 指令：竞选 ====================

const cmd_election = seal.ext.newCmdItemInfo();
cmd_election.name = "圣约翰竞选";
cmd_election.help = "用法：.圣约翰竞选 <职位>\n职位：班级代表 干事 副主席 主席\n消耗50精力，冷却3.5天。需满足人气门槛。";
cmd_election.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!gameStarted()) { seal.replyToSender(ctx, msg, "⏳ 学期尚未开始，请等待管理员使用 .圣约翰开始学期。"); return seal.ext.newCmdExecuteResult(true); }
    if (isHoliday()) {
        seal.replyToSender(ctx, msg, `🏖️ 现在是${getDayInfo(getGameDay()).label}，放假期间无法竞选。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const role = (argv.getArgN(1) || "").trim();
    if (!COUNCIL_ROLES.includes(role)) {
        seal.replyToSender(ctx, msg, `❌ 无效职位。可选：${COUNCIL_ROLES.join(" · ")}\n各职位人气门槛：班级代表≥60　干事≥75　副主席≥90　主席≥110`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const minPop = COUNCIL_REQ[role];
    if (player.popularity < minPop) {
        seal.replyToSender(ctx, msg, `❌ 人气不足！竞选${role}需要人气 ≥${minPop}，当前 ${player.popularity}。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    if (isOnCooldown(player, "election")) {
        seal.replyToSender(ctx, msg, `⏳ 竞选冷却中，${cdRemaining(player, "election")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.election)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.election} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshStress(player);
    player.stress = Math.min(STRESS_CAP, player.stress + STRESS_ADD.election);

    // 当选概率：50% + (人气-门槛)*1.5%，上限85%
    const winChance = Math.min(0.85, 0.50 + (player.popularity - minPop) * 0.015);
    const won = Math.random() < winChance;

    setCooldown(player, "election");
    if (won) {
        player.councilRole = role;
        player.popularity = Math.min(POPULARITY_CAP, player.popularity + COUNCIL_REWARD[role]);
        player.extracurriculars["debate"] = Math.max(player.extracurriculars["debate"] || 0, 2);
        savePlayer(userId, player);
        sendAnnouncement(`🏛️ ${CHARACTERS[player.charKey].fullName} 当选学生会${role}！`);
        seal.replyToSender(ctx, msg,
            `🏛️ 竞选结果：当选！\n恭喜成为学生会${role}！\n人气 +${COUNCIL_REWARD[role]} → ${player.popularity}\n⚡ 精力剩余：${player.energy}　😤 压力：${player.stress}/100`
        );
    } else {
        player.popularity = Math.max(0, player.popularity - 10);
        savePlayer(userId, player);
        seal.replyToSender(ctx, msg,
            `🏛️ 竞选结果：落选……\n人气 -10 → ${player.popularity}\n😤 压力：${player.stress}/100\n⚡ 精力剩余：${player.energy}`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰竞选"] = cmd_election;

// ==================== 指令：社团列表 ====================

const cmd_club_list = seal.ext.newCmdItemInfo();
cmd_club_list.name = "圣约翰社团列表";
cmd_club_list.help = "查看所有社团及入门条件。";
cmd_club_list.solve = function(ctx, msg, argv) {
    const open = CLUB_NAMES.filter(n => CLUBS[n].open).join(" · ");
    const gated = CLUB_NAMES.filter(n => !CLUBS[n].open && !["橄榄球队","田径队","篮球队"].includes(n)).join(" · ");
    const elite = ["橄榄球队","田径队","篮球队"].join(" · ");
    seal.replyToSender(ctx, msg,
        `🎭【圣约翰社团列表】\n\n` +
        `📂 开放社团（直接加入）\n${open}\n\n` +
        `🔒 门槛社团\n${gated}\n\n` +
        `🏅 精英队伍\n${elite}\n\n` +
        `学生会需要 .圣约翰竞选 参加竞选（人气≥60起）`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰社团列表"] = cmd_club_list;

// ==================== 指令：休息 / 放松 ====================

const cmd_rest = seal.ext.newCmdItemInfo();
cmd_rest.name = "圣约翰休息";
cmd_rest.help = "休息降低压力。不消耗精力，冷却2小时。";
cmd_rest.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshStress(player);
    if (isOnCooldown(player, "rest")) {
        seal.replyToSender(ctx, msg, `⏳ 休息冷却中，${cdRemaining(player, "rest")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const reduce = randInt(20, 30);
    player.stress = Math.max(0, player.stress - reduce);
    setCooldown(player, "rest");
    savePlayer(userId, player);
    seal.replyToSender(ctx, msg, `😴 好好休息了一下……\n压力 -${reduce} → ${player.stress}/100（${getStressLevel(player.stress).label}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰休息"] = cmd_rest;

const cmd_relax = seal.ext.newCmdItemInfo();
cmd_relax.name = "圣约翰放松";
cmd_relax.help = "花时间做喜欢的事，大幅降低压力。消耗20精力，冷却4小时。";
cmd_relax.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    player = refreshEnergy(player);
    player = refreshStress(player);
    if (isOnCooldown(player, "relax")) {
        seal.replyToSender(ctx, msg, `⏳ 放松冷却中，${cdRemaining(player, "relax")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.relax)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.relax} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }
    const events = [
        "在Central Park晒了一下午太阳",
        "刷了一整天剧，什么都没想",
        "和朋友去Brooklyn吃了顿好的",
        "在书店待了三小时，买了两本书",
        "去健身房跑步，脑子终于清空了",
    ];
    const reduce = randInt(35, 50);
    player.stress = Math.max(0, player.stress - reduce);
    setCooldown(player, "relax");
    savePlayer(userId, player);
    const event = events[randInt(0, events.length - 1)];
    seal.replyToSender(ctx, msg,
        `🌿 放松：${event}\n压力 -${reduce} → ${player.stress}/100（${getStressLevel(player.stress).label}）\n⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰放松"] = cmd_relax;

// ==================== 指令：互动 ====================

const cmd_interact = seal.ext.newCmdItemInfo();
cmd_interact.name = "圣约翰互动";
cmd_interact.help = "用法：.圣约翰互动 <英文名>\n与对方互动，提升双方好感度。消耗10精力，每对玩家冷却2小时。";
cmd_interact.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const nameArg = (argv.getArgN(1) || "").trim();
    const found = getPlayerByName(nameArg);
    if (!found || found.userId === userId) {
        seal.replyToSender(ctx, msg, "❌ 请输入对方的英文名，例如：.圣约翰互动 James");
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetId = found.userId;
    const targetPlayer = found.player;
    if (!targetPlayer) {
        seal.replyToSender(ctx, msg, "❌ 对方还没有注册圣约翰。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const relCheck = getRelation(userId, targetId);
    const interactCdMs = relCheck.favor >= 100 ? 2 * 3600 * 1000 : CD.interact;
    if (isOnCooldownMs(player, `interact_${targetId}`, interactCdMs)) {
        const cdMsg = cdRemainingMs(player, `interact_${targetId}`, interactCdMs);
        seal.replyToSender(ctx, msg, `⏳ 与 ${targetPlayer.displayName} 的互动还在冷却中，${cdMsg}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    if (!spendEnergy(player, COST.interact)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.interact} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const r = Math.random();
    let delta, desc;
    if (r < 0.55)      { delta = randInt(5, 12); desc = "聊得很开心！"; }
    else if (r < 0.85) { delta = randInt(1, 4);  desc = "还不错，感觉自然了一点。"; }
    else               { delta = -randInt(2, 5); desc = "气氛有点尴尬……"; }

    // 更新双向好感（互动主要加自己对对方的好感，对方对自己小幅加）
    const relA = getRelation(userId, targetId);
    const relB = getRelation(targetId, userId);
    relA.favor = Math.max(0, Math.min(200, relA.favor + delta));
    relA.lastInteract = Date.now();
    relB.favor = Math.max(0, Math.min(200, relB.favor + Math.floor(delta * 0.5)));
    relB.lastInteract = Date.now();
    saveRelation(userId, targetId, relA);
    saveRelation(targetId, userId, relB);

    setInteractCooldown(player, targetId);
    savePlayer(userId, player);

    const stageA = getRelationStage(relA.favor);
    const sign = delta >= 0 ? "+" : "";
    seal.replyToSender(ctx, msg,
        `💬 与 ${targetPlayer.displayName} 互动\n${desc}\n` +
        `好感 ${sign}${delta} → ${relA.favor}（${stageA.label}）\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰互动"] = cmd_interact;

// ==================== 指令：好感查询 ====================

const cmd_favor = seal.ext.newCmdItemInfo();
cmd_favor.name = "圣约翰好感";
cmd_favor.help = "用法：.圣约翰好感 <英文名>\n查看与对方的好感度。";
cmd_favor.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const nameArg = (argv.getArgN(1) || "").trim();
    const found = getPlayerByName(nameArg);
    if (!found || found.userId === userId) {
        seal.replyToSender(ctx, msg, "❌ 请输入对方的英文名，例如：.圣约翰好感 Noah");
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetId = found.userId;
    const targetPlayer = found.player;
    if (!targetPlayer) { seal.replyToSender(ctx, msg, "❌ 对方还没有注册。"); return seal.ext.newCmdExecuteResult(true); }

    const relA = getRelation(userId, targetId);
    const relB = getRelation(targetId, userId);
    const stageA = getRelationStage(relA.favor);
    const stageB = getRelationStage(relB.favor);

    const isCouple = player.partner === targetId;
    const coupleTag = isCouple ? "\n💕 你们目前是恋人关系" : "";

    seal.replyToSender(ctx, msg,
        `💕 好感度查询\n` +
        `你 → ${targetPlayer.displayName}：${relA.favor}（${stageA.label}）\n` +
        `${targetPlayer.displayName} → 你：${relB.favor}（${stageB.label}）${coupleTag}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰好感"] = cmd_favor;

// ==================== 指令：告白 ====================

const cmd_confess = seal.ext.newCmdItemInfo();
cmd_confess.name = "圣约翰告白";
cmd_confess.help = "用法：.圣约翰告白 <英文名>\n需要对对方好感 ≥70。消耗30精力，对方有24小时接受/拒绝。";
cmd_confess.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (player.partner) {
        const all = getAllPlayers();
        seal.replyToSender(ctx, msg, `❌ 你已经和 ${all[player.partner]?.displayName || "???"} 在一起了。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const nameArg = (argv.getArgN(1) || "").trim();
    const found = getPlayerByName(nameArg);
    if (!found || found.userId === userId) {
        seal.replyToSender(ctx, msg, "❌ 请输入对方的英文名，例如：.圣约翰告白 Chloe"); return seal.ext.newCmdExecuteResult(true);
    }
    const targetId = found.userId;
    const targetPlayer = getPlayer(targetId);
    if (!targetPlayer) { seal.replyToSender(ctx, msg, "❌ 对方还没有注册。"); return seal.ext.newCmdExecuteResult(true); }

    if (targetPlayer.partner) {
        const all = getAllPlayers();
        seal.replyToSender(ctx, msg, `❌ ${targetPlayer.displayName} 已经在恋爱中了。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (targetPlayer.pendingConfess) {
        seal.replyToSender(ctx, msg, `❌ ${targetPlayer.displayName} 目前已有待处理的告白。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const relA = getRelation(userId, targetId);
    if (relA.favor < 70) {
        seal.replyToSender(ctx, msg, `❌ 好感度不足（当前 ${relA.favor}），需要 ≥70 才能告白。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    if (!spendEnergy(player, COST.confess)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.confess} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    // 写入目标的 pendingConfess
    targetPlayer.pendingConfess = { from: userId, at: Date.now() };
    savePlayer(userId, player);
    savePlayer(targetId, targetPlayer);

    seal.replyToSender(ctx, msg,
        `💌 ${CHARACTERS[player.charKey].fullName} 向 ${targetPlayer.displayName} 告白了！\n` +
        `${targetPlayer.displayName} 请在24小时内使用 .圣约翰接受 或 .圣约翰拒绝 回应。\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰告白"] = cmd_confess;

// ==================== 指令：接受 / 拒绝 ====================

const cmd_accept = seal.ext.newCmdItemInfo();
cmd_accept.name = "圣约翰接受";
cmd_accept.help = "接受当前待处理的告白。";
cmd_accept.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (!player.pendingConfess) {
        seal.replyToSender(ctx, msg, "❌ 目前没有待处理的告白。"); return seal.ext.newCmdExecuteResult(true);
    }
    // 检查超时（24小时）
    if (Date.now() - player.pendingConfess.at > 24 * 3600 * 1000) {
        player.pendingConfess = null;
        savePlayer(userId, player);
        seal.replyToSender(ctx, msg, "⏰ 告白已超时，自动拒绝了。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const fromId = player.pendingConfess.from;
    let fromPlayer = getPlayer(fromId);
    if (!fromPlayer) { player.pendingConfess = null; savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true); }

    // 建立恋人关系
    player.partner = fromId;
    player.pendingConfess = null;
    fromPlayer.partner = userId;

    // 好感锁定提升
    const relA = getRelation(fromId, userId);
    const relB = getRelation(userId, fromId);
    relA.favor = Math.max(relA.favor, 100);
    relB.favor = Math.max(relB.favor, 100);
    relA.lastInteract = Date.now();
    relB.lastInteract = Date.now();
    saveRelation(fromId, userId, relA);
    saveRelation(userId, fromId, relB);

    // 人气加成
    player.popularity = Math.min(POPULARITY_CAP, player.popularity + 20);
    fromPlayer.popularity = Math.min(POPULARITY_CAP, fromPlayer.popularity + 20);

    savePlayer(userId, player);
    savePlayer(fromId, fromPlayer);

    sendAnnouncement(`💕 ${fromPlayer.displayName} 和 ${player.displayName} 在一起了！`);
    seal.replyToSender(ctx, msg,
        `💕 接受了 ${fromPlayer.displayName} 的告白！\n` +
        `你们现在是恋人关系 🎉\n人气 +20 → ${player.popularity}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰接受"] = cmd_accept;

const cmd_reject = seal.ext.newCmdItemInfo();
cmd_reject.name = "圣约翰拒绝";
cmd_reject.help = "拒绝当前待处理的告白。";
cmd_reject.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (!player.pendingConfess) {
        seal.replyToSender(ctx, msg, "❌ 目前没有待处理的告白。"); return seal.ext.newCmdExecuteResult(true);
    }
    const fromId = player.pendingConfess.from;
    let fromPlayer = getPlayer(fromId);
    player.pendingConfess = null;
    savePlayer(userId, player);

    if (fromPlayer) {
        const relA = getRelation(fromId, userId);
        relA.favor = Math.max(0, relA.favor - 25);
        saveRelation(fromId, userId, relA);
        fromPlayer.popularity = Math.max(0, fromPlayer.popularity - 5);
        savePlayer(fromId, fromPlayer);
        // 私信发起方（不公开）
        try {
            const endpoints = seal.getEndPoints();
            for (const ep of endpoints) {
                const m = seal.newMessage();
                m.messageType = "private";
                m.sender = { userId: fromId };
                const ctx2 = seal.createTempCtx(ep, m);
                seal.replyToSender(ctx2, m, `💔 ${player.displayName} 拒绝了你的告白。\n好感 -25，人气 -5。`);
                break;
            }
        } catch(e) {}
    }
    seal.replyToSender(ctx, msg, `💔 拒绝了告白。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰拒绝"] = cmd_reject;

// ==================== 指令：约会 ====================

const cmd_date = seal.ext.newCmdItemInfo();
cmd_date.name = "圣约翰约会";
cmd_date.help = "用法：.圣约翰约会 <英文名>\n需是恋人关系，维护感情并降低双方压力。消耗25精力，冷却1天。";
cmd_date.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const nameArg = (argv.getArgN(1) || "").trim();
    const found = getPlayerByName(nameArg);
    const targetId = found ? found.userId : null;
    if (!targetId) { seal.replyToSender(ctx, msg, "❌ 请输入恋人的英文名，例如：.圣约翰约会 Sofia"); return seal.ext.newCmdExecuteResult(true); }
    if (player.partner !== targetId) {
        seal.replyToSender(ctx, msg, "❌ 只能和恋人约会。"); return seal.ext.newCmdExecuteResult(true);
    }
    player = refreshEnergy(player);
    player = refreshStress(player);
    if (isOnCooldown(player, "date")) {
        seal.replyToSender(ctx, msg, `⏳ 约会冷却中，${cdRemaining(player, "date")}后可用。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!spendEnergy(player, COST.date)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.date} 点。`); savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    let targetPlayer = getPlayer(targetId);
    targetPlayer = refreshStress(targetPlayer);

    const stressDown = 40;
    const favorGain = 15;
    player.stress = Math.max(0, player.stress - stressDown);
    targetPlayer.stress = Math.max(0, targetPlayer.stress - stressDown);

    const relA = getRelation(userId, targetId);
    const relB = getRelation(targetId, userId);
    relA.favor = Math.min(200, relA.favor + favorGain);
    relB.favor = Math.min(200, relB.favor + favorGain);
    relA.lastInteract = Date.now();
    relB.lastInteract = Date.now();
    saveRelation(userId, targetId, relA);
    saveRelation(targetId, userId, relB);

    setCooldown(player, "date");
    savePlayer(userId, player);
    savePlayer(targetId, targetPlayer);

    const dates = [
        "一起去了Central Park散步", "在Brooklyn找到了一家很棒的餐厅",
        "逛了一下午博物馆", "一起去看了场电影", "在图书馆并排坐了一整个下午",
    ];
    const event = dates[randInt(0, dates.length - 1)];
    seal.replyToSender(ctx, msg,
        `💕 与 ${targetPlayer.displayName} 约会：${event}\n` +
        `双方压力 -${stressDown}　好感 +${favorGain}\n` +
        `你的压力：${player.stress}/100　⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰约会"] = cmd_date;

// ==================== 指令：分手 ====================

const cmd_breakup = seal.ext.newCmdItemInfo();
cmd_breakup.name = "圣约翰分手";
cmd_breakup.help = "与当前恋人分手。双方好感归零，发起方压力+15、人气-15。";
cmd_breakup.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (!player.partner) {
        seal.replyToSender(ctx, msg, "❌ 你目前没有在恋爱中。"); return seal.ext.newCmdExecuteResult(true);
    }
    const partnerId = player.partner;
    let partnerPlayer = getPlayer(partnerId);
    const partnerName = partnerPlayer?.displayName || "???";

    // 清除恋人关系
    player.partner = null;
    player.popularity = Math.max(0, player.popularity - 15);
    player.stress = Math.min(STRESS_CAP, (player.stress || 0) + 15);

    const relA = getRelation(userId, partnerId);
    const relB = getRelation(partnerId, userId);
    relA.favor = 0;
    relB.favor = 0;
    saveRelation(userId, partnerId, relA);
    saveRelation(partnerId, userId, relB);

    if (partnerPlayer) {
        partnerPlayer.partner = null;
        savePlayer(partnerId, partnerPlayer);
    }
    savePlayer(userId, player);

    if (player.announcePublic?.breakup !== false) {
        sendAnnouncement(`💔 ${CHARACTERS[player.charKey].fullName} 和 ${partnerName} 分手了……`);
    }
    seal.replyToSender(ctx, msg,
        `💔 与 ${partnerName} 分手了。\n人气 -15 → ${player.popularity}　压力 +15 → ${player.stress}/100`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰分手"] = cmd_breakup;

// ==================== 关系自动衰减检查 ====================
// 每次玩家操作时顺带检查：如果是恋人且48小时未互动，好感扣分，跌破60自动分手

// ==================== 指令：大学申请 ====================

const cmd_colleges = seal.ext.newCmdItemInfo();
cmd_colleges.name = "圣约翰专业";
cmd_colleges.help = "查看所有学校和专业的申请要求。可加学校名筛选：.圣约翰专业 MIT";
cmd_colleges.solve = function(ctx, msg, argv) {
    try {
    const filter = (argv.getArgN(1) || "").trim().toLowerCase();
    const tierLabel = ["", "T1 · 藤校/顶尖", "T2 · 顶尖非藤", "T3 · 好学校", "T4 · 保底/特招"];
    const botUid = ctx.endPoint.userId;
    const nodes = [];
    let found = false;

    nodes.push({ type: "node", data: { name: "圣约翰升学办公室", uin: botUid,
        content: "🎓【大学申请要求一览】\n\n每所学校的要求见下方各节点。\n\n" +
                 "📌 格式说明\nGPA≥ 最低绩点\nSAT≥ 最低SAT分\n科目成绩/课外/艺术/学生会要求见各条目\n\n" +
                 (filter ? ("🔍 筛选：" + filter) : "（显示全部学校）")
    }});

    const collegeKeys = Object.keys(COLLEGES);
    for (let tier = 1; tier <= 4; tier++) {
        const schoolKeys = collegeKeys.filter(function(k) { return COLLEGES[k].tier === tier; });
        if (!schoolKeys.length) continue;
        let tierContent = "━━ " + tierLabel[tier] + " ━━\n";
        let tierHasMatch = false;
        for (let si = 0; si < schoolKeys.length; si++) {
            const name = schoolKeys[si];
            const col = COLLEGES[name];
            if (filter && name.toLowerCase().indexOf(filter) < 0 && col.fullName.toLowerCase().indexOf(filter) < 0) continue;
            tierHasMatch = true;
            found = true;
            tierContent += "\n📍 " + col.fullName + "\n";
            const majorKeys = Object.keys(col.majors);
            for (let mi = 0; mi < majorKeys.length; mi++) {
                const major = majorKeys[mi];
                const req = col.majors[major];
                const gradeKeys = Object.keys(req.grades || {});
                const gradeReqs = gradeKeys.map(function(s) { return s + "≥" + GRADE_TIERS[req.grades[s]]; }).join(" ");
                const extObj = req.ext || {};
                const extKeys = Object.keys(extObj).filter(function(k) { return extObj[k] > 0; });
                const extReqs = extKeys.map(function(k) { return k + ":" + EXT_LABELS[extObj[k]]; }).join(" ");
                const artReq = req.artReq ? ("艺术:" + req.artReq.type + "≥" + ART_TIERS[req.artReq.tier]) : "";
                const councilReq = req.council ? ("学生会≥" + req.council) : "";
                const extras = [gradeReqs, extReqs, artReq, councilReq].filter(Boolean).join("  ");
                tierContent += "  · " + major + "　GPA≥" + req.gpa + "　SAT≥" + req.sat + (extras ? "\n    " + extras : "") + "\n";
            }
        }
        if (tierHasMatch) {
            nodes.push({ type: "node", data: { name: tierLabel[tier], uin: botUid, content: tierContent } });
        }
    }

    if (!found) {
        seal.replyToSender(ctx, msg, filter ? ("未找到与「" + filter + "」相关的学校。") : "（无数据）");
        return seal.ext.newCmdExecuteResult(true);
    }

    sendForwardMsg(ctx, msg, nodes, "🎓 大学申请要求列表（WS未配置，改用普通消息）\n请配置 ws地址 后使用合并转发。");
    return seal.ext.newCmdExecuteResult(true);
    } catch(e) {
        seal.replyToSender(ctx, msg, "❌ 专业列表错误：" + String(e));
        return seal.ext.newCmdExecuteResult(true);
    }
};
ext.cmdMap["圣约翰专业"] = cmd_colleges;

// ==================== 指令：申请大学 ====================

const cmd_apply = seal.ext.newCmdItemInfo();
cmd_apply.name = "圣约翰申请";
cmd_apply.help = "用法：.圣约翰申请 <学校名> <专业名>\n需到达六月（第10月）后解锁。系统检查GPA/SAT/成绩/课外/艺术/学生会是否全部达标。";
cmd_apply.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    if (getGameDay() < 10) {
        const left = 10 - getGameDay();
        seal.replyToSender(ctx, msg, !gameStarted() ? "⏳ 学期尚未开始，请等待管理员使用 .圣约翰开始学期。" : `⏳ 大学申请将在六月（第10月）开放，还剩 ${left} 个月。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 解析参数：支持 .圣约翰申请 MIT CS/Engineering
    const allArgs = [];
    let i = 1;
    while (argv.getArgN(i)) { allArgs.push(argv.getArgN(i)); i++; }
    if (allArgs.length < 2) {
        seal.replyToSender(ctx, msg, "❌ 用法：.圣约翰申请 <学校名> <专业名>\n例：.圣约翰申请 MIT CS/Engineering");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 模糊匹配学校名
    const schoolInput = allArgs[0];
    const majorInput = allArgs.slice(1).join(" ");
    const schoolKey = Object.keys(COLLEGES).find(k =>
        k.toLowerCase().includes(schoolInput.toLowerCase()) ||
        COLLEGES[k].fullName.toLowerCase().includes(schoolInput.toLowerCase())
    );
    if (!schoolKey) {
        seal.replyToSender(ctx, msg, `❌ 找不到学校"${schoolInput}"。使用 .圣约翰专业 查看所有学校。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const col = COLLEGES[schoolKey];
    const majorKey = Object.keys(col.majors).find(m =>
        m.toLowerCase().includes(majorInput.toLowerCase()) ||
        majorInput.toLowerCase().includes(m.toLowerCase())
    );
    if (!majorKey) {
        seal.replyToSender(ctx, msg, `❌ ${col.fullName} 没有"${majorInput}"专业。\n可选专业：${Object.keys(col.majors).join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const req = col.majors[majorKey];
    player = refreshEnergy(player);
    player = refreshStress(player);

    const gpa = calcGPA(player.grades);
    const sat = player.satScore;
    const failures = [];

    // GPA检查
    if (gpa < req.gpa) failures.push(`GPA不足（当前 ${gpa.toFixed(2)}，需要 ≥${req.gpa}）`);
    // SAT检查
    if (sat === null) failures.push("尚未参加SAT考试");
    else if (sat < req.sat) failures.push(`SAT不足（当前 ${sat}，需要 ≥${req.sat}）`);
    // 科目成绩检查
    for (const [subj, minTier] of Object.entries(req.grades || {})) {
        const cur = player.grades[subj]?.tier ?? 0;
        if (cur < minTier) failures.push(`${subj} 不足（当前 ${GRADE_TIERS[cur]}，需要 ≥${GRADE_TIERS[minTier]}）`);
    }
    // 课外检查
    for (const [extKey, minLevel] of Object.entries(req.ext || {})) {
        if (minLevel <= 0) continue;
        const cur = player.extracurriculars[extKey] || 0;
        if (cur < minLevel) failures.push(`课外活动 ${extKey} 不足（当前 ${EXT_LABELS[cur]}，需要 ${EXT_LABELS[minLevel]}）`);
    }
    // 艺术要求检查
    if (req.artReq) {
        if (!player.art) {
            failures.push("需要艺术方向天赋");
        } else {
            const cat = artCategory(player.art.type);
            if (cat !== req.artReq.type) failures.push(`需要 ${req.artReq.type} 类艺术方向`);
            else if (player.art.tier < req.artReq.tier) failures.push(`艺术等级不足（当前 ${ART_TIERS[player.art.tier]}，需要 ≥${ART_TIERS[req.artReq.tier]}）`);
        }
    }
    // 学生会检查
    if (req.council) {
        const councilOrder = [null, "班级代表", "干事", "副主席", "主席"];
        const reqIdx = councilOrder.indexOf(req.council);
        const curIdx = councilOrder.indexOf(player.councilRole || null);
        if (curIdx < reqIdx) failures.push(`需要学生会职位 ≥${req.council}（当前：${player.councilRole || "无"}）`);
    }

    if (failures.length > 0) {
        seal.replyToSender(ctx, msg,
            `📋 申请 ${col.fullName} · ${majorKey}\n\n❌ 条件未满足：\n` +
            failures.map(f => `  · ${f}`).join("\n") + "\n\n继续努力！"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    // 全部达标 → 录取！
    if (!player.acceptedList) player.acceptedList = [];
    const alreadyAccepted = player.acceptedList.some(function(a) {
        return a.school === schoolKey && a.major === majorKey;
    });
    if (alreadyAccepted) {
        seal.replyToSender(ctx, msg, `✅ 你已经被 ${col.fullName} · ${majorKey} 录取过了！`);
        return seal.ext.newCmdExecuteResult(true);
    }
    player.acceptedList.push({ school: schoolKey, major: majorKey, fullName: col.fullName });
    savePlayer(userId, player);
    sendAnnouncement(`🎓 ${CHARACTERS[player.charKey].fullName} 被 ${col.fullName} ${majorKey} 专业录取！`);
    const totalAccepted = player.acceptedList.length;
    seal.replyToSender(ctx, msg,
        `🎓【录取通知书】\n\n` +
        `恭喜 ${player.displayName}！\n` +
        `你已被 ${col.fullName} · ${majorKey} 专业正式录取！\n\n` +
        `GPA: ${gpa.toFixed(2)}　SAT: ${sat}\n` +
        (totalAccepted > 1 ? `\n📋 累计录取 ${totalAccepted} 所院校，继续冲！` : `\n🎉 首个 offer！继续申请其他学校吧。`)
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰申请"] = cmd_apply;

// ==================== 指令：公告群配置 ====================

// ==================== 指令：统一设置面板 ====================

const cmd_settings = seal.ext.newCmdItemInfo();
cmd_settings.name = "圣约翰设置";
cmd_settings.help = "用法：.圣约翰设置\n查看或修改管理设置。无参数显示面板；复制面板内容修改后原样发回即可应用。";
cmd_settings.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const cfg = getConfig();
    const twitterData = getTwitterData();

    // 判断是否为编辑模式：消息中含有 【xxx】yyy 格式
    const raw = msg.message || "";
    const editLines = [];
    raw.split("\n").forEach(function(line) {
        const m = line.trim().match(/^【([^】]+)】(.+)$/);
        if (m) editLines.push({ label: m[1].trim(), val: m[2].trim() });
    });

    if (editLines.length > 0) {
        // 权限检查：有管理员时只有管理员能改（除了【管理员】字段无管理员时任何人可设）
        const hasAdmin = !!cfg.adminId;
        const callerIsAdmin = isAdmin(userId);

        const success = [];
        const errors = [];

        editLines.forEach(function(e) {
            if (e.val === "未设置") return;
            if (e.label === "公告群") {
                if (hasAdmin && !callerIsAdmin) { errors.push("公告群：无权修改"); return; }
                cfg.announceGroup = e.val;
                cfg.announceEndpoint = ctx.endPoint?.userId || "";
                success.push(`公告群 → ${e.val}`);
            } else if (e.label === "推特群") {
                if (hasAdmin && !callerIsAdmin) { errors.push("推特群：无权修改"); return; }
                twitterData.twitterGroup = e.val;
                twitterData.twitterEndpoint = ctx.endPoint?.userId || "";
                success.push(`推特群 → ${e.val}`);
            } else if (e.label === "管理员") {
                if (hasAdmin && !callerIsAdmin) { errors.push("管理员：只有当前管理员可转让"); return; }
                const found = getPlayerByName(e.val);
                const targetId = found ? found.userId : e.val;
                cfg.adminId = targetId;
                success.push(`管理员 → ${targetId}`);
            }
        });

        if (success.length > 0) {
            saveConfig(cfg);
            saveTwitterData(twitterData);
        }

        let reply = `✅ 设置已更新（${success.length} 项）\n` + success.join("\n");
        if (errors.length) reply += `\n\n❌ 失败：\n` + errors.join("\n");
        seal.replyToSender(ctx, msg, reply);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 展示面板
    const semesterLine = cfg.gameStartTime
        ? `${new Date(cfg.gameStartTime).toLocaleString("zh-CN")}（第 ${getGameDay()} 月）`
        : "未开始（使用 .圣约翰开始学期 启动）";

    const adminHint = cfg.adminId
        ? "只有管理员可以修改设置。"
        : "⚠️ 尚无管理员——任何人均可填写【管理员】字段完成首次设置。";

    seal.replyToSender(ctx, msg,
        `.圣约翰设置\n` +
        `【公告群】${cfg.announceGroup || "未设置"}\n` +
        `【推特群】${twitterData.twitterGroup || "未设置"}\n` +
        `【管理员】${cfg.adminId || "未设置"}\n\n` +
        `📅 学期状态：${semesterLine}\n\n` +
        `复制上方三行修改内容后直接发回即可应用。留"未设置"的项不会被更改。\n${adminHint}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰设置"] = cmd_settings;

// ==================== 指令：开始学期 ====================

const cmd_start_semester = seal.ext.newCmdItemInfo();
cmd_start_semester.name = "圣约翰开始学期";
cmd_start_semester.help = "用法：.圣约翰开始学期\n【管理员专用】启动全局游戏时钟，所有玩家从此刻起共享同一时间线。只能由管理员执行。";
cmd_start_semester.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const cfg = getConfig();

    if (!cfg.adminId) {
        seal.replyToSender(ctx, msg, "⛔ 尚未设置管理员，请先使用 .圣约翰设置 填写【管理员】。");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!isAdmin(userId)) {
        seal.replyToSender(ctx, msg, "⛔ 只有管理员才能开始学期。");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (cfg.gameStartTime) {
        const day = getGameDay();
        const info = getDayInfo(day);
        seal.replyToSender(ctx, msg, `ℹ️ 学期已于 ${new Date(cfg.gameStartTime).toLocaleString("zh-CN")} 开始，当前是${info.label}（第 ${day} 月）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    cfg.gameStartTime = Date.now();
    saveConfig(cfg);
    const dateStr = new Date(cfg.gameStartTime).toLocaleString("zh-CN");
    seal.replyToSender(ctx, msg,
        `🎓【圣约翰预科高中】新学期正式开始！\n` +
        `📅 开学时间：${dateStr}\n` +
        `当前：九月·开学季（第1月）\n\n` +
        `所有同学可以开始入学了！使用 .圣约翰注册 选择角色。`
    );
    sendAnnouncement(`🎓 新学期正式开始！\n📅 ${dateStr}\n\n欢迎来到圣约翰预科高中，使用 .圣约翰注册 开始你的校园生活！`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰开始学期"] = cmd_start_semester;

// ==================== 指令：管理员调整属性 ====================
// 用法：.圣约翰调整 <英文名> <属性> <数值>
// 属性：精力/energy  压力/stress  人气/popularity  SAT  英语/Math/... 等科目名
// 数值：+20 / -10 / 直接写数字（绝对值覆盖）

const cmd_admin_adjust = seal.ext.newCmdItemInfo();
cmd_admin_adjust.name = "圣约翰调整";
cmd_admin_adjust.help = "用法：.圣约翰调整 <英文名> <属性> <数值>\n【管理员】直接修改玩家属性。\n属性：精力 压力 人气 SAT 英语/数学/历史/生物/化学/物理/外语/体育/艺术/音乐/计算机\n数值：+20 或 -10 为增减，直接写数字为覆盖。";
cmd_admin_adjust.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    if (!isAdmin(userId)) {
        seal.replyToSender(ctx, msg, "⛔ 只有管理员才能使用此指令。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const nameArg  = (argv.getArgN(1) || "").trim();
    const attrArg  = (argv.getArgN(2) || "").trim().toLowerCase();
    const valArg   = (argv.getArgN(3) || "").trim();

    if (!nameArg || !attrArg || !valArg) {
        seal.replyToSender(ctx, msg, "用法：.圣约翰调整 <英文名> <属性> <数值>\n例：.圣约翰调整 James 精力 +30");
        return seal.ext.newCmdExecuteResult(true);
    }

    const found = getPlayerByName(nameArg);
    if (!found) { seal.replyToSender(ctx, msg, `❌ 找不到玩家"${nameArg}"，请检查英文名是否正确。`); return seal.ext.newCmdExecuteResult(true); }
    const { userId: targetId, player } = found;

    // 解析数值：+N / -N 为增减，否则绝对覆盖
    const isDelta = /^[+-]/.test(valArg);
    const numVal  = parseInt(valArg, 10);
    if (isNaN(numVal)) { seal.replyToSender(ctx, msg, `❌ 数值"${valArg}"无效，请填数字（如 +20 或 50）。`); return seal.ext.newCmdExecuteResult(true); }

    function applyVal(current, min, max) {
        return Math.max(min, Math.min(max, isDelta ? (current + numVal) : numVal));
    }

    let changed = "";

    // 简单属性
    if (attrArg === "精力" || attrArg === "energy") {
        const before = player.energy;
        player.energy = applyVal(player.energy, 0, ENERGY_CAP);
        changed = `精力 ${before} → ${player.energy}`;

    } else if (attrArg === "压力" || attrArg === "stress") {
        const before = player.stress;
        player.stress = applyVal(player.stress, 0, STRESS_CAP);
        changed = `压力 ${before} → ${player.stress}`;

    } else if (attrArg === "人气" || attrArg === "popularity") {
        const before = player.popularity;
        player.popularity = applyVal(player.popularity, 0, POPULARITY_CAP);
        changed = `人气 ${before} → ${player.popularity}`;

    } else if (attrArg === "sat") {
        const before = player.satScore || 0;
        player.satScore = applyVal(before, 400, 1600);
        changed = `SAT ${before} → ${player.satScore}`;

    } else {
        // 科目成绩 tier 调整
        const resolvedSubj = SUBJECT_ALIAS[attrArg];
        if (!resolvedSubj || !player.grades || !player.grades[resolvedSubj]) {
            seal.replyToSender(ctx, msg, `❌ 未知属性"${attrArg}"。可选：精力 压力 人气 SAT 英语 数学 历史 生物 化学 物理 外语 体育 艺术 音乐 计算机`);
            return seal.ext.newCmdExecuteResult(true);
        }
        const g = player.grades[resolvedSubj];
        const before = g.tier;
        if (isDelta) {
            applyGradeChange(g, numVal);
            changed = `${resolvedSubj} ${numVal > 0 ? "+" : ""}${numVal} 进度 → ${GRADE_TIERS[g.tier]} (${g.progress}/100)`;
        } else {
            g.tier = Math.max(0, Math.min(7, numVal));
            g.progress = 0;
            changed = `${resolvedSubj} tier ${before} → ${g.tier} (${GRADE_TIERS[g.tier]})`;
        }
    }

    savePlayer(targetId, player);
    seal.replyToSender(ctx, msg, `✅【${player.displayName}】${changed}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰调整"] = cmd_admin_adjust;

// ==================== 关系自动衰减检查 ====================

function checkRelationDecay(userId) {
    let player = getPlayer(userId);
    if (!player || !player.partner) return;

    const partnerId = player.partner;
    const rel = getRelation(userId, partnerId);
    const now = Date.now();
    const elapsed = now - (rel.lastInteract || now);
    const intervals = Math.floor(elapsed / (48 * 3600 * 1000));
    if (intervals <= 0) return;

    rel.favor = Math.max(0, rel.favor - intervals * 8);
    rel.lastInteract = (rel.lastInteract || now) + intervals * 48 * 3600 * 1000;
    saveRelation(userId, partnerId, rel);

    if (rel.favor < 60) {
        // 自动分手
        let partnerPlayer = getPlayer(partnerId);
        const partnerName = partnerPlayer?.displayName || "???";
        player.partner = null;
        if (partnerPlayer) { partnerPlayer.partner = null; savePlayer(partnerId, partnerPlayer); }
        const relB = getRelation(partnerId, userId);
        relB.favor = 0;
        saveRelation(partnerId, userId, relB);
        savePlayer(userId, player);
        sendAnnouncement(`💔 ${CHARACTERS[player.charKey].fullName} 和 ${partnerName} 因长时间未联系而分手了……`);
    } else if (rel.favor < 75) {
        sendAnnouncement(`⚠️ ${CHARACTERS[player.charKey].fullName}：你和恋人的好感度偏低（${rel.favor}），记得多互动！`);
    }
}


// ==================== 指令：补课 ====================

const cmd_tutor = seal.ext.newCmdItemInfo();
cmd_tutor.name = "圣约翰补课";
cmd_tutor.help = "用法：.圣约翰补课 <英文名> <科目>\n辅导对方某科，双方成绩均提升，好感 +8。消耗20精力，挚友效果+20%，冷却4小时/科目/对象。";
cmd_tutor.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const nameArg = (argv.getArgN(1) || "").trim();
    const foundTarget = getPlayerByName(nameArg);
    if (!foundTarget || foundTarget.userId === userId) {
        seal.replyToSender(ctx, msg, `📖 用法：.圣约翰补课 <英文名> <科目>\n例如：.圣约翰补课 James Math\n可选科目：${ALL_SUBJECTS.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetId = foundTarget.userId;
    let targetPlayer = foundTarget.player;

    const subjRaw = (argv.getArgN(2) || "").trim().toLowerCase();
    if (!subjRaw) {
        seal.replyToSender(ctx, msg, `📖 用法：.圣约翰补课 <英文名> <科目>\n例如：.圣约翰补课 James Math\n可选科目：${ALL_SUBJECTS.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const subj = SUBJECT_ALIAS[subjRaw] || ALL_SUBJECTS.find(function(s) { return s.toLowerCase() === subjRaw; });
    if (!subj) {
        seal.replyToSender(ctx, msg, `❌ 科目"${argv.getArgN(2)}"不存在。\n可选：${ALL_SUBJECTS.join(" · ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cdKey = `tutor_${targetId}_${subj}`;
    if (isOnCooldownMs(player, cdKey, CD.tutor)) {
        seal.replyToSender(ctx, msg, `⏳ 已经给 ${targetPlayer.displayName} 补过 ${subj} 了，${cdRemainingMs(player, cdKey, CD.tutor)}后可再次辅导。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    player = refreshEnergy(player);
    if (!spendEnergy(player, COST.tutor)) {
        seal.replyToSender(ctx, msg, `⚡ 精力不足！需要 ${COST.tutor} 点，当前 ${player.energy} 点。`);
        savePlayer(userId, player); return seal.ext.newCmdExecuteResult(true);
    }

    const relAB = getRelation(userId, targetId);
    const isBestFriend = relAB.favor >= 100;
    const mult = isBestFriend ? 1.2 : 1.0;

    const selfDelta = Math.round(randInt(3, 6) * mult);
    const targetDelta = Math.round(randInt(8, 15) * mult);
    const favorGain = 8;

    applyGradeChange(player.grades[subj], selfDelta);
    applyGradeChange(targetPlayer.grades[subj], targetDelta);

    relAB.favor = Math.min(200, relAB.favor + favorGain);
    relAB.lastInteract = Date.now();
    const relBA = getRelation(targetId, userId);
    relBA.favor = Math.min(200, relBA.favor + favorGain);
    relBA.lastInteract = Date.now();
    saveRelation(userId, targetId, relAB);
    saveRelation(targetId, userId, relBA);

    if (!player.cooldowns) player.cooldowns = {};
    player.cooldowns[cdKey] = Date.now();
    savePlayer(userId, player);
    savePlayer(targetId, targetPlayer);

    const friendTag = isBestFriend ? "（挚友加成×1.2）" : "";
    seal.replyToSender(ctx, msg,
        `📖 补课：${subj} → ${targetPlayer.displayName}${friendTag}\n` +
        `你：${subj} +${selfDelta}　对方：${subj} +${targetDelta}\n` +
        `双方好感 +${favorGain}（你→对方：${relAB.favor}）\n` +
        `⚡ 精力剩余：${player.energy}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰补课"] = cmd_tutor;

// ==================== 指令：排行榜 ====================

const cmd_rank = seal.ext.newCmdItemInfo();
cmd_rank.name = "圣约翰排行";
cmd_rank.help = "查看GPA、人气、SAT三项排行榜（前5名）。";
cmd_rank.solve = function(ctx, msg, argv) {
    const all = getAllPlayers();
    const list = Object.entries(all).map(function(entry) {
        const uid = entry[0]; const p = entry[1];
        const ch = CHARACTERS[p.charKey];
        return {
            name: ch ? ch.fullName : (p.displayName || uid),
            gpa: p.grades ? calcGPA(p.grades) : 0,
            pop: p.popularity || 0,
            sat: p.satScore,
        };
    });

    function top5(arr, key, fmt) {
        return arr
            .filter(function(x) { return key === "sat" ? x.sat !== null : true; })
            .sort(function(a, b) { return (key === "sat" ? b.sat - a.sat : b[key] - a[key]); })
            .slice(0, 5)
            .map(function(x, i) {
                const medal = ["🥇","🥈","🥉","4️⃣","5️⃣"][i];
                return `${medal} ${x.name}　${fmt(x)}`;
            }).join("\n");
    }

    const gpaRank = top5(list, "gpa", function(x) { return "GPA " + x.gpa.toFixed(2); });
    const popRank = top5(list, "pop", function(x) { return "人气 " + x.pop; });
    const satRank = top5(list, "sat", function(x) { return "SAT " + x.sat; });

    seal.replyToSender(ctx, msg,
        `🏆【圣约翰排行榜】\n\n` +
        `📚 GPA 榜\n${gpaRank || "暂无数据"}\n\n` +
        `⭐ 人气榜\n${popRank || "暂无数据"}\n\n` +
        `📝 SAT 榜（最新成绩）\n${satRank || "暂无人考过SAT"}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰排行"] = cmd_rank;

// ==================== 指令：游戏状态 ====================

const cmd_game_status = seal.ext.newCmdItemInfo();
cmd_game_status.name = "圣约翰游戏状态";
cmd_game_status.help = "查看全局游戏状态：注册玩家、当前月份、录取情况、公告群配置。";
cmd_game_status.solve = function(ctx, msg, argv) {
    const all = getAllPlayers();
    const entries = Object.entries(all);

    if (!entries.length) {
        seal.replyToSender(ctx, msg, "🏫 目前还没有人注册圣约翰。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const cfg = getConfig();
    const currentDay = getGameDay();
    const dayInfo = getDayInfo(currentDay);
    const monthTag = gameStarted()
        ? `${dayInfo.label}（第${currentDay}月）${dayInfo.type !== "school" ? " 🏖️" : ""}`
        : "【学期尚未开始】";
    const startedAt = cfg.gameStartTime
        ? new Date(cfg.gameStartTime).toLocaleString("zh-CN")
        : "—";

    // 每位玩家的状态行
    const playerLines = entries.map(function(e) {
        const uid = e[0]; const p = e[1];
        const ch = CHARACTERS[p.charKey];
        const name = ch ? ch.fullName : (p.displayName || uid);
        const list = (p.acceptedList && p.acceptedList.length)
            ? p.acceptedList
            : (p.accepted ? [p.accepted] : []);
        const acceptedTag = list.length
            ? "\n      ✅ " + list.map(function(a) { return a.fullName + " · " + a.major; }).join("\n      ✅ ")
            : "";
        const gpa = p.grades ? calcGPA(p.grades).toFixed(2) : "—";
        return `  ${name}　GPA ${gpa}${acceptedTag}`;
    }).join("\n");

    // 录取统计
    const acceptedCount = entries.filter(function(e) {
        const p = e[1];
        return (p.acceptedList && p.acceptedList.length) || p.accepted;
    }).length;

    const announceTag = cfg.announceGroup
        ? `已配置（群 ${cfg.announceGroup}）`
        : "未配置";
    const adminTag = cfg.adminId || "未设置";

    const botUid = ctx.endPoint.userId;
    const nodes = [
        { type: "node", data: { name: "🏫 圣约翰学校概览", uin: botUid,
            content: "🏫【圣约翰预科高中 · 游戏状态】\n\n" +
                     "📅 当前：" + monthTag + "\n" +
                     "🗓️ 开学时间：" + startedAt + "\n" +
                     "👑 管理员：" + adminTag + "\n" +
                     "👥 注册人数：" + entries.length + " 人　已录取：" + acceptedCount + " 人\n" +
                     "📣 公告群：" + announceTag
        }},
        { type: "node", data: { name: "📋 在校名单", uin: botUid,
            content: "📋 在校名单（共 " + entries.length + " 人）\n\n" + playerLines
        }}
    ];
    sendForwardMsg(ctx, msg, nodes,
        "🏫【圣约翰游戏状态】\n当前：" + monthTag + "\n注册：" + entries.length + " 人，录取：" + acceptedCount + " 人"
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰游戏状态"] = cmd_game_status;

// ==================== 帮助指令 ====================

const cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = "圣约翰帮助";
cmd_help.help = "查看所有可用指令。";
cmd_help.solve = function(ctx, msg, argv) {
    const botUid = ctx.endPoint.userId;
    const nodes = [
        { type: "node", data: { name: "🏫 圣约翰预科高中", uin: botUid,
            content: "🏫【圣约翰预科高中·指令列表】\n\n" +
                     "📝 注册与查询\n" +
                     ".圣约翰注册 <英文名>\n.圣约翰档案\n.圣约翰精力\n\n" +
                     "📚 学习\n" +
                     ".圣约翰上课 <科目>\n.圣约翰自习\n.圣约翰备考SAT\n.圣约翰考SAT"
        }},
        { type: "node", data: { name: "🎨 艺术 / 社团 / 社交", uin: botUid,
            content: "🎨 艺术特招\n" +
                     ".圣约翰选艺术 <方向>\n.圣约翰练习\n.圣约翰演出\n\n" +
                     "🎭 社团\n" +
                     ".圣约翰社团列表\n.圣约翰加入 <社团>\n.圣约翰社团活动 <社团>\n.圣约翰我的社团\n.圣约翰竞选 <职位>\n\n" +
                     "💬 社交与人气\n" +
                     ".圣约翰社交\n.圣约翰发帖\n.圣约翰参加派对\n\n" +
                     "😴 压力管理\n" +
                     ".圣约翰休息\n.圣约翰放松"
        }},
        { type: "node", data: { name: "💕 关系 / 大学申请", uin: botUid,
            content: "💕 关系\n" +
                     ".圣约翰互动 <英文名>\n.圣约翰补课 <英文名> <科目>\n.圣约翰好感 <英文名>\n" +
                     ".圣约翰告白 <英文名>\n.圣约翰接受\n.圣约翰拒绝\n.圣约翰约会 <英文名>\n.圣约翰分手\n\n" +
                     "🎓 大学申请\n" +
                     ".圣约翰专业 [学校名]　（合并转发显示详情）\n.圣约翰申请 <学校> <专业>\n\n" +
                     "📊 排行与信息\n" +
                     ".圣约翰排行\n.圣约翰游戏状态"
        }},
        { type: "node", data: { name: "推特 / 收藏 / 管理", uin: botUid,
            content: "🔍 收藏系统\n" +
                     ".圣约翰寻宝　　随机捡到校园遗物（6小时冷却）\n" +
                     ".圣约翰收藏　　查看全部收集品\n\n" +
                     "【推特系统】\n" +
                     ".圣约翰注册推特 <用户名>\n.圣约翰推特 [用户名]\n" +
                     ".圣约翰发推 <内容>（2h冷却）\n" +
                     ".圣约翰点赞 <用户名>（30分钟冷却）\n" +
                     ".圣约翰转发 <用户名>（2h冷却）\n" +
                     "※内容含八卦/学习/运动关键词影响爆款概率\n\n" +
                     "⚙️ 管理\n" +
                     ".圣约翰设置\n.圣约翰开始学期\n" +
                     ".圣约翰调整 <英文名> <属性> <数值>"
        }},
        { type: "node", data: { name: "📅 学年日历", uin: botUid,
            content: "📅 学年日历\n\n" +
                     "第1月　九月 · 开学\n" +
                     "第2月　十月\n第3月　十一月\n第4月　十二月\n" +
                     "第5月　寒假 🏖️（精力恢复×2）\n" +
                     "第6月　二月\n第7月　三月\n第8月　四月\n第9月　五月\n" +
                     "第10月　六月 · 解锁大学申请\n" +
                     "第11-12月　暑假 🏖️（精力恢复×2）\n\n" +
                     "💡 提示\n" +
                     "・精力满上限120，每小时恢复6点（假期12点）\n" +
                     "・压力满100会触发崩溃状态\n" +
                     "・第10月起可用 .圣约翰申请 提交大学志愿"
        }}
    ];
    sendForwardMsg(ctx, msg, nodes, "🏫 请使用 .圣约翰帮助 查看指令（需在群内使用且配置ws地址）。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰帮助"] = cmd_help;

// ==================== 指令：寻宝（拾物系统）====================

function scavengeRoll() {
    const total = COLLECTIBLES.reduce(function(s, c) { return s + c.weight; }, 0);
    let r = Math.random() * total;
    for (const c of COLLECTIBLES) {
        r -= c.weight;
        if (r <= 0) return c;
    }
    return COLLECTIBLES[0];
}

function applyItemEffect(player, item) {
    if (!item.effect) return "";
    const e = item.effect;
    if (e.type === "energy") {
        player.energy = Math.min(ENERGY_CAP, (player.energy || 0) + e.value);
        return `⚡ 精力 +${e.value}`;
    }
    if (e.type === "stress") {
        player.stress = Math.max(0, (player.stress || 0) + e.value);
        return e.value < 0 ? `😌 压力 ${e.value}` : `😤 压力 +${e.value}`;
    }
    if (e.type === "grade") {
        if (player.grades && player.grades[e.subj]) {
            applyGradeChange(player.grades[e.subj], e.value);
            return `📚 ${e.subj} +${e.value} 进度`;
        }
    }
    if (e.type === "art_progress") {
        if (player.art) {
            player.art.progress = Math.min(99, (player.art.progress || 0) + e.value);
            return `🎨 艺术进度 +${e.value}`;
        }
    }
    if (e.type === "popularity") {
        player.popularity = Math.min(POPULARITY_CAP, (player.popularity || 0) + e.value);
        return `⭐ 人气 +${e.value}`;
    }
    if (e.type === "all_grades") {
        const subj = ALL_SUBJECTS[Math.floor(Math.random() * ALL_SUBJECTS.length)];
        applyGradeChange(player.grades[subj], e.value);
        return `✨ ${subj} +${e.value} 进度（随机科目）`;
    }
    return "";
}

const RARITY_LABEL = { common: "普通", rare: "稀有✨", legendary: "传说🌟" };

const cmd_scavenge = seal.ext.newCmdItemInfo();
cmd_scavenge.name = "圣约翰寻宝";
cmd_scavenge.help = "在校园角落寻找遗留物品。冷却3小时。部分物品拾取时即触发效果。";
cmd_scavenge.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }
    if (!gameStarted()) { seal.replyToSender(ctx, msg, "⏳ 学期尚未开始。"); return seal.ext.newCmdExecuteResult(true); }

    if (isOnCooldownMs(player, "scavenge", CD.scavenge)) {
        const remain = cdRemainingMs(player, "scavenge", CD.scavenge);
        seal.replyToSender(ctx, msg, `⏳ 还需 ${remain} 才能再次寻宝。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const item = scavengeRoll();
    if (!player.items) player.items = {};
    player.items[item.id] = (player.items[item.id] || 0) + 1;

    player.cooldowns["scavenge"] = Date.now();

    const effectText = applyItemEffect(player, item);
    savePlayer(userId, player);

    const total = Object.values(player.items).reduce(function(s, v) { return s + v; }, 0);
    seal.replyToSender(ctx, msg,
        `🔍 在校园角落发现了——\n\n` +
        `${item.emoji} 【${item.name}】${RARITY_LABEL[item.rarity]}\n` +
        `"${item.desc}"\n\n` +
        (effectText ? `效果：${effectText}\n` : "") +
        `收藏：${total} 件（使用 .圣约翰收藏 查看全部）`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰寻宝"] = cmd_scavenge;

// ==================== 指令：收藏 ====================

const cmd_collection = seal.ext.newCmdItemInfo();
cmd_collection.name = "圣约翰收藏";
cmd_collection.help = "查看已收集的校园物品。";
cmd_collection.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const items = player.items || {};
    const owned = Object.entries(items).filter(function(e) { return e[1] > 0; });
    if (!owned.length) {
        seal.replyToSender(ctx, msg, "🎒 收藏夹是空的，使用 .圣约翰寻宝 开始探索。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const total = owned.length;
    const byRarity = { legendary: [], rare: [], common: [] };
    owned.forEach(function(e) {
        const c = COLLECTIBLE_MAP[e[0]];
        if (c) byRarity[c.rarity].push(`${c.emoji} ${c.name}${e[1] > 1 ? " ×" + e[1] : ""}`);
    });

    let lines = [];
    if (byRarity.legendary.length) lines.push("🌟 传说\n  " + byRarity.legendary.join("　"));
    if (byRarity.rare.length)      lines.push("✨ 稀有\n  " + byRarity.rare.join("　"));
    if (byRarity.common.length)    lines.push("普通\n  " + byRarity.common.join("　"));

    const allIds = COLLECTIBLES.map(function(c) { return c.id; });
    const progress = `${total}/${allIds.length}`;

    seal.replyToSender(ctx, msg,
        `🎒【${player.displayName}的收藏】${progress} 种\n\n` +
        lines.join("\n\n")
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰收藏"] = cmd_collection;

// ==================== 推特系统：辅助函数 ====================

// ==================== 推特系统：内容分析 ====================

function analyzeTweetContent(content) {
    if (/八卦|drama|绯闻|恋爱|告白|分手|吵架|撕|爆料|秘密|喜欢|暗恋|cp|CP/.test(content))  return "drama";
    if (/作业|考试|sat|SAT|gpa|GPA|成绩|图书馆|自习|复习|学习|读书|deadline|刷题|背单词/.test(content)) return "academic";
    if (/比赛|训练|社团|演出|运动|赢|输|决赛|进球|练习|排练|表演/.test(content)) return "sports";
    return "personal";
}

const CONTENT_LABEL = { drama: "💬八卦", academic: "📚学习", sports: "🏆运动", personal: "✏️日常" };

function tweetRoll(followers, contentType) {
    let viralChance = Math.min(0.15, 0.03 + followers / 5000);
    let praiseW = 0.30, neutralW = 0.35, backlashW = 0.13, cancelW = 0.07;

    if (contentType === "drama") {
        viralChance = Math.min(0.28, viralChance * 2.2);
        praiseW = 0.25; neutralW = 0.22; backlashW = 0.22; cancelW = 0.13;
    } else if (contentType === "academic") {
        viralChance = viralChance * 0.4;
        praiseW = 0.42; neutralW = 0.40; backlashW = 0.05; cancelW = 0.03;
    } else if (contentType === "sports") {
        viralChance = Math.min(0.22, viralChance * 1.5);
        praiseW = 0.38; neutralW = 0.30; backlashW = 0.08; cancelW = 0.04;
    }

    const r = Math.random();
    if (r < viralChance)
        return { type: "viral",    followerDelta: randInt(40, 120), popDelta:  15, stressDelta:  0, label: "🔥 爆款！全校都在讨论" };
    const r2 = r - viralChance;
    if (r2 < praiseW)
        return { type: "praise",   followerDelta: randInt(8,   35), popDelta:   5, stressDelta:  0, label: "👍 收到一波好评" };
    if (r2 < praiseW + neutralW)
        return { type: "neutral",  followerDelta: randInt(1,    8), popDelta:   0, stressDelta:  0, label: "😐 普通一推" };
    if (r2 < praiseW + neutralW + backlashW)
        return { type: "backlash", followerDelta: -randInt(5,  30), popDelta: -10, stressDelta: 18, label: "💢 引发争议，部分人取关" };
    return     { type: "cancelled",followerDelta: randInt(3,   15), popDelta:  -5, stressDelta: 12, label: "🌊 被骂上热搜，吃瓜群众涌入" };
}

function checkFollowerMilestone(handle, before, after) {
    for (const m of [10, 50, 100, 300, 500, 1000]) {
        if (before < m && after >= m) return `🎉 @${handle} 粉丝突破 ${m}！`;
    }
    return null;
}

function broadcastToTwitterGroup(twitterData, text) {
    if (!twitterData.twitterGroup || !twitterData.twitterEndpoint) return;
    try {
        const endpoints = seal.getEndPoints();
        for (const ep of endpoints) {
            if (ep.userId === twitterData.twitterEndpoint) {
                const m = seal.newMessage();
                m.messageType = "group";
                m.groupId = buildGroupId(ep.userId, twitterData.twitterGroup);
                m.sender = { userId: ep.userId };
                const ctx2 = seal.createTempCtx(ep, m);
                seal.replyToSender(ctx2, m, text);
                return;
            }
        }
    } catch (e) {}
}



// ==================== 推特系统：NPC 自动评价 ====================

const SIM_COMMENTERS = [
    "James W.", "Noah P.", "Marcus H.", "Connor W.", "Jasper L.",
    "Rafael M.", "Oliver T.", "Eliot Z.", "Theo V.", "Callum R.", "Ben N.",
    "Chloe B.", "Zoe H.", "Lily C.", "Sofia R.", "Vivienne A.",
    "Margot S.", "Nadia O.", "Wren N.", "Amara D.", "Jess K.", "Petra H."
];

// 路人网友，仅在爆款/被骂时出现
const SIM_STRANGERS = [
    "user8823", "anonymous_xox", "passerby_k", "lurker2049", "ghost_reader",
    "nightowl_99", "randomguy404", "just_scrolling", "idk_who_this_is", "nobody_lol",
    "deleted_user", "unknown_acc", "quiet_one_7", "spectator_only", "throwaway_acc"
];

const SIM_COMMENTS = {
    drama: {
        viral: [
            "哦天哦天这什么情况！！", "等等这是真的吗？？", "cp感拉满了爆了",
            "全校都在传了", "这也太drama了吧我的天", "有人没有人快来看",
            "求爆料求爆料！！", "我的下巴掉了", "截图截图截图",
            "不是我疯了就是这个学校疯了", "昨天就感觉不对劲果然！",
            "转给我室友她在崩溃", "这条推特拯救了我无聊的下午",
            "不是吧不是吧真的假的", "我就说嘛！！",
            "刚从体育课回来看到这条腿都软了", "你知道多少快告诉我",
            "评论区人呢赶紧来", "这学校什么情况啊", "完了完了真的炸了",
            "朋友你今天救了我", "已转发给全宿舍", "这我要截图留着",
            "话题标签已经挂上了吗", "我要去校门口等消息",
            "全校就差一条横幅了", "戏比电视剧好看",
            "上课呢全程分心就等更新", "速速续集！！",
            "圣约翰推特值班记者就是你了"
        ],
        praise: [
            "八卦王本人", "好家伙有内情", "我就知道！！", "说出了我想说的",
            "懂的都懂👀", "这是什么神仙洞察力", "消息灵通选手",
            "你是怎么知道这些的", "没想到你敢说", "终于有人说了",
            "我憋这个好久了谢谢你", "发现你了八卦雷达",
            "情报收集能力满分", "这条我存了", "你说的对我没有意见",
            "其实大家都知道只是没人说", "有被你戳到", "不愧是你",
            "眼神犀利如刀", "洞察力是学的还是天生的",
            "暗处观察大师", "讲真的你说得很有道理",
            "这句话我要记一年", "这么说太对了",
            "我以为只有我这么想", "你说完我立刻点赞",
            "太准了吧！", "你这个人挺有意思的",
            "关注了，后续继续说", "说到点子上了"
        ],
        neutral: [
            "哦……", "看看", "有点意思", "知道了", "嗯嗯",
            "路过", "收到", "这样啊", "没想到",
            "哦这样", "懂了", "好", "ok",
            "学到了", "继续", "哦哦", "嗯",
            "看到了", "原来如此", "收下了",
            "嗯哼", "知道啦", "👀", "了解",
            "刷到了", "好的", "谢谢分享", "mark",
            "哦吼", "嗯？"
        ],
        backlash: [
            "这说的是谁啊", "有点过分了吧", "不评价。", "建议三思",
            "……", "真的有必要吗", "涉及到别人了吧这",
            "能不能别乱说", "当事人看到了怎么办", "发这个不太好吧",
            "你确定吗", "别人没同意你发这个",
            "这样讲话不合适", "说话之前想一下", "有点乱说了",
            "这不太好吧", "建议私信不要公开", "这会伤到别人的",
            "慎言慎言", "这条我觉得你发错了",
            "想好再发", "有没有想过当事人感受",
            "说话要负责任", "这种事不好随便讲",
            "不太建议这么说", "公开场合别这样",
            "有点不合适", "三思而后行",
            "我不同意", "这么说有点过"
        ],
        cancelled: [
            "好了别说了", "人都走了还在po", "评论区已经炸了",
            "这已经太明显了", "已举报", "建议删了",
            "你还没意识到问题吗", "不是在帮你，这样真的不好",
            "停了停了大家都看见了", "已经有人截图去传了",
            "现在删还来得及", "这条推文你会后悔的",
            "管理员马上来了", "太明显了真的", "收拾一下吧",
            "热度有了但代价太大", "我劝你冷静一下",
            "事情没你想的那么简单", "这件事不适合公开讲",
            "先把这条撤了再说", "你把人得罪完了",
            "评论区现在乱成一锅粥", "不建议继续发了",
            "已经有人在截图存证了", "你今天是在立flag吗",
            "这条之后你会很难受的", "踩雷了",
            "冷静期先别发东西", "出大事了",
            "已经扩散出去了拦不住了"
        ]
    },
    academic: {
        viral: [
            "学霸本人！！", "你为什么这么牛", "求带求带！！",
            "考场上你是神", "直接把我激励到了", "我不如你多了",
            "这人是怎么做到的", "学习机器在此", "下次考前发一条我来膜拜",
            "我现在立刻马上去图书馆", "被你羞辱到了但很服气",
            "你不累吗……（羡慕）", "我今天什么都没学你发了这个",
            "看完去背单词了", "你真的是我榜样",
            "不行了我也要努力了", "这条让我清醒了",
            "对比之下我在干嘛", "感觉能从屏幕里感受到你的气场",
            "好的我现在合上手机去学习", "把这条设成手机壁纸",
            "求问时间管理秘诀", "怎么考的快说",
            "你睡几个小时", "自律的极限就是你了",
            "天赋加努力等于你", "人和人的差距在这里",
            "我是垃圾你是王者", "被激励到热泪盈眶",
            "膜拜膜拜"
        ],
        praise: [
            "这种心态值得学习", "激励到我了", "好羡慕这种状态",
            "下次我也要这样", "冲冲冲！", "有被鼓励到",
            "记下了", "这个方法我要试试", "你是认真的吗太强了",
            "方向找对了", "思路很清晰", "这样做效率高",
            "好方法", "学到了", "感谢分享",
            "这个技巧有用", "试试看", "有道理",
            "受教了", "你比我想的更厉害",
            "加油！我也要这样", "一起卷！",
            "真的很好的分享", "这对我很有帮助",
            "支持！继续分享", "你总结得很好",
            "值得收藏", "有用！", "看完感觉可以了",
            "跟你学"
        ],
        neutral: [
            "哦好", "加油", "继续！", "嗯！",
            "好的好的", "收到了", "👍", "哦",
            "了解", "嗯嗯", "好", "ok",
            "看到了", "收下了", "知道了",
            "哦这样", "学习中", "mark",
            "懂了", "好的", "嗯哼",
            "好好好", "谢谢分享", "嗯？",
            "继续", "知道啦", "哦吼",
            "okay", "row", "好哦"
        ],
        backlash: [
            "凡尔赛警告", "优等生就是爱装", "有点烦这种po",
            "发这个干嘛", "别人不学习吗", "内卷标兵",
            "不是你卷就算了还要发出来", "懂了懂了你很厉害",
            "好的好的很强很强", "不用分享的谢谢",
            "自己知道就行了", "炫耀得很含蓄",
            "当别人都不努力吗", "凡尔赛体选手",
            "有没有想过别人看了怎么想", "卷王就卷王直说",
            "这不是在激励是在压人", "好吧你最厉害",
            "安静点可以吗", "这种帖子我最烦",
            "成绩好了不起啊", "不懂为什么要发这个",
            "看累了", "给别人留点活路",
            "又来了", "每次都这样",
            "你这是优等生病", "行吧你说啥都行",
            "知道了你牛", "ok我很菜满意了吗"
        ],
        cancelled: [
            "这不是炫耀吗", "有点离谱", "??",
            "你以为别人不努力吗", "这发出来是什么意思",
            "有点看不懂你的想法", "这样说很伤人的",
            "真的有必要晒出来吗", "搞得别人压力很大",
            "没必要的", "这是在攀比吗",
            "不好评价", "说这些意义是什么",
            "评论区现在什么感受", "有人觉得被针对了",
            "我觉得你可以不发", "这条有点踩线",
            "你可能没意识到但这样伤人", "删一删比较好",
            "不太适合发出来的东西", "三思",
            "好多人不舒服了", "评论区风向不好",
            "已经有人关掉通知了", "引起了反感",
            "你本意可能不是这样但结果就是这样", "适得其反",
            "本来是好事但发出来味道变了", "下次注意一下",
            "有点翻车了", "收收吧"
        ]
    },
    sports: {
        viral: [
            "全场MVP！！！！", "这场真的炸裂", "赢了赢了赢了！！",
            "太燃了！！", "决赛现场宣布！", "我在场上我就哭了",
            "运动员天花板", "你是为了赢而生的", "这一幕我记一辈子",
            "全程录像回来我还要看三遍", "这就是为什么我爱看比赛！！",
            "可以颁奖了不用比了", "神仙打架现场",
            "看完我浑身起鸡皮疙瘩", "这种比赛百年一遇",
            "体育馆快炸了", "全场都站起来了吧",
            "这场永远记得", "运动会名场面诞生了",
            "直接封神", "传说级别的发挥",
            "就算输了这场也值了", "场面太激动人心了",
            "我的心跳跟着加速", "好家伙这就是天才",
            "赶快出道吧", "这条要扩散出去的",
            "看到这个我的腿也软了", "让我站起来鼓掌",
            "年度最佳比赛"
        ],
        praise: [
            "厉害了！", "赛场上你最帅", "训练有素！",
            "这场看爽了", "体育生天花板！", "一直支持你",
            "平时训练没白费", "状态很好", "下次继续！",
            "看你比赛感觉我也能跑起来", "喜欢你比赛时的气场",
            "就该这样！", "越来越强了", "发挥稳定",
            "对自己有要求的人", "训练的成果出来了",
            "赛场上的你最好看", "这种状态保持住",
            "好好好，继续！", "进步很明显",
            "每次都在突破自己", "做到了！",
            "支持你", "看得出来准备充分了",
            "实力派", "这场发挥很稳",
            "专注的样子很帅", "比上次好很多",
            "坚持训练有回报", "你可以的"
        ],
        neutral: [
            "加油！", "好！", "继续冲！", "不错不错",
            "嗯", "👏", "看到了", "好的",
            "继续！", "还行", "ok",
            "努力了", "嗯嗯", "看了",
            "good", "挺好的", "收到",
            "知道啦", "不错", "了解",
            "嗯哼", "好好好", "行",
            "ok啊", "哦", "加油加油",
            "看看", "继续吧", "嗯！", "好哦"
        ],
        backlash: [
            "这场发挥一般？", "下次能不能稳一点", "比赛好像没这么好？",
            "有点失误吧", "上半场不是很稳", "还有提升空间",
            "我以为会更好", "这场有点可惜", "没发挥出来",
            "细节上有失误", "状态不是最好的",
            "下次加油", "能做到更好的", "有点遗憾",
            "没上次好", "可以反思一下", "细节需要改",
            "发挥失常了？", "有点出戏", "有些地方需要调整",
            "看得出还没到最好状态", "下次注意节奏",
            "稍微有点可惜", "体力不够？",
            "这场结果还好但过程有点", "判断有时差了一步",
            "整体还行，细节扣分", "可以再稳一点",
            "有波动，调整一下", "下次会更好的"
        ],
        cancelled: [
            "这场……有点说不清", "评论区已经乱了", "有争议",
            "裁判的问题还是自己的问题", "不好评价", "大家意见不一",
            "有人觉得有问题", "这场存在争议",
            "结果上说不清楚", "有点复杂",
            "评论区分两派了", "各说各的",
            "我也不知道该怎么说", "有说法不一",
            "这场情况比较特殊", "不太好定论",
            "双方各有道理", "再看看吧",
            "有点难评", "说不好谁对",
            "留给大家讨论", "有一些问题",
            "我觉得比较复杂", "这场确实有争议",
            "各有说法", "看立场",
            "两边都有人支持", "没有定论",
            "情况比较特殊", "先等等再说"
        ]
    },
    personal: {
        viral: [
            "引起我极大共鸣！！", "一万个赞！！", "一针见血",
            "这直接说出我心声了", "全校人都在转这条",
            "你是怎么知道我在想什么的", "这条推文我要存下来",
            "发给我好朋友了她也在点头", "说得我沉默了好久",
            "我今天什么都没干就刷到这条值了", "转发！所有人都需要看到这个",
            "好的我现在去反思我的人生", "为什么说出了我一直想说的话",
            "这句话太对了我保存了", "收藏夹又多一条",
            "刚刚还在想这件事就看到了", "这条推文有魔法",
            "我发给所有我认识的人了", "被准确击中",
            "怎么有人能把我的想法说得这么清楚", "全班都在转",
            "被你说得有点想哭", "我今天的心情被你描述出来了",
            "太真实了没有办法不转发", "这就是共情力满分",
            "我以为只有我一个人这么想", "说到灵魂里去了",
            "这条可以刷屏了", "所有人都需要看到",
            "完全准确", "你懂我"
        ],
        praise: [
            "说得有道理", "就是这样！", "懂的都懂",
            "对对对！", "这话没毛病", "有被说中",
            "想法很有趣", "思路清晰", "说到我心里了",
            "这个角度没想过", "同意！！", "点了个赞感觉不够",
            "讲得很好", "有道理", "我同意",
            "这样想也对", "挺好的观点", "认可",
            "说得在理", "没毛病", "确实",
            "支持这个看法", "赞成", "有想法",
            "这么看也说得通", "挺有意思的角度",
            "你想得挺深的", "不错的观点",
            "这句话我记住了", "说得好"
        ],
        neutral: [
            "哦", "嗯嗯", "看到了", "好的好的",
            "👀", "有点意思", "嗯", "路过",
            "了解", "嗯哼", "好", "ok",
            "看了", "收下了", "这样啊",
            "知道了", "哦这样", "mark",
            "懂了", "还行", "好好好",
            "谢谢分享", "嗯？", "继续",
            "知道啦", "哦吼", "okay",
            "啊", "哦哦", "好哦"
        ],
        backlash: [
            "没太看懂", "有必要po这个吗", "这是在说什么",
            "???", "所以是什么意思", "感觉逻辑有点问题",
            "不太认同", "你确定这个对吗", "有点奇怪",
            "这说法有点问题", "我不这么觉得",
            "这个逻辑不太通", "有点绕", "说清楚点",
            "不是很懂你想表达什么", "这能说出来？",
            "有点走偏了", "我看法不一样",
            "这不对吧", "不太一样的看法",
            "感觉哪里不对", "不认同这个",
            "这观点存疑", "可以再想想",
            "说法有点问题", "这么说不太准确",
            "我不同意", "存疑", "这不太对",
            "有点怪怪的"
        ],
        cancelled: [
            "这引发了争议", "评论区炸了", "热度来了但不是好的那种",
            "我觉得大家的反应也可以理解", "两边都有道理但你选了更难的那边",
            "撤回还来得及", "下次想好再发",
            "踩雷了", "大家反应很大",
            "说法引起了反弹", "评论区两边开打了",
            "你可能不是这个意思但大家是这么理解的",
            "本意和结果之间有误差", "翻车了",
            "有点控制不住局面了", "建议冷处理",
            "删了重新整理一下思路", "别继续讲了",
            "有些话发出来和说出来效果不一样",
            "先停下来看看反应", "这条不应该发",
            "事情往不好的方向发展了", "评论区快打起来了",
            "不如把评论关了", "建议沉默一段时间",
            "道歉可能更好", "有点失控",
            "说错了就承认吧", "现在能补救吗",
            "今天的推特课就此结束"
        ]
    }
};

function pickSimComments(contentType, rollType, count) {
    const pool = (SIM_COMMENTS[contentType] || SIM_COMMENTS.personal)[rollType] || SIM_COMMENTS.personal.neutral;
    // 爆款/被骂：最后一条来自陌生路人网友
    const useStranger = (rollType === "viral" || rollType === "cancelled") && count >= 2;
    const usedCommenters = [];
    const usedTexts = [];
    const result = [];
    for (var i = 0; i < count; i++) {
        var attempts = 0;
        var commenter, text;
        var fromStranger = useStranger && (i === count - 1);
        var namePool = fromStranger ? SIM_STRANGERS : SIM_COMMENTERS;
        do {
            commenter = namePool[Math.floor(Math.random() * namePool.length)];
            attempts++;
        } while (usedCommenters.indexOf(commenter) >= 0 && attempts < 10);
        attempts = 0;
        do {
            text = pool[Math.floor(Math.random() * pool.length)];
            attempts++;
        } while (usedTexts.indexOf(text) >= 0 && attempts < 10);
        usedCommenters.push(commenter);
        usedTexts.push(text);
        result.push({ name: commenter, text: text });
    }
    return result;
}

// ==================== 指令：注册推特 ====================

const cmd_twitter_register = seal.ext.newCmdItemInfo();
cmd_twitter_register.name = "圣约翰注册推特";
cmd_twitter_register.help = "用法：.圣约翰注册推特 <用户名>\n注册推特账号（字母/数字/下划线，3-20字符）。注册后用 .圣约翰发推 <内容> 发帖。";
cmd_twitter_register.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const handle = (argv.getArgN(1) || "").trim().toLowerCase();
    if (!handle || !/^[a-z0-9_]{3,20}$/.test(handle)) {
        seal.replyToSender(ctx, msg, "❌ 用户名须为 3-20 位字母/数字/下划线。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const twitterData = getTwitterData();

    if (twitterData.users[userId]) {
        seal.replyToSender(ctx, msg, `ℹ️ 你已注册推特账号 @${twitterData.users[userId].handle}。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (twitterData.handles[handle]) {
        seal.replyToSender(ctx, msg, `❌ 用户名 @${handle} 已被占用，请换一个。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    twitterData.handles[handle] = userId;
    twitterData.users[userId] = { handle, followers: 0, tweetCount: 0, praises: 0, backlashes: 0, lastTweetTime: 0 };
    saveTwitterData(twitterData);

    seal.replyToSender(ctx, msg,
        `【推特】 推特账号创建成功！\n\n用户名：@${handle}\n粉丝：0\n\n` +
        `发推方法：.圣约翰发推 <内容>（每2小时限发一条）`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰注册推特"] = cmd_twitter_register;

// ==================== 指令：推特主页 ====================

const cmd_twitter_profile = seal.ext.newCmdItemInfo();
cmd_twitter_profile.name = "圣约翰推特";
cmd_twitter_profile.help = "用法：.圣约翰推特 [用户名]\n查看自己或他人的推特主页。不填则查自己。";
cmd_twitter_profile.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const twitterData = getTwitterData();
    let targetUserId = userId;
    const handleArg = (argv.getArgN(1) || "").trim().toLowerCase().replace(/^@/, "");

    if (handleArg) {
        const found = twitterData.handles[handleArg];
        if (!found) { seal.replyToSender(ctx, msg, `❌ 找不到 @${handleArg}，可能未注册推特。`); return seal.ext.newCmdExecuteResult(true); }
        targetUserId = found;
    }

    const tUser = twitterData.users[targetUserId];
    if (!tUser) {
        seal.replyToSender(ctx, msg, handleArg ? `❌ @${handleArg} 未注册推特。` : "❌ 你还没有注册推特，使用 .圣约翰注册推特 <用户名>。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetPlayer = getPlayer(targetUserId);
    const name = targetPlayer ? targetPlayer.displayName : tUser.handle;
    const lastTime = tUser.lastTweetTime || tUser.lastTweet || 0;
    const cdLeft = lastTime ? Math.max(0, Math.ceil((CD.tweet - (Date.now() - lastTime)) / 60000)) : 0;
    const cdLine = targetUserId === userId && cdLeft > 0 ? `\n⏳ 发推冷却：还需 ${cdLeft} 分钟` : "";

    // 最新推文展示
    let tweetLine = "";
    if (tUser.latestTweet) {
        const lt = tUser.latestTweet;
        const preview = lt.content.length > 60 ? lt.content.slice(0, 60) + "…" : lt.content;
        const timeAgo = Math.floor((Date.now() - lt.time) / 3600000);
        const timeStr = timeAgo < 1 ? "刚刚" : timeAgo < 24 ? (timeAgo + "小时前") : (Math.floor(timeAgo / 24) + "天前");
        tweetLine = "\n\n最新推文 " + (CONTENT_LABEL[lt.contentType] || "") + " · " + timeStr +
                    "\n\u201c" + preview + "\u201d\n" +
                    "👍" + (lt.likes || 0) + "  🔁" + (lt.retweets || 0) + "  💬" + (lt.replies || 0);
        if (lt.simComments && lt.simComments.length) {
            tweetLine += "\n" + lt.simComments.map(function(c) { return "  💬 " + c.name + "：" + c.text; }).join("\n");
        }
    }

    // 粉丝等级徽章
    const f = tUser.followers || 0;
    const badge = f >= 1000 ? "🌟" : f >= 500 ? "⭐" : f >= 100 ? "✨" : f >= 50 ? "🔹" : "";

    seal.replyToSender(ctx, msg,
        `【推特】【${name} @${tUser.handle}】${badge}\n\n` +
        `粉丝：${f}　推文：${tUser.tweetCount || 0}\n` +
        `好评：${tUser.praises || 0}　争议：${tUser.backlashes || 0}` +
        tweetLine + cdLine
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰推特"] = cmd_twitter_profile;

// ==================== 指令：发推 ====================

const cmd_tweet = seal.ext.newCmdItemInfo();
cmd_tweet.name = "圣约翰发推";
cmd_tweet.help = "用法：.圣约翰发推 <内容>\n用推特账号发一条推文。2小时冷却。";
cmd_tweet.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    let player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const twitterData = getTwitterData();
    const myUser = twitterData.users[userId];
    if (!myUser) {
        seal.replyToSender(ctx, msg, "❌ 你还没有推特账号，请先 .圣约翰注册推特 <用户名>。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const now = Date.now();
    const lastTweet = myUser.lastTweetTime || 0;
    if (now - lastTweet < CD.tweet) {
        const mins = Math.ceil((CD.tweet - (now - lastTweet)) / 60000);
        seal.replyToSender(ctx, msg, "⏳ 发推冷却中，还需 " + mins + " 分钟。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const argParts = [];
    var ai = 1;
    while (true) {
        const a = argv.getArgN(ai);
        if (!a) break;
        argParts.push(a);
        ai++;
    }
    const content = argParts.join(" ").trim();
    if (!content) {
        seal.replyToSender(ctx, msg, "用法：.圣约翰发推 <内容>");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (content.length > 280) {
        seal.replyToSender(ctx, msg, "❌ 推文不能超过 280 字。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const contentType = analyzeTweetContent(content);
    const roll = tweetRoll(myUser.followers || 0, contentType);
    const prevFollowers = myUser.followers || 0;

    myUser.followers = Math.max(0, prevFollowers + roll.followerDelta);
    myUser.tweetCount = (myUser.tweetCount || 0) + 1;
    myUser.lastTweetTime = now;
    if (roll.type === "praise" || roll.type === "viral") myUser.praises = (myUser.praises || 0) + 1;
    if (roll.type === "backlash" || roll.type === "cancelled") myUser.backlashes = (myUser.backlashes || 0) + 1;
    const commentCount = roll.type === "viral" ? 3 : roll.type === "cancelled" ? 3 : roll.type === "praise" ? 2 : roll.type === "backlash" ? 2 : 1;
    const simComments = pickSimComments(contentType, roll.type, commentCount);
    myUser.latestTweet = { content: content, contentType: contentType, time: now, likes: 0, retweets: 0, replies: simComments.length, simComments: simComments };

    player.popularity = Math.max(0, Math.min(POPULARITY_CAP, (player.popularity || 0) + roll.popDelta));
    if (roll.stressDelta > 0) player.stress = Math.min(100, (player.stress || 0) + roll.stressDelta);
    savePlayer(userId, player);
    saveTwitterData(twitterData);

    const deltaSign = roll.followerDelta >= 0 ? "+" : "";
    const commentLines = simComments.map(function(c) { return "  💬 " + c.name + "\uff1a" + c.text; }).join("\n");
    seal.replyToSender(ctx, msg,
        "\U0001F426 @" + myUser.handle + " \u53d1\u63a8\u4e86\uff01\n" +
        "\u201c" + content + "\u201d\n\n" +
        roll.label + "\n" +
        "\u7c89\u4e1d " + deltaSign + roll.followerDelta + " \u2192 " + myUser.followers +
        (roll.popDelta !== 0 ? "\u3000\u4eba\u6c14 " + (roll.popDelta > 0 ? "+" : "") + roll.popDelta : "") +
        (roll.stressDelta > 0 ? "\u3000\u538b\u529b +" + roll.stressDelta : "") +
        "\n\n\U0001F4AC \u8bc4\u8bba\n" + commentLines
    );

    broadcastToTwitterGroup(twitterData,
        "【推特】【@" + myUser.handle + "（" + player.displayName + "）发推了】" +
        " " + (CONTENT_LABEL[contentType] || "") + "\n" +
        "\u201c" + content.slice(0, 120) + "\u201d\n" +
        roll.label
    );

    const milestone = checkFollowerMilestone(myUser.handle, prevFollowers, myUser.followers);
    if (milestone) broadcastToTwitterGroup(twitterData, milestone);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰发推"] = cmd_tweet;

// ==================== 指令：点赞 ====================

const cmd_like = seal.ext.newCmdItemInfo();
cmd_like.name = "圣约翰点赞";
cmd_like.help = "用法：.圣约翰点赞 <用户名>\n给该用户最新推文点赞。每人每账号30分钟冷却。";
cmd_like.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const handleArg = (argv.getArgN(1) || "").trim().toLowerCase().replace(/^@/, "");
    if (!handleArg) { seal.replyToSender(ctx, msg, "用法：.圣约翰点赞 <用户名>"); return seal.ext.newCmdExecuteResult(true); }

    const twitterData = getTwitterData();
    const targetId = twitterData.handles[handleArg];
    if (!targetId) { seal.replyToSender(ctx, msg, `❌ 找不到 @${handleArg}。`); return seal.ext.newCmdExecuteResult(true); }
    if (targetId === userId) { seal.replyToSender(ctx, msg, "❌ 不能给自己点赞。"); return seal.ext.newCmdExecuteResult(true); }

    const targetUser = twitterData.users[targetId];
    if (!targetUser || !targetUser.latestTweet) { seal.replyToSender(ctx, msg, `❌ @${handleArg} 还没有发过推文。`); return seal.ext.newCmdExecuteResult(true); }

    const now = Date.now();
    const cdKey = userId + "_like_" + handleArg;
    const likeCDMs = 30 * 60 * 1000;
    if (twitterData.likeCDs[cdKey] && now - twitterData.likeCDs[cdKey] < likeCDMs) {
        const mins = Math.ceil((likeCDMs - (now - twitterData.likeCDs[cdKey])) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 点赞冷却中，还需 ${mins} 分钟。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const gain = randInt(2, 8);
    const prevFollowers = targetUser.followers || 0;
    targetUser.latestTweet.likes = (targetUser.latestTweet.likes || 0) + 1;
    targetUser.followers = prevFollowers + gain;
    twitterData.likeCDs[cdKey] = now;
    saveTwitterData(twitterData);

    seal.replyToSender(ctx, msg, `👍 点赞了 @${handleArg} 的推文！（他的粉丝 +${gain}）`);

    // 点赞数达到5条时广播
    if (targetUser.latestTweet.likes === 5) {
        const lt = targetUser.latestTweet;
        const targetPlayer = getPlayer(targetId);
        const tName = targetPlayer ? targetPlayer.displayName : handleArg;
        broadcastToTwitterGroup(twitterData,
            `🔥【正在流行】@${handleArg}（${tName}）的推文获得了 5 个赞！\n"${lt.content.slice(0, 80)}"`
        );
    }

    const milestone = checkFollowerMilestone(handleArg, prevFollowers, targetUser.followers);
    if (milestone) broadcastToTwitterGroup(twitterData, milestone);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰点赞"] = cmd_like;

// ==================== 指令：转发 ====================

const cmd_retweet = seal.ext.newCmdItemInfo();
cmd_retweet.name = "圣约翰转发";
cmd_retweet.help = "用法：.圣约翰转发 <用户名>\n转发该用户最新推文，帮助扩散，对方涨粉，你也获得少量曝光。每人每账号2小时冷却。";
cmd_retweet.solve = function(ctx, msg, argv) {
    const userId = ctx.player.userId;
    const player = getPlayer(userId);
    if (!player) { seal.replyToSender(ctx, msg, "🏫 请先 .圣约翰注册 入学。"); return seal.ext.newCmdExecuteResult(true); }

    const myTwitter = getTwitterData().users[userId];
    if (!myTwitter) { seal.replyToSender(ctx, msg, "❌ 请先 .圣约翰注册推特 才能转发。"); return seal.ext.newCmdExecuteResult(true); }

    const handleArg = (argv.getArgN(1) || "").trim().toLowerCase().replace(/^@/, "");
    if (!handleArg) { seal.replyToSender(ctx, msg, "用法：.圣约翰转发 <用户名>"); return seal.ext.newCmdExecuteResult(true); }

    const twitterData = getTwitterData();
    const targetId = twitterData.handles[handleArg];
    if (!targetId) { seal.replyToSender(ctx, msg, `❌ 找不到 @${handleArg}。`); return seal.ext.newCmdExecuteResult(true); }
    if (targetId === userId) { seal.replyToSender(ctx, msg, "❌ 不能转发自己的推文。"); return seal.ext.newCmdExecuteResult(true); }

    const targetUser = twitterData.users[targetId];
    if (!targetUser || !targetUser.latestTweet) { seal.replyToSender(ctx, msg, `❌ @${handleArg} 还没有发过推文。`); return seal.ext.newCmdExecuteResult(true); }

    const now = Date.now();
    const cdKey = userId + "_rt_" + handleArg;
    const rtCDMs = 2 * 3600 * 1000;
    if (twitterData.retweetCDs[cdKey] && now - twitterData.retweetCDs[cdKey] < rtCDMs) {
        const mins = Math.ceil((rtCDMs - (now - twitterData.retweetCDs[cdKey])) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 转发冷却中，还需 ${mins} 分钟。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetGain = randInt(10, 30);
    const myGain = randInt(2, 8);
    const prevTargetFollowers = targetUser.followers || 0;
    const myUser = twitterData.users[userId];

    targetUser.latestTweet.retweets = (targetUser.latestTweet.retweets || 0) + 1;
    targetUser.followers = prevTargetFollowers + targetGain;
    if (myUser) myUser.followers = (myUser.followers || 0) + myGain;
    twitterData.retweetCDs[cdKey] = now;
    saveTwitterData(twitterData);

    const lt = targetUser.latestTweet;
    const targetPlayer = getPlayer(targetId);
    const tName = targetPlayer ? targetPlayer.displayName : handleArg;
    const preview = lt.content.length > 60 ? lt.content.slice(0, 60) + "…" : lt.content;

    seal.replyToSender(ctx, msg,
        `🔁 转发了 @${handleArg} 的推文！\n"${preview}"\n\n@${handleArg} 粉丝 +${targetGain}　你 +${myGain}`
    );

    broadcastToTwitterGroup(twitterData,
        `🔁【@${myTwitter.handle} 转发了 @${handleArg}（${tName}）】\n"${lt.content.slice(0, 100)}"`
    );

    const milestone = checkFollowerMilestone(handleArg, prevTargetFollowers, targetUser.followers);
    if (milestone) broadcastToTwitterGroup(twitterData, milestone);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["圣约翰转发"] = cmd_retweet;

// ==================== Gossip Girl 系统 ====================

var _lastSchedulerCheck = 0;

function getGossipData() {
    var raw = ext.storageGet("gossipData") || "{}";
    var d;
    try { d = JSON.parse(raw); } catch(e) { d = {}; }
    if (!Array.isArray(d.queue)) d.queue = [];
    if (!d.interval) d.interval = 4;
    if (!d.lastSent) d.lastSent = 0;
    if (!d.accountName) d.accountName = "Gossip Girl";
    if (!d.handle) d.handle = "gossipgirl";
    return d;
}

function saveGossipData(d) {
    ext.storageSet("gossipData", JSON.stringify(d));
}

function fireGossipPost() {
    var d = getGossipData();
    if (!d.queue.length) return;
    var post = d.queue.shift();
    d.lastSent = Date.now();
    saveGossipData(d);

    var twitterData = getTwitterData();
    if (!twitterData.twitterGroup) return;
    var eps = seal.getEndPoints();
    for (var i = 0; i < eps.length; i++) {
        var ep = eps[i];
        var m = seal.newMessage();
        m.groupId = buildGroupId(ep.userId, twitterData.twitterGroup);
        m.messageType = "group";
        var tCtx = seal.createTempCtx(ep, m);
        seal.replyToSender(tCtx, m,
            "【Gossip Girl】\n" +
            "@" + d.handle + "（" + d.accountName + "）\n\n" +
            post + "\n\n" +
            "XOXO, Gossip Girl"
        );
    }
}

// 每条指令触发时做一次懒检查，最多每5分钟检查一次
function checkGossipQueue() {
    var now = Date.now();
    if (now - _lastGossipCheck < 5 * 60 * 1000) return;
    _lastGossipCheck = now;
    var d = getGossipData();
    if (!d.queue.length) return;
    if (now - d.lastSent >= d.interval * 3600 * 1000) {
        fireGossipPost();
    }
}

const cmd_gossip = seal.ext.newCmdItemInfo();
cmd_gossip.name = "圣约翰gossip";
cmd_gossip.help = [
    "管理员专用：管理 Gossip Girl 自动发帖队列。",
    "子命令：",
    "  .圣约翰gossip 添加 <内容>       加入队列",
    "  .圣约翰gossip 队列              查看待发帖子",
    "  .圣约翰gossip 清空              清空队列",
    "  .圣约翰gossip 发送              立即发送队首帖子",
    "  .圣约翰gossip 间隔 <小时>       设置自动发帖间隔（默认4h）",
    "  .圣约翰gossip 账号 <名称> <handle>  设置账号名和推特ID"
].join("\n");
cmd_gossip.solve = function(ctx, msg, argv) {
    var r = seal.ext.newCmdExecuteResult(true);
    if (!isAdmin(ctx.player.userId)) {
        seal.replyToSender(ctx, msg, "❌ 仅管理员可用。");
        return r;
    }
    var sub = (argv.getArgN(1) || "").trim();
    var d = getGossipData();

    if (sub === "添加") {
        // 添加
        var parts = [];
        var ai = 2;
        while (true) { var a = argv.getArgN(ai); if (!a) break; parts.push(a); ai++; }
        var content = parts.join(" ").trim();
        if (!content) { seal.replyToSender(ctx, msg, "用法：.圣约翰gossip 添加 <内容>"); return r; }
        d.queue.push(content);
        saveGossipData(d);
        seal.replyToSender(ctx, msg, "✅ 已加入队列（当前队列 " + d.queue.length + " 条）。");

    } else if (sub === "队列") {
        // 队列
        if (!d.queue.length) { seal.replyToSender(ctx, msg, "📬 队列为空。"); return r; }
        var lines = d.queue.map(function(item, idx) { return (idx + 1) + ". " + item; });
        var nextIn = d.lastSent ? Math.max(0, Math.ceil((d.interval * 3600000 - (Date.now() - d.lastSent)) / 60000)) : 0;
        seal.replyToSender(ctx, msg,
            "Gossip Girl 队列（" + d.queue.length + " 条）\n间隔：" + d.interval + "h\n" +
            "下条大约：" + (nextIn > 0 ? nextIn + " 分钟后" : "随时可发") + "\n\n" +
            lines.join("\n")
        );

    } else if (sub === "清空") {
        // 清空
        d.queue = [];
        saveGossipData(d);
        seal.replyToSender(ctx, msg, "✅ 队列已清空。");

    } else if (sub === "发送") {
        // 发送
        if (!d.queue.length) { seal.replyToSender(ctx, msg, "📬 队列为空，无内容可发。"); return r; }
        fireGossipPost();
        seal.replyToSender(ctx, msg, "✅ 已发送队首帖子。");

    } else if (sub === "间隔") {
        // 间隔
        var hrs = parseFloat(argv.getArgN(2) || "");
        if (isNaN(hrs) || hrs < 0.5) { seal.replyToSender(ctx, msg, "请输入小时数（最小 0.5）。"); return r; }
        d.interval = hrs;
        saveGossipData(d);
        seal.replyToSender(ctx, msg, "✅ 自动发帖间隔设为 " + hrs + " 小时。");

    } else if (sub === "账号") {
        // 账号
        var nameArg = (argv.getArgN(2) || "").trim();
        var handleArg = (argv.getArgN(3) || "").trim().replace(/^@/, "").toLowerCase();
        if (!nameArg || !handleArg) { seal.replyToSender(ctx, msg, "用法：.圣约翰gossip 账号 <名称> <handle>"); return r; }
        d.accountName = nameArg;
        d.handle = handleArg;
        saveGossipData(d);
        seal.replyToSender(ctx, msg, "✅ Gossip Girl 账号：" + d.accountName + " @" + d.handle);

    } else {
        seal.replyToSender(ctx, msg, cmd_gossip.help);
    }
    return r;
};
ext.cmdMap["圣约翰gossip"] = cmd_gossip;

// ==================== NPC 自动互动（每小时）====================

function checkTwitterNpcEngagement() {
    var twitterData = getTwitterData();
    var now = Date.now();
    if (now - (twitterData.lastNpcRun || 0) < 3600 * 1000) return;
    twitterData.lastNpcRun = now;

    var users = twitterData.users || {};
    // 找出过去24小时内有发推的玩家
    var active = [];
    for (var uid in users) {
        var u = users[uid];
        if (u.latestTweet && u.latestTweet.time && (now - u.latestTweet.time < 24 * 3600 * 1000)) {
            active.push({ uid: uid, u: u });
        }
    }
    if (!active.length) { saveTwitterData(twitterData); return; }

    // 随机最多3人
    active.sort(function() { return Math.random() - 0.5; });
    var picks = active.slice(0, Math.min(3, active.length));

    if (!twitterData.twitterGroup) { saveTwitterData(twitterData); return; }
    var eps = seal.getEndPoints();

    var lines = [];
    for (var pi = 0; pi < picks.length; pi++) {
        var entry = picks[pi];
        var tUser = entry.u;
        var lt = tUser.latestTweet;
        var roll = Math.random();

        if (roll < 0.45) {
            // 评论
            var newComments = pickSimComments(lt.contentType || "personal", "neutral", 1);
            if (!Array.isArray(lt.simComments)) lt.simComments = [];
            lt.simComments = lt.simComments.concat(newComments);
            lt.replies = lt.simComments.length;
            var c = newComments[0];
            lines.push("💬 " + c.name + " 评论了 @" + tUser.handle + "：「" + c.text + "」");
        } else if (roll < 0.80) {
            // 点赞
            var likeCount = Math.floor(Math.random() * 3) + 1;
            lt.likes = (lt.likes || 0) + likeCount;
            var liker = SIM_COMMENTERS[Math.floor(Math.random() * SIM_COMMENTERS.length)];
            lines.push("👍 " + liker + " 等 " + likeCount + " 人点赞了 @" + tUser.handle + " 的推文");
        }
        // else: 20% 无互动
        twitterData.users[entry.uid] = tUser;
    }

    saveTwitterData(twitterData);

    if (!lines.length) return;
    var text = "【推特互动播报】\n" + lines.join("\n");
    for (var i = 0; i < eps.length; i++) {
        var ep = eps[i];
        var m = seal.newMessage();
        m.groupId = buildGroupId(ep.userId, twitterData.twitterGroup);
        m.messageType = "group";
        var tCtx = seal.createTempCtx(ep, m);
        seal.replyToSender(tCtx, m, text);
    }
}

// ==================== 通用调度器 ====================

function checkGossipQueue() {
    var d = getGossipData();
    var now = Date.now();
    if (d.queue.length && now - d.lastSent >= d.interval * 3600 * 1000) {
        fireGossipPost();
    }
}

ext.onNotCommandReceived = function(ctx, msg) {
    var now = Date.now();
    if (now - _lastSchedulerCheck < 5 * 60 * 1000) return;
    _lastSchedulerCheck = now;
    checkGossipQueue();
    checkTwitterNpcEngagement();
};

