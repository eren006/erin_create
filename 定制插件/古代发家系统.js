// ==UserScript==
// @name         古代发家系统
// @author       长日将尽
// @version      2.0.0
// @description  种地偷菜、科举入仕、开铺经商、争抢佳人——一部属于你的种田发家文
// @timestamp    1748563200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

// ========================
// 初始化
// ========================

let ext = seal.ext.find("ancient_farm_v2");
if (!ext) {
    ext = seal.ext.new("ancient_farm_v2", "长日将尽", "2.0.0");
    seal.ext.registerIntConfig(ext, "打猎冷却_分钟", 120);
    seal.ext.registerIntConfig(ext, "偷菜冷却_分钟", 30);
    seal.ext.registerIntConfig(ext, "科举冷却_小时", 4);
    seal.ext.registerIntConfig(ext, "收租间隔_小时", 8);
    seal.ext.register(ext);
}

// ========================
// 数据存取
// ========================

function getData() {
    try { return JSON.parse(ext.storageGet("farm_data") || "{}"); }
    catch { return {}; }
}
function saveData(d) { ext.storageSet("farm_data", JSON.stringify(d)); }

function getAttrData(gid) {
    try { return JSON.parse(ext.storageGet(`attr_${gid}`) || "{}"); }
    catch { return {}; }
}
function saveAttrData(gid, d) { ext.storageSet(`attr_${gid}`, JSON.stringify(d)); }

function pk(ctx) { return `${ctx.group.groupId}|${ctx.player.userId}`; }
function now() { return Date.now(); }

// ========================
// 格式化
// ========================

function fmtMs(ms) {
    if (ms <= 0) return "不到1分钟";
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return m > 0 ? `${h}小时${m}分` : `${h}小时`;
    return `${m}分`;
}

function fmtCoins(n) {
    n = Math.floor(n);
    if (n >= 100) {
        const liang = Math.floor(n / 100);
        const tong = n % 100;
        return tong > 0 ? `${liang}两${tong}铜` : `${liang}两`;
    }
    return `${n}铜`;
}

function rand(min, max) {
    return min + Math.floor(Math.random() * (max - min + 1));
}

function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

// @mention 格式（QQ CQ码）
function atUser(userId) {
    const num = userId.includes(":") ? userId.split(":")[1] : userId;
    return `[CQ:at,qq=${num}]`;
}

// ========================
// 游戏常量
// ========================

const CROPS = {
    "白菜": { seed: "菜种",   seedCost: 5,   growH: 2,  minY: 3, maxY: 6,  minP: 8,   maxP: 15   },
    "萝卜": { seed: "萝卜种", seedCost: 8,   growH: 3,  minY: 2, maxY: 5,  minP: 18,  maxP: 28   },
    "土豆": { seed: "土豆种", seedCost: 15,  growH: 4,  minY: 2, maxY: 4,  minP: 30,  maxP: 45   },
    "草药": { seed: "草药种", seedCost: 40,  growH: 8,  minY: 1, maxY: 3,  minP: 80,  maxP: 130  },
    "人参": { seed: "参苗",   seedCost: 300, growH: 24, minY: 1, maxY: 2,  minP: 600, maxP: 1000 },
};
const SEED_TO_CROP = {};
for (const [crop, info] of Object.entries(CROPS)) SEED_TO_CROP[info.seed] = crop;

const HUNT_TABLE = [
    { weight: 25,  name: null,       desc: ["上山转了一圈，什么也没遇到，悻悻而归",
                                            "深山雾重，只闻鸟鸣，一无所获",
                                            "走了半天山路，怀揣空篓子回了家"] },
    { weight: 22,  name: "野山菌",   desc: ["在松树下发现了一片野山菌！"], min: 1, max: 4, minP: 15, maxP: 28  },
    { weight: 18,  name: "野兔",     desc: ["眼疾手快，套住了一只肥兔子！"],   min: 1, max: 2, minP: 35, maxP: 55  },
    { weight: 13,  name: "野鸡",     desc: ["草丛里扑棱棱飞出一只野鸡，被逮住了！"], min: 1, max: 2, minP: 55, maxP: 80  },
    { weight: 10,  name: "野猪肉",   desc: ["遭遇一头野猪！血战之后，猎人笑到了最后！"], min: 2, max: 5, minP: 45, maxP: 70  },
    { weight: 6,   name: "灵芝",     desc: ["悬崖边的老松下，赫然生着一朵灵芝！！"], min: 1, max: 1, minP: 250, maxP: 450 },
    { weight: 4,   name: "梅花鹿",   desc: ["溪边饮水的梅花鹿，美丽又值钱！！"],   min: 1, max: 1, minP: 180, maxP: 300 },
    { weight: 1.5, name: "何首乌",   desc: ["古树盘根处，挖出了传说中的百年何首乌！！！"], min: 1, max: 1, minP: 500, maxP: 900 },
    { weight: 0.5, name: "百年山参", desc: ["【天降奇遇！！！】云雾散处，一株百年山参就在眼前——"], min: 1, max: 1, minP: 1500, maxP: 3000 },
];

const LAND_COSTS = [500, 2000, 8000, 30000, 100000];

// 功名体系
const FAME_LEVELS = [
    { title: "白身",   examCost: 500,   examRate: 0.60, examCd: 4  },
    { title: "秀才",   examCost: 2000,  examRate: 0.40, examCd: 6  },
    { title: "举人",   examCost: 10000, examRate: 0.25, examCd: 12 },
    { title: "进士",   examCost: 50000, examRate: 0.10, examCd: 24 },
    { title: "状元",   examCost: 0,     examRate: 0,    examCd: 0  }, // 最高
];

// 铺子体系（需对应功名才能开）
const SHOPS = {
    "小铺子": { requiredFame: 1, cost: 1000,   minIncome: 50,   maxIncome: 100  },
    "酒楼":   { requiredFame: 2, cost: 8000,   minIncome: 200,  maxIncome: 400  },
    "商行":   { requiredFame: 3, cost: 50000,  minIncome: 800,  maxIncome: 1600 },
    "钱庄":   { requiredFame: 4, cost: 200000, minIncome: 3000, maxIncome: 6000 },
};

// 身份（按铜钱）
const IDENTITIES = [
    { name: "穷苦流民",  threshold: 0       },
    { name: "普通村民",  threshold: 200     },
    { name: "小农",      threshold: 1000    },
    { name: "富农",      threshold: 5000    },
    { name: "小商人",    threshold: 20000   },
    { name: "大商人",    threshold: 100000  },
    { name: "富甲乡里",  threshold: 500000  },
    { name: "大富豪",    threshold: 2000000 },
];

function getIdentity(coins) {
    let id = IDENTITIES[0];
    for (const i of IDENTITIES) { if (coins >= i.threshold) id = i; else break; }
    return id;
}

