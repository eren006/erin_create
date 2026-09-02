// ==UserScript==
// @name         长日设置
// @author       长日将尽
// @version      1.4.0
// @description  独立的设置控制台（基础、互动、信件、公告）及天数系统、统计报告。所有数据统一存储在主插件 changri 中。
// @timestamp    1778742000
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
// 配置常量
// ========================
const MONITOR_TIMEOUT_DEFAULT_MS = 10800000; // 3 小时
const ADC_TURN_TIMEOUT_DEFAULT_MS = 3600000; // 1 小时
const SETTING_POLL_INTERVAL_MS = 60000;      // 1 分钟

// ========================
// 核心依赖：读取主插件存储
// ========================

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()              { return globalThis.__changriApi || null; }
function mainStorGet(key)      { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val) { const api = getApi(); if (api) api.kvSetRaw(key, val); else console.error(`[长日设置] 主插件未加载，写入丢失: ${key}`); }

// JSON 对象读写：走主插件 kvGet/kvSet（带缓存与损坏容错），JSON key 一律用这两个函数
function mainKvGet(key, def) { const api = getApi(); return api ? api.kvGet(key, def) : def; }
function mainKvSet(key, val) { const api = getApi(); if (api) api.kvSet(key, val); else console.error(`[长日设置] 主插件未加载，写入丢失: ${key}`); }
function isUserAdmin(ctx, msg) { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function mainGetTodayCountsLine(day) { return getApi()?.getTodayActivitySummaryLine(day) ?? ""; }
// 向后兼容：业务逻辑中 getMainExt() 仅作存在性守卫使用
function getMainExt()          { return getApi(); }

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
    const val = mainStorGet(key);
    if (val === null || val === undefined || val.trim() === "") return defaultValue;
    return val;
}

function setMainStorage(key, value) { mainStorSet(key, value); }

// ========================
// 设置配置辅助函数
// ========================

// 目击配置
function getSightingConfig() {
    const defaultConfig = { enabled: false, send_to_all: true, max_reports_per_day: 5, include_ended_meetings: false, time_overlap_threshold: 0.3, trigger_chance: 50 };
    try {
        return { ...defaultConfig, ...mainKvGet("sighting_system_config", {}) };
    } catch (e) { return defaultConfig; }
}

function setSightingConfig(config) {
    mainKvSet("sighting_system_config", config);
}

// 地点系统配置
function getPlaceSystemConfig() {
    const defaultConfig = { enabled: false, require_key_by_default: false };
    try {
        return { ...defaultConfig, ...mainKvGet("place_system_config", {}) };
    } catch (e) { return defaultConfig; }
}

function setPlaceSystemConfig(config) {
    mainKvSet("place_system_config", config);
}

// 攻防系统配置
function getAttackDefenseConfig() {
    const defaultConfig = { enabled: false };
    try {
        if (!getApi()) return defaultConfig;
        const val = mainStorGet("attack_defense_config");
        return val ? { ...defaultConfig, ...JSON.parse(val) } : defaultConfig;
    } catch(e) { return defaultConfig; }
}

function setAttackDefenseConfig(config) { mainKvSet("attack_defense_config", config); }

// DLC 检查
function isDLC(key) {
    try { return mainKvGet('global_feature_toggle', {})[key] === true; }
    catch(e) { return false; }
}

// ========================
// 统一参数系统
// ========================

const settingsConfig = {};

function getUnifiedParamValue(param) {
    if (param.getter) return param.getter();
    if (param.type === 'bool_string') {
        return getMainStorage(param.key, param.default ? "true" : "false") === "true" ? '开启' : '关闭';
    }
    if (param.type === 'string_raw') {
        return getMainStorage(param.key, String(param.default)).replace(/^"|"$/g, '');
    }
    if (param.type === 'routing') {
        try {
            const map = mainKvGet(param.key, {});
            if (!map || !Object.keys(map).length) return '未设置';
            return Object.entries(map).map(([d, g]) => `${d}:${g}`).join('，');
        } catch(e) { return '未设置'; }
    }
    const raw = getMainStorage(param.key, JSON.stringify(param.default));
    try {
        const parsed = JSON.parse(raw);
        if (param.nested) {
            const v = parsed[param.nested];
            if (param.type === 'bool') return (v === true || v === '开启') ? '开启' : '关闭';
            return v !== undefined ? v : param.default;
        }
        if (param.type === 'bool') return (parsed === true || parsed === 'true' || parsed === '开启') ? '开启' : '关闭';
        return parsed;
    } catch(e) { return param.default; }
}

function setUnifiedParamValue(param, val) {
    if (param.setter) { param.setter(val); return; }
    if (param.type === 'bool_string') {
        setMainStorage(param.key, val === '开启' ? "true" : "false");
        return;
    }
    if (param.type === 'string_raw') {
        setMainStorage(param.key, val);
        return;
    }
    if (param.type === 'routing') {
        const pairs = val.split(/[，,\s]+/);
        const map = {};
        for (const pair of pairs) {
            const m = pair.trim().match(/^(D\d+)[：:]\s*(\d+)$/i);
            if (m) map[m[1].toUpperCase()] = m[2];
        }
        mainKvSet(param.key, map);
        return;
    }
    if (param.nested) {
        let cfg = {};
        try { cfg = mainKvGet(param.key, {}); } catch(e) { console.error(`[设置] 读取 ${param.key} 失败:`, e.message); }
        if (param.type === 'bool') cfg[param.nested] = (val === '开启');
        else if (param.type === 'number') cfg[param.nested] = parseInt(val);
        else cfg[param.nested] = val;
        mainKvSet(param.key, cfg);
    } else if (param.type === 'bool') {
        mainKvSet(param.key, val === '开启');
    } else if (param.raw) {
        mainKvSet(param.key, val === '未设置' ? null : val);
    } else {
        setMainStorage(param.key, val);
    }
}

