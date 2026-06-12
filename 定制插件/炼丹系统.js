// ==UserScript==
// @name         炼丹系统
// @author       长日将尽
// @version      1.0.0
// @description  修仙炼丹主题的种菜偷菜玩法：开炉炼丹、采收丹药、盗丹博弈
// @timestamp    1748563200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

// ========================
// 初始化
// ========================

let ext = seal.ext.find("alchemy_system");
if (!ext) {
    ext = seal.ext.new("alchemy_system", "长日将尽", "1.0.0");

    // 配置项
    seal.ext.registerIntConfig(ext, "炼丹时长_小时", 8);       // 默认8小时
    seal.ext.registerIntConfig(ext, "盗丹冷却_分钟", 60);      // 盗丹冷却时间
    seal.ext.registerIntConfig(ext, "盗丹成功率_百分比", 50);   // 基础成功率

    seal.ext.register(ext);
}

// ========================
// 数据存取
// ========================

function getData() {
    try { return JSON.parse(ext.storageGet("alchemy_data") || "{}"); }
    catch { return {}; }
}
function saveData(d) { ext.storageSet("alchemy_data", JSON.stringify(d)); }

function playerKey(ctx) {
    return `${ctx.group.groupId}|${ctx.player.userId}`;
}
function bagKey(pkey) { return `${pkey}|bag`; }
function cdKey(pkey)  { return `${pkey}|stealcd`; }

function nowMs() { return Date.now(); }

function fmtMs(ms) {
    if (ms <= 0) return "不到1分钟";
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    if (h > 0 && m > 0) return `${h}小时${m}分钟`;
    if (h > 0) return `${h}小时`;
    return `${m}分钟`;
}

// ========================
// 丹药表
// ========================

// weight 为权重，越小越稀有
const PILL_TABLE = [
    { name: "回气丹",   min: 1,  max: 3,  weight: 50 },
    { name: "固元丹",   min: 2,  max: 5,  weight: 28 },
    { name: "化血丹",   min: 3,  max: 7,  weight: 15 },
    { name: "大还丹",   min: 5,  max: 12, weight: 6  },
    { name: "九转金丹", min: 15, max: 30, weight: 1  },
];

function rollPill() {
    const total = PILL_TABLE.reduce((s, p) => s + p.weight, 0);
    let r = Math.random() * total;
    for (const p of PILL_TABLE) {
        r -= p.weight;
        if (r <= 0) {
            const count = p.min + Math.floor(Math.random() * (p.max - p.min + 1));
            return { name: p.name, count };
        }
    }
    const p = PILL_TABLE[0];
    return { name: p.name, count: p.min };
}

function pillRarityLabel(name) {
    const idx = PILL_TABLE.findIndex(p => p.name === name);
    return ["★☆☆☆☆", "★★☆☆☆", "★★★☆☆", "★★★★☆", "★★★★★"][idx] || "☆☆☆☆☆";
}

// ========================
// 指令：炼丹
// ========================

