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

let ext = seal.ext.find('changriRPG');
if (!ext) {
    ext = seal.ext.new("changriRPG", "长日将尽", "2.0.0");
    seal.ext.register(ext);
}

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()                          { return globalThis.__changriApi || null; }
function mainStorGet(key)                  { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val)             { getApi()?.kvSetRaw(key, val); }

// JSON 对象读写：走主插件 kvGet/kvSet（带缓存与损坏容错），JSON key 一律用这两个函数
function mainKvGet(key, def) { const api = getApi(); return api ? api.kvGet(key, def) : def; }
function mainKvSet(key, val) { getApi()?.kvSet(key, val); }
function getMainStorageInt(key, def)       { return getApi()?.getStorageInt(key, def) ?? def; }
function isUserFeatureEnabled(uid, key, def = true) { return getApi()?.isUserFeatureEnabled(uid, key, def) ?? def; }
function getPrimaryUid(platform, uid)      { return getApi()?.getPrimaryUid(platform, uid) ?? uid; }
function getRoleName(ctx, msg)             { return getApi()?.getRoleName(ctx, msg) ?? null; }
function getRoleUid(platform, roleName)    { return getApi()?.getUidByRoleName(platform, roleName) ?? null; }
function isUserAdmin(ctx, msg)             { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function ws(postData, ctx, msg, ok)        { return getApi()?.ws(postData, ctx, msg, ok); }
function getSafeEndPoint(platform = "QQ") {
    const api = getApi();
    if (api) return api.getSafeEndPoint(platform);
    // 兼容独立运行：主插件未加载时走本地实现
    const eps = seal.getEndPoints();
    if (!eps || !eps.length) return null;
    return eps.find(e => e.platform === platform && e.state === 1) || eps.find(e => e.state === 1) || eps[0];
}
// 向后兼容：存储辅助函数中 getMainExt() 仅作存在性守卫
function getMainExt()                      { return getApi(); }
const isArchiveEnabled = (...a) => getApi()?.isArchiveEnabled(...a) ?? false;
const postToArchive    = (...a) => getApi()?.postToArchive(...a);

// 将长文本按空行切块，攒到 CHUNK_LEN 就切一段，供合并转发按段拆成多个节点
function chunkBagText(text) {
    const CHUNK_LEN = 300;
    const parts = [];
    let current = "";
    for (const block of text.split("\n\n")) {
        const chunk = current ? current + "\n\n" + block : block;
        if (chunk.length > CHUNK_LEN && current) {
            parts.push(current);
            current = block;
        } else {
            current = chunk;
        }
    }
    if (current) parts.push(current);
    return parts;
}

// 群聊内以合并转发发送多段内容；私聊没有合并转发能力，退化为逐条普通消息
function sendForwardOrPlain(ctx, msg, contents, nickname = "长日系统") {
    if (!contents.length) return;
    if (msg.groupId) {
        const nodes = contents.map(content => ({ type: "node", data: { name: nickname, uin: "2852199344", content } }));
        const targetGid = msg.groupId.replace(/[^\d]/g, "");
        ws({ action: "send_group_forward_msg", params: { group_id: parseInt(targetGid, 10), messages: nodes } }, ctx, msg, "");
    } else {
        for (const content of contents) seal.replyToSender(ctx, msg, content);
    }
}

// ========================
// 存储辅助
// ========================

function getRegistry() {
    const main = getMainExt();
    if (!main) return {};
    const items = mainKvGet("item_registry", {});
    const equips = mainKvGet("equipment_registry", {});
    return Object.assign({}, items, equips);
}
function saveRegistry(reg) {
    const main = getMainExt();
    if (!main) return;
    // 只保存非装备条目到 item_registry，装备由 saveEquipRegistry 单独管理
    const itemsOnly = {};
    for (const [code, item] of Object.entries(reg)) {
        if (item.type !== "equipment") itemsOnly[code] = item;
    }
    mainKvSet("item_registry", itemsOnly);
}

// RPG 属性定义：{ attrName: { min, max, default, desc } }
// 兼容迁移旧格式 sys_attr_presets (数组) 和 item_valid_attrs (数组)
function getAttrDefs() {
    const main = getMainExt();
    if (!main) return {};
    let defs = {};
    try { defs = mainKvGet("rpg_attr_defs", {}); } catch(e) { console.error("[RPG] getAttrDefs 读取 rpg_attr_defs 失败:", e.message); }
    if (!Object.keys(defs).length) {
        let migrated = false;
        for (const key of ["sys_attr_presets", "item_valid_attrs"]) {
            try {
                const arr = mainKvGet(key, []);
                if (Array.isArray(arr)) arr.forEach(n => { if (n && !defs[n]) { defs[n] = { min: null, max: null, default: 0, desc: "" }; migrated = true; } });
            } catch(e) { console.error(`[RPG] getAttrDefs 迁移旧字段 ${key} 失败:`, e.message); }
        }
        if (migrated) {
            mainKvSet("rpg_attr_defs", defs);
            mainKvSet("sys_attr_presets", Object.keys(defs));
        }
    }
    return defs;
}
function saveAttrDefs(defs) {
    const main = getMainExt();
    if (!main) return;
    mainKvSet("rpg_attr_defs", defs);
    // 保持 sys_attr_presets 同步，这样其他脚本调用时不会出错
    mainKvSet("sys_attr_presets", Object.keys(defs));
}

// 角色属性数值：{ roleName: { attrName: value } }
function getCharAttrs() {
    const main = getMainExt();
    return main ? mainKvGet("sys_character_attrs", {}) : {};
}
function saveCharAttrs(attrs) {
    const main = getMainExt();
    if (main) mainKvSet("sys_character_attrs", attrs);
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
    return main ? mainKvGet("craft_recipes", {}) : {};
}
function saveCraftRecipes(recipes) {
    const main = getMainExt();
    if (main) mainKvSet("craft_recipes", recipes);
}

function getInvAll() {
    const main = getMainExt();
    return main ? mainKvGet("global_inventories", {}) : {};
}
function saveInvAll(invs) {
    const main = getMainExt();
    if (main) mainKvSet("global_inventories", invs);
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
        const newEntry = { code, count, remainingUses: initialUses };
        if (itemInfo.durability != null && itemInfo.durability > 0) newEntry.currentDurability = itemInfo.durability;
        inv.push(newEntry);
    }

    invs[roleKey] = inv;
    saveInvAll(invs);
}
function removeFromInv(roleKey, code, count) {
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    
    // 过滤出所有符合代码的项，按次数从高到低排序，确保扣除逻辑的一致性
    let entries = inv.filter(e => e.code === code).sort((a, b) => {
        const au = a.remainingUses === -1 ? -Infinity : (a.remainingUses ?? 0);
        const bu = b.remainingUses === -1 ? -Infinity : (b.remainingUses ?? 0);
        return bu - au;
    });
    
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
    return main ? mainKvGet("pool_definitions", {}) : {};
}
function savePoolDefs(defs) {
    const main = getMainExt();
    if (main) mainKvSet("pool_definitions", defs);
}

function getDrawConfig() {
    const main = getMainExt();
    return main ? mainKvGet("pool_draw_config", {"total":2,"pools":{}}) : { total: 2, pools: {} };
}
function saveDrawConfig(cfg) {
    const main = getMainExt();
    if (main) mainKvSet("pool_draw_config", cfg);
}

function getShop() {
    const main = getMainExt();
    return main ? mainKvGet("shop_listings", []) : [];
}
function saveShop(shop) {
    const main = getMainExt();
    if (main) mainKvSet("shop_listings", shop);
    // 商城不含实时库存状态（纯配置），可以安全地立即同步回网页，
    // 不用等管理员手动「推送全部」。
    if (isArchiveEnabled()) postToArchive("/api/sync_config", { shop_listings: JSON.stringify(shop) });
}

function getMarket() {
    const main = getMainExt();
    return main ? mainKvGet("secondhand_market", {}) : {};
}
function saveMarket(market) {
    const main = getMainExt();
    if (main) mainKvSet("secondhand_market", market);
}

