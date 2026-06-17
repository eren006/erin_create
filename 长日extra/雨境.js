// ==UserScript==
// @name         雨境
// @author       长日将尽
// @version      1.0.0
// @description  雨境addon：雨点/HP/PVP执念之争系统
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

/**
 * 数据存储（均存于主插件 changri 下，key 前缀 yj_）
 *   yj_players       { [platform]: { [uid]: PlayerData } }
 *   yj_pvpSessions   { [pvpId]: Session }
 *   yj_pvpQueue      { ["platform:uid"]: [pvpId, ...] }   // 防守方排队
 *   yj_pvpOpen       boolean
 *   yj_mgmtGroup     string  纯数字群号
 *
 * PlayerData:
 *   raindrops       number
 *   hp              number  (0~100)
 *   isAlive         boolean
 *   isRevived       boolean  续命状态（禁PVP，大群公开）
 *   timeLocked      boolean  时间线锁定（对决进行中）
 *   pvpToday        number   今日已发起/参与PVP次数
 *   pvpPairsToday   string[] 今日已对决的对手uid列表
 *
 * Session.status 状态机：
 *   pending_accept      → 等待防守方应战
 *   pending_alloc_admin → 双方已就绪，等管理录入分配
 *   ready_to_battle     → 分配已录入，等管理执行
 *   completed / cancelled
 */

let ext = seal.ext.find('yuanjing');
if (!ext) {
    ext = seal.ext.new('yuanjing', '长日将尽', '1.0.0');
    seal.ext.register(ext);
}

// ========================
// 工具：主插件存储读写
// ========================
function getMainExt() {
    const main = seal.ext.find('changri');
    if (!main) console.error('[雨境] 未找到主插件 changri，请确认已加载');
    return main;
}

function getData(key, defaultVal) {
    const main = getMainExt();
    if (!main) return defaultVal;
    const raw = main.storageGet('yj_' + key);
    if (!raw) return defaultVal;
    try { return JSON.parse(raw); } catch (e) { return defaultVal; }
}

function setData(key, value) {
    const main = getMainExt();
    if (main) main.storageSet('yj_' + key, JSON.stringify(value));
}

// ========================
// 玩家数据
// ========================
function getAllPlayers() {
    return getData('players', {});
}

function getPlayer(platform, uid) {
    const all = getAllPlayers();
    if (!all[platform]) all[platform] = {};
    if (!all[platform][uid]) {
        all[platform][uid] = {
            raindrops: 0, hp: 100,
            isAlive: true, isRevived: false, timeLocked: false,
            pvpToday: 0, pvpPairsToday: []
        };
        setData('players', all);
    }
    return all[platform][uid];
}

function savePlayer(platform, uid, data) {
    const all = getAllPlayers();
    if (!all[platform]) all[platform] = {};
    all[platform][uid] = data;
    setData('players', all);
}

// ========================
// PVP 会话
// ========================
function getSessions() { return getData('pvpSessions', {}); }

function getSession(pvpId) { return getSessions()[pvpId] || null; }

function saveSession(pvpId, data) {
    const s = getSessions();
    s[pvpId] = data;
    setData('pvpSessions', s);
}

// ========================
// PVP 队列（针对防守方排队）
// ========================
function getQueue() { return getData('pvpQueue', {}); }

function enqueueChallenge(defenderKey, pvpId) {
    const q = getQueue();
    if (!q[defenderKey]) q[defenderKey] = [];
    q[defenderKey].push(pvpId);
    setData('pvpQueue', q);
}

function peekQueue(defenderKey) {
    const q = getQueue();
    return (q[defenderKey] || [])[0] || null;
}

function dequeueChallenge(defenderKey, pvpId) {
    const q = getQueue();
    if (!q[defenderKey]) return;
    q[defenderKey] = q[defenderKey].filter(id => id !== pvpId);
    setData('pvpQueue', q);
}

// ========================
// 角色名 / 个人群 查询（读主插件 a_private_group）
// a_private_group[platform][uid] = [roleName, gid]
// ========================
function getRoleName(platform, uid) {
    const main = getMainExt();
    if (!main) return uid;
    try {
        const apg = JSON.parse(main.storageGet('a_private_group') || '{}');
        return apg[platform]?.[uid]?.[0] || uid;
    } catch (e) { return uid; }
}

function getPersonalGid(platform, uid) {
    const main = getMainExt();
    if (!main) return null;
    try {
        const apg = JSON.parse(main.storageGet('a_private_group') || '{}');
        return apg[platform]?.[uid]?.[1] || null;
    } catch (e) { return null; }
}

function getUidByRole(platform, roleName) {
    const main = getMainExt();
    if (!main) return null;
    try {
        const apg = JSON.parse(main.storageGet('a_private_group') || '{}');
        const roles = apg[platform] || {};
        return Object.entries(roles).find(([_, v]) => v[0] === roleName)?.[0] || null;
    } catch (e) { return null; }
}

// ========================
// 发消息工具
// ========================
function sendToGroup(endPoint, platform, gid, text) {
    try {
        const m = seal.newMessage();
        m.messageType = 'group';
        m.groupId = `${platform}-Group:${gid}`;
        seal.replyToSender(seal.createTempCtx(endPoint, m), m, text);
    } catch (e) { console.error('[雨境] sendToGroup:', e); }
}

// 发到玩家个人群
function notifyPlayer(endPoint, platform, uid, text) {
    const gid = getPersonalGid(platform, uid);
    if (gid) sendToGroup(endPoint, platform, gid, text);
}

// 发到大群（adminAnnounceGroupId）
function broadcastMain(endPoint, platform, text) {
    const main = getMainExt();
    if (!main) return;
    const gid = JSON.parse(main.storageGet('adminAnnounceGroupId') || 'null');
    if (gid) sendToGroup(endPoint, platform, String(gid), text);
}

// 发到管理群
function sendToMgmt(endPoint, platform, text) {
    const gid = getData('mgmtGroup', '');
    if (gid) sendToGroup(endPoint, platform, String(gid), text);
}

// ========================
// 权限
// ========================
function isAdmin(ctx, msg) {
    if (ctx.privilegeLevel >= 100) return true;
    const main = getMainExt();
    if (!main) return false;
    try {
        const list = JSON.parse(main.storageGet('a_adminList') || '{}');
        const platform = msg.platform;
        const uid = msg.sender.userId.replace(`${platform}:`, '');
        return !!(list[platform] && list[platform].includes(uid));
    } catch (e) { return false; }
}

// ========================
// 游戏天数（读主插件 global_days，格式 "D1"）
// ========================
function getGameDay() {
    const main = getMainExt();
    if (!main) return 1;
    const raw = main.storageGet('global_days') || 'D1';
    const n = parseInt(raw.replace(/\D/g, ''));
    return isNaN(n) ? 1 : n;
}

