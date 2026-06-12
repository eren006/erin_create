// ============================================================
// 人间烟火 v3.0 — 指令处理：种地 / 上山 / 偷菜
// ============================================================

// ── 种地 ──
function doPlant(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus) {
    const cropName = (cmdArgs.getArgN(2) || "").trim();
    if (!cropName) {
        const unlocked = Object.entries(CROPS).filter(([, c]) =>
            p.coins >= c.reqW && (p.fame || 0) >= c.reqF
        );
        const locked = Object.entries(CROPS).filter(([, c]) =>
            p.coins < c.reqW || (p.fame || 0) < c.reqF
        );
        const ul = unlocked.map(([name, c]) => `${name}(${c.h}h)`).join("、");
        const lk = locked.map(([name, c]) =>
            `${name}[需${fmtCoins(c.reqW)}+${FAME[c.reqF].title}]`
        ).join("、");
        let reply = `📋 可种作物：${ul || "（无）"}`;
        if (lk) reply += `\n🔒 未解锁：${lk}`;
        reply += `\n今日天气推荐：${daily.rec.join("、") || "无特别推荐"}`;
        reply += `\n用法：.烟火 种 [作物名]`;
        seal.replyToSender(ctx, msg, reply);
        return;
    }

    const check = canPlantCrop(p, cropName);
    if (!check.ok) { seal.replyToSender(ctx, msg, `不能种【${cropName}】：${check.reason}`); return; }

    const emptyIdx = p.plots.findIndex(pl => pl === null);
    if (emptyIdx === -1) { seal.replyToSender(ctx, msg, "田地全满！先 .烟火 收 腾出空地，或 .烟火 扩地 扩大田园。"); return; }

    const crop = CROPS[cropName];

    // 春耕动员：本日一次免费
    const useFree = hasEvent(daily, "free_plant") && p.freePlantDate !== todayStr();
    if (!useFree) {
        const seeds = p.bag[crop.seed] || 0;
        if (seeds <= 0) {
            seal.replyToSender(ctx, msg, `没有【${crop.seed}】！先去 .烟火 买 ${crop.seed} 5 购入。`);
            return;
        }
        p.bag[crop.seed] = seeds - 1;
        if (!p.bag[crop.seed]) delete p.bag[crop.seed];
    } else {
        p.freePlantDate = todayStr();
    }

    const event = rollPlantEvent(fort);
    const cropMod = 1 + (bonus.crop || 0);
    const readyAt = now() + crop.h * 3600000;
    p.plots[emptyIdx] = {
        crop: cropName, plantedAt: now(), readyAt, notified: false,
        yieldMod: (event.yieldMod || 1.0) * cropMod,
    };
    if (event.coins) p.coins += event.coins;
    saveData(data);

    const weatherHint = daily.rec.includes(cropName) ? "☀️ 今日天气适宜此作物，预计增产！" : "";
    let reply = `🌱 第${emptyIdx + 1}块地种下了【${cropName}】`;
    if (useFree) reply += "（春耕动员：本次免消耗种子）";
    reply += `\n⏳ ${fmtMs(crop.h * 3600000)}后成熟，届时会@你提醒！`;
    if (weatherHint) reply += `\n${weatherHint}`;
    if (event.text) reply += `\n✨ ${event.text}`;
    if (event.coins) reply += `（挖出了 ${fmtCoins(event.coins)}）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 收地 ──
function doHarvest(ctx, msg, data, key, p, daily, fort, bonus) {
    const harvested = []; let unready = 0;
    const hEvent = rollHarvestEvent(fort, daily);

    for (let i = 0; i < p.plots.length; i++) {
        const pl = p.plots[i]; if (!pl) continue;
        if (pl.readyAt - now() > 0) { unready++; continue; }
        const cr = CROPS[pl.crop];
        const raw = rand(cr.minY, cr.maxY);
        const count = Math.max(1, Math.round(raw * (pl.yieldMod || 1.0) * hEvent.yieldMod));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + count;
        harvested.push({ name: pl.crop, count });
        p.plots[i] = null;
    }
    if (hEvent.coins) p.coins += hEvent.coins;
    saveData(data);

    if (!harvested.length && !unready) { seal.replyToSender(ctx, msg, "田地是空的，先用 .烟火 种 [作物] 播种！"); return; }
    if (!harvested.length) { seal.replyToSender(ctx, msg, `${unready} 块地还没熟，再等等吧！`); return; }

    const list = harvested.map(h => `【${h.name}】×${h.count}`).join("、");
    const flavor = ["擦了把汗，嘴角不自觉地往上扬。","一筐一筐装进背篓，满满当当。","看着丰收，心里头那点愁也散了。"];
    let reply = `🌾 ${ctx.player.name} 收获：${list}\n${pick(flavor)}`;
    if (hEvent.text) reply += `\n✨ ${hEvent.text}`;
    if (hEvent.coins) reply += `（意外得 ${fmtCoins(hEvent.coins)}）`;
    if (unready) reply += `\n（还有 ${unready} 块未成熟）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 田地状态 ──
function doViewFarm(ctx, msg, p, daily) {
    const lines = p.plots.map((pl, i) => {
        if (!pl) return `第${i + 1}块：【空地】`;
        const left = pl.readyAt - now();
        if (left <= 0) return `第${i + 1}块：【${pl.crop}】✅ 已成熟！`;
        const pct = Math.floor((1 - left / (CROPS[pl.crop].h * 3600000)) * 100);
        const bar = "█".repeat(Math.floor(pct / 10)) + "░".repeat(10 - Math.floor(pct / 10));
        return `第${i + 1}块：【${pl.crop}】[${bar}]${pct}% 剩${fmtMs(left)}`;
    });
    const nextCost = LAND_COSTS[p.plots.length - 2];
    seal.replyToSender(ctx, msg,
        `🌾 ${ctx.player.name} 的田地（${p.plots.length}块）：\n` +
        lines.join("\n") +
        (nextCost ? `\n扩地费：${fmtCoins(nextCost)}（.烟火 扩地）` : "") +
        `\n今日天气推荐：${daily.rec.join("、") || "无特别推荐"}`
    );
}

// ── 扩地 ──
function doExpandFarm(ctx, msg, data, key, p) {
    const LAND_COSTS = [500, 2000, 8000, 30000, 100000];
    const max = 2 + LAND_COSTS.length;
    if (p.plots.length >= max) { seal.replyToSender(ctx, msg, `田地已达上限（${max}块）！`); return; }
    const cost = LAND_COSTS[p.plots.length - 2];
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `扩地需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`); return; }
    p.coins -= cost; p.plots.push(null);
    saveData(data);
    seal.replyToSender(ctx, msg, `🏡 扩地成功！花费 ${fmtCoins(cost)}，现有 ${p.plots.length} 块田地。`);
}

