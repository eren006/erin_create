// ==UserScript==
// @name         社交系统
// @author       长日将尽
// @version      1.4.0
// @description  秘密论坛、寄信与关系线系统。所有数据存储在主插件 changri 中。
// @timestamp    1778742000
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E7%A4%BE%E4%BA%A4.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E7%A4%BE%E4%BA%A4.js
// ==/UserScript==

function getMainExt() {
    const main = seal.ext.find('changri');
    if (!main) {
        console.error("❌ 社交系统：未找到主插件 changri，请检查主插件是否已加载");
        return null;
    }
    return main;
}

let ext = seal.ext.find('changriV1');
if (!ext) {
    ext = seal.ext.new("changriV1", "长日将尽", "1.4.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

// ========================
// 核心依赖：主插件共享 API（globalThis.__changriApi，调用时懒获取）
// 主插件已更新时全部委托给它；否则走下方兼容实现（直读主插件存储）
// ========================

function getApi() { return globalThis.__changriApi || null; }

function mainStorGet(key) {
    const api = getApi();
    if (api) return api.kvGetRaw(key);
    const m = getMainExt();
    return m ? m.storageGet(key) : null;
}

function mainStorSet(key, val) {
    const api = getApi();
    if (api) { api.kvSetRaw(key, val); return; }
    const m = getMainExt();
    if (m) m.storageSet(key, val);
}

function getPrimaryUid(platform, uid) {
    const api = getApi();
    if (api) return api.getPrimaryUid(platform, uid);
    try {
        const extras = JSON.parse(mainStorGet("extra_accounts") || "{}");
        return extras[`${platform}:${uid}`] || uid;
    } catch (e) { return uid; }
}

function getRoleName(ctx, msg) {
    const api = getApi();
    if (api) return api.getRoleName(ctx, msg);
    try {
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        const platform = msg.platform;
        const rawUid = msg.sender.userId.replace(`${platform}:`, "");
        const uid = getPrimaryUid(platform, rawUid);
        return apg[platform]?.[uid]?.[0] || null;
    } catch (e) { return null; }
}

function getUidByRoleName(platform, roleName) {
    const api = getApi();
    if (api) return api.getUidByRoleName(platform, roleName);
    try {
        const apg = JSON.parse(mainStorGet("a_private_group") || "{}");
        const roles = apg[platform] || {};
        return Object.entries(roles).find(([_, v]) => v[0] === roleName)?.[0] || null;
    } catch (e) { return null; }
}

function resolveUidToName(platform, uid) {
    const api = getApi();
    if (api) return api.resolveUidToName(platform, uid);
    try {
        return JSON.parse(mainStorGet("a_private_group") || "{}")?.[platform]?.[uid]?.[0] || uid;
    } catch (e) { return uid; }
}

function isUserAdmin(ctx, msg) {
    const api = getApi();
    if (api) return api.isUserAdmin(ctx, msg);
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    try {
        const a_adminList = JSON.parse(mainStorGet("a_adminList") || "{}");
        return ctx.privilegeLevel === 100 || (a_adminList[platform] && a_adminList[platform].includes(uid));
    } catch (e) { return false; }
}

function isUserFeatureEnabled(uid, key, defaultValue = true) {
    const api = getApi();
    if (api) return api.isUserFeatureEnabled(uid, key, defaultValue);
    const blockMap = JSON.parse(mainStorGet("feature_user_blocklist") || "{}");
    const personConfig = blockMap[uid];
    if (personConfig && personConfig[key] !== undefined) return personConfig[key];
    return defaultValue;
}

// 读取主插件存储的整数型设置（兼容 JSON 编码的 '"500"' 与裸字符串 '500' 两种格式）
function getMainStorageInt(key, defaultVal) {
    const api = getApi();
    if (api) return api.getStorageInt(key, defaultVal);
    const raw = mainStorGet(key);
    if (!raw) return defaultVal;
    try { const v = parseInt(JSON.parse(raw)); return isNaN(v) ? defaultVal : v; }
    catch (e) { const v = parseInt(raw); return isNaN(v) ? defaultVal : v; }
}

function recordMeetingAndAnnounce(subtype, platform, ctx, endPoint) {
    const api = getApi();
    if (api) return api.recordMeetingAndAnnounce(subtype, platform, ctx, endPoint);
    const subtypeKeyMap = {
        "电话": "call", "私密": "private", "寄信": "chaosletter",
        "心动信": "lovemail", "礼物": "gift", "心愿": "wish",
        "官约": "official", "拉线": "relation"
    };
    const keyType = subtypeKeyMap[subtype] || "unknown";
    const storageKey = `a_meetingCount_${keyType}`;
    let count = parseInt(mainStorGet(storageKey) || "0");
    count++;
    mainStorSet(storageKey, count.toString());

    const groupId = JSON.parse(mainStorGet("adminAnnounceGroupId") || "null");
    if (groupId) {
        const frequency = parseInt(mainStorGet("announceFrequency") || "5");
        if (count % frequency === 0) {
            const labels = {
                "电话": ["☎️", "电话"], "私密": ["💫", "私密约会"], "寄信": ["📮", "寄信"],
                "心动信": ["💌", "心动信派送"], "礼物": ["🎁", "礼物赠送"],
                "心愿": ["🌠", "心愿"], "官约": ["🏢", "官方约会"], "拉线": ["🔗", "关系线记录"]
            };
            const [emoji, label] = labels[subtype] || ["📝", "互动"];
            const broadcastText = `${emoji} 【第${count}次${label}记录】`;
            const msgDivineLog = seal.newMessage();
            msgDivineLog.messageType = "group";
            msgDivineLog.groupId = `${platform}-Group:${groupId}`;
            const ctxDivineLog = seal.createTempCtx(endPoint, msgDivineLog);
            seal.replyToSender(ctxDivineLog, msgDivineLog, broadcastText);
        }
    }
}

// ========================
// WS 工具函数（从主插件读配置）
// ========================

function ws(postData, ctx, msg, successreply) {
    const api = getApi();
    if (api) return api.ws(postData, ctx, msg, successreply);
    const main = getMainExt();
    if (!main) return;
    const wsUrl = seal.ext.getStringConfig(main, "ws地址");
    const token = seal.ext.getStringConfig(main, "ws Access token");
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
    const wsConn = new WebSocket(connectionUrl);
    let isClosed = false;
    const closeSafe = (reason) => {
        if (!isClosed) {
            isClosed = true;
            clearTimeout(timeoutId);
            if (wsConn.readyState === WebSocket.OPEN || wsConn.readyState === WebSocket.CONNECTING) {
                wsConn.close(1000, reason);
            }
        }
    };
    const timeoutId = setTimeout(() => { if (!isClosed) closeSafe("TIMEOUT"); }, 3000);
    wsConn.onopen = () => {
        try { wsConn.send(JSON.stringify(postData)); } catch (e) { closeSafe("SERIALIZE_ERROR"); }
    };
    wsConn.onmessage = (event) => {
        try {
            const response = JSON.parse(event.data);
            if (response.post_type === "meta_event") return;
            if (response.echo !== currentEcho) return;
            if (response.status === 'ok' || response.retcode === 0) {
                if (successreply) seal.replyToSender(ctx, msg, successreply);
                closeSafe("ACTION_SUCCESS");
            } else {
                closeSafe("ACTION_FAILED");
            }
        } catch (e) { closeSafe("PARSE_ERROR"); }
    };
    wsConn.onerror = () => closeSafe("WS_ERROR");
}

// ========================
// 通用工具函数
// ========================

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
        console.error(`[论坛] sendTextToGroup 异常:`, e);
    }
};