// ========================
// PVP 开关
// ========================
function isPvpOpen() { return getData('pvpOpen', false); }

// ========================
// 北京时间 & 时间槽锁定
// ========================
function getBeijingTimeSlot() {
    const bj = new Date(Date.now() + 8 * 60 * 60 * 1000);
    const h = String(bj.getUTCHours()).padStart(2, '0');
    const m = String(bj.getUTCMinutes()).padStart(2, '0');
    return `${h}:${m}-23:59`;
}

function lockPlayerSlot(platform, uid, dayStr, slot) {
    const api = globalThis.__changriApi;
    if (!api || !slot) return;
    let slots;
    try { slots = JSON.parse(api.kvGetRaw('a_lockedSlots') || '{}'); } catch (e) { slots = {}; }
    const key = `${platform}:${uid}`;
    if (!slots[key]) slots[key] = {};
    if (!slots[key][dayStr]) slots[key][dayStr] = [];
    if (!slots[key][dayStr].includes(slot)) {
        slots[key][dayStr].push(slot);
        api.kvSetRaw('a_lockedSlots', JSON.stringify(slots));
    }
}

function unlockPlayerSlot(platform, uid, dayStr, slot) {
    const api = globalThis.__changriApi;
    if (!api || !dayStr || !slot) return;
    let slots;
    try { slots = JSON.parse(api.kvGetRaw('a_lockedSlots') || '{}'); } catch (e) { return; }
    const key = `${platform}:${uid}`;
    if (!slots[key]?.[dayStr]) return;
    const idx = slots[key][dayStr].indexOf(slot);
    if (idx === -1) return;
    slots[key][dayStr].splice(idx, 1);
    if (slots[key][dayStr].length === 0) delete slots[key][dayStr];
    if (Object.keys(slots[key]).length === 0) delete slots[key];
    api.kvSetRaw('a_lockedSlots', JSON.stringify(slots));
}

// ========================
// 工具函数
// ========================
function rd(max) {
    if (max <= 0) return 0;
    return Math.floor(Math.random() * max) + 1;
}

let _pvpCounter = 0;
function genPvpId() {
    _pvpCounter++;
    return `pvp_${Date.now()}_${_pvpCounter}`;
}

// 检查某玩家是否已有进行中（非 completed/cancelled）的 PVP
function hasActivePvp(platform, uid) {
    const fullId = `${platform}:${uid}`;
    const sessions = getSessions();
    return Object.values(sessions).some(s =>
        !['completed', 'cancelled'].includes(s.status) &&
        (s.initiator === fullId || s.defender === fullId)
    );
}

// ========================
// 死亡处理
// ========================
function handleDeath(endPoint, platform, uid, reason) {
    const p = getPlayer(platform, uid);
    if (!p.isAlive) return; // 已处理过，不重复
    p.isAlive = false;
    p.hp = 0;
    p.timeLocked = false;
    p.isRevived = false;
    savePlayer(platform, uid, p);

    const name = getRoleName(platform, uid);
    broadcastMain(endPoint, platform, '【雨境通报】一个灵魂已在雨中消散。');
    sendToMgmt(endPoint, platform,
        `【死亡通报】${name} 已消散\n原因：${reason}\n剩余雨点：${p.raindrops}｜HP：${p.hp}`);
    notifyPlayer(endPoint, platform, uid, `【雨境】你已消散于雨境之中。\n${reason}`);
}

// ========================
// PVP 雨点结算
// ========================
function settlePvp(endPoint, platform, session, result) {
    // result: 'initiator_win' | 'defender_win' | 'draw'
    const [iPf, iUid] = session.initiator.split(':');
    const [dPf, dUid] = session.defender.split(':');
    const iP = getPlayer(iPf, iUid);
    const dP = getPlayer(dPf, dUid);

    iP.timeLocked = false;
    dP.timeLocked = false;
    unlockPlayerSlot(iPf, iUid, session.iLockDay, session.iLockSlot);
    unlockPlayerSlot(dPf, dUid, session.dLockDay, session.dLockSlot);

    if (result === 'initiator_win') {
        const take = session.defenderRaindrops;
        iP.raindrops += take;
        dP.raindrops = Math.max(0, dP.raindrops - take);
    } else if (result === 'defender_win') {
        const take = session.initiatorRaindrops;
        dP.raindrops += take;
        iP.raindrops = Math.max(0, iP.raindrops - take);
    }
    // draw: 各自保留

    savePlayer(iPf, iUid, iP);
    savePlayer(dPf, dUid, dP);
    session.status = 'completed';
    saveSession(session.pvpId, session);

    // 雨点归零→死亡
    if (result === 'initiator_win' && dP.raindrops <= 0)
        handleDeath(endPoint, dPf, dUid, '执念之争落败·雨点归零');
    if (result === 'defender_win' && iP.raindrops <= 0)
        handleDeath(endPoint, iPf, iUid, '执念之争落败·雨点归零');

    // 提醒排队（先出队已结算的条目，再看是否还有下一条）
    [session.initiator, session.defender].forEach(key => {
        dequeueChallenge(key, session.pvpId);
        const next = peekQueue(key);
        if (next) {
            const [pf, u] = key.split(':');
            sendToMgmt(endPoint, platform,
                `【队列提醒】${getRoleName(pf, u)} 有等待中的执念之争：${next}`);
        }
    });
}

// ========================
// 超时检查（手动触发）
// ========================
function checkTimeouts(endPoint, platform) {
    const now = Date.now();
    const sessions = getSessions();
    for (const [pvpId, s] of Object.entries(sessions)) {
        if (s.status !== 'pending_accept') continue;
        if (now - s.createdAt < 60 * 60 * 1000) continue; // < 60min

        const [iPf, iUid] = s.initiator.split(':');
        const [dPf, dUid] = s.defender.split(':');
        const iP = getPlayer(iPf, iUid);
        const dP = getPlayer(dPf, dUid);
        const penalty = s.initiatorRaindrops;

        dP.raindrops = Math.max(0, dP.raindrops - penalty);
        iP.timeLocked = false;
        dP.timeLocked = false;
        unlockPlayerSlot(iPf, iUid, s.iLockDay, s.iLockSlot);
        savePlayer(iPf, iUid, iP);
        savePlayer(dPf, dUid, dP);
        s.status = 'completed';
        saveSession(pvpId, s);

        sendToMgmt(endPoint, platform,
            `【PVP超时结算】${getRoleName(dPf, dUid)} 超时未应战\n` +
            `扣除 ${penalty} 颗雨点（剩余：${dP.raindrops}）\n` +
            `挑战方：${getRoleName(iPf, iUid)}`);
        notifyPlayer(endPoint, dPf, dUid,
            `【雨境】你超时未应战，扣除 ${penalty} 颗雨点。剩余：${dP.raindrops} 颗。`);

        if (dP.raindrops <= 0) handleDeath(endPoint, dPf, dUid, '超时未应战·雨点归零');
    }
}

