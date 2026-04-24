// ==UserScript==
// @name         留言板系统
// @author       长日将尽
// @version      1.2.0
// @description  留言板系统：支持注册/匿名发言、冷却、每日限额、合并转发分片
// @timestamp    1742205760
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find("messageBoard")
if (!ext) {
    ext = seal.ext.new("messageBoard", "留言板系统", "1.2.0");
    seal.ext.register(ext);
    ext.autoActive = true;
}

// ========================
// 📦 存储键名
// ========================
const STORAGE_MESSAGES = "message_board_messages";      // 留言板数组
const STORAGE_PUBLIC_GROUP = "message_board_public_group"; // 公示群号
const STORAGE_USERS = "message_board_users";            // 注册用户表 { QQ: { username, registeredAt } }
const STORAGE_CONFIG = "message_board_config";          // 配置 { allowAnonymous, cooldownSeconds, dailyLimit }
const STORAGE_DAILY_COUNTS = "message_board_daily_counts"; // 每日发言计数 { QQ: { dateStr, count } }

seal.ext.registerStringConfig(ext, "ws地址", "ws://localhost:3001");
seal.ext.registerStringConfig(ext, "ws Access token", '', "输入与上方端口对应的token，没有则留空");
let whiteList = 0;

// ========================
// 🛠️ 辅助函数
// ========================

// 获取当前自然日字符串 YYYY-MM-DD
function getTodayStr() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}

// 获取配置
function getConfig() {
    const defaultConfig = {
        allowAnonymous: true,   
        allowCustomName: true,  // 【新增】是否允许自定义署名/匿名
        cooldownSeconds: 30,    
        dailyLimit: 10          
    };
    const stored = JSON.parse(ext.storageGet(STORAGE_CONFIG) || "{}");
    return { ...defaultConfig, ...stored };
}

function saveConfig(config) {
    ext.storageSet(STORAGE_CONFIG, JSON.stringify(config));
}

// 获取注册用户表 { QQ: { username, registeredAt } }
function getUsers() {
    return JSON.parse(ext.storageGet(STORAGE_USERS) || "{}");
}

function saveUsers(users) {
    ext.storageSet(STORAGE_USERS, JSON.stringify(users));
}

// 计算等级与头衔
function getLevelInfo(exp = 0) {
    const lvl = Math.floor(Math.sqrt(exp / 10));
    let title = "初来乍到";
    if (lvl >= 5) title = "活跃分子";
    if (lvl >= 10) title = "留言达人";
    if (lvl >= 20) title = "社区领袖";
    return { lvl, title };
}

// 增加经验
function addExp(qq, amount) {
    let users = getUsers();
    if (users[qq]) {
        users[qq].exp = (users[qq].exp || 0) + amount;
        saveUsers(users);
    }
}

// 获取或注册用户（自动注册：如果未注册则用QQ号作为用户名）
function getOrRegisterUser(qq, nickname) {
    let users = getUsers();
    if (!users[qq]) {
        const username = nickname ? nickname.trim() : `用户${qq.slice(-4)}`;
        users[qq] = {
            username: username,
            registeredAt: Date.now()
        };
        saveUsers(users);
        return username;
    }
    return users[qq].username;
}

// 获取用户今日发言次数
function getUserDailyCount(qq) {
    const today = getTodayStr();
    const counts = JSON.parse(ext.storageGet(STORAGE_DAILY_COUNTS) || "{}");
    if (!counts[qq]) return 0;
    if (counts[qq].date !== today) return 0;
    return counts[qq].count || 0;
}

// 增加用户今日发言次数
function incrementUserDailyCount(qq) {
    const today = getTodayStr();
    const counts = JSON.parse(ext.storageGet(STORAGE_DAILY_COUNTS) || "{}");
    if (!counts[qq]) {
        counts[qq] = { date: today, count: 1 };
    } else if (counts[qq].date !== today) {
        counts[qq] = { date: today, count: 1 };
    } else {
        counts[qq].count += 1;
    }
    ext.storageSet(STORAGE_DAILY_COUNTS, JSON.stringify(counts));
}

// 检查冷却
function getCooldownRemaining(qq) {
    const key = `msg_cd_${qq}`;
    const lastTime = parseInt(ext.storageGet(key) || "0");
    const config = getConfig();
    const now = Date.now();
    const elapsed = now - lastTime;
    if (elapsed < config.cooldownSeconds * 1000) {
        return Math.ceil((config.cooldownSeconds * 1000 - elapsed) / 1000);
    }
    return 0;
}

