// ============================================================
// 人间烟火 v3.0 — 工具函数 & 每日系统
// ============================================================

// ── 基础工具 ──
function rand(a, b)  { return a + Math.floor(Math.random() * (b - a + 1)); }
function pick(arr)   { return arr[Math.floor(Math.random() * arr.length)]; }
function now()       { return Date.now(); }
function atUser(uid) { const n = uid.includes(":") ? uid.split(":")[1] : uid; return `[CQ:at,qq=${n}]`; }

function fmtMs(ms) {
    if (ms <= 0) return "不到1分钟";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return m > 0 ? `${h}小时${m}分` : `${h}小时`;
    return `${m}分`;
}
function fmtCoins(n) {
    n = Math.floor(n);
    if (n >= 100) { const l = Math.floor(n / 100), t = n % 100; return t ? `${l}两${t}铜` : `${l}两`; }
    return `${n}铜`;
}

// ── 日期工具 ──
function getDateStr(offset = 0) {
    const d = new Date(Date.now() + offset * 86400000);
    return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}
function todayStr()     { return getDateStr(0);  }
function yesterdayStr() { return getDateStr(-1); }

// ── 数据存取 ──
function getData()          { try { return JSON.parse(ext.storageGet("yh3_players") || "{}"); } catch { return {}; } }
function saveData(d)        { ext.storageSet("yh3_players", JSON.stringify(d)); }
function getAttr(gid)       { try { return JSON.parse(ext.storageGet(`yh3_attr_${gid}`) || "{}"); } catch { return {}; } }
function saveAttr(gid, d)   { ext.storageSet(`yh3_attr_${gid}`, JSON.stringify(d)); }
function getDailyRaw(gid)   { try { return JSON.parse(ext.storageGet(`yh3_daily_${gid}`) || "{}"); } catch { return {}; } }
function saveDailyRaw(gid,d){ ext.storageSet(`yh3_daily_${gid}`, JSON.stringify(d)); }

function pk(ctx) { return `${ctx.group.groupId}|${ctx.player.userId}`; }

// ── 每日数据（天气 + 事件）——按群，每天刷新 ──
function getDailyData(gid) {
    const today = todayStr();
    const raw = getDailyRaw(gid);
    if (raw.date === today) return raw;

    // 生成新一天
    const weather = WEATHERS[Math.floor(Math.random() * WEATHERS.length)];
    const numEvents = rand(1, 3);
    const shuffled = [...DAILY_EVENTS].sort(() => Math.random() - 0.5);
    const events = shuffled.slice(0, numEvents);

    // 推荐作物（天气偏好 + 当前可种）
    const rec = weather.rec.filter(c => CROPS[c]);

    const daily = { date: today, weather, events, rec };
    saveDailyRaw(gid, daily);
    return daily;
}

function hasEvent(daily, type) {
    return daily.events.some(e => e.type === type);
}
function getEvent(daily, type) {
    return daily.events.find(e => e.type === type) || null;
}

// ── 佳人初始化 ──
function getAttrInit(gid) {
    let ad = getAttr(gid);
    let changed = false;
    for (const [name, price] of CHARS) {
        if (!ad[name]) { ad[name] = { owner: null, ownerName: null, price, married: false }; changed = true; }
    }
    if (changed) saveAttr(gid, ad);
    return ad;
}

// ── 加成计算（佳人 + 村庄）──
function getCharBonuses(userId, gid) {
    const ad = getAttr(gid);
    const b = {};
    for (const [name,,, , type, val] of CHARS) {
        if (type && ad[name] && ad[name].owner === userId) b[type] = (b[type] || 0) + val;
    }
    return b;
}
function getVillageBonus(player) {
    const v = VILLAGES[player.villageIdx ?? 0];
    return v && v.bonus ? { [v.bonus]: v.val } : {};
}
function getAllBonuses(player, gid) {
    const cb = getCharBonuses(player.userId, gid);
    const vb = getVillageBonus(player);
    const result = { ...cb };
    for (const [k, v] of Object.entries(vb)) result[k] = (result[k] || 0) + v;
    return result;
}

// ── 解锁检查 ──
function canPlantCrop(player, cropName) {
    const c = CROPS[cropName];
    if (!c) return { ok: false, reason: `不存在的作物"${cropName}"` };
    if (player.coins < c.reqW)
        return { ok: false, reason: `需要身家 ${fmtCoins(c.reqW)}（当前 ${fmtCoins(player.coins)}）` };
    if ((player.fame || 0) < c.reqF)
        return { ok: false, reason: `需要功名【${FAME[c.reqF].title}】（当前【${FAME[player.fame || 0].title}】）` };
    return { ok: true };
}

// ── 端点缓存 & 消息发送 ──
const epCache = new Map();

function cacheEp(ctx) {
    if (!ctx.endPoint || !ctx.group) return;
    const key = `${ctx.endPoint.platform}:${ctx.endPoint.userId}:${ctx.group.groupId}`;
    epCache.set(key, ctx.endPoint);
}