// ========================
// 🗨️ 秘密论坛系统
// ========================

seal.ext.registerIntConfig(ext, "forumMaxLength", 500, "论坛内容最大长度", "发帖和回复的最大字符数");

const getForumPosts = () => JSON.parse(mainStorGet("forum_posts") || "[]");
const saveForumPosts = (posts) => mainStorSet("forum_posts", JSON.stringify(posts));

function sendToAnnounceGroup(ctx, platform, text) {
    const announceGid = mainStorGet("song_group_id");
    if (announceGid) {
        sendTextToGroup(platform, announceGid, text);
    } else {
        console.log("[论坛系统] 尚未配置 song_group_id，跳过公告。");
    }
}

function sendForumForward(ctx, msg, nodes) {
    const gid = msg.groupId.replace(/[^\d]/g, "");
    ws({
        "action": "send_group_forward_msg",
        "params": { "group_id": parseInt(gid, 10), "messages": nodes }
    }, ctx, msg, "");
}

function findPostById(postId) {
    const posts = getForumPosts();
    const index = posts.findIndex(p => p.id === postId && p.status === "active");
    return index !== -1 ? { post: posts[index], index: index } : null;
}

function extractMentions(content, platform) {
    const main = getMainExt();
    if (!main) return [];
    const priv = JSON.parse(mainStorGet("a_private_group") || "{}")[platform] || {};
    const validNames = new Set(Object.values(priv).map(v => v[0]));
    const matches = [...(content.matchAll(/@(\S+)/g) || [])].map(m => m[1]);
    return [...new Set(matches.filter(n => validNames.has(n)))];
}

function sendMentionNotice(platform, mentionedName, postId, authorName) {
    const uid = getUidByRoleName(platform, mentionedName);
    if (!uid || /^npc_/.test(uid)) return;
    const main = getMainExt();
    if (!main) return;
    const pGid = JSON.parse(mainStorGet("a_private_group") || "{}")[platform]?.[uid]?.[1];
    if (!pGid || pGid === "0") return;
    sendTextToGroup(platform, pGid, `📣 「${authorName}」在论坛帖子 [${postId}] 的回复中提到了你！`);
}

