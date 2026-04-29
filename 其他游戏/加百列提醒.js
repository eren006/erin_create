// ==UserScript==
// @name         大天使加百列
// @author       长日将尽
// @version      1.2.0
// @description  吾乃加百列，奉命为你铭记此刻——无需引号，直述心声。🕊️
// @license      MIT
// ==/UserScript==

function parseTimeInfo(timeStr) {
    const trimmed = timeStr.trim();

    // 相对时间：如 "5分钟后"、"2小时后"
    const relativeMatch = trimmed.match(/^(\d+)(分钟|小时|天)后$/);
    if (relativeMatch) {
        const num = parseInt(relativeMatch[1], 10);
        const unit = relativeMatch[2];
        let ms = 0;

        if (unit === '分钟') ms = num * 60 * 1000;
        else if (unit === '小时') ms = num * 60 * 60 * 1000;
        else if (unit === '天') ms = num * 24 * 60 * 60 * 1000;

        return {
            type: 'relative',
            timestamp: Date.now() + ms,
            repeat: false,
            timing: trimmed
        };
    }

    // 每日重复：如 "每天14:30" 或 "每天14：30"
    const dailyMatch = trimmed.match(/^每天\s*(\d{1,2})[:：](\d{1,2})$/);
    if (dailyMatch) {
        const hours = parseInt(dailyMatch[1], 10);
        const minutes = parseInt(dailyMatch[2], 10);

        if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
            throw new Error("时辰有误：小时应为 0–23，分钟应为 0–59。");
        }

        const now = new Date();
        const target = new Date(now);
        target.setHours(hours, minutes, 0, 0);

        if (target <= now) {
            target.setDate(target.getDate() + 1);
        }

        return {
            type: 'daily',
            timestamp: target.getTime(),
            repeat: true,
            timing: trimmed,
            repeatHours: hours,
            repeatMinutes: minutes
        };
    }

    // 固定时间：如 "14:30" 或 "14：30"
    const fixedMatch = trimmed.match(/^(\d{1,2})[:：](\d{1,2})$/);
    if (fixedMatch) {
        const hours = parseInt(fixedMatch[1], 10);
        const minutes = parseInt(fixedMatch[2], 10);

        if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
            throw new Error("时辰有误：小时应为 0–23，分钟应为 0–59。");
        }

        const now = new Date();
        const target = new Date(now);
        target.setHours(hours, minutes, 0, 0);

        if (target <= now) {
            target.setDate(target.getDate() + 1);
        }

        return {
            type: 'fixed',
            timestamp: target.getTime(),
            repeat: false,
            timing: trimmed
        };
    }

    throw new Error("凡人，时间格式不识。支持：14:30、每天14:30、5分钟后");
}

class ArchangelGabriel {
    static __instance = null;
    taskMap = new Map();
    timer = null;
    ext = null;

    constructor(ext) {
        if (ArchangelGabriel.__instance) {
            throw new Error("天上地下，唯有一位加百列。");
        }
        this.ext = ext;
        this.load();
        ArchangelGabriel.__instance = this;
    }

    static getInstance(ext = null) {
        if (!ArchangelGabriel.__instance) {
            new ArchangelGabriel(ext);
        }
        return ArchangelGabriel.__instance;
    }

    getUUID() {
        return 'G' + Math.random().toString(36).substr(2, 8).toUpperCase();
    }

    // 生成艾特用户的CQ码（从战国提醒中复制的逻辑）
    generateAtCQ(userId) {
        // userId格式可能是 "qq:123456" 或纯数字，提取数字部分
        const qqNumber = userId.includes(':') ? userId.split(':')[1] : userId;
        return `[CQ:at,qq=${qqNumber}] `;
    }

    save() {
        const data = {};
        for (const [id, task] of this.taskMap.entries()) {
            if (task.fun === deliverMessage) {
                data[id] = {
                    id: task.id,
                    timing: task.timing,
                    task_sec: task.task_sec,
                    creator: task.creator,
                    isGroup: task.isGroup,
                    group: task.group,
                    paused: task.paused,
                    repeat: task.repeat,
                    type: task.type,
                    repeatHours: task.repeatHours,
                    repeatMinutes: task.repeatMinutes,
                    arg: task.arg
                };
            }
        }
        this.ext.storageSet("gabriel_reminders", JSON.stringify(data));
    }