function sendGroupMsg(player, text) {
    if (!player.groupId || !player.userId) return;
    const ep = epCache.get(`${player.epPlat}:${player.epBot}:${player.groupId}`);
    if (!ep) return;
    try {
        const m = seal.newMessage(); m.messageType = "group"; m.groupId = player.groupId;
        const c = seal.createTempCtx(ep, m);
        seal.replyToSender(c, m, text);
    } catch(e) { console.error("[人间烟火] sendGroupMsg error:", e.message); }
}

// ── 定时检查：庄稼成熟通知 ──
try {
    setInterval(() => {
        const data = getData();
        let changed = false;
        for (const [, p] of Object.entries(data)) {
            if (!p || !p.plots) continue;
            const ready = p.plots.filter(pl => pl && !pl.notified && pl.readyAt <= now());
            if (!ready.length) continue;
            const crops = ready.map(pl => `【${pl.crop}】`).join("、");
            sendGroupMsg(p, `${atUser(p.userId)} 主人！${crops}成熟了，快去 .烟火 收 吧！`);
            for (const pl of p.plots) { if (pl && !pl.notified && pl.readyAt <= now()) pl.notified = true; }
            changed = true;
        }
        if (changed) saveData(data);
    }, 120000);
} catch(e) { console.error("[人间烟火] 定时器失败:", e.message); }

// ── 玩家初始化 & 迁移 ──
function ensurePlayer(ctx) {
    cacheEp(ctx);
    const data = getData();
    const key = pk(ctx);
    if (data[key]) {
        const p = data[key];
        p.epPlat  = ctx.endPoint ? ctx.endPoint.platform : "";
        p.epBot   = ctx.endPoint ? ctx.endPoint.userId   : "";
        p.groupId = ctx.group ? ctx.group.groupId : "";
        p.userId  = ctx.player.userId;
        p.userName = ctx.player.name;
        // 迁移旧字段
        if (!p.children)   p.children   = [];
        if (!p.shops)      p.shops      = {};
        if (!p.bag)        p.bag        = {};
        if (p.villageIdx === undefined) p.villageIdx = Math.floor(Math.random() * VILLAGES.length);
        saveData(data);
    }
    return data;
}

// ── 子嗣成长阶段 ──
function childStage(bornAt) {
    const days = (now() - bornAt) / 86400000;
    if (days < 3)  return { name:"婴儿", emoji:"👶", days, canTask: false };
    if (days < 7)  return { name:"幼童", emoji:"🧒", days, canTask: false, canEdu: true };
    if (days < 15) return { name:"少年", emoji:"🧑", days, canTask: true,  tasks:["收地"] };
    return                 { name:"成年", emoji:"👨", days, canTask: true,  tasks:["收地","上山","经商"] };
}

