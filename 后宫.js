"use strict";
// ==UserScript==
// @name         后宫·红颜策 (终极全能整合版)
// @author       长日将尽
// @version      8.0.0
// @description  包含生产、修习、侍寝、子嗣成长、有名有姓、手动晋升、体力恢复
// @timestamp    1713827133
// @license      Apache-2
// ==/UserScript==

let ext = seal.ext.find("HaremMasterFinal");
if (!ext) {
    ext = seal.ext.new("HaremMasterFinal", "长日将尽", "8.0.0");
    seal.ext.register(ext);
}

const DATA_KEY = "harem_final_data";
const RECOVERY_TIME = 20 * 60 * 1000; 
const STAMINA_TICK = 15;

// ========== 1. 位分等级与严苛要求 (整合了子嗣岁数) ==========
const LEVELS = [
    { name: "官女子", reqExp: 0, reqChild: 0, reqAge: 0, reqAttr: {} },
    { name: "答应", reqExp: 500, reqChild: 0, reqAge: 0, reqAttr: { charm: 30, etiquette: 20 } },
    { name: "常在", reqExp: 1500, reqChild: 0, reqAge: 0, reqAttr: { charm: 60, talent: 50, prestige: 20 } },
    { name: "贵人", reqExp: 5000, reqChild: 0, reqAge: 0, reqAttr: { charm: 120, wit: 100, etiquette: 150 } },
    { name: "嫔", reqExp: 12000, reqChild: 1, reqAge: 3, reqAttr: { wit: 250, prestige: 300 } },
    { name: "妃", reqExp: 35000, reqChild: 1, reqAge: 6, reqAttr: { charm: 500, wit: 600, talent: 500 } },
    { name: "贵妃", reqExp: 100000, reqChild: 2, reqAge: 8, reqAttr: { prestige: 1000, wit: 1200, health: 80 } },
    { name: "皇贵妃", reqExp: 200000, reqChild: 2, reqAge: 12, reqAttr: { wit: 2500, talent: 2000, etiquette: 1500 } },
    { name: "皇后", reqExp: 500000, reqChild: 3, reqAge: 15, reqAttr: { wit: 5000, prestige: 5000, health: 100, etiquette: 2500 } }
];

// 新增：装备库
const SHOP_ITEMS = {
    "点翠头面": { price: 800, attr: "charm", value: 15, desc: "珠翠满头，华贵异常。" },
    "流彩云龙裙": { price: 1200, attr: "etiquette", value: 20, desc: "流光溢彩，动人心魄。" },
    "檀香木梳": { price: 300, attr: "talent", value: 5, desc: "暗香浮动，沁人心脾。" }
};

// ========== 扩充后的基础数据库 ==========
const SURNAMES = [
    "乌拉那拉", "钮祜禄", "富察", "甄", "年", "叶赫那拉", "博尔济吉特", "索绰罗", 
    "阿鲁特", "喜塔腊", "佟佳", "马佳", "瓜尔佳", "完颜", "赫舍里", "沈", "安", "陆"
];
const NAMES = [
    "嬛", "玉娆", "世兰", "如懿", "琅嬅", "晞月", "意欢", "魏璎", "宁玉", 
    "眉庄", "陵容", "沁雅", "若曦", "云婉", "纯悫", "和嘉", "梦华", "念慈"
];
const PERSONALITIES = ["娇纵", "清冷", "温婉", "玲珑", "刚毅", "咸鱼", "孤傲", "淡泊"];
const BACKGROUNDS = [
    { type: "功臣之女", coin: 800, bonus: { prestige: 20, charm: 5 }, desc: "母家功勋卓著，入宫便自带威仪。" },
    { type: "书香门第", coin: 400, bonus: { talent: 20, etiquette: 10 }, desc: "自幼饱读诗书，满身书卷雅气。" },
    { type: "商贾之家", coin: 1500, bonus: { wit: 10 }, desc: "家中虽无官爵，但这金银打点却是最不缺的。" },
    { type: "落第文官", coin: 200, bonus: { health: 15, charm: 10 }, desc: "家境清寒，倒养成了这一副如花笑靥与坚韧体魄。" },
    { type: "异姓王族", coin: 1000, bonus: { prestige: 10, wit: 15 }, desc: "塞外王旗之后，心思深沉莫测。" }
];

