// ==UserScript==
// @name         RPG系统
// @author       长日将尽
// @version      1.4.0
// @description  物品注册、背包、商城、抽取池、二手市场。所有数据存储在主插件 changri 中。
// @timestamp    1778742000
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5RPG.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5RPG.js
// ==/UserScript==

function getMainExt() {
    const main = seal.ext.find('changri');
    if (!main) {
        console.error("❌ RPG系统错误：未找到主插件 changri，请检查主插件是否已加载");
        return null;
    }
    return main;
}

let ext = seal.ext.find('changriRPG');
if (!ext) {
    ext = seal.ext.new("changriRPG", "长日将尽", "2.0.0");
    seal.ext.register(ext);
}

// ========================
// 核心依赖：主插件共享 API（globalThis.__changriApi，调用时懒获取）
// 主插件已更新时全部委托给它；否则走下方兼容实现（直读主插件存储）
// ========================

function getApi() { return globalThis.__changriApi || null; }

function mainStorGet(key) {
    const api = getApi();
    if (api) return api.kvGetRaw(key);
    const m = getMainExt();
    return m ? m.storageGet(key) : null;
}

function mainStorSet(key, val) {
    const api = getApi();
    if (api) { api.kvSetRaw(key, val); return; }
    const m = getMainExt();
    if (m) m.storageSet(key, val);
}

// 读取主插件整数型设置，兼容 JSON 编码的 '"70"' 与裸字符串 '70' 两种格式
function getMainStorageInt(key, defaultVal) {
    const api = getApi();
    if (api) return api.getStorageInt(key, defaultVal);
    const raw = mainStorGet(key);
    if (!raw) return defaultVal;
    try { return parseInt(JSON.parse(raw)) || defaultVal; }
    catch (e) { return parseInt(raw) || defaultVal; }
}

function isUserFeatureEnabled(uid, key, defaultValue = true) {
    const api = getApi();
    if (api) return api.isUserFeatureEnabled(uid, key, defaultValue);
    try {
        const blockMap = JSON.parse(mainStorGet("feature_user_blocklist") || "{}");
        const personConfig = blockMap[uid];
        if (personConfig && personConfig[key] !== undefined) return personConfig[key];
    } catch (e) { }
    return defaultValue;
}

function getPrimaryUid(platform, uid) {
    const api = getApi();
    if (api) return api.getPrimaryUid(platform, uid);
    try {
        const extras = JSON.parse(mainStorGet("extra_accounts") || "{}");
        return extras[`${platform}:${uid}`] || uid;
    } catch (e) { return uid; }
}

// 新结构：a_private_group[platform][uid] = [roleName, gid]
function getRoleName(ctx, msg) {
    const api = getApi();
    if (api) return api.getRoleName(ctx, msg);
    try {
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        const platform = msg.platform;
        const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
        const uid = getPrimaryUid(platform, rawUid);
        return apg[platform]?.[uid]?.[0] || null;
    } catch (e) { console.log("[物品V2] getRoleName: " + e.message); }
    return null;
}

// getRoleUid：roleName 反查 uid（主插件侧叫 getUidByRoleName）
function getRoleUid(platform, roleName) {
    const api = getApi();
    if (api) return api.getUidByRoleName(platform, roleName);
    try {
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        const roles = apg[platform] || {};
        const entry = Object.entries(roles).find(([_, v]) => v[0] === roleName);
        return entry ? entry[0] : null;
    } catch (e) { return null; }
}

function isUserAdmin(ctx, msg) {
    const api = getApi();
    if (api) return api.isUserAdmin(ctx, msg);
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    try {
        const a_adminList = JSON.parse(mainStorGet("a_adminList") || "{}");
        return ctx.privilegeLevel === 100 || (a_adminList[platform] && a_adminList[platform].includes(uid));
    } catch (e) { return false; }
}

// ========================
// 存储辅助
// ========================

function getRegistry() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("item_registry") || "{}") : {};
}
function saveRegistry(reg) {
    const main = getMainExt();
    if (main) mainStorSet("item_registry", JSON.stringify(reg));
}

// RPG 属性定义：{ attrName: { min, max, default, desc } }
// 兼容迁移旧格式 sys_attr_presets (数组) 和 item_valid_attrs (数组)
function getAttrDefs() {
    const main = getMainExt();
    if (!main) return {};
    let defs = {};
    try { defs = JSON.parse(mainStorGet("rpg_attr_defs") || "{}"); } catch(e) {}
    if (!Object.keys(defs).length) {
        let migrated = false;
        for (const key of ["sys_attr_presets", "item_valid_attrs"]) {
            try {
                const arr = JSON.parse(mainStorGet(key) || "[]");
                if (Array.isArray(arr)) arr.forEach(n => { if (n && !defs[n]) { defs[n] = { min: null, max: null, default: 0, desc: "" }; migrated = true; } });
            } catch(e) {}
        }
        if (migrated) {
            mainStorSet("rpg_attr_defs", JSON.stringify(defs));
            mainStorSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
        }
    }
    return defs;
}
function saveAttrDefs(defs) {
    const main = getMainExt();
    if (!main) return;
    mainStorSet("rpg_attr_defs", JSON.stringify(defs));
    // 保持 sys_attr_presets 同步，这样其他脚本调用时不会出错
    mainStorSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
}

// 角色属性数值：{ roleName: { attrName: value } }
function getCharAttrs() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("sys_character_attrs") || "{}") : {};
}
function saveCharAttrs(attrs) {
    const main = getMainExt();
    if (main) mainStorSet("sys_character_attrs", JSON.stringify(attrs));
}

function clampAttr(def, value) {
    if (!def) return value;
    if (def.min !== null && def.min !== undefined && value < def.min) return def.min;
    if (def.max !== null && def.max !== undefined && value > def.max) return def.max;
    return value;
}

function getValidAttrs() {
    return Object.keys(getAttrDefs());
}
function saveValidAttrs(attrs) {
    const defs = getAttrDefs();
    const newDefs = {};
    for (const a of attrs) {
        newDefs[a] = defs[a] || { min: null, max: null, default: 0, desc: "" };
    }
    saveAttrDefs(newDefs);
}

// 合成系统
function getCraftRecipes() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("craft_recipes") || "{}") : {};
}
function saveCraftRecipes(recipes) {
    const main = getMainExt();
    if (main) mainStorSet("craft_recipes", JSON.stringify(recipes));
}

function getInvAll() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("global_inventories") || "{}") : {};
}
function saveInvAll(invs) {
    const main = getMainExt();
    if (main) mainStorSet("global_inventories", JSON.stringify(invs));
}

function pruneExpiredItems(roleKey) {
    const invs = getInvAll();
    const inv = invs[roleKey];
    if (!inv) return;
    const now = Date.now();
    const pruned = inv.filter(e => !e.expiresAt || e.expiresAt > now);
    if (pruned.length !== inv.length) {
        invs[roleKey] = pruned;
        saveInvAll(invs);
    }
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
    const roleInv = (getInvAll()[roleKey]) || [];
    // 同一物品可能因 remainingUses 不同存在多条 entry，汇总所有
    return roleInv.filter(e => e.code === code).reduce((sum, e) => sum + (e.count || 0), 0);
}

function getPoolDefs() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("pool_definitions") || "{}") : {};
}
function savePoolDefs(defs) {
    const main = getMainExt();
    if (main) mainStorSet("pool_definitions", JSON.stringify(defs));
}

function getDrawConfig() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("pool_draw_config") || '{"total":2,"pools":{}}') : { total: 2, pools: {} };
}
function saveDrawConfig(cfg) {
    const main = getMainExt();
    if (main) mainStorSet("pool_draw_config", JSON.stringify(cfg));
}

function getShop() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("shop_listings") || "[]") : [];
}
function saveShop(shop) {
    const main = getMainExt();
    if (main) mainStorSet("shop_listings", JSON.stringify(shop));
}

function getMarket() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("secondhand_market") || "{}") : {};
}
function saveMarket(market) {
    const main = getMainExt();
    if (main) mainStorSet("secondhand_market", JSON.stringify(market));
}

function getMarketConfig() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("market_config") || '{"fee":3,"enabled":true}') : { fee: 3, enabled: true };
}
function saveMarketConfig(cfg) {
    const main = getMainExt();
    if (main) mainStorSet("market_config", JSON.stringify(cfg));
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

    const uid = getRoleUid(platform, roleName);
    if (!uid) return;
    const primaryUid = getPrimaryUid(platform, uid);
    const roleKey = `${platform}:${primaryUid}`;
    const charAttrs = getCharAttrs();
    // 新结构：charAttrs 以 uid 为 key
    const roleAttrs = charAttrs[primaryUid] || {};
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
        charAttrs[primaryUid] = roleAttrs;
        saveCharAttrs(charAttrs);
    }
}

// ========================
// 抽取次数系统
// ========================

function getPlayerDrawRec(platform, uid) {
    const main = getMainExt();
    if (!main) return null;
    const records = JSON.parse(mainStorGet("player_draw_records") || "{}");
    const key = `${platform}:${uid}`;
    let rec = records[key] || { day: "", used: {}, extra: {} };
    const currentDay = mainStorGet("global_days") || "";
    if (rec.day !== currentDay) { rec.day = currentDay; rec.used = {}; }
    return { records, key, rec };
}

function savePlayerDrawRec(records, key, rec) {
    const main = getMainExt();
    if (!main) return;
    records[key] = rec;
    mainStorSet("player_draw_records", JSON.stringify(records));
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

function drawFromTierFree(tier) {
    const available = (tier.items || []).filter(i => i.count > 0);
    if (!available.length) return null;
    const picked = available[Math.floor(Math.random() * available.length)];
    picked.count -= 1;
    if (picked.count <= 0) tier.items.splice(tier.items.indexOf(picked), 1);
    return picked.code; // caller saves defs
}

function getPityCounters() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("player_pity_counters") || "{}") : {};
}
function savePityCounters(counters) {
    const main = getMainExt();
    if (main) mainStorSet("player_pity_counters", JSON.stringify(counters));
}
function getPityCount(uid, poolName) {
    return (getPityCounters()[uid] || {})[poolName] || 0;
}
function setPityCount(uid, poolName, val) {
    const counters = getPityCounters();
    if (!counters[uid]) counters[uid] = {};
    if (val <= 0) delete counters[uid][poolName];
    else counters[uid][poolName] = val;
    savePityCounters(counters);
}

// ========================
// 通知辅助
// ========================

