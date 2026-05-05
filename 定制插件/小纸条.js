// ==UserScript==
// @name         小纸条
// @author       长日将尽
// @version      2.2.0
// @description  多玩法类型的小纸条传递系统，支持检定公示、收发箱查询、配额管理
// @timestamp    1746374400
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

// ========================
// 初始化
// ========================

let ext = seal.ext.find("note_plugin");
if (!ext) {
    ext = seal.ext.new("note_plugin", "长日将尽", "2.2.0");
    seal.ext.register(ext);
}

// ========================
// WS 工具（合并转发）
// ========================

function ws(postData, ctx, msg, successReply) {
    const wsUrl = seal.ext.getStringConfig(ext, "ws地址");
    const token = seal.ext.getStringConfig(ext, "ws_token");
    let url = wsUrl;
    if (token) url += (url.includes("?") ? "&" : "?") + "access_token=" + encodeURIComponent(token);

    const echo = postData.action + "_" + Date.now();
    postData.echo = echo;

    if (postData.params) {
        if (postData.params.group_id) postData.params.group_id = parseInt(postData.params.group_id);
    }

    const socket = new WebSocket(url);
    let closed = false;
    const close = () => {
        if (!closed) {
            closed = true;
            clearTimeout(tid);
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) socket.close();
        }
    };

    const tid = setTimeout(() => {
        if (!closed) {
            console.log("[小纸条WS] 超时: " + postData.action);
            close();
        }
    }, 5000);

    socket.onopen = () => {
        try { socket.send(JSON.stringify(postData)); } catch (e) { close(); }
    };

    socket.onmessage = (event) => {
        try {
            const res = JSON.parse(event.data);
            if (res.post_type === "meta_event") return;
            if (res.echo !== echo) return;
            if ((res.status === "ok" || res.retcode === 0) && successReply) {
                seal.replyToSender(ctx, msg, successReply);
            }
            close();
        } catch (e) { close(); }
    };

    socket.onerror = () => close();
}

// 发送合并转发到当前群
function sendForward(ctx, msg, nodes) {
    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, "❌ 请在群内使用此指令。");
        return;
    }
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
}

// 发送合并转发到指定群
function sendForwardToGroup(ctx, msg, gid, nodes) {
    ws({ action: "send_group_forward_msg", params: { group_id: parseInt(gid, 10), messages: nodes } }, ctx, msg, "");
}

// 构造一条合并转发节点
function makeNode(ctx, name, content) {
    return { type: "node", data: { name: name, uin: ctx.endPoint.userId, content: content } };
}

// ========================
// 存储 key 命名规则
// ========================
// note_players          {[platform]: {[角色名]: uid}}
// note_quotas           {[platform]: {[角色名]: {[type]: number}}}
// note_disabled         {[platform]: {[角色名]: {[type]: true}}}
// note_records          [{id, from, to, type, title, pen, time, day, content, ts}]
// note_public_group     string  群号
// note_check_rate       {[platform]: {[角色名]: {[type]: 0-100}}}
// note_check_text       {[type]: string}
// note_check_hide       {[type]: bool}
// note_global_day       string  "D0"/"D1"...

const DEFAULT_TYPE = "小纸条";

function getPlayers() { return JSON.parse(ext.storageGet("note_players") || "{}"); }
function setPlayers(v) { ext.storageSet("note_players", JSON.stringify(v)); }

function getQuotas() { return JSON.parse(ext.storageGet("note_quotas") || "{}"); }
function setQuotas(v) { ext.storageSet("note_quotas", JSON.stringify(v)); }

function getDisabled() { return JSON.parse(ext.storageGet("note_disabled") || "{}"); }
function setDisabled(v) { ext.storageSet("note_disabled", JSON.stringify(v)); }

function getRecords() { return JSON.parse(ext.storageGet("note_records") || "[]"); }
function setRecords(v) { ext.storageSet("note_records", JSON.stringify(v)); }

function getCheckRate() { return JSON.parse(ext.storageGet("note_check_rate") || "{}"); }
function setCheckRate(v) { ext.storageSet("note_check_rate", JSON.stringify(v)); }

function getCheckText() { return JSON.parse(ext.storageGet("note_check_text") || "{}"); }
function setCheckText(v) { ext.storageSet("note_check_text", JSON.stringify(v)); }

function getCheckHide() { return JSON.parse(ext.storageGet("note_check_hide") || "{}"); }
function setCheckHide(v) { ext.storageSet("note_check_hide", JSON.stringify(v)); }

function getPublicGroup() { return ext.storageGet("note_public_group") || ""; }
function setPublicGroup(v) { ext.storageSet("note_public_group", v); }

function getGlobalDay() { return ext.storageGet("note_global_day") || "D0"; }
function setGlobalDay(v) { ext.storageSet("note_global_day", v); }

// ========================
// 权限判断
// ========================

function isAdmin(ctx, msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const adminList = JSON.parse(ext.storageGet("note_admins") || "{}");
    return ctx.privilegeLevel >= 100 || (adminList[platform] && adminList[platform].includes(uid));
}

// ========================
// 玩家查询辅助
// ========================

function findPlayerByUid(platform, uid) {
    const players = getPlayers();
    const map = players[platform] || {};
    return Object.keys(map).find(name => map[name] === uid) || null;
}

function findUidByName(platform, name) {
    const players = getPlayers();
    return (players[platform] || {})[name] || null;
}

// ========================
// 解析多名玩家（顿号/逗号分隔）
// ========================