// ========== 2. 核心逻辑工具 ==========
function getPlayers() {
    let data = ext.storageGet(DATA_KEY);
    return data ? JSON.parse(data) : {};
}

function savePlayers(p) {
    ext.storageSet(DATA_KEY, JSON.stringify(p));
}

function updateStamina(p) {
    const now = Date.now();
    const passed = now - p.lastRecover;
    if (passed >= RECOVERY_TIME) {
        const intervals = Math.floor(passed / RECOVERY_TIME);
        const gain = intervals * STAMINA_TICK;
        
        if (p.stamina < 100) {
            p.stamina = Math.min(100, p.stamina + gain);
            // 关键：确保lastRecover随着步长移动，但不丢失余数
            p.lastRecover += intervals * RECOVERY_TIME;
        } else {
            // 已满则持续更新时间，防止满体力后第一次操作消耗瞬间又回满
            p.lastRecover = now;
        }
    }
}

// 自动分娩检查与文案生成
function checkPregnancy(p) {
    if (!p || !p.isPregnant) return "";

    const NOW = Date.now();
    const PREG_DURATION = 15 * 60 * 1000; // 设定为15分钟

    if (NOW - p.pregTime >= PREG_DURATION) {
        const gender = Math.random() < 0.5 ? "皇子" : "公主";
        p.children.push({ 
            name: gender, 
            title: "未封", 
            gender: gender, 
            age: 0, 
            growProgress: 0 
        });
        p.isPregnant = false;
        p.pregTime = 0;

        return `\n\n🎊 **【喜报：龙裔降生】**\n“恭喜小主！永和宫传出喜讯，您平安诞下一位【${gender}】。圣上闻讯龙颜大悦，赏赐已在路上了。”`;
    }
    return "";
}

// ========== 3. 指令集实现 ==========

