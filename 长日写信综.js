/**
 * 长日写信综 - 独立的信件系统
 * 支持发送正式信件、混乱寄信、信件撤回、配置管理等功能
 *
 * 核心功能：
 * - 发送信件：正式、格式化的书信系统
 * - 寄信：带混乱效果的非正式信件
 * - 信件撤回：3分钟内可撤回已发送信件
 * - 配置管理：管理员可配置系统参数
 * - 记录查询：查看信件发送记录
 */

const ext = seal.ext.find("我的长日");
if (!ext) {
    console.error("❌ 长日写信综需要依赖「我的长日」插件");
}

// ========================
// 【1】工具函数
// ========================

/**
 * 获取玩家角色名
 */
function getRoleName(ctx, msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const groups = JSON.parse(ext.storageGet("a_private_group") || "{}");
    return Object.entries(groups[platform] || {}).find(([_, v]) => v[0] === uid)?.[0];
}

/**
 * 获取主账号UID
 */
function getPrimaryUid(platform, uid) {
    return uid;
}

/**
 * 记录活动
 */
function recordActivity(actType, platform, ctx, endpoint) {
    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce(actType, platform, ctx, endpoint);
    }
}

// ========================
// 【2】发送信件命令（正式信件）
// ========================

let cmd_send_letter = seal.ext.newCmdItemInfo();
cmd_send_letter.name = "发送信件";
cmd_send_letter.help = `📮 发送正式信件
格式：。发送信件
【收件人】角色名
【内容】信件内容
【日期】日期（选填，显示在信件顶部）
【附件】附加内容（选填，以分隔线显示）
【署名】落款（选填，默认为你的角色名）

示例：
。发送信件
【收件人】小明
【内容】亲爱的小明，今天天气真好...
【日期】2026年4月28日
【署名】小红`;

