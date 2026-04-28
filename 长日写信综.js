/**
 * 长日写信综 - 独立的正式信件系统
 * 支持发送正式信件、写信币赏金制度、配置管理等功能
 *
 * 核心功能：
 * - 发送信件：正式、格式化的书信系统
 * - 写信币赏金：根据字数发放写信币奖励
 * - 配置管理：管理员可配置系统参数
 * - 记录查询：查看信件发送记录
 */

const ext = seal.ext.find("我的长日");
if (!ext) {
    console.error("❌ 长日写信综需要依赖「我的长日」插件");
}

// ========================
// 【1】开关和初始化
// ========================

/**
 * 检查写信综是否启用
 */
function isLetterSystemEnabled() {
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    return config.enable_letter_system === true;
}

/**
 * 注册写信币货币
 */
function ensureLetterCoinCurrency() {
    const itemReg = JSON.parse(ext.storageGet("item_registry") || "{}");

    // 检查是否已注册
    const hasLetterCoin = Object.values(itemReg).some(item =>
        item.name === "写信币" || item.code === "CUR_LETTER"
    );

    if (!hasLetterCoin) {
        // 生成新的货币代码
        const currencyKeys = Object.keys(itemReg).filter(k => k.startsWith("CUR_"));
        const maxNum = Math.max(0, ...currencyKeys.map(k => parseInt(k.replace("CUR_", "")) || 0));
        const newCode = `CUR_${String(maxNum + 1).padStart(3, "0")}`;

        itemReg[newCode] = {
            code: newCode,
            name: "写信币",
            desc: "通过发送信件获得的货币，可用于各种消费",
            type: "currency"
        };

        ext.storageSet("item_registry", JSON.stringify(itemReg));
    }
}

// ========================
// 【2】工具函数
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
 * 记录活动
 */
function recordActivity(actType, platform, ctx, endpoint) {
    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce(actType, platform, ctx, endpoint);
    }
}

// ========================
// 【3】启用写信综（管理员命令）
// ========================

let cmd_enable_letter_system = seal.ext.newCmdItemInfo();
cmd_enable_letter_system.name = "启用写信综";
cmd_enable_letter_system.help = `✉️ 【管理员】启用写信综系统
格式：。启用写信综 <开启/关闭>

效果：
- 开启：启用发送信件功能，自动注册写信币货币
- 关闭：禁用发送信件功能

示例：
。启用写信综 开启
。启用写信综 关闭`;

cmd_enable_letter_system.solve = (ctx, msg, cmdArgs) => {
    if (!seal.isAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    const action = cmdArgs.getArgN(1);

    if (!action || (action !== "开启" && action !== "关闭")) {
        return seal.replyToSender(ctx, msg, cmd_enable_letter_system.help);
    }

    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");

    if (action === "开启") {
        config.enable_letter_system = true;
        ext.storageSet("global_feature_toggle", JSON.stringify(config));

        // 自动注册写信币
        ensureLetterCoinCurrency();

        seal.replyToSender(ctx, msg, `✅ 写信综已启用！\n\n✨ 已自动注册货币：写信币\n📮 玩家可以开始使用「发送信件」命令。`);
    } else {
        config.enable_letter_system = false;
        ext.storageSet("global_feature_toggle", JSON.stringify(config));
        seal.replyToSender(ctx, msg, `❌ 写信综已禁用。\n\n玩家无法使用「发送信件」命令。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["启用写信综"] = cmd_enable_letter_system;

// ========================
// 【4】发送信件命令（正式信件）
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
    // 1. 检查写信综是否启用
    if (!isLetterSystemEnabled()) {
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。\n\n管理员需要先执行「启用写信综 开启」。");
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
    const dailyLimit = parseInt(ext.storageGet("letter_daily_limit") || "5");
    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(ext.storageGet("letter_day_counts") || "{}");

    if (!dlCounts[userKey] || dlCounts[userKey].day !== gameDay) {
        dlCounts[userKey] = { day: gameDay, count: 0 };
    }

    const currentCount = dlCounts[userKey].count;
    if (currentCount >= dailyLimit) {
        seal.replyToSender(ctx, msg, `📪 今日已发 ${currentCount}/${dailyLimit} 封信件。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 6. 赏金机制
    const minChars = parseInt(ext.storageGet("letter_min_chars") || "0");
    const rewardPerLetter = parseInt(ext.storageGet("letter_reward") || "0");
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
    ext.storageSet("letter_day_counts", JSON.stringify(dlCounts));

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
// 【5】信件配置（管理员）
// ========================

let cmd_letter_config = seal.ext.newCmdItemInfo();
cmd_letter_config.name = "信件设置";
cmd_letter_config.help = `⚙️ 【管理员】配置发送信件系统
格式：。信件设置 <参数> <值>

参数：
- 日限：每日最多可发送的信件数（默认5）
- 赏金：每封信获得的写信币数（默认0，即禁用赏金）
- 最小字数：获得赏金的最少字数（默认0）

示例：
。信件设置 日限 10
。信件设置 赏金 5
。信件设置 最小字数 10`;

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

    if (param === "日限") {
        ext.storageSet("letter_daily_limit", value);
        modified = true;
    } else if (param === "赏金") {
        ext.storageSet("letter_reward", value);
        modified = true;
    } else if (param === "最小字数") {
        ext.storageSet("letter_min_chars", value);
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
// 【6】查看信件状态
// ========================

let cmd_letter_status = seal.ext.newCmdItemInfo();
cmd_letter_status.name = "信件状态";
cmd_letter_status.help = `📊 查看信件系统状态和个人额度
格式：。信件状态`;

cmd_letter_status.solve = (ctx, msg, cmdArgs) => {
    if (!isLetterSystemEnabled()) {
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const gameDay = ext.storageGet("global_days") || "D0";

    const dailyLimit = parseInt(ext.storageGet("letter_daily_limit") || "5");
    const reward = parseInt(ext.storageGet("letter_reward") || "0");
    const minChars = parseInt(ext.storageGet("letter_min_chars") || "0");

    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(ext.storageGet("letter_day_counts") || "{}");
    const used = dlCounts[userKey]?.count || 0;

    let info = `📊 发送信件系统状态\n\n`;
    info += `📅 游戏日期：${gameDay}\n\n`;
    info += `├ 每日限额：${dailyLimit} 封\n`;
    info += `├ 今日已用：${used} 封\n`;
    info += `├ 剩余额度：${Math.max(0, dailyLimit - used)} 封\n`;
    info += `├ 写信币赏：${reward > 0 ? reward + " 币/封" : "禁用"}\n`;
    if (minChars > 0) info += `└ 最小字数：${minChars}`;

    seal.replyToSender(ctx, msg, info);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["信件状态"] = cmd_letter_status;

// ========================
// 【7】初始化
// ========================

console.log("✅ 长日写信综已加载");