// 【选秀入宫】增强版
const cmd_join = seal.ext.newCmdItemInfo();
cmd_join.name = '选秀入宫';
cmd_join.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    if (players[msg.sender.userId]) return seal.replyToSender(ctx, msg, "🌸 小主已在宫中。");

    // 随机家世与性格
    const bg = BACKGROUNDS[Math.floor(Math.random() * BACKGROUNDS.length)];
    const personality = PERSONALITIES[Math.floor(Math.random() * PERSONALITIES.length)];
    
    // 随机姓名
    const surname = SURNAMES[Math.floor(Math.random() * SURNAMES.length)];
    const firstName = NAMES[Math.floor(Math.random() * NAMES.length)];
    const fullName = surname + "·" + (argv.args[0] || firstName);

    // 初始属性 (基础30 + 家世加成)
    players[msg.sender.userId] = {
        name: fullName,
        level: 0,
        exp: 0,
        stamina: 100,
        coin: bg.coin,
        lastRecover: Date.now(),
        personality: personality,
        background: bg.type,
        charm: 30 + (bg.bonus.charm || 0),
        wit: 30 + (bg.bonus.wit || 0),
        talent: 30 + (bg.bonus.talent || 0),
        health: 80 + (bg.bonus.health || 0),
        etiquette: 10 + (bg.bonus.etiquette || 0),
        prestige: 0 + (bg.bonus.prestige || 0),
        workProgress: { sew: 0, scent: 0, farm: 0 },
        children: [],
        isPregnant: false,
        pregTime: 0
    };

    savePlayers(players);
    
    let reply = `📜 **选秀实录**\n`;
    reply += `“${surname}氏${fullName}，${bg.type}，年十六。”\n`;
    reply += `性格：【${personality}】\n`;
    reply += `出身描述：${bg.desc}\n`;
    reply += `----------------\n`;
    reply += `✨ 留牌子，赐香囊，封为【${LEVELS[0].name}】！\n`;
    reply += `内务府已按家世拨下起家银钱 ${bg.coin} 文。`;
    
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 【宫廷营生】女红/调香/种菜
const cmd_work = seal.ext.newCmdItemInfo();
cmd_work.name = '宫廷营生';
// 【宫廷营生】沉浸式文案修改版
cmd_work.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
    updateStamina(p);

    if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }

    const type = argv.args[0];
    const map = { "女红": "sew", "调香": "scent", "种菜": "farm" };
    const key = map[type];

    if (!key) return seal.replyToSender(ctx, msg, "💡 “小主，内务府目前的差事有：女红、调香、种菜，您想选哪样？”");
    if (p.stamina < 20) return seal.replyToSender(ctx, msg, `🍵 “小主，您这脸色都白了，还是先歇息会儿吧。” (需20体力，当前${Math.floor(p.stamina)})`);

    p.stamina -= 20;
    
    // 进度与品级算法
    let bonus = (type === "女红" ? p.talent : type === "调香" ? p.charm : p.health) * 0.15;
    let gain = Math.floor(Math.random() * 15 + 10 + bonus);
    p.workProgress[key] += gain;

    // 随机互动文案池
    const plots = {
        "女红": [
            `🧵 暖阁内，你正低头绣着一副云缎锦屏，指尖飞针走线，绣出的花瓣栩栩如生。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🧵 窗外鸟鸣啁啾，你正细心地分拣五色丝线，为太后寿礼赶制祥云纹披风。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🧵 月影摇曳，你借着烛火勾勒衣襟上的暗纹，虽然辛苦，眼见这针脚却愈发细密了。 (进度+${gain}%，当前${p.workProgress[key]}%)`
        ],
        "调香": [
            `🏺 你在案前轻研香墨，将檀香、鹅梨与百花露按古法调配，室中异香扑鼻。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🏺 避暑避寒，你正忙着将新采的落梅烘干入药，试图调制出那款千金难求的“冷香丸”。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🏺 捣药杵声沉沉，你细心地去除香料中的杂质，只为这一缕清幽的帐中香。 (进度+${gain}%，当前${p.workProgress[key]}%)`
        ],
        "种菜": [
            `🍃 你挽起袖子，在寝宫后院的小园子里翻土除草，泥土的清香让你心情大好。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🍃 细雨如酥，你提着木桶为那几株青嫩的小青菜浇水，看着它们破土而出。 (进度+${gain}%，当前${p.workProgress[key]}%)`,
            `🍃 阳光明媚，你正蹲在田垄旁仔细观察辣椒的长势，忙碌间额间沁出一层细汗。 (进度+${gain}%，当前${p.workProgress[key]}%)`
        ]
    };

    let res = plots[type][Math.floor(Math.random() * plots[type].length)];

    // 满100结算：引入随机品级文案
    if (p.workProgress[key] >= 100) {
        p.workProgress[key] = 0;
        const qualities = ["【寻常】", "【精巧】", "【上品】", "【御供】", "【传世】"];
        const qIdx = Math.floor(Math.random() * qualities.length);
        const earn = Math.floor(150 + (qIdx * 60) + (Math.random() * 50));
        const prestigeGain = 10 + qIdx * 5;
        
        p.coin += earn; 
        p.prestige += prestigeGain;

        const itemNames = { "女红": "苏绣披风", "调香": "百合冷香", "种菜": "时令鲜蔬" };
        res += `\n\n✨ **大功告成！**\n你耗费心力做出的${qualities[qIdx]}${itemNames[type]}被内务府嬷嬷一眼相中，折合银钱 **${earn}文** 入库，声望提升了 **${prestigeGain}点**。`;
    }

    savePlayers(players);
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};

// 【日常修习】礼仪/心计
const cmd_study = seal.ext.newCmdItemInfo();
cmd_study.name = '日常修习';
cmd_study.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
    updateStamina(p);
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    const type = argv.args[0];
    if (p.stamina < 15) return seal.replyToSender(ctx, msg, "体力不足。");
    p.stamina -= 15;
    if (type === "礼仪") { p.etiquette += 5; seal.replyToSender(ctx, msg, "🦒 学习规矩，礼仪提升。"); }
    else if (type === "心计") { p.wit += 5; seal.replyToSender(ctx, msg, "♟️ 钻研权谋，心计提升。"); }
    else { seal.replyToSender(ctx, msg, ".日常修习 <礼仪/心计>"); return; }
    savePlayers(players);
    return seal.ext.newCmdExecuteResult(true);
};

