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

// RPG 属性定义：{ attrName: { min, max, default, desc } }
// 兼容迁移旧格式 sys_attr_presets (数组) 和 item_valid_attrs (数组)
function getAttrDefs() {
    const main = getMain();
    if (!main) return {};
    let defs = {};
    try { defs = JSON.parse(main.storageGet("rpg_attr_defs") || "{}"); } catch(e) {}
    if (!Object.keys(defs).length) {
        let migrated = false;
        for (const key of ["sys_attr_presets", "item_valid_attrs"]) {
            try {
                const arr = JSON.parse(main.storageGet(key) || "[]");
                if (Array.isArray(arr)) arr.forEach(n => { if (n && !defs[n]) { defs[n] = { min: null, max: null, default: 0, desc: "" }; migrated = true; } });
            } catch(e) {}
        }
        if (migrated) {
            main.storageSet("rpg_attr_defs", JSON.stringify(defs));
            main.storageSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
        }
    }
    return defs;
}
function saveAttrDefs(defs) {
    const main = getMain();
    if (!main) return;
    main.storageSet("rpg_attr_defs", JSON.stringify(defs));
    // 保持 sys_attr_presets 同步，这样其他脚本调用时不会出错
    main.storageSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
}

// 角色属性数值：{ roleName: { attrName: value } }
function getCharAttrs() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("sys_character_attrs") || "{}") : {};
}
function modCharAttrs(platform, roleName, attrEffectStr) {
    if (!attrEffectStr) return;
    
    const charAttrs = getCharAttrs();
    const defs = getAttrDefs(); // 确保你有这个函数获取属性定义
    if (!charAttrs[roleName]) charAttrs[roleName] = {};

    const effects = attrEffectStr.split(/[,，]/);
    effects.forEach(eff => {
        const m = eff.trim().match(/^(.+?)([+\-]{1,2})(\d+)$/);
        if (m) {
            const [, aName, op, valStr] = m;
            const val = parseInt(valStr);
            const def = defs[aName];
            
            let currentVal = charAttrs[roleName][aName] ?? (def ? def.default : 0);
            const change = op.includes('-') ? -val : val;
            
            charAttrs[roleName][aName] = clampAttr(def, currentVal + change);
        }
    });
    
    saveCharAttrs(charAttrs);
}
function saveCharAttrs(attrs) {
    const main = getMain();
    if (main) main.storageSet("sys_character_attrs", JSON.stringify(attrs));
}

function clampAttr(def, value) {
    if (!def) return value;
    if (def.min !== null && def.min !== undefined && value < def.min) return def.min;
    if (def.max !== null && def.max !== undefined && value > def.max) return def.max;
    return value;
}

// RPG 属性系统辅助函数
function getAttrDefs() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("sys_attr_defs") || "{}") : {};
}
function saveAttrDefs(defs) {
    const main = getMain();
    if (main) main.storageSet("sys_attr_defs", JSON.stringify(defs));
}

function getCharAttrs() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("sys_character_attrs") || "{}") : {};
}
function saveCharAttrs(attrs) {
    const main = getMain();
    if (main) main.storageSet("sys_character_attrs", JSON.stringify(attrs));
}

function clampAttr(def, val) {
    if (def.max !== null && def.max !== undefined) {
        val = Math.min(val, def.max);
    }
    if (def.min !== null && def.min !== undefined) {
        val = Math.max(val, def.min);
    }
    return val;
}

// 合成系统
function getCraftRecipes() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("craft_recipes") || "{}") : {};
}
function saveCraftRecipes(recipes) {
    const main = getMain();
    if (main) main.storageSet("craft_recipes", JSON.stringify(recipes));
}

function getInvAll() {
    const main = getMain();
    return main ? JSON.parse(main.storageGet("global_inventories") || "{}") : {};
}
function saveInvAll(invs) {
    const main = getMain();
    if (main) main.storageSet("global_inventories", JSON.stringify(invs));
}

function saveInv(roleKey, inv) {
    const invs = getInvAll();
    invs[roleKey] = inv;
    saveInvAll(invs);
}
function getInv(roleKey) {
    return getInvAll()[roleKey] || [];
}
function addToInv(roleKey, code, count) {
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    const reg = getRegistry(); // 必须获取注册表
    const itemInfo = reg[code]; // 获取该物品的定义信息

    if (!itemInfo) {
        console.error(`[物品系统] 尝试添加不存在的物品代码: ${code}`);
        return;
    }

    // 获取该物品应有的初始次数 (如果注册表里没写，默认 -1 无限)
    const initialUses = itemInfo.maxUses ?? -1;

    // 查找背包里是否有【代码相同】且【剩余次数也相同】的物品进行堆叠
    // 这样可以区分"用过一半的"和"全新的"
    const entry = inv.find(e => e.code === code && (e.remainingUses ?? -1) === initialUses);

    if (entry) {
        entry.count += count;
    } else {
        inv.push({ 
            code, 
            count, 
            remainingUses: initialUses // 初始化剩余次数
        });
    }

    invs[roleKey] = inv;
    saveInvAll(invs);
}
function removeFromInv(roleKey, code, count) {
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    
    // 过滤出所有符合代码的项，按次数从高到低排序，确保扣除逻辑的一致性
    let entries = inv.filter(e => e.code === code).sort((a, b) => (b.remainingUses || 0) - (a.remainingUses || 0));
    
    let remainingToRemove = count;
    for (let entry of entries) {
        if (remainingToRemove <= 0) break;
        const take = Math.min(entry.count, remainingToRemove);
        entry.count -= take;
        remainingToRemove -= take;
    }

    // 清理数量归零的项
    const newInv = inv.filter(e => e.count > 0);
    invs[roleKey] = newInv;
    saveInvAll(invs);
    
    return remainingToRemove === 0;
}

