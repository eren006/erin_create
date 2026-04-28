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
    // 这样可以区分“用过一半的”和“全新的”
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
cmd_upload_item.help = "【管理员】注册新物品\n格式：名称*描述*次数*属性效果\n次数：-1为无限，正数位次数\n效果：属性+10,属性-5 (支持多个，逗号隔开)\n支持多行批量上载";

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
        const attrs = (parts[3] || "").trim() || null; // 属性效果字符串

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
            maxUses: maxUses, // 记录最大使用次数
            attrs: attrs,    // 存储复合属性字符串，如 "体力+10,心情-5"
            price: 0         // 默认价格，后续可通过商城指令修改
        };

        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        results.push(`✅ [${code}] ${name} | 次数:${useText} | 效果:[${attrs || "无"}]`);
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
cmd_upload_interact.help = "【管理员】注册互动类物品（对他人使用）\n格式：名称*描述*次数*属性效果\n示例：上载互动物品 医疗包*为他人包扎*1*体力+50";
cmd_upload_interact.solve = (ctx, msg, cmdArgs) => {
    if (ctx.privilegeLevel < 40) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rest = msg.message.replace(/^[。.]\s*上载互动物品\s*/, "").trim();
    if (!rest) return seal.ext.newCmdExecuteResult(true);

    const parts = rest.split(/[*＊]/);
    const name = (parts[0] || "").trim();
    const desc = (parts[1] || "").trim() || "暂无描述";
    const maxUses = parseInt((parts[2] || "").trim());
    const attrs = (parts[3] || "").trim() || null;

    if (!name || isNaN(maxUses)) return seal.replyToSender(ctx, msg, "❌ 格式错误。");

    const reg = getRegistry();
    let hdId = 1;
    const hdCodes = Object.keys(reg).filter(c => c.startsWith("HD"));
    if (hdCodes.length > 0) {
        const lastNum = Math.max(...hdCodes.map(c => parseInt(c.replace("HD", ""))));
        hdId = lastNum + 1;
    }
    const code = `HD${hdId.toString().padStart(3, '0')}`;

    reg[code] = { code, name, desc, type: "interact", maxUses, attrs };
    saveRegistry(reg);

    seal.replyToSender(ctx, msg, `✅ 互动道具已注册：[${code}] ${name}\n效果：${attrs || "无"}`);
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
cmd_apply.help = "对他人使用互动道具\n格式：施加 目标姓名 物品名/代码\n示例：施加 张三 医疗包";
cmd_apply.solve = (ctx, msg, cmdArgs) => {
    const main = getMain();
    // --- 新增：时段检查 ---
    if (!isApplyTimeValid(main)) {
        const hoursStr = main.storageGet("apply_item_hours");
        return seal.replyToSender(ctx, msg, `❌ 当前不在道具施加时段内。\n当前可用时段：${hoursStr}`);
    }
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
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
    const isAnonymous = main.storageGet("apply_item_anonymous") === "true";

    // 通知被施加者
    if (shouldNotify) {
        // 决定显示的名字：如果开启匿名，则显示“某人”
        const displayName = isAnonymous ? "某人" : `角色「${roleName}」`;
        
        notifyPlayer(ctx, platform, targetName, `💉 ${displayName} 对你使用了 [${item.name}]！\n📊 你的属性变化：${effectStr}`);
    }

    // 给发起者的反馈（发起者始终能看到详细信息）
    let feedback = `✅ 你成功对「${targetName}」使用了 [${item.name}] ${usageStatus}。`;
    if (!shouldNotify) {
        feedback += "\n(已根据设置隐藏对目标的通知)";
    } else if (isAnonymous) {
        feedback += "\n(已根据设置匿名通知目标)";
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
