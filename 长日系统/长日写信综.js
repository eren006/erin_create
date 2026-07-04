// ==UserScript==
// @name         长日写信综
// @author       长日将尽
// @version      1.5.0
// @description  独立的正式信件系统，支持发送信件、写信币赏金、配置管理
// @timestamp    1778742000
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

function sendLetterForward(groupIdRaw, nodes, ctx) {
    const api = getApi();
    if (api) {
        const gid = parseInt(String(groupIdRaw).replace(/[^\d]/g, ""), 10);
        api.ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes }, echo: "letter_forward_" + Date.now() }, ctx, null, null);
        return;
    }
    const main = _mainExt();
    if (!main) return;
    const wsUrl = seal.ext.getStringConfig(main, "ws地址");
    const token = seal.ext.getStringConfig(main, "ws Access token");
    if (!wsUrl) return;
    let url = wsUrl;
    if (token) url += (url.includes("?") ? "&" : "?") + "access_token=" + encodeURIComponent(token);
    const gid = parseInt(String(groupIdRaw).replace(/[^\d]/g, ""), 10);
    const socket = new WebSocket(url);
    socket.onopen = () => {
        socket.send(JSON.stringify({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes }, echo: "letter_forward_" + Date.now() }));
        socket.close();
    };
    socket.onerror = (e) => { console.error("[写信综] 合并转发发送失败", e.message); };
}

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()              { return globalThis.__changriApi || null; }
// 仅供 sendLetterForward WS 回退路径读取插件 config，其余不应使用
function _mainExt()            { return seal.ext.find('changri'); }
function mainStorGet(key)      { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val) { getApi()?.kvSetRaw(key, val); }

// JSON 对象读写：走主插件 kvGet/kvSet（带缓存与损坏容错），JSON key 一律用这两个函数
function mainKvGet(key, def) { const api = getApi(); return api ? api.kvGet(key, def) : def; }
function mainKvSet(key, val) { getApi()?.kvSet(key, val); }
function isUserAdmin(ctx, msg) { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function isArchiveEnabled()    { return getApi()?.isArchiveEnabled() ?? false; }
function postToArchive(endpoint, data) { return getApi()?.postToArchive(endpoint, data); }
function getMainStorageInt(key, def)   { return getApi()?.getStorageInt(key, def) ?? def; }

// 本地扩展对象（用于注册命令）
let ext = seal.ext.find("letter_system");
if (!ext) {
    ext = seal.ext.new("letter_system", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}

// ========================
// 存储辅助函数
// ========================

function isLetterSyncEnabled() {
    return isArchiveEnabled() && isLetterSystemEnabled();
}

function getMainStorage(key, defaultValue) {
    const val = mainStorGet(key);
    if (val === null || val === undefined || val.trim() === "") return defaultValue;
    return val;
}

function setMainStorage(key, value) { mainStorSet(key, value); }

// ========================
// 【1】开关和初始化
// ========================

/**
 * 检查写信综是否启用
 */
function isLetterSystemEnabled() {
    const config = mainKvGet("global_feature_toggle", {});
    return config.enable_direct_letter === true;
}

/**
 * 注册写信币货币
 */
function ensureLetterCoinCurrency() {
    const itemReg = mainKvGet("item_registry", {});

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

        mainKvSet("item_registry", itemReg);
    }
}

/**
 * 注册特殊写信道具
 */
function ensureLetterSpecialItems() {
    const itemReg = mainKvGet("item_registry", {});

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

    mainKvSet("item_registry", itemReg);
}

// ========================
// 【2】工具函数
// ========================

function getPrimaryUid(platform, uid) {
    const api = getApi();
    if (api) return api.getPrimaryUid(platform, uid);
    try {
        const extras = mainKvGet("extra_accounts", {});
        return extras[`${platform}:${uid}`] || uid;
    } catch (e) { console.error("[写信综] getPrimaryUid 解析失败:", e); return uid; }
}

// 新结构：a_private_group[platform][uid] = [roleName, gid]
function getRoleName(ctx, msg) {
    const api = getApi();
    if (api) return api.getRoleName(ctx, msg);
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(`${platform}:`, "");
    const uid = getPrimaryUid(platform, rawUid);
    const groups = mainKvGet("a_private_group", {});
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
    const api = getApi();
    if (api) return api.recordMeetingAndAnnounce(actType, platform, ctx, endpoint);
    // 旧版兼容：插件文件作用域隔离，此探测在旧主插件下永远为 false（历史上即为空操作）
    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce(actType, platform, ctx, endpoint);
    }
}