cmd_send_letter.solve = (ctx, msg, cmdArgs) => {
    // 1. 功能开关检查
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_direct_letter === false) {
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能已关闭。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 2. 身份核验
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 请先使用「创建新角色」来认领你的身份。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 解析标签
    const raw = msg.message.trim();
    const getTag = (tag) => {
        const regex = new RegExp(`【${tag}】([\\s\\S]*?)(?=【|$)`, "i");
        const match = raw.match(regex);
        return match ? match[1].trim() : null;
    };

    const signature = getTag("署名") || senderRoleName;
    const receiver = getTag("收件人") || getTag("发送对象");
    const content = getTag("内容") || "";
    const dateTag = getTag("日期");
    const attachment = getTag("附件");

    // 4. 验证必填项
    if (!receiver) {
        seal.replyToSender(ctx, msg, `⚠️ 请指定【收件人】。\n\n示例：\n。发送信件\n【收件人】小明\n【内容】你好呀`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!a_private_group[platform]?.[receiver]) {
        seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${receiver}」。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!content) {
        seal.replyToSender(ctx, msg, `⚠️ 信件内容不能为空。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 5. 每日限额检查
    const gameDay = ext.storageGet("global_days") || "D0";
    const dailyLimit = parseInt(ext.storageGet("direct_letter_daily_limit") || "5");
    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(ext.storageGet("direct_letter_day_counts") || "{}");

    if (!dlCounts[userKey] || dlCounts[userKey].day !== gameDay) {
        dlCounts[userKey] = { day: gameDay, count: 0 };
    }

    const currentCount = dlCounts[userKey].count;
    if (currentCount >= dailyLimit) {
        seal.replyToSender(ctx, msg, `📪 今日已发 ${currentCount}/${dailyLimit} 封信件。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 6. 赏金机制
    const minChars = parseInt(ext.storageGet("direct_letter_min_chars") || "0");
    const rewardPerLetter = parseInt(ext.storageGet("direct_letter_reward") || "0");
    const contentLength = content.replace(/\s/g, "").length;
    const meetsMinChars = minChars === 0 || contentLength >= minChars;

    // 7. 组装信件内容
    let finalLetter = `✉️ ${receiver}，你收到一封信：\n`;
    if (dateTag) finalLetter += `📅 日期：${dateTag}\n`;
    finalLetter += `\n「${content}」\n\n—— ${signature}`;
    if (attachment) finalLetter += `\n\n附件：\n--------------------\n${attachment}`;

    // 8. 投递到收件人私人群
    const targetEntry = a_private_group[platform][receiver];
    const deliverMsg = seal.newMessage();
    deliverMsg.messageType = "group";
    deliverMsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const deliverCtx = seal.createTempCtx(ctx.endPoint, deliverMsg);
    seal.replyToSender(deliverCtx, deliverMsg, finalLetter);

    // 9. 发放赏金
    let rewardGiven = 0;
    let totalCoins = 0;
    if (rewardPerLetter > 0 && meetsMinChars) {
        let attrs = JSON.parse(ext.storageGet("sys_character_attrs") || "{}");
        if (!attrs[senderRoleName]) attrs[senderRoleName] = {};
        attrs[senderRoleName]["写信币"] = (attrs[senderRoleName]["写信币"] || 0) + rewardPerLetter;
        totalCoins = attrs[senderRoleName]["写信币"];
        ext.storageSet("sys_character_attrs", JSON.stringify(attrs));

        let presets = JSON.parse(ext.storageGet("sys_attr_presets") || "[]");
        if (!presets.includes("写信币")) {
            presets.push("写信币");
            ext.storageSet("sys_attr_presets", JSON.stringify(presets));
        }
        rewardGiven = rewardPerLetter;
    }

    // 10. 更新计数
    dlCounts[userKey].count = currentCount + 1;
    ext.storageSet("direct_letter_day_counts", JSON.stringify(dlCounts));

    // 11. 回复发信人
    let reply = `✉️ 信件已送达「${receiver}」！\n`;
    reply += `🖋️ 落款：${signature}\n`;
    reply += `📅 ${gameDay}（今日剩余：${dailyLimit - (currentCount + 1)}/${dailyLimit}）`;
    if (rewardPerLetter > 0) {
        reply += meetsMinChars ? `\n💰 写信币 +${rewardGiven}（共 ${totalCoins}）` : `\n📝 提示：字数不足 ${minChars}，未获得赏金。`;
    }

    seal.replyToSender(ctx, msg, reply);
    recordActivity("发送信件", platform, ctx, ctx.endPoint);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["发送信件"] = cmd_send_letter;

// ========================
// 【3】寄信命令（混乱信件）
// ========================

let cmd_chaos_letter = seal.ext.newCmdItemInfo();
cmd_chaos_letter.name = "寄信";
cmd_chaos_letter.help = `🕊️ 通过鸽子寄送混乱信件（可能被篡改、送错、署名错误等）
格式：。寄信 <收件人> <内容>

特性：
- 内容可能被侵蚀、丢失或被涂黑
- 署名可能被篡改
- 信件可能送错收件人
- 3分钟内可发「撤回」取消
- 有概率在公开群显示

冷却：60秒 / 每日限额：5封

示例：
。寄信 小明 亲爱的小明，我想对你说...`;

cmd_chaos_letter.solve = (ctx, msg, cmdArgs) => {
    // 1. 功能开关
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_chaos_letter === false) {
        seal.replyToSender(ctx, msg, "🕊️ 寄信功能已关闭。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const senderRoleName = getRoleName(ctx, msg);
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 2. 身份验证
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 请先使用「创建新角色」来认领你的身份。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 解析参数
    const raw = msg.message.trim();
    const parts = raw.substring(2).trim().split(/\s+/);
    if (parts.length < 2) {
        seal.replyToSender(ctx, msg, "⚠️ 格式错误！\n\n正确格式：。寄信 <收件人> <内容>\n\n示例：。寄信 小明 你好啊");
        return seal.ext.newCmdExecuteResult(true);
    }

    const toname = parts[0];
    const contentOriginal = parts.slice(1).join(" ");

    if (!a_private_group[platform]?.[toname]) {
        seal.replyToSender(ctx, msg, `❌ 未找到收信人：${toname}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 4. 冷却检查
    const cooldownKey = `chaos_letter_cooldown_${platform}:${uid}`;
    const lastSent = parseInt(ext.storageGet(cooldownKey) || "0");
    const now = Date.now();
    const mailCooldownMin = parseInt(ext.storageGet("mailCooldown") || "1");

    if (now - lastSent < mailCooldownMin * 60 * 1000) {
        const rem = Math.ceil((mailCooldownMin * 60 * 1000 - (now - lastSent)) / 60000);
        return seal.replyToSender(ctx, msg, `⏳ 鸽子正在休息，请 ${rem} 分钟后再试`);
    }

    // 5. 每日限额
    const gameDay = ext.storageGet("global_days") || "D0";
    const globalChaosCounts = JSON.parse(ext.storageGet("global_chaos_letter_counts") || "{}");
    const userKey = `${platform}:${uid}`;
    let userRec = globalChaosCounts[userKey] || { day: gameDay, count: 0 };

    if (userRec.day !== gameDay) userRec = { day: gameDay, count: 0 };

    let chaosConfig = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
    const defaultConfig = {
        misdelivery: 0, blackoutText: 0, loseContent: 0, antonymReplace: 0,
        reverseOrder: 0, mistakenSignature: 0, poeticSignature: 0, dailyLimit: 5, publicChance: 50
    };
    chaosConfig = { ...defaultConfig, ...chaosConfig };

    if (userRec.count >= chaosConfig.dailyLimit) {
        return seal.replyToSender(ctx, msg, `🕊️ 今日寄信次数已达上限(${chaosConfig.dailyLimit})`);
    }

    // 6. 内容侵蚀处理
    let content = contentOriginal;
    const chaosCharPool = ["梦", "影", "幻", "虚", "无", "断", "零", "终", "念", "尘", "迹", "雾", "嘘", "寂"];

    if (Math.random() * 100 < chaosConfig.antonymReplace) {
        let textArray = content.split('');
        const replaceCount = Math.floor(textArray.length * (0.15 + Math.random() * 0.1));
        for (let i = 0; i < replaceCount; i++) {
            textArray[Math.floor(Math.random() * textArray.length)] = chaosCharPool[Math.floor(Math.random() * chaosCharPool.length)];
        }
        content = textArray.join('');
    }

    if (Math.random() * 100 < chaosConfig.loseContent && content.length > 5) {
        content = content.slice(0, Math.floor(content.length * 0.7)) + "……";
    }

    if (Math.random() * 100 < chaosConfig.blackoutText) {
        const blackout = ["◼︎", "█", "■", "▮"];
        content = content.split('').map(c => Math.random() < 0.2 ? blackout[Math.floor(Math.random() * blackout.length)] : c).join('');
    }

    // 7. 署名处理
    let finalSignature = `落款：${senderRoleName}`;
    if (Math.random() * 100 < chaosConfig.mistakenSignature) {
        const others = Object.keys(a_private_group[platform]).filter(n => n !== senderRoleName);
        if (others.length) finalSignature = `落款：${others[Math.floor(Math.random() * others.length)]}`;
    }

    // 8. 投递处理
    let trueRecipient = toname;
    if (Math.random() * 100 < chaosConfig.misdelivery) {
        const others = Object.keys(a_private_group[platform]).filter(n => n !== toname);
        if (others.length) trueRecipient = others[Math.floor(Math.random() * others.length)];
    }

    const targetEntry = a_private_group[platform][trueRecipient];
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    const targetQQ = targetEntry[0];
    const notice = `[CQ:at,qq=${targetQQ}]\n📱 ${toname}，你收到一条短信：\n「${content}」\n\n${finalSignature}`;
    seal.replyToSender(newctx, newmsg, notice);

    // 9. 更新数据
    ext.storageSet(cooldownKey, now.toString());
    userRec.count += 1;
    globalChaosCounts[userKey] = userRec;
    ext.storageSet("global_chaos_letter_counts", JSON.stringify(globalChaosCounts));

    // 10. 记录可撤回
    const pendingRecall = JSON.parse(ext.storageGet("pending_recall") || "{}");
    pendingRecall[userKey] = {
        type: "短信",
        toname,
        trueRecipient,
        recipientGroupId: targetEntry[1],
        sentAt: now,
        senderName: senderRoleName,
    };
    ext.storageSet("pending_recall", JSON.stringify(pendingRecall));

    seal.replyToSender(ctx, msg, `🕊️ 信件已由鸽子衔往 ${toname} 处。今日已发 ${userRec.count}/${chaosConfig.dailyLimit}（3分钟内可发「撤回」取消）。`);

    // 11. 公开逻辑
    const letterPublicEnabled = JSON.parse(ext.storageGet("letter_public_send") || "false");
    if (letterPublicEnabled && (Math.random() * 100 <= chaosConfig.publicChance)) {
        const adminGid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
        if (adminGid) {
            const pMsg = seal.newMessage();
            pMsg.messageType = "group";
            pMsg.groupId = `${platform}-Group:${adminGid}`;
            const pCtx = seal.createTempCtx(ctx.endPoint, pMsg);
            seal.replyToSender(pCtx, pMsg, `💌 公开信件：\n「${senderRoleName}」→「${toname}」\n内容：「${content}」`);
        }
    }

    recordActivity("寄信", platform, ctx, ctx.endPoint);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["寄信"] = cmd_chaos_letter;

// ========================
// 【4】信件撤回
// ========================

let cmd_recall_letter = seal.ext.newCmdItemInfo();
cmd_recall_letter.name = "撤回";
cmd_recall_letter.help = `↩️ 撤回3分钟内发送的信件或短信（仅发送者可用）
格式：。撤回

限制：
- 仅限3分钟内发送的消息
- 仅有发送者可撤回
- 超时后无法撤回`;

cmd_recall_letter.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const userKey = `${platform}:${uid}`;
    const senderRoleName = getRoleName(ctx, msg);

    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 请先使用「创建新角色」来认领你的身份。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const pendingRecall = JSON.parse(ext.storageGet("pending_recall") || "{}");
    const record = pendingRecall[userKey];

    if (!record) {
        seal.replyToSender(ctx, msg, "❌ 没有可撤回的消息。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查时间限制
    const now = Date.now();
    if (now - record.sentAt > 3 * 60 * 1000) {
        delete pendingRecall[userKey];
        ext.storageSet("pending_recall", JSON.stringify(pendingRecall));
        seal.replyToSender(ctx, msg, "⏰ 消息已超时（3分钟），无法撤回。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 删除记录
    delete pendingRecall[userKey];
    ext.storageSet("pending_recall", JSON.stringify(pendingRecall));

    seal.replyToSender(ctx, msg, `↩️ ${record.type}已撤回。`);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["撤回"] = cmd_recall_letter;

// ========================
// 【5】信件配置（管理员）
// ========================

let cmd_letter_config = seal.ext.newCmdItemInfo();
cmd_letter_config.name = "信件设置";
cmd_letter_config.help = `⚙️ 【管理员】配置信件系统
格式：。信件设置 <参数> <值>

【发送信件参数】：
- 直信日限：每日最多可发送的正式信件数（默认5）
- 写信币赏：每封信获得的写信币数（默认0，即禁用赏金）
- 最小字数：获得赏金的最少字数（默认0）

【寄信参数】：
- 寄信日限：每日最多可寄信数（默认5）
- 寄信冷却：寄信间隔时间（分钟，默认1）
- 错送率：信件被送错的概率（0-100%，默认0）
- 篡改率：内容被篡改的概率（0-100%，默认0）
- 签名错：署名被篡改的概率（0-100%，默认0）
- 公开率：信件在公开群显示的概率（0-100%，默认50）

示例：
。信件设置 直信日限 10
。信件设置 写信币赏 10
。信件设置 寄信日限 5`;

cmd_letter_config.solve = (ctx, msg, cmdArgs) => {
    if (!seal.isAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    const param = cmdArgs.getArgN(1);
    const value = cmdArgs.getArgN(2);

    if (!param || !value) {
        return seal.replyToSender(ctx, msg, cmd_letter_config.help);
    }

    let modified = false;

    // 发送信件配置
    if (param === "直信日限") {
        ext.storageSet("direct_letter_daily_limit", value);
        modified = true;
    } else if (param === "写信币赏") {
        ext.storageSet("direct_letter_reward", value);
        modified = true;
    } else if (param === "最小字数") {
        ext.storageSet("direct_letter_min_chars", value);
        modified = true;
    }
    // 寄信配置
    else if (param === "寄信日限") {
        let cfg = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        cfg.dailyLimit = parseInt(value);
        ext.storageSet("chaos_letter_config", JSON.stringify(cfg));
        modified = true;
    } else if (param === "寄信冷却") {
        ext.storageSet("mailCooldown", value);
        modified = true;
    } else if (param === "错送率") {
        let cfg = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        cfg.misdelivery = parseInt(value);
        ext.storageSet("chaos_letter_config", JSON.stringify(cfg));
        modified = true;
    } else if (param === "篡改率") {
        let cfg = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        cfg.antonymReplace = parseInt(value);
        ext.storageSet("chaos_letter_config", JSON.stringify(cfg));
        modified = true;
    } else if (param === "签名错") {
        let cfg = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        cfg.mistakenSignature = parseInt(value);
        ext.storageSet("chaos_letter_config", JSON.stringify(cfg));
        modified = true;
    } else if (param === "公开率") {
        let cfg = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        cfg.publicChance = parseInt(value);
        ext.storageSet("chaos_letter_config", JSON.stringify(cfg));
        modified = true;
    }

    if (modified) {
        seal.replyToSender(ctx, msg, `✅ 已设置 ${param} = ${value}`);
    } else {
        seal.replyToSender(ctx, msg, "⚠️ 未知参数。\n" + cmd_letter_config.help);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["信件设置"] = cmd_letter_config;

// ========================
// 【6】查看配置
// ========================

let cmd_letter_status = seal.ext.newCmdItemInfo();
cmd_letter_status.name = "信件状态";
cmd_letter_status.help = `📊 查看信件系统配置和个人额度
格式：。信件状态`;

cmd_letter_status.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const gameDay = ext.storageGet("global_days") || "D0";

    // 发送信件配置
    const dlLimit = parseInt(ext.storageGet("direct_letter_daily_limit") || "5");
    const reward = parseInt(ext.storageGet("direct_letter_reward") || "0");
    const minChars = parseInt(ext.storageGet("direct_letter_min_chars") || "0");

    // 寄信配置
    let chaosConfig = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
    const chaosLimit = chaosConfig.dailyLimit || 5;
    const cooldown = parseInt(ext.storageGet("mailCooldown") || "1");

    // 个人额度
    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(ext.storageGet("direct_letter_day_counts") || "{}");
    const dlUsed = dlCounts[userKey]?.count || 0;

    let globalChaosCounts = JSON.parse(ext.storageGet("global_chaos_letter_counts") || "{}");
    const chaosUsed = globalChaosCounts[userKey]?.count || 0;

    let info = `📊 信件系统状态\n\n`;
    info += `📅 游戏日期：${gameDay}\n\n`;

    info += `【发送信件】\n`;
    info += `├ 每日限额：${dlLimit} 封\n`;
    info += `├ 今日已用：${dlUsed} 封\n`;
    info += `├ 写信币赏：${reward > 0 ? reward + " 币/封" : "禁用"}\n`;
    if (minChars > 0) info += `├ 最小字数：${minChars}\n`;
    info += `└ 剩余额度：${Math.max(0, dlLimit - dlUsed)} 封\n\n`;

    info += `【寄信】\n`;
    info += `├ 每日限额：${chaosLimit} 封\n`;
    info += `├ 今日已用：${chaosUsed} 封\n`;
    info += `├ 冷却时间：${cooldown} 分钟\n`;
    info += `├ 错送率：${chaosConfig.misdelivery || 0}%\n`;
    info += `├ 篡改率：${chaosConfig.antonymReplace || 0}%\n`;
    info += `├ 签名错率：${chaosConfig.mistakenSignature || 0}%\n`;
    info += `├ 公开率：${chaosConfig.publicChance || 50}%\n`;
    info += `└ 剩余额度：${Math.max(0, chaosLimit - chaosUsed)} 封`;

    seal.replyToSender(ctx, msg, info);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["信件状态"] = cmd_letter_status;

// ========================
// 【7】记录查询
// ========================

let cmd_letter_record = seal.ext.newCmdItemInfo();
cmd_letter_record.name = "信件记录";
cmd_letter_record.help = `📋 查看今日信件发送记录
格式：。信件记录

显示信息：
- 正式信件（发送信件）
- 混乱信件（寄信）
- 已发送数和剩余额度`;

cmd_letter_record.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const gameDay = ext.storageGet("global_days") || "D0";
    const userKey = `${platform}:${uid}`;

    const dlLimit = parseInt(ext.storageGet("direct_letter_daily_limit") || "5");
    let dlCounts = JSON.parse(ext.storageGet("direct_letter_day_counts") || "{}");
    const dlUsed = dlCounts[userKey]?.count || 0;

    let chaosConfig = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
    const chaosLimit = chaosConfig.dailyLimit || 5;
    let globalChaosCounts = JSON.parse(ext.storageGet("global_chaos_letter_counts") || "{}");
    const chaosUsed = globalChaosCounts[userKey]?.count || 0;

    let info = `📋 ${gameDay} 信件记录\n\n`;
    info += `📮 发送信件：${dlUsed}/${dlLimit}（剩余 ${Math.max(0, dlLimit - dlUsed)} 封）\n`;
    info += `🕊️ 寄信：${chaosUsed}/${chaosLimit}（剩余 ${Math.max(0, chaosLimit - chaosUsed)} 封）`;

    seal.replyToSender(ctx, msg, info);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["信件记录"] = cmd_letter_record;

console.log("✅ 长日写信综已加载");