// 【请求侍寝】需打点费
const cmd_sleep = seal.ext.newCmdItemInfo();
cmd_sleep.name = '请求侍寝';
cmd_sleep.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }

    // 1. 物理拦截：怀孕期间不能侍寝
    if (p.isPregnant) {
        return seal.replyToSender(ctx, msg, "🤰 “小主，您如今身怀六甲，圣上特许您在寝宫安胎，不宜操劳承宠。”");
    }

    if (p.coin < 150 || p.stamina < 40) return seal.replyToSender(ctx, msg, "银钱(150)或体力(40)不足。");
    
    updateStamina(p);
    p.coin -= 150; 
    p.stamina -= 40;

    let chance = (p.charm / 1000) + 0.2;
    if (Math.random() < chance) {
        p.exp += 300;
        let res = "🏮 承接圣恩，龙颜大悦，你获得的经验提升了。";
        
        // 2. 逻辑保护：只有未怀孕状态下才可能触发怀孕判定
        if (!p.isPregnant && Math.random() < 0.35) { 
            p.isPregnant = true; 
            p.pregTime = Date.now(); 
            res += "\n✨ 随后御医问诊，发现小主已月余未见红，是有喜了！"; 
        }
        
        savePlayers(players);
        seal.replyToSender(ctx, msg, res);
    } else {
        savePlayers(players);
        seal.replyToSender(ctx, msg, "🌙 皇上今晚翻了别人的牌子。");
    }
    return seal.ext.newCmdExecuteResult(true);
};

// 【子嗣管理】培养长大与封号
const cmd_child = seal.ext.newCmdItemInfo();
cmd_child.name = '子嗣管理';
cmd_child.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    if (p.isPregnant && Date.now() - p.pregTime > 15 * 60 * 1000) {
        const gender = Math.random() < 0.5 ? "皇子" : "公主";
        p.children.push({ name: gender, title: "未封", gender, age: 0, growProgress: 0 });
        p.isPregnant = false; savePlayers(players);
        return seal.replyToSender(ctx, msg, `👶 诞下一名【${gender}】！可开始【培养】。`);
    }
    const sub = argv.args[0];
    if (sub === "培养") {
        const idx = parseInt(argv.args[1]);
        if (isNaN(idx) || !p.children[idx] || p.stamina < 25) return seal.replyToSender(ctx, msg, "指序号并需25体力。");
        p.stamina -= 25;
        let c = p.children[idx];
        let gain = Math.floor(Math.random() * 20 + 10 + p.talent * 0.1);
        c.growProgress += gain;
        if (c.growProgress >= 100) { c.growProgress = 0; c.age += 1; }
        savePlayers(players);
        seal.replyToSender(ctx, msg, `📖 教导中...进度+${gain}%，当前${c.age}岁。`);
    } else if (sub === "赐封号") {
        const idx = parseInt(argv.args[1]); const title = argv.args[2];
        if (p.children[idx] && title) { p.children[idx].title = title; savePlayers(players); seal.replyToSender(ctx, msg, `✨ 册封为：${title}${p.children[idx].gender}。`); }
    } else {
        let list = `👶 子嗣：\n`;
        p.children.forEach((c, i) => list += `${i}. [${c.title}]${c.gender} ${c.age}岁\n`);
        seal.replyToSender(ctx, msg, list || "无子嗣。");
    }
    return seal.ext.newCmdExecuteResult(true);
};

// 【请求晋升】手动Check
const cmd_promote = seal.ext.newCmdItemInfo();
cmd_promote.name = '请求晋升';
cmd_promote.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    const next = LEVELS[p.level + 1];
    if (!next) return seal.replyToSender(ctx, msg, "👑 已是巅峰。");
    let fails = [];
    if (p.exp < next.reqExp) fails.push(`经验不足`);
    if (p.children.length < next.reqChild) fails.push(`子嗣不足`);
    const maxAge = p.children.reduce((max, c) => Math.max(max, c.age), 0);
    if (maxAge < next.reqAge) fails.push(`孩子岁数不足(需${next.reqAge}岁)`);
    for (let a in next.reqAttr) if (p[a] < next.reqAttr[a]) fails.push(`属性[${a}]不足`);

    if (fails.length > 0) seal.replyToSender(ctx, msg, `❌ 条件不符：\n- ` + fails.join("\n- "));
    else { p.level++; p.coin += 1000; savePlayers(players); seal.replyToSender(ctx, msg, `🎉 晋升为【${LEVELS[p.level].name}】！`); }
    return seal.ext.newCmdExecuteResult(true);
};

