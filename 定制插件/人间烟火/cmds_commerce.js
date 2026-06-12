// ============================================================
// 人间烟火 v3.0 — 指令处理：集市 / 科举 / 铺子 / 佳人
// ============================================================

// ── 集市 ──
function doMarket(ctx, msg, p, daily) {
    // 只显示玩家已解锁的种子
    const unlockedSeeds = Object.entries(CROPS)
        .filter(([, c]) => p.coins >= c.reqW && (p.fame || 0) >= c.reqF)
        .map(([name, c]) => {
            const disc = hasEvent(daily, "seed_disc") ? Math.round(c.cost * getEvent(daily, "seed_disc").val) : c.cost;
            const discStr = disc !== c.cost ? `~~${fmtCoins(c.cost)}~~ → ${fmtCoins(disc)}` : fmtCoins(c.cost);
            return `  ${c.seed} ${discStr}/个 → 种${name}（${c.h}h，售${fmtCoins(c.minP)}~${fmtCoins(c.maxP)}）`;
        });

    const huntLines = HUNT_TABLE.filter(h => h.name).map(h =>
        `  ${h.name}：${fmtCoins(h.minP)}~${fmtCoins(h.maxP)}/个`
    );

    const specialLines = Object.entries(SPECIAL_ITEMS).map(([name, s]) =>
        `  ${name}：${fmtCoins(s.minP)}~${fmtCoins(s.maxP)}/个`
    );

    const evtStr = daily.events.length
        ? daily.events.map(e => `${e.emoji}${e.name}`).join(" | ")
        : "（今日无特殊事件）";

    seal.replyToSender(ctx, msg,
        `🏪 今日集市（物价浮动）\n今日事件：${evtStr}\n` +
        `━━【种子】━━\n${unlockedSeeds.join("\n") || "  （暂无可购种子）"}\n` +
        `━━【收购·山货】━━\n${huntLines.join("\n")}\n` +
        `━━【收购·特殊】━━\n${specialLines.join("\n")}\n` +
        `.烟火 买 [种子] [数量] | .烟火 卖 [物品] [数量/全部]`
    );
}

// ── 购买种子 ──
function doBuy(ctx, msg, cmdArgs, data, key, p, daily) {
    const itemName = (cmdArgs.getArgN(2) || "").trim();
    const countArg = (cmdArgs.getArgN(3) || "1").trim();
    if (!itemName) {
        const list = Object.entries(CROPS)
            .filter(([, c]) => p.coins >= c.reqW && (p.fame || 0) >= c.reqF)
            .map(([, c]) => c.seed).join("、");
        seal.replyToSender(ctx, msg, `已解锁种子：${list || "（无）"}\n用法：.烟火 买 菜种 5`);
        return;
    }
    const cropName = SEED_MAP[itemName];
    if (!cropName) { seal.replyToSender(ctx, msg, `"${itemName}"不是种子！`); return; }
    const check = canPlantCrop(p, cropName);
    if (!check.ok) { seal.replyToSender(ctx, msg, `种子未解锁：${check.reason}`); return; }

    const count = Math.max(1, parseInt(countArg) || 1);
    const crop = CROPS[cropName];
    const disc = hasEvent(daily, "seed_disc") ? getEvent(daily, "seed_disc").val : 1;
    const unitCost = Math.round(crop.cost * disc);
    const total = unitCost * count;
    if (p.coins < total) { seal.replyToSender(ctx, msg, `需要 ${fmtCoins(total)}，持有 ${fmtCoins(p.coins)}，差 ${fmtCoins(total - p.coins)}`); return; }

    p.coins -= total;
    p.bag[itemName] = (p.bag[itemName] || 0) + count;
    saveData(data);
    const discHint = disc < 1 ? "（大集打折！）" : "";
    seal.replyToSender(ctx, msg, `🛒 买入 ${itemName}×${count}，花费 ${fmtCoins(total)}${discHint}，剩余 ${fmtCoins(p.coins)}`);
}