function getInvCount(roleKey, code) {
    // 获取全部背包数据
    const allInv = getInvAll(); 
    // 获取该角色的背包数组，如果不存在则默认为空数组
    const roleInv = allInv[roleKey] || [];
    
    // 查找匹配 code 的物品条目
    const entry = roleInv.find(e => e.code === code);
    
    // 如果找到了返回 count，否则返回 0
    return entry ? (entry.count || 0) : 0;
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

function genItemCode(reg) {
    for (let d = 1; d < 10000; d++) {
        const code = `ITEM_${String(d).padStart(3, '0')}`;
        if (!reg[code]) return code;
    }
    return null;
}

function genInteractionCode(reg) {
    for (let d = 1; d < 10000; d++) {
        const code = `INTER_${String(d).padStart(3, '0')}`;
        if (!reg[code]) return code;
    }
    return null;
}

function genCurrencyCode(reg) {
    for (let d = 1; d < 10000; d++) {
        const code = `CUR_${String(d).padStart(3, '0')}`;
        if (!reg[code]) return code;
    }
    return null;
}

function genSecondhandCode(market) {
    for (let d = 1; d < 10000; d++) {
        const code = `MARK_${String(d).padStart(4, '0')}`;
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
    const changes = parseAttrEffects(changesStr);
    if (!Object.keys(changes).length) return;

    const reg = getRegistry();
    const defs = getAttrDefs();
    const currencyByName = {};
    for (const item of Object.values(reg)) {
        if (item.type === "currency") currencyByName[item.name] = item.code;
    }

    const roleKey = `${platform}:${roleName}`;
    const charAttrs = getCharAttrs();
    const roleAttrs = charAttrs[roleName] || {};
    let attrsChanged = false;

    for (const [attr, delta] of Object.entries(changes)) {
        if (currencyByName[attr]) {
            if (delta > 0) addToInv(roleKey, currencyByName[attr], delta);
            else if (delta < 0) removeFromInv(roleKey, currencyByName[attr], -delta);
        } else {
            const def = defs[attr];
            const cur = parseInt(roleAttrs[attr] ?? (def?.default ?? 0));
            roleAttrs[attr] = clampAttr(def, cur + delta);
            attrsChanged = true;
        }
    }

    if (attrsChanged) {
        charAttrs[roleName] = roleAttrs;
        saveCharAttrs(charAttrs);
    }
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
    if (!reg["SPEC_001"]) {
        reg["SPEC_001"] = { code: "SPEC_001", name: "追踪器", desc: "一枚散发着微光的微型追踪器，轻轻按动便能感知目标此刻的行踪。", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_002"]) {
        reg["SPEC_002"] = { code: "SPEC_002", name: "万能钥匙", desc: "一把泛着银光的万能钥匙，据说能开启世间任何一扇被锁住的门。", type: "preset", attrs: null };
        changed = true;
    }
    // 默认货币：金币、银币（按名称判断，避免重复注册）
    const currencyNames = new Set(Object.values(reg).filter(r => r.type === "currency").map(r => r.name));
    if (!currencyNames.has("金币")) {
        const code = genCurrencyCode(reg);
        if (code) { reg[code] = { code, name: "金币", desc: "流通于玩家间的基础货币。", type: "currency", attrs: null }; changed = true; }
    }
    if (!currencyNames.has("银币")) {
        const code = genCurrencyCode(reg);
        if (code) { reg[code] = { code, name: "银币", desc: "比金币更零碎的辅助货币。", type: "currency", attrs: null }; changed = true; }
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

    if (code === "SPEC_001") {
        const targetRole = cmdArgs.getArgN(2);
        if (!targetRole) return seal.replyToSender(ctx, msg, "🔍 请指定要追踪的角色：使用 SPEC_001 角色名");
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
            if (!timeArg) return seal.replyToSender(ctx, msg, "🔍 请指定追踪时间：使用 SPEC_001 角色名 时间（如 14 或 14:30）");
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
        if (!removeFromInv(roleKey, "SPEC_001", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的追踪器。");
        if (!isSuccess) return seal.replyToSender(ctx, msg, `🔍 信号干扰，定位失败。\n（追踪器已消耗）`);

        let resultMsg = `🔍 追踪到「${targetRole}」在 ${globalDay} ${matchingEvent.time} 出现在「${matchingEvent.place || "某处"}」`;
        if (showPartner && matchingEvent.partner && matchingEvent.partner !== "独自一人") resultMsg += `，与 ${matchingEvent.partner} 一起`;
        resultMsg += `。\n（追踪器已消耗）`;
        return seal.replyToSender(ctx, msg, resultMsg);
    }

    if (code === "SPEC_002") {
        const placeName = cmdArgs.args.slice(1).join(' ').trim();
        if (!placeName) return seal.replyToSender(ctx, msg, "🔑 请指定要兑换钥匙的地点：使用 SPEC_002 地点名");
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
        if (!removeFromInv(roleKey, "SPEC_002", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的万能钥匙。");
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
    if (log.length > 500) log.splice(0, log.length - 500);
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
cmd_reg_attr.help = `【管理员】注册/查看 RPG 属性
注册属性 列表
注册属性 名称                     无范围限制，默认值0
注册属性 名称 min max             有范围，默认值=min
注册属性 名称 min max default
注册属性 名称 min max default 描述`;
cmd_reg_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const defs = getAttrDefs();
    if (cmdArgs.getArgN(1) === "列表") {
        const attrs = getValidAttrs();
        return seal.replyToSender(ctx, msg, attrs.length ? `📋 已注册属性：${attrs.join("、")}` : "📋 暂无已注册属性。");
    }
    const newAttrs = [];
    for (let i = 1; ; i++) { const a = cmdArgs.getArgN(i); if (!a) break; newAttrs.push(a); }
    if (!newAttrs.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    // 检查是否与货币名冲突
    const reg = getRegistry();
    const currencyNames = new Set(Object.values(reg).filter(r => r.type === "currency").map(r => r.name));
    const conflicted = newAttrs.filter(a => currencyNames.has(a));
    if (conflicted.length) return seal.replyToSender(ctx, msg, `❌ 以下属性名已被货币占用：${conflicted.join("、")}`);

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
cmd_upload_item.help = "【管理员】注册新物品\n格式：名称*描述*次数*属性效果*允许二手\n次数：-1为无限，正数位次数\n效果：属性+10,属性-5 (支持多个，逗号隔开)\n允许二手：Y/N，默认N（不允许）\n支持多行批量上载";

cmd_upload_item.solve = (ctx, msg, cmdArgs) => {
    // 1. 权限校验
    const isAdmin = ctx.privilegeLevel >= 40 || seal.ext.isAdmin(ext, ctx.player.userId);
    if (!isAdmin) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rawMsg = msg.message.trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let itemLines;

    // 2. 解析多行输入
    if (msgParts.length > 1) {
        // 第一行是指令名，从第二行开始是数据
        itemLines = msgParts.slice(1).filter(l => l.trim());
    } else {
        // 单行输入处理
        const rest = rawMsg.replace(/^[。.]\s*上载物品\s*/, "").trim();
        itemLines = rest ? [rest] : [];
    }

    if (!itemLines.length) {
        const r = seal.ext.newCmdExecuteResult(true);
        r.showHelp = true;
        return r;
    }

    // 3. 获取注册表
    const reg = getRegistry();
    const results = [];

    for (const line of itemLines) {
        const parts = line.split(/[*＊]/);
        if (parts.length < 3) {
            results.push(`❌ 格式错误: 「${line.substring(0,10)}...」需包含名称、描述、次数`);
            continue;
        }

        const name = (parts[0] || "").trim();
        const desc = (parts[1] || "").trim() || "暂无描述";
        const maxUses = parseInt((parts[2] || "").trim());
        const attrs = (parts[3] || "").trim() || null;
        const canResell = ((parts[4] || "").trim().toUpperCase() === "Y");

        if (!name) { results.push(`❌ 名称不能为空`); continue; }
        if (isNaN(maxUses)) { results.push(`❌ 「${name}」次数参数必须是数字`); continue; }

        // 检查同名物品
        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) {
            results.push(`⚠️ 「${name}」已存在 [${existing.code}]，跳过`);
            continue;
        }

        // 生成唯一代码
        const code = genItemCode(reg);
        if (!code) {
            results.push("❌ 错误：代码空间已满，无法继续注册");
            break;
        }

        // 4. 写入注册表数据结构
        reg[code] = {
            code,
            name,
            desc,
            type: "item",
            maxUses: maxUses,
            attrs: attrs,
            price: 0,
            canResell: canResell
        };

        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        const resellText = canResell ? "✅ 可二手" : "❌ 不可二手";
        results.push(`✅ [${code}] ${name} | 次数:${useText} | 效果:[${attrs || "无"}] | ${resellText}`);
    }

    // 5. 保存并反馈
    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `📦 物品注册结果（共${itemLines.length}条）：\n${results.join("\n")}`);
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

let cmd_del_attr = seal.ext.newCmdItemInfo();
cmd_del_attr.name = "删除属性";
cmd_del_attr.help = "【管理员】删除已注册属性\n删除属性 名称";
cmd_del_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const name = cmdArgs.getArgN(1);
    if (!name) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getAttrDefs();
    if (!defs[name]) return seal.replyToSender(ctx, msg, `❌ 未找到属性「${name}」`);
    delete defs[name];
    saveAttrDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 属性「${name}」已删除（已有角色的数值不受影响）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除属性"] = cmd_del_attr;

let cmd_set_attr = seal.ext.newCmdItemInfo();
cmd_set_attr.name = "设置属性";
cmd_set_attr.help = "【管理员】直接设置角色属性值\n设置属性 角色名 属性名 值\n示例：设置属性 张三 体力 80";
cmd_set_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1), attrName = cmdArgs.getArgN(2), valStr = cmdArgs.getArgN(3);
    if (!roleName || !attrName || !valStr) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const val = parseInt(valStr);
    if (isNaN(val)) return seal.replyToSender(ctx, msg, "❌ 值必须为整数。");
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!apg[msg.platform]?.[roleName]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」`);
    const defs = getAttrDefs();
    const clamped = clampAttr(defs[attrName], val);
    const charAttrs = getCharAttrs();
    if (!charAttrs[roleName]) charAttrs[roleName] = {};
    charAttrs[roleName][attrName] = clamped;
    saveCharAttrs(charAttrs);
    const note = clamped !== val ? `（已截断至范围内：${clamped}）` : "";
    seal.replyToSender(ctx, msg, `✅ 【${roleName}】${attrName} 已设为 ${clamped}${note}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置属性"] = cmd_set_attr;

let cmd_shop_add = seal.ext.newCmdItemInfo();
cmd_shop_add.name = "上架商城";
cmd_shop_add.help = "【管理员】上架物品\n上架商城 物品码*价格货币名\n示例：上架商城 ITEM_001*10金币";
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
cmd_adjust.help = "【管理员】直接调整玩家背包数量\n调整 角色名 物品码 +N 或 -N\n示例：调整 张三 ITEM_001 +3";
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
cmd_give_item.name = "赠送道具";
cmd_give_item.help = "将背包中的物品送给其他玩家\n赠送道具 角色名 物品码 [数量]";
cmd_give_item.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const fromRoleKey = `${platform}:${roleName}`; // 赠送者Key
    
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
    const count = parseInt(cmdArgs.getArgN(3)) || 1;

    // 1. 基础校验
    if (isNaN(count) || count <= 0) return seal.replyToSender(ctx, msg, "❌ 赠送数量必须是正整数。");
    if (!targetName || !inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    if (targetName === roleName) return seal.replyToSender(ctx, msg, "⚠️ 不能赠送给自己。");

    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    
    // 2. 目标校验
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!apg[platform]?.[targetName]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
    const toRoleKey = `${platform}:${targetName}`; // 接收者Key

    // 3. 物品与次数校验
    const reg = getRegistry();
    const itemInfo = findItem(reg, inputCode);
    if (!itemInfo) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);

    // --- 核心修改：手动处理背包转移以保留 remainingUses ---
    let fromInv = getInv(fromRoleKey);
    let itemIdx = fromInv.findIndex(i => i.code === itemInfo.code);

    if (itemIdx === -1 || fromInv[itemIdx].count < count) {
        const has = itemIdx === -1 ? 0 : fromInv[itemIdx].count;
        return seal.replyToSender(ctx, msg, `❌ [${itemInfo.code}]${itemInfo.name} 不足（持有 ${has}，需要 ${count}）。`);
    }

    // 记录赠送者当前的剩余次数
    const currentRemaining = fromInv[itemIdx].remainingUses ?? (itemInfo.maxUses ?? -1);

    // 4. 执行扣除（从赠送者背包）
    fromInv[itemIdx].count -= count;
    if (fromInv[itemIdx].count <= 0) {
        fromInv.splice(itemIdx, 1);
    }
    saveInv(fromRoleKey, fromInv);

    // 5. 执行增加（到接收者背包）
    let toInv = getInv(toRoleKey);
    // 只有代码相同且剩余次数也相同的物品才堆叠，否则分两叠放（保证次数不被洗掉）
    let existing = toInv.find(i => i.code === itemInfo.code && i.remainingUses === currentRemaining);
    
    if (existing) {
        existing.count += count;
    } else {
        toInv.push({
            code: itemInfo.code,
            name: itemInfo.name,
            count: count,
            remainingUses: currentRemaining // 完美继承次数
        });
    }
    saveInv(toRoleKey, toInv);

    // 6. 反馈
    const usageText = (currentRemaining !== -1) ? `(余${currentRemaining}次)` : "";
    notifyPlayer(ctx, platform, targetName, `📦 「${roleName}」赠送给你 [${itemInfo.code}]${itemInfo.name}${usageText} ×${count}，已加入背包。`);
    seal.replyToSender(ctx, msg, `✅ 已将 [${itemInfo.code}]${itemInfo.name}${usageText} ×${count} 赠送给「${targetName}」。`);
    
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["赠送道具"] = cmd_give_item;

let cmd_use = seal.ext.newCmdItemInfo();
cmd_use.name = "使用";
cmd_use.help = "使用背包中的物品\n使用 物品码或名称 [参数]\n示例：\n使用 SPEC_001 张三 —— 追踪器\n使用 ITEM_001 —— 普通物品";

cmd_use.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const inputCode = cmdArgs.getArgN(1);

    if (!inputCode) { 
        const r = seal.ext.newCmdExecuteResult(true); 
        r.showHelp = true; 
        return r; 
    }

    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);

    // 检查是否为互动物品
    if (item.type === "interact") {
        return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 是互动物品，请使用「施加 目标名 ${item.code}」来对其他人使用。`);
    }

    // 1. 获取玩家背包，寻找该物品实例
    let inv = getInv(roleKey);
    let invIndex = inv.findIndex(i => i.code === item.code);

    if (invIndex === -1 || inv[invIndex].count <= 0) {
        return seal.replyToSender(ctx, msg, `❌ 背包中没有 [${item.code}]${item.name}。`);
    }

    let userItem = inv[invIndex];

    // 2. 特殊物品逻辑 (SPEC_001, SPEC_002)
    if (item.code === "SPEC_001" || item.code === "SPEC_002") {
        return handleSpecialItemUse(ctx, msg, platform, roleName, roleKey, item.code, cmdArgs);
    }

    // 3. 处理属性变更 (支持多属性同时影响)
    let effectReply = "";
    if (item.attrs) {
        // 调用你系统中的属性变更函数
        modCharAttrs(platform, roleName, item.attrs); 
        const changes = parseAttrEffects(item.attrs);
        effectReply = `\n📊 属性变化：${Object.entries(changes).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join("，")}`;
    }

    // 4. 【核心逻辑】处理使用次数扣减
    let usageStatus = "";
    
    // 如果 remainingUses 未定义(老数据)，则初始化为注册表的 maxUses
    if (userItem.remainingUses === undefined) {
        userItem.remainingUses = item.maxUses ?? -1;
    }

    if (userItem.remainingUses !== -1) {
        // 消耗一次次数
        userItem.remainingUses -= 1;

        if (userItem.remainingUses <= 0) {
            // 次数耗尽，扣除一个堆叠数量
            userItem.count -= 1;
            if (userItem.count <= 0) {
                inv.splice(invIndex, 1); // 彻底用光，移除物品
                usageStatus = "(已耗尽)";
            } else {
                // 如果还有叠层，重置次数到最大值
                userItem.remainingUses = item.maxUses;
                usageStatus = `(消耗1份，余${userItem.count}份)`;
            }
        } else {
            usageStatus = `(余${userItem.remainingUses}次)`;
        }
    } else {
        // 无限次数物品，使用即扣除 1 个数量
        userItem.count -= 1;
        if (userItem.count <= 0) {
            inv.splice(invIndex, 1);
        }
    }

    // 5. 保存背包更新
    saveInv(roleKey, inv);

    // 6. 记录日志并反馈
    logItemUsage(platform, roleName, item.code, item.name);
    let reply = `⚙️ 【${roleName}】使用了 [${item.code}]${item.name} ${usageStatus}。${effectReply}`;
    seal.replyToSender(ctx, msg, reply);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["使用"] = cmd_use;

let cmd_sell = seal.ext.newCmdItemInfo();
cmd_sell.name = "售卖";
cmd_sell.help = "将物品上架二手市场\n售卖 物品码 价格 货币名 [数量]\n示例：售卖 ITEM_001 8 金币 2";

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

    if (!inputCode || !priceStr || !currencyName) { 
        const r = seal.ext.newCmdExecuteResult(true); 
        r.showHelp = true; 
        return r; 
    }
    if (count <= 0 || isNaN(count)) return seal.replyToSender(ctx, msg, "❌ 数量必须为正整数。");

    const price = parseInt(priceStr);
    if (isNaN(price) || price <= 0) return seal.replyToSender(ctx, msg, "❌ 价格必须为正整数。");

    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);
    if (item.type === "preset") return seal.replyToSender(ctx, msg, "❌ 特殊道具不可在二手市场售卖。");
    if (!item.canResell) return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不允许在二手市场售卖。`);

    const currency = Object.values(reg).find(r => r.name === currencyName && r.type === "currency");
    if (!currency) return seal.replyToSender(ctx, msg, `❌ 未找到货币「${currencyName}」。`);

    // --- 核心逻辑修改：手动处理背包扣除，以获取 remainingUses ---
    let inv = getInv(roleKey);
    let invIndex = inv.findIndex(i => i.code === item.code);

    if (invIndex === -1 || inv[invIndex].count < count) {
        const has = invIndex === -1 ? 0 : inv[invIndex].count;
        return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不足（持有 ${has}，需要 ${count}）。`);
    }

    let userItem = inv[invIndex];
    // 获取该物品目前的剩余次数（如果是旧数据则取注册表默认值）
    const currentRemaining = userItem.remainingUses ?? (item.maxUses ?? -1);

    // 执行扣除
    userItem.count -= count;
    if (userItem.count <= 0) {
        inv.splice(invIndex, 1);
    }
    saveInv(roleKey, inv);

    // --- 写入市场数据 ---
    const market = getMarket();
    const shCode = genSecondhandCode(market);
    if (!shCode) return seal.replyToSender(ctx, msg, "❌ 二手市场编号已满。");

    market[shCode] = { 
        sellerRole: roleName, 
        code: item.code, 
        count: count, 
        price: price, 
        currencyCode: currency.code, 
        currencyName: currencyName, 
        listedAt: Date.now(),
        // 【新增字段】记录售卖时的剩余次数
        remainingUses: currentRemaining 
    };

    saveMarket(market);

    let usageText = (currentRemaining !== -1) ? `(余${currentRemaining}次)` : "";
    seal.replyToSender(ctx, msg, `✅ [${item.code}]${item.name}${usageText} ×${count} 已上架二手市场 #${shCode}\n售价：${price * count} ${currencyName}`);
    
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

    // --- 购买逻辑 ---
    if (action === "买") {
        const shCode = (cmdArgs.getArgN(2) || "").padStart(4, '0');
        const listing = market[shCode];
        if (!listing) return seal.replyToSender(ctx, msg, `❌ 未找到编号 #${shCode} 的卖单。`);

        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        if (listing.sellerRole === roleName) return seal.replyToSender(ctx, msg, "❌ 不能购买自己的卖单。");

        const platform = msg.platform;
        const buyerRoleKey = `${platform}:${roleName}`;
        const sellerRoleKey = `${platform}:${listing.sellerRole}`;

        // 计算费用
        const totalPrice = listing.price * listing.count;
        const fee = Math.ceil(totalPrice * cfg.fee / 100);
        const totalCost = totalPrice + fee;

        // 检查买家余额
        const hasCurrency = getInvCount(buyerRoleKey, listing.currencyCode);
        if (hasCurrency < totalCost) {
            return seal.replyToSender(ctx, msg, `❌ ${listing.currencyName}不足。需要 ${totalCost}（含费），持有 ${hasCurrency}。`);
        }

        // --- 执行交易 ---
        // 1. 扣除买家钱款
        removeFromInv(buyerRoleKey, listing.currencyCode, totalCost);
        // 2. 将原价（不含手续费）给卖家
        addToInv(sellerRoleKey, listing.currencyCode, totalPrice);

        // 3. 【核心修改】买家获得物品，且必须继承剩余次数
        let buyerInv = getInv(buyerRoleKey);
        const itemInfo = reg[listing.code];
        
        // 查找背包里是否有【代码相同】且【剩余次数也相同】的物品进行堆叠
        let existing = buyerInv.find(i => i.code === listing.code && i.remainingUses === listing.remainingUses);
        if (existing) {
            existing.count += listing.count;
        } else {
            buyerInv.push({
                code: listing.code,
                name: itemInfo?.name || listing.code,
                count: listing.count,
                remainingUses: listing.remainingUses ?? (itemInfo?.maxUses ?? -1)
            });
        }
        saveInv(buyerRoleKey, buyerInv);

        // 4. 清理市场单据
        delete market[shCode];
        saveMarket(market);

        const itemName = itemInfo?.name || listing.code;
        const usageText = (listing.remainingUses !== -1) ? `(余${listing.remainingUses}次)` : "";

        // 5. 通知与反馈
        notifyPlayer(ctx, platform, listing.sellerRole, `💰 卖单 #${shCode} [${listing.code}]${itemName}${usageText} ×${listing.count} 已售出，获得 ${totalPrice}${listing.currencyName}。`);
        seal.replyToSender(ctx, msg, `✅ 购买成功！获得 [${listing.code}]${itemName}${usageText} ×${listing.count}，花费 ${totalCost}${listing.currencyName}`);
        
        return seal.ext.newCmdExecuteResult(true);
    }

    // --- 查看逻辑 ---
    const listings = Object.entries(market);
    if (!listings.length) return seal.replyToSender(ctx, msg, "🏬 二手市场暂无在售物品。");

    const lines = listings.map(([shCode, l]) => {
        const itemInfo = reg[l.code];
        const itemName = itemInfo?.name || l.code;
        const fee = Math.ceil(l.price * l.count * cfg.fee / 100);
        
        // 增加剩余次数显示
        let usageText = "";
        if (l.remainingUses !== undefined && l.remainingUses !== -1) {
            usageText = `(余${l.remainingUses}次)`;
        }

        return `#${shCode} [${l.code}]${itemName}${usageText} ×${l.count} — ${l.price * l.count}${l.currencyName}\n   └ 卖家：${l.sellerRole}`;
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

let cmd_upload_recipe = seal.ext.newCmdItemInfo();
cmd_upload_recipe.name = "上传配方";
cmd_upload_recipe.help = "【管理员】注册合成配方\n格式：上传配方 目标物品名*材料名:数量,材料名:数量\n示例：上传配方 简易绷带*干净的布:2,酒精:1";
cmd_upload_recipe.solve = (ctx, msg, cmdArgs) => {
    if (ctx.privilegeLevel < 40) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rest = msg.message.replace(/^[。.]\s*上传配方\s*/, "").trim();
    if (!rest) return seal.ext.newCmdExecuteResult(true);

    const parts = rest.split(/[*＊]/);
    if (parts.length < 2) return seal.replyToSender(ctx, msg, "❌ 格式错误。需为：目标物品*材料1:数量,材料2:数量");

    const targetName = parts[0].trim();
    const ingredientsStr = parts[1].trim();

    const reg = getRegistry();
    const targetItem = Object.values(reg).find(i => i.name === targetName);
    if (!targetItem) return seal.replyToSender(ctx, msg, `❌ 未找到目标物品「${targetName}」`);

    const ingredients = [];
    const ingParts = ingredientsStr.split(/[,，]/);
    for (let p of ingParts) {
        const [name, count] = p.split(/[:：]/);
        const item = Object.values(reg).find(i => i.name === name.trim());
        if (!item) return seal.replyToSender(ctx, msg, `❌ 未找到材料「${name}」`);
        ingredients.push({ code: item.code, name: item.name, count: parseInt(count) || 1 });
    }

    const main = getMain();
    const recipes = JSON.parse(main.storageGet("item_recipes") || "{}");
    recipes[targetItem.code] = { targetCode: targetItem.code, targetName: targetItem.name, ingredients };
    main.storageSet("item_recipes", JSON.stringify(recipes));

    const ingText = ingredients.map(i => `${i.name}x${i.count}`).join(", ");
    seal.replyToSender(ctx, msg, `✅ 配方已注册：[${targetItem.name}] ← ${ingText}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传配方"] = cmd_upload_recipe;

let cmd_craft = seal.ext.newCmdItemInfo();
cmd_craft.name = "合成";
cmd_craft.help = "消耗材料制作物品\n格式：合成 物品名 [数量]\n示例：合成 简易绷带";
cmd_craft.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    
    const targetInput = cmdArgs.getArgN(1);
    const craftCount = parseInt(cmdArgs.getArgN(2)) || 1;
    if (!targetInput) return seal.replyToSender(ctx, msg, "❌ 请输入要合成的物品名。");

    const main = getMain();
    const recipes = JSON.parse(main.storageGet("item_recipes") || "{}");
    const reg = getRegistry();
    
    // 查找配方
    const recipe = Object.values(recipes).find(r => r.targetName === targetInput || r.targetCode === targetInput);
    if (!recipe) return seal.replyToSender(ctx, msg, `❌ 没有关于「${targetInput}」的配方。`);

    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const inv = getInv(roleKey);

    // 1. 检查材料是否充足
    for (let ing of recipe.ingredients) {
        const needed = ing.count * craftCount;
        const owned = getInvCount(roleKey, ing.code);
        if (owned < needed) {
            return seal.replyToSender(ctx, msg, `❌ 材料不足：需要 ${ing.name}x${needed}，当前仅有 ${owned}。`);
        }
    }

    // 2. 扣除材料
    for (let ing of recipe.ingredients) {
        removeFromInv(roleKey, ing.code, ing.count * craftCount);
    }

    // 3. 增加产物 (继承注册表的初始次数)
    const targetItemInfo = reg[recipe.targetCode];
    addToInv(roleKey, recipe.targetCode, craftCount);

    seal.replyToSender(ctx, msg, `🛠️ 合成成功！消耗材料制作了 [${recipe.targetName}] x${craftCount}。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["合成"] = cmd_craft;

let cmd_recipe_list = seal.ext.newCmdItemInfo();
cmd_recipe_list.name = "查看配方";
cmd_recipe_list.solve = (ctx, msg, cmdArgs) => {
    const main = getMain();
    const recipes = JSON.parse(main.storageGet("item_recipes") || "{}");
    const list = Object.values(recipes);
    if (!list.length) return seal.replyToSender(ctx, msg, "📜 暂无已知配方。");

    const lines = list.map(r => `• ${r.targetName}: ${r.ingredients.map(i => `${i.name}x${i.count}`).join(" + ")}`);
    seal.replyToSender(ctx, msg, `📜 已知配方列表：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看配方"] = cmd_recipe_list;

let cmd_upload_interact = seal.ext.newCmdItemInfo();
cmd_upload_interact.name = "上载互动物品";
cmd_upload_interact.help = "【管理员】注册互动类物品（对他人使用）\n格式：名称*描述*次数*属性效果*允许二手\n次数：-1为无限，正数位次数\n效果：属性+10,属性-5 (支持多个，逗号隔开)\n允许二手：Y/N，默认N（不允许）\n示例：上载互动物品 医疗包*为他人包扎*1*体力+50*Y";
cmd_upload_interact.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rawMsg = msg.message.trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let itemLines;

    // 解析多行输入
    if (msgParts.length > 1) {
        itemLines = msgParts.slice(1).filter(l => l.trim());
    } else {
        const rest = rawMsg.replace(/^[。.]\s*上载互动物品\s*/, "").trim();
        itemLines = rest ? [rest] : [];
    }

    if (!itemLines.length) {
        const r = seal.ext.newCmdExecuteResult(true);
        r.showHelp = true;
        return r;
    }

    const reg = getRegistry();
    const results = [];

    for (const line of itemLines) {
        const parts = line.split(/[*＊]/);
        if (parts.length < 3) {
            results.push(`❌ 格式错误: 「${line.substring(0,10)}...」需包含名称、描述、次数`);
            continue;
        }

        const name = (parts[0] || "").trim();
        const desc = (parts[1] || "").trim() || "暂无描述";
        const maxUses = parseInt((parts[2] || "").trim());
        const attrs = (parts[3] || "").trim() || null;
        const canResell = ((parts[4] || "").trim().toUpperCase() === "Y");

        if (!name) { results.push(`❌ 名称不能为空`); continue; }
        if (isNaN(maxUses)) { results.push(`❌ 「${name}」次数参数必须是数字`); continue; }

        // 检查同名物品
        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) {
            results.push(`⚠️ 「${name}」已存在 [${existing.code}]，跳过`);
            continue;
        }

        // 生成唯一代码
        const code = genInteractionCode(reg);
        if (!code) {
            results.push("❌ 错误：代码空间已满，无法继续注册");
            break;
        }

        // 写入注册表
        reg[code] = {
            code,
            name,
            desc,
            type: "interact",
            maxUses: maxUses,
            attrs: attrs,
            price: 0,
            canResell: canResell
        };

        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        const resellText = canResell ? "✅ 可二手" : "❌ 不可二手";
        results.push(`✅ [${code}] ${name} | 次数:${useText} | 效果:[${attrs || "无"}] | ${resellText}`);
    }

    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `🎭 互动物品注册结果（共${itemLines.length}条）：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上载互动物品"] = cmd_upload_interact;

function isApplyTimeValid(main) {
    const hoursStr = main.storageGet("apply_item_hours");
    if (!hoursStr) return true; // 未设置则全天可用

    const now = new Date();
    const currentHour = now.getHours(); // 获取当前现实小时 (0-23)
    
    // 解析 9-12,14-18 这种格式
    const periods = hoursStr.split(/[,，]/);
    for (let p of periods) {
        const [start, end] = p.split('-').map(v => parseInt(v));
        if (!isNaN(start) && !isNaN(end)) {
            if (currentHour >= start && currentHour < end) return true;
        } else if (!isNaN(start)) { // 处理单小时配置
            if (currentHour === start) return true;
        }
    }
    return false;
}

let cmd_apply = seal.ext.newCmdItemInfo();
cmd_apply.name = "施加";
cmd_apply.help = "对他人使用互动道具\n格式：施加 目标姓名 物品名/代码\n查看设置：施加 设置 或 施加 查看\n示例：施加 张三 医疗包";
cmd_apply.solve = (ctx, msg, cmdArgs) => {
    const main = getMain();
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);

    // 显示施加设置
    if (!targetName || targetName === "设置" || targetName === "查看") {
        const applyNotify = main.storageGet("apply_item_notification") !== "false";
        const exposeRate = parseInt(main.storageGet("apply_item_expose_rate") || "0");
        const applyHours = main.storageGet("apply_item_hours") || "不限";

        const results = [
            "【互动物品施加设置】",
            `施加是否提醒：${applyNotify ? '开启' : '关闭'} (${applyNotify ? '告知对方' : '不告知对方'})`,
            `暴露名字概率：${exposeRate}% (${exposeRate === 0 ? '完全匿名' : exposeRate === 100 ? '完全暴露' : '随机暴露'})`,
            `施加可用时段：${applyHours}`,
        ];
        return seal.replyToSender(ctx, msg, results.join('\n'));
    }

    // --- 新增：时段检查 ---
    if (!isApplyTimeValid(main)) {
        const hoursStr = main.storageGet("apply_item_hours");
        return seal.replyToSender(ctx, msg, `❌ 当前不在道具施加时段内。\n当前可用时段：${hoursStr}`);
    }
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    if (!targetName || !inputCode) {
        const r = seal.ext.newCmdExecuteResult(true);
        r.showHelp = true;
        return r;
    }

    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const reg = getRegistry();
    const item = findItem(reg, inputCode);

    // 1. 基础校验
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);
    if (item.type !== "interact") return seal.replyToSender(ctx, msg, `⚠️ [${item.name}] 不是互动类物品，请使用「.使用」指令。`);

    // 2. 检查目标是否存在
    const apg = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!apg[platform]?.[targetName]) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);

    // 3. 检查发起者背包
    let inv = getInv(roleKey);
    let invIndex = inv.findIndex(i => i.code === item.code);
    if (invIndex === -1 || inv[invIndex].count <= 0) {
        return seal.replyToSender(ctx, msg, `❌ 你的背包里没有 [${item.code}]${item.name}。`);
    }

    // 4. 执行效果 (施加给目标)
    if (item.attrs) {
        modCharAttrs(platform, targetName, item.attrs);
    }

    // 5. 扣除发起者的消耗次数
    let userItem = inv[invIndex];
    let usageStatus = "";
    if (userItem.remainingUses !== -1) {
        userItem.remainingUses--;
        if (userItem.remainingUses <= 0) {
            userItem.count--;
            if (userItem.count <= 0) {
                inv.splice(invIndex, 1);
                usageStatus = "(已耗尽)";
            } else {
                userItem.remainingUses = item.maxUses;
                usageStatus = `(消耗1份，余${userItem.count}份)`;
            }
        } else {
            usageStatus = `(余${userItem.remainingUses}次)`;
        }
    } else {
        userItem.count--;
        if (userItem.count <= 0) inv.splice(invIndex, 1);
    }

    // 6. 保存数据
    saveInv(roleKey, inv);

    // 7. 渲染反馈
    const changes = parseAttrEffects(item.attrs);
    const effectStr = Object.entries(changes).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join("，");
    const main = getMain();
    const shouldNotify = main.storageGet("apply_item_notification") !== "false";
    const exposeRate = parseInt(main.storageGet("apply_item_expose_rate") || "0");
    const isExposed = Math.random() * 100 < exposeRate;

    // 通知被施加者
    if (shouldNotify) {
        // 根据概率决定是否暴露名字
        const displayName = isExposed ? `角色「${roleName}」` : "某人";

        notifyPlayer(ctx, platform, targetName, `💉 ${displayName} 对你使用了 [${item.name}]！\n📊 你的属性变化：${effectStr}`);
    }

    // 给发起者的反馈（发起者始终能看到详细信息）
    let feedback = `✅ 你成功对「${targetName}」使用了 [${item.name}] ${usageStatus}。`;
    if (!shouldNotify) {
        feedback += "\n(已根据设置隐藏对目标的通知)";
    } else {
        feedback += `\n(暴露概率：${exposeRate}%，本次${isExposed ? "已暴露名字" : "保持匿名"})`;
    }
    feedback += `\n📊 目标属性变化：${effectStr}`;

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["施加"] = cmd_apply;

// ========================
// 合成系统
// ========================

let cmd_reg_craft = seal.ext.newCmdItemInfo();
cmd_reg_craft.name = "注册合成";
cmd_reg_craft.help = "【管理员】注册合成配方\n注册合成 产物代码*描述*材料代码1:数量1,材料代码2:数量2[*限制条件]\n限制格式：attr:属性名:最小值,currency:货币名:最小值\n示例：注册合成 高级丹*升级丹药*初级丹:3,金币:100*attr:体力:50,currency:金币:50";
cmd_reg_craft.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const raw = cmdArgs.getArgN(1);
    if (!raw) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const parts = raw.split(/[*＊]/);
    const outputCode = (parts[0] || "").trim();
    const desc = (parts[1] || "").trim();
    const materialsStr = (parts[2] || "").trim();
    const limitsStr = (parts[3] || "").trim();

    if (!outputCode || !materialsStr) return seal.replyToSender(ctx, msg, "❌ 格式错误，至少需要产物代码和材料。");

    const reg = getRegistry();
    if (!reg[outputCode]) return seal.replyToSender(ctx, msg, `❌ 产物代码 [${outputCode}] 不存在。`);

    // 解析材料
    const materials = {};
    const matParts = materialsStr.split(",");
    for (const mat of matParts) {
        const [code, countStr] = mat.split(":").map(s => s.trim());
        if (!code || !countStr) return seal.replyToSender(ctx, msg, "❌ 材料格式错误，应为 代码:数量");
        const count = parseInt(countStr);
        if (isNaN(count) || count <= 0) return seal.replyToSender(ctx, msg, "❌ 材料数量必须为正整数。");
        if (!reg[code]) return seal.replyToSender(ctx, msg, `❌ 材料代码 [${code}] 不存在。`);
        materials[code] = count;
    }

    // 解析限制条件
    const limits = { attrs: {}, currencies: {} };
    if (limitsStr) {
        const limitParts = limitsStr.split(",");
        for (const limit of limitParts) {
            const [type, name, valueStr] = limit.split(":").map(s => s.trim());
            if (!type || !name || !valueStr) return seal.replyToSender(ctx, msg, "❌ 限制格式错误，应为 type:名称:数值");
            const value = parseInt(valueStr);
            if (isNaN(value)) return seal.replyToSender(ctx, msg, "❌ 限制数值必须为整数。");

            if (type === "attr") {
                limits.attrs[name] = value;
            } else if (type === "currency") {
                limits.currencies[name] = value;
            } else {
                return seal.replyToSender(ctx, msg, "❌ 限制类型应为 attr 或 currency");
            }
        }
    }

    const recipes = getCraftRecipes();
    recipes[outputCode] = { materials, output: outputCode, desc: desc || "暂无描述", limits };
    saveCraftRecipes(recipes);

    const matStr = Object.entries(materials).map(([c, cnt]) => `${reg[c].name}×${cnt}`).join(" + ");
    let msg_text = `✅ 合成配方已注册：${matStr} → ${reg[outputCode].name}`;
    if (desc) msg_text += `\n📝 ${desc}`;
    if (Object.keys(limits.attrs).length || Object.keys(limits.currencies).length) {
        msg_text += "\n⚠️ 限制条件：";
        for (const [attr, val] of Object.entries(limits.attrs)) msg_text += `\n  · ${attr} ≥ ${val}`;
        for (const [curr, val] of Object.entries(limits.currencies)) msg_text += `\n  · ${curr} ≥ ${val}`;
    }
    seal.replyToSender(ctx, msg, msg_text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["注册合成"] = cmd_reg_craft;

let cmd_view_craft = seal.ext.newCmdItemInfo();
cmd_view_craft.name = "查看合成";
cmd_view_craft.help = "查看所有合成配方\n查看合成 [搜索关键词]";
cmd_view_craft.solve = (ctx, msg, cmdArgs) => {
    const recipes = getCraftRecipes();
    const reg = getRegistry();
    if (!Object.keys(recipes).length) return seal.replyToSender(ctx, msg, "📋 暂无合成配方。");

    const filter = cmdArgs.getArgN(1) || "";
    const filtered = Object.entries(recipes).filter(([code]) => !filter || code.includes(filter) || reg[code]?.name.includes(filter));

    if (!filtered.length) return seal.replyToSender(ctx, msg, `📋 未找到包含「${filter}」的配方。`);

    const lines = filtered.map(([code, recipe]) => {
        const matStr = Object.entries(recipe.materials).map(([c, cnt]) => `${reg[c]?.name || c}×${cnt}`).join(" + ");
        let line = `[${code}] ${reg[code]?.name || code}`;
        if (recipe.desc && recipe.desc !== "暂无描述") line += ` - ${recipe.desc}`;
        line += `\n   ← ${matStr}`;

        const limits = recipe.limits || {};
        if (Object.keys(limits.attrs || {}).length || Object.keys(limits.currencies || {}).length) {
            line += "\n   ⚠️ 需求：";
            for (const [attr, val] of Object.entries(limits.attrs || {})) line += ` ${attr}≥${val},`;
            for (const [curr, val] of Object.entries(limits.currencies || {})) line += ` ${curr}≥${val},`;
            line = line.slice(0, -1);
        }
        return line;
    });
    seal.replyToSender(ctx, msg, `📋 合成配方（${filtered.length}/${Object.keys(recipes).length}）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看合成"] = cmd_view_craft;

// ========================
// 无前缀指令触发
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = msg.message.trim();
    const fa = (parts) => ({ getArgN: (n) => parts[n - 1] || "", args: parts });
    const isAdmin = isUserAdmin(ctx, msg);
    const platform = msg.platform;

    // ── RPG 属性 ──

    // 我的状态
    if (raw === "我的状态") {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 未绑定角色");
        const defs = getAttrDefs();
        const charAttrs = getCharAttrs();
        const roleAttrs = charAttrs[roleName] || {};
        const attrNames = Object.keys(defs);
        if (!attrNames.length) return seal.replyToSender(ctx, msg, `🎭 【${roleName}】暂无属性，管理员可用「我创建属性」添加。`);
        const BAR = 10;
        const lines = attrNames.map(name => {
            const def = defs[name];
            const val = roleAttrs[name] ?? (def.default ?? 0);
            if (def.max !== null && def.max !== undefined && def.min !== null) {
                const pct = def.max === def.min ? 1 : (val - def.min) / (def.max - def.min);
                const filled = Math.round(Math.max(0, Math.min(1, pct)) * BAR);
                const bar = "█".repeat(filled) + "░".repeat(BAR - filled);
                return `${name}  ${bar}  ${val}/${def.max}`;
            }
            return `${name}  ${val}${def.min !== null ? `（最低${def.min}）` : ""}`;
        });
        return seal.replyToSender(ctx, msg, `🎭 【${roleName}】的状态\n${"━".repeat(14)}\n${lines.join("\n")}`);
    }

    // 我创建属性（管理员，无前缀）
    if (raw.startsWith("我创建属性") && isAdmin) {
        const rest = raw.slice(5).trim().split(/\s+/);
        return cmd_reg_attr.solve(ctx, msg, fa(rest.length && rest[0] ? rest : [""]));
    }

    // 角色:属性++值 / 角色:属性--值 / 角色:货币++值（管理员批量改属性或货币）
    if (isAdmin) {
        const attrM = raw.match(/^(.+?)[:：](.+?)([+\-]{2})([\d、,，]+)$/);
        if (attrM) {
            const [, rolesPart, attrName, op, valsPart] = attrM;
            const main = getMain();
            if (!main) return;
            const priv = JSON.parse(main.storageGet("a_private_group") || "{}")[platform] || {};
            const roles = rolesPart === "全体" ? Object.keys(priv) : rolesPart.split(/[、,，]/).map(r => r.trim());
            const vals = valsPart.split(/[、,，]/).map(v => parseInt(v));
            const res = [];

            // 检查是属性还是货币
            const defs = getAttrDefs();
            const reg = getRegistry();
            const currencyCode = Object.entries(reg).find(([_, info]) => info.type === "currency" && info.name === attrName)?.[0];

            if (defs[attrName]) {
                // 处理属性
                const charAttrs = getCharAttrs();
                roles.forEach((r, i) => {
                    if (!priv[r]) return;
                    if (!charAttrs[r]) charAttrs[r] = {};
                    const v = isNaN(vals[i]) ? vals[0] : vals[i];
                    const old = charAttrs[r][attrName] ?? (defs[attrName].default ?? 0);
                    const next = clampAttr(defs[attrName], op === "++" ? old + v : old - v);
                    charAttrs[r][attrName] = next;
                    res.push(`${r}：${old}→${next}`);
                });
                if (res.length) {
                    saveCharAttrs(charAttrs);
                    return seal.replyToSender(ctx, msg, `${op === "++" ? "📈" : "📉"} ${attrName} 变更：\n${res.join("\n")}`);
                }
            } else if (currencyCode) {
                // 处理货币
                roles.forEach((r, i) => {
                    if (!priv[r]) return;
                    const roleKey = `${platform}:${r}`;
                    const v = isNaN(vals[i]) ? vals[0] : vals[i];
                    const inv = getInv(roleKey);
                    const entry = inv.find(e => e.code === currencyCode);
                    const old = entry?.count || 0;
                    if (op === "++") {
                        addToInv(roleKey, currencyCode, v);
                    } else {
                        removeFromInv(roleKey, currencyCode, Math.min(v, old));
                    }
                    const newEntry = getInv(roleKey).find(e => e.code === currencyCode);
                    const next = newEntry?.count || 0;
                    res.push(`${r}：${old}→${next}`);
                });
                if (res.length) {
                    return seal.replyToSender(ctx, msg, `${op === "++" ? "📈" : "📉"} ${attrName} 变更：\n${res.join("\n")}`);
                }
            }
        }
    }

    // ── 合成系统 ──
    if (raw === "合成列表") {
        return cmd_view_craft.solve(ctx, msg, fa([]));
    }
    if (raw.startsWith("合成")) {
        const rest = raw.slice(2).trim();
        if (rest) {
            // 格式：合成 产物代码 或 合成 产物代码 数量
            const craftParts = rest.split(/\s+/);
            const outputCode = craftParts[0];
            const count = craftParts[1] ? parseInt(craftParts[1]) : 1;

            const roleName = getRoleName(ctx, msg);
            if (!roleName) return seal.replyToSender(ctx, msg, "❌ 未绑定角色");

            const recipes = getCraftRecipes();
            const recipe = recipes[outputCode];
            if (!recipe) return seal.replyToSender(ctx, msg, `❌ 合成配方 [${outputCode}] 不存在`);

            const reg = getRegistry();
            const roleKey = `${platform}:${roleName}`;
            const inv = getInv(roleKey);
            const charAttrs = getCharAttrs();
            const roleAttrs = charAttrs[roleName] || {};
            const defs = getAttrDefs();

            // 检查限制条件
            const limits = recipe.limits || {};
            const unmet = [];
            for (const [attr, minVal] of Object.entries(limits.attrs || {})) {
                const have = roleAttrs[attr] || 0;
                if (have < minVal) unmet.push(`${attr} 需≥${minVal}（当前${have}）`);
            }
            for (const [currencyName, minVal] of Object.entries(limits.currencies || {})) {
                const currencyCode = Object.entries(reg).find(([_, info]) => info.type === "currency" && info.name === currencyName)?.[0];
                if (currencyCode) {
                    const currEntry = inv.find(e => e.code === currencyCode);
                    const have = currEntry?.count || 0;
                    if (have < minVal) unmet.push(`${currencyName} 需≥${minVal}（当前${have}）`);
                }
            }
            if (unmet.length) {
                return seal.replyToSender(ctx, msg, `❌ 不满足合成条件：\n${unmet.join("\n")}`);
            }

            // 检查材料是否足够
            const lacking = [];
            for (const [matCode, matCount] of Object.entries(recipe.materials)) {
                const needed = matCount * count;
                const matEntry = inv.find(e => e.code === matCode);
                const have = matEntry?.count || (roleAttrs[matCode] || 0);
                if (have < needed) {
                    lacking.push(`${reg[matCode]?.name || matCode} (需${needed}，只有${have})`);
                }
            }
            if (lacking.length) {
                return seal.replyToSender(ctx, msg, `❌ 材料不足：\n${lacking.join("\n")}`);
            }

            // 扣除材料
            for (const [matCode, matCount] of Object.entries(recipe.materials)) {
                const matEntry = inv.find(e => e.code === matCode);
                if (matEntry) {
                    removeFromInv(roleKey, matCode, matCount * count);
                } else if (defs[matCode]) {
                    const oldVal = roleAttrs[matCode] || 0;
                    roleAttrs[matCode] = oldVal - matCount * count;
                }
            }
            if (Object.keys(roleAttrs).length) {
                charAttrs[roleName] = roleAttrs;
                saveCharAttrs(charAttrs);
            }

            // 给予产物
            addToInv(roleKey, outputCode, count);

            const matStr = Object.entries(recipe.materials)
                .map(([c, cnt]) => `${reg[c]?.name || c}×${cnt * count}`)
                .join(" + ");
            return seal.replyToSender(ctx, msg, `✨ 合成成功！\n消耗：${matStr}\n获得：${reg[outputCode]?.name || outputCode}×${count}`);
        }
    }

    // ── 道具 ──
    if (raw === "商城") return cmd_shop_view.solve(ctx, msg, fa([]));
    if (raw === "我的背包" || raw === "背包") return cmd_bag.solve(ctx, msg, fa([]));
    if (raw === "我的抽取次数" || raw === "抽取次数") return cmd_draw_count.solve(ctx, msg, fa([]));
    if (raw === "二手市场") return cmd_market.solve(ctx, msg, fa([]));


    if (raw.startsWith("抽取")) {
        const rest = raw.slice(2).trim();
        return cmd_draw.solve(ctx, msg, fa(rest ? [rest] : []));
    }
    // 新增：合成 (支持 合成 物品名 [数量])
    if (raw.startsWith("合成")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts[0]) return cmd_craft.solve(ctx, msg, fa(parts));
    }

    // 新增：施加 (支持 施加 目标 物品)
    if (raw.startsWith("施加")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts.length >= 2) return cmd_apply.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("购买")) {
        const parts = raw.slice(2).trim().split(/\s+/);
        if (parts[0]) return cmd_buy.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("赠送道具")) {
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

    // ── RPG 属性 ──

    // 我的状态
    if (raw === "我的状态") {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 未绑定角色");
        const defs = getAttrDefs();
        const charAttrs = getCharAttrs();
        const roleAttrs = charAttrs[roleName] || {};
        const attrNames = Object.keys(defs);
        if (!attrNames.length) return seal.replyToSender(ctx, msg, `🎭 【${roleName}】暂无属性，管理员可用「我创建属性」添加。`);
        const BAR = 10;
        const lines = attrNames.map(name => {
            const def = defs[name];
            const val = roleAttrs[name] ?? (def.default ?? 0);
            if (def.max !== null && def.max !== undefined && def.min !== null) {
                const pct = def.max === def.min ? 1 : (val - def.min) / (def.max - def.min);
                const filled = Math.round(Math.max(0, Math.min(1, pct)) * BAR);
                const bar = "█".repeat(filled) + "░".repeat(BAR - filled);
                return `${name}  ${bar}  ${val}/${def.max}`;
            }
            return `${name}  ${val}${def.min !== null ? `（最低${def.min}）` : ""}`;
        });
        return seal.replyToSender(ctx, msg, `🎭 【${roleName}】的状态\n${"━".repeat(14)}\n${lines.join("\n")}`);
    }

    // 我创建属性（管理员，无前缀）
    if (raw.startsWith("我创建属性") && isAdmin) {
        const rest = raw.slice(5).trim().split(/\s+/);
        return cmd_reg_attr.solve(ctx, msg, fa(rest.length && rest[0] ? rest : [""]));
    }

    // 角色:属性++值 / 角色:属性--值（管理员批量改属性）
    if (isAdmin) {
        const attrM = raw.match(/^(.+?)[:：](.+?)([+\-]{2})([\d、,，]+)$/);
        if (attrM) {
            const [, rolesPart, attrName, op, valsPart] = attrM;
            const defs = getAttrDefs();
            if (defs[attrName]) {
                const main = getMain();
                if (!main) return;
                const priv = JSON.parse(main.storageGet("a_private_group") || "{}")[platform] || {};
                const roles = rolesPart === "全体" ? Object.keys(priv) : rolesPart.split(/[、,，]/).map(r => r.trim());
                const vals = valsPart.split(/[、,，]/).map(v => parseInt(v));
                const charAttrs = getCharAttrs();
                const res = [];
                roles.forEach((r, i) => {
                    if (!priv[r]) return;
                    if (!charAttrs[r]) charAttrs[r] = {};
                    const v = isNaN(vals[i]) ? vals[0] : vals[i];
                    const old = charAttrs[r][attrName] ?? (defs[attrName].default ?? 0);
                    const next = clampAttr(defs[attrName], op === "++" ? old + v : old - v);
                    charAttrs[r][attrName] = next;
                    res.push(`${r}：${old}→${next}`);
                });
                if (res.length) {
                    saveCharAttrs(charAttrs);
                    return seal.replyToSender(ctx, msg, `${op === "++" ? "📈" : "📉"} ${attrName} 变更：\n${res.join("\n")}`);
                }
            }
        }
    }
};

// ========================
// 同步踩点池命令
// ========================

let cmd_sync_spot_pools = seal.ext.newCmdItemInfo();
cmd_sync_spot_pools.name = "同步踩点池";
cmd_sync_spot_pools.help = "【管理员】同步地点系统中的所有地点到抽取池\n同步踩点池\n  将自动为每个地点创建相应的池子（若已存在则跳过）\n  不删除任何已有的池子";
cmd_sync_spot_pools.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 读取地点系统配置（检查是否启用）
    let placeSystemEnabled = true;
    try {
        const placeConfig = JSON.parse(main.storageGet("place_system_config") || "{}");
        placeSystemEnabled = placeConfig.enabled !== false;
    } catch(e) {}

    if (!placeSystemEnabled) {
        return seal.replyToSender(ctx, msg, "⚠️ 地点系统未启用，无法同步踩点池。");
    }

    // 读取所有地点
    let places = {};
    try {
        places = JSON.parse(main.storageGet("available_places") || "{}");
    } catch(e) {
        return seal.replyToSender(ctx, msg, "❌ 无法读取地点数据。");
    }

    if (Object.keys(places).length === 0) {
        return seal.replyToSender(ctx, msg, "⚠️ 地点系统中没有地点数据。");
    }

    // 获取当前的池子定义
    const poolDefs = getPoolDefs();

    let created = [];
    let skipped = [];

    // 为每个地点创建对应的池子（如果不存在）
    for (const placeName in places) {
        const poolName = `${placeName}池`;

        if (poolDefs[poolName]) {
            skipped.push(placeName);
        } else {
            // 创建新的固定池
            poolDefs[poolName] = {
                name: poolName,
                type: "fixed",
                items: [],
                enabled: true
            };
            created.push(placeName);
        }
    }

    // 保存更新后的池子定义
    savePoolDefs(poolDefs);

    let resultMsg = "✅ 踩点池同步完成！\n";
    if (created.length > 0) {
        resultMsg += `\n📝 新建池子 (${created.length})：\n` + created.map(p => `  · ${p}池`).join("\n");
    }
    if (skipped.length > 0) {
        resultMsg += `\n⏭️  已存在，跳过 (${skipped.length})：\n` + skipped.map(p => `  · ${p}池`).join("\n");
    }
    resultMsg += `\n\n💡 现在可使用「上架池子」命令向这些池子添加物品。`;

    seal.replyToSender(ctx, msg, resultMsg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步踩点池"] = cmd_sync_spot_pools;

// ========================
// 攻防系统 - 存储和配置
// ========================

function getAttackDefenseConfig() {
    const main = getMain();
    if (!main) return {};
    try {
        return JSON.parse(main.storageGet("attack_defense_config") || "{}");
    } catch(e) { return {}; }
}

function saveAttackDefenseConfig(config) {
    const main = getMain();
    if (main) main.storageSet("attack_defense_config", JSON.stringify(config));
}

function getAttackDefenseData() {
    const main = getMain();
    if (!main) return { battles: {}, playerStats: {}, skills: {} };
    try {
        return JSON.parse(main.storageGet("attack_defense_data") || "{}");
    } catch(e) { return { battles: {}, playerStats: {}, skills: {} }; }
}

function saveAttackDefenseData(data) {
    const main = getMain();
    if (main) main.storageSet("attack_defense_data", JSON.stringify(data));
}

// 初始化玩家战斗属性
function initPlayerBattleAttrs(name) {
    return {
        ATK: 50,      // 攻击力
        DEF: 30,      // 防御力
        AGI: 40,      // 敏捷
        HP: 100,      // 生命值
        TMP_SHIELD: 0, // 临时盾
        MP: 50,       // 魔法值
        MP_REGEN: 5   // 每回合魔法恢复
    };
}

// 获取玩家当前属性
function getPlayerBattleAttrs(name) {
    const data = getAttackDefenseData();
    if (!data.playerStats) data.playerStats = {};
    if (!data.playerStats[name]) {
        data.playerStats[name] = initPlayerBattleAttrs(name);
        saveAttackDefenseData(data);
    }
    return data.playerStats[name];
}

function savePlayerBattleAttrs(name, attrs) {
    const data = getAttackDefenseData();
    if (!data.playerStats) data.playerStats = {};
    data.playerStats[name] = attrs;
    saveAttackDefenseData(data);
}

// ========================
// 攻防系统 - 战斗管理
// ========================

function generateBattleId() {
    return "BATTLE_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
}

function createBattle(initiator, mode = "free-for-all") {
    const battleId = generateBattleId();
    const config = getAttackDefenseConfig();

    return {
        id: battleId,
        initiator: initiator,
        mode: mode,
        status: "pending", // pending(待接受), preparing(准备中), ongoing(进行中), ended(已结束)
        players: [initiator],
        turns: config.defaultTurns || 10,
        currentTurn: 0,
        turnOrder: [initiator],
        currentPlayerIndex: 0,
        createdAt: Date.now(),
        turnStartTime: Date.now(),
        turnTimeout: config.turnTimeout || 3600000, // 默认1小时
        actions: [], // 所有行动记录
        playerStates: {
            [initiator]: {
                hp: getPlayerBattleAttrs(initiator).HP,
                mp: getPlayerBattleAttrs(initiator).MP,
                shield: 0,
                alive: true,
                damage_taken: 0,
                skills_used: []
            }
        },
        rewards: null,
        winner: null
    };
}

function addPlayerToBattle(battleId, playerName) {
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    const battle = data.battles[battleId];
    if (!battle || battle.status !== "pending") return false;

    if (battle.players.includes(playerName)) return false;

    battle.players.push(playerName);
    const attrs = getPlayerBattleAttrs(playerName);
    battle.playerStates[playerName] = {
        hp: attrs.HP,
        mp: attrs.MP,
        shield: 0,
        alive: true,
        damage_taken: 0,
        skills_used: []
    };

    saveAttackDefenseData(data);
    return true;
}

function startBattle(battleId) {
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    const battle = data.battles[battleId];
    if (!battle) return false;

    battle.status = "preparing";
    // 按敏捷排序
    const agiScores = {};
    battle.players.forEach(p => {
        agiScores[p] = getPlayerBattleAttrs(p).AGI;
    });
    battle.turnOrder = battle.players.sort((a, b) => agiScores[b] - agiScores[a]);
    battle.currentPlayerIndex = 0;
    battle.status = "ongoing";
    battle.currentTurn = 1;
    battle.turnStartTime = Date.now();

    saveAttackDefenseData(data);
    return true;
}

function getCurrentBattlePlayer(battle) {
    if (!battle || battle.status !== "ongoing") return null;
    return battle.turnOrder[battle.currentPlayerIndex];
}

function recordAction(battleId, action) {
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    const battle = data.battles[battleId];
    if (!battle) return false;

    action.timestamp = Date.now();
    action.turn = battle.currentTurn;
    battle.actions.push(action);

    saveAttackDefenseData(data);
    return true;
}

// ========================
// 攻防系统 - 战斗计算
// ========================

function calculateNormalAttack(attacker, defender) {
    const atkAttrs = getPlayerBattleAttrs(attacker);
    const defAttrs = getPlayerBattleAttrs(defender);
    const config = getAttackDefenseConfig();

    let baseDamage = atkAttrs.ATK;
    let defReduction = Math.max(0, defAttrs.DEF * 0.1);

    // 应用伤害随机性
    let randomRange = config.damageRandomness;
    if (!randomRange || randomRange === 0) {
        baseDamage = baseDamage - defReduction;
    } else if (typeof randomRange === 'string' && randomRange.includes('-')) {
        const [min, max] = randomRange.split('-').map(Number);
        const random = Math.floor(Math.random() * (max - min + 1)) + min;
        baseDamage = baseDamage + (min - 1 + random) - defReduction;
    }

    return Math.max(1, Math.round(baseDamage));
}

function applyDamage(battleId, targetName, damage) {
    const data = getAttackDefenseData();
    if (!data.battles) return 0;
    const battle = data.battles[battleId];
    if (!battle || !battle.playerStates[targetName]) return 0;

    const state = battle.playerStates[targetName];
    let actualDamage = damage;

    // 先扣盾，再扣HP
    if (state.shield > 0) {
        const shieldDamage = Math.min(state.shield, actualDamage);
        state.shield -= shieldDamage;
        actualDamage -= shieldDamage;
    }

    if (actualDamage > 0) {
        state.hp -= actualDamage;
        state.damage_taken += actualDamage;
        if (state.hp <= 0) {
            state.alive = false;
        }
    }

    saveAttackDefenseData(data);
    return damage;
}

function getAlivePlayersCount(battle) {
    let count = 0;
    for (const player of battle.players) {
        if (battle.playerStates[player] && battle.playerStates[player].alive) {
            count++;
        }
    }
    return count;
}

// ========================
// 攻防系统 - 命令: 发起战斗
// ========================

let cmd_pk = seal.ext.newCmdItemInfo();
cmd_pk.name = "PK";
cmd_pk.help = "发起或接受战斗\n发起 [对手1] [对手2]...\n发起  （不指定对手时进入自由模式）\n接受 <战斗ID>\n拒绝 <战斗ID>";
cmd_pk.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const subCmd = cmdArgs.getArgN(1);
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    if (!data.playerStats) data.playerStats = {};

    // 发起战斗
    if (subCmd === "发起") {
        // 检查每日发起次数限制
        const today = new Date().toDateString();
        if (!data.playerStats[player]) data.playerStats[player] = initPlayerBattleAttrs(player);
        if (!data.playerStats[player].initiations) data.playerStats[player].initiations = {};
        if (!data.playerStats[player].initiations[today]) data.playerStats[player].initiations[today] = 0;

        const maxInitiations = config.maxInitiations || 10;
        if (data.playerStats[player].initiations[today] >= maxInitiations) {
            return seal.replyToSender(ctx, msg, `❌ 今日发起战斗次数已达上限 (${maxInitiations}次)。`);
        }

        const battle = createBattle(player);

        // 如果指定了对手，自动添加他们（混战模式）
        const opponents = [];
        for (let i = 2; i <= cmdArgs.getArgCount(); i++) {
            opponents.push(cmdArgs.getArgN(i));
        }

        if (opponents.length > 0) {
            opponents.forEach(opp => addPlayerToBattle(battle.id, opp));
            battle.status = "preparing";
        }

        data.battles[battle.id] = battle;
        data.playerStats[player].initiations[today]++;
        saveAttackDefenseData(data);

        let msg_text = `⚔️ ${player} 发起了一场战斗！\n\n战斗ID: ${battle.id}\n\n`;
        if (opponents.length > 0) {
            msg_text += `参战者: ${[player, ...opponents].join(", ")}\n\n`;
            msg_text += `输入「PK 接受 ${battle.id}」开始战斗。`;
        } else {
            msg_text += `这是一个开放战斗，其他人可以:\n\n输入「PK 接受 ${battle.id}」加入战斗`;
        }

        return seal.replyToSender(ctx, msg, msg_text);
    }

    // 接受战斗
    if (subCmd === "接受") {
        const battleId = cmdArgs.getArgN(2);
        if (!battleId || !data.battles[battleId]) {
            return seal.replyToSender(ctx, msg, "❌ 无效的战斗ID。");
        }

        const battle = data.battles[battleId];
        if (battle.status !== "pending" && battle.status !== "preparing") {
            return seal.replyToSender(ctx, msg, "❌ 该战斗已不可加入。");
        }

        if (battle.players.includes(player)) {
            return seal.replyToSender(ctx, msg, "❌ 你已加入该战斗。");
        }

        // 检查拒绝限制（如果启用强制参战则无需检查）
        if (!config.forceParticipate) {
            const today = new Date().toDateString();
            if (!data.playerStats[player].refusals) data.playerStats[player].refusals = {};
            if (!data.playerStats[player].refusals[today]) data.playerStats[player].refusals[today] = 0;

            const maxRefusals = config.maxRefusals || 10;
            if (data.playerStats[player].refusals[today] >= maxRefusals) {
                return seal.replyToSender(ctx, msg, `❌ 由于你今日拒绝次数过多，无法接受新的战斗。`);
            }
        }

        addPlayerToBattle(battleId, player);

        // 如果有足够的人，自动开始战斗
        if (battle.players.length >= (config.minPlayers || 2) && !config.manualStart) {
            startBattle(battleId);
            return seal.replyToSender(ctx, msg, `✅ ${player} 加入了战斗！\n\n⚔️ 战斗已开始！\n\n当前玩家: ${getCurrentBattlePlayer(battle)}\n\n输入「PK 攻击 <对手名字>」发动攻击。`);
        }

        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, `✅ ${player} 加入了战斗 ${battleId}!\n\n当前参战者: ${battle.players.join(", ")}`);
    }

    // 拒绝战斗
    if (subCmd === "拒绝") {
        const battleId = cmdArgs.getArgN(2);
        if (!battleId || !data.battles[battleId]) {
            return seal.replyToSender(ctx, msg, "❌ 无效的战斗ID。");
        }

        const battle = data.battles[battleId];
        if (battle.status !== "pending" && battle.status !== "preparing") {
            return seal.replyToSender(ctx, msg, "❌ 该战斗已不可拒绝。");
        }

        const today = new Date().toDateString();
        if (!data.playerStats[player].refusals) data.playerStats[player].refusals = {};
        if (!data.playerStats[player].refusals[today]) data.playerStats[player].refusals[today] = 0;
        data.playerStats[player].refusals[today]++;

        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, `✅ 你拒绝了战斗 ${battleId}。\n\n今日已拒绝 ${data.playerStats[player].refusals[today]} 次。`);
    }
};

ext.cmdMap["PK"] = cmd_pk;

// ========================
// 攻防系统 - 命令: 战斗操作
// ========================

let cmd_attack = seal.ext.newCmdItemInfo();
cmd_attack.name = "攻击";
cmd_attack.help = "在战斗中发动攻击\n攻击 <对手名字>";
cmd_attack.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const targetName = cmdArgs.getArgN(1);
    if (!targetName) return seal.replyToSender(ctx, msg, "❌ 请指定攻击目标。");

    const data = getAttackDefenseData();
    if (!data.battles) return seal.replyToSender(ctx, msg, "❌ 没有进行中的战斗。");

    // 找到玩家所在的战斗
    let battle = null;
    for (const bid in data.battles) {
        if (data.battles[bid].players.includes(player) && data.battles[bid].status === "ongoing") {
            battle = data.battles[bid];
            break;
        }
    }

    if (!battle) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");

    const currentPlayer = getCurrentBattlePlayer(battle);
    if (currentPlayer !== player) {
        return seal.replyToSender(ctx, msg, `❌ 现在不是你的回合。当前轮到: ${currentPlayer}`);
    }

    if (!battle.playerStates[targetName]) {
        return seal.replyToSender(ctx, msg, "❌ 目标不存在或未参加此战斗。");
    }

    if (!battle.playerStates[targetName].alive) {
        return seal.replyToSender(ctx, msg, "❌ 目标已被击败。");
    }

    if (targetName === player) {
        return seal.replyToSender(ctx, msg, "❌ 无法攻击自己。");
    }

    // 计算伤害
    const damage = calculateNormalAttack(player, targetName);
    applyDamage(battle.id, targetName, damage);

    // 记录行动
    recordAction(battle.id, {
        actor: player,
        action: "attack",
        target: targetName,
        damage: damage,
        targetHP: battle.playerStates[targetName].hp
    });

    let result = `⚔️ ${player} 攻击了 ${targetName}！\n\n伤害: ${damage}\n${targetName} 剩余HP: ${Math.max(0, battle.playerStates[targetName].hp)}`;

    // 检查目标是否被击败
    if (!battle.playerStates[targetName].alive) {
        result += `\n\n☠️ ${targetName} 被击败了！`;
    }

    // 检查战斗是否结束
    if (getAlivePlayersCount(battle) <= 1) {
        battle.status = "ended";
        const survivors = battle.players.filter(p => battle.playerStates[p] && battle.playerStates[p].alive);
        if (survivors.length === 1) {
            battle.winner = survivors[0];
            result += `\n\n🏆 战斗结束！${survivors[0]} 胜利！`;
        } else {
            result += `\n\n⚔️ 战斗结束，平手！`;
        }
    } else {
        // 进到下一个回合
        battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
        // 跳过已击败的玩家
        let attempts = 0;
        while (!battle.playerStates[battle.turnOrder[battle.currentPlayerIndex]].alive && attempts < battle.turnOrder.length) {
            battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
            attempts++;
        }

        if (battle.currentPlayerIndex === 0) {
            battle.currentTurn++;
        }
        battle.turnStartTime = Date.now();

        result += `\n\n➡️ 轮到 ${getCurrentBattlePlayer(battle)} 的回合。`;
    }

    saveAttackDefenseData(data);
    return seal.replyToSender(ctx, msg, result);
};

ext.cmdMap["攻击"] = cmd_attack;

// ========================
// 攻防系统 - 命令: 防守
// ========================

let cmd_defend = seal.ext.newCmdItemInfo();
cmd_defend.name = "防守";
cmd_defend.help = "在战斗中防守一回合（增加防御力）\n防守";
cmd_defend.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const data = getAttackDefenseData();
    if (!data.battles) return seal.replyToSender(ctx, msg, "❌ 没有进行中的战斗。");

    let battle = null;
    for (const bid in data.battles) {
        if (data.battles[bid].players.includes(player) && data.battles[bid].status === "ongoing") {
            battle = data.battles[bid];
            break;
        }
    }

    if (!battle) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");

    const currentPlayer = getCurrentBattlePlayer(battle);
    if (currentPlayer !== player) {
        return seal.replyToSender(ctx, msg, `❌ 现在不是你的回合。当前轮到: ${currentPlayer}`);
    }

    // 记录防守行动
    recordAction(battle.id, {
        actor: player,
        action: "defend",
        defenseBonus: 50
    });

    // 进到下一个回合
    battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
    let attempts = 0;
    while (!battle.playerStates[battle.turnOrder[battle.currentPlayerIndex]].alive && attempts < battle.turnOrder.length) {
        battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
        attempts++;
    }

    if (battle.currentPlayerIndex === 0) {
        battle.currentTurn++;
    }
    battle.turnStartTime = Date.now();

    saveAttackDefenseData(data);
    return seal.replyToSender(ctx, msg, `🛡️ ${player} 进入防守姿态！\n\n➡️ 轮到 ${getCurrentBattlePlayer(battle)} 的回合。`);
};

ext.cmdMap["防守"] = cmd_defend;

// ========================
// 攻防系统 - 命令: 投降/逃跑
// ========================

let cmd_surrender = seal.ext.newCmdItemInfo();
cmd_surrender.name = "投降";
cmd_surrender.help = "在战斗中投降或尝试逃跑\n投降";
cmd_surrender.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const data = getAttackDefenseData();
    if (!data.battles) return seal.replyToSender(ctx, msg, "❌ 没有进行中的战斗。");

    let battle = null;
    for (const bid in data.battles) {
        if (data.battles[bid].players.includes(player) && data.battles[bid].status === "ongoing") {
            battle = data.battles[bid];
            break;
        }
    }

    if (!battle) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");

    const escapeRate = config.escapeRate !== undefined ? config.escapeRate : 30;
    const escapeRoll = Math.random() * 100;

    recordAction(battle.id, {
        actor: player,
        action: "escape",
        success: escapeRoll < escapeRate
    });

    if (escapeRoll < escapeRate) {
        // 成功逃脱
        battle.playerStates[player].alive = false;

        let result = `💨 ${player} 成功逃离了战斗！`;

        if (getAlivePlayersCount(battle) <= 1) {
            battle.status = "ended";
            const survivors = battle.players.filter(p => battle.playerStates[p] && battle.playerStates[p].alive);
            if (survivors.length === 1) {
                battle.winner = survivors[0];
                result += `\n\n🏆 战斗结束！${survivors[0]} 胜利！`;
            } else {
                result += `\n\n⚔️ 战斗结束，平手！`;
            }
        } else {
            // 进到下一个回合
            battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
            let attempts = 0;
            while (!battle.playerStates[battle.turnOrder[battle.currentPlayerIndex]].alive && attempts < battle.turnOrder.length) {
                battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
                attempts++;
            }

            if (battle.currentPlayerIndex === 0) {
                battle.currentTurn++;
            }
            battle.turnStartTime = Date.now();

            result += `\n\n➡️ 轮到 ${getCurrentBattlePlayer(battle)} 的回合。`;
        }

        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, result);
    } else {
        // 逃脱失败
        const nextPlayerIndex = (battle.currentPlayerIndex + 1) % battle.turnOrder.length;
        let attempts = 0;
        while (!battle.playerStates[battle.turnOrder[nextPlayerIndex]].alive && attempts < battle.turnOrder.length && attempts < 1) {
            attempts++;
        }

        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, `❌ ${player} 逃脱失败！\n\n(成功率: ${escapeRate}%)`);
    }
};

ext.cmdMap["投降"] = cmd_surrender;
ext.cmdMap["逃跑"] = cmd_surrender;

// ========================
// 攻防系统 - 管理员命令: 开关/设置
// ========================

let cmd_attack_defense_admin = seal.ext.newCmdItemInfo();
cmd_attack_defense_admin.name = "攻防";
cmd_attack_defense_admin.help = "【管理员】攻防系统管理\n攻防 开 / 关     - 启用/禁用系统\n攻防 查看        - 查看配置\n攻防 设置 参数 值 - 设置配置参数";
cmd_attack_defense_admin.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const subCmd = cmdArgs.getArgN(1);
    let config = getAttackDefenseConfig();

    // 开启系统
    if (subCmd === "开") {
        config.enabled = true;
        saveAttackDefenseConfig(config);
        return seal.replyToSender(ctx, msg, "✅ 攻防系统已启用。");
    }

    // 关闭系统
    if (subCmd === "关") {
        config.enabled = false;
        saveAttackDefenseConfig(config);
        return seal.replyToSender(ctx, msg, "✅ 攻防系统已禁用。");
    }

    // 查看配置
    if (subCmd === "查看") {
        let info = "🎮 攻防系统配置:\n\n";
        info += `启用状态: ${config.enabled ? "✅ 已启用" : "❌ 已禁用"}\n`;
        info += `\n⚙️ 参数:\n`;
        info += `· 每日最大发起次数: ${config.maxInitiations || 10}\n`;
        info += `· 每日最大拒绝次数: ${config.maxRefusals || 10}\n`;
        info += `· 每回合超时(ms): ${config.turnTimeout || 3600000}\n`;
        info += `· 默认回合数: ${config.defaultTurns || 10}\n`;
        info += `· 逃脱成功率(%): ${config.escapeRate !== undefined ? config.escapeRate : 30}\n`;
        info += `· 伤害随机性: ${config.damageRandomness || "无 (纯数值)"}\n`;
        info += `· 强制参战模式: ${config.forceParticipate ? "是" : "否"}\n`;
        info += `· 最小参战人数: ${config.minPlayers || 2}\n`;
        info += `· 手动开始模式: ${config.manualStart ? "是" : "否"}\n`;

        return seal.replyToSender(ctx, msg, info);
    }

    // 设置参数
    if (subCmd === "设置") {
        const paramName = cmdArgs.getArgN(2);
        const paramValue = cmdArgs.getArgN(3);

        if (!paramName || !paramValue) {
            return seal.replyToSender(ctx, msg, "❌ 请指定参数名和值。");
        }

        switch(paramName) {
            case "每日发起":
                config.maxInitiations = parseInt(paramValue);
                break;
            case "每日拒绝":
                config.maxRefusals = parseInt(paramValue);
                break;
            case "回合超时":
                config.turnTimeout = parseInt(paramValue);
                break;
            case "默认回合":
                config.defaultTurns = parseInt(paramValue);
                break;
            case "逃脱率":
                config.escapeRate = parseInt(paramValue);
                break;
            case "伤害随机":
                config.damageRandomness = paramValue === "无" ? 0 : paramValue;
                break;
            case "强制参战":
                config.forceParticipate = paramValue === "是";
                break;
            case "最小人数":
                config.minPlayers = parseInt(paramValue);
                break;
            case "手动开始":
                config.manualStart = paramValue === "是";
                break;
            default:
                return seal.replyToSender(ctx, msg, `❌ 未知参数: ${paramName}`);
        }

        saveAttackDefenseConfig(config);
        return seal.replyToSender(ctx, msg, `✅ 设置成功: ${paramName} = ${paramValue}`);
    }

    return seal.replyToSender(ctx, msg, "❌ 无效命令。");
};

ext.cmdMap["攻防"] = cmd_attack_defense_admin;

// ========================
// 攻防系统 - 管理员命令: 添加人员
// ========================

let cmd_add_player = seal.ext.newCmdItemInfo();
cmd_add_player.name = "添加人员";
cmd_add_player.help = "【管理员】手动将玩家加入战斗\n添加人员 <玩家名> [玩家2] [玩家3]...";
cmd_add_player.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const initiator = cmdArgs.getArgN(1);
    if (!initiator) return seal.replyToSender(ctx, msg, "❌ 请指定玩家名。");

    const data = getAttackDefenseData();
    const battle = createBattle(initiator, "free-for-all");

    // 添加其他玩家
    for (let i = 2; i <= cmdArgs.getArgCount(); i++) {
        const playerName = cmdArgs.getArgN(i);
        if (playerName) addPlayerToBattle(battle.id, playerName);
    }

    data.battles[battle.id] = battle;
    saveAttackDefenseData(data);

    let msg_text = `✅ 已创建战斗!\n\n战斗ID: ${battle.id}\n`;
    msg_text += `参战者: ${battle.players.join(", ")}\n\n`;
    msg_text += `输入「PK 接受 ${battle.id}」开始战斗。`;

    return seal.replyToSender(ctx, msg, msg_text);
};

ext.cmdMap["添加人员"] = cmd_add_player;

// ========================
// 攻防系统 - 管理员命令: 添加技能
// ========================

let cmd_add_skill = seal.ext.newCmdItemInfo();
cmd_add_skill.name = "添加技能";
cmd_add_skill.help = "【管理员】为玩家解锁技能\n添加技能 <玩家名> <技能名>";
cmd_add_skill.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const playerName = cmdArgs.getArgN(1);
    const skillName = cmdArgs.getArgN(2);

    if (!playerName || !skillName) {
        return seal.replyToSender(ctx, msg, "❌ 请指定玩家名和技能名。");
    }

    const data = getAttackDefenseData();
    if (!data.skills) data.skills = {};
    if (!data.skills[playerName]) data.skills[playerName] = [];

    if (data.skills[playerName].includes(skillName)) {
        return seal.replyToSender(ctx, msg, `❌ ${playerName} 已经拥有技能 ${skillName}。`);
    }

    data.skills[playerName].push(skillName);
    saveAttackDefenseData(data);

    return seal.replyToSender(ctx, msg, `✅ 已为 ${playerName} 解锁技能: ${skillName}`);
};

ext.cmdMap["添加技能"] = cmd_add_skill;

// ========================
// 攻防系统 - 查看战斗状态
// ========================

let cmd_battle_status = seal.ext.newCmdItemInfo();
cmd_battle_status.name = "战斗状态";
cmd_battle_status.help = "查看当前战斗状态\n战斗状态 [战斗ID]";
cmd_battle_status.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const battleId = cmdArgs.getArgN(1);
    const data = getAttackDefenseData();
    if (!data.battles) return seal.replyToSender(ctx, msg, "❌ 没有战斗信息。");

    let battle = null;

    if (battleId) {
        battle = data.battles[battleId];
        if (!battle) return seal.replyToSender(ctx, msg, "❌ 战斗不存在。");
    } else {
        // 查找玩家参加的战斗
        for (const bid in data.battles) {
            if (data.battles[bid].players.includes(player) && data.battles[bid].status === "ongoing") {
                battle = data.battles[bid];
                break;
            }
        }
        if (!battle) return seal.replyToSender(ctx, msg, "❌ 你未参加任何进行中的战斗。");
    }

    let info = `⚔️ 战斗状态\n\n`;
    info += `战斗ID: ${battle.id}\n`;
    info += `状态: ${battle.status}\n`;
    info += `回合: ${battle.currentTurn}/${battle.turns}\n`;
    info += `\n当前轮到: ${getCurrentBattlePlayer(battle)}\n\n`;

    info += `参战者:\n`;
    battle.players.forEach(p => {
        const state = battle.playerStates[p];
        const status = state.alive ? "🟢 存活" : "💀 已败";
        info += `· ${p}: ${state.hp}/${getPlayerBattleAttrs(p).HP} HP | ${state.shield} 盾 | ${status}\n`;
    });

    return seal.replyToSender(ctx, msg, info);
};

ext.cmdMap["战斗状态"] = cmd_battle_status;

// ========================
// 攻防系统 - 查看属性
// ========================

let cmd_battle_attrs = seal.ext.newCmdItemInfo();
cmd_battle_attrs.name = "属性";
cmd_battle_attrs.help = "查看或管理战斗属性\n属性              - 查看自己的属性\n属性 <玩家名>     - 查看其他玩家属性\n【管理员】\n属性 设置 <玩家> <属性> <值> - 修改属性";
cmd_battle_attrs.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const subCmd = cmdArgs.getArgN(1);

    // 查看自己或指定玩家的属性
    if (!subCmd || (subCmd && !["设置", "修改"].includes(subCmd))) {
        const targetName = subCmd || getRoleName(ctx, msg);
        if (!targetName) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");

        const attrs = getPlayerBattleAttrs(targetName);
        let info = `⚔️ ${targetName} 的战斗属性\n\n`;
        info += `攻击力 (ATK):    ${attrs.ATK}\n`;
        info += `防御力 (DEF):    ${attrs.DEF}\n`;
        info += `敏捷 (AGI):      ${attrs.AGI}\n`;
        info += `生命值 (HP):     ${attrs.HP}\n`;
        info += `护盾 (TMP_SHIELD): ${attrs.TMP_SHIELD}\n`;
        info += `魔法值 (MP):     ${attrs.MP}\n`;
        info += `回复/回合 (MP_REGEN): ${attrs.MP_REGEN}\n`;

        return seal.replyToSender(ctx, msg, info);
    }

    // 管理员修改属性
    if (subCmd === "设置" || subCmd === "修改") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

        const playerName = cmdArgs.getArgN(2);
        const attrName = cmdArgs.getArgN(3);
        const value = parseInt(cmdArgs.getArgN(4));

        if (!playerName || !attrName || isNaN(value)) {
            return seal.replyToSender(ctx, msg, "❌ 用法: 属性 设置 <玩家> <属性> <值>");
        }

        const validAttrs = ["ATK", "DEF", "AGI", "HP", "TMP_SHIELD", "MP", "MP_REGEN"];
        if (!validAttrs.includes(attrName)) {
            return seal.replyToSender(ctx, msg, `❌ 无效属性。有效属性: ${validAttrs.join(", ")}`);
        }

        const attrs = getPlayerBattleAttrs(playerName);
        const oldValue = attrs[attrName];
        attrs[attrName] = value;
        savePlayerBattleAttrs(playerName, attrs);

        return seal.replyToSender(ctx, msg, `✅ 已修改 ${playerName} 的 ${attrName}: ${oldValue} → ${value}`);
    }
};

ext.cmdMap["属性"] = cmd_battle_attrs;

// ========================
// 攻防系统 - 战斗历史
// ========================

let cmd_battle_history = seal.ext.newCmdItemInfo();
cmd_battle_history.name = "战斗历史";
cmd_battle_history.help = "查看战斗历史和统计\n战斗历史 <战斗ID> [页码]";
cmd_battle_history.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const battleId = cmdArgs.getArgN(1);
    if (!battleId) return seal.replyToSender(ctx, msg, "❌ 请指定战斗ID。");

    const data = getAttackDefenseData();
    if (!data.battles || !data.battles[battleId]) {
        return seal.replyToSender(ctx, msg, "❌ 战斗不存在。");
    }

    const battle = data.battles[battleId];
    const pageNum = parseInt(cmdArgs.getArgN(2)) || 1;
    const pageSize = 10;
    const totalActions = battle.actions.length;
    const totalPages = Math.ceil(totalActions / pageSize);

    if (pageNum > totalPages || pageNum < 1) {
        return seal.replyToSender(ctx, msg, `❌ 页码范围: 1-${totalPages}`);
    }

    let info = `📋 战斗历史 - ${battle.id}\n`;
    info += `状态: ${battle.status} | 赢家: ${battle.winner || "进行中"}\n\n`;
    info += `第 ${pageNum}/${totalPages} 页:\n\n`;

    const start = (pageNum - 1) * pageSize;
    const end = Math.min(start + pageSize, totalActions);

    for (let i = start; i < end; i++) {
        const action = battle.actions[i];
        info += `[T${action.turn}] ${action.actor}:`;

        if (action.action === "attack") {
            info += ` 攻击 ${action.target} → ${action.damage} 伤害\n`;
        } else if (action.action === "defend") {
            info += ` 防守 (防御+${action.defenseBonus})\n`;
        } else if (action.action === "escape") {
            info += ` 尝试逃脱 → ${action.success ? "成功" : "失败"}\n`;
        } else if (action.action === "skill") {
            info += ` 使用技能 ${action.skill} → ${action.damage} 伤害\n`;
        }
    }

    return seal.replyToSender(ctx, msg, info);
};

ext.cmdMap["战斗历史"] = cmd_battle_history;

// ========================
// 攻防系统 - 设置中文显示名
// ========================

let cmd_set_display_name = seal.ext.newCmdItemInfo();
cmd_set_display_name.name = "设置昵称";
cmd_set_display_name.help = "设置战斗中显示的昵称\n设置昵称 <昵称>";
cmd_set_display_name.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const displayName = cmdArgs.getArgN(1);
    if (!displayName) return seal.replyToSender(ctx, msg, "❌ 请指定昵称。");

    const data = getAttackDefenseData();
    if (!data.playerStats) data.playerStats = {};
    if (!data.playerStats[player]) data.playerStats[player] = initPlayerBattleAttrs(player);

    data.playerStats[player].displayName = displayName;
    saveAttackDefenseData(data);

    return seal.replyToSender(ctx, msg, `✅ 昵称已设置为: ${displayName}`);
};

ext.cmdMap["设置昵称"] = cmd_set_display_name;

// ========================
// 一键初始化 - 快速启用攻防系统
// ========================

let cmd_quick_init = seal.ext.newCmdItemInfo();
cmd_quick_init.name = "一键初始化";
cmd_quick_init.help = "【管理员】一键初始化攻防系统 - 注册属性和回血药\n一键初始化\n  将自动创建：\n  · 5个RPG属性（HP、MP、ATK、DEF、AGI）\n  · 4种回血药（小、中、大、满）\n  · 启用攻防系统";
cmd_quick_init.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 获取当前属性和物品定义
    const defs = getAttrDefs();
    const registry = getRegistry();

    let results = [];
    let errors = [];

    // ========== 创建RPG属性 ==========
    const attrs = [
        { name: "HP", min: 0, max: 100, default: 50, desc: "生命值" },
        { name: "MP", min: 0, max: 100, default: 50, desc: "魔法值" },
        { name: "ATK", min: 0, max: 100, default: 40, desc: "攻击力" },
        { name: "DEF", min: 0, max: 100, default: 30, desc: "防御力" },
        { name: "AGI", min: 0, max: 100, default: 40, desc: "敏捷" }
    ];

    attrs.forEach(attr => {
        if (defs[attr.name]) {
            errors.push(`⏭️ 属性「${attr.name}」已存在`);
        } else {
            defs[attr.name] = {
                min: attr.min,
                max: attr.max,
                default: attr.default,
                desc: attr.desc
            };
            results.push(`✅ 已创建属性：${attr.name}`);
        }
    });

    saveAttrDefs(defs);

    // ========== 创建回血药物品 ==========
    const potions = [
        {
            name: "小回血药",
            desc: "恢复少量HP",
            uses: -1,
            effects: "HP+30",
            resellable: "Y",
            code: "ITEM_POT_S"
        },
        {
            name: "中回血药",
            desc: "恢复中等HP",
            uses: -1,
            effects: "HP+60",
            resellable: "Y",
            code: "ITEM_POT_M"
        },
        {
            name: "大回血药",
            desc: "恢复大量HP",
            uses: -1,
            effects: "HP+100",
            resellable: "Y",
            code: "ITEM_POT_L"
        },
        {
            name: "全恢复药",
            desc: "完全恢复HP和MP",
            uses: 0,
            effects: "HP+100,MP+100",
            resellable: "N",
            code: "ITEM_POT_FULL"
        }
    ];

    potions.forEach(potion => {
        if (registry[potion.code]) {
            errors.push(`⏭️ 物品「${potion.name}」(${potion.code})已存在`);
        } else {
            registry[potion.code] = {
                code: potion.code,
                name: potion.name,
                type: "normal",
                desc: potion.desc,
                useTimes: parseInt(potion.uses),
                attrs: potion.effects.split(",").map(e => {
                    const [attr, val] = e.trim().split("+");
                    return { attr: attr.trim(), value: parseInt(val) };
                }),
                canResell: potion.resellable === "Y"
            };
            results.push(`✅ 已创建物品：${potion.name} (${potion.code})`);
        }
    });

    saveRegistry(registry);

    // ========== 启用攻防系统 ==========
    let attackDefenseConfig = getAttackDefenseConfig();
    if (!attackDefenseConfig.enabled) {
        attackDefenseConfig.enabled = true;
        attackDefenseConfig.maxInitiations = attackDefenseConfig.maxInitiations || 10;
        attackDefenseConfig.maxRefusals = attackDefenseConfig.maxRefusals || 10;
        attackDefenseConfig.turnTimeout = attackDefenseConfig.turnTimeout || 3600000;
        attackDefenseConfig.defaultTurns = attackDefenseConfig.defaultTurns || 10;
        attackDefenseConfig.escapeRate = attackDefenseConfig.escapeRate !== undefined ? attackDefenseConfig.escapeRate : 30;
        attackDefenseConfig.damageRandomness = attackDefenseConfig.damageRandomness || 0;
        attackDefenseConfig.forceParticipate = false;
        attackDefenseConfig.minPlayers = 2;
        attackDefenseConfig.manualStart = false;
        saveAttackDefenseConfig(attackDefenseConfig);
        results.push(`✅ 已启用攻防系统（休闲模式配置）`);
    } else {
        errors.push(`⏭️ 攻防系统已启用`);
    }

    // ========== 创建基础装备 ==========
    const equipRegistry = getEquipRegistry();
    const baseEquips = [
        {
            name: "铁制短剑",
            desc: "一把普通的短剑",
            slot: "hand",
            baseAttrs: { ATK: 15 },
            reinforceBonus: { ATK: 2 },
            maxReinforce: 10,
            code: "EQUIP_SWORD_01"
        },
        {
            name: "皮革甲胄",
            desc: "轻便的皮甲防御",
            slot: "chest",
            baseAttrs: { DEF: 20, HP: 50 },
            reinforceBonus: { DEF: 3 },
            maxReinforce: 10,
            code: "EQUIP_CHEST_01"
        },
        {
            name: "铁制头盔",
            desc: "保护头部的头盔",
            slot: "head",
            baseAttrs: { DEF: 10 },
            reinforceBonus: { DEF: 1 },
            maxReinforce: 10,
            code: "EQUIP_HEAD_01"
        },
        {
            name: "腰部护甲",
            desc: "增强体力的护甲",
            slot: "hand",
            baseAttrs: { HP: 30 },
            reinforceBonus: { HP: 5 },
            maxReinforce: 10,
            code: "EQUIP_WAIST_01"
        },
        {
            name: "敏捷靴子",
            desc: "提升速度的靴子",
            slot: "foot",
            baseAttrs: { AGI: 5 },
            reinforceBonus: { AGI: 1 },
            maxReinforce: 10,
            code: "EQUIP_FOOT_01"
        }
    ];

    let equipCount = 0;
    baseEquips.forEach(equip => {
        if (!equipRegistry[equip.code]) {
            equipRegistry[equip.code] = {
                code: equip.code,
                name: equip.name,
                desc: equip.desc,
                type: "equipment",
                slot: equip.slot,
                baseAttrs: equip.baseAttrs,
                reinforceBonus: equip.reinforceBonus,
                maxReinforce: equip.maxReinforce
            };
            equipCount++;
        }
    });

    if (equipCount > 0) {
        saveEquipRegistry(equipRegistry);
        results.push(`✅ 已创建装备系统（${equipCount}件基础装备）`);
    } else {
        errors.push(`⏭️ 装备系统已初始化`);
    }

    // 初始化强化系统配置
    let equipConfig = getEquipConfig();
    if (!equipConfig.successRate) {
        equipConfig.enabled = true;
        equipConfig.successRate = 90;
        equipConfig.costPerLevel = [100, 150, 200, 250, 300, 400, 500, 600, 750, 1000];
        saveEquipConfig(equipConfig);
    }

    // ========== 返回结果 ==========
    let reply = `🚀 一键初始化完成！\n\n`;

    if (results.length > 0) {
        reply += `✅ 成功项目 (${results.length})：\n` + results.join("\n") + "\n\n";
    }

    if (errors.length > 0) {
        reply += `⏭️ 已跳过 (${errors.length})：\n` + errors.join("\n") + "\n\n";
    }

    reply += `📋 已创建：\n`;
    reply += `· 5个属性：HP、MP、ATK、DEF、AGI\n`;
    reply += `· 4种药品：小/中/大回血药 + 全恢复药\n`;
    reply += `· 5件装备：铁剑、皮甲、头盔、腰甲、靴子\n`;
    reply += `· 攻防系统已启用\n`;
    reply += `· 强化系统已启用\n\n`;
    reply += `💡 下一步：\n`;
    reply += `· 上架商城：上架商城 ITEM_POT_S*50金币\n`;
    reply += `· 上架装备：上架商城 EQUIP_SWORD_01*500金币\n`;
    reply += `· 配置攻防：攻防 设置 参数 值\n`;
    reply += `· 创建池子：注册池子 回血药池 fixed`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["一键初始化"] = cmd_quick_init;

// ========================
// 装备系统 - 存储和配置
// ========================

function getEquipRegistry() {
    const main = getMain();
    if (!main) return {};
    try {
        return JSON.parse(main.storageGet("equipment_registry") || "{}");
    } catch(e) { return {}; }
}

function saveEquipRegistry(reg) {
    const main = getMain();
    if (main) main.storageSet("equipment_registry", JSON.stringify(reg));
}

function getEquipConfig() {
    const main = getMain();
    if (!main) return {};
    try {
        return JSON.parse(main.storageGet("equipment_config") || "{}");
    } catch(e) { return {}; }
}

function saveEquipConfig(config) {
    const main = getMain();
    if (main) main.storageSet("equipment_config", JSON.stringify(config));
}

function getEquipSlots() {
    const main = getMain();
    if (!main) return ["head", "chest", "hand", "leg", "foot"];
    try {
        const slots = JSON.parse(main.storageGet("equipment_slots") || "[]");
        return slots.length > 0 ? slots : ["head", "chest", "hand", "leg", "foot"];
    } catch(e) {
        return ["head", "chest", "hand", "leg", "foot"];
    }
}

function saveEquipSlots(slots) {
    const main = getMain();
    if (main) main.storageSet("equipment_slots", JSON.stringify(slots));
}

function getSlotDisplayNames() {
    const main = getMain();
    if (!main) return {};
    try {
        return JSON.parse(main.storageGet("equipment_slot_names") || "{}");
    } catch(e) {
        return {};
    }
}

function saveSlotDisplayNames(names) {
    const main = getMain();
    if (main) main.storageSet("equipment_slot_names", JSON.stringify(names));
}

function getSlotDisplayName(slot) {
    const names = getSlotDisplayNames();
    return names[slot] || slot;
}

function getPlayerEquips(roleKey) {
    const main = getMain();
    if (!main) return null;
    try {
        const data = JSON.parse(main.storageGet("player_equipments") || "{}");
        if (!data[roleKey]) {
            const slots = getEquipSlots();
            data[roleKey] = {};
            slots.forEach(slot => {
                data[roleKey][slot] = null;
            });
            main.storageSet("player_equipments", JSON.stringify(data));
        }
        return data[roleKey];
    } catch(e) { return null; }
}

function savePlayerEquips(roleKey, equips) {
    const main = getMain();
    if (!main) return;
    try {
        const data = JSON.parse(main.storageGet("player_equipments") || "{}");
        data[roleKey] = equips;
        main.storageSet("player_equipments", JSON.stringify(data));
    } catch(e) {}
}

function generateEquipCode(registry) {
    let i = 1;
    while (registry[`EQUIP_${String(i).padStart(3, '0')}`]) i++;
    return `EQUIP_${String(i).padStart(3, '0')}`;
}

function findEquip(registry, input) {
    if (registry[input]) return registry[input];
    for (const code in registry) {
        if (registry[code].name === input) return registry[code];
    }
    return null;
}

function getEquipBonus(equip, reinforceLevel) {
    if (!equip || !equip.baseAttrs) return {};

    const bonus = {};
    for (const attr in equip.baseAttrs) {
        bonus[attr] = equip.baseAttrs[attr];
    }

    if (reinforceLevel > 0 && equip.reinforceBonus) {
        for (const attr in equip.reinforceBonus) {
            bonus[attr] = (bonus[attr] || 0) + (equip.reinforceBonus[attr] * reinforceLevel);
        }
    }

    return bonus;
}

function getTotalEquipBonus(playerEquips, registry) {
    const totalBonus = {};

    for (const slot in playerEquips) {
        const equipped = playerEquips[slot];
        if (!equipped || !equipped.code) continue;

        const equip = registry[equipped.code];
        if (!equip) continue;

        const bonus = getEquipBonus(equip, equipped.reinforceLevel || 0);
        for (const attr in bonus) {
            totalBonus[attr] = (totalBonus[attr] || 0) + bonus[attr];
        }
    }

    return totalBonus;
}

// ========================
// 装备系统 - 玩家命令：装备管理
// ========================

let cmd_equip = seal.ext.newCmdItemInfo();
cmd_equip.name = "装备";
cmd_equip.help = "装备或查看装备\n装备 <装备名或代码>    - 穿上装备\n脱装备 <槽位>          - 卸下装备\n查看装备                - 显示当前装备及属性加成\n装备列表                - 查看所有可用装备\n装备详情 <装备码>       - 查看装备详细信息\n\n💡 槽位由管理员定义，执行「槽位 查看」看可用槽位。";
cmd_equip.solve = (ctx, msg, cmdArgs) => {
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const subCmd = cmdArgs.getArgN(1);
    const registry = getEquipRegistry();
    const main = getMain();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 获取roleKey
    const parts = msg.sender.userId.split(':');
    const platform = parts[0];
    const rawUid = parts[1];
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${player}`;

    // 查看装备
    if (!subCmd) {
        const equips = getPlayerEquips(roleKey);
        if (!equips) return seal.replyToSender(ctx, msg, "❌ 无法读取装备数据。");

        let info = `⚔️ ${player} 的装备:\n\n`;
        let hasEquip = false;

        for (const slot in equips) {
            const equipped = equips[slot];
            if (!equipped || !equipped.code) {
                info += `${getSlotEmoji(slot)} ${getSlotName(slot)}: 空\n`;
            } else {
                hasEquip = true;
                const equip = registry[equipped.code];
                if (equip) {
                    const bonus = getEquipBonus(equip, equipped.reinforceLevel || 0);
                    const bonusStr = Object.entries(bonus).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join(',');
                    info += `${getSlotEmoji(slot)} ${getSlotName(slot)}: ${equip.name}`;
                    if (equipped.reinforceLevel) {
                        info += ` [+${equipped.reinforceLevel}]`;
                    }
                    info += ` (${bonusStr})\n`;
                }
            }
        }

        if (hasEquip) {
            const totalBonus = getTotalEquipBonus(equips, registry);
            info += `\n📊 总属性加成:\n`;
            for (const attr in totalBonus) {
                info += `· ${attr}${totalBonus[attr] > 0 ? '+' : ''}${totalBonus[attr]}\n`;
            }
        }

        return seal.replyToSender(ctx, msg, info);
    }

    // 穿上装备
    if (!subCmd.match(/^(脱|查|装|列|详)/)) {
        const equipName = subCmd;
        const equip = findEquip(registry, equipName);
        if (!equip) return seal.replyToSender(ctx, msg, `❌ 未找到装备「${equipName}」。`);

        const equips = getPlayerEquips(roleKey);
        if (!equips) return seal.replyToSender(ctx, msg, "❌ 无法读取装备数据。");

        const slot = equip.slot;
        const allSlots = getEquipSlots();

        // 检查槽位是否有效
        if (!allSlots.includes(slot)) {
            return seal.replyToSender(ctx, msg, `❌ 装备槽位「${slot}」不存在或已被删除。`);
        }

        const oldEquip = equips[slot];

        equips[slot] = { code: equip.code, reinforceLevel: 0 };
        savePlayerEquips(roleKey, equips);

        let msg_text = `✅ 你穿上了 ${equip.name}！\n\n`;
        const bonus = getEquipBonus(equip, 0);
        const bonusStr = Object.entries(bonus).map(([k, v]) => `${k}+${v}`).join(', ');
        msg_text += `属性加成: ${bonusStr}`;

        if (oldEquip && oldEquip.code && registry[oldEquip.code]) {
            msg_text += `\n\n(原装备 ${registry[oldEquip.code].name} 已卸下)`;
        }

        return seal.replyToSender(ctx, msg, msg_text);
    }

    // 列表
    if (subCmd === "列表" || subCmd === "列表") {
        const equips = Object.values(registry).filter(e => e.type === "equipment");
        if (!equips.length) return seal.replyToSender(ctx, msg, "❌ 还没有注册任何装备。");

        let info = `📋 装备列表 (${equips.length}件):\n\n`;
        equips.forEach(equip => {
            const bonus = Object.entries(equip.baseAttrs || {}).map(([k, v]) => `${k}+${v}`).join(', ');
            info += `· [${equip.code}] ${equip.name} (${getSlotName(equip.slot)})\n  ${equip.desc}\n  属性: ${bonus}\n\n`;
        });

        return seal.replyToSender(ctx, msg, info);
    }

    // 详情
    if (subCmd === "详情") {
        const equipCode = cmdArgs.getArgN(2);
        if (!equipCode || !registry[equipCode]) {
            return seal.replyToSender(ctx, msg, "❌ 请指定有效的装备代码。");
        }

        const equip = registry[equipCode];
        let info = `⚔️ ${equip.name}\n\n`;
        info += `代码: ${equip.code}\n`;
        info += `槽位: ${getSlotName(equip.slot)}\n`;
        info += `描述: ${equip.desc}\n\n`;
        info += `基础属性加成:\n`;
        for (const attr in equip.baseAttrs) {
            info += `· ${attr}+${equip.baseAttrs[attr]}\n`;
        }
        if (equip.reinforceBonus && equip.maxReinforce) {
            info += `\n强化属性 (每级):\n`;
            for (const attr in equip.reinforceBonus) {
                info += `· ${attr}+${equip.reinforceBonus[attr]} (最高${equip.maxReinforce}级)\n`;
            }
        }

        return seal.replyToSender(ctx, msg, info);
    }

    return seal.replyToSender(ctx, msg, cmd_equip.help);
};

ext.cmdMap["装备"] = cmd_equip;

// 辅助函数
function getSlotName(slot) {
    const displayNames = getSlotDisplayNames();
    if (displayNames[slot]) return displayNames[slot];

    const names = { head: "头部", chest: "胸部", hand: "手部", leg: "腿部", foot: "脚部" };
    return names[slot] || slot;
}

function getSlotEmoji(slot) {
    const emojis = { head: "🎩", chest: "🛡️", hand: "⚔️", leg: "👖", foot: "👢" };
    return emojis[slot] || "📦";
}

// ========================
// 装备系统 - 玩家命令：脱装备
// ========================

let cmd_unequip = seal.ext.newCmdItemInfo();
cmd_unequip.name = "脱装备";
cmd_unequip.help = "卸下装备\n脱装备 <槽位>\n\n执行「槽位 查看」查看所有可用槽位。";
cmd_unequip.solve = (ctx, msg, cmdArgs) => {
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const slot = cmdArgs.getArgN(1);
    if (!slot) return seal.replyToSender(ctx, msg, "❌ 请指定槽位。");

    const allSlots = getEquipSlots();
    if (!allSlots.includes(slot)) {
        return seal.replyToSender(ctx, msg, `❌ 无效的槽位。有效槽位: ${allSlots.join(", ")}`);
    }

    const parts = msg.sender.userId.split(':');
    const platform = parts[0];
    const roleKey = `${platform}:${player}`;

    const equips = getPlayerEquips(roleKey);
    if (!equips) return seal.replyToSender(ctx, msg, "❌ 无法读取装备数据。");

    if (!equips[slot] || !equips[slot].code) {
        return seal.replyToSender(ctx, msg, `❌ ${getSlotName(slot)}槽位没有装备。`);
    }

    const equipCode = equips[slot].code;
    const registry = getEquipRegistry();
    const equip = registry[equipCode];

    equips[slot] = null;
    savePlayerEquips(roleKey, equips);

    let msg_text = `✅ 你卸下了 ${equip.name}！`;
    return seal.replyToSender(ctx, msg, msg_text);
};

ext.cmdMap["脱装备"] = cmd_unequip;

// ========================
// 装备系统 - 玩家命令：强化装备
// ========================

let cmd_reinforce = seal.ext.newCmdItemInfo();
cmd_reinforce.name = "强化装备";
cmd_reinforce.help = "强化装备并提升属性\n强化装备 <槽位> [次数]\n\n示例: 强化装备 hand (强化1次)\n     强化装备 hand 5 (强化5次)\n\n执行「槽位 查看」查看所有可用槽位。";
cmd_reinforce.solve = (ctx, msg, cmdArgs) => {
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

    const slot = cmdArgs.getArgN(1);
    const times = parseInt(cmdArgs.getArgN(2)) || 1;

    if (!slot) return seal.replyToSender(ctx, msg, "❌ 请指定槽位。");

    const allSlots = getEquipSlots();
    if (!allSlots.includes(slot)) {
        return seal.replyToSender(ctx, msg, `❌ 无效的槽位。有效槽位: ${allSlots.join(", ")}`);
    }

    const parts = msg.sender.userId.split(':');
    const platform = parts[0];
    const roleKey = `${platform}:${player}`;

    const equips = getPlayerEquips(roleKey);
    if (!equips || !equips[slot] || !equips[slot].code) {
        return seal.replyToSender(ctx, msg, `❌ ${getSlotName(slot)}槽位没有装备。`);
    }

    const registry = getEquipRegistry();
    const equip = registry[equips[slot].code];
    if (!equip) return seal.replyToSender(ctx, msg, "❌ 装备数据错误。");

    const maxReinforce = equip.maxReinforce || 10;
    const currentLevel = equips[slot].reinforceLevel || 0;

    if (currentLevel >= maxReinforce) {
        return seal.replyToSender(ctx, msg, `❌ 该装备已达到最高强化等级 (${maxReinforce})。`);
    }

    const config = getEquipConfig();
    const costPerLevel = config.costPerLevel || [100, 150, 200, 250, 300, 400, 500, 600, 750, 1000];
    const successRate = config.successRate !== undefined ? config.successRate : 90;
    const main = getMain();

    let totalCost = 0;
    let results = [];

    for (let i = 0; i < times; i++) {
        const newLevel = currentLevel + i + 1;
        if (newLevel > maxReinforce) break;

        const cost = costPerLevel[Math.min(newLevel - 1, costPerLevel.length - 1)];
        totalCost += cost;

        // 检查成功率
        const roll = Math.random() * 100;
        if (roll < successRate) {
            results.push(`✅ 等级 ${newLevel - 1} → ${newLevel} 强化成功！`);
        } else {
            results.push(`❌ 等级 ${newLevel - 1} 强化失败！消耗金币已扣除。`);
            // 继续扣费，但不提升等级
            continue;
        }

        // 更新强化等级
        equips[slot].reinforceLevel = newLevel;
    }

    // 扣费（使用现有的货币系统）
    if (totalCost > 0) {
        try {
            const charCurrency = JSON.parse(main.storageGet("sys_character_currency") || "{}");
            if (!charCurrency[player]) charCurrency[player] = {};
            if (!charCurrency[player]["金币"]) charCurrency[player]["金币"] = 0;

            if (charCurrency[player]["金币"] < totalCost) {
                return seal.replyToSender(ctx, msg, `❌ 金币不足。需要 ${totalCost}，你有 ${charCurrency[player]["金币"]}。`);
            }

            charCurrency[player]["金币"] -= totalCost;
            main.storageSet("sys_character_currency", JSON.stringify(charCurrency));
        } catch(e) {
            return seal.replyToSender(ctx, msg, "❌ 扣费失败。");
        }
    }

    savePlayerEquips(roleKey, equips);

    let msg_text = `⚡ 强化结果:\n\n` + results.join("\n");
    msg_text += `\n\n💰 消耗金币: ${totalCost}`;
    msg_text += `\n当前强化等级: ${equips[slot].reinforceLevel}/${maxReinforce}`;

    return seal.replyToSender(ctx, msg, msg_text);
};

ext.cmdMap["强化装备"] = cmd_reinforce;

// ========================
// 装备系统 - 管理员命令：注册装备
// ========================

let cmd_register_equip = seal.ext.newCmdItemInfo();
cmd_register_equip.name = "注册装备";
cmd_register_equip.help = "【管理员】注册新装备\n注册装备 <装备名>*<描述>*<槽位>*<基础属性>*[强化属性]*[最大强化]\n\n属性格式: ATK+15,DEF+10 (用逗号分隔多个属性)\n属性必须已注册，执行「我创建属性」可注册新属性\n槽位：执行「槽位 查看」查看所有可用槽位\n\n示例:\n注册装备 铁制短剑*普通短剑*hand*ATK+15*ATK+2*10\n注册装备 钢铁胸甲*防御胸甲*chest*DEF+20,HP+50*DEF+3*10\n注册装备 智者法杖*法术武器*hand*智力+20,MP+50*智力+3*10";
cmd_register_equip.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const input = msg.messageType === "group" ?
        msg.rawMessage.substring(msg.rawMessage.indexOf(" ") + 1) :
        msg.rawMessage.substring(msg.rawMessage.indexOf(" ") + 1);

    const parts = input.split(/[*]/);
    if (parts.length < 4) {
        return seal.replyToSender(ctx, msg, "❌ 参数不足。格式: 装备名*描述*槽位*基础属性[*强化属性*最大强化]");
    }

    const name = parts[0].trim();
    const desc = parts[1].trim();
    const slot = parts[2].trim();
    const baseAttrStr = parts[3].trim();
    const reinforceAttrStr = parts[4]?.trim();
    const maxReinforceStr = parts[5]?.trim();

    const allSlots = getEquipSlots();
    if (!allSlots.includes(slot)) {
        return seal.replyToSender(ctx, msg, `❌ 无效槽位。有效槽位: ${allSlots.join(", ")}`);
    }

    // 解析属性
    const parseAttrs = (str) => {
        const attrs = {};
        if (!str) return attrs;
        const matches = str.split(',');
        matches.forEach(m => {
            const match = m.trim().match(/^(\w+)([\+\-])(\d+)$/);
            if (match) {
                const [, attrName, op, value] = match;
                attrs[attrName] = parseInt(value) * (op === '+' ? 1 : -1);
            }
        });
        return attrs;
    };

    const baseAttrs = parseAttrs(baseAttrStr);
    const reinforceBonus = reinforceAttrStr ? parseAttrs(reinforceAttrStr) : null;
    const maxReinforce = maxReinforceStr ? parseInt(maxReinforceStr) : 10;

    if (Object.keys(baseAttrs).length === 0) {
        return seal.replyToSender(ctx, msg, "❌ 基础属性格式错误。格式: ATK+15,DEF+10");
    }

    // 验证所有属性是否已注册
    const attrDefs = getAttrDefs();
    const allAttrNames = new Set([...Object.keys(baseAttrs)]);
    if (reinforceBonus) {
        Object.keys(reinforceBonus).forEach(attr => allAttrNames.add(attr));
    }

    const unregisteredAttrs = [];
    for (const attrName of allAttrNames) {
        if (!attrDefs[attrName]) {
            unregisteredAttrs.push(attrName);
        }
    }

    if (unregisteredAttrs.length > 0) {
        return seal.replyToSender(ctx, msg, `❌ 以下属性未注册: ${unregisteredAttrs.join(", ")}\n\n请先执行 \"我创建属性 <属性名>\" 来注册这些属性。`);
    }

    const registry = getEquipRegistry();
    const code = generateEquipCode(registry);

    registry[code] = {
        code: code,
        name: name,
        desc: desc,
        type: "equipment",
        slot: slot,
        baseAttrs: baseAttrs,
        reinforceBonus: reinforceBonus,
        maxReinforce: maxReinforce
    };

    saveEquipRegistry(registry);

    let msg_text = `✅ 装备已注册！\n\n`;
    msg_text += `代码: ${code}\n`;
    msg_text += `名称: ${name}\n`;
    msg_text += `槽位: ${getSlotName(slot)}\n`;
    msg_text += `基础属性: ${Object.entries(baseAttrs).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join(', ')}\n`;
    if (reinforceBonus) {
        msg_text += `强化属性: ${Object.entries(reinforceBonus).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}/级`).join(', ')}\n`;
        msg_text += `最大强化: ${maxReinforce}级\n`;
    }

    return seal.replyToSender(ctx, msg, msg_text);
};

ext.cmdMap["注册装备"] = cmd_register_equip;

// ========================
// 装备系统 - 管理员命令：强化配置
// ========================

let cmd_equip_config = seal.ext.newCmdItemInfo();
cmd_equip_config.name = "强化";
cmd_equip_config.help = "【管理员】配置强化系统\n强化 启 / 禁          - 启用/禁用强化系统\n强化 查看             - 查看强化配置\n强化 设置 成功率 <值>  - 设置强化成功率(0-100)\n强化 设置 消耗 <值>    - 设置强化消耗(每级增加)";
cmd_equip_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const subCmd = cmdArgs.getArgN(1);
    let config = getEquipConfig();

    if (subCmd === "启") {
        config.enabled = true;
        saveEquipConfig(config);
        return seal.replyToSender(ctx, msg, "✅ 强化系统已启用。");
    }

    if (subCmd === "禁") {
        config.enabled = false;
        saveEquipConfig(config);
        return seal.replyToSender(ctx, msg, "✅ 强化系统已禁用。");
    }

    if (subCmd === "查看") {
        let info = "⚙️ 强化系统配置:\n\n";
        info += `启用状态: ${config.enabled !== false ? "✅ 已启用" : "❌ 已禁用"}\n`;
        info += `成功率: ${config.successRate !== undefined ? config.successRate : 90}%\n`;
        const costs = config.costPerLevel || [100, 150, 200, 250, 300, 400, 500, 600, 750, 1000];
        info += `消耗: ${costs.join(', ')} (按强化等级递增)\n`;
        return seal.replyToSender(ctx, msg, info);
    }

    if (subCmd === "设置") {
        const param = cmdArgs.getArgN(2);
        const value = cmdArgs.getArgN(3);

        if (param === "成功率") {
            const rate = parseInt(value);
            if (isNaN(rate) || rate < 0 || rate > 100) {
                return seal.replyToSender(ctx, msg, "❌ 成功率必须在0-100之间。");
            }
            config.successRate = rate;
            saveEquipConfig(config);
            return seal.replyToSender(ctx, msg, `✅ 强化成功率已设置为 ${rate}%。`);
        }

        if (param === "消耗") {
            const increase = parseInt(value);
            if (isNaN(increase) || increase <= 0) {
                return seal.replyToSender(ctx, msg, "❌ 消耗增量必须为正整数。");
            }
            const costs = [];
            for (let i = 0; i < 10; i++) {
                costs.push(100 + i * increase);
            }
            config.costPerLevel = costs;
            saveEquipConfig(config);
            return seal.replyToSender(ctx, msg, `✅ 强化消耗已设置。各等级消耗: ${costs.join(', ')}`);
        }
    }

    return seal.replyToSender(ctx, msg, cmd_equip_config.help);
};

ext.cmdMap["强化"] = cmd_equip_config;

// ========================
// 装备系统 - 管理员命令：槽位管理
// ========================

let cmd_equip_slots = seal.ext.newCmdItemInfo();
cmd_equip_slots.name = "槽位";
cmd_equip_slots.help = "【管理员】管理装备槽位\n槽位 查看               - 查看所有槽位\n槽位 添加 <槽位码> <名称> - 添加新槽位\n槽位 删除 <槽位码>      - 删除槽位\n槽位 重置              - 重置为默认5个槽位\n\n示例:\n槽位 添加 ring1 戒指1\n槽位 添加 wing 翅膀\n槽位 删除 ring1";
cmd_equip_slots.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const subCmd = cmdArgs.getArgN(1);
    let slots = getEquipSlots();
    let slotNames = getSlotDisplayNames();

    if (subCmd === "查看") {
        let info = `📋 装备槽位列表 (${slots.length}个):\n\n`;
        slots.forEach((slot, idx) => {
            const displayName = slotNames[slot] || slot;
            info += `${idx + 1}. [${slot}] ${displayName}\n`;
        });
        return seal.replyToSender(ctx, msg, info);
    }

    if (subCmd === "添加") {
        const slotCode = cmdArgs.getArgN(2);
        const slotName = cmdArgs.getArgN(3);

        if (!slotCode || !slotName) {
            return seal.replyToSender(ctx, msg, "❌ 请指定槽位码和显示名称。");
        }

        if (slots.includes(slotCode)) {
            return seal.replyToSender(ctx, msg, `❌ 槽位「${slotCode}」已存在。`);
        }

        // 检查槽位码格式（只允许字母数字）
        if (!/^[a-z0-9_]+$/i.test(slotCode)) {
            return seal.replyToSender(ctx, msg, "❌ 槽位码只能包含字母、数字和下划线。");
        }

        slots.push(slotCode);
        slotNames[slotCode] = slotName;

        saveEquipSlots(slots);
        saveSlotDisplayNames(slotNames);

        return seal.replyToSender(ctx, msg, `✅ 已添加槽位「${slotCode}」(${slotName})。\n\n现在共有 ${slots.length} 个槽位。`);
    }

    if (subCmd === "删除") {
        const slotCode = cmdArgs.getArgN(2);

        if (!slotCode) {
            return seal.replyToSender(ctx, msg, "❌ 请指定要删除的槽位码。");
        }

        if (!slots.includes(slotCode)) {
            return seal.replyToSender(ctx, msg, `❌ 槽位「${slotCode}」不存在。`);
        }

        if (slots.length <= 1) {
            return seal.replyToSender(ctx, msg, "❌ 至少需要保留1个槽位。");
        }

        slots = slots.filter(s => s !== slotCode);
        delete slotNames[slotCode];

        saveEquipSlots(slots);
        saveSlotDisplayNames(slotNames);

        // 同时从所有玩家的装备数据中移除这个槽位
        const main = getMain();
        if (main) {
            try {
                const data = JSON.parse(main.storageGet("player_equipments") || "{}");
                for (const roleKey in data) {
                    delete data[roleKey][slotCode];
                }
                main.storageSet("player_equipments", JSON.stringify(data));
            } catch(e) {}
        }

        return seal.replyToSender(ctx, msg, `✅ 已删除槽位「${slotCode}」。\n\n现在共有 ${slots.length} 个槽位。\n\n⚠️ 该槽位上的装备已卸除。`);
    }

    if (subCmd === "重置") {
        const defaultSlots = ["head", "chest", "hand", "leg", "foot"];
        const defaultNames = {
            head: "头部",
            chest: "胸部",
            hand: "手部",
            leg: "腿部",
            foot: "脚部"
        };

        saveEquipSlots(defaultSlots);
        saveSlotDisplayNames(defaultNames);

        return seal.replyToSender(ctx, msg, `✅ 已重置为默认5个槽位:\n\n${defaultSlots.map(s => `· [${s}] ${defaultNames[s]}`).join("\n")}`);
    }

    return seal.replyToSender(ctx, msg, cmd_equip_slots.help);
};

ext.cmdMap["槽位"] = cmd_equip_slots;
