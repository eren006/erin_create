// ==UserScript==
// @name         长日设置
// @author       长日将尽
// @version      1.1.0
// @description  独立的设置控制台（基础、互动、信件、公告）及天数系统、统计报告。所有数据统一存储在主插件 changriV1 中。
// @timestamp    1743292800
// @license      MIT
// ==/UserScript==

/**
 * 说明：
 * 1. 核心依赖：通过 seal.ext.find('changriV1') 寻找主插件，读写其存储中的配置数据。
 * 2. 功能模块：统一设置面板（基础、互动、信件、公告）、天数管理、自动天数推进、统计报告。
 * 3. 数据存储：所有配置项、计数、池子数据均存储在主插件 changriV1 的存储空间中。
 * 4. 权限检查：复用主插件的管理员列表（a_adminList）和 ctx.privilegeLevel。
 */

let ext = seal.ext.find('setting_system');
if (!ext) {
    ext = seal.ext.new("setting_system", "长日将尽", "1.1.0");
    seal.ext.register(ext);
}

// ========================
// 核心依赖：读取主插件存储
// ========================

function getMainExt() {
    const main = seal.ext.find('changriV1');
    if (!main) {
        console.error("❌ 设置系统错误：未找到主插件 changriV1，请检查主插件是否已加载");
        return null;
    }
    return main;
}

/**
 * 权限检查（依赖 changriV1 的管理员列表）
 */
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

// 辅助：发送纯文本到指定群（不依赖 ws，使用 seal 内置方法）
function sendTextToGroup(platform, gid, text) {
    try {
        const target = `${platform}-Group:${gid.toString().replace(/\D/g, "")}`;
        const m = seal.newMessage();
        m.messageType = "group";
        m.groupId = target;
        const eps = seal.getEndPoints();
        if (eps?.length) {
            seal.replyToSender(seal.createTempCtx(eps[0], m), m, text);
        }
    } catch (e) {
        console.error("发送群消息失败:", e);
    }
}

// ========================
// 通用解析引擎（用于设置模板）
// ========================

function handleApply(ctx, msg, rawMessage, paramHandler) {
    const lines = rawMessage.split('\n');
    const success = [];
    const error = [];
    for (let i = 1; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) continue;
        const match = line.match(/^【([^】]+)】\s*(.+)$/);
        if (!match) continue;
        const result = paramHandler(match[1].trim(), match[2].trim());
        if (result.success) success.push(result.message);
        else error.push(result.message);
    }
    let reply = `✅ 处理完成（成功 ${success.length} 项）\n` + success.join('\n');
    if (error.length > 0) reply += `\n\n❌ 失败项：\n` + error.join('\n');
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
}

// ========================
// 辅助函数：读写主插件配置
// ========================

function getMainStorage(key, defaultValue) {
    const main = getMainExt();
    if (!main) return defaultValue;
    const val = main.storageGet(key);
    // 增加 val.trim() 检查，防止解析空字符串导致的 EOF 错误
    if (val === null || val === undefined || val.trim() === "") return defaultValue;
    return val;
}

function setMainStorage(key, value) {
    const main = getMainExt();
    if (!main) return;
    main.storageSet(key, value);
}

// 目击配置
function getSightingConfig() {
    const defaultConfig = { enabled: true, send_to_all: true, max_reports_per_day: 5, include_ended_meetings: false, time_overlap_threshold: 0.3 };
    try {
        return { ...defaultConfig, ...JSON.parse(getMainStorage("sighting_system_config", "{}")) };
    } catch (e) { return defaultConfig; }
}

function setSightingConfig(config) {
    setMainStorage("sighting_system_config", JSON.stringify(config));
}

// 地点系统配置
function getPlaceSystemConfig() {
    const defaultConfig = { enabled: true, require_key_by_default: false };
    try {
        return { ...defaultConfig, ...JSON.parse(getMainStorage("place_system_config", "{}")) };
    } catch (e) { return defaultConfig; }
}

function setPlaceSystemConfig(config) {
    setMainStorage("place_system_config", JSON.stringify(config));
}

// ========================
// 基础设置模块
// ========================
function showBasicSettings(ctx, msg) {
    // 增加完整默认值
    let feature = {
        enable_wechat: true,
        enable_general_gift: true,
        enable_wish_system: true,
        enable_general_appointment: true
    };
    try {
        const raw = getMainStorage("global_feature_toggle", "{}");
        feature = { ...feature, ...JSON.parse(raw) };
    } catch (e) { feature = {}; }

    const results = [
        ".设置 基础设置",
        `【恋综名】${getMainStorage("love_show_name", "\"未设置\"").replace(/"/g, '')}`,
        `【微信】${feature.enable_wechat !== false ? '开启' : '关闭'}`,
        `【礼物】${feature.enable_general_gift !== false ? '开启' : '关闭'}`,
        `【心愿】${feature.enable_wish_system !== false ? '开启' : '关闭'}`,
        `【发起邀约】${feature.enable_general_appointment !== false ? '开启' : '关闭'}`,
        `【关系线系统】${getMainStorage("relationship_system_enabled", "true") === "true" ? '开启' : '关闭'}`,
        `【关系线上限】${getMainStorage("max_relationships_per_user", "5")}`,
        `【点歌群】${getMainStorage("song_group_id", "未设置").replace(/"/g, '')}`,
        `【后台群】${getMainStorage("background_group_id", "未设置").replace(/"/g, '')}`,
        `【公告群】${getMainStorage("adminAnnounceGroupId", "未设置").replace(/"/g, '')}`,
        `【水群】${getMainStorage("water_group_id", "未设置").replace(/"/g, '')}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyBasicParam(name, val) {
    const featureMap = { '微信': 'enable_wechat', '礼物': 'enable_general_gift', '心愿': 'enable_wish_system', '发起邀约': 'enable_general_appointment' };
    if (featureMap[name]) {
        let cfg = JSON.parse(getMainStorage("global_feature_toggle", "{}"));
        cfg[featureMap[name]] = (val === '开启');
        setMainStorage("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【${name}】已${val}` };
    }
    if (name === '关系线系统') {
        setMainStorage("relationship_system_enabled", JSON.stringify(val === '开启'));
        return { success: true, message: `【${name}】已${val}` };
    }
    if (name === '恋综名') {
        setMainStorage("love_show_name", JSON.stringify(val));
        return { success: true, message: `【${name}】已设为 ${val}` };
    }
    if (name === '关系线上限') {
        setMainStorage("max_relationships_per_user", val);
        return { success: true, message: `【${name}】已设为 ${val}` };
    }
    const groups = { '点歌群': 'song_group_id', '后台群': 'background_group_id', '公告群': 'adminAnnounceGroupId', '水群': 'water_group_id' };
    if (groups[name]) {
        setMainStorage(groups[name], JSON.stringify(val === '未设置' ? null : val));
        return { success: true, message: `【${name}】已同步` };
    }
    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 互动设置模块
