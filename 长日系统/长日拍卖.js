// ==UserScript==
// @name         拍卖系统
// @author       长日将尽
// @version      1.0.0
// @description  拍卖系统（卫星插件）。所有数据存储在主插件 changri 中。
// @timestamp    1750291200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E6%8B%8D%E5%8D%96.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E6%8B%8D%E5%8D%96.js
// ==/UserScript==

let ext = seal.ext.find('auction_system');
if (!ext) {
    ext = seal.ext.new("auction_system", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()                      { return globalThis.__changriApi || null; }
function mainStorGet(key)              { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val)         { getApi()?.kvSetRaw(key, val); }
function isUserAdmin(ctx, msg)         { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function isArchiveEnabled()            { return getApi()?.isArchiveEnabled() ?? false; }
function postToArchive(path, body)     { return getApi()?.postToArchive(path, body); }
function ws(postData, ctx, msg, ok, err) { return getApi()?.ws(postData, ctx, msg, ok, err); }
function getRoleName(ctx, msg)         { return getApi()?.getRoleName(ctx, msg) ?? null; }
function getPrimaryUid(platform, uid)  { return getApi()?.getPrimaryUid(platform, uid) ?? uid; }
// 以下两个需要读插件配置，无法通过共享 API 获取
function _mainExt()        { return seal.ext.find('changri'); }
function getArchiveBase()  { const m = _mainExt(); return m ? (seal.ext.getStringConfig(m, "RP存档服务器地址") || "").replace(/\/$/, "") : ""; }
function getArchiveToken() { const m = _mainExt(); return m ? (seal.ext.getStringConfig(m, "RP存档Token") || "") : ""; }

const MAX_CONCURRENT_AUCTIONS = 10; // 同时进行中的拍卖上限

// ========================
// RPG背包辅助函数（本地副本，使用 mainStorGet/Set）
// ========================

function getRegistry_rpg() {
    return JSON.parse(mainStorGet("item_registry") || "{}");
}
function findItem_rpg(reg, input) {
    if (!input) return null;
    const code = input.toUpperCase();
    if (reg[code]) return reg[code];
    return Object.values(reg).find(r => r.name === input) || null;
}
function findCurrencyByName_rpg(name) {
    const reg = getRegistry_rpg();
    return Object.values(reg).find(i => i.type === "currency" && i.name === name) || null;
}
function getInvAll_rpg() {
    return JSON.parse(mainStorGet("global_inventories") || "{}");
}
function saveInvAll_rpg(invs) {
    mainStorSet("global_inventories", JSON.stringify(invs));
}
function getInvCount_rpg(roleKey, code) {
    const inv = getInvAll_rpg()[roleKey] || [];
    return inv.filter(e => e.code === code).reduce((s, e) => s + e.count, 0);
}
function removeFromInv_rpg(roleKey, code, count) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    let remaining = count;
    for (const entry of inv.filter(e => e.code === code).sort((a, b) => (b.remainingUses || 0) - (a.remainingUses || 0))) {
        if (remaining <= 0) break;
        const take = Math.min(entry.count, remaining);
        entry.count -= take;
        remaining -= take;
    }
    invs[roleKey] = inv.filter(e => e.count > 0);
    saveInvAll_rpg(invs);
}
function addToInv_local(roleKey, code, count) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    const reg = getRegistry_rpg();
    const itemInfo = reg[code];
    if (!itemInfo) { console.error(`[拍卖] 尝试添加不存在的物品代码: ${code}`); return false; }
    const initialUses = itemInfo.maxUses ?? -1;
    const entry = inv.find(e => e.code === code && (e.remainingUses ?? -1) === initialUses);
    if (entry) { entry.count += count; } else { inv.push({ code, count, remainingUses: initialUses }); }
    invs[roleKey] = inv;
    saveInvAll_rpg(invs);
    return true;
}

// ========================
// 🔨 拍卖系统
// ========================

function _addToInvWithExpiry(roleKey, code, count, expiresAt) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    const reg = getRegistry_rpg();
    const itemInfo = reg[code];
    if (!itemInfo) { console.error(`[拍卖] 找不到物品代码: ${code}`); return; }
    const initialUses = itemInfo.maxUses ?? -1;
    inv.push({ code, count, remainingUses: initialUses, expiresAt });
    invs[roleKey] = inv;
    saveInvAll_rpg(invs);
}

