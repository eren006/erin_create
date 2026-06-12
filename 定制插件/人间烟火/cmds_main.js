// ============================================================
// 人间烟火 v3.0 — 主路由 + 剩余子命令
// ============================================================

// ── 立业 ──
function doInit(ctx, msg, cmdArgs, data, key) {
    cacheEp(ctx);
    if (data[key]) {
        const p = data[key];
        seal.replyToSender(ctx, msg,
            `${p.fullName || ctx.player.name} 早已在此扎根，无需重建。\n` +
            `身份：${getIdentity(p.coins).name}（${FAME[p.fame || 0].title}）| 身家：${fmtCoins(p.coins)}`
        );
        return;
    }

    const givenName = (cmdArgs.getArgN(2) || "").trim();
    if (!givenName) {
        seal.replyToSender(ctx, msg,
            `请告诉我你的名字！\n用法：.烟火 立业 [名字]\n例如：.烟火 立业 小明`
        );
        return;
    }
    if (givenName.length > 4) {
        seal.replyToSender(ctx, msg, "名字最多4个字！");
        return;
    }

    const surname    = pick(SURNAMES);
    const villageIdx = Math.floor(Math.random() * VILLAGES.length);
    const village    = VILLAGES[villageIdx];
    const fullName   = surname + givenName;

    data[key] = {
        coins: 50, plots: [null, null], huntCd: 0, stealCd: 0,
        nightRaidCd: 0, examCd: 0, shopCd: 0, helpDate: "",
        fame: 0, shops: {}, bag: { "菜种": 3 },
        signInDate: "", signInStreak: 0, freePlantDate: "",
        huntBuff: false, children: [], spouse: null, proposeFrom: null,
        surname, givenName, fullName, villageIdx,
        epPlat:  ctx.endPoint ? ctx.endPoint.platform : "",
        epBot:   ctx.endPoint ? ctx.endPoint.userId   : "",
        groupId: ctx.group ? ctx.group.groupId : "",
        userId: ctx.player.userId, userName: ctx.player.name,
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `📖【序章】\n` +
        `${fullName}拍了拍空瘪的钱袋，望向脚下这两亩薄田，长出一口气——\n` +
        `"总得从哪里开始。"\n\n` +
        `姓名：${fullName}\n` +
        `出身：${village.name}（${village.desc}）\n` +
        `村庄加成：${BONUS_DESC[village.bonus] || "无"}${Math.round(village.val * 100)}%\n\n` +
        `初始家当：50铜 · 田地×2 · 菜种×3\n` +
        `庄稼成熟时会@你提醒！\n` +
        `输入 .烟火 帮助 查看所有玩法`
    );
}

