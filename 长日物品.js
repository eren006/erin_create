// ==UserScript==
// @name         物品系统V2
// @author       长日将尽
// @version      2.0.0
// @description  物品注册、背包、商城、抽取池、二手市场。所有数据存储在主插件 changriV1 中。
// @timestamp    1745568000
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find('item_system_v2');
if (!ext) {
    ext = seal.ext.new("item_system_v2", "长日将尽", "2.0.0");
    seal.ext.register(ext);
}

// ========================
// 核心依赖
// ========================

function getMain() {
    const main = seal.ext.find('changriV1');
    if (!main) console.error("[物品V2] 未找到主插件 changriV1");
    return main;
}

function getPrimaryUid(platform, uid) {
    const main = getMain();
    if (!main) return uid;
    try {
        const extras = JSON.parse(main.storageGet("extra_accounts") || "{}");
        return extras[`${platform}:${uid}`] || uid;
    } catch (e) { return uid; }
}

function getRoleName(ctx, msg) {
    const main = getMain();
    if (!main) return null;
    try {
        const charPlatform = JSON.parse(main.storageGet("a_private_group") || "{}");
        const platform = msg.platform;
        const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
        const uid = getPrimaryUid(platform, rawUid);
        if (!charPlatform[platform]) return null;
        for (const name in charPlatform[platform]) {
            if (Array.isArray(charPlatform[platform][name]) && charPlatform[platform][name][0] === uid) return name;
        }
    } catch (e) { console.log("[物品V2] getRoleName: " + e.message); }
    return null;
}

function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;
    const main = getMain();
    if (!main) return false;
    try {
        const adminList = JSON.parse(main.storageGet("a_adminList") || "{}");
        const parts = msg.sender.userId.split(':');
        return adminList[parts[0]] && adminList[parts[0]].includes(parts[1]);
    } catch (e) { return false; }
}

// ========================
// 存储辅助
// ========================

function getRegistry() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("item_registry") || "{}") : {};
}
function saveRegistry(reg) {
    const main = getMain();
    if (main) main.storageSet("item_registry", JSON.stringify(reg));
}

function getValidAttrs() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("item_valid_attrs") || "[]") : [];
}
function saveValidAttrs(attrs) {
    const main = getMain();
    if (main) main.storageSet("item_valid_attrs", JSON.stringify(attrs));
}

function getInvAll() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("global_inventories") || "{}") : {};
}
function saveInvAll(invs) {
    const main = getMain();
    if (main) main.storageSet("global_inventories", JSON.stringify(invs));
}
function getInv(roleKey) { return getInvAll()[roleKey] || []; }
function saveInv(roleKey, inv) {
    const invs = getInvAll();
    invs[roleKey] = inv;
    saveInvAll(invs);
}
function addToInv(roleKey, code, count) {
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    const entry = inv.find(e => e.code === code);
    if (entry) entry.count += count;
    else inv.push({ code, count });
    invs[roleKey] = inv;
    saveInvAll(invs);
}
function removeFromInv(roleKey, code, count) {
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    const entry = inv.find(e => e.code === code);
    if (!entry || entry.count < count) return false;
    entry.count -= count;
    if (entry.count <= 0) inv.splice(inv.indexOf(entry), 1);
    invs[roleKey] = inv;
    saveInvAll(invs);
    return true;
}
function getInvCount(roleKey, code) {
    const entry = getInv(roleKey).find(e => e.code === code);
    return entry ? entry.count : 0;
}

function getPoolDefs() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("pool_definitions") || "{}") : {};
}
function savePoolDefs(defs) {
    const main = getMain();
    if (main) main.storageSet("pool_definitions", JSON.stringify(defs));
}

function getDrawConfig() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("pool_draw_config") || '{"total":2,"pools":{}}') : { total: 2, pools: {} };
}
function saveDrawConfig(cfg) {
    const main = getMain();
    if (main) main.storageSet("pool_draw_config", JSON.stringify(cfg));
}

function getShop() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("shop_listings") || "[]") : [];
}
function saveShop(shop) {
    const main = getMain();
    if (main) main.storageSet("shop_listings", JSON.stringify(shop));
}

function getMarket() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("secondhand_market") || "{}") : {};
}
function saveMarket(market) {
    const main = getMain();
    if (main) main.storageSet("secondhand_market", JSON.stringify(market));
}

function getMarketConfig() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("market_config") || '{"fee":3,"enabled":true}') : { fee: 3, enabled: true };
}
function saveMarketConfig(cfg) {
    const main = getMain();
    if (main) main.storageSet("market_config", JSON.stringify(cfg));
}

// ========================
// 代码生成器
// ========================

const CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ";

function genItemCode(reg) {
    for (let i = 0; i < CODE_LETTERS.length; i++)
        for (let j = 0; j < CODE_LETTERS.length; j++)
            for (let d = 0; d < 100; d++) {
                const code = `${CODE_LETTERS[i]}${CODE_LETTERS[j]}${String(d).padStart(2, '0')}`;
                if (!reg[code]) return code;
            }
    return null;
}

function genCurrencyCode(reg) {
    for (let i = 0; i < CODE_LETTERS.length; i++)
        for (let d = 0; d < 1000; d++) {
            const code = `${CODE_LETTERS[i]}${String(d).padStart(3, '0')}`;
            if (!reg[code]) return code;
        }
    return null;
}

function genSecondhandCode(market) {
    for (let d = 1; d < 10000; d++) {
        const code = String(d).padStart(4, '0');
        if (!market[code]) return code;
    }
    return null;
}

// 按代码或名称查找物品
function findItem(reg, input) {
    if (!input) return null;
    const code = input.toUpperCase();
    if (reg[code]) return reg[code];
    return Object.values(reg).find(r => r.name === input) || null;
}

// ========================
// 属性效果
// ========================

function parseAttrEffects(str) {
    if (!str) return {};
    const result = {};
    for (const part of str.split(/[,，]/)) {
        const m = part.trim().match(/^(.+?)([+-]\d+)$/);
        if (m) result[m[1]] = parseInt(m[2]);
    }
    return result;
}

function modCharAttrs(platform, roleName, changesStr) {
    if (!changesStr) return;
    const main = getMain();
    if (!main) return;
    const changes = parseAttrEffects(changesStr);
    if (!Object.keys(changes).length) return;
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    const info = apg[platform]?.[roleName];
    if (!info) return;
    const profileKey = `${platform}:${info[0]}`;
    const profiles = JSON.parse(main.storageGet("sys_char_profiles") || "{}");
    const profile = profiles[profileKey] || {};
    for (const [attr, delta] of Object.entries(changes)) profile[attr] = (profile[attr] || 0) + delta;
    profiles[profileKey] = profile;
    main.storageSet("sys_char_profiles", JSON.stringify(profiles));
}

