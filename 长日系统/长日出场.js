// ==UserScript==
// @name         出场系统
// @author       长日将尽
// @version      1.0.0
// @description  出场顺序抽取与依次出场（卫星插件）。所有数据存储在主插件 changri 中。
// @timestamp    1785484800
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// @updateUrl    https://raw.gitmirror.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%87%BA%E5%9C%BA.js
// @updateUrl    https://raw.githubusercontent.com/eren006/erin_create/main/%E9%95%BF%E6%97%A5%E7%B3%BB%E7%BB%9F/%E9%95%BF%E6%97%A5%E5%87%BA%E5%9C%BA.js
// ==/UserScript==

let ext = seal.ext.find('entrance_system');
if (!ext) {
    ext = seal.ext.new("entrance_system", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

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
function getRoleName(ctx, msg)         { return getApi()?.getRoleName(ctx, msg) ?? null; }
function getPrimaryUid(platform, uid)  { return getApi()?.getPrimaryUid(platform, uid) ?? uid; }
function sendTextToGroup(platform, gid, text) { return getApi()?.sendTextToGroup(platform, gid, text); }
function collectImageToArchive(url, uid)      { return getApi()?.collectImageToArchive(url, uid); }
function deleteCollectedImage(url)            { return getApi()?.deleteCollectedImage(url); }
function extractImageSrc(cqTag)               { return getApi()?.extractImageSrc(cqTag) ?? null; }
function wsRequest(postData, onResponse, onTimeout, timeoutMs) { return getApi()?.wsRequest(postData, onResponse, onTimeout, timeoutMs); }

// ========================
// 🎭 出场系统
// ========================
// sys_entrance_order：抽取好的出场顺序 [{uid, roleName}]，整体覆盖，重排不影响下面两项存储
// sys_entrance_submit / sys_entrance_image：按 uid 存的出场文字/图片，与顺序无关，反复提交覆盖，重排不清空
// sys_entrance_state：{active, index} 记录「开始出场」进行到第几位；戏群复用点歌已配置的 song_group_id

function getEntranceRoster(platform) {
    const roles = mainKvGet("a_private_group", {})[platform] || {};
    const npcList = mainKvGet("a_npc_list", []);
    return Object.entries(roles)
        .filter(([, info]) => info[0] && !npcList.includes(info[0]))
        .map(([uid, info]) => ({ uid, roleName: info[0] }));
}

function shuffleInPlace(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

function getEntranceShowGid() {
    const raw = mainStorGet("song_group_id");
    return raw ? raw.replace(/[^\d]/g, "") : "";
}

// 出场推进核心：从当前位开始，只要已有出场文字/图片就连续发出并前进，直到遇到没提交的人才停下 @ 提醒
// forceAnnounce：即使位置没变也要发一次 @ 提醒（用于「开始出场」「跳过出场」的首次/强制通知）
function tryAdvanceEntrance(ctx, platform, forceAnnounce = false) {
    const state = mainKvGet("sys_entrance_state", { active: false, index: 0 });
    if (!state.active) return;
    const gid = getEntranceShowGid();
    if (!gid) return;
    const order = mainKvGet("sys_entrance_order", []);

    let submits = mainKvGet("sys_entrance_submit", {});
    let images  = mainKvGet("sys_entrance_image", {});
    let idx = state.index;

    while (idx < order.length) {
        const person = order[idx];
        const sub = submits[person.uid];
        const img = images[person.uid];
        if (!sub && !img) break;

        let content = `🎭 【${person.roleName}】出场`;
        if (sub) content += `\n${sub.content}`;
        if (img) content += `\n${img.comment ? img.comment + "\n" : ""}[CQ:image,url=${img.url}]`;
        sendTextToGroup(platform, gid, content);

        // 图片已经念出来了，戏群聊天记录里就有了，rp_archive 上那份不用再留着占配额
        if (img) deleteCollectedImage(img.url);
        delete submits[person.uid];
        delete images[person.uid];
        idx++;
    }
    mainKvSet("sys_entrance_submit", submits);
    mainKvSet("sys_entrance_image", images);

    if (idx >= order.length) {
        mainKvSet("sys_entrance_state", { active: false, index: idx });
        if (idx !== state.index || forceAnnounce) sendTextToGroup(platform, gid, "🎭 出场已全部完成！");
        return;
    }

    mainKvSet("sys_entrance_state", { active: true, index: idx });
    if (idx !== state.index || forceAnnounce) {
        sendTextToGroup(platform, gid, `[CQ:at,qq=${order[idx].uid}] 轮到你出场啦，请发送「提交出场」或「提交出场图片」`);
    }
}

let cmdDrawEntranceOrder = seal.ext.newCmdItemInfo();
cmdDrawEntranceOrder.name = "抽取出场顺序";
cmdDrawEntranceOrder.help = "。抽取出场顺序 —— 管理员专属，随机排出所有已绑定非NPC角色的出场顺序并发到公告群；重新执行会重新打乱";
cmdDrawEntranceOrder.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const platform = msg.platform;
    const roster = shuffleInPlace(getEntranceRoster(platform));
    if (roster.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 没有找到任何已绑定角色的非NPC玩家");
        return seal.ext.newCmdExecuteResult(true);
    }
    mainKvSet("sys_entrance_order", roster);
    mainKvSet("sys_entrance_state", { active: false, index: 0 });

    const listText = roster.map((r, i) => `${i + 1}. ${r.roleName}`).join("\n");
    const announceGid = mainKvGet("adminAnnounceGroupId", null);
    if (announceGid) {
        sendTextToGroup(platform, announceGid, `🎭 出场顺序已抽取（共${roster.length}人）：\n${listText}`);
        seal.replyToSender(ctx, msg, "✅ 出场顺序已重新抽取并发布到公告群。");
    } else {
        seal.replyToSender(ctx, msg, `⚠️ 未配置公告群，出场顺序仅在此显示：\n${listText}`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["抽取出场顺序"] = cmdDrawEntranceOrder;

let cmdStartEntrance = seal.ext.newCmdItemInfo();
cmdStartEntrance.name = "开始出场";
cmdStartEntrance.help = "。开始出场 —— 管理员专属，按抽取好的顺序在戏群依次艾特出场；已提交的自动发出并跳到下一个";
cmdStartEntrance.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (!getEntranceShowGid()) {
        seal.replyToSender(ctx, msg, "❌ 未配置戏群（与点歌共用的戏群配置），请先配置");
        return seal.ext.newCmdExecuteResult(true);
    }
    const order = mainKvGet("sys_entrance_order", []);
    if (order.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 还没有抽取出场顺序，请先执行「抽取出场顺序」");
        return seal.ext.newCmdExecuteResult(true);
    }
    const state = mainKvGet("sys_entrance_state", { active: false, index: 0 });
    if (state.active) {
        seal.replyToSender(ctx, msg, `⚠️ 出场已经在进行中（第${state.index + 1}位），继续等待或使用「跳过出场」`);
    } else {
        mainKvSet("sys_entrance_state", { active: true, index: 0 });
        seal.replyToSender(ctx, msg, "✅ 出场开始！");
    }
    tryAdvanceEntrance(ctx, msg.platform, true);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始出场"] = cmdStartEntrance;

let cmdSkipEntrance = seal.ext.newCmdItemInfo();
cmdSkipEntrance.name = "跳过出场";
cmdSkipEntrance.help = "。跳过出场 —— 管理员专属，当前等待的人不提交时手动跳到下一个（不影响其已保存的出场内容，之后仍可被念出）";
cmdSkipEntrance.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const state = mainKvGet("sys_entrance_state", { active: false, index: 0 });
    if (!state.active) {
        seal.replyToSender(ctx, msg, "❌ 出场流程未在进行中");
        return seal.ext.newCmdExecuteResult(true);
    }
    const order = mainKvGet("sys_entrance_order", []);
    const skipped = order[state.index];
    mainKvSet("sys_entrance_state", { active: true, index: state.index + 1 });
    seal.replyToSender(ctx, msg, `⏭️ 已跳过「${skipped ? skipped.roleName : "?"}」的出场`);
    tryAdvanceEntrance(ctx, msg.platform, true);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["跳过出场"] = cmdSkipEntrance;

// 「查看出场状态」：管理员用，不用等实时流程就能看整体进度——谁已经出过场、当前轮到谁等了多久、
// 后面的人里谁已经提前交了、谁还完全没交
let cmdEntranceStatus = seal.ext.newCmdItemInfo();
cmdEntranceStatus.name = "查看出场状态";
cmdEntranceStatus.help = "。查看出场状态 —— 管理员专属，查看出场顺序、已出场人数、当前轮到谁及已等待时长、后面每个人是否已提前提交";
cmdEntranceStatus.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可用");
        return seal.ext.newCmdExecuteResult(true);
    }
    const order = mainKvGet("sys_entrance_order", []);
    if (order.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 还没有抽取出场顺序");
        return seal.ext.newCmdExecuteResult(true);
    }
    const state = mainKvGet("sys_entrance_state", { active: false, index: 0 });
    const submits = mainKvGet("sys_entrance_submit", {});
    const images = mainKvGet("sys_entrance_image", {});

    let header;
    if (order.length && state.index >= order.length && !state.active) {
        header = `🎭 出场状态：已全部完成（共${order.length}人）`;
    } else if (!state.active) {
        header = `🎭 出场状态：尚未开始（发送「开始出场」启动，共${order.length}人）`;
    } else {
        const current = order[state.index];
        const currentS = current ? (submits[current.uid] || images[current.uid]) : null;
        header = `🎭 出场状态：进行中（第${state.index + 1}/${order.length}位）\n` +
                 `⏳ 当前轮到：${current ? current.roleName : "?"}` +
                 (currentS ? "" : "（尚未提交）");
    }

    const lines = order.map((p, i) => {
        if (i < state.index) return `✅ ${p.roleName}（已出场）`;
        const sub = submits[p.uid];
        const img = images[p.uid];
        if (i === state.index && state.active) {
            return `⏳ ${p.roleName}（当前轮到，${sub || img ? "已提交，即将发出" : "还没提交"}）`;
        }
        if (sub && img) return `📝📷 ${p.roleName}（已提前提交文字+图片）`;
        if (sub) return `📝 ${p.roleName}（已提前提交文字）`;
        if (img) return `📷 ${p.roleName}（已提前提交图片）`;
        return `⬜ ${p.roleName}（还没提交）`;
    });

    seal.replyToSender(ctx, msg, `${header}\n\n${lines.join("\n")}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看出场状态"] = cmdEntranceStatus;

// 「提交出场 名字\n内容」：名字须与发言人绑定角色一致，反复提交覆盖
function handleEntranceSubmit(ctx, msg, subM) {
    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const roleName = getRoleName(ctx, msg);
    if (!roleName) {
        seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const name = subM[1].trim();
    const content = subM[2].trim();
    if (name !== roleName) {
        seal.replyToSender(ctx, msg, `❌ 名字「${name}」与你绑定的角色「${roleName}」不符`);
        return seal.ext.newCmdExecuteResult(true);
    }
    let submits = mainKvGet("sys_entrance_submit", {});
    submits[uid] = { roleName, content, time: Date.now() };
    mainKvSet("sys_entrance_submit", submits);
    seal.replyToSender(ctx, msg, "✅ 出场内容已保存，轮到你时会自动发出。");
    tryAdvanceEntrance(ctx, platform);
    return seal.ext.newCmdExecuteResult(true);
}

// 回复自己发的图片消息「提交出场图片 评论」：和点歌一样经 get_msg 读原消息，图片转存失败就不保存（QQ链接会过期，不留死链）
function handleEntranceImageSubmit(ctx, msg, raw, wdId) {
    const platform = msg.platform;
    const uid = getPrimaryUid(platform, msg.sender.userId.replace(`${platform}:`, ""));
    const roleName = getRoleName(ctx, msg);
    if (!roleName) {
        seal.replyToSender(ctx, msg, "❌ 请先创建角色。");
        return seal.ext.newCmdExecuteResult(true);
    }
    const commentMatch = raw.match(/提交出场图片\s*([\s\S]*)$/);
    const comment = commentMatch ? commentMatch[1].trim() : "";
    const errMsg = "❌ 提交失败：LLOneBot 未能读取该消息（可能不在缓存中）。";
    wsRequest(
        { action: "get_msg", params: { message_id: wdId } },
        (response) => {
            if (response.status !== "ok" && response.retcode !== 0) return seal.replyToSender(ctx, msg, errMsg);
            const data = response.data;
            const originalContent = data && (typeof data.message === "string" ? data.message : JSON.stringify(data.message || ""));
            const imgTagMatch = originalContent && originalContent.match(/\[CQ:image,[^\]]*\]/);
            const srcUrl = imgTagMatch && extractImageSrc(imgTagMatch[0]);
            if (!srcUrl) return seal.replyToSender(ctx, msg, "❌ 回复的消息里没有找到可下载的图片链接");
            (async () => {
                const permanentUrl = await collectImageToArchive(srcUrl, uid);
                if (!permanentUrl) return seal.replyToSender(ctx, msg, "❌ 图片转存失败，请重新发送图片后再提交");
                let images = mainKvGet("sys_entrance_image", {});
                // 反复提交会覆盖，旧图不再被引用，从 rp_archive 删掉避免白占配额
                if (images[uid]) deleteCollectedImage(images[uid].url);
                images[uid] = { roleName, url: permanentUrl, comment, time: Date.now() };
                mainKvSet("sys_entrance_image", images);
                seal.replyToSender(ctx, msg, "✅ 出场图片已保存，轮到你时会自动发出。");
                tryAdvanceEntrance(ctx, platform);
            })();
        },
        () => seal.replyToSender(ctx, msg, errMsg)
    );
    return seal.ext.newCmdExecuteResult(true);
}

// ========================
// 出场相关的无前缀触发（通过 onNotCommandReceived 处理）
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = (msg.rawMessage || msg.message || "").trim();
    const platform = msg.platform;
    const groupId = msg.groupId.replace(`${platform}-Group:`, '');

    // 回复图片消息「提交出场图片 评论」
    const replyMatch = raw.match(/\[CQ:reply,id=(\-?\d+)\]/);
    if (replyMatch && raw.includes("提交出场图片")) {
        return handleEntranceImageSubmit(ctx, msg, raw, Number(replyMatch[1]));
    }

    // 提交出场图片引导（未回复图片消息时单独发送）
    if (raw === "提交出场图片") {
        return seal.replyToSender(ctx, msg, "📷 提交出场图片用法：先发一张图片，再回复那条消息发送\n提交出场图片 评论内容\n（评论可省略）");
    }

    // 出场进行中：戏群里直接发「当前轮到的人名 + 换行 + 内容」，不带指令前缀也当作已出场
    const entranceState = mainKvGet("sys_entrance_state", { active: false, index: 0 });
    if (entranceState.active && raw.includes("\n") && groupId === getEntranceShowGid()) {
        const entranceOrder = mainKvGet("sys_entrance_order", []);
        const currentPerson = entranceOrder[entranceState.index];
        if (currentPerson) {
            const entranceLines = raw.split(/\r?\n/);
            if (entranceLines[0].trim() === currentPerson.roleName) {
                const entranceContent = entranceLines.slice(1).join("\n").trim();
                if (entranceContent) {
                    let entranceSubmits = mainKvGet("sys_entrance_submit", {});
                    entranceSubmits[currentPerson.uid] = { roleName: currentPerson.roleName, content: entranceContent, time: Date.now() };
                    mainKvSet("sys_entrance_submit", entranceSubmits);
                    tryAdvanceEntrance(ctx, platform);
                    return seal.ext.newCmdExecuteResult(true);
                }
            }
        }
    }

    // 「提交出场 名字\n内容」（\s+ 保证不会误吞「提交出场图片」）
    const entranceSubM = raw.match(/^提交出场\s+(.+?)[\r\n]+([\s\S]+)$/);
    if (entranceSubM) return handleEntranceSubmit(ctx, msg, entranceSubM);
};
