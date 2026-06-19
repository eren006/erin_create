// ==UserScript==
// @name         诊断_结戏奖励
// @author       长日将尽
// @version      1.0.0
// @description  【测试脚本，用完可删】模拟结戏奖励判定全流程，不写入任何数据
// ==/UserScript==

let ext = seal.ext.find("debug_end_game_bonus");
if (!ext) {
    ext = seal.ext.new("debug_end_game_bonus", "长日将尽", "1.0.0");
    seal.ext.register(ext);
}

function getMain() { return seal.ext.find("changri"); }

const tplTypeToStored = { "私约": "私密", "心意": "心愿" };

let cmd = seal.ext.newCmdItemInfo();
cmd.name = "诊断结戏奖励";
cmd.help = `【测试脚本】模拟结戏奖励判定，不写入任何数据
用法1：。诊断结戏奖励                          → 检查所有模版配置 + 注册表健康
用法2：。诊断结戏奖励 群号                      → 用该群真实 session 数据模拟
用法3：。诊断结戏奖励 子类型 段数 字数 [耗时]    → 纯数值模拟，如：私约 3 1200 45`;

cmd.solve = (ctx, msg, cmdArgs) => {
    const main = getMain();
    const lines = ["[诊断_结戏奖励] ===== 开始诊断 ====="];

    if (!main) {
        lines.push("❌ 主插件 changri 未找到");
        report(ctx, msg, lines);
        return seal.ext.newCmdExecuteResult(true);
    }
    lines.push("✅ 主插件 changri 已加载");

    // ── 读取公共数据 ──────────────────────────────────────────
    const templates = JSON.parse(main.storageGet("end_game_bonus_templates") || "[]");
    const reg       = JSON.parse(main.storageGet("item_registry")            || "{}");
    const npcList   = JSON.parse(main.storageGet("a_npc_list")               || "[]");
    const apg       = JSON.parse(main.storageGet("a_private_group")          || "{}");

    if (!templates.length) {
        lines.push("❌ end_game_bonus_templates 为空，未配置任何奖励模版");
        report(ctx, msg, lines);
        return seal.ext.newCmdExecuteResult(true);
    }
    const enabledCount = templates.filter(t => t.enabled).length;
    lines.push(`ℹ️  共 ${templates.length} 个模版（启用 ${enabledCount} 个，停用 ${templates.length - enabledCount} 个）`);

    // ── 注册表空检测（强提醒）────────────────────────────────
    const regSize = Object.keys(reg).length;
    if (regSize === 0) {
        lines.push("");
        lines.push("⛔ ================================");
        lines.push("⛔ item_registry 为空！");
        lines.push("⛔ 请立即执行：。全量同步");
        lines.push("⛔ 否则结戏时所有货币/道具奖励");
        lines.push("⛔ 都会发放失败并被跳过！");
        lines.push("⛔ ================================");
        report(ctx, msg, lines);
        return seal.ext.newCmdExecuteResult(true);
    }
    lines.push(`ℹ️  item_registry 共 ${regSize} 条记录`);

    // ── 注册表查找 helpers ────────────────────────────────────
    const currencyByName = {};
    Object.values(reg).forEach(r => { if (r.type === "currency") currencyByName[r.name] = r.code; });

    function lookupCode(targetType, target) {
        // 优先按名称查；找不到则试 target 本身当 code（与 applyRewardItem 兜底逻辑一致）
        if (targetType === "currency") {
            if (currencyByName[target]) return currencyByName[target];
        }
        const upper = target.toUpperCase();
        if (reg[upper]) return upper;
        const found = Object.values(reg).find(v => v.name === target);
        return found ? found.code : null;
    }

    function checkRewardItem(r, indent) {
        const i = indent || "    ";
        if (r.type === "location_draw") return `${i}ℹ️  地点池抽取 ×${r.amount || 1}（运行时检查）`;
        if (r.type === "pool") {
            return (r.items || []).map(item => checkRewardItem(item, i + "  ")).join("\n");
        }
        const target = (r.target || "").trim();
        if (!target) return `${i}⚠️ 奖励目标为空`;
        if (r.targetType === "attr") return `${i}ℹ️  属性「${target}」+${r.amount}（不检查注册表）`;
        const code = lookupCode(r.targetType, target);
        const prob = (r.prob != null && r.prob < 100) ? ` (${r.prob}%)` : "";
        return code
            ? `${i}✅ ${r.targetType === "currency" ? "货币" : "道具"}「${target}」→ ${code} ×${r.amount}${prob}`
            : `${i}❌ 「${target}」在 item_registry 中不存在（${r.targetType}）`;
    }

    // ── 条件评估 ─────────────────────────────────────────────
    function evalCond(op, val, threshold) {
        switch (op) {
            case "=":     return val === threshold;
            case "!=":    return val !== threshold;
            case ">=":    return val >= threshold;
            case "<=":    return val <= threshold;
            case "range": return val >= threshold[0] && val <= threshold[1];
        }
        return false;
    }

    function condStr(c, val) {
        const met = evalCond(c.op, val, c.value);
        const opStr = c.op === "range" ? `${c.value[0]}~${c.value[1]}` : `${c.op}${c.value}`;
        return `${met ? "✅" : "❌"} ${c.param}${opStr}（现${val}）`;
    }

    // ── 核心：对单个玩家做模拟 ───────────────────────────────
    function simulatePlayer(roleName, stat, elapsedMin, subtype) {
        const avgWords = stat.replies > 0 ? Math.floor(stat.words / stat.replies) : 0;

        const getVal = param => {
            switch (param) {
                case "本场个人段数":           return stat.replies;
                case "本场个人总字数":         return stat.words;
                case "本场个人平均每段字数":   return avgWords;
                case "结戏最多耗费时间":       return elapsedMin;
            }
            return 0;
        };

        const matched = templates.filter(t => {
            if (!t.enabled) return false;
            const tplType = t.subtype || "通用";
            if (tplType === "通用") return true;
            return (tplTypeToStored[tplType] || tplType) === subtype;
        });

        const out = [`\n👤 ${roleName}（${stat.replies}段 · ${stat.words}字 · 均${avgWords}字/段 · 耗时${elapsedMin}分）`];

        if (!matched.length) {
            out.push(`  ⚠️ 无匹配的启用模版（场次类型=${subtype || "未知"}）`);
            return out;
        }

        let anyReward = false;

        for (const tpl of matched) {
            out.push(`  📋 模版「${tpl.name}」（${tpl.subtype || "通用"}）：`);
            for (const group of (tpl.groups || [])) {
                const groupLabel = group.op === "or" ? "[or-取首个满足]" : "[and-全部条件]";
                for (const block of (group.blocks || [])) {
                    const conds = block.conditions || [];
                    const allMet = conds.every(c => evalCond(c.op, getVal(c.param), c.value));
                    const condStr_ = conds.map(c => condStr(c, getVal(c.param))).join(" | ");
                    const rewards = block.rewards || [];

                    if (allMet) {
                        anyReward = true;
                        const rewardDescs = rewards.map(r => {
                            if (r.type === "pool") {
                                const total = (r.items || []).reduce((s, i) => s + i.weight, 0);
                                return `🎲${(r.items || []).map(i => `${i.target}×${i.amount}(${total > 0 ? Math.round(i.weight/total*100) : 0}%)`).join("/")}`;
                            }
                            if (r.type === "location_draw") return `🎰地点池×${r.amount || 1}`;
                            const prob = (r.prob != null && r.prob < 100) ? `(${r.prob}%)` : "";
                            return `${r.target}×${r.amount}${prob}`;
                        });
                        out.push(`    🎁 命中 ${groupLabel}`);
                        out.push(`       条件：${condStr_}`);
                        out.push(`       奖励：${rewardDescs.join("、")}`);
                    } else {
                        out.push(`    ⏳ 未达 ${groupLabel}: ${condStr_}`);
                    }

                    if (group.op === "or" && allMet) break; // or 模式命中即停
                }
            }
        }

        if (!anyReward) out.push("  （本次不会发放任何奖励）");
        return out;
    }

    // ── 解析参数，分流 ────────────────────────────────────────
    const arg1 = cmdArgs.getArgN(1);
    const arg2 = cmdArgs.getArgN(2);
    const arg3 = cmdArgs.getArgN(3);
    const arg4 = cmdArgs.getArgN(4);

    const isGroupMode = arg1 && /^\d{5,}$/.test(arg1);
    const isMockMode  = arg1 && !isGroupMode && arg2 && arg3;

    if (!arg1) {
        // 模式1：仅健康检查
        lines.push("\n📋 模版注册表健康检查：");
        for (const tpl of templates) {
            lines.push(`\n  [${tpl.enabled ? "✅启用" : "⏸️停用"}] 「${tpl.name}」 subtype=${tpl.subtype || "通用"}`);
            for (const group of (tpl.groups || [])) {
                for (const block of (group.blocks || [])) {
                    const conds = (block.conditions || []).map(c => `${c.param}${c.op}${c.value}`).join(" & ");
                    lines.push(`    条件：${conds || "（无条件，必然触发）"}`);
                    for (const r of (block.rewards || [])) {
                        lines.push(checkRewardItem(r, "      "));
                    }
                }
            }
        }

    } else if (isGroupMode) {
        // 模式2：真实群数据
        const groupId = arg1;
        const sessionStats = JSON.parse(main.storageGet("group_session_stats") || "{}");
        const groupStat = sessionStats[groupId];

        if (!groupStat) {
            lines.push(`❌ 群 ${groupId} 没有 session stats（场次未开始或已结束）`);
            report(ctx, msg, lines);
            return seal.ext.newCmdExecuteResult(true);
        }

        const playerKeys = Object.keys(groupStat).filter(k => k !== "_startTime");
        if (!playerKeys.length) {
            lines.push(`❌ 群 ${groupId} 的 session stats 中没有玩家数据`);
            report(ctx, msg, lines);
            return seal.ext.newCmdExecuteResult(true);
        }

        const bSched = JSON.parse(main.storageGet("b_confirmedSchedule") || "{}");
        let subtype = "";
        outer: for (const evList of Object.values(bSched)) {
            for (const ev of evList) {
                if (ev.group === groupId && ev.subtype) { subtype = ev.subtype; break outer; }
            }
        }

        const elapsedMin = groupStat._startTime
            ? Math.floor((Date.now() - groupStat._startTime) / 60000)
            : 0;

        lines.push(`\n🎯 群 ${groupId} | 类型「${subtype || "未知"}」| 已用时 ${elapsedMin} 分钟`);
        lines.push(`   session 中有 ${playerKeys.length} 个 uid（NPC名单：${npcList.join(",") || "空"}）`);

        for (const uid of playerKeys) {
            let roleName = uid;
            for (const pf of Object.keys(apg)) {
                if (apg[pf][uid]) { roleName = apg[pf][uid][0]; break; }
            }
            if (npcList.includes(roleName)) {
                lines.push(`\n👤 ${roleName}（NPC，结戏不发奖励，跳过）`);
                continue;
            }
            lines.push(...simulatePlayer(roleName, groupStat[uid], elapsedMin, subtype));
        }

    } else if (isMockMode) {
        // 模式3：纯数值模拟
        const subtypeRaw = arg1;
        const replies  = parseInt(arg2)  || 0;
        const words    = parseInt(arg3)  || 0;
        const elapsed  = parseInt(arg4)  || 0;
        const subtype  = tplTypeToStored[subtypeRaw] || subtypeRaw;

        lines.push(`\n🧪 模拟模式：子类型「${subtypeRaw}」→ 内部「${subtype}」`);
        lines.push(...simulatePlayer("模拟玩家", { replies, words }, elapsed, subtype));
    }

    report(ctx, msg, lines);
    return seal.ext.newCmdExecuteResult(true);
};

function report(ctx, msg, lines) {
    const text = lines.join("\n");
    console.log(text);
    seal.replyToSender(ctx, msg, text);
}

ext.cmdMap["诊断结戏奖励"] = cmd;

console.log("✅ 诊断_结戏奖励 已加载，发送「。诊断结戏奖励」开始检查");