function notifyPlayer(ctx, platform, roleName, text) {
    const main = getMainExt();
    if (!main) return;
    const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
    // 新结构：通过 roleName 反查 uid，再取 gid
    const uid = getRoleUid(platform, roleName);
    if (!uid) return;
    const info = apg[platform]?.[uid];
    if (!info) return;
    const notifyMsg = seal.newMessage();
    notifyMsg.messageType = "group";
    notifyMsg.groupId = `${platform}-Group:${info[1]}`;
    const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
    seal.replyToSender(notifyCtx, notifyMsg, `[CQ:at,qq=${uid}]\n${text}`);
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
    const main = getMainExt();
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
    if (!reg["SPEC_003"]) {
        reg["SPEC_003"] = { code: "SPEC_003", name: "望远镜", desc: "一架精致的望远镜，使用后可在目标下次发信时悄悄抄录一份副本。", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_004"]) {
        reg["SPEC_004"] = { code: "SPEC_004", name: "羽毛笔", desc: "一支神奇的羽毛笔，使用后可截获目标发出的下一封信并在发送前修改内容。", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_005"]) {
        reg["SPEC_005"] = { code: "SPEC_005", name: "捕鼠器", desc: "一个精巧的捕鼠器，激活后将锁定目标指定小时内的行动，使其无法私约、电话或摘心愿。", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_006"]) {
        reg["SPEC_006"] = { code: "SPEC_006", name: "窃听器", desc: "一枚微型窃听装置，激活后可悄悄截录目标的电话内容——信号有时会有些干扰……", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_007"]) {
        reg["SPEC_007"] = { code: "SPEC_007", name: "截信器", desc: "一台隐蔽的信号截断仪，激活后可拦截目标发出的短信，但内容偶有失真……", type: "preset", attrs: null };
        changed = true;
    }
    if (!reg["SPEC_008"]) {
        reg["SPEC_008"] = { code: "SPEC_008", name: "回音壁", desc: "一面奇异的墙壁，贴上后可感知所有投向目标的信件内容——对方收到什么，你便知晓什么。", type: "preset", attrs: null };
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

// ========================
// 特殊物品使用逻辑
// ========================


// ========================
// 使用记录
// ========================

function logItemUsage(platform, roleName, code, itemName) {
    const main = getMainExt();
    if (!main) return;
    const log = JSON.parse(mainStorGet("item_usage_log") || "[]");
    log.push({ timestamp: Date.now(), platform, roleName, code, name: itemName });
    if (log.length > 500) log.splice(0, log.length - 500);
    mainStorSet("item_usage_log", JSON.stringify(log));
}

// ========================
// 背包显示（手机版紧凑格式）
// ========================

function formatItemEntry(entry, info) {
    const name = info.name || entry.code;
    const shortName = name.length > 8 ? name.slice(0, 8) : name;
    const codeShort = entry.code.slice(-3);
    const desc = (info.desc || "").slice(0, 15);
    const uses = (entry.remainingUses ?? info.maxUses ?? -1);
    const usesStr = uses === -1 ? "∞次" : `余${uses}次`;

    let tags = "";
    if (info.type === "preset") tags += "🎯";
    if (info.canResell === false) tags += "🔒";
    if (info.canResell === true) tags += "✨";

    let line1 = `·${shortName}[${codeShort}]${tags}`;
    let line2 = `数量×${entry.count}|${usesStr}`;
    let line3 = desc || "无描述";

    let result = `${line1}\n${line2}\n${line3}`;

    if (info.attrs) {
        const attrsShort = info.attrs.slice(0, 22);
        result += `\n${attrsShort}`;
    }

    return result;
}

function formatInventory(roleKey, roleName, reg, category = "全部", page = 1) {
    const inv = getInv(roleKey).filter(e => e.count > 0);

    const currencies = [], presets = [], items = [];
    // 所有注册货币都显示，即使玩家没有记录也补0
    for (const [code, info] of Object.entries(reg)) {
        if (info.type !== "currency") continue;
        const entry = inv.find(e => e.code === code) || { code, count: 0 };
        currencies.push({ entry, info });
    }
    for (const entry of inv) {
        const info = reg[entry.code] || { name: entry.code, type: "item" };
        if (info.type === "currency") continue;
        else if (info.type === "preset") presets.push({ entry, info });
        else items.push({ entry, info });
    }

    if (!currencies.length && !presets.length && !items.length) return `🎒【${roleName}】背包空空`;

    const PAGE_SIZE = 6;
    const catList = [];
    if (currencies.length) catList.push({ name: "货币", emoji: "💰", items: currencies });
    if (presets.length) catList.push({ name: "道具", emoji: "⚙️", items: presets });
    if (items.length) catList.push({ name: "物品", emoji: "📦", items });

    let lines = [`背包|${roleName}`];

    if (category === "全部") {
        for (const cat of catList) {
            const displayItems = cat.items.slice(0, 3);
            lines.push(`${cat.emoji}${cat.name}(${cat.items.length})`);
            for (const { entry, info } of displayItems) {
                if (info.type === "currency") {
                    lines.push(`${info.name}：${entry.count}`);
                } else {
                    lines.push(formatItemEntry(entry, info));
                }
            }
            if (cat.items.length > 3) {
                lines.push(`>查看全部${cat.items.length - 3}项`);
            }
        }
        lines.push("");
        lines.push("指令:");
        lines.push(".背包 货币/道具/物品");
        lines.push(".背包 搜 关键词");
    } else {
        const catMap = { "货币": "currency", "道具": "preset", "物品": "item" };
        const typeFilter = catMap[category];
        const filtered = catList.find(c => {
            if (typeFilter === "currency") return c.emoji === "💰";
            if (typeFilter === "preset") return c.emoji === "⚙️";
            if (typeFilter === "item") return c.emoji === "📦";
            return false;
        });

        if (!filtered || !filtered.items.length) {
            return `🎒背包无${category}`;
        }

        const total = filtered.items.length;
        const start = (page - 1) * PAGE_SIZE;
        const end = Math.min(start + PAGE_SIZE, total);
        const pageItems = filtered.items.slice(start, end);
        const totalPages = Math.ceil(total / PAGE_SIZE);

        lines.push(`${filtered.emoji}${category} ${page}/${totalPages}`);
        for (const { entry, info } of pageItems) {
            if (info.type === "currency") {
                lines.push(`${info.name}：${entry.count}`);
            } else {
                lines.push(formatItemEntry(entry, info));
            }
        }

        if (totalPages > 1) {
            lines.push("");
            if (page > 1) lines.push(`⬅️.背包 ${category} ${page-1}`);
            if (page < totalPages) lines.push(`➡️.背包 ${category} ${page+1}`);
        }
        lines.push(".背包");
    }

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
    const arg1 = cmdArgs.getArgN(1);
    if (!arg1) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const arg2 = cmdArgs.getArgN(2);
    const arg3 = cmdArgs.getArgN(3);
    const arg4 = cmdArgs.getArgN(4);

    const reg = getRegistry();
    const currencyNames = new Set(Object.values(reg).filter(r => r.type === "currency").map(r => r.name));

    // 格式：我创建属性 [名] [最小] [最大] [默认]
    if (arg2 !== "" && !isNaN(Number(arg2))) {
        if (currencyNames.has(arg1)) return seal.replyToSender(ctx, msg, `❌ 属性名「${arg1}」已被货币占用`);
        const min = Number(arg2);
        const max = arg3 !== "" && !isNaN(Number(arg3)) ? Number(arg3) : null;
        const defaultVal = arg4 !== "" && !isNaN(Number(arg4)) ? Number(arg4) : 0;
        const existDefs = getAttrDefs();
        const isNew = !existDefs[arg1];
        existDefs[arg1] = { min, max, default: defaultVal, desc: existDefs[arg1]?.desc || "" };
        saveAttrDefs(existDefs);
        return seal.replyToSender(ctx, msg, `✅ ${isNew ? "新增" : "更新"}属性「${arg1}」：最小${min} 最大${max ?? "无限"} 默认${defaultVal}`);
    }

    // 旧格式：批量注册属性名（无范围）
    const newAttrs = [arg1];
    for (let i = 2; ; i++) { const a = cmdArgs.getArgN(i); if (!a) break; newAttrs.push(a); }
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

// ========================
// 初始化预设物品
// ========================

let cmd_init_preset = seal.ext.newCmdItemInfo();
cmd_init_preset.name = "初始化预设物品";
cmd_init_preset.help = "【管理员】初始化系统预设物品（追踪器、万能钥匙、金币、银币）\n格式：。初始化预设物品";
cmd_init_preset.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    initPresetItems();
    seal.replyToSender(ctx, msg, "✅ 已初始化系统预设物品：追踪器、万能钥匙、望远镜、羽毛笔、捕鼠器、窃听器、截信器、回音壁，以及默认货币金币/银币");
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["初始化预设物品"] = cmd_init_preset;

let cmd_upload_item = seal.ext.newCmdItemInfo();
cmd_upload_item.name = "上载物品";
cmd_upload_item.help = "【管理员】注册新物品\n格式：名称*描述*次数*属性效果*允许二手\n次数：-1为无限，正数为次数\n效果：属性+10,属性-5（仅限已注册属性或货币，多个逗号隔开，可为空）\n允许二手：Y/N，默认N\n支持多行批量上载";

cmd_upload_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);

    // 第一行去掉指令前缀后的剩余内容
    const firstLineRest = msgParts[0].replace(/^[。.]\s*上载物品\s*/, "").trim();
    const extraLines = msgParts.slice(1).map(l => l.trim()).filter(l => l);
    const itemLines = [...(firstLineRest ? [firstLineRest] : []), ...extraLines];

    if (!itemLines.length) {
        const validAttrs = getValidAttrs();
        const attrList = validAttrs.length ? validAttrs.join("、") : "（暂无，请先注册属性）";
        return seal.replyToSender(ctx, msg, `📦 上载物品格式：\n名称*描述*次数*属性效果*允许二手\n\n· 次数：-1 为无限，正数为使用次数\n· 效果：属性+数字,属性-数字（可为空）\n· 允许二手：Y 或 N（默认 N）\n· 支持多行批量，每行一条\n\n当前可用属性：${attrList}`);
    }

    const reg = getRegistry();
    const defs = getAttrDefs();
    const currencyNames = new Set(Object.values(reg).filter(i => i.type === "currency").map(i => i.name));
    const results = [];

    for (const line of itemLines) {
        const parts = line.split(/[*＊]/);
        if (parts.length < 3) {
            results.push(`❌ 格式错误：「${line.substring(0, 15)}」需至少包含 名称*描述*次数`);
            continue;
        }

        const name = (parts[0] || "").trim();
        const desc = (parts[1] || "").trim() || "暂无描述";
        const maxUses = parseInt((parts[2] || "").trim());
        const attrsRaw = (parts[3] || "").trim();
        const canResell = ((parts[4] || "").trim().toUpperCase() === "Y");

        if (!name) { results.push(`❌ 名称不能为空`); continue; }
        if (isNaN(maxUses)) { results.push(`❌ 「${name}」次数必须是数字`); continue; }

        // 效果格式校验
        let attrsStr = null;
        if (attrsRaw) {
            const segments = attrsRaw.split(/[,，]/);
            let attrErr = null;
            for (const seg of segments) {
                const m = seg.trim().match(/^(.+?)([+-]\d+)$/);
                if (!m) { attrErr = `效果格式错误「${seg.trim()}」，需为：属性+数字 或 属性-数字`; break; }
                const attrName = m[1];
                if (!defs[attrName] && !currencyNames.has(attrName)) {
                    attrErr = `未知属性「${attrName}」，请先注册属性`; break;
                }
            }
            if (attrErr) { results.push(`❌ 「${name}」${attrErr}`); continue; }
            attrsStr = attrsRaw;
        }

        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) { results.push(`⚠️ 「${name}」已存在 [${existing.code}]，跳过`); continue; }

        const code = genItemCode(reg);
        if (!code) { results.push("❌ 代码空间已满，无法继续注册"); break; }

        reg[code] = { code, name, desc, type: "item", maxUses, attrs: attrsStr, price: 0, canResell };

        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        const resellText = canResell ? "可二手" : "不可二手";
        results.push(`✅ [${code}] ${name} | ${useText} | 效果:${attrsStr || "无"} | ${resellText}`);
    }

    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `📦 物品注册结果（共${results.length}条）：\n${results.join("\n")}`);
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
    const existing = Object.values(reg).find(r => r.name === name);
    if (existing) return seal.replyToSender(ctx, msg, `⚠️ 「${name}」已存在 [${existing.code}]（${existing.type}），货币名不能重复`);
    const validAttrs = getValidAttrs();
    if (validAttrs.includes(name)) return seal.replyToSender(ctx, msg, `❌ 「${name}」已被注册为属性，货币名不能与属性重复`);
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
cmd_item_list.help = "查看所有已注册物品/货币\n物品列表 [物品|互动|货币|预设|全部]";
cmd_item_list.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const reg = getRegistry();
    const filter = cmdArgs.getArgN(1) || "全部";
    const entries = Object.values(reg).filter(e => {
        if (filter === "货币") return e.type === "currency";
        if (filter === "物品") return e.type === "item";
        if (filter === "预设") return e.type === "preset";
        if (filter === "互动") return e.type === "interact";
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
    const poolDefs = getPoolDefs();
    const boundPools = Object.values(poolDefs).filter(p => p.type === "tiered" && p.attr === name).map(p => p.name);
    if (boundPools.length) return seal.replyToSender(ctx, msg, `❌ 属性「${name}」正被分段池「${boundPools.join("、")}」绑定，无法删除。\n请先删除或修改这些池子。`);
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
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    // 新结构：通过 roleName 反查 uid
    const setAttrUid = getRoleUid(msg.platform, roleName);
    if (!setAttrUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」`);
    const setAttrPrimaryUid = getPrimaryUid(msg.platform, setAttrUid);
    const defs = getAttrDefs();
    const clamped = clampAttr(defs[attrName], val);
    const charAttrs = getCharAttrs();
    if (!charAttrs[setAttrPrimaryUid]) charAttrs[setAttrPrimaryUid] = {};
    charAttrs[setAttrPrimaryUid][attrName] = clamped;
    saveCharAttrs(charAttrs);
    const note = clamped !== val ? `（已截断至范围内：${clamped}）` : "";
    seal.replyToSender(ctx, msg, `✅ 【${roleName}】${attrName} 已设为 ${clamped}${note}`);
    notifyPlayer(ctx, msg.platform, roleName, `📊【属性更新】你的「${attrName}」已设定为 ${clamped}${note}`);
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

    // 检查特殊道具限制（SPEC_003望远镜、SPEC_004羽毛笔）
    if ((item.code === "SPEC_003" || item.code === "SPEC_004")) {
        const letterExt = seal.ext.find("changri");
        if (letterExt) {
            const config = JSON.parse(mainStorGet("global_feature_toggle") || "{}");
            if (!config.enable_direct_letter) {
                return seal.replyToSender(ctx, msg, `❌ 「${item.name}」只有在启用写信综模式后才能上架。`);
            }
        } else {
            return seal.replyToSender(ctx, msg, `❌ 写信系统未找到。`);
        }
    }

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
cmd_reg_pool.help = "【管理员】创建抽取池\n注册池子 池子名 数量 —— 数量池（有限个数，抽完即止）\n注册池子 池子名 权重 —— 权重池（加权随机，不减少）\n注册池子 池子名 保底 —— 保底池（权重随机+累计保底，跨天持久）\n💡 也可直接「上架池子」，池子不存在时会自动创建为数量池";
cmd_reg_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    const poolTypeRaw = cmdArgs.getArgN(2);
    const typeMap = { "数量": "free", "自由": "free", "free": "free", "权重": "fixed", "固定": "fixed", "fixed": "fixed", "保底": "pity", "pity": "pity" };
    const poolType = typeMap[poolTypeRaw];
    if (!poolName || !poolType) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const existTypeStr = defs[poolName] ? (defs[poolName].type === "fixed" ? "权重池" : defs[poolName].type === "pity" ? "保底池" : "数量池") : "";
    if (defs[poolName]) return seal.replyToSender(ctx, msg, `⚠️ 池子「${poolName}」已存在（${existTypeStr}）。`);
    const newPool = { name: poolName, type: poolType, items: [], enabled: true };
    if (poolType === "pity") { newPool.pityItems = []; newPool.pityThreshold = 10; }
    defs[poolName] = newPool;
    savePoolDefs(defs);
    const typeLabel = poolType === "fixed" ? "权重池" : poolType === "pity" ? "保底池（默认10次触发）" : "数量池";
    seal.replyToSender(ctx, msg, `✅ 池子「${poolName}」已创建（${typeLabel}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["注册池子"] = cmd_reg_pool;

let cmd_pool_add = seal.ext.newCmdItemInfo();
cmd_pool_add.name = "上架池子";
cmd_pool_add.help = `【管理员】向池子添加物品（池子不存在时自动创建为数量池）
数量池：上架池子 池子名 物品码*数量
权重池：上架池子 池子名 物品码*权重
多行批量（推荐）：
。上架池子 池子名
物品码*数量
物品码2*数量2`;
cmd_pool_add.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    let pool = defs[poolName];
    let autoCreated = false;
    if (!pool) {
        defs[poolName] = { name: poolName, type: "free", items: [], enabled: true };
        pool = defs[poolName];
        autoCreated = true;
    }
    const rawMsg = (msg.message || "").trim();
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

        // 检查特殊道具限制（SPEC_003望远镜、SPEC_004羽毛笔）
        if ((item.code === "SPEC_003" || item.code === "SPEC_004")) {
            const letterExt = seal.ext.find("changri");
            if (letterExt) {
                const config = JSON.parse(mainStorGet("global_feature_toggle") || "{}");
                if (!config.enable_direct_letter) {
                    results.push(`❌ 「${item.name}」只有在启用写信综模式后才能添加到池子。`);
                    continue;
                }
            } else {
                results.push(`❌ 写信系统未找到。`);
                continue;
            }
        }

        if (isNaN(num) || num <= 0) { results.push(`❌ 数值无效: ${parts[1]}`); continue; }
        if (pool.type === "fixed" || pool.type === "pity") {
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
    const header = autoCreated ? `🆕 池子「${poolName}」不存在，已自动创建为数量池。\n` : "";
    seal.replyToSender(ctx, msg, `${header}上架结果：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上架池子"] = cmd_pool_add;

let cmd_pool_remove = seal.ext.newCmdItemInfo();
cmd_pool_remove.name = "从池移除";
cmd_pool_remove.help = `【管理员】从池子中移除物品，支持多行批量
从池移除 池子名 物品码   —— 移除单个
多行批量：
。从池移除 池子名
物品码1
物品码2`;
cmd_pool_remove.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let inputCodes;
    if (msgParts.length > 1) {
        inputCodes = msgParts.slice(1).map(l => l.trim()).filter(l => l);
    } else {
        const single = cmdArgs.getArgN(2);
        if (!single) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
        inputCodes = [single];
    }
    const reg = getRegistry();
    const results = [];
    for (const inputCode of inputCodes) {
        const item = findItem(reg, inputCode);
        const code = item ? item.code : inputCode.toUpperCase();
        const idx = pool.items.findIndex(i => i.code === code);
        if (idx === -1) { results.push(`❌ [${code}] 不在池子中`); continue; }
        pool.items.splice(idx, 1);
        results.push(`✅ 已移除 [${code}]${item?.name || ""}`);
    }
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `从「${poolName}」移除：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["从池移除"] = cmd_pool_remove;

let cmd_pool_config = seal.ext.newCmdItemInfo();
cmd_pool_config.name = "池子设定";
cmd_pool_config.help = `【管理员】查看或设置每游戏日抽取次数
池子设定              —— 查看全部设定与池子状态
池子设定 总量 N       —— 全局每日总次数
池子设定 总量 无限    —— 全局无限制
池子设定 池子名 N     —— 给特定池设专属次数
池子设定 池子名 无限  —— 移除该池专属次数限制`;
cmd_pool_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    if (!arg1 || arg1 === "查看") {
        const cfg = getDrawConfig();
        const defs = getPoolDefs();
        const totalStr = (cfg.total !== null && cfg.total !== undefined) ? `${cfg.total}次/天` : "无限";
        let text = `📊 池子设定一览 | 全局总量：${totalStr}\n`;
        const poolList = Object.values(defs);
        if (!poolList.length) {
            text += "\n（暂无池子）";
        } else {
            for (const pool of poolList) {
                const icon = pool.enabled ? "✅" : "❌";
                const typeStr = pool.type === "fixed" ? "权重" : pool.type === "pity" ? "保底" : "数量";
                const poolLimit = cfg.pools?.[pool.name];
                const limitStr = poolLimit !== undefined ? `${poolLimit}次/天` : "跟随全局";
                const itemCount = pool.items.length;
                const stockStr = pool.type === "free"
                    ? `${pool.items.reduce((s, i) => s + (i.count || 0), 0)}个`
                    : `${itemCount}种`;
                const pityNote = pool.type === "pity" ? `｜保底${pool.pityThreshold || 10}次` : "";
                text += `\n${icon} 【${pool.name}】${typeStr}池 | 库存${stockStr} | ${limitStr}${pityNote}`;
            }
        }
        return seal.replyToSender(ctx, msg, text);
    }
    const cfg = getDrawConfig();
    if (arg1 === "总量") {
        if (!arg2) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
        cfg.total = arg2 === "无限" ? null : parseInt(arg2);
        if (arg2 !== "无限" && isNaN(cfg.total)) return seal.replyToSender(ctx, msg, "❌ 次数必须为正整数或「无限」。");
        saveDrawConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 全局总量：${cfg.total !== null ? cfg.total + "次/天" : "无限"}`);
    }
    if (!arg2) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    if (arg2 === "无限") {
        if (cfg.pools) delete cfg.pools[arg1];
        saveDrawConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 已移除「${arg1}」的专属次数限制（跟随全局）`);
    }
    const n = parseInt(arg2);
    if (isNaN(n) || n < 0) return seal.replyToSender(ctx, msg, "❌ 次数必须为非负整数或「无限」。");
    if (!cfg.pools) cfg.pools = {};
    cfg.pools[arg1] = n;
    saveDrawConfig(cfg);
    seal.replyToSender(ctx, msg, `✅ 池子「${arg1}」每日次数：${n}次`);
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

function registerPoolToggleCmds() {
    ext.cmdMap["开启池子"] = makePoolToggleCmd("开启池子", true);
    ext.cmdMap["关闭池子"] = makePoolToggleCmd("关闭池子", false);
}

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

let cmd_batch_create_pools = seal.ext.newCmdItemInfo();
cmd_batch_create_pools.name = "一键建池";
cmd_batch_create_pools.help = "【管理员】根据地点列表批量创建同名自由池\n一键建池 —— 为所有已注册地点创建「地点名池」（free类型，已存在的跳过）";
cmd_batch_create_pools.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    const places = JSON.parse(mainStorGet("available_places") || "{}");
    const placeNames = Object.keys(places);
    if (!placeNames.length) return seal.replyToSender(ctx, msg, "❌ 暂无已注册地点，请先用「地点 添加 地点名」添加地点。");

    const defs = getPoolDefs();
    const created = [];
    const skipped = [];

    for (const placeName of placeNames) {
        const poolName = `${placeName}池`;
        if (defs[poolName]) {
            skipped.push(poolName);
        } else {
            defs[poolName] = { name: poolName, type: "free", items: [], enabled: true };
            created.push(poolName);
        }
    }

    if (created.length) savePoolDefs(defs);

    const lines = [];
    if (created.length) lines.push(`✅ 已创建（${created.length}个）：${created.join("、")}`);
    if (skipped.length) lines.push(`⏭️ 已跳过（${skipped.length}个，已存在）：${skipped.join("、")}`);
    seal.replyToSender(ctx, msg, `🎲 一键建池完成：\n${lines.join("\n")}\n\n💡 请用「上架池子 池子名 物品码*数量」往池子里加物品。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["一键建池"] = cmd_batch_create_pools;

let cmd_view_pool = seal.ext.newCmdItemInfo();
cmd_view_pool.name = "查看池子";
cmd_view_pool.help = `【管理员】查看池子详情
查看池子          —— 列出所有池子状态（等同于「池子设定」查看）
查看池子 池子名   —— 显示该池子的全部物品`;
cmd_view_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    const defs = getPoolDefs();
    const cfg = getDrawConfig();
    const reg = getRegistry();
    if (!poolName) {
        const poolList = Object.values(defs);
        if (!poolList.length) return seal.replyToSender(ctx, msg, "📭 当前没有任何池子。\n💡 用「上架池子 池子名 物品码*数量」创建并上架。");
        const totalStr = (cfg.total !== null && cfg.total !== undefined) ? `${cfg.total}次/天` : "无限";
        let text = `🎲 抽取池一览（${poolList.length}个）| 全局总量：${totalStr}`;
        for (const pool of poolList) {
            const icon = pool.enabled ? "✅" : "❌";
            const typeStr = pool.type === "fixed" ? "权重池" : pool.type === "tiered" ? "分段池" : pool.type === "pity" ? "保底池" : "数量池";
            const poolLimit = cfg.pools?.[pool.name];
            const limitStr = poolLimit !== undefined ? `${poolLimit}次/天` : "全局";
            let totalStock;
            if (pool.type === "tiered") {
                const tiers = pool.tiers || [];
                totalStock = `${tiers.length}段`;
            } else if (pool.type === "free") {
                totalStock = pool.items.reduce((s, i) => s + (i.count || 0), 0) + "个";
            } else {
                totalStock = pool.items.length + "种";
            }
            const pityNote = pool.type === "pity" ? `｜保底${pool.pityThreshold || 10}次` : "";
            text += `\n${icon} 【${pool.name}】${typeStr} | 库存${totalStock} | ${limitStr}${pityNote}`;
        }
        return seal.replyToSender(ctx, msg, text);
    }
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    const typeStr = pool.type === "fixed" ? "权重池" : pool.type === "tiered" ? "分段池" : pool.type === "pity" ? "保底池" : "数量池";
    const statusStr = pool.enabled ? "已开启" : "已关闭";
    const poolLimit = cfg.pools?.[poolName];
    const totalStr = (cfg.total !== null && cfg.total !== undefined) ? `${cfg.total}次` : "无限";
    const limitStr = poolLimit !== undefined ? `${poolLimit}次/天（专属）` : `跟随全局（${totalStr}/天）`;
    let text = `📦 【${poolName}】${typeStr} · ${statusStr} | 抽取：${limitStr}`;
    if (pool.type === "pity") {
        const threshold = pool.pityThreshold || 10;
        const pityCount = (pool.items || []).length;
        const pityItemCount = (pool.pityItems || []).length;
        text += `\n保底阈值：${threshold}次｜普通物品：${pityCount}种｜保底物品：${pityItemCount}种`;
        if (pool.items.length) {
            text += `\n\n📋 普通物品（权重池）：`;
            for (const entry of pool.items) {
                const item = reg[entry.code] || { name: entry.code };
                text += `\n  · ${item.name} [${entry.code}] 权重×${entry.weight}`;
            }
        }
        if ((pool.pityItems || []).length) {
            text += `\n\n🌟 保底物品：`;
            for (const entry of pool.pityItems) {
                const item = reg[entry.code] || { name: entry.code };
                text += `\n  · ${item.name} [${entry.code}] 权重×${entry.weight}`;
            }
        }
        return seal.replyToSender(ctx, msg, text);
    }
    if (pool.type === "tiered") {
        const tiers = pool.tiers || [];
        text += `\n绑定属性：${pool.attr || "未设置"} | 共 ${tiers.length} 个分段`;
        for (const t of tiers) {
            const lo = t.min !== null && t.min !== undefined ? t.min : "-∞";
            const hi = t.max !== null && t.max !== undefined ? t.max : "+∞";
            const tType = t.type === "fixed" ? "权重" : "数量";
            const label = t.label ? `[${t.label}] ` : "";
            text += `\n  · ${label}${lo} ≤ ${pool.attr} < ${hi}（${tType}，${t.items?.length || 0}种）`;
        }
    } else if (!pool.items.length) {
        text += "\n\n📭 池子内暂无物品。";
    } else {
        text += `\n\n📋 物品列表（${pool.items.length}种）：`;
        for (const entry of pool.items) {
            const item = reg[entry.code] || { name: entry.code };
            if (pool.type === "fixed") {
                text += `\n  · ${item.name} [${entry.code}] 权重×${entry.weight}`;
            } else {
                text += `\n  · ${item.name} [${entry.code}] ×${entry.count}`;
            }
        }
        if (pool.type === "free") {
            const total = pool.items.reduce((s, i) => s + (i.count || 0), 0);
            text += `\n\n合计库存：${total} 个`;
        }
    }
    return seal.replyToSender(ctx, msg, text);
};
ext.cmdMap["查看池子"] = cmd_view_pool;

let cmd_clear_pool = seal.ext.newCmdItemInfo();
cmd_clear_pool.name = "清空池子";
cmd_clear_pool.help = "【管理员】清空池子内所有物品（保留池子结构和设定）\n清空池子 池子名";
cmd_clear_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    const count = pool.items.length;
    pool.items = [];
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 已清空「${poolName}」（移除 ${count} 种物品）。\n💡 池子结构和次数设定保留，可直接「上架池子」补货。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空池子"] = cmd_clear_pool;

let cmd_adjust = seal.ext.newCmdItemInfo();
cmd_adjust.name = "调整";
cmd_adjust.help = "【管理员】直接调整玩家背包数量\n调整 角色名 物品码 +N [物品码2 +N2 ...]\n示例：调整 张三 ITEM_001 +3\n多个：调整 张三 ITEM_001 +3 ITEM_002 -1 SPEC_005 +2";
cmd_adjust.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1);
    if (!roleName || !cmdArgs.getArgN(2)) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const platform = msg.platform;
    const uid = getRoleUid(platform, roleName);
    if (!uid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const roleKey = `${platform}:${getPrimaryUid(platform, uid)}`;
    const reg = getRegistry();

    // 收集所有 物品码+数量 对（从 arg2 开始，每两个一组）
    const pairs = [];
    let i = 2;
    while (true) {
        const code = cmdArgs.getArgN(i);
        const deltaStr = cmdArgs.getArgN(i + 1);
        if (!code) break;
        if (!deltaStr) { pairs.push({ err: `「${code}」缺少数量` }); break; }
        const delta = parseInt(deltaStr);
        if (isNaN(delta)) { pairs.push({ err: `「${code}」数量格式错误：${deltaStr}` }); break; }
        const item = findItem(reg, code);
        if (!item) { pairs.push({ err: `找不到物品「${code}」` }); i += 2; continue; }
        pairs.push({ item, delta });
        i += 2;
    }

    if (!pairs.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const lines = [];
    for (const p of pairs) {
        if (p.err) { lines.push(`❌ ${p.err}`); continue; }
        const { item, delta } = p;
        if (delta === 0) { lines.push(`⚠️ ${item.name} 调整量为0，跳过`); continue; }
        if (delta > 0) {
            addToInv(roleKey, item.code, delta);
            lines.push(`✅ [${item.code}]${item.name} ×${delta} 已加入背包`);
            notifyPlayer(ctx, platform, roleName, `📦【背包更新】${item.name} ×${delta} 已加入你的背包。`);
        } else {
            if (!removeFromInv(roleKey, item.code, -delta)) {
                lines.push(`❌ [${item.code}]${item.name} 背包数量不足，跳过`);
            } else {
                lines.push(`✅ [${item.code}]${item.name} ×${-delta} 已扣除`);
                notifyPlayer(ctx, platform, roleName, `📦【背包更新】${item.name} ×${-delta} 已从你的背包中移除。`);
            }
        }
    }

    seal.replyToSender(ctx, msg, `📦 调整「${roleName}」背包（共${pairs.length}项）：\n${lines.join("\n")}`);
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
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const platform = msg.platform;
    // 新结构：通过 roleName 反查 uid
    const uid = getRoleUid(platform, roleName);
    if (!uid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const drRec = getPlayerDrawRec(platform, getPrimaryUid(platform, uid));
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
        notifyPlayer(ctx, platform, roleName, `✨【机会降临】你在「${poolName}」中获得了 ${n} 次额外抽取机会！`);
    } else {
        rec.extra._total = (rec.extra._total || 0) + n;
        seal.replyToSender(ctx, msg, `✅ 已为「${roleName}」发放总额外次数 ×${n}`);
        notifyPlayer(ctx, platform, roleName, `✨【机会降临】你获得了 ${n} 次额外抽取机会！`);
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
    const adminPlatform = msg.platform;
    const adminTargetUid = getRoleUid(adminPlatform, roleName);
    if (!adminTargetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    seal.replyToSender(ctx, msg, formatInventory(`${adminPlatform}:${getPrimaryUid(adminPlatform, adminTargetUid)}`, roleName, getRegistry()));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看背包"] = cmd_admin_bag;

let cmd_usage_log = seal.ext.newCmdItemInfo();
cmd_usage_log.name = "物品使用记录";
cmd_usage_log.help = "【管理员】查看今日物品使用记录\n物品使用记录 [N] —— 默认20条";
cmd_usage_log.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const n = parseInt(cmdArgs.getArgN(1)) || 20;
    const log = JSON.parse(mainStorGet("item_usage_log") || "[]");
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
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
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
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const fromRoleKey = `${platform}:${uid}`; // 赠送者Key
    
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);
    const count = parseInt(cmdArgs.getArgN(3)) || 1;

    // 1. 基础校验
    if (isNaN(count) || count <= 0) return seal.replyToSender(ctx, msg, "❌ 赠送数量必须是正整数。");
    if (!targetName || !inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    if (targetName === roleName) return seal.replyToSender(ctx, msg, "⚠️ 不能赠送给自己。");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 2. 目标校验（新结构：通过 roleName 反查 uid）
    const toTargetUid = getRoleUid(platform, targetName);
    if (!toTargetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
    const toRoleKey = `${platform}:${getPrimaryUid(platform, toTargetUid)}`; // 接收者Key

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
cmd_use.help = "使用背包中的普通物品\n使用 物品码或名称\n示例：使用 ITEM_001\n特殊道具（SPEC类）请使用「特殊使用」指令";

cmd_use.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
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

    // 2. 特殊道具须使用专属指令
    if (item.type === "preset") {
        return seal.replyToSender(ctx, msg, `⚙️ [${item.code}]${item.name} 是特殊道具，请使用「特殊使用 ${item.name} [参数]」`);
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
                userItem.remainingUses = item.maxUses ?? -1;
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
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
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
    const cancelSellerUid = getRoleUid(platform, listing.sellerRole);
    const cancelSellerPrimaryUid = cancelSellerUid ? getPrimaryUid(platform, cancelSellerUid) : listing.sellerRole;
    const cancelRoleKey = `${platform}:${cancelSellerPrimaryUid}`;
    // 还原挂单时记录的剩余次数，而不是用 addToInv 重置为初始次数
    const cancelInv = getInv(cancelRoleKey);
    const cancelRemaining = listing.remainingUses ?? (getRegistry()[listing.code]?.maxUses ?? -1);
    const existingEntry = cancelInv.find(e => e.code === listing.code && (e.remainingUses ?? -1) === cancelRemaining);
    if (existingEntry) {
        existingEntry.count += listing.count;
    } else {
        cancelInv.push({ code: listing.code, count: listing.count, remainingUses: cancelRemaining });
    }
    saveInv(cancelRoleKey, cancelInv);
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
        const buyerRawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
        const buyerUid = getPrimaryUid(platform, buyerRawUid);
        const buyerRoleKey = `${platform}:${buyerUid}`;
        const sellerUid = getRoleUid(platform, listing.sellerRole);
        const sellerPrimaryUid = sellerUid ? getPrimaryUid(platform, sellerUid) : listing.sellerRole;
        const sellerRoleKey = `${platform}:${sellerPrimaryUid}`;

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
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    if (!isUserFeatureEnabled(uid, "enable_item_draw")) {
        return seal.replyToSender(ctx, msg, "❌ 你的抽取功能已被管理员关闭。");
    }
    const roleKey = `${platform}:${uid}`;
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
    let tierLabel = null;
    let isPity = false;
    if (pool.type === "fixed") {
        drawnCode = drawFromFixed(pool, reg);
    } else if (pool.type === "pity") {
        const threshold = pool.pityThreshold || 10;
        const pityItems = (pool.pityItems || []).filter(i => reg[i.code]);
        const currentCount = getPityCount(uid, pool.name);
        if (currentCount + 1 >= threshold && pityItems.length > 0) {
            drawnCode = drawFromFixed({ items: pityItems }, reg);
            isPity = true;
            setPityCount(uid, pool.name, 0);
        } else {
            const normalItems = (pool.items || []).filter(i => reg[i.code]);
            if (normalItems.length > 0) {
                drawnCode = drawFromFixed(pool, reg);
            } else if (pityItems.length > 0) {
                drawnCode = drawFromFixed({ items: pityItems }, reg);
                isPity = true;
                setPityCount(uid, pool.name, 0);
            }
            // 只有实际抽到了物品才递增计数器，避免空池时虚增保底进度
            if (!isPity && drawnCode) setPityCount(uid, pool.name, currentCount + 1);
        }
    } else if (pool.type === "tiered") {
        const allAttrs = getCharAttrs();
        const attrVal = Number((allAttrs[uid] || {})[pool.attr] ?? 0);
        const tier = (pool.tiers || []).find(t => {
            const lo = t.min !== null && t.min !== undefined ? Number(t.min) : -Infinity;
            const hi = t.max !== null && t.max !== undefined ? Number(t.max) : Infinity;
            return attrVal >= lo && attrVal < hi;
        });
        if (!tier) return seal.replyToSender(ctx, msg, `⚠️ 你的「${pool.attr}」（${attrVal}）不在任何分段范围内，无法抽取。`);
        tierLabel = tier.label || null;
        if (tier.type === "fixed") {
            drawnCode = drawFromFixed(tier, reg);
        } else {
            drawnCode = drawFromTierFree(tier);
            if (drawnCode) savePoolDefs(defs);
        }
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
    const tierNote = tierLabel ? ` [${tierLabel}]` : "";
    const pityNote = pool.type === "pity"
        ? (isPity ? "\n🌟 保底触发！" : `\n（保底进度：${getPityCount(uid, pool.name)}/${pool.pityThreshold || 10}）`)
        : "";
    seal.replyToSender(ctx, msg, `🎲 【${roleName}】从「${poolName}」${tierNote}抽到：[${drawnCode}]${item.name}\n描述：${item.desc}\n（今日总抽取：${totalUsed}/${totalBase}）${pityNote}`);
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

// ========================
// 保底池专属指令
// ========================

let cmd_set_pity = seal.ext.newCmdItemInfo();
cmd_set_pity.name = "设置保底";
cmd_set_pity.help = "【管理员】设置保底池触发阈值\n设置保底 池子名 N  —— 抽取N次后必出保底物品\n设置保底 池子名    —— 查看当前阈值";
cmd_set_pity.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    if (pool.type !== "pity") return seal.replyToSender(ctx, msg, `❌ 「${poolName}」不是保底池（当前类型：${pool.type === "fixed" ? "权重池" : "数量池"}）。`);
    const nRaw = cmdArgs.getArgN(2);
    if (!nRaw) {
        return seal.replyToSender(ctx, msg, `📊 「${poolName}」保底阈值：${pool.pityThreshold || 10}次\n保底物品：${(pool.pityItems || []).length}种`);
    }
    const n = parseInt(nRaw);
    if (isNaN(n) || n < 1) return seal.replyToSender(ctx, msg, "❌ 阈值必须为正整数。");
    pool.pityThreshold = n;
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `✅ 「${poolName}」保底阈值已设为 ${n} 次。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置保底"] = cmd_set_pity;

let cmd_add_pity_item = seal.ext.newCmdItemInfo();
cmd_add_pity_item.name = "上架保底";
cmd_add_pity_item.help = `【管理员】向保底池添加保底物品（权重抽取）
上架保底 池子名 物品码*权重
多行批量：
。上架保底 池子名
物品码*权重
物品码2*权重2`;
cmd_add_pity_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    if (pool.type !== "pity") return seal.replyToSender(ctx, msg, `❌ 「${poolName}」不是保底池。`);
    if (!pool.pityItems) pool.pityItems = [];
    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);
    const itemLines = msgParts.length > 1
        ? msgParts.slice(1).filter(l => l.trim())
        : (cmdArgs.getArgN(2) ? [cmdArgs.getArgN(2)] : []);
    if (!itemLines.length) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const results = [];
    for (const line of itemLines) {
        const parts = line.trim().split(/[*＊]/);
        const inputCode = (parts[0] || "").trim();
        const num = parseInt((parts[1] || "1").trim());
        const item = findItem(reg, inputCode);
        if (!item) { results.push(`❌ 未知物品「${inputCode}」`); continue; }
        if (isNaN(num) || num <= 0 || num > 999) { results.push(`❌ 权重无效（1~999）: ${parts[1]}`); continue; }
        const existing = pool.pityItems.find(i => i.code === item.code);
        if (existing) { existing.weight = num; results.push(`🔄 [${item.code}]${item.name} 保底权重更新为 ${num}`); }
        else { pool.pityItems.push({ code: item.code, weight: num }); results.push(`✅ [${item.code}]${item.name} 保底权重 ${num}`); }
    }
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `「${poolName}」保底物品上架：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上架保底"] = cmd_add_pity_item;

let cmd_remove_pity_item = seal.ext.newCmdItemInfo();
cmd_remove_pity_item.name = "从保底移除";
cmd_remove_pity_item.help = `【管理员】从保底池的保底物品列表中移除物品
从保底移除 池子名 物品码   —— 移除单个
多行批量：
。从保底移除 池子名
物品码1
物品码2`;
cmd_remove_pity_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const poolName = cmdArgs.getArgN(1);
    if (!poolName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const defs = getPoolDefs();
    const pool = defs[poolName];
    if (!pool) return seal.replyToSender(ctx, msg, `❌ 未找到池子「${poolName}」。`);
    if (pool.type !== "pity") return seal.replyToSender(ctx, msg, `❌ 「${poolName}」不是保底池。`);
    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);
    let inputCodes;
    if (msgParts.length > 1) {
        inputCodes = msgParts.slice(1).map(l => l.trim()).filter(l => l);
    } else {
        const single = cmdArgs.getArgN(2);
        if (!single) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
        inputCodes = [single];
    }
    const reg = getRegistry();
    const results = [];
    for (const inputCode of inputCodes) {
        const item = findItem(reg, inputCode);
        const code = item ? item.code : inputCode.toUpperCase();
        const idx = (pool.pityItems || []).findIndex(i => i.code === code);
        if (idx === -1) { results.push(`❌ [${code}] 不在保底列表中`); continue; }
        pool.pityItems.splice(idx, 1);
        results.push(`✅ 已移除 [${code}]${item?.name || ""}`);
    }
    savePoolDefs(defs);
    seal.replyToSender(ctx, msg, `从「${poolName}」保底列表移除：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["从保底移除"] = cmd_remove_pity_item;

let cmd_my_pity = seal.ext.newCmdItemInfo();
cmd_my_pity.name = "我的保底";
cmd_my_pity.help = "查看自己在各保底池的当前累计次数";
cmd_my_pity.solve = (ctx, msg) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(/^[a-z]+:/i, ""));
    const defs = getPoolDefs();
    const pityPools = Object.values(defs).filter(p => p.type === "pity" && p.enabled);
    if (!pityPools.length) return seal.replyToSender(ctx, msg, "当前没有开放的保底池。");
    let text = `🌟 【${roleName}】保底进度：`;
    for (const pool of pityPools) {
        const count = getPityCount(uid, pool.name);
        const threshold = pool.pityThreshold || 10;
        text += `\n  · ${pool.name}：${count}/${threshold}`;
    }
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的保底"] = cmd_my_pity;
ext.cmdMap["保底进度"] = cmd_my_pity;

let cmd_bag = seal.ext.newCmdItemInfo();
cmd_bag.name = "我的背包";
cmd_bag.help = `查看自己的背包
。背包                     查看背包全览
。背包 货币/道具/物品      按分类查看
。背包 [分类] [页码]      翻页查看（如：。背包 道具 2）
。背包 搜 [关键词]        搜索物品`;
cmd_bag.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    const arg1 = cmdArgs.getArgN(1) || "全部";
    const arg2 = cmdArgs.getArgN(2) || "1";
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
    pruneExpiredItems(roleKey);
    const reg = getRegistry();

    if (arg1 === "搜" || arg1 === "搜索") {
        const keyword = arg2;
        if (!keyword) return seal.replyToSender(ctx, msg, "❌ 请输入搜索关键词\n使用: 。背包 搜 关键词");

        const inv = getInv(roleKey).filter(e => e.count > 0);
        const results = inv.filter(entry => {
            const info = reg[entry.code] || { name: entry.code };
            const name = info.name || "";
            const desc = info.desc || "";
            return name.includes(keyword) || desc.includes(keyword);
        });

        if (!results.length) return seal.replyToSender(ctx, msg, `🔍 未找到「${keyword}」`);

        const lines = [`搜索「${keyword}」(${results.length})`];
        for (const entry of results.slice(0, 8)) {
            const info = reg[entry.code] || { name: entry.code, type: "item" };
            lines.push(formatItemEntry(entry, info));
        }
        if (results.length > 8) lines.push(`...还有${results.length - 8}项`);
        seal.replyToSender(ctx, msg, lines.join("\n"));
        return seal.ext.newCmdExecuteResult(true);
    }

    const validCategories = ["全部", "货币", "道具", "物品"];
    const category = validCategories.includes(arg1) ? arg1 : "全部";
    const page = Math.max(1, parseInt(arg2) || 1);

    seal.replyToSender(ctx, msg, formatInventory(roleKey, roleName, reg, category, page));
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

let cmd_craft = seal.ext.newCmdItemInfo();
cmd_craft.name = "合成";
cmd_craft.help = "消耗材料合成物品\n合成 产物代码 [数量]\n示例：合成 ITEM_001\n合成 ITEM_001 3\n用「查看合成」查看所有配方";
cmd_craft.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    const outputInput = cmdArgs.getArgN(1);
    const count = parseInt(cmdArgs.getArgN(2)) || 1;
    if (!outputInput) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const reg = getRegistry();
    const targetItem = findItem(reg, outputInput);
    const outputCode = targetItem ? targetItem.code : outputInput.toUpperCase();

    const recipes = getCraftRecipes();
    const recipe = recipes[outputCode];
    if (!recipe) return seal.replyToSender(ctx, msg, `❌ 没有关于「${outputInput}」的合成配方。用「查看合成」查看所有配方。`);

    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
    const inv = getInv(roleKey);
    const charAttrs = getCharAttrs();
    const roleAttrs = charAttrs[uid] || {};

    // 检查限制条件
    const limits = recipe.limits || {};
    const unmet = [];
    for (const [attr, minVal] of Object.entries(limits.attrs || {})) {
        const have = roleAttrs[attr] || 0;
        if (have < minVal) unmet.push(`${attr} 需≥${minVal}（当前${have}）`);
    }
    for (const [currencyName, minVal] of Object.entries(limits.currencies || {})) {
        const currencyCode = Object.entries(reg).find(([_, info]) => info.type === "currency" && info.name === currencyName)?.[0];
        if (!currencyCode) {
            unmet.push(`${currencyName}（配方中的货币不存在，请联系管理员）`);
        } else {
            const have = getInvCount(roleKey, currencyCode);
            if (have < minVal) unmet.push(`${currencyName} 需≥${minVal}（当前${have}）`);
        }
    }
    if (unmet.length) return seal.replyToSender(ctx, msg, `❌ 不满足合成条件：\n${unmet.join("\n")}`);

    // 检查材料是否足够
    const lacking = [];
    for (const [matCode, matCount] of Object.entries(recipe.materials)) {
        const needed = matCount * count;
        const have = getInvCount(roleKey, matCode);
        if (have < needed) lacking.push(`${reg[matCode]?.name || matCode} (需${needed}，只有${have})`);
    }
    if (lacking.length) return seal.replyToSender(ctx, msg, `❌ 材料不足：\n${lacking.join("\n")}`);

    // 扣除材料
    for (const [matCode, matCount] of Object.entries(recipe.materials)) {
        removeFromInv(roleKey, matCode, matCount * count);
    }

    // 成功率
    const successRate = recipe.successRate ?? 100;
    let successCount = 0;
    for (let i = 0; i < count; i++) {
        if (Math.random() * 100 < successRate) successCount++;
    }

    if (successCount > 0) addToInv(roleKey, outputCode, successCount);

    const matStr = Object.entries(recipe.materials)
        .map(([c, cnt]) => `${reg[c]?.name || c}×${cnt * count}`)
        .join(" + ");
    const outputName = reg[outputCode]?.name || outputCode;

    if (successCount === count) {
        seal.replyToSender(ctx, msg, `✨ 合成成功！\n消耗：${matStr}\n获得：${outputName}×${count}`);
    } else if (successCount === 0) {
        seal.replyToSender(ctx, msg, `❌ 合成失败！消耗了材料，但未能制作出「${outputName}」。`);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ 合成部分成功（${successCount}/${count}）！\n消耗：${matStr}\n获得：${outputName}×${successCount}`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["合成"] = cmd_craft;

let cmd_upload_interact = seal.ext.newCmdItemInfo();
cmd_upload_interact.name = "上载互动物品";
cmd_upload_interact.help = "【管理员】注册互动类物品（对他人使用）\n格式：名称*描述*次数*属性效果*允许二手\n次数：-1为无限，正数为次数\n效果：属性+10,属性-5（仅限已注册属性或货币，多个逗号隔开，可为空）\n允许二手：Y/N，默认N\n支持多行批量上载";
cmd_upload_interact.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);

    const firstLineRest = msgParts[0].replace(/^[。.]\s*上载互动物品\s*/, "").trim();
    const extraLines = msgParts.slice(1).map(l => l.trim()).filter(l => l);
    const itemLines = [...(firstLineRest ? [firstLineRest] : []), ...extraLines];

    if (!itemLines.length) {
        const validAttrs = getValidAttrs();
        const attrList = validAttrs.length ? validAttrs.join("、") : "（暂无，请先注册属性）";
        return seal.replyToSender(ctx, msg, `🎭 上载互动物品格式：\n名称*描述*次数*属性效果*允许二手\n\n· 次数：-1 为无限，正数为使用次数\n· 效果：属性+数字,属性-数字（可为空）\n· 允许二手：Y 或 N（默认 N）\n· 支持多行批量，每行一条\n\n当前可用属性：${attrList}`);
    }

    const reg = getRegistry();
    const defs = getAttrDefs();
    const currencyNames = new Set(Object.values(reg).filter(i => i.type === "currency").map(i => i.name));
    const results = [];

    for (const line of itemLines) {
        const parts = line.split(/[*＊]/);
        if (parts.length < 3) {
            results.push(`❌ 格式错误：「${line.substring(0, 15)}」需至少包含 名称*描述*次数`);
            continue;
        }

        const name = (parts[0] || "").trim();
        const desc = (parts[1] || "").trim() || "暂无描述";
        const maxUses = parseInt((parts[2] || "").trim());
        const attrsRaw = (parts[3] || "").trim();
        const canResell = ((parts[4] || "").trim().toUpperCase() === "Y");

        if (!name) { results.push(`❌ 名称不能为空`); continue; }
        if (isNaN(maxUses)) { results.push(`❌ 「${name}」次数必须是数字`); continue; }

        // 效果格式校验
        let attrsStr = null;
        if (attrsRaw) {
            const segments = attrsRaw.split(/[,，]/);
            let attrErr = null;
            for (const seg of segments) {
                const m = seg.trim().match(/^(.+?)([+-]\d+)$/);
                if (!m) { attrErr = `效果格式错误「${seg.trim()}」，需为：属性+数字 或 属性-数字`; break; }
                const attrName = m[1];
                if (!defs[attrName] && !currencyNames.has(attrName)) {
                    attrErr = `未知属性「${attrName}」，请先注册属性`; break;
                }
            }
            if (attrErr) { results.push(`❌ 「${name}」${attrErr}`); continue; }
            attrsStr = attrsRaw;
        }

        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) { results.push(`⚠️ 「${name}」已存在 [${existing.code}]，跳过`); continue; }

        const code = genInteractionCode(reg);
        if (!code) { results.push("❌ 代码空间已满，无法继续注册"); break; }

        reg[code] = { code, name, desc, type: "interact", maxUses, attrs: attrsStr, price: 0, canResell };

        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        const resellText = canResell ? "可二手" : "不可二手";
        results.push(`✅ [${code}] ${name} | ${useText} | 效果:${attrsStr || "无"} | ${resellText}`);
    }

    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `🎭 互动物品注册结果（共${results.length}条）：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上载互动物品"] = cmd_upload_interact;

let cmd_delete_item = seal.ext.newCmdItemInfo();
cmd_delete_item.name = "删除物品";
cmd_delete_item.help = "【管理员】彻底删除物品定义，自动清出所有背包/商城/池子/配方/二手市场\n删除物品 物品码或名称";
cmd_delete_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const input = cmdArgs.getArgN(1);
    if (!input) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const reg = getRegistry();
    const item = findItem(reg, input);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未找到物品「${input}」。`);
    const code = item.code;
    const name = item.name;
    const log = [];

    // 1. 清出所有背包
    const invAll = getInvAll();
    let bagCount = 0;
    for (const roleKey of Object.keys(invAll)) {
        const inv = invAll[roleKey];
        const before = inv.reduce((s, e) => e.code === code ? s + e.count : s, 0);
        if (before > 0) {
            invAll[roleKey] = inv.filter(e => e.code !== code);
            bagCount += before;
        }
    }
    saveInvAll(invAll);
    if (bagCount > 0) log.push(`🎒 背包：清出 ×${bagCount}`);

    // 2. 商城下架
    const shop = getShop();
    const shopBefore = shop.length;
    const shopAfter = shop.filter(l => l.code !== code);
    if (shopAfter.length < shopBefore) {
        saveShop(shopAfter);
        log.push(`🏪 商城：移除 ${shopBefore - shopAfter.length} 条上架`);
    }

    // 3. 从所有池子移除
    const defs = getPoolDefs();
    let poolLog = [];
    for (const poolName of Object.keys(defs)) {
        const pool = defs[poolName];
        if (!pool.items) continue;
        const before = pool.items.length;
        pool.items = pool.items.filter(i => i.code !== code);
        if (pool.items.length < before) poolLog.push(poolName);
    }
    if (poolLog.length > 0) {
        savePoolDefs(defs);
        log.push(`🎰 池子：从「${poolLog.join("、")}」移除`);
    }

    // 4. 从 craft_recipes 移除
    const main = getMainExt();
    const craftRecipes = getCraftRecipes();
    let recipeLog = [];
    if (craftRecipes[code]) {
        delete craftRecipes[code];
        recipeLog.push("合成配方（产物）");
    }
    for (const targetCode of Object.keys(craftRecipes)) {
        const recipe = craftRecipes[targetCode];
        if (recipe.materials && recipe.materials[code]) {
            delete recipe.materials[code];
            recipeLog.push(`「${reg[targetCode]?.name || targetCode}」合成配方的材料`);
        }
    }
    saveCraftRecipes(craftRecipes);
    if (recipeLog.length > 0) log.push(`📋 配方：移除 ${recipeLog.join("、")}`);

    // 6. 二手市场撤单
    const market = getMarket();
    let marketCount = 0;
    for (const shCode of Object.keys(market)) {
        if (market[shCode].code === code) {
            delete market[shCode];
            marketCount++;
        }
    }
    if (marketCount > 0) {
        saveMarket(market);
        log.push(`🔄 二手市场：撤销 ${marketCount} 条挂单`);
    }

    // 7. 删除物品定义
    delete reg[code];
    saveRegistry(reg);
    log.push(`🗑️ 物品定义 [${code}]${name} 已删除`);

    seal.replyToSender(ctx, msg, `✅ 删除完成：\n${log.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除物品"] = cmd_delete_item;

function isApplyTimeValid(main) {
    const hoursStr = mainStorGet("apply_item_hours");
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
cmd_apply.help = "对他人使用互动道具（INTER类）\n格式：施加 目标姓名 物品名/代码\n示例：施加 张三 治疗术\n\n特殊道具（SPEC类）请使用「特殊使用」指令\n\n【管理设置】\n施加 设置  或  施加 查看  查看施加系统设置";
cmd_apply.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    const targetName = cmdArgs.getArgN(1);
    const inputCode = cmdArgs.getArgN(2);

    // 显示施加设置
    if (!targetName || targetName === "设置" || targetName === "查看") {
        const applyNotify = mainStorGet("apply_item_notification") !== "false";
        const exposeRate = getMainStorageInt("apply_item_expose_rate", 0);
        const applyHours = mainStorGet("apply_item_hours") || "不限";

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
        const hoursStr = mainStorGet("apply_item_hours");
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
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
    const reg = getRegistry();
    const item = findItem(reg, inputCode);

    // 1. 基础校验
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${inputCode}」`);

    // 特殊道具须使用专属指令
    if (item.type === "preset") {
        return seal.replyToSender(ctx, msg, `⚙️ [${item.code}]${item.name} 是特殊道具，请使用「特殊使用 ${item.name} [参数]」`);
    }

    if (item.type !== "interact") return seal.replyToSender(ctx, msg, `⚠️ [${item.name}] 不是互动类物品，请使用「使用」指令。`);

    // 2. 检查目标是否存在
    const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
    const targetUid = getRoleUid(platform, targetName);
    if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);

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
    if (userItem.remainingUses === undefined) {
        userItem.remainingUses = item.maxUses ?? -1;
    }
    if (userItem.remainingUses !== -1) {
        userItem.remainingUses--;
        if (userItem.remainingUses <= 0) {
            userItem.count--;
            if (userItem.count <= 0) {
                inv.splice(invIndex, 1);
                usageStatus = "(已耗尽)";
            } else {
                userItem.remainingUses = item.maxUses ?? -1;
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
    const shouldNotify = mainStorGet("apply_item_notification") !== "false";
    const exposeRate = getMainStorageInt("apply_item_expose_rate", 0);
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
    seal.replyToSender(ctx, msg, feedback);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["施加"] = cmd_apply;

// ========================
// 特殊道具使用
// ========================

let cmd_special_use = seal.ext.newCmdItemInfo();
cmd_special_use.name = "特殊使用";
cmd_special_use.help = `使用特殊道具（SPEC类）
追踪器：特殊使用 追踪器 目标角色 [时间]
万能钥匙：特殊使用 万能钥匙 地点名
望远镜：特殊使用 望远镜 目标角色
羽毛笔：特殊使用 羽毛笔 目标角色
捕鼠器：特殊使用 捕鼠器 目标角色 时间（整点，如 14）
窃听器：特殊使用 窃听器 目标角色 [条数=10] [干扰率=30]
截信器：特殊使用 截信器 目标角色 [条数=10] [干扰率=30]
回音壁：特殊使用 回音壁 目标角色 [条数=10] [干扰率=30]`;

cmd_special_use.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    const inputCode = cmdArgs.getArgN(1);
    if (!inputCode) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;
    const reg = getRegistry();
    const item = findItem(reg, inputCode);

    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知道具「${inputCode}」`);
    if (!item.code.startsWith("SPEC_")) return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不是特殊道具。`);
    if ((item.code === "SPEC_003" || item.code === "SPEC_004") && !seal.ext.find("letter_system")) {
        return seal.replyToSender(ctx, msg, "❌ 此道具需要写信综插件开启才能使用。");
    }

    const inv = getInv(roleKey);
    if (!inv.find(e => e.code === item.code && e.count > 0)) {
        return seal.replyToSender(ctx, msg, `❌ 背包中没有可用的「${item.name}」。`);
    }

    // ── SPEC_001 追踪器 ──
    if (item.code === "SPEC_001") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, "🔍 请指定要追踪的角色：特殊使用 追踪器 角色名 [时间]");
        // 新结构：通过 roleName 反查 uid
        const trackerTargetUid = getRoleUid(platform, targetName);
        if (!trackerTargetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);

        const globalDay = mainStorGet("global_days");
        if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 未设置游戏天数。");

        const timeRestrict = mainStorGet("item_tracker_time_restrict") !== "false";
        let timeRange;
        if (timeRestrict) {
            const h = new Date().getHours();
            timeRange = `${h.toString().padStart(2,'0')}:00-${h === 23 ? "23:59" : (h+1).toString().padStart(2,'0')+":00"}`;
        } else {
            const timeArg = cmdArgs.getArgN(3);
            if (!timeArg) return seal.replyToSender(ctx, msg, "🔍 请指定追踪时间：特殊使用 追踪器 角色名 时间（如 14 或 14:30）");
            let hour, minute = 0;
            if (/^\d{1,2}$/.test(timeArg)) { hour = parseInt(timeArg); }
            else if (/^\d{1,2}:\d{2}$/.test(timeArg)) {
                [hour, minute] = timeArg.split(':').map(Number);
                if (minute < 0 || minute > 59) return seal.replyToSender(ctx, msg, "⚠️ 分钟应在00-59之间");
            } else return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用：14 或 14:30");
            if (hour < 0 || hour > 23) return seal.replyToSender(ctx, msg, "⚠️ 小时应在0-23之间");
            const start = `${hour.toString().padStart(2,'0')}:${minute.toString().padStart(2,'0')}`;
            let endH = hour + 1, endM = minute;
            if (endH >= 24) { endH = 23; endM = 59; }
            timeRange = `${start}-${endH.toString().padStart(2,'0')}:${endM.toString().padStart(2,'0')}`;
        }

        const b_confirmedSchedule = JSON.parse(mainStorGet("b_confirmedSchedule") || "{}");
        const targetKey = `${platform}:${getPrimaryUid(platform, trackerTargetUid)}`;
        const matchingEvent = (b_confirmedSchedule[targetKey] || []).find(ev => ev.day === globalDay && timeOverlap(ev.time, timeRange));
        const successRate = getMainStorageInt("item_tracker_success_rate", 70);
        const showPartner = mainStorGet("item_tracker_show_partner") !== "false";
        const isSuccess = Math.random() * 100 < successRate;

        if (!removeFromInv(roleKey, "SPEC_001", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的追踪器。");
        if (!matchingEvent) return seal.replyToSender(ctx, msg, `🔍 未能发现「${targetName}」的行踪。\n（追踪器已消耗）`);
        if (!isSuccess) return seal.replyToSender(ctx, msg, `🔍 信号干扰，定位失败。\n（追踪器已消耗）`);

        let resultMsg = `🔍 追踪到「${targetName}」在 ${globalDay} ${matchingEvent.time} 出现在「${matchingEvent.place || "某处"}」`;
        if (showPartner && matchingEvent.partner && matchingEvent.partner !== "独自一人") resultMsg += `，与 ${matchingEvent.partner} 一起`;
        resultMsg += `。\n（追踪器已消耗）`;
        return seal.replyToSender(ctx, msg, resultMsg);
    }

    // ── SPEC_002 万能钥匙 ──
    if (item.code === "SPEC_002") {
        const placeName = cmdArgs.args.slice(1).join(' ').trim();
        if (!placeName) return seal.replyToSender(ctx, msg, "🔑 请指定要兑换钥匙的地点：特殊使用 万能钥匙 地点名");
        const availablePlaces = JSON.parse(mainStorGet("available_places") || "{}");
        if (!availablePlaces[placeName]) {
            const placeList = Object.keys(availablePlaces).join("、") || "（暂无）";
            return seal.replyToSender(ctx, msg, `❌ 未找到地点「${placeName}」。\n📍 可用地点：${placeList}`);
        }
        let placeKeys = JSON.parse(mainStorGet("place_keys") || "{}");
        if (!placeKeys[platform]) placeKeys[platform] = {};
        if (!placeKeys[platform][roleName]) placeKeys[platform][roleName] = [];
        if (placeKeys[platform][roleName].includes(placeName))
            return seal.replyToSender(ctx, msg, `🔑 你已经拥有「${placeName}」的钥匙了。`);
        if (!removeFromInv(roleKey, "SPEC_002", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的万能钥匙。");
        placeKeys[platform][roleName].push(placeName);
        mainStorSet("place_keys", JSON.stringify(placeKeys));
        return seal.replyToSender(ctx, msg, `🔑 成功兑换「${placeName}」的钥匙！（万能钥匙已消耗）`);
    }

    // ── SPEC_003 望远镜 / SPEC_004 羽毛笔 ──
    if (item.code === "SPEC_003" || item.code === "SPEC_004") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, `✉️ 请指定目标：特殊使用 ${item.name} 角色名`);
        const featureToggle = JSON.parse(mainStorGet("global_feature_toggle") || "{}");
        if (!featureToggle.enable_direct_letter) return seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。");
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        if (!Object.values(apg[platform] || {}).some(v => v[0] === targetName)) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);
        if (!removeFromInv(roleKey, item.code, 1)) return seal.replyToSender(ctx, msg, `❌ 背包中没有可用的「${item.name}」。`);
        const effectsKey = item.code === "SPEC_003" ? "letter_telescope_effects" : "letter_quill_pen_effects";
        const effects = JSON.parse(mainStorGet(effectsKey) || "{}");
        if (!effects[targetName]) effects[targetName] = [];
        effects[targetName].push({ applier: roleName, applyTime: Date.now(), itemCode: item.code });
        mainStorSet(effectsKey, JSON.stringify(effects));
        return seal.replyToSender(ctx, msg, `✅ 你已向「${targetName}」施加了「${item.name}」！`);
    }

    // ── SPEC_005 捕鼠器 ──
    if (item.code === "SPEC_005") {
        const targetName = cmdArgs.getArgN(2);
        const timeArg = cmdArgs.getArgN(3);
        if (!targetName) return seal.replyToSender(ctx, msg, "🪤 请指定目标：特殊使用 捕鼠器 角色名 时间（如 14）");
        if (!timeArg) return seal.replyToSender(ctx, msg, "🪤 请指定锁定时间：特殊使用 捕鼠器 角色名 时间（如 14）");
        if (!/^\d{1,2}$/.test(timeArg)) return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用整点小时，如：14");
        const hour = parseInt(timeArg);
        if (hour < 0 || hour > 23) return seal.replyToSender(ctx, msg, "⚠️ 小时应在0-23之间");
        const endH = hour === 23 ? 23 : hour + 1;
        const endM = hour === 23 ? 59 : 0;
        const timeRange = `${hour.toString().padStart(2,'0')}:00-${endH.toString().padStart(2,'0')}:${endM.toString().padStart(2,'0')}`;

        const globalDay = mainStorGet("global_days");
        if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 未设置游戏天数。");

        // 新结构：通过 roleName 反查 uid
        const trapTargetUid = getRoleUid(platform, targetName);
        if (!trapTargetUid) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);
        const targetKey = `${platform}:${getPrimaryUid(platform, trapTargetUid)}`;

        if (!removeFromInv(roleKey, "SPEC_005", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的捕鼠器。");

        let a_lockedSlots = JSON.parse(mainStorGet("a_lockedSlots") || "{}");
        if (!a_lockedSlots[targetKey]) a_lockedSlots[targetKey] = {};
        if (!a_lockedSlots[targetKey][globalDay]) a_lockedSlots[targetKey][globalDay] = [];
        if (!a_lockedSlots[targetKey][globalDay].includes(timeRange)) {
            a_lockedSlots[targetKey][globalDay].push(timeRange);
        }
        mainStorSet("a_lockedSlots", JSON.stringify(a_lockedSlots));

        notifyPlayer(ctx, platform, targetName, `🪤 你在 ${globalDay} ${timeRange} 踩中了捕鼠器，该时段内无法发起或接受私约、电话，也无法摘心愿。`);
        return seal.replyToSender(ctx, msg, `🪤 捕鼠器已激活！「${targetName}」在 ${globalDay} ${timeRange} 的行动被锁定。\n（捕鼠器已消耗）`);
    }

    // ── SPEC_006 窃听器 ──
    if (item.code === "SPEC_006") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, "📡 请指定目标：特殊使用 窃听器 角色名 [条数=10] [干扰率=30]");
        const countRaw = parseInt(cmdArgs.getArgN(3));
        const blurRaw = parseInt(cmdArgs.getArgN(4));
        const remainCount = isNaN(countRaw) || countRaw <= 0 ? 10 : countRaw;
        const blurProb = isNaN(blurRaw) ? 30 : Math.max(0, Math.min(100, blurRaw));

        const targetUid = getRoleUid(platform, targetName);
        if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
        if (!removeFromInv(roleKey, "SPEC_006", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的窃听器。");

        const phoneTaps = JSON.parse(mainStorGet("phone_tap_effects") || "{}");
        phoneTaps[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainStorSet("phone_tap_effects", JSON.stringify(phoneTaps));

        return seal.replyToSender(ctx, msg, `📡 窃听器已部署！\n目标：${targetName}\n最多截听：${remainCount} 条\n干扰率：${blurProb}%\n（窃听器已消耗）`);
    }

    // ── SPEC_007 截信器 ──
    if (item.code === "SPEC_007") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, "📱 请指定目标：特殊使用 截信器 角色名 [条数=10] [干扰率=30]");
        const countRaw = parseInt(cmdArgs.getArgN(3));
        const blurRaw = parseInt(cmdArgs.getArgN(4));
        const remainCount = isNaN(countRaw) || countRaw <= 0 ? 10 : countRaw;
        const blurProb = isNaN(blurRaw) ? 30 : Math.max(0, Math.min(100, blurRaw));

        const targetUid = getRoleUid(platform, targetName);
        if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
        if (!removeFromInv(roleKey, "SPEC_007", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的截信器。");

        const smsTaps = JSON.parse(mainStorGet("sms_tap_effects") || "{}");
        smsTaps[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainStorSet("sms_tap_effects", JSON.stringify(smsTaps));

        return seal.replyToSender(ctx, msg, `📱 截信器已部署！\n目标：${targetName}\n最多截取：${remainCount} 条\n干扰率：${blurProb}%\n（截信器已消耗）`);
    }

    // ── SPEC_008 回音壁 ──
    if (item.code === "SPEC_008") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, "🪞 请指定目标：特殊使用 回音壁 角色名 [条数=10] [干扰率=30]");
        const countRaw = parseInt(cmdArgs.getArgN(3));
        const blurRaw  = parseInt(cmdArgs.getArgN(4));
        const remainCount = isNaN(countRaw) || countRaw <= 0 ? 10 : countRaw;
        const blurProb    = isNaN(blurRaw) ? 30 : Math.max(0, Math.min(100, blurRaw));

        const targetUid = getRoleUid(platform, targetName);
        if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」。`);
        if (!removeFromInv(roleKey, "SPEC_008", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的回音壁。");

        const echoWalls = JSON.parse(mainStorGet("sms_echo_wall_effects") || "{}");
        echoWalls[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainStorSet("sms_echo_wall_effects", JSON.stringify(echoWalls));

        return seal.replyToSender(ctx, msg, `🪞 回音壁已贴附！\n目标：${targetName}\n最多截取：${remainCount} 条\n干扰率：${blurProb}%\n（回音壁已消耗）`);
    }

    return seal.replyToSender(ctx, msg, `❌ 未知的特殊道具 [${item.code}]，请联系管理员。`);
};
ext.cmdMap["特殊使用"] = cmd_special_use;

// ========================
// 合成系统
// ========================

let cmd_reg_craft = seal.ext.newCmdItemInfo();
cmd_reg_craft.name = "注册合成";
cmd_reg_craft.help = "【管理员】注册合成配方\n注册合成 产物代码*描述*材料代码1:数量1,材料代码2:数量2[*限制条件[*成功率]]\n限制格式：attr:属性名:最小值,currency:货币名:最小值\n成功率：0-100，默认100（消耗材料后按此概率获得产物）\n示例：注册合成 高级丹*升级丹药*初级丹:3,金币:100*attr:体力:50*80";
cmd_reg_craft.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const raw = cmdArgs.getArgN(1);
    if (!raw) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const parts = raw.split(/[*＊]/);
    const outputCode = (parts[0] || "").trim();
    const desc = (parts[1] || "").trim();
    const materialsStr = (parts[2] || "").trim();
    const limitsStr = (parts[3] || "").trim();
    const successRateStr = (parts[4] || "").trim();

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

    let successRate = 100;
    if (successRateStr) {
        successRate = parseInt(successRateStr);
        if (isNaN(successRate) || successRate < 0 || successRate > 100)
            return seal.replyToSender(ctx, msg, "❌ 成功率必须是 0-100 之间的整数");
    }

    const recipes = getCraftRecipes();
    recipes[outputCode] = { materials, output: outputCode, desc: desc || "暂无描述", limits, successRate };
    saveCraftRecipes(recipes);

    const matStr = Object.entries(materials).map(([c, cnt]) => `${reg[c].name}×${cnt}`).join(" + ");
    let msg_text = `✅ 合成配方已注册：${matStr} → ${reg[outputCode].name}`;
    if (desc) msg_text += `\n📝 ${desc}`;
    if (successRate < 100) msg_text += `\n🎲 成功率：${successRate}%`;
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

let cmd_del_craft = seal.ext.newCmdItemInfo();
cmd_del_craft.name = "删除合成";
cmd_del_craft.help = "【管理员】删除合成配方（不影响物品本身）\n删除合成 产物代码或名称";
cmd_del_craft.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const input = cmdArgs.getArgN(1);
    if (!input) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const reg = getRegistry();
    const target = findItem(reg, input);
    const code = target ? target.code : input.toUpperCase();
    const recipes = getCraftRecipes();
    if (!recipes[code]) return seal.replyToSender(ctx, msg, `❌ 未找到「${input}」的合成配方。`);
    const name = reg[code]?.name || code;
    delete recipes[code];
    saveCraftRecipes(recipes);
    seal.replyToSender(ctx, msg, `✅ 已删除「${name}」的合成配方。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除合成"] = cmd_del_craft;

// ========================
// 无前缀指令触发
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.message || "").trim();
    const fa = (parts) => ({ getArgN: (n) => parts[n - 1] || "", args: parts });
    const isAdmin = isUserAdmin(ctx, msg);
    const platform = msg.platform;

    // ── RPG 属性 ──

    // 我的状态
    if (raw === "我的状态") {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 未绑定角色");
        const myStatusUid = getPrimaryUid(platform, msg.sender.userId.replace(/^[a-z]+:/i, ""));
        const defs = getAttrDefs();
        const charAttrs = getCharAttrs();
        // 新结构：charAttrs 以 uid 为 key
        const roleAttrs = charAttrs[myStatusUid] || {};
        const attrNames = Object.keys(defs);
        if (!attrNames.length) return seal.replyToSender(ctx, msg, `🎭 【${roleName}】暂无属性，管理员可用「我创建属性」添加。`);

        // 分类属性
        const limitedAttrs = [];
        const unlimitedAttrs = [];
        const BAR = 8;

        attrNames.forEach(name => {
            const def = defs[name];
            const val = roleAttrs[name] ?? (def.default ?? 0);
            if (def.max !== null && def.max !== undefined && def.min !== null) {
                const pct = def.max === def.min ? 1 : (val - def.min) / (def.max - def.min);
                const filled = Math.round(Math.max(0, Math.min(1, pct)) * BAR);
                const bar = "▓".repeat(filled) + "░".repeat(BAR - filled);
                const percent = Math.round(pct * 100);
                limitedAttrs.push(`【${name}】${bar} ${val}/${def.max}`);
            } else {
                const minText = def.min !== null ? ` [最低:${def.min}]` : "";
                unlimitedAttrs.push(`【${name}】${val}${minText}`);
            }
        });

        // 获取货币信息
        const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
        const uid = getPrimaryUid(platform, rawUid);
        const roleKey = `${platform}:${uid}`;
        const inv = getInv(roleKey);
        const registry = getRegistry();
        const currencies = inv.filter(e => {
            const item = registry[e.code];
            return item && item.type === "currency";
        }).sort((a, b) => a.code.localeCompare(b.code));

        let result = `\n★━━━━━━━━━━━━━━━━━━★\n🎭 【${roleName}】的状态\n★━━━━━━━━━━━━━━━━━━★\n`;

        if (limitedAttrs.length > 0) {
            result += `\n📊 核心属性\n`;
            limitedAttrs.forEach(l => {
                result += `${l}\n`;
            });
        }

        if (unlimitedAttrs.length > 0) {
            result += `\n📈 资源属性\n`;
            unlimitedAttrs.forEach(l => {
                result += `${l}\n`;
            });
        }

        if (currencies.length > 0) {
            result += `\n💰 货币\n`;
            currencies.forEach(curr => {
                const currName = registry[curr.code]?.name || curr.code;
                result += `${currName}: ${curr.count}\n`;
            });
        }

        result += `★━━━━━━━━━━━━━━━━━━★`;
        return seal.replyToSender(ctx, msg, result);
    }

    // 我创建属性（管理员，无前缀）换行批量：每行 属性名 [最小 最大 默认]
    if (raw.startsWith("我创建属性") && isAdmin) {
        const body = raw.slice(5).trim();
        if (!body) return seal.replyToSender(ctx, msg, "❌ 请提供属性定义，格式：属性名 最小 最大 默认");
        const lines = body.split(/\n/).map(l => l.trim()).filter(Boolean);
        const reg = getRegistry();
        const currencyNames = new Set(Object.values(reg).filter(r => r.type === "currency").map(r => r.name));
        const defs = getAttrDefs();
        const results = [];
        for (const line of lines) {
            const parts = line.split(/\s+/);
            const name = parts[0];
            if (!name) continue;
            if (currencyNames.has(name)) { results.push(`❌ 「${name}」已被货币占用`); continue; }
            if (parts[1] !== undefined && !isNaN(Number(parts[1]))) {
                const min = Number(parts[1]);
                const max = parts[2] !== undefined && !isNaN(Number(parts[2])) ? Number(parts[2]) : null;
                const def = parts[3] !== undefined && !isNaN(Number(parts[3])) ? Number(parts[3]) : 0;
                const isNew = !defs[name];
                defs[name] = { min, max, default: def, desc: defs[name]?.desc || "" };
                results.push(`${isNew ? "✅ 新增" : "🔄 更新"}「${name}」：${min}~${max ?? "∞"} 默认${def}`);
            } else {
                const isNew = !defs[name];
                if (isNew) defs[name] = { min: null, max: null, default: 0, desc: "" };
                results.push(`${isNew ? "✅ 新增" : "⏭️ 已存在"}「${name}」`);
            }
        }
        saveAttrDefs(defs);
        return seal.replyToSender(ctx, msg, results.join("\n"));
    }
    if (raw.startsWith("我移除属性") && isAdmin) {
        const body = raw.slice(5).trim();
        if (!body) return seal.replyToSender(ctx, msg, "❌ 请指定要移除的属性名。");
        const names = body.split(/\n/).map(l => l.trim()).filter(Boolean);
        const defs = getAttrDefs();
        const charAttrs = getCharAttrs();
        const results = [];
        for (const attrName of names) {
            if (!defs[attrName]) { results.push(`❌ 「${attrName}」不存在`); continue; }
            delete defs[attrName];
            for (const role of Object.keys(charAttrs)) delete charAttrs[role][attrName];
            results.push(`✅ 已移除「${attrName}」`);
        }
        saveAttrDefs(defs);
        saveCharAttrs(charAttrs);
        const remaining = Object.keys(defs);
        results.push(`当前属性：${remaining.length ? remaining.join("、") : "（无）"}`);
        return seal.replyToSender(ctx, msg, results.join("\n"));
    }

    // 角色:属性++值 / 角色:属性--值 / 角色:货币++值（管理员批量改属性或货币）
    if (isAdmin) {
        const attrM = raw.match(/^(.+?)[:：](.+?)([+\-]{2})([\d、,，]+)$/);
        if (attrM) {
            const [, rolesPart, attrName, op, valsPart] = attrM;
            const main = getMainExt();
            if (!main) return;
            const priv = JSON.parse(mainStorGet("a_private_group") || "{}")[platform] || {};
            // 新结构：priv 以 uid 为 key，value[0] 是 roleName
            // roles 统一为 roleName 列表
            const roles = rolesPart === "全体"
                ? Object.values(priv).map(v => v[0]).filter(Boolean)
                : rolesPart.split(/[、,，]/).map(r => r.trim());
            const vals = valsPart.split(/[、,，]/).map(v => parseInt(v));
            const res = [];

            // 检查是属性还是货币
            const defs = getAttrDefs();
            const reg = getRegistry();
            const currencyCode = Object.entries(reg).find(([_, info]) => info.type === "currency" && info.name === attrName)?.[0];

            if (defs[attrName]) {
                // 处理属性
                const charAttrs = getCharAttrs();
                const notifyList = [];
                roles.forEach((r, i) => {
                    // 新结构：通过 roleName 反查 uid
                    const rUidAttr = getRoleUid(platform, r);
                    if (!rUidAttr) return;
                    const rPrimaryUidAttr = getPrimaryUid(platform, rUidAttr);
                    if (!charAttrs[rPrimaryUidAttr]) charAttrs[rPrimaryUidAttr] = {};
                    const v = isNaN(vals[i]) ? vals[0] : vals[i];
                    const old = charAttrs[rPrimaryUidAttr][attrName] ?? (defs[attrName].default ?? 0);
                    const next = clampAttr(defs[attrName], op === "++" ? old + v : old - v);
                    charAttrs[rPrimaryUidAttr][attrName] = next;
                    res.push(`${r}：${old}→${next}`);
                    notifyList.push({ r, old, next });
                });
                if (res.length) {
                    saveCharAttrs(charAttrs);
                    notifyList.forEach(({ r, old, next }) => {
                        notifyPlayer(ctx, platform, r, `${op === "++" ? "📈" : "📉"}【属性变动】你的「${attrName}」：${old} → ${next}`);
                    });
                    return seal.replyToSender(ctx, msg, `${op === "++" ? "📈" : "📉"} ${attrName} 变更：\n${res.join("\n")}`);
                }
            } else if (currencyCode) {
                // 处理货币
                const notifyList = [];
                roles.forEach((r, i) => {
                    // 新结构：通过 roleName 反查 uid
                    const rUid = getRoleUid(platform, r);
                    if (!rUid) return;
                    const roleKey = `${platform}:${getPrimaryUid(platform, rUid)}`;
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
                    notifyList.push({ r, old, next });
                });
                if (res.length) {
                    notifyList.forEach(({ r, old, next }) => {
                        notifyPlayer(ctx, platform, r, `${op === "++" ? "💰" : "💸"}【货币变动】你的「${attrName}」：${old} → ${next}`);
                    });
                    return seal.replyToSender(ctx, msg, `${op === "++" ? "💰" : "💸"} 货币「${attrName}」变更：\n${res.join("\n")}`);
                }
            }
        }
    }

    // ── 合成系统 ──
    if (raw === "合成列表") {
        return cmd_view_craft.solve(ctx, msg, fa([]));
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
    if (raw.startsWith("特殊使用")) {
        const parts = raw.slice(4).trim().split(/\s+/);
        if (parts[0]) return cmd_special_use.solve(ctx, msg, fa(parts));
    }
    if (raw.startsWith("上架二手")) {
        const parts = raw.slice(4).trim().split(/\s+/);
        if (parts.length >= 3) return cmd_sell.solve(ctx, msg, fa(parts));
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

// ========================
// 同步踩点池命令
// ========================

let cmd_sync_spot_pools = seal.ext.newCmdItemInfo();
cmd_sync_spot_pools.name = "同步踩点池";
cmd_sync_spot_pools.help = "【管理员】同步地点系统中的所有地点到抽取池\n同步踩点池\n  将自动为每个地点创建相应的池子（若已存在则跳过）\n  不删除任何已有的池子";
cmd_sync_spot_pools.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 读取地点系统配置（检查是否启用）
    let placeSystemEnabled = true;
    try {
        const placeConfig = JSON.parse(mainStorGet("place_system_config") || "{}");
        placeSystemEnabled = placeConfig.enabled !== false;
    } catch(e) {}

    if (!placeSystemEnabled) {
        return seal.replyToSender(ctx, msg, "⚠️ 地点系统未启用，无法同步踩点池。");
    }

    // 读取所有地点
    let places = {};
    try {
        places = JSON.parse(mainStorGet("available_places") || "{}");
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

// ── 从 RP 存档服务器同步池子 ─────────────────────────────────────────────────
let cmd_sync_pools_from_archive = seal.ext.newCmdItemInfo();
cmd_sync_pools_from_archive.name = "同步池子";
cmd_sync_pools_from_archive.help = "【管理员】从RP存档服务器拉取池子配置（在存档网页编辑后使用）\n同步池子       —— 拉取并覆盖本地池子定义和抽取设定\n同步池子 预览  —— 只显示存档中的池子，不实际同步";
cmd_sync_pools_from_archive.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    const archiveEnabled = seal.ext.getBoolConfig(main, "启用RP存档传输");
    if (!archiveEnabled) return seal.replyToSender(ctx, msg, "❌ 未启用RP存档传输，请先在长日设置中开启。");

    const base  = (seal.ext.getStringConfig(main, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址。");

    const previewOnly = (cmdArgs.getArgN(1) || "") === "预览";
    const headers = {};
    if (token) headers["X-Archive-Token"] = token;

    (async () => {
        try {
            const resp = await fetch(`${base}/api/pool_config`, { headers });
            if (!resp.ok) {
                seal.replyToSender(ctx, msg, `❌ 拉取失败，服务器返回 ${resp.status}。`);
                return;
            }
            const data = await resp.json();
            if (!data.ok) {
                seal.replyToSender(ctx, msg, `❌ 拉取失败：${data.error || "未知错误"}`);
                return;
            }
            const defs = data.pool_definitions || {};
            const cfg  = data.pool_draw_config  || { total: null, pools: {} };
            const poolNames = Object.keys(defs);

            if (previewOnly) {
                if (!poolNames.length) {
                    seal.replyToSender(ctx, msg, "📭 存档中暂无池子配置。");
                    return;
                }
                const totalStr = cfg.total != null ? `${cfg.total}次/天` : "无限";
                let preview = `👁️ 存档池子预览（${poolNames.length}个）| 全局：${totalStr}\n`;
                for (const name of poolNames) {
                    const p = defs[name];
                    const typeStr = p.type === "fixed" ? "权重池" : p.type === "tiered" ? "分段池" : p.type === "pity" ? "保底池" : "数量池";
                    const stock = p.type === "tiered"
                        ? (p.tiers?.length || 0) + "段"
                        : p.type === "free"
                            ? p.items.reduce((s, i) => s + (i.count || 0), 0) + "个"
                            : p.items.length + "种";
                    const perDay = cfg.pools?.[name];
                    const limitStr = perDay != null ? `${perDay}次/天` : "跟随全局";
                    preview += `\n${p.enabled ? "✅" : "❌"} 【${name}】${typeStr} | 库存${stock} | ${limitStr}`;
                }
                preview += "\n\n💡 确认无误后发送「同步池子」正式同步。";
                seal.replyToSender(ctx, msg, preview);
                return;
            }

            mainStorSet("pool_definitions", JSON.stringify(defs));
            mainStorSet("pool_draw_config", JSON.stringify(cfg));
            const totalStr = cfg.total != null ? `${cfg.total}次/天` : "无限";
            seal.replyToSender(ctx, msg, `✅ 池子已同步（${poolNames.length} 个池子，全局次数：${totalStr}）。`);
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 同步失败：${e.message || String(e)}`);
        }
    })();
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步池子"] = cmd_sync_pools_from_archive;

let cmd_push_pools = seal.ext.newCmdItemInfo();
cmd_push_pools.name = "上传池子";
cmd_push_pools.help = "【管理员】将本地池子配置推送到RP存档服务器（覆盖网页端的配置）\n上传池子";
cmd_push_pools.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const archiveEnabled = seal.ext.getBoolConfig(main, "启用RP存档传输");
    if (!archiveEnabled) return seal.replyToSender(ctx, msg, "❌ 未启用RP存档传输，请先在长日设置中开启。");
    const base  = (seal.ext.getStringConfig(main, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址。");
    const defs = getPoolDefs();
    const cfg  = getDrawConfig();
    const poolCount = Object.keys(defs).length;
    const headers = { "Content-Type": "application/json" };
    if (token) headers["X-Archive-Token"] = token;
    (async () => {
        try {
            const resp = await fetch(`${base}/api/pool_config`, {
                method: "POST",
                headers,
                body: JSON.stringify({ pool_definitions: defs, pool_draw_config: cfg })
            });
            if (!resp.ok) {
                seal.replyToSender(ctx, msg, `❌ 上传失败，服务器返回 ${resp.status}。`);
                return;
            }
            const data = await resp.json();
            if (data.ok) {
                seal.replyToSender(ctx, msg, `✅ 已将 ${poolCount} 个池子上传到存档服务器。`);
            } else {
                seal.replyToSender(ctx, msg, `❌ 上传失败：${data.error || "未知错误"}`);
            }
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 上传失败：${e.message || String(e)}`);
        }
    })();
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传池子"] = cmd_push_pools;

// ========================
// 攻防系统 - 存储与配置
// ========================

function getAttackDefenseConfig() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return JSON.parse(mainStorGet("attack_defense_config") || "{}");
    } catch(e) { return {}; }
}

function saveAttackDefenseConfig(config) {
    const main = getMainExt();
    if (main) mainStorSet("attack_defense_config", JSON.stringify(config));
}

function getAttackDefenseData() {
    const main = getMainExt();
    if (!main) return { battles: {}, playerStats: {}, playerSkills: {} };
    try {
        return JSON.parse(mainStorGet("attack_defense_data") || "{}");
    } catch(e) { return { battles: {}, playerStats: {}, playerSkills: {} }; }
}

function saveAttackDefenseData(data) {
    const main = getMainExt();
    if (main) mainStorSet("attack_defense_data", JSON.stringify(data));
}

// 技能定义由 rp_archive 管理端写入 skill_defs，机器人只读
function getSkillDefs() {
    try { return JSON.parse(mainStorGet("skill_defs") || "{}"); } catch(e) { return {}; }
}

// 玩家基础战斗属性（纯底值，不含装备加成）
function initPlayerBattleAttrs() {
    return { ATK: 50, DEF: 30, AGI: 40, HP: 100, MP: 50, MP_REGEN: 5 };
}

function getPlayerBattleAttrs(name) {
    const all = JSON.parse(mainStorGet("battle_attrs") || "{}");
    if (!all[name]) {
        all[name] = initPlayerBattleAttrs();
        mainStorSet("battle_attrs", JSON.stringify(all));
    }
    return all[name];
}

function savePlayerBattleAttrs(name, attrs) {
    const all = JSON.parse(mainStorGet("battle_attrs") || "{}");
    all[name] = attrs;
    mainStorSet("battle_attrs", JSON.stringify(all));
}

function getPlayerSkills() {
    return JSON.parse(mainStorGet("player_skills") || "{}");
}
function savePlayerSkills(skills) {
    mainStorSet("player_skills", JSON.stringify(skills));
}

// ========================
// 攻防系统 - 战斗管理
// ========================

// 短战斗ID，如 B-A3K9，方便玩家手打
function generateBattleId() {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let id = "B-";
    for (let i = 0; i < 4; i++) id += chars[Math.floor(Math.random() * chars.length)];
    return id;
}

// 获取玩家有效属性 = 基础属性 + 装备加成
function getEffectiveBattleAttrs(playerName, roleKey) {
    const base = getPlayerBattleAttrs(playerName);
    const result = {
        ATK: base.ATK || 50, DEF: base.DEF || 30, AGI: base.AGI || 40,
        HP:  base.HP  || 100, MP: base.MP  || 50, MP_REGEN: base.MP_REGEN || 5
    };
    try {
        const equips = getPlayerEquips(roleKey);
        const equipReg = getEquipRegistry();
        if (equips && equipReg) {
            const bonus = getTotalEquipBonus(equips, equipReg);
            for (const attr of ["ATK","DEF","AGI","HP","MP","MP_REGEN"]) {
                if (bonus[attr]) result[attr] = Math.max(0, result[attr] + bonus[attr]);
            }
        }
    } catch(e) {}
    return result;
}

// 初始化并返回玩家 playerState（含装备加成）
function _makePlayerState(playerName, roleKey) {
    const attrs = getEffectiveBattleAttrs(playerName, roleKey);
    return {
        hp: attrs.HP, maxHp: attrs.HP,
        mp: attrs.MP, maxMp: attrs.MP,
        shield: 0, alive: true,
        defending: false, buffs: [],
        damage_taken: 0
    };
}

function createBattle(initiator, roleKey) {
    const config = getAttackDefenseConfig();
    return {
        id: generateBattleId(),
        initiator,
        status: "pending",
        players: [initiator],
        roleKeys: { [initiator]: roleKey },
        turns: config.defaultTurns || 10,
        currentTurn: 0,
        turnOrder: [],
        currentPlayerIndex: 0,
        createdAt: Date.now(),
        turnStartTime: Date.now(),
        actions: [],
        playerStates: { [initiator]: _makePlayerState(initiator, roleKey) },
        winner: null
    };
}

function addPlayerToBattle(battleId, playerName, roleKey) {
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    const battle = data.battles[battleId];
    if (!battle || battle.status !== "pending") return false;
    if (battle.players.includes(playerName)) return false;

    battle.players.push(playerName);
    if (!battle.roleKeys) battle.roleKeys = {};
    battle.roleKeys[playerName] = roleKey;
    battle.playerStates[playerName] = _makePlayerState(playerName, roleKey);

    saveAttackDefenseData(data);
    return true;
}

function startBattle(battle) {
    const agiMap = {};
    battle.players.forEach(p => {
        const rk = (battle.roleKeys || {})[p] || p;
        agiMap[p] = getEffectiveBattleAttrs(p, rk).AGI;
    });
    battle.turnOrder = [...battle.players].sort((a, b) => agiMap[b] - agiMap[a]);
    battle.currentPlayerIndex = 0;
    battle.status = "ongoing";
    battle.currentTurn = 1;
    battle.turnStartTime = Date.now();
}

function getCurrentBattlePlayer(battle) {
    if (!battle || battle.status !== "ongoing") return null;
    return battle.turnOrder[battle.currentPlayerIndex];
}

// 推进到下一个存活玩家，必要时增加回合数
function advanceTurn(battle) {
    const n = battle.turnOrder.length;
    let steps = 0;
    do {
        battle.currentPlayerIndex = (battle.currentPlayerIndex + 1) % n;
        if (battle.currentPlayerIndex === 0) battle.currentTurn++;
        steps++;
    } while (steps < n && !battle.playerStates[battle.turnOrder[battle.currentPlayerIndex]].alive);
    battle.turnStartTime = Date.now();
}

// 每个玩家回合开始时：回复 MP + 处理 buff 倒计时
function processTurnStart(battle, playerName) {
    const state = battle.playerStates[playerName];
    if (!state) return;
    const rk = (battle.roleKeys || {})[playerName] || playerName;
    const mpRegen = getEffectiveBattleAttrs(playerName, rk).MP_REGEN || 0;
    state.mp = Math.min(state.maxMp, state.mp + mpRegen);
    if (state.buffs) {
        state.buffs = state.buffs.filter(b => { b.turnsLeft--; return b.turnsLeft > 0; });
    }
}

// ========================
// 攻防系统 - 伤害计算
// ========================

// 公式：damage × 100/(100+DEF)。DEF=50 → 67%；DEF=100 → 50%；DEF=200 → 33%
function _defReduction(raw, def) {
    return Math.max(1, Math.round(raw * 100 / (100 + Math.max(0, def))));
}

function _effectiveDef(playerName, battle) {
    const rk = (battle.roleKeys || {})[playerName] || playerName;
    let def = getEffectiveBattleAttrs(playerName, rk).DEF;
    const st = battle.playerStates[playerName];
    if (st && st.buffs) st.buffs.forEach(b => { if (b.type === "debuff_def") def -= b.amount; });
    return Math.max(0, def);
}

function _effectiveAtk(playerName, battle) {
    const rk = (battle.roleKeys || {})[playerName] || playerName;
    let atk = getEffectiveBattleAttrs(playerName, rk).ATK;
    const st = battle.playerStates[playerName];
    if (st && st.buffs) st.buffs.forEach(b => { if (b.type === "debuff_atk") atk -= b.amount; });
    return Math.max(0, atk);
}

// 对战斗内目标施加伤害（处理防守状态 + 护盾 + HP扣减）
function _dealDamage(battle, targetName, rawDmg) {
    const st = battle.playerStates[targetName];
    if (!st || !st.alive) return 0;
    let dmg = rawDmg;
    if (st.defending) { dmg = Math.max(1, Math.floor(dmg * 0.5)); st.defending = false; }
    if (st.shield > 0) {
        const abs = Math.min(st.shield, dmg);
        st.shield -= abs; dmg -= abs;
    }
    if (dmg > 0) {
        st.hp -= dmg; st.damage_taken += dmg;
        if (st.hp <= 0) { st.hp = 0; st.alive = false; }
    }
    return rawDmg - dmg >= 0 ? rawDmg - (rawDmg - dmg >= dmg ? dmg : 0) : dmg; // 实际造成伤害
}

// 实际伤害简化版（含随机 ±10%）
function _calcAndDeal(battle, attackerName, targetName) {
    const atk = _effectiveAtk(attackerName, battle);
    const def = _effectiveDef(targetName, battle);
    const rand = 0.9 + Math.random() * 0.2;
    const raw = _defReduction(Math.round(atk * rand), def);
    return _dealDamage(battle, targetName, raw);
}

function getAlivePlayersCount(battle) {
    return battle.players.filter(p => battle.playerStates[p] && battle.playerStates[p].alive).length;
}

// ========================
// 攻防系统 - 技能执行引擎
// ========================

function executeSkill(battle, skillName, casterName, targetName) {
    const defs = getSkillDefs();
    const skill = defs[skillName];
    if (!skill) return { ok: false, msg: `❌ 技能「${skillName}」不存在，请检查技能库。` };

    const cst = battle.playerStates[casterName];
    const params = skill.params || {};
    const mpCost = skill.mpCost || 0;

    if (cst.mp < mpCost) return { ok: false, msg: `❌ MP不足（需要 ${mpCost}，当前 ${cst.mp}）。` };
    cst.mp -= mpCost;

    const lines = [`✨ ${casterName} 使用了【${skillName}】！`];
    const type = skill.type;

    const needTarget = ["damage","true_damage","drain","debuff_atk","debuff_def","mp_drain"];
    if (needTarget.includes(type) && type !== "aoe") {
        if (!targetName) return { ok: false, msg: "❌ 该技能需要指定目标。" };
        const tst = battle.playerStates[targetName];
        if (!tst || !tst.alive) return { ok: false, msg: "❌ 目标不存在或已被击败。" };
        if (targetName === casterName && !["heal","shield"].includes(type)) {
            return { ok: false, msg: "❌ 不能对自己使用此技能。" };
        }
    }

    if (type === "damage") {
        const atk = _effectiveAtk(casterName, battle);
        const def = _effectiveDef(targetName, battle);
        const mult = params.multiplier || 1.0;
        const rawDmg = _defReduction(Math.round(atk * mult * (0.9 + Math.random() * 0.2)), def);
        const actual = _dealDamage(battle, targetName, rawDmg);
        const tst = battle.playerStates[targetName];
        lines.push(`💥 对 ${targetName} 造成 ${actual} 伤害（${Math.round(mult*100)}% 攻击力）`);
        lines.push(`❤️ ${targetName} HP：${Math.max(0,tst.hp)}/${tst.maxHp}`);
        if (!tst.alive) lines.push(`☠️ ${targetName} 被击败！`);

    } else if (type === "true_damage") {
        const dmg = Math.round((params.amount || 30) * (0.9 + Math.random() * 0.2));
        const actual = _dealDamage(battle, targetName, dmg);
        const tst = battle.playerStates[targetName];
        lines.push(`💥 对 ${targetName} 造成 ${actual} 真实伤害（无视防御）`);
        lines.push(`❤️ ${targetName} HP：${Math.max(0,tst.hp)}/${tst.maxHp}`);
        if (!tst.alive) lines.push(`☠️ ${targetName} 被击败！`);

    } else if (type === "heal") {
        const amt = params.amount || 50;
        const before = cst.hp;
        cst.hp = Math.min(cst.maxHp, cst.hp + amt);
        lines.push(`💚 回复 ${cst.hp - before} HP（${cst.hp}/${cst.maxHp}）`);

    } else if (type === "drain") {
        const atk = _effectiveAtk(casterName, battle);
        const def = _effectiveDef(targetName, battle);
        const mult = params.multiplier || 1.0;
        const rawDmg = _defReduction(Math.round(atk * mult * (0.9 + Math.random() * 0.2)), def);
        const actual = _dealDamage(battle, targetName, rawDmg);
        const healed = Math.round(actual * (params.drainPct || 0.5));
        cst.hp = Math.min(cst.maxHp, cst.hp + healed);
        const tst = battle.playerStates[targetName];
        lines.push(`🩸 对 ${targetName} 造成 ${actual} 伤害，吸取 ${healed} HP！`);
        lines.push(`❤️ ${targetName} ${Math.max(0,tst.hp)}/${tst.maxHp} ← ${casterName} ${cst.hp}/${cst.maxHp}`);
        if (!tst.alive) lines.push(`☠️ ${targetName} 被击败！`);

    } else if (type === "shield") {
        const amt = params.amount || 50;
        cst.shield += amt;
        lines.push(`🛡️ 获得 ${amt} 护盾（当前护盾：${cst.shield}）`);

    } else if (type === "aoe") {
        const enemies = battle.players.filter(p => p !== casterName && battle.playerStates[p].alive);
        if (!enemies.length) return { ok: false, msg: "❌ 场上没有可攻击的目标。" };
        const mult = params.multiplier || 0.7;
        const hits = [];
        enemies.forEach(enemy => {
            const atk = _effectiveAtk(casterName, battle);
            const def = _effectiveDef(enemy, battle);
            const rawDmg = _defReduction(Math.round(atk * mult * (0.85 + Math.random() * 0.3)), def);
            const actual = _dealDamage(battle, enemy, rawDmg);
            const tst = battle.playerStates[enemy];
            hits.push(`${enemy} -${actual}HP（剩 ${Math.max(0,tst.hp)}）${tst.alive ? '' : ' ☠️'}`);
        });
        lines.push(`💥 群体攻击！\n` + hits.join("\n"));

    } else if (type === "debuff_atk" || type === "debuff_def") {
        const tst = battle.playerStates[targetName];
        if (!tst.buffs) tst.buffs = [];
        const turns = params.turns || 2;
        const amount = params.amount || 20;
        tst.buffs.push({ type, amount, turnsLeft: turns });
        const label = type === "debuff_atk" ? "ATK" : "DEF";
        lines.push(`📉 ${targetName} 的 ${label} 降低 ${amount}，持续 ${turns} 回合`);

    } else if (type === "mp_drain") {
        const tst = battle.playerStates[targetName];
        const amt = Math.min(params.amount || 30, tst.mp);
        tst.mp -= amt;
        cst.mp = Math.min(cst.maxMp, cst.mp + Math.floor(amt * 0.5));
        lines.push(`🔵 消耗 ${targetName} ${amt} MP，自身回复 ${Math.floor(amt*0.5)} MP`);

    } else {
        return { ok: false, msg: `❌ 未知技能类型「${type}」。` };
    }

    return { ok: true, msg: lines.join("\n") };
}

// ========================
// 攻防系统 - 战斗结算与奖励
// ========================

function resolveBattleEnd(battle) {
    battle.status = "ended";
    const config = getAttackDefenseConfig();
    const alive = battle.players.filter(p => battle.playerStates[p] && battle.playerStates[p].alive);

    let winner = null;
    if (alive.length === 1) {
        winner = alive[0];
    } else if (alive.length > 1) {
        // 回合上限：按剩余HP%排名
        winner = alive.sort((a, b) => {
            const sa = battle.playerStates[a], sb = battle.playerStates[b];
            return (sb.hp / sb.maxHp) - (sa.hp / sa.maxHp);
        })[0];
    }
    battle.winner = winner;

    // 写入战斗日志（供网页端查看）
    const _log = JSON.parse(mainStorGet("battle_log") || "[]");
    _log.unshift({
        id: battle.id, players: battle.players, winner: winner || null,
        turns: battle.currentTurn, actions: (battle.actions || []).length,
        endedAt: Date.now()
    });
    if (_log.length > 100) _log.length = 100;
    mainStorSet("battle_log", JSON.stringify(_log));

    const lines = ["⚔️ ─ 战斗结束 ─"];
    if (winner) lines.push(`🏆 ${winner} 胜利！`);
    else lines.push(`⚔️ 平局！`);

    // 发放奖励
    const currName = config.rewardCurrency;
    const winAmt   = parseInt(config.rewardWin)  || 0;
    const loseAmt  = parseInt(config.rewardLose) || 0;
    if (currName && (winAmt > 0 || loseAmt > 0)) {
        const reg = getRegistry();
        const curr = Object.values(reg).find(r => r.name === currName && r.type === "currency");
        if (curr) {
            battle.players.forEach(p => {
                const rk = (battle.roleKeys || {})[p] || p;
                const isWinner = p === winner;
                const isDraw   = !winner;
                const amt = isDraw ? Math.floor(winAmt * 0.5) : isWinner ? winAmt : loseAmt;
                if (amt > 0) {
                    addToInv(rk, curr.code, amt);
                    lines.push(`💰 ${p} 获得 ${amt} ${currName}`);
                }
            });
        }
    }

    return lines.join("\n");
}

// ========================
// 攻防系统 - 辅助：找玩家所在进行中战斗
// ========================

function findActiveBattle(player) {
    const data = getAttackDefenseData();
    if (!data.battles) return null;
    for (const bid in data.battles) {
        const b = data.battles[bid];
        if (b.status === "ongoing" && b.players.includes(player)) return { data, battle: b };
    }
    return null;
}

// 检查回合数是否超限，超限则结算
function checkTurnLimit(battle, data) {
    const config = getAttackDefenseConfig();
    const maxTurns = config.defaultTurns || 10;
    if (battle.currentTurn > maxTurns) {
        const resultMsg = resolveBattleEnd(battle);
        saveAttackDefenseData(data);
        return resultMsg;
    }
    return null;
}

// ========================
// 攻防系统 - 命令: PK
// ========================

// ─ 提取 roleKey 的辅助函数 ─
function _getRoleKey(msg) {
    const parts = msg.sender.userId.split(':');
    const platform = parts[0];
    const rawUid = parts[1];
    const uid = getPrimaryUid(platform, rawUid);
    return `${platform}:${uid}`;
}

let cmd_pk = seal.ext.newCmdItemInfo();
cmd_pk.name = "PK";
cmd_pk.help = "⚔️ 战斗系统\nPK 发起 [对手名]...  — 发起战斗（可指定对手，或留空开放挑战）\nPK 接受 <战斗ID>    — 接受/加入战斗\nPK 拒绝 <战斗ID>    — 拒绝战斗邀请";
cmd_pk.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");

    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");
    const roleKey = _getRoleKey(msg);

    const subCmd = cmdArgs.getArgN(1);
    const data = getAttackDefenseData();
    if (!data.battles) data.battles = {};
    if (!data.playerStats) data.playerStats = {};

    if (subCmd === "发起") {
        // 每日发起次数限制
        const today = new Date().toDateString();
        if (!data.playerStats[player]) data.playerStats[player] = initPlayerBattleAttrs();
        const stats = data.playerStats[player];
        if (!stats.initiations) stats.initiations = {};
        if (!stats.initiations[today]) stats.initiations[today] = 0;
        const maxInit = config.maxInitiations || 10;
        if (stats.initiations[today] >= maxInit) {
            return seal.replyToSender(ctx, msg, `❌ 今日发起次数已达上限（${maxInit} 次）。`);
        }

        const battle = createBattle(player, roleKey);
        const opponents = [];
        for (let i = 2; i <= cmdArgs.getArgCount(); i++) {
            const opp = cmdArgs.getArgN(i);
            if (opp) opponents.push(opp);
        }
        opponents.forEach(opp => addPlayerToBattle(battle.id, opp, opp)); // 对手 roleKey 等 PK 接受时再补全

        if (opponents.length > 0) {
            // 双方都在，直接开战
            startBattle(battle);
            data.battles[battle.id] = battle;
            stats.initiations[today]++;
            saveAttackDefenseData(data);
            const first = getCurrentBattlePlayer(battle);
            processTurnStart(battle, first);
            saveAttackDefenseData(data);
            return seal.replyToSender(ctx, msg,
                `⚔️ 战斗开始！\n战斗ID：${battle.id}\n参战者：${battle.players.join("、")}\n` +
                `\n先手：${first}\n` +
                `\n可用行动：攻击 / 防守 / 使用技能 技能名 目标 / 战斗用品 物品名 / 投降`
            );
        } else {
            battle.status = "pending";
            data.battles[battle.id] = battle;
            stats.initiations[today]++;
            saveAttackDefenseData(data);
            return seal.replyToSender(ctx, msg,
                `⚔️ ${player} 发起了开放战斗！\n战斗ID：${battle.id}\n\n其他人输入「PK 接受 ${battle.id}」加入`
            );
        }
    }

    if (subCmd === "接受") {
        const battleId = cmdArgs.getArgN(2);
        if (!battleId || !data.battles[battleId]) return seal.replyToSender(ctx, msg, "❌ 无效的战斗ID。");
        const battle = data.battles[battleId];
        if (battle.status !== "pending") return seal.replyToSender(ctx, msg, "❌ 该战斗已无法加入。");
        if (battle.players.includes(player)) return seal.replyToSender(ctx, msg, "❌ 你已在此战斗中。");

        // 补全 roleKey（发起时对手的 roleKey 可能是占位的）
        if (!battle.roleKeys) battle.roleKeys = {};
        battle.roleKeys[player] = roleKey;
        if (!battle.playerStates[player]) {
            battle.players.push(player);
            battle.playerStates[player] = _makePlayerState(player, roleKey);
        } else {
            // 重新生成（之前 roleKey 是占位的）
            battle.playerStates[player] = _makePlayerState(player, roleKey);
        }

        const minPlayers = config.minPlayers || 2;
        if (battle.players.length >= minPlayers) {
            startBattle(battle);
            const first = getCurrentBattlePlayer(battle);
            processTurnStart(battle, first);
            saveAttackDefenseData(data);
            return seal.replyToSender(ctx, msg,
                `✅ ${player} 加入！战斗开始！\n战斗ID：${battle.id}\n参战者：${battle.players.join("、")}\n` +
                `\n先手：${first}\n可用行动：攻击 / 防守 / 使用技能 技能名 目标 / 战斗用品 物品名 / 投降`
            );
        }
        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, `✅ ${player} 加入战斗 ${battleId}！\n参战者：${battle.players.join("、")}`);
    }

    if (subCmd === "拒绝") {
        const battleId = cmdArgs.getArgN(2);
        if (!battleId || !data.battles[battleId]) return seal.replyToSender(ctx, msg, "❌ 无效的战斗ID。");
        const battle = data.battles[battleId];
        if (!battle.players.includes(battle.initiator) || battle.initiator === player) {
            delete data.battles[battleId];
        }
        saveAttackDefenseData(data);
        return seal.replyToSender(ctx, msg, `✅ 已拒绝战斗 ${battleId}。`);
    }
};

ext.cmdMap["PK"] = cmd_pk;

// ========================
// 攻防系统 - 命令: 攻击
// ========================

// 回合行动公共收尾：推进回合 + 检查上限 + 保存
function _afterAction(data, battle) {
    if (getAlivePlayersCount(battle) <= 1) {
        const r = resolveBattleEnd(battle);
        saveAttackDefenseData(data);
        return r;
    }
    advanceTurn(battle);
    const next = getCurrentBattlePlayer(battle);
    const limitMsg = checkTurnLimit(battle, data);
    if (limitMsg) { saveAttackDefenseData(data); return limitMsg; }
    processTurnStart(battle, next);
    saveAttackDefenseData(data);
    const nst = battle.playerStates[next];
    return `➡️ 轮到 ${next} 的回合（HP ${nst.hp}/${nst.maxHp}  MP ${nst.mp}/${nst.maxMp}）`;
}

let cmd_attack = seal.ext.newCmdItemInfo();
cmd_attack.name = "攻击";
cmd_attack.help = "攻击 <目标名>  — 普通攻击（受DEF减伤，±10%随机）";
cmd_attack.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");
    const targetName = cmdArgs.getArgN(1);
    if (!targetName) return seal.replyToSender(ctx, msg, "❌ 请指定攻击目标。");
    if (targetName === player) return seal.replyToSender(ctx, msg, "❌ 不能攻击自己。");

    const found = findActiveBattle(player);
    if (!found) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");
    const { data, battle } = found;

    if (getCurrentBattlePlayer(battle) !== player)
        return seal.replyToSender(ctx, msg, `❌ 还没到你的回合，当前：${getCurrentBattlePlayer(battle)}`);
    const tst = battle.playerStates[targetName];
    if (!tst) return seal.replyToSender(ctx, msg, "❌ 目标不在此战斗中。");
    if (!tst.alive) return seal.replyToSender(ctx, msg, "❌ 目标已被击败。");

    const dmg = _calcAndDeal(battle, player, targetName);
    battle.actions.push({ turn: battle.currentTurn, actor: player, action: "attack", target: targetName, damage: dmg });

    let reply = `⚔️ ${player} 普通攻击 ${targetName}！\n💥 造成 ${dmg} 伤害`;
    reply += `\n❤️ ${targetName} HP：${Math.max(0,tst.hp)}/${tst.maxHp}`;
    if (!tst.alive) reply += `\n☠️ ${targetName} 被击败！`;
    reply += "\n\n" + _afterAction(data, battle);
    return seal.replyToSender(ctx, msg, reply);
};
ext.cmdMap["攻击"] = cmd_attack;

// ========================
// 攻防系统 - 命令: 防守
// ========================

let cmd_defend = seal.ext.newCmdItemInfo();
cmd_defend.name = "防守";
cmd_defend.help = "防守  — 进入防守姿态，下次受到攻击伤害减半";
cmd_defend.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");

    const found = findActiveBattle(player);
    if (!found) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");
    const { data, battle } = found;

    if (getCurrentBattlePlayer(battle) !== player)
        return seal.replyToSender(ctx, msg, `❌ 还没到你的回合，当前：${getCurrentBattlePlayer(battle)}`);

    battle.playerStates[player].defending = true;
    battle.actions.push({ turn: battle.currentTurn, actor: player, action: "defend" });
    const tail = _afterAction(data, battle);
    return seal.replyToSender(ctx, msg, `🛡️ ${player} 进入防守姿态！（下次受击伤害减半）\n\n${tail}`);
};
ext.cmdMap["防守"] = cmd_defend;

// ========================
// 攻防系统 - 命令: 使用技能
// ========================

let cmd_use_skill = seal.ext.newCmdItemInfo();
cmd_use_skill.name = "使用技能";
cmd_use_skill.help = "使用技能 <技能名> [目标名]  — 消耗MP使用已解锁的技能";
cmd_use_skill.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");
    const skillName = cmdArgs.getArgN(1);
    if (!skillName) return seal.replyToSender(ctx, msg, "❌ 请指定技能名。");

    const playerSkills = (getPlayerSkills())[player] || [];
    if (!playerSkills.includes(skillName))
        return seal.replyToSender(ctx, msg, `❌ 你未解锁技能「${skillName}」。\n输入「我的技能」查看已解锁技能。`);

    const found = findActiveBattle(player);
    if (!found) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");
    const { data, battle } = found;

    if (getCurrentBattlePlayer(battle) !== player)
        return seal.replyToSender(ctx, msg, `❌ 还没到你的回合，当前：${getCurrentBattlePlayer(battle)}`);

    const targetName = cmdArgs.getArgN(2);
    const result = executeSkill(battle, skillName, player, targetName);
    if (!result.ok) return seal.replyToSender(ctx, msg, result.msg);

    battle.actions.push({ turn: battle.currentTurn, actor: player, action: "skill", skill: skillName, target: targetName });
    const tail = _afterAction(data, battle);
    return seal.replyToSender(ctx, msg, result.msg + "\n\n" + tail);
};
ext.cmdMap["使用技能"] = cmd_use_skill;

// ========================
// 攻防系统 - 命令: 战斗用品
// ========================

let cmd_battle_item = seal.ext.newCmdItemInfo();
cmd_battle_item.name = "战斗用品";
cmd_battle_item.help = "战斗用品 <物品名/代码>  — 在战斗中消耗背包物品（仅生效HP/MP效果）";
cmd_battle_item.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");
    const roleKey = _getRoleKey(msg);
    const itemInput = cmdArgs.getArgN(1);
    if (!itemInput) return seal.replyToSender(ctx, msg, "❌ 请指定物品名或代码。");

    const found = findActiveBattle(player);
    if (!found) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");
    const { data, battle } = found;

    if (getCurrentBattlePlayer(battle) !== player)
        return seal.replyToSender(ctx, msg, `❌ 还没到你的回合，当前：${getCurrentBattlePlayer(battle)}`);

    const reg = getRegistry();
    const item = findItem(reg, itemInput);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未找到物品「${itemInput}」。`);
    if (!item.attrs) return seal.replyToSender(ctx, msg, `❌「${item.name}」没有属性效果，无法在战斗中使用。`);
    if (getInvCount(roleKey, item.code) < 1)
        return seal.replyToSender(ctx, msg, `❌ 背包里没有「${item.name}」。`);

    const effects = parseAttrEffects(item.attrs);
    const st = battle.playerStates[player];
    const lines = [`🎒 ${player} 使用了「${item.name}」！`];
    let used = false;

    for (const attr in effects) {
        const delta = effects[attr];
        if (attr === "HP") {
            const before = st.hp;
            st.hp = Math.max(0, Math.min(st.maxHp, st.hp + delta));
            lines.push(`❤️ HP ${delta > 0 ? '+' : ''}${st.hp - before}（${st.hp}/${st.maxHp}）`);
            used = true;
        } else if (attr === "MP") {
            const before = st.mp;
            st.mp = Math.max(0, Math.min(st.maxMp, st.mp + delta));
            lines.push(`🔵 MP ${delta > 0 ? '+' : ''}${st.mp - before}（${st.mp}/${st.maxMp}）`);
            used = true;
        }
    }
    if (!used) return seal.replyToSender(ctx, msg, `❌「${item.name}」的效果在战斗中无效（仅支持HP/MP类）。`);

    removeFromInv(roleKey, item.code, 1);
    battle.actions.push({ turn: battle.currentTurn, actor: player, action: "item", item: item.name });
    const tail = _afterAction(data, battle);
    return seal.replyToSender(ctx, msg, lines.join("\n") + "\n\n" + tail);
};
ext.cmdMap["战斗用品"] = cmd_battle_item;

// ========================
// 攻防系统 - 命令: 投降/逃跑
// ========================

let cmd_surrender = seal.ext.newCmdItemInfo();
cmd_surrender.name = "投降";
cmd_surrender.help = "投降  — 直接认输退出战斗\n逃跑  — 有成功率的逃脱（默认30%）";
cmd_surrender.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");

    const found = findActiveBattle(player);
    if (!found) return seal.replyToSender(ctx, msg, "❌ 你未参加进行中的战斗。");
    const { data, battle } = found;

    const isEscape = msg.message.includes("逃跑");
    if (isEscape) {
        const escapeRate = config.escapeRate !== undefined ? config.escapeRate : 30;
        if (Math.random() * 100 >= escapeRate) {
            battle.actions.push({ turn: battle.currentTurn, actor: player, action: "escape", success: false });
            const tail = _afterAction(data, battle);
            return seal.replyToSender(ctx, msg, `❌ ${player} 逃跑失败！（成功率 ${escapeRate}%）\n\n${tail}`);
        }
        battle.actions.push({ turn: battle.currentTurn, actor: player, action: "escape", success: true });
    } else {
        battle.actions.push({ turn: battle.currentTurn, actor: player, action: "surrender" });
    }

    battle.playerStates[player].alive = false;
    const resultMsg = resolveBattleEnd(battle);
    saveAttackDefenseData(data);
    const prefix = isEscape ? `💨 ${player} 成功逃离！` : `🏳️ ${player} 投降！`;
    return seal.replyToSender(ctx, msg, `${prefix}\n\n${resultMsg}`);
};
ext.cmdMap["投降"] = cmd_surrender;
ext.cmdMap["逃跑"] = cmd_surrender;

// ========================
// 攻防系统 - 管理员指令
// ========================

let cmd_attack_defense_admin = seal.ext.newCmdItemInfo();
cmd_attack_defense_admin.name = "攻防";
cmd_attack_defense_admin.help = "【管理员】攻防系统\n攻防 开/关       — 启用/禁用\n攻防 查看        — 查看配置\n攻防 设置 参数 值 — 修改参数\n攻防 结束 战斗ID  — 强制结束战斗\n\n可设置参数：每日发起/默认回合/逃脱率/奖励货币/胜者奖励/败者奖励/最小人数";
cmd_attack_defense_admin.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const subCmd = cmdArgs.getArgN(1);
    let config = getAttackDefenseConfig();

    if (subCmd === "开") { config.enabled = true;  saveAttackDefenseConfig(config); return seal.replyToSender(ctx, msg, "✅ 攻防系统已启用。"); }
    if (subCmd === "关") { config.enabled = false; saveAttackDefenseConfig(config); return seal.replyToSender(ctx, msg, "✅ 攻防系统已禁用。"); }

    if (subCmd === "查看") {
        let info = `🎮 攻防系统配置\n状态：${config.enabled ? "✅ 已启用" : "❌ 已禁用"}\n\n`;
        info += `每日最大发起：${config.maxInitiations || 10}\n`;
        info += `默认回合数：${config.defaultTurns || 10}\n`;
        info += `逃脱成功率：${config.escapeRate !== undefined ? config.escapeRate : 30}%\n`;
        info += `最小参战人数：${config.minPlayers || 2}\n`;
        info += `奖励货币：${config.rewardCurrency || "（未设置）"}\n`;
        info += `胜者奖励：${config.rewardWin || 0}\n`;
        info += `败者奖励：${config.rewardLose || 0}\n`;
        return seal.replyToSender(ctx, msg, info);
    }

    if (subCmd === "结束") {
        const battleId = cmdArgs.getArgN(2);
        if (!battleId) return seal.replyToSender(ctx, msg, "❌ 请指定战斗ID。");
        const adData = getAttackDefenseData();
        const battle = adData.battles && adData.battles[battleId];
        if (!battle || battle.status !== "ongoing") return seal.replyToSender(ctx, msg, "❌ 战斗不存在或已结束。");
        const resultMsg = resolveBattleEnd(battle);
        saveAttackDefenseData(adData);
        return seal.replyToSender(ctx, msg, `✅ 强制结束战斗 ${battleId}\n\n${resultMsg}`);
    }

    if (subCmd === "设置") {
        const param = cmdArgs.getArgN(2);
        const val   = cmdArgs.getArgN(3);
        if (!param || !val) return seal.replyToSender(ctx, msg, "❌ 请指定参数和值。");
        const map = {
            "每日发起": "maxInitiations", "默认回合": "defaultTurns",
            "逃脱率": "escapeRate", "最小人数": "minPlayers",
            "奖励货币": "rewardCurrency", "胜者奖励": "rewardWin", "败者奖励": "rewardLose"
        };
        const key = map[param];
        if (!key) return seal.replyToSender(ctx, msg, `❌ 未知参数「${param}」`);
        config[key] = (key === "rewardCurrency") ? val : parseInt(val);
        saveAttackDefenseConfig(config);
        return seal.replyToSender(ctx, msg, `✅ 已设置 ${param} = ${val}`);
    }

    return seal.replyToSender(ctx, msg, cmd_attack_defense_admin.help);
};
ext.cmdMap["攻防"] = cmd_attack_defense_admin;

// ========================
// 攻防系统 - 玩家技能管理
// ========================

let cmd_player_skill = seal.ext.newCmdItemInfo();
cmd_player_skill.name = "玩家技能";
cmd_player_skill.help = "【管理员】玩家技能管理\n玩家技能 <角色名> <技能名> 授予  — 为角色解锁技能\n玩家技能 <角色名> <技能名> 撤销  — 取消角色技能\n玩家技能 <角色名>          — 查看角色的技能列表";
cmd_player_skill.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const targetPlayer = cmdArgs.getArgN(1);
    if (!targetPlayer) return seal.replyToSender(ctx, msg, "❌ 请指定角色名。");

    const allSkills = getPlayerSkills();
    if (!allSkills[targetPlayer]) allSkills[targetPlayer] = [];
    const skills = allSkills[targetPlayer];

    const skillName = cmdArgs.getArgN(2);
    const action    = cmdArgs.getArgN(3);

    if (!skillName) {
        const defs = getSkillDefs();
        const info = skills.length
            ? skills.map(s => `· ${s}${defs[s] ? `（${defs[s].type} MP:${defs[s].mpCost||0}）` : ''}`).join("\n")
            : "（暂无技能）";
        return seal.replyToSender(ctx, msg, `🌟 ${targetPlayer} 的技能列表：\n${info}`);
    }

    if (action === "授予") {
        const defs = getSkillDefs();
        if (!defs[skillName]) return seal.replyToSender(ctx, msg, `❌ 技能「${skillName}」不在技能库中，请先在 rp_archive 管理端注册。`);
        if (skills.includes(skillName)) return seal.replyToSender(ctx, msg, `❌ ${targetPlayer} 已拥有「${skillName}」。`);
        skills.push(skillName);
        savePlayerSkills(allSkills);
        return seal.replyToSender(ctx, msg, `✅ 已为 ${targetPlayer} 授予技能「${skillName}」。`);
    }

    if (action === "撤销") {
        const idx = skills.indexOf(skillName);
        if (idx === -1) return seal.replyToSender(ctx, msg, `❌ ${targetPlayer} 未持有「${skillName}」。`);
        skills.splice(idx, 1);
        savePlayerSkills(allSkills);
        return seal.replyToSender(ctx, msg, `✅ 已撤销 ${targetPlayer} 的技能「${skillName}」。`);
    }

    return seal.replyToSender(ctx, msg, cmd_player_skill.help);
};
ext.cmdMap["玩家技能"] = cmd_player_skill;

// ========================
// 攻防系统 - 技能库 / 我的技能
// ========================

let cmd_skill_lib = seal.ext.newCmdItemInfo();
cmd_skill_lib.name = "技能库";
cmd_skill_lib.help = "技能库  — 查看所有已注册的战斗技能";
cmd_skill_lib.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const defs = getSkillDefs();
    const entries = Object.values(defs);
    if (!entries.length) return seal.replyToSender(ctx, msg, "📖 技能库暂无技能，请管理员在 rp_archive 注册。");
    let info = `📖 技能库（${entries.length}个）\n\n`;
    entries.forEach(sk => {
        const p = sk.params || {};
        const pStr = Object.entries(p).map(([k,v]) => `${k}:${v}`).join(" ");
        info += `【${sk.name}】 类型:${sk.type}  MP:${sk.mpCost||0}\n`;
        if (pStr) info += `  参数：${pStr}\n`;
        if (sk.desc) info += `  ${sk.desc}\n`;
    });
    return seal.replyToSender(ctx, msg, info.trim());
};
ext.cmdMap["技能库"] = cmd_skill_lib;

let cmd_my_skills = seal.ext.newCmdItemInfo();
cmd_my_skills.name = "我的技能";
cmd_my_skills.help = "我的技能  — 查看已解锁的技能";
cmd_my_skills.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");
    const skills = (getPlayerSkills())[player] || [];
    if (!skills.length) return seal.replyToSender(ctx, msg, "🌟 你还没有解锁任何技能。");
    const defs = getSkillDefs();
    let info = `🌟 ${player} 的技能（${skills.length}个）\n\n`;
    skills.forEach(s => {
        const sk = defs[s];
        if (!sk) { info += `· ${s}（定义已删除）\n`; return; }
        info += `【${s}】 ${sk.type}  MP:${sk.mpCost||0}\n`;
        if (sk.desc) info += `  ${sk.desc}\n`;
    });
    return seal.replyToSender(ctx, msg, info.trim());
};
ext.cmdMap["我的技能"] = cmd_my_skills;

// ========================
// 攻防系统 - 战斗状态
// ========================

let cmd_battle_status = seal.ext.newCmdItemInfo();
cmd_battle_status.name = "战斗状态";
cmd_battle_status.help = "战斗状态 [战斗ID]  — 查看战斗详情";
cmd_battle_status.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");

    const battleId = cmdArgs.getArgN(1);
    const adData = getAttackDefenseData();
    if (!adData.battles) return seal.replyToSender(ctx, msg, "❌ 没有战斗记录。");

    let battle = battleId ? adData.battles[battleId] : null;
    if (!battle) {
        for (const bid in adData.battles) {
            if (adData.battles[bid].players.includes(player) && adData.battles[bid].status === "ongoing") {
                battle = adData.battles[bid]; break;
            }
        }
    }
    if (!battle) return seal.replyToSender(ctx, msg, "❌ 未找到战斗。");

    const maxTurns = config.defaultTurns || 10;
    let info = `⚔️ 战斗 ${battle.id}  回合 ${battle.currentTurn}/${maxTurns}\n`;
    info += `当前行动：${getCurrentBattlePlayer(battle) || "—"}\n\n`;
    battle.players.forEach(p => {
        const st = battle.playerStates[p];
        const icon = st.alive ? "🟢" : "💀";
        const bufStr = (st.buffs || []).map(b => `${b.type.replace("debuff_","-")}${b.amount}(${b.turnsLeft})`).join(" ");
        info += `${icon} ${p}\n`;
        info += `   HP ${st.hp}/${st.maxHp}  MP ${st.mp}/${st.maxMp}  盾 ${st.shield}`;
        if (st.defending) info += "  🛡️防守中";
        if (bufStr) info += `\n   ${bufStr}`;
        info += "\n";
    });
    return seal.replyToSender(ctx, msg, info.trim());
};
ext.cmdMap["战斗状态"] = cmd_battle_status;

// ========================
// 攻防系统 - 查看/设置属性
// ========================

let cmd_battle_attrs = seal.ext.newCmdItemInfo();
cmd_battle_attrs.name = "属性";
cmd_battle_attrs.help = "属性 [角色名]  — 查看战斗属性（含装备加成）\n【管理员】属性 设置 <角色> <属性> <值>  — 修改基础属性\n可修改：ATK DEF AGI HP MP MP_REGEN";
cmd_battle_attrs.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const self = getRoleName(ctx, msg);
    const subCmd = cmdArgs.getArgN(1);

    if (subCmd === "设置" || subCmd === "修改") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
        const targetName = cmdArgs.getArgN(2);
        const attrName   = cmdArgs.getArgN(3);
        const value      = parseInt(cmdArgs.getArgN(4));
        if (!targetName || !attrName || isNaN(value))
            return seal.replyToSender(ctx, msg, "❌ 用法：属性 设置 <角色> <属性> <值>");
        const valid = ["ATK","DEF","AGI","HP","MP","MP_REGEN"];
        if (!valid.includes(attrName))
            return seal.replyToSender(ctx, msg, `❌ 可修改属性：${valid.join("  ")}`);
        const attrs = getPlayerBattleAttrs(targetName);
        const old = attrs[attrName];
        attrs[attrName] = value;
        savePlayerBattleAttrs(targetName, attrs);
        return seal.replyToSender(ctx, msg, `✅ ${targetName} 的 ${attrName}：${old} → ${value}`);
    }

    const targetName = subCmd || self;
    if (!targetName) return seal.replyToSender(ctx, msg, "❌ 无法获取角色信息。");
    if (targetName !== self && !isUserAdmin(ctx, msg))
        return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const parts = msg.sender.userId.split(':');
    const rk = (targetName === self) ? msg.sender.userId : targetName;
    const base  = getPlayerBattleAttrs(targetName);
    const eff   = getEffectiveBattleAttrs(targetName, rk);
    let info = `⚔️ ${targetName} 的战斗属性\n\n`;
    ["ATK","DEF","AGI","HP","MP","MP_REGEN"].forEach(attr => {
        const b = base[attr] || 0;
        const e = eff[attr] || 0;
        const diff = e - b;
        info += `${attr.padEnd(8)}  ${e}`;
        if (diff !== 0) info += `（基础 ${b} ${diff > 0 ? '+' : ''}${diff} 装备）`;
        info += "\n";
    });
    return seal.replyToSender(ctx, msg, info.trim());
};
ext.cmdMap["属性"] = cmd_battle_attrs;

// ========================
// 攻防系统 - 战斗历史
// ========================

let cmd_battle_history = seal.ext.newCmdItemInfo();
cmd_battle_history.name = "战斗历史";
cmd_battle_history.help = "战斗历史 <战斗ID> [页码]";
cmd_battle_history.solve = (ctx, msg, cmdArgs) => {
    const config = getAttackDefenseConfig();
    if (!config.enabled) return seal.replyToSender(ctx, msg, "❌ 攻防系统未启用。");
    const battleId = cmdArgs.getArgN(1);
    if (!battleId) return seal.replyToSender(ctx, msg, "❌ 请指定战斗ID。");
    const adData = getAttackDefenseData();
    if (!adData.battles || !adData.battles[battleId]) return seal.replyToSender(ctx, msg, "❌ 战斗不存在。");

    const battle  = adData.battles[battleId];
    const pageNum  = parseInt(cmdArgs.getArgN(2)) || 1;
    const pageSize = 10;
    const total    = battle.actions.length;
    const pages    = Math.max(1, Math.ceil(total / pageSize));
    if (pageNum < 1 || pageNum > pages) return seal.replyToSender(ctx, msg, `❌ 页码范围：1-${pages}`);

    let info = `📋 战斗 ${battle.id}  状态:${battle.status}  胜者:${battle.winner || "—"}\n第 ${pageNum}/${pages} 页\n\n`;
    const start = (pageNum - 1) * pageSize;
    for (let i = start; i < Math.min(start + pageSize, total); i++) {
        const a = battle.actions[i];
        info += `[T${a.turn}] ${a.actor} `;
        if (a.action === "attack")     info += `攻击 ${a.target} → ${a.damage} 伤害\n`;
        else if (a.action === "defend")    info += `防守\n`;
        else if (a.action === "skill")     info += `使用技能【${a.skill}】${a.target ? ' → ' + a.target : ''}\n`;
        else if (a.action === "item")      info += `使用道具「${a.item}」\n`;
        else if (a.action === "escape")    info += `逃跑 → ${a.success ? "成功" : "失败"}\n`;
        else if (a.action === "surrender") info += `投降\n`;
        else info += `${a.action}\n`;
    }
    return seal.replyToSender(ctx, msg, info.trim());
};
ext.cmdMap["战斗历史"] = cmd_battle_history;

// ========================
// 一键初始化 - 快速启用攻防系统
// ========================

let cmd_quick_init = seal.ext.newCmdItemInfo();
cmd_quick_init.name = "一键初始化";
cmd_quick_init.help = "【管理员】一键初始化攻防系统 - 注册属性和回血药\n一键初始化\n  将自动创建：\n  · 5个RPG属性（HP、MP、ATK、DEF、AGI）\n  · 4种回血药（小、中、大、满）\n  · 启用攻防系统";
cmd_quick_init.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const main = getMainExt();
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
                type: "item",
                desc: potion.desc,
                maxUses: parseInt(potion.uses),
                attrs: potion.effects,
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
            code: "EQUIP_SWORD_01"
        },
        {
            name: "皮革甲胄",
            desc: "轻便的皮甲防御",
            slot: "chest",
            baseAttrs: { DEF: 20, HP: 50 },
            code: "EQUIP_CHEST_01"
        },
        {
            name: "铁制头盔",
            desc: "保护头部的头盔",
            slot: "head",
            baseAttrs: { DEF: 10 },
            code: "EQUIP_HEAD_01"
        },
        {
            name: "腰部护甲",
            desc: "增强体力的护甲",
            slot: "hand",
            baseAttrs: { HP: 30 },
            code: "EQUIP_WAIST_01"
        },
        {
            name: "敏捷靴子",
            desc: "提升速度的靴子",
            slot: "foot",
            baseAttrs: { AGI: 5 },
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
                baseAttrs: equip.baseAttrs
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
    reply += `· 攻防系统已启用\n\n`;
    reply += `💡 下一步：\n`;
    reply += `· 上架商城：上架商城 ITEM_POT_S*50金币\n`;
    reply += `· 上架装备：上架商城 EQUIP_SWORD_01*500金币\n`;
    reply += `· 配置攻防：攻防 设置 参数 值\n`;
    reply += `· 创建池子：注册池子 回血药池 fixed`;

    // 注册池子开启/关闭命令
    registerPoolToggleCmds();
    reply += `\n· 已启用池子控制命令：开启池子、关闭池子`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["一键初始化"] = cmd_quick_init;

// ========================
// 装备系统 - 存储和配置
// ========================

function getEquipRegistry() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return JSON.parse(mainStorGet("equipment_registry") || "{}");
    } catch(e) { return {}; }
}