// ── 签到系统 ──
function doSignIn(ctx, msg, data, key) {
    const p = data[key];
    const today  = todayStr();
    const yester = yesterdayStr();
    if (p.signInDate === today) {
        seal.replyToSender(ctx, msg, `今日已签到，明日再来！（连续 ${p.signInStreak || 1} 天）`);
        return;
    }

    const streak  = (p.signInDate === yester) ? (p.signInStreak || 0) + 1 : 1;
    p.signInStreak = streak;
    p.signInDate   = today;

    // 基础奖励
    let coins = rand(20, 60);
    const bonuses = getAllBonuses(p, ctx.group.groupId);
    if (bonuses.sign) coins = Math.round(coins * (1 + bonuses.sign));

    // 检查丰年庆典事件
    const daily = getDailyData(ctx.group.groupId);
    if (hasEvent(daily, "signin_x2")) coins *= 2;

    // 连签额外奖励
    let streakBonus = 0, streakGift = null, streakMsg = "";
    if (streak >= 30)      { streakBonus = 300; streakGift = { seed:"参苗",   count:1 }; streakMsg = "🎊 连续签到30天！"; }
    else if (streak >= 14) { streakBonus = 150; streakGift = { seed:"草药种", count:3 }; streakMsg = "🎁 连续签到14天！"; }
    else if (streak >= 7)  { streakBonus = 80;  streakGift = { seed:"萝卜种", count:5 }; streakMsg = "✨ 连续签到7天！"; }
    else if (streak >= 3)  { streakBonus = 25;  streakMsg  = "🌱 连续签到3天！"; }

    const total = coins + streakBonus;
    p.coins += total;
    if (streakGift) p.bag[streakGift.seed] = (p.bag[streakGift.seed] || 0) + streakGift.count;

    // 子嗣触发检查（已婚 + 子女 < 3）
    let childMsg = "";
    if (p.spouse && (p.children || []).length < 3) {
        const childRate = 0.15 + (bonuses.child || 0);
        if (Math.random() < childRate) {
            const gender = Math.random() < 0.5 ? "m" : "f";
            const namePool = gender === "m" ? CHILD_NAMES_M : CHILD_NAMES_F;
            const childName = (p.surname || "张") + pick(namePool);
            const child = { name: childName, gender, bornAt: now(), eduLevel: 0, lastTaskAt: 0 };
            if (!p.children) p.children = [];
            p.children.push(child);
            childMsg = `\n\n🍼 【喜事！】你的孩子 ${childName} 降生了！用 .烟火 孩子 查看。`;
        }
    }

    saveData(data);

    const flavor = ["鸡鸣三声，天色未明已起身。","晨光熹微，又是新的一天。","睁开眼，今天又是充满希望的一天。"];
    let reply = `☀️ 签到成功！（连续 ${streak} 天）\n${pick(flavor)}\n获得：${fmtCoins(total)}`;
    if (hasEvent(daily, "signin_x2")) reply += "（丰年庆典翻倍！）";
    if (streakMsg) { reply += `\n${streakMsg}额外获得 ${fmtCoins(streakBonus)}`; }
    if (streakGift) reply += `+ ${streakGift.seed}×${streakGift.count}`;
    reply += `\n当前身家：${fmtCoins(p.coins)}${childMsg}`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 随机事件辅助 ──
function rollPlantEvent(fort) {
    const r = Math.random();
    if (r < 0.04) return { tag:"bonanza", text:"翻地时竟挖出一枚古钱！", coins: rand(20, 80) };
    if (r < 0.14) return { tag:"pest",    text:"地里发现些虫迹，可能影响收成。", yieldMod: 0.75 };
    if (r < 0.24) return { tag:"fertile", text:"土地格外肥沃，预计丰收！", yieldMod: 1.3 * fort.cropM };
    return { tag:"normal", text: null, yieldMod: 1.0 };
}

function rollHarvestEvent(fort, daily) {
    let base = 1.0 * fort.cropM;
    if (hasEvent(daily, "crop_up"))   base *= getEvent(daily, "crop_up").val;
    if (hasEvent(daily, "crop_down")) base *= getEvent(daily, "crop_down").val;
    const r = Math.random();
    if (r < 0.03) return { tag:"gift",   yieldMod: base, text:"收获时发现地头有个包袱，里有散碎银两！", coins: rand(30,100) };
    if (r < 0.10) return { tag:"bumper", yieldMod: base * 1.5, text:"天公作美，今日大丰收！" };
    if (r < 0.20) return { tag:"damage", yieldMod: base * 0.8, text:"昨夜风雨，略有损失。" };
    return { tag:"normal", yieldMod: base, text: null };
}

function rollSellMod(fort, daily, itemName) {
    let mod = fort.sellM;
    if (hasEvent(daily, "sell_up")) mod *= getEvent(daily, "sell_up").val;
    if (hasEvent(daily, "tax"))     mod *= getEvent(daily, "tax").val;
    // 神医问诊：草药类涨价
    if (hasEvent(daily, "herb_x2") && ["草药","灵芝","何首乌","野山参","百年山参","天山雪莲","千年灵芝","龙须菜","人参"].includes(itemName)) {
        mod *= 2;
    }
    return mod;
}

// 上山结果计算（含时段/天气/日事件/加成）
function rollHuntResult(player, bonus, daily) {
    // 冬日封山
    if (hasEvent(daily, "hunt_ban")) return { empty: true, desc: "大雪封山，无功而返。" };

    const h = new Date().getHours();
    let timeMod = { animal:1.0, herb:1.0, rare:1.0, label:"" };
    if      (h >= 5  && h < 9)  timeMod = { animal:1.3, herb:0.7, rare:0.8,  label:"清晨" };
    else if (h >= 17 && h < 21) timeMod = { animal:1.2, herb:1.0, rare:1.3,  label:"傍晚" };
    else if (h >= 21 || h < 5)  timeMod = { animal:0.8, herb:1.2, rare:1.5,  label:"深夜" };

    const weather = daily.weather;
    const huntMod = weather.huntMod;
    const herbMod = weather.herbMod;
    const rareMod = 1 + (bonus.rare || 0);
    const huntBuff = bonus.hunt || 0; // reduces empty weight

    // 构建权重表
    const table = HUNT_TABLE.map(h => {
        let w = h.w;
        if (h.type === "empty")  w *= (1 - huntBuff * 0.5) * (hasEvent(daily, "hunt_buff") ? 0.3 : 1);
        if (h.type === "animal") w *= huntMod * timeMod.animal;
        if (h.type === "herb")   w *= huntMod * herbMod * timeMod.herb;
        if (h.type === "rare")   w *= huntMod * rareMod * timeMod.rare;
        return { ...h, w: Math.max(0.01, w) };
    });

    const total = table.reduce((s, h) => s + h.w, 0);
    let r = Math.random() * total;
    let result = table[0];
    for (const h of table) { r -= h.w; if (r <= 0) { result = h; break; } }

    // 山匪事件
    let banditLoss = 0;
    if (hasEvent(daily, "hunt_bandit") && result.type !== "empty" && Math.random() < 0.40) {
        banditLoss = rand(20, 80);
    }

    // 链式事件
    let chain = null;
    if (Math.random() < 0.12) chain = pick(HUNT_CHAINS)();

    return { result, chain, banditLoss, timeMod };
}
