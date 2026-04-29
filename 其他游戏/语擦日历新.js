// ==UserScript==
// @name         语擦助手
// @author       长日将尽
// @version      2.1.0
// @description  记录和管理语擦档期，支持跨年录入、撞档预警、本月在档/空闲查询、本年数据统计（含主题题材）、月视图。
// @timestamp    2026-04-25
// @license      CC BY-NC-SA
// ==/UserScript//

/**
 * 数据结构（与 v1.7.x 完全兼容，同 storage key，直接替换即可）：
 * 存储键 "yuca_helper_data"
 * {
 *   "用户ID": {
 *     "恋综名": {
 *       startYear: 2025,
 *       timeRange: "MMDD MMDD",   // 同年如 "0315 0320"，跨年如 "1201 0201"
 *       status, character, orientation, theme,
 *       roleName, roleType, gender, outcome
 *     }
 *   }
 * }
 *
 * v2.0.0 改动：
 * - 修复跨年时间段（如 1201 0201）被验证拦截的 bug
 * - 录入档期：覆盖旧记录时提示"已更新"
 * - 修改命令：错误提示补全"结局"字段
 * - 新增：查档期、重命名档期、档期帮助
 * - 本月档期：同时展示在档恋综列表和空闲日期
 * - 提取 parseYearMonth、calcMonthOccupied 公共函数，消除月视图/本月档期的重复逻辑
 *
 * v2.1.0 改动：
 * - 录入档期：保存后检测与已有档期的时间重叠，给出撞档提醒（不阻止录入）
 * - 本年数据：新增主题题材分布统计
 */

let ext = seal.ext.find('yuca_helper');
if (!ext) {
    ext = seal.ext.new('yuca_helper', '长日将尽', '2.1.0');
    seal.ext.register(ext);
}

// ======================== 存储工具 ========================

const STORAGE_KEY = 'yuca_helper_data';

function readAllData() {
    let raw = ext.storageGet(STORAGE_KEY);
    if (raw) {
        try { return JSON.parse(raw); } catch (e) { return {}; }
    }
    return {};
}

function saveAllData(data) {
    ext.storageSet(STORAGE_KEY, JSON.stringify(data));
}

function getUserData(ctx, msg) {
    return readAllData()[msg.sender.userId] || {};
}

function updateUserData(ctx, msg, newData) {
    let all = readAllData();
    all[msg.sender.userId] = newData;
    saveAllData(all);
}

// ======================== 时间工具 ========================

function getCurrentYear() { return new Date().getFullYear(); }
function getCurrentMonth() { return new Date().getMonth() + 1; }
function getDaysInMonth(year, month) { return new Date(year, month, 0).getDate(); }
function getFirstDayOfMonth(year, month) { return new Date(year, month - 1, 1).getDay(); }

/**
 * 解析时间段字符串（MMDD MMDD）。
 * v2.0.0 修复：允许跨年（endMonth < startMonth），不再错误拦截。
 */
function parseTimeRange(rangeStr) {
    const pattern = /^(\d{2})(\d{2})\s+(\d{2})(\d{2})$/;
    let match = rangeStr.match(pattern);
    if (!match) {
        return { valid: false, errorMsg: '时间段格式错误，应为 MMDD MMDD（同年如 0315 0320，跨年如 1201 0201）' };
    }

    let sm = parseInt(match[1], 10), sd = parseInt(match[2], 10);
    let em = parseInt(match[3], 10), ed = parseInt(match[4], 10);

    if (sm < 1 || sm > 12 || em < 1 || em > 12) {
        return { valid: false, errorMsg: '月份必须在 01-12 之间' };
    }

    const maxDay = m => m === 2 ? 29 : [4, 6, 9, 11].includes(m) ? 30 : 31;

    if (sd < 1 || sd > maxDay(sm)) {
        return { valid: false, errorMsg: `开始日期 ${sm}月 不存在 ${sd} 日` };
    }
    if (ed < 1 || ed > maxDay(em)) {
        return { valid: false, errorMsg: `结束日期 ${em}月 不存在 ${ed} 日` };
    }

    // 跨年（endMonth < startMonth）合法；同月时结束日必须大于开始日
    if (em === sm && ed <= sd) {
        return { valid: false, errorMsg: '同月时结束日必须大于开始日' };
    }

    return { valid: true, startMonth: sm, startDay: sd, endMonth: em, endDay: ed, errorMsg: '' };
}

function isCrossYear(endMonth, startMonth) {
    return endMonth < startMonth;
}

// ======================== 长消息分段发送 ========================

function sendLongMessage(ctx, msg, text, maxLen = 1500) {
    if (text.length <= maxLen) {
        seal.replyToSender(ctx, msg, text);
        return;
    }
    let lines = text.split('\n');
    let chunks = [], cur = '';
    for (let line of lines) {
        if ((cur + line + '\n').length > maxLen) {
            chunks.push(cur);
            cur = line + '\n';
        } else {
            cur += line + '\n';
        }
    }
    if (cur) chunks.push(cur);
    for (let chunk of chunks) seal.replyToSender(ctx, msg, chunk.trim());
}

// ======================== 参数解析工具 ========================

/**
 * 智能解析年月参数，顺序任意。
 * @returns {{ year, month, error }}
 */
function parseYearMonth(arg1, arg2) {
    const isYear = y => !isNaN(y) && y >= 1900 && y <= 2100;
    const isMon = m => !isNaN(m) && m >= 1 && m <= 12;
    const now = new Date();

    if (arg1 && arg2) {
        let n1 = parseInt(arg1, 10), n2 = parseInt(arg2, 10);
        if (isYear(n1) && isMon(n2)) return { year: n1, month: n2, error: null };
        if (isMon(n1) && isYear(n2)) return { year: n2, month: n1, error: null };
        return { error: '❌ 参数无效，请提供合法的年份（1900-2100）和月份（1-12）' };
    } else if (arg1) {
        let m = parseInt(arg1, 10);
        if (!isMon(m)) return { error: '❌ 月份无效，请输入 1-12 之间的数字' };
        return { year: now.getFullYear(), month: m, error: null };
    }
    return { year: now.getFullYear(), month: now.getMonth() + 1, error: null };
}

// ======================== 月份占用计算（复用于本月档期/月视图） ========================

/**
 * 计算指定年月中各天是否被档期覆盖，以及在档恋综列表。
 * @returns {{ occupied: boolean[], daysInMonth: number, activeShows: Array }}
 */
function calcMonthOccupied(userData, targetYear, targetMonth) {
    let daysInMonth = getDaysInMonth(targetYear, targetMonth);
    let occupied = new Array(daysInMonth + 1).fill(false);
    let activeShows = [];

    for (let name in userData) {
        let entry = userData[name];
        let { startYear, timeRange } = entry;
        let parsed = parseTimeRange(timeRange);
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
        let endYear = cross ? startYear + 1 : startYear;

        let startVal = startYear * 10000 + parsed.startMonth * 100 + parsed.startDay;
        let endVal = endYear * 10000 + parsed.endMonth * 100 + parsed.endDay;
        let monthStartVal = targetYear * 10000 + targetMonth * 100 + 1;
        let monthEndVal = targetYear * 10000 + targetMonth * 100 + daysInMonth;

        if (endVal < monthStartVal || startVal > monthEndVal) continue;

        let startDay = (startYear === targetYear && parsed.startMonth === targetMonth)
            ? parsed.startDay : 1;
        let endDay = (endYear === targetYear && parsed.endMonth === targetMonth)
            ? parsed.endDay : daysInMonth;

        for (let d = startDay; d <= endDay; d++) occupied[d] = true;
        activeShows.push({ name, startDay, endDay });
    }

    return { occupied, daysInMonth, activeShows };
}

// ======================== 撞档检测 ========================

/**
 * 检测新档期与已有档期是否存在时间重叠。
 * @param {Object} userData  当前用户全部档期（已含本次新增/覆盖后的数据）
 * @param {string} skipName  本次录入的恋综名，跳过自身比较
 * @param {number} newStartYear
 * @param {Object} newParsed  parseTimeRange 返回的解析结果
 * @returns {string[]} 与新档期存在重叠的恋综名列表
 */
function findConflicts(userData, skipName, newStartYear, newParsed) {
    let cross = isCrossYear(newParsed.endMonth, newParsed.startMonth);
    let newEndYear = cross ? newStartYear + 1 : newStartYear;
    let newStartVal = newStartYear * 10000 + newParsed.startMonth * 100 + newParsed.startDay;
    let newEndVal = newEndYear * 10000 + newParsed.endMonth * 100 + newParsed.endDay;

    let conflicts = [];
    for (let name in userData) {
        if (name === skipName) continue;
        let entry = userData[name];
        let parsed = parseTimeRange(entry.timeRange || '');
        if (!parsed.valid) continue;

        let existCross = isCrossYear(parsed.endMonth, parsed.startMonth);
        let existEndYear = existCross ? entry.startYear + 1 : entry.startYear;
        let existStartVal = entry.startYear * 10000 + parsed.startMonth * 100 + parsed.startDay;
        let existEndVal = existEndYear * 10000 + parsed.endMonth * 100 + parsed.endDay;

        if (newStartVal <= existEndVal && newEndVal >= existStartVal) {
            conflicts.push(name);
        }
    }
    return conflicts;
}

// ======================== 字段映射（全局复用） ========================

const FIELD_MAP = {
    '时间段': 'timeRange', 'timerange': 'timeRange',
    '恋综名': 'name', 'name': 'name',
    '年份': 'startYear', 'year': 'startYear',
    '状态': 'status', 'status': 'status',
    '皮相': 'character', 'character': 'character',
    '性向': 'orientation', 'orientation': 'orientation',
    '主题': 'theme', 'theme': 'theme',
    '角色名': 'roleName', 'rolename': 'roleName',
    '角色类型': 'roleType', 'roletype': 'roleType',
    '性别': 'gender', 'gender': 'gender',
    '结局': 'outcome', 'outcome': 'outcome'
};

const ENTRY_TEMPLATE = '。录入档期\n时间段：\n恋综名：\n年份：\n状态：\n皮相：\n性向：\n主题：\n角色名：\n角色类型：\n性别：\n结局：';

// ======================== 档期帮助 ========================

let cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = '档期帮助';
cmd_help.help = '。档期帮助 —— 显示所有可用指令';
cmd_help.solve = (ctx, msg, cmdArgs) => {
    let help = `📅 【语擦助手 v2.1 指令列表】
══════════════
📝 录入与管理
  。录入档期          录入新档期（多行键值格式）
  。修改 名 项 值     修改指定字段
  。重命名档期 旧 新  重命名恋综（保留所有数据）
  。删除档期 名       删除指定档期

🔍 查询
  。查档期 名             查看档期完整详情
  。我的日历              全部档期（按年分组）
  。本月档期 [年] [月]    本月在档恋综及空闲日期
  。月视图   [年] [月]    日历视图（标记有档期日）

📊 统计
  。本年数据 [年]   年度数据统计

💡 时间段格式：MMDD MMDD
   同年示例：0315 0320（3月15日至3月20日）
   跨年示例：1201 0201（12月1日至次年2月1日）
══════════════`;
    seal.replyToSender(ctx, msg, help);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['档期帮助'] = cmd_help;

// ======================== 录入档期 ========================

let cmd_add = seal.ext.newCmdItemInfo();
cmd_add.name = '录入档期';
cmd_add.help = `。录入档期 —— 以多行键值对方式录入档期。时间段格式：MMDD MMDD（跨年示例：1201 0201）。未填写字段默认"未知"，年份默认当前年。\n\n模板：\n${ENTRY_TEMPLATE}`;
cmd_add.solve = (ctx, msg, cmdArgs) => {
    const rawMessage = msg.message.trim();
    const prefix = '。录入档期';
    let content = rawMessage.startsWith(prefix) ? rawMessage.substring(prefix.length).trim() : rawMessage;

    if (!content) {
        seal.replyToSender(ctx, msg, `请按以下格式录入档期（可复制后填写）：\n\n${ENTRY_TEMPLATE}\n\n时间段格式：MMDD MMDD\n同年示例：0315 0320\n跨年示例：1201 0201`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let fields = {
        timeRange: null, name: null, startYear: getCurrentYear(),
        status: '未知', character: '未知', orientation: '未知',
        theme: '未知', roleName: '未知', roleType: '未知',
        gender: '未知', outcome: '未知'
    };

    for (let line of content.split('\n')) {
        line = line.trim();
        if (!line) continue;
        let match = line.match(/^(.+?)[:：](.*)$/);
        if (!match) continue;

        let keyRaw = match[1].trim();
        let value = match[2].trim();
        let keyNorm = keyRaw.toLowerCase().replace(/\s+/g, '');
        let fieldKey = FIELD_MAP[keyNorm] || FIELD_MAP[keyRaw];
        if (!fieldKey) continue;

        if (fieldKey === 'startYear') {
            if (!value) continue;
            let y = parseInt(value, 10);
            if (isNaN(y) || y < 1900 || y > 2100) {
                seal.replyToSender(ctx, msg, `❌ 年份"${value}"无效，请输入四位数字年份（如2025）或留空`);
                return seal.ext.newCmdExecuteResult(true);
            }
            fields.startYear = y;
        } else if (value) {
            fields[fieldKey] = value;
        }
    }

    if (!fields.timeRange) {
        seal.replyToSender(ctx, msg, '❌ 缺少必填字段"时间段"，请填写例如 0315 0320');
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!fields.name) {
        seal.replyToSender(ctx, msg, '❌ 缺少必填字段"恋综名"，请填写恋综名称');
        return seal.ext.newCmdExecuteResult(true);
    }

    let parsed = parseTimeRange(fields.timeRange);
    if (!parsed.valid) {
        seal.replyToSender(ctx, msg, `❌ ${parsed.errorMsg}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let all = readAllData();
    let uid = msg.sender.userId;
    if (!all[uid]) all[uid] = {};
    let isUpdate = !!all[uid][fields.name];

    all[uid][fields.name] = {
        startYear: fields.startYear,
        timeRange: fields.timeRange,
        status: fields.status,
        character: fields.character,
        orientation: fields.orientation,
        theme: fields.theme,
        roleName: fields.roleName,
        roleType: fields.roleType,
        gender: fields.gender,
        outcome: fields.outcome
    };
    saveAllData(all);

    let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
    let hint = cross ? '（跨年，将自动拆分显示）' : '';
    let action = isUpdate ? '已更新' : '已录入';

    // 撞档检测：检查与其他档期的时间重叠（all[uid] 此时已含本次录入）
    let conflicts = findConflicts(all[uid], fields.name, fields.startYear, parsed);

    let reply = `✅ 档期${action}${hint}：\n`;
    reply += `恋综名：${fields.name}\n`;
    reply += `时间段：${fields.startYear}/${fields.timeRange}\n`;
    if (fields.status !== '未知') reply += `状态：${fields.status}\n`;
    if (fields.character !== '未知') reply += `皮相：${fields.character}\n`;
    if (fields.orientation !== '未知') reply += `性向：${fields.orientation}\n`;
    if (fields.theme !== '未知') reply += `主题：${fields.theme}\n`;
    if (fields.roleName !== '未知') reply += `角色名：${fields.roleName}\n`;
    if (fields.roleType !== '未知') reply += `角色类型：${fields.roleType}\n`;
    if (fields.gender !== '未知') reply += `性别：${fields.gender}\n`;
    if (fields.outcome !== '未知') reply += `结局：${fields.outcome}\n`;

    if (conflicts.length > 0) {
        reply += `\n⚠️ 撞档提醒：与以下档期存在时间重叠：\n`;
        conflicts.forEach(n => reply += `  · ${n}\n`);
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['录入档期'] = cmd_add;

// ======================== 查档期 ========================

let cmd_query = seal.ext.newCmdItemInfo();
cmd_query.name = '查档期';
cmd_query.help = '。查档期 恋综名 —— 查看指定恋综的完整档期信息';
cmd_query.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    if (!name) {
        seal.replyToSender(ctx, msg, '❌ 格式：。查档期 恋综名');
        return seal.ext.newCmdExecuteResult(true);
    }
    let userData = getUserData(ctx, msg);
    if (!userData[name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综「${name}」的档期记录`);
        return seal.ext.newCmdExecuteResult(true);
    }
    let e = userData[name];
    let parsed = parseTimeRange(e.timeRange || '');
    let cross = parsed.valid && isCrossYear(parsed.endMonth, parsed.startMonth);

    let reply = `📌 【${name}】${cross ? '（跨年）' : ''}\n`;
    reply += `时间段：${e.startYear}/${e.timeRange}\n`;
    reply += `状态：${e.status || '未知'}\n`;
    reply += `皮相：${e.character || '未知'}\n`;
    reply += `性向：${e.orientation || '未知'}\n`;
    reply += `主题：${e.theme || '未知'}\n`;
    reply += `角色名：${e.roleName || '未知'}\n`;
    reply += `角色类型：${e.roleType || '未知'}\n`;
    reply += `性别：${e.gender || '未知'}\n`;
    reply += `结局：${e.outcome || '未知'}`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['查档期'] = cmd_query;

// ======================== 修改档期 ========================

let cmd_modify = seal.ext.newCmdItemInfo();
cmd_modify.name = '修改';
cmd_modify.help = '。修改 恋综名 项目 内容 —— 修改指定恋综的某个字段。项目可以是：时间段、年份、状态、皮相、性向、主题、角色名、角色类型、性别、结局。';
cmd_modify.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let field = cmdArgs.getArgN(2);
    let value = cmdArgs.getArgN(3);
    if (!name || !field || !value) {
        seal.replyToSender(ctx, msg, '❌ 参数不足，格式：。修改 恋综名 项目 内容');
        return seal.ext.newCmdExecuteResult(true);
    }

    let fieldKey = FIELD_MAP[(field.toLowerCase ? field.toLowerCase() : field).replace(/\s+/g, '')] || FIELD_MAP[field];
    // "name" 字段不允许通过修改命令改变（应使用重命名档期）
    if (!fieldKey || fieldKey === 'name') {
        seal.replyToSender(ctx, msg, '❌ 项目名称无效，可用项目：时间段、年份、状态、皮相、性向、主题、角色名、角色类型、性别、结局\n（重命名恋综请用：。重命名档期 旧名 新名）');
        return seal.ext.newCmdExecuteResult(true);
    }

    let all = readAllData();
    let uid = msg.sender.userId;
    let userData = all[uid] || {};
    if (!userData[name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综「${name}」的档期`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (fieldKey === 'timeRange') {
        let parsed = parseTimeRange(value);
        if (!parsed.valid) {
            seal.replyToSender(ctx, msg, `❌ ${parsed.errorMsg}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        userData[name].timeRange = value;
    } else if (fieldKey === 'startYear') {
        let year = parseInt(value, 10);
        if (isNaN(year) || year < 1900 || year > 2100) {
            seal.replyToSender(ctx, msg, '❌ 年份无效，请输入四位数字年份（如2025）');
            return seal.ext.newCmdExecuteResult(true);
        }
        userData[name].startYear = year;
    } else {
        userData[name][fieldKey] = value;
    }

    all[uid] = userData;
    saveAllData(all);
    seal.replyToSender(ctx, msg, `✅ 已修改「${name}」的 ${field} 为：${value}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['修改'] = cmd_modify;

// ======================== 重命名档期 ========================

let cmd_rename = seal.ext.newCmdItemInfo();
cmd_rename.name = '重命名档期';
cmd_rename.help = '。重命名档期 旧名 新名 —— 将恋综名从旧名改为新名（保留所有档期数据）';
cmd_rename.solve = (ctx, msg, cmdArgs) => {
    let oldName = cmdArgs.getArgN(1);
    let newName = cmdArgs.getArgN(2);
    if (!oldName || !newName) {
        seal.replyToSender(ctx, msg, '❌ 格式：。重命名档期 旧名 新名');
        return seal.ext.newCmdExecuteResult(true);
    }
    let all = readAllData();
    let uid = msg.sender.userId;
    let userData = all[uid] || {};
    if (!userData[oldName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综「${oldName}」的档期`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (userData[newName]) {
        seal.replyToSender(ctx, msg, `❌ 恋综「${newName}」已存在，请先删除或换一个名称`);
        return seal.ext.newCmdExecuteResult(true);
    }
    userData[newName] = userData[oldName];
    delete userData[oldName];
    all[uid] = userData;
    saveAllData(all);
    seal.replyToSender(ctx, msg, `✅ 已将「${oldName}」重命名为「${newName}」`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['重命名档期'] = cmd_rename;

// ======================== 删除档期 ========================

let cmd_delete = seal.ext.newCmdItemInfo();
cmd_delete.name = '删除档期';
cmd_delete.help = '。删除档期 恋综名 —— 删除指定恋综的档期记录';
cmd_delete.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    if (!name) {
        seal.replyToSender(ctx, msg, '❌ 参数不足，格式：。删除档期 恋综名');
        return seal.ext.newCmdExecuteResult(true);
    }
    let all = readAllData();
    let uid = msg.sender.userId;
    let userData = all[uid] || {};
    if (!userData[name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综「${name}」的档期`);
        return seal.ext.newCmdExecuteResult(true);
    }
    delete userData[name];
    all[uid] = userData;
    saveAllData(all);
    seal.replyToSender(ctx, msg, `✅ 已删除恋综「${name}」的档期`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['删除档期'] = cmd_delete;

// ======================== 我的日历 ========================

let cmd_calendar = seal.ext.newCmdItemInfo();
cmd_calendar.name = '我的日历';
cmd_calendar.help = '。我的日历 —— 按年份分组显示所有档期（含角色信息、性别、结局）';
cmd_calendar.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你的档期日历空空如也～');
        return seal.ext.newCmdExecuteResult(true);
    }

    let yearGroups = {};

    for (let name in userData) {
        let entry = userData[name];
        let { startYear, timeRange, status, character, orientation, theme } = entry;
        let roleName = entry.roleName || '未知';
        let roleType = entry.roleType || '未知';
        let gender = entry.gender || '未知';
        let outcome = entry.outcome || '未知';
        let parsed = parseTimeRange(timeRange);
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);

        let roleParts = [];
        if (roleName !== '未知') roleParts.push(roleName);
        if (roleType !== '未知') roleParts.push(roleType);
        if (gender !== '未知') roleParts.push(gender);
        if (outcome !== '未知') roleParts.push(`结:${outcome}`);
        let roleStr = roleParts.length > 0 ? ` [${roleParts.join('/')}]` : '';

        let baseInfo = [status, character, orientation, theme]
            .filter(v => v && v !== '未知').join(' ');
        if (baseInfo) baseInfo = ' · ' + baseInfo;

        const pad = n => n.toString().padStart(2, '0');

        if (cross) {
            let first = `${startYear}/${pad(parsed.startMonth)}${pad(parsed.startDay)}-1231`;
            let second = `${startYear + 1}/0101-${pad(parsed.endMonth)}${pad(parsed.endDay)}`;

            if (!yearGroups[startYear]) yearGroups[startYear] = [];
            yearGroups[startYear].push({
                sort: startYear * 10000 + parsed.startMonth * 100 + parsed.startDay,
                line: `📌 ${name}${roleStr}\n   ${first}${baseInfo}`
            });
            if (!yearGroups[startYear + 1]) yearGroups[startYear + 1] = [];
            yearGroups[startYear + 1].push({
                sort: (startYear + 1) * 10000 + 101,
                line: `📌 ${name}${roleStr} (续)\n   ${second}${baseInfo}`
            });
        } else {
            let range = `${startYear}/${pad(parsed.startMonth)}${pad(parsed.startDay)}-${pad(parsed.endMonth)}${pad(parsed.endDay)}`;
            if (!yearGroups[startYear]) yearGroups[startYear] = [];
            yearGroups[startYear].push({
                sort: startYear * 10000 + parsed.startMonth * 100 + parsed.startDay,
                line: `📌 ${name}${roleStr}\n   ${range}${baseInfo}`
            });
        }
    }

    for (let year in yearGroups) {
        yearGroups[year].sort((a, b) => a.sort - b.sort);
    }

    let reply = '📅 【我的档期日历】\n══════════════\n';
    let sortedYears = Object.keys(yearGroups).map(Number).sort((a, b) => a - b);
    for (let year of sortedYears) {
        reply += `\n✨ ${year} 年 ✨\n──────────────\n`;
        yearGroups[year].forEach(item => { reply += item.line + '\n'; });
    }
    reply += '══════════════';

    sendLongMessage(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['我的日历'] = cmd_calendar;

// ======================== 本月档期（显示在档恋综 + 空闲日期） ========================

let cmd_this_month = seal.ext.newCmdItemInfo();
cmd_this_month.name = '本月档期';
cmd_this_month.help = '。本月档期 [年份] [月份] 或 [月份] [年份] —— 显示指定年月的在档恋综列表及空闲日期区间';
cmd_this_month.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let ym = parseYearMonth(cmdArgs.getArgN(1), cmdArgs.getArgN(2));
    if (ym.error) {
        seal.replyToSender(ctx, msg, ym.error);
        return seal.ext.newCmdExecuteResult(true);
    }
    let { year: targetYear, month: targetMonth } = ym;

    let { occupied, daysInMonth, activeShows } = calcMonthOccupied(userData, targetYear, targetMonth);

    const pad = n => n.toString().padStart(2, '0');

    let reply = `📅 ${targetYear}年${targetMonth}月 档期概览\n══════════════\n`;

    if (activeShows.length === 0) {
        reply += `▶ 在档恋综：本月无档期\n`;
    } else {
        activeShows.sort((a, b) => a.startDay - b.startDay);
        reply += `▶ 在档恋综（${activeShows.length} 个）：\n`;
        activeShows.forEach(s => {
            reply += `  · ${s.name}（${pad(s.startDay)}日-${pad(s.endDay)}日）\n`;
        });
    }

    let freeIntervals = [];
    let start = null;
    for (let d = 1; d <= daysInMonth; d++) {
        if (!occupied[d] && start === null) start = d;
        if (occupied[d] && start !== null) { freeIntervals.push({ start, end: d - 1 }); start = null; }
    }
    if (start !== null) freeIntervals.push({ start, end: daysInMonth });

    reply += '\n🆓 空闲日期：\n';
    if (freeIntervals.length === 0) {
        reply += '  整月无空闲（全部被档期覆盖）\n';
    } else {
        let rangeStr = freeIntervals.map(iv =>
            iv.start === iv.end
                ? `${pad(iv.start)}日`
                : `${pad(iv.start)}-${pad(iv.end)}日`
        ).join('、');
        reply += `  ${rangeStr}\n`;
    }

    reply += '══════════════';
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['本月档期'] = cmd_this_month;

// ======================== 本年数据 ========================

let cmd_year_data = seal.ext.newCmdItemInfo();
cmd_year_data.name = '本年数据';
cmd_year_data.help = '。本年数据 [年份] —— 统计指定年份的档期总数、皮相、性向/性别/结局分布、语擦天数（去重）。缺省统计至今日。';
cmd_year_data.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📊 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let now = new Date();
    let targetYear, targetStart, targetEnd, yearLabel;

    let yearParam = cmdArgs.getArgN(1);
    if (yearParam) {
        targetYear = parseInt(yearParam, 10);
        if (isNaN(targetYear) || targetYear < 1900 || targetYear > 2100) {
            seal.replyToSender(ctx, msg, '❌ 年份无效，请输入四位数字年份（如2025）');
            return seal.ext.newCmdExecuteResult(true);
        }
        targetStart = targetYear * 10000 + 101;
        targetEnd = targetYear * 10000 + 1231;
        yearLabel = `${targetYear}年`;
    } else {
        targetYear = now.getFullYear();
        let month = now.getMonth() + 1;
        let day = now.getDate();
        targetStart = targetYear * 10000 + 101;
        targetEnd = targetYear * 10000 + month * 100 + day;
        yearLabel = `${targetYear}年（截至今日）`;
    }

    let totalLianZong = 0;
    let characters = [];
    let orientations = [];
    let genders = [];
    let outcomes = [];
    let themes = [];
    let activeRanges = [];

    for (let name in userData) {
        let entry = userData[name];
        let { startYear, timeRange, character, orientation, theme } = entry;
        let gender = entry.gender || '未知';
        let outcome = entry.outcome || '未知';
        let parsed = parseTimeRange(timeRange);
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
        let endYear = cross ? startYear + 1 : startYear;

        let startVal = startYear * 10000 + parsed.startMonth * 100 + parsed.startDay;
        let endVal = endYear * 10000 + parsed.endMonth * 100 + parsed.endDay;

        if (endVal < targetStart || startVal > targetEnd) continue;

        totalLianZong++;
        if (character !== '未知') characters.push({ name, character });
        if (orientation !== '未知') orientations.push(orientation);
        if (gender !== '未知') genders.push(gender);
        if (outcome !== '未知') outcomes.push(outcome);
        if (theme && theme !== '未知') themes.push(theme);

        activeRanges.push({ start: Math.max(startVal, targetStart), end: Math.min(endVal, targetEnd) });
    }

    // 逐日统计语擦天数
    let sy = Math.floor(targetStart / 10000), sm2 = Math.floor((targetStart % 10000) / 100), sd2 = targetStart % 100;
    let ey = Math.floor(targetEnd / 10000), em2 = Math.floor((targetEnd % 10000) / 100), ed2 = targetEnd % 100;

    let totalDaysInRange = 0, coveredDays = 0, weekdayCovered = 0, weekendCovered = 0;
    let curDate = new Date(sy, sm2 - 1, sd2);
    let endDate = new Date(ey, em2 - 1, ed2);
    endDate.setHours(23, 59, 59, 999);

    while (curDate <= endDate) {
        totalDaysInRange++;
        let curVal = curDate.getFullYear() * 10000 + (curDate.getMonth() + 1) * 100 + curDate.getDate();
        let covered = activeRanges.some(r => curVal >= r.start && curVal <= r.end);
        if (covered) {
            coveredDays++;
            let dow = curDate.getDay();
            if (dow === 0 || dow === 6) weekendCovered++; else weekdayCovered++;
        }
        curDate.setDate(curDate.getDate() + 1);
    }

    let coveredPercent = totalDaysInRange > 0 ? (coveredDays / totalDaysInRange * 100).toFixed(1) : '0.0';

    const distrib = (arr, label, emoji) => {
        if (arr.length === 0) return `\n${emoji} ${label}：无非未知记录\n`;
        let countMap = {};
        arr.forEach(v => countMap[v] = (countMap[v] || 0) + 1);
        let total = arr.length;
        let out = `\n${emoji} ${label}分布（共 ${total} 个非未知）：\n`;
        Object.entries(countMap).sort((a, b) => b[1] - a[1]).forEach(([v, c]) => {
            out += `   ${v} ： ${c} (${(c / total * 100).toFixed(1)}%)\n`;
        });
        return out;
    };

    let reply = `📊 【${yearLabel}数据】\n══════════════\n📌 涉及的恋综：${totalLianZong} 个\n`;

    if (characters.length > 0) {
        reply += `\n🎭 皮相（非未知）：\n`;
        characters.forEach(c => reply += `   · ${c.name} ： ${c.character}\n`);
    } else {
        reply += `\n🎭 皮相：无记录\n`;
    }

    reply += distrib(orientations, '性向', '❤️');
    reply += distrib(genders, '性别', '🚻');
    reply += distrib(outcomes, '结局', '🎬');
    reply += distrib(themes, '主题题材', '🎨');

    reply += `\n📅 语擦天数：${coveredDays} 天（占 ${coveredPercent}%）\n`;
    reply += `   · 周中：${weekdayCovered} 天\n`;
    reply += `   · 周末：${weekendCovered} 天\n`;
    reply += '══════════════';

    sendLongMessage(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['本年数据'] = cmd_year_data;

// ======================== 月视图 ========================

let cmd_month_view = seal.ext.newCmdItemInfo();
cmd_month_view.name = '月视图';
cmd_month_view.help = '。月视图 [年份] [月份] 或 [月份] [年份] —— 显示指定年月的日历，标记有档期的日期。缺省年份为今年，缺省月份为当月。';
cmd_month_view.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let ym = parseYearMonth(cmdArgs.getArgN(1), cmdArgs.getArgN(2));
    if (ym.error) {
        seal.replyToSender(ctx, msg, ym.error);
        return seal.ext.newCmdExecuteResult(true);
    }
    let { year: targetYear, month: targetMonth } = ym;

    let { occupied, daysInMonth } = calcMonthOccupied(userData, targetYear, targetMonth);

    let firstDay = getFirstDayOfMonth(targetYear, targetMonth);
    let weekdays = ['日', '一', '二', '三', '四', '五', '六'];
    let lines = [];
    let line = '   '.repeat(firstDay);

    for (let d = 1; d <= daysInMonth; d++) {
        let dayStr = d.toString().padStart(2, ' ');
        line += occupied[d] ? `[${dayStr}]` : ` ${dayStr} `;
        if ((firstDay + d) % 7 === 0 || d === daysInMonth) {
            lines.push(line);
            line = '';
        }
    }

    let reply = `📅 ${targetYear}年${targetMonth}月 档期视图\n`;
    reply += weekdays.join(' ') + '\n';
    lines.forEach(l => reply += l + '\n');
    reply += '注：[数字] 表示该日有档期';
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['月视图'] = cmd_month_view;