// ========================
// 工具：校验携带雨点
// ========================
function checkBetRaindrops(player, betRain) {
    if (betRain < 1) return '至少携带1颗雨点。';
    if (betRain > player.raindrops) return `雨点不足（持有：${player.raindrops} 颗）。`;
    if (player.raindrops > 1 && betRain >= player.raindrops)
        return `须至少保留1颗，最多可携带 ${player.raindrops - 1} 颗。`;
    return null; // 合法
}

// ========================================================
// 指令注册
// ========================================================

// ——————————————————————————
// 1. 执念之争（玩家发起PVP）
// ——————————————————————————
const cmdChallenge = seal.ext.newCmdItemInfo();
cmdChallenge.name = '执念之争';
cmdChallenge.help = '向他人发起执念之争：.执念之争 角色名 N颗';
cmdChallenge.solve = (ctx, msg, cmdArgs) => {
    const reply = t => (seal.replyToSender(ctx, msg, `【雨境】${t}`), seal.ext.newCmdExecuteResult(true));

    if (!isPvpOpen()) return reply('执念之争尚未开启。');

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, '');
    const me = getPlayer(platform, uid);

    if (!me.isAlive || me.hp <= 0) return reply('你无法发起执念之争（已消散或HP归零）。');
    if (me.isRevived)   return reply('续命期间无法参与执念之争。');
    if (me.timeLocked)  return reply('你的时间线已锁定，请先完成进行中的执念之争。');

    const day = getGameDay();
    if (day >= 2 && day <= 3 && me.pvpToday >= 2)
        return reply(`今日发起次数已达上限（Day2-3每人限2次）。`);

    const targetName = cmdArgs.getArgN(1);
    const rainArg    = cmdArgs.getArgN(2);
    if (!targetName || !rainArg) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const numM = rainArg.match(/^(\d+)颗?$/);
    if (!numM) return reply('格式错误。示例：.执念之争 小明 3颗');
    const betRain = parseInt(numM[1]);

    const err = checkBetRaindrops(me, betRain);
    if (err) return reply(err);

    const defUid = getUidByRole(platform, targetName);
    if (!defUid)          return reply(`未找到角色「${targetName}」。`);
    if (defUid === uid)   return reply('不能向自己发起执念之争。');

    const defP = getPlayer(platform, defUid);
    if (!defP.isAlive || defP.hp <= 0) return reply('对方已消散，无法发起。');
    if (defP.isRevived) return reply(`${targetName} 处于续命状态，无法发起执念之争。`);

    if (day >= 2 && day <= 3 && (me.pvpPairsToday || []).includes(defUid))
        return reply('今日已与此人对决过（Day2-3限同一对手每天1次）。');

    const pvpId  = genPvpId();
    const iKey   = `${platform}:${uid}`;
    const dKey   = `${platform}:${defUid}`;

    const session = {
        pvpId, status: 'pending_accept',
        initiator: iKey, defender: dKey,
        initiatorRaindrops: betRain, defenderRaindrops: 0,
        initiatorAlloc: null, defenderAlloc: null,
        initiatorHP: me.hp, defenderHP: defP.hp,
        createdAt: Date.now(), defenderAcceptedAt: null
    };
    saveSession(pvpId, session);

    const isDefBusy = hasActivePvp(platform, defUid);
    if (isDefBusy) {
        // 排队，暂不锁定发起方，但计数照算（防止绕过每日上限）
        enqueueChallenge(dKey, pvpId);
        if (day >= 2 && day <= 3) {
            me.pvpToday = (me.pvpToday || 0) + 1;
            if (!me.pvpPairsToday) me.pvpPairsToday = [];
            me.pvpPairsToday.push(defUid);
            savePlayer(platform, uid, me);
        }
        seal.replyToSender(ctx, msg,
            `【雨境】已向 ${targetName} 发起执念之争（${pvpId}），对方正在对决中，已排入队列。`);
        sendToMgmt(ctx.endPoint, platform,
            `【PVP排队】${getRoleName(platform, uid)} → ${targetName}（${pvpId}）`);
    } else {
        // 立即生效，锁定发起方
        me.timeLocked = true;
        if (day >= 2 && day <= 3) {
            me.pvpToday = (me.pvpToday || 0) + 1;
            if (!me.pvpPairsToday) me.pvpPairsToday = [];
            me.pvpPairsToday.push(defUid);
        }
        savePlayer(platform, uid, me);

        const iSlot = getBeijingTimeSlot();
        session.iLockDay = `D${day}`;
        session.iLockSlot = iSlot;
        saveSession(pvpId, session);
        lockPlayerSlot(platform, uid, `D${day}`, iSlot);

        seal.replyToSender(ctx, msg,
            `【雨境】执念之争已发起。携带 ${betRain} 颗雨点，等待 ${targetName} 应战……\nID：${pvpId}`);
        notifyPlayer(ctx.endPoint, platform, defUid,
            `【雨境】${getRoleName(platform, uid)} 向你发起了执念之争，携带 ${betRain} 颗雨点。\n` +
            `回复「.应战 N颗」接受。60分钟内不回应则默认败北。\nID：${pvpId}`);
        sendToMgmt(ctx.endPoint, platform,
            `【PVP发起】${getRoleName(platform, uid)} → ${targetName}\n携带：${betRain} 颗｜ID：${pvpId}`);
    }

    broadcastMain(ctx.endPoint, platform, '【雨境】当前有一场执念之争正在进行。');
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['执念之争'] = cmdChallenge;


