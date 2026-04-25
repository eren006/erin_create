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

function sendNotify(groupId, userId, text) {
    const eps = seal.getEndPoints();
    if (eps.length > 0 && groupId) {
        const fakeMsg = seal.newMessage();
        fakeMsg.groupId = groupId;
        fakeMsg.messageType = 'group';
        const targetCtx = seal.createTempCtx(eps[0], fakeMsg);
        const at = userId ? `[CQ:at,qq=${userId}] ` : "";
        seal.replyToSender(targetCtx, fakeMsg, at + text);
    }
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
    if (!admins[msg.platform].includes(targetQQ)) {
        admins[msg.platform].push(targetQQ);
        setDb("paidan_adminList", admins);
        seal.replyToSender(ctx, msg, `✅ 已将 ${targetQQ} 设为排单管理员`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["添加排单管理员"] = cmdAdmin;

// ======================== 指令：系统配置 ========================

let cmdConfig = seal.ext.newCmdItemInfo();
cmdConfig.name = "设置下单格式";
cmdConfig.solve = (ctx, msg, cmdArgs) => {
    if (!isOrderAdmin(ctx, msg)) return;
    const format = msg.message.replace(".设置下单格式", "").trim();
    if (!format) return seal.replyToSender(ctx, msg, "❌ 格式不能为空");
    
    let config = getDb("paidan_config");
    config.orderFormat = format;
    setDb("paidan_config", config);
    seal.replyToSender(ctx, msg, `✅ 下单格式已更新为：\n${format}`);
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

// 2. 下单 (核心解析逻辑)
let cmdOrder = seal.ext.newCmdItemInfo();
cmdOrder.name = "下单";
cmdOrder.solve = (ctx, msg) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    let users = getDb("paidan_users");
    const user = users[uid];

    if (!user || !user.verified) return seal.replyToSender(ctx, msg, "❌ 您尚未通过管理员核对，无法下单。");
    if (new Date(user.expiry) < new Date()) return seal.replyToSender(ctx, msg, `⚠️ 您的卡片已于 ${user.expiry} 过期，无法下单。`);
    if (user.balance <= 0) return seal.replyToSender(ctx, msg, "⚠️ 您的剩余数量不足，请联系管理增补。");

    const orderId = "P" + Date.now().toString().slice(-6);
    let orders = getDb("paidan_orders");
    orders[orderId] = {
        id: orderId,
        uid: uid,
        content: msg.message.replace(".下单", "").trim(),
        status: "待接单",
        group: msg.groupId,
        timestamp: Date.now()
    };
    setDb("paidan_orders", orders);

    seal.replyToSender(ctx, msg, `✅ 下单成功！订单编号：${orderId}\n状态：等待管理员接单`);
    
    // 工作群同步
    const config = getDb("paidan_config");
    if (config.adminGroupId) {
        const text = `🔥 【新订单：${orderId}】\n客户：${user.name}\n内容：\n${orders[orderId].content}`;
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

    let users = getDb("paidan_users");
    if (!users[targetUid]) return seal.replyToSender(ctx, msg, "❌ 找不到该用户");

    users[targetUid].balance = realCount;
    users[targetUid].expiry = expiry;
    users[targetUid].verified = true;
    users[targetUid].expiryReminded = false;
    setDb("paidan_users", users);

    seal.replyToSender(ctx, msg, `✅ 用户 ${users[targetUid].name} 核对完成。`);
    
    // 回执到用户群
    sendNotify(users[targetUid].group, targetUid, `✨ 管理员已完成您的资产核对！\n核定数量：${realCount}\n有效期至：${expiry}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["排单核对"] = cmdCheck;

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

    orders[orderId].status = "制作中";
    orders[orderId].acceptTime = Date.now(); // 记录接单确切时间
    orders[orderId].duration = duration;
    setDb("paidan_orders", orders);

    // 写入日志
    addOrderLog(`管理员 ${msg.sender.nickname} 接收了订单 ${orderId}，预计工期 ${duration} 天`);

    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 已接单，预计工期 ${duration} 天。`);
    sendNotify(orders[orderId].group, orders[orderId].uid, `🔔 管理员已接单！预计交付：${duration}天内。请给劳斯一点创作时间哦~`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["接单"] = cmdAccept;

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
    users[uid].balance -= decr;
    orders[orderId].status = "已完成";
    
    setDb("paidan_orders", orders);
    setDb("paidan_users", users);

    seal.replyToSender(ctx, msg, `✅ 订单 ${orderId} 扣卡成功，剩余 ${users[uid].balance} 张。`);
    
    sendNotify(orders[orderId].group, uid, `🎉 您的订单 [${orderId}] 已制作完成！\n本次扣除：${decr}\n剩余卡片数量：${users[uid].balance}`);
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
        res += `编号：${o.id}\n客户：${users[o.uid]?.name || '未知'}\n群号：${o.group}\n内容：${o.content.slice(0, 30)}...\n————\n`;
    });
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
        res += `编号：${o.id}\n客户：${users[o.uid]?.name || '未知'}\n群号：${o.group}\n需求：${o.content}\n————\n`;
    });
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看待完成"] = cmdTodoList;
ext.cmdMap["待完成列表"] = cmdTodoList;

let cmdMy = seal.ext.newCmdItemInfo();
cmdMy.name = "查看订单状态";
cmdMy.solve = (ctx, msg) => {
    const uid = msg.sender.userId.replace(`${msg.platform}:`, "");
    const orders = getDb("paidan_orders");
    const my = Object.values(orders).filter(o => o.uid === uid && o.status !== "已完成");
    
    if (my.length === 0) return seal.replyToSender(ctx, msg, "您没有进行中的订单。");
    
    let res = "🔍 【进行中订单】\n";
    my.forEach(o => {
        res += `编号：${o.id}\n状态：${o.status}\n内容摘要：${o.content.slice(0,15)}...\n————\n`;
    });
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看订单状态"] = cmdMy;

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
    const activeOrders = Object.values(orders).filter(o => o.status !== "已完成");
    
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

// ======================== 后台巡检任务 ========================

function runOrderMonitor() {
    let orders = getDb("paidan_orders");
    let users = getDb("paidan_users");
    const config = getDb("paidan_config");
    let modified = false;

    // 1. 检查订单超时 (超过3天未完成)
    for (let id in orders) {
        let o = orders[id];
        if (o.status !== "已完成") {
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