let cmd炼丹 = seal.ext.newCmdItemInfo();
cmd炼丹.name = "炼丹";
cmd炼丹.help = "开始炼制丹药，等待出炉后采收。用法：.炼丹";
cmd炼丹.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const pkey = playerKey(ctx);
    const fur = data[pkey];
    const brewMs = seal.ext.getIntConfig(ext, "炼丹时长_小时") * 3600000;

    if (fur && fur.brewing) {
        const left = fur.readyAt - nowMs();
        if (left > 0) {
            seal.replyToSender(ctx, msg,
                `🔥 炼丹炉正在运转中！\n` +
                `正在炼制：【${fur.pill.name}】\n` +
                `距出炉还需：${fmtMs(left)}\n` +
                `（提示：丹炉运转时有被盗丹风险）`
            );
            return seal.ext.newCmdExecuteResult(true);
        }
        // 已炼成但未采
        seal.replyToSender(ctx, msg,
            `✅ 【${fur.pill.name}】已炼成，还在炉内等待采收！\n请先用【采丹】取出，再重新开炉。`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const pill = rollPill();
    data[pkey] = {
        brewing: true,
        pill,
        startAt: nowMs(),
        readyAt: nowMs() + brewMs,
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `🔥 ${ctx.player.name} 点燃炼丹炉，开始炼制！\n` +
        `本次炼制：【${pill.name}】${pillRarityLabel(pill.name)}\n` +
        `预计出炉：${fmtMs(brewMs)} 后\n` +
        `————————\n` +
        `丹炉运转期间，小心他人盗丹…`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["炼丹"] = cmd炼丹;

// ========================
// 指令：采丹
// ========================

let cmd采丹 = seal.ext.newCmdItemInfo();
cmd采丹.name = "采丹";
cmd采丹.help = "采收已炼制完成的丹药。用法：.采丹";
cmd采丹.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const pkey = playerKey(ctx);
    const fur = data[pkey];

    if (!fur || !fur.brewing) {
        seal.replyToSender(ctx, msg, `你的炼丹炉是空的，先用【炼丹】开始炼制吧！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const left = fur.readyAt - nowMs();
    if (left > 0) {
        seal.replyToSender(ctx, msg,
            `🔥 丹药尚未炼成，还需 ${fmtMs(left)}，请勿心急！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const pill = fur.pill;
    const bkey = bagKey(pkey);
    const bag = data[bkey] || {};
    bag[pill.name] = (bag[pill.name] || 0) + pill.count;
    data[bkey] = bag;
    data[pkey] = { brewing: false };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `✨ 采丹成功！\n` +
        `${ctx.player.name} 收获了 ${pill.count} 颗【${pill.name}】${pillRarityLabel(pill.name)}\n` +
        `炼丹炉已清空，可重新开始炼制。`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["采丹"] = cmd采丹;

// ========================
// 指令：炉况
// ========================

let cmd炉况 = seal.ext.newCmdItemInfo();
cmd炉况.name = "炉况";
cmd炉况.help = "查看自己炼丹炉的进度。用法：.炉况";
cmd炉况.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const pkey = playerKey(ctx);
    const fur = data[pkey];
    const brewMs = seal.ext.getIntConfig(ext, "炼丹时长_小时") * 3600000;

    if (!fur || !fur.brewing) {
        seal.replyToSender(ctx, msg,
            `${ctx.player.name} 的炼丹炉空空如也，用【炼丹】开始炼制！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const left = fur.readyAt - nowMs();
    if (left <= 0) {
        seal.replyToSender(ctx, msg,
            `✅ 【${fur.pill.name}】已炼成，正在炉中等待！\n快用【采丹】取出吧！`
        );
    } else {
        const elapsed = brewMs - left;
        const pct = Math.min(100, Math.floor(elapsed / brewMs * 100));
        const filled = Math.floor(pct / 10);
        const bar = "█".repeat(filled) + "░".repeat(10 - filled);
        seal.replyToSender(ctx, msg,
            `🔥 ${ctx.player.name} 的炼丹炉运转中\n` +
            `炼制中：【${fur.pill.name}】${pillRarityLabel(fur.pill.name)}\n` +
            `进度：[${bar}] ${pct}%\n` +
            `剩余：${fmtMs(left)}`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["炉况"] = cmd炉况;

// ========================
// 指令：盗丹
// ========================

let cmd盗丹 = seal.ext.newCmdItemInfo();
cmd盗丹.name = "盗丹";
cmd盗丹.help = "盗取他人炼丹炉中的丹药（炉外无效）。用法：.盗丹 @目标";
cmd盗丹.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const thiefPkey = playerKey(ctx);
    const cdMs = seal.ext.getIntConfig(ext, "盗丹冷却_分钟") * 60000;
    const baseRate = seal.ext.getIntConfig(ext, "盗丹成功率_百分比");

    // 冷却检查
    const cd = data[cdKey(thiefPkey)] || 0;
    const cdLeft = cd - nowMs();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg,
            `盗丹术尚在冷却中！\n还需 ${fmtMs(cdLeft)} 方可再次行动。`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    // 解析目标
    const atList = msg.atUsersId || [];
    if (atList.length === 0) {
        seal.replyToSender(ctx, msg, `请@一个目标！用法：.盗丹 @某人`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetUserId = atList[0];
    if (targetUserId === ctx.player.userId) {
        seal.replyToSender(ctx, msg, `不能盗取自己的丹药！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetPkey = `${ctx.group.groupId}|${targetUserId}`;
    const targetFur = data[targetPkey];

    if (!targetFur || !targetFur.brewing) {
        seal.replyToSender(ctx, msg, `对方炼丹炉是空的，没有可盗之物！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (targetFur.readyAt - nowMs() <= 0) {
        seal.replyToSender(ctx, msg,
            `对方的丹药已炼成出炉，盗丹只在炼制过程中有效！`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    // 设置冷却（不管成败都触发）
    data[cdKey(thiefPkey)] = nowMs() + cdMs;

    // 盗丹判定
    const roll = Math.floor(Math.random() * 100) + 1;
    const success = roll <= baseRate;

    if (success) {
        const pill = targetFur.pill;
        const stolenCount = Math.max(1, Math.floor(pill.count / 2));
        pill.count -= stolenCount;

        const thiefBkey = bagKey(thiefPkey);
        const thiefBag = data[thiefBkey] || {};
        thiefBag[pill.name] = (thiefBag[pill.name] || 0) + stolenCount;
        data[thiefBkey] = thiefBag;

        if (pill.count <= 0) {
            // 炉内被洗劫一空
            data[targetPkey] = { brewing: false };
            seal.replyToSender(ctx, msg,
                `🎊 盗丹大成！（掷骰 d100=${roll}，需≤${baseRate}）\n` +
                `${ctx.player.name} 神不知鬼不觉地潜入对方炼丹炉，\n` +
                `将炉内 ${stolenCount} 颗【${pill.name}】洗劫一空！\n` +
                `（炉内已空，对方炼丹炉熄灭）`
            );
        } else {
            data[targetPkey].pill = pill;
            seal.replyToSender(ctx, msg,
                `🎊 盗丹成功！（掷骰 d100=${roll}，需≤${baseRate}）\n` +
                `${ctx.player.name} 悄悄潜入对方炼丹炉，\n` +
                `盗走了 ${stolenCount} 颗【${pill.name}】！\n` +
                `（对方炉内仍剩 ${pill.count} 颗）`
            );
        }
    } else {
        seal.replyToSender(ctx, msg,
            `💥 盗丹失败！（掷骰 d100=${roll}，需≤${baseRate}）\n` +
            `${ctx.player.name} 触发了护炉禁制，被震飞而出！\n` +
            `冷却 ${fmtMs(cdMs)} 后方可再次出手。`
        );
    }

    saveData(data);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["盗丹"] = cmd盗丹;

// ========================
// 指令：丹库
// ========================

let cmd丹库 = seal.ext.newCmdItemInfo();
cmd丹库.name = "丹库";
cmd丹库.help = "查看自己持有的丹药。用法：.丹库";
cmd丹库.solve = (ctx, msg, cmdArgs) => {
    const data = getData();
    const bkey = bagKey(playerKey(ctx));
    const bag = data[bkey] || {};
    const items = Object.entries(bag).filter(([, v]) => v > 0);

    if (items.length === 0) {
        seal.replyToSender(ctx, msg, `📦 ${ctx.player.name} 的丹库空空如也！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 按稀有度排序（稀有度高的在前）
    items.sort((a, b) => {
        const ia = PILL_TABLE.findIndex(p => p.name === a[0]);
        const ib = PILL_TABLE.findIndex(p => p.name === b[0]);
        return ib - ia;
    });

    const total = items.reduce((s, [, v]) => s + v, 0);
    const list = items.map(([name, count]) =>
        `${pillRarityLabel(name)} 【${name}】×${count}`
    ).join("\n");

    seal.replyToSender(ctx, msg,
        `📦 ${ctx.player.name} 的丹库（共 ${total} 颗）：\n${list}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["丹库"] = cmd丹库;

// ========================
// 指令：炼丹帮助
// ========================

let cmd炼丹帮助 = seal.ext.newCmdItemInfo();
cmd炼丹帮助.name = "炼丹帮助";
cmd炼丹帮助.help = "查看炼丹系统全部指令";
cmd炼丹帮助.solve = (ctx, msg, cmdArgs) => {
    const brewH = seal.ext.getIntConfig(ext, "炼丹时长_小时");
    const cdMin = seal.ext.getIntConfig(ext, "盗丹冷却_分钟");
    const rate = seal.ext.getIntConfig(ext, "盗丹成功率_百分比");

    seal.replyToSender(ctx, msg,
        `🧪 炼丹系统指令列表\n` +
        `————————\n` +
        `【炼丹】开始炼制丹药（${brewH}小时出炉）\n` +
        `【采丹】采收已炼成的丹药\n` +
        `【炉况】查看炼丹进度条\n` +
        `【丹库】查看持有的丹药\n` +
        `【盗丹 @目标】尝试盗取他人炉内丹药\n` +
        `  ↳ 成功率 ${rate}%，冷却 ${cdMin} 分钟（成败皆触发）\n` +
        `  ↳ 仅可盗取炼制中（未出炉）的丹药\n` +
        `  ↳ 成功偷走炉内丹药的一半\n` +
        `————————\n` +
        `丹药品质（由低到高）：\n` +
        PILL_TABLE.map(p => `${pillRarityLabel(p.name)} ${p.name}`).join(" < ")
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["炼丹帮助"] = cmd炼丹帮助;