function pruneExpiredAuctionItems() {
    const invs = getInvAll_rpg();
    const now = Date.now();
    let changed = false;
    for (const roleKey of Object.keys(invs)) {
        const before = invs[roleKey].length;
        invs[roleKey] = invs[roleKey].filter(e => !e.expiresAt || e.expiresAt > now);
        if (invs[roleKey].length !== before) changed = true;
    }
    if (changed) saveInvAll_rpg(invs);
}

function getAuctions() {
    return JSON.parse(mainStorGet("auction_items") || "{}");
}
function saveAuctions(data) {
    mainStorSet("auction_items", JSON.stringify(data));
}
function getAuctionSettings() {
    return {
        displayGroup: JSON.parse(mainStorGet("song_group_id") || "null") || "",
        allowAnon: mainStorGet("auction_allow_anon") !== "false",
        broadcast: mainStorGet("auction_broadcast") !== "false",
        showTopBidder: mainStorGet("auction_show_top_bidder") !== "false",
        currency: mainStorGet("auction_currency") || "金币"
    };
}

function _settleSingleAuction(ctx, msg, settings, auctions, id, item) {
    const platform = msg.platform;
    const bids = item.bids || [];
    if (bids.length === 0) {
        item.status = "unsold";
        _announceAuction(ctx, msg, settings, `🔨 拍卖结束 | ${id} 「${item.name}」\n💸 无人出价，已流拍。`);
        return `${id} 「${item.name}」流拍（无人出价）`;
    }

    const currencyItem = findCurrencyByName_rpg(settings.currency);
    let winner = null;
    if (currencyItem) {
        for (const bid of bids) {
            const roleKey = `${platform}:${bid.uid}`;
            if (getInvCount_rpg(roleKey, currencyItem.code) >= bid.amount) { winner = bid; break; }
        }
    } else {
        const attrs = JSON.parse(mainStorGet("sys_character_attrs") || "{}");
        for (const bid of bids) {
            if ((attrs[bid.uid]?.[settings.currency] || 0) >= bid.amount) { winner = bid; break; }
        }
    }

    if (!winner) {
        item.status = "unsold";
        _announceAuction(ctx, msg, settings, `🔨 拍卖结束 | ${id} 「${item.name}」\n💸 所有出价者余额不足，已流拍。`);
        return `${id} 「${item.name}」流拍（余额不足）`;
    }

    if (currencyItem) {
        removeFromInv_rpg(`${platform}:${winner.uid}`, currencyItem.code, winner.amount);
    } else {
        const attrs = JSON.parse(mainStorGet("sys_character_attrs") || "{}");
        if (!attrs[winner.uid]) attrs[winner.uid] = {};
        attrs[winner.uid][settings.currency] = (attrs[winner.uid][settings.currency] || 0) - winner.amount;
        mainStorSet("sys_character_attrs", JSON.stringify(attrs));
    }

    const roleKey = `${platform}:${winner.uid}`;
    const itemCode = item.code || item.name.toUpperCase();
    if (item.expireHours) {
        const expiresAt = Date.now() + item.expireHours * 3600 * 1000;
        _addToInvWithExpiry(roleKey, itemCode, 1, expiresAt);
    } else {
        addToInv_local(roleKey, itemCode, 1);
    }
    item.status = "sold";
    item.winner = { roleName: winner.roleName, amount: winner.amount, isAnon: winner.isAnon };

    const winnerDisplay = winner.isAnon ? "匿名玩家" : `「${winner.roleName}」`;
    const expireNote = item.expireHours ? `\n⏳ 物品将在 ${item.expireHours} 小时后失效` : "";
    _announceAuction(ctx, msg, settings,
        `🎉 拍卖成交公告\n${"━".repeat(16)}\n📦 ${id} 「${item.name}」\n🏆 最终得主：${winnerDisplay}\n💰 成交价：${winner.amount} ${settings.currency}\n${"━".repeat(16)}\n物品已放入得主背包。${expireNote}`);
    return `${id} 「${item.name}」→ ${winnerDisplay} ${winner.amount} ${settings.currency}`;
}