// ========================
function showInteractionSettings(ctx, msg) {
    let duration = { phone: 29, private: 59 };
    try {
        duration = { ...duration, ...JSON.parse(getMainStorage("appointment_duration_config", "{}")) };
    } catch (e) {}

    const results = [
        ".设置 互动设置",
        `【地点系统】${getPlaceSystemConfig().enabled ? '开启' : '关闭'}`,
        `【电话最小时长】${duration.phone}`,
        `【私密最小时长】${duration.private}`,
        `【寄信冷却时间】${getMainStorage("mailCooldown", "60")}`,
        `【送礼冷却时间】${getMainStorage("giftCooldown", "30")}`,
        `【送礼模式】${getMainStorage("giftMode", "0")}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyInteractionParam(name, val) {
    // 地点系统
    if (name === '地点系统') {
        let c = getPlaceSystemConfig();
        c.enabled = (val === '开启');
        setPlaceSystemConfig(c);
        return { success: true, message: `地点系统已${val}` };
    }

    // 邀约时长
    const durationMap = { '电话最小时长': 'phone', '私密最小时长': 'private' };
    if (durationMap[name]) {
        let d = JSON.parse(getMainStorage("appointment_duration_config", "{}"));
        d[durationMap[name]] = parseInt(val);
        setMainStorage("appointment_duration_config", JSON.stringify(d));
        return { success: true, message: `【${name}】已更新` };
    }

    // 其他存储键
    const storageKeys = {
        '寄信冷却时间': 'mailCooldown',
        '送礼冷却时间': 'giftCooldown',
        '送礼模式': 'giftMode'
    };
    if (storageKeys[name]) {
        setMainStorage(storageKeys[name], val);
        return { success: true, message: `【${name}】已设为 ${val}` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 信件设置模块
// ========================

/**
 * 信件设置模块 - 完整加固版
 */
function showLetterSettings(ctx, msg) {
    // 1. 初始化默认值，确保即使解析失败也有数据可用
    let feature = {
        enable_chaos_letter: true,
        enable_lovemail: true,
    };
    
    let chaos = {
        dailyLimit: 5,
        misdelivery: 0,
        blackoutText: 0,
        loseContent: 0,
        antonymReplace: 0,
        reverseOrder: 0,
        mistakenSignature: 0,
        poeticSignature: 0,
        publicChance: 50
    };

    // 2. 尝试解析主插件存储的功能开关
    try {
        const rawFeature = getMainStorage("global_feature_toggle", "{}");
        const parsedFeature = JSON.parse(rawFeature);
        // 合并解析结果
        feature = { ...feature, ...parsedFeature };
    } catch (e) {
        console.error("解析 global_feature_toggle 失败:", e);
    }

    // 3. 尝试解析主插件存储的混乱信件配置
    try {
        const rawChaos = getMainStorage("chaos_letter_config", "{}");
        const parsedChaos = JSON.parse(rawChaos);
        // 合并解析结果
        chaos = { ...chaos, ...parsedChaos };
    } catch (e) {
        console.error("解析 chaos_letter_config 失败:", e);
    }

    // 5. 组装展示模板
    const results = [
        ".设置 信件设置",
        `【寄信】${feature.enable_chaos_letter !== false ? '开启' : '关闭'}`,
        `【寄信每日上限】${chaos.dailyLimit}`,
        `【寄信允许自定义名字】${getMainStorage("allow_custom_letter_sign", "false") === "true" ? '开启' : '关闭'}`,
        `【寄信混乱送错】${chaos.misdelivery}`,
        `【寄信混乱涂改】${chaos.blackoutText}`,
        `【寄信混乱丢失】${chaos.loseContent}`,
        `【寄信混乱反义】${chaos.antonymReplace}`,
        `【寄信混乱乱序】${chaos.reverseOrder}`,
        `【寄信混乱混淆】${chaos.mistakenSignature}`,
        `【寄信混乱诗意】${chaos.poeticSignature}`,
    ];

    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyLetterParam(name, val) {
    if (name === '寄信') {
        let cfg = JSON.parse(getMainStorage("global_feature_toggle", "{}"));
        cfg.enable_chaos_letter = (val === '开启');
        setMainStorage("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【寄信】已${val}` };
    }

    if (name === '寄信允许自定义名字') {
        const isOpen = (val === '开启');
        setMainStorage("allow_custom_letter_sign", isOpen ? "true" : "false");
        return { success: true, message: `【${name}】已${val}` };
    }

    const chaosMap = {
        '寄信每日上限': 'dailyLimit',
        '寄信混乱送错': 'misdelivery',
        '寄信混乱涂改': 'blackoutText',
        '寄信混乱丢失': 'loseContent',
        '寄信混乱反义': 'antonymReplace',
        '寄信混乱乱序': 'reverseOrder',
        '寄信混乱混淆': 'mistakenSignature',
        '寄信混乱诗意': 'poeticSignature'
    };
    if (chaosMap[name]) {
        let c = JSON.parse(getMainStorage("chaos_letter_config", "{}"));
        c[chaosMap[name]] = parseInt(val);
        setMainStorage("chaos_letter_config", JSON.stringify(c));
        return { success: true, message: `【${name}】已更新为 ${val}` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 发送信件设置模块
// ========================
function showDirectLetterSettings(ctx, msg) {
    const feature = (() => {
        try { return JSON.parse(getMainStorage("global_feature_toggle", "{}")); } catch (e) { return {}; }
    })();
    const results = [
        ".设置 发送信件设置",
        `【发送信件】${feature.enable_direct_letter !== false ? '开启' : '关闭'}`,
        `【发送信件每日上限】${getMainStorage("direct_letter_daily_limit", "5")}`,
        `【发送信件最低字数】${getMainStorage("direct_letter_min_chars", "0")}`,
        `【发送信件赏金】${getMainStorage("direct_letter_reward", "0")}`,
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyDirectLetterParam(name, val) {
    if (name === '发送信件') {
        let cfg = JSON.parse(getMainStorage("global_feature_toggle", "{}"));
        cfg.enable_direct_letter = (val === '开启');
        setMainStorage("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【发送信件】已${val}` };
    }
    const storageKeys = {
        '发送信件每日上限': 'direct_letter_daily_limit',
        '发送信件最低字数': 'direct_letter_min_chars',
        '发送信件赏金': 'direct_letter_reward'
    };
    if (storageKeys[name]) {
        setMainStorage(storageKeys[name], val);
        return { success: true, message: `【${name}】已更新为 ${val}` };
    }
    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 公告设置模块
// ========================

function showPublicSettings(ctx, msg) {
    let chaos = { publicChance: 50 };
    try {
        chaos = { ...chaos, ...JSON.parse(getMainStorage("chaos_letter_config", "{}")) };
    } catch (e) {}

    // 辅助函数：安全解析布尔值
    const getBool = (key) => {
        try {
            const val = getMainStorage(key, "false");
            return val === "true" || JSON.parse(val) === true;
        } catch (e) { return false; }
    };

    const results = [
        ".设置 公告设置",
        `【心愿公开提醒】${getBool("wish_public_send") ? '开启' : '关闭'}`,
        `【送礼公开发送】${getBool("gift_public_send") ? '开启' : '关闭'}`,
        `【寄信公开发送】${getBool("letter_public_send") ? '开启' : '关闭'}`,
        `【寄信公开概率】${chaos.publicChance}`,
        `【礼物公开概率】${getMainStorage("giftPublicChance", "50")}`,
        `【每日礼物上限】${getMainStorage("giftDailyLimit", "100")}`,
        `【公告触发频率】${getMainStorage("announceFrequency", "5")}`,
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyPublicParam(name, val) {
    const map = {
        '心愿公开提醒': 'wish_public_send',
        '送礼公开发送': 'gift_public_send',
        '寄信公开发送': 'letter_public_send',
    };
    if (map[name]) {
        setMainStorage(map[name], JSON.stringify(val === '开启'));
        return { success: true, message: `【${name}】已${val}` };
    }

    if (name === '寄信公开概率') {
        let c = JSON.parse(getMainStorage("chaos_letter_config", "{}"));
        c.publicChance = parseInt(val);
        setMainStorage("chaos_letter_config", JSON.stringify(c));
        return { success: true, message: `【${name}】已设为 ${val}%` };
    }

    const storageKeys = {
        '礼物公开概率': 'giftPublicChance',
        '每日礼物上限': 'giftDailyLimit',
        '公告触发频率': 'announceFrequency'
    };
    if (storageKeys[name]) {
        setMainStorage(storageKeys[name], val);
        return { success: true, message: `【${name}】已保存为 ${val}` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 心动信设置模块
// ========================
function showLovemailSettings(ctx, msg) {
    const feature = (() => {
        try { return JSON.parse(getMainStorage("global_feature_toggle", "{}")); } catch (e) { return {}; }
    })();
    const deliveryTime = getMainStorage("lovemail_delivery_time", "22:00").replace(/"/g, '');
    const expose = getMainStorage("lovemail_expose", "false") === "true";
    const exposeChance = getMainStorage("lovemail_expose_chance", "10");

    const results = [
        ".设置 心动信设置",
        `【心动信】${feature.enable_lovemail !== false ? '开启' : '关闭'}`,
        `【心动信送达时间】${deliveryTime}`,
        `【心动信曝光】${expose ? '开启' : '关闭'}`,
        `【心动信曝光概率】${exposeChance}`,
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyLovemailParam(name, val) {
    if (name === '心动信') {
        let cfg = JSON.parse(getMainStorage("global_feature_toggle", "{}"));
        cfg.enable_lovemail = (val === '开启');
        setMainStorage("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【心动信】已${val}` };
    }
    if (name === '心动信送达时间') {
        setMainStorage("lovemail_delivery_time", JSON.stringify(val));
        return { success: true, message: `心动信送达时间已设为 ${val}` };
    }
    if (name === '心动信曝光') {
        setMainStorage("lovemail_expose", val === '开启' ? "true" : "false");
        return { success: true, message: `【心动信曝光】已${val}` };
    }
    if (name === '心动信曝光概率') {
        const n = parseInt(val);
        if (isNaN(n) || n < 0 || n > 100) return { success: false, message: "概率请填 0-100 的整数" };
        setMainStorage("lovemail_expose_chance", val);
        return { success: true, message: `【心动信曝光概率】已设为 ${val}%` };
    }
    return { success: false, message: `未知参数：${name}` };
}

function showItemSettings(ctx, msg) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const trackerRate = parseInt(main.storageGet("item_tracker_success_rate") || "70");
    const drawLimit = parseInt(main.storageGet("item_daily_draw_limit") || "2");
    const showPartner = main.storageGet("item_tracker_show_partner") !== "false";
    const timeRestrict = main.storageGet("item_tracker_time_restrict") !== "false";
    const itemPoolMode = getMainStorage("item_pool_mode", "自由池");

    const results = [
        ".设置 道具设置",
        `【追踪器成功率】${trackerRate}`,
        `【每日抽取上限】${drawLimit}`,
        `【追踪器显示伙伴】${showPartner ? "开启" : "关闭"}`,
        `【追踪器时间限制】${timeRestrict ? "开启" : "关闭"}`,
        `【物品池模式】${itemPoolMode}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

// ========================
// 商城设置模块
// ========================
function showShopSettings(ctx, msg) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const currencyAttr = main.storageGet("shop_currency_attr") || "金币";
    const refreshHours = parseInt(main.storageGet("shop_refresh_hours") || "24");
    const shopMode = main.storageGet("shop_mode") || "抽卡";

    const results = [
        ".设置 商城设置",
        `【商城模式】${shopMode}`,
        `  抽卡 = 每人随机一件礼物，自动加图鉴，可无限赠送`,
        `  商城 = 全部在售商品，需购买加背包，库存有限（默认10件）`,
        `  ⚠️ 切换模式会自动转换现有数据（图鉴↔背包）`,
        `【商城货币属性】${currencyAttr}（商城模式购买时扣除）`,
        `【商城刷新间隔】${refreshHours}h（抽卡模式下个人刷新间隔）`,
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyShopParam(name, val) {
    const main = getMainExt();
    if (!main) return { success: false, message: "无法连接主插件" };

    if (name === '商城货币属性') {
        if (!val || !val.trim()) return { success: false, message: "【商城货币属性】不能为空" };
        const attrName = val.trim();
        const presets = JSON.parse(main.storageGet("sys_attr_presets") || "[]");
        if (!presets.includes(attrName)) {
            return { success: false, message: `❌ 属性「${attrName}」尚未创建。\n请先让骰主执行：我创建属性 ${attrName}` };
        }
        main.storageSet("shop_currency_attr", attrName);
        return { success: true, message: `【商城货币属性】已设为「${attrName}」` };
    }
    if (name === '商城刷新间隔') {
        const hours = parseInt(val);
        if (isNaN(hours) || hours < 1) return { success: false, message: "【商城刷新间隔】必须是 ≥1 的整数（单位：小时）" };
        main.storageSet("shop_refresh_hours", hours.toString());
        main.storageSet("shop_personal_display", "{}");
        return { success: true, message: `【商城刷新间隔】已设为 ${hours} 小时（所有人下次进入商城生效）` };
    }
    if (name === '商城模式') {
        const newMode = val === "商城" ? "商城" : "抽卡";
        const oldMode = main.storageGet("shop_mode") || "抽卡";
        if (newMode === oldMode) return { success: false, message: `【商城模式】当前已是「${newMode}」` };

        // 数据转换
        const invs = JSON.parse(main.storageGet("global_inventories") || "{}");
        const sightings = JSON.parse(main.storageGet("gift_sightings") || "{}");
        const presetGifts = JSON.parse(main.storageGet("preset_gifts") || "{}");
        const privGroup = JSON.parse(main.storageGet("a_private_group") || "{}");

        if (newMode === "商城") {
            // 抽卡→商城：图鉴×3 转入背包
            for (const [platform, roles] of Object.entries(privGroup)) {
                for (const [roleName, info] of Object.entries(roles)) {
                    const uid = Array.isArray(info) ? info[0] : info;
                    const userKey = `${platform}:${uid}`;
                    const unlocked = sightings[userKey]?.unlocked_gifts || [];
                    if (!unlocked.length) continue;
                    const roleKey = `${platform}:${roleName}`;
                    if (!invs[roleKey]) invs[roleKey] = [];
                    for (const giftId of unlocked) {
                        const gift = presetGifts[giftId];
                        if (!gift) continue;
                        const ei = invs[roleKey].findIndex(i => i.giftId === giftId && i.source === "礼物商城");
                        if (ei !== -1) { invs[roleKey][ei].count = (invs[roleKey][ei].count || 1) + 3; }
                        else { invs[roleKey].push({ name: gift.name, desc: gift.content, used: false, type: "礼物", giftId, count: 3, createTime: Date.now(), source: "礼物商城" }); }
                    }
                    if (sightings[userKey]) sightings[userKey].unlocked_gifts = [];
                }
            }
        } else {
            // 商城→抽卡：背包商城礼物转入图鉴并移除
            for (const [platform, roles] of Object.entries(privGroup)) {
                for (const [roleName, info] of Object.entries(roles)) {
                    const uid = Array.isArray(info) ? info[0] : info;
                    const userKey = `${platform}:${uid}`;
                    const roleKey = `${platform}:${roleName}`;
                    if (!invs[roleKey]) continue;
                    const shopItems = invs[roleKey].filter(i => i.giftId && i.source === "礼物商城");
                    if (!sightings[userKey]) sightings[userKey] = { unlocked_gifts: [] };
                    for (const item of shopItems) {
                        if (!sightings[userKey].unlocked_gifts.includes(item.giftId)) {
                            sightings[userKey].unlocked_gifts.push(item.giftId);
                        }
                    }
                    invs[roleKey] = invs[roleKey].filter(i => !(i.giftId && i.source === "礼物商城"));
                }
            }
        }

        main.storageSet("global_inventories", JSON.stringify(invs));
        main.storageSet("gift_sightings", JSON.stringify(sightings));
        main.storageSet("shop_mode", newMode);
        main.storageSet("shop_personal_display", "{}");
        const note = newMode === "商城" ? "图鉴礼物已×3转入各玩家背包" : "背包商城礼物已转入各玩家图鉴";
        return { success: true, message: `【商城模式】已切换为「${newMode}」\n${note}` };
    }
    return { success: false, message: `未知参数：${name}` };
}

function showAuctionSettings(ctx, msg) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");
    const displayGroup = main.storageGet("auction_display_group") || "未设置";
    const allowAnon = main.storageGet("auction_allow_anon") !== "false" ? "开启" : "关闭";
    const broadcast = main.storageGet("auction_broadcast") !== "false" ? "开启" : "关闭";
    const showTop = main.storageGet("auction_show_top_bidder") !== "false" ? "开启" : "关闭";
    const currency = main.storageGet("auction_currency") || "金币";
    seal.replyToSender(ctx, msg, [
        ".设置 拍卖设置",
        `【拍卖展示群】${displayGroup}`,
        `  拍卖结果与出价播报发往该群`,
        `【允许匿名出价】${allowAnon}`,
        `【出价播报】${broadcast}`,
        `  每次出价后是否向展示群广播`,
        `【展示最高出价者】${showTop}`,
        `  查看拍卖/播报中是否显示出价者角色名`,
        `【拍卖货币】${currency}`,
        `  出价时验证该属性余额，结束后自动扣除`,
    ].join('\n'));
}

function applyAuctionParam(name, val) {
    const main = getMainExt();
    if (!main) return { success: false, message: "无法连接主插件" };
    if (name === '拍卖展示群') {
        const gid = val.trim();
        if (!/^\d+$/.test(gid)) return { success: false, message: "【拍卖展示群】请填写纯数字群号" };
        main.storageSet("auction_display_group", gid);
        return { success: true, message: `【拍卖展示群】已设为 ${gid}` };
    }
    if (name === '允许匿名出价') {
        const v = val.trim() === "开启";
        main.storageSet("auction_allow_anon", v ? "true" : "false");
        return { success: true, message: `【允许匿名出价】已${v ? "开启" : "关闭"}` };
    }
    if (name === '出价播报') {
        const v = val.trim() === "开启";
        main.storageSet("auction_broadcast", v ? "true" : "false");
        return { success: true, message: `【出价播报】已${v ? "开启" : "关闭"}` };
    }
    if (name === '展示最高出价者') {
        const v = val.trim() === "开启";
        main.storageSet("auction_show_top_bidder", v ? "true" : "false");
        return { success: true, message: `【展示最高出价者】已${v ? "开启" : "关闭"}` };
    }
    if (name === '拍卖货币') {
        const attr = val.trim();
        if (!attr) return { success: false, message: "【拍卖货币】不能为空" };
        const presets = JSON.parse(main.storageGet("sys_attr_presets") || "[]");
        if (!presets.includes(attr)) return { success: false, message: `❌ 属性「${attr}」尚未创建。\n请先执行：我创建属性 ${attr}` };
        main.storageSet("auction_currency", attr);
        return { success: true, message: `【拍卖货币】已设为「${attr}」` };
    }
    return { success: false, message: `未知参数：${name}` };
}

function applyItemParam(name, val) {
    const main = getMainExt();
    if (!main) return { success: false, message: "无法连接主插件" };

    if (name === '追踪器成功率') {
        const num = parseInt(val);
        if (isNaN(num) || num < 0 || num > 100) {
            return { success: false, message: "【追踪器成功率】必须是 0-100 之间的整数" };
        }
        main.storageSet("item_tracker_success_rate", num.toString());
        return { success: true, message: `【追踪器成功率】已设为 ${num}%` };
    }
    if (name === '每日抽取上限') {
        const num = parseInt(val);
        if (isNaN(num) || num < 1) {
            return { success: false, message: "【每日抽取上限】必须是 ≥1 的整数" };
        }
        main.storageSet("item_daily_draw_limit", num.toString());
        return { success: true, message: `【每日抽取上限】已设为 ${num} 次` };
    }
    if (name === '追踪器显示伙伴') {
        const enabled = (val === '开启' || val === '开' || val === 'true');
        main.storageSet("item_tracker_show_partner", enabled ? "true" : "false");
        return { success: true, message: `【追踪器显示伙伴】已${enabled ? "开启" : "关闭"}` };
    }
    if (name === '追踪器时间限制') {
        const enabled = (val === '开启' || val === '开' || val === 'true');
        main.storageSet("item_tracker_time_restrict", enabled ? "true" : "false");
        return { success: true, message: `【追踪器时间限制】已${enabled ? "开启" : "关闭"}` };
    }
    if (name === '物品池模式') {
        if (val !== '自由池' && val !== '固定池') {
            return { success: false, message: "【物品池模式】必须是「自由池」或「固定池」" };
        }
        setMainStorage("item_pool_mode", val);
        return { success: true, message: `【物品池模式】已切换为 ${val}` };
    }
    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 群组管理设置模块
// ========================

function showGroupSettings(ctx, msg) {
    const sighting = getSightingConfig();
    const enableJoin = getMainStorage("enable_join_existing_appointment", "true") !== "false";
    
    // 安全解析布尔值
    const getBool = (key, def) => {
        try {
            const val = getMainStorage(key, String(def));
            return val === "true" || JSON.parse(val) === true;
        } catch (e) { return def; }
    };

    const autoMerge = getBool("auto_merge_duplicate_private", false);
    const requireFupan = getBool("require_fupan_before_end", true);
    const expireHours = getMainStorage("group_expire_hours", "48");

    const results = [
        ".设置 群组设置",
        `【小群过期时间】${expireHours}`,
        `【允许加入已有私约】${enableJoin ? "开启" : "关闭"}`,
        `【自动合并重合私约】${autoMerge ? "开启" : "关闭"}`,
        `【复盘强制结束】${requireFupan ? "开启" : "关闭"}`,
        `【目击报告】${sighting.enabled ? '开启' : '关闭'}`,
        `【目击每日上限】${sighting.max_reports_per_day}`,
        `【时间重叠阈值】${Math.round(sighting.time_overlap_threshold * 100)}%`,
        `【目击报告方式】${sighting.send_to_all ? '双向通知' : '单向通知'}`,
        `【包含已结束】${sighting.include_ended_meetings ? '是' : '否'}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyGroupParam(name, val) {
    // 目击报告相关
    if (['目击报告', '目击报告方式', '目击每日上限', '时间重叠阈值', '包含已结束'].includes(name)) {
        let c = getSightingConfig();
        if (name === '目击报告') c.enabled = (val === '开启');
        if (name === '目击报告方式') c.send_to_all = (val === '双向通知');
        if (name === '目击每日上限') c.max_reports_per_day = parseInt(val);
        if (name === '时间重叠阈值') c.time_overlap_threshold = parseInt(val) / 100;
        if (name === '包含已结束') c.include_ended_meetings = (val === '是');
        setSightingConfig(c);
        return { success: true, message: `【${name}】已更新` };
    }

    if (name === '允许加入已有私约') {
        setMainStorage("enable_join_existing_appointment", val === '开启' ? "true" : "false");
        return { success: true, message: `【允许加入已有私约】已${val}` };
    }

    if (name === '自动合并重合私约') {
        setMainStorage("auto_merge_duplicate_private", JSON.stringify(val === '开启'));
        return { success: true, message: `【自动合并重合私约】已${val}` };
    }

    if (name === '复盘强制结束') {
        setMainStorage("require_fupan_before_end", JSON.stringify(val === '开启'));
        return { success: true, message: `【复盘强制结束】已${val}` };
    }

    if (name === '小群过期时间') {
        setMainStorage("group_expire_hours", val);
        return { success: true, message: `【小群过期时间】已设为 ${val} 小时` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 设置指令主体
// ========================

// ========================
// 懒加载默认值（首次使用设置时初始化缺失的关键配置）
// ========================
function ensureDefaults(main) {
    const defaults = {
        "global_feature_toggle": JSON.stringify({ enable_general_letter: true, enable_general_gift: true, enable_general_appointment: true, enable_chaos_letter: true, enable_secret_letter: true, enable_wish_system: true, enable_lovemail: true }),
        "chaos_letter_config": JSON.stringify({ misdelivery: 0, blackoutText: 0, loseContent: 0, antonymReplace: 0, reverseOrder: 0, mistakenSignature: 0, poeticSignature: 0, dailyLimit: 5, publicChance: 50 }),
        "sighting_system_config": JSON.stringify({ enabled: true, send_to_all: true, max_reports_per_day: 5, include_ended_meetings: false, time_overlap_threshold: 0.3 }),
        "place_system_config": JSON.stringify({ enabled: true, require_key_by_default: false }),
        "appointment_duration_config": JSON.stringify({ phone: 29, private: 59 }),
        "monitor_settings": JSON.stringify({ enabled: true, min_words_phone: 20, min_words_private: 150, min_words_wish: 150, min_words_official: 150, timeout_phone: 3600000, timeout_private: 10800000, timeout_wish: 10800000, timeout_official: 10800000, remind_interval_phone: 5400000, remind_interval_private: 10800000, remind_interval_wish: 10800000, remind_interval_official: 10800000 }),
        "group_expire_hours": "48",
        "relationship_system_enabled": "true",
        "max_relationships_per_user": "5",
        "lovemail_default_limit": "3",
        "lovemail_day_limits": "{}",
        "auto_day_reset_enabled": "false",
        "item_pool_mode": "自由池",
        "shop_currency_attr": "金币",
        "shop_refresh_hours": "24",
        "shop_mode": "抽卡",
    };
    for (const [key, val] of Object.entries(defaults)) {
        const existing = main.storageGet(key);
        if (!existing || existing.trim() === "") main.storageSet(key, val);
    }
}

let cmd_settings = seal.ext.newCmdItemInfo();
cmd_settings.name = '设置';
cmd_settings.help = `==== 📺 恋综系统控制台 ====
.设置 基础  - 恋综名、群号、核心功能开关
.设置 互动  - 冷却时间、邀约时长、地点系统
.设置 信件  - 寄信开关/每日上限/混乱参数
.设置 发送信件 - 发送信件开关/上限/字数/赏金
.设置 心动信 - 心动信开关/送达时间/曝光设置
.设置 公告  - 公开广播概率/开关/触发频率
.设置 道具  - 物品抽取、追踪器参数
.设置 商城  - 礼物商城模式/货币/刷新间隔
.设置 拍卖  - 拍卖展示群/匿名/播报/货币等
.设置 群组  - 小群管理、目击报告

💡 输入对应指令后，复制弹出的模板修改并重新发送即可。`;

cmd_settings.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足：该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const main = getMainExt();
    if (main) ensureDefaults(main);

    const rawMessage = msg.message.trim();
    const subCmd = argv.getArgN(1);

    // 提交模式：识别首行标识符
    if (rawMessage.includes('\n')) {
        const firstLine = rawMessage.split('\n')[0];
        if (firstLine.includes('基础设置')) return handleApply(ctx, msg, rawMessage, applyBasicParam);
        if (firstLine.includes('互动设置')) return handleApply(ctx, msg, rawMessage, applyInteractionParam);
        if (firstLine.includes('信件设置')) return handleApply(ctx, msg, rawMessage, applyLetterParam);
        if (firstLine.includes('发送信件设置')) return handleApply(ctx, msg, rawMessage, applyDirectLetterParam);
        if (firstLine.includes('心动信设置')) return handleApply(ctx, msg, rawMessage, applyLovemailParam);
        if (firstLine.includes('公告设置')) return handleApply(ctx, msg, rawMessage, applyPublicParam);
        if (firstLine.includes('道具设置')) return handleApply(ctx, msg, rawMessage, applyItemParam);
        if (firstLine.includes('商城设置')) return handleApply(ctx, msg, rawMessage, applyShopParam);
        if (firstLine.includes('拍卖设置')) return handleApply(ctx, msg, rawMessage, applyAuctionParam);
        if (firstLine.includes('群组设置')) return handleApply(ctx, msg, rawMessage, applyGroupParam);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查询模式
    switch (subCmd) {
        case '基础': return showBasicSettings(ctx, msg);
        case '互动': return showInteractionSettings(ctx, msg);
        case '信件': return showLetterSettings(ctx, msg);
        case '发送信件': return showDirectLetterSettings(ctx, msg);
        case '心动信': return showLovemailSettings(ctx, msg);
        case '公告': return showPublicSettings(ctx, msg);
        case '道具': return showItemSettings(ctx, msg);
        case '商城': return showShopSettings(ctx, msg);
        case '拍卖': return showAuctionSettings(ctx, msg);
        case '群组': return showGroupSettings(ctx, msg);
        default: seal.replyToSender(ctx, msg, cmd_settings.help);
    }
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置"] = cmd_settings;

// ========================
// 设置信箱上限指令
// ========================

let cmd_set_mailbox_limit = seal.ext.newCmdItemInfo();
cmd_set_mailbox_limit.name = '设置信箱上限';
cmd_set_mailbox_limit.help = `配置不同游戏天数的心动信每日投稿上限

格式1：.设置信箱上限                     # 查看当前所有配置
格式2：.设置信箱上限 D0:3 D1:5 D2:2     # 批量设置多天（空格分隔）
格式3：.设置信箱上限 默认 3              # 设置全局默认上限（当某天未配置时使用）
格式4：.设置信箱上限 清空                # 清除所有按天配置（仅保留全局默认）

示例：
.设置信箱上限 D0:1 D1:5 D2:3 D3:2
.设置信箱上限 默认 3
.设置信箱上限 清空`;

cmd_set_mailbox_limit.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const arg1 = argv.getArgN(1);

    let dayLimits = JSON.parse(getMainStorage("lovemail_day_limits", "{}"));
    let defaultLimit = parseInt(getMainStorage("lovemail_default_limit", "3"));

    if (!arg1) {
        let msgText = `📮 当前心动信投稿上限配置：\n`;
        msgText += `• 全局默认：${defaultLimit} 封/天\n`;
        if (Object.keys(dayLimits).length > 0) {
            msgText += `• 按天特殊配置：\n`;
            const sorted = Object.keys(dayLimits).sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)));
            for (const day of sorted) {
                msgText += `  ${day}：${dayLimits[day]} 封\n`;
            }
        } else {
            msgText += `• 暂无按天配置\n`;
        }
        msgText += `\n💡 使用「。设置信箱上限 D0:3 D1:5」批量设置。`;
        seal.replyToSender(ctx, msg, msgText);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (arg1 === "清空") {
        setMainStorage("lovemail_day_limits", "{}");
        seal.replyToSender(ctx, msg, "✅ 已清空所有按天配置，后续将只使用全局默认上限。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (arg1 === "默认") {
        const newDefault = parseInt(argv.getArgN(2));
        if (isNaN(newDefault) || newDefault < 1) {
            return seal.replyToSender(ctx, msg, "❌ 默认上限必须是 ≥1 的数字");
        }
        setMainStorage("lovemail_default_limit", newDefault.toString());
        seal.replyToSender(ctx, msg, `✅ 已设置全局默认上限：${newDefault} 封/天`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const newLimits = {};
    let parseError = false;

    for (let i = 1; i <= argv.args.length; i++) {
        const part = argv.getArgN(i);
        if (!part) continue;
        const match = part.match(/^D(\d+):(\d+)$/i);
        if (match) {
            const dayKey = `D${match[1]}`;
            const limit = parseInt(match[2]);
            if (isNaN(limit) || limit < 1) {
                parseError = true;
                break;
            }
            newLimits[dayKey] = limit;
        } else {
            parseError = true;
            break;
        }
    }

    if (parseError || Object.keys(newLimits).length === 0) {
        return seal.replyToSender(ctx, msg, "❌ 格式错误，请使用：。设置信箱上限 D0:3 D1:5 D2:2");
    }

    const currentLimits = JSON.parse(getMainStorage("lovemail_day_limits", "{}"));
    Object.assign(currentLimits, newLimits);
    setMainStorage("lovemail_day_limits", JSON.stringify(currentLimits));

    let reply = `✅ 已更新以下天数的上限：\n`;
    for (const [day, limit] of Object.entries(newLimits)) {
        reply += `  ${day} → ${limit} 封\n`;
    }
    reply += `\n当前全局默认：${defaultLimit} 封/天`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置信箱上限"] = cmd_set_mailbox_limit;

// ========================
// 天数系统 & 统计报告
// ========================

/**
 * 生成统计报告
 */
function generateStatisticsReport(ctx, msg, newDay, previousDay, isCleared = false) {
    const platform = msg.platform;
    const main = getMainExt();
    if (!main) return "❌ 无法获取主插件数据";

    // 读取各种计数
    const meetingCounts = {
        "电话": parseInt(main.storageGet("a_meetingCount_call") || "0"),
        "私密": parseInt(main.storageGet("a_meetingCount_private") || "0"),
        "寄信": parseInt(main.storageGet("a_meetingCount_chaosletter") || "0"),
        "发送信件": parseInt(main.storageGet("a_meetingCount_directletter") || "0"),
        "心动信": parseInt(main.storageGet("a_meetingCount_lovemail") || "0"),
        "礼物": parseInt(main.storageGet("a_meetingCount_gift") || "0"),
        "心愿": parseInt(main.storageGet("a_meetingCount_wish") || "0"),
        "官约": parseInt(main.storageGet("a_meetingCount_official") || "0")
    };

    const groupList = JSON.parse(main.storageGet("group") || "[]");
    const totalGroups = groupList.length;
    const occupiedGroups = groupList.filter(g => g.endsWith("_占用")).length;
    const availableGroups = totalGroups - occupiedGroups;

    const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
    const playerCount = a_private_group[platform] ? Object.keys(a_private_group[platform]).length : 0;
    const loveshow_name = JSON.parse(main.storageGet("love_show_name") || "\"未设置\"");

    const appointmentList = JSON.parse(main.storageGet("appointmentList") || "[]");
    const pendingRequests = appointmentList.length;

    const b_MultiGroupRequest = JSON.parse(main.storageGet("b_MultiGroupRequest") || "{}");
    const multiRequests = Object.keys(b_MultiGroupRequest).length;

    const b_confirmedSchedule = JSON.parse(main.storageGet("b_confirmedSchedule") || "{}");
    let activeMeetings = 0;
    for (const key in b_confirmedSchedule) {
        activeMeetings += b_confirmedSchedule[key].filter(item => item.status === "active").length;
    }

    const wishPool = JSON.parse(main.storageGet("a_wishPool") || "[]");
    const wishCount = wishPool.length;

    const lovemailPool = JSON.parse(main.storageGet("lovemail_pool") || "[]");
    const lovemailCount = lovemailPool.length;

    const groupExpireInfo = JSON.parse(main.storageGet("group_expire_info") || "{}");
    const expiredGroups = Object.entries(groupExpireInfo)
        .filter(([_, info]) => Date.now() > info.expireTime)
        .length;

    let report = 
        `📊 【${loveshow_name}统计报告】\n\n` +
        `🔄 天数切换：${previousDay} → ${newDay}\n` +
        `🕒 生成时间：${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}\n` +
        `👥 【玩家统计】\n• 绑定角色数：${playerCount} 人\n\n` +
        `📞 【会面统计】\n` +
        `• 电话：${meetingCounts["电话"]} 次\n` +
        `• 私密：${meetingCounts["私密"]} 次\n` +
        `• 官约：${meetingCounts["官约"]} 次\n` +
        `• 寄信：${meetingCounts["寄信"]} 次\n` +
        `• 发送信件：${meetingCounts["发送信件"]} 次\n` +
        `• 心动信派送：${meetingCounts["心动信"]} 次\n` +
        `• 礼物馈赠：${meetingCounts["礼物"]} 次\n` +
        `• 心愿达成：${meetingCounts["心愿"]} 次\n\n` +
        `📋 【待办事项】\n` +
        `• 待处理请求：${pendingRequests} 个\n` +
        `• 多人邀约：${multiRequests} 个\n` +
        `• 心愿漂流瓶：${wishCount} 个\n` +
        `• 心动信：${lovemailCount} 封\n\n` +
        `👥 【群组状态】\n` +
        `• 群组总数：${totalGroups} 个\n` +
        `• 可用群组：${availableGroups} 个（${availableGroups === 0 ? "⚠️ 需要添加群号" : "✅ 正常"}）\n` +
        `• 占用群组：${occupiedGroups} 个\n` +
        `• 已过期群组：${expiredGroups} 个${expiredGroups > 0 ? " ⚠️ 需要清理" : ""}\n` +
        `• 活跃会议：${activeMeetings} 个\n\n`;

    if (availableGroups === 0) {
        report += `⚠️ 【紧急建议】\n• 可用群组为0，请立即使用「。添加群号」添加备用群\n`;
    }
    if (expiredGroups > 0) {
        report += `• 有 ${expiredGroups} 个群组已过期，请使用「。查看到期群」处理\n`;
    }
    if (pendingRequests > 10) {
        report += `• 待处理请求较多（${pendingRequests}个），建议提醒玩家处理\n`;
    }

    return report;
}

/**
 * 发送统计报告到后台群
 */
function sendStatisticsToBackgroundGroup(ctx, msg, newDay, statisticsReport, isCleared) {
    const platform = msg.platform;
    const main = getMainExt();
    if (!main) return;

    const backgroundGroupId = JSON.parse(main.storageGet("background_group_id") || "null");
    if (!backgroundGroupId) return;

    const backgroundMsg = seal.newMessage();
    backgroundMsg.messageType = "group";
    backgroundMsg.sender = {};
    // 兼容自动天数重置时 ctx 为 null 的情况
    if (ctx && ctx.endPoint && ctx.endPoint.userId) {
        backgroundMsg.sender.userId = ctx.endPoint.userId;
    } else {
        backgroundMsg.sender.userId = "0"; // 默认值
    }
    backgroundMsg.groupId = `${platform}-Group:${backgroundGroupId}`;
    const backgroundCtx = ctx ? seal.createTempCtx(ctx.endPoint, backgroundMsg) : seal.createTempCtx(seal.getEndPoints()[0], backgroundMsg);

    const backgroundMessage = 
        `📢 【系统通知】\n` +
        `全局天数已切换到：${newDay}\n` +
        `${isCleared ? "✅ 所有计数已重置" : "⏸️ 计数保持原样"}\n\n` +
        `${statisticsReport}\n` +
        `💡 操作建议：\n` +
        `1. 检查可用群组数量，不足时及时添加\n` +
        `2. 处理已过期的群组\n` +
        `3. 提醒玩家处理待办请求\n` +
        `4. 根据剧情需要安排官方约会`;

    seal.replyToSender(backgroundCtx, backgroundMsg, backgroundMessage);
}

// ========================
// 天数设置指令（默认自动清空）
// ========================

let cmd_set_days = seal.ext.newCmdItemInfo();
cmd_set_days.name = "设置天数";
cmd_set_days.help = "。设置天数 D1 —— 设置全局天数，自动清空所有会面计数、信件计数、寄信限制、心愿池和心动信池\n示例：\n。设置天数 D2\n。设置天数 D3";
cmd_set_days.solve = (ctx, msg, args) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 该指令仅限骰主或管理员使用"), seal.ext.newCmdExecuteResult(true);
    let day = args.getArgN(1);
    if (!day || !/^D\d+$/i.test(day)) return seal.replyToSender(ctx, msg, "⚠️ 请输入正确的天数格式，例如：。设置天数 D1"), seal.ext.newCmdExecuteResult(true);
    day = day.toUpperCase();

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const prev = main.storageGet("global_days") || "未设置";
    main.storageSet("global_days", day);
    main.storageSet("auto_day_last_reset", "0");

    let resp = `✅ 已将全局天数从 ${prev} 设置为：${day}`;

    // 自动清空所有计数
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official"].forEach(k => main.storageSet(k, "0"));
    const groups = JSON.parse(main.storageGet("a_private_group") || "{}")[msg.platform];
    if (groups) {
        for (let name in groups) {
            main.storageSet(`chaos_letter_daily_${msg.platform}:${groups[name][0]}_${day}`, "0");
        }
    }
    main.storageSet("a_wishPool", "[]");
    main.storageSet("lovemail_pool", "[]");
    resp += "\n✅ 已自动清空所有会面计数、每日信件计数、寄信限制、心愿池和心动信池";

    const report = generateStatisticsReport(ctx, msg, day, prev);
    const platform = msg.platform;

    const announceGid = JSON.parse(main.storageGet("adminAnnounceGroupId") || "null");
    if (announceGid) {
        sendTextToGroup(platform, announceGid, `📜 全局天数已从 ${prev} 切换到 ${day}（所有计数已自动重置）`);
    }
    const bgGid = JSON.parse(main.storageGet("background_group_id") || "null");
    if (bgGid) sendStatisticsToBackgroundGroup(ctx, msg, day, report, true);

    seal.replyToSender(ctx, msg, resp + `\n\n📊 统计报告已生成${bgGid ? '并发送到后台群' : ''}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置天数"] = cmd_set_days;

// ========================
// 自动天数系统
// ========================

let autoDayTimer = null;

function performAutoDayReset(newDay, now) {
    const main = getMainExt();
    if (!main) return;

    const prev = main.storageGet("global_days") || "未设置";
    main.storageSet("global_days", newDay);
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official"].forEach(k => main.storageSet(k, "0"));
    const groups = JSON.parse(main.storageGet("a_private_group") || "{}")["QQ"];
    if (groups) {
        for (let name in groups) {
            main.storageSet(`chaos_letter_daily_QQ:${groups[name][0]}_${newDay}`, "0");
        }
    }
    main.storageSet("a_wishPool", "[]");
    main.storageSet("lovemail_pool", "[]");

    const mockMsg = { platform: "QQ" };
    const report = generateStatisticsReport(null, mockMsg, newDay, prev);
    const announceGid = JSON.parse(main.storageGet("adminAnnounceGroupId") || "null");
    if (announceGid) sendTextToGroup("QQ", announceGid, `📜 自动天数推进：${prev} → ${newDay}（所有计数已清空）`);
    const bgGid = JSON.parse(main.storageGet("background_group_id") || "null");
    if (bgGid) sendStatisticsToBackgroundGroup(null, mockMsg, newDay, report, true);

    console.log(`[自动天数] 已从 ${prev} 推进至 ${newDay}，并清空所有计数`);
}

function registerAutoDaySystem() {
    if (autoDayTimer) clearInterval(autoDayTimer);
    autoDayTimer = setInterval(() => {
        const main = getMainExt();
        if (!main) return;
        if (!JSON.parse(main.storageGet("auto_day_reset_enabled") || "false")) return;
        const now = new Date();
        if (now.getHours() === 23 && now.getMinutes() === 59) {
            const todayKey = `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}`;
            if (parseInt(main.storageGet("auto_day_last_reset") || "0") === todayKey) return;
            let cur = main.storageGet("global_days") || "D0";
            let m = cur.match(/^D(\d+)$/i);
            if (!m) { cur = "D0"; m = ["D0","0"]; }
            performAutoDayReset(`D${parseInt(m[1])+1}`, now);
            main.storageSet("auto_day_last_reset", todayKey);
        }
    }, 60000);
}

// ========================
// 自动天数开关指令
// ========================

let cmd_enable_auto_day = seal.ext.newCmdItemInfo();
cmd_enable_auto_day.name = "开启自动天数";
cmd_enable_auto_day.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "权限不足");
    const main = getMainExt();
    if (main) main.storageSet("auto_day_reset_enabled", "true");
    seal.replyToSender(ctx, msg, "✅ 自动天数推进已开启，每天 23:59 自动将天数 +1 并清空计数");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开启自动天数"] = cmd_enable_auto_day;

let cmd_disable_auto_day = seal.ext.newCmdItemInfo();
cmd_disable_auto_day.name = "关闭自动天数";
cmd_disable_auto_day.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "权限不足");
    const main = getMainExt();
    if (main) main.storageSet("auto_day_reset_enabled", "false");
    seal.replyToSender(ctx, msg, "⏸️ 自动天数推进已关闭");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["关闭自动天数"] = cmd_disable_auto_day;

// 启动自动天数轮询
registerAutoDaySystem();