// ========================
// 抽取次数系统
// ========================

function getPlayerDrawRec(platform, uid) {
    const main = getMain();
    if (!main) return null;
    const records = JSON.parse(main.storageGet("player_draw_records") || "{}");
    const key = `${platform}:${uid}`;
    let rec = records[key] || { day: "", used: {}, extra: {} };
    const currentDay = main.storageGet("global_days") || "";
    if (rec.day !== currentDay) { rec.day = currentDay; rec.used = {}; }
    return { records, key, rec };
}

function savePlayerDrawRec(records, key, rec) {
    const main = getMain();
    if (!main) return;
    records[key] = rec;
    main.storageSet("player_draw_records", JSON.stringify(records));
}

function canDraw(rec, config, poolName) {
    const usedTotal = rec.used._total || 0;
    const extraTotal = rec.extra._total || 0;
    const totalBase = (config.total !== null && config.total !== undefined) ? config.total : Infinity;
    if (usedTotal >= totalBase + extraTotal) return { ok: false, reason: "今日总抽取次数已用完" };
    if (poolName) {
        const poolBase = config.pools?.[poolName];
        if (poolBase !== null && poolBase !== undefined) {
            const usedPool = rec.used[poolName] || 0;
            const extraPool = rec.extra[poolName] || 0;
            if (usedPool >= poolBase + extraPool) return { ok: false, reason: `「${poolName}」今日抽取次数已用完` };
        }
    }
    return { ok: true };
}

function consumeDraw(rec, poolName) {
    rec.used._total = (rec.used._total || 0) + 1;
    if (poolName) rec.used[poolName] = (rec.used[poolName] || 0) + 1;
}

function drawFromFixed(pool, reg) {
    const valid = (pool.items || []).filter(i => reg[i.code]);
    if (!valid.length) return null;
    const total = valid.reduce((s, i) => s + (i.weight || 1), 0);
    let rand = Math.random() * total;
    for (const item of valid) {
        rand -= (item.weight || 1);
        if (rand <= 0) return item.code;
    }
    return valid[valid.length - 1].code;
}

function drawFromFree(pool, defs) {
    const available = (pool.items || []).filter(i => i.count > 0);
    if (!available.length) return null;
    const picked = available[Math.floor(Math.random() * available.length)];
    picked.count -= 1;
    if (picked.count <= 0) pool.items.splice(pool.items.indexOf(picked), 1);
    savePoolDefs(defs);
    return picked.code;
}

// ========================
// 通知辅助
// ========================

function notifyPlayer(ctx, platform, roleName, text) {
    const main = getMain();
    if (!main) return;
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    const info = apg[platform]?.[roleName];
    if (!info) return;
    const notifyMsg = seal.newMessage();
    notifyMsg.messageType = "group";
    notifyMsg.groupId = `${platform}-Group:${info[1]}`;
    const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
    seal.replyToSender(notifyCtx, notifyMsg, text);
}

// ========================
// 时间辅助
// ========================

function timeOverlap(t1, t2) {
    const toMin = t => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
    const [s1, e1] = t1.split("-").map(toMin);
    const [s2, e2] = t2.split("-").map(toMin);
    return !(e1 <= s2 || e2 <= s1);
}

// ========================
// 预设物品初始化
// ========================