function settleExpiredAuctions(ctx, msg) {
    pruneExpiredAuctionItems();
    const auctions = getAuctions();
    const now = Date.now();
    const settings = getAuctionSettings();
    const summary = [];
    let changed = false;
    for (const [id, item] of Object.entries(auctions)) {
        if (item.status !== "active") continue;
        if (now < item.endTime) continue;
        summary.push(_settleSingleAuction(ctx, msg, settings, auctions, id, item));
        changed = true;
    }
    if (changed) saveAuctions(auctions);
    return summary;
}

function _notifyAuction(ctx, msg, settings, text) {
    if (!settings.displayGroup || !settings.broadcast) return;
    ws({ action: "send_group_msg", params: { group_id: parseInt(settings.displayGroup), message: text } }, ctx, msg, "");
}
function _announceAuction(ctx, msg, settings, text) {
    if (!settings.displayGroup) return;
    ws({ action: "send_group_msg", params: { group_id: parseInt(settings.displayGroup), message: text } }, ctx, msg, "");
}

function _nextAuctionId(auctions) {
    const nums = Object.keys(auctions).map(k => parseInt(k.replace('#', ''))).filter(n => !isNaN(n));
    return `#${nums.length > 0 ? Math.max(...nums) + 1 : 1}`;
}

function _parseAuctionItem(raw) {
    const parts = raw.trim().split('%');
    if (parts.length < 4) return { err: `格式错误（需至少4段，用%分隔）：${raw}` };
    const [itemInput, sp, mi, dur, expStr] = parts;
    const startPrice = parseInt(sp), minIncrement = parseInt(mi), durationHours = parseFloat(dur);
    if (!itemInput.trim()) return { err: "物品码/名称为空" };
    if (isNaN(startPrice) || startPrice < 0) return { err: `起拍价无效：${sp}` };
    if (isNaN(minIncrement) || minIncrement < 1) return { err: `最低加价无效：${mi}` };
    if (isNaN(durationHours) || durationHours <= 0) return { err: `时长无效：${dur}` };
    let expireHours = null;
    if (expStr !== undefined && expStr.trim() !== '') {
        expireHours = parseFloat(expStr);
        if (isNaN(expireHours) || expireHours <= 0) return { err: `失效时长无效：${expStr}` };
    }
    return { itemInput: itemInput.trim(), startPrice, minIncrement, durationHours, expireHours };
}

// ========================
// 拍卖管理指令
// ========================

let cmd_add_auction = seal.ext.newCmdItemInfo();
cmd_add_auction.name = "添加拍卖物品";
cmd_add_auction.help = "。添加拍卖物品 物品码或名称%起拍价%最低加价%时长(h)[%失效时长(h)]\n批量：多件用$分隔\n例：。添加拍卖物品 ITEM_001%100%10%24\n带失效：。添加拍卖物品 ITEM_001%100%10%24%72";
cmd_add_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"); return seal.ext.newCmdExecuteResult(true); }
    const inputArg = cmdArgs.args.slice(1).join(' ').trim();
    if (!inputArg) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const auctions = getAuctions();
    const activeCount = Object.values(auctions).filter(a => a.status === "active").length;
    const reg = getRegistry_rpg();
    const items = inputArg.includes('$') ? inputArg.split('$') : [inputArg];
    const results = { success: 0, failed: 0, details: [] };
    const now = Date.now();

    for (const item of items) {
        if (!item.trim()) continue;
        if (activeCount + results.success >= MAX_CONCURRENT_AUCTIONS) { results.details.push(`❌ 已达${MAX_CONCURRENT_AUCTIONS}件同时上限，剩余未添加`); results.failed += items.length - results.success - results.failed; break; }
        const parsed = _parseAuctionItem(item);
        if (parsed.err) { results.details.push(`❌ ${parsed.err}`); results.failed++; continue; }
        const regItem = findItem_rpg(reg, parsed.itemInput);
        if (!regItem) { results.details.push(`❌ 未找到物品「${parsed.itemInput}」，请先上载物品`); results.failed++; continue; }
        const id = _nextAuctionId(auctions);
        const canResell = regItem.allowSecondhand === true;
        auctions[id] = { id, code: regItem.code, name: regItem.name, desc: regItem.desc || "", startPrice: parsed.startPrice, minIncrement: parsed.minIncrement, durationHours: parsed.durationHours, expireHours: parsed.expireHours, canResell, startTime: now, endTime: now + parsed.durationHours * 3600 * 1000, bids: [], status: "active", winner: null };
        const resellText = canResell ? "✅ 可二手" : "❌ 不可二手";
        const expireText = parsed.expireHours ? `⏳ 得主 ${parsed.expireHours}h 后失效` : "永久有效";
        results.details.push(`✅ ${id} [${regItem.code}]「${regItem.name}」起拍 ${parsed.startPrice}，最低加价 ${parsed.minIncrement}，时长 ${parsed.durationHours}h | ${resellText} | ${expireText}`);
        results.success++;
    }

    if (results.success > 0) saveAuctions(auctions);
    let rep = items.length > 1 ? `📦 批量添加 ✅${results.success} ❌${results.failed}\n\n` : "";
    rep += results.details.join('\n');
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["添加拍卖物品"] = cmd_add_auction;