// 美男美女花名册（50人）
const CHAR_LIST = [
    // 美男 25人 [名字, 价格, 描述]
    ["云逸",   500,  "寒门书生，清冽眼神，字字诗书，偏生心存傲骨"],
    ["墨寒",   600,  "江湖杀手，冷面冷心，却只在你面前低下了眉眼"],
    ["季白",   550,  "浪迹天涯的游侠，轻功绝顶，笑起来无拘无束"],
    ["沈昀",   700,  "太子侍读，温润如玉，一双手只会拿笔和拿剑"],
    ["裴珩",   650,  "将军之子，英武不凡，护短到了骨子里"],
    ["叶临风", 800,  "药谷门主，医术通神，性情淡漠却妙手仁心"],
    ["顾长宁", 900,  "京城第一美男子，世家出身，偏偏最厌富贵浮华"],
    ["陆辞",   750,  "本届探花郎，才高八斗，笑起来有两个梨涡"],
    ["傅深",   850,  "皇商世家，手段狠辣，对外人冷淡，唯独对你温柔"],
    ["祁景",   700,  "边关守将，三十年未娶，铁汉柔情藏得极深"],
    ["夏侯临", 500,  "宗室旁支，天生神力，憨厚可爱到让人捏脸"],
    ["容绪",   600,  "茶馆说书人，天下秘事都在他嘴里，从不轻易泄露"],
    ["周晋",   550,  "捕快头领，断案如神，见不得任何人受委屈"],
    ["苏慕",   650,  "落魄世子，清贫却风骨傲然，宁折不弯"],
    ["明珩",   900,  "国师之徒，身负异术，生死看淡，唯你一人例外"],
    ["贺云亭", 700,  "御前侍卫，忠义两全，话不多，但说出口字字算数"],
    ["晏九",   800,  "江湖盟主，三分醉意七分清醒，总在最关键时刻出现"],
    ["程锦",   550,  "绸缎商人，儒雅随和，最善经营，笑起来让人安心"],
    ["薛行",   600,  "钦天监副监，会推算命数，自称命硬，不信鬼神"],
    ["庄澜",   700,  "水军都督，在海上长大，不惧风浪，眼里有星辰大海"],
    ["石泽",   450,  "铁匠之子，粗犷憨实，打出的剑天下一绝，人也实在"],
    ["卫临",   750,  "太医院院判，救死扶伤，冷静如水，手若春风"],
    ["崔远",   600,  "藏书楼主，博闻强记，最喜欢分享，从不藏私"],
    ["阮江",   500,  "茶馆伙计，笑容暖如朝阳，谁来了都是座上宾"],
    ["林凌",   550,  "前任捕快，归隐后只想种地，却总被江湖找上门"],
    // 美女 25人
    ["苏锦年", 600,  "将门之女，上马能打仗，下马能绣花，两样都绝"],
    ["白鹭",   550,  "江湖女侠，剑法凌厉，性子不拘，最看不惯伪君子"],
    ["霍晴川", 700,  "名门闺秀，才情出众，心思细腻，笑里藏着万千心事"],
    ["凤瑶",   850,  "异域公主，性格烈如骄阳，认定的事九头牛也拉不回"],
    ["谢明月", 800,  "太师之女，温婉贤淑，藏着一腔不让须眉的抱负"],
    ["沈素素", 500,  "村姑出身，厨艺绝佳，悟性极高，笑起来眼睛弯弯"],
    ["孟青竹", 650,  "道观小道姑，超凡脱俗，心清如水，偶尔说出惊天之语"],
    ["李春花", 700,  "繁花楼头牌，歌舞无双，心中早有归处，等一个有缘人"],
    ["崔颜",   750,  "翰林千金，博览群书，擅长辩论，输了也不肯认"],
    ["宋佳期", 800,  "商贾之女，精于算术，眼光毒辣，从不做亏本买卖"],
    ["顾婵娟", 600,  "织锦坊主，手艺天下一绝，性子温和，做事极有章法"],
    ["云梦",   700,  "宫中御厨，做的每道菜都是极品，脾气比厨艺更香"],
    ["华锦",   500,  "布衣百姓，勤劳善良，内心比任何人都要强大"],
    ["秦暮雪", 650,  "女捕快，胆大心细，武艺高强，连大老爷都让她三分"],
    ["周婉如", 600,  "大儒孙女，知书达理，待人宽厚，从不争抢却处处受人敬"],
    ["乔盈盈", 450,  "养猪姑娘，豪爽可爱，力气出奇大，笑声传三里"],
    ["陆瑶",   850,  "前朝公主遗孤，隐于市井，心有大志，等待时机"],
    ["沈云裳", 700,  "绣娘出身，后成宫廷画师，最爱大红色，画里藏着故事"],
    ["司马婵", 750,  "商行账房，天生算账奇才，一双眼睛什么都逃不过"],
    ["赵小鱼", 550,  "渔家女儿，爽朗自在，最懂看天象，说话直来直去"],
    ["柳如是", 800,  "才女，诗画双绝，最恨虚伪，朋友不多但个个掏心"],
    ["夏初",   650,  "桃园女主人，酿得一手好酒，喝醉了才说真心话"],
    ["江琴",   700,  "云游郎中，医术精湛，走遍千山万水，见过许多生死"],
    ["聂小倩", 750,  "书院山长，管理严格，内心却有最柔软的一块地方"],
    ["霓裳",   900,  "舞姬出身，身世成谜，一舞倾城，只肯为懂她的人跳"],
];

function rollHunt() {
    const total = HUNT_TABLE.reduce((s, h) => s + h.weight, 0);
    let r = Math.random() * total;
    for (const h of HUNT_TABLE) { r -= h.weight; if (r <= 0) return h; }
    return HUNT_TABLE[0];
}

// ========================
// 端点缓存（用于定时通知）
// ========================

const epCache = new Map(); // "platform:botId:groupId" -> endPoint

function cacheEp(ctx) {
    if (!ctx.endPoint || !ctx.group) return;
    const key = `${ctx.endPoint.platform}:${ctx.endPoint.userId}:${ctx.group.groupId}`;
    epCache.set(key, ctx.endPoint);
}

// ========================
// 定时检查：庄稼成熟提醒
// ========================

try {
    setInterval(() => {
        const data = getData();
        const nowMs = Date.now();
        let changed = false;

        for (const [key, player] of Object.entries(data)) {
            if (!player || !player.plots || !player.groupId || !player.userId) continue;

            const readyNew = player.plots.filter(p => p && !p.notified && p.readyAt <= nowMs);
            if (readyNew.length === 0) continue;

            const epKey = `${player.epPlatform}:${player.epBotId}:${player.groupId}`;
            const ep = epCache.get(epKey);
            if (!ep) continue;

            const cropList = readyNew.map(p => `【${p.crop}】`).join("、");
            const notifyMsg = seal.newMessage();
            notifyMsg.messageType = "group";
            notifyMsg.groupId = player.groupId;
            const tempCtx = seal.createTempCtx(ep, notifyMsg);
            seal.replyToSender(tempCtx, notifyMsg,
                `${atUser(player.userId)} 主人！${cropList}已经成熟，快去【收地】吧！`
            );

            for (const p of player.plots) {
                if (p && !p.notified && p.readyAt <= nowMs) p.notified = true;
            }
            changed = true;
        }

        if (changed) saveData(data);
    }, 120000);
} catch (e) {
    console.error("[发家系统] 定时器初始化失败:", e.message);
}

