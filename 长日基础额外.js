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
cmd_view_preset_gifts.help = "礼物商城 - 随机解锁 1 个预设礼物（受游戏天数和冷却控制）";

cmd_view_preset_gifts.solve = (ctx, msg) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const userKey = `${platform}:${uid}`;

    // 1. 身份验证
    const sendname = getRoleName(ctx, msg);
    if (!sendname) {
        seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再逛商城。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 冷却检查
    let globalCooldowns = JSON.parse(main.storageGet("global_shop_cooldowns") || "{}");
    const now = Date.now();
    const cooldownDuration = 3600 * 1000; // 1小时

    if (now - (globalCooldowns[userKey] || 0) < cooldownDuration) {
        const remainingMin = Math.ceil((cooldownDuration - (now - globalCooldowns[userKey])) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 进货中... 商城正在整顿，请 ${remainingMin} 分钟后再来~`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 获取数据
    const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
    const giftIds = Object.keys(presetGifts);
    if (giftIds.length === 0) {
        return seal.replyToSender(ctx, msg, "🛒 商城空空如也。");
    }

    // 4. 图鉴与解锁逻辑
    let giftSightings = JSON.parse(main.storageGet("gift_sightings") || "{}");
    if (!giftSightings[userKey]) {
        giftSightings[userKey] = { unlocked_gifts: [] };
    }

    // 随机选择一个未解锁的礼物（如果全部已解锁，则随机一个已解锁的）
    let selectedId;
    let unlocked = giftSightings[userKey].unlocked_gifts;
    let available = giftIds.filter(id => !unlocked.includes(id));
    if (available.length > 0) {
        const randomIndex = Math.floor(Math.random() * available.length);
        selectedId = available[randomIndex];
    } else {
        // 已全部解锁，随机一个已解锁的（但不会重复添加）
        const randomIndex = Math.floor(Math.random() * giftIds.length);
        selectedId = giftIds[randomIndex];
    }
    const gift = presetGifts[selectedId];

    if (!unlocked.includes(selectedId)) {
        unlocked.push(selectedId);
    }

    // 5. 持久化（图鉴解锁）
    globalCooldowns[userKey] = now;
    main.storageSet("global_shop_cooldowns", JSON.stringify(globalCooldowns));
    main.storageSet("gift_sightings", JSON.stringify(giftSightings));

    // 6. 加入背包（获得 3 份可赠送的礼物副本）
    const roleInvKey = `${platform}:${sendname}`;
    const invs = JSON.parse(main.storageGet("global_inventories") || "{}");
    if (!invs[roleInvKey]) invs[roleInvKey] = [];
    for (let i = 0; i < 3; i++) {
        invs[roleInvKey].push({
            name: gift.name,
            desc: gift.content,
            used: false,
            type: "礼物",
            giftId: selectedId,
            createTime: Date.now(),
            source: "礼物商城"
        });
    }
    main.storageSet("global_inventories", JSON.stringify(invs));

    // 7. 渲染回复
    const isNew = unlocked.length === (invs[roleInvKey].filter(i => i.giftId === selectedId).length === 3 ? unlocked.length : unlocked.length - 1);
    let rep = `🛒 【${sendname}】你在商城货架发现了一件宝贝：\n\n`;
    rep += `📦 编号：${selectedId}\n`;
    rep += `✨ 礼物：${gift.name}\n`;
    rep += `📝 内容：${gift.content}\n`;
    rep += `\n🎁 已获得 3 份，可通过「道具赠送 对方名 ${gift.name}」送出\n`;
    rep += `📚 图鉴进度：${unlocked.length} / ${giftIds.length}`;
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["礼物商城"] = cmd_view_preset_gifts;

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
cmd_upload_preset_gift.help = `用法：
1. 单个上传：上传预设礼物 编号:礼物名:礼物内容
   示例：上传预设礼物 #1:玫瑰花:一束精心包装的红色玫瑰花

2. 批量上传：上传预设礼物 礼物1$礼物2$礼物3
   示例：上传预设礼物 #1:玫瑰花:一束红玫瑰$#2:巧克力:一盒心形巧克力

3. 导出数据：上传预设礼物 导出 - 导出所有预设礼物数据`;

cmd_upload_preset_gift.solve = (ctx, msg, cmdArgs) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const inputArg = cmdArgs.getArgN(1).trim();
    if (!inputArg) {
        seal.replyToSender(ctx, msg,
            "❌ 请输入参数\n" +
            "格式1（单个）：编号:礼物名:礼物内容\n" +
            "格式2（批量）：礼物1$礼物2$礼物3\n" +
            "格式3（导出）：上传预设礼物 导出");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 导出功能
    if (inputArg === "导出") {
        const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
        if (Object.keys(presetGifts).length === 0) {
            seal.replyToSender(ctx, msg, "📭 当前没有预设礼物数据");
            return seal.ext.newCmdExecuteResult(true);
        }
        const exportData = JSON.stringify(presetGifts, null, 2);
        seal.replyToSender(ctx, msg, `📦 当前预设礼物数据：\n\`\`\`json\n${exportData}\n\`\`\``);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取现有礼物数据
    let presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");

    let results = {
        success: 0,
        failed: 0,
        details: []
    };

    // 判断是批量上传还是单个上传
    const giftItems = inputArg.includes('$') ? inputArg.split('$') : [inputArg];

    for (const giftItem of giftItems) {
        const item = giftItem.trim();
        if (!item) continue;

        const parts = item.split(':');
        if (parts.length < 3) {
            results.details.push(`❌ 格式错误: ${item} (需要冒号分隔三部分)`);
            results.failed++;
            continue;
        }

        const giftId = parts[0].trim();
        const giftName = parts[1].trim();
        let giftContent = parts.slice(2).join(':').trim();

        if (!giftId.startsWith('#')) {
            results.details.push(`❌ 编号错误: ${giftId} (必须以#开头)`);
            results.failed++;
            continue;
        }
        if (!giftName || !giftContent) {
            results.details.push(`❌ 内容为空: ${giftId} (名称和内容不能为空)`);
            results.failed++;
            continue;
        }

        if (presetGifts[giftId]) {
            results.details.push(`🔄 已存在: ${giftId} (${giftName}) - 已更新`);
        } else {
            results.details.push(`✅ 新增: ${giftId} (${giftName})`);
        }

        if (presetGifts[giftId]) {
            presetGifts[giftId] = {
                ...presetGifts[giftId],
                name: giftName,
                content: giftContent,
                updated_at: new Date().toLocaleString("zh-CN")
            };
        } else {
            presetGifts[giftId] = {
                name: giftName,
                content: giftContent,
                created_at: new Date().toLocaleString("zh-CN"),
                usage_count: 0
            };
        }
        results.success++;
    }

    if (results.success > 0) {
        main.storageSet("preset_gifts", JSON.stringify(presetGifts));
    }

    let rep = "";
    if (giftItems.length > 1) {
        rep += `📦 批量上传完成 (${giftItems.length}个)\n`;
        rep += `✅ 成功: ${results.success}个\n`;
        rep += `❌ 失败: ${results.failed}个\n`;
        rep += `📊 当前总计: ${Object.keys(presetGifts).length}个预设礼物\n\n`;
    }

    if (results.details.length > 0) {
        if (giftItems.length <= 3) {
            rep += "📋 处理详情：\n";
            results.details.forEach(detail => {
                rep += `  ${detail}\n`;
            });
        } else {
            rep += "📋 前3项处理详情：\n";
            for (let i = 0; i < Math.min(3, results.details.length); i++) {
                rep += `  ${results.details[i]}\n`;
            }
            if (results.details.length > 3) {
                rep += `  ...等${results.details.length}项\n`;
            }
        }
    }

    if (results.success === 0) {
        rep += "\n💡 提示：批量上传时使用 $ 分隔多个礼物\n" +
               "示例：#1:礼物名:礼物内容$#2:礼物名:礼物内容";
    }

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
};