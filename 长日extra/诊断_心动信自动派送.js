// ==UserScript==
// @name         诊断_心动信自动派送
// @author       长日将尽
// @version      1.1.0
// @description  【测试脚本，用完可删】检查心动信自动派送的全链路状态，不写入任何数据
// ==/UserScript==

let ext = seal.ext.find("debug_lovemail_auto");
if (!ext) {
    ext = seal.ext.new("debug_lovemail_auto", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}

function getMain() { return seal.ext.find("changri"); }
function getSocial() { return seal.ext.find("changriV1"); }

function storGet(main, key) {
    try { return main.storageGet(key) || ""; } catch(e) { return ""; }
}

// 和 长日社交.js 完全一样的 getSafeEndPoint
function getSafeEndPoint(platform = "QQ") {
    const eps = seal.getEndPoints();
    if (!eps || eps.length === 0) return null;
    let target = eps.find(e => e.platform === platform && e.state === 1);
    if (!target) target = eps.find(e => e.state === 1);
    if (!target) target = eps[0];
    return target;
}

// 和 长日社交.js 完全一样的 sendTextToGroup
function sendTextToGroup(platform, gid, text) {
    const ep = getSafeEndPoint(platform);
    if (!ep) throw new Error("getSafeEndPoint 返回 null");
    const target = `${platform}-Group:${gid.toString().replace(/\D/g, "")}`;
    const m = seal.newMessage();
    m.messageType = "group";
    m.groupId = target;
    seal.replyToSender(seal.createTempCtx(ep, m), m, text);
}

let _diagTestTimer = null;

let cmd = seal.ext.newCmdItemInfo();
cmd.name = "诊断心动信";
cmd.help = `【测试脚本】检查心动信自动派送全链路，管理员专用
用法1：。诊断心动信            → 全链路状态报告
用法2：。诊断心动信 测试定时器  → 注册一个 30 秒后触发的测试 timer，用和心动信相同的代码路径往后台群发消息
用法3：。诊断心动信 取消测试   → 取消尚未触发的测试 timer
用法4：。诊断心动信 重启定时器  → 重新注册心动信自动派送 timer（原 timer 可能因异常被杀死时使用）`;

cmd.solve = (ctx, msg, cmdArgs) => {
    const main = getMain();
    if (!main) {
        seal.replyToSender(ctx, msg, "❌ 主插件 changri 未找到");
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 模式：重启定时器 ────────────────────────────────────────
    if (cmdArgs.getArgN(1) === "重启定时器") {
        const restart = globalThis._changriV1RestartLoveMail;
        if (typeof restart !== "function") {
            seal.replyToSender(ctx, msg, "❌ 找不到 _changriV1RestartLoveMail，请确认社交插件 changriV1 已加载且版本支持此操作。");
            return seal.ext.newCmdExecuteResult(true);
        }
        try {
            restart();
            seal.replyToSender(ctx, msg, "✅ 已重置心动信触发记录（_loveMailLastTriggerMinute = -1）。\n现在由主插件的 setInterval 每 30 秒驱动，到达派送时间时自动触发。");
        } catch(e) {
            seal.replyToSender(ctx, msg, `❌ 重启失败：${e.message || String(e)}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 模式：取消测试 ─────────────────────────────────────────
    if (cmdArgs.getArgN(1) === "取消测试") {
        if (_diagTestTimer !== null) {
            clearInterval(_diagTestTimer);
            _diagTestTimer = null;
            seal.replyToSender(ctx, msg, "✅ 测试定时器已取消，不会再发送测试消息。");
        } else {
            seal.replyToSender(ctx, msg, "ℹ️ 当前没有待触发的测试定时器。");
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 模式：测试定时器 ────────────────────────────────────────
    if (cmdArgs.getArgN(1) === "测试定时器") {
        const bgGid = JSON.parse(storGet(main, "background_group_id") || "null");
        if (!bgGid) {
            seal.replyToSender(ctx, msg, "❌ 未配置 background_group_id，无法测试（请先在设置里配置后台群）");
            return seal.ext.newCmdExecuteResult(true);
        }
        if (_diagTestTimer !== null) {
            seal.replyToSender(ctx, msg, "⚠️ 已有一个测试定时器在等待中，请先发「。诊断心动信 取消测试」再重新启动。");
            return seal.ext.newCmdExecuteResult(true);
        }

        seal.replyToSender(ctx, msg,
            `⏳ 测试定时器已启动\n` +
            `将在 30 秒后，用和心动信定时器完全相同的代码路径，` +
            `向后台群 ${bgGid} 发送测试消息。\n` +
            `请在 30 秒后检查后台群是否收到「[诊断] 定时器测试消息」。\n` +
            `如需提前取消：。诊断心动信 取消测试`
        );

        _diagTestTimer = setInterval(() => {
            clearInterval(_diagTestTimer);
            _diagTestTimer = null;
            let timerOk = false;
            let errMsg = "";
            try {
                sendTextToGroup("QQ", bgGid,
                    `[诊断] 定时器测试消息\n` +
                    `时间：${new Date().toLocaleTimeString()}\n` +
                    `结论：✅ setInterval + seal.replyToSender + createTempCtx 路径正常`
                );
                timerOk = true;
            } catch(e) {
                errMsg = e.message || String(e);
            }

            // 也回报给发指令的群
            try {
                const epBack = getSafeEndPoint(msg.platform);
                if (epBack) {
                    const mBack = seal.newMessage();
                    mBack.messageType = msg.messageType;
                    mBack.groupId = msg.groupId;
                    seal.replyToSender(seal.createTempCtx(epBack, mBack), mBack,
                        timerOk
                            ? `✅ 定时器测试完成：消息已发往后台群 ${bgGid}，请确认是否收到。`
                            : `❌ 定时器测试失败：sendTextToGroup 抛出异常\n${errMsg}\n这说明 timer 里 seal.replyToSender 路径有问题。`
                    );
                }
            } catch(e2) {}
        }, 30000);

        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 模式：全链路诊断（默认）────────────────────────────────
    const lines = ["🔍 心动信自动派送诊断"];

    // ── 1. 插件加载 ────────────────────────────────────────────
    lines.push("\n【插件加载】");
    const social = getSocial();
    lines.push(`  主插件 changri：✅ 已加载`);
    lines.push(`  社交插件 changriV1：${social ? "✅ 已加载" : "❌ 未找到（心动信定时器在此）"}`);

    // ── 1b. 定时器状态 ─────────────────────────────────────────
    lines.push("\n【心动信定时器状态】");
    lines.push(`  驱动方式：主插件 changri 的 setInterval（loveMailTick 直接内联，不再依赖 globalThis）`);
    const lastTick = globalThis._changriV1LastTick || null;
    if (lastTick === null) {
        lines.push(`  上次 tick：从未记录（主插件加载后还没有触发过，或刚重启）`);
    } else {
        const secAgo = Math.round((Date.now() - lastTick) / 1000);
        const status = secAgo <= 35 ? "✅ 正常" : secAgo <= 120 ? "⚠️ 略慢" : "❌ 已停止（超过 120s 未 tick）";
        lines.push(`  上次 tick：${secAgo} 秒前  ${status}（正常应 ≤30 秒）`);
    }

    // ── 2. 功能开关 ────────────────────────────────────────────
    lines.push("\n【功能开关】");
    let toggle = {};
    try { toggle = JSON.parse(storGet(main, "global_feature_toggle") || "{}"); } catch(e) {}
    const loEnabled = toggle.enable_lovemail !== false;
    lines.push(`  enable_lovemail 原始值：${JSON.stringify(toggle.enable_lovemail)}`);
    lines.push(`  isLoveMailEnabled 判断：${loEnabled ? "✅ true（允许派送）" : "❌ false（定时器会跳过）"}`);

    // ── 3. 派送时间 ────────────────────────────────────────────
    lines.push("\n【派送时间】");
    const rawTime = storGet(main, "lovemail_delivery_time");
    const deliveryTime = rawTime.replace(/"/g, "").trim() || "22:00";
    lines.push(`  lovemail_delivery_time 原始值：${JSON.stringify(rawTime)}`);
    lines.push(`  解析后使用：${deliveryTime}`);
    const timeParts = deliveryTime.split(":").map(Number);
    const timeOk = timeParts.length === 2 && !isNaN(timeParts[0]) && !isNaN(timeParts[1]);
    if (!timeOk) {
        lines.push(`  格式：❌ 解析失败（定时器每轮都会 return，永不触发）`);
    } else {
        const [tH, tM] = timeParts;
        const tgt = tH * 60 + tM;
        const now = new Date();
        const cur = now.getHours() * 60 + now.getMinutes();
        const fmt = (t) => `${String(Math.floor(t/60)).padStart(2,"0")}:${String(t%60).padStart(2,"0")}`;
        lines.push(`  格式：✅ 有效`);
        lines.push(`  当前时间：${fmt(cur)}，目标：${fmt(tgt)}`);
        lines.push(`  -5min 预警：${fmt((tgt-5+1440)%1440)}，-10min 预警：${fmt((tgt-10+1440)%1440)}`);
        if (cur === tgt) lines.push(`  ⚡ 现在正好是派送时间！`);
    }

    // ── 4. EndPoint ────────────────────────────────────────────
    lines.push("\n【EndPoint（机器人连接）】");
    const eps = seal.getEndPoints();
    if (!eps || eps.length === 0) {
        lines.push(`  ❌ 无任何 EndPoint（定时器内 getSafeEndPoint 会返回 null，派送中止）`);
    } else {
        const active = eps.filter(e => e.state === 1);
        lines.push(`  共 ${eps.length} 个，状态=1（在线）：${active.length} 个`);
        active.forEach(e => lines.push(`    ✅ ${e.platform} state=${e.state}`));
        if (active.length === 0) lines.push(`  ❌ 无在线 EndPoint（派送中止）`);
    }

    // ── 5. 信件池 ───────────────────────────────────────────────
    lines.push("\n【信件池 lovemail_pool】");
    let pool = [];
    try { pool = JSON.parse(storGet(main, "lovemail_pool") || "[]"); } catch(e) {}
    if (pool.length === 0) {
        lines.push(`  信池为空（若派送时也为空，performLoveMailDelivery 直接返回，不发任何消息）`);
    } else {
        lines.push(`  共 ${pool.length} 封待派送`);
        const byReceiver = {};
        pool.forEach(r => { byReceiver[r.receiver] = (byReceiver[r.receiver] || 0) + 1; });
        Object.entries(byReceiver).forEach(([r, n]) => lines.push(`    「${r}」× ${n} 封`));
    }

    // ── 6. 私信群映射 ───────────────────────────────────────────
    lines.push("\n【私信群映射 a_private_group】");
    const platform = msg.platform;
    let apg = {};
    try { apg = JSON.parse(storGet(main, "a_private_group") || "{}"); } catch(e) {}
    const groups = apg[platform] || {};
    lines.push(`  ${platform} 已登记：${Object.keys(groups).length} 个 uid`);
    if (pool.length > 0) {
        lines.push(`  信池中收件人检查：`);
        const receivers = [...new Set(pool.map(r => r.receiver))];
        for (const receiver of receivers) {
            let foundUid = null;
            for (const [uid, arr] of Object.entries(groups)) {
                if (arr && arr[0] === receiver) { foundUid = uid; break; }
            }
            const addr = foundUid ? groups[foundUid] : null;
            if (!foundUid) {
                lines.push(`    「${receiver}」❌ 找不到 uid（信会进 failedRecords）`);
            } else if (!addr || !addr[1]) {
                lines.push(`    「${receiver}」❌ uid=${foundUid} 但无群号`);
            } else {
                lines.push(`    「${receiver}」✅ uid=${foundUid}，私信群=${addr[1]}`);
            }
        }
    }

    // ── 7. 后台群 ───────────────────────────────────────────────
    lines.push("\n【后台群 background_group_id】");
    const bgGid = JSON.parse(storGet(main, "background_group_id") || "null");
    lines.push(`  ${bgGid !== null ? `✅ ${bgGid}` : "未配置（跳过清单发送，不影响派送本身）"}`);

    // ── 8. 公告群 ───────────────────────────────────────────────
    lines.push("\n【公告群 adminAnnounceGroupId】");
    const announceGid = JSON.parse(storGet(main, "adminAnnounceGroupId") || "null");
    lines.push(`  ${announceGid !== null ? `✅ ${announceGid}（-5min 预警会发这里）` : "未配置（跳过预警消息）"}`);

    // ── 9. 派送计数 ─────────────────────────────────────────────
    lines.push("\n【派送计数 a_meetingCount_lovemail】");
    const deliverCount = parseInt(storGet(main, "a_meetingCount_lovemail") || "0");
    lines.push(`  本季累计成功派送次数：${deliverCount}`);
    lines.push(`  （每次 performLoveMailDelivery 发出至少 1 封才 +1）`);

    lines.push("\n提示：。诊断心动信 测试定时器  → 30 秒后向公告群发测试消息，验证 timer 发送路径");
    lines.push("===== 诊断完成 =====");
    seal.replyToSender(ctx, msg, lines.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["诊断心动信"] = cmd;
