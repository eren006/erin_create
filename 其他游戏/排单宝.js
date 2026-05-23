// ==UserScript==
// @name         排单宝 (OrderMaster)
// @author       长日将尽
// @version      2.0.0
// @description  标签化下单系统，支持管理群提醒、全流程CQ码艾特通知。
// @timestamp    1742205760
// @license      MIT
// ==/UserScript//

let ext = seal.ext.find('order_master');
if (!ext) {
    ext = seal.ext.new('order_master', '长日将尽', '2.0.0');
    seal.ext.register(ext);
}

// ======================== 核心数据库 ========================

const getDb = (key) => JSON.parse(ext.storageGet(key) || "{}");
const setDb = (key, data) => ext.storageSet(key, JSON.stringify(data));

// ======================== 权限与配置 ========================

function isOrderAdmin(ctx, msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const admins = getDb("paidan_adminList");
    return ctx.privilegeLevel === 100 || (admins[platform] && admins[platform].includes(uid));
}

// 返回 true 表示成功发送，false 表示 groupId 为空无法发送
// 遍历所有 endpoint 尝试发送，解决多 bot 账号时 eps[0] 不在目标群的问题
function sendNotify(groupId, userId, text) {
    const eps = seal.getEndPoints();
    console.log(`[排单宝] sendNotify 调用 | groupId=${groupId} userId=${userId} eps数量=${eps.length}`);
    if (!groupId || eps.length === 0) {
        console.log(`[排单宝] sendNotify 跳过：groupId为空或无endpoint`);
        return false;
    }
    const at = userId ? `[CQ:at,qq=${userId}] ` : "";
    for (const ep of eps) {
        console.log(`[排单宝] sendNotify 尝试通过 ep(${ep.userId ?? ep.id ?? '未知'}) 发送到群 ${groupId}`);
        const fakeMsg = seal.newMessage();
        fakeMsg.groupId = groupId;
        fakeMsg.messageType = 'group';
        const targetCtx = seal.createTempCtx(ep, fakeMsg);
        seal.replyToSender(targetCtx, fakeMsg, at + text);
    }
    return true;
}

// ======================== 指令：管理员管理 ========================