function getMarketConfig() {
    const main = getMainExt();
    return main ? mainKvGet("market_config", {"fee":3,"enabled":true}) : { fee: 3, enabled: true };
}
function saveMarketConfig(cfg) {
    const main = getMainExt();
    if (main) mainKvSet("market_config", cfg);
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

// 挂单里存的 currencyCode 可能因货币重新注册而失配（背包按新 code 有余额，
// 挂单却按创建时的旧 code 查询）。买卖时按 currencyName 现查一次注册表校正，
// 避免每次都要手动跑「修复商城货币」。
function resolveListingCurrencyCode(reg, listing) {
    if (reg[listing.currencyCode]?.type === "currency") return listing.currencyCode;
    const found = Object.entries(reg).find(([, info]) => info.type === "currency" && info.name === listing.currencyName);
    return found ? found[0] : listing.currencyCode;
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
    const records = mainKvGet("player_draw_records", {});
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
    mainKvSet("player_draw_records", records);
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
    return main ? mainKvGet("player_pity_counters", {}) : {};
}
function savePityCounters(counters) {
    const main = getMainExt();
    if (main) mainKvSet("player_pity_counters", counters);
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
    const apg = mainKvGet("a_private_group", {});
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
    const log = mainKvGet("item_usage_log", []);
    log.push({ timestamp: Date.now(), platform, roleName, code, name: itemName });
    if (log.length > 500) log.splice(0, log.length - 500);
    mainKvSet("item_usage_log", log);
}

// ========================
// 背包显示（手机版紧凑格式）
// ========================

function formatItemEntry(entry, info) {
    const name = info.name || entry.code;
    const shortName = name.length > 16 ? name.slice(0, 15) + "…" : name;
    const codeShort = entry.code.slice(-3);
    const desc = info.desc || "";
    const uses = (entry.remainingUses ?? info.maxUses ?? -1);
    const usesStr = uses === -1 ? "∞次" : `余${uses}次`;
    const durStr = (info.durability != null && entry.currentDurability !== undefined)
        ? `|耐久${entry.currentDurability}/${info.durability}` : "";

    let tags = "";
    if (info.type === "preset") tags += "🎯";
    if (info.type === "equipment") tags += "⚔️";
    if (info.canResell === false) tags += "🔒";
    if (info.canResell === true) tags += "✨";

    let line1 = `·${shortName}[${codeShort}]${tags}`;
    let line2 = `数量×${entry.count}|${usesStr}${durStr}`;
    let line3 = desc || "无描述";

    let result = `${line1}\n${line2}\n${line3}`;

    if (info.attrs) result += `\n${info.attrs}`;

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
            lines.push(`${cat.emoji}${cat.name}(${cat.items.length})`);
            for (const { entry, info } of cat.items) {
                if (info.type === "currency") {
                    lines.push(`${info.name}：${entry.count}`);
                } else {
                    lines.push(formatItemEntry(entry, info));
                    lines.push("");
                }
            }
            lines.push("");
        }
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["注册属性"] = cmd_reg_attr; (合入属性子命令)

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

// ========================
// 上载：统一注册指令（物品 / 互动物品 / 货币）
// ========================

function parseUploadTags(line, defs, currencyNames) {
    const blocks = [];
    const name = line.replace(/【([^】]*)】/g, (_, c) => { blocks.push(c.trim()); return ''; }).trim();
    if (!name) return { error: '物品名不能为空' };
    const effectPat = /^[\w一-鿿㐀-䶿]+[+-]\d+([,，][\w一-鿿㐀-䶿]+[+-]\d+)*$/;
    let type = 'item', desc = null, maxUses = -1, attrsRaw = null, canResell = false;
    for (const b of blocks) {
        if (b === '互动') { type = 'interact'; continue; }
        if (b === '货币') { type = 'currency'; continue; }
        if (b === '二手') { canResell = true; continue; }
        if (b === '无限') { maxUses = -1; continue; }
        if (b === '一次') { maxUses = 1; continue; }
        const tm = b.match(/^(\d+)次$/);
        if (tm) { maxUses = parseInt(tm[1]); continue; }
        if (effectPat.test(b)) {
            const segs = b.split(/[,，]/);
            for (const seg of segs) {
                const m = seg.trim().match(/^(.+?)([+-]\d+)$/);
                if (!m) return { error: `效果格式错误「${seg}」` };
                const aName = m[1];
                if (!defs[aName] && !currencyNames.has(aName))
                    return { error: `未知属性「${aName}」，请先注册属性` };
            }
            attrsRaw = b; continue;
        }
        if (desc === null) desc = b;
    }
    return { name, type, desc, maxUses, attrsRaw, canResell };
}

let cmd_upload = seal.ext.newCmdItemInfo();
cmd_upload.name = "上载";
cmd_upload.help = `【管理员】注册物品/互动物品/货币，支持多行批量
格式：物品名【标签】【标签】...
  【描述文字】   物品描述
  【N次】        使用次数；【无限】= 无限次
  【属性+N】     效果，如【力量+5,体力-2】
  【互动】       互动物品（对他人使用）
  【货币】       注册为货币
  【二手】       允许二手交易
示例：
  。上载 金苹果【恢复体力】【5次】【体力+10】
  。上载
  爱心糖【甜蜜道具】【互动】【甜蜜+3】【二手】
  银币【货币】`;
cmd_upload.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const rawMsg = (msg.message || "").trim();
    const msgParts = rawMsg.split(/\r?\n/);
    const firstRest = msgParts[0].replace(/^[。.]\s*上载\s*/, "").trim();
    const extraLines = msgParts.slice(1).map(l => l.trim()).filter(l => l);
    const lines = [...(firstRest ? [firstRest] : []), ...extraLines];

    if (!lines.length) {
        const attrList = getValidAttrs().join("、") || "（暂无，请先注册属性）";
        return seal.replyToSender(ctx, msg, `📦 上载格式：物品名【标签】...\n标签：【N次】【无限】【属性+N,属性-N】【互动】【货币】【二手】【描述】\n当前可用属性：${attrList}`);
    }

    const reg = getRegistry();
    const defs = getAttrDefs();
    const currencyNames = new Set(Object.values(reg).filter(i => i.type === "currency").map(i => i.name));
    const results = [];

    for (const line of lines) {
        const parsed = parseUploadTags(line, defs, currencyNames);
        if (parsed.error) { results.push(`❌ 「${line.substring(0, 20)}」${parsed.error}`); continue; }
        const { name, type, desc, maxUses, attrsRaw, canResell } = parsed;

        const existing = Object.values(reg).find(r => r.name === name);
        if (existing) { results.push(`⚠️ 「${name}」已存在 [${existing.code}]，跳过`); continue; }

        if (type === 'currency') {
            if (getValidAttrs().includes(name)) { results.push(`❌ 「${name}」已被注册为属性，货币名不能与属性重复`); continue; }
            const code = genCurrencyCode(reg);
            if (!code) { results.push("❌ 货币代码空间已满"); break; }
            reg[code] = { code, name, desc: desc || "暂无描述", type: "currency", attrs: null };
            results.push(`✅ 💰 [${code}] ${name}（货币）`); continue;
        }

        const genFn = type === 'interact' ? genInteractionCode : genItemCode;
        const code = genFn(reg);
        if (!code) { results.push("❌ 代码空间已满，无法继续注册"); break; }
        reg[code] = { code, name, desc: desc || "暂无描述", type, maxUses, attrs: attrsRaw, price: 0, canResell };
        const useText = maxUses === -1 ? "无限" : `${maxUses}次`;
        const icon = type === 'interact' ? "🎭" : "📦";
        const resellPart = canResell ? " | 可二手" : "";
        results.push(`✅ ${icon} [${code}] ${name} | ${useText} | 效果:${attrsRaw || "无"}${resellPart}`);
    }

    saveRegistry(reg);
    seal.replyToSender(ctx, msg, `上载结果（共${results.length}条）：\n${results.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上载"] = cmd_upload;


let cmd_item_list = seal.ext.newCmdItemInfo();
cmd_item_list.name = "物品列表";
cmd_item_list.help = "查看所有已注册物品/货币\n物品列表 [物品|互动|货币|预设|全部]";
cmd_item_list.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

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

    const formatEntry = e => {
        const icon = e.type === "currency" ? "💰" : e.type === "preset" ? "⚙️" : "📦";
        const attrStr = e.attrs ? ` (${e.attrs})` : "";
        return `${icon} [${e.code}] ${e.name}${attrStr}\n   └ ${e.desc}`;
    };
    const header = `📋 ${filter}列表（${entries.length}）：`;
    const CHUNK_SIZE = 15;
    const nodeContents = [header];
    for (let i = 0; i < entries.length; i += CHUNK_SIZE) {
        nodeContents.push(entries.slice(i, i + CHUNK_SIZE).map(formatEntry).join("\n"));
    }
    sendForwardOrPlain(ctx, msg, nodeContents, "物品管理员");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["物品列表"] = cmd_item_list;

let cmd_del_attr = seal.ext.newCmdItemInfo();
cmd_del_attr.name = "删除属性";
cmd_del_attr.help = "【管理员】删除已注册属性\n删除属性 名称";
cmd_del_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["删除属性"] = cmd_del_attr; (合入属性子命令)

let cmd_set_attr = seal.ext.newCmdItemInfo();
cmd_set_attr.name = "设置属性";
cmd_set_attr.help = "【管理员】直接设置角色属性值\n设置属性 角色名 属性名 值\n示例：设置属性 张三 体力 80";
cmd_set_attr.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["设置属性"] = cmd_set_attr; (合入属性子命令)

let cmd_shop_add = seal.ext.newCmdItemInfo();
cmd_shop_add.name = "上架商城";
cmd_shop_add.help = "【管理员】上架物品\n上架商城 物品码*价格货币名\n示例：上架商城 ITEM_001*10金币";
cmd_shop_add.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
            const config = mainKvGet("global_feature_toggle", {});
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
// ext.cmdMap["上架商城"] = cmd_shop_add; (合入商城子命令)

let cmd_shop_remove = seal.ext.newCmdItemInfo();
cmd_shop_remove.name = "商城下架";
cmd_shop_remove.help = "【管理员】将物品从商城下架\n商城下架 物品码或名称";
cmd_shop_remove.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["商城下架"] = cmd_shop_remove; (合入商城子命令)

let cmd_view_pool = seal.ext.newCmdItemInfo();
cmd_view_pool.name = "查看池子";
cmd_view_pool.help = `【管理员】查看池子详情
查看池子          —— 列出所有池子状态（等同于「池子设定」查看）
查看池子 池子名   —— 显示该池子的全部物品`;
cmd_view_pool.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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

let cmd_adjust = seal.ext.newCmdItemInfo();
cmd_adjust.name = "调整";
cmd_adjust.help = "【管理员】直接调整玩家背包数量\n调整 角色名 物品码 +N [物品码2 +N2 ...]\n示例：调整 张三 ITEM_001 +3\n多个：调整 张三 ITEM_001 +3 ITEM_002 -1 SPEC_005 +2";
cmd_adjust.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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



let cmd_market_config = seal.ext.newCmdItemInfo();
cmd_market_config.name = "二手设定";
cmd_market_config.help = "【管理员】配置二手市场\n二手设定 手续费:N —— 设置手续费百分比（2-5）\n二手设定 开启 / 关闭\n二手设定 查看";
cmd_market_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["二手设定"] = cmd_market_config; (合入二手子命令)

// ========================
// 玩家指令
// ========================

let cmd_shop_view = seal.ext.newCmdItemInfo();
cmd_shop_view.name = "商城";
cmd_shop_view.help = "商城\n商城              查看商城\n商城 购买 物品名   购买物品\n商城 上架 物品*价格 上架（管理员）\n商城 下架 物品名   下架（管理员）";
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
    const currencyCode = resolveListingCurrencyCode(reg, listing);
    if (currencyCode !== listing.currencyCode) { listing.currencyCode = currencyCode; saveShop(shop); }
    const totalCost = listing.price * count;
    const hasCurrency = getInvCount(roleKey, currencyCode);
    if (hasCurrency < totalCost) return seal.replyToSender(ctx, msg, `❌ ${listing.currencyName}不足。需要 ${totalCost}，持有 ${hasCurrency}。`);
    removeFromInv(roleKey, currencyCode, totalCost);
    addToInv(roleKey, item.code, count);
    seal.replyToSender(ctx, msg, `✅ 购买成功！获得 [${item.code}]${item.name} ×${count}，花费 ${totalCost}${listing.currencyName}`);
    return seal.ext.newCmdExecuteResult(true);
};
// ext.cmdMap["购买"] = cmd_buy; (合入商城子命令)

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
    // 同一物品码可能因剩余次数不同拆成多条堆叠，赠送只能从单一堆叠转出（否则 remainingUses 无法确定）
    // 因此优先找“单独就够数量”的那一叠，而不是盲目取第一条匹配（可能只是恰好排在前面的小堆叠）
    let fromInv = getInv(fromRoleKey);
    let itemIdx = fromInv.findIndex(i => i.code === itemInfo.code && i.count >= count);

    if (itemIdx === -1) {
        const has = getInvCount(fromRoleKey, itemInfo.code);
        const splitHint = has >= count ? "（持有量分散在多个剩余次数不同的堆叠中，单次赠送需来自同一堆叠，请拆分数量分次赠送）" : "";
        return seal.replyToSender(ctx, msg, `❌ [${itemInfo.code}]${itemInfo.name} 不足（持有 ${has}，需要 ${count}）。${splitHint}`);
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

// 扣除物品一次使用次数并保存背包，返回状态文字
function _consumeItem(inv, invIndex, item, roleKey) {
    let userItem = inv[invIndex];
    if (userItem.remainingUses === undefined) {
        userItem.remainingUses = item.maxUses ?? -1;
    }
    let usageStatus = "";
    if (userItem.remainingUses !== -1) {
        userItem.remainingUses -= 1;
        if (userItem.remainingUses <= 0) {
            userItem.count -= 1;
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
        userItem.count -= 1;
        if (userItem.count <= 0) inv.splice(invIndex, 1);
    }
    // ── 耐久度：有 durability 定义时，每次使用消耗 1 点；归零时物品损坏销毁 ──
    if (item.durability != null && item.durability > 0) {
        const curIdx = inv.indexOf(userItem);
        if (curIdx !== -1) {
            if (userItem.currentDurability === undefined) userItem.currentDurability = item.durability;
            userItem.currentDurability -= 1;
            if (userItem.currentDurability <= 0) {
                inv.splice(curIdx, 1);
                usageStatus = "(已损坏)";
            } else if (!usageStatus) {
                usageStatus = `(耐久 ${userItem.currentDurability}/${item.durability})`;
            }
        }
    }
    saveInv(roleKey, inv);
    return usageStatus;
}

let cmd_use = seal.ext.newCmdItemInfo();
cmd_use.name = "使用";
cmd_use.help = `使用背包中的物品
· 使用 物品          — 对自己使用普通物品
· 使用 物品 目标     — 对他人使用互动物品
· 使用 特殊 道具名   — 使用特殊道具（SPEC类）
· 使用 设置          — 查看互动物品施加设置`;

cmd_use.solve = (ctx, msg, cmdArgs) => {
    if (cmdArgs.getArgN(1) === "特殊") {
        return cmd_special_use.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);

    // 查看施加设置
    if (!arg1 || arg1 === "设置" || arg1 === "查看") {
        const applyNotify = mainStorGet("apply_item_notification") !== "false";
        const exposeRate = getMainStorageInt("apply_item_expose_rate", 0);
        const applyHours = mainStorGet("apply_item_hours") || "不限";
        return seal.replyToSender(ctx, msg, [
            "【互动物品施加设置】",
            `施加是否提醒：${applyNotify ? '开启' : '关闭'} (${applyNotify ? '告知对方' : '不告知对方'})`,
            `暴露名字概率：${exposeRate}% (${exposeRate === 0 ? '完全匿名' : exposeRate === 100 ? '完全暴露' : '随机暴露'})`,
            `施加可用时段：${applyHours}`,
        ].join('\n'));
    }

    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const roleKey = `${platform}:${uid}`;

    const reg = getRegistry();
    const item = findItem(reg, arg1);
    if (!item) return seal.replyToSender(ctx, msg, `❌ 未知物品「${arg1}」`);

    if (item.type === "preset") {
        return seal.replyToSender(ctx, msg, `⚙️ [${item.code}]${item.name} 是特殊道具，请使用「特殊使用 ${item.name} [参数]」`);
    }

    const targetName = arg2 || null;

    // ── INTER 互动物品：必须有目标 ──────────────────────────────
    if (item.type === "interact") {
        if (!targetName) {
            return seal.replyToSender(ctx, msg, `💉 [${item.name}] 是互动物品，请指定目标：\n使用 ${item.name} 目标角色`);
        }
        const main = getMainExt();
        if (!isApplyTimeValid(main)) {
            const hoursStr = mainStorGet("apply_item_hours");
            return seal.replyToSender(ctx, msg, `❌ 当前不在道具施加时段内。\n当前可用时段：${hoursStr}`);
        }
        const targetUid = getRoleUid(platform, targetName);
        if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);

        let inv = getInv(roleKey);
        let invIndex = inv.findIndex(i => i.code === item.code);
        if (invIndex === -1 || inv[invIndex].count <= 0) {
            return seal.replyToSender(ctx, msg, `❌ 你的背包里没有 [${item.code}]${item.name}。`);
        }
        if (item.attrs) modCharAttrs(platform, targetName, item.attrs);
        const usageStatus = _consumeItem(inv, invIndex, item, roleKey);

        const changes = item.attrs ? parseAttrEffects(item.attrs) : {};
        const effectStr = Object.entries(changes).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join("，");
        const shouldNotify = mainStorGet("apply_item_notification") !== "false";
        const exposeRate = getMainStorageInt("apply_item_expose_rate", 0);
        const isExposed = Math.random() * 100 < exposeRate;
        if (shouldNotify) {
            const displayName = isExposed ? `角色「${roleName}」` : "某人";
            notifyPlayer(ctx, platform, targetName, `💉 ${displayName} 对你使用了 [${item.name}]！\n📊 你的属性变化：${effectStr}`);
        }
        let feedback = `✅ 你成功对「${targetName}」使用了 [${item.name}] ${usageStatus}。`;
        feedback += shouldNotify
            ? `\n(暴露概率：${exposeRate}%，本次${isExposed ? "已暴露名字" : "保持匿名"})`
            : "\n(已根据设置隐藏对目标的通知)";
        if (effectStr) feedback += `\n📊 目标属性变化：${effectStr}`;
        seal.replyToSender(ctx, msg, feedback);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 普通物品：自用 ──────────────────────────────────────────
    if (targetName) {
        return seal.replyToSender(ctx, msg, `⚠️ [${item.name}] 不是互动类物品，只能对自己使用（无需指定目标）。`);
    }
    let inv = getInv(roleKey);
    let invIndex = inv.findIndex(i => i.code === item.code);
    if (invIndex === -1 || inv[invIndex].count <= 0) {
        return seal.replyToSender(ctx, msg, `❌ 背包中没有 [${item.code}]${item.name}。`);
    }
    let effectReply = "";
    if (item.attrs) {
        modCharAttrs(platform, roleName, item.attrs);
        const changes = parseAttrEffects(item.attrs);
        effectReply = `\n📊 属性变化：${Object.entries(changes).map(([k, v]) => `${k}${v > 0 ? '+' : ''}${v}`).join("，")}`;
    }
    const usageStatus = _consumeItem(inv, invIndex, item, roleKey);
    logItemUsage(platform, roleName, item.code, item.name);
    seal.replyToSender(ctx, msg, `⚙️ 【${roleName}】使用了 [${item.code}]${item.name} ${usageStatus}。${effectReply}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["使用"] = cmd_use;
// ext.cmdMap["用"] alias removed

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
    // 同一物品码可能因剩余次数不同拆成多条堆叠，一次上架只能来自单一堆叠（否则 remainingUses 无法确定）
    // 因此优先找“单独就够数量”的那一叠，而不是盲目取第一条匹配（可能只是恰好排在前面的小堆叠）
    let inv = getInv(roleKey);
    let invIndex = inv.findIndex(i => i.code === item.code && i.count >= count);

    if (invIndex === -1) {
        const has = getInvCount(roleKey, item.code);
        const splitHint = has >= count ? "（持有量分散在多个剩余次数不同的堆叠中，单次上架需来自同一堆叠，请拆分数量分次上架）" : "";
        return seal.replyToSender(ctx, msg, `❌ [${item.code}]${item.name} 不足（持有 ${has}，需要 ${count}）。${splitHint}`);
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
// ext.cmdMap["售卖"] = cmd_sell; (合入二手子命令)

let cmd_cancel_sell = seal.ext.newCmdItemInfo();
cmd_cancel_sell.name = "撤销卖单";
cmd_cancel_sell.help = "撤销二手市场的卖单\n撤销卖单 编号（如 0001）";
cmd_cancel_sell.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const platform = msg.platform;
    const rawCode = (cmdArgs.getArgN(1) || "").trim();
    if (!/^\d{1,4}$/.test(rawCode)) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const shCode = rawCode.padStart(4, '0');
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
// ext.cmdMap["撤销卖单"] = cmd_cancel_sell; (合入二手子命令)

let cmd_market = seal.ext.newCmdItemInfo();
cmd_market.name = "二手";
cmd_market.help = "查看/购买二手市场物品\n二手市场 —— 查看所有在售\n二手市场 买 编号 —— 购买指定编号";

cmd_market.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);
    if (sub === "卖" || sub === "售卖") return cmd_sell.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "撤" || sub === "撤销") return cmd_cancel_sell.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "设定") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_market_config.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

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

        // 校正挂单里可能失配的 currencyCode（见 resolveListingCurrencyCode 注释）
        const currencyCode = resolveListingCurrencyCode(reg, listing);
        if (currencyCode !== listing.currencyCode) { listing.currencyCode = currencyCode; saveMarket(market); }

        // 检查买家余额
        const hasCurrency = getInvCount(buyerRoleKey, currencyCode);
        if (hasCurrency < totalCost) {
            return seal.replyToSender(ctx, msg, `❌ ${listing.currencyName}不足。需要 ${totalCost}（含费），持有 ${hasCurrency}。`);
        }

        // --- 执行交易 ---
        // 1. 扣除买家钱款
        removeFromInv(buyerRoleKey, currencyCode, totalCost);
        // 2. 将原价（不含手续费）给卖家
        addToInv(sellerRoleKey, currencyCode, totalPrice);

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
ext.cmdMap["二手"] = cmd_market;