    load() {
        try {
            const saved = this.ext.storageGet("gabriel_reminders") || "{}";
            const data = JSON.parse(saved);
            for (const id in data) {
                const task = data[id];
                task.fun = deliverMessage;
                task.executed = false;
                task.paused = task.paused || false;
                task.repeat = task.repeat || false;
                task.type = task.type || 'fixed';
                this.taskMap.set(id, task);
            }
        } catch (e) {
            console.error("加百列翻阅圣约之书时略有迟滞……", e);
        }
    }

    addTask(ctx, msg, timeStr, messageText) {
        const timeInfo = parseTimeInfo(timeStr);
        const isPrivate = (msg.messageType === "private");

        const task = {
            id: this.getUUID(),
            fun: deliverMessage,
            timing: timeInfo.timing,
            task_sec: timeInfo.timestamp,
            executed: false,
            paused: false,
            creator: ctx.player.userId,
            isGroup: !isPrivate,
            group: isPrivate ? null : msg.groupId,
            repeat: timeInfo.repeat,
            type: timeInfo.type,
            repeatHours: timeInfo.repeatHours || null,
            repeatMinutes: timeInfo.repeatMinutes || null,
            arg: [
                ctx.endPoint.userId,
                msg.guildId || "",
                msg.groupId || "",
                ctx.player.userId,
                isPrivate,
                messageText
            ]
        };
        this.taskMap.set(task.id, task);
        this.save();
        this.startTimer();
        return task;
    }

    startTimer() {
        if (this.timer) return;
        this.timer = setInterval(() => {
            this.checkTasks();
        }, 5000);
    }

    checkTasks() {
        const now = Date.now();
        for (const [id, task] of this.taskMap.entries()) {
            if (!task.paused && !task.executed && task.task_sec <= now) {
                try {
                    task.fun(...task.arg, this.generateAtCQ);
                } catch (e) {
                    console.error("加百列传递讯息时遭遇干扰……", e);
                }

                task.executed = true;

                // 如果是重复提醒，重新计算下次执行时间
                if (task.repeat) {
                    const nextDate = new Date();
                    nextDate.setDate(nextDate.getDate() + 1);
                    nextDate.setHours(task.repeatHours, task.repeatMinutes, 0, 0);
                    task.task_sec = nextDate.getTime();
                    task.executed = false;
                } else {
                    this.taskMap.delete(id);
                }

                this.save();
            }
        }
        if (this.taskMap.size === 0) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }

    listTasks(ctx) {
        let text = "📜 加百列的圣约之书（仅显示你有权查看的条目）：\n";
        let hasAny = false;
        for (const task of this.taskMap.values()) {
            if (
                ctx.privilegeLevel === 100 ||
                task.creator === ctx.player.userId ||
                (task.isGroup && task.group === ctx.group.groupId && ctx.privilegeLevel >= 40)
            ) {
                const d = new Date(task.task_sec);
                const timeStr = `${d.getMonth()+1}月${d.getDate()}日 ${d.getHours()}:${d.getMinutes().toString().padStart(2,'0')}`;
                const status = task.paused ? '⏸️ ' : '';
                const repeat = task.repeat ? ' 🔄' : '';
                text += `• [${task.id}] ${status}${timeStr} → ${task.arg[5]}${repeat}\n`;
                hasAny = true;
            }
        }
        return hasAny ? text : "🕊️ 圣约之书暂无与你相关的记载。";
    }

    deleteTask(ctx, id) {
        if (!this.taskMap.has(id)) {
            return "❌ 此编号不在圣约之书中。";
        }
        const task = this.taskMap.get(id);
        if (
            ctx.privilegeLevel === 100 ||
            task.creator === ctx.player.userId ||
            (task.isGroup && task.group === ctx.group.groupId && ctx.privilegeLevel >= 40)
        ) {
            this.taskMap.delete(id);
            this.save();
            return "✅ 已从圣约之书中抹去此条。";
        } else {
            return "❌ 非缔约者、群管理者或至高者，不得擅改圣约。";
        }
    }

