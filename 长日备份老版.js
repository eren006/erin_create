// ==UserScript==
// @name         长日将尽系统
// @author       长日将尽
// @version      1.1.0
// @description  无
// @timestamp    1742205760
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find("changriV1")
if (!ext) {
    ext = seal.ext.new("changriV1", "长日将尽", "1.1.0");
    // 注册扩展
    seal.ext.register(ext);
    ext.autoActive = true;
}
ext.autoActive = true;

seal.ext.registerStringConfig(ext, "ws地址", "ws://localhost:3001");
    seal.ext.registerStringConfig(ext, "ws Access token", '', "输入与上方端口对应的token，没有则留空");
    seal.ext.registerStringConfig(ext, "群管插件使用需要满足的条件", '1', "使用豹语表达式，例如：$t群号_RAW=='2001'，1为所有群可用");
    seal.ext.registerBoolConfig(ext, "开启现实时段校验", false, "是否限制玩家只能发起与当前现实时间对应的剧情时段邀约");
    //这些要删掉
    seal.ext.registerIntConfig(ext, "mailCooldown", 60, "寄信冷却时间（分钟）", "寄信行为之间的最小间隔时间");
    seal.ext.registerIntConfig(ext, "giftCooldown", 30, "礼物赠送冷却时间（分钟）", "两次赠送礼物之间的最小间隔时间");
    seal.ext.registerIntConfig(ext, "giftDailyLimit", 100, "每日礼物额度上限", "每天可赠送礼物的最大数量");
    seal.ext.registerIntConfig(ext, "secretLetterCooldown", 2, "匿名信冷却时间（分钟）", "发送匿名信的最小间隔时间");
    seal.ext.registerIntConfig(ext, "secretLetterDailyLimit", 30, "匿名信每日次数上限", "每天可发送匿名信的最大数量");
    seal.ext.registerIntConfig(ext, "secretLetterRevealChance", 15, "匿名信暴露身份概率（0-100）", "发送匿名信时暴露身份的概率，设置为0则不暴露");
    seal.ext.registerIntConfig(ext, "secretLetterPublicChance", 50, "匿名信公开概率（0-100）", "匿名信被公开到公告群的几率，设置为0则不公开");
    //这些要删掉
    seal.ext.registerIntConfig(ext, "giftMode", 0, "送礼模式：0-自定义+预设，1-只允许预设，2-只允许自定义", "控制送礼功能的模式");
    let whiteList = 0;
function ws(postData, ctx, msg, successreply) {
    const wsUrl = seal.ext.getStringConfig(ext, "ws地址");
    const token = seal.ext.getStringConfig(ext, "ws Access token");
    let connectionUrl = wsUrl;

    if (token) {
        const separator = connectionUrl.includes('?') ? '&' : '?';
        connectionUrl += `${separator}access_token=${encodeURIComponent(token)}`;
    }

    const currentEcho = postData.action + "_" + Date.now();
    postData.echo = currentEcho;

    if (postData.params) {
        if (postData.params.message_id) postData.params.message_id = parseInt(postData.params.message_id);
        if (postData.params.group_id) postData.params.group_id = parseInt(postData.params.group_id);
    }

    const ws = new WebSocket(connectionUrl);
    let isClosed = false;

    const closeSafe = (reason) => {
        if (!isClosed) {
            isClosed = true;
            clearTimeout(timeoutId);
            // 只有在连接还在开启状态时才去关闭
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close(1000, reason);
            }
        }
    };

    const timeoutId = setTimeout(() => {
        if (!isClosed) {
            console.log(`[WS] 请求超时: ${postData.action}`);
            closeSafe("TIMEOUT");
        }
    }, 6000);

    ws.onopen = function() {
        try {
            const sendStr = JSON.stringify(postData);
            ws.send(sendStr);
            // 只有调试时才开启此行，平时可以注释掉
            // console.log('WS发送数据:', sendStr); 
        } catch (e) {
            console.error('发送失败, JSON序列化错误:', e);
            closeSafe("SERIALIZE_ERROR");
        }
    };

    ws.onmessage = function(event) {
        try {
            const response = JSON.parse(event.data);
            if (response.post_type === "meta_event") return;
            if (response.echo !== currentEcho) return;

            if (response.status === 'ok' || response.retcode === 0) {
                if (postData.action === "get_group_member_list") {
                    handleMemberListResponse(ctx, msg, response.data);
                    closeSafe("LIST_SUCCESS");
                } else if (postData.action === "get_msg") {
                    handleForwardAction(ctx, msg, response.data, ws);
                } else {
                    if (successreply) seal.replyToSender(ctx, msg, successreply);
                    closeSafe("ACTION_SUCCESS");
                }
            } else {
                console.error(`[WS] 服务端返回错误: ${JSON.stringify(response)}`);
                closeSafe("ACTION_FAILED");
            }
        } catch (e) {
            console.error('WS收包解析异常:', e);
        }
    };

    // --- 核心修复：更温和的错误处理 ---
    ws.onerror = function(e) {
        // 如果连接已经关闭或者正在关闭，不打印异常信息
        if (isClosed || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED) {
            return;
        }
        console.error('[WS] 运行异常，请检查地址、Token或OneBot连接状态');
    };

    ws.onclose = function(event) {
        isClosed = true;
        // 只有当关闭代码不是 1000 (正常关闭) 且不是主动触发时才记录日志
        if (event.code !== 1000 && event.reason !== "ACTION_SUCCESS") {
            console.log(`[WS] 连接已关闭 (代码: ${event.code}, 原因: ${event.reason})`);
        }
    };

    return seal.ext.newCmdExecuteResult(true);
}

function handleForwardAction(ctx, msg, data, currentWs) {
    // 1. 群号处理 (去掉平台前缀，转为纯数字)
    let rawGid = ext.storageGet("temp_target_gid") || "";
    const gid = parseInt(rawGid.replace(/[^\d]/g, ""), 10);
    const taskType = ext.storageGet("temp_task_type") || "forward";
    
    if (isNaN(gid) || !data || !data.message) {
        if (currentWs) currentWs.close(1000, "FAIL_DATA");
        return;
    }

    const originalContent = typeof data.message === 'string' ? data.message : JSON.stringify(data.message);

    if (taskType === "song") {
        const dgr = ext.storageGet("temp_song_dgr") || "未知";
        const ly = ext.storageGet("temp_song_ly") || "无";

        // 识别 ID：neteaseIdMatch 匹配数字，qqIdMatch 匹配字母数字混合
        const neteaseIdMatch = originalContent.match(/id[=:]\s*(\d+)/);
        const qqIdMatch = originalContent.match(/["'](?:mid|songmid)["']\s*[:=]\s*["'](\w+)["']/) || 
                          originalContent.match(/mid=(\w+)/) ||
                          originalContent.match(/songid[=:]\s*(\d+)/);

        let songId = "";
        let musicType = "163";

        if (qqIdMatch) {
            songId = qqIdMatch[1];
            musicType = "qq";
        } else if (neteaseIdMatch) {
            songId = neteaseIdMatch[1];
            musicType = "163";
        }

        if (songId) {
            // A. 发送文案回执
            currentWs.send(JSON.stringify({
                "action": "send_group_msg",
                "params": { 
                    "group_id": gid, 
                    "message": `🎵 【点歌台】\n点歌人：${dgr}\n留言：${ly}` 
                }
            }));

            // B. 发送音乐卡片 (直接发送，不走 HTTP)
            setTimeout(() => {
                if (currentWs.readyState === 1) {
                    currentWs.send(JSON.stringify({
                        "action": "send_group_msg",
                        "params": {
                            "group_id": gid,
                            "message": [
                                {
                                    "type": "music",
                                    "data": {
                                        "type": musicType,
                                        "id": songId
                                    }
                                }
                            ]
                        }
                    }));
                    seal.replyToSender(ctx, msg, "✅ 点歌已同步至点歌群。");
                }
            }, 1000);
        } else {
            seal.replyToSender(ctx, msg, "❌ 识别失败，请引用音乐分享卡片。");
        }
    } else {
        // 复盘逻辑：保持双消息平铺
        const sourceName = ext.storageGet("temp_source_group_name") || "未知群聊";
        currentWs.send(JSON.stringify({
            "action": "send_group_msg",
            "params": { "group_id": gid, "message": `📢 复盘来源：【${sourceName}】` }
        }));
        setTimeout(() => {
            if (currentWs.readyState === 1) {
                currentWs.send(JSON.stringify({
                    "action": "send_group_msg",
                    "params": { "group_id": gid, "message": data.message }
                }));
            }
        }, 500);
    }

    // 延迟关闭连接
    setTimeout(() => { if (currentWs.readyState === 1) currentWs.close(1000, "FINISH"); }, 2000);
}
/**
 * 内部辅助：处理群成员数据解析
 */
/**
 * 内部辅助：处理群成员数据解析 (适配审查版)
 */
function handleMemberListResponse(ctx, msg, data) {
    let members = [];
    if (Array.isArray(data)) {
        members = data;
    } else if (data && typeof data === 'object') {
        members = data.members || data.list || Object.values(data);
    }

    // --- 核心修改：检查是否处于“审查模式” ---
    const auditOwner = ext.storageGet("temp_audit_owner");
    if (auditOwner) {
        performAuditLogic(ctx, msg, auditOwner, members);
        ext.storageSet("temp_audit_owner", ""); // 清除标志位
        return;
    }

    // 原有的普通展示逻辑保持不变
    if (members.length > 0) {
        let responseText = `👥 群成员列表（共${members.length}人）:\n\n`;
        members.slice(0, 30).forEach((member, index) => {
            const user_id = member.user_id || member.qq || '未知';
            const nickname = member.nickname || member.name || '未知';
            const card = member.card || member.group_card || '';
            const role = member.role === 'owner' ? '👑' : (member.role === 'admin' ? '⭐' : '👤');
            let cardDisplay = (card && card !== nickname) ? ` [${card}]` : '';
            responseText += `${index + 1}. ${role} ${nickname}${cardDisplay} (${user_id})\n`;
        });
        if (members.length > 30) responseText += `\n...仅展示前30位成员`;
        seal.replyToSender(ctx, msg, responseText);
    } else {
        seal.replyToSender(ctx, msg, "未能解析到有效的群成员数据。");
    }
}

/**
 * 核心对比逻辑：执行结果分析
 */
function performAuditLogic(ctx, msg, ownerName, members) {
    const platform = msg.platform;
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");
    
    const playerMap = {}; 
    const npcUIDs = {};   
    const memberUIDs = members.map(m => (m.user_id || m.qq).toString());

    // 建立映射
    Object.entries(a_private_group[platform] || {}).forEach(([name, data]) => {
        if (npcList.includes(name)) npcUIDs[name] = data[0]; 
        else playerMap[data[0]] = name; 
    });

    const ownerData = a_private_group[platform][ownerName];
    if (!ownerData) return;
    const ownerUID = ownerData[0];
    const gid = ownerData[1];

    // 1. 检查缺 NPC
    let missing = npcList.filter(n => !memberUIDs.includes(npcUIDs[n]));
    // 2. 检查多玩家
    let overlaps = memberUIDs.filter(id => playerMap[id] && id !== ownerUID).map(id => playerMap[id]);

    // 只有异常才回复
    if (missing.length > 0 || overlaps.length > 0) {
        let res = `📌 群「${ownerName}」(${gid})：\n`;
        if (missing.length > 0) res += `❌ 缺NPC：${missing.join('/')}\n`;
        if (overlaps.length > 0) res += `⚠️ 重合：${overlaps.join('/')}`;
        seal.replyToSender(ctx, msg, res.trim());
    }
}

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 10);
}

function generateGroupRef() {
    return "grp_" + Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
  }
  

  function isValidTimeFormat(timeStr) {
    const regex = /^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/;
    const match = timeStr.match(regex);
    if (!match) return false;
  
    const [, h1, m1, h2, m2] = match.map(Number);
    if (
      h1 < 0 || h1 > 23 || m1 < 0 || m1 > 59 ||
      h2 < 0 || h2 > 23 || m2 < 0 || m2 > 59
    ) return false;
  
    const start = h1 * 60 + m1;
    const end = h2 * 60 + m2;
  
    // ❌ 禁止跨日
    if (end <= start) return false;
  
    return true;
  }
  
function parseTimeRange(timeStr) {
  const [start, end] = timeStr.split("-");
  return [parseInt(start.replace(":", "")), parseInt(end.replace(":", ""))];
}
function timeConflict(newDay, newTime, existingDay, existingTime) {
  if (newDay !== existingDay) return false;
  const [newStart, newEnd] = parseTimeRange(newTime);
  const [existStart, existEnd] = parseTimeRange(existingTime);
  return !(newEnd <= existStart || newStart >= existEnd);
}

function isUserAdmin(ctx, msg) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_adminList = JSON.parse(ext.storageGet("a_adminList") || "{}");
    return ctx.privilegeLevel === 100 || (a_adminList[platform] && a_adminList[platform].includes(uid));
  }

  function timeOverlap(t1, t2) {
    const [start1, end1] = parseStartEnd(t1);
    const [start2, end2] = parseStartEnd(t2);
    return !(end1 <= start2 || end2 <= start1); // 包含、重叠、边界接触全都算冲突
  }
  

  function normalizeTimeString(s) {
    return s.replace(/\s+/g, "").replace("–", "-").replace("－", "-");
  }
  
  function parseStartEnd(t) {
    t = normalizeTimeString(t); // ✅ 标准化时间段格式
    const [s, e] = t.split("-");
    const toMin = t => {
      const [h, m] = t.split(":").map(Number);
      return h * 60 + m;
    };
    return [toMin(s), toMin(e)];
  }


// 注册公告触发频率（例如：每5次发一次）
seal.ext.registerIntConfig(ext, "announceFrequency", 5, "公告触发频率", "每发生多少次该类型的互动后，向管理员群发送一次记录公告");
function recordMeetingAndAnnounce(subtype, platform, ctx, endPoint) {
    const subtypeKeyMap = {
        "电话": "call",
        "私密": "private",
        "剧情信件": "letter",
        "寄信": "chaosletter",
        "礼物": "gift",
        "匿名信": "secretletter",
        "心愿": "wish",
        "官约": "official"
    };
    const keyType = subtypeKeyMap[subtype] || "unknown";
    const storageKey = `a_meetingCount_${keyType}`;

    let count = parseInt(ext.storageGet(storageKey) || "0");
    count++;
    ext.storageSet(storageKey, count.toString());

    const groupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");

    if (groupId) {
        const msgDivineLog = seal.newMessage();
        msgDivineLog.messageType = "group";
        msgDivineLog.groupId = `${platform}-Group:${groupId}`;
        msgDivineLog.sender = {};
        const ctxDivineLog = seal.createTempCtx(endPoint, msgDivineLog);

        const getStageText = (subtype, count) => {
            // --- 核心修改部分：从配置项获取频率 ---
            // 获取用户在插件设置里填写的数字，默认为 5
            const frequency = seal.ext.getIntConfig(ext, "announceFrequency"); 
            
            // 检查是否应该触发公告：使用动态频率
            let shouldAnnounce = (count % frequency === 0);
            
            if (!shouldAnnounce) return null;

            const getDirectRecord = (type, count, emoji) => {
                return `${emoji} 【第${count}次${type}记录】`;
            };

            // ... 以下逻辑保持不变 ...
            if (subtype === "电话") return getDirectRecord("电话", count, "☎️");
            if (subtype === "私密") return getDirectRecord("私密约会", count, "💫");
            if (subtype === "剧情信件" || subtype === "寄信") return getDirectRecord("寄信", count, "✉️");
            if (subtype === "礼物") return getDirectRecord("礼物赠送", count, "🎁");
            if (subtype === "匿名信") return getDirectRecord("匿名信", count, "💌");
            if (subtype === "心愿") return getDirectRecord("心愿", count, "🌠");
            if (subtype === "官约") return getDirectRecord("官方约会", count, "🏢");

            return getDirectRecord("互动", count, "📝");
        };

        const broadcastText = getStageText(subtype, count);
        if (broadcastText) {
            seal.replyToSender(ctxDivineLog, msgDivineLog, broadcastText);
        }
    }
}

// 统一的接受请求冲突检查函数
function checkAcceptanceConflicts(platform, userId, roleName, day, time, excludeMultiGroupRef = null, excludeAppointmentId = null) {
  const results = [];
  
  // 1. 检查锁定冲突
  const a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
  const locked = a_lockedSlots[`${platform}:${userId}`]?.[day] || [];
  for (let slot of locked) {
    if (timeOverlap(slot, time)) {
      results.push(`在 ${day} ${slot} 被管理员锁定`);
      break;
    }
  }

  // 2. 检查已确认日程冲突
  const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
  const confirmedList = b_confirmedSchedule[`${platform}:${userId}`] || [];
  for (let sch of confirmedList) {
    if (sch.day === day && timeOverlap(sch.time, time)) {
      results.push(`在 ${day} ${time} 已有确认的${sch.subtype || '活动'}安排`);
      break;
    }
  }

  // 3. 检查已接受但未成团的多人邀请（排除当前邀约）
  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  for (let [ref, group] of Object.entries(b_MultiGroupRequest)) {
    // 排除当前正在处理的多人邀约
    if (excludeMultiGroupRef && ref === excludeMultiGroupRef) continue;
    
    const status = group.targetList?.[roleName];
    if (status === "accepted" && group.day === day && timeOverlap(group.time, time)) {
      results.push(`在 ${day} ${time} 已接受其他多人小群邀请`);
      break;
    }
  }

  // 7. 检查已摘取的心愿（在已确认日程中）
  const myWishConfirmed = confirmedList.filter(ev => 
    ev.subtype === "心愿" &&
    ev.day === day &&
    timeOverlap(ev.time, time)
  );
  
  if (myWishConfirmed.length > 0) {
    results.push(`在 ${day} ${time} 已有安排`);
  }

  return results;
}

  function getAdminPassword() {
    let rawPass = ext.storageGet("adminPassword");
    let parsedPass;
  
    try {
      parsedPass = JSON.parse(rawPass);
    } catch (e) {
      parsedPass = rawPass;
    }
  
    return (parsedPass || "detroit").trim(); // 兜底并清理空格
  }

function isUserFeatureEnabled(roleName, key, defaultValue = true) {
  const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  const personConfig = blockMap[roleName];
  if (personConfig && personConfig[key] !== undefined) {
    return personConfig[key];
  }
  return defaultValue;
}
 // 辅助函数：统一获取并清洗数据格式
function getRoleStorage() {
    let data = JSON.parse(ext.storageGet("a_private_group") || "{}");
    let needsUpdate = false;

    // 集中处理老旧数据格式 (Array 转 Platform-Object 结构)
    for (let key in data) {
        if (Array.isArray(data[key])) {
            needsUpdate = true;
            let parts = data[key][0].split(":");
            let platform = parts.length > 1 ? parts[0] : "QQ";
            let uid = parts.length > 1 ? parts[1] : data[key][0];

            if (!data[platform]) data[platform] = {};
            data[platform][key] = [uid, data[key][1] || "0"];
            delete data[key];
        }
    }
    
    if (needsUpdate) ext.storageSet("a_private_group", JSON.stringify(data));
    return data;
}

// 1. 创建新角色
let cmd_bind_role = seal.ext.newCmdItemInfo();
cmd_bind_role.name = "创建新角色";
cmd_bind_role.help = "使用方法：.创建新角色 [名称]";
cmd_bind_role.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    if (!name || name === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    let platform = msg.platform;
    let gid = msg.groupId ? msg.groupId.replace(`${platform}-Group:`, "") : "0";
    let uid = msg.sender.userId.replace(`${platform}:`, "");
    let storage = getRoleStorage();

    if (!storage[platform]) storage[platform] = {};

    // 检查名称是否被他人占用
    if (storage[platform][name] && storage[platform][name][0] !== uid) {
        seal.replyToSender(ctx, msg, `❌ 名称「${name}」已被其他用户占用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查找并删除该用户旧的角色绑定 (防止一人多号)
    let oldName = Object.keys(storage[platform]).find(key => storage[platform][key][0] === uid);
    let isRename = !!oldName && oldName !== name;

    if (oldName) delete storage[platform][oldName];

    // 执行保存
    storage[platform][name] = [uid, gid];
    ext.storageSet("a_private_group", JSON.stringify(storage));

    let tip = isRename ? `角色名已由「${oldName}」更新为「${name}」` : `角色「${name}」创建成功！`;
    seal.replyToSender(ctx, msg, `✅ ${tip}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建新角色"] = cmd_bind_role;

// 2. 玩家名单
let cmd_role_list = seal.ext.newCmdItemInfo();
cmd_role_list.name = "玩家名单";
cmd_role_list.solve = (ctx, msg) => {
    let storage = getRoleStorage();
    let platform = msg.platform;
    let roles = storage[platform] || {};

    if (Object.keys(roles).length === 0) {
        seal.replyToSender(ctx, msg, `当前平台暂无已绑定的角色`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let rep = `📊 当前已绑定角色列表：\n`;
    for (let [name, info] of Object.entries(roles)) {
        let groupShow = info[1] === "0" ? "未录入" : info[1];
        rep += `👤 ${name}\n   ID: ${info[0]}\n   群号: ${groupShow}\n\n`;
    }
    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["玩家名单"] = cmd_role_list;

// 3. 清除玩家
let cmd_del_role = seal.ext.newCmdItemInfo();
cmd_del_role.name = "清除玩家";
cmd_del_role.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `该指令仅限骰主使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let delName = cmdArgs.getArgN(1);
    if (!delName) {
        seal.replyToSender(ctx, msg, `请输入要移除的角色名`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let storage = getRoleStorage();
    let platform = msg.platform;

    if (!storage[platform] || !storage[platform][delName]) {
        seal.replyToSender(ctx, msg, `未找到角色「${delName}」，请检查输入`);
        return seal.ext.newCmdExecuteResult(true);
    }

    delete storage[platform][delName];
    ext.storageSet("a_private_group", JSON.stringify(storage));
    seal.replyToSender(ctx, msg, `✅ 已成功清除玩家「${delName}」的数据`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["清除玩家"] = cmd_del_role;

// =========================
// 🎯 设置全局天数（格式如 D1、D2）
// 用于统一事件 / 发起邀约 / 时间轴等的"当前天数"标识
// =========================
let cmd_set_days = seal.ext.newCmdItemInfo();
cmd_set_days.name = "设置天数";
cmd_set_days.help = "。设置天数 D1 [清空] —— 设置全局天数，可选清空所有计数并生成统计报告\n示例：\n。设置天数 D2\n。设置天数 D3 清空";

cmd_set_days.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `⚠️ 该指令仅限骰主或管理员使用`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let dayStr = cmdArgs.getArgN(1);
  let clearFlag = (cmdArgs.getArgN(2) || "").toLowerCase();

  if (!dayStr || !/^D\d+$/i.test(dayStr)) {
    seal.replyToSender(ctx, msg, `⚠️ 请输入正确的天数格式，例如：。设置天数 D1`);
    return seal.ext.newCmdExecuteResult(true);
  }

  dayStr = dayStr.toUpperCase();
  const previousDay = ext.storageGet("global_days") || "未设置";
  ext.storageSet("global_days", dayStr);
  
  let responseText = `✅ 已将全局天数从 ${previousDay} 设置为：${dayStr}`;
  
  // 生成统计报告
  let statisticsReport = generateStatisticsReport(ctx, msg, dayStr, previousDay);
  // 清空寄信每日限制
  const platform = msg.platform;
  
  // 如果指定了清空，则清空所有计数
  if (clearFlag === "清空") {
    // 清空所有会面计数
    const meetingCountKeys = [
      "a_meetingCount_call",
      "a_meetingCount_private", 
      "a_meetingCount_letter",
      "a_meetingCount_gift",
      "a_meetingCount_wish",
      "a_meetingCount_chaosletter",
      "a_meetingCount_secretletter",
      "a_meetingCount_official"
    ];
    
    for (let key of meetingCountKeys) {
      ext.storageSet(key, "0");
    }
    

    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    if (a_private_group[platform]) {
      for (let roleName in a_private_group[platform]) {
        const uid = a_private_group[platform][roleName][0];
        const dailyLimitKey = `chaos_letter_daily_${platform}:${uid}_${dayStr}`;
        ext.storageSet(dailyLimitKey, "0");
      }
    }
    
    // 清空心愿池
    ext.storageSet("a_wishPool", JSON.stringify([]));
    
    // 清空心动信池
    ext.storageSet("lovemail_pool", JSON.stringify([]));
    
    responseText += `\n✅ 已同时清空所有会面计数、每日信件计数、寄信限制、心愿池和心动信池`;
  }
  
  // 发送到公告群（如果设置）
  const groupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
  if (groupId) {
    const msgDivine = seal.newMessage();
    msgDivine.messageType = "group";
    msgDivine.groupId = `${platform}-Group:${groupId}`;
    msgDivine.sender = {};
    const ctxDivine = seal.createTempCtx(ctx.endPoint, msgDivine);

    seal.replyToSender(ctxDivine, msgDivine, `📜 全局天数已从 ${previousDay} 切换到 ${dayStr}${clearFlag === "清空" ? "（所有计数已重置）" : ""}`);
  }
  
  // 发送到后台群（如果设置）
  const backgroundGroupId = JSON.parse(ext.storageGet("background_group_id"));
  if (backgroundGroupId) {
    sendStatisticsToBackgroundGroup(ctx, msg, dayStr, statisticsReport, clearFlag === "清空");
  }
  
  seal.replyToSender(ctx, msg, responseText + `\n\n📊 统计报告已生成${backgroundGroupId ? '并发送到后台群' : ''}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置天数"] = cmd_set_days;

// =========================
// 📊 统计报告生成函数
// =========================
/**
 * 生成统计报告
 */
function generateStatisticsReport(ctx, msg, newDay, previousDay, isCleared = false) {
  const platform = msg.platform;
  
  // 获取各种数据
  const meetingCounts = {
    "电话": parseInt(ext.storageGet("a_meetingCount_call") || "0"),
    "私密": parseInt(ext.storageGet("a_meetingCount_private") || "0"),
    "剧情信件": parseInt(ext.storageGet("a_meetingCount_letter") || "0"),
    "寄信": parseInt(ext.storageGet("a_meetingCount_chaosletter") || "0"),
    "礼物": parseInt(ext.storageGet("a_meetingCount_gift") || "0"),
    "匿名信": parseInt(ext.storageGet("a_meetingCount_secretletter") || "0"),
    "心愿": parseInt(ext.storageGet("a_meetingCount_wish") || "0"),
    "官约": parseInt(ext.storageGet("a_meetingCount_official") || "0")
  };
  
  // 获取群组状态
  const groupList = JSON.parse(ext.storageGet("group") || "[]");
  const totalGroups = groupList.length;
  const occupiedGroups = groupList.filter(g => g.endsWith("_占用")).length;
  const availableGroups = totalGroups - occupiedGroups;
  
  // 获取玩家数量
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  const playerCount = a_private_group[platform] ? Object.keys(a_private_group[platform]).length : 0;
  const loveshow_name = JSON.parse(ext.storageGet("love_show_name"))
  
  // 获取待处理请求
  const appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  const pendingRequests = appointmentList.length;
  
  // 获取多人邀约
  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  const multiRequests = Object.keys(b_MultiGroupRequest).length;
  
  // 获取已确认日程
  const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
  let activeMeetings = 0;
  for (const key in b_confirmedSchedule) {
    activeMeetings += b_confirmedSchedule[key].filter(item => item.status === "active").length;
  }
  
  // 获取心愿池
  const wishPool = JSON.parse(ext.storageGet("a_wishPool") || "[]");
  const wishCount = wishPool.length;
  
  // 获取心动信池
  const lovemailPool = JSON.parse(ext.storageGet("lovemail_pool") || "[]");
  const lovemailCount = lovemailPool.length;
  
  // 获取群组到期信息
  const groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
  const expiredGroups = Object.entries(groupExpireInfo)
    .filter(([_, info]) => Date.now() > info.expireTime)
    .length;
  
  // 生成报告
  let report = 
    `📊 【${loveshow_name}统计报告】\n\n` +
    `🔄 天数切换：${previousDay} → ${newDay}\n` +
    `🕒 生成时间：${new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })}\n` +
    
    `👥 【玩家统计】\n` +
    `• 绑定角色数：${playerCount} 人\n\n` +
    
    `📞 【会面统计】\n` +
    `• 电话会面：${meetingCounts["电话"]} 次\n` +
    `• 私密会面：${meetingCounts["私密"]} 次\n` +
    `• 剧情信件：${meetingCounts["剧情信件"]} 次\n` +
    `• 寄信：${meetingCounts["寄信"]} 次\n` +
    `• 礼物馈赠：${meetingCounts["礼物"]} 次\n` +
    `• 匿名信：${meetingCounts["匿名信"]} 次\n` +
    `• 心愿达成：${meetingCounts["心愿"]} 次\n` +
    `• 官方约会：${meetingCounts["官约"]} 次\n\n` +
    
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
  
  // 添加建议
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
  const backgroundGroupId = JSON.parse(ext.storageGet("background_group_id"));
  
  if (!backgroundGroupId) return;
  
  const backgroundMsg = seal.newMessage();
  backgroundMsg.messageType = "group";
  backgroundMsg.sender = {};
  backgroundMsg.sender.userId = msg.sender.userId;
  backgroundMsg.groupId = `${platform}-Group:${backgroundGroupId}`;
  const backgroundCtx = seal.createTempCtx(ctx.endPoint, backgroundMsg);
  
  // 构建后台群消息
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
// 🗝️ 地点权限管理系统 精简版
// ========================

// --- 核心工具函数 ---
const store = {
    get: (key) => JSON.parse(ext.storageGet(key) || "{}"),
    set: (key, val) => ext.storageSet(key, JSON.stringify(val))
};

const getRoleName = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    return Object.entries(store.get("a_private_group")[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0];
};

// --- 逻辑判断逻辑 ---
function checkPlacePermission(platform, roleName, placeName) {
    const config = store.get("place_system_config");
    if (!config.enabled || config.enabled === undefined) return { allowed: true };
    
    const places = store.get("available_places");
    const place = places[placeName];

    // 处理私人房间
    if (!place) {
        const owner = placeName.match(/^(.+?)的房间$/)?.[1];
        const groups = store.get("a_private_group")[platform] || {};
        return { allowed: !!(owner && groups[owner]), reason: "地点不存在或私人房间未激活" };
    }

    if (!place.locked) return { allowed: true };
    const hasKey = (store.get("place_keys")[platform]?.[roleName] || []).includes(placeName);
    return { allowed: hasKey, reason: "需要钥匙" };
}

/**
 * 统一的地点检查函数（优化版）
 * @param {string} platform 平台
 * @param {string} senderName 发送者角色名
 * @param {string} place 地点
 * @param {string} instructionName 指令名称
 */
function checkPlaceCommon(platform, senderName, place, instructionName = "发起邀约") {
  // 获取配置，增加默认值兜底
  const placeSystemConfig = JSON.parse(ext.storageGet("place_system_config") || '{"enabled": false}');
  const availablePlaces = JSON.parse(ext.storageGet("available_places") || "{}");
  
  // --- 情况 A: 地点系统已【启用】 (严格检查模式) ---
  if (placeSystemConfig.enabled) {
    // 调用你原有的权限检查函数
    const permission = checkPlacePermission(platform, senderName, place);
    
    if (!permission.allowed) {
      let errorMsg = `⚠️ 地点「${place}」不可用：${permission.reason}\n\n`;
      
      if (Object.keys(availablePlaces).length > 0) {
        errorMsg += "📍 可用地点：\n";
        Object.entries(availablePlaces).forEach(([placeName, data]) => {
          const desc = data.desc ? `（${data.desc}）` : '';
          const lockStatus = data.locked ? '🔒' : '📍';
          errorMsg += `${lockStatus} ${placeName}${desc}\n`;
        });
        errorMsg += "\n";
      }
      
      errorMsg += "💡 温馨提示：\n";
      errorMsg += "- 也可以选择「[角色名]的房间」格式\n";
      errorMsg += "- 使用「查看可私约地点」查看可用地点\n";
      errorMsg += "- 使用「查看我的钥匙」查看拥有的钥匙";
      
      return { valid: false, errorMsg: errorMsg };
    }
  } 
  
  // --- 情况 B: 地点系统已【禁用】 (宽松检查模式) ---
  else {
    const placeExists = availablePlaces[place];
    const isPrivateRoom = place.match(/^(.+?)的房间$/);
    
    // 如果地点不在预设库里，且也不是私人房间
    if (Object.keys(availablePlaces).length > 0 && !placeExists && !isPrivateRoom) {
      let warningMsg = `📢 提示：地点系统未启用，已自动通过${instructionName}。\n`;
      warningMsg += `📝 您填写的地点「${place}」不在预设名单中。\n\n`;
      
      warningMsg += "📍 当前预设地点库：\n";
      Object.entries(availablePlaces).forEach(([placeName, data]) => {
        const desc = data.desc ? `（${data.desc}）` : '';
        warningMsg += `· ${placeName}${desc}\n`;
      });

      // valid 为 true，不拦截，仅通过 warningMsg 携带提示
      return { valid: true, errorMsg: "", warningMsg: warningMsg };
    }
  }
  
  // 默认通过
  return { valid: true, errorMsg: "", warningMsg: "" };
}

// --- 玩家指令 ---
let cmdPlace = seal.ext.newCmdItemInfo();
cmdPlace.name = "地点";
cmdPlace.help = "。地点 查看 // 。地点 钥匙";
cmdPlace.solve = (ctx, msg, cmdArgs) => {
    const role = getRoleName(ctx, msg);
    const platform = msg.platform;
    const sub = cmdArgs.getArgN(1);
    const places = store.get("available_places");
    const userKeys = role ? (store.get("place_keys")[platform]?.[role] || []) : [];

    if (sub === "查看") {
        let rep = "🏢 可用地点列表：\n";
        Object.entries(places).forEach(([name, data]) => {
            const status = data.locked ? (userKeys.includes(name) ? "🔑" : "🔒") : "📍";
            rep += `${status} ${name}${data.desc ? `:${data.desc}` : ""}\n`;
        });
        return seal.replyToSender(ctx, msg, rep + "\n提示：也可使用「[角色名]的房间」");
    }
    
    if (sub === "钥匙") {
        if (!role) return seal.replyToSender(ctx, msg, "未绑定角色");
        return seal.replyToSender(ctx, msg, userKeys.length ? `🔑 拥有钥匙：\n${userKeys.join("、")}` : "🔐 无钥匙");
    }
};
ext.cmdMap["地点"] = cmdPlace;

// ========================
// 🛠️ 地点管理系统 - 核心指令集
// ========================

// 1. 基础管理指令：。地点管理 [添加/删除/开关/钥匙/清空]
let cmdPlaceAdm = seal.ext.newCmdItemInfo();
cmdPlaceAdm.name = "地点管理";
cmdPlaceAdm.help = "。地点管理 添加 地点:描述 / 删除 地点 / 开关 地点 / 钥匙 角色名 地点 / 清空";
cmdPlaceAdm.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const op = cmdArgs.getArgN(1);
    let places = JSON.parse(ext.storageGet("available_places") || "{}");
    let keys = JSON.parse(ext.storageGet("place_keys") || "{}");
    const pf = msg.platform;

    switch(op) {
        case "添加": {
            const arg = cmdArgs.getArgN(2);
            if (!arg) return seal.replyToSender(ctx, msg, "使用：.地点管理 添加 地点名:描述");
            const [name, desc] = arg.split(":");
            places[name.trim()] = { desc: desc || "", locked: false, creator: "管理员", created_at: new Date().toLocaleString() };
            seal.replyToSender(ctx, msg, `✅ 已添加地点：${name}`);
            break;
        }
        case "删除": {
            const name = cmdArgs.getArgN(2);
            delete places[name];
            seal.replyToSender(ctx, msg, `🗑️ 已删除地点：${name}`);
            break;
        }
        case "开关": {
            const name = cmdArgs.getArgN(2);
            if (places[name]) {
                places[name].locked = !places[name].locked;
                seal.replyToSender(ctx, msg, `🔐 ${name} 状态：${places[name].locked ? "已上锁" : "已解锁"}`);
            } else {
                seal.replyToSender(ctx, msg, "❌ 地点不存在");
            }
            break;
        }
        case "钥匙": {
            const role = cmdArgs.getArgN(2);
            const pName = cmdArgs.getArgN(3);
            if (!places[pName]) return seal.replyToSender(ctx, msg, "❌ 目标地点不存在");
            if (!keys[pf]) keys[pf] = {};
            if (!keys[pf][role]) keys[pf][role] = [];
            
            const idx = keys[pf][role].indexOf(pName);
            if (idx === -1) {
                keys[pf][role].push(pName);
                seal.replyToSender(ctx, msg, `🔑 已发放 [${pName}] 钥匙给 [${role}]`);
            } else {
                keys[pf][role].splice(idx, 1);
                seal.replyToSender(ctx, msg, `🚫 已收回 [${role}] 的 [${pName}] 钥匙`);
            }
            break;
        }
        case "清空": {
            if (cmdArgs.getArgN(2) !== "Y") return seal.replyToSender(ctx, msg, "⚠️ 确认清空请使用：.地点管理 清空 Y");
            places = {}; keys = {};
            seal.replyToSender(ctx, msg, "🧹 地点系统已彻底初始化");
            break;
        }
        default:
            seal.replyToSender(ctx, msg, "💡 子指令：添加、删除、开关、钥匙、清空");
    }
    ext.storageSet("available_places", JSON.stringify(places));
    ext.storageSet("place_keys", JSON.stringify(keys));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["地点管理"] = cmdPlaceAdm;

// 2. 批量设置地点
let cmdBatchPlace = seal.ext.newCmdItemInfo();
cmdBatchPlace.name = "批量设置地点";
cmdBatchPlace.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const arg = cmdArgs.getArgN(1);
    if (!arg) return seal.replyToSender(ctx, msg, "格式：地点1:描述/地点2:描述");
    
    let places = JSON.parse(ext.storageGet("available_places") || "{}");
    const items = arg.split("/");
    items.forEach(item => {
        const [name, desc] = item.split(":");
        if (name) places[name.trim()] = { desc: desc || "", locked: false, creator: "管理员", created_at: new Date().toLocaleString() };
    });
    ext.storageSet("available_places", JSON.stringify(places));
    seal.replyToSender(ctx, msg, `✅ 成功批量处理 ${items.length} 个地点`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["批量设置地点"] = cmdBatchPlace;

// 3. 批量发放钥匙
let cmdBatchKey = seal.ext.newCmdItemInfo();
cmdBatchKey.name = "批量发放钥匙";
cmdBatchKey.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const roles = (cmdArgs.getArgN(1) || "").split("/");
    const pNames = (cmdArgs.getArgN(2) || "").split("/");
    let keys = JSON.parse(ext.storageGet("place_keys") || "{}");
    const pf = msg.platform;
    if (!keys[pf]) keys[pf] = {};

    roles.forEach(r => {
        if (!keys[pf][r.trim()]) keys[pf][r.trim()] = [];
        pNames.forEach(p => {
            if (!keys[pf][r.trim()].includes(p.trim())) keys[pf][r.trim()].push(p.trim());
        });
    });
    ext.storageSet("place_keys", JSON.stringify(keys));
    seal.replyToSender(ctx, msg, "✅ 批量授权完成");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["批量发放钥匙"] = cmdBatchKey;

// 4. 查看详情与统计 (合二为一)
let cmdViewPlace = seal.ext.newCmdItemInfo();
cmdViewPlace.name = "查看地点详情";
cmdViewPlace.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const places = JSON.parse(ext.storageGet("available_places") || "{}");
    const keys = JSON.parse(ext.storageGet("place_keys") || "{}")[msg.platform] || {};
    
    let rep = "🏢 地点系统详细报告：\n";
    Object.entries(places).forEach(([name, data]) => {
        const holders = Object.entries(keys).filter(([_, kList]) => kList.includes(name)).map(([r]) => r);
        rep += `\n${data.locked ? "🔒" : "🔓"} ${name}\n 📝 描述：${data.desc || "无"}\n 🔑 持有：${holders.join(",") || "无人"}\n`;
    });
    seal.replyToSender(ctx, msg, rep || "📭 系统内无地点数据");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看地点详情"] = cmdViewPlace;
ext.cmdMap["查看钥匙分配"] = cmdViewPlace; // 共用逻辑

// ========================
// 📞 电话指令（合并版）- 重构版
// ========================
let cmd_phone = seal.ext.newCmdItemInfo();
cmd_phone.name = "电话";
cmd_phone.help = "。电话 1100-1200 邀请人1[/邀请人2/...] [标题]\n示例：\n。电话 1100-1200 张三\n。电话 1400-1500 李四/王五 一起聊聊";

// 🔧 手机QQ适配版 - 消息生成函数
function generatePhoneInvitationMessage(sendname, title, day, time, isMulti, otherNames) {
  const line = "━━━━━━━━━━━━━━"; // 视觉分割线
  const subLine = "┈┈┈┈┈┈┈┈┈┈┈┈"; // 副分割线
  
  let message = `📱 【语音通话邀约】\n${line}\n`;
  
  // 留言内容区
  message += `💭 留言内容：\n`;
  if (title) {
    message += `「 ${title} 」\n`;
  }
  
  message += `“ 嗨~ 我是 ${sendname}！\n`;
  
  if (isMulti) {
    message += `我想在 ${day} 的 ${time} 找你打个电话`;
    if (otherNames.length > 0) {
      const peers = otherNames.length === 1 
                    ? otherNames[0] 
                    : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
      message += `，${peers}也会加入。`;
    }
  } else {
    message += `我想在 ${day} 的 ${time} 找你单独聊聊天～`;
  }
  
  message += `\n电话已准备好，等你接通哦！ ”\n`;
  message += `${subLine}\n`;

  // 操作指南区（使用更醒目的列表符号）
  message += `💡 操作指引：\n`;
  message += `🔹 输入：.私约请求 (查看详情)\n`;
  message += `🔹 输入：.接受 序号 (接通电话)\n`;
  message += `🔹 输入：.拒绝 序号 (暂时忙线)\n\n`;
  
  message += `⚙️ 进群后请输入：.ext all on\n`;
  message += `${line}\n`;
  message += `⏳ 电话呼叫中，请及时回复...`;

  return message;
}

// 🔧 获取当前现实时段
function getCurrentRealityTimeSlot() {
  const now = new Date();
  const hours = now.getHours();
  const minutes = now.getMinutes();
  
  if (hours >= 0 && hours < 8) {
    return 1; // 时段1: 00:00–07:59
  } else if (hours >= 8 && hours < 16) {
    return 2; // 时段2: 08:00–15:59
  } else {
    return 3; // 时段3: 16:00–23:59
  }
}

// 🔧 检查游戏时间是否属于指定时段
function isTimeInSlot(time, targetSlot) {
  const timeSlots = {
    1: { start: "00:00", end: "07:59" },
    2: { start: "08:00", end: "15:59" },
    3: { start: "16:00", end: "23:59" }
  };
  
  const match = time.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/);
  if (!match) return false;
  
  const startTime = `${match[1]}:${match[2]}`;
  const endTime = `${match[3]}:${match[4]}`;
  
  const slot = timeSlots[targetSlot];
  if (!slot) return false;
  
  // 检查开始时间和结束时间是否都在目标时段内
  return startTime >= slot.start && startTime <= slot.end && 
         endTime >= slot.start && endTime <= slot.end;
}

cmd_phone.solve = (ctx, msg, cmdArgs) => {
  let config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
  let enable_general_appointment = config.enable_general_appointment ?? true;
  if (!enable_general_appointment) {
    seal.replyToSender(ctx, msg, `📅 当前已禁用通用发起邀约功能，无法发起电话。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🔐 检查用户权限
  const platform = msg.platform;
  const uid = msg.sender.userId.replace(`${platform}:`, "");
  
  // 获取发送者角色名
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  if (!a_private_group[platform]) a_private_group[platform] = {};
  
  const sendname = Object.entries(a_private_group[platform])
    .find(([_, val]) => val[0] === uid)?.[0];
  if (!sendname) {
    seal.replyToSender(ctx, msg, `请先使用「创建新角色」绑定角色`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查该角色是否被禁止使用发起邀约功能
  const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  if (blockMap[sendname] && blockMap[sendname].enable_general_appointment === false) {
    seal.replyToSender(ctx, msg, `🚫 您已被禁止使用发起邀约功能`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const globalDay = ext.storageGet("global_days");
  if (!globalDay) {
    seal.replyToSender(ctx, msg, `⚠️ 当前尚未设置全局天数，请先使用 "。设置天数 D1"`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  const day = globalDay;
  
  // 获取参数
  let rawTime = cmdArgs.getArgN(1);
  let namesArg = cmdArgs.getArgN(2);
  let title = cmdArgs.getArgN(3);

  if (!rawTime || !namesArg) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  // 转换时间格式
  let time = "";
  if (/^\d{4}-\d{4}$/.test(rawTime)) {
    const start = rawTime.slice(0, 2) + ":" + rawTime.slice(2, 4);
    const end = rawTime.slice(5, 7) + ":" + rawTime.slice(7, 9);
    time = `${start}-${end}`;
  } else {
    seal.replyToSender(ctx, msg,
      `⚠️ 时间参数格式错误：「${rawTime}」\n` +
      `请输入四位数字格式，如：1100-1200`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // ========== 检查现实时段限制 ==========
  const enableRealityCheck = seal.ext.getBoolConfig(ext, "开启现实时段校验");
  
  if (enableRealityCheck) {
    const currentRealitySlot = getCurrentRealityTimeSlot();
    const timeSlots = {
      1: { start: "00:00", end: "07:59", name: "时段1 (00:00–07:59)" },
      2: { start: "08:00", end: "15:59", name: "时段2 (08:00–15:59)" },
      3: { start: "16:00", end: "23:59", name: "时段3 (16:00–23:59)" }
    };
    
    const currentSlot = timeSlots[currentRealitySlot];
    
    // 只有在开关开启时，才执行 isTimeInSlot 检查
    if (!isTimeInSlot(time, currentRealitySlot)) {
      seal.replyToSender(ctx, msg,
        `⚠️ 时段限制：当前现实时间为 ${formatTime(new Date())}，属于${currentSlot.name}\n` +
        `你只能发起该时段内的剧情邀约。\n\n` +
        `💡 如需取消此限制，请联系管理在插件配置中关闭“开启现实时段校验”。`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }
  // ========== 检查结束 ==========

  // 🔒 检查时间是否在允许范围内
  const allowedTimeRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
  if (allowedTimeRanges.length > 0) {
    let isTimeAllowed = false;
    const [userStart, userEnd] = time.split('-');
    
    for (const range of allowedTimeRanges) {
      const [rangeStart, rangeEnd] = range.split('-');
      if (userStart >= rangeStart && userEnd <= rangeEnd) {
        isTimeAllowed = true;
        break;
      }
    }
    
    if (!isTimeAllowed) {
      const allowedRangesText = allowedTimeRanges.map(range => `· ${range}`).join('\n');
      seal.replyToSender(ctx, msg,
        `⚠️ 时间 ${time} 不在允许的范围内\n\n` +
        `📋 当前允许的时间段：\n${allowedRangesText}\n\n` +
        `请选择上述时间段内的预约时间~`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  // 检查时间格式
  if (!isValidTimeFormat(time)) {
    seal.replyToSender(ctx, msg, `请输入正确的时间格式，时间段需合法`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查时间长度
  const durationConfig = JSON.parse(ext.storageGet("appointment_duration_config") || "{}");
  const phoneMinDuration = durationConfig.phone !== undefined ? durationConfig.phone : 29;

  const match = time.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/);
  if (match) {
      const startMinutes = parseInt(match[1]) * 60 + parseInt(match[2]);
      const endMinutes = parseInt(match[3]) * 60 + parseInt(match[4]);
      const duration = endMinutes - startMinutes;

      if (duration < phoneMinDuration) {
          seal.replyToSender(ctx, msg, `⚠️ 电话邀约时间需大于等于 ${phoneMinDuration}分钟，请重新设置（如 1400-14${phoneMinDuration < 10 ? '0' : ''}${phoneMinDuration}）`);
          return seal.ext.newCmdExecuteResult(true);
      }
  }

  if (!a_private_group[platform]) a_private_group[platform] = {};

  // 解析邀请人
  const names = namesArg.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
  const isMulti = names.length > 1;

  // 🔒 检查是否被锁定
  let a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
  
  // 检查所有邀请人
  const fromKey = `${platform}:${uid}`;
  let failed = [];
  
  for (let toname of names) {
    // 检查对方是否已绑定
    if (!a_private_group[platform] || !a_private_group[platform][toname]) {
      failed.push(`${toname}（未注册）`);
      continue;
    }

    const toKey = `${platform}:${a_private_group[platform][toname][0]}`;

    // 检查对方是否被锁定
    const toLocked = a_lockedSlots[toKey]?.[day] || [];
    if (toLocked.some(lockedTime => timeOverlap(time, lockedTime))) {
      failed.push(`${toname}（该时段被锁定）`);
      continue;
    }

    // 不能邀请自己
    if (toname === sendname) {
      failed.push(`${toname}（不能邀请自己）`);
      continue;
    }
  }

  if (failed.length > 0) {
    seal.replyToSender(ctx, msg, `⚠️ 无法发起电话，以下对象不符合条件：\n- ${failed.join("\n- ")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查自己是否被锁定
  const fromLocked = a_lockedSlots[fromKey]?.[day] || [];
  if (fromLocked.some(lockedTime => timeOverlap(time, lockedTime))) {
    seal.replyToSender(ctx, msg, `⚠️ 你在 ${day} ${time} 段与锁定时间重叠，无法发起预约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 地点默认为"电话"
  const place = "电话";

  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

  // 检查发起人冲突
  let conflict = false;
  if (b_confirmedSchedule[fromKey]) {
    b_confirmedSchedule[fromKey].forEach(ev => {
      const subtype = (ev.subtype || "").toLowerCase();
      if (
        ["小群", "续杯", "私密", "电话"].includes(subtype) &&
        timeConflict(day, time, ev.day, ev.time)
      ) {
        conflict = true;
      }
    });
  }

  if (conflict) {
    seal.replyToSender(ctx, msg, `⚠️ 你在 ${day} ${time} 时段已有安排，无法发起电话~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查其他冲突（不暴露具体安排）
  for (let toname of names) {
    // 检查是否已被对方发过相同时间段的小群请求
    const backRequest = appointmentList.find(app =>
      app.sendid === a_private_group[platform][toname][0] &&
      app.toname === sendname &&
      app.day === day &&
      timeConflict(app.time, time)
    );

    if (backRequest) {
      seal.replyToSender(ctx, msg,
        `⚠️ ${toname} 已向你发送了一条在 ${day} ${time} 的小群请求，建议先使用"私约请求"处理`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 检查对方是否已有安排（不告诉发起人具体是什么安排）
    const toKey = `${platform}:${a_private_group[platform][toname][0]}`;
    if (b_confirmedSchedule[toKey]) {
      let hasConflict = false;
      b_confirmedSchedule[toKey].forEach(ev => {
        if (timeConflict(day, time, ev.day, ev.time)) {
          hasConflict = true;
        }
      });
      if (hasConflict) {
        failed.push(`${toname}（该时段已有安排）`);
      }
    }

    // 检查多人邀约冲突
    for (let [ref, group] of Object.entries(b_MultiGroupRequest)) {
      if (group.day !== day || !timeOverlap(group.time, time)) continue;
      
      const sendStatus = group.targetList?.[sendname];
      if (sendStatus === "accepted" || sendStatus === null) {
        seal.replyToSender(ctx, msg,
          `⚠️ 你在 ${day} ${time} 已被邀请参与一个多人小群（状态：${sendStatus === "accepted" ? "已接受" : "待回应"}），不可重复发起该时间段小群`);
        return seal.ext.newCmdExecuteResult(true);
      }
      
      const targetStatus = group.targetList?.[toname];
      if (targetStatus === "accepted") {
        seal.replyToSender(ctx, msg,
          `⚠️ ${toname} 已接受一个多人小群邀请（${group.day} ${group.time}），但尚未建群，时间冲突无法发起单人小群`);
        return seal.ext.newCmdExecuteResult(true);
      }
    }
  }

  if (failed.length > 0) {
    seal.replyToSender(ctx, msg, `⚠️ 无法发起电话，以下对象在该时段已有安排：\n- ${failed.join("\n- ")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 创建邀约
  if (isMulti) {
    // 多人电话
    const groupRef = generateGroupRef();
    const groupData = {
      id: groupRef,
      sendname, 
      sendid: uid,
      subtype: "电话",
      day, 
      time, 
      place,
      title: title || "",
      targetList: {}
    };

    // 为每个邀请人创建记录
    for (let toname of names) {
      const toid = a_private_group[platform][toname][0];
      groupData.targetList[toname] = null;

      appointmentList.push({
        id: generateId(),
        type: "小群",
        subtype: "电话",
        sendname,
        sendid: uid,
        toname,
        toid,
        gid: a_private_group[platform][sendname][1],
        day, 
        time, 
        place,
        title: title || "",
        groupRef
      });

      // 发送通知（使用通用函数）
      const newmsg = seal.newMessage();
      newmsg.messageType = "group";
      newmsg.sender = {};
      newmsg.sender.userId = `${platform}:${toid}`;
      newmsg.groupId = `${platform}-Group:${a_private_group[platform][toname][1]}`;
      const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
      
      const otherNames = names.filter(n => n !== toname);
      const noticeText = generatePhoneInvitationMessage(
        sendname, 
        title, 
        day, 
        time, 
        true, 
        otherNames
      );
      
      seal.replyToSender(newctx, newmsg, noticeText);
    }

    // 保存多人邀约数据
    b_MultiGroupRequest[groupRef] = groupData;
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
    
  } else {
    // 单人电话
    const toname = names[0];
    const toid = a_private_group[platform][toname][0];
    
    appointmentList.push({
      id: generateId(),
      type: "小群",
      subtype: "电话",
      sendname,
      sendid: uid,
      toname,
      toid,
      gid: a_private_group[platform][sendname][1],
      day,
      time,
      place,
      title: title || ""
    });

    // 发送通知（使用通用函数）
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${toid}`;
    newmsg.groupId = `${platform}-Group:${a_private_group[platform][toname][1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    const noticeText = generatePhoneInvitationMessage(
      sendname, 
      title, 
      day, 
      time, 
      false, 
      []
    );
    
    seal.replyToSender(newctx, newmsg, noticeText);
  }
  
  ext.storageSet("appointmentList", JSON.stringify(appointmentList));

  const successMsg = isMulti 
    ? `✅ 你已成功向 ${names.join("、")} 发起多人电话邀约`
    : `你已经悄悄给 ${names[0]} 发出了一条电话邀约，等他/她发现吧~`;
  
  seal.replyToSender(ctx, msg, successMsg);
    
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["电话"] = cmd_phone;

// 🔧 格式化时间函数（辅助函数）
function formatTime(date) {
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${hours}:${minutes}`;
}

// ========================
// 🤫 私约指令（合并版）- 重构版
// ========================
let cmd_appointment_private = seal.ext.newCmdItemInfo();
cmd_appointment_private.name = "私约";
cmd_appointment_private.help = "私约 1120-1230 地点 对方角色名[/对方2/...]\n示例：\n。私约 11:20-12:30 餐厅 张三\n。私约 1400-1500 咖啡厅 李四/王五";

// 🔧 手机QQ适配版 - 私密邀约消息生成函数
function generatePrivateInvitationMessage(sendname, place, day, time, isMulti, otherNames) {
  const line = "━━━━━━━━━━━━━━"; // 视觉分割线
  const subLine = "┈┈┈┈┈┈┈┈┈┈┈┈"; // 副分割线
  
  let message = `💌 【私密约会邀请】\n${line}\n`;
  
  // 留言内容区
  message += `💭 留言内容：\n`;
  message += `“ 嗨~ 我是 ${sendname}！\n`;
  
  if (isMulti && otherNames.length > 0) {
    const peers = otherNames.length === 1 
                  ? otherNames[0] 
                  : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
    message += `我想邀请你和 ${peers}，\n`;
  } else {
    message += `我想单独邀请你，\n`;
  }
  
  message += `在 ${day} 的 ${time}\n`;
  message += `前往【 ${place} 】聚聚。\n`;
  message += `期待你的到来哦~ ”\n`;
  
  message += `${subLine}\n`;

  // 操作指南区
  message += `💡 操作指引：\n`;
  message += `🔹 输入：.私约请求 (查看详情)\n`;
  message += `🔹 输入：.接受 序号 (确认赴约)\n`;
  message += `🔹 输入：.拒绝 序号 (婉拒邀请)\n\n`;
  
  message += `📍 到达地点后请留意环境描述\n`;
  message += `${line}\n`;
  message += `⏳ 邀约确认中，请及时回复！ ✨`;
  
  return message;
}

// 🔧 通用创建邀约记录和发送通知函数
function createAndNotifyAppointment({
  ctx,
  platform,
  sendname,
  sendid,
  subtype,
  day,
  time,
  place,
  names,
  title = "",
  isMulti,
  generateMessageFn,
  successMessage
}) {
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  let b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  
  let groupRef = null;
  
  if (isMulti) {
    // 多人邀约
    groupRef = generateGroupRef();
    const groupData = {
      id: groupRef,
      sendname, 
      sendid,
      subtype,
      day, 
      time, 
      place,
      title,
      targetList: {}
    };
    
    b_MultiGroupRequest[groupRef] = groupData;
  }
  
  // 为每个邀请人创建记录并发送通知
  for (let toname of names) {
    const toid = a_private_group[platform][toname][0];
    
    // 创建邀约记录
    const appointmentRecord = {
      id: generateId(),
      type: "小群",
      subtype,
      sendname,
      sendid,
      toname,
      toid,
      gid: a_private_group[platform][sendname][1],
      day, 
      time, 
      place,
      ...(title ? { title } : {})
    };
    
    if (isMulti && groupRef) {
      appointmentRecord.groupRef = groupRef;
      b_MultiGroupRequest[groupRef].targetList[toname] = null;
    }
    
    appointmentList.push(appointmentRecord);
    
    // 发送通知
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${toid}`;
    newmsg.groupId = `${platform}-Group:${a_private_group[platform][toname][1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
    
    const otherNames = isMulti ? names.filter(n => n !== toname) : [];
    const noticeText = generateMessageFn(sendname, place, day, time, isMulti, otherNames,toname);
    
    seal.replyToSender(newctx, newmsg, noticeText);
  }
  
  // 保存数据
  ext.storageSet("appointmentList", JSON.stringify(appointmentList));
  if (isMulti) {
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
  }
  
  return {
    success: true,
    groupRef,
    isMulti,
    names
  };
}

cmd_appointment_private.solve = (ctx, msg, cmdArgs) => {
  let config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
  let enable_general_appointment = config.enable_general_appointment ?? true;
  if (!enable_general_appointment) {
    seal.replyToSender(ctx, msg, "📅 当前已禁用通用发起邀约功能，无法发起私密邀约。");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🔐 检查用户权限
  const platform = msg.platform;
  const uid = msg.sender.userId.replace(`${platform}:`, "");
  
  // 获取发送者角色名
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  if (!a_private_group[platform]) a_private_group[platform] = {};
  
  const sendname = Object.entries(a_private_group[platform])
    .find(([_, val]) => val[0] === uid)?.[0];
  if (!sendname) {
    seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查该角色是否被禁止使用发起邀约功能
  const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  if (blockMap[sendname] && blockMap[sendname].enable_general_appointment === false) {
    seal.replyToSender(ctx, msg, "🚫 您已被禁止使用发起邀约功能");
    return seal.ext.newCmdExecuteResult(true);
  }

  const globalDay = ext.storageGet("global_days");
  if (!globalDay) {
    seal.replyToSender(ctx, msg, "⚠️ 当前尚未设置全局天数，请先使用 \"。设置天数 D1\"");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  const day = globalDay;
  
  // 获取参数
  let rawTime = cmdArgs.getArgN(1);
  let place = cmdArgs.getArgN(2);
  let namesArg = cmdArgs.getArgN(3);

  if (!rawTime || !place || !namesArg) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  // 统一处理时间格式（支持1100-1200和11:20-12:30两种格式）
  let time = "";
  if (/^\d{4}-\d{4}$/.test(rawTime)) {
    // 格式: 1100-1200 -> 11:00-12:00
    const start = rawTime.slice(0, 2) + ":" + rawTime.slice(2, 4);
    const end = rawTime.slice(5, 7) + ":" + rawTime.slice(7, 9);
    time = `${start}-${end}`;
  } else if (/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/.test(rawTime)) {
    // 格式: 11:20-12:30
    time = rawTime;
  } else {
    seal.replyToSender(ctx, msg,
      `⚠️ 时间参数格式错误：「${rawTime}」\n` +
      `请输入标准格式，如：\n` +
      `· 1100-1200\n` +
      `· 11:20-12:30`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // ========== 检查现实时段限制 ==========
  const enableRealityCheck = seal.ext.getBoolConfig(ext, "开启现实时段校验");
  
  if (enableRealityCheck) {
    const currentRealitySlot = getCurrentRealityTimeSlot();
    const timeSlots = {
      1: { start: "00:00", end: "07:59", name: "时段1 (00:00–07:59)" },
      2: { start: "08:00", end: "15:59", name: "时段2 (08:00–15:59)" },
      3: { start: "16:00", end: "23:59", name: "时段3 (16:00–23:59)" }
    };
    
    const currentSlot = timeSlots[currentRealitySlot];
    
    // 只有在开关开启时，才执行 isTimeInSlot 检查
    if (!isTimeInSlot(time, currentRealitySlot)) {
      seal.replyToSender(ctx, msg,
        `⚠️ 时段限制：当前现实时间为 ${formatTime(new Date())}，属于${currentSlot.name}\n` +
        `你只能发起该时段内的剧情邀约。\n\n` +
        `💡 如需取消此限制，请联系管理在插件配置中关闭“开启现实时段校验”。`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }
  // ========== 检查结束 ==========
  
  // 🔒 检查时间是否在允许范围内
  const allowedTimeRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
  if (allowedTimeRanges.length > 0) {
    let isTimeAllowed = false;
    const [userStart, userEnd] = time.split('-');
    
    for (const range of allowedTimeRanges) {
      const [rangeStart, rangeEnd] = range.split('-');
      if (userStart >= rangeStart && userEnd <= rangeEnd) {
        isTimeAllowed = true;
        break;
      }
    }
    
    if (!isTimeAllowed) {
      const allowedRangesText = allowedTimeRanges.map(range => `· ${range}`).join('\n');
      seal.replyToSender(ctx, msg,
        `⚠️ 时间 ${time} 不在允许的范围内\n\n` +
        `📋 当前允许的时间段：\n${allowedRangesText}\n\n` +
        `请选择上述时间段内的预约时间~`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  // 检查时间格式有效性
  if (!isValidTimeFormat(time)) {
    seal.replyToSender(ctx, msg, "请输入正确的时间格式，时间段需合法");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查时间长度
  const durationConfig = JSON.parse(ext.storageGet("appointment_duration_config") || "{}");
  const privateMinDuration = durationConfig.private !== undefined ? durationConfig.private : 59;

  const match = time.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/);
  if (match) {
    const startMinutes = parseInt(match[1]) * 60 + parseInt(match[2]);
    const endMinutes = parseInt(match[3]) * 60 + parseInt(match[4]);
    const duration = endMinutes - startMinutes;

    if (duration < privateMinDuration) {
      seal.replyToSender(ctx, msg, `⚠️ 私密邀约时间需大于等于 ${privateMinDuration}分钟，请重新设置（如 14:00-15:00）`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  // 解析邀请人
  const names = namesArg.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
  const isMulti = names.length > 1;

  if (!a_private_group[platform]) a_private_group[platform] = {};

  // 🔒 检查是否被锁定
  let a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
  const fromKey = `${platform}:${uid}`;
  
  // 检查所有邀请人
  let failed = [];
  
  for (let toname of names) {
    // 检查对方是否已绑定
    if (!a_private_group[platform] || !a_private_group[platform][toname]) {
      failed.push(`${toname}（未注册）`);
      continue;
    }

    const toKey = `${platform}:${a_private_group[platform][toname][0]}`;

    // 检查对方是否被锁定
    const toLocked = a_lockedSlots[toKey]?.[day] || [];
    if (toLocked.some(lockedTime => timeOverlap(time, lockedTime))) {
      failed.push(`${toname}（该时段被锁定）`);
      continue;
    }

    // 不能邀请自己
    if (toname === sendname) {
      failed.push(`${toname}（不能邀请自己）`);
      continue;
    }
  }

  if (failed.length > 0) {
    seal.replyToSender(ctx, msg, `⚠️ 无法发起私约，以下对象不符合条件：\n- ${failed.join("\n- ")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查自己是否被锁定
  const fromLocked = a_lockedSlots[fromKey]?.[day] || [];
  if (fromLocked.some(lockedTime => timeOverlap(time, lockedTime))) {
    seal.replyToSender(ctx, msg, `⚠️ 你在 ${day} ${time} 段与锁定时间重叠，无法发起预约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // ========== 使用公共函数进行地点检查 ==========
  const placeCheck = checkPlaceCommon(platform, sendname, place, "私约");
  if (!placeCheck.valid) {
    seal.replyToSender(ctx, msg, placeCheck.errorMsg);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 如果有警告信息（地点系统关闭时的提示），显示但不阻止
  if (placeCheck.warningMsg) {
    seal.replyToSender(ctx, msg, placeCheck.warningMsg);
  }
  // ========== 地点检查结束 ==========

  let b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

  // 检查发起人冲突
  let conflict = false;
  
  // 🕵️‍♂️ 检查发起人（fromKey）是否在该时间段已有确认行程冲突
  if (b_confirmedSchedule[fromKey]) {
    b_confirmedSchedule[fromKey].forEach(ev => {
      const subtype = (ev.subtype || "").toLowerCase();
      if (
        ["小群", "续杯", "私密", "电话"].includes(subtype) &&
        timeConflict(day, time, ev.day, ev.time)
      ) {
        conflict = true;
      }
    });
  }

  // ⚠️ 若发起人已有密约类安排与当前时间冲突，则终止发起
  if (conflict) {
    seal.replyToSender(ctx, msg, `⚠️ 你在 ${day} ${time} 时段已有安排，无法发起私约~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查其他冲突
  for (let toname of names) {
    const toKey = `${platform}:${a_private_group[platform][toname][0]}`;
    
    // ✅ 检查是否已被对方发过相同时间段的小群请求
    const backRequest = appointmentList.find(app =>
      app.sendid === a_private_group[platform][toname][0] &&
      app.toname === sendname &&
      app.day === day &&
      timeConflict(app.time, time)
    );

    if (backRequest) {
      seal.replyToSender(ctx, msg,
        `⚠️ ${toname} 已向你发送了一条在 ${day} ${time} 的小群请求，建议先使用"私约请求"处理`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 检查对方是否已有安排（不告诉发起人具体是什么安排）
    if (b_confirmedSchedule[toKey]) {
      let hasConflict = false;
      b_confirmedSchedule[toKey].forEach(ev => {
        if (timeConflict(day, time, ev.day, ev.time)) {
          hasConflict = true;
        }
      });
      if (hasConflict) {
        failed.push(`${toname}（该时段已有安排）`);
      }
    }

    // 检查多人邀约冲突
    for (let [ref, group] of Object.entries(b_MultiGroupRequest)) {
      if (group.day !== day || !timeOverlap(group.time, time)) continue;
      
      const sendStatus = group.targetList?.[sendname];
      if (sendStatus === "accepted" || sendStatus === null) {
        seal.replyToSender(ctx, msg,
          `⚠️ 你在 ${day} ${time} 已被邀请参与一个多人小群（状态：${sendStatus === "accepted" ? "已接受" : "待回应"}），不可重复发起该时间段小群`);
        return seal.ext.newCmdExecuteResult(true);
      }
      
      const targetStatus = group.targetList?.[toname];
      if (targetStatus === "accepted") {
        seal.replyToSender(ctx, msg,
          `⚠️ ${toname} 已接受一个多人小群邀请（${group.day} ${group.time}），但尚未建群，时间冲突无法发起单人小群`);
        return seal.ext.newCmdExecuteResult(true);
      }
    }
  }

  if (failed.length > 0) {
    seal.replyToSender(ctx, msg, `⚠️ 无法发起私约，以下对象在该时段已有安排：\n- ${failed.join("\n- ")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // ✅ 使用通用函数创建邀约和发送通知
  const result = createAndNotifyAppointment({
    ctx,
    platform,
    sendname,
    sendid: uid,
    subtype: "私密",
    day,
    time,
    place,
    names,
    isMulti,
    generateMessageFn: generatePrivateInvitationMessage
  });

  // 发送成功消息
  const successMsg = result.isMulti 
    ? `✅ 你已成功向 ${result.names.join("、")} 发起多人私密邀约`
    : `你已经悄悄给 ${result.names[0]} 发出了一条私密邀约，等他/她发现吧~`;
  
  seal.replyToSender(ctx, msg, successMsg);
    
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["私约"] = cmd_appointment_private;

// 🔧 新增：设置允许预约时间范围的指令
let cmd_set_allowed_times = seal.ext.newCmdItemInfo();
cmd_set_allowed_times.name = "设置邀约时间";
cmd_set_allowed_times.help = "。设置邀约时间 [时间段1] [时间段2] ...\n示例：。设置邀约时间 09:00-12:00 14:00-18:00";
cmd_set_allowed_times.solve = (ctx, msg, cmdArgs) => {
  let timeRanges = [];
  
  // 收集所有时间段参数
  for (let i = 1; i <= cmdArgs.args.length; i++) {
    const arg = cmdArgs.getArgN(i);
    if (arg) {
      // 验证时间格式
      if (!/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/.test(arg)) {
        seal.replyToSender(ctx, msg, `⚠️ 时间格式错误：「${arg}」\n请使用格式：HH:MM-HH:MM，如 09:00-12:00`);
        return seal.ext.newCmdExecuteResult(true);
      }
      timeRanges.push(arg);
    }
  }
  
  if (timeRanges.length === 0) {
    // 如果没有参数，显示当前设置
    const currentRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
    if (currentRanges.length === 0) {
      seal.replyToSender(ctx, msg, "📋 当前未设置允许的邀约时间段（任何时间都允许）");
    } else {
      seal.replyToSender(ctx, msg, `📋 当前允许的邀约时间段：\n${currentRanges.map(range => `· ${range}`).join('\n')}`);
    }
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 保存设置
  ext.storageSet("allowed_appointment_times", JSON.stringify(timeRanges));
  seal.replyToSender(ctx, msg, `✅ 已设置允许的邀约时间段：\n${timeRanges.map(range => `· ${range}`).join('\n')}`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置邀约时间"] = cmd_set_allowed_times;

// 🔧 新增：清空允许时间范围的指令
let cmd_clear_allowed_times = seal.ext.newCmdItemInfo();
cmd_clear_allowed_times.name = "清空邀约时间";
cmd_clear_allowed_times.help = "。清空邀约时间 - 清空所有时间限制";
cmd_clear_allowed_times.solve = (ctx, msg, cmdArgs) => {
  ext.storageSet("allowed_appointment_times", JSON.stringify([]));
  seal.replyToSender(ctx, msg, "✅ 已清空邀约时间限制，现在任何时间都允许发起邀约");
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空邀约时间"] = cmd_clear_allowed_times;


// ========================
// 📜 修改剧情信件指令 - 去掉配额，改为发送到后台群
// ========================
let cmd_send_letter_updated = seal.ext.newCmdItemInfo();
cmd_send_letter_updated.name = "剧情信件";
cmd_send_letter_updated.help = "剧情信件 内容 - 发送剧情信件到后台群";

cmd_send_letter_updated.solve = (ctx, msg, cmdArgs) => {
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    const enable_general_letter = config.enable_general_letter ?? true;
    if (!enable_general_letter) {
        seal.replyToSender(ctx, msg, "📪 剧情信件功能已被关闭，今日无人能投信于鸽羽之上。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    const sendname = Object.keys(a_private_group[platform]).find(
        key => a_private_group[platform][key][0] === uid
    );
    if (!sendname) {
        seal.replyToSender(ctx, msg, `请先创建新角色再使用该指令`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取信件内容
    const context = msg.message.match(new RegExp(`剧情信件 ([\\s\\S]+)`));
    if (!context) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    const letterContent = context[1].trim();
    if (!letterContent) {
        seal.replyToSender(ctx, msg, "信件内容不能为空");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查后台群是否设置
    const backgroundGroupId = JSON.parse(ext.storageGet("background_group_id"));
    if (!backgroundGroupId) {
        seal.replyToSender(ctx, msg, "⚠️ 管理员尚未设置后台群，无法发送剧情信件");
        return seal.ext.newCmdExecuteResult(true);
    }

    console.log(backgroundGroupId)

    // 发送到后台群
    const backgroundMsg = seal.newMessage();
    backgroundMsg.messageType = "group";
    backgroundMsg.sender = {};
    backgroundMsg.sender.userId = `${platform}:${uid}`;
    backgroundMsg.groupId = `${platform}-Group:${backgroundGroupId}`;
    const backgroundCtx = seal.createTempCtx(ctx.endPoint, backgroundMsg);

    // ✅ 发送剧情信件到后台群
    seal.replyToSender(ctx, msg, `📬 剧情信件已寄出到后台群`);
    seal.replyToSender(backgroundCtx, backgroundMsg,
        `📜 剧情信件：\n✉️ 来自「${sendname}」，\n\n${letterContent}`);

    // 记录会议计数
    recordMeetingAndAnnounce("剧情信件", platform, ctx, ctx.endPoint);
    
    return seal.ext.newCmdExecuteResult(true);
};

// 替换原来的剧情信件指令
ext.cmdMap["剧情信件"] = cmd_send_letter_updated;

// ========================
// 🛒 礼物商城指令（方案 C 重构版）
// ========================

let cmd_view_preset_gifts = seal.ext.newCmdItemInfo();
cmd_view_preset_gifts.name = "礼物商城";
cmd_view_preset_gifts.help = "礼物商城 - 随机解锁 1 个预设礼物（受游戏天数和冷却控制）";

cmd_view_preset_gifts.solve = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const userKey = `${platform}:${uid}`; // 统一使用大表 Key 格式

    // 1. 身份验证
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const sendname = Object.keys(a_private_group[platform] || {}).find(
        key => a_private_group[platform][key][0] === uid
    );
    if (!sendname) {
        seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再逛商城。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 【方案 C】冷却检查 (使用全局冷却大表)
    let globalCooldowns = JSON.parse(ext.storageGet("global_shop_cooldowns") || "{}");
    const now = Date.now();
    const cooldownDuration = 5400 * 1000; // 1.5 小时转换为毫秒

    if (now - (globalCooldowns[userKey] || 0) < cooldownDuration) {
        const remainingMin = Math.ceil((cooldownDuration - (now - globalCooldowns[userKey])) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 进货中... 商城正在整顿，请 ${remainingMin} 分钟后再来~`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 获取数据
    const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    const giftIds = Object.keys(presetGifts);
    
    if (giftIds.length === 0) {
        return seal.replyToSender(ctx, msg, "🛒 商城空空如也。");
    }

    // 4. 【方案 C】图鉴与解锁逻辑
    let giftSightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
    if (!giftSightings[userKey]) {
        giftSightings[userKey] = { unlocked_gifts: [] };
    }

    // 随机选择 1 个并解锁
    const randomIndex = Math.floor(Math.random() * giftIds.length);
    const selectedId = giftIds[randomIndex];
    const gift = presetGifts[selectedId];

    if (!giftSightings[userKey].unlocked_gifts.includes(selectedId)) {
        giftSightings[userKey].unlocked_gifts.push(selectedId);
    }

    // 5. 持久化大表数据
    globalCooldowns[userKey] = now;
    ext.storageSet("global_shop_cooldowns", JSON.stringify(globalCooldowns));
    ext.storageSet("gift_sightings", JSON.stringify(giftSightings));

    // 6. 渲染回复
    let rep = `🛒 【${sendname}】你在商城货架深处发现了一件宝贝：\n\n`;
    rep += `📦 编号：${selectedId}\n`;
    rep += `✨ 礼物：${gift.name}\n`;
    rep += `📝 内容：${gift.content}\n`;
    rep += `\n📚 目前已收集：${giftSightings[userKey].unlocked_gifts.length} / ${giftIds.length}\n`;
    rep += `💡 发送「。我的图鉴」查看所有已解锁礼物。`;

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["礼物商城"] = cmd_view_preset_gifts;

// ========================
// 📚 我的图鉴指令
// ========================

let cmd_view_my_gift_collection = seal.ext.newCmdItemInfo();
cmd_view_my_gift_collection.name = "我的图鉴";
cmd_view_my_gift_collection.help = "我的图鉴 - 查看你已解锁的所有礼物";

cmd_view_my_gift_collection.solve = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId;
    
    // 获取图鉴数据
    let giftSightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
    const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    
    if (!giftSightings[uid] || giftSightings[uid].unlocked_gifts.length === 0) {
        seal.replyToSender(ctx, msg, 
            "📚 你的图鉴空空如也~\n\n" +
            "💡 使用「礼物商城」查看并解锁新礼物\n" +
            "每次查看都会解锁新的礼物，解锁后即可赠送！"
        );
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const unlockedGifts = giftSightings[uid].unlocked_gifts;
    const totalGifts = Object.keys(presetGifts).length;
    
    let rep = `📚 【我的礼物图鉴】\n`;
    rep += `🎯 解锁进度：${unlockedGifts.length}/${totalGifts}\n\n`;
    
    // 按编号排序显示
    const sortedGiftIds = unlockedGifts.sort((a, b) => {
        const numA = parseInt(a.replace('#', '')) || 0;
        const numB = parseInt(b.replace('#', '')) || 0;
        return numA - numB;
    });
    
    // 分组显示，每5个一组
    const groups = [];
    for (let i = 0; i < sortedGiftIds.length; i += 5) {
        groups.push(sortedGiftIds.slice(i, i + 5));
    }
    
    groups.forEach((group, groupIndex) => {
        rep += `📖 第${groupIndex + 1}页：\n`;
        group.forEach(giftId => {
            const gift = presetGifts[giftId];
            if (gift) {
                const usageCount = gift.usage_count || 0;
                const starRating = usageCount > 20 ? '⭐⭐⭐⭐⭐' : 
                                  usageCount > 15 ? '⭐⭐⭐⭐' : 
                                  usageCount > 10 ? '⭐⭐⭐' : 
                                  usageCount > 5 ? '⭐⭐' : 
                                  usageCount > 0 ? '⭐' : '☆';
                rep += `  🎁 ${giftId}: ${gift.name} ${starRating}\n`;
            } else {
                rep += `  ❓ ${giftId}: 礼物已下架\n`;
            }
        });
        rep += '\n';
    });
    
    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的图鉴"] = cmd_view_my_gift_collection;

let cmd_send_gift = seal.ext.newCmdItemInfo();
cmd_send_gift.name = "送礼";
cmd_send_gift.help = "。送礼 对方角色名 礼物内容/#预设编号\n示例：\n。送礼 张三 #1\n。送礼 李四 一束玫瑰花\n使用「礼物商城」查看预设礼物";

cmd_send_gift.solve = (ctx, msg, cmdArgs) => {
  // 1. 功能开关检查
  const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
  if (!(config.enable_general_gift ?? true)) {
    seal.replyToSender(ctx, msg, "🎁 礼物功能已被禁用。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const toname = cmdArgs.getArgN(1);
  const giftInput = cmdArgs.getArgN(2);
  if (!toname || !giftInput) {
    seal.replyToSender(ctx, msg, cmd_send_gift.help);
    return seal.ext.newCmdExecuteResult(true);
  }

  const platform = msg.platform;
  const uid = msg.sender.userId.replace(`${platform}:`, "");
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  
  // 2. 身份识别
  const sendname = Object.keys(a_private_group[platform] || {}).find(
    key => a_private_group[platform][key][0] === uid
  );
  if (!sendname) {
    seal.replyToSender(ctx, msg, `❌ 请先创建新角色再使用该指令`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 3. 权限与自送检查
  const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  if (blockMap[sendname]?.enable_general_gift === false) {
    return seal.replyToSender(ctx, msg, `🎁 ${sendname} 被限制使用礼物功能。`);
  }
  if (toname === sendname) {
    return seal.replyToSender(ctx, msg, `🌸 礼不自赠，情当他寄。`);
  }
  if (!a_private_group[platform][toname]) {
    return seal.replyToSender(ctx, msg, `❌ 未找到收件人 ${toname}`);
  }

  // 4. 冷却与限次检查
  const gameDay = ext.storageGet("global_days") || "D0";
  const dailyLimit = parseInt(ext.storageGet("giftDailyLimit") || "100");
  const cooldownMin = parseInt(ext.storageGet("giftCooldown") || "30")
  
  let globalStats = JSON.parse(ext.storageGet("global_gift_stats") || "{}");
  let globalCooldowns = JSON.parse(ext.storageGet("global_gift_cooldowns") || "{}");
  const userKey = `${platform}:${uid}`;
  const now = Date.now();

  const lastSent = globalCooldowns[userKey] || 0;
  if (now - lastSent < cooldownMin * 60 * 1000) {
    const rem = Math.ceil((cooldownMin * 60 * 1000 - (now - lastSent)) / 1000);
    seal.replyToSender(ctx, msg, `⏳ 快递员仍在路上，请等待 ${rem} 秒后再送~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let userStat = globalStats[userKey] || { day: gameDay, count: 0 };
  if (userStat.day !== gameDay) userStat = { day: gameDay, count: 0 };
  if (userStat.count >= dailyLimit) {
    seal.replyToSender(ctx, msg, `🎁 今日送礼次数已达上限(${dailyLimit})。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const giftMode = parseInt(ext.storageGet("giftMode") || "0");
    if (giftMode === 1 && !giftInput.startsWith('#')) {
        seal.replyToSender(ctx, msg, "❌ 当前仅允许使用预设礼物（带 # 编号）");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (giftMode === 2 && giftInput.startsWith('#')) {
        seal.replyToSender(ctx, msg, "❌ 当前仅允许自定义礼物，不能使用预设编号");
        return seal.ext.newCmdExecuteResult(true);
    }

  // 5. 礼物内容处理（修复作用域问题）
  let giftDisplayName = "";
  let giftContent = giftInput;

  if (giftInput.startsWith('#')) {
    // 解析预设礼物数据
    let presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    const giftData = presetGifts[giftInput];
    
    if (!giftData) {
      seal.replyToSender(ctx, msg, `❌ 预设礼物 ${giftInput} 不存在`);
      return seal.ext.newCmdExecuteResult(true);
    }
    
    // 检查解锁图鉴
    const sightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
    const userUnlocked = sightings[msg.sender.userId]?.unlocked_gifts || [];
    if (!userUnlocked.includes(giftInput)) {
       seal.replyToSender(ctx, msg, `🔒 礼物 ${giftInput} 未解锁！请先去商城解锁。`);
       return seal.ext.newCmdExecuteResult(true);
    }

    giftDisplayName = `「${giftData.name}」`;
    giftContent = giftData.content;

    // 更新预设礼物使用次数（原错误位置已合并至此）
    presetGifts[giftInput].usage_count = (presetGifts[giftInput].usage_count || 0) + 1;
    ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
  } else {
    giftDisplayName = "一份特别的礼物";
    giftContent = giftInput;
  }

  // 6. 执行投递
  const targetEntry = a_private_group[platform][toname];
  const newmsg = seal.newMessage();
  newmsg.messageType = "group";
  newmsg.groupId = `${platform}-Group:${targetEntry[1]}`; 
  const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

  const recipientMsg = `🎀 ${toname}，有一份来自「${sendname}」的快递：\n礼物：${giftDisplayName}\n寄语：「${giftContent}」`;
  seal.replyToSender(newctx, newmsg, recipientMsg);

  // 7. 保存状态与回复
  userStat.count += 1;
  const currentNum = userStat.count;
  const remainingNum = dailyLimit - currentNum;

  globalStats[userKey] = userStat;
  globalCooldowns[userKey] = now;
  
  ext.storageSet("global_gift_stats", JSON.stringify(globalStats));
  ext.storageSet("global_gift_cooldowns", JSON.stringify(globalCooldowns));

  seal.replyToSender(ctx, msg, `🎁 已成功将 ${giftDisplayName} 送往「${toname}」的房间。\n(今日第 ${currentNum}份，余 ${remainingNum}份)`);

// 8. 礼物公开发送逻辑
const publicGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
const giftPublicEnabled = JSON.parse(ext.storageGet("gift_public_send") || "false");

if (giftPublicEnabled && publicGroupId) {
    // 读取公开概率，默认为 50
    const publicChance = parseInt(ext.storageGet("giftPublicChance") || "50", 10);
    const randomNum = Math.floor(Math.random() * 100) + 1; // 1-100

    if (randomNum <= publicChance) {
        // 构造群消息对象（完整字段）
        const pubMsg = seal.newMessage();
        pubMsg.messageType = "group";
        pubMsg.groupId = `${platform}-Group:${publicGroupId}`;
        pubMsg.sender = {};  // 满足接口要求

        const pubCtx = seal.createTempCtx(ctx.endPoint, pubMsg);

        // 公开消息内容（带随机数和概率信息）
        const publicNotice = `🎁 公开的礼物：\n来自「${sendname}」→「${toname}」\n送出了：${giftDisplayName}，内容：「${giftContent}」\n\n（随机数：${randomNum}，触发公开，设置概率：${publicChance}%）`;

        seal.replyToSender(pubCtx, pubMsg, publicNotice);
    }
}

  recordMeetingAndAnnounce("礼物", platform, ctx, ctx.endPoint);

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["送礼"] = cmd_send_gift;

// ========================
// 📦 管理员指令：上传预设礼物（简化版）
// ========================

let cmd_upload_preset_gift = seal.ext.newCmdItemInfo();
cmd_upload_preset_gift.name = "上传预设礼物";
cmd_upload_preset_gift.help = `用法：
1. 单个上传：上传预设礼物 编号:礼物名:礼物内容
   示例：上传预设礼物 #1:玫瑰花:一束精心包装的红色玫瑰花

2. 批量上传：上传预设礼物 礼物1$礼物2$礼物3
   示例：上传预设礼物 #1:玫瑰花:一束红玫瑰$#2:巧克力:一盒心形巧克力

3. 导出数据：上传预设礼物 导出 - 导出所有预设礼物数据`;

cmd_upload_preset_gift.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const inputArg = cmdArgs.getArgN(1).trim();
    if (!inputArg) {
        seal.replyToSender(ctx, msg, 
            "❌ 请输入参数\n" +
            "格式1（单个）：编号:礼物名:礼物内容\n" +
            "格式2（批量）：礼物1$礼物2$礼物3\n" +
            "格式3（导出）：上传预设礼物 导出");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 导出功能
    if (inputArg === "导出") {
        const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
        if (Object.keys(presetGifts).length === 0) {
            seal.replyToSender(ctx, msg, "📭 当前没有预设礼物数据");
            return seal.ext.newCmdExecuteResult(true);
        }
        
        const exportData = JSON.stringify(presetGifts, null, 2);
        seal.replyToSender(ctx, msg, `📦 当前预设礼物数据：\n\`\`\`json\n${exportData}\n\`\`\``);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取现有礼物数据
    let presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");

    let results = {
        success: 0,
        failed: 0,
        details: []
    };

    // 判断是批量上传还是单个上传
    const giftItems = inputArg.includes('$') ? inputArg.split('$') : [inputArg];
    
    for (const giftItem of giftItems) {
        const item = giftItem.trim();
        if (!item) continue;

        // 解析单个礼物参数
        const parts = item.split(':');
        if (parts.length < 3) {
            results.details.push(`❌ 格式错误: ${item} (需要冒号分隔三部分)`);
            results.failed++;
            continue;
        }

        const giftId = parts[0].trim();
        const giftName = parts[1].trim();
        let giftContent = parts.slice(2).join(':').trim();

        // 验证编号格式
        if (!giftId.startsWith('#')) {
            results.details.push(`❌ 编号错误: ${giftId} (必须以#开头)`);
            results.failed++;
            continue;
        }

        // 验证内容
        if (!giftName || !giftContent) {
            results.details.push(`❌ 内容为空: ${giftId} (名称和内容不能为空)`);
            results.failed++;
            continue;
        }

        // 检查是否已存在
        if (presetGifts[giftId]) {
            results.details.push(`🔄 已存在: ${giftId} (${giftName}) - 已更新`);
        } else {
            results.details.push(`✅ 新增: ${giftId} (${giftName})`);
        }

        // 创建或更新礼物
        if (presetGifts[giftId]) {
            // 更新现有礼物
            presetGifts[giftId] = {
                ...presetGifts[giftId],
                name: giftName,
                content: giftContent,
                updated_at: new Date().toLocaleString("zh-CN")
            };
        } else {
            // 添加新礼物
            presetGifts[giftId] = {
                name: giftName,
                content: giftContent,
                created_at: new Date().toLocaleString("zh-CN"),
                usage_count: 0
            };
        }
        results.success++;
    }

    // 保存到存储
    if (results.success > 0) {
        ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
    }

    // 构建回复
    let rep = "";
    if (giftItems.length > 1) {
        rep += `📦 批量上传完成 (${giftItems.length}个)\n`;
        rep += `✅ 成功: ${results.success}个\n`;
        rep += `❌ 失败: ${results.failed}个\n`;
        rep += `📊 当前总计: ${Object.keys(presetGifts).length}个预设礼物\n\n`;
    }

    if (results.details.length > 0) {
        if (giftItems.length <= 3) {
            // 少量礼物时显示详细结果
            rep += "📋 处理详情：\n";
            results.details.forEach(detail => {
                rep += `  ${detail}\n`;
            });
        } else {
            // 大量礼物时只显示概要
            rep += "📋 前3项处理详情：\n";
            for (let i = 0; i < Math.min(3, results.details.length); i++) {
                rep += `  ${results.details[i]}\n`;
            }
            if (results.details.length > 3) {
                rep += `  ...等${results.details.length}项\n`;
            }
        }
    }

    // 如果没有成功项，添加提示
    if (results.success === 0) {
        rep += "\n💡 提示：批量上传时使用 $ 分隔多个礼物\n" +
               "示例：#1:礼物名:礼物内容$#2:礼物名:礼物内容";
    }

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传预设礼物"] = cmd_upload_preset_gift;

// ========================
// 🗑️ 管理员指令：删除预设礼物
// ========================

let cmd_delete_preset_gift = seal.ext.newCmdItemInfo();
cmd_delete_preset_gift.name = "删除预设礼物";
cmd_delete_preset_gift.help = `用法：
1. 删除单个：删除预设礼物 编号
   示例：删除预设礼物 #1

2. 批量删除：删除预设礼物 编号1,编号2,编号3
   示例：删除预设礼物 #1,#2,#3

3. 删除所有：删除预设礼物 全部 (⚠️危险操作)`;

cmd_delete_preset_gift.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const giftIds = cmdArgs.getArgN(1);
    if (!giftIds) {
        seal.replyToSender(ctx, msg, "请指定要删除的礼物编号，多个编号用逗号分隔");
        return seal.ext.newCmdExecuteResult(true);
    }

    let presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    let giftSightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");

    // 检查是否要删除全部
    if (giftIds.trim() === "全部") {
        // 确认操作
        const confirmArg = cmdArgs.getArgN(2);
        if (confirmArg !== "确认") {
            seal.replyToSender(ctx, msg, 
                "⚠️ 危险操作：这将删除所有预设礼物！\n" +
                "如需继续，请输入：删除预设礼物 全部 确认\n" +
                `当前共有 ${Object.keys(presetGifts).length} 个预设礼物`);
            return seal.ext.newCmdExecuteResult(true);
        }

        // 清空所有图鉴数据
        for (const userId in giftSightings) {
            giftSightings[userId].unlocked_gifts = [];
        }
        ext.storageSet("gift_sightings", JSON.stringify(giftSightings));
        
        const totalCount = Object.keys(presetGifts).length;
        presetGifts = {};
        ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
        
        seal.replyToSender(ctx, msg, `✅ 已删除全部 ${totalCount} 个预设礼物，并清空了所有玩家的图鉴记录`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 解析要删除的编号列表
    const idsToDelete = giftIds.split(',').map(id => id.trim()).filter(id => id);
    
    let deletedCount = 0;
    let notFoundCount = 0;
    let removedFromSightings = 0;
    let resultDetails = [];

    for (const giftId of idsToDelete) {
        if (!presetGifts[giftId]) {
            resultDetails.push(`❌ 未找到: ${giftId}`);
            notFoundCount++;
            continue;
        }

        const giftName = presetGifts[giftId].name;
        
        // 从图鉴数据中移除这个礼物
        let userRemoved = 0;
        for (const userId in giftSightings) {
            const unlockedGifts = giftSightings[userId].unlocked_gifts || [];
            const index = unlockedGifts.indexOf(giftId);
            if (index !== -1) {
                unlockedGifts.splice(index, 1);
                giftSightings[userId].unlocked_gifts = unlockedGifts;
                userRemoved++;
            }
        }
        
        // 删除礼物本身
        delete presetGifts[giftId];
        deletedCount++;
        removedFromSightings += userRemoved;
        
        resultDetails.push(`✅ 已删除: ${giftId} (${giftName}) - 从 ${userRemoved} 位玩家图鉴中移除`);
    }

    // 保存更改
    if (deletedCount > 0) {
        ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
        ext.storageSet("gift_sightings", JSON.stringify(giftSightings));
    }

    // 构建回复
    let rep = "";
    if (idsToDelete.length > 1) {
        rep += `🗑️ 批量删除完成\n`;
        rep += `✅ 成功删除: ${deletedCount}个\n`;
        rep += `❌ 未找到: ${notFoundCount}个\n`;
        rep += `👥 从玩家图鉴移除总计: ${removedFromSightings}次\n\n`;
        
        if (deletedCount > 0) {
            rep += "📋 处理详情：\n";
            resultDetails.forEach(detail => {
                rep += `  ${detail}\n`;
            });
        }
    } else {
        // 单个删除
        if (deletedCount > 0) {
            rep = resultDetails[0];
        } else {
            rep = `❌ 未找到编号为 ${giftIds} 的预设礼物`;
        }
    }

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除预设礼物"] = cmd_delete_preset_gift;

// 添加群号
let cmd_add_group = seal.ext.newCmdItemInfo();
cmd_add_group.name = "添加群号";
cmd_add_group.help = "。添加群号 群号（多个用逗号隔开）";
cmd_add_group.solve = (ctx, msg, cmdArgs) => {
    let temp = isUserAdmin(ctx, msg);
    if (!msg.isMaster && !temp) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let grouplist = cmdArgs.getArgN(1);
    if (!grouplist) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    grouplist = grouplist.replace(/，/g, ",").split(",");
    let group = JSON.parse(ext.storageGet("group") || "[]");
    for (let i = 0; i < grouplist.length; i++) {
        if (/^[0-9]+$/.test(grouplist[i]) && !group.includes(grouplist[i])) {
            group.push(grouplist[i]);
        }
    }

    ext.storageSet("group", JSON.stringify(group));
    seal.replyToSender(ctx, msg, `✅ 已添加群号，当前可用共 ${group.length} 个。`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["添加群号"] = cmd_add_group;

// 查看群号
let cmd_show_group = seal.ext.newCmdItemInfo();
cmd_show_group.name = "查看群号";
cmd_show_group.help = "。查看群号";
cmd_show_group.solve = (ctx, msg, cmdArgs) => {
    let temp = isUserAdmin(ctx, msg);
    if (!msg.isMaster && !temp) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let group = JSON.parse(ext.storageGet("group") || "[]");
    let rep = `📜 当前可用群号（共 ${group.length} 个）：\n`;
    for (let i = 0; i < group.length; i++) {
        rep += `• ${group[i]}\n`;
    }

    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["查看群号"] = cmd_show_group;

// 移除群号
let cmd_remove_group = seal.ext.newCmdItemInfo();
cmd_remove_group.name = "移除群号";
cmd_remove_group.help = "。移除群号 群号（多个用逗号隔开）";
cmd_remove_group.solve = (ctx, msg, cmdArgs) => {
    let temp = isUserAdmin(ctx, msg);
    if (!msg.isMaster && !temp) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let grouplist = cmdArgs.getArgN(1);
    if (!grouplist) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    grouplist = grouplist.replace(/，/g, ",").split(",");
    let group = JSON.parse(ext.storageGet("group") || "[]");
    for (let i = 0; i < grouplist.length; i++) {
        let idx = group.indexOf(grouplist[i]);
        if (idx !== -1) group.splice(idx, 1);
    }

    ext.storageSet("group", JSON.stringify(group));
    seal.replyToSender(ctx, msg, `✅ 指定群号已移除，当前可用共 ${group.length} 个。`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["移除群号"] = cmd_remove_group;


let cmd_admin_view_active = seal.ext.newCmdItemInfo();
cmd_admin_view_active.name = "查看进行中";
cmd_admin_view_active.help = "。查看进行中 D几（管理员查看未结束的已确认邀约，仅显示类型与群号）";

cmd_admin_view_active.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  const dayArg = cmdArgs.getArgN(1);
  if (!dayArg || !/^D\d+$/.test(dayArg)) {
    seal.replyToSender(ctx, msg, "请输入正确的天数，例如：。查看进行中 D1");
    return seal.ext.newCmdExecuteResult(true);
  }

  const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

  // 以 group 为唯一键，防止重复
  const groupMap = {};

  for (const uid in b_confirmedSchedule) {
    for (const ev of b_confirmedSchedule[uid]) {
      if (
        ev.day === dayArg &&
        ev.status !== "ended" &&
        ev.group
      ) {
        if (!groupMap[ev.group]) {
          groupMap[ev.group] = ev.subtype || "未知";
        }
      }
    }
  }

  const entries = Object.entries(groupMap);
  if (entries.length === 0) {
    seal.replyToSender(ctx, msg, `📭 ${dayArg} 当前没有进行中的邀约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let reply = `📌 ${dayArg} 进行中的邀约：\n\n`;
  entries.forEach(([group, subtype], idx) => {
    reply += `${idx + 1}️⃣ ${subtype} ｜ 群号：${group}\n`;
  });

  seal.replyToSender(ctx, msg, reply.trim());
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["查看进行中"] = cmd_admin_view_active;

let cmd_grouplist_release = seal.ext.newCmdItemInfo();
cmd_grouplist_release.name = "结束私约";
cmd_grouplist_release.help = "。结束私约（将当前群标记为结束状态，禁止当前阶段续杯）";

cmd_grouplist_release.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)){
    seal.replyToSender(ctx, msg, `该指令仅限骰主使用`);
    return seal.ext.newCmdExecuteResult(true);
  }
  let group = JSON.parse(ext.storageGet("group") || "[]");

  let platform = msg.platform;
  let gid = msg.groupId.replace(`${platform}-Group:`, "");

  const fullId = `${gid}_占用`;

  if (group.includes(fullId)) {
    // ✅ 将占用状态移除，使该群可复用
    group.splice(group.indexOf(fullId), 1);
    group.push(gid); // 标记为"可复用"
    ext.storageSet("group", JSON.stringify(group));

    // ✅ 更新 b_confirmedSchedule 中所有 status 为 ended
    const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    let modified = false;
    let matchCount = 0;

    for (let uid in b_confirmedSchedule) {
      for (let ev of b_confirmedSchedule[uid]) {
        if (ev.group === gid && ev.status !== "ended") {
          ev.status = "ended";
          modified = true;
          matchCount++;
        }
      }
    }

    if (modified) {
      ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    }

    // 🆕 清除到期记录
    let groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
    if (groupExpireInfo[gid]) {
      delete groupExpireInfo[gid];
      ext.storageSet("group_expire_info", JSON.stringify(groupExpireInfo));
      console.log(`[DEBUG] 已清除群组 ${gid} 的到期记录`);
    }

    console.log(`[DEBUG] ${gid} 标记为 ended，更新 ${matchCount} 条记录`);
    seal.replyToSender(ctx, msg, `✅ 本群（${gid}）本轮小群已结束，可再次发起新小群，所有相关记录已标记"已结束"`);
    setGroupName(ctx, msg, ctx.group.groupId, `备用`)   
    cleanupGroupTimer(gid)
    
  } else {
    seal.replyToSender(ctx, msg, `⚠️ 当前群号未处于占用状态，无法结束`);
  }

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["结束私约"] = cmd_grouplist_release;

let cmd_view_requests = seal.ext.newCmdItemInfo();
cmd_view_requests.name = "私约请求列表";
cmd_view_requests.help = "。私约请求 —— 查看你收到的所有私约、发起邀约与赠礼";

cmd_view_requests.solve = (ctx, msg) => {
  const uid = msg.sender.userId;
  const platform = msg.platform;
  const appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");

  // --- 1. 处理收到的请求 (保持逻辑，按人头显示) ---
  let received = appointmentList.filter(item => 
    `${platform}:${item.toid}` === uid && item.type === "小群"
  ).filter(item => {
    if (item.groupRef && b_MultiGroupRequest[item.groupRef]) {
      return b_MultiGroupRequest[item.groupRef].targetList?.[item.toname] === null;
    }
    return true; 
  });

  // --- 2. 处理发出的请求 (修复重复显示 Bug) ---
  let rawSent = appointmentList.filter(item => 
    `${platform}:${item.sendid}` === uid && item.type === "小群"
  ).filter(item => {
    if (item.groupRef && b_MultiGroupRequest[item.groupRef]) {
      return b_MultiGroupRequest[item.groupRef].targetList?.[item.toname] === null;
    }
    return true;
  });

  // 使用 Map 进行去重：如果 groupRef 相同，视为同一个邀约事件
  let sentMap = new Map();
  rawSent.forEach(item => {
    const key = item.groupRef || `single_${item.day}_${item.time}_${item.toname}`;
    if (!sentMap.has(key)) {
      sentMap.set(key, item);
    }
  });
  let sent = Array.from(sentMap.values());

  // --- 3. 空列表检查 ---
  if (received.length === 0 && sent.length === 0) {
    seal.replyToSender(ctx, msg, "✨【通知中心】\n\n当前暂无待处理的邀约请求。");
    return seal.ext.newCmdExecuteResult(true);
  }

  let rep = "📱 ─── 邀约中心 ─── 📱\n\n";

  // --- 📬 收到的请求区 ---
  if (received.length > 0) {
    rep += "┏━━━  📥 待处理请求  ━━━\n";
    received.forEach((item, index) => {
      const isMulti = !!item.groupRef;
      rep += `┃ [ ${index + 1} ] ${isMulti ? '👥 多人邀约' : '📩 个人私约'}\n`;
      rep += `┃ ┈┈┈┈┈┈┈┈┈┈┈┈\n`;
      rep += `┃ 🏷️ 形式：${item.subtype}\n`;
      rep += `┃ 📅 时间：${item.day} ${item.time}\n`;
      rep += `┃ 📍 地点：${item.place}\n`;
      rep += `┃ 👤 来自：${item.sendname}\n`;
      if (isMulti) {
        const group = b_MultiGroupRequest[item.groupRef];
        let others = group ? Object.keys(group.targetList).filter(name => name !== item.toname) : [];
        if (others.length > 0) rep += `┃ 👥 同行：${others.join("、")}\n`;
      }
      rep += `┃\n`; 
    });
    rep += "┗━━━━━━━━━━━━━━\n";
    rep += "💡 指令：。接受/拒绝 序号\n\n";
  }

  // --- 📤 发出的请求区 ---
  if (sent.length > 0) {
    rep += "┏━━━  📤 已发出申请  ━━━\n";
    sent.forEach((item, i) => {
      const isMulti = !!item.groupRef;
      rep += `┃ [ ID: S${i + 1} ] ${item.subtype}\n`;
      rep += `┃ 🕒 计划：${item.day} ${item.time}\n`;
      rep += `┃ 📍 地点：${item.place}\n`;
      
      if (isMulti) {
        const group = b_MultiGroupRequest[item.groupRef];
        // 动态获取该多人邀约下的所有目标成员
        let targets = group ? Object.keys(group.targetList) : [item.toname];
        rep += `┃ 🎯 目标：${targets.join("、")}\n`;
      } else {
        rep += `┃ 🎯 对象：${item.toname}\n`;
      }
      rep += `┃\n`;
    });
    rep += "┗━━━━━━━━━━━━━━\n";
    rep += "💡 指令：。撤销 S序号\n";
  }

  rep += "\n─── END OF LIST ───";
  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["私约请求"] = cmd_view_requests;

function cleanupConflictsAndNotify(platform, toid, toname, day, time, ctx, msg) {
    const myId = `${platform}:${toid}`;
    const allAppointments = JSON.parse(ext.storageGet("appointmentList") || "[]");
    const a_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  
    let updatedAppointments = [];
    let removedCount = 0;
    const notifyRefused = [];
  
    for (let req of allAppointments) {
      if (`${platform}:${req.toid}` !== myId) {
        updatedAppointments.push(req);
        continue;
      }
  
      if (req.day !== day || !timeOverlap(req.time, time)) {
        updatedAppointments.push(req);
        continue;
      }

      if (req.type === "礼物") {
        updatedAppointments.push(req);
        continue;
      }
  
      if (req.groupRef && a_MultiGroupRequest[req.groupRef]) {
        const group = a_MultiGroupRequest[req.groupRef];
        if (req.toname === toname && group.targetList[toname] === null) {
          group.targetList[toname] = "refused";
          notifyRefused.push({
            ref: req.groupRef,
            sendid: group.sendid,
            toname,
            day: group.day,
            time: group.time,
            place: group.place
          });
          console.log(`[清理冲突] 从多人请求 ${req.groupRef} 中移除了 ${toname}`);
          continue;
        }
        updatedAppointments.push(req);
        continue;
      }
      removedCount++;
    }
  
    ext.storageSet("appointmentList", JSON.stringify(updatedAppointments));
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(a_MultiGroupRequest));
  
    console.log(`[清理冲突] 正在处理 ${toname} 接受 ${day} ${time}，共移除 ${removedCount} 点对点，标记拒绝 ${notifyRefused.length} 多人请求`);
  
    // 🔔 通知逻辑：改为使用 WebSocket 发送
    for (let n of notifyRefused) {
      const targetGroupIdRaw = a_private_group[platform]?.[n.toname]?.[1];
      if (!targetGroupIdRaw) {
        console.log(`[❗️通知失败] 找不到 ${n.toname} 的绑定群，跳 skipped`);
        continue;
      }

      // 提取纯数字群号
      const cleanGid = parseInt(targetGroupIdRaw.toString().replace(/[^\d]/g, ""), 10);
      
      const notice = `📜 ${n.toname} 的时间被占用，无法进行你的约会：
          🕒 时间：${n.day} ${n.time}
          📍 地点：${n.place}`;

      // 构造 WS 请求体
      const postData = {
        "action": "send_group_msg",
        "params": {
          "group_id": cleanGid,
          "message": notice
        }
      };

      try {
        console.log(`[WS通知] 发起人:${n.sendid} -> 群:${cleanGid}`);
        // 调用脚本内定义的 ws 函数
        ws(postData, ctx, msg, ""); 
      } catch (e) {
        console.error(`[WS通知失败] ${e.message}`);
      }
    }
  
    return {
      removedCount,
      refusedCount: notifyRefused.length
    };
}

let cmd_accept_request = seal.ext.newCmdItemInfo();
cmd_accept_request.name = "接受";
cmd_accept_request.help = "。接受 序号";

cmd_accept_request.solve = (ctx, msg, cmdArgs) => {
  try {
    const platform = msg.platform;
    const userId = msg.sender.userId;
    const index = parseInt(cmdArgs.getArgN(1));

    // 统一读取私密群映射（a_private_group）
    const privateGroups = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 读取待办请求
    let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");

    // 🗂️ 获取所有发给本角色的请求
    const myRequests = appointmentList.filter(item => `${platform}:${item.toid}` === userId);
    if (isNaN(index) || index < 1 || index > myRequests.length) {
      seal.replyToSender(ctx, msg, "请输入有效的请求编号");
      return seal.ext.newCmdExecuteResult(true);
    }

    const item = myRequests[index - 1];

    // 小工具：去平台前缀并转成字符串
    const stripUid = (u) => String(u || "").replace(`${platform}:`, "");
    // 小工具：安全取角色 UID / groupId
    const getRoleUid = (name) => privateGroups?.[platform]?.[name]?.[0];
    const getRoleGroupId = (name) => privateGroups?.[platform]?.[name]?.[1];

    // 👥 多人小群分支（存在 groupRef）
    if (item.groupRef) {
      const raw = ext.storageGet("b_MultiGroupRequest") || "{}";
      console.log("📦 当前 b_MultiGroupRequest 原始数据：", raw);

      const b_MultiGroupRequest = JSON.parse(raw);
      console.log(`🔍 查找 groupRef: ${item.groupRef}`);

      const group = b_MultiGroupRequest[item.groupRef];
      if (!group) {
        console.log(`⚠️ 未找到 groupRef: ${item.groupRef}，可能已被撤回`);
        seal.replyToSender(ctx, msg, "请求已失效，可能已被撤回");
        return seal.ext.newCmdExecuteResult(true);
      }

      console.log(`✅ groupRef ${item.groupRef} 对应结构如下：`, JSON.stringify(group, null, 2));

      // ⚠️ 已回应校验
      const currentStatus = group.targetList?.[item.toname];
      if (currentStatus === "accepted") {
        seal.replyToSender(ctx, msg, "⚠️ 你已接受该请求，无需重复操作");
        return seal.ext.newCmdExecuteResult(true);
      }
      if (currentStatus === "refused") {
        seal.replyToSender(ctx, msg, "⚠️ 你已拒绝该请求，无法再接受");
        return seal.ext.newCmdExecuteResult(true);
      }

      // 为当前单人请求生成唯一ID（用于排除自身检查）
      const currentAppointmentId = `${platform}:${group.sendid}:${item.toid}:${group.day}:${group.time}`;

      // 统一的冲突检查 - 添加排除参数
      const myConflicts = checkAcceptanceConflicts(platform, item.toid, item.toname, group.day, group.time, item.groupRef, currentAppointmentId);
      const senderConflicts = checkAcceptanceConflicts(platform, group.sendid, group.sendname, group.day, group.time, item.groupRef, currentAppointmentId);
      
      // 检查接受者冲突
      if (myConflicts.length > 0) {
        const conflictMsg = myConflicts.map(conflict => `• ${conflict}`).join('\n');
        seal.replyToSender(ctx, msg, `⚠️ 你无法接受该请求，原因如下：\n${conflictMsg}`);
        return seal.ext.newCmdExecuteResult(true);
      }
      
      // 检查发起者冲突
      if (senderConflicts.length > 0) {
        const conflictMsg = senderConflicts.map(conflict => `• ${conflict}`).join('\n');
        seal.replyToSender(ctx, msg, `⚠️ 发起人无法继续此请求，原因如下：\n${conflictMsg}`);
        return seal.ext.newCmdExecuteResult(true);
      }

      // ✅ 标记为已接受，移除该请求记录
      if (!group.targetList) group.targetList = {};
      group.targetList[item.toname] = "accepted";
      appointmentList = appointmentList.filter(i => i !== item);
      ext.storageSet("appointmentList", JSON.stringify(appointmentList));
      cleanupConflictsAndNotify(platform, item.toid, item.toname, group.day, group.time, ctx, msg);
      ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));

      // 📦 回应统计
      const allResponded = Object.values(group.targetList || {}).every(v => v !== null);
      const acceptedList = Object.entries(group.targetList || {}).filter(([_, v]) => v === "accepted");

      if (allResponded && acceptedList.length > 0) {
        // 分配群号
        const groupList = JSON.parse(ext.storageGet("group") || "[]");
        const available = groupList.filter(g => !g.endsWith("_占用"));
        if (available.length === 0) {
          seal.replyToSender(ctx, msg, "暂无可用小群群号，请稍后再试");
          return seal.ext.newCmdExecuteResult(true);
        }

        const gid = available[Math.floor(Math.random() * available.length)];
        groupList.splice(groupList.indexOf(gid), 1);
        groupList.push(gid + "_占用");
        ext.storageSet("group", JSON.stringify(groupList));

        // 🕯️ 组群前检查地点"是否有人"（不阻断）
        const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

        // 先构造"本次小群所有参与者"的 UID 集合（发起人 + 已接受）
        const roleUidList = [
          stripUid(group.sendid),
          ...acceptedList
            .map(([name]) => stripUid(getRoleUid(name)))
            .filter(Boolean)
        ];

        let placeConflict = false;

        for (const key of Object.keys(b_confirmedSchedule || {})) {
          // 排除本次参与者自身
          if (roleUidList.includes(stripUid(key))) continue;

          for (const ev of (b_confirmedSchedule[key] || [])) {
            if (ev.day === group.day && ev.place === group.place && timeOverlap(group.time, ev.time)) {
              placeConflict = true;
              break;
            }
          }
          if (placeConflict) break;
        }

        // 在分配群号后添加接受时间记录
        const acceptTime = Date.now();
        // 读取小群过期时间配置（默认为48小时）
        const expireHours = parseInt(ext.storageGet("group_expire_hours") || "48");
        const expireTime = acceptTime + expireHours * 60 * 60 * 1000;

        // 格式化时间显示
        const formatTime = (timestamp) => {
            return new Date(timestamp).toLocaleString("zh-CN", {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        };

        // 📖 记录已确认日程
        const allNames = [group.sendname, ...acceptedList.map(([name]) => name)];
        for (const name of allNames) {
          const roleUid = name === group.sendname ? group.sendid : getRoleUid(name);
          if (!roleUid) continue;
          const key = `${platform}:${stripUid(roleUid)}`;
          if (!b_confirmedSchedule[key]) b_confirmedSchedule[key] = [];
          b_confirmedSchedule[key].push({
            day: group.day,
            time: group.time,
            partner: "多人小群",
            subtype: group.subtype,
            place: group.place,
            group: gid,
            status: "active"
          });
        }

        // 记录群组信息
        let groupInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
        groupInfo[gid] = {
            acceptTime: acceptTime,
            expireTime: expireTime,
            participants: allNames,
            subtype: group.subtype,
            day: group.day,
            time: group.time,
            place: group.place
        };
        ext.storageSet("group_expire_info", JSON.stringify(groupInfo));

         // 在群内公告中添加结束时间提示
        const expireNotice = `⏰ 本群将在 ${formatTime(expireTime)} 自动结束（${expireHours}小时有效期）`;

        // 修改发送给玩家的通知，也添加结束时间
        const groupNotice =
            `你已被纳入小群：${group.subtype} ${group.day} ${group.time} @${group.place}\n` +
            `群号：${gid}\n参与者：${[group.sendname, ...acceptedList.map(([n]) => n)].join("、")}\n\n${expireNotice}`;


        for (const name of [group.sendname, ...acceptedList.map(([n]) => n)]) {
          const ug = getRoleUid(name);
          const gidBind = getRoleGroupId(name);
          if (ug && gidBind) {
            const msgNotice = seal.newMessage();
            msgNotice.messageType = "group";
            msgNotice.sender = {};
            msgNotice.sender.userId = `${platform}:${ug}`;
            msgNotice.groupId = `${platform}-Group:${gidBind}`;
            const ctxNotice = seal.createTempCtx(ctx.endPoint, msgNotice);
            seal.replyToSender(ctxNotice, msgNotice, groupNotice);
          }
        }

        // 🧾 最终群内公告
        const finalGroupMsg = seal.newMessage();
        finalGroupMsg.messageType = "group";
        finalGroupMsg.sender = {};
        finalGroupMsg.sender.userId = `${platform}:${group.sendid}`;
        finalGroupMsg.groupId = `${platform}-Group:${gid}`;
        const finalCtx = seal.createTempCtx(ctx.endPoint, finalGroupMsg);

        // 修改群内公告
        seal.replyToSender(finalCtx, finalGroupMsg,
            `🎉 小群创建成功：\n${group.subtype} ${group.day} ${group.time} @${group.place}\n参与者：${[group.sendname, ...acceptedList.map(([n]) => n)].join("、")}\n\n${expireNotice}`);

        setGroupName(finalCtx, finalGroupMsg, finalCtx.group.groupId, `${group.subtype} ${group.day} ${group.time} @${group.place}多人`)   
        
        triggerSightingCheck(platform, group.day, group.time, group.place, 
            [group.sendname, ...acceptedList.map(([n]) => n)], gid, group.subtype);

        // 🧹 清理与落盘
        delete b_MultiGroupRequest[item.groupRef];
        ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
        ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
        recordMeetingAndAnnounce(group.subtype, platform, ctx, ctx.endPoint);

        for (const name of [group.sendname, ...acceptedList.map(([n]) => n)]) {
          const roleUid = name === group.sendname ? group.sendid : getRoleUid(name);
          if (roleUid) cleanupConflictsAndNotify(platform, roleUid, name, group.day, group.time, ctx, msg);
        }

        if (group.subtype) {
            const allParticipants = [group.sendname, ...acceptedList.map(([n]) => n)];
            initGroupTimer(platform, gid, group.subtype, allParticipants, group.sendname);
        }

        return seal.ext.newCmdExecuteResult(true);
      } else {
        // 🔔 尚未全部回应，提示
        const acceptedNames = Object.entries(group.targetList || {}).filter(([_, v]) => v === "accepted").map(([n]) => n);
        const pendingNames = Object.entries(group.targetList || {}).filter(([_, v]) => v === null).map(([n]) => n);
        let hint = `你已接受该小群请求`;
        if (acceptedNames.length > 1) hint += `，目前已接受者：${acceptedNames.join("、")}`;
        if (pendingNames.length > 0) hint += `，待回应：${pendingNames.join("、")}`;
        seal.replyToSender(ctx, msg, hint + `。`);

        const sendGroupId = getRoleGroupId(item.sendname);
        if (sendGroupId) {
          const msgToInitiator = seal.newMessage();
          msgToInitiator.messageType = "group";
          msgToInitiator.sender = {};
          msgToInitiator.sender.userId = `${platform}:${item.sendid}`;
          msgToInitiator.groupId = `${platform}-Group:${sendGroupId}`;
          const ctxToInitiator = seal.createTempCtx(ctx.endPoint, msgToInitiator);
          seal.replyToSender(ctxToInitiator, msgToInitiator, `${item.toname} 接受了你的多人小群请求，等待其他人回应~`);
        }

        return seal.ext.newCmdExecuteResult(true);
      }
    }

    // 🧑‍🤝‍🧑 单人小群分支
    if (item.type === "小群") {
      // 为当前单人请求生成唯一ID（用于排除自身检查）
      const currentAppointmentId = `${platform}:${item.sendid}:${item.toid}:${item.day}:${item.time}`;

      // 统一的冲突检查 - 添加排除参数
      const myConflicts = checkAcceptanceConflicts(platform, item.toid, item.toname, item.day, item.time, null, currentAppointmentId);
      const senderConflicts = checkAcceptanceConflicts(platform, item.sendid, item.sendname, item.day, item.time, null, currentAppointmentId);
      
      // 检查接受者冲突
      if (myConflicts.length > 0) {
        const conflictMsg = myConflicts.map(conflict => `• ${conflict}`).join('\n');
        seal.replyToSender(ctx, msg, `⚠️ 你无法接受该请求，原因如下：\n${conflictMsg}`);
        return seal.ext.newCmdExecuteResult(true);
      }
      
      // 检查发起者冲突
      if (senderConflicts.length > 0) {
        const conflictMsg = senderConflicts.map(conflict => `• ${conflict}`).join('\n');
        seal.replyToSender(ctx, msg, `⚠️ 发起人无法继续此请求，原因如下：\n${conflictMsg}`);
        return seal.ext.newCmdExecuteResult(true);
      }

      const groupList = JSON.parse(ext.storageGet("group") || "[]");
      const groupFree = groupList.filter(g => !g.endsWith("_占用"));
      if (groupFree.length === 0) {
        seal.replyToSender(ctx, msg, "现在暂无可调用的群号，请稍后再试");
        return seal.ext.newCmdExecuteResult(true);
      }

      const gid = groupFree[Math.floor(Math.random() * groupFree.length)];
      groupList.splice(groupList.indexOf(gid), 1);
      groupList.push(gid + "_占用");
      ext.storageSet("group", JSON.stringify(groupList));

      // 在单人小群分支的分配群号后添加
      const acceptTime = Date.now();
      // 读取小群过期时间配置（默认为48小时）
      const expireHours = parseInt(ext.storageGet("group_expire_hours") || "48");
      const expireTime = acceptTime + expireHours * 60 * 60 * 1000;

      // 记录群组信息
      let groupInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
      groupInfo[gid] = {
          acceptTime: acceptTime,
          expireTime: expireTime,
          participants: [item.sendname, item.toname],
          subtype: item.subtype,
          day: item.day,
          time: item.time,
          place: item.place
      };
      ext.storageSet("group_expire_info", JSON.stringify(groupInfo));

      // 格式化时间
      const formatTime = (timestamp) => {
          return new Date(timestamp).toLocaleString("zh-CN", {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit'
          });
      };

      const expireNotice = `⏰ 本群将在 ${formatTime(expireTime)} 自动结束（${expireHours}小时有效期）`;

      // 修改通知消息
      let rep = `你接受了来自${item.sendname}的一对一小群请求，分配群号为 ${gid}\n\n${expireNotice}`;
      let send = `${item.toname}接受了你的一对一小群请求，分配群号为 ${gid}\n\n${expireNotice}`;

      const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

      // 落盘双方日程
      for (const who of [item.sendid, item.toid]) {
        const key = `${platform}:${stripUid(who)}`;
        if (!b_confirmedSchedule[key]) b_confirmedSchedule[key] = [];
        b_confirmedSchedule[key].push({
          day: item.day,
          time: item.time,
          partner: (who === item.sendid ? item.toname : item.sendname),
          subtype: item.subtype,
          group: gid,
          place: item.place,
          status: "active"
        });
      }
      ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
      recordMeetingAndAnnounce(item.subtype, platform, ctx, ctx.endPoint);

      // 移除该请求
      appointmentList = appointmentList.filter(i => i !== item);
      ext.storageSet("appointmentList", JSON.stringify(appointmentList));

      // 清理冲突并通知
      cleanupConflictsAndNotify(platform, item.toid, item.toname, item.day, item.time, ctx, msg);
      cleanupConflictsAndNotify(platform, item.sendid, item.sendname, item.day, item.time, ctx, msg);
      seal.replyToSender(ctx, msg, rep);

      // 群内公告
      const notice = seal.newMessage();
      notice.messageType = "group";
      notice.sender = {};
      notice.sender.userId = `${platform}:${item.sendid}`;
      notice.groupId = `${platform}-Group:${gid}`;
      const noticeCtx = seal.createTempCtx(ctx.endPoint, notice);
      // 修改群内公告
      seal.replyToSender(noticeCtx, notice,
          `小群创建成功：${item.subtype} ${item.day} ${item.time} ${item.place} ${item.sendname}&${item.toname}\n\n${expireNotice}`)
      setGroupName(noticeCtx, notice, noticeCtx.group.groupId, `${item.subtype} ${item.day} ${item.time} ${item.place} ${item.sendname}&${item.toname}`)

      // 触发目击检查
      triggerSightingCheck(platform, item.day, item.time, item.place, 
          [item.sendname, item.toname], gid, item.subtype);
      // ✅ 通知发起人绑定的私密群
      const sendGroupId = getRoleGroupId(item.sendname);
      if (sendGroupId) {
        const msgToInitiator = seal.newMessage();
        msgToInitiator.messageType = "group";
        msgToInitiator.sender = {};
        msgToInitiator.sender.userId = `${platform}:${item.sendid}`;
        msgToInitiator.groupId = `${platform}-Group:${sendGroupId}`;
        const ctxToInitiator = seal.createTempCtx(ctx.endPoint, msgToInitiator);
        seal.replyToSender(ctxToInitiator, msgToInitiator, send);
        if (item.subtype) {
            initGroupTimer(platform, gid, item.subtype, [item.sendname, item.toname], item.sendname);
        }
      } else {
        seal.replyToSender(ctx, msg, `⚠️ 无法找到 ${item.sendname} 的私密群绑定，通知未送达`);
      }

      return seal.ext.newCmdExecuteResult(true);
    }

  } catch (e) {
    console.log(`[异常] .接受 崩溃: ${e.stack || e}`);
    return seal.ext.newCmdExecuteResult(true);
  }
};

ext.cmdMap["接受"] = cmd_accept_request;

// ========================
// ⏰ 查看到期群指令
// ========================

let cmd_view_expired_groups = seal.ext.newCmdItemInfo();
cmd_view_expired_groups.name = "查看到期群";
cmd_view_expired_groups.help = "查看所有已到期群组\n。查看到期群 - 查看所有已到期群组\n。查看到期群 提醒 - 向所有已到期群组发送到期提醒";

cmd_view_expired_groups.solve = (ctx, msg, cmdArgs) => {
    try {
        if (!isUserAdmin(ctx, msg)) {
            seal.replyToSender(ctx, msg, "⚠️ 该指令仅限管理员使用");
            return seal.ext.newCmdExecuteResult(true);
        }

        const platform = msg.platform;
        const action = cmdArgs.getArgN(1);
        const now = Date.now();
        
        // 读取群组到期信息
        const groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
        const confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
        const privateGroups = JSON.parse(ext.storageGet("a_private_group") || "{}");
        
        // 筛选已到期的群组（当前时间 > expireTime）
        const expiredGroups = [];
        const activeGroups = [];
        
        for (const [gid, info] of Object.entries(groupExpireInfo)) {
            if (now > info.expireTime) {
                expiredGroups.push({ gid, ...info });
            } else {
                activeGroups.push({ gid, ...info });
            }
        }
        
        // 如果没有参数，显示到期群组列表
        if (!action) {
            if (expiredGroups.length === 0) {
                seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组。");
                return seal.ext.newCmdExecuteResult(true);
            }
            
            // 格式化时间显示
            const formatTime = (timestamp) => {
                return new Date(timestamp).toLocaleString("zh-CN", {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            };
            
            let result = `⏰ 已到期群组列表（共${expiredGroups.length}个）：\n\n`;
            
            expiredGroups.forEach((group, index) => {
                const overdueMinutes = Math.floor((now - group.expireTime) / (60 * 1000));
                const overdueHours = Math.floor(overdueMinutes / 60);
                const overdueDays = Math.floor(overdueHours / 24);
                
                result += `📌 群组 ${index + 1}:\n`;
                result += `  群号：${group.gid}\n`;
                result += `  类型：${group.subtype || '小群'}\n`;
                result += `  时间：${group.day} ${group.time}\n`;
                result += `  地点：${group.place}\n`;
                result += `  参与者：${group.participants.join('、')}\n`;
                result += `  到期时间：${formatTime(group.expireTime)}\n`;
                
                if (overdueDays > 0) {
                    result += `  已超时：${overdueDays}天${overdueHours % 24}小时${overdueMinutes % 60}分钟\n`;
                } else if (overdueHours > 0) {
                    result += `  已超时：${overdueHours}小时${overdueMinutes % 60}分钟\n`;
                } else {
                    result += `  已超时：${overdueMinutes}分钟\n`;
                }
                result += "\n";
            });
            
            result += `💡 提示：使用「。查看到期群 提醒」向所有已到期群组发送提醒消息`;
            
            seal.replyToSender(ctx, msg, result);
            return seal.ext.newCmdExecuteResult(true);
        }
        
        // 如果参数是"提醒"
        if (action === "提醒") {
            if (expiredGroups.length === 0) {
                seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组，无需提醒。");
                return seal.ext.newCmdExecuteResult(true);
            }
            
            let successCount = 0;
            let failCount = 0;
            const failDetails = [];
            
            // 向每个到期群组发送提醒
            for (const group of expiredGroups) {
                try {
                    const groupMsg = seal.newMessage();
                    groupMsg.messageType = "group";
                    groupMsg.groupId = `${platform}-Group:${group.gid}`;
                    groupMsg.sender = {};
                    
                    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
                    
                    // 计算超时时间
                    const overdueMinutes = Math.floor((now - group.expireTime) / (60 * 1000));
                    const overdueHours = Math.floor(overdueMinutes / 60);
                    const overdueDays = Math.floor(overdueHours / 24);
                    
                    let overdueText = "";
                    if (overdueDays > 0) {
                        overdueText = `${overdueDays}天${overdueHours % 24}小时${overdueMinutes % 60}分钟`;
                    } else if (overdueHours > 0) {
                        overdueText = `${overdueHours}小时${overdueMinutes % 60}分钟`;
                    } else {
                        overdueText = `${overdueMinutes}分钟`;
                    }
                    
                    // 温和的到期提醒消息
                    const reminderMsg = 
                        `⏰ 温馨提示：\n\n` +
                        `本群互动时间已经超过预定结束时间 ${overdueText} 啦～\n\n` +
                        `如果各位已经完成互动，可以请管理员帮忙结束本群，\n` +
                        `使用指令「。结束私约」即可。\n\n` +
                        `📋 群组信息：\n` +
                        `• 类型：${group.subtype || '小群'}\n` +
                        `• 时间：${group.day} ${group.time}\n` +
                        `• 地点：${group.place}\n` +
                        `• 参与者：${group.participants.join('、')}\n\n` +
                        `感谢各位的参与～`;
                    
                    seal.replyToSender(groupCtx, groupMsg, reminderMsg);
                    successCount++;
                    
                } catch (error) {
                    failCount++;
                    failDetails.push(`群组 ${group.gid}: ${error.message}`);
                    console.log(`向群组 ${group.gid} 发送提醒失败:`, error);
                }
            }
            
            // 显示提醒结果
            let result = `📢 到期提醒发送完成：\n\n`;
            result += `✅ 成功提醒：${successCount} 个群组\n`;
            
            if (failCount > 0) {
                result += `⚠️ 提醒失败：${failCount} 个群组\n`;
                if (failDetails.length > 0 && failDetails.length <= 5) {
                    result += `失败详情：\n${failDetails.map(d => `• ${d}`).join('\n')}\n`;
                }
            }
            
            result += `\n💡 小提示：\n`;
            result += `• 已到期的群组会继续在列表中显示\n`;
            result += `• 管理员可在相应群内使用「。结束私约」结束群组`;
            
            seal.replyToSender(ctx, msg, result);
            return seal.ext.newCmdExecuteResult(true);
        }
        
        seal.replyToSender(ctx, msg, "⚠️ 参数错误，请使用：\n。查看到期群 - 查看列表\n。查看到期群 提醒 - 发送提醒");
        return seal.ext.newCmdExecuteResult(true);
        
    } catch (error) {
        console.log(`[异常] .查看到期群 崩溃: ${error.stack || error}`);
        seal.replyToSender(ctx, msg, "⚠️ 指令执行出错，请检查日志");
        return seal.ext.newCmdExecuteResult(true);
    }
};

ext.cmdMap["查看到期群"] = cmd_view_expired_groups;

function setGroupName(ctx, msg, groupId, groupName) {
    // 1. 检查使用条件
    const triggerCondition = seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件");
    const fmtCondition = parseInt(seal.format(ctx, `{${triggerCondition}}`));
    
    if (fmtCondition !== 1) {
        seal.replyToSender(ctx, msg, `当前不满足使用条件，无法使用群管功能`);
        console.log('不满足群管插件使用条件，无法设置群名');
        return seal.ext.newCmdExecuteResult(true);
    }

    console.log(groupId)
    console.log(ctx.group.groupId)
    
    // 3. 参数验证
    if (!groupName || groupName.trim() === '') {
        seal.replyToSender(ctx, msg, `请输入需要设置的群名`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 4. 提取群号（处理不同格式）
    let groupIdNum;
    if (typeof groupId === 'string') {
        const match = groupId.match(/:(\d+)/);
        if (match && match[1]) {
            groupIdNum = match[1];
        } else {
            // 如果没有冒号格式，假设已经是纯数字
            groupIdNum = groupId;
        }
    } else {
        // 如果是数字，转换为字符串
        groupIdNum = groupId.toString();
    }
    
    // 5. 发送WebSocket请求
    const postData = {
        "action": "set_group_name",
        "params": {
            group_id: groupIdNum,
            group_name: groupName,
        }
    };
    
    const successreply = `已修改群名为${groupName}。`;
    return ws(postData, ctx, msg, successreply);
}

// 命令版本（如果需要保留命令）
const cmdgroupname = seal.ext.newCmdItemInfo();
cmdgroupname.name = "设置加百列群名";
cmdgroupname.help = "设置加百列群名，.设置加百列群名 【群名】";
cmdgroupname.solve = (ctx, msg, cmdArgs) => {
    const groupName = cmdArgs.getArgN(1);

      if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `⚠️ 此乃管理权限之事，非管理员者不得。`);
    return seal.ext.newCmdExecuteResult(true);
  }
    
    if (!groupName) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }
    
    return setGroupName(ctx, msg, ctx.group.groupId, groupName);
};

ext.cmdMap["设置加百列群名"] = cmdgroupname;

    const cmdSpecialTitle = seal.ext.newCmdItemInfo();
    cmdSpecialTitle.name = "群头衔更改";
    cmdSpecialTitle.help =
        "群头衔功能，可用“.群头衔 内容” 指令来更改。 “.群头衔 权限切换”来切换可发布者的身份，默认为管理员与群主才能更改头衔（master和白名单例外），切换后为所有人都可以更改。无论哪种权限，管理员和群主可以通过@某人代改。";
    cmdSpecialTitle.allowDelegate = true;
    cmdSpecialTitle.solve = (ctx, msg, cmdArgs) => {
        const triggerCondition = seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件");
        const fmtCondition = parseInt(seal.format(ctx, `{${triggerCondition}}`));

        if (fmtCondition === 1) {
            let val = cmdArgs.getArgN(1);
            ctx.delegateText = "";
            switch (val) {
                case "help": {
                    ret.showHelp = true;
                    return seal.ext.newCmdExecuteResult(true);
                }
                default: {
                    if (!val) {
                        seal.replyToSender(ctx, msg, `请输入头衔内容`);
                        return seal.ext.newCmdExecuteResult(true);
                    }

                    // 权限切换
                    if (val === "权限切换" && ctx.privilegeLevel > 45) {
                        whiteList = whiteList === 1 ? 0 : 1;
                        seal.replyToSender(
                            ctx,
                            msg,
                            whiteList === 1 ?
                            `权限已切换为管理员与群主可更改` :
                            `权限已切换为所有人可更改`
                        );
                        return seal.ext.newCmdExecuteResult(true);
                    }

                    if (ctx.privilegeLevel < 45 && whiteList === 1) {
                        seal.replyToSender(
                            ctx,
                            msg,
                            `权限不足，无法修改群头衔,当前只有管理员与群主可无法修改群头衔`
                        );
                        return seal.ext.newCmdExecuteResult(true);
                    }

                    // 获取用户ID
                    let userQQ;
                    let mctx = seal.getCtxProxyFirst(ctx, cmdArgs);
                    userQQ = mctx.player.userId.split(":")[1];

                    if (ctx.privilegeLevel < 45 && mctx.player.userId !== ctx.player.userId) {
                        seal.replyToSender(ctx, msg, `权限不足，无法修改他人群头衔。`);
                        return seal.ext.newCmdExecuteResult(true);
                    }

                    const groupContent = val;
                    const contentLength = Array.from(groupContent).reduce(
                        (length, char) => {
                            if (/[\u0020-\u007E]/.test(char)) {
                                length += 0.5;
                            } else if (/[\u4e00-\u9fa5]/.test(char)) {
                                length += 1;
                            }
                            return length;
                        },
                        0
                    );

                    if (contentLength > 6) {
                        seal.replyToSender(ctx, msg, "头衔长度不能超过六个字符。");
                        return seal.ext.newCmdExecuteResult(true);
                    }

                    let groupQQ = ctx.group.groupId.match(/:(\d+)/)[1];
                    let postData = {
                        "action": "set_group_special_title",
                        "params": {
                            group_id: parseInt(groupQQ, 10),
                            user_id: parseInt(userQQ, 10),
                            special_title: groupContent.toString(),
                        }
                    };
                    const successreply = `群头衔更改成功。`;

                    return ws(postData, ctx, msg, successreply)
                };
            }
        } else {
            seal.replyToSender(
                ctx,
                msg,
                `当前不满足使用条件，无法使用群管功能`
            );
            return seal.ext.newCmdExecuteResult(true);
        }
    };
ext.cmdMap["群头衔"] = cmdSpecialTitle;

 // ========================
// 📢 群公告发布函数
// ========================

/**
 * 发布群公告
 * @param {Object} ctx - 上下文对象
 * @param {Object} msg - 消息对象
 * @param {string|number} groupId - 群号
 * @param {string} content - 公告内容
 * @param {boolean} [skipPermissionCheck=false] - 是否跳过权限检查
 * @returns {Object} 执行结果
 */
function setGroupNotice(ctx, msg, groupId, content, skipPermissionCheck = false) {
    // 1. 检查使用条件
    const triggerCondition = seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件");
    const fmtCondition = parseInt(seal.format(ctx, `{${triggerCondition}}`));
    
    if (fmtCondition !== 1) {
        seal.replyToSender(ctx, msg, `当前不满足使用条件，无法使用群管功能`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 2. 检查权限
    if (!skipPermissionCheck) {
        if (ctx.privilegeLevel < 45 && whiteList === 1) {
            seal.replyToSender(ctx, msg, `权限不足，无法发布群公告`);
            return seal.ext.newCmdExecuteResult(true);
        }
    }
    
    // 3. 提取群号
    let groupIdNum;
    if (typeof groupId === 'string') {
        const match = groupId.match(/:(\d+)/);
        groupIdNum = match ? match[1] : groupId;
    } else {
        groupIdNum = groupId.toString();
    }
    
    // 4. 处理内容
    let contentClean = seal.format(ctx, content.replace(/\[CQ:[^\]]*\]/g, ""));
    let postData = {
        "action": "_send_group_notice",
        "params": {
            group_id: groupIdNum,
            content: contentClean,
        }
    };
    
    // 5. 检查图片
    let regex = /\[CQ:image,file=(.*?),url=(.*?)\]/;
    let imgMatch = content.match(regex);
    if (imgMatch) {
        postData.params.image = imgMatch[2];
    }
    
    // 6. 发送请求
    const successreply = `群公告发送成功。`;
    return ws(postData, ctx, msg, successreply);
}
// ========================
// 📢 群公告发布指令
// ========================

let cmdGroupNotice = seal.ext.newCmdItemInfo();
cmdGroupNotice.name = "群公告发布";
cmdGroupNotice.help = 
    "。群公告发布 内容 - 发布群公告（支持图片）\n" +
    "。群公告发布 权限切换 - 切换发布权限（管理员可用）\n" +
    "。群公告发布 准备工作 - 发布准备开始公告\n" +
    "。群公告发布 玩家指令 - 发布玩家指令说明\n" +
    "。群公告发布 管理流程 - 发布管理员工作流程说明";

cmdGroupNotice.solve = function(ctx, msg, cmdArgs) {
    // 权限切换功能
    if (cmdArgs.getArgN(1) === "权限切换") {
        if (ctx.privilegeLevel > 45) {
            whiteList = whiteList === 1 ? 0 : 1;
            seal.replyToSender(ctx, msg, 
                whiteList === 1 ? 
                `权限已切换为管理员与群主可发布` : 
                `权限已切换为所有人都可发布`
            );
        } else {
            seal.replyToSender(ctx, msg, `权限不足，无法切换权限`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 准备工作功能
    if (cmdArgs.getArgN(1) === "准备工作") {
        const noticeContent = `【准备开始】

欢迎你来到《长梦无尽》剧组！箭头后为解释，可以不复制~

🎭 角色管理指令：
。创建新角色 名称 群号 
→ 注册系统，方便后续使用功能

🔗 关系线系统指令：
。查看关系线 对方角色名 
→ 在确认关系线后，查看关系线记录的记载（以及和谁拉过关系线）
。添加关系线细节 对方角色名 内容
→ 用于关系线沟通
。确认关系线 对方角色名 
→ 最终复确认并记录双方的关系线（请由发起方确认，会占用关系线份额）

祝您玩得开心~！有什么指令方面的问题请查询公告！`;
        
        // 使用函数发布公告
        return setGroupNotice(ctx, msg, ctx.group.groupId, noticeContent);
    }
    
    // 玩家指令功能
    if (cmdArgs.getArgN(1) === "玩家指令") {
        const noticeContent = `【基础指令】
该骰为长日将尽专有研发的小骰，和常规骰的指令略有不同。

🎭 语擦指令：
。创建新角色 名字
→ 请使用你想用的qq进行注册，本系统不绑定群，仅识别账号

。私约 0000-0130 地点 对方名字
。电话 0000-0030 对方名字
→ 发起私约和电话，时间请用四位数字表示，小时在前分钟在后；如果要同时约多人，请用 对方名字1/对方名字2 这样的格式。

。时间线
→ 查看自己的时间线、回复情况。

。私约请求 
。接受/拒绝 1  / 。撤销 S1
→ 在收到邀约后，查看私约请求序号接受/拒绝。如果只有一个请求，一般可以直接使用。接受 1；请注意如果有多个请求，在接受/拒绝之后顺序会发生变化，比如原本的2号会变成1号。

。寄信 对方名字 内容
→ 快速短信，有冷却cd，尽量不要发送图片、换行、空格。
。送礼 对方名字 礼物编号
→ 快速礼物，有冷却cd。

。礼物商城 / 。我的图鉴
→ 获取可以赠送的礼物，冷却为1.5小时。

。发送心动信
。查看我的心动信件
。撤回我的心动信件
→ 心动信系统

。玩家名单
→ 查看已绑定的角色

💡 温馨提示：
- 所有时间请使用24小时制
- 使用前请确保角色已正确绑定`;
        
        // 使用函数发布公告
        return setGroupNotice(ctx, msg, ctx.group.groupId, noticeContent);
    }
     // 管理流程功能
    if (cmdArgs.getArgN(1) === "管理流程") {
        const noticeContent = `【管理流程指南】

🔧 提前准备
1. 系统参数（设置调整所需要的设置）
2. 。添加群号 （添加备用群）
3. 。创建新角色 名字（npc注册）
4. 请在所有备用群把加百列设为管理，并且在开始前使用。ext all on确保功能正常。

📢 发布指令公告
1. 。群公告发布 玩家指令
2. 。群公告发布 准备工作
3. 。群头衔 可以直接给玩家设置头衔（需要加百列是群主）

📅 每日维持
1. 。设置天数 D1 清空
2. 。发起官约（根据剧情需要）
3. 。重置计数 all（清空次数）
4. 。统一发心动信（在需要的节点统一发信）
5. 。提醒超时 （一键催戏）
6. 。结束私约（在收群的时候释放群）
7. 。设置信箱上限 数量

🔄 其他维护
- 。强硬初始化（谨慎使用，重置所有数据）
- 。查看所有请求（监控当前待处理请求）
- 。时间锁定（锁定角色特定时间段）
- 。功能权限（限制特定角色的功能使用）

⚠️ 注意事项：
- 执行管理操作前请确认权限
- 重要操作前建议备份数据
- 定期清理过期群组和请求`;
        
        // 使用函数发布公告
        return setGroupNotice(ctx, msg, ctx.group.groupId, noticeContent);
    }
    
    // 提取公告内容
    const matchResult = msg.message.match(/^[。.]群公告发布\s+(.+)$/s);
    if (!matchResult || !matchResult[1]) {
        seal.replyToSender(ctx, msg, `请输入公告内容`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const content = matchResult[1].trim();
    
    // 使用函数发布公告
    return setGroupNotice(ctx, msg, ctx.group.groupId, content);
};

// 注册指令
ext.cmdMap["群公告发布"] = cmdGroupNotice;

// 💬 群内通知发起人
function notifySenderInGroup(platform, sendid, groupId, content, ctx) {
  const msg = seal.newMessage();
  msg.messageType = "group";
  msg.groupId = `${platform}-Group:${groupId}`;
  msg.sender = {};
  msg.sender.userId = `${platform}:${sendid}`;
  const innerCtx = seal.createTempCtx(ctx.endPoint, msg);
  seal.replyToSender(innerCtx, msg, content);
}

let cmd_refuse_request = seal.ext.newCmdItemInfo();
cmd_refuse_request.name = "拒绝";
cmd_refuse_request.help = "。拒绝 序号";

cmd_refuse_request.solve = (ctx, msg, cmdArgs) => {
  const index = parseInt(cmdArgs.getArgN(1));
  const platform = msg.platform;
  const uid = msg.sender.userId;

  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  const myRequests = appointmentList.filter(item => `${platform}:${item.toid}` === uid);

  if (myRequests.length === 0) {
    seal.replyToSender(ctx, msg, "你当前没有待处理请求");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (isNaN(index) || index < 1 || index > myRequests.length) {
    seal.replyToSender(ctx, msg, "请输入有效的请求编号");
    return seal.ext.newCmdExecuteResult(true);
  }

  const item = myRequests[index - 1];
  appointmentList = appointmentList.filter(i => i !== item);
  ext.storageSet("appointmentList", JSON.stringify(appointmentList));

  const privateGroups = JSON.parse(ext.storageGet("a_private_group") || "{}");
  let yourName = "（未知角色）";
  if (privateGroups[platform]) {
    for (const [name, val] of Object.entries(privateGroups[platform])) {
      if (val[0] === uid.replace(`${platform}:`, "")) {
        yourName = name;
        break;
      }
    }
  }

  // 🧑‍🤝‍🧑 多人请求
  if (item.groupRef) {
    const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
    const ref = item.groupRef;
    const group = b_MultiGroupRequest[ref];

    if (!group || !group.targetList.hasOwnProperty(item.toname)) {
      seal.replyToSender(ctx, msg, "请求已失效或身份信息缺失");
      return seal.ext.newCmdExecuteResult(true);
    }

    const status = group.targetList[item.toname];
    if (status === "accepted") {
      seal.replyToSender(ctx, msg, "⚠️ 你已接受该请求，无法再次拒绝");
      return seal.ext.newCmdExecuteResult(true);
    }
    if (status === "refused") {
      seal.replyToSender(ctx, msg, "⚠️ 你已拒绝该请求，无需重复操作");
      return seal.ext.newCmdExecuteResult(true);
    }

    group.targetList[item.toname] = "refused";
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));

    const allRefused = Object.values(group.targetList).every(v => v === "refused");
    const targetGroupId = privateGroups[platform][item.sendname]?.[1];

    if (targetGroupId) {
      const content = allRefused
        ? `❌ 所有人都拒绝了你发起的多人小群请求，系统已撤销该请求`
        : `📜 ${yourName}婉拒了您的多人小群邀请：
📅 ${group.day} ${group.time}
📍 ${group.place}`;
      notifySenderInGroup(platform, item.sendid, targetGroupId, content, ctx);
    }

    if (allRefused) {
      delete b_MultiGroupRequest[ref];
      ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
    }

    seal.replyToSender(ctx, msg,
      `你以「${yourName}」的身份拒绝了来自 ${item.sendname} 的多人小群请求：
📅 ${item.day} ${item.time}
📍 ${item.place}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 👤 单人小群请求
  const targetGroupId = privateGroups[platform][item.sendname]?.[1];
  if (targetGroupId) {
    const content = `📜 ${yourName}说：
📅 ${item.day} ${item.time}
📍 ${item.place}
我来不了啊！`;
    notifySenderInGroup(platform, item.sendid, targetGroupId, content, ctx);
  } else {
    seal.replyToSender(ctx, msg, "⚠️ 无法找到对方的私密群组，通知发送失败");
  }

  seal.replyToSender(ctx, msg,
    `你以「${yourName}」的身份拒绝了来自 ${item.sendname} 的小群请求：
📅 ${item.day} ${item.time}
📍 ${item.place}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["拒绝"] = cmd_refuse_request;

let cmd_withdraw_request = seal.ext.newCmdItemInfo();
cmd_withdraw_request.name = "撤销";
cmd_withdraw_request.help = "。撤销 或 撤销 S序号（仅可撤回尚未被接受的小群申请）";

cmd_withdraw_request.solve = (ctx, msg, cmdArgs) => {
  let indexRaw = cmdArgs.getArgN(1);
  let uid = msg.sender.userId;
  let platform = msg.platform;

  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  let b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  let a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

  // 🧾 仅保留尚未被接受的小群请求（含多人）
  let mySent = appointmentList.filter(item => {
    const fromMe = `${platform}:${item.sendid}` === uid && item.type === "小群";
    if (!fromMe) return false;

    if (item.groupRef && b_MultiGroupRequest[item.groupRef]) {
      const status = b_MultiGroupRequest[item.groupRef].targetList?.[item.toname];
      return status === null;
    } else {
      return true;
    }
  });

  if (!indexRaw) {
    if (mySent.length === 0) {
      seal.replyToSender(ctx, msg, "📜 您当前无待撤之约，可安心歇息。");
      return seal.ext.newCmdExecuteResult(true);
    }

    let rep = "📤 您发出的待回应发起邀约如下：\n";
    mySent.forEach((item, i) => {
      rep += `[S${i + 1}] → ${item.toname}：${item.subtype} ${item.day} ${item.time} @${item.place}\n`;
    });
    rep += `\n🖋 如欲撤销，请下达 “撤销 S序号” 例如：。撤销 S1`;
    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!indexRaw.startsWith("S")) {
    seal.replyToSender(ctx, msg, "⚠️ 撤销需使用格式 “撤销 S序号”，例如：。撤销 S1");
    return seal.ext.newCmdExecuteResult(true);
  }

  let index = parseInt(indexRaw.substring(1));
  if (isNaN(index) || index < 1 || index > mySent.length) {
    seal.replyToSender(ctx, msg, "⚠️ 序号无效，请重新确认");
    return seal.ext.newCmdExecuteResult(true);
  }

  let item = mySent[index - 1];

  if (!a_private_group[platform] || !a_private_group[platform][item.sendname]) {
    seal.replyToSender(ctx, msg, `⚠️ 未能识别您的角色信息，撤销失败`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 再次确认该请求存在（按字段匹配）
  let exists = appointmentList.some(i =>
    i.type === item.type &&
    i.sendid === item.sendid &&
    i.toid === item.toid &&
    i.day === item.day &&
    i.time === item.time &&
    i.place === item.place
  );
  if (!exists) {
    seal.replyToSender(ctx, msg, "📜 此约已不存于账册，或已有人应诺，无法撤回");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🎭 多人请求撤回
  if (item.groupRef) {
    const ref = item.groupRef;

    if (!b_MultiGroupRequest[ref]) {
      seal.replyToSender(ctx, msg, `📜 此共聚之邀已不存，或已达成，无法撤销`);
      return seal.ext.newCmdExecuteResult(true);
    }

    const hasAccepted = Object.values(b_MultiGroupRequest[ref].targetList).some(status => status === "accepted");
    if (hasAccepted) {
      seal.replyToSender(ctx, msg, `⚠️ 此多人之邀已有宾客应允，现不可撤，望悉知`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 通知所有被邀请人
    const names = Object.keys(b_MultiGroupRequest[ref].targetList);
    for (let toname of names) {
      let toid = a_private_group[platform][toname]?.[0];
      let gid = a_private_group[platform][toname]?.[1];
      if (!toid || !gid) continue;

      let notify = seal.newMessage();
      notify.messageType = "group";
      notify.sender = {};
      notify.sender.userId = `${platform}:${toid}`;
      notify.groupId = `${platform}-Group:${gid}`;
      let notifyCtx = seal.createTempCtx(ctx.endPoint, notify);
      seal.replyToSender(notifyCtx, notify,
        `📜 ${item.sendname} 撤回了原定于 ${item.day} ${item.time} @${item.place} 的共聚之邀。\n风云变幻，聚散由天。`);
    }

    appointmentList = appointmentList.filter(i => i.groupRef !== ref);
    delete b_MultiGroupRequest[ref];
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
    ext.storageSet("appointmentList", JSON.stringify(appointmentList));

    seal.replyToSender(ctx, msg, `📍 您已撤回此场共谋之邀，诸位亦将另觅良机。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 👤 单人请求撤回
  appointmentList = appointmentList.filter(i =>
    !(
      i.type === item.type &&
      i.sendid === item.sendid &&
      i.toid === item.toid &&
      i.day === item.day &&
      i.time === item.time &&
      i.place === item.place
    )
  );
  ext.storageSet("appointmentList", JSON.stringify(appointmentList));

  const rep  = `📍 您已撤回向 ${item.toname} 发起之邀：${item.subtype} ${item.day} ${item.time} @${item.place}`;
  const send = `📜 ${item.sendname} 撤回了原定于 ${item.day} ${item.time} @${item.place} 的发起邀约，或有更变，敬请见谅。`;

  // ——关键：优先取被邀请者的绑定群号
  let recipientGid = null;
  if (a_private_group[platform] && a_private_group[platform][item.toname]) {
    recipientGid = a_private_group[platform][item.toname][1]; // 被邀请者绑定群
  }
  // 如仍无，则尝试 item.gid 兜底
  if (!recipientGid && item.gid) recipientGid = item.gid;

  seal.replyToSender(ctx, msg, rep);

  if (recipientGid) {
    // 手动构造“发给被邀请者群”的消息
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${item.toid}`;         // 被邀请者
    newmsg.groupId = `${platform}-Group:${recipientGid}`;      // 被邀请者的群号

    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
    seal.replyToSender(newctx, newmsg, send);
  } else {
    // 找不到目标群 → 仅回执给发起者
    seal.replyToSender(ctx, msg, "⚠️ 未找到对方绑定群，未能发送撤回通知。");
  }

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["撤销"] = cmd_withdraw_request;

let cmd_view_schedule_other = seal.ext.newCmdItemInfo();
cmd_view_schedule_other.name = "查看他人时间线";
cmd_view_schedule_other.help = "。查看他人时间线 角色名 —— 管理员专属，查看指定角色的全部时间安排";

cmd_view_schedule_other.solve = (ctx, msg, cmdArgs) => {
  const role = cmdArgs.getArgN(1);
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

  if (!role) {
    seal.replyToSender(ctx, msg, "📌 请注明需查看的角色名，例如：\n.查看他人时间线 玛丽");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `⚠️ 此乃管理权限之事，非管理员者不得窥探他人行迹`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const targetUid = a_private_group[platform][role]?.[0];
  if (!targetUid) {
    seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${role}」，请确认其已完成绑定`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const key = `${platform}:${targetUid}`;
  const schedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

  if (!schedule[key] || schedule[key].length === 0) {
    seal.replyToSender(ctx, msg, `📭 ${role} 目前尚无任何已确认的会晤安排`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const sorted = schedule[key].slice().sort((a, b) => {
    const getMin = s => parseInt(s.time.split("-")[0].replace(":", ""));
    if (a.day !== b.day) return parseInt(a.day.slice(1)) - parseInt(b.day.slice(1));
    return getMin(a) - getMin(b);
  });

  const grouped = {};
  for (let item of sorted) {
    if (!grouped[item.day]) grouped[item.day] = [];
    grouped[item.day].push(item);
  }

  let rep = `📜 ${role} 的密约行程如下所列：\n`;
  for (let day of Object.keys(grouped).sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)))) {
    rep += `\n📅【${day}】\n`;
    for (let ev of grouped[day]) {
      let marker = ev.subtype === "续杯" ? "🌀" : ev.subtype === "电话" ? "📞" : "🤫";
      rep += `${marker} ${ev.time} —— ${ev.partner}（${ev.subtype}小群）\n`;
    }
  }

  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["查看他人时间线"] = cmd_view_schedule_other;

// 统一时间锁定指令
let cmd_time_lock = seal.ext.newCmdItemInfo();
cmd_time_lock.name = "时间锁定";
cmd_time_lock.help = `
时间锁定 [操作] [目标] [日期] [时间] —— 管理员管理角色时间锁定状态

参数说明：
• 操作：锁定/解锁
• 目标：单个角色名 / 多个角色名用/分隔 / 全体
• 日期：D1, D2, D3...（格式：D+数字）
• 时间：14:00-16:00（格式：开始时间-结束时间）

示例：
。时间锁定 锁定 角色A D3 14:00-16:00
。时间锁定 锁定 角色A/角色B/角色C D3 14:00-16:00
。时间锁定 锁定 全体 D3 14:00-16:00
。时间锁定 解锁 角色A D3 14:00-16:00
。时间锁定 解锁 全体 D3 14:00-16:00
。时间锁定 解锁 角色A/角色B D3 14:00-16:00
`;

cmd_time_lock.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const operation = argv.getArgN(1); // 锁定/解锁
    const target = argv.getArgN(2);    // 角色名/角色A/角色B/全体
    const day = argv.getArgN(3);       // D1, D2...
    const time = argv.getArgN(4);      // 14:00-16:00

    // 参数验证
    if (!operation || !target || !day || !time) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    if (operation !== "锁定" && operation !== "解锁") {
        seal.replyToSender(ctx, msg, "⚠️ 操作参数错误：必须是「锁定」或「解锁」");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!/^D\d+$/.test(day)) {
        seal.replyToSender(ctx, msg, "⚠️ 日期格式错误：必须是D+数字，如D1, D2, D3...");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!isValidTimeFormat(time)) {
        seal.replyToSender(ctx, msg, "⚠️ 时间格式错误：必须是HH:MM-HH:MM格式，如14:00-16:00");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    let a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    let a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");

    // 获取目标角色列表
    let targetRoles = [];
    
    if (target === "全体") {
        // 获取当前平台所有角色
        if (a_private_group[platform]) {
            targetRoles = Object.keys(a_private_group[platform]);
        }
        if (targetRoles.length === 0) {
            seal.replyToSender(ctx, msg, "⚠️ 当前平台没有任何绑定的角色");
            return seal.ext.newCmdExecuteResult(true);
        }
    } else if (target.includes("/")) {
        // 多个角色，用/分隔
        targetRoles = target.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
    } else {
        // 单个角色
        targetRoles = [target];
    }

    // 处理每个角色
    let successList = [];
    let failList = [];
    let notFoundList = [];
    let alreadyList = []; // 已经锁定/解锁的状态

    for (let roleName of targetRoles) {
        // 检查角色是否存在
        if (!a_private_group[platform] || !a_private_group[platform][roleName]) {
            notFoundList.push(roleName);
            continue;
        }

        const uid = a_private_group[platform][roleName][0];
        const key = `${platform}:${uid}`;

        // 执行锁定或解锁操作
        if (operation === "锁定") {
            if (!a_lockedSlots[key]) a_lockedSlots[key] = {};
            if (!a_lockedSlots[key][day]) a_lockedSlots[key][day] = [];
            
            if (a_lockedSlots[key][day].includes(time)) {
                alreadyList.push(`⚠️「${roleName}」已锁定 ${day} ${time}`);
            } else {
                a_lockedSlots[key][day].push(time);
                successList.push(`✅「${roleName}」已锁定 ${day} ${time}`);
            }
        } else { // 解锁操作
            if (a_lockedSlots[key] && a_lockedSlots[key][day]) {
                const index = a_lockedSlots[key][day].indexOf(time);
                if (index !== -1) {
                    a_lockedSlots[key][day].splice(index, 1);
                    // 清理空数组和空对象
                    if (a_lockedSlots[key][day].length === 0) delete a_lockedSlots[key][day];
                    if (Object.keys(a_lockedSlots[key]).length === 0) delete a_lockedSlots[key];
                    successList.push(`✅「${roleName}」已解锁 ${day} ${time}`);
                } else {
                    alreadyList.push(`⚠️「${roleName}」未锁定 ${day} ${time}`);
                }
            } else {
                alreadyList.push(`⚠️「${roleName}」未锁定 ${day} ${time}`);
            }
        }
    }

    // 保存数据
    ext.storageSet("a_lockedSlots", JSON.stringify(a_lockedSlots));

    // 构建回复消息
    let resultMsg = "";
    
    if (successList.length > 0) {
        resultMsg += `📋 ${operation}操作成功（${successList.length}个）：\n`;
        resultMsg += successList.join("\n") + "\n\n";
    }
    
    if (alreadyList.length > 0) {
        resultMsg += `ℹ️ 无需操作（${alreadyList.length}个）：\n`;
        resultMsg += alreadyList.join("\n") + "\n\n";
    }
    
    if (notFoundList.length > 0) {
        resultMsg += `❌ 未找到角色（${notFoundList.length}个）：\n`;
        resultMsg += notFoundList.map(name => `「${name}」`).join("、") + "\n\n";
    }
    
    if (failList.length > 0) {
        resultMsg += `⚠️ 操作失败（${failList.length}个）：\n`;
        resultMsg += failList.join("\n");
    }

    // 如果没有任何操作结果，显示提示
    if (successList.length === 0 && alreadyList.length === 0 && 
        notFoundList.length === 0 && failList.length === 0) {
        resultMsg = "⚠️ 未执行任何操作，请检查参数";
    }

    seal.replyToSender(ctx, msg, resultMsg.trim());
    return seal.ext.newCmdExecuteResult(true);
};

// 替换原有的四个指令
ext.cmdMap["时间锁定"] = cmd_time_lock;

let cmd_grant_admin = seal.ext.newCmdItemInfo();
cmd_grant_admin.name = "授予管理员";
cmd_grant_admin.help = "。授予管理员 QQ号 密码（输入正确密码后将该QQ设为临时管理员）";

cmd_grant_admin.solve = (ctx, msg, cmdArgs) => {
  const targetQQ = cmdArgs.getArgN(1);
  const inputPass = cmdArgs.getArgN(2);
  const platform = msg.platform;

  if (!targetQQ || !inputPass) {
    seal.replyToSender(ctx, msg, "请输入授权格式，例如：.授予管理员 123456789 newyork");
    return seal.ext.newCmdExecuteResult(true);
  }

  const ADMIN_SECRET = getAdminPassword();

  if (inputPass.trim() !== ADMIN_SECRET) {
    seal.replyToSender(ctx, msg, "❌ 密码错误，无法授权管理员");
    return seal.ext.newCmdExecuteResult(true);
  }

  const uid = `${platform}:${targetQQ}`;
  let a_adminList = JSON.parse(ext.storageGet("a_adminList") || "{}");
  if (!a_adminList[platform]) a_adminList[platform] = [];

  if (!a_adminList[platform].includes(targetQQ)) {
    a_adminList[platform].push(targetQQ);
    ext.storageSet("a_adminList", JSON.stringify(a_adminList));
    seal.replyToSender(ctx, msg, `✅ 成功将 ${targetQQ} 设为 ${platform} 平台的临时管理员`);
  } else {
    seal.replyToSender(ctx, msg, `⚠️ ${targetQQ} 已是管理员`);
  }
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["授予管理员"] = cmd_grant_admin;


let cmd_set_admin_pass = seal.ext.newCmdItemInfo();
cmd_set_admin_pass.name = "更改密令";  // 法语：更改密码
cmd_set_admin_pass.help = "。更改密令 新密码（需要是管理员才能执行）";

cmd_set_admin_pass.solve = (ctx, msg, cmdArgs) => {
  const newPass = cmdArgs.getArgN(1);

  if (!newPass || newPass.length < 4) {
    seal.replyToSender(ctx, msg, "⚠️ 请提供一个至少4位的新密码，例如：.更改密令 UltraSecret");
    return seal.ext.newCmdExecuteResult(true);
  }

  // ✅ 存为规范 JSON 字符串，避免后续 JSON.parse 出错
  ext.storageSet("adminPassword", JSON.stringify(newPass));

  seal.replyToSender(ctx, msg, "✅ 管理员密码已成功更新");
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["更改密令"] = cmd_set_admin_pass;


let cmd_revoke_admin = seal.ext.newCmdItemInfo();
cmd_revoke_admin.name = "收回管理员";
cmd_revoke_admin.help = "。收回管理员 QQ号 密码（输入正确密码可撤销管理员身份）";

cmd_revoke_admin.solve = (ctx, msg, cmdArgs) => {
  const targetUid = cmdArgs.getArgN(1);
  const inputPass = cmdArgs.getArgN(2);
  const platform = msg.platform;

  if (!targetUid || !inputPass) {
    seal.replyToSender(ctx, msg, "请输入完整参数：。撤销管理员 QQ号 密码");
    return seal.ext.newCmdExecuteResult(true);
  }

  const ADMIN_SECRET = getAdminPassword();

  if (inputPass.trim() !== ADMIN_SECRET) {
    seal.replyToSender(ctx, msg, "❌ 密码错误，无法撤销管理员");
    return seal.ext.newCmdExecuteResult(true);
  }

  let a_adminList = JSON.parse(ext.storageGet("a_adminList") || "{}");
  if (!a_adminList[platform]) {
    seal.replyToSender(ctx, msg, "⚠️ 当前平台无管理员记录");
    return seal.ext.newCmdExecuteResult(true);
  }

  const newList = a_adminList[platform].filter(id => id !== targetUid);
  if (newList.length === a_adminList[platform].length) {
    seal.replyToSender(ctx, msg, `⚠️ 用户 ${targetUid} 并非管理员`);
    return seal.ext.newCmdExecuteResult(true);
  }

  a_adminList[platform] = newList;
  ext.storageSet("a_adminList", JSON.stringify(a_adminList));
  seal.replyToSender(ctx, msg, `✅ 已撤销 ${targetUid} 的管理员身份`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["收回管理员"] = cmd_revoke_admin;

let cmd_list_admins = seal.ext.newCmdItemInfo();
cmd_list_admins.name = "管理员列表";
cmd_list_admins.help = "。管理员列表（显示当前所有平台下的临时管理员）";

cmd_list_admins.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "只有管理员可以查看管理员列表");
    return seal.ext.newCmdExecuteResult(true);
  }

  const a_adminList = JSON.parse(ext.storageGet("a_adminList") || "{}");
  let rep = "📋 当前所有平台的管理员清单：\n";

  const platforms = Object.keys(a_adminList);
  if (platforms.length === 0) {
    rep += "（暂无记录）";
  } else {
    for (let plat of platforms) {
      const ids = a_adminList[plat];
      if (ids.length === 0) continue;
      rep += `\n【${plat}】\n`;
      for (let id of ids) {
        rep += `- ${plat}:${id}\n`;
      }
    }
  }

  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["管理员列表"] = cmd_list_admins;

let cmd_clear_admin = seal.ext.newCmdItemInfo();
cmd_clear_admin.name = "清空管理员";
cmd_clear_admin.help = "。清空管理员 密码（输入正确密码可清空所有平台管理员）";

cmd_clear_admin.solve = (ctx, msg, cmdArgs) => {
  const input = cmdArgs.getArgN(1);

  if (!input) {
    seal.replyToSender(ctx, msg, "请输入密码，例如：.清空管理员 anton");
    return seal.ext.newCmdExecuteResult(true);
  }

  const ADMIN_SECRET = getAdminPassword();

  if (input.trim() !== ADMIN_SECRET) {
    seal.replyToSender(ctx, msg, "❌ 密码错误，无法清空管理员列表");
    return seal.ext.newCmdExecuteResult(true);
  }

  ext.storageSet("a_adminList", JSON.stringify({}));
  seal.replyToSender(ctx, msg, "✅ 所有平台的临时管理员已被清空");
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["清空管理员"] = cmd_clear_admin;

let cmd_list_all_requests = seal.ext.newCmdItemInfo();
cmd_list_all_requests.name = "查看所有请求";
cmd_list_all_requests.help = "。查看所有请求（管理员/骰主专用）";

cmd_list_all_requests.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员或骰主可以查看所有请求`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");

  if (appointmentList.length === 0 && Object.keys(b_MultiGroupRequest).length === 0) {
    seal.replyToSender(ctx, msg, "📭 当前没有任何待处理请求");
    return seal.ext.newCmdExecuteResult(true);
  }

  let rep = "📦 全部待处理请求如下：\n\n";

  // 显示普通请求
  if (appointmentList.length > 0) {
    rep += "📩 普通请求（使用「删除请求 序号」或「删除请求ID ID串」移除）：\n";
    appointmentList.forEach((item, index) => {
      let marker = item.type === "礼物" ? "🎁" : item.groupRef ? "👥" : "📩";
      if (item.type === "小群") {
        if (item.groupRef) {
          // 多人邀约的单个请求，显示groupRef但不重复显示
          const group = b_MultiGroupRequest[item.groupRef];
          if (group) {
            const status = group.targetList?.[item.toname];
            rep += `[${index + 1}] ${marker} ${item.subtype}小群｜${item.day} ${item.time} @${item.place}\n→ ${item.sendname} → ${item.toname}（状态：${status === "accepted" ? "✅已接受" : status === "refused" ? "❌已拒绝" : "⏳待回应"}）\nID: ${item.id}｜GroupRef: ${item.groupRef}\n\n`;
          } else {
            rep += `[${index + 1}] ${marker} ${item.subtype}小群｜${item.day} ${item.time} @${item.place}\n→ ${item.sendname} → ${item.toname}\nID: ${item.id}｜GroupRef: ${item.groupRef}\n\n`;
          }
        } else {
          rep += `[${index + 1}] ${marker} ${item.subtype}小群｜${item.day} ${item.time} @${item.place}\n→ ${item.sendname} → ${item.toname}\nID: ${item.id}\n\n`;
        }
      } else if (item.type === "礼物") {
        rep += `[${index + 1}] ${marker} 礼物｜${item.sendname} → ${item.toname}：「${item.gift}」\nID: ${item.id}\n\n`;
      }
    });
  }

  // 显示多人邀约记录
  if (Object.keys(b_MultiGroupRequest).length > 0) {
    rep += "\n👥 多人邀约记录（使用「移除多人邀约 groupRef」移除）：\n";
    Object.entries(b_MultiGroupRequest).forEach(([groupRef, group], index) => {
      rep += `[M${index + 1}] ${group.subtype}多人邀约｜${group.day} ${group.time} @${group.place}\n`;
      rep += `→ 发起人：${group.sendname}\n`;
      rep += `→ 目标列表：\n`;
      
      // 显示每个目标的状态
      Object.entries(group.targetList || {}).forEach(([targetName, status]) => {
        const statusText = status === "accepted" ? "✅已接受" : 
                          status === "refused" ? "❌已拒绝" : 
                          "⏳待回应";
        rep += `   • ${targetName}：${statusText}\n`;
      });
      
      rep += `GroupRef: ${groupRef}\n\n`;
    });
  }

  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看所有请求"] = cmd_list_all_requests;

// ========================
// 🗑️ 删除请求指令（通过序号）
// ========================

let cmd_delete_request = seal.ext.newCmdItemInfo();
cmd_delete_request.name = "删除请求";
cmd_delete_request.help = "。删除请求 序号/M序号 —— 删除指定的普通请求或多人邀约\n例如：\n。删除请求 1（删除普通请求）\n。删除请求 M1（删除多人邀约）";

cmd_delete_request.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员或骰主可以删除请求`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const indexArg = cmdArgs.getArgN(1);
  if (!indexArg) {
    seal.replyToSender(ctx, msg, `请指定要删除的请求序号，例如：\n。删除请求 1（普通请求）\n。删除请求 M1（多人邀约）`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const platform = msg.platform;
  let appointmentList = JSON.parse(ext.storageGet("appointmentList") || "[]");
  let b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");

  // 检查是否是多人邀约（以M开头）
  if (indexArg.toUpperCase().startsWith('M')) {
    // 处理多人邀约
    const multiIndex = parseInt(indexArg.substring(1));
    
    if (isNaN(multiIndex) || multiIndex < 1) {
      seal.replyToSender(ctx, msg, `⚠️ 无效的多人邀约序号：${indexArg}`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 获取所有多人邀约的groupRef列表
    const multiRefs = Object.keys(b_MultiGroupRequest);
    
    if (multiIndex > multiRefs.length) {
      seal.replyToSender(ctx, msg, `⚠️ 多人邀约序号 ${indexArg} 超出范围，当前共有 ${multiRefs.length} 个多人邀约`);
      return seal.ext.newCmdExecuteResult(true);
    }

    const targetRef = multiRefs[multiIndex - 1];
    const targetGroup = b_MultiGroupRequest[targetRef];
    
    if (!targetGroup) {
      seal.replyToSender(ctx, msg, `❌ 未找到对应的多人邀约记录`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 删除该多人邀约的所有相关请求
    const initialCount = appointmentList.length;
    appointmentList = appointmentList.filter(item => item.groupRef !== targetRef);
    
    // 删除多人邀约记录
    delete b_MultiGroupRequest[targetRef];
    
    // 保存数据
    ext.storageSet("appointmentList", JSON.stringify(appointmentList));
    ext.storageSet("b_MultiGroupRequest", JSON.stringify(b_MultiGroupRequest));
    
    const removedCount = initialCount - appointmentList.length;
    
    seal.replyToSender(ctx, msg, 
      `✅ 已删除多人邀约：${targetGroup.subtype} ${targetGroup.day} ${targetGroup.time} @${targetGroup.place}\n` +
      `发起人：${targetGroup.sendname}\n` +
      `目标：${Object.keys(targetGroup.targetList || {}).join("、")}\n` +
      `同时删除了 ${removedCount} 个相关请求`);
    
  } else {
    // 处理普通请求
    const regularIndex = parseInt(indexArg);
    
    if (isNaN(regularIndex) || regularIndex < 1) {
      seal.replyToSender(ctx, msg, `⚠️ 无效的请求序号：${indexArg}`);
      return seal.ext.newCmdExecuteResult(true);
    }

    if (regularIndex > appointmentList.length) {
      seal.replyToSender(ctx, msg, `⚠️ 请求序号 ${indexArg} 超出范围，当前共有 ${appointmentList.length} 个请求`);
      return seal.ext.newCmdExecuteResult(true);
    }

    const targetRequest = appointmentList[regularIndex - 1];
    
    // 检查是否是多人邀约的单个请求
    if (targetRequest.groupRef) {
      seal.replyToSender(ctx, msg,
        `⚠️ 该请求属于多人邀约的一部分，无法单独删除。\n` +
        `请使用「。删除请求 M序号」删除整个多人邀约。\n` +
        `所属多人邀约 GroupRef: ${targetRequest.groupRef}`);
      return seal.ext.newCmdExecuteResult(true);
    }

    // 删除请求
    appointmentList.splice(regularIndex - 1, 1);
    ext.storageSet("appointmentList", JSON.stringify(appointmentList));
    
    let detail = "";
    if (targetRequest.type === "小群") {
      detail = `${targetRequest.sendname} → ${targetRequest.toname} 的小群（${targetRequest.subtype} ${targetRequest.day} ${targetRequest.time} @${targetRequest.place})`;
    } else if (targetRequest.type === "礼物") {
      detail = `${targetRequest.sendname} → ${targetRequest.toname} 的礼物「${targetRequest.gift}」`;
    }
    
    seal.replyToSender(ctx, msg, `✅ 已删除请求：${detail}\nID: ${targetRequest.id}`);
  }
  
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["删除请求"] = cmd_delete_request;

let cmd_view_locks = seal.ext.newCmdItemInfo();
cmd_view_locks.name = "查看锁定";
cmd_view_locks.help = "。查看锁定 角色名（管理员/骰主可用）";

cmd_view_locks.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员或骰主可以查看角色锁定状态`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const name = cmdArgs.getArgN(1);
  if (!name) {
    seal.replyToSender(ctx, msg, `请输入角色名，如：查看锁定 安托万`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const platform = msg.platform;
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  if (!a_private_group[platform] || !a_private_group[platform][name]) {
    seal.replyToSender(ctx, msg, `未找到角色「${name}」，请确认其是否已绑定`);
    return;
  }

  const uid = a_private_group[platform][name][0];
  const key = `${platform}:${uid}`;
  const a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");

  if (!a_lockedSlots[key] || Object.keys(a_lockedSlots[key]).length === 0) {
    seal.replyToSender(ctx, msg, `✅ 角色「${name}」当前没有任何被锁定的时间段`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let rep = `📋 ${name} 的锁定时间段如下：\n`;
  const days = Object.keys(a_lockedSlots[key]).sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)));
  for (let day of days) {
    rep += `\n【${day}】\n`;
    for (let t of a_lockedSlots[key][day]) {
      rep += `- ${t}\n`;
    }
  }

  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看锁定"] = cmd_view_locks;

// ========================
// 🔄 强硬初始化（修正版）
// ========================

let cmd_hard_reset = seal.ext.newCmdItemInfo();
cmd_hard_reset.name = "强硬初始化";
cmd_hard_reset.help = "。强硬初始化（重置所有存储，包括地点系统）";

cmd_hard_reset.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `该指令仅限管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取目击配置函数（如果存在）
    const getSightingConfig = function() {
        return {
            enabled: true,
            send_to_all: true,
            max_reports_per_day: 5,
            include_ended_meetings: false,
            time_overlap_threshold: 0.3
        };
    };

    // 获取地点系统配置函数（如果存在）
    const getPlaceSystemConfig = function() {
        return {
            enabled: true,
            require_key_by_default: false
        };
    };

    const defaultStore = {
        appointmentList: JSON.stringify([]),
        b_confirmedSchedule: JSON.stringify({}),
        b_MultiGroupRequest: JSON.stringify({}),
        a_lockedSlots: JSON.stringify({}),
        a_private_group: JSON.stringify({}),
        group_expire_info: JSON.stringify({}),   // 清空所有群组到期倒计时
        forum_posts: JSON.stringify([]),
        group: JSON.stringify([]),
        a_adminList: JSON.stringify({}),
        a_messageLog: JSON.stringify([]),
        a_meetingCount_call: "0",
        a_meetingCount_private: "0",
        a_meetingCount_letter: "0",
        a_meetingCount_gift: "0",
        a_meetingCount_secretletter: "0",
        a_meetingCount_wish: "0",
        a_wishPool: JSON.stringify([]),
        lovemail_pool: JSON.stringify([]),
        lovemail_limit: "2",
        // 地点系统（正确的存储格式）
        place_system_config: JSON.stringify(getPlaceSystemConfig()),
        available_places: JSON.stringify({}),
        place_keys: JSON.stringify({}),
        // 原有配置
        global_feature_toggle: JSON.stringify({
            enable_general_letter: true,
            enable_general_gift: true,
            enable_general_appointment: true,
            enable_chaos_letter: true,
            enable_secret_letter: true,
            enable_wish_system: true,
            enable_lovemail: true
        }),
        adminPassword: JSON.stringify("newyork"),
        adminAnnounceGroupId: JSON.stringify(null),
        allowed_appointment_times: JSON.stringify([]),
        sighting_system_config: JSON.stringify(getSightingConfig()),
        sighting_daily_count: JSON.stringify({}),
        feature_user_blocklist: JSON.stringify({}),
        chaos_letter_config: JSON.stringify({
            misdelivery: 0,
            blackoutText: 0,
            loseContent: 0,
            antonymReplace: 0,
            reverseOrder: 0,
            fuzzySignature: 0,
            mistakenSignature: 0,
            poeticSignature: 0,
            dailyLimit: 5,
            publicChance: 50
        }),
        gift_public_send: JSON.stringify(false),
        secret_letter_public_send: JSON.stringify(false),
        wish_public_send: JSON.stringify(false),
        letter_public_send: JSON.stringify(false),
        preset_gifts: JSON.stringify({}),
        gift_sightings: JSON.stringify({}),
        // 新增小群过期时间配置
        group_expire_hours: "48",
        // 新增关系线系统配置
        relationship_system_enabled: JSON.stringify(true),
        max_relationships_per_user: "5",
        // 新增群组ID配置
        song_group_id: JSON.stringify(null),
        background_group_id: JSON.stringify(null),
        // 新增寄信配置
        appointment_duration_config: JSON.stringify({
            phone: 29,
            private: 59
        }),
            // 监听系统配置
        monitor_settings: JSON.stringify({
            enabled: true,
            min_words_phone: 20,
            min_words_private: 150,
            min_words_wish: 150,
            min_words_official: 150,
            timeout_phone: 3600000, // 1小时
            timeout_private: 10800000, // 3小时
            timeout_wish: 10800000, // 3小时
            timeout_official: 10800000, // 3小时
            remind_interval_phone: 5400000, // 1.5小时
            remind_interval_private: 10800000, // 3小时
            remind_interval_wish: 10800000, // 3小时
            remind_interval_official: 10800000 // 3小时
        }),
        
        // 监听群组列表（从group列表中筛选）
        monitor_groups: JSON.stringify([]),
        
        // 群组计时器状态
        group_timers: JSON.stringify({}),
        
        // 用户统计信息
        user_stats: JSON.stringify({}),
        // --- 补充内容 ---
        current_day: "D0", // 重置回第一天
        whiteList: "1",    // 默认开启管理员权限模式
        wx_channels: JSON.stringify({}), // 清空所有微信频道
        relationship_data: JSON.stringify({}), // 清空关系线内容
        
        // 游戏进度与标志位
        game_stage: "preparation", 
        global_flags: JSON.stringify({}),

        // 1. 🆕 晚餐系统重置
        dinner_system_data: JSON.stringify({}),
        dinner_global_status: "未开始",

        // 2. 🆕 微信系统重置
        wechat_groups: JSON.stringify({}),
        // 3. 🆕 NPC 列表重置
        a_npc_list: JSON.stringify([]),

        // 4. 🆕 物品/抽奖系统重置
        sys_item_pool: JSON.stringify([]), // 清空抽奖池
        global_inventories: JSON.stringify({}),   // 清空全服所有人背包
        global_draw_records: JSON.stringify({}),

        // 🆕 重置所有人的寄信限次
        global_chaos_letter_counts: JSON.stringify({}), 
        
        // 建议顺便把冷却也重置了，防止初始化后还要等2分钟
        chaos_letter_cooldown_data: JSON.stringify({}),
        // 🆕 方案 C：送礼系统重置
        global_gift_stats: JSON.stringify({}),     // 清空所有人每日送礼计数
        global_gift_cooldowns: JSON.stringify({}), // 清空所有人送礼冷却
        global_secret_letter_stats: JSON.stringify({}),
        global_secret_letter_cooldowns: JSON.stringify({}),
        global_shop_cooldowns: JSON.stringify({}), // 清空所有人逛商城的冷却
    };

    // 使用ext.storageSet逐个设置
    for (let key in defaultStore) {
        ext.storageSet(key, defaultStore[key]);
    }

    seal.replyToSender(ctx, msg, "✅ 全部存储项目已初始化为默认结构（含完整的地点系统）");
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["强硬初始化"] = cmd_hard_reset;

let cmd_reset_meeting_count = seal.ext.newCmdItemInfo();
cmd_reset_meeting_count.name = "重置计数";
cmd_reset_meeting_count.help = "。重置计数 call/private/letter/gift/wish/all\n参数说明：\n- call: 电话\n- private: 私密\n- letter: 剧情信件\n- gift: 礼物(含限次)\n- wish: 心愿\n- all: 全部重置";

cmd_reset_meeting_count.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 只有管理员可以重置会面计数");
    return seal.ext.newCmdExecuteResult(true);
  }

  const target = (cmdArgs.getArgN(1) || "").toLowerCase();
  const platform = msg.platform;
  
  // 1. 定义映射关系：参数名 -> [存储Key列表, 显示名称]
  // 这里的 Key 列表支持同时清理多个相关的 Storage Key
  const countMap = {
    "call": [["a_meetingCount_call"], "📞 电话会面"],
    "private": [["a_meetingCount_private"], "🤫 私密会面"],
    "letter": [["a_meetingCount_letter", "a_meetingCount_chaosletter"], "📜 信件往来"],
    "gift": [["a_meetingCount_gift", "global_gift_stats", "global_gift_cooldowns"], "🎁 礼物馈赠"],
    "wish": [["a_meetingCount_wish"], "🌠 心愿达成"],
    "secret": [["a_meetingCount_secretletter"], "💌 匿名信"]
  };

  // 2. 确定需要重置的 Key 列表
  let keysToProcess = [];
  if (target === "all") {
    keysToProcess = Object.keys(countMap);
  } else if (countMap[target]) {
    keysToProcess = [target];
  }

  if (keysToProcess.length === 0) {
    seal.replyToSender(ctx, msg, "⚠️ 参数错误，可选：call/private/letter/gift/wish/secret/all");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 3. 执行重置逻辑
  const clearedNames = [];
  keysToProcess.forEach(key => {
    const [storageKeys, displayName] = countMap[key];
    
    storageKeys.forEach(sKey => {
      // 如果是礼物大表或冷却表，重置为 {}，否则重置为 "0"
      if (sKey === "global_gift_stats" || sKey === "global_gift_cooldowns") {
        ext.storageSet(sKey, JSON.stringify({}));
      } else {
        ext.storageSet(sKey, "0");
      }
    });
    
    clearedNames.push(displayName);
  });

  // 4. 反馈结果
  seal.replyToSender(ctx, msg, `✅ 已重置以下项目的计数与限制：\n${clearedNames.join("、")}`);

  // 5. 管理群通知
  const adminGid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
  if (adminGid) {
    const noticeMsg = seal.newMessage();
    noticeMsg.messageType = "group";
    noticeMsg.groupId = `${platform}-Group:${adminGid}`;
    const noticeCtx = seal.createTempCtx(ctx.endPoint, noticeMsg);
    seal.replyToSender(noticeCtx, noticeMsg, `📜 管理员已重置了 [${clearedNames.join("/")}] 的统计数据`);
  }

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["重置计数"] = cmd_reset_meeting_count;

let cmd_block_user_feature = seal.ext.newCmdItemInfo();
cmd_block_user_feature.name = "功能权限";
cmd_block_user_feature.help = "。功能权限 角色名 信件/礼物/发起邀约 开启/关闭 —— 针对某人限制某功能";

cmd_block_user_feature.solve = (ctx, msg, cmdArgs) => {
  const roleName = cmdArgs.getArgN(1);     // 角色名
  const featureName = cmdArgs.getArgN(2);  // 信件 / 礼物 / 发起邀约
  const action = cmdArgs.getArgN(3);       // 开启 / 关闭

  if (!roleName || !featureName || !action) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  // 🔧 新增“发起邀约”功能映射
  const featureMap = {
    "剧情信件": "enable_general_letter",
    "礼物": "enable_general_gift",
    "发起邀约": "enable_general_appointment",
    "寄信": "enable_chaos_letter",
    "匿名信": "enable_secret_letter",
    "心愿": "enable_wish_system",
    "心动信": "enable_lovemail"
  };


  const key = featureMap[featureName];
  if (!key) {
    seal.replyToSender(ctx, msg, `⚠️ 功能名仅支持：信件 / 礼物 / 发起邀约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const value = (action === "开启") ? true : (action === "关闭") ? false : null;
  if (value === null) {
    seal.replyToSender(ctx, msg, `⚠️ 状态应为：开启 / 关闭`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  if (!blockMap[roleName]) blockMap[roleName] = {};
  blockMap[roleName][key] = value;
  ext.storageSet("feature_user_blocklist", JSON.stringify(blockMap));

  const status = value ? "✅ 已允许使用" : "🚫 已封禁";
  seal.replyToSender(ctx, msg, `${status} ${featureName} 功能：${roleName}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["功能权限"] = cmd_block_user_feature;

let cmd_view_user_feature = seal.ext.newCmdItemInfo();
cmd_view_user_feature.name = "查看功能权限";
cmd_view_user_feature.help = "。查看功能权限 —— 查看所有被设定过功能开关的角色与状态";

cmd_view_user_feature.solve = (ctx, msg, cmdArgs) => {
  let blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");

  if (Object.keys(blockMap).length === 0) {
    seal.replyToSender(ctx, msg, "📭 当前尚无任何角色设定功能权限。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const featureLabelMap = {
    enable_general_letter: "剧情信件",
    enable_general_gift: "礼物",
    enable_general_appointment: "发起邀约",
    enable_chaos_letter: "寄信",
    enable_secret_letter: "匿名信",
    enable_wish_system: "心愿",
    enable_lovemail: "心动信"
  };


  let lines = [];

  for (let roleName in blockMap) {
    let userFeatures = blockMap[roleName];
    let statusList = [];

    for (let key in userFeatures) {
      let status = userFeatures[key] ? "✅开启" : "🚫关闭";
      let label = featureLabelMap[key] || key;
      statusList.push(`${label}：${status}`);
    }

    if (statusList.length > 0) {
      lines.push(`【${roleName}】→ ${statusList.join("，")}`);
    }
  }

  if (lines.length === 0) {
    seal.replyToSender(ctx, msg, "📭 所有角色当前均为默认状态，无权限限制。");
    return seal.ext.newCmdExecuteResult(true);
  }

  seal.replyToSender(ctx, msg, `📜 功能权限状态如下：\n\n${lines.join("\n")}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["查看功能权限"] = cmd_view_user_feature;
// === 匿名信指令：方案 C 完整版 ===
let cmd_send_secretletter = seal.ext.newCmdItemInfo();
cmd_send_secretletter.name = "匿名信";
cmd_send_secretletter.help = "。匿名信 对方角色名 内容\n（注：基于当前游戏天数限次，初始化后自动重置）";

cmd_send_secretletter.solve = (ctx, msg, cmdArgs) => {
    // 1. 基础功能开关检查
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_secret_letter === false) {
        seal.replyToSender(ctx, msg, "📪 匿名信功能已关闭。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 身份与权限识别
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    // 获取发送者角色名
    const sendname = Object.keys(a_private_group[platform] || {}).find(
        key => a_private_group[platform][key][0] === uid
    );
    if (!sendname) {
        seal.replyToSender(ctx, msg, "⚠️ 请先创建并绑定角色。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取目标信息
    const toname = cmdArgs.getArgN(1);
    if (!toname || !a_private_group[platform]?.[toname]) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${toname}」，请检查名称。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (sendname === toname) {
        seal.replyToSender(ctx, msg, "⚠️ 不能向自己发送匿名信。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取内容 (正则提取以支持多行)
    const match = msg.message.match(new RegExp(`匿名信 ${toname} ([\\s\\S]+)`));
    if (!match || !match[1].trim()) {
        seal.replyToSender(ctx, msg, "用法：。匿名信 对方角色名 内容");
        return seal.ext.newCmdExecuteResult(true);
    }
    const content = match[1].trim();

    // 3. 【方案 C 核心逻辑】限次与冷却检查
    const gameDay = ext.storageGet("global_days") || "D0";
    let secretLimit = parseInt(ext.storageGet("secretLetterDailyLimit") || "30");
    const cooldownMin = parseInt(ext.storageGet("secretLetterCooldown") || "2")
    
    // 从大表中读取
    let globalStats = JSON.parse(ext.storageGet("global_secret_letter_stats") || "{}");
    let globalCooldowns = JSON.parse(ext.storageGet("global_secret_letter_cooldowns") || "{}");

    const userKey = `${platform}:${uid}`;
    const now = Date.now();

    // 次数限制逻辑 (基于 gameDay，初始化 global_days 后会自动重置)
    let userStat = globalStats[userKey] || { day: "", count: 0 };
    if (userStat.day !== gameDay) {
        userStat = { day: gameDay, count: 0 };
    }
    if (userStat.count >= secretLimit) {
        seal.replyToSender(ctx, msg, `📪 今日匿名信件次数已达上限（${secretLimit} 封）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const currentNum = userStat.count;
    const remainingNum = dailyLimit - userStat.count;


    // 冷却逻辑
    const lastSent = globalCooldowns[userKey] || 0;
    if (now - lastSent < cooldownMin * 60 * 1000) {
        const remaining = Math.ceil((cooldownMin * 60 * 1000 - (now - lastSent)) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 信鸽尚未归笼，请 ${remaining} 分钟后再试~`);
        return seal.ext.newCmdExecuteResult(true);
    }


    // 4. 发送处理 (暴露身份概率逻辑)
    let revealChance = parseInt(ext.storageGet("secretLetterRevealChance") || "15");
    const isRevealed = Math.random() * 100 < revealChance;
    const finalSignature = isRevealed ? `落款：${sendname}（似曾相识的笔迹…）` : `（落款人不详）`;

    // 构造跨群消息
    const targetEntry = a_private_group[platform][toname];
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${targetEntry[0]}`;
    newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    // 5. 最终投递
    seal.replyToSender(ctx, msg, `✉️ 你的匿名信已暗中飞入 ${toname} 的窗前。这是你今日寄出的第 ${currentNum} 封，今日剩余：${remainingNum}。`);
    seal.replyToSender(newctx, newmsg, `📜 ${toname}，你收到一封匿名信件：\n「${content}」\n\n${finalSignature}`);

    // 6. 状态持久化 (存回大表)
    userStat.count += 1;
    userStat.day = gameDay;
    globalStats[userKey] = userStat;
    globalCooldowns[userKey] = now;
    
    ext.storageSet("global_secret_letter_stats", JSON.stringify(globalStats));
    ext.storageSet("global_secret_letter_cooldowns", JSON.stringify(globalCooldowns));

    // 7. 公开发送逻辑 (如果有开启)
    if (JSON.parse(ext.storageGet("secret_letter_public_send") || "false")) {
        let publicChance = parseInt(ext.storageGet("secretLetterPublicChance") || "50");
        if (Math.random() * 100 <= publicChance) {
            const adminGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
            if (adminGroupId) {
                const pubMsg = seal.newMessage();
                pubMsg.groupId = `${platform}-Group:${adminGroupId}`;
                const pubCtx = seal.createTempCtx(ctx.endPoint, pubMsg);
                const info = isRevealed ? `(已暴露: ${sendname})` : `(保持匿名)`;
                seal.replyToSender(pubCtx, pubMsg, `📢 公开匿名信：\n发往「${toname}」\n内容：「${content}」\n${info}`);
            }
        }
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["匿名信"] = cmd_send_secretletter;
// ========================
// 🌠 挂心愿指令（使用类似私约的时间格式）
// ========================
let cmd_post_wish = seal.ext.newCmdItemInfo();
cmd_post_wish.name = "挂心愿";
cmd_post_wish.help = "。挂心愿 1400-1500 地点 心愿内容（匿名发布带时间心愿，天数从全局天数获取）";

cmd_post_wish.solve = (ctx, msg, cmdArgs) => {
  const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
  if (config.enable_wish_system === false) {
    seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭，暂无法使用漂流瓶");
    return seal.ext.newCmdExecuteResult(true);
  }

  const platform = msg.platform;
  const uid = msg.sender.userId;
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  const name = Object.entries(a_private_group[platform] || {}).find(([k, v]) => 
    v[0] === uid.replace(`${platform}:`, "")
  )?.[0];

  if (!name) {
    seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取全局天数
  const globalDay = ext.storageGet("global_days");
  if (!globalDay) {
    seal.replyToSender(ctx, msg, "⚠️ 当前尚未设置全局天数，请先使用 \"。设置天数 D1\"");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  const day = globalDay; // 使用全局天数
  
  const rawTime = cmdArgs.getArgN(1);
  const place = cmdArgs.getArgN(2);
  
  // 从第三个参数开始，把后面的全部拼接
  let contentParts = [];
  for (let i = 3; i <= cmdArgs.args.length; i++) {
    const arg = cmdArgs.getArgN(i);
    if (arg) contentParts.push(arg);
  }
  const content = contentParts.join(" ").trim();

  if (!rawTime || !place || !content) {
    seal.replyToSender(ctx, msg, "格式错误，请使用：挂心愿 1400-1500 地点 想说的话\n示例：挂心愿 1400-1500 餐厅 我想吃大餐");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 统一处理时间格式（支持1100-1200和11:20-12:30两种格式）
  let time = "";
  if (/^\d{4}-\d{4}$/.test(rawTime)) {
    // 格式: 1100-1200 -> 11:00-12:00
    const start = rawTime.slice(0, 2) + ":" + rawTime.slice(2, 4);
    const end = rawTime.slice(5, 7) + ":" + rawTime.slice(7, 9);
    time = `${start}-${end}`;
  } else if (/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/.test(rawTime)) {
    // 格式: 11:20-12:30
    time = rawTime;
  } else {
    seal.replyToSender(ctx, msg,
      `⚠️ 时间参数格式错误：「${rawTime}」\n` +
      `请输入标准格式，如：\n` +
      `· 1100-1200\n` +
      `· 11:20-12:30`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🔒 检查时间是否在允许范围内
  const allowedTimeRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
  if (allowedTimeRanges.length > 0) {
    let isTimeAllowed = false;
    const [userStart, userEnd] = time.split('-');
    
    for (const range of allowedTimeRanges) {
      const [rangeStart, rangeEnd] = range.split('-');
      if (userStart >= rangeStart && userEnd <= rangeEnd) {
        isTimeAllowed = true;
        break;
      }
    }
    
    if (!isTimeAllowed) {
      const allowedRangesText = allowedTimeRanges.map(range => `· ${range}`).join('\n');
      seal.replyToSender(ctx, msg,
        `⚠️ 时间 ${time} 不在允许的范围内\n\n` +
        `📋 当前允许的时间段：\n${allowedRangesText}\n\n` +
        `请选择上述时间段内的预约时间~`);
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  // 检查时间格式有效性
  if (!isValidTimeFormat(time)) {
    seal.replyToSender(ctx, msg, "请输入正确的时间格式，时间段需合法");
    return seal.ext.newCmdExecuteResult(true);
  }

  // ========== 使用公共函数进行地点检查 ==========
  const placeCheck = checkPlaceCommon(platform, name, place, "挂心愿");
  if (!placeCheck.valid) {
    seal.replyToSender(ctx, msg, placeCheck.errorMsg);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 如果有警告信息（地点系统关闭时的提示），显示但不阻止
  if (placeCheck.warningMsg) {
    seal.replyToSender(ctx, msg, placeCheck.warningMsg);
  }
  // ========== 地点检查结束 ==========

  // 🔍 新增：检查时间冲突
  const conflicts = checkAcceptanceConflicts(platform, uid.replace(`${platform}:`, ""), name, day, time);
  if (conflicts.length > 0) {
    const conflictMsg = conflicts.map(conflict => `• ${conflict}`).join('\n');
    seal.replyToSender(ctx, msg, `⚠️ 无法挂出心愿，时间冲突如下：\n${conflictMsg}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🆕 检查用户当前心愿数量（先清理过期心愿）
  let wishPool = JSON.parse(ext.storageGet("a_wishPool") || "[]");
  const now = Date.now();
  const WISH_EXPIRE_TIME = 24 * 60 * 60 * 1000; // 24小时
  wishPool = wishPool.filter(w => now - w.timestamp < WISH_EXPIRE_TIME);
  
  // 统计用户当前有效心愿数量
  const userWishCount = wishPool.filter(w => w.fromId === uid).length;
  const MAX_WISH_PER_USER = 3; // 每人最多3个心愿
  
  if (userWishCount >= MAX_WISH_PER_USER) {
    seal.replyToSender(ctx, msg, `⚠️ 你已发布 ${userWishCount} 个心愿，最多只能同时存在 ${MAX_WISH_PER_USER} 个。请等待心愿被摘取或过期后再发布新的。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查心愿内容长度
  if (content.length > 200) {
    seal.replyToSender(ctx, msg, `⚠️ 心愿内容过长，最多200字，当前 ${content.length} 字`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🆕 生成6-7位的简洁心愿编号
  const generateSimpleWishId = () => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    const length = 6 + Math.floor(Math.random() * 2); // 6或7位
    let result = '';
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  };

  // 确保编号唯一
  let id;
  do {
    id = generateSimpleWishId();
  } while (wishPool.some(w => w.id === id));

  wishPool.push({
    id,
    day,
    time: time,
    place,
    content,
    fromId: uid,
    timestamp: now
  });
  ext.storageSet("a_wishPool", JSON.stringify(wishPool));
  
  const expireTime = new Date(now + WISH_EXPIRE_TIME).toLocaleTimeString();
  seal.replyToSender(ctx, msg, 
    `✅ 你的心愿已放入漂流瓶\n` +
    `📝 编号：${id}\n` +
    `📅 日期：${day}\n` +
    `⏰ 时间：${time}\n` +
    `📍 地点：${place}\n` +
    `⏰ 有效期：24小时（至 ${expireTime}）\n` +
    `📊 你还有 ${MAX_WISH_PER_USER - userWishCount - 1} 个心愿名额\n` +
    `愿有心人拾起。`
  );

   // 🌟 新增：心愿公开发送逻辑
  const wishPublicSendEnabled = JSON.parse(ext.storageGet("wish_public_send") || "false");
  if (wishPublicSendEnabled) {
    const groupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
    if (groupId) {
      const publicMsg = seal.newMessage();
      publicMsg.messageType = "group";
      publicMsg.groupId = `${platform}-Group:${groupId}`;
      publicMsg.sender = {};
      const publicCtx = seal.createTempCtx(ctx.endPoint, publicMsg);
      
      // 格式化时间显示
      const formatTime = (timeStr) => {
        return timeStr.replace('-', ' ~ ');
      };
      
      const publicNotice = 
        `🌠 新的心愿漂流瓶\n` +
        `📝 编号：${id}\n` +
        `📅 日期：${day}\n` +
        `⏰ 时间：${formatTime(time)}\n` +
        `📍 地点：${place}\n` +
        `💌 内容：${content}\n` +
        `\n✨ 使用「摘心愿 ${id}」即可摘取此心愿\n` +
        `⏳ 有效期为24小时`;
      
      seal.replyToSender(publicCtx, publicMsg, publicNotice);
    }
  }

  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["挂心愿"] = cmd_post_wish;

let cmd_view_wish = seal.ext.newCmdItemInfo();
cmd_view_wish.name = "看心愿";
cmd_view_wish.help = "。看心愿（查看当前漂流瓶）";

cmd_view_wish.solve = (ctx, msg) => {
  let wishPool = JSON.parse(ext.storageGet("a_wishPool") || "[]");
  
  // 🆕 清理过期心愿
  const now = Date.now();
  const WISH_EXPIRE_TIME = 24 * 60 * 60 * 1000;
  const expiredWishes = wishPool.filter(w => now - w.timestamp >= WISH_EXPIRE_TIME);
  wishPool = wishPool.filter(w => now - w.timestamp < WISH_EXPIRE_TIME);
  
  // 如果有过期心愿，更新存储
  if (expiredWishes.length > 0) {
    ext.storageSet("a_wishPool", JSON.stringify(wishPool));
    console.log(`[心愿系统] 自动清理了 ${expiredWishes.length} 个过期心愿`);
  }

  if (wishPool.length === 0) {
    seal.replyToSender(ctx, msg, "📭 当前没有可拾取的心愿。");
    return seal.ext.newCmdExecuteResult(true);
  }

  let rep = "📜 当前漂浮的心愿如下：\n";
  wishPool.forEach((w, i) => {
    const remainTime = WISH_EXPIRE_TIME - (now - w.timestamp);
    const remainHours = Math.ceil(remainTime / (60 * 60 * 1000));
    rep += `编号：${w.id}｜时间：${w.day} ${w.time}｜地点：${w.place}｜剩余：${remainHours}小时｜内容：${w.content}\n`;
  });

  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["看心愿"] = cmd_view_wish;

let cmd_pick_wish = seal.ext.newCmdItemInfo();
cmd_pick_wish.name = "摘心愿";
cmd_pick_wish.help = "。摘心愿 心愿编号（根据看心愿的ID）";

cmd_pick_wish.solve = (ctx, msg, cmdArgs) => {
  const wid = cmdArgs.getArgN(1)?.toUpperCase();
  if (!wid) {
    seal.replyToSender(ctx, msg, "请提供要摘取的心愿编号（如：。摘心愿 H78LKD2B）");
    return seal.ext.newCmdExecuteResult(true);
  }

  let wishPool = JSON.parse(ext.storageGet("a_wishPool") || "[]");
  
  // 🆕 先清理过期心愿
  const now = Date.now();
  const WISH_EXPIRE_TIME = 24 * 60 * 60 * 1000;
  const expiredWishes = wishPool.filter(w => now - w.timestamp >= WISH_EXPIRE_TIME);
  wishPool = wishPool.filter(w => now - w.timestamp < WISH_EXPIRE_TIME);
  
  // 如果有过期心愿，更新存储
  if (expiredWishes.length > 0) {
    ext.storageSet("a_wishPool", JSON.stringify(wishPool));
  }

  const wish = wishPool.find(w => w.id === wid);
  if (!wish) {
    seal.replyToSender(ctx, msg, `未找到编号为 ${wid} 的心愿，可能已被摘走或已过期`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🆕 检查不能摘取自己的心愿
  if (msg.sender.userId === wish.fromId) {
    seal.replyToSender(ctx, msg, "❌ 不能摘取自己发布的心愿");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🆕 检查心愿是否过期（双重保险）
  if (now - wish.timestamp >= WISH_EXPIRE_TIME) {
    wishPool = wishPool.filter(w => w.id !== wid);
    ext.storageSet("a_wishPool", JSON.stringify(wishPool));
    seal.replyToSender(ctx, msg, `⚠️ 心愿 ${wid} 已过期，无法摘取`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查摘取者是否有时间冲突
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  const name = Object.entries(a_private_group[platform] || {}).find(([k, v]) => 
    v[0] === uid.replace(`${platform}:`, "")
  )?.[0];

  if (!name) {
    seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取发布者的角色名
  const fromName = Object.entries(a_private_group[platform] || {}).find(([k, v]) => 
    v[0] === wish.fromId.replace(`${platform}:`, "")
  )?.[0] || "匿名者";

  // 🔍 更新：使用统一的冲突检查函数检查双方时间冲突
  const pickerConflicts = checkAcceptanceConflicts(platform, uid.replace(`${platform}:`, ""), name, wish.day, wish.time);
  const publisherConflicts = checkAcceptanceConflicts(platform, wish.fromId.replace(`${platform}:`, ""), fromName, wish.day, wish.time);
  
  // 检查摘取者冲突
  if (pickerConflicts.length > 0) {
    const conflictMsg = pickerConflicts.map(conflict => `• ${conflict}`).join('\n');
    seal.replyToSender(ctx, msg, `⚠️ 你无法摘取该心愿，时间冲突如下：\n${conflictMsg}`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 检查发布者冲突
  if (publisherConflicts.length > 0) {
    const conflictMsg = publisherConflicts.map(conflict => `• ${conflict}`).join('\n');
    seal.replyToSender(ctx, msg, `⚠️ 心愿发布者无法继续此心愿，原因如下：\n${conflictMsg}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 分配群号
  const groupList = JSON.parse(ext.storageGet("group") || "[]");
  const free = groupList.find(g => !g.endsWith("_占用"));
  if (!free) {
    seal.replyToSender(ctx, msg, `当前无可用群号，稍后再试`);
    return seal.ext.newCmdExecuteResult(true);
  }
  const gid = free;
  groupList.splice(groupList.indexOf(gid), 1);
  groupList.push(gid + "_占用");
  ext.storageSet("group", JSON.stringify(groupList));

  // 加入b_confirmedSchedule
  const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
  for (let who of [uid, wish.fromId]) {
    const whoName = who === uid ? name : fromName;
    const partnerName = who === uid ? fromName : name;
    
    if (!b_confirmedSchedule[who]) b_confirmedSchedule[who] = [];
    b_confirmedSchedule[who].push({
      day: wish.day,
      time: wish.time,
      subtype: "心愿",
      place: wish.place, // 使用心愿中存储的地点
      partner: partnerName,
      group: gid,
      status: "active"
    });
  }

  // 🧹 同步清理拾愿人与发起人那边的冲突请求
  for (let who of [uid, wish.fromId]) {
    const whoName = who === uid ? name : fromName;
    cleanupConflictsAndNotify(platform, who, whoName, wish.day, wish.time, ctx, msg);
  }

  // 通知双方
  const participants = [
    { id: uid, name: name },
    { id: wish.fromId, name: fromName }
  ];
  
  for (let participant of participants) {
    const groupId = a_private_group[platform]?.[participant.name]?.[1];
    if (!groupId) {
      console.log(`[❗️] 无法找到 ${participant.name} 的群组`);
      continue;
    }
    
    const msg2 = seal.newMessage();
    msg2.messageType = "group";
    msg2.sender = {};
    msg2.sender.userId = `${platform}:${participant.id}`;
    msg2.groupId = `${platform}-Group:${groupId}`;
    const ctx2 = seal.createTempCtx(ctx.endPoint, msg2);
    
    const otherName = participant.id === uid ? fromName : name;
    seal.replyToSender(ctx2, msg2, 
      `💫 命运之线已交织！你与 ${otherName} 的心愿相遇。\n` +
      `⏰ 时间：${wish.day} ${wish.time}\n` +
      `📍 地点：${wish.place}\n` +
      `💌 心愿内容：${wish.content}\n` +
      `🏮 小群：${gid}\n` +
      `愿此相逢如星火，点亮彼此时光。`
    );
  }

  // 群内公告 - 修改这里：显示心愿内容而不是"心愿交点"
  const notice = seal.newMessage();
  notice.messageType = "group";
  notice.sender = {};
  notice.sender.userId = `${platform}:${msg.sender.userId}`;
  notice.groupId = `${platform}-Group:${gid}`;
  const noticeCtx = seal.createTempCtx(ctx.endPoint, notice);
  
  // 对心愿内容进行简化和美化处理
  const displayContent = wish.content.length > 30 ? 
    wish.content.substring(0, 30) + "..." : wish.content;
  
  seal.replyToSender(noticeCtx, notice,
    `小群创建成功：心愿 ${wish.day} ${wish.time} ${wish.place} 「${displayContent}」 ${fromName}&${name}`);
    setGroupName(noticeCtx, notice, noticeCtx.group.groupId, `心愿 ${wish.day} ${wish.time} ${wish.place} ${fromName}&${name}`)  
    
    // 触发目击检查
    triggerSightingCheck(platform, wish.day, wish.time, wish.place, 
        [fromName, name], gid, "心愿");

  // 从心愿池中删除
  wishPool = wishPool.filter(w => w.id !== wid);
  ext.storageSet("a_wishPool", JSON.stringify(wishPool));
  ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
  
  seal.replyToSender(ctx, msg, `🎉 摘取成功！小群 ${gid} 已建立，愿此愿圆满。`);
  recordMeetingAndAnnounce("心愿", platform, ctx, ctx.endPoint);
  if (wish) { // 在 cmd_pick_wish 指令中
        initGroupTimer(platform, gid, "心愿", [fromName, name], fromName);
    }
  return seal.ext.newCmdExecuteResult(true);
};


// 🆕 添加撤回心愿指令
let cmd_withdraw_wish = seal.ext.newCmdItemInfo();
cmd_withdraw_wish.name = "撤心愿";
cmd_withdraw_wish.help = "。撤心愿 [心愿编号]（撤回自己的心愿，不填编号则列出可撤回的心愿）";

cmd_withdraw_wish.solve = (ctx, msg, cmdArgs) => {
  const wid = cmdArgs.getArgN(1)?.toUpperCase();
  const platform = msg.platform;
  const uid = msg.sender.userId;

  let wishPool = JSON.parse(ext.storageGet("a_wishPool") || "[]");
  
  // 清理过期心愿
  const now = Date.now();
  const WISH_EXPIRE_TIME = 24 * 60 * 60 * 1000;
  wishPool = wishPool.filter(w => now - w.timestamp < WISH_EXPIRE_TIME);
  ext.storageSet("a_wishPool", JSON.stringify(wishPool));

  const myWishes = wishPool.filter(w => w.fromId === uid);
  
  if (myWishes.length === 0) {
    seal.replyToSender(ctx, msg, "📭 你当前没有可撤回的心愿");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!wid) {
    // 列出可撤回的心愿
    let rep = "📜 你可撤回的心愿：\n";
    myWishes.forEach((w, i) => {
      const remainTime = WISH_EXPIRE_TIME - (now - w.timestamp);
      const remainHours = Math.ceil(remainTime / (60 * 60 * 1000));
      rep += `编号：${w.id}｜时间：${w.day} ${w.time}｜地点：${w.place}｜剩余：${remainHours}小时｜内容：${w.content}\n`;
    });
    rep += `\n使用「。撤心愿 编号」撤回指定心愿`;
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 撤回指定心愿
  const wish = myWishes.find(w => w.id === wid);
  if (!wish) {
    seal.replyToSender(ctx, msg, `未找到编号为 ${wid} 的心愿，请检查是否属于你`);
    return seal.ext.newCmdExecuteResult(true);
  }

  wishPool = wishPool.filter(w => w.id !== wid);
  ext.storageSet("a_wishPool", JSON.stringify(wishPool));
  
  seal.replyToSender(ctx, msg, `✅ 已撤回心愿 ${wid}\n📝 内容：${wish.content}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["摘心愿"] = cmd_pick_wish;
ext.cmdMap["撤心愿"] = cmd_withdraw_wish;

let cmd_send_chaos_letter = seal.ext.newCmdItemInfo();
cmd_send_chaos_letter.name = "寄信";
cmd_send_chaos_letter.help = "。寄信 对方角色名 内容（有概率送错、模糊、涂改、丢失）";

cmd_send_chaos_letter.solve = (ctx, msg, cmdArgs) => {
  const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
  if (config.enable_chaos_letter === false) {
    seal.replyToSender(ctx, msg, "🕊️ 寄信功能已关闭，无法发送寄信");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🔐 新增：检查用户权限
  const platform = msg.platform;
  const uid = msg.sender.userId.replace(`${platform}:`, "");
  
  // 获取发送者角色名
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  if (!a_private_group[platform]) a_private_group[platform] = {};
  
  const sendname = Object.entries(a_private_group[platform])
    .find(([_, val]) => val[0] === uid)?.[0];
  if (!sendname) {
    seal.replyToSender(ctx, msg, `请先使用「创建新角色」绑定角色`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查该角色是否被禁止使用寄信功能
  if (!isUserFeatureEnabled(sendname, "enable_chaos_letter")) {
    seal.replyToSender(ctx, msg, `🚫 您已被禁止使用寄信功能`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 🎲 读取配置
  let chaosConfig = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
  const defaultConfig = {
    misdelivery: 0,      // 送错
    blackoutText: 0,     // 涂改
    loseContent: 0,      // 丢失
    antonymReplace: 0,   // 反义
    reverseOrder: 0,     // 乱序
    fuzzySignature: 0,   // 模糊
    mistakenSignature: 0, // 混淆
    poeticSignature: 0,  // 诗意
    dailyLimit: 5,       // 每日上限
    publicChance: 50     // 公开概率（0-100）
  };
  chaosConfig = { ...defaultConfig, ...chaosConfig };

  // ⏳ 冷却机制（2分钟）
  const cooldownKey = `chaos_letter_cooldown_${platform}:${uid}`;
  const lastSent = parseInt(ext.storageGet(cooldownKey) || "0");
  const now = Date.now();
  let mailCooldownMin = parseInt(ext.storageGet("mailCooldown") || "60")
  const cooldownDuration = mailCooldownMin * 60 * 1000;

  if (now - lastSent < cooldownDuration) {
    const remaining = Math.ceil((cooldownDuration - (now - lastSent)) / 60000);
    seal.replyToSender(ctx, msg, `无法发送，发送过于频繁，正在冷却中，请稍候 ${remaining} 分钟再试`);
    return seal.ext.newCmdExecuteResult(true);
  }
  ext.storageSet(cooldownKey, now.toString());

  // 📅 每日寄信次数限制 (方案 C 大表版)
  const gameDay = ext.storageGet("global_days") || "D0"; 
  const globalChaosCounts = JSON.parse(ext.storageGet("global_chaos_letter_counts") || "{}");
  const userKey = `${platform}:${uid}`;

  // 获取该用户记录
  let userRec = globalChaosCounts[userKey] || { day: "", count: 0 };
  
  // 如果天数对不上（新的一天或重置了），重置计数
  if (userRec.day !== gameDay) {
    userRec = { day: gameDay, count: 0 };
  }

  if (userRec.count >= chaosConfig.dailyLimit) {
    seal.replyToSender(ctx, msg, `🕊️ 今日寄信次数已达上限（${chaosConfig.dailyLimit}次），请明日再试`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 记录本次使用 (保存回大表)
  userRec.count += 1;
  userRec.day = gameDay;
  globalChaosCounts[userKey] = userRec;
  ext.storageSet("global_chaos_letter_counts", JSON.stringify(globalChaosCounts));

  // 计算当前是第几封和剩余封数
  const currentNum = userRec.count;
  const remainingNum = chaosConfig.dailyLimit - userRec.count;

  const toname = cmdArgs.getArgN(1);
  const raw = msg.message.match(new RegExp(`寄信 ${toname} ([\\s\\S]+)`));
  if (!toname || !raw || !raw[1]) {
    seal.replyToSender(ctx, msg, `你的格式有误，发送失败，用法：。寄信 对方角色名 内容`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const contentOriginal = raw[1].trim();
  if (!a_private_group[platform]) a_private_group[platform] = {};


  if (!a_private_group[platform][toname]) {
    seal.replyToSender(ctx, msg, `发送失败，未找到收信人 ${toname} 的绑定信息`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const allNames = Object.keys(a_private_group[platform]);
  let content = contentOriginal;

  const effects = {
    loseContent: Math.random() < (chaosConfig.loseContent / 100),
    blackoutText: Math.random() < (chaosConfig.blackoutText / 100),
    reverseOrder: Math.random() < (chaosConfig.reverseOrder / 100),
    misdelivery: Math.random() < (chaosConfig.misdelivery / 100),
    antonymReplace: Math.random() < (chaosConfig.antonymReplace / 100)
  };

  // 🖋️ 落款混淆机制（三类）
  const fuzzyChance = chaosConfig.fuzzySignature / 100;
  const mistakenChance = chaosConfig.mistakenSignature / 100;
  const poeticChance = chaosConfig.poeticSignature / 100;

  const antonyms = {
  "喜": "厌",
  "爱": "恨",
  "美": "丑",
  "光": "暗",
  "乐": "痛",
  "真": "假",
  "生": "死",
  "善": "恶",
  "高": "低",
  "天": "地",
  "长": "短",
  "白": "黑",
  "热": "冷",
  "强": "弱",
  "新": "旧",
  "福": "祸",
  "香": "臭",
  "宁": "乱",
  "大": "小",
  "他": "她",
  "我": "鸡",
  "你": "鸭",
  "您": "鹅",
  "一": "二",
  "不": "就",
  "饭": "牡丹",
  "好": "随便",
 "荤": "素",
  "素": "荤",

  // 🎭 新增情感&人格
  "忠": "叛",
  "勇": "怯",
  "智": "愚",
  "信": "疑",
  "笑": "哭",
  "仁": "残",
  "义": "贼",
  "德": "罪",
  "敬": "辱",

  // 🌓 抽象&命运
  "命": "运",
  "正": "邪",
  "光": "影",
  "昼": "夜",
  "醒": "梦",
  "醒": "醉",
  "上": "下",
  "主": "仆",
  "君": "贼",
  "王": "奴",
  "皇": "民",
  "神": "魔",
  "福": "灾",

  // 💬 人物代称 & 关系
  "兄": "弟",
  "姐": "妹",
  "父": "子",
  "主": "仆",
  "男": "女",
  "公": "私",
  "夫": "妻",
  "敌": "友",

  // 🕊️ 宗教 & 道德
  "圣": "俗",
  "洁": "污",
  "灵": "尸",
  "罪": "赎",
  "光": "劫",
  "愿": "怨",
  "祷": "咒",
  "祝": "诅",

  // 🏞️ 自然 & 场所
  "海": "陆",
  "山": "谷",
  "火": "水",
  "风": "土",
  "东": "西",
  "南": "北",
  "春": "秋",
  "夏": "冬",

  // ⏳ 时间与变化
  "早": "晚",
  "旧": "新",
  "前": "后",
  "升": "降",
  "快": "慢",
  "始": "终",
  "永": "暂",
  "常": "变"
};

  // 替换逻辑
  if (effects.antonymReplace) {
    content = content.split('').map(char =>
      antonyms[char] ? antonyms[char] : char
    ).join('');
  }

  // ✂️ 内容截断
  if (effects.loseContent && content.length > 6) {
    const cut = Math.floor(content.length * 0.3);
    content = content.slice(0, content.length - cut) + "……";
  }

  // 🔤 字迹涂改
  if (effects.blackoutText) {
    const blackout = ["◼︎", "█", "■", "▮"];
    content = content.split('').map(c =>
      Math.random() < 0.20 ? blackout[Math.floor(Math.random() * blackout.length)] : c
    ).join('');
  }

  // 🧠 顺序颠倒
  if (effects.reverseOrder) {
    const sentences = content.split(/(?<=[。！？!?\n])/).filter(Boolean);
    const processed = sentences.map(s => {
      if (Math.random() < 0.3) {  // 仅处理约 30% 的句子
        const words = [...s.trim()];
        if (words.length > 1) {
          const r = Math.random();
          if (r < 0.5) {
            words.reverse(); // 全句倒转
          } else {
            // Fisher–Yates 洗牌
            for (let i = words.length - 1; i > 0; i--) {
              const j = Math.floor(Math.random() * (i + 1));
              [words[i], words[j]] = [words[j], words[i]];
            }
          }
          return words.join('') + (/[。！？!?]$/.test(s) ? '' : '。');
        }
      }
      return s; // 保持原样
    });
    content = processed.join('');
  }
  let finalSignature = `落款：${sendname}`;

const nameVariants = {
  fuzzy: ["某位阁下", "昨晚托梦给你的那位","你的头号黑粉","一个不愿意透露姓名的路人甲","那个谁（突然忘了叫啥）","？", "……"],
  mistaken: Object.keys(a_private_group[platform]).filter(n => n !== sendname),
  poetic: [
    "正在找拖鞋的哲学家",
    "被生活放鸽子的养鸽人",
    "欠费停机的纯爱灵魂",
    "火锅店编外评论家",
    "深夜谈判的蚊子受害者",
    "仙人掌杀手",
    "正在等外卖的救世主",
    "刚把糖当盐撒的厨子",
    "试图感化蚊子的圣人",
    "没带准考证的梦中勇士",
    "购物车里的定居者",
    "闹钟暗杀计划执行人",
    "正在自闭的野生影帝",
    "想退休的带薪摸鱼家",
    "袜子攒了一盆的人",
    "临期面包品鉴师",
    "离家出走的良心本人",
    "早八魂的破碎残片",
    "在淋浴头下开演唱会的巨星",
    "那个忘了买邮票的穷鬼"
]
};

  const r = Math.random();
  if (r < fuzzyChance && nameVariants.fuzzy.length) {
    finalSignature = `落款：${nameVariants.fuzzy[Math.floor(Math.random() * nameVariants.fuzzy.length)]}（墨迹模糊）`;
  } else if (r < fuzzyChance + mistakenChance && nameVariants.mistaken.length) {
    finalSignature = `落款：${nameVariants.mistaken[Math.floor(Math.random() * nameVariants.mistaken.length)]}`;
  } else if (r < fuzzyChance + mistakenChance + poeticChance && nameVariants.poetic.length) {
    finalSignature = `落款：${nameVariants.poetic[Math.floor(Math.random() * nameVariants.poetic.length)]}`;
  }

  // 📤 投错人
  let trueRecipient = toname;
  if (effects.misdelivery && allNames.length > 1) {
    const candidates = allNames.filter(n => n !== toname);
    trueRecipient = candidates[Math.floor(Math.random() * candidates.length)];
  }

  const targetEntry = a_private_group[platform][trueRecipient];
  if (!targetEntry) {
    seal.replyToSender(ctx, msg, `发送失败，⚠️ 找不到 ${trueRecipient} 的私密群，投递失败`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const groupId = targetEntry[1];
  const targetId = targetEntry[0];

  // 🕊️ 构造与投递
  const newmsg = seal.newMessage();
  newmsg.messageType = "group";
  newmsg.sender = {};
  newmsg.sender.userId = `${platform}:${targetId}`;
  newmsg.groupId = `${platform}-Group:${groupId}`;
  const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

  const notice = `📜 ${toname}，你收到一封书信：\n「${content}」\n\n${finalSignature}`;
  // 修改这里的回复话术
  const successReply = `🕊️ 发送成功！这是你今日投递的第 ${currentNum} 封信，今日还可发送 ${remainingNum} 封。一只鸽子已向远方飞去……`;
  seal.replyToSender(ctx, msg, successReply);
  seal.replyToSender(newctx, newmsg, notice);

  // 📣 广播事件（如有需记录）
  recordMeetingAndAnnounce?.("寄信", platform, ctx, ctx.endPoint);

  // 🆕 新增：寄信公开发送逻辑
  const letterPublicSendEnabled = JSON.parse(ext.storageGet("letter_public_send") || "false");
  if (letterPublicSendEnabled) {
    // 使用配置中的公开概率
    const randomNum = Math.floor(Math.random() * 100) + 1; // 1-100
    if (randomNum <= chaosConfig.publicChance) { // 小于等于配置值时公开
      const groupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
      if (groupId) {
        const publicMsg = seal.newMessage();
        publicMsg.messageType = "group";
        publicMsg.groupId = `${platform}-Group:${groupId}`;
        publicMsg.sender = {};
        const publicCtx = seal.createTempCtx(ctx.endPoint, publicMsg);
        
        const publicNotice = `💌 公开的信件：\n来自「${finalSignature}」→「${toname}」\n内容：「${content}」\n\n（随机数：${randomNum}，触发公开，设置概率：${chaosConfig.publicChance}%）`;
        seal.replyToSender(publicCtx, publicMsg, publicNotice);
      }
    }
  }

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["寄信"] = cmd_send_chaos_letter;

// ========================
// 🎯 群发信息指令
// ========================

let cmd_broadcast_message = seal.ext.newCmdItemInfo();
cmd_broadcast_message.name = "群发信息";
cmd_broadcast_message.help = "向所有已绑定角色的个人群发送相同的信息\n格式：.群发信息 内容";

cmd_broadcast_message.solve = (ctx, msg, cmdArgs) => {
  // 🔐 检查管理员权限
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "🚫 该指令仅限管理员使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取消息内容
  const rawContent = msg.message.replace(/^。群发信息\s+/, '').trim();
  if (!rawContent) {
    seal.replyToSender(ctx, msg, "📝 用法：.群发信息 内容");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取所有绑定的个人群信息
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  
  // 统计信息
  let successCount = 0;
  let failedCount = 0;
  const platform = msg.platform;
  
  // 检查当前平台是否有绑定的个人群
  if (!a_private_group[platform] || Object.keys(a_private_group[platform]).length === 0) {
    seal.replyToSender(ctx, msg, "⚠️ 当前平台没有找到任何绑定的个人群");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取当前游戏天数（用于上下文）
  const gameDay = ext.storageGet("global_days") || "D0";
  
  // 构建消息内容（可以添加天数信息）
  const messageContent = `📢 群发信息（${gameDay}）\n\n${rawContent}\n\n── 系统广播`;
  
  // 获取所有角色名和对应的群信息
  const entries = Object.entries(a_private_group[platform]);
  
  // 使用递归函数分批发送，避免消息轰炸
  const sendMessagesInBatches = (index) => {
    if (index >= entries.length) {
      // 所有消息发送完成，反馈结果
      const resultMessage = [
        "📤 群发信息完成",
        "────────────────────",
        `✅ 成功发送：${successCount} 个个人群`,
        failedCount > 0 ? `❌ 发送失败：${failedCount} 个个人群` : "🎉 所有消息均发送成功",
        "",
        "💡 注意：",
        "- 消息已发送到所有已绑定角色的个人群",
        "- 如果某些角色没有收到消息，请检查其个人群是否有效"
      ].join('\n');
      
      seal.replyToSender(ctx, msg, resultMessage);
      
      return;
    }
    
    const [characterName, groupInfo] = entries[index];
    
    try {
      const [userId, groupId] = groupInfo;
      
      if (!userId || !groupId) {
        console.warn(`跳过无效的个人群绑定：${characterName}`);
        failedCount++;
        // 继续发送下一个
        setTimeout(() => sendMessagesInBatches(index + 1), 50);
        return;
      }
      
      // 创建临时消息和上下文
      const newmsg = seal.newMessage();
      newmsg.messageType = "group";
      newmsg.sender = {};
      newmsg.sender.userId = `${platform}:${userId}`;
      newmsg.groupId = `${platform}-Group:${groupId}`;
      const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
      
      // 发送消息
      seal.replyToSender(newctx, newmsg, messageContent);
      successCount++;
      
    } catch (error) {
      console.error(`发送消息到 ${characterName} 的个人群失败:`, error);
      failedCount++;
    }
    
    // 每发送5条消息后稍作停顿（使用setTimeout实现异步延迟）
    if ((index + 1) % 5 === 0) {
      setTimeout(() => sendMessagesInBatches(index + 1), 200);
    } else {
      // 立即发送下一条
      setTimeout(() => sendMessagesInBatches(index + 1), 50);
    }
  };
  
  // 开始发送消息
  setTimeout(() => sendMessagesInBatches(0), 100);
  
  // 先回复一个"正在发送"的提示
  seal.replyToSender(ctx, msg, "⏳ 正在群发消息，请稍候...");
  
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["群发信息"] = cmd_broadcast_message;

/**
 * 将关系线细节平铺转发到目标群 (登记名 + 真实QQ头像)
 * @param {object} ctx 上下文
 * @param {object} msg 消息对象
 * @param {string} toRoleName 对方角色名（用于获取对方QQ和可能的群）
 * @param {string} fromRoleName 当前用户角色名（用于获取自己的群，也用于节点判断）
 * @param {Array} details 细节数组
 * @param {boolean} self true=发到自己群，false=发到对方群
 */
function sendCombinedDetails(ctx, msg, toRoleName, fromRoleName, details, self) {
    const platform = msg.platform;
    const groups = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 1. 获取对方的绑定信息（用于头像和可能的目标群）
    const toAddr = groups[platform]?.[toRoleName];
    if (!toAddr || !details || details.length === 0) return;
    const toUid = toAddr[0]; // 对方真实QQ

    // 2. 获取自己的真实QQ
    const sourceUid = msg.sender.userId.replace(`${platform}:`, "");

    // 3. 确定目标群ID
    let targetGid;
    if (self) {
        // 发到自己群：用当前用户角色名获取自己的群
        const selfAddr = groups[platform]?.[fromRoleName];
        if (!selfAddr) return; // 自己未绑定群
        targetGid = selfAddr[1];
    } else {
        // 发到对方群：直接用对方的群
        targetGid = toAddr[1];
    }

    // 4. 获取当前用户角色名（也可直接用 fromRoleName，但保持与原有逻辑一致）
    const sourceRoleName = RelationshipUtils.getRoleName(ctx, msg, platform);

    // 5. 构造节点
    const nodes = details.map(d => {
        const isFromMe = (d.from === sourceRoleName); // 判断是谁说的
        return {
            type: "node",
            data: {
                name: d.from,                      // 显示角色名
                uin: isFromMe ? sourceUid : toUid, // 关键修正：对方永远用 toUid
                content: d.text
            }
        };
    });

    // 6. 插入页眉（根据 self 调整文字）
    const headerContent = self
        ? `📜 你与「${toRoleName}」的关系细节：`
        : `📜 角色「${sourceRoleName}」更新了与你的关系细节：`;

    nodes.unshift({
        type: "node",
        data: {
            name: "关系线档案",
            uin: "10001",
            content: headerContent
        }
    });

    // 7. 发送
    ws({
        action: "send_group_forward_msg",
        params: {
            group_id: parseInt(targetGid.replace(/[^\d]/g, ""), 10),
            messages: nodes
        }
    }, ctx, msg, "");
}

// 辅助函数：获取对方绑定的 [uid, gid]
function getTargetAddr(platform, roleName) {
    const groups = JSON.parse(ext.storageGet("a_private_group") || "{}");
    return groups[platform]?.[roleName];
}

const RelationshipUtils = {
    getRoleName: (ctx, msg, platform) => {
        const uid = msg.sender.userId.replace(`${platform}:`, "");
        const groups = JSON.parse(ext.storageGet("a_private_group") || "{}");
        return Object.entries(groups[platform] || {}).find(([_, v]) => v[0] === uid)?.[0];
    },
    getData: (key) => JSON.parse(ext.storageGet(key) || "{}"),
    setData: (key, data) => ext.storageSet(key, JSON.stringify(data)),
    isEnabled: () => JSON.parse(ext.storageGet("relationship_system_enabled") || "true")
};

let cmd_add_rel_detail = seal.ext.newCmdItemInfo();
cmd_add_rel_detail.name = "添加关系线细节";
cmd_add_rel_detail.solve = (ctx, msg, cmdArgs) => {
    if (!RelationshipUtils.isEnabled()) return seal.replyToSender(ctx, msg, "❌ 系统已关闭");

    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);
    const content = cmdArgs.args.slice(1).join(' ').trim();

    if (!sendName || !toName || !content) return seal.replyToSender(ctx, msg, "格式：。添加关系线细节 对方名 内容");
    if (sendName === toName) return seal.replyToSender(ctx, msg, "⚠️ 你不能跟自己建立关系线哦。");

    let relData = RelationshipUtils.getData("relationship_lines") || {};
    if (!relData[platform]) relData[platform] = {};

    // 1. 统一查找逻辑：确保 sendName 和 toName 在结构中存在
    if (!relData[platform][sendName]) relData[platform][sendName] = {};
    if (!relData[platform][toName]) relData[platform][toName] = {};

    // 2. 获取现有关系引用（双向兼容）
    let rel = relData[platform][sendName][toName] || relData[platform][toName][sendName];
    
    // 3. 如果是新关系，进行初始化
    if (!rel) {
        const maxRel = parseInt(ext.storageGet("max_relationships_per_user") || "20");
        const currentCount = Object.values(relData[platform][sendName]).filter(r => r.initiator === sendName).length;
        
        if (currentCount >= maxRel) return seal.replyToSender(ctx, msg, `⚠️ 你的发起额度已达上限 (${maxRel})`);
        
        // 关键修复：显式初始化 details 数组
        rel = { 
            initiator: sendName, 
            confirmed: false, 
            details: [] 
        };
        
        seal.replyToSender(ctx, msg, `✨ 已成功向「${toName}」发起关系线邀请并记录细节。`);
    }

    // 4. 再次检查细节数组是否存在（防范未知异常）
    if (!rel.details) rel.details = [];

    // 5. 记录细节
    rel.details.push({ text: content, from: sendName });

    // 6. 镜像存储引用
    relData[platform][sendName][toName] = rel;
    relData[platform][toName][sendName] = rel;

    RelationshipUtils.setData("relationship_lines", relData);

    // 7. 同步通知
    const addr = getTargetAddr(platform, toName);
    if (addr) {
        sendNewDetailNotification(ctx, msg, toName, content, sendName, addr[1]);
        sendCombinedDetails(ctx, msg, toName, sendName,rel.details,false);
        seal.replyToSender(ctx, msg, `✅ 细节已同步至「${toName}」的绑定群 (${addr[1]})`);
    } else {
        seal.replyToSender(ctx, msg, `✅ 细节已记录，但「${toName}」尚未绑定注册群，无法实时同步。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["添加关系线细节"] = cmd_add_rel_detail;

/**
 * 向对方绑定群发送一条新细节通知（普通消息）
 */
function sendNewDetailNotification(ctx, msg, toRoleName, content, fromRoleName, targetGid) {
    const platform = msg.platform;
    const groups = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const toAddr = groups[platform]?.[toRoleName];
    if (!toAddr) return;

    // 提取纯数字群号
    const targetGidNum = parseInt(targetGid.replace(/[^\d]/g, ""), 10);
    if (isNaN(targetGidNum)) return;

    // 构造消息文本（可自定义格式）
    const message = `📝 来自「${fromRoleName}」的新关系细节：\n${content}\n\n（使用「。查看关系线 ${fromRoleName}」查看完整记录）`;

    ws({
        action: "send_group_msg",
        params: {
            group_id: targetGidNum,
            message: message
        }
    }, ctx, msg, "");
}

let cmd_confirm_relationship = seal.ext.newCmdItemInfo();
cmd_confirm_relationship.name = "确认关系线";
cmd_confirm_relationship.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);

    let relData = RelationshipUtils.getData("relationship_lines");
    if (!relData[platform]?.[sendName]?.[toName]) return seal.replyToSender(ctx, msg, "未找到该关系线");

    relData[platform][sendName][toName].confirmed = true;
    if (relData[platform][toName]?.[sendName]) relData[platform][toName][sendName].confirmed = true;

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 你已确认与「${toName}」的关系线为完成状态。`);

    // Notify 对方
    const addr = getTargetAddr(platform, toName);
    if (addr) {
        ws({ "action": "send_group_msg", "params": { "group_id": parseInt(addr[1]), "message": `🤝 「${sendName}」已确认并完成了你们的关系线！` } }, ctx, msg, "");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["确认关系线"] = cmd_confirm_relationship;

let cmd_set_forced_rel = seal.ext.newCmdItemInfo();
cmd_set_forced_rel.name = "设置强制关系线";
cmd_set_forced_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "权限不足");
    const platform = msg.platform;
    const nameA = cmdArgs.getArgN(1);
    const nameB = cmdArgs.getArgN(2);

    // 修正：从索引 2 开始切片（即第3个参数开始的所有内容）
    const content = cmdArgs.args.slice(2).join(' ').trim();

    if (!nameA || !nameB || !content) {
        return seal.replyToSender(ctx, msg, "格式：。设置强制关系线 角色A 角色B 描述内容");
    }

    let relData = RelationshipUtils.getData("relationship_lines");
    const forceNode = {
        initiator: "SYSTEM", // 系统发起，不占份额
        confirmed: true,
        isMandatory: true,
        details: [{ text: `[系统设定] ${content}`, time: new Date().toLocaleString(), from: "管理员" }]
    };

    if (!relData[platform]) relData[platform] = {};
    if (!relData[platform][nameA]) relData[platform][nameA] = {};
    if (!relData[platform][nameB]) relData[platform][nameB] = {};

    relData[platform][nameA][nameB] = forceNode;
    relData[platform][nameB][nameA] = { ...forceNode, received: true }; // B 端标记为收到

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 已成功为「${nameA}」与「${nameB}」建立强制关系线。`);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置强制关系线"] = cmd_set_forced_rel;

// 删除
let cmd_del_rel = seal.ext.newCmdItemInfo();
cmd_del_rel.name = "删除关系线";
cmd_del_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return;
    const platform = msg.platform, nameA = cmdArgs.getArgN(1), nameB = cmdArgs.getArgN(2);
    let data = RelationshipUtils.getData("relationship_lines");
    if (data[platform]) {
        if (data[platform][nameA]) delete data[platform][nameA][nameB];
        if (data[platform][nameB]) delete data[platform][nameB][nameA];
        RelationshipUtils.setData("relationship_lines", data);
        seal.replyToSender(ctx, msg, "✅ 已删除该关系线");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除关系线"] = cmd_del_rel;

// 清空 (含验证码)
let cmd_clear_rel = seal.ext.newCmdItemInfo();
cmd_clear_rel.name = "清空关系线";
cmd_clear_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return;
    const code = cmdArgs.getArgN(1);
    const expected = `${String(new Date().getMonth() + 1).padStart(2,'0')}${String(new Date().getDate()).padStart(2,'0')}`;
    if (code !== expected) return seal.replyToSender(ctx, msg, `⚠️ 危险操作！输入确认码：${expected}`);
    
    let data = RelationshipUtils.getData("relationship_lines");
    delete data[msg.platform];
    RelationshipUtils.setData("relationship_lines", data);
    seal.replyToSender(ctx, msg, "🔥 已清空当前平台所有关系线");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空关系线"] = cmd_clear_rel;

// ========================
// ✏️ 指令：删除最后细节
// ========================
let cmd_del_last_detail = seal.ext.newCmdItemInfo();
cmd_del_last_detail.name = "撤回关系细节";
cmd_del_last_detail.help = "。撤回关系细节 对方角色名 (删除你发给对方的最后一条细节)";

cmd_del_last_detail.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);

    if (!sendName || !toName) return seal.replyToSender(ctx, msg, "格式：。撤回关系细节 对方角色名");

    let relData = RelationshipUtils.getData("relationship_lines");
    let rel = relData[platform]?.[sendName]?.[toName];

    if (!rel || !rel.details || rel.details.length === 0) {
        return seal.replyToSender(ctx, msg, "没有可撤回的细节记录。");
    }

    // 只能撤回自己发的最后一条
    const lastIdx = rel.details.length - 1;
    if (rel.details[lastIdx].from !== sendName) {
        return seal.replyToSender(ctx, msg, "最后一条记录不是你发送的，无法撤回。");
    }

    const removed = rel.details.pop();
    // 同步对方
    if (relData[platform][toName]?.[sendName]?.details) {
        relData[platform][toName][sendName].details.pop();
    }

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 已成功撤回内容：\n"${removed.text}"`);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤回关系细节"] = cmd_del_last_detail;

let cmd_view_relationship = seal.ext.newCmdItemInfo();
cmd_view_relationship.name = "查看关系线";
cmd_view_relationship.help = "。查看关系线 [对方名]\n(不加名字：看列表；加名字：发送合并转发细节)";

cmd_view_relationship.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    if (!sendName) return seal.replyToSender(ctx, msg, "请先绑定角色");

    const toName = cmdArgs.getArgN(1);
    let relData = RelationshipUtils.getData("relationship_lines");
    const myRels = relData[platform]?.[sendName] || {};

    // --- 场景 A: 后面加了名字，执行合并转发查看 ---
    if (toName) {
        const rel = myRels[toName];
        if (!rel) return seal.replyToSender(ctx, msg, `你与「${toName}」之间暂无关系记录。`);
        
        if (!rel.details || rel.details.length === 0) {
            return seal.replyToSender(ctx, msg, `你与「${toName}」虽有关系线，但尚未添加任何细节。`);
        }

        // 执行合并转发
        sendCombinedDetails(ctx, msg, toName, sendName,rel.details,true);
        return seal.ext.newCmdExecuteResult(true);
    }

    // --- 场景 B: 没加名字，显示关系线汇总列表 ---
    let reply = `📚 「${sendName}」的关系线列表：\n`;
    const maxRel = parseInt(ext.storageGet("max_relationships_per_user") || "20");
    
    // 统计主动发起的条数 (排除 SYSTEM 发起的强制线)
    let activeCount = 0;
    let listContent = "";

    Object.entries(myRels).forEach(([name, data]) => {
        const isSystem = data.initiator === "SYSTEM";
        if (!isSystem && data.initiator === sendName) activeCount++;
        
        const statusIcon = data.confirmed ? "✅" : "⏳";
        const typeTag = isSystem ? "【强制】" : (data.initiator === sendName ? "【发起】" : "【收到】");
        const detailCount = data.details ? data.details.length : 0;
        
        listContent += `${statusIcon} ${typeTag} 与「${name}」(${detailCount}条细节)\n`;
    });

    if (!listContent) {
        reply += "（暂无任何记录）";
    } else {
        reply += listContent;
        reply += `\n📊 额度占用：${activeCount}/${maxRel}`;
        reply += `\n💡 输入「。查看关系线 名字」同步合并转发细节`;
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看关系线"] = cmd_view_relationship;

let cmd_create_official_appointment = seal.ext.newCmdItemInfo();
cmd_create_official_appointment.name = "发起官约";
cmd_create_official_appointment.help = "。发起官约 D1 14:00-15:00 地点 参与者1/参与者2/...（管理员专用，自动创建官方约会群组）";

cmd_create_official_appointment.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员可以发起官约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const day = cmdArgs.getArgN(1);
  const time = cmdArgs.getArgN(2);
  const place = cmdArgs.getArgN(3);
  const participantsRaw = cmdArgs.getArgN(4);

  if (!day || !time || !place || !participantsRaw) {
    seal.replyToSender(ctx, msg, `格式：。发起官约 D1 14:00-15:00 地点 参与者1/参与者2/...`);
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!isValidTimeFormat(time)) {
    seal.replyToSender(ctx, msg, `请输入合法的时间格式，如 14:00-16:00，且结束时间需大于开始时间`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const participants = participantsRaw.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
  const platform = msg.platform;
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  const a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
  const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

  if (!a_private_group[platform]) {
    seal.replyToSender(ctx, msg, `当前平台没有绑定任何角色`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let validParticipants = [];
  let invalidParticipants = [];
  
  for (let name of participants) {
    if (a_private_group[platform][name]) {
      validParticipants.push(name);
    } else {
      invalidParticipants.push(name);
    }
  }

  if (invalidParticipants.length > 0) {
    seal.replyToSender(ctx, msg, `以下参与者未找到：${invalidParticipants.join("、")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查时间冲突逻辑保持不变...
  let conflictParticipants = [];
  for (let name of validParticipants) {
    const uid = a_private_group[platform][name][0];
    const key = `${platform}:${uid}`;
    const locked = a_lockedSlots[key]?.[day] || [];
    if (locked.some(slot => timeOverlap(slot, time))) {
      conflictParticipants.push(`${name}（被锁定）`);
      continue;
    }
    const schedule = b_confirmedSchedule[key] || [];
    if (schedule.some(ev => ev.day === day && timeOverlap(ev.time, time))) {
      conflictParticipants.push(`${name}（已有安排）`);
      continue;
    }
  }

  if (conflictParticipants.length > 0) {
    seal.replyToSender(ctx, msg, `以下参与者时间冲突：\n${conflictParticipants.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 分配群号
  const groupList = JSON.parse(ext.storageGet("group") || "[]");
  const available = groupList.filter(g => !g.endsWith("_占用"));
  
  if (available.length === 0) {
    seal.replyToSender(ctx, msg, `暂无可用群号`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const gid = available[Math.floor(Math.random() * available.length)];
  groupList.splice(groupList.indexOf(gid), 1);
  groupList.push(gid + "_占用");
  ext.storageSet("group", JSON.stringify(groupList));

  // --- 新增：过期与计时逻辑 ---
  const acceptTime = Date.now();
  const expireHours = parseInt(ext.storageGet("group_expire_hours") || "48");
  const expireTime = acceptTime + expireHours * 60 * 60 * 1000;
  const formatTime = (ts) => new Date(ts).toLocaleString("zh-CN", { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  const expireNotice = `⏰ 本群将在 ${formatTime(expireTime)} 自动结束（${expireHours}小时有效期）`;

  // 更新已确认日程
  for (let name of validParticipants) {
    const uid = a_private_group[platform][name][0];
    const key = `${platform}:${uid}`;
    if (!b_confirmedSchedule[key]) b_confirmedSchedule[key] = [];
    b_confirmedSchedule[key].push({
      day: day,
      time: time,
      partner: `官约（${validParticipants.join("、")}）`,
      subtype: "官约",
      place: place,
      group: gid,
      status: "active"
    });
  }
  ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

  // 记录群组过期信息
  let groupInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
  groupInfo[gid] = {
      acceptTime: acceptTime,
      expireTime: expireTime,
      participants: validParticipants,
      subtype: "官约",
      day: day,
      time: time,
      place: place
  };
  ext.storageSet("group_expire_info", JSON.stringify(groupInfo));

  // 通知参与者（私聊/绑定群）
  for (let name of validParticipants) {
    const uid = a_private_group[platform][name][0];
    const boundGroupId = a_private_group[platform][name][1];
    
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender.userId = `${platform}:${uid}`;
    newmsg.groupId = `${platform}-Group:${boundGroupId}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
    
    seal.replyToSender(newctx, newmsg,
      `🎊 官方邀约通知\n\n` +
      `📅 时间：${day} ${time}\n` +
      `📍 地点：${place}\n` +
      `👥 参与者：${validParticipants.join("、")}\n` +
      `💬 群号：${gid}\n\n` +
      `${expireNotice}\n请按时参加。`
    );
  }

  // 在官约群内发送公告
  const notice = seal.newMessage();
  notice.messageType = "group";
  notice.groupId = `${platform}-Group:${gid}`;
  const noticeCtx = seal.createTempCtx(ctx.endPoint, notice);
  
  seal.replyToSender(noticeCtx, notice,
    `🎊 官方约会开始\n\n` +
    `📅 时间：${day} ${time}\n` +
    `📍 地点：${place}\n` +
    `👥 参与者：${validParticipants.join("、")}\n\n` +
    `${expireNotice}`
  );

  setGroupName(noticeCtx, notice, noticeCtx.group.groupId, `官约 ${day} ${time} ${place} ${validParticipants.join("、")}`);

  // --- 核心：启动计时器 ---
  // 官约模式下，默认发起人为管理员，这里可以使用 validParticipants[0] 作为逻辑上的发起者
  if (typeof initGroupTimer === "function") {
      initGroupTimer(platform, gid, "官约", validParticipants, validParticipants[0]);
  }

  seal.replyToSender(ctx, msg, `✅ 官约创建成功！群号：${gid}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["发起官约"] = cmd_create_official_appointment;
// ========================
// 👀 目击报告系统 v1.1
// ========================

/**
 * 目击报告系统功能：
 * 1. 可开关控制
 * 2. 需要地点系统开启
 * 3. 在成功分配小群后，检查同一时间段同一地点是否有其他约会（包括已结束的）
 * 4. 时间段部分重合即触发目击
 * 5. 向参与者发送目击报告
 */

// 获取目击报告系统配置
function getSightingConfig() {
    const defaultConfig = {
        enabled: false,  // 默认关闭
        send_to_all: true, // 是否同时发送给被目击者
        max_reports_per_day: 3, // 每人每天最大目击报告次数
        include_ended_meetings: true, // 包含已结束的会议
        time_overlap_threshold: 0.3 // 时间重叠阈值（30%以上重叠触发）
    };
    const config = JSON.parse(ext.storageGet("sighting_system_config") || "{}");
    return { ...defaultConfig, ...config };
}

// 设置目击报告系统配置
function setSightingConfig(config) {
    ext.storageSet("sighting_system_config", JSON.stringify(config));
}

// 检查目击报告功能是否可用
function isSightingEnabled() {
    const sightingConfig = getSightingConfig();
    const placeSystemConfig = getPlaceSystemConfig();
    
    // 目击报告系统未启用
    if (!sightingConfig.enabled) {
        return false;
    }
    
    // 地点系统未启用
    if (!placeSystemConfig.enabled) {
        return false;
    }
    
    return true;
}

// 检查用户今日目击报告次数
function getUserSightingCountToday(platform, roleName) {
    const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const sightingCount = JSON.parse(ext.storageGet("sighting_daily_count") || "{}");
    
    if (!sightingCount[today]) {
        sightingCount[today] = {};
    }
    
    const platformKey = `${platform}:${roleName}`;
    return sightingCount[today][platformKey] || 0;
}

// 增加用户今日目击报告次数
function incrementUserSightingCountToday(platform, roleName) {
    const today = new Date().toISOString().slice(0, 10);
    const sightingCount = JSON.parse(ext.storageGet("sighting_daily_count") || "{}");
    
    if (!sightingCount[today]) {
        sightingCount[today] = {};
    }
    
    const platformKey = `${platform}:${roleName}`;
    sightingCount[today][platformKey] = (sightingCount[today][platformKey] || 0) + 1;
    ext.storageSet("sighting_daily_count", JSON.stringify(sightingCount));
}

// 检查是否需要发送目击报告（随机概率 + 每日次数限制）
function shouldSendSightingReport(platform, roleName) {
    const sightingConfig = getSightingConfig();
    
    // 检查今日次数
    const todayCount = getUserSightingCountToday(platform, roleName);
    if (todayCount >= sightingConfig.max_reports_per_day) {
        return false;
    }
    
    // 随机概率：50%触发
    const randomChance = Math.random() < 1;
    return randomChance;
}

// 计算两个时间段的重叠比例
function calculateTimeOverlapRatio(time1, time2) {
    const [start1, end1] = parseStartEnd(time1);
    const [start2, end2] = parseStartEnd(time2);
    
    // 计算重叠的分钟数
    const overlapStart = Math.max(start1, start2);
    const overlapEnd = Math.min(end1, end2);
    
    if (overlapStart >= overlapEnd) {
        return 0; // 没有重叠
    }
    
    const overlapMinutes = overlapEnd - overlapStart;
    const duration1 = end1 - start1;
    const duration2 = end2 - start2;
    
    // 返回两个时间段中较短者的重叠比例
    const minDuration = Math.min(duration1, duration2);
    return overlapMinutes / minDuration;
}

// 查找同一时间同一地点的其他约会（包括已结束的）
function findSimultaneousMeetings(platform, day, time, place, excludeGroupId = null) {
    const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    const groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const sightingConfig = getSightingConfig();
    
    const simultaneousMeetings = [];
    
    // 遍历所有已确认的日程（包括已结束的）
    for (const [userId, scheduleList] of Object.entries(b_confirmedSchedule)) {
        for (const meeting of scheduleList) {
            // 跳过排除的群组
            if (excludeGroupId && meeting.group === excludeGroupId) continue;
            
            // 检查是否同一天同一地点
            if (meeting.day !== day || meeting.place !== place) continue;
            
            // 检查时间段是否重叠（部分重合即可）
            const overlapRatio = calculateTimeOverlapRatio(meeting.time, time);
            if (overlapRatio < sightingConfig.time_overlap_threshold) continue;
            
            // 获取参与者信息
            const meetingParticipants = [];
            const meetingGroupId = meeting.group;
            
            // 尝试从群组信息中获取参与者
            if (meetingGroupId && groupExpireInfo[meetingGroupId]) {
                meetingParticipants.push(...groupExpireInfo[meetingGroupId].participants);
            } else {
                // 从日程信息中获取参与者
                if (meeting.partner) {
                    if (meeting.partner === "多人小群") {
                        // 多人小群，需要从其他地方获取参与者
                        // 这里简化处理，标记为多人
                        meetingParticipants.push("多人");
                    } else {
                        meetingParticipants.push(meeting.partner);
                    }
                }
                
                // 从用户ID获取角色名
                const userIdParts = userId.split(':');
                const userPlatform = userIdParts[0];
                const userUid = userIdParts[1];
                
                if (a_private_group[userPlatform]) {
                    const roleName = Object.entries(a_private_group[userPlatform])
                        .find(([_, val]) => val[0] === userUid)?.[0];
                    if (roleName && !meetingParticipants.includes(roleName)) {
                        meetingParticipants.push(roleName);
                    }
                }
            }
            
            // 如果参与者为空，跳过
            if (meetingParticipants.length === 0) continue;
            
            // 确定活动类型
            let meetingType = meeting.subtype || "未知";
            if (meeting.partner === "多人小群") {
                meetingType = "多人" + meetingType;
            }
            
            // 确定会议状态
            const isEnded = meeting.status === "ended";
            
            simultaneousMeetings.push({
                groupId: meetingGroupId,
                day: meeting.day,
                time: meeting.time,
                place: meeting.place,
                participants: [...new Set(meetingParticipants)], // 去重
                type: meetingType,
                isEnded: isEnded,
                overlapRatio: overlapRatio
            });
        }
    }
    
    // 排序：按时间重叠比例降序排列
    simultaneousMeetings.sort((a, b) => b.overlapRatio - a.overlapRatio);
    
    return simultaneousMeetings;
}
// 发送目击报告
function sendSightingReports(platform, newMeetingInfo, simultaneousMeetings) {
    const sightingConfig = getSightingConfig();
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    if (!a_private_group[platform]) return;
    
    // 为新会议的每个参与者发送目击报告
    for (const participant of newMeetingInfo.participants) {
        // 检查是否需要发送报告
        if (!shouldSendSightingReport(platform, participant)) {
            continue;
        }
        
        // 获取参与者的群组ID
        const participantInfo = a_private_group[platform][participant];
        if (!participantInfo || !participantInfo[1]) {
            continue;
        }
        
        // 为每个同时进行的会议生成报告
        for (const otherMeeting of simultaneousMeetings) {
            // 跳过自己所在的会议
            if (otherMeeting.participants.includes(participant)) continue;
            
            // 构建生动的报告消息
            const otherParticipantsText = otherMeeting.participants.join('、');
            
            const reportMessage = 
                `👀 不会吧，你居然在 ${newMeetingInfo.place} 看见了 ${otherParticipantsText} 在一起！\n` +
                `\n📅 时间：${newMeetingInfo.day} 左右` +
                `\n\n💭 这奇妙的巧合，是命运的捉弄还是缘分的安排呢~`;
            
            // 发送报告
            const msg = seal.newMessage();
            msg.messageType = "group";
            msg.groupId = `${platform}-Group:${participantInfo[1]}`;
            msg.sender = {};
            const ctx = seal.createTempCtx(seal.ext.find("changriV1").endPoint, msg);
            
            seal.replyToSender(ctx, msg, reportMessage);
            
            // 增加目击次数
            incrementUserSightingCountToday(platform, participant);
            
            // 如果配置为同时发送给被目击者
            if (sightingConfig.send_to_all) {
                sendCounterSightingReports(platform, otherMeeting, newMeetingInfo);
            }
            
            // 每个参与者每天只发送一次报告
            break;
        }
    }
}

// 发送反向目击报告（被目击者收到报告）
function sendCounterSightingReports(platform, originalMeeting, newMeetingInfo) {
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    if (!a_private_group[platform]) return;
    
    for (const participant of originalMeeting.participants) {
        // 检查是否需要发送报告
        if (!shouldSendSightingReport(platform, participant)) {
            continue;
        }
        
        // 获取参与者的群组ID
        const participantInfo = a_private_group[platform][participant];
        if (!participantInfo || !participantInfo[1]) {
            continue;
        }
        
        // 构建反向报告消息
        const newParticipantsText = newMeetingInfo.participants.join('、');
        
        const reportMessage = 
            `👀 哎呀，你和${originalMeeting.participants.length > 1 ? '伙伴们' : '朋友'}在 ${originalMeeting.place} 的约会被 ${newParticipantsText} 看到了！\n` +
            `\n📅 时间：${originalMeeting.day} 左右` +
            `\n\n💭 秘密不小心溜出去啦~不过，这也算是一种奇妙的缘分呢！`;
        
        // 发送报告
        const msg = seal.newMessage();
        msg.messageType = "group";
        msg.groupId = `${platform}-Group:${participantInfo[1]}`;
        msg.sender = {};
        const ctx = seal.createTempCtx(seal.ext.find("changriV1").endPoint, msg);
        
        seal.replyToSender(ctx, msg, reportMessage);
        
        // 增加目击次数
        incrementUserSightingCountToday(platform, participant);
    }
}

// 获取时间重叠的描述
function getTimeOverlapDescription(time1, time2) {
    const [start1, end1] = parseStartEnd(time1);
    const [start2, end2] = parseStartEnd(time2);
    
    // 找到重叠的时间段
    const overlapStart = Math.max(start1, start2);
    const overlapEnd = Math.min(end1, end2);
    
    // 计算重叠的分钟数
    const overlapMinutes = Math.max(0, overlapEnd - overlapStart);
    
    // 格式化为小时:分钟
    const formatMinutes = (minutes) => {
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
    };
    
    if (overlapMinutes > 0) {
        const overlapStartTime = formatMinutes(overlapStart);
        const overlapEndTime = formatMinutes(overlapEnd);
        return `${overlapStartTime}-${overlapEndTime}（重叠${overlapMinutes}分钟）`;
    } else {
        // 如果没有完全重叠，但时间段相近（相隔30分钟内）
        const timeGap = Math.min(
            Math.abs(start1 - end2),
            Math.abs(start2 - end1)
        );
        
        if (timeGap <= 30) {
            const gapTime = formatMinutes(Math.max(start1, start2));
            return `${gapTime}左右`;
        } else {
            // 返回大致时间段
            const midTime1 = formatMinutes(Math.floor((start1 + end1) / 2));
            const midTime2 = formatMinutes(Math.floor((start2 + end2) / 2));
            return `${midTime1}至${midTime2}期间`;
        }
    }
}

// 在分配小群后触发目击检查
function triggerSightingCheck(platform, day, time, place, participants, groupId, subtype) {
    // 检查功能是否可用
    if (!isSightingEnabled()) {
        return;
    }
    
    // 构建新会议信息
    const newMeetingInfo = {
        day,
        time,
        place,
        participants,
        groupId,
        subtype
    };
    
    // 查找同时同地的其他会议
    const simultaneousMeetings = findSimultaneousMeetings(platform, day, time, place, groupId);
    
    if (simultaneousMeetings.length > 0) {
        // 发送目击报告
        sendSightingReports(platform, newMeetingInfo, simultaneousMeetings);
    }
}

// ========================
// 📦 恋综系统分类控制台 (完整版)
// ========================

let cmd_settings = seal.ext.newCmdItemInfo();
cmd_settings.name = '设置';
cmd_settings.help = `==== 📺 恋综系统控制台 ====
使用方法：
.设置 基础  - 名字、群号、核心功能开关
.设置 互动  - 冷却时间、邀约时长、目击上限
.设置 信件  - 寄信混乱度、匿名上限、送达时间
.设置 公告  - 各种公开广播的概率与开关

💡 提示：输入对应指令后，复制弹出的模板进行修改即可。`;

cmd_settings.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足：该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const rawMessage = msg.message.trim();
    const subCmd = argv.getArgN(1);

    // 提交模式：识别首行标识符
    if (rawMessage.includes('\n')) {
        const firstLine = rawMessage.split('\n')[0];
        if (firstLine.includes('基础设置')) return handleApply(ctx, msg, rawMessage, applyBasicParam);
        if (firstLine.includes('互动设置')) return handleApply(ctx, msg, rawMessage, applyInteractionParam);
        if (firstLine.includes('信件设置')) return handleApply(ctx, msg, rawMessage, applyLetterParam);
        if (firstLine.includes('公告设置')) return handleApply(ctx, msg, rawMessage, applyPublicParam);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查询模式
    switch (subCmd) {
        case '基础': return showBasicSettings(ctx, msg);
        case '互动': return showInteractionSettings(ctx, msg);
        case '信件': return showLetterSettings(ctx, msg);
        case '公告': return showPublicSettings(ctx, msg);
        default: seal.replyToSender(ctx, msg, cmd_settings.help);
    }
    return seal.ext.newCmdExecuteResult(true);
};

// --- ⚙️ 通用解析引擎 ---
function handleApply(ctx, msg, rawMessage, paramHandler) {
    const lines = rawMessage.split('\n');
    const success = []; const error = [];
    for (let i = 1; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) continue;
        const match = line.match(/^【([^】]+)】\s*(.+)$/);
        if (!match) continue;
        const result = paramHandler(match[1].trim(), match[2].trim());
        if (result.success) success.push(result.message); else error.push(result.message);
    }
    let reply = `✅ 处理完成（成功 ${success.length} 项）\n` + success.join('\n');
    if (error.length > 0) reply += `\n\n❌ 失败项：\n` + error.join('\n');
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
}

// --- 1️⃣ 基础设置模块 ---
function showBasicSettings(ctx, msg) {
    const feature = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    const results = [
        "🎯 基础设置当前配置", "────────────────", ".设置 基础设置",
        `【恋综名】${JSON.parse(ext.storageGet("love_show_name") || "\"未设置\"")}`,
        `【微信】${feature.enable_wechat !== false ? '开启' : '关闭'}`,
        `【礼物】${feature.enable_general_gift !== false ? '开启' : '关闭'}`,
        `【心愿】${feature.enable_wish_system !== false ? '开启' : '关闭'}`,
        `【发起邀约】${feature.enable_general_appointment !== false ? '开启' : '关闭'}`,
        `【关系线系统】${JSON.parse(ext.storageGet("relationship_system_enabled") || "true") ? '开启' : '关闭'}`,
        `【关系线上限】${ext.storageGet("max_relationships_per_user") || "5"}`,
        `【点歌群】${JSON.parse(ext.storageGet("song_group_id") || "\"未设置\"")}`,
        `【后台群】${JSON.parse(ext.storageGet("background_group_id") || "\"未设置\"")}`,
        `【公告群】${JSON.parse(ext.storageGet("adminAnnounceGroupId") || "\"未设置\"")}`,
        `【水群】${JSON.parse(ext.storageGet("water_group_id") || "\"未设置\"")}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyBasicParam(name, val) {
    const featureMap = { '微信': 'enable_wechat', '礼物': 'enable_general_gift', '心愿': 'enable_wish_system', '发起邀约': 'enable_general_appointment' };
    if (featureMap[name]) {
        let cfg = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
        cfg[featureMap[name]] = (val === '开启');
        ext.storageSet("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【${name}】已${val}` };
    }
    if (name === '关系线系统') { ext.storageSet("relationship_system_enabled", JSON.stringify(val === '开启')); return { success: true, message: `【${name}】已${val}` }; }
    if (name === '恋综名') { ext.storageSet("love_show_name", JSON.stringify(val)); return { success: true, message: `【${name}】已设为 ${val}` }; }
    if (name === '关系线上限') { ext.storageSet("max_relationships_per_user", val); return { success: true, message: `【${name}】已设为 ${val}` }; }
    const groups = { '点歌群': 'song_group_id', '后台群': 'background_group_id', '公告群': 'adminAnnounceGroupId', '水群': 'water_group_id' };
    if (groups[name]) { ext.storageSet(groups[name], JSON.stringify(val === '未设置' ? null : val)); return { success: true, message: `【${name}】已同步` }; }
    return { success: false, message: `未知参数：${name}` };
}

// --- 2️⃣ 互动设置模块 (已修正为纯 Storage) ---
function showInteractionSettings(ctx, msg) {
    const sighting = getSightingConfig();
    const place = getPlaceSystemConfig();
    const duration = JSON.parse(ext.storageGet("appointment_duration_config") || "{\"phone\":29,\"private\":59}");
    
    const results = [
        "🤝 互动设置当前配置", "────────────────", ".设置 互动设置",
        `【地点系统】${place.enabled ? '开启' : '关闭'}`,
        `【目击报告】${sighting.enabled ? '开启' : '关闭'}`,
        `【目击每日上限】${sighting.max_reports_per_day}`,
        `【电话最小时长】${duration.phone}`,
        `【私密最小时长】${duration.private}`,
        `【寄信冷却时间】${ext.storageGet("mailCooldown") || "60"}`,
        `【送礼冷却时间】${ext.storageGet("giftCooldown") || "30"}`,
        `【匿名信冷却时间】${ext.storageGet("secretLetterCooldown") || "2"}`,
        `【送礼模式】${ext.storageGet("giftMode") || "0"}`,
        `【时间重叠阈值】${Math.round(sighting.time_overlap_threshold * 100)}`,
        `【目击报告方式】${sighting.send_to_all ? '双向通知' : '单向通知'}`,
        `【包含已结束】${sighting.include_ended_meetings ? '是' : '否'}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyInteractionParam(name, val) {
    // 1. 地点系统处理 (保持原样)
    if (name === '地点系统') { 
        let c = getPlaceSystemConfig(); 
        c.enabled = (val === '开启'); 
        setPlaceSystemConfig(c); 
        return { success: true, message: `地点系统已${val}` }; 
    }

    // 2. 目击报告相关 (保持原样)
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

    // 3. 邀约时长处理 (保持原样)
    const durationMap = { '电话最小时长': 'phone', '私密最小时长': 'private' };
    if (durationMap[name]) {
        let d = JSON.parse(ext.storageGet("appointment_duration_config") || "{}");
        d[durationMap[name]] = parseInt(val);
        ext.storageSet("appointment_duration_config", JSON.stringify(d));
        return { success: true, message: `【${name}】已更新` };
    }

    // 4. ✨ 修改重点：将原本的 setConfig 改为 storageSet
    const storageKeys = { 
        '寄信冷却时间': 'mailCooldown', 
        '送礼冷却时间': 'giftCooldown', 
        '匿名信冷却时间': 'secretLetterCooldown', 
        '送礼模式': 'giftMode' 
    };

    if (storageKeys[name]) {
        // 直接存入数据库，存为字符串或数字均可，建议保持字符串存入，读取时 parseInt
        ext.storageSet(storageKeys[name], val); 
        return { success: true, message: `【${name}】已设为 ${val}` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// --- 3️⃣ 信件设置模块 (已修正为纯 Storage) ---
function showLetterSettings(ctx, msg) {
    const feature = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    const chaos = JSON.parse(ext.storageGet("chaos_letter_config") || "{\"dailyLimit\":5}");
    const results = [
        "✉️ 信件设置当前配置", "────────────────", ".设置 信件设置",
        `【寄信】${feature.enable_chaos_letter !== false ? '开启' : '关闭'}`,
        `【心动信】${feature.enable_lovemail !== false ? '开启' : '关闭'}`,
        `【匿名信】${feature.enable_secret_letter !== false ? '开启' : '关闭'}`,
        `【后台信件】${feature.enable_general_letter !== false ? '开启' : '关闭'}`,
        `【心动信送达时间】${JSON.parse(ext.storageGet("lovemail_delivery_time") || "\"22:00\"")}`,
        `【寄信每日上限】${chaos.dailyLimit}`,
        `【匿名信每日上限】${ext.storageGet("secretLetterDailyLimit") || "30"}`,
        `【寄信混乱送错】${chaos.misdelivery || 0}`,
        `【寄信混乱涂改】${chaos.blackoutText || 0}`,
        `【寄信混乱丢失】${chaos.loseContent || 0}`,
        `【寄信混乱反义】${chaos.antonymReplace || 0}`,
        `【寄信混乱乱序】${chaos.reverseOrder || 0}`,
        `【寄信混乱模糊】${chaos.fuzzySignature || 0}`,
        `【寄信混乱混淆】${chaos.mistakenSignature || 0}`,
        `【寄信混乱诗意】${chaos.poeticSignature || 0}`,
        `【小群过期时间】${ext.storageGet("group_expire_hours") || "48"}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyLetterParam(name, val) {
    const featureMap = { 
        '寄信': 'enable_chaos_letter', 
        '心动信': 'enable_lovemail', 
        '匿名信': 'enable_secret_letter', 
        '后台信件': 'enable_general_letter' 
    };

    // 1. 处理功能开关 (保持原样)
    if (featureMap[name]) {
        let cfg = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
        cfg[featureMap[name]] = (val === '开启');
        ext.storageSet("global_feature_toggle", JSON.stringify(cfg));
        return { success: true, message: `【${name}】已${val}` };
    }

    // 2. 处理送达时间 (保持原样)
    if (name === '心动信送达时间') { 
        ext.storageSet("lovemail_delivery_time", JSON.stringify(val)); 
        return { success: true, message: `时间已设为 ${val}` }; 
    }

    // 3. ✨ 修改重点：匿名信每日上限由 setConfig 改为直接 storageSet
    if (name === '匿名信每日上限') { 
        ext.storageSet("secretLetterDailyLimit", val); 
        return { success: true, message: `【${name}】上限已更新为 ${val}` }; 
    }

    // 4. 处理寄信混乱度参数 (这些原本就是存入 storage 的 JSON，保持原样即可)
    const chaosMap = { 
        '寄信每日上限': 'dailyLimit', 
        '寄信混乱送错': 'misdelivery', 
        '寄信混乱涂改': 'blackoutText', 
        '寄信混乱丢失': 'loseContent', 
        '寄信混乱反义': 'antonymReplace', 
        '寄信混乱乱序': 'reverseOrder', 
        '寄信混乱模糊': 'fuzzySignature', 
        '寄信混乱混淆': 'mistakenSignature', 
        '寄信混乱诗意': 'poeticSignature' 
    };
    if (chaosMap[name]) {
        let c = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        c[chaosMap[name]] = parseInt(val);
        ext.storageSet("chaos_letter_config", JSON.stringify(c));
        return { success: true, message: `【${name}】已更新为 ${val}` };
    }

    // 5. 过期时间 (保持原样)
    if (name === '小群过期时间') { 
        ext.storageSet("group_expire_hours", val); 
        return { success: true, message: `已设为 ${val}小时` }; 
    }

    return { success: false, message: `未知参数：${name}` };
}

// --- 4️⃣ 公告设置模块 (已修正为纯 Storage) ---
function showPublicSettings(ctx, msg) {
    const chaos = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
    const results = [
        "📢 公告设置当前配置", "────────────────", ".设置 公告设置",
        `【心愿公开提醒】${JSON.parse(ext.storageGet("wish_public_send") || "false") ? '开启' : '关闭'}`,
        `【送礼公开发送】${JSON.parse(ext.storageGet("gift_public_send") || "false") ? '开启' : '关闭'}`,
        `【寄信公开发送】${JSON.parse(ext.storageGet("letter_public_send") || "false") ? '开启' : '关闭'}`,
        `【匿名信公开发送】${JSON.parse(ext.storageGet("secret_letter_public_send") || "false") ? '开启' : '关闭'}`,
        `【寄信公开概率】${chaos.publicChance || 50}`,
        `【礼物公开概率】${ext.storageGet("giftPublicChance") || "50"}`,
        `【匿名信公开概率】${ext.storageGet("secretLetterPublicChance") || "50"}`,
        `【匿名信暴露概率】${ext.storageGet("secretLetterRevealChance") || "15"}`,
        `【每日礼物上限】${ext.storageGet("giftDailyLimit") || "100"}`
    ];
    seal.replyToSender(ctx, msg, results.join('\n'));
}

function applyPublicParam(name, val) {
    // 1. 处理广播开关 (保持原样)
    const map = { 
        '心愿公开提醒': 'wish_public_send', 
        '送礼公开发送': 'gift_public_send', 
        '寄信公开发送': 'letter_public_send', 
        '匿名信公开发送': 'secret_letter_public_send' 
    };
    if (map[name]) { 
        ext.storageSet(map[name], JSON.stringify(val === '开启')); 
        return { success: true, message: `【${name}】已${val}` }; 
    }

    // 2. 处理寄信公开概率 (保持原样，存入大表)
    if (name === '寄信公开概率') {
        let c = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
        c.publicChance = parseInt(val);
        ext.storageSet("chaos_letter_config", JSON.stringify(c));
        return { success: true, message: `【${name}】已设为 ${val}%` };
    }

    // 3. ✨ 修改重点：将原本的 setConfig 改为直接 storageSet
    const storageKeys = { 
        '礼物公开概率': 'giftPublicChance', 
        '匿名信公开概率': 'secretLetterPublicChance', 
        '匿名信暴露概率': 'secretLetterRevealChance', 
        '每日礼物上限': 'giftDailyLimit' 
    };

    if (storageKeys[name]) {
        // 直接存入数据库
        ext.storageSet(storageKeys[name], val); 
        return { success: true, message: `【${name}】已保存为 ${val}` };
    }

    return { success: false, message: `未知参数：${name}` };
}

// ========================
// 📮 设置信箱上限指令
// ========================

let cmd_set_mailbox_limit = seal.ext.newCmdItemInfo();
cmd_set_mailbox_limit.name = '设置信箱上限';
cmd_set_mailbox_limit.help = `查看或设置我的信箱上限

格式1：.设置信箱上限 - 查看当前设置
格式2：.设置信箱上限 [数字]

示例：
.设置信箱上限 5
.设置信箱上限 3`;

cmd_set_mailbox_limit.solve = function(ctx, msg, argv) {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const limitValue = argv.getArgN(1);
    
    if (!limitValue) {
        // 查看当前设置
        const currentLimit = parseInt(ext.storageGet("lovemail_daily_limit") || "3");
        seal.replyToSender(ctx, msg, `📮 当前我的信箱上限：${currentLimit} 封/天`);
        return seal.ext.newCmdExecuteResult(true);
    } else {
        // 设置新值
        const newLimit = parseInt(limitValue);
        
        if (isNaN(newLimit) || newLimit < 1) {
            seal.replyToSender(ctx, msg, "❌ 参数错误：请输入≥1的数字");
            return seal.ext.newCmdExecuteResult(true);
        }
        
        ext.storageSet("lovemail_daily_limit", newLimit.toString());
        seal.replyToSender(ctx, msg, `✅ 已设置我的信箱上限为：${newLimit} 封/天`);
        return seal.ext.newCmdExecuteResult(true);
    }
};

// ========================
// 🔧 辅助函数
// ========================

// 构建结果消息
function buildResultMessage(settingType, paramCount, successResults, errorResults, warningResults) {
    let replyText = "";
    
    if (paramCount === 0) {
        replyText = `⚠️ 未检测到有效的参数设置，请检查格式是否正确\n`;
        replyText += `格式应为：.${settingType}\n【参数名1】值1\n【参数名2】值2\n...`;
    } else {
        replyText = `📋 ${settingType}结果\n`;
        replyText += "────────────────\n";
        
        if (successResults.length > 0) {
            replyText += `✅ 成功设置 ${successResults.length} 个参数：\n`;
            successResults.forEach((result, index) => {
                replyText += `${index + 1}. ${result}\n`;
            });
            replyText += "\n";
        }
        
        if (errorResults.length > 0) {
            replyText += `❌ 设置失败 ${errorResults.length} 个参数：\n`;
            errorResults.forEach((error, index) => {
                replyText += `${index + 1}. ${error}\n`;
            });
            replyText += "\n";
        }
        
        if (warningResults.length > 0) {
            replyText += `⚠️ 警告 ${warningResults.length} 个：\n`;
            warningResults.forEach((warning, index) => {
                replyText += `${index + 1}. ${warning}\n`;
            });
        }
        
        replyText += `\n📊 ${settingType}完成，可使用「.${settingType}」查看最新状态`;
    }
    
    return replyText;
}

// 辅助函数：获取目击配置
function getSightingConfig() {
    const defaultConfig = {
        enabled: true,
        send_to_all: true,
        max_reports_per_day: 5,
        include_ended_meetings: false,
        time_overlap_threshold: 0.3
    };
    const config = JSON.parse(ext.storageGet("sighting_system_config") || "{}");
    return { ...defaultConfig, ...config };
}

// 辅助函数：设置目击配置
function setSightingConfig(config) {
    ext.storageSet("sighting_system_config", JSON.stringify(config));
}

// 辅助函数：获取地点系统配置
function getPlaceSystemConfig() {
    const defaultConfig = {
        enabled: true,
        require_key_by_default: false
    };
    const config = JSON.parse(ext.storageGet("place_system_config") || "{}");
    return { ...defaultConfig, ...config };
}

// 辅助函数：设置地点系统配置
function setPlaceSystemConfig(config) {
    ext.storageSet("place_system_config", JSON.stringify(config));
}

// ========================
// 🛠️ 指令注册与映射
// ========================

// 1. 注册核心“设置”指令
ext.cmdMap['设置'] = cmd_settings;

// 2. 注册“设置信箱上限”指令
ext.cmdMap['设置信箱上限'] = cmd_set_mailbox_limit;

// 3. 修改原“系统参数”指令为引导提示
let cmd_system_params = seal.ext.newCmdItemInfo();
cmd_system_params.name = '系统参数';
cmd_system_params.solve = function(ctx, msg, argv) {
    const helpText = `📺 恋综系统控制台已升级！
现已整合为统一的【.设置】指令，支持分类查看与修改。

使用方法：
.设置 基础  - 名字、群号、核心功能开关
.设置 互动  - 冷却时间、邀约时长、目击上限
.设置 信件  - 寄信混乱度、匿名上限、送达时间
.设置 公告  - 各种公开广播的概率与开关

📮 专项指令：
.设置信箱上限 [数字] - 设置我的信箱每日上限

💡 提示：输入对应分类（如：.设置 基础）后，复制弹出的模板发送即可完成批量修改。`;
    
    seal.replyToSender(ctx, msg, helpText);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap['系统参数'] = cmd_system_params;
// ========================
// ⏰ 监听系统核心函数（修改版）
// ========================

/**
 * 获取监听设置
 */
function getMonitorSettings() {
    const defaultSettings = {
        enabled: true,
        min_words_phone: 20,
        min_words_private: 150,
        min_words_wish: 150,
        min_words_official: 150,
        timeout_phone: 3600000,
        timeout_private: 10800000,
        timeout_wish: 10800000,
        timeout_official: 10800000,
        remind_interval_phone: 5400000,
        remind_interval_private: 10800000,
        remind_interval_wish: 10800000,
        remind_interval_official: 10800000,
        auto_monitor_all_groups: true  // 新增：自动监控所有群组
    };
    
    const settings = JSON.parse(ext.storageGet("monitor_settings") || "{}");
    return { ...defaultSettings, ...settings };
}

/**
 * 保存监听设置
 */
function setMonitorSettings(settings) {
    ext.storageSet("monitor_settings", JSON.stringify(settings));
}

/**
 * 获取群组计时器
 */
function getGroupTimers() {
    return JSON.parse(ext.storageGet("group_timers") || "{}");
}

/**
 * 保存群组计时器
 */
function saveGroupTimers(timers) {
    ext.storageSet("group_timers", JSON.stringify(timers));
}

/**
 * 获取用户统计
 */
function getUserStats() {
    return JSON.parse(ext.storageGet("user_stats") || "{}");
}

/**
 * 保存用户统计
 */
function saveUserStats(stats) {
    ext.storageSet("user_stats", JSON.stringify(stats));
}

/**
 * 初始化群组计时器（修正版）
 * 修改：过滤掉已拒绝的参与者
 */
function initGroupTimer(platform, groupId, subtype, participants, initiator) {
    const settings = getMonitorSettings();
    if (!settings.enabled) return;
    
    // 获取多人邀约状态，过滤掉已拒绝的参与者
    const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
    const multiGroup = Object.values(b_MultiGroupRequest).find(g => 
        g.sendname === initiator && 
        g.participants && 
        g.participants.includes(initiator)
    );
    
    // 如果有多人邀约状态，过滤掉已拒绝的人
    let activeParticipants = [...participants];
    if (multiGroup && multiGroup.targetList) {
        activeParticipants = participants.filter(participant => {
            const status = multiGroup.targetList[participant];
            // 只包括已接受和待回应的参与者
            return status === "accepted" || status === null;
        });
    }
    
    // 如果没有活跃参与者，不创建计时器
    if (activeParticipants.length === 0) return;
    
    const timers = getGroupTimers();
    const now = Date.now();
    
    // 根据类型获取超时时间
    const getTimeout = (type) => {
        switch(type) {
            case "电话": return settings.timeout_phone;
            case "私密": return settings.timeout_private;
            case "心愿": return settings.timeout_wish;
            case "官方约会": return settings.timeout_official;
            default: return settings.timeout_private;
        }
    };
    
    // 判断计时模式：2人使用轮流模式，多人使用独立模式
    const isTwoPerson = activeParticipants.length === 2;
    
    // 初始化计时器状态
    const timerData = {
        platform: platform,
        groupId: groupId,
        subtype: subtype,
        startTime: now,
        participants: activeParticipants, // 使用过滤后的参与者
        timerStatus: {},
        lastRemindTime: null,
        timeoutDuration: getTimeout(subtype),
        timerMode: isTwoPerson ? "turn_taking" : "independent"
    };
    
    if (isTwoPerson) {
        // 一对一邀约：轮流模式
        timerData.timerStatus[initiator] = {
            status: "timing",
            startTime: now,
            repliedTime: null,
            wordCount: 0,
            remindedTimes: 0,
            isInitiator: true
        };
        
        const receiver = activeParticipants.find(p => p !== initiator);
        if (receiver) {
            timerData.timerStatus[receiver] = {
                status: "waiting",
                startTime: null,
                repliedTime: null,
                wordCount: 0,
                remindedTimes: 0,
                isInitiator: false
            };
        }
    } else {
        // 多人邀约：独立模式
        activeParticipants.forEach(participant => {
            const isInitiator = participant === initiator;
            timerData.timerStatus[participant] = {
                status: "timing", // 独立模式中，所有人一开始都计时
                startTime: now,
                repliedTime: null,
                wordCount: 0,
                remindedTimes: 0,
                isInitiator: isInitiator
            };
        });
    }
    
    timers[groupId] = timerData;
    saveGroupTimers(timers);
    
    console.log(`[监听系统] 初始化群组 ${groupId} 的计时器，参与者：${activeParticipants.join(',')}，模式：${isTwoPerson ? '轮流模式' : '独立模式'}`);
}

/**
 * 处理回复（监听消息时调用）
 * 修改：独立模式下，每个人回复后保持"已回复"状态，不改变其他人状态
 */
function handleReply(platform, groupId, roleName, message) {

    const settings = getMonitorSettings();
    if (!settings.enabled) {
        return false;
    }
    
    const timers = getGroupTimers();
    const timer = timers[groupId];
    if (!timer) {
        return false;
    }
    
    const roleStatus = timer.timerStatus[roleName];
    if (!roleStatus) {
        console.warn(`[监听系统] 处理失败: 角色 [${roleName}] 不在当前计时的参与者名单中`);
        return false;
    }
    
    // 检查状态
    console.log(`[监听系统] 角色 [${roleName}] 当前状态: ${roleStatus.status}, 模式: ${timer.timerMode}`);
    
    if (roleStatus.status !== "timing") {
        console.warn(`[监听系统] 忽略回复: [${roleName}] 的状态不是 "timing" (计时中)，当前状态为 "${roleStatus.status}"`);
        return false;
    }
    
    // 计算字数
    const wordCount = countWords(message);
    const minWords = getMinWords(timer.subtype);
    console.log(`[监听系统] 字数统计: 当前输入 ${wordCount} 字, 最低要求 ${minWords} 字`);
    
    // 检查是否达到最低字数要求
    if (wordCount < minWords) {
        console.warn(`[监听系统] 忽略回复: 字数不足 (需要 ${minWords} 字，实际 ${wordCount} 字)`);
        return false;
    }
    
    // --- 校验通过，开始更新数据 ---
    
    // 记录回复
    roleStatus.status = "replied";
    roleStatus.repliedTime = Date.now();
    roleStatus.wordCount = wordCount;
    
    // 更新用户统计
    updateUserStats(platform, roleName, wordCount, roleStatus.startTime, roleStatus.repliedTime);
    
    // 根据计时模式处理下一步
    if (timer.timerMode === "turn_taking") {
        const otherParticipant = timer.participants.find(p => p !== roleName);
        
        if (otherParticipant) {
            const otherStatus = timer.timerStatus[otherParticipant];
            if (otherStatus) {
                otherStatus.status = "timing";
                otherStatus.startTime = Date.now();
                otherStatus.repliedTime = null;
                otherStatus.wordCount = 0;
                otherStatus.remindedTimes = 0;
                console.log(`[监听系统] 轮流模式: 下一位角色 [${otherParticipant}] 已进入计时状态`);
            }
        } else {
            console.log(`[监听系统] 轮流模式: 未找到另一位参与者`);
        }
    } else {
        console.log(`[监听系统] 独立模式: 角色 [${roleName}] 回复成功，不影响其他人的计时状态`);
    }
    
    saveGroupTimers(timers);
    
    return true;
}

/**
 * 计算字数
 */
function countWords(text) {
    if (!text) return 0;
    
    // 移除CQ码
    const cleanText = text.replace(/\[CQ:[^\]]*\]/g, '');
    
    // 统计中文字符
    const chineseChars = (cleanText.match(/[\u4e00-\u9fa5]/g) || []).length;
    
    // 统计英文单词（按空格分割）
    const englishText = cleanText.replace(/[\u4e00-\u9fa5]/g, '');
    const englishWords = englishText.trim().split(/\s+/).filter(word => word.length > 0).length;
    
    return chineseChars + englishWords;
}

/**
 * 获取最低字数要求
 */
function getMinWords(subtype) {
    const settings = getMonitorSettings();
    switch(subtype) {
        case "电话": return settings.min_words_phone;
        case "私密": return settings.min_words_private;
        case "心愿": return settings.min_words_wish;
        case "官方约会": return settings.min_words_official;
        default: return settings.min_words_private;
    }
}

/**
 * 更新用户统计
 */
function updateUserStats(platform, roleName, wordCount, startTime, repliedTime) {
    const stats = getUserStats();
    const key = `${platform}:${roleName}`;
    
    if (!stats[key]) {
        stats[key] = {
            totalGroups: 0,
            totalWords: 0,
            replyTimes: {},
            subtypeStats: {}
        };
    }
    
    const userStat = stats[key];
    userStat.totalGroups += 1;
    userStat.totalWords += wordCount;
    
    // 计算回复时间（毫秒）
    const replyTimeMs = repliedTime - startTime;
    const replyTimeMin = Math.round(replyTimeMs / 60000);
    
    // 按类型统计
    if (!userStat.subtypeStats) userStat.subtypeStats = {};
    if (!userStat.subtypeStats[platform]) userStat.subtypeStats[platform] = {};
    if (!userStat.subtypeStats[platform][roleName]) {
        userStat.subtypeStats[platform][roleName] = {
            groups: 0,
            totalReplyTime: 0,
            fastestReply: null,
            slowestReply: null
        };
    }
    
    const subtypeStat = userStat.subtypeStats[platform][roleName];
    subtypeStat.groups += 1;
    subtypeStat.totalReplyTime += replyTimeMin;
    
    if (!subtypeStat.fastestReply || replyTimeMin < subtypeStat.fastestReply.time) {
        subtypeStat.fastestReply = { time: replyTimeMin, partner: "未知" };
    }
    if (!subtypeStat.slowestReply || replyTimeMin > subtypeStat.slowestReply.time) {
        subtypeStat.slowestReply = { time: replyTimeMin, partner: "未知" };
    }
    
    saveUserStats(stats);
}

/**
 * 检查超时并提醒
 */
function checkTimeouts() {
    const settings = getMonitorSettings();
    if (!settings.enabled) return;
    
    const timers = getGroupTimers();
    const now = Date.now();
    let hasReminders = false;
    
    for (const [groupId, timer] of Object.entries(timers)) {
        // 跳过已完成的
        if (timer.status === "completed") continue;
        
        // 检查每个人的状态
        for (const [roleName, status] of Object.entries(timer.timerStatus)) {
            // 只有计时状态才检查超时
            if (status.status === "timing" && status.startTime) {
                const elapsed = now - status.startTime;
                
                // 检查是否超时
                if (elapsed > timer.timeoutDuration) {
                    // 检查提醒间隔
                    const lastRemind = timer.lastRemindTime || 0;
                    const remindInterval = getRemindInterval(timer.subtype);
                    
                    if (now - lastRemind > remindInterval) {
                        // 发送提醒
                        sendReminder(timer.platform, groupId, roleName, timer.subtype, elapsed);
                        
                        // 更新提醒时间
                        timer.lastRemindTime = now;
                        status.remindedTimes += 1;
                        hasReminders = true;
                    }
                }
            }
        }
    }
    
    if (hasReminders) {
        saveGroupTimers(timers);
    }
}

/**
 * 获取提醒间隔
 */
function getRemindInterval(subtype) {
    const settings = getMonitorSettings();
    switch(subtype) {
        case "电话": return settings.remind_interval_phone;
        case "私密": return settings.remind_interval_private;
        case "心愿": return settings.remind_interval_wish;
        case "官方约会": return settings.remind_interval_official;
        default: return settings.remind_interval_private;
    }
}

/**
 * 发送提醒
 */
function sendReminder(platform, groupId, roleName, subtype, elapsedTime) {
    // 获取角色绑定的群
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const roleGroupId = a_private_group[platform]?.[roleName]?.[1];
    
    if (!roleGroupId) return;
    
    // 计算超时时间
    const hours = Math.floor(elapsedTime / 3600000);
    const minutes = Math.floor((elapsedTime % 3600000) / 60000);
    
    // 发送到角色绑定的群
    const msg1 = seal.newMessage();
    msg1.messageType = "group";
    msg1.groupId = `${platform}-Group:${roleGroupId}`;
    msg1.sender = {};
    const ctx1 = seal.createTempCtx(ctx.endPoint, msg1);
    
    seal.replyToSender(ctx1, msg1, 
        `⏰ 提醒：你在 ${subtype} 群 ${groupId} 中已超过 ${hours}小时${minutes}分钟未回复\n请尽快回复！`);
    
    // 发送到群组本身
    const msg2 = seal.newMessage();
    msg2.messageType = "group";
    msg2.groupId = `${platform}-Group:${groupId}`;
    msg2.sender = {};
    const ctx2 = seal.createTempCtx(ctx.endPoint, msg2);
    
    seal.replyToSender(ctx2, msg2, 
        `⏰ 提醒：${roleName} 已超过 ${hours}小时${minutes}分钟未回复\n请 ${roleName} 尽快回复！`);
}

/**
 * 结束私约时清理计时器
 */
function cleanupGroupTimer(groupId) {
    const timers = getGroupTimers();
    if (timers[groupId]) {
        delete timers[groupId];
        saveGroupTimers(timers);
        console.log(`[监听系统] 清理群组 ${groupId} 的计时器`);
    }
}

function forwardMsg(ctx, msg, wdId, targetGid) {
    if (!checkCondition(ctx)) return;

    // 1. 白名单校验
    const activeGroupsStr = ext.storageGet("group") || "[]";
    let activeGroups = JSON.parse(activeGroupsStr);
    const currentGroupId = ctx.group.groupId.replace(/[^\d]/g, "");
    
    if (!activeGroups.includes(currentGroupId)) {
        seal.replyToSender(ctx, msg, `⚠️ 本群(${currentGroupId})未在系统中注册，无法转发。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 暂存目标群号和当前群名，供 ws 回调逻辑提取
    ext.storageSet("temp_target_gid", targetGid.toString().replace(/[^\d]/g, ""));
    ext.storageSet("temp_source_group_name", ctx.group.groupName || "未知群聊");

    // 3. 核心步骤：获取消息原始内容
    const postData = {
        "action": "get_msg",
        "params": { "message_id": wdId }
    };

    console.log(`[转发系统] 正在从消息ID ${wdId} 提取原始节点...`);
    // 调用统一的 ws 函数，后续逻辑在 ws 的 onmessage 中根据 get_msg 处理
    return ws(postData, ctx, msg, ""); 
}

function withdrawMsg(ctx, msg, wdId) {
    if (!checkCondition(ctx)) return;
    const postData = {
        "action": "delete_msg",
        "params": { 
            "message_id": parseInt(wdId) // 关键：确保是数字
        }
    };
    return ws(postData, ctx, msg, "已执行撤回操作。");
}

// 通用条件检查
function checkCondition(ctx) {
    const triggerCondition = seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件");
    const fmtCondition = parseInt(seal.format(ctx, `{${triggerCondition}}`));
    return fmtCondition === 1;
}

// ========================
// 👂 消息监听处理
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = msg.rawMessage || msg.message || "";
    const platform = msg.platform;
    const groupId = msg.groupId.replace(`${platform}-Group:`, '');

    // 统一匹配回复 ID
    const replyMatch = raw.match(/\[CQ:reply,id=(\-?\d+)\]/);
    const wdId = replyMatch ? Number(replyMatch[1]) : null;

    if (wdId !== null) {
        // 1. 处理撤回
        if (raw.includes("撤回")) {
            withdrawMsg(ctx, msg, wdId);
            return;
        }

        // 2. 处理点歌
        if (raw.includes("点歌")) {
            const songGroupId = ext.storageGet("song_group_id"); 
            if (!songGroupId) return seal.replyToSender(ctx, msg, "❌ 未配置点歌群号");

            // 严格匹配格式
            const dgrMatch = raw.match(/点歌人[:：]\s*(.*?)(?=\s|,|，|留言|$)/);
            const lyMatch = raw.match(/留言[:：]\s*(.*)/);

            if (!dgrMatch || !lyMatch) {
                const helpText = `⚠️ 格式不规范！\n回复卡片并输入：\n点歌 点歌人：xx 留言：xx`;
                seal.replyToSender(ctx, msg, helpText);
                return;
            }

            ext.storageSet("temp_target_gid", songGroupId);
            ext.storageSet("temp_task_type", "song");
            ext.storageSet("temp_song_dgr", dgrMatch[1].trim());
            ext.storageSet("temp_song_ly", lyMatch[1].trim());
            
            ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg);
            return;
        }

        // 3. 处理复盘
        if (raw.includes("转发复盘") || raw.includes("复盘")) {
            const backgroundGroupId = ext.storageGet("background_group_id");
            if (!backgroundGroupId) return seal.replyToSender(ctx, msg, "未配置目标群号");

            ext.storageSet("temp_target_gid", backgroundGroupId);
            ext.storageSet("temp_task_type", "forward");
            ext.storageSet("temp_source_group_name", ctx.group.groupName);
            
            ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg);
            const helpText = `已复盘至后台群，请尽快退出群聊！`;
            seal.replyToSender(ctx, msg, helpText);
            return;
        }
    }

    // --- 原有的私有群监听逻辑 ---
    try {
        const uid = msg.sender.userId.replace(`${platform}:`, '');
        const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
        const roleName = Object.entries(a_private_group[platform] || {})
            .find(([_, val]) => val[0] === uid)?.[0];
        if (roleName) {
            handleReply(platform, groupId, roleName, msg.message);
        }
    } catch (e) {
        console.error('监听系统错误:', e);
    }
};

let cmd_view_schedule = seal.ext.newCmdItemInfo();
cmd_view_schedule.name = "时间线";
cmd_view_schedule.help = "。时间线（显示你已确认和待建的所有小群安排）";

cmd_view_schedule.solve = (ctx, msg) => {
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const roleId = uid.replace(`${platform}:`, "");
  const schedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
  const b_MultiGroupRequest = JSON.parse(ext.storageGet("b_MultiGroupRequest") || "{}");
  const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
  const groupTimers = JSON.parse(ext.storageGet("group_timers") || "{}");

  let events = schedule[uid] ? schedule[uid].slice() : [];
  const myRoleName = Object.keys(a_private_group[platform] || {}).find(name => a_private_group[platform][name][0] === roleId);

  // --- 数据聚合部分 (保持原逻辑不变) ---
  for (let [ref, group] of Object.entries(b_MultiGroupRequest)) {
    const activeParticipants = Object.entries(group.targetList || {})
      .filter(([_, status]) => status === "accepted" || status === null)
      .map(([name]) => name);
    if (activeParticipants.length === 0) continue;

    const isRecipient = group.targetList?.[myRoleName] === "accepted";
    const isSender = group.sendid === roleId;

    if (isRecipient || isSender) {
      const allTargets = isSender ? [...new Set([group.sendname, ...activeParticipants])] : activeParticipants;
      const alreadyIncluded = events.some(e => e.day === group.day && e.time === group.time && e.place === group.place);
      
      if (!alreadyIncluded) {
        events.push({
          day: group.day, time: group.time, subtype: group.subtype, place: group.place,
          partner: isSender ? allTargets.join("、") : group.sendname, // 简化伙伴显示
          status: "pending", isMulti: !!group.groupRef, multiRef: ref, group: null
        });
      }
    }
  }

  if (events.length === 0) {
    seal.replyToSender(ctx, msg, "✨ 【日程表】\n\n当前暂无行程安排，享受自由时光吧。");
    return seal.ext.newCmdExecuteResult(true);
  }

  // --- 排序逻辑 ---
  const sorted = events.sort((a, b) => {
    const dayNum = s => parseInt(s.day.slice(1));
    const timeStart = s => parseInt(s.time.split("-")[0].replace(":", ""));
    return dayNum(a) - dayNum(b) || timeStart(a) - timeStart(b);
  });

  // --- 排版展示部分 ---
  let rep = "📱 ─── 我的个人时间线 ─── 📱\n\n";

  const grouped = {};
  for (const ev of sorted) {
    if (!grouped[ev.day]) grouped[ev.day] = [];
    grouped[ev.day].push(ev);
  }

  const daySort = (a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1));
  const dayKeys = Object.keys(grouped).sort(daySort);

  dayKeys.forEach((day, dIdx) => {
    rep += `📅 **${day}**\n`;
    
    grouped[day].forEach((ev, eIdx) => {
      // 1. 确定状态图标与色彩感
      let statusLabel = "";
      let timelineIcon = "┣"; 
      if (eIdx === grouped[day].length - 1) timelineIcon = "┗";

      const isEnded = ev.status === "ended";
      const isPending = ev.status === "pending";
      const isActive = !isEnded && !isPending;

      // 2. 状态标签解析
      if (isEnded) statusLabel = "已完结";
      else if (isPending) statusLabel = "待开启";
      else statusLabel = "进行中";

      // 3. 回复状态检测 (针对进行中)
      let replyTag = "";
      if (isActive && ev.group && groupTimers[ev.group]) {
        const rStatus = groupTimers[ev.group].timerStatus?.[myRoleName];
        if (rStatus?.status === "replied") replyTag = " [已回]";
        else if (rStatus?.status === "timing") replyTag = " [⏳未回]";
      } else if (isPending && ev.isMulti && ev.multiRef) {
        const mStatus = b_MultiGroupRequest[ev.multiRef]?.targetList?.[myRoleName];
        if (mStatus === "accepted") replyTag = " [🤝已接]";
      }

      // 4. 类型图标
      const typeIcon = ev.subtype === "电话" ? "📞" : (ev.subtype === "续杯" ? "🍷" : "🎭");

      // 5. 组合单行卡片
      rep += `${timelineIcon}── ${ev.time}\n`;
      rep += `    ${typeIcon} ${ev.subtype} · ${statusLabel}${replyTag}\n`;
      rep += `    📍 地点：${ev.place || "未知"}\n`;
      rep += `    👥 伙伴：${ev.partner}\n`;
      rep += `\n`;
    });
  });

  rep += "─── END OF TIMELINE ───";
  seal.replyToSender(ctx, msg, rep.trim());
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["时间线"] = cmd_view_schedule;

// ========================
// 📊 查看计时器状态指令（增强版 - 显示等待时间）
// ========================

let cmd_view_timers = seal.ext.newCmdItemInfo();
cmd_view_timers.name = "查看计时器";
cmd_view_timers.help = "查看计时器 [群号] - 查看计时器状态和回复等待时间";
cmd_view_timers.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const timers = getGroupTimers();
    const timerCount = Object.keys(timers).length;
    const now = Date.now();
    
    if (timerCount === 0) {
        seal.replyToSender(ctx, msg, "📭 当前没有活跃的计时器");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 1. 构造合并消息的节点列表
    const nodes = [];

    // 页眉节点
    nodes.push({
        type: "node",
        data: {
            name: "计时监控中心",
            uin: "2852199344", // 使用系统通知头像
            content: `📊 当前共有 ${timerCount} 个计时器正在运行\n数据更新时间：${new Date().toLocaleTimeString()}`
        }
    });

    // 遍历计时器生成详细节点
    Object.entries(timers).forEach(([gid, timer]) => {
        let nodeText = `📍 群组：${gid}\n`;
        nodeText += `✨ 类型：${timer.subtype} | 🎮 模式：${timer.timerMode === 'turn_taking' ? '轮流' : '独立'}\n`;
        nodeText += `━━━━━━━━━━━━━━━\n`;

        Object.entries(timer.timerStatus).forEach(([name, status]) => {
            const elapsed = status.startTime ? Math.round((now - status.startTime) / 60000) : 0;
            const remainingMs = status.startTime ? (timer.timeoutDuration - (now - status.startTime)) : 0;
            
            let statusIcon = "⏸️";
            let timeStr = "";

            if (status.status === "timing") {
                statusIcon = remainingMs > 0 ? "⏳" : "🔴";
                const absMins = Math.abs(Math.round(remainingMs / 60000));
                timeStr = remainingMs > 0 ? ` (剩${absMins}min)` : ` (超${absMins}min!)`;
            } else if (status.status === "replied") {
                statusIcon = "✅";
            }

            nodeText += `${statusIcon} ${name}: ${status.status}${timeStr}\n`;
        });

        nodes.push({
            type: "node",
            data: {
                name: `群组 ${gid} 详情`,
                uin: "10001",
                content: nodeText.trim()
            }
        });
    });

    // 2. 发送逻辑：如果是私聊或群聊，都调用合并消息接口
    const targetGid = msg.groupId.replace(/[^\d]/g, "");
    
    // 调用 WebSocket 发送合并消息 (OneBot 标准)
    // 这里的 ws 是你代码中封装的发送函数
    ws({
        "action": "send_group_forward_msg",
        "params": {
            "group_id": parseInt(targetGid, 10),
            "messages": nodes
        }
    }, ctx, msg, "");

    // 3. 同时给管理员发一个简短的回执（防止管理员以为没反应）
    const totalOverdue = Object.values(timers).reduce((sum, t) => {
        return sum + Object.values(t.timerStatus).filter(s => s.status === 'timing' && (now - s.startTime) > t.timeoutDuration).length;
    }, 0);

    seal.replyToSender(ctx, msg, `✅ 监控报表已生成\n⏳ 待回：${totalOverdue} 人超时\n(详情请点击下方合并消息查看)`);
    
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看计时器"] = cmd_view_timers;

// ========================
// ⏰ 提醒超时指令 - 温柔版（管理员专用）
// ========================

let cmd_remind_timeouts = seal.ext.newCmdItemInfo();
cmd_remind_timeouts.name = "提醒超时";
cmd_remind_timeouts.help = "提醒超时 [群号] - 温柔地提醒所有超时未回复的人（管理员专用）";

cmd_remind_timeouts.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "亲爱的管理员，这个指令需要管理员权限才能使用哦～ 🌸");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const targetGroup = cmdArgs.getArgN(1);
    const timers = getGroupTimers();
    const settings = getMonitorSettings();
    
    if (!settings.enabled) {
        seal.replyToSender(ctx, msg, "亲爱的管理员，监听系统当前处于休息状态呢，暂时无法发送提醒哦～ 💤");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    if (Object.keys(timers).length === 0) {
        seal.replyToSender(ctx, msg, "🌙 现在大家都好乖呢，没有人在超时等待回复中，真是令人欣慰～");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const now = Date.now();
    let remindersSent = [];
    let noTimeouts = [];
    let noTimer = [];
    
    // 获取私密群组映射
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    // 遍历计时器
    for (const [groupId, timer] of Object.entries(timers)) {
        // 如果指定了群号，只处理该群
        if (targetGroup && groupId !== targetGroup) continue;
        
        let groupReminders = [];
        let groupNoTimeouts = true;
        
        // 检查每个参与者的状态
        for (const [roleName, status] of Object.entries(timer.timerStatus)) {
            // 只检查计时中且已超时的人
            if (status.status === "timing" && status.startTime) {
                const elapsed = now - status.startTime;
                
                if (elapsed > timer.timeoutDuration) {
                    // 检查提醒间隔
                    const lastRemind = timer.lastRemindTime || 0;
                    const remindInterval = getRemindInterval(timer.subtype);
                    
                    if (now - lastRemind > remindInterval) {
                        // 发送温柔的提醒
                        const platform = timer.platform;
                        const roleGroupId = a_private_group[platform]?.[roleName]?.[1];
                        
                        if (roleGroupId) {
                            // 发送到角色绑定的群 - 温柔版
                            const msg1 = seal.newMessage();
                            msg1.messageType = "group";
                            msg1.groupId = `${platform}-Group:${roleGroupId}`;
                            msg1.sender = {};
                            const ctx1 = seal.createTempCtx(ctx.endPoint, msg1);
                            
                            const hours = Math.floor(elapsed / 3600000);
                            const minutes = Math.floor((elapsed % 3600000) / 60000);
                            
                            // 温柔版提醒消息
                            let gentleMessage = "";
                            
                            if (hours >= 3) {
                                gentleMessage = 
                                    `💫 亲爱的 ${roleName}～\n` +
                                    `注意到你在「${timer.subtype}」的小群 ${groupId} 中已经 ${hours}小时${minutes}分钟没有回应了呢～\n` +
                                    `是不是遇到什么小困扰啦？需要的话可以随时找我们聊聊哦～\n` +
                                    `其他小伙伴还在耐心等待你的回应呢，记得抽空回一下呀～ ❤️\n\n` +
                                    `✨ 小贴士：慢慢来，不着急，照顾好自己最重要～`;
                            } else if (hours >= 1) {
                                gentleMessage = 
                                    `🌸 亲爱的 ${roleName}～\n` +
                                    `你的小伙伴们在「${timer.subtype}」的小群 ${groupId} 中等你 ${hours}小时${minutes}分钟了哦～\n` +
                                    `可能是忙碌中一时忘记了呢？有空的时候回一下大家吧～\n` +
                                    `期待看到你的回应哦～ 🌟\n\n` +
                                    `💌 温馨提示：回复不用太完美，真诚的交流最珍贵～`;
                            } else {
                                gentleMessage = 
                                    `✨ 亲爱的 ${roleName}～\n` +
                                    `你在「${timer.subtype}」的小群 ${groupId} 中有个小提醒呢～\n` +
                                    `已经 ${minutes} 分钟过去啦，是不是刚好在思考怎么回复呀？\n` +
                                    `想到什么就说什么吧，大家都很期待听到你的声音呢～ 🌈\n\n` +
                                    `💝 慢慢来，我们等你～`;
                            }
                            
                            seal.replyToSender(ctx1, msg1, gentleMessage);
                            
                            // 发送到群组本身 - 同样温柔的语气
                            const msg2 = seal.newMessage();
                            msg2.messageType = "group";
                            msg2.groupId = `${platform}-Group:${groupId}`;
                            msg2.sender = {};
                            const ctx2 = seal.createTempCtx(ctx.endPoint, msg2);
                            
                            const groupNotice = 
                                `🌷 给 ${roleName} 的温馨小提示：\n` +
                                `大家注意到你已经 ${hours}小时${minutes}分钟没有回复啦～\n` +
                                `是不是在忙或者需要更多思考时间呢？\n` +
                                `慢慢来，不着急，我们理解你可能需要一点空间～ 🌼\n` +
                                `等你准备好，随时可以加入我们的对话哦～`;
                            
                            seal.replyToSender(ctx2, msg2, groupNotice);
                            
                            // 记录提醒
                            groupReminders.push({
                                roleName,
                                hours,
                                minutes,
                                type: timer.subtype
                            });
                            
                            // 更新提醒时间和计数
                            timer.lastRemindTime = now;
                            status.remindedTimes = (status.remindedTimes || 0) + 1;
                            groupNoTimeouts = false;
                        }
                    }
                }
            }
        }
        
        // 如果有发送提醒，更新计时器
        if (groupReminders.length > 0) {
            saveGroupTimers(timers);
            remindersSent.push({
                groupId,
                reminders: groupReminders,
                subtype: timer.subtype,
                participants: timer.participants
            });
        } else if (targetGroup && groupNoTimeouts) {
            noTimeouts.push(`群组 ${groupId} 里的小伙伴们都好准时呢，没有超时的～ 🌟`);
        }
    }
    
    // 构建温柔的报告消息
    let rep = "";
    
    if (targetGroup) {
        // 指定群组的报告
        if (remindersSent.length > 0) {
            rep += `🌺 管理员亲爱的，关于群组 ${targetGroup} 的提醒情况：\n`;
            rep += "═" .repeat(35) + "\n";
            
            remindersSent.forEach(result => {
                rep += `\n🌼 群组 ${result.groupId}（${result.subtype}类型）\n`;
                rep += `🤗 参与者：${result.participants?.join("、") || "可爱的大家"}\n`;
                rep += `💕 已经温柔提醒了 ${result.reminders.length} 位朋友：\n`;
                
                result.reminders.forEach(r => {
                    rep += `   • ${r.roleName}（已经等待 ${r.hours}小时${r.minutes}分钟）\n`;
                });
            });
            
            rep += `\n🌸 提醒已经温柔地发出啦，希望不会打扰到大家～`;
        } else if (noTimeouts.length > 0) {
            rep += `💫 ${noTimeouts.join("\n")}`;
        } else {
            rep = `🌙 没有找到群组 ${targetGroup} 的信息呢，可能还没有计时器在运行～`;
        }
    } else {
        // 全群提醒结果
        const totalReminders = remindersSent.reduce((sum, result) => sum + result.reminders.length, 0);
        
        if (totalReminders > 0) {
            rep += `💖 亲爱的管理员，温柔提醒任务完成啦～\n`;
            rep += "═" .repeat(40) + "\n";
            rep += `📊 检查了 ${Object.keys(timers).length} 个群组\n`;
            rep += `💌 共发送了 ${totalReminders} 条温柔提醒\n`;
            rep += `🌷 涉及 ${remindersSent.length} 个群组\n\n`;
            
            // 按类型统计
            const statsByType = {};
            remindersSent.forEach(result => {
                const type = result.subtype;
                if (!statsByType[type]) statsByType[type] = 0;
                statsByType[type] += result.reminders.length;
            });
            
            if (Object.keys(statsByType).length > 0) {
                rep += "🌈 按类型统计：\n";
                Object.entries(statsByType).forEach(([type, count]) => {
                    const emoji = 
                        type === "电话" ? "📞" : 
                        type === "私密" ? "🤫" : 
                        type === "心愿" ? "💌" : 
                        type === "官方约会" ? "🏢" : "✨";
                    rep += `${emoji} ${type}：${count} 条提醒\n`;
                });
                rep += "\n";
            }
            
            // 详细列表（简洁版）
            rep += "🌸 提醒发送详情：\n";
            remindersSent.forEach((result, index) => {
                const emoji = ["💖", "💝", "💗", "💓", "💞"][index % 5];
                rep += `${emoji} 群组 ${result.groupId}：`;
                rep += `${result.reminders.map(r => r.roleName).join("、")}\n`;
            });
            
            rep += `\n💕 所有的提醒都已经用最温柔的方式发送出去啦～`;
        } else {
            rep = 
                `🌙 检查完成啦～\n` +
                `现在所有的群组都很好呢，没有超时未回的情况～\n` +
                `大家都很守时，真是令人欣慰呢～ 🌟`;
        }
    }
    
    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["提醒超时"] = cmd_remind_timeouts;


// ========================
// ⚙️ 设置监听参数指令（增强版 - 应用到进行中计时器）
// ========================

/**
 * 更新所有活跃计时器的超时设置
 * @param {Object} newSettings 新的监控设置
 * @returns {Object} 更新结果 { updated: number, total: number }
 */
function updateActiveTimerSettings(newSettings) {
    const timers = getGroupTimers();
    let updatedCount = 0;
    const now = Date.now();
    
    for (const [groupId, timer] of Object.entries(timers)) {
        let needUpdate = false;
        
        // 根据计时器类型更新超时时间
        const oldTimeout = timer.timeoutDuration;
        let newTimeout = oldTimeout;
        
        switch(timer.subtype) {
            case "电话":
                newTimeout = newSettings.timeout_phone;
                break;
            case "私密":
                newTimeout = newSettings.timeout_private;
                break;
            case "心愿":
                newTimeout = newSettings.timeout_wish;
                break;
            case "官方约会":
                newTimeout = newSettings.timeout_official;
                break;
            default:
                newTimeout = newSettings.timeout_private;
        }
        
        // 如果超时时间发生变化
        if (newTimeout !== oldTimeout) {
            timer.timeoutDuration = newTimeout;
            needUpdate = true;
            
            // 记录变化日志
            console.log(`[监听系统] 群组 ${groupId}（${timer.subtype}）超时时间已更新：${oldTimeout/3600000}小时 -> ${newTimeout/3600000}小时`);
        }
        
        // 更新提醒间隔信息
        timer.remindInterval = getRemindInterval(timer.subtype);
        
        if (needUpdate) {
            updatedCount++;
            
            // 检查是否需要调整状态（如果新的超时时间已过）
            for (const [roleName, status] of Object.entries(timer.timerStatus)) {
                if (status.status === "timing" && status.startTime) {
                    const elapsed = now - status.startTime;
                    if (elapsed > newTimeout) {
                        // 如果已经超过新的超时时间，标记为超时
                        console.log(`[监听系统] 注意：${roleName} 在新的超时设置下已超时`);
                    }
                }
            }
        }
    }
    
    if (updatedCount > 0) {
        saveGroupTimers(timers);
    }
    
    return {
        updated: updatedCount,
        total: Object.keys(timers).length
    };
}
let cmd_set_monitor_params = seal.ext.newCmdItemInfo();
cmd_set_monitor_params.name = "设置监听参数";
cmd_set_monitor_params.help = `⚙️ 设置监听参数 [参数]

📌 格式：类型=字数/超时
（提醒间隔已移除，仅需设置两个参数）

🔹 类型：电话、私密、心愿、官约、所有
🔹 字数：最小回复字数限制
🔹 超时：允许最长不说话时间（小时）

✅ 示例：
  。设置监听参数 电话=20/1
  。设置监听参数 私密=150/3
  。设置监听参数 所有=100/2

✨ 生效后将同步至所有进行中的计时器`;

cmd_set_monitor_params.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "亲爱的管理员，这个指令需要管理员权限哦～ 🌸");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const settings = getMonitorSettings();
    
    // 1. 无参数时：显示当前配置快照
    if (!cmdArgs.getArgN(1)) {
        let rep = "🌸 当前监听系统配置 🌸\n";
        rep += "━━━━━━━━━━━━━━━\n\n";
        
        const configMap = [
            { label: "📞 电话", w: settings.min_words_phone, t: settings.timeout_phone },
            { label: "🤫 私密", w: settings.min_words_private, t: settings.timeout_private },
            { label: "💌 心愿", w: settings.min_words_wish, t: settings.timeout_wish },
            { label: "🏛️ 官约", w: settings.min_words_official, t: settings.timeout_official }
        ];

        configMap.forEach(item => {
            rep += `${item.label}\n`;
            rep += `┗ 📝 ${item.w}字 | ⏰ ${item.t / 3600000}h\n\n`;
        });
        
        rep += `📊 活跃计时群组：${Object.keys(getGroupTimers()).length} 个\n`;
        rep += "━━━━━━━━━━━━━━━\n";
        rep += "💡 格式：类型=字数/超时 (小时)";
        
        seal.replyToSender(ctx, msg, rep.trim());
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 2. 解析参数 (格式：类型=字数/超时)
    let updates = [];
    let errors = [];
    let hasUpdate = false;
    
    for (let i = 1; ; i++) {
        const arg = cmdArgs.getArgN(i);
        if (!arg) break;
        
        // 正则修改：只匹配 两个 参数 (字数/超时)
        const match = arg.match(/^(\S+)=(\d+)\/([\d.]+)$/);
        if (!match) {
            errors.push(`${arg} (格式需为: 类型=字数/超时)`);
            continue;
        }
        
        const type = match[1].toLowerCase();
        const words = parseInt(match[2]);
        const timeoutMs = parseFloat(match[3]) * 3600000;

        const targetTypes = [];
        if (["所有", "all", "*"].includes(type)) {
            targetTypes.push("phone", "private", "wish", "official");
        } else if (type === "电话" || type === "phone") targetTypes.push("phone");
        else if (type === "私密" || type === "private") targetTypes.push("private");
        else if (type === "心愿" || type === "wish") targetTypes.push("wish");
        else if (type === "官约" || type === "official") targetTypes.push("official");
        else {
            errors.push(`未知类型: ${type}`);
            continue;
        }

        targetTypes.forEach(t => {
            settings[`min_words_${t}`] = words;
            settings[`timeout_${t}`] = timeoutMs;
        });
        
        updates.push(`${type} → ${words}字/${match[3]}h`);
        hasUpdate = true;
    }
    
    // 3. 保存并反馈
    if (hasUpdate) {
        setMonitorSettings(settings);
        // 调用同步函数，让正在计时的群组也变掉
        updateActiveTimerSettings(settings); 

        let res = "✅ 监听参数更新完成\n";
        res += "───────────────\n";
        updates.forEach(u => res += `· ${u}\n`);
        if (errors.length > 0) {
            res += "\n❌ 部分失败：\n";
            errors.forEach(e => res += `· ${e}\n`);
        }
        seal.replyToSender(ctx, msg, res.trim());
    } else {
        seal.replyToSender(ctx, msg, "❌ 更新失败：\n" + errors.join("\n"));
    }
    
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置监听参数"] = cmd_set_monitor_params;

// ========================
// 🔄 重置所有计时器超时指令
// ========================

let cmd_reset_all_timers = seal.ext.newCmdItemInfo();
cmd_reset_all_timers.name = "重置计时器设置";
cmd_reset_all_timers.help = "重置计时器设置 - 强制所有计时器重新加载当前设置";

cmd_reset_all_timers.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "亲爱的管理员，这个指令需要管理员权限哦～ 🌸");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const timers = getGroupTimers();
    const timerCount = Object.keys(timers).length;
    
    if (timerCount === 0) {
        seal.replyToSender(ctx, msg, "🌙 当前没有活跃的计时器，无需重置");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const settings = getMonitorSettings();
    const updateResult = updateActiveTimerSettings(settings);
    
    let rep = 
        `🔄 计时器设置重置完成 🔄\n` +
        "═" .repeat(40) + "\n\n";
    
    rep += `📊 重置统计：\n`;
    rep += `• 活跃群组：${updateResult.total} 个\n`;
    rep += `• 已更新：${updateResult.updated} 个\n\n`;
    
    if (updateResult.updated > 0) {
        rep += `✅ 所有计时器已重新应用当前设置\n\n`;
        
        // 显示当前设置概览
        rep += `📋 当前生效的设置：\n`;
        rep += `• 电话：${settings.timeout_phone / 3600000}小时超时\n`;
        rep += `• 私密：${settings.timeout_private / 3600000}小时超时\n`;
        rep += `• 心愿：${settings.timeout_wish / 3600000}小时超时\n`;
        rep += `• 官方约会：${settings.timeout_official / 3600000}小时超时\n`;
        rep += `• 自动监控：${settings.auto_monitor_all_groups ? '✅ 启用' : '❌ 禁用'}\n\n`;
        
        rep += `✨ 所有进行中的计时器现在使用统一的超时标准`;
    } else {
        rep += `📭 所有计时器已经使用最新设置，无需更新`;
    }
    
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["重置计时器设置"] = cmd_reset_all_timers;

// ========================
// 📊 检查设置一致性指令
// ========================

let cmd_check_timer_settings = seal.ext.newCmdItemInfo();
cmd_check_timer_settings.name = "检查计时器设置";
cmd_check_timer_settings.help = "检查计时器设置 - 检查计时器设置与当前配置是否一致";

cmd_check_timer_settings.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "亲爱的管理员，这个指令需要管理员权限哦～ 🌸");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const timers = getGroupTimers();
    const timerCount = Object.keys(timers).length;
    const settings = getMonitorSettings();
    const now = Date.now();
    
    if (timerCount === 0) {
        seal.replyToSender(ctx, msg, "🌙 当前没有活跃的计时器");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    let inconsistentTimers = [];
    let warningTimers = [];
    
    for (const [groupId, timer] of Object.entries(timers)) {
        const expectedTimeout = (() => {
            switch(timer.subtype) {
                case "电话": return settings.timeout_phone;
                case "私密": return settings.timeout_private;
                case "心愿": return settings.timeout_wish;
                case "官方约会": return settings.timeout_official;
                default: return settings.timeout_private;
            }
        })();
        
        // 检查超时时间是否一致
        if (Math.abs(timer.timeoutDuration - expectedTimeout) > 1000) { // 允许1秒的误差
            inconsistentTimers.push({
                groupId,
                subtype: timer.subtype,
                current: timer.timeoutDuration / 3600000,
                expected: expectedTimeout / 3600000,
                participants: timer.participants.length
            });
        }
        
        // 检查是否有严重超时的计时器
        for (const [roleName, status] of Object.entries(timer.timerStatus)) {
            if (status.status === "timing" && status.startTime) {
                const elapsed = now - status.startTime;
                const overtime = elapsed - expectedTimeout;
                
                if (overtime > expectedTimeout * 0.5) { // 超时超过50%
                    warningTimers.push({
                        groupId,
                        roleName,
                        subtype: timer.subtype,
                        elapsedHours: Math.round(elapsed / 3600000 * 10) / 10,
                        expectedHours: expectedTimeout / 3600000,
                        overtimeHours: Math.round(overtime / 3600000 * 10) / 10
                    });
                }
            }
        }
    }
    
    let rep = 
        `🔍 计时器设置一致性检查 🔍\n` +
        "═" .repeat(45) + "\n\n";
    
    rep += `📊 总体情况：\n`;
    rep += `• 活跃群组：${timerCount} 个\n`;
    rep += `• 设置不一致：${inconsistentTimers.length} 个\n`;
    rep += `• 严重超时警告：${warningTimers.length} 个\n`;
    rep += `• 自动监控状态：${settings.auto_monitor_all_groups ? '✅ 启用' : '❌ 禁用'}\n\n`;
    
    // 显示不一致的计时器
    if (inconsistentTimers.length > 0) {
        rep += `⚠️ 设置不一致的计时器：\n`;
        inconsistentTimers.forEach((item, index) => {
            rep += `${index + 1}. 群组 ${item.groupId}（${item.subtype}）\n`;
            rep += `   当前：${item.current}小时，应为：${item.expected}小时\n`;
            rep += `   参与者：${item.participants}人\n`;
        });
        rep += `\n💡 建议使用「重置计时器设置」指令同步设置\n\n`;
    }
    
    // 显示严重超时警告
    if (warningTimers.length > 0) {
        rep += `🚨 严重超时警告：\n`;
        warningTimers.forEach((item, index) => {
            rep += `${index + 1}. 群组 ${item.groupId}（${item.subtype}）\n`;
            rep += `   ${item.roleName} 已等待 ${item.elapsedHours}小时\n`;
            rep += `   （超时 ${item.overtimeHours}小时）\n`;
        });
        rep += `\n💡 建议使用「提醒超时」指令发送提醒\n\n`;
    }
    
    // 显示当前设置
    if (inconsistentTimers.length === 0 && warningTimers.length === 0) {
        rep += `✅ 所有计时器设置一致，运行正常\n\n`;
    }
    
    rep += `📋 当前系统设置：\n`;
    rep += `• 电话：${settings.timeout_phone / 3600000}小时超时\n`;
    rep += `• 私密：${settings.timeout_private / 3600000}小时超时\n`;
    rep += `• 心愿：${settings.timeout_wish / 3600000}小时超时\n`;
    rep += `• 官方约会：${settings.timeout_official / 3600000}小时超时`;
    
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["检查计时器设置"] = cmd_check_timer_settings;

// ========================
// 💬 微信长期群聊功能（修改版）
// ========================

// 🔧 检查两人之间是否已有活跃微信群
function checkWechatBetweenUsers(platform, user1, user2) {
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};
    
    for (const groupId in platformGroups) {
        const group = platformGroups[groupId];
        // 只检查活跃群
        if (group.status === "active") {
            // 检查两个用户是否都在这个群中
            if (group.participants.includes(user1) && group.participants.includes(user2)) {
                return {
                    exists: true,
                    groupId: groupId,
                    topic: group.topic || "(无主题)"
                };
            }
        }
    }
    
    return { exists: false };
}

// 🔧 查看我的微信群
let cmd_view_my_wechat = seal.ext.newCmdItemInfo();
cmd_view_my_wechat.name = "我的微信群";
cmd_view_my_wechat.help = "。我的微信群 - 查看你参与的微信群";
cmd_view_my_wechat.solve = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    
    // 获取用户角色名
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const roleName = Object.entries(a_private_group[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0];
    
    if (!roleName) {
        seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
        return seal.ext.newCmdExecuteResult(true);
    }

    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};
    
    let myGroups = [];
    
    // 查找用户参与的微信群
    for (const groupId in platformGroups) {
        const group = platformGroups[groupId];
        if (group.participants.includes(roleName)) {
            myGroups.push({
                id: groupId,
                ...group
            });
        }
    }

    if (myGroups.length === 0) {
        seal.replyToSender(ctx, msg, "📭 你当前没有参与任何微信群");
        return seal.ext.newCmdExecuteResult(true);
    }

    let rep = "💬 你参与的微信群：\n\n";
    myGroups.forEach((group, index) => {
        const status = group.status === "active" ? "✅ 活跃" : "❌ 已结束";
        const topic = group.topic ? `「${group.topic}」` : "(无主题)";
        rep += `${index + 1}. 群号：${group.id}\n`;
        rep += `   主题：${topic}\n`;
        rep += `   状态：${status}\n`;
        rep += `   创建者：${group.creator}\n`;
        rep += `   创建时间：${group.created_at}\n`;
        rep += `   成员：${group.participants.join("、")}\n`;
        rep += `\n`;
    });

    rep += "💡 温馨提示：\n";
    rep += "- 每个微信关系只能有一个活跃群\n";
    rep += "- 结束微信群需要管理员权限";

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["我的微信群"] = cmd_view_my_wechat;

// 🔧 创建微信群指令（增加两人之间唯一性检查）
let cmd_wechat = seal.ext.newCmdItemInfo();
cmd_wechat.name = "微信";
cmd_wechat.help = "。微信 对方角色名[/对方2/...] [主题] - 创建长期微信群聊\n示例：\n。微信 张三\n。微信 李四/王五 一起讨论剧情";

cmd_wechat.solve = (ctx, msg, cmdArgs) => {
    // 检查功能是否开启
    let config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_wechat === false) {
        seal.replyToSender(ctx, msg, "💬 微信功能已关闭，无法创建微信群");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    
    // 获取发送者角色名
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};
    
    const sendname = Object.entries(a_private_group[platform])
        .find(([_, val]) => val[0] === uid)?.[0];
    
    if (!sendname) {
        seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查用户是否被禁止使用微信功能
    const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
    if (blockMap[sendname] && blockMap[sendname].enable_wechat === false) {
        seal.replyToSender(ctx, msg, "🚫 您已被禁止使用微信功能");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取参数
    const namesArg = cmdArgs.getArgN(1);
    const topic = cmdArgs.getArgN(2);

    if (!namesArg) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    // 解析邀请人
    const names = namesArg.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
    const isMulti = names.length > 0;

    // 检查所有邀请人
    let failed = [];
    for (let toname of names) {
        // 检查对方是否已绑定
        if (!a_private_group[platform] || !a_private_group[platform][toname]) {
            failed.push(`${toname}（未注册）`);
            continue;
        }

        // 不能邀请自己
        if (toname === sendname) {
            failed.push(`${toname}（不能邀请自己）`);
            continue;
        }
        
        // 🆕 检查两人之间是否已有活跃微信群
        const existingGroup = checkWechatBetweenUsers(platform, sendname, toname);
        if (existingGroup.exists) {
            failed.push(`${toname}（已存在活跃微信群：${existingGroup.groupId}，主题：${existingGroup.topic}）`);
            continue;
        }
    }

    if (failed.length > 0) {
        seal.replyToSender(ctx, msg, `⚠️ 无法创建微信群，以下对象不符合条件：\n- ${failed.join("\n- ")}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 🆕 检查多人群中任意两人之间是否已有活跃群
    if (names.length > 1) {
        const allParticipants = [sendname, ...names];
        for (let i = 0; i < allParticipants.length; i++) {
            for (let j = i + 1; j < allParticipants.length; j++) {
                const user1 = allParticipants[i];
                const user2 = allParticipants[j];
                const existingGroup = checkWechatBetweenUsers(platform, user1, user2);
                if (existingGroup.exists) {
                    seal.replyToSender(ctx, msg, 
                        `⚠️ 无法创建多人微信群\n` +
                        `${user1} 和 ${user2} 之间已存在活跃微信群\n` +
                        `群号：${existingGroup.groupId}\n` +
                        `主题：${existingGroup.topic}\n\n` +
                        `💡 温馨提示：每个微信关系只能有一个活跃群`
                    );
                    return seal.ext.newCmdExecuteResult(true);
                }
            }
        }
    }

    // 获取所有参与者
    const allParticipants = [sendname, ...names];
    
    // 检查是否有可用群号（使用微信专用的标记）
    const groupList = JSON.parse(ext.storageGet("group") || "[]");
    const available = groupList.filter(g => !g.endsWith("_占用") && !g.endsWith("_微信占用"));
    
    if (available.length === 0) {
        seal.replyToSender(ctx, msg, "⚠️ 暂无可用群号，请管理员先添加备用群");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 随机选择一个群号
    const gid = available[Math.floor(Math.random() * available.length)];
    groupList.splice(groupList.indexOf(gid), 1);
    groupList.push(gid + "_微信占用");
    ext.storageSet("group", JSON.stringify(groupList));

    // 创建微信群记录
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    if (!wechatGroups[platform]) wechatGroups[platform] = {};
    
    const now = new Date();
    const created_at = now.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
    
    wechatGroups[platform][gid] = {
        id: gid,
        creator: sendname,
        creator_id: uid,
        topic: topic || "",
        participants: allParticipants,
        status: "active",
        created_at: created_at,
        created_timestamp: now.getTime()
    };
    
    ext.storageSet("wechat_groups", JSON.stringify(wechatGroups));

    // 通知所有参与者
    const groupNotice = `💬 微信群创建成功\n\n` +
                       `📱 群号：${gid}\n` +
                       `👤 创建者：${sendname}\n` +
                       `📝 主题：${topic || "(无主题)"}\n` +
                       `👥 成员：${allParticipants.join("、")}\n\n` +
                       `💡 温馨提示：\n` +
                       `• 这是一个长期群聊，没有时间限制\n` +
                       `• 每个微信关系只能有一个活跃群\n` +
                       `• 只有管理员可以结束微信群`;
    
    // 在群内发布公告
    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${gid}`;
    groupMsg.sender = {};
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    
    seal.replyToSender(groupCtx, groupMsg, groupNotice);
    
    // 设置群名（可选）
    try {
        setGroupName(groupCtx, groupMsg, gid, `微信${topic ? ":" + topic : ""}`);
    } catch (e) {
        console.log("设置群名失败，但不影响功能使用:", e);
    }

    // 通知每个参与者
    for (let participant of allParticipants) {
        const participantInfo = a_private_group[platform][participant];
        if (participantInfo) {
            const participantUid = participantInfo[0];
            const participantGid = participantInfo[1];
            
            if (participantUid && participantGid) {
                const notifyMsg = seal.newMessage();
                notifyMsg.messageType = "group";
                notifyMsg.sender = {};
                notifyMsg.sender.userId = `${platform}:${participantUid}`;
                notifyMsg.groupId = `${platform}-Group:${participantGid}`;
                const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
                
                const personalNotice = `💬 你已被加入微信群\n` +
                                     `📱 群号：${gid}\n` +
                                     `👤 创建者：${sendname}\n` +
                                     `📝 主题：${topic || "(无主题)"}\n` +
                                     `👥 成员：${allParticipants.join("、")}\n\n` +
                                     `💡 温馨提示：\n` +
                                     `• 这是一个长期群聊，没有时间限制\n` +
                                     `• 每个微信关系只能有一个活跃群\n` +
                                     `• 只有管理员可以结束微信群`;
                
                seal.replyToSender(notifyCtx, notifyMsg, personalNotice);
            }
        }
    }

    seal.replyToSender(ctx, msg, 
        `✅ 微信群创建成功！\n` +
        `📱 群号：${gid}\n` +
        `📝 主题：${topic || "(无主题)"}\n` +
        `👥 成员：${allParticipants.join("、")}\n\n` +
        `💡 温馨提示：每个微信关系只能有一个活跃群`
    );
    
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["微信"] = cmd_wechat;

// 🔧 结束微信群指令（只有管理员可以操作）
let cmd_end_wechat = seal.ext.newCmdItemInfo();
cmd_end_wechat.name = "结束微信";
cmd_end_wechat.help = "。结束微信 - 在当前微信群内使用，只有管理员可以结束该微信群";
cmd_end_wechat.solve = (ctx, msg) => {
    // 🆕 只有管理员可以操作
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 只有管理员可以结束微信群");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const gid = msg.groupId.replace(`${platform}-Group:`, "");
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    
    // 检查是否为微信群
    const groupList = JSON.parse(ext.storageGet("group") || "[]");
    if (!groupList.includes(gid + "_微信占用")) {
        seal.replyToSender(ctx, msg, "⚠️ 当前群不是微信群，无法使用此指令");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取微信群信息
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const groupInfo = wechatGroups[platform]?.[gid];
    
    if (!groupInfo) {
        seal.replyToSender(ctx, msg, "⚠️ 微信群信息不存在或已失效");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 🆕 获取管理员角色名
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const userRole = Object.entries(a_private_group[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0] || "管理员";

    // 更新群状态
    groupInfo.status = "ended";
    groupInfo.ended_at = new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
    groupInfo.ended_by = userRole;
    
    wechatGroups[platform][gid] = groupInfo;
    ext.storageSet("wechat_groups", JSON.stringify(wechatGroups));

    // 释放群号
    const groupIndex = groupList.indexOf(gid + "_微信占用");
    if (groupIndex !== -1) {
        groupList.splice(groupIndex, 1);
        groupList.push(gid); // 放回备用群列表
        ext.storageSet("group", JSON.stringify(groupList));
    }

    // 群内公告
    const endNotice = `💬 微信群已结束\n\n` +
                     `📱 群号：${gid}\n` +
                     `📝 主题：${groupInfo.topic || "(无主题)"}\n` +
                     `⏰ 创建时间：${groupInfo.created_at}\n` +
                     `⏰ 结束时间：${groupInfo.ended_at}\n` +
                     `👤 结束者：${userRole}（管理员）\n` +
                     `👥 原成员：${groupInfo.participants.join("、")}\n\n` +
                     `✨ 感谢大家的参与！`;
    
    seal.replyToSender(ctx, msg, endNotice);

    // 通知所有原参与者
    const a_private_group_full = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    for (let participant of groupInfo.participants) {
        const participantInfo = a_private_group_full[platform]?.[participant];
        if (participantInfo) {
            const participantUid = participantInfo[0];
            const participantGid = participantInfo[1];
            
            if (participantUid && participantGid && participantGid !== gid) {
                const notifyMsg = seal.newMessage();
                notifyMsg.messageType = "group";
                notifyMsg.sender = {};
                notifyMsg.sender.userId = `${platform}:${participantUid}`;
                notifyMsg.groupId = `${platform}-Group:${participantGid}`;
                const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
                
                const personalNotice = `💬 微信群已结束通知\n` +
                                     `📱 群号：${gid}\n` +
                                     `📝 主题：${groupInfo.topic || "(无主题)"}\n` +
                                     `👤 结束者：${userRole}（管理员）\n` +
                                     `⏰ 结束时间：${groupInfo.ended_at}\n` +
                                     `✨ 该群已释放为备用群\n\n` +
                                     `💡 现在可以重新创建微信关系群`;
                
                seal.replyToSender(notifyCtx, notifyMsg, personalNotice);
            }
        }
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束微信"] = cmd_end_wechat;

// 🔧 查看所有微信群（管理员专用）- 合并转发版
let cmd_view_all_wechat = seal.ext.newCmdItemInfo();
cmd_view_all_wechat.name = "查看微信群";
cmd_view_all_wechat.help = "。查看微信群 - 管理员查看所有微信群（合并转发）";
cmd_view_all_wechat.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};

    if (Object.keys(platformGroups).length === 0) {
        seal.replyToSender(ctx, msg, "📭 当前平台没有任何微信群");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 准备合并转发节点
    const nodes = [];

    // 页眉节点
    nodes.push({
        type: "node",
        data: {
            name: "群档案",
            uin: "10001", // 固定档案员QQ
            content: `📋 当前平台共有 ${Object.keys(platformGroups).length} 个微信群`
        }
    });

    // 活跃群节点
    const activeGroups = Object.values(platformGroups).filter(g => g.status === "active");
    if (activeGroups.length > 0) {
        let activeContent = "✅ 活跃微信群：\n";
        activeGroups.forEach((group, index) => {
            activeContent += `${index + 1}. 群号：${group.id}\n`;
            activeContent += `   主题：${group.topic || "(无主题)"}\n`;
            activeContent += `   创建者：${group.creator}\n`;
            activeContent += `   创建时间：${group.created_at}\n`;
            activeContent += `   成员：${group.participants.join("、")}\n`;
            if (group.participants.length === 2) {
                activeContent += `   关系：${group.participants[0]} ↔ ${group.participants[1]}\n`;
            }
            activeContent += `\n`;
        });
        nodes.push({
            type: "node",
            data: {
                name: "活跃群",
                uin: msg.sender.userId, // 使用管理员自己的QQ显示头像
                content: activeContent
            }
        });
    }

    // 已结束群节点
    const endedGroups = Object.values(platformGroups).filter(g => g.status === "ended");
    if (endedGroups.length > 0) {
        let endedContent = "❌ 已结束微信群：\n";
        endedGroups.forEach((group, index) => {
            endedContent += `${index + 1}. 群号：${group.id}\n`;
            endedContent += `   主题：${group.topic || "(无主题)"}\n`;
            endedContent += `   创建者：${group.creator}\n`;
            endedContent += `   创建时间：${group.created_at}\n`;
            endedContent += `   结束时间：${group.ended_at}\n`;
            endedContent += `   结束者：${group.ended_by || "未知"}\n`;
            endedContent += `   原成员：${group.participants.join("、")}\n`;
            endedContent += `\n`;
        });
        nodes.push({
            type: "node",
            data: {
                name: "已结束群",
                uin: msg.sender.userId,
                content: endedContent
            }
        });
    }

    // 统计信息节点
    const uniqueRelations = new Set();
    activeGroups.forEach(group => {
        if (group.participants.length === 2) {
            const sorted = group.participants.sort();
            uniqueRelations.add(`${sorted[0]}↔${sorted[1]}`);
        }
    });
    const statsContent = `📊 统计信息：\n• 活跃微信群：${activeGroups.length} 个\n• 已结束微信群：${endedGroups.length} 个\n• 唯一微信关系：${uniqueRelations.size} 对`;
    nodes.push({
        type: "node",
        data: {
            name: "统计",
            uin: msg.sender.userId,
            content: statsContent
        }
    });

    // 帮助节点
    nodes.push({
        type: "node",
        data: {
            name: "帮助",
            uin: msg.sender.userId,
            content: "💡 管理指令：\n- 在微信群内使用「。结束微信」可结束该群（需管理员权限）"
        }
    });

    // 发送合并转发到当前群
    const currentGroupId = msg.groupId;
    const groupIdNum = parseInt(currentGroupId.replace(/[^\d]/g, ""), 10);
    ws({
        action: "send_group_forward_msg",
        params: {
            group_id: groupIdNum,
            messages: nodes
        }
    }, ctx, msg, "");

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看微信群"] = cmd_view_all_wechat;

// 🔧 清理已结束的微信群记录（管理员专用）
let cmd_cleanup_wechat = seal.ext.newCmdItemInfo();
cmd_cleanup_wechat.name = "清理微信群记录";
cmd_cleanup_wechat.help = "。清理微信群记录 - 清理已结束的微信群记录";
cmd_cleanup_wechat.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};

    // 只保留活跃群，移除已结束群
    const activeGroups = {};
    let removedCount = 0;
    
    for (const [groupId, groupInfo] of Object.entries(platformGroups)) {
        if (groupInfo.status === "active") {
            activeGroups[groupId] = groupInfo;
        } else {
            removedCount++;
        }
    }

    wechatGroups[platform] = activeGroups;
    ext.storageSet("wechat_groups", JSON.stringify(wechatGroups));

    seal.replyToSender(ctx, msg, `✅ 已清理微信群记录，移除了 ${removedCount} 个已结束的微信群记录`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清理微信群记录"] = cmd_cleanup_wechat;

// 🔧 强制解除微信关系（管理员专用）
let cmd_force_break_wechat = seal.ext.newCmdItemInfo();
cmd_force_break_wechat.name = "强制解除微信关系";
cmd_force_break_wechat.help = "。强制解除微信关系 角色名1 角色名2 - 强制解除两人之间的微信关系";
cmd_force_break_wechat.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const role1 = cmdArgs.getArgN(1);
    const role2 = cmdArgs.getArgN(2);

    if (!role1 || !role2) {
        seal.replyToSender(ctx, msg, "请指定两个角色名：。强制解除微信关系 角色名1 角色名2");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (role1 === role2) {
        seal.replyToSender(ctx, msg, "⚠️ 不能指定相同的角色");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    // 检查角色是否存在
    if (!a_private_group[platform]?.[role1] || !a_private_group[platform]?.[role2]) {
        seal.replyToSender(ctx, msg, "⚠️ 指定的角色不存在，请检查角色名");
        return seal.ext.newCmdExecuteResult(true);
    }

    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};
    
    let foundGroup = null;
    let groupId = null;
    
    // 查找两人之间的活跃微信群
    for (const [gid, group] of Object.entries(platformGroups)) {
        if (group.status === "active" && 
            group.participants.includes(role1) && 
            group.participants.includes(role2)) {
            foundGroup = group;
            groupId = gid;
            break;
        }
    }

    if (!foundGroup) {
        seal.replyToSender(ctx, msg, `✅ ${role1} 和 ${role2} 之间没有活跃的微信关系`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 结束该微信群
    foundGroup.status = "ended";
    foundGroup.ended_at = new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
    foundGroup.ended_by = "管理员（强制解除）";
    
    platformGroups[groupId] = foundGroup;
    wechatGroups[platform] = platformGroups;
    ext.storageSet("wechat_groups", JSON.stringify(wechatGroups));

    // 释放群号
    const groupList = JSON.parse(ext.storageGet("group") || "[]");
    const groupIndex = groupList.indexOf(groupId + "_微信占用");
    if (groupIndex !== -1) {
        groupList.splice(groupIndex, 1);
        groupList.push(groupId); // 放回备用群列表
        ext.storageSet("group", JSON.stringify(groupList));
    }

    // 通知参与者
    const participants = foundGroup.participants;
    for (let participant of participants) {
        const participantInfo = a_private_group[platform]?.[participant];
        if (participantInfo) {
            const participantUid = participantInfo[0];
            const participantGid = participantInfo[1];
            
            if (participantUid && participantGid) {
                const notifyMsg = seal.newMessage();
                notifyMsg.messageType = "group";
                notifyMsg.sender = {};
                notifyMsg.sender.userId = `${platform}:${participantUid}`;
                notifyMsg.groupId = `${platform}-Group:${participantGid}`;
                const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
                
                const personalNotice = `💬 微信关系强制解除通知\n` +
                                     `📱 群号：${groupId}\n` +
                                     `📝 主题：${foundGroup.topic || "(无主题)"}\n` +
                                     `👥 关系：${role1} ↔ ${role2}\n` +
                                     `👤 操作者：管理员\n` +
                                     `⏰ 操作时间：${foundGroup.ended_at}\n\n` +
                                     `✨ 该微信关系已解除，现在可以重新创建微信关系群`;
                
                seal.replyToSender(notifyCtx, notifyMsg, personalNotice);
            }
        }
    }

    seal.replyToSender(ctx, msg, 
        `✅ 已强制解除 ${role1} 和 ${role2} 的微信关系\n` +
        `📱 群号：${groupId}\n` +
        `📝 主题：${foundGroup.topic || "(无主题)"}\n` +
        `👥 已通知所有参与者：${participants.join("、")}`
    );
    
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["强制解除微信关系"] = cmd_force_break_wechat;

// ========================
// 🗨️ 秘密论坛系统 (WS公告集成版)
// ========================

// --- 📋 系统配置 ---
seal.ext.registerIntConfig(ext, "forumMaxLength", 500, "论坛内容最大长度", "发帖和回复的最大字符数");
// 💡 新增配置：用于存放接收公告的群号
seal.ext.registerStringConfig(ext, "forumAnnounceGroupId", "", "论坛公告同步的目标群号");

// --- 🔧 核心辅助函数 ---
const getForumPosts = () => JSON.parse(ext.storageGet("forum_posts") || "[]");
const saveForumPosts = (posts) => ext.storageSet("forum_posts", JSON.stringify(posts));
/**
 * 💡 改造后的公告函数：
 * 放弃 WS 手动构造，直接调用你已有的 sendTextToGroup
 */
function sendToAnnounceGroup(ctx, platform, text) {
    // 统一从 storage 获取你原本定义的公告群号
    const announceGid = JSON.parse(ext.storageGet("song_group_id") || "null");
    
    if (announceGid) {
        // 调用你现成的发送函数
        sendTextToGroup(platform, announceGid, text);
    } else {
        console.log("[论坛系统] 尚未配置 adminAnnounceGroupId，跳过公告。");
    }
}

function sendForumForward(ctx, msg, nodes) {
    const gid = msg.groupId.replace(/[^\d]/g, "");
    ws({
        "action": "send_group_forward_msg",
        "params": {
            "group_id": parseInt(gid, 10),
            "messages": nodes
        }
    }, ctx, msg, "");
}

function findPostById(postId) {
    const posts = getForumPosts();
    const index = posts.findIndex(p => p.id === postId && p.status === "active");
    return index !== -1 ? { post: posts[index], index: index } : null;
}


// ========================
// 📝 指令：发帖 (智能署名版)
// ========================
let cmd_post_forum = seal.ext.newCmdItemInfo();
cmd_post_forum.name = "发帖";
cmd_post_forum.help = ".发帖 (署名) [内容] —— 发表一篇新帖子";
cmd_post_forum.solve = (ctx, msg, cmdArgs) => {
    const roleName = RelationshipUtils.getRoleName(ctx, msg, msg.platform) || ctx.player.name;
    let author, content;

    if (cmdArgs.args.length > 1) {
        author = cmdArgs.getArgN(1);
        content = msg.message.replace(/^[。.]发帖\s+\S+\s*/, "").trim();
    } else {
        author = roleName;
        content = cmdArgs.getArgN(1) || "";
    }

    if (!content) {
        seal.replyToSender(ctx, msg, "💡 请输入帖子内容！\n格式：.发帖 内容 或 .发帖 署名 内容");
        return seal.ext.newCmdExecuteResult(true);
    }

    const posts = getForumPosts();
    const postId = Math.random().toString(36).substring(2, 7).toUpperCase();
    
    posts.push({
        id: postId, author, content, timestamp: new Date().toLocaleString(),
        replies: [], likes: [], dislikes: [], status: "active"
    });

    saveForumPosts(posts);
    seal.replyToSender(ctx, msg, `✅ 帖子 [${postId}] 发布成功！`);
    sendToAnnounceGroup(ctx, msg.platform, `📢 【论坛新帖】\n🆔 ${postId}\n👤 ${author}\n📜 ${content}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发帖"] = cmd_post_forum;

// ========================
// 💬 指令：回复帖子 (修正版)
// ========================
let cmd_reply_post = seal.ext.newCmdItemInfo();
cmd_reply_post.name = "回复帖子";
cmd_reply_post.help = ".回复帖子 [贴号] (署名) [内容] —— 回复现有帖子";
cmd_reply_post.solve = (ctx, msg, cmdArgs) => {
    const postId = cmdArgs.getArgN(1);
    const roleName = RelationshipUtils.getRoleName(ctx, msg, msg.platform) || ctx.player.name;
    let author, content;

    if (cmdArgs.args.length > 2) {
        author = cmdArgs.getArgN(2);
        content = msg.message.replace(/^[。.]回复帖子\s+\S+\s+\S+\s*/, "").trim();
    } else {
        author = roleName;
        content = msg.message.replace(/^[。.]回复帖子\s+\S+\s*/, "").trim();
    }

    if (!postId || !content) {
        seal.replyToSender(ctx, msg, "❌ 格式错误！\n格式：.回复帖子 [贴号] 内容");
        return seal.ext.newCmdExecuteResult(true);
    }

    const result = findPostById(postId);
    if (!result) {
        seal.replyToSender(ctx, msg, `❌ 找不到帖子 [${postId}]`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const posts = getForumPosts();
    // 💡 回复不分配ID，直接追加到 replies 数组
    posts[result.index].replies.push({ author, content, timestamp: new Date().toLocaleString() });
    saveForumPosts(posts);

    seal.replyToSender(ctx, msg, `✅ 已回复到帖子 [${postId}]`);
    sendToAnnounceGroup(ctx, msg.platform, `💬 【论坛回复】\n📌 贴号：${postId}\n👤 ${author}\n📝 ${content}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["回复帖子"] = cmd_reply_post;

// ========================
// 👍 指令：点赞 / 点踩
// ========================
function handleVote(ctx, msg, cmdArgs, isLike) {
    const postId = cmdArgs.getArgN(1);
    const author = cmdArgs.getArgN(2);
    if (!postId || !author) return seal.ext.newCmdExecuteResult(true);

    const result = findPostById(postId);
    if (!result) return seal.ext.newCmdExecuteResult(true);

    const posts = getForumPosts();
    const post = posts[result.index];
    
    const myList = isLike ? post.likes : post.dislikes;
    const otherList = isLike ? post.dislikes : post.likes;

    if (myList.includes(author)) {
        seal.replyToSender(ctx, msg, "⚠️ 你已经表过态啦～");
        return seal.ext.newCmdExecuteResult(true);
    }

    const idx = otherList.indexOf(author);
    if (idx !== -1) otherList.splice(idx, 1);

    myList.push(author);
    saveForumPosts(posts);

    const typeStr = isLike ? "点赞" : "点踩";
    seal.replyToSender(ctx, msg, `✅ ${typeStr}成功！`);
    
    // 同步公告 (调用改造后的函数)
    sendToAnnounceGroup(ctx, msg.platform, `${isLike ? '❤️' : '👎'} 【论坛动态】\n👤 ${author} 对帖子 [${postId}] 进行了${typeStr}\n🔥 赞：${post.likes.length} | ❄️ 踩：${post.dislikes.length}`);
    return seal.ext.newCmdExecuteResult(true);
}

let cmd_like = seal.ext.newCmdItemInfo();
cmd_like.name = "点赞";
cmd_like.solve = (ctx, msg, cmdArgs) => {
handleVote(ctx, msg, cmdArgs, true);
}
ext.cmdMap["点赞"] = cmd_like;

let cmd_dislike = seal.ext.newCmdItemInfo();
cmd_dislike.name = "点踩";
cmd_dislike.solve = (ctx, msg, cmdArgs) => {
handleVote(ctx, msg, cmdArgs, false);
}
ext.cmdMap["点踩"] = cmd_dislike;

// ========================
// 📋 指令：查看帖子
// ========================
let cmd_view_posts = seal.ext.newCmdItemInfo();
cmd_view_posts.name = "查看帖子";
cmd_view_posts.solve = (ctx, msg, cmdArgs) => {
    const postId = cmdArgs.getArgN(1);
    let allPosts = getForumPosts().filter(p => p.status === "active");

    if (allPosts.length === 0) {
        seal.replyToSender(ctx, msg, "📭 论坛空空如也");
        return seal.ext.newCmdExecuteResult(true);
    }

    const nodes = [];
    if (postId) {
        const post = allPosts.find(p => p.id === postId);
        if (!post) return seal.ext.newCmdExecuteResult(true);

        nodes.push({
            type: "node", data: {
                name: `${post.author} (楼主)`, uin: "10001",
                content: `📜 【正文】\n\n${post.content}\n\n${"━".repeat(12)}\n👍 ${post.likes.length} | 👎 ${post.dislikes.length}`
            }
        });

        post.replies.forEach((r, i) => {
            nodes.push({ type: "node", data: { name: `${r.author} (L${i + 1})`, uin: "2852199344", content: r.content } });
        });
        sendForumForward(ctx, msg, nodes);
    } else {
        allPosts.sort((a, b) => (b.replies.length * 2 + b.likes.length) - (a.replies.length * 2 + a.likes.length));

        nodes.push({ type: "node", data: { name: "论坛热榜", uin: "2852199344", content: "🔥 当前最受关注的 10 篇帖子" } });

        allPosts.slice(0, 10).forEach(p => {
            nodes.push({
                type: "node", data: {
                    name: `ID: ${p.id} | ${p.author}`, uin: "10001",
                    content: `📜 ${p.content.substring(0, 30)}...\n💬 ${p.replies.length} | 👍 ${p.likes.length}`
                }
            });
        });
        sendForumForward(ctx, msg, nodes);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看帖子"] = cmd_view_posts;

// ========================
// 🗑️ 管理：删除帖子
// ========================
let cmd_delete_post = seal.ext.newCmdItemInfo();
cmd_delete_post.name = "删除帖子";
cmd_delete_post.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该权限仅限管理员使用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const postId = cmdArgs.getArgN(1);
    const result = findPostById(postId);

    if (result) {
        const posts = getForumPosts();
        posts[result.index].status = "deleted";
        saveForumPosts(posts);

        seal.replyToSender(ctx, msg, `🗑️ 帖子 [${postId}] 已成功下架。`);
        
        // 同步通知公告群 (WS)
        sendToAnnounceGroup(ctx, msg.platform, `🛡️ 【论坛管理】\n管理员删除了帖子：[${postId}]\n理由：违反社区规范`);
    } else {
        seal.replyToSender(ctx, msg, "❌ 找不到该帖子或已被删除。");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除帖子"] = cmd_delete_post;

// === 👥 群成员查看功能 (精简版) ===

const solveGroupMembers = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足");

    // 1. 提取群号：优先取参数，无参数则取当前群
    let inputId = cmdArgs.getArgN(1) || ctx.group.groupId;
    let groupIdNum = inputId.toString().replace(/[^\d]/g, "");

    if (!groupIdNum) return seal.replyToSender(ctx, msg, "⚠️ 无法识别群号");

    // 2. 检查触发条件
    const condition = seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件");
    if (parseInt(seal.format(ctx, `{${condition}}`)) !== 1) {
        return seal.replyToSender(ctx, msg, "当前不满足使用条件");
    }

    // 3. 发送请求
    return ws({
        "action": "get_group_member_list",
        "params": { "group_id": parseInt(groupIdNum, 10) }
    }, ctx, msg, "🔍 正在请求群成员列表...");
};

// 注册两个指令到同一个 solve 函数
let cmd_members = seal.ext.newCmdItemInfo();
cmd_members.name = "查看群成员";
cmd_members.solve = solveGroupMembers;
ext.cmdMap[cmd_members.name] = cmd_members;

let cmd_members_spec = seal.ext.newCmdItemInfo();
cmd_members_spec.name = "查看指定群成员";
cmd_members_spec.solve = solveGroupMembers;
ext.cmdMap[cmd_members_spec.name] = cmd_members_spec;

// === 🛡️ 指令：。审查私密群 ===
let cmd_audit_full = seal.ext.newCmdItemInfo();
cmd_audit_full.name = "审查私密群";
cmd_audit_full.help = "直接输出 NPC 缺失或玩家重合的结果。";

cmd_audit_full.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足");

    const platform = msg.platform;
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");
    
    const playerList = Object.entries(a_private_group[platform] || {})
        .filter(([name]) => !npcList.includes(name));

    if (playerList.length === 0) return seal.replyToSender(ctx, msg, "📭 无玩家记录");

    seal.replyToSender(ctx, msg, `🔍 正在核对 ${playerList.length} 个私密群...`);

    // 循环发起请求
    playerList.forEach(([ownerName, data]) => {
        const gid = data[1];

        // 核心技巧：通过延迟或存储位标记当前处理的群
        // 这里的 ws 是你原本的 function ws
        setTimeout(() => {
            // 设置一个临时标记，让 handleMemberListResponse 知道这是在审查谁
            ext.storageSet("temp_audit_owner", ownerName);
            
            ws({
                "action": "get_group_member_list",
                "params": { "group_id": parseInt(gid, 10) }
            }, ctx, msg, null); 
        }, 100); 
    });

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["审查私密群"] = cmd_audit_full;

// 注册开关与概率
seal.ext.registerBoolConfig(ext, "开启心动信曝光", false, "开启后，信件有概率同步发送到指定的公告群");
seal.ext.registerIntConfig(ext, "曝光概率", 10, "每封信件被公开的概率 (0-100)");

// === 核心功能：发送心动信 ===
let cmd_send_lovemail = seal.ext.newCmdItemInfo();
cmd_send_lovemail.name = "发送心动信";
cmd_send_lovemail.help = "。发送心动信\n【署名】（选填）\n【发送对象】角色名\n【内容】想说的话（支持空行）";

cmd_send_lovemail.solve = (ctx, msg, cmdArgs) => {
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_lovemail === false) {
        seal.replyToSender(ctx, msg, "💌 心动信箱已关闭，暂不可投稿");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // --- 🕊️ 天使的身份核验 ---
    // 检查发信人是否已经绑定了角色
    const senderRoleName = Object.entries(a_private_group[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0];
    
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 远方的旅人，寄信前请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const raw = msg.message.trim();

    // --- 优化解析逻辑：使用正则提取 ---
    const getTag = (tag) => {
        const regex = new RegExp(`【${tag}】([\\s\\S]*?)(?=【|$)`, "i");
        const match = raw.match(regex);
        return match ? match[1].trim() : null;
    };

    const signature = getTag("署名") || "匿名";
    const receiver = getTag("发送对象") || getTag("收件人");
    let content = getTag("内容") || "";

    // 格式检查
    if (!receiver) {
        let helpMsg = `⚠️ 格式错误！请指定发送对象。\n`;
        helpMsg += `\n标准格式：\n`;
        helpMsg += `。发送心动信\n`;
        helpMsg += `【发送对象】角色名\n`;
        helpMsg += `【内容】想说的话\n`;
        helpMsg += `【署名】自定义昵称（选填，不填默认使用群名片）\n`;
        
        seal.replyToSender(ctx, msg, helpMsg);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 验证收信人是否存在
    if (!a_private_group[platform] || !a_private_group[platform][receiver]) {
        seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${receiver}」的投递地址，请确认名字是否正确。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 限制检查
    const MAX_PER_DAY = parseInt(ext.storageGet("lovemail_daily_limit") || "2");
    const mailKey = "lovemail_pool";
    let records = JSON.parse(ext.storageGet(mailKey) || "[]");
    const today = new Date().toLocaleDateString();
    
    const myTodayCount = records.filter(r => r.uid === uid && r.date === today).length;
    if (myTodayCount >= MAX_PER_DAY) {
        seal.replyToSender(ctx, msg, `📪 今日投稿次数已达上限（${MAX_PER_DAY} 封），请明天再来。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 保存信件 (增加 timestamp 用于精准撤回)
    records.push({
        uid,
        receiver,
        content,
        signature,
        date: today,
        timestamp: Date.now() 
    });

    ext.storageSet(mailKey, JSON.stringify(records));

    // 回复用户
    let reply = `💌 心动信已成功投递至「${receiver}」的信箱！\n`;
    reply += `📝 署名：${signature}\n`;
    reply += `✨ 提示：管理员统一送出前，你仍可以使用「。撤回我的心动信件」取消本次投递。`;
    
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发送心动信"] = cmd_send_lovemail;

function performLoveMailDelivery(ctx, msg) {
    const platform = msg ? msg.platform : "QQ";
    const mailKey = "lovemail_pool";
    const records = JSON.parse(ext.storageGet(mailKey) || "[]");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // --- 1. 严格读取配置 ---
    const isPublicEnabled = seal.ext.getBoolConfig(ext, "开启心动信曝光");
    const publicChance = seal.ext.getIntConfig(ext, "曝光概率");
    
    // 兼容性处理公告群号：先取存储，没有则取配置
    let announceGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
    if (!announceGroupId || announceGroupId === "null") {
        announceGroupId = seal.ext.getStringConfig(ext, "曝光公告群号"); 
    }

    if (records.length === 0) return { success: 0, fail: 0, publicCount: 0, empty: true };

    console.log(`[心动信箱] 开始派送 ${records.length} 封信件，曝光开关: ${isPublicEnabled}, 概率: ${publicChance}%`);

    const mailBox = {};
    records.forEach(r => {
        if (!mailBox[r.receiver]) mailBox[r.receiver] = [];
        mailBox[r.receiver].push(r);
    });

    let success = 0;
    let fail = 0;
    let publicCount = 0;
    const eps = seal.getEndPoints();
    const publicNodes = []; 

    for (const receiver in mailBox) {
        const mails = mailBox[receiver];
        const addr = a_private_group[platform]?.[receiver];
        
        if (addr) {
            const [_, groupId] = addr;
            const targetGroup = `${platform}-Group:${groupId.replace(/[^\d]/g, "")}`;
            const deliverMsg = seal.newMessage();
            deliverMsg.messageType = "group";
            deliverMsg.groupId = targetGroup;
            
            // 确保自动任务时也有可用的 deliverCtx
            const deliverCtx = (ctx && ctx.endPoint) ? ctx : seal.createTempCtx(eps[0], deliverMsg);

            mails.forEach((mail, idx) => {
                // 正常投递
                let text = `💌 亲爱的 ${receiver}，你收到一封心动信件！\n`;
                text += `（这是你今日收到的第 ${idx + 1} / ${mails.length} 封）\n`;
                text += `┈┈┈┈┈┈┈┈┈┈┈┈\n「 ${mail.content} 」\n┈┈┈┈┈┈┈┈┈┈┈┈\n📝 署名：${mail.signature}`;
                seal.replyToSender(deliverCtx, deliverMsg, text);
                success++;

                // --- 2. 曝光逻辑优化 ---
                if (isPublicEnabled && announceGroupId && announceGroupId !== "null") {
                    const randomNum = Math.floor(Math.random() * 100) + 1;
                    // 调试日志：如果一直不掉落，可以临时取消下面这行的注释看看随机数
                    // console.log(`[曝光检查] 随机数: ${randomNum}, 目标: <= ${publicChance}`);
                    
                    if (randomNum <= publicChance) {
                        publicCount++;
                        publicNodes.push({
                            type: "node",
                            data: {
                                name: "天堂里飘落的信笺",
                                uin: "2852199344",
                                content: `💌 公开的信件：\n来自「${mail.signature}」→「${receiver}」\n内容：「${mail.content}」\n\n（幸运值：${randomNum}，触发曝光）`
                            }
                        });
                    }
                }
            });
        } else {
            fail += mails.length;
        }
    }

    // --- 3. 发送逻辑优化 ---
    if (publicNodes.length > 0 && announceGroupId && announceGroupId !== "null") {
        const targetGidRaw = announceGroupId.toString().replace(/[^\d]/g, "");
        console.log(`[心动信箱] 触发曝光！共有 ${publicCount} 封信件将发送至群: ${targetGidRaw}`);

        publicNodes.unshift({
            type: "node",
            data: {
                name: "心动天使",
                uin: "2852199344",
                content: `✨ 哎呀，有 ${publicNodes.length} 份心意在飞往信箱的途中，不小心飘落到了公告区...`
            }
        });

        const pubMsg = seal.newMessage();
        pubMsg.messageType = "group";
        pubMsg.groupId = `${platform}-Group:${targetGidRaw}`;
        const pubCtx = seal.createTempCtx(eps[0], pubMsg);

        ws({
            "action": "send_group_forward_msg",
            "params": {
                "group_id": parseInt(targetGidRaw, 10),
                "messages": publicNodes
            }
        }, pubCtx, pubMsg, "");
    } else if (isPublicEnabled) {
        console.log(`[心动信箱] 本次未触发曝光。待曝光数: ${publicNodes.length}, 公告群: ${announceGroupId}`);
    }

    ext.storageSet(mailKey, "[]");
    return { success, fail, publicCount, empty: false };
}

let cmd_deliver_lovemail = seal.ext.newCmdItemInfo();
cmd_deliver_lovemail.name = "统一送心动信";
cmd_deliver_lovemail.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足。");

    const result = performLoveMailDelivery(ctx, msg);
    
    if (result.empty) {
        seal.replyToSender(ctx, msg, "📭 信箱空空如也。");
    } else {
        seal.replyToSender(ctx, msg, `📬 手动投递完成！成功 ${result.success} 封，失败 ${result.fail} 封。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["统一送心动信"] = cmd_deliver_lovemail;

// === 管理员功能：心动信箱巡检 (守护天使版) ===
let cmd_stat_lovemail = seal.ext.newCmdItemInfo();
cmd_stat_lovemail.name = "信箱统计";
cmd_stat_lovemail.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "✨ 抱歉，这里只有邮局守护者才能进入哦。");

    const mailKey = "lovemail_pool";
    const records = JSON.parse(ext.storageGet(mailKey) || "[]");

    if (records.length === 0) {
        seal.replyToSender(ctx, msg, "🕊️ 此时的邮局静悄悄的，还没有待投递的心意。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 1. 整理飘落的心意
    const mailBox = {};
    records.forEach(r => {
        if (!mailBox[r.receiver]) mailBox[r.receiver] = [];
        mailBox[r.receiver].push(r);
    });

    const nodes = [];
    // 扉页节点
    nodes.push({
        type: "node",
        data: {
            name: "心动邮局·巡检手记",
            uin: "2852199344",
            content: `🌸 此时此刻，共有 ${records.length} 份心意正在等待传递\n🕰️ 巡检时间：${new Date().toLocaleString()}\n愿每一份温柔都能准时抵达。`
        }
    });

    // --- 核心逻辑：优雅地拆分超长心意 ---
    const MAX_CHAR_PER_NODE = 1200; // 稍微收紧一点，让排版在手机上更透气

    Object.entries(mailBox).forEach(([receiver, mails]) => {
        let currentNodeText = `👤 致：${receiver}\n📬 待收件数：${mails.length} 封\n━━━━━━━━━━━━━━━\n`;
        let part = 1;

        mails.forEach((m, index) => {
            let letterText = `【信件序号：${index + 1}】\n📝 署名：${m.signature}\n📜 内容：${m.content}\n`;
            if (index < mails.length - 1) letterText += `┈┈┈┈┈┈┈┈┈┈┈┈\n`;

            // 如果这一页纸写不下了
            if ((currentNodeText + letterText).length > MAX_CHAR_PER_NODE) {
                nodes.push({
                    type: "node",
                    data: {
                        name: `给 ${receiver} 的心意分册 (其之 ${part})`,
                        uin: "10001",
                        content: currentNodeText.trim()
                    }
                });
                // 开启新的一页
                currentNodeText = `👤 致：${receiver} (接前文)\n━━━━━━━━━━━━━━━\n` + letterText;
                part++;
            } else {
                currentNodeText += letterText;
            }
        });

        // 放入最后的余韵
        nodes.push({
            type: "node",
            data: {
                name: part === 1 ? `致 ${receiver} 的信` : `致 ${receiver} 的信 (终卷)`,
                uin: "10001",
                content: currentNodeText.trim()
            }
        });
    });

    // 3. 轻轻地包裹并寄送给管理员
    const MAX_NODES_PER_MSG = 90; 
    const targetGid = msg.groupId.replace(/[^\d]/g, "");

    for (let i = 0; i < nodes.length; i += MAX_NODES_PER_MSG) {
        const chunk = nodes.slice(i, i + MAX_NODES_PER_MSG);
        ws({
            "action": "send_group_forward_msg",
            "params": {
                "group_id": parseInt(targetGid, 10),
                "messages": chunk
            }
        }, ctx, msg, "");
    }

    // 4. 给管理员的温柔回执
    const reportMsg = `✅ 统计报表已封缄完毕\n📮 发现 ${Object.keys(mailBox).length} 位收件人的小小秘密\n✨ 巡检记录共计 ${nodes.length} 页，请您审阅。`;
    seal.replyToSender(ctx, msg, reportMsg);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["信箱统计"] = cmd_stat_lovemail;

// === 玩家功能：查看我的信件 ===
let cmd_view_mylovemails = seal.ext.newCmdItemInfo();
cmd_view_mylovemails.name = "查看我的心动信件";
cmd_view_mylovemails.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const records = JSON.parse(ext.storageGet("lovemail_pool") || "[]");
    const my = records.filter(r => r.uid === uid);

    if (!my.length) return seal.replyToSender(ctx, msg, "📭 你目前没有待投递的信件。");
    
    let res = "📄 你待投递的信件如下：\n";
    my.forEach((r, i) => res += `\n#${i + 1} | 接收者: ${r.receiver}\n内容: ${r.content}\n`);
    seal.replyToSender(ctx, msg, res);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看我的心动信件"] = cmd_view_mylovemails;

// === 玩家功能：撤回信件 ===
let cmd_revoke_lovemail = seal.ext.newCmdItemInfo();
cmd_revoke_lovemail.name = "撤回我的心动信件";
cmd_revoke_lovemail.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    let records = JSON.parse(ext.storageGet("lovemail_pool") || "[]");

    const my = records.filter(r => r.uid === uid);
    if (isNaN(idx) || idx < 0 || idx >= my.length) {
        return seal.replyToSender(ctx, msg, "⚠️ 请输入正确的序号，例如：。撤回我的心动信件 1");
    }

    const targetTimestamp = my[idx].timestamp;
    const finalRecords = records.filter(r => r.timestamp !== targetTimestamp);
    
    ext.storageSet("lovemail_pool", JSON.stringify(finalRecords));
    seal.replyToSender(ctx, msg, `✅ 已成功撤回发送给「${my[idx].receiver}」的信件。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤回我的心动信件"] = cmd_revoke_lovemail;


// === 🕒 心动信全自动化流程 (轮询稳定版) ===

let loveMailTimer = null; // 全局定时器句柄

// === 修改后的 🕒 心动信全自动化流程 ===

function registerLoveMailSystem() {
    if (loveMailTimer) {
        clearInterval(loveMailTimer);
        loveMailTimer = null;
    }

    let lastTriggerMinute = -1;

    loveMailTimer = setInterval(() => {
        // --- 核心修改：最优先检查功能开关 ---
        // 如果开关关闭，直接跳出，不执行后续任何逻辑（包括时间判断和提醒）
        if (!isLoveMailEnabled()) return;

        const now = new Date();
        const currentHour = now.getHours();
        const currentMinute = now.getMinutes();
        const currentTimeTotal = currentHour * 60 + currentMinute;

        if (currentMinute === lastTriggerMinute) return;

        // 获取设置的派送时间
        const deliveryTime = JSON.parse(ext.storageGet("lovemail_delivery_time") || "\"22:00\"");
        const timeParts = deliveryTime.split(':').map(Number);
        if (timeParts.length !== 2) return;
        const [targetH, targetM] = timeParts;
        const targetTimeTotal = targetH * 60 + targetM;

        const getOffsetTotal = (offset) => {
            let t = targetTimeTotal + offset;
            if (t < 0) t += 1440;
            return t % 1440;
        };

        // --- 逻辑检查 ---
        // 1. 正式派送时间
        if (currentTimeTotal === targetTimeTotal) {
            console.log("[心动信箱] 到达预定时间，执行正式派送...");
            
            // 构造一个简单的模拟 msg 对象，确保 platform 能够传递进去
            const mockMsg = { platform: "QQ" }; 
            performLoveMailDelivery(null, mockMsg);
            
            lastTriggerMinute = currentMinute;
        }
        // 2. 派送预告 (提前5分钟)
        else if (currentTimeTotal === getOffsetTotal(-5)) {
            const announceGid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
            if (announceGid) {
                sendTextToGroup("QQ", announceGid, `📬 邮差正在整理信箱，心动信件即将在 5 分钟后开始派送，请注意查收。`);
            }
            lastTriggerMinute = currentMinute;
        } 
        // 3. 截稿提醒 (提前10分钟)
        else if (currentTimeTotal === getOffsetTotal(-10)) {
            const platform = "QQ";
            const groups = JSON.parse(ext.storageGet("a_private_group") || "{}")[platform] || {};
            const targetGids = [...new Set(Object.values(groups).map(v => v[1]))];
            targetGids.forEach(gid => {
                sendTextToGroup(platform, gid, `⌛ 投递截止预告：\n心动信箱将于 10 分钟后截止收稿并开始派送，还没投递的小伙伴要抓紧咯～`);
            });
            lastTriggerMinute = currentMinute;
        }

    }, 30000); 

    console.log(`[心动信箱] 轮询系统已启动。当前设定派送时间：${JSON.parse(ext.storageGet("lovemail_delivery_time") || "\"22:00\"")}`);
}
function performLoveMailDelivery(ctx, msg) {
    const platform = msg ? msg.platform : "QQ";
    const mailKey = "lovemail_pool";
    const records = JSON.parse(ext.storageGet(mailKey) || "[]");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    const isPublicEnabled = seal.ext.getBoolConfig(ext, "开启心动信曝光");
    const publicChance = seal.ext.getIntConfig(ext, "曝光概率");
    const announceGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");

    if (records.length === 0) return { success: 0, fail: 0, publicCount: 0, empty: true };

    const mailBox = {};
    records.forEach(r => {
        if (!mailBox[r.receiver]) mailBox[r.receiver] = [];
        mailBox[r.receiver].push(r);
    });

    let success = 0;
    let fail = 0;
    let publicCount = 0;
    const eps = seal.getEndPoints();
    const publicNodes = []; 

    for (const receiver in mailBox) {
        const mails = mailBox[receiver];
        const addr = a_private_group[platform]?.[receiver];
        
        if (addr) {
            const [_, groupId] = addr;
            const targetGidRaw = groupId.replace(/[^\d]/g, "");
            const targetGroup = `${platform}-Group:${targetGidRaw}`;
            
            const deliverMsg = seal.newMessage();
            deliverMsg.messageType = "group";
            deliverMsg.groupId = targetGroup;
            const deliverCtx = (ctx && ctx.endPoint) ? ctx : seal.createTempCtx(eps[0], deliverMsg);

            // 🆕 构造属于该收件人的专属信箱包
            const personalNodes = [];
            personalNodes.push({
                type: "node",
                data: {
                    name: "心动邮局·派送员",
                    uin: "2852199344",
                    content: `💌 亲爱的 ${receiver}，你有一份包含 ${mails.length} 封信件的包裹待启封。`
                }
            });

            mails.forEach((mail, idx) => {
                // 1. 放入个人包裹
                personalNodes.push({
                    type: "node",
                    data: {
                        name: `第 ${idx + 1} 封信件`,
                        uin: "10001",
                        content: `「 ${mail.content} 」\n┈┈┈┈┈┈┈┈┈┈┈┈\n📝 署名：${mail.signature}`
                    }
                });
                success++;

                // 2. 判定曝光
                if (isPublicEnabled && announceGroupId && announceGroupId !== "null") {
                    const randomNum = Math.floor(Math.random() * 100) + 1;
                    if (randomNum <= publicChance) {
                        publicCount++;
                        publicNodes.push({
                            type: "node",
                            data: {
                                name: "飘落的信笺",
                                uin: "2852199344",
                                content: `📩 寄给「${receiver}」的心动信\n来自「${mail.signature}」\n内容：「${mail.content}」`
                            }
                        });
                    }
                }
            });

            // 🆕 发送专属包裹
            ws({
                "action": "send_group_forward_msg",
                "params": {
                    "group_id": parseInt(targetGidRaw, 10),
                    "messages": personalNodes
                }
            }, deliverCtx, deliverMsg, "");

        } else {
            fail += mails.length;
        }
    }

    // 统一发送曝光内容
    if (publicNodes.length > 0 && announceGroupId && announceGroupId !== "null") {
        const targetAnnounceGidRaw = announceGroupId.toString().replace(/[^\d]/g, "");
        publicNodes.unshift({
            type: "node",
            data: {
                name: "心动天使",
                uin: "2852199344",
                content: `✨ 哎呀，有 ${publicNodes.length} 份心意在飞往信箱的途中，不小心飘落到了公告区...`
            }
        });

        const pubMsg = seal.newMessage();
        pubMsg.messageType = "group";
        pubMsg.groupId = `${platform}-Group:${targetAnnounceGidRaw}`;
        const pubCtx = seal.createTempCtx(eps[0], pubMsg);

        ws({
            "action": "send_group_forward_msg",
            "params": {
                "group_id": parseInt(targetAnnounceGidRaw, 10),
                "messages": publicNodes
            }
        }, pubCtx, pubMsg, "");
    }

    ext.storageSet(mailKey, "[]");
    return { success, fail, publicCount, empty: false };
}

// 辅助函数保持不变...
function isLoveMailEnabled() {
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    return config.enable_lovemail !== false;
}

function sendTextToGroup(platform, gid, text) {
    try {
        const target = `${platform}-Group:${gid.toString().replace(/[^\d]/g, "")}`;
        const deliverMsg = seal.newMessage();
        deliverMsg.messageType = "group";
        deliverMsg.groupId = target;
        const eps = seal.getEndPoints();
        if (eps && eps.length > 0) {
            const deliverCtx = seal.createTempCtx(eps[0], deliverMsg);
            seal.replyToSender(deliverCtx, deliverMsg, text);
        }
    } catch (e) {
        console.log(`[心动信箱] 发送失败: ${e.message}`);
    }
}

// 启动
registerLoveMailSystem();
// === 基础配置与工具函数 ===
seal.ext.registerIntConfig(ext, "dailyDrawLimit", 2, "每日抽取次数上限");

// 获取当前角色的工具函数
const ItemRoleUtils = {
    // 1. 获取角色标识 (平台+角色名)
    getRoleKey: (ctx, msg) => {
        const platform = msg.platform;
        const uid = msg.sender.userId.replace(`${platform}:`, "");
        const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
        const roleName = Object.entries(a_private_group[platform] || {})
            .find(([_, val]) => val[0] === uid)?.[0];
        return roleName ? `${platform}:${roleName}` : null;
    },

    // 2. 获取池子数据
    getPool: () => JSON.parse(ext.storageGet("sys_item_pool") || "[]"),
    setPool: (data) => ext.storageSet("sys_item_pool", JSON.stringify(data)),

    // 3. 【方案C核心】全服背包管理
    getGlobalInvs: () => JSON.parse(ext.storageGet("global_inventories") || "{}"),
    setGlobalInvs: (data) => ext.storageSet("global_inventories", JSON.stringify(data)),

    // 获取特定角色的背包
    getInv: (roleKey) => {
        const invs = ItemRoleUtils.getGlobalInvs();
        return invs[roleKey] || [];
    },
    // 保存特定角色的背包
    setInv: (roleKey, inv) => {
        const invs = ItemRoleUtils.getGlobalInvs();
        invs[roleKey] = inv;
        ItemRoleUtils.setGlobalInvs(invs);
    },

    // 4. 抽取记录 (建议也存入大表，方便初始化一键重置)
    getGlobalRecords: () => JSON.parse(ext.storageGet("global_draw_records") || "{}"),
    setGlobalRecords: (data) => ext.storageSet("global_draw_records", JSON.stringify(data)),

    getToday: () => {
        const d = new Date();
        return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    }
};

// === 管理员指令：投放与管理池子 ===
let cmd_item_admin = seal.ext.newCmdItemInfo();
cmd_item_admin.name = "投放";
cmd_item_admin.help = "【管理员指令】\n。投放 添加 物品名|描述|数量 —— 批量向池子投放物资\n。投放 查看池子 —— 查看当前池内剩余物资统计\n。投放 移除 物品名 —— 从池子里删掉一个特定物品\n。投放 清空池子 —— 彻底清空物资池";

cmd_item_admin.solve = (ctx, msg, cmdArgs) => {
    // 权限检查
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可操作物资池。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const subCmd = cmdArgs.getArgN(1);
    let pool = ItemRoleUtils.getPool();

    // 1. 手动加东西 (。投放 添加 物品名|描述|数量)
    if (subCmd === '添加') {
        const rawInput = cmdArgs.getArgN(2);
        if (!rawInput) {
            seal.replyToSender(ctx, msg, "用法错误！示例：。投放 添加 肾上腺素|急救用药品|5");
            return seal.ext.newCmdExecuteResult(true);
        }

        const parts = rawInput.split('|');
        const name = (parts[0] || "无名物品").trim();
        const desc = (parts[1] || "该物品没有任何描述").trim();
        const count = parseInt(parts[2]) || 1;

        if (name === "") return seal.replyToSender(ctx, msg, "❌ 物品名不能为空。");

        // 循环加入池子
        for (let i = 0; i < count; i++) {
            pool.push({
                name: name,
                desc: desc,
                used: false,
                createTime: new Date().getTime()
            });
        }

        ItemRoleUtils.setPool(pool);
        seal.replyToSender(ctx, msg, `✅ 投放成功！\n物品：【${name}】\n数量：${count} 件\n描述：${desc}\n目前池内总计：${pool.length} 件物资。`);

    // 2. 查看池子 (。投放 查看池子)
    } else if (subCmd === '查看池子' || subCmd === '查看') {
        if (pool.length === 0) {
            seal.replyToSender(ctx, msg, "📋 当前物资池空空如也，请先使用「。投放 添加」放入物资。");
            return seal.ext.newCmdExecuteResult(true);
        }

        // 按名称统计数量
        const stats = pool.reduce((acc, item) => {
            acc[item.name] = (acc[item.name] || 0) + 1;
            return acc;
        }, {});

        let text = `📋 物资池状态 (总计: ${pool.length} 件)：\n`;
        for (let name in stats) {
            text += `· ${name}：共 ${stats[name]} 件\n`;
        }
        text += `\n💡 玩家使用「。抽取」指令时将从中随机获得一件。`;
        
        seal.replyToSender(ctx, msg, text.trim());

    // 3. 移除特定物品 (。投放 移除 物品名)
    } else if (subCmd === '移除') {
        const targetName = cmdArgs.getArgN(2);
        const index = pool.findIndex(i => i.name === targetName);
        
        if (index > -1) {
            pool.splice(index, 1);
            ItemRoleUtils.setPool(pool);
            seal.replyToSender(ctx, msg, `🗑️ 已从池子中移除一件【${targetName}】。剩余：${pool.length} 件。`);
        } else {
            seal.replyToSender(ctx, msg, `❌ 池子中没有名为【${targetName}】的物品。`);
        }

    // 4. 清空池子
    } else if (subCmd === '清空池子') {
        ItemRoleUtils.setPool([]);
        seal.replyToSender(ctx, msg, "☢️ 物资池已彻底清空。");

    } // 5. 手动给特定玩家加东西 (。投放 给予 角色名|物品名|描述)
    else if (subCmd === '给予' || subCmd === '发放') {
        const rawInput = cmdArgs.getArgN(2);
        if (!rawInput) {
            seal.replyToSender(ctx, msg, "用法错误！示例：。投放 给予 张三|神秘钥匙|一把发光的钥匙");
            return seal.ext.newCmdExecuteResult(true);
        }

        const parts = rawInput.split('|');
        const targetRoleName = (parts[0] || "").trim();
        const itemName = (parts[1] || "").trim();
        const itemDesc = (parts[2] || "管理员发放的物品").trim();

        if (!targetRoleName || !itemName) return seal.replyToSender(ctx, msg, "❌ 格式错误：角色名和物品名不能为空。");

        const platform = msg.platform;
        const targetKey = `${platform}:${targetRoleName}`;

        // 验证角色是否存在于 a_private_group
        const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
        if (!a_private_group[platform]?.[targetRoleName]) {
            return seal.replyToSender(ctx, msg, `❌ 错误：角色「${targetRoleName}」未登记。`);
        }

        // 获取并更新该角色的背包
        let inv = ItemRoleUtils.getInv(targetKey);
        inv.push({
            name: itemName,
            desc: itemDesc,
            used: false,
            createTime: new Date().getTime(),
            source: "Admin" // 标记来源
        });
        
        ItemRoleUtils.setInv(targetKey, inv);
        seal.replyToSender(ctx, msg, `✅ 已手动向角色【${targetRoleName}】的背包发放：【${itemName}】`);

    } else {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["投放"] = cmd_item_admin;

// === 玩家指令：抽取 ===
let cmd_item_draw = seal.ext.newCmdItemInfo();
cmd_item_draw.name = "抽取";
cmd_item_draw.solve = (ctx, msg) => {
    const roleKey = ItemRoleUtils.getRoleKey(ctx, msg);
    if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先创建并绑定角色。");

    const today = ItemRoleUtils.getToday();
    const limit = seal.ext.getIntConfig(ext, "dailyDrawLimit");

    // 读取抽取记录
    let records = ItemRoleUtils.getGlobalRecords();
    let myRec = records[roleKey] || { date: "", count: 0 };
    if (myRec.date !== today) myRec = { date: today, count: 0 };

    if (myRec.count >= limit) {
        seal.replyToSender(ctx, msg, `⚠️ 你今日抽取次数已达上限(${limit})。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let pool = ItemRoleUtils.getPool();
    if (pool.length === 0) return seal.replyToSender(ctx, msg, "❌ 物资池已空。");

    const index = Math.floor(Math.random() * pool.length);
    const item = pool.splice(index, 1)[0];
    ItemRoleUtils.setPool(pool);

    // 存入背包
    let inv = ItemRoleUtils.getInv(roleKey);
    inv.push(item);
    ItemRoleUtils.setInv(roleKey, inv);

    // 更新记录
    myRec.count += 1;
    records[roleKey] = myRec;
    ItemRoleUtils.setGlobalRecords(records);

    const name = roleKey.split(":")[1];
    seal.replyToSender(ctx, msg, `🎁 【${name}】获得了：【${item.name}】\n描述：${item.desc}\n(今日进度: ${myRec.count}/${limit})`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["抽取"] = cmd_item_draw;

// === 玩家指令：背包 ===
let cmd_item_inv = seal.ext.newCmdItemInfo();
cmd_item_inv.name = "背包";
cmd_item_inv.solve = (ctx, msg) => {
    const roleKey = ItemRoleUtils.getRoleKey(ctx, msg);
    if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");

    let inv = ItemRoleUtils.getInv(roleKey);
    const name = roleKey.split(":")[1];
    if (inv.length === 0) return seal.replyToSender(ctx, msg, `🎒 【${name}】的背包空空如也。`);

    let text = `🎒 【${name}】的背包：\n`;
    inv.forEach((item, idx) => {
        text += `${idx + 1}. ${item.name}${item.used ? " [已使用]" : ""}\n   └ ${item.desc}\n`;
    });
    seal.replyToSender(ctx, msg, text.trim());
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["背包"] = cmd_item_inv;

// === 玩家指令：赠送 ===
let cmd_item_give = seal.ext.newCmdItemInfo();
cmd_item_give.name = "赠送";
cmd_item_give.solve = (ctx, msg, cmdArgs) => {
    const myKey = ItemRoleUtils.getRoleKey(ctx, msg);
    const targetName = cmdArgs.getArgN(1);
    const itemName = cmdArgs.getArgN(2);
    const platform = msg.platform;

    if (!myKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");
    const targetKey = `${platform}:${targetName}`;

    // 检查目标是否存在
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]?.[targetName]) return seal.replyToSender(ctx, msg, `❌ 角色「${targetName}」不存在。`);
    if (myKey === targetKey) return seal.replyToSender(ctx, msg, "⚠️ 不能送给自己。");

    let myInv = ItemRoleUtils.getInv(myKey);
    const idx = myInv.findIndex(i => i.name === itemName);

    if (idx > -1) {
        const item = myInv.splice(idx, 1)[0];
        ItemRoleUtils.setInv(myKey, myInv);

        let tInv = ItemRoleUtils.getInv(targetKey);
        tInv.push(item);
        ItemRoleUtils.setInv(targetKey, tInv);

        seal.replyToSender(ctx, msg, `🤝 赠送成功！【${item.name}】已交给【${targetName}】。`);
    } else {
        seal.replyToSender(ctx, msg, `❌ 背包里没有【${itemName}】。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["赠送"] = cmd_item_give;

// === 4. 玩家指令：使用 (方案 C 修正版) ===
let cmd_item_use = seal.ext.newCmdItemInfo();
cmd_item_use.name = "使用";
cmd_item_use.solve = (ctx, msg, cmdArgs) => {
    const roleKey = ItemRoleUtils.getRoleKey(ctx, msg); // 使用 roleKey 标识
    const itemName = cmdArgs.getArgN(1);
    
    if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");
    if (!itemName) return seal.replyToSender(ctx, msg, "用法：。使用 物品名");

    const roleName = roleKey.split(":")[1]; // 获取角色名用于回显
    let inv = ItemRoleUtils.getInv(roleKey); // 统一调用方式
    const item = inv.find(i => i.name === itemName && !i.used);
    
    if (item) {
        item.used = true; // 标记为已使用
        ItemRoleUtils.setInv(roleKey, inv); // 保存回全局大表
        seal.replyToSender(ctx, msg, `⚙️ 【${roleName}】使用了【${itemName}】。`);
    } else {
        seal.replyToSender(ctx, msg, `❌ 背包中没有未使用的【${itemName}】。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["使用"] = cmd_item_use;

// ========================
// 📞 盲盒电话系统配置
// ========================
seal.ext.registerIntConfig(ext, "blindPhoneMaxInitiated", 1, "最大发起的盲盒电话上限", "每个人同时能开启的盲盒电话数量");
seal.ext.registerIntConfig(ext, "blindPhoneMaxMessages", 90, "盲盒电话对话上限", "达到此条数后电话会自动断开");
seal.ext.registerIntConfig(ext, "blindPhoneCooldown", 5, "发起盲盒电话冷却时间（分钟）", "两次发起之间的最小间隔");
seal.ext.registerIntConfig(ext, "blindPhoneDailyLimit", 10, "每日发起盲盒电话上限", "每个角色每天可以发起的次数");

const BlindPhoneUtils = {
    getData: () => JSON.parse(ext.storageGet("blind_phones") || "{}"),
    setData: (data) => ext.storageSet("blind_phones", JSON.stringify(data)),
    // 获取/设置个人冷却与计数
    getUserStat: (uid) => JSON.parse(ext.storageGet(`blind_stat_${uid}`) || '{"lastTime":0, "dailyCount":0, "day":""}'),
    setUserStat: (uid, stat) => ext.storageSet(`blind_stat_${uid}`, JSON.stringify(stat)),
    generateId: () => Math.random().toString(36).substring(2, 8).toUpperCase(),
    anonymousUin: "2852199344" 
};

// ========================
// ☎️ 指令：。接通盲盒电话
// ========================
let cmd_start_blind_phone = seal.ext.newCmdItemInfo();
cmd_start_blind_phone.name = "接通盲盒电话";
cmd_start_blind_phone.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId;
    const senderName = RelationshipUtils.getRoleName(ctx, msg, platform);
    if (!senderName) return seal.replyToSender(ctx, msg, "❌ 您还没有登记姓名，无法拨打电话。");

    // --- 1. 冷却与上限检查 ---
    const now = Date.now();
    const today = new Date().toDateString();
    let stat = BlindPhoneUtils.getUserStat(uid);

    if (stat.day !== today) {
        stat.day = today;
        stat.dailyCount = 0;
    }

    const cdMinutes = seal.ext.getIntConfig(ext, "blindPhoneCooldown");
    if (now - stat.lastTime < cdMinutes * 60 * 1000) {
        const wait = Math.ceil((cdMinutes * 60 * 1000 - (now - stat.lastTime)) / 1000 / 60);
        return seal.replyToSender(ctx, msg, `⏳ 电话线路繁忙，请休息 ${wait} 分钟后再试。`);
    }

    const dailyLimit = seal.ext.getIntConfig(ext, "blindPhoneDailyLimit");
    if (stat.dailyCount >= dailyLimit) {
        return seal.replyToSender(ctx, msg, `⚠️ 您今天的拨打次数已达上限 (${dailyLimit}次)，请明天再拨。`);
    }

    let phoneData = BlindPhoneUtils.getData();
    const myActive = Object.values(phoneData).filter(p => p.caller === senderName && p.status === "active");
    if (myActive.length >= seal.ext.getIntConfig(ext, "blindPhoneMaxInitiated")) {
        return seal.replyToSender(ctx, msg, `⚠️ 您的通话线路已被占用，请先挂断当前通话 [${myActive[0].id}]。`);
    }

    // --- 2. 随机匹配 ---
    const groups = JSON.parse(ext.storageGet("a_private_group") || "{}")[platform] || {};
    const allRoles = Object.keys(groups).filter(name => name !== senderName);
    if (allRoles.length === 0) return seal.replyToSender(ctx, msg, "📭 暂时没有可以接听电话的用户。");
    
    const targetRole = allRoles[Math.floor(Math.random() * allRoles.length)];

    // --- 3. 建立连接 ---
    const phoneId = BlindPhoneUtils.generateId();
    phoneData[phoneId] = {
        id: phoneId, caller: senderName, callee: targetRole,
        messages: [], status: "active", startTime: now
    };
    BlindPhoneUtils.setData(phoneData);

    stat.lastTime = now;
    stat.dailyCount += 1;
    BlindPhoneUtils.setUserStat(uid, stat);

    // --- 4. 发起者回执 (生活化措辞) ---
    let receipt = `📞 【拨号成功 · 等待接听】\n${"━".repeat(15)}\n`;
    receipt += `🔢 线路编号：${phoneId}\n`;
    receipt += `👤 通话对象：随机匹配中 (身份已隐藏)\n`;
    receipt += `🔋 今日通话剩余：${dailyLimit - stat.dailyCount}次\n`;
    receipt += `${"┈".repeat(15)}\n`;
    receipt += `💡 对方的电话正在响起...\n`;
    receipt += `💬 回复：。盲盒聊天 ${phoneId} 内容\n`;
    receipt += `📴 挂断：。挂断盲盒电话 ${phoneId}`;
    seal.replyToSender(ctx, msg, receipt);

    // --- 5. 接收方通知 ---
    const targetAddr = getTargetAddr(platform, targetRole);
    if (targetAddr) {
        ws({
            "action": "send_group_forward_msg",
            "params": {
                "group_id": parseInt(targetAddr[1].replace(/[^\d]/g, ""), 10),
                "messages": [{
                    type: "node", data: {
                        name: "未知来电", uin: BlindPhoneUtils.anonymousUin,
                        content: `📱 叮铃铃！您收到了一个盲盒来电。\n\n线路编号：${phoneId}\n回复方式：使用「。盲盒聊天 ${phoneId} [内容]」进行通话。`
                    }
                }]
            }
        }, ctx, msg, "");
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["接通盲盒电话"] = cmd_start_blind_phone;

// ========================
// 💬 指令：。盲盒聊天 编号 内容
// ========================
let cmd_blind_chat = seal.ext.newCmdItemInfo();
cmd_blind_chat.name = "盲盒聊天";
cmd_blind_chat.solve = (ctx, msg, cmdArgs) => {
    const phoneId = cmdArgs.getArgN(1);
    const content = msg.message.replace(/^[。.]盲盒聊天\s+\S+\s+/, "").trim();
    const platform = msg.platform;
    const uid = msg.sender.userId;
    const senderName = RelationshipUtils.getRoleName(ctx, msg, platform);

    if (!phoneId || !content) return seal.replyToSender(ctx, msg, "格式：。盲盒聊天 编号 内容");

    let phoneData = BlindPhoneUtils.getData();
    const phone = phoneData[phoneId];

    if (!phone || phone.status !== "active") return seal.replyToSender(ctx, msg, "❌ 这通电话已经挂断或线路不存在。");
    
    let identity = "";
    let targetRole = "";
    if (phone.caller === senderName) {
        identity = "发起者";
        targetRole = phone.callee;
    } else if (phone.callee === senderName) {
        identity = "接收者";
        targetRole = phone.caller;
    } else {
        return seal.replyToSender(ctx, msg, "⚠️ 您不在当前的通话线路上。");
    }

    // 聊天冷却
    const now = Date.now();
    const chatCooldownKey = `blind_chat_cd_${uid}_${phoneId}`;
    const lastChatTime = parseInt(ext.storageGet(chatCooldownKey) || "0");
    const chatCdMinutes = seal.ext.getIntConfig(ext, "secretLetterCooldown");

    if (now - lastChatTime < chatCdMinutes * 60 * 1000) {
        const remaining = Math.ceil((chatCdMinutes * 60 * 1000 - (now - lastChatTime)) / 1000);
        return seal.replyToSender(ctx, msg, `⏳ 话筒还没传过来，请等待 ${remaining} 秒再继续通话。`);
    }

    phone.messages.push({ from: identity, text: content });
    ext.storageSet(chatCooldownKey, now.toString());

    // 熔断
    const maxMsgs = seal.ext.getIntConfig(ext, "blindPhoneMaxMessages");
    if (phone.messages.length >= maxMsgs) {
        delete phoneData[phoneId];
        BlindPhoneUtils.setData(phoneData);
        const endMsg = `📴 【通话结束】当前的通话时长已达上限，线路已自动切断。`;
        seal.replyToSender(ctx, msg, endMsg);
        const targetAddr = getTargetAddr(platform, targetRole);
        if (targetAddr) ws({ "action": "send_group_msg", "params": { "group_id": parseInt(targetAddr[1].replace(/[^\d]/g, "")), "message": endMsg } }, ctx, msg, "");
        return seal.ext.newCmdExecuteResult(true);
    }

    BlindPhoneUtils.setData(phoneData);

    const targetAddr = getTargetAddr(platform, targetRole);
    if (targetAddr) {
        const nodes = phone.messages.slice(-5).map(m => ({
            type: "node", data: { name: m.from, uin: BlindPhoneUtils.anonymousUin, content: m.text }
        }));
        nodes.unshift({
            type: "node", data: { name: "通话中", uin: "10001", content: `(线路 ${phoneId}) 对方说：` }
        });

        ws({
            "action": "send_group_forward_msg",
            "params": {
                "group_id": parseInt(targetAddr[1].replace(/[^\d]/g, ""), 10),
                "messages": nodes
            }
        }, ctx, msg, "");
        seal.replyToSender(ctx, msg, `✅ 话语已传达到对方耳边。`);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ 信号中断，无法传达。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["盲盒聊天"] = cmd_blind_chat;

// ========================
// 📴 指令：。挂断盲盒电话 编号
// ========================
let cmd_hangup_blind = seal.ext.newCmdItemInfo();
cmd_hangup_blind.name = "挂断盲盒电话";
cmd_hangup_blind.solve = (ctx, msg, cmdArgs) => {
    const phoneId = cmdArgs.getArgN(1);
    const senderName = RelationshipUtils.getRoleName(ctx, msg, msg.platform);

    let phoneData = BlindPhoneUtils.getData();
    const phone = phoneData[phoneId];

    if (!phone) return seal.replyToSender(ctx, msg, "❌ 找不到该电话编号。");
    if (phone.caller !== senderName && phone.callee !== senderName) return seal.replyToSender(ctx, msg, "⚠️ 你无权挂断此电话。");

    const targetRole = (phone.caller === senderName) ? phone.callee : phone.caller;
    delete phoneData[phoneId];
    BlindPhoneUtils.setData(phoneData);

    const endMsg = `📴 对方已挂断了盲盒电话 [${phoneId}]。`;
    seal.replyToSender(ctx, msg, `✅ 你已挂断电话。`);

    const targetAddr = getTargetAddr(msg.platform, targetRole);
    if (targetAddr) {
        ws({ "action": "send_group_msg", "params": { "group_id": parseInt(targetAddr[1]), "message": endMsg } }, ctx, msg, "");
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["挂断盲盒电话"] = cmd_hangup_blind;

// ========================
// 🎭 指令：。设为npc [名字]
// ========================
let cmd_set_npc = seal.ext.newCmdItemInfo();
cmd_set_npc.name = "设为npc";
cmd_set_npc.help = "用法：.设为npc [角色名]\n说明：将角色标记为NPC，标记后该角色不会参与自动分组。再次输入可取消标记。";
cmd_set_npc.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 仅限管理员使用此功能。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let name = cmdArgs.getArgN(1);
    if (!name) {
        seal.replyToSender(ctx, msg, "❌ 请输入要操作的角色名。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let platform = msg.platform;
    let storage = getRoleStorage();
    let npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");

    if (!storage[platform] || !storage[platform][name]) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${name}」，请先创建角色。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let index = npcList.indexOf(name);
    if (index === -1) {
        npcList.push(name);
        ext.storageSet("a_npc_list", JSON.stringify(npcList));
        seal.replyToSender(ctx, msg, `✅ 已将「${name}」设为 NPC，分组时将自动跳过。`);
    } else {
        npcList.splice(index, 1);
        ext.storageSet("a_npc_list", JSON.stringify(npcList));
        seal.replyToSender(ctx, msg, `✅ 已取消「${name}」的 NPC 身份。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设为npc"] = cmd_set_npc;

// ========================
// 🎲 指令：。随机分组 [组数]
// ========================
let cmd_random_group = seal.ext.newCmdItemInfo();
cmd_random_group.name = "随机分组";
cmd_random_group.help = "用法：.随机分组 [数字]\n说明：将所有非NPC玩家随机分配到指定数量的组中。";
cmd_random_group.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 仅限管理员使用分组功能。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let groupCount = parseInt(cmdArgs.getArgN(1));
    if (isNaN(groupCount) || groupCount <= 0) {
        seal.replyToSender(ctx, msg, "❌ 请输入正确的小组数量，例如：.随机分组 2");
        return seal.ext.newCmdExecuteResult(true);
    }

    let platform = msg.platform;
    let storage = getRoleStorage();
    let npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");
    
    // 获取当前平台所有玩家，并剔除 NPC
    let players = Object.keys(storage[platform] || {}).filter(name => !npcList.includes(name));

    if (players.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 当前平台没有可分配的非NPC玩家。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (groupCount > players.length) {
        seal.replyToSender(ctx, msg, `❌ 组数(${groupCount})不能大于玩家总数(${players.length})。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 洗牌算法 (Fisher-Yates Shuffle)
    for (let i = players.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [players[i], players[j]] = [players[j], players[i]];
    }

    // 分配到小组
    let groups = Array.from({ length: groupCount }, () => []);
    players.forEach((player, index) => {
        groups[index % groupCount].push(player);
    });

    // 构建回复文本
    let response = `🎲 【随机分组结果】\n总人数：${players.length} | 组数：${groupCount}\n`;
    response += "━━━━━━━━━━━━━━\n";
    groups.forEach((members, i) => {
        response += `第 ${i + 1} 组：${members.join("、")}\n`;
    });
    response += "━━━━━━━━━━━━━━";

    seal.replyToSender(ctx, msg, response);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["随机分组"] = cmd_random_group;

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

    let confirmed = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    const platform = msg.platform;
    const privateGroups = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 1. 定位目标角色的 UID
    const targetUid = privateGroups?.[platform]?.[name]?.[0];
    if (!targetUid) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色 ${name} 的注册信息。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetKey = `${platform}:${targetUid}`;

    // 2. 在该角色的日程里找到那场具体的“约会”
    const userSchedule = confirmed[targetKey] || [];
    const appointment = userSchedule.find(ev => ev.day === day && ev.time === time);

    if (!appointment) {
        seal.replyToSender(ctx, msg, `❌ 在 ${name} 的日程中未找到 ${day} ${time} 的记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 提取这场约会涉及的所有人名
    // 如果是单人约会，partner 是名字；如果是多人，你需要确保接受指令里存的是列表或者特殊标识
    let participants = [name];
    if (appointment.partner === "多人小群") {
        // 如果是多人小群，逻辑上我们需要扫描全表，删除所有含有相同 group ID 的记录
        const gid = appointment.group;
        let deletedCount = 0;
        for (let uid in confirmed) {
            let before = confirmed[uid].length;
            confirmed[uid] = confirmed[uid].filter(ev => ev.group !== gid);
            if (confirmed[uid].length < before) deletedCount++;
        }
        ext.storageSet("b_confirmedSchedule", JSON.stringify(confirmed));
        seal.replyToSender(ctx, msg, `✅ 已根据多人小群 ID(${gid}) 抹除所有参与者的排期（共 ${deletedCount} 人）。`);
    } else {
        // 如果是单人约会，精准删除这两个人的
        const partnerName = appointment.partner;
        const partnerUid = privateGroups?.[platform]?.[partnerName]?.[0];
        const partnerKey = partnerUid ? `${platform}:${partnerUid}` : null;

        // 删除发起人（张三）的
        confirmed[targetKey] = confirmed[targetKey].filter(ev => !(ev.day === day && ev.time === time));
        
        // 删除对方的
        if (partnerKey && confirmed[partnerKey]) {
            confirmed[partnerKey] = confirmed[partnerKey].filter(ev => !(ev.day === day && ev.time === time));
        }

        ext.storageSet("b_confirmedSchedule", JSON.stringify(confirmed));
        seal.replyToSender(ctx, msg, `✅ 已精准抹除 ${name} 与 ${partnerName} 在 ${day} ${time} 的约会记录。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["删除时间线"] = cmd_delete_timeline_precise;
/**
 * 🆔 升级版：同步角色名片至 私信群 + 广播群（水群/公告/点歌）
 */
function syncAllFromStorage(ctx, msg) {
    const storage = getRoleStorage();
    const platform = msg.platform || "QQ";
    const platformData = storage[platform] || {};

    // --- 🔍 新增：获取特殊群号 ---
    // 对应你之前在【设置 基础】中存入的键名
    const specialGroups = [
        JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null"), // 公告群
        JSON.parse(ext.storageGet("water_group_id") || "null"),       // 水群
        JSON.parse(ext.storageGet("song_group_id") || "null")        // 点歌群
    ].filter(id => id && id !== "未设置"); // 过滤掉空值

    const charNames = Object.keys(platformData);
    if (charNames.length === 0) {
        seal.replyToSender(ctx, msg, "📭 数据库中没有已注册的角色。");
        return;
    }

    let count = 0;
    charNames.forEach(name => {
        const uid = platformData[name][0];
        const privateGid = platformData[name][1]; // 原有的私信群
        
        // 收集该角色需要同步的所有群 ID
        let targetGroupList = [];
        
        // 1. 添加私信群 (如果有效)
        if (privateGid && privateGid !== "0") targetGroupList.push(privateGid);
        
        // 2. 添加所有特殊群
        targetGroupList = targetGroupList.concat(specialGroups);

        // 去重，防止一个群发两次指令
        targetGroupList = [...new Set(targetGroupList)];

        if (uid) {
            targetGroupList.forEach(gid => {
                const cleanGid = parseInt(gid.toString().replace(/[^\d]/g, ""), 10);
                const cleanUid = parseInt(uid.toString().replace(/[^\d]/g, ""), 10);

                if (!isNaN(cleanGid) && !isNaN(cleanUid)) {
                    const setCardPayload = {
                        "action": "set_group_card",
                        "params": {
                            "group_id": cleanGid,
                            "user_id": cleanUid,
                            "card": name
                        }
                    };

                    try {
                        // 发送修改名片请求
                        ws(setCardPayload, ctx, { platform: platform, groupId: "" }, "");
                        count++;
                    } catch (e) {
                        console.log(`[名片同步] WS下发失败 (群:${gid}): ${e.message}`);
                    }
                }
            });
        }
    });

    seal.replyToSender(ctx, msg, `🔄 名片全同步完成！\n已向 ${specialGroups.length} 个公共群及各私信群下发指令。\n累计尝试更新名片次数：${count}`);
}

// ========================
// 🛠️ 指令注册
// ========================
let cmd_sync_now = seal.ext.newCmdItemInfo();
cmd_sync_now.name = "同步当前群名片"; 
cmd_sync_now.solve = (ctx, msg, cmdArgs) => {
    // 权限检查，确保只有管理员能大规模同步
    if (!isUserAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    
    syncAllFromStorage(ctx, msg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步当前群名片"] = cmd_sync_now;