// ── 出售 ──
function doSell(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus) {
    const itemName = (cmdArgs.getArgN(2) || "").trim();
    const countArg = (cmdArgs.getArgN(3) || "").trim();
    if (!itemName) { seal.replyToSender(ctx, msg, "用法：.烟火 卖 [物品] [数量/全部]\n先用 .烟火 背包 查看持有物品。"); return; }

    const have = p.bag[itemName] || 0;
    if (!have) { seal.replyToSender(ctx, msg, `背包里没有【${itemName}】！`); return; }
    const sellCount = countArg === "全部" ? have : Math.min(parseInt(countArg) || 1, have);
    if (sellCount <= 0) { seal.replyToSender(ctx, msg, "数量有误！"); return; }

    // 查单价
    let unitPrice = 0;
    const cr = CROPS[itemName];
    if (cr) unitPrice = rand(cr.minP, cr.maxP);
    else {
        const ht = HUNT_TABLE.find(h => h.name === itemName);
        if (ht) unitPrice = rand(ht.minP, ht.maxP);
        else {
            const sp = SPECIAL_ITEMS[itemName];
            if (sp) unitPrice = rand(sp.minP, sp.maxP);
        }
    }
    if (!unitPrice) { seal.replyToSender(ctx, msg, `【${itemName}】无法在集市出售！`); return; }

    const sellMod = rollSellMod(fort, daily, itemName) * (1 + (bonus.sell || 0));
    const finalUnit = Math.round(unitPrice * sellMod);
    const total = finalUnit * sellCount;
    const coinsBefore = p.coins;

    p.bag[itemName] = have - sellCount;
    if (!p.bag[itemName]) delete p.bag[itemName];
    p.coins += total;

    const idBefore = getIdentity(coinsBefore);
    const idAfter  = getIdentity(p.coins);
    saveData(data);

    let reply = `💰 【${itemName}】×${sellCount}，今日单价 ${fmtCoins(finalUnit)}，共得 ${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}`;
    if (idAfter.name !== idBefore.name) {
        reply += `\n\n🎉 身份晋升为【${idAfter.name}】！`;
        const ni = IDENTITIES[IDENTITIES.indexOf(idAfter) + 1];
        if (ni) reply += `\n距【${ni.name}】还差 ${fmtCoins(ni.threshold - p.coins)}`;
    }
    seal.replyToSender(ctx, msg, reply);
}

// ── 科举 ──
function doExam(ctx, msg, data, key, p, fort, bonus) {
    const fame = p.fame || 0;
    if (fame >= FAME.length - 1) { seal.replyToSender(ctx, msg, "已是【状元】，科举之路已至极峰！"); return; }
    const lv = FAME[fame];
    const cdLeft = (p.examCd || 0) - now();
    if (cdLeft > 0) { seal.replyToSender(ctx, msg, `上次考试后还需休整，${fmtMs(cdLeft)} 后再考！`); return; }
    if (p.coins < lv.examCost) { seal.replyToSender(ctx, msg, `参考需盘缠 ${fmtCoins(lv.examCost)}，还差 ${fmtCoins(lv.examCost - p.coins)}！`); return; }

    p.coins -= lv.examCost;
    p.examCd = now() + lv.cdH * 3600000;
    const rate = Math.min(0.95, lv.examRate + (bonus.exam || 0));
    const success = Math.random() <= rate;

    if (success) {
        p.fame = fame + 1;
        saveData(data);
        const nextTitle = FAME[fame + 1].title;
        const f = ["金榜题名，鞭炮声中，邻里皆来道贺！","看榜时心如擂鼓，找到自己名字，泪水不争气地流了下来。","先生说：十年寒窗苦，今日终有报。"];
        let reply = `📜【科举揭榜】金榜有名！\n${ctx.player.name} 一举高中【${nextTitle}】！\n${pick(f)}`;
        // 解锁提示
        const su = Object.entries(SHOPS).find(([, s]) => s.req === p.fame);
        if (su) reply += `\n🎊 已解锁铺子：【${su[0]}】（.烟火 开铺 ${su[0]}）`;
        // 解锁作物提示
        const newCrops = Object.keys(CROPS).filter(c => CROPS[c].reqF === p.fame);
        if (newCrops.length) reply += `\n🌱 已解锁新作物：${newCrops.join("、")}（还需达到对应财富）`;
        seal.replyToSender(ctx, msg, reply);
    } else {
        saveData(data);
        const f = ["答到一半手心发抖，出了考场才知道写错了。","文章洋洋洒洒，偏偏偏了题意，名落孙山。","主考官看了半天，摇头，落笔打了个叉。"];
        seal.replyToSender(ctx, msg, `📜【科举揭榜】榜上无名。\n${pick(f)}\n花费盘缠 ${fmtCoins(lv.examCost)}，${fmtMs(lv.cdH * 3600000)} 后可再考。`);
    }
}