    modifyTask(ctx, id, newTimeStr, newMessage) {
        if (!this.taskMap.has(id)) {
            return "❌ 此编号不在圣约之书中。";
        }
        const task = this.taskMap.get(id);
        if (
            ctx.privilegeLevel === 100 ||
            task.creator === ctx.player.userId ||
            (task.isGroup && task.group === ctx.group.groupId && ctx.privilegeLevel >= 40)
        ) {
            try {
                const timeInfo = parseTimeInfo(newTimeStr);
                task.timing = timeInfo.timing;
                task.task_sec = timeInfo.timestamp;
                task.repeat = timeInfo.repeat;
                task.type = timeInfo.type;
                task.repeatHours = timeInfo.repeatHours || null;
                task.repeatMinutes = timeInfo.repeatMinutes || null;
                task.executed = false;
                task.arg[5] = newMessage;
                this.save();
                return "✅ 已修改圣约。";
            } catch (e) {
                return `❌ 修改失败：${e.message}`;
            }
        } else {
            return "❌ 非缔约者、群管理者或至高者，不得擅改圣约。";
        }
    }

    pauseTask(ctx, id) {
        if (!this.taskMap.has(id)) {
            return "❌ 此编号不在圣约之书中。";
        }
        const task = this.taskMap.get(id);
        if (
            ctx.privilegeLevel === 100 ||
            task.creator === ctx.player.userId ||
            (task.isGroup && task.group === ctx.group.groupId && ctx.privilegeLevel >= 40)
        ) {
            task.paused = true;
            this.save();
            return "⏸️ 已暂停此条提醒。";
        } else {
            return "❌ 非缔约者、群管理者或至高者，不得擅改圣约。";
        }
    }

    resumeTask(ctx, id) {
        if (!this.taskMap.has(id)) {
            return "❌ 此编号不在圣约之书中。";
        }
        const task = this.taskMap.get(id);
        if (
            ctx.privilegeLevel === 100 ||
            task.creator === ctx.player.userId ||
            (task.isGroup && task.group === ctx.group.groupId && ctx.privilegeLevel >= 40)
        ) {
            task.paused = false;
            this.save();
            return "▶️ 已恢复此条提醒。";
        } else {
            return "❌ 非缔约者、群管理者或至高者，不得擅改圣约。";
        }
    }
}

function deliverMessage(epId, guildId, groupId, userId, isPrivate, text, generateAtCQ) {
    const eps = seal.getEndPoints();
    for (let ep of eps) {
        if (ep.userId === epId) {
            const msg = seal.newMessage();

            // 构建最终消息：如果是群消息，添加艾特
            let finalMessage = text;
            if (!isPrivate && groupId && generateAtCQ) {
                const atCQ = generateAtCQ(userId);
                finalMessage = `${atCQ}${text}`;
            }

            if (isPrivate) {
                msg.messageType = "private";
                msg.sender.userId = userId;
            } else {
                msg.messageType = "group";
                msg.groupId = groupId;
                msg.guildId = guildId || "";
                msg.sender.userId = userId;
            }

            const ctx = seal.createTempCtx(ep, msg);
            seal.replyToSender(ctx, msg, finalMessage);
            return;
        }
    }
}