function setCooldown(qq) {
    const key = `msg_cd_${qq}`;
    ext.storageSet(key, Date.now().toString());
}

// 获取发送者的QQ号
function getSenderQQ(msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    return uid;
}

// 获取发送者的展示名称（注册名或匿名）
function getSenderDisplayName(ctx, msg, useAnonymous = false) {
    const qq = getSenderQQ(msg);
    if (!useAnonymous) {
        const users = getUsers();
        if (users[qq]) {
            return users[qq].username;
        }
        // 未注册则自动注册（使用QQ昵称或默认）
        const nickname = msg.sender.card || msg.sender.nickname || `用户${qq.slice(-4)}`;
        return getOrRegisterUser(qq, nickname);
    } else {
        // 匿名：返回固定格式
        return "匿名网友";
    }
}

// 检查是否为管理员
function isAdmin(ctx, msg) {
    return msg.isMaster || ctx.privilegeLevel === 100;
}

// ========================
// 🌐 WebSocket 发送函数（复用长日系统的连接配置）
// ========================
function wsRequest(postData, ctx, msg, successReply) {
    const wsUrl = seal.ext.getStringConfig(ext, "ws地址");
    const token = seal.ext.getStringConfig(ext, "ws Access token");
    let connectionUrl = wsUrl;
    if (token) {
        const separator = connectionUrl.includes('?') ? '&' : '?';
        connectionUrl += `${separator}access_token=${encodeURIComponent(token)}`;
    }
    const currentEcho = (postData.action || "request") + "_" + Date.now();
    postData.echo = currentEcho;

    if (postData.params) {
        if (postData.params.message_id) postData.params.message_id = parseInt(postData.params.message_id);
        if (postData.params.group_id) postData.params.group_id = parseInt(postData.params.group_id);
    }

    const ws = new WebSocket(connectionUrl);
    let isClosed = false;
    let timeoutId = setTimeout(() => {
        if (!isClosed) {
            console.log(`[留言板WS] 请求超时: ${postData.action}`);
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close(1000, "TIMEOUT");
            }
            isClosed = true;
        }
    }, 6000);

    ws.onopen = function() {
        try {
            ws.send(JSON.stringify(postData));
        } catch (e) {
            console.error('[留言板WS] 发送失败:', e);
            clearTimeout(timeoutId);
            isClosed = true;
            ws.close();
        }
    };

    ws.onmessage = function(event) {
        try {
            const response = JSON.parse(event.data);
            if (response.post_type === "meta_event") return;
            if (response.echo !== currentEcho) return;
            clearTimeout(timeoutId);
            if (response.status === 'ok' || response.retcode === 0) {
                if (successReply) seal.replyToSender(ctx, msg, successReply);
            } else {
                console.error(`[留言板WS] 错误: ${JSON.stringify(response)}`);
            }
        } catch (e) {
            console.error('[留言板WS] 解析异常:', e);
        }
        if (ws.readyState === WebSocket.OPEN) ws.close(1000, "DONE");
        isClosed = true;
    };

    ws.onerror = function(e) {
        if (!isClosed) console.error('[留言板WS] 连接异常');
        clearTimeout(timeoutId);
        isClosed = true;
    };

    ws.onclose = function() {
        clearTimeout(timeoutId);
        isClosed = true;
    };
}

/**
 * 发送合并转发消息到指定群（自动分片，每片最多90个节点）
 */
