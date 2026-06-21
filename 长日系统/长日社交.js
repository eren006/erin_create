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

let ext = seal.ext.find('changriV1');
if (!ext) {
    ext = seal.ext.new("changriV1", "长日将尽", "1.4.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

// ========================
// 核心依赖：主插件共享 API
// ========================
function getApi()                          { return globalThis.__changriApi || null; }
function mainStorGet(key)                  { return getApi()?.kvGetRaw(key) ?? null; }
function mainStorSet(key, val)             { getApi()?.kvSetRaw(key, val); }
function getPrimaryUid(platform, uid)      { return getApi()?.getPrimaryUid(platform, uid) ?? uid; }
function getRoleName(ctx, msg)             { return getApi()?.getRoleName(ctx, msg) ?? null; }
function getUidByRoleName(platform, name)  { return getApi()?.getUidByRoleName(platform, name) ?? null; }
function resolveUidToName(platform, uid)   { return getApi()?.resolveUidToName(platform, uid) ?? uid; }
function isUserAdmin(ctx, msg)             { return getApi()?.isUserAdmin(ctx, msg) ?? false; }
function isUserFeatureEnabled(uid, key, def = true) { return getApi()?.isUserFeatureEnabled(uid, key, def) ?? def; }
function getMainStorageInt(key, def)       { return getApi()?.getStorageInt(key, def) ?? def; }
function recordMeetingAndAnnounce(sub, p, ctx, ep) { return getApi()?.recordMeetingAndAnnounce(sub, p, ctx, ep); }
function ws(postData, ctx, msg, ok)        { return getApi()?.ws(postData, ctx, msg, ok); }

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
    if (!getApi()) return [];
    const priv = JSON.parse(mainStorGet("a_private_group") || "{}")[platform] || {};
    const validNames = new Set(Object.values(priv).map(v => v[0]));
    const matches = [...(content.matchAll(/@(\S+)/g) || [])].map(m => m[1]);
    return [...new Set(matches.filter(n => validNames.has(n)))];
}

function sendMentionNotice(platform, mentionedName, postId, authorName) {
    const uid = getUidByRoleName(platform, mentionedName);
    if (!uid || /^npc_/.test(uid)) return;
    if (!getApi()) return;
    const pGid = JSON.parse(mainStorGet("a_private_group") || "{}")[platform]?.[uid]?.[1];
    if (!pGid || pGid === "0") return;
    sendTextToGroup(platform, pGid, `[CQ:at,qq=${uid}]\n📣 「${authorName}」在论坛帖子 [${postId}] 的回复中提到了你！`);
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
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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

    const atStr = toUid ? `[CQ:at,qq=${toUid}]\n` : "";
    const message = `${atStr}📝 来自「${fromRoleName}」的新关系细节：\n${content}\n\n（使用「。查看关系线 ${fromRoleName}」查看完整记录）`;
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
        const atStr = toUid ? `[CQ:at,qq=${toUid}]\n` : "";
        ws({ "action": "send_group_msg", "params": { "group_id": parseInt(addr[1]), "message": `${atStr}🤝 「${sendName}」已确认并完成了你们的关系线！` } }, ctx, msg, "");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["确认关系线"] = cmd_confirm_relationship;

let cmd_set_forced_rel = seal.ext.newCmdItemInfo();
cmd_set_forced_rel.name = "设置强制关系线";
cmd_set_forced_rel.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"), seal.ext.newCmdExecuteResult(true);
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"), seal.ext.newCmdExecuteResult(true);
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
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。"), seal.ext.newCmdExecuteResult(true);
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
        const atStr = toUid ? `[CQ:at,qq=${toUid}]\n` : "";
        ws({
            action: "send_group_msg",
            params: { group_id: parseInt(addr[1], 10), message: `${atStr}🗑️ 「${sendName}」撤回了一条发给你的关系细节：\n"${removed.text}"` }
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
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
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

    // 关系线
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

    // 心愿
    if (raw.startsWith("挂心愿")) {
        const rest = raw.slice(3).trim();
        return cmd_post_wish.solve(ctx, msg, makeFakeCmdArgs(rest ? rest.split(/\s+/) : []));
    }

    if (raw === "看心愿") {
        return cmd_view_wish.solve(ctx, msg);
    }

    if (raw.startsWith("摘心愿")) {
        const rest = raw.slice(3).trim();
        return cmd_pick_wish.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    if (raw.startsWith("撤心愿")) {
        const rest = raw.slice(3).trim();
        return cmd_withdraw_wish.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    // 礼物
    {
        const giftM = raw.match(/^(.*?)送礼\s+(.+?)\s+([\s\S]+)$/);
        if (giftM) {
            if (!requireApi(ctx, msg)) return;
            const customName = giftM[1].trim() || null;
            return handleNaturalGift(ctx, msg, msg.platform, giftM[2].trim(), giftM[3].trim(), customName);
        } else if (/^(.*?)送礼$/.test(raw)) {
            return seal.replyToSender(ctx, msg, "📦 送礼格式：送礼 对方名 礼物内容\n例：送礼 张三 一束花\n\n图鉴内礼物：送礼 对方名 #编号（可无限送礼）");
        }
    }

    if (raw === "礼品店") return cmd_view_preset_gifts.solve(ctx, msg);
    if (raw === "图鉴" || raw === "我的图鉴" || raw.startsWith("图鉴 ") || raw.startsWith("我的图鉴 ")) {
        const rest = raw.replace(/^(我的)?图鉴/, "").trim();
        return cmd_view_my_gift_collection.solve(ctx, msg, makeFakeCmdArgs(rest ? [rest] : []));
    }

    // 本场统计
    if (raw === "本场统计") return cmd_my_stats.solve(ctx, msg, makeFakeCmdArgs([]));

    // 查看全员统计/本季字数 → 统计管理已迁至 rp_archive 网页端
    if (raw === "查看全员统计" || raw === "本季字数") {
        const api = getApi();
        if (!api || !api.isUserAdmin(ctx, msg)) return;
        const ep = api.getSafeEndPoint();
        seal.replyToSender(ctx, msg, `📊 全员统计已迁至网页端，请访问：\n${ep}/admin/stats`);
        return;
    }
};

// ============================================================
// 🧩 合并模块公共委托
// 心愿 / 礼物 / 心动信 / 本场统计 四个模块（2026-06 自卫星插件并入本文件），
// 以下函数仅存在于主插件共享 API（__changriApi），主插件未加载时相关指令报错退出。
// ============================================================
function requireApi(ctx, msg) {
    if (getApi()) return true;
    seal.replyToSender(ctx, msg, "❌ 该功能需要主插件「长日将尽」，请先加载主插件");
    return false;
}
const cachedGet = mainStorGet;
const cachedSet = mainStorSet;
const getStorageInt = getMainStorageInt;
const getUserRoleName = (...a) => getApi().getUserRoleName(...a);
const checkTsFeatureWindow = (...a) => getApi().checkTsFeatureWindow(...a);
const parseAndValidateTime = (...a) => getApi().parseAndValidateTime(...a);
const checkRealityHourLimit = (...a) => getApi().checkRealityHourLimit(...a);
const checkPlaceCommon = (...a) => getApi().checkPlaceCommon(...a);
const checkAcceptanceConflicts = (...a) => getApi().checkAcceptanceConflicts(...a);
const isLetterSystemEnabled = (...a) => getApi().isLetterSystemEnabled(...a);
const checkAndCostLetterCoin = (...a) => getApi().checkAndCostLetterCoin(...a);
const getCharProfile = (...a) => getApi().getCharProfile(...a);
const finalizeGroupCreation = (...a) => getApi().finalizeGroupCreation(...a);
const recordInteractionStat = (...a) => getApi().recordInteractionStat(...a);
const getRoleDetails = (...a) => getApi().getRoleDetails(...a);
const checkNoQuitBlocker = (...a) => getApi().checkNoQuitBlocker(...a);
const applyMsgTemplate = (...a) => getApi().applyMsgTemplate(...a);
const isArchiveEnabled = (...a) => getApi().isArchiveEnabled(...a);
const postToArchive = (...a) => getApi().postToArchive(...a);
const getUserStats  = (...a) => getApi().getUserStats(...a);
const saveUserStats = (...a) => getApi().saveUserStats(...a);
const getInteractionCounts = (...a) => getApi().getInteractionCounts(...a);
const getTop3Text = (...a) => getApi().getTop3Text(...a);
const getRoleStorage = (...a) => getApi().getRoleStorage(...a);


// 心愿悬赏奖励用：直接操作 changri 存储里的背包数据
function wishCheckInv(roleKey, code, count) {
    const invs = JSON.parse(cachedGet("global_inventories") || "{}");
    const total = (invs[roleKey] || []).filter(e => e.code === code).reduce((s, e) => s + (e.count || 0), 0);
    return total >= count;
}
function wishAddToInv(roleKey, code, count) {
    const reg = JSON.parse(cachedGet("item_registry") || "{}");
    const item = reg[code];
    if (!item) return;
    const invs = JSON.parse(cachedGet("global_inventories") || "{}");
    const inv = invs[roleKey] || [];
    const initialUses = item.maxUses !== undefined ? item.maxUses : -1;
    const entry = inv.find(e => e.code === code && (e.remainingUses !== undefined ? e.remainingUses : -1) === initialUses);
    if (entry) { entry.count += count; } else { inv.push({ code, count, remainingUses: initialUses }); }
    invs[roleKey] = inv;
    cachedSet("global_inventories", JSON.stringify(invs));
}
function wishGetDailyCount(uid, day, type) {
    const key = type === 'post' ? "wish_daily_post_counts" : "wish_daily_pick_counts";
    const counts = JSON.parse(cachedGet(key) || "{}");
    const rec = counts[uid] || { day: "", count: 0 };
    return rec.day === day ? rec.count : 0;
}
function wishIncrDailyCount(uid, day, type) {
    const key = type === 'post' ? "wish_daily_post_counts" : "wish_daily_pick_counts";
    const counts = JSON.parse(cachedGet(key) || "{}");
    const rec = counts[uid] || { day: "", count: 0 };
    counts[uid] = { day, count: rec.day === day ? rec.count + 1 : 1 };
    cachedSet(key, JSON.stringify(counts));
}

function wishRemoveFromInv(roleKey, code, count) {
    const invs = JSON.parse(cachedGet("global_inventories") || "{}");
    const inv = invs[roleKey] || [];
    let rem = count;
    for (const e of inv.filter(e => e.code === code)) {
        if (rem <= 0) break;
        const take = Math.min(e.count, rem);
        e.count -= take;
        rem -= take;
    }
    invs[roleKey] = inv.filter(e => e.count > 0);
    cachedSet("global_inventories", JSON.stringify(invs));
}

// 兼容 fromId 带/不带 platform 前缀两种历史格式
function wishIsOwner(platform, uid, rawUid, fromId) {
    return fromId === uid || fromId === rawUid || fromId.replace(`${platform}:`, "") === rawUid;
}

const WishUtils = {
    getPool: () => {
        const now = Date.now(), exp = 86400000;
        const raw = JSON.parse(cachedGet("a_wishPool") || "[]");
        const p = raw.filter(w => now - w.timestamp < exp);
        // Bug4修复：有过期条目时清理存储
        if (p.length < raw.length) cachedSet("a_wishPool", JSON.stringify(p));
        return p;
    },
    savePool: (p) => cachedSet("a_wishPool", JSON.stringify(p)),
    formatList: (pool, title) => {
        if (!pool.length) return title + "当前没有漂浮的心愿。";
        const now = Date.now(), exp = 86400000;
        return `📜 ${title}：\n` + pool.map(w => {
            const rem = Math.ceil((exp - (now - w.timestamp)) / 3600000);
            const rewardStr = w.rewardCode ? `｜🎁 ${w.rewardName} ×${w.rewardCount}` : "";
            const genderStr = w.gender === "男" ? "👨" : w.gender === "女" ? "👩" : "";
            const label = w.displayName ? `${genderStr} ${w.displayName}` : genderStr;
            return `编号：${w.id}｜${label}｜${w.day} ${w.time}｜${w.place}｜剩${rem}h${rewardStr}｜内容：${w.content}`;
        }).join('\n');
    }
};

// ==========================================
// 挂心愿
// ==========================================
let cmd_post_wish = {};
cmd_post_wish.solve =(ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const cfg = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");
    { const _fw = checkTsFeatureWindow("enable_wish_system"); if (!_fw.ok) return seal.replyToSender(ctx, msg, _fw.msg); }

    const platform = msg.platform;
    const rawUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const uid = `${platform}:${rawUid}`;
    const name = getUserRoleName(platform, uid);
    const day = cachedGet("global_days");
    if (!name || !day) return seal.replyToSender(ctx, msg, !name ? "请先绑定角色" : "请先设置全局天数");
    if (!isUserFeatureEnabled(rawUid, "enable_wish_system"))
        return seal.replyToSender(ctx, msg, "❌ 你已被限制使用心愿功能");

    const rawFull = msg.message.trim().replace(/^[。.]?\s*挂心愿\s*/, "");
    const pipeIdx = rawFull.indexOf("|");
    const mainPart = pipeIdx !== -1 ? rawFull.slice(0, pipeIdx).trim() : rawFull.trim();
    const customNick = pipeIdx !== -1 ? rawFull.slice(pipeIdx + 1).trim() : "";
    if (customNick.length > 10) return seal.replyToSender(ctx, msg, "⚠️ 昵称最多10个字");

    const mainArgs = mainPart.split(/\s+/);
    let [rawT, place, ...contentArr] = mainArgs;
    const content = contentArr.join(" ").trim();
    if (!rawT || !place || !content) return seal.replyToSender(ctx, msg, "用法：挂心愿 1400-1500 地点 内容 [| 昵称]");

    const timeResult = parseAndValidateTime(rawT, [], 0, "心愿");
    if (!timeResult.valid) return seal.replyToSender(ctx, msg, timeResult.errorMsg);
    const time = timeResult.time;

    // 冲突与限制检查
    if (!checkRealityHourLimit(time, ctx, msg)) return;
    const pCheck = checkPlaceCommon(platform, name, place, "挂心愿");
    if (!pCheck.valid) return seal.replyToSender(ctx, msg, pCheck.errorMsg);

    const conflicts = checkAcceptanceConflicts(platform, rawUid, name, day, time);
    if (conflicts.length) return seal.replyToSender(ctx, msg, `⚠️ 时间冲突：\n${conflicts.join('\n')}`);

    let pool = WishUtils.getPool();
    const wishMaxConcurrent = getStorageInt("wish_max_concurrent", 3);
    if (pool.filter(w => wishIsOwner(platform, uid, rawUid, w.fromId)).length >= wishMaxConcurrent) return seal.replyToSender(ctx, msg, `⚠️ 最多同时挂${wishMaxConcurrent}个心愿`);
    const wishDailyPostLimit = getStorageInt("wish_daily_post_limit", 0);
    if (wishDailyPostLimit > 0 && wishGetDailyCount(uid, day, 'post') >= wishDailyPostLimit) {
        return seal.replyToSender(ctx, msg, `⚠️ 今日发布心愿次数已达上限（${wishDailyPostLimit}次）`);
    }

    // Bug2修复：所有验证通过后再扣写信币
    let wishCoinCheck = null;
    if (isLetterSystemEnabled()) {
        wishCoinCheck = checkAndCostLetterCoin(ctx, msg, "wish");
        if (!wishCoinCheck.success) {
            seal.replyToSender(ctx, msg, wishCoinCheck.errorMsg);
            return seal.ext.newCmdExecuteResult(true);
        }
    }

    const id = Math.random().toString(36).slice(2, 9).toUpperCase();
    const wishProfile = getCharProfile(platform, name);
    pool.push({ id, day, time, place, content, fromId: uid, timestamp: Date.now(), gender: wishProfile.gender, displayName: customNick || "" });
    WishUtils.savePool(pool);
    wishIncrDailyCount(uid, day, 'post');

    const _wishCost = wishCoinCheck?.cost > 0 ? `\n💰 已消耗写信币 ${wishCoinCheck.cost} 枚` : "";
    const _昵称行 = customNick ? `\n🏷️ 显示昵称：${customNick}` : "";
    let wishSuccessMsg = applyMsgTemplate("wish_post_success", { 编号: id, 昵称行: _昵称行.trim(), 费用行: _wishCost.trim() })
        || `✅ 心愿已漂走！编号：${id}\n有效期：24小时${_昵称行}${_wishCost}`;
    seal.replyToSender(ctx, msg, wishSuccessMsg);

    // 公共频道推送
    if (JSON.parse(cachedGet("wish_public_send") || "true")) {
        const gid = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");
        if (gid) {
            const genderEmoji = wishProfile.gender === "男" ? "👨" : "👩";
            const displayLabel = customNick ? `${genderEmoji} ${customNick}` : genderEmoji;
            const m = seal.newMessage(); m.messageType = "group"; m.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m), m, applyMsgTemplate("wish_broadcast", {
                编号: id, 发布者: displayLabel, 日期: day, 时间: time.replace('-', ' ~ '), 地点: place, 内容: content
            }) || `🌠 新心愿 [${id}]\n${displayLabel}\n📅 ${day} ${time.replace('-', ' ~ ')}\n📍 ${place}\n💌 ${content}\n✨ 摘取：摘心愿 ${id}`);
        }
    }
    return seal.ext.newCmdExecuteResult(true);
};

// ==========================================
// 看心愿 & 摘心愿
// ==========================================
const cmd_view_wish = {
    solve: (ctx, msg) => {
        if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
        const cfg = JSON.parse(cachedGet("global_feature_toggle") || "{}");
        if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");
        seal.replyToSender(ctx, msg, WishUtils.formatList(WishUtils.getPool(), "当前心愿"));
        return seal.ext.newCmdExecuteResult(true);
    }
};

let cmd_pick_wish = {};
cmd_pick_wish.solve =async (ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const cfg = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");
    const wid = cmdArgs.getArgN(1)?.toUpperCase();
    const platform = msg.platform;
    const rawUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const uid = `${platform}:${rawUid}`;
    const name = getUserRoleName(platform, uid);
    if (!wid || !name) return seal.replyToSender(ctx, msg, !wid ? "格式：摘心愿 编号" : "请先绑定角色");

    let pool = WishUtils.getPool();
    const wish = pool.find(w => w.id === wid);
    if (!wish || wishIsOwner(platform, uid, rawUid, wish.fromId)) return seal.replyToSender(ctx, msg, !wish ? "心愿不存在或已过期" : "不能摘自己的心愿");

    const fromName = getUserRoleName(platform, wish.fromId) || wish.fromId;

    // 摘取冲突双向检查
    const check = (u, n) => checkAcceptanceConflicts(platform, u.replace(`${platform}:`, ""), n, wish.day, wish.time);
    const errs = [...check(uid, name), ...check(wish.fromId, fromName)];
    if (errs.length) return seal.replyToSender(ctx, msg, `⚠️ 无法建立联系：\n${errs.join('\n')}`);

    const wishDailyPickLimit = getStorageInt("wish_daily_pick_limit", 0);
    const currentDay = cachedGet("global_days") || "";
    if (wishDailyPickLimit > 0 && wishGetDailyCount(uid, currentDay, 'pick') >= wishDailyPickLimit) {
        return seal.replyToSender(ctx, msg, `⚠️ 今日摘取心愿次数已达上限（${wishDailyPickLimit}次）`);
    }

    // 移除并成交
    WishUtils.savePool(pool.filter(w => w.id !== wid));
    wishIncrDailyCount(uid, currentDay, 'pick');

    const item = {
        id: wid, type: "小群", subtype: "心愿", sendname: fromName, sendid: wish.fromId.replace(`${platform}:`, ""),
        toname: name, toid: uid.replace(`${platform}:`, ""), day: wish.day, time: wish.time, place: wish.place, title: wish.content
    };

    // 异步下发
    const wishGid = await finalizeGroupCreation(platform, ctx, msg, item, [fromName, name]);
    if (wishGid !== false) {
        recordInteractionStat(platform, name, fromName, "wish");
    }

    // 通知挂心愿者（finalizeGroupCreation 已跳过 sendname，需单独发）
    const { uid: fromUid, gid: fromBindGid } = getRoleDetails(platform, fromName);
    if (fromUid && fromBindGid) {
        const m = seal.newMessage(); m.messageType = "group"; m.groupId = `${platform}-Group:${fromBindGid}`;
        const wishNotifyText = applyMsgTemplate("wish_picked_notify", {
            摘取者: name, 地点: wish.place, 日期: wish.day, 时间: wish.time, 群号: wishGid
        }) || `💫 你的心愿被 ${name} 摘取了！\n📍 ${wish.place} | ⏰ ${wish.day} ${wish.time}\n💬 群号：${wishGid}`;
        seal.replyToSender(seal.createTempCtx(ctx.endPoint, m), m, `[CQ:at,qq=${fromUid}]\n${wishNotifyText}`);
    }

    const _悬赏奖励行 = wish.rewardCode ? `\n🎁 悬赏奖励：${wish.rewardName} ×${wish.rewardCount} 已加入你的背包！` : "";
    if (wish.rewardCode) wishAddToInv(uid, wish.rewardCode, wish.rewardCount);
    const pickReply = applyMsgTemplate("wish_pick_success", { 群号: wishGid, 悬赏奖励行: _悬赏奖励行.trim() })
        || `🎉 摘取成功！专属小群已建立。\n💬 群号：${wishGid}${_悬赏奖励行}`;
    seal.replyToSender(ctx, msg, pickReply);
    return seal.ext.newCmdExecuteResult(true);
};

// ==========================================
// 撤心愿
// ==========================================
let cmd_withdraw_wish = {};
cmd_withdraw_wish.solve =(ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const cfg = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");
    const wid = cmdArgs.getArgN(1)?.toUpperCase();
    const platform = msg.platform;
    const rawUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const uid = `${platform}:${rawUid}`;
    let pool = WishUtils.getPool();

    if (!wid) {
        const myWishes = pool.filter(w => wishIsOwner(platform, uid, rawUid, w.fromId));
        return seal.replyToSender(ctx, msg, WishUtils.formatList(myWishes, "你发布的心愿") + "\n\n使用「撤心愿 编号」撤回");
    }

    const withdrawWish = pool.find(w => w.id === wid);
    if (!withdrawWish) return seal.replyToSender(ctx, msg, `❌ 找不到编号「${wid}」的心愿，可能已过期或被摘取`);
    if (!wishIsOwner(platform, uid, rawUid, withdrawWish.fromId)) return seal.replyToSender(ctx, msg, "❌ 该心愿不属于你");

    WishUtils.savePool(pool.filter(w => w.id !== wid));
    const _退回行 = withdrawWish.rewardCode ? `\n🎁 悬赏物品「${withdrawWish.rewardName}」×${withdrawWish.rewardCount} 已退回背包。` : "";
    if (withdrawWish.rewardCode) wishAddToInv(uid, withdrawWish.rewardCode, withdrawWish.rewardCount);
    const withdrawReply = applyMsgTemplate("wish_withdraw_success", { 编号: wid, 悬赏退回行: _退回行.trim() })
        || `✅ 已撤回心愿 ${wid}${_退回行}`;
    seal.replyToSender(ctx, msg, withdrawReply);
    return seal.ext.newCmdExecuteResult(true);
};

// ==========================================
// 悬赏心愿
// ==========================================
let cmd_bounty_wish = seal.ext.newCmdItemInfo();
cmd_bounty_wish.name = "悬赏心愿";
cmd_bounty_wish.help = "挂出带物品奖励的心愿\n格式：悬赏心愿 时间 地点 内容 | 物品名/码 数量\n示例：悬赏心愿 1400-1500 图书馆 陪我看书 | 滋补汤 1";
cmd_bounty_wish.solve = (ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const cfg = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (cfg.enable_wish_system === false) return seal.replyToSender(ctx, msg, "🌠 心愿功能已关闭。");
    if (cachedGet("wish_bounty_enabled") === "false") return seal.replyToSender(ctx, msg, "🎁 悬赏心愿功能已关闭。");

    const platform = msg.platform;
    const rawUid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const uid = `${platform}:${rawUid}`;
    const name = getUserRoleName(platform, uid);
    const day = cachedGet("global_days");
    if (!name) return seal.replyToSender(ctx, msg, "请先绑定角色");
    if (!day) return seal.replyToSender(ctx, msg, "请先设置全局天数");
    if (!isUserFeatureEnabled(rawUid, "enable_wish_system"))
        return seal.replyToSender(ctx, msg, "❌ 你已被限制使用心愿功能");

    const rawFull = msg.message.trim().replace(/^[。.]?\s*悬赏心愿\s*/, "");
    const pipeIdx = rawFull.search(/[|｜]/);
    if (pipeIdx === -1) return seal.replyToSender(ctx, msg, "格式：悬赏心愿 时间 地点 内容 | 物品名 数量 [| 昵称]\n示例：悬赏心愿 1400-1500 图书馆 陪我看书 | 滋补汤 1 | 神秘人A");

    const wishPart = rawFull.slice(0, pipeIdx).trim();
    const afterFirstPipe = rawFull.slice(pipeIdx + 1);
    const secondPipeIdx = afterFirstPipe.search(/[|｜]/);
    let rewardPart, customNick;
    if (secondPipeIdx !== -1) {
        rewardPart = afterFirstPipe.slice(0, secondPipeIdx).trim();
        customNick = afterFirstPipe.slice(secondPipeIdx + 1).trim();
    } else {
        rewardPart = afterFirstPipe.trim();
        customNick = "";
    }
    if (customNick.length > 10) return seal.replyToSender(ctx, msg, "⚠️ 昵称最多10个字");

    const wishArgs = wishPart.split(/\s+/);
    const rawT = wishArgs[0], place = wishArgs[1];
    const content = wishArgs.slice(2).join(" ").trim();
    if (!rawT || !place || !content) return seal.replyToSender(ctx, msg, "格式：悬赏心愿 时间 地点 内容 | 物品名 数量");

    const rewardArgs = rewardPart.split(/\s+/);
    if (rewardArgs.length < 2) return seal.replyToSender(ctx, msg, "❌ 悬赏格式：| 物品名 数量");
    const rewardCount = parseInt(rewardArgs[rewardArgs.length - 1]);
    if (isNaN(rewardCount) || rewardCount <= 0) return seal.replyToSender(ctx, msg, "❌ 悬赏数量必须为正整数");
    const rewardInput = rewardArgs.slice(0, -1).join(" ");

    const reg = JSON.parse(cachedGet("item_registry") || "{}");
    const rewardItem = Object.values(reg).find(r => r.code === rewardInput.toUpperCase() || r.name === rewardInput);
    if (!rewardItem) return seal.replyToSender(ctx, msg, `❌ 找不到物品「${rewardInput}」`);

    const roleKey = uid;
    if (!wishCheckInv(roleKey, rewardItem.code, rewardCount)) {
        return seal.replyToSender(ctx, msg, `❌ 背包中「${rewardItem.name}」数量不足（需要 ${rewardCount}）`);
    }

    const timeResult = parseAndValidateTime(rawT, [], 0, "心愿");
    if (!timeResult.valid) return seal.replyToSender(ctx, msg, timeResult.errorMsg);
    const time = timeResult.time;
    if (!checkRealityHourLimit(time, ctx, msg)) return;
    const pCheck = checkPlaceCommon(platform, name, place, "悬赏心愿");
    if (!pCheck.valid) return seal.replyToSender(ctx, msg, pCheck.errorMsg);
    const conflicts = checkAcceptanceConflicts(platform, rawUid, name, day, time);
    if (conflicts.length) return seal.replyToSender(ctx, msg, `⚠️ 时间冲突：\n${conflicts.join('\n')}`);

    let pool = WishUtils.getPool();
    const wishMaxConcurrentB = getStorageInt("wish_max_concurrent", 3);
    if (pool.filter(w => wishIsOwner(platform, uid, rawUid, w.fromId)).length >= wishMaxConcurrentB) return seal.replyToSender(ctx, msg, `⚠️ 最多同时挂${wishMaxConcurrentB}个心愿`);
    const wishDailyPostLimitB = getStorageInt("wish_daily_post_limit", 0);
    if (wishDailyPostLimitB > 0 && wishGetDailyCount(uid, day, 'post') >= wishDailyPostLimitB) {
        return seal.replyToSender(ctx, msg, `⚠️ 今日发布心愿次数已达上限（${wishDailyPostLimitB}次）`);
    }

    let wishCoinCheck = null;
    if (isLetterSystemEnabled()) {
        wishCoinCheck = checkAndCostLetterCoin(ctx, msg, "wish");
        if (!wishCoinCheck.success) { seal.replyToSender(ctx, msg, wishCoinCheck.errorMsg); return seal.ext.newCmdExecuteResult(true); }
    }

    wishRemoveFromInv(roleKey, rewardItem.code, rewardCount);

    const id = Math.random().toString(36).slice(2, 9).toUpperCase();
    const bountyProfile = getCharProfile(platform, name);
    pool.push({ id, day, time, place, content, fromId: uid, timestamp: Date.now(), gender: bountyProfile.gender, displayName: customNick || "", rewardCode: rewardItem.code, rewardName: rewardItem.name, rewardCount });
    WishUtils.savePool(pool);
    wishIncrDailyCount(uid, day, 'post');

    const _b昵称行 = customNick ? `\n🏷️ 显示昵称：${customNick}` : "";
    const _b费用行 = wishCoinCheck?.cost > 0 ? `\n💰 已消耗写信币 ${wishCoinCheck.cost} 枚` : "";
    seal.replyToSender(ctx, msg, applyMsgTemplate("wish_bounty_post_success", {
        编号: id, 悬赏物: rewardItem.name, 悬赏数量: rewardCount, 昵称行: _b昵称行.trim(), 费用行: _b费用行.trim()
    }) || `✅ 悬赏心愿已发出！编号：${id}\n🎁 悬赏：${rewardItem.name} ×${rewardCount}（已从背包扣除）\n有效期：24小时${_b昵称行}${_b费用行}`);

    if (JSON.parse(cachedGet("wish_public_send") || "true")) {
        const gid = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");
        if (gid) {
            const genderEmoji = bountyProfile.gender === "男" ? "👨" : "👩";
            const displayLabel = customNick ? `${genderEmoji} ${customNick}` : genderEmoji;
            const m = seal.newMessage(); m.messageType = "group"; m.groupId = `${platform}-Group:${gid}`;
            seal.replyToSender(seal.createTempCtx(ctx.endPoint, m), m, applyMsgTemplate("wish_bounty_broadcast", {
                编号: id, 发布者: displayLabel, 日期: day, 时间: time.replace('-', ' ~ '),
                地点: place, 内容: content, 悬赏物: rewardItem.name, 悬赏数量: rewardCount
            }) || `🌠 新悬赏心愿 [${id}]\n${displayLabel}\n📅 ${day} ${time.replace('-', ' ~ ')}\n📍 ${place}\n💌 ${content}\n🎁 悬赏：${rewardItem.name} ×${rewardCount}\n✨ 摘取：摘心愿 ${id}`);
        }
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["悬赏心愿"] = cmd_bounty_wish;
// ========================
// 🎁 礼物系统
// ========================
async function handleNaturalGift(ctx, msg, platform, toname, giftInput, customSenderName = null) {
    // 1. 功能开关检查
    const config = JSON.parse(cachedGet("global_feature_toggle") || "{}");
    if (!(config.enable_general_gift ?? true)) {
        return seal.replyToSender(ctx, msg, "🎁 礼物功能已被禁用。");
    }
    { const _fw = checkTsFeatureWindow("enable_general_gift"); if (!_fw.ok) return seal.replyToSender(ctx, msg, _fw.msg); }

    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const a_private_group = JSON.parse(cachedGet("a_private_group") || "{}");

    // 2. 身份识别
    const autoSendname = getRoleName(ctx, msg);
    if (!autoSendname) {
        return seal.replyToSender(ctx, msg, `❌ 请先创建新角色再使用该功能`);
    }
    const allowCustomSign = cachedGet("allow_custom_gift_sign") === "true";
    const sendname = allowCustomSign && customSenderName ? customSenderName : autoSendname;

    // 违规检查
    if (!(await checkNoQuitBlocker(uid, ctx, msg))) return;

    // 3. 权限与自送检查（新结构：feature_user_blocklist[uid]）
    if (!isUserFeatureEnabled(uid, "enable_general_gift")) {
        return seal.replyToSender(ctx, msg, `🎁 ${sendname} 被限制使用礼物功能。`);
    }
    if (toname === autoSendname) {
        return seal.replyToSender(ctx, msg, `🌸 礼不自赠，情当他寄。`);
    }
    // 新结构：通过 roleName 反查 uid
    const toUid = getUidByRoleName(platform, toname);
    if (!toUid) {
        return seal.replyToSender(ctx, msg, `❌ 未找到收件人 ${toname}`);
    }

    // 4. 冷却与限次检查
    const gameDay = cachedGet("global_days") || "D0";
    const dailyLimit = getStorageInt("giftDailyLimit", 100);
    const cooldownMin = getStorageInt("giftCooldown", 30);
    const isPreset = giftInput.startsWith('#');

    let globalStats = JSON.parse(cachedGet("global_gift_stats") || "{}");
    let globalCooldowns = JSON.parse(cachedGet("global_gift_cooldowns") || "{}");
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
    const giftMode = getStorageInt("giftMode", 0);
    if (giftMode === 1 && !isPreset) {
        return seal.replyToSender(ctx, msg, "❌ 当前仅允许使用预设礼物（以 # 开头）");
    }

    // 5. 礼物内容解析
    let giftDisplayName = "";
    let giftContent = giftInput;

    if (giftInput.startsWith('#')) {
        let presetGifts = JSON.parse(cachedGet("preset_gifts") || "{}");
        const giftData = presetGifts[giftInput];
        if (!giftData) return seal.replyToSender(ctx, msg, `❌ 预设礼物 ${giftInput} 不存在`);

        // 抽卡模式：检查图鉴，可无限赠送
        const sightings = JSON.parse(cachedGet("gift_sightings") || "{}");
        const owned = sightings[userKey]?.unlocked_gifts || [];
        if (!owned.includes(giftInput)) {
            return seal.replyToSender(ctx, msg, `🔒 「${giftData.name}」不在图鉴中，请先发送「礼品店」收集。`);
        }

        giftDisplayName = `「${giftData.name}」`;
        giftContent = giftData.content;
        presetGifts[giftInput].usage_count = (presetGifts[giftInput].usage_count || 0) + 1;
        cachedSet("preset_gifts", JSON.stringify(presetGifts));
    } else {
        giftDisplayName = "一份特别的礼物";
        giftContent = giftInput;
    }

    // 6. 混乱投递（丢失 / 送错）
    const chaosGiftCfg = JSON.parse(cachedGet("chaos_letter_config") || "{}");
    const giftLostChance = chaosGiftCfg.giftLost || 0;
    const giftMisdeliveryChance = chaosGiftCfg.giftMisdelivery || 0;

    let actualToname = toname;
    let actualToUid = toUid;
    let isLost = false;

    if (giftLostChance > 0 && Math.random() * 100 < giftLostChance) {
        isLost = true;
    } else if (giftMisdeliveryChance > 0 && Math.random() * 100 < giftMisdeliveryChance) {
        const otherEntries = Object.entries(a_private_group[platform] || {})
            .filter(([uid, v]) => v[0] !== toname && v[0] !== sendname);
        if (otherEntries.length) {
            const pick = otherEntries[Math.floor(Math.random() * otherEntries.length)];
            actualToUid = pick[0];
            actualToname = pick[1][0];
        }
    }

    // 投递（通过 actualToUid 查找 gid）
    if (!isLost) {
        const targetEntry = a_private_group[platform][actualToUid];

        // 收到即入图鉴：若设置开启，且是预设礼物，将礼物加入实际收件人图鉴
        let catalogHint = "";
        if (giftInput.startsWith('#') && cachedGet("shop_gift_catalog_on_receive") === "true") {
            const recipientPrimaryUid = getPrimaryUid(platform, actualToUid);
            const recipientKey = `${platform}:${recipientPrimaryUid}`;
            const sightings = JSON.parse(cachedGet("gift_sightings") || "{}");
            if (!sightings[recipientKey]) sightings[recipientKey] = { unlocked_gifts: [] };
            if (!sightings[recipientKey].unlocked_gifts.includes(giftInput) && Math.random() < 0.5) {
                sightings[recipientKey].unlocked_gifts.push(giftInput);
                cachedSet("gift_sightings", JSON.stringify(sightings));
                const total = Object.keys(JSON.parse(cachedGet("preset_gifts") || "{}")).length;
                const newCount = sightings[recipientKey].unlocked_gifts.length;
                catalogHint = `\n✨ 这份礼物悄悄收进了你的图鉴～ 📚 ${newCount}/${total}`;
            }
        }

        if (!targetEntry) {
            seal.replyToSender(ctx, msg, "❌ 礼物投递失败：找不到收件人所在群组。");
            return;
        }
        const newmsg = seal.newMessage();
        newmsg.messageType = "group";
        newmsg.groupId = `${platform}-Group:${targetEntry[1]}`;
        const newctx = seal.createTempCtx(ctx.endPoint, newmsg);
        const recipientMsg = applyMsgTemplate("gift_notice", {
            "收件人": actualToname, "收件人QQ": actualToUid,
            "发送者": sendname, "礼物名": giftDisplayName, "寄语": giftContent
        }) || `[CQ:at,qq=${actualToUid}]\n🎀 ${actualToname}，有一份来自「${sendname}」的快递：\n礼物：${giftDisplayName}\n寄语：「${giftContent}」${catalogHint}`;
        seal.replyToSender(newctx, newmsg, recipientMsg);
        recordInteractionStat(platform, sendname, actualToname, "gift");
    } else {
        // 丢失：仅记发送方 sent，不记收件方 received（双方均不知情）
        recordInteractionStat(platform, sendname, toname, "gift", true);
    }

    // 7. 更新数据
    userStat.count += 1;
    globalStats[userKey] = userStat;
    globalCooldowns[userKey] = now;
    cachedSet("global_gift_stats", JSON.stringify(globalStats));
    cachedSet("global_gift_cooldowns", JSON.stringify(globalCooldowns));

    // 8. 公开广播逻辑（丢失时跳过，存档前先决定是否公开）
    let isPublicDrop = false;
    let publicGroupId = null, pubCtxForGift = null, pubMsgForGift = null;
    if (!isLost) {
        publicGroupId = JSON.parse(cachedGet("adminAnnounceGroupId") || "null");
        const giftPublicEnabled = JSON.parse(cachedGet("gift_public_send") || "false");
        if (giftPublicEnabled && publicGroupId) {
            const publicChance = getStorageInt("giftPublicChance", 50);
            if ((Math.floor(Math.random() * 100) + 1) <= publicChance) {
                isPublicDrop = true;
                pubMsgForGift = seal.newMessage();
                pubMsgForGift.messageType = "group";
                pubMsgForGift.groupId = `${platform}-Group:${publicGroupId}`;
                pubCtxForGift = seal.createTempCtx(ctx.endPoint, pubMsgForGift);
            }
        }
    }

    const hideReceiverOnDrop = cachedGet("drop_hide_receiver") === "true";

    // 礼物实时存档
    if (isArchiveEnabled()) {
        postToArchive("/api/event", {
            type:            "gift",
            from_role:       autoSendname,
            from_custom_name: sendname !== autoSendname ? sendname : undefined,
            from_qq:         uid,
            to_role:         actualToname,
            to_qq:           actualToUid,
            content:         giftContent || "",
            extra_info:      { giftName: giftDisplayName, isLost: isLost, isPublic: isPublicDrop, hide_receiver: isPublicDrop && hideReceiverOnDrop },
            game_day:        cachedGet("global_days") || "D?",
            session_id:      "",
            timestamp:       Date.now()
        });
    }

    // 丢失与正常均显示相同提示，发送方不知情
    seal.replyToSender(ctx, msg, `🎁 已成功将 ${giftDisplayName} 送往「${toname}」的房间。\n(今日第 ${userStat.count}份)`);

    if (isPublicDrop && pubCtxForGift && pubMsgForGift) {
        const dropReceiver = hideReceiverOnDrop ? "某人" : toname;
        const publicNotice = applyMsgTemplate("gift_broadcast", {
            "发送者": sendname, "收件人": dropReceiver,
            "礼物名": giftDisplayName, "寄语": giftContent
        }) || `🎁 公告：来自「${sendname}」送给「${dropReceiver}」的礼物：${giftDisplayName}\n寄语：「${giftContent}」`;
        seal.replyToSender(pubCtxForGift, pubMsgForGift, publicNotice);
    }

    recordMeetingAndAnnounce("礼物", platform, ctx, ctx.endPoint);
}

// ========================
// 🛒 礼品店
// ========================

let cmd_view_preset_gifts = {};
cmd_view_preset_gifts.solve =(ctx, msg) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const sendname = getRoleName(ctx, msg);
    if (!sendname) {
        seal.replyToSender(ctx, msg, "你想走进去，却发现自己还没有名字。\n先创建一个角色，再来逛吧。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const presetGifts = JSON.parse(cachedGet("preset_gifts") || "{}");
    const allIds = Object.keys(presetGifts);

    if (allIds.length === 0) return seal.replyToSender(ctx, msg, "你推开门，走了进去。\n货架上什么都没有，空气里只有淡淡的木头气味。\n也许过些时候再来。");

    // 每人独立随机1件，自动加入图鉴，刷新只选未拥有的
    const refreshHours = parseInt(cachedGet("shop_refresh_hours") || "24");
    const now = Date.now();
    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(/^[a-z]+:/i, ""));
    const userKey = `${platform}:${uid}`;

    const sightings = JSON.parse(cachedGet("gift_sightings") || "{}");
    const owned = new Set(sightings[userKey]?.unlocked_gifts || []);

    let personalDisplay = {};
    try { personalDisplay = JSON.parse(cachedGet("shop_personal_display") || "{}"); } catch (e) {}

    const myDisplay = personalDisplay[userKey];
    const needsRefresh = !myDisplay || (now - myDisplay.refreshedAt) > refreshHours * 3600 * 1000;

    if (needsRefresh) {
        const unowned = allIds.filter(id => !owned.has(id));
        if (unowned.length > 0) {
            const picked = unowned[Math.floor(Math.random() * unowned.length)];
            personalDisplay[userKey] = { giftId: picked, refreshedAt: now };
            cachedSet("shop_personal_display", JSON.stringify(personalDisplay));
        }
        // 若全部拥有，不刷新 giftId（保留旧展示）
    }

    const currentGiftId = personalDisplay[userKey]?.giftId;
    const total = allIds.length;
    const ownedCount = owned.size;

    if (!currentGiftId || !presetGifts[currentGiftId]) {
        if (ownedCount >= total) {
            return seal.replyToSender(ctx, msg, `你走遍了每一格货架，翻过了每一个角落。\n这里所有的 ${total} 件礼物，都已经在你的图鉴里了。\n\n发送「图鉴」看看你收藏的一切。`);
        }
        return seal.replyToSender(ctx, msg, "你在货架间走了一圈，今天似乎什么都还没上架。\n过一会儿再来看看。");
    }

    const gift = presetGifts[currentGiftId];
    const nextRefreshMs = personalDisplay[userKey].refreshedAt + refreshHours * 3600 * 1000 - now;
    const nextRefreshHrs = Math.max(1, Math.ceil(nextRefreshMs / 3600000));

    if (owned.has(currentGiftId)) {
        return seal.replyToSender(ctx, msg,
            `你在货架上看见了它——\n\n${currentGiftId} 「${gift.name}」\n${gift.content}\n\n这件已经在你的图鉴里了。\n再等 ${nextRefreshHrs} 个小时，也许会有新的东西出现。\n\n📚 图鉴进度：${ownedCount}/${total}`
        );
    }

    // 新礼物：自动加入图鉴
    if (!sightings[userKey]) sightings[userKey] = { unlocked_gifts: [] };
    sightings[userKey].unlocked_gifts.push(currentGiftId);

    // 50% 概率额外获得第二件未拥有的礼物
    let bonusGiftId = null;
    let bonusGift = null;
    if (Math.random() < 0.5) {
        const stillUnowned = allIds.filter(id => id !== currentGiftId && !owned.has(id));
        if (stillUnowned.length > 0) {
            bonusGiftId = stillUnowned[Math.floor(Math.random() * stillUnowned.length)];
            bonusGift = presetGifts[bonusGiftId];
            sightings[userKey].unlocked_gifts.push(bonusGiftId);
        }
    }

    cachedSet("gift_sightings", JSON.stringify(sightings));

    const newCount = ownedCount + 1 + (bonusGiftId ? 1 : 0);

    let replyText = `你在货架上发现了一件没见过的东西，拿起来看了看。\n\n${currentGiftId} 「${gift.name}」\n${gift.content}`;

    if (bonusGiftId && bonusGift) {
        replyText += `\n\n转身要走，视线扫到角落里还有一件——\n\n${bonusGiftId} 「${bonusGift.name}」\n${bonusGift.content}`;
        replyText += `\n\n✨ 两件都收入图鉴。📚 进度：${newCount}/${total}`;
    } else {
        replyText += `\n\n✨ 收入图鉴。📚 进度：${newCount}/${total}`;
    }

    replyText += `\n下次再来大约要等 ${nextRefreshHrs} 个小时。\n\n想把它送给某人？发送「送礼 对方名 礼物编号」`;

    seal.replyToSender(ctx, msg, replyText);
    return seal.ext.newCmdExecuteResult(true);
};

// ========================
// 📚 我的图鉴
// ========================

let cmd_view_my_gift_collection = {};
cmd_view_my_gift_collection.solve =(ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");
    // Resolve via primary account (extra_accounts alias)
    const primaryUid = getPrimaryUid(platform, uid);
    const userKey = `${platform}:${primaryUid}`;
    const queryId = cmdArgs?.getArgN ? cmdArgs.getArgN(1) : "";

    const presetGifts = JSON.parse(cachedGet("preset_gifts") || "{}");
    const total = Object.keys(presetGifts).length;

    if (total === 0) return seal.replyToSender(ctx, msg, "📚 图鉴暂无礼物，管理员尚未上传任何礼物~");

    const sortedByHeat = Object.entries(presetGifts)
        .map(([id, g]) => ({ id, name: g.name, content: g.content, count: g.usage_count || 0 }))
        .sort((a, b) => b.count - a.count);
    const heatRanks = {};
    let rank = 1;
    for (let i = 0; i < sortedByHeat.length; i++) {
        if (i > 0 && sortedByHeat[i].count < sortedByHeat[i - 1].count) rank = i + 1;
        heatRanks[sortedByHeat[i].id] = rank;
    }

    const sightings = JSON.parse(cachedGet("gift_sightings") || "{}");
    const owned = sightings[userKey]?.unlocked_gifts || [];

    if (queryId && queryId.startsWith('#')) {
        if (!owned.includes(queryId)) return seal.replyToSender(ctx, msg, `🔒 ${queryId} 不在你的图鉴中`);
        const gift = presetGifts[queryId];
        if (!gift) return seal.replyToSender(ctx, msg, `❌ ${queryId} 已下架`);
        return seal.replyToSender(ctx, msg,
            `📖 ${queryId} 「${gift.name}」\n🔥 热度第${heatRanks[queryId]}名\n${"━".repeat(14)}\n${gift.content}`
        );
    }

    if (owned.length === 0) {
        return seal.replyToSender(ctx, msg, `📚 图鉴（0/${total}）\n发送「礼品店」开始收集！`);
    }
    const sorted = [...owned].sort((a, b) => (parseInt(a.replace('#', '')) || 0) - (parseInt(b.replace('#', '')) || 0));
    let text = `📚 我的图鉴（${owned.length}/${total}）\n${"━".repeat(14)}\n💌 图鉴内的礼物可无限送礼\n发送「图鉴 #编号」查看详细描述\n`;
    for (const giftId of sorted) {
        const gift = presetGifts[giftId];
        if (!gift) { text += `\n${giftId} （已下架）`; continue; }
        text += `\n${giftId} 「${gift.name}」 🔥第${heatRanks[giftId]}名`;
    }
    seal.replyToSender(ctx, msg, text.trim());
    return seal.ext.newCmdExecuteResult(true);
};
// 💌 心动信系统已迁移至主插件 长日系统.js

// ========================
// 📊 玩家指令：查看个人历史统计
// ========================
let cmd_my_stats = {};
cmd_my_stats.solve =(ctx, msg, cmdArgs) => {
    if (!requireApi(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const storage = getRoleStorage();
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const roleName = storage[platform]?.[uid]?.[0];

    if (!roleName) {
        seal.replyToSender(ctx, msg, "❌ 未找到你的角色绑定信息，请先创建角色。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 字数统计以 user_stats 为准（每条有效回复实时累加，从不清空，全季完整）
    const stats = getUserStats();
    const globalStat = stats[`${platform}:${uid}`];

    let reply = `📊 【${roleName}】统计报告\n`;

    if (!globalStat) {
        const iCountsEarly = getInteractionCounts()[`${platform}:${roleName}`] || {};
        const hasInteraction = Object.keys(iCountsEarly).length > 0;
        if (!hasInteraction) {
            seal.replyToSender(ctx, msg, `📊 【${roleName}】暂无统计数据，快去参与邀约吧！`);
            return seal.ext.newCmdExecuteResult(true);
        }
        if (hasInteraction) {
            const smsFE = getTop3Text(iCountsEarly.sms_received);
            const smsTE = getTop3Text(iCountsEarly.sms_sent);
            const giftFE = getTop3Text(iCountsEarly.gift_received);
            const giftTE = getTop3Text(iCountsEarly.gift_sent);
            const apptFE = getTop3Text(iCountsEarly.appt_received);
            const apptTE = getTop3Text(iCountsEarly.appt_sent);
            if (smsFE || smsTE) {
                reply += `【短信】\n`;
                if (smsFE) reply += `📨 最喜欢给你发短信：\n${smsFE}\n`;
                if (smsTE) reply += `📤 你最喜欢发短信给：\n${smsTE}\n`;
            }
            if (giftFE || giftTE) {
                reply += `【礼物】\n`;
                if (giftFE) reply += `🎀 最喜欢送你礼物：\n${giftFE}\n`;
                if (giftTE) reply += `🎁 你最喜欢送礼给：\n${giftTE}\n`;
            }
            if (apptFE || apptTE) {
                reply += `【约会】\n`;
                if (apptFE) reply += `📅 最喜欢约你（私约/电话）：\n${apptFE}\n`;
                if (apptTE) reply += `💌 你最喜欢约（私约/电话）：\n${apptTE}\n`;
            }
            const wishFE = getTop3Text(iCountsEarly.wish_received);
            const wishTE = getTop3Text(iCountsEarly.wish_sent);
            if (wishFE || wishTE) {
                reply += `【心愿】\n`;
                if (wishFE) reply += `🌠 最喜欢摘你心愿：\n${wishFE}\n`;
                if (wishTE) reply += `✨ 你最喜欢摘谁的心愿：\n${wishTE}\n`;
            }
        }
        reply += `— 以上 —`;
        seal.replyToSender(ctx, msg, reply);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 本季累计数据块（user_stats 实时累加，全季完整）
    reply += `【本季累计】\n`;
    reply += `🔹 累计回复：${globalStat.totalReplies} 次\n`;
    reply += `🔹 累计字数：${globalStat.totalWords} 字\n`;
    reply += `🔹 平均每条：${globalStat.avgWords} 字\n`;
    reply += `🔹 平均耗时：${globalStat.avgReplyTimeMin} 分钟\n`;

    const sub = globalStat.subtypeStats?.[platform]?.[uid];
    if (sub) {
        reply += `🔹 极限速度：${sub.fastestReply || '--'} min (最快)\n`;
    }

    const iCounts = getInteractionCounts()[`${platform}:${roleName}`] || {};
    const smsFrom = getTop3Text(iCounts.sms_received);
    const smsTo   = getTop3Text(iCounts.sms_sent);
    const giftFrom = getTop3Text(iCounts.gift_received);
    const giftTo   = getTop3Text(iCounts.gift_sent);
    const apptFrom = getTop3Text(iCounts.appt_received);
    const apptTo   = getTop3Text(iCounts.appt_sent);

    if (smsFrom || smsTo) {
        reply += `【短信】\n`;
        if (smsFrom) reply += `📨 最喜欢给你发短信：\n${smsFrom}\n`;
        if (smsTo)   reply += `📤 你最喜欢发短信给：\n${smsTo}\n`;
    }
    if (giftFrom || giftTo) {
        reply += `【礼物】\n`;
        if (giftFrom) reply += `🎀 最喜欢送你礼物：\n${giftFrom}\n`;
        if (giftTo)   reply += `🎁 你最喜欢送礼给：\n${giftTo}\n`;
    }
    if (apptFrom || apptTo) {
        reply += `【约会】\n`;
        if (apptFrom) reply += `📅 最喜欢约你（私约/电话）：\n${apptFrom}\n`;
        if (apptTo)   reply += `💌 你最喜欢约（私约/电话）：\n${apptTo}\n`;
    }
    const wishFrom = getTop3Text(iCounts.wish_received);
    const wishTo   = getTop3Text(iCounts.wish_sent);
    if (wishFrom || wishTo) {
        reply += `【心愿】\n`;
        if (wishFrom) reply += `🌠 最喜欢摘你心愿：\n${wishFrom}\n`;
        if (wishTo)   reply += `✨ 你最喜欢摘谁的心愿：\n${wishTo}\n`;
    }

    reply += `— 以上 —`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 管理员：修复被 null-startTime 污染的耗时统计（avgReplyTimeMin 超过阈值才清零，正常数据保留）
// 用法：。修复耗时统计（扫全部）/ 。修复耗时统计 角色名（只查该角色）
// 默认阈值：平均耗时 > 1440 分钟（24小时）视为异常
let cmd_fix_reply_time = seal.ext.newCmdItemInfo();
cmd_fix_reply_time.name = "修复耗时统计";
cmd_fix_reply_time.help = "。修复耗时统计 [角色名] —— 自动检测并清除异常耗时数据，正常数据保留，管理员专用";
cmd_fix_reply_time.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const THRESHOLD_MIN = 2880; // 单次平均超过 48 小时视为污染
    const platform = msg.platform;
    const targetRoleName = cmdArgs.getArgN(1) || null;
    const stats = getUserStats();

    const isCorrupted = (entry) => (entry.avgReplyTimeMin || 0) > THRESHOLD_MIN;

    const resetTimeFields = (entry) => {
        entry.totalReplyTimeMs = 0;
        entry.timedReplies = 0;
        entry.avgReplyTimeMin = 0;
        if (entry.subtypeStats) {
            for (const plat of Object.values(entry.subtypeStats)) {
                for (const sub of Object.values(plat)) {
                    sub.totalTime = 0;
                    sub.fastestReply = null;
                    sub.slowestReply = null;
                }
            }
        }
    };

    if (targetRoleName) {
        const uid = getUidByRoleName(platform, targetRoleName);
        const key = uid ? `${platform}:${uid}` : null;
        if (!key || !stats[key]) {
            seal.replyToSender(ctx, msg, `❌ 找不到角色「${targetRoleName}」的统计数据。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        const entry = stats[key];
        if (isCorrupted(entry)) {
            resetTimeFields(entry);
            saveUserStats(stats);
            seal.replyToSender(ctx, msg, `✅ 「${targetRoleName}」耗时数据异常（${entry.avgReplyTimeMin ?? "?"}分），已清零，字数/次数保留。`);
        } else {
            seal.replyToSender(ctx, msg, `✅ 「${targetRoleName}」耗时数据正常（${entry.avgReplyTimeMin ?? 0}分），无需修复。`);
        }
    } else {
        const lines = [];
        let fixedCount = 0;
        for (const [key, entry] of Object.entries(stats)) {
            if (isCorrupted(entry)) {
                const oldAvg = entry.avgReplyTimeMin;
                resetTimeFields(entry);
                lines.push(`· ${key}：${oldAvg}分 → 已清零`);
                fixedCount++;
            }
        }
        saveUserStats(stats);
        if (fixedCount === 0) {
            seal.replyToSender(ctx, msg, `✅ 全部玩家耗时数据正常，无需修复。`);
        } else {
            seal.replyToSender(ctx, msg, `✅ 已修复 ${fixedCount} 位玩家的异常耗时数据（字数/次数保留）：\n${lines.join("\n")}`);
        }
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["修复耗时统计"] = cmd_fix_reply_time;

