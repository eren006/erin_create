// ==UserScript==
// @name         长日基础额外
// @author       长日将尽
// @version      1.0.0
// @description  基础功能的额外配置模块（礼物商城、图鉴、预设礼物管理），数据统一存储在主插件 changriV1 中。
// @timestamp    1743292800
// @license      MIT
// ==/UserScript=

let ext = seal.ext.find('extra_system');
if (!ext) {
    ext = seal.ext.new("extra_system", "长日基础额外", "1.0.0");
    seal.ext.register(ext);
}

// ========================
// 核心依赖：读取主插件存储
// ========================

function getMainExt() {
    const main = seal.ext.find('changriV1');
    if (!main) {
        console.error("❌ 基础额外系统错误：未找到主插件 changriV1，请检查主插件是否已加载");
        return null;
    }
    return main;
}

function getRoleName(ctx, msg) {
    const main = getMainExt();
    if (!main) return null;
    try {
        let rawData = main.storageGet("a_private_group");
        if (!rawData) return null;
        let charPlatform = JSON.parse(rawData);
        const platform = msg.platform;
        const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");
        if (!charPlatform[platform]) return null;
        for (let name in charPlatform[platform]) {
            if (Array.isArray(charPlatform[platform][name]) && charPlatform[platform][name][0] === uid) {
                return name;
            }
        }
    } catch (e) {
        console.log("基础额外系统读取主插件数据失败: " + e.message);
    }
    return null;
}

function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;
    const main = getMainExt();
    if (!main) return false;
    try {
        let rawAdmin = main.storageGet("a_adminList");
        if (!rawAdmin) return false;
        let a_adminList = JSON.parse(rawAdmin);
        const parts = msg.sender.userId.split(':');
        const platform = parts[0];
        const pureUid = parts[1];
        return a_adminList[platform] && a_adminList[platform].includes(pureUid);
    } catch (e) {
        return false;
    }
}

// ========================
// 🔧 工具：合并转发消息
// ========================
function sendForwardMsg(ctx, msg, nodes) {
    const main = getMainExt();
    if (!main || typeof main._ws !== "function") return;
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    main._ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
}

// ========================
// 🛒 礼物商城指令
// ========================

let cmd_view_preset_gifts = seal.ext.newCmdItemInfo();
cmd_view_preset_gifts.name = "礼物商城";
cmd_view_preset_gifts.help = "礼物商城 — 查看今日上架的商品（随机3件）";

