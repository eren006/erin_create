// ==UserScript==
// @name         长日设置
// @author       长日将尽
// @version      1.1.0
// @description  独立的设置控制台（基础、互动、信件、公告）及天数系统、统计报告。所有数据统一存储在主插件 changri 中。
// @timestamp    1743292800
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E8%AE%BE%E7%BD%AE.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E8%AE%BE%E7%BD%AE.js
// ==/UserScript==

/**
 * 说明：
 * 1. 核心依赖：通过 seal.ext.find('changri') 寻找主插件，读写其存储中的配置数据。
 * 2. 功能模块：统一设置面板（基础、互动、信件、公告）、天数管理、自动天数推进、统计报告。
 * 3. 数据存储：所有配置项、计数、池子数据均存储在主插件 changri 的存储空间中。
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
    const main = seal.ext.find('changri');
    if (!main) {
        console.error("❌ 设置系统错误：未找到主插件 changri，请检查主插件是否已加载");
        return null;
    }
    return main;
}

/**
 * 权限检查（依赖 changri 的管理员列表）
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
// 参数模板系统
// ========================

const settingsConfig = {
    基础设置: {
        title: ".设置 基础设置",
        params: [
            { label: '恋综名', key: 'love_show_name', type: 'string', default: '未设置', raw: true },
            { label: '微信', key: 'global_feature_toggle', nested: 'enable_wechat', type: 'bool', default: true },
            { label: '礼物', key: 'global_feature_toggle', nested: 'enable_general_gift', type: 'bool', default: true },
            { label: '心愿', key: 'global_feature_toggle', nested: 'enable_wish_system', type: 'bool', default: true },
            { label: '发起邀约', key: 'global_feature_toggle', nested: 'enable_general_appointment', type: 'bool', default: true },
            { label: '关系线系统', key: 'relationship_system_enabled', type: 'bool', default: true },
            { label: '关系线上限', key: 'max_relationships_per_user', type: 'string', default: '5' },
            { label: '点歌群', key: 'song_group_id', type: 'string', default: '未设置', raw: true },
            { label: '后台群', key: 'background_group_id', type: 'string', default: '未设置', raw: true },
            { label: '公告群', key: 'adminAnnounceGroupId', type: 'string', default: '未设置', raw: true },
            { label: '水群', key: 'water_group_id', type: 'string', default: '未设置', raw: true },
            { label: '复盘群分流', key: 'fupan_routing_enabled', type: 'bool', default: false },
            { label: '复盘群分流群', key: 'fupan_routing_groups', type: 'routing', default: '未设置' }
        ]
    }
};

function getParamValue(param) {
    const raw = getMainStorage(param.key, JSON.stringify(param.default));
    if (param.raw) return raw.replace(/"/g, '');
    if (param.type === 'routing') {
        try {
            const map = JSON.parse(raw);
            if (!map || !Object.keys(map).length) return '未设置';
            return Object.entries(map).map(([d, g]) => `${d}:${g}`).join('，');
        } catch (e) { return '未设置'; }
    }
    try {
        const parsed = JSON.parse(raw);
        if (param.nested) {
            // 修正：判断布尔值 true 或 字符串 '开启'
            return (parsed[param.nested] === true || parsed[param.nested] === '开启') ? '开启' : '关闭';
        }
        // 修正：判断布尔值 true、字符串 'true' 或 字符串 '开启'
        if (param.type === 'bool') {
            return (parsed === true || parsed === 'true' || parsed === '开启') ? '开启' : '关闭';
        }
        return parsed;
    } catch (e) {
        return param.default;
    }
}

function setParamValue(param, val) {
    if (param.type === 'routing') {
        const pairs = val.split(/[，,\s]+/);
        const map = {};
        for (const pair of pairs) {
            const m = pair.trim().match(/^(D\d+)[：:]\s*(\d+)$/i);
            if (m) map[m[1].toUpperCase()] = m[2];
        }
        setMainStorage(param.key, JSON.stringify(map));
        return;
    }
    if (param.nested) {
        let cfg = JSON.parse(getMainStorage(param.key, "{}"));
        cfg[param.nested] = (val === '开启');
        setMainStorage(param.key, JSON.stringify(cfg));
    } else if (param.type === 'bool') {
        setMainStorage(param.key, JSON.stringify(val === '开启'));
    } else if (param.raw) {
        setMainStorage(param.key, JSON.stringify(val === '未设置' ? null : val));
    } else {
        setMainStorage(param.key, val);
    }
}

function showSettings(ctx, msg, category) {
    const config = settingsConfig[category];
    if (!config) return seal.replyToSender(ctx, msg, "❌ 未知的设置类别");

    const results = [config.title];
    for (const param of config.params) {
        const val = getParamValue(param);
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyParam(name, val, category) {
    const config = settingsConfig[category];
    if (!config) return { success: false, message: "❌ 未知的设置类别" };

    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };

    setParamValue(param, val);
    if (param.type === 'bool') {
        return { success: true, message: `【${name}】已${val}` };
    }
    return { success: true, message: `【${name}】已更新` };
}

// 保留旧接口以兼容现有命令
function showBasicSettings(ctx, msg) {
    showSettings(ctx, msg, '基础设置');
}

function applyBasicParam(name, val) {
    return applyParam(name, val, '基础设置');
}

// ========================
// 互动设置模块
// ========================

settingsConfig['互动设置'] = {
    title: ".设置 互动设置",
    params: [
        { label: '地点系统', getter: () => getPlaceSystemConfig().enabled ? '开启' : '关闭', setter: (v) => { let c = getPlaceSystemConfig(); c.enabled = (v === '开启'); setPlaceSystemConfig(c); } },
        { label: '结戏抽取', key: 'end_game_draw_config', nested: 'enabled', type: 'bool', default: false },
        { label: '电话最小时长', key: 'appointment_duration_config', nested: 'phone', type: 'number', default: 29 },
        { label: '私密最小时长', key: 'appointment_duration_config', nested: 'private', type: 'number', default: 59 },
        { label: '寄信冷却时间', key: 'mailCooldown', type: 'string', default: '60' },
        { label: '送礼冷却时间', key: 'giftCooldown', type: 'string', default: '30' },
        { label: '送礼模式', key: 'giftMode', type: 'string', default: '0' }
    ]
};

function getConfigParamValue(param) {
    if (param.getter) return param.getter();
    const raw = getMainStorage(param.key, JSON.stringify(param.default));
    try {
        const parsed = JSON.parse(raw);
        if (param.nested) {
            if (param.type === 'bool') {
                return parsed[param.nested] !== false ? '开启' : '关闭';
            }
            return parsed[param.nested];
        }
        if (param.type === 'bool') return parsed === true || parsed === '开启' ? '开启' : '关闭';
        return parsed;
    } catch (e) {
        return param.default;
    }
}

function setConfigParamValue(param, val) {
    if (param.setter) { param.setter(val); return; }
    if (param.nested) {
        let cfg = JSON.parse(getMainStorage(param.key, "{}"));
        cfg[param.nested] = param.type === 'bool' ? (val === '开启') : (param.type === 'number' ? parseInt(val) : val);
        setMainStorage(param.key, JSON.stringify(cfg));
    } else if (param.type === 'bool') {
        setMainStorage(param.key, JSON.stringify(val === '开启'));
    } else {
        setMainStorage(param.key, val);
    }
}

function showInteractionSettings(ctx, msg) {
    const config = settingsConfig['互动设置'];
    const results = [config.title];
    for (const param of config.params) {
        const val = getConfigParamValue(param);
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyInteractionParam(name, val) {
    const config = settingsConfig['互动设置'];
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    setConfigParamValue(param, val);
    return { success: true, message: `【${name}】已更新` };
}

// ========================
// 信件设置模块 - 简化版
// ========================

function getOrParseJson(key, defaults) {
    const raw = getMainStorage(key, "{}");
    try {
        return { ...defaults, ...JSON.parse(raw) };
    } catch (e) {
        return defaults;
    }
}

settingsConfig['信件设置'] = {
    title: ".设置 信件设置",
    params: [
        { label: '寄信', key: 'global_feature_toggle', nested: 'enable_chaos_letter', type: 'bool', default: true },
        { label: '寄信每日上限', key: 'chaos_letter_config', nested: 'dailyLimit', type: 'number', default: 5 },
        { label: '寄信允许自定义名字', key: 'allow_custom_letter_sign', type: 'bool_string', default: false },
        { label: '寄信混乱送错', key: 'chaos_letter_config', nested: 'misdelivery', type: 'number', default: 0 },
        { label: '寄信混乱涂改', key: 'chaos_letter_config', nested: 'blackoutText', type: 'number', default: 0 },
        { label: '寄信混乱丢失', key: 'chaos_letter_config', nested: 'loseContent', type: 'number', default: 0 },
        { label: '寄信混乱反义', key: 'chaos_letter_config', nested: 'antonymReplace', type: 'number', default: 0 },
        { label: '寄信混乱乱序', key: 'chaos_letter_config', nested: 'reverseOrder', type: 'number', default: 0 },
        { label: '寄信混乱混淆', key: 'chaos_letter_config', nested: 'mistakenSignature', type: 'number', default: 0 },
        { label: '寄信混乱诗意', key: 'chaos_letter_config', nested: 'poeticSignature', type: 'number', default: 0 }
    ]
};

function getLetterParamValue(param) {
    if (param.type === 'bool_string') {
        return getMainStorage(param.key, "false") === "true" ? '开启' : '关闭';
    }
    const raw = getMainStorage(param.key, JSON.stringify(param.default));
    try {
        const parsed = JSON.parse(raw);
        if (param.nested) {
            if (param.type === 'bool') return parsed[param.nested] !== false ? '开启' : '关闭';
            return parsed[param.nested];
        }
        return parsed;
    } catch (e) {
        return param.default;
    }
}

function setLetterParamValue(param, val) {
    if (param.type === 'bool_string') {
        setMainStorage(param.key, val === '开启' ? "true" : "false");
        return;
    }
    if (param.nested) {
        let cfg = JSON.parse(getMainStorage(param.key, "{}"));
        cfg[param.nested] = param.type === 'bool' ? (val === '开启') : parseInt(val);
        setMainStorage(param.key, JSON.stringify(cfg));
    } else {
        setMainStorage(param.key, val);
    }
}

function showLetterSettings(ctx, msg) {
    const config = settingsConfig['信件设置'];
    const results = [config.title];
    for (const param of config.params) {
        const val = getLetterParamValue(param);
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyLetterParam(name, val) {
    const config = settingsConfig['信件设置'];
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    setLetterParamValue(param, val);
    return { success: true, message: `【${name}】已更新` };
}

// ========================
// 发送信件设置模块
// ========================

settingsConfig['发送信件设置'] = {
    title: ".设置 发送信件设置",
    params: [
        { label: '发送信件', key: 'global_feature_toggle', nested: 'enable_direct_letter', type: 'bool', default: false },
        { label: '发送信件每日上限', key: 'direct_letter_daily_limit', type: 'string', default: '5' },
        { label: '发送信件最低字数', key: 'direct_letter_min_chars', type: 'string', default: '0' },
        { label: '发送信件赏金', key: 'direct_letter_reward', type: 'string', default: '0' }
    ]
};

function showDirectLetterSettings(ctx, msg) {
    const config = settingsConfig['发送信件设置'];
    const results = [config.title];
    for (const param of config.params) {
        const val = getConfigParamValue(param);
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyDirectLetterParam(name, val) {
    const config = settingsConfig['发送信件设置'];
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    setConfigParamValue(param, val);
    return { success: true, message: `【${name}】已更新` };
}

// ========================
// 公告设置模块
// ========================

settingsConfig['公告设置'] = {
    title: ".设置 公告设置",
    params: [
        { label: '心愿公开提醒', key: 'wish_public_send', type: 'bool_string', default: false },
        { label: '送礼公开发送', key: 'gift_public_send', type: 'bool_string', default: false },
        { label: '寄信公开发送', key: 'letter_public_send', type: 'bool_string', default: false },
        { label: '寄信公开概率', key: 'chaos_letter_config', nested: 'publicChance', type: 'number', default: 50 },
        { label: '礼物公开概率', key: 'giftPublicChance', type: 'string', default: '50' },
        { label: '每日礼物上限', key: 'giftDailyLimit', type: 'string', default: '100' },
        { label: '公告触发频率', key: 'announceFrequency', type: 'string', default: '5' }
    ]
};

function showPublicSettings(ctx, msg) {
    const config = settingsConfig['公告设置'];
    const results = [config.title];
    for (const param of config.params) {
        let val;
        if (param.type === 'bool_string') {
            val = getMainStorage(param.key, "false") === "true" ? '开启' : '关闭';
        } else {
            val = getConfigParamValue(param);
        }
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyPublicParam(name, val) {
    const config = settingsConfig['公告设置'];
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    if (param.type === 'bool_string') {
        setMainStorage(param.key, val === '开启' ? "true" : "false");
    } else {
        setConfigParamValue(param, val);
    }
    return { success: true, message: `【${name}】已更新` };
}

// ========================
// 心动信设置模块
// ========================

settingsConfig['心动信设置'] = {
    title: ".设置 心动信设置",
    params: [
        { label: '心动信', key: 'global_feature_toggle', nested: 'enable_lovemail', type: 'bool', default: true },
        { label: '心动信送达时间', key: 'lovemail_delivery_time', type: 'string_raw', default: '22:00' },
        { label: '心动信曝光', key: 'lovemail_expose', type: 'bool_string', default: false },
        { label: '心动信曝光概率', key: 'lovemail_expose_chance', type: 'string', default: '10', validate: (v) => {
            const n = parseInt(v);
            if (isNaN(n) || n < 0 || n > 100) return "概率请填 0-100 的整数";
            return null;
        }}
    ]
};

function showLovemailSettings(ctx, msg) {
    const config = settingsConfig['心动信设置'];
    const results = [config.title];
    for (const param of config.params) {
        let val;
        if (param.type === 'string_raw') {
            val = getMainStorage(param.key, param.default).replace(/"/g, '');
        } else if (param.type === 'bool_string') {
            val = getMainStorage(param.key, param.default) === "true" ? '开启' : '关闭';
        } else {
            val = getConfigParamValue(param);
        }
        results.push(`【${param.label}】${val}`);
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyLovemailParam(name, val) {
    const config = settingsConfig['心动信设置'];
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    if (param.validate) {
        const err = param.validate(val);
        if (err) return { success: false, message: `❌ ${err}` };
    }
    if (param.type === 'string_raw') {
        setMainStorage(param.key, JSON.stringify(val));
    } else if (param.type === 'bool_string') {
        setMainStorage(param.key, val === '开启' ? "true" : "false");
    } else {
        setConfigParamValue(param, val);
    }
    return { success: true, message: `【${name}】已更新` };
}

function showItemSettings(ctx, msg) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const trackerRate = parseInt(main.storageGet("item_tracker_success_rate") || "70");
    const drawLimit = parseInt(main.storageGet("item_daily_draw_limit") || "2");
    const showPartner = main.storageGet("item_tracker_show_partner") !== "false";
    const timeRestrict = main.storageGet("item_tracker_time_restrict") !== "false";
    const itemPoolMode = getMainStorage("item_pool_mode", "自由池");
    const applyNotify = main.storageGet("apply_item_notification") !== "false";
    const exposeNameRate = parseInt(main.storageGet("apply_item_expose_rate") || "0");
    const applyHours = main.storageGet("apply_item_hours") || "不限";

    const results = [
        ".设置 道具设置",
        `【追踪器成功率】${trackerRate}`,
        `【每日抽取上限】${drawLimit}`,
        `【追踪器显示伙伴】${showPartner ? "开启" : "关闭"}`,
        `【追踪器时间限制】${timeRestrict ? "开启" : "关闭"}`,
        `【物品池模式】${itemPoolMode}`,
        `【施加是否提醒】${applyNotify ? '开启' : '关闭'}`,
        `【暴露名字概率】${exposeNameRate}%`,
        `【施加可用时段】${applyHours}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

// ========================
// 礼品店设置模块
// ========================
function showShopSettings(ctx, msg) {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const refreshHours = parseInt(main.storageGet("shop_refresh_hours") || "24");

    seal.replyToSender(ctx, msg, [
        ".设置 礼品店设置",
        `【礼品店刷新间隔】${refreshHours}`,
    ].join('\n'));
}

function applyShopParam(name, val) {
    const main = getMainExt();
    if (!main) return { success: false, message: "无法连接主插件" };

    if (name === '礼品店刷新间隔') {
        const hours = parseInt(val);
        if (isNaN(hours) || hours < 1) return { success: false, message: "【礼品店刷新间隔】必须是 ≥1 的整数（单位：小时）" };
        main.storageSet("shop_refresh_hours", hours.toString());
        main.storageSet("shop_personal_display", "{}");
        return { success: true, message: `【礼品店刷新间隔】已设为 ${hours} 小时（所有人下次进入礼品店生效）` };
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
    const reg = JSON.parse(main.storageGet("item_registry") || "{}");
    const registeredCurrencies = Object.values(reg).filter(r => r.type === "currency").map(r => r.name);
    const currencyLine = registeredCurrencies.length
        ? `【拍卖货币】${currency}（可选：${registeredCurrencies.join("、")}）`
        : `【拍卖货币】${currency}（暂无已注册货币）`;
    seal.replyToSender(ctx, msg, [
        ".设置 拍卖设置",
        `【拍卖展示群】${displayGroup}`,
        `【允许匿名出价】${allowAnon}`,
        `【出价播报】${broadcast}`,
        `【展示最高出价者】${showTop}`,
        currencyLine,
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
        const reg = JSON.parse(main.storageGet("item_registry") || "{}");
        const isCurrency = Object.values(reg).some(i => i.type === "currency" && i.name === attr);
        if (!presets.includes(attr) && !isCurrency) return { success: false, message: `❌ 「${attr}」不是已注册的属性或货币。\n请先注册属性（注册属性 ${attr}）或货币（注册货币 ${attr}*描述）` };
        main.storageSet("auction_currency", attr);
        return { success: true, message: `【拍卖货币】已设为「${attr}」${isCurrency ? "（货币物品）" : "（属性）"}` };
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
    if (name === '施加是否提醒') {
        const isOpen = (val === '开启');
        main.storageSet("apply_item_notification", isOpen ? "true" : "false");
        return { success: true, message: `【施加是否提醒】已${val}` };
    }
    if (name === '暴露名字概率') {
        const rate = parseInt(val);
        if (isNaN(rate) || rate < 0 || rate > 100) {
            return { success: false, message: "❌ 暴露名字概率必须是 0-100 之间的数字" };
        }
        main.storageSet("apply_item_expose_rate", rate.toString());
        return { success: true, message: `【暴露名字概率】已设为：${rate}%` };
    }
    if (name === '施加可用时段') {
    if (val === '不限' || val === '全部') {
        main.storageSet("apply_item_hours", "");
        return { success: true, message: `【施加可用时段】已设为全天可用` };
    }
    if (!/^[\d\-,，]+$/.test(val)) {
            return { success: false, message: "❌ 格式错误。示例：18-23 或 9-12,14-18" };
        }
        main.storageSet("apply_item_hours", val);
        return { success: true, message: `【施加可用时段】已设为：${val}` };
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
// 群组管理设置模块 - 简化版
// ========================

function parseBoolValue(key, def) {
    try {
        const val = getMainStorage(key, String(def));
        return val === "true" || JSON.parse(val) === true;
    } catch (e) { return def; }
}

function showGroupSettings(ctx, msg) {
    const sighting = getSightingConfig();
    const enableJoin = getMainStorage("enable_join_existing_appointment", "true") !== "false";
    const autoMerge = parseBoolValue("auto_merge_duplicate_private", false);
    const requireFupan = parseBoolValue("require_fupan_before_end", true);
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
    const sightingFields = { '目击报告': 'enabled', '目击报告方式': 'send_to_all', '目击每日上限': 'max_reports_per_day', '时间重叠阈值': 'threshold', '包含已结束': 'include_ended_meetings' };
    if (sightingFields[name]) {
        let c = getSightingConfig();
        if (name === '目击报告') c.enabled = (val === '开启');
        else if (name === '目击报告方式') c.send_to_all = (val === '双向通知');
        else if (name === '目击每日上限') c.max_reports_per_day = parseInt(val);
        else if (name === '时间重叠阈值') c.time_overlap_threshold = parseInt(val) / 100;
        else if (name === '包含已结束') c.include_ended_meetings = (val === '是');
        setSightingConfig(c);
        return { success: true, message: `【${name}】已更新` };
    }

    const boolFields = { '允许加入已有私约': 'enable_join_existing_appointment', '自动合并重合私约': 'auto_merge_duplicate_private', '复盘强制结束': 'require_fupan_before_end' };
    if (boolFields[name]) {
        setMainStorage(boolFields[name], JSON.stringify(val === '开启'));
        return { success: true, message: `【${name}】已${val}` };
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
        "shop_refresh_hours": "24",
    };
    for (const [key, val] of Object.entries(defaults)) {
        const existing = main.storageGet(key);
        if (!existing || existing.trim() === "") main.storageSet(key, val);
    }
}

// 已移除重复的cmd_settings声明，使用下面的新版本

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

    let backgroundGroupId = JSON.parse(main.storageGet("background_group_id") || "null");
    const fupanRouting = main.storageGet("fupan_routing_enabled") === "true";
    if (fupanRouting) {
        try {
            const routingMap = JSON.parse(main.storageGet("fupan_routing_groups") || "{}");
            const firstId = Object.values(routingMap)[0];
            if (firstId) backgroundGroupId = firstId;
        } catch (e) {}
    }
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
    const platform = msg.platform;

    // ★ 第一步：生成报告（在清空前，基于当前数据）
    const report = generateStatisticsReport(ctx, msg, day, prev);

    // ★ 第二步：清空所有计数
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official"].forEach(k => main.storageSet(k, "0"));
    const groups = JSON.parse(main.storageGet("a_private_group") || "{}")[platform];
    if (groups) {
        for (let name in groups) {
            main.storageSet(`chaos_letter_daily_${platform}:${groups[name][0]}_${day}`, "0");
        }
    }
    main.storageSet("a_wishPool", "[]");
    main.storageSet("lovemail_pool", "[]");

    // ★ 第三步：设置新天数
    main.storageSet("global_days", day);
    main.storageSet("auto_day_last_reset", "0");

    let resp = `✅ 已将全局天数从 ${prev} 设置为：${day}`;
    resp += "\n✅ 已自动清空所有会面计数、每日信件计数、寄信限制、心愿池和心动信池";

    // ★ 第四步：发送报告
    const announceGid = JSON.parse(main.storageGet("adminAnnounceGroupId") || "null");
    if (announceGid) {
        sendTextToGroup(platform, announceGid, `📜 全局天数已从 ${prev} 切换到 ${day}（所有计数已自动重置）`);
    }
    const bgGid = JSON.parse(main.storageGet("background_group_id") || "null");
    const fupanRoutingForReport = main.storageGet("fupan_routing_enabled") === "true";
    let reportTarget = bgGid;
    if (fupanRoutingForReport) {
        try {
            const rm = JSON.parse(main.storageGet("fupan_routing_groups") || "{}");
            const firstId = Object.values(rm)[0];
            if (firstId) reportTarget = firstId;
        } catch (e) {}
    }
    if (reportTarget) sendStatisticsToBackgroundGroup(ctx, msg, day, report, true);

    seal.replyToSender(ctx, msg, resp + `\n\n📊 统计报告已生成${reportTarget ? '并发送到后台群' : ''}`);
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
    const mockMsg = { platform: "QQ" };

    // ★ 第一步：生成报告（在清空前，基于当前数据）
    const report = generateStatisticsReport(null, mockMsg, newDay, prev);

    // ★ 第二步：清空所有计数
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official"].forEach(k => main.storageSet(k, "0"));
    const groups = JSON.parse(main.storageGet("a_private_group") || "{}")["QQ"];
    if (groups) {
        for (let name in groups) {
            main.storageSet(`chaos_letter_daily_QQ:${groups[name][0]}_${newDay}`, "0");
        }
    }
    main.storageSet("a_wishPool", "[]");
    main.storageSet("lovemail_pool", "[]");

    // ★ 第三步：设置新天数
    main.storageSet("global_days", newDay);

    // ★ 第四步：发送报告
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

// ========================
// 结戏加成管理指令（模版系统）
// ========================

let cmd_end_bonus = seal.ext.newCmdItemInfo();
cmd_end_bonus.name = "结戏加成";
cmd_end_bonus.help = `结戏加成 — 管理结戏自动发放奖励规则

结戏加成 模版列表              查看所有模版
结戏加成 可用参数              列出可用条件与奖励参数
结戏加成 查看 模版名           查看模版详情
结戏加成 批量 模版名 [类型]    多行写入/覆盖模版（类型：心意/官约/私约/电话/通用）
结戏加成 开启/关闭 模版名      启用或禁用模版
结戏加成 删除模版 模版名       删除整个模版
结戏加成 导出 模版名           导出为 JSON（可编辑后用导入覆盖）
结戏加成 导入 JSON字符串       JSON 导入/覆盖模版

批量格式（多行发送）：
结戏加成 批量 模版名 [类型]
and
段数 >= 5
奖励 好感度 2
池 金币 30 60 TJ00 1 40
or
字数 >= 800
奖励 金币 40
or
字数 >= 300
奖励 金币 15`;

cmd_end_bonus.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足");
        return seal.ext.newCmdExecuteResult(true);
    }

    const main = getMainExt();
    if (!main) return seal.ext.newCmdExecuteResult(true);

    const getTemplates = () => JSON.parse(main.storageGet("end_game_bonus_templates") || "[]");
    const saveTemplates = (t) => main.storageSet("end_game_bonus_templates", JSON.stringify(t));
    const findTemplate = (templates, name) => templates.find(t => t.name === name);


    const detectTargetType = (target) => {
        const reg = JSON.parse(main.storageGet("item_registry") || "{}");
        const upperTarget = target.toUpperCase();
        for (const r of Object.values(reg)) {
            if (r.type === "currency" && r.name === target) return "currency";
            if (r.type !== "currency" && (r.code === upperTarget || r.name === target)) return "item";
        }
        return "attr";
    };

    const sub = argv.getArgN(1);

    // 模版列表
    if (!sub || sub === "模版列表") {
        const templates = getTemplates();
        if (!templates.length) {
            seal.replyToSender(ctx, msg, "📋 暂无模版，使用「结戏加成 新建 模版名」创建。");
            return seal.ext.newCmdExecuteResult(true);
        }
        const typeTag = (t) => t.subtype && t.subtype !== "通用" ? `[${t.subtype}]` : "[通用]";
        const lines = templates.map((t, i) => `${t.enabled ? "✅" : "⏸️"} [${i+1}] ${t.name} ${typeTag(t)}`);
        seal.replyToSender(ctx, msg, `📋 结戏加成模版列表：\n${lines.join("\n")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 可用参数
    if (sub === "可用参数") {
        seal.replyToSender(ctx, msg, `📌 可用条件参数：
• 本场个人段数
• 本场个人总字数
• 本场个人平均每段字数
• 结戏最多耗费时间（分钟，<= 判断）

📌 可用运算符：>=  <=  =  !=  range（如 range 100 500）

📌 可用奖励目标：
• 已注册货币（货币名）
• 已注册道具（道具码）
• 已注册属性（属性名）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查看 模版名
    if (sub === "查看") {
        const name = argv.getArgN(2);
        if (!name) { seal.replyToSender(ctx, msg, "❌ 请指定模版名"); return seal.ext.newCmdExecuteResult(true); }
        const templates = getTemplates();
        const tpl = findTemplate(templates, name);
        if (!tpl) { seal.replyToSender(ctx, msg, `❌ 模版「${name}」不存在`); return seal.ext.newCmdExecuteResult(true); }

        const typeLabel = tpl.subtype || "通用";
        const lines = [`📋 模版：${tpl.name} ${tpl.enabled ? "✅" : "⏸️"} [${typeLabel}]`];
        let blockNum = 0;
        tpl.groups.forEach((group, gi) => {
            group.blocks.forEach((block, bi) => {
                blockNum++;
                if (blockNum > 1) {
                    lines.push(bi === 0 ? group.op : "and");
                }
                block.conditions.forEach(c => {
                    const valStr = c.op === "range" ? `${c.value[0]}-${c.value[1]}` : c.value;
                    lines.push(`【条件】${c.param} ${c.op} ${valStr}`);
                });
                (block.rewards || []).forEach(r => {
                    if (!r.type || r.type === "fixed") {
                        lines.push(`【固定奖励】${r.target}×${r.amount}`);
                    } else if (r.type === "pool") {
                        const total = r.items.reduce((s, it) => s + it.weight, 0);
                        const poolStr = r.items.map(it =>
                            `${it.target}×${it.amount}(${total > 0 ? Math.round(it.weight / total * 100) : 0}%)`
                        ).join(" / ");
                        lines.push(`【概率池】${poolStr || "（空）"}`);
                    }
                });
                lines.push(`  （块 #${blockNum}）`);
            });
        });
        seal.replyToSender(ctx, msg, lines.join("\n"));
        return seal.ext.newCmdExecuteResult(true);
    }


    // 开启 / 关闭 模版名
    if (sub === "开启" || sub === "关闭") {
        const name = argv.getArgN(2);
        if (!name) { seal.replyToSender(ctx, msg, "❌ 请指定模版名"); return seal.ext.newCmdExecuteResult(true); }
        const templates = getTemplates();
        const tpl = findTemplate(templates, name);
        if (!tpl) { seal.replyToSender(ctx, msg, `❌ 模版「${name}」不存在`); return seal.ext.newCmdExecuteResult(true); }
        tpl.enabled = (sub === "开启");
        saveTemplates(templates);
        seal.replyToSender(ctx, msg, `${sub === "开启" ? "✅" : "⏸️"} 模版「${name}」已${sub}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 批量 模版名 [类型]（多行自然语言格式）
    if (sub === "批量") {
        const name = argv.getArgN(2);
        if (!name) {
            seal.replyToSender(ctx, msg, `❌ 格式：结戏加成 批量 模版名 [类型]\n然后换行写规则，例如：\n\nand\n段数 >= 5\n奖励 好感度 2\n池 金币 30 60 TJ00 1 40\nor\n字数 >= 800\n奖励 金币 40\nor\n字数 >= 300\n奖励 金币 15`);
            return seal.ext.newCmdExecuteResult(true);
        }

        const validSubtypes = ["心意", "官约", "私约", "电话", "通用"];
        const rawSub = argv.getArgN(3) || "";
        const subtype = validSubtypes.includes(rawSub) ? rawSub : "通用";

        const allLines = msg.message.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
        const dataLines = allLines.slice(1); // 跳过命令行

        const paramAliases = {
            "段数": "本场个人段数",
            "字数": "本场个人总字数",
            "总字数": "本场个人总字数",
            "平均字数": "本场个人平均每段字数",
            "耗费时间": "结戏最多耗费时间",
        };
        const validParams = Object.values(paramAliases).concat(Object.keys(paramAliases));
        const validOps = [">=", "<=", "=", "!=", "range"];

        const groups = [];
        let currentGroup = null;
        let currentBlock = null;
        const errors = [];

        for (const line of dataLines) {
            if (line === "and" || line === "or") {
                const newBlock = { conditions: [], rewards: [] };
                if (line === "or" && currentGroup && currentGroup.op === "or") {
                    currentGroup.blocks.push(newBlock); // 同一 or 组追加新块
                } else {
                    currentGroup = { op: line, blocks: [newBlock] };
                    groups.push(currentGroup);
                }
                currentBlock = newBlock;
                continue;
            }

            if (!currentBlock) { errors.push(`需要先写 and 或 or：${line}`); continue; }

            // 奖励 目标 数量
            if (line.startsWith("奖励 ")) {
                const parts = line.slice(3).trim().split(/\s+/);
                if (parts.length < 2) { errors.push(`奖励格式错误：${line}`); continue; }
                const amount = parseInt(parts[1]);
                if (isNaN(amount)) { errors.push(`奖励数量不是数字：${line}`); continue; }
                currentBlock.rewards.push({ type: "fixed", target: parts[0], targetType: detectTargetType(parts[0]), amount });
                continue;
            }

            // 池 目标1 数量1 权重1 目标2 数量2 权重2 ...
            if (line.startsWith("池 ")) {
                const parts = line.slice(2).trim().split(/\s+/);
                if (parts.length % 3 !== 0) { errors.push(`概率池需要3个一组（目标 数量 权重）：${line}`); continue; }
                const items = [];
                let poolErr = false;
                for (let i = 0; i < parts.length; i += 3) {
                    const amount = parseInt(parts[i+1]), weight = parseInt(parts[i+2]);
                    if (isNaN(amount) || isNaN(weight)) { errors.push(`概率池数值错误：${parts[i]} ${parts[i+1]} ${parts[i+2]}`); poolErr = true; break; }
                    items.push({ target: parts[i], targetType: detectTargetType(parts[i]), amount, weight });
                }
                if (!poolErr) currentBlock.rewards.push({ type: "pool", items });
                continue;
            }

            // 条件：参数 运算符 数值
            const parts = line.split(/\s+/);
            if (parts.length >= 3) {
                const param = paramAliases[parts[0]] || parts[0];
                if (!validParams.includes(param)) { errors.push(`未知条件参数：${parts[0]}，可用：段数/字数/平均字数/耗费时间`); continue; }
                const op = parts[1];
                if (!validOps.includes(op)) { errors.push(`未知运算符：${op}，可用：>= <= = != range`); continue; }
                let value;
                if (op === "range") {
                    if (parts.length < 4) { errors.push(`range 需要两个数值：${line}`); continue; }
                    value = [parseInt(parts[2]), parseInt(parts[3])];
                } else {
                    value = parseInt(parts[2]);
                    if (isNaN(value)) { errors.push(`条件值不是数字：${parts[2]}`); continue; }
                }
                currentBlock.conditions.push({ param, op, value });
                continue;
            }

            errors.push(`无法识别的行：${line}`);
        }

        if (errors.length) {
            seal.replyToSender(ctx, msg, `❌ 解析出错：\n${errors.join("\n")}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        if (!groups.length) {
            seal.replyToSender(ctx, msg, "❌ 没有找到任何规则，请先写 and 或 or");
            return seal.ext.newCmdExecuteResult(true);
        }

        const templates = getTemplates();
        const existing = templates.findIndex(t => t.name === name);
        const tpl = { id: existing >= 0 ? templates[existing].id : Date.now(), name, subtype, enabled: true, groups };

        if (existing >= 0) {
            templates[existing] = tpl;
            seal.replyToSender(ctx, msg, `✅ 已覆盖更新模版「${name}」（${subtype}），共 ${groups.length} 个规则组`);
        } else {
            templates.push(tpl);
            seal.replyToSender(ctx, msg, `✅ 已创建模版「${name}」（${subtype}），共 ${groups.length} 个规则组`);
        }
        saveTemplates(templates);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 导出 模版名
    if (sub === "导出") {
        const name = argv.getArgN(2);
        if (!name) { seal.replyToSender(ctx, msg, "❌ 请指定模版名"); return seal.ext.newCmdExecuteResult(true); }
        const templates = getTemplates();
        const tpl = findTemplate(templates, name);
        if (!tpl) { seal.replyToSender(ctx, msg, `❌ 模版「${name}」不存在`); return seal.ext.newCmdExecuteResult(true); }
        const exported = { name: tpl.name, subtype: tpl.subtype || "通用", enabled: tpl.enabled, groups: tpl.groups };
        seal.replyToSender(ctx, msg, `📤 模版「${name}」JSON：\n${JSON.stringify(exported, null, 2)}\n\n编辑后用「结戏加成 导入 JSON」一次性导入。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 导入 JSON
    if (sub === "导入") {
        const raw = argv.args.slice(1).join(" ").trim();
        if (!raw) { seal.replyToSender(ctx, msg, "❌ 格式：结戏加成 导入 JSON字符串"); return seal.ext.newCmdExecuteResult(true); }

        let parsed;
        try { parsed = JSON.parse(raw); } catch(e) { seal.replyToSender(ctx, msg, `❌ JSON 解析失败：${e.message}`); return seal.ext.newCmdExecuteResult(true); }

        if (!parsed.name) { seal.replyToSender(ctx, msg, "❌ 缺少 name 字段"); return seal.ext.newCmdExecuteResult(true); }
        if (!Array.isArray(parsed.groups)) { seal.replyToSender(ctx, msg, "❌ 缺少 groups 数组"); return seal.ext.newCmdExecuteResult(true); }

        const validSubtypes = ["心意", "官约", "私约", "电话", "通用"];
        const subtype = parsed.subtype || "通用";
        if (!validSubtypes.includes(subtype)) { seal.replyToSender(ctx, msg, `❌ subtype 不合法，可选：${validSubtypes.join(" / ")}`); return seal.ext.newCmdExecuteResult(true); }

        for (const group of parsed.groups) {
            if (!group.op || !["and", "or"].includes(group.op)) { seal.replyToSender(ctx, msg, "❌ group.op 必须是 and 或 or"); return seal.ext.newCmdExecuteResult(true); }
            for (const block of (group.blocks || [])) {
                for (const r of (block.rewards || [])) {
                    if (r.type === "pool") {
                        for (const item of (r.items || [])) {
                            if (!item.targetType) item.targetType = detectTargetType(item.target);
                        }
                    } else {
                        if (!r.targetType) r.targetType = detectTargetType(r.target);
                        if (!r.type) r.type = "fixed";
                    }
                }
            }
        }

        const templates = getTemplates();
        const existing = templates.findIndex(t => t.name === parsed.name);
        const tpl = { id: existing >= 0 ? templates[existing].id : Date.now(), name: parsed.name, subtype, enabled: parsed.enabled !== false, groups: parsed.groups };

        if (existing >= 0) {
            templates[existing] = tpl;
            seal.replyToSender(ctx, msg, `✅ 已覆盖更新模版「${parsed.name}」（${subtype}）`);
        } else {
            templates.push(tpl);
            seal.replyToSender(ctx, msg, `✅ 已导入新模版「${parsed.name}」（${subtype}）`);
        }
        saveTemplates(templates);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 删除模版 模版名
    if (sub === "删除模版") {
        const name = argv.getArgN(2);
        if (!name) { seal.replyToSender(ctx, msg, "❌ 请指定模版名"); return seal.ext.newCmdExecuteResult(true); }
        const templates = getTemplates();
        const idx = templates.findIndex(t => t.name === name);
        if (idx === -1) { seal.replyToSender(ctx, msg, `❌ 模版「${name}」不存在`); return seal.ext.newCmdExecuteResult(true); }
        templates.splice(idx, 1);
        saveTemplates(templates);
        seal.replyToSender(ctx, msg, `🗑️ 已删除模版「${name}」`);
        return seal.ext.newCmdExecuteResult(true);
    }

    seal.replyToSender(ctx, msg, cmd_end_bonus.help);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结戏加成"] = cmd_end_bonus;

// ========================
// 攻防系统配置管理
// ========================

function getAttackDefenseConfig() {
    const defaultConfig = { enabled: false };
    try {
        const main = getMainExt();
        if (!main) return defaultConfig;
        const val = main.storageGet("attack_defense_config");
        return val ? { ...defaultConfig, ...JSON.parse(val) } : defaultConfig;
    } catch(e) { return defaultConfig; }
}

function setAttackDefenseConfig(config) {
    const main = getMainExt();
    if (!main) return;
    main.storageSet("attack_defense_config", JSON.stringify(config));
}

function showAttackDefenseSettings(ctx, msg) {
    let config = getAttackDefenseConfig();
    let info = "⚔️ 攻防系统设置\n\n";
    info += `${config.enabled ? "✅" : "❌"} 系统状态: ${config.enabled ? "已启用" : "已禁用"}\n\n`;
    info += "⚙️ 参数配置:\n";
    info += `· 每日最大发起次数: ${config.maxInitiations || 10}\n`;
    info += `· 每日最大拒绝次数: ${config.maxRefusals || 10}\n`;
    info += `· 单个回合超时(毫秒): ${config.turnTimeout || 3600000}\n`;
    info += `· 默认回合数: ${config.defaultTurns || 10}\n`;
    info += `· 逃脱成功率(%): ${config.escapeRate !== undefined ? config.escapeRate : 30}\n`;
    info += `· 伤害随机性: ${config.damageRandomness ? config.damageRandomness : "无(纯数值)"}\n`;
    info += `· 强制参战模式: ${config.forceParticipate ? "是" : "否"}\n`;
    info += `· 最小参战人数: ${config.minPlayers || 2}\n`;
    info += `· 手动开始模式: ${config.manualStart ? "是" : "否"}\n`;
    info += `\n输入「攻防 设置 参数 值」来修改配置。`;
    seal.replyToSender(ctx, msg, info);
}

let cmd_settings = seal.ext.newCmdItemInfo();
cmd_settings.name = "设置";
cmd_settings.help = "【管理员】查看和管理各系统设置\n。设置               - 显示所有设置类别\n。设置 基础设置      - 查看/修改基础设置\n。设置 互动设置      - 查看/修改互动设置\n。设置 信件设置      - 查看/修改信件系统\n。设置 道具设置      - 查看/修改道具参数";
cmd_settings.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足");

    const subCmd = cmdArgs.getArgN(1);
    const rawMsg = msg.message; // 用于 handleApply 解析批量修改格式

    // 1. 如果是直接输入 "。设置" 或 "。设置 查看"
    if (!subCmd || subCmd === "查看") {
        let info = "🎮 长日系统设置面板\n\n";
        info += "🔹 使用方法：`。设置 类别` 查看，或按照【格式】换行批量修改\n\n";
        info += "可用类别：\n";
        info += "· 。设置 基础设置\n";
        info += "· 。设置 互动设置\n";
        info += "· 。设置 信件设置\n";
        info += "· 。设置 发送信件设置\n";
        info += "· 。设置 公告设置\n";
        info += "· 。设置 心动信设置\n";
        info += "· 。设置 道具设置\n";
        info += "· 。设置 拍卖设置\n";
        info += "· 。设置 群组设置\n";
        info += "· 。设置 礼品店设置\n";
        info += "· 。设置 攻防\n";
        return seal.replyToSender(ctx, msg, info);
    }

    // 2. 路由分发：处理各个子模块的查看与修改
    switch (subCmd) {
        case "基础设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, (n, v) => applyParam(n, v, '基础设置'));
            return showSettings(ctx, msg, '基础设置');
            
        case "互动设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyInteractionParam);
            return showInteractionSettings(ctx, msg);

        case "信件设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyLetterParam);
            return showLetterSettings(ctx, msg);

        case "发送信件设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyDirectLetterParam);
            return showDirectLetterSettings(ctx, msg);

        case "公告设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyPublicParam);
            return showPublicSettings(ctx, msg);

        case "心动信设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyLovemailParam);
            return showLovemailSettings(ctx, msg);

        case "道具设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyItemParam);
            return showItemSettings(ctx, msg);

        case "拍卖设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyAuctionParam);
            return showAuctionSettings(ctx, msg);

        case "群组设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyGroupParam);
            return showGroupSettings(ctx, msg);

        case "礼品店设置":
            if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, applyShopParam);
            return showShopSettings(ctx, msg);

        case "攻防":
            return showAttackDefenseSettings(ctx, msg);

        default:
            return seal.replyToSender(ctx, msg, `❌ 未知的设置类别: ${subCmd}\n请输入 \`。设置\` 查看可用列表`);
    }
};

ext.cmdMap["设置"] = cmd_settings;

// ========================
// 一键初始化指令
// ========================

let cmd_init_settings = seal.ext.newCmdItemInfo();
cmd_init_settings.name = "初始化设置";
cmd_init_settings.help = "【管理员】一键补全缺失的系统默认配置\n使用方法：。初始化设置";
cmd_init_settings.solve = (ctx, msg, argv) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件 changri");

    try {
        // 调用脚本中已有的 ensureDefaults 函数进行补全
        ensureDefaults(main);
        
        let reply = "✅ 系统设置初始化完成！\n";
        reply += "• 已补全缺失的：功能开关、信件配置、目击参数、过期时间等\n";
        reply += "• 注意：此操作仅补全空白项，不会修改你已经设置好的内容";
        
        seal.replyToSender(ctx, msg, reply);
    } catch (e) {
        console.error("初始化失败:", e);
        seal.replyToSender(ctx, msg, `❌ 初始化过程中出现错误: ${e.message}`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["初始化设置"] = cmd_init_settings;

// 启动自动天数轮询
registerAutoDaySystem();