function parseNames(str) {
    return str.split(/[、,，]/).map(s => s.trim()).filter(Boolean);
}

// ========================
// 解析 .to 指令参数
//   .to 收件人 署名|<类型·标题> 时间：dx 内容：XXXXX
// ========================

function parseToCmd(rawText) {
    // rawText 是去掉 ".to " 后的全文
    // 格式：收件人 署名|<类型·标题> 时间：dx 内容：XXXXX
    //        可以没有署名部分，则格式：收件人 <类型·标题> 时间：dx 内容：XXXXX
    //        类型·标题 可省略 -> 收件人 署名 时间：dx 内容：XXXXX （类型=DEFAULT_TYPE）

    const contentMatch = rawText.match(/内容[：:]([\s\S]+)$/);
    if (!contentMatch) return null;
    const content = contentMatch[1].trim();
    const beforeContent = rawText.slice(0, contentMatch.index).trim();

    // 提取时间
    const timeMatch = beforeContent.match(/时间[：:]\s*(d\d+)/i);
    const day = timeMatch ? timeMatch[1].toUpperCase() : null;
    const beforeTime = timeMatch ? beforeContent.slice(0, timeMatch.index).trim() : beforeContent;

    // 前面的部分：收件人 [署名][|<类型·标题>]
    // 按空格分割第一个词作为收件人
    const spaceIdx = beforeTime.search(/\s+/);
    let toName, rest;
    if (spaceIdx === -1) {
        toName = beforeTime;
        rest = "";
    } else {
        toName = beforeTime.slice(0, spaceIdx);
        rest = beforeTime.slice(spaceIdx).trim();
    }

    // rest 格式：署名|<类型·标题>  或  <类型·标题>  或  署名  或 空
    let pen = null, noteType = DEFAULT_TYPE, title = "小纸条";

    const angleBracketMatch = rest.match(/<([^>]+)>/);
    if (angleBracketMatch) {
        const inner = angleBracketMatch[1]; // 类型·标题
        const dotIdx = inner.indexOf("·");
        if (dotIdx !== -1) {
            noteType = inner.slice(0, dotIdx).trim() || DEFAULT_TYPE;
            title = inner.slice(dotIdx + 1).trim() || "小纸条";
        } else {
            title = inner.trim();
        }
        // 署名在 < 之前，用 | 分隔
        const beforeAngle = rest.slice(0, angleBracketMatch.index).trim();
        pen = beforeAngle.replace(/\|$/, "").trim() || null;
    } else if (rest) {
        // 没有 <>，把整个 rest 当署名
        pen = rest || null;
    }

    return { toName, pen, noteType, title, day, content };
}

// ========================
// 过滤记录（收件/寄件/类型/日期）
// ========================

function filterRecords(records, { direction, roleName, noteType, day }) {
    return records.filter(r => {
        if (direction === "in" && r.to !== roleName) return false;
        if (direction === "out" && r.from !== roleName) return false;
        if (noteType && r.type !== noteType) return false;
        if (day && r.day && r.day.toUpperCase() !== day.toUpperCase()) return false;
        return true;
    });
}

// ========================
// 构造纸条展示文本
// ========================

function formatNote(r, idx) {
    const penLine = r.pen ? `署名：${r.pen}` : `署名：${r.from}`;
    return `📝 #${idx + 1} 【${r.type}·${r.title}】\n` +
           `📅 ${r.day || "?"}\n` +
           `📮 ${r.from} → ${r.to}\n` +
           `${penLine}\n` +
           `──────────\n${r.content}`;
}

// ========================
// 骰主指令
// ========================

// 1. .给纸条 [类型] 玩家1、玩家2 n
let cmd_give = seal.ext.newCmdItemInfo();
cmd_give.name = "给纸条";
cmd_give.help = ".给纸条 [玩法类型] 玩家名… n\n示例：.给纸条 5 猫头鹰、兔子\n示例：.给纸条 礼物 猫头鹰、兔子 5";
cmd_give.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;

    // 解析参数：最后一个词是数字，倒数第二个是玩家列表，若还有词则是类型
    const raw = cmdArgs.getArgN(1) ? cmdArgs.getAllArgs().trim() : "";
    // 拆分：末尾的纯数字
    const m = raw.match(/^(.*?)\s+(\d+)$/s);
    if (!m) { seal.replyToSender(ctx, msg, "❌ 格式错误，示例：.给纸条 礼物 猫头鹰 5"); return seal.ext.newCmdExecuteResult(true); }

    const before = m[1].trim(), n = parseInt(m[2]);
    // before 可能是 "类型 玩家们" 或 "玩家们"
    // 用最后出现中文名的方式：先试着把第一个词当类型，如果它是已注册玩家名则不是类型
    const players = getPlayers();
    const pmap = players[platform] || {};

    let noteType = DEFAULT_TYPE, namesStr = before;
    const firstSpace = before.search(/\s+/);
    if (firstSpace !== -1) {
        const maybeType = before.slice(0, firstSpace).trim();
        const rest = before.slice(firstSpace).trim();
        // 如果 maybeType 不是玩家名，则视为类型
        if (!pmap[maybeType]) {
            noteType = maybeType;
            namesStr = rest;
        }
    }

    const names = parseNames(namesStr);
    if (!names.length) { seal.replyToSender(ctx, msg, "❌ 未识别到玩家名。"); return seal.ext.newCmdExecuteResult(true); }

    const quotas = getQuotas();
    if (!quotas[platform]) quotas[platform] = {};
    const missing = [];
    for (const name of names) {
        if (!pmap[name]) { missing.push(name); continue; }
        if (!quotas[platform][name]) quotas[platform][name] = {};
        quotas[platform][name][noteType] = (quotas[platform][name][noteType] || 0) + n;
    }
    setQuotas(quotas);

    let reply = `✅ 已为 ${names.filter(n => pmap[n]).join("、")} 增加 ${noteType} 纸条 ${n} 张。`;
    if (missing.length) reply += `\n⚠️ 未找到：${missing.join("、")}`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["给纸条"] = cmd_give;