function sendForwardToGroup(groupId, nodes, ctx, msg) {
    if (!groupId || !nodes || nodes.length === 0) return;
    const MAX_NODES_PER_FORWARD = 90;

    if (nodes.length <= MAX_NODES_PER_FORWARD) {
        const postData = {
            action: "send_group_forward_msg",
            params: {
                group_id: parseInt(groupId, 10),
                messages: nodes
            }
        };
        wsRequest(postData, ctx, msg, null);
        return;
    }

    const headNode = nodes[0];
    const bodyNodes = nodes.slice(1);
    const totalBody = bodyNodes.length;
    const firstChunkSize = MAX_NODES_PER_FORWARD - 1;
    const otherChunkSize = MAX_NODES_PER_FORWARD;

    let offset = 0;
    let chunkIndex = 0;

    while (offset < totalBody) {
        let chunkNodes = [];
        if (chunkIndex === 0) {
            const end = Math.min(offset + firstChunkSize, totalBody);
            chunkNodes = [headNode, ...bodyNodes.slice(offset, end)];
            offset = end;
        } else {
            const end = Math.min(offset + otherChunkSize, totalBody);
            const continueNode = {
                type: "node",
                data: {
                    name: "📌 留言板",
                    uin: "2852199344",
                    content: "━━━━━━ 接上一条 ━━━━━━"
                }
            };
            chunkNodes = [continueNode, ...bodyNodes.slice(offset, end)];
            offset = end;
        }
        const postData = {
            action: "send_group_forward_msg",
            params: {
                group_id: parseInt(groupId, 10),
                messages: chunkNodes
            }
        };
        wsRequest(postData, ctx, msg, null);
        chunkIndex++;
    }
}

function sendTextToGroup(groupId, text, ctx, msg) {
    if (!groupId || !text) return;
    const postData = {
        action: "send_group_msg",
        params: {
            group_id: parseInt(groupId, 10),
            message: text
        }
    };
    wsRequest(postData, ctx, msg, null);
}

// ========================
// 📋 构建合并转发节点
// ========================
function buildMessageNodes(messages) {
    const DEFAULT_UIN = "2852199344"; 
    
    // 【核心改动】仅截取最后20条留言进行展示
    const displayMsgs = messages.slice(-20);
    
    const nodes = [];
    nodes.push({
        type: "node",
        data: {
            name: "📢 留言板",
            uin: DEFAULT_UIN,
            content: `✨ 当前展示最近 ${displayMsgs.length} 条留言 (总计 ${messages.length} 条) ✨`
        }
    });

    displayMsgs.forEach(m => {
        const timeStr = new Date(m.timestamp).toLocaleString("zh-CN", { hour12: false });
        nodes.push({
            type: "node",
            data: {
                name: m.displayName,
                uin: DEFAULT_UIN, 
                content: `【${m.displayName}】 ${timeStr}\n${m.content}`
            }
        });
    });
    return nodes;
}

function buildTextMessageList(messages) {
    if (!messages.length) return "📭 当前没有任何留言。";
    let text = "📋 留言板列表（用于撤回）：\n\n";
    const sorted = [...messages].sort((a, b) => a.timestamp - b.timestamp);
    sorted.forEach((msg, idx) => {
        const timeStr = new Date(msg.timestamp).toLocaleString("zh-CN", { hour12: false });
        text += `【${idx+1}】${msg.displayName} | ${timeStr}\n    ${msg.content}\n\n`;
    });
    return text;
}

// ========================
// 🔄 刷新公示群
// ========================
function refreshPublicBoard(ctx, msg) {
    const publicGroup = ext.storageGet(STORAGE_PUBLIC_GROUP) || "";
    if (!publicGroup) return false;
    const messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    const nodes = buildMessageNodes(messages);
    sendForwardToGroup(publicGroup, nodes, ctx, msg);
    return true;
}