function saveEquipRegistry(reg) {
    const main = getMainExt();
    if (main) mainStorSet("equipment_registry", JSON.stringify(reg));
}

function getEquipConfig() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return JSON.parse(mainStorGet("equipment_config") || "{}");
    } catch(e) { return {}; }
}

function saveEquipConfig(config) {
    const main = getMainExt();
    if (main) mainStorSet("equipment_config", JSON.stringify(config));
}

function getEquipSlots() {
    const main = getMainExt();
    if (!main) return ["head", "chest", "hand", "leg", "foot"];
    try {
        const slots = JSON.parse(mainStorGet("equipment_slots") || "[]");
        return slots.length > 0 ? slots : ["head", "chest", "hand", "leg", "foot"];
    } catch(e) {
        return ["head", "chest", "hand", "leg", "foot"];
    }
}

function saveEquipSlots(slots) {
    const main = getMainExt();
    if (main) mainStorSet("equipment_slots", JSON.stringify(slots));
}

function getSlotDisplayNames() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return JSON.parse(mainStorGet("equipment_slot_names") || "{}");
    } catch(e) {
        return {};
    }
}

function saveSlotDisplayNames(names) {
    const main = getMainExt();
    if (main) mainStorSet("equipment_slot_names", JSON.stringify(names));
}

