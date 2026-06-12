// ============================================================
// 人间烟火 v3.1 扩展指令 — 排行榜 / 成就查看 / 节日查看
// ============================================================

// ── 排行榜 ──
function doLeaderboard(ctx, msg, gid) {
    const data  = getData();
    const all   = Object.entries(data)
        .filter(([k]) => k.startsWith(gid + "|"))
        .map(([, p]) => p)
        .filter(p => p && p.coins !== undefined);

    if (all.length < 2) {
        seal.replyToSender(ctx, msg, "群内立业的人还不够多，排行榜等人气旺了再看！");
        return;
    }

    // 财富榜
    const wealthTop = [...all].sort((a, b) => b.coins - a.coins).slice(0, 10);
    const wealthLines = wealthTop.map((p, i) => {
        const medal  = ["🥇","🥈","🥉"][i] || `${i + 1}.`;
        const title  = getPlayerTitle(p);
        const name   = p.fullName || p.userName;
        return `${medal} ${name}${title ? `【${title}】` : ""}  ${fmtCoins(p.coins)}`;
    });

    // 功名榜
    const fameTop = [...all].sort((a, b) => (b.fame || 0) - (a.fame || 0)).slice(0, 5);
    const fameLines = fameTop.map((p, i) => {
        const name = p.fullName || p.userName;
        return `${i + 1}. ${name}：${FAME[p.fame || 0].title}`;
    });

    // 成就榜
    const achTop = [...all]
        .sort((a, b) => (b.achievements || []).length - (a.achievements || []).length)
        .slice(0, 5);
    const achLines = achTop.map((p, i) => {
        const name = p.fullName || p.userName;
        return `${i + 1}. ${name}：${(p.achievements || []).length} 个成就`;
    });

    seal.replyToSender(ctx, msg,
        `🏆 人间烟火 · 群内排行\n` +
        `━━【财富榜】━━\n${wealthLines.join("\n")}\n` +
        `━━【功名榜】━━\n${fameLines.join("\n")}\n` +
        `━━【成就榜】━━\n${achLines.join("\n")}`
    );
}

// ── 成就列表 ──
function doAchievementList(ctx, msg, p) {
    const unlocked = new Set(p.achievements || []);
    const title    = getPlayerTitle(p);

    const lines = ACHIEVEMENTS.map(a => {
        if (unlocked.has(a.id)) {
            return `✅ 【${a.name}】${a.desc}  称号：「${a.title}」`;
        }
        if (a.hidden) {
            return `🔒 ??? （隐藏成就）`;
        }
        return `⬜ 【${a.name}】${a.desc}`;
    });

    const total = ACHIEVEMENTS.length;
    const done  = unlocked.size;
    const pct   = Math.floor(done / total * 100);

    seal.replyToSender(ctx, msg,
        `🏅 ${p.fullName || ctx.player.name} 的成就\n` +
        `当前称号：${title ? `「${title}」` : "（无）"}\n` +
        `完成进度：${done}/${total}（${pct}%）\n` +
        `━━━━━━\n` +
        lines.join("\n")
    );
}

// ── 节日信息 ──
function doFestivalInfo(ctx, msg) {
    const today = getTodayFestival();
    const d = new Date();
    const m = d.getMonth() + 1, day = d.getDate();

    // 找下一个节日
    let next = null;
    for (const f of FESTIVALS) {
        const fDate = new Date(d.getFullYear(), f.month - 1, f.day);
        if (fDate >= d) { next = f; break; }
    }
    if (!next) next = FESTIVALS[0]; // wrap to next year

    if (today) {
        const effects = [];
        if (today.signMod  > 1)  effects.push(`签到×${today.signMod}`);
        if (today.harvestBoost)  effects.push(`收成×${today.harvestBoost}`);
        if (today.rareBoost)     effects.push(`稀有×${today.rareBoost}`);
        if (today.herbBoost)     effects.push(`药材价×${today.herbBoost}`);
        if (today.charDisc)      effects.push(`佳人${today.charDisc * 10}折`);
        if (today.giftItem)      effects.push(`签到送${today.giftItem}×${today.giftCount || 1}`);

        seal.replyToSender(ctx, msg,
            `${today.emoji} 今日节日：【${today.name}】\n` +
            `"${today.special}"\n\n` +
            `节日效果：${effects.join("、")}\n` +
            `（还有 ${today.duration - ((new Date(d.getFullYear(), m - 1, day) - new Date(d.getFullYear(), today.month - 1, today.day)) / 86400000)} 天结束）`
        );
    } else {
        seal.replyToSender(ctx, msg,
            `当前无节日。\n下一个节日：${next.emoji}【${next.name}】（${next.month}月${next.day}日）\n${next.special}`
        );
    }
}