// ── 状态 ──
function doStatus(ctx, msg, p, gid) {
    const id      = getIdentity(p.coins);
    const idIdx   = IDENTITIES.indexOf(id);
    const nextId  = IDENTITIES[idIdx + 1];
    const fort    = getDailyFortune(ctx.player.userId);
    const daily   = getDailyData(gid);
    const bonus   = getAllBonuses(p, gid);
    const village = VILLAGES[p.villageIdx ?? 0];

    const huntLeft  = (p.huntCd   || 0) - now();
    const examLeft  = (p.examCd   || 0) - now();
    const shopLeft  = (p.shopCd   || 0) - now();
    const readyCnt  = p.plots.filter(pl => pl && pl.readyAt <= now()).length;
    const shopList  = Object.entries(p.shops || {}).filter(([, v]) => v > 0).map(([n, v]) => `${n}×${v}`);
    const children  = p.children || [];

    // 加成汇总（村庄 + 佳人）
    const bonusLines = [];
    if (bonus.crop)  bonusLines.push(`作物+${Math.round(bonus.crop * 100)}%`);
    if (bonus.sell)  bonusLines.push(`售价+${Math.round(bonus.sell * 100)}%`);
    if (bonus.shop)  bonusLines.push(`铺子+${Math.round(bonus.shop * 100)}%`);
    if (bonus.exam)  bonusLines.push(`科举+${Math.round(bonus.exam * 100)}%`);
    if (bonus.steal) bonusLines.push(`偷菜+${Math.round(bonus.steal * 100)}%`);
    if (bonus.anti)  bonusLines.push(`防盗+${Math.round(bonus.anti * 100)}%`);
    if (bonus.rare)  bonusLines.push(`稀有+${Math.round(bonus.rare * 100)}%`);
    if (bonus.hunt)  bonusLines.push(`打猎+${Math.round(bonus.hunt * 100)}%`);

    const lines = [
        `📜 ${p.fullName || ctx.player.name} 的发家档案`,
        `━━━━━━━━━━`,
        `身份：${id.name} | 功名：${FAME[p.fame || 0].title}`,
        `出身：${village.name}`,
        `身家：${fmtCoins(p.coins)}`,
        `今日运势：${fort.emoji}${fort.label}`,
        `田地：${p.plots.length}块${readyCnt ? `（${readyCnt}块已熟！）` : ""}`,
    ];
    if (shopList.length) lines.push(`铺子：${shopList.join("、")} | 收租：${shopLeft > 0 ? fmtMs(shopLeft) + "后" : "可收"}`);
    lines.push(`上山：${huntLeft > 0 ? fmtMs(huntLeft) + "后可出发" : "可出发"}`);
    if ((p.fame || 0) < FAME.length - 1) {
        const fl = FAME[p.fame || 0];
        lines.push(`科举：${examLeft > 0 ? fmtMs(examLeft) + "后可考" : `可参考（需${fmtCoins(fl.examCost)}，升${FAME[(p.fame||0)+1].title}）`}`);
    }
    if (p.spouse) lines.push(`配偶：${p.spouse.name}（${p.spouse.type === "npc" ? "佳人" : "玩家"}）`);
    if (children.length) lines.push(`子嗣：${children.map(c => c.name).join("、")}`);
    if (bonusLines.length) lines.push(`当前加成：${bonusLines.join(" | ")}`);
    lines.push(`━━━━━━━━━━`);
    lines.push(nextId ? `距【${nextId.name}】还差 ${fmtCoins(nextId.threshold - p.coins)}` : "富甲天下，已至巅峰！");

    // 今日事件提示
    if (daily.events.length) {
        lines.push(`\n今日事件：${daily.events.map(e => `${e.emoji}${e.name}`).join(" | ")}`);
    }
    seal.replyToSender(ctx, msg, lines.join("\n"));
}

// ── 背包 ──
function doBackpack(ctx, msg, p) {
    const bag = p.bag || {};
    const items = Object.entries(bag).filter(([, v]) => v > 0);
    if (!items.length) { seal.replyToSender(ctx, msg, `${p.fullName || ctx.player.name} 的背包空空如也！`); return; }

    const seeds = [], crops = [], hunts = [], special = [];
    for (const [name, count] of items) {
        if (SEED_MAP[name])             seeds.push(`${name}×${count}`);
        else if (CROPS[name])           crops.push(`${name}×${count}`);
        else if (SPECIAL_ITEMS[name])   special.push(`${name}×${count}`);
        else                            hunts.push(`${name}×${count}`);
    }
    const lines = [];
    if (seeds.length)   lines.push(`【种子】${seeds.join("、")}`);
    if (crops.length)   lines.push(`【农产】${crops.join("、")}`);
    if (hunts.length)   lines.push(`【山货】${hunts.join("、")}`);
    if (special.length) lines.push(`【特殊】${special.join("、")}`);
    seal.replyToSender(ctx, msg, `🎒 ${p.fullName || ctx.player.name} 的背包：\n${lines.join("\n")}`);
}

// ── 天气 ──
function doWeather(ctx, msg, gid, p) {
    const daily = getDailyData(gid);
    const w = daily.weather;
    const tierLines = [];
    // 只显示玩家已解锁的推荐作物
    const recUnlocked = (daily.rec || []).filter(c =>
        CROPS[c] && p.coins >= CROPS[c].reqW && (p.fame || 0) >= CROPS[c].reqF
    );
    const recLocked = (daily.rec || []).filter(c =>
        CROPS[c] && (p.coins < CROPS[c].reqW || (p.fame || 0) < CROPS[c].reqF)
    );

    let reply = `${w.emoji} 今日天气：${w.name}\n"${w.desc}"\n\n`;
    reply += `作物收成：×${w.cropMod.toFixed(2)} | 打猎：×${w.huntMod.toFixed(2)} | 药材：×${w.herbMod.toFixed(2)}\n`;
    reply += `\n今日适合种植：${recUnlocked.length ? recUnlocked.join("、") : "（已解锁作物无特别推荐）"}`;
    if (recLocked.length) reply += `\n（未解锁推荐：${recLocked.join("、")}）`;
    if (daily.events.length) {
        reply += `\n\n今日事件：\n` + daily.events.map(e => `${e.emoji}【${e.name}】${e.desc}`).join("\n");
    }
    seal.replyToSender(ctx, msg, reply);
}