function getSlotDisplayName(slot) {
    const names = getSlotDisplayNames();
    return names[slot] || slot;
}

function getPlayerEquips(roleKey) {
    const main = getMainExt();
    if (!main) return null;
    try {
        const data = JSON.parse(mainStorGet("player_equipments") || "{}");
        if (!data[roleKey]) {
            const slots = getEquipSlots();
            data[roleKey] = {};
            slots.forEach(slot => {
                data[roleKey][slot] = null;
            });
            mainStorSet("player_equipments", JSON.stringify(data));
        }
        return data[roleKey];
    } catch(e) { return null; }
}

function savePlayerEquips(roleKey, equips) {
    const main = getMainExt();
    if (!main) return;
    try {
        const data = JSON.parse(mainStorGet("player_equipments") || "{}");
        data[roleKey] = equips;
        mainStorSet("player_equipments", JSON.stringify(data));
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

function getEquipBonus(equip) {
    if (!equip || !equip.baseAttrs) return {};

    const bonus = {};
    for (const attr in equip.baseAttrs) {
        bonus[attr] = equip.baseAttrs[attr];
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

        const bonus = getEquipBonus(equip);
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
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 获取roleKey
    const parts = msg.sender.userId.split(':');
    const platform = parts[0];
    const rawUid = parts[1];
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;

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
                    const bonus = getEquipBonus(equip);
                    const bonusStr = Object.entries(bonus).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join(',');
                    info += `${getSlotEmoji(slot)} ${getSlotName(slot)}: ${equip.name} (${bonusStr})\n`;
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

        equips[slot] = { code: equip.code };
        savePlayerEquips(roleKey, equips);

        let msg_text = `✅ 你穿上了 ${equip.name}！\n\n`;
        const bonus = getEquipBonus(equip);
        const bonusStr = Object.entries(bonus).map(([k, v]) => `${k}+${v}`).join(', ');
        msg_text += `属性加成: ${bonusStr}`;

        if (oldEquip && oldEquip.code && registry[oldEquip.code]) {
            msg_text += `\n\n(原装备 ${registry[oldEquip.code].name} 已卸下)`;
        }

        return seal.replyToSender(ctx, msg, msg_text);
    }

    // 列表
    if (subCmd === "列表" || subCmd === "列表") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

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
    const rawUid = parts[1];
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;

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
// 装备系统 - 管理员命令：注册装备
// ========================

let cmd_register_equip = seal.ext.newCmdItemInfo();
cmd_register_equip.name = "注册装备";
cmd_register_equip.help = "【管理员】注册新装备\n注册装备 <装备名>*<描述>*<槽位>*<基础属性>\n\n属性格式: ATK+15,DEF+10 (用逗号分隔多个属性)\n属性必须已注册，执行「我创建属性」可注册新属性\n槽位：执行「槽位 查看」查看所有可用槽位\n\n示例:\n注册装备 铁制短剑*普通短剑*hand*ATK+15\n注册装备 钢铁胸甲*防御胸甲*chest*DEF+20,HP+50\n注册装备 智者法杖*法术武器*hand*智力+20,MP+50";
cmd_register_equip.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const input = cmdArgs.args.slice(1).join(' ').trim();

    const parts = input.split(/[*]/);
    if (parts.length < 4) {
        return seal.replyToSender(ctx, msg, "❌ 参数不足。格式: 装备名*描述*槽位*基础属性");
    }

    const name = parts[0].trim();
    const desc = parts[1].trim();
    const slot = parts[2].trim();
    const baseAttrStr = parts[3].trim();

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

    if (Object.keys(baseAttrs).length === 0) {
        return seal.replyToSender(ctx, msg, "❌ 基础属性格式错误。格式: ATK+15,DEF+10");
    }

    // 验证所有属性是否已注册
    const attrDefs = getAttrDefs();
    const allAttrNames = new Set([...Object.keys(baseAttrs)]);

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
        baseAttrs: baseAttrs
    };

    saveEquipRegistry(registry);

    let msg_text = `✅ 装备已注册！\n\n`;
    msg_text += `代码: ${code}\n`;
    msg_text += `名称: ${name}\n`;
    msg_text += `槽位: ${getSlotName(slot)}\n`;
    msg_text += `基础属性: ${Object.entries(baseAttrs).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join(', ')}\n`;

    return seal.replyToSender(ctx, msg, msg_text);
};

ext.cmdMap["注册装备"] = cmd_register_equip;

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
        const main = getMainExt();
        if (main) {
            try {
                const data = JSON.parse(mainStorGet("player_equipments") || "{}");
                for (const roleKey in data) {
                    delete data[roleKey][slotCode];
                }
                mainStorSet("player_equipments", JSON.stringify(data));
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

// ========================
// 升级系统 (PlayerLevel)
// ========================

// 获取升级规则
function getLevelUpRules() {
    const main = getMainExt();
    return main ? JSON.parse(mainStorGet("level_up_rules") || '{"max_level":100,"enabled":true,"level_up_rules":{}}') : {};
}

function saveLevelUpRules(rules) {
    const main = getMainExt();
    if (main) mainStorSet("level_up_rules", JSON.stringify(rules));
}

// 获取玩家当前等级（新结构：uid 为 key）
function getPlayerLevel(uid) {
    const main = getMainExt();
    if (!main) return 1;
    const data = JSON.parse(mainStorGet("player_level") || "{}");
    return data[uid] || 1;
}

function setPlayerLevel(uid, level) {
    const main = getMainExt();
    if (!main) return;
    const data = JSON.parse(mainStorGet("player_level") || "{}");
    data[uid] = level;
    mainStorSet("player_level", JSON.stringify(data));
}

// 获取玩家升级历史（新结构：uid 为 key）
function getLevelHistory(uid) {
    const main = getMainExt();
    if (!main) return [];
    const data = JSON.parse(mainStorGet("player_level_history") || "{}");
    return data[uid] || [];
}

function addLevelHistory(uid, record) {
    const main = getMainExt();
    if (!main) return;
    const data = JSON.parse(mainStorGet("player_level_history") || "{}");
    if (!data[uid]) data[uid] = [];
    data[uid].push(record);
    mainStorSet("player_level_history", JSON.stringify(data));
}

// 递增公式：基础 + (级数-1) × 增幅
function calculateValue(baseStr, level) {
    if (!baseStr.includes('+')) return parseInt(baseStr) || 0;
    const [base, increment] = baseStr.split('+').map(x => parseFloat(x) || 0);
    return Math.floor(base + (level - 1) * increment);
}

// 替换描述中的 {等级}
function replaceDescTemplate(desc, level) {
    return desc.replace(/{等级}/g, level);
}

// 解析消耗品/奖励品字符串
// `:` 格式 → 货币/物品/属性，存 code（货币和物品）或名（属性）
// `+` 格式 → 属性增量奖励，存 { attrs: { attrName: qty } }（仅用于奖励字段）
// 返回 { result, errors }；errors 非空说明有未知名称
function parseConsumables(str, level) {
    if (!str || str.trim() === '') return { result: {}, errors: [] };
    const result = {};
    const errors = [];
    const entries = str.split(',').map(s => s.trim()).filter(s => s);

    const itemReg = getRegistry();
    const attrDefs = getAttrDefs();
    const currencyByName = {};
    const itemByName = {};
    for (const [code, info] of Object.entries(itemReg)) {
        if (info.type === "currency") currencyByName[info.name] = code;
        else itemByName[info.name] = code;
    }

    entries.forEach(entry => {
        if (entry.includes(':')) {
            const colonIdx = entry.indexOf(':');
            const name = entry.slice(0, colonIdx).trim();
            const value = entry.slice(colonIdx + 1).trim();
            const actualValue = calculateValue(value, level);

            // 货币优先，其次物品，再次属性
            if (currencyByName[name]) {
                if (!result.currencies) result.currencies = {};
                result.currencies[currencyByName[name]] = actualValue;
            } else if (itemByName[name]) {
                if (!result.items) result.items = {};
                result.items[itemByName[name]] = actualValue;
            } else if (attrDefs[name]) {
                if (!result.attributes) result.attributes = {};
                result.attributes[name] = actualValue;
            } else {
                errors.push(`「${name}」不是已注册的物品、货币或属性`);
            }
        } else if (entry.includes('+')) {
            // `+` 格式仅用于奖励字段（属性增量），消耗字段不应出现
            const plusIdx = entry.indexOf('+');
            const name = entry.slice(0, plusIdx).trim();
            const value = entry.slice(plusIdx + 1).trim();
            const actualValue = calculateValue(value, level);
            if (!result.attrs) result.attrs = {};
            result.attrs[name] = actualValue;
        } else {
            errors.push(`「${entry}」格式无法识别（应为 名称:数量 或 属性名+数值）`);
        }
    });

    return { result, errors };
}

// 展开等级范围 "1-50" → [1, 2, ..., 50]
function expandLevelRange(rangeStr) {
    if (!rangeStr.includes('-')) return [parseInt(rangeStr)];
    const [start, end] = rangeStr.split('-').map(x => parseInt(x));
    const levels = [];
    for (let i = start; i <= end; i++) levels.push(i);
    return levels;
}

// 上传升级等级命令
function cmd_upload_level_rule(msg, cmdArgs, ctx) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 未找到主插件");

    const rest = cmdArgs.args.slice(1).join(' ').trim();
    const parts = rest.split('*').map(p => p.trim());

    // 格式：等级范围 * 描述 * 消耗品 * 奖励品 [* 成功率]，共至少4段
    if (parts.length < 4) {
        return seal.replyToSender(ctx, msg, "❌ 格式错误\n格式：上传升级等级 <等级|范围> * <描述> * <消耗品> * <奖励品> [*成功率]\n消耗品格式：物品名:数量 或 物品名:基础+增幅（无消耗填-）\n奖励品格式：属性名+数值 或 物品名:数量（无奖励填-）\n示例：\n  上传升级等级 1-10 * {等级}级冒险者 * 金币:50+50 * HP+5+5\n  上传升级等级 20 * 传奇战士 * 金币:1000,晶体:3 * ATK+20,DEF+10 * 80");
    }

    const levelRange = parts[0];
    const description = parts[1];
    const consumablesStr = parts[2] === '-' ? '' : parts[2];
    const rewardsStr = parts[3] === '-' ? '' : parts[3];
    const successRate = parts[4] ? Math.max(0, Math.min(100, parseInt(parts[4]) || 100)) : 100;

    const levels = expandLevelRange(levelRange);
    if (!levels.length || levels.some(isNaN)) {
        return seal.replyToSender(ctx, msg, `❌ 等级范围「${levelRange}」无法解析`);
    }

    // 用第一个等级做配置时校验（捕获名称错误）
    const consumeCheck = parseConsumables(consumablesStr, levels[0]);
    const rewardCheck = parseConsumables(rewardsStr, levels[0]);

    // 消耗品字段出现 + 格式（属性增量），属于误用
    const consumeWrongFmt = consumablesStr.split(',').map(s => s.trim()).filter(s => s && s.includes('+') && !s.includes(':'));
    const allErrors = [
        ...consumeCheck.errors.map(e => `消耗品：${e}`),
        ...rewardCheck.errors.map(e => `奖励品：${e}`),
        ...consumeWrongFmt.map(s => `消耗品：「${s}」请用 名称:数量 格式，+格式仅限奖励品`),
    ];
    if (allErrors.length) {
        return seal.replyToSender(ctx, msg, `❌ 配置校验失败：\n${allErrors.join("\n")}`);
    }

    const rules = getLevelUpRules();
    if (!rules.level_up_rules) rules.level_up_rules = {};

    // 成功率：范围时首级100%线性递减至末级 successRate%，单级直接用
    let successRates = {};
    if (successRate < 100 && successRate > 0 && levels.length > 1) {
        const step = (100 - successRate) / (levels.length - 1);
        levels.forEach((lv, idx) => { successRates[lv] = Math.floor(100 - idx * step); });
    } else {
        levels.forEach(lv => { successRates[lv] = successRate; });
    }

    // 为每个等级创建配置
    levels.forEach(level => {
        const desc = replaceDescTemplate(description, level);
        const { result: consume } = parseConsumables(consumablesStr, level);
        const { result: reward } = parseConsumables(rewardsStr, level);
        rules.level_up_rules[level] = {
            description: desc,
            consume,
            rewards: reward,
            success_rate: successRates[level] ?? 100,
        };
    });

    saveLevelUpRules(rules);

    const rangeLabel = levels.length > 1 ? `等级 ${levels[0]}-${levels[levels.length-1]}` : `等级 ${levels[0]}`;
    return seal.replyToSender(ctx, msg, `✅ 已配置 ${levels.length} 个升级规则（${rangeLabel}）`);
}

// 查看升级配置
function cmd_view_level_rule(ctx, msg, cmdArgs) {
    const levelStr = cmdArgs.getArgN(2);
    if (!levelStr) {
        const rules = getLevelUpRules();
        const levels = Object.keys(rules.level_up_rules || {}).sort((a,b) => parseInt(a) - parseInt(b));
        const levelCount = levels.length;
        const maxLevel = rules.max_level || 100;
        const rangeStr = levelCount > 0 ? `${levels[0]}-${levels[levels.length-1]}` : "（暂无）";
        return seal.replyToSender(ctx, msg, `📊 升级系统配置\n\n最大等级: ${maxLevel}\n已配置等级: ${levelCount}个\n等级范围: ${rangeStr}`);
    }

    const level = parseInt(levelStr);
    const rules = getLevelUpRules();
    const rule = rules.level_up_rules[level];

    if (!rule) {
        return seal.replyToSender(ctx, msg, `❌ 等级 ${level} 未配置`);
    }

    const viewReg = getRegistry();
    const cname = (code) => viewReg[code]?.name || code;

    let msg_text = `📋 等级 ${level}: ${rule.description}\n\n`;
    msg_text += `消耗品:\n`;
    if (rule.consume.items) Object.entries(rule.consume.items).forEach(([code, qty]) => { msg_text += `  · ${cname(code)}: ${qty}\n`; });
    if (rule.consume.currencies) Object.entries(rule.consume.currencies).forEach(([code, qty]) => { msg_text += `  · ${cname(code)}: ${qty}\n`; });
    if (rule.consume.attributes) Object.entries(rule.consume.attributes).forEach(([name, qty]) => { msg_text += `  · ${name}: ${qty}\n`; });
    if (!rule.consume.items && !rule.consume.currencies && !rule.consume.attributes) msg_text += `  · (无)\n`;

    msg_text += `\n奖励品:\n`;
    if (rule.rewards.attrs) Object.entries(rule.rewards.attrs).forEach(([attr, val]) => { msg_text += `  · ${attr}+${val}\n`; });
    if (rule.rewards.currencies) Object.entries(rule.rewards.currencies).forEach(([code, qty]) => { msg_text += `  · ${cname(code)}: ${qty}\n`; });
    if (rule.rewards.items) Object.entries(rule.rewards.items).forEach(([code, qty]) => { msg_text += `  · ${cname(code)}: ${qty}\n`; });
    if (!rule.rewards.attrs && !rule.rewards.currencies && !rule.rewards.items) msg_text += `  · (无)\n`;

    msg_text += `\n成功率: ${rule.success_rate}%`;

    return seal.replyToSender(ctx, msg, msg_text);
}

// 升级列表
function cmd_level_list(ctx, msg, cmdArgs) {
    const rules = getLevelUpRules();
    const levels = Object.keys(rules.level_up_rules || {}).sort((a,b) => parseInt(a) - parseInt(b));

    if (levels.length === 0) {
        return seal.replyToSender(ctx, msg, "❌ 尚未配置任何升级等级");
    }

    let msg_text = `📜 升级等级列表 (共 ${levels.length} 级)\n\n`;
    levels.forEach(lv => {
        const rule = rules.level_up_rules[lv];
        msg_text += `${lv}. ${rule.description}\n`;
    });

    return seal.replyToSender(ctx, msg, msg_text);
}

// 检查玩家是否满足消耗条件（items/currencies 以 code 为 key）
function checkConsumables(uid, roleKey, consume) {
    const playerAttrs = (getCharAttrs()[uid]) || {};
    const reg = getRegistry();

    if (consume.attributes) {
        for (const [attrName, required] of Object.entries(consume.attributes)) {
            const current = playerAttrs[attrName] || 0;
            if (current < required)
                return { ok: false, reason: `${attrName}不足（需要${required}，当前${current}）` };
        }
    }

    if (consume.currencies) {
        for (const [code, required] of Object.entries(consume.currencies)) {
            const name = reg[code]?.name || code;
            const current = getInvCount(roleKey, code) || 0;
            if (current < required)
                return { ok: false, reason: `${name}不足（需要${required}，当前${current}）` };
        }
    }

    if (consume.items) {
        for (const [code, required] of Object.entries(consume.items)) {
            const name = reg[code]?.name || code;
            const current = getInvCount(roleKey, code) || 0;
            if (current < required)
                return { ok: false, reason: `${name}不足（需要${required}，当前${current}）` };
        }
    }

    return { ok: true };
}

// 消耗资源（items/currencies 以 code 为 key）
function consumeResources(uid, roleKey, consume) {
    if (consume.attributes) {
        const charAttrs = getCharAttrs();
        if (!charAttrs[uid]) charAttrs[uid] = {};
        for (const [attrName, amount] of Object.entries(consume.attributes))
            charAttrs[uid][attrName] = (charAttrs[uid][attrName] || 0) - amount;
        saveCharAttrs(charAttrs);
    }

    if (consume.currencies) {
        for (const [code, amount] of Object.entries(consume.currencies))
            removeFromInv(roleKey, code, amount);
    }

    if (consume.items) {
        for (const [code, amount] of Object.entries(consume.items))
            removeFromInv(roleKey, code, amount);
    }
}

// 发放奖励（items/currencies 以 code 为 key，属性增量在 attrs）
function grantRewards(uid, roleKey, rewards) {
    if (rewards.attrs) {
        const charAttrs = getCharAttrs();
        if (!charAttrs[uid]) charAttrs[uid] = {};
        for (const [attrName, amount] of Object.entries(rewards.attrs))
            charAttrs[uid][attrName] = (charAttrs[uid][attrName] || 0) + amount;
        saveCharAttrs(charAttrs);
    }

    if (rewards.currencies) {
        for (const [code, amount] of Object.entries(rewards.currencies))
            addToInv(roleKey, code, amount);
    }

    if (rewards.items) {
        for (const [code, amount] of Object.entries(rewards.items))
            addToInv(roleKey, code, amount);
    }
}

// 玩家升级命令
function cmd_do_levelup(msg, cmdArgs, ctx) {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) {
        return seal.replyToSender(ctx, msg, "❌ 无法识别角色");
    }

    const rules = getLevelUpRules();
    if (!rules.enabled) {
        return seal.replyToSender(ctx, msg, "❌ 升级系统已关闭");
    }

    const main = getMainExt();
    const combatPlatform = msg.platform;
    const combatRawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const combatUid = getPrimaryUid(combatPlatform, combatRawUid);
    const roleKey = `${combatPlatform}:${combatUid}`;
    const curLevel = getPlayerLevel(combatUid);
    const maxLevel = rules.max_level || 100;

    if (curLevel >= maxLevel) {
        return seal.replyToSender(ctx, msg, `✨ 您已达到最高等级 ${maxLevel}`);
    }

    const nextLevel = curLevel + 1;
    const rule = rules.level_up_rules[nextLevel];

    if (!rule) {
        return seal.replyToSender(ctx, msg, `⚠️ 等级 ${nextLevel} 尚未配置`);
    }

    // 检查消耗品
    const checkResult = checkConsumables(combatUid, roleKey, rule.consume);
    if (!checkResult.ok) {
        return seal.replyToSender(ctx, msg, `❌ 升级失败！\n${checkResult.reason}`);
    }

    // 判断成功率
    const successRate = rule.success_rate || 100;
    const isSuccess = Math.random() * 100 < successRate;

    if (!isSuccess) {
        consumeResources(combatUid, roleKey, rule.consume);
        addLevelHistory(combatUid, {
            timestamp: new Date().toLocaleString(),
            from_level: curLevel,
            to_level: nextLevel,
            success: false,
            consumed: rule.consume,
            reason: "升级失败"
        });
        return seal.replyToSender(ctx, msg, `❌ 升级失败！\n消耗已扣除（成功率${successRate}%）`);
    }

    // 升级成功：消耗资源
    consumeResources(combatUid, roleKey, rule.consume);

    // 发放奖励
    grantRewards(combatUid, roleKey, rule.rewards);

    // 提升等级
    setPlayerLevel(combatUid, nextLevel);

    // 记录历史
    addLevelHistory(combatUid, {
        timestamp: new Date().toLocaleString(),
        from_level: curLevel,
        to_level: nextLevel,
        success: true,
        consumed: rule.consume,
        gained: rule.rewards
    });

    // 返回成功消息
    let msg_text = `✅ 恭喜！升级成功！\n\n`;
    msg_text += `${rule.description}\n`;
    msg_text += `等级: ${curLevel} → ${nextLevel}\n\n`;

    const succReg = getRegistry();
    const scname = (code) => succReg[code]?.name || code;
    if (rule.rewards.attrs) {
        msg_text += `获得属性:\n`;
        Object.entries(rule.rewards.attrs).forEach(([attr, val]) => { msg_text += `  · ${attr}+${val}\n`; });
    }
    if (rule.rewards.currencies) {
        msg_text += `获得货币:\n`;
        Object.entries(rule.rewards.currencies).forEach(([code, val]) => { msg_text += `  · ${scname(code)}×${val}\n`; });
    }
    if (rule.rewards.items) {
        msg_text += `获得物品:\n`;
        Object.entries(rule.rewards.items).forEach(([code, val]) => { msg_text += `  · ${scname(code)}×${val}\n`; });
    }

    return seal.replyToSender(ctx, msg, msg_text);
}

// 查看升级信息
function cmd_levelup_info(msg, cmdArgs, ctx) {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) {
        return seal.replyToSender(ctx, msg, "❌ 无法识别角色");
    }

    const infoUid = getPrimaryUid(msg.platform, msg.sender.userId.replace(/^[a-z]+:/i, ""));
    const curLevel = getPlayerLevel(infoUid);
    const rules = getLevelUpRules();
    const nextLevel = curLevel + 1;
    const maxLevel = rules.max_level || 100;

    let msg_text = `📊 升级信息\n\n`;
    msg_text += `当前等级: ${curLevel}\n`;
    msg_text += `最大等级: ${maxLevel}\n\n`;

    if (curLevel >= maxLevel) {
        msg_text += `✨ 您已达到最高等级！`;
    } else {
        const rule = rules.level_up_rules[nextLevel];
        if (rule) {
            msg_text += `下一等级: ${nextLevel} - ${rule.description}\n\n`;
            const infoReg = getRegistry();
            const icname = (code) => infoReg[code]?.name || code;
            msg_text += `升级需要:\n`;
            if (rule.consume.items) Object.entries(rule.consume.items).forEach(([code, qty]) => { msg_text += `  · ${icname(code)}: ${qty}\n`; });
            if (rule.consume.currencies) Object.entries(rule.consume.currencies).forEach(([code, qty]) => { msg_text += `  · ${icname(code)}: ${qty}\n`; });
            if (rule.consume.attributes) Object.entries(rule.consume.attributes).forEach(([name, qty]) => { msg_text += `  · 消耗${name}${qty}点\n`; });
        }
    }

    return seal.replyToSender(ctx, msg, msg_text);
}