// ── 上山 ──
function doHunt(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = seal.ext.getIntConfig(ext, "打猎冷却_分钟") * 60000;
    const cdLeft = (p.huntCd || 0) - now();
    if (cdLeft > 0 && !p.huntBuff) {
        seal.replyToSender(ctx, msg, `精力未复，${fmtMs(cdLeft)} 后才能再上山。`);
        return;
    }
    if (p.huntBuff) p.huntBuff = false; // 消耗buff

    p.huntCd = now() + cdMs;

    const { result, chain, banditLoss, timeMod } = rollHuntResult(p, bonus, daily);

    // 空手
    if (!result.name) {
        if (banditLoss) p.coins = Math.max(0, p.coins - banditLoss);
        saveData(data);
        seal.replyToSender(ctx, msg,
            `🏔️ ${timeMod.label ? `[${timeMod.label}]` : ""}${ctx.player.name} 上山归来……\n` +
            `${pick(result.desc)}` +
            (banditLoss ? `\n⚔️ 遭遇山匪，损失了 ${fmtCoins(banditLoss)}！` : "") +
            (chain ? `\n\n📖 途中：${chain.text}` +
                (chain.coins ? `（${chain.coins > 0 ? "获得" : "损失"} ${fmtCoins(Math.abs(chain.coins))}）` : "") : "") +
            `\n（${fmtMs(cdMs)} 后可再上山）`
        );
        return;
    }

    const count = rand(result.min, result.max);
    p.bag[result.name] = (p.bag[result.name] || 0) + count;
    if (banditLoss) p.coins = Math.max(0, p.coins - banditLoss);

    // 链式事件道具
    if (chain && chain.item) {
        p.bag[chain.item] = (p.bag[chain.item] || 0) + (chain.count || 1);
    }
    if (chain && chain.coins) {
        p.coins = Math.max(0, p.coins + chain.coins);
    }

    saveData(data);
    const estVal = rand(result.minP, result.maxP) * count;
    let reply = `🏔️ ${timeMod.label ? `[${timeMod.label}] ` : ""}${ctx.player.name} 上山归来！\n`;
    reply += `${pick(result.desc)}\n`;
    reply += `获得：【${result.name}】×${count}（约值 ${fmtCoins(estVal)}）`;
    if (banditLoss) reply += `\n⚔️ 遭山匪打劫，损失 ${fmtCoins(banditLoss)}！`;
    if (chain && chain.text) {
        reply += `\n\n📖 途中奇遇：\n${chain.text}`;
        if (chain.item) reply += `（获得【${chain.item}】×${chain.count || 1}）`;
        if (chain.coins) reply += `（${chain.coins > 0 ? "+" : ""}${fmtCoins(chain.coins)}）`;
    }
    reply += `\n（${fmtMs(cdMs)} 后可再上山）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 偷菜（@目标，公开）──
function doSteal(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = seal.ext.getIntConfig(ext, "偷菜冷却_分钟") * 60000;
    // 贼人入村事件：冷却减半
    const effectiveCd = hasEvent(daily, "steal_chaos") ? cdMs * 0.5 : cdMs;
    const cdLeft = (p.stealCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `上次偷菜风头还没过，${fmtMs(cdLeft)} 后再出手！`);
        return;
    }

    const atList = msg.atUsersId || [];
    if (!atList.length) { seal.replyToSender(ctx, msg, "请@一个目标！用法：.烟火 偷 @某人"); return; }
    if (atList[0] === ctx.player.userId) { seal.replyToSender(ctx, msg, "偷自己的菜？这合理吗？"); return; }

    const gid = ctx.group.groupId;
    const tKey = `${gid}|${atList[0]}`;
    const target = data[tKey];
    if (!target || !target.plots || !target.plots.some(pl => pl)) {
        seal.replyToSender(ctx, msg, "对方田里空空如也，没什么可偷！");
        return;
    }

    p.stealCd = now() + effectiveCd;

    // 成功率 = 55% + 偷菜加成 - 对方防盗加成，运势修正
    const targetBonus = getAllBonuses(target, gid);
    const rate = Math.min(0.90, Math.max(0.10,
        (0.55 + (bonus.steal || 0) - (targetBonus.anti || 0)) * fort.stealM
    ));

    const success = Math.random() <= rate;
    const filledIdxArr = target.plots.map((pl, i) => pl ? i : -1).filter(i => i >= 0);

    if (success && filledIdxArr.length) {
        const si = pick(filledIdxArr);
        const pl = target.plots[si];
        const cr = CROPS[pl.crop];
        const stolen = Math.max(1, Math.floor(rand(cr.minY, cr.maxY) * 0.4));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + stolen;
        saveData(data);

        const ok = ["月黑风高，手脚麻利摘了几个就跑！","趁主人不在，飞快摘了几颗揣进怀里！","动作轻柔，连露水都没惊动——"];
        seal.replyToSender(ctx, msg, `🌙 ${pick(ok)}\n偷到：【${pl.crop}】×${stolen}（冷却 ${fmtMs(effectiveCd)}）`);
        sendGroupMsg(target, `${atUser(target.userId)} 你的【${pl.crop}】被 ${ctx.player.name} 偷走了 ${stolen} 个！快 .烟火 收 防止损失！`);
    } else {
        saveData(data);
        const fail = ["脚下一滑，踩断树枝，邻居的狗叫了起来，狼狈逃窜！","正要下手，猛地想起这家主人会武功，腿一软跑了！","手还没伸过去，就被路过老伯盯住了。"];
        seal.replyToSender(ctx, msg, `😅 ${pick(fail)}\n（冷却 ${fmtMs(effectiveCd)}）`);
        sendGroupMsg(target, `${atUser(target.userId)} ${ctx.player.name} 刚才想偷你的菜，没得手——不过要注意！`);
    }
}

// ── 夜袭（随机匿名偷菜）──
function doNightRaid(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = 1800000; // 30分钟固定
    const effectiveCd = hasEvent(daily, "steal_chaos") ? cdMs * 0.5 : cdMs;
    const cdLeft = (p.nightRaidCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `刚才的风声还没散，${fmtMs(cdLeft)} 后再行动！`);
        return;
    }

    const gid = ctx.group.groupId;
    // 找群内有庄稼的其他玩家
    const victims = Object.entries(data).filter(([k, v]) => {
        if (!k.startsWith(gid + "|") || k === key) return false;
        return v.plots && v.plots.some(pl => pl !== null);
    }).map(([, v]) => v);

    if (!victims.length) {
        seal.replyToSender(ctx, msg, "🌙 夜色中四处张望……村里暂时没有可偷的庄稼。");
        return;
    }

    p.nightRaidCd = now() + effectiveCd;
    const target = pick(victims);
    const filledIdxArr = target.plots.map((pl, i) => pl ? i : -1).filter(i => i >= 0);

    // 成功率（匿名，基础略低）
    const targetBonus = getAllBonuses(target, gid);
    const rate = Math.min(0.80, Math.max(0.10,
        (0.48 + (bonus.steal || 0) - (targetBonus.anti || 0)) * fort.stealM
    ));
    const success = Math.random() <= rate;

    if (success) {
        const si = pick(filledIdxArr);
        const pl = target.plots[si];
        const cr = CROPS[pl.crop];
        const stolen = Math.max(1, Math.floor(rand(cr.minY, cr.maxY) * 0.35));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + stolen;
        saveData(data);
        const ok = [
            "趁着月色，悄悄潜入……无声无息地摘走了几颗。",
            "夜幕掩护之下，手脚轻巧，对方浑然不知。",
            "月上柳梢头，人定了，这才出手——干净利落。",
        ];
        seal.replyToSender(ctx, msg,
            `🌙 ${pick(ok)}\n偷到：【${pl.crop}】×${stolen}，对方不知道是谁干的。\n（冷却 ${fmtMs(effectiveCd)}）`
        );
        // 匿名通知——只说有贼，不说是谁
        sendGroupMsg(target, `${atUser(target.userId)} 夜里有人偷了你的【${pl.crop}】${stolen}个！小心门户！`);
    } else {
        saveData(data);
        const fail = [
            "脚踩到了一块空罐子，「铛」的一声，赶紧跑路！",
            "刚翻过篱笆，里面的狗突然叫了起来——落荒而逃。",
            "黑暗中一脚踩空，摔了个跟头，什么没拿到就跑了。",
        ];
        seal.replyToSender(ctx, msg,
            `😅 ${pick(fail)}\n（冷却 ${fmtMs(effectiveCd)}）`
        );
        // 不通知对方（失败了，对方不知道）
    }
}
