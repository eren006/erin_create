// ==UserScript==
// @name         长日将尽系统
// @author       长日将尽
// @version      1.4.0
// @description  无
// @timestamp    1778742000
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F.js
// ==/UserScript==

let ext = seal.ext.find("changri")
if (!ext) {
    ext = seal.ext.new("changri", "长日将尽", "1.4.0");
    // 注册扩展
    seal.ext.register(ext);
    ext.autoActive = true;
}
ext.autoActive = true;

// ── 存储缓存层 ──────────────────────────────────────────────────────────────
// 缓存 storageGet 的原始字符串，写时同步落库（写穿）。
// 约束：changri 存储的所有读写（含卫星插件，经 __changriApi.kvGetRaw/kvSetRaw）
// 都必须经过这两个函数；若在海豹 WebUI 直接改了插件存储，需重载本插件清缓存。
const _kvCache = Object.create(null);
function cachedGet(key) {
    if (!(key in _kvCache)) _kvCache[key] = ext.storageGet(key);
    return _kvCache[key];
}
function cachedSet(key, val) {
    const str = typeof val === "string" ? val : String(val);
    ext.storageSet(key, str);
    _kvCache[key] = str;
}

// 读取整数型设置，兼容 JSON 编码的 '"48"' 与裸字符串 '48' 两种格式
function getStorageInt(key, defaultVal) {
    const raw = cachedGet(key);
    if (!raw) return defaultVal;
    try { const v = parseInt(JSON.parse(raw)); return isNaN(v) ? defaultVal : v; }
    catch (e) { const v = parseInt(raw); return isNaN(v) ? defaultVal : v; }
}

seal.ext.registerStringConfig(ext, "ws地址", "ws://localhost:3001");
    seal.ext.registerStringConfig(ext, "ws Access token", '', "输入与上方端口对应的token，没有则留空");
    seal.ext.registerStringConfig(ext, "群管插件使用需要满足的条件", '1', "使用豹语表达式，例如：$t群号_RAW=='2001'，1为所有群可用");
    seal.ext.registerBoolConfig(ext, "开启现实时段校验", false, "是否限制玩家只能发起与当前现实时间对应的剧情时段邀约");
    seal.ext.registerBoolConfig(ext, "启用RP存档传输", false, "开启后，监听到的RP正文、短信、礼物将在结戏时发送到存档服务器");
    seal.ext.registerStringConfig(ext, "RP存档服务器地址", "http://localhost:6666", "Flask存档服务器地址，末尾不带/");
    seal.ext.registerStringConfig(ext, "RP存档Token", "", "存档服务器API验证Token，与服务器端RP_API_TOKEN环境变量一致，留空则不验证");


// ========================
// 🌐 WebSocket 通信模块
// ========================
// 批量同步专用函数（使用单个连接）
function wsBatchSync(requestQueue, ctx, msg) {
    const wsUrl = seal.ext.getStringConfig(ext, "ws地址");
    const token = seal.ext.getStringConfig(ext, "ws Access token");
    let connectionUrl = wsUrl;

    if (token) {
        const separator = connectionUrl.includes('?') ? '&' : '?';
        connectionUrl += `${separator}access_token=${encodeURIComponent(token)}`;
    }

    const ws = new WebSocket(connectionUrl);
    let isClosed = false;
    let currentIndex = 0;
    let successCount = 0;
    let failureCount = 0;

    const closeSafe = (reason) => {
        if (!isClosed) {
            isClosed = true;
            clearTimeout(timeoutId);
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close(1000, reason);
            }
        }
    };

    const timeoutId = setTimeout(() => {
        if (!isClosed) {
            console.log(`[WS] 批量同步超时`);
            closeSafe("TIMEOUT");
        }
    }, 30000); // 30秒超时

    const sendNext = () => {
        if (currentIndex >= requestQueue.length) {
            closeSafe("BATCH_COMPLETE");
            return;
        }

        const postData = requestQueue[currentIndex];
        const currentEcho = postData.action + "_" + Date.now() + "_" + currentIndex;
        postData.echo = currentEcho;

        if (postData.params) {
            if (postData.params.message_id) postData.params.message_id = parseInt(postData.params.message_id);
            if (postData.params.group_id) postData.params.group_id = parseInt(postData.params.group_id);
        }

        try {
            ws.send(JSON.stringify(postData));
        } catch (e) {
            console.error('发送失败:', e);
            currentIndex++;
            failureCount++;
            sendNext();
        }
    };

    ws.onopen = function() {
        sendNext();
    };

    ws.onmessage = function(event) {
        try {
            const response = JSON.parse(event.data);
            if (response.post_type === "meta_event") return;
            if (!response.echo) return;

            if (response.status === 'ok' || response.retcode === 0) {
                successCount++;
            } else {
                console.error(`[WS] 请求失败: ${response.echo}`);
                failureCount++;
            }

            currentIndex++;
            // 延迟50ms后发送下一个请求
            setTimeout(sendNext, 50);
        } catch (e) {
            console.error('收包解析异常:', e);
        }
    };

    ws.onerror = function(e) {
        if (isClosed || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED) {
            return;
        }
        console.error('[WS] 连接异常，请检查OneBot连接状态');
        closeSafe("ERROR");
    };

    ws.onclose = function(event) {
        isClosed = true;
        const resultMsg = `✅ 同步完成！\n成功: ${successCount}\n失败: ${failureCount}\n总计: ${requestQueue.length}`;
        seal.replyToSender(ctx, msg, resultMsg);
    };
}

// ── WS 请求器：每请求短连接 + echo 匹配 + 超时清理 ──
// 注意：不做常驻连接。配置的 ws地址 是 OneBot 正向 WS 的 universal 端点（根路径），
// 常驻连接会持续收到全部 QQ 事件推送涌入海豹 JS 运行时，且插件重载后旧连接
// 回调悬空，实测会导致海豹崩溃。社区插件（恋综2.2.2 等）均为短连接模式。
// 收益保留在结构层：全系统唯一实现，卫星插件经 api.ws 委托；
// echo 带自增序号，避免同毫秒两个同名 action 串包。
const WSM = {
    seq: 0,

    buildUrl() {
        let url = seal.ext.getStringConfig(ext, "ws地址") || "";
        const token = seal.ext.getStringConfig(ext, "ws Access token");
        if (url && token) {
            url += (url.includes("?") ? "&" : "?") + "access_token=" + encodeURIComponent(token);
        }
        return url;
    },

    // 发起一次请求；onResponse 收到完整 response 对象；超时/失败走 onTimeout
    request(postData, onResponse, onTimeout, timeoutMs = 3000) {
        const echo = postData.echo || (postData.action + "_" + Date.now() + "_" + (this.seq++));
        postData.echo = echo;
        let payload;
        try { payload = JSON.stringify(postData); } catch (e) {
            console.error("发送失败, JSON序列化错误:", e);
            return null;
        }
        const url = this.buildUrl();
        if (!url) {
            console.error("[WS] 未配置 ws地址");
            if (onTimeout) onTimeout();
            return null;
        }
        let conn;
        try { conn = new WebSocket(url); } catch (e) {
            console.error("[WS] 连接创建失败，请检查 ws地址 配置:", e);
            if (onTimeout) onTimeout();
            return null;
        }
        let done = false;
        const finish = (reason) => {
            if (done) return;
            done = true;
            clearTimeout(timer);
            if (conn.readyState === WebSocket.OPEN || conn.readyState === WebSocket.CONNECTING) {
                try { conn.close(1000, reason); } catch (e) {}
            }
        };
        const timer = setTimeout(() => {
            if (!done) {
                console.log(`[WS] 请求超时: ${postData.action}`);
                finish("TIMEOUT");
                if (onTimeout) onTimeout();
            }
        }, timeoutMs);
        conn.onopen = () => {
            try { conn.send(payload); } catch (e) {
                console.error("[WS] 发送失败:", e);
                finish("SEND_ERROR");
                if (onTimeout) onTimeout();
            }
        };
        conn.onmessage = (event) => {
            let response;
            try { response = JSON.parse(event.data); } catch (e) { return; }
            if (response.post_type === "meta_event") return;
            if (response.echo !== echo) return;
            finish("DONE");
            try { onResponse(response); } catch (e) { console.error("[WS] 回调异常:", e); }
        };
        conn.onerror = () => {
            if (done || conn.readyState === WebSocket.CLOSING || conn.readyState === WebSocket.CLOSED) return;
            console.error("[WS] 运行异常，请检查地址、Token或OneBot连接状态");
        };
        conn.onclose = (event) => {
            if (event && event.code !== 1000) {
                console.log(`[WS] 连接已关闭 (代码: ${event.code}, 原因: ${event.reason || ""})`);
            }
            // 未收到响应即被关闭（如 OneBot 未启动、连接被拒）：立即按失败处理
            if (!done) {
                done = true;
                clearTimeout(timer);
                if (onTimeout) onTimeout();
            }
        };
        return echo;
    },

    // 单向发送，不关心响应
    push(postData) {
        this.request(postData, () => {}, null);
    },
};

// 兼容包装：签名与历史版本一致，全部调用点无需改动
function ws(postData, ctx, msg, successreply, errorreply) {
    if (postData.params) {
        if (postData.params.message_id) postData.params.message_id = parseInt(postData.params.message_id);
        if (postData.params.group_id) postData.params.group_id = parseInt(postData.params.group_id);
    }
    WSM.request(postData,
        (response) => {
            if (response.status === 'ok' || response.retcode === 0) {
                if (postData.action === "get_group_member_list") {
                    handleMemberListResponse(ctx, msg, response.data, postData.echo);
                } else if (postData.action === "get_msg") {
                    handleForwardAction(ctx, msg, response.data);
                } else {
                    if (successreply) seal.replyToSender(ctx, msg, successreply);
                }
            } else {
                console.error(`[WS] 服务端返回错误: ${JSON.stringify(response)}`);
                if (errorreply) seal.replyToSender(ctx, msg, errorreply);
            }
        },
        () => { if (errorreply) seal.replyToSender(ctx, msg, errorreply); }
    );
    return seal.ext.newCmdExecuteResult(true);
}

// 暴露给其他插件使用
ext._ws = ws;

function handleForwardAction(ctx, msg, data) {
    const taskType = cachedGet("temp_task_type") || "forward";
    // 点歌直接读 song_group_id，避免与复盘共用 temp_target_gid 导致群号错乱
    const rawGid = taskType === "song"
        ? (cachedGet("song_group_id") || "")
        : (cachedGet("temp_target_gid") || "");
    const gid = parseInt(rawGid.replace(/[^\d]/g, ""), 10);

    if (isNaN(gid) || !data || !data.message) {
        if (!data || !data.message) seal.replyToSender(ctx, msg, "❌ 点歌/复盘失败：消息内容为空，请确认回复的是音乐卡片。");
        return;
    }

    const originalContent = typeof data.message === 'string' ? data.message : JSON.stringify(data.message);

    if (taskType === "song") {
        const dgr = cachedGet("temp_song_dgr") || "未知";
        const ly = cachedGet("temp_song_ly") || "无";

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
            ws({ action: "send_group_msg", params: { group_id: gid, message: `🎵 【点歌台】\n点歌人：${dgr}\n留言：${ly}` } }, ctx, msg, "");
            setTimeout(() => {
                ws({ action: "send_group_msg", params: { group_id: gid, message: `[CQ:music,type=${musicType},id=${songId}]` } }, ctx, msg, "");
                seal.replyToSender(ctx, msg, "✅ 点歌已同步至戏群。");
            }, 800);
        } else {
            seal.replyToSender(ctx, msg, "❌ 识别失败，请引用音乐分享卡片。");
        }
    } else {
        // 复盘逻辑：保持双消息平铺
        const sourceName = cachedGet("temp_source_group_name") || "未知群聊";
        WSM.push({
            "action": "send_group_msg",
            "params": { "group_id": gid, "message": `📢 复盘来源：【${sourceName}】` }
        });
        setTimeout(() => {
            WSM.push({
                "action": "send_group_msg",
                "params": { "group_id": gid, "message": data.message }
            });
        }, 500);
    }
}
// ========================
// 📦 RP存档模块
// ========================

function isArchiveEnabled() {
    return seal.ext.getBoolConfig(ext, "启用RP存档传输");
}

function applyMsgTemplate(tplName, vars) {
    const raw = cachedGet("custom_message_templates");
    if (!raw) return null;
    try {
        const tpl = JSON.parse(raw)[tplName];
        if (!tpl || !tpl.trim()) return null;
        return tpl.replace(/\{([^}]+)\}/g, (_, k) => (vars[k] !== undefined ? vars[k] : `{${k}}`));
    } catch (e) { return null; }
}

async function postToArchive(endpoint, data) {
    const base = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) return;
    // 网络抖动重试：session_end 丢失会导致该场次统计永远停留在 entry 累加值
    for (let attempt = 1; attempt <= 3; attempt++) {
        try {
            const resp = await fetch(base + endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify(data)
            });
            if (resp.ok) return;
            // 4xx 是请求本身的问题，重试无意义
            if (resp.status < 500) {
                console.error(`[RP存档] ${endpoint} 返回 ${resp.status}，不重试`);
                return;
            }
            console.error(`[RP存档] ${endpoint} 返回 ${resp.status}（第${attempt}次）`);
        } catch (e) {
            console.error(`[RP存档] 发送失败 ${endpoint}（第${attempt}次）:`, e.message || String(e));
        }
        if (attempt < 3) await new Promise(r => setTimeout(r, attempt * 3000));
    }
}

function getActiveSessionId(platform, senderName) {
    const uid = getUidByRoleName(platform, senderName);
    if (!uid) return "";
    const key = `${platform}:${uid}`;
    const bSched = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const active = (bSched[key] || []).find(e => e.status === "active" && e.group);
    if (!active) return "";
    const startTs = (getSessionStats()[active.group] || {})._startTime;
    return startTs ? `${active.group}_${startTs}` : "";
}