// ========================
// 【3】注册写信综基础道具（管理员命令）
// ========================
// 写信综开关本身走共享的 global_feature_toggle.enable_direct_letter
// （。设置 功能开关 里的「发送信件」，与 rp 端后台是同一个键位）。
// 本指令只负责补齐货币/道具注册，与开关状态无关，可重复执行。

let cmd_register_letter_items = seal.ext.newCmdItemInfo();
cmd_register_letter_items.name = "注册写信综基础道具";
cmd_register_letter_items.help = `✉️ 【管理员】一键注册写信综所需的货币与道具
格式：。注册写信综基础道具

效果：
- 注册「写信币」货币（已注册则跳过）
- 注册「望远镜」「羽毛笔」两个特殊道具（已注册则跳过）

提示：
写信综功能本身的开关请去「。设置 功能开关」（发送信件）或 rp 端后台切换，
本指令只补齐货币/道具注册，可重复执行。`;

cmd_register_letter_items.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    }

    ensureLetterCoinCurrency();
    ensureLetterSpecialItems();

    seal.replyToSender(ctx, msg, `✅ 写信综基础道具已注册（已存在的自动跳过）！\n\n✨ 货币：写信币\n🔭 道具：望远镜、羽毛笔\n\n如果「发送信件」功能还没开启，记得去「。设置 功能开关」里打开。`);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["注册写信综基础道具"] = cmd_register_letter_items;

// ========================
// 【3.5】写信综指南（管理员设置引导，。前缀命令）
// ========================
// 注意：与下方【8】的玩家版「写信综指南」（不带。号，走 onNotCommandReceived）
// 互不冲突——前者需要命令前缀触发，后者是纯文本关键词触发。

let cmd_letter_admin_guide = seal.ext.newCmdItemInfo();
cmd_letter_admin_guide.name = "写信综指南";
cmd_letter_admin_guide.help = `📖 【管理员】写信综设置引导
格式：。写信综指南`;