// ========================
// 📝 核心留言指令
// ========================
let cmd_post_msg = seal.ext.newCmdItemInfo();
cmd_post_msg.name = "留言板";
cmd_post_msg.help = "。留言板 [自定义署名/匿名] 内容 —— 添加留言\n示例：\n。留言板 你好世界\n。留言板 匿名 悄悄话\n。留言板 某某 这里的风景真好";
cmd_post_msg.solve = (ctx, msg, cmdArgs) => {
    const config = getConfig();
    const qq = getSenderQQ(msg);
    
    // 1. 解析参数
    let firstArg = cmdArgs.getArgN(1);
    let secondArg = cmdArgs.getArgN(2);
    
    let content = "";
    let displayName = "";
    let isAnonymous = false;

    if (secondArg) {
        // 【核心修改】检查是否允许自定义署名或匿名
        if (!config.allowCustomName) {
            seal.replyToSender(ctx, msg, "❌ 当前留言板已由管理员关闭了自定义署名及匿名功能。");
            return seal.ext.newCmdExecuteResult(true);
        }
        
        isAnonymous = true; // 使用自定义名称或匿名视为匿名模式，不计入主页历史
        displayName = (firstArg === "匿名" || firstArg === "anonymous") ? "匿名网友" : firstArg;
        content = secondArg;
        
        // 限制长度
        if (displayName.length > 20) {
            seal.replyToSender(ctx, msg, "❌ 署名太长了（限20字）。");
            return seal.ext.newCmdExecuteResult(true);
        }
    } else {
        // 标准实名留言：使用注册昵称或QQ昵称
        content = firstArg;
        isAnonymous = false;
        const nickname = msg.sender.card || msg.sender.nickname || `用户${qq.slice(-4)}`;
        displayName = getOrRegisterUser(qq, nickname);
    }
    
    if (!content) {
        const helpMsg = config.allowCustomName 
            ? "💡 请输入留言内容，格式：\n。留言板 内容\n。留言板 [自定义署名] 内容" 
            : "💡 请输入留言内容，格式：\n。留言板 内容";
        seal.replyToSender(ctx, msg, helpMsg);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 2. 冷却检查
    const remainingCd = getCooldownRemaining(qq);
    if (remainingCd > 0) {
        seal.replyToSender(ctx, msg, `⏳ 冷却中，请 ${remainingCd} 秒后再试。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 3. 每日次数检查
    const todayCount = getUserDailyCount(qq);
    if (todayCount >= config.dailyLimit) {
        seal.replyToSender(ctx, msg, `📊 今日留言次数已达上限（${config.dailyLimit}次），明天再来吧～`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 4. 生成留言对象
    const id = Math.random().toString(36).substring(2, 8).toUpperCase();
    const newMessage = {
        id: id,
        content: content,
        displayName: displayName,
        senderUid: qq,
        timestamp: Date.now(),
        isAnonymous: isAnonymous,
        likes: [] 
    };
    
    let messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    messages.push(newMessage);
    ext.storageSet(STORAGE_MESSAGES, JSON.stringify(messages));
    
    // 5. 经验值结算：只有实名留言才涨经验
    if (!isAnonymous) {
        // 假设 addExp 函数在你的脚本其他地方已定义
        if (typeof addExp === "function") {
            addExp(qq, 10);
        }
    }
    
    // 6. 更新冷却和每日计数
    setCooldown(qq);
    incrementUserDailyCount(qq);
    
    const remainingDaily = config.dailyLimit - (todayCount + 1);
    seal.replyToSender(ctx, msg, `✅ 留言已成功添加！\n👤 显示署名：${displayName}\n📊 今日剩余次数：${remainingDaily}`);
    
    // 7. 刷新公示群（将触发仅展示最近20条的逻辑）
    refreshPublicBoard(ctx, msg);
    
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["留言板"] = cmd_post_msg;

// ========================
// 📋 留言列表（文本）
// ========================
let cmd_list_messages = seal.ext.newCmdItemInfo();
cmd_list_messages.name = "留言列表";
cmd_list_messages.help = "。留言列表 —— 查看留言板所有留言及序号（用于撤回）";
cmd_list_messages.solve = (ctx, msg, cmdArgs) => {
    const messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    const text = buildTextMessageList(messages);
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["留言列表"] = cmd_list_messages;

// ========================
// 👀 查看留言板（合并转发）
// ========================
let cmd_view_board = seal.ext.newCmdItemInfo();
cmd_view_board.name = "查看留言板";
cmd_view_board.help = "。查看留言板 —— 以合并转发形式查看留言板完整内容";
cmd_view_board.solve = (ctx, msg, cmdArgs) => {
    const groupId = msg.groupId ? msg.groupId.replace(/[^\d]/g, "") : "";
    if (!groupId) {
        seal.replyToSender(ctx, msg, "请在群内使用此指令。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    const nodes = buildMessageNodes(messages);
    sendForwardToGroup(groupId, nodes, ctx, msg);
    seal.replyToSender(ctx, msg, `📬 已将留言板（共${messages.length}条）以合并转发形式发送至本群。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看留言板"] = cmd_view_board;

// ========================
// 🗑️ 撤留言
// ========================
let cmd_withdraw_message = seal.ext.newCmdItemInfo();
cmd_withdraw_message.name = "撤留言";
cmd_withdraw_message.help = "。撤留言—— 撤回自己发布的留言（管理员可撤任意）";
cmd_withdraw_message.solve = (ctx, msg, cmdArgs) => {
    const qq = getSenderQQ(msg);
    let messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    
    // 【改动】倒序查找该用户的最后一条留言
    let lastIdx = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].senderUid === qq) {
            lastIdx = i;
            break;
        }
    }

    if (lastIdx === -1) {
        seal.replyToSender(ctx, msg, "❌ 你近期没有发布过留言，或留言已被撤回。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const targetContent = messages[lastIdx].content;
    messages.splice(lastIdx, 1); // 移除该条
    
    ext.storageSet(STORAGE_MESSAGES, JSON.stringify(messages));
    seal.replyToSender(ctx, msg, `✅ 已成功撤回你的上一条留言：\n「${targetContent}」`);
    refreshPublicBoard(ctx, msg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤留言"] = cmd_withdraw_message;

// ========================
// 👤 注册/改名指令（已增加查重）
// ========================
let cmd_register = seal.ext.newCmdItemInfo();
cmd_register.name = "留言板注册";
cmd_register.help = "。留言板注册 昵称 —— 注册或修改昵称（不可重复）";
cmd_register.solve = (ctx, msg, cmdArgs) => {
    let newName = cmdArgs.getArgN(1);
    if (!newName) {
        seal.replyToSender(ctx, msg, "请提供昵称，例如：。留言板注册 小明");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (newName.length > 20) {
        seal.replyToSender(ctx, msg, "❌ 昵称太长了，不能超过20个字符。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const qq = getSenderQQ(msg);
    let users = getUsers();

    // --- 新增：查重逻辑 ---
    for (let uid in users) {
        // 如果这个名字已被占用，且占用者不是当前发送者本人
        if (users[uid].username === newName && uid !== qq) {
            seal.replyToSender(ctx, msg, `❌ 注册失败，「${newName}」已经被别人抢先占用啦，换个名字试试吧？`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }
    // --------------------

    if (!users[qq]) {
        // 新用户注册
        users[qq] = { 
            username: newName, 
            registeredAt: Date.now(),
            exp: 0, // 初始化经验
            bio: ""  // 初始化签名
        };
    } else {
        // 老用户改名
        users[qq].username = newName;
    }

    saveUsers(users);
    seal.replyToSender(ctx, msg, `✅ 昵称设置成功！现在你可以通过「。查看用户 ${newName}」来查看自己的主页了。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["留言板注册"] = cmd_register;

// ========================
// ⚙️ 管理员配置指令 (已增加署名开关)
// ========================
let cmd_config = seal.ext.newCmdItemInfo();
cmd_config.name = "留言板配置";
cmd_config.help = "。留言板配置 [署名|冷却|上限] [on/off|数值] —— 管理员设置\n示例：\n。留言板配置 署名 off\n。留言板配置 冷却 60\n。留言板配置 上限 20";
cmd_config.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const key = cmdArgs.getArgN(1);
    const value = cmdArgs.getArgN(2);
    const config = getConfig();
    
    if (key === "署名") {
        // 控制是否允许自定义署名/匿名
        if (value === "on" || value === "开") {
            config.allowCustomName = true;
            seal.replyToSender(ctx, msg, "✅ 自定义署名/匿名留言已开启");
        } else if (value === "off" || value === "关") {
            config.allowCustomName = false;
            seal.replyToSender(ctx, msg, "✅ 自定义署名/匿名留言已关闭（仅限注册名发言）");
        } else {
            seal.replyToSender(ctx, msg, `当前署名功能：${config.allowCustomName ? "开启" : "关闭"}\n使用「。留言板配置 署名 on/off」切换`);
        }
    } 
    else if (key === "冷却") {
        const sec = parseInt(value);
        if (!isNaN(sec) && sec >= 0 && sec <= 3600) {
            config.cooldownSeconds = sec;
            seal.replyToSender(ctx, msg, `✅ 冷却时间已设置为 ${sec} 秒`);
        } else {
            seal.replyToSender(ctx, msg, `当前冷却：${config.cooldownSeconds} 秒\n使用「。留言板配置 冷却 秒数」设置`);
        }
    }
    else if (key === "上限") {
        const limit = parseInt(value);
        if (!isNaN(limit) && limit >= 1 && limit <= 100) {
            config.dailyLimit = limit;
            seal.replyToSender(ctx, msg, `✅ 每日留言上限已设置为 ${limit} 条`);
        } else {
            seal.replyToSender(ctx, msg, `当前每日上限：${config.dailyLimit} 条\n使用「。留言板配置 上限 数字」设置`);
        }
    }
    else {
        // 显示当前所有配置状态
        seal.replyToSender(ctx, msg, `📋 当前留言板配置：
• 自定义署名：${config.allowCustomName ? "开启" : "关闭"}
• 冷却时间：${config.cooldownSeconds} 秒
• 每日上限：${config.dailyLimit} 条
使用「。留言板配置 署名/冷却/上限」进行修改`);
    }
    
    saveConfig(config);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["留言板配置"] = cmd_config;

// ========================
// 🧹 管理员：设置公示群
// ========================
let cmd_set_public = seal.ext.newCmdItemInfo();
cmd_set_public.name = "设置留言板群";
cmd_set_public.help = "。设置留言板群 群号 —— 设置公示群";
cmd_set_public.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    let gid = cmdArgs.getArgN(1);
    if (!gid) {
        const current = ext.storageGet(STORAGE_PUBLIC_GROUP) || "未设置";
        seal.replyToSender(ctx, msg, `当前公示群：${current}\n使用「。设置留言板群 群号」设置`);
        return seal.ext.newCmdExecuteResult(true);
    }
    gid = gid.replace(/[^\d]/g, "");
    if (!gid) {
        seal.replyToSender(ctx, msg, "无效的群号");
        return seal.ext.newCmdExecuteResult(true);
    }
    ext.storageSet(STORAGE_PUBLIC_GROUP, gid);
    seal.replyToSender(ctx, msg, `✅ 公示群已设置为 ${gid}`);
    refreshPublicBoard(ctx, msg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置留言板群"] = cmd_set_public;

// ========================
// 📝 指令扩展：点赞
// ========================
let cmd_like = seal.ext.newCmdItemInfo();
cmd_like.name = "点赞";
cmd_like.help = "。点赞 序号 —— 给留言板上的某条留言点赞";
cmd_like.solve = (ctx, msg, cmdArgs) => {
    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    const qq = msg.sender.userId.replace(/\D/g, "");
    
    let messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    if (isNaN(idx) || idx < 0 || idx >= messages.length) {
        seal.replyToSender(ctx, msg, "❌ 序号错误，请使用「。留言列表」查看");
        return seal.ext.newCmdExecuteResult(true);
    }

    const target = messages[idx];
    if (!target.likes) target.likes = [];
    if (target.likes.includes(qq)) {
        seal.replyToSender(ctx, msg, "⚠️ 你已经给这条留言点过赞啦~");
        return seal.ext.newCmdExecuteResult(true);
    }

    target.likes.push(qq);
    ext.storageSet(STORAGE_MESSAGES, JSON.stringify(messages));
    addExp(target.senderUid, 2); // 被点赞者加经验
    
    seal.replyToSender(ctx, msg, `👍 点赞成功！这条留言目前已有 ${target.likes.length} 个赞。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["点赞"] = cmd_like;

// ========================
// 👤 指令扩展：查看用户 & 签名
// ========================
let cmd_user_profile = seal.ext.newCmdItemInfo();
cmd_user_profile.name = "查看用户";
cmd_user_profile.help = "。查看用户 [名字] —— 查看指定用户的个人主页";
cmd_user_profile.solve = (ctx, msg, cmdArgs) => {
    const targetName = cmdArgs.getArgN(1);
    const users = getUsers();
    const messages = JSON.parse(ext.storageGet(STORAGE_MESSAGES) || "[]");
    
    let targetUid = null;
    let userData = null;

    // 查找用户
    for (let uid in users) {
        if (users[uid].username === targetName) {
            targetUid = uid;
            userData = users[uid];
            break;
        }
    }

    if (!userData) {
        seal.replyToSender(ctx, msg, "🔍 未找到该用户，请确认名字输入正确。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const info = getLevelInfo(userData.exp);
    
    // 核心改动：严格过滤掉该用户的所有匿名留言
    const userMsgs = messages.filter(m => 
        m.senderUid === targetUid && 
        m.isAnonymous === false // 确保只抓取实名发言
    ).slice(-5).reverse();

    let profile = `👤 【${userData.username}】的个人主页\n`;
    profile += `━━━━━━━━━━━━━━\n`;
    profile += `称号：${info.title} (Lv.${info.lvl})\n`;
    profile += `经验：${userData.exp || 0}\n`;
    profile += `签名：${userData.bio || "这个人很懒，什么都没写。"}\n`;
    profile += `━━━━━━━━━━━━━━\n`;
    profile += `📝 最近公开留言：\n`; // 标注为“公开”
    
    if (userMsgs.length === 0) {
        profile += "暂无公开留言";
    } else {
        userMsgs.forEach((m, i) => {
            // 这里显示的都是 isAnonymous 为 false 的内容
            profile += `${i+1}. ${m.content.substring(0,20)}${m.content.length > 20 ? "..." : ""}\n`;
        });
    }

    seal.replyToSender(ctx, msg, profile);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看用户"] = cmd_user_profile;

let cmd_set_bio = seal.ext.newCmdItemInfo();
cmd_set_bio.name = "设置签名";
cmd_set_bio.help = "。设置签名 内容 —— 设置个人主页的个性签名";
cmd_set_bio.solve = (ctx, msg, cmdArgs) => {
    // 使用 getRestArgsFrom(1) 获取第一个参数之后的所有内容
    const bio = cmdArgs.getRestArgsFrom(1).trim(); 
    
    if (!bio) {
        seal.replyToSender(ctx, msg, "💡 请输入要设置的签名内容。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const qq = msg.sender.userId.replace(/\D/g, "");
    let users = getUsers();
    if (!users[qq]) {
        seal.replyToSender(ctx, msg, "❌ 请先进行「。留言板注册」");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 限制长度并保存
    users[qq].bio = bio.substring(0, 50);
    saveUsers(users);
    seal.replyToSender(ctx, msg, "✅ 签名设置成功！");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置签名"] = cmd_set_bio;

// ========================
// 🧹 管理员：清空留言板
// ========================
let cmd_clear_board = seal.ext.newCmdItemInfo();
cmd_clear_board.name = "清空留言板";
cmd_clear_board.help = "。清空留言板 —— 一键清空所有留言";
cmd_clear_board.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    ext.storageSet(STORAGE_MESSAGES, "[]");
    seal.replyToSender(ctx, msg, "✅ 留言板已清空");
    refreshPublicBoard(ctx, msg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空留言板"] = cmd_clear_board;


// 🚨 新增：系统重置指令
// ========================
let cmd_reset_all = seal.ext.newCmdItemInfo();
cmd_reset_all.name = "重置留言板";
cmd_reset_all.help = "。重置留言板 —— 【危险】清空所有数据恢复出厂设置";
cmd_reset_all.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    
    // 清空所有相关存储
    ext.storageSet(STORAGE_MESSAGES, "[]");
    ext.storageSet(STORAGE_USERS, "{}");
    ext.storageSet(STORAGE_DAILY_COUNTS, "{}");
    ext.storageSet(STORAGE_CONFIG, "{}");
    
    seal.replyToSender(ctx, msg, "☣️ 留言板已彻底重置。所有注册信息、经验、留言已灰飞烟灭。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["重置留言板"] = cmd_reset_all;

// ========================
// ℹ️ 帮助
// ========================
let cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = "留言板帮助";
cmd_help.help = "显示所有指令";
cmd_help.solve = (ctx, msg, cmdArgs) => {
    const helpText = `📢 【留言板系统 v1.2】

【普通用户】
• 。留言板注册 昵称 - 注册/修改显示昵称
• 。留言板 [自定义名/匿名] 内容 - 添加留言（匿名需配置开启）
• 。查看留言板 - 合并转发查看完整留言板
• 。留言列表 - 查看带序号的留言列表（用于撤回）
• 。撤留言 - 撤回自己最后一条的留言
• 。点赞 序号 - 给喜欢的留言点赞
• 。查看用户 名字 - 查看个人等级、签名和历史
• 。设置签名 内容 - 自定义主页展示

【管理员】
• 。留言板配置 匿名 on/off - 允许/禁止匿名
• 。留言板配置 冷却 秒数 - 设置发言冷却（0-3600）
• 。留言板配置 上限 数字 - 设置每日留言次数上限（1-100）
• 。设置留言板群 群号 - 设置公示群
• 。清空留言板 - 清空所有留言

📦 留言超过90条自动分多条合并转发。每日次数按自然日0点重置。`;
    seal.replyToSender(ctx, msg, helpText);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["留言板帮助"] = cmd_help;

// ========================
// 🎉 启动提示
// ========================
console.log("[留言板系统] 插件已加载，支持注册、匿名、冷却、每日限额");