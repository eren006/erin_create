// ==UserScript==
// @name         古代农商系统
// @author       长日将尽
// @version      1.0.0
// @description  种地、打猎、采药、买卖，从穷苦流民白手起家成为大富豪
// @timestamp    1748563200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

// ========================
// 初始化
// ========================

let ext = seal.ext.find("ancient_farm_system");
if (!ext) {
    ext = seal.ext.new("ancient_farm_system", "长日将尽", "1.0.0");
    seal.ext.registerIntConfig(ext, "打猎冷却_分钟", 120);
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
function pk(ctx) { return `${ctx.group.groupId}|${ctx.player.userId}`; }
function now() { return Date.now(); }

// ========================
// 格式化工具
// ========================

function fmtMs(ms) {
    if (ms <= 0) return "不到1分钟";
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return m > 0 ? `${h}小时${m}分` : `${h}小时`;
    return `${m}分`;
}

// 1两 = 100铜，显示格式化
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

// ========================
// 游戏数据表
// ========================

// 作物表：seed=种子名, seedCost=种子价格(铜), growH=生长时间(小时), minY/maxY=收获数量, minP/maxP=市价区间(铜/个)
const CROPS = {
    "白菜": { seed: "菜种",   seedCost: 5,   growH: 2,  minY: 3, maxY: 6,  minP: 8,   maxP: 15   },
    "萝卜": { seed: "萝卜种", seedCost: 8,   growH: 3,  minY: 2, maxY: 5,  minP: 18,  maxP: 28   },
    "土豆": { seed: "土豆种", seedCost: 15,  growH: 4,  minY: 2, maxY: 4,  minP: 30,  maxP: 45   },
    "草药": { seed: "草药种", seedCost: 40,  growH: 8,  minY: 1, maxY: 3,  minP: 80,  maxP: 130  },
    "人参": { seed: "参苗",   seedCost: 300, growH: 24, minY: 1, maxY: 2,  minP: 600, maxP: 1000 },
};

// 种子名反查作物名
const SEED_TO_CROP = {};
for (const [crop, info] of Object.entries(CROPS)) {
    SEED_TO_CROP[info.seed] = crop;
}

// 上山结果表：weight=权重, name=null为空手而归
const HUNT_TABLE = [
    { weight: 25,  name: null,        desc: "山里没有动静，白跑一趟",           min: 0, max: 0, minP: 0,    maxP: 0    },
    { weight: 22,  name: "野山菌",    desc: "在山脚发现了不少野山菌",           min: 1, max: 4, minP: 15,   maxP: 28   },
    { weight: 18,  name: "野兔",      desc: "猎到了野兔",                       min: 1, max: 2, minP: 35,   maxP: 55   },
    { weight: 13,  name: "野鸡",      desc: "猎到了野鸡",                       min: 1, max: 2, minP: 55,   maxP: 80   },
    { weight: 10,  name: "野猪肉",    desc: "遇上了野猪，搏斗后带回了猪肉",     min: 2, max: 5, minP: 45,   maxP: 70   },
    { weight: 6,   name: "灵芝",      desc: "在深山崖边发现了珍贵灵芝！",       min: 1, max: 1, minP: 250,  maxP: 450  },
    { weight: 4,   name: "梅花鹿",    desc: "猎到了一头梅花鹿！",               min: 1, max: 1, minP: 180,  maxP: 300  },
    { weight: 1.5, name: "何首乌",    desc: "在古树下挖到了百年何首乌！！",     min: 1, max: 1, minP: 500,  maxP: 900  },
    { weight: 0.5, name: "百年山参",  desc: "传说中的百年山参就在眼前！！！",   min: 1, max: 1, minP: 1500, maxP: 3000 },
];

// 扩地费用：第3块→第4→5→6→7块
const LAND_COSTS = [500, 2000, 8000, 30000, 100000];

// 身份阶梯（按铜钱判定）
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
    for (const i of IDENTITIES) {
        if (coins >= i.threshold) id = i;
        else break;
    }
    return id;
}