// ── 每日事件 ──
function doEvents(ctx, msg, gid) {
    const daily = getDailyData(gid);
    if (!daily.events.length) { seal.replyToSender(ctx, msg, "今日无特殊事件，平平安安。"); return; }
    const lines = daily.events.map(e => `${e.emoji}【${e.name}】\n${e.desc}`);
    seal.replyToSender(ctx, msg, `📰 今日事件（共${daily.events.length}个）：\n\n${lines.join("\n\n")}`);
}

// ── 运势 ──
function doFortune(ctx, msg) {
    const f = getDailyFortune(ctx.player.userId);
    seal.replyToSender(ctx, msg,
        `${f.emoji}【今日运势：${f.label}】\n"${f.poem}"\n\n` +
        `出售价格 ×${f.sellM.toFixed(2)} | 偷菜成功 ×${f.stealM.toFixed(2)} | 作物收获 ×${f.cropM.toFixed(2)}\n` +
        `（运势每日一换，${ctx.player.name}明日自会不同）`
    );
}

// ── 村子信息 ──
function doVillage(ctx, msg, p, gid) {
    const village = VILLAGES[p.villageIdx ?? 0];
    // 统计群内同村人数
    const data = getData();
    const villagers = Object.values(data).filter(
        v => v.groupId === ctx.group.groupId && v.villageIdx === p.villageIdx && v.userId !== ctx.player.userId
    );
    const names = villagers.slice(0, 5).map(v => v.fullName || v.userName);

    seal.replyToSender(ctx, msg,
        `🏘️ ${p.fullName || ctx.player.name} 的出身地\n` +
        `━━━━━━\n` +
        `【${village.name}】\n${village.desc}\n\n` +
        `村庄加成：${BONUS_DESC[village.bonus] || "无"}${Math.round(village.val * 100)}%\n` +
        `群内同村人：${names.length ? names.join("、") + (villagers.length > 5 ? `等${villagers.length}人` : "") : "暂无"}\n` +
        `（村庄随机分配，永久固定，无法更改）`
    );
}

// ── 帮助 ──
function doHelp(ctx, msg, p) {
    const fame = p ? (p.fame || 0) : 0;
    seal.replyToSender(ctx, msg,
        `🌾【人间烟火】全指令一览\n` +
        `━━【每日必做】━━\n` +
        `  签到 / 天气 / 事件 / 运势\n` +
        `━━【田地种植】━━\n` +
        `  种 [作物] / 收 / 田地 / 扩地\n` +
        `  （成熟自动@提醒｜天气影响收成）\n` +
        `━━【山野】━━\n` +
        `  上山 / 偷 @目标 / 夜袭\n` +
        `━━【买卖】━━\n` +
        `  集市 / 买 [种子] [数量] / 卖 [物品] [数量/全部]\n` +
        `━━【仕途】━━\n` +
        `  科举 / 开铺 [铺名] / 铺子 / 收租\n` +
        `━━【佳人】━━\n` +
        `  花名册 [男/女/空闲/页码] / 佳人 [姓名]\n` +
        `  追求 [姓名] / 放手 [姓名]\n` +
        `━━【婚育】━━\n` +
        `  求婚 @目标 / 迎娶 [佳人名]\n` +
        `  答应 / 拒绝 / 离婚 / 帮忙\n` +
        `  孩子 / 教导 [孩子名] / 差遣 [孩子名] [任务]\n` +
        `━━【其他】━━\n` +
        `  状态 / 背包 / 村子\n` +
        `━━【作物解锁】━━\n` +
        `  初阶：无需条件 | 中阶：小农+秀才\n` +
        `  进阶：富农+举人 | 高阶：小商人+进士 | 仙阶：大商人+状元`
    );
}

// ============================================================
// 主指令路由
// ============================================================
let cmdMain = seal.ext.newCmdItemInfo();
cmdMain.name = "烟火";
cmdMain.help = "人间烟火系统。输入 .烟火 帮助 查看所有指令。";

