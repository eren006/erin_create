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
    const line = "━━━━━━━━━━━━━━";
    const subLine = "┈┈┈┈┈┈┈┈┈┈┈┈";
    let message = targetQQ ? `[CQ:at,qq=${targetQQ}]\n` : "";
    message += `📱 【语音通话邀约】\n${line}\n💭 留言内容：\n`;
    if (title) message += `「 ${title} 」\n`;
    message += `“ 嗨~ 我是 ${sendname}！\n`;
    if (isMulti) {
        message += `我想在 ${day} 的 ${time} 找你打个电话`;
        if (otherNames.length) {
            const peers = otherNames.length === 1 ? otherNames[0] : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
            message += `，${peers}也会加入。`;
        }
    } else {
        message += `我想在 ${day} 的 ${time} 找你单独聊聊天～`;
    }
    message += `\n电话已准备好，等你接通哦！ ”\n${subLine}\n💡 提示：通话已自动建立并生成通讯频段！\n\n⚙️ 进群后请输入：.ext all on\n${line}\n✨ 祝你们通话愉快！`;
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
    const line = "━━━━━━━━━━━━━━";
    const subLine = "┈┈┈┈┈┈┈┈┈┈┈┈";
    let message = targetQQ ? `[CQ:at,qq=${targetQQ}]\n` : "";
    message += `💌 【私密约会邀请】\n${line}\n💭 留言内容：\n“ 嗨~ 我是 ${sendname}！\n`;
    if (isMulti && otherNames.length) {
        const peers = otherNames.length === 1 ? otherNames[0] : `${otherNames.slice(0, -1).join("、")}和${otherNames.slice(-1)}`;
        message += `我想邀请你和 ${peers}，\n`;
    } else {
        message += `我想单独邀请你，\n`;
    }
    message += `在 ${day} 的 ${time}\n前往【 ${place} 】聚聚。\n期待你的到来哦~ ”\n${subLine}\n💡 提示：约会已自动确认并生成私人空间！\n\n📍 到达地点后请留意环境描述\n${line}\n✨ 祝你们约会愉快！`;
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
ext.cmdMap["拒绝加入"] = cmd_reject_join;这个流程有没有bug