// ========================
// 工具：保存玩家端点信息
// ========================

function ensurePlayer(ctx) {
    cacheEp(ctx);
    const data = getData();
    const key = pk(ctx);
    if (data[key]) {
        // 更新端点信息
        data[key].epPlatform = ctx.endPoint ? ctx.endPoint.platform : "";
        data[key].epBotId = ctx.endPoint ? ctx.endPoint.userId : "";
        data[key].groupId = ctx.group ? ctx.group.groupId : "";
        data[key].userId = ctx.player.userId;
        data[key].userName = ctx.player.name;
        saveData(data);
    }
    return data;
}

// ========================
// .立业 — 初始化
// ========================

let cmd立业 = seal.ext.newCmdItemInfo();
cmd立业.name = "立业";
cmd立业.help = "开始你的发家传奇。用法：.立业";
cmd立业.solve = (ctx, msg, cmdArgs) => {
    cacheEp(ctx);
    const data = getData();
    const key = pk(ctx);

    if (data[key]) {
        const p = data[key];
        const id = getIdentity(p.coins);
        const ft = FAME_LEVELS[p.fame || 0].title;
        seal.replyToSender(ctx, msg,
            `${ctx.player.name} 早已在此扎根，无需重建。\n当前身份：${id.name}（${ft}）| 身家：${fmtCoins(p.coins)}`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    data[key] = {
        coins: 50, plots: [null, null], huntCd: 0, stealCd: 0,
        examCd: 0, fame: 0, shops: {}, shopCd: 0,
        bag: { "菜种": 3 },
        epPlatform: ctx.endPoint ? ctx.endPoint.platform : "",
        epBotId: ctx.endPoint ? ctx.endPoint.userId : "",
        groupId: ctx.group ? ctx.group.groupId : "",
        userId: ctx.player.userId, userName: ctx.player.name,
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `📖 【序章】\n` +
        `${ctx.player.name}拍了拍空瘪的钱袋，看了看脚下这两亩薄田，长出一口气——\n` +
        `"总得从哪里开始。"\n\n` +
        `初始家当：50铜 · 田地×2 · 菜种×3\n` +
        `庄稼成熟时机器人会@提醒你！\n` +
        `————\n` +
        `【种 白菜】播种 | 【收地】收获\n` +
        `【上山】打猎采药 | 【集市】买卖\n` +
        `【科举】参加考试晋升功名\n` +
        `【发家帮助】查看全部指令`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["立业"] = cmd立业;

// ========================
// .种 — 播种
// ========================

let cmd种 = seal.ext.newCmdItemInfo();
cmd种.name = "种";
cmd种.help = "在空地播种。用法：.种 白菜";
cmd种.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const cropName = cmdArgs.getArgN(1);
    if (!cropName) {
        const list = Object.entries(CROPS).map(([c, i]) => `${c}(${i.growH}h)`).join("、");
        seal.replyToSender(ctx, msg, `可种：${list}\n用法：.种 白菜`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const crop = CROPS[cropName];
    if (!crop) {
        seal.replyToSender(ctx, msg, `不认识"${cropName}"！可种：${Object.keys(CROPS).join("、")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const p = data[key];
    const emptyIdx = p.plots.findIndex(pl => pl === null);
    if (emptyIdx === -1) {
        seal.replyToSender(ctx, msg, "田地全满，先【收地】腾空，或【扩地】购新田！");
        return seal.ext.newCmdExecuteResult(true);
    }

    const seedCount = p.bag[crop.seed] || 0;
    if (seedCount <= 0) {
        seal.replyToSender(ctx, msg,
            `没有【${crop.seed}】了，去集市购买（${fmtCoins(crop.seedCost)}/个）。\n用法：.买 ${crop.seed} 5`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    p.bag[crop.seed] = seedCount - 1;
    if (p.bag[crop.seed] === 0) delete p.bag[crop.seed];

    const readyAt = now() + crop.growH * 3600000;
    p.plots[emptyIdx] = { crop: cropName, plantedAt: now(), readyAt, notified: false };
    saveData(data);

    const flavor = [
        `弯腰将种子埋入泥土，轻轻拍实，心里盘算着收获时的情景。`,
        `手沾泥土的瞬间，有种说不出的踏实。`,
        `种下去的是种子，也是对未来的盼头。`,
    ];
    seal.replyToSender(ctx, msg,
        `🌱 第 ${emptyIdx + 1} 块地种下了【${cropName}】\n` +
        `${pick(flavor)}\n` +
        `⏳ 约 ${fmtMs(crop.growH * 3600000)} 后成熟，成熟时会@提醒你！`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["种"] = cmd种;
ext.cmdMap["种地"] = cmd种;

// ========================
// .收地 — 收获
// ========================

let cmd收地 = seal.ext.newCmdItemInfo();
cmd收地.name = "收地";
cmd收地.help = "收获所有成熟的作物。用法：.收地";
cmd收地.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const harvested = [];
    let unready = 0;

    for (let i = 0; i < p.plots.length; i++) {
        const plot = p.plots[i];
        if (!plot) continue;
        if (plot.readyAt - now() > 0) { unready++; continue; }
        const crop = CROPS[plot.crop];
        const count = rand(crop.minY, crop.maxY);
        p.bag[plot.crop] = (p.bag[plot.crop] || 0) + count;
        harvested.push({ name: plot.crop, count });
        p.plots[i] = null;
    }
    saveData(data);

    if (harvested.length === 0 && unready === 0) {
        seal.replyToSender(ctx, msg, "田地是空的，先用【种】种点什么！");
    } else if (harvested.length === 0) {
        seal.replyToSender(ctx, msg, `${unready} 块地还没成熟，再等等！用【田地】查看进度。`);
    } else {
        const list = harvested.map(h => `【${h.name}】×${h.count}`).join("、");
        const flavor = [
            "阳光正好，一筐一筐装进背篓，满满当当。",
            "看着收进仓的东西，心里头那点愁也散了。",
            "擦了把汗，嘴角不自觉地往上扬。",
        ];
        let reply = `🌾 ${ctx.player.name} 收获：${list}\n${pick(flavor)}`;
        if (unready > 0) reply += `\n（另有 ${unready} 块地仍在生长）`;
        reply += `\n去集市出售：.卖 白菜 全部`;
        seal.replyToSender(ctx, msg, reply);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["收地"] = cmd收地;
ext.cmdMap["收"] = cmd收地;

// ========================
// .田地 — 查看农田
// ========================

let cmd田地 = seal.ext.newCmdItemInfo();
cmd田地.name = "田地";
cmd田地.help = "查看田地状态。用法：.田地";
cmd田地.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const lines = p.plots.map((plot, i) => {
        if (!plot) return `第${i + 1}块：【空地】`;
        const left = plot.readyAt - now();
        if (left <= 0) return `第${i + 1}块：【${plot.crop}】✅ 已成熟！`;
        const pct = Math.floor((1 - left / (CROPS[plot.crop].growH * 3600000)) * 100);
        const bar = "█".repeat(Math.floor(pct / 10)) + "░".repeat(10 - Math.floor(pct / 10));
        return `第${i + 1}块：【${plot.crop}】[${bar}]${pct}% 剩${fmtMs(left)}`;
    });

    const nextCost = LAND_COSTS[p.plots.length - 2];
    const expandHint = nextCost ? `\n扩地费：${fmtCoins(nextCost)}（.扩地）` : "";

    seal.replyToSender(ctx, msg, `🌾 ${ctx.player.name} 的田地（${p.plots.length}块）：\n${lines.join("\n")}${expandHint}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["田地"] = cmd田地;

// ========================
// .上山 — 打猎/采药
// ========================

let cmd上山 = seal.ext.newCmdItemInfo();
cmd上山.name = "上山";
cmd上山.help = "去山里打猎采药（有冷却）。用法：.上山";
cmd上山.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const cdMs = seal.ext.getIntConfig(ext, "打猎冷却_分钟") * 60000;
    const cdLeft = p.huntCd - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `精力未复，${fmtMs(cdLeft)} 后才能再次上山。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const result = rollHunt();
    p.huntCd = now() + cdMs;

    if (!result.name) {
        saveData(data);
        const emptyDesc = Array.isArray(result.desc) ? pick(result.desc) : result.desc;
        seal.replyToSender(ctx, msg,
            `🏔️ ${ctx.player.name} 背着竹篓上了山……\n${emptyDesc}\n（${fmtMs(cdMs)} 后可再上山）`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const count = rand(result.min, result.max);
    p.bag[result.name] = (p.bag[result.name] || 0) + count;
    saveData(data);

    const desc = Array.isArray(result.desc) ? pick(result.desc) : result.desc;
    const estVal = rand(result.minP, result.maxP) * count;
    seal.replyToSender(ctx, msg,
        `🏔️ ${ctx.player.name} 上山归来！\n${desc}\n` +
        `获得：【${result.name}】×${count}（约值 ${fmtCoins(estVal)}）\n` +
        `（${fmtMs(cdMs)} 后可再上山）`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上山"] = cmd上山;

// ========================
// .偷菜 @目标 — 偷取庄稼
// ========================

let cmd偷菜 = seal.ext.newCmdItemInfo();
cmd偷菜.name = "偷菜";
cmd偷菜.help = "趁人不备偷取他人田里的庄稼！用法：.偷菜 @目标";
cmd偷菜.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const thiefKey = pk(ctx);
    if (!data[thiefKey]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const thief = data[thiefKey];
    const cdMs = seal.ext.getIntConfig(ext, "偷菜冷却_分钟") * 60000;
    const cdLeft = thief.stealCd - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `上次偷菜惊动了邻居，还得等 ${fmtMs(cdLeft)} 风头才过！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const atList = msg.atUsersId || [];
    if (atList.length === 0) {
        seal.replyToSender(ctx, msg, "请@一个目标！用法：.偷菜 @某人");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetId = atList[0];
    if (targetId === ctx.player.userId) {
        seal.replyToSender(ctx, msg, "偷自己的菜？这合理吗？");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetKey = `${ctx.group.groupId}|${targetId}`;
    const target = data[targetKey];

    if (!target || !target.plots) {
        seal.replyToSender(ctx, msg, "对方还没立业，没有田地可偷！");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 找对方有庄稼的地（未成熟的才能偷，成熟了主人还没收）
    const stealablePlots = target.plots.filter(p => p !== null);
    if (stealablePlots.length === 0) {
        seal.replyToSender(ctx, msg, "对方田里空空如也，没什么可偷的！");
        return seal.ext.newCmdExecuteResult(true);
    }

    thief.stealCd = now() + cdMs;

    const roll = Math.floor(Math.random() * 100) + 1;
    const success = roll <= 55;

    if (success) {
        // 随机选一块地偷
        const stealableIdxArr = target.plots.map((p, i) => p ? i : -1).filter(i => i >= 0);
        const stealIdx = pick(stealableIdxArr);
        const plot = target.plots[stealIdx];
        const crop = CROPS[plot.crop];
        const stolen = Math.max(1, Math.floor(rand(crop.minY, crop.maxY) * 0.4));

        thief.bag[plot.crop] = (thief.bag[plot.crop] || 0) + stolen;

        // 减少目标产量（不直接清除地块）
        if (!plot.stolenCount) plot.stolenCount = 0;
        plot.stolenCount += stolen;

        saveData(data);

        const flavorSuccess = [
            "月黑风高，手脚麻利地摘了一把就跑！",
            "趁着主人不在，飞快摘了几个揣进怀里！",
            "动作轻柔，连露水都没惊动——",
        ];
        seal.replyToSender(ctx, msg,
            `🌙 【${ctx.player.name} 出手了！】\n` +
            `${pick(flavorSuccess)}\n` +
            `偷到：【${plot.crop}】×${stolen}\n` +
            `（冷却 ${fmtMs(cdMs)}）`
        );

        // 通知被偷者（若有端点缓存）
        if (target.groupId && target.userId) {
            const epKey = `${target.epPlatform}:${target.epBotId}:${target.groupId}`;
            const ep = epCache.get(epKey);
            if (ep) {
                const notifyMsg2 = seal.newMessage();
                notifyMsg2.messageType = "group";
                notifyMsg2.groupId = target.groupId;
                const notifyCtx = seal.createTempCtx(ep, notifyMsg2);
                seal.replyToSender(notifyCtx, notifyMsg2,
                    `${atUser(target.userId)} 你的【${plot.crop}】被 ${ctx.player.name} 偷走了 ${stolen} 个！快去【收地】防止二次损失！`
                );
            }
        }
    } else {
        saveData(data);
        const flavorFail = [
            "脚下一滑，踩断了树枝——邻居的狗叫了起来，狼狈逃窜！",
            "正要下手，猛地想起这家主人会武功，腿一软跑了！",
            "手还没伸过去，就被一个路过的老伯盯住了，只好讪讪离开。",
        ];
        seal.replyToSender(ctx, msg,
            `😅 【偷菜失败！】\n${pick(flavorFail)}\n` +
            `（冷却 ${fmtMs(cdMs)}）`
        );

        // 通知被偷者有人试图偷菜
        if (target.groupId && target.userId) {
            const epKey = `${target.epPlatform}:${target.epBotId}:${target.groupId}`;
            const ep = epCache.get(epKey);
            if (ep) {
                const notifyMsg2 = seal.newMessage();
                notifyMsg2.messageType = "group";
                notifyMsg2.groupId = target.groupId;
                const notifyCtx = seal.createTempCtx(ep, notifyMsg2);
                seal.replyToSender(notifyCtx, notifyMsg2,
                    `${atUser(target.userId)} ${ctx.player.name} 刚才想偷你的菜，没得手——不过要小心！`
                );
            }
        }
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["偷菜"] = cmd偷菜;

// ========================
// .集市 — 价格表
// ========================

let cmd集市 = seal.ext.newCmdItemInfo();
cmd集市.name = "集市";
cmd集市.help = "查看集市物价。用法：.集市";
cmd集市.solve = (ctx, msg, cmdArgs) => {
    const seedLines = Object.entries(CROPS).map(([crop, info]) =>
        `  ${info.seed} ${fmtCoins(info.seedCost)}/个 → 种${crop}（${info.growH}h，售${fmtCoins(info.minP)}~${fmtCoins(info.maxP)}/个）`
    );
    const huntLines = HUNT_TABLE.filter(h => h.name).map(h =>
        `  ${h.name}：${fmtCoins(h.minP)}~${fmtCoins(h.maxP)}/个`
    );
    seal.replyToSender(ctx, msg,
        `🏪 今日集市（物价每次浮动）\n` +
        `━━【种子购入】━━\n${seedLines.join("\n")}\n` +
        `━━【山货收购】━━\n${huntLines.join("\n")}\n` +
        `\n【买 种子名 数量】购买 · 【卖 物品名 数量/全部】出售`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["集市"] = cmd集市;

// ========================
// .卖 — 出售
// ========================

let cmd卖 = seal.ext.newCmdItemInfo();
cmd卖.name = "卖";
cmd卖.help = "出售物品。用法：.卖 野兔 2 / .卖 白菜 全部";
cmd卖.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const itemName = cmdArgs.getArgN(1);
    const countArg = cmdArgs.getArgN(2);
    if (!itemName) {
        seal.replyToSender(ctx, msg, "用法：.卖 物品名 数量（或"全部"）\n用【背包】查看持有物品。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const p = data[key];
    const have = p.bag[itemName] || 0;
    if (have <= 0) { seal.replyToSender(ctx, msg, `背包里没有【${itemName}】！`); return seal.ext.newCmdExecuteResult(true); }

    const sellCount = countArg === "全部" ? have : Math.min(parseInt(countArg) || 1, have);

    let unitPrice = 0;
    const cropInfo = CROPS[itemName];
    if (cropInfo) unitPrice = rand(cropInfo.minP, cropInfo.maxP);
    else { const h = HUNT_TABLE.find(h => h.name === itemName); if (h) unitPrice = rand(h.minP, h.maxP); }

    if (unitPrice === 0) { seal.replyToSender(ctx, msg, `【${itemName}】无法在集市出售！`); return seal.ext.newCmdExecuteResult(true); }

    const total = unitPrice * sellCount;
    const coinsBefore = p.coins;
    p.bag[itemName] = have - sellCount;
    if (p.bag[itemName] === 0) delete p.bag[itemName];
    p.coins += total;

    const idBefore = getIdentity(coinsBefore);
    const idAfter = getIdentity(p.coins);
    saveData(data);

    let reply = `💰 【${itemName}】×${sellCount}，今日单价 ${fmtCoins(unitPrice)}，共得 ${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}`;
    if (idAfter.name !== idBefore.name) {
        reply += `\n\n🎉 身份晋升为【${idAfter.name}】！`;
        const nextId = IDENTITIES[IDENTITIES.indexOf(idAfter) + 1];
        if (nextId) reply += `\n距【${nextId.name}】还差 ${fmtCoins(nextId.threshold - p.coins)}`;
    }
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["卖"] = cmd卖;
ext.cmdMap["出售"] = cmd卖;

// ========================
// .买 — 购买种子
// ========================

let cmd买 = seal.ext.newCmdItemInfo();
cmd买.name = "买";
cmd买.help = "购买种子。用法：.买 菜种 5";
cmd买.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const itemName = cmdArgs.getArgN(1);
    const count = Math.max(1, parseInt(cmdArgs.getArgN(2)) || 1);
    if (!itemName) {
        const list = Object.entries(CROPS).map(([, i]) => `${i.seed}(${fmtCoins(i.seedCost)}/个)`).join("、");
        seal.replyToSender(ctx, msg, `可购买：${list}\n用法：.买 菜种 5`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cropName = SEED_TO_CROP[itemName];
    if (!cropName) { seal.replyToSender(ctx, msg, `不能购买"${itemName}"，可买的种子：${Object.values(CROPS).map(i => i.seed).join("、")}`); return seal.ext.newCmdExecuteResult(true); }

    const crop = CROPS[cropName];
    const cost = crop.seedCost * count;
    const p = data[key];

    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `身上不够！需要 ${fmtCoins(cost)}，持有 ${fmtCoins(p.coins)}，差 ${fmtCoins(cost - p.coins)}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= cost;
    p.bag[itemName] = (p.bag[itemName] || 0) + count;
    saveData(data);

    seal.replyToSender(ctx, msg, `🛒 购入 ${itemName}×${count}，花费 ${fmtCoins(cost)}，剩余 ${fmtCoins(p.coins)}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["买"] = cmd买;
ext.cmdMap["购买"] = cmd买;

// ========================
// .扩地
// ========================

let cmd扩地 = seal.ext.newCmdItemInfo();
cmd扩地.name = "扩地";
cmd扩地.help = "购买新田地。用法：.扩地";
cmd扩地.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    if (p.plots.length >= 2 + LAND_COSTS.length) {
        seal.replyToSender(ctx, msg, `田地已达上限（${2 + LAND_COSTS.length}块）！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cost = LAND_COSTS[p.plots.length - 2];
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg, `扩地需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= cost;
    p.plots.push(null);
    saveData(data);

    seal.replyToSender(ctx, msg, `🏡 扩地成功！花费 ${fmtCoins(cost)}，现有 ${p.plots.length} 块田地。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["扩地"] = cmd扩地;

// ========================
// .科举 — 参加科举
// ========================

let cmd科举 = seal.ext.newCmdItemInfo();
cmd科举.name = "科举";
cmd科举.help = "参加科举考试，晋升功名（秀才→举人→进士→状元）。用法：.科举";
cmd科举.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const fame = p.fame || 0;

    if (fame >= FAME_LEVELS.length - 1) {
        seal.replyToSender(ctx, msg, `已是【状元】，科举一途已至极峰，无需再考！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const level = FAME_LEVELS[fame];
    const cdLeft = (p.examCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `上次考试后还需静养，${fmtMs(cdLeft)} 后才能再考！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (p.coins < level.examCost) {
        seal.replyToSender(ctx, msg,
            `参加科举需要打点盘缠 ${fmtCoins(level.examCost)}，目前只有 ${fmtCoins(p.coins)}，还差 ${fmtCoins(level.examCost - p.coins)}！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const nextTitle = FAME_LEVELS[fame + 1].title;
    p.coins -= level.examCost;
    p.examCd = now() + level.examCd * 3600000;

    const roll = Math.random();
    if (roll <= level.examRate) {
        p.fame = fame + 1;
        saveData(data);

        const successFlavor = [
            "金榜题名，鞭炮声中，邻里皆来道贺！",
            "看榜时心跳如鼓，找到自己名字那一刻，泪水不争气地流了下来。",
            "先生说过，十年寒窗苦，今日终有报。",
        ];
        let reply =
            `📜 【科举揭榜】金榜有名！\n` +
            `${ctx.player.name} 一举高中，荣获【${nextTitle}】！\n` +
            `${pick(successFlavor)}\n`;

        if (p.fame === 1) reply += `\n🎊 已解锁：可开设【小铺子】（.开铺 小铺子）`;
        if (p.fame === 2) reply += `\n🎊 已解锁：可开设【酒楼】`;
        if (p.fame === 3) reply += `\n🎊 已解锁：可开设【商行】`;
        if (p.fame === 4) reply += `\n🎊 已解锁：可开设【钱庄】| 已达功名之巅！`;

        seal.replyToSender(ctx, msg, reply);
    } else {
        saveData(data);
        const failFlavor = [
            "答到一半，手心发抖，出了考场才知道写错了。",
            "文章洋洋洒洒，偏偏偏了题意，名落孙山。",
            "主考官看了半天，摇了摇头，落笔打了个叉。",
        ];
        seal.replyToSender(ctx, msg,
            `📜 【科举揭榜】榜上无名。\n${pick(failFlavor)}\n` +
            `花费盘缠 ${fmtCoins(level.examCost)}，${fmtMs(level.examCd * 3600000)} 后可再考。`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["科举"] = cmd科举;

// ========================
// .开铺 — 开设铺子
// ========================

let cmd开铺 = seal.ext.newCmdItemInfo();
cmd开铺.name = "开铺";
cmd开铺.help = "开设铺子（需对应功名）。用法：.开铺 小铺子";
cmd开铺.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const shopName = cmdArgs.getArgN(1);
    if (!shopName) {
        const list = Object.entries(SHOPS).map(([name, s]) =>
            `  ${name}：需${FAME_LEVELS[s.requiredFame].title}，投资${fmtCoins(s.cost)}，每${seal.ext.getIntConfig(ext,"收租间隔_小时")}h收入${fmtCoins(s.minIncome)}~${fmtCoins(s.maxIncome)}`
        ).join("\n");
        seal.replyToSender(ctx, msg, `可开设的铺子：\n${list}\n用法：.开铺 小铺子`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const shop = SHOPS[shopName];
    if (!shop) {
        seal.replyToSender(ctx, msg, `不认识"${shopName}"！可开：${Object.keys(SHOPS).join("、")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const p = data[key];
    if ((p.fame || 0) < shop.requiredFame) {
        seal.replyToSender(ctx, msg,
            `开设${shopName}需要【${FAME_LEVELS[shop.requiredFame].title}】以上功名，当前是【${FAME_LEVELS[p.fame || 0].title}】！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!p.shops) p.shops = {};
    const owned = p.shops[shopName] || 0;
    if (owned >= 3) {
        seal.replyToSender(ctx, msg, `${shopName}最多开3家！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (p.coins < shop.cost) {
        seal.replyToSender(ctx, msg, `开设${shopName}需 ${fmtCoins(shop.cost)}，还差 ${fmtCoins(shop.cost - p.coins)}！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= shop.cost;
    p.shops[shopName] = owned + 1;
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🏪 ${shopName}开张大吉！花费 ${fmtCoins(shop.cost)}\n` +
        `现有 ${p.shops[shopName]} 家${shopName}，每 ${seal.ext.getIntConfig(ext,"收租间隔_小时")}h 可领取收入！\n` +
        `用【收租】领取所有铺子收益。`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开铺"] = cmd开铺;

// ========================
// .收租 — 收取铺子收入
// ========================

let cmd收租 = seal.ext.newCmdItemInfo();
cmd收租.name = "收租";
cmd收租.help = "收取所有铺子的收益。用法：.收租";
cmd收租.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    if (!p.shops || Object.keys(p.shops).length === 0) {
        seal.replyToSender(ctx, msg, "你还没有铺子！先用【开铺】开设，需要对应功名。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const intervalMs = seal.ext.getIntConfig(ext, "收租间隔_小时") * 3600000;
    const cdLeft = (p.shopCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `账房说账还没结好，${fmtMs(cdLeft)} 后再来！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let total = 0;
    const details = [];
    for (const [shopName, count] of Object.entries(p.shops)) {
        if (!count || count <= 0) continue;
        const shop = SHOPS[shopName];
        const income = rand(shop.minIncome, shop.maxIncome) * count;
        total += income;
        details.push(`${shopName}×${count}：${fmtCoins(income)}`);
    }

    if (total === 0) {
        seal.replyToSender(ctx, msg, "本期没有收入，下次再来！");
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins += total;
    p.shopCd = now() + intervalMs;
    saveData(data);

    seal.replyToSender(ctx, msg,
        `💼 账房送来了账册——\n${details.join("\n")}\n` +
        `合计入账：${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}\n` +
        `下次收租：${fmtMs(intervalMs)} 后`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["收租"] = cmd收租;

// ========================
// .我的铺子
// ========================

let cmd铺子 = seal.ext.newCmdItemInfo();
cmd铺子.name = "我的铺子";
cmd铺子.help = "查看自己的铺子。用法：.我的铺子";
cmd铺子.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const shops = p.shops || {};
    const owned = Object.entries(shops).filter(([, v]) => v > 0);

    if (owned.length === 0) {
        seal.replyToSender(ctx, msg, `还没有铺子，科举获取功名后可用【开铺】开设！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const intervalMs = seal.ext.getIntConfig(ext, "收租间隔_小时") * 3600000;
    const cdLeft = (p.shopCd || 0) - now();
    const lines = owned.map(([name, count]) => {
        const shop = SHOPS[name];
        return `  ${name}×${count}，每次收入 ${fmtCoins(shop.minIncome * count)}~${fmtCoins(shop.maxIncome * count)}`;
    });

    seal.replyToSender(ctx, msg,
        `🏪 ${ctx.player.name} 的铺子：\n${lines.join("\n")}\n` +
        `下次收租：${cdLeft > 0 ? fmtMs(cdLeft) + "后" : "现在可收（.收租）"}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的铺子"] = cmd铺子;
ext.cmdMap["铺子"] = cmd铺子;

// ========================
// 美男美女系统
// ========================

// 初始化花名册（群级别）
function initAttr(gid) {
    let ad = getAttrData(gid);
    let changed = false;
    for (const [name, basePrice, desc] of CHAR_LIST) {
        if (!ad[name]) {
            ad[name] = { owner: null, ownerName: null, price: basePrice, desc };
            changed = true;
        }
    }
    if (changed) saveAttrData(gid, ad);
    return ad;
}

// .花名册 — 查看所有佳人
let cmd花名册 = seal.ext.newCmdItemInfo();
cmd花名册.name = "花名册";
cmd花名册.help = "查看群内可追求的美男美女。用法：.花名册 [男/女/空闲/第N页]";
cmd花名册.solve = (ctx, msg, cmdArgs) => {
    const gid = ctx.group.groupId;
    const ad = initAttr(gid);
    const filter = cmdArgs.getArgN(1) || "";

    let chars = CHAR_LIST.map(([name, , desc]) => ({
        name, desc, ...ad[name]
    }));

    if (filter === "男") chars = chars.filter((_, i) => i < 25);
    else if (filter === "女") chars = chars.filter((_, i) => i >= 25);
    else if (filter === "空闲") chars = chars.filter(c => !c.owner);
    else if (filter === "我的") {
        const myId = ctx.player.userId;
        chars = chars.filter(c => c.owner === myId);
    }

    const pageSize = 10;
    const pageNum = parseInt(filter) || 1;
    const totalPages = Math.ceil(chars.length / pageSize);
    const page = isNaN(parseInt(filter)) ? 1 : Math.min(pageNum, totalPages);
    const paged = chars.slice((page - 1) * pageSize, page * pageSize);

    const lines = paged.map(c =>
        `【${c.name}】${c.owner ? `（已归 ${c.ownerName}，${fmtCoins(c.price)}可争抢）` : `（${fmtCoins(c.price)}可追求）`}`
    );

    seal.replyToSender(ctx, msg,
        `💐 花名册（第${page}/${totalPages}页）\n` +
        `可用：男/女/空闲/页码 筛选，如 .花名册 女\n` +
        `━━━━━━\n${lines.join("\n")}\n` +
        `━━━━━━\n追求用：.追求 姓名 | 查看佳人：.花名册 我的`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["花名册"] = cmd花名册;

// .佳人详情 — 查看单人详情
let cmd佳人详情 = seal.ext.newCmdItemInfo();
cmd佳人详情.name = "佳人";
cmd佳人详情.help = "查看某位佳人的详细信息。用法：.佳人 云逸";
cmd佳人详情.solve = (ctx, msg, cmdArgs) => {
    const gid = ctx.group.groupId;
    const ad = initAttr(gid);
    const name = cmdArgs.getArgN(1);

    if (!name) {
        // 查看自己的佳人
        const myId = ctx.player.userId;
        const mine = CHAR_LIST.filter(([n]) => ad[n] && ad[n].owner === myId).map(([n]) => n);
        if (mine.length === 0) {
            seal.replyToSender(ctx, msg, "你还没有佳人，用【追求 姓名】去追吧！");
        } else {
            const lines = mine.map(n => {
                const c = ad[n];
                const entry = CHAR_LIST.find(([en]) => en === n);
                return `【${n}】${entry ? entry[2] : ""}（当前身价 ${fmtCoins(c.price)}）`;
            });
            seal.replyToSender(ctx, msg, `${ctx.player.name} 的佳人们：\n${lines.join("\n")}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    const entry = CHAR_LIST.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"，用【花名册】查看全部。`); return seal.ext.newCmdExecuteResult(true); }

    const c = ad[name] || { owner: null, ownerName: null, price: entry[1], desc: entry[2] };
    const statusLine = c.owner
        ? `归属：${c.ownerName}（出价 ${fmtCoins(Math.ceil(c.price * 1.5))} 可争抢）`
        : `尚无归属，只需 ${fmtCoins(c.price)} 即可追求`;

    seal.replyToSender(ctx, msg,
        `💌 【${name}】\n${c.desc}\n━━━━\n${statusLine}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["佳人"] = cmd佳人详情;
ext.cmdMap["我的佳人"] = cmd佳人详情;

// .追求 — 追求/争抢佳人
let cmd追求 = seal.ext.newCmdItemInfo();
cmd追求.name = "追求";
cmd追求.help = "追求或争抢某位佳人。用法：.追求 云逸";
cmd追求.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const gid = ctx.group.groupId;
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const name = cmdArgs.getArgN(1);
    if (!name) { seal.replyToSender(ctx, msg, "请指定追求目标！用法：.追求 云逸\n用【花名册】查看全部人选。"); return seal.ext.newCmdExecuteResult(true); }

    const entry = CHAR_LIST.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"，用【花名册】查看。`); return seal.ext.newCmdExecuteResult(true); }

    const ad = initAttr(gid);
    const c = ad[name];
    const p = data[key];

    // 自己已拥有
    if (c.owner === ctx.player.userId) {
        seal.replyToSender(ctx, msg, `${name} 已经在你身边了，何必再追？`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let cost = c.owner ? Math.ceil(c.price * 1.5) : c.price;

    if (p.coins < cost) {
        seal.replyToSender(ctx, msg,
            c.owner
                ? `争抢【${name}】需出价 ${fmtCoins(cost)}（现价×1.5），还差 ${fmtCoins(cost - p.coins)}！`
                : `追求【${name}】需要 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= cost;

    if (c.owner) {
        // 争抢：前任主人得回原价+10%
        const prevOwnerKey = `${gid}|${c.owner}`;
        const prevOwner = data[prevOwnerKey];
        const refund = Math.floor(c.price * 1.1);
        if (prevOwner) {
            prevOwner.coins += refund;
        }

        const prevName = c.ownerName;
        c.ownerName = ctx.player.name;
        c.owner = ctx.player.userId;
        c.price = cost;

        saveData(data);
        saveAttrData(gid, ad);

        const flavorSnatch = [
            "锦书一封，人已改换门庭。",
            "花落谁家，今日见分晓。",
            "财帛动人心，情缘自有定数。",
        ];
        let reply =
            `💘 ${ctx.player.name} 以 ${fmtCoins(cost)} 的诚意，将【${name}】从 ${prevName} 身边带走了！\n` +
            `${pick(flavorSnatch)}\n` +
            `（${prevName} 获得退款 ${fmtCoins(refund)}，当前身价 ${fmtCoins(cost)}）`;

        // 通知被抢者
        if (prevOwner && prevOwner.groupId && prevOwner.userId) {
            const epKey = `${prevOwner.epPlatform}:${prevOwner.epBotId}:${prevOwner.groupId}`;
            const ep = epCache.get(epKey);
            if (ep) {
                const nm = seal.newMessage();
                nm.messageType = "group";
                nm.groupId = prevOwner.groupId;
                const tc = seal.createTempCtx(ep, nm);
                seal.replyToSender(tc, nm,
                    `${atUser(prevOwner.userId)} 【${name}】被 ${ctx.player.name} 以 ${fmtCoins(cost)} 争走了！退款 ${fmtCoins(refund)}。`
                );
            }
        }

        seal.replyToSender(ctx, msg, reply);
    } else {
        c.owner = ctx.player.userId;
        c.ownerName = ctx.player.name;
        c.price = cost;

        saveData(data);
        saveAttrData(gid, ad);

        const flavorGet = [
            "鸿雁传书，情意已通，缘分自此而始。",
            "心悦之人终归己，此后相伴左右。",
            "一见倾心，万两黄金也值得。",
        ];
        seal.replyToSender(ctx, msg,
            `💕 ${ctx.player.name} 以 ${fmtCoins(cost)} 的诚意追到了【${name}】！\n` +
            `${pick(flavorGet)}\n${entry[2]}`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["追求"] = cmd追求;
ext.cmdMap["争抢"] = cmd追求;

// .放手 — 放弃一位佳人
let cmd放手 = seal.ext.newCmdItemInfo();
cmd放手.name = "放手";
cmd放手.help = "放弃一位佳人，让他/她重回花名册（退还原价50%）。用法：.放手 云逸";
cmd放手.solve = (ctx, msg, cmdArgs) => {
    const data = ensurePlayer(ctx);
    const gid = ctx.group.groupId;
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const name = cmdArgs.getArgN(1);
    if (!name) { seal.replyToSender(ctx, msg, "用法：.放手 云逸\n用【我的佳人】查看已拥有的佳人。"); return seal.ext.newCmdExecuteResult(true); }

    const ad = initAttr(gid);
    const c = ad[name];
    if (!c || c.owner !== ctx.player.userId) {
        seal.replyToSender(ctx, msg, `【${name}】不在你身边，无需放手。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const refund = Math.floor(c.price * 0.5);
    const p = data[key];
    p.coins += refund;

    const origEntry = CHAR_LIST.find(([n]) => n === name);
    c.owner = null;
    c.ownerName = null;
    c.price = origEntry ? origEntry[1] : c.price;

    saveData(data);
    saveAttrData(gid, ad);

    seal.replyToSender(ctx, msg,
        `【${name}】已放手，重回自由身。\n退还 ${fmtCoins(refund)}，他/她的身价恢复初始。`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["放手"] = cmd放手;

// ========================
// .背包
// ========================

let cmd背包 = seal.ext.newCmdItemInfo();
cmd背包.name = "背包";
cmd背包.help = "查看背包。用法：.背包";
cmd背包.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const bag = data[key].bag || {};
    const items = Object.entries(bag).filter(([, v]) => v > 0);
    if (items.length === 0) { seal.replyToSender(ctx, msg, `${ctx.player.name} 的背包空空如也！`); return seal.ext.newCmdExecuteResult(true); }

    const seeds = [], crops = [], hunts = [];
    for (const [name, count] of items) {
        if (SEED_TO_CROP[name]) seeds.push(`${name}×${count}`);
        else if (CROPS[name]) crops.push(`${name}×${count}`);
        else hunts.push(`${name}×${count}`);
    }
    let lines = [];
    if (seeds.length) lines.push(`【种子】${seeds.join("、")}`);
    if (crops.length) lines.push(`【农产】${crops.join("、")}`);
    if (hunts.length) lines.push(`【山货】${hunts.join("、")}`);

    seal.replyToSender(ctx, msg, `🎒 ${ctx.player.name} 的背包：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["背包"] = cmd背包;
ext.cmdMap["仓库"] = cmd背包;

// ========================
// .身家
// ========================

let cmd身家 = seal.ext.newCmdItemInfo();
cmd身家.name = "身家";
cmd身家.help = "查看财富和状态。用法：.身家";
cmd身家.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const id = getIdentity(p.coins);
    const idIdx = IDENTITIES.indexOf(id);
    const nextId = IDENTITIES[idIdx + 1];
    const fame = p.fame || 0;
    const fameTitle = FAME_LEVELS[fame].title;
    const huntLeft = (p.huntCd || 0) - now();
    const examLeft = (p.examCd || 0) - now();
    const shopLeft = (p.shopCd || 0) - now();
    const readyPlots = p.plots.filter(pl => pl && pl.readyAt <= now()).length;

    const shopList = Object.entries(p.shops || {}).filter(([, v]) => v > 0).map(([n, v]) => `${n}×${v}`);

    let lines = [
        `📜 ${ctx.player.name} 的发家档案`,
        `━━━━━━━━━━`,
        `身份：${id.name} | 功名：${fameTitle}`,
        `身家：${fmtCoins(p.coins)}`,
        `田地：${p.plots.length}块${readyPlots ? `（${readyPlots}块已熟！）` : ""}`,
    ];
    if (shopList.length) lines.push(`铺子：${shopList.join("、")}${shopLeft > 0 ? `（${fmtMs(shopLeft)}后收租）` : "（可收租）"}`);
    lines.push(`上山：${huntLeft > 0 ? fmtMs(huntLeft) + "后" : "可出发"}`);
    if (fame < FAME_LEVELS.length - 1) {
        const nextFame = FAME_LEVELS[fame + 1];
        lines.push(`科举：${examLeft > 0 ? fmtMs(examLeft) + "后可考" : `可参考（需${fmtCoins(FAME_LEVELS[fame].examCost)}，目标${nextFame.title}）`}`);
    }
    lines.push(`━━━━━━━━━━`);
    lines.push(nextId ? `距【${nextId.name}】还差 ${fmtCoins(nextId.threshold - p.coins)}` : "富甲天下，已至巅峰！");

    seal.replyToSender(ctx, msg, lines.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["身家"] = cmd身家;
ext.cmdMap["状态"] = cmd身家;

// ========================
// .发家帮助
// ========================

let cmd帮助 = seal.ext.newCmdItemInfo();
cmd帮助.name = "发家帮助";
cmd帮助.help = "查看全部指令";
cmd帮助.solve = (ctx, msg, cmdArgs) => {
    seal.replyToSender(ctx, msg,
        `🌾 古代发家系统 · 全指令\n` +
        `━━【基础】━━\n` +
        `【立业】创建角色 | 【身家】查看状态 | 【背包】查看物品\n` +
        `━━【种地】━━\n` +
        `【种 作物名】播种 | 【收地】收获 | 【田地】查看进度\n` +
        `【扩地】购新田 | （成熟时会@提醒）\n` +
        `━━【山野】━━\n` +
        `【上山】打猎/采药（冷却${seal.ext.getIntConfig(ext,"打猎冷却_分钟")}分）\n` +
        `【偷菜 @目标】悄悄偷别人田里的菜\n` +
        `━━【买卖】━━\n` +
        `【集市】价格表 | 【买 种子 数量】购种子\n` +
        `【卖 物品 数量/全部】出售\n` +
        `━━【科举仕途】━━\n` +
        `【科举】参加考试（白身→秀才→举人→进士→状元）\n` +
        `【开铺 铺名】开设铺子（需对应功名）\n` +
        `【铺子】查看铺子 | 【收租】领取铺子收益\n` +
        `━━【佳人争抢】━━\n` +
        `【花名册】查看50位美男美女\n` +
        `【佳人 姓名】查看详情 | 【我的佳人】查看拥有\n` +
        `【追求 姓名】追求/争抢佳人 | 【放手 姓名】释放\n` +
        `━━【身份晋升】━━\n` +
        IDENTITIES.map((id, i) => i === 0 ? id.name : `${fmtCoins(id.threshold)}→${id.name}`).join(" ")
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发家帮助"] = cmd帮助;
