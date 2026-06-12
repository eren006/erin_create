// ============================================================
// 人间烟火 v3.0 — 指令处理：婚姻 / 子嗣
// ============================================================

// ── 迎娶佳人（NPC婚姻）──
function doMarryNPC(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 迎娶 [佳人姓名]"); return; }
    if (p.spouse) {
        seal.replyToSender(ctx, msg, `你已与【${p.spouse.name}】成婚，无法再娶/嫁。若要改变，请先 .烟火 离婚。`);
        return;
    }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (!c || c.owner !== ctx.player.userId) {
        seal.replyToSender(ctx, msg, `你还没有追求到【${name}】！先用 .烟火 追求 ${name}。`);
        return;
    }
    if (c.married) { seal.replyToSender(ctx, msg, `【${name}】已是你的配偶！`); return; }

    const cost = 1000; // 婚礼费用
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `办婚礼需要 ${fmtCoins(cost)} 盘缠，还差 ${fmtCoins(cost - p.coins)}！`); return; }

    p.coins -= cost;
    p.spouse = { type: "npc", id: name, name };
    c.married = true;
    saveData(data); saveAttr(gid, ad);

    const entry = CHARS.find(([n]) => n === name);
    const [,,gender,,bt,bv] = entry || [];
    const gStr = gender === "m" ? "他" : "她";
    const f = [
        `红烛高照，宾客盈门，${name}${gStr}今日盛装而来，眼中含笑。`,
        `拜了天地，入了洞房，此后便是一家人了。`,
        `婚书一签，便是一生。愿此后风雨同路，岁月静好。`,
    ];
    let reply = `🎊 ${ctx.player.name} 与【${name}】正式成婚！\n${pick(f)}\n花费婚礼盘缠：${fmtCoins(cost)}`;
    if (bt) reply += `\n\n💑 配偶加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%（已包含在佳人加成中）`;
    reply += `\n\n婚后每日签到有概率迎来新成员，用 .烟火 孩子 查看子嗣！`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 向玩家求婚 ──
function doProposePlayer(ctx, msg, cmdArgs, data, key, p, gid) {
    if (p.spouse) {
        seal.replyToSender(ctx, msg, `你已与【${p.spouse.name}】成婚，无法再求婚。若要改变，请先 .烟火 离婚。`);
        return;
    }
    const atList = msg.atUsersId || [];
    if (!atList.length) { seal.replyToSender(ctx, msg, "用法：.烟火 求婚 @目标"); return; }
    if (atList[0] === ctx.player.userId) { seal.replyToSender(ctx, msg, "不能向自己求婚！"); return; }

    const tKey = `${gid}|${atList[0]}`;
    const target = data[tKey];
    if (!target) { seal.replyToSender(ctx, msg, "对方还没立业！"); return; }
    if (target.spouse) { seal.replyToSender(ctx, msg, "对方已成婚，不可打扰！"); return; }

    // 存储求婚请求到目标玩家
    target.proposeFrom = { id: ctx.player.userId, name: p.fullName || ctx.player.name, expire: now() + 86400000 };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `💍 ${p.fullName || ctx.player.name} 向 ${target.fullName || target.userName} 送去了婚帖！\n` +
        `对方可在24小时内用 .烟火 答应 或 .烟火 拒绝 来回应。`
    );
    sendGroupMsg(target, `${atUser(target.userId)} 💍 ${p.fullName || ctx.player.name} 向你求婚了！\n用 .烟火 答应 接受，或 .烟火 拒绝 婉拒。（24小时内有效）`);
}

// ── 答应求婚 ──
function doAccept(ctx, msg, data, key, p, gid) {
    if (p.spouse) { seal.replyToSender(ctx, msg, "你已成婚，无法再答应求婚。"); return; }
    const prop = p.proposeFrom;
    if (!prop || prop.expire < now()) { seal.replyToSender(ctx, msg, "没有待回应的婚帖，或已过期。"); return; }

    const sKey = `${gid}|${prop.id}`;
    const suitor = data[sKey];
    if (!suitor) { seal.replyToSender(ctx, msg, "求婚者已不在此处。"); return; }
    if (suitor.spouse) { seal.replyToSender(ctx, msg, "对方已另有婚配，婚帖作废。"); p.proposeFrom = null; saveData(data); return; }

    // 双方成婚
    p.spouse = { type: "player", id: prop.id, name: prop.name };
    suitor.spouse = { type: "player", id: ctx.player.userId, name: p.fullName || ctx.player.name };
    p.proposeFrom = null;
    saveData(data);

    const f = ["红烛高照，宾客盈门，此后便是一家人了。","拜了天地，入了洞房，愿此后风雨同路。","婚书一签，便是一生，岁月静好。"];
    seal.replyToSender(ctx, msg,
        `🎊 ${p.fullName || ctx.player.name} 与 ${prop.name} 正式成婚！\n${pick(f)}\n\n婚后每日签到有概率迎来子嗣！\n配偶可每天互相用 .烟火 帮忙 帮对方收一块地。`
    );
    sendGroupMsg(suitor, `${atUser(suitor.userId)} 🎊 ${p.fullName || ctx.player.name} 答应了你的求婚！你们成婚了！`);
}

