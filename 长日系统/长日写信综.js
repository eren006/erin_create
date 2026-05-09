// ==UserScript==
// @name         长日写信综
// @author       长日将尽
// @version      1.0.0
// @description  独立的正式信件系统，支持发送信件、写信币赏金、配置管理
// @timestamp    1745568000
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%86%99%E4%BF%A1%E7%BB%BC.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%86%99%E4%BF%A1%E7%BB%BC.js
// ==/UserScript==

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

// ========================
// 核心依赖：获取主插件 changri
// ========================

function getMainExt() {
    const main = seal.ext.find('changri');
    if (!main) {
        console.error("❌ 写信综错误：未找到主插件 changri，请检查主插件是否已加载");
        return null;
    }
    return main;
}

// 本地扩展对象（用于注册命令）
let ext = seal.ext.find("letter_system");
if (!ext) {
    ext = seal.ext.new("letter_system", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}

// ========================
// 存储辅助函数
// ========================

function getMainStorage(key, defaultValue) {
    const main = getMainExt();
    if (!main) return defaultValue;
    const val = main.storageGet(key);
    if (val === null || val === undefined || val.trim() === "") return defaultValue;
    return val;
}

function setMainStorage(key, value) {
    const main = getMainExt();
    if (!main) return;
    main.storageSet(key, value);
}

// ========================
// 权限判断
// ========================

function isUserAdmin(ctx, msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const main = getMainExt();
    const a_adminList = JSON.parse((main ? main.storageGet("a_adminList") : null) || "{}");
    return ctx.privilegeLevel === 100 || (a_adminList[platform] && a_adminList[platform].includes(uid));
}

// ========================
// 【1】开关和初始化
// ========================

/**
 * 检查写信综是否启用
 */
function isLetterSystemEnabled() {
    const config = JSON.parse(getMainStorage("global_feature_toggle", "{}"));
    return config.enable_direct_letter === true;
}

/**
 * 注册写信币货币
 */
function ensureLetterCoinCurrency() {
    const itemReg = JSON.parse(getMainStorage("item_registry") || "{}");

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

        setMainStorage("item_registry", JSON.stringify(itemReg));
    }
}

/**
 * 注册特殊写信道具
 */
function ensureLetterSpecialItems() {
    const itemReg = JSON.parse(getMainStorage("item_registry") || "{}");

    // 望远镜
    if (!itemReg["SPEC_003"]) {
        itemReg["SPEC_003"] = {
            code: "SPEC_003",
            name: "望远镜",
            desc: "施加给目标，当其发出信件时自动抄录一份给使用者",
            type: "item",
            special: true
        };
    }

    // 羽毛笔
    if (!itemReg["SPEC_004"]) {
        itemReg["SPEC_004"] = {
            code: "SPEC_004",
            name: "羽毛笔",
            desc: "施加给目标，其下一封信将先发送给使用者进行修改后再发出",
            type: "item",
            special: true
        };
    }

    setMainStorage("item_registry", JSON.stringify(itemReg));
}

// ========================
// 【2】工具函数
// ========================

function getPrimaryUid(platform, uid) {
    const main = getMainExt();
    if (!main) return uid;
    try {
        const extras = JSON.parse(main.storageGet("extra_accounts") || "{}");
        return extras[`${platform}:${uid}`] || uid;
    } catch (e) { return uid; }
}

// 新结构：a_private_group[platform][uid] = [roleName, gid]
function getRoleName(ctx, msg) {
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(`${platform}:`, "");
    const uid = getPrimaryUid(platform, rawUid);
    const groups = JSON.parse(getMainStorage("a_private_group") || "{}");
    return groups[platform]?.[uid]?.[0] || null;
}

// 按 roleName 反查 entry（返回 [roleName, gid] 或 null）
function getEntryByRoleName(apg, platform, roleName) {
    return Object.values(apg[platform] || {}).find(v => v[0] === roleName) || null;
}

/**
 * 记录活动
 */
function recordActivity(actType, platform, ctx, endpoint) {
    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce(actType, platform, ctx, endpoint);
    }
}

/**
 * 处理超时的待审信件（3小时未修改则发送原文）
 */