cmdMain.solve = (ctx, msg, cmdArgs) => {
    const sub  = (cmdArgs.getArgN(1) || "").trim();
    const gid  = ctx.group ? ctx.group.groupId : "";

    // ── 不需要立业的指令 ──
    if (!sub || sub === "帮助" || sub === "help") {
        const data = getData();
        doHelp(ctx, msg, data[pk(ctx)]);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (sub === "立业" || sub === "开始") {
        const data = getData();
        doInit(ctx, msg, cmdArgs, data, pk(ctx));
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 需要立业的指令 ──
    const data = ensurePlayer(ctx);
    const key  = pk(ctx);
    if (!data[key]) {
        seal.replyToSender(ctx, msg, "请先输入 .烟火 立业 [名字] 开始游戏！");
        return seal.ext.newCmdExecuteResult(true);
    }
    const p     = data[key];
    const daily = getDailyData(gid);
    const fort  = getDailyFortune(ctx.player.userId);
    const bonus = getAllBonuses(p, gid);

    switch (sub) {
        // 每日
        case "签到":                 doSignIn(ctx, msg, data, key); break;
        case "天气":                 doWeather(ctx, msg, gid, p); break;
        case "事件": case "每日事件": doEvents(ctx, msg, gid); break;
        case "运势": case "天命":    doFortune(ctx, msg); break;

        // 信息
        case "状态": case "身家":    doStatus(ctx, msg, p, gid); break;
        case "背包": case "仓库":    doBackpack(ctx, msg, p); break;
        case "村子": case "出身":    doVillage(ctx, msg, p, gid); break;

        // 种地
        case "种": case "种地":      doPlant(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus); break;
        case "收": case "收地":      doHarvest(ctx, msg, data, key, p, daily, fort, bonus); break;
        case "田": case "田地":      doViewFarm(ctx, msg, p, daily); break;
        case "扩地": case "买地":    doExpandFarm(ctx, msg, data, key, p); break;

        // 山野
        case "上山": case "打猎":    doHunt(ctx, msg, data, key, p, daily, fort, bonus); break;
        case "偷":  case "偷菜":     doSteal(ctx, msg, data, key, p, daily, fort, bonus); break;
        case "夜袭":                 doNightRaid(ctx, msg, data, key, p, daily, fort, bonus); break;

        // 买卖
        case "集市": case "市":      doMarket(ctx, msg, p, daily); break;
        case "买":  case "购买":     doBuy(ctx, msg, cmdArgs, data, key, p, daily); break;
        case "卖":  case "出售":     doSell(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus); break;

        // 科举 & 铺子
        case "科举": case "考试":    doExam(ctx, msg, data, key, p, fort, bonus); break;
        case "开铺":                 doOpenShop(ctx, msg, cmdArgs, data, key, p); break;
        case "铺子": case "我的铺子":doViewShops(ctx, msg, p); break;
        case "收租": case "租":      doCollectRent(ctx, msg, data, key, p, bonus); break;

        // 佳人
        case "花名册": case "册":    doCharList(ctx, msg, cmdArgs, p, gid); break;
        case "佳人": case "我的佳人":doCharDetail(ctx, msg, cmdArgs, gid); break;
        case "追求": case "争抢":    doPursue(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "放手": case "放弃":    doRelease(ctx, msg, cmdArgs, data, key, p, gid); break;

        // 婚育
        case "迎娶":                 doMarryNPC(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "求婚":                 doProposePlayer(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "答应":                 doAccept(ctx, msg, data, key, p, gid); break;
        case "拒绝":                 doReject(ctx, msg, data, key, p); break;
        case "离婚":                 doDivorce(ctx, msg, data, key, p, gid); break;
        case "帮忙": case "帮帮":    doSpouseHelp(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "孩子": case "子嗣":    doViewChildren(ctx, msg, p); break;
        case "教导":                 doTeachChild(ctx, msg, cmdArgs, data, key, p); break;
        case "差遣":                 doDispatchChild(ctx, msg, cmdArgs, data, key, p, bonus); break;

        default:
            seal.replyToSender(ctx, msg, `不认识"${sub}"，输入 .烟火 帮助 查看所有指令。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["烟火"] = cmdMain;
