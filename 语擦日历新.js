// ==UserScript==
// @name         语擦助手
// @author       长日将尽
// @version      1.7.2
// @description  记录和管理语擦档期，支持跨年拆分、本月空闲区间、本年数据统计、月视图。新增性别字段，时间段格式 MMDD MMDD。长消息自动分段。
// @timestamp    2025-03-16
// @license      CC BY-NC-SA
// ==/UserScript//

/**
 * 数据结构：
 * 所有用户数据存储在统一键 "yuca_helper_data" 下：
 * {
 *   "用户ID1": {
 *     "恋综名A": {
 *       startYear: 2025,
 *       timeRange: "MMDD MMDD",    // 例如 "0315 0320"
 *       status: "状态",
 *       character: "皮相",
 *       orientation: "性向",
 *       theme: "主题",
 *       roleName: "角色名",
 *       roleType: "角色类型",
 *       gender: "性别"
 *     },
 *     ...
 *   },
 *   ...
 * }
 *
 * 如果 timeRange 跨年（结束月份 < 开始月份），则结束年份 = startYear + 1。
 * 显示时，跨年区间会被拆分为两个年份分别展示。
 */

let ext = seal.ext.find('yuca_helper');
if (!ext) {
    ext = seal.ext.new('yuca_helper', '长日将尽', '1.7.2');
    seal.ext.register(ext);
}

// ======================== 辅助函数 ========================

const STORAGE_KEY = 'yuca_helper_data';

function readAllData() {
    let raw = ext.storageGet(STORAGE_KEY);
    if (raw) {
        try {
            return JSON.parse(raw);
        } catch (e) {
            return {};
        }
    }
    return {};
}

function saveAllData(data) {
    ext.storageSet(STORAGE_KEY, JSON.stringify(data));
}

function getUserData(ctx, msg) {
    let all = readAllData();
    return all[msg.sender.userId] || {};
}

function getUserDataRef(ctx, msg) {
    let all = readAllData();
    let uid = msg.sender.userId;
    if (!all[uid]) all[uid] = {};
    return all[uid];
}

function updateUserData(ctx, msg, newData) {
    let all = readAllData();
    all[msg.sender.userId] = newData;
    saveAllData(all);
}

function getCurrentYear() {
    return new Date().getFullYear();
}

function getCurrentMonth() {
    return new Date().getMonth() + 1;
}

function getCurrentDay() {
    return new Date().getDate();
}

function getDaysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

function getFirstDayOfMonth(year, month) {
    return new Date(year, month - 1, 1).getDay();
}

/**
 * 解析时间段字符串（新格式：MMDD MMDD）
 * @returns {Object} { valid, startMonth, startDay, endMonth, endDay, errorMsg }
 */
function parseTimeRange(rangeStr) {
    // 新格式：四个数字 空格 四个数字
    const pattern = /^(\d{2})(\d{2})\s+(\d{2})(\d{2})$/;
    let match = rangeStr.match(pattern);
    if (!match) {
        return { valid: false, errorMsg: '时间段格式错误，应为 MMDD MMDD（例如 0315 0320）' };
    }

    let startMonth = parseInt(match[1], 10);
    let startDay = parseInt(match[2], 10);
    let endMonth = parseInt(match[3], 10);
    let endDay = parseInt(match[4], 10);

    // 月份范围 1-12
    if (startMonth < 1 || startMonth > 12 || endMonth < 1 || endMonth > 12) {
        return { valid: false, errorMsg: '月份必须在 01-12 之间' };
    }

    // 日期范围合法性（2月允许29日）
    const daysInMonth = (month) => {
        if (month === 2) return 29;
        if ([4,6,9,11].includes(month)) return 30;
        return 31;
    };

    if (startDay < 1 || startDay > daysInMonth(startMonth)) {
        return { valid: false, errorMsg: `开始日期 ${startMonth}月 不存在 ${startDay} 日` };
    }
    if (endDay < 1 || endDay > daysInMonth(endMonth)) {
        return { valid: false, errorMsg: `结束日期 ${endMonth}月 不存在 ${endDay} 日` };
    }

    // 比较前后日期
    const dateToValue = (month, day) => month * 100 + day;
    if (dateToValue(endMonth, endDay) <= dateToValue(startMonth, startDay)) {
        return { valid: false, errorMsg: '结束日期必须大于开始日期' };
    }

    return {
        valid: true,
        startMonth, startDay,
        endMonth, endDay,
        errorMsg: ''
    };
}