// ── 开铺 ──
function doOpenShop(ctx, msg, cmdArgs, data, key, p) {
    const shopName = (cmdArgs.getArgN(2) || "").trim();
    if (!shopName) {
        const list = Object.entries(SHOPS).map(([n, s]) =>
            `  ${n}：需${FAME[s.req].title}+${fmtCoins(s.cost)}，每${seal.ext.getIntConfig(ext,"收租间隔_小时")}h收${fmtCoins(s.minI)}~${fmtCoins(s.maxI)}`
        );
        seal.replyToSender(ctx, msg, `可开铺子：\n${list.join("\n")}\n用法：.烟火 开铺 小铺子`);
        return;
    }
    const shop = SHOPS[shopName];
    if (!shop) { seal.replyToSender(ctx, msg, `不认识"${shopName}"，可开：${Object.keys(SHOPS).join("、")}`); return; }
    if ((p.fame || 0) < shop.req) { seal.replyToSender(ctx, msg, `开${shopName}需【${FAME[shop.req].title}】以上，当前【${FAME[p.fame || 0].title}】！`); return; }
    if (!p.shops) p.shops = {};
    if ((p.shops[shopName] || 0) >= 3) { seal.replyToSender(ctx, msg, `${shopName}最多开3家！`); return; }
    if (p.coins < shop.cost) { seal.replyToSender(ctx, msg, `开${shopName}需 ${fmtCoins(shop.cost)}，还差 ${fmtCoins(shop.cost - p.coins)}！`); return; }
    p.coins -= shop.cost;
    p.shops[shopName] = (p.shops[shopName] || 0) + 1;
    saveData(data);
    seal.replyToSender(ctx, msg, `🏪 ${shopName}开张大吉！花费 ${fmtCoins(shop.cost)}，现有 ${p.shops[shopName]} 家。每${seal.ext.getIntConfig(ext,"收租间隔_小时")}h可 .烟火 收租！`);
}

// ── 查看铺子 ──
function doViewShops(ctx, msg, p) {
    const owned = Object.entries(p.shops || {}).filter(([, v]) => v > 0);
    if (!owned.length) { seal.replyToSender(ctx, msg, "还没有铺子！先 .烟火 科举 获取功名再 .烟火 开铺。"); return; }
    const itvH = seal.ext.getIntConfig(ext, "收租间隔_小时");
    const cdLeft = (p.shopCd || 0) - now();
    const lines = owned.map(([n, c]) => { const s = SHOPS[n]; return `  ${n}×${c}，每次 ${fmtCoins(s.minI * c)}~${fmtCoins(s.maxI * c)}`; });
    seal.replyToSender(ctx, msg,
        `🏪 ${ctx.player.name} 的铺子：\n${lines.join("\n")}\n` +
        `下次收租：${cdLeft > 0 ? fmtMs(cdLeft) + "后" : "现在可收（.烟火 收租）"}`
    );
}