// ========================
// 💱 玩家直接议价交易
// ========================
function getTradeConfig() {
    return getMainExt() ? mainKvGet("trade_config", {"daily_limit":0,"cooldown_minutes":0}) : { daily_limit: 0, cooldown_minutes: 0 };
}
function saveTradeConfig(cfg) { if (getMainExt()) mainKvSet("trade_config", cfg); }
function getTradeUserStats() {
    return getMainExt() ? mainKvGet("trade_user_stats", {}) : {};
}
function saveTradeUserStats(stats) { if (getMainExt()) mainKvSet("trade_user_stats", stats); }

// 检查玩家是否可以参与交易；type="propose"只查冷却，"complete"还查每日上限
function checkTradePlayerReady(platform, uid, type) {
    const cfg = getTradeConfig();
    const key = `${platform}:${uid}`;
    const ps  = (getTradeUserStats()[key]) || {};
    const now = Date.now();
    if (cfg.cooldown_minutes > 0 && ps.lastTradeAt) {
        const elapsed = (now - ps.lastTradeAt) / 60000;
        if (elapsed < cfg.cooldown_minutes) {
            const rem = Math.ceil(cfg.cooldown_minutes - elapsed);
            return { ok: false, reason: `交易冷却中，还需等待 ${rem} 分钟` };
        }
    }
    if (type === "complete" && cfg.daily_limit > 0) {
        const today = cachedGet("global_day") || "";
        if (ps.todayDate === today && (ps.todayCount || 0) >= cfg.daily_limit) {
            return { ok: false, reason: `今日交易次数已达上限（${cfg.daily_limit} 次）` };
        }
    }
    return { ok: true };
}
function recordTradeCompletion(platform, uid) {
    const stats = getTradeUserStats();
    const key   = `${platform}:${uid}`;
    const today = cachedGet("global_day") || "";
    const ps    = stats[key] || {};
    if (ps.todayDate !== today) { ps.todayDate = today; ps.todayCount = 0; }
    ps.todayCount    = (ps.todayCount || 0) + 1;
    ps.lastTradeAt   = Date.now();
    stats[key] = ps;
    saveTradeUserStats(stats);
}

function getTradeWhitelist() {
    return getMainExt() ? mainKvGet("trade_whitelist", []) : [];
}

function getTradeOffers() {
    return getMainExt() ? mainKvGet("trade_offers", {}) : {};
}
function saveTradeOffers(o) {
    if (getMainExt()) mainKvSet("trade_offers", o);
}
function genTradeId(offers) {
    for (let i = 1; i <= 9999; i++) {
        const id = "TR" + String(i).padStart(4, "0");
        if (!offers[id]) return id;
    }
    return null;
}
// 物品名或编码 → 编码（两个注册表均查）
function resolveItemCode(nameOrCode) {
    const reg = getRegistry(); const eq = getEquipRegistry();
    const upper = nameOrCode.toUpperCase();
    if (reg[upper] || eq[upper]) return upper;
    for (const [code, info] of Object.entries(reg)) { if (info.name === nameOrCode) return code; }
    for (const [code, info] of Object.entries(eq))  { if (info.name === nameOrCode) return code; }
    return null;
}
// 解析 "给:物品名或码×N,..." 或 "要:..." 格式 → [{raw, count}]（raw 待后续 resolve）
function parseTradeItems(raw) {
    if (!raw) return null;
    const str = raw.replace(/^[给要]:/, "").trim();
    if (!str) return null;
    const result = [];
    for (const part of str.split(",").map(s => s.trim()).filter(Boolean)) {
        const sepIdx = part.search(/[×xX*]/);
        if (sepIdx === -1) {
            if (!part) return null;
            result.push({ raw: part, count: 1 });
        } else {
            const raw2 = part.slice(0, sepIdx).trim();
            const count = parseInt(part.slice(sepIdx + 1).trim());
            if (!raw2 || isNaN(count) || count < 1) return null;
            result.push({ raw: raw2, count });
        }
    }
    return result.length ? result : null;
}
// 将 parseTradeItems 结果中的 raw 解析为 code，返回 {items, errors}
function resolveTradeItems(parsed) {
    const items = []; const errors = [];
    for (const { raw, count } of parsed) {
        const code = resolveItemCode(raw);
        if (!code) errors.push(`「${raw}」`);
        else items.push({ code, count });
    }
    return { items, errors };
}
function tradeItemsText(items) {
    const reg = getRegistry(); const eq = getEquipRegistry();
    return items.map(({ code, count }) => {
        const info = reg[code] || eq[code];
        return (info ? info.name : code) + "×" + count;
    }).join("、");
}
function checkHasItems(roleKey, items) {
    const reg = getRegistry(); const eq = getEquipRegistry();
    // 先按物品码合并数量，避免同一物品码在给/要列表中重复出现时，逐条独立校验各自都"够"、
    // 但汇总需求量其实超过实际持有量（会被用来无中生有复制物品）
    const totals = new Map();
    for (const { code, count } of items) totals.set(code, (totals.get(code) || 0) + count);
    const missing = [];
    for (const [code, count] of totals) {
        const have = getInvCount(roleKey, code);
        if (have < count) {
            const info = reg[code] || eq[code];
            missing.push(`${info ? info.name : code}（有×${have}，需×${count}）`);
        }
    }
    return missing;
}
function tradeGetRoleKey(platform, roleName) {
    const uid = getRoleUid(platform, roleName);
    return uid ? `${platform}:${uid}` : null;
}