// 创建命令对象（规范格式）
let cmd_upload_level = seal.ext.newCmdItemInfo();
cmd_upload_level.name = "上传升级等级";
cmd_upload_level.help = "【管理员】配置升级规则\n上传升级等级 <等级|范围> * <描述> * <消耗品> * <奖励品> [*成功率]\n· 等级与描述之间也用 * 分隔，共4段\n· 消耗品：物品名:数量 或 物品名:基础+增幅，无消耗填 -\n· 奖励品：属性名+数值 或 物品名:数量，无奖励填 -\n· 成功率：0-100，范围配置时从100%线性递减至该值\n示例：\n  上传升级等级 1-10 * {等级}级冒险者 * 金币:50+50 * HP+5+5\n  上传升级等级 20 * 传奇战士 * 金币:1000,晶体:3 * ATK+20,DEF+10 * 80\n  上传升级等级 5 * 铁甲武士 * - * ATK+10";
cmd_upload_level.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足");
    return cmd_upload_level_rule(msg, cmdArgs, ctx);
};
ext.cmdMap["上传升级等级"] = cmd_upload_level;

let cmd_view_level = seal.ext.newCmdItemInfo();
cmd_view_level.name = "查看升级配置";
cmd_view_level.help = "查看升级配置\n查看升级配置 [等级号]";
cmd_view_level.solve = (ctx, msg, cmdArgs) => {
    return cmd_view_level_rule(ctx, msg, cmdArgs);
};
ext.cmdMap["查看升级配置"] = cmd_view_level;