function initPresetItems() {
    const main = getMain();
    if (!main) return;
    const reg = getRegistry();
    let changed = false;
    if (!reg["TJ00"]) {
        reg["TJ00"] = { code: "TJ00", name: "追踪器", desc: "一枚散发着微光的微型追踪器，轻轻按动便能感知目标此刻的行踪。", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["WN00"]) {
        reg["WN00"] = { code: "WN00", name: "万能钥匙", desc: "一把泛着银光的万能钥匙，据说能开启世间任何一扇被锁住的门。", type: "preset", attrs: null };
        changed = true;
    }
    if (changed) saveRegistry(reg);
}

initPresetItems();

// ========================
// 特殊物品使用逻辑
// ========================

function handleSpecialItemUse(ctx, msg, platform, roleName, roleKey, code, cmdArgs) {
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    if (code === "TJ00") {
        const targetRole = cmdArgs.getArgN(2);
        if (!targetRole) return seal.replyToSender(ctx, msg, "🔍 请指定要追踪的角色：使用 TJ00 角色名");
        const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
        const targetInfo = apg[platform]?.[targetRole];
        if (!targetInfo) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetRole}」。`);
        const targetKey = `${platform}:${targetInfo[0]}`;
        const globalDay = main.storageGet("global_days");
        if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 未设置游戏天数。");

        const timeRestrict = main.storageGet("item_tracker_time_restrict") !== "false";
        let timeRange;
        if (timeRestrict) {
            const h = new Date().getHours();
            timeRange = `${h.toString().padStart(2,'0')}:00-${h === 23 ? "23:59" : (h+1).toString().padStart(2,'0')+":00"}`;
        } else {
            const timeArg = cmdArgs.getArgN(3);
            if (!timeArg) return seal.replyToSender(ctx, msg, "🔍 请指定追踪时间：使用 TJ00 角色名 时间（如 14 或 14:30）");
            let hour, minute = 0;
            if (/^\d{1,2}$/.test(timeArg)) { hour = parseInt(timeArg); }
            else if (/^\d{1,2}:\d{2}$/.test(timeArg)) {
                [hour, minute] = timeArg.split(':').map(Number);
                if (minute < 0 || minute > 59) return seal.replyToSender(ctx, msg, "⚠️ 分钟应在00-59之间");
            } else return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用：14 或 14:30");
            if (hour < 0 || hour > 23) return seal.replyToSender(ctx, msg, "⚠️ 小时应在0-23之间");
            const start = `${hour.toString().padStart(2,'0')}:${minute.toString().padStart(2,'0')}`;
            let endH = hour, endM = minute + 60;
            if (endM >= 60) { endH += Math.floor(endM / 60); endM %= 60; }
            if (endH >= 24) { endH = 23; endM = 59; }
            timeRange = `${start}-${endH.toString().padStart(2,'0')}:${endM.toString().padStart(2,'0')}`;
        }

        const b_confirmedSchedule = JSON.parse(main.storageGet("b_confirmedSchedule") || "{}");
        const matchingEvent = (b_confirmedSchedule[targetKey] || []).find(ev => ev.day === globalDay && timeOverlap(ev.time, timeRange));
        const successRate = parseInt(main.storageGet("item_tracker_success_rate") || "70");
        const showPartner = main.storageGet("item_tracker_show_partner") !== "false";
        const isSuccess = Math.random() * 100 < successRate;

        if (!matchingEvent) return seal.replyToSender(ctx, msg, `🔍 未能发现「${targetRole}」的行踪。\n（追踪器未消耗）`);
        if (!removeFromInv(roleKey, "TJ00", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的追踪器。");
        if (!isSuccess) return seal.replyToSender(ctx, msg, `🔍 信号干扰，定位失败。\n（追踪器已消耗）`);

        let resultMsg = `🔍 追踪到「${targetRole}」在 ${globalDay} ${matchingEvent.time} 出现在「${matchingEvent.place || "某处"}」`;
        if (showPartner && matchingEvent.partner && matchingEvent.partner !== "独自一人") resultMsg += `，与 ${matchingEvent.partner} 一起`;
        resultMsg += `。\n（追踪器已消耗）`;
        return seal.replyToSender(ctx, msg, resultMsg);
    }

    if (code === "WN00") {
        const placeName = cmdArgs.args.slice(1).join(' ').trim();
        if (!placeName) return seal.replyToSender(ctx, msg, "🔑 请指定要兑换钥匙的地点：使用 WN00 地点名");
        const availablePlaces = JSON.parse(main.storageGet("available_places") || "{}");
        if (!availablePlaces[placeName]) {
            const placeList = Object.keys(availablePlaces).join("、") || "（暂无）";
            return seal.replyToSender(ctx, msg, `❌ 未找到地点「${placeName}」。\n📍 可用地点：${placeList}`);
        }
        let placeKeys = JSON.parse(main.storageGet("place_keys") || "{}");
        if (!placeKeys[platform]) placeKeys[platform] = {};
        if (!placeKeys[platform][roleName]) placeKeys[platform][roleName] = [];
        if (placeKeys[platform][roleName].includes(placeName))
            return seal.replyToSender(ctx, msg, `🔑 你已经拥有「${placeName}」的钥匙了。`);
        if (!removeFromInv(roleKey, "WN00", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的万能钥匙。");
        placeKeys[platform][roleName].push(placeName);
        main.storageSet("place_keys", JSON.stringify(placeKeys));
        return seal.replyToSender(ctx, msg, `🔓 万能钥匙化作一缕金光，为你开启了「${placeName}」的门锁！\n你获得了该地点的钥匙。`);
    }

    return false;
}

// ========================
// 使用记录
// ========================

function logItemUsage(platform, roleName, code, itemName) {
    const main = getMain();
    if (!main) return;
    const log = JSON.parse(main.storageGet("item_usage_log") || "[]");
    log.push({ timestamp: Date.now(), platform, roleName, code, name: itemName });
    main.storageSet("item_usage_log", JSON.stringify(log));
}

// ========================
// 背包显示
// ========================

function formatInventory(roleKey, roleName, reg) {
    const inv = getInv(roleKey).filter(e => e.count > 0);
    if (!inv.length) return `🎒 【${roleName}】的背包空空如也。`;
    const currencies = [], presets = [], items = [];
    for (const entry of inv) {
        const info = reg[entry.code] || { name: entry.code, type: "item" };
        if (info.type === "currency") currencies.push({ entry, info });
        else if (info.type === "preset") presets.push({ entry, info });
        else items.push({ entry, info });
    }
    const lines = [`🎒 【${roleName}】的背包：`];
    if (currencies.length) { lines.push("💰 货币："); currencies.forEach(({ entry, info }) => lines.push(`  · ${info.name} [${entry.code}] ×${entry.count}`)); }
    if (presets.length) { lines.push("⚙️ 特殊道具："); presets.forEach(({ entry, info }) => lines.push(`  · ${info.name} [${entry.code}] ×${entry.count}`)); }
    if (items.length) { lines.push("📦 物品："); items.forEach(({ entry, info }) => lines.push(`  · ${info.name} [${entry.code}] ×${entry.count}`)); }
    return lines.join("\n");
}

// ========================
// 管理员指令
// ========================

let cmd_reg_attr = seal.ext.newCmdItemInfo();
cmd_reg_attr.name = "注册属性";
cmd_reg_attr.help = "【管理员】注册可用属性名\n注册属性 体力 精力 心情 —— 空格分隔\n注册属性 列表 —— 查看已注册属性";
cmd_reg_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    if (cmdArgs.getArgN(1) === "列表") {
        const attrs = getValidAttrs();
        return seal.replyToSender(ctx, msg, attrs.length ? `📋 已注册属性：${attrs.join("、")}` : "📋 暂无已注册属性。");
    }
    const newAttrs = [];
    for (let i = 1; ; i++) { const a = cmdArgs.getArgN(i); if (!a) break; newAttrs.push(a); }
    if (!newAttrs.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const attrs = getValidAttrs();
    let added = 0;
    for (const a of newAttrs) if (!attrs.includes(a)) { attrs.push(a); added++; }
    saveValidAttrs(attrs);
    seal.replyToSender(ctx, msg, `✅ 新增 ${added} 个属性。当前：${attrs.join("、")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["注册属性"] = cmd_reg_attr;

let cmd_upload_item = seal.ext.newCmdItemInfo();
cmd_upload_item.name = "上载物品";
cmd_upload_item.help = "【管理员】注册新物品\n上载物品 名称*描述[*属性效果]\n属性效果如：体力+10,精力-5\n支持多行批量";
cmd_upload_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const rawMsg = msg.message.trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let itemLines;
    if (msgParts.length > 1) {
        itemLines = msgParts.slice(1).filter(l => l.trim());
    } else {
        const rest = rawMsg.replace(/^[。.]\s*上载物品\s*/, "").trim();
        itemLines = rest ? [rest] : [];
    }
    if (!itemLines.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const results = [];
    for (const line of itemLines) {
        const parts = line.split(/[*＊]/);
        const name = (parts[0] || "").trim();
        const desc = (parts[1] || "").trim() || "暂无描述";
        const attrs = (parts[2] || "").trim() || null;
        if (!name) { results.push(`❌ 名称不能为空`); continue; }
        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) { results.push(`⚠️ 「${name}」已存在 [${existing.code}]`); continue; }
        const code = genItemCode(reg);
        if (!code) { results.push("❌ 代码空间已满"); break; }
        reg[code] = { code, name, desc, type: "item", attrs };
        results.push(`✅ [${code}] ${name}${attrs ? ` (${attrs})` : ""}`);
    }
    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `物品注册结果：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上载物品"] = cmd_upload_item;

let cmd_reg_currency = seal.ext.newCmdItemInfo();
cmd_reg_currency.name = "注册货币";
cmd_reg_currency.help = "【管理员】注册新货币\n注册货币 名称*描述\n示例：注册货币 金币*流通货币";
cmd_reg_currency.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const raw = cmdArgs.getArgN(1);
    if (!raw) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const parts = raw.split(/[*＊]/);
    const name = (parts[0] || "").trim();
    const desc = (parts[1] || "").trim() || "暂无描述";
    if (!name) return seal.replyToSender(ctx, msg, "❌ 货币名不能为空。");
    const reg = getRegistry();
    const existing = Object.values(reg).find(r => r.name === name && r.type === "currency");
    if (existing) return seal.replyToSender(ctx, msg, `⚠️ 货币「${name}」已存在 [${existing.code}]`);
    const code = genCurrencyCode(reg);
    if (!code) return seal.replyToSender(ctx, msg, "❌ 货币代码空间已满。");
    reg[code] = { code, name, desc, type: "currency", attrs: null };
    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `✅ 货币「${name}」已注册，代码 [${code}]`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["注册货币"] = cmd_reg_currency;

let cmd_item_list = seal.ext.newCmdItemInfo();
cmd_item_list.name = "物品列表";
cmd_item_list.help = "查看所有已注册物品/货币\n物品列表 [物品|货币|预设|全部]";
cmd_item_list.solve = (ctx, msg, cmdArgs) => {
    const reg = getRegistry();
    const filter = cmdArgs.getArgN(1) || "全部";
    const entries = Object.values(reg).filter(e => {
        if (filter === "货币") return e.type === "currency";
        if (filter === "物品") return e.type === "item";
        if (filter === "预设") return e.type === "preset";
        return true;
    });
    if (!entries.length) return seal.replyToSender(ctx, msg, `📋 暂无${filter === "全部" ? "" : filter}。`);
    const lines = entries.map(e => {
        const icon = e.type === "currency" ? "💰" : e.type === "preset" ? "⚙️" : "📦";
        const attrStr = e.attrs ? ` (${e.attrs})` : "";
        return `${icon} [${e.code}] ${e.name}${attrStr}\n   └ ${e.desc}`;
    });
    seal.replyToSender(ctx, msg, `📋 ${filter}列表（${entries.length}）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["物品列表"] = cmd_item_list;

let cmd_shop_add = seal.ext.newCmdItemInfo();
cmd_shop_add.name = "上架商城";
cmd_shop_add.help = "【管理员】上架物品\n上架商城 物品码*价格货币名\n示例：上架商城 AA00*10金币";
cmd_shop_add.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const raw = cmdArgs.getArgN(1);
    if (!raw) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const parts = raw.split(/[*＊]/);
    const inputCode = (parts[0] || "").trim();
    const priceStr = (parts[1] || "").trim();
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${inputCode}」`);
    const priceMatch = priceStr.match(/^(\d+)(.+)$/);
    if (!priceMatch) return seal.replyToSender(ctx, msg, "❌ 价格格式错误，示例：10金币");
    const amount = parseInt(priceMatch[1]);
    const currencyName = priceMatch[2].trim();
    const currency = Object.values(reg).find(r => r.name === currencyName && r.type === "currency");
    if (!currency) return seal.replyToSender(ctx, msg, `❌ 未找到货币「${currencyName}」，请先注册。`);
    if (item.type === "currency") {
        const currencyCount = Object.values(reg).filter(r => r.type === "currency").length;
        if (currencyCount < 2) return seal.replyToSender(ctx, msg, "❌ 上架货币需先注册至少2种货币。");
    }
    const shop = getShop();
    const existingIdx = shop.findIndex(s => s.code === item.code);
    if (existingIdx !== -1) {
        shop[existingIdx].price = amount;
        shop[existingIdx].currencyCode = currency.code;
        shop[existingIdx].currencyName = currencyName;
    } else {
        shop.push({ code: item.code, price: amount, currencyCode: currency.code, currencyName });
    }
    saveShop(shop);
    seal.replyToSender(ctx, msg, `✅ [${item.code}]${item.name} 已${existingIdx !== -1 ? "更新价格" : "上架"}，售价 ${amount}${currencyName}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上架商城"] = cmd_shop_add;

let cmd_shop_remove = seal.ext.newCmdItemInfo();
cmd_shop_remove.name = "商城下架";
cmd_shop_remove.help = "【管理员】将物品从商城下架\n商城下架 物品码或名称";
cmd_shop_remove.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const input = cmdArgs.getArgN(1);
    if (!input) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const item = findItem(reg, input);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${input}」`);
    const shop = getShop();
    const idx = shop.findIndex(s => s.code === item.code);
    if (idx === -1) return seal.replyToSender(ctx, msg, `❌ 商城中没有 [${item.code}]${item.name}`);
    shop.splice(idx, 1);
    saveShop(shop);
    seal.replyToSender(ctx, msg, `✅ [${item.code}]${item.name} 已从商城下架。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["商城下架"] = cmd_shop_remove;

let cmd_reg_pool = seal.ext.newCmdItemInfo();
cmd_reg_pool.name = "注册池子";
cmd_reg_pool.help = "【管理员】创建抽取池\n注册池子 池子名 fixed —— 固定池（加权随机，不减少）\n注册池子 池子名 free —— 自由池（有限数量，抽完即止）";
cmd_reg_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    const poolType = cmdArgs.getArgN(2);
    if (!poolName || !["fixed", "free"].includes(poolType)) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    if (defs[poolName]) return seal.replyToSender(ctx, msg, `⚠️ 池子「${poolName}」已存在。`);
    defs[poolName] = { name: poolName, type: poolType, items: [], enabled: true };
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 池子「${poolName}」已创建（${poolType === "fixed" ? "固定池" : "自由池"}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["注册池子"] = cmd_reg_pool;

let cmd_pool_add = seal.ext.newCmdItemInfo();
cmd_pool_add.name = "上架池子";
cmd_pool_add.help = "【管理员】向池子添加物品\n固定池：上架池子 池子名 物品码*权重\n自由池：上架池子 池子名 物品码*数量\n支持多行批量";
cmd_pool_add.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    const rawMsg = msg.message.trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let itemLines;
    if (msgParts.length > 1) {
        itemLines = msgParts.slice(1).filter(l => l.trim());
    } else {
        const rest = cmdArgs.getArgN(2);
        itemLines = rest ? [rest] : [];
    }
    if (!itemLines.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const results = [];
    for (const line of itemLines) {
        const parts = line.trim().split(/[*＊]/);
        const inputCode = (parts[0] || "").trim();
        const num = parseInt((parts[1] || "1").trim());
        const item = findItem(reg, inputCode);
        if (!item) { results.push(`❌ 未知物品「${inputCode}」`); continue; }
        if (isNaN(num) || num <= 0) { results.push(`❌ 数值无效: ${parts[1]}`); continue; }
        if (pool.type === "fixed") {
            if (num > 999) { results.push(`❌ 权重最大999: [${item.code}]`); continue; }
            const existing = pool.items.find(i => i.code === item.code);
            if (existing) { existing.weight = num; results.push(`🔄 [${item.code}]${item.name} 权重更新为 ${num}`); }
            else { pool.items.push({ code: item.code, weight: num }); results.push(`✅ [${item.code}]${item.name} 权重 ${num}`); }
        } else {
            const existing = pool.items.find(i => i.code === item.code);
            if (existing) { existing.count += num; results.push(`🔄 [${item.code}]${item.name} 数量+${num}（共${existing.count}）`); }
            else { pool.items.push({ code: item.code, count: num }); results.push(`✅ [${item.code}]${item.name} ×${num}`); }
        }
    }
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `池子「${poolName}」更新：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上架池子"] = cmd_pool_add;

let cmd_pool_remove = seal.ext.newCmdItemInfo();
cmd_pool_remove.name = "从池移除";
cmd_pool_remove.help = "【管理员】从池子中移除物品\n从池移除 池子名 物品码或名称";
cmd_pool_remove.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
    if (!poolName || !inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    const code = item ? item.code : inputCode.toUpperCase();
    const idx = pool.items.findIndex(i => i.code === code);
    if (idx === -1) return seal.replyToSender(ctx, msg, `❌ 池子中没有 [${code}]`);
    pool.items.splice(idx, 1);
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 已从「${poolName}」移除 [${code}]${item?.name || ""}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["从池移除"] = cmd_pool_remove;

let cmd_pool_config = seal.ext.newCmdItemInfo();
cmd_pool_config.name = "池子设定";
cmd_pool_config.help = "【管理员】设置每游戏日抽取次数\n池子设定 查看\n池子设定 总量:N —— 全局每日总次数\n池子设定 总量:无限 —— 无限制\n池子设定 池子名:N —— 特定池每日次数";
cmd_pool_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const arg = cmdArgs.getArgN(1);
    if (!arg || arg === "查看") {
        const cfg = getDrawConfig();
        let text = `📊 抽取次数设定：\n总量：${cfg.total !== null && cfg.total !== undefined ? cfg.total + "次" : "无限"}`;
        for (const [pn, n] of Object.entries(cfg.pools || {})) text += `\n  · ${pn}：${n}次`;
        return seal.replyToSender(ctx, msg, text);
    }
    const colonIdx = arg.indexOf(":");
    if (colonIdx === -1) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const key = arg.substring(0, colonIdx);
    const valStr = arg.substring(colonIdx + 1);
    const cfg = getDrawConfig();
    if (key === "总量") {
        cfg.total = valStr === "无限" ? null : parseInt(valStr);
        saveDrawConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 总量限制：${cfg.total !== null ? cfg.total + "次" : "无限"}`);
    }
    const n = parseInt(valStr);
    if (isNaN(n) || n < 0) return seal.replyToSender(ctx, msg, "❌ 次数必须为非负整数。");
    if (!cfg.pools) cfg.pools = {};
    cfg.pools[key] = n;
    saveDrawConfig(cfg);
    seal.replyToSender(ctx, msg, `✅ 池子「${key}」每日次数：${n}次`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["池子设定"] = cmd_pool_config;

function makePoolToggleCmd(cmdName, enableValue) {
    let cmd = seal.ext.newCmdItemInfo();
    cmd.name = cmdName;
    cmd.help = `【管理员】${cmdName} 池子名`;
    cmd.solve = (ctx, msg, cmdArgs) => {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
        const poolName = cmdArgs.getArgN(1);
        if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
        const defs = getPoolDefs();
        if (!defs[poolName]) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
        defs[poolName].enabled = enableValue;
        savePoolDefs(defs);
        seal.replyToSender(ctx, msg, `✅ 池子「${poolName}」已${enableValue ? "开启" : "关闭"}。`);
        return seal.ext.newCmdExecuteResult(true);
    };
    return cmd;
}
ext.cmdMap["开启池子"] = makePoolToggleCmd("开启池子", true);
ext.cmdMap["关闭池子"] = makePoolToggleCmd("关闭池子", false);

let cmd_del_pool = seal.ext.newCmdItemInfo();
cmd_del_pool.name = "删除池子";
cmd_del_pool.help = "【管理员】彻底删除池子\n删除池子 池子名";
cmd_del_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    if (!defs[poolName]) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    delete defs[poolName];
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 池子「${poolName}」已删除。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除池子"] = cmd_del_pool;

let cmd_adjust = seal.ext.newCmdItemInfo();
cmd_adjust.name = "调整";
cmd_adjust.help = "【管理员】直接调整玩家背包数量\n调整 角色名 物品码 +N 或 -N\n示例：调整 张三 AA00 +3";
cmd_adjust.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
    const deltaStr = cmdArgs.getArgN(3);
    if (!roleName || !inputCode || !deltaStr) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const delta = parseInt(deltaStr);
    if (isNaN(delta)) return seal.replyToSender(ctx, msg, "❌ 数量格式错误，示例：+3 或 -2");
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${inputCode}」`);
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    const platform = msg.platform;
    if (!apg[platform]?.[roleName]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const roleKey = `${platform}:${roleName}`;
    if (delta > 0) {
        addToInv(roleKey, item.code, delta);
        seal.replyToSender(ctx, msg, `✅ [${item.code}]${item.name} ×${delta} 已加入「${roleName}」背包。`);
    } else if (delta < 0) {
        if (!removeFromInv(roleKey, item.code, -delta)) return seal.replyToSender(ctx, msg, `❌ 「${roleName}」背包中数量不足。`);
        seal.replyToSender(ctx, msg, `✅ 已从「${roleName}」背包扣除 [${item.code}]${item.name} ×${-delta}。`);
    } else {
        seal.replyToSender(ctx, msg, "⚠️ 调整量为0，无变化。");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["调整"] = cmd_adjust;

let cmd_grant_draws = seal.ext.newCmdItemInfo();
cmd_grant_draws.name = "发放抽取";
cmd_grant_draws.help = "【管理员】给玩家额外抽取次数（永久，不随游戏日重置）\n发放抽取 角色名 N —— 总量额外N次\n发放抽取 角色名 池子名 N —— 特定池额外N次";
cmd_grant_draws.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    const arg3 = cmdArgs.getArgN(3);
    if (!roleName || !arg2) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    const platform = msg.platform;
    if (!apg[platform]?.[roleName]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const uid = apg[platform][roleName][0];
    const drRec = getPlayerDrawRec(platform, uid);
    if (!drRec) return seal.replyToSender(ctx, msg, "❌ 无法读取抽取记录。");
    const { records, key, rec } = drRec;
    let poolName = null, n;
    if (arg3) { poolName = arg2; n = parseInt(arg3); }
    else { n = parseInt(arg2); }
    if (isNaN(n) || n <= 0) return seal.replyToSender(ctx, msg, "❌ 次数必须为正整数。");
    if (!rec.extra) rec.extra = {};
    if (poolName) {
        rec.extra[poolName] = (rec.extra[poolName] || 0) + n;
        seal.replyToSender(ctx, msg, `✅ 已为「${roleName}」发放「${poolName}」额外次数 ×${n}`);
    } else {
        rec.extra._total = (rec.extra._total || 0) + n;
        seal.replyToSender(ctx, msg, `✅ 已为「${roleName}」发放总额外次数 ×${n}`);
    }
    savePlayerDrawRec(records, key, rec);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发放抽取"] = cmd_grant_draws;

let cmd_admin_bag = seal.ext.newCmdItemInfo();
cmd_admin_bag.name = "查看背包";
cmd_admin_bag.help = "【管理员】查看指定角色背包\n查看背包 角色名";
cmd_admin_bag.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    seal.replyToSender(ctx, msg, formatInventory(`${msg.platform}:${roleName}`, roleName, getRegistry()));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看背包"] = cmd_admin_bag;

let cmd_usage_log = seal.ext.newCmdItemInfo();
cmd_usage_log.name = "物品使用记录";
cmd_usage_log.help = "【管理员】查看今日物品使用记录\n物品使用记录 [N] —— 默认20条";
cmd_usage_log.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const n = parseInt(cmdArgs.getArgN(1)) || 20;
    const log = JSON.parse(main.storageGet("item_usage_log") || "[]");
    const todayStart = new Date(); todayStart.setHours(0, 0, 0, 0);
    const todayLog = log.filter(e => e.timestamp >= todayStart.getTime()).sort((a, b) => a.timestamp - b.timestamp);
    if (!todayLog.length) return seal.replyToSender(ctx, msg, "📭 今天还没有物品使用记录。");
    const slice = todayLog.slice(-n);
    const lines = slice.map((e, i) => {
        const t = new Date(e.timestamp).toLocaleTimeString("zh-CN", { hour: '2-digit', minute: '2-digit' });
        return `${i + 1}. ${t} ${e.roleName} 使用了 [${e.code}]${e.name}`;
    });
    seal.replyToSender(ctx, msg, `📜 今日记录（${slice.length}/${todayLog.length}）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["物品使用记录"] = cmd_usage_log;

let cmd_market_config = seal.ext.newCmdItemInfo();
cmd_market_config.name = "二手设定";
cmd_market_config.help = "【管理员】配置二手市场\n二手设定 手续费:N —— 设置手续费百分比（2-5）\n二手设定 开启 / 关闭\n二手设定 查看";
cmd_market_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const arg = cmdArgs.getArgN(1);
    const cfg = getMarketConfig();
    if (!arg || arg === "查看") {
        return seal.replyToSender(ctx, msg, `🏬 二手市场设定：\n状态：${cfg.enabled ? "开启" : "关闭"}\n手续费：${cfg.fee}%（买家承担，向上取整）`);
    }
    if (arg === "开启") { cfg.enabled = true; saveMarketConfig(cfg); return seal.replyToSender(ctx, msg, "✅ 二手市场已开启。"); }
    if (arg === "关闭") { cfg.enabled = false; saveMarketConfig(cfg); return seal.replyToSender(ctx, msg, "✅ 二手市场已关闭。"); }
    const colonIdx = arg.indexOf(":");
    if (colonIdx !== -1 && arg.substring(0, colonIdx) === "手续费") {
        const fee = parseInt(arg.substring(colonIdx + 1));
        if (isNaN(fee) || fee < 2 || fee > 5) return seal.replyToSender(ctx, msg, "❌ 手续费需在2-5之间。");
        cfg.fee = fee;
        saveMarketConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 手续费已设为 ${fee}%`);
    }
    const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r;
};
ext.cmdMap["二手设定"] = cmd_market_config;

// ========================
// 玩家指令
// ========================

let cmd_shop_view = seal.ext.newCmdItemInfo();
cmd_shop_view.name = "商城";
cmd_shop_view.help = "查看商城物品列表";
cmd_shop_view.solve = (ctx, msg) => {
    const shop = getShop();
    const reg = getRegistry();
    if (!shop.length) return seal.replyToSender(ctx, msg, "🏪 商城暂无上架物品。");
    const lines = shop.map(s => {
        const item = reg[s.code] || { name: s.code, desc: "" };
        return `[${s.code}] ${item.name} — ${s.price}${s.currencyName}\n   └ ${item.desc}`;
    });
    seal.replyToSender(ctx, msg, `🏪 商城（${shop.length}件）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["商城"] = cmd_shop_view;

let cmd_buy = seal.ext.newCmdItemInfo();
cmd_buy.name = "购买";
cmd_buy.help = "从商城购买物品\n购买 物品码 [数量]";
cmd_buy.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const inputCode = cmdArgs.getArgN(1);
    const count = parseInt(cmdArgs.getArgN(2)) || 1;
    if (!inputCode || count <= 0) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${inputCode}」`);
    const shop = getShop();
    const listing = shop.find(s => s.code === item.code);
    if (!listing) return seal.replyToSender(ctx, msg, `❌ 商城中没有 [${item.code}]${item.name}，发送「商城」查看。`);
    const totalCost = listing.price * count;
    const hasCurrency = getInvCount(roleKey, listing.currencyCode);
    if (hasCurrency < totalCost) return seal.replyToSender(ctx, msg, `❌ ${listing.currencyName}不足。需要 ${totalCost}，持有 ${hasCurrency}。`);
    removeFromInv(roleKey, listing.currencyCode, totalCost);
    addToInv(roleKey, item.code, count);
    seal.replyToSender(ctx, msg, `✅ 购买成功！获得 [${item.code}]${item.name} ×${count}，花费 ${totalCost}${listing.currencyName}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["购买"] = cmd_buy;

let cmd_give_item = seal.ext.newCmdItemInfo();
cmd_give_item.name = "赠送物品";
cmd_give_item.help = "将背包中的物品送给其他玩家\n赠送物品 角色名 物品码 [数量]";
cmd_give_item.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
    const count = parseInt(cmdArgs.getArgN(3)) || 1;
    if (!targetName || !inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    if (targetName === roleName) return seal.replyToSender(ctx, msg, "⚠️ 不能赠送给自己。");
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!apg[platform]?.[targetName]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);
    if (!removeFromInv(roleKey, item.code, count)) {
        const has = getInvCount(roleKey, item.code);
        return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不足（持有 ${has}，需要 ${count}）。`);
    }
    addToInv(`${platform}:${targetName}`, item.code, count);
    notifyPlayer(ctx, platform, targetName, `📦 「${roleName}」赠送给你 [${item.code}]${item.name} ×${count}，已加入背包。`);
    seal.replyToSender(ctx, msg, `✅ 已将 [${item.code}]${item.name} ×${count} 赠送给「${targetName}」。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["赠送物品"] = cmd_give_item;

let cmd_use = seal.ext.newCmdItemInfo();
cmd_use.name = "使用";
cmd_use.help = "使用背包中的物品\n使用 物品码或名称 [参数]\n示例：\n使用 TJ00 张三 —— 追踪器\n使用 WN00 酒馆 —— 万能钥匙\n使用 AA00 —— 普通物品";
cmd_use.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const inputCode = cmdArgs.getArgN(1);
    if (!inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);
    if (getInvCount(roleKey, item.code) <= 0) return seal.replyToSender(ctx, msg, `❌ 背包中没有 [${item.code}]${item.name}。`);
    if (item.code === "TJ00" || item.code === "WN00") {
        return handleSpecialItemUse(ctx, msg, platform, roleName, roleKey, item.code, cmdArgs);
    }
    if (!removeFromInv(roleKey, item.code, 1)) return seal.replyToSender(ctx, msg, "❌ 使用失败。");
    if (item.attrs) modCharAttrs(platform, roleName, item.attrs);
    logItemUsage(platform, roleName, item.code, item.name);
    let reply = `⚙️ 【${roleName}】使用了 [${item.code}]${item.name}。`;
    if (item.attrs) {
        const changes = parseAttrEffects(item.attrs);
        reply += `\n📊 属性变化：${Object.entries(changes).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join("，")}`;
    }
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["使用"] = cmd_use;

let cmd_sell = seal.ext.newCmdItemInfo();
cmd_sell.name = "售卖";
cmd_sell.help = "将物品上架二手市场\n售卖 物品码 价格 货币名 [数量]\n示例：售卖 AA00 8 金币 2";
cmd_sell.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const cfg = getMarketConfig();
    if (!cfg.enabled) return seal.replyToSender(ctx, msg, "❌ 二手市场暂未开放。");
    const inputCode = cmdArgs.getArgN(1);
    const priceStr = cmdArgs.getArgN(2);
    const currencyName = cmdArgs.getArgN(3);
    const count = parseInt(cmdArgs.getArgN(4)) || 1;
    if (!inputCode || !priceStr || !currencyName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const price = parseInt(priceStr);
    if (isNaN(price) || price <= 0) return seal.replyToSender(ctx, msg, "❌ 价格必须为正整数。");
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);
    if (item.type === "preset") return seal.replyToSender(ctx, msg, "❌ 特殊道具不可在二手市场售卖。");
    const currency = Object.values(reg).find(r => r.name === currencyName && r.type === "currency");
    if (!currency) return seal.replyToSender(ctx, msg, `❌ 未找到货币「${currencyName}」。`);
    if (!removeFromInv(roleKey, item.code, count)) {
        const has = getInvCount(roleKey, item.code);
        return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不足（持有 ${has}，需要 ${count}）。`);
    }
    const market = getMarket();
    const shCode = genSecondhandCode(market);
    if (!shCode) return seal.replyToSender(ctx, msg, "❌ 二手市场编号已满。");
    market[shCode] = { sellerRole: roleName, code: item.code, count, price, currencyCode: currency.code, currencyName, listedAt: Date.now() };
    saveMarket(market);
    seal.replyToSender(ctx, msg, `✅ [${item.code}]${item.name} ×${count} 已上架二手市场，编号 #${shCode}，售价 ${price * count}${currencyName}（手续费${cfg.fee}%）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["售卖"] = cmd_sell;

let cmd_cancel_sell = seal.ext.newCmdItemInfo();
cmd_cancel_sell.name = "撤销卖单";
cmd_cancel_sell.help = "撤销二手市场的卖单\n撤销卖单 编号（如 0001）";
cmd_cancel_sell.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const shCode = (cmdArgs.getArgN(1) || "").padStart(4, '0');
    if (shCode.length !== 4) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const market = getMarket();
    const listing = market[shCode];
    if (!listing) return seal.replyToSender(ctx, msg, `❌ 未找到卖单 #${shCode}`);
    if (listing.sellerRole !== roleName && !isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 只能撤销自己的卖单。");
    delete market[shCode];
    saveMarket(market);
    addToInv(`${platform}:${listing.sellerRole}`, listing.code, listing.count);
    const reg = getRegistry();
    seal.replyToSender(ctx, msg, `✅ 卖单 #${shCode} 已撤销，[${listing.code}]${reg[listing.code]?.name || listing.code} ×${listing.count} 已退回背包。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤销卖单"] = cmd_cancel_sell;

let cmd_market = seal.ext.newCmdItemInfo();
cmd_market.name = "二手市场";
cmd_market.help = "查看/购买二手市场物品\n二手市场 —— 查看所有在售\n二手市场 买 编号 —— 购买指定编号";
cmd_market.solve = (ctx, msg, cmdArgs) => {
    const cfg = getMarketConfig();
    if (!cfg.enabled) return seal.replyToSender(ctx, msg, "❌ 二手市场暂未开放。");
    const action = cmdArgs.getArgN(1);
    const market = getMarket();
    const reg = getRegistry();
    if (action === "买") {
        const shCode = (cmdArgs.getArgN(2) || "").padStart(4, '0');
        const listing = market[shCode];
        if (!listing) return seal.replyToSender(ctx, msg, `❌ 未找到编号 #${shCode} 的卖单。`);
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        if (listing.sellerRole === roleName) return seal.replyToSender(ctx, msg, "❌ 不能购买自己的卖单。");
        const platform = msg.platform;
        const roleKey = `${platform}:${roleName}`;
        const fee = Math.ceil(listing.price * listing.count * cfg.fee / 100);
        const totalCost = listing.price * listing.count + fee;
        const hasCurrency = getInvCount(roleKey, listing.currencyCode);
        if (hasCurrency < totalCost) return seal.replyToSender(ctx, msg, `❌ ${listing.currencyName}不足。需要 ${totalCost}（含手续费${fee}），持有 ${hasCurrency}。`);
        removeFromInv(roleKey, listing.currencyCode, totalCost);
        addToInv(`${platform}:${listing.sellerRole}`, listing.currencyCode, listing.price * listing.count);
        addToInv(roleKey, listing.code, listing.count);
        delete market[shCode];
        saveMarket(market);
        const itemName = reg[listing.code]?.name || listing.code;
        notifyPlayer(ctx, platform, listing.sellerRole, `💰 卖单 #${shCode} [${listing.code}]${itemName} ×${listing.count} 已售出，获得 ${listing.price * listing.count}${listing.currencyName}。`);
        seal.replyToSender(ctx, msg, `✅ 购买成功！获得 [${listing.code}]${itemName} ×${listing.count}，花费 ${totalCost}${listing.currencyName}（含手续费${fee}）`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const listings = Object.entries(market);
    if (!listings.length) return seal.replyToSender(ctx, msg, "🏬 二手市场暂无在售物品。");
    const lines = listings.map(([shCode, l]) => {
        const itemName = reg[l.code]?.name || l.code;
        const fee = Math.ceil(l.price * l.count * cfg.fee / 100);
        return `#${shCode} [${l.code}]${itemName} ×${l.count} — ${l.price * l.count}${l.currencyName}（+手续费${fee}）\n   └ 卖家：${l.sellerRole}`;
    });
    seal.replyToSender(ctx, msg, `🏬 二手市场（${listings.length}件）：\n${lines.join("\n")}\n\n💡 发送「二手市场 买 编号」购买`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["二手市场"] = cmd_market;

let cmd_draw = seal.ext.newCmdItemInfo();
cmd_draw.name = "抽取";
cmd_draw.help = "从抽取池获得物品\n抽取 —— 从第一个开放池抽取\n抽取 池子名 —— 从指定池子抽取";
cmd_draw.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const drRec = getPlayerDrawRec(platform, uid);
    if (!drRec) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const { records, key, rec } = drRec;
    const defs = getPoolDefs();
    const enabledPools = Object.values(defs).filter(p => p.enabled);
    if (!enabledPools.length) return seal.replyToSender(ctx, msg, "❌ 当前没有开放的抽取池。");
    let poolName = cmdArgs.getArgN(1);
    let pool;
    if (poolName) {
        pool = defs[poolName];
        if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
        if (!pool.enabled) return seal.replyToSender(ctx, msg, `❌ 池子「${poolName}」当前未开放。`);
    } else {
        pool = enabledPools[0];
        poolName = pool.name;
    }
    const config = getDrawConfig();
    const check = canDraw(rec, config, poolName);
    if (!check.ok) return seal.replyToSender(ctx, msg, `⚠️ ${check.reason}`);
    const reg = getRegistry();
    let drawnCode;
    if (pool.type === "fixed") {
        drawnCode = drawFromFixed(pool, reg);
    } else {
        drawnCode = drawFromFree(pool, defs);
    }
    if (!drawnCode) return seal.replyToSender(ctx, msg, `❌ 池子「${poolName}」已空。`);
    consumeDraw(rec, poolName);
    savePlayerDrawRec(records, key, rec);
    addToInv(roleKey, drawnCode, 1);
    const item = reg[drawnCode] || { name: drawnCode, desc: "" };
    const totalUsed = rec.used._total || 0;
    const totalBase = (config.total !== null && config.total !== undefined) ? config.total : "∞";
    seal.replyToSender(ctx, msg, `🎲 【${roleName}】从「${poolName}」抽到：[${drawnCode}]${item.name}\n描述：${item.desc}\n（今日总抽取：${totalUsed}/${totalBase}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["抽取"] = cmd_draw;

let cmd_draw_count = seal.ext.newCmdItemInfo();
cmd_draw_count.name = "我的抽取次数";
cmd_draw_count.help = "查看今日抽取次数情况";
cmd_draw_count.solve = (ctx, msg) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const drRec = getPlayerDrawRec(platform, uid);
    if (!drRec) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const { rec } = drRec;
    const config = getDrawConfig();
    const usedTotal = rec.used._total || 0;
    const extraTotal = rec.extra._total || 0;
    const totalBase = (config.total !== null && config.total !== undefined) ? config.total : null;
    const totalMax = totalBase !== null ? totalBase + extraTotal : null;
    const remaining = totalMax !== null ? Math.max(0, totalMax - usedTotal) : "∞";
    let text = `🎲 【${roleName}】今日抽取：\n总量：${usedTotal}/${totalMax !== null ? totalMax : "∞"}，剩余 ${remaining}`;
    if (extraTotal > 0) text += `（含额外 ${extraTotal} 次）`;
    const defs = getPoolDefs();
    for (const [pn, base] of Object.entries(config.pools || {})) {
        if (defs[pn]?.enabled) {
            const usedP = rec.used[pn] || 0;
            const extraP = rec.extra[pn] || 0;
            text += `\n  · ${pn}：${usedP}/${base + extraP}`;
        }
    }
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的抽取次数"] = cmd_draw_count;
ext.cmdMap["抽取次数"] = cmd_draw_count;

let cmd_bag = seal.ext.newCmdItemInfo();
cmd_bag.name = "我的背包";
cmd_bag.help = "查看自己的背包";
cmd_bag.solve = (ctx, msg) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    seal.replyToSender(ctx, msg, formatInventory(`${msg.platform}:${roleName}`, roleName, getRegistry()));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的背包"] = cmd_bag;
ext.cmdMap["背包"] = cmd_bag;

let cmd_item_detail = seal.ext.newCmdItemInfo();
cmd_item_detail.name = "物品详情";
cmd_item_detail.help = "查看物品详情\n物品详情 物品码或名称";
cmd_item_detail.solve = (ctx, msg, cmdArgs) => {
    const input = cmdArgs.getArgN(1);
    if (!input) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const item = findItem(reg, input);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未找到物品「${input}」`);
    const typeLabel = { item: "普通物品", currency: "货币", preset: "特殊道具" }[item.type] || item.type;
    let text = `📦 [${item.code}] ${item.name}\n类型：${typeLabel}\n描述：${item.desc}`;
    if (item.attrs) text += `\n属性效果：${item.attrs}`;
    const listing = getShop().find(s => s.code === item.code);
    if (listing) text += `\n🏪 商城售价：${listing.price}${listing.currencyName}`;
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["物品详情"] = cmd_item_detail;

// ========================
// 无前缀指令触发
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = msg.message.trim();
    const fa = (parts) => ({ getArgN: (n) => parts[n - 1] || "", args: parts });

    if (raw === "商城") return cmd_shop_view.solve(ctx, msg, fa([]));
    if (raw === "我的背包" || raw === "背包") return cmd_bag.solve(ctx, msg, fa([]));
    if (raw === "我的抽取次数" || raw === "抽取次数") return cmd_draw_count.solve(ctx, msg, fa([]));
    if (raw === "二手市场") return cmd_market.solve(ctx, msg, fa([]));

    if (raw.startsWith("抽取")) {
        const rest = raw.slice(2).trim();
        return cmd_draw.solve(ctx, msg, fa(rest ? [rest] : []));
    }
    if (raw.startsWith("购买")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts[0]) return cmd_buy.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("赠送物品")) {
        const parts = raw.slice(4).trim().split(/\s+/);
        if (parts.length >= 2) return cmd_give_item.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("使用")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts[0]) return cmd_use.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("售卖")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts.length >= 3) return cmd_sell.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("物品详情")) {
        const parts = raw.slice(4).trim().split(/\s+/);
        if (parts[0]) return cmd_item_detail.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("二手市场 买")) {
        const parts = raw.slice("二手市场".length).trim().split(/\s+/);
        return cmd_market.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("撤销卖单")) {
        const parts = raw.slice(4).trim().split(/\s+/);
        if (parts[0]) return cmd_cancel_sell.solve(ctx, msg, fa(parts));
    }
};