let cmd_trade = seal.ext.newCmdItemInfo();
cmd_trade.name = "交易";
cmd_trade.help = [
    "💱 玩家议价交易（需管理员开启 dlc_trade）",
    "交易 提出 [对方] [给:物品码×N,...] [要:物品码×N,...] [备注]",
    "交易 接受 [单号]   — 接受交易（双方必须持有对应物品）",
    "交易 拒绝 [单号]   — 拒绝对方提案",
    "交易 还价 [单号] [给:物品码×N,...] [要:物品码×N,...] [备注]",
    "交易 撤回 [单号]   — 撤回自己发出的提案",
    "交易 列表         — 查看我的所有进行中及近期交易",
    "交易 详情 [单号]  — 查看完整的交易内容",
    "交易 设定（管理员）— 配置每日上限/冷却时间，详见「交易 设定」",
    "示例：交易 提出 李四 给:ITEM_001×2 要:ITEM_002×1 换个好东西"
].join("\n");
cmd_trade.solve = (ctx, msg, cmdArgs) => {
    if (cmdArgs.getArgN(1) === "设定") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_trade_config.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

    const toggle = mainKvGet("global_feature_toggle", {});
    if (!toggle.dlc_trade) return seal.replyToSender(ctx, msg, "❌ 议价交易功能未开启，请联系管理员。");

    const platform = msg.platform;
    const myName = getRoleName(ctx, msg);
    if (!myName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
    const rawUid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const uid = getPrimaryUid(platform, rawUid);
    const myKey = `${platform}:${uid}`;

    const sub = cmdArgs.getArgN(1);

    // ── 提出 ──────────────────────────────────────────────────────
    if (sub === "提出") {
        const toName   = cmdArgs.getArgN(2);
        const giveRaw  = cmdArgs.getArgN(3);
        const wantRaw  = cmdArgs.getArgN(4);
        const note     = cmdArgs.getArgN(5) || "";
        if (!toName || !giveRaw || !wantRaw) {
            return seal.replyToSender(ctx, msg,
                "⚠️ 格式：交易 提出 对方角色名 给:物品码×N,... 要:物品码×N,... [备注]\n" +
                "示例：交易 提出 李四 给:ITEM_001×2 要:ITEM_002×1");
        }
        if (toName === myName) return seal.replyToSender(ctx, msg, "❌ 不能和自己交易。");
        const proposeCheck = checkTradePlayerReady(platform, uid, "propose");
        if (!proposeCheck.ok) return seal.replyToSender(ctx, msg, `❌ ${proposeCheck.reason}`);

        if (!getRoleUid(platform, toName)) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${toName}」。`);
        if (!giveRaw.startsWith("给:")) return seal.replyToSender(ctx, msg, "❌ 第3个参数格式应为「给:物品码×N,...」");
        if (!wantRaw.startsWith("要:")) return seal.replyToSender(ctx, msg, "❌ 第4个参数格式应为「要:物品码×N,...」");

        const giveParsed = parseTradeItems(giveRaw);
        const wantParsed = parseTradeItems(wantRaw);
        if (!giveParsed) return seal.replyToSender(ctx, msg, "❌ 「给」物品列表格式错误，示例：给:铁剑×2,ITEM_002×1");
        if (!wantParsed) return seal.replyToSender(ctx, msg, "❌ 「要」物品列表格式错误，示例：要:回血药×1");

        const { items: give, errors: giveErr } = resolveTradeItems(giveParsed);
        const { items: want, errors: wantErr } = resolveTradeItems(wantParsed);
        if (giveErr.length) return seal.replyToSender(ctx, msg, `❌ 找不到物品：${giveErr.join("、")}`);
        if (wantErr.length) return seal.replyToSender(ctx, msg, `❌ 找不到物品：${wantErr.join("、")}`);

        // 白名单校验（白名单为空视为全部允许）
        const wl = getTradeWhitelist();
        if (wl.length > 0) {
            const _reg = getRegistry(); const _eq = getEquipRegistry();
            const blocked = [...give, ...want].filter(({ code }) => !wl.includes(code))
                .map(({ code }) => { const i = _reg[code] || _eq[code]; return i ? i.name : code; });
            if (blocked.length) return seal.replyToSender(ctx, msg, `❌ 以下物品不在可交易白名单中：${blocked.join("、")}`);
        }

        const myMissing = checkHasItems(myKey, give);
        if (myMissing.length) return seal.replyToSender(ctx, msg, `❌ 你背包物品不足：\n${myMissing.join("\n")}`);

        const offers = getTradeOffers();
        const id = genTradeId(offers);
        if (!id) return seal.replyToSender(ctx, msg, "❌ 交易单号已满，请联系管理员清理。");

        offers[id] = { id, from: myName, to: toName, give, want, status: "pending", createdAt: Date.now(), note, relatedId: null };
        saveTradeOffers(offers);

        seal.replyToSender(ctx, msg,
            `✅ 交易提案 ${id} 已发出！\n📤 你提供：${tradeItemsText(give)}\n📥 你想要：${tradeItemsText(want)}` +
            (note ? `\n💬 ${note}` : "") + `\n\n等待 ${toName} 回应。`);
        notifyPlayer(ctx, platform, toName,
            `📨 ${myName} 向你发起了交易提案 ${id}！\n📤 对方提供：${tradeItemsText(give)}\n📥 对方想要：${tradeItemsText(want)}` +
            (note ? `\n💬 ${note}` : "") + `\n\n回复：交易 接受/拒绝/还价 ${id}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 接受 ──────────────────────────────────────────────────────
    if (sub === "接受") {
        const id = cmdArgs.getArgN(2);
        if (!id) return seal.replyToSender(ctx, msg, "❌ 请指定单号，如：交易 接受 TR0001");
        const offers = getTradeOffers();
        const offer  = offers[id];
        if (!offer) return seal.replyToSender(ctx, msg, `❌ 未找到交易单 ${id}。`);
        if (offer.to !== myName) return seal.replyToSender(ctx, msg, "❌ 这笔交易不是发给你的。");
        if (offer.status !== "pending") return seal.replyToSender(ctx, msg, `❌ 该交易单已「${offer.status}」，无法接受。`);

        const fromKey  = tradeGetRoleKey(platform, offer.from);
        if (!fromKey) return seal.replyToSender(ctx, msg, "❌ 无法找到发起方账户信息。");
        const fromUid  = getRoleUid(platform, offer.from);

        // 冷却 + 每日上限检查（接受双方都要满足）
        const myReady    = checkTradePlayerReady(platform, uid,     "complete");
        if (!myReady.ok) return seal.replyToSender(ctx, msg, `❌ 你无法完成交易：${myReady.reason}`);
        const theirReady = fromUid ? checkTradePlayerReady(platform, fromUid, "complete") : { ok: true };
        if (!theirReady.ok) return seal.replyToSender(ctx, msg, `❌ 对方无法完成交易：${theirReady.reason}`);

        const myMissing    = checkHasItems(myKey,   offer.want);
        if (myMissing.length) return seal.replyToSender(ctx, msg, `❌ 你的背包物品不足，无法接受：\n${myMissing.join("\n")}`);
        const theirMissing = checkHasItems(fromKey, offer.give);
        if (theirMissing.length) return seal.replyToSender(ctx, msg,
            `⚠️ 对方背包物品已不足，交易无法完成：\n${theirMissing.join("\n")}\n\n请拒绝该交易单后重新协商。`);

        // 执行物品交换
        for (const { code, count } of offer.give) { removeFromInv(fromKey, code, count); addToInv(myKey, code, count); }
        for (const { code, count } of offer.want) { removeFromInv(myKey, code, count); addToInv(fromKey, code, count); }

        offer.status = "accepted"; offer.closedAt = Date.now();
        saveTradeOffers(offers);
        recordTradeCompletion(platform, uid);
        if (fromUid) recordTradeCompletion(platform, fromUid);

        seal.replyToSender(ctx, msg, `✅ 交易 ${id} 完成！\n📦 你获得：${tradeItemsText(offer.give)}\n📤 你给出：${tradeItemsText(offer.want)}`);
        notifyPlayer(ctx, platform, offer.from,
            `🎉 ${myName} 接受了你的交易 ${id}！\n📦 你获得：${tradeItemsText(offer.want)}\n📤 你给出：${tradeItemsText(offer.give)}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 拒绝 ──────────────────────────────────────────────────────
    if (sub === "拒绝") {
        const id = cmdArgs.getArgN(2);
        if (!id) return seal.replyToSender(ctx, msg, "❌ 请指定单号，如：交易 拒绝 TR0001");
        const offers = getTradeOffers();
        const offer  = offers[id];
        if (!offer) return seal.replyToSender(ctx, msg, `❌ 未找到交易单 ${id}。`);
        if (offer.to !== myName) return seal.replyToSender(ctx, msg, "❌ 这笔交易不是发给你的。");
        if (offer.status !== "pending") return seal.replyToSender(ctx, msg, `❌ 该交易单已「${offer.status}」，无法拒绝。`);

        offer.status = "rejected"; offer.closedAt = Date.now();
        saveTradeOffers(offers);

        seal.replyToSender(ctx, msg, `✅ 已拒绝交易 ${id}。`);
        notifyPlayer(ctx, platform, offer.from,
            `❌ ${myName} 拒绝了你的交易提案 ${id}。\n📤 你曾提供：${tradeItemsText(offer.give)}\n📥 你曾想要：${tradeItemsText(offer.want)}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 还价 ──────────────────────────────────────────────────────
    if (sub === "还价") {
        const id      = cmdArgs.getArgN(2);
        const giveRaw = cmdArgs.getArgN(3);
        const wantRaw = cmdArgs.getArgN(4);
        const note    = cmdArgs.getArgN(5) || "";
        if (!id || !giveRaw || !wantRaw) {
            return seal.replyToSender(ctx, msg,
                "⚠️ 格式：交易 还价 单号 给:物品码×N,... 要:物品码×N,... [备注]");
        }
        const offers = getTradeOffers();
        const offer  = offers[id];
        if (!offer) return seal.replyToSender(ctx, msg, `❌ 未找到交易单 ${id}。`);
        if (offer.to !== myName) return seal.replyToSender(ctx, msg, "❌ 这笔交易不是发给你的。");
        if (offer.status !== "pending") return seal.replyToSender(ctx, msg, `❌ 该交易单已「${offer.status}」，无法还价。`);
        if (!giveRaw.startsWith("给:")) return seal.replyToSender(ctx, msg, "❌ 第3个参数格式应为「给:物品码×N,...」");
        if (!wantRaw.startsWith("要:")) return seal.replyToSender(ctx, msg, "❌ 第4个参数格式应为「要:物品码×N,...」");

        const giveParsed = parseTradeItems(giveRaw);
        const wantParsed = parseTradeItems(wantRaw);
        if (!giveParsed) return seal.replyToSender(ctx, msg, "❌ 「给」物品列表格式错误。");
        if (!wantParsed) return seal.replyToSender(ctx, msg, "❌ 「要」物品列表格式错误。");

        const { items: give, errors: giveErr } = resolveTradeItems(giveParsed);
        const { items: want, errors: wantErr } = resolveTradeItems(wantParsed);
        if (giveErr.length) return seal.replyToSender(ctx, msg, `❌ 找不到物品：${giveErr.join("、")}`);
        if (wantErr.length) return seal.replyToSender(ctx, msg, `❌ 找不到物品：${wantErr.join("、")}`);

        const myMissing = checkHasItems(myKey, give);
        if (myMissing.length) return seal.replyToSender(ctx, msg, `❌ 你背包物品不足：\n${myMissing.join("\n")}`);

        offer.status = "countered";
        const newId = genTradeId(offers);
        if (!newId) return seal.replyToSender(ctx, msg, "❌ 交易单号已满。");
        offers[newId] = { id: newId, from: myName, to: offer.from, give, want, status: "pending", createdAt: Date.now(), note, relatedId: id };
        saveTradeOffers(offers);

        seal.replyToSender(ctx, msg,
            `✅ 还价提案 ${newId} 已发出（原提案 ${id} 已关闭）。\n📤 你提供：${tradeItemsText(give)}\n📥 你想要：${tradeItemsText(want)}` +
            (note ? `\n💬 ${note}` : ""));
        notifyPlayer(ctx, platform, offer.from,
            `🔄 ${myName} 对你的交易 ${id} 提出了还价！\n新提案号：${newId}\n📤 对方提供：${tradeItemsText(give)}\n📥 对方想要：${tradeItemsText(want)}` +
            (note ? `\n💬 ${note}` : "") + `\n\n回复：交易 接受/拒绝/还价 ${newId}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 撤回 ──────────────────────────────────────────────────────
    if (sub === "撤回") {
        const id = cmdArgs.getArgN(2);
        if (!id) return seal.replyToSender(ctx, msg, "❌ 请指定单号，如：交易 撤回 TR0001");
        const offers = getTradeOffers();
        const offer  = offers[id];
        if (!offer) return seal.replyToSender(ctx, msg, `❌ 未找到交易单 ${id}。`);
        if (offer.from !== myName) return seal.replyToSender(ctx, msg, "❌ 只能撤回自己发起的交易。");
        if (offer.status !== "pending") return seal.replyToSender(ctx, msg, `❌ 该交易单已「${offer.status}」，无法撤回。`);

        offer.status = "withdrawn"; offer.closedAt = Date.now();
        saveTradeOffers(offers);

        seal.replyToSender(ctx, msg, `✅ 交易 ${id} 已撤回。`);
        notifyPlayer(ctx, platform, offer.to, `📪 ${myName} 撤回了发给你的交易提案 ${id}。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 列表 ──────────────────────────────────────────────────────
    if (sub === "列表") {
        const offers = getTradeOffers();
        const mine   = Object.values(offers).filter(o => o.from === myName || o.to === myName);
        const pending = mine.filter(o => o.status === "pending");
        const recent  = mine.filter(o => o.status !== "pending")
            .sort((a, b) => (b.closedAt || b.createdAt) - (a.closedAt || a.createdAt))
            .slice(0, 5);

        if (!pending.length && !recent.length) return seal.replyToSender(ctx, msg, "📋 暂无交易记录。");
        const lines = [];
        if (pending.length) {
            lines.push("📋 进行中：");
            for (const o of pending) {
                const dir   = o.from === myName ? "→" : "←";
                const other = o.from === myName ? o.to : o.from;
                lines.push(`  [${o.id}] ${dir} ${other}  给:${tradeItemsText(o.give)}  要:${tradeItemsText(o.want)}`);
            }
        }
        if (recent.length) {
            lines.push("📁 最近记录：");
            const statusMap = { accepted:"已成交", rejected:"已拒绝", withdrawn:"已撤回", countered:"已还价" };
            for (const o of recent) {
                const other = o.from === myName ? o.to : o.from;
                lines.push(`  [${o.id}] ${other} · ${statusMap[o.status] || o.status}`);
            }
        }
        return seal.replyToSender(ctx, msg, `💱 我的交易单\n${lines.join("\n")}\n\n💡 交易 详情 单号  查看完整信息`);
    }

    // ── 详情 ──────────────────────────────────────────────────────
    if (sub === "详情") {
        const id = cmdArgs.getArgN(2);
        if (!id) return seal.replyToSender(ctx, msg, "❌ 请指定单号，如：交易 详情 TR0001");
        const offers = getTradeOffers();
        const offer  = offers[id];
        if (!offer) return seal.replyToSender(ctx, msg, `❌ 未找到交易单 ${id}。`);
        if (offer.from !== myName && offer.to !== myName)
            return seal.replyToSender(ctx, msg, "❌ 这笔交易与你无关。");

        const statusMap = { pending:"待回应", accepted:"已成交", rejected:"已拒绝", withdrawn:"已撤回", countered:"已还价" };
        const dateStr = new Date(offer.createdAt).toLocaleString("zh-CN", { month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit" });
        let text = `💱 交易单 ${id}\n状态：${statusMap[offer.status] || offer.status}\n` +
            `发起：${offer.from}  →  接受方：${offer.to}\n时间：${dateStr}\n\n` +
            `📤 ${offer.from} 提供：${tradeItemsText(offer.give)}\n📥 ${offer.from} 想要：${tradeItemsText(offer.want)}`;
        if (offer.note) text += `\n💬 ${offer.note}`;
        if (offer.relatedId) text += `\n🔗 关联原单：${offer.relatedId}`;
        return seal.replyToSender(ctx, msg, text);
    }

    return seal.replyToSender(ctx, msg, cmd_trade.help);
};
ext.cmdMap["交易"] = cmd_trade;

// 交易 设定 子命令的实现（不再作为独立命令注册，仅供 cmd_trade.solve 调用）
let cmd_trade_config = seal.ext.newCmdItemInfo();
cmd_trade_config.name = "交易设定";
cmd_trade_config.help = "【管理员】配置议价交易限制\n交易 设定 查看\n交易 设定 每日上限 N   — 每人每游戏日最多完成 N 笔（0=不限）\n交易 设定 冷却 N       — 完成后冷却 N 分钟才能再次提出/接受（0=不限）";
cmd_trade_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    const sub = cmdArgs.getArgN(1);
    const cfg = getTradeConfig();
    if (!sub || sub === "查看") {
        return seal.replyToSender(ctx, msg,
            `💱 交易系统设定：\n每日上限：${cfg.daily_limit > 0 ? cfg.daily_limit + " 次" : "不限"}\n冷却时间：${cfg.cooldown_minutes > 0 ? cfg.cooldown_minutes + " 分钟" : "不限"}`);
    }
    if (sub === "每日上限") {
        const n = parseInt(cmdArgs.getArgN(2));
        if (isNaN(n) || n < 0) return seal.replyToSender(ctx, msg, "❌ 请输入 0 或正整数（0=不限）。");
        cfg.daily_limit = n;
        saveTradeConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 每日交易上限已设为：${n > 0 ? n + " 次" : "不限"}`);
    }
    if (sub === "冷却") {
        const n = parseInt(cmdArgs.getArgN(2));
        if (isNaN(n) || n < 0) return seal.replyToSender(ctx, msg, "❌ 请输入 0 或正整数分钟（0=不限）。");
        cfg.cooldown_minutes = n;
        saveTradeConfig(cfg);
        return seal.replyToSender(ctx, msg, `✅ 交易冷却已设为：${n > 0 ? n + " 分钟" : "不限"}`);
    }
    return seal.replyToSender(ctx, msg, cmd_trade_config.help);
};

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
cmd_bag.name = "背包";
cmd_bag.help = `查看背包
。背包                查看全览
。背包 货币/道具/物品  按分类查看（支持翻页：。背包 道具 2）
。背包 搜 关键词       搜索物品
。背包 详情 物品名     物品详情
。背包 记录 [N]        今日使用记录（管理员，默认20条）
。背包 他人 角色名     查看他人背包（管理员）`;
cmd_bag.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    const sub = cmdArgs.getArgN(1);

    if (sub === "他人") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        const targetRole = cmdArgs.getArgN(2);
        if (!targetRole) return seal.replyToSender(ctx, msg, "❌ 请输入角色名：。背包 他人 角色名");
        const tPlatform = msg.platform;
        const tUid = getRoleUid(tPlatform, targetRole);
        if (!tUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetRole}」。`);
        const otherBagText = formatInventory(`${tPlatform}:${getPrimaryUid(tPlatform, tUid)}`, targetRole, getRegistry());
        sendForwardOrPlain(ctx, msg, chunkBagText(otherBagText), `${targetRole}的背包`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (sub === "详情") {
        const input = cmdArgs.getArgN(2);
        if (!input) return seal.replyToSender(ctx, msg, "❌ 请输入物品名：。背包 详情 物品名");
        const reg = getRegistry();
        const item = findItem(reg, input);
        if (!item) return seal.replyToSender(ctx, msg, `❌ 未找到物品「${input}」`);
        const typeLabel = { item: "普通物品", currency: "货币", preset: "特殊道具", interact: "互动物品" }[item.type] || item.type;
        let text = `📦 [${item.code}] ${item.name}
类型：${typeLabel}
描述：${item.desc}`;
        if (item.attrs) text += `
属性效果：${item.attrs}`;
        const listing = getShop().find(s => s.code === item.code);
        if (listing) text += `
🏪 商城售价：${listing.price}${listing.currencyName}`;
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (sub === "记录") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        if (!getMainExt()) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
        const n = parseInt(cmdArgs.getArgN(2)) || 20;
        const log = mainKvGet("item_usage_log", []);
        const todayStart = new Date(); todayStart.setHours(0, 0, 0, 0);
        const todayLog = log.filter(e => e.timestamp >= todayStart.getTime()).sort((a, b) => a.timestamp - b.timestamp);
        if (!todayLog.length) return seal.replyToSender(ctx, msg, "📭 今天还没有物品使用记录。");
        const slice = todayLog.slice(-n);
        const lines = slice.map((e, i) => {
            const t = new Date(e.timestamp).toLocaleTimeString("zh-CN", { hour: '2-digit', minute: '2-digit' });
            return `${i + 1}. ${t} ${e.roleName} 使用了 [${e.code}]${e.name}`;
        });
        seal.replyToSender(ctx, msg, `📜 今日记录（${slice.length}/${todayLog.length}）：
${lines.join("\n")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const arg1 = sub || "全部";
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

    const bagText = formatInventory(roleKey, roleName, reg, category, page);
    sendForwardOrPlain(ctx, msg, chunkBagText(bagText), `${roleName}的背包`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["背包"] = cmd_bag;


let cmd_craft = seal.ext.newCmdItemInfo();
cmd_craft.name = "合成";
cmd_craft.help = "消耗材料合成物品\n合成 产物代码 [数量]\n示例：合成 ITEM_001\n合成 ITEM_001 3\n用「查看合成」查看所有配方";
cmd_craft.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);

    if (sub === "查看") {
        const recipes = getCraftRecipes();
        const reg = getRegistry();
        if (!Object.keys(recipes).length) return seal.replyToSender(ctx, msg, "📋 暂无合成配方。");
        const filter = cmdArgs.getArgN(2) || "";
        const filtered = Object.entries(recipes).filter(([code]) => !filter || code.includes(filter) || reg[code]?.name.includes(filter));
        if (!filtered.length) return seal.replyToSender(ctx, msg, `📋 未找到包含「${filter}」的配方。`);
        const lines = filtered.map(([code, recipe]) => {
            const matStr = Object.entries(recipe.materials).map(([c, cnt]) => `${reg[c]?.name || c}×${cnt}`).join(" + ");
            let line = `[${code}] ${reg[code]?.name || code}`;
            if (recipe.desc && recipe.desc !== "暂无描述") line += ` - ${recipe.desc}`;
            line += `
   ← ${matStr}`;
            const limits = recipe.limits || {};
            if (Object.keys(limits.attrs || {}).length || Object.keys(limits.currencies || {}).length) {
                line += "\n   ⚠️ 需求：";
                for (const [attr, val] of Object.entries(limits.attrs || {})) line += ` ${attr}≥${val},`;
                for (const [curr, val] of Object.entries(limits.currencies || {})) line += ` ${curr}≥${val},`;
                line = line.slice(0, -1);
            }
            return line;
        });
        seal.replyToSender(ctx, msg, `📋 合成配方（${filtered.length}/${Object.keys(recipes).length}）：
${lines.join("\n")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (sub === "删除") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        const input = cmdArgs.getArgN(2);
        if (!input) return seal.replyToSender(ctx, msg, "❌ 请输入产物名：。合成 删除 物品名");
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
    }

    if (sub === "注册") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        // 委托给独立的注册合成逻辑（通过重新解析消息）
        const fakeArgs = { getArgN: (n) => cmdArgs.getArgN(n + 1) };
        return cmd_reg_craft.solve(ctx, msg, fakeArgs);
    }

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


let cmd_delete_item = seal.ext.newCmdItemInfo();
cmd_delete_item.name = "删除物品";
cmd_delete_item.help = "【管理员】彻底删除物品定义，自动清出所有背包/商城/池子/配方/二手市场\n删除物品 物品码或名称";
cmd_delete_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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

    // 2. 商城下架（含以该货币计价的上架，货币没了没法付款）
    const shop = getShop();
    const shopBefore = shop.length;
    const shopAfter = shop.filter(l => l.code !== code && l.currencyCode !== code);
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

    // 6. 二手市场撤单（含以该货币计价的挂单，货币没了没法付款）
    const market = getMarket();
    let marketCount = 0;
    for (const shCode of Object.keys(market)) {
        if (market[shCode].code === code || market[shCode].currencyCode === code) {
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
    // 装备类型同步从 equipment_registry 删除
    const equipRegDel = getEquipRegistry();
    if (equipRegDel[code]) {
        delete equipRegDel[code];
        saveEquipRegistry(equipRegDel);
        log.push(`⚔️ 已同步删除装备注册`);
    }
    log.push(`🗑️ 物品定义 [${code}]${name} 已删除`);

    seal.replyToSender(ctx, msg, `✅ 删除完成：\n${log.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除物品"] = cmd_delete_item;

// 货币被删除后同名重新注册会换 code，导致老的商城/二手市场挂单里存的 currencyCode 失配
// （背包按当前 code 显示有余额，购买却按挂单里的旧 code 查到 0）。
// 该指令按 currencyName 重新匹配当前注册表，批量修正所有挂单的 currencyCode，无需逐条重新上架。
let cmd_fix_shop_currency = seal.ext.newCmdItemInfo();
cmd_fix_shop_currency.name = "修复商城货币";
cmd_fix_shop_currency.help = "【管理员】按货币名重新匹配商城/二手市场挂单里的货币 code\n用于货币被删除重建后，老挂单出现「背包有余额但购买提示不足」的情况";
cmd_fix_shop_currency.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const reg = getRegistry();
    const currencyByName = {};
    for (const item of Object.values(reg)) {
        if (item.type === "currency") currencyByName[item.name] = item.code;
    }

    const shop = getShop();
    let shopFixed = 0, shopOrphan = 0;
    for (const listing of shop) {
        const correctCode = currencyByName[listing.currencyName];
        if (!correctCode) { shopOrphan++; continue; }
        if (listing.currencyCode !== correctCode) { listing.currencyCode = correctCode; shopFixed++; }
    }
    if (shopFixed > 0) saveShop(shop);

    const market = getMarket();
    let marketFixed = 0, marketOrphan = 0;
    for (const shCode of Object.keys(market)) {
        const listing = market[shCode];
        const correctCode = currencyByName[listing.currencyName];
        if (!correctCode) { marketOrphan++; continue; }
        if (listing.currencyCode !== correctCode) { listing.currencyCode = correctCode; marketFixed++; }
    }
    if (marketFixed > 0) saveMarket(market);

    seal.replyToSender(ctx, msg,
        `✅ 修复完成：\n🏪 商城：修正 ${shopFixed} 条${shopOrphan ? `，${shopOrphan} 条货币名已不存在（跳过）` : ""}\n🔄 二手市场：修正 ${marketFixed} 条${marketOrphan ? `，${marketOrphan} 条货币名已不存在（跳过）` : ""}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["修复商城货币"] = cmd_fix_shop_currency;

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

// 施加：旧格式兼容别名（参数顺序 施加 目标 物品 → 内部转为 使用 物品 目标）
let cmd_apply = seal.ext.newCmdItemInfo();
cmd_apply.name = "施加";
cmd_apply.help = "兼容旧格式：施加 目标 物品\n推荐新格式：使用 物品 目标\n查看设置：使用 设置";
cmd_apply.solve = (ctx, msg, cmdArgs) => {
    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    // 设置/查看转发
    if (!arg1 || arg1 === "设置" || arg1 === "查看") {
        return cmd_use.solve(ctx, msg, { getArgN: (n) => n === 1 ? arg1 : null });
    }
    if (!arg2) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    // 旧格式：施加 目标 物品 → 等价于 使用 物品 目标
    return cmd_use.solve(ctx, msg, { getArgN: (n) => n === 1 ? arg2 : n === 2 ? arg1 : null });
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

        const b_confirmedSchedule = mainKvGet("b_confirmedSchedule", {});
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
        const availablePlaces = mainKvGet("available_places", {});
        if (!availablePlaces[placeName]) {
            const placeList = Object.keys(availablePlaces).join("、") || "（暂无）";
            return seal.replyToSender(ctx, msg, `❌ 未找到地点「${placeName}」。\n📍 可用地点：${placeList}`);
        }
        let placeKeys = mainKvGet("place_keys", {});
        if (!placeKeys[platform]) placeKeys[platform] = {};
        if (!placeKeys[platform][roleName]) placeKeys[platform][roleName] = [];
        if (placeKeys[platform][roleName].includes(placeName))
            return seal.replyToSender(ctx, msg, `🔑 你已经拥有「${placeName}」的钥匙了。`);
        if (!removeFromInv(roleKey, "SPEC_002", 1)) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的万能钥匙。");
        placeKeys[platform][roleName].push(placeName);
        mainKvSet("place_keys", placeKeys);
        return seal.replyToSender(ctx, msg, `🔑 成功兑换「${placeName}」的钥匙！（万能钥匙已消耗）`);
    }

    // ── SPEC_003 望远镜 / SPEC_004 羽毛笔 ──
    if (item.code === "SPEC_003" || item.code === "SPEC_004") {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) return seal.replyToSender(ctx, msg, `✉️ 请指定目标：特殊使用 ${item.name} 角色名`);
        const featureToggle = mainKvGet("global_feature_toggle", {});
        if (!featureToggle.enable_direct_letter) return seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。");
        const apg = mainKvGet("a_private_group", {});
        if (!Object.values(apg[platform] || {}).some(v => v[0] === targetName)) return seal.replyToSender(ctx, msg, `❌ 未找到目标角色「${targetName}」。`);
        if (!removeFromInv(roleKey, item.code, 1)) return seal.replyToSender(ctx, msg, `❌ 背包中没有可用的「${item.name}」。`);
        const effectsKey = item.code === "SPEC_003" ? "letter_telescope_effects" : "letter_quill_pen_effects";
        const effects = mainKvGet(effectsKey, {});
        if (!effects[targetName]) effects[targetName] = [];
        effects[targetName].push({ applier: roleName, applyTime: Date.now(), itemCode: item.code });
        mainKvSet(effectsKey, effects);
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

        let a_lockedSlots = mainKvGet("a_lockedSlots", {});
        if (!a_lockedSlots[targetKey]) a_lockedSlots[targetKey] = {};
        if (!a_lockedSlots[targetKey][globalDay]) a_lockedSlots[targetKey][globalDay] = [];
        if (!a_lockedSlots[targetKey][globalDay].includes(timeRange)) {
            a_lockedSlots[targetKey][globalDay].push(timeRange);
        }
        mainKvSet("a_lockedSlots", a_lockedSlots);

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

        const phoneTaps = mainKvGet("phone_tap_effects", {});
        phoneTaps[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainKvSet("phone_tap_effects", phoneTaps);

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

        const smsTaps = mainKvGet("sms_tap_effects", {});
        smsTaps[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainKvSet("sms_tap_effects", smsTaps);

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

        const echoWalls = mainKvGet("sms_echo_wall_effects", {});
        echoWalls[targetName] = { ownerRoleName: roleName, platform, remainCount, blurProb };
        mainKvSet("sms_echo_wall_effects", echoWalls);

        return seal.replyToSender(ctx, msg, `🪞 回音壁已贴附！\n目标：${targetName}\n最多截取：${remainCount} 条\n干扰率：${blurProb}%\n（回音壁已消耗）`);
    }

    return seal.replyToSender(ctx, msg, `❌ 未知的特殊道具 [${item.code}]，请联系管理员。`);
};
// ext.cmdMap["特殊使用"] (合入使用子命令)

// ========================
// 合成系统
// ========================

let cmd_reg_craft = seal.ext.newCmdItemInfo();
cmd_reg_craft.name = "注册合成";
cmd_reg_craft.help = "【管理员】注册合成配方\n注册合成 产物代码*描述*材料代码1:数量1,材料代码2:数量2[*限制条件[*成功率]]\n限制格式：attr:属性名:最小值,currency:货币名:最小值\n成功率：0-100，默认100（消耗材料后按此概率获得产物）\n示例：注册合成 高级丹*升级丹药*初级丹:3,金币:100*attr:体力:50*80";
cmd_reg_craft.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// cmd_reg_craft 保留供 合成 注册 子命令调用



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
            const priv = mainKvGet("a_private_group", {})[platform] || {};
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
// ========================
// 攻防系统 - 存储与配置
// ========================

function getAttackDefenseConfig() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return mainKvGet("attack_defense_config", {});
    } catch(e) { return {}; }
}

function saveAttackDefenseConfig(config) {
    const main = getMainExt();
    if (main) mainKvSet("attack_defense_config", config);
}

function getAttackDefenseData() {
    const main = getMainExt();
    if (!main) return { battles: {}, playerStats: {}, playerSkills: {} };
    try {
        return mainKvGet("attack_defense_data", {});
    } catch(e) { return { battles: {}, playerStats: {}, playerSkills: {} }; }
}

function saveAttackDefenseData(data) {
    const main = getMainExt();
    if (main) mainKvSet("attack_defense_data", data);
}

// 技能定义由 rp_archive 管理端写入 skill_defs，机器人只读
function getSkillDefs() {
    try { return mainKvGet("skill_defs", {}); } catch(e) { return {}; }
}

// 玩家基础战斗属性（纯底值，不含装备加成）
function initPlayerBattleAttrs() {
    return { ATK: 50, DEF: 30, AGI: 40, HP: 100, MP: 50, MP_REGEN: 5 };
}

function getPlayerBattleAttrs(name) {
    const all = mainKvGet("battle_attrs", {});
    if (!all[name]) {
        all[name] = initPlayerBattleAttrs();
        mainKvSet("battle_attrs", all);
    }
    return all[name];
}

function savePlayerBattleAttrs(name, attrs) {
    const all = mainKvGet("battle_attrs", {});
    all[name] = attrs;
    mainKvSet("battle_attrs", all);
}

function getPlayerSkills() {
    return mainKvGet("player_skills", {});
}
function savePlayerSkills(skills) {
    mainKvSet("player_skills", skills);
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
    } catch(e) { console.error(`[RPG] getEffectiveBattleAttrs(${playerName}) 计算装备加成失败:`, e.message); }
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

// 受击时降低目标已装备物品的耐久度，耐久归零则自动卸下
function _degradeEquipDurabilityOnHit(battle, targetName) {
    const rk = (battle.roleKeys || {})[targetName] || targetName;
    const main = getMainExt();
    if (!main) return;
    const allEquips = mainKvGet("player_equipments", {});
    const playerEquips = allEquips[rk];
    if (!playerEquips) return;
    const equipReg = getEquipRegistry();
    let changed = false;
    const brokenNames = [];
    for (const slot in playerEquips) {
        const slotEntry = playerEquips[slot];
        if (!slotEntry || !slotEntry.code) continue;
        const equipDef = equipReg[slotEntry.code];
        if (!equipDef || equipDef.durability == null) continue;
        if (slotEntry.currentDurability === undefined) slotEntry.currentDurability = equipDef.durability;
        slotEntry.currentDurability -= 1;
        changed = true;
        if (slotEntry.currentDurability <= 0) {
            slotEntry.currentDurability = 0;
            playerEquips[slot] = null;
            brokenNames.push(equipDef.name);
        }
    }
    if (changed) {
        allEquips[rk] = playerEquips;
        mainKvSet("player_equipments", allEquips);
    }
    if (brokenNames.length) {
        if (!battle.battleLog) battle.battleLog = [];
        battle.battleLog.push(`💔 ${targetName} 的装备【${brokenNames.join("、")}】耐久归零，已损毁！`);
    }
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
        _degradeEquipDurabilityOnHit(battle, targetName);
    }
    return Math.max(0, dmg); // 实际造成伤害（护盾吸收后剩余扣血量）
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
    const _log = mainKvGet("battle_log", []);
    _log.unshift({
        id: battle.id, players: battle.players, winner: winner || null,
        turns: battle.currentTurn, actions: (battle.actions || []).length,
        endedAt: Date.now()
    });
    if (_log.length > 100) _log.length = 100;
    mainKvSet("battle_log", _log);

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
        const pkPlatform = msg.sender.userId.split(':')[0];
        opponents.forEach(opp => {
            const oppUid = getRoleUid(pkPlatform, opp);
            const oppRoleKey = oppUid ? `${pkPlatform}:${oppUid}` : opp;
            addPlayerToBattle(battle.id, opp, oppRoleKey);
        });

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
        delete data.battles[battleId];
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
    const logPrefix = (battle.battleLog && battle.battleLog.length)
        ? battle.battleLog.splice(0).join("\n") + "\n"
        : "";
    if (getAlivePlayersCount(battle) <= 1) {
        const r = resolveBattleEnd(battle);
        saveAttackDefenseData(data);
        return logPrefix + r;
    }
    advanceTurn(battle);
    const next = getCurrentBattlePlayer(battle);
    const limitMsg = checkTurnLimit(battle, data);
    if (limitMsg) { saveAttackDefenseData(data); return logPrefix + limitMsg; }
    processTurnStart(battle, next);
    saveAttackDefenseData(data);
    const nst = battle.playerStates[next];
    return logPrefix + `➡️ 轮到 ${next} 的回合（HP ${nst.hp}/${nst.maxHp}  MP ${nst.mp}/${nst.maxMp}）`;
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
// ext.cmdMap["使用技能"] = cmd_use_skill; (合入技能子命令)

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
// ext.cmdMap["战斗用品"] = cmd_battle_item; (合入战况)

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

    if (getCurrentBattlePlayer(battle) !== player)
        return seal.replyToSender(ctx, msg, `❌ 还没到你的回合，当前：${getCurrentBattlePlayer(battle)}`);

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

    // 只标记自己退出，是否结束整场战斗交给 _afterAction 统一判定（存活人数<=1 才真正结算），
    // 三人及以上混战中不应因为一人投降/逃跑就打断其他人的对战
    battle.playerStates[player].alive = false;
    const tail = _afterAction(data, battle);
    const prefix = isEscape ? `💨 ${player} 成功逃离！` : `🏳️ ${player} 投降！`;
    return seal.replyToSender(ctx, msg, `${prefix}\n\n${tail}`);
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["玩家技能"] = cmd_player_skill; (合入技能子命令)

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
// ext.cmdMap["技能库"] = cmd_skill_lib; (合入技能子命令)

let cmd_my_skills = seal.ext.newCmdItemInfo();
cmd_my_skills.name = "技能";
cmd_my_skills.help = "技能\n技能              查看我的技能\n技能 使用 技能名 [目标]  使用技能\n技能 库            查看技能库\n技能 配置 操作 角色名 技能名  管理员配置";
cmd_my_skills.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);
    if (sub === "使用") return cmd_use_skill.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "库") return cmd_skill_lib.solve(ctx, msg, { getArgN: (_) => "" });
    if (sub === "配置") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_player_skill.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

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
ext.cmdMap["技能"] = cmd_my_skills;

// ========================
// 攻防系统 - 战斗状态
// ========================

let cmd_battle_status = seal.ext.newCmdItemInfo();
cmd_battle_status.name = "战况";
cmd_battle_status.help = "战况\n战况           当前战斗状态\n战况 历史      战斗历史记录\n战况 用品      战斗可用道具";
cmd_battle_status.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);
    if (sub === "历史") return cmd_battle_history.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "用品") return cmd_battle_item.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });

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
ext.cmdMap["战况"] = cmd_battle_status;

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

    if (subCmd === "注册") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_reg_attr.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }
    if (subCmd === "删除") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        const name = cmdArgs.getArgN(2);
        if (!name) return seal.replyToSender(ctx, msg, "❌ 请输入属性名：。属性 删除 名称");
        const defs = getAttrDefs();
        if (!defs[name]) return seal.replyToSender(ctx, msg, `❌ 未找到属性「${name}」`);
        const poolDefs = getPoolDefs();
        const boundPools = Object.values(poolDefs).filter(p => p.type === "tiered" && p.attr === name).map(p => p.name);
        if (boundPools.length) return seal.replyToSender(ctx, msg, `❌ 属性「${name}」正被分段池「${boundPools.join("、")}」绑定，无法删除。`);
        delete defs[name];
        saveAttrDefs(defs);
        return seal.replyToSender(ctx, msg, `✅ 属性「${name}」已删除`);
    }
    if (subCmd === "列表") {
        const attrs = getValidAttrs();
        return seal.replyToSender(ctx, msg, attrs.length ? `📋 已注册属性：${attrs.join("、")}` : "📋 暂无已注册属性。");
    }
    if (subCmd === "设置") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_set_attr.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

    if (subCmd === "改" || subCmd === "修改") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

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
// ext.cmdMap["战斗历史"] = cmd_battle_history; (合入战况)

// ========================
// 一键初始化 - 快速启用攻防系统
// ========================

let cmd_quick_init = seal.ext.newCmdItemInfo();
cmd_quick_init.name = "一键初始化";
cmd_quick_init.help = "【管理员】一键初始化攻防系统 - 注册属性和回血药\n一键初始化\n  将自动创建：\n  · 5个RPG属性（HP、MP、ATK、DEF、AGI）\n  · 4种回血药（小、中、大、满）\n  · 启用攻防系统";
cmd_quick_init.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

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
            uses: -1,
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
        return mainKvGet("equipment_registry", {});
    } catch(e) { return {}; }
}

function saveEquipRegistry(reg) {
    const main = getMainExt();
    if (main) mainKvSet("equipment_registry", reg);
}

function getEquipConfig() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return mainKvGet("equipment_config", {});
    } catch(e) { return {}; }
}

