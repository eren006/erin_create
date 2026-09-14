// ==UserScript==
// @name         语擦助手（含卡救星）
// @author       机械飞升宗·长日将尽
// @version      3.7.0
// @description  语擦档期管理 + 卡片救星 二合一：档期录入/查询/统计/月历图/结局分布图/下一场倒计时/答案之书/塔罗/灵签，叠加卡片录入/预警/急救箱/一键下单转发，并新增两者的联动展示与结局回填提醒。机械飞升宗出品。
// @timestamp    1787788800
// @diceRequireVer 1.2.0
// @license      CC BY-NC-SA
// ==/UserScript==

/**
 * 机械飞升宗出品。
 *
 * 二合一说明（v3.0.0，2026-08-26）：
 * 本文件把原来的「语擦助手」（语擦日历新.js）和「卡救星」（卡救星.js）合并成一份脚本，
 * 但两者仍各自以独立扩展名注册（yuca_helper / card_savior），存储 key 也完全不变
 * （yuca_helper_data / card_savior_fixed_data）。所以老数据不用做任何迁移，
 * 直接用本文件替换服务器上原来的两个脚本文件即可，指令名称也全部保留。
 *
 * 这次顺带做的优化：
 * 1. 卡片新增可选字段「关联恋综」：录入/修改卡片时可以填一个恋综名。
 * 2. 。本月档期 现在会在档期信息后面追加"卡片提醒"区块：
 *    展示 7 天内到期的卡片，并且如果某张卡关联的恋综本月正好在档，会标出来。
 *    这样不用分别查两个插件，一条指令就能看到"这个月要用哪些卡"。
 * 3. 到期提醒合并成同一个定时器：卡片到期前 10/5/3 天提醒（沿用原逻辑），
 *    新增档期开始前 3/1 天提醒，且提醒文本里会带上关联卡片的库存/到期情况。
 * 4. 卡救星原有指令补全了 help 文本（方便用 SealDice 自带的帮助系统查看用法）、
 *    数量/价格的数字校验、新增「卡救星帮助」指令；
 *    修复了「已下单」在卡片不存在时 return 值不规范的问题；
 *    「卡片列表」改成按长度自动分段（复用语擦助手的 sendLongMessage），
 *    不再固定"每 5 张分一条"，避免卡片描述变长后错位。
 *
 * v3.1.0 新增（2026-08-26）：
 * - 。下一场：显示正在进行中的档期 + 最近一场即将开始的档期倒计时
 * - 结局回填提醒：档期结束 3 天后，如果「结局」字段还是"未知"，自动私聊提醒一次，
 *   避免「本年数据」里的结局分布因为忘填而一直缺一大块
 *
 * v3.2.0 新增（2026-08-26）：
 * - 。答案之书 [问题]：纯娱乐向小工具，随机翻一页当答案
 *
 * v3.3.0 新增（2026-08-26）：
 * - 。下单 卡名\n内容：把内容（支持换行、图片）自动转发到该卡绑定的群，
 *   不管在哪发这条指令都会发到绑定群，同时消耗 1 张库存。
 *   群号来源：在目标群里。录入卡片会自动绑定当前群；也可以事后用
 *   。修改卡片 卡名 群号 群号数字 手动补绑（纯数字会自动补 QQ-Group: 前缀）。
 * - 。塔罗单张 [问题]：抽一张大阿尔卡纳（22张），含正/逆位具体解读
 * - 。灵签 [问题]：抽一支中式灵签（20签，上上签～下下签），含签诗和解签
 *
 * v3.4.0 新增（2026-08-26）：
 * - 。月历图 [年] [月]：图片版月历，按恋综上色标出在档日期，图例含时间段和角色名
 * - 。结局分布图 [年份]：结局（HE/BE/OE/开放式）分布饼图
 *   两者都需要本机先启动图片渲染服务：node board_server.js（和「恋综：战棋」共用同一个
 *   服务/同一个端口 8855，board_server.js 已扩展出 /calendar /pie 两个接口）。
 *   服务没启动或生成失败时会自动回退成一句文字提示，不影响其它指令正常使用。
 *   生成的 PNG 只是服务端的中间产物，转成 base64 发出去之后立刻在服务端删除，
 *   不会在本地堆积图片文件（发到群里的这张图本身仍然是普通消息，撤不撤由你自己判断）。
 *
 * v3.5.0 修复（2026-08-28）：
 * - 。我的日历 不带年份参数时，改为只显示各年份的档期条数概览，不再一次性把所有年份
 *   的全部详情拼成一长串消息刷屏（记录多的人以前可能被拆成好几条消息连发）。
 *   要看某一年的具体条目，加上年份参数：。我的日历 2025
 *
 * v3.6.0 新增（2026-08-28）：
 * - 长消息支持合并转发：在海豹「yuca_helper」扩展配置里填写 ws地址 / ws Access token
 *   （协议端正向 WebSocket，参考同作者「长日系统」的实现，LLOneBot/NapCat/go-cqhttp
 *   等 OneBot v11 协议端都适用），配置后群聊里的长消息（我的日历、本月档期、本年数据、
 *   卡片列表）会自动改用合并转发发送，不再刷屏成好几条消息。
 *   没配置、私聊场景、或者合并转发请求失败/超时，都会自动回退成原来的分段普通消息，
 *   不影响原有功能。
 *
 * v3.7.0 新增（2026-08-28）：
 * - 。导出档期 [年份|全部] / 。导入档期 数据：跨机器人迁移数据。
 *   旧版语擦助手（语擦日历新.js）也同步加了。导出档期，两边数据互通：
 *   旧版导出 → 新版导入，或者新版之间互相导出导入都可以。
 *   导出的是纯文本（JSON），数据多时自动拆成多条消息，每条都要单独完整发给
 *   对方的。导入档期；同名恋综导入时会被覆盖更新，不会重复。
 */

// ======================== 扩展注册（保持独立，存储互不影响） ========================

let extCalendar = seal.ext.find('yuca_helper');
if (!extCalendar) {
    extCalendar = seal.ext.new('yuca_helper', '机械飞升宗·长日将尽', '3.7.0');
    seal.ext.register(extCalendar);
}

let extCard = seal.ext.find('card_savior');
if (!extCard) {
    extCard = seal.ext.new('card_savior', '机械飞升宗·长日将尽', '3.5.0');
    seal.ext.register(extCard);
}

// 合并转发用的协议端连接配置（只在 yuca_helper 这一个扩展下配一次，卡救星那边共用）。
// 参考同作者「长日系统」的实现：短连接 WebSocket + echo 匹配，不做常驻连接。
seal.ext.registerStringConfig(extCalendar, 'ws地址', '', '协议端正向WebSocket地址（如 ws://127.0.0.1:3001），配了之后群里的长消息会用合并转发发送；留空则退回普通分段消息');
seal.ext.registerStringConfig(extCalendar, 'ws Access token', '', '对应协议端的 access_token，没有则留空');
seal.ext.registerStringConfig(extCalendar, '图片服务地址', 'http://127.0.0.1:8855', '本地图片渲染服务地址，修改 board_server.js 端口后请同步修改这里');

// ======================== 通用工具 ========================

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

// ======================== 合并转发桥接（短连接 WS，参考长日系统同款实现） ========================
// 调协议端自己的 OneBot 动作（send_group_forward_msg），不是海豹自带能力。
// 没配置 ws地址、不在群聊里、或者请求失败/超时，统一回退成 sendLongMessage 的分段普通消息。

const WSM = {
    seq: 0,
    buildUrl() {
        let url = seal.ext.getStringConfig(extCalendar, 'ws地址') || '';
        const token = seal.ext.getStringConfig(extCalendar, 'ws Access token');
        if (url && token) {
            url += (url.includes('?') ? '&' : '?') + 'access_token=' + encodeURIComponent(token);
        }
        return url;
    },
    // 发起一次短连接请求；onResponse 收到完整 response 对象，超时/失败走 onTimeout
    request(postData, onResponse, onTimeout, timeoutMs = 5000) {
        const echo = postData.action + '_' + Date.now() + '_' + (this.seq++);
        postData.echo = echo;
        let payload;
        try { payload = JSON.stringify(postData); } catch (e) { if (onTimeout) onTimeout(); return; }

        const url = this.buildUrl();
        if (!url) { if (onTimeout) onTimeout(); return; }

        let conn;
        try { conn = new WebSocket(url); } catch (e) { if (onTimeout) onTimeout(); return; }

        let done = false;
        const finish = () => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            if (conn.readyState === WebSocket.OPEN || conn.readyState === WebSocket.CONNECTING) {
                try { conn.close(1000, 'DONE'); } catch (e) { /* 忽略 */ }
            }
        };
        const timer = setTimeout(() => {
            if (!done) { finish(); if (onTimeout) onTimeout(); }
        }, timeoutMs);

        conn.onopen = () => {
            try { conn.send(payload); } catch (e) { finish(); if (onTimeout) onTimeout(); }
        };
        conn.onmessage = (event) => {
            if (done) return;
            let response;
            try { response = JSON.parse(event.data); } catch (e) { return; }
            if (response.post_type === 'meta_event') return;
            if (response.echo !== echo) return;
            finish();
            try { onResponse(response); } catch (e) { console.log('[语擦助手] WS 回调异常:', e.message); }
        };
        conn.onerror = () => { /* onclose 会跟着触发，统一在那边处理失败 */ };
        conn.onclose = () => {
            if (!done) { done = true; clearTimeout(timer); if (onTimeout) onTimeout(); }
        };
    }
};

// 长内容优先用合并转发发出去（群聊+已配置 ws地址时）；否则/失败时回退成分段普通消息
function sendAsForward(ctx, msg, nodeName, text, maxLen = 1500) {
    if (text.length <= maxLen) {
        seal.replyToSender(ctx, msg, text);
        return;
    }
    if (!msg.groupId || !WSM.buildUrl()) {
        sendLongMessage(ctx, msg, text, maxLen);
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

    let botUid = ctx.endPoint.userId;
    let nodes = chunks.map(chunk => ({
        type: 'node',
        data: { name: nodeName, uin: botUid, content: chunk.trim() }
    }));
    let groupId = parseInt(String(msg.groupId).replace(/[^\d]/g, ''), 10);

    WSM.request(
        { action: 'send_group_forward_msg', params: { group_id: groupId, messages: nodes } },
        (response) => {
            if (!(response.status === 'ok' || response.retcode === 0)) {
                console.log('[语擦助手] 合并转发被协议端拒绝，回退分段消息:', JSON.stringify(response));
                sendLongMessage(ctx, msg, text, maxLen);
            }
        },
        () => {
            console.log('[语擦助手] 合并转发请求超时/连接失败，回退分段消息');
            sendLongMessage(ctx, msg, text, maxLen);
        }
    );
}

// 卡片到期用的日期差（YYYY-MM-DD 绝对日期）
function getDaysDiff(dateStr) {
    const target = new Date(dateStr);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const diffTime = target - now;
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

function formatTime(timestamp) {
    if (!timestamp) return '尚未下单';
    const d = new Date(timestamp);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`;
}

// ======================== 本地图片渲染服务桥接（月历图 / 结局分布图） ========================
// 依赖同一台机器上运行的 Node 图片服务（board_server.js，和「恋综：战棋」共用同一个服务，默认端口 8855）。
// 服务没启动时 fetch 会失败，这里统一 try/catch 兜底，调用方自行决定失败后的文字回退方案。

function assignShowColors(showNames) {
    let showColor = {};
    // 名称哈希决定色相，保证同一恋综跨月份始终使用同一颜色。
    showNames.forEach(name => {
        let hash = 2166136261;
        for (let i = 0; i < name.length; i++) {
            hash ^= name.charCodeAt(i);
            hash = Math.imul(hash, 16777619);
        }
        const hue = (hash >>> 0) % 360;
        const s = 58, l = 82;
        const c = (1 - Math.abs(2 * l / 100 - 1)) * s / 100;
        const x = c * (1 - Math.abs((hue / 60) % 2 - 1));
        const m = l / 100 - c / 2;
        let rgb = hue < 60 ? [c, x, 0] : hue < 120 ? [x, c, 0] : hue < 180 ? [0, c, x]
            : hue < 240 ? [0, x, c] : hue < 300 ? [x, 0, c] : [c, 0, x];
        showColor[name] = rgb.map(v => Math.round((v + m) * 255));
    });
    return showColor;
}

async function fetchRenderBase64(routePath, payload) {
    try {
        let serverUrl = (seal.ext.getStringConfig(extCalendar, '图片服务地址') || 'http://127.0.0.1:8855').replace(/\/$/, '');
        const res = await fetch(`${serverUrl}${routePath}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res || !res.ok) throw new Error('图片服务无响应');
        const result = await res.json();
        if (!result.ok) throw new Error(result.error || '图片生成失败');
        if (!result.url) throw new Error('图片服务返回结果缺少 url 字段，请确认 board_server.js 是不是最新版');
        return { url: result.url, error: null };
    } catch (e) {
        const errMsg = (e && e.message) || String(e);
        console.log('[语擦助手] 图片生成失败:', errMsg);
        return { url: '', error: errMsg };
    }
}

// 异步拉取图片并发送；solve 函数本身保持同步返回，图片走 promise 链异步补发（同「恋综：战棋」的模式）
// onFail 收到真实报错文本，方便直接在回复里带出原因，不用翻服务端/海豹日志
//
// 直接用图片服务返回的 http:// 网址发送，而不是塞整段 base64（太长会被海豹按
// 长度自动拆成一堆碎文本）或者用 seal.base64ToImage() 转成本地文件路径（部分
// QQ 协议端出于安全考虑会拒绝 file:// 本地路径，报"资源路径受限"）。http 网址
// 这种引用方式是所有协议端都通用支持的写法。
function sendRenderedImage(ctx, msg, routePath, payload, onFail) {
    fetchRenderBase64(routePath, payload)
        .then(({ url, error }) => {
            if (url) {
                seal.replyToSender(ctx, msg, `[CQ:image,file=${url}]`);
            } else if (onFail) {
                onFail(error || '未知错误');
            }
        })
        .catch(e => { if (onFail) onFail((e && e.message) || String(e)); });
}

// ======================== 语擦助手：存储 ========================

const CALENDAR_STORAGE_KEY = 'yuca_helper_data';

function readAllData() {
    let raw = extCalendar.storageGet(CALENDAR_STORAGE_KEY);
    if (raw) {
        try { return JSON.parse(raw); } catch (e) { return {}; }
    }
    return {};
}

function saveAllData(data) {
    extCalendar.storageSet(CALENDAR_STORAGE_KEY, JSON.stringify(data));
}

function getUserData(ctx, msg) {
    return readAllData()[msg.sender.userId] || {};
}

// ======================== 语擦助手：时间工具 ========================

function getCurrentYear() { return new Date().getFullYear(); }
function getDaysInMonth(year, month) { return new Date(year, month, 0).getDate(); }
function getFirstDayOfMonth(year, month) { return new Date(year, month - 1, 1).getDay(); }

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

    if (em === sm && ed <= sd) {
        return { valid: false, errorMsg: '同月时结束日必须大于开始日' };
    }

    return { valid: true, startMonth: sm, startDay: sd, endMonth: em, endDay: ed, errorMsg: '' };
}

function isCrossYear(endMonth, startMonth) {
    return endMonth < startMonth;
}

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

// 按天列出当月在档的恋综名（供月历图渲染用），逻辑同 calcMonthOccupied，只是记录到每一天而非布尔值
function buildDayShowsForMonth(userData, targetYear, targetMonth) {
    let daysInMonth = getDaysInMonth(targetYear, targetMonth);
    let dayShows = {};

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

        for (let d = startDay; d <= endDay; d++) {
            if (!dayShows[d]) dayShows[d] = [];
            dayShows[d].push(name);
        }
    }

    return dayShows;
}

function buildYearOverview(userData, targetYear) {
    let months = [];
    let activeNames = new Set();
    let occupiedDays = 0;
    let conflictDays = 0;
    let busiestMonth = 1;
    let busiestScore = -1;

    for (let month = 1; month <= 12; month++) {
        let dayShows = buildDayShowsForMonth(userData, targetYear, month);
        let dayCounts = {};
        let monthScore = 0;
        Object.keys(dayShows).forEach(day => {
            let uniqueShows = Array.from(new Set(dayShows[day]));
            dayCounts[day] = uniqueShows.length;
            monthScore += uniqueShows.length;
            occupiedDays++;
            if (uniqueShows.length > 1) conflictDays++;
            uniqueShows.forEach(name => activeNames.add(name));
        });
        if (monthScore > busiestScore) {
            busiestScore = monthScore;
            busiestMonth = month;
        }
        months.push({ month, dayCounts });
    }

    return {
        months,
        summary: {
            totalShows: activeNames.size,
            occupiedDays,
            conflictDays,
            busiestMonth: activeNames.size ? busiestMonth : 0
        }
    };
}

function formatTimeRangeDisplay(timeRange) {
    let parsed = parseTimeRange(timeRange || '');
    if (!parsed.valid) return '';
    const pad = n => n.toString().padStart(2, '0');
    return `${pad(parsed.startMonth)}.${pad(parsed.startDay)}-${pad(parsed.endMonth)}.${pad(parsed.endDay)}`;
}

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

// ======================== 卡救星：存储 ========================

const CARD_STORAGE_KEY = 'card_savior_fixed_data';
const VALID_TYPES = ['板写', '溶图', '溶写', '其他'];

function getData() {
    let raw = extCard.storageGet(CARD_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
}

function saveData(data) {
    extCard.storageSet(CARD_STORAGE_KEY, JSON.stringify(data));
}

// 手动填群号时允许只写纯数字群号，自动补上 QQ-Group: 前缀；
// 已经是完整格式（含冒号）的值原样保留，不重复处理。
function normalizeGroupId(value) {
    if (/^\d+$/.test(value)) {
        return `QQ-Group:${value}`;
    }
    return value;
}

// ======================== 联动：卡片提醒区块（供。本月档期使用） ========================

function buildCardAlertSection(uid, activeShows) {
    let cardAll = getData();
    let userCards = cardAll[uid] || {};
    let cardNames = Object.keys(userCards);
    if (cardNames.length === 0) return '';

    const ALERT_DAYS = 7;
    let upcoming = [];
    let expiredCount = 0;

    for (let n of cardNames) {
        let c = userCards[n];
        let d = getDaysDiff(c.expiry);
        if (d < 0) { expiredCount++; continue; }
        if (d <= ALERT_DAYS) upcoming.push({ card: c, days: d });
    }
    upcoming.sort((a, b) => a.days - b.days);

    let activeShowNames = new Set(activeShows.map(s => s.name));

    let section = '\n🃏 卡片提醒（卡救星）\n──────────────\n';
    if (upcoming.length === 0 && expiredCount === 0) {
        section += '  近期无需关注的卡片\n';
        return section;
    }

    upcoming.forEach(({ card, days }) => {
        let linked = card.relatedShow && activeShowNames.has(card.relatedShow) ? ' 🔗本月在档' : '';
        section += `  · ${card.name}（${card.type}）剩 ${days} 天 | 库存 ${card.quantity}${linked}\n`;
    });
    if (expiredCount > 0) {
        section += `  ⚠️ 另有 ${expiredCount} 张已过期未清理（发送。清理过期）\n`;
    }
    return section;
}

// ======================== 语擦助手：档期帮助 ========================

let cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = '档期帮助';
cmd_help.help = '。档期帮助 —— 显示所有可用指令';
cmd_help.solve = (ctx, msg, cmdArgs) => {
    let help = `📅 【语擦助手 v3.6 指令列表】
══════════════
📝 录入与管理
  。录入档期          录入新档期（多行键值格式）
  。修改 名 项 值     修改指定字段
  。重命名档期 旧 新  重命名恋综（保留所有数据）
  。删除档期 名       删除指定档期

🔍 查询
  。查档期 名             查看档期完整详情
  。我的日历 [年份]       不带年份看概览，带年份看该年具体档期
  。本月档期 [年] [月]    本月在档恋综、空闲日期 + 卡片提醒
  。月视图   [年] [月]    日历视图（文字版，标记有档期日）
  。月历图   [年] [月]    日历视图（图片版，见下方💡）
  。年度总览图 [年]      全年档期热力图（图片版）
  。下一场                正在进行的档期 + 最近一场倒计时

🎱 娱乐
  。答案之书 [问题]   随机翻一页当答案，图一乐
  。塔罗单张 [问题]   抽一张大阿尔卡纳塔罗，含正逆位解读
  。灵签 [问题]       抽一支中式灵签，含签诗和解签

📊 统计
  。本年数据 [年]     年度数据统计（文字版）
  。结局分布图 [年]   结局分布饼图（图片版，见下方💡）

🃏 卡片联动（详见。卡救星帮助）
  。录入卡片 / 卡片列表 / 急救箱 / 下单 等
  卡片可选填「关联恋综」，本月在档时会在。本月档期里被标出来

📦 迁移
  。导出档期 [年份|全部]   导出数据，可以迁移到其它机器人（旧版/新版互通）
  。导入档期 数据          接收对方。导出档期 发的数据

💡 时间段格式：MMDD MMDD
   同年示例：0315 0320（3月15日至3月20日）
   跨年示例：1201 0201（12月1日至次年2月1日）
💡 档期结束 3 天后如果「结局」还没填，会自动私聊提醒一次
💡「月历图」「年度总览图」「结局分布图」需要本机先启动图片渲染服务（node board_server.js，
   和「恋综：战棋」共用同一个服务），没启动时会自动回退成文字提示，不影响其它指令
══════════════`;
    seal.replyToSender(ctx, msg, help);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['档期帮助'] = cmd_help;

// ======================== 语擦助手：录入档期 ========================

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
        outcome: fields.outcome,
        reminded: [],
        outcomeReminded: false
    };
    saveAllData(all);

    let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
    let hint = cross ? '（跨年，将自动拆分显示）' : '';
    let action = isUpdate ? '已更新' : '已录入';

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
extCalendar.cmdMap['录入档期'] = cmd_add;

// ======================== 语擦助手：查档期 ========================

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
extCalendar.cmdMap['查档期'] = cmd_query;

// ======================== 语擦助手：修改档期 ========================

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
        userData[name].reminded = [];
        userData[name].outcomeReminded = false;
    } else if (fieldKey === 'startYear') {
        let year = parseInt(value, 10);
        if (isNaN(year) || year < 1900 || year > 2100) {
            seal.replyToSender(ctx, msg, '❌ 年份无效，请输入四位数字年份（如2025）');
            return seal.ext.newCmdExecuteResult(true);
        }
        userData[name].startYear = year;
        userData[name].reminded = [];
        userData[name].outcomeReminded = false;
    } else {
        userData[name][fieldKey] = value;
    }

    all[uid] = userData;
    saveAllData(all);
    seal.replyToSender(ctx, msg, `✅ 已修改「${name}」的 ${field} 为：${value}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['修改'] = cmd_modify;

// ======================== 语擦助手：重命名档期 ========================

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

    // 联动：同步更新指向该恋综的卡片关联字段，避免重命名后卡片关联失效
    let cardAll = getData();
    let userCards = cardAll[uid];
    if (userCards) {
        let synced = 0;
        for (let n in userCards) {
            if (userCards[n].relatedShow === oldName) {
                userCards[n].relatedShow = newName;
                synced++;
            }
        }
        if (synced > 0) saveData(cardAll);
    }
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['重命名档期'] = cmd_rename;

// ======================== 语擦助手：删除档期 ========================

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
extCalendar.cmdMap['删除档期'] = cmd_delete;

// ======================== 语擦助手：我的日历 ========================

let cmd_calendar = seal.ext.newCmdItemInfo();
cmd_calendar.name = '我的日历';
cmd_calendar.help = '。我的日历 [年份] —— 不带年份：显示各年份档期数量概览；带年份：显示该年所有档期详情（含角色信息、性别、结局）';
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

    let sortedYears = Object.keys(yearGroups).map(Number).sort((a, b) => a - b);

    // 不带年份参数：只显示各年份条目数概览，避免记录多的人一次性刷出一长串消息
    let yearParam = cmdArgs.getArgN(1);
    if (!yearParam) {
        let reply = '📅 【我的档期日历 · 年份概览】\n══════════════\n';
        sortedYears.forEach(year => {
            reply += `✨ ${year} 年：${yearGroups[year].length} 条\n`;
        });
        reply += '══════════════\n💡 发送。我的日历 年份 查看该年具体条目，例如：。我的日历 ' + sortedYears[0];
        seal.replyToSender(ctx, msg, reply);
        return seal.ext.newCmdExecuteResult(true);
    }

    let targetYear = parseInt(yearParam, 10);
    if (isNaN(targetYear) || !yearGroups[targetYear]) {
        seal.replyToSender(ctx, msg, `❌ ${yearParam} 年没有档期记录。可用年份：${sortedYears.join('、')}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = `📅 【我的档期日历 · ${targetYear} 年】\n══════════════\n`;
    yearGroups[targetYear].forEach(item => { reply += item.line + '\n'; });
    reply += '══════════════';

    sendAsForward(ctx, msg, '语擦助手', reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['我的日历'] = cmd_calendar;

// ======================== 语擦助手：本月档期（含卡片提醒联动） ========================

let cmd_this_month = seal.ext.newCmdItemInfo();
cmd_this_month.name = '本月档期';
cmd_this_month.help = '。本月档期 [年份] [月份] 或 [月份] [年份] —— 显示指定年月的在档恋综、空闲日期，以及 7 天内到期/关联在档恋综的卡片提醒';
cmd_this_month.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);

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

    reply += buildCardAlertSection(msg.sender.userId, activeShows);
    reply += '══════════════';

    sendAsForward(ctx, msg, '语擦助手', reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['本月档期'] = cmd_this_month;

// ======================== 语擦助手：本年数据 ========================

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

    sendAsForward(ctx, msg, '语擦助手', reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['本年数据'] = cmd_year_data;

// ======================== 语擦助手：月视图 ========================

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
extCalendar.cmdMap['月视图'] = cmd_month_view;

// ======================== 语擦助手：月历图（图片版月视图） ========================

let cmd_calendar_image = seal.ext.newCmdItemInfo();
cmd_calendar_image.name = '月历图';
cmd_calendar_image.help = '。月历图 [年] [月] —— 生成本月档期日历图片。需要本机先启动图片渲染服务（node board_server.js），服务未启动或生成失败时会自动回退成文字提示。';
cmd_calendar_image.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);

    let ym = parseYearMonth(cmdArgs.getArgN(1), cmdArgs.getArgN(2));
    if (ym.error) {
        seal.replyToSender(ctx, msg, ym.error);
        return seal.ext.newCmdExecuteResult(true);
    }
    let { year: targetYear, month: targetMonth } = ym;

    let dayShows = buildDayShowsForMonth(userData, targetYear, targetMonth);
    let showNamesSet = new Set();
    Object.values(dayShows).forEach(arr => arr.forEach(n => showNamesSet.add(n)));
    let showNamesList = Array.from(showNamesSet);

    if (showNamesList.length === 0) {
        seal.replyToSender(ctx, msg, `📅 ${targetYear}年${targetMonth}月 没有档期记录，换个月份试试，或发送。月视图 看文字版`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let showColor = assignShowColors(showNamesList);
    let showTimeRange = {};
    let showNameDict = {};
    showNamesList.forEach(n => {
        showTimeRange[n] = formatTimeRangeDisplay(userData[n].timeRange);
        if (userData[n].roleName && userData[n].roleName !== '未知') showNameDict[n] = userData[n].roleName;
    });

    let payload = {
        year: targetYear, month: targetMonth, dayShows, showColor, showTimeRange,
        showNameDict, uid: msg.sender.userId
    };

    sendRenderedImage(ctx, msg, '/calendar', payload, (err) => {
        seal.replyToSender(ctx, msg, `⚠️ 图片生成失败：${err}\n已跳过图片；可以发送。月视图 查看文字版。`);
    });

    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['月历图'] = cmd_calendar_image;

// ======================== 语擦助手：年度总览图 ========================

let cmd_year_overview_image = seal.ext.newCmdItemInfo();
cmd_year_overview_image.name = '年度总览图';
cmd_year_overview_image.help = '。年度总览图 [年份] —— 生成 12 个月的全年档期热力图，颜色越深表示当天重叠档期越多。';
cmd_year_overview_image.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let yearParam = cmdArgs.getArgN(1);
    let targetYear = yearParam ? parseInt(yearParam, 10) : getCurrentYear();
    if (!/^\d{4}$/.test(String(yearParam || targetYear)) || targetYear < 1900 || targetYear > 2100) {
        seal.replyToSender(ctx, msg, '❌ 年份无效，请输入四位数字年份（如2026）');
        return seal.ext.newCmdExecuteResult(true);
    }

    let overview = buildYearOverview(userData, targetYear);
    if (overview.summary.totalShows === 0) {
        seal.replyToSender(ctx, msg, `📅 ${targetYear}年没有档期记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    sendRenderedImage(ctx, msg, '/year-overview', {
        year: targetYear,
        months: overview.months,
        summary: overview.summary,
        uid: msg.sender.userId
    }, (err) => {
        seal.replyToSender(ctx, msg, `⚠️ 年度总览图生成失败：${err}`);
    });
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['年度总览图'] = cmd_year_overview_image;

// ======================== 语擦助手：结局分布图 ========================

let cmd_outcome_pie = seal.ext.newCmdItemInfo();
cmd_outcome_pie.name = '结局分布图';
cmd_outcome_pie.help = '。结局分布图 [年份] —— 生成本年结局分布图。HE/BE/OE/开放式以外的写法会归入「未填写」。需要本机先启动图片渲染服务。';
cmd_outcome_pie.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📊 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let yearParam = cmdArgs.getArgN(1);
    let targetYear = yearParam ? parseInt(yearParam, 10) : getCurrentYear();
    if (isNaN(targetYear) || targetYear < 1900 || targetYear > 2100) {
        seal.replyToSender(ctx, msg, '❌ 年份无效，请输入四位数字年份（如2025）');
        return seal.ext.newCmdExecuteResult(true);
    }

    let targetStart = targetYear * 10000 + 101;
    let targetEnd = targetYear * 10000 + 1231;
    let stats = { HE: 0, BE: 0, OE: 0, 开放式: 0, 未填写: 0 };

    for (let name in userData) {
        let entry = userData[name];
        let parsed = parseTimeRange(entry.timeRange || '');
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
        let endYear = cross ? entry.startYear + 1 : entry.startYear;
        let startVal = entry.startYear * 10000 + parsed.startMonth * 100 + parsed.startDay;
        let endVal = endYear * 10000 + parsed.endMonth * 100 + parsed.endDay;
        if (endVal < targetStart || startVal > targetEnd) continue;

        if (entry.outcome && Object.prototype.hasOwnProperty.call(stats, entry.outcome) && entry.outcome !== '未填写') {
            stats[entry.outcome]++;
        } else {
            stats.未填写++;
        }
    }

    let total = Object.values(stats).reduce((a, b) => a + b, 0);
    if (total === 0) {
        seal.replyToSender(ctx, msg, `📊 ${targetYear}年没有可统计的档期记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let payload = { year: targetYear, stats, uid: msg.sender.userId };
    sendRenderedImage(ctx, msg, '/pie', payload, (err) => {
        seal.replyToSender(ctx, msg, `⚠️ 图片生成失败：${err}\n已跳过图片；可以发送。本年数据 查看文字版统计。`);
    });

    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['结局分布图'] = cmd_outcome_pie;

// ======================== 语擦助手：下一场（倒计时） ========================

let cmd_next = seal.ext.newCmdItemInfo();
cmd_next.name = '下一场';
cmd_next.help = '。下一场 —— 显示正在进行中的档期，以及最近一场即将开始的档期倒计时';
cmd_next.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📅 你还没有任何档期记录。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let today = new Date();
    today.setHours(0, 0, 0, 0);

    let ongoing = [];
    let upcoming = [];

    for (let name in userData) {
        let entry = userData[name];
        let parsed = parseTimeRange(entry.timeRange || '');
        if (!parsed.valid) continue;

        let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
        let endYear = cross ? entry.startYear + 1 : entry.startYear;
        let startDate = new Date(entry.startYear, parsed.startMonth - 1, parsed.startDay);
        let endDate = new Date(endYear, parsed.endMonth - 1, parsed.endDay);

        if (today >= startDate && today <= endDate) {
            let daysLeft = Math.ceil((endDate - today) / (1000 * 60 * 60 * 24));
            ongoing.push({ name, daysLeft, timeRange: entry.timeRange });
        } else if (today < startDate) {
            let daysUntil = Math.ceil((startDate - today) / (1000 * 60 * 60 * 24));
            upcoming.push({ name, daysUntil, timeRange: entry.timeRange });
        }
    }

    if (ongoing.length === 0 && upcoming.length === 0) {
        seal.replyToSender(ctx, msg, '🎉 近期没有排定的档期，可以歇一歇～');
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = '📅 【下一场】\n══════════════\n';

    if (ongoing.length > 0) {
        ongoing.sort((a, b) => a.daysLeft - b.daysLeft);
        reply += '🔴 正在进行：\n';
        ongoing.forEach(o => {
            reply += `  · ${o.name}（还剩 ${o.daysLeft} 天结束，${o.timeRange}）\n`;
        });
    }

    if (upcoming.length > 0) {
        upcoming.sort((a, b) => a.daysUntil - b.daysUntil);
        let next = upcoming[0];
        reply += `\n⏭️ 下一场：「${next.name}」还有 ${next.daysUntil} 天开始（${next.timeRange}）\n`;
        if (upcoming.length > 1) {
            reply += `（之后还有 ${upcoming.length - 1} 场排定）\n`;
        }
    } else {
        reply += '\n⏭️ 之后暂无排定档期\n';
    }

    reply += '══════════════';
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['下一场'] = cmd_next;

// ======================== 语擦助手：导出档期 / 导入档期（跨机器人迁移） ========================

const EXPORT_TYPE = 'yuca_export_v1';
const EXPORT_CHUNK_CHAR_LIMIT = 3500;

function buildExportEntries(userData, filterFn) {
    let entries = {};
    for (let name in userData) {
        if (filterFn && !filterFn(name, userData[name])) continue;
        let e = userData[name];
        entries[name] = {
            startYear: e.startYear, timeRange: e.timeRange, status: e.status,
            character: e.character, orientation: e.orientation, theme: e.theme,
            roleName: e.roleName, roleType: e.roleType, gender: e.gender, outcome: e.outcome
        };
    }
    return entries;
}

function encodeExportBatch(entries) {
    return JSON.stringify({ __type: EXPORT_TYPE, exportedAt: Date.now(), entries });
}

// 把一批 entries 拆成若干"每份都能独立导入"的小批次，每份长度不超过限制，避免单条消息太长发不出去
function splitEntriesIntoBatches(entries) {
    let names = Object.keys(entries);
    let batches = [];
    let cur = {};
    for (let name of names) {
        let trial = Object.assign({}, cur, { [name]: entries[name] });
        if (encodeExportBatch(trial).length > EXPORT_CHUNK_CHAR_LIMIT && Object.keys(cur).length > 0) {
            batches.push(cur);
            cur = { [name]: entries[name] };
        } else {
            cur = trial;
        }
    }
    if (Object.keys(cur).length > 0) batches.push(cur);
    return batches;
}

let cmd_export = seal.ext.newCmdItemInfo();
cmd_export.name = '导出档期';
cmd_export.help = '。导出档期 [年份|全部] —— 导出你自己的档期数据，用于迁移到其它机器人（旧版/新版语擦助手互通）。不带参数显示年份概览；带年份只导出那一年；发送"全部"导出所有年份，数据多时会自动拆成多条消息，每条都要单独发给目标机器人的。导入档期。';
cmd_export.solve = (ctx, msg, cmdArgs) => {
    let userData = getUserData(ctx, msg);
    if (Object.keys(userData).length === 0) {
        seal.replyToSender(ctx, msg, '📭 你还没有任何档期记录，没什么可导出的。');
        return seal.ext.newCmdExecuteResult(true);
    }

    let yearCounts = {};
    for (let name in userData) {
        let y = userData[name].startYear;
        yearCounts[y] = (yearCounts[y] || 0) + 1;
    }
    let sortedYears = Object.keys(yearCounts).map(Number).sort((a, b) => a - b);

    let param = cmdArgs.getArgN(1);
    if (!param) {
        let reply = '📦 【导出档期】\n══════════════\n';
        sortedYears.forEach(y => { reply += `✨ ${y} 年：${yearCounts[y]} 条\n`; });
        reply += '══════════════\n💡 发送。导出档期 年份 只导出那一年；发送。导出档期 全部 导出所有年份';
        seal.replyToSender(ctx, msg, reply);
        return seal.ext.newCmdExecuteResult(true);
    }

    let entries;
    if (param === '全部') {
        entries = buildExportEntries(userData);
    } else {
        let year = parseInt(param, 10);
        if (isNaN(year) || !yearCounts[year]) {
            seal.replyToSender(ctx, msg, `❌ ${param} 年没有档期记录。可用年份：${sortedYears.join('、')}，或发送。导出档期 全部`);
            return seal.ext.newCmdExecuteResult(true);
        }
        entries = buildExportEntries(userData, (name, e) => e.startYear === year);
    }

    let batches = splitEntriesIntoBatches(entries);
    if (batches.length === 1) {
        seal.replyToSender(ctx, msg, '📦 导出完成，把下面这条完整发给目标机器人的。导入档期：\n' + encodeExportBatch(batches[0]));
    } else {
        seal.replyToSender(ctx, msg, `📦 数据较多，拆成了 ${batches.length} 份，每一份都要单独完整发给目标机器人的。导入档期（顺序不影响）：`);
        batches.forEach((batch, i) => {
            seal.replyToSender(ctx, msg, `— 第 ${i + 1}/${batches.length} 份 —\n` + encodeExportBatch(batch));
        });
    }
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['导出档期'] = cmd_export;

let cmd_import = seal.ext.newCmdItemInfo();
cmd_import.name = '导入档期';
cmd_import.help = '。导入档期 数据 —— 导入用。导出档期 生成的数据（可以来自旧版语擦助手，也可以来自另一个跑语擦助手的机器人）。同名恋综会被覆盖更新为导入的版本，其余记录不受影响。';
cmd_import.solve = (ctx, msg, cmdArgs) => {
    const prefix = '。导入档期';
    let raw = msg.message.trim();
    let blob = raw.startsWith(prefix) ? raw.substring(prefix.length).trim() : raw;

    if (!blob) {
        seal.replyToSender(ctx, msg, '❌ 格式：。导入档期 数据（数据来自对方的。导出档期）');
        return seal.ext.newCmdExecuteResult(true);
    }

    let parsed;
    try {
        parsed = JSON.parse(blob);
    } catch (e) {
        seal.replyToSender(ctx, msg, '❌ 数据格式不对，粘贴的时候可能漏了一部分，检查一下是不是完整复制的');
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!parsed || parsed.__type !== EXPORT_TYPE || !parsed.entries) {
        seal.replyToSender(ctx, msg, '❌ 这不是。导出档期 生成的数据');
        return seal.ext.newCmdExecuteResult(true);
    }

    let all = readAllData();
    let uid = msg.sender.userId;
    if (!all[uid]) all[uid] = {};

    let added = 0, updated = 0, skipped = 0;
    for (let name in parsed.entries) {
        let e = parsed.entries[name];
        let parsedRange = parseTimeRange(e.timeRange || '');
        if (!parsedRange.valid) { skipped++; continue; }

        let isNew = !all[uid][name];
        all[uid][name] = {
            startYear: e.startYear, timeRange: e.timeRange,
            status: e.status || '未知', character: e.character || '未知',
            orientation: e.orientation || '未知', theme: e.theme || '未知',
            roleName: e.roleName || '未知', roleType: e.roleType || '未知',
            gender: e.gender || '未知', outcome: e.outcome || '未知',
            reminded: [], outcomeReminded: false
        };
        if (isNew) added++; else updated++;
    }

    saveAllData(all);
    let skipHint = skipped > 0 ? `，跳过 ${skipped} 条格式异常的` : '';
    seal.replyToSender(ctx, msg, `✅ 导入完成：新增 ${added} 条，更新 ${updated} 条${skipHint}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['导入档期'] = cmd_import;

// ======================== 语擦助手：答案之书（娱乐向） ========================

const ANSWER_BOOK = [
    '是的，毫无疑问。',
    '现在还不是时候。',
    '别问了，你心里其实已经有答案。',
    '机会正在靠近，主动一点。',
    '答案是否定的，接受它。',
    '再等等，答案会自己浮现。',
    '你猜对了。',
    '这次运气站在你这边。',
    '别自欺欺人了。',
    '先睡一觉，明天再看。',
    '值得冒险一试。',
    '三思而后行。',
    '这个念头，放下比较好。',
    '宇宙暂时没有回应。',
    '去做吧，反正也不会更糟了。',
    '答案藏在你还没问出口的那句话里。',
    '现在不行，但会有转机。',
    '别想了，去睡觉。',
    '这是个圈套，小心。',
    '顺其自然。',
    '你已经知道该怎么选了。',
    '再犹豫就来不及了。',
    '答案是：随便你。',
    '这次不建议。',
    '试试也无妨。',
    '别人说了不算，你说了才算。',
    '换个问题问吧，这个没意义。',
    '运气不错，大胆去做。',
    '小心为上。',
    '这条路走得通，但会绕远。',
    '问心无愧就好。',
    '答案是：看心情。',
    '先解决眼前的事再说。',
    '会有人替你做决定，别急。',
    '这次是真的可以。',
    '不要，真的不要。',
    '答案早就写在你的犹豫里了。',
    '去问问擅长这个的人。',
    '答案之书今天很懒，自己看着办。',
    '是命运的安排。'
];

let cmd_answer_book = seal.ext.newCmdItemInfo();
cmd_answer_book.name = '答案之书';
cmd_answer_book.help = '。答案之书 [问题] —— 心里默念问题，随机翻开一页作为答案（纯娱乐向，不作为决策依据）';
cmd_answer_book.solve = (ctx, msg, cmdArgs) => {
    const rawMessage = msg.message.trim();
    const prefix = '。答案之书';
    let question = rawMessage.startsWith(prefix) ? rawMessage.substring(prefix.length).trim() : '';

    let answer = ANSWER_BOOK[Math.floor(Math.random() * ANSWER_BOOK.length)];
    let reply = question
        ? `📖 【答案之书】\n你的问题：${question}\n\n${answer}`
        : `📖 【答案之书】\n心中默念你的问题——\n\n${answer}`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['答案之书'] = cmd_answer_book;

// ======================== 语擦助手：塔罗单张（大阿尔卡纳，含正逆位解读） ========================

const TAROT_MAJOR_ARCANA = [
    { name: '0 愚者', upright: '新的开始，自由随性，放手一试，别怕摔跤。', reversed: '冲动鲁莽，准备不足，三思而后行。' },
    { name: 'I 魔术师', upright: '资源到位，创造力和行动力兼备，是时候把想法变成现实。', reversed: '能力被浪费，或者在耍小聪明、自欺欺人。' },
    { name: 'II 女祭司', upright: '直觉比逻辑更可靠，答案在沉默和内省里。', reversed: '忽视了内心的声音，或被表面信息误导。' },
    { name: 'III 女皇', upright: '丰盛、滋养、创造力旺盛，适合孕育新事物。', reversed: '过度付出导致自我耗竭，或创造力受阻。' },
    { name: 'IV 皇帝', upright: '秩序、掌控力、稳固的结构，靠规则和意志推进事情。', reversed: '过度专制，或局面失控、缺乏纪律。' },
    { name: 'V 教皇', upright: '传统智慧、寻求指导，走大家都认可的路更稳妥。', reversed: '教条僵化，或需要打破常规、自己找路。' },
    { name: 'VI 恋人', upright: '重要的选择，关系中的和谐与结合，跟随真心。', reversed: '关系失衡，或面临一个让人纠结的抉择。' },
    { name: 'VII 战车', upright: '意志力驱动前进，冲突中赢得胜利，方向明确。', reversed: '方向失控，内耗严重，缺乏统一目标。' },
    { name: 'VIII 力量', upright: '以柔克刚，耐心和自我掌控比蛮力更有效。', reversed: '自我怀疑，或情绪/欲望失控。' },
    { name: 'IX 隐士', upright: '退一步独自沉淀，答案在向内寻找的路上。', reversed: '过度孤立，或逃避该面对的人和事。' },
    { name: 'X 命运之轮', upright: '转折点到来，风向在变，顺势而为。', reversed: '时运不济，或抗拒改变导致错过机会。' },
    { name: 'XI 正义', upright: '因果分明，做出的选择会被公平地回应。', reversed: '不公平的处境，或逃避该承担的责任。' },
    { name: 'XII 倒吊人', upright: '换个角度看问题，暂时的停滞其实是必要的沉淀。', reversed: '拖延、抗拒改变视角，困在原地。' },
    { name: 'XIII 死神', upright: '一个阶段结束，为新的开始腾出空间，不必恐惧。', reversed: '抗拒结束，停滞不前，该放下的还没放下。' },
    { name: 'XIV 节制', upright: '平衡、耐心调和，慢慢来，急不得。', reversed: '失衡、走极端，缺乏耐心导致状况恶化。' },
    { name: 'XV 恶魔', upright: '被欲望、执念或某种关系束缚，但枷锁其实可以自己解开。', reversed: '正在挣脱束缚，找回掌控权。' },
    { name: 'XVI 高塔', upright: '突如其来的剧变，旧结构崩塌，虽然痛但是必要的清理。', reversed: '危机被暂时压下，但问题还在，迟早要面对。' },
    { name: 'XVII 星星', upright: '希望重燃，疗愈正在发生，相信过程。', reversed: '信心动摇，感觉希望渺茫，需要重新找回信念。' },
    { name: 'XVIII 月亮', upright: '情况模糊不清，潜意识和恐惧在起作用，别急着下结论。', reversed: '迷雾正在散去，真相开始浮现。' },
    { name: 'XIX 太阳', upright: '顺遂、明朗，值得庆祝的好结果。', reversed: '暂时被乌云遮住，但本质依然是好的，耐心等光照进来。' },
    { name: 'XX 审判', upright: '一次重要的觉醒或总结，为过去做出评判，迎接新阶段。', reversed: '自我怀疑，或逃避该有的反思和清算。' },
    { name: 'XXI 世界', upright: '一个完整的循环圆满达成，收获与完成。', reversed: '差临门一脚，或不愿意结束一个已经完成的阶段。' }
];

let cmd_tarot = seal.ext.newCmdItemInfo();
cmd_tarot.name = '塔罗单张';
cmd_tarot.help = '。塔罗单张 [问题] —— 从大阿尔卡纳 22 张牌中抽一张，附正/逆位解读，纯娱乐向';
cmd_tarot.solve = (ctx, msg, cmdArgs) => {
    const rawMessage = msg.message.trim();
    const prefix = '。塔罗单张';
    let question = rawMessage.startsWith(prefix) ? rawMessage.substring(prefix.length).trim() : '';

    let card = TAROT_MAJOR_ARCANA[Math.floor(Math.random() * TAROT_MAJOR_ARCANA.length)];
    let reversed = Math.random() < 0.5;
    let orientation = reversed ? '逆位' : '正位';
    let meaning = reversed ? card.reversed : card.upright;

    let reply = '🔮 【塔罗单张】\n';
    if (question) reply += `你的问题：${question}\n`;
    reply += `\n抽到：${card.name}（${orientation}）\n${meaning}`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['塔罗单张'] = cmd_tarot;

// ======================== 语擦助手：灵签（中式签文，含解签） ========================

const CHINESE_FORTUNE_STICKS = [
    { id: 1, tier: '上上签', poem: '晴空万里映朝霞，好事临门到你家；心中疑虑今可解，一帆风顺乐无涯。', meaning: '诸事顺遂的好签，眼下的犹豫可以放下了，大胆去做。' },
    { id: 2, tier: '上签', poem: '春风得意马蹄疾，一路繁花一路诗；莫道前途多坎坷，柳暗花明又一时。', meaning: '整体向好，过程可能有小波折，但结果值得期待。' },
    { id: 3, tier: '中签', poem: '云开雾散日渐明，静待时机莫强行；心急难成千里路，从容自有好收成。', meaning: '不是不行，是时候未到，耐心等待比强求更有效。' },
    { id: 4, tier: '中签', poem: '舟行江上风未定，进退之间费思量；且看两岸风景好，何必执意争短长。', meaning: '局势还不明朗，先别急着做决定，多观察再行动。' },
    { id: 5, tier: '上签', poem: '百花深处藏珍宝，有心之人自会找；莫叹眼前无路走，转角便是艳阳照。', meaning: '好事就在不远处，关键是别放弃寻找。' },
    { id: 6, tier: '下签', poem: '风雨飘摇路难行，且莫强求一时成；退一步来天地阔，静养心神待时清。', meaning: '目前不宜强攻，退一步反而海阔天空，先养精蓄锐。' },
    { id: 7, tier: '中签', poem: '明镜高悬照真心，是非曲直自分明；莫为浮云遮望眼，坦荡而行少纷争。', meaning: '事情终会真相大白，行得正不用怕闲言碎语。' },
    { id: 8, tier: '上上签', poem: '喜鹊登枝报好音，多年心愿此时成；莫嫌等待时日久，守得云开见月明。', meaning: '期待已久的事有望成真，之前的等待没有白费。' },
    { id: 9, tier: '下签', poem: '孤舟夜泊寒江雪，独自思量路更长；莫怨天时人不助，且将心事付流光。', meaning: '眼下会觉得孤立无援，但硬扛过去这段就好，别钻牛角尖。' },
    { id: 10, tier: '中签', poem: '种豆得豆种瓜瓜，因果循环不虚差；今日耕耘他日果，切莫半途自嗟呀。', meaning: '付出和结果是成正比的，别半途而废。' },
    { id: 11, tier: '上签', poem: '鱼跃龙门声势壮，一朝得志展锋芒；莫忘来时艰辛路，谦逊方能路更长。', meaning: '会有一次翻身或突破的机会，把握住，但别飘。' },
    { id: 12, tier: '下下签', poem: '乌云蔽日风雨急，此时行事多阻力；不如按兵先自守，待到云散再图之。', meaning: '眼下不是好时机，硬闯只会徒增损耗，先守成为上策。' },
    { id: 13, tier: '中签', poem: '路遇岔口两难选，进也忧来退也愁；静心细想根本处，自然明白该何求。', meaning: '面临选择很正常，回到最初的目的想清楚，答案自然浮现。' },
    { id: 14, tier: '中签', poem: '藤缠古树枝叶茂，看似缠绕实相依；莫将牵绊当羁绊，同心自有好光景。', meaning: '人际或感情上的"纠缠"其实是彼此需要，别急着挣脱。' },
    { id: 15, tier: '上签', poem: '久旱逢甘霖润土，枯木也能再逢春；莫道此生已定局，转机常在意外中。', meaning: '低谷已经快过去了，转机会以意想不到的方式出现。' },
    { id: 16, tier: '下签', poem: '镜花水月终是空，执念太深徒伤神；放下执著心自宽，柳暗自有花明春。', meaning: '太执着的那件事，可能本来就抓不住，放手是解法。' },
    { id: 17, tier: '中签', poem: '路遥知马力方显，日久见人心自明；莫因一时难辨认，且将耐心留三分。', meaning: '需要时间来验证的事，急不来，交给时间。' },
    { id: 18, tier: '上上签', poem: '金榜题名众人贺，多年苦读终有成；莫忘初心来时路，再攀高峰更从容。', meaning: '努力终于要有回报了，是值得庆祝的好签。' },
    { id: 19, tier: '下签', poem: '秋风扫叶满地黄，繁华过后总有伤；莫因一时之得失，来年春暖又花香。', meaning: '可能会经历一次失落或结束，但这不是永远，春天还会再来。' },
    { id: 20, tier: '中签', poem: '舟到桥头自然直，莫为未至事先忧；心宽路自宽三分，从容以对渡春秋。', meaning: '想太多反而添堵，很多事到了那一步自然有解法，别提前焦虑。' }
];

let cmd_fortune_stick = seal.ext.newCmdItemInfo();
cmd_fortune_stick.name = '灵签';
cmd_fortune_stick.help = '。灵签 [问题] —— 抽一支灵签，含签诗和解签，纯娱乐向';
cmd_fortune_stick.solve = (ctx, msg, cmdArgs) => {
    const rawMessage = msg.message.trim();
    const prefix = '。灵签';
    let question = rawMessage.startsWith(prefix) ? rawMessage.substring(prefix.length).trim() : '';

    let stick = CHINESE_FORTUNE_STICKS[Math.floor(Math.random() * CHINESE_FORTUNE_STICKS.length)];

    let reply = '🎋 【灵签】\n';
    if (question) reply += `你的问题：${question}\n`;
    reply += `\n第${stick.id}签 · ${stick.tier}\n『${stick.poem}』\n\n解签：${stick.meaning}`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
extCalendar.cmdMap['灵签'] = cmd_fortune_stick;

// ======================== 卡救星：卡救星帮助 ========================

let cmd_card_help = seal.ext.newCmdItemInfo();
cmd_card_help.name = '卡救星帮助';
cmd_card_help.help = '。卡救星帮助 —— 显示卡片管理相关指令';
cmd_card_help.solve = (ctx, msg, cmdArgs) => {
    let help = `🃏 【卡救星 指令列表】
══════════════
。录入卡片 名称 日期 数量 [关联恋综]
。修改卡片 名称 属性 值   属性：名称/数量/价格/类型/群号/关联恋综
。已下单 名称 [数量]      仅记录消耗，不转发内容
。下单 名称\\n内容        把内容自动转发到该卡绑定的群，并消耗1个（支持换行/图片）
。删除卡片 名称
。卡片列表 [类型]         类型：${VALID_TYPES.join('/')}
。清理过期
。急救箱 [类型]           随机抽一张（同：随机卡片）

💡 关联恋综后，「。本月档期」会自动联动展示相关卡片状态。
💡 直接在目标群里发。录入卡片，会自动绑定当前群作为下单群；
   在别处创建的卡片需要手动。修改卡片 名称 群号 群号数字 补绑（直接填数字就行，会自动补前缀）。
到期前 10/5/3 天会自动提醒（按录入时所在场景私聊或群内@）。
══════════════`;
    seal.replyToSender(ctx, msg, help);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['卡救星帮助'] = cmd_card_help;

// ======================== 卡救星：录入卡片 ========================

let cmdAdd = seal.ext.newCmdItemInfo();
cmdAdd.name = '录入卡片';
cmdAdd.help = '。录入卡片 名称 日期(YYYY-MM-DD) 数量 [关联恋综] —— 关联恋综后可在。本月档期中联动提醒';
cmdAdd.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let date = cmdArgs.getArgN(2);
    let num = parseInt(cmdArgs.getArgN(3));
    let relatedShow = cmdArgs.getArgN(4) || '';

    if (!name || !date || isNaN(num)) {
        seal.replyToSender(ctx, msg, ".录入卡片 <名称> <日期:YYYY-MM-DD> <数量> [关联恋综]");
        return seal.ext.newCmdExecuteResult(true);
    }

    let data = getData();
    let uid = msg.sender.userId;
    if (!data[uid]) data[uid] = {};

    if (data[uid][name]) {
        seal.replyToSender(ctx, msg, `❌ 名称「${name}」已存在。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    data[uid][name] = {
        name: name, expiry: date, quantity: num,
        price: 0, type: '其他', orderGroup: msg.groupId || '',
        lastOrder: null, reminded: [], relatedShow: relatedShow
    };

    saveData(data);
    let relatedHint = relatedShow ? `\n🔗 关联恋综：${relatedShow}` : '';
    seal.replyToSender(ctx, msg, `✨ 录入成功\n📌 名称：${name}\n⏳ 到期：${date}\n📦 库存：${num}${relatedHint}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['录入卡片'] = cmdAdd;

// ======================== 卡救星：修改卡片 ========================

let cmdMod = seal.ext.newCmdItemInfo();
cmdMod.name = '修改卡片';
cmdMod.help = '。修改卡片 名称 属性 值 —— 属性可选：名称/数量/价格/类型/群号/关联恋综';
cmdMod.solve = (ctx, msg, cmdArgs) => {
    let oldName = cmdArgs.getArgN(1);
    let attr = cmdArgs.getArgN(2);
    let value = cmdArgs.getArgN(3);

    let data = getData();
    let userCards = data[msg.sender.userId];

    if (!userCards || !userCards[oldName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到卡片「${oldName}」`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (attr === '名称') {
        if (userCards[value]) {
            seal.replyToSender(ctx, msg, "❌ 新名称已被占用");
            return seal.ext.newCmdExecuteResult(true);
        }
        userCards[value] = userCards[oldName];
        userCards[value].name = value;
        delete userCards[oldName];
    } else {
        switch (attr) {
            case '数量': {
                let q = parseInt(value);
                if (isNaN(q)) {
                    seal.replyToSender(ctx, msg, "❌ 数量必须为数字");
                    return seal.ext.newCmdExecuteResult(true);
                }
                userCards[oldName].quantity = q;
                break;
            }
            case '价格': {
                let p = parseFloat(value);
                if (isNaN(p)) {
                    seal.replyToSender(ctx, msg, "❌ 价格必须为数字");
                    return seal.ext.newCmdExecuteResult(true);
                }
                userCards[oldName].price = p;
                break;
            }
            case '群号': userCards[oldName].orderGroup = normalizeGroupId(value); break;
            case '关联恋综': userCards[oldName].relatedShow = value; break;
            case '类型':
                if (!VALID_TYPES.includes(value)) {
                    seal.replyToSender(ctx, msg, `❌ 可选类型：${VALID_TYPES.join('/')}`);
                    return seal.ext.newCmdExecuteResult(true);
                }
                userCards[oldName].type = value;
                break;
            default:
                seal.replyToSender(ctx, msg, "❌ 属性可选：名称/数量/价格/类型/群号/关联恋综");
                return seal.ext.newCmdExecuteResult(true);
        }
    }
    saveData(data);
    seal.replyToSender(ctx, msg, `✅ 已修改「${oldName}」的 ${attr}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['修改卡片'] = cmdMod;

// ======================== 卡救星：已下单 ========================

let cmdOrder = seal.ext.newCmdItemInfo();
cmdOrder.name = '已下单';
cmdOrder.help = '。已下单 名称 [数量] —— 消耗指定数量库存，默认消耗 1 个';
cmdOrder.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let count = parseInt(cmdArgs.getArgN(2)) || 1;
    let data = getData();
    let card = data[msg.sender.userId]?.[name];
    if (!card) {
        seal.replyToSender(ctx, msg, "❌ 卡片不存在");
        return seal.ext.newCmdExecuteResult(true);
    }

    card.quantity -= count;
    card.lastOrder = new Date().getTime();
    saveData(data);
    let negativeHint = card.quantity < 0 ? '\n⚠️ 库存已为负数，请检查是否多扣了' : '';
    seal.replyToSender(ctx, msg, `📉 消耗成功\n📌 名称：${name}\n📦 剩余：${card.quantity}${negativeHint}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['已下单'] = cmdOrder;

// ======================== 卡救星：下单（自动转发到绑定群） ========================

let cmdPlaceOrder = seal.ext.newCmdItemInfo();
cmdPlaceOrder.name = '下单';
cmdPlaceOrder.help = '。下单 卡名\n下单内容（可换行、可带图片）—— 把内容自动转发到该卡绑定的群（不管你在哪发的这条指令），并消耗 1 张库存。\n群号请先用。修改卡片 卡名 群号 群号数字 绑定（直接填数字就行）；或者直接在目标群里。录入卡片，会自动绑定当前群。';
cmdPlaceOrder.solve = (ctx, msg, cmdArgs) => {
    const prefix = '。下单';
    let raw = msg.message.trim();
    let afterCmd = raw.startsWith(prefix) ? raw.substring(prefix.length).trim() : raw;

    let match = afterCmd.match(/^(\S+)\s*([\s\S]*)$/);
    if (!match || !match[1]) {
        seal.replyToSender(ctx, msg, "格式：。下单 卡名\n下单内容（换行后写正文，支持图片）");
        return seal.ext.newCmdExecuteResult(true);
    }
    let name = match[1];
    let content = match[2].replace(/\s+$/, '');

    if (!content) {
        seal.replyToSender(ctx, msg, "❌ 请在卡名后面写上要下单的内容（可以换行）");
        return seal.ext.newCmdExecuteResult(true);
    }

    let data = getData();
    let uid = msg.sender.userId;
    let card = data[uid]?.[name];
    if (!card) {
        seal.replyToSender(ctx, msg, `❌ 未找到卡片「${name}」`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!card.orderGroup) {
        seal.replyToSender(ctx, msg, `❌「${name}」还没绑定下单群，请先发送：。修改卡片 ${name} 群号 群号数字（直接填数字就行）\n（或者直接去目标群里重新。录入卡片一次，会自动绑定当前群）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let eps = seal.getEndPoints();
    if (eps.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 当前没有可用的连接端点，发送失败");
        return seal.ext.newCmdExecuteResult(true);
    }

    let fakeMsg = seal.newMessage();
    fakeMsg.groupId = card.orderGroup;
    fakeMsg.messageType = 'group';
    let targetCtx = seal.createTempCtx(eps[0], fakeMsg);
    seal.replyToSender(targetCtx, fakeMsg, content);

    card.quantity -= 1;
    card.lastOrder = new Date().getTime();
    saveData(data);

    let negativeHint = card.quantity < 0 ? '\n⚠️ 库存已为负数，请检查' : '';
    seal.replyToSender(ctx, msg, `✅ 下单内容已转发至「${name}」绑定的群\n📦 剩余库存：${card.quantity}${negativeHint}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['下单'] = cmdPlaceOrder;

// ======================== 卡救星：删除卡片 ========================

let cmdDel = seal.ext.newCmdItemInfo();
cmdDel.name = '删除卡片';
cmdDel.help = '。删除卡片 名称 —— 删除指定卡片';
cmdDel.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let data = getData();
    if (data[msg.sender.userId]?.[name]) {
        delete data[msg.sender.userId][name];
        saveData(data);
        seal.replyToSender(ctx, msg, `🗑️ 已删除：${name}`);
    } else {
        seal.replyToSender(ctx, msg, "❌ 未找到该卡片");
    }
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['删除卡片'] = cmdDel;

// ======================== 卡救星：卡片列表 ========================

let cmdList = seal.ext.newCmdItemInfo();
cmdList.name = '卡片列表';
cmdList.help = `。卡片列表 [类型] —— 按临期排序列出卡片，类型可选：${VALID_TYPES.join('/')}`;
cmdList.solve = (ctx, msg, cmdArgs) => {
    let filterType = cmdArgs.getArgN(1) || '';
    let data = getData();
    let userCards = data[msg.sender.userId];

    if (!userCards || Object.keys(userCards).length === 0) {
        seal.replyToSender(ctx, msg, "📭 卡包空空如也。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let cardNames = Object.keys(userCards);
    if (filterType) {
        if (!VALID_TYPES.includes(filterType)) {
            seal.replyToSender(ctx, msg, `❌ 可选类型：${VALID_TYPES.join('/')}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        cardNames = cardNames.filter(n => userCards[n].type === filterType);
        if (cardNames.length === 0) {
            seal.replyToSender(ctx, msg, `📭 没有「${filterType}」类型的卡片。`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    cardNames.sort((a, b) => new Date(userCards[a].expiry) - new Date(userCards[b].expiry));

    let total = cardNames.length;
    let title = filterType ? `🛡️ 【卡片救星 · ${filterType}】\n共计 ${total} 张，按临期排序：`
                           : `🛡️ 【卡片救星 · 资产总览】\n共计 ${total} 张卡片，按临期排序：`;
    seal.replyToSender(ctx, msg, title);

    let bodyLines = [];
    for (let i = 0; i < total; i++) {
        let card = userCards[cardNames[i]];
        let days = getDaysDiff(card.expiry);
        let status = days > 0 ? `剩 ${days} 天` : "⚠️ 已过期";
        let relatedLine = card.relatedShow ? `\n🔗 关联：${card.relatedShow}` : '';

        bodyLines.push(
            `📌 【${card.name}】 (${card.type})\n` +
            `⏳ 状态：${status} | 📦 库存：${card.quantity}\n` +
            `💰 价格：${card.price} | 🕓 上次：${formatTime(card.lastOrder)}${relatedLine}\n` +
            "————————————"
        );
    }
    sendAsForward(ctx, msg, '卡救星', bodyLines.join('\n'));
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['卡片列表'] = cmdList;

// ======================== 卡救星：清理过期卡片 ========================

let cmdClean = seal.ext.newCmdItemInfo();
cmdClean.name = '清理过期';
cmdClean.help = '。清理过期 —— 删除所有已过期的卡片';
cmdClean.solve = (ctx, msg, cmdArgs) => {
    let data = getData();
    let uid = msg.sender.userId;
    let userCards = data[uid];

    if (!userCards || Object.keys(userCards).length === 0) {
        seal.replyToSender(ctx, msg, "📭 卡包空空如也。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let expired = Object.keys(userCards).filter(n => getDaysDiff(userCards[n].expiry) <= 0);
    if (expired.length === 0) {
        seal.replyToSender(ctx, msg, "✅ 没有过期卡片，卡包干净。");
        return seal.ext.newCmdExecuteResult(true);
    }

    expired.forEach(n => delete userCards[n]);
    saveData(data);
    seal.replyToSender(ctx, msg, `🗑️ 已清理 ${expired.length} 张过期卡片：\n${expired.map(n => `· ${n}`).join('\n')}`);
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['清理过期'] = cmdClean;

// ======================== 卡救星：急救箱 ========================

const JIUJIU_LINES = [
    "命运之手为你选中了它！",
    "今天就用它吧，别再纠结了~",
    "它在卡包里等你很久了。",
    "就决定是你了！",
    "缘分天注定，出手吧！",
    "骰子已掷出，无法反悔。",
];

let cmdRandom = seal.ext.newCmdItemInfo();
cmdRandom.name = '急救箱';
cmdRandom.help = '。急救箱 [类型] —— 随机抽一张有效卡片（同：随机卡片）';
cmdRandom.solve = (ctx, msg, cmdArgs) => {
    let filterType = cmdArgs.getArgN(1) || '';
    let data = getData();
    let userCards = data[msg.sender.userId];

    if (!userCards || Object.keys(userCards).length === 0) {
        seal.replyToSender(ctx, msg, "📭 卡包空空如也，没什么可抽的。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let pool = Object.values(userCards).filter(c => getDaysDiff(c.expiry) >= 0);
    if (filterType) {
        if (!VALID_TYPES.includes(filterType)) {
            seal.replyToSender(ctx, msg, `❌ 可选类型：${VALID_TYPES.join('/')}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        pool = pool.filter(c => c.type === filterType);
    }

    if (pool.length === 0) {
        let tip = filterType ? `没有有效的「${filterType}」卡片` : '没有有效卡片（可能都过期了？）';
        seal.replyToSender(ctx, msg, `📭 ${tip}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let card = pool[Math.floor(Math.random() * pool.length)];
    let days = getDaysDiff(card.expiry);
    let flavor = JIUJIU_LINES[Math.floor(Math.random() * JIUJIU_LINES.length)];

    seal.replyToSender(ctx, msg,
        `🎲 【急救箱】${flavor}\n` +
        `📌 ${card.name}（${card.type}）\n` +
        `⏳ 还剩 ${days} 天到期 | 📦 库存：${card.quantity}`
    );
    return seal.ext.newCmdExecuteResult(true);
};
extCard.cmdMap['急救箱'] = cmdRandom;
extCard.cmdMap['随机卡片'] = cmdRandom;

// ======================== 联动定时提醒（合并为一个定时器） ========================

function runCardReminders() {
    let data = getData();
    let modified = false;
    for (let uid in data) {
        for (let name in data[uid]) {
            let card = data[uid][name];
            let days = getDaysDiff(card.expiry);
            let milestones = [10, 5, 3];

            for (let m of milestones) {
                if (days === m && !card.reminded.includes(m)) {
                    let atPrefix = `[CQ:at,qq=${uid.replace('QQ:', '')}] `;
                    let text = `${atPrefix}📢 【过期预警】\n您的「${name}」还有 ${days} 天就要到期了。\n当前库存：${card.quantity}\n请记得及时使用。`;
                    let eps = seal.getEndPoints();
                    if (eps.length > 0) {
                        let fakeMsg = seal.newMessage();
                        if (card.orderGroup && (card.orderGroup.includes('Group') || card.orderGroup.includes('-'))) {
                            fakeMsg.groupId = card.orderGroup;
                            fakeMsg.messageType = 'group';
                        } else {
                            fakeMsg.sender.userId = uid;
                            fakeMsg.messageType = 'private';
                            text = `📢 【过期预警】\n您的「${name}」还有 ${days} 天就要到期了。\n当前库存：${card.quantity}\n请记得及时使用。`;
                        }
                        let targetCtx = seal.createTempCtx(eps[0], fakeMsg);
                        seal.replyToSender(targetCtx, fakeMsg, text);
                    }
                    card.reminded.push(m);
                    modified = true;
                }
            }
        }
    }
    if (modified) saveData(data);
}

function runShowReminders() {
    let all = readAllData();
    let cardAll = getData();
    let modified = false;
    const milestones = [3, 1];
    let today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let uid in all) {
        let userShows = all[uid];
        let userCards = cardAll[uid] || {};

        for (let name in userShows) {
            let entry = userShows[name];
            let parsed = parseTimeRange(entry.timeRange || '');
            if (!parsed.valid) continue;
            if (!entry.reminded) entry.reminded = [];

            let startDate = new Date(entry.startYear, parsed.startMonth - 1, parsed.startDay);
            let diffDays = Math.ceil((startDate - today) / (1000 * 60 * 60 * 24));

            for (let m of milestones) {
                if (diffDays === m && !entry.reminded.includes(m)) {
                    let relatedCards = Object.values(userCards).filter(c => c.relatedShow === name);
                    let cardInfo = relatedCards.length > 0
                        ? '\n🔗 关联卡片：' + relatedCards.map(c => `${c.name}(剩${getDaysDiff(c.expiry)}天/库存${c.quantity})`).join('、')
                        : '';
                    let text = `📅 【档期提醒】\n「${name}」还有 ${m} 天开始（${entry.timeRange}）。${cardInfo}`;

                    let eps = seal.getEndPoints();
                    if (eps.length > 0) {
                        let fakeMsg = seal.newMessage();
                        fakeMsg.sender.userId = uid;
                        fakeMsg.messageType = 'private';
                        let targetCtx = seal.createTempCtx(eps[0], fakeMsg);
                        seal.replyToSender(targetCtx, fakeMsg, text);
                    }
                    entry.reminded.push(m);
                    modified = true;
                }
            }

            // 结局回填提醒：档期结束 3 天后，如果结局仍未知就提醒一次
            let cross = isCrossYear(parsed.endMonth, parsed.startMonth);
            let endYear = cross ? entry.startYear + 1 : entry.startYear;
            let endDate = new Date(endYear, parsed.endMonth - 1, parsed.endDay);
            let daysSinceEnd = Math.floor((today - endDate) / (1000 * 60 * 60 * 24));

            if (daysSinceEnd === 3 && (!entry.outcome || entry.outcome === '未知') && !entry.outcomeReminded) {
                let text = `📝 【结局回填提醒】\n「${name}」（${entry.timeRange}）已经结束几天啦，结局还没填呢～\n发送：。修改 ${name} 结局 xxx 来补充吧`;
                let eps = seal.getEndPoints();
                if (eps.length > 0) {
                    let fakeMsg = seal.newMessage();
                    fakeMsg.sender.userId = uid;
                    fakeMsg.messageType = 'private';
                    let targetCtx = seal.createTempCtx(eps[0], fakeMsg);
                    seal.replyToSender(targetCtx, fakeMsg, text);
                }
                entry.outcomeReminded = true;
                modified = true;
            }
        }
    }
    if (modified) saveAllData(all);
}

function runAllReminders() {
    runCardReminders();
    runShowReminders();
    setTimeout(runAllReminders, 6 * 60 * 60 * 1000);
}
setTimeout(runAllReminders, 20000);