// ── 收租 ──
function doCollectRent(ctx, msg, data, key, p, bonus) {
    const owned = Object.entries(p.shops || {}).filter(([, v]) => v > 0);
    if (!owned.length) { seal.replyToSender(ctx, msg, "没有铺子！先 .烟火 开铺 开设。"); return; }
    const itvMs = seal.ext.getIntConfig(ext, "收租间隔_小时") * 3600000;
    const cdLeft = (p.shopCd || 0) - now();
    if (cdLeft > 0) { seal.replyToSender(ctx, msg, `账房说账还没结好，${fmtMs(cdLeft)} 后再来！`); return; }
    const shopBonus = 1 + (bonus.shop || 0);
    let total = 0; const details = [];
    for (const [n, c] of owned) {
        const s = SHOPS[n];
        const inc = Math.round(rand(s.minI, s.maxI) * c * shopBonus);
        total += inc; details.push(`${n}×${c}：${fmtCoins(inc)}`);
    }
    p.coins += total; p.shopCd = now() + itvMs;
    saveData(data);
    seal.replyToSender(ctx, msg, `💼 账房送来了账册——\n${details.join("\n")}\n合计入账：${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}\n下次收租：${fmtMs(itvMs)} 后`);
}

// ── 花名册 ──
function doCharList(ctx, msg, cmdArgs, p, gid) {
    const ad = getAttrInit(gid);
    const filter = (cmdArgs.getArgN(2) || "").trim();
    let chars = CHARS.map(([name, price, gender, desc, bt, bv]) => ({
        name, price, gender, desc, bt, bv, ...ad[name]
    }));
    if (filter === "男") chars = chars.filter(c => c.gender === "m");
    else if (filter === "女") chars = chars.filter(c => c.gender === "f");
    else if (filter === "空闲") chars = chars.filter(c => !c.owner);
    else if (filter === "我的") chars = chars.filter(c => c.owner === ctx.player.userId);

    const pageSize = 10;
    const pageNum  = parseInt(filter) || 1;
    const total    = Math.ceil(chars.length / pageSize);
    const page     = isNaN(parseInt(filter)) ? 1 : Math.max(1, Math.min(pageNum, total));
    const paged    = chars.slice((page - 1) * pageSize, page * pageSize);

    const lines = paged.map(c => {
        const bn = c.bt ? `[${BONUS_DESC[c.bt]}${Math.round(c.bv * 100)}%]` : "";
        const own = c.owner
            ? `（归 ${c.ownerName}${c.married ? "·已婚" : ""}，出价 ${fmtCoins(Math.ceil(c.price * (c.married ? 3 : 1.5)))} 争抢）`
            : `（无主，${fmtCoins(c.price)}）`;
        return `【${c.name}】${bn}${own}`;
    });
    seal.replyToSender(ctx, msg,
        `💐 花名册（${page}/${total}页，共50人）\n筛选：男/女/空闲/我的/页码\n━━━━━━\n${lines.join("\n")}\n━━━━━━\n追求：.烟火 追求 [姓名] | 详情：.烟火 佳人 [姓名]`
    );
}