let cmd_post_forum = seal.ext.newCmdItemInfo();
cmd_post_forum.name = "发帖";
cmd_post_forum.help = ".发帖 (署名) [内容] —— 发表一篇新帖子";
cmd_post_forum.solve = (ctx, msg, cmdArgs) => {
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 你还不是本系统的会员，请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const roleName = getRoleName(ctx, msg) || ctx.player.name;
    if (roleName) {
        const forumUid = getUidByRoleName(msg.platform, roleName);
        if (forumUid && !isUserFeatureEnabled(forumUid, "enable_forum")) {
            seal.replyToSender(ctx, msg, "🚫 你的论坛功能已被关闭。");
            return seal.ext.newCmdExecuteResult(true);
        }
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

    const forumMaxLen = getMainStorageInt("forum_max_length", 500);
    if (content.length > forumMaxLen) {
        seal.replyToSender(ctx, msg, `⚠️ 内容过长（${content.length} 字），论坛发帖上限为 ${forumMaxLen} 字，请精简后再提交。`);
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

let cmd_reply_post = seal.ext.newCmdItemInfo();
cmd_reply_post.name = "回复帖子";
cmd_reply_post.help = ".回复帖子 [贴号] (引用N|署名) [内容]";
cmd_reply_post.solve = (ctx, msg, cmdArgs) => {
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 你还不是本系统的会员，请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const postId = cmdArgs.getArgN(1);
    const roleName = getRoleName(ctx, msg) || ctx.player.name;
    let author, content, quoteFloor = null, quoteContent = null;
    const arg2 = cmdArgs.getArgN(2);
    const quoteMatch = arg2 && arg2.match(/^引用(\d+)$/);

    if (quoteMatch) {
        quoteFloor = parseInt(quoteMatch[1]);
        author = roleName;
        content = msg.message.replace(/^[。.]?回复帖子\s+\S+\s+\S+\s*/, "").trim();
    } else if (cmdArgs.args.length > 2) {
        author = arg2;
        content = msg.message.replace(/^[。.]?回复帖子\s+\S+\s+\S+\s*/, "").trim();
    } else {
        author = roleName;
        content = msg.message.replace(/^[。.]?回复帖子\s+\S+\s*/, "").trim();
    }

    if (!postId || !content) {
        seal.replyToSender(ctx, msg, "❌ 格式错误！\n格式：回复帖子 贴号 内容\n引用楼层：回复帖子 贴号 引用N 内容（引用0=楼主）");
        return seal.ext.newCmdExecuteResult(true);
    }

    const forumMaxLen = getMainStorageInt("forum_max_length", 500);
    if (content.length > forumMaxLen) {
        seal.replyToSender(ctx, msg, `⚠️ 内容过长（${content.length} 字），论坛回复上限为 ${forumMaxLen} 字，请精简后再提交。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const result = findPostById(postId);
    if (!result) {
        seal.replyToSender(ctx, msg, `❌ 找不到帖子 [${postId}]`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (quoteFloor !== null) {
        const srcPost = result.post;
        if (quoteFloor === 0) {
            const c = srcPost.content;
            quoteContent = c.length > 60 ? c.substring(0, 60) + "…" : c;
        } else {
            const qReply = srcPost.replies[quoteFloor - 1];
            if (!qReply) {
                seal.replyToSender(ctx, msg, `❌ 楼层 L${quoteFloor} 不存在（当前共 ${srcPost.replies.length} 楼）`);
                return seal.ext.newCmdExecuteResult(true);
            }
            const c = qReply.content;
            quoteContent = c.length > 60 ? c.substring(0, 60) + "…" : c;
        }
    }

    const posts = getForumPosts();
    const newReply = { author, content, timestamp: new Date().toLocaleString(), likes: [], dislikes: [] };
    if (quoteFloor !== null) { newReply.quoteFloor = quoteFloor; newReply.quoteContent = quoteContent; }
    posts[result.index].replies.push(newReply);
    saveForumPosts(posts);

    seal.replyToSender(ctx, msg, `✅ 已回复到帖子 [${postId}]`);
    sendToAnnounceGroup(ctx, msg.platform, `💬 【论坛回复】\n📌 贴号：${postId}\n👤 ${author}\n📝 ${content}`);

    const platform = msg.platform;
    extractMentions(content, platform).forEach(name => {
        if (name !== author) sendMentionNotice(platform, name, postId, author);
    });

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["回复帖子"] = cmd_reply_post;

function handleVote(ctx, msg, cmdArgs, isLike) {
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 你还不是本系统的会员，请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }
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
    sendToAnnounceGroup(ctx, msg.platform, `${isLike ? '❤️' : '👎'} 【论坛动态】\n👤 ${author} 对帖子 [${postId}] 进行了${typeStr}\n🔥 赞：${post.likes.length} | ❄️ 踩：${post.dislikes.length}`);
    return seal.ext.newCmdExecuteResult(true);
}

let cmd_like = seal.ext.newCmdItemInfo();
cmd_like.name = "点赞";
cmd_like.solve = (ctx, msg, cmdArgs) => handleVote(ctx, msg, cmdArgs, true);
ext.cmdMap["点赞"] = cmd_like;

let cmd_dislike = seal.ext.newCmdItemInfo();
cmd_dislike.name = "点踩";
cmd_dislike.solve = (ctx, msg, cmdArgs) => handleVote(ctx, msg, cmdArgs, false);
ext.cmdMap["点踩"] = cmd_dislike;

function handleFloorVote(ctx, msg, cmdArgs, isLike) {
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 你还不是本系统的会员，请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const postId = cmdArgs.getArgN(1);
    const floorStr = cmdArgs.getArgN(2);
    const author = cmdArgs.getArgN(3) || senderRoleName;
    const typeStr = isLike ? "点赞" : "点踩";

    if (!postId || !floorStr || !/^\d+$/.test(floorStr)) {
        seal.replyToSender(ctx, msg, `格式：${typeStr}楼层 帖ID 楼层号 署名`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const floorNum = parseInt(floorStr);
    const result = findPostById(postId);
    if (!result) {
        seal.replyToSender(ctx, msg, `❌ 找不到帖子 [${postId}]`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const posts = getForumPosts();
    const reply = posts[result.index].replies[floorNum - 1];
    if (!reply) {
        seal.replyToSender(ctx, msg, `❌ 楼层 L${floorNum} 不存在`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!reply.likes) reply.likes = [];
    if (!reply.dislikes) reply.dislikes = [];

    const myList = isLike ? reply.likes : reply.dislikes;
    const otherList = isLike ? reply.dislikes : reply.likes;

    if (myList.includes(author)) {
        seal.replyToSender(ctx, msg, "⚠️ 你已经表过态啦～");
        return seal.ext.newCmdExecuteResult(true);
    }
    const idx = otherList.indexOf(author);
    if (idx !== -1) otherList.splice(idx, 1);
    myList.push(author);
    saveForumPosts(posts);

    seal.replyToSender(ctx, msg, `✅ 对 L${floorNum} ${typeStr}成功！👍 ${reply.likes.length} | 👎 ${reply.dislikes.length}`);
    return seal.ext.newCmdExecuteResult(true);
}

let cmd_like_floor = seal.ext.newCmdItemInfo();
cmd_like_floor.name = "点赞楼层";
cmd_like_floor.solve = (ctx, msg, cmdArgs) => handleFloorVote(ctx, msg, cmdArgs, true);
ext.cmdMap["点赞楼层"] = cmd_like_floor;

let cmd_dislike_floor = seal.ext.newCmdItemInfo();
cmd_dislike_floor.name = "点踩楼层";
cmd_dislike_floor.solve = (ctx, msg, cmdArgs) => handleFloorVote(ctx, msg, cmdArgs, false);
ext.cmdMap["点踩楼层"] = cmd_dislike_floor;

let cmd_view_posts = seal.ext.newCmdItemInfo();
cmd_view_posts.name = "查看帖子";
cmd_view_posts.solve = (ctx, msg, cmdArgs) => {
    const senderRoleName = getRoleName(ctx, msg);
    if (!senderRoleName) {
        seal.replyToSender(ctx, msg, "✨ 你还不是本系统的会员，请先使用「创建新角色」来认领你的身份吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

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
            let replyContent = "";
            if (r.quoteFloor !== undefined && r.quoteFloor !== null) {
                const floorLabel = r.quoteFloor === 0 ? "楼主" : `L${r.quoteFloor}`;
                replyContent += `「引用 ${floorLabel}」\n${r.quoteContent}\n${"─".repeat(14)}\n`;
            }
            replyContent += r.content;
            const rl = (r.likes || []).length, rd = (r.dislikes || []).length;
            if (rl > 0 || rd > 0) replyContent += `\n👍 ${rl} | 👎 ${rd}`;
            nodes.push({ type: "node", data: { name: `${r.author} (L${i + 1})`, uin: "2852199344", content: replyContent } });
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
        sendToAnnounceGroup(ctx, msg.platform, `🛡️ 【论坛管理】\n管理员删除了帖子：[${postId}]\n理由：违反社区规范`);
    } else {
        seal.replyToSender(ctx, msg, "❌ 找不到该帖子或已被删除。");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除帖子"] = cmd_delete_post;

// ========================
// 🔗 关系线系统
// ========================

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
    const groups = JSON.parse(mainStorGet("a_private_group") || "{}");

    // 1. 获取对方的绑定信息（uid为key的新结构）
    const toUid = getUidByRoleName(platform, toRoleName);
    const toAddr = toUid ? groups[platform]?.[toUid] : null;
    if (!toAddr || !details || details.length === 0) return;

    // 2. 获取自己的真实QQ
    const sourceUid = msg.sender.userId.replace(`${platform}:`, "");

    // 3. 确定目标群ID
    let targetGid;
    if (self) {
        const fromUidKey = getUidByRoleName(platform, fromRoleName);
        const selfAddr = fromUidKey ? groups[platform]?.[fromUidKey] : null;
        if (!selfAddr) return;
        targetGid = selfAddr[1];
    } else {
        targetGid = toAddr[1];
    }

    // 4. 获取当前用户角色名
    const sourceRoleName = RelationshipUtils.getRoleName(ctx, msg, platform);

    // 5. 统计总字数
    const totalChars = details.reduce((sum, d) => sum + (d.text?.length || 0), 0);
    const MAX_DETAIL_CHARS = getMainStorageInt("max_detail_chars", 500);
    const SPLIT_THRESHOLD = getMainStorageInt("forward_split_threshold", 4000);
    const gid = parseInt(targetGid.replace(/[^\d]/g, ""), 10);

    const makeNode = d => {
        const isFromMe = (d.from === sourceRoleName);
        return { type: "node", data: { name: d.from, uin: isFromMe ? sourceUid : toUid, content: d.text } };
    };

    const headerBase = self
        ? `📜 你与「${toRoleName}」的关系细节`
        : `📜 角色「${sourceRoleName}」更新了与你的关系细节`;
    const charInfo = `共 ${details.length} 条 | 单条上限 ${MAX_DETAIL_CHARS} 字 | 累计 ${totalChars} 字`;

    if (totalChars > SPLIT_THRESHOLD) {
        const mid = Math.ceil(details.length / 2);
        const part1 = details.slice(0, mid);
        const part2 = details.slice(mid);
        const header1 = { type: "node", data: { name: "关系线档案", uin: "10001",
            content: `${headerBase}\n${charInfo}\n⚠️ 内容较多，已拆分为2条转发 · 第1部分（共${mid}条）` } };
        const header2 = { type: "node", data: { name: "关系线档案", uin: "10001",
            content: `${headerBase}\n第2部分（共${details.length - mid}条）` } };
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: [header1, ...part1.map(makeNode)] } }, ctx, msg, "");
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: [header2, ...part2.map(makeNode)] } }, ctx, msg, "");
    } else {
        const header = { type: "node", data: { name: "关系线档案", uin: "10001",
            content: `${headerBase}\n${charInfo}` } };
        ws({ action: "send_group_forward_msg", params: { group_id: gid, messages: [header, ...details.map(makeNode)] } }, ctx, msg, "");
    }
}

function getTargetAddr(platform, roleName) {
    const groups = JSON.parse(mainStorGet("a_private_group") || "{}");
    const uid = getUidByRoleName(platform, roleName);
    if (!uid) return null;
    const entry = groups[platform]?.[uid];
    return entry ? [uid, entry[1]] : null;
}

const RelationshipUtils = {
    getRoleName: (ctx, msg, platform) => {
        const rawUid = msg.sender.userId.replace(`${platform}:`, "");
        const uid = getPrimaryUid(platform, rawUid);
        const groups = JSON.parse(mainStorGet("a_private_group") || "{}");
        return groups[platform]?.[uid]?.[0] || null;
    },
    getData: (key) => JSON.parse(mainStorGet(key) || "{}"),
    setData: (key, data) => mainStorSet(key, JSON.stringify(data)),
    isEnabled: () => JSON.parse(mainStorGet("relationship_system_enabled") || "false")
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

    const MAX_DETAIL_CHARS = getMainStorageInt("max_detail_chars", 500);
    const charCount = content.length;
    if (charCount > MAX_DETAIL_CHARS) {
        return seal.replyToSender(ctx, msg, `⚠️ 内容过长（${charCount} 字），单条拉线上限为 ${MAX_DETAIL_CHARS} 字，请精简后再提交。`);
    }

    let relData = RelationshipUtils.getData("relationship_lines") || {};
    if (!relData[platform]) relData[platform] = {};

    const sendUid = getUidByRoleName(platform, sendName);
    const toUid = getUidByRoleName(platform, toName);
    if (!sendUid || !toUid) return seal.replyToSender(ctx, msg, "❌ 找不到角色");

    if (!relData[platform][sendUid]) relData[platform][sendUid] = {};
    if (!relData[platform][toUid]) relData[platform][toUid] = {};

    let rel = relData[platform][sendUid][toUid] || relData[platform][toUid][sendUid];
    const isNewRel = !rel;

    if (isNewRel) {
        const maxRel = getMainStorageInt("max_relationships_per_user", 20);
        const currentCount = Object.values(relData[platform][sendUid]).filter(r => r.initiator === sendName).length;

        if (currentCount >= maxRel) return seal.replyToSender(ctx, msg, `⚠️ 你的发起额度已达上限 (${maxRel})`);

        rel = { initiator: sendName, confirmed: false, details: [] };
    }

    if (!rel.details) rel.details = [];

    const MAX_DETAIL_COUNT = getMainStorageInt("max_detail_count", 20);
    if (rel.details.length >= MAX_DETAIL_COUNT) {
        return seal.replyToSender(ctx, msg, `⚠️ 你们的关系线已达段数上限（${MAX_DETAIL_COUNT} 段），无法继续添加。`);
    }

    const MAX_REL_TOTAL_CHARS = getMainStorageInt("max_rel_total_chars", 3000);
    const currentTotal = rel.details.reduce((sum, d) => sum + (d.text?.length || 0), 0);
    if (currentTotal + charCount > MAX_REL_TOTAL_CHARS) {
        return seal.replyToSender(ctx, msg, `⚠️ 添加后将超过总字数上限（${MAX_REL_TOTAL_CHARS} 字，当前已有 ${currentTotal} 字），请精简内容。`);
    }

    rel.details.push({ text: content, from: sendName });

    relData[platform][sendUid][toUid] = rel;
    relData[platform][toUid][sendUid] = rel;

    RelationshipUtils.setData("relationship_lines", relData);

    const totalCharsNow = rel.details.reduce((sum, d) => sum + (d.text?.length || 0), 0);
    const SPLIT_THRESHOLD = getMainStorageInt("forward_split_threshold", 4000);
    const segCount = rel.details.length;
    const splitNote = totalCharsNow > SPLIT_THRESHOLD ? " · 查看时将拆分为2条转发" : "";
    const splitHint = `（本条 ${charCount} 字 · 累计 ${totalCharsNow}/${MAX_REL_TOTAL_CHARS} 字 · ${segCount}/${MAX_DETAIL_COUNT} 段${splitNote}）`;
    const newRelHint = isNewRel ? "✨ 关系线已建立。\n" : "";

    const addr = getTargetAddr(platform, toName);
    if (addr) {
        sendNewDetailNotification(ctx, msg, toName, content, sendName, addr[1]);
        sendCombinedDetails(ctx, msg, toName, sendName, rel.details, false);
        seal.replyToSender(ctx, msg, `${newRelHint}✅ 细节已同步至「${toName}」的绑定群 (${addr[1]})\n${splitHint}`);
    } else {
        seal.replyToSender(ctx, msg, `${newRelHint}✅ 细节已记录，但「${toName}」尚未绑定注册群，无法实时同步。\n${splitHint}`);
    }

    recordMeetingAndAnnounce("拉线", platform, ctx, ctx.endPoint);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["拉线"] = cmd_add_rel_detail;

function sendNewDetailNotification(ctx, msg, toRoleName, content, fromRoleName, targetGid) {
    const platform = msg.platform;
    const groups = JSON.parse(mainStorGet("a_private_group") || "{}");
    const toUid = getUidByRoleName(platform, toRoleName);
    const toAddr = toUid ? groups[platform]?.[toUid] : null;
    if (!toAddr) return;

    const targetGidNum = parseInt(targetGid.replace(/[^\d]/g, ""), 10);
    if (isNaN(targetGidNum)) return;

    const message = `📝 来自「${fromRoleName}」的新关系细节：\n${content}\n\n（使用「。查看关系线 ${fromRoleName}」查看完整记录）`;
    ws({ action: "send_group_msg", params: { group_id: targetGidNum, message: message } }, ctx, msg, "");
}

let cmd_confirm_relationship = seal.ext.newCmdItemInfo();
cmd_confirm_relationship.name = "确认关系线";
cmd_confirm_relationship.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);

    let relData = RelationshipUtils.getData("relationship_lines");
    const sendUid = getUidByRoleName(platform, sendName);
    const toUid = getUidByRoleName(platform, toName);
    if (!sendUid || !toUid || !relData[platform]?.[sendUid]?.[toUid]) return seal.replyToSender(ctx, msg, "未找到该关系线");

    relData[platform][sendUid][toUid].confirmed = true;
    if (relData[platform][toUid]?.[sendUid]) relData[platform][toUid][sendUid].confirmed = true;

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 你已确认与「${toName}」的关系线为完成状态。`);

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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "权限不足"), seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const nameA = cmdArgs.getArgN(1);
    const nameB = cmdArgs.getArgN(2);
    const content = cmdArgs.args.slice(2).join(' ').trim();

    if (!nameA || !nameB || !content) {
        return seal.replyToSender(ctx, msg, "格式：。设置强制关系线 角色A 角色B 描述内容");
    }

    let relData = RelationshipUtils.getData("relationship_lines");
    const forceNode = {
        initiator: "SYSTEM",
        confirmed: true,
        isMandatory: true,
        details: [{ text: `[系统设定] ${content}`, time: new Date().toLocaleString(), from: "管理员" }]
    };

    const uidA = getUidByRoleName(platform, nameA);
    const uidB = getUidByRoleName(platform, nameB);
    if (!uidA || !uidB) return seal.replyToSender(ctx, msg, `❌ 找不到角色「${!uidA ? nameA : nameB}」`);

    if (!relData[platform]) relData[platform] = {};
    if (!relData[platform][uidA]) relData[platform][uidA] = {};
    if (!relData[platform][uidB]) relData[platform][uidB] = {};

    relData[platform][uidA][uidB] = forceNode;
    relData[platform][uidB][uidA] = { ...forceNode, received: true };

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 已成功为「${nameA}」与「${nameB}」建立强制关系线。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["设置强制关系线"] = cmd_set_forced_rel;

let cmd_del_rel = seal.ext.newCmdItemInfo();
cmd_del_rel.name = "删除关系线";
cmd_del_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足"), seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform, nameA = cmdArgs.getArgN(1), nameB = cmdArgs.getArgN(2);
    let data = RelationshipUtils.getData("relationship_lines");
    const uidA = getUidByRoleName(platform, nameA);
    const uidB = getUidByRoleName(platform, nameB);
    if (!uidA) return seal.replyToSender(ctx, msg, `❌ 找不到角色「${nameA}」`);
    if (!uidB) return seal.replyToSender(ctx, msg, `❌ 找不到角色「${nameB}」`);
    if (data[platform]) {
        if (data[platform][uidA]) delete data[platform][uidA][uidB];
        if (data[platform][uidB]) delete data[platform][uidB][uidA];
        RelationshipUtils.setData("relationship_lines", data);
        seal.replyToSender(ctx, msg, "✅ 已删除该关系线");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除关系线"] = cmd_del_rel;

let cmd_clear_rel = seal.ext.newCmdItemInfo();
cmd_clear_rel.name = "清空关系线";
cmd_clear_rel.help = "。清空关系线 MMDD\n清空当前平台全部关系线（需输入当日日期码确认，如0526）";
cmd_clear_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "⚠️ 权限不足"), seal.ext.newCmdExecuteResult(true);
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

let cmd_withdraw_relation = seal.ext.newCmdItemInfo();
cmd_withdraw_relation.name = "撤回关系";
cmd_withdraw_relation.help = "。撤回关系 对方角色名 要撤回的内容（精确匹配，仅撤回自己发送的细节）";
cmd_withdraw_relation.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const sendName = RelationshipUtils.getRoleName(ctx, msg, platform);
    const toName = cmdArgs.getArgN(1);
    const content = cmdArgs.args.slice(1).join(' ').trim();

    if (!sendName || !toName || !content) {
        return seal.replyToSender(ctx, msg, "格式：。撤回关系 对方角色名 要撤回的内容");
    }

    let relData = RelationshipUtils.getData("relationship_lines");
    const sendUid = getUidByRoleName(platform, sendName);
    const toUid = getUidByRoleName(platform, toName);
    let rel = sendUid && toUid ? (relData[platform]?.[sendUid]?.[toUid] || relData[platform]?.[toUid]?.[sendUid]) : null;
    if (!rel || !rel.details || rel.details.length === 0) {
        return seal.replyToSender(ctx, msg, "没有可撤回的细节记录。");
    }

    const idx = rel.details.findIndex(d => d.from === sendName && d.text === content);
    if (idx === -1) {
        return seal.replyToSender(ctx, msg, `未找到你发送的匹配内容：「${content}」\n可使用「。查看关系线 ${toName}」查看所有细节。`);
    }

    const removed = rel.details[idx];
    rel.details.splice(idx, 1);

    const otherRel = toUid && sendUid ? (relData[platform]?.[toUid]?.[sendUid] || relData[platform]?.[sendUid]?.[toUid]) : null;
    if (otherRel && otherRel.details && otherRel !== rel) {
        const otherIdx = otherRel.details.findIndex(d => d.from === sendName && d.text === content);
        if (otherIdx !== -1) otherRel.details.splice(otherIdx, 1);
    }

    RelationshipUtils.setData("relationship_lines", relData);
    seal.replyToSender(ctx, msg, `✅ 已成功撤回你发送的细节：\n"${removed.text}"`);

    const addr = getTargetAddr(platform, toName);
    if (addr) {
        ws({
            action: "send_group_msg",
            params: { group_id: parseInt(addr[1], 10), message: `🗑️ 「${sendName}」撤回了一条发给你的关系细节：\n"${removed.text}"` }
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
    const myUid = getUidByRoleName(platform, sendName);
    const myRelsRaw = myUid ? (relData[platform]?.[myUid] || {}) : {};
    const myRels = {};
    for (const [uid, rel] of Object.entries(myRelsRaw)) {
        const name = resolveUidToName(platform, uid);
        myRels[name] = rel;
    }

    if (toName) {
        const rel = myRels[toName];
        if (!rel) return seal.replyToSender(ctx, msg, `你与「${toName}」之间暂无关系记录。`);
        if (!rel.details || rel.details.length === 0) {
            return seal.replyToSender(ctx, msg, `你与「${toName}」虽有关系线，但尚未添加任何细节。`);
        }
        sendCombinedDetails(ctx, msg, toName, sendName, rel.details, true);
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = `📚 「${sendName}」的关系线列表：\n`;
    const maxRel = getMainStorageInt("max_relationships_per_user", 20);
    const SPLIT_THRESHOLD = getMainStorageInt("forward_split_threshold", 4000);
    let activeCount = 0;
    let listContent = "";

    Object.entries(myRels).forEach(([name, data]) => {
        const isSystem = data.initiator === "SYSTEM";
        if (!isSystem && data.initiator === sendName) activeCount++;
        const statusIcon = data.confirmed ? "✅" : "⏳";
        const typeTag = isSystem ? "【强制】" : (data.initiator === sendName ? "【发起】" : "【收到】");
        const detailCount = data.details ? data.details.length : 0;
        const totalChars = data.details ? data.details.reduce((sum, d) => sum + (d.text?.length || 0), 0) : 0;
        const charHint = totalChars > SPLIT_THRESHOLD ? `⚠️${totalChars}字·将拆分` : `${totalChars}字`;
        listContent += `${statusIcon} ${typeTag} 与「${name}」(${detailCount}条 | ${charHint})\n`;
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

let cmd_rel_stats = seal.ext.newCmdItemInfo();
cmd_rel_stats.name = "关系线统计";
cmd_rel_stats.help = "。关系线统计 —— 查看所有角色的关系线数量（管理员专用）";
cmd_rel_stats.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const relData = JSON.parse(mainStorGet("relationship_lines") || "{}");
    const platformData = relData[platform] || {};

    const stats = [];
    for (const [uid, links] of Object.entries(platformData)) {
        const count = Object.keys(links).length;
        if (count > 0) {
            const role = resolveUidToName(platform, uid);
            stats.push({ role, count });
        }
    }

    stats.sort((a, b) => b.count - a.count);

    if (stats.length === 0) {
        seal.replyToSender(ctx, msg, "📭 当前平台没有任何关系线记录");
        return seal.ext.newCmdExecuteResult(true);
    }

    const nodes = [];
    const header = `📊 角色关系线统计（${platform} 平台）\n共 ${stats.length} 个角色拥有关系线\n— 以上 —`;
    nodes.push({ type: "node", data: { name: "关系线统计员", uin: "10001", content: header } });

    const chunkSize = 20;
    for (let i = 0; i < stats.length; i += chunkSize) {
        const chunk = stats.slice(i, i + chunkSize);
        let content = "";
        chunk.forEach((item, idx) => { content += `${i + idx + 1}. ${item.role}：${item.count} 条关系线\n`; });
        nodes.push({ type: "node", data: { name: `角色列表 (${Math.floor(i / chunkSize) + 1})`, uin: "2852199344", content: content.trim() } });
    }

    const targetGid = msg.groupId.replace(/[^\d]/g, "");
    ws({ action: "send_group_forward_msg", params: { group_id: parseInt(targetGid, 10), messages: nodes } }, ctx, msg, "");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["关系线统计"] = cmd_rel_stats;

// ========================
// 无前缀触发：关系线指令
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();

    const makeFakeCmdArgs = (parts) => ({
        getArgN: (n) => parts[n - 1] || "",
        args: parts
    });

    if (raw.startsWith("拉线")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_add_rel_detail.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("确认关系线")) {
        const rest = raw.slice(5).trim();
        if (rest) return cmd_confirm_relationship.solve(ctx, msg, makeFakeCmdArgs([rest]));
    }

    if (raw.startsWith("撤回关系")) {
        const rest = raw.slice(4).trim();
        if (rest) return cmd_withdraw_relation.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }

    if (raw.startsWith("查看关系线")) {
        const rest = raw.slice(5).trim();
        return cmd_view_relationship.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw === "关系线统计") {
        return cmd_rel_stats.solve(ctx, msg, makeFakeCmdArgs([]));
    }

};