function saveEquipConfig(config) {
    const main = getMainExt();
    if (main) mainKvSet("equipment_config", config);
}

function getEquipSlots() {
    const main = getMainExt();
    if (!main) return ["head", "chest", "hand", "leg", "foot"];
    try {
        const slots = mainKvGet("equipment_slots", []);
        return slots.length > 0 ? slots : ["head", "chest", "hand", "leg", "foot"];
    } catch(e) {
        return ["head", "chest", "hand", "leg", "foot"];
    }
}

function saveEquipSlots(slots) {
    const main = getMainExt();
    if (main) mainKvSet("equipment_slots", slots);
}

function getSlotDisplayNames() {
    const main = getMainExt();
    if (!main) return {};
    try {
        return mainKvGet("equipment_slot_names", {});
    } catch(e) {
        return {};
    }
}

function saveSlotDisplayNames(names) {
    const main = getMainExt();
    if (main) mainKvSet("equipment_slot_names", names);
}

function getSlotDisplayName(slot) {
    const names = getSlotDisplayNames();
    return names[slot] || slot;
}

function getPlayerEquips(roleKey) {
    const main = getMainExt();
    if (!main) return null;
    try {
        const data = mainKvGet("player_equipments", {});
        if (!data[roleKey]) {
            const slots = getEquipSlots();
            data[roleKey] = {};
            slots.forEach(slot => {
                data[roleKey][slot] = null;
            });
            mainKvSet("player_equipments", data);
        }
        return data[roleKey];
    } catch(e) { return null; }
}