// ── 佳人详情 ──
function doCharDetail(ctx, msg, cmdArgs, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) {
        const ad = getAttrInit(gid);
        const mine = CHARS.filter(([n]) => ad[n] && ad[n].owner === ctx.player.userId);
        if (!mine.length) { seal.replyToSender(ctx, msg, "你还没有佳人，用 .烟火 追求 [姓名] 去追！"); return; }
        const lines = mine.map(([n,,,,bt,bv]) => {
            const c = ad[n];
            const bn = bt ? `  加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "";
            return `【${n}】身价 ${fmtCoins(c.price)}${c.married ? " ·已婚" : ""}${bn}`;
        });
        seal.replyToSender(ctx, msg, `${ctx.player.name} 的佳人们：\n${lines.join("\n")}`);
        return;
    }
    const entry = CHARS.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"！`); return; }
    const ad = getAttrInit(gid);
    const [, baseP, gender, desc, bt, bv] = entry;
    const c = ad[name] || { owner: null, ownerName: null, price: baseP, married: false };
    const statusLine = c.owner
        ? `归属：${c.ownerName}${c.married ? "（已婚）" : ""}，出价 ${fmtCoins(Math.ceil(c.price * (c.married ? 3 : 1.5)))} 可争抢`
        : `尚无归属，只需 ${fmtCoins(c.price)} 即可追求`;
    const bLine = bt ? `\n🌟 被动加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "";
    seal.replyToSender(ctx, msg,
        `💌 【${name}】（${gender === "m" ? "美男" : "美女"}）\n${desc}${bLine}\n━━━━\n${statusLine}\n\n用 .烟火 迎娶 ${name} 可正式成婚（需先追求到ta）`
    );
}

// ── 追求 ──
function doPursue(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 追求 [姓名]"); return; }
    const entry = CHARS.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"！`); return; }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (c.owner === ctx.player.userId) { seal.replyToSender(ctx, msg, `${name} 早已在你身边，何必再追？`); return; }

    const factor = c.married ? 3 : 1.5;
    const cost = c.owner ? Math.ceil(c.price * factor) : c.price;
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg,
            c.owner
                ? `争抢【${name}】需出价 ${fmtCoins(cost)}（已婚价×${factor}），还差 ${fmtCoins(cost - p.coins)}！`
                : `追求【${name}】需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`
        );
        return;
    }

    p.coins -= cost;
    if (c.owner) {
        // 被争抢：原主人退款+10%
        const prevKey = `${gid}|${c.owner}`;
        const prev = data[prevKey];
        const refund = Math.floor(c.price * 1.1);
        if (prev) {
            // 如果是婚配关系，解除
            if (prev.spouse && prev.spouse.type === "npc" && prev.spouse.id === name) {
                prev.spouse = null;
            }
            prev.coins += refund;
        }
        const prevName = c.ownerName;
        c.owner = ctx.player.userId; c.ownerName = ctx.player.name;
        c.price = cost; c.married = false; // 争夺后婚姻关系解除
        saveData(data); saveAttr(gid, ad);
        seal.replyToSender(ctx, msg, `💘 ${ctx.player.name} 以 ${fmtCoins(cost)} 将【${name}】从 ${prevName} 身边带走了！\n（${prevName} 获退款 ${fmtCoins(refund)}）`);
        if (prev) sendGroupMsg(prev, `${atUser(prev.userId)} 【${name}】被 ${ctx.player.name} 以 ${fmtCoins(cost)} 争走了！退款 ${fmtCoins(refund)}。`);
    } else {
        c.owner = ctx.player.userId; c.ownerName = ctx.player.name; c.price = cost;
        saveData(data); saveAttr(gid, ad);
        const f = ["鸿雁传书，情意已通，缘分自此而始。","心悦之人终归己，此后相伴左右。","一见倾心，万两黄金也值得。"];
        const [,,,,bt,bv] = entry;
        seal.replyToSender(ctx, msg,
            `💕 ${ctx.player.name} 以 ${fmtCoins(cost)} 追到了【${name}】！\n${pick(f)}\n${entry[3]}` +
            (bt ? `\n🌟 被动加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "") +
            `\n\n可用 .烟火 迎娶 ${name} 正式成婚！`
        );
    }
}

// ── 放手 ──
function doRelease(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 放手 [姓名]"); return; }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (!c || c.owner !== ctx.player.userId) { seal.replyToSender(ctx, msg, `【${name}】不在你身边。`); return; }
    const refund = Math.floor(c.price * 0.5);
    p.coins += refund;
    if (p.spouse && p.spouse.type === "npc" && p.spouse.id === name) p.spouse = null;
    const origEntry = CHARS.find(([n]) => n === name);
    c.owner = null; c.ownerName = null; c.price = origEntry ? origEntry[1] : c.price; c.married = false;
    saveData(data); saveAttr(gid, ad);
    seal.replyToSender(ctx, msg, `【${name}】已放手，重回自由身。退还 ${fmtCoins(refund)}，身价恢复初始。`);
}
