// ==UserScript==
// @name         大天使加百列
// @author       加百列 & Qwen
// @version      1.2.0
// @description  吾乃加百列，奉命为你铭记此刻——无需引号，直述心声。🕊️
// @license      MIT
// ==/UserScript==

function parseTimeToFutureTimestamp(timeStr) {
    const match = timeStr.trim().match(/^(\d{1,2})[:：](\d{1,2})$/);
    if (!match) {
        throw new Error("凡人，时间需以 HH:mm 或 HH：mm 书写，如 9:05 或 14：30。");
    }
    let [_, hoursStr, minutesStr] = match;
    let hours = parseInt(hoursStr, 10);
    let minutes = parseInt(minutesStr, 10);

    if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) {
        throw new Error("时辰有误：小时应为 0–23，分钟应为 0–59。");
    }

    const now = new Date();
    const targetToday = new Date(now);
    targetToday.setHours(hours, minutes, 0, 0);

    if (targetToday <= now) {
        targetToday.setDate(targetToday.getDate() + 1);
    }

    return targetToday.getTime();
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
                this.taskMap.set(id, task);
            }
        } catch (e) {
            console.error("加百列翻阅圣约之书时略有迟滞……", e);
        }
    }

    addTask(ctx, msg, timeStr, messageText) {
        const taskSec = parseTimeToFutureTimestamp(timeStr);
        const isPrivate = (msg.messageType === "private");

        const task = {
            id: this.getUUID(),
            fun: deliverMessage,
            timing: timeStr,
            task_sec: taskSec,
            executed: false,
            creator: ctx.player.userId,
            isGroup: !isPrivate,
            group: isPrivate ? null : msg.groupId,
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
            if (!task.executed && task.task_sec <= now) {
                try {
                    task.fun(...task.arg, this.generateAtCQ);
                } catch (e) {
                    console.error("加百列传递讯息时遭遇干扰……", e);
                } finally {
                    task.executed = true;
                    this.taskMap.delete(id);
                    this.save();
                }
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
                text += `• [${task.id}] ${timeStr} → ${task.arg[5]}\n`;
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

        // 匹配 "提醒我" 关键词后跟时间和内容
        const notifyMatch = rawMsg.match(/^提醒我\s+(\d{1,2}[:：]\d{1,2})\s+(.+)$/s);

        if (notifyMatch) {
            const timeStr = notifyMatch[1];
            const messageText = notifyMatch[2].trim();

            if (!messageText) {
                seal.replyToSender(ctx, msg, "❌ 请赐下你要铭记的言语，例如：提醒我 14:30 记得吃药");
                return seal.ext.newCmdExecuteResult(true);
            }

            const gabriel = ArchangelGabriel.getInstance(ext);
            try {
                gabriel.addTask(ctx, msg, timeStr, messageText);
                const execTime = new Date(parseTimeToFutureTimestamp(timeStr));
                const timeDisplay = `${execTime.getMonth()+1}月${execTime.getDate()}日 ${execTime.getHours()}:${execTime.getMinutes().toString().padStart(2,'0')}`;

                const isPrivate = (msg.messageType === "private");
                const atInfo = isPrivate ? "" : "（提醒时会艾特君）";

                seal.replyToSender(ctx, msg, `🕊️ 吾已将「${messageText}」载入圣约之书，将于 ${timeDisplay} 为你鸣钟${atInfo}。`);
            } catch (e) {
                seal.replyToSender(ctx, msg, `⚠️ 加百列无法记录此谕：${e.message}`);
            }

            return seal.ext.newCmdExecuteResult(true);
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

📜 用法：
提醒我 14:30 记得吃药
提醒我 2:00 夜巡开始啦～

📖 其他指令：
提醒我 list     → 查阅圣约之书
提醒我 del <ID> → 抹去某条记载

✨ 说明：
- 时间后所有文字将视为提醒内容（支持空格）
- 时间格式：HH:mm 或 HH：mm（如 9:05、14:30、14：30）
- 若时辰已过（如 20:00 设 2:00），则延至明日
- 每条提醒仅生效一次，钟响即焚
- 在群聊中提醒时会自动艾特设置者
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
            }
        }

        return seal.ext.newCmdExecuteResult(false);
    };

    seal.ext.register(ext);
    ArchangelGabriel.getInstance(ext);
}