function processExpiredQuillPens() {
    const TIMEOUT_MS = 3 * 60 * 60 * 1000; // 3小时
    const now = Date.now();
    let pendingLetters = JSON.parse(getMainStorage("letter_pending_quill_pens") || "{}");
    const a_private_group = JSON.parse(getMainStorage("a_private_group") || "{}");

    for (const [modifierRoleName, letters] of Object.entries(pendingLetters)) {
        for (let i = letters.length - 1; i >= 0; i--) {
            const letterData = letters[i];
            if (now - letterData.applyTime > TIMEOUT_MS) {
                // 超时，发送原文
                try {
                    const platform = letterData.platform;
                    const targetEntry = getEntryByRoleName(a_private_group, platform, letterData.receiverName);
                    if (targetEntry) {
                        let originalLetter = `✉️ ${letterData.receiverName}，你收到一封信：\n`;
                        if (letterData.dateTag) originalLetter += `📅 日期：${letterData.dateTag}\n`;
                        originalLetter += `\n「${letterData.content}」\n\n—— ${letterData.signature}`;
                        if (letterData.attachment) originalLetter += `\n\n附件：\n--------------------\n${letterData.attachment}`;
                        originalLetter += `\n\n⏰ (此信件已超时3小时，自动发送原文)`;

                        const msg = seal.newMessage();
                        msg.messageType = "group";
                        msg.groupId = `${platform}-Group:${targetEntry[1]}`;
                        const msgCtx = seal.createTempCtx({endPoint: {cmdPrefix: "。"}}, msg);
                        seal.replyToSender(msgCtx, msg, originalLetter);
                    }
                } catch (e) {
                    console.error("发送超时待审信件失败:", e);
                }

                // 删除该待审信件
                letters.splice(i, 1);
            }
        }
    }

    setMainStorage("letter_pending_quill_pens", JSON.stringify(pendingLetters));
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
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    const action = cmdArgs.getArgN(1);

    if (!action || (action !== "开启" && action !== "关闭")) {
        return seal.replyToSender(ctx, msg, cmd_enable_letter_system.help);
    }

    const config = JSON.parse(getMainStorage("global_feature_toggle") || "{}");

    if (action === "开启") {
        config.enable_direct_letter = true;
        setMainStorage("global_feature_toggle", JSON.stringify(config));

        // 自动注册写信币
        ensureLetterCoinCurrency();

        // 自动注册特殊道具
        ensureLetterSpecialItems();

        seal.replyToSender(ctx, msg, `✅ 写信综已启用！\n\n✨ 已自动注册货币：写信币\n🔭 已自动注册道具：望远镜、羽毛笔\n📮 玩家可以开始使用「发送信件」命令。`);
    } else {
        config.enable_direct_letter = false;
        setMainStorage("global_feature_toggle", JSON.stringify(config));
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
    // 检查并处理超时的待审信件
    processExpiredQuillPens();

    // 1. 检查写信综是否启用
    if (!isLetterSystemEnabled()) {
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。\n\n管理员需要先执行「启用写信综 开启」。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(getMainStorage("a_private_group") || "{}");

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
        seal.replyToSender(ctx, msg, `⚠️ 请指定【收件人】。\n\n示例：\n。发送信件\n【收件人】小明\n【内容】亲爱的小明，今天天气真好...\n【日期】2026年4月28日\n【附件】随信附上一份礼物\n【署名】小红`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!getEntryByRoleName(a_private_group, platform, receiver)) {
        seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${receiver}」。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!content) {
        seal.replyToSender(ctx, msg, `⚠️ 信件内容不能为空。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 5. 每日限额检查
    const gameDay = getMainStorage("global_days") || "D0";
    const dailyLimit = parseInt(getMainStorage("direct_letter_daily_limit") || "5");
    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(getMainStorage("letter_day_counts") || "{}");

    if (!dlCounts[userKey] || dlCounts[userKey].day !== gameDay) {
        dlCounts[userKey] = { day: gameDay, count: 0 };
    }

    const currentCount = dlCounts[userKey].count;
    if (currentCount >= dailyLimit) {
        seal.replyToSender(ctx, msg, `📪 今日已发 ${currentCount}/${dailyLimit} 封信件。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 6. 检查特殊道具效果（望远镜、羽毛笔）
    let telescopeAppliers = []; // 施加望远镜的人列表
    let quillPenApplier = null; // 施加羽毛笔的人
    let effectToHandle = null; // 需要处理的效果

    const telescopeEffects = JSON.parse(getMainStorage("letter_telescope_effects") || "{}");
    const quillPenEffects = JSON.parse(getMainStorage("letter_quill_pen_effects") || "{}");

    if (telescopeEffects[senderRoleName]) {
        telescopeAppliers = telescopeEffects[senderRoleName]
            .filter(e => e.itemCode === "SPEC_003")
            .sort((a, b) => a.applyTime - b.applyTime);
    }

    if (quillPenEffects[senderRoleName]) {
        const quillPens = quillPenEffects[senderRoleName]
            .filter(e => e.itemCode === "SPEC_004")
            .sort((a, b) => a.applyTime - b.applyTime);
        if (quillPens.length > 0) {
            quillPenApplier = quillPens[0];
        }
    }

    // 确定优先级（谁先施加谁优先）
    if (quillPenApplier && telescopeAppliers.length > 0) {
        if (quillPenApplier.applyTime < telescopeAppliers[0].applyTime) {
            effectToHandle = { type: "quill", data: quillPenApplier };
        } else {
            effectToHandle = { type: "telescope", data: telescopeAppliers[0] };
        }
    } else if (quillPenApplier) {
        effectToHandle = { type: "quill", data: quillPenApplier };
    } else if (telescopeAppliers.length > 0) {
        effectToHandle = { type: "telescope", data: telescopeAppliers[0] };
    }

    // 6. 赏金机制（提前计算，羽毛笔路径也需要）
    const minChars = parseInt(getMainStorage("direct_letter_min_chars") || "0");
    const rewardPerLetter = parseInt(getMainStorage("direct_letter_reward") || "0");
    const contentLength = content.replace(/\s/g, "").length;
    const meetsMinChars = minChars === 0 || contentLength >= minChars;

    // 通用：发放赏金 + 更新计数 + 回复发信人
    const giveRewardAndReply = () => {
        let rewardGiven = 0;
        let totalCoins = 0;
        if (rewardPerLetter > 0 && meetsMinChars) {
            const roleKey = `${platform}:${uid}`;
            const itemReg = JSON.parse(getMainStorage("item_registry") || "{}");
            const coinEntry = Object.entries(itemReg).find(([, v]) => v.name === "写信币");
            if (coinEntry) {
                const [coinCode, coinDef] = coinEntry;
                const invs = JSON.parse(getMainStorage("global_inventories") || "{}");
                const inv = invs[roleKey] || [];
                const initialUses = coinDef.maxUses ?? -1;
                const existing = inv.find(e => e.code === coinCode && (e.remainingUses ?? -1) === initialUses);
                if (existing) { existing.count += rewardPerLetter; }
                else { inv.push({ code: coinCode, count: rewardPerLetter, remainingUses: initialUses }); }
                invs[roleKey] = inv;
                setMainStorage("global_inventories", JSON.stringify(invs));
                totalCoins = inv.filter(e => e.code === coinCode).reduce((sum, e) => sum + e.count, 0);
            }
            rewardGiven = rewardPerLetter;
        }
        dlCounts[userKey].count = currentCount + 1;
        setMainStorage("letter_day_counts", JSON.stringify(dlCounts));
        let reply = `✉️ 信件已送达「${receiver}」！\n`;
        reply += `🖋️ 落款：${signature}\n`;
        reply += `📅 ${gameDay}（今日剩余：${dailyLimit - (currentCount + 1)}/${dailyLimit}）`;
        if (rewardPerLetter > 0) {
            reply += meetsMinChars ? `\n💰 写信币 +${rewardGiven}（共 ${totalCoins}）` : `\n📝 提示：字数不足 ${minChars}，未获得赏金。`;
        }
        seal.replyToSender(ctx, msg, reply);
        recordActivity("发送信件", platform, ctx, ctx.endPoint);
    };

    // 处理羽毛笔效果（优先级最高时）
    if (effectToHandle?.type === "quill" && receiver !== quillPenApplier.applier) {
        let pendingLetters = JSON.parse(getMainStorage("letter_pending_quill_pens") || "{}");
        if (!pendingLetters[quillPenApplier.applier]) {
            pendingLetters[quillPenApplier.applier] = [];
        }

        pendingLetters[quillPenApplier.applier].push({
            senderName: senderRoleName,
            receiverName: receiver,
            content: content,
            dateTag: dateTag,
            attachment: attachment,
            signature: signature,
            gameDay: gameDay,
            platform: platform,
            applyTime: Date.now(),
            userId: uid
        });

        setMainStorage("letter_pending_quill_pens", JSON.stringify(pendingLetters));

        // CC 原始信件给施加人
        const applierEntry = getEntryByRoleName(a_private_group, platform, quillPenApplier.applier);
        if (applierEntry) {
            const idx = pendingLetters[quillPenApplier.applier].length;
            let originalPreview = `✉️ ${receiver}，你收到一封信：\n`;
            if (dateTag) originalPreview += `📅 日期：${dateTag}\n`;
            originalPreview += `\n「${content}」\n\n—— ${signature}`;
            if (attachment) originalPreview += `\n\n附件：\n--------------------\n${attachment}`;
            const ccMsg = seal.newMessage();
            ccMsg.messageType = "group";
            ccMsg.groupId = `${platform}-Group:${applierEntry[1]}`;
            const ccCtx = seal.createTempCtx(ctx.endPoint, ccMsg);
            seal.replyToSender(ccCtx, ccMsg, `✏️【羽毛笔截获】第 ${idx} 封\n${originalPreview}\n\n使用「羽毛笔修改 ${idx} 新内容」来修改后发出`);
        }

        // 清除已使用的羽毛笔效果
        quillPenEffects[senderRoleName] = quillPenEffects[senderRoleName].filter(e => e !== quillPenApplier);
        setMainStorage("letter_quill_pen_effects", JSON.stringify(quillPenEffects));

        // 照常给发信人回执、计数、写信币
        giveRewardAndReply();
        return seal.ext.newCmdExecuteResult(true);
    }

    // 7. 组装信件内容
    let finalLetter = `✉️ ${receiver}，你收到一封信：\n`;
    if (dateTag) finalLetter += `📅 日期：${dateTag}\n`;
    finalLetter += `\n「${content}」\n\n—— ${signature}`;
    if (attachment) finalLetter += `\n\n附件：\n--------------------\n${attachment}`;

    // 8. 投递到收件人私人群
    const targetEntry = getEntryByRoleName(a_private_group, platform, receiver);
    const deliverMsg = seal.newMessage();
    deliverMsg.messageType = "group";
    deliverMsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const deliverCtx = seal.createTempCtx(ctx.endPoint, deliverMsg);
    seal.replyToSender(deliverCtx, deliverMsg, finalLetter);

    // 8.5 处理望远镜效果：抄录一份给施加人
    if (effectToHandle?.type === "telescope") {
        const telescopeApplier = effectToHandle.data;
        const applierEntry = getEntryByRoleName(a_private_group, platform, telescopeApplier.applier);
        if (applierEntry) {
            const copyMsg = seal.newMessage();
            copyMsg.messageType = "group";
            copyMsg.groupId = `${platform}-Group:${applierEntry[1]}`;
            const copyCtx = seal.createTempCtx(ctx.endPoint, copyMsg);
            seal.replyToSender(copyCtx, copyMsg, `🔭【望远镜抄录】\n${finalLetter}`);
        }
        telescopeEffects[senderRoleName] = telescopeEffects[senderRoleName].filter(e => e !== telescopeApplier);
        setMainStorage("letter_telescope_effects", JSON.stringify(telescopeEffects));
    }

    // 9. 发放赏金 + 计数 + 回执
    giveRewardAndReply();

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
- 心愿成本：发送心愿需要消费的写信币数（默认0，即禁用消费）
- 私约成本：发送私约需要消费的写信币数（默认0，即禁用消费）

示例：
。信件设置 日限 10
。信件设置 赏金 5
。信件设置 最小字数 10
。信件设置 心愿成本 3
。信件设置 私约成本 5`;

cmd_letter_config.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    const param = cmdArgs.getArgN(1);
    const value = cmdArgs.getArgN(2);

    if (!param || !value) {
        return seal.replyToSender(ctx, msg, cmd_letter_config.help);
    }

    let modified = false;

    if (param === "日限") {
        setMainStorage("direct_letter_daily_limit", value);
        modified = true;
    } else if (param === "赏金") {
        setMainStorage("direct_letter_reward", value);
        modified = true;
    } else if (param === "最小字数") {
        setMainStorage("direct_letter_min_chars", value);
        modified = true;
    } else if (param === "心愿成本") {
        setMainStorage("wish_coin_cost", value);
        modified = true;
    } else if (param === "私约成本") {
        setMainStorage("appointment_coin_cost", value);
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
    const gameDay = getMainStorage("global_days") || "D0";

    const dailyLimit = parseInt(getMainStorage("direct_letter_daily_limit") || "5");
    const reward = parseInt(getMainStorage("direct_letter_reward") || "0");
    const minChars = parseInt(getMainStorage("direct_letter_min_chars") || "0");

    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(getMainStorage("letter_day_counts") || "{}");
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
// ========================
// 【7】羽毛笔修改命令
// ========================

let cmd_quill_pen_modify = seal.ext.newCmdItemInfo();
cmd_quill_pen_modify.name = "羽毛笔修改";
cmd_quill_pen_modify.help = `✏️ 查看或修改截获的信件
格式：
  羽毛笔修改          —— 查看待修改清单
  羽毛笔修改 序号 内容  —— 修改指定序号的信件后发出`;

cmd_quill_pen_modify.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const a_private_group = JSON.parse(getMainStorage("a_private_group") || "{}");

    const modifierRoleName = getRoleName(ctx, msg);
    if (!modifierRoleName) {
        seal.replyToSender(ctx, msg, "✨ 请先使用「创建新角色」来认领你的身份。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let pendingLetters = JSON.parse(getMainStorage("letter_pending_quill_pens") || "{}");
    const myPending = pendingLetters[modifierRoleName] || [];

    const idxStr = cmdArgs.getArgN(1);

    // 无参数：显示清单
    if (!idxStr) {
        if (myPending.length === 0) {
            seal.replyToSender(ctx, msg, "✏️ 没有待修改的信件。");
        } else {
            let list = `✏️ 待修改信件（共 ${myPending.length} 封）：\n`;
            myPending.forEach((l, i) => {
                const preview = l.content.length > 20 ? l.content.slice(0, 20) + "..." : l.content;
                list += `${i + 1}. ${l.senderName} → ${l.receiverName}：${preview}\n`;
            });
            list += `\n使用「羽毛笔修改 序号 新内容」来修改后发出`;
            seal.replyToSender(ctx, msg, list);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    const idx = parseInt(idxStr);
    if (isNaN(idx) || idx < 1 || idx > myPending.length) {
        seal.replyToSender(ctx, msg, `❌ 序号无效，请输入 1-${myPending.length} 之间的数字。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 提取序号后的全部内容作为新正文
    const rawAfterCmd = msg.message.replace(/^[\s\S]*?羽毛笔修改\s*/, "").trim();
    const spacePos = rawAfterCmd.search(/\s/);
    const newContent = spacePos === -1 ? "" : rawAfterCmd.slice(spacePos + 1).trim();

    if (!newContent) {
        seal.replyToSender(ctx, msg, "❌ 请提供修改后的内容。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const letterData = myPending[idx - 1];

    let finalLetter = `✉️ ${letterData.receiverName}，你收到一封信：\n`;
    if (letterData.dateTag) finalLetter += `📅 日期：${letterData.dateTag}\n`;
    finalLetter += `\n「${newContent}」\n\n—— ${letterData.signature}`;
    if (letterData.attachment) finalLetter += `\n\n附件：\n--------------------\n${letterData.attachment}`;

    const targetEntry = getEntryByRoleName(a_private_group, platform, letterData.receiverName);
    const deliverMsg = seal.newMessage();
    deliverMsg.messageType = "group";
    deliverMsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const deliverCtx = seal.createTempCtx(ctx.endPoint, deliverMsg);
    seal.replyToSender(deliverCtx, deliverMsg, finalLetter);

    myPending.splice(idx - 1, 1);
    if (myPending.length === 0) {
        delete pendingLetters[modifierRoleName];
    } else {
        pendingLetters[modifierRoleName] = myPending;
    }
    setMainStorage("letter_pending_quill_pens", JSON.stringify(pendingLetters));

    seal.replyToSender(ctx, msg, `✅ 信件已修改并发出！已以「${letterData.senderName}」的名义发给「${letterData.receiverName}」。`);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["羽毛笔修改"] = cmd_quill_pen_modify;

// ========================
// 【9】初始化
// ========================

console.log("✅ 长日写信综已加载");