// 【查看寝宫】状态查询
const cmd_status = seal.ext.newCmdItemInfo();
cmd_status.name = '查看寝宫';
cmd_status.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    updateStamina(p);

    // 关系排序逻辑
    let rels = [];
    for (let id in (p.relations || {})) {
        if (players[id]) rels.push({ name: players[id].name, val: p.relations[id] });
    }
    rels.sort((a, b) => b.val - a.val);
    let top3 = rels.slice(0, 3).map(r => `${r.name}(${r.val})`).join(", ") || "暂无";
    let bot3 = rels.slice(-3).reverse().map(r => `${r.name}(${r.val})`).join(", ") || "暂无";

    let txt = `🏮 【${p.name}】`;
    if (p.isDeposed) txt += ` | ❄️ 冷宫罪妃`;
    else txt += ` | ${LEVELS[p.level].name}`;
    txt += `⚡ 体力: ${Math.floor(p.stamina)} | 💰 银钱: ${p.coin}\n`;
    txt += `📈 经验: ${p.exp} | ⚖️ 声望: ${p.prestige}\n`;
    txt += `🎭 容貌: ${p.charm} | 🧠 心计: ${p.wit}\n`;
    txt += `----------------\n`;
    txt += `❤️ 莫逆之交：${top3}\n`;
    txt += `💔 势不两立：${bot3}`;
    
    seal.replyToSender(ctx, msg, txt);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_garden = seal.ext.newCmdItemInfo();