function savePlayerEquips(roleKey, equips) {
    const main = getMainExt();
    if (!main) return;
    try {
        const data = mainKvGet("player_equipments", {});
        data[roleKey] = equips;
        mainKvSet("player_equipments", data);
    } catch(e) { console.error(`[RPG] savePlayerEquips(${roleKey}) 保存失败:`, e.message); }
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
cmd_equip.help = "装备或查看装备\n装备 <装备名或代码>    - 穿上装备\n装备 脱 <槽位>         - 卸下装备\n装备                    - 显示当前装备及属性加成\n装备 列表（管理员）     - 查看所有可用装备\n装备 详情 <装备码>      - 查看装备详细信息\n\n💡 槽位由管理员定义，执行「槽位 查看」看可用槽位。";
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

    // 子命令路由：脱/注册/槽位/修复 合入
    if (subCmd === "脱") return doUnequip(ctx, msg, cmdArgs.getArgN(2));
    if (subCmd === "注册") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return doRegisterEquip(ctx, msg, cmdArgs.args.slice(1).join(' ').trim());
    }
    if (subCmd === "槽位") {
        return doEquipSlots(ctx, msg, cmdArgs.getArgN(2), cmdArgs.getArgN(3), cmdArgs.getArgN(4));
    }
    if (subCmd === "修复") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return doRepair(ctx, msg, cmdArgs.getArgN(2), cmdArgs.getArgN(3));
    }

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
                    const durDisp = (equip.durability != null && equipped.currentDurability !== undefined)
                        ? ` [耐久${equipped.currentDurability}/${equip.durability}]` : "";
                    info += `${getSlotEmoji(slot)} ${getSlotName(slot)}: ${equip.name}${durDisp} (${bonusStr})\n`;
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

        // 检查背包持有
        if (getInvCount(roleKey, equip.code) < 1) {
            return seal.replyToSender(ctx, msg, `❌ 你的背包里没有 ${equip.name}，请先通过商城购买或获得后再装备。`);
        }
        removeFromInv(roleKey, equip.code, 1);

        // 若原槽位有装备则归还背包
        if (oldEquip && oldEquip.code) {
            const oldDef = registry[oldEquip.code];
            if (oldDef) {
                const invs = getInvAll();
                const inv = invs[roleKey] || [];
                const returnEntry = { code: oldEquip.code, count: 1, remainingUses: -1 };
                if (oldDef.durability != null && oldEquip.currentDurability !== undefined) {
                    returnEntry.currentDurability = oldEquip.currentDurability;
                }
                inv.push(returnEntry);
                invs[roleKey] = inv;
                saveInvAll(invs);
            }
        }

        equips[slot] = { code: equip.code };
        if (equip.durability != null) equips[slot].currentDurability = equip.durability;
        savePlayerEquips(roleKey, equips);

        let msg_text = `✅ 你穿上了 ${equip.name}！\n\n`;
        const bonus = getEquipBonus(equip);
        const bonusStr = Object.entries(bonus).map(([k, v]) => `${k}${v >= 0 ? '+' : ''}${v}`).join(', ');
        msg_text += `属性加成: ${bonusStr}`;

        if (oldEquip && oldEquip.code && registry[oldEquip.code]) {
            msg_text += `\n\n(原装备 ${registry[oldEquip.code].name} 已卸下并归还背包)`;
        }

        return seal.replyToSender(ctx, msg, msg_text);
    }

    // 列表
    if (subCmd === "列表") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

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