// ── 拒绝求婚 ──
function doReject(ctx, msg, data, key, p) {
    if (!p.proposeFrom || p.proposeFrom.expire < now()) {
        seal.replyToSender(ctx, msg, "没有待回应的婚帖。");
        return;
    }
    const name = p.proposeFrom.name;
    p.proposeFrom = null;
    saveData(data);
    seal.replyToSender(ctx, msg, `已婉拒了 ${name} 的婚帖。`);
}

// ── 离婚 ──
function doDivorce(ctx, msg, data, key, p, gid) {
    if (!p.spouse) { seal.replyToSender(ctx, msg, "你尚未成婚。"); return; }
    const spouse = p.spouse;
    // 离婚代价：损失10%财富
    const penalty = Math.floor(p.coins * 0.1);
    p.coins = Math.max(0, p.coins - penalty);

    // 若配偶是玩家，通知并解除
    if (spouse.type === "player") {
        const sKey = `${gid}|${spouse.id}`;
        const s = data[sKey];
        if (s) { s.spouse = null; }
    } else {
        // NPC婚姻：佳人重回可争抢状态
        const ad = getAttrInit(gid);
        if (ad[spouse.id]) { ad[spouse.id].married = false; saveAttr(gid, ad); }
    }

    p.spouse = null;
    saveData(data);

    seal.replyToSender(ctx, msg,
        `💔 ${ctx.player.name} 与 ${spouse.name} 和离。\n` +
        `离婚代价：损失 ${fmtCoins(penalty)}（财富的10%）。\n` +
        `当前身家：${fmtCoins(p.coins)}`
    );
    if (spouse.type === "player") {
        const sKey = `${gid}|${spouse.id}`;
        const s = data[sKey];
        if (s) sendGroupMsg(s, `${atUser(s.userId)} ${ctx.player.name} 提出和离，你们已解除婚约。`);
    }
}

// ── 配偶帮忙（帮助收地，每天1次）──
function doSpouseHelp(ctx, msg, cmdArgs, data, key, p, gid) {
    if (!p.spouse || p.spouse.type !== "player") {
        seal.replyToSender(ctx, msg, "只有与玩家成婚才能互相帮忙！");
        return;
    }
    const today = todayStr();
    if (p.helpDate === today) { seal.replyToSender(ctx, msg, "今天已经帮忙过了，明天再来！"); return; }

    // 帮哪方？看@目标，默认帮配偶
    const atList = msg.atUsersId || [];
    const targetId = atList.length ? atList[0] : p.spouse.id;
    if (targetId !== p.spouse.id) { seal.replyToSender(ctx, msg, "只能帮配偶！"); return; }

    const tKey = `${gid}|${targetId}`;
    const target = data[tKey];
    if (!target || !target.spouse || target.spouse.id !== ctx.player.userId) {
        seal.replyToSender(ctx, msg, "对方婚姻状态有变，无法帮忙。");
        return;
    }

    // 帮助收取一块成熟的地
    const readyIdx = target.plots.findIndex(pl => pl && pl.readyAt <= now());
    if (readyIdx === -1) { seal.replyToSender(ctx, msg, `${target.fullName || target.userName} 暂时没有成熟的庄稼。`); return; }

    const pl = target.plots[readyIdx];
    const cr = CROPS[pl.crop];
    const count = Math.max(1, rand(cr.minY, cr.maxY));
    target.bag[pl.crop] = (target.bag[pl.crop] || 0) + count;
    target.plots[readyIdx] = null;
    p.helpDate = today;
    saveData(data);

    seal.replyToSender(ctx, msg, `💑 帮配偶收获了【${pl.crop}】×${count}！`);
    sendGroupMsg(target, `${atUser(target.userId)} 你的配偶 ${p.fullName || ctx.player.name} 帮你收了【${pl.crop}】×${count}！`);
}

// ── 查看子嗣 ──
function doViewChildren(ctx, msg, p) {
    const children = p.children || [];
    if (!children.length) {
        const hint = p.spouse ? "每日签到有机会迎来新生儿！" : "先成婚（.烟火 求婚/@目标 或 .烟火 迎娶 佳人名）才能有孩子！";
        seal.replyToSender(ctx, msg, `${ctx.player.name} 膝下尚无子女。\n${hint}`);
        return;
    }
    const lines = children.map(child => {
        const st = childStage(child.bornAt);
        const taskReady = child.lastTaskAt < now() - 43200000; // 12h冷却
        let line = `${st.emoji}【${child.name}】${st.name}（已出生${Math.floor(st.days)}天）`;
        if (st.canEdu) line += `  学识:${child.eduLevel || 0}/10`;
        if (st.canTask) line += `  ${taskReady ? "✅可差遣" : "⏳差遣冷却中"}`;
        return line;
    });
    const maxChildren = 3;
    seal.replyToSender(ctx, msg,
        `👨‍👩‍👧 ${ctx.player.name} 的子嗣（${children.length}/${maxChildren}）：\n${lines.join("\n")}\n` +
        `\n.烟火 教导 [孩子名]  /  .烟火 差遣 [孩子名] [收地/上山/经商]`
    );
}