// 2. .扣除纸条 [类型] 玩家名… n
let cmd_deduct = seal.ext.newCmdItemInfo();
cmd_deduct.name = "扣除纸条";
cmd_deduct.help = ".扣除纸条 [玩法类型] 玩家名… n";
cmd_deduct.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;

    const raw = cmdArgs.getAllArgs().trim();
    const m = raw.match(/^(.*?)\s+(\d+)$/s);
    if (!m) { seal.replyToSender(ctx, msg, "❌ 格式错误，示例：.扣除纸条 礼物 猫头鹰 5"); return seal.ext.newCmdExecuteResult(true); }

    const before = m[1].trim(), n = parseInt(m[2]);
    const players = getPlayers();
    const pmap = players[platform] || {};

    let noteType = DEFAULT_TYPE, namesStr = before;
    const firstSpace = before.search(/\s+/);
    if (firstSpace !== -1) {
        const maybeType = before.slice(0, firstSpace).trim();
        const rest = before.slice(firstSpace).trim();
        if (!pmap[maybeType]) { noteType = maybeType; namesStr = rest; }
    }

    const names = parseNames(namesStr);
    const quotas = getQuotas();
    if (!quotas[platform]) quotas[platform] = {};

    for (const name of names) {
        if (!pmap[name]) continue;
        if (!quotas[platform][name]) quotas[platform][name] = {};
        quotas[platform][name][noteType] = Math.max(0, (quotas[platform][name][noteType] || 0) - n);
    }
    setQuotas(quotas);

    seal.replyToSender(ctx, msg, `✅ 已为 ${names.filter(n => pmap[n]).join("、")} 扣除 ${noteType} 纸条 ${n} 张（不低于0）。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["扣除纸条"] = cmd_deduct;

// 3. .纸条清零 [类型] 玩家名…
let cmd_reset_quota = seal.ext.newCmdItemInfo();
cmd_reset_quota.name = "纸条清零";
cmd_reset_quota.help = ".纸条清零 [玩法类型] 玩家名…";
cmd_reset_quota.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;

    const raw = cmdArgs.getAllArgs().trim();
    const players = getPlayers();
    const pmap = players[platform] || {};

    let noteType = DEFAULT_TYPE, namesStr = raw;
    const firstSpace = raw.search(/\s+/);
    if (firstSpace !== -1) {
        const maybeType = raw.slice(0, firstSpace).trim();
        const rest = raw.slice(firstSpace).trim();
        if (!pmap[maybeType]) { noteType = maybeType; namesStr = rest; }
    }

    const names = parseNames(namesStr);
    const quotas = getQuotas();
    if (!quotas[platform]) quotas[platform] = {};

    for (const name of names) {
        if (!pmap[name]) continue;
        if (!quotas[platform][name]) quotas[platform][name] = {};
        quotas[platform][name][noteType] = 0;
    }
    setQuotas(quotas);

    seal.replyToSender(ctx, msg, `✅ 已将 ${names.filter(n => pmap[n]).join("、")} 的 ${noteType} 纸条清零。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["纸条清零"] = cmd_reset_quota;

// 4. .删除小纸条玩家 玩家名
let cmd_remove_player = seal.ext.newCmdItemInfo();
cmd_remove_player.name = "删除小纸条玩家";
cmd_remove_player.help = ".删除小纸条玩家 玩家名";
cmd_remove_player.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const name = cmdArgs.getArgN(1);
    if (!name) { seal.replyToSender(ctx, msg, "❌ 请输入玩家名。"); return seal.ext.newCmdExecuteResult(true); }

    const players = getPlayers();
    if (!players[platform] || !players[platform][name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到玩家：${name}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    delete players[platform][name];
    setPlayers(players);

    // 清理配额和禁用状态
    const quotas = getQuotas();
    if (quotas[platform]) delete quotas[platform][name];
    setQuotas(quotas);

    const disabled = getDisabled();
    if (disabled[platform]) delete disabled[platform][name];
    setDisabled(disabled);

    seal.replyToSender(ctx, msg, `✅ 已注销玩家：${name}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除小纸条玩家"] = cmd_remove_player;

// 5. .绑定纸条公示群
let cmd_bind_public = seal.ext.newCmdItemInfo();
cmd_bind_public.name = "绑定纸条公示群";
cmd_bind_public.help = ".绑定纸条公示群 （在目标群内使用）";
cmd_bind_public.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    if (!msg.groupId) { seal.replyToSender(ctx, msg, "❌ 请在群聊中使用此指令。"); return seal.ext.newCmdExecuteResult(true); }

    const gid = msg.groupId.replace(/[^\d]/g, "");
    setPublicGroup(gid);
    seal.replyToSender(ctx, msg, `✅ 已将本群（${gid}）设为纸条公示群。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["绑定纸条公示群"] = cmd_bind_public;

// 6. .重置小纸条
let cmd_reset_all = seal.ext.newCmdItemInfo();
cmd_reset_all.name = "重置小纸条";
cmd_reset_all.help = ".重置小纸条 （骰主专用，清空所有数据）";
cmd_reset_all.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }

    ext.storageSet("note_players", "{}");
    ext.storageSet("note_quotas", "{}");
    ext.storageSet("note_disabled", "{}");
    ext.storageSet("note_records", "[]");
    ext.storageSet("note_check_rate", "{}");
    ext.storageSet("note_check_text", "{}");
    ext.storageSet("note_check_hide", "{}");
    ext.storageSet("note_public_group", "");
    ext.storageSet("note_global_day", "D0");

    seal.replyToSender(ctx, msg, "✅ 小纸条插件已完全重置。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["重置小纸条"] = cmd_reset_all;

// 7. .重置纸条时间轴
let cmd_reset_day = seal.ext.newCmdItemInfo();
cmd_reset_day.name = "重置纸条时间轴";
cmd_reset_day.help = ".重置纸条时间轴 （将时间轴重置为D0，并为现有所有纸条标注当前日期）";
cmd_reset_day.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }

    setGlobalDay("D0");

    // 将所有没有 day 的纸条补上 D0
    const records = getRecords();
    for (const r of records) {
        if (!r.day) r.day = "D0";
    }
    setRecords(records);

    seal.replyToSender(ctx, msg, "✅ 时间轴已重置为 D0，所有纸条日期已更新。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["重置纸条时间轴"] = cmd_reset_day;

// ========================
// 骰主：查看收件/寄件
// ========================

// 解析查看参数：[类型] [dx] 玩家名
function parseViewArgs(raw, platform) {
    // raw 是指令后面的全部文字
    // 找最后一个词（玩家名），往前找 dx，再往前找类型
    const parts = raw.trim().split(/\s+/);
    const players = getPlayers();
    const pmap = players[platform] || {};

    let roleName = null, noteType = null, day = null;

    // 从后往前扫
    let remaining = [...parts];

    // 最后一个词：玩家名
    if (remaining.length && pmap[remaining[remaining.length - 1]]) {
        roleName = remaining.pop();
    }

    // 再看有没有 dx
    if (remaining.length && /^d\d+$/i.test(remaining[remaining.length - 1])) {
        day = remaining.pop().toUpperCase();
    }

    // 剩余：类型
    if (remaining.length) {
        noteType = remaining.join(" ").trim() || null;
    }

    return { roleName, noteType, day };
}

// 8. .查看纸条收件 [类型] [dx] 玩家名
let cmd_view_inbox = seal.ext.newCmdItemInfo();
cmd_view_inbox.name = "查看纸条收件";
cmd_view_inbox.help = ".查看纸条收件 [玩法类型] [dx] 玩家名\n示例：.查看纸条收件 猫头鹰\n示例：.查看纸条收件 礼物 d1 猫头鹰";
cmd_view_inbox.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const raw = cmdArgs.getAllArgs().trim();
    const { roleName, noteType, day } = parseViewArgs(raw, platform);

    if (!roleName) { seal.replyToSender(ctx, msg, "❌ 未识别到玩家名，请确认该玩家已绑定。"); return seal.ext.newCmdExecuteResult(true); }

    const records = getRecords();
    const filtered = filterRecords(records, { direction: "in", roleName, noteType, day });

    if (!filtered.length) {
        seal.replyToSender(ctx, msg, `📭 ${roleName} 没有符合条件的收件记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const header = `📥 ${roleName} 的收件箱（${noteType || "全部"}${day ? " · " + day : ""}）共 ${filtered.length} 条`;
    const nodes = [makeNode(ctx, "📮 纸条系统", header), ...filtered.map((r, i) => makeNode(ctx, r.from || "匿名", formatNote(r, i)))];
    sendForward(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看纸条收件"] = cmd_view_inbox;

// 9. .查看纸条寄出 [类型] [dx] 玩家名
let cmd_view_outbox = seal.ext.newCmdItemInfo();
cmd_view_outbox.name = "查看纸条寄出";
cmd_view_outbox.help = ".查看纸条寄出 [玩法类型] [dx] 玩家名\n示例：.查看纸条寄出 猫头鹰\n示例：.查看纸条寄出 礼物 d1 猫头鹰";
cmd_view_outbox.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const raw = cmdArgs.getAllArgs().trim();
    const { roleName, noteType, day } = parseViewArgs(raw, platform);

    if (!roleName) { seal.replyToSender(ctx, msg, "❌ 未识别到玩家名，请确认该玩家已绑定。"); return seal.ext.newCmdExecuteResult(true); }

    const records = getRecords();
    const filtered = filterRecords(records, { direction: "out", roleName, noteType, day });

    if (!filtered.length) {
        seal.replyToSender(ctx, msg, `📭 ${roleName} 没有符合条件的寄出记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const header = `📤 ${roleName} 的寄件箱（${noteType || "全部"}${day ? " · " + day : ""}）共 ${filtered.length} 条`;
    const nodes = [makeNode(ctx, "📮 纸条系统", header), ...filtered.map((r, i) => makeNode(ctx, r.from || "匿名", formatNote(r, i)))];
    sendForward(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看纸条寄出"] = cmd_view_outbox;

// 10. .设置检定 [类型] X 玩家名…
let cmd_set_check = seal.ext.newCmdItemInfo();
cmd_set_check.name = "设置检定";
cmd_set_check.help = ".设置检定 [玩法类型] 0-100 玩家名…\n示例：.设置检定 30 猫头鹰\n示例：.设置检定 礼物 100 猫头鹰、兔子";
cmd_set_check.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const raw = cmdArgs.getAllArgs().trim();

    // 格式：[类型] 数字 玩家名…
    // 找第一个纯数字 token
    const tokens = raw.split(/\s+/);
    let noteType = DEFAULT_TYPE, rate = null, namesStr = "";
    const players = getPlayers();
    const pmap = players[platform] || {};

    let numIdx = -1;
    for (let i = 0; i < tokens.length; i++) {
        if (/^\d+$/.test(tokens[i])) { numIdx = i; break; }
    }
    if (numIdx === -1) { seal.replyToSender(ctx, msg, "❌ 请提供检定率数字（0-100）。"); return seal.ext.newCmdExecuteResult(true); }

    rate = Math.min(100, Math.max(0, parseInt(tokens[numIdx])));
    if (numIdx > 0) noteType = tokens.slice(0, numIdx).join(" ");
    namesStr = tokens.slice(numIdx + 1).join(" ");

    const names = parseNames(namesStr);
    if (!names.length) { seal.replyToSender(ctx, msg, "❌ 未识别到玩家名。"); return seal.ext.newCmdExecuteResult(true); }

    const checkRate = getCheckRate();
    if (!checkRate[platform]) checkRate[platform] = {};

    const ok = [], missing = [];
    for (const name of names) {
        if (!pmap[name]) { missing.push(name); continue; }
        if (!checkRate[platform][name]) checkRate[platform][name] = {};
        checkRate[platform][name][noteType] = rate;
        ok.push(name);
    }
    setCheckRate(checkRate);

    let reply = `✅ 已为 ${ok.join("、")} 设置 ${noteType} 检定率为 ${rate}%。`;
    if (rate === 0) reply += `（0% = 不公示）`;
    else if (rate === 100) reply += `（100% = 必公示）`;
    if (missing.length) reply += `\n⚠️ 未找到：${missing.join("、")}`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置检定"] = cmd_set_check;

// 11. .设置公示文案 [类型] 文案
let cmd_set_announce = seal.ext.newCmdItemInfo();
cmd_set_announce.name = "设置公示文案";
cmd_set_announce.help = ".设置公示文案 [玩法类型] 文案内容\n示例：.设置公示文案 纸条掉出来啦！\n示例：.设置公示文案 礼物 礼物纸条掉啦！";
cmd_set_announce.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }

    const raw = cmdArgs.getAllArgs().trim();
    const players = getPlayers();
    const platform = msg.platform;
    const pmap = players[platform] || {};

    // 第一个词如果不是玩家名且有多个词，视为类型
    const firstSpace = raw.search(/\s+/);
    let noteType = DEFAULT_TYPE, text = raw;
    if (firstSpace !== -1) {
        const maybeType = raw.slice(0, firstSpace).trim();
        if (!pmap[maybeType]) {
            noteType = maybeType;
            text = raw.slice(firstSpace).trim();
        }
    }

    const checkText = getCheckText();
    checkText[noteType] = text;
    setCheckText(checkText);

    seal.replyToSender(ctx, msg, `✅ 已设置 ${noteType} 的公示文案：${text}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置公示文案"] = cmd_set_announce;

// 12. .设置隐藏检定 [类型] 是/否
let cmd_hide_check = seal.ext.newCmdItemInfo();
cmd_hide_check.name = "设置隐藏检定";
cmd_hide_check.help = ".设置隐藏检定 [玩法类型] 是/否\n示例：.设置隐藏检定 是\n示例：.设置隐藏检定 礼物 是";
cmd_hide_check.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }

    const raw = cmdArgs.getAllArgs().trim();
    const tokens = raw.split(/\s+/);
    const last = tokens[tokens.length - 1];
    const hide = last === "是" || last === "yes" || last === "true";
    const noteType = tokens.length > 1 ? tokens.slice(0, -1).join(" ") : DEFAULT_TYPE;

    const checkHide = getCheckHide();
    checkHide[noteType] = hide;
    setCheckHide(checkHide);

    seal.replyToSender(ctx, msg, `✅ 已${hide ? "开启" : "关闭"} ${noteType} 的检定率隐藏。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置隐藏检定"] = cmd_hide_check;

// 13. .显示小纸条计数
let cmd_show_counts = seal.ext.newCmdItemInfo();
cmd_show_counts.name = "显示小纸条计数";
cmd_show_counts.help = ".显示小纸条计数 （显示各类型纸条的发送总数）";
cmd_show_counts.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }

    const records = getRecords();
    const typeCounts = {};
    for (const r of records) {
        typeCounts[r.type] = (typeCounts[r.type] || 0) + 1;
    }

    if (!Object.keys(typeCounts).length) {
        seal.replyToSender(ctx, msg, "📊 暂无纸条记录。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = "📊 各类型纸条发送计数：\n";
    for (const [type, count] of Object.entries(typeCounts)) {
        reply += `  · ${type}：${count} 张\n`;
    }
    reply += `合计：${records.length} 张`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["显示小纸条计数"] = cmd_show_counts;

// 14. .纸条玩家列表
let cmd_player_list = seal.ext.newCmdItemInfo();
cmd_player_list.name = "纸条玩家列表";
cmd_player_list.help = ".纸条玩家列表 （查看所有已绑定玩家）";
cmd_player_list.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const players = getPlayers();
    const pmap = players[platform] || {};
    const names = Object.keys(pmap);

    if (!names.length) {
        seal.replyToSender(ctx, msg, "📋 当前无已绑定玩家。");
        return seal.ext.newCmdExecuteResult(true);
    }

    seal.replyToSender(ctx, msg, `📋 已绑定玩家（${names.length} 人）：\n${names.map(n => `  · ${n}`).join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["纸条玩家列表"] = cmd_player_list;

// 15. .禁用纸条 [类型] 玩家名
let cmd_ban = seal.ext.newCmdItemInfo();
cmd_ban.name = "禁用纸条";
cmd_ban.help = ".禁用纸条 [玩法类型] 玩家名\n示例：.禁用纸条 猫头鹰\n示例：.禁用纸条 礼物 猫头鹰";
cmd_ban.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const raw = cmdArgs.getAllArgs().trim();
    const players = getPlayers();
    const pmap = players[platform] || {};

    const tokens = raw.split(/\s+/);
    let noteType = DEFAULT_TYPE, name = "";
    if (tokens.length >= 2 && !pmap[tokens[0]]) {
        noteType = tokens[0];
        name = tokens.slice(1).join(" ");
    } else {
        name = raw;
    }

    if (!pmap[name]) { seal.replyToSender(ctx, msg, `❌ 未找到玩家：${name}`); return seal.ext.newCmdExecuteResult(true); }

    const disabled = getDisabled();
    if (!disabled[platform]) disabled[platform] = {};
    if (!disabled[platform][name]) disabled[platform][name] = {};
    disabled[platform][name][noteType] = true;
    setDisabled(disabled);

    seal.replyToSender(ctx, msg, `✅ 已禁用 ${name} 的 ${noteType} 纸条发送。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["禁用纸条"] = cmd_ban;

// 16. .解禁纸条 [类型] 玩家名
let cmd_unban = seal.ext.newCmdItemInfo();
cmd_unban.name = "解禁纸条";
cmd_unban.help = ".解禁纸条 [玩法类型] 玩家名\n示例：.解禁纸条 猫头鹰\n示例：.解禁纸条 礼物 猫头鹰";
cmd_unban.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "❌ 仅骰主可用。"); return seal.ext.newCmdExecuteResult(true); }
    const platform = msg.platform;
    const raw = cmdArgs.getAllArgs().trim();
    const players = getPlayers();
    const pmap = players[platform] || {};

    const tokens = raw.split(/\s+/);
    let noteType = DEFAULT_TYPE, name = "";
    if (tokens.length >= 2 && !pmap[tokens[0]]) {
        noteType = tokens[0];
        name = tokens.slice(1).join(" ");
    } else {
        name = raw;
    }

    if (!pmap[name]) { seal.replyToSender(ctx, msg, `❌ 未找到玩家：${name}`); return seal.ext.newCmdExecuteResult(true); }

    const disabled = getDisabled();
    if (disabled[platform] && disabled[platform][name]) {
        delete disabled[platform][name][noteType];
    }
    setDisabled(disabled);

    seal.replyToSender(ctx, msg, `✅ 已解禁 ${name} 的 ${noteType} 纸条发送。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["解禁纸条"] = cmd_unban;

// ========================
// 玩家通用指令
// ========================

// 1. .纸条绑定 玩家名
let cmd_bind = seal.ext.newCmdItemInfo();
cmd_bind.name = "纸条绑定";
cmd_bind.help = ".纸条绑定 玩家名";
cmd_bind.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const name = cmdArgs.getArgN(1);

    if (!name) { seal.replyToSender(ctx, msg, "❌ 请输入要绑定的角色名。"); return seal.ext.newCmdExecuteResult(true); }

    const players = getPlayers();
    if (!players[platform]) players[platform] = {};

    // 检查名字是否已被他人绑定
    const existingUid = players[platform][name];
    if (existingUid && existingUid !== uid) {
        seal.replyToSender(ctx, msg, `❌ 角色名「${name}」已被他人使用。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查自己是否已有绑定
    const myName = findPlayerByUid(platform, uid);
    if (myName && myName !== name) {
        seal.replyToSender(ctx, msg, `⚠️ 你已绑定角色「${myName}」，请先解除绑定再重新绑定。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    players[platform][name] = uid;
    setPlayers(players);

    seal.replyToSender(ctx, msg, `✅ 已绑定角色：${name}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["纸条绑定"] = cmd_bind;

// 2. .解除纸条绑定
let cmd_unbind = seal.ext.newCmdItemInfo();
cmd_unbind.name = "解除纸条绑定";
cmd_unbind.help = ".解除纸条绑定";
cmd_unbind.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const name = findPlayerByUid(platform, uid);

    if (!name) { seal.replyToSender(ctx, msg, "❌ 你尚未绑定角色。"); return seal.ext.newCmdExecuteResult(true); }

    const players = getPlayers();
    delete players[platform][name];
    setPlayers(players);

    seal.replyToSender(ctx, msg, `✅ 已解除角色「${name}」的绑定。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["解除纸条绑定"] = cmd_unbind;

// 3. .to 收件人 署名|<类型·标题> 时间：dx 内容：XXXXX
let cmd_send = seal.ext.newCmdItemInfo();
cmd_send.name = "to";
cmd_send.help = ".to 收件人 [署名|]<类型·标题> 时间：dx 内容：……\n示例：.to 兔子 匿名|<小纸条·秘密> 时间：d1 内容：你好呀";
cmd_send.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const sendName = findPlayerByUid(platform, uid);

    if (!sendName) {
        seal.replyToSender(ctx, msg, "❌ 请先使用 .纸条绑定 角色名 完成绑定。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const rawAll = cmdArgs.getAllArgs().trim();
    const parsed = parseToCmd(rawAll);

    if (!parsed) {
        seal.replyToSender(ctx, msg, "❌ 格式错误。\n正确格式：.to 收件人 [署名|]<类型·标题> 时间：dx 内容：……\n示例：.to 兔子 匿名|<小纸条·秘密> 时间：d1 内容：你好呀");
        return seal.ext.newCmdExecuteResult(true);
    }

    const { toName, pen, noteType, title, day, content } = parsed;

    // 验证收件人
    const players = getPlayers();
    const pmap = players[platform] || {};
    if (!pmap[toName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到收件人：${toName}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查禁用
    const disabled = getDisabled();
    if (disabled[platform] && disabled[platform][sendName] && disabled[platform][sendName][noteType]) {
        seal.replyToSender(ctx, msg, `❌ 你的 ${noteType} 纸条发送功能已被禁用。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查配额
    const quotas = getQuotas();
    const remaining = (quotas[platform] && quotas[platform][sendName] && quotas[platform][sendName][noteType]) || 0;
    if (remaining <= 0) {
        seal.replyToSender(ctx, msg, `❌ 你的 ${noteType} 纸条已用完（剩余 0 张）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 扣除配额
    quotas[platform][sendName][noteType] = remaining - 1;
    setQuotas(quotas);

    // 记录
    const gameDay = day || getGlobalDay();
    const record = {
        id: Date.now() + "_" + Math.random().toString(36).slice(2, 6),
        from: sendName, to: toName,
        type: noteType, title, pen, day: gameDay, content,
        ts: Date.now()
    };
    const records = getRecords();
    records.push(record);
    setRecords(records);

    // 给发送者回执
    seal.replyToSender(ctx, msg, `📮 纸条已寄出！\n收件人：${toName}\n类型：${noteType} · ${title}\n日期：${gameDay}\n剩余 ${noteType} 纸条：${remaining - 1} 张`);

    // ✅ 检定 & 公示
    const checkRate = getCheckRate();
    const rate = (checkRate[platform] && checkRate[platform][toName] && checkRate[platform][toName][noteType]);
    const finalRate = (rate !== undefined && rate !== null) ? rate : 0;

    if (finalRate > 0) {
        const roll = Math.random() * 100;
        const dropped = roll < finalRate;

        if (dropped) {
            const publicGid = getPublicGroup();
            if (publicGid) {
                const checkHide = getCheckHide();
                const hide = checkHide[noteType] === true;
                const checkText = getCheckText();
                const announceText = checkText[noteType] || "📌 纸条意外曝光了！";

                let publicMsg = `${announceText}\n`;
                publicMsg += `📝 【${noteType}·${title}】${gameDay}\n`;
                publicMsg += `📮 ${hide ? "某人" : sendName} → ${toName}\n`;
                if (!hide) publicMsg += `检定：${finalRate}% 命中 ${roll.toFixed(1)}%\n`;
                publicMsg += `──────────\n${content}`;
                if (pen) publicMsg += `\n\n落款：${pen}`;

                const pMsg = seal.newMessage();
                pMsg.messageType = "group";
                pMsg.groupId = `${platform}-Group:${publicGid}`;
                const pCtx = seal.createTempCtx(ctx.endPoint, pMsg);
                seal.replyToSender(pCtx, pMsg, publicMsg);
            }
        }
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["to"] = cmd_send;

// 4. .我的纸条收件箱 [类型] [dx]
let cmd_my_inbox = seal.ext.newCmdItemInfo();
cmd_my_inbox.name = "我的纸条收件箱";
cmd_my_inbox.help = ".我的纸条收件箱 [玩法类型] [dx]\n示例：.我的纸条收件箱\n示例：.我的纸条收件箱 礼物 d1";
cmd_my_inbox.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const roleName = findPlayerByUid(platform, uid);

    if (!roleName) { seal.replyToSender(ctx, msg, "❌ 请先绑定角色。"); return seal.ext.newCmdExecuteResult(true); }

    const raw = cmdArgs.getAllArgs().trim();
    const tokens = raw.split(/\s+/).filter(Boolean);
    let noteType = null, day = null;

    if (tokens.length >= 2) {
        if (/^d\d+$/i.test(tokens[tokens.length - 1])) {
            day = tokens.pop().toUpperCase();
            noteType = tokens.join(" ") || null;
        } else {
            noteType = tokens.join(" ");
        }
    } else if (tokens.length === 1) {
        if (/^d\d+$/i.test(tokens[0])) day = tokens[0].toUpperCase();
        else noteType = tokens[0];
    }

    const records = getRecords();
    const filtered = filterRecords(records, { direction: "in", roleName, noteType, day });

    if (!filtered.length) {
        seal.replyToSender(ctx, msg, `📭 收件箱为空（${noteType || "全部"}${day ? " · " + day : ""}）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const header = `📥 ${roleName} 的收件箱（${noteType || "全部"}${day ? " · " + day : ""}）共 ${filtered.length} 条`;
    const nodes = [makeNode(ctx, "📮 纸条系统", header), ...filtered.map((r, i) => makeNode(ctx, r.from || "匿名", formatNote(r, i)))];
    sendForward(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的纸条收件箱"] = cmd_my_inbox;

// 5. .我的纸条寄件箱 [类型] [dx]
let cmd_my_outbox = seal.ext.newCmdItemInfo();
cmd_my_outbox.name = "我的纸条寄件箱";
cmd_my_outbox.help = ".我的纸条寄件箱 [玩法类型] [dx]\n示例：.我的纸条寄件箱\n示例：.我的纸条寄件箱 礼物 d1";
cmd_my_outbox.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const roleName = findPlayerByUid(platform, uid);

    if (!roleName) { seal.replyToSender(ctx, msg, "❌ 请先绑定角色。"); return seal.ext.newCmdExecuteResult(true); }

    const raw = cmdArgs.getAllArgs().trim();
    const tokens = raw.split(/\s+/).filter(Boolean);
    let noteType = null, day = null;

    if (tokens.length >= 2) {
        if (/^d\d+$/i.test(tokens[tokens.length - 1])) {
            day = tokens.pop().toUpperCase();
            noteType = tokens.join(" ") || null;
        } else {
            noteType = tokens.join(" ");
        }
    } else if (tokens.length === 1) {
        if (/^d\d+$/i.test(tokens[0])) day = tokens[0].toUpperCase();
        else noteType = tokens[0];
    }

    const records = getRecords();
    const filtered = filterRecords(records, { direction: "out", roleName, noteType, day });

    if (!filtered.length) {
        seal.replyToSender(ctx, msg, `📭 寄件箱为空（${noteType || "全部"}${day ? " · " + day : ""}）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const header = `📤 ${roleName} 的寄件箱（${noteType || "全部"}${day ? " · " + day : ""}）共 ${filtered.length} 条`;
    const nodes = [makeNode(ctx, "📮 纸条系统", header), ...filtered.map((r, i) => makeNode(ctx, r.from || "匿名", formatNote(r, i)))];
    sendForward(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的纸条寄件箱"] = cmd_my_outbox;

// 6. .我的小纸条
let cmd_my_notes = seal.ext.newCmdItemInfo();
cmd_my_notes.name = "我的小纸条";
cmd_my_notes.help = ".我的小纸条 （查看所有类型剩余配额）";
cmd_my_notes.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(platform + ":", "");
    const roleName = findPlayerByUid(platform, uid);

    if (!roleName) { seal.replyToSender(ctx, msg, "❌ 请先绑定角色。"); return seal.ext.newCmdExecuteResult(true); }

    const quotas = getQuotas();
    const myQuotas = (quotas[platform] && quotas[platform][roleName]) || {};

    if (!Object.keys(myQuotas).length) {
        seal.replyToSender(ctx, msg, `📝 ${roleName}，你目前没有任何纸条配额。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = `📝 ${roleName} 的纸条余量：\n`;
    for (const [type, count] of Object.entries(myQuotas)) {
        const disabled = getDisabled();
        const isBanned = disabled[platform] && disabled[platform][roleName] && disabled[platform][roleName][type];
        reply += `  · ${type}：${count} 张${isBanned ? "（已禁用）" : ""}\n`;
    }
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的小纸条"] = cmd_my_notes;

// 7. .小纸条帮助
let cmd_help = seal.ext.newCmdItemInfo();
cmd_help.name = "小纸条帮助";
cmd_help.help = ".小纸条帮助 （显示完整帮助文档）";
cmd_help.solve = (ctx, msg, cmdArgs) => {
    const helpText = `📝 小纸条插件帮助 v2.2
====================
【基本概念】
- 消息权限：可以有多个玩法类型，每种类型的配额独立管理
- 公示群：骰主指定的群聊，用于公示检定掉落的小纸条

【骰主专用命令】
.给纸条 [类型] 玩家… n — 增加指定玩法类型配额
.扣除纸条 [类型] 玩家… n — 扣除配额
.纸条清零 [类型] 玩家… — 将配额清零
.删除小纸条玩家 玩家名 — 注销玩家
.绑定纸条公示群 — 将当前群设为公示群
.重置小纸条 — 重置所有数据
.重置纸条时间轴 — 重置时间轴到D0
.查看纸条收件 [类型] [dx] 玩家名 — 查看收件
.查看纸条寄出 [类型] [dx] 玩家名 — 查看寄件
.设置检定 [类型] 0-100 玩家… — 设置公示率
.设置公示文案 [类型] 文案 — 设置公示文案
.设置隐藏检定 [类型] 是/否 — 是否隐藏检定率
.显示小纸条计数 — 查看各类型发送数
.纸条玩家列表 — 查看已绑定玩家
.禁用纸条 [类型] 玩家名 — 禁止该玩家发送
.解禁纸条 [类型] 玩家名 — 解除禁止

【玩家通用命令】
.纸条绑定 角色名 — 绑定进入系统
.解除纸条绑定 — 解除绑定
.to 收件人 [署名|]<类型·标题> 时间：dx 内容：…… — 发送纸条
.我的纸条收件箱 [类型] [dx] — 查看收件
.我的纸条寄件箱 [类型] [dx] — 查看寄件
.我的小纸条 — 查看配额余量

【.to 格式说明】
.to 兔子 匿名|<小纸条·秘密> 时间：d1 内容：你好呀
           ↑署名  ↑类型  ↑标题
署名和<>部分可省略，省略时使用默认类型「小纸条」`;

    seal.replyToSender(ctx, msg, helpText);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["小纸条帮助"] = cmd_help;

// ========================
// 配置项注册
// ========================

seal.ext.registerStringConfig(ext, "ws地址", "ws://127.0.0.1:3001", "OneBot WS 地址（合并转发功能需要）");
seal.ext.registerStringConfig(ext, "ws_token", "", "WS Access Token（可留空）");

console.log("[小纸条] 插件加载完成 v2.2.0");