let cmdAdmin = seal.ext.newCmdItemInfo();
cmdAdmin.name = "添加排单管理员";
cmdAdmin.solve = (ctx, msg, cmdArgs) => {
    if (ctx.privilegeLevel < 100) return;
    const targetQQ = cmdArgs.getArgN(1);
    if (!targetQQ) return seal.replyToSender(ctx, msg, "❌ 请输入QQ号");
    
    let admins = getDb("paidan_adminList");
    if (!admins[msg.platform]) admins[msg.platform] = [];
    if (admins[msg.platform].includes(targetQQ)) {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 已经是排单管理员了。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    admins[msg.platform].push(targetQQ);
    setDb("paidan_adminList", admins);
    seal.replyToSender(ctx, msg, `✅ 已将 ${targetQQ} 设为排单管理员`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["添加排单管理员"] = cmdAdmin;

let cmdRemoveAdmin = seal.ext.newCmdItemInfo();
cmdRemoveAdmin.name = "移除排单管理员";
cmdRemoveAdmin.solve = (ctx, msg, cmdArgs) => {
    if (ctx.privilegeLevel < 100) return;
    const targetQQ = cmdArgs.getArgN(1);
    if (!targetQQ) return seal.replyToSender(ctx, msg, "❌ 请输入QQ号");

    let admins = getDb("paidan_adminList");
    if (!admins[msg.platform] || !admins[msg.platform].includes(targetQQ)) {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 不在管理员列表中。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    admins[msg.platform] = admins[msg.platform].filter(id => id !== targetQQ);
    setDb("paidan_adminList", admins);
    seal.replyToSender(ctx, msg, `✅ 已移除排单管理员：${targetQQ}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["移除排单管理员"] = cmdRemoveAdmin;

let cmdSetUnlimited = seal.ext.newCmdItemInfo();
cmdSetUnlimited.name = "设置无限下单";
cmdSetUnlimited.help = ".设置无限下单 <QQ号>  授予该账号无限并发下单权限";
cmdSetUnlimited.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetQQ = cmdArgs.getArgN(1);
    if (!targetQQ) return seal.replyToSender(ctx, msg, "❌ 请输入QQ号");

    let unlimited = getDb("paidan_unlimitedUsers");
    if (!unlimited[msg.platform]) unlimited[msg.platform] = [];
    if (unlimited[msg.platform].includes(targetQQ)) {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 已拥有无限下单权限。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    unlimited[msg.platform].push(targetQQ);
    setDb("paidan_unlimitedUsers", unlimited);
    seal.replyToSender(ctx, msg, `✅ 已为 ${targetQQ} 开启无限下单权限（可同时存在多笔进行中订单）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置无限下单"] = cmdSetUnlimited;

let cmdUnsetUnlimited = seal.ext.newCmdItemInfo();
cmdUnsetUnlimited.name = "取消无限下单";
cmdUnsetUnlimited.help = ".取消无限下单 <QQ号>  撤销该账号的无限并发下单权限";
cmdUnsetUnlimited.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetQQ = cmdArgs.getArgN(1);
    if (!targetQQ) return seal.replyToSender(ctx, msg, "❌ 请输入QQ号");

    let unlimited = getDb("paidan_unlimitedUsers");
    if (!unlimited[msg.platform] || !unlimited[msg.platform].includes(targetQQ)) {
        seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 没有无限下单权限。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    unlimited[msg.platform] = unlimited[msg.platform].filter(id => id !== targetQQ);
    setDb("paidan_unlimitedUsers", unlimited);
    seal.replyToSender(ctx, msg, `✅ 已撤销 ${targetQQ} 的无限下单权限`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["取消无限下单"] = cmdUnsetUnlimited;

// ======================== 指令：系统配置 ========================

let cmdConfig = seal.ext.newCmdItemInfo();
cmdConfig.name = "设置下单格式";
cmdConfig.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const format = msg.message.replace(/^[.。]设置下单格式\s*/, "").trim();
    if (!format) return seal.replyToSender(ctx, msg, "❌ 格式不能为空");

    // 校验每个非空行必须含有 ：
    const lines = format.split("\n").filter(l => l.trim());
    const invalidLines = lines.filter(l => !l.includes("：") && !l.includes(":"));
    if (invalidLines.length > 0) {
        return seal.replyToSender(ctx, msg, `❌ 格式设置有误，以下行缺少冒号，每行必须是「字段名：提示说明」的格式：\n${invalidLines.join("\n")}`);
    }

    // 自动提取字段名（冒号前面的部分，兼容全角半角）
    const fields = lines.map(l => l.split(/[：:]/)[0].trim()).filter(f => f);

    let config = getDb("paidan_config");
    config.orderFormat = format;
    config.orderFields = fields;
    setDb("paidan_config", config);
    seal.replyToSender(ctx, msg, `✅ 下单格式已更新，共解析 ${fields.length} 个字段：\n${fields.join("、")}\n\n用户下单时将自动校验以上字段是否全部填写。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置下单格式"] = cmdConfig;

let cmdWorkGroup = seal.ext.newCmdItemInfo();
cmdWorkGroup.name = "设置排单工作群";
cmdWorkGroup.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    let config = getDb("paidan_config");
    config.adminGroupId = msg.groupId;
    setDb("paidan_config", config);
    seal.replyToSender(ctx, msg, `✅ 工作群已绑定：${msg.groupId}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置排单工作群"] = cmdWorkGroup;

let cmdNotice = seal.ext.newCmdItemInfo();
cmdNotice.name = "设置排单公告";
cmdNotice.help = ".设置排单公告 <内容>  （留空则清空公告）";
cmdNotice.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const notice = msg.message.replace(/^[.。]设置排单公告\s*/, "").trim();
    let config = getDb("paidan_config");
    config.notice = notice;
    setDb("paidan_config", config);
    seal.replyToSender(ctx, msg, notice ? `✅ 公告已更新：\n${notice}` : "✅ 公告已清空。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置排单公告"] = cmdNotice;

// ======================== 指令：用户流程 ========================

// 1. 注册
let cmdReg = seal.ext.newCmdItemInfo();
cmdReg.name = "排单注册";
cmdReg.solve = (ctx, msg, cmdArgs) => {
    const name = cmdArgs.getArgN(1);
    const count = parseInt(cmdArgs.getArgN(2)) || 0;
    if (!name) return seal.replyToSender(ctx, msg, "⚠️ 请输入：.排单注册 姓名 剩余数量");

    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    let users = getDb("paidan_users");
    if (users[uid] && users[uid].verified) {
        seal.replyToSender(ctx, msg, "⚠️ 您已通过核对，如需修改请联系管理员。");
        return seal.ext.newCmdExecuteResult(true);
    }
    users[uid] = { name, balance: count, expiry: "待核对", verified: false, group: msg.groupId };
    setDb("paidan_users", users);

    seal.replyToSender(ctx, msg, "✨ 注册信息已提交。请联系管理员录入有效期并核对数量。");
    
    // 通知工作群
    const config = getDb("paidan_config");
    if (config.adminGroupId) {
        const text = `📢 【新注册提醒】\n姓名：${name}\n报数：${count}\nUID：${uid}\n来自群：${msg.groupId}\n请管理员使用「.排单核对」进行确认。`;
        sendNotify(config.adminGroupId, null, text);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单注册"] = cmdReg;

// 2. 下单 (两步流程：先展示格式，填写后再提交)
let cmdOrder = seal.ext.newCmdItemInfo();
cmdOrder.name = "下单";
cmdOrder.solve = (ctx, msg) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    let users = getDb("paidan_users");
    const user = users[uid];

    if (!user || !user.verified) return seal.replyToSender(ctx, msg, "❌ 您尚未通过管理员核对，无法下单。");
    if (new Date(user.expiry) < new Date()) return seal.replyToSender(ctx, msg, `⚠️ 您的卡片已于 ${user.expiry} 过期，无法下单。`);
    if (user.balance <= 0) return seal.replyToSender(ctx, msg, "⚠️ 您的剩余数量不足，请联系管理增补。");

    const content = msg.message.replace(/^[.。]下单\s*/, "").trim();

    // 第一步：无内容时展示公告 + 格式模板
    if (!content) {
        const config = getDb("paidan_config");
        const format = config.orderFormat || "（管理员尚未设置下单格式，请联系管理员）";
        let reply = "";
        if (config.notice) reply += `📢 【公告】\n${config.notice}\n\n`;
        reply += `📋 请按以下格式填写，然后发送【.下单 <填写内容>】提交：\n\n${format}`;
        return seal.replyToSender(ctx, msg, reply);
    }

    // 限制：同一用户不能同时存在进行中的订单（无限下单白名单用户跳过）
    const config = getDb("paidan_config");
    let orders = getDb("paidan_orders");
    const unlimitedUsers = getDb("paidan_unlimitedUsers");
    const isUnlimited = Array.isArray(unlimitedUsers[msg.platform]) && unlimitedUsers[msg.platform].includes(uid);
    if (!isUnlimited) {
        const hasActive = Object.values(orders).some(
            o => o.uid === uid && o.status !== "已完成" && o.status !== "已拒绝" && o.status !== "已撤单"
        );
        if (hasActive) return seal.replyToSender(ctx, msg, "⚠️ 您有一笔订单尚未完成，请等待当前订单完成后再下新单。");
    }

    // 字段格式校验
    if (config.orderFields && config.orderFields.length > 0) {
        const missing = config.orderFields.filter(f => !content.includes(f + "：") && !content.includes(f + ":"));
        if (missing.length > 0) {
            return seal.replyToSender(ctx, msg, `❌ 下单格式不完整，以下字段未填写：\n${missing.map(f => `· ${f}`).join("\n")}\n\n请发送【.下单】查看完整格式后重新提交。`);
        }
    }

    const orderId = "P" + Date.now().toString().slice(-6);
    orders[orderId] = {
        id: orderId,
        uid: uid,
        content: content,
        status: "待接单",
        group: msg.groupId,
        timestamp: Date.now()
    };
    setDb("paidan_orders", orders);

    seal.replyToSender(ctx, msg, `✅ 下单成功！订单编号：${orderId}\n状态：等待管理员接单`);

    if (config.adminGroupId) {
        const text = `🔥 【新订单：${orderId}】\n客户：${user.name}\n内容：\n${content}`;
        sendNotify(config.adminGroupId, null, text);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["下单"] = cmdOrder;

// ======================== 指令：管理员操作 ========================

// 核对
let cmdCheck = seal.ext.newCmdItemInfo();
cmdCheck.name = "排单核对";
cmdCheck.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetUid = cmdArgs.getArgN(1);
    const realCount = parseInt(cmdArgs.getArgN(2));
    const expiry = cmdArgs.getArgN(3); // YYYY-MM-DD

    if (isNaN(realCount)) return seal.replyToSender(ctx, msg, "❌ 请输入有效的数量（数字）");
    if (!expiry || !/^\d{4}-\d{1,2}-\d{1,2}$/.test(expiry)) return seal.replyToSender(ctx, msg, "❌ 有效期格式应为 YYYY-MM-DD，例如：2026-12-31");
    const [ey, em, ed] = expiry.split("-");
    const normalizedExpiry = `${ey}-${em.padStart(2,"0")}-${ed.padStart(2,"0")}`;

    let users = getDb("paidan_users");
    if (!users[targetUid]) return seal.replyToSender(ctx, msg, "❌ 找不到该用户");

    users[targetUid].balance = realCount;
    users[targetUid].expiry = normalizedExpiry;
    users[targetUid].verified = true;
    users[targetUid].expiryReminded = false;
    setDb("paidan_users", users);

    const sent = sendNotify(users[targetUid].group, targetUid, `✨ 管理员已完成您的资产核对！\n核定数量：${realCount}\n有效期至：${normalizedExpiry}`);
    const warnMsg = sent ? "" : "\n⚠️ 注意：该用户无群记录，回执未能发出，请手动通知。";
    seal.replyToSender(ctx, msg, `✅ 用户 ${users[targetUid].name} 核对完成。${warnMsg}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单核对"] = cmdCheck;

let cmdAddBalance = seal.ext.newCmdItemInfo();
cmdAddBalance.name = "增补余额";
cmdAddBalance.help = ".增补余额 <UID> <数量>";
cmdAddBalance.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetUid = cmdArgs.getArgN(1);
    const amount = parseInt(cmdArgs.getArgN(2));
    if (!targetUid) return seal.replyToSender(ctx, msg, "❌ 请提供用户UID");
    if (isNaN(amount) || amount <= 0) return seal.replyToSender(ctx, msg, "❌ 请输入有效的增补数量（正整数）");

    let users = getDb("paidan_users");
    if (!users[targetUid]) return seal.replyToSender(ctx, msg, "❌ 找不到该用户");

    users[targetUid].balance += amount;
    setDb("paidan_users", users);

    addOrderLog(`管理员为 ${targetUid} 增补余额 ${amount}，当前余额 ${users[targetUid].balance}`);
    seal.replyToSender(ctx, msg, `✅ 已为 ${users[targetUid].name} 增补 ${amount} 张，当前余额：${users[targetUid].balance} 张。`);
    sendNotify(users[targetUid].group, targetUid, `💳 管理员为您增补了 ${amount} 张卡片！\n当前余额：${users[targetUid].balance} 张`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["增补余额"] = cmdAddBalance;

let cmdExtend = seal.ext.newCmdItemInfo();
cmdExtend.name = "延期";
cmdExtend.help = ".延期 <UID> <新有效期 YYYY-MM-DD>";
cmdExtend.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetUid = cmdArgs.getArgN(1);
    const newExpiry = cmdArgs.getArgN(2);
    if (!targetUid) return seal.replyToSender(ctx, msg, "❌ 请提供用户UID");
    if (!newExpiry || !/^\d{4}-\d{1,2}-\d{1,2}$/.test(newExpiry)) return seal.replyToSender(ctx, msg, "❌ 有效期格式应为 YYYY-MM-DD，例如：2026-12-31");
    const [ny, nm, nd] = newExpiry.split("-");
    const normalizedNewExpiry = `${ny}-${nm.padStart(2,"0")}-${nd.padStart(2,"0")}`;

    let users = getDb("paidan_users");
    if (!users[targetUid]) return seal.replyToSender(ctx, msg, "❌ 找不到该用户");

    const oldExpiry = users[targetUid].expiry;
    users[targetUid].expiry = normalizedNewExpiry;
    users[targetUid].expiryReminded = false;
    setDb("paidan_users", users);

    addOrderLog(`管理员将 ${targetUid} 有效期从 ${oldExpiry} 延至 ${normalizedNewExpiry}`);
    seal.replyToSender(ctx, msg, `✅ 已将 ${users[targetUid].name} 有效期延至：${normalizedNewExpiry}`);
    sendNotify(users[targetUid].group, targetUid, `📅 管理员已为您续期！\n新有效期至：${normalizedNewExpiry}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["延期"] = cmdExtend;

// ======================== 模块一：接单（带工期设置） ========================
let cmdAccept = seal.ext.newCmdItemInfo();
cmdAccept.name = "接单";
cmdAccept.help = ".接单 <编号> [预计天数, 默认2]";
cmdAccept.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orderId = cmdArgs.getArgN(1);
    const duration = parseInt(cmdArgs.getArgN(2)) || 2; // 默认48小时(2天)

    let orders = getDb("paidan_orders");
    if (!orders[orderId]) return seal.replyToSender(ctx, msg, "❌ 订单不存在");
    if (orders[orderId].status === "已完成" || orders[orderId].status === "已拒绝") {
        return seal.replyToSender(ctx, msg, `❌ 订单 ${orderId} 已是「${orders[orderId].status}」状态，无法接单。`);
    }
    if (orders[orderId].status === "制作中" || orders[orderId].status === "草图阶段") {
        // 允许修改工期，但不重新发通知
        orders[orderId].duration = duration;
        setDb("paidan_orders", orders);
        addOrderLog(`管理员 ${msg.sender.nickname} 修改订单 ${orderId} 工期为 ${duration} 天`);
        return seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 工期已更新为 ${duration} 天（状态不变，不重发通知）。`);
    }

    orders[orderId].status = "制作中";
    orders[orderId].acceptTime = Date.now();
    orders[orderId].duration = duration;
    setDb("paidan_orders", orders);

    addOrderLog(`管理员 ${msg.sender.nickname} 接收了订单 ${orderId}，预计工期 ${duration} 天`);

    const sent = sendNotify(orders[orderId].group, orders[orderId].uid, `🔔 管理员已接单！预计交付：${duration}天内。请给劳斯一点创作时间哦~`);
    const warnMsg = sent ? "" : "\n⚠️ 注意：订单来源群无记录，接单回执未能发出，请手动通知客户。";
    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 已接单，预计工期 ${duration} 天。${warnMsg}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["接单"] = cmdAccept;

// ======================== 拒绝接单 ========================
let cmdReject = seal.ext.newCmdItemInfo();
cmdReject.name = "拒绝接单";
cmdReject.help = ".拒绝接单 <编号> <理由>";
cmdReject.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orderId = cmdArgs.getArgN(1);
    if (!orderId) return seal.replyToSender(ctx, msg, "❌ 请提供订单编号");

    // 提取理由：去掉指令名和编号，剩余部分为理由
    const raw = msg.message.replace(/^[.。]拒绝接单\s*/, "").trim();
    const spaceIdx = raw.indexOf(" ");
    const reason = spaceIdx === -1 ? "" : raw.slice(spaceIdx + 1).trim();

    let orders = getDb("paidan_orders");
    if (!orders[orderId]) return seal.replyToSender(ctx, msg, "❌ 订单不存在");
    if (orders[orderId].status === "已完成") return seal.replyToSender(ctx, msg, "❌ 订单已完成，无法拒绝");
    if (orders[orderId].status === "已拒绝") return seal.replyToSender(ctx, msg, "❌ 订单已是拒绝状态");

    orders[orderId].status = "已拒绝";
    orders[orderId].rejectReason = reason || "管理员未说明原因";
    setDb("paidan_orders", orders);

    addOrderLog(`管理员拒绝了订单 ${orderId}，理由：${reason || "未说明"}`);
    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 已拒绝。`);
    sendNotify(orders[orderId].group, orders[orderId].uid,
        `❌ 您的订单 [${orderId}] 已被拒绝。\n理由：${reason || "管理员未说明原因"}\n如有疑问请联系管理员，确认后可重新下单。`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拒绝接单"] = cmdReject;

// ======================== 模块二：反向防催单系统 ========================
let cmdUrge = seal.ext.newCmdItemInfo();
cmdUrge.name = "催单";
cmdUrge.solve = (ctx, msg, cmdArgs) => {
    const orderId = cmdArgs.getArgN(1);
    const orders = getDb("paidan_orders");
    const o = orders[orderId];

    if (!o) return seal.replyToSender(ctx, msg, "❌ 未找到该订单。");
    if (o.status === "待接单") return seal.replyToSender(ctx, msg, "⏳ 订单还在排队中，请等待管理员接单。");
    if (o.status === "已完成") return seal.replyToSender(ctx, msg, "✅ 订单已经完成啦，请查收消息。");

    // 计算进度
    const now = Date.now();
    const startTime = o.acceptTime || o.timestamp;
    const totalMs = o.duration * 24 * 60 * 60 * 1000;
    const passedMs = now - startTime;
    const progress = Math.min(Math.floor((passedMs / totalMs) * 100), 100);

    // 保护期逻辑：如果进度未到 80%，机器人自动挡掉
    const PROTECT_THRESHOLD = 80; 
    if (progress < PROTECT_THRESHOLD) {
        let progressBar = "▓".repeat(Math.floor(progress/10)) + "░".repeat(10 - Math.floor(progress/10));
        let reply = `🛠️ 工坊正在努力施工中...\n`;
        reply += `进度：[${progressBar}] ${progress}%\n`;
        reply += `提示：当前接单时间较短，请给劳斯一点创作空间。待进度超过${PROTECT_THRESHOLD}%后可再次尝试。`;
        return seal.replyToSender(ctx, msg, reply);
    }

    // 超过保护期，转发至管理群
    const config = getDb("paidan_config");
    if (config.adminGroupId) {
        const adminText = `⚠️ 【催单转发】客户 [CQ:at,qq=${o.uid}] 正在询问订单 [${orderId}] 的进度，工期已达 ${progress}%。`;
        sendNotify(config.adminGroupId, null, adminText);
        addOrderLog(`客户 ${o.uid} 对订单 ${orderId} 发起了催单`);
    } else {
        seal.replyToSender(ctx, msg, "⚠️ 系统尚未配置工作群，请联系管理员处理。");
        return seal.ext.newCmdExecuteResult(true);
    }
    seal.replyToSender(ctx, msg, "📫 催单请求已发送给劳斯，请耐心等待回复。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["催单"] = cmdUrge;

// ======================== 模块三：日志系统 ========================
function addOrderLog(desc) {
    let logs = getDb("paidan_logs");
    if (!Array.isArray(logs)) logs = [];
    logs.unshift({
        time: new Date().toLocaleString(),
        desc: desc
    });
    // 只保留最近200条
    if (logs.length > 200) logs = logs.slice(0, 200);
    setDb("paidan_logs", logs);
}

let cmdLog = seal.ext.newCmdItemInfo();
cmdLog.name = "排单日志";
cmdLog.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const logs = getDb("paidan_logs");
    if (!logs.length) return seal.replyToSender(ctx, msg, "暂无操作日志。");
    
    let res = "📒 【近期排单操作日志】\n";
    logs.slice(0, 10).forEach(l => {
        res += `[${l.time}] ${l.desc}\n`;
    });
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单日志"] = cmdLog;

// 扣卡完成
let cmdFinish = seal.ext.newCmdItemInfo();
cmdFinish.name = "扣卡";
cmdFinish.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orderId = cmdArgs.getArgN(1);
    const decr = parseInt(cmdArgs.getArgN(2)) || 1;

    let orders = getDb("paidan_orders");
    let users = getDb("paidan_users");
    if (!orders[orderId]) return seal.replyToSender(ctx, msg, "❌ 订单不存在");

    const uid = orders[orderId].uid;
    if (!users[uid]) return seal.replyToSender(ctx, msg, "❌ 找不到对应用户数据，请联系开发者检查。");
    if (users[uid].balance < decr) return seal.replyToSender(ctx, msg, `❌ 余额不足，当前余额 ${users[uid].balance} 张，无法扣除 ${decr} 张。`);

    users[uid].balance -= decr;
    orders[orderId].status = "已完成";

    setDb("paidan_orders", orders);
    setDb("paidan_users", users);

    const sent = sendNotify(orders[orderId].group, uid, `🎉 您的订单 [${orderId}] 已制作完成！\n本次扣除：${decr}\n剩余卡片数量：${users[uid].balance}`);
    const warnMsg = sent ? "" : "\n⚠️ 注意：订单来源群无记录，完成回执未能发出，请手动通知客户。";
    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 扣卡成功，剩余 ${users[uid].balance} 张。${warnMsg}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["扣卡"] = cmdFinish;

// ======================== 查询指令 ========================

// 1. 管理员：查看所有「待接单」订单
let cmdQueue = seal.ext.newCmdItemInfo();
cmdQueue.name = "查看待接单";
cmdQueue.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orders = getDb("paidan_orders");
    const queue = Object.values(orders).filter(o => o.status === "待接单");
    
    if (queue.length === 0) {
        seal.replyToSender(ctx, msg, "🍀 当前待接单池空空如也。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const users = getDb("paidan_users");
    let res = "📋 【待接单排队】\n";
    queue.forEach(o => {
        const preview = o.content.length > 50 ? o.content.slice(0, 50) + "…" : o.content;
        res += `【${o.id}】${preview}\n`;
    });
    res += "\n💡 发送「.查看订单详情 <编号>」查看完整内容";
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看待接单"] = cmdQueue;

// 2. 管理员：查看所有「待完成」订单 (新增)
let cmdTodoList = seal.ext.newCmdItemInfo();
cmdTodoList.name = "查看待完成";
cmdTodoList.help = ".查看待完成 (查看已接单待扣卡的任务列表)";
cmdTodoList.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orders = getDb("paidan_orders");
    const todoList = Object.values(orders).filter(o => o.status === "制作中" || o.status === "草图阶段");
    
    if (todoList.length === 0) {
        seal.replyToSender(ctx, msg, "✅ 恭喜！目前没有任何待完成的任务。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const users = getDb("paidan_users");
    let res = "🛠️ 【待完成任务清单】\n";
    todoList.forEach(o => {
        const preview = o.content.length > 50 ? o.content.slice(0, 50) + "…" : o.content;
        const urgent = o.isUrgent ? "⚡" : "";
        res += `【${o.id}】${urgent}${o.status} ${preview}\n`;
    });
    res += "\n💡 发送「.查看订单详情 <编号>」查看完整内容";
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看待完成"] = cmdTodoList;
ext.cmdMap["待完成列表"] = cmdTodoList;

let cmdUserList = seal.ext.newCmdItemInfo();
cmdUserList.name = "用户列表";
cmdUserList.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const users = getDb("paidan_users");
    const list = Object.entries(users);
    if (list.length === 0) return seal.replyToSender(ctx, msg, "暂无任何注册用户。");

    let res = `👥 【排单用户列表】共 ${list.length} 人\n`;
    list.forEach(([uid, u]) => {
        if (u.verified) {
            const daysLeft = Math.ceil((new Date(u.expiry) - Date.now()) / (1000 * 60 * 60 * 24));
            const expNote = daysLeft > 0 ? `期至${u.expiry}` : `已过期`;
            res += `${u.name}（${uid}）✅ 余额${u.balance}张 | ${expNote}\n`;
        } else {
            res += `${u.name}（${uid}）⏳ 待核对\n`;
        }
    });
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["用户列表"] = cmdUserList;

let cmdCleanExpired = seal.ext.newCmdItemInfo();
cmdCleanExpired.name = "清理过期用户";
cmdCleanExpired.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;

    let users = getDb("paidan_users");
    const orders = getDb("paidan_orders");
    const now = new Date();
    const removed = [];
    const skipped = [];

    for (const [uid, u] of Object.entries(users)) {
        if (!u.verified || u.expiry === "待核对") continue;
        if (new Date(u.expiry) >= now) continue;

        // 有进行中的订单则跳过，避免数据悬空
        const hasActive = Object.values(orders).some(
            o => o.uid === uid && o.status !== "已完成" && o.status !== "已拒绝" && o.status !== "已撤单"
        );
        if (hasActive) {
            skipped.push(`${u.name}（${uid}）`);
        } else {
            removed.push(`${u.name}（${uid}）`);
            delete users[uid];
        }
    }

    setDb("paidan_users", users);

    let res = removed.length > 0
        ? `✅ 已清理 ${removed.length} 位过期用户：\n${removed.join("\n")}`
        : "✅ 没有需要清理的过期用户。";
    if (skipped.length > 0) {
        res += `\n\n⚠️ 以下用户已过期但有进行中的订单，已跳过：\n${skipped.join("\n")}`;
    }
    if (removed.length > 0) addOrderLog(`清理过期用户 ${removed.length} 人：${removed.join("、")}`);

    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清理过期用户"] = cmdCleanExpired;

let cmdRemoveUser = seal.ext.newCmdItemInfo();
cmdRemoveUser.name = "移除用户";
cmdRemoveUser.help = ".移除用户 <UID>";
cmdRemoveUser.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const targetUid = cmdArgs.getArgN(1);
    if (!targetUid) return seal.replyToSender(ctx, msg, "❌ 请提供用户UID");

    let users = getDb("paidan_users");
    if (!users[targetUid]) return seal.replyToSender(ctx, msg, "❌ 找不到该用户");

    const orders = getDb("paidan_orders");
    const hasActive = Object.values(orders).some(
        o => o.uid === targetUid && o.status !== "已完成" && o.status !== "已拒绝" && o.status !== "已撤单"
    );
    if (hasActive) return seal.replyToSender(ctx, msg, `❌ 该用户有进行中的订单，请先处理完再移除。`);

    const name = users[targetUid].name;
    delete users[targetUid];
    setDb("paidan_users", users);

    addOrderLog(`管理员移除了用户 ${name}（${targetUid}）`);
    seal.replyToSender(ctx, msg, `✅ 已移除用户：${name}（${targetUid}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["移除用户"] = cmdRemoveUser;

let cmdDetail = seal.ext.newCmdItemInfo();
cmdDetail.name = "查看订单详情";
cmdDetail.help = ".查看订单详情 <编号>  查看指定订单的完整内容";
cmdDetail.solve = (ctx, msg, cmdArgs) => {
    const orderId = cmdArgs.getArgN(1);
    if (!orderId) return seal.replyToSender(ctx, msg, "❌ 请提供订单编号，格式：.查看订单详情 <编号>");

    const orders = getDb("paidan_orders");
    const o = orders[orderId];
    if (!o) return seal.replyToSender(ctx, msg, "❌ 订单不存在。");

    // 普通用户只能查看自己的订单
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    if (!isOrderAdmin(ctx, msg) && o.uid !== uid) {
        return seal.replyToSender(ctx, msg, "❌ 这不是您的订单。");
    }

    const users = getDb("paidan_users");
    const urgent = o.isUrgent ? " ⚡急单" : "";
    let res = `📄 【订单详情：${orderId}】\n`;
    res += `客户：${users[o.uid]?.name || '未知'}（${o.uid}）\n`;
    res += `状态：${o.status}${urgent}\n`;
    res += `来源群：${o.group}\n`;
    res += `下单时间：${new Date(o.timestamp).toLocaleString()}\n`;
    res += `————\n${o.content}`;
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看订单详情"] = cmdDetail;

let cmdMy = seal.ext.newCmdItemInfo();
cmdMy.name = "查看订单状态";
cmdMy.solve = (ctx, msg) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    const orders = getDb("paidan_orders");
    const my = Object.values(orders).filter(o => o.uid === uid && o.status !== "已完成");
    
    if (my.length === 0) return seal.replyToSender(ctx, msg, "您没有进行中的订单。");
    
    let res = "🔍 【进行中订单】\n";
    my.forEach(o => {
        const summary = o.content.length > 15 ? o.content.slice(0, 15) + "..." : o.content;
        res += `编号：${o.id}\n状态：${o.status}\n内容摘要：${summary}\n————\n`;
    });
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看订单状态"] = cmdMy;

let cmdBalance = seal.ext.newCmdItemInfo();
cmdBalance.name = "查余额";
cmdBalance.solve = (ctx, msg) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    const users = getDb("paidan_users");
    const user = users[uid];
    if (!user) return seal.replyToSender(ctx, msg, "❌ 您尚未注册，请先使用 .排单注册。");
    if (!user.verified) return seal.replyToSender(ctx, msg, "⏳ 您的注册尚未通过管理员核对。");

    const daysLeft = Math.ceil((new Date(user.expiry) - Date.now()) / (1000 * 60 * 60 * 24));
    const expiryNote = daysLeft > 0 ? `（还剩 ${daysLeft} 天）` : "（已过期）";
    seal.replyToSender(ctx, msg, `💳 【您的排单余额】\n姓名：${user.name}\n剩余数量：${user.balance} 张\n有效期至：${user.expiry} ${expiryNote}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查余额"] = cmdBalance;

let cmdCancel = seal.ext.newCmdItemInfo();
cmdCancel.name = "撤单";
cmdCancel.help = ".撤单 <订单编号>  （仅限「待接单」状态可撤）";
cmdCancel.solve = (ctx, msg, cmdArgs) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    const orderId = cmdArgs.getArgN(1);
    if (!orderId) return seal.replyToSender(ctx, msg, "❌ 请提供订单编号，格式：.撤单 <编号>");

    let orders = getDb("paidan_orders");
    const o = orders[orderId];
    if (!o) return seal.replyToSender(ctx, msg, "❌ 订单不存在。");
    if (o.uid !== uid) return seal.replyToSender(ctx, msg, "❌ 这不是您的订单。");
    if (o.status !== "待接单") return seal.replyToSender(ctx, msg, `❌ 订单已处于「${o.status}」状态，无法自行撤回。如需取消请联系管理员。`);

    orders[orderId].status = "已撤单";
    setDb("paidan_orders", orders);

    addOrderLog(`用户 ${uid} 撤回了订单 ${orderId}`);
    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 已撤回。如需重新下单请使用 .下单。`);

    const config = getDb("paidan_config");
    if (config.adminGroupId) {
        sendNotify(config.adminGroupId, null, `📭 用户 ${uid} 撤回了订单 [${orderId}]。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤单"] = cmdCancel;

// ======================== 进度与权重模块 ========================

// 1. 反馈草图
let cmdSketch = seal.ext.newCmdItemInfo();
cmdSketch.name = "反馈草图";
cmdSketch.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orderId = cmdArgs.getArgN(1);
    let orders = getDb("paidan_orders");
    if (!orders[orderId]) return seal.replyToSender(ctx, msg, "❌ 订单不存在");

    orders[orderId].status = "草图阶段";
    setDb("paidan_orders", orders);

    seal.replyToSender(ctx, msg, `🎨 订单 ${orderId} 进度已更新：草图已出。`);
    sendNotify(orders[orderId].group, orders[orderId].uid, `✨ 您的订单 [${orderId}] 已出草图！请及时确认进度。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["反馈草图"] = cmdSketch;

// 2. 调整优先级
let cmdPriority = seal.ext.newCmdItemInfo();
cmdPriority.name = "设为急单";
cmdPriority.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orderId = cmdArgs.getArgN(1);
    let orders = getDb("paidan_orders");
    if (!orders[orderId]) return;

    orders[orderId].isUrgent = true;
    setDb("paidan_orders", orders);
    seal.replyToSender(ctx, msg, `⚡ 订单 ${orderId} 已标记为高优先级急单。`);
    sendNotify(orders[orderId].group, orders[orderId].uid, `⚡ 您的订单 [${orderId}] 已被标记为急单，将优先处理。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设为急单"] = cmdPriority;

// ======================== 看板与统计 ========================

// 3. 排单看板
let cmdKanban = seal.ext.newCmdItemInfo();
cmdKanban.name = "排单看板";
cmdKanban.solve = (ctx, msg) => {
    const orders = getDb("paidan_orders");
    const activeOrders = Object.values(orders).filter(o => o.status !== "已完成" && o.status !== "已拒绝" && o.status !== "已撤单");
    
    if (activeOrders.length === 0) return seal.replyToSender(ctx, msg, "🟢 当前工坊空闲，暂无排单。");

    const users = getDb("paidan_users");
    let res = "📊 【工坊实时排单看板】\n";
    activeOrders.sort((a, b) => (b.isUrgent ? 1 : 0) - (a.isUrgent ? 1 : 0)); // 急单置顶

    activeOrders.forEach(o => {
        let icon = o.status === "待接单" ? "⚪" : (o.status === "草图阶段" ? "🟡" : "🟢");
        let urgent = o.isUrgent ? " [⚡急]" : "";
        let timeDiff = Math.floor((Date.now() - o.timestamp) / (1000 * 60 * 60 * 24));
        let timeout = timeDiff >= 3 ? " ⏳超时" : "";

        res += `${icon}${urgent} ${o.id} | ${users[o.uid]?.name || '访客'}${timeout}\n`;
        res += `   进度：${o.status} | 已排：${timeDiff}天\n`;
    });
    res += "\n💡 提示：⚪待接单 🟡草图 🟢制作中";
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单看板"] = cmdKanban;

// 4. 管理员月报统计
let cmdReport = seal.ext.newCmdItemInfo();
cmdReport.name = "排单月报";
cmdReport.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const orders = Object.values(getDb("paidan_orders"));
    const now = new Date();
    const currentMonth = now.getMonth();
    
    const currentYear = now.getFullYear();
    const monthlyOrders = orders.filter(o => {
        const d = new Date(o.timestamp);
        return d.getFullYear() === currentYear && d.getMonth() === currentMonth && o.status === "已完成";
    });

    let res = `📅 【${now.getMonth() + 1}月工坊结算报告】\n`;
    res += `✅ 本月结清：${monthlyOrders.length} 单\n`;
    
    // 简单客户排行
    let stats = {};
    monthlyOrders.forEach(o => stats[o.uid] = (stats[o.uid] || 0) + 1);
    let topUser = Object.entries(stats).sort((a,b) => b[1] - a[1])[0];
    
    if (topUser) {
        const userName = getDb("paidan_users")[topUser[0]]?.name || "匿名";
        res += `🏆 本月之星：${userName} (${topUser[1]}单)\n`;
    }
    
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单月报"] = cmdReport;

// ======================== 群发公告 ========================

let cmdBroadcast = seal.ext.newCmdItemInfo();
cmdBroadcast.name = "排单群发";
cmdBroadcast.help = ".排单群发 <内容>  向所有已核对客户发送公告";
cmdBroadcast.solve = (ctx, msg) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const content = msg.message.replace(/^[.。]排单群发\s*/, "").trim();
    if (!content) return seal.replyToSender(ctx, msg, "❌ 内容不能为空，用法：.排单群发 <内容>");

    const users = getDb("paidan_users");
    const verified = Object.entries(users).filter(([, u]) => u.verified);
    if (verified.length === 0) return seal.replyToSender(ctx, msg, "⚠️ 当前没有已核对的客户。");

    const text = `📢 【工坊公告】\n${content}`;
    let sent = 0, failed = 0;

    // 按群去重：同一个群只发一条，避免同群多人收到重复消息
    const groupMap = new Map(); // groupId → [uid, ...]
    for (const [uid, u] of verified) {
        if (!u.group) { failed++; continue; }
        if (!groupMap.has(u.group)) groupMap.set(u.group, []);
        groupMap.get(u.group).push(uid);
    }

    for (const [groupId, uids] of groupMap) {
        // 同群多人时合并 @ 列表
        const at = uids.map(uid => `[CQ:at,qq=${uid}]`).join(" ");
        const ok = sendNotify(groupId, null, at + " " + text);
        if (ok) sent += uids.length; else failed += uids.length;
    }

    addOrderLog(`管理员群发公告，成功 ${sent} 人，失败 ${failed} 人`);
    seal.replyToSender(ctx, msg, `✅ 群发完成。成功：${sent} 人，无群记录跳过：${failed} 人`);

    // 同步推送公告到网页端
    const base  = seal.ext.getStringConfig(ext, "网页端地址").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "网页端Token");
    if (base && token) {
        fetch(`${base}/api/announce`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
            body: JSON.stringify({ content, from: "Bot群发" })
        }).catch(() => {});
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单群发"] = cmdBroadcast;

// ======================== 后台巡检任务 ========================

function runOrderMonitor() {
    let orders = getDb("paidan_orders");
    let users = getDb("paidan_users");
    const config = getDb("paidan_config");
    let modified = false;

    // 1. 检查订单超时 (超过3天未完成)
    for (let id in orders) {
        let o = orders[id];
        if (o.status !== "已完成" && o.status !== "已拒绝" && o.status !== "已撤单") {
            let days = Math.floor((Date.now() - o.timestamp) / (1000 * 60 * 60 * 24));
            if (days >= 3 && !o.timeoutReminded) {
                sendNotify(config.adminGroupId, null, `⏳ 【订单积压预警】\n订单 [${id}] 已停滞 ${days} 天，请管理留意进度。`);
                o.timeoutReminded = true;
                modified = true;
            }
        }
    }

    // 2. 检查用户资产到期 (提前3天提醒)
    for (let uid in users) {
        let u = users[uid];
        if (u.verified && u.expiry !== "待核对") {
            let exp = new Date(u.expiry);
            let diff = Math.ceil((exp - Date.now()) / (1000 * 60 * 60 * 24));
            if (diff <= 3 && diff > 0 && !u.expiryReminded) {
                sendNotify(u.group, uid, `📢 【有效期预警】\n您的排单余额有效期仅剩 ${diff} 天，请及时联系管理续期。`);
                u.expiryReminded = true;
                modified = true;
            }
        }
    }

    if (modified) {
        setDb("paidan_orders", orders);
        setDb("paidan_users", users);
    }
    setTimeout(runOrderMonitor, 6 * 60 * 60 * 1000); // 每6小时巡检一次
}

// 启动延时巡检
setTimeout(runOrderMonitor, 10000);

// ======================== 网页端同步模块 ========================

seal.ext.registerStringConfig(ext, "网页端地址", "http://47.99.64.227:5237", "排单宝网页端服务器地址，末尾不带/");
seal.ext.registerStringConfig(ext, "网页端Token", "", "网页端超管后台账户页面的 API Token");

async function pushToWeb(ctx, msg, silent) {
    const base  = seal.ext.getStringConfig(ext, "网页端地址").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "网页端Token");
    if (!token) {
        if (!silent) seal.replyToSender(ctx, msg, "❌ 请先在插件设置中填写「网页端Token」");
        return false;
    }
    try {
        const resp = await fetch(`${base}/api/bot/push`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" },
            body: JSON.stringify({
                paidan_orders:    getDb("paidan_orders"),
                paidan_users:     getDb("paidan_users"),
                paidan_config:    getDb("paidan_config"),
                paidan_adminList: getDb("paidan_adminList"),
            })
        });
        const data = await resp.json();
        if (!silent) {
            seal.replyToSender(ctx, msg, data.ok ? "✅ 已同步到网页端" : `❌ 同步失败：${data.error}`);
        }
        return data.ok;
    } catch (e) {
        if (!silent) seal.replyToSender(ctx, msg, `❌ 网络错误：${String(e)}`);
        return false;
    }
}

// 手动同步指令
let cmdSyncWeb = seal.ext.newCmdItemInfo();
cmdSyncWeb.name = "同步网页端";
cmdSyncWeb.help = ".同步网页端  将当前所有排单数据推送到网页看板";
cmdSyncWeb.solve = async (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    await pushToWeb(ctx, msg, false);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步网页端"] = cmdSyncWeb;

// 拉取网页散单指令
let cmdPullWeb = seal.ext.newCmdItemInfo();
cmdPullWeb.name = "拉取散单";
cmdPullWeb.help = ".拉取散单  从网页端拉取新的散单，合并到排单队列";
cmdPullWeb.solve = async (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const base  = seal.ext.getStringConfig(ext, "网页端地址").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "网页端Token");
    if (!token) {
        seal.replyToSender(ctx, msg, "❌ 请先在插件设置中填写「网页端Token」");
        return seal.ext.newCmdExecuteResult(true);
    }
    try {
        const resp = await fetch(`${base}/api/sync`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        const data = await resp.json();
        if (!data.ok) {
            seal.replyToSender(ctx, msg, `❌ 拉取失败：${data.error}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        if (data.count === 0) {
            seal.replyToSender(ctx, msg, "✅ 暂无新散单");
            return seal.ext.newCmdExecuteResult(true);
        }

        let orders = getDb("paidan_orders");
        let newCount = 0;
        const lines = [];
        for (const o of data.orders) {
            const key = o.order_no;
            if (orders[key]) continue;
            const content = `【网页散单】称呼：${o.customer_name}  联系：${o.customer_contact}\n${o.description || o.title}`;
            orders[key] = {
                id:           key,
                uid:          o.customer_contact,
                content:      content,
                status:       "待接单",
                timestamp:    (o.created_at ? o.created_at * 1000 : Date.now()),
                isUrgent:     !!o.is_urgent,
                webOrderNo:   o.order_no,
                source:       "web",
                customerName: o.customer_name,
            };
            newCount++;
            lines.push(`· ${key}  ${o.customer_name}`);
        }

        if (newCount > 0) {
            setDb("paidan_orders", orders);
            addOrderLog(`从网页端拉取 ${newCount} 条散单`);
            await pushToWeb(ctx, msg, true);
        }

        const detail = lines.length ? "\n" + lines.join("\n") : "";
        seal.replyToSender(ctx, msg,
            `✅ 拉取完成，新增 ${newCount} 条散单${detail}\n发送 .排单看板 查看全部队列`);
    } catch (e) {
        seal.replyToSender(ctx, msg, `❌ 网络错误：${String(e)}`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拉取散单"] = cmdPullWeb;