// ==UserScript==
// @name         诊断_写信综复盘
// @author       长日将尽
// @version      1.0.0
// @description  【临时诊断脚本，用完即删】检查发送信件为何无法复盘，逐层排查开关/同步/存档连通性
// ==/UserScript==

let ext = seal.ext.find("debug_letter_fupan");
if (!ext) {
    ext = seal.ext.new("debug_letter_fupan", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}

function getMain() {
    return seal.ext.find("changri");
}

// ========================
// 诊断命令：。诊断写信综
// ========================

let cmd = seal.ext.newCmdItemInfo();
cmd.name = "诊断写信综";
cmd.help = "【临时诊断】检查写信综复盘不可用的原因";

cmd.solve = async (ctx, msg, cmdArgs) => {
    const main = getMain();
    const lines = ["[诊断_写信综复盘] ========== 开始诊断 =========="];

    // ── 第一层：主插件是否存在 ──────────────────────────────
    if (!main) {
        lines.push("❌ [1] 主插件 changri 未找到 → 所有检查终止");
        report(ctx, msg, lines);
        return seal.ext.newCmdExecuteResult(true);
    }
    lines.push("✅ [1] 主插件 changri 已加载");

    // ── 第二层：发送信件功能开关 ────────────────────────────
    let featureToggle = {};
    try {
        featureToggle = JSON.parse(main.storageGet("global_feature_toggle") || "{}");
    } catch (e) {
        lines.push("❌ [2] global_feature_toggle 解析失败：" + e.message);
    }
    const letterEnabled = featureToggle.enable_direct_letter === true;
    lines.push(
        (letterEnabled ? "✅" : "❌") +
        ` [2] 发送信件功能开关（enable_direct_letter）= ${featureToggle.enable_direct_letter ?? "未设置"}` +
        (!letterEnabled ? " → 玩家根本无法发信，存档自然没有记录" : "")
    );

    // ── 第三层：RP存档传输总开关 ────────────────────────────
    const archiveEnabled = seal.ext.getBoolConfig(main, "启用RP存档传输");
    lines.push(
        (archiveEnabled ? "✅" : "❌") +
        ` [3] 启用RP存档传输 = ${archiveEnabled}` +
        (!archiveEnabled ? " → 所有上报被拦截，不仅写信综，短信/礼物也不会上报（但你说短信可以？请核查）" : "")
    );

    // ── 第四层：写信综同步开关 ──────────────────────────────
    const syncRaw = main.storageGet("direct_letter_sync_enabled") || "false";
    const syncEnabled = syncRaw.trim() === "true";
    lines.push(
        (syncEnabled ? "✅" : "❌") +
        ` [4] 写信综同步开关（direct_letter_sync_enabled）= "${syncRaw}"` +
        (!syncEnabled ? " → isLetterSyncEnabled() 返回 false，发信时不会调用 postToArchive" : "")
    );

    // ── 第五层：存档服务器地址 ──────────────────────────────
    const archiveBase = (seal.ext.getStringConfig(main, "RP存档服务器地址") || "").replace(/\/$/, "");
    lines.push(
        (archiveBase ? "✅" : "❌") +
        ` [5] RP存档服务器地址 = "${archiveBase || "（空）"}"` +
        (!archiveBase ? " → postToArchive 会直接 return，不发请求" : "")
    );

    // ── 第六层：Token ───────────────────────────────────────
    const token = seal.ext.getStringConfig(main, "RP存档Token") || "";
    lines.push(`ℹ️  [6] RP存档Token = ${token ? "已配置（不展示内容）" : "（空，不验证）"}`);

    // ── 第七层：今日是否有人发过信 ─────────────────────────
    const dayCountsRaw = main.storageGet("letter_day_counts") || "{}";
    let dayCounts = {};
    try { dayCounts = JSON.parse(dayCountsRaw); } catch (e) {}
    const totalSent = Object.values(dayCounts).reduce((s, v) => s + (v.count || 0), 0);
    const gameDay = main.storageGet("global_days") || "未设置";
    lines.push(
        (totalSent > 0 ? "✅" : "⚠️") +
        ` [7] letter_day_counts 当前游戏日 ${gameDay} 共发信记录：${totalSent} 封` +
        (totalSent === 0 ? " → 从未有人发过信，存档里不会有 direct_letter 事件（这是正常的，不是错误）" : "")
    );

    // ── 第八层：实际连通性测试 ──────────────────────────────
    if (archiveBase && archiveEnabled && syncEnabled) {
        lines.push("⏳ [8] 正在尝试向存档发送测试事件（dry-run）...");
        try {
            const testPayload = {
                type:       "direct_letter",
                from_role:  "__诊断测试__",
                from_qq:    "0",
                to_role:    "__诊断测试__",
                to_qq:      "",
                content:    "这是一条诊断测试消息，请忽略",
                extra_info: { signature: "诊断", date_tag: "", attachment: "", _is_debug: true },
                game_day:   gameDay,
                session_id: "",
                timestamp:  Date.now()
            };
            const resp = await fetch(archiveBase + "/api/event", {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-Archive-Token": token },
                body: JSON.stringify(testPayload)
            });
            const text = await resp.text();
            if (resp.ok) {
                lines.push(`✅ [8] 连通性测试成功，HTTP ${resp.status}，响应：${text.slice(0, 100)}`);
                lines.push("   ⚠️  注意：测试事件已写入存档，请去后台手动删除 from_role='__诊断测试__' 的记录");
            } else {
                lines.push(`❌ [8] 连通性测试失败，HTTP ${resp.status}，响应：${text.slice(0, 200)}`);
            }
        } catch (e) {
            lines.push(`❌ [8] 连通性测试抛出异常：${e.message || String(e)}`);
        }
    } else {
        lines.push("⏭️  [8] 跳过连通性测试（前置条件不满足）");
    }

    // ── 综合诊断结论 ────────────────────────────────────────
    lines.push("");
    lines.push("========== 诊断结论 ==========");
    if (!letterEnabled) {
        lines.push("根本原因：发送信件功能未开启。请先执行「。启用写信综 开启」或在设置中开启「发送信件」。");
    } else if (!archiveEnabled) {
        lines.push("根本原因：RP存档传输总开关关闭。但你说短信可以复盘，这里矛盾，请检查是否有多个 changri 实例。");
    } else if (!syncEnabled) {
        lines.push("根本原因：写信综的同步开关未开。执行「。信件设置 同步 开」即可。");
    } else if (!archiveBase) {
        lines.push("根本原因：存档服务器地址为空。");
    } else if (totalSent === 0) {
        lines.push("目前无问题，只是还没有玩家发过信，所以存档里没有记录，/letters 页面显示锁屏。一旦有人发信就会自动出现。");
    } else {
        lines.push("配置看起来都正确，但有信件记录却无法复盘。请看 [8] 连通性测试结果。");
    }

    report(ctx, msg, lines);
    return seal.ext.newCmdExecuteResult(true);
};

function report(ctx, msg, lines) {
    const text = lines.join("\n");
    console.log(text);
    seal.replyToSender(ctx, msg, text);
}

ext.cmdMap["诊断写信综"] = cmd;

console.log("✅ 诊断_写信综复盘 已加载，发送「。诊断写信综」开始检查");