cmd_letter_admin_guide.solve = (ctx, msg, cmdArgs) => {
    const lines = [
        "📖 写信综设置引导",
        "",
        "① 开启功能",
        "。设置 功能开关 发送信件 开启",
        "（或在 rp 端后台把「发送信件（写信综）」打开，两边共用同一个开关）",
        "",
        "② 注册基础货币/道具",
        "。注册写信综基础道具",
        "（注册写信币、望远镜、羽毛笔；可重复执行，已注册的会跳过——不执行的话赏金和道具都用不了）",
        "",
        "③ 按需配置参数（。信件设置 参数 值）",
        "日限：每日可发信件数（默认5）",
        "赏金：每封信奖励写信币数（默认0=不发）",
        "最小字数：获得赏金所需的最低字数",
        "发送cd：两封信之间的冷却分钟数",
        "心愿成本：发心愿消耗的写信币数",
        "私约成本：发私约消耗的写信币数",
        "",
        "④ RP存档同步",
        "「启用RP存档传输」和写信综都开启后，信件会自动同步进复盘存档，无需额外设置。",
        "",
        "⑤ 玩家使用",
        "玩家可发送纯文字「写信综指南」（不带。号）查看使用说明，",
        "或直接用「。发送信件」「。信件状态」「。羽毛笔修改」。",
    ];
    seal.replyToSender(ctx, msg, lines.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["写信综指南"] = cmd_letter_admin_guide;

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
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能未启用。\n\n管理员需要先在「。设置 功能开关」开启「发送信件」，并执行「注册写信综基础道具」。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const a_private_group = mainKvGet("a_private_group", {});

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
    const dailyLimit = getMainStorageInt("direct_letter_daily_limit", 5);
    const userKey = `${platform}:${uid}`;
    let dlCounts = mainKvGet("letter_day_counts", {});

    if (!dlCounts[userKey] || dlCounts[userKey].day !== gameDay) {
        dlCounts[userKey] = { day: gameDay, count: 0 };
    }

    const currentCount = dlCounts[userKey].count;
    if (currentCount >= dailyLimit) {
        seal.replyToSender(ctx, msg, `📪 今日已发 ${currentCount}/${dailyLimit} 封信件。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 5.5 冷却检查
    const cdMinutes = getMainStorageInt("direct_letter_cooldown", 0);
    if (cdMinutes > 0) {
        const lastSendTime = dlCounts[userKey].lastSendTime || 0;
        const cdRemain = cdMinutes - Math.floor((Date.now() - lastSendTime) / 60000);
        if (cdRemain > 0) {
            seal.replyToSender(ctx, msg, `⏳ 发信冷却中，还需等待 ${cdRemain} 分钟。`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    // 6. 检查特殊道具效果（望远镜、羽毛笔）
    let telescopeAppliers = []; // 施加望远镜的人列表
    let quillPenApplier = null; // 施加羽毛笔的人
    let effectToHandle = null; // 需要处理的效果

    const telescopeEffects = mainKvGet("letter_telescope_effects", {});
    const quillPenEffects = mainKvGet("letter_quill_pen_effects", {});

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
    const minChars = getMainStorageInt("direct_letter_min_chars", 0);
    const rewardPerLetter = getMainStorageInt("direct_letter_reward", 0);
    const contentLength = content.replace(/\s/g, "").length;
    const meetsMinChars = minChars === 0 || contentLength >= minChars;

    // 通用：发放赏金 + 更新计数 + 回复发信人
    const giveRewardAndReply = () => {
        let rewardGiven = 0;
        let totalCoins = 0;
        if (rewardPerLetter > 0 && meetsMinChars) {
            const roleKey = `${platform}:${uid}`;
            const itemReg = mainKvGet("item_registry", {});
            const coinEntry = Object.entries(itemReg).find(([, v]) => v.name === "写信币");
            if (coinEntry) {
                const [coinCode, coinDef] = coinEntry;
                const invs = mainKvGet("global_inventories", {});
                const inv = invs[roleKey] || [];
                const initialUses = coinDef.maxUses ?? -1;
                const existing = inv.find(e => e.code === coinCode && (e.remainingUses ?? -1) === initialUses);
                if (existing) { existing.count += rewardPerLetter; }
                else { inv.push({ code: coinCode, count: rewardPerLetter, remainingUses: initialUses }); }
                invs[roleKey] = inv;
                mainKvSet("global_inventories", invs);
                totalCoins = inv.filter(e => e.code === coinCode).reduce((sum, e) => sum + e.count, 0);
            }
            rewardGiven = rewardPerLetter;
        }
        dlCounts[userKey].count = currentCount + 1;
        dlCounts[userKey].lastSendTime = Date.now();
        mainKvSet("letter_day_counts", dlCounts);
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
    // 收信人是施加人本人时，羽毛笔不拦截，但仍需消耗效果
    if (effectToHandle?.type === "quill" && receiver === quillPenApplier.applier) {
        quillPenEffects[senderRoleName] = quillPenEffects[senderRoleName].filter(e => e !== quillPenApplier);
        mainKvSet("letter_quill_pen_effects", quillPenEffects);
    } else if (effectToHandle?.type === "quill") {
        let pendingLetters = mainKvGet("letter_pending_quill_pens", {});
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

        mainKvSet("letter_pending_quill_pens", pendingLetters);

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
            seal.replyToSender(ccCtx, ccMsg, `✏️【羽毛笔截获】第 ${idx} 封\n${originalPreview}\n\n使用「。羽毛笔修改 ${idx} 新内容」来修改后发出`);
        }

        // 清除已使用的羽毛笔效果
        quillPenEffects[senderRoleName] = quillPenEffects[senderRoleName].filter(e => e !== quillPenApplier);
        mainKvSet("letter_quill_pen_effects", quillPenEffects);

        // 照常给发信人回执、计数、写信币
        giveRewardAndReply();
        return seal.ext.newCmdExecuteResult(true);
    }

    // 7. 组装信件内容
    let finalLetter = `✉️ ${receiver}，你收到一封信：\n`;
    if (dateTag) finalLetter += `📅 日期：${dateTag}\n`;
    finalLetter += `\n「${content}」\n\n—— ${signature}`;
    if (attachment) finalLetter += `\n\n附件：\n--------------------\n${attachment}`;

    // 8. 投递到收件人私人群（合并转发）
    const targetEntry = getEntryByRoleName(a_private_group, platform, receiver);
    const letterNodes = [
        { type: "node", data: { name: signature, uin: "10001", content: `✉️ 寄给 ${receiver} 的信` } },
        { type: "node", data: { name: signature, uin: "10001", content: finalLetter.replace(/^✉️[^\n]*\n/, "") } }
    ];
    sendLetterForward(targetEntry[1], letterNodes, ctx);

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
        mainKvSet("letter_telescope_effects", telescopeEffects);
    }

    // 9. 存档：实时上报信件到 rp_archive
    if (isLetterSyncEnabled()) {
        postToArchive("/api/event", {
            type:       "direct_letter",
            from_role:  senderRoleName,
            from_qq:    uid,
            to_role:    receiver,
            to_qq:      "",
            content:    content,
            extra_info: {
                signature:  signature,
                date_tag:   dateTag   || "",
                attachment: attachment || ""
            },
            game_day:   gameDay,
            session_id: "",
            timestamp:  Date.now()
        });
    }

    // 10. 发放赏金 + 计数 + 回执
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
- 发送cd：两封信之间的冷却时间（分钟，默认0即无冷却）
- 心愿成本：发送心愿需要消费的写信币数（默认0，即禁用消费）
- 私约成本：发送私约需要消费的写信币数（默认0，即禁用消费）

示例：
。信件设置 日限 10
。信件设置 赏金 5
。信件设置 最小字数 10
。信件设置 发送cd 30
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
    } else if (param === "发送cd") {
        setMainStorage("direct_letter_cooldown", value);
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
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const gameDay = getMainStorage("global_days") || "D0";

    const dailyLimit = getMainStorageInt("direct_letter_daily_limit", 5);
    const reward = getMainStorageInt("direct_letter_reward", 0);
    const minChars = getMainStorageInt("direct_letter_min_chars", 0);
    const cdMinutes = getMainStorageInt("direct_letter_cooldown", 0);

    const userKey = `${platform}:${uid}`;
    let dlCounts = mainKvGet("letter_day_counts", {});
    const used = (dlCounts[userKey]?.day === gameDay ? dlCounts[userKey]?.count : 0) || 0;

    const syncEnabled = isLetterSyncEnabled();
    const hasMinChars = minChars > 0;
    const hasCd = cdMinutes > 0;

    // 计算各行是否是最后一行（用于选 ├ 或 └）
    const tail = (isLast) => isLast ? "└" : "├";

    let info = `📊 发送信件系统状态\n\n`;
    info += `📅 游戏日期：${gameDay}\n\n`;
    info += `├ 每日限额：${dailyLimit} 封\n`;
    info += `├ 今日已用：${used} 封\n`;
    info += `├ 剩余额度：${Math.max(0, dailyLimit - used)} 封\n`;
    info += `${tail(!hasMinChars && !hasCd && !syncEnabled)} 写信币赏：${reward > 0 ? reward + " 币/封" : "禁用"}\n`;
    if (hasMinChars) info += `${tail(!hasCd && !syncEnabled)} 最小字数：${minChars}\n`;
    if (hasCd) {
        const lastSendTime = (dlCounts[userKey]?.day === gameDay ? dlCounts[userKey]?.lastSendTime : 0) || 0;
        const cdRemain = Math.max(0, cdMinutes - Math.floor((Date.now() - lastSendTime) / 60000));
        info += `${tail(!syncEnabled)} 发信冷却：${cdMinutes} 分钟（${cdRemain > 0 ? "剩余 " + cdRemain + " 分钟" : "已就绪"}）\n`;
    }
    if (syncEnabled) info += `└ RP同步：已开启`;

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
    const a_private_group = mainKvGet("a_private_group", {});

    const modifierRoleName = getRoleName(ctx, msg);
    if (!modifierRoleName) {
        seal.replyToSender(ctx, msg, "✨ 请先使用「创建新角色」来认领你的身份。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let pendingLetters = mainKvGet("letter_pending_quill_pens", {});
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
            list += `\n使用「。羽毛笔修改 序号 新内容」来修改后发出`;
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
    if (!targetEntry) {
        seal.replyToSender(ctx, msg, `❌ 投递失败：找不到「${letterData.receiverName}」所在群组。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const modLetterNodes = [
        { type: "node", data: { name: letterData.signature, uin: "10001", content: `✉️ 寄给 ${letterData.receiverName} 的信（经羽毛笔修改）` } },
        { type: "node", data: { name: letterData.signature, uin: "10001", content: finalLetter.replace(/^✉️[^\n]*\n/, "") } }
    ];
    sendLetterForward(targetEntry[1], modLetterNodes, ctx);

    // 同步到 rp_archive（若开关开启）
    if (isLetterSyncEnabled()) {
        postToArchive("/api/event", {
            type:       "direct_letter",
            from_role:  letterData.senderName,
            from_qq:    letterData.userId,
            to_role:    letterData.receiverName,
            to_qq:      "",
            content:    newContent,
            extra_info: {
                signature:      letterData.signature,
                date_tag:       letterData.dateTag   || "",
                attachment:     letterData.attachment || "",
                quill_modified: true
            },
            game_day:   letterData.gameDay,
            session_id: "",
            timestamp:  Date.now()
        });
    }

    myPending.splice(idx - 1, 1);
    if (myPending.length === 0) {
        delete pendingLetters[modifierRoleName];
    } else {
        pendingLetters[modifierRoleName] = myPending;
    }
    mainKvSet("letter_pending_quill_pens", pendingLetters);

    seal.replyToSender(ctx, msg, `✅ 信件已修改并发出！已以「${letterData.senderName}」的名义发给「${letterData.receiverName}」。`);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["羽毛笔修改"] = cmd_quill_pen_modify;

// ========================
// 【8】写信综指南
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();
    if (raw !== "写信综指南") return;

    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, "请在群内使用此指令。");
        return;
    }

    const sections = [
        ["📖 写信综指南", ""],
        ["【私约】",
         "私约 1120-1230 地点 对方角色名[/对方2/...]",
         "例：私约 1400-1500 咖啡厅 张三"],
        ["【修改时间线】（在约会群内使用）",
         "修改时间线 D1 1400-1500",
         "",
         "【拒绝时间线】",
         "拒绝时间线 群号"],
        ["【发送信件】",
         "。发送信件",
         "【收件人】角色名",
         "【内容】信件内容",
         "【日期】日期（选填）",
         "【附件】附加内容（选填）",
         "【署名】落款（选填，默认角色名）"],
        ["【短信】",
         "[署名]短信 收信人 内容",
         "例：短信 张三 你好！",
         "例：李四短信 张三 你好！",
         "",
         "【送礼】",
         "送礼 对方名 礼物内容",
         "送礼 对方名 #编号（图鉴内礼物，可无限送）"],
        ["【道具：望远镜】",
         "效果：施加给目标后，目标发出信件时自动抄录一份给你",
         "使用：。特殊使用 望远镜 角色名",
         "",
         "【道具：羽毛笔】",
         "效果：施加给目标后，目标下一封信将先发给你，由你修改后再发出",
         "使用：。特殊使用 羽毛笔 角色名",
         "查看待修改：。羽毛笔修改",
         "修改并发出：。羽毛笔修改 序号 新内容"],
        ["【背包】",
         "。背包              查看背包全览",
         "。背包 货币/道具/物品  按分类查看",
         "。背包 [分类] [页码]  翻页（如：。背包 道具 2）"],
    ];

    const nodes = sections.map(lines => ({
        type: "node",
        data: { name: "写信综指南", uin: "10001", content: lines.join("\n") }
    }));

    sendLetterForward(msg.groupId, nodes, ctx);
};

// ========================
// 【9】初始化
// ========================

console.log("✅ 长日写信综已加载");