let cmd_level_listing = seal.ext.newCmdItemInfo();
cmd_level_listing.name = "升级列表";
cmd_level_listing.help = "查看所有已配置的升级等级";
cmd_level_listing.solve = (ctx, msg, cmdArgs) => {
    return cmd_level_list(ctx, msg, cmdArgs);
};
ext.cmdMap["升级列表"] = cmd_level_listing;

let cmd_do_upgrade = seal.ext.newCmdItemInfo();
cmd_do_upgrade.name = "升级";
cmd_do_upgrade.help = "升级一次\n格式：升级";
cmd_do_upgrade.solve = (ctx, msg, cmdArgs) => {
    return cmd_do_levelup(msg, cmdArgs, ctx);
};
ext.cmdMap["升级"] = cmd_do_upgrade;

let cmd_level_info = seal.ext.newCmdItemInfo();
cmd_level_info.name = "查看升级信息";
cmd_level_info.help = "查看升级进度和下一等级要求\n格式：查看升级信息";
cmd_level_info.solve = (ctx, msg, cmdArgs) => {
    return cmd_levelup_info(msg, cmdArgs, ctx);
};
ext.cmdMap["查看升级信息"] = cmd_level_info;

let cmd_level_history = seal.ext.newCmdItemInfo();
cmd_level_history.name = "升级历史";
cmd_level_history.help = "查看自己的升级历史\n升级历史 [最近N条，默认10]";
cmd_level_history.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(/^[a-z]+:/i, ""));
    const limit = Math.min(parseInt(cmdArgs.getArgN(1)) || 10, 50);
    const history = getLevelHistory(uid);
    if (!history.length) return seal.replyToSender(ctx, msg, "📜 暂无升级记录。");
    const recent = history.slice(-limit).reverse();
    const lines = recent.map(r => {
        const icon = r.success ? "✅" : "❌";
        return `${icon} ${r.timestamp}  Lv.${r.from_level} → ${r.success ? `Lv.${r.to_level}` : `Lv.${r.from_level}（失败）`}`;
    });
    seal.replyToSender(ctx, msg, `📜 升级历史（最近${recent.length}条）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["升级历史"] = cmd_level_history;

let cmd_level_settings = seal.ext.newCmdItemInfo();
cmd_level_settings.name = "升级系统设置";
cmd_level_settings.help = "【管理员】升级系统全局设置\n升级系统设置 开启|关闭\n升级系统设置 最大等级 <数字>";
cmd_level_settings.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    if (!arg1) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const rules = getLevelUpRules();
    if (arg1 === "开启") {
        rules.enabled = true;
        saveLevelUpRules(rules);
        return seal.replyToSender(ctx, msg, "✅ 升级系统已开启。");
    }
    if (arg1 === "关闭") {
        rules.enabled = false;
        saveLevelUpRules(rules);
        return seal.replyToSender(ctx, msg, "✅ 升级系统已关闭。");
    }
    if (arg1 === "最大等级") {
        const n = parseInt(arg2);
        if (isNaN(n) || n < 1) return seal.replyToSender(ctx, msg, "❌ 最大等级必须为正整数。");
        rules.max_level = n;
        saveLevelUpRules(rules);
        return seal.replyToSender(ctx, msg, `✅ 最大等级已设为 ${n}。`);
    }
    const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r;
};
ext.cmdMap["升级系统设置"] = cmd_level_settings;

// ========================
// 角色档案
// ========================
let cmd_profile = seal.ext.newCmdItemInfo();
cmd_profile.name = "角色档案";
cmd_profile.help = "【管理员】查看角色综合档案\n角色档案 角色名";
cmd_profile.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const roleName = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const platform = msg.platform;
    const uid = getRoleUid(platform, roleName);
    if (!uid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const primaryUid = getPrimaryUid(platform, uid);
    const roleKey = `${platform}:${primaryUid}`;

    // 属性
    const defs = getAttrDefs();
    const allAttrs = getCharAttrs();
    const myAttrs = allAttrs[primaryUid] || {};
    const attrStr = Object.keys(defs).length
        ? Object.keys(defs).map(k => `${k}: ${myAttrs[k] ?? defs[k].default ?? 0}`).join(" | ")
        : "暂无属性";

    // 背包
    const reg = getRegistry();
    const inv = getInv(roleKey);
    const invStr = inv.length
        ? inv.map(e => `${reg[e.code]?.name || e.code} ×${e.count}`).join(" | ")
        : "空";

    // 关系线（读主插件存储）
    let relCount = 0, initiated = 0, received = 0, confirmed = 0;
    try {
        const relData = JSON.parse(mainStorGet("relationship_lines") || "{}");
        const myRels = relData[platform]?.[uid] || {};
        relCount = Object.keys(myRels).length;
        for (const rel of Object.values(myRels)) {
            if (rel.confirmed) confirmed++;
            if (rel.initiator === roleName) initiated++; else received++;
        }
    } catch(e) {}

    const lines = [
        `📋 角色档案：${roleName}`,
        ``,
        `【属性】${attrStr}`,
        ``,
        `【关系线】共 ${relCount} 条（发起 ${initiated} / 收到 ${received} / 已确认 ${confirmed}）`,
        ``,
        `【背包】${invStr}`,
    ];
    seal.replyToSender(ctx, msg, lines.join('\n'));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["角色档案"] = cmd_profile;

// ========================
// 批量发放
// ========================
let cmd_batch_give = seal.ext.newCmdItemInfo();
cmd_batch_give.name = "批量发放";
cmd_batch_give.help = "【管理员】批量发放物品\n批量发放 物品码/名 +N 角色1 角色2 ...\n批量发放 物品码/名 +N 全员";
cmd_batch_give.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const inputCode = cmdArgs.getArgN(1);
    const deltaStr = cmdArgs.getArgN(2);
    const firstTarget = cmdArgs.getArgN(3);
    if (!inputCode || !deltaStr || !firstTarget) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const delta = parseInt(deltaStr);
    if (isNaN(delta) || delta <= 0) return seal.replyToSender(ctx, msg, "❌ 数量必须为正整数，示例：+3");
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const reg = getRegistry();
    const item = findItem(reg, inputCode);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${inputCode}」`);
    const platform = msg.platform;

    let targets = [];
    if (firstTarget === "全员") {
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        targets = Object.values(apg[platform] || {}).map(v => v[0]).filter(Boolean);
    } else {
        let i = 3;
        while (cmdArgs.getArgN(i)) { targets.push(cmdArgs.getArgN(i)); i++; }
    }
    if (!targets.length) return seal.replyToSender(ctx, msg, "❌ 未找到目标角色。");

    const errs = [];
    for (const name of targets) {
        const uid = getRoleUid(platform, name);
        if (!uid) { errs.push(name); continue; }
        addToInv(`${platform}:${getPrimaryUid(platform, uid)}`, item.code, delta);
        notifyPlayer(ctx, platform, name, `📦【背包更新】${item.name} ×${delta} 已加入你的背包。`);
    }

    const ok = targets.length - errs.length;
    let reply = `📦 批量发放 [${item.code}]${item.name} ×${delta}（共 ${targets.length} 人）：成功 ${ok} | 失败 ${errs.length}`;
    if (errs.length) reply += `\n找不到角色：${errs.join("、")}`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["批量发放"] = cmd_batch_give;