// ——————————————————————————
// 2. 应战（防守方接受）
// ——————————————————————————
const cmdAccept = seal.ext.newCmdItemInfo();
cmdAccept.name = '应战';
cmdAccept.help = '接受执念之争挑战：.应战 N颗';
cmdAccept.solve = (ctx, msg, cmdArgs) => {
    const reply = t => (seal.replyToSender(ctx, msg, `【雨境】${t}`), seal.ext.newCmdExecuteResult(true));

    const platform = msg.platform;
    const uid      = msg.sender.userId.replace(`${platform}:`, '');
    const fullId   = `${platform}:${uid}`;
    const me       = getPlayer(platform, uid);

    if (!me.isAlive || me.hp <= 0) return reply('你无法应战（已消散或HP归零）。');

    // 找到待接受的挑战
    const sessions = getSessions();
    const target = Object.values(sessions).find(
        s => s.defender === fullId && s.status === 'pending_accept'
    );
    if (!target) return reply('当前没有等待你应战的执念之争。');

    const rainArg = cmdArgs.getArgN(1);
    const numM    = rainArg ? rainArg.match(/^(\d+)颗?$/) : null;
    if (!numM) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }
    const betRain = parseInt(numM[1]);

    const err = checkBetRaindrops(me, betRain);
    if (err) return reply(err);

    const day = getGameDay();
    const [iPf, iUid] = target.initiator.split(':');

    if (day >= 2 && day <= 3 && (me.pvpToday || 0) >= 2)
        return reply('今日参与次数已达上限（Day2-3每人限2次）。');

    // 更新防守方计数 & 锁定
    if (day >= 2 && day <= 3) {
        me.pvpToday = (me.pvpToday || 0) + 1;
        if (!me.pvpPairsToday) me.pvpPairsToday = [];
        me.pvpPairsToday.push(iUid);
    }
    me.timeLocked = true;
    savePlayer(platform, uid, me);

    const acceptSlot = getBeijingTimeSlot();
    const acceptDay  = `D${day}`;
    target.dLockDay  = acceptDay;
    target.dLockSlot = acceptSlot;
    lockPlayerSlot(platform, uid, acceptDay, acceptSlot);

    // 锁定发起方（若是从排队里激活的可能还没锁）
    const iP = getPlayer(iPf, iUid);
    if (!iP.timeLocked) {
        if (day >= 2 && day <= 3) {
            iP.pvpToday = (iP.pvpToday || 0) + 1;
            if (!iP.pvpPairsToday) iP.pvpPairsToday = [];
            iP.pvpPairsToday.push(uid);
        }
        iP.timeLocked = true;
        savePlayer(iPf, iUid, iP);
        target.iLockDay  = acceptDay;
        target.iLockSlot = acceptSlot;
        lockPlayerSlot(iPf, iUid, acceptDay, acceptSlot);
    }

    target.defenderRaindrops = betRain;
    target.status            = 'pending_alloc_admin';
    target.defenderAcceptedAt = Date.now();
    saveSession(target.pvpId, target);

    seal.replyToSender(ctx, msg,
        `【雨境】已接受执念之争，携带 ${betRain} 颗雨点入局。双方时间线已锁定。\nID：${target.pvpId}`);
    notifyPlayer(ctx.endPoint, iPf, iUid,
        `【雨境】${getRoleName(platform, uid)} 已接受你的执念之争，携带 ${betRain} 颗雨点。时间线已锁定。`);
    sendToMgmt(ctx.endPoint, platform,
        `【PVP应战·等待分配】\nID：${target.pvpId}\n` +
        `${getRoleName(iPf, iUid)}（发起）携带 ${target.initiatorRaindrops} 颗\n` +
        `${getRoleName(platform, uid)}（防守）携带 ${betRain} 颗\n\n` +
        `双方提交分配方案后录入：\n.pvp分配 ${target.pvpId} 攻击X防御Y 攻击X防御Y`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['应战'] = cmdAccept;


// ——————————————————————————
// 3. 撤战（发起方撤回，接受前有效）
// ——————————————————————————
const cmdWithdraw = seal.ext.newCmdItemInfo();
cmdWithdraw.name = '撤战';
cmdWithdraw.help = '撤回尚未被接受的挑战：.撤战';
cmdWithdraw.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid      = msg.sender.userId.replace(`${platform}:`, '');
    const fullId   = `${platform}:${uid}`;

    const target = Object.values(getSessions()).find(
        s => s.initiator === fullId && s.status === 'pending_accept'
    );
    if (!target) {
        seal.replyToSender(ctx, msg, '【雨境】没有可撤回的挑战（不存在或已被接受）。');
        return seal.ext.newCmdExecuteResult(true);
    }

    target.status = 'cancelled';
    saveSession(target.pvpId, target);

    const me = getPlayer(platform, uid);
    me.timeLocked = false;
    savePlayer(platform, uid, me);
    unlockPlayerSlot(platform, uid, target.iLockDay, target.iLockSlot);

    seal.replyToSender(ctx, msg, `【雨境】执念之争已撤回（${target.pvpId}）。`);
    const [dPf, dUid] = target.defender.split(':');
    sendToMgmt(ctx.endPoint, platform,
        `【PVP撤回】${getRoleName(platform, uid)} 撤回了对 ${getRoleName(dPf, dUid)} 的挑战（${target.pvpId}）`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['撤战'] = cmdWithdraw;


// ——————————————————————————
// 4. pvp分配（管理员录入双方分配）
// ——————————————————————————
const cmdAlloc = seal.ext.newCmdItemInfo();
cmdAlloc.name = 'pvp分配';
cmdAlloc.help = '录入双方分配方案：.pvp分配 pvpId 攻击X防御Y 攻击X防御Y\n（发起方在前，防守方在后）';
cmdAlloc.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, '【雨境】无权限。');
        return seal.ext.newCmdExecuteResult(true);
    }

    const pvpId    = cmdArgs.getArgN(1);
    const iAllocS  = cmdArgs.getArgN(2);
    const dAllocS  = cmdArgs.getArgN(3);

    if (!pvpId || !iAllocS || !dAllocS) {
        const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r;
    }

    const parseAlloc = s => {
        const m = s.match(/^攻击(\d+)防御(\d+)$/);
        return m ? { atk: parseInt(m[1]), def: parseInt(m[2]) } : null;
    };
    const iA = parseAlloc(iAllocS);
    const dA = parseAlloc(dAllocS);

    if (!iA || !dA) {
        seal.replyToSender(ctx, msg, '【雨境】格式错误。\n示例：.pvp分配 pvp_xxx 攻击20防御10 攻击30防御20');
        return seal.ext.newCmdExecuteResult(true);
    }

    const session = getSession(pvpId);
    if (!session) {
        seal.replyToSender(ctx, msg, `【雨境】未找到会话：${pvpId}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (session.status !== 'pending_alloc_admin') {
        seal.replyToSender(ctx, msg, `【雨境】状态不符（当前：${session.status}），无法录入分配。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const iTotal = session.initiatorRaindrops * 10;
    const dTotal = session.defenderRaindrops * 10;

    if (iA.atk + iA.def !== iTotal)
        return (seal.replyToSender(ctx, msg, `【雨境】发起方攻+防须等于 ${iTotal}（${session.initiatorRaindrops}颗×10）`), seal.ext.newCmdExecuteResult(true));
    if (dA.atk + dA.def !== dTotal)
        return (seal.replyToSender(ctx, msg, `【雨境】防守方攻+防须等于 ${dTotal}（${session.defenderRaindrops}颗×10）`), seal.ext.newCmdExecuteResult(true));
    if (iA.atk < 1 || iA.def < 1)
        return (seal.replyToSender(ctx, msg, '【雨境】发起方攻击与防御均不可为0。'), seal.ext.newCmdExecuteResult(true));
    if (dA.atk < 1 || dA.def < 1)
        return (seal.replyToSender(ctx, msg, '【雨境】防守方攻击与防御均不可为0。'), seal.ext.newCmdExecuteResult(true));

    session.initiatorAlloc = iA;
    session.defenderAlloc  = dA;
    session.status         = 'ready_to_battle';
    saveSession(pvpId, session);

    const [iPf, iUid] = session.initiator.split(':');
    const [dPf, dUid] = session.defender.split(':');
    seal.replyToSender(ctx, msg,
        `【雨境】分配录入完成（${pvpId}）\n` +
        `${getRoleName(iPf, iUid)}：攻击${iA.atk} · 防御${iA.def}\n` +
        `${getRoleName(dPf, dUid)}：攻击${dA.atk} · 防御${dA.def}\n\n` +
        `发送 .pvp执行 ${pvpId} 开始战斗`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['pvp分配'] = cmdAlloc;


// ——————————————————————————
// 5. pvp执行（管理员触发战斗结算）
// ——————————————————————————
const cmdExecute = seal.ext.newCmdItemInfo();
cmdExecute.name = 'pvp执行';
cmdExecute.help = '执行战斗结算：.pvp执行 pvpId';
cmdExecute.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, '【雨境】无权限。');
        return seal.ext.newCmdExecuteResult(true);
    }

    const pvpId = cmdArgs.getArgN(1);
    if (!pvpId) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const session = getSession(pvpId);
    if (!session) {
        seal.replyToSender(ctx, msg, `【雨境】未找到会话：${pvpId}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (session.status !== 'ready_to_battle') {
        seal.replyToSender(ctx, msg, `【雨境】状态不符（当前：${session.status}），请先录入分配。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const [iPf, iUid] = session.initiator.split(':');
    const [dPf, dUid] = session.defender.split(':');
    const iName = getRoleName(iPf, iUid);
    const dName = getRoleName(dPf, dUid);
    const iA    = session.initiatorAlloc;
    const dA    = session.defenderAlloc;

    let iHP = session.initiatorHP;
    let dHP = session.defenderHP;

    // ——战斗日志——
    let log = `【执念之争·战报】\n`;
    log += `${iName}  ⚔️  ${dName}\n`;
    log += `${iName}：攻${iA.atk}·守${iA.def}（${session.initiatorRaindrops}颗）\n`;
    log += `${dName}：攻${dA.atk}·守${dA.def}（${session.defenderRaindrops}颗）\n`;
    log += `━━━━━━━━━━━━━━━━━━\n`;

    const MAX_ROUNDS = 300;
    let round = 1;
    while (iHP > 0 && dHP > 0 && round <= MAX_ROUNDS) {
        // 发起方攻，防守方守
        const iAtk = rd(iA.atk);
        const dDef = rd(dA.def);
        const dmg1 = Math.max(0, iAtk - dDef);
        dHP -= dmg1;
        log += `第${round}回合\n`;
        log += `  ${iName} 攻 ${iAtk}（//${iA.atk}）vs ${dName} 守 ${dDef}（//${dA.def}） → 伤害 ${dmg1}，${dName} HP：${Math.max(0, dHP)}\n`;
        if (dHP <= 0) break;

        // 防守方攻，发起方守
        const dAtk = rd(dA.atk);
        const iDef = rd(iA.def);
        const dmg2 = Math.max(0, dAtk - iDef);
        iHP -= dmg2;
        log += `  ${dName} 攻 ${dAtk}（//${dA.atk}）vs ${iName} 守 ${iDef}（//${iA.def}） → 伤害 ${dmg2}，${iName} HP：${Math.max(0, iHP)}\n`;

        round++;
    }

    log += `━━━━━━━━━━━━━━━━━━\n`;

    // ——更新实际HP——
    const iP = getPlayer(iPf, iUid);
    const dP = getPlayer(dPf, dUid);
    const iLost = Math.max(0, session.initiatorHP - Math.max(0, iHP));
    const dLost = Math.max(0, session.defenderHP  - Math.max(0, dHP));
    iP.hp = Math.max(0, iP.hp - iLost);
    dP.hp = Math.max(0, dP.hp - dLost);
    savePlayer(iPf, iUid, iP);
    savePlayer(dPf, dUid, dP);

    // ——判断胜负——
    const iDead = iHP <= 0;
    const dDead = dHP <= 0;
    let result;

    if (iDead && dDead) {
        result = 'draw';
        log += `【结果】双方同归于尽 · 平局\n雨点各自保留`;
    } else if (dDead) {
        result = 'initiator_win';
        log += `【结果】${iName} 胜\n获得 ${session.defenderRaindrops} 颗雨点`;
    } else {
        result = 'defender_win';
        log += `【结果】${dName} 胜\n获得 ${session.initiatorRaindrops} 颗雨点`;
    }

    seal.replyToSender(ctx, msg, log);

    // ——HP归零死亡（战斗消耗，早于雨点结算）——
    if (iP.hp <= 0 && iP.isAlive) handleDeath(ctx.endPoint, iPf, iUid, '执念之争中HP耗尽');
    if (dP.hp <= 0 && dP.isAlive) handleDeath(ctx.endPoint, dPf, dUid, '执念之争中HP耗尽');

    // ——雨点转移与死亡检查——
    settlePvp(ctx.endPoint, msg.platform, session, result);

    // 追加战后双方状态（结算后重读保证雨点准确）
    const iPost = getPlayer(iPf, iUid);
    const dPost = getPlayer(dPf, dUid);
    const postLog = `战后状态：\n${iName}｜HP：${iP.hp}｜雨点：${iPost.raindrops}\n${dName}｜HP：${dP.hp}｜雨点：${dPost.raindrops}`;
    seal.replyToSender(ctx, msg, postLog);

    // 战报推送到双方个人群
    notifyPlayer(ctx.endPoint, iPf, iUid,
        `【雨境·执念之争结果】\n对阵：${dName}\n结果：${result === 'initiator_win' ? '你胜出' : result === 'draw' ? '平局' : '你落败'}\n` +
        `战后｜HP：${iP.hp}｜雨点：${getPlayer(iPf, iUid).raindrops}`);
    notifyPlayer(ctx.endPoint, dPf, dUid,
        `【雨境·执念之争结果】\n对阵：${iName}\n结果：${result === 'defender_win' ? '你胜出' : result === 'draw' ? '平局' : '你落败'}\n` +
        `战后｜HP：${dP.hp}｜雨点：${getPlayer(dPf, dUid).raindrops}`);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['pvp执行'] = cmdExecute;


// ——————————————————————————
// 6. 开启 / 关闭 PVP
// ——————————————————————————
const cmdOpenPvp = seal.ext.newCmdItemInfo();
cmdOpenPvp.name = '开启pvp';
cmdOpenPvp.help = '管理员开启执念之争：.开启pvp';
cmdOpenPvp.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    setData('pvpOpen', true);
    seal.replyToSender(ctx, msg, '【雨境】执念之争已开启。');
    broadcastMain(ctx.endPoint, msg.platform, '【雨境】执念之争时间开启，雨点流转，执念碰撞。');
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['开启pvp'] = cmdOpenPvp;

const cmdClosePvp = seal.ext.newCmdItemInfo();
cmdClosePvp.name = '关闭pvp';
cmdClosePvp.help = '管理员关闭执念之争：.关闭pvp';
cmdClosePvp.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    setData('pvpOpen', false);
    seal.replyToSender(ctx, msg, '【雨境】执念之争已关闭。');
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['关闭pvp'] = cmdClosePvp;


// ——————————————————————————
// 7. pvp状态（管理员总览）
// ——————————————————————————
const cmdPvpStatus = seal.ext.newCmdItemInfo();
cmdPvpStatus.name = 'pvp状态';
cmdPvpStatus.help = '查看进行中的执念之争：.pvp状态';
cmdPvpStatus.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));

    const active = Object.values(getSessions()).filter(
        s => !['completed', 'cancelled'].includes(s.status)
    );
    if (active.length === 0) {
        seal.replyToSender(ctx, msg, '【雨境】当前没有进行中的执念之争。');
        return seal.ext.newCmdExecuteResult(true);
    }

    const statusLabel = {
        'pending_accept':      '等待应战',
        'pending_alloc_admin': '等待分配录入',
        'ready_to_battle':     '待执行'
    };

    let text = `【雨境·执念之争状态】共 ${active.length} 场\n`;
    for (const s of active) {
        const [iPf, iUid] = s.initiator.split(':');
        const [dPf, dUid] = s.defender.split(':');
        const elapsed = Math.floor((Date.now() - s.createdAt) / 60000);
        text += `\n▸ ${s.pvpId}\n`;
        text += `  ${getRoleName(iPf, iUid)} vs ${getRoleName(dPf, dUid)}\n`;
        text += `  状态：${statusLabel[s.status] || s.status}｜已 ${elapsed} 分钟\n`;
        if (s.status === 'pending_alloc_admin' || s.status === 'ready_to_battle') {
            text += `  发起携带：${s.initiatorRaindrops}颗｜防守携带：${s.defenderRaindrops}颗\n`;
        }
        if (s.status === 'ready_to_battle') {
            text += `  分配：${getRoleName(iPf, iUid)} 攻${s.initiatorAlloc.atk}守${s.initiatorAlloc.def}` +
                    ` / ${getRoleName(dPf, dUid)} 攻${s.defenderAlloc.atk}守${s.defenderAlloc.def}\n`;
        }
    }
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['pvp状态'] = cmdPvpStatus;


// ——————————————————————————
// 8. pvp检查超时（手动触发）
// ——————————————————————————
const cmdCheckTimeout = seal.ext.newCmdItemInfo();
cmdCheckTimeout.name = 'pvp检查超时';
cmdCheckTimeout.help = '手动触发超时检查：.pvp检查超时';
cmdCheckTimeout.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    checkTimeouts(ctx.endPoint, msg.platform);
    seal.replyToSender(ctx, msg, '【雨境】超时检查完成。');
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['pvp检查超时'] = cmdCheckTimeout;


// ——————————————————————————
// 9. 雨境信息（玩家自查）
// ——————————————————————————
const cmdMyInfo = seal.ext.newCmdItemInfo();
cmdMyInfo.name = '雨境信息';
cmdMyInfo.help = '查看自己的雨境状态：.雨境信息';
cmdMyInfo.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid      = msg.sender.userId.replace(`${platform}:`, '');
    const p        = getPlayer(platform, uid);
    const status   = !p.isAlive    ? '💀 已消散'
                   : p.isRevived   ? '🕯️ 续命中（禁PVP）'
                   : p.timeLocked  ? '⚔️ 对决中（时间线锁定）'
                   : '✅ 正常';
    seal.replyToSender(ctx, msg,
        `【雨境状态】\n🌧️ 雨点：${p.raindrops} 颗\n❤️ HP：${p.hp} / 100\n📋 状态：${status}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境信息'] = cmdMyInfo;


// ——————————————————————————
// 10. 雨境查询（管理员）
// ——————————————————————————
const cmdQuery = seal.ext.newCmdItemInfo();
cmdQuery.name = '雨境查询';
cmdQuery.help = '管理员查询玩家状态：.雨境查询 角色名  或  .雨境查询 全员';
cmdQuery.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    const platform = msg.platform;
    const arg      = cmdArgs.getArgN(1);
    if (!arg) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    if (arg === '全员') {
        const all = (getAllPlayers()[platform] || {});
        if (Object.keys(all).length === 0)
            return (seal.replyToSender(ctx, msg, '【雨境】暂无玩家数据。'), seal.ext.newCmdExecuteResult(true));
        let text = '【雨境·全员状态】\n';
        for (const [uid, p] of Object.entries(all)) {
            const icon = !p.isAlive ? '💀' : p.isRevived ? '🕯️' : p.timeLocked ? '⚔️' : '✅';
            text += `${icon} ${getRoleName(platform, uid)}｜雨点:${p.raindrops}｜HP:${p.hp}\n`;
        }
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    }

    const uid = getUidByRole(platform, arg);
    if (!uid) return (seal.replyToSender(ctx, msg, `【雨境】未找到角色「${arg}」。`), seal.ext.newCmdExecuteResult(true));
    const p  = getPlayer(platform, uid);
    const st = !p.isAlive ? '💀 已消散' : p.isRevived ? '🕯️ 续命中' : p.timeLocked ? '⚔️ 对决中' : '✅ 正常';
    seal.replyToSender(ctx, msg,
        `【雨境·${arg}】\n🌧️ 雨点：${p.raindrops} 颗\n❤️ HP：${p.hp} / 100\n📋 ${st}\n今日PVP：${p.pvpToday} 次`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境查询'] = cmdQuery;


// ——————————————————————————
// 11. 雨境设置（管理员调数值）
// ——————————————————————————
const cmdSet = seal.ext.newCmdItemInfo();
cmdSet.name = '雨境设置';
cmdSet.help = '调整玩家数值：.雨境设置 角色名 雨点+5 HP-20\n支持 +N -N =N，可同时写多个';
cmdSet.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    const platform = msg.platform;
    const roleName = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const uid = getUidByRole(platform, roleName);
    if (!uid) return (seal.replyToSender(ctx, msg, `【雨境】未找到角色「${roleName}」。`), seal.ext.newCmdExecuteResult(true));

    const p    = getPlayer(platform, uid);
    // 合并剩余参数
    const args = [cmdArgs.getArgN(2), cmdArgs.getArgN(3), cmdArgs.getArgN(4)].filter(Boolean).join(' ');
    const changed = [];

    const rainM = args.match(/雨点([+\-=])(\d+)/);
    if (rainM) {
        if (rainM[1] === '+') p.raindrops += parseInt(rainM[2]);
        else if (rainM[1] === '-') p.raindrops = Math.max(0, p.raindrops - parseInt(rainM[2]));
        else p.raindrops = parseInt(rainM[2]);
        changed.push(`雨点→${p.raindrops}`);
    }

    const hpM = args.match(/HP([+\-=])(\d+)/i);
    if (hpM) {
        if (hpM[1] === '+') p.hp = Math.min(100, p.hp + parseInt(hpM[2]));
        else if (hpM[1] === '-') p.hp = Math.max(0, p.hp - parseInt(hpM[2]));
        else p.hp = Math.min(100, parseInt(hpM[2]));
        changed.push(`HP→${p.hp}`);
    }

    if (changed.length === 0) {
        seal.replyToSender(ctx, msg, '【雨境】未识别到操作。\n支持：雨点+N 雨点-N 雨点=N HP+N HP-N HP=N');
        return seal.ext.newCmdExecuteResult(true);
    }

    savePlayer(platform, uid, p);
    seal.replyToSender(ctx, msg, `【雨境】${roleName} 已更新：${changed.join('，')}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境设置'] = cmdSet;


// ——————————————————————————
// 12. 雨境初始化（管理员）
// ——————————————————————————
const cmdInit = seal.ext.newCmdItemInfo();
cmdInit.name = '雨境初始化';
cmdInit.help = '初始化玩家雨境数据：.雨境初始化 角色名 N颗\n（HP重置为100，雨点为N，其余清零）';
cmdInit.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    const platform = msg.platform;
    const roleName = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const uid = getUidByRole(platform, roleName);
    if (!uid) return (seal.replyToSender(ctx, msg, `【雨境】未找到角色「${roleName}」。`), seal.ext.newCmdExecuteResult(true));

    const rainArg = cmdArgs.getArgN(2);
    const rainM   = rainArg ? rainArg.match(/^(\d+)颗?$/) : null;
    const initRain = rainM ? parseInt(rainM[1]) : 0;

    savePlayer(platform, uid, {
        raindrops: initRain, hp: 100,
        isAlive: true, isRevived: false, timeLocked: false,
        pvpToday: 0, pvpPairsToday: []
    });
    seal.replyToSender(ctx, msg, `【雨境】${roleName} 初始化完成｜HP:100｜雨点:${initRain}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境初始化'] = cmdInit;


// ——————————————————————————
// 13. 续命（玩家为他人续命，消耗1颗雨点）
// ——————————————————————————
const cmdRevive = seal.ext.newCmdItemInfo();
cmdRevive.name = '续命';
cmdRevive.help = '为消散的角色续命（消耗1颗雨点）：.续命 角色名';
cmdRevive.solve = (ctx, msg, cmdArgs) => {
    const platform = msg.platform;
    const uid      = msg.sender.userId.replace(`${platform}:`, '');
    const me       = getPlayer(platform, uid);

    if (!me.isAlive)        return (seal.replyToSender(ctx, msg, '【雨境】你已消散，无法续命他人。'), seal.ext.newCmdExecuteResult(true));
    if (me.raindrops < 1)   return (seal.replyToSender(ctx, msg, '【雨境】雨点不足（续命需消耗1颗）。'), seal.ext.newCmdExecuteResult(true));

    const roleName  = cmdArgs.getArgN(1);
    if (!roleName) { const r = seal.ext.newCmdExecuteResult(true); r.showHelp = true; return r; }

    const targetUid = getUidByRole(platform, roleName);
    if (!targetUid) return (seal.replyToSender(ctx, msg, `【雨境】未找到角色「${roleName}」。`), seal.ext.newCmdExecuteResult(true));

    const target = getPlayer(platform, targetUid);
    if (target.isRevived) return (seal.replyToSender(ctx, msg, '【雨境】对方已处于续命状态中。'), seal.ext.newCmdExecuteResult(true));
    if (target.isAlive)   return (seal.replyToSender(ctx, msg, '【雨境】对方尚未消散，无需续命。'), seal.ext.newCmdExecuteResult(true));

    me.raindrops -= 1;
    target.isAlive   = true;
    target.isRevived = true;
    target.hp        = 1;
    savePlayer(platform, uid, me);
    savePlayer(platform, targetUid, target);

    seal.replyToSender(ctx, msg,
        `【雨境】你消耗1颗雨点，为 ${roleName} 续命。续命期间对方无法参与PVP。`);
    notifyPlayer(ctx.endPoint, platform, targetUid,
        `【雨境】${getRoleName(platform, uid)} 为你续命，你暂时留存于雨境之中。续命期间禁止参与PVP。`);
    broadcastMain(ctx.endPoint, platform,
        '【雨境通报】一个消散的灵魂获得了续命，暂时留存于雨境之中。（续命状态）');
    sendToMgmt(ctx.endPoint, platform,
        `【续命】${getRoleName(platform, uid)} 为 ${roleName} 续命，消耗1颗雨点。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['续命'] = cmdRevive;


// ——————————————————————————
// 14. 雨境每日重置（管理员，天数切换时调用）
// ——————————————————————————
const cmdDailyReset = seal.ext.newCmdItemInfo();
cmdDailyReset.name = '雨境每日重置';
cmdDailyReset.help = '重置所有玩家今日PVP计数：.雨境每日重置';
cmdDailyReset.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    const all      = getAllPlayers();
    const platform = msg.platform;
    if (all[platform]) {
        for (const uid of Object.keys(all[platform])) {
            all[platform][uid].pvpToday      = 0;
            all[platform][uid].pvpPairsToday = [];
        }
    }
    setData('players', all);
    seal.replyToSender(ctx, msg, '【雨境】每日PVP计数已重置。');
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境每日重置'] = cmdDailyReset;


// ——————————————————————————
// 15. 设置管理群（管理员）
// ——————————————————————————
const cmdSetMgmt = seal.ext.newCmdItemInfo();
cmdSetMgmt.name = '雨境管理群';
cmdSetMgmt.help = '设置管理群群号：.雨境管理群 群号';
cmdSetMgmt.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));
    const gid = cmdArgs.getArgN(1);
    if (!gid || !/^\d+$/.test(gid))
        return (seal.replyToSender(ctx, msg, '【雨境】请输入纯数字群号。'), seal.ext.newCmdExecuteResult(true));
    setData('mgmtGroup', gid);
    seal.replyToSender(ctx, msg, `【雨境】管理群已设置为 ${gid}。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨境管理群'] = cmdSetMgmt;

// ——————————————————————————
// 16. 设置雨量（管理员）
// ——————————————————————————
const RAIN_TYPES = { '小雨': 4, '中雨': 3, '大雨': 2, '暴雨': 1 };

function getRainConfig() { return getData('rainConfig', null); }
function setRainConfig(cfg) { setData('rainConfig', cfg); }

const cmdSetRain = seal.ext.newCmdItemInfo();
cmdSetRain.name = '设置雨量';
cmdSetRain.help = '设置当日雨量：.设置雨量 [小雨/中雨/大雨/暴雨]';
cmdSetRain.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));

    const type = cmdArgs.getArgN(1);
    if (!type || !RAIN_TYPES[type]) {
        seal.replyToSender(ctx, msg, '【雨境】请输入有效雨量类型：小雨 / 中雨 / 大雨 / 暴雨');
        return seal.ext.newCmdExecuteResult(true);
    }

    const day = getGameDay();
    const cost = RAIN_TYPES[type];
    setRainConfig({ rainType: type, cost, dayStr: `D${day}`, paidUids: [] });

    seal.replyToSender(ctx, msg, `【雨境】已设置 D${day} 雨量：${type}（需缴纳 ${cost} 颗雨点）`);
    broadcastMain(ctx.endPoint, msg.platform,
        `【雨境·雨量公告】今日降雨：${type}\n` +
        `需缴纳 ${cost} 颗雨点，雨点不足部分按 20HP/颗 扣除。\n` +
        `发送「.缴纳雨点」进行缴纳。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['设置雨量'] = cmdSetRain;


// ——————————————————————————
// 17. 缴纳雨点（玩家）
// ——————————————————————————
const cmdPayRain = seal.ext.newCmdItemInfo();
cmdPayRain.name = '缴纳雨点';
cmdPayRain.help = '缴纳当日雨量：.缴纳雨点  或  .缴纳雨点 N颗（N为自愿消耗的雨点数，不足部分以HP抵偿）';
cmdPayRain.solve = (ctx, msg, cmdArgs) => {
    const reply = t => (seal.replyToSender(ctx, msg, `【雨境】${t}`), seal.ext.newCmdExecuteResult(true));

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, '');
    const p = getPlayer(platform, uid);

    if (!p.isAlive) return reply('你已消散，无需缴纳。');

    const cfg = getRainConfig();
    if (!cfg) return reply('当日雨量尚未公布，请等待管理组通知。');

    const day = getGameDay();
    if (cfg.dayStr !== `D${day}`) return reply('当日雨量尚未公布，请等待管理组通知。');

    const fullId = `${platform}:${uid}`;
    if (cfg.paidUids.includes(fullId)) return reply('你今日已缴纳过，请勿重复操作。');

    const cost = cfg.cost;
    let useRain;

    const arg = cmdArgs.getArgN(1);
    if (arg) {
        const m = arg.match(/^(\d+)颗?$/);
        if (!m) return reply('格式错误。示例：.缴纳雨点  或  .缴纳雨点 2颗');
        useRain = parseInt(m[1]);
        if (useRain > cost) return reply(`今日${cfg.rainType}只需缴纳 ${cost} 颗，无需超额。`);
        if (useRain > p.raindrops) return reply(`雨点不足（持有：${p.raindrops} 颗）。`);
    } else {
        useRain = Math.min(p.raindrops, cost);
    }

    const hpDeduct = (cost - useRain) * 20;
    p.raindrops -= useRain;
    p.hp = Math.max(0, p.hp - hpDeduct);

    cfg.paidUids.push(fullId);
    setRainConfig(cfg);
    savePlayer(platform, uid, p);

    let result = `【雨境·缴纳完成】${cfg.rainType}（共 ${cost} 颗）\n消耗雨点：${useRain} 颗`;
    if (hpDeduct > 0) result += `\nHP抵偿：${hpDeduct}（${cost - useRain} 颗×20HP）`;
    result += `\n当前｜雨点：${p.raindrops} 颗｜HP：${p.hp}`;
    seal.replyToSender(ctx, msg, result);

    sendToMgmt(ctx.endPoint, platform,
        `【雨量缴纳】${getRoleName(platform, uid)}：雨点-${useRain}，HP-${hpDeduct}，剩余HP:${p.hp}`);

    if (p.hp <= 0 && p.isAlive) handleDeath(ctx.endPoint, platform, uid, `${cfg.rainType}侵蚀·HP耗尽`);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['缴纳雨点'] = cmdPayRain;


// ——————————————————————————
// 18. 雨量状态（管理员）
// ——————————————————————————
const cmdRainStatus = seal.ext.newCmdItemInfo();
cmdRainStatus.name = '雨量状态';
cmdRainStatus.help = '查看当日雨量缴纳情况：.雨量状态';
cmdRainStatus.solve = (ctx, msg, cmdArgs) => {
    if (!isAdmin(ctx, msg)) return (seal.replyToSender(ctx, msg, '【雨境】无权限。'), seal.ext.newCmdExecuteResult(true));

    const cfg = getRainConfig();
    if (!cfg) {
        seal.replyToSender(ctx, msg, '【雨境】当日雨量尚未设置。');
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const all = getAllPlayers()[platform] || {};
    const aliveUids = Object.entries(all).filter(([_, p]) => p.isAlive).map(([uid]) => uid);
    const paidSet = new Set(cfg.paidUids.map(k => k.split(':')[1]));
    const unpaid = aliveUids.filter(uid => !paidSet.has(uid));

    let text = `【雨境·雨量状态】${cfg.dayStr} ${cfg.rainType}（${cfg.cost}颗）\n`;
    text += `已缴：${cfg.paidUids.length} 人｜未缴：${unpaid.length} 人`;
    if (unpaid.length > 0)
        text += `\n未缴名单：${unpaid.map(uid => getRoleName(platform, uid)).join('、')}`;

    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['雨量状态'] = cmdRainStatus;

console.log('[雨境] v1.0.0 加载完成');