function rollHunt() {
    const total = HUNT_TABLE.reduce((s, h) => s + h.weight, 0);
    let r = Math.random() * total;
    for (const h of HUNT_TABLE) {
        r -= h.weight;
        if (r <= 0) return h;
    }
    return HUNT_TABLE[0];
}

// ========================
// .立业 — 初始化角色
// ========================

let cmd立业 = seal.ext.newCmdItemInfo();
cmd立业.name = "立业";
cmd立业.help = "开始发家之路。用法：.立业";
cmd立业.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);

    if (data[key]) {
        const p = data[key];
        const id = getIdentity(p.coins);
        seal.replyToSender(ctx, msg,
            `${ctx.player.name} 已立业在此，无需重建。\n当前身份：${id.name} | 身家：${fmtCoins(p.coins)}`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    data[key] = {
        coins: 50,
        plots: [null, null],
        huntCd: 0,
        bag: { "菜种": 3 },
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🌱 ${ctx.player.name} 带着全部家当来到此地，白手起家！\n` +
        `初始家当：50铜 + 2块田地 + 菜种×3\n` +
        `————————\n` +
        `快速入门：\n` +
        `【种 白菜】用菜种种下白菜（2小时后成熟）\n` +
        `【收地】收获成熟作物\n` +
        `【卖 白菜 全部】在集市出售\n` +
        `【上山】去山里打猎采药\n` +
        `【农商帮助】查看全部指令`
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
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const cropName = cmdArgs.getArgN(1);
    if (!cropName) {
        const list = Object.entries(CROPS).map(([c, i]) => `${c}（${i.growH}h，需${i.seed}）`).join("、");
        seal.replyToSender(ctx, msg, `请指定作物！可种：${list}\n用法：.种 白菜`);
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
        seal.replyToSender(ctx, msg, `田地全满！先【收地】腾出空地，或用【扩地】购买新田。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const seedCount = p.bag[crop.seed] || 0;
    if (seedCount <= 0) {
        seal.replyToSender(ctx, msg,
            `没有【${crop.seed}】了！去集市购买，单价 ${fmtCoins(crop.seedCost)}。\n用法：.买 ${crop.seed} 5`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    p.bag[crop.seed] = seedCount - 1;
    if (p.bag[crop.seed] === 0) delete p.bag[crop.seed];

    p.plots[emptyIdx] = {
        crop: cropName,
        plantedAt: now(),
        readyAt: now() + crop.growH * 3600000,
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🌿 在第 ${emptyIdx + 1} 块地种下了【${cropName}】！\n` +
        `${fmtMs(crop.growH * 3600000)} 后成熟，记得回来【收地】。`
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
cmd收地.help = "收获所有已成熟的作物。用法：.收地";
cmd收地.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const harvested = [];
    let unready = 0;

    for (let i = 0; i < p.plots.length; i++) {
        const plot = p.plots[i];
        if (!plot) continue;
        const left = plot.readyAt - now();
        if (left > 0) { unready++; continue; }
        const crop = CROPS[plot.crop];
        const count = rand(crop.minY, crop.maxY);
        p.bag[plot.crop] = (p.bag[plot.crop] || 0) + count;
        harvested.push(`【${plot.crop}】×${count}`);
        p.plots[i] = null;
    }

    saveData(data);

    if (harvested.length === 0 && unready === 0) {
        seal.replyToSender(ctx, msg, "田地是空的，先用【种】种点什么！");
    } else if (harvested.length === 0) {
        seal.replyToSender(ctx, msg, `还没成熟，再等等！（${unready} 块地在生长中）`);
    } else {
        let reply = `🌾 ${ctx.player.name} 收获：${harvested.join("、")}`;
        if (unready > 0) reply += `\n（还有 ${unready} 块地未成熟）`;
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
        if (!plot) return `第${i + 1}块：【空地】可播种`;
        const left = plot.readyAt - now();
        if (left <= 0) return `第${i + 1}块：【${plot.crop}】✅ 已成熟，快去收！`;
        const pct = Math.floor((1 - left / (CROPS[plot.crop].growH * 3600000)) * 100);
        return `第${i + 1}块：【${plot.crop}】⏳ ${fmtMs(left)}后熟（${pct}%）`;
    });

    // 下次可扩地提示
    const nextCost = LAND_COSTS[p.plots.length - 2];
    const expandHint = nextCost ? `\n扩地费用：${fmtCoins(nextCost)}（.扩地）` : "";

    seal.replyToSender(ctx, msg,
        `🌾 ${ctx.player.name} 的田地（${p.plots.length} 块）：\n` +
        lines.join("\n") + expandHint
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["田地"] = cmd田地;

// ========================
// .上山 — 打猎/采药
// ========================

let cmd上山 = seal.ext.newCmdItemInfo();
cmd上山.name = "上山";
cmd上山.help = "去山上打猎或采药（有冷却）。用法：.上山";
cmd上山.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const cdMs = seal.ext.getIntConfig(ext, "打猎冷却_分钟") * 60000;
    const cdLeft = p.huntCd - now();

    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `精力不济，${fmtMs(cdLeft)} 后才能再次上山！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const result = rollHunt();
    p.huntCd = now() + cdMs;

    if (!result.name) {
        saveData(data);
        seal.replyToSender(ctx, msg,
            `🏔️ ${ctx.player.name} 上山转了一圈……\n${result.desc}\n（下次：${fmtMs(cdMs)} 后）`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const count = rand(result.min, result.max);
    p.bag[result.name] = (p.bag[result.name] || 0) + count;
    saveData(data);

    const estVal = rand(result.minP, result.maxP) * count;
    seal.replyToSender(ctx, msg,
        `🏔️ ${ctx.player.name} 上山归来！\n` +
        `${result.desc}：【${result.name}】×${count}\n` +
        `参考价值约 ${fmtCoins(estVal)}\n` +
        `（下次：${fmtMs(cdMs)} 后）`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上山"] = cmd上山;

// ========================
// .集市 — 价格表
// ========================

let cmd集市 = seal.ext.newCmdItemInfo();
cmd集市.name = "集市";
cmd集市.help = "查看集市价格表。用法：.集市";
cmd集市.solve = (ctx, msg, cmdArgs) => {
    const seedLines = Object.entries(CROPS).map(([crop, info]) =>
        `  ${info.seed} ${fmtCoins(info.seedCost)}/个 → 种出${crop}（${info.growH}h，市价${fmtCoins(info.minP)}~${fmtCoins(info.maxP)}/个）`
    );
    const huntLines = HUNT_TABLE.filter(h => h.name).map(h =>
        `  ${h.name}：${fmtCoins(h.minP)}~${fmtCoins(h.maxP)}/个`
    );

    seal.replyToSender(ctx, msg,
        `🏪 集市价目表（市价每次浮动）\n` +
        `━━【购买种子】━━\n` +
        seedLines.join("\n") + "\n" +
        `━━【收购山货/农产】━━\n` +
        huntLines.join("\n") + "\n" +
        `\n【买 种子名 数量】购买 | 【卖 物品名 数量/全部】出售`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["集市"] = cmd集市;

// ========================
// .卖 — 出售物品
// ========================

let cmd卖 = seal.ext.newCmdItemInfo();
cmd卖.name = "卖";
cmd卖.help = "出售物品。用法：.卖 野兔 2 / .卖 白菜 全部";
cmd卖.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const itemName = cmdArgs.getArgN(1);
    const countArg = cmdArgs.getArgN(2);

    if (!itemName) {
        seal.replyToSender(ctx, msg, "用法：.卖 物品名 数量\n例如：.卖 野兔 2 / .卖 白菜 全部\n用【背包】查看持有物品。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const p = data[key];
    const have = p.bag[itemName] || 0;
    if (have <= 0) {
        seal.replyToSender(ctx, msg, `背包里没有【${itemName}】！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const sellCount = countArg === "全部" ? have : Math.min(parseInt(countArg) || 1, have);
    if (sellCount <= 0) {
        seal.replyToSender(ctx, msg, "数量有误！");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查单价：先查农产品，再查山货
    let unitPrice = 0;
    const cropInfo = CROPS[itemName];
    if (cropInfo) {
        unitPrice = rand(cropInfo.minP, cropInfo.maxP);
    } else {
        const huntInfo = HUNT_TABLE.find(h => h.name === itemName);
        if (huntInfo) unitPrice = rand(huntInfo.minP, huntInfo.maxP);
    }

    if (unitPrice === 0) {
        seal.replyToSender(ctx, msg, `【${itemName}】无法在集市出售！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const total = unitPrice * sellCount;
    const coinsBefore = p.coins;
    p.bag[itemName] = have - sellCount;
    if (p.bag[itemName] === 0) delete p.bag[itemName];
    p.coins += total;

    const idBefore = getIdentity(coinsBefore);
    const idAfter = getIdentity(p.coins);
    saveData(data);

    let reply =
        `💰 出售成功！\n` +
        `【${itemName}】×${sellCount}，今日单价 ${fmtCoins(unitPrice)}，共得 ${fmtCoins(total)}\n` +
        `当前身家：${fmtCoins(p.coins)}`;

    if (idAfter.name !== idBefore.name) {
        reply += `\n\n🎉 恭喜！身份晋升为【${idAfter.name}】！`;
        const nextId = IDENTITIES[IDENTITIES.indexOf(idAfter) + 1];
        if (nextId) reply += `\n（距【${nextId.name}】还需 ${fmtCoins(nextId.threshold - p.coins)}）`;
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
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const itemName = cmdArgs.getArgN(1);
    const count = Math.max(1, parseInt(cmdArgs.getArgN(2)) || 1);

    if (!itemName) {
        const list = Object.entries(CROPS).map(([, i]) => `${i.seed}（${fmtCoins(i.seedCost)}/个）`).join("、");
        seal.replyToSender(ctx, msg, `请指定要购买的种子！\n可购买：${list}\n用法：.买 菜种 5`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cropName = SEED_TO_CROP[itemName];
    if (!cropName) {
        const list = Object.values(CROPS).map(i => i.seed).join("、");
        seal.replyToSender(ctx, msg, `不能购买"${itemName}"！可买的种子：${list}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const crop = CROPS[cropName];
    const cost = crop.seedCost * count;
    const p = data[key];

    if (p.coins < cost) {
        seal.replyToSender(ctx, msg,
            `身上铜钱不够！\n需要 ${fmtCoins(cost)}，持有 ${fmtCoins(p.coins)}，差 ${fmtCoins(cost - p.coins)}`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= cost;
    p.bag[itemName] = (p.bag[itemName] || 0) + count;
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🛒 购买成功！${itemName}×${count}，花费 ${fmtCoins(cost)}\n剩余身家：${fmtCoins(p.coins)}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["买"] = cmd买;
ext.cmdMap["购买"] = cmd买;

// ========================
// .扩地 — 扩大田地
// ========================

let cmd扩地 = seal.ext.newCmdItemInfo();
cmd扩地.name = "扩地";
cmd扩地.help = "花铜钱购买新田地。用法：.扩地";
cmd扩地.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const maxLand = 2 + LAND_COSTS.length;

    if (p.plots.length >= maxLand) {
        seal.replyToSender(ctx, msg, `田地已达上限（${maxLand} 块），无法继续扩张！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cost = LAND_COSTS[p.plots.length - 2];
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg,
            `扩地需要 ${fmtCoins(cost)}，当前身家 ${fmtCoins(p.coins)}，还差 ${fmtCoins(cost - p.coins)}！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    p.coins -= cost;
    p.plots.push(null);
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🏡 扩地成功！花费 ${fmtCoins(cost)}，现有田地 ${p.plots.length} 块。\n剩余身家：${fmtCoins(p.coins)}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["扩地"] = cmd扩地;

// ========================
// .背包 — 查看物品
// ========================

let cmd背包 = seal.ext.newCmdItemInfo();
cmd背包.name = "背包";
cmd背包.help = "查看背包中的物品。用法：.背包";
cmd背包.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const bag = data[key].bag || {};
    const items = Object.entries(bag).filter(([, v]) => v > 0);

    if (items.length === 0) {
        seal.replyToSender(ctx, msg, `${ctx.player.name} 的背包空空如也！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 分类显示：种子 / 农产品 / 山货药材
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
// .身家 — 个人状态
// ========================

let cmd身家 = seal.ext.newCmdItemInfo();
cmd身家.name = "身家";
cmd身家.help = "查看财富和身份状态。用法：.身家";
cmd身家.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const key = pk(ctx);
    if (!data[key]) { seal.replyToSender(ctx, msg, "请先用【立业】开始游戏！"); return seal.ext.newCmdExecuteResult(true); }

    const p = data[key];
    const id = getIdentity(p.coins);
    const idIdx = IDENTITIES.indexOf(id);
    const nextId = IDENTITIES[idIdx + 1];
    const cdLeft = p.huntCd - now();

    const nextLine = nextId
        ? `下一身份：【${nextId.name}】，还差 ${fmtCoins(nextId.threshold - p.coins)}`
        : `已达最高身份，富甲天下！`;

    const readyPlots = p.plots.filter(pl => pl && pl.readyAt <= now()).length;
    const growingPlots = p.plots.filter(pl => pl && pl.readyAt > now()).length;

    seal.replyToSender(ctx, msg,
        `📜 ${ctx.player.name} 的状态\n` +
        `━━━━━━━━━━\n` +
        `身份：【${id.name}】\n` +
        `身家：${fmtCoins(p.coins)}\n` +
        `田地：${p.plots.length} 块` +
        (readyPlots ? `（${readyPlots} 块已成熟！）` : growingPlots ? `（${growingPlots} 块生长中）` : "") + "\n" +
        `上山：${cdLeft > 0 ? `冷却中（${fmtMs(cdLeft)}后可出发）` : "可以出发"}\n` +
        `━━━━━━━━━━\n` +
        nextLine
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["身家"] = cmd身家;
ext.cmdMap["状态"] = cmd身家;

// ========================
// .农商帮助
// ========================

let cmd帮助 = seal.ext.newCmdItemInfo();
cmd帮助.name = "农商帮助";
cmd帮助.help = "查看古代农商系统所有指令";
cmd帮助.solve = (ctx, msg, cmdArgs) => {
    seal.replyToSender(ctx, msg,
        `🌾 古代农商系统 · 指令列表\n` +
        `━━【基础】━━\n` +
        `【立业】创建角色，开始游戏\n` +
        `【身家】查看财富、身份、田地状态\n` +
        `【背包】查看持有物品\n` +
        `━━【耕种】━━\n` +
        `【种 作物名】在空地播种（需种子）\n` +
        `【收地】收获所有成熟作物\n` +
        `【田地】查看田地状态和倒计时\n` +
        `【扩地】花铜钱购买新田地\n` +
        `━━【买卖】━━\n` +
        `【集市】查看物价表\n` +
        `【买 种子名 数量】购买种子\n` +
        `【卖 物品名 数量】出售物品\n` +
        `【卖 物品名 全部】一键全卖\n` +
        `━━【山野】━━\n` +
        `【上山】打猎/采药（${seal.ext.getIntConfig(ext, "打猎冷却_分钟")}分钟冷却）\n` +
        `━━【身份晋升】━━\n` +
        IDENTITIES.map((id, i) =>
            i === 0 ? `初始：${id.name}` : `${fmtCoins(id.threshold)}：${id.name}`
        ).join(" → ")
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["农商帮助"] = cmd帮助;