function buildSessionArchive(gid, platform, forced) {
    const timers = getGroupTimers();
    const timer  = timers[gid] || {};
    const ss     = getSessionStats()[gid] || {};

    const startTs = ss._startTime || Date.now();
    const endTs   = Date.now();
    const sessionId = `${gid}_${startTs}`;

    const participants = timer.participants || [];

    // 每人统计（uid → roleName 映射后输出）
    const stats = {};
    participants.forEach(roleName => {
        const uid = getUidByRoleName(platform, roleName);
        if (uid && ss[uid]) {
            stats[roleName] = { replies: ss[uid].replies || 0, words: ss[uid].words || 0 };
        }
    });

    const expireInfo = JSON.parse(cachedGet("group_expire_info") || "{}")[gid] || {};
    const gameDay    = expireInfo.day  || timer.day || cachedGet("global_days") || "";

    // 心动信/短信/礼物均已在事件发生时实时 POST /api/event，此处不再批量附带
    // （心动信 pool 投完即清空，批量读取必然为空；短信/礼物实时上传已含 session_id）

    // 顺带附上 QQ→角色映射，服务器自动更新玩家数据库，无需手动同步
    const _npcListBuild = JSON.parse(cachedGet("a_npc_list") || "[]");
    const playersList = participants.map(roleName => {
        const uid = getUidByRoleName(platform, roleName);
        return uid ? { qq: uid, role_name: roleName, is_npc: _npcListBuild.includes(roleName) } : null;
    }).filter(Boolean);

    return {
        session_id:   sessionId,
        group_id:     gid,
        platform:     platform,
        game_day:     gameDay,
        game_time:    expireInfo.time    || timer.time    || "",
        place:        expireInfo.place   || timer.place   || "",
        subtype:      timer.subtype      || expireInfo.subtype || "",
        participants: participants,
        start_ts:     startTs,
        end_ts:       endTs,
        forced:       forced ? 1 : 0,
        stats:        stats,
        players:      playersList,
    };
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
    const auditOwner = cachedGet("temp_audit_owner");
    if (auditOwner) {
        performAuditLogic(ctx, msg, auditOwner, members);
        cachedSet("temp_audit_owner", "");
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
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
    
    const playerMap = {}; 
    const npcUIDs = {};   
    const memberUIDs = members.map(m => (m.user_id || m.qq).toString());

    // 建立映射（新结构：uid为key，roleName在value[0]）
    Object.entries(a_private_group[platform] || {}).forEach(([uid, data]) => {
        const name = data[0];
        if (npcList.includes(name)) npcUIDs[name] = uid;
        else playerMap[uid] = name;
    });

    // 通过 ownerName 反查 uid
    const ownerEntry = Object.entries(a_private_group[platform] || {}).find(([_, v]) => v[0] === ownerName);
    if (!ownerEntry) return;
    const ownerUID = ownerEntry[0];
    const gid = ownerEntry[1][1];

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
    const a_adminList = JSON.parse(cachedGet("a_adminList") || "{}");
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


function recordMeetingAndAnnounce(subtype, platform, ctx, endPoint) {
    const subtypeKeyMap = {
        "电话": "call",
        "私密": "private",
        "寄信": "chaosletter",
        "发送信件": "directletter",
        "心动信": "lovemail",
        "礼物": "gift",
        "心愿": "wish",
        "官约": "official",
        "拉线": "relation"
    };
    const keyType = subtypeKeyMap[subtype] || "unknown";
    const storageKey = `a_meetingCount_${keyType}`;

    let count = parseInt(cachedGet(storageKey) || "0");
    count++;
    cachedSet(storageKey, count.toString());

    const groupId = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");

    if (groupId) {
        const msgDivineLog = seal.newMessage();
        msgDivineLog.messageType = "group";
        msgDivineLog.groupId = `${platform}-Group:${groupId}`;
        const ctxDivineLog = seal.createTempCtx(endPoint, msgDivineLog);

        const getStageText = (subtype, count) => {
            // --- 核心修改部分：从配置项获取频率 ---
            // 获取用户在插件设置里填写的数字，默认为 5
            const frequency = getStorageInt("announceFrequency", 5);
            
            // 检查是否应该触发公告：使用动态频率
            let shouldAnnounce = (count % frequency === 0);
            
            if (!shouldAnnounce) return null;

            const getDirectRecord = (type, count, emoji) => {
                return `${emoji} 【第${count}次${type}记录】`;
            };

            // ... 以下逻辑保持不变 ...
            if (subtype === "电话") return getDirectRecord("电话", count, "☎️");
            if (subtype === "私密") return getDirectRecord("私密约会", count, "💫");
            if (subtype === "寄信") return getDirectRecord("寄信", count, "📮");

            if (subtype === "心动信") return getDirectRecord("心动信派送", count, "💌");
            if (subtype === "礼物") return getDirectRecord("礼物赠送", count, "🎁");
            if (subtype === "心愿") return getDirectRecord("心愿", count, "🌠");
            if (subtype === "官约") return getDirectRecord("官方约会", count, "🏢");
            if (subtype === "拉线") return getDirectRecord("关系线记录", count, "🔗");

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
  const a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
  const locked = a_lockedSlots[`${platform}:${userId}`]?.[day] || [];
  for (let slot of locked) {
    if (timeOverlap(slot, time)) {
      results.push(`在 ${day} ${slot} 被管理员锁定`);
      break;
    }
  }

  // 2. 检查已确认日程冲突
  const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
  const confirmedList = b_confirmedSchedule[`${platform}:${userId}`] || [];
  for (let sch of confirmedList) {
    if (sch.day === day && timeOverlap(sch.time, time)) {
      results.push(`在 ${day} ${time} 已有确认的${sch.subtype || '活动'}安排`);
      break;
    }
  }

  // 3. 检查已接受但未成团的多人邀请（排除当前邀约）
  const b_MultiGroupRequest = JSON.parse(cachedGet("b_MultiGroupRequest") || "{}");
  for (let [ref, group] of Object.entries(b_MultiGroupRequest)) {
    // 排除当前正在处理的多人邀约
    if (excludeMultiGroupRef && ref === excludeMultiGroupRef) continue;
    
    const status = group.targetList?.[roleName];
    if (status === "accepted" && group.day === day && timeOverlap(group.time, time)) {
      results.push(`在 ${day} ${time} 已接受其他多人小群邀请`);
      break;
    }
  }

  return results;
}

  function getAdminPassword() {
    let rawPass = cachedGet("adminPassword");
    let parsedPass;
  
    try {
      parsedPass = JSON.parse(rawPass);
    } catch (e) {
      parsedPass = rawPass;
    }
  
    return (parsedPass || "detroit").trim(); // 兜底并清理空格
  }

function isUserFeatureEnabled(uid, key, defaultValue = true) {
  const blockMap = JSON.parse(cachedGet("feature_user_blocklist") || "{}");
  const personConfig = blockMap[uid];
  if (personConfig && personConfig[key] !== undefined) {
    return personConfig[key];
  }
  return defaultValue;
}
 // 辅助函数：统一获取并清洗数据格式
function getRoleStorage() {
    let data = JSON.parse(cachedGet("a_private_group") || "{}");
    // 直接返回数据，不再进行 Array 检查和 needsUpdate 判断
    return data;
}

// ========================
// 👤 角色与权限管理
// ========================

// ── 季度工具函数 ──────────────────────────────────────────────────────────────
function getSeasonShowName() { return cachedGet("season_show_name") || ""; }
function getSeasonMode()     { return cachedGet("season_mode") || "review"; }
function hasActiveSeason()   { return !!getSeasonShowName(); }

// a_private_group 是否已无任何角色（所有 platform 下都无 uid entry）
function isRoleStorageEmpty() {
    const storage = getRoleStorage();
    for (const platform of Object.keys(storage)) {
        if (Object.keys(storage[platform] || {}).length > 0) return false;
    }
    return true;
}
// ─────────────────────────────────────────────────────────────────────────────

// 1. 创建新角色
let cmd_bind_role = {};
cmd_bind_role.solve =(ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    if (!name || name === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    if (isArchiveEnabled() && !hasActiveSeason()) {
        seal.replyToSender(ctx, msg, "⚠️ 当前没有活跃的季度，请联系主办发起「创建新季度」后再创建角色。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let platform = msg.platform;
    let gid = msg.groupId ? msg.groupId.replace(`${platform}-Group:`, "") : "0";
    let uid = msg.sender.userId.replace(`${platform}:`, "");
    let storage = getRoleStorage();

    if (!storage[platform]) storage[platform] = {};

    // 检查名称是否被他人占用（新结构：uid为key，roleName在value[0]）
    const existingUidForName = Object.entries(storage[platform]).find(([k, v]) => v[0] === name && k !== uid)?.[0];
    if (existingUidForName) {
        seal.replyToSender(ctx, msg, `❌ 名称「${name}」已被其他用户占用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 已有角色则拒绝，提示用修改名字（新结构：直接按uid查找）
    if (storage[platform][uid]) {
        const existingName = storage[platform][uid][0];
        seal.replyToSender(ctx, msg, `⚠️ 你已有角色「${existingName}」。若想改名，请发送「修改名字 新名字」。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    storage[platform][uid] = [name, gid];
    cachedSet("a_private_group", JSON.stringify(storage));
    initCharProfile(platform, name);

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
        `\n发送「玩家名单」查看所有角色。`
    );
    return seal.ext.newCmdExecuteResult(true);
};

// 修改名字
function doRenameRole(ctx, msg, newName) {
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const storage = getRoleStorage();
    if (!storage[platform]) return seal.replyToSender(ctx, msg, "❌ 请先创建角色");

    const entry = storage[platform][uid];
    if (!entry) return seal.replyToSender(ctx, msg, "❌ 请先创建角色");
    const oldName = entry[0];
    if (oldName === newName) return seal.replyToSender(ctx, msg, "❌ 新名字与当前名字相同");

    const takenByOther = Object.entries(storage[platform]).find(([k, v]) => v[0] === newName && k !== uid);
    if (takenByOther) return seal.replyToSender(ctx, msg, `❌ 名字「${newName}」已被他人使用`);

    storage[platform][uid][0] = newName;
    cachedSet("a_private_group", JSON.stringify(storage));

    const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
    const npcIdx = npcList.indexOf(oldName);
    if (npcIdx !== -1) { npcList[npcIdx] = newName; cachedSet("a_npc_list", JSON.stringify(npcList)); }

    const relData = JSON.parse(cachedGet("relationship_lines") || "{}");
    if (relData[platform]) {
        for (const rels of Object.values(relData[platform])) {
            for (const rel of Object.values(rels)) {
                if (rel.initiator === oldName) rel.initiator = newName;
                if (Array.isArray(rel.details)) rel.details.forEach(d => { if (d.from === oldName) d.from = newName; });
            }
        }
        cachedSet("relationship_lines", JSON.stringify(relData));
    }

    // 同步 b_confirmedSchedule 中的 partner 字段
    const bcs = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    let bcsChanged = false;
    for (const schedList of Object.values(bcs)) {
        for (const ev of schedList) {
            if (ev.partner && ev.partner !== "多人小群") {
                const parts = ev.partner.split(/[、,]/).map(s => s.trim());
                const idx = parts.indexOf(oldName);
                if (idx !== -1) { parts[idx] = newName; ev.partner = parts.join("、"); bcsChanged = true; }
            }
        }
    }
    if (bcsChanged) cachedSet("b_confirmedSchedule", JSON.stringify(bcs));

    // 同步 group_expire_info 中的 participants
    const gei = JSON.parse(cachedGet("group_expire_info") || "{}");
    let geiChanged = false;
    for (const info of Object.values(gei)) {
        if (Array.isArray(info.participants)) {
            const i = info.participants.indexOf(oldName);
            if (i !== -1) { info.participants[i] = newName; geiChanged = true; }
        }
    }
    if (geiChanged) cachedSet("group_expire_info", JSON.stringify(gei));

    // 同步 group_timers 中的 participants 和 timerStatus key
    const timers = JSON.parse(cachedGet("group_timers") || "{}");
    let timersChanged = false;
    for (const timer of Object.values(timers)) {
        if (Array.isArray(timer.participants)) {
            const i = timer.participants.indexOf(oldName);
            if (i !== -1) { timer.participants[i] = newName; timersChanged = true; }
        }
        if (timer.timerStatus && timer.timerStatus[oldName]) {
            timer.timerStatus[newName] = timer.timerStatus[oldName];
            delete timer.timerStatus[oldName];
            timersChanged = true;
        }
    }
    if (timersChanged) cachedSet("group_timers", JSON.stringify(timers));

    // 同步 interaction_counts 中的 roleName key 和内层统计 key
    const ic = JSON.parse(cachedGet("interaction_counts") || "{}");
    let icChanged = false;
    const oldKey = `${platform}:${oldName}`;
    const newKey = `${platform}:${newName}`;
    if (ic[oldKey]) { ic[newKey] = ic[oldKey]; delete ic[oldKey]; icChanged = true; }
    for (const entry of Object.values(ic)) {
        for (const field of Object.keys(entry)) {
            if (entry[field] && typeof entry[field] === "object" && entry[field][oldName] !== undefined) {
                entry[field][newName] = entry[field][oldName];
                delete entry[field][oldName];
                icChanged = true;
            }
        }
    }
    if (icChanged) cachedSet("interaction_counts", JSON.stringify(ic));

    seal.replyToSender(ctx, msg, `✅ 角色名已由「${oldName}」改为「${newName}」。`);
    return seal.ext.newCmdExecuteResult(true);
}

// 2. 玩家名单
let cmd_role_list = {};
cmd_role_list.solve =(ctx, msg) => {
    let storage = getRoleStorage();
    let platform = msg.platform;
    let roles = storage[platform] || {};

    if (Object.keys(roles).length === 0) {
        seal.replyToSender(ctx, msg, `当前平台暂无已绑定的角色`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取 NPC 列表（全局存储）
    let npcList = JSON.parse(cachedGet("a_npc_list") || "[]");

    let rep = `📊 当前已绑定角色列表：\n`;
    // 新结构：uid为key，roleName在value[0]
    for (let [uid, info] of Object.entries(roles)) {
        const name = info[0];
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

    // 新结构：uid为key，按roleName查找
    const targetUidEntry = storage[platform] && Object.entries(storage[platform]).find(([_, v]) => v[0] === delName);
    if (!targetUidEntry) {
        seal.replyToSender(ctx, msg, `未找到角色「${delName}」，请检查输入`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const uid = targetUidEntry[0];
    const uidKey = `${platform}:${uid}`;

    // 1. 绑定记录
    delete storage[platform][uid];
    cachedSet("a_private_group", JSON.stringify(storage));

    // 2. 时间锁定
    const lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
    delete lockedSlots[uidKey];
    cachedSet("a_lockedSlots", JSON.stringify(lockedSlots));

    // 3. 已确认日程 + 释放该玩家占用的群号
    const confirmed = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const playerSchedules = confirmed[uidKey] || [];
    const groupsToRelease = playerSchedules
        .filter(ev => ev.group && ev.status === "active")
        .map(ev => ev.group);
    if (groupsToRelease.length > 0) {
        let groupList = JSON.parse(cachedGet("group") || "[]");
        for (const gid of groupsToRelease) {
            const occupiedIdx = groupList.indexOf(gid + "_占用");
            if (occupiedIdx !== -1) {
                groupList.splice(occupiedIdx, 1);
                groupList.push(gid);
            }
        }
        cachedSet("group", JSON.stringify(groupList));
    }
    delete confirmed[uidKey];
    cachedSet("b_confirmedSchedule", JSON.stringify(confirmed));

    // 4. 地点钥匙
    const placeKeys = JSON.parse(cachedGet("place_keys") || "{}");
    if (placeKeys[platform]) {
        delete placeKeys[platform][uid];
        cachedSet("place_keys", JSON.stringify(placeKeys));
    }

    // 5. 角色档案（性别/皮相/签名/年龄）
    const profiles = JSON.parse(cachedGet("sys_char_profiles") || "{}");
    delete profiles[uidKey];
    cachedSet("sys_char_profiles", JSON.stringify(profiles));

    // 6. 关系线（删除该玩家的条目，及其他人对该玩家的条目）
    const relData = JSON.parse(cachedGet("relationship_lines") || "{}");
    if (relData[platform]) {
        delete relData[platform][uid];
        for (const otherUid of Object.keys(relData[platform])) {
            delete relData[platform][otherUid][uid];
        }
        cachedSet("relationship_lines", JSON.stringify(relData));
    }

    // 7. 心动信发送次数记录
    const lovemailCounts = JSON.parse(cachedGet("lovemail_day_counts") || "{}");
    delete lovemailCounts[uid];
    cachedSet("lovemail_day_counts", JSON.stringify(lovemailCounts));

    // 7.5 交互统计（interaction_counts key 为 platform:roleName）
    const ic = JSON.parse(cachedGet("interaction_counts") || "{}");
    const icKey = `${platform}:${delName}`;
    let icChanged = false;
    if (ic[icKey]) { delete ic[icKey]; icChanged = true; }
    // 清除其他人记录中对该角色的引用
    for (const entry of Object.values(ic)) {
        for (const field of Object.keys(entry)) {
            if (entry[field] && typeof entry[field] === "object" && entry[field][delName] !== undefined) {
                delete entry[field][delName];
                icChanged = true;
            }
        }
    }
    if (icChanged) cachedSet("interaction_counts", JSON.stringify(ic));

    // 8. RPG数据（背包/属性/抽取记录/二手市场挂单）——全部存在主 ext
    {
        // 背包
        const invs = JSON.parse(cachedGet("global_inventories") || "{}");
        delete invs[uidKey];
        cachedSet("global_inventories", JSON.stringify(invs));

        // RPG属性
        const charAttrs = JSON.parse(cachedGet("sys_character_attrs") || "{}");
        delete charAttrs[uid];
        cachedSet("sys_character_attrs", JSON.stringify(charAttrs));

        // 抽取记录
        const drawRecs = JSON.parse(cachedGet("player_draw_records") || "{}");
        delete drawRecs[uidKey];
        cachedSet("player_draw_records", JSON.stringify(drawRecs));

        // 二手市场：撤销该角色的所有挂单
        const market = JSON.parse(cachedGet("secondhand_market") || "{}");
        let marketChanged = false;
        for (const code of Object.keys(market)) {
            if (market[code].sellerRole === delName) { delete market[code]; marketChanged = true; }
        }
        if (marketChanged) cachedSet("secondhand_market", JSON.stringify(market));
    }

    seal.replyToSender(ctx, msg, `✅ 已成功清除玩家「${delName}」的全部数据`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["清除玩家"] = cmd_del_role;


// ========================
// ========================
// 🗝️ 地点权限管理系统
// ========================

// --- 核心工具函数 ---
const store = {
    get: (key) => JSON.parse(cachedGet(key) || "{}"),
    set: (key, val) => cachedSet(key, JSON.stringify(val))
};

// 将辅助账号 uid 解析为主账号 uid（找不到则原样返回）
const getPrimaryUid = (platform, uid) => {
    const extras = store.get("extra_accounts");
    return extras[`${platform}:${uid}`] || uid;
};

// 新结构：a_private_group[platform][uid] = [roleName, gid]
// getRoleName: O(1) 查找（uid为key）
const getRoleName = (ctx, msg) => {
    const platform = msg.platform;
    const rawUid = msg.sender.userId.replace(`${platform}:`, "");
    const uid = getPrimaryUid(platform, rawUid);
    return store.get("a_private_group")[platform]?.[uid]?.[0] || null;
};

// getUserRoleName: O(1) 查找
const getUserRoleName = (platform, fullUid) => {
    const uid = getPrimaryUid(platform, String(fullUid).replace(`${platform}:`, ""));
    return store.get("a_private_group")[platform]?.[uid]?.[0] || null;
};

// 通过 roleName 反查 uid（O(n) 扫描，仅在必要时使用）
const getUidByRoleName = (platform, roleName) => {
    const roles = store.get("a_private_group")[platform] || {};
    return Object.entries(roles).find(([_, v]) => v[0] === roleName)?.[0] || null;
};

// uid → roleName 显示（找不到则返回 uid 本身）
const resolveUidToName = (platform, uid) => {
    return store.get("a_private_group")[platform]?.[uid]?.[0] || uid;
};

// 跨平台查找 uid → roleName
const resolveUidToNameAnyPlatform = (uid) => {
    const apg = store.get("a_private_group");
    for (const platform in apg) {
        if (apg[platform][uid]) return apg[platform][uid][0];
    }
    return uid;
};

// ========================
// 🔌 共享 API：卫星插件统一入口
// ========================
// 所有插件运行在同一个 JS 运行时，经 globalThis 共享。
// 卫星插件（RPG/设置/社交/写信综/晚餐）调用时懒获取 globalThis.__changriApi，
// 不要在卫星文件里复制这些函数的实现。
const changriApi = {
    ext,
    // 存储（带缓存，卫星读写主存储必须走这两对函数）
    kvGetRaw: cachedGet,
    kvSetRaw: cachedSet,
    kvGet(key, def) {
        const raw = cachedGet(key);
        if (raw === null || raw === undefined || raw === "") return def;
        try { return JSON.parse(raw); } catch (e) { return def; }
    },
    kvSet(key, val) { cachedSet(key, JSON.stringify(val)); },
    getStorageInt,
    // 身份与权限
    getPrimaryUid,
    getRoleName,
    getUserRoleName,
    getUidByRoleName,
    resolveUidToName,
    resolveUidToNameAnyPlatform,
    isUserAdmin,
    isUserFeatureEnabled,
    // 互动计数与公告
    recordMeetingAndAnnounce,
    recordInteractionStat,
    // 统计数据读取（统计卫星用）
    getUserStats,
    getRoleStorage,
    getInteractionCounts,
    getTop3Text,
    // 邀约公共校验与建群（心愿等卫星用）
    checkTsFeatureWindow,
    parseAndValidateTime,
    checkRealityHourLimit,
    checkPlaceCommon,
    checkAcceptanceConflicts,
    isLetterSystemEnabled,
    checkAndCostLetterCoin,
    getCharProfile,
    finalizeGroupCreation,
    checkNoQuitBlocker,
    // 消息模板与存档（礼物等卫星用）
    applyMsgTemplate,
    isArchiveEnabled,
    postToArchive,
    // getRoleDetails/sendTextToGroup 是 const 箭头函数（不提升），需包一层延迟取值
    getRoleDetails: (platform, name) => getRoleDetails(platform, name),
    getSafeEndPoint,
    sendTextToGroup: (platform, gid, text) => sendTextToGroup(platform, gid, text),
    // OneBot WS（常驻连接）
    ws,
};
globalThis.__changriApi = changriApi;
try { ext._api = changriApi; } catch (e) { console.log("[长日系统] ext._api 挂载失败（不影响 globalThis 共享）"); }

// ========================
// 数据结构迁移：roleName-key → uid-key
// ========================
function migrateToUidIndex() {
    const apg = store.get("a_private_group");
    let migrated = false;

    for (const platform in apg) {
        const platformData = apg[platform];
        const newPlatformData = {};
        let platformMigrated = false;

        for (const key in platformData) {
            const val = platformData[key];
            // 新结构特征：val[0] 是 roleName（字符串），val[1] 是 gid（纯数字字符串）
            // 旧结构特征：key 是 roleName，val[0] 是 uid（纯数字字符串），val[1] 是 gid
            // 判断依据：uid 通常是纯数字，roleName 通常包含中文或字母
            const looksLikeUid = /^\d+$/.test(key);
            if (!looksLikeUid) {
                // 旧结构：key = roleName, val = [uid, gid]
                const roleName = key;
                const uid = val[0];
                const gid = val[1];
                if (!uid) continue; // 跳过无效记录
                if (!newPlatformData[uid]) {
                    newPlatformData[uid] = [roleName, gid];
                    platformMigrated = true;
                    console.log(`[迁移] ${platform} ${roleName}(${uid}) → uid-key`);
                }
            } else {
                // 新结构：key = uid，直接复制
                newPlatformData[key] = val;
            }
        }

        if (platformMigrated) {
            apg[platform] = newPlatformData;
            migrated = true;
        }
    }

    if (migrated) {
        store.set("a_private_group", apg);
        console.log("[迁移] a_private_group 迁移完成（roleName-key → uid-key）");
    }

    // 迁移 feature_user_blocklist: roleName-key → uid-key
    const fbl = store.get("feature_user_blocklist");
    let fblMigrated = false;
    const newFbl = {};
    for (const k in fbl) {
        // 旧结构：key = platform:roleName；新结构：key = platform:uid
        const colonIdx = k.indexOf(':');
        if (colonIdx === -1) { newFbl[k] = fbl[k]; continue; }
        const plat = k.slice(0, colonIdx);
        const nameOrUid = k.slice(colonIdx + 1);
        const looksLikeUid = /^\d+$/.test(nameOrUid);
        if (!looksLikeUid) {
            // 旧：roleName → 查找 uid
            const uidLookup = getUidByRoleName(plat, nameOrUid);
            if (uidLookup) {
                newFbl[`${plat}:${uidLookup}`] = fbl[k];
                fblMigrated = true;
            } else {
                newFbl[k] = fbl[k]; // 无法迁移，保留
            }
        } else {
            newFbl[k] = fbl[k];
        }
    }
    if (fblMigrated) {
        store.set("feature_user_blocklist", newFbl);
        console.log("[迁移] feature_user_blocklist 迁移完成");
    }

    // 迁移 place_keys: roleName-key → uid-key（per platform）
    const placeKeys = store.get("place_keys");
    let pkMigrated = false;
    for (const plat in placeKeys) {
        const platData = placeKeys[plat];
        const newPlatData = {};
        let changed = false;
        for (const nameOrUid in platData) {
            const looksLikeUid = /^\d+$/.test(nameOrUid);
            if (!looksLikeUid) {
                const uidLookup = getUidByRoleName(plat, nameOrUid);
                if (uidLookup) {
                    newPlatData[uidLookup] = platData[nameOrUid];
                    changed = true;
                } else {
                    newPlatData[nameOrUid] = platData[nameOrUid];
                }
            } else {
                newPlatData[nameOrUid] = platData[nameOrUid];
            }
        }
        if (changed) {
            placeKeys[plat] = newPlatData;
            pkMigrated = true;
        }
    }
    if (pkMigrated) {
        store.set("place_keys", placeKeys);
        console.log("[迁移] place_keys 迁移完成");
    }
}

// 在扩展加载时执行迁移
try {
    migrateToUidIndex();
} catch (e) {
    console.error("[迁移] migrateToUidIndex 执行失败:", e);
}

// ========================
// 角色档案系统
// ========================
function getCharProfile(platform, roleName) {
    // 新结构：通过 roleName 反查 uid
    const uid = getUidByRoleName(platform, roleName);
    if (!uid) return {};
    return store.get("sys_char_profiles")[`${platform}:${uid}`] || {};
}

function setCharProfile(platform, roleName, patch) {
    const uid = getUidByRoleName(platform, roleName);
    if (!uid) return;
    const profiles = store.get("sys_char_profiles");
    const key = `${platform}:${uid}`;
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

// --- 逻辑判断逻辑 ---
function checkPlacePermission(platform, roleName, placeName) {
    const config = store.get("place_system_config");
    if (!config.enabled || config.enabled === undefined) return { allowed: true };

    const places = store.get("available_places");
    const place = places[placeName];

    // 处理私人房间
    if (!place) {
        const owner = placeName.match(/^(.+?)的房间$/)?.[1];
        if (!owner) return { allowed: false, reason: "地点不存在" };
        const ownerUid = getUidByRoleName(platform, owner);
        return { allowed: !!ownerUid, reason: "地点不存在或私人房间未激活" };
    }

    if (!place.locked) return { allowed: true };
    // 新结构：place_keys[platform][uid]
    const uid = getUidByRoleName(platform, roleName);
    const hasKey = uid && (store.get("place_keys")[platform]?.[uid] || []).includes(placeName);
    return { allowed: !!hasKey, reason: "需要钥匙" };
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
  const placeSystemConfig = JSON.parse(cachedGet("place_system_config") || '{"enabled": false}');
  const availablePlaces = JSON.parse(cachedGet("available_places") || "{}");
  
  // --- 情况 A: 地点系统已【启用】 (严格检查模式) ---
  if (placeSystemConfig.enabled) {

    // 新增：检查私人房间是否被禁用
    const allowPrivateRooms = JSON.parse(cachedGet("allow_private_rooms") || "true");
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
      // 获取该用户的钥匙，按权限分类显示地点
      const senderUid = getUidByRoleName(platform, senderName);
      const userKeys = senderUid ? (JSON.parse(cachedGet("place_keys") || "{}")[platform]?.[senderUid] || []) : [];

      let errorMsg = `⚠️ 地点「${place}」不可用：${permission.reason}\n`;

      if (Object.keys(availablePlaces).length > 0) {
        const accessible = [], locked = [];
        Object.entries(availablePlaces).forEach(([placeName, data]) => {
          const desc = data.desc ? `（${data.desc}）` : '';
          if (!data.locked) {
            accessible.push(`📍 ${placeName}${desc}`);
          } else if (userKeys.includes(placeName)) {
            accessible.push(`🔑 ${placeName}${desc}`);
          } else {
            locked.push(`🔒 ${placeName}${desc}`);
          }
        });
        if (accessible.length) {
          errorMsg += "\n✅ 你可以进入：\n" + accessible.map(s => `  ${s}`).join("\n") + "\n";
        }
        if (locked.length) {
          errorMsg += "\n🔒 需要钥匙：\n" + locked.map(s => `  ${s}`).join("\n") + "\n";
        }
      }

      errorMsg += "\n💡 ";
      if (allowPrivateRooms) errorMsg += "也可用「[角色名]的房间」格式；";
      errorMsg += "「地点 查看」查看完整列表";

      return { valid: false, errorMsg: errorMsg };
    }
  } 
  
  // --- 情况 B: 地点系统已【禁用】 (宽松检查模式，直接通过) ---
  // 地点系统未启用时不做任何地点校验，也不显示地点列表
  
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
    // 新结构：place_keys[platform][uid]
    const roleUid = role ? getUidByRoleName(platform, role) : null;
    const userKeys = roleUid ? (store.get("place_keys")[platform]?.[roleUid] || []) : [];

    if (sub === "查看") {
        const placeConfig = JSON.parse(cachedGet("place_system_config") || '{"enabled": false}');
        const allowPrivateRooms = JSON.parse(cachedGet("allow_private_rooms") || "true");
        const placeList = Object.entries(places);

        let rep = "🏢 地点列表\n";
        if (placeConfig.enabled) {
            if (placeList.length === 0) {
                rep += "（暂无公共地点）\n";
            } else {
                placeList.forEach(([name, data]) => {
                    let tag;
                    if (!data.locked) {
                        tag = "📍";
                    } else if (userKeys.includes(name)) {
                        tag = "🔑 已解锁";
                    } else {
                        tag = "🔒 需要钥匙";
                    }
                    rep += `${tag} ${name}${data.desc ? `（${data.desc}）` : ""}\n`;
                });
            }
            rep += `\n🏠 私人房间：${allowPrivateRooms ? "✅ 可用" : "❌ 已关闭"}`;
            if (allowPrivateRooms) rep += "\n💡 使用「[角色名]的房间」格式";
        } else {
            if (placeList.length === 0) {
                rep += "（暂无地点）\n";
            } else {
                placeList.forEach(([name, data]) => {
                    rep += `📍 ${name}${data.desc ? `（${data.desc}）` : ""}\n`;
                });
            }
            if (allowPrivateRooms) rep += "\n💡 也可使用「[角色名]的房间」格式的私人地点";
        }
        return seal.replyToSender(ctx, msg, rep);
    }

    if (sub === "钥匙") {
        if (!role) return seal.replyToSender(ctx, msg, "❌ 未绑定角色，无法查看钥匙");
        if (!userKeys.length) return seal.replyToSender(ctx, msg, "🔐 你目前没有任何地点钥匙");
        let rep = "🔑 你持有的钥匙：\n";
        userKeys.forEach(k => {
            const exists = places[k];
            if (!exists) {
                rep += `  ⚠️ ${k}（地点已被删除）\n`;
            } else {
                rep += `  🔑 ${k}${exists.desc ? `（${exists.desc}）` : ""}${exists.locked ? "" : "（当前未上锁）"}\n`;
            }
        });
        return seal.replyToSender(ctx, msg, rep);
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
    let places = JSON.parse(cachedGet("available_places") || "{}");
    let keys = JSON.parse(cachedGet("place_keys") || "{}");
    const pf = msg.platform;

    switch(op) {
        case "添加": {
            const arg = cmdArgs.getArgN(2);
            if (!arg) return seal.replyToSender(ctx, msg, "用法：.地点管理 添加 地点名:描述\n示例：.地点管理 添加 庭院:阳光充足的小院");
            const [rawName, desc] = arg.split(/[:：]/);
            const name = (rawName || "").trim();
            if (!name) return seal.replyToSender(ctx, msg, "❌ 地点名不能为空");
            if (places[name]) return seal.replyToSender(ctx, msg, `⚠️ 地点「${name}」已存在，如需修改描述请先删除再重新添加`);
            const trimDesc = (desc || "").trim();
            places[name] = { desc: trimDesc, locked: false, creator: "管理员", created_at: new Date().toLocaleString() };
            seal.replyToSender(ctx, msg, `✅ 已添加地点：${name}${trimDesc ? `\n📝 描述：${trimDesc}` : ""}`);
            break;
        }
        case "删除": {
            const name = cmdArgs.getArgN(2);
            if (!name) { seal.replyToSender(ctx, msg, "用法：.地点管理 删除 地点名"); break; }
            if (!places[name]) {
                const available = Object.keys(places);
                const hint = available.length ? `\n现有地点：${available.join("、")}` : "\n（当前无地点）";
                seal.replyToSender(ctx, msg, `❌ 地点「${name}」不存在${hint}`);
                break;
            }
            delete places[name];
            // 同步清理所有平台中该地点的钥匙记录
            let cleanedCount = 0;
            for (const plat in keys) {
                for (const uid in keys[plat]) {
                    const idx = keys[plat][uid].indexOf(name);
                    if (idx !== -1) { keys[plat][uid].splice(idx, 1); cleanedCount++; }
                }
            }
            const cleanMsg = cleanedCount > 0 ? `\n🔑 已同步清理 ${cleanedCount} 个角色的相关钥匙` : "";
            seal.replyToSender(ctx, msg, `🗑️ 已删除地点：${name}${cleanMsg}`);
            break;
        }
        case "开关": {
            const name = cmdArgs.getArgN(2);
            if (!name) { seal.replyToSender(ctx, msg, "用法：.地点管理 开关 地点名"); break; }
            if (!places[name]) {
                const available = Object.keys(places);
                const hint = available.length ? `\n现有地点：${available.join("、")}` : "\n（当前无地点）";
                seal.replyToSender(ctx, msg, `❌ 地点「${name}」不存在${hint}`);
                break;
            }
            places[name].locked = !places[name].locked;
            const newState = places[name].locked ? "🔒 已上锁" : "🔓 已解锁";
            const lockHint = places[name].locked ? "\n持有钥匙的角色仍可进入" : "";
            seal.replyToSender(ctx, msg, `${newState}：${name}${lockHint}`);
            break;
        }
        case "钥匙": {
            const role = cmdArgs.getArgN(2);
            const pName = cmdArgs.getArgN(3);
            if (!role || !pName) return seal.replyToSender(ctx, msg, "用法：.地点管理 钥匙 角色名 地点名\n示例：.地点管理 钥匙 张三 图书馆");
            if (!places[pName]) {
                const available = Object.keys(places);
                const hint = available.length ? `\n现有地点：${available.join("、")}` : "\n（当前无地点）";
                return seal.replyToSender(ctx, msg, `❌ 地点「${pName}」不存在${hint}`);
            }
            // 新结构：place_keys[platform][uid]
            const targetUid = getUidByRoleName(pf, role);
            if (!targetUid) { seal.replyToSender(ctx, msg, `❌ 找不到角色「${role}」，请确认角色名是否正确`); break; }
            if (!keys[pf]) keys[pf] = {};
            if (!keys[pf][targetUid]) keys[pf][targetUid] = [];

            const idx = keys[pf][targetUid].indexOf(pName);
            if (idx === -1) {
                keys[pf][targetUid].push(pName);
                const unlockedHint = !places[pName].locked ? "\n（提示：该地点当前未上锁，钥匙暂不生效）" : "";
                seal.replyToSender(ctx, msg, `🔑 已发放「${pName}」钥匙给「${role}」${unlockedHint}`);
            } else {
                keys[pf][targetUid].splice(idx, 1);
                seal.replyToSender(ctx, msg, `🚫 已收回「${role}」的「${pName}」钥匙`);
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
          const subCmd = cmdArgs.getArgN(2);
          if (subCmd === "on" || subCmd === "开" || subCmd === "开启") {
            cachedSet("allow_private_rooms", "true");
            seal.replyToSender(ctx, msg, "✅ 私人房间功能已开启\n玩家可以使用「[角色名]的房间」格式进行私约");
          } else if (subCmd === "off" || subCmd === "关" || subCmd === "关闭") {
            cachedSet("allow_private_rooms", "false");
            seal.replyToSender(ctx, msg, "❌ 私人房间功能已关闭\n玩家不能再使用「[角色名]的房间」格式");
          } else {
            const cur = JSON.parse(cachedGet("allow_private_rooms") || "true");
            seal.replyToSender(ctx, msg, `🏠 私人房间当前状态：${cur ? "✅ 开启" : "❌ 关闭"}\n切换：.地点管理 私人房间 on/off`);
          }
          break;
        }
        default: {
            const allowPrivate = JSON.parse(cachedGet("allow_private_rooms") || "true");
            const helpMsg = [
                "📚 地点管理帮助",
                "",
                "【添加】.地点管理 添加 地点名:描述",
                "  例：.地点管理 添加 庭院:阳光充足的小院",
                "  描述可留空，支持中英文冒号",
                "",
                "【删除】.地点管理 删除 地点名",
                "  会自动清理该地点的所有钥匙记录",
                "",
                "【开关】.地点管理 开关 地点名",
                "  切换上锁/解锁状态，上锁后无钥匙者无法进入",
                "",
                "【钥匙】.地点管理 钥匙 角色名 地点名",
                "  再次执行同一命令可收回钥匙（切换式）",
                "",
                "【清空】.地点管理 清空 Y",
                "  ⚠️ 永久删除所有地点和钥匙数据，需加 Y 确认",
                "",
                `【私人房间】.地点管理 私人房间 on/off`,
                `  当前状态：${allowPrivate ? "✅ 开启" : "❌ 关闭"}`,
                "  开启后玩家可用「[角色名]的房间」格式",
                "",
                "💡 地点名、角色名均区分大小写"
            ].join("\n");
            seal.replyToSender(ctx, msg, helpMsg);
            break;
        }
    }
    cachedSet("available_places", JSON.stringify(places));
    cachedSet("place_keys", JSON.stringify(keys));
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
    if (!arg) return seal.replyToSender(ctx, msg, "格式：.批量设置地点 地点1:描述/地点2:描述\n示例：.批量设置地点 图书馆:安静的阅读空间/咖啡厅:温馨小店");

    let places = JSON.parse(cachedGet("available_places") || "{}");
    const items = arg.split("/");
    const added = [], skipped = [];
    items.forEach(item => {
        const [rawName, desc] = item.split(/[:：]/); // 支持中英文冒号
        const name = (rawName || "").trim();
        if (!name) { skipped.push("（空名称）"); return; }
        places[name] = { desc: (desc || "").trim(), locked: false, creator: "管理员", created_at: new Date().toLocaleString() };
        added.push(name);
    });
    cachedSet("available_places", JSON.stringify(places));
    let rep = `✅ 成功添加 ${added.length} 个地点：${added.join("、")}`;
    if (skipped.length) rep += `\n⚠️ 跳过 ${skipped.length} 个无效条目`;
    seal.replyToSender(ctx, msg, rep);
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
    let keys = JSON.parse(cachedGet("place_keys") || "{}");
    const pf = msg.platform;
    if (!keys[pf]) keys[pf] = {};

    const found = [], notFound = [];
    roles.forEach(r => {
        const rName = r.trim();
        if (!rName) return;
        // 新结构：place_keys[platform][uid]
        const rUid = getUidByRoleName(pf, rName);
        if (!rUid) { notFound.push(rName); return; }
        if (!keys[pf][rUid]) keys[pf][rUid] = [];
        pNames.forEach(p => {
            const pTrimmed = p.trim();
            if (pTrimmed && !keys[pf][rUid].includes(pTrimmed)) keys[pf][rUid].push(pTrimmed);
        });
        found.push(rName);
    });
    cachedSet("place_keys", JSON.stringify(keys));
    let rep = `✅ 已授权 ${found.length} 个角色：${found.join("、") || "无"}`;
    if (notFound.length) rep += `\n⚠️ 未找到以下角色：${notFound.join("、")}\n（请检查角色名是否正确）`;
    seal.replyToSender(ctx, msg, rep);
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
    const places = JSON.parse(cachedGet("available_places") || "{}");
    const keys = JSON.parse(cachedGet("place_keys") || "{}")[msg.platform] || {};
    
    const placeConfig = JSON.parse(cachedGet("place_system_config") || '{"enabled": false}');
    const allowPrivate = JSON.parse(cachedGet("allow_private_rooms") || "true");
    const placeCount = Object.keys(places).length;
    let rep = "🏢 地点系统详细报告\n";
    rep += "━━━━━━━━━━━━\n";
    rep += `系统状态：${placeConfig.enabled ? "✅ 已启用" : "⭕ 未启用"}\n`;
    rep += `私人房间：${allowPrivate ? "✅ 开启" : "❌ 关闭"}\n`;
    rep += `地点总数：${placeCount} 个\n`;
    rep += "━━━━━━━━━━━━\n";
    if (placeCount === 0) {
        rep += "（暂无地点）";
    } else {
        Object.entries(places).forEach(([name, data]) => {
            // 新结构：keys的key是uid，显示时转为roleName
            const holders = Object.entries(keys).filter(([_, kList]) => kList.includes(name)).map(([uid]) => resolveUidToName(msg.platform, uid));
            rep += `${data.locked ? "🔒" : "🔓"} ${name}\n`;
            if (data.desc) rep += `   📝 ${data.desc}\n`;
            rep += `   🔑 持钥匙者：${holders.join("、") || "无"}\n`;
        });
    }
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看地点详情"] = cmdViewPlace;
ext.cmdMap["查看钥匙分配"] = cmdViewPlace; // 共用逻辑

// ========================
// 💕 约会与邀约系统
// ========================
function checkTsFeatureWindow(featureKey) {
    const windows = JSON.parse(cachedGet("ts_feature_windows") || "[]");
    const entry = windows.find(w => w.feature === featureKey);
    if (!entry) return { ok: true };
    const h = new Date().getHours();
    if (h >= entry.start && h < entry.end) return { ok: true };
    const s = String(entry.start).padStart(2, "0");
    const e = String(entry.end).padStart(2, "0");
    return { ok: false, msg: `⚠️ 该功能当前不可用，开放时间为 ${s}:00–${e}:00。` };
}

function checkRealityHourLimit(timeStr, ctx, msg) {
    const slotSizeRaw = cachedGet("ts_reality_slot_size");
    const slotSize = slotSizeRaw ? JSON.parse(slotSizeRaw) : 0;
    if (!slotSize) {
        // 兜底：兼容旧版 strict_hour_match 开关
        const enableStorage = cachedGet("ts_strict_hour_match");
        const enable = enableStorage ? JSON.parse(enableStorage) : seal.ext.getBoolConfig(ext, "开启现实时段校验");
        if (!enable) return true;
    } else if (slotSize <= 0) {
        return true;
    }

    const now = new Date();
    const currentHour = now.getHours();
    const currentTimeStr = `${String(currentHour).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

    let startHour = null;
    const match = timeStr.match(/(\d{2}):\d{2}-/);
    if (match) startHour = parseInt(match[1], 10);

    if (startHour === null) {
        seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，无法进行时段检查");
        return false;
    }

    const sz = slotSize || 1;
    const currentSlot = Math.floor(currentHour / sz);
    const startSlot   = Math.floor(startHour   / sz);

    if (startSlot !== currentSlot) {
        const slotStart = currentSlot * sz;
        const slotEnd   = Math.min(slotStart + sz, 24) - 1;
        seal.replyToSender(ctx, msg,
            `⚠️ 时段限制：当前现实时间为 ${currentTimeStr}，本时段（现实 ${String(slotStart).padStart(2,'0')}:00–${String(slotEnd).padStart(2,'0')}:59）` +
            `只能发起戏内 ${String(slotStart).padStart(2,'0')}:xx–${String(slotEnd).padStart(2,'0')}:xx 开始的剧情邀约。\n\n` +
            `💡 如需取消此限制，请联系管理调整「现实/戏内时间对照档位」。`);
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
        // 新结构：通过 roleName 反查 uid
        const toUidLookup = Object.entries(a_private_group[platform] || {}).find(([_, v]) => v[0] === toname)?.[0];
        if (!toUidLookup) {
            failed.push(`${toname}（未注册）`);
            continue;
        }
        const toKey = `${platform}:${toUidLookup}`;
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
        // 新结构：通过 roleName 反查 uid
        const toUidLookup2 = Object.entries(a_private_group[platform] || {}).find(([_, v]) => v[0] === toname)?.[0];
        if (!toUidLookup2) continue;
        const toKey = `${platform}:${toUidLookup2}`;
        
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
    
    let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    let existingParticipants = groupExpireInfo[groupId]?.participants || [];
    
    if (existingParticipants.length === 0) {
        const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
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
            expireTime: Date.now() + (getStorageInt("group_expire_hours", 48) * 3600000),
            participants: allParticipants,
            subtype: "私密",
            day: day,
            time: time,
            place: place
        };
    }
    cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));
    
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    
    for (const [key, schedules] of Object.entries(b_confirmedSchedule)) {
        for (let ev of schedules) {
            if (ev.group === groupId && ev.day === day && ev.time === time) {
                if (allParticipants.length > 2) {
                    ev.partner = "多人小群";
                } else {
                    const currentPartners = ev.partner.split(/[、,]/).map(s => s.trim());
                    const newPartners = [...new Set([...currentPartners, ...newNames])];
                    ev.partner = newPartners.join("、");
                }
            }
        }
    }
    
    for (let newName of newNames) {
        // 新结构：通过 roleName 反查 uid
        const newNameUid = getUidByRoleName(platform, newName);
        const targetInfo = newNameUid ? a_private_group[platform][newNameUid] : null;
        if (!targetInfo) continue;
        const targetUid = newNameUid;
        const targetKey = `${platform}:${targetUid}`;
        if (!b_confirmedSchedule[targetKey]) b_confirmedSchedule[targetKey] = [];
        
        const alreadyExists = b_confirmedSchedule[targetKey].some(ev => 
            ev.group === groupId && ev.day === day && ev.time === time
        );
        if (!alreadyExists) {
            b_confirmedSchedule[targetKey].push({
                day: day,
                time: time,
                partner: allParticipants.length > 2 ? "多人小群" : allParticipants.find(n => n !== newName) || allParticipants.join("、"),
                subtype: "私密",
                place: place,
                group: groupId,
                status: "active"
            });
        }
    }
    cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    
    let groupTimers = JSON.parse(cachedGet("group_timers") || "{}");
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
        cachedSet("group_timers", JSON.stringify(groupTimers));
    }
    
    // 更新群名
    const nameTag = allParticipants.length > 2 ? "多人" : allParticipants.join("、");
    const newGroupName = `私密 ${day} ${time} ${place} ${nameTag}`;
    const renameMsg = seal.newMessage();
    renameMsg.messageType = "group";
    renameMsg.groupId = `${platform}-Group:${groupId}`;
    const renameCtx = seal.createTempCtx(ctx.endPoint, renameMsg);
    setGroupName(renameCtx, renameMsg, groupId, newGroupName);

    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${groupId}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    const joinNotice = `🎉 欢迎新伙伴加入！\n\n${newNames.join("、")} 也选择了在 ${day} ${time} 前往【${place}】。\n现在你们可以一起进行这场约会啦！\n\n当前参与者：${allParticipants.join("、")}`;
    seal.replyToSender(groupCtx, groupMsg, joinNotice);

    // 通知新成员（跳过发起者 sendname，发起者由私约指令的 successMsg 告知）
    for (let newName of newNames) {
        if (newName === sendname) continue;
        const newNameUid2 = getUidByRoleName(platform, newName);
        const targetInfo = newNameUid2 ? a_private_group[platform][newNameUid2] : null;
        if (targetInfo) {
            const targetGroupId = targetInfo[1];
            const privateMsg = seal.newMessage();
            privateMsg.messageType = "group";
            privateMsg.groupId = `${platform}-Group:${targetGroupId}`;
            const privateCtx = seal.createTempCtx(ctx.endPoint, privateMsg);
            const notice = `✨ ${sendname} 发起的私约已自动合并到现有约会中！\n\n📅 时间：${day} ${time}\n📍 地点：${place}\n👥 参与者：${allParticipants.join("、")}\n💬 群号：${groupId}\n\n请自行申请入群，享受约会时光~`;
            seal.replyToSender(privateCtx, privateMsg, notice);
        }
    }

    return true;
}

async function checkAppointmentPreflight(ctx, msg, cmdArgs, subtype, minDurationKey, minDurationOverride) {
    let config = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    let enable_general_appointment = config.enable_general_appointment ?? true;
    if (!enable_general_appointment) {
        return { valid: false, errorMsg: "📅 当前已禁用通用发起邀约功能，无法发起" + (subtype === "电话" ? "电话" : "私密邀约") + "。" };
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    const sendname = getRoleName(ctx, msg);
    if (!sendname) return { valid: false, errorMsg: "请先使用「创建新角色」绑定角色" };

    // 新结构：blockMap[uid]
    const sendUid = getPrimaryUid(platform, uid);
    if (!isUserFeatureEnabled(sendUid, "enable_general_appointment")) {
        return { valid: false, errorMsg: "🚫 您已被禁止使用发起邀约功能" };
    }

    const globalDay = cachedGet("global_days");
    if (!globalDay) return { valid: false, errorMsg: "⚠️ 当前尚未设置全局天数，请先使用 \".设置天数 D1\"" };
    const day = globalDay;

    const rawTime = cmdArgs.getArgN(1);
    const namesArg = subtype === "电话" ? cmdArgs.getArgN(2) : cmdArgs.getArgN(3);
    const placeOrTitle = subtype === "电话" ? cmdArgs.getArgN(3) : cmdArgs.getArgN(2); 
    if (!rawTime || !namesArg) {
        const exampleTime = getExampleTimeRange();
        let helpMsg = "";
        if (subtype === "电话") {
            helpMsg = `⚠️ 参数不足，正确格式：\n电话 ${exampleTime} 邀请人1[/邀请人2/...] [标题]\n示例：\n电话 ${exampleTime} 张三\n电话 ${exampleTime} 李四/王五 一起聊聊`;
        } else {
            const cmdName = subtype === "私密" ? "私约" : subtype;
            helpMsg = `⚠️ 参数不足，正确格式：\n${cmdName} ${exampleTime} 地点 对方角色名[/对方2/...]\n示例：\n${cmdName} ${exampleTime} 咖啡厅 张三\n${cmdName} ${exampleTime} 餐厅 李四/王五`;
        }
        return { valid: false, errorMsg: helpMsg };
    }

    const allowedRanges = JSON.parse(cachedGet("allowed_appointment_times") || "[]");
    const durationConfig = JSON.parse(cachedGet("appointment_duration_config") || "{}");
    const minDuration = minDurationOverride !== undefined ? minDurationOverride
        : (durationConfig[minDurationKey] !== undefined ? durationConfig[minDurationKey] : (minDurationKey === "phone" ? 29 : 59));
    const timeRes = parseAndValidateTime(rawTime, allowedRanges, minDuration, subtype);
    if (!timeRes.valid) return { valid: false, errorMsg: timeRes.errorMsg };
    const time = timeRes.time;

    if (!checkRealityHourLimit(time, ctx, msg)) return { valid: false, errorMsg: "" };

    // 时间调度：禁约时段（按游戏日）
    {
        const _blocked = JSON.parse(cachedGet("ts_blocked_by_day") || "{}")[day] || [];
        if (_blocked.length > 0) {
            const _startHour = parseInt(time.split(":")[0]);
            if (_blocked.includes(_startHour)) {
                return { valid: false, errorMsg: `⚠️ ${day} ${String(_startHour).padStart(2,"0")}:00 时段已被系统禁约，请选择其他时间。` };
            }
        }
    }

    // 时间调度：允许弧长（小时）
    {
        const _allowedDurs = JSON.parse(cachedGet("ts_allowed_durations") || "[]");
        if (_allowedDurs.length > 0) {
            const _m = time.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/);
            if (_m) {
                const _durMins = (parseInt(_m[3]) * 60 + parseInt(_m[4])) - (parseInt(_m[1]) * 60 + parseInt(_m[2]));
                const _durHours = _durMins / 60;
                if (!_allowedDurs.includes(_durHours)) {
                    const _opts = _allowedDurs.map(h => `${h}h`).join("、");
                    return { valid: false, errorMsg: `⚠️ 邀约时长不符，当前允许的弧长为：${_opts}。` };
                }
            }
        }
    }

    const names = namesArg.replace(/，/g, "/").split("/").map(n => n.trim()).filter(Boolean);
    const isMulti = names.length > 1;
    const fromKey = `${platform}:${uid}`;

    let a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
    const { selfLocked, failed: lockFailed } = checkLockedSlots(platform, day, time, fromKey, sendname, names, a_private_group, a_lockedSlots);
    if (selfLocked) return { valid: false, errorMsg: `⚠️ 你在 ${day} ${time} 段与锁定时间重叠，无法发起预约` };
    if (lockFailed.length) return { valid: false, errorMsg: `⚠️ 无法发起${subtype}，以下对象不符合条件：\n- ${lockFailed.join("\n- ")}` };

    if (subtype !== "电话") {
        const instructionName = subtype === "私密" ? "私约" : subtype;
        const placeCheck = checkPlaceCommon(platform, sendname, placeOrTitle, instructionName);
        if (!placeCheck.valid) return { valid: false, errorMsg: placeCheck.errorMsg };
        if (placeCheck.warningMsg) seal.replyToSender(ctx, msg, placeCheck.warningMsg);
    }

    if (!(await checkNoQuitBlocker(uid, ctx, msg))) {
        return { valid: false, errorMsg: "🚫 您仍有未退出的违规临时群，无法发起邀约" };
    }

    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");

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

    const autoMerge = (subtype === "私密") && (JSON.parse(cachedGet("auto_merge_duplicate_private") || "false"));
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
        const joinEnabled = cachedGet("enable_join_existing_appointment") === "true";
        const joinHint = joinEnabled ? `\n💡 你可以使用「申请加入 角色名 时间点」尝试加入对方的预约。` : "";
        return {
            valid: false,
            errorMsg: `⚠️ 以下角色在 ${day} ${time} 时段已有安排：${conflictNames}${joinHint}`
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
    ctx, msg, platform, sendname, sendid, subtype, day, time, place, names, title = "", isMulti
}) {
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");

    // 直接构造已确认的数据体并调用 finalizeGroupCreation 建群
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
        const gid = await finalizeGroupCreation(platform, ctx, msg, groupData, participants);
        if (gid === false) return { success: false };
        names.forEach(n => recordInteractionStat(platform, sendname, n, "appt"));
        return { success: true, isMulti, names, gid };
    } else {
        const toname = names[0];
        // 新结构：通过 roleName 反查 uid，再取 gid
        const toUidDirect = getUidByRoleName(platform, toname);
        const toid = toUidDirect;
        const sendUidDirect = getUidByRoleName(platform, sendname);
        const item = {
            id: generateId(),
            type: "小群",
            subtype,
            sendname,
            sendid,
            toname,
            toid,
            gid: sendUidDirect ? a_private_group[platform][sendUidDirect]?.[1] : null,
            day,
            time,
            place,
            ...(title ? { title } : {})
        };

        const participants = [sendname, toname];
        const gid = await finalizeGroupCreation(platform, ctx, msg, item, participants);
        if (gid === false) return { success: false };
        names.forEach(n => recordInteractionStat(platform, sendname, n, "appt"));
        return { success: true, isMulti, names, gid };
    }
}

// ========================
// 💰 写信币消费辅助函数
// ========================

/**
 * 检查写信系统是否启用
 */
function isLetterSystemEnabled() {
    const letterExt = seal.ext.find("changri");
    if (!letterExt) return false;
    const config = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    return config.enable_direct_letter === true;
}

/**
 * 检查和消费写信币
 * @returns {success: bool, errorMsg?: string}
 */
function checkAndCostLetterCoin(ctx, msg, costType) {
    const letterExt = seal.ext.find("changri");
    if (!letterExt) return { success: false, errorMsg: "❌ 写信系统未找到" };

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");

    // 获取玩家角色名（新结构：uid为key，roleName在value[0]）
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const senderRoleName = a_private_group[platform]?.[uid]?.[0];

    if (!senderRoleName) {
        return { success: false, errorMsg: "✨ 请先使用「创建新角色」来认领你的身份。" };
    }

    // 获取消费成本
    let cost = 0;
    if (costType === "wish") {
        cost = parseInt(cachedGet("wish_coin_cost") || "0");
    } else if (costType === "appointment") {
        cost = parseInt(cachedGet("appointment_coin_cost") || "0");
    }

    if (cost <= 0) {
        return { success: true }; // 未启用消费
    }

    // 检查写信币余额（从背包 global_inventories 读取）
    const roleKey = `${platform}:${uid}`;
    const itemReg = JSON.parse(cachedGet("item_registry") || "{}");
    const coinEntry = Object.entries(itemReg).find(([, v]) => v.name === "写信币");
    if (!coinEntry) {
        return { success: false, errorMsg: "❌ 写信币尚未注册，请先启用写信综。" };
    }
    const [coinCode] = coinEntry;

    const invs = JSON.parse(cachedGet("global_inventories") || "{}");
    const inv = invs[roleKey] || [];
    const currentCoins = inv.filter(e => e.code === coinCode).reduce((sum, e) => sum + (e.count || 0), 0);

    if (currentCoins < cost) {
        return { success: false, errorMsg: `💰 写信币不足！需要 ${cost} 枚，现有 ${currentCoins} 枚。` };
    }

    // 消费写信币（从背包中扣除）
    let remaining = cost;
    for (const entry of inv) {
        if (entry.code === coinCode && remaining > 0) {
            const deduct = Math.min(entry.count || 0, remaining);
            entry.count -= deduct;
            remaining -= deduct;
        }
    }
    invs[roleKey] = inv.filter(e => e.count > 0 || e.code !== coinCode);
    cachedSet("global_inventories", JSON.stringify(invs));

    return { success: true, cost };
}

// ========================
// 📞 电话指令（直接确认版）
// ========================
let cmd_phone = {};

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
    // 检查写信系统是否启用
    if (isLetterSystemEnabled()) {
        seal.replyToSender(ctx, msg, "❌ 启用写信综模式后，电话功能已禁用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const pre = await checkAppointmentPreflight(ctx, msg, cmdArgs, "电话", "phone");
    if (!pre.valid) return seal.replyToSender(ctx, msg, pre.errorMsg), seal.ext.newCmdExecuteResult(true);
    const { platform, uid, sendname, day, time, names, isMulti, a_private_group, title } = pre.data;

    // 替换为直接确认函数
    const result = await directCreateAndFinalizeAppointment({
        ctx, msg, platform, sendname, sendid: uid,
        subtype: "电话", day, time, place: "电话",
        names, isMulti, title
    });

    if (result.success) {
        const successMsg = isMulti
            ? `✅ 你已成功向 ${names.join("、")} 发起多人电话，通讯频段已自动建立！\n💬 频段：${result.gid}`
            : `✅ 你已成功与 ${names[0]} 连线，通讯频段已自动建立！\n💬 频段：${result.gid}`;
        seal.replyToSender(ctx, msg, successMsg);
    }
    return seal.ext.newCmdExecuteResult(true);
};

function formatTime(date) {
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  return `${hours}:${minutes}`;
}

// ========================
// 🤫 私约指令（直接确认版）
// ========================

function getPrivateAliases() {
    try { return JSON.parse(cachedGet("private_appointment_aliases") || "[]"); } catch { return []; }
}

let cmd_appointment_private = {};

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

cmd_appointment_private.solve = async (ctx, msg, cmdArgs, aliasConfig) => {
    const subtype = aliasConfig?.trigger || "私密";
    const typeName = aliasConfig?.trigger || "私约";
    const minDurationOverride = aliasConfig?.minDuration;

    // 检查写信系统启用时是否需要消费写信币
    let coinCheck = { success: true, cost: 0 };
    if (isLetterSystemEnabled()) {
        coinCheck = checkAndCostLetterCoin(ctx, msg, "appointment");
        if (!coinCheck.success) {
            seal.replyToSender(ctx, msg, coinCheck.errorMsg);
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    const pre = await checkAppointmentPreflight(ctx, msg, cmdArgs, subtype, "private", minDurationOverride);
    if (!pre.valid) return seal.replyToSender(ctx, msg, pre.errorMsg), seal.ext.newCmdExecuteResult(true);

    if (pre.data.mergeTarget) {
        const newNames = [pre.data.sendname, ...pre.data.names];
        const success = mergeIntoExistingAppointment(ctx, msg, pre.data.mergeTarget, newNames, pre.data);
        if (success) {
            const successMsg = `✅ 你发起的${typeName}已自动合并到现有约会中！\n参与者：${pre.data.mergeTarget.partner}\n群号：${pre.data.mergeTarget.group}\n请自行申请入群~`;
            seal.replyToSender(ctx, msg, successMsg);
            return seal.ext.newCmdExecuteResult(true);
        } else {
            seal.replyToSender(ctx, msg, "❌ 自动合并失败，请稍后重试或联系管理员。");
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    const { platform, uid, sendname, day, time, names, isMulti, place, a_private_group } = pre.data;

    // 替换为直接确认函数
    const result = await directCreateAndFinalizeAppointment({
        ctx, msg, platform, sendname, sendid: uid,
        subtype, day, time, place,
        names, isMulti
    });

    if (result.success) {
        let successMsg = isMulti
            ? `✅ 你已成功与 ${names.join("、")} 开启多方${typeName}，私人空间已自动建立！\n💬 群号：${result.gid}`
            : `✅ 你已成功与 ${names[0]} 开启${typeName}，私人空间已自动建立！\n💬 群号：${result.gid}`;
        if (coinCheck.cost > 0) successMsg += `\n💰 已消耗写信币 ${coinCheck.cost} 枚`;
        seal.replyToSender(ctx, msg, successMsg);
    }
    return seal.ext.newCmdExecuteResult(true);
};

// ========================
// 💬 微信长期群聊功能
// ========================

// 🔧 检查两人之间是否已有活跃微信群
function checkWechatBetweenUsers(platform, user1, user2) {
    const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};

    for (const groupId in platformGroups) {
        const group = platformGroups[groupId];
        if (group.status === "active") {
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

let cmd_wechat = {};
cmd_wechat.solve =async (ctx, msg, cmdArgs) => {
    let config = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (config.enable_wechat === false) {
        seal.replyToSender(ctx, msg, "💬 微信功能已关闭");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    const sendname = getRoleName(ctx, msg);
    if (!sendname) {
        seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 新结构：feature_user_blocklist[uid]
    const wechatSendUid = getPrimaryUid(platform, uid);
    if (!isUserFeatureEnabled(wechatSendUid, "enable_wechat")) {
        seal.replyToSender(ctx, msg, "🚫 您已被禁止使用微信功能");
        return seal.ext.newCmdExecuteResult(true);
    }

    const toname = cmdArgs.getArgN(1);
    if (!toname) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    // 新结构：通过 roleName 反查 uid
    const wechatToUid = getUidByRoleName(platform, toname);
    if (!wechatToUid) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${toname}」，请确认对方已注册`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (toname === sendname) {
        seal.replyToSender(ctx, msg, "❌ 不能邀请自己");
        return seal.ext.newCmdExecuteResult(true);
    }

    const existing = checkWechatBetweenUsers(platform, sendname, toname);
    if (existing.exists) {
        seal.replyToSender(ctx, msg, `⚠️ 你和「${toname}」之间已存在活跃微信群：${existing.groupId}（主题：${existing.topic}）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const gid = await allocateGroup(platform, ctx, msg);
    if (!gid) {
        seal.replyToSender(ctx, msg, "⚠️ 暂无可用群号，请联系管理员添加备用群");
        return seal.ext.newCmdExecuteResult(true);
    }

    try {
        const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
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
        cachedSet("wechat_groups", JSON.stringify(wechatGroups));

        // 戏群公告
        const groupMsg = seal.newMessage();
        groupMsg.messageType = "group";
        groupMsg.groupId = `${platform}-Group:${gid}`;
        const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
        seal.replyToSender(groupCtx, groupMsg, `💬 微信群已建立\n\n👥 成员：${sendname}、${toname}\n\n💡 长期群聊，无时间限制，每个微信关系只能有一个活跃群。`);
        setGroupName(groupCtx, groupMsg, gid, `微信:${sendname}&${toname}`);

        // 通知对方（发起者已通过下方 successMsg 得到回执）
        const toUidLookup = getUidByRoleName(platform, toname);
        const toInfo = toUidLookup ? a_private_group[platform][toUidLookup] : null;
        if (toInfo) {
            const toBindGid = toInfo[1];
            const notifyMsg = seal.newMessage();
            notifyMsg.messageType = "group";
            notifyMsg.groupId = `${platform}-Group:${toBindGid}`;
            const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
            seal.replyToSender(notifyCtx, notifyMsg, `💬 ${sendname} 邀你加入微信群\n\n📱 群号：${gid}\n👥 成员：${sendname}、${toname}\n\n💡 长期群聊，无时间限制。`);
        }

        seal.replyToSender(ctx, msg, `✅ 微信群创建成功！\n📱 群号：${gid}\n👥 成员：${sendname}、${toname}`);
    } catch (e) {
        // 创建失败，释放已分配的群号
        const groupList = JSON.parse(cachedGet("group") || "[]");
        const idx = groupList.indexOf(gid + "_占用");
        if (idx !== -1) {
            groupList.splice(idx, 1);
            groupList.push(gid);
            cachedSet("group", JSON.stringify(groupList));
        }
        seal.replyToSender(ctx, msg, `❌ 微信群创建失败（群号已释放），请重试。错误：${e.message}`);
    }
    return seal.ext.newCmdExecuteResult(true);
};



let cmd_view_schedule = {};
cmd_view_schedule.solve =(ctx, msg) => {
    const platform = msg.platform, uid = msg.sender.userId, roleId = uid.replace(`${platform}:`, "");
    const storage = (k) => JSON.parse(cachedGet(k) || "{}");
    const schedule = storage("b_confirmedSchedule"), multiReq = storage("b_MultiGroupRequest");
    const privGroup = storage("a_private_group"), timers = storage("group_timers");
    
    // 新结构：uid为key，roleName在value[0]
    const myName = privGroup[platform]?.[roleId]?.[0] || null;
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
        const _aliasIconMap = {};
        getPrivateAliases().forEach(a => { if (a.trigger && a.icon) _aliasIconMap[a.trigger] = a.icon; });
        const icon = ({ "电话": "📞", "微信群": "💬", ..._aliasIconMap })[ev.subtype] || "🎭";
        let progressText = "";
        if (ev.group && !ev.isWechat) {
            // ended 用存档快照，进行中用实时计数
            const grpProg = ev.finalProgress || JSON.parse(cachedGet("group_write_progress") || "{}")[ev.group] || {};
            const privGrp = store.get("a_private_group")[platform] || {};
            const parts = [myName, ...ev.partner.split(/[、,，]/).map(s => s.trim()).filter(Boolean)]
                .filter((v, i, a) => a.indexOf(v) === i);
            const counts = parts.map(n => {
                const uid = Object.entries(privGrp).find(([_, v]) => v[0] === n)?.[0];
                return uid ? (grpProg[uid] || 0) : 0;
            });
            if (counts.some(c => c > 0)) progressText = `\n✍️ ${ev.status === "ended" ? "最终段数" : "当前进度"}：${counts.join('v')}`;
        }
        ev.displayText = `【${ev.day} ${ev.time}】\n${icon} ${ev.subtype} · ${tag}\n📍 地点：${ev.place || "未知"}\n👥 伙伴：${ev.partner}${progressText}`;
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
        const partnerName = ev.partner.split(/[、,]/)[0];
        const pUid = getUidByRoleName(platform, partnerName) || botUid;
        nodes.push({ type: "node", data: { name: ev.partner.split(/[、,]/)[0] || "助手", uin: pUid, content: ev.displayText } });
    });

    nodes.unshift({ type: "node", data: { name: "时间线档案", uin: botUid, content: `📅 共 ${events.length} 条日程，${wechat.length} 个群组` } });

    ws({ action: "send_group_forward_msg", params: { group_id: parseInt(msg.groupId.replace(/[^\d]/g, ""), 10), messages: nodes } }, ctx, msg, "");
};


// ========================
// 📥 手动加入请求指令
// ========================
let cmd_apply_join = {};
cmd_apply_join.solve =async (ctx, msg, cmdArgs) => {

    const enableJoin = cachedGet("enable_join_existing_appointment");
    if (enableJoin !== "true") {
        return seal.replyToSender(ctx, msg, "🚫 当前未启用「加入私约」功能。");
    }

    // 1. 获取参数
    const targetName = cmdArgs.getArgN(1);
    const rawTime = cmdArgs.getArgN(2);
    if (!targetName || !rawTime) {
        return seal.replyToSender(ctx, msg, "⚠️ 参数不足，正确格式：申请加入 角色名 时间点\n示例：申请加入 张三 14:30");
    }

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    if (!a_private_group[platform]) a_private_group[platform] = {};

    // 2. 获取发起人角色名
    const sendname = getRoleName(ctx, msg);
    if (!sendname) return seal.replyToSender(ctx, msg, "请先使用「创建新角色」绑定角色");

    // 3. 全局天数
    const globalDay = cachedGet("global_days");
    if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 当前尚未设置全局天数，请先使用 \".设置天数 D1\"");

    // 4. 验证目标角色是否存在
    const targetUid = getUidByRoleName(platform, targetName);
    if (!targetUid) {
        return seal.replyToSender(ctx, msg, `❌ 角色「${targetName}」未注册，无法发起加入请求。`);
    }
    const targetInfo = a_private_group[platform][targetUid];
    const targetGroupId = targetInfo?.[1];  // 用于通知的个人群

    // 5. 解析时间点（支持 HH:MM 或 HHMM）
    let pointTime = rawTime;
    if (/^\d{4}$/.test(rawTime)) {
        pointTime = `${rawTime.slice(0, 2)}:${rawTime.slice(2, 4)}`;
    } else if (!/^\d{2}:\d{2}$/.test(rawTime)) {
        return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用 HH:MM 或 HHMM（如 14:30 或 1430）");
    }

    // 6. 获取目标角色的已确认日程
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
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
    // 多人小群情况：partner 为"多人小群"，需从 group_expire_info 检查
    if (matchingSchedule.partner === "多人小群" && matchingSchedule.group) {
        const gei = JSON.parse(cachedGet("group_expire_info") || "{}");
        const existingParticipants = gei[matchingSchedule.group]?.participants || [];
        if (existingParticipants.includes(sendname)) {
            return seal.replyToSender(ctx, msg, `⚠️ 你已经在该约会中，无需重复加入。`);
        }
    }

    // 9. 检查发起人自身在该时段是否有冲突（复用冲突检测）
    const fromKey = `${platform}:${uid}`;
    const fromSchedules = b_confirmedSchedule[fromKey] || [];
    const hasConflict = fromSchedules.some(s => timeConflict(globalDay, matchingSchedule.time, s.day, s.time));
    if (hasConflict) {
        return seal.replyToSender(ctx, msg, `⚠️ 你在 ${globalDay} ${matchingSchedule.time} 已有其他安排，无法加入该预约。`);
    }

    // 10. 检查锁定时间冲突（复用锁定检查）
    let a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
    const fromLocked = a_lockedSlots[fromKey]?.[globalDay] || [];
    if (fromLocked.some(lockedTime => timeOverlap(matchingSchedule.time, lockedTime))) {
        return seal.replyToSender(ctx, msg, `⚠️ 你在 ${globalDay} ${matchingSchedule.time} 时段被锁定，无法加入。`);
    }

    // 11. 检查是否已有待处理的加入请求（避免重复）
    let joinRequests = JSON.parse(cachedGet("join_request_list") || "[]");
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
    cachedSet("join_request_list", JSON.stringify(joinRequests));

    // 13. 通知目标角色（发送到其个人群）
    if (targetGroupId) {
        const notifyMsg = seal.newMessage();
        notifyMsg.messageType = "group";
        notifyMsg.groupId = `${platform}-Group:${targetGroupId}`;
        const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
        const notice = `📢 加入请求\n\n${sendname} 想加入你正在进行的预约：\n📅 ${globalDay} ${matchingSchedule.time}\n📍 ${matchingSchedule.place || "电话"}\n\n请使用「加入请求」查看详情，然后输入「同意加入 编号」或「拒绝加入 编号」。`;
        seal.replyToSender(notifyCtx, notifyMsg, notice);
    }

    // 14. 回复发起人
    seal.replyToSender(ctx, msg, `✨ 已向「${targetName}」发送加入请求，请等待对方回应。`);
    return seal.ext.newCmdExecuteResult(true);
};


// ========================
// 辅助函数（若尚未定义）
// ========================
function timeToMinutes(timeStr) {
    const [h, m] = timeStr.split(':').map(Number);
    return h * 60 + m;
}

let cmd_join_requests = {};
cmd_join_requests.solve =(ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const pureUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const joinRequests = JSON.parse(cachedGet("join_request_list") || "[]");
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

let cmd_accept_join = {};
cmd_accept_join.solve =(ctx, msg, cmdArgs) => {

    const enableJoin = cachedGet("enable_join_existing_appointment");
    if (enableJoin !== "true") {
        return seal.replyToSender(ctx, msg, "🚫 当前未启用「加入私约」功能。");
    }

    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    const platform = msg.platform;
    const pureUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));

    let joinRequests = JSON.parse(cachedGet("join_request_list") || "[]");
    const myPending = joinRequests.filter(req => req.toUid === pureUid && req.status === "pending");
    if (isNaN(idx) || idx < 0 || idx >= myPending.length) {
        return seal.replyToSender(ctx, msg, "❌ 无效的编号，请使用「加入请求」查看。");
    }
    const request = myPending[idx];
    const fullRequest = joinRequests.find(r => r.id === request.id);
    if (!fullRequest) return seal.replyToSender(ctx, msg, "❌ 请求不存在或已过期。");
    
    // 请求已处理，直接移除
    const acceptIdx = joinRequests.indexOf(fullRequest);
    if (acceptIdx !== -1) joinRequests.splice(acceptIdx, 1);
    cachedSet("join_request_list", JSON.stringify(joinRequests));
    
    // 获取发起人信息（新结构：通过 roleName 反查 uid）
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const fromUid = getUidByRoleName(platform, fullRequest.from);
    if (!fromUid) {
        seal.replyToSender(ctx, msg, `⚠️ 无法找到发起人「${fullRequest.from}」的信息。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetGroupId = fullRequest.targetGroupId;
    
    // 更新日程
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
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
    cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

    // 同步更新 group_expire_info 参与者列表
    let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    if (groupExpireInfo[groupId]) {
        const existingParts = groupExpireInfo[groupId].participants || [];
        if (!existingParts.includes(fullRequest.from)) {
            groupExpireInfo[groupId].participants = [...existingParts, fullRequest.from];
        }
        cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));
    }

    // 同步更新计时器
    let groupTimers = JSON.parse(cachedGet("group_timers") || "{}");
    const timerEntry = groupTimers[groupId];
    if (timerEntry) {
        const now = Date.now();
        // 若原来是两人轮替模式，加入第三人后切换为独立计时
        if (timerEntry.timerMode === "turn_taking" && timerEntry.participants.length === 2) {
            timerEntry.timerMode = "independent";
            for (const status of Object.values(timerEntry.timerStatus)) {
                if (status.status === "waiting") {
                    status.status = "timing";
                    status.startTime = now;
                    status.repliedTime = null;
                    status.wordCount = 0;
                    status.remindedTimes = 0;
                }
            }
        }
        if (!timerEntry.participants.includes(fullRequest.from)) {
            timerEntry.participants.push(fullRequest.from);
        }
        if (!timerEntry.timerStatus[fullRequest.from]) {
            timerEntry.timerStatus[fullRequest.from] = {
                status: "timing",
                startTime: now,
                repliedTime: null,
                wordCount: 0,
                remindedTimes: 0,
                isInitiator: false
            };
        }
        groupTimers[groupId] = timerEntry;
        cachedSet("group_timers", JSON.stringify(groupTimers));
    }

    // 更新群名（加人后重新计算参与者数量）
    const updatedParticipants = groupExpireInfo[groupId]?.participants || [];
    if (updatedParticipants.length > 0) {
        const nameTag = updatedParticipants.length > 2 ? "多人" : updatedParticipants.join("、");
        const newGroupName = `${targetSchedule.subtype || "私密"} ${day} ${time} ${targetSchedule.place ? targetSchedule.place + " " : ""}${nameTag}`;
        const renameMsg = seal.newMessage();
        renameMsg.messageType = "group";
        renameMsg.groupId = `${platform}-Group:${targetGroupId}`;
        const renameCtx = seal.createTempCtx(ctx.endPoint, renameMsg);
        setGroupName(renameCtx, renameMsg, targetGroupId, newGroupName);
    }

    // 在约会群内发送通知
    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${targetGroupId}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
    seal.replyToSender(groupCtx, groupMsg, `✨ ${fullRequest.from} 已经到来，正在加入你们的约会。`);

    // 通知申请人（发送群号）
    const fromInfo = a_private_group[platform][fromUid];
    const fromGroupId = fromInfo?.[1];
    if (fromGroupId) {
        const fromMsg = seal.newMessage();
        fromMsg.messageType = "group";
        fromMsg.groupId = `${platform}-Group:${fromGroupId}`;
        const fromCtx = seal.createTempCtx(ctx.endPoint, fromMsg);
        seal.replyToSender(fromCtx, fromMsg, `✅ 你已成功加入 ${fullRequest.to} 的私约，群号：${targetGroupId}\n请自行申请入群。`);
    }

    seal.replyToSender(ctx, msg, `✅ 已同意 ${fullRequest.from} 加入你的私约。`);
    return seal.ext.newCmdExecuteResult(true);
};

let cmd_reject_join = {};
cmd_reject_join.solve =(ctx, msg, cmdArgs) => {
    const idx = parseInt(cmdArgs.getArgN(1)) - 1;
    const platform = msg.platform;
    const pureUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));

    let joinRequests = JSON.parse(cachedGet("join_request_list") || "[]");
    const myPending = joinRequests.filter(req => req.toUid === pureUid && req.status === "pending");
    if (isNaN(idx) || idx < 0 || idx >= myPending.length) {
        return seal.replyToSender(ctx, msg, "❌ 无效的编号，请使用「加入请求」查看。");
    }
    const request = myPending[idx];
    const fullRequest = joinRequests.find(r => r.id === request.id);
    if (!fullRequest) return seal.replyToSender(ctx, msg, "❌ 请求不存在或已过期。");
    
    // 请求已处理，直接移除
    const rejectIdx = joinRequests.indexOf(fullRequest);
    if (rejectIdx !== -1) joinRequests.splice(rejectIdx, 1);
    cachedSet("join_request_list", JSON.stringify(joinRequests));
    
    // 通知发起人
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const fromUid = getUidByRoleName(platform, fullRequest.from);
    const fromInfo = fromUid ? a_private_group[platform]?.[fromUid] : null;
    if (fromInfo) {
        const fromGroupId = fromInfo[1];
        if (fromGroupId) {
            const fromMsg = seal.newMessage();
            fromMsg.messageType = "group";
            fromMsg.groupId = `${platform}-Group:${fromGroupId}`;
            const fromCtx = seal.createTempCtx(ctx.endPoint, fromMsg);
            seal.replyToSender(fromCtx, fromMsg, `❌ ${fullRequest.to} 拒绝了你的加入请求。`);
        }
    }

    seal.replyToSender(ctx, msg, `✅ 已拒绝 ${fullRequest.from} 的加入请求。`);
    return seal.ext.newCmdExecuteResult(true);
};

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
    const currentRanges  = JSON.parse(cachedGet("allowed_appointment_times") || "[]");
    const blockedByDay   = JSON.parse(cachedGet("ts_blocked_by_day")   || "{}");
    const allowedDurs    = JSON.parse(cachedGet("ts_allowed_durations") || "[]");
    const currentDay     = cachedGet("global_days") || "";

    const lines = ["📋 邀约时间限制"];

    // 1. 功能时间窗口（allowed_appointment_times）
    lines.push("\n【可约时间段】");
    if (currentRanges.length === 0) {
      lines.push("· 不限（任何时间）");
    } else {
      currentRanges.forEach(r => lines.push(`· ${r}`));
    }

    // 2. 禁约时段（ts_blocked_by_day，当前天 + 全览）
    lines.push("\n【禁约时段（按游戏日）】");
    const dayKeys = Object.keys(blockedByDay);
    if (dayKeys.length === 0) {
      lines.push("· 无");
    } else {
      dayKeys.sort().forEach(d => {
        const hours = blockedByDay[d];
        if (!hours || hours.length === 0) return;
        const tag = d === currentDay ? `${d}（当前）` : d;
        lines.push(`· ${tag}：${hours.map(h => `${String(h).padStart(2,"0")}:00`).join("、")}`);
      });
    }

    // 3. 允许弧长（ts_allowed_durations）
    lines.push("\n【允许弧长】");
    if (allowedDurs.length === 0) {
      lines.push("· 不限");
    } else {
      lines.push(`· ${allowedDurs.map(h => `${h}h`).join("、")}`);
    }

    seal.replyToSender(ctx, msg, lines.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 保存设置
  cachedSet("allowed_appointment_times", JSON.stringify(timeRanges));
  seal.replyToSender(ctx, msg, `✅ 已设置允许的邀约时间段：\n${timeRanges.map(range => `· ${range}`).join('\n')}`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置邀约时间"] = cmd_set_allowed_times;

// 🔧 新增：清空允许时间范围的指令
let cmd_clear_allowed_times = seal.ext.newCmdItemInfo();
cmd_clear_allowed_times.name = "清空邀约时间";
cmd_clear_allowed_times.help = "。清空邀约时间 - 清空所有时间限制";
cmd_clear_allowed_times.solve = (ctx, msg, cmdArgs) => {
  cachedSet("allowed_appointment_times", JSON.stringify([]));
  seal.replyToSender(ctx, msg, "✅ 已清空邀约时间限制，现在任何时间都允许发起邀约");
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空邀约时间"] = cmd_clear_allowed_times;


// ========================
// 🏠 群组生命周期管理
// ========================

// 添加群号
let cmd_add_group = seal.ext.newCmdItemInfo();
cmd_add_group.name = "添加群号";
cmd_add_group.help = "。添加群号 群号（多个用逗号隔开）";
cmd_add_group.solve = (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    let grouplist = cmdArgs.getArgN(1);
    if (!grouplist) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    grouplist = grouplist.replace(/，/g, ",").split(",");
    let group = JSON.parse(cachedGet("group") || "[]");
    for (let i = 0; i < grouplist.length; i++) {
        if (/^[0-9]+$/.test(grouplist[i]) && !group.includes(grouplist[i])) {
            group.push(grouplist[i]);
        }
    }
    cachedSet("group", JSON.stringify(group));
    seal.replyToSender(ctx, msg, `✅ 已添加群号，当前可用共 ${group.length} 个。`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["添加群号"] = cmd_add_group;

// 移除群号
let cmd_remove_group = seal.ext.newCmdItemInfo();
cmd_remove_group.name = "移除群号";
cmd_remove_group.help = "。移除群号 群号（多个用逗号隔开）";
cmd_remove_group.solve = (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    let grouplist = cmdArgs.getArgN(1);
    if (!grouplist) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    grouplist = grouplist.replace(/，/g, ",").split(",");
    let group = JSON.parse(cachedGet("group") || "[]");
    for (let i = 0; i < grouplist.length; i++) {
        let idx = group.indexOf(grouplist[i]);
        if (idx !== -1) group.splice(idx, 1);
    }
    cachedSet("group", JSON.stringify(group));
    seal.replyToSender(ctx, msg, `✅ 指定群号已移除，当前可用共 ${group.length} 个。`);
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["移除群号"] = cmd_remove_group;

// 查看群号
let cmd_show_group = seal.ext.newCmdItemInfo();
cmd_show_group.name = "查看群号";
cmd_show_group.help = "。查看群号";
cmd_show_group.solve = (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    let group = JSON.parse(cachedGet("group") || "[]");
    let rep = `📜 当前可用群号（共 ${group.length} 个）：\n`;
    for (let i = 0; i < group.length; i++) {
        const isOccupied = group[i].endsWith("_占用");
        rep += `• ${isOccupied ? group[i].replace(/_占用$/, "") + " 🔴占用中" : group[i]}\n`;
    }
    seal.replyToSender(ctx, msg, rep.trim());
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["查看群号"] = cmd_show_group;

// 开启群号组（从 rp_archive 拉取组内 QQ 号批量注入）
let cmd_open_group_set = seal.ext.newCmdItemInfo();
cmd_open_group_set.name = "开启群号组";
cmd_open_group_set.help = "。开启群号组 组名\n从 rp_archive 后台读取该组所有群号，批量加入可用池";
cmd_open_group_set.solve = async (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const setName = cmdArgs.getArgN(1);
    if (!setName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) {
        seal.replyToSender(ctx, msg, `❌ 未配置 RP 存档服务器地址。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    try {
        const resp = await fetch(`${base}/api/group_set/${encodeURIComponent(setName)}`, {
            headers: { "X-Archive-Token": token }
        });
        if (!resp.ok) {
            seal.replyToSender(ctx, msg, `❌ 服务器返回 ${resp.status}，请检查组名是否正确。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        const data = await resp.json();
        if (!data.ok || !data.group_ids || data.group_ids.length === 0) {
            seal.replyToSender(ctx, msg, `⚠️ 群号组「${setName}」在后台不存在或暂无群号。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        let group = JSON.parse(cachedGet("group") || "[]");
        let added = 0;
        for (const gid of data.group_ids) {
            if (!group.includes(gid) && !group.includes(gid + "_占用")) {
                group.push(gid);
                added++;
            }
        }
        cachedSet("group", JSON.stringify(group));
        seal.replyToSender(ctx, msg, `✅ 群号组「${setName}」已开启，新注入 ${added} 个群号（共 ${data.group_ids.length} 个），当前可用池共 ${group.length} 个。`);
    } catch (e) {
        seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
    }
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["开启群号组"] = cmd_open_group_set;

// 关闭群号组（从 rp_archive 拉取组内 QQ 号批量移除，占用中的无法移除）
let cmd_close_group_set = seal.ext.newCmdItemInfo();
cmd_close_group_set.name = "关闭群号组";
cmd_close_group_set.help = "。关闭群号组 组名\n将该组所有群号从可用池移除（占用中的群无法移除）";
cmd_close_group_set.solve = async (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const setName = cmdArgs.getArgN(1);
    if (!setName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) {
        seal.replyToSender(ctx, msg, `❌ 未配置 RP 存档服务器地址。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    try {
        const resp = await fetch(`${base}/api/group_set/${encodeURIComponent(setName)}`, {
            headers: { "X-Archive-Token": token }
        });
        if (!resp.ok) {
            seal.replyToSender(ctx, msg, `❌ 服务器返回 ${resp.status}，请检查组名是否正确。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        const data = await resp.json();
        if (!data.ok || !data.group_ids || data.group_ids.length === 0) {
            seal.replyToSender(ctx, msg, `⚠️ 群号组「${setName}」在后台不存在或暂无群号。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        let group = JSON.parse(cachedGet("group") || "[]");
        let removed = 0, skipped = [];
        for (const gid of data.group_ids) {
            if (group.includes(gid + "_占用")) {
                skipped.push(gid);
            } else {
                const idx = group.indexOf(gid);
                if (idx !== -1) { group.splice(idx, 1); removed++; }
            }
        }
        cachedSet("group", JSON.stringify(group));
        let rep = `✅ 群号组「${setName}」已关闭，移除 ${removed} 个群号，当前可用池剩 ${group.length} 个。`;
        if (skipped.length > 0) rep += `\n⚠️ 以下群正在占用中，无法移除：\n${skipped.map(g => `• ${g}`).join("\n")}`;
        seal.replyToSender(ctx, msg, rep);
    } catch (e) {
        seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
    }
    return seal.ext.newCmdExecuteResult(true);
}
ext.cmdMap["关闭群号组"] = cmd_close_group_set;

// 驱逐指定QQ
let cmd_kick_qq = seal.ext.newCmdItemInfo();
cmd_kick_qq.name = "驱逐";
cmd_kick_qq.help = "使用方法：。驱逐 QQ号\n从群号池所有群中踢出指定QQ";
cmd_kick_qq.solve = async (ctx, msg, cmdArgs) => {
    if (!msg.isMaster && !isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `此指令仅限骰主或管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetQQ = cmdArgs.getArgN(1);
    if (!targetQQ || !/^\d+$/.test(targetQQ)) {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    const platform = msg.platform;
    const extras = JSON.parse(cachedGet("extra_accounts") || "{}");
    // 找到主账号（若 targetQQ 本身是额外账号则找到其主账号）
    const primaryUid = extras[`${platform}:${targetQQ}`] || targetQQ;
    // 收集主账号 + 所有额外账号
    const extraQQs = Object.entries(extras)
        .filter(([k, v]) => k.startsWith(`${platform}:`) && v === primaryUid)
        .map(([k]) => k.replace(`${platform}:`, ""));
    const allTargetQQs = [...new Set([primaryUid, ...extraQQs])];

    const groups = JSON.parse(cachedGet("group") || "[]")
        .map(g => g.replace(/_占用$/, ""));

    if (groups.length === 0) {
        seal.replyToSender(ctx, msg, `❌ 群号池为空，无群可操作。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const extraTip = allTargetQQs.length > 1 ? `（含额外账号：${allTargetQQs.filter(q => q !== primaryUid).join("、")}）` : "";
    seal.replyToSender(ctx, msg, `🔍 正在从 ${groups.length} 个群中搜索并踢出 ${targetQQ}${extraTip}...`);

    let countKick = 0;
    let countNotIn = 0;

    for (const gid of groups) {
        const members = await getGroupMembersSilent(gid, ctx, msg);
        const memberIds = members.map(m => m.user_id.toString());
        for (const tqq of allTargetQQs) {
            if (memberIds.includes(tqq)) {
                ws({
                    action: "set_group_kick",
                    params: {
                        group_id: parseInt(gid),
                        user_id: parseInt(tqq)
                    }
                }, ctx, msg, null);
                countKick++;
            } else {
                countNotIn++;
            }
        }
    }

    const result = countKick > 0
        ? `✅ 已向 ${countKick} 个群/账号发出踢出指令（不在其中: ${countNotIn} 次）。`
        : `ℹ️ 该QQ及其额外账号不在群号池的任何群中。`;
    seal.replyToSender(ctx, msg, result);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["驱逐"] = cmd_kick_qq;


let cmd_admin_view_active = {};
cmd_admin_view_active.solve =(ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  let dayArg = cmdArgs.getArgN(1);
  if (!dayArg || !/^D\d+$/.test(dayArg)) {
    dayArg = cachedGet("global_days") || "D0";
  }

  const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");

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


// ========================
// 查看所有活跃微信群（管理员）
// ========================

let cmd_view_wechat_groups = seal.ext.newCmdItemInfo();
cmd_view_wechat_groups.name = "查看微信群";
cmd_view_wechat_groups.help = "。查看微信群 —— 列出所有当前活跃的微信群（管理员专用）";

cmd_view_wechat_groups.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
    const platformGroups = wechatGroups[platform] || {};

    const active = Object.values(platformGroups).filter(g => g.status === "active");

    if (active.length === 0) {
        seal.replyToSender(ctx, msg, "📭 当前没有活跃的微信群");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 同时检查群池，标出群号是否正确处于占用状态
    const groupList = JSON.parse(cachedGet("group") || "[]");

    let reply = `💬 当前活跃微信群（共 ${active.length} 个）：\n\n`;
    active.sort((a, b) => (a.created_timestamp || 0) - (b.created_timestamp || 0));
    active.forEach((g, idx) => {
        const inPool = groupList.includes(g.id + "_占用");
        const warn = inPool ? "" : " ⚠️[群池异常]";
        reply += `${idx + 1}. 群号：${g.id}${warn}\n`;
        reply += `   👥 ${g.participants.join("、")}\n`;
        reply += `   📅 创建：${g.created_at}\n`;
        if (g.topic) reply += `   📌 主题：${g.topic}\n`;
        reply += "\n";
    });

    seal.replyToSender(ctx, msg, reply.trim());
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["查看微信群"] = cmd_view_wechat_groups;

let cmd_grouplist_release = {};

/**
 * 结束微信群（仅清理状态，不发公告）
 */
function endWechatGroup(ctx, msg, gid, platform, uid) {
    const groupList = JSON.parse(cachedGet("group") || "[]");
    const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
    const groupInfo = wechatGroups[platform]?.[gid];
    if (!groupInfo) {
        seal.replyToSender(ctx, msg, "⚠️ 当前群不是微信群，无法结束");
        return false;
    }

    // 获取操作者角色名（仅用于记录）
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const userRole = a_private_group[platform]?.[uid]?.[0] || "管理员";

    // 更新群状态
    groupInfo.status = "ended";
    groupInfo.ended_at = new Date().toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" });
    groupInfo.ended_by = userRole;
    wechatGroups[platform][gid] = groupInfo;
    cachedSet("wechat_groups", JSON.stringify(wechatGroups));

    // 释放群号
    const groupIndex = groupList.indexOf(gid + "_占用");
    if (groupIndex !== -1) {
        groupList.splice(groupIndex, 1);
        groupList.push(gid);
        cachedSet("group", JSON.stringify(groupList));
    }

    // 【新增：微信群也重置计数】
        let progress = JSON.parse(cachedGet("group_write_progress") || "{}");
        if (progress[gid]) {
            delete progress[gid];
            cachedSet("group_write_progress", JSON.stringify(progress));
        }

    // 修改群名为"备用"
    setGroupName(ctx, msg, gid, getIdleGroupName());

    // 仅向操作者反馈
    seal.replyToSender(ctx, msg, `✅ 微信群 ${gid} 已结束，群号已释放。`);
    return true;
}

cmd_grouplist_release.solve = (ctx, msg, cmdArgs) => {
    let group = JSON.parse(cachedGet("group") || "[]");
    let platform = msg.platform;
    let gid = msg.groupId.replace(`${platform}-Group:`, "");
    const uid = msg.sender.userId.replace(`${platform}:`, "");

    // 判断是否为微信群（通过 wechat_groups 数据判断，而非后缀）
    const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
    if (wechatGroups[platform]?.[gid]?.status === "active") {
        endWechatGroup(ctx, msg, gid, platform, uid);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 非微信群：原有结束逻辑
    const fullId = `${gid}_占用`;
    if (group.includes(fullId)) {
        // ----- 结束逻辑 -----
        // 将占用状态移除，使该群可复用
        group.splice(group.indexOf(fullId), 1);
        group.push(gid);
        cachedSet("group", JSON.stringify(group));

        // 更新 b_confirmedSchedule 中所有 status 为 ended，并快照 V 数
        let progress = JSON.parse(cachedGet("group_write_progress") || "{}");
        const finalProgress = progress[gid] ? { ...progress[gid] } : null;

        let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
        let modified = false;
        let matchCount = 0;
        for (let uidKey in b_confirmedSchedule) {
            for (let ev of b_confirmedSchedule[uidKey]) {
                if (ev.group === gid && ev.status !== "ended") {
                    ev.status = "ended";
                    if (finalProgress) ev.finalProgress = finalProgress;
                    modified = true;
                    matchCount++;
                }
            }
        }
        if (modified) {
            cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
        }

        // 重置该群的写帖进度计数
        if (progress[gid]) {
            delete progress[gid];
            cachedSet("group_write_progress", JSON.stringify(progress));
        }

        // 存档必须在清除 group_expire_info 之前，否则拿不到 day/time/place
        if (isArchiveEnabled() && getSeasonMode() !== "no_review") {
            postToArchive("/api/session_end", buildSessionArchive(gid, platform, false));
        }

        // 清除到期记录
        let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
        if (groupExpireInfo[gid]) {
            delete groupExpireInfo[gid];
            cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));
            console.log(`[DEBUG] 已清除群组 ${gid} 的到期记录`);
        }

        console.log(`[DEBUG] ${gid} 标记为 ended，更新 ${matchCount} 条记录`);
        seal.replyToSender(ctx, msg, `✅ 本群（${gid}）本轮小群已结束，可再次发起新小群，所有相关记录已标记"已结束"`);
        setGroupName(ctx, msg, ctx.group.groupId, getIdleGroupName());
        cleanupGroupTimer(gid);
        applyEndGameBonuses(ctx, msg, gid, platform);
    } else {
        seal.replyToSender(ctx, msg, `⚠️ 当前群号未处于占用状态，无法结束`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

// 管理员强结指令：执行所有清理但不发放任何结戏奖励
// 用法：强结私约 [群号]  —— 不填群号则对当前群操作
const cmd_force_end = seal.ext.newCmdItemInfo();
cmd_force_end.name = "强结私约";
cmd_force_end.help = "。强结私约 [群号]（管理员专用）：强制结束指定群（不填则当前群），跳过复盘检查，不发放结戏奖励，并在目标群 @ 成员提示退群。";
cmd_force_end.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const argGid = (cmdArgs.getArgN(1) || "").trim();
    const gid = argGid || msg.groupId.replace(`${platform}-Group:`, "");
    const isRemote = !!argGid; // 是否在外部群操作

    // 构造目标群的 msg/ctx，用于在目标群发消息和改群名
    const targetMsg = seal.newMessage();
    targetMsg.messageType = "group";
    targetMsg.groupId = `${platform}-Group:${gid}`;
    const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);

    let group = JSON.parse(cachedGet("group") || "[]");

    // 微信群：复用原有清理函数
    const wechatGroups = JSON.parse(cachedGet("wechat_groups") || "{}");
    if (wechatGroups[platform]?.[gid]?.status === "active") {
        endWechatGroup(targetCtx, targetMsg, gid, platform, msg.sender.userId.replace(`${platform}:`, ""));
        if (isRemote) seal.replyToSender(ctx, msg, `✅ 已强结微信群 ${gid}。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const fullId = `${gid}_占用`;
    if (!group.includes(fullId)) {
        seal.replyToSender(ctx, msg, `⚠️ 群号 ${gid} 未处于占用状态，无法结束`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 释放群号
    group.splice(group.indexOf(fullId), 1);
    group.push(gid);
    cachedSet("group", JSON.stringify(group));

    // 重置写帖进度
    let progress = JSON.parse(cachedGet("group_write_progress") || "{}");
    if (progress[gid]) {
        delete progress[gid];
        cachedSet("group_write_progress", JSON.stringify(progress));
    }

    // 更新 b_confirmedSchedule，同时收集参与者 uid
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    let modified = false;
    const participantUids = new Set();
    for (let uidKey in b_confirmedSchedule) {
        for (let ev of b_confirmedSchedule[uidKey]) {
            if (ev.group === gid && ev.status !== "ended") {
                ev.status = "ended";
                modified = true;
                participantUids.add(uidKey);
            }
        }
    }
    if (modified) cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

    // 若 b_confirmedSchedule 没有记录，也尝试从 a_private_group 收集（gid 匹配者）
    if (participantUids.size === 0) {
        Object.entries(a_private_group[platform] || {}).forEach(([uid, data]) => {
            if (data[1] === gid) participantUids.add(uid);
        });
    }

    // 存档必须在清除 group_expire_info 之前，否则拿不到 day/time/place
    if (isArchiveEnabled() && getSeasonMode() !== "no_review") {
        postToArchive("/api/session_end", buildSessionArchive(gid, platform, true));
    }

    // 清除到期记录
    let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    if (groupExpireInfo[gid]) {
        delete groupExpireInfo[gid];
        cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));
    }

    cleanupGroupTimer(gid);
    accumulateToSeasonStats(platform, gid);
    const sessionStats = getSessionStats();
    if (sessionStats[gid]) {
        delete sessionStats[gid];
        saveSessionStats(sessionStats);
    }

    // 在目标群发送提示，@ 所有参与者请其退群
    const atParts = [...participantUids].map(uid => `[CQ:at,qq=${uid}]`).join(" ");
    const targetNotice = atParts
        ? `${atParts}\n⚠️ 本群已被管理员强制结束，不发放结戏奖励，请各位退群。`
        : `⚠️ 本群已被管理员强制结束，不发放结戏奖励，请各位退群。`;
    seal.replyToSender(targetCtx, targetMsg, targetNotice);
    setGroupName(targetCtx, targetMsg, gid, getIdleGroupName());

    // 向发令者确认（在外部群操作时才需要额外回复，在目标群操作时目标群已有消息）
    if (isRemote) {
        seal.replyToSender(ctx, msg, `✅ 群 ${gid} 已强制结束，已在目标群通知成员退群。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["强结私约"] = cmd_force_end;

function cleanupConflictsAndNotify(platform, toid, toname, day, time, ctx, msg) {
    const myId = `${platform}:${toid}`;
    const allAppointments = JSON.parse(cachedGet("appointmentList") || "[]");
    const a_MultiGroupRequest = JSON.parse(cachedGet("b_MultiGroupRequest") || "{}");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
  
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
  
    cachedSet("appointmentList", JSON.stringify(updatedAppointments));
    cachedSet("b_MultiGroupRequest", JSON.stringify(a_MultiGroupRequest));
  
    console.log(`[清理冲突] 正在处理 ${toname} 接受 ${day} ${time}，共移除 ${removedCount} 点对点，标记拒绝 ${notifyRefused.length} 多人请求`);
  
    // 🔔 通知逻辑：改为使用 WebSocket 发送
    for (let n of notifyRefused) {
      const nUid = getUidByRoleName(platform, n.toname);
      const targetGroupIdRaw = nUid ? a_private_group[platform]?.[nUid]?.[1] : null;
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
    const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
    
    // --- 1. 读取 noquit 存储 ---
    // 结构预期: { "12345": ["10001", "10002"], "789012": ["10001"] }
    const noquitRecord = JSON.parse(cachedGet("noquit") || "{}");
    let needSave = false;

    // 构建 QQ -> 角色信息的映射
    const qqToRole = {};
    for (let [uid, info] of Object.entries(platformRoles)) {
        const roleName = info[0];
        if (roleName) qqToRole[uid] = { uid, name: roleName, isNPC: npcList.includes(roleName) };
    }

    let hasNonNPC = false;
    for (let member of members) {
        const qq = member.user_id.toString();
        const role = qqToRole[qq];

        if (role && !role.isNPC) {
            hasNonNPC = true;
            const groupId = platformRoles[role.uid]?.[1];
            if (groupId) {
                // 初始化记录
                if (!noquitRecord[qq]) noquitRecord[qq] = [];

                // 新增群号
                if (!noquitRecord[qq].includes(gid)) {
                    noquitRecord[qq].push(gid);
                    needSave = true;
                    console.log(`[NoQuit] 记录玩家 ${qq} 在群 ${gid} 未退出 (累计群数: ${noquitRecord[qq].length})`);
                }

                const count = noquitRecord[qq].length;

                const remindMsg = seal.newMessage();
                remindMsg.messageType = "group";
                remindMsg.groupId = `${platform}-Group:${groupId}`;
                const remindCtx = seal.createTempCtx(ctx.endPoint, remindMsg);
                seal.replyToSender(remindCtx, remindMsg,
                    `[CQ:at,qq=${qq}] ⚠️ 系统检测到群 ${gid} 将用于私密邀约/心愿等自动建群，请尽快退出，否则可能影响后续流程。（累计未退：${count}）`);
            }
        }
    }
    
    // --- 3. 如果有变动，写入存储 ---
    if (needSave) {
        cachedSet("noquit", JSON.stringify(noquitRecord));
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
    let groupList = JSON.parse(cachedGet("group") || "[]");
    let freeGroups = groupList.filter(g => !g.endsWith("_占用"));
    if (freeGroups.length === 0) return null;

    // 随机打乱顺序
    for (let i = freeGroups.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [freeGroups[i], freeGroups[j]] = [freeGroups[j], freeGroups[i]];
    }

    for (let gid of freeGroups) {
        // 先抢占（重新读取防止并发后已被占用），再检查群内成员
        const gl = JSON.parse(cachedGet("group") || "[]");
        if (!gl.includes(gid)) continue; // 已被其他并发调用占走
        cachedSet("group", JSON.stringify(gl.map(g => g === gid ? gid + "_占用" : g)));

        const hasNonNPC = await checkGroupHasNonNPC(platform, gid, ctx, msg);
        if (!hasNonNPC) {
            return gid;
        }
        // 群内有非NPC玩家，释放占用后继续找下一个
        const gl2 = JSON.parse(cachedGet("group") || "[]");
        cachedSet("group", JSON.stringify(gl2.map(g => g === gid + "_占用" ? gid : g)));
    }
    return null;
}

/**
 * 校验并清理 noquit 记录（增强版：增加 NPC 身份自动赦免）
 * @param {string} qq - 玩家QQ号
 * @param {Object} ctx - 上下文
 * @param {Object} msg - 消息对象
 * @returns {Promise<boolean>} - true: 干净/已退出/已转为NPC, false: 仍卡在群里
 */
async function validateAndCleanNoQuit(qq, ctx, msg) {
    const noquitRecord = JSON.parse(cachedGet("noquit") || "{}");
    
    // 1. 如果该玩家本来就没有记录，直接放行
    if (!noquitRecord[qq] || noquitRecord[qq].length === 0) {
        return true;
    }

    // --- 核心优化：NPC 身份检查 ---
    const platform = msg.platform;
    const roleStorage = getRoleStorage();
    const platformRoles = roleStorage[platform] || {};
    const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");

    // 新结构：a_private_group[platform][uid] = [roleName, gid]，直接查
    const roleName = platformRoles[qq]?.[0] || null;

    // 如果该角色现在被标记为了 NPC，直接清空其违规记录并放行
    if (roleName && npcList.includes(roleName)) {
        console.log(`[NoQuit] 检测到玩家 ${roleName}(${qq}) 已转为 NPC，自动清空违规记录。`);
        delete noquitRecord[qq];
        cachedSet("noquit", JSON.stringify(noquitRecord));
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
        cachedSet("noquit", JSON.stringify(noquitRecord));
        return true; 
    } else if (stillInGroups.length < noquitRecord[qq].length) {
        noquitRecord[qq] = stillInGroups;
        cachedSet("noquit", JSON.stringify(noquitRecord));
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
    const platform = msg.platform;
    const roles = (getRoleStorage()[platform] || {});
    const npcs = JSON.parse(cachedGet("a_npc_list") || "[]");
    const extras = JSON.parse(cachedGet("extra_accounts") || "{}");

    const arg1 = cmdArgs.getArgN(1);
    // 检查是否包含"驱逐"参数
    const shouldKick = arg1 === "驱逐";
    // 进行中模式：清空所有非NPC的noquit，只扫描未占用的群
    const isInProgress = arg1 === "进行中";

    // 根据主账号 uid 获取其所有额外账号 QQ 列表
    const getExtraQQs = (primaryQQ) => Object.entries(extras)
        .filter(([k, v]) => k.startsWith(`${platform}:`) && v === primaryQQ)
        .map(([k]) => k.replace(`${platform}:`, ""));

    if (isInProgress) {
        seal.replyToSender(ctx, msg, "🔍 进行中模式：正在清空非NPC未退群记录并扫描空闲群...");

        const rawGroups = JSON.parse(cachedGet("group") || "[]");
        // 只扫描未占用的群（跳过含 _占用 后缀的）
        const freeGroups = rawGroups.filter(g => !g.endsWith("_占用"));

        // 清空所有非NPC玩家的 noquit 记录
        const noquit = JSON.parse(cachedGet("noquit") || "{}");
        for (const qq of Object.keys(noquit)) {
            const roleName = roles[qq]?.[0];
            if (roleName && !npcs.includes(roleName)) {
                delete noquit[qq];
            }
        }

        let countUpdate = 0;
        for (let gid of freeGroups) {
            const members = await getGroupMembersSilent(gid, ctx, msg);
            for (let m of members) {
                const qq = m.user_id.toString();
                const roleName = roles[qq]?.[0];
                if (roleName && !npcs.includes(roleName)) {
                    if (!noquit[qq]) noquit[qq] = [];
                    if (!noquit[qq].includes(gid)) {
                        noquit[qq].push(gid);
                        countUpdate++;
                    }
                }
            }
        }

        cachedSet("noquit", JSON.stringify(noquit));
        seal.replyToSender(ctx, msg, `✅ 进行中扫描完成！\n已清空并重建非NPC未退群记录\n空闲群扫描新增: ${countUpdate} 条记录`);
        return seal.ext.newCmdExecuteResult(true);
    }

    seal.replyToSender(ctx, msg, "🔍 正在扫描全服...");

    const groups = JSON.parse(cachedGet("group") || "[]").map(g => g.replace(/_占用$/, ""));
    const noquit = JSON.parse(cachedGet("noquit") || "{}");

    let countUpdate = 0; // 新增记录数
    let countKick = 0;   // 尝试踢人计数

    // 遍历所有群
    for (let gid of groups) {
        const members = await getGroupMembersSilent(gid, ctx, msg);
        for (let m of members) {
            const qq = m.user_id.toString();
            // 找角色名（新结构 key=uid，value[0]=roleName）
            const roleName = roles[qq]?.[0];

            // 如果是玩家且不是NPC
            if (roleName && !npcs.includes(roleName)) {
                if (!noquit[qq]) {
                    noquit[qq] = [];
                }
                if (!noquit[qq].includes(gid)) {
                    noquit[qq].push(gid);
                    countUpdate++;
                }

                // 驱逐模式：本次扫描到还在群里就踢出（含额外账号）
                if (shouldKick) {
                    const allKickQQs = [qq, ...getExtraQQs(qq)];
                    for (const kqq of allKickQQs) {
                        try {
                            await ws({
                                action: "set_group_kick",
                                params: {
                                    group_id: parseInt(gid),
                                    user_id: parseInt(kqq)
                                }
                            }, ctx, msg, null);
                            countKick++;
                        } catch (e) {
                            console.error(`[踢人] 发送指令失败:`, e);
                        }
                    }
                }
            }
        }
    }

    // 只有数据有变更才保存
    if (countUpdate > 0) {
        cachedSet("noquit", JSON.stringify(noquit));
    }

    // 根据模式回复不同的消息
    if (shouldKick) {
        seal.replyToSender(ctx, msg, `✅ 扫描并驱逐完成！\n新增记录: ${countUpdate} 人\n执行踢出: ${countKick} 人`);
    } else {
        seal.replyToSender(ctx, msg, `✅ 扫描完成，新增 ${countUpdate} 条违规记录。(如需驱逐请加"驱逐"参数)`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["更新未退群"] = cmd_fix_noquit;

// ========================
// 🗑️ 清空季度数据
// ========================
let cmd_reset_season_data = seal.ext.newCmdItemInfo();
cmd_reset_season_data.name = "清空季度数据";
cmd_reset_season_data.help = `用法：。清空季度数据 [确认]
扫描所有群，确认无玩家残留后清空本季度全部玩家数据。
加「确认」参数可跳过残留检查，强制清空。`;
cmd_reset_season_data.solve = async (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const force = (cmdArgs.getArgN(1) || "").trim() === "确认";
    const platform = msg.platform;
    const roles = getRoleStorage()[platform] || {};
    const npcs = JSON.parse(cachedGet("a_npc_list") || "[]");
    const groups = JSON.parse(cachedGet("group") || "[]").map(g => g.replace(/_占用$/, ""));

    if (!force) {
        seal.replyToSender(ctx, msg, "🔍 正在扫描各群残留玩家，请稍候…");
        const remaining = [];
        for (const gid of groups) {
            const members = await getGroupMembersSilent(gid, ctx, msg);
            for (const m of members) {
                const qq = m.user_id.toString();
                const roleName = roles[qq]?.[0];
                if (roleName && !npcs.includes(roleName)) {
                    if (!remaining.find(r => r.qq === qq)) {
                        remaining.push({ name: roleName, qq });
                    }
                }
            }
        }
        if (remaining.length > 0) {
            const list = remaining.map(r => `· ${r.name}（${r.qq}）`).join("\n");
            seal.replyToSender(ctx, msg,
                `⚠️ 以下 ${remaining.length} 名玩家仍在群内，请先执行「更新未退群 驱逐」再清空：\n${list}\n\n` +
                `如需跳过检查强制清空，发送「。清空季度数据 确认」`
            );
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    // 清空全部数据（仅保留 a_adminList / adminPassword）
    const CLEAR_KEYS = [
        // ── 角色 / 季度 ──
        "a_private_group",       "a_npc_list",            "a_lockedSlots",
        "a_wishPool",            "a_quick_official_plan", "extra_accounts",
        "feature_user_blocklist","noquit",                "season_show_name",
        "season_mode",           "season_schedule_start", "season_schedule_end",
        "season_supplement_end", "love_show_name",
        // ── 约会 / 日程 ──
        "appointmentList",       "b_MultiGroupRequest",   "b_confirmedSchedule",
        "join_request_list",     "allowed_appointment_times",
        "appointment_coin_cost", "appointment_duration_config",
        "auto_merge_duplicate_private","enable_join_existing_appointment",
        "group",                 "group_expire_info",     "group_timers",
        "group_session_stats",   "group_write_progress",
        "fupan_routing_enabled", "fupan_routing_groups",
        // ── 统计 / 计数 ──
        "interaction_counts",    "user_stats",            "global_days",
        "season_player_stats",   "auto_day_reset_enabled","auto_day_last_reset",
        "global_gift_cooldowns", "global_gift_stats",
        "global_chaos_letter_counts",
        "lovemail_day_counts",   "lovemail_pool",
        "letter_day_counts",     "wish_daily_post_counts","wish_daily_pick_counts",
        "a_meetingCount_call",   "a_meetingCount_chaosletter",
        "a_meetingCount_directletter", "a_meetingCount_gift",
        "a_meetingCount_letter", "a_meetingCount_lovemail",
        "a_meetingCount_official","a_meetingCount_private",
        "a_meetingCount_secretletter","a_meetingCount_wish",
        // ── 角色属性 / 档案 ──
        "sys_char_profiles",     "sys_character_attrs",   "sys_attr_presets",
        "rpg_attr_defs",
        // ── 物品 / 背包 / 商城 ──
        "item_registry",         "item_currencies",       "item_usage_log",
        "global_inventories",    "player_draw_records",   "player_equipments",
        "player_pity_counters",  "player_level",          "player_level_history",
        "shop_listings",         "secondhand_market",     "market_config",
        "pool_definitions",      "pool_draw_config",      "presets",
        "craft_recipes",         "attack_defense_config", "attack_defense_data",
        "equipment_config",      "equipment_registry",    "equipment_slots",
        "equipment_slot_names",  "level_up_rules",        "max_level",
        // ── 道具效果 ──
        "phone_tap_effects",     "sms_tap_effects",       "sms_echo_wall_effects",
        "letter_quill_pen_effects","letter_telescope_effects","letter_pending_quill_pens",
        "apply_item_expose_rate","apply_item_hours",      "apply_item_notification",
        "item_tracker_show_partner","item_tracker_success_rate","item_tracker_time_restrict",
        // ── 礼品店 ──
        "preset_gifts",          "gift_sightings",        "shop_personal_display",
        "shop_refresh_hours",    "shop_gift_catalog_on_receive",
        "sighting_daily_count",  "sighting_system_config",
        // ── 拍卖 ──
        "auction_items",         "auction_allow_anon",    "auction_broadcast",
        "auction_currency",      "auction_show_top_bidder",
        // ── 地点 ──
        "available_places",      "place_keys",            "place_system_config",
        // ── 信件 / 心动信 ──
        "lovemail_default_limit","lovemail_day_limits",   "lovemail_delivery_time",
        "lovemail_expose",       "lovemail_expose_chance","letter_public_send",
        "allow_custom_letter_sign","chaos_letter_config", "mailCooldown",
        "direct_letter_cooldown","direct_letter_daily_limit","direct_letter_min_chars",
        "direct_letter_reward",  "direct_letter_sync_enabled",
        // ── 礼物 ──
        "gift_public_send",      "allow_custom_gift_sign","drop_hide_receiver",
        "giftCooldown",          "giftDailyLimit",        "giftMode",
        "giftPublicChance",
        // ── 心愿 ──
        "wish_bounty_enabled",   "wish_coin_cost",        "wish_public_send",
        "wish_max_concurrent",   "wish_daily_post_limit", "wish_daily_pick_limit",
        // ── 关系线 ──
        "relationship_lines",    "relationship_system_enabled",
        "max_relationships_per_user","max_detail_chars",
        "max_detail_count",      "max_rel_total_chars",  "forward_split_threshold",
        // ── 社交 / 论坛 / 晚餐 ──
        "forum_posts",           "forum_max_length",      "dinner_system_data",
        "wechat_groups",
        // ── 收集 / 写帖 ──
        "sys_info_collection",   "sys_info_projects",     "projects",
        // ── Binary Tag / 目击 ──
        "sys_binary_tags",
        // ── 时段窗口配置 ──
        "ts_allowed_durations",  "ts_blocked_by_day",     "ts_feature_windows",
        "ts_strict_hour_match",
        // ── 临时数据（点歌/审计中转）──
        "temp_audit_owner",      "temp_song_dgr",         "temp_song_ly",
        "temp_source_group_name","temp_target_gid",       "temp_task_type",
        // ── 系统设置 ──
        "global_feature_toggle", "custom_message_templates",
        "allow_private_rooms",   "announceFrequency",     "monitor_settings",
        "background_group_id",   "song_group_id",         "adminAnnounceGroupId",
        "end_game_bonus_templates","end_game_draw_config",
        "end_season_report_enabled","group_expire_hours", "idle_group_name",
    ];

    for (const key of CLEAR_KEYS) {
        cachedSet(key, "");
    }

    // changriRPG 自有存储
    const rpgExt = seal.ext.find("changriRPG");
    if (rpgExt) rpgExt.storageSet("scheduled_collections", "");

    // 长日晚餐自有存储（数据存在 dinner_system 命名空间，不在 changri 里）
    const dinnerExt = seal.ext.find("dinner_system");
    if (dinnerExt) {
        for (const k of ["dinner_system_data", "guard_game_state", "guard_game_locations"]) {
            dinnerExt.storageSet(k, "");
        }
    }

    seal.replyToSender(ctx, msg,
        `✅ 季度数据已全量清空\n仅保留：管理员列表、密令。\n\n` +
        `现在可以执行：\n。创建新季度 恋综名 复盘/不复盘 MMDD-MMDD`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空季度数据"] = cmd_reset_season_data;

// --- 辅助提取：统一的角色信息获取 ---
const getRoleDetails = (platform, name) => {
    // name is a roleName; look up the uid first, then get gid
    const privateGroups = JSON.parse(cachedGet("a_private_group") || "{}");
    const uid = getUidByRoleName(platform, name);
    if (!uid) return { uid: null, gid: null };
    const info = privateGroups?.[platform]?.[uid] || [];
    return { uid, gid: info[1] };
};

async function finalizeGroupCreation(platform, ctx, msg, groupData, participants) {
    // 1. 获取可用群号
    const gid = await allocateGroup(platform, ctx, msg);
    if (!gid) {
        seal.replyToSender(ctx, msg, "❌ 暂无可调用的群号，请联系管理员扩容群池。");
        return false;
    }

    const expireHours = getStorageInt("group_expire_hours", 48);
    const expireTime = Date.now() + expireHours * 3600000;
    const timeStr = new Date(expireTime).toLocaleString("zh-CN", { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });

    // 2. 准备数据落盘
    const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const groupInfo = JSON.parse(cachedGet("group_expire_info") || "{}");

    participants.forEach(name => {
        const details = getRoleDetails(platform, name);
        if (!details || !details.uid) return;
        const key = `${platform}:${details.uid.replace(/^[a-z]+:/i, "")}`;
        
        if (!b_confirmedSchedule[key]) b_confirmedSchedule[key] = [];
        
        // 逻辑：如果只有2人，Partner 存对方名字；如果多人，存"多人小群"
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
    cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));
    cachedSet("group_expire_info", JSON.stringify(groupInfo));

    // 3. 构建群名：2人显示名字，多于2人显示"多人"
    const participantsText = participants.join("、");
    const groupNameTag = participants.length > 2 ? "多人" : participantsText;
    const finalGroupName = `${groupData.subtype} ${groupData.day} ${groupData.time} ${groupNameTag}`;

    // 4. 构建通知文案
    const otherNames = participants.filter(n => n !== groupData.sendname);
    const multiLine = participants.length > 2
        ? `\n同行：${otherNames.join("、")}`
        : (otherNames.length === 1 ? "" : "");

    const guide = `\n\n修改时间 ➜ 修改时间线 ${groupData.day} 新时间\n不想参加 ➜ 拒绝时间线 ${gid}\n结束互动 ➜ 在约会群发「结束私约」`;

    // 发给各参与者私群的邀请通知（保留"邀你"措辞）
    let noticeText;
    if (groupData.subtype === "电话") {
        const titleLine = groupData.title ? ` · ${groupData.title}` : "";
        const peersLine = participants.length > 2 ? `\n同话：${otherNames.join("、")}` : "";
        noticeText = `📞 来电

${groupData.sendname} 邀你接听通话${titleLine}
🕐 ${groupData.day} ${groupData.time}${peersLine}

频段：${gid}
有效至 ${timeStr}${guide}`;
    } else {
        noticeText = `💌 私约

${groupData.sendname} 约你 ${groupData.day} ${groupData.time} 在 ${groupData.place} 相见${multiLine}

群号：${gid}
有效至 ${timeStr}${guide}`;
    }

    // 发到约会群本身的公告（列出全部参与者，去掉"邀你"措辞）
    let groupAnnouncement;
    if (groupData.subtype === "电话") {
        const titleLine = groupData.title ? ` · ${groupData.title}` : "";
        groupAnnouncement = `📞 通话已接通${titleLine}

🕐 ${groupData.day} ${groupData.time}
👥 参与者：${participantsText}

✍️ 戏文格式：首行写自己的角色名，换行后写正文（不符合格式的消息视为闲聊，不计入存档与字数）

频段：${gid}
有效至 ${timeStr}${guide}`;
    } else {
        groupAnnouncement = `💌 约会已确认

📅 ${groupData.day} ${groupData.time}
📍 ${groupData.place}
👥 参与者：${participantsText}

群号：${gid}
有效至 ${timeStr}${guide}`;
    }

    // 5. 向所有参与者发送私聊/绑定群通知（跳过发起者，发起者由指令回执告知）
    participants.forEach(name => {
        if (name === groupData.sendname) return;
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

    seal.replyToSender(targetCtx, targetMsg, groupAnnouncement);
    setGroupName(targetCtx, targetMsg, gid, finalGroupName);

    // 6.5 在每人的个人绑定群单独发一条 @提醒，提示在约会群发 .ext all on
    participants.forEach(name => {
        const { uid, gid: bindGid } = getRoleDetails(platform, name);
        if (!uid || !bindGid) return;
        const m = seal.newMessage();
        m.messageType = "group";
        m.groupId = `${platform}-Group:${bindGid}`;
        const tempCtx = seal.createTempCtx(ctx.endPoint, m);
        seal.replyToSender(tempCtx, m, `[CQ:at,qq=${uid}]\n⚠️ 请在约会群（群号：${gid}）发送 .ext all on 开启机器人指令，否则可能收不到结戏奖励！`);
    });

    // 7. 其他系统触发
    triggerSightingCheck(platform, groupData.day, groupData.time, groupData.place, participants, gid, groupData.subtype, ctx, msg);
    recordMeetingAndAnnounce(groupData.subtype, platform, ctx, ctx.endPoint);
    if (groupData.subtype) initGroupTimer(platform, gid, groupData.subtype, participants, participants[0]);
    return gid;
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
        
        // 读取并解析存储
        const groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
        
        // 核心修改：[indexKey, info] 对应 ["239689865", {对象内容}]
        const expiredGroups = [];
        for (const [indexKey, info] of Object.entries(groupExpireInfo)) {
            if (now > info.expireTime) {
                expiredGroups.push({ indexKey, ...info });
            }
        }
        
        const formatTime = (ts) => new Date(ts).toLocaleString("zh-CN", { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
        
        // 1. 查看列表
        if (!action) {
            if (!expiredGroups.length) return seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组。"), seal.ext.newCmdExecuteResult(true);
            if (!msg.groupId) return seal.replyToSender(ctx, msg, "⚠️ 请在群内使用此指令。"), seal.ext.newCmdExecuteResult(true);
            const botUid = ctx.endPoint.userId;
            const nodes = [];
            nodes.push({ type: "node", data: { name: "到期群总览", uin: botUid, content: `⏰ 已到期群组列表（共 ${expiredGroups.length} 个）\n💡 使用「。查看到期群 提醒」向到期群发送消息` } });
            expiredGroups.forEach(g => {
                const overdue = (now - g.expireTime) / 60000;
                const overdueDays = Math.floor(overdue / 1440), overdueHours = Math.floor((overdue % 1440) / 60), overdueMins = Math.floor(overdue % 60);
                const overdueStr = `${overdueDays?`${overdueDays}天`:''}${overdueHours?`${overdueHours}小时`:''}${overdueMins}分钟`;
                const content = `📌 群号：${g.indexKey}\n类型：${g.subtype || '小群'}\n时间：${g.day} ${g.time}\n地点：${g.place}\n参与者：${g.participants.join('、')}\n到期时间：${formatTime(g.expireTime)}\n已超时：${overdueStr}`;
                nodes.push({ type: "node", data: { name: g.participants.join('、') || "未知", uin: botUid, content } });
            });
            ws({ action: "send_group_forward_msg", params: { group_id: parseInt(msg.groupId.replace(/[^\d]/g, ""), 10), messages: nodes } }, ctx, msg, "");
            return seal.ext.newCmdExecuteResult(true);
        }
        
        // 2. 发送提醒
        if (action === "提醒") {
            if (!expiredGroups.length) return seal.replyToSender(ctx, msg, "📭 当前没有已到期的群组，无需提醒。"), seal.ext.newCmdExecuteResult(true);
            let successCount = 0, failCount = 0;
            
            for (const group of expiredGroups) {
                try {
                    const groupMsg = seal.newMessage();
                    groupMsg.messageType = "group";
                    // 关键：发消息必须用内部真正的 gid
                    groupMsg.groupId = `${platform}-Group:${group.indexKey}`;
                    
                    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);
                    const reminderMsg = `⏰ 温馨提示：\n本群互动时间已经超时了哦～\n\n📋 记录号：${group.indexKey}\n• 时间：${group.day} ${group.time}\n• 地点：${group.place}\n\n如果互动已结束，请使用「结束私约」`;
                    
                    seal.replyToSender(groupCtx, groupMsg, reminderMsg);
                    successCount++;
                } catch (e) {
                    failCount++;
                }
            }
            return seal.replyToSender(ctx, msg, `📢 提醒发送完成！\n✅ 成功：${successCount}\n❌ 失败：${failCount}`), seal.ext.newCmdExecuteResult(true);
        }
        
        return seal.replyToSender(ctx, msg, "⚠️ 参数错误。"), seal.ext.newCmdExecuteResult(true);
    } catch (error) {
        console.log(`[异常] .查看到期群: ${error.stack}`);
        return seal.replyToSender(ctx, msg, "⚠️ 执行出错，请检查后台日志。"), seal.ext.newCmdExecuteResult(true);
    }
};

ext.cmdMap["查看到期群"] = cmd_view_expired_groups;

function getIdleGroupName() {
    return (cachedGet("idle_group_name") || "").trim() || "备用";
}

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
cmdSpecialTitle.help = "群头衔功能，可用.群头衔 内容 指令来更改。 .群头衔 权限切换来切换可发布者的身份，默认为管理员与群主才能更改头衔（master和白名单例外），切换后为所有人都可以更改。无论哪种权限，管理员和群主可以通过@某人代改。";
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
  const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");

  if (!role) {
    seal.replyToSender(ctx, msg, "📌 请注明需查看的角色名，例如：\n.查看他人时间线 玛丽");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `⚠️ 此乃管理权限之事，非管理员者不得窥探他人行迹`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const targetUid = getUidByRoleName(platform, role);
  if (!targetUid) {
    seal.replyToSender(ctx, msg, `⚠️ 找不到角色「${role}」，请确认其已完成绑定`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const key = `${platform}:${targetUid}`;
  const schedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");

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
      let marker = ev.subtype === "电话" ? "📞" : "🤫";
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
    let a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    let a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");

    // 获取目标角色列表（roleNames 用于显示，内部转换为 uid 操作）
    let targetRoles = [];

    if (target === "全体") {
        // 获取当前平台所有角色名
        if (a_private_group[platform]) {
            targetRoles = Object.values(a_private_group[platform]).map(v => v[0]).filter(Boolean);
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
        // 新结构：通过 roleName 反查 uid
        const uid = getUidByRoleName(platform, roleName);
        if (!uid) {
            notFoundList.push(roleName);
            continue;
        }

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
    cachedSet("a_lockedSlots", JSON.stringify(a_lockedSlots));

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
  let a_adminList = JSON.parse(cachedGet("a_adminList") || "{}");
  if (!a_adminList[platform]) a_adminList[platform] = [];

  if (!a_adminList[platform].includes(targetQQ)) {
    a_adminList[platform].push(targetQQ);
    cachedSet("a_adminList", JSON.stringify(a_adminList));
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
  cachedSet("adminPassword", JSON.stringify(newPass));

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

  let a_adminList = JSON.parse(cachedGet("a_adminList") || "{}");
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
  cachedSet("a_adminList", JSON.stringify(a_adminList));
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

  const a_adminList = JSON.parse(cachedGet("a_adminList") || "{}");
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

  cachedSet("a_adminList", JSON.stringify({}));
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
  const uid = getUidByRoleName(platform, name);
  if (!uid) {
    seal.replyToSender(ctx, msg, `未找到角色「${name}」，请确认其是否已绑定`);
    return;
  }

  const key = `${platform}:${uid}`;
  const a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");

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
cmd_block_user_feature.help = "。功能权限 角色名 功能 开启/关闭\n功能：礼物/发起邀约/寄信/心愿/心动信/论坛/抽取/全部";

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
    "抽取": "enable_item_draw"
  };

  const value = (action === "开启") ? true : (action === "关闭") ? false : null;
  if (value === null) {
    seal.replyToSender(ctx, msg, `⚠️ 状态应为：开启 / 关闭`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 新结构：feature_user_blocklist[uid] 而非 [roleName]
  const platform = msg.platform;
  const targetUid = getUidByRoleName(platform, roleName);
  if (!targetUid) {
    seal.replyToSender(ctx, msg, `❌ 找不到角色「${roleName}」`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let blockMap = JSON.parse(cachedGet("feature_user_blocklist") || "{}");
  if (!blockMap[targetUid]) blockMap[targetUid] = {};

  if (featureName === "全部") {
    for (const key of Object.values(featureMap)) blockMap[targetUid][key] = value;
    cachedSet("feature_user_blocklist", JSON.stringify(blockMap));
    const status = value ? "✅ 已开启" : "🚫 已关闭";
    seal.replyToSender(ctx, msg, `${status} 全部功能：${roleName}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const key = featureMap[featureName];
  if (!key) {
    seal.replyToSender(ctx, msg, `⚠️ 功能名可选：礼物 / 发起邀约 / 寄信 / 心愿 / 心动信 / 论坛 / 抽取 / 全部`);
    return seal.ext.newCmdExecuteResult(true);
  }

  blockMap[targetUid][key] = value;
  cachedSet("feature_user_blocklist", JSON.stringify(blockMap));

  const status = value ? "✅ 已开启" : "🚫 已关闭";
  seal.replyToSender(ctx, msg, `${status} ${featureName} 功能：${roleName}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["功能权限"] = cmd_block_user_feature;

let cmd_view_user_feature = seal.ext.newCmdItemInfo();
cmd_view_user_feature.name = "查看功能权限";
cmd_view_user_feature.help = "。查看功能权限 —— 查看所有被设定过功能开关的角色与状态";

cmd_view_user_feature.solve = (ctx, msg, cmdArgs) => {
  let blockMap = JSON.parse(cachedGet("feature_user_blocklist") || "{}");

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
    enable_item_draw: "抽取"
  };


  let lines = [];

  // 新结构：blockMap[uid]，显示时转为 roleName
  for (let uid in blockMap) {
    const displayName = resolveUidToNameAnyPlatform(uid);
    let userFeatures = blockMap[uid];
    let statusList = [];

    for (let key in userFeatures) {
      let status = userFeatures[key] ? "✅开启" : "🚫关闭";
      let label = featureLabelMap[key] || key;
      statusList.push(`${label}：${status}`);
    }

    if (statusList.length > 0) {
      lines.push(`【${displayName}】→ ${statusList.join("，")}`);
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
// 🕊️ 寄信与关系线系统
// ========================
async function handleNaturalChaosLetter(ctx, msg, platform, sendname, toname, contentOriginal) {
    const config = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (config.enable_chaos_letter === false) {
        return seal.replyToSender(ctx, msg, "🕊️ 寄信功能已关闭。");
    }

    // 真实角色名（sendname 可能是自定义署名，realSendname 始终是绑定角色）
    const realSendname = getRoleName(ctx, msg) || sendname;

    if (toname === realSendname) {
        return seal.replyToSender(ctx, msg, "📱 短信不可发给自己。");
    }

    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const toUidForLetter = getUidByRoleName(platform, toname);
    if (!toUidForLetter) {
        return seal.replyToSender(ctx, msg, `❌ 未找到收信人：${toname}`);
    }

    // 🎲 读取混乱配置
    let chaosConfig = JSON.parse(cachedGet("chaos_letter_config") || "{}");
    const defaultConfig = {
        misdelivery: 0, blackoutText: 0, loseContent: 0, antonymReplace: 0,
        reverseOrder: 0, mistakenSignature: 0, poeticSignature: 0, dailyLimit: 5, publicChance: 50
    };
    chaosConfig = { ...defaultConfig, ...chaosConfig };

    // ⏳ 冷却与次数检查 (使用发送者的主账号 UID)
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const cooldownKey = `chaos_letter_cooldown_${platform}:${uid}`;
    const lastSent = parseInt(cachedGet(cooldownKey) || "0");
    const now = Date.now();
    const mailCooldownMin = getStorageInt("mailCooldown", 60);
    
    if (now - lastSent < mailCooldownMin * 60 * 1000) {
        const rem = Math.ceil((mailCooldownMin * 60 * 1000 - (now - lastSent)) / 60000);
        return seal.replyToSender(ctx, msg, `⏳ 鸽子正在休息，请 ${rem} 分钟后再试`);
    }

    const gameDay = cachedGet("global_days") || "D0"; 
    const globalChaosCounts = JSON.parse(cachedGet("global_chaos_letter_counts") || "{}");
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

    // 🖋️ 落款逻辑（新结构：keys 是 uid，values[0] 是 roleName）
    let finalSignature = `落款：${sendname}`;
    const sigRoll = Math.random();
    if (sigRoll < (chaosConfig.mistakenSignature / 100)) {
        const allRoleNames = Object.values(a_private_group[platform] || {}).map(v => v[0]).filter(n => n && n !== sendname);
        if (allRoleNames.length) finalSignature = `落款：${allRoleNames[Math.floor(Math.random() * allRoleNames.length)]}`;
    }

    // 📤 投递
    let trueRecipientName = toname;
    let trueRecipientUid = toUidForLetter;
    if (Math.random() < (chaosConfig.misdelivery / 100)) {
        const otherEntries = Object.entries(a_private_group[platform] || {}).filter(([uid, v]) => v[0] !== toname);
        if (otherEntries.length) {
            const pick = otherEntries[Math.floor(Math.random() * otherEntries.length)];
            trueRecipientUid = pick[0];
            trueRecipientName = pick[1][0];
        }
    }

    const targetEntry = a_private_group[platform]?.[trueRecipientUid];
    if (!targetEntry) {
        seal.replyToSender(ctx, msg, "❌ 短信投递失败：找不到收件人所在群组。");
        return;
    }
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    const notice = applyMsgTemplate("sms_notice", {
        "收件人": trueRecipientName, "收件人QQ": trueRecipientUid,
        "内容": content, "落款": finalSignature
    }) || `[CQ:at,qq=${trueRecipientUid}]\n📱 ${trueRecipientName}，你收到一条短信：\n「${content}」\n\n${finalSignature}`;
    seal.replyToSender(newctx, newmsg, notice);
    recordInteractionStat(platform, sendname, trueRecipientName, "sms");

    // 提前判断是否公开（需在存档前确定，以便写入 hide_receiver）
    const hideReceiverOnDrop = cachedGet("drop_hide_receiver") === "true";
    const letterPublicEnabled = JSON.parse(cachedGet("letter_public_send") || "false");
    const adminGidForSms = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");
    const isPublicSms = letterPublicEnabled && adminGidForSms &&
        (Math.floor(Math.random() * 100) + 1 <= chaosConfig.publicChance);

    // 短信实时存档
    if (isArchiveEnabled()) {
        const isMisdelivered    = trueRecipientName !== toname;
        const isContentChaos    = content !== contentOriginal;
        const isSignatureChaos  = finalSignature !== `落款：${sendname}`;
        postToArchive("/api/event", {
            type:            "sms",
            from_role:       realSendname,
            from_custom_name: sendname !== realSendname ? sendname : undefined,
            from_qq:         uid,
            to_role:         trueRecipientName,
            to_qq:           trueRecipientUid,
            content:         contentOriginal,
            extra_info: {
                delivered:          content,
                signature:          finalSignature,
                intended_to:        toname,
                is_misdelivered:    isMisdelivered,
                is_content_chaos:   isContentChaos,
                is_signature_chaos: isSignatureChaos,
                is_chaos:           isMisdelivered || isContentChaos || isSignatureChaos,
                isPublic:           isPublicSms,
                hide_receiver:      isPublicSms && hideReceiverOnDrop
            },
            game_day:   gameDay,
            session_id: "",
            timestamp:  Date.now()
        });
    }

    // 7. 更新数据
    cachedSet(cooldownKey, now.toString());
    userRec.count += 1;
    globalChaosCounts[userKey] = userRec;
    cachedSet("global_chaos_letter_counts", JSON.stringify(globalChaosCounts));

    seal.replyToSender(ctx, msg, `🕊️ 信件已由鸽子衔往 ${toname} 处。今日已发 ${userRec.count}/${chaosConfig.dailyLimit}。`);

    // 公开逻辑
    if (isPublicSms) {
        const pMsg = seal.newMessage();
        pMsg.messageType = "group";
        pMsg.groupId = `${platform}-Group:${adminGidForSms}`;
        const pCtx = seal.createTempCtx(ctx.endPoint, pMsg);
        const publicContent = chaosConfig.publicShowEffect ? content : contentOriginal;
        const publicTo = hideReceiverOnDrop ? "某人" : toname;
        seal.replyToSender(pCtx, pMsg, applyMsgTemplate("sms_broadcast", {
            "发送者": sendname, "收件人": publicTo, "内容": publicContent
        }) || `💌 公开信件：\n「${sendname}」→「${publicTo}」\n内容：「${publicContent}」`);
    }

    if (typeof recordMeetingAndAnnounce === "function") {
        recordMeetingAndAnnounce("寄信", platform, ctx, ctx.endPoint);
    }
}

// ========================
// 🏢 官约与目击系统
// ========================

let cmd_create_official_appointment = seal.ext.newCmdItemInfo();
cmd_create_official_appointment.name = "发起官约";
cmd_create_official_appointment.help = "。发起官约 D1 14:00-15:00 地点 参与者1/参与者2/...（管理员专用，自动创建官方约会群组）";

cmd_create_official_appointment.solve = async (ctx, msg, cmdArgs) => {
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
  const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
  const a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
  const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");

  if (!a_private_group[platform]) {
    seal.replyToSender(ctx, msg, `当前平台没有绑定任何角色`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let validParticipants = [];
  let invalidParticipants = [];

  for (let name of participants) {
    if (getUidByRoleName(platform, name)) {
      validParticipants.push(name);
    } else {
      invalidParticipants.push(name);
    }
  }

  if (invalidParticipants.length > 0) {
    seal.replyToSender(ctx, msg, `以下参与者未找到：${invalidParticipants.join("、")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查时间冲突逻辑
  let conflictParticipants = [];
  for (let name of validParticipants) {
    const uid = getUidByRoleName(platform, name);
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
  const gid = await allocateGroup(platform, ctx, msg);
  if (!gid) {
    seal.replyToSender(ctx, msg, `暂无可用群号`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // --- 新增：过期与计时逻辑 ---
  const acceptTime = Date.now();
  const expireHours = getStorageInt("group_expire_hours", 48);
  const expireTime = acceptTime + expireHours * 60 * 60 * 1000;
  const formatTime = (ts) => new Date(ts).toLocaleString("zh-CN", { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
  const expireNotice = `⏰ 本群将在 ${formatTime(expireTime)} 自动结束（${expireHours}小时有效期）`;

  // 更新已确认日程
  for (let name of validParticipants) {
    const uid = getUidByRoleName(platform, name);
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
  cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

  // 记录群组过期信息
  let groupInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
  groupInfo[gid] = {
      acceptTime: acceptTime,
      expireTime: expireTime,
      participants: validParticipants,
      subtype: "官约",
      day: day,
      time: time,
      place: place
  };
  cachedSet("group_expire_info", JSON.stringify(groupInfo));

  // 改群名
  const groupNameTag = validParticipants.length > 2 ? "多人" : validParticipants.join("、");
  const finalGroupName = `官约 ${day} ${time} ${place} ${groupNameTag}`;
  const targetMsg = seal.newMessage();
  targetMsg.messageType = "group";
  targetMsg.groupId = `${platform}-Group:${gid}`;
  const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);
  setGroupName(targetCtx, targetMsg, gid, finalGroupName);

  // 向戏群发公告
  const officialGuide = `\n\n修改时间 ➜ 修改时间线 ${day} 新时间\n不想参加 ➜ 拒绝时间线 ${gid}`;
  const officialAnnouncement = `🎖️ 官约已确认\n\n📅 ${day} ${time}\n📍 ${place}\n👥 参与者：${validParticipants.join("、")}\n\n群号：${gid}\n有效至 ${new Date(expireTime).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}${officialGuide}`;
  seal.replyToSender(targetCtx, targetMsg, officialAnnouncement);

  // 向每位参与者的绑定群发送群号
  for (let name of validParticipants) {
    const nameUid = getUidByRoleName(platform, name);
    const boundGroupId = nameUid ? a_private_group[platform][nameUid]?.[1] : null;
    if (!boundGroupId) continue;
    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.groupId = `${platform}-Group:${boundGroupId}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
    seal.replyToSender(newctx, newmsg, `🎖️ 官约通知\n\n📅 ${day} ${time}\n📍 ${place}\n👥 参与者：${validParticipants.join("、")}\n\n💬 官约群号：${gid}`);
  }

  // --- 核心：启动计时器 ---
  // 官约模式下，默认发起人为管理员，这里可以使用 validParticipants[0] 作为逻辑上的发起者
  if (typeof initGroupTimer === "function") {
      initGroupTimer(platform, gid, "官约", validParticipants, validParticipants[0]);
  }

  recordMeetingAndAnnounce("官约", platform, ctx, ctx.endPoint);
  seal.replyToSender(ctx, msg, `✅ 官约创建成功！群号：${gid}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["发起官约"] = cmd_create_official_appointment;

// ========================
// 📋 Binary Tag 管理
// ========================

let cmd_modify_tag = seal.ext.newCmdItemInfo();
cmd_modify_tag.name = "修改tag";
cmd_modify_tag.help = "。修改tag tag名字 种类1:姓名1，姓名2 种类2:姓名3，姓名4（管理员专用，创建/更新 binary tag 并分配玩家）";

cmd_modify_tag.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "只有管理员可以使用此功能");
        return seal.ext.newCmdExecuteResult(true);
    }

    const raw = msg.message.trim().replace(/^[。.]\S+\s*/, "");
    const spaceIdx = raw.search(/\s+/);
    if (spaceIdx === -1) {
        seal.replyToSender(ctx, msg, "格式：。修改tag tag名字 种类1:姓名1，姓名2 种类2:姓名3，姓名4");
        return seal.ext.newCmdExecuteResult(true);
    }

    const tagName = raw.slice(0, spaceIdx).trim();
    const rest = raw.slice(spaceIdx).trim();

    // 解析 "种类1:姓名1，姓名2 种类2:姓名3，姓名4"
    const catPattern = /([^\s：:]+)[：:]\s*([^：:]+?)(?=\s+[^\s：:]+[：:]|$)/g;
    const catMatches = [...rest.matchAll(catPattern)];

    if (catMatches.length < 2) {
        seal.replyToSender(ctx, msg, "格式错误：需要至少两个种类。\n格式：。修改tag tag名字 种类1:姓名1，姓名2 种类2:姓名3，姓名4");
        return seal.ext.newCmdExecuteResult(true);
    }

    const tags = store.get("sys_binary_tags");
    tags[tagName] = {};
    for (const m of catMatches) {
        const catName = m[1].trim();
        const names = m[2].trim().split(/[，,、\s]+/).map(s => s.trim()).filter(Boolean);
        tags[tagName][catName] = names;
    }
    store.set("sys_binary_tags", tags);

    let reply = `✅ 已更新 tag「${tagName}」：\n`;
    for (const [cat, names] of Object.entries(tags[tagName])) {
        reply += `  · ${cat}：${names.join("、")}\n`;
    }
    seal.replyToSender(ctx, msg, reply.trim());
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["修改tag"] = cmd_modify_tag;

// 📋 便捷官约：计划官约 + 执行官约
// ========================

let cmd_plan_official = seal.ext.newCmdItemInfo();
cmd_plan_official.name = "计划官约";
cmd_plan_official.help = "。计划官约 tag名字/无 组数 D几 时间段 地点1，地点2，...（管理员专用，生成官约分组方案）";

cmd_plan_official.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员可以使用此功能`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const tagArg     = cmdArgs.getArgN(1);
  const groupCount = parseInt(cmdArgs.getArgN(2));
  const day        = cmdArgs.getArgN(3);
  const time       = cmdArgs.getArgN(4);
  const placesRaw  = cmdArgs.getArgN(5);

  if (!tagArg || isNaN(groupCount) || groupCount <= 0 || !day || !time || !placesRaw) {
    seal.replyToSender(ctx, msg, `格式：。计划官约 tag名字/无 组数 D几 时间段 地点1，地点2，...\n示例：。计划官约 贵族 2 D1 14:00-16:00 咖啡厅，公园\n示例：。计划官约 无 2 D1 14:00-16:00 咖啡厅，公园`);
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!isValidTimeFormat(time)) {
    seal.replyToSender(ctx, msg, `请输入合法的时间格式，如 14:00-16:00，且结束时间需大于开始时间`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const wantTag = (tagArg !== "无");
  const platform = msg.platform;

  // 解析地点（支持中英文逗号）
  const places = placesRaw.replace(/,/g, "，").split("，").map(p => p.trim()).filter(Boolean);
  if (places.length !== groupCount) {
    seal.replyToSender(ctx, msg, `❌ 建设不成功：地点数量（${places.length}）与组数（${groupCount}）不一致，请确保地点和组数相同`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 获取所有非NPC玩家
  const apg = store.get("a_private_group")[platform] || {};
  const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
  const allPlayers = Object.entries(apg)
    .map(([uid, val]) => ({ uid, name: val[0] }))
    .filter(p => p.name && !npcList.includes(p.name));

  if (allPlayers.length === 0) {
    seal.replyToSender(ctx, msg, `❌ 当前平台没有非NPC玩家`);
    return seal.ext.newCmdExecuteResult(true);
  }
  if (groupCount > allPlayers.length) {
    seal.replyToSender(ctx, msg, `❌ 组数(${groupCount})不能大于玩家总数(${allPlayers.length})`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查所有玩家的时间冲突
  const a_lockedSlots      = JSON.parse(cachedGet("a_lockedSlots") || "{}");
  const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
  let conflictPlayers = [];
  for (let p of allPlayers) {
    const key = `${platform}:${p.uid}`;
    const locked = a_lockedSlots[key]?.[day] || [];
    if (locked.some(slot => timeOverlap(slot, time))) {
      conflictPlayers.push(`${p.name}（被锁定）`);
      continue;
    }
    const schedule = b_confirmedSchedule[key] || [];
    if (schedule.some(ev => ev.day === day && timeOverlap(ev.time, time))) {
      conflictPlayers.push(`${p.name}（已有安排）`);
    }
  }
  if (conflictPlayers.length > 0) {
    seal.replyToSender(ctx, msg, `❌ 建设不成功：以下玩家时间冲突：\n${conflictPlayers.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 分组（Fisher-Yates 洗牌）
  const shuffle = arr => {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  };

  let groups = Array.from({ length: groupCount }, () => []);
  if (wantTag) {
    const allTags = store.get("sys_binary_tags");
    const tagData = allTags[tagArg];
    if (!tagData || Object.keys(tagData).length === 0) {
      seal.replyToSender(ctx, msg, `❌ 未找到 tag「${tagArg}」，请先使用「。修改tag」创建`);
      return seal.ext.newCmdExecuteResult(true);
    }

    const nameToPlayer = {};
    for (const p of allPlayers) nameToPlayer[p.name] = p;

    const buckets = Object.values(tagData).map(names =>
      shuffle(names.filter(n => nameToPlayer[n]).map(n => nameToPlayer[n]))
    );

    const assignedNames = new Set(Object.values(tagData).flat());
    const unassigned = shuffle(allPlayers.filter(p => !assignedNames.has(p.name)));

    const maxLen = Math.max(...buckets.map(b => b.length), 0);
    const indices = buckets.map(() => 0);
    for (let r = 0; r < maxLen; r++) {
      for (let b = 0; b < buckets.length; b++) {
        if (indices[b] < buckets[b].length) {
          groups[r % groupCount].push(buckets[b][indices[b]++].name);
        }
      }
    }
    unassigned.forEach((p, idx) => { groups[idx % groupCount].push(p.name); });
  } else {
    shuffle(allPlayers).forEach((p, idx) => { groups[idx % groupCount].push(p.name); });
  }

  // 保存方案
  const planGroups = groups.map((members, i) => ({ participants: members, place: places[i] }));
  const plan = { platform, day, time, groupCount, groups: planGroups };
  cachedSet("a_quick_official_plan", JSON.stringify(plan));

  // 展示方案
  let resp = `📋 官约方案已生成${wantTag ? `（${tagArg} 交替模式）` : ""}：\n`;
  resp += `📅 ${day} ${time}\n━━━━━━━━━━━━━━\n`;
  planGroups.forEach((g, i) => {
    resp += `第 ${i + 1} 组 📍${g.place}：${g.participants.join("、")}\n`;
  });
  resp += `━━━━━━━━━━━━━━\n✅ 方案已保存，使用「。执行官约」一键发起所有官约`;
  seal.replyToSender(ctx, msg, resp);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["计划官约"] = cmd_plan_official;

// ---

let cmd_execute_official = seal.ext.newCmdItemInfo();
cmd_execute_official.name = "执行官约";
cmd_execute_official.help = "。执行官约（管理员专用，一键执行已保存的官约方案）";

cmd_execute_official.solve = async (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `只有管理员可以执行官约`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const planRaw = cachedGet("a_quick_official_plan");
  if (!planRaw) {
    seal.replyToSender(ctx, msg, `❌ 没有已保存的官约方案，请先使用「。计划官约」生成方案`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const plan = JSON.parse(planRaw);
  if (plan.platform !== msg.platform) {
    seal.replyToSender(ctx, msg, `❌ 保存的方案属于其他平台，请重新计划`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const { day, time, groups } = plan;
  const platform = msg.platform;
  const apg = store.get("a_private_group");

  // 执行前再次校验时间冲突（防止方案过期）
  const a_lockedSlots = JSON.parse(cachedGet("a_lockedSlots") || "{}");
  const b_confirmedSchedule_check = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
  let conflictPlayers = [];
  for (let g of groups) {
    for (let name of g.participants) {
      const uid = getUidByRoleName(platform, name);
      if (!uid) continue;
      const key = `${platform}:${uid}`;
      const locked = a_lockedSlots[key]?.[day] || [];
      if (locked.some(slot => timeOverlap(slot, time))) {
        conflictPlayers.push(`${name}（被锁定）`);
        continue;
      }
      const schedule = b_confirmedSchedule_check[key] || [];
      if (schedule.some(ev => ev.day === day && timeOverlap(ev.time, time))) {
        conflictPlayers.push(`${name}（已有安排）`);
      }
    }
  }
  if (conflictPlayers.length > 0) {
    seal.replyToSender(ctx, msg, `❌ 执行失败，方案可能已过期，以下玩家时间冲突：\n${conflictPlayers.join("\n")}\n请重新「。计划官约」`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const expireHours = getStorageInt("group_expire_hours", 48);
  const formatTime = (ts) => new Date(ts).toLocaleString("zh-CN", { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });

  let results = [];
  let failed  = [];

  for (let i = 0; i < groups.length; i++) {
    const { participants, place } = groups[i];

    // 验证参与者仍然存在
    const invalidP = participants.filter(n => !getUidByRoleName(platform, n));
    if (invalidP.length > 0) {
      failed.push(`第${i + 1}组：找不到玩家 ${invalidP.join("、")}`);
      continue;
    }

    // 分配群号
    const gid = await allocateGroup(platform, ctx, msg);
    if (!gid) {
      failed.push(`第${i + 1}组：暂无可用群号`);
      continue;
    }

    const acceptTime = Date.now();
    const expireTime = acceptTime + expireHours * 60 * 60 * 1000;

    // 更新日程（每次重新读写，避免多组之间覆盖）
    const bcs = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    for (let name of participants) {
      const uid = getUidByRoleName(platform, name);
      const key = `${platform}:${uid}`;
      if (!bcs[key]) bcs[key] = [];
      bcs[key].push({ day, time, partner: `官约（${participants.join("、")}）`, subtype: "官约", place, group: gid, status: "active" });
    }
    cachedSet("b_confirmedSchedule", JSON.stringify(bcs));

    // 记录群组过期信息
    const groupInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    groupInfo[gid] = { acceptTime, expireTime, participants, subtype: "官约", day, time, place };
    cachedSet("group_expire_info", JSON.stringify(groupInfo));

    // 改群名
    const groupNameTag = participants.length > 2 ? "多人" : participants.join("、");
    const finalGroupName = `官约 ${day} ${time} ${place} ${groupNameTag}`;
    const targetMsg = seal.newMessage();
    targetMsg.messageType = "group";
    targetMsg.groupId = `${platform}-Group:${gid}`;
    const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);
    setGroupName(targetCtx, targetMsg, gid, finalGroupName);

    // 向戏群发公告
    const execGuide = `\n\n修改时间 ➜ 修改时间线 ${day} 新时间\n不想参加 ➜ 拒绝时间线 ${gid}`;
    const execExpireStr = new Date(expireTime).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    seal.replyToSender(targetCtx, targetMsg, `🎖️ 官约已确认\n\n📅 ${day} ${time}\n📍 ${place}\n👥 参与者：${participants.join("、")}\n\n群号：${gid}\n有效至 ${execExpireStr}${execGuide}`);

    // 向每位参与者的绑定群发送通知
    for (let name of participants) {
      const uid = getUidByRoleName(platform, name);
      const boundGroupId = uid ? apg[platform]?.[uid]?.[1] : null;
      if (!boundGroupId) continue;
      const newmsg = seal.newMessage();
      newmsg.messageType = "group";
      newmsg.groupId = `${platform}-Group:${boundGroupId}`;
      const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
      seal.replyToSender(newctx, newmsg, `🎖️ 官约通知\n\n📅 ${day} ${time}\n📍 ${place}\n👥 参与者：${participants.join("、")}\n\n💬 官约群号：${gid}`);
    }

    // 启动计时器
    if (typeof initGroupTimer === "function") {
      initGroupTimer(platform, gid, "官约", participants, participants[0]);
    }

    recordMeetingAndAnnounce("官约", platform, ctx, ctx.endPoint);
    results.push(`第${i + 1}组 [${gid}]：${participants.join("、")} @ ${place}`);
  }

  // 清空方案
  cachedSet("a_quick_official_plan", "");

  let resp = `✅ 便捷官约执行完毕！\n━━━━━━━━━━━━━━\n`;
  if (results.length > 0) resp += results.join("\n");
  if (failed.length > 0)  resp += `\n\n❌ 以下组失败：\n${failed.join("\n")}`;
  seal.replyToSender(ctx, msg, resp);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["执行官约"] = cmd_execute_official;

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
        max_reports_per_day: 5, // 每人每天最大目击报告次数
        trigger_chance: 50, // 满足重叠条件后的触发概率 (%)
        include_ended_meetings: false, // 包含已结束的会议
        time_overlap_threshold: 0.3 // 时间重叠阈值（30%以上重叠触发）
    };
    const config = JSON.parse(cachedGet("sighting_system_config") || "{}");
    return { ...defaultConfig, ...config };
}

// 设置目击报告系统配置
function setSightingConfig(config) {
    cachedSet("sighting_system_config", JSON.stringify(config));
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
        enabled: false,
        require_key_by_default: false
    };
    const config = JSON.parse(cachedGet("place_system_config") || "{}");
    return { ...defaultConfig, ...config };
}

// 检查用户今日目击报告次数（以 uid 为 key）
function getUserSightingCountToday(platform, uid) {
    const today = new Date().toISOString().slice(0, 10);
    const sightingCount = JSON.parse(cachedGet("sighting_daily_count") || "{}");
    return (sightingCount[today] || {})[`${platform}:${uid}`] || 0;
}

// 增加用户今日目击报告次数（以 uid 为 key，同时清理过期日期）
function incrementUserSightingCountToday(platform, uid) {
    const today = new Date().toISOString().slice(0, 10);
    const sightingCount = JSON.parse(cachedGet("sighting_daily_count") || "{}");
    // 清理非今天的旧数据
    for (const date of Object.keys(sightingCount)) {
        if (date !== today) delete sightingCount[date];
    }
    if (!sightingCount[today]) sightingCount[today] = {};
    sightingCount[today][`${platform}:${uid}`] = (sightingCount[today][`${platform}:${uid}`] || 0) + 1;
    cachedSet("sighting_daily_count", JSON.stringify(sightingCount));
}

// 检查是否需要发送目击报告（随机概率 + 每日次数限制）
// roleName 参数：通过 getUidByRoleName 转换为 uid 后传入
function shouldSendSightingReport(platform, roleName) {
    const sightingConfig = getSightingConfig();
    const uid = getUidByRoleName(platform, roleName);

    // 检查今日次数（以 uid 为 key）
    const todayCount = uid ? getUserSightingCountToday(platform, uid) : 0;
    if (todayCount >= sightingConfig.max_reports_per_day) {
        return false;
    }
    
    const randomChance = Math.random() * 100 < (sightingConfig.trigger_chance ?? 50);
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
    if (minDuration === 0) return 0;
    return overlapMinutes / minDuration;
}

// 查找同一时间同一地点的其他约会
function findSimultaneousMeetings(platform, day, time, place, excludeGroupId = null) {
    const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const sightingConfig = getSightingConfig();

    // 按 groupId 去重，避免同一会议因多个参与者各有日程而重复出现
    const seenGroups = new Set();
    const simultaneousMeetings = [];

    for (const [userId, scheduleList] of Object.entries(b_confirmedSchedule)) {
        for (const meeting of scheduleList) {
            if (excludeGroupId && meeting.group === excludeGroupId) continue;
            if (meeting.day !== day || meeting.place !== place) continue;
            if (!meeting.partner) continue;

            // 已结束的会议按配置决定是否纳入
            if (!sightingConfig.include_ended_meetings && meeting.status === "ended") continue;

            const overlapRatio = calculateTimeOverlapRatio(meeting.time, time);
            if (overlapRatio < sightingConfig.time_overlap_threshold) continue;

            // 按 groupId 去重（同一群组只收录一次）
            const meetingGroupId = meeting.group;
            if (meetingGroupId && seenGroups.has(meetingGroupId)) continue;
            if (meetingGroupId) seenGroups.add(meetingGroupId);

            // 获取参与者
            const meetingParticipants = [];
            if (meetingGroupId && groupExpireInfo[meetingGroupId]?.participants?.length) {
                meetingParticipants.push(...groupExpireInfo[meetingGroupId].participants);
            } else {
                if (meeting.partner && meeting.partner !== "多人小群") meetingParticipants.push(meeting.partner);
                const [userPlatform, userUid] = userId.split(':');
                // 新结构：uid为key，roleName在value[0]
                const roleName = a_private_group[userPlatform]?.[userUid]?.[0];
                if (roleName && !meetingParticipants.includes(roleName)) meetingParticipants.push(roleName);
            }

            if (meetingParticipants.length === 0) continue;

            simultaneousMeetings.push({
                groupId: meetingGroupId,
                day: meeting.day,
                time: meeting.time,
                place: meeting.place,
                participants: [...new Set(meetingParticipants)],
                type: meeting.subtype || "未知",
                isEnded: meeting.status === "ended",
                overlapRatio
            });
        }
    }

    simultaneousMeetings.sort((a, b) => b.overlapRatio - a.overlapRatio);
    return simultaneousMeetings;
}
function sendSightingReports(platform, newMeetingInfo, simultaneousMeetings, ctx, msg) {
    if (!ctx || !ctx.endPoint) return;

    const sightingConfig = getSightingConfig();
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    if (!a_private_group[platform]) return;

    // 记录已触发过反向报告的 meeting，避免重复通知
    const processedReverseMeetings = new Set();

    for (const participant of newMeetingInfo.participants) {
        // 新结构：通过 roleName 反查 uid，再取 gid
        const participantUid = getUidByRoleName(platform, participant);
        const participantInfo = participantUid ? a_private_group[platform][participantUid] : null;
        if (!participantInfo?.[1]) continue;

        const targetGroupId = participantInfo[1];

        for (const otherMeeting of simultaneousMeetings) {
            // 跳过自己所在的会议
            if (otherMeeting.participants.includes(participant)) continue;

            // 检查是否还在每日上限内（含随机概率）
            if (!shouldSendSightingReport(platform, participant)) continue;

            const otherParticipantsText = otherMeeting.participants.join('、');
            const reportMessage = `👀 不会吧，你居然在 ${newMeetingInfo.place} 看见了 ${otherParticipantsText} 在一起！（时间：${otherMeeting.time}）`;

            const newMsg = seal.newMessage();
            newMsg.messageType = "group";
            newMsg.groupId = `${platform}-Group:${targetGroupId}`;
            const tempCtx = seal.createTempCtx(ctx.endPoint, newMsg);
            try {
                seal.replyToSender(tempCtx, newMsg, reportMessage);
            } catch (err) {
                console.error("[目击] 发送报告失败:", err);
            }

            if (participantUid) incrementUserSightingCountToday(platform, participantUid);

            if (sightingConfig.send_to_all && !processedReverseMeetings.has(otherMeeting.groupId)) {
                processedReverseMeetings.add(otherMeeting.groupId);
                sendCounterSightingReports(platform, otherMeeting, newMeetingInfo, ctx);
            }
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
    
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    
    if (!a_private_group[platform]) return;
    
    const sightingConfig = getSightingConfig();

    for (const participant of originalMeeting.participants) {
        // 新结构：通过 roleName 反查 uid，再取 gid
        const participantUid = getUidByRoleName(platform, participant);
        const participantInfo = participantUid ? a_private_group[platform][participantUid] : null;
        if (!participantInfo || !participantInfo[1]) {
            continue;
        }

        // 反向通知只检查每日上限，不再做随机判定（目击事件已由正向触发确认）
        if (participantUid) {
            const todayCount = getUserSightingCountToday(platform, participantUid);
            if (todayCount >= sightingConfig.max_reports_per_day) continue;
        }
        
        // 构建反向报告消息
        const newParticipantsText = newMeetingInfo.participants.join('、');
        
        const reportMessage =
            `👀 哎呀，你和${originalMeeting.participants.length > 1 ? '伙伴们' : '朋友'}在 ${originalMeeting.place} 的约会被 ${newParticipantsText} 看到了！（时间：${originalMeeting.time}）` ;
        
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
        
        // 增加目击次数（以 uid 为 key）
        if (participantUid) incrementUserSightingCountToday(platform, participantUid);
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
        timeout: 10800000,          // 180分钟，统一超时时间
        remind_interval: 10800000,  // 180分钟，统一提醒间隔
        auto_monitor_all_groups: true
    };
    
    const settings = JSON.parse(cachedGet("monitor_settings") || "{}");
    return { ...defaultSettings, ...settings };
}

/**
 * 保存监听设置
 */
function setMonitorSettings(settings) {
    cachedSet("monitor_settings", JSON.stringify(settings));
}

/**
 * 获取群组计时器
 */
function getGroupTimers() {
    return JSON.parse(cachedGet("group_timers") || "{}");
}

/**
 * 保存群组计时器
 */
function saveGroupTimers(timers) {
    cachedSet("group_timers", JSON.stringify(timers));
}

/**
 * 获取用户统计
 */
function getUserStats() {
    return JSON.parse(cachedGet("user_stats") || "{}");
}

function saveUserStats(stats) {
    cachedSet("user_stats", JSON.stringify(stats));
}

function getInteractionCounts() {
    return JSON.parse(cachedGet("interaction_counts") || "{}");
}

function saveInteractionCounts(counts) {
    cachedSet("interaction_counts", JSON.stringify(counts));
}

// type: "sms" | "gift" | "appt"；skipReceived=true 时只记发送方 sent，不记收件方 received
function recordInteractionStat(platform, fromRole, toRole, type, skipReceived = false) {
    if (!fromRole || !toRole || fromRole === toRole) return;
    const counts = getInteractionCounts();
    const fromKey = `${platform}:${fromRole}`;
    const toKey = `${platform}:${toRole}`;
    const sentField = `${type}_sent`;
    const recvField = `${type}_received`;

    if (!counts[fromKey]) counts[fromKey] = {};
    if (!counts[fromKey][sentField]) counts[fromKey][sentField] = {};
    counts[fromKey][sentField][toRole] = (counts[fromKey][sentField][toRole] || 0) + 1;

    if (!skipReceived) {
        if (!counts[toKey]) counts[toKey] = {};
        if (!counts[toKey][recvField]) counts[toKey][recvField] = {};
        counts[toKey][recvField][fromRole] = (counts[toKey][recvField][fromRole] || 0) + 1;
    }

    saveInteractionCounts(counts);
}

function getTop3Text(countMap) {
    if (!countMap || !Object.keys(countMap).length) return null;
    return Object.entries(countMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([name, count], i) => `  ${i + 1}. ${name}（${count}次）`)
        .join("\n");
}

function getSessionStats() {
    return JSON.parse(cachedGet("group_session_stats") || "{}");
}

function saveSessionStats(s) {
    cachedSet("group_session_stats", JSON.stringify(s));
}

// 结戏时把本群字数/段数归入本季累计，供「本场统计」跨场次汇总
function accumulateToSeasonStats(platform, gid) {
    const ss = getSessionStats();
    const groupStat = ss[gid];
    if (!groupStat) return;
    const acc = JSON.parse(cachedGet("season_player_stats") || "{}");
    if (!acc[platform]) acc[platform] = {};
    for (const [uid, stat] of Object.entries(groupStat)) {
        if (uid === "_startTime") continue;
        if (!acc[platform][uid]) acc[platform][uid] = { replies: 0, words: 0 };
        acc[platform][uid].replies += stat.replies || 0;
        acc[platform][uid].words   += stat.words   || 0;
    }
    cachedSet("season_player_stats", JSON.stringify(acc));
}

/**
 * 结戏时发放加成奖励（模版系统）
 */
function applyEndGameBonuses(ctx, msg, gid, platform) {
    const templates = JSON.parse(cachedGet("end_game_bonus_templates") || "[]");
    // group_expire_info[gid] 在结束流程里已先被删，改从 b_confirmedSchedule 读 subtype
    const _bSched = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    let groupSubtype = "";
    outer: for (const evList of Object.values(_bSched)) {
        for (const ev of evList) {
            if (ev.group === gid && ev.subtype) { groupSubtype = ev.subtype; break outer; }
        }
    }
    // 模版用用户可读名称，群记录用内部名称，做映射对齐
    const tplTypeToStored = { "私约": "私密", "心意": "心愿" };
    const enabled = templates.filter(t => {
        if (!t.enabled) return false;
        const tplType = t.subtype || "通用";
        if (tplType === "通用") return true;
        const resolved = tplTypeToStored[tplType] || tplType;
        return resolved === groupSubtype;
    });

    const sessionStats = getSessionStats();
    const groupStat = sessionStats[gid];
    const playerKeys = groupStat ? Object.keys(groupStat).filter(k => k !== "_startTime") : [];

    if (!enabled.length || !groupStat || !playerKeys.length) {
        accumulateToSeasonStats(platform, gid);
        delete sessionStats[gid];
        saveSessionStats(sessionStats);
        applyEndGameDraws(ctx, msg, gid, platform, playerKeys);
        return;
    }

    const reg = JSON.parse(cachedGet("item_registry") || "{}");
    const currencyByName = {};
    Object.values(reg).forEach(r => { if (r.type === "currency") currencyByName[r.name] = r.code; });

    const apg = JSON.parse(cachedGet("a_private_group") || "{}");

    // 查找结戏群对应的地点（供 location_draw 奖励使用）
    const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    let endGamePlace = null;
    for (const [, events] of Object.entries(b_confirmedSchedule)) {
        for (const event of events) {
            if (event.group === gid && event.place) { endGamePlace = event.place; break; }
        }
        if (endGamePlace) break;
    }
    const endGamePoolName = endGamePlace ? `${endGamePlace}池` : null;
    const poolDefs = seal.ext.find("changriRPG") ? JSON.parse(cachedGet("pool_definitions") || "{}") : null;
    let drawRecords = JSON.parse(cachedGet("player_draw_records") || "{}");
    let drawRecordsChanged = false;
    const currentDrawDay = cachedGet("global_days") || "";

    // 计算游戏耗时（分钟）
    const elapsedMinutes = groupStat._startTime
        ? Math.floor((Date.now() - groupStat._startTime) / 60000)
        : 0;

    // 条件评估
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

    // 概率池抽取
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

    // 发放单条奖励（playerUid 为 uid），返回显示文字
    function applyRewardItem(playerUid, rewardItem) {
        const { target, targetType, amount } = rewardItem;
        if (targetType === "currency" || targetType === "item") {
            const code = targetType === "currency"
                ? (currencyByName[target] || target.toUpperCase())
                : target.toUpperCase();
            addToInv_system(`${platform}:${playerUid}`, code, amount);
            return `${target}×${amount}`;
        } else {
            // attr：使用 uid-based profile key
            const profileKey = `${platform}:${playerUid}`;
            const profiles = JSON.parse(cachedGet("sys_char_profiles") || "{}");
            if (!profiles[profileKey]) profiles[profileKey] = {};
            const cur = parseInt(profiles[profileKey][target] || "0");
            profiles[profileKey][target] = String(cur + amount);
            cachedSet("sys_char_profiles", JSON.stringify(profiles));
            return `${target}+${amount}`;
        }
    }

    // 发放地点池抽取机会，返回显示文字（失败返回 null，附带原因到 failLines）
    function applyLocationDraw(playerUid, amount, failLines) {
        if (!endGamePoolName) {
            failLines.push("⚠️ 地点池抽取：本场未绑定地点，跳过");
            return null;
        }
        if (!poolDefs || !poolDefs[endGamePoolName]) {
            failLines.push(`⚠️ 地点池抽取：「${endGamePoolName}」不存在，跳过（可用「一键建池」创建）`);
            return null;
        }
        const recKey = `${platform}:${playerUid}`;
        if (!drawRecords[recKey]) drawRecords[recKey] = { day: "", used: {}, extra: {} };
        if (drawRecords[recKey].day !== currentDrawDay) { drawRecords[recKey].day = currentDrawDay; drawRecords[recKey].used = {}; }
        if (!drawRecords[recKey].extra) drawRecords[recKey].extra = {};
        drawRecords[recKey].extra[endGamePoolName] = (drawRecords[recKey].extra[endGamePoolName] || 0) + amount;
        drawRecordsChanged = true;
        return `「${endGamePoolName}」抽取×${amount}`;
    }

    const report = [];

    // playerKeys 中的 key 现在是 uid
    for (const playerUid of playerKeys) {
        const roleName = resolveUidToName(platform, playerUid);
        const stat = groupStat[playerUid];
        const avgWords = stat.replies > 0 ? Math.floor(stat.words / stat.replies) : 0;

        const getStatVal = (param) => {
            switch (param) {
                case "本场个人段数":       return stat.replies;
                case "本场个人总字数":     return stat.words;
                case "本场个人平均每段字数": return avgWords;
                case "结戏最多耗费时间":   return elapsedMinutes;
            }
            return 0;
        };

        const fixedLines = [];
        const poolLines = [];
        const failLines = [];

        function processReward(r) {
            const prob = (r.prob == null) ? 100 : r.prob;
            if (prob < 100 && Math.random() * 100 >= prob) return;
            if (!r.type || r.type === "fixed") {
                const result = applyRewardItem(playerUid, r);
                if (result) fixedLines.push(result);
            } else if (r.type === "pool" && r.items.length) {
                const drawn = drawFromPool(r);
                if (drawn) {
                    const result = applyRewardItem(playerUid, drawn);
                    if (result) {
                        const total = r.items.reduce((s, it) => s + it.weight, 0);
                        const pct = total > 0 ? Math.round(drawn.weight / total * 100) : 0;
                        poolLines.push(`${result}（${pct}%）`);
                    }
                }
            } else if (r.type === "location_draw") {
                const result = applyLocationDraw(playerUid, r.amount || 1, failLines);
                if (result) fixedLines.push(result);
            }
        }

        for (const tpl of enabled) {
            for (const group of tpl.groups) {
                if (group.op === "and") {
                    for (const block of group.blocks) {
                        const allMet = (block.conditions || []).every(c =>
                            evaluateCondition(c.op, getStatVal(c.param), c.value)
                        );
                        if (!allMet) continue;
                        for (const r of (block.rewards || [])) processReward(r);
                    }
                } else if (group.op === "or") {
                    for (const block of group.blocks) {
                        const allMet = (block.conditions || []).every(c =>
                            evaluateCondition(c.op, getStatVal(c.param), c.value)
                        );
                        if (!allMet) continue;
                        for (const r of (block.rewards || [])) processReward(r);
                        break;
                    }
                }
            }
        }

        const allLines = [...fixedLines, ...poolLines];
        if (!allLines.length && !failLines.length) continue;

        report.push(`【${roleName}】${allLines.join("、")}${failLines.length ? "\n  " + failLines.join("\n  ") : ""}`);

        // 个人群艾特通知（新结构：uid为key）
        const roleEntry = apg[platform]?.[playerUid];
        if (roleEntry && allLines.length) {
            const personalGroupId = roleEntry[1];
            const notifyMsg = seal.newMessage();
            notifyMsg.messageType = "group";
            notifyMsg.groupId = `${platform}-Group:${personalGroupId}`;
            const notifyCtx = seal.createTempCtx(ctx.endPoint, notifyMsg);
            const fixedText = fixedLines.join("、");
            const poolText = poolLines.length ? `\n🎲 概率奖励抽中：${poolLines.join("、")}` : "";
            const notice = `[CQ:at,qq=${playerUid}]\n🎁 结戏加成已发放：${fixedText}${poolText}\n💡 可使用「背包」查看道具与货币，「角色卡」查看属性变更。`;
            seal.replyToSender(notifyCtx, notifyMsg, notice);
        }
    }

    if (drawRecordsChanged) {
        cachedSet("player_draw_records", JSON.stringify(drawRecords));
    }

    // 清除本群本场记录（归档前先累加到季度累计）
    accumulateToSeasonStats(platform, gid);
    delete sessionStats[gid];
    saveSessionStats(sessionStats);

    if (report.length) {
        seal.replyToSender(ctx, msg, `🎁 结戏加成已发放：\n${report.join("\n")}`);
    }

    // 发放结戏抽取机会（sessionStats[gid] 已删，需传入 playerKeys）
    applyEndGameDraws(ctx, msg, gid, platform, playerKeys);
}

/**
 * 结戏时自动发放对应地点的抽取机会（需要先同步踩点池）
 */
function applyEndGameDraws(ctx, msg, gid, platform, playerKeys) {
    const drawConfig = JSON.parse(cachedGet("end_game_draw_config") || "{}");
    if (!drawConfig.enabled) return;

    const chance = drawConfig.chance ?? 100; // 触发概率 0-100
    const count  = drawConfig.count  ?? 1;  // 每人发放次数

    // 从 b_confirmedSchedule 获取该群的地点
    const b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    let place = null;
    for (const [, events] of Object.entries(b_confirmedSchedule)) {
        for (const event of events) {
            if (event.group === gid && event.place) { place = event.place; break; }
        }
        if (place) break;
    }
    if (!place) return;

    const poolName = `${place}池`;

    // 调用方在删除 sessionStats[gid] 前传入 playerKeys；无传参时兜底读 storage（不含 _startTime）
    const participants = playerKeys
        ? playerKeys.filter(k => k !== "_startTime")
        : Object.keys((getSessionStats()[gid]) || {}).filter(k => k !== "_startTime");
    if (!participants.length) return;

    if (!seal.ext.find("changriRPG")) return;

    const records = JSON.parse(cachedGet("player_draw_records") || "{}");
    const awardedList = [];

    const apgPlatform = JSON.parse(cachedGet("a_private_group") || "{}")[platform] || {};
    for (const uid of participants) {
        if (uid === "_startTime") continue;
        // 概率检定
        if (Math.random() * 100 >= chance) continue;

        const key = `${platform}:${uid}`;
        let rec = records[key] || { day: "", used: {}, extra: {} };
        const currentDay = cachedGet("global_days") || "";
        if (rec.day !== currentDay) { rec.day = currentDay; rec.used = {}; }
        if (!rec.extra) rec.extra = {};

        rec.extra[poolName] = (rec.extra[poolName] || 0) + count;
        records[key] = rec;
        awardedList.push(apgPlatform[uid]?.[0] || uid);
    }

    if (awardedList.length) {
        cachedSet("player_draw_records", JSON.stringify(records));
        const chanceText = chance < 100 ? `（${chance}%概率触发）` : "";
        seal.replyToSender(ctx, msg, `🎰 结戏抽取${chanceText}：已为 ${awardedList.join("、")} 发放「${poolName}」抽取机会 ×${count}`);
    }
}

/**
 * 初始化群组计时器（修正版）
 * 修改：过滤掉已拒绝的参与者
 */
function initGroupTimer(platform, groupId, subtype, participants, initiator) {
    const settings = getMonitorSettings();
    if (!settings.enabled) return;
    
    // 获取多人邀约状态，过滤掉已拒绝的参与者
    const b_MultiGroupRequest = JSON.parse(cachedGet("b_MultiGroupRequest") || "{}");
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
            // 只包括已接受和待回应的参与者（status 未设置时为 undefined，用 == null 同时匹配 null/undefined）
            return status === "accepted" || status == null;
        });
    }
    
    // 如果没有活跃参与者，不创建计时器
    if (activeParticipants.length === 0) return;
    
    const timers = getGroupTimers();
    const now = Date.now();
    
    // 获取超时时间：优先使用服务端下发的分场次配置，其次单一 timeout，最后兜底默认
    const _subtypeTimeoutKey = { "电话": "timeout_phone", "私密": "timeout_private", "心愿": "timeout_wish", "官约": "timeout_official" }[subtype];
    const getTimeout = () => (_subtypeTimeoutKey && settings[_subtypeTimeoutKey]) || settings.timeout || 10800000;
    
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
        timeoutDuration: getTimeout(),
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
            isInitiator: true,
            sessionReplies: 0,
            sessionWords: 0
        };

        const receiver = activeParticipants.find(p => p !== initiator);
        if (receiver) {
            timerData.timerStatus[receiver] = {
                status: "waiting",
                startTime: null,
                repliedTime: null,
                wordCount: 0,
                remindedTimes: 0,
                isInitiator: false,
                sessionReplies: 0,
                sessionWords: 0
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
                isInitiator: isInitiator,
                sessionReplies: 0,
                sessionWords: 0
            };
        });
    }
    
    timers[groupId] = timerData;
    saveGroupTimers(timers);

    // 记录游戏真正开始时间，供结戏加成的"结戏最多耗费时间"使用
    // （计时器在结戏前会被清理，所以需要提前写入 sessionStats）
    // 强制重置：上一场若未走「结束私约/强结」流程，残留的 _startTime 和字数
    // 会让新场次合并进旧 session_id 并继承旧统计，必须清掉
    const _initSS = getSessionStats();
    _initSS[groupId] = { _startTime: now };
    saveSessionStats(_initSS);

    console.log(`[监听系统] 初始化群组 ${groupId} 的计时器，参与者：${activeParticipants.join(',')}，模式：${isTwoPerson ? '轮流模式' : '独立模式'}`);
}


/**
 * 处理回复（监听消息时调用）
 * 已集成：计时状态更新、字数校验、转发逻辑、以及写帖进度计数
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
        console.warn(`[监听系统] 处理失败: 角色 [${roleName}] 不在参与者名单中`);
        return false;
    }

    // RP存档（不复盘模式跳过 entry 记录）
    if (isArchiveEnabled() && getSeasonMode() !== "no_review") {
        const _archiveSS = getSessionStats()[groupId] || {};
        const _startTs = _archiveSS._startTime || Date.now();
        const _expireInfo = JSON.parse(cachedGet("group_expire_info") || "{}")[groupId] || {};
        const _gameDay = _expireInfo.day || timer.day || cachedGet("global_days") || "";
        const _npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
        const _logTypes = ["私密", "电话", "官约", "心愿"];
        const _archivePayload = {
            session_id: `${groupId}_${_startTs}`,
            group_id:   groupId,
            role_name:  roleName,
            is_npc:     _npcList.includes(roleName),
            game_day:   _gameDay,
            game_time:  _expireInfo.time  || timer.time  || "",
            place:      _expireInfo.place || timer.place || "",
            subtype:    timer.subtype || "",
            timestamp:  Date.now()
        };

        // 统一格式要求：所有场次（含电话、NPC）首行必须是角色名，闲聊不入档
        let _archivedContent = null;
        const _arcLines = message.split("\n");
        const _arcFirst = _arcLines[0].trim();
        if (_arcFirst === roleName) {
            const content = _arcLines.slice(1).join("\n").trim();
            if (content) {
                postToArchive("/api/rp", { ..._archivePayload, content });
                _archivedContent = content;
                if (_logTypes.includes(timer.subtype))
                    console.log(`[存档] ${timer.subtype} | ${_gameDay} | ${roleName}${_npcList.includes(roleName) ? "(NPC)" : ""} | ${content.slice(0,30)}…`);
            }
        }

        // 字数统计：凡存档成功的回复（非NPC）都累计，不依赖 timing 状态
        // 10分钟内同一人同一群再发且 Jaccard 相似度 ≥ 0.6，视为撤回重发：替换字数而非新增
        if (_archivedContent && !_npcList.includes(roleName)) {
            const _wc = countWords(_archivedContent);
            const _archiveUid = getUidByRoleName(platform, roleName);
            if (_archiveUid) {
                const _ssArc = getSessionStats();
                if (!_ssArc[groupId]) _ssArc[groupId] = {};
                if (!_ssArc[groupId]._startTime) _ssArc[groupId]._startTime = _startTs;
                if (!_ssArc[groupId][_archiveUid]) _ssArc[groupId][_archiveUid] = { replies: 0, words: 0 };

                // 撤回重发检测
                const _cacheKey = `reply_cache__${groupId}__${_archiveUid}`;
                const _cached = (() => { try { return JSON.parse(cachedGet(_cacheKey) || "null"); } catch(e) { return null; } })();
                const _now = Date.now();
                let _isRedo = false;
                if (_cached && (_now - _cached.ts) <= 600000) {
                    // Jaccard 相似度（字符 bigram）
                    const bigrams = s => {
                        const set = new Set();
                        for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
                        return set;
                    };
                    const a = bigrams(_cached.content), b = bigrams(_archivedContent);
                    const inter = [...a].filter(x => b.has(x)).length;
                    const union = new Set([...a, ...b]).size;
                    const jaccard = union > 0 ? inter / union : 0;
                    if (jaccard >= 0.6) {
                        // 替换：减去旧字数，不新增段数
                        _ssArc[groupId][_archiveUid].words = Math.max(0,
                            _ssArc[groupId][_archiveUid].words - _cached.words) + _wc;
                        _isRedo = true;
                        console.log(`[字数] ${roleName} | 群${groupId} | 撤回重发(Jaccard=${jaccard.toFixed(2)}) 替换 ${_cached.words}→${_wc}字`);
                    }
                }
                if (!_isRedo) {
                    _ssArc[groupId][_archiveUid].replies += 1;
                    _ssArc[groupId][_archiveUid].words += _wc;
                    console.log(`[字数] ${roleName} | 群${groupId} | +${_wc}字 +1段 | 累计${_ssArc[groupId][_archiveUid].words}字/${_ssArc[groupId][_archiveUid].replies}段`);
                }

                saveSessionStats(_ssArc);
                // 更新缓存（无论替换还是新增，都以本次内容作为下次比对基准）
                cachedSet(_cacheKey, JSON.stringify({ content: _archivedContent, words: _wc, ts: _now }));
            }
        }
    }

    // 1. 检查计时状态
    // 独立模式：任何人随时可发，不拦截
    // 轮流模式：waiting（对方回合）和 timing（自己回合）都允许；replied 才拦截（已回等对方）
    if (timer.timerMode === "turn_taking") {
        if (roleStatus.status === "replied") return false;
    }

    // 2. 字数（与存档段同口径：首行是角色名则去掉首行，电话也不例外）
    // 首行不是角色名视为闲聊，不计入统计和进度
    const _wLines = message.split("\n");
    if (_wLines[0].trim() !== roleName) return false;
    const _wContent = _wLines.slice(1).join("\n").trim();
    const wordCount = countWords(_wContent);

    // --- 开始更新数据 ---

    // 3. 记录回复状态
    roleStatus.status = "replied";
    roleStatus.repliedTime = Date.now();
    roleStatus.wordCount = wordCount;

    // 4. 更新用户统计（新签名：传 uid）
    const roleUid = getUidByRoleName(platform, roleName);
    updateUserStats(platform, roleUid || roleName, wordCount, roleStatus.startTime, roleStatus.repliedTime);

    // 5. 【新增逻辑】记录写帖进度 (替代原来的 .写了 指令)
    // 获取该角色的 UID（新结构：直接使用 getUidByRoleName 结果）
    const uid = roleUid;

    if (uid) {
        const progress = JSON.parse(cachedGet("group_write_progress") || "{}");
        // 这里的 groupId 是当前互动的群号（如 001_1）
        if (!progress[groupId]) progress[groupId] = {};
        progress[groupId][uid] = (progress[groupId][uid] || 0) + 1;
        cachedSet("group_write_progress", JSON.stringify(progress));
        console.log(`[监听系统] 记录进度: ${roleName}(${uid}) 在群 ${groupId} 回复数 +1`);
    }

    // 6. session 统计已在存档段累计，此处仅同步写入计时器（用于展示）
    const sessionUid = roleUid;

    // 同步写入计时器，方便查看计时器时直接读取
    if (!roleStatus.sessionReplies) roleStatus.sessionReplies = 0;
    if (!roleStatus.sessionWords) roleStatus.sessionWords = 0;
    roleStatus.sessionReplies += 1;
    roleStatus.sessionWords += wordCount;

    // 实时推送本场 stats 到存档服务器（自动更新统计页面 + 玩家数据库）
    // NPC 回复不触发 stats 推送，避免污染数据分析
    const _npcListStats = JSON.parse(cachedGet("a_npc_list") || "[]");
    if (isArchiveEnabled() && sessionUid && !_npcListStats.includes(roleName)) {
        const _ss2 = getSessionStats()[groupId] || {};
        const _startTs2 = _ss2._startTime || Date.now();
        const liveStats = {};
        (timer.participants || []).forEach(rn => {
            const ruid = getUidByRoleName(platform, rn);
            if (ruid && _ss2[ruid]) {
                liveStats[rn] = { replies: _ss2[ruid].replies || 0, words: _ss2[ruid].words || 0 };
            }
        });
        const livePlayers = (timer.participants || []).map(rn => {
            const ruid = getUidByRoleName(platform, rn);
            return ruid ? { qq: ruid, role_name: rn, is_npc: _npcListStats.includes(rn) } : null;
        }).filter(Boolean);
        const _expireInfo2 = JSON.parse(cachedGet("group_expire_info") || "{}")[groupId] || {};
        postToArchive("/api/session_stats", {
            session_id: `${groupId}_${_startTs2}`,
            group_id:   groupId,
            game_day:   _expireInfo2.day  || timer.day   || cachedGet("global_days") || "",
            game_time:  _expireInfo2.time || timer.time  || "",
            place:      _expireInfo2.place|| timer.place || "",
            subtype:    timer.subtype || "",
            stats:      liveStats,
            players:    livePlayers,
        });
    }

    // 7. 处理计时器流转 (轮流模式/独立模式)
    const _flowNow = Date.now();
    if (timer.timerMode === "turn_taking") {
        // 轮流模式：发言方 → replied，对方 → timing（无论谁抢先开头都成立）
        const otherParticipant = timer.participants.find(p => p !== roleName);
        if (otherParticipant) {
            const otherStatus = timer.timerStatus[otherParticipant];
            if (otherStatus) {
                otherStatus.status = "timing";
                otherStatus.startTime = _flowNow;
                otherStatus.repliedTime = null;
                otherStatus.wordCount = 0;
                otherStatus.remindedTimes = 0;
            }
        }
    } else {
        // 独立模式：任何人发言后，其余所有人变 timing（开始计时等回复）
        timer.participants.forEach(p => {
            if (p === roleName) return;
            const ps = timer.timerStatus[p];
            if (ps) {
                ps.status = "timing";
                ps.startTime = _flowNow;
                ps.repliedTime = null;
                ps.wordCount = 0;
                ps.remindedTimes = 0;
            }
        });
    }

    saveGroupTimers(timers);
    return true; // 返回 true 表示处理成功，外部逻辑会执行 handleReply 转发
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
 * 更新用户统计
 */
/**
 * 更新用户统计（增强版：包含平均字数与平均时长）
 */
// uid 参数为玩家 uid（非 roleName），key 改为 ${platform}:${uid}
function updateUserStats(platform, uid, wordCount, startTime, repliedTime) {
    const stats = getUserStats();
    const key = `${platform}:${uid}`;

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
    userStat.avgReplyTimeMin = parseFloat((userStat.totalReplyTimeMs / userStat.totalReplies / 60000).toFixed(1));

    // 4. 更新细分类型统计（uid 为 key）
    if (!userStat.subtypeStats[platform]) userStat.subtypeStats[platform] = {};
    if (!userStat.subtypeStats[platform][uid]) {
        userStat.subtypeStats[platform][uid] = {
            replies: 0,
            totalWords: 0,
            totalTime: 0,
            fastestReply: null,
            slowestReply: null
        };
    }

    const sub = userStat.subtypeStats[platform][uid];
    sub.replies += 1;
    sub.totalWords += wordCount;
    sub.totalTime += replyTimeMs;

    // 记录最快/最慢纪录（分钟）
    const currentReplyMin = Math.round(replyTimeMs / 60000);
    if (!sub.fastestReply || currentReplyMin < sub.fastestReply) sub.fastestReply = currentReplyMin;
    if (!sub.slowestReply || currentReplyMin > sub.slowestReply) sub.slowestReply = currentReplyMin;

    saveUserStats(stats);

    console.log(`[统计更新] uid=${uid}: 本次回复${wordCount}字, 耗时${currentReplyMin}分 | 累计平均: ${userStat.avgWords}字, ${userStat.avgReplyTimeMin}分`);
}

/**
 * 获取提醒间隔
 */
function getRemindInterval() {
    return getMonitorSettings().remind_interval;
}

/**
 * 发送提醒
 */
function sendReminder(platform, groupId, roleName, subtype, elapsedTime,ctx) {
    // 获取角色绑定的群（新结构：通过 roleName 反查 uid）
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");
    const roleUid = getUidByRoleName(platform, roleName);
    const roleGroupId = roleUid ? a_private_group[platform]?.[roleUid]?.[1] : null;
    
    if (!roleGroupId) return;
    
    // 计算超时时间
    const hours = Math.floor(elapsedTime / 3600000);
    const minutes = Math.floor((elapsedTime % 3600000) / 60000);
    
    // 发送到角色绑定的群
    const msg1 = seal.newMessage();
    msg1.messageType = "group";
    msg1.groupId = `${platform}-Group:${roleGroupId}`;
    const ctx1 = seal.createTempCtx(ctx.endPoint, msg1);

    seal.replyToSender(ctx1, msg1,
        `⏰ 提醒：你在 ${subtype} 群 ${groupId} 中已超过 ${hours}小时${minutes}分钟未回复\n请尽快回复！`);

    // 发送到群组本身
    const msg2 = seal.newMessage();
    msg2.messageType = "group";
    msg2.groupId = `${platform}-Group:${groupId}`;
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
    const activeGroupsStr = cachedGet("group") || "[]";
    let activeGroups = JSON.parse(activeGroupsStr);
    const currentGroupId = ctx.group.groupId.replace(/[^\d]/g, "");
    
    if (!activeGroups.includes(currentGroupId)) {
        seal.replyToSender(ctx, msg, `⚠️ 本群(${currentGroupId})未在系统中注册，无法转发。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 暂存目标群号和当前群名，供 ws 回调逻辑提取
    cachedSet("temp_target_gid", targetGid.toString().replace(/[^\d]/g, ""));
    cachedSet("temp_source_group_name", ctx.group.groupName || "未知群聊");

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
    return ws(
        { action: "delete_msg", params: { message_id: parseInt(wdId) } },
        ctx, msg,
        "✅ 已撤回。",
        "❌ 撤回失败（消息不在 LLOneBot 缓存中）"
    );
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
    const platform = msg.platform;
    const _rawUid = msg.sender.userId.replace(`${platform}:`, '');
    const uid = getPrimaryUid(platform, _rawUid); // 辅助账号自动解析为主账号 uid
    const groupId = msg.groupId.replace(`${platform}-Group:`, ''), isAdmin = isUserAdmin(ctx, msg);
    const getS = (k) => JSON.parse(cachedGet(k) || (k.includes("list") || k.includes("presets") || k.includes("projects") ? "[]" : "{}"));

    // 1. 回复卡片逻辑 (撤回/点歌/复盘)
    const replyMatch = raw.match(/\[CQ:reply,id=(\-?\d+)\]/);
    if (replyMatch) {
        const wdId = Number(replyMatch[1]);
        if (raw.includes("撤回")) return withdrawMsg(ctx, msg, wdId);
        if (raw.includes("点歌")) {
            const gid = cachedGet("song_group_id"), dM = raw.match(/点歌人[:：]\s*(.*?)(?=\s|,|，|留言|$)/), lM = raw.match(/留言[:：]\s*(.*)/);
            if (!gid || !dM || !lM) return seal.replyToSender(ctx, msg, !gid ? "❌ 未配置戏群" : "⚠️ 格式错误\n正确用法：回复音乐卡片，消息内容写\n点歌人：名字 留言：内容");
            ["temp_target_gid", "temp_task_type", "temp_song_dgr", "temp_song_ly"].forEach((k, i) => cachedSet(k, [gid, "song", dM[1].trim(), lM[1].trim()][i]));
            return ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg, null, "❌ 点歌失败：LLOneBot 未能读取该消息（可能不在缓存中）。");
        }
        if (raw.includes("转发复盘")) {
            return seal.replyToSender(ctx, msg, "📋 当前版本无需转发复盘，直接发送「结束私约」退群即可。");
        }
    }

    // 2.5 点歌引导（未回复卡片时单独发点歌）
    if (raw === "点歌") {
        return seal.replyToSender(ctx, msg, "🎵 点歌用法：回复一张音乐卡片，消息内容写\n点歌人：名字 留言：内容\n例：点歌人：张三 留言：送给你的歌");
    }


    const letM = raw.match(/^(.+?)?短信\s*(.+?)\s+([\s\S]+)$/);
    if (letM) {
        // 【修改点】单独读取开关状态
        const allowCustom = cachedGet("allow_custom_letter_sign") === "true";
        
        const priv = getS("a_private_group")[platform] || {};
        let snd = "";

        if (allowCustom && letM[1]) {
            // 允许自定义且写了 A 部分，直接取 A
            snd = letM[1].trim();
        } else {
            // 不允许自定义或没写 A，按原逻辑自动识别或校验
            snd = letM[1] ? letM[1].trim() : getRoleName(ctx, msg);
        }

        // 【修改点】如果开启了自定义，不再强制要求 snd 必须存在于 priv 绑定中
        if (snd && (allowCustom || Object.values(priv).some(v => v[0] === snd))) {
            return handleNaturalChaosLetter(ctx, msg, platform, snd, letM[2].trim(), letM[3].trim());
        } else {
            return seal.replyToSender(ctx, msg, "❌ 角色识别失败");
        }
    } else if (/^(.+?)?短信$/.test(raw)) {
        return seal.replyToSender(ctx, msg, "💌 短信格式：[署名]短信 收信人 内容\n例：短信 李四 你好！\n例：张三短信 李四 你好！");
    }

    // 4. 约会/邀约/微信/心愿/发帖/心动信（无指令前缀触发）
    const makeFakeCmdArgs = (parts) => ({
        getArgN: (n) => parts[n - 1] || "",
        args: parts
    });

    if (raw.startsWith("电话")) {
        const rest = raw.slice(2).trim();
        return cmd_phone.solve(ctx, msg, makeFakeCmdArgs(rest ? rest.split(/\s+/) : []));
    }

    const _matchedAlias = getPrivateAliases().find(a => a.trigger && raw.startsWith(a.trigger));
    if (_matchedAlias) {
        const rest = raw.slice(_matchedAlias.trigger.length).trim();
        return cmd_appointment_private.solve(ctx, msg, makeFakeCmdArgs(rest ? rest.split(/\s+/) : []), _matchedAlias);
    }

    if (raw.startsWith("私约")) {
        const rest = raw.slice(2).trim();
        return cmd_appointment_private.solve(ctx, msg, makeFakeCmdArgs(rest ? rest.split(/\s+/) : []));
    }

    if (raw.startsWith("微信")) {
        const rest = raw.slice(2).trim();
        return cmd_wechat.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw.startsWith("发帖")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_post_forum.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("回复帖子")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_reply_post.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("查看帖子")) {
        const rest = raw.slice(4).trim();
        return cmd_view_posts.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
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
            const rolesStorageCheck = store.get("a_private_group")[platform] || {};
            if (rolesStorageCheck[extraQQ]) return seal.replyToSender(ctx, msg, `❌ 该账号已是主账号（角色：${rolesStorageCheck[extraQQ][0]}），无法绑定为额外账号`);
            extras[extraKey] = uid;
            store.set("extra_accounts", extras);

            // 清理辅助账号的商城/图鉴数据，只保留主账号的
            // 1. 删除辅助账号的 gift_sightings（uid-based key）
            const sightings = JSON.parse(cachedGet("gift_sightings") || "{}");
            const extraSightingKey = `${platform}:${extraQQ}`;
            if (sightings[extraSightingKey]) {
                delete sightings[extraSightingKey];
                cachedSet("gift_sightings", JSON.stringify(sightings));
            }
            // 2. 删除辅助账号的 global_inventories（roleName-based key）
            // 找出辅助账号在 a_private_group 中绑定的角色名
            const rolesStorage = store.get("a_private_group")[platform] || {};
            const extraRoleName = Object.entries(rolesStorage).find(([, v]) => v[0] === extraQQ)?.[0];
            if (extraRoleName) {
                const invs = JSON.parse(cachedGet("global_inventories") || "{}");
                const extraInvKey = `${platform}:${extraRoleName}`;
                if (invs[extraInvKey]) {
                    delete invs[extraInvKey];
                    cachedSet("global_inventories", JSON.stringify(invs));
                }
            }
            // 3. 删除辅助账号的 shop_personal_display（uid-based key，抽卡进度）
            const spd = JSON.parse(cachedGet("shop_personal_display") || "{}");
            if (spd[extraSightingKey]) {
                delete spd[extraSightingKey];
                cachedSet("shop_personal_display", JSON.stringify(spd));
            }

            return seal.replyToSender(ctx, msg, `✅ 已将 ${extraQQ} 绑定为「${selfRoleName}」的额外账号（辅助账号的商城/图鉴数据已清除）`);
        }
        // 查看自己的额外账号
        const myExtras = Object.entries(extras).filter(([, v]) => v === uid).map(([k]) => k.replace(`${platform}:`, ""));
        return seal.replyToSender(ctx, msg, myExtras.length ? `📱 你的额外账号：\n${myExtras.join("\n")}` : "📭 暂无额外账号");
    }

    // 4.8 角色档案修改（无前缀）
    if (raw.startsWith("修改名字") || raw.startsWith("修改姓名")) {
        const newName = raw.slice(4).trim();
        if (!newName) return seal.replyToSender(ctx, msg, "格式：修改名字 新名字");
        return doRenameRole(ctx, msg, newName);
    }

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

    if (raw === "角色卡") {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
        const roleKey = `${platform}:${uid}`;
        const prof = getCharProfile(platform, roleName);

        // 基础信息
        const genderText = prof.gender === "男" ? "👨 男" : "👩 女";
        const ageText = prof.age !== undefined && prof.age !== null ? `${prof.age}岁` : "未设置";

        // ── 属性 ──────────────────────────────────────────────
        const attrLines = [];
        try {
            const attrDefs = JSON.parse(cachedGet("rpg_attr_defs") || "{}");
            const charAttrs = JSON.parse(cachedGet("sys_character_attrs") || "{}");
            // 新结构：charAttrs 以 uid 为 key
            const roleAttrs = charAttrs[uid] || {};
            const BAR = 6;
            for (const [name, def] of Object.entries(attrDefs)) {
                const val = roleAttrs[name] ?? (def.default ?? 0);
                if (def.max !== null && def.max !== undefined && def.min !== null) {
                    const pct = def.max === def.min ? 1 : (val - def.min) / (def.max - def.min);
                    const filled = Math.round(Math.max(0, Math.min(1, pct)) * BAR);
                    attrLines.push(`【${name}】${"▓".repeat(filled)}${"░".repeat(BAR - filled)} ${val}/${def.max}`);
                } else {
                    attrLines.push(`【${name}】${val}`);
                }
            }
        } catch(e) {}

        // ── 装备 ──────────────────────────────────────────────
        const equipLines = [];
        try {
            const allEquips = JSON.parse(cachedGet("player_equipments") || "{}");
            const reg = JSON.parse(cachedGet("item_registry") || "{}");
            const playerEquips = allEquips[roleKey] || {};
            const slots = JSON.parse(cachedGet("equipment_slots") || "[]");
            const slotNames = JSON.parse(cachedGet("equipment_slot_names") || "{}");
            const defaultNames = { head:"头部", chest:"胸部", hand:"手部", leg:"腿部", foot:"脚部" };
            const defaultEmoji = { head:"🎩", chest:"🛡️", hand:"⚔️", leg:"👖", foot:"👢" };
            for (const slot of (slots.length ? slots : ["head","chest","hand","leg","foot"])) {
                const e = playerEquips[slot];
                if (e && e.code) {
                    const displayName = slotNames[slot] || defaultNames[slot] || slot;
                    const emoji = defaultEmoji[slot] || "📦";
                    equipLines.push(`${emoji}${displayName}：${reg[e.code]?.name || e.code}`);
                }
            }
        } catch(e) {}

        // ── 货币 ──────────────────────────────────────────────
        const currLines = [];
        try {
            const invs = JSON.parse(cachedGet("global_inventories") || "{}");
            const reg = JSON.parse(cachedGet("item_registry") || "{}");
            for (const e of (invs[roleKey] || [])) {
                if (e.count > 0 && reg[e.code]?.type === "currency") {
                    currLines.push(`${reg[e.code].name}：${e.count}`);
                }
            }
        } catch(e) {}

        // ── 拼接 ──────────────────────────────────────────────
        const out = [];
        out.push(`★━━━━━━━━━━★`);
        out.push(`🃏 【${roleName}】`);
        out.push(`★━━━━━━━━━━★`);
        out.push(``);
        out.push(`${genderText} · ${ageText}`);
        out.push(`🌸 皮相：${prof.look || "未设置"}`);
        if (prof.bio) out.push(`✏️ ${prof.bio}`);
        if (attrLines.length) { out.push(``); out.push(`📊 战斗属性`); out.push(...attrLines); }
        if (equipLines.length) { out.push(``); out.push(`⚔️ 装备`); out.push(...equipLines); }
        if (currLines.length) { out.push(``); out.push(`💰 货币`); out.push(...currLines); }
        out.push(``);
        out.push(`★━━━━━━━━━━★`);

        seal.replyToSender(ctx, msg, out.join("\n"));
        return seal.ext.newCmdExecuteResult(true);
    }

    // 4.9 拍卖系统（无前缀）
    if (raw === "查看拍卖") {
        settleExpiredAuctions(ctx, msg);
        const auctions = getAuctions();
        const settings = getAuctionSettings();
        const now = Date.now();
        const activeItems = Object.values(auctions).filter(a => a.status === "active");
        if (activeItems.length === 0) return seal.replyToSender(ctx, msg, "📭 当前没有进行中的拍卖");
        const gid = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
        const bot = "长日将尽", uin = "10001";
        const nodes = [
            { type: "node", data: { name: bot, uin, content: `🔨 当前拍卖（${activeItems.length}件）\n${"━".repeat(14)}\n货币：${settings.currency}\n发送「实名出价 价格 编号」或「匿名出价 价格 编号」参与竞拍` } },
            ...activeItems.map(item => {
                const remain = Math.max(0, item.endTime - now);
                const remainText = remain > 3600000 ? `${Math.ceil(remain / 3600000)}小时` : `${Math.ceil(remain / 60000)}分钟`;
                const topBid = item.bids[0];
                let bidLine = topBid
                    ? `当前出价：${topBid.amount} ${settings.currency}` + (settings.showTopBidder && !topBid.isAnon ? `（${topBid.roleName}）` : "")
                    : `起拍价：${item.startPrice} ${settings.currency}（尚无出价）`;
                return { type: "node", data: { name: bot, uin, content: `${item.id} 「${item.name}」\n📝 ${item.desc}\n💰 起拍：${item.startPrice} | 最低加价：${item.minIncrement}\n${bidLine}\n⏰ 剩余：${remainText}` } };
            })
        ];
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: nodes } }, ctx, msg, "");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (raw.startsWith("实名出价") || raw.startsWith("匿名出价")) {
        const isAnon = raw.startsWith("匿名出价");
        const rest = raw.slice(4).trim();
        const parts = rest.split(/\s+/);
        const amountStr = parts[0], auctionId = parts[1];
        if (!amountStr || !auctionId) return seal.replyToSender(ctx, msg, `格式：${isAnon ? "匿名" : "实名"}出价 价格 编号\n例：${isAnon ? "匿名" : "实名"}出价 150 #1`);
        const amount = parseInt(amountStr);
        if (isNaN(amount) || amount <= 0) return seal.replyToSender(ctx, msg, "❌ 出价必须是正整数");

        settleExpiredAuctions(ctx, msg);
        const auctions = getAuctions();
        const settings = getAuctionSettings();
        const item = auctions[auctionId];
        if (!item) return seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${auctionId}`);
        if (item.status !== "active") return seal.replyToSender(ctx, msg, "❌ 该物品拍卖已结束");
        if (Date.now() > item.endTime) return seal.replyToSender(ctx, msg, "❌ 该拍卖已到期，请等待管理员结算");
        if (isAnon && !settings.allowAnon) return seal.replyToSender(ctx, msg, "❌ 当前不允许匿名出价");

        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色");

        const topBid = item.bids[0];
        const minBid = topBid ? topBid.amount + item.minIncrement : item.startPrice;
        if (amount < minBid) return seal.replyToSender(ctx, msg, `❌ 出价不足！最低应出 ${minBid} ${settings.currency}（${topBid ? `当前最高${topBid.amount}+最低加价${item.minIncrement}` : `起拍价${item.startPrice}`}）`);

        const currencyItem = findCurrencyByName_rpg(settings.currency);
        let balance;
        if (currencyItem) {
            balance = getInvCount_rpg(`${platform}:${uid}`, currencyItem.code);
        } else {
            const attrs = JSON.parse(cachedGet("sys_character_attrs") || "{}");
            // 新结构：charAttrs 以 uid 为 key
            balance = attrs[uid]?.[settings.currency] || 0;
        }
        if (balance < amount) return seal.replyToSender(ctx, msg, `❌ ${settings.currency}不足！需要 ${amount}，当前 ${balance}`);

        // 同一人只保留最新出价
        item.bids = item.bids.filter(b => b.roleName !== roleName);
        item.bids.push({ roleName, uid, amount, isAnon, time: Date.now() });
        item.bids.sort((a, b) => b.amount - a.amount);
        saveAuctions(auctions);

        const bidderDisplay = isAnon ? "匿名玩家" : `「${roleName}」`;
        seal.replyToSender(ctx, msg, `✅ 出价成功！${auctionId} 「${item.name}」\n${bidderDisplay} 出价 ${amount} ${settings.currency}`);
        if (settings.broadcast) {
            const top = item.bids[0];
            const topDisplay = settings.showTopBidder && !top.isAnon ? `「${top.roleName}」` : "匿名";
            _notifyAuction(ctx, msg, settings, `🔔 出价播报 | ${auctionId} 「${item.name}」\n💰 最新出价：${top.amount} ${settings.currency}${settings.showTopBidder ? `（${topDisplay}）` : ""}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }


    // 4.11 时间线
    if (raw === "时间线") return cmd_view_schedule.solve(ctx, msg, makeFakeCmdArgs([]));
    if (raw.startsWith("修改时间线")) {
        const rest = raw.slice(5).trim();
        if (rest) return cmd_update_schedule.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
        return cmd_update_schedule.solve(ctx, msg, makeFakeCmdArgs([]));
    }
    if (raw.startsWith("拒绝时间线")) {
        const rest = raw.slice(5).trim();
        return cmd_abolish_schedule.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }
    if (raw.startsWith("结束私约")) {
        const rest = raw.slice(4).trim();
        return cmd_grouplist_release.solve(ctx, msg, makeFakeCmdArgs(rest ? rest.split(/\s+/) : []));
    }

    // 4.12 加入请求
    if (raw === "加入请求") return cmd_join_requests.solve(ctx, msg, makeFakeCmdArgs([]));
    if (raw.startsWith("同意加入")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_accept_join.solve(ctx, msg, makeFakeCmdArgs([rest]));
    }
    if (raw.startsWith("拒绝加入")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_reject_join.solve(ctx, msg, makeFakeCmdArgs([rest]));
    }

    // 4.14.1 基础指南
    if (raw === "基础指南") {
        if (!msg.groupId) {
            return seal.replyToSender(ctx, msg, "请在群内使用此指令。");
        }
        (async () => {
            const base = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
            const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
            if (base) {
                try {
                    const resp = await fetch(`${base}/api/command_guides`, {
                        headers: { "X-Archive-Token": token }
                    });
                    if (resp.ok) {
                        const data = await resp.json();
                        if (data.ok && data.guides && data.guides.length > 0) {
                            const lines = ["📖 指令指南"];
                            data.guides.forEach(g => {
                                lines.push(`\n【${g.name}】`);
                                lines.push(g.url);
                            });
                            seal.replyToSender(ctx, msg, lines.join("\n"));
                            return;
                        }
                    }
                } catch (e) {
                    console.log("[基础指南] archive 不可用，回退到静态文本:", e.message || String(e));
                }
            }
            // fallback：静态合并转发
            const sections = [
                ["📖 基础指南", ""],
                ["【私约】",
                 "私约 1120-1230 地点 对方角色名[/对方2/...]",
                 "例：私约 1400-1500 咖啡厅 张三",
                 "例：私约 1400-1500 咖啡厅 张三/李四"],
                ["【修改时间线】（在约会群内使用）",
                 "修改时间线 D1 1400-1500",
                 "",
                 "【拒绝时间线】",
                 "拒绝时间线 群号"],
                ["【电话】",
                 "电话 1100-1200 邀请人1[/邀请人2/...]",
                 "例：电话 1400-1500 张三"],
                ["【短信】",
                 "[署名]短信 收信人 内容",
                 "例：短信 张三 你好！",
                 "例：李四短信 张三 你好！",
                 "",
                 "【送礼】",
                 "送礼 对方名 礼物内容",
                 "送礼 对方名 #编号（图鉴内礼物，可无限送）"],
                ["【心动信】",
                 "发送心动信",
                 "【发送对象】角色名",
                 "【内容】想说的话",
                 "【署名】自定义昵称（选填，不超过20字）",
                 "",
                 "。撤回心动信 编号   撤回已投递的信",
                 "查看信箱            查看收到的心动信"],
            ];
            const gidRaw = parseInt(msg.groupId.replace(/\D/g, ""), 10);
            const nodes = sections.map(lines => ({
                type: "node",
                data: { name: "基础指南", uin: "10001", content: lines.join("\n") }
            }));
            const m = seal.newMessage();
            m.messageType = "group";
            m.groupId = msg.groupId;
            const c = seal.createTempCtx(ctx.endPoint, m);
            ws({ action: "send_group_forward_msg", params: { group_id: gidRaw, messages: nodes } }, c, m, "");
        })();
        return seal.ext.newCmdExecuteResult(true);
    }

    // 4.15 管理员无前缀指令
    if (isAdmin) {
        if (raw === "查看计时器") return cmd_view_timers.solve(ctx, msg, makeFakeCmdArgs([]));
        if (raw === "查看进行中" || raw.startsWith("查看进行中 ")) {
            const dayPart = raw.slice(5).trim();
            return cmd_admin_view_active.solve(ctx, msg, makeFakeCmdArgs(dayPart ? [dayPart] : []));
        }
        if (raw.startsWith("提醒超时")) {
            const rest = raw.slice(4).trim();
            return cmd_remind_timeouts.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
        }
        if (raw.startsWith("设定关系线")) {
            const param = raw.slice(5).trim();
            if (!param) {
                const maxChars = cachedGet("max_detail_chars") || "500";
                const maxRel = cachedGet("max_relationships_per_user") || "20";
                return seal.replyToSender(ctx, msg, `📐 设定关系线\n字数上限：${maxChars} 字\n关系线上限：${maxRel} 条\n\n格式：\n设定关系线 字数上限 N\n设定关系线 关系上限 N`);
            }
            const m = param.match(/^(字数上限|关系上限)\s+(\d+)$/);
            if (!m) return seal.replyToSender(ctx, msg, "格式：设定关系线 字数上限 500\n  或：设定关系线 关系上限 20");
            const val = parseInt(m[2]);
            if (val <= 0) return seal.replyToSender(ctx, msg, "❌ 数值必须为正整数");
            if (m[1] === "字数上限") {
                cachedSet("max_detail_chars", String(val));
                return seal.replyToSender(ctx, msg, `✅ 单条拉线字数上限已设为 ${val} 字`);
            } else {
                cachedSet("max_relationships_per_user", String(val));
                return seal.replyToSender(ctx, msg, `✅ 关系线上限已设为 ${val} 条`);
            }
        }
        if (raw.startsWith("发起官约")) {
            const rest = raw.slice(4).trim();
            if (rest) return cmd_create_official_appointment.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
        }
    }


    // 5. 信息收集系统 & 设定NPC
    const projects = getS("sys_info_projects"); // 获取已有的项目列表
    const subM = raw.match(/^我提交\s*(.+?)[:：\s]\s*([\s\S]+)$/);

    if (subM) {
        const t = subM[1].trim(); // 用户尝试提交的项目名
        const content = subM[2].trim(); // 提交的内容

        // 检查项目是否存在于 projects 列表中
        if (projects.includes(t)) {
            // 逻辑 A: 项目存在，正常记录数据
            let d = getS("sys_info_collection");
            (d[t] = d[t] || []).push({ 
                sender: getRoleName(ctx, msg), 
                time: new Date().toLocaleString(), 
                text: content 
            });
            cachedSet("sys_info_collection", JSON.stringify(d));
            return seal.replyToSender(ctx, msg, `✅ 已记录至「${t}」。`);
        } else {
            // 逻辑 B: 项目不存在，提示联系管理员
            return seal.replyToSender(ctx, msg, `❌ 错误：尚未创建收集集「${t}」，请联系管理员创建后再提交。`);
        }
    }

    // --- 删除上传：用户撤回自己的提交 ---
    if (raw.startsWith("删除上传")) {
        const delArg = raw.slice(4).trim();
        const delM = delArg.match(/^(.+?)\s+(\d+)$/);
        if (!delM) {
            return seal.replyToSender(ctx, msg, `📤 删除上传格式：删除上传 项目名 序号\n示例：删除上传 人物档案 3\n（先用「查看收集 项目名」查看序号）`);
        }
        const delProject = delM[1].trim();
        const delIdx = parseInt(delM[2]) - 1;
        const myName = getRoleName(ctx, msg);
        const projectsList2 = getS("sys_info_projects");
        if (!projectsList2.includes(delProject)) {
            return seal.replyToSender(ctx, msg, `❌ 未找到项目「${delProject}」`);
        }
        let delData = getS("sys_info_collection");
        const recs = delData[delProject] || [];
        if (delIdx < 0 || delIdx >= recs.length) {
            return seal.replyToSender(ctx, msg, `❌ 序号超出范围（共 ${recs.length} 条）`);
        }
        const target = recs[delIdx];
        if (!isAdmin && target.sender !== myName) {
            return seal.replyToSender(ctx, msg, `❌ 只能删除自己的提交（该条由「${target.sender || "未知"}」提交）`);
        }
        recs.splice(delIdx, 1);
        delData[delProject] = recs;
        cachedSet("sys_info_collection", JSON.stringify(delData));
        return seal.replyToSender(ctx, msg, `✅ 已删除「${delProject}」第 ${delIdx + 1} 条提交。`);
    }

    // --- 所有人可用的查看功能 ---
    if (raw.startsWith("查看收集")) {
        const t = raw.replace("查看收集", "").trim();
        const projectsList = getS("sys_info_projects");
        
        // 1. 如果只输入"查看收集"，列出所有可选项目
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
        if (!getUidByRoleName(platform, name)) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${name}」`);
        const idx = npcList.indexOf(name);
        if (idx === -1) npcList.push(name); else npcList.splice(idx, 1);
        cachedSet("a_npc_list", JSON.stringify(npcList));
        return seal.replyToSender(ctx, msg, `✅ ${name} 的 NPC 身份已${idx === -1 ? '设定' : '取消'}`);
    }

    if (isAdmin) {
        if (raw.startsWith("创建收集") && isAdmin) {
            const pN = raw.replace("创建收集", "").trim();
            if (pN && !projects.includes(pN)) { projects.push(pN); cachedSet("sys_info_projects", JSON.stringify(projects)); return seal.replyToSender(ctx, msg, `✅ 已建立项目：${pN}`); }
        }
        let allInfo = getS("sys_info_collection");
        if (raw.startsWith("我清空")) {
            const t = raw.replace("我清空", "").trim();
            if (allInfo[t]) { allInfo[t] = []; cachedSet("sys_info_collection", JSON.stringify(allInfo)); return seal.replyToSender(ctx, msg, `🗑️ 已清空「${t}」`); }
        }
    }

    // 5. --- 你的核心私有群监听逻辑 (确保被包裹在 try 中) ---
    try {
        const a_private_group = getS("a_private_group");
        // 新结构：a_private_group[platform][uid] = [roleName, gid]，直接用 uid 查
        const roleName = a_private_group[platform]?.[uid]?.[0];

        if (roleName) {
            handleReply(platform, groupId, roleName, msg.message);

            // 格式提示：首行≠角色名时提醒，不计入存档和字数
            // 只在有活跃计时器的群里提示，避免日常闲聊误触发
            const _hintTimers = getGroupTimers();
            const _hintTimer = _hintTimers[groupId];
            if (_hintTimer) {
                const _hintLines = msg.message.split("\n");
                const _hintFirst = _hintLines[0].trim();
                if (_hintFirst !== roleName) {
                    const _isPhone = _hintTimer.subtype === "电话";
                    // 电话群：所有不符合格式的消息都提醒
                    // 其他群：仅在首行像角色名（≤20字）且有第二行时提醒（避免日常闲聊刷屏）
                    const _shouldHint = _isPhone
                        || (_hintFirst.length >= 1 && _hintFirst.length <= 20
                            && _hintLines.length >= 2 && _hintLines[1].trim());
                    if (_shouldHint) {
                        seal.replyToSender(ctx, msg,
                            `⚠️ 首行「${_hintFirst}」不是你的角色名，这条不会计入存档和字数。\n你的角色名是「${roleName}」`);
                    }
                }
            }
        }
    } catch (e) {
        console.error('监听系统错误:', e);
    }
};

let cmd_view_timers = {};
cmd_view_timers.solve =(ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return;

    const timers = JSON.parse(cachedGet("group_timers") || "{}"), now = Date.now();
    const tKeys = Object.keys(timers);
    if (!tKeys.length) return seal.replyToSender(ctx, msg, "📭 当前没有活跃的计时器");

    let totalOverdue = 0;
    const timerNodes = [];
    tKeys.forEach(gid => {
        const t = timers[gid];
        const detail = Object.entries(t.timerStatus).map(([name, s]) => {
            const replies = s.sessionReplies || 0;
            const words = s.sessionWords || 0;
            const avg = replies > 0 ? Math.round(words / replies) : 0;
            const statLine = `  📝 ${replies}段 / ${words}字 / 均${avg}字`;

            if (s.status !== "timing") return `✅ ${name}: replied\n${statLine}`;

            const diff = t.timeoutDuration - (now - s.startTime);
            const isOver = diff < 0;
            if (isOver) totalOverdue++;

            return `${isOver ? "🔴" : "⏳"} ${name}: ${Math.abs(Math.round(diff / 60000))}min${isOver ? "!" : ""}\n${statLine}`;
        }).join('\n');

        timerNodes.push({
            type: "node",
            data: { name: `群组 ${gid} | ${t.subtype}`, uin: "10001", content: `📍 模式：${t.timerMode === 'turn_taking' ? '轮流' : '独立'}\n— 以上 —\n${detail}` }
        });
    });

    const gId = parseInt(msg.groupId.replace(/[^\d]/g, ""), 10);
    const CHUNK = 10;
    const totalBatches = Math.ceil(timerNodes.length / CHUNK);
    const timeStr = new Date().toLocaleTimeString();

    for (let i = 0; i < totalBatches; i++) {
        const batchLabel = totalBatches > 1 ? `（第${i + 1}批/共${totalBatches}批）` : "";
        const header = { type: "node", data: { name: "计时监控中心", uin: "2852199344", content: `📊 运行中：${tKeys.length} 个${batchLabel}\n更新：${timeStr}` } };
        const chunk = [header, ...timerNodes.slice(i * CHUNK, (i + 1) * CHUNK)];
        ws({ action: "send_group_forward_msg", params: { group_id: gId, messages: chunk } }, ctx, msg, "");
    }

    seal.replyToSender(ctx, msg, `✅ 报表已生成${totalBatches > 1 ? `（共${totalBatches}批）` : ""}\n⏳ 超时：${totalOverdue} 人\n(详情见下方合并消息)`);
    return seal.ext.newCmdExecuteResult(true);
};

let cmd_remind_timeouts = {};
cmd_remind_timeouts.solve =(ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "🌸 只有管理员可以呼唤大家哦～");

    const target = cmdArgs.getArgN(1), now = Date.now();
    const timers = JSON.parse(cachedGet("group_timers") || "{}");
    const priv = JSON.parse(cachedGet("a_private_group") || "{}");
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

            const roleUid2 = getUidByRoleName(platform, name);

            // 1. 发送给个人小群
            const pGid = roleUid2 ? priv[platform]?.[roleUid2]?.[1] : null;
            if (pGid) {
                const text = `✨ 亲爱的 ${name}，在「${timer.subtype}」里大家等你 ${timeStr} 啦。如果不忙的话，记得回一下小伙伴们哦～ ❤️`;
                const m1 = seal.newMessage(); m1.messageType = "group"; m1.groupId = `${platform}-Group:${pGid}`;
                seal.replyToSender(seal.createTempCtx(ctx.endPoint, m1), m1, text);
            }

            // 2. 发送到公共群，@主账号和所有额外账号
            const extras2 = JSON.parse(cachedGet("extra_accounts") || "{}");
            const allAtUids = roleUid2 && !/^npc_/.test(roleUid2)
                ? [roleUid2, ...Object.entries(extras2)
                    .filter(([k, v]) => k.startsWith(`${platform}:`) && v === roleUid2)
                    .map(([k]) => k.replace(`${platform}:`, ""))]
                : [];
            const atStr2 = allAtUids.map(u => `[CQ:at,qq=${u}]`).join("") + (allAtUids.length ? "\n" : "");
            const m2 = seal.newMessage(); m2.messageType = "group"; m2.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m2), m2, `${atStr2}🌷 温馨提示：${name} 已经忙碌 ${timeStr} 啦，我们再耐心等一下ta吧～`);

            s.remindedTimes = (s.remindedTimes || 0) + 1;
            sentCount++;
        });

        if (groupReminders.length) {
            timer.lastRemindTime = now;
            detail.push(`群组 ${gid}: ${groupReminders.map(r => r[0]).join("、")}`);
        }
    }

    if (sentCount > 0) {
        cachedSet("group_timers", JSON.stringify(timers));
        seal.replyToSender(ctx, msg, `💖 提醒任务完成！\n共送出 ${sentCount} 份温柔提醒：\n${detail.join('\n')}\n大家一定会感受到的～ 🌟`);
    } else {
        seal.replyToSender(ctx, msg, "🌙 检查了一圈，现在大家都很守时，不需要打扰呢～");
    }
    return seal.ext.newCmdExecuteResult(true);
};

// ========================
// ========================
// 更新活跃计时器超时（供设置变更时调用）
function updateActiveTimerSettings(newTimeout, newRemindInterval) {
    const timers = getGroupTimers();
    let changed = false;
    for (const timer of Object.values(timers)) {
        if (timer.timeoutDuration !== newTimeout) {
            timer.timeoutDuration = newTimeout;
            changed = true;
        }
        timer.remindInterval = newRemindInterval;
    }
    if (changed) saveGroupTimers(timers);
}

// ========================
// 📮 派送辅助与档期自动 D0
// ========================
// 心动信主体逻辑已拆至卫星插件 长日心动信.js（经 __changriApi 调用），
// 以下为留在主插件的公共部分：发送辅助（本文件与卫星共用）与档期自动 D0 定时器。

function getSafeEndPoint(platform = "QQ") {
    const eps = seal.getEndPoints();
    if (!eps || eps.length === 0) return null;
    let target = eps.find(e => e.platform === platform && e.state === 1);
    if (!target) target = eps.find(e => e.state === 1);
    if (!target) target = eps[0];
    return target;
}

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

// 返回今天的 MMDD 字符串，如 "0528"
function getTodayMMDD() {
    const d = new Date();
    return String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
}

// 档期自动 D0：每分钟检查一次，档期开始日当天 global_days 为空时自动设置 D0
let _lastAutoD0Date = "";
function checkAutoD0() {
    const schedStart = cachedGet("season_schedule_start") || "";
    if (!schedStart) return;
    const today = getTodayMMDD();
    if (today !== schedStart) return;
    if (_lastAutoD0Date === today) return;          // 今天已处理过
    const current = cachedGet("global_days") || "";
    if (current) return;                             // 已有天数，不覆盖
    cachedSet("global_days", "D0");
    _lastAutoD0Date = today;
    const announceGid = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");
    if (announceGid) sendTextToGroup("QQ", announceGid, `🗓️ 档期正式开始！游戏天数已自动设置为 D0。`);
}
setInterval(checkAutoD0, 30000);

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
    let npcList = JSON.parse(cachedGet("a_npc_list") || "[]");

    if (!storage[platform] || !getUidByRoleName(platform, name)) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${name}」，请先创建角色。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let index = npcList.indexOf(name);
    if (index === -1) {
        npcList.push(name);
        cachedSet("a_npc_list", JSON.stringify(npcList));
        seal.replyToSender(ctx, msg, `✅ 已将「${name}」设为 NPC，分组时将自动跳过。`);
    } else {
        npcList.splice(index, 1);
        cachedSet("a_npc_list", JSON.stringify(npcList));
        seal.replyToSender(ctx, msg, `✅ 已取消「${name}」的 NPC 身份。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设为npc"] = cmd_set_npc;

// 创建NPC（与创建新角色逻辑相同，额外加入 npc_list）
let cmd_create_npc = seal.ext.newCmdItemInfo();
cmd_create_npc.name = "创建NPC";
cmd_create_npc.help = "用法：。创建NPC [角色名]\n说明：创建角色并自动标记为NPC身份（不计入弧长统计）。";
cmd_create_npc.solve = (ctx, msg, cmdArgs) => {
    const name = cmdArgs.getArgN(1);
    if (!name || name === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    // archive 开启时必须先有活跃季度
    if (isArchiveEnabled() && !hasActiveSeason()) {
        seal.replyToSender(ctx, msg, "❌ 当前无活跃季度。请先运行「创建新季度 恋综名 复盘/不复盘 MMDD-MMDD」。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const gid = msg.groupId ? msg.groupId.replace(`${platform}-Group:`, "") : "0";
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const storage = getRoleStorage();
    if (!storage[platform]) storage[platform] = {};

    // 检查名称是否被他人占用
    const existingUidForName = Object.entries(storage[platform]).find(([k, v]) => v[0] === name && k !== uid)?.[0];
    if (existingUidForName) {
        seal.replyToSender(ctx, msg, `❌ 名称「${name}」已被其他用户占用`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 已有角色则拒绝
    if (storage[platform][uid]) {
        const existingName = storage[platform][uid][0];
        seal.replyToSender(ctx, msg, `⚠️ 你已有角色「${existingName}」。若想改名，请发送「修改名字 新名字」。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    storage[platform][uid] = [name, gid];
    cachedSet("a_private_group", JSON.stringify(storage));
    initCharProfile(platform, name);

    // 加入 NPC 列表
    const npcList = JSON.parse(cachedGet("a_npc_list") || "[]");
    if (!npcList.includes(name)) {
        npcList.push(name);
        cachedSet("a_npc_list", JSON.stringify(npcList));
    }

    const profile = getCharProfile(platform, name);
    seal.replyToSender(ctx, msg,
        `✅ NPC「${name}」创建成功！已自动标记为NPC身份。\n` +
        `\n以下是初始档案：\n` +
        `👤 性别：${profile.gender}　年龄：${profile.age}\n` +
        `🌸 皮相：${profile.look}\n` +
        `\n💡 可发送以下消息定制角色：\n` +
        `  修改性别 男/女\n` +
        `  修改年龄 数字\n` +
        `  修改皮相 明星名\n` +
        `  修改签名 你的签名`
    );
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建NPC"] = cmd_create_npc;

// ========================
// ========================
// RPG背包辅助函数（复制自长日RPG，确保长日系统能调用）
// ========================
function getRegistry_rpg() {
    const main = seal.ext.find("changri");
    return main ? JSON.parse(cachedGet("item_registry") || "{}") : {};
}
function findItem_rpg(reg, input) {
    if (!input) return null;
    const code = input.toUpperCase();
    if (reg[code]) return reg[code];
    return Object.values(reg).find(r => r.name === input) || null;
}
function findCurrencyByName_rpg(name) {
    const reg = getRegistry_rpg();
    return Object.values(reg).find(i => i.type === "currency" && i.name === name) || null;
}
function getInvCount_rpg(roleKey, code) {
    const inv = getInvAll_rpg()[roleKey] || [];
    return inv.filter(e => e.code === code).reduce((s, e) => s + e.count, 0);
}
function removeFromInv_rpg(roleKey, code, count) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    let remaining = count;
    for (const entry of inv.filter(e => e.code === code).sort((a, b) => (b.remainingUses || 0) - (a.remainingUses || 0))) {
        if (remaining <= 0) break;
        const take = Math.min(entry.count, remaining);
        entry.count -= take;
        remaining -= take;
    }
    invs[roleKey] = inv.filter(e => e.count > 0);
    saveInvAll_rpg(invs);
}
function getInvAll_rpg() {
    const main = seal.ext.find("changri");
    return main ? JSON.parse(cachedGet("global_inventories") || "{}") : {};
}
function saveInvAll_rpg(invs) {
    const main = seal.ext.find("changri");
    if (main) cachedSet("global_inventories", JSON.stringify(invs));
}
function addToInv_system(roleKey, code, count) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    const reg = getRegistry_rpg();
    const itemInfo = reg[code];

    if (!itemInfo) {
        console.error(`[长日系统] 尝试添加不存在的物品代码: ${code}`);
        return;
    }

    const initialUses = itemInfo.maxUses ?? -1;
    const entry = inv.find(e => e.code === code && (e.remainingUses ?? -1) === initialUses);

    if (entry) {
        entry.count += count;
    } else {
        inv.push({
            code,
            count,
            remainingUses: initialUses
        });
    }

    invs[roleKey] = inv;
    saveInvAll_rpg(invs);
}

// 🔨 拍卖系统
// ========================

// 带失效时间写入背包（不与普通条目堆叠）
function _addToInvWithExpiry(roleKey, code, count, expiresAt) {
    const invs = getInvAll_rpg();
    const inv = invs[roleKey] || [];
    const reg = getRegistry_rpg();
    const itemInfo = reg[code];
    if (!itemInfo) { console.error(`[拍卖] 找不到物品代码: ${code}`); return; }
    const initialUses = itemInfo.maxUses ?? -1;
    inv.push({ code, count, remainingUses: initialUses, expiresAt });
    invs[roleKey] = inv;
    saveInvAll_rpg(invs);
}

// 清理所有背包中已过期的拍卖物品（expiresAt 字段）
function pruneExpiredAuctionItems() {
    const invs = getInvAll_rpg();
    const now = Date.now();
    let changed = false;
    for (const roleKey of Object.keys(invs)) {
        const before = invs[roleKey].length;
        invs[roleKey] = invs[roleKey].filter(e => !e.expiresAt || e.expiresAt > now);
        if (invs[roleKey].length !== before) changed = true;
    }
    if (changed) saveInvAll_rpg(invs);
}

function getAuctions() {
    return JSON.parse(cachedGet("auction_items") || "{}");
}
function saveAuctions(data) {
    cachedSet("auction_items", JSON.stringify(data));
}
function getAuctionSettings() {
    return {
        displayGroup: JSON.parse(cachedGet("song_group_id") || "null") || "",
        allowAnon: cachedGet("auction_allow_anon") !== "false",
        broadcast: cachedGet("auction_broadcast") !== "false",
        showTopBidder: cachedGet("auction_show_top_bidder") !== "false",
        currency: cachedGet("auction_currency") || "金币"
    };
}

// 结算单件拍卖（不检查到期时间），返回结果描述字符串
function _settleSingleAuction(ctx, msg, settings, auctions, id, item) {
    const platform = msg.platform;
    const bids = item.bids || [];
    if (bids.length === 0) {
        item.status = "unsold";
        _announceAuction(ctx, msg, settings, `🔨 拍卖结束 | ${id} 「${item.name}」\n💸 无人出价，已流拍。`);
        return `${id} 「${item.name}」流拍（无人出价）`;
    }

    const currencyItem = findCurrencyByName_rpg(settings.currency);
    let winner = null;
    if (currencyItem) {
        for (const bid of bids) {
            const roleKey = `${platform}:${bid.uid}`;
            if (getInvCount_rpg(roleKey, currencyItem.code) >= bid.amount) { winner = bid; break; }
        }
    } else {
        const attrs = JSON.parse(cachedGet("sys_character_attrs") || "{}");
        for (const bid of bids) {
            if ((attrs[bid.uid]?.[settings.currency] || 0) >= bid.amount) { winner = bid; break; }
        }
    }

    if (!winner) {
        item.status = "unsold";
        _announceAuction(ctx, msg, settings, `🔨 拍卖结束 | ${id} 「${item.name}」\n💸 所有出价者余额不足，已流拍。`);
        return `${id} 「${item.name}」流拍（余额不足）`;
    }

    if (currencyItem) {
        removeFromInv_rpg(`${platform}:${winner.uid}`, currencyItem.code, winner.amount);
    } else {
        const attrs = JSON.parse(cachedGet("sys_character_attrs") || "{}");
        if (!attrs[winner.uid]) attrs[winner.uid] = {};
        attrs[winner.uid][settings.currency] = (attrs[winner.uid][settings.currency] || 0) - winner.amount;
        cachedSet("sys_character_attrs", JSON.stringify(attrs));
    }

    const roleKey = `${platform}:${winner.uid}`;
    const itemCode = item.code || item.name.toUpperCase();
    if (item.expireHours) {
        const expiresAt = Date.now() + item.expireHours * 3600 * 1000;
        _addToInvWithExpiry(roleKey, itemCode, 1, expiresAt);
    } else {
        addToInv_system(roleKey, itemCode, 1);
    }
    item.status = "sold";
    item.winner = { roleName: winner.roleName, amount: winner.amount, isAnon: winner.isAnon };

    const winnerDisplay = winner.isAnon ? "匿名玩家" : `「${winner.roleName}」`;
    const expireNote = item.expireHours ? `\n⏳ 物品将在 ${item.expireHours} 小时后失效` : "";
    _announceAuction(ctx, msg, settings,
        `🎉 拍卖成交公告\n${"━".repeat(16)}\n📦 ${id} 「${item.name}」\n🏆 最终得主：${winnerDisplay}\n💰 成交价：${winner.amount} ${settings.currency}\n${"━".repeat(16)}\n物品已放入得主背包。${expireNote}`);
    return `${id} 「${item.name}」→ ${winnerDisplay} ${winner.amount} ${settings.currency}`;
}

// 被动触发：结算所有到期拍卖，并清理已过期背包物品
function settleExpiredAuctions(ctx, msg) {
    pruneExpiredAuctionItems();
    const auctions = getAuctions();
    const now = Date.now();
    const settings = getAuctionSettings();
    const summary = [];
    let changed = false;

    for (const [id, item] of Object.entries(auctions)) {
        if (item.status !== "active") continue;
        if (now < item.endTime) continue;
        summary.push(_settleSingleAuction(ctx, msg, settings, auctions, id, item));
        changed = true;
    }

    if (changed) saveAuctions(auctions);
    return summary;
}

function _notifyAuction(ctx, msg, settings, text) {
    if (!settings.displayGroup || !settings.broadcast) return;
    ws({ action: "send_group_msg", params: { group_id: parseInt(settings.displayGroup), message: text } }, ctx, msg, "");
}
function _announceAuction(ctx, msg, settings, text) {
    if (!settings.displayGroup) return;
    ws({ action: "send_group_msg", params: { group_id: parseInt(settings.displayGroup), message: text } }, ctx, msg, "");
}

// 生成下一个拍卖编号
function _nextAuctionId(auctions) {
    const nums = Object.keys(auctions).map(k => parseInt(k.replace('#', ''))).filter(n => !isNaN(n));
    return `#${nums.length > 0 ? Math.max(...nums) + 1 : 1}`;
}

// 解析单件格式：名称%起拍价%最低加价%时长(h)[%失效时长(h)]
function _parseAuctionItem(raw) {
    const parts = raw.trim().split('%');
    if (parts.length < 4) return { err: `格式错误（需至少4段，用%分隔）：${raw}` };
    const [itemInput, sp, mi, dur, expStr] = parts;
    const startPrice = parseInt(sp), minIncrement = parseInt(mi), durationHours = parseFloat(dur);
    if (!itemInput.trim()) return { err: "物品码/名称为空" };
    if (isNaN(startPrice) || startPrice < 0) return { err: `起拍价无效：${sp}` };
    if (isNaN(minIncrement) || minIncrement < 1) return { err: `最低加价无效：${mi}` };
    if (isNaN(durationHours) || durationHours <= 0) return { err: `时长无效：${dur}` };
    let expireHours = null;
    if (expStr !== undefined && expStr.trim() !== '') {
        expireHours = parseFloat(expStr);
        if (isNaN(expireHours) || expireHours <= 0) return { err: `失效时长无效：${expStr}` };
    }
    return { itemInput: itemInput.trim(), startPrice, minIncrement, durationHours, expireHours };
}

// 添加拍卖物品
let cmd_add_auction = seal.ext.newCmdItemInfo();
cmd_add_auction.name = "添加拍卖物品";
cmd_add_auction.help = "。添加拍卖物品 物品码或名称%起拍价%最低加价%时长(h)[%失效时长(h)]\n批量：多件用$分隔\n例：。添加拍卖物品 ITEM_001%100%10%24\n带失效：。添加拍卖物品 ITEM_001%100%10%24%72";
cmd_add_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "该指令仅限管理员使用"); return seal.ext.newCmdExecuteResult(true); }
    const inputArg = msg.message.replace(/^[。.]添加拍卖物品\s*/, "").trim();
    if (!inputArg) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const auctions = getAuctions();
    const activeCount = Object.values(auctions).filter(a => a.status === "active").length;
    const reg = getRegistry_rpg();
    const items = inputArg.includes('$') ? inputArg.split('$') : [inputArg];
    const results = { success: 0, failed: 0, details: [] };
    const now = Date.now();

    for (const item of items) {
        if (!item.trim()) continue;
        if (activeCount + results.success >= 10) { results.details.push("❌ 已达10件同时上限，剩余未添加"); results.failed += items.length - results.success - results.failed; break; }
        const parsed = _parseAuctionItem(item);
        if (parsed.err) { results.details.push(`❌ ${parsed.err}`); results.failed++; continue; }
        const regItem = findItem_rpg(reg, parsed.itemInput);
        if (!regItem) { results.details.push(`❌ 未找到物品「${parsed.itemInput}」，请先上载物品`); results.failed++; continue; }
        const id = _nextAuctionId(auctions);
        const canResell = regItem.allowSecondhand === true;
        auctions[id] = { id, code: regItem.code, name: regItem.name, desc: regItem.desc || "", startPrice: parsed.startPrice, minIncrement: parsed.minIncrement, durationHours: parsed.durationHours, expireHours: parsed.expireHours, canResell, startTime: now, endTime: now + parsed.durationHours * 3600 * 1000, bids: [], status: "active", winner: null };
        const resellText = canResell ? "✅ 可二手" : "❌ 不可二手";
        const expireText = parsed.expireHours ? `⏳ 得主 ${parsed.expireHours}h 后失效` : "永久有效";
        results.details.push(`✅ ${id} [${regItem.code}]「${regItem.name}」起拍 ${parsed.startPrice}，最低加价 ${parsed.minIncrement}，时长 ${parsed.durationHours}h | ${resellText} | ${expireText}`);
        results.success++;
    }

    if (results.success > 0) saveAuctions(auctions);
    let rep = items.length > 1 ? `📦 批量添加 ✅${results.success} ❌${results.failed}\n\n` : "";
    rep += results.details.join('\n');
    seal.replyToSender(ctx, msg, rep);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["添加拍卖物品"] = cmd_add_auction;

// 删除拍卖物品
let cmd_del_auction = seal.ext.newCmdItemInfo();
cmd_del_auction.name = "删除拍卖物品";
cmd_del_auction.help = "。删除拍卖物品 编号（如 #1）";
cmd_del_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "该指令仅限管理员使用"); return seal.ext.newCmdExecuteResult(true); }
    const id = cmdArgs.getArgN(1);
    if (!id) { seal.replyToSender(ctx, msg, "格式：。删除拍卖物品 #编号"); return seal.ext.newCmdExecuteResult(true); }
    const auctions = getAuctions();
    if (!auctions[id]) { seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${id}`); return seal.ext.newCmdExecuteResult(true); }
    const name = auctions[id].name;
    delete auctions[id];
    saveAuctions(auctions);
    seal.replyToSender(ctx, msg, `✅ 已删除 ${id} 「${name}」`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除拍卖物品"] = cmd_del_auction;

// 手动结算（管理员）
let cmd_settle_auction = seal.ext.newCmdItemInfo();
cmd_settle_auction.name = "结算拍卖";
cmd_settle_auction.help = "。结算拍卖 #编号 —— 手动结算指定拍卖（无需到期）";
cmd_settle_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "该指令仅限管理员使用"); return seal.ext.newCmdExecuteResult(true); }
    const id = cmdArgs.getArgN(1);
    if (!id) { seal.replyToSender(ctx, msg, "格式：。结算拍卖 #编号"); return seal.ext.newCmdExecuteResult(true); }
    const auctions = getAuctions();
    const item = auctions[id];
    if (!item) { seal.replyToSender(ctx, msg, `❌ 找不到拍卖物品 ${id}`); return seal.ext.newCmdExecuteResult(true); }
    if (item.status !== "active") { seal.replyToSender(ctx, msg, `❌ ${id} 已结算（状态：${item.status}）`); return seal.ext.newCmdExecuteResult(true); }
    const settings = getAuctionSettings();
    const result = _settleSingleAuction(ctx, msg, settings, auctions, id, item);
    saveAuctions(auctions);
    seal.replyToSender(ctx, msg, `✅ 结算完成：${result}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结算拍卖"] = cmd_settle_auction;

// 拉取拍卖队列
let cmd_pull_auction = seal.ext.newCmdItemInfo();
cmd_pull_auction.name = "拉取拍卖队列";
cmd_pull_auction.help = "。拉取拍卖队列 —— 从存档服务器拉取待拍物品并激活，自动清空服务器队列";
cmd_pull_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "该指令仅限管理员使用"); return seal.ext.newCmdExecuteResult(true); }
    if (!isArchiveEnabled()) { seal.replyToSender(ctx, msg, "❌ 存档未启用，请先在设置中开启「启用RP存档传输」"); return seal.ext.newCmdExecuteResult(true); }
    const base = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) { seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址"); return seal.ext.newCmdExecuteResult(true); }
    fetch(base + "/api/auction_queue", {
        method: "GET",
        headers: { "X-Archive-Token": token }
    }).then(r => r.json()).then(data => {
        if (!data || !data.ok) { seal.replyToSender(ctx, msg, `❌ 拉取失败：${(data && data.error) || "未知错误"}`); return; }
        const queue = data.queue || [];
        if (!queue.length) { seal.replyToSender(ctx, msg, "📭 队列为空，暂无新的拍卖物品"); return; }
        const auctions = getAuctions();
        const reg = getRegistry_rpg();
        const now = Date.now();
        const results = { success: 0, failed: 0, details: [] };
        for (const item of queue) {
            const regItem = findItem_rpg(reg, item.code);
            if (!regItem) { results.details.push(`❌ 未找到物品「${item.code}」，请先上载物品`); results.failed++; continue; }
            const id = _nextAuctionId(auctions);
            const canResell = regItem.allowSecondhand === true;
            auctions[id] = {
                id, code: regItem.code, name: regItem.name, desc: regItem.desc || "",
                startPrice: item.startPrice, minIncrement: item.minIncrement,
                durationHours: item.durationHours, expireHours: item.expireHours || null,
                canResell, startTime: now, endTime: now + item.durationHours * 3600 * 1000,
                bids: [], status: "active", winner: null
            };
            const expireText = item.expireHours ? `失效 ${item.expireHours}h` : "永久";
            results.details.push(`✅ ${id}「${regItem.name}」起拍 ${item.startPrice}，时长 ${item.durationHours}h | ${expireText}`);
            results.success++;
        }
        if (results.success > 0) saveAuctions(auctions);
        // 清空服务器队列
        fetch(base + "/api/auction_queue", { method: "DELETE", headers: { "X-Archive-Token": token } })
            .catch(e => console.error("[拍卖] 清空队列失败:", e));
        let rep = `📦 拉取拍卖队列 ✅${results.success} ❌${results.failed}\n\n${results.details.join('\n')}`;
        seal.replyToSender(ctx, msg, rep);
    }).catch(e => {
        seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
    });
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拉取拍卖队列"] = cmd_pull_auction;

// 上传拍卖
let cmd_push_auction = seal.ext.newCmdItemInfo();
cmd_push_auction.name = "上传拍卖";
cmd_push_auction.help = "。上传拍卖 —— 将当前拍卖状态快照推送到存档服务器供后台查看";
cmd_push_auction.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) { seal.replyToSender(ctx, msg, "该指令仅限管理员使用"); return seal.ext.newCmdExecuteResult(true); }
    if (!isArchiveEnabled()) { seal.replyToSender(ctx, msg, "❌ 存档未启用，请先在设置中开启「启用RP存档传输」"); return seal.ext.newCmdExecuteResult(true); }
    const auctions = getAuctions();
    const count = Object.keys(auctions).length;
    postToArchive("/api/auction_snapshot", { snapshot: auctions });
    seal.replyToSender(ctx, msg, `✅ 拍卖快照已发送（共 ${count} 件）\n在后台「拍卖」页面可查看详情`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传拍卖"] = cmd_push_auction;

// ========================
// 📋 管理帮助（运营清单）
// ========================
let cmd_admin_help = seal.ext.newCmdItemInfo();
cmd_admin_help.name = "管理帮助";
cmd_admin_help.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 该指令仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const base = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const groupsUrl = base ? `${base}/admin/groups`         : "（未配置存档服务器地址）";
    const guidesUrl = base ? `${base}/admin/command_guides` : "（未配置存档服务器地址）";
    const statsUrl  = base ? `${base}/admin/stats`          : "（未配置存档服务器地址）";
    (async () => {
        let guideLines = "";
        if (base) {
            try {
                const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
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
            "1. 【后台】录入群号组：",
            `   ${groupsUrl}`,
            "2. 【后台】创建指令指南：",
            `   ${guidesUrl}`,
            "3. 。清空季度数据  ← 扫描残留玩家并清空上季数据",
            "4. 。创建新季度 恋综名 复盘/不复盘 MMDD-MMDD [补戏MMDD]",
            "5. 。开启群号组 组名  ← 从后台拉取群号到戏群池",
            "6. 。初始化设置  ← 从后台拉取系统配置（或 。同步设置 强制覆盖）",
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

    let confirmed = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const platform = msg.platform;
    const privateGroups = JSON.parse(cachedGet("a_private_group") || "{}");

    // 1. 定位目标角色的 UID
    const targetUid = privateGroups?.[platform]?.[name]?.[0];
    if (!targetUid) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色 ${name} 的注册信息。`);
        return seal.ext.newCmdExecuteResult(true);
    }
    const targetKey = `${platform}:${targetUid}`;

    // 2. 在该角色的日程里找到那场具体的"约会"
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
        cachedSet("b_confirmedSchedule", JSON.stringify(confirmed));
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

        cachedSet("b_confirmedSchedule", JSON.stringify(confirmed));
        seal.replyToSender(ctx, msg, `✅ 已精准抹除 ${name} 与 ${partnerName} 在 ${day} ${time} 的约会记录。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["删除时间线"] = cmd_delete_timeline_precise;

let cmd_sync_now = seal.ext.newCmdItemInfo();
cmd_sync_now.name = "同步名片";
cmd_sync_now.help = "同步名片 公告/戏群/水群";
cmd_sync_now.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return;

    const groupTypeMap = {
        "公告": "adminAnnounceGroupId",
        "戏群": "song_group_id",
        "水群": "water_group_id",
    };
    const typeArg = (cmdArgs.args[0] || "").trim();
    const storageKey = groupTypeMap[typeArg];
    if (!storageKey) return seal.replyToSender(ctx, msg, "⚠️ 请指定群类型：同步名片 公告 / 戏群 / 水群");

    const targetGid = JSON.parse(cachedGet(storageKey) || "null");
    if (!targetGid || targetGid === "未设置") return seal.replyToSender(ctx, msg, `⚠️ ${typeArg}群号未配置`);
    const cleanTargetGid = parseInt(targetGid.toString().replace(/[^\d]/g, ""));
    if (isNaN(cleanTargetGid)) return seal.replyToSender(ctx, msg, `⚠️ ${typeArg}群号无效`);

    const platform = msg.platform, storage = getRoleStorage();
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
// 📅 修改时间线 指令
// ========================
let cmd_update_schedule = {};
cmd_update_schedule.solve =(ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const gid = msg.groupId.replace(`${platform}-Group:`, "");
    const newDay = cmdArgs.getArgN(1); // 例如 D1
    const newRawTime = cmdArgs.getArgN(2); // 例如 1400-1500

    if (!newDay || !newRawTime) return seal.replyToSender(ctx, msg, "⚠️ 格式错误，请使用：.修改时间线 D1 1400-1500");

    // 1. 获取当前群的参与者信息
    let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    const info = groupExpireInfo[gid];
    if (!info) return seal.replyToSender(ctx, msg, "⚠️ 只有在活跃的私约/电话群内才能修改时间。");

    // 2. 校验新时间格式与合法性
    const allowedRanges = JSON.parse(cachedGet("allowed_appointment_times") || "[]");
    const subtype = info.subtype || "私密";
    const minDuration = subtype === "电话" ? 29 : 59;
    const timeRes = parseAndValidateTime(newRawTime, allowedRanges, minDuration, subtype);
    if (!timeRes.valid) return seal.replyToSender(ctx, msg, timeRes.errorMsg);
    const newTime = timeRes.time;

    // 3. 冲突检查：检查所有人名下在新时段是否有别的安排
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
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
    cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));

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
    cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

    // C. 同步 group_timers 中的 day/time
    const groupTimersForUpdate = JSON.parse(cachedGet("group_timers") || "{}");
    if (groupTimersForUpdate[gid]) {
        groupTimersForUpdate[gid].day  = newDay;
        groupTimersForUpdate[gid].time = newTime;
        cachedSet("group_timers", JSON.stringify(groupTimersForUpdate));
    }

    // 5. 修改群名片并通知
    const nameTag = participants.length > 2 ? "多人" : participants.join("/");
    const newGroupName = `${subtype} ${newDay} ${newTime} ${info.place} ${nameTag}`;
    setGroupName(ctx, msg, gid, newGroupName);

    seal.replyToSender(ctx, msg, `✅ 时间线修改成功！\n📅 新时间：${newDay} ${newTime}\n新的日程已同步至所有参与者的【时间线】。`);
    return seal.ext.newCmdExecuteResult(true);
};

// ========================
// 🗑️ 拒绝时间线 指令
// ========================
let cmd_abolish_schedule = {};
cmd_abolish_schedule.solve =(ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const targetGid = cmdArgs.getArgN(1);

    if (!targetGid) return seal.replyToSender(ctx, msg, "⚠️ 格式错误，请使用：.拒绝时间线 群号");

    let groupPool = JSON.parse(cachedGet("group") || "[]");
    let groupExpireInfo = JSON.parse(cachedGet("group_expire_info") || "{}");
    let b_confirmedSchedule = JSON.parse(cachedGet("b_confirmedSchedule") || "{}");
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");

    // 1. 检查是否为占用状态
    const fullId = `${targetGid}_占用`;
    const isOccupied = groupPool.includes(fullId);

    if (!isOccupied) return seal.replyToSender(ctx, msg, `⚠️ 群号 ${targetGid} 未处于占用状态，无需拒绝。`);

    // 2. 检查约会类型，只有电话和私约可以拒绝
    const groupInfo = groupExpireInfo[targetGid] || {};
    const subtype = groupInfo.subtype || "私密";
    if (subtype === "心愿" || subtype === "官约") {
        return seal.replyToSender(ctx, msg, `⚠️ ${subtype}约不可拒绝，请通过正常流程处理。`);
    }

    // 3. 获取参与者信息
    const participants = groupInfo.participants || [];

    // 3.5 检查执行者是否是该约会的参与者
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const isParticipant = participants.some(name => {
        const details = getRoleDetails(platform, name);
        return details && details.uid && details.uid.replace(/^[a-z]+:/i, "") === uid;
    });
    if (!isParticipant) return seal.replyToSender(ctx, msg, `⚠️ 你不是该约会的参与者，无法拒绝。`);

    // 找到拒绝者的角色名
    const rejecterName = participants.find(name => {
        const details = getRoleDetails(platform, name);
        return details && details.uid && details.uid.replace(/^[a-z]+:/i, "") === uid;
    }) || "对方";

    const groupMsg = seal.newMessage();
    groupMsg.messageType = "group";
    groupMsg.groupId = `${platform}-Group:${targetGid}`;
    const groupCtx = seal.createTempCtx(ctx.endPoint, groupMsg);

    if (participants.length <= 2) {
        // ── 两人约会：直接取消 ──
        seal.replyToSender(groupCtx, groupMsg, `🚫 【约会已取消】\n\n${rejecterName} 取消了这场约会。\n请各位参与者尽快退群，期待下次相遇！`);

        for (let participantName of participants) {
            // 新结构：通过 roleName 反查 uid，再取 gid
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

        // 清除全部日程记录
        for (let uidKey in b_confirmedSchedule) {
            b_confirmedSchedule[uidKey] = b_confirmedSchedule[uidKey].filter(ev => ev.group !== targetGid);
        }
        cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

        if (groupExpireInfo[targetGid]) {
            delete groupExpireInfo[targetGid];
            cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));
        }

        const idx = groupPool.indexOf(fullId);
        if (idx !== -1) {
            groupPool.splice(idx, 1);
            groupPool.push(targetGid);
            cachedSet("group", JSON.stringify(groupPool));
        }

        setGroupName(ctx, msg, targetGid, getIdleGroupName());
        cleanupGroupTimer(targetGid);

        seal.replyToSender(ctx, msg, `✅ 已取消群 ${targetGid} 的约会，并通知了相关参与者。`);

    } else {
        // ── 多人约会：移除拒绝者，约会继续 ──
        const remaining = participants.filter(n => n !== rejecterName);

        seal.replyToSender(groupCtx, groupMsg, `⚠️ 【成员退出】\n\n${rejecterName} 退出了这场约会。\n约会继续，请 ${rejecterName} 尽快退群。`);

        // 通知各参与者（新结构：通过 roleName 反查 uid，再取 gid）
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

        // 仅清除拒绝者自己的日程条目（新结构：直接用 uid 匹配）
        const rejecterUidForCleanup = getUidByRoleName(platform, rejecterName);
        if (rejecterUidForCleanup) {
            const rejecterKey = `${platform}:${rejecterUidForCleanup}`;
            if (b_confirmedSchedule[rejecterKey]) {
                b_confirmedSchedule[rejecterKey] = b_confirmedSchedule[rejecterKey].filter(ev => ev.group !== targetGid);
            }
        }
        // 同步其他参与者的 partner 字段，移除已退出者
        for (const uidKey of Object.keys(b_confirmedSchedule)) {
            for (const ev of b_confirmedSchedule[uidKey]) {
                if (ev.group === targetGid && ev.partner && ev.partner !== "多人小群") {
                    const parts = ev.partner.split(/[、,]/).map(s => s.trim()).filter(n => n !== rejecterName);
                    ev.partner = parts.length === 1 ? parts[0] : parts.join("、");
                }
            }
        }
        cachedSet("b_confirmedSchedule", JSON.stringify(b_confirmedSchedule));

        // 更新参与者列表，约会继续
        groupExpireInfo[targetGid].participants = remaining;
        cachedSet("group_expire_info", JSON.stringify(groupExpireInfo));

        // 清理 group_timers 中拒绝者的条目
        const timersForReject = JSON.parse(cachedGet("group_timers") || "{}");
        const timerEntry = timersForReject[targetGid];
        if (timerEntry) {
            if (Array.isArray(timerEntry.participants)) {
                timerEntry.participants = timerEntry.participants.filter(n => n !== rejecterName);
            }
            if (timerEntry.timerStatus) {
                delete timerEntry.timerStatus[rejecterName];
            }
            cachedSet("group_timers", JSON.stringify(timersForReject));
        }

        seal.replyToSender(ctx, msg, `✅ 你已退出群 ${targetGid} 的约会，剩余参与者：${remaining.join("、")}。`);
    }

    return seal.ext.newCmdExecuteResult(true);
};

// ========================
// 🔄 全量同步 指令
// 从 RP 存档服务器一次性拉取所有数据：物品/货币/属性定义/奖励模板/池子
// ========================
let cmd_full_sync = seal.ext.newCmdItemInfo();
cmd_full_sync.name = "全量同步";
cmd_full_sync.help = `【管理员】从RP存档服务器全量拉取数据，覆盖本地存储
全量同步       —— 同步所有数据（物品、货币、属性、奖励模板、池子）
全量同步 预览  —— 只显示存档中的数据摘要，不实际写入

同步内容：
  · 物品/货币注册表（item_registry）
  · 属性定义（rpg_attr_defs / sys_attr_presets）
  · 结戏奖励模板和抽奖配置（end_game_bonus_templates / end_game_draw_config）
  · 抽取池子定义和次数设定（pool_definitions / pool_draw_config）`;

cmd_full_sync.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    if (!isArchiveEnabled()) return seal.replyToSender(ctx, msg, "❌ 未启用RP存档传输，请先在长日设置中开启。");

    const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址。");

    const previewOnly = (cmdArgs.getArgN(1) || "") === "预览";
    const headers = {};
    if (token) headers["X-Archive-Token"] = token;

    seal.replyToSender(ctx, msg, "⏳ 正在从存档服务器拉取数据，请稍候…");

    (async () => {
        try {
            // 并行拉取两个接口
            const [cfgResp, poolResp] = await Promise.all([
                fetch(`${base}/api/config`, { headers }),
                fetch(`${base}/api/pool_config`, { headers })
            ]);

            if (!cfgResp.ok)  throw new Error(`/api/config 返回 ${cfgResp.status}`);
            if (!poolResp.ok) throw new Error(`/api/pool_config 返回 ${poolResp.status}`);

            const cfg  = await cfgResp.json();
            const pool = await poolResp.json();
            if (!pool.ok) throw new Error(`pool_config 错误：${pool.error || "未知"}`);

            // 要同步的 blob 键（从 /api/config 拿）
            const BLOB_KEYS = [
                "item_registry",
                "rpg_attr_defs",
                "sys_attr_presets",
                "end_game_bonus_templates",
                "end_game_draw_config",
                "item_registry_pending",
                "preset_gifts",
                "private_appointment_aliases",
            ];

            if (previewOnly) {
                const itemReg  = JSON.parse(cfg["item_registry"] || "{}");
                const attrDefs = JSON.parse(cfg["rpg_attr_defs"] || "{}");
                const poolDefs = pool.pool_definitions || {};
                const poolCfg  = pool.pool_draw_config  || {};
                const currencies = Object.values(itemReg).filter(i => i.type === "currency").length;
                const items      = Object.values(itemReg).filter(i => i.type !== "currency").length;
                const attrs      = Object.keys(attrDefs).length;
                const pools      = Object.keys(poolDefs).length;
                const totalLimit = poolCfg.total != null ? `${poolCfg.total}次/天` : "无限";
                seal.replyToSender(ctx, msg,
                    `👁️ 存档数据预览：\n` +
                    `📦 物品/货币：货币 ${currencies} 种，物品 ${items} 种\n` +
                    `📊 属性定义：${attrs} 项\n` +
                    `🎲 抽取池：${pools} 个，全局次数 ${totalLimit}\n\n` +
                    `💡 确认无误后发送「全量同步」正式写入。`
                );
                return;
            }

            // 写入 blob 键
            let synced = [];
            for (const key of BLOB_KEYS) {
                if (cfg[key] != null) {
                    cachedSet(key, cfg[key]);
                    synced.push(key);
                }
            }

            // 写入池子数据
            const poolDefs = pool.pool_definitions || {};
            const poolCfg  = pool.pool_draw_config  || { total: null, pools: {} };
            cachedSet("pool_definitions", JSON.stringify(poolDefs));
            cachedSet("pool_draw_config",  JSON.stringify(poolCfg));

            // 统计结果
            const itemReg  = JSON.parse(cfg["item_registry"] || "{}");
            const attrDefs = JSON.parse(cfg["rpg_attr_defs"] || "{}");
            const currencies = Object.values(itemReg).filter(i => i.type === "currency").length;
            const items      = Object.values(itemReg).filter(i => i.type !== "currency").length;
            const poolCount  = Object.keys(poolDefs).length;
            const totalLimit = poolCfg.total != null ? `${poolCfg.total}次/天` : "无限";

            seal.replyToSender(ctx, msg,
                `✅ 全量同步完成！\n` +
                `📦 物品/货币：货币 ${currencies} 种，物品 ${items} 种\n` +
                `📊 属性定义：${Object.keys(attrDefs).length} 项\n` +
                `🎲 抽取池：${poolCount} 个，全局次数 ${totalLimit}`
            );
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 全量同步失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["全量同步"] = cmd_full_sync;


// ========================
// 📤 上传礼品库 指令
// 将本地 preset_gifts 推送到 RP 存档服务器
// ========================
let cmd_upload_gifts = seal.ext.newCmdItemInfo();
cmd_upload_gifts.name = "上传礼品库";
cmd_upload_gifts.help = "【管理员】将本地预设礼品表推送到RP存档服务器";

cmd_upload_gifts.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");
    if (!isArchiveEnabled()) return seal.replyToSender(ctx, msg, "❌ 未启用RP存档传输，请先在长日设置中开启。");

    const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
    const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
    if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址。");

    const raw = cachedGet("preset_gifts") || "{}";
    let gifts;
    try { gifts = JSON.parse(raw); } catch(e) { return seal.replyToSender(ctx, msg, "❌ 本地礼品库数据损坏，无法上传。"); }

    const count = Object.keys(gifts).length;
    if (!count) return seal.replyToSender(ctx, msg, "❌ 本地礼品库为空，没有可上传的内容。");

    const headers = { "Content-Type": "application/json" };
    if (token) headers["X-Archive-Token"] = token;

    (async () => {
        try {
            const resp = await fetch(`${base}/api/sync_config`, {
                method: "POST",
                headers,
                body: JSON.stringify({ preset_gifts: raw })
            });
            if (!resp.ok) throw new Error(`服务器返回 ${resp.status}`);
            const data = await resp.json();
            if (!data.ok) throw new Error(data.error || "未知错误");
            seal.replyToSender(ctx, msg, `✅ 礼品库已上传！共 ${count} 件预设礼品已同步到存档服务器。`);
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 上传失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["上传礼品库"] = cmd_upload_gifts;


// ── 创建新季度 ────────────────────────────────────────────────────────────────
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
    const scheduleArg = cmdArgs.getArgN(3); // "MMDD-MMDD" or empty
    const suppArg     = cmdArgs.getArgN(4); // "MMDD" or empty

    if (!seasonName || seasonName === "help") {
        const ret = seal.ext.newCmdExecuteResult(true);
        ret.showHelp = true;
        return ret;
    }

    // 已有活跃季度
    if (hasActiveSeason()) {
        seal.replyToSender(ctx, msg, `❌ 已有活跃季度「${getSeasonShowName()}」，请先「结束季度」再开新季度。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 角色存储必须为空
    if (!isRoleStorageEmpty()) {
        seal.replyToSender(ctx, msg, "❌ 请先执行「。清空季度数据」清空角色数据，再创建新季度。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 解析档期（必填）
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
        const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
        const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
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

            // 存储本地
            cachedSet("season_show_name", seasonName);
            cachedSet("season_mode", mode);
            cachedSet("season_schedule_start", scheduleStart);
            cachedSet("season_schedule_end",   scheduleEnd);
            cachedSet("season_supplement_end", supplementEnd);

            // 初始化默认物品（仅补空缺，已有则跳过）
            const reg = JSON.parse(cachedGet("item_registry") || "{}");
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
            if (regChanged) cachedSet("item_registry", JSON.stringify(reg));

            // 构建档期提示
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

// ── 修改档期 ──────────────────────────────────────────────────────────────────
let cmd_set_schedule = seal.ext.newCmdItemInfo();
cmd_set_schedule.name = "修改档期";
cmd_set_schedule.help = `用法：。修改档期 MMDD-MMDD [补戏MMDD]
同步更新存档服务器和本地缓存的档期设置。

示例：
  修改档期 0528-0601          仅设主档期
  修改档期 0528-0601 0604     主档期 + 补戏截止
  修改档期 清空               清空所有档期限制`;
cmd_set_schedule.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足");
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
        const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
        const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
        if (!base) return seal.replyToSender(ctx, msg, "❌ 未配置存档服务器地址");

        try {
            const resp = await fetch(`${base}/api/update_schedule`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify({ schedule_start: scheduleStart, schedule_end: scheduleEnd, supplement_end: supplementEnd })
            });
            const data = await resp.json();
            if (!data.ok) return seal.replyToSender(ctx, msg, `❌ 更新失败：${data.error || resp.status}`);

            // 更新本地缓存
            cachedSet("season_schedule_start", scheduleStart);
            cachedSet("season_schedule_end",   scheduleEnd);
            cachedSet("season_supplement_end", supplementEnd);

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

// ── 结束季度 ──────────────────────────────────────────────────────────────────
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
        const base  = (seal.ext.getStringConfig(ext, "RP存档服务器地址") || "").replace(/\/$/, "");
        const token = seal.ext.getStringConfig(ext, "RP存档Token") || "";
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

            // 拉取个人报告并群发（仅开启时）
            if (cachedGet("end_season_report_enabled") === "true") {
                try {
                    const reportResp = await fetch(`${base}/api/season_report/${data.show_id}`, {
                        headers: { "X-Archive-Token": token }
                    });
                    const report = await reportResp.json();
                    if (report.ok) {
                        const platform = ctx.platform || "QQ";
                        const privGroups = JSON.parse(cachedGet("a_private_group") || "{}");
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

                            // 互动对象 Top3
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

                            // 最活跃时段称号
                            if (s.time_title) {
                                lines.push(
                                    ``,
                                    `⏰ 你最喜欢互动的时间是 ${s.peak_slot}`,
                                    `   专属称号：「${s.time_title}」`,
                                    `   ${s.time_tagline}`
                                );
                            }

                            // 最长一场戏摘录
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

            // 注意：此处不清除 season_show_name，交由「清空季度数据」完成
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 请求失败：${e.message || String(e)}`);
        }
    })();

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束季度"] = cmd_end_season;

// ── 季末报告开关 ──────────────────────────────────────────────────────────────
let cmd_end_report_toggle = seal.ext.newCmdItemInfo();
cmd_end_report_toggle.name = "季末报告";
cmd_end_report_toggle.help = `用法：。季末报告 开启/关闭/状态
控制结束季度时是否自动向每位玩家的个人群发送互动报告。
⚠️ 开启后，请确保执行「结束季度」时 bot 仍在所有玩家的个人群内。`;
cmd_end_report_toggle.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足");
    const arg = (cmdArgs.getArgN(1) || "").trim();
    if (arg === "开启") {
        cachedSet("end_season_report_enabled", "true");
        seal.replyToSender(ctx, msg,
            `✅ 季末报告已开启。\n` +
            `⚠️ 提醒：执行「结束季度」时请确保 bot 仍在所有玩家的个人群内，否则无法发送。`
        );
    } else if (arg === "关闭") {
        cachedSet("end_season_report_enabled", "false");
        seal.replyToSender(ctx, msg, `✅ 季末报告已关闭，结束季度时将不再发送个人报告。`);
    } else {
        const enabled = cachedGet("end_season_report_enabled") === "true";
        seal.replyToSender(ctx, msg,
            `📊 季末报告当前状态：${enabled ? "✅ 开启" : "❌ 关闭"}\n` +
            `使用「。季末报告 开启」或「。季末报告 关闭」切换。`
        );
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["季末报告"] = cmd_end_report_toggle;