// ========================
// 定时收集
// ========================

function getCollections() {
    return JSON.parse(ext.storageGet("scheduled_collections") || "{}");
}
function saveCollections(cols) {
    ext.storageSet("scheduled_collections", JSON.stringify(cols));
}

function getSafeEndPointRPG(platform) {
    const eps = seal.getEndPoints();
    if (!eps || !eps.length) return null;
    return eps.find(e => e.platform === platform && e.state === 1) || eps.find(e => e.state === 1) || eps[0];
}

function sendToAdminGroupRPG(platform, text) {
    const main = getMainExt();
    if (!main) return;
    const gid = JSON.parse(mainStorGet("adminAnnounceGroupId") || "null");
    if (!gid) return;
    try {
        const ep = getSafeEndPointRPG(platform);
        if (!ep) return;
        const m = seal.newMessage();
        m.messageType = "group";
        m.groupId = `${platform}-Group:${gid}`;
        seal.replyToSender(seal.createTempCtx(ep, m), m, text);
    } catch (e) { console.error("[定时收集] sendToAdminGroup:", e.message); }
}

// withAt=true 时在每个玩家的私人群里单独艾特该玩家
function broadcastToAllPlayerGroups(platform, text, withAt) {
    const main = getMainExt();
    if (!main) return;
    const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
    const groups = apg[platform] || {};
    if (withAt) {
        // 按群分组，每个玩家各自收到艾特
        Object.entries(groups).forEach(([uid, info]) => {
            const gid = info[1];
            if (!gid) return;
            try {
                const ep = getSafeEndPointRPG(platform);
                if (!ep) return;
                const m = seal.newMessage();
                m.messageType = "group";
                m.groupId = `${platform}-Group:${gid}`;
                seal.replyToSender(seal.createTempCtx(ep, m), m, `[CQ:at,qq=${uid}]\n${text}`);
            } catch (e) { console.error("[定时收集] broadcast at:", e.message); }
        });
    } else {
        const gids = [...new Set(Object.values(groups).map(v => v[1]).filter(Boolean))];
        gids.forEach(gid => {
            try {
                const ep = getSafeEndPointRPG(platform);
                if (!ep) return;
                const m = seal.newMessage();
                m.messageType = "group";
                m.groupId = `${platform}-Group:${gid}`;
                seal.replyToSender(seal.createTempCtx(ep, m), m, text);
            } catch (e) { console.error("[定时收集] broadcast:", e.message); }
        });
    }
}