// ========================
// 🔔 注册插件
// ========================
if (!seal.ext.find('大天使加百列')) {
    const ext = seal.ext.new('大天使加百列', 'Archangel Gabriel', '1.2.0');

    ext.onNotCommand = (ctx, msg) => {
        const rawMsg = msg.message.trim();

        // 匹配 "提醒我" 关键词后跟时间和内容（支持各种时间格式）
        const notifyMatch = rawMsg.match(/^提醒我\s+(.+?)\s+(.+)$/s);

        if (notifyMatch) {
            const timeStr = notifyMatch[1];
            const messageText = notifyMatch[2].trim();

            // 检查是否是时间格式（排除命令）
            if (/^(\d{1,2}[:：]\d{1,2}|每天\s*\d{1,2}[:：]\d{1,2}|\d+(?:分钟|小时|天)后)$/.test(timeStr.trim())) {
                if (!messageText) {
                    seal.replyToSender(ctx, msg, "❌ 请赐下你要铭记的言语，例如：提醒我 14:30 记得吃药");
                    return seal.ext.newCmdExecuteResult(true);
                }

                const gabriel = ArchangelGabriel.getInstance(ext);
                try {
                    const timeInfo = parseTimeInfo(timeStr);
                    gabriel.addTask(ctx, msg, timeStr, messageText);
                    const execTime = new Date(timeInfo.timestamp);
                    const timeDisplay = `${execTime.getMonth()+1}月${execTime.getDate()}日 ${execTime.getHours()}:${execTime.getMinutes().toString().padStart(2,'0')}`;
                    const repeatText = timeInfo.repeat ? '（每日重复）' : '';

                    const isPrivate = (msg.messageType === "private");
                    const atInfo = isPrivate ? "" : "（提醒时会艾特君）";

                    seal.replyToSender(ctx, msg, `🕊️ 吾已将「${messageText}」载入圣约之书，将于 ${timeDisplay} 为你鸣钟${atInfo}${repeatText}。`);
                } catch (e) {
                    seal.replyToSender(ctx, msg, `⚠️ 加百列无法记录此谕：${e.message}`);
                }

                return seal.ext.newCmdExecuteResult(true);
            }
        }

        // 匹配 "提醒我" 后跟命令
        const cmdMatch = rawMsg.match(/^提醒我\s+(\S+)(?:\s+(.+))?$/);

        if (cmdMatch) {
            const cmd = cmdMatch[1];
            const arg = cmdMatch[2];
            const gabriel = ArchangelGabriel.getInstance(ext);

            switch (cmd) {
                case 'help':
                case '帮助':
                    const helpText = `
🕊️【大天使加百列 · 圣谕系统】
吾乃加百列，奉命为你铭记此刻——无需引号，直述心声。

📜 基础用法：
提醒我 14:30 记得吃药
提醒我 每天14:30 每日吃药
提醒我 5分钟后 喝水
提醒我 2小时后 开会

📖 提醒管理：
提醒我 list       → 查阅圣约之书
提醒我 del <ID>   → 抹去某条记载
提醒我 改 <ID> <新时间> <新内容>  → 修改提醒
提醒我 暂停 <ID>  → 暂停提醒
提醒我 恢复 <ID>  → 恢复提醒

✨ 说明：
- 时间格式支持：HH:mm、HH：mm、每天HH:mm、X分钟后、X小时后、X天后
- 每日重复提醒会自动续期到明天同一时间
- 暂停的提醒不会触发，但保留在圣约之书中
- 群聊提醒会自动艾特设置者
`;
                    seal.replyToSender(ctx, msg, helpText);
                    return seal.ext.newCmdExecuteResult(true);

                case 'list':
                case '列表':
                    seal.replyToSender(ctx, msg, gabriel.listTasks(ctx));
                    return seal.ext.newCmdExecuteResult(true);

                case 'del':
                case 'delete':
                case '删除':
                    if (!arg) {
                        seal.replyToSender(ctx, msg, "❌ 请赐下要抹去的圣约编号，使用 提醒我 list 查阅。");
                    } else {
                        seal.replyToSender(ctx, msg, gabriel.deleteTask(ctx, arg));
                    }
                    return seal.ext.newCmdExecuteResult(true);

                case '改':
                case 'mod':
                case 'modify':
                    if (!arg) {
                        seal.replyToSender(ctx, msg, "❌ 格式：提醒我 改 <ID> <新时间> <新内容>");
                    } else {
                        const modMatch = arg.match(/^(\S+)\s+(.+?)\s+(.+)$/);
                        if (modMatch) {
                            const id = modMatch[1];
                            const newTime = modMatch[2];
                            const newMsg = modMatch[3];
                            seal.replyToSender(ctx, msg, gabriel.modifyTask(ctx, id, newTime, newMsg));
                        } else {
                            seal.replyToSender(ctx, msg, "❌ 格式：提醒我 改 <ID> <新时间> <新内容>");
                        }
                    }
                    return seal.ext.newCmdExecuteResult(true);

                case '暂停':
                case 'pause':
                    if (!arg) {
                        seal.replyToSender(ctx, msg, "❌ 请赐下要暂停的圣约编号。");
                    } else {
                        seal.replyToSender(ctx, msg, gabriel.pauseTask(ctx, arg));
                    }
                    return seal.ext.newCmdExecuteResult(true);

                case '恢复':
                case 'resume':
                    if (!arg) {
                        seal.replyToSender(ctx, msg, "❌ 请赐下要恢复的圣约编号。");
                    } else {
                        seal.replyToSender(ctx, msg, gabriel.resumeTask(ctx, arg));
                    }
                    return seal.ext.newCmdExecuteResult(true);
            }
        }

        return seal.ext.newCmdExecuteResult(false);
    };

    seal.ext.register(ext);
    ArchangelGabriel.getInstance(ext);
}