// ── 教导孩子 ──
function doTeachChild(ctx, msg, cmdArgs, data, key, p) {
    const cname = (cmdArgs.getArgN(2) || "").trim();
    if (!cname) { seal.replyToSender(ctx, msg, "用法：.烟火 教导 [孩子名]"); return; }
    const child = (p.children || []).find(c => c.name === cname);
    if (!child) { seal.replyToSender(ctx, msg, `找不到孩子"${cname}"！用 .烟火 孩子 查看。`); return; }
    const st = childStage(child.bornAt);
    if (!st.canEdu) { seal.replyToSender(ctx, msg, `${child.name}还是婴儿，等长大一点再教导！`); return; }
    if ((child.eduLevel || 0) >= 10) { seal.replyToSender(ctx, msg, `${child.name}的学识已满！`); return; }

    const cost = 50 * ((child.eduLevel || 0) + 1);
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `教导 ${child.name} 需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`); return; }

    p.coins -= cost;
    child.eduLevel = (child.eduLevel || 0) + 1;
    saveData(data);

    const f = [
        "手把手教导，孩子认真地点头，眼里闪着光。",
        "给他讲了一下午的道理，似懂非懂，但终究有所得。",
        "不知不觉天色暗了，回过神来，孩子已安静地在旁边练习。",
    ];
    seal.replyToSender(ctx, msg,
        `📚 教导${child.name}……\n${pick(f)}\n学识提升至 ${child.eduLevel}/10，花费 ${fmtCoins(cost)}`
    );
}

// ── 差遣孩子 ──
function doDispatchChild(ctx, msg, cmdArgs, data, key, p, bonus) {
    const cname  = (cmdArgs.getArgN(2) || "").trim();
    const task   = (cmdArgs.getArgN(3) || "").trim();
    if (!cname || !task) { seal.replyToSender(ctx, msg, "用法：.烟火 差遣 [孩子名] [收地/上山/经商]"); return; }

    const child = (p.children || []).find(c => c.name === cname);
    if (!child) { seal.replyToSender(ctx, msg, `找不到孩子"${cname}"！`); return; }
    const st = childStage(child.bornAt);
    if (!st.canTask) { seal.replyToSender(ctx, msg, `${child.name}还太小，等长到少年再差遣！`); return; }
    if (!st.tasks.includes(task)) {
        seal.replyToSender(ctx, msg, `${child.name}目前只能：${st.tasks.join("、")}（成年后解锁更多）`);
        return;
    }

    const taskCdMs = 43200000; // 12小时
    if (child.lastTaskAt + taskCdMs > now()) {
        seal.replyToSender(ctx, msg, `${child.name}还在休息，${fmtMs(child.lastTaskAt + taskCdMs - now())} 后再差遣！`);
        return;
    }

    child.lastTaskAt = now();
    const eduBonus = (child.eduLevel || 0) * 0.05; // 学识每级+5%效率

    if (task === "收地") {
        const readyIdx = p.plots.findIndex(pl => pl && pl.readyAt <= now());
        if (readyIdx === -1) { child.lastTaskAt = 0; seal.replyToSender(ctx, msg, `没有成熟的庄稼，差遣无效。`); return; }
        const pl = p.plots[readyIdx];
        const cr = CROPS[pl.crop];
        const count = Math.max(1, Math.round(rand(cr.minY, cr.maxY) * (0.6 + eduBonus)));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + count;
        p.plots[readyIdx] = null;
        saveData(data);
        seal.replyToSender(ctx, msg, `🧑 ${child.name} 去田里收了【${pl.crop}】×${count}！（学识加成 +${Math.round(eduBonus * 100)}%）`);

    } else if (task === "上山") {
        // 孩子上山，成功率和收获均低于父母
        const huntRate = 0.5 + eduBonus;
        if (Math.random() > huntRate) {
            saveData(data);
            seal.replyToSender(ctx, msg, `🏔️ ${child.name}上山转了一圈，空手而归……`);
            return;
        }
        const commonItems = HUNT_TABLE.filter(h => h.name && h.w >= 5);
        const item = pick(commonItems);
        const count = rand(item.min, item.max);
        p.bag[item.name] = (p.bag[item.name] || 0) + count;
        saveData(data);
        seal.replyToSender(ctx, msg, `🏔️ ${child.name} 上山带回了【${item.name}】×${count}！`);

    } else if (task === "经商") {
        if (!p.shops || !Object.values(p.shops).some(v => v > 0)) {
            child.lastTaskAt = 0; seal.replyToSender(ctx, msg, "你还没有铺子，无法差遣经商！"); return;
        }
        const income = Math.round(rand(30, 80) * (1 + eduBonus) * (1 + (bonus.shop || 0)));
        p.coins += income;
        saveData(data);
        seal.replyToSender(ctx, msg, `💼 ${child.name} 在铺子里帮忙，带回了额外收入 ${fmtCoins(income)}！`);
    }
}