function doUnequip(ctx, msg, slot) {
    const player = getRoleName(ctx, msg);
    if (!player) return seal.replyToSender(ctx, msg, "❌ 无法获取你的角色信息。");

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
    const equipSlotData = equips[slot];
    const registry = getEquipRegistry();
    const equip = registry[equipCode];

    equips[slot] = null;
    savePlayerEquips(roleKey, equips);

    // 装备归还背包（保留当前耐久度）
    const invs = getInvAll();
    const inv = invs[roleKey] || [];
    const returnEntry = { code: equipCode, count: 1, remainingUses: -1 };
    if (equip && equip.durability != null && equipSlotData.currentDurability !== undefined) {
        returnEntry.currentDurability = equipSlotData.currentDurability;
    }
    inv.push(returnEntry);
    invs[roleKey] = inv;
    saveInvAll(invs);

    let msg_text = `✅ 你卸下了 ${equip ? equip.name : equipCode}，已归还背包。`;
    return seal.replyToSender(ctx, msg, msg_text);
}

// ========================
// 装备系统 - 管理员命令：注册装备
// ========================

const cmd_register_equip_help = "【管理员】注册新装备\n注册装备 <装备名>*<描述>*<槽位>*<基础属性>\n\n属性格式: ATK+15,DEF+10 (用逗号分隔多个属性)\n属性必须已注册，执行「我创建属性」可注册新属性\n槽位：执行「槽位 查看」查看所有可用槽位\n\n示例:\n注册装备 铁制短剑*普通短剑*hand*ATK+15\n注册装备 钢铁胸甲*防御胸甲*chest*DEF+20,HP+50\n注册装备 智者法杖*法术武器*hand*智力+20,MP+50";
function doRegisterEquip(ctx, msg, inputStr) {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const input = (inputStr || "").trim();

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

    // 验证所有属性是否已注册（战斗基础属性不需要在 rpg_attr_defs 中注册）
    const BATTLE_ATTRS = new Set(["ATK","DEF","AGI","HP","MP","MP_REGEN"]);
    const attrDefs = getAttrDefs();
    const allAttrNames = new Set([...Object.keys(baseAttrs)]);

    const unregisteredAttrs = [];
    for (const attrName of allAttrNames) {
        if (!BATTLE_ATTRS.has(attrName) && !attrDefs[attrName]) {
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
}

// ========================
// 装备系统 - 管理员命令：槽位管理
// ========================

const cmd_equip_slots_help = "【管理员】管理装备槽位\n槽位 查看               - 查看所有槽位\n槽位 添加 <槽位码> <名称> - 添加新槽位\n槽位 删除 <槽位码>      - 删除槽位\n槽位 重置              - 重置为默认5个槽位\n\n示例:\n槽位 添加 ring1 戒指1\n槽位 添加 wing 翅膀\n槽位 删除 ring1";
function doEquipSlots(ctx, msg, subCmd, arg2, arg3) {
    let slots = getEquipSlots();
    let slotNames = getSlotDisplayNames();

    if (subCmd === "查看" || !subCmd) {
        let info = `📋 装备槽位列表 (${slots.length}个):\n\n`;
        slots.forEach((slot, idx) => {
            const displayName = slotNames[slot] || slot;
            info += `${idx + 1}. [${slot}] ${displayName}\n`;
        });
        return seal.replyToSender(ctx, msg, info);
    }

    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    if (subCmd === "添加") {
        const slotCode = arg2;
        const slotName = arg3;

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
        const slotCode = arg2;

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
                const data = mainKvGet("player_equipments", {});
                for (const roleKey in data) {
                    delete data[roleKey][slotCode];
                }
                mainKvSet("player_equipments", data);
            } catch(e) { console.error(`[RPG] 删除槽位 ${slotCode} 时清理玩家装备数据失败:`, e.message); }
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

    return seal.replyToSender(ctx, msg, cmd_equip_slots_help);
}

const cmd_repair_help = "【管理员】修复装备耐久度\n修复 <角色名> [槽位码]  - 恢复指定角色全部（或指定槽位）装备耐久到最大值";
function doRepair(ctx, msg, targetRole, slotFilterArg) {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    if (!targetRole) return seal.replyToSender(ctx, msg, "❌ 请指定角色名。");
    const slotFilter = slotFilterArg || null;

    const allEquips = mainKvGet("player_equipments", {});
    const equipReg = getEquipRegistry();
    const platform = msg.platform;
    const targetUid = getRoleUid(platform, targetRole);
    if (!targetUid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetRole}」。`);
    const rk = `${platform}:${targetUid}`;
    const playerEquips = allEquips[rk];
    if (!playerEquips) return seal.replyToSender(ctx, msg, `❌ 角色「${targetRole}」暂无装备记录。`);

    const repaired = [];
    for (const slot in playerEquips) {
        if (slotFilter && slot !== slotFilter) continue;
        const slotEntry = playerEquips[slot];
        if (!slotEntry || !slotEntry.code) continue;
        const equipDef = equipReg[slotEntry.code];
        if (!equipDef || equipDef.durability == null) continue;
        slotEntry.currentDurability = equipDef.durability;
        repaired.push(`${getSlotName(slot)}·${equipDef.name}`);
    }
    if (!repaired.length) return seal.replyToSender(ctx, msg, `⚙️ 没有找到需要修复的装备${slotFilter ? `（槽位：${slotFilter}）` : ""}。`);
    allEquips[rk] = playerEquips;
    mainKvSet("player_equipments", allEquips);
    return seal.replyToSender(ctx, msg, `🔧 已修复「${targetRole}」的装备：${repaired.join("、")}`);
}

// ========================
// 升级系统 (PlayerLevel)
// ========================

// 获取升级规则
function getLevelUpRules() {
    const main = getMainExt();
    return main ? mainKvGet("level_up_rules", {"max_level":100,"enabled":true,"level_up_rules":{}}) : {};
}

function saveLevelUpRules(rules) {
    const main = getMainExt();
    if (main) mainKvSet("level_up_rules", rules);
}

// 获取玩家当前等级（新结构：uid 为 key）
function getPlayerLevel(uid) {
    const main = getMainExt();
    if (!main) return 1;
    const data = mainKvGet("player_level", {});
    return data[uid] || 1;
}

function setPlayerLevel(uid, level) {
    const main = getMainExt();
    if (!main) return;
    const data = mainKvGet("player_level", {});
    data[uid] = level;
    mainKvSet("player_level", data);
}

// 获取玩家升级历史（新结构：uid 为 key）
function getLevelHistory(uid) {
    const main = getMainExt();
    if (!main) return [];
    const data = mainKvGet("player_level_history", {});
    return data[uid] || [];
}

function addLevelHistory(uid, record) {
    const main = getMainExt();
    if (!main) return;
    const data = mainKvGet("player_level_history", {});
    if (!data[uid]) data[uid] = [];
    data[uid].push(record);
    mainKvSet("player_level_history", data);
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    return cmd_upload_level_rule(msg, cmdArgs, ctx);
};
// ext.cmdMap["上传升级等级"] = cmd_upload_level; (合入升级子命令)

let cmd_view_level = seal.ext.newCmdItemInfo();
cmd_view_level.name = "查看升级配置";
cmd_view_level.help = "查看升级配置\n查看升级配置 [等级号]";
cmd_view_level.solve = (ctx, msg, cmdArgs) => {
    return cmd_view_level_rule(ctx, msg, cmdArgs);
};
// ext.cmdMap["查看升级配置"] = cmd_view_level; (合入升级子命令)

let cmd_level_listing = seal.ext.newCmdItemInfo();
cmd_level_listing.name = "升级列表";
cmd_level_listing.help = "查看所有已配置的升级等级";
cmd_level_listing.solve = (ctx, msg, cmdArgs) => {
    return cmd_level_list(ctx, msg, cmdArgs);
};
// ext.cmdMap["升级列表"] = cmd_level_listing; (合入升级子命令)

let cmd_do_upgrade = seal.ext.newCmdItemInfo();
cmd_do_upgrade.name = "升级";
cmd_do_upgrade.help = "升级一次\n格式：升级";
cmd_do_upgrade.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);
    if (sub === "列表") return cmd_level_listing.solve(ctx, msg, { getArgN: (_) => "" });
    if (sub === "信息") return cmd_level_info.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "历史") return cmd_level_history.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "上传") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_upload_level.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }
    if (sub === "配置") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_view_level.solve(ctx, msg, { getArgN: (_) => "" });
    }
    if (sub === "设置") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_level_settings.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }

    return cmd_do_levelup(msg, cmdArgs, ctx);
};
ext.cmdMap["升级"] = cmd_do_upgrade;

let cmd_level_info = seal.ext.newCmdItemInfo();
cmd_level_info.name = "查看升级信息";
cmd_level_info.help = "查看升级进度和下一等级要求\n格式：查看升级信息";
cmd_level_info.solve = (ctx, msg, cmdArgs) => {
    return cmd_levelup_info(msg, cmdArgs, ctx);
};
// ext.cmdMap["查看升级信息"] = cmd_level_info; (合入升级子命令)

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
// ext.cmdMap["升级历史"] = cmd_level_history; (合入升级子命令)

let cmd_level_settings = seal.ext.newCmdItemInfo();
cmd_level_settings.name = "升级系统设置";
cmd_level_settings.help = "【管理员】升级系统全局设置\n升级系统设置 开启|关闭\n升级系统设置 最大等级 <数字>";
cmd_level_settings.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["升级系统设置"] = cmd_level_settings; (合入升级子命令)

// ========================
// 角色档案
// ========================
let cmd_profile = seal.ext.newCmdItemInfo();
cmd_profile.name = "角色档案";
cmd_profile.help = "【管理员】查看角色综合档案\n角色档案 角色名";
cmd_profile.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    const roleName = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const platform = msg.platform;
    const uid = getRoleUid(platform, roleName);
    if (!uid) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${roleName}」。`);
    const primaryUid = getPrimaryUid(platform, uid);
    const roleKey = `${platform}:${primaryUid}`;

    // 属性（含装备加成）
    const defs = getAttrDefs();
    const allAttrs = getCharAttrs();
    const myAttrs = allAttrs[primaryUid] || {};
    const equipBonus = getTotalEquipBonus(getPlayerEquips(roleKey) || {}, getEquipRegistry());
    const attrStr = Object.keys(defs).length
        ? Object.keys(defs).map(k => {
            const base = myAttrs[k] ?? defs[k].default ?? 0;
            const bonus = equipBonus[k] || 0;
            return `${k}: ${base + bonus}${bonus ? ` (${bonus > 0 ? '+' : ''}${bonus})` : ''}`;
        }).join(" | ")
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
        const relData = mainKvGet("relationship_lines", {});
        const myRels = relData[platform]?.[uid] || {};
        relCount = Object.keys(myRels).length;
        for (const rel of Object.values(myRels)) {
            if (rel.confirmed) confirmed++;
            if (rel.initiator === roleName) initiated++; else received++;
        }
    } catch(e) { console.error(`[RPG] 读取 ${roleName} 关系线数据失败:`, e.message); }

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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
        const apg = mainKvGet("a_private_group", {});
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
    const primary = mainKvGet("scheduled_collections", null);
    if (primary !== null) return primary;
    // 兼容旧版本：数据曾存在 changriRPG 本地 ext，此处一次性迁移到主插件共享存储
    let legacy = {};
    try { legacy = JSON.parse(ext.storageGet("scheduled_collections") || "{}"); }
    catch (e) { console.error("[定时收集] 旧数据解析失败:", e.message); }
    if (Object.keys(legacy).length) mainKvSet("scheduled_collections", legacy);
    return legacy;
}
function saveCollections(cols) {
    mainKvSet("scheduled_collections", cols);
}