function showPanel(ctx, msg, category, sections) {
    const config = settingsConfig[category];
    if (!config) return seal.replyToSender(ctx, msg, `❌ 未知设置类别: ${category}`);
    const results = [config.title];
    if (sections) {
        for (const sec of sections) {
            results.push(sec.header);
            for (const label of sec.labels) {
                const param = config.params.find(p => p.label === label);
                if (param) results.push(`【${param.label}】${getUnifiedParamValue(param)}`);
            }
        }
    } else {
        for (const param of config.params) {
            results.push(`【${param.label}】${getUnifiedParamValue(param)}`);
        }
    }
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyPanelParam(name, val, category) {
    const config = settingsConfig[category];
    if (!config) return { success: false, message: `❌ 未知类别: ${category}` };
    const param = config.params.find(p => p.label === name);
    if (!param) return { success: false, message: `未知参数：${name}` };
    if (param.validate) {
        const err = param.validate(val);
        if (err) return { success: false, message: `❌ ${err}` };
    }
    setUnifiedParamValue(param, val);
    if (param.type === 'bool' || param.type === 'bool_string') return { success: true, message: `【${name}】已${val}` };
    return { success: true, message: `【${name}】已更新` };
}

// ========================
// 板块1：基础设置
// ========================
settingsConfig['基础设置'] = {
    title: "。设置 基础设置",
    params: [
        { label: '恋综名', key: 'love_show_name', type: 'string', default: '未设置', raw: true },
        { label: '戏群', key: 'song_group_id', type: 'string', default: '未设置', raw: true },
        { label: '后台群', key: 'background_group_id', type: 'string', default: '未设置', raw: true },
        { label: '公告群', key: 'adminAnnounceGroupId', type: 'string', default: '未设置', raw: true },
        { label: '水群', key: 'water_group_id', type: 'string', default: '未设置', raw: true },
        { label: '关系线系统', key: 'relationship_system_enabled', type: 'bool', default: false },
        { label: '关系线上限', key: 'max_relationships_per_user', type: 'string', default: '5' },
        { label: '拉线字数上限', key: 'max_detail_chars', type: 'string', default: '500' },
        { label: '拉线段数上限', key: 'max_detail_count', type: 'string', default: '20' },
        { label: '拉线总字数上限', key: 'max_rel_total_chars', type: 'string', default: '3000' },
        { label: '论坛字数上限', key: 'forum_max_length', type: 'string', default: '500' },
    ]
};

// ========================
// 板块2：功能开关
// ========================
settingsConfig['功能开关'] = {
    title: "。设置 功能开关",
    params: [
        { label: '微信', key: 'global_feature_toggle', nested: 'enable_wechat', type: 'bool', default: false },
        { label: '礼物', key: 'global_feature_toggle', nested: 'enable_general_gift', type: 'bool', default: true },
        { label: '发起邀约', key: 'global_feature_toggle', nested: 'enable_general_appointment', type: 'bool', default: true },
        { label: '寄信', key: 'global_feature_toggle', nested: 'enable_chaos_letter', type: 'bool', default: true },
        { label: '发送信件', key: 'global_feature_toggle', nested: 'enable_direct_letter', type: 'bool', default: false },
        { label: '心愿', key: 'global_feature_toggle', nested: 'enable_wish_system', type: 'bool', default: true },
        { label: '心动信', key: 'global_feature_toggle', nested: 'enable_lovemail', type: 'bool', default: false },
        { label: '地点系统',
          getter: () => getPlaceSystemConfig().enabled ? '开启' : '关闭',
          setter: (v) => { let c = getPlaceSystemConfig(); c.enabled = (v === '开启'); setPlaceSystemConfig(c); } },
        { label: '结戏抽取', key: 'end_game_draw_config', nested: 'enabled', type: 'bool', default: false },
    ]
};

// ========================
// 板块3：互动参数
// ========================
settingsConfig['互动参数'] = {
    title: "。设置 互动参数",
    params: [
        { label: '电话最短所需时长', key: 'appointment_duration_config', nested: 'phone', type: 'number', default: 29 },
        { label: '私密最短所需时长', key: 'appointment_duration_config', nested: 'private', type: 'number', default: 59 },
        { label: '寄信冷却', key: 'mailCooldown', type: 'string', default: '60' },
        { label: '送礼冷却', key: 'giftCooldown', type: 'string', default: '30' },
        { label: '送礼模式', key: 'giftMode', type: 'string', default: '0' },
        { label: '小群过期时间', key: 'group_expire_hours', type: 'string', default: '48' },
        { label: '允许私人房间', key: 'allow_private_rooms', type: 'bool', default: true },
        { label: '允许加入已有私约', key: 'enable_join_existing_appointment', type: 'bool', default: false },
        { label: '自动合并重合私约', key: 'auto_merge_duplicate_private', type: 'bool', default: false },
        { label: '备用群名', key: 'idle_group_name', type: 'string_raw', default: '备用' },
        { label: '时段匹配模式',
          getter: () => { const v = getMainStorage('ts_slot_mode', ''); return v === 'exact' ? '精确' : '累积'; },
          setter: (v) => { mainStorSet('ts_slot_mode', v === '精确' ? 'exact' : 'cumulative'); },
          validate: (v) => { return ['精确', '累积'].includes(v) ? null : '请填写「精确」或「累积」'; },
          note: '精确=只能开当前时段；累积=可开当前及之前所有时段' },
        { label: '超时时间',
          getter: () => { try { return String(Math.round((mainKvGet('monitor_settings', {}).timeout || MONITOR_TIMEOUT_DEFAULT_MS) / 60000)); } catch(e) { return '180'; } },
          setter: (v) => { let c = {}; try { c = mainKvGet('monitor_settings', {}); } catch(e) { console.error("[设置] 读取 monitor_settings 失败:", e.message); } c.timeout = parseInt(v) * 60000; mainKvSet('monitor_settings', c); },
          validate: (v) => { const n = parseInt(v); return (isNaN(n) || n < 1) ? "请填写分钟数（正整数）" : null; } },
        { label: '提醒间隔',
          getter: () => { try { return String(Math.round((mainKvGet('monitor_settings', {}).remind_interval || MONITOR_TIMEOUT_DEFAULT_MS) / 60000)); } catch(e) { return '180'; } },
          setter: (v) => { let c = {}; try { c = mainKvGet('monitor_settings', {}); } catch(e) { console.error("[设置] 读取 monitor_settings 失败:", e.message); } c.remind_interval = parseInt(v) * 60000; mainKvSet('monitor_settings', c); },
          validate: (v) => { const n = parseInt(v); return (isNaN(n) || n < 1) ? "请填写分钟数（正整数）" : null; } },
        { label: '强结发放奖励', key: 'force_end_grant_reward', type: 'bool_string', default: false,
          hint: '开启后「强结私约」「一键强结」也会按正常结戏规则发放奖励，默认关闭（不发放）' },
    ]
};

// ========================
// 板块4：信件与礼品（分节展示）
// ========================
settingsConfig['信件与礼品'] = {
    title: "。设置 信件与礼品",
    params: [
        // 寄信
        { label: '寄信每日上限', key: 'chaos_letter_config', nested: 'dailyLimit', type: 'number', default: 5 },
        { label: '寄信自定义署名', key: 'allow_custom_letter_sign', type: 'bool_string', default: false },
        { label: '寄信混乱送错', key: 'chaos_letter_config', nested: 'misdelivery', type: 'number', default: 0 },
        { label: '寄信混乱涂改', key: 'chaos_letter_config', nested: 'blackoutText', type: 'number', default: 0 },
        { label: '寄信混乱丢失', key: 'chaos_letter_config', nested: 'loseContent', type: 'number', default: 0 },
        { label: '寄信混乱反义', key: 'chaos_letter_config', nested: 'antonymReplace', type: 'number', default: 0 },
        { label: '寄信混乱乱序', key: 'chaos_letter_config', nested: 'reverseOrder', type: 'number', default: 0 },
        { label: '寄信混乱混淆', key: 'chaos_letter_config', nested: 'mistakenSignature', type: 'number', default: 0 },
        { label: '寄信混乱残页', key: 'chaos_letter_config', nested: 'tornPage', type: 'number', default: 0 },
        // 送礼
        { label: '每日礼物上限', key: 'giftDailyLimit', type: 'string', default: '100' },
        { label: '送礼自定义署名', key: 'allow_custom_gift_sign', type: 'bool_string', default: false },
        { label: '掉落曝光隐藏收件人', key: 'drop_hide_receiver', type: 'bool_string', default: false },
        { label: '送礼混乱丢失', key: 'chaos_letter_config', nested: 'giftLost', type: 'number', default: 0 },
        { label: '送礼混乱送错', key: 'chaos_letter_config', nested: 'giftMisdelivery', type: 'number', default: 0 },
        { label: '收到礼物入图鉴', key: 'shop_gift_catalog_on_receive', type: 'bool_string', default: false },
        // 发送信件
        { label: '发送信件每日上限', key: 'direct_letter_daily_limit', type: 'string', default: '5' },
        { label: '发送信件冷却', key: 'direct_letter_cooldown', type: 'string', default: '0' },
        { label: '发送信件最低字数', key: 'direct_letter_min_chars', type: 'string', default: '0' },
        { label: '发送信件赏金', key: 'direct_letter_reward', type: 'string', default: '0' },
        // 心动信
        { label: '心动信送达时间', key: 'lovemail_delivery_time', type: 'string_raw', default: '22:00' },
        { label: '心动信曝光', key: 'lovemail_expose', type: 'bool_string', default: false },
        { label: '心动信曝光概率', key: 'lovemail_expose_chance', type: 'string', default: '10',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 0 || n > 100) return "概率请填 0-100 的整数"; return null; } },
        // 心愿
        { label: '心愿公开提醒', key: 'wish_public_send', type: 'bool_string', default: true },
        { label: '悬赏开关', key: 'wish_bounty_enabled', type: 'bool_string', default: true },
        { label: '心愿同时上限', key: 'wish_max_concurrent', type: 'string', default: '3',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 1) return "必须是 ≥1 的整数"; return null; } },
        { label: '心愿每日发布上限', key: 'wish_daily_post_limit', type: 'string', default: '0',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 0) return "必须是 ≥0 的整数（0=不限）"; return null; } },
        { label: '心愿每日摘取上限', key: 'wish_daily_pick_limit', type: 'string', default: '0',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 0) return "必须是 ≥0 的整数（0=不限）"; return null; } },
        // 礼品店
        { label: '礼品店刷新间隔',
          getter: () => getMainStorage('shop_refresh_hours', '24'),
          setter: (v) => { const h = parseInt(v); setMainStorage('shop_refresh_hours', h.toString()); setMainStorage('shop_personal_display', '{}'); },
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 1) return "必须是 ≥1 的整数（单位：小时）"; return null; } },
        // 道具
        { label: '追踪器成功率', key: 'item_tracker_success_rate', type: 'string', default: '70',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 0 || n > 100) return "必须是 0-100 之间的整数"; return null; } },
        { label: '追踪器显示伙伴', key: 'item_tracker_show_partner', type: 'bool_string', default: true },
        { label: '追踪器时间限制', key: 'item_tracker_time_restrict', type: 'bool_string', default: true },
        { label: '道具施加提醒', key: 'apply_item_notification', type: 'bool_string', default: true },
        { label: '暴露名字概率', key: 'apply_item_expose_rate', type: 'string', default: '0',
          validate: (v) => { const n = parseInt(v); if (isNaN(n) || n < 0 || n > 100) return "必须是 0-100 之间的数字"; return null; } },
        { label: '施加可用时段',
          getter: () => { const v = getMainStorage('apply_item_hours', ''); return (!v || v === '' || v === '""') ? '不限' : v; },
          setter: (v) => { setMainStorage('apply_item_hours', (v === '不限' || v === '全部') ? '' : v); },
          validate: (v) => { if (v === '不限' || v === '全部') return null; if (!/^[\d\-,，]+$/.test(v)) return "格式错误。示例：18-23 或 9-12,14-18"; return null; } },
    ]
};

const PANEL4_SECTIONS = [
    { header: '─── 寄信 ───', labels: ['寄信每日上限','寄信自定义署名','寄信混乱送错','寄信混乱涂改','寄信混乱丢失','寄信混乱反义','寄信混乱乱序','寄信混乱混淆','寄信混乱残页'] },
    { header: '─── 送礼 ───', labels: ['每日礼物上限','送礼自定义署名','掉落曝光隐藏收件人','送礼混乱丢失','送礼混乱送错','收到礼物入图鉴'] },
    { header: '─── 发送信件 ───', labels: ['发送信件每日上限','发送信件冷却','发送信件最低字数','发送信件赏金'] },
    { header: '─── 心动信 ───', labels: ['心动信送达时间','心动信曝光','心动信曝光概率'] },
    { header: '─── 心愿 ───', labels: ['心愿公开提醒','悬赏开关','心愿同时上限','心愿每日发布上限','心愿每日摘取上限'] },
    { header: '─── 礼品店 ───', labels: ['礼品店刷新间隔'] },
    { header: '─── 道具 ───', labels: ['追踪器成功率','追踪器显示伙伴','追踪器时间限制','道具施加提醒','暴露名字概率','施加可用时段'] },
];

// ========================
// 板块5：公告设置
// ========================
settingsConfig['公告设置'] = {
    title: "。设置 公告设置",
    params: [
        { label: '送礼公开发送', key: 'gift_public_send', type: 'bool_string', default: false },
        { label: '寄信公开发送', key: 'letter_public_send', type: 'bool_string', default: false },
        { label: '寄信公开概率', key: 'chaos_letter_config', nested: 'publicChance', type: 'number', default: 50 },
        { label: '礼物公开概率', key: 'giftPublicChance', type: 'string', default: '50' },
        { label: '公告触发频率', key: 'announceFrequency', type: 'string', default: '5' },
    ]
};