// 解析时间字符串，支持 "2000" / "20:00" 两种格式，返回 { h, m } 或 null
function parseCollectionTime(str) {
    str = str.trim();
    let h, m;
    if (/^\d{3,4}$/.test(str)) {
        // 2000 → 20:00, 900 → 9:00
        h = parseInt(str.slice(0, -2));
        m = parseInt(str.slice(-2));
    } else if (/^\d{1,2}:\d{2}$/.test(str)) {
        [h, m] = str.split(":").map(Number);
    } else {
        return null;
    }
    if (h < 0 || h > 23 || m < 0 || m > 59) return null;
    return { h, m };
}

function formatHM(h, m) {
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

// 每分钟只激活一次，避免重复触发
let _collectionLastMinute = -1;
let _collectionTimer = null;

function registerCollectionTimer() {
    if (_collectionTimer) clearInterval(_collectionTimer);
    _collectionTimer = setInterval(() => {
        const now = new Date();
        const h = now.getHours(), mn = now.getMinutes();
        const currentTotal = h * 60 + mn;
        if (currentTotal === _collectionLastMinute) return;
        _collectionLastMinute = currentTotal;

        const cols = getCollections();
        let changed = false;
        for (const name in cols) {
            const col = cols[name];
            if (col.active) continue;
            const targetTotal = col.h * 60 + col.m;
            // 使用取模处理跨午夜情况，diff 为正表示还有多少分钟
            const diff = ((targetTotal - currentTotal) + 1440) % 1440;
            const timeStr = formatHM(col.h, col.m);

            // diff===0 为准点触发；diff>1438 覆盖 bot 重启导致跳过目标分钟的场景（最多容错2分钟）
            if (diff === 0 || diff >= 1438) {
                col.active = true;
                changed = true;
                broadcastToAllPlayerGroups("QQ", `📋【收集开启】「${name}」现已开始收集！\n请使用：定时收集 ${name} 你的内容`, true);
                sendToAdminGroupRPG("QQ", `📋【收集开启】「${name}」已于 ${timeStr} 开启。`);
            } else if (diff === 30 && !col.reminded30) {
                col.reminded30 = true;
                changed = true;
                broadcastToAllPlayerGroups("QQ", `⏰【收集预告】「${name}」将于 ${timeStr}（30分钟后）开始收集，请提前准备！`, true);
            } else if (diff === 10 && !col.reminded10) {
                col.reminded10 = true;
                changed = true;
                broadcastToAllPlayerGroups("QQ", `⏰【收集预告】「${name}」将于 ${timeStr}（10分钟后）开始收集！`, true);
            } else if (diff === 5 && !col.reminded5) {
                col.reminded5 = true;
                changed = true;
                broadcastToAllPlayerGroups("QQ", `⏰【收集预告】「${name}」将于 ${timeStr}（5分钟后）开始收集，马上就到！`, true);
            }
        }
        if (changed) saveCollections(cols);
    }, 30000);
}

ext.onLoad = () => { registerCollectionTimer(); };

// 管理员：创建定时收集
let cmd_collection_create = seal.ext.newCmdItemInfo();
cmd_collection_create.name = "创建定时收集";
cmd_collection_create.help = "【管理员】创建定时收集\n创建定时收集 时间 项目名字\n时间格式：2000 或 20:00\n示例：创建定时收集 2000 心情调查";
cmd_collection_create.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const timeStr = cmdArgs.getArgN(1);
    const name = cmdArgs.getArgN(2);
    if (!timeStr || !name) {
        const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r;
    }
    const t = parseCollectionTime(timeStr);
    if (!t) return seal.replyToSender(ctx, msg, "❌ 时间格式无效，请使用 2000 或 20:00。");
    const cols = getCollections();
    if (cols[name]) return seal.replyToSender(ctx, msg, `⚠️ 「${name}」已存在，请先用「关闭定时收集 ${name}」删除再创建。`);
    cols[name] = { name, h: t.h, m: t.m, active: false, createdAt: Date.now(), submissions: [] };
    saveCollections(cols);
    seal.replyToSender(ctx, msg, `✅ 定时收集「${name}」已创建，将于 ${formatHM(t.h, t.m)} 自动开启。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建定时收集"] = cmd_collection_create;

// 管理员：关闭定时收集
let cmd_collection_close = seal.ext.newCmdItemInfo();
cmd_collection_close.name = "关闭定时收集";
cmd_collection_close.help = "【管理员】关闭并删除定时收集\n关闭定时收集 项目名字";
cmd_collection_close.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const name = cmdArgs.getArgN(1);
    if (!name) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const cols = getCollections();
    if (!cols[name]) return seal.replyToSender(ctx, msg, `❌ 找不到收集「${name}」。`);
    delete cols[name];
    saveCollections(cols);
    seal.replyToSender(ctx, msg, `✅ 定时收集「${name}」已关闭。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["关闭定时收集"] = cmd_collection_close;

// 管理员：查看定时收集（无参数=列表，有参数=查看提交内容）
let cmd_collection_list = seal.ext.newCmdItemInfo();
cmd_collection_list.name = "查看定时收集";
cmd_collection_list.help = "【管理员】查看定时收集\n查看定时收集          — 列出所有收集\n查看定时收集 项目名字  — 查看该项目的提交记录";
cmd_collection_list.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const cols = getCollections();
    const name = cmdArgs.getArgN(1);

    if (!name) {
        const keys = Object.keys(cols);
        if (!keys.length) return seal.replyToSender(ctx, msg, "📋 当前没有定时收集。");
        const lines = keys.map(n => {
            const c = cols[n];
            const count = (c.submissions || []).length;
            return `· ${n}（${formatHM(c.h, c.m)} 开启）${c.active ? " ✅已激活" : " ⏳等待中"} | ${count} 条提交`;
        });
        seal.replyToSender(ctx, msg, `📋 定时收集列表：\n${lines.join("\n")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!cols[name]) return seal.replyToSender(ctx, msg, `❌ 找不到收集「${name}」。`);
    const subs = cols[name].submissions || [];
    if (!subs.length) return seal.replyToSender(ctx, msg, `📋「${name}」暂无提交记录。`);
    const lines = subs.map((s, i) => `${i + 1}. 【${s.roleName}】${s.time}\n   ${s.content}`);
    seal.replyToSender(ctx, msg, `📋「${name}」提交记录（共 ${subs.length} 条）：\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看定时收集"] = cmd_collection_list;

// 玩家：提交定时收集内容
let cmd_collection_submit = seal.ext.newCmdItemInfo();
cmd_collection_submit.name = "定时收集";
cmd_collection_submit.help = "提交定时收集内容\n定时收集 项目名字 内容\n示例：定时收集 心情调查 今天很开心！";
cmd_collection_submit.solve = (ctx, msg, cmdArgs) => {
    const name = cmdArgs.getArgN(1);
    if (!name) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const cols = getCollections();
    if (!cols[name]) return seal.replyToSender(ctx, msg, `❌ 找不到收集「${name}」。`);
    if (!cols[name].active) {
        const c = cols[name];
        return seal.replyToSender(ctx, msg, `⏳ 收集「${name}」尚未开启，将于 ${formatHM(c.h, c.m)} 开始。`);
    }
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 未找到你的角色信息，请确认已绑定角色。");

    // 提取内容：名字之后所有参数拼合
    let content = "";
    let i = 2;
    const parts = [];
    while (true) {
        const p = cmdArgs.getArgN(i);
        if (!p) break;
        parts.push(p);
        i++;
    }
    content = parts.join(" ").trim();
    if (!content) return seal.replyToSender(ctx, msg, "❌ 请输入收集内容。");

    const now = new Date();
    const timeStr = formatHM(now.getHours(), now.getMinutes());

    if (!cols[name].submissions) cols[name].submissions = [];
    cols[name].submissions.push({ roleName, time: timeStr, content });
    saveCollections(cols);
    seal.replyToSender(ctx, msg, `✅ 已提交「${name}」收集，谢谢！`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["定时收集"] = cmd_collection_submit;