function sendToAdminGroupRPG(platform, text) {
    const main = getMainExt();
    if (!main) return;
    const gid = mainKvGet("adminAnnounceGroupId", null);
    if (!gid) return;
    try {
        const ep = getSafeEndPoint(platform);
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
    const apg = mainKvGet("a_private_group", {});
    const groups = apg[platform] || {};
    if (withAt) {
        // 按群分组，每个玩家各自收到艾特
        Object.entries(groups).forEach(([uid, info]) => {
            const gid = info[1];
            if (!gid) return;
            try {
                const ep = getSafeEndPoint(platform);
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
                const ep = getSafeEndPoint(platform);
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["创建定时收集"] = cmd_collection_create; (合入定时收集子命令)

// 管理员：关闭定时收集
let cmd_collection_close = seal.ext.newCmdItemInfo();
cmd_collection_close.name = "关闭定时收集";
cmd_collection_close.help = "【管理员】关闭并删除定时收集\n关闭定时收集 项目名字";
cmd_collection_close.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    const name = cmdArgs.getArgN(1);
    if (!name) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const cols = getCollections();
    if (!cols[name]) return seal.replyToSender(ctx, msg, `❌ 找不到收集「${name}」。`);
    delete cols[name];
    saveCollections(cols);
    seal.replyToSender(ctx, msg, `✅ 定时收集「${name}」已关闭。`);
    return seal.ext.newCmdExecuteResult(true);
};
// ext.cmdMap["关闭定时收集"] = cmd_collection_close; (合入定时收集子命令)

// 管理员：查看定时收集（无参数=列表，有参数=查看提交内容）
let cmd_collection_list = seal.ext.newCmdItemInfo();
cmd_collection_list.name = "查看定时收集";
cmd_collection_list.help = "【管理员】查看定时收集\n查看定时收集          — 列出所有收集\n查看定时收集 项目名字  — 查看该项目的提交记录";
cmd_collection_list.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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
// ext.cmdMap["查看定时收集"] = cmd_collection_list; (合入定时收集子命令)

// 玩家：提交定时收集内容
let cmd_collection_submit = seal.ext.newCmdItemInfo();
cmd_collection_submit.name = "定时收集";
cmd_collection_submit.help = "提交定时收集内容\n定时收集 项目名字 内容\n示例：定时收集 心情调查 今天很开心！";
cmd_collection_submit.solve = (ctx, msg, cmdArgs) => {
    const sub = cmdArgs.getArgN(1);
    if (sub === "查看") return cmd_collection_list.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    if (sub === "创建") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_collection_create.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }
    if (sub === "关闭") {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return cmd_collection_close.solve(ctx, msg, { getArgN: (n) => cmdArgs.getArgN(n + 1) });
    }
    const name = sub;
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