settingsConfig['季末报告'] = {
    title: "。设置 季末报告",
    params: [
        { label: '季末报告', key: 'end_season_report_enabled', type: 'bool_string', default: false,
          hint: '开启后结束季度时将向每位玩家个人群发送互动报告，请确保 bot 届时仍在各个人群内' },
    ]
};

// ========================
// DLC 开关面板
// ========================
settingsConfig['DLC'] = {
    title: "。设置 DLC",
    params: [
        { label: '目击报告DLC', key: 'global_feature_toggle', nested: 'dlc_sighting', type: 'bool', default: false },
        { label: '复盘群DLC', key: 'global_feature_toggle', nested: 'dlc_fupan', type: 'bool', default: false },
        { label: '拍卖DLC', key: 'global_feature_toggle', nested: 'dlc_auction', type: 'bool', default: false },
        { label: '攻防DLC', key: 'global_feature_toggle', nested: 'dlc_attack', type: 'bool', default: false },
        { label: '论坛DLC', key: 'global_feature_toggle', nested: 'dlc_forum', type: 'bool', default: false },
        { label: '自动天数DLC', key: 'global_feature_toggle', nested: 'dlc_auto_day', type: 'bool', default: false },
    ]
};

// ========================
// DLC: 目击设置
// ========================
settingsConfig['目击设置'] = {
    title: "。设置 目击设置",
    params: [
        { label: '目击报告',
          getter: () => getSightingConfig().enabled ? '开启' : '关闭',
          setter: (v) => { let c = getSightingConfig(); c.enabled = (v === '开启'); setSightingConfig(c); } },
        { label: '目击每日上限',
          getter: () => String(getSightingConfig().max_reports_per_day),
          setter: (v) => { let c = getSightingConfig(); c.max_reports_per_day = parseInt(v); setSightingConfig(c); },
          validate: (v) => isNaN(parseInt(v)) ? "请填写整数" : null },
        { label: '目击重叠时间判定比例',
          getter: () => String(Math.round(getSightingConfig().time_overlap_threshold * 100)),
          setter: (v) => { let c = getSightingConfig(); c.time_overlap_threshold = parseInt(v) / 100; setSightingConfig(c); },
          validate: (v) => { const n = parseInt(v); return (isNaN(n) || n < 0 || n > 100) ? "请填 0-100 的整数" : null; } },
        { label: '撞见触发概率',
          getter: () => String(getSightingConfig().trigger_chance ?? 50),
          setter: (v) => { let c = getSightingConfig(); c.trigger_chance = parseInt(v); setSightingConfig(c); },
          validate: (v) => { const n = parseInt(v); return (isNaN(n) || n < 0 || n > 100) ? "请填 0-100 的整数" : null; } },
        { label: '目击报告方式',
          getter: () => getSightingConfig().send_to_all ? '双向通知' : '单向通知',
          setter: (v) => { let c = getSightingConfig(); c.send_to_all = (v === '双向通知'); setSightingConfig(c); } },
        { label: '包含已结束',
          getter: () => getSightingConfig().include_ended_meetings ? '是' : '否',
          setter: (v) => { let c = getSightingConfig(); c.include_ended_meetings = (v === '是'); setSightingConfig(c); } },
    ]
};

// ========================
// DLC: 复盘设置
// ========================
settingsConfig['复盘设置'] = {
    title: "。设置 复盘设置",
    params: [
        { label: '复盘群分流', key: 'fupan_routing_enabled', type: 'bool', default: false },
        { label: '复盘群分流群', key: 'fupan_routing_groups', type: 'routing', default: '未设置' },
        { label: '复盘强制结束', key: 'require_fupan_before_end', type: 'bool', default: false },
    ]
};

// ========================
// DLC: 拍卖设置
// ========================
settingsConfig['拍卖设置'] = {
    title: "。设置 拍卖设置",
    params: [
        { label: '允许匿名出价', key: 'auction_allow_anon', type: 'bool_string', default: true },
        { label: '出价播报', key: 'auction_broadcast', type: 'bool_string', default: true },
        { label: '展示最高出价者', key: 'auction_show_top_bidder', type: 'bool_string', default: true },
        { label: '拍卖货币',
          getter: () => {
            const currency = getMainStorage('auction_currency', '金币');
            const main = getMainExt();
            if (!main) return currency;
            const reg = mainKvGet("item_registry", {});
            const currencies = Object.values(reg).filter(r => r.type === "currency").map(r => r.name);
            return currencies.length ? `${currency}（可选：${currencies.join("、")}）` : currency;
          },
          setter: (v) => {
            const attr = v.trim().replace(/（[^）]*）$/, '').trim();
            setMainStorage('auction_currency', attr);
          },
          validate: (v) => {
            const attr = v.trim().replace(/（[^）]*）$/, '').trim();
            if (!attr) return "不能为空";
            const main = getMainExt();
            if (!main) return null;
            const presets = mainKvGet("sys_attr_presets", []);
            const reg = mainKvGet("item_registry", {});
            const isCurrency = Object.values(reg).some(i => i.type === "currency" && i.name === attr);
            if (!presets.includes(attr) && !isCurrency) return `「${attr}」不是已注册的属性或货币。请先注册属性（注册属性 ${attr}）或货币（注册货币 ${attr}*描述）`;
            return null;
          }
        },
    ]
};

// ========================
// DLC: 攻防设置
// ========================
function adcParam(key, defaultVal, type) {
    return {
        getter: () => {
            const c = getAttackDefenseConfig();
            const v = c[key] !== undefined ? c[key] : defaultVal;
            return type === 'bool' ? (v ? '开启' : '关闭') : String(v !== undefined ? v : defaultVal);
        },
        setter: (v) => {
            let c = getAttackDefenseConfig();
            if (type === 'bool') c[key] = (v === '开启');
            else if (type === 'number') c[key] = parseInt(v);
            else c[key] = v;
            setAttackDefenseConfig(c);
        }
    };
}

settingsConfig['攻防设置'] = {
    title: "。设置 攻防设置",
    params: [
        { label: '攻防系统', ...adcParam('enabled', false, 'bool') },
        { label: '每日最大发起次数', ...adcParam('maxInitiations', 10, 'number'),
          validate: (v) => isNaN(parseInt(v)) ? "请填整数" : null },
        { label: '每日最大拒绝次数', ...adcParam('maxRefusals', 10, 'number'),
          validate: (v) => isNaN(parseInt(v)) ? "请填整数" : null },
        { label: '单回合超时(毫秒)', ...adcParam('turnTimeout', ADC_TURN_TIMEOUT_DEFAULT_MS, 'number') },
        { label: '默认回合数', ...adcParam('defaultTurns', 10, 'number') },
        { label: '逃脱成功率', ...adcParam('escapeRate', 30, 'number'),
          validate: (v) => { const n = parseInt(v); return (isNaN(n) || n < 0 || n > 100) ? "请填 0-100 整数" : null; } },
        { label: '伤害随机性', ...adcParam('damageRandomness', '无', 'string') },
        { label: '强制参战模式', ...adcParam('forceParticipate', false, 'bool') },
        { label: '最小参战人数', ...adcParam('minPlayers', 2, 'number') },
        { label: '手动开始模式', ...adcParam('manualStart', false, 'bool') },
    ]
};

// ========================
// 懒加载默认值
// ========================
function ensureDefaults(main) {
    const defaults = {
        "global_feature_toggle": JSON.stringify({
            enable_general_letter: true, enable_general_gift: true, enable_general_appointment: true,
            enable_chaos_letter: true, enable_secret_letter: true, enable_wish_system: true,
            enable_lovemail: false, enable_wechat: false, enable_direct_letter: false,
            dlc_sighting: false, dlc_fupan: false, dlc_auction: false,
            dlc_attack: false, dlc_forum: false, dlc_auto_day: false
        }),
        "chaos_letter_config": JSON.stringify({ misdelivery: 0, blackoutText: 0, loseContent: 0, antonymReplace: 0, reverseOrder: 0, mistakenSignature: 0, tornPage: 0, dailyLimit: 5, publicChance: 50, giftLost: 0, giftMisdelivery: 0 }),
        "sighting_system_config": JSON.stringify({ enabled: false, send_to_all: true, max_reports_per_day: 5, include_ended_meetings: false, time_overlap_threshold: 0.3 }),
        "place_system_config": JSON.stringify({ enabled: false, require_key_by_default: false }),
        "appointment_duration_config": JSON.stringify({ phone: 29, private: 59 }),
        "monitor_settings": JSON.stringify({ enabled: true, timeout: MONITOR_TIMEOUT_DEFAULT_MS, remind_interval: MONITOR_TIMEOUT_DEFAULT_MS, auto_monitor_all_groups: true }),
        // 固定开启项
        "wish_public_send": "true",
        "shop_gift_catalog_on_receive": "true",
        // 群组
        "group_expire_hours": "48",
        "require_fupan_before_end": "false",
        "enable_join_existing_appointment": "false",
        "auto_merge_duplicate_private": "false",
        "relationship_system_enabled": "false",
        "max_relationships_per_user": "5",
        "max_detail_chars": "500",
        // 互动参数
        "mailCooldown": "60",
        "giftCooldown": "30",
        "giftMode": "0",
        "end_game_draw_config": JSON.stringify({ enabled: false }),
        // 信件
        "allow_custom_letter_sign": "false",
        "allow_custom_gift_sign": "false",
        "drop_hide_receiver": "false",
        "giftDailyLimit": "100",
        // 发送信件
        "direct_letter_daily_limit": "5",
        "direct_letter_min_chars": "0",
        "direct_letter_reward": "0",
        // 心动信
        "lovemail_delivery_time": "22:00",
        "lovemail_expose": "false",
        "lovemail_expose_chance": "10",
        "lovemail_default_limit": "3",
        "lovemail_day_limits": "{}",
        // 心愿
        "wish_bounty_enabled": "true",
        "wish_max_concurrent": "3",
        "wish_daily_post_limit": "0",
        "wish_daily_pick_limit": "0",
        // 礼品店
        "shop_refresh_hours": "24",
        // 道具
        "item_tracker_success_rate": "70",
        "item_tracker_show_partner": "true",
        "item_tracker_time_restrict": "true",
        "apply_item_notification": "true",
        "apply_item_expose_rate": "0",
        "apply_item_hours": "",
        // 公告
        "gift_public_send": "false",
        "letter_public_send": "false",
        "giftPublicChance": "50",
        "announceFrequency": "5",
        // DLC 拍卖
        "auction_allow_anon": "true",
        "auction_broadcast": "true",
        "auction_show_top_bidder": "true",
        "auction_currency": "金币",
        "attack_defense_config": JSON.stringify({ enabled: false, maxInitiations: 10, maxRefusals: 10, turnTimeout: ADC_TURN_TIMEOUT_DEFAULT_MS, defaultTurns: 10, escapeRate: 30, forceParticipate: false, minPlayers: 2, manualStart: false }),
        // 系统
        "global_days": "D99",
        "auto_day_reset_enabled": "false",
        "item_pool_mode": "自由池",
    };
    for (const [key, val] of Object.entries(defaults)) {
        const existing = mainStorGet(key);
        if (!existing || existing.trim() === "") mainStorSet(key, val);
    }
    // 迁移：为已存在的 global_feature_toggle 补充新增字段（兼容旧数据）
    try {
        const existingFt = mainStorGet("global_feature_toggle");
        if (existingFt && existingFt.trim()) {
            const ft = JSON.parse(existingFt);
            const newFields = {
                enable_direct_letter: false,
                dlc_sighting: false, dlc_fupan: false, dlc_auction: false,
                dlc_attack: false, dlc_forum: false, dlc_auto_day: false
            };
            let changed = false;
            for (const [k, v] of Object.entries(newFields)) {
                if (ft[k] === undefined) { ft[k] = v; changed = true; }
            }
            if (changed) mainKvSet("global_feature_toggle", ft);
        }
    } catch(e) { console.error("[设置] 迁移 global_feature_toggle 新增字段失败:", e.message); }
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
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const arg1 = argv.getArgN(1);

    let dayLimits = mainKvGet("lovemail_day_limits", {});
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

    const currentLimits = mainKvGet("lovemail_day_limits", {});
    Object.assign(currentLimits, newLimits);
    mainKvSet("lovemail_day_limits", currentLimits);

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
        "电话": parseInt(mainStorGet("a_meetingCount_call") || "0"),
        "私密": parseInt(mainStorGet("a_meetingCount_private") || "0"),
        "寄信": parseInt(mainStorGet("a_meetingCount_chaosletter") || "0"),
        "发送信件": parseInt(mainStorGet("a_meetingCount_directletter") || "0"),
        "心动信": parseInt(mainStorGet("a_meetingCount_lovemail") || "0"),
        "礼物": parseInt(mainStorGet("a_meetingCount_gift") || "0"),
        "心愿": parseInt(mainStorGet("a_meetingCount_wish") || "0"),
        "官约": parseInt(mainStorGet("a_meetingCount_official") || "0")
    };

    const groupList = mainKvGet("group", []);
    const totalGroups = groupList.length;
    const occupiedGroups = groupList.filter(g => g.endsWith("_占用")).length;
    const availableGroups = totalGroups - occupiedGroups;

    const a_private_group = mainKvGet("a_private_group", {});
    const playerCount = a_private_group[platform] ? Object.keys(a_private_group[platform]).length : 0;
    const loveshow_name = mainStorGet("love_show_name") || "未设置";

    const appointmentList = mainKvGet("appointmentList", []);
    const pendingRequests = appointmentList.length;

    const b_MultiGroupRequest = mainKvGet("b_MultiGroupRequest", {});
    const multiRequests = Object.keys(b_MultiGroupRequest).length;

    const b_confirmedSchedule = mainKvGet("b_confirmedSchedule", {});
    let activeMeetings = 0;
    for (const key in b_confirmedSchedule) {
        activeMeetings += b_confirmedSchedule[key].filter(item => item.status === "active").length;
    }

    const wishPool = mainKvGet("a_wishPool", []);
    const wishCount = wishPool.length;

    const lovemailPool = mainKvGet("lovemail_pool", []);
    const lovemailCount = lovemailPool.length;

    const groupExpireInfo = mainKvGet("group_expire_info", {});
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

    let backgroundGroupId = mainKvGet("background_group_id", null);
    const fupanRouting = mainStorGet("fupan_routing_enabled") === "true";
    if (fupanRouting) {
        try {
            const routingMap = mainKvGet("fupan_routing_groups", {});
            const firstId = Object.values(routingMap)[0];
            if (firstId) backgroundGroupId = firstId;
        } catch (e) { console.error("[设置] 读取 fupan_routing_groups 失败:", e.message); }
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅骰主或管理员可用。"), seal.ext.newCmdExecuteResult(true);
    let day = args.getArgN(1);
    if (!day || !/^D\d+$/i.test(day)) return seal.replyToSender(ctx, msg, "⚠️ 请输入正确的天数格式，例如：。设置天数 D1"), seal.ext.newCmdExecuteResult(true);
    day = day.toUpperCase();

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件");

    const prev = mainStorGet("global_days") || "未设置";
    const platform = msg.platform;

    // ★ 第一步：生成报告（在清空前，基于当前数据）
    const report = generateStatisticsReport(ctx, msg, day, prev);

    // ★ 第二步：清空所有计数
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official","a_meetingCount_lovemail","a_meetingCount_directletter","a_meetingCount_relation"].forEach(k => mainStorSet(k, "0"));
    const groups = mainKvGet("a_private_group", {})[platform];
    if (groups) {
        // 新结构：key 是 uid，groups[uid][0] 是 roleName
        for (let uid in groups) {
            mainStorSet(`chaos_letter_daily_${platform}:${uid}_${day}`, "0");
        }
    }
    mainStorSet("a_wishPool", "[]");
    mainStorSet("lovemail_pool", "[]");

    // ★ 第三步：设置新天数
    mainStorSet("global_days", day);
    mainStorSet("auto_day_last_reset", "0");

    let resp = `✅ 已将全局天数从 ${prev} 设置为：${day}`;
    resp += "\n✅ 已自动清空所有会面计数、每日信件计数、寄信限制、心愿池和心动信池";

    // ★ 第四步：发送报告
    const announceGid = mainKvGet("adminAnnounceGroupId", null);
    if (announceGid) {
        const todayLine = prev !== "未设置" ? `\n${mainGetTodayCountsLine(prev)}` : "";
        sendTextToGroup(platform, announceGid, `📜 全局天数已从 ${prev} 切换到 ${day}（所有计数已自动重置）${todayLine}`);
    }
    const bgGid = mainKvGet("background_group_id", null);
    const fupanRoutingForReport = mainStorGet("fupan_routing_enabled") === "true";
    let reportTarget = bgGid;
    if (fupanRoutingForReport) {
        try {
            const rm = mainKvGet("fupan_routing_groups", {});
            const firstId = Object.values(rm)[0];
            if (firstId) reportTarget = firstId;
        } catch (e) { console.error("[设置] 读取 fupan_routing_groups 失败:", e.message); }
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

    const prev = mainStorGet("global_days") || "未设置";
    const mockMsg = { platform: "QQ" };

    // ★ 第一步：生成报告（在清空前，基于当前数据）
    const report = generateStatisticsReport(null, mockMsg, newDay, prev);

    // ★ 第二步：清空所有计数
    ["a_meetingCount_call","a_meetingCount_private","a_meetingCount_letter","a_meetingCount_gift","a_meetingCount_wish","a_meetingCount_chaosletter","a_meetingCount_secretletter","a_meetingCount_official","a_meetingCount_lovemail","a_meetingCount_directletter","a_meetingCount_relation"].forEach(k => mainStorSet(k, "0"));
    const groups = mainKvGet("a_private_group", {})["QQ"];
    if (groups) {
        // 新结构：key 是 uid，groups[uid][0] 是 roleName
        for (let uid in groups) {
            mainStorSet(`chaos_letter_daily_QQ:${uid}_${newDay}`, "0");
        }
    }
    mainStorSet("a_wishPool", "[]");
    mainStorSet("lovemail_pool", "[]");

    // ★ 第三步：设置新天数
    mainStorSet("global_days", newDay);

    // ★ 第四步：发送报告
    const announceGid = mainKvGet("adminAnnounceGroupId", null);
    if (announceGid) {
        const todayLine = prev !== "未设置" ? `\n${mainGetTodayCountsLine(prev)}` : "";
        sendTextToGroup("QQ", announceGid, `📜 自动天数推进：${prev} → ${newDay}（所有计数已清空）${todayLine}`);
    }
    const bgGid = mainKvGet("background_group_id", null);
    if (bgGid) sendStatisticsToBackgroundGroup(null, mockMsg, newDay, report, true);

    console.log(`[自动天数] 已从 ${prev} 推进至 ${newDay}，并清空所有计数`);
}

function registerAutoDaySystem() {
    if (autoDayTimer) clearInterval(autoDayTimer);
    autoDayTimer = setInterval(() => {
        const main = getMainExt();
        if (!main) return;
        if (!isDLC('dlc_auto_day')) return;
        const now = new Date();
        if (now.getHours() === 23 && now.getMinutes() === 59) {
            const todayKey = `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
            if (mainStorGet("auto_day_last_reset") === todayKey) return;
            let cur = mainStorGet("global_days") || "D0";
            let m = cur.match(/^D(\d+)$/i);
            if (!m) { cur = "D0"; m = ["D0","0"]; }
            performAutoDayReset(`D${parseInt(m[1])+1}`, now);
            mainStorSet("auto_day_last_reset", todayKey);
        }
    }, SETTING_POLL_INTERVAL_MS);
}

// ========================
// 自动天数开关指令
// ========================

function setDLC(key, value) {
    try {
        const ft = mainKvGet('global_feature_toggle', {});
        ft[key] = value;
        mainKvSet('global_feature_toggle', ft);
    } catch(e) { console.error(`[设置] setDLC(${key}) 保存失败:`, e.message); }
}

let cmd_enable_auto_day = seal.ext.newCmdItemInfo();
cmd_enable_auto_day.name = "开启自动天数";
cmd_enable_auto_day.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    const main = getMainExt();
    if (main) {
        setDLC('dlc_auto_day', true);
        mainStorSet("auto_day_reset_enabled", "true");
    }
    seal.replyToSender(ctx, msg, "✅ 自动天数推进已开启，每天 23:59 自动将天数 +1 并清空计数");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开启自动天数"] = cmd_enable_auto_day;

let cmd_disable_auto_day = seal.ext.newCmdItemInfo();
cmd_disable_auto_day.name = "关闭自动天数";
cmd_disable_auto_day.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    const main = getMainExt();
    if (main) {
        setDLC('dlc_auto_day', false);
        mainStorSet("auto_day_reset_enabled", "false");
    }
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
地点池 1
池 金币 30 60 TJ00 1 40
or
字数 >= 800
奖励 金币 40
or
字数 >= 300
奖励 金币 15

地点池 N：发放结戏群地点同名抽取池的 N 次机会，池不存在时跳过并提示`;

cmd_end_bonus.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const main = getMainExt();
    if (!main) return seal.ext.newCmdExecuteResult(true);

    const getTemplates = () => mainKvGet("end_game_bonus_templates", []);
    const saveTemplates = (t) => mainKvSet("end_game_bonus_templates", t);
    const findTemplate = (templates, name) => templates.find(t => t.name === name);


    const detectTargetType = (target) => {
        const reg = mainKvGet("item_registry", {});
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
• 已注册属性（属性名）
• 地点池（写法：地点池 N，发放结戏群地点同名抽取池的 N 次抽取机会；若该池不存在则跳过并提示）`);
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
                    } else if (r.type === "location_draw") {
                        lines.push(`【地点池抽取】×${r.amount}（结戏群地点同名池）`);
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

        const allLines = (msg.message || "").split(/\r?\n/).map(l => l.trim()).filter(Boolean);
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

            // 地点池 N
            if (line.startsWith("地点池 ")) {
                const amount = parseInt(line.slice(4).trim());
                if (isNaN(amount) || amount < 1) { errors.push(`地点池次数需为正整数：${line}`); continue; }
                currentBlock.rewards.push({ type: "location_draw", amount });
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
// 设置指令
// ========================

let cmd_settings = seal.ext.newCmdItemInfo();
cmd_settings.name = "设置";
cmd_settings.help = `【管理员】查看和管理各系统设置
。设置               - 显示所有设置类别
。设置 基础设置      - 群组配置、关系线
。设置 功能开关      - 所有功能 开启/关闭
。设置 互动参数      - 时长、冷却、私约参数
。设置 信件与礼品    - 信件、送礼、心动信、心愿、礼品店、道具
。设置 公告设置      - 公开发送、公告频率
。设置 DLC          - 管理 DLC 模块开关`;

cmd_settings.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const subCmd = cmdArgs.getArgN(1);
    const rawMsg = msg.message || "";

    if (!subCmd || subCmd === "查看") {
        let info = "🎮 长日系统设置面板\n\n";
        info += "🔹 查看：。设置 类别\n🔹 修改：。设置 类别（换行）【参数名】值\n\n";
        info += "【基础包】\n";
        info += "· 。设置 基础设置\n";
        info += "· 。设置 功能开关\n";
        info += "· 。设置 互动参数\n";
        info += "· 。设置 信件与礼品\n";
        info += "· 。设置 公告设置\n";
        info += "\n【DLC 管理】\n";
        info += "· 。设置 DLC\n";
        if (isDLC('dlc_sighting')) info += "· 。设置 目击设置\n";
        if (isDLC('dlc_fupan')) info += "· 。设置 复盘设置\n";
        if (isDLC('dlc_auction')) info += "· 。设置 拍卖设置\n";
        if (isDLC('dlc_attack')) info += "· 。设置 攻防设置\n";
        return seal.replyToSender(ctx, msg, info);
    }

    // 别名映射（兼容旧指令名）
    const aliases = {
        '基础': '基础设置',
        '功能': '功能开关',
        '互动': '互动参数', '互动设置': '互动参数',
        '信件': '信件与礼品', '信件设置': '信件与礼品',
        '礼品': '信件与礼品', '发送信件': '信件与礼品',
        '公告': '公告设置',
        '目击': '目击设置',
        '复盘': '复盘设置',
        '拍卖': '拍卖设置',
        '攻防': '攻防设置',
        // 旧板块名兼容
        '道具': '信件与礼品', '道具设置': '信件与礼品',
        '礼品店': '信件与礼品', '礼品店设置': '信件与礼品',
        '心动信': '信件与礼品', '心动信设置': '信件与礼品',
        '心愿': '信件与礼品', '心愿设置': '信件与礼品',
        '发送信件设置': '信件与礼品',
        '群组': '互动参数', '群组设置': '互动参数',
    };
    const resolved = aliases[subCmd] || subCmd;

    // DLC 板块门控
    const dlcGate = { '目击设置': 'dlc_sighting', '复盘设置': 'dlc_fupan', '拍卖设置': 'dlc_auction', '攻防设置': 'dlc_attack' };
    if (dlcGate[resolved] && !isDLC(dlcGate[resolved])) {
        return seal.replyToSender(ctx, msg, `❌ 「${resolved}」是 DLC 功能，请先在「。设置 DLC」中开启对应选项`);
    }

    if (!settingsConfig[resolved]) {
        return seal.replyToSender(ctx, msg, `❌ 未知的设置类别: ${subCmd}\n请输入「。设置」查看可用列表`);
    }

    if (resolved === '信件与礼品') {
        if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, (n, v) => applyPanelParam(n, v, resolved));
        return showPanel(ctx, msg, resolved, PANEL4_SECTIONS);
    }

    if (rawMsg.includes('\n')) return handleApply(ctx, msg, rawMsg, (n, v) => applyPanelParam(n, v, resolved));
    return showPanel(ctx, msg, resolved);
};

ext.cmdMap["设置"] = cmd_settings;

// ========================
// 从存档服务器拉取配置（供初始化和同步共用）
// ========================
async function fetchServerConfig() {
    const main = getMainExt();
    if (!main) return null;
    const base = (seal.ext.getStringConfig(main.ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main.ext, "RP存档Token") || "";
    if (!base) return null;
    try {
        const resp = await fetch(base + "/api/config", {
            headers: { "X-Archive-Token": token }
        });
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        return null;
    }
}

// ========================
// 一键初始化指令（先尝试拉取 UI 配置，拉不到则用内置默认值）
// ========================

let cmd_init_settings = seal.ext.newCmdItemInfo();
cmd_init_settings.name = "初始化设置";
cmd_init_settings.help = "【管理员】一键补全缺失的系统默认配置（优先从存档 UI 拉取）\n使用方法：。初始化设置";
cmd_init_settings.solve = async (ctx, msg, argv) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件 changri");

    try {
        const serverConfig = await fetchServerConfig();

        if (serverConfig) {
            // 只补空白项：server config 作为默认值，不覆盖已有设置
            for (const [key, value] of Object.entries(serverConfig)) {
                const existing = mainStorGet(key);
                if (!existing || existing.trim() === "") {
                    mainStorSet(key, String(value));
                }
            }
            ensureDefaults(main); // 补 server config 未覆盖的项
            seal.replyToSender(ctx, msg,
                `✅ 初始化完成（已从 UI 配置拉取 ${Object.keys(serverConfig).length} 项）\n` +
                "• 仅补全空白项，已有设置不受影响\n" +
                "• 如需强制覆盖所有设置，请使用「。拉取全部」"
            );
        } else {
            ensureDefaults(main);
            seal.replyToSender(ctx, msg,
                "✅ 初始化完成（存档服务器未配置或无法连接，已使用内置默认值）\n" +
                "• 仅补全空白项，已有设置不受影响"
            );
        }
    } catch (e) {
        console.error("初始化失败:", e);
        seal.replyToSender(ctx, msg, `❌ 初始化过程中出现错误: ${e.message}`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["初始化设置"] = cmd_init_settings;

// 推送全部 使用的配置键列表
const SYNC_DIRECT_KEYS = [
    "item_registry", "rpg_attr_defs", "sys_attr_presets",
    "global_days", "auto_day_reset_enabled", "item_pool_mode",
    "adminAnnounceGroupId", "song_group_id", "background_group_id", "water_group_id",
    "fupan_routing_enabled", "fupan_routing_groups",
    "enable_join_existing_appointment", "require_fupan_before_end", "group_expire_hours", "appointment_coin_cost", "idle_group_name",
    "force_end_grant_reward",
    "mailCooldown", "allow_custom_letter_sign", "letter_public_send",
    "giftCooldown", "gift_public_send", "giftPublicChance", "giftDailyLimit",
    "allow_custom_gift_sign", "drop_hide_receiver",
    "shop_refresh_hours", "allow_private_rooms", "announceFrequency",
    "lovemail_default_limit", "lovemail_day_limits", "lovemail_delivery_time", "lovemail_expose", "lovemail_expose_chance",
    "direct_letter_daily_limit", "direct_letter_min_chars", "direct_letter_reward", "direct_letter_cooldown",
    "wish_public_send", "wish_bounty_enabled", "wish_max_concurrent",
    "wish_daily_post_limit", "wish_daily_pick_limit", "wish_coin_cost",
    "relationship_system_enabled", "max_relationships_per_user", "max_detail_chars", "max_detail_count", "max_rel_total_chars",
    "item_tracker_success_rate", "item_tracker_show_partner", "item_tracker_time_restrict",
    "apply_item_notification", "apply_item_expose_rate", "apply_item_hours",
    "shop_gift_catalog_on_receive",
    "auction_allow_anon", "auction_broadcast", "auction_show_top_bidder", "auction_currency",
    "stakeout_allow_solo",
    "ts_slot_mode",
];

// json_parent 键 → 子字段列表（与 CONFIG_SCHEMA json_parent 对应）
const SYNC_JSON_PARENT_KEYS = {
    "global_feature_toggle": [
        "enable_general_gift", "enable_general_appointment",
        "enable_chaos_letter", "enable_wish_system", "enable_lovemail",
        "enable_wechat", "enable_direct_letter",
        "dlc_sighting", "dlc_fupan", "dlc_auction", "dlc_attack",
        "dlc_forum", "dlc_auto_day", "dlc_moments",
        "dlc_stakeout", "dlc_battle_appt", "dlc_trade"
    ],
    "chaos_letter_config": [
        "misdelivery", "blackoutText", "loseContent", "antonymReplace",
        "reverseOrder", "mistakenSignature", "tornPage",
        "dailyLimit", "publicChance", "publicShowEffect", "giftLost", "giftMisdelivery"
    ],
    "appointment_duration_config": ["phone", "private", "stakeout"],
    "sighting_system_config": [
        "enabled", "send_to_all", "max_reports_per_day",
        "include_ended_meetings", "time_overlap_threshold", "trigger_chance"
    ],
    "place_system_config": ["enabled", "require_key_by_default"],
    "monitor_settings": [
        "enabled", "auto_monitor_all_groups",
        "min_words_phone", "min_words_private", "min_words_wish", "min_words_official",
        "timeout_phone", "timeout_private", "timeout_wish", "timeout_official"
    ],
    "custom_type_labels": ["私密", "电话", "官约", "微信", "心愿"],
};


// ========================
// 推送全部（bot → 网页端，一键全推）
// 包含：配置设置、物品/装备注册表、结戏模版、池子、礼品库、待上载物品/装备
// ========================
let cmd_push_all = seal.ext.newCmdItemInfo();
cmd_push_all.name = "推送全部";
cmd_push_all.help = "【管理员】将机器人所有数据一次性推送到存档网页端\n使用方法：。推送全部";
cmd_push_all.solve = async (ctx, msg, argv) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件 changri");

    const base  = (seal.ext.getStringConfig(main.ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main.ext, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址");

    seal.replyToSender(ctx, msg, "⏳ 正在推送所有数据到网页端…");

    const authHeaders = { "Content-Type": "application/json", "X-Archive-Token": token };
    const payload = {};

    // 1. 直存配置键
    for (const key of SYNC_DIRECT_KEYS) {
        const val = mainStorGet(key);
        if (val !== null && val !== undefined && val !== "") payload[key] = val;
    }

    // 2. json_parent 展开键
    // 注意：monitor_settings 里的 timeout_phone/private/wish/official 在机器人侧是「毫秒」，
    // 但网页端 site_config 里对应字段是「小时」（assemble_bot_config 拉取时会 ×3600000 换算成毫秒）。
    // 推送时必须换算回小时，否则下次「拉取全部/初始化设置」会再乘一次 3600000，多次推拉后超时时长会指数级爆炸。
    const MS_TO_HOUR_KEYS = { monitor_settings: ["timeout_phone", "timeout_private", "timeout_wish", "timeout_official"] };
    for (const [parent, subKeys] of Object.entries(SYNC_JSON_PARENT_KEYS)) {
        const raw = mainStorGet(parent);
        if (!raw) continue;
        try {
            const obj = JSON.parse(raw);
            const hourKeys = MS_TO_HOUR_KEYS[parent] || [];
            for (const subKey of subKeys) {
                if (obj[subKey] === undefined) continue;
                const val = hourKeys.includes(subKey) ? (Number(obj[subKey]) || 0) / 3600000 : obj[subKey];
                payload[`${parent}__${subKey}`] = String(val);
            }
        } catch (e) { console.warn(`[推送全部] 解析 ${parent} 失败: ${e.message}`); }
    }

    // 3. blob 键
    const PUSH_ALL_BLOB_KEYS = [
        "end_game_bonus_templates", "end_game_draw_config",
        "equipment_registry", "equipment_slots", "equipment_slot_names",
        "trade_whitelist", "preset_gifts",
        "private_appointment_aliases", "sms_aliases",
        "available_places", "place_keys",
        "custom_message_templates",
        "craft_recipes",
        "skill_defs", "battle_attrs", "player_skills",
        "attack_defense_config",
        "shop_listings", "market_config",
    ];
    for (const key of PUSH_ALL_BLOB_KEYS) {
        const val = mainStorGet(key);
        if (val !== null && val !== undefined && val !== "") payload[key] = val;
    }

    // ── 推送配置+注册表+模版+礼品库 ──────────────────────────────────────────
    let configSynced = 0;
    try {
        const resp = await fetch(`${base}/api/sync_config`, {
            method: "POST",
            headers: authHeaders,
            body: JSON.stringify(payload)
        });
        if (resp.status === 401 || resp.status === 403) {
            return seal.replyToSender(ctx, msg, "❌ Token 无效或未配置，请检查插件设置里的「RP存档Token」");
        }
        if (!resp.ok) throw new Error(`sync_config 返回 ${resp.status}`);
        const result = await resp.json();
        configSynced = result.synced || Object.keys(payload).length;
    } catch (e) {
        return seal.replyToSender(ctx, msg, `❌ 配置推送失败：${e.message}`);
    }

    // ── 推送池子 ─────────────────────────────────────────────────────────────
    let poolCount = 0;
    let poolErr = null;
    try {
        let poolDefs = {}, poolDrawCfg = { total: null, pools: {} };
        try { poolDefs    = mainKvGet("pool_definitions", {}); } catch(e) { console.error("[设置] 推送配置读取 pool_definitions 失败:", e.message); }
        try { poolDrawCfg = mainKvGet("pool_draw_config", {}); } catch(e) { console.error("[设置] 推送配置读取 pool_draw_config 失败:", e.message); }
        poolCount = Object.keys(poolDefs).length;
        const resp = await fetch(`${base}/api/pool_config`, {
            method: "POST",
            headers: authHeaders,
            body: JSON.stringify({ pool_definitions: poolDefs, pool_draw_config: poolDrawCfg })
        });
        if (!resp.ok) throw new Error(`pool_config 返回 ${resp.status}`);
    } catch (e) { poolErr = e.message; }

    // ── 推送拍卖快照 ─────────────────────────────────────────────────────────
    let auctionErr = null;
    let auctionCount = 0;
    try {
        const auctionData = mainKvGet("auction_items", {});
        auctionCount = Object.keys(auctionData).length;
        const resp = await fetch(`${base}/api/auction_snapshot`, {
            method: "POST",
            headers: authHeaders,
            body: JSON.stringify({ snapshot: auctionData })
        });
        if (!resp.ok) throw new Error(`auction_snapshot 返回 ${resp.status}`);
    } catch (e) { auctionErr = e.message; }

    // ── 汇报结果 ─────────────────────────────────────────────────────────────
    let msg_lines = [`✅ 推送全部完成！`];
    msg_lines.push(`📋 配置+注册表+模版：${configSynced} 项`);
    msg_lines.push(poolErr ? `⚠️ 池子推送失败：${poolErr}` : `🎲 池子：${poolCount} 个`);
    msg_lines.push(auctionErr ? `⚠️ 拍卖快照推送失败：${auctionErr}` : `🔨 拍卖快照：${auctionCount} 件`);
    seal.replyToSender(ctx, msg, msg_lines.join("\n"));

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["推送全部"] = cmd_push_all;


// ========================
// 拉取全部（网页端 → bot，数据合流与落地）
// ========================
let cmd_pull_all = seal.ext.newCmdItemInfo();
cmd_pull_all.name = "拉取全部";
cmd_pull_all.help = "【管理员】将存档网页端所有数据一次性拉取到机器人\n使用方法：。拉取全部";
cmd_pull_all.solve = async (ctx, msg, argv) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件 changri");

    const base  = (seal.ext.getStringConfig(main.ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main.ext, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址（在海豹插件设置里填写）");

    seal.replyToSender(ctx, msg, "⏳ 正在从网页端拉取所有数据…");

    const headers = { "X-Archive-Token": token };

    // ── 1. 拉取并重组基础配置 ─────────────────────────────────────────────────
    let configCount = 0;
    try {
        const resp = await fetch(`${base}/api/config`, { headers });
        if (!resp.ok) throw new Error(`/api/config 返回 ${resp.status}`);
        const config = await resp.json();

        // 用于存放逆向组装的 JSON Parent 对象
        const reconstructedParents = {};

        for (const [key, value] of Object.entries(config)) {
            if (key.includes("__")) {
                // 处理形如 parentKey__subKey 的扁平化键，重新封装为 JSON
                const [parent, subKey] = key.split("__");
                if (!reconstructedParents[parent]) {
                    try {
                        reconstructedParents[parent] = mainKvGet(parent, {});
                    } catch(e) { reconstructedParents[parent] = {}; }
                }
                reconstructedParents[parent][subKey] = value;
            } else {
                // 普通直存键直接写入
                mainStorSet(key, String(value));
                configCount++;
            }
        }

        // 把重新组装好的 JSON 父母键写入存储
        for (const [parent, obj] of Object.entries(reconstructedParents)) {
            mainKvSet(parent, obj);
            configCount++;
        }
    } catch (e) {
        return seal.replyToSender(ctx, msg, `❌ 基础配置拉取失败：${e.message}`);
    }

    // ── 2. 处理「待上载物品」（从网页端拉取并合并入本地注册表） ───────────────────────
    let pendingMerged = 0;
    try {
        const pendingResp = await fetch(`${base}/api/pending_items`, { headers });
        if (pendingResp.ok) {
            const pendingData = await pendingResp.json();
            const pending = pendingData.pending || [];
            if (pending.length > 0) {
                const reg = mainKvGet("item_registry", {});
                for (const p of pending) {
                    if (Object.values(reg).some(r => r.name === p.name)) continue; // 名字去重
                    
                    const codePrefix = p.type === "interact" ? "INTER_" : "ITEM_";
                    let code = null;
                    for (let d = 1; d < 10000; d++) {
                        const c = codePrefix + String(d).padStart(3, "0");
                        if (!reg[c]) { code = c; break; }
                    }
                    if (!code) continue;

                    reg[code] = { 
                        code, name: p.name, desc: p.desc, type: p.type,
                        maxUses: p.maxUses, attrs: p.attrs, price: 0, canResell: p.canResell,
                        ...(p.durability != null ? { durability: p.durability } : {}) 
                    };
                    pendingMerged++;
                }
                mainKvSet("item_registry", reg);
                // 告诉网页端：这些待上载数据我已经成功合流并落地了，可以清空了
                await fetch(`${base}/api/pending_items`, { method: "DELETE", headers });
            }
        }
    } catch (e) { console.warn(`[拉取全部] 处理网页待上载物品失败: ${e.message}`); }

    // ── 3. 处理「待上载装备」（从网页端拉取并合并入本地注册表） ───────────────────────
    let equipPendingMerged = 0;
    try {
        const equipPendingResp = await fetch(`${base}/api/pending_equips`, { headers });
        if (equipPendingResp.ok) {
            const equipPendingData = await equipPendingResp.json();
            const equipPending = equipPendingData.pending || [];
            if (equipPending.length > 0) {
                const equipReg = mainKvGet("equipment_registry", {});
                for (const p of equipPending) {
                    if (Object.values(equipReg).some(r => r.name === p.name)) continue;
                    
                    let code = null;
                    for (let d = 1; d < 10000; d++) {
                        const c = "EQUIP_" + String(d).padStart(3, "0");
                        if (!equipReg[c]) { code = c; break; }
                    }
                    if (!code) continue;

                    const baseAttrs = {};
                    if (p.baseAttrs) {
                        p.baseAttrs.split(",").forEach(seg => {
                            const m = seg.trim().match(/^(.+?)([+-]\d+)$/);
                            if (m) baseAttrs[m[1]] = parseInt(m[2]);
                        });
                    }
                    equipReg[code] = { 
                        code, name: p.name, desc: p.desc, type: "equipment",
                        slot: p.slot, baseAttrs,
                        ...(p.durability != null ? { durability: p.durability } : {}) 
                    };
                    equipPendingMerged++;
                }
                mainKvSet("equipment_registry", equipReg);
                // 告诉网页端：清除已拉取的待上载装备
                await fetch(`${base}/api/pending_equips`, { method: "DELETE", headers });
            }
        }
    } catch (e) { console.warn(`[拉取全部] 处理网页待注册装备失败: ${e.message}`); }

    // ── 3.5 若合流了新物品/装备，把带编号的完整注册表回写网页端 ─────────────────
    // 编号由机器人分配，之前需要再手动发一次「推送全部」网页才能显示新编号；
    // 这里在同一条「拉取全部」里自动回写，避免两步操作。
    if (pendingMerged > 0 || equipPendingMerged > 0) {
        try {
            const writeback = {};
            if (pendingMerged > 0)      writeback.item_registry      = mainStorGet("item_registry");
            if (equipPendingMerged > 0) writeback.equipment_registry = mainStorGet("equipment_registry");
            await fetch(`${base}/api/sync_config`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify(writeback)
            });
        } catch (e) { console.warn(`[拉取全部] 回写注册表到网页端失败: ${e.message}`); }
    }

    // ── 4. 拉取池子配置 ─────────────────────────────────────────────────────────
    let poolCount = 0;
    let poolErr = null;
    try {
        const resp = await fetch(`${base}/api/pool_config`, { headers });
        if (!resp.ok) throw new Error(`/api/pool_config 返回 ${resp.status}`);
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "未知错误");
        const defs = data.pool_definitions || {};
        const cfg  = data.pool_draw_config  || { total: null, pools: {} };
        mainKvSet("pool_definitions", defs);
        mainKvSet("pool_draw_config", cfg);
        poolCount = Object.keys(defs).length;
    } catch (e) { poolErr = e.message; }

    // ── 5. 拉取拍卖队列 ─────────────────────────────────────────────────────────
    let auctionActivated = 0;
    let auctionFailed = 0;
    let auctionErr = null;
    try {
        const resp = await fetch(`${base}/api/auction_queue`, { headers });
        if (!resp.ok) throw new Error(`auction_queue 返回 ${resp.status}`);
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || "未知错误");
        const queue = data.queue || [];
        if (queue.length > 0) {
            let auctionData = {};
            try { auctionData = mainKvGet("auction_items", {}); } catch(e) { console.error("[设置] 拍卖队列同步读取 auction_items 失败:", e.message); }
            let reg = {};
            try { reg = mainKvGet("item_registry", {}); } catch(e) { console.error("[设置] 拍卖队列同步读取 item_registry 失败:", e.message); }
            
            const now = Date.now();
            
            // 【安全修复】寻找当前本地已有的最大数字ID，防止覆盖已有拍卖
            let maxIdNum = 0;
            Object.keys(auctionData).forEach(k => {
                const num = parseInt(k.replace("A", ""));
                if (!isNaN(num) && num > maxIdNum) maxIdNum = num;
            });
            let nextIdNum = maxIdNum + 1;

            for (const item of queue) {
                const regItem = Object.values(reg).find(r => r.code === item.code);
                if (!regItem) { auctionFailed++; continue; }
                
                const id = `A${String(nextIdNum).padStart(3, "0")}`;
                nextIdNum++;
                
                auctionData[id] = {
                    id, code: regItem.code, name: regItem.name, desc: regItem.desc || "",
                    startPrice: item.startPrice, minIncrement: item.minIncrement,
                    durationHours: item.durationHours, expireHours: item.expireHours || null,
                    canResell: regItem.allowSecondhand === true,
                    startTime: now, endTime: now + item.durationHours * 3600 * 1000,
                    bids: [], status: "active", winner: null
                };
                auctionActivated++;
            }
            if (auctionActivated > 0) mainKvSet("auction_items", auctionData);
            await fetch(`${base}/api/auction_queue`, { method: "DELETE", headers });
        }
    } catch (e) { auctionErr = e.message; }

    // ── 6. 还原拍卖快照（仅当本地 auction_items 为空时） ──────────────────────
    let auctionSnapshotRestored = 0;
    let auctionSnapshotErr = null;
    try {
        const localAuction = mainStorGet("auction_items");
        const localEmpty = !localAuction || Object.keys(JSON.parse(localAuction || "{}")).length === 0;
        if (localEmpty) {
            const snapResp = await fetch(`${base}/api/auction_snapshot`, { headers });
            if (snapResp.ok) {
                const snapData = await snapResp.json();
                const snapshot = snapData.snapshot || {};
                if (Object.keys(snapshot).length > 0) {
                    mainKvSet("auction_items", snapshot);
                    auctionSnapshotRestored = Object.keys(snapshot).length;
                }
            }
        }
    } catch (e) { auctionSnapshotErr = e.message; }

    // ── 汇报结果 ─────────────────────────────────────────────────────────────
    let msg_lines = [`✅ 拉取全部完成！`];
    msg_lines.push(`📋 配置+注册表+模版：${configCount} 项已同步`);
    if (pendingMerged > 0)      msg_lines.push(`📦 网页端同步：成功落地 ${pendingMerged} 件新物品`);
    if (equipPendingMerged > 0) msg_lines.push(`🛡️ 网页端同步：成功落地 ${equipPendingMerged} 件新装备`);
    msg_lines.push(poolErr ? `⚠️ 池子拉取失败：${poolErr}` : `🎲 池子：${poolCount} 个已覆盖`);

    if (auctionErr) {
        msg_lines.push(`⚠️ 拍卖队列拉取失败：${auctionErr}`);
    } else if (auctionActivated > 0) {
        msg_lines.push(`🔨 拍卖队列：成功激活 ${auctionActivated} 件${auctionFailed > 0 ? `（⚠️ ${auctionFailed} 件物品代码本地不存在）` : ""}`);
    }
    if (auctionSnapshotErr) {
        msg_lines.push(`⚠️ 拍卖快照还原失败：${auctionSnapshotErr}`);
    } else if (auctionSnapshotRestored > 0) {
        msg_lines.push(`🔨 拍卖快照：已还原 ${auctionSnapshotRestored} 件进行中拍卖`);
    }
    
    msg_lines.push(`所有设置已立即生效。`);
    seal.replyToSender(ctx, msg, msg_lines.join("\n"));

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拉取全部"] = cmd_pull_all;

// ── 同步指南 ──────────────────────────────────────────────────────────────────

function sendSyncGuideForward(groupId) {
    const main = getMainExt();
    if (!main) return;
    const wsUrl = seal.ext.getStringConfig(main.ext, "ws地址");
    const token = seal.ext.getStringConfig(main.ext, "ws Access token");
    if (!wsUrl) return;
    let url = wsUrl;
    if (token) url += (url.includes("?") ? "&" : "?") + "access_token=" + encodeURIComponent(token);
    const gid = parseInt(String(groupId).replace(/[^\d]/g, ""), 10);

    const sections = [
        ["📡 同步指南",
         "RP 存档系统同步命令速查",
         "",
         "⬇  存档服务器 → 机器人（拉取，覆盖本地）",
         "⬆  机器人 → 存档服务器（推送，覆盖网页）",
         "",
         "发送「同步指南」随时查阅"],

        ["🌐 全量操作（长日设置插件，管理员）",
         "─────────────────────────────",
         "⬇ 拉取全部",
         "从存档服务器拉取全部数据，覆盖本地",
         "涵盖：配置+注册表+模版、待上载物品/装备合并、池子、拍卖队列/快照",
         "用法：拉取全部",
         "",
         "⬆ 推送全部",
         "将机器人当前数据全量推送到存档网页端",
         "涵盖：设置项、物品/装备注册表、结戏加成模版、礼品库、池子、拍卖快照",
         "用法：推送全部"],

        ["💡 常用场景速查",
         "─────────────────────────────",
         "网页端编辑完池子/设置/物品 → 拉取全部",
         "新部署机器人 / 初始化 → 拉取全部",
         "机器人这边配置/物品/池子有改动，要同步给网页 → 推送全部",
         "",
         "⚠️ 现已合并为「推送全部」「拉取全部」两条一键全量指令",
         "不再有单独的同步设置/同步池子/上传池子/全量同步/全量上传等指令，也没有预览模式"],
    ];

    const nodes = sections.map(lines => ({
        type: "node",
        data: { name: "同步指南", uin: "10001", content: lines.join("\n") }
    }));

    const api = getApi();
    if (api) {
        api.ws({
            action: "send_group_forward_msg",
            params: { group_id: gid, messages: nodes },
            echo: "sync_guide_" + Date.now()
        }, null, null, null);
        return;
    }
    const socket = new WebSocket(url);
    socket.onopen = () => {
        socket.send(JSON.stringify({
            action: "send_group_forward_msg",
            params: { group_id: gid, messages: nodes },
            echo: "sync_guide_" + Date.now()
        }));
        socket.close();
    };
    socket.onerror = (e) => { console.error("[同步指南] 合并转发发送失败", e.message); };
}

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();
    if (raw !== "同步指南") return;
    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, "请在群内使用此指令。");
        return;
    }
    sendSyncGuideForward(msg.groupId);
};

// 启动自动天数轮询
registerAutoDaySystem();

// ============================================================
// 📦 拉存档（上传最新 ZIP 到公告群文件）
// ============================================================
let cmd_pull_archive = seal.ext.newCmdItemInfo();
cmd_pull_archive.name = "拉存档";
cmd_pull_archive.help = "【管理员】将最新存档 ZIP 上传到公告群文件\n用法：。拉存档\n说明：需先在 RP 存档后台点击「下载 ZIP」生成存档，然后用此指令推送到公告群。";
cmd_pull_archive.solve = async (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const main = getMainExt();
    if (!main) {
        seal.replyToSender(ctx, msg, "❌ 无法连接主插件 changri");
        return seal.ext.newCmdExecuteResult(true);
    }

    const base  = (seal.ext.getStringConfig(main.ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(main.ext, "RP存档Token") || "";
    if (!base || !token) {
        seal.replyToSender(ctx, msg, "❌ 未配置「RP存档服务器地址」或「RP存档Token」，请先在插件设置中填写");
        return seal.ext.newCmdExecuteResult(true);
    }

    const announceGid = mainKvGet("adminAnnounceGroupId", null);
    if (!announceGid) {
        seal.replyToSender(ctx, msg, "❌ 未配置公告群（adminAnnounceGroupId），请先在长日设置中填写群号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const api = getApi();
    if (!api) {
        seal.replyToSender(ctx, msg, "❌ 无法获取 bot API，请确认 changri 插件已加载");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查询存档文件名
    let zipName = "存档.zip";
    try {
        const infoResp = await fetch(`${base}/api/latest_archive_info?token=${encodeURIComponent(token)}`);
        if (infoResp.status === 404) {
            seal.replyToSender(ctx, msg, "❌ 服务端暂无存档数据");
            return seal.ext.newCmdExecuteResult(true);
        }
        if (infoResp.status === 403) {
            seal.replyToSender(ctx, msg, "❌ Token 无效，请检查插件设置里的「RP存档Token」");
            return seal.ext.newCmdExecuteResult(true);
        }
        if (infoResp.ok) {
            const info = await infoResp.json();
            if (info.name) zipName = info.name;
        }
    } catch (e) {
        seal.replyToSender(ctx, msg, `❌ 连接存档服务器失败：${e.message}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    seal.replyToSender(ctx, msg, `⏳ 正在上传「${zipName}」到公告群…`);

    const fileUrl = `${base}/api/latest_archive?token=${encodeURIComponent(token)}`;
    api.ws({
        action: "upload_group_file",
        params: { group_id: announceGid, file: fileUrl, name: zipName },
        echo: "pull_archive_" + Date.now()
    }, null, null, null);

    await new Promise(r => setTimeout(r, 3000));
    seal.replyToSender(ctx, msg, `✅ 已请求上传「${zipName}」到公告群，请稍候查看群文件。`);

    return seal.ext.newCmdExecuteResult(true);
};
// ext.cmdMap["拉存档"] = cmd_pull_archive;  // 暂时禁用，LLBot 群文件上传超时问题待解决

// ============================================================
// 🎲 随机分组（2026-06 自卫星插件并入本文件）
// ============================================================
let cmd_random_group = seal.ext.newCmdItemInfo();
cmd_random_group.name = "随机分组";
cmd_random_group.help = "用法：.随机分组 [数字] [bg|tag名字]\n说明：将所有非NPC玩家随机分配到指定数量的组中。加 bg 尽量保证每组男女搭配；加 tag 名字则按「。修改tag」创建的分类交替分组。";
cmd_random_group.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let groupCount = parseInt(cmdArgs.getArgN(1));
    if (isNaN(groupCount) || groupCount <= 0) {
        seal.replyToSender(ctx, msg, "❌ 请输入正确的小组数量，例如：.随机分组 2");
        return seal.ext.newCmdExecuteResult(true);
    }
    const modeArg = cmdArgs.getArgN(2);
    const bgMode = modeArg === "bg";
    const tagArg = (!bgMode && modeArg) ? modeArg : null;

    const api = getApi();
    if (!api) {
        seal.replyToSender(ctx, msg, "❌ 主插件「长日将尽」未加载，请先加载主插件");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const storage = api.getRoleStorage();
    const npcList = mainKvGet("a_npc_list", []);
    const players = Object.values(storage[platform] || {}).map(v => v[0]).filter(n => n && !npcList.includes(n));

    if (players.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 当前平台没有可分配的非NPC玩家。");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (groupCount > players.length) {
        seal.replyToSender(ctx, msg, `❌ 组数(${groupCount})不能大于玩家总数(${players.length})。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let tagData = null;
    if (tagArg) {
        tagData = api.kvGet("sys_binary_tags", {})[tagArg];
        if (!tagData || Object.keys(tagData).length === 0) {
            seal.replyToSender(ctx, msg, `❌ 未找到 tag「${tagArg}」，请先使用「。修改tag」创建`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    const shuffle = arr => {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    };

    const groups = Array.from({ length: groupCount }, () => []);

    if (bgMode) {
        const privGrp = api.kvGet("a_private_group", {})[platform] || {};
        const profiles = api.kvGet("sys_char_profiles", {});
        const nameToUid = {};
        Object.entries(privGrp).forEach(([uid, v]) => { nameToUid[v[0]] = uid; });
        const males = shuffle(players.filter(n => {
            const uid = nameToUid[n];
            return uid && (profiles[`${platform}:${uid}`]?.gender || "女") === "男";
        }));
        const females = shuffle(players.filter(n => {
            const uid = nameToUid[n];
            return !uid || (profiles[`${platform}:${uid}`]?.gender || "女") !== "男";
        }));
        const maxRounds = Math.max(males.length, females.length);
        let mi = 0, fi = 0;
        for (let r = 0; r < maxRounds; r++) {
            if (mi < males.length)   { groups[r % groupCount].push(males[mi++]); }
            if (fi < females.length) { groups[r % groupCount].push(females[fi++]); }
        }
    } else if (tagArg) {
        const playerSet = new Set(players);
        const buckets = Object.values(tagData).map(names => shuffle(names.filter(n => playerSet.has(n))));
        const assignedNames = new Set(Object.values(tagData).flat());
        const unassigned = shuffle(players.filter(n => !assignedNames.has(n)));

        const maxLen = Math.max(...buckets.map(b => b.length), 0);
        const indices = buckets.map(() => 0);
        for (let r = 0; r < maxLen; r++) {
            for (let b = 0; b < buckets.length; b++) {
                if (indices[b] < buckets[b].length) {
                    groups[r % groupCount].push(buckets[b][indices[b]++]);
                }
            }
        }
        unassigned.forEach((p, idx) => { groups[idx % groupCount].push(p); });
    } else {
        shuffle(players).forEach((player, index) => {
            groups[index % groupCount].push(player);
        });
    }

    const modeLabel = bgMode ? "（男女搭配模式）" : (tagArg ? `（${tagArg} 交替模式）` : "");
    let response = `🎲 【随机分组结果】${modeLabel}\n总人数：${players.length} | 组数：${groupCount}\n`;
    response += "━━━━━━━━━━━━━━\n";
    groups.forEach((members, i) => {
        response += `第 ${i + 1} 组：${members.join("、")}\n`;
    });
    response += "━━━━━━━━━━━━━━";

    seal.replyToSender(ctx, msg, response);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["随机分组"] = cmd_random_group;