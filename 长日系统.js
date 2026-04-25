// ==UserScript==
// @name         长日将尽系统
// @author       长日将尽
// @version      1.3.0
// @description  无
// @timestamp    1742205760
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find("changriV1")
if (!ext) {
    ext = seal.ext.new("changriV1", "长日将尽", "1.2.0");
    // 注册扩展
    seal.ext.register(ext);
    ext.autoActive = true;
}
ext.autoActive = true;

seal.ext.registerStringConfig(ext, "ws地址", "ws://localhost:3001");
    seal.ext.registerStringConfig(ext, "ws Access token", '', "输入与上方端口对应的token，没有则留空");
    seal.ext.registerStringConfig(ext, "群管插件使用需要满足的条件", '1', "使用豹语表达式，例如：$t群号_RAW=='2001'，1为所有群可用");
    seal.ext.registerBoolConfig(ext, "开启现实时段校验", false, "是否限制玩家只能发起与当前现实时间对应的剧情时段邀约");

// ========================
// 🌐 WebSocket 通信模块
// ========================
function ws(postData, ctx, msg, successreply) {
    const wsUrl = seal.ext.getStringConfig(ext, "ws地址");
    const token = seal.ext.getStringConfig(ext, "ws Access token");
    let connectionUrl = wsUrl;

    if (token) {
        const separator = connectionUrl.includes('?') ? '&' : '?';
        connectionUrl += `${separator}access_token=${encodeURIComponent(token)}`;
    }

    const currentEcho = postData.echo || (postData.action + "_" + Date.now());
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
    }, 3000);

    ws.onopen = function() {
        try {
            const sendStr = JSON.stringify(postData);
            ws.send(sendStr);
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
                    handleMemberListResponse(ctx, msg, response.data,currentEcho);
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

// 暴露给其他插件使用
ext._ws = ws;
ext._showBackpack = (ctx, msg, targetRoleName) => {
    const platform = msg.platform;
    const roleKey = `${platform}:${targetRoleName}`;
    const inv = (store.get("global_inventories")[roleKey] || []).filter(i => !i.used);
    const fakeMsg = { ...msg };
    const normalGifts = getItemsByCategory(inv, "普通礼物");
    const normalTools = getItemsByCategory(inv, "普通道具");
    const specTools   = getItemsByCategory(inv, "特殊道具");
    const trunc = (s, n = 20) => s && s.length > n ? s.slice(0, n) + "…" : (s || "");
    if (!inv.length) { seal.replyToSender(ctx, msg, `🎒 【${targetRoleName}】背包空空如也。`); return; }
    const mkN = (content) => ({ type: "node", data: { name: BACKPACK_BOT, uin: BACKPACK_UIN, content } });
    const nodes = [mkN(
        `🎒 【${targetRoleName}】的背包\n${"━".repeat(14)}\n` +
        `🎁 普通礼物  ${normalGifts.length} 件 · 📦 普通道具  ${normalTools.length} 件 · ⚙️ 特殊道具  ${specTools.length} 件`
    )];
    const addN = (label, emoji, items, prefix) => {
        if (!items.length) return;
        nodes.push(mkN(`${emoji} ${label}\n${"─".repeat(12)}\n` + items.map((it, i) => `${emoji} ${prefix}${i+1}. ${it.name}${it.from ? `  来自：${it.from}` : ""}  ${trunc(it.desc)}`).join("\n")));
    };
    addN("普通礼物", "🎁", normalGifts, "普通礼物");
    addN("普通道具", "📦", normalTools,  "普通道具");
    addN("特殊道具", "⚙️", specTools,   "特殊道具");
    sendBackpackNodes(ctx, msg, nodes);
};

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

        // 优先匹配 CQ 码格式：[CQ:music,type=qq,id=xxx] / [CQ:music,type=163,id=xxx]
        const cqMatch = originalContent.match(/\[CQ:music,type=(\w+),id=([\w]+)\]/);
        // 次优先匹配 JSON 格式：{"type":"qq","id":"xxx"}
        const jsonTypeMatch = originalContent.match(/"type"\s*:\s*"(qq|163|kugou|migu|kuwo)"/);
        const jsonIdMatch   = originalContent.match(/"id"\s*:\s*"?([\w]+)"?/);

        let songId = "";
        let musicType = "163";

        if (cqMatch) {
            musicType = cqMatch[1];
            songId    = cqMatch[2];
        } else if (jsonTypeMatch && jsonIdMatch) {
            musicType = jsonTypeMatch[1];
            songId    = jsonIdMatch[1];
        } else {
            // 兜底：mid/songmid 字段（旧版 QQ 音乐格式）
            const qqFallback = originalContent.match(/["'](?:mid|songmid)["']\s*[:=]\s*["'](\w+)["']/)
                            || originalContent.match(/mid=([\w]+)/);
            const neteaseFallback = originalContent.match(/id[=:]\s*(\d+)/);
            if (qqFallback) { songId = qqFallback[1]; musicType = "qq"; }
            else if (neteaseFallback) { songId = neteaseFallback[1]; musicType = "163"; }
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
                            "message": `[CQ:music,type=${musicType},id=${songId}]`
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
// ========================
// 🔧 核心工具函数
// ========================

// 全局静默标记和回调
const silentMemberCallbackMap = new Map();

function handleMemberListResponse(ctx, msg, data, echo) {
    let members = [];
    if (Array.isArray(data)) {
        members = data;
    } else if (data && typeof data === 'object') {
        members = data.members || data.list || Object.values(data);
    }

    if (echo && silentMemberCallbackMap.has(echo)) {
        const callback = silentMemberCallbackMap.get(echo);
        silentMemberCallbackMap.delete(echo);
        if (typeof callback === 'function') {
            callback(members);
        }
        return;
    }

    // 3. 如果是审计模式（用于管理员检查群成员对不对），执行审计逻辑
    const auditOwner = ext.storageGet("temp_audit_owner");
    if (auditOwner) {
        performAuditLogic(ctx, msg, auditOwner, members);
        ext.storageSet("temp_audit_owner", "");
        return; // 结束
    }
}

/**
 * 静默获取群成员列表（不输出到聊天窗口）
 * @param {string} gid 群号
 * @param {Object} ctx 上下文
 * @param {Object} msg 消息对象
 * @returns {Promise<Array>} 成员列表
 */
function getGroupMembersSilent(gid, ctx, msg) {
    return new Promise((resolve) => {
        const echo = `get_group_member_list_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        silentMemberCallbackMap.set(echo, resolve);

        ws({
            action: "get_group_member_list",
            params: { group_id: parseInt(gid, 10) },
            echo: echo
        }, ctx, msg, null);

        // 超时兜底：3.5秒后若仍未响应，清理并以空数组 resolve，避免 Promise 永远悬空
        setTimeout(() => {
            if (silentMemberCallbackMap.has(echo)) {
                console.warn(`[getGroupMembersSilent] 超时未响应，echo: ${echo}, gid: ${gid}`);
                silentMemberCallbackMap.delete(echo);
                resolve([]);
            }
        }, 3500);
    });
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
        "寄信": "chaosletter",
        "礼物": "gift",
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
            if (subtype === "礼物") return getDirectRecord("礼物赠送", count, "🎁");
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
    // 直接返回数据，不再进行 Array 检查和 needsUpdate 判断
    return data;
}

// ========================
// 👤 角色与权限管理
// ========================

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

    initCharProfile(platform, name);

    if (isRename) {
        // 迁移档案key
        const profiles = store.get("sys_char_profiles");
        const oldKey = `${platform}:${oldName}`;
        const newKey = `${platform}:${name}`;
        if (profiles[oldKey]) { profiles[newKey] = profiles[oldKey]; delete profiles[oldKey]; store.set("sys_char_profiles", profiles); }
        seal.replyToSender(ctx, msg, `✅ 角色名已由「${oldName}」更新为「${name}」`);
    } else {
        const profile = getCharProfile(platform, name);
        seal.replyToSender(ctx, msg,
            `✅ 角色「${name}」创建成功！\n` +
            `\n欢迎加入长日！以下是你的初始档案：\n` +
            `👤 性别：${profile.gender}　年龄：${profile.age}\n` +
            `🌸 皮相：${profile.look}\n` +
            `\n💡 可发送以下消息定制角色：\n` +
            `  修改性别 男/女\n` +
            `  修改年龄 数字\n` +
            `  修改皮相 明星名\n` +
            `  修改签名 你的签名（12小时冷却）\n` +
            `\n发送「玩家名单」查看所有角色，「指令指南」查看全部功能。`
        );
    }
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

    // 获取 NPC 列表（全局存储）
    let npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");

    let rep = `📊 当前已绑定角色列表：\n`;
    for (let [name, info] of Object.entries(roles)) {
        let isNPC = npcList.includes(name);
        let npcTag = isNPC ? " 🎭" : "";
        const prof = getCharProfile(platform, name);
        const gender = prof.gender || "女";
        const age = prof.age !== undefined ? prof.age : 18;
        const look = prof.look || (gender === "男" ? "亨利卡维尔" : "刘亦菲");
        const bio = prof.bio ? `\n   签名：${prof.bio}` : "";
        rep += `👤 ${name}${npcTag}\n   ${gender} · ${age}岁 · 皮相：${look}${bio}\n\n`;
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


// ========================
// ========================
// 🗝️ 地点权限管理系统
// ========================

// --- 核心工具函数 ---
const store = {
    get: (key) => JSON.parse(ext.storageGet(key) || "{}"),
    set: (key, val) => ext.storageSet(key, JSON.stringify(val))
};

const getRoleName = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    // Check primary roles first
    const roles = store.get("a_private_group")[platform] || {};
    const primary = Object.entries(roles).find(([_, val]) => val[0] === uid)?.[0];
    if (primary) return primary;
    // Resolve via extra_accounts alias
    const extras = store.get("extra_accounts");
    const primaryUid = extras[`${platform}:${uid}`];
    if (primaryUid) return Object.entries(roles).find(([_, val]) => val[0] === primaryUid)?.[0] || null;
    return null;
};

const getUserRoleName = (platform, fullUid) => {
    const uid = String(fullUid).replace(`${platform}:`, "");
    const roles = store.get("a_private_group")[platform] || {};
    const primary = Object.entries(roles).find(([_, val]) => val[0] === uid)?.[0];
    if (primary) return primary;
    const extras = store.get("extra_accounts");
    const primaryUid = extras[`${platform}:${uid}`];
    if (primaryUid) return Object.entries(roles).find(([_, val]) => val[0] === primaryUid)?.[0] || null;
    return null;
};

// ========================
// 角色档案系统
// ========================
function getCharProfile(platform, roleName) {
    const profiles = store.get("sys_char_profiles");
    return profiles[`${platform}:${roleName}`] || {};
}

function setCharProfile(platform, roleName, patch) {
    const profiles = store.get("sys_char_profiles");
    const key = `${platform}:${roleName}`;
    profiles[key] = Object.assign(profiles[key] || {}, patch);
    store.set("sys_char_profiles", profiles);
}

function initCharProfile(platform, roleName, gender) {
    const genderVal = gender || "女";
    const defaultLook = genderVal === "男" ? "亨利卡维尔" : "刘亦菲";
    const existing = getCharProfile(platform, roleName);
    setCharProfile(platform, roleName, {
        gender: existing.gender || genderVal,
        age: existing.age !== undefined ? existing.age : 18,
        look: existing.look || defaultLook,
        bio: existing.bio || "",
        bioUpdatedAt: existing.bioUpdatedAt || 0,
        lookUpdatedAt: existing.lookUpdatedAt || 0
    });
}

// 背包物品按类别分组（兼容无 type 字段的旧数据）
// 普通礼物: 赠送收到的礼物 + 礼物商城物品
// 普通道具: 抽取所得普通物品
// 特殊道具: 管理员发放的功能性道具（追踪器/万能钥匙等）
function getItemsByCategory(inv, cat) {
    return inv.filter(i => {
        if (cat === "特殊道具") return i.special === true || i.type === "道具";
        if (cat === "普通道具") return i.type === "普通" && !i.special;
        if (cat === "普通礼物") return i.type === "普通礼物" || i.type === "礼物";
        return false;
    });
}

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

    // 新增：检查私人房间是否被禁用
    const allowPrivateRooms = JSON.parse(ext.storageGet("allow_private_rooms") || "true");
    const isPrivateRoom = place.match(/^(.+?)的房间$/);
    if (!allowPrivateRooms && isPrivateRoom) {
      return { 
        valid: false, 
        errorMsg: `⚠️ 私人房间功能已关闭，不能使用「${place}」格式的地点。\n` 
      };
    }
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
        
        // 增加私人房间开关状态（仅当地点系统启用时显示）
        const placeConfig = JSON.parse(ext.storageGet("place_system_config") || '{"enabled": false}');
        if (placeConfig.enabled) {
            const allowPrivateRooms = JSON.parse(ext.storageGet("allow_private_rooms") || "true");
            rep += `\n🏠 私人房间功能：${allowPrivateRooms ? "✅ 开启" : "❌ 关闭"}\n`;
        }
        rep += "\n提示：也可使用「[角色名]的房间」";
        return seal.replyToSender(ctx, msg, rep);
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
            // 支持中英文冒号
            const [name, desc] = arg.split(/[:：]/);
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
        case "私人房间": {
          const subCmd = cmdArgs.getArgN(2); // on/off 或 开关
          let allow = JSON.parse(ext.storageGet("allow_private_rooms") || "true");
          if (subCmd === "on" || subCmd === "开" || subCmd === "开启") {
            allow = true;
            ext.storageSet("allow_private_rooms", "true");
            seal.replyToSender(ctx, msg, "✅ 私人房间功能已开启，玩家可以使用「[角色名]的房间」格式的地点。");
          } else if (subCmd === "off" || subCmd === "关") {
            allow = false;
            ext.storageSet("allow_private_rooms", "false");
            seal.replyToSender(ctx, msg, "❌ 私人房间功能已关闭，玩家将不能使用「[角色名]的房间」格式的地点。");
          } else {
            // 显示当前状态
            const status = allow ? "开启" : "关闭";
            seal.replyToSender(ctx, msg, `🏠 私人房间功能当前状态：${status}\n使用：.地点管理 私人房间 on/off 来切换。`);
          }
          break;
        }
        default:
              const helpMsg = `
          📚 地点管理命令帮助

          1. 添加地点
            用法：.地点管理 添加 地点名:描述
            示例：.地点管理 添加 庭院:一个阳光充足的小院子
            说明：地点名和描述之间用英文冒号或中文冒号分隔，描述可以留空。

          2. 删除地点
            用法：.地点管理 删除 地点名
            示例：.地点管理 删除 庭院
            说明：会完全移除该地点，所有与之相关的钥匙记录也会失效。

          3. 开关地点（上锁/解锁）
            用法：.地点管理 开关 地点名
            示例：.地点管理 开关 庭院
            说明：上锁后，没有对应钥匙的玩家无法进入该地点。

          4. 发放/收回钥匙
            用法：.地点管理 钥匙 角色名 地点名
            示例：.地点管理 钥匙 张三 庭院
            说明：如果该角色还没有这把钥匙，则发放；如果已有，则收回（切换式）。

          5. 清空所有地点和钥匙
            用法：.地点管理 清空 Y
            示例：.地点管理 清空 Y
            说明：⚠️ 永久删除所有地点数据和钥匙数据，无法恢复，需要确认参数 Y。

          6. 私人房间开关（全局功能）
            用法：.地点管理 私人房间 on/off
            示例：.地点管理 私人房间 on
            说明：开启后，玩家可以使用“[角色名]的房间”格式创建私人地点。
            当前状态：${JSON.parse(ext.storageGet("allow_private_rooms") || "true") ? "开启" : "关闭"}

          💡 提示：所有子命令中的地点名、角色名均区分大小写，请保持一致。
              `;
              seal.replyToSender(ctx, msg, helpMsg);
              break;
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
    const allowPrivate = JSON.parse(ext.storageGet("allow_private_rooms") || "true");
    rep += `🏠 私人房间开关：${allowPrivate ? "开启" : "关闭"}\n`;
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
// 💕 约会与邀约系统
// ========================
function checkRealityHourLimit(timeStr, ctx, msg) {
    const enable = seal.ext.getBoolConfig(ext, "开启现实时段校验");
    if (!enable) return true;

    const now = new Date();
    const currentHour = now.getHours();
    const currentTimeStr = `${String(currentHour).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

    // 提取预约开始时间的小时
    let startHour = null;
    const match = timeStr.match(/(\d{2}):\d{2}-/);
    if (match) {
        startHour = parseInt(match[1], 10);
    }

    if (startHour === null) {
        seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，无法进行时段检查");
        return false;
    }

    if (startHour !== currentHour) {
        seal.replyToSender(ctx, msg,
            `⚠️ 时段限制：当前现实时间为 ${currentTimeStr}，只能发起当前小时（${currentHour}:00-${currentHour}:59）内的剧情邀约。\n\n` +
            `💡 如需取消此限制，请联系管理在插件配置中关闭“开启现实时段校验”。`);
        return false;
    }
    return true;
}

// ========================
// 🔧 公共辅助函数（电话/私约共用）
// ========================

function parseAndValidateTime(rawTime, allowedRanges, minDuration, subtype) {
    let time = "";
    if (/^\d{4}-\d{4}$/.test(rawTime)) {
        const start = rawTime.slice(0, 2) + ":" + rawTime.slice(2, 4);
        const end = rawTime.slice(5, 7) + ":" + rawTime.slice(7, 9);
        time = `${start}-${end}`;
    } else if (/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/.test(rawTime)) {
        time = rawTime;
    } else {
        return { valid: false, errorMsg: `⚠️ 时间参数格式错误：「${rawTime}」\n请输入标准格式，如：\n· 1100-1200\n· 11:20-12:30` };
    }

    if (allowedRanges.length > 0) {
        const [userStart, userEnd] = time.split('-');
        const ok = allowedRanges.some(range => {
            const [rangeStart, rangeEnd] = range.split('-');
            return userStart >= rangeStart && userEnd <= rangeEnd;
        });
        if (!ok) {
            const rangesText = allowedRanges.map(r => `· ${r}`).join('\n');
            return { valid: false, errorMsg: `⚠️ 时间 ${time} 不在允许的范围内\n\n📋 当前允许的时间段：\n${rangesText}\n\n请选择上述时间段内的预约时间~` };
        }
    }

    if (!isValidTimeFormat(time)) {
        return { valid: false, errorMsg: "请输入正确的时间格式，时间段需合法" };
    }

    const match = time.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/);
    if (match) {
        const startMinutes = parseInt(match[1]) * 60 + parseInt(match[2]);
        const endMinutes = parseInt(match[3]) * 60 + parseInt(match[4]);
        const duration = endMinutes - startMinutes;
        if (duration < minDuration) {
            return { valid: false, errorMsg: `⚠️ ${subtype}邀约时间需大于等于 ${minDuration}分钟，请重新设置（如 ${minDuration === 29 ? "1400-1430" : "14:00-15:00"}）` };
        }
    }

    return { valid: true, time };
}

function checkLockedSlots(platform, day, time, fromKey, sendname, names, a_private_group, a_lockedSlots) {
    let failed = [];
    for (let toname of names) {
        if (!a_private_group[platform] || !a_private_group[platform][toname]) {
            failed.push(`${toname}（未注册）`);
            continue;
        }
        const toKey = `${platform}:${a_private_group[platform][toname][0]}`;
        const toLocked = a_lockedSlots[toKey]?.[day] || [];
        if (toLocked.some(lockedTime => timeOverlap(time, lockedTime))) {
            failed.push(`${toname}（该时段被锁定）`);
            continue;
        }
        if (toname === sendname) {
            failed.push(`${toname}（不能邀请自己）`);
        }
    }
    const fromLocked = a_lockedSlots[fromKey]?.[day] || [];
    const selfLocked = fromLocked.some(lockedTime => timeOverlap(time, lockedTime));
    return { selfLocked, failed };
}

// 修改点：去除了 pending 队列的检查，只查 b_confirmedSchedule 的硬冲突
function checkParticipantConflicts(platform, day, time, sendname, names, a_private_group, b_confirmedSchedule) {
    let failedNames = [];           
    let existingAppointments = [];  

    for (let toname of names) {
        const toKey = `${platform}:${a_private_group[platform][toname][0]}`;
        
        let hasConflict = false;
        let conflictSchedule = null;
        if (b_confirmedSchedule[toKey]) {
            for (let ev of b_confirmedSchedule[toKey]) {
                if (timeConflict(day, time, ev.day, ev.time)) {
                    hasConflict = true;
                    conflictSchedule = ev;   
                    break;
                }
            }
        }
        
        if (hasConflict) {
            existingAppointments.push({
                name: toname,
                schedule: conflictSchedule,
                groupId: conflictSchedule.group,      
                day: conflictSchedule.day,
                time: conflictSchedule.time,
                place: conflictSchedule.place
            });
            continue; 
        }
    }
    
    return { stop: false, failedNames, existingAppointments };
}

function getExampleTimeRange() {
    const now = new Date();
    let startHour = now.getHours();
    const formatHour = (h) => String(h).padStart(2, '0');
    
    if (startHour === 23) {
        return "2300-2359";  
    }
    return `${formatHour(startHour)}00-${formatHour(startHour + 1)}00`;
}

function mergeIntoExistingAppointment(ctx, msg, existingAppointment, newNames, preData) {
    const { platform, sendname, day, time, place, a_private_group, fromKey } = preData;
    const groupId = existingAppointment.group;
    
    let groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
    let existingParticipants = groupExpireInfo[groupId]?.participants || [];
    
    if (existingParticipants.length === 0) {
        const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
        const participantsSet = new Set();
        for (const [key, schedules] of Object.entries(b_confirmedSchedule)) {
            for (const ev of schedules) {
                if (ev.group === groupId && ev.day === day && ev.time === time) {
                    const partners = ev.partner.split(/[、,]/).map(s => s.trim());
                    partners.forEach(p => participantsSet.add(p));
                }
            }
        }
        existingParticipants = Array.from(participantsSet);
    }
    
    const allParticipants = [...new Set([...existingParticipants, ...newNames])];
    
    if (groupExpireInfo[groupId]) {
        groupExpireInfo[groupId].participants = allParticipants;
    } else {
        groupExpireInfo[groupId] = {
            acceptTime: Date.now(),
            expireTime: Date.now() + (parseInt(ext.storageGet("group_expire_hours") || "48") * 3600000),
            participants: allParticipants,
            subtype: "私密",
            day: day,
            time: time,
            place: place
        };
    }
    ext.storageSet("group_expire_info", JSON.stringify(groupExpireInfo));
    
    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    
    for (const [key, schedules] of Object.entries(b_confirmedSchedule)) {
        for (let ev of schedules) {
            if (ev.group === groupId && ev.day === day && ev.time === time) {
                const currentPartners = ev.partner.split(/[、,]/).map(s => s.trim());
                const newPartners = [...new Set([...currentPartners, ...newNames])];
                ev.partner = newPartners.join("、");
            }
        }
    }
    
    for (let newName of newNames) {
        const targetInfo = a_private_group[platform][newName];
        if (!targetInfo) continue;
        const targetUid = targetInfo[0];
        const targetKey = `${platform}:${targetUid}`;
        if (!b_confirmedSchedule[targetKey]) b_confirmedSchedule[targetKey] = [];
        
        const alreadyExists = b_confirmedSchedule[targetKey].some(ev => 
            ev.group === groupId && ev.day === day && ev.time === time
        );
        if (!alreadyExists) {
            b_confirmedSchedule[targetKey].push({
                day: day,
                time: time,
                partner: allParticipants.join("、"),
                subtype: "私密",
                place: place,
                group: groupId,
                status: "active"
            });
        }
    }
    ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    
    let groupTimers = JSON.parse(ext.storageGet("group_timers") || "{}");
    let timer = groupTimers[groupId];
    
    if (timer) {
        const now = Date.now();
        const isTwoPerson = timer.participants.length === 2;
        
        if (timer.timerMode === "turn_taking" && isTwoPerson) {
            timer.timerMode = "independent";
            for (let [role, status] of Object.entries(timer.timerStatus)) {
                if (status.status === "waiting") {
                    status.status = "timing";
                    status.startTime = now;
                    status.repliedTime = null;
                    status.wordCount = 0;
                    status.remindedTimes = 0;
                }
            }
        }
        
        for (let newName of newNames) {
            if (!timer.timerStatus[newName]) {
                timer.timerStatus[newName] = {
                    status: "timing",
                    startTime: now,
                    repliedTime: null,
                    wordCount: 0,
                    remindedTimes: 0,
                    isInitiator: false
                };
            }
        }
        
        timer.participants = allParticipants;
        groupTimers[groupId] = timer;
        ext.storageSet("group_timers", JSON.stringify(groupTimers));
    }
    
    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${groupId}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    const joinNotice = `🎉 欢迎新伙伴加入！\n\n${newNames.join("、")} 也选择了在 ${day} ${time} 前往【${place}】。\n现在你们可以一起进行这场约会啦！\n\n当前参与者：${allParticipants.join("、")}`;
    seal.replyToSender(groupCtx, groupMsg, joinNotice);
    
    for (let newName of newNames) {
        const targetInfo = a_private_group[platform][newName];
        if (targetInfo) {
            const targetGroupId = targetInfo[1];
            const targetUid = targetInfo[0];
            const privateMsg = seal.newMessage();
            privateMsg.messageType = "group";
            privateMsg.groupId = `${platform}-Group:${targetGroupId}`;
            privateMsg.sender = {};
            privateMsg.sender.userId = `${platform}:${targetUid}`;
            const privateCtx = seal.createTempCtx(ctx.endPoint, privateMsg);
            const notice = `✨ 你发起的私约已自动合并到现有约会中！\n\n📅 时间：${day} ${time}\n📍 地点：${place}\n👥 参与者：${allParticipants.join("、")}\n💬 群号：${groupId}\n\n请自行申请入群，享受约会时光~`;
            seal.replyToSender(privateCtx, privateMsg, notice);
        }
    }
    
    return true;
}

async function checkAppointmentPreflight(ctx, msg, cmdArgs, subtype, minDurationKey) {
    let config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    let enable_general_appointment = config.enable_general_appointment ?? true;
    if (!enable_general_appointment) {
        return { valid: false, errorMsg: "📅 当前已禁用通用发起邀约功能，无法发起" + (subtype === "电话" ? "电话" : "私密邀约") + "。" };
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    const sendname = Object.entries(a_private_group[platform]).find(([_, val]) => val[0] === uid)?.[0];
    if (!sendname) return { valid: false, errorMsg: "请先使用「创建新角色」绑定角色" };

    const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
    if (blockMap[sendname]?.enable_general_appointment === false) {
        return { valid: false, errorMsg: "🚫 您已被禁止使用发起邀约功能" };
    }

    const globalDay = ext.storageGet("global_days");
    if (!globalDay) return { valid: false, errorMsg: "⚠️ 当前尚未设置全局天数，请先使用 \".设置天数 D1\"" };
    const day = globalDay;

    const rawTime = cmdArgs.getArgN(1);
    const namesArg = subtype === "电话" ? cmdArgs.getArgN(2) : cmdArgs.getArgN(3);
    const placeOrTitle = subtype === "电话" ? cmdArgs.getArgN(3) : cmdArgs.getArgN(2); 
    if (!rawTime || !namesArg) {
        const exampleTime = getExampleTimeRange();
        let helpMsg = "";
        if (subtype === "电话") {
            helpMsg = `⚠️ 参数不足，正确格式：\n。电话 ${exampleTime} 邀请人1[/邀请人2/...] [标题]\n示例：\n。电话 ${exampleTime} 张三\n。电话 ${exampleTime} 李四/王五 一起聊聊`;
        } else {
            helpMsg = `⚠️ 参数不足，正确格式：\n。私约 ${exampleTime} 地点 对方角色名[/对方2/...]\n示例：\n。私约 ${exampleTime} 咖啡厅 张三\n。私约 ${exampleTime} 餐厅 李四/王五`;
        }
        return { valid: false, errorMsg: helpMsg };
    }

    const allowedRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
    const durationConfig = JSON.parse(ext.storageGet("appointment_duration_config") || "{}");
    const minDuration = durationConfig[minDurationKey] !== undefined ? durationConfig[minDurationKey] : (minDurationKey === "phone" ? 29 : 59);
    const timeRes = parseAndValidateTime(rawTime, allowedRanges, minDuration, subtype);
    if (!timeRes.valid) return { valid: false, errorMsg: timeRes.errorMsg };
    const time = timeRes.time;

    if (!checkRealityHourLimit(time, ctx, msg)) return { valid: false, errorMsg: "" }; 

    const names = namesArg.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
    const isMulti = names.length > 1;
    const fromKey = `${platform}:${uid}`;

    let a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
    const { selfLocked, failed: lockFailed } = checkLockedSlots(platform, day, time, fromKey, sendname, names, a_private_group, a_lockedSlots);
    if (selfLocked) return { valid: false, errorMsg: `⚠️ 你在 ${day} ${time} 段与锁定时间重叠，无法发起预约` };
    if (lockFailed.length) return { valid: false, errorMsg: `⚠️ 无法发起${subtype}，以下对象不符合条件：\n- ${lockFailed.join("\n- ")}` };

    if (subtype === "私密") {
        const placeCheck = checkPlaceCommon(platform, sendname, placeOrTitle, "私约");
        if (!placeCheck.valid) return { valid: false, errorMsg: placeCheck.errorMsg };
        if (placeCheck.warningMsg) seal.replyToSender(ctx, msg, placeCheck.warningMsg); 
    }

    if (!(await checkNoQuitBlocker(uid, ctx, msg))) {
        return { valid: false, errorMsg: "🚫 您仍有未退出的违规临时群，无法发起邀约" };
    }

    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");

    let conflict = false;
    if (b_confirmedSchedule[fromKey]) {
        b_confirmedSchedule[fromKey].forEach(ev => {
            const evSubtype = (ev.subtype || "").toLowerCase();
            if (["小群", "私密", "电话"].includes(evSubtype) && timeConflict(day, time, ev.day, ev.time)) {
                conflict = true;
            }
        });
    }
    if (conflict) return { valid: false, errorMsg: `⚠️ 你在 ${day} ${time} 时段已有安排，无法发起${subtype}~` };

    // 修改点：去除了待处理队列的检查，只检查硬冲突
    const conflictRes = checkParticipantConflicts(platform, day, time, sendname, names, a_private_group, b_confirmedSchedule);
    if (conflictRes.stop) return { valid: false, errorMsg: conflictRes.errorMsg };

    const autoMerge = (subtype === "私密") && (JSON.parse(ext.storageGet("auto_merge_duplicate_private") || "false"));
    let mergeTarget = null;
    let otherConflicts = [];

    if (conflictRes.existingAppointments) {
        for (let conflict of conflictRes.existingAppointments) {
            const isExactlySame = conflict.schedule.day === day &&
                                  conflict.schedule.time === time &&
                                  conflict.schedule.place === placeOrTitle &&
                                  conflict.schedule.group; 
            if (isExactlySame && autoMerge) {
                mergeTarget = conflict.schedule;
            } else {
                otherConflicts.push(conflict);
            }
        }
    }

    if (otherConflicts.length > 0) {
        const conflictNames = otherConflicts.map(e => e.name).join("、");
        return {
            valid: false,
            errorMsg: `⚠️ 以下角色在 ${day} ${time} 时段已有安排：${conflictNames}\n💡 你可以使用「。申请加入 角色名 时间点」尝试加入对方的预约。`
        };
    }

    return {
        valid: true,
        data: {
            platform, uid, sendname, day, time, names, isMulti,
            a_private_group, fromKey,
            place: subtype === "电话" ? "电话" : placeOrTitle,
            title: subtype === "电话" ? placeOrTitle || "" : "",
            b_confirmedSchedule,
            mergeTarget
        }
    };
}

// ========================
// 🚀 直接建群与通知（替换原有的待回应队列逻辑）
// ========================
async function directCreateAndFinalizeAppointment({
    ctx, msg, platform, sendname, sendid, subtype, day, time, place, names, title = "", isMulti, generateMessageFn
}) {
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 1. 下发系统提示信件（已自动接受版文案）
    for (let toname of names) {
        const toid = a_private_group[platform][toname][0];
        const newmsg = seal.newMessage();
        newmsg.messageType = "group";
        newmsg.sender = {};
        newmsg.sender.userId = `${platform}:${toid}`;
        newmsg.groupId = `${platform}-Group:${a_private_group[platform][toname][1]}`;
        const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
        
        const otherNames = isMulti ? names.filter(n => n !== toname) : [];
        const noticeText = generateMessageFn(sendname, place, day, time, isMulti, otherNames, toid);
        
        seal.replyToSender(newctx, newmsg, noticeText);
    }
    
    // 2. 直接构造已确认的数据体并调用 finalizeGroupCreation 建群
    if (isMulti) {
        const groupRef = generateGroupRef(); 
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
        // 全部置为已接受
        names.forEach(n => groupData.targetList[n] = "accepted");
        
        const participants = [sendname, ...names];
        await finalizeGroupCreation(platform, ctx, msg, groupData, participants);
    } else {
        const toname = names[0];
        const toid = a_private_group[platform][toname][0];
        const item = {
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
        
        const participants = [sendname, toname];
        await finalizeGroupCreation(platform, ctx, msg, item, participants);
    }
    
    return { success: true, isMulti, names };
}

// ========================
// 📞 电话指令（直接确认版）
// ========================
let cmd_phone = seal.ext.newCmdItemInfo();
cmd_phone.name = "电话";
cmd_phone.help = "。电话 1100-1200 邀请人1[/邀请人2/...] [标题]\n示例：\n。电话 1100-1200 张三\n。电话 1400-1500 李四/王五 一起聊聊";

function generatePhoneInvitationMessage(sendname, title, day, time, isMulti, otherNames, targetQQ) {
    let message = targetQQ ? `[CQ:at,qq=${targetQQ}]\n` : "";
    message += `📱 【电话邀约】${sendname} 邀请你\n`;
    message += `📅 ${day} ${time}`;
    if (isMulti && otherNames.length) {
        const peers = otherNames.length === 1 ? otherNames[0] : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
        message += `，另有 ${peers} 加入`;
    }
    if (title) message += `\n💬 ${title}`;
    message += `\n💌 群号见下方通知`;
    return message;
}

cmd_phone.solve = async (ctx, msg, cmdArgs) => {
    const pre = await checkAppointmentPreflight(ctx, msg, cmdArgs, "电话", "phone");
    if (!pre.valid) return seal.replyToSender(ctx, msg, pre.errorMsg), seal.ext.newCmdExecuteResult(true);
    const { platform, uid, sendname, day, time, names, isMulti, a_private_group, title } = pre.data;

    // 替换为直接确认函数
    await directCreateAndFinalizeAppointment({
        ctx, msg, platform, sendname, sendid: uid,
        subtype: "电话", day, time, place: "电话",
        names, isMulti, title,
        generateMessageFn: generatePhoneInvitationMessage
    });

    const successMsg = isMulti 
        ? `✅ 你已成功向 ${names.join("、")} 发起多人电话，通讯频段已自动建立！` 
        : `✅ 你已成功与 ${names[0]} 连线，通讯频段已自动建立！`;
    seal.replyToSender(ctx, msg, successMsg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["电话"] = cmd_phone;

function formatTime(date) {
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${hours}:${minutes}`;
}

// ========================
// 🤫 私约指令（直接确认版）
// ========================
let cmd_appointment_private = seal.ext.newCmdItemInfo();
cmd_appointment_private.name = "私约";
cmd_appointment_private.help = "。私约 1120-1230 地点 对方角色名[/对方2/...]\n示例：\n。私约 11:20-12:30 餐厅 张三\n。私约 1400-1500 咖啡厅 李四/王五";

function generatePrivateInvitationMessage(sendname, place, day, time, isMulti, otherNames, targetQQ) {
    let message = targetQQ ? `[CQ:at,qq=${targetQQ}]\n` : "";
    message += `💌 【私约邀请】${sendname} 邀请你\n`;
    message += `📅 ${day} ${time}  📍 ${place}`;
    if (isMulti && otherNames.length) {
        const peers = otherNames.length === 1 ? otherNames[0] : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
        message += `\n👥 另有 ${peers} 参与`;
    }
    message += `\n💌 群号见下方通知`;
    return message;
}

cmd_appointment_private.solve = async (ctx, msg, cmdArgs) => {
    const pre = await checkAppointmentPreflight(ctx, msg, cmdArgs, "私密", "private");
    if (!pre.valid) return seal.replyToSender(ctx, msg, pre.errorMsg), seal.ext.newCmdExecuteResult(true);

    if (pre.data.mergeTarget) {
        const newNames = pre.data.names; 
        const success = mergeIntoExistingAppointment(ctx, msg, pre.data.mergeTarget, newNames, pre.data);
        if (success) {
            const successMsg = `✅ 你发起的私约已自动合并到现有约会中！\n参与者：${pre.data.mergeTarget.partner}\n群号：${pre.data.mergeTarget.group}\n请自行申请入群~`;
            seal.replyToSender(ctx, msg, successMsg);
            return seal.ext.newCmdExecuteResult(true);
        } else {
            seal.replyToSender(ctx, msg, "❌ 自动合并失败，请稍后重试或联系管理员。");
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    const { platform, uid, sendname, day, time, names, isMulti, place, a_private_group } = pre.data;
    
    // 替换为直接确认函数
    await directCreateAndFinalizeAppointment({
        ctx, msg, platform, sendname, sendid: uid,
        subtype: "私密", day, time, place,
        names, isMulti,
        generateMessageFn: generatePrivateInvitationMessage
    });
    
    const successMsg = isMulti 
        ? `✅ 你已成功与 ${names.join("、")} 开启多方私约，私人空间已自动建立！` 
        : `✅ 你已成功与 ${names[0]} 开启私约，私人空间已自动建立！`;
    seal.replyToSender(ctx, msg, successMsg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["私约"] = cmd_appointment_private;


let cmd_view_schedule = seal.ext.newCmdItemInfo();
cmd_view_schedule.name = "时间线";
cmd_view_schedule.solve = (ctx, msg) => {
    const platform = msg.platform, uid = msg.sender.userId, roleId = uid.replace(`${platform}:`, "");
    const storage = (k) => JSON.parse(ext.storageGet(k) || "{}");
    const schedule = storage("b_confirmedSchedule"), multiReq = storage("b_MultiGroupRequest");
    const privGroup = storage("a_private_group"), timers = storage("group_timers");
    
    const myName = Object.keys(privGroup[platform] || {}).find(n => privGroup[platform][n][0] === roleId);
    if (!myName) return seal.replyToSender(ctx, msg, "请先绑定角色");

    // 1. 聚合日程与微信群
    let events = (schedule[uid] || []).map(e => ({...e}));
    
    // 注入多人预约
    Object.entries(multiReq).forEach(([ref, g]) => {
        const isRecip = g.targetList?.[myName] === "accepted", isSend = g.sendid === roleId;
        if ((isRecip || isSend) && !events.some(e => e.day === g.day && e.time === g.time)) {
            const partners = isSend ? [...new Set([g.sendname, ...Object.keys(g.targetList || {}).filter(n => g.targetList[n] !== "rejected")])] : [g.sendname];
            events.push({ day: g.day, time: g.time, subtype: g.subtype, place: g.place, partner: partners.join("、"), status: "pending", isMulti: true, multiRef: ref });
        }
    });

    // 排序并格式化
    events.sort((a, b) => parseInt(a.day.slice(1)) - parseInt(b.day.slice(1)) || a.time.localeCompare(b.time));

    const wechat = Object.values(storage("wechat_groups")[platform] || {})
        .filter(g => g.status === "active" && g.participants.includes(myName))
        .map(g => ({ day: "微信群", time: "长期", subtype: "微信群", place: g.topic, partner: g.participants.join("、"), status: "active", isWechat: true }));

    const allEvents = [...events, ...wechat];
    if (!allEvents.length) return seal.replyToSender(ctx, msg, "✨ 【日程表】\n\n当前暂无行程安排。");

    // 2. 构造显示文本
    allEvents.forEach(ev => {
        const isPending = ev.status === "pending", isEnded = ev.status === "ended";
        let tag = "";
        if (ev.isWechat) tag = "长期活跃";
        else {
            const timer = ev.group ? timers[ev.group]?.timerStatus?.[myName]?.status : null;
            tag = isEnded ? "已完结" : (isPending ? "待开启" : "进行中") + 
                  (timer === "replied" ? " [已回]" : (timer === "timing" ? " [⏳未回]" : ""));
            if (isPending && ev.isMulti && multiReq[ev.multiRef]?.targetList?.[myName] === "accepted") tag += " [🤝已接]";
        }
        const icon = { "电话": "📞", "续杯": "🍷", "微信群": "💬" }[ev.subtype] || "🎭";
        ev.displayText = `【${ev.day} ${ev.time}】\n${icon} ${ev.subtype} · ${tag}\n📍 地点：${ev.place || "未知"}\n👥 伙伴：${ev.partner}`;
    });

    if (!msg.groupId) return seal.replyToSender(ctx, msg, "请在群内使用合并转发。");
    
    // 3. 构造合并转发节点
    const botUid = ctx.endPoint.userId, nodes = [];
    let curDay = "";

    allEvents.forEach(ev => {
        if (ev.day !== curDay) {
            nodes.push({ type: "node", data: { name: "📅 日程管家", uin: botUid, content: ev.isWechat ? "💬 我的微信群" : `✨ ==== ${ev.day} 的日程 ==== ✨` } });
            curDay = ev.day;
        }
        const pUid = privGroup[platform]?.[ev.partner.split(/[、,]/)[0]]?.[0] || botUid;
        nodes.push({ type: "node", data: { name: ev.partner.split(/[、,]/)[0] || "助手", uin: pUid, content: ev.displayText } });
    });

    nodes.unshift({ type: "node", data: { name: "时间线档案", uin: botUid, content: `📅 共 ${events.length} 条日程，${wechat.length} 个群组` } });

    ws({ action: "send_group_forward_msg", params: { group_id: parseInt(msg.groupId.replace(/[^\d]/g, ""), 10), messages: nodes } }, ctx, msg, "");
};
ext.cmdMap["时间线"] = cmd_view_schedule;


// ========================
// 📥 手动加入请求指令
// ========================
let cmd_apply_join = seal.ext.newCmdItemInfo();
cmd_apply_join.name = "申请加入";
cmd_apply_join.help = "。申请加入 角色名 时间点\n功能：向已有约会的角色申请加入其当前时段内的私约或电话。\n示例：\n。申请加入 张三 14:30\n。申请加入 李四 1430";

cmd_apply_join.solve = async (ctx, msg, cmdArgs) => {

    const enableJoin = ext.storageGet("enable_join_existing_appointment");
    if (!enableJoin) {
        return seal.replyToSender(ctx, msg, "🚫 当前未启用「加入私约」功能。");
    }

    // 1. 获取参数
    const targetName = cmdArgs.getArgN(1);
    const rawTime = cmdArgs.getArgN(2);
    if (!targetName || !rawTime) {
        return seal.replyToSender(ctx, msg, "⚠️ 参数不足，正确格式：。申请加入 角色名 时间点\n示例：。申请加入 张三 14:30");
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    // 2. 获取发起人角色名
    const sendname = Object.entries(a_private_group[platform]).find(([_, val]) => val[0] === uid)?.[0];
    if (!sendname) return seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");

    // 3. 全局天数
    const globalDay = ext.storageGet("global_days");
    if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 当前尚未设置全局天数，请先使用 \".设置天数 D1\"");

    // 4. 验证目标角色是否存在
    const targetInfo = a_private_group[platform][targetName];
    if (!targetInfo) {
        return seal.replyToSender(ctx, msg, `❌ 角色「${targetName}」未注册，无法发起加入请求。`);
    }
    const targetUid = targetInfo[0];
    const targetGroupId = targetInfo[1];  // 用于通知的个人群

    // 5. 解析时间点（支持 HH:MM 或 HHMM）
    let pointTime = rawTime;
    if (/^\d{4}$/.test(rawTime)) {
        pointTime = `${rawTime.slice(0, 2)}:${rawTime.slice(2, 4)}`;
    } else if (!/^\d{2}:\d{2}$/.test(rawTime)) {
        return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用 HH:MM 或 HHMM（如 14:30 或 1430）");
    }

    // 6. 获取目标角色的已确认日程
    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    const targetKey = `${platform}:${targetUid}`;
    const targetSchedules = b_confirmedSchedule[targetKey] || [];

    // 7. 查找包含该时间点的预约（精确到天，且时间范围包含该时间点）
    const matchingSchedule = targetSchedules.find(schedule => {
        if (schedule.day !== globalDay) return false;
        const [startStr, endStr] = schedule.time.split('-');
        const pointMinutes = timeToMinutes(pointTime);
        const startMinutes = timeToMinutes(startStr);
        const endMinutes = timeToMinutes(endStr);
        return pointMinutes >= startMinutes && pointMinutes <= endMinutes;
    });

    if (!matchingSchedule) {
        return seal.replyToSender(ctx, msg, `❌ 未找到「${targetName}」在 ${globalDay} ${pointTime} 附近的有效预约。`);
    }

    // 8. 检查发起人是否已经是该预约的参与者
    if (matchingSchedule.partner && matchingSchedule.partner.includes(sendname)) {
        return seal.replyToSender(ctx, msg, `⚠️ 你已经在「${targetName}」的该时段预约中，无需重复加入。`);
    }

    // 9. 检查发起人自身在该时段是否有冲突（复用冲突检测）
    const fromKey = `${platform}:${uid}`;
    const fromSchedules = b_confirmedSchedule[fromKey] || [];
    const hasConflict = fromSchedules.some(s => timeConflict(globalDay, matchingSchedule.time, s.day, s.time));
    if (hasConflict) {
        return seal.replyToSender(ctx, msg, `⚠️ 你在 ${globalDay} ${matchingSchedule.time} 已有其他安排，无法加入该预约。`);
    }

    // 10. 检查锁定时间冲突（复用锁定检查）
    let a_lockedSlots = JSON.parse(ext.storageGet("a_lockedSlots") || "{}");
    const fromLocked = a_lockedSlots[fromKey]?.[globalDay] || [];
    if (fromLocked.some(lockedTime => timeOverlap(matchingSchedule.time, lockedTime))) {
        return seal.replyToSender(ctx, msg, `⚠️ 你在 ${globalDay} ${matchingSchedule.time} 时段被锁定，无法加入。`);
    }

    // 11. 检查是否已有待处理的加入请求（避免重复）
    let joinRequests = JSON.parse(ext.storageGet("join_request_list") || "[]");
    const existingPending = joinRequests.some(req =>
        req.from === sendname &&
        req.to === targetName &&
        req.day === globalDay &&
        req.time === matchingSchedule.time &&
        req.status === "pending"
    );
    if (existingPending) {
        return seal.replyToSender(ctx, msg, `⏳ 你已经向「${targetName}」发起了针对该时段的加入请求，请等待对方处理。`);
    }

    // 12. 创建加入请求
    const requestId = Math.random().toString(36).substring(2, 8);
    const joinRequest = {
        id: requestId,
        type: "join",
        from: sendname,
        fromUid: uid,
        to: targetName,
        toUid: targetUid,
        day: globalDay,
        time: matchingSchedule.time,
        place: matchingSchedule.place || "电话",
        targetGroupId: matchingSchedule.group,   // 已有预约所在的群号
        targetSchedule: matchingSchedule,        // 完整日程对象
        status: "pending",
        timestamp: Date.now()
    };
    joinRequests.push(joinRequest);
    ext.storageSet("join_request_list", JSON.stringify(joinRequests));

    // 13. 通知目标角色（发送到其个人群）
    if (targetGroupId) {
        const notifyMsg = seal.newMessage();
        notifyMsg.messageType = "group";
        notifyMsg.groupId = `${platform}-Group:${targetGroupId}`;
        notifyMsg.sender = {};
        notifyMsg.sender.userId = `${platform}:${targetUid}`;
        const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
        const notice = `📢 加入请求\n\n${sendname} 想加入你正在进行的预约：\n📅 ${globalDay} ${matchingSchedule.time}\n📍 ${matchingSchedule.place || "电话"}\n\n请使用「加入请求」查看详情，然后输入「同意加入 编号」或「拒绝加入 编号」。`;
        seal.replyToSender(notifyCtx, notifyMsg, notice);
    }

    // 14. 回复发起人
    seal.replyToSender(ctx, msg, `✨ 已向「${targetName}」发送加入请求，请等待对方回应。`);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["申请加入"] = cmd_apply_join;

// ========================
// 辅助函数（若尚未定义）
// ========================
function timeToMinutes(timeStr) {
    const [h, m] = timeStr.split(':').map(Number);
    return h * 60 + m;
}

let cmd_join_requests = seal.ext.newCmdItemInfo();
cmd_join_requests.name = "加入请求";
cmd_join_requests.help = "。加入请求 —— 查看你收到的加入现有私约的请求";
cmd_join_requests.solve = (ctx, msg, cmdArgs) => {
    const uid = msg.sender.userId;
    const platform = msg.platform;
    const pureUid = uid.replace(`${platform}:`, "");
    const joinRequests = JSON.parse(ext.storageGet("join_request_list") || "[]");
    const myRequests = joinRequests.filter(req => req.toUid === pureUid && req.status === "pending");
    
    if (myRequests.length === 0) {
        seal.replyToSender(ctx, msg, "📭 当前没有待处理的加入请求。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    let rep = "📥 加入请求列表：\n\n";
    myRequests.forEach((req, idx) => {
        rep += `【编号 ${idx + 1}】\n`;
        rep += `发起人：${req.from}\n`;
        rep += `时间：${req.day} ${req.time}\n`;
        rep += `地点：${req.place}\n`;
        rep += `目标群：${req.targetGroupId}\n`;
        rep += `请求ID：${req.id}\n\n`;
    });
    rep += "💡 使用「同意加入 编号」或「拒绝加入 编号」处理。";
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["加入请求"] = cmd_join_requests;

let cmd_accept_join = seal.ext.newCmdItemInfo();
cmd_accept_join.name = "同意加入";
cmd_accept_join.help = "。同意加入 编号 —— 同意对方加入你当前的私约";
cmd_accept_join.solve = (ctx, msg, cmdArgs) => {

    const enableJoin = ext.storageGet("enable_join_existing_appointment");
    if (!enableJoin) {
        return seal.replyToSender(ctx, msg, "🚫 当前未启用「加入私约」功能。");
    }

    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    const uid = msg.sender.userId;
    const platform = msg.platform;
    const pureUid = uid.replace(`${platform}:`, "");
    
    let joinRequests = JSON.parse(ext.storageGet("join_request_list") || "[]");
    const myPending = joinRequests.filter(req => req.toUid === pureUid && req.status === "pending");
    if (isNaN(idx) || idx < 0 || idx >= myPending.length) {
        return seal.replyToSender(ctx, msg, "❌ 无效的编号，请使用「加入请求」查看。");
    }
    const request = myPending[idx];
    const fullRequest = joinRequests.find(r => r.id === request.id);
    if (!fullRequest) return seal.replyToSender(ctx, msg, "❌ 请求不存在或已过期。");
    
    // 更新请求状态
    fullRequest.status = "accepted";
    ext.storageSet("join_request_list", JSON.stringify(joinRequests));
    
    // 获取发起人信息
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const fromInfo = a_private_group[platform]?.[fullRequest.from];
    if (!fromInfo) {
        seal.replyToSender(ctx, msg, `⚠️ 无法找到发起人「${fullRequest.from}」的信息。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const fromUid = fromInfo[0];
    const targetGroupId = fullRequest.targetGroupId;
    
    // 更新日程
    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    const fromKey = `${platform}:${fromUid}`;
    const targetSchedule = fullRequest.targetSchedule;
    const groupId = targetSchedule.group;
    const day = targetSchedule.day;
    const time = targetSchedule.time;
    
    // 1. 找到所有与这个群组、时间、地点相关的参与者记录
    const relatedEntries = [];
    for (const [key, scheduleList] of Object.entries(b_confirmedSchedule)) {
        for (let ev of scheduleList) {
            if (ev.group === groupId && ev.day === day && ev.time === time) {
                relatedEntries.push({ key, ev });
            }
        }
    }
    
    // 2. 为每个现有参与者更新 partner（追加新成员）
    const newPartnerSuffix = "、" + fullRequest.from;
    for (let entry of relatedEntries) {
        if (!entry.ev.partner.includes(fullRequest.from)) {
            entry.ev.partner += newPartnerSuffix;
        }
    }
    
    // 3. 为新成员创建日程记录
    let basePartner = relatedEntries.length > 0 ? relatedEntries[0].ev.partner : targetSchedule.partner;
    if (!basePartner.includes(fullRequest.from)) {
        basePartner += newPartnerSuffix;
    }
    const newSchedule = { ...targetSchedule };
    newSchedule.partner = basePartner;
    if (!b_confirmedSchedule[fromKey]) b_confirmedSchedule[fromKey] = [];
    b_confirmedSchedule[fromKey].push(newSchedule);
    
    // 保存修改
    ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    
    // 在群内发送通知
    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${targetGroupId}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    seal.replyToSender(groupCtx, groupMsg, `✨ ${fullRequest.from} 已经到来，正在加入你们的约会。`);
    
    // 通知发起人（发送群号）
    const fromGroupId = fromInfo[1];
    if (fromGroupId) {
        const fromMsg = seal.newMessage();
        fromMsg.messageType = "group";
        fromMsg.groupId = `${platform}-Group:${fromGroupId}`;
        fromMsg.sender = {};
        fromMsg.sender.userId = `${platform}:${fromUid}`;
        const fromCtx = seal.createTempCtx(ctx.endPoint, fromMsg);
        seal.replyToSender(fromCtx, fromMsg, `✅ 你已成功加入 ${fullRequest.to} 的私约，群号：${targetGroupId}\n请自行申请入群。`);
    }
    
    seal.replyToSender(ctx, msg, `✅ 已同意 ${fullRequest.from} 加入你的私约。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同意加入"] = cmd_accept_join;

let cmd_reject_join = seal.ext.newCmdItemInfo();
cmd_reject_join.name = "拒绝加入";
cmd_reject_join.help = "。拒绝加入 编号 —— 拒绝对方加入你当前的私约";
cmd_reject_join.solve = (ctx, msg, cmdArgs) => {
    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    const uid = msg.sender.userId;
    const platform = msg.platform;
    const pureUid = uid.replace(`${platform}:`, "");
    
    let joinRequests = JSON.parse(ext.storageGet("join_request_list") || "[]");
    const myPending = joinRequests.filter(req => req.toUid === pureUid && req.status === "pending");
    if (isNaN(idx) || idx < 0 || idx >= myPending.length) {
        return seal.replyToSender(ctx, msg, "❌ 无效的编号，请使用「加入请求」查看。");
    }
    const request = myPending[idx];
    const fullRequest = joinRequests.find(r => r.id === request.id);
    if (!fullRequest) return seal.replyToSender(ctx, msg, "❌ 请求不存在或已过期。");
    
    fullRequest.status = "rejected";
    ext.storageSet("join_request_list", JSON.stringify(joinRequests));
    
    // 通知发起人
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const fromInfo = a_private_group[platform]?.[fullRequest.from];
    if (fromInfo) {
        const fromGroupId = fromInfo[1];
        if (fromGroupId) {
            const fromMsg = seal.newMessage();
            fromMsg.messageType = "group";
            fromMsg.groupId = `${platform}-Group:${fromGroupId}`;
            fromMsg.sender = {};
            fromMsg.sender.userId = `${platform}:${fromInfo[0]}`;
            const fromCtx = seal.createTempCtx(ctx.endPoint, fromMsg);
            seal.replyToSender(fromCtx, fromMsg, `❌ ${fullRequest.to} 拒绝了你的加入请求。`);
        }
    }
    
    seal.replyToSender(ctx, msg, `✅ 已拒绝 ${fullRequest.from} 的加入请求。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拒绝加入"] = cmd_reject_join;

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
// 🎁 礼物系统
// ========================
async function handleNaturalGift(ctx, msg, platform, toname, giftInput, customSenderName = null) {
    // 1. 功能开关检查
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (!(config.enable_general_gift ?? true)) {
        return seal.replyToSender(ctx, msg, "🎁 礼物功能已被禁用。");
    }

    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 2. 身份识别
    const autoSendname = Object.keys(a_private_group[platform] || {}).find(
        key => a_private_group[platform][key][0] === uid
    );
    if (!autoSendname) {
        return seal.replyToSender(ctx, msg, `❌ 请先创建新角色再使用该功能`);
    }
    const allowCustomSign = ext.storageGet("allow_custom_letter_sign") === "true";
    const sendname = allowCustomSign && customSenderName ? customSenderName : autoSendname;

    // 违规检查
    if (!(await checkNoQuitBlocker(uid, ctx, msg))) return;

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
    const cooldownMin = parseInt(ext.storageGet("giftCooldown") || "30");
    
    let globalStats = JSON.parse(ext.storageGet("global_gift_stats") || "{}");
    let globalCooldowns = JSON.parse(ext.storageGet("global_gift_cooldowns") || "{}");
    const userKey = `${platform}:${uid}`;
    const now = Date.now();

    const lastSent = globalCooldowns[userKey] || 0;
    if (now - lastSent < cooldownMin * 60 * 1000) {
        const rem = Math.ceil((cooldownMin * 60 * 1000 - (now - lastSent)) / 1000);
        return seal.replyToSender(ctx, msg, `⏳ 快递员仍在路上，请等待 ${rem} 秒后再送~`);
    }

    let userStat = globalStats[userKey] || { day: gameDay, count: 0 };
    if (userStat.day !== gameDay) userStat = { day: gameDay, count: 0 };
    if (userStat.count >= dailyLimit) {
        return seal.replyToSender(ctx, msg, `🎁 今日送礼次数已达上限(${dailyLimit})。`);
    }

    // 模式检查
    const giftMode = parseInt(ext.storageGet("giftMode") || "0");
    if (giftMode === 1 && !giftInput.startsWith('#')) {
        return seal.replyToSender(ctx, msg, "❌ 当前仅允许使用预设礼物（以 # 开头）");
    }

    // 5. 礼物内容解析
    let giftDisplayName = "";
    let giftContent = giftInput;

    if (giftInput.startsWith('#')) {
        const shopMode = ext.storageGet("shop_mode") || "抽卡";
        let presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
        const giftData = presetGifts[giftInput];
        if (!giftData) return seal.replyToSender(ctx, msg, `❌ 预设礼物 ${giftInput} 不存在`);

        if (shopMode === "商城") {
            // 商城模式：消耗背包里的一件
            const myInvKey = `${platform}:${autoSendname}`;
            const invs = store.get("global_inventories");
            const myInv = invs[myInvKey] || [];
            const backpackIdx = myInv.findIndex(i => i.giftId === giftInput && !i.used);
            if (backpackIdx === -1) {
                return seal.replyToSender(ctx, msg, `❌ 背包里没有「${giftData.name}」，请先在礼物商城购买。`);
            }
            if ((myInv[backpackIdx].count || 1) > 1) {
                myInv[backpackIdx].count -= 1;
            } else {
                myInv.splice(backpackIdx, 1);
            }
            invs[myInvKey] = myInv;
            store.set("global_inventories", invs);
        } else {
            // 抽卡模式：检查图鉴，可无限赠送
            const sightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
            const uid_clean = msg.sender.userId.replace(/^[a-z]+:/i, "");
            const userKey = `${platform}:${uid_clean}`;
            const owned = sightings[userKey]?.unlocked_gifts || [];
            if (!owned.includes(giftInput)) {
                return seal.replyToSender(ctx, msg, `🔒 「${giftData.name}」不在图鉴中，请先发送「礼物商城」收集。`);
            }
        }

        giftDisplayName = `「${giftData.name}」`;
        giftContent = giftData.content;
        presetGifts[giftInput].usage_count = (presetGifts[giftInput].usage_count || 0) + 1;
        ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
    } else {
        giftDisplayName = "一份特别的礼物";
        giftContent = giftInput;
    }

    // 6. 投递（不写入收件人背包/图鉴，仅发送通知消息）
    const targetEntry = a_private_group[platform][toname];
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    const targetQQ = targetEntry[0];
    const recipientMsg = `[CQ:at,qq=${targetQQ}]\n🎀 ${toname}，有一份来自「${sendname}」的快递：\n礼物：${giftDisplayName}\n寄语：「${giftContent}」`;
    seal.replyToSender(newctx, newmsg, recipientMsg);

    // 7. 更新数据
    userStat.count += 1;
    globalStats[userKey] = userStat;
    globalCooldowns[userKey] = now;
    ext.storageSet("global_gift_stats", JSON.stringify(globalStats));
    ext.storageSet("global_gift_cooldowns", JSON.stringify(globalCooldowns));

    seal.replyToSender(ctx, msg, `🎁 已成功将 ${giftDisplayName} 送往「${toname}」的房间。\n(今日第 ${userStat.count}份)`);

    // 8. 公开广播逻辑 (保持原样)
    const publicGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
    const giftPublicEnabled = JSON.parse(ext.storageGet("gift_public_send") || "false");
    if (giftPublicEnabled && publicGroupId) {
        const publicChance = parseInt(ext.storageGet("giftPublicChance") || "50", 10);
        if ((Math.floor(Math.random() * 100) + 1) <= publicChance) {
            const pubMsg = seal.newMessage();
            pubMsg.messageType = "group";
            pubMsg.groupId = `${platform}-Group:${publicGroupId}`;
            const pubCtx = seal.createTempCtx(ctx.endPoint, pubMsg);
            const publicNotice = `🎁 公告：来自「${sendname}」送给「${toname}」的礼物：${giftDisplayName}\n寄语：「${giftContent}」`;
            seal.replyToSender(pubCtx, pubMsg, publicNotice);
        }
    }
    
    recordMeetingAndAnnounce("礼物", platform, ctx, ctx.endPoint);
}

// ========================
// 🏠 群组生命周期管理
// ========================

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
cmd_grouplist_release.help = "。结束私约（将当前群标记为结束状态，禁止当前阶段续杯）。若当前群为微信群，则结束微信群并释放群号。";

/**
 * 结束微信群（仅清理状态，不发公告）
 */
function endWechatGroup(ctx, msg, gid, platform, uid) {
    const groupList = JSON.parse(ext.storageGet("group") || "[]");
    if (!groupList.includes(gid + "_微信占用")) {
        seal.replyToSender(ctx, msg, "⚠️ 当前群不是微信群，无法结束");
        return false;
    }

    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    const groupInfo = wechatGroups[platform]?.[gid];
    if (!groupInfo) {
        seal.replyToSender(ctx, msg, "⚠️ 微信群信息不存在或已失效");
        return false;
    }

    // 获取操作者角色名（仅用于记录）
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
        groupList.push(gid);
        ext.storageSet("group", JSON.stringify(groupList));
    }

    // 修改群名为“备用”
    setGroupName(ctx, msg, gid, "备用");

    // 仅向操作者反馈
    seal.replyToSender(ctx, msg, `✅ 微信群 ${gid} 已结束，群号已释放。`);
    return true;
}

cmd_grouplist_release.solve = (ctx, msg, cmdArgs) => {
    let group = JSON.parse(ext.storageGet("group") || "[]");
    let platform = msg.platform;
    let gid = msg.groupId.replace(`${platform}-Group:`, "");
    const uid = msg.sender.userId.replace(`${platform}:`, "");

    // 判断是否为微信群（以 "_微信占用" 结尾）
    if (group.includes(gid + "_微信占用")) {
        endWechatGroup(ctx, msg, gid, platform, uid);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 非微信群：原有结束逻辑
    const fullId = `${gid}_占用`;
    if (group.includes(fullId)) {
        // ----- 读取“复盘强制结束”开关 -----
        const requireFupan = JSON.parse(ext.storageGet("require_fupan_before_end") || "true");
        if (requireFupan) {
            // ----- 复盘检查（参照更新 status 的遍历方式）-----
            const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
            let needFupan = false;  // 是否需要复盘（存在未复盘的活跃记录）

            for (let uidKey in b_confirmedSchedule) {
                for (let ev of b_confirmedSchedule[uidKey]) {
                    if (ev.group === gid && ev.status === "active") {
                        // 如果该活跃记录没有 fupan 字段或 fupan !== true，则要求复盘
                        if (!ev.fupan) {
                            needFupan = true;
                            break;
                        }
                    }
                }
                if (needFupan) break;
            }

            if (needFupan) {
                seal.replyToSender(ctx, msg, `⚠️ 请先完成当前小群的复盘（合并记录并在回复该合并记录“转发复盘”指令），然后再结束私约。`);
                return seal.ext.newCmdExecuteResult(true);
            }
        }
        // 如果开关关闭，直接跳过复盘检查，继续结束流程

        // ----- 复盘检查通过（或已关闭），继续原有结束逻辑 -----
        // 将占用状态移除，使该群可复用
        group.splice(group.indexOf(fullId), 1);
        group.push(gid);
        ext.storageSet("group", JSON.stringify(group));

        // 更新 b_confirmedSchedule 中所有 status 为 ended
        let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
        let modified = false;
        let matchCount = 0;
        for (let uidKey in b_confirmedSchedule) {
            for (let ev of b_confirmedSchedule[uidKey]) {
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

        // 清除到期记录
        let groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
        if (groupExpireInfo[gid]) {
            delete groupExpireInfo[gid];
            ext.storageSet("group_expire_info", JSON.stringify(groupExpireInfo));
            console.log(`[DEBUG] 已清除群组 ${gid} 的到期记录`);
        }

        console.log(`[DEBUG] ${gid} 标记为 ended，更新 ${matchCount} 条记录`);
        seal.replyToSender(ctx, msg, `✅ 本群（${gid}）本轮小群已结束，可再次发起新小群，所有相关记录已标记"已结束"`);
        setGroupName(ctx, msg, ctx.group.groupId, `备用`);
        cleanupGroupTimer(gid);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ 当前群号未处于占用状态，无法结束`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束私约"] = cmd_grouplist_release;

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

/**
 * 检查指定群号中是否有非NPC的已绑定角色（异步，返回 Promise）
 * @param {string} platform - 平台标识
 * @param {string} gid - 群号（纯数字字符串）
 * @param {Object} ctx - 上下文
 * @param {Object} msg - 原始消息对象
 * @returns {Promise<boolean>} - true: 有非NPC玩家, false: 无
 */
async function checkGroupHasNonNPC(platform, gid, ctx, msg) {
    const members = await getGroupMembersSilent(gid, ctx, msg);
    console.log(`[checkGroupHasNonNPC] 群 ${gid} 获取到成员数: ${members.length}`);
    
    const roleStorage = getRoleStorage();
    const platformRoles = roleStorage[platform] || {};
    const npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");
    
    // --- 1. 读取 noquit 存储 ---
    // 结构预期: { "12345": ["10001", "10002"], "789012": ["10001"] }
    const noquitRecord = JSON.parse(ext.storageGet("noquit") || "{}");
    let needSave = false;

    // 构建 QQ -> 角色信息的映射
    const qqToRole = {};
    for (let [roleName, info] of Object.entries(platformRoles)) {
        const qq = info[0];
        if (qq) qqToRole[qq] = { name: roleName, isNPC: npcList.includes(roleName) };
    }

    let hasNonNPC = false;
    for (let member of members) {
        const qq = member.user_id.toString();
        const role = qqToRole[qq];
        
        if (role && !role.isNPC) {
            hasNonNPC = true;
            // 向该玩家发送提醒（通过其绑定的私群）
            const groupId = platformRoles[role.name]?.[1];
            if (groupId) {
                const remindMsg = seal.newMessage();
                remindMsg.messageType = "group";
                remindMsg.groupId = `${platform}-Group:${groupId}`;
                const remindCtx = seal.createTempCtx(ctx.endPoint, remindMsg);
                const atCq = `[CQ:at,qq=${qq}]`;
                seal.replyToSender(remindCtx, remindMsg,
                    `${atCq} ⚠️ 系统检测到群 ${gid} 将用于私密邀约/心愿等自动建群，请尽快退出，否则可能影响后续流程。`);
                
                // --- 2. 累积记录未退出的群 (数组模式) ---
                
                // 如果该用户还没有记录，初始化为空数组
                if (!noquitRecord[qq]) {
                    noquitRecord[qq] = [];
                }
                
                // 如果数组中还没有这个群号，则加入（避免重复记录）
                if (!noquitRecord[qq].includes(gid)) {
                    noquitRecord[qq].push(gid);
                    needSave = true;
                    console.log(`[NoQuit] 记录玩家 ${qq} 在群 ${gid} 未退出 (累计群数: ${noquitRecord[qq].length})`);
                }
            }
        }
    }
    
    // --- 3. 如果有变动，写入存储 ---
    if (needSave) {
        ext.storageSet("noquit", JSON.stringify(noquitRecord));
    }

    console.log(`[checkGroupHasNonNPC] 有非NPC玩家: ${hasNonNPC}`);
    return hasNonNPC;
}

/**
 * 分配一个未被占用且群成员中没有非NPC玩家的群号（异步）
 * @param {string} platform - 平台标识
 * @param {Object} ctx - 上下文
 * @param {Object} msg - 原始消息对象
 * @returns {Promise<string|null>} - 分配的群号，若无可用则返回 null
 */
async function allocateGroup(platform, ctx, msg) {
    let groupList = JSON.parse(ext.storageGet("group") || "[]");
    let freeGroups = groupList.filter(g => !g.endsWith("_占用"));  // 只过滤占用，不过滤 blocked
    if (freeGroups.length === 0) return null;

    // 随机打乱顺序
    for (let i = freeGroups.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [freeGroups[i], freeGroups[j]] = [freeGroups[j], freeGroups[i]];
    }

    for (let gid of freeGroups) {
        const hasNonNPC = await checkGroupHasNonNPC(platform, gid, ctx, msg);
        if (!hasNonNPC) {
            // 该群可用，标记为占用
            const newGroupList = groupList.map(g => g === gid ? gid + "_占用" : g);
            ext.storageSet("group", JSON.stringify(newGroupList));
            return gid;
        }
        // 有非NPC玩家，跳过该群，不标记 _blocked，继续尝试下一个
    }
    return null; // 所有群都不可用
}

/**
 * 校验并清理 noquit 记录（增强版：增加 NPC 身份自动赦免）
 * @param {string} qq - 玩家QQ号
 * @param {Object} ctx - 上下文
 * @param {Object} msg - 消息对象
 * @returns {Promise<boolean>} - true: 干净/已退出/已转为NPC, false: 仍卡在群里
 */
async function validateAndCleanNoQuit(qq, ctx, msg) {
    const noquitRecord = JSON.parse(ext.storageGet("noquit") || "{}");
    
    // 1. 如果该玩家本来就没有记录，直接放行
    if (!noquitRecord[qq] || noquitRecord[qq].length === 0) {
        return true;
    }

    // --- 核心优化：NPC 身份检查 ---
    const platform = msg.platform;
    const roleStorage = getRoleStorage();
    const platformRoles = roleStorage[platform] || {};
    const npcList = JSON.parse(ext.storageGet("a_npc_list") || "[]");

    // 找到该 QQ 绑定的角色名
    const roleName = Object.keys(platformRoles).find(name => platformRoles[name][0] === qq);

    // 如果该角色现在被标记为了 NPC，直接清空其违规记录并放行
    if (roleName && npcList.includes(roleName)) {
        console.log(`[NoQuit] 检测到玩家 ${roleName}(${qq}) 已转为 NPC，自动清空违规记录。`);
        delete noquitRecord[qq];
        ext.storageSet("noquit", JSON.stringify(noquitRecord));
        return true;
    }
    // ----------------------------

    const stillInGroups = []; // 记录玩家仍然在里面的群号

    // 2. 正常的退群校验逻辑
    for (let gid of noquitRecord[qq]) {
        try {
            const members = await getGroupMembersSilent(gid, ctx, msg);
            const isMember = members.some(m => m.user_id.toString() === qq);
            if (isMember) {
                stillInGroups.push(gid);
            }
        } catch (e) {
            // 获取失败视为已退出
        }
    }

    // 3. 更新存储
    if (stillInGroups.length === 0) {
        delete noquitRecord[qq];
        ext.storageSet("noquit", JSON.stringify(noquitRecord));
        return true; 
    } else if (stillInGroups.length < noquitRecord[qq].length) {
        noquitRecord[qq] = stillInGroups;
        ext.storageSet("noquit", JSON.stringify(noquitRecord));
        return false;
    }
    
    return false;
}

/**
 * 封装的 NoQuit 检查拦截器
 * 如果玩家还在违规群中，直接回复并阻止操作
 * @param {string} qq - 玩家ID
 * @param {Object} ctx - 上下文
 * @param {Object} msg - 消息对象
 * @returns {Promise<boolean>} - true: 放行, false: 已拦截
 */
async function checkNoQuitBlocker(qq, ctx, msg) {
    const isClean = await validateAndCleanNoQuit(qq, ctx, msg);
    if (!isClean) {
        seal.replyToSender(ctx, msg, `🚫 检测到您仍有未退出的临时房间，请退出后再试。`);
        return false;
    }
    return true;
}

let cmd_fix_noquit = seal.ext.newCmdItemInfo();
cmd_fix_noquit.name = "更新未退群";
cmd_fix_noquit.solve = async (ctx, msg, cmdArgs) => {
    seal.replyToSender(ctx, msg, "🔍 正在扫描全服...");

    const platform = msg.platform;
    const roles = (getRoleStorage()[platform] || {});
    const npcs = JSON.parse(ext.storageGet("a_npc_list") || "[]");
    const groups = JSON.parse(ext.storageGet("group") || "[]").map(g => g.replace("_占用", ""));
    const noquit = JSON.parse(ext.storageGet("noquit") || "{}");

    let countUpdate = 0; // 新增记录数
    let countKick = 0;   // 尝试踢人计数

    // 检查是否包含“驱逐”参数
    const shouldKick = cmdArgs.getArgN(1) === "驱逐";

    // 遍历所有群
    for (let gid of groups) {
        const members = await getGroupMembersSilent(gid, ctx, msg);
        for (let m of members) {
            const qq = m.user_id.toString();
            // 找角色名
            const roleName = Object.keys(roles).find(k => roles[k][0] === qq);

            // 如果是玩家且不是NPC
            if (roleName && !npcs.includes(roleName)) {
                let isNewRecord = false;
                if (!noquit[qq]) {
                    noquit[qq] = [];
                }
                if (!noquit[qq].includes(gid)) {
                    noquit[qq].push(gid);
                    isNewRecord = true;
                    countUpdate++;
                }

                // 如果是驱逐模式，且该玩家在违规群里，直接踢出
                if (shouldKick && isNewRecord) {
                    try {
                        // 构造踢人指令
                        // 注意：这里直接 await ws()，因为 ws 函数内部会处理连接和发送
                        await ws({
                            action: "set_group_kick",
                            params: {
                                group_id: parseInt(gid),
                                user_id: parseInt(qq)
                                // reject_add_request 默认为 false，不加这个参数
                            }
                        }, ctx, msg, null); // 第四个参数是 successreply，这里不需要回复，传 null
                        
                        countKick++;
                    } catch (e) {
                        console.error(`[踢人] 发送指令失败:`, e);
                    }
                }
            }
        }
    }

    // 只有数据有变更才保存
    if (countUpdate > 0) {
        ext.storageSet("noquit", JSON.stringify(noquit));
    }

    // 根据模式回复不同的消息
    if (shouldKick) {
        seal.replyToSender(ctx, msg, `✅ 扫描并驱逐完成！\n新增记录: ${countUpdate} 人\n执行踢出: ${countKick} 人`);
    } else {
        seal.replyToSender(ctx, msg, `✅ 扫描完成，新增 ${countUpdate} 条违规记录。(如需驱逐请加“驱逐”参数)`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["更新未退群"] = cmd_fix_noquit;

// --- 辅助提取：统一的角色信息获取 ---
const getRoleDetails = (platform, name) => {
    const privateGroups = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const info = privateGroups?.[platform]?.[name] || [];
    return { uid: info[0], gid: info[1] };
};

async function finalizeGroupCreation(platform, ctx, msg, groupData, participants) {
    // 1. 获取可用群号
    const gid = await allocateGroup(platform, ctx, msg);
    if (!gid) return seal.replyToSender(ctx, msg, "❌ 暂无可调用的群号，请联系管理员扩容群池。");

    const expireHours = parseInt(ext.storageGet("group_expire_hours") || "48");
    const expireTime = Date.now() + expireHours * 3600000;
    const timeStr = new Date(expireTime).toLocaleString("zh-CN", { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

    // 2. 准备数据落盘
    const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    const groupInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");

    participants.forEach(name => {
        const details = getRoleDetails(platform, name);
        if (!details || !details.uid) return;
        const key = `${platform}:${details.uid.replace(/^[a-z]+:/i, "")}`;
        
        if (!b_confirmedSchedule[key]) b_confirmedSchedule[key] = [];
        
        // 逻辑：如果只有2人，Partner 存对方名字；如果多人，存“多人小群”
        const partnerInfo = participants.length > 2 
            ? "多人小群" 
            : participants.find(n => n !== name);

        b_confirmedSchedule[key].push({
            day: groupData.day,
            time: groupData.time,
            place: groupData.place,
            partner: partnerInfo,
            subtype: groupData.subtype,
            group: gid,
            status: "active"
        });
    });

    groupInfo[gid] = { ...groupData, participants, expireTime };
    ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    ext.storageSet("group_expire_info", JSON.stringify(groupInfo));

    // 3. 构建群名：2人显示名字，多于2人显示“多人”
    const participantsText = participants.join("、");
    const groupNameTag = participants.length > 2 ? "多人" : participantsText;
    const finalGroupName = `${groupData.subtype} ${groupData.day} ${groupData.time} ${groupNameTag}`;

    // 4. 构建统一通知文案（包含群号和所有人名）
    const noticeText = `🎉 【${groupData.subtype}】创建成功！\n` +
                       `━━━━━━━━━━━━━━\n` +
                       `👤 发起人：${groupData.sendname}\n` +
                       `📅 时间：${groupData.day} ${groupData.time}\n` +
                       `📍 地点：${groupData.place}\n` +
                       `👥 参与者：${participantsText}\n` +
                       `💬 群号：${gid}\n` +
                       `⏰ 有效期至：${timeStr}\n` +
                       `━━━━━━━━━━━━━━\n` +
                       `请搜索群号入群\n` +
                       `· 修改时间 → 。修改时间线 ${groupData.day} 新时间段\n` +
                       `· 提前结束 → 。废除时间线`;

    // 5. 向所有参与者发送私聊/绑定群通知
    participants.forEach(name => {
        const { uid, gid: bindGid } = getRoleDetails(platform, name);
        if (uid && bindGid) {
            const m = seal.newMessage();
            m.messageType = "group";
            m.groupId = `${platform}-Group:${bindGid}`;
            const tempCtx = seal.createTempCtx(ctx.endPoint, m);
            seal.replyToSender(tempCtx, m, noticeText);
        }
    });

    // 6. 目标约会群初始化与更名
    const targetMsg = seal.newMessage();
    targetMsg.messageType = "group";
    targetMsg.groupId = `${platform}-Group:${gid}`;
    const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);
    
    seal.replyToSender(targetCtx, targetMsg, noticeText);
    setGroupName(targetCtx, targetMsg, gid, finalGroupName);

    // 7. 其他系统触发
    triggerSightingCheck(platform, groupData.day, groupData.time, groupData.place, participants, gid, groupData.subtype, ctx, msg);
    recordMeetingAndAnnounce(groupData.subtype, platform, ctx, ctx.endPoint);
    if (groupData.subtype) initGroupTimer(platform, gid, groupData.subtype, participants, participants[0]);
}

// ========================
// ⏰ 查看到期群指令（精简版）
// ========================

let cmd_view_expired_groups = seal.ext.newCmdItemInfo();
cmd_view_expired_groups.name = "查看到期群";
cmd_view_expired_groups.help = "查看所有已到期群组\n。查看到期群 - 查看所有已到期群组\n。查看到期群 提醒 - 向所有已到期群组发送到期提醒";

cmd_view_expired_groups.solve = (ctx, msg, cmdArgs) => {
    try {
        if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 该指令仅限管理员使用"), seal.ext.newCmdExecuteResult(true);
        const platform = msg.platform;
        const action = cmdArgs.getArgN(1);
        const now = Date.now();
        const groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
        const [expiredGroups, activeGroups] = Object.entries(groupExpireInfo).reduce(([exp, act], [gid, info]) => ((now > info.expireTime ? exp : act).push({ gid, ...info }), [exp, act]), [[], []]);
        
        const formatTime = (ts) => new Date(ts).toLocaleString("zh-CN", { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
        
        if (!action) {
            if (!expiredGroups.length) return seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组。"), seal.ext.newCmdExecuteResult(true);
            let result = `⏰ 已到期群组列表（共${expiredGroups.length}个）：\n\n`;
            expiredGroups.forEach((g, idx) => {
                const overdue = (now - g.expireTime) / 60000;
                const overdueDays = Math.floor(overdue / 1440), overdueHours = Math.floor((overdue % 1440) / 60), overdueMins = Math.floor(overdue % 60);
                result += `📌 群组 ${idx+1}:\n  群号：${g.gid}\n  类型：${g.subtype || '小群'}\n  时间：${g.day} ${g.time}\n  地点：${g.place}\n  参与者：${g.participants.join('、')}\n  到期时间：${formatTime(g.expireTime)}\n  已超时：${overdueDays?`${overdueDays}天`:''}${overdueHours?`${overdueHours}小时`:''}${overdueMins}分钟\n\n`;
            });
            result += `💡 提示：使用「。查看到期群 提醒」向所有已到期群组发送提醒消息`;
            return seal.replyToSender(ctx, msg, result), seal.ext.newCmdExecuteResult(true);
        }
        
        if (action === "提醒") {
            if (!expiredGroups.length) return seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组，无需提醒。"), seal.ext.newCmdExecuteResult(true);
            let successCount = 0, failCount = 0, failDetails = [];
            for (const group of expiredGroups) {
                try {
                    const groupMsg = seal.newMessage();
                    groupMsg.messageType = "group";
                    groupMsg.groupId = `${platform}-Group:${group.gid}`;
                    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
                    const overdue = (now - group.expireTime) / 60000;
                    const overdueDays = Math.floor(overdue / 1440), overdueHours = Math.floor((overdue % 1440) / 60), overdueMins = Math.floor(overdue % 60);
                    const overdueText = overdueDays ? `${overdueDays}天${overdueHours}小时${overdueMins}分钟` : (overdueHours ? `${overdueHours}小时${overdueMins}分钟` : `${overdueMins}分钟`);
                    const reminderMsg = `⏰ 温馨提示：\n\n本群互动时间已经超过预定结束时间 ${overdueText} 啦～\n\n如果各位已经完成互动，可以请管理员帮忙结束本群，\n使用指令「。结束私约」即可。\n\n📋 群组信息：\n• 类型：${group.subtype || '小群'}\n• 时间：${group.day} ${group.time}\n• 地点：${group.place}\n• 参与者：${group.participants.join('、')}\n\n感谢各位的参与～`;
                    seal.replyToSender(groupCtx, groupMsg, reminderMsg);
                    successCount++;
                } catch (error) {
                    failCount++;
                    failDetails.push(`群组 ${group.gid}: ${error.message}`);
                }
            }
            let result = `📢 到期提醒发送完成：\n\n✅ 成功提醒：${successCount} 个群组\n`;
            if (failCount) result += `⚠️ 提醒失败：${failCount} 个群组\n${failDetails.length && failDetails.length<=5 ? `失败详情：\n${failDetails.map(d=>`• ${d}`).join('\n')}\n` : ''}`;
            result += `\n💡 小提示：\n• 已到期的群组会继续在列表中显示\n• 管理员可在相应群内使用「。结束私约」结束群组`;
            return seal.replyToSender(ctx, msg, result), seal.ext.newCmdExecuteResult(true);
        }
        
        return seal.replyToSender(ctx, msg, "⚠️ 参数错误，请使用：\n。查看到期群 - 查看列表\n。查看到期群 提醒 - 发送提醒"), seal.ext.newCmdExecuteResult(true);
    } catch (error) {
        console.log(`[异常] .查看到期群 崩溃: ${error.stack || error}`);
        return seal.replyToSender(ctx, msg, "⚠️ 指令执行出错，请检查日志"), seal.ext.newCmdExecuteResult(true);
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
cmdSpecialTitle.help = "群头衔功能，可用“.群头衔 内容” 指令来更改。 “.群头衔 权限切换”来切换可发布者的身份，默认为管理员与群主才能更改头衔（master和白名单例外），切换后为所有人都可以更改。无论哪种权限，管理员和群主可以通过@某人代改。";
cmdSpecialTitle.allowDelegate = true;
cmdSpecialTitle.solve = (ctx, msg, cmdArgs) => {
    const fmtCondition = parseInt(seal.format(ctx, `{${seal.ext.getStringConfig(ext, "群管插件使用需要满足的条件")}}`));
    if (fmtCondition !== 1) return seal.replyToSender(ctx, msg, `当前不满足使用条件，无法使用群管功能`), seal.ext.newCmdExecuteResult(true);

    let val = cmdArgs.getArgN(1);
    ctx.delegateText = "";
    if (val === "help") return seal.ext.newCmdExecuteResult(true);

    if (!val) return seal.replyToSender(ctx, msg, `请输入头衔内容`), seal.ext.newCmdExecuteResult(true);

    if (val === "权限切换" && ctx.privilegeLevel > 45) {
        whiteList = whiteList === 1 ? 0 : 1;
        seal.replyToSender(ctx, msg, whiteList === 1 ? `权限已切换为管理员与群主可更改` : `权限已切换为所有人可更改`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (ctx.privilegeLevel < 45 && whiteList === 1) {
        return seal.replyToSender(ctx, msg, `权限不足，无法修改群头衔,当前只有管理员与群主可无法修改群头衔`), seal.ext.newCmdExecuteResult(true);
    }

    let mctx = seal.getCtxProxyFirst(ctx, cmdArgs);
    let userQQ = mctx.player.userId.split(":")[1];
    if (ctx.privilegeLevel < 45 && mctx.player.userId !== ctx.player.userId) {
        return seal.replyToSender(ctx, msg, `权限不足，无法修改他人群头衔。`), seal.ext.newCmdExecuteResult(true);
    }

    const groupContent = val;
    const contentLength = Array.from(groupContent).reduce((len, c) => len + (/[\u0020-\u007E]/.test(c) ? 0.5 : /[\u4e00-\u9fa5]/.test(c) ? 1 : 0), 0);
    if (contentLength > 6) return seal.replyToSender(ctx, msg, "头衔长度不能超过六个字符。"), seal.ext.newCmdExecuteResult(true);

    const groupQQ = ctx.group.groupId.match(/:(\d+)/)[1];
    const postData = { action: "set_group_special_title", params: { group_id: parseInt(groupQQ, 10), user_id: parseInt(userQQ, 10), special_title: groupContent.toString() } };
    return ws(postData, ctx, msg, `群头衔更改成功。`);
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
// 📢 群公告发布指令（简化版）
// ========================

let cmdGroupNotice = seal.ext.newCmdItemInfo();
cmdGroupNotice.name = "群公告发布";
cmdGroupNotice.help = 
    "。群公告发布 内容 - 发布群公告（支持图片）\n" +
    "。群公告发布 权限切换 - 切换发布权限（管理员可用）\n" +
    "注：预设模板已移除，请直接输入内容。";

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
    
    // 提取公告内容
    const matchResult = msg.message.match(/^[。.]群公告发布\s+(.+)$/s);
    if (!matchResult || !matchResult[1]) {
        seal.replyToSender(ctx, msg, `请输入公告内容。示例：。群公告发布 今晚8点有活动`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const content = matchResult[1].trim();
    
    // 使用函数发布公告
    return setGroupNotice(ctx, msg, ctx.group.groupId, content);
};

// 注册指令
ext.cmdMap["群公告发布"] = cmdGroupNotice;

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

// ========================
// 🛡️ 管理员系统
// ========================

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

let cmd_block_user_feature = seal.ext.newCmdItemInfo();
cmd_block_user_feature.name = "功能权限";
cmd_block_user_feature.help = "。功能权限 角色名 功能 开启/关闭\n功能：礼物/发起邀约/寄信/心愿/心动信/论坛/商城购买/抽取/全部";

cmd_block_user_feature.solve = (ctx, msg, cmdArgs) => {
  const roleName = cmdArgs.getArgN(1);
  const featureName = cmdArgs.getArgN(2);
  const action = cmdArgs.getArgN(3);

  if (!roleName || !featureName || !action) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const featureMap = {
    "礼物": "enable_general_gift",
    "发起邀约": "enable_general_appointment",
    "寄信": "enable_chaos_letter",
    "心愿": "enable_wish_system",
    "心动信": "enable_lovemail",
    "论坛": "enable_forum",
    "商城购买": "enable_shop_purchase",
    "抽取": "enable_item_draw"
  };

  const value = (action === "开启") ? true : (action === "关闭") ? false : null;
  if (value === null) {
    seal.replyToSender(ctx, msg, `⚠️ 状态应为：开启 / 关闭`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
  if (!blockMap[roleName]) blockMap[roleName] = {};

  if (featureName === "全部") {
    for (const key of Object.values(featureMap)) blockMap[roleName][key] = value;
    ext.storageSet("feature_user_blocklist", JSON.stringify(blockMap));
    const status = value ? "✅ 已开启" : "🚫 已关闭";
    seal.replyToSender(ctx, msg, `${status} 全部功能：${roleName}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const key = featureMap[featureName];
  if (!key) {
    seal.replyToSender(ctx, msg, `⚠️ 功能名可选：礼物 / 发起邀约 / 寄信 / 心愿 / 心动信 / 论坛 / 商城购买 / 抽取 / 全部`);
    return seal.ext.newCmdExecuteResult(true);
  }

  blockMap[roleName][key] = value;
  ext.storageSet("feature_user_blocklist", JSON.stringify(blockMap));

  const status = value ? "✅ 已开启" : "🚫 已关闭";
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
    enable_general_gift: "礼物",
    enable_general_appointment: "发起邀约",
    enable_chaos_letter: "寄信",
    enable_wish_system: "心愿",
    enable_lovemail: "心动信",
    enable_forum: "论坛",
    enable_shop_purchase: "商城购买",
    enable_item_draw: "抽取"
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

// ========================
// 🌠 心愿系统
// ========================
const WishUtils = {
    getPool: () => {
        const now = Date.now(), exp = 86400000;
        let p = JSON.parse(ext.storageGet("a_wishPool") || "[]").filter(w => now - w.timestamp < exp);
        return p; // 仅作为获取，写入放在具体操作中
    },
    savePool: (p) => ext.storageSet("a_wishPool", JSON.stringify(p)),
    formatList: (pool, title) => {
        if (!pool.length) return title + "当前没有漂浮的心愿。";
        const now = Date.now(), exp = 86400000;
        return `📜 ${title}：\n` + pool.map(w => {
            const rem = Math.ceil((exp - (now - w.timestamp)) / 3600000);
            return `编号：${w.id}｜${w.day} ${w.time}｜${w.place}｜剩${rem}h｜内容：${w.content}`;
        }).join('\n');
    }
};

// ==========================================
// 挂心愿
// ==========================================
let cmd_post_wish = seal.ext.newCmdItemInfo();
cmd_post_wish.name = "挂心愿";
cmd_post_wish.solve = (ctx, msg, cmdArgs) => {
    const cfg = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");

    const platform = msg.platform, uid = msg.sender.userId, name = getUserRoleName(platform, uid);
    const day = ext.storageGet("global_days");
    if (!name || !day) return seal.replyToSender(ctx, msg, !name ? "请先绑定角色" : "请先设置全局天数");

    let [rawT, place, ...contentArr] = cmdArgs.args;
    const content = contentArr.join(" ").trim();
    if (!rawT || !place || !content) return seal.replyToSender(ctx, msg, "用法：挂心愿 1400-1500 地点 内容");

    const time = parseWishTime(rawT);
    if (!time || !isValidTimeFormat(time)) return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误（如 1400-1500）");

    // 冲突与限制检查
    if (!checkRealityHourLimit(time, ctx, msg)) return;
    const pCheck = checkPlaceCommon(platform, name, place, "挂心愿");
    if (!pCheck.valid) return seal.replyToSender(ctx, msg, pCheck.errorMsg);

    const conflicts = checkAcceptanceConflicts(platform, uid.replace(`${platform}:`, ""), name, day, time);
    if (conflicts.length) return seal.replyToSender(ctx, msg, `⚠️ 时间冲突：\n${conflicts.join('\n')}`);

    let pool = WishUtils.getPool();
    if (pool.filter(w => w.fromId === uid).length >= 3) return seal.replyToSender(ctx, msg, "⚠️ 最多同时挂3个心愿");

    const id = Math.random().toString(36).slice(2, 9).toUpperCase();
    pool.push({ id, day, time, place, content, fromId: uid, timestamp: Date.now() });
    WishUtils.savePool(pool);

    seal.replyToSender(ctx, msg, `✅ 心愿已漂走！编号：${id}\n有效期：24小时`);

    // 公共频道推送
    if (JSON.parse(ext.storageGet("wish_public_send") || "false")) {
        const gid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
        if (gid) {
            const m = seal.newMessage(); m.messageType = "group"; m.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m), m, `🌠 新心愿 [${id}]\n📅 ${day} ${time.replace('-', ' ~ ')}\n📍 ${place}\n💌 ${content}\n✨ 摘取：。摘心愿 ${id}`);
        }
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["挂心愿"] = cmd_post_wish;

// ==========================================
// 看心愿 & 摘心愿
// ==========================================
ext.cmdMap["看心愿"] = {
    name: "看心愿",
    solve: (ctx, msg) => {
        seal.replyToSender(ctx, msg, WishUtils.formatList(WishUtils.getPool(), "当前心愿"));
        return seal.ext.newCmdExecuteResult(true);
    }
};

let cmd_pick_wish = seal.ext.newCmdItemInfo();
cmd_pick_wish.name = "摘心愿";
cmd_pick_wish.solve = async (ctx, msg, cmdArgs) => {
    const wid = cmdArgs.getArgN(1)?.toUpperCase();
    const platform = msg.platform, uid = msg.sender.userId, name = getUserRoleName(platform, uid);
    if (!wid || !name) return seal.replyToSender(ctx, msg, !wid ? "格式：。摘心愿 编号" : "请先绑定角色");

    let pool = WishUtils.getPool();
    const wish = pool.find(w => w.id === wid);
    if (!wish || wish.fromId === uid) return seal.replyToSender(ctx, msg, !wish ? "心愿不存在或已过期" : "不能摘自己的心愿");

    const fromName = getUserRoleName(platform, wish.fromId);
    
    // 摘取冲突双向检查
    const check = (u, n) => checkAcceptanceConflicts(platform, u.replace(`${platform}:`, ""), n, wish.day, wish.time);
    const errs = [...check(uid, name), ...check(wish.fromId, fromName)];
    if (errs.length) return seal.replyToSender(ctx, msg, `⚠️ 无法建立联系：\n${errs.join('\n')}`);

    // 移除并成交
    WishUtils.savePool(pool.filter(w => w.id !== wid));

    const item = {
        id: wid, type: "小群", subtype: "心愿", sendname: fromName, sendid: wish.fromId.replace(`${platform}:`, ""),
        toname: name, toid: uid.replace(`${platform}:`, ""), day: wish.day, time: wish.time, place: wish.place, title: wish.content
    };

    // 异步下发
    await finalizeGroupCreation(platform, ctx, msg, item, [fromName, name]);
    
    // 通知双方
    const priv = JSON.parse(ext.storageGet("a_private_group") || "{}")[platform] || {};
    [ {id: uid, t: fromName}, {id: wish.fromId, t: name} ].forEach(p => {
        const gid = priv[p.t === fromName ? name : fromName]?.[1];
        if (gid) {
            const m = seal.newMessage(); m.messageType = "group"; m.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m), m, `💫 摘心愿成功！与 ${p.t} 的小群已开启。\n📍 ${wish.place} | ⏰ ${wish.day} ${wish.time}`);
        }
    });

    seal.replyToSender(ctx, msg, `🎉 摘取成功！专属小群已建立。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["摘心愿"] = cmd_pick_wish;

// ==========================================
// 撤心愿
// ==========================================
let cmd_withdraw_wish = seal.ext.newCmdItemInfo();
cmd_withdraw_wish.name = "撤心愿";
cmd_withdraw_wish.solve = (ctx, msg, cmdArgs) => {
    const wid = cmdArgs.getArgN(1)?.toUpperCase(), uid = msg.sender.userId;
    let pool = WishUtils.getPool();
    const myWishes = pool.filter(w => w.fromId === uid);

    if (!wid) return seal.replyToSender(ctx, msg, WishUtils.formatList(myWishes, "你发布的心愿") + "\n\n使用「。撤心愿 编号」撤回");

    if (!myWishes.some(w => w.id === wid)) return seal.replyToSender(ctx, msg, "❌ 编号错误或该心愿不属于你");

    WishUtils.savePool(pool.filter(w => w.id !== wid));
    seal.replyToSender(ctx, msg, `✅ 已撤回心愿 ${wid}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤心愿"] = cmd_withdraw_wish;

// ========================
// 🕊️ 寄信与关系线系统
// ========================
async function handleNaturalChaosLetter(ctx, msg, platform, sendname, toname, contentOriginal) {
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_chaos_letter === false) {
        return seal.replyToSender(ctx, msg, "🕊️ 寄信功能已关闭。");
    }

    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform][toname]) {
        return seal.replyToSender(ctx, msg, `❌ 未找到收信人：${toname}`);
    }

    // 🎲 读取混乱配置
    let chaosConfig = JSON.parse(ext.storageGet("chaos_letter_config") || "{}");
    const defaultConfig = {
        misdelivery: 0, blackoutText: 0, loseContent: 0, antonymReplace: 0,
        reverseOrder: 0, mistakenSignature: 0, poeticSignature: 0, dailyLimit: 5, publicChance: 50
    };
    chaosConfig = { ...defaultConfig, ...chaosConfig };

    // ⏳ 冷却与次数检查 (使用发送者的 UID)
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const cooldownKey = `chaos_letter_cooldown_${platform}:${uid}`;
    const lastSent = parseInt(ext.storageGet(cooldownKey) || "0");
    const now = Date.now();
    const mailCooldownMin = parseInt(ext.storageGet("mailCooldown") || "60");
    
    if (now - lastSent < mailCooldownMin * 60 * 1000) {
        const rem = Math.ceil((mailCooldownMin * 60 * 1000 - (now - lastSent)) / 60000);
        return seal.replyToSender(ctx, msg, `⏳ 鸽子正在休息，请 ${rem} 分钟后再试`);
    }

    const gameDay = ext.storageGet("global_days") || "D0"; 
    const globalChaosCounts = JSON.parse(ext.storageGet("global_chaos_letter_counts") || "{}");
    const userKey = `${platform}:${uid}`;
    let userRec = globalChaosCounts[userKey] || { day: gameDay, count: 0 };
    if (userRec.day !== gameDay) userRec = { day: gameDay, count: 0 };

    if (userRec.count >= chaosConfig.dailyLimit) {
        return seal.replyToSender(ctx, msg, `🕊️ 今日寄信次数已达上限(${chaosConfig.dailyLimit})`);
    }

    // 📝 内容侵蚀处理 (保持原逻辑)
    let content = contentOriginal;
    const chaosCharPool = ["梦", "影", "幻", "虚", "无", "断", "零", "终", "念", "尘", "迹", "雾", "嘘", "寂"];
    
    if (Math.random() < (chaosConfig.antonymReplace / 100)) {
        let textArray = content.split('');
        const replaceCount = Math.floor(textArray.length * (0.15 + Math.random() * 0.1));
        for (let i = 0; i < replaceCount; i++) {
            textArray[Math.floor(Math.random() * textArray.length)] = chaosCharPool[Math.floor(Math.random() * chaosCharPool.length)];
        }
        content = textArray.join('');
    }
    if (Math.random() < (chaosConfig.loseContent / 100) && content.length > 5) {
        content = content.slice(0, Math.floor(content.length * 0.7)) + "……";
    }
    if (Math.random() < (chaosConfig.blackoutText / 100)) {
        const blackout = ["◼︎", "█", "■", "▮"];
        content = content.split('').map(c => Math.random() < 0.2 ? blackout[Math.floor(Math.random() * blackout.length)] : c).join('');
    }

    // 🖋️ 落款逻辑
    let finalSignature = `落款：${sendname}`;
    const sigRoll = Math.random();
    if (sigRoll < (chaosConfig.mistakenSignature / 100)) {
        const others = Object.keys(a_private_group[platform]).filter(n => n !== sendname);
        if (others.length) finalSignature = `落款：${others[Math.floor(Math.random() * others.length)]}`;
    }

    // 📤 投递
    let trueRecipient = toname;
    if (Math.random() < (chaosConfig.misdelivery / 100)) {
        const others = Object.keys(a_private_group[platform]).filter(n => n !== toname);
        if (others.length) trueRecipient = others[Math.floor(Math.random() * others.length)];
    }

    const targetEntry = a_private_group[platform][trueRecipient];
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    const targetQQ = targetEntry[0];
    const notice = `[CQ:at,qq=${targetQQ}]\n📱 ${toname}，你收到一条短信：\n「${content}」\n\n${finalSignature}`;
    seal.replyToSender(newctx, newmsg, notice);

    // 7. 更新数据
    ext.storageSet(cooldownKey, now.toString());
    userRec.count += 1;
    globalChaosCounts[userKey] = userRec;
    ext.storageSet("global_chaos_letter_counts", JSON.stringify(globalChaosCounts));

    seal.replyToSender(ctx, msg, `🕊️ 信件已由鸽子衔往 ${toname} 处。今日已发 ${userRec.count}/${chaosConfig.dailyLimit}。`);

    // 公开逻辑
    const letterPublicEnabled = JSON.parse(ext.storageGet("letter_public_send") || "false");
    if (letterPublicEnabled && (Math.random() * 100 <= chaosConfig.publicChance)) {
        const adminGid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
        if (adminGid) {
            const pMsg = seal.newMessage();
            pMsg.messageType = "group";
            pMsg.groupId = `${platform}-Group:${adminGid}`;
            const pCtx = seal.createTempCtx(ctx.endPoint, pMsg);
            seal.replyToSender(pCtx, pMsg, `💌 公开信件：\n「${sendname}」→「${toname}」\n内容：「${content}」`);
        }
    }

    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce("寄信", platform, ctx, ctx.endPoint);
    }
}

// ========================
// 核心功能：发送信件（含：日期前置、附件展示、写信币赏金）
// ========================
let cmd_send_letter = seal.ext.newCmdItemInfo();
cmd_send_letter.name = "发送信件";
cmd_send_letter.help = "。发送信件\n【收件人】角色名\n【内容】信件内容\n【日期】显示的日期（选填，前置显示）\n【附件】额外备注/物品（选填，分开展示）\n【署名】自定义落款（选填）";

cmd_send_letter.solve = (ctx, msg, cmdArgs) => {
    // 1. 功能开关
    const config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_direct_letter === false) {
        seal.replyToSender(ctx, msg, "✉️ 发送信件功能已关闭。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");

    // 2. 身份核验
    const senderRoleName = Object.entries(a_private_group[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0];
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 远方的旅人，寄信前请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const raw = msg.message.trim();

    // 3. 解析【】标签
    const getTag = (tag) => {
        const regex = new RegExp(`【${tag}】([\\s\\S]*?)(?=【|$)`, "i");
        const match = raw.match(regex);
        return match ? match[1].trim() : null;
    };

    const signature = getTag("署名") || senderRoleName;
    const receiver = getTag("收件人") || getTag("发送对象");
    const content = getTag("内容") || "";
    const dateTag = getTag("日期");      // 日期解析
    const attachment = getTag("附件");   // 附件解析

    if (!receiver) {
        seal.replyToSender(ctx, msg, `⚠️ 格式错误！请指定收件人。\n\n标准格式：\n。发送信件\n【收件人】角色名\n【内容】想说的话\n【日期】日期\n【附件】附件内容\n【署名】落款`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!a_private_group[platform]?.[receiver]) {
        seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${receiver}」，请确认名字是否正确。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!content) {
        seal.replyToSender(ctx, msg, `⚠️ 信件内容不能为空。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 4. 游戏天数 & 每日限额
    const gameDay = ext.storageGet("global_days") || "D0";
    const dailyLimit = parseInt(ext.storageGet("direct_letter_daily_limit") || "5");
    const userKey = `${platform}:${uid}`;
    let dlCounts = JSON.parse(ext.storageGet("direct_letter_day_counts") || "{}");
    if (!dlCounts[userKey] || dlCounts[userKey].day !== gameDay) {
        dlCounts[userKey] = { day: gameDay, count: 0 };
    }
    const currentCount = dlCounts[userKey].count;

    if (currentCount >= dailyLimit) {
        seal.replyToSender(ctx, msg, `📪 ${gameDay} 你已发送 ${currentCount} 封信件（上限 ${dailyLimit} 封）。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 5. 赏金检查
    const minChars = parseInt(ext.storageGet("direct_letter_min_chars") || "0");
    const rewardPerLetter = parseInt(ext.storageGet("direct_letter_reward") || "0");
    const contentLength = content.replace(/\s/g, "").length;
    const meetsMinChars = minChars === 0 || contentLength >= minChars;

    // 6. 组装并投递到收件人私人群
    let finalLetter = `✉️ ${receiver}，你收到一封信：\n`;
    
    // 日期前置
    if (dateTag) finalLetter += `📅 日期：${dateTag}\n`;
    
    finalLetter += `\n「${content}」\n\n—— ${signature}`;

    // 附件展示（加分隔线）
    if (attachment) {
        finalLetter += `\n\n附件：\n--------------------\n${attachment}`;
    }

    const targetEntry = a_private_group[platform][receiver];
    const deliverMsg = seal.newMessage();
    deliverMsg.messageType = "group";
    deliverMsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const deliverCtx = seal.createTempCtx(ctx.endPoint, deliverMsg);
    seal.replyToSender(deliverCtx, deliverMsg, finalLetter);

    // 7. 发放写信币赏金
    let rewardGiven = 0;
    let totalCoins = 0;
    if (rewardPerLetter > 0 && meetsMinChars) {
        let attrs = JSON.parse(ext.storageGet("sys_character_attrs") || "{}");
        if (!attrs[senderRoleName]) attrs[senderRoleName] = {};
        attrs[senderRoleName]["写信币"] = (attrs[senderRoleName]["写信币"] || 0) + rewardPerLetter;
        totalCoins = attrs[senderRoleName]["写信币"];
        ext.storageSet("sys_character_attrs", JSON.stringify(attrs));

        let presets = JSON.parse(ext.storageGet("sys_attr_presets") || "[]");
        if (!presets.includes("写信币")) {
            presets.push("写信币");
            ext.storageSet("sys_attr_presets", JSON.stringify(presets));
        }
        rewardGiven = rewardPerLetter;
    }

    // 8. 更新发送计数
    dlCounts[userKey].count = currentCount + 1;
    ext.storageSet("direct_letter_day_counts", JSON.stringify(dlCounts));

    // 9. 回复发信人
    let reply = `✉️ 信件已送达「${receiver}」！\n`;
    reply += `🖋️ 落款：${signature}\n`;
    reply += `📅 ${gameDay}（今日剩余：${dailyLimit - (currentCount + 1)}/${dailyLimit}）`;
    if (rewardPerLetter > 0) {
        reply += meetsMinChars ? `\n💰 写信币 +${rewardGiven}（共 ${totalCoins}）` : `\n📝 提示：字数不足 ${minChars}，未获得赏金。`;
    }
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发送信件"] = cmd_send_letter;

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
cmd_add_rel_detail.name = "拉线";
cmd_add_rel_detail.solve = (ctx, msg, cmdArgs) => {
    if (!RelationshipUtils.isEnabled()) return seal.replyToSender(ctx, msg, "❌ 系统已关闭");

    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);
    const content = cmdArgs.args.slice(1).join(' ').trim();

    if (!sendName || !toName || !content) return seal.replyToSender(ctx, msg, "格式：。拉线 对方名 内容");
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
ext.cmdMap["拉线"] = cmd_add_rel_detail;

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
// ✏️ 指令：撤回关系（按内容匹配）
// ========================
let cmd_withdraw_relation = seal.ext.newCmdItemInfo();
cmd_withdraw_relation.name = "撤回关系";
cmd_withdraw_relation.help = "。撤回关系 对方角色名 要撤回的内容（精确匹配，仅撤回自己发送的细节）";

cmd_withdraw_relation.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);
    // 从第二个参数之后的所有内容作为要撤回的内容（支持空格）
    const content = cmdArgs.args.slice(1).join(' ').trim();

    if (!sendName || !toName || !content) {
        return seal.replyToSender(ctx, msg, "格式：。撤回关系 对方角色名 要撤回的内容");
    }

    let relData = RelationshipUtils.getData("relationship_lines");
    let rel = relData[platform]?.[sendName]?.[toName];
    if (!rel || !rel.details || rel.details.length === 0) {
        return seal.replyToSender(ctx, msg, "没有可撤回的细节记录。");
    }

    // 查找自己发送的、内容精确匹配的第一条细节
    const idx = rel.details.findIndex(d => d.from === sendName && d.text === content);
    if (idx === -1) {
        return seal.replyToSender(ctx, msg, `未找到你发送的匹配内容：「${content}」\n可使用「。查看关系线 ${toName}」查看所有细节。`);
    }

    const removed = rel.details[idx];
    // 删除自己的记录
    rel.details.splice(idx, 1);

    // 同步删除对方存储中的相同记录（按内容 + 发送人匹配）
    const otherRel = relData[platform]?.[toName]?.[sendName];
    if (otherRel && otherRel.details) {
        const otherIdx = otherRel.details.findIndex(d => d.from === sendName && d.text === content);
        if (otherIdx !== -1) otherRel.details.splice(otherIdx, 1);
    }

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 已成功撤回你发送的细节：\n"${removed.text}"`);

    // 可选：通知对方
    const addr = getTargetAddr(platform, toName);
    if (addr) {
        ws({
            action: "send_group_msg",
            params: {
                group_id: parseInt(addr[1], 10),
                message: `🗑️ 「${sendName}」撤回了一条发给你的关系细节：\n"${removed.text}"`
            }
        }, ctx, msg, "");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤回关系"] = cmd_withdraw_relation;

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

// ========================
// 📊 关系线统计（管理员专用）
// ========================
let cmd_rel_stats = seal.ext.newCmdItemInfo();
cmd_rel_stats.name = "关系线统计";
cmd_rel_stats.help = "。关系线统计 —— 查看所有角色的关系线数量（管理员专用）";
cmd_rel_stats.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const relData = JSON.parse(ext.storageGet("relationship_lines") || "{}");
    const platformData = relData[platform] || {};

    // 收集所有角色名及关系线数量
    const stats = [];
    for (const [role, links] of Object.entries(platformData)) {
        // links 是一个对象，键为关联的角色名，值为关系对象
        const count = Object.keys(links).length;
        if (count > 0) {
            stats.push({ role, count });
        }
    }

    // 按关系线数量降序排序
    stats.sort((a, b) => b.count - a.count);

    if (stats.length === 0) {
        seal.replyToSender(ctx, msg, "📭 当前平台没有任何关系线记录");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 构造合并转发消息
    const nodes = [];
    const header = `📊 角色关系线统计（${platform} 平台）\n共 ${stats.length} 个角色拥有关系线\n━━━━━━━━━━━━━━━`;
    nodes.push({
        type: "node",
        data: {
            name: "关系线统计员",
            uin: "10001",
            content: header
        }
    });

    // 每 20 个角色打包成一个节点，避免单条消息过长
    const chunkSize = 20;
    for (let i = 0; i < stats.length; i += chunkSize) {
        const chunk = stats.slice(i, i + chunkSize);
        let content = "";
        chunk.forEach((item, idx) => {
            content += `${i + idx + 1}. ${item.role}：${item.count} 条关系线\n`;
        });
        nodes.push({
            type: "node",
            data: {
                name: `角色列表 (${Math.floor(i / chunkSize) + 1})`,
                uin: "2852199344",
                content: content.trim()
            }
        });
    }

    // 发送合并转发
    const targetGid = msg.groupId.replace(/[^\d]/g, "");
    ws({
        action: "send_group_forward_msg",
        params: {
            group_id: parseInt(targetGid, 10),
            messages: nodes
        }
    }, ctx, msg, "");

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["关系线统计"] = cmd_rel_stats;

// ========================
// 🏢 官约与目击系统
// ========================

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
    newmsg.sender = {};
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

// 辅助函数：获取地点系统配置
function getPlaceSystemConfig() {
    const defaultConfig = {
        enabled: true,
        require_key_by_default: false
    };
    const config = JSON.parse(ext.storageGet("place_system_config") || "{}");
    return { ...defaultConfig, ...config };
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
    const randomChance = Math.random() < 0.5;
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
    console.log("找到其他会议数量：" + simultaneousMeetings.length)
    return simultaneousMeetings;
}
function sendSightingReports(platform, newMeetingInfo, simultaneousMeetings, ctx, msg) {
    console.log("[DEBUG] sendSightingReports 被调用", {
        platform,
        newMeetingInfo,
        simultaneousMeetingsCount: simultaneousMeetings?.length,
        ctxType: typeof ctx,
        msgType: typeof msg,
        ctxExists: !!ctx,
        msgExists: !!msg,
        ctxEndPointExists: ctx && !!ctx.endPoint
    });
    
    // 检查 ctx 和 endPoint 有效性
    if (!ctx || !ctx.endPoint) {
        console.error("[ERROR] sendSightingReports: ctx 或 ctx.endPoint 无效，无法发送报告");
        return;
    }
    
    const sightingConfig = getSightingConfig();
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    
    if (!a_private_group[platform]) {
        console.log("[DEBUG] a_private_group[platform] 不存在，platform=", platform);
        return;
    }
    
    // 记录已经发送过反向报告的 meeting，避免重复
    const processedReverseMeetings = new Set();
    
    // 为新会议的每个参与者发送目击报告
    for (const participant of newMeetingInfo.participants) {
        // 检查是否需要发送报告
        if (!shouldSendSightingReport(platform, participant)) {
            console.log("[DEBUG] 跳过参与者（shouldSendSightingReport=false）:", participant);
            continue;
        }
        
        // 获取参与者的群组ID
        const participantInfo = a_private_group[platform][participant];
        if (!participantInfo || !participantInfo[1]) {
            console.log("[DEBUG] 参与者信息无效:", participant, participantInfo);
            continue;
        }
        
        // 为每个同时进行的会议生成报告
        for (const otherMeeting of simultaneousMeetings) {
            // 跳过自己所在的会议
            if (otherMeeting.participants.includes(participant)) {
                console.log("[DEBUG] 跳过自身会议，参与者:", participant);
                continue;
            }
            
            // 构建生动的报告消息
            const otherParticipantsText = otherMeeting.participants.join('、');
            const reportMessage = 
                `👀 不会吧，你居然在 ${newMeetingInfo.place} 看见了 ${otherParticipantsText} 在一起！\n` ;
            
            // 使用 seal 框架发送消息
            const targetGroupId = participantInfo[1];
            const newMsg = seal.newMessage();
            newMsg.messageType = "group";
            newMsg.groupId = `${platform}-Group:${targetGroupId}`;
            const tempCtx = seal.createTempCtx(ctx.endPoint, newMsg);
            
            try {
                seal.replyToSender(tempCtx, newMsg, reportMessage);
                console.log("[DEBUG] 目击报告已发送至群组:", targetGroupId);
            } catch (err) {
                console.error("[ERROR] 发送目击报告失败:", err);
            }
            
            // 增加目击次数
            incrementUserSightingCountToday(platform, participant);
            
            // 如果配置为同时发送给被目击者，且该 meeting 尚未处理过反向报告
            if (sightingConfig.send_to_all && !processedReverseMeetings.has(otherMeeting.groupId)) {
                processedReverseMeetings.add(otherMeeting.groupId);
                sendCounterSightingReports(platform, otherMeeting, newMeetingInfo, ctx);
            }
            
            // 每个参与者每天只发送一次报告
            break;
        }
    }
}

// 发送反向目击报告（被目击者收到报告）
function sendCounterSightingReports(platform, originalMeeting, newMeetingInfo, ctx) {
    // 检查 ctx 和 endPoint 有效性
    if (!ctx || !ctx.endPoint) {
        console.error("[ERROR] sendCounterSightingReports: ctx 或 ctx.endPoint 无效，无法发送反向报告");
        return;
    }
    
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
            `👀 哎呀，你和${originalMeeting.participants.length > 1 ? '伙伴们' : '朋友'}在 ${originalMeeting.place} 的约会被 ${newParticipantsText} 看到了！\n` ;
        
        // 使用传入的 ctx 创建临时上下文发送报告
        const targetGroupId = participantInfo[1];
        const newMsg = seal.newMessage();
        newMsg.messageType = "group";
        newMsg.groupId = `${platform}-Group:${targetGroupId}`;
        const tempCtx = seal.createTempCtx(ctx.endPoint, newMsg);
        
        try {
            seal.replyToSender(tempCtx, newMsg, reportMessage);
        } catch (err) {
            console.error("[ERROR] 发送反向目击报告失败:", err);
            continue;
        }
        
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
function triggerSightingCheck(platform, day, time, place, participants, groupId, subtype,ctx,msg) {
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
        sendSightingReports(platform, newMeetingInfo, simultaneousMeetings,ctx,msg);
    }
}
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
/**
 * 更新用户统计（增强版：包含平均字数与平均时长）
 */
function updateUserStats(platform, roleName, wordCount, startTime, repliedTime) {
    const stats = getUserStats();
    const key = `${platform}:${roleName}`;
    
    // 1. 初始化统计结构
    if (!stats[key]) {
        stats[key] = {
            totalWords: 0,        // 总字数
            totalReplies: 0,      // 总有效回复次数
            totalReplyTimeMs: 0,  // 总回复耗时（毫秒）
            avgWords: 0,          // 平均字数
            avgReplyTimeMin: 0,   // 平均耗时（分钟）
            subtypeStats: {}      // 分类型统计
        };
    }
    
    const userStat = stats[key];
    const replyTimeMs = repliedTime - startTime;

    // 2. 更新基础累加数据
    userStat.totalReplies += 1;
    userStat.totalWords += wordCount;
    userStat.totalReplyTimeMs += replyTimeMs;

    // 3. 计算全局平均值
    userStat.avgWords = parseFloat((userStat.totalWords / userStat.totalReplies).toFixed(2));
    // 计算平均分钟数（保留1位小数）
    userStat.avgReplyTimeMin = parseFloat((userStat.totalReplyTimeMs / userStat.totalReplies / 60000).toFixed(1));
    
    // 4. 更新细分类型统计（可选，保持你原有的逻辑并增强）
    if (!userStat.subtypeStats[platform]) userStat.subtypeStats[platform] = {};
    if (!userStat.subtypeStats[platform][roleName]) {
        userStat.subtypeStats[platform][roleName] = {
            replies: 0,
            totalWords: 0,
            totalTime: 0,
            fastestReply: null,
            slowestReply: null
        };
    }
    
    const sub = userStat.subtypeStats[platform][roleName];
    sub.replies += 1;
    sub.totalWords += wordCount;
    sub.totalTime += replyTimeMs;
    
    // 记录最快/最慢纪录（分钟）
    const currentReplyMin = Math.round(replyTimeMs / 60000);
    if (!sub.fastestReply || currentReplyMin < sub.fastestReply) sub.fastestReply = currentReplyMin;
    if (!sub.slowestReply || currentReplyMin > sub.slowestReply) sub.slowestReply = currentReplyMin;
    
    saveUserStats(stats);
    
    console.log(`[统计更新] ${roleName}: 本次回复${wordCount}字, 耗时${currentReplyMin}分 | 累计平均: ${userStat.avgWords}字, ${userStat.avgReplyTimeMin}分`);
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
function sendReminder(platform, groupId, roleName, subtype, elapsedTime,ctx) {
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

// ========================
// 📨 消息转发系统
// ========================
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

// ========================
// 📊 玩家指令：查看个人历史统计
// ========================
let cmd_my_stats = seal.ext.newCmdItemInfo();
cmd_my_stats.name = "本场统计"; // 保留原名或改为“历史统计”
cmd_my_stats.help = "。本场统计 （查看角色在系统中的全平台历史表现数据）";
cmd_my_stats.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const storage = getRoleStorage();
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const roleName = Object.keys(storage[platform] || {}).find(key => storage[platform][key][0] === uid);

    if (!roleName) {
        seal.replyToSender(ctx, msg, "❌ 未找到你的角色绑定信息，请先创建角色。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const stats = getUserStats();
    const globalStat = stats[`${platform}:${roleName}`];

    if (!globalStat) {
        seal.replyToSender(ctx, msg, `📊 【${roleName}】暂无历史统计数据，快去参与邀约吧！`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = `📊 【${roleName}】历史统计报告\n`;
    reply += `━━━━━━━━━━━━━━━\n`;
    reply += `🔹 累计回复：${globalStat.totalReplies} 次\n`;
    reply += `🔹 累计字数：${globalStat.totalWords} 字\n`;
    reply += `🔹 平均每条：${globalStat.avgWords} 字\n`;
    reply += `🔹 平均耗时：${globalStat.avgReplyTimeMin} 分钟\n`;
    
    const sub = globalStat.subtypeStats?.[platform]?.[roleName];
    if (sub) {
        reply += `🔹 极限速度：${sub.fastestReply || '--'} min (最快)\n`;
    }
    reply += `━━━━━━━━━━━━━━━`;
    
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["本场统计"] = cmd_my_stats;


// ========================
// 👑 管理员：存入统计（全场数据导出 - 兼容版）
// ========================

let cmd_admin_save_all = seal.ext.newCmdItemInfo();
cmd_admin_save_all.name = "存入统计";
cmd_admin_save_all.help = "。存入统计 （管理员功能：自动以字段格式导出全场玩家历史统计数据）";
cmd_admin_save_all.solve = (ctx, msg, cmdArgs) => {
    // 1. 权限校验
    if (ctx.privilegeLevel < 40) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，此指令仅限管理员使用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const stats = getUserStats(); // 获取用户统计
    const storage = JSON.parse(ext.storageGet("a_private_group") || "{}"); // 模仿你的“时间线”代码获取角色绑定
    const userKeys = Object.keys(stats);

    if (userKeys.length === 0) {
        seal.replyToSender(ctx, msg, "📂 统计数据库为空，暂无数据。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, "❌ 请在群内使用此指令以支持合并转发。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 构造数据节点
    const botUid = ctx.endPoint.userId;
    const nodes = [];

    // 添加页眉
    nodes.push({
        type: "node",
        data: {
            name: "系统档案库",
            uin: botUid,
            content: `📜 长日系统 - 全员历史统计导出\n共计记录：${userKeys.length} 位角色`
        }
    });

    // 遍历数据生成节点
    userKeys.forEach((key) => {
        const data = stats[key];
        const parts = key.split(':');
        const roleName = parts[1];
        
        // 模仿反查QQ/UID逻辑
        let bindQQ = "未知";
        if (storage[platform] && storage[platform][roleName]) {
            bindQQ = storage[platform][roleName][0];
        }

        // 构造字段化文本
        let fieldText = `[角色名]：${roleName}\n`;
        fieldText += `[QQ号]：${bindQQ}\n`;
        fieldText += `[总回复数]：${data.totalReplies}\n`;
        fieldText += `[总字数]：${data.totalWords}\n`;
        fieldText += `[平均字数]：${data.avgWords}\n`;
        fieldText += `[平均回复时间]：${data.avgReplyTimeMin}分钟\n`;
        fieldText += `[CSV行]：${roleName},${bindQQ},${data.totalReplies},${data.totalWords},${data.avgWords},${data.avgReplyTimeMin}`;

        nodes.push({
            type: "node",
            data: {
                name: roleName,
                uin: (bindQQ !== "未知" ? bindQQ : botUid),
                content: fieldText
            }
        });
    });

    // 3. 模仿“时间线”逻辑，通过 ws 发送合并转发
    const rawGroupId = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const postData = {
        action: "send_group_forward_msg",
        params: {
            group_id: rawGroupId,
            messages: nodes
        }
    };

    console.log(`[监听系统] 管理员正在导出全场统计数据...`);
    return ws(postData, ctx, msg, ""); 
};

// 注册指令
ext.cmdMap["存入统计"] = cmd_admin_save_all;

// ========================
// 👑 管理员：查看全员统计（合并转发）
// ========================

let cmd_all_stats = seal.ext.newCmdItemInfo();
cmd_all_stats.name = "查看全员统计";
cmd_all_stats.help = "。查看全员统计 （管理员功能：查看所有玩家数据排名，合并转发形式）";
cmd_all_stats.solve = (ctx, msg, cmdArgs) => {
    // 1. 权限校验
    if (ctx.privilegeLevel < 40) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，此指令仅限管理员使用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const stats = getUserStats();
    const storage = JSON.parse(ext.storageGet("a_private_group") || "{}"); // 用于反查UID显示头像
    const userKeys = Object.keys(stats);

    if (userKeys.length === 0) {
        seal.replyToSender(ctx, msg, "📂 统计数据库为空，暂无玩家数据。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!msg.groupId) {
        seal.replyToSender(ctx, msg, "❌ 请在群内使用此指令。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 数据排序：按总字数从高到低排序
    const sortedKeys = userKeys.sort((a, b) => stats[b].totalWords - stats[a].totalWords);

    // 3. 构造合并转发节点 (模仿时间线逻辑)
    const botUid = ctx.endPoint.userId;
    const nodes = [];

    // 页眉节点
    nodes.push({
        type: "node",
        data: {
            name: "排行榜管家",
            uin: botUid,
            content: `📜 长日系统 - 全员数据排名报告\n(按总字数降序排列)`
        }
    });

    // 遍历排序后的数据
    sortedKeys.forEach((key, index) => {
        const user = stats[key];
        const [platform, roleName] = key.split(':');
        
        // 反查UID以显示对应玩家头像
        let bindUid = botUid;
        if (storage[platform] && storage[platform][roleName]) {
            bindUid = storage[platform][roleName][0];
        }

        let info = `第 ${index + 1} 名：【${roleName}】\n`;
        info += `━━━━━━━━━━━━━━━\n`;
        info += `🔹 总回复：${user.totalReplies} 次\n`;
        info += `🔹 总字数：${user.totalWords} 字\n`;
        info += `🔹 平均字数：${user.avgWords} 字/条\n`;
        info += `🔹 平均耗时：${user.avgReplyTimeMin} 分钟\n`;
        
        // 增加最快/最慢纪录显示
        const sub = user.subtypeStats?.[platform]?.[roleName];
        if (sub) {
            info += `⏱️ 极限：最快 ${sub.fastestReply || '--'} min / 最慢 ${sub.slowestReply || '--'} min`;
        }

        nodes.push({
            type: "node",
            data: {
                name: `排名 ${index + 1} - ${roleName}`,
                uin: bindUid,
                content: info
            }
        });
    });

    // 4. 调用 ws 发送
    const rawGroupId = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const postData = {
        action: "send_group_forward_msg",
        params: {
            group_id: rawGroupId,
            messages: nodes
        }
    };

    return ws(postData, ctx, msg, ""); 
};

// 注册指令
ext.cmdMap["查看全员统计"] = cmd_all_stats;

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
// 📡 全局事件监听
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();
    const platform = msg.platform, uid = msg.sender.userId.replace(`${platform}:`, '');
    const groupId = msg.groupId.replace(`${platform}-Group:`, ''), isAdmin = isUserAdmin(ctx, msg);
    const getS = (k) => JSON.parse(ext.storageGet(k) || (k.includes("list") || k.includes("presets") || k.includes("projects") ? "[]" : "{}"));

    // 1. 回复卡片逻辑 (撤回/点歌/复盘)
    const replyMatch = raw.match(/\[CQ:reply,id=(\-?\d+)\]/);
    if (replyMatch) {
        const wdId = Number(replyMatch[1]);
        if (raw.includes("撤回")) return withdrawMsg(ctx, msg, wdId);
        if (raw.includes("点歌")) {
            const gid = ext.storageGet("song_group_id"), dM = raw.match(/点歌人[:：]\s*(.*?)(?=\s|,|，|留言|$)/), lM = raw.match(/留言[:：]\s*(.*)/);
            if (!gid || !dM || !lM) return seal.replyToSender(ctx, msg, !gid ? "❌ 未配置点歌群" : "⚠️ 格式错误\n正确用法：回复音乐卡片，消息内容写\n点歌人：名字 留言：内容");
            ["temp_target_gid", "temp_task_type", "temp_song_dgr", "temp_song_ly"].forEach((k, i) => ext.storageSet(k, [gid, "song", dM[1].trim(), lM[1].trim()][i]));
            return ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg);
        }
        if (raw.includes("转发复盘")) {
            const bgId = ext.storageGet("background_group_id");
            if (!bgId) return seal.replyToSender(ctx, msg, "未配置目标群");
            ext.storageSet("temp_target_gid", bgId); ext.storageSet("temp_task_type", "forward"); ext.storageSet("temp_source_group_name", ctx.group.groupName);
            let bSched = getS("b_confirmedSchedule");
            Object.values(bSched).flat().forEach(ev => { if(ev.group === groupId && ev.status === "active") ev.fupan = true; });
            ext.storageSet("b_confirmedSchedule", JSON.stringify(bSched));
            ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg);
            return seal.replyToSender(ctx, msg, `已复盘至后台，请尽快结课退群！`);
        }
    }

    // 2. 属性系统 (我创建属性/我的状态/属性变更)
    if (raw.startsWith("我创建属性") && isAdmin) {
        const name = raw.replace("我创建属性", "").trim();
        let pts = getS("sys_attr_presets");
        if (name && !pts.includes(name)) { pts.push(name); ext.storageSet("sys_attr_presets", JSON.stringify(pts)); return seal.replyToSender(ctx, msg, `✅ 已创建属性：${name}`); }
    }
    if (raw === "我的状态") {
        const role = getRoleName(ctx, msg), data = getS("sys_character_attrs"), pts = getS("sys_attr_presets");
        return seal.replyToSender(ctx, msg, role ? `🎭 【${role}】状态\n` + (pts.length ? pts.map(p => `${p}：${data[role]?.[p] || 0}`).join('\n') : "暂无属性") : "❌ 未绑定角色");
    }
    const attrM = raw.match(/^(.+?)[:：](.+?)([+\-]{2})([\d、,，]+)$/);
    if (attrM && isAdmin) {
        const [_, rP, aN, op, vP] = attrM, pts = getS("sys_attr_presets"), priv = getS("a_private_group");
        if (pts.includes(aN)) {
            let data = getS("sys_character_attrs"), res = [], rs = rP === "全体" ? Object.keys(priv[platform] || {}) : rP.split(/[、,，]/).map(r => r.trim());
            const vL = vP.split(/[、,，]/).map(v => parseInt(v));
            rs.forEach((r, i) => { if (priv[platform]?.[r]) { const old = (data[r] = data[r] || {})[aN] || 0, v = isNaN(vL[i]) ? vL[0] : vL[i]; res.push(`${r}：${old}->${(data[r][aN] = op === "++" ? old + v : old - v)}`); } });
            if (res.length) { ext.storageSet("sys_character_attrs", JSON.stringify(data)); return seal.replyToSender(ctx, msg, `${op === "++" ? "📈" : "📉"} ${aN}变更:\n${res.join('\n')}`); }
        }
    }

    // 3. 互动系统 (赠送/短信)
    // 支持「赠送 对方 礼物」和「自定义名赠送 对方 礼物」，排除「道具赠送」
    if (!raw.startsWith("道具赠送")) {
        const giftM = raw.match(/^(.*?)赠送\s+(.+?)\s+(.+)$/);
        if (giftM) {
            const customName = giftM[1].trim() || null;
            return handleNaturalGift(ctx, msg, platform, giftM[2].trim(), giftM[3].trim(), customName);
        }
    }

    const letM = raw.match(/^(.+?)?短信\s*(.+?)\s+([\s\S]+)$/);
    if (letM) {
        // 【修改点】单独读取开关状态
        const allowCustom = ext.storageGet("allow_custom_letter_sign") === "true";
        
        const priv = getS("a_private_group")[platform] || {};
        let snd = "";

        if (allowCustom && letM[1]) {
            // 允许自定义且写了 A 部分，直接取 A
            snd = letM[1].trim();
        } else {
            // 不允许自定义或没写 A，按原逻辑自动识别或校验
            snd = letM[1] ? letM[1].trim() : Object.keys(priv).find(k => priv[k][0] === uid);
        }

        // 【修改点】如果开启了自定义，不再强制要求 snd 必须存在于 priv 绑定中
        if (snd && (allowCustom || priv[snd])) {
            return handleNaturalChaosLetter(ctx, msg, platform, snd, letM[2].trim(), letM[3].trim());
        } else {
            return seal.replyToSender(ctx, msg, "❌ 角色识别失败");
        }
    }

    // 4. 约会/邀约/微信/心愿/发帖/心动信（无指令前缀触发）
    const makeFakeCmdArgs = (parts) => ({
        getArgN: (n) => parts[n - 1] || "",
        args: parts
    });

    if (raw.startsWith("电话")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_phone.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("私约")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_appointment_private.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("微信")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_wechat.solve(ctx, msg, makeFakeCmdArgs([rest]));
    }

    if (raw.startsWith("挂心愿")) {
        const rest = raw.slice(3).trim();
        if (rest) return cmd_post_wish.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw === "看心愿") {
        return ext.cmdMap["看心愿"].solve(ctx, msg);
    }

    if (raw.startsWith("摘心愿")) {
        const rest = raw.slice(3).trim();
        return cmd_pick_wish.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw.startsWith("撤心愿")) {
        const rest = raw.slice(3).trim();
        return cmd_withdraw_wish.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw.startsWith("发帖")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_post_forum.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("回复帖子")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_reply_post.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("发送心动信")) {
        return cmd_send_lovemail.solve(ctx, msg, makeFakeCmdArgs([]));
    }

    if (raw === "礼物商城") return cmd_view_preset_gifts.solve(ctx, msg);
    if (raw === "图鉴" || raw === "我的图鉴") return cmd_view_my_gift_collection.solve(ctx, msg);
    if (raw.startsWith("购买")) {
        const rest = raw.slice(2).trim();
        if (rest) {
            const parts = rest.split(/\s+/);
            return cmd_purchase.solve(ctx, msg, { getArgN: (n) => parts[n - 1] || "", args: parts });
        }
    }
    if (raw.startsWith("补货") && isAdmin) {
        const shopModeNc = ext.storageGet("shop_mode") || "抽卡";
        if (shopModeNc !== "商城") return seal.replyToSender(ctx, msg, "⚠️ 补货仅在商城模式下可用。");
        const parts = raw.slice(2).trim().split(/\s+/);
        const target = parts[0], qty = parts[1] ? parseInt(parts[1]) : 10;
        if (!target) return seal.replyToSender(ctx, msg, "用法：补货 名字or编号 数量（默认10）");
        if (isNaN(qty) || qty < 1) return seal.replyToSender(ctx, msg, "❌ 数量必须是正整数");
        const pgNc = JSON.parse(ext.storageGet("preset_gifts") || "{}");
        let gidNc = pgNc[target] ? target : (Object.entries(pgNc).find(([, g]) => g.name === target) || [])[0];
        if (!gidNc) return seal.replyToSender(ctx, msg, `❌ 找不到「${target}」`);
        pgNc[gidNc].stock = (pgNc[gidNc].stock || 0) + qty;
        ext.storageSet("preset_gifts", JSON.stringify(pgNc));
        return seal.replyToSender(ctx, msg, `✅ 「${pgNc[gidNc].name}」补货 ${qty} 件，当前库存：${pgNc[gidNc].stock}`);
    }

    if (raw === "背包") return cmd_backpack.solve(ctx, msg, makeFakeCmdArgs([]));
    if (raw.match(/^背包\s+(礼物|普通道具|道具|特殊道具)$/) ||
        raw.match(/^背包\s+(普通礼物|普通道具|特殊道具)\d+$/)) {
        const parts = raw.split(/\s+/);
        return cmd_backpack.solve(ctx, msg, makeFakeCmdArgs([parts[1]]));
    }

    // 4.5 角色系统（无前缀）
    if (raw.startsWith("创建新角色")) {
        const rest = raw.slice(5).trim();
        if (rest) return cmd_bind_role.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw === "玩家名单") return cmd_role_list.solve(ctx, msg, makeFakeCmdArgs([]));

    if (raw === "地点查看" || raw === "查看地点") {
        return cmdPlace.solve(ctx, msg, makeFakeCmdArgs(["查看"]));
    }

    if (raw.startsWith("申请加入")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_apply_join.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    // 4.6 关系线（无前缀，管理员指令）
    if (raw.startsWith("拉线") && isAdmin) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_add_rel_detail.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("查看关系线")) {
        const rest = raw.slice(5).trim();
        return cmd_view_relationship.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw.startsWith("撤回关系") && isAdmin) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_withdraw_relation.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw === "关系线统计" && isAdmin) {
        return cmd_rel_stats.solve(ctx, msg, makeFakeCmdArgs([]));
    }

    // 4.7 额外账号（无前缀，本人操作）
    if (raw.startsWith("额外账号")) {
        const rest = raw.slice(4).trim();
        const selfRoleName = getRoleName(ctx, msg);
        if (!selfRoleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const extras = store.get("extra_accounts");
        if (rest.startsWith("删除")) {
            const extraQQ = rest.slice(2).trim();
            if (!extraQQ) return seal.replyToSender(ctx, msg, "格式：额外账号 删除 QQ号");
            const extraKey = `${platform}:${extraQQ}`;
            if (extras[extraKey] !== uid) return seal.replyToSender(ctx, msg, `❌ 该账号不是你的额外账号`);
            delete extras[extraKey];
            store.set("extra_accounts", extras);
            return seal.replyToSender(ctx, msg, `✅ 已移除额外账号 ${extraQQ}`);
        }
        if (rest) {
            const extraQQ = rest.trim();
            const extraKey = `${platform}:${extraQQ}`;
            if (extras[extraKey]) return seal.replyToSender(ctx, msg, `❌ 该账号已被绑定为其他角色的额外账号`);
            extras[extraKey] = uid;
            store.set("extra_accounts", extras);
            return seal.replyToSender(ctx, msg, `✅ 已将 ${extraQQ} 绑定为「${selfRoleName}」的额外账号`);
        }
        // 查看自己的额外账号
        const myExtras = Object.entries(extras).filter(([, v]) => v === uid).map(([k]) => k.replace(`${platform}:`, ""));
        return seal.replyToSender(ctx, msg, myExtras.length ? `📱 你的额外账号：\n${myExtras.join("\n")}` : "📭 暂无额外账号");
    }

    // 4.8 角色档案修改（无前缀）
    if (raw.startsWith("修改性别")) {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const val = raw.slice(4).trim();
        if (val !== "男" && val !== "女") return seal.replyToSender(ctx, msg, "性别仅支持：男 / 女");
        setCharProfile(platform, roleName, { gender: val });
        return seal.replyToSender(ctx, msg, `✅ 性别已更新为：${val}`);
    }

    if (raw.startsWith("修改年龄")) {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const val = parseInt(raw.slice(4).trim());
        if (isNaN(val) || val < 0 || val > 200) return seal.replyToSender(ctx, msg, "❌ 请输入有效年龄（0-200）");
        setCharProfile(platform, roleName, { age: val });
        return seal.replyToSender(ctx, msg, `✅ 年龄已更新为：${val}`);
    }

    if (raw.startsWith("修改皮相")) {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const val = raw.slice(4).trim();
        if (!val) return seal.replyToSender(ctx, msg, "请输入明星名，例：修改皮相 刘亦菲");
        const prof = getCharProfile(platform, roleName);
        const now = Date.now();
        const cooldown = 2 * 3600 * 1000;
        if (prof.lookUpdatedAt && now - prof.lookUpdatedAt < cooldown) {
            const remain = Math.ceil((cooldown - (now - prof.lookUpdatedAt)) / 60000);
            return seal.replyToSender(ctx, msg, `⏳ 皮相修改冷却中，还需等待 ${remain} 分钟`);
        }
        setCharProfile(platform, roleName, { look: val, lookUpdatedAt: now });
        return seal.replyToSender(ctx, msg, `✅ 皮相已更新为：${val}`);
    }

    if (raw.startsWith("修改签名")) {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const val = raw.slice(4).trim();
        if (!val) return seal.replyToSender(ctx, msg, "请输入签名内容，例：修改签名 愿岁月温柔以待");
        const prof = getCharProfile(platform, roleName);
        const now = Date.now();
        const cooldown = 12 * 3600 * 1000;
        if (prof.bioUpdatedAt && now - prof.bioUpdatedAt < cooldown) {
            const remain = Math.ceil((cooldown - (now - prof.bioUpdatedAt)) / 60000);
            return seal.replyToSender(ctx, msg, `⏳ 签名修改冷却中，还需等待 ${remain} 分钟`);
        }
        setCharProfile(platform, roleName, { bio: val, bioUpdatedAt: now });
        return seal.replyToSender(ctx, msg, `✅ 签名已更新为：${val}`);
    }

    // 5. 信息收集系统 & 设定NPC
    const projects = getS("sys_info_projects");
    const subM = raw.match(/^我提交\s*(.+?)[:：\s]\s*([\s\S]+)$/);
    if (subM && projects.includes(subM[1].trim())) {
        const t = subM[1].trim(); let d = getS("sys_info_collection");
        (d[t] = d[t] || []).push({ sender: getRoleName(ctx, msg), time: new Date().toLocaleString(), text: subM[2].trim() });
        ext.storageSet("sys_info_collection", JSON.stringify(d)); return seal.replyToSender(ctx, msg, `✅ 已记录至「${t}」。`);
    }

    // --- 所有人可用的查看功能 ---
    if (raw.startsWith("查看收集")) {
        const t = raw.replace("查看收集", "").trim();
        const projectsList = getS("sys_info_projects");
        
        // 1. 如果只输入“查看收集”，列出所有可选项目
        if (!t) {
            return seal.replyToSender(ctx, msg, `📋 可查看的收集项目：\n${projectsList.length ? projectsList.join('\n') : "暂无项目"}`);
        }
        
        // 2. 如果项目存在，展示内容
        if (projectsList.includes(t)) {
            let allInfo = getS("sys_info_collection");
            let records = allInfo[t] || [];
            if (records.length > 0) {
                const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
                const nodes = [
                    { type: "node", data: { name: "长日将尽", uin: "10001", content: `📖 「${t}」共 ${records.length} 条记录` } },
                    ...records.map((item, idx) => ({
                        type: "node",
                        data: {
                            name: item.sender || "未知",
                            uin: "10001",
                            content: `[${idx + 1}] ${item.time}\n${item.text}`
                        }
                    }))
                ];
                ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
                return;
            } else {
                return seal.replyToSender(ctx, msg, `❓ 项目「${t}」目前还没有人提交内容哦。`);
            }
        } else {
            return seal.replyToSender(ctx, msg, `❌ 未找到项目「${t}」，请检查名称是否正确。`);
        }
    }

    // --- 设定 NPC 指令 ---
    const npcM = raw.match(/^设定\s*(.+?)\s*为\s*npc$/i);
    if (npcM && isAdmin) {
        const name = npcM[1].trim(); let npcList = getS("a_npc_list");
        if (!(getS("a_private_group")[platform] || {})[name]) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${name}」`);
        const idx = npcList.indexOf(name);
        if (idx === -1) npcList.push(name); else npcList.splice(idx, 1);
        ext.storageSet("a_npc_list", JSON.stringify(npcList));
        return seal.replyToSender(ctx, msg, `✅ ${name} 的 NPC 身份已${idx === -1 ? '设定' : '取消'}`);
    }

    if (isAdmin) {
        if (raw.startsWith("创建收集") && isAdmin) {
            const pN = raw.replace("创建收集", "").trim();
            if (pN && !projects.includes(pN)) { projects.push(pN); ext.storageSet("sys_info_projects", JSON.stringify(projects)); return seal.replyToSender(ctx, msg, `✅ 已建立项目：${pN}`); }
        }
        let allInfo = getS("sys_info_collection");
        if (raw.startsWith("我清空")) {
            const t = raw.replace("我清空", "").trim();
            if (allInfo[t]) { allInfo[t] = []; ext.storageSet("sys_info_collection", JSON.stringify(allInfo)); return seal.replyToSender(ctx, msg, `🗑️ 已清空「${t}」`); }
        }
    }

    // 5. --- 你的核心私有群监听逻辑 (确保被包裹在 try 中) ---
    try {
        const a_private_group = getS("a_private_group");
        const roleName = Object.entries(a_private_group[platform] || {})
            .find(([_, val]) => val[0] === uid)?.[0];
        
        if (roleName) {
            // 如果找到了对应的角色名，执行原有的 handleReply 转发
            handleReply(platform, groupId, roleName, msg.message);
        }
    } catch (e) {
        console.error('监听系统错误:', e);
    }
};

let cmd_view_timers = seal.ext.newCmdItemInfo();
cmd_view_timers.name = "查看计时器";
cmd_view_timers.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return;

    const timers = JSON.parse(ext.storageGet("group_timers") || "{}"), now = Date.now();
    const tKeys = Object.keys(timers);
    if (!tKeys.length) return seal.replyToSender(ctx, msg, "📭 当前没有活跃的计时器");

    const nodes = [{ type: "node", data: { name: "计时监控中心", uin: "2852199344", content: `📊 运行中：${tKeys.length} 个\n更新：${new Date().toLocaleTimeString()}` } }];

    let totalOverdue = 0;
    tKeys.forEach(gid => {
        const t = timers[gid];
        const detail = Object.entries(t.timerStatus).map(([name, s]) => {
            if (s.status !== "timing") return `✅ ${name}: replied`;
            
            const diff = t.timeoutDuration - (now - s.startTime);
            const isOver = diff < 0;
            if (isOver) totalOverdue++;
            
            return `${isOver ? "🔴" : "⏳"} ${name}: ${Math.abs(Math.round(diff / 60000))}min${isOver ? "!" : ""}`;
        }).join('\n');

        nodes.push({
            type: "node",
            data: { name: `群组 ${gid} | ${t.subtype}`, uin: "10001", content: `📍 模式：${t.timerMode === 'turn_taking' ? '轮流' : '独立'}\n━━━━━━━━━━━━━━━\n${detail}` }
        });
    });

    const gId = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    ws({ action: "send_group_forward_msg", params: { group_id: gId, messages: nodes } }, ctx, msg, "");
    seal.replyToSender(ctx, msg, `✅ 报表已生成\n⏳ 超时：${totalOverdue} 人\n(详情见下方合并消息)`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看计时器"] = cmd_view_timers;

let cmd_remind_timeouts = seal.ext.newCmdItemInfo();
cmd_remind_timeouts.name = "提醒超时";
cmd_remind_timeouts.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "🌸 只有管理员可以呼唤大家哦～");

    const target = cmdArgs.getArgN(1), now = Date.now();
    const timers = JSON.parse(ext.storageGet("group_timers") || "{}");
    const priv = JSON.parse(ext.storageGet("a_private_group") || "{}");
    let sentCount = 0, detail = [];

    for (const [gid, timer] of Object.entries(timers)) {
        if (target && gid !== target) continue;

        const platform = timer.platform;
        const groupReminders = Object.entries(timer.timerStatus).filter(([name, s]) => {
            if (s.status !== "timing") return false;
            const elapsed = now - s.startTime;
            const interval = 3600000; // 默认1小时提醒间隔
            return elapsed > timer.timeoutDuration && (now - (timer.lastRemindTime || 0) > interval);
        });

        groupReminders.forEach(([name, s]) => {
            const elapsed = now - s.startTime;
            const h = Math.floor(elapsed / 3600000), m = Math.floor((elapsed % 3600000) / 60000);
            const timeStr = h > 0 ? `${h}h${m}m` : `${m}m`;

            // 1. 发送给个人小群
            const pGid = priv[platform]?.[name]?.[1];
            if (pGid) {
                const text = `✨ 亲爱的 ${name}，在「${timer.subtype}」里大家等你 ${timeStr} 啦。如果不忙的话，记得回一下小伙伴们哦～ ❤️`;
                const m1 = seal.newMessage(); m1.messageType = "group"; m1.groupId = `${platform}-Group:${pGid}`;
                seal.replyToSender(seal.createTempCtx(ctx.endPoint, m1), m1, text);
            }

            // 2. 发送到公共群
            const m2 = seal.newMessage(); m2.messageType = "group"; m2.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m2), m2, `🌷 温馨提示：${name} 已经忙碌 ${timeStr} 啦，我们再耐心等一下ta吧～`);

            s.remindedTimes = (s.remindedTimes || 0) + 1;
            sentCount++;
        });

        if (groupReminders.length) {
            timer.lastRemindTime = now;
            detail.push(`群组 ${gid}: ${groupReminders.map(r => r[0]).join("、")}`);
        }
    }

    if (sentCount > 0) {
        ext.storageSet("group_timers", JSON.stringify(timers));
        seal.replyToSender(ctx, msg, `💖 提醒任务完成！\n共送出 ${sentCount} 份温柔提醒：\n${detail.join('\n')}\n大家一定会感受到的～ 🌟`);
    } else {
        seal.replyToSender(ctx, msg, "🌙 检查了一圈，现在大家都很守时，不需要打扰呢～");
    }
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

// ========================
// 核心指令：微信
// ========================

let cmd_wechat = seal.ext.newCmdItemInfo();
cmd_wechat.name = "微信";
cmd_wechat.help = "。微信 对方角色名 —— 与对方建立长期微信群聊\n示例：。微信 张三";

cmd_wechat.solve = (ctx, msg, cmdArgs) => {
    // 1. 功能开关（默认开启）
    let config = JSON.parse(ext.storageGet("global_feature_toggle") || "{}");
    if (config.enable_wechat === false) {
        seal.replyToSender(ctx, msg, "💬 微信功能已关闭");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    // 获取发送者角色名
    const sendname = Object.entries(a_private_group[platform]).find(([_, val]) => val[0] === uid)?.[0];
    if (!sendname) {
        seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查用户是否被禁止
    const blockMap = JSON.parse(ext.storageGet("feature_user_blocklist") || "{}");
    if (blockMap[sendname] && blockMap[sendname].enable_wechat === false) {
        seal.replyToSender(ctx, msg, "🚫 您已被禁止使用微信功能");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取目标角色名
    const toname = cmdArgs.getArgN(1);
    if (!toname) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    // 检查目标是否存在
    if (!a_private_group[platform][toname]) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${toname}」，请确认对方已注册`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 不能邀请自己
    if (toname === sendname) {
        seal.replyToSender(ctx, msg, "❌ 不能邀请自己");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查两人是否已有活跃微信群
    const existing = checkWechatBetweenUsers(platform, sendname, toname);
    if (existing.exists) {
        seal.replyToSender(ctx, msg, `⚠️ 你和「${toname}」之间已存在活跃微信群：${existing.groupId}（主题：${existing.topic}）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取可用群号（排除占用和微信占用）
    const groupList = JSON.parse(ext.storageGet("group") || "[]");
    const available = groupList.filter(g => !g.endsWith("_占用") && !g.endsWith("_微信占用"));
    if (available.length === 0) {
        seal.replyToSender(ctx, msg, "⚠️ 暂无可用群号，请联系管理员添加备用群");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 分配群号
    const gid = available[Math.floor(Math.random() * available.length)];
    groupList.splice(groupList.indexOf(gid), 1);
    groupList.push(gid + "_微信占用");
    ext.storageSet("group", JSON.stringify(groupList));

    // 创建微信群记录
    const wechatGroups = JSON.parse(ext.storageGet("wechat_groups") || "{}");
    if (!wechatGroups[platform]) wechatGroups[platform] = {};
    const now = new Date();
    wechatGroups[platform][gid] = {
        id: gid,
        creator: sendname,
        creator_id: uid,
        topic: "",
        participants: [sendname, toname],
        status: "active",
        created_at: now.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }),
        created_timestamp: now.getTime()
    };
    ext.storageSet("wechat_groups", JSON.stringify(wechatGroups));

    // 通知群内所有成员（群公告）
    const groupNotice = `💬 微信群创建成功\n\n📱 群号：${gid}\n👤 创建者：${sendname}\n👥 成员：${sendname}、${toname}\n\n💡 这是一个长期群聊，无时间限制，每个微信关系只能有一个活跃群。`;
    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${gid}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    seal.replyToSender(groupCtx, groupMsg, groupNotice);
    // 设置群名
    setGroupName(groupCtx, groupMsg, gid, `微信:${sendname}&${toname}`);

    // 通知双方的个人群
    const participants = [sendname, toname];
    for (let participant of participants) {
        const info = a_private_group[platform][participant];
        if (info) {
            const [pUid, pGid] = info;
            const notifyMsg = seal.newMessage();
            notifyMsg.messageType = "group";
            notifyMsg.groupId = `${platform}-Group:${pGid}`;
            notifyMsg.sender = {};
            notifyMsg.sender.userId = `${platform}:${pUid}`;
            const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
            const personalNotice = `💬 你已被加入微信群\n📱 群号：${gid}\n👤 创建者：${sendname}\n👥 成员：${sendname}、${toname}\n\n💡 这是一个长期群聊，无时间限制。`;
            seal.replyToSender(notifyCtx, notifyMsg, personalNotice);
        }
    }

    // 回复创建者
    seal.replyToSender(ctx, msg, `✅ 微信群创建成功！\n📱 群号：${gid}\n👥 成员：${sendname}、${toname}`);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["微信"] = cmd_wechat;

// ========================
// 🗨️ 秘密论坛系统 (WS公告集成版)
// ========================

// --- 📋 系统配置 ---
seal.ext.registerIntConfig(ext, "forumMaxLength", 500, "论坛内容最大长度", "发帖和回复的最大字符数");


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
    if (roleName && !isUserFeatureEnabled(roleName, "enable_forum")) {
        seal.replyToSender(ctx, msg, "🚫 你的论坛功能已被关闭。");
        return seal.ext.newCmdExecuteResult(true);
    }
    let author, content;

    if (cmdArgs.args.length > 1) {
        author = cmdArgs.getArgN(1);
        content = msg.message.replace(/^[。.]?发帖\s+\S+\s*/, "").trim();
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
        content = msg.message.replace(/^[。.]?回复帖子\s+\S+\s+\S+\s*/, "").trim();
    } else {
        author = roleName;
        content = msg.message.replace(/^[。.]?回复帖子\s+\S+\s*/, "").trim();
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

// ========================
// 💌 心动信系统
// ========================
seal.ext.registerBoolConfig(ext, "开启心动信曝光", false, "开启后，信件有概率同步发送到指定的公告群");
seal.ext.registerIntConfig(ext, "曝光概率", 10, "每封信件被公开的概率 (0-100)");

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

    // 身份核验
    const senderRoleName = Object.entries(a_private_group[platform] || {})
        .find(([_, val]) => val[0] === uid)?.[0];
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 远方的旅人，寄信前请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const raw = msg.message.trim();

    // 解析标签
    const getTag = (tag) => {
        const regex = new RegExp(`【${tag}】([\\s\\S]*?)(?=【|$)`, "i");
        const match = raw.match(regex);
        return match ? match[1].trim() : null;
    };

    const signature = getTag("署名") || "匿名";
    const receiver = getTag("发送对象") || getTag("收件人");
    let content = getTag("内容") || "";

    if (!receiver) {
        let helpMsg = `⚠️ 格式错误！请指定发送对象。\n\n标准格式：\n。发送心动信\n【发送对象】角色名\n【内容】想说的话\n【署名】自定义昵称（选填）\n`;
        seal.replyToSender(ctx, msg, helpMsg);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!a_private_group[platform] || !a_private_group[platform][receiver]) {
        seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${receiver}」的投递地址，请确认名字是否正确。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ========== 按游戏天数进行限额检查 ==========
    // 获取当前游戏天数（例如 "D0", "D1"）
    let globalDay = ext.storageGet("global_days");
    if (!globalDay) {
        seal.replyToSender(ctx, msg, "⚠️ 当前未设置游戏天数，请联系管理员设置「。设置天数 D0」");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 读取上限配置
    const dayLimits = JSON.parse(ext.storageGet("lovemail_day_limits") || "{}");
    const defaultLimit = parseInt(ext.storageGet("lovemail_default_limit") || "3");
    let maxPerDay = dayLimits[globalDay] !== undefined ? dayLimits[globalDay] : defaultLimit;
    if (maxPerDay < 1) maxPerDay = 1; // 安全保护

    // 读取该用户在当前游戏天数内已发送的数量
    let dayCounts = JSON.parse(ext.storageGet("lovemail_day_counts") || "{}");
    if (!dayCounts[uid]) dayCounts[uid] = {};
    const currentCount = dayCounts[uid][globalDay] || 0;

    if (currentCount >= maxPerDay) {
        seal.replyToSender(ctx, msg, `📪 在当前游戏天数 ${globalDay} 中，你已投稿 ${currentCount} 封（上限 ${maxPerDay} 封）。请等待下一天再试。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ========== 保存信件 ==========
    const mailKey = "lovemail_pool";
    let records = JSON.parse(ext.storageGet(mailKey) || "[]");
    records.push({
        uid,
        receiver,
        content,
        signature,
        gameDay: globalDay,          // 记录所属游戏天数（便于后续统计）
        timestamp: Date.now()
    });
    ext.storageSet(mailKey, JSON.stringify(records));

    // 更新该用户在当前游戏天数内的计数
    dayCounts[uid][globalDay] = currentCount + 1;
    ext.storageSet("lovemail_day_counts", JSON.stringify(dayCounts));

    // 回复用户
    let reply = `💌 心动信已成功投递至「${receiver}」的信箱！\n`;
    reply += `📝 署名：${signature}\n`;
    reply += `📅 游戏天数：${globalDay}（今日剩余次数：${maxPerDay - (currentCount + 1)}/${maxPerDay}）\n`;
    reply += `✨ 提示：管理员统一送出前，你仍可以使用「。撤回心动信」取消本次投递。`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["发送心动信"] = cmd_send_lovemail;

function generateMailReport(records, title = "📮 心动信派送清单") {
    if (!records?.length) return [];

    // 分组（一行搞定）
    const mailBox = records.reduce((map, r) => ((map[r.receiver] ??= []).push(r), map), {});

    const nodes = [{
        type: "node",
        data: {
            name: "心动邮局·系统日志",
            uin: "2852199344",
            content: `${title}\n🕐 ${new Date().toLocaleString()}\n📬 待派送信件总数：${records.length} 封\n━━━━━━━━━━━━━━━`
        }
    }];

    const MAX = 1200;
    for (const [receiver, mails] of Object.entries(mailBox)) {
        let text = `👤 收件人：${receiver}\n📨 信件数量：${mails.length} 封\n┈┈┈┈┈┈┈┈┈┈\n`;
        let part = 1;

        mails.forEach((mail, idx) => {
            const letter = `【信件 ${idx + 1}】\n📝 署名：${mail.signature}\n📜 内容：${mail.content}\n${idx < mails.length - 1 ? '┈┈┈┈┈┈┈┈┈┈\n' : ''}`;
            if ((text + letter).length > MAX) {
                nodes.push({ type: "node", data: { name: `致 ${receiver} 的信件 (分册 ${part})`, uin: "10001", content: text.trim() } });
                text = `👤 收件人：${receiver} (接前文)\n┈┈┈┈┈┈┈┈┈┈\n${letter}`;
                part++;
            } else text += letter;
        });

        nodes.push({ type: "node", data: { name: part === 1 ? `致 ${receiver} 的信件` : `致 ${receiver} 的信件 (终卷)`, uin: "10001", content: text.trim() } });
    }
    return nodes;
}

let cmd_stat_lovemail = seal.ext.newCmdItemInfo();
cmd_stat_lovemail.name = "信箱统计";
cmd_stat_lovemail.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "✨ 抱歉，这里只有邮局守护者才能进入哦。");

    const records = JSON.parse(ext.storageGet("lovemail_pool") || "[]");
    if (!records.length) return seal.replyToSender(ctx, msg, "🕊️ 此时的邮局静悄悄的，还没有待投递的心意。");

    const nodes = generateMailReport(records, "🌸 心动邮局·巡检手记");
    nodes[0].data.content = `🌸 此时此刻，共有 ${records.length} 份心意正在等待传递\n🕰️ 巡检时间：${new Date().toLocaleString()}\n愿每一份温柔都能准时抵达。`;

    const targetGid = msg.groupId.replace(/\D/g, "");
    for (let i = 0; i < nodes.length; i += 90) {
        ws({ action: "send_group_forward_msg", params: { group_id: parseInt(targetGid, 10), messages: nodes.slice(i, i + 90) } }, ctx, msg, "");
    }

    const receiverCount = new Set(records.map(r => r.receiver)).size;
    seal.replyToSender(ctx, msg, `✅ 统计报表已封缄完毕\n📮 发现 ${receiverCount} 位收件人的小小秘密\n✨ 巡检记录共计 ${nodes.length} 页，请您审阅。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["信箱统计"] = cmd_stat_lovemail;

// === 玩家功能：查看我的信件 ===
let cmd_view_mylovemails = seal.ext.newCmdItemInfo();
cmd_view_mylovemails.name = "查看信箱";
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
ext.cmdMap["查看信箱"] = cmd_view_mylovemails;

// === 玩家功能：撤回信件 ===
let cmd_revoke_lovemail = seal.ext.newCmdItemInfo();
cmd_revoke_lovemail.name = "撤回心动信";
cmd_revoke_lovemail.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    let records = JSON.parse(ext.storageGet("lovemail_pool") || "[]");

    const my = records.filter(r => r.uid === uid);
    if (isNaN(idx) || idx < 0 || idx >= my.length) {
        return seal.replyToSender(ctx, msg, "⚠️ 请输入正确的序号，例如：。撤回心动信 1");
    }

    const targetMail = my[idx];                     // 获取完整信件对象
    const targetTimestamp = targetMail.timestamp;
    const finalRecords = records.filter(r => r.timestamp !== targetTimestamp);
    
    // ========== 恢复该信件所属游戏天数的发送次数 ==========
    let dayCounts = JSON.parse(ext.storageGet("lovemail_day_counts") || "{}");
    const gameDay = targetMail.gameDay;             // 信件发送时的游戏天数
    if (dayCounts[uid] && dayCounts[uid][gameDay] && dayCounts[uid][gameDay] > 0) {
        dayCounts[uid][gameDay]--;
        if (dayCounts[uid][gameDay] === 0) {
            delete dayCounts[uid][gameDay];
        }
        if (Object.keys(dayCounts[uid]).length === 0) {
            delete dayCounts[uid];
        }
        ext.storageSet("lovemail_day_counts", JSON.stringify(dayCounts));
    }
    
    ext.storageSet("lovemail_pool", JSON.stringify(finalRecords));
    seal.replyToSender(ctx, msg, `✅ 已成功撤回发送给「${targetMail.receiver}」的信件。\n📪 已恢复你在「${gameDay}」的 1 次发送机会。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["撤回心动信"] = cmd_revoke_lovemail;


let loveMailTimer = null; // 全局定时器句柄

/**
 * 核心工具函数：安全地“借”一个 EndPoint
 * 能够有效避免 seal.createTempCtx(undefined, ...) 导致的 nil pointer 崩溃
 */
function getSafeEndPoint(platform = "QQ") {
    const eps = seal.getEndPoints();
    if (!eps || eps.length === 0) return null;

    // 1. 优先寻找对应平台且在线的 (state 1 为在线)
    let target = eps.find(e => e.platform === platform && e.state === 1);
    
    // 2. 找不到就找任何一个在线的
    if (!target) target = eps.find(e => e.state === 1);
    
    // 3. 还找不到就拿第一个 (最后的保底)
    if (!target) target = eps[0];

    return target;
}

function registerLoveMailSystem() {
    
    if (loveMailTimer) {
        clearInterval(loveMailTimer);
        loveMailTimer = null;
    }

    let lastTriggerMinute = -1;

    loveMailTimer = setInterval(() => {
        // --- 1. 检查开关 ---
        if (!isLoveMailEnabled()) return;

        const now = new Date();
        const currentHour = now.getHours();
        const currentMinute = now.getMinutes();
        const currentTimeTotal = currentHour * 60 + currentMinute;

        // 避免同一分钟重复触发
        if (currentMinute === lastTriggerMinute) return;

        // --- 2. 读取并解析派送时间 (增加容错处理) ---
        let deliveryTimeRaw = ext.storageGet("lovemail_delivery_time") || "\"22:00\"";
        let deliveryTime = "22:00";
        try {
            // 彻底清洗可能存在的冗余引号
            deliveryTime = JSON.parse(deliveryTimeRaw).replace(/\"/g, "");
        } catch (e) {
            deliveryTime = "22:00";
        }

        const timeParts = deliveryTime.split(':').map(Number);
        if (timeParts.length !== 2) return;
        const [targetH, targetM] = timeParts;
        const targetTimeTotal = targetH * 60 + targetM;

        const getOffsetTotal = (offset) => {
            let t = targetTimeTotal + offset;
            if (t < 0) t += 1440;
            return t % 1440;
        };

        // --- 3. 逻辑检查点 (Log监测) ---

        // A. 正式派送时间
        if (currentTimeTotal === targetTimeTotal) {
            console.log(`[心动信箱] 【命中目标】当前时间 ${currentHour}:${currentMinute}，开始执行自动派送...`);
            const backgroundGroupId = JSON.parse(ext.storageGet("background_group_id") || "null");
            
            try {
                const result = performLoveMailDelivery(null, { platform: "QQ" }, backgroundGroupId); 
                console.log(`[心动信箱] 自动派送任务结束，反馈结果: ${JSON.stringify(result)}`);
            } catch (err) {
                console.error(`[心动信箱] 自动派送执行期间发生异常: ${err.message}`);
            }
            lastTriggerMinute = currentMinute;
        }
        // B. 派送预告 (提前5分钟)
        else if (currentTimeTotal === getOffsetTotal(-5)) {
            console.log(`[心动信箱] 触发5分钟预告推送...`);
            const announceGid = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
            if (announceGid) {
                sendTextToGroup("QQ", announceGid, `📬 邮差正在整理信箱，心动信件即将在 5 分钟后开始派送，请注意查收。`);
            }
            lastTriggerMinute = currentMinute;
        } 
        // C. 截稿提醒 (提前10分钟)
        else if (currentTimeTotal === getOffsetTotal(-10)) {
            console.log(`[心动信箱] 触发10分钟截稿提醒...`);
            const platform = "QQ";
            const groups = JSON.parse(ext.storageGet("a_private_group") || "{}")[platform] || {};
            const targetGids = [...new Set(Object.values(groups).map(v => v[1]))];
            targetGids.forEach(gid => {
                sendTextToGroup(platform, gid, `⌛ 投递截止预告：\n心动信箱将于 10 分钟后截止收稿并开始派送，还没投递的小伙伴要抓紧咯～`);
            });
            lastTriggerMinute = currentMinute;
        }

    }, 30000); // 30秒轮询一次

    console.log(`[心动信箱] 轮询系统已启动。当前系统时间: ${new Date().getHours()}:${new Date().getMinutes()}`);
    console.log(`[心动信箱] 设定派送时间: ${ext.storageGet("lovemail_delivery_time") || "未设定(默认22:00)"}`);
}

function performLoveMailDelivery(ctx, msg, backgroundGroupId) {
    const platform = msg?.platform ?? "QQ";
    const mailKey = "lovemail_pool";
    
    let records = [];
    try {
        records = JSON.parse(ext.storageGet(mailKey) || "[]");
    } catch(e) {
        console.error(`[心动信箱] 无法读取信件池: ${e.message}`);
    }

    console.log(`[心动信箱] 进入派送函数，信件池现有封数: ${records.length}`);

    if (!records.length) {
        return { success: 0, fail: 0, empty: true, status: "信池为空" };
    }

    // 获取新鲜的 EndPoint，确保上下文不为空
    const ep = (ctx && ctx.endPoint) ? ctx.endPoint : getSafeEndPoint(platform);
    if (!ep) {
        console.error("[心动信箱] 致命错误：无可用的 EndPoint，派送中止");
        return { success: 0, fail: 0, status: "找不到EndPoint" };
    }

    const sendForward = (gid, nodes) => {
        const raw = gid.toString().replace(/\D/g, "");
        const m = seal.newMessage();
        m.messageType = "group";
        m.groupId = `${platform}-Group:${raw}`;
        const c = seal.createTempCtx(ep, m);
        ws({ action: "send_group_forward_msg", params: { group_id: parseInt(raw, 10), messages: nodes } }, c, m, "");
    };

    // 1. 发送后台清单 (如果配置了)
    if (backgroundGroupId && records.length) {
        if (typeof generateMailReport === 'function') {
            const reportNodes = generateMailReport(records, "📋 心动信自动派送清单");
            if (reportNodes.length) sendForward(backgroundGroupId, reportNodes);
        }
    }

    const a_private_group = JSON.parse(ext.storageGet("a_private_group") || "{}");
    const isPublicEnabled = seal.ext.getBoolConfig(ext, "开启心动信曝光");
    const publicChance = seal.ext.getIntConfig(ext, "曝光概率");
    let announceGroupId = JSON.parse(ext.storageGet("adminAnnounceGroupId") || "null");
    if (!announceGroupId || announceGroupId === "null") announceGroupId = null;

    const mailBox = records.reduce((map, r) => ((map[r.receiver] ??= []).push(r), map), {});
    let success = 0, fail = 0, publicCount = 0;
    const publicNodes = [];

    // 2. 遍历信箱派送
    for (const [receiver, mails] of Object.entries(mailBox)) {
        const addr = a_private_group[platform]?.[receiver];
        if (addr) {
            const targetGidRaw = addr[1].replace(/\D/g, "");
            const personalNodes = [{ type: "node", data: { name: "心动邮局·派送员", uin: "2852199344", content: `💌 亲爱的 ${receiver}，你有一份包含 ${mails.length} 封信件的包裹待启封。` } }];
            
            mails.forEach((mail, idx) => {
                personalNodes.push({ type: "node", data: { name: `第 ${idx + 1} 封信件`, uin: "10001", content: `「 ${mail.content} 」\n┈┈┈┈┈┈┈┈┈┈┈┈\n📝 署名：${mail.signature}` } });
                success++;
                if (isPublicEnabled && announceGroupId) {
                    if (Math.floor(Math.random() * 100) + 1 <= publicChance) {
                        publicCount++;
                        publicNodes.push({ type: "node", data: { name: "飘落的信笺", uin: "2852199344", content: `📩 寄给「${receiver}」的心动信\n来自「${mail.signature}」\n内容：「${mail.content}」` } });
                    }
                }
            });
            sendForward(targetGidRaw, personalNodes);
        } else {
            fail += mails.length;
        }
    }

    // 3. 公共曝光
    if (publicNodes.length && announceGroupId) {
        sendForward(announceGroupId, [{ type: "node", data: { name: "心动天使", uin: "2852199344", content: `✨ 哎呀，有 ${publicNodes.length} 份心意在飞往信箱的途中，不小心飘落到了公告区...` } }, ...publicNodes]);
    }
    
    // 4. 清理并反馈
    ext.storageSet(mailKey, "[]");
    return { success, fail, publicCount, empty: false, status: "派送完成" };
}

// 辅助函数：发文本到群
const sendTextToGroup = (platform, gid, text) => {
    try {
        const ep = getSafeEndPoint(platform);
        if (!ep) return;
        const target = `${platform}-Group:${gid.toString().replace(/\D/g, "")}`;
        const m = seal.newMessage();
        m.messageType = "group";
        m.groupId = target;
        seal.replyToSender(seal.createTempCtx(ep, m), m, text);
    } catch (e) {
        console.error(`[LoveMail] sendTextToGroup 异常:`, e);
    }
};

// 功能开关检查
const isLoveMailEnabled = () => JSON.parse(ext.storageGet("global_feature_toggle") || "{}").enable_lovemail !== false;

// 统一送心动信指令
let cmd_deliver_lovemail = seal.ext.newCmdItemInfo();
cmd_deliver_lovemail.name = "统一送心动信";
cmd_deliver_lovemail.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足。");
    const result = performLoveMailDelivery(ctx, msg);
    if (result.empty) {
        seal.replyToSender(ctx, msg, "📭 信箱空空如也。");
    } else {
        seal.replyToSender(ctx, msg, `📬 手动投递完成！结果: ${result.status} (成功 ${result.success} 封)`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["统一送心动信"] = cmd_deliver_lovemail;

registerLoveMailSystem();

// ========================
// 🎭 杂项管理指令
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
// 📖 指令指南（合并转发）
// ========================
let cmd_guide = seal.ext.newCmdItemInfo();
cmd_guide.name = "指令指南";
cmd_guide.solve = (ctx, msg) => {
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const bot = "长日将尽", uin = "10001";

    const section = (title, lines) => ({
        type: "node",
        data: { name: bot, uin, content: `${title}\n${"━".repeat(14)}\n${lines.join("\n")}` }
    });

    const nodes = [
        { type: "node", data: { name: bot, uin, content: `📖 长日指令指南\n${"━".repeat(14)}\n以下指令无需句号，直接发送消息即可触发。` } },
        section("🌟 入门", [
            "创建新角色 角色名",
            "  例：创建新角色 张三",
            "  注册角色，获得初始档案（性别/年龄/皮相）",
            "",
            "修改性别 男/女",
            "修改年龄 数字",
            "修改皮相 明星名  （2小时冷却）",
            "修改签名 内容     （12小时冷却）",
            "",
            "额外账号 QQ号",
            "  将另一个QQ绑定为当前角色的别号",
            "额外账号 删除 QQ号",
            "额外账号  （不带参数→查看已有）",
            "",
            "玩家名单",
            "  查看所有已注册角色及其档案",
            "",
            "地点查看",
            "  查看当前可用地点列表",
        ]),
        section("🔗 关系线", [
            "查看关系线",
            "  查看你的所有关系对象（列表）",
            "",
            "查看关系线 角色名",
            "  查看与该角色的详细关系记录（合并转发）",
        ]),
        section("💕 约会与邀约", [
            "电话 时间 对方名 [标题]",
            "  例：电话 1400-1500 张三",
            "  例：电话 1400-1500 张三/李四 一起聊聊",
            "",
            "私约 时间 地点 对方名[/对方2/...]",
            "  例：私约 1400-1500 咖啡厅 张三",
            "",
            "申请加入 角色名 时间点",
            "  申请加入已有约会",
            "  例：申请加入 张三 14:30",
        ]),
        section("💬 微信长期群", [
            "微信 对方名",
            "  例：微信 张三",
        ]),
        section("🌠 心愿系统", [
            "挂心愿 时间 地点 内容",
            "  例：挂心愿 1400-1500 图书馆 想找人聊聊",
            "",
            "看心愿  （查看所有漂流心愿）",
            "摘心愿 编号  （例：摘心愿 A1B2C3）",
            "撤心愿 [编号]  （不带编号→列出自己的心愿）",
        ]),
        section("📱 短信", [
            "[署名]短信 收信人 内容",
            "  例：张三短信 李四 你好！",
            "  不写署名则自动使用角色名",
        ]),
        section("🎒 背包与物品", [
            "抽取  （从物品池随机获得普通物品）",
            "抽取次数  （查看今日剩余次数）",
            "",
            "背包  （总览）",
            "背包 礼物 / 普通道具 / 道具 / 特殊道具",
            "背包 普通礼物1 / 普通道具1 / 特殊道具1  （查看详情）",
            "",
            "道具赠送 对方名 物品名",
            "  例：道具赠送 张三 玫瑰",
            "",
            "赠送 对方名 礼物内容",
            "  叙事礼物（有冷却与每日上限）",
            "  例：赠送 张三 一束花",
            "  例：张三赠送 李四 #1",
            "",
            "使用 物品名 [参数]",
            "  例：使用 万能钥匙 图书馆",
        ]),
        section("🛒 礼物商城", [
            "礼物商城",
            "  抽卡模式：每人随机抽一件礼物，自动加入图鉴",
            "  商城模式：展示所有在售商品及库存价格",
            "",
            "购买 编号or名字 [数量]  （仅商城模式）",
            "  例：购买 #1 3  /  购买 玫瑰花",
            "",
            "图鉴  （查看收藏进度与全服热度排名）",
            "",
            "赠送 对方 #编号",
            "  抽卡模式：图鉴内礼物无限赠送",
            "  商城模式：消耗背包内一件礼物",
        ]),
        section("🗨️ 论坛系统", [
            "发帖 内容",
            "  例：发帖 今天天气真好",
            "发帖 署名 内容",
            "  例：发帖 张三 今天天气真好",
            "",
            "回复帖子 贴号 内容",
            "  例：回复帖子 A1B2C 同感！",
            "回复帖子 贴号 署名 内容",
        ]),
        section("💌 心动信", [
            "发送心动信",
            "【发送对象】角色名",
            "【内容】想说的话（支持空行）",
            "【署名】自定义昵称（选填）",
        ]),
        section("📋 信息收集", [
            "我提交 项目名: 内容",
            "  例：我提交 问卷: 我选A",
            "",
            "查看收集          → 列出所有项目",
            "查看收集 项目名   → 查看该项目全部内容",
        ]),
    ];

    ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["指令指南"] = cmd_guide;

// ========================
// 👑 管理指令（合并转发）
// ========================
let cmd_admin_guide = seal.ext.newCmdItemInfo();
cmd_admin_guide.name = "管理指令";
cmd_admin_guide.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const bot = "长日将尽", uin = "10001";

    const section = (title, lines) => ({
        type: "node",
        data: { name: bot, uin, content: `${title}\n${"━".repeat(14)}\n${lines.join("\n")}` }
    });

    const nodes = [
        { type: "node", data: { name: bot, uin, content: `👑 长日管理指令指南\n${"━".repeat(14)}\n以下指令均需加句号前缀，且仅限管理员使用。` } },
        section("🔑 管理员账户", [
            "。授予管理员 QQ号 密码",
            "  将指定 QQ 设为临时管理员",
            "",
            "。收回管理员 QQ号 密码",
            "  撤销指定 QQ 的管理员身份",
            "",
            "。管理员列表",
            "  查看当前所有管理员",
            "",
            "。清空管理员 密码",
            "  清空所有平台的管理员",
            "",
            "。更改密令 新密码",
            "  更改管理员授权密码（至少4位）",
        ]),
        section("🚫 功能权限管理", [
            "。功能权限 角色名 功能 开启/关闭",
            "  功能可选：礼物 / 发起邀约 / 寄信 / 心愿 / 心动信",
            "            论坛 / 商城购买 / 抽取 / 全部",
            "  例：。功能权限 张三 论坛 关闭",
            "  例：。功能权限 张三 全部 关闭  （一键阻断）",
            "",
            "。查看功能权限",
            "  查看所有被设置过权限的角色",
            "",
            "。查看锁定 角色名",
            "  查看指定角色的时间段锁定情况",
            "",
            "。查看他人时间线 角色名",
            "  查看指定角色的全部时间安排",
        ]),
        section("⚙️ 系统设置（长日设置）", [
            "。设置 基础 / 互动 / 信件 / 公告 / 道具 / 群组",
            "  进入对应模块的设置面板",
            "",
            "。设置天数 D1 / D2 / D3...",
            "  切换当前游戏天数",
            "",
            "。开启自动天数 / 。关闭自动天数",
            "  控制每天 23:59 自动推进天数",
            "",
            "。设置信箱上限 D0:3 D1:5...",
            "  设置各天数的心动信每日上限",
            "  例：。设置信箱上限 默认 3",
            "",
            "。master jsclear 插件名字",
            "  重置插件存储（替代原强硬初始化）",
        ]),
        section("📊 数据统计", [
            "。存入统计",
            "  将全场玩家历史数据导出为字段格式",
            "",
            "。查看全员统计",
            "  查看所有玩家数据排名（合并转发）",
        ]),
        section("📢 群管功能", [
            "。群公告发布 内容",
            "  在当前群发布公告",
            "",
            "。群公告发布 权限切换",
            "  切换公告发布权限（管理员/所有人）",
            "",
            "。群头衔 内容",
            "  更改自己的群头衔",
            "",
            "。群头衔 @某人 内容",
            "  代改他人群头衔",
            "",
            "。群头衔 权限切换",
            "  切换头衔修改权限（管理员/所有人）",
        ]),
        section("🎲 物品管理（长日物品）", [
            "。自由放 物品名 数量 [描述]",
            "  向自由池投放物品",
            "",
            "。固定放 物品名 数量",
            "  向固定池投放物品",
            "",
            "。发放 物品名 角色名",
            "  直接发放物品给某角色",
            "",
            "。固定发放 物品名 角色名",
            "  发放固定物品给某角色",
            "",
            "。物品使用记录",
            "  查看所有物品使用记录",
            "",
            "。清空物品",
            "  清空当前物品池",
            "",
            "。移除物品 物品名",
            "  从池中删除指定物品",
            "",
            "。删除使用记录 编号",
            "  删除指定使用记录",
            "",
            "。查看背包 角色名",
            "  查看指定角色的背包",
        ]),
        section("🛒 礼物商城管理", [
            "【商城设置（.设置 商城）】",
            "  商城模式：抽卡 / 商城（切换时自动转换图鉴↔背包数据）",
            "  商城货币属性：商城模式下购买消耗的属性名（如 金币）",
            "  商城刷新间隔：抽卡模式下个人刷新间隔（小时，默认24）",
            "",
            "【上传格式（用&分隔字段）】",
            "  。上传预设礼物 #1&玫瑰花&一束红玫瑰",
            "  。上传预设礼物 #1&玫瑰花&50&一束红玫瑰  （商城模式加价格）",
            "  批量：#1&礼物1&内容$#2&礼物2&内容",
            "  。上传预设礼物 导出  （导出所有礼物 JSON）",
            "",
            "补货 名字or编号 数量  （仅商城模式，管理员无前缀触发）",
            "",
            "。删除预设礼物 编号",
            "。删除预设礼物 全部 确认  ⚠️",
        ]),
        section("🔗 关系线管理（无前缀，管理员）", [
            "拉线 对方名 关系内容",
            "  例：拉线 张三 两人曾在大学相识",
            "",
            "撤回关系 对方名 要撤回的内容",
            "  精确匹配，仅能撤回自己发送的记录",
            "",
            "关系线统计",
            "  查看所有角色的关系线数量",
        ]),
        section("👤 角色管理", [
            "。清除玩家 角色名",
            "  删除该角色的注册数据",
        ]),
    ];

    ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["管理指令"] = cmd_admin_guide;

// ========================
// 🛒 礼物商城
// ========================

let cmd_view_preset_gifts = seal.ext.newCmdItemInfo();
cmd_view_preset_gifts.name = "礼物商城";
cmd_view_preset_gifts.help = "礼物商城 — 查看本期上架商品（抽卡模式：每人随机；商城模式：全部在售）";

cmd_view_preset_gifts.solve = (ctx, msg) => {
    const sendname = getRoleName(ctx, msg);
    if (!sendname) {
        seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再逛商城。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    const shopMode = ext.storageGet("shop_mode") || "抽卡";
    const allIds = Object.keys(presetGifts);

    if (allIds.length === 0) return seal.replyToSender(ctx, msg, "🛒 商城暂无礼物，管理员尚未上传任何礼物~");

    if (shopMode === "商城") {
        // 商城模式：展示所有在售商品（有库存），最多30件
        const currencyAttr = ext.storageGet("shop_currency_attr") || "金币";
        const inStock = Object.entries(presetGifts).filter(([, g]) => (g.stock || 0) > 0);
        if (inStock.length === 0) return seal.replyToSender(ctx, msg, "🛒 所有商品已售罄，等待管理员补货~");
        const FULL_CAP = 30;
        const display = inStock.slice(0, FULL_CAP);
        const truncated = inStock.length > FULL_CAP;

        let text = `🛒 礼物商城\n${"━".repeat(14)}\n` +
            `💰 货币：${currencyAttr}\n` +
            `📦 共 ${inStock.length} 件在售${truncated ? `（仅展示前 ${FULL_CAP} 件）` : ""}\n`;
        for (const [id, gift] of display) {
            text += `\n${id} 「${gift.name}」\n📝 ${gift.content}\n💰 ${gift.price ?? 0} ${currencyAttr}  📦 库存：${gift.stock} 件\n`;
        }
        text += `\n发送「购买 编号or名字 数量」即可购买`;
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 抽卡模式：每人独立随机1件，自动加入图鉴，刷新只选未拥有的
    const refreshHours = parseInt(ext.storageGet("shop_refresh_hours") || "24");
    const now = Date.now();
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const userKey = `${platform}:${uid}`;

    const sightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
    const owned = new Set(sightings[userKey]?.unlocked_gifts || []);

    let personalDisplay = {};
    try { personalDisplay = JSON.parse(ext.storageGet("shop_personal_display") || "{}"); } catch (e) {}

    const myDisplay = personalDisplay[userKey];
    const needsRefresh = !myDisplay || (now - myDisplay.refreshedAt) > refreshHours * 3600 * 1000;

    if (needsRefresh) {
        const unowned = allIds.filter(id => !owned.has(id));
        if (unowned.length > 0) {
            const picked = unowned[Math.floor(Math.random() * unowned.length)];
            personalDisplay[userKey] = { giftId: picked, refreshedAt: now };
            ext.storageSet("shop_personal_display", JSON.stringify(personalDisplay));
        }
        // 若全部拥有，不刷新 giftId（保留旧展示）
    }

    const currentGiftId = personalDisplay[userKey]?.giftId;
    const total = allIds.length;
    const ownedCount = owned.size;

    if (!currentGiftId || !presetGifts[currentGiftId]) {
        if (ownedCount >= total) {
            return seal.replyToSender(ctx, msg, `🎊 恭喜！你已集齐全部 ${total} 件礼物！\n发送「图鉴」查看你的收藏。`);
        }
        return seal.replyToSender(ctx, msg, "🎰 暂无可抽取的礼物，请稍后再试。");
    }

    const gift = presetGifts[currentGiftId];
    const nextRefreshMs = personalDisplay[userKey].refreshedAt + refreshHours * 3600 * 1000 - now;
    const nextRefreshHrs = Math.max(1, Math.ceil(nextRefreshMs / 3600000));

    if (owned.has(currentGiftId)) {
        return seal.replyToSender(ctx, msg,
            `🎰 本期礼物：${currentGiftId} 「${gift.name}」\n📝 ${gift.content}\n\n✅ 你已收藏此礼物\n📚 图鉴进度：${ownedCount}/${total}\n🔄 ${nextRefreshHrs}h 后刷新新礼物`
        );
    }

    // 新礼物：自动加入图鉴
    if (!sightings[userKey]) sightings[userKey] = { unlocked_gifts: [] };
    sightings[userKey].unlocked_gifts.push(currentGiftId);
    ext.storageSet("gift_sightings", JSON.stringify(sightings));

    const newCount = ownedCount + 1;
    seal.replyToSender(ctx, msg,
        `🎰 本期礼物：${currentGiftId} 「${gift.name}」\n📝 ${gift.content}\n\n✨ 已加入图鉴！📚 进度：${newCount}/${total}\n🔄 ${nextRefreshHrs}h 后刷新\n\n💌 发送「赠送 对方名 ${currentGiftId}」即可赠送`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["礼物商城"] = cmd_view_preset_gifts;

// ========================
// 🛍️ 购买
// ========================

let cmd_purchase = seal.ext.newCmdItemInfo();
cmd_purchase.name = "购买";
cmd_purchase.help = "购买 商品名 — 在礼物商城购买指定商品";

cmd_purchase.solve = (ctx, msg, cmdArgs) => {
    if ((ext.storageGet("shop_mode") || "抽卡") !== "商城") {
        return seal.replyToSender(ctx, msg, "🎰 当前为抽卡模式，发送「礼物商城」查看今日礼物。");
    }

    const sendname = getRoleName(ctx, msg);
    if (!sendname) return seal.replyToSender(ctx, msg, "⚠️ 请先创建角色再购买商品。");

    if (!isUserFeatureEnabled(sendname, "enable_shop_purchase")) {
        return seal.replyToSender(ctx, msg, "🚫 你的商城购买功能已被关闭。");
    }

    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    if (!arg1) return seal.replyToSender(ctx, msg, "用法：购买 编号or名字 [数量]");

    const qty = arg2 ? parseInt(arg2) : 1;
    if (isNaN(qty) || qty < 1) return seal.replyToSender(ctx, msg, "❌ 数量必须是正整数");

    const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    const currencyAttr = ext.storageGet("shop_currency_attr") || "金币";

    // 支持编号(#1)或名字查找
    let giftId = null, gift = null;
    if (arg1.startsWith('#') && presetGifts[arg1]) {
        giftId = arg1; gift = presetGifts[arg1];
    } else {
        const entry = Object.entries(presetGifts).find(([, g]) => g.name === arg1);
        if (entry) { [giftId, gift] = entry; }
    }
    if (!gift) return seal.replyToSender(ctx, msg, `❌ 商城中没有「${arg1}」，发送「礼物商城」查看在售商品。`);

    const stock = gift.stock || 0;
    if (stock <= 0) return seal.replyToSender(ctx, msg, `😔 「${gift.name}」已售罄。`);
    if (stock < qty) return seal.replyToSender(ctx, msg, `😔 「${gift.name}」库存不足，剩余 ${stock} 件。`);

    const price = gift.price ?? 0;
    const totalPrice = price * qty;
    if (totalPrice > 0) {
        let attrs = JSON.parse(ext.storageGet("sys_character_attrs") || "{}");
        const currentVal = attrs[sendname]?.[currencyAttr] || 0;
        if (currentVal < totalPrice) {
            return seal.replyToSender(ctx, msg, `💰 ${currencyAttr}不足！需要 ${totalPrice}${qty > 1 ? `（${price}×${qty}）` : ""}，当前 ${currentVal}。`);
        }
        if (!attrs[sendname]) attrs[sendname] = {};
        attrs[sendname][currencyAttr] = currentVal - totalPrice;
        ext.storageSet("sys_character_attrs", JSON.stringify(attrs));
    }

    const platform = msg.platform;
    const roleInvKey = `${platform}:${sendname}`;
    const invs = JSON.parse(ext.storageGet("global_inventories") || "{}");
    if (!invs[roleInvKey]) invs[roleInvKey] = [];
    const existingIdx = invs[roleInvKey].findIndex(i => i.giftId === giftId && i.source === "礼物商城" && !i.used);
    if (existingIdx !== -1) {
        invs[roleInvKey][existingIdx].count = (invs[roleInvKey][existingIdx].count || 1) + qty;
    } else {
        invs[roleInvKey].push({ name: gift.name, desc: gift.content, used: false, type: "礼物", giftId, count: qty, createTime: Date.now(), source: "礼物商城" });
    }
    ext.storageSet("global_inventories", JSON.stringify(invs));

    presetGifts[giftId].stock = stock - qty;
    ext.storageSet("preset_gifts", JSON.stringify(presetGifts));

    const priceText = totalPrice > 0 ? `（已扣除 ${totalPrice} ${currencyAttr}）` : "";
    seal.replyToSender(ctx, msg,
        `✅ 购买成功${priceText}\n` +
        `🎁 ${giftId} 「${gift.name}」×${qty} 已放入背包\n` +
        `📦 商城剩余库存：${stock - qty} 件`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["购买"] = cmd_purchase;

// ========================
// 📚 我的图鉴
// ========================

let cmd_view_my_gift_collection = seal.ext.newCmdItemInfo();
cmd_view_my_gift_collection.name = "图鉴";
cmd_view_my_gift_collection.help = "图鉴 — 查看礼物收藏与全服热度排名";

cmd_view_my_gift_collection.solve = (ctx, msg) => {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    const userKey = `${platform}:${uid}`;
    const shopMode = ext.storageGet("shop_mode") || "抽卡";

    const presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");
    const total = Object.keys(presetGifts).length;

    if (total === 0) return seal.replyToSender(ctx, msg, "📚 图鉴暂无礼物，管理员尚未上传任何礼物~");

    // 计算全服热度排名（竞争排名，可并列）
    const sortedByHeat = Object.entries(presetGifts)
        .map(([id, g]) => ({ id, name: g.name, content: g.content, count: g.usage_count || 0 }))
        .sort((a, b) => b.count - a.count);
    const heatRanks = {};
    let rank = 1;
    for (let i = 0; i < sortedByHeat.length; i++) {
        if (i > 0 && sortedByHeat[i].count < sortedByHeat[i - 1].count) rank = i + 1;
        heatRanks[sortedByHeat[i].id] = rank;
    }

    if (shopMode === "抽卡") {
        const sightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
        const owned = sightings[userKey]?.unlocked_gifts || [];
        if (owned.length === 0) {
            return seal.replyToSender(ctx, msg, `📚 图鉴（0/${total}）\n发送「礼物商城」开始收集！`);
        }
        const sorted = [...owned].sort((a, b) => (parseInt(a.replace('#', '')) || 0) - (parseInt(b.replace('#', '')) || 0));
        let text = `📚 我的图鉴（${owned.length}/${total}）\n${"━".repeat(14)}\n💌 图鉴内的礼物可无限赠送\n`;
        for (const giftId of sorted) {
            const gift = presetGifts[giftId];
            if (!gift) { text += `\n${giftId} （已下架）\n`; continue; }
            text += `\n${giftId} 「${gift.name}」 🔥热度第${heatRanks[giftId]}名\n📝 ${gift.content}\n`;
        }
        seal.replyToSender(ctx, msg, text.trim());
    } else {
        // 商城模式：显示全部礼物目录（热度排名）
        let text = `📚 礼物图鉴（共 ${total} 件）\n${"━".repeat(14)}\n`;
        for (const { id, name, content, count } of sortedByHeat) {
            text += `\n${id} 「${name}」 🔥第${heatRanks[id]}名（${count}次）\n📝 ${content}\n`;
        }
        seal.replyToSender(ctx, msg, text.trim());
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["图鉴"] = cmd_view_my_gift_collection;
ext.cmdMap["我的图鉴"] = cmd_view_my_gift_collection;

// ========================
// 📦 上传预设礼物
// ========================

let cmd_upload_preset_gift = seal.ext.newCmdItemInfo();
cmd_upload_preset_gift.name = "上传预设礼物";
cmd_upload_preset_gift.help = `上传预设礼物 #编号&名称&内容
上传预设礼物 #编号&名称&价格&内容  （商城模式，价格为整数）
批量：上传预设礼物 #1&玫瑰&内容$#2&巧克力&内容
导出：上传预设礼物 导出`;

cmd_upload_preset_gift.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const shopMode = ext.storageGet("shop_mode") || "抽卡";
    const currencyAttr = ext.storageGet("shop_currency_attr") || "金币";
    const inputArg = cmdArgs.getArgN(1).trim();

    if (!inputArg) {
        seal.replyToSender(ctx, msg,
            shopMode === "商城"
                ? `格式：#编号&名称&价格&内容（货币：${currencyAttr}）\n例：#1&玫瑰花&50&一束红玫瑰`
                : "格式：#编号&名称&内容\n例：#1&玫瑰花&一束红玫瑰"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    let presetGifts = JSON.parse(ext.storageGet("preset_gifts") || "{}");

    if (inputArg === "导出") {
        if (Object.keys(presetGifts).length === 0) {
            seal.replyToSender(ctx, msg, "📭 当前没有预设礼物数据");
            return seal.ext.newCmdExecuteResult(true);
        }
        seal.replyToSender(ctx, msg, `📦 当前预设礼物数据：\n\`\`\`json\n${JSON.stringify(presetGifts, null, 2)}\n\`\`\``);
        return seal.ext.newCmdExecuteResult(true);
    }

    function parseSingle(raw) {
        const parts = raw.trim().split('&');
        const giftId = (parts[0] || "").trim();
        const giftName = (parts[1] || "").trim();
        if (!giftId.startsWith('#')) return { err: `编号必须以#开头：${giftId}` };
        if (!giftName) return { err: `礼物名为空：${raw}` };
        // 自动检测第3段是否为价格（纯数字）
        let price = 0, giftContent = "";
        if (parts.length >= 4 && /^\d+$/.test((parts[2] || "").trim())) {
            price = parseInt(parts[2].trim());
            giftContent = parts.slice(3).join('&').trim();
        } else {
            if (shopMode === "商城" && parts.length < 3) return { err: `格式错误（商城模式建议写价格）：${raw}` };
            giftContent = parts.slice(2).join('&').trim();
        }
        if (!giftContent) return { err: `内容为空：${raw}` };
        return { giftId, giftName, giftContent, price };
    }

    const giftItems = inputArg.includes('$') ? inputArg.split('$') : [inputArg];
    const results = { success: 0, failed: 0, details: [] };

    for (const giftItem of giftItems) {
        const item = giftItem.trim();
        if (!item) continue;
        const parsed = parseSingle(item);
        if (parsed.err) { results.details.push(`❌ ${parsed.err}`); results.failed++; continue; }
        const { giftId, giftName, giftContent, price } = parsed;
        const isUpdate = !!presetGifts[giftId];
        presetGifts[giftId] = isUpdate
            ? { ...presetGifts[giftId], name: giftName, content: giftContent, price, updated_at: new Date().toLocaleString("zh-CN") }
            : { name: giftName, content: giftContent, price, stock: 10, usage_count: 0, created_at: new Date().toLocaleString("zh-CN") };
        results.details.push(isUpdate
            ? `🔄 更新：${giftId}「${giftName}」${shopMode === "商城" ? ` 价格:${price}` : ""}`
            : `✅ 新增：${giftId}「${giftName}」${shopMode === "商城" ? ` 价格:${price} 库存:10` : ""}`);
        results.success++;
    }

    if (results.success > 0) ext.storageSet("preset_gifts", JSON.stringify(presetGifts));

    let rep = "";
    if (giftItems.length > 1) rep += `📦 批量上传完成  ✅${results.success}  ❌${results.failed}  共${Object.keys(presetGifts).length}件\n\n`;
    const showCount = Math.min(results.details.length, 5);
    rep += results.details.slice(0, showCount).join('\n');
    if (results.details.length > showCount) rep += `\n...等${results.details.length}项`;
    if (results.success === 0) rep += `\n💡 格式：#编号&名称${shopMode === "商城" ? "&价格" : ""}&内容`;

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传预设礼物"] = cmd_upload_preset_gift;

// ========================
// 🗑️ 删除预设礼物
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

    if (giftIds.trim() === "全部") {
        const confirmArg = cmdArgs.getArgN(2);
        if (confirmArg !== "确认") {
            seal.replyToSender(ctx, msg,
                "⚠️ 危险操作：这将删除所有预设礼物！\n" +
                "如需继续，请输入：删除预设礼物 全部 确认\n" +
                `当前共有 ${Object.keys(presetGifts).length} 个预设礼物`);
            return seal.ext.newCmdExecuteResult(true);
        }

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

        delete presetGifts[giftId];
        deletedCount++;
        removedFromSightings += userRemoved;
        resultDetails.push(`✅ 已删除: ${giftId} (${giftName}) - 从 ${userRemoved} 位玩家图鉴中移除`);
    }

    if (deletedCount > 0) {
        ext.storageSet("preset_gifts", JSON.stringify(presetGifts));
        ext.storageSet("gift_sightings", JSON.stringify(giftSightings));
    }

    let rep = "";
    if (idsToDelete.length > 1) {
        rep += `🗑️ 批量删除完成\n`;
        rep += `✅ 成功删除: ${deletedCount}个\n`;
        rep += `❌ 未找到: ${notFoundCount}个\n`;
        rep += `👥 从玩家图鉴移除总计: ${removedFromSightings}次\n\n`;
        if (deletedCount > 0) {
            rep += "📋 处理详情：\n";
            resultDetails.forEach(detail => { rep += `  ${detail}\n`; });
        }
    } else {
        rep = deletedCount > 0 ? resultDetails[0] : `❌ 未找到编号为 ${giftIds} 的预设礼物`;
    }

    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除预设礼物"] = cmd_delete_preset_gift;

// ========================
// 🎒 背包
// ========================
const BACKPACK_BOT = "礼物助手", BACKPACK_UIN = "10086";

function sendBackpackNodes(ctx, msg, nodes) {
    const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const CHUNK = 90;
    if (nodes.length <= CHUNK) {
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
        return;
    }
    // 超过90条拆分发送
    for (let i = 0; i < nodes.length; i += CHUNK) {
        const chunk = nodes.slice(i, i + CHUNK);
        setTimeout(() => {
            ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: chunk } }, ctx, msg, "");
        }, Math.floor(i / CHUNK) * 1200);
    }
}

let cmd_backpack = seal.ext.newCmdItemInfo();
cmd_backpack.name = "背包";
cmd_backpack.help = "背包 — 全览\n背包 礼物/普通道具/道具/特殊道具 — 按分类查看\n背包 普通礼物1/普通道具1/特殊道具1 — 查看完整详情";
cmd_backpack.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");

    const platform = msg.platform;
    const roleKey = `${platform}:${roleName}`;
    const inv = (store.get("global_inventories")[roleKey] || []).filter(i => !i.used);

    const arg1 = cmdArgs.getArgN(1);
    const trunc = (s, n = 20) => s && s.length > n ? s.slice(0, n) + "…" : (s || "");
    const mkNode = (content) => ({ type: "node", data: { name: BACKPACK_BOT, uin: BACKPACK_UIN, content } });

    // 查看单件详情
    if (arg1) {
        const detailM = arg1.match(/^(普通礼物|普通道具|特殊道具)(\d+)$/);
        if (detailM) {
            const [_, cat, numStr] = detailM;
            const items = getItemsByCategory(inv, cat);
            const item = items[parseInt(numStr) - 1];
            if (!item) return seal.replyToSender(ctx, msg, `❌ ${cat}${numStr} 不存在。`);
            const emoji = { 特殊道具: "⚙️", 普通礼物: "🎁", 普通道具: "📦" }[cat];
            const fromLine = item.from ? `\n📮 来自：${item.from}` : "";
            const countLine = (item.count || 1) > 1 ? `\n🔢 数量：${item.count}` : "";
            seal.replyToSender(ctx, msg, `${emoji} 【${cat}${numStr}】${item.name}${fromLine}${countLine}\n${"─".repeat(12)}\n📝 ${item.desc}`);
            return seal.ext.newCmdExecuteResult(true);
        }

        // 按分类筛选
        const filterMap = {
            "礼物":    [["普通礼物", "🎁", "普通礼物"]],
            "普通道具": [["普通道具", "📦", "普通道具"]],
            "特殊道具": [["特殊道具", "⚙️", "特殊道具"]],
            "道具":    [["普通道具", "📦", "普通道具"], ["特殊道具", "⚙️", "特殊道具"]],
        };
        const sections = filterMap[arg1];
        if (!sections) return seal.replyToSender(ctx, msg, "格式：背包 礼物 / 普通道具 / 道具 / 特殊道具\n或：背包 普通礼物1 / 普通道具1 / 特殊道具1");

        const nodes = [];
        let total = 0;
        for (const [cat, emoji, prefix] of sections) {
            const items = getItemsByCategory(inv, cat);
            total += items.length;
            if (!items.length) continue;
            const lines = items.map((it, i) => `${emoji} ${prefix}${i + 1}. ${it.name}${(it.count || 1) > 1 ? ` x${it.count}` : ""}${it.from ? `  来自：${it.from}` : ""}  ${trunc(it.desc)}`);
            nodes.push(mkNode(`${emoji} ${cat}\n${"─".repeat(12)}\n${lines.join("\n")}`));
        }
        if (!nodes.length) {
            seal.replyToSender(ctx, msg, `🎒 【${roleName}】的${arg1}分区空空如也。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        nodes.unshift(mkNode(`🎒 【${roleName}】的背包 · ${arg1}\n${"━".repeat(14)}\n共 ${total} 件`));
        sendBackpackNodes(ctx, msg, nodes);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 全览
    const shopModeForBackpack = ext.storageGet("shop_mode") || "抽卡";
    let gachaProgressLine = "";
    if (shopModeForBackpack === "抽卡") {
        const uid_bp = msg.sender.userId.replace(/^[a-z]+:/i, "");
        const bpUserKey = `${platform}:${uid_bp}`;
        const bpSightings = JSON.parse(ext.storageGet("gift_sightings") || "{}");
        const bpPresets = JSON.parse(ext.storageGet("preset_gifts") || "{}");
        const ownedCnt = (bpSightings[bpUserKey]?.unlocked_gifts || []).length;
        const totalCnt = Object.keys(bpPresets).length;
        gachaProgressLine = `\n📚 图鉴进度：${ownedCnt}/${totalCnt}（发送「图鉴」查看收藏）`;
    }

    if (inv.length === 0 && !gachaProgressLine) {
        seal.replyToSender(ctx, msg, `🎒 【${roleName}】的背包空空如也。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const normalGifts = getItemsByCategory(inv, "普通礼物");
    const normalTools = getItemsByCategory(inv, "普通道具");
    const specTools   = getItemsByCategory(inv, "特殊道具");

    const nodes = [mkNode(
        `🎒 【${roleName}】的背包\n${"━".repeat(14)}\n` +
        (shopModeForBackpack === "商城" ? `🎁 普通礼物  ${normalGifts.length} 件\n` : "") +
        `📦 普通道具  ${normalTools.length} 件\n` +
        `⚙️ 特殊道具  ${specTools.length} 件` +
        gachaProgressLine + "\n\n" +
        `发送「背包 礼物」只看礼物\n` +
        `发送「背包 普通礼物1」查看完整详情\n` +
        `发送「道具赠送 对方名 物品名」转交物品`
    )];

    const addSection = (cat, emoji, items, prefix) => {
        if (!items.length) return;
        const lines = items.map((it, i) => `${emoji} ${prefix}${i + 1}. ${it.name}${(it.count || 1) > 1 ? ` x${it.count}` : ""}  ${trunc(it.desc)}`);
        nodes.push(mkNode(`${emoji} ${cat}\n${"─".repeat(12)}\n${lines.join("\n")}`));
    };

    addSection("普通礼物", "🎁", normalGifts, "普通礼物");
    addSection("普通道具", "📦", normalTools,  "普通道具");
    addSection("特殊道具", "⚙️", specTools,   "特殊道具");

    sendBackpackNodes(ctx, msg, nodes);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["背包"] = cmd_backpack;

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

let cmd_sync_now = seal.ext.newCmdItemInfo();
cmd_sync_now.name = "同步名片"; 
cmd_sync_now.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return;

    const platform = msg.platform, storage = getRoleStorage();
    const pData = storage[platform] || {};
    // 统一读取特殊群组，过滤无效值
    const specials = ["adminAnnounceGroupId", "water_group_id", "song_group_id"]
        .map(k => JSON.parse(ext.storageGet(k) || "null"))
        .filter(id => id && id !== "未设置");

    const names = Object.keys(pData);
    if (!names.length) return seal.replyToSender(ctx, msg, "📭 数据库为空");

    let count = 0;
    names.forEach((name, index) => {
        const [uid, pGid] = pData[name];
        // 合并私信群与公共群，去重
        const targets = [...new Set([pGid, ...specials])].filter(id => id && id !== "0");

        targets.forEach(gid => {
            const cleanGid = parseInt(gid.toString().replace(/[^\d]/g, ""));
            const cleanUid = parseInt(uid.toString().replace(/[^\d]/g, ""));

            if (!isNaN(cleanGid) && !isNaN(cleanUid)) {
                // 增加一个小延迟，防止 WS 堵塞导致失败
                setTimeout(() => {
                    ws({
                        "action": "set_group_card",
                        "params": { "group_id": cleanGid, "user_id": cleanUid, "card": name }
                    }, ctx, msg, "");
                }, (count++) * 100); // 每个请求间隔 100ms
            }
        });
    });

    seal.replyToSender(ctx, msg, `🔄 正在同步 ${names.length} 个角色的名片...\n涉及群组：${specials.length + 1} 个\n预计操作次数：${count}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["同步名片"] = cmd_sync_now;

// ========================
// 📅 修改时间线 指令
// ========================
let cmd_update_schedule = seal.ext.newCmdItemInfo();
cmd_update_schedule.name = "修改时间线";
cmd_update_schedule.help = "。修改时间线 D1 1400-1500 (在约会群内使用，修改当前约会的时间)";

cmd_update_schedule.solve = async (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const gid = msg.groupId.replace(`${platform}-Group:`, "");
    const newDay = cmdArgs.getArgN(1); // 例如 D1
    const newRawTime = cmdArgs.getArgN(2); // 例如 1400-1500

    if (!newDay || !newRawTime) return seal.replyToSender(ctx, msg, "⚠️ 格式错误，请使用：.修改时间线 D1 1400-1500");

    // 1. 获取当前群的参与者信息
    let groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
    const info = groupExpireInfo[gid];
    if (!info) return seal.replyToSender(ctx, msg, "⚠️ 只有在活跃的私约/电话群内才能修改时间。");

    // 2. 校验新时间格式与合法性
    const allowedRanges = JSON.parse(ext.storageGet("allowed_appointment_times") || "[]");
    const subtype = info.subtype || "私密";
    const minDuration = subtype === "电话" ? 29 : 59;
    const timeRes = parseAndValidateTime(newRawTime, allowedRanges, minDuration, subtype);
    if (!timeRes.valid) return seal.replyToSender(ctx, msg, timeRes.errorMsg);
    const newTime = timeRes.time;

    // 3. 冲突检查：检查所有人名下在新时段是否有别的安排
    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
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

    // 4. 执行修改
    // A. 修改群基础信息
    info.day = newDay;
    info.time = newTime;
    groupExpireInfo[gid] = info;
    ext.storageSet("group_expire_info", JSON.stringify(groupExpireInfo));

    // B. 同步修改所有人的日程表
    for (let name of participants) {
        const details = getRoleDetails(platform, name);
        const key = `${platform}:${details.uid.replace(/^[a-z]+:/i, "")}`;
        if (b_confirmedSchedule[key]) {
            b_confirmedSchedule[key].forEach(ev => {
                if (ev.group === gid) {
                    ev.day = newDay;
                    ev.time = newTime;
                }
            });
        }
    }
    ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

    // 5. 修改群名片并通知
    const nameTag = participants.length > 2 ? "多人" : participants.join("/");
    const newGroupName = `${subtype} ${newDay} ${newTime} ${info.place} ${nameTag}`;
    setGroupName(ctx, msg, gid, newGroupName);

    seal.replyToSender(ctx, msg, `✅ 时间线修改成功！\n📅 新时间：${newDay} ${newTime}\n新的日程已同步至所有参与者的【时间线】。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["修改时间线"] = cmd_update_schedule;

// ========================
// 🗑️ 废除时间线 指令
// ========================
let cmd_abolish_schedule = seal.ext.newCmdItemInfo();
cmd_abolish_schedule.name = "废除时间线";
cmd_abolish_schedule.help = "。废除时间线 (强制删除当前约会记录并释放群号，无需复盘)";

cmd_abolish_schedule.solve = (ctx, msg) => {
    const platform = msg.platform;
    const gid = msg.groupId.replace(`${platform}-Group:`, "");
    let groupPool = JSON.parse(ext.storageGet("group") || "[]");

    // 1. 检查是否为占用状态
    const fullId = `${gid}_占用`;
    const isOccupied = groupPool.includes(fullId);
    
    if (!isOccupied) return seal.replyToSender(ctx, msg, "⚠️ 当前群号未处于占用状态，无需废除。");

    // 2. 彻底删除日程记录 (b_confirmedSchedule)
    let b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
    for (let uidKey in b_confirmedSchedule) {
        // 过滤掉当前群的所有记录
        b_confirmedSchedule[uidKey] = b_confirmedSchedule[uidKey].filter(ev => ev.group !== gid);
    }
    ext.storageSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

    // 3. 清理过期信息 (group_expire_info)
    let groupExpireInfo = JSON.parse(ext.storageGet("group_expire_info") || "{}");
    if (groupExpireInfo[gid]) {
        delete groupExpireInfo[gid];
        ext.storageSet("group_expire_info", JSON.stringify(groupExpireInfo));
    }

    // 4. 释放群号回池子
    const idx = groupPool.indexOf(fullId);
    if (idx !== -1) {
        groupPool.splice(idx, 1);
        groupPool.push(gid);
        ext.storageSet("group", JSON.stringify(groupPool));
    }

    // 5. 修改群名片并遣散通知
    setGroupName(ctx, msg, gid, `备用`);
    cleanupGroupTimer(gid); // 清理该群计时器

    const notice = `🚫 【约会废除通知】\n\n本场时间线已被强制废除，相关日程已从系统删除。\n请各位参与者尽快退群，期待下次相遇！`;
    seal.replyToSender(ctx, msg, notice);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["废除时间线"] = cmd_abolish_schedule;