let cmd_del_auction = seal.ext.newCmdItemInfo();
cmd_del_auction.name = "删除拍卖物品";
cmd_del_auction.help = "。删除拍卖物品 编号（如 #1）";
cmd_del_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"); return seal.ext.newCmdExecuteResult(true); }
    const id = cmdArgs.getArgN(1);
    if (!id) { seal.replyToSender(ctx, msg, "格式：。删除拍卖物品 #编号"); return seal.ext.newCmdExecuteResult(true); }
    const auctions = getAuctions();
    if (!auctions[id]) { seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${id}`); return seal.ext.newCmdExecuteResult(true); }
    const name = auctions[id].name;
    delete auctions[id];
    saveAuctions(auctions);
    seal.replyToSender(ctx, msg, `✅ 已删除 ${id} 「${name}」`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除拍卖物品"] = cmd_del_auction;

let cmd_settle_auction = seal.ext.newCmdItemInfo();
cmd_settle_auction.name = "结算拍卖";
cmd_settle_auction.help = "。结算拍卖 #编号 —— 手动结算指定拍卖（无需到期）";
cmd_settle_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"); return seal.ext.newCmdExecuteResult(true); }
    const id = cmdArgs.getArgN(1);
    if (!id) { seal.replyToSender(ctx, msg, "格式：。结算拍卖 #编号"); return seal.ext.newCmdExecuteResult(true); }
    const auctions = getAuctions();
    const item = auctions[id];
    if (!item) { seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${id}`); return seal.ext.newCmdExecuteResult(true); }
    if (item.status !== "active") { seal.replyToSender(ctx, msg, `❌ ${id} 已结算（状态：${item.status}）`); return seal.ext.newCmdExecuteResult(true); }
    const settings = getAuctionSettings();
    const result = _settleSingleAuction(ctx, msg, settings, auctions, id, item);
    saveAuctions(auctions);
    seal.replyToSender(ctx, msg, `✅ 结算完成：${result}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结算拍卖"] = cmd_settle_auction;


// ========================
// 玩家出价指令（无前缀，通过 onNotCommandReceived 处理）
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();
    const platform = msg.platform;
    const _rawUid = msg.sender.userId.replace(`${platform}:`, '');
    const uid = getPrimaryUid(platform, _rawUid);

    if (raw === "查看拍卖") {
        settleExpiredAuctions(ctx, msg);
        const auctions = getAuctions();
        const settings = getAuctionSettings();
        const now = Date.now();
        const activeItems = Object.values(auctions).filter(a => a.status === "active");
        if (activeItems.length === 0) return seal.replyToSender(ctx, msg, "📭 当前没有进行中的拍卖");
        const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
        const bot = "长日将尽", uin = "10001";
        const nodes = [
            { type: "node", data: { name: bot, uin, content: `🔨 当前拍卖（${activeItems.length}件）\n${"━".repeat(14)}\n货币：${settings.currency}\n发送「实名出价 价格 编号」或「匿名出价 价格 编号」参与竞拍` } },
            ...activeItems.map(item => {
                const remain = Math.max(0, item.endTime - now);
                const remainText = remain > 3600000 ? `${Math.ceil(remain / 3600000)}小时` : `${Math.ceil(remain / 60000)}分钟`;
                const topBid = item.bids[0];
                let bidLine = topBid
                    ? `当前出价：${topBid.amount} ${settings.currency}` + (settings.showTopBidder && !topBid.isAnon ? `（${topBid.roleName}）` : "")
                    : `起拍价：${item.startPrice} ${settings.currency}（尚无出价）`;
                return { type: "node", data: { name: bot, uin, content: `${item.id} 「${item.name}」\n📝 ${item.desc}\n💰 起拍：${item.startPrice} | 最低加价：${item.minIncrement}\n${bidLine}\n⏰ 剩余：${remainText}` } };
            })
        ];
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
        return;
    }

    if (raw.startsWith("实名出价") || raw.startsWith("匿名出价")) {
        const isAnon = raw.startsWith("匿名出价");
        const rest = raw.slice(4).trim();
        const parts = rest.split(/\s+/);
        const amountStr = parts[0], auctionId = parts[1];
        if (!amountStr || !auctionId) return seal.replyToSender(ctx, msg, `格式：${isAnon ? "匿名" : "实名"}出价 价格 编号\n例：${isAnon ? "匿名" : "实名"}出价 150 #1`);
        const amount = parseInt(amountStr);
        if (isNaN(amount) || amount <= 0) return seal.replyToSender(ctx, msg, "❌ 出价必须是正整数");

        settleExpiredAuctions(ctx, msg);
        const auctions = getAuctions();
        const settings = getAuctionSettings();
        const item = auctions[auctionId];
        if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${auctionId}`);
        if (item.status !== "active") return seal.replyToSender(ctx, msg, "❌ 该物品拍卖已结束");
        if (Date.now() > item.endTime) return seal.replyToSender(ctx, msg, "❌ 该拍卖已到期，请等待管理员结算");
        if (isAnon && !settings.allowAnon) return seal.replyToSender(ctx, msg, "❌ 当前不允许匿名出价");

        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色");

        const topBid = item.bids[0];
        const minBid = topBid ? topBid.amount + item.minIncrement : item.startPrice;
        if (amount < minBid) return seal.replyToSender(ctx, msg, `❌ 出价不足！最低应出 ${minBid} ${settings.currency}（${topBid ? `当前最高${topBid.amount}+最低加价${item.minIncrement}` : `起拍价${item.startPrice}`}）`);

        const currencyItem = findCurrencyByName_rpg(settings.currency);
        let balance;
        if (currencyItem) {
            balance = getInvCount_rpg(`${platform}:${uid}`, currencyItem.code);
        } else {
            const attrs = JSON.parse(mainStorGet("sys_character_attrs") || "{}");
            balance = attrs[uid]?.[settings.currency] || 0;
        }
        if (balance < amount) return seal.replyToSender(ctx, msg, `❌ ${settings.currency}不足！需要 ${amount}，当前 ${balance}`);

        item.bids = item.bids.filter(b => b.roleName !== roleName);
        item.bids.push({ roleName, uid, amount, isAnon, time: Date.now() });
        item.bids.sort((a, b) => b.amount - a.amount);
        saveAuctions(auctions);

        const bidderDisplay = isAnon ? "匿名玩家" : `「${roleName}」`;
        seal.replyToSender(ctx, msg, `✅ 出价成功！${auctionId} 「${item.name}」\n${bidderDisplay} 出价 ${amount} ${settings.currency}`);
        if (settings.broadcast) {
            const top = item.bids[0];
            const topDisplay = settings.showTopBidder && !top.isAnon ? `「${top.roleName}」` : "匿名";
            _notifyAuction(ctx, msg, settings, `🔔 出价播报 | ${auctionId} 「${item.name}」\n💰 最新出价：${top.amount} ${settings.currency}${settings.showTopBidder ? `（${topDisplay}）` : ""}`);
        }
        return;
    }
};