cmd_view_preset_gifts.solve = (ctx, msg) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const sendname = getRoleName(ctx, msg);
    if (!sendname) {
        seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再逛商城。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
    const freeMode = main.storageGet("shop_free_mode") !== "false";
    const currencyAttr = main.storageGet("shop_currency_attr") || "金币";

    // 只展示有库存的商品
    const inStock = Object.entries(presetGifts).filter(([, g]) => (g.stock ?? 3) > 0);
    if (inStock.length === 0) {
        return seal.replyToSender(ctx, msg, "🛒 商城暂无库存，请等待补货~");
    }

    // 随机抽取最多3件
    const shuffled = inStock.sort(() => Math.random() - 0.5).slice(0, 3);
    const bot = "礼物助手", uin = "10086";

    const nodes = [{
        type: "node",
        data: { name: bot, uin, content:
            `🛒 礼物商城\n${"━".repeat(14)}\n` +
            (freeMode
                ? "✨ 当前开启零元购，所有商品免费！\n"
                : `💰 使用货币：${currencyAttr}\n`) +
            `📦 共有 ${inStock.length} 件在售，随机展示 ${shuffled.length} 件\n\n` +
            `发送「购买 商品名」即可购买`
        }
    }];

    for (const [id, gift] of shuffled) {
        const stock = gift.stock ?? 3;
        const priceText = freeMode ? "0元（零元购）" : `${gift.price ?? 0} ${currencyAttr}`;
        nodes.push({ type: "node", data: { name: bot, uin, content:
            `🎁 ${gift.name}\n${"─".repeat(12)}\n` +
            `📝 ${gift.content}\n` +
            `💰 价格：${priceText}\n` +
            `📦 剩余库存：${stock} 件`
        }});
    }

    sendForwardMsg(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["礼物商城"] = cmd_view_preset_gifts;

// ========================
// 🛍️ 玩家指令：购买
// ========================

let cmd_purchase = seal.ext.newCmdItemInfo();
cmd_purchase.name = "购买";
cmd_purchase.help = "购买 商品名 — 在礼物商城购买指定商品";

cmd_purchase.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const sendname = getRoleName(ctx, msg);
    if (!sendname) return seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再购买商品。");

    const itemName = cmdArgs.getArgN(1);
    if (!itemName) return seal.replyToSender(ctx, msg, "用法：购买 商品名");

    const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
    const freeMode = main.storageGet("shop_free_mode") !== "false";
    const currencyAttr = main.storageGet("shop_currency_attr") || "金币";

    // 按名字找商品
    const entry = Object.entries(presetGifts).find(([, g]) => g.name === itemName);
    if (!entry) return seal.replyToSender(ctx, msg, `❌ 商城中没有「${itemName}」，发送「礼物商城」查看在售商品。`);
    const [giftId, gift] = entry;

    const stock = gift.stock ?? 3;
    if (stock <= 0) return seal.replyToSender(ctx, msg, `😔 「${itemName}」已售罄。`);

    // 非零元购：检查并扣除货币
    if (!freeMode) {
        const price = gift.price ?? 0;
        if (price > 0) {
            let attrs = JSON.parse(main.storageGet("sys_character_attrs") || "{}");
            const currentVal = attrs[sendname]?.[currencyAttr] || 0;
            if (currentVal < price) {
                return seal.replyToSender(ctx, msg, `💰 ${currencyAttr}不足！需要 ${price}，当前 ${currentVal}。`);
            }
            if (!attrs[sendname]) attrs[sendname] = {};
            attrs[sendname][currencyAttr] = currentVal - price;
            main.storageSet("sys_character_attrs", JSON.stringify(attrs));
        }
    }

    // 加入背包（1份，普通礼物分区）
    const platform = msg.platform;
    const roleInvKey = `${platform}:${sendname}`;
    const invs = JSON.parse(main.storageGet("global_inventories") || "{}");
    if (!invs[roleInvKey]) invs[roleInvKey] = [];
    invs[roleInvKey].push({
        name: gift.name,
        desc: gift.content,
        used: false,
        type: "礼物",
        giftId: giftId,
        createTime: Date.now(),
        source: "礼物商城"
    });
    main.storageSet("global_inventories", JSON.stringify(invs));

    // 扣库存
    presetGifts[giftId].stock = stock - 1;
    main.storageSet("preset_gifts", JSON.stringify(presetGifts));

    // 更新图鉴（购买即解锁）
    const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const userKey = `${platform}:${uid}`;
    let sightings = JSON.parse(main.storageGet("gift_sightings") || "{}");
    if (!sightings[userKey]) sightings[userKey] = { unlocked_gifts: [] };
    if (!sightings[userKey].unlocked_gifts.includes(giftId)) {
        sightings[userKey].unlocked_gifts.push(giftId);
    }
    main.storageSet("gift_sightings", JSON.stringify(sightings));

    const priceText = freeMode ? "（零元购）" : `（已扣除 ${gift.price ?? 0} ${currencyAttr}）`;
    seal.replyToSender(ctx, msg,
        `✅ 购买成功${priceText}\n` +
        `🎁 「${gift.name}」已放入背包·普通礼物\n` +
        `📦 商城剩余库存：${stock - 1} 件`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["购买"] = cmd_purchase;

// ========================
// 📚 我的图鉴指令
// ========================

let cmd_view_my_gift_collection = seal.ext.newCmdItemInfo();
cmd_view_my_gift_collection.name = "我的图鉴";
cmd_view_my_gift_collection.help = "我的图鉴 - 查看你已解锁的所有礼物";

cmd_view_my_gift_collection.solve = (ctx, msg) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const platform = msg.platform;
    const uid = msg.sender.userId;
    const userKey = `${platform}:${uid.replace(`${platform}:`, "")}`;

    let giftSightings = JSON.parse(main.storageGet("gift_sightings") || "{}");
    const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");

    if (!giftSightings[userKey] || giftSightings[userKey].unlocked_gifts.length === 0) {
        seal.replyToSender(ctx, msg,
            "📚 你的图鉴空空如也~\n" +
            "去「礼物商城」逛逛，每次都会解锁一件新礼物！"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const unlockedGifts = giftSightings[userKey].unlocked_gifts;
    const totalGifts = Object.keys(presetGifts).length;
    const bot = "长日将尽", uin = "10001";

    const sortedGiftIds = [...unlockedGifts].sort((a, b) => {
        const numA = parseInt(a.replace('#', '')) || 0;
        const numB = parseInt(b.replace('#', '')) || 0;
        return numA - numB;
    });

    const nodes = [
        {
            type: "node",
            data: {
                name: bot, uin,
                content: `📚 我的礼物图鉴\n${"━".repeat(14)}\n🎯 解锁进度：${unlockedGifts.length} / ${totalGifts}\n💡 已解锁的礼物均可通过「赠送」送出`
            }
        },
        ...sortedGiftIds.map(giftId => {
            const gift = presetGifts[giftId];
            if (!gift) {
                return { type: "node", data: { name: bot, uin, content: `❓ ${giftId}\n（该礼物已下架）` } };
            }
            const heat = gift.usage_count || 0;
            const stars = heat > 20 ? "⭐⭐⭐⭐⭐" : heat > 15 ? "⭐⭐⭐⭐" : heat > 10 ? "⭐⭐⭐" : heat > 5 ? "⭐⭐" : heat > 0 ? "⭐" : "☆";
            return {
                type: "node",
                data: {
                    name: bot, uin,
                    content: `🎁 ${giftId}  ${gift.name}\n${"─".repeat(12)}\n📝 ${gift.content}\n🔥 热度：${stars}`
                }
            };
        })
    ];

    sendForwardMsg(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的图鉴"] = cmd_view_my_gift_collection;

// ========================
// 📦 管理员指令：上传预设礼物（简化版）
// ========================

let cmd_upload_preset_gift = seal.ext.newCmdItemInfo();
cmd_upload_preset_gift.name = "上传预设礼物";
cmd_upload_preset_gift.help = `用法（零元购开启）：上传预设礼物 编号:礼物名:礼物内容
用法（零元购关闭）：上传预设礼物 编号:礼物名:价格:礼物内容
批量（$分隔）：上传预设礼物 礼物1$礼物2
补货（恢复库存）：上传预设礼物 补货 编号
导出：上传预设礼物 导出`;

cmd_upload_preset_gift.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const freeMode = main.storageGet("shop_free_mode") !== "false";
    const currencyAttr = main.storageGet("shop_currency_attr") || "金币";
    const inputArg = cmdArgs.getArgN(1).trim();

    if (!inputArg) {
        const fmt = freeMode
            ? "格式：编号:礼物名:礼物内容（零元购模式，无需价格）"
            : `格式：编号:礼物名:价格:礼物内容（货币：${currencyAttr}）`;
        seal.replyToSender(ctx, msg, `❌ 请输入参数\n${fmt}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");

    // 导出
    if (inputArg === "导出") {
        if (Object.keys(presetGifts).length === 0) {
            seal.replyToSender(ctx, msg, "📭 当前没有预设礼物数据");
            return seal.ext.newCmdExecuteResult(true);
        }
        seal.replyToSender(ctx, msg, `📦 当前预设礼物数据：\n\`\`\`json\n${JSON.stringify(presetGifts, null, 2)}\n\`\`\``);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 补货：恢复指定编号库存为3
    const restockArg = cmdArgs.getArgN(2);
    if (inputArg === "补货") {
        if (!restockArg) return seal.replyToSender(ctx, msg, "用法：上传预设礼物 补货 编号（如 #1）");
        if (!presetGifts[restockArg]) return seal.replyToSender(ctx, msg, `❌ 编号 ${restockArg} 不存在。`);
        presetGifts[restockArg].stock = 3;
        main.storageSet("preset_gifts", JSON.stringify(presetGifts));
        seal.replyToSender(ctx, msg, `✅ 「${presetGifts[restockArg].name}」库存已补至 3 件。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 解析单条
    function parseSingle(raw) {
        const parts = raw.trim().split(':');
        const giftId = (parts[0] || "").trim();
        const giftName = (parts[1] || "").trim();
        if (!giftId.startsWith('#')) return { err: `编号必须以#开头: ${giftId}` };
        if (!giftName) return { err: `礼物名为空: ${raw}` };

        if (freeMode) {
            // #id:name:content
            if (parts.length < 3) return { err: `格式错误(缺少内容): ${raw}` };
            const giftContent = parts.slice(2).join(':').trim();
            if (!giftContent) return { err: `内容为空: ${raw}` };
            return { giftId, giftName, giftContent, price: 0 };
        } else {
            // #id:name:price:content
            if (parts.length < 4) return { err: `格式错误(零元购已关闭，需要价格): ${raw}\n  正确格式：编号:礼物名:价格:礼物内容` };
            const price = parseInt(parts[2].trim());
            if (isNaN(price) || price < 0) return { err: `价格必须为非负整数: ${parts[2]}` };
            const giftContent = parts.slice(3).join(':').trim();
            if (!giftContent) return { err: `内容为空: ${raw}` };
            return { giftId, giftName, giftContent, price };
        }
    }

    const giftItems = inputArg.includes('$') ? inputArg.split('$') : [inputArg];
    const results = { success: 0, failed: 0, details: [] };

    for (const giftItem of giftItems) {
        const item = giftItem.trim();
        if (!item) continue;
        const parsed = parseSingle(item);
        if (parsed.err) {
            results.details.push(`❌ ${parsed.err}`);
            results.failed++;
            continue;
        }
        const { giftId, giftName, giftContent, price } = parsed;
        const isUpdate = !!presetGifts[giftId];
        presetGifts[giftId] = isUpdate
            ? { ...presetGifts[giftId], name: giftName, content: giftContent, price, updated_at: new Date().toLocaleString("zh-CN") }
            : { name: giftName, content: giftContent, price, stock: 3, usage_count: 0, created_at: new Date().toLocaleString("zh-CN") };
        results.details.push(isUpdate
            ? `🔄 更新: ${giftId} (${giftName}) 价格:${price}`
            : `✅ 新增: ${giftId} (${giftName}) 价格:${price} 库存:3`);
        results.success++;
    }

    if (results.success > 0) main.storageSet("preset_gifts", JSON.stringify(presetGifts));

    let rep = "";
    if (giftItems.length > 1) {
        rep += `📦 批量上传完成\n✅ 成功: ${results.success}  ❌ 失败: ${results.failed}\n📊 总计: ${Object.keys(presetGifts).length} 件\n\n`;
    }
    const showCount = Math.min(results.details.length, 5);
    rep += results.details.slice(0, showCount).join('\n');
    if (results.details.length > showCount) rep += `\n...等${results.details.length}项`;
    if (results.success === 0) rep += `\n💡 ${freeMode ? "零元购模式：编号:礼物名:内容" : "付费模式：编号:礼物名:价格:内容"}`;

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传预设礼物"] = cmd_upload_preset_gift;

// ========================
// 🗑️ 管理员指令：删除预设礼物
// ========================

let cmd_delete_preset_gift = seal.ext.newCmdItemInfo();
cmd_delete_preset_gift.name = "删除预设礼物";
cmd_delete_preset_gift.help = `用法：
1. 删除单个：删除预设礼物 编号
   示例：删除预设礼物 #1

2. 批量删除：删除预设礼物 编号1,编号2,编号3
   示例：删除预设礼物 #1,#2,#3

3. 删除所有：删除预设礼物 全部 (⚠️危险操作)`;

cmd_delete_preset_gift.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const giftIds = cmdArgs.getArgN(1);
    if (!giftIds) {
        seal.replyToSender(ctx, msg, "请指定要删除的礼物编号，多个编号用逗号分隔");
        return seal.ext.newCmdExecuteResult(true);
    }

    let presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
    let giftSightings = JSON.parse(main.storageGet("gift_sightings") || "{}");

    if (giftIds.trim() === "全部") {
        const confirmArg = cmdArgs.getArgN(2);
        if (confirmArg !== "确认") {
            seal.replyToSender(ctx, msg,
                "⚠️ 危险操作：这将删除所有预设礼物！\n" +
                "如需继续，请输入：删除预设礼物 全部 确认\n" +
                `当前共有 ${Object.keys(presetGifts).length} 个预设礼物`);
            return seal.ext.newCmdExecuteResult(true);
        }

        for (const userId in giftSightings) {
            giftSightings[userId].unlocked_gifts = [];
        }
        main.storageSet("gift_sightings", JSON.stringify(giftSightings));

        const totalCount = Object.keys(presetGifts).length;
        presetGifts = {};
        main.storageSet("preset_gifts", JSON.stringify(presetGifts));

        seal.replyToSender(ctx, msg, `✅ 已删除全部 ${totalCount} 个预设礼物，并清空了所有玩家的图鉴记录`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const idsToDelete = giftIds.split(',').map(id => id.trim()).filter(id => id);
    let deletedCount = 0;
    let notFoundCount = 0;
    let removedFromSightings = 0;
    let resultDetails = [];

    for (const giftId of idsToDelete) {
        if (!presetGifts[giftId]) {
            resultDetails.push(`❌ 未找到: ${giftId}`);
            notFoundCount++;
            continue;
        }

        const giftName = presetGifts[giftId].name;
        let userRemoved = 0;
        for (const userId in giftSightings) {
            const unlockedGifts = giftSightings[userId].unlocked_gifts || [];
            const index = unlockedGifts.indexOf(giftId);
            if (index !== -1) {
                unlockedGifts.splice(index, 1);
                giftSightings[userId].unlocked_gifts = unlockedGifts;
                userRemoved++;
            }
        }

        delete presetGifts[giftId];
        deletedCount++;
        removedFromSightings += userRemoved;
        resultDetails.push(`✅ 已删除: ${giftId} (${giftName}) - 从 ${userRemoved} 位玩家图鉴中移除`);
    }

    if (deletedCount > 0) {
        main.storageSet("preset_gifts", JSON.stringify(presetGifts));
        main.storageSet("gift_sightings", JSON.stringify(giftSightings));
    }

    let rep = "";
    if (idsToDelete.length > 1) {
        rep += `🗑️ 批量删除完成\n`;
        rep += `✅ 成功删除: ${deletedCount}个\n`;
        rep += `❌ 未找到: ${notFoundCount}个\n`;
        rep += `👥 从玩家图鉴移除总计: ${removedFromSightings}次\n\n`;
        if (deletedCount > 0) {
            rep += "📋 处理详情：\n";
            resultDetails.forEach(detail => {
                rep += `  ${detail}\n`;
            });
        }
    } else {
        if (deletedCount > 0) {
            rep = resultDetails[0];
        } else {
            rep = `❌ 未找到编号为 ${giftIds} 的预设礼物`;
        }
    }

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除预设礼物"] = cmd_delete_preset_gift;

// ========================
// 💬 无前缀指令触发
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = msg.message.trim();
    if (raw === "礼物商城") return cmd_view_preset_gifts.solve(ctx, msg, { getArgN: () => "", args: [] });
    if (raw === "我的图鉴") return cmd_view_my_gift_collection.solve(ctx, msg);
    if (raw.startsWith("购买")) {
        const itemName = raw.slice(2).trim();
        if (itemName) return cmd_purchase.solve(ctx, msg, { getArgN: (n) => n === 1 ? itemName : "", args: [itemName] });
    }
};