cmd_garden.name = '御花园散步';
cmd_garden.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p || p.stamina < 15) return seal.replyToSender(ctx, msg, "体力不足(15)。");
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    
    updateStamina(p);
    p.stamina -= 15;
    if (!p.relations) p.relations = {};

    // 获取除自己以外的其他玩家ID
    let otherIds = Object.keys(players).filter(id => id !== msg.sender.userId);
    let randomOtherId = otherIds[Math.floor(Math.random() * otherIds.length)];
    let target = randomOtherId ? players[randomOtherId] : null;
    if (!p.relations) p.relations = {};
    if (!target.relations) target.relations = {};

    // 基础环境事件池
    let events = [
        { d: "偶遇圣上，你随口吟诵的一句诗词深得龙心。", r: () => { p.exp += 200; return "经验+200"; } },
        { d: "你在绛雪轩捡到一支成色极好的金钗。", r: () => { p.coin += 300; return "银钱+300"; } },
        { d: "撞见两位妃嫔在假山后密谈，你听到了不得了的秘密。", r: () => { p.wit += 10; return "心计+10"; } },
        { d: "不慎在石子路上扭了脚，惊动了御医。", r: () => { p.health -= 5; return "体质-5"; } },
        { d: "你在浮翠阁前拾得一方丝帕，上面绣着鸳鸯戏水。", r: () => { p.talent += 5; return "才华+5"; } },
        { d: "你在太液池边喂鱼，看着鱼儿争食，心境开阔了许多。", r: () => { p.stamina += 20; return "体力+20"; } }
    ];

    // 如果有其他玩家，加入交互事件
    if (target) {
        events.push(
            { 
                d: `你在转角处遇见了【${target.name}】，对方正带着宫女赏花。`, 
                r: () => { 
                    let change = Math.floor(Math.random() * 20 + 10);
                    p.relations[randomOtherId] = (p.relations[randomOtherId] || 0) + change;
                    return `与 ${target.name} 寒暄了一阵，友好值 +${change}`;
                } 
            },
            { 
                d: `你远远瞧见【${target.name}】在御花园假山后焚香告天，似乎在诅咒什么。`, 
                r: () => { 
                    let change = Math.floor(Math.random() * 20 + 10);
                    p.relations[randomOtherId] = (p.relations[randomOtherId] || 0) - change;
                    return `你心生厌恶，与 ${target.name} 的友好值 -${change}`;
                } 
            },
            { 
                d: `你在亭子里偶遇【${target.name}】，两人一见如故，共叙姐妹情谊。`, 
                r: () => { 
                    p.relations[randomOtherId] = (p.relations[randomOtherId] || 0) + 30;
                    p.exp += 50;
                    return `与 ${target.name} 义结金兰，友好值 +30，经验+50`;
                } 
            }
        );
    }
    
    const ev = events[Math.floor(Math.random() * events.length)];
    let res = `🌳 【御花园】\n${ev.d}\n✨ 效果：${ev.r()}`;
    
    savePlayers(players);
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_fight = seal.ext.newCmdItemInfo();
cmd_fight.name = '宫斗';
cmd_fight.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    let targetId = argv.args[0]; // 需输入目标QQ
    let type = argv.args[1];   // 掌掴 或 投毒

    if (!p || !players[targetId] || targetId === msg.sender.userId) {
        return seal.replyToSender(ctx, msg, "💡 “小主，宫斗需得有个目标，总不能跟自己过不去。”\n用法：.宫斗 <目标QQ> <掌掴/投毒>");
    }
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    
    updateStamina(p);
    if (p.stamina < 50) return seal.replyToSender(ctx, msg, "🍵 “小主，您现在身子虚弱，恐怕拿不稳这药瓶，也挥不动那巴掌。” (需50体力)");

    p.stamina -= 50;
    let target = players[targetId];
    
    // 初始化关系对象（防止旧数据报错）
    if (!p.relations) p.relations = {};
    if (!target.relations) target.relations = {};

    // 无论胜负，关系值必定大幅下降
    let relationDrop = Math.floor(Math.random() * 50 + 50); // 随机降低 50-100 点
    p.relations[targetId] = (p.relations[targetId] || 0) - relationDrop;
    target.relations[msg.sender.userId] = (target.relations[msg.sender.userId] || 0) - relationDrop;

    // 判定逻辑：心计压制
    let success = p.wit > target.wit * 0.8; 
    let res = `⚔️ **【宫斗：${type}】**\n`;

    if (type === "掌掴") {
        if (success) {
            target.prestige -= 25; 
            p.prestige += 15;
            res += `💢 你在众目睽睽之下截住了${target.name}，抬手便是一记响亮的耳光。对方捂着脸眼中满是怨恨，名望大损！`;
        } else {
            p.prestige -= 40;
            p.health -= 5;
            res += `❌ 你试图掌掴${target.name}，不料对方早有防备，反被其推搡在地，落了个“御前失仪”的笑话，名望与体质受损。`;
        }
    } else if (type === "投毒") {
        if (success) {
            target.health -= 30; 
            p.wit += 20;
            res += `🐍 你的手脚极干净，${target.name}饮下那盏燕窝后便卧床不起，御医也查不出病因。对方体质大跌！`;
        } else {
            p.wit -= 30; 
            p.health -= 15;
            res += `💀 投毒之事竟被抓个正着！你被迫在皇后面前自食恶果，不仅心计受损，身体也落下了病根。`;
        }
    } else {
        return seal.replyToSender(ctx, msg, "💡 请选择手段：掌掴 或 投毒");
    }

    res += `\n💔 **后果**：你与 ${target.name} 的友好值下降了 ${relationDrop} 点，已是水火不容。`;
    if (p.prestige < -200 || p.health < 10) {
        p.isDeposed = true;
        res += `\n\n📢 **【废黜圣旨】**\n“${p.name} 行迹卑劣，不堪教化，着即废去位分，贬入冷宫，永不启用！”`;
    }
    
    savePlayers(players);
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_shop = seal.ext.newCmdItemInfo();
cmd_shop.name = '内务府置办';
cmd_shop.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    let itemName = argv.args[0];
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }
    
    if (!itemName || !SHOP_ITEMS[itemName]) {
        let list = "🛍️ 【内务府清单】\n";
        for (let k in SHOP_ITEMS) list += `- ${k}: ${SHOP_ITEMS[k].price}文 (${SHOP_ITEMS[k].desc})\n`;
        return seal.replyToSender(ctx, msg, list);
    }
    
    let item = SHOP_ITEMS[itemName];
    if (p.coin < item.price) return seal.replyToSender(ctx, msg, "银钱不足。");
    
    p.coin -= item.price;
    p[item.attr] += item.value;
    
    savePlayers(players);
    seal.replyToSender(ctx, msg, `✨ 置办成功！${itemName}已入库，你的${item.attr}提升了${item.value}点。`);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_interact = seal.ext.newCmdItemInfo();
cmd_interact.name = '宫廷交际';
cmd_interact.help = "用法：.宫廷交际 <目标QQ> <送礼/构陷>";
cmd_interact.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    let targetId = argv.args[0];
    let action = argv.args[1];
        if (p.isDeposed) {
        return seal.replyToSender(ctx, msg, "❄️ “这里是冷宫，小主还是省省力气吧。想要出去，得先在【浣衣局】刷洗够了再说。”");
    }

    if (!p || !players[targetId] || targetId === msg.sender.userId) return;
    if (!p.relations) p.relations = {};
    updateStamina(p);

    if (action === "送礼") {
        if (p.coin < 300) return seal.replyToSender(ctx, msg, "囊中羞涩，拿不出像样的礼物（需300文）。");
        p.coin -= 300;
        p.relations[targetId] = (p.relations[targetId] || 0) + 50;
        seal.replyToSender(ctx, msg, `🎁 你遣人送了一对赤金步摇给【${players[targetId].name}】，双方友好值增加 50。`);
    } else if (action === "构陷") {
        if (p.stamina < 40) return seal.replyToSender(ctx, msg, "心力交瘁，无力布局（需40体力）。");
        p.stamina -= 40;
        let success = p.wit > players[targetId].wit * 0.7;
        if (success) {
            p.relations[targetId] = (p.relations[targetId] || 0) - 60;
            players[targetId].prestige -= 30;
            seal.replyToSender(ctx, msg, `🐍 你在内务府散布流言，【${players[targetId].name}】名望大损，友好值降低 60。`);
        } else {
            p.relations[targetId] = (p.relations[targetId] || 0) - 30;
            p.prestige -= 20;
            seal.replyToSender(ctx, msg, `💀 你的构陷被【${players[targetId].name}】识破，反被扣上搬弄是非之名，名望受损。`);
        }
    }
    
    savePlayers(players);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_cold_palace = seal.ext.newCmdItemInfo();
cmd_cold_palace.name = '浣衣局';
cmd_cold_palace.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    if (!p) return;
    if (!p.isDeposed) return seal.replyToSender(ctx, msg, "贵人们才不来这腌臜地方。");

    updateStamina(p);
    if (p.stamina < 30) return seal.replyToSender(ctx, msg, "你连木盆都端不动了...（需30体力）");

    p.stamina -= 30;
    let gain = Math.floor(Math.random() * 10 + 5);
    p.prestige += gain;
    p.health -= 5; // 做苦役扣体质

    let res = `🧺 你在浣衣局刷洗了整整一日的宫服，手都被冻裂了。名望+${gain}，体质-5。`;

    // 翻身判定
    if (p.prestige >= 0) {
        p.isDeposed = false;
        p.level = 0; // 回宫后降为最低级：官女子
        res += `\n\n✨ **【重见天日】**\n皇上念你悔过之心诚恳，特赦你出冷宫。虽只是个官女子，但总算是回来了。`;
    }

    savePlayers(players);
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};

const cmd_mock = seal.ext.newCmdItemInfo();
cmd_mock.name = '冷宫探视';
cmd_mock.solve = function(ctx, msg, argv) {
    let players = getPlayers();
    let p = players[msg.sender.userId];
    let targetId = argv.args[0];
    let target = players[targetId];

    if (!target || !target.isDeposed) return seal.replyToSender(ctx, msg, "对方不在冷宫。");
    
    // 羞辱逻辑：如果对方是你的仇人（关系为负）
    if (p.relations && p.relations[targetId] < 0) {
        target.health -= 10;
        p.prestige += 5;
        seal.replyToSender(ctx, msg, `😏 你去冷宫羞辱了【${target.name}】一番，看着她落魄的样子，你心情大好。对方体质-10。`);
    } else {
        target.health += 10;
        p.relations[targetId] = (p.relations[targetId] || 0) + 20;
        seal.replyToSender(ctx, msg, `🥖 你念在旧情，偷偷给冷宫里的【${target.name}】送了些干粮。对方友好值+20。`);
    }
    
    savePlayers(players);
    return seal.ext.newCmdExecuteResult(true);
};

// ========== 4. 指令注册 (补全) ==========
ext.cmdMap['选秀入宫'] = cmd_join;
ext.cmdMap['宫廷营生'] = cmd_work;
ext.cmdMap['日常修习'] = cmd_study;
ext.cmdMap['请求侍寝'] = cmd_sleep;
ext.cmdMap['子嗣管理'] = cmd_child;
ext.cmdMap['请求晋升'] = cmd_promote;
ext.cmdMap['查看寝宫'] = cmd_status;
ext.cmdMap['御花园散步'] = cmd_garden;
ext.cmdMap['宫斗'] = cmd_fight;
ext.cmdMap['内务府置办'] = cmd_shop;
ext.cmdMap['宫廷交际'] = cmd_interact;
ext.cmdMap['浣衣局'] = cmd_cold_palace;
ext.cmdMap['冷宫探视'] = cmd_mock;