function isCrossYear(endMonth, startMonth) {
    return endMonth < startMonth;
}

// ======================== 新增：长消息分段发送 ========================
/**
 * 将长文本分段发送，每段不超过 maxLen 字符（默认1500）
 * @param {Object} ctx 上下文
 * @param {Object} msg 消息对象
 * @param {string} text 要发送的文本
 * @param {number} maxLen 单条消息最大长度
 */
function sendLongMessage(ctx, msg, text, maxLen = 1500) {
    if (text.length <= maxLen) {
        seal.replyToSender(ctx, msg, text);
        return;
    }

    let lines = text.split('\n');
    let currentChunk = '';
    let chunks = [];

    for (let line of lines) {
        // 如果加入当前行会超出长度，则保存当前块，并重新开始
        if ((currentChunk + line + '\n').length > maxLen) {
            chunks.push(currentChunk);
            currentChunk = line + '\n';
        } else {
            currentChunk += line + '\n';
        }
    }
    if (currentChunk) chunks.push(currentChunk);

    for (let chunk of chunks) {
        seal.replyToSender(ctx, msg, chunk.trim());
    }
}

// ======================== 录入档期（支持结局） ========================
let cmd_add = seal.ext.newCmdItemInfo();
cmd_add.name = '录入档期';
cmd_add.help = '。录入档期 —— 以多行键值对方式录入档期。直接发送如下格式（可复制后填写）：\n\n。录入档期\n时间段：\n恋综名：\n年份：\n状态：\n皮相：\n性向：\n主题：\n角色名：\n角色类型：\n性别：\n结局：\n\n时间段格式：MMDD MMDD（如 0315 0320）。未填写的字段默认为“未知”，年份默认为当前年。';
cmd_add.solve = (ctx, msg, cmdArgs) => {
    const rawMessage = msg.message.trim();
    const prefix = '。录入档期';
    let content = rawMessage.startsWith(prefix) ? rawMessage.substring(prefix.length).trim() : rawMessage;

    if (!content) {
        let template = '请按以下格式录入档期（可复制后填写）：\n\n。录入档期\n时间段：\n恋综名：\n年份：\n状态：\n皮相：\n性向：\n主题：\n角色名：\n角色类型：\n性别：\n结局：\n\n时间段格式示例：0315 0320';
        seal.replyToSender(ctx, msg, template);
        return seal.ext.newCmdExecuteResult(true);
    }

    const fieldMap = {
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

    let fields = {
        timeRange: null,
        name: null,
        startYear: getCurrentYear(),
        status: '未知',
        character: '未知',
        orientation: '未知',
        theme: '未知',
        roleName: '未知',
        roleType: '未知',
        gender: '未知',
        outcome: '未知'
    };

    let lines = content.split('\n');
    for (let line of lines) {
        line = line.trim();
        if (line === '') continue;

        let match = line.match(/^(.+?)[:：](.*)$/);
        if (!match) continue;

        let keyRaw = match[1].trim();
        let value = match[2].trim();

        let keyNorm = keyRaw.toLowerCase().replace(/\s+/g, '');
        let fieldKey = fieldMap[keyNorm] || fieldMap[keyRaw];
        if (!fieldKey) continue;

        if (fieldKey === 'startYear') {
            if (value === '') continue;
            let y = parseInt(value, 10);
            if (isNaN(y) || y < 1900 || y > 2100) {
                seal.replyToSender(ctx, msg, `❌ 年份“${value}”无效，请输入四位数字年份（如2025）或留空`);
                return seal.ext.newCmdExecuteResult(true);
            }
            fields.startYear = y;
        } else {
            if (value !== '') {
                fields[fieldKey] = value;
            }
        }
    }

    if (!fields.timeRange) {
        seal.replyToSender(ctx, msg, '❌ 缺少必填字段“时间段”，请填写例如 0315 0320');
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!fields.name) {
        seal.replyToSender(ctx, msg, '❌ 缺少必填字段“恋综名”，请填写恋综名称');
        return seal.ext.newCmdExecuteResult(true);
    }

    let parsed = parseTimeRange(fields.timeRange);
    if (!parsed.valid) {
        seal.replyToSender(ctx, msg, `❌ ${parsed.errorMsg}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let userData = getUserDataRef(ctx, msg);
    userData[fields.name] = {
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
    updateUserData(ctx, msg, userData);

    let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
    let hint = cross ? '（跨年，已自动拆分）' : '';

    let reply = `✅ 档期已录入${hint}：\n`;
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

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['录入档期'] = cmd_add;

// ======================== 修改档期 ========================
let cmd_modify = seal.ext.newCmdItemInfo();
cmd_modify.name = '修改';
cmd_modify.help = '。修改 恋综名 项目 内容 —— 修改指定恋综的某个字段。项目可以是：时间段、年份、状态、皮相、性向、主题、角色名、角色类型、性别。';
cmd_modify.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let field = cmdArgs.getArgN(2);
    let value = cmdArgs.getArgN(3);
    if (!name || !field || !value) {
        seal.replyToSender(ctx, msg, '❌ 参数不足，格式：。修改 恋综名 项目 内容');
        return seal.ext.newCmdExecuteResult(true);
    }

    const fieldMap = {
        '时间段': 'timeRange', '年份': 'startYear', '状态': 'status',
        '皮相': 'character', '性向': 'orientation', '主题': 'theme',
        '角色名': 'roleName', '角色类型': 'roleType', '性别': 'gender',
        'timerange': 'timeRange', 'year': 'startYear', 'status': 'status',
        'character': 'character', 'orientation': 'orientation', 'theme': 'theme',
        'rolename': 'roleName', 'roletype': 'roleType', 'gender': 'gender',
        '结局': 'outcome', 'outcome': 'outcome'
    };

    let fieldKey = fieldMap[field.toLowerCase ? field.toLowerCase() : field];
    if (!fieldKey) {
        seal.replyToSender(ctx, msg, '❌ 项目名称无效，可用项目：时间段、年份、状态、皮相、性向、主题、角色名、角色类型、性别');
        return seal.ext.newCmdExecuteResult(true);
    }

    let userData = getUserDataRef(ctx, msg);
    if (!userData[name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综“${name}”的档期`);
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

    updateUserData(ctx, msg, userData);
    seal.replyToSender(ctx, msg, `✅ 已修改 ${name} 的 ${field} 为：${value}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['修改'] = cmd_modify;

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

    let userData = getUserDataRef(ctx, msg);
    if (!userData[name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到恋综“${name}”的档期`);
        return seal.ext.newCmdExecuteResult(true);
    }

    delete userData[name];
    updateUserData(ctx, msg, userData);
    seal.replyToSender(ctx, msg, `✅ 已删除恋综“${name}”的档期`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['删除档期'] = cmd_delete;

// ======================== 我的日历（显示性别） ========================
let cmd_calendar = seal.ext.newCmdItemInfo();
cmd_calendar.name = '我的日历';
cmd_calendar.help = '。我的日历 —— 按年份分组显示所有档期（含角色信息、性别）';
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
        // 兼容旧数据，若没有则默认为“未知”
        let roleName = entry.roleName || '未知';
        let roleType = entry.roleType || '未知';
        let gender = entry.gender || '未知';
        let outcome = entry.outcome || '未知';  
        let parsed = parseTimeRange(timeRange);
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);

        // 构建角色信息字符串（如果非未知）
        let roleStr = '';
        if (roleName !== '未知' || roleType !== '未知' || gender !== '未知' || outcome !== '未知') {
            let parts = [];
            if (roleName !== '未知') parts.push(roleName);
            if (roleType !== '未知') parts.push(roleType);
            if (gender !== '未知') parts.push(gender);
            if (outcome !== '未知') parts.push(`结:${outcome}`);  
            roleStr = ` [${parts.join('/')}]`;
        }

        // 构建基本信息（过滤未知）
        let baseInfo = ` ${status} ${character} ${orientation} ${theme}`.replace(/未知/g, '').trim();
        if (baseInfo) baseInfo = ' · ' + baseInfo;

        if (cross) {
            // 第一段：startYear 年 startMonth.startDay ～ 12.31
            let first = `${startYear}/${parsed.startMonth.toString().padStart(2,'0')}${parsed.startDay.toString().padStart(2,'0')}-1231`;
            // 第二段：startYear+1 年 01.01 ～ endMonth.endDay
            let second = `${startYear+1}/0101-${parsed.endMonth.toString().padStart(2,'0')}${parsed.endDay.toString().padStart(2,'0')}`;

            if (!yearGroups[startYear]) yearGroups[startYear] = [];
            yearGroups[startYear].push({
                sort: startYear * 10000 + parsed.startMonth * 100 + parsed.startDay,
                line: `📌 ${name}${roleStr}\n   ${first}${baseInfo}`
            });
            if (!yearGroups[startYear+1]) yearGroups[startYear+1] = [];
            yearGroups[startYear+1].push({
                sort: (startYear+1) * 10000 + 1 * 100 + 1,
                line: `📌 ${name}${roleStr} (续)\n   ${second}${baseInfo}`
            });
        } else {
            let range = `${startYear}/${parsed.startMonth.toString().padStart(2,'0')}${parsed.startDay.toString().padStart(2,'0')}-${parsed.endMonth.toString().padStart(2,'0')}${parsed.endDay.toString().padStart(2,'0')}`;
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
    
    // 替换为分段发送
    sendLongMessage(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['我的日历'] = cmd_calendar;

// ======================== 本月档期（智能识别参数顺序） ========================
let cmd_this_month = seal.ext.newCmdItemInfo();
cmd_this_month.name = '本月档期';
cmd_this_month.help = '。本月档期 [年份] [月份] 或 [月份] [年份] —— 显示指定年月的空闲日期区间。缺省年份为今年，缺省月份为当月。';
cmd_this_month.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let now = new Date();
    let targetYear, targetMonth;

    let arg1 = cmdArgs.getArgN(1);
    let arg2 = cmdArgs.getArgN(2);

    const isValidYear = (y) => !isNaN(y) && y >= 1900 && y <= 2100;
    const isValidMonth = (m) => !isNaN(m) && m >= 1 && m <= 12;

    if (arg1 && arg2) {
        let num1 = parseInt(arg1, 10);
        let num2 = parseInt(arg2, 10);

        if (isValidYear(num1) && isValidMonth(num2)) {
            targetYear = num1;
            targetMonth = num2;
        } else if (isValidMonth(num1) && isValidYear(num2)) {
            targetYear = num2;
            targetMonth = num1;
        } else {
            seal.replyToSender(ctx, msg, '❌ 参数无效，请提供合法的年份（1900-2100）和月份（1-12）');
            return seal.ext.newCmdExecuteResult(true);
        }
    } else if (arg1 && !arg2) {
        let month = parseInt(arg1, 10);
        if (!isValidMonth(month)) {
            seal.replyToSender(ctx, msg, '❌ 月份无效，请输入 1-12 之间的数字');
            return seal.ext.newCmdExecuteResult(true);
        }
        targetMonth = month;
        targetYear = now.getFullYear();
    } else {
        targetYear = now.getFullYear();
        targetMonth = now.getMonth() + 1;
    }

    let daysInMonth = getDaysInMonth(targetYear, targetMonth);
    let occupied = new Array(daysInMonth + 1).fill(false);

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

        let startDayInMonth = 1;
        let endDayInMonth = daysInMonth;

        if (startYear === targetYear && parsed.startMonth === targetMonth) {
            startDayInMonth = parsed.startDay;
        }
        if (startYear < targetYear && targetMonth === 1 && cross) {
            startDayInMonth = 1;
        }
        if (endYear === targetYear && parsed.endMonth === targetMonth) {
            endDayInMonth = parsed.endDay;
        }
        if (endYear > targetYear && targetMonth === 12 && cross) {
            endDayInMonth = daysInMonth;
        }

        for (let d = startDayInMonth; d <= endDayInMonth; d++) {
            occupied[d] = true;
        }
    }

    let freeIntervals = [];
    let start = null;
    for (let d = 1; d <= daysInMonth; d++) {
        if (!occupied[d] && start === null) start = d;
        if (occupied[d] && start !== null) {
            freeIntervals.push({ start, end: d - 1 });
            start = null;
        }
    }
    if (start !== null) freeIntervals.push({ start, end: daysInMonth });

    if (freeIntervals.length === 0) {
        seal.replyToSender(ctx, msg, `📅 ${targetYear}年${targetMonth}月 整月无空闲（全部被档期覆盖）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let rangeStr = freeIntervals.map(iv => {
        if (iv.start === iv.end) return `${iv.start.toString().padStart(2,'0')}`;
        else return `${iv.start.toString().padStart(2,'0')}-${iv.end.toString().padStart(2,'0')}`;
    }).join('、');

    seal.replyToSender(ctx, msg, `📅 ${targetYear}年${targetMonth}月 空闲日期：\n${rangeStr}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['本月档期'] = cmd_this_month;

// ======================== 本年数据 ========================
let cmd_year_data = seal.ext.newCmdItemInfo();
cmd_year_data.name = '本年数据';
cmd_year_data.help = '。本年数据 [年份] —— 统计指定年份（缺省为今年）的档期总数、皮相列表、性向分布、性别分布、结局分布百分比、语擦天数（去重）。若缺省，统计至今日。';
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
        targetStart = targetYear * 10000 + 1 * 100 + 1;
        targetEnd = targetYear * 10000 + 12 * 100 + 31;
        yearLabel = `${targetYear}年`;
    } else {
        targetYear = now.getFullYear();
        let month = now.getMonth() + 1;
        let day = now.getDate();
        targetStart = targetYear * 10000 + 1 * 100 + 1;
        targetEnd = targetYear * 10000 + month * 100 + day;
        yearLabel = `${targetYear}年（截至今日）`;
    }

    let totalLianZong = 0;
    let characters = [];
    let orientations = [];
    let genders = [];
    let outcomes = [];

    let activeRanges = [];

    for (let name in userData) {
        let entry = userData[name];
        let { startYear, timeRange, character, orientation } = entry;
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

        let rangeStart = Math.max(startVal, targetStart);
        let rangeEnd = Math.min(endVal, targetEnd);
        activeRanges.push({ start: rangeStart, end: rangeEnd });
    }

    // 计算语擦天数
    let startYear = Math.floor(targetStart / 10000);
    let startMonth = Math.floor((targetStart % 10000) / 100);
    let startDay = targetStart % 100;
    let endYear = Math.floor(targetEnd / 10000);
    let endMonth = Math.floor((targetEnd % 10000) / 100);
    let endDay = targetEnd % 100;

    let totalDaysInRange = 0;
    let coveredDays = 0;
    let weekdayCovered = 0;
    let weekendCovered = 0;

    let currentDate = new Date(startYear, startMonth - 1, startDay);
    let endDate = new Date(endYear, endMonth - 1, endDay);
    endDate.setHours(23, 59, 59, 999);

    while (currentDate <= endDate) {
        totalDaysInRange++;
        let currentVal = currentDate.getFullYear() * 10000 + (currentDate.getMonth() + 1) * 100 + currentDate.getDate();

        let isCovered = false;
        for (let range of activeRanges) {
            if (currentVal >= range.start && currentVal <= range.end) {
                isCovered = true;
                break;
            }
        }

        if (isCovered) {
            coveredDays++;
            let dayOfWeek = currentDate.getDay();
            if (dayOfWeek === 0 || dayOfWeek === 6) {
                weekendCovered++;
            } else {
                weekdayCovered++;
            }
        }

        currentDate.setDate(currentDate.getDate() + 1);
    }

    let coveredPercent = totalDaysInRange > 0 ? (coveredDays / totalDaysInRange * 100).toFixed(1) : '0.0';

    // 构建回复
    let reply = `📊 【${yearLabel}数据】\n══════════════\n📌 涉及的恋综：${totalLianZong} 个\n`;

    if (characters.length > 0) {
        reply += `\n🎭 皮相（非未知）：\n`;
        characters.forEach(c => reply += `   · ${c.name} ： ${c.character}\n`);
    } else {
        reply += `\n🎭 皮相：无记录\n`;
    }

    if (orientations.length > 0) {
        let countMap = {};
        orientations.forEach(o => countMap[o] = (countMap[o] || 0) + 1);
        let totalOri = orientations.length;
        reply += `\n❤️ 性向分布（共 ${totalOri} 个非未知）：\n`;
        let sorted = Object.entries(countMap).sort((a, b) => b[1] - a[1]);
        sorted.forEach(([ori, cnt]) => {
            let percent = (cnt / totalOri * 100).toFixed(1);
            reply += `   ${ori} ： ${cnt} (${percent}%)\n`;
        });
    } else {
        reply += `\n❤️ 性向：无非未知记录\n`;
    }

    if (genders.length > 0) {
        let countMap = {};
        genders.forEach(g => countMap[g] = (countMap[g] || 0) + 1);
        let totalGender = genders.length;
        reply += `\n🚻 性别分布（共 ${totalGender} 个非未知）：\n`;
        let sorted = Object.entries(countMap).sort((a, b) => b[1] - a[1]);
        sorted.forEach(([gen, cnt]) => {
            let percent = (cnt / totalGender * 100).toFixed(1);
            reply += `   ${gen} ： ${cnt} (${percent}%)\n`;
        });
    } else {
        reply += `\n🚻 性别：无非未知记录\n`;
    }

    if (outcomes.length > 0) {
        let countMap = {};
        outcomes.forEach(o => countMap[o] = (countMap[o] || 0) + 1);
        let totalOutcome = outcomes.length;
        reply += `\n🎬 结局分布（共 ${totalOutcome} 个非未知）：\n`;
        let sorted = Object.entries(countMap).sort((a, b) => b[1] - a[1]);
        sorted.forEach(([out, cnt]) => {
            let percent = (cnt / totalOutcome * 100).toFixed(1);
            reply += `   ${out} ： ${cnt} (${percent}%)\n`;
        });
    } else {
        reply += `\n🎬 结局：无非未知记录\n`;
    }

    reply += `\n📅 语擦天数：${coveredDays} 天（占 ${coveredPercent}%）\n`;
    reply += `   · 周中：${weekdayCovered} 天\n`;
    reply += `   · 周末：${weekendCovered} 天\n`;

    reply += '══════════════';
    
    // 替换为分段发送
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

    let now = new Date();
    let targetYear, targetMonth;

    let arg1 = cmdArgs.getArgN(1);
    let arg2 = cmdArgs.getArgN(2);

    const isValidYear = (y) => !isNaN(y) && y >= 1900 && y <= 2100;
    const isValidMonth = (m) => !isNaN(m) && m >= 1 && m <= 12;

    if (arg1 && arg2) {
        let num1 = parseInt(arg1, 10);
        let num2 = parseInt(arg2, 10);

        if (isValidYear(num1) && isValidMonth(num2)) {
            targetYear = num1;
            targetMonth = num2;
        } else if (isValidMonth(num1) && isValidYear(num2)) {
            targetYear = num2;
            targetMonth = num1;
        } else {
            seal.replyToSender(ctx, msg, '❌ 参数无效，请提供合法的年份（1900-2100）和月份（1-12）');
            return seal.ext.newCmdExecuteResult(true);
        }
    } else if (arg1 && !arg2) {
        let month = parseInt(arg1, 10);
        if (!isValidMonth(month)) {
            seal.replyToSender(ctx, msg, '❌ 月份无效，请输入 1-12 之间的数字');
            return seal.ext.newCmdExecuteResult(true);
        }
        targetMonth = month;
        targetYear = now.getFullYear();
    } else {
        targetYear = now.getFullYear();
        targetMonth = now.getMonth() + 1;
    }

    let daysInMonth = getDaysInMonth(targetYear, targetMonth);
    let occupied = new Array(daysInMonth + 1).fill(false);

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

        let startDayInMonth = 1;
        let endDayInMonth = daysInMonth;

        if (startYear === targetYear && parsed.startMonth === targetMonth) {
            startDayInMonth = parsed.startDay;
        }
        if (startYear < targetYear && targetMonth === 1 && cross) {
            startDayInMonth = 1;
        }
        if (endYear === targetYear && parsed.endMonth === targetMonth) {
            endDayInMonth = parsed.endDay;
        }
        if (endYear > targetYear && targetMonth === 12 && cross) {
            endDayInMonth = daysInMonth;
        }

        for (let d = startDayInMonth; d <= endDayInMonth; d++) {
            occupied[d] = true;
        }
    }

    // 构建日历
    let firstDay = getFirstDayOfMonth(targetYear, targetMonth);
    let weekdays = ['日', '一', '二', '三', '四', '五', '六'];
    let header = weekdays.join(' ');
    let lines = [];

    let line = '';
    for (let i = 0; i < firstDay; i++) {
        line += '   ';
    }

    for (let d = 1; d <= daysInMonth; d++) {
        let dayStr = d.toString().padStart(2, ' ');
        if (occupied[d]) {
            dayStr = `[${dayStr}]`;
        } else {
            dayStr = ` ${dayStr} `;
        }
        line += dayStr;
        if ((firstDay + d) % 7 === 0 || d === daysInMonth) {
            lines.push(line);
            line = '';
        }
    }

    let reply = `📅 ${targetYear}年${targetMonth}月 档期视图\n`;
    reply += `${header}\n`;
    lines.forEach(l => reply += l + '\n');
    reply += '注：[数字] 表示该日有档期';
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['月视图'] = cmd_month_view;