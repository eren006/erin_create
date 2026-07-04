// ==UserScript==
// @name         季度管理系统
// @author       长日将尽
// @version      1.0.0
// @description  季度管理、时间线修改、场次状态（卫星插件）。所有数据存储在主插件 changri 中。
// @timestamp    1750291200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%AD%A3%E5%BA%A6.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%AD%A3%E5%BA%A6.js
// ==/UserScript==

let ext = seal.ext.find('season_system');
if (!ext) {
    ext = seal.ext.new("season_system", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

const STATS_CHUNK_SIZE = 20; // 统计转发消息每批最大节点数

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()                      { return globalThis.__changriApi || null; }
function mainStorGet(key)              { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val)         { getApi()?.kvSetRaw(key, val); }

// JSON 对象读写：走主插件 kvGet/kvSet（带缓存与损坏容错），JSON key 一律用这两个函数
function mainKvGet(key, def) { const api = getApi(); return api ? api.kvGet(key, def) : def; }
function mainKvSet(key, val) { getApi()?.kvSet(key, val); }
function isUserAdmin(ctx, msg)         { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function isArchiveEnabled()            { return getApi()?.isArchiveEnabled() ?? false; }
function ws(postData, ctx, msg, ok, err) { return getApi()?.ws(postData, ctx, msg, ok, err); }
function wsBatchSync(queue, ctx, msg)  { return getApi()?.wsBatchSync(queue, ctx, msg); }
function getRoleDetails(platform, name){ return getApi()?.getRoleDetails(platform, name) ?? {}; }
function getUidByRoleName(p, name)     { return getApi()?.getUidByRoleName(p, name) ?? null; }
function getRoleStorage()              { return getApi()?.getRoleStorage() ?? {}; }
function sendTextToGroup(p, gid, text) { return getApi()?.sendTextToGroup(p, gid, text); }
function parseAndValidateTime(t, r, d, s) { return getApi()?.parseAndValidateTime(t, r, d, s) ?? { valid: false, errorMsg: "API未加载" }; }
function getSeasonShowName()           { return getApi()?.getSeasonShowName() ?? ""; }
function hasActiveSeason()             { return getApi()?.hasActiveSeason() ?? false; }
function isRoleStorageEmpty()          { return getApi()?.isRoleStorageEmpty() ?? true; }
function getSessionStats()             { return getApi()?.getSessionStats() ?? {}; }
function saveSessionStats(ss)          { getApi()?.saveSessionStats(ss); }
function getCustomTypeLabel(s)         { return getApi()?.getCustomTypeLabel(s) ?? s; }
function timeConflict(nd, nt, ed, et)  { return getApi()?.timeConflict(nd, nt, ed, et) ?? false; }
function setGroupName(ctx, msg, gid, n){ return getApi()?.setGroupName(ctx, msg, gid, n); }
function getIdleGroupName()            { return getApi()?.getIdleGroupName() ?? "空闲群"; }
function cleanupGroupTimer(gid)        { getApi()?.cleanupGroupTimer(gid); }
// 以下两个需要读插件配置，无法通过共享 API 获取，保留直接访问
function _mainExt()        { return seal.ext.find('changri'); }
function getArchiveBase()  { const m = _mainExt(); return m ? (seal.ext.getStringConfig(m, "RP存档服务器地址") || "").replace(/\/$/, "") : ""; }
function getArchiveToken() { const m = _mainExt(); return m ? (seal.ext.getStringConfig(m, "RP存档Token") || "") : ""; }

// ========================
// RPG背包辅助（供补发奖励使用）
// ========================

function getRegistry_rpg() {
    return mainKvGet("item_registry", {});
}
function getInvAll_rpg() {
    return mainKvGet("global_inventories", {});
}
function saveInvAll_rpg(invs) {
    mainKvSet("global_inventories", invs);
}
function addToInv_local(roleKey, code, count) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    const reg = getRegistry_rpg();
    const itemInfo = reg[code];
    if (!itemInfo) { console.error(`[季度] 尝试添加不存在的物品代码: ${code}`); return false; }
    const initialUses = itemInfo.maxUses ?? -1;
    const entry = inv.find(e => e.code === code && (e.remainingUses ?? -1) === initialUses);
    if (entry) { entry.count += count; } else { inv.push({ code, count, remainingUses: initialUses }); }
    invs[roleKey] = inv;
    saveInvAll_rpg(invs);
    return true;
}

// ========================
// 📋 管理帮助（运营清单）
// ========================
let cmd_admin_help = seal.ext.newCmdItemInfo();
cmd_admin_help.name = "管理帮助";
cmd_admin_help.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const base = getArchiveBase();
    const groupsUrl = base ? `${base}/admin/groups`         : "（未配置存档服务器地址）";
    const guidesUrl = base ? `${base}/admin/command_guides` : "（未配置存档服务器地址）";
    const statsUrl  = base ? `${base}/admin/stats`          : "（未配置存档服务器地址）";
    (async () => {
        let guideLines = "";
        if (base) {
            try {
                const token = getArchiveToken();
                const resp = await fetch(`${base}/api/command_guides`, {
                    headers: { "X-Archive-Token": token }
                });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.ok && data.guides && data.guides.length > 0) {
                        guideLines = "\n【📖 当前指令指南（可转发给玩家）】\n" +
                            data.guides.map(g => `  ${g.name}：${g.url}`).join("\n");
                    }
                }
            } catch (_) {}
        }
        const text = [
            "📋 长日运营清单",
            "━".repeat(14),
            "",
            "【🆕 开季流程】",
            "1. 【网页】录入群号组：",
            `   ${groupsUrl}`,
            "2. 【网页】创建指令指南：",
            `   ${guidesUrl}`,
            "3. 。清空季度数据  ← 扫描残留玩家并清空上季数据",
            "4. 。创建新季度 恋综名 复盘/不复盘 MMDD-MMDD [补戏MMDD]",
            "5. 。开启群号组 组名  ← 从后台拉取群号到戏群池",
            "6. 。初始化设置  ← 从后台拉取系统配置（或 。拉取全部 强制覆盖）",
            "7. 。创建NPC 角色名  ← 注册所有NPC（复盘模式必须）",
            "8. 玩家自行：创建新角色 角色名",
            "9. 。设置天数 D0  ← 确认天数状态",
            "",
            "【📅 日常运营】",
            "• 查看进行中         ← 查看所有进行中约会",
            "• 查看计时器         ← 查看活跃群倒计时",
            "• 提醒超时           ← 向超时群发送提醒",
            "• 。设置天数 Dx      ← 手动推进天数（或 。开启自动天数）",
            "• 。功能权限 角色名 功能 开启/关闭  ← 管控玩家权限",
            "• 。调整 角色名 物品码 +N/-N       ← 调整背包物品",
            `• 全员统计/本季报表：${statsUrl}`,
            "",
            "【🏁 结季流程】",
            "1. 。结束季度  ← 封存并获取公开存档链接",
            "2. 确认存档链接内容无误",
            "3. 更新未退群 驱逐  ← 踢出所有仍在群内的玩家",
            "4. 。清空季度数据  ← 确认无人残留后清空",
        ].join("\n") + guideLines;
        seal.replyToSender(ctx, msg, text);
    })();
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["管理帮助"] = cmd_admin_help;

// ========================
// 删除时间线
// ========================
let cmd_delete_timeline_precise = seal.ext.newCmdItemInfo();
cmd_delete_timeline_precise.name = "删除时间线";
cmd_delete_timeline_precise.help = "。删除时间线 天数 时间 角色名\n示例：。删除时间线 D1 14:00 张三";
cmd_delete_timeline_precise.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);

    const day = cmdArgs.getArgN(1);
    const time = cmdArgs.getArgN(2);
    const name = cmdArgs.getArgN(3);

    if (!day || !time || !name) {
        seal.replyToSender(ctx, msg, "⚠️ 参数不足！\n格式：。删除时间线 [天数] [时间] [角色名]");
        return seal.ext.newCmdExecuteResult(true);
    }

    let confirmed = mainKvGet("b_confirmedSchedule", {});
    const platform = msg.platform;
    const privateGroups = mainKvGet("a_private_group", {});

    const targetUid = privateGroups?.[platform]?.[name]?.[0];
    if (!targetUid) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色 ${name} 的注册信息。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetKey = `${platform}:${targetUid}`;

    const userSchedule = confirmed[targetKey] || [];
    const appointment = userSchedule.find(ev => ev.day === day && ev.time === time);

    if (!appointment) {
        seal.replyToSender(ctx, msg, `❌ 在 ${name} 的日程中未找到 ${day} ${time} 的记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (appointment.partner === "多人小群") {
        const gid = appointment.group;
        let deletedCount = 0;
        for (let uid in confirmed) {
            let before = confirmed[uid].length;
            confirmed[uid] = confirmed[uid].filter(ev => ev.group !== gid);
            if (confirmed[uid].length < before) deletedCount++;
        }
        mainKvSet("b_confirmedSchedule", confirmed);
        seal.replyToSender(ctx, msg, `✅ 已根据多人小群 ID(${gid}) 抹除所有参与者的排期（共 ${deletedCount} 人）。`);
    } else {
        const partnerName = appointment.partner;
        const partnerUid = privateGroups?.[platform]?.[partnerName]?.[0];
        const partnerKey = partnerUid ? `${platform}:${partnerUid}` : null;

        confirmed[targetKey] = confirmed[targetKey].filter(ev => !(ev.day === day && ev.time === time));
        if (partnerKey && confirmed[partnerKey]) {
            confirmed[partnerKey] = confirmed[partnerKey].filter(ev => !(ev.day === day && ev.time === time));
        }
        mainKvSet("b_confirmedSchedule", confirmed);
        seal.replyToSender(ctx, msg, `✅ 已精准抹除 ${name} 与 ${partnerName} 在 ${day} ${time} 的约会记录。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除时间线"] = cmd_delete_timeline_precise;

// ========================
// 同步名片
// ========================
let cmd_sync_now = seal.ext.newCmdItemInfo();
cmd_sync_now.name = "同步名片";
cmd_sync_now.help = "同步名片 公告/戏群/水群";
cmd_sync_now.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);

    const groupTypeMap = {
        "公告": "adminAnnounceGroupId",
        "戏群": "song_group_id",
        "水群": "water_group_id",
    };
    const typeArg = (cmdArgs.args[0] || "").trim();
    const storageKey = groupTypeMap[typeArg];
    if (!storageKey) return seal.replyToSender(ctx, msg, "⚠️ 请指定群类型：同步名片 公告 / 戏群 / 水群");

    const targetGid = mainKvGet(storageKey, null);
    if (!targetGid || targetGid === "未设置") return seal.replyToSender(ctx, msg, `⚠️ ${typeArg}群号未配置`);
    const cleanTargetGid = parseInt(targetGid.toString().replace(/[^\d]/g, ""));
    if (isNaN(cleanTargetGid)) return seal.replyToSender(ctx, msg, `⚠️ ${typeArg}群号无效`);

    const platform = msg.platform;
    const storage = getRoleStorage();
    const pData = storage[platform] || {};
    const names = Object.keys(pData);
    if (!names.length) return seal.replyToSender(ctx, msg, "📭 数据库为空");

    const requestQueue = [];
    names.forEach(uidKey => {
        const data = pData[uidKey];
        if (!Array.isArray(data) || data.length < 2 || !data[0]) return;
        const roleName = data[0];
        const cleanUid = parseInt(uidKey.toString().replace(/[^\d]/g, ""));
        if (isNaN(cleanUid)) return;
        requestQueue.push({
            action: "set_group_card",
            params: { group_id: cleanTargetGid, user_id: cleanUid, card: roleName }
        });
    });

    if (!requestQueue.length) return seal.replyToSender(ctx, msg, "⚠️ 没有有效的同步目标");

    wsBatchSync(requestQueue, ctx, msg);
    seal.replyToSender(ctx, msg, `🔄 正在向${typeArg}同步 ${names.length} 个角色的名片...\n总共需要 ${requestQueue.length} 次操作`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步名片"] = cmd_sync_now;

// ========================
// 📅 修改时间线 / 拒绝时间线（通过 onNotCommandReceived 分发）
// ========================
let cmd_update_schedule = {};
cmd_update_schedule.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const gid = msg.groupId.replace(`${platform}-Group:`, "");
    const newDay = cmdArgs.getArgN(1);
    const newRawTime = cmdArgs.getArgN(2);

    if (!newDay || !newRawTime) return seal.replyToSender(ctx, msg, "⚠️ 格式错误，请使用：.修改时间线 D1 1400-1500");

    let groupExpireInfo = mainKvGet("group_expire_info", {});
    const info = groupExpireInfo[gid];
    if (!info) return seal.replyToSender(ctx, msg, "⚠️ 只有在活跃的私约/电话群内才能修改时间。");

    const allowedRanges = mainKvGet("allowed_appointment_times", []);
    const subtype = info.subtype || "私密";
    const minDuration = subtype === "电话" ? 29 : 59;
    const timeRes = parseAndValidateTime(newRawTime, allowedRanges, minDuration, subtype);
    if (!timeRes.valid) return seal.replyToSender(ctx, msg, timeRes.errorMsg);
    const newTime = timeRes.time;

    let b_confirmedSchedule = mainKvGet("b_confirmedSchedule", {});
    const participants = info.participants || [];
    let conflictNames = [];

    for (let name of participants) {
        const details = getRoleDetails(platform, name);
        if (!details.uid) continue;
        const key = `${platform}:${details.uid.replace(/^[a-z]+:/i, "")}`;
        const hasConflict = (b_confirmedSchedule[key] || []).some(ev =>
            ev.group !== gid && ev.status === "active" && timeConflict(newDay, newTime, ev.day, ev.time)
        );
        if (hasConflict) conflictNames.push(name);
    }

    if (conflictNames.length > 0) {
        return seal.replyToSender(ctx, msg, `❌ 修改失败！以下成员在 ${newDay} ${newTime} 已有其他安排：\n${conflictNames.join("、")}`);
    }

    info.day = newDay;
    info.time = newTime;
    groupExpireInfo[gid] = info;
    mainKvSet("group_expire_info", groupExpireInfo);

    for (let name of participants) {
        const details = getRoleDetails(platform, name);
        const key = `${platform}:${details.uid.replace(/^[a-z]+:/i, "")}`;
        if (b_confirmedSchedule[key]) {
            b_confirmedSchedule[key].forEach(ev => {
                if (ev.group === gid) { ev.day = newDay; ev.time = newTime; }
            });
        }
    }
    mainKvSet("b_confirmedSchedule", b_confirmedSchedule);

    const groupTimersForUpdate = mainKvGet("group_timers", {});
    if (groupTimersForUpdate[gid]) {
        groupTimersForUpdate[gid].day  = newDay;
        groupTimersForUpdate[gid].time = newTime;
        mainKvSet("group_timers", groupTimersForUpdate);
    }

    const nameTag = participants.length > 2 ? "多人" : participants.join("/");
    const newGroupName = `${getCustomTypeLabel(subtype)} ${newDay} ${newTime} ${info.place} ${nameTag}`;
    setGroupName(ctx, msg, gid, newGroupName);

    seal.replyToSender(ctx, msg, `✅ 时间线修改成功！\n📅 新时间：${newDay} ${newTime}\n新的日程已同步至所有参与者的【时间线】。`);
    return seal.ext.newCmdExecuteResult(true);
};

let cmd_abolish_schedule = {};
cmd_abolish_schedule.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const targetGid = cmdArgs.getArgN(1);

    if (!targetGid) return seal.replyToSender(ctx, msg, "⚠️ 格式错误，请使用：.拒绝时间线 群号");

    let groupPool = mainKvGet("group", []);
    let groupExpireInfo = mainKvGet("group_expire_info", {});
    let b_confirmedSchedule = mainKvGet("b_confirmedSchedule", {});
    const a_private_group = mainKvGet("a_private_group", {});

    const fullId = `${targetGid}_占用`;
    const isOccupied = groupPool.includes(fullId);

    if (!isOccupied) return seal.replyToSender(ctx, msg, `⚠️ 群号 ${targetGid} 未处于占用状态，无需拒绝。`);

    const groupInfo = groupExpireInfo[targetGid] || {};
    const subtype = groupInfo.subtype || "私密";
    if (subtype === "心愿" || subtype === "官约") {
        return seal.replyToSender(ctx, msg, `⚠️ ${getCustomTypeLabel(subtype)}不可拒绝，请通过正常流程处理。`);
    }

    const participants = groupInfo.participants || [];

    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const isParticipant = participants.some(name => {
        const details = getRoleDetails(platform, name);
        return details && details.uid && details.uid.replace(/^[a-z]+:/i, "") === uid;
    });
    if (!isParticipant) return seal.replyToSender(ctx, msg, `⚠️ 你不是该约会的参与者，无法拒绝。`);

    const rejecterName = participants.find(name => {
        const details = getRoleDetails(platform, name);
        return details && details.uid && details.uid.replace(/^[a-z]+:/i, "") === uid;
    }) || "对方";

    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${targetGid}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);

    if (participants.length <= 2) {
        seal.replyToSender(groupCtx, groupMsg, `🚫 【约会已取消】\n\n${rejecterName} 取消了这场约会。\n请各位参与者尽快退群，期待下次相遇！`);

        for (let participantName of participants) {
            const participantUid = getUidByRoleName(platform, participantName);
            const targetInfo = participantUid ? a_private_group[platform]?.[participantUid] : null;
            if (!targetInfo) continue;
            const targetGidPrivate = targetInfo[1];
            if (!participantUid || !targetGidPrivate) continue;
            const privateMsg = seal.newMessage();
            privateMsg.messageType = "group";
            privateMsg.groupId = `${platform}-Group:${targetGidPrivate}`;
            const privateCtx = seal.createTempCtx(ctx.endPoint, privateMsg);
            const isSelf = participantUid === uid;
            const privateNotice = isSelf
                ? `✅ 你已取消与 ${participants.filter(n => n !== rejecterName).join("、")} 的约会。`
                : `❌ ${rejecterName} 取消了你们的约会，期待下次相遇！`;
            seal.replyToSender(privateCtx, privateMsg, privateNotice);
        }

        for (let uidKey in b_confirmedSchedule) {
            b_confirmedSchedule[uidKey] = b_confirmedSchedule[uidKey].filter(ev => ev.group !== targetGid);
        }
        mainKvSet("b_confirmedSchedule", b_confirmedSchedule);

        if (groupExpireInfo[targetGid]) {
            delete groupExpireInfo[targetGid];
            mainKvSet("group_expire_info", groupExpireInfo);
        }

        const idx = groupPool.indexOf(fullId);
        if (idx !== -1) {
            groupPool.splice(idx, 1);
            groupPool.push(targetGid);
            mainKvSet("group", groupPool);
        }

        setGroupName(ctx, msg, targetGid, getIdleGroupName());
        cleanupGroupTimer(targetGid);

        seal.replyToSender(ctx, msg, `✅ 已取消群 ${targetGid} 的约会，并通知了相关参与者。`);

    } else {
        const remaining = participants.filter(n => n !== rejecterName);

        seal.replyToSender(groupCtx, groupMsg, `⚠️ 【成员退出】\n\n${rejecterName} 退出了这场约会。\n约会继续，请 ${rejecterName} 尽快退群。`);

        for (let participantName of participants) {
            const participantUid2 = getUidByRoleName(platform, participantName);
            const targetInfo2 = participantUid2 ? a_private_group[platform]?.[participantUid2] : null;
            if (!targetInfo2) continue;
            const targetGidPrivate2 = targetInfo2[1];
            if (!participantUid2 || !targetGidPrivate2) continue;
            const privateMsg = seal.newMessage();
            privateMsg.messageType = "group";
            privateMsg.groupId = `${platform}-Group:${targetGidPrivate2}`;
            const privateCtx = seal.createTempCtx(ctx.endPoint, privateMsg);
            const isSelf = participantUid2 === uid;
            const privateNotice = isSelf
                ? `✅ 你已退出与 ${remaining.join("、")} 的约会，他们将继续进行。`
                : `ℹ️ ${rejecterName} 退出了约会，你与 ${remaining.filter(n => n !== participantName).join("、") || "其他人"} 的约会继续。`;
            seal.replyToSender(privateCtx, privateMsg, privateNotice);
        }

        const rejecterUidForCleanup = getUidByRoleName(platform, rejecterName);
        if (rejecterUidForCleanup) {
            const rejecterKey = `${platform}:${rejecterUidForCleanup}`;
            if (b_confirmedSchedule[rejecterKey]) {
                b_confirmedSchedule[rejecterKey] = b_confirmedSchedule[rejecterKey].filter(ev => ev.group !== targetGid);
            }
        }
        for (const uidKey of Object.keys(b_confirmedSchedule)) {
            for (const ev of b_confirmedSchedule[uidKey]) {
                if (ev.group === targetGid && ev.partner && ev.partner !== "多人小群") {
                    const parts = ev.partner.split(/[、,]/).map(s => s.trim()).filter(n => n !== rejecterName);
                    ev.partner = parts.length === 1 ? parts[0] : parts.join("、");
                }
            }
        }
        mainKvSet("b_confirmedSchedule", b_confirmedSchedule);

        groupExpireInfo[targetGid].participants = remaining;
        mainKvSet("group_expire_info", groupExpireInfo);

        const timersForReject = mainKvGet("group_timers", {});
        const timerEntry = timersForReject[targetGid];
        if (timerEntry) {
            if (Array.isArray(timerEntry.participants)) {
                timerEntry.participants = timerEntry.participants.filter(n => n !== rejecterName);
            }
            if (timerEntry.timerStatus) {
                delete timerEntry.timerStatus[rejecterName];
            }
            mainKvSet("group_timers", timersForReject);
        }

        seal.replyToSender(ctx, msg, `✅ 你已退出群 ${targetGid} 的约会，剩余参与者：${remaining.join("、")}。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};



// ========================
// ── 创建新季度
// ========================
let cmd_new_season = seal.ext.newCmdItemInfo();
cmd_new_season.name = "创建新季度";
cmd_new_season.help = `用法：。创建新季度 恋综名 复盘/不复盘 MMDD-MMDD [补戏MMDD]
前提：须先执行「。清空季度数据」（角色存储为空）

参数说明：
  恋综名       季度显示名
  复盘/不复盘  是否生成复盘存档
  MMDD-MMDD    必填，正式档期范围，如 0528-0601
                 · 开始日前：短信/礼物等互动不记录
                 · 开始日自动设为 D0
  补戏MMDD     可选，补戏截止日（如 0604）
                 · 补戏期：场次记录，但不计弧长

示例：
  创建新季度 某某恋综 复盘 0610-0614
  创建新季度 某某恋综 复盘 0610-0614 0617`;
cmd_new_season.solve = (ctx, msg, cmdArgs) => {
    const seasonName = cmdArgs.getArgN(1);
    const modeArg    = cmdArgs.getArgN(2);
    const scheduleArg = cmdArgs.getArgN(3);
    const suppArg     = cmdArgs.getArgN(4);

    if (!seasonName || seasonName === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    if (hasActiveSeason()) {
        seal.replyToSender(ctx, msg, `❌ 已有活跃季度「${getSeasonShowName()}」，请先「结束季度」再开新季度。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!isRoleStorageEmpty()) {
        seal.replyToSender(ctx, msg, "❌ 请先执行「。清空季度数据」清空角色数据，再创建新季度。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let scheduleStart = "", scheduleEnd = "", supplementEnd = "";
    if (!scheduleArg || !/^\d{4}-\d{4}$/.test(scheduleArg)) {
        seal.replyToSender(ctx, msg, `❌ 档期为必填项，格式 MMDD-MMDD（如 0610-0614）。\n完整用法：。创建新季度 恋综名 复盘/不复盘 MMDD-MMDD [补戏MMDD]`);
        return seal.ext.newCmdExecuteResult(true);
    }
    [scheduleStart, scheduleEnd] = scheduleArg.split("-");
    if (suppArg && /^\d{4}$/.test(suppArg)) {
        supplementEnd = suppArg;
    } else if (suppArg) {
        seal.replyToSender(ctx, msg, `⚠️ 补戏日期格式错误，应为 MMDD（如 0617），已忽略。`);
    }

    const isReview  = !modeArg || modeArg === "复盘";
    const mode      = isReview ? "review" : "no_review";
    const modeLabel = isReview ? "复盘" : "不复盘";

    (async () => {
        const base  = getArchiveBase();
        const token = getArchiveToken();
        if (!base) {
            seal.replyToSender(ctx, msg, "❌ 未配置 RP 存档服务器地址，无法创建季度。");
            return;
        }
        try {
            const resp = await fetch(`${base}/api/new_season`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify({ name: seasonName, mode,
                    schedule_start: scheduleStart,
                    schedule_end:   scheduleEnd,
                    supplement_end: supplementEnd })
            });
            const data = await resp.json();
            if (!data.ok) {
                seal.replyToSender(ctx, msg, `❌ 创建季度失败：${data.error || resp.status}`);
                return;
            }

            mainStorSet("season_show_name", seasonName);
            mainStorSet("season_mode", mode);
            mainStorSet("season_schedule_start", scheduleStart);
            mainStorSet("season_schedule_end",   scheduleEnd);
            mainStorSet("season_supplement_end", supplementEnd);

            const reg = mainKvGet("item_registry", {});
            const specItems = [
                { code: "SPEC_001", name: "追踪器",   desc: "一枚散发着微光的微型追踪器，轻轻按动便能感知目标此刻的行踪。" },
                { code: "SPEC_002", name: "万能钥匙", desc: "一把泛着银光的万能钥匙，据说能开启世间任何一扇被锁住的门。" },
                { code: "SPEC_003", name: "望远镜",   desc: "一架精致的望远镜，使用后可在目标下次发信时悄悄抄录一份副本。" },
                { code: "SPEC_004", name: "羽毛笔",   desc: "一支神奇的羽毛笔，使用后可截获目标发出的下一封信并在发送前修改内容。" },
                { code: "SPEC_005", name: "捕鼠器",   desc: "一个精巧的捕鼠器，激活后将锁定目标指定小时内的行动，使其无法私约、电话或摘心愿。" },
                { code: "SPEC_006", name: "窃听器",   desc: "一枚微型窃听装置，激活后可悄悄截录目标的电话内容——信号有时会有些干扰……" },
                { code: "SPEC_007", name: "截信器",   desc: "一台隐蔽的信号截断仪，激活后可拦截目标发出的短信，但内容偶有失真……" },
                { code: "SPEC_008", name: "回音壁",   desc: "一面奇异的墙壁，贴上后可感知所有投向目标的信件内容——对方收到什么，你便知晓什么。" },
            ];
            let regChanged = false;
            for (const item of specItems) {
                if (!reg[item.code]) { reg[item.code] = { code: item.code, name: item.name, desc: item.desc, type: "preset", attrs: null }; regChanged = true; }
            }
            const currencyNames = new Set(Object.values(reg).filter(r => r.type === "currency").map(r => r.name));
            if (!currencyNames.has("金币"))   { reg["CUR_001"]    = { code: "CUR_001",    name: "金币",   desc: "流通于玩家间的基础货币。",              type: "currency", attrs: null }; regChanged = true; }
            if (!currencyNames.has("银币"))   { reg["CUR_002"]    = { code: "CUR_002",    name: "银币",   desc: "比金币更零碎的辅助货币。",              type: "currency", attrs: null }; regChanged = true; }
            if (!reg["CUR_LETTER"])           { reg["CUR_LETTER"] = { code: "CUR_LETTER", name: "写信币", desc: "通过发送信件获得的货币，可用于各种消费。", type: "currency", attrs: null }; regChanged = true; }
            if (regChanged) mainKvSet("item_registry", reg);

            let scheduleHint = "";
            if (scheduleStart && scheduleEnd) {
                const mm1 = scheduleStart.slice(0,2), dd1 = scheduleStart.slice(2);
                const mm2 = scheduleEnd.slice(0,2),   dd2 = scheduleEnd.slice(2);
                scheduleHint = `\n📅 档期：${parseInt(mm1)}/${parseInt(dd1)} – ${parseInt(mm2)}/${parseInt(dd2)}`;
                if (supplementEnd) {
                    const mms = supplementEnd.slice(0,2), dds = supplementEnd.slice(2);
                    scheduleHint += `（补戏至 ${parseInt(mms)}/${parseInt(dds)}）`;
                }
                scheduleHint += `\n   · 档期前：互动不记录 · 开始日自动 D0`;
                if (supplementEnd) scheduleHint += `\n   · 补戏期：场次记录，弧长不计`;
            }

            seal.replyToSender(ctx, msg,
                `✅ 季度「${seasonName}」已开启（${modeLabel}模式）${scheduleHint}\n\n` +
                `现在可以使用：\n` +
                `• 创建新角色 角色名\n` +
                `• 创建NPC 角色名\n\n` +
                (isReview ? `💡 复盘模式：所有戏和场次均会存档。\n记得所有 NPC 也需要「创建NPC」，否则无法自动复盘。` :
                            `💡 不复盘模式：戏和场次不存档，仅记录玩家数据到超管后台。`)
            );
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建新季度"] = cmd_new_season;

// ========================
// ── 修改档期
// ========================
let cmd_set_schedule = seal.ext.newCmdItemInfo();
cmd_set_schedule.name = "修改档期";
cmd_set_schedule.help = `用法：。修改档期 MMDD-MMDD [补戏MMDD]
同步更新存档服务器和本地缓存的档期设置。

示例：
  修改档期 0528-0601          仅设主档期
  修改档期 0528-0601 0604     主档期 + 补戏截止
  修改档期 清空               清空所有档期限制`;
cmd_set_schedule.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    if (!isArchiveEnabled()) return seal.replyToSender(ctx, msg, "❌ 未启用RP存档传输");

    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);

    if (!arg1 || arg1 === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    let scheduleStart = "", scheduleEnd = "", supplementEnd = "";

    if (arg1 === "清空") {
        // 清空档期
    } else if (/^\d{4}-\d{4}$/.test(arg1)) {
        [scheduleStart, scheduleEnd] = arg1.split("-");
        if (arg2 && /^\d{4}$/.test(arg2)) {
            supplementEnd = arg2;
        } else if (arg2) {
            return seal.replyToSender(ctx, msg, `⚠️ 补戏日期格式错误，应为 MMDD（如 0604）`);
        }
    } else {
        return seal.replyToSender(ctx, msg, `⚠️ 档期格式错误，应为 MMDD-MMDD（如 0528-0601）`);
    }

    (async () => {
        const base  = getArchiveBase();
        const token = getArchiveToken();
        if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址");

        try {
            const resp = await fetch(`${base}/api/update_schedule`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify({ schedule_start: scheduleStart, schedule_end: scheduleEnd, supplement_end: supplementEnd })
            });
            const data = await resp.json();
            if (!data.ok) return seal.replyToSender(ctx, msg, `❌ 更新失败：${data.error || resp.status}`);

            mainStorSet("season_schedule_start", scheduleStart);
            mainStorSet("season_schedule_end",   scheduleEnd);
            mainStorSet("season_supplement_end", supplementEnd);

            if (!scheduleStart) {
                seal.replyToSender(ctx, msg, "✅ 档期已清空，存档不再限制时间范围。");
            } else {
                const fmt = s => `${parseInt(s.slice(0,2))}/${parseInt(s.slice(2))}`;
                let hint = `✅ 档期已更新：${fmt(scheduleStart)} – ${fmt(scheduleEnd)}`;
                if (supplementEnd) hint += `（补戏至 ${fmt(supplementEnd)}）`;
                seal.replyToSender(ctx, msg, hint);
            }
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["修改档期"] = cmd_set_schedule;

// ========================
// ── 结束季度
// ========================
let cmd_end_season = seal.ext.newCmdItemInfo();
cmd_end_season.name = "结束季度";
cmd_end_season.help = "用法：。结束季度\n封存当前季度并获取公开存档链接";
cmd_end_season.solve = (ctx, msg, cmdArgs) => {
    if (!hasActiveSeason()) {
        seal.replyToSender(ctx, msg, "❌ 当前没有活跃季度。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const currentName = getSeasonShowName();

    (async () => {
        const base  = getArchiveBase();
        const token = getArchiveToken();
        if (!base) {
            seal.replyToSender(ctx, msg, "❌ 未配置 RP 存档服务器地址。");
            return;
        }
        try {
            const resp = await fetch(`${base}/api/end_season`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify({})
            });
            const data = await resp.json();
            if (!data.ok) {
                seal.replyToSender(ctx, msg, `❌ 结束季度失败：${data.error || resp.status}`);
                return;
            }
            seal.replyToSender(ctx, msg,
                `✅ 季度「${currentName}」已封存\n` +
                `📎 公开存档：${data.public_url}\n` +
                `─────────────────────\n` +
                `请确认存档内容无误后：\n` +
                `第一步：。清空季度数据\n` +
                `第二步：创建新季度 恋综名 复盘/不复盘 MMDD-MMDD`
            );

            if (mainStorGet("end_season_report_enabled") === "true") {
                try {
                    const reportResp = await fetch(`${base}/api/season_report/${data.show_id}`, {
                        headers: { "X-Archive-Token": token }
                    });
                    const report = await reportResp.json();
                    if (report.ok) {
                        const platform = ctx.platform || "QQ";
                        const privGroups = mainKvGet("a_private_group", {});
                        const playerMap  = privGroups[platform] || {};

                        const fmtPartners = (list) =>
                            list && list.length
                                ? list.map((x, i) => `  ${["🥇","🥈","🥉"][i]} ${x[0]}（${x[1]} 次）`).join("\n")
                                : null;

                        let sentCount = 0;
                        for (const [, entry] of Object.entries(playerMap)) {
                            const roleName = Array.isArray(entry) ? entry[0] : null;
                            const gid      = Array.isArray(entry) ? entry[1] : null;
                            if (!roleName || !gid) continue;

                            const s = report.players[roleName] || {};
                            const lines = [
                                `🎬 「${currentName}」已落幕`,
                                `这是你「${roleName}」的本季互动报告：`,
                                ``,
                                `📅 参与场次：${s.sessions  || 0} 场`,
                                `💬 发送短信：${s.sms_sent  || 0} 条　收到短信：${s.sms_recv  || 0} 条`,
                                `🎁 赠送礼物：${s.gift_sent || 0} 次　收到礼物：${s.gift_recv || 0} 次`,
                            ];
                            const lmS = s.lovemail_sent || 0, lmR = s.lovemail_recv || 0;
                            if (lmS + lmR > 0) lines.push(`💌 心动信件：发 ${lmS} 封　收 ${lmR} 封`);
                            const ltS = s.letter_sent || 0, ltR = s.letter_recv || 0;
                            if (ltS + ltR > 0) lines.push(`✉️ 直接信件：发 ${ltS} 封　收 ${ltR} 封`);

                            const smsSentTo   = fmtPartners(s.top_sms_sent_to);
                            const smsRecvFrom = fmtPartners(s.top_sms_recv_from);
                            const giftSentTo  = fmtPartners(s.top_gift_sent_to);
                            const giftRecvFrom= fmtPartners(s.top_gift_recv_from);
                            if (smsSentTo || smsRecvFrom || giftSentTo || giftRecvFrom) {
                                lines.push(``, `── 你的互动 Top3 ──`);
                                if (smsSentTo)    lines.push(`💬 你发短信最多的：\n${smsSentTo}`);
                                if (smsRecvFrom)  lines.push(`💬 给你发短信最多的：\n${smsRecvFrom}`);
                                if (giftSentTo)   lines.push(`🎁 你送礼最多的：\n${giftSentTo}`);
                                if (giftRecvFrom) lines.push(`🎁 给你送礼最多的：\n${giftRecvFrom}`);
                            }

                            if (s.time_title) {
                                lines.push(
                                    ``,
                                    `⏰ 你最喜欢互动的时间是 ${s.peak_slot}`,
                                    `   专属称号：「${s.time_title}」`,
                                    `   ${s.time_tagline}`
                                );
                            }

                            if (s.best_excerpt && s.best_excerpt.length > 0) {
                                lines.push(``, `── 你本季最精彩的一场戏 ──`);
                                for (const e of s.best_excerpt) {
                                    lines.push(`${e.role}：${e.text}`);
                                }
                                lines.push(`（……）`);
                            }

                            sendTextToGroup(platform, gid, lines.join("\n"));
                            sentCount++;
                        }
                        if (sentCount > 0) {
                            seal.replyToSender(ctx, msg, `📊 已向 ${sentCount} 位玩家的个人群发送了本季互动报告。`);
                        }
                    }
                } catch (reportErr) {
                    console.error("[结束季度] 报告发送失败：", reportErr.message);
                }
            }

            const _ftoggle = mainKvGet("global_feature_toggle", {});
            if (_ftoggle.dlc_auto_day) {
                _ftoggle.dlc_auto_day = false;
                mainKvSet("global_feature_toggle", _ftoggle);
                seal.replyToSender(ctx, msg, "⏹️ 自动天数已自动关闭。");
            }
            if (_ftoggle.enable_lovemail) {
                _ftoggle.enable_lovemail = false;
                mainKvSet("global_feature_toggle", _ftoggle);
                seal.replyToSender(ctx, msg, "💌 心动信已自动关闭。");
            }

        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束季度"] = cmd_end_season;

// ========================
// ── 季末报告开关
// ========================
let cmd_end_report_toggle = seal.ext.newCmdItemInfo();
cmd_end_report_toggle.name = "季末报告";
cmd_end_report_toggle.help = `用法：。季末报告 开启/关闭/状态
控制结束季度时是否自动向每位玩家的个人群发送互动报告。
⚠️ 开启后，请确保执行「结束季度」时 bot 仍在所有玩家的个人群内。`;
cmd_end_report_toggle.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
    const arg = (cmdArgs.getArgN(1) || "").trim();
    if (arg === "开启") {
        mainStorSet("end_season_report_enabled", "true");
        seal.replyToSender(ctx, msg,
            `✅ 季末报告已开启。\n` +
            `⚠️ 提醒：执行「结束季度」时请确保 bot 仍在所有玩家的个人群内，否则无法发送。`
        );
    } else if (arg === "关闭") {
        mainStorSet("end_season_report_enabled", "false");
        seal.replyToSender(ctx, msg, `✅ 季末报告已关闭，结束季度时将不再发送个人报告。`);
    } else {
        const enabled = mainStorGet("end_season_report_enabled") === "true";
        seal.replyToSender(ctx, msg,
            `📊 季末报告当前状态：${enabled ? "✅ 开启" : "❌ 关闭"}\n` +
            `使用「。季末报告 开启」或「。季末报告 关闭」切换。`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["季末报告"] = cmd_end_report_toggle;

// ========================
// 📊 场次状态查看 & 手动调整
// ========================

let cmd_session_status = seal.ext.newCmdItemInfo();
cmd_session_status.name = "场次状态";
cmd_session_status.help = "用法：。场次状态\n管理员查看所有活跃群组当前写帖进度与结戏奖励条件达成情况（合并转发）";
cmd_session_status.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"), seal.ext.newCmdExecuteResult(true);
    if (!msg.groupId) return seal.replyToSender(ctx, msg, "⚠️ 请在群内使用此指令"), seal.ext.newCmdExecuteResult(true);

    const platform = msg.platform;
    const gei      = mainKvGet("group_expire_info", {});
    const ss       = getSessionStats();
    const apg      = mainKvGet("a_private_group", {})[platform] || {};
    const templates = mainKvGet("end_game_bonus_templates", []);
    const tplTypeToStored = { "私约": "私密", "心意": "心愿" };
    const now = Date.now();

    const activeGroups = Object.entries(gei);
    if (!activeGroups.length) return seal.replyToSender(ctx, msg, "📭 当前无活跃群组"), seal.ext.newCmdExecuteResult(true);

    const botUid = ctx.endPoint.userId;
    const nodes = [];
    nodes.push({ type: "node", data: { name: "场次总览", uin: botUid,
        content: `📊 活跃群组共 ${activeGroups.length} 个\n` +
                 `💡 手动修正：。调整场次 群号 角色名 +字数 [+段数]` } });

    function evalCond(op, val, thr) {
        switch (op) {
            case "=":     return val === thr;
            case "!=":    return val !== thr;
            case ">=":    return val >= thr;
            case "<=":    return val <= thr;
            case "range": return val >= thr[0] && val <= thr[1];
        }
        return false;
    }

    for (const [gid, info] of activeGroups) {
        const groupStat  = ss[gid] || {};
        const participants = info.participants || [];
        const subtype    = info.subtype || "";
        const elapsedMin = groupStat._startTime ? Math.floor((now - groupStat._startTime) / 60000) : 0;

        const enabled = templates.filter(t => {
            if (!t.enabled) return false;
            const tType = t.subtype || "通用";
            if (tType === "通用") return true;
            return (tplTypeToStored[tType] || tType) === subtype;
        });

        const playerLines = participants.map(roleName => {
            const uid     = Object.entries(apg).find(([, v]) => v[0] === roleName)?.[0];
            const stat    = uid ? (groupStat[uid] || { replies: 0, words: 0 }) : { replies: 0, words: 0 };
            const replies = stat.replies || 0;
            const words   = stat.words   || 0;
            const avg     = replies > 0 ? Math.floor(words / replies) : 0;

            const getVal = (param) => {
                switch (param) {
                    case "本场个人段数":         return replies;
                    case "本场个人总字数":       return words;
                    case "本场个人平均每段字数": return avg;
                    case "结戏最多耗费时间":     return elapsedMin;
                }
                return 0;
            };

            const rewardLines = [];
            for (const tpl of enabled) {
                for (const group of tpl.groups) {
                    for (const block of group.blocks) {
                        const conds   = block.conditions || [];
                        const rewards = block.rewards    || [];
                        if (!rewards.length) continue;
                        const rewardDesc = rewards.map(r => `${r.target}×${r.amount}`).join("、");
                        const allMet = conds.every(c => evalCond(c.op, getVal(c.param), c.value));
                        const condDesc = conds.map(c => {
                            const val    = getVal(c.param);
                            const met    = evalCond(c.op, val, c.value);
                            const opStr  = { "=": "=", "!=": "≠", ">=": "≥", "<=": "≤", "range": "~" }[c.op] || c.op;
                            const thrStr = Array.isArray(c.value) ? `${c.value[0]}-${c.value[1]}` : c.value;
                            return `${met ? "✅" : "❌"} ${c.param}${opStr}${thrStr}（现${val}）`;
                        }).join("  ");
                        rewardLines.push(`  ${allMet ? "🎁" : "⏳"} ${rewardDesc}\n    ${condDesc}`);
                    }
                }
            }

            const uidNote = uid ? "" : " ⚠️未绑定";
            return `👤 ${roleName}${uidNote}：${replies}段 · ${words}字（均${avg}字/段）` +
                   (rewardLines.length ? "\n" + rewardLines.join("\n") : "");
        });

        const overdue    = now > info.expireTime ? " ⚠️已超时" : "";
        const timeStr    = info.day ? `${info.day} ${info.time || ""}` : "时间未知";
        const header     = `📌 群号：${gid}\n类型：${getCustomTypeLabel(subtype) || '小群'}\n⏰ ${timeStr}${overdue}\n📍 ${info.place || "地点未知"}`;
        const sep        = "\n─────────\n";
        const content  = header + sep + playerLines.join(sep);
        const nodeName = participants.slice(0, 3).join("、") + (participants.length > 3 ? "…" : "");
        nodes.push({ type: "node", data: { name: nodeName || gid, uin: botUid, content } });
    }

    const gidInt   = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const total    = activeGroups.length;
    const batches  = Math.ceil(total / STATS_CHUNK_SIZE);
    const groupNodes = nodes.slice(1);

    for (let b = 0; b < batches; b++) {
        const slice   = groupNodes.slice(b * STATS_CHUNK_SIZE, (b + 1) * STATS_CHUNK_SIZE);
        const header  = { type: "node", data: { name: "场次总览", uin: botUid,
            content: `📊 活跃群组 ${total} 个${batches > 1 ? `（第 ${b + 1}/${batches} 批）` : ""}\n` +
                     `💡 手动修正：。调整场次 群号 角色名 +字数 [+段数]` } };
        ws({ action: "send_group_forward_msg", params: { group_id: gidInt, messages: [header, ...slice] } }, ctx, msg, "");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["场次状态"] = cmd_session_status;

let cmd_adjust_session = seal.ext.newCmdItemInfo();
cmd_adjust_session.name = "调整场次";
cmd_adjust_session.help = `用法：。调整场次 群号 角色名 字数偏移 [段数偏移]
示例：
  。调整场次 12345 张三 +500        ← 加500字
  。调整场次 12345 张三 +500 +2     ← 加500字、加2段（同步更新几v几）
  。调整场次 12345 张三 -100 -1     ← 减100字、减1段
偏移量带+/-均可，结果不会低于0。`;
cmd_adjust_session.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"), seal.ext.newCmdExecuteResult(true);

    const platform    = msg.platform;
    const gid         = (cmdArgs.getArgN(1) || "").trim();
    const roleName    = (cmdArgs.getArgN(2) || "").trim();
    const rawWords    = (cmdArgs.getArgN(3) || "").trim();
    const rawReplies  = (cmdArgs.getArgN(4) || "").trim();

    if (!gid || !roleName || !rawWords)
        return seal.replyToSender(ctx, msg, "⚠️ 用法：。调整场次 群号 角色名 字数偏移 [段数偏移]"), seal.ext.newCmdExecuteResult(true);

    const deltaWords   = parseInt(rawWords, 10);
    const deltaReplies = rawReplies ? parseInt(rawReplies, 10) : 0;
    if (isNaN(deltaWords))
        return seal.replyToSender(ctx, msg, "⚠️ 字数偏移格式错误，示例：+500 或 -100"), seal.ext.newCmdExecuteResult(true);
    if (rawReplies && isNaN(deltaReplies))
        return seal.replyToSender(ctx, msg, "⚠️ 段数偏移格式错误，示例：+2 或 -1"), seal.ext.newCmdExecuteResult(true);

    const apg = mainKvGet("a_private_group", {})[platform] || {};
    const uid = Object.entries(apg).find(([, v]) => v[0] === roleName)?.[0];
    if (!uid)
        return seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${roleName}」`), seal.ext.newCmdExecuteResult(true);

    const ss = getSessionStats();
    if (!ss[gid])
        return seal.replyToSender(ctx, msg, `⚠️ 找不到群 ${gid} 的场次记录\n提示：可用「场次状态」查看所有活跃群号`), seal.ext.newCmdExecuteResult(true);
    if (!ss[gid][uid]) ss[gid][uid] = { replies: 0, words: 0 };

    const before = { replies: ss[gid][uid].replies || 0, words: ss[gid][uid].words || 0 };
    ss[gid][uid].words   = Math.max(0, before.words   + deltaWords);
    ss[gid][uid].replies = Math.max(0, before.replies + deltaReplies);
    saveSessionStats(ss);

    let progressNote = "";
    if (deltaReplies !== 0) {
        const prog = mainKvGet("group_write_progress", {});
        if (!prog[gid]) prog[gid] = {};
        prog[gid][uid] = Math.max(0, (prog[gid][uid] || 0) + deltaReplies);
        mainKvSet("group_write_progress", prog);
        progressNote = `\n  ↳ 几v几 进度已同步：${prog[gid][uid]} 段`;
    }

    const sign = n => n >= 0 ? `+${n}` : `${n}`;
    const after = ss[gid][uid];
    seal.replyToSender(ctx, msg,
        `✅ 已调整【${roleName}】在群 ${gid} 的场次数据：\n` +
        `  字数：${before.words} → ${after.words}（${sign(deltaWords)}）\n` +
        `  段数：${before.replies} → ${after.replies}（${sign(deltaReplies)}）` +
        progressNote
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["调整场次"] = cmd_adjust_session;

// ========================
// ── 补发结戏奖励
// ========================
let cmd_reissue_bonus = seal.ext.newCmdItemInfo();
cmd_reissue_bonus.name = "补发奖励";
cmd_reissue_bonus.help = `【管理员】对已结束场次手动补发结戏奖励
用法（多行消息）：
。补发奖励 模版名
角色名 段数 字数 [耗时分钟]
角色名 段数 字数 [耗时分钟]
...

示例：
。补发奖励 标准奖励
张三 8 1200 45
李四 5 900 45

说明：
• 段数/字数/耗时 用于匹配模版条件，需手动填入当时的实际数据
• 耗时分钟可省略，省略时视为 0（对"结戏最多耗费时间 >=" 条件不利，请酌情填写）
• 奖励直接写入背包/属性，并向玩家个人群发通知`;
cmd_reissue_bonus.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const tplName = cmdArgs.getArgN(1);
    if (!tplName) {
        seal.replyToSender(ctx, msg, "❌ 请指定模版名，格式见「。补发奖励」帮助");
        return seal.ext.newCmdExecuteResult(true);
    }

    const templates = mainKvGet("end_game_bonus_templates", []);
    const tpl = templates.find(t => t.name === tplName);
    if (!tpl) {
        seal.replyToSender(ctx, msg, `❌ 模版「${tplName}」不存在，用「结戏加成 模版列表」查看`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!tpl.enabled) {
        seal.replyToSender(ctx, msg, `⚠️ 模版「${tplName}」当前已关闭，仍继续补发`);
    }

    const allLines = (msg.message || "").split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const playerLines = allLines.slice(1);

    if (!playerLines.length) {
        seal.replyToSender(ctx, msg, "❌ 请在第二行起填写角色名和数据，每行一个");
        return seal.ext.newCmdExecuteResult(true);
    }

    const reg = mainKvGet("item_registry", {});
    const currencyByName = {};
    Object.values(reg).forEach(r => { if (r.type === "currency") currencyByName[r.name] = r.code; });

    const apg = mainKvGet("a_private_group", {});

    function evaluateCondition(op, statVal, value) {
        switch (op) {
            case "=":     return statVal === value;
            case "!=":    return statVal !== value;
            case ">=":    return statVal >= value;
            case "<=":    return statVal <= value;
            case "range": return statVal >= value[0] && statVal <= value[1];
        }
        return false;
    }

    function drawFromPool(pool) {
        const totalWeight = pool.items.reduce((s, it) => s + it.weight, 0);
        if (totalWeight <= 0) return null;
        let rand = Math.random() * totalWeight;
        for (const item of pool.items) {
            rand -= item.weight;
            if (rand <= 0) return item;
        }
        return pool.items[pool.items.length - 1];
    }

    function applyOneReward(playerUid, rewardItem, failLines) {
        const { target, targetType, amount } = rewardItem;
        if (targetType === "currency" || targetType === "item") {
            let code = targetType === "currency" ? (currencyByName[target] || null) : null;
            if (!code) {
                const upper = target.toUpperCase();
                if (reg[upper]) {
                    code = upper;
                } else {
                    const found = Object.values(reg).find(r => r.name === target);
                    if (found) code = found.code;
                }
            }
            if (!code) {
                failLines.push(`⚠️ 「${target}」未在注册表中找到，跳过`);
                return null;
            }
            const ok = addToInv_local(`${platform}:${playerUid}`, code, amount);
            if (!ok) {
                failLines.push(`⚠️ 「${target}」发放失败（代码 ${code} 不在注册表），跳过`);
                return null;
            }
            return `${target}×${amount}`;
        } else {
            const profileKey = `${platform}:${playerUid}`;
            const profiles = mainKvGet("sys_char_profiles", {});
            if (!profiles[profileKey]) profiles[profileKey] = {};
            const cur = parseInt(profiles[profileKey][target] || "0");
            profiles[profileKey][target] = String(cur + amount);
            mainKvSet("sys_char_profiles", profiles);
            return `${target}+${amount}`;
        }
    }

    const report = [];
    const errors = [];

    for (const line of playerLines) {
        const parts = line.split(/\s+/);
        if (parts.length < 3) { errors.push(`格式错误（需要：角色名 段数 字数）：${line}`); continue; }
        const roleName = parts[0];
        const replies = parseInt(parts[1]);
        const words = parseInt(parts[2]);
        const elapsedMinutes = parts[3] ? parseInt(parts[3]) : 0;
        if (isNaN(replies) || isNaN(words)) { errors.push(`段数/字数不是数字：${line}`); continue; }

        const uid = getUidByRoleName(platform, roleName);
        if (!uid) { errors.push(`⚠️ 找不到角色「${roleName}」对应的 UID，请确认角色已注册`); continue; }

        const avgWords = replies > 0 ? Math.floor(words / replies) : 0;
        const getStatVal = (param) => {
            switch (param) {
                case "本场个人段数":         return replies;
                case "本场个人总字数":       return words;
                case "本场个人平均每段字数": return avgWords;
                case "结戏最多耗费时间":     return elapsedMinutes;
            }
            return 0;
        };

        const fixedLines = [];
        const poolLines = [];
        const failLines = [];

        function processR(r) {
            const prob = (r.prob == null) ? 100 : r.prob;
            if (prob < 100 && Math.random() * 100 >= prob) return;
            if (!r.type || r.type === "fixed") {
                const res = applyOneReward(uid, r, failLines);
                if (res) fixedLines.push(res);
            } else if (r.type === "pool" && r.items.length) {
                const drawn = drawFromPool(r);
                if (drawn) {
                    const res = applyOneReward(uid, drawn, failLines);
                    if (res) {
                        const total = r.items.reduce((s, it) => s + it.weight, 0);
                        const pct = total > 0 ? Math.round(drawn.weight / total * 100) : 0;
                        poolLines.push(`${res}（${pct}%）`);
                    }
                }
            }
            // location_draw 在补发场景下跳过
        }

        for (const group of tpl.groups) {
            if (group.op === "and") {
                for (const block of group.blocks) {
                    const allMet = (block.conditions || []).every(c =>
                        evaluateCondition(c.op, getStatVal(c.param), c.value)
                    );
                    if (!allMet) continue;
                    for (const r of (block.rewards || [])) processR(r);
                }
            } else if (group.op === "or") {
                for (const block of group.blocks) {
                    const allMet = (block.conditions || []).every(c =>
                        evaluateCondition(c.op, getStatVal(c.param), c.value)
                    );
                    if (!allMet) continue;
                    for (const r of (block.rewards || [])) processR(r);
                    break;
                }
            }
        }

        const allLines2 = [...fixedLines, ...poolLines];
        const lineDesc = allLines2.length ? allLines2.join("、") : "（无条件命中，未发放）";
        const failDesc = failLines.length ? `\n  ${failLines.join("\n  ")}` : "";
        report.push(`【${roleName}】${lineDesc}${failDesc}`);

        const roleEntry = apg[platform]?.[uid];
        if (roleEntry && allLines2.length) {
            const personalGroupId = roleEntry[1];
            const notifyMsg = seal.newMessage();
            notifyMsg.messageType = "group";
            notifyMsg.groupId = `${platform}-Group:${personalGroupId}`;
            const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
            const fixedText = fixedLines.join("、");
            const poolText = poolLines.length ? `\n🎲 概率奖励抽中：${poolLines.join("、")}` : "";
            seal.replyToSender(notifyCtx, notifyMsg,
                `[CQ:at,qq=${uid}]\n🎁 结戏加成补发：${fixedText}${poolText}\n💡 可使用「背包」查看道具与货币，「角色卡」查看属性变更。`
            );
        }
    }

    if (errors.length) {
        seal.replyToSender(ctx, msg, `⚠️ 以下行解析失败：\n${errors.join("\n")}`);
    }
    if (report.length) {
        seal.replyToSender(ctx, msg, `🎁 补发结戏奖励（模版：${tplName}）：\n${report.join("\n")}`);
    } else if (!errors.length) {
        seal.replyToSender(ctx, msg, "📭 无奖励被发放（所有条件均未命中）");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["补发奖励"] = cmd_reissue_bonus;

// ========================
// ── 查奖励情况
// ========================
let cmd_check_rewards = seal.ext.newCmdItemInfo();
cmd_check_rewards.name = "查奖励情况";
cmd_check_rewards.help = `【管理员】从 rp_archive 拉取最近已结束场次，预览各玩家按当前模版应得的奖励。
用法：。查奖励情况 [条数]
  条数默认 5，最多 20。
  不实际发放任何奖励，仅供核查后手动「。补发奖励」。`;
cmd_check_rewards.solve = (ctx, msg, cmdArgs) => {
    if (!isArchiveEnabled()) {
        seal.replyToSender(ctx, msg, "❌ 未启用 RP 存档传输，无法拉取历史场次");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const limitArg = parseInt(cmdArgs.getArgN(1) || "5");
    const limit = isNaN(limitArg) ? 5 : Math.min(Math.max(limitArg, 1), 20);

    const base  = getArchiveBase();
    const token = getArchiveToken();

    const templates = mainKvGet("end_game_bonus_templates", []);
    const enabledTpls = templates.filter(t => t.enabled);

    const platform = msg.platform;

    const tplTypeToStored = { "私约": "私密", "心意": "心愿" };
    function isTplMatch(tpl, subtype) {
        const tplType = tpl.subtype || "通用";
        if (tplType === "通用") return true;
        const resolved = tplTypeToStored[tplType] || tplType;
        return resolved === subtype;
    }
    function evalCond(op, val, thr) {
        switch (op) {
            case "=":     return val === thr;
            case "!=":    return val !== thr;
            case ">=":    return val >= thr;
            case "<=":    return val <= thr;
            case "range": return val >= thr[0] && val <= thr[1];
        }
        return false;
    }

    function predictRewards(roleName, stat, subtype, elapsedMin) {
        const replies  = stat.replies || 0;
        const words    = stat.words   || 0;
        const avgWords = replies > 0 ? Math.floor(words / replies) : 0;

        const getVal = (param) => {
            switch (param) {
                case "本场个人段数":         return replies;
                case "本场个人总字数":       return words;
                case "本场个人平均每段字数": return avgWords;
                case "结戏最多耗费时间":     return elapsedMin;
            }
            return 0;
        };

        const matched = [];
        const missed  = [];

        for (const tpl of enabledTpls) {
            if (!isTplMatch(tpl, subtype)) continue;
            for (const group of tpl.groups) {
                if (group.op === "and") {
                    for (const block of group.blocks) {
                        const rewards = block.rewards || [];
                        if (!rewards.length) continue;
                        const conds = block.conditions || [];
                        const results = conds.map(c => {
                            const val = getVal(c.param);
                            const met = evalCond(c.op, val, c.value);
                            const thr = Array.isArray(c.value) ? `${c.value[0]}-${c.value[1]}` : c.value;
                            return { met, desc: `${c.param}${c.op}${thr}（现${val}）` };
                        });
                        const allMet = results.every(r => r.met);
                        const rewardDesc = rewards.map(r => {
                            if (!r.type || r.type === "fixed") return `${r.target}×${r.amount}`;
                            if (r.type === "pool") {
                                const total = r.items.reduce((s, it) => s + it.weight, 0);
                                return "概率[" + r.items.map(it =>
                                    `${it.target}×${it.amount}(${total>0?Math.round(it.weight/total*100):0}%)`
                                ).join("/") + "]";
                            }
                            if (r.type === "location_draw") return `地点池抽取×${r.amount}`;
                            return r.target;
                        }).join("、");
                        if (allMet) {
                            matched.push(`✅ ${rewardDesc}【${tpl.name}】`);
                        } else {
                            const failDesc = results.filter(r => !r.met).map(r => r.desc).join(" ");
                            missed.push(`❌ ${rewardDesc}（未满足：${failDesc}）【${tpl.name}】`);
                        }
                    }
                } else if (group.op === "or") {
                    let anyHit = false;
                    for (const block of group.blocks) {
                        const conds = block.conditions || [];
                        const allMet = conds.every(c => evalCond(c.op, getVal(c.param), c.value));
                        if (!allMet) continue;
                        const rewards = block.rewards || [];
                        const rewardDesc = rewards.map(r => {
                            if (!r.type || r.type === "fixed") return `${r.target}×${r.amount}`;
                            if (r.type === "pool") {
                                const total = r.items.reduce((s, it) => s + it.weight, 0);
                                return "概率[" + r.items.map(it =>
                                    `${it.target}×${it.amount}(${total>0?Math.round(it.weight/total*100):0}%)`
                                ).join("/") + "]";
                            }
                            if (r.type === "location_draw") return `地点池抽取×${r.amount}`;
                            return r.target;
                        }).join("、");
                        matched.push(`✅ ${rewardDesc}【${tpl.name}】`);
                        anyHit = true;
                        break;
                    }
                    if (!anyHit) {
                        missed.push(`❌ or组无命中【${tpl.name}】`);
                    }
                }
            }
        }
        return { matched, missed, replies, words, avgWords };
    }

    (async () => {
        try {
            const resp = await fetch(`${base}/api/recent_sessions?limit=${limit}`, {
                headers: { "X-Archive-Token": token }
            });
            if (!resp.ok) {
                seal.replyToSender(ctx, msg, `❌ 拉取存档失败（HTTP ${resp.status}）`);
                return;
            }
            const data = await resp.json();
            if (!data.ok || !data.sessions) {
                seal.replyToSender(ctx, msg, "❌ 存档返回格式异常");
                return;
            }
            if (!data.sessions.length) {
                seal.replyToSender(ctx, msg, "📭 存档中无已结束场次");
                return;
            }

            if (!enabledTpls.length) {
                seal.replyToSender(ctx, msg, "⚠️ 当前无已启用的结戏加成模版，将显示场次数据但无法预测奖励");
            }

            const botUid = ctx.endPoint.userId;
            const gidInt = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
            const nodes  = [];

            nodes.push({ type: "node", data: { name: "奖励情况总览", uin: botUid,
                content: `📋 最近 ${data.sessions.length} 场已结束场次奖励预览\n` +
                         `当前启用模版：${enabledTpls.length ? enabledTpls.map(t=>t.name).join("、") : "（无）"}\n` +
                         `✅ = 条件命中应发放　❌ = 条件未满足\n` +
                         `如需补发：。补发奖励 模版名\n角色名 段数 字数 [耗时分钟]` } });

            for (const session of data.sessions) {
                let stats = {};
                let participants = [];
                try {
                    stats = JSON.parse(session.stats || "{}");
                    participants = JSON.parse(session.participants || "[]");
                } catch (e) { /* skip */ }

                const elapsedMin = (session.start_ts && session.end_ts)
                    ? Math.floor((session.end_ts - session.start_ts) / 60000)
                    : 0;

                const subtype = (session.subtype || "").replace(/\|补戏$/, "").trim();
                const header  = [
                    `📌 ${session.game_day || "日期未知"} ${session.game_time || ""}`,
                    `📍 ${session.place || "地点未知"}　类型：${subtype || "通用"}`,
                    `群号：${session.group_id}　耗时约 ${elapsedMin} 分钟`,
                ].join("\n");

                const playerLines = [];
                for (const roleName of participants) {
                    const stat = stats[roleName] || { replies: 0, words: 0 };
                    const { matched, missed, replies, words, avgWords } = predictRewards(roleName, stat, subtype, elapsedMin);
                    const statLine = `${replies}段·${words}字（均${avgWords}字/段）`;
                    const uid = getUidByRoleName(platform, roleName);
                    const uidNote = uid ? "" : " ⚠️未绑定";
                    const lines = [`👤 ${roleName}${uidNote}　${statLine}`];
                    if (!enabledTpls.length) {
                        lines.push("  （无启用模版）");
                    } else if (!matched.length && !missed.length) {
                        lines.push("  无匹配模版");
                    } else {
                        matched.forEach(l => lines.push("  " + l));
                        missed.forEach(l  => lines.push("  " + l));
                    }
                    playerLines.push(lines.join("\n"));
                }

                const content = header + "\n─────────\n" + (playerLines.length ? playerLines.join("\n─────────\n") : "（无参与者数据）");
                const nodeName = participants.slice(0, 3).join("、") + (participants.length > 3 ? "…" : "");
                nodes.push({ type: "node", data: { name: nodeName || session.group_id, uin: botUid, content } });
            }

            ws({ action: "send_group_forward_msg", params: { group_id: gidInt, messages: nodes } }, ctx, msg, "");
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 请求异常：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查奖励情况"] = cmd_check_rewards;

// ========================
// 修改/拒绝时间线（无前缀，通过 onNotCommandReceived 处理）
// ========================

ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();

    const makeFakeCmdArgs = (parts) => ({
        args: ['', ...parts],
        getArgN: (n) => parts[n - 1] || "",
    });

    if (raw.startsWith("修改时间线")) {
        const rest = raw.slice(5).trim();
        const parts = rest ? rest.split(/\s+/) : [];
        return cmd_update_schedule.solve(ctx, msg, makeFakeCmdArgs(parts));
    }

    if (raw.startsWith("拒绝时间线")) {
        const rest = raw.slice(5).trim();
        return cmd_abolish_schedule.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }
};
