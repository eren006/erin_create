// ==UserScript==
// @name         纸牌竞技系统（机器人主持）
// @author       长日将尽
// @version      1.0.0
// @description  Texas Hold'em改编，机器人主持人管理游戏流程
// @timestamp    1742205760
// @license      MIT
// ==/UserScript==

/**
 * 纸牌竞技系统 - 非赌博类游戏
 * 核心特性：
 * - 机器人主持人艾特玩家，控制游戏节奏
 * - 每局独立计分，不涉及真实交易
 * - 私信发牌，公开比牌
 * - 支持多人同时游戏
 */

let ext = seal.ext.find('cardgame_system');
if (!ext) {
    ext = seal.ext.new("cardgame_system", "长日将尽纸牌竞技", "1.0.0");
    seal.ext.register(ext);
}

// ========================
// 核心工具函数
// ========================

function getMainExt() {
    const main = seal.ext.find('changri');
    if (!main) {
        console.error("❌ 未找到主插件 changri");
        return null;
    }
    return main;
}

// 参考长日系统的寄信方式，发送到玩家的个人私聊群
// 使用方式完全参照长日系统的 sendLetter
function sendToPrivateGroup(ctx, endPoint, platform, roleName, message) {
    const main = getMainExt();
    if (!main) {
        console.error("[牌局] 主插件未找到");
        return false;
    }

    try {
        const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
        const targetEntry = a_private_group[platform]?.[roleName];

        if (!targetEntry || !targetEntry[1]) {
            console.error(`[牌局] 找不到${roleName}的个人群信息`);
            return false;
        }

        // 完全参照长日系统的寄信方式
        const deliverMsg = seal.newMessage();
        deliverMsg.messageType = "group";
        deliverMsg.groupId = `${platform}-Group:${targetEntry[1]}`;

        const deliverCtx = seal.createTempCtx(endPoint, deliverMsg);
        seal.replyToSender(deliverCtx, deliverMsg, message);

        return true;
    } catch (e) {
        console.error(`[牌局] 发送到个人群失败: ${e.message}`);
        return false;
    }
}

function getCardGameData() {
    const main = getMainExt();
    return main ? JSON.parse(main.storageGet("card_game_data") || "{}") : {};
}

function saveCardGameData(data) {
    const main = getMainExt();
    if (main) main.storageSet("card_game_data", JSON.stringify(data));
}

function getRoleName(ctx, msg) {
    const main = getMainExt();
    if (!main) return msg.sender.nickname;
    try {
        const charData = JSON.parse(main.storageGet("Character_Platform") || "{}");
        const parts = msg.sender.userId.split(':');
        const platform = parts[0];
        const uid = parts[1];
        return charData[platform]?.[uid] || msg.sender.nickname;
    } catch (e) {
        return msg.sender.nickname;
    }
}

function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");
    const main = getMainExt();
    if (!main) return false;
    try {
        const a_adminList = JSON.parse(main.storageGet("a_adminList") || "{}");
        return a_adminList[platform] && a_adminList[platform].includes(uid);
    } catch (e) {
        return false;
    }
}

// ========================
// 牌组操作
// ========================

// 创建标准52张牌组
function createDeck() {
    const suits = ['♠', '♥', '♦', '♣'];
    const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
    const deck = [];
    for (let i = 0; i < suits.length; i++) {
        for (let j = 0; j < ranks.length; j++) {
            deck.push({ suit: suits[i], rank: ranks[j], code: i * 13 + j });
        }
    }
    return deck;
}

// 洗牌
function shuffleDeck(deck) {
    const shuffled = [...deck];
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
}

// 卡牌显示
function cardToString(card) {
    return `${card.suit}${card.rank}`;
}

function cardsToString(cards) {
    return cards.map(cardToString).join(' ');
}

// ========================
// 手牌评估
// ========================

function getRankValue(rank) {
    const ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'];
    return ranks.indexOf(rank);
}

// 评估5张牌的强度（返回[等级, 高牌序列]）
function evaluateHand(cards) {
    if (cards.length !== 5) return [0, []];

    const ranks = cards.map(c => getRankValue(c.rank));
    const suits = cards.map(c => c.suit);
    const rankCounts = {};

    ranks.forEach(r => rankCounts[r] = (rankCounts[r] || 0) + 1);
    const counts = Object.values(rankCounts).sort((a, b) => b - a);

    // 检查同花
    const isFlush = suits.every(s => s === suits[0]);

    // 检查顺子
    const sortedRanks = [...ranks].sort((a, b) => b - a);
    const isStright = sortedRanks.every((r, i) => i === 0 || r === sortedRanks[i-1] - 1) ||
                     (sortedRanks.join(',') === '12,3,2,1,0'); // A-2-3-4-5

    // 等级评估 (从高到低)
    if (isFlush && isStright) return [8, sortedRanks]; // 同花顺
    if (counts[0] === 4) return [7, sortedRanks];      // 四条
    if (counts[0] === 3 && counts[1] === 2) return [6, sortedRanks]; // 葫芦
    if (isFlush) return [5, sortedRanks];              // 同花
    if (isStright) return [4, sortedRanks];            // 顺子
    if (counts[0] === 3) return [3, sortedRanks];      // 三条
    if (counts[0] === 2 && counts[1] === 2) return [2, sortedRanks]; // 两对
    if (counts[0] === 2) return [1, sortedRanks];      // 一对
    return [0, sortedRanks];                           // 高牌
}

// 比较两手牌
function compareHands(hand1, hand2) {
    const [grade1, kickers1] = hand1;
    const [grade2, kickers2] = hand2;

    if (grade1 !== grade2) return grade1 > grade2 ? 1 : -1;
    for (let i = 0; i < kickers1.length; i++) {
        if (kickers1[i] !== kickers2[i]) return kickers1[i] > kickers2[i] ? 1 : -1;
    }
    return 0;
}

// ========================
// 炸金花牌型评估（3张牌）
// ========================

function getRankValue(rank) {
    const rankMap = { 'A': 14, 'K': 13, 'Q': 12, 'J': 11 };
    if (rankMap[rank]) return rankMap[rank];
    const num = parseInt(rank);
    return num >= 2 && num <= 10 ? num : 0;
}

function evaluateThreeCards(cards) {
    // 返回 [等级, 高牌序列]
    // 等级：5=豹子 4=顺金 3=金花 2=顺子 1=对子 0=高牌

    if (!cards || cards.length !== 3) return [0, []];

    const ranks = cards.map(c => getRankValue(c.rank)).sort((a, b) => b - a);
    const suits = cards.map(c => c.suit);

    // 检查豹子（三张相同）
    if (ranks[0] === ranks[1] && ranks[1] === ranks[2]) {
        return [5, ranks];
    }

    // 检查同花
    const isFlush = suits[0] === suits[1] && suits[1] === suits[2];

    // 检查顺子（包括特殊情况 A-2-3）
    const isStraight = (ranks[0] - ranks[1] === 1 && ranks[1] - ranks[2] === 1) ||
                       (ranks[0] === 14 && ranks[1] === 3 && ranks[2] === 2); // A-3-2

    if (isFlush && isStraight) {
        // 顺金：特殊处理 A-3-2 为最小顺金
        const straightRanks = (ranks[0] === 14 && ranks[1] === 3 && ranks[2] === 2)
            ? [5, 4, 3]  // A-3-2 视为 5-4-3（最小）
            : ranks;
        return [4, straightRanks];
    }

    if (isFlush) {
        // 金花（同花）
        return [3, ranks];
    }

    if (isStraight) {
        // 顺子
        const straightRanks = (ranks[0] === 14 && ranks[1] === 3 && ranks[2] === 2)
            ? [5, 4, 3]  // A-3-2
            : ranks;
        return [2, straightRanks];
    }

    // 检查对子（两张相同）
    if (ranks[0] === ranks[1]) {
        const kickers = [ranks[0], ranks[0], ranks[2]];
        return [1, kickers];
    }
    if (ranks[1] === ranks[2]) {
        const kickers = [ranks[1], ranks[1], ranks[0]];
        return [1, kickers];
    }

    // 高牌（都不同）
    return [0, ranks];
}

function compareThreeCards(hand1, hand2) {
    const [grade1, kickers1] = hand1;
    const [grade2, kickers2] = hand2;

    // 先比等级
    if (grade1 !== grade2) {
        return grade1 > grade2 ? 1 : -1;
    }

    // 等级相同，按高牌序列比较
    for (let i = 0; i < Math.min(kickers1.length, kickers2.length); i++) {
        if (kickers1[i] !== kickers2[i]) {
            return kickers1[i] > kickers2[i] ? 1 : -1;
        }
    }

    return 0; // 完全相同（平局）
}

// ========================
// 游戏指令
// ========================

let cmd_create_game = seal.ext.newCmdItemInfo();
cmd_create_game.name = "创建竞技";
cmd_create_game.help = "创建一场纸牌竞技赛\n.创建竞技 [人数=6] [初始积分=1000]";
cmd_create_game.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 仅管理员可创建竞技赛");
    }

    let maxPlayers = parseInt(cmdArgs.getArgN(1)) || 6;
    let initialScore = parseInt(cmdArgs.getArgN(2)) || 1000;

    if (maxPlayers < 2 || maxPlayers > 10) {
        return seal.replyToSender(ctx, msg, "❌ 人数需要在2-10之间");
    }

    const gameId = Date.now().toString();
    const games = getCardGameData();

    games[gameId] = {
        gameId: gameId,
        gameType: "texas",     // 游戏类型标识
        status: "waiting",  // waiting, dealing, playing, ended
        maxPlayers: maxPlayers,
        initialScore: initialScore,
        players: [],
        seats: new Array(maxPlayers).fill(null),
        deck: [],
        communityCards: [],
        pot: 0,
        currentBettor: 0,
        round: 0,  // 0=pre-flop, 1=flop, 2=turn, 3=river
        createdAt: Date.now(),
        lastActionTime: null,  // 上一次操作的时间戳
        actionTimeout: 30000   // 30秒超时（毫秒）
    };

    saveCardGameData(games);

    let reply = `🎴 创建竞技赛成功！\n`;
    reply += `游戏ID: ${gameId}\n`;
    reply += `最多${maxPlayers}人，初始积分${initialScore}分\n`;
    reply += `────────────\n`;
    reply += `📍 当前座位：\n`;
    for (let i = 0; i < maxPlayers; i++) {
        reply += `座位${i+1}: （空）\n`;
    }
    reply += `\n使用 .加入竞技 [座位号] 加入游戏\n`;
    reply += `或使用 .加入竞技 自动分配\n`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建竞技"] = cmd_create_game;

// ========================

let cmd_join_game = seal.ext.newCmdItemInfo();
cmd_join_game.name = "加入竞技";
cmd_join_game.help = "加入纸牌竞技赛\n.加入竞技 [座位号]\n.加入竞技 自动";
cmd_join_game.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    const seatInput = cmdArgs.getArgN(1);
    const games = getCardGameData();

    // 找最新的游戏
    const gameId = Object.keys(games)
        .filter(id => games[id].status === "waiting")
        .sort((a, b) => parseInt(b) - parseInt(a))[0];

    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 当前没有等待中的竞技赛");
    }

    const game = games[gameId];

    // 检查是否已在游戏中
    if (game.players.find(p => p.name === roleName)) {
        return seal.replyToSender(ctx, msg, "❌ 你已经加入这场竞技赛了");
    }

    let seatIndex = -1;

    if (seatInput === "自动") {
        // 自动分配
        seatIndex = game.seats.indexOf(null);
    } else {
        seatIndex = parseInt(seatInput) - 1;
    }

    if (seatIndex < 0 || seatIndex >= game.maxPlayers) {
        return seal.replyToSender(ctx, msg, `❌ 座位号需要在1-${game.maxPlayers}之间`);
    }

    if (game.seats[seatIndex] !== null) {
        return seal.replyToSender(ctx, msg, `❌ 座位${seatIndex+1}已被占据`);
    }

    game.seats[seatIndex] = roleName;
    game.players.push({
        name: roleName,
        seat: seatIndex,
        score: game.initialScore,
        holeCards: [],
        currentBet: 0,
        totalBet: 0,
        status: "active",
        folded: false
    });

    saveCardGameData(games);

    let reply = `✅ ${roleName} 成功加入座位${seatIndex+1}！\n\n`;
    reply += `📍 当前座位:\n`;
    for (let i = 0; i < game.maxPlayers; i++) {
        const playerName = game.seats[i] || "（空）";
        reply += `座位${i+1}: ${playerName}\n`;
    }
    reply += `\n当前${game.players.length}/${game.maxPlayers}人\n`;

    if (game.players.length === game.maxPlayers) {
        reply += `\n👉 人数已满！管理员可以使用 .开始游戏 ${gameId} 开始竞技\n`;
    }

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["加入竞技"] = cmd_join_game;

// ========================
// 游戏开始和流程
// ========================

let cmd_start_game = seal.ext.newCmdItemInfo();
cmd_start_game.name = "开始游戏";
cmd_start_game.help = "开始纸牌竞技赛\n.开始游戏 [游戏ID]";
cmd_start_game.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 仅管理员可开始游戏");
    }

    const gameId = cmdArgs.getArgN(1);
    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 请指定游戏ID: .开始游戏 [ID]");
    }

    const games = getCardGameData();
    const game = games[gameId];

    if (!game) {
        return seal.replyToSender(ctx, msg, "❌ 游戏ID不存在");
    }

    if (game.status !== "waiting") {
        return seal.replyToSender(ctx, msg, "❌ 游戏已开始或已结束");
    }

    if (game.players.length < 2) {
        return seal.replyToSender(ctx, msg, "❌ 至少需要2个玩家");
    }

    // 初始化游戏
    game.status = "dealing";
    game.round = 0;
    game.currentBettor = 0;
    game.deck = shuffleDeck(createDeck());
    game.communityCards = [];

    // 给每个玩家发2张底牌
    game.players.forEach((player, idx) => {
        const card1 = game.deck.pop();
        const card2 = game.deck.pop();
        player.holeCards = [card1, card2];
        player.currentBet = 0;
        player.totalBet = 0;
        player.folded = false;
        player.status = "active";
    });

    game.pot = 0;
    game.round = 0;

    game.status = "playing";
    game.pot = 0;
    game.round = 0;
    game.currentBettor = 0;

    saveCardGameData(games);

    // 发送开始消息
    let startMsg = `🎴 纸牌竞技赛正式开始！\n`;
    startMsg += `════════════════════\n`;
    startMsg += `👥 参赛玩家（${game.players.length}人）:\n`;
    game.players.forEach((p, i) => {
        startMsg += `座位${p.seat + 1}: ${p.name} - ${p.score}积分\n`;
    });
    startMsg += `════════════════════\n`;
    startMsg += `🎴 底牌已发送到私聊群\n`;
    startMsg += `⏳ 第一个玩家（座位${game.players[0].seat + 1}）请准备...\n`;

    seal.replyToSender(ctx, msg, startMsg);

    // 分别给每个玩家私信发底牌
    const main = getMainExt();
    if (!main) {
        seal.replyToSender(ctx, msg, "⚠️ 警告：无法发送底牌，主插件未找到");
        return seal.ext.newCmdExecuteResult(true);
    }

    try {
        const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
        const platform = msg.platform;

        game.players.forEach((player, idx) => {
            let cardMsg = `🎴【底牌】\n`;
            cardMsg += `你的两张底牌：${cardsToString(player.holeCards)}\n`;
            cardMsg += `\n────────────\n`;
            cardMsg += `座位: ${player.seat + 1}\n`;
            cardMsg += `当前积分: ${player.score}\n`;
            cardMsg += `────────────\n`;
            cardMsg += `💡 保管好这张牌，不要告诉其他人！\n`;

            if (idx === 0) {
                cardMsg += `\n🔔 【你是第一位玩家】\n`;
                cardMsg += `准备好后，在公开群中使用：\n`;
                cardMsg += `.跟注 / .弃牌 / .加注 [数额] / .全押\n`;
            }

            sendToPrivateGroup(ctx, ctx.endPoint, platform, player.name, cardMsg);
        });
    } catch (e) {
        console.error(`发牌失败: ${e.message}`);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始游戏"] = cmd_start_game;

// ========================
// 玩家操作指令
// ========================

let cmd_check = seal.ext.newCmdItemInfo();
cmd_check.name = "跟注";
cmd_check.help = "跟注当前下注额";
cmd_check.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    const games = getCardGameData();

    // 找该玩家所在的游戏
    const gameId = Object.keys(games).find(id =>
        games[id].status === "playing" &&
        games[id].players.some(p => p.name === roleName)
    );

    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 你未参加任何进行中的竞技赛");
    }

    const game = games[gameId];
    const player = game.players.find(p => p.name === roleName);
    const currentBettingPlayer = game.players[game.currentBettor];

    if (player.name !== currentBettingPlayer.name) {
        return seal.replyToSender(ctx, msg, `❌ 现在轮到 ${currentBettingPlayer.name} 操作\n使用: .跟注 / .加注 [数额] / .弃牌`);
    }

    if (player.folded) {
        return seal.replyToSender(ctx, msg, "❌ 你已弃牌");
    }

    // 检查是否超时
    if (handlePlayerTimeout(game, games, gameId, ctx, roleName)) {
        // 已超时自动弃牌，nextBettor 已在 checkTimeout 中被调用
        return seal.replyToSender(ctx, msg, `❌ 你操作超时已自动弃牌！`);
    }

    const needToBet = currentBettingPlayer.currentBet - player.currentBet;
    if (needToBet > player.score) {
        return seal.replyToSender(ctx, msg, `❌ 你的积分不足，只能全押 .全押`);
    }

    // 执行跟注
    player.currentBet += needToBet;
    player.score -= needToBet;
    game.pot += needToBet;
    player.totalBet += needToBet;

    let reply = `✅ ${roleName} 跟注了 ${needToBet} 积分\n`;
    reply += `💰 底池: ${game.pot}\n`;
    reply += `剩余积分: ${player.score}`;

    seal.replyToSender(ctx, msg, reply);

    // 轮到下一个玩家
    if (game.gameType === "zhajinhua") {
        nextBettorZhajinhua(game, games, gameId, ctx);
    } else {
        nextBettor(game, games, gameId, ctx);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["跟注"] = cmd_check;

let cmd_fold = seal.ext.newCmdItemInfo();
cmd_fold.name = "弃牌";
cmd_fold.help = "弃牌并退出当轮";
cmd_fold.solve = (ctx, msg) => {
    const roleName = getRoleName(ctx, msg);
    const games = getCardGameData();

    const gameId = Object.keys(games).find(id =>
        games[id].status === "playing" &&
        games[id].players.some(p => p.name === roleName)
    );

    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 你未参加任何进行中的竞技赛");
    }

    const game = games[gameId];
    const player = game.players.find(p => p.name === roleName);

    if (player.folded) {
        return seal.replyToSender(ctx, msg, "❌ 你已经弃牌了");
    }

    // 检查是否超时（如果轮到该玩家但已超时）
    const currentBettingPlayer = game.players[game.currentBettor];
    if (player.name === currentBettingPlayer.name) {
        if (checkTimeout(game, games, gameId, ctx)) {
            return seal.replyToSender(ctx, msg, `❌ 你操作超时已自动弃牌！`);
        }
    }

    player.folded = true;
    player.status = "folded";

    let reply = `⚠️ ${roleName} 弃牌了\n`;
    reply += `退出本轮竞争\n`;
    reply += `💰 底池: ${game.pot}`;

    seal.replyToSender(ctx, msg, reply);

    saveCardGameData(games);

    if (game.gameType === "zhajinhua") {
        nextBettorZhajinhua(game, games, gameId, ctx);
    } else {
        nextBettor(game, games, gameId, ctx);
    }

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["弃牌"] = cmd_fold;

// 下一个投注者 - 机器人主持人艾特下一个玩家
function nextBettor(game, games, gameId, ctx) {
    const activePlayers = game.players.filter(p => !p.folded && p.status === "active");

    if (activePlayers.length <= 1) {
        // 游戏结束
        endRound(game, games, gameId, ctx);
        return;
    }

    // 找下一个未弃牌的玩家
    let nextIdx = (game.currentBettor + 1) % game.players.length;
    let attempts = 0;
    while (game.players[nextIdx].folded && attempts < game.players.length) {
        nextIdx = (nextIdx + 1) % game.players.length;
        attempts++;
    }

    game.currentBettor = nextIdx;
    const nextPlayer = game.players[game.currentBettor];

    if (nextPlayer.folded) {
        nextBettor(game, games, gameId, ctx);
        return;
    }

    // 记录操作开始时间（用于超时检查）
    game.lastActionTime = Date.now();

    saveCardGameData(games);

    // 🤖 机器人主持人艾特下一个玩家
    if (ctx) {
        let actionMsg = `\n💬 【机器人主持】\n`;
        actionMsg += `@${nextPlayer.name} 现在轮到你了！\n`;
        actionMsg += `────────────\n`;
        actionMsg += `座位: ${nextPlayer.seat + 1}\n`;
        actionMsg += `你的积分: ${nextPlayer.score}\n`;
        actionMsg += `当前下注额: ${game.betAmount || 0}\n`;
        actionMsg += `底池: ${game.pot}\n`;
        actionMsg += `────────────\n`;
        actionMsg += `⏱️  30秒内未操作将自动弃牌\n`;
        actionMsg += `\n请选择下列之一：\n`;
        actionMsg += `  .跟注          跟当前下注额\n`;
        actionMsg += `  .弃牌          放弃本轮\n`;
        actionMsg += `  .加注 [数额]   加注到指定积分\n`;
        actionMsg += `  .全押          投入所有积分\n`;

        seal.replyToSender(ctx, ctx.message, actionMsg);
    }
}

// 检查是否超时，超时则自动弃牌
function checkTimeout(game, games, gameId, ctx) {
    if (!game.lastActionTime) return false;

    const elapsed = Date.now() - game.lastActionTime;

    if (elapsed > game.actionTimeout) {
        const currentPlayer = game.players[game.currentBettor];
        currentPlayer.folded = true;
        currentPlayer.status = "folded";

        let timeoutMsg = `\n⏱️ 【超时自动弃牌】\n`;
        timeoutMsg += `${currentPlayer.name} 超过30秒未操作\n`;
        timeoutMsg += `自动弃牌！\n`;
        timeoutMsg += `💰 底池: ${game.pot}`;

        if (ctx) seal.replyToSender(ctx, ctx.message, timeoutMsg);

        saveCardGameData(games);
        return true;
    }

    return false;
}

// 检查玩家是否超时并自动弃牌
function handlePlayerTimeout(game, games, gameId, ctx, roleName) {
    const player = game.players.find(p => p.name === roleName);
    if (!player) return false;

    const currentBettingPlayer = game.players[game.currentBettor];
    if (player.name !== currentBettingPlayer.name) return false;

    // 检查是否超时
    if (checkTimeout(game, games, gameId, ctx)) {
        return true; // 已超时并自动弃牌
    }

    return false; // 未超时
}

function endRound(game, games, gameId, ctx) {
    const activePlayers = game.players.filter(p => !p.folded);

    if (activePlayers.length === 1) {
        // 只剩一个人，他赢
        const winner = activePlayers[0];
        winner.score += game.pot;

        let msg = `\n🏆【本轮结束】\n`;
        msg += `${winner.name} 赢得本轮！\n`;
        msg += `获得积分: +${game.pot}\n`;
        msg += `总积分: ${winner.score}`;

        if (ctx) seal.replyToSender(ctx, ctx.message, msg);

        game.status = "ended";
        saveCardGameData(games);
        return;
    }

    // 多个人存活，显示公牌进行比牌
    if (game.round < 3) {
        dealCommunityCards(game, games, gameId, ctx);
    } else {
        // 河牌已出，进行摊牌
        showdown(game, games, gameId, ctx);
    }
}

function dealCommunityCards(game, games, gameId, ctx) {
    const stages = ["Flop（翻牌）", "Turn（转牌）", "River（河牌）"];
    const stageCounts = [3, 1, 1];

    for (let i = 0; i < stageCounts[game.round]; i++) {
        game.communityCards.push(game.deck.pop());
    }

    game.round++;

    let msg = `\n🎴【${stages[game.round - 1]}】\n`;
    msg += `公共牌: ${cardsToString(game.communityCards)}\n`;
    msg += `底池: ${game.pot}`;

    if (ctx) seal.replyToSender(ctx, ctx.message, msg);

    // 重置下注
    game.players.forEach(p => {
        if (!p.folded) p.currentBet = 0;
    });
    game.currentBettor = 0;

    saveCardGameData(games);

    // 继续下注轮
    nextBettor(game, games, gameId, ctx);
}

function showdown(game, games, gameId, ctx) {
    const activePlayers = game.players.filter(p => !p.folded);

    let bestHandValue = null;
    let winners = [];

    activePlayers.forEach(player => {
        const allCards = [...player.holeCards, ...game.communityCards];
        // 计算最好的5张牌（这里简化为使用前5张）
        const bestFive = allCards.slice(0, 5);
        const handValue = evaluateHand(bestFive);

        if (bestHandValue === null || compareHands(handValue, bestHandValue) > 0) {
            bestHandValue = handValue;
            winners = [player];
        } else if (compareHands(handValue, bestHandValue) === 0) {
            winners.push(player);
        }
    });

    const winnerShare = Math.floor(game.pot / winners.length);

    let resultMsg = `\n🏆【摊牌结果】\n`;
    resultMsg += `最终公共牌: ${cardsToString(game.communityCards)}\n`;
    resultMsg += `────────────\n`;

    winners.forEach(winner => {
        winner.score += winnerShare;
        resultMsg += `🎉 ${winner.name} 获胜!\n`;
        resultMsg += `  手牌: ${cardsToString(winner.holeCards)}\n`;
        resultMsg += `  获得积分: +${winnerShare}\n`;
        resultMsg += `  总积分: ${winner.score}\n`;
    });

    if (ctx) seal.replyToSender(ctx, ctx.message, resultMsg);

    game.status = "ended";
    saveCardGameData(games);
}

// ========================

let cmd_rules = seal.ext.newCmdItemInfo();
cmd_rules.name = "牌型规则";
cmd_rules.help = "查看所有牌型的大小关系";
cmd_rules.solve = (ctx, msg) => {
    let reply = `🎴 纸牌竞技 - 牌型大小表\n`;
    reply += `════════════════════\n\n`;

    reply += `【1】皇家同花顺 🏆 最大\n`;
    reply += `同一花色的 10-J-Q-K-A\n`;
    reply += `示例：♠10 ♠J ♠Q ♠K ♠A\n`;
    reply += `出现概率：1/649,740\n\n`;

    reply += `【2】同花顺\n`;
    reply += `同一花色的连续5张牌\n`;
    reply += `示例：♥5 ♥6 ♥7 ♥8 ♥9\n`;
    reply += `特殊：A-2-3-4-5 也是顺子（最小顺子）\n\n`;

    reply += `【3】四条（铁支）\n`;
    reply += `4张相同花色的牌\n`;
    reply += `示例：♠A ♥A ♦A ♣A (加任意1张)\n\n`;

    reply += `【4】葫芦（满堂红）\n`;
    reply += `3张相同 + 2张相同\n`;
    reply += `示例：♠K ♥K ♦K ♣5 ♥5\n`;
    reply += `（三个K + 一对5）\n\n`;

    reply += `【5】同花（花）\n`;
    reply += `同一花色的任意5张牌\n`;
    reply += `示例：♦2 ♦5 ♦8 ♦J ♦Q\n\n`;

    reply += `【6】顺子（龙）\n`;
    reply += `任意花色的连续5张牌\n`;
    reply += `示例：♠2 ♥3 ♦4 ♣5 ♠6\n`;
    reply += `特殊：A-2-3-4-5 是最小顺子\n\n`;

    reply += `【7】三条（三个子）\n`;
    reply += `3张相同的牌\n`;
    reply += `示例：♠9 ♥9 ♦9 ♣2 ♥5\n\n`;

    reply += `【8】两对\n`;
    reply += `两组相同的牌\n`;
    reply += `示例：♠K ♥K ♦7 ♣7 ♠2\n`;
    reply += `（一对K + 一对7 + 一张2）\n\n`;

    reply += `【9】一对\n`;
    reply += `2张相同的牌\n`;
    reply += `示例：♠Q ♥Q ♦3 ♣8 ♠2\n\n`;

    reply += `【10】高牌 💧 最小\n`;
    reply += `没有任何组合，只比最高牌\n`;
    reply += `示例：♠A ♥K ♦J ♣9 ♠5\n`;
    reply += `（单独一张A是最大的高牌）\n\n`;

    reply += `════════════════════\n`;
    reply += `⚡ 快速记忆口诀\n`;
    reply += `从大到小：\n`;
    reply += `皇家顺 → 顺 → 四 → 葫 → 花\n`;
    reply += `龙 → 三 → 两对 → 一对 → 高\n`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["牌型规则"] = cmd_rules;

// ========================

let cmd_list_games = seal.ext.newCmdItemInfo();
cmd_list_games.name = "竞技列表";
cmd_list_games.help = "查看所有竞技赛";
cmd_list_games.solve = (ctx, msg) => {
    const games = getCardGameData();
    const waitingGames = Object.values(games).filter(g => g.status === "waiting");

    if (waitingGames.length === 0) {
        return seal.replyToSender(ctx, msg, "📭 当前没有等待中的竞技赛");
    }

    let reply = `🎴 竞技赛列表\n`;
    reply += `────────────\n`;

    waitingGames.forEach(game => {
        reply += `\n🆔 ${game.gameId}\n`;
        reply += `👥 ${game.players.length}/${game.maxPlayers} 人已加入\n`;
        reply += `💰 初始积分: ${game.initialScore}\n`;
        reply += `加入: .加入竞技 [座位号]\n`;
    });

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["竞技列表"] = cmd_list_games;

// ========================
// 炸金花游戏命令
// ========================

let cmd_create_zhajinhua = seal.ext.newCmdItemInfo();
cmd_create_zhajinhua.name = "创建炸金花";
cmd_create_zhajinhua.help = "创建一场炸金花赛\n.创建炸金花 [人数=5] [初始积分=100]";
cmd_create_zhajinhua.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        return seal.replyToSender(ctx, msg, "❌ 只有管理员可以创建游戏");
    }

    const maxPlayers = Math.max(2, Math.min(6, parseInt(cmdArgs.getArgN(1)) || 5));
    const initialScore = Math.max(10, parseInt(cmdArgs.getArgN(2)) || 100);

    const gameId = `zhajinhua_${Date.now()}`;
    const games = getCardGameData();

    games[gameId] = {
        gameId,
        gameType: "zhajinhua",           // 炸金花类型标识
        status: "waiting",
        maxPlayers,
        initialScore,
        players: [],
        seats: Array(maxPlayers).fill(null),
        deck: [],
        communityCards: [],              // 炸金花无公共牌
        pot: 0,
        currentBettor: 0,
        round: 0,
        createdAt: Date.now(),
        lastActionTime: null,
        actionTimeout: 30000
    };

    saveCardGameData(games);

    let reply = `✅ 炸金花赛创建成功！\n`;
    reply += `🆔 游戏ID: ${gameId}\n`;
    reply += `👥 容纳人数: ${maxPlayers}\n`;
    reply += `💰 初始积分: ${initialScore}\n`;
    reply += `\n加入指令: .加入炸金花 ${gameId}\n`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["创建炸金花"] = cmd_create_zhajinhua;

let cmd_join_zhajinhua = seal.ext.newCmdItemInfo();
cmd_join_zhajinhua.name = "加入炸金花";
cmd_join_zhajinhua.help = "加入炸金花赛\n.加入炸金花 [游戏ID]";
cmd_join_zhajinhua.solve = (ctx, msg, cmdArgs) => {
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    const gameId = cmdArgs.getArgN(1);
    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 请输入游戏ID\n用法: .加入炸金花 [游戏ID]");
    }

    const games = getCardGameData();
    const game = games[gameId];

    if (!game) return seal.replyToSender(ctx, msg, `❌ 游戏「${gameId}」不存在`);
    if (game.gameType !== "zhajinhua") {
        return seal.replyToSender(ctx, msg, "❌ 这不是炸金花游戏");
    }
    if (game.status !== "waiting") {
        return seal.replyToSender(ctx, msg, `❌ 游戏已开始，无法加入`);
    }
    if (game.players.length >= game.maxPlayers) {
        return seal.replyToSender(ctx, msg, `❌ 游戏人数已满(${game.maxPlayers}人)`);
    }
    if (game.players.some(p => p.name === roleName)) {
        return seal.replyToSender(ctx, msg, "❌ 你已加入此游戏");
    }

    // 找第一个空座位
    const seatIdx = game.seats.indexOf(null);
    game.seats[seatIdx] = roleName;

    game.players.push({
        name: roleName,
        seat: seatIdx,
        score: game.initialScore,
        holeCards: [],
        currentBet: 0,
        totalBet: 0,
        status: "active",
        folded: false
    });

    saveCardGameData(games);

    let reply = `✅ 已加入炸金花赛 ${gameId}\n`;
    reply += `👥 已有 ${game.players.length}/${game.maxPlayers} 人\n`;
    reply += `💰 你的积分: ${game.initialScore}\n`;
    reply += `\n人满后请开始: .开始炸金花`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["加入炸金花"] = cmd_join_zhajinhua;

let cmd_start_zhajinhua = seal.ext.newCmdItemInfo();
cmd_start_zhajinhua.name = "开始炸金花";
cmd_start_zhajinhua.help = "开始炸金花赛（需要4人以上）\n.开始炸金花 [游戏ID]";
cmd_start_zhajinhua.solve = (ctx, msg, cmdArgs) => {
    const games = getCardGameData();

    // 查找该玩家所在的炸金花游戏
    const roleName = getRoleName(ctx, msg);
    if (!roleName) return seal.replyToSender(ctx, msg, "❌ 请先创建角色。");

    let gameId = cmdArgs.getArgN(1);
    if (!gameId) {
        // 如果没有提供gameId，找该玩家所在的炸金花游戏
        gameId = Object.keys(games).find(id =>
            games[id].gameType === "zhajinhua" &&
            games[id].status === "waiting" &&
            games[id].players.some(p => p.name === roleName)
        );
    }

    if (!gameId) {
        return seal.replyToSender(ctx, msg, "❌ 游戏未找到或你未加入");
    }

    const game = games[gameId];

    if (game.status !== "waiting") {
        return seal.replyToSender(ctx, msg, "❌ 游戏已开始");
    }

    if (game.players.length < 2) {
        return seal.replyToSender(ctx, msg, `❌ 至少需要2人才能开始（当前${game.players.length}人）`);
    }

    // 重新初始化游戏
    game.status = "dealing";
    game.deck = createDeck();
    shuffleDeck(game.deck);

    // 为每个玩家发3张底牌
    for (let i = 0; i < game.players.length; i++) {
        game.players[i].holeCards = [];
        for (let j = 0; j < 3; j++) {
            game.players[i].holeCards.push(game.deck.pop());
        }
        game.players[i].status = "active";
        game.players[i].folded = false;
        game.players[i].currentBet = 0;
        game.players[i].totalBet = 0;
    }

    game.pot = 0;
    game.currentBettor = 0;
    game.round = 0;
    game.status = "playing";

    saveCardGameData(games);

    // 显示公开游戏信息
    let gameMsg = `🎴 炸金花赛开始！\n`;
    gameMsg += `🆔 ID: ${gameId}\n`;
    gameMsg += `────────────\n`;
    gameMsg += `👥 玩家名单：\n`;

    for (let i = 0; i < game.players.length; i++) {
        gameMsg += `  座位${i + 1}️⃣: ${game.players[i].name} - 💰${game.players[i].score}\n`;
    }

    gameMsg += `\n💰 底池: ${game.pot}\n`;
    gameMsg += `⏱️ 30秒内未操作将自动弃牌\n`;

    seal.replyToSender(ctx, msg, gameMsg);

    // 给每个玩家发私聊底牌
    for (const player of game.players) {
        const cardMsg = `🎴 你的底牌：\n${cardsToString(player.holeCards)}`;
        sendToPrivateGroup(ctx, ctx.endPoint, msg.platform, player.name, cardMsg);
    }

    // 轮到第一个玩家
    nextBettorZhajinhua(game, games, gameId, ctx);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始炸金花"] = cmd_start_zhajinhua;

// 炸金花专用的下一个投注者函数
function nextBettorZhajinhua(game, games, gameId, ctx) {
    const activePlayers = game.players.filter(p => !p.folded && p.status === "active");

    if (activePlayers.length <= 1) {
        // 游戏结束 - 只有一个玩家未弃牌
        endRoundZhajinhua(game, games, gameId, ctx);
        return;
    }

    // 找下一个未弃牌的玩家
    let nextIdx = (game.currentBettor + 1) % game.players.length;
    let attempts = 0;
    while (game.players[nextIdx].folded && attempts < game.players.length) {
        nextIdx = (nextIdx + 1) % game.players.length;
        attempts++;
    }

    game.currentBettor = nextIdx;
    const nextPlayer = game.players[game.currentBettor];

    if (nextPlayer.folded) {
        nextBettorZhajinhua(game, games, gameId, ctx);
        return;
    }

    // 记录操作开始时间
    game.lastActionTime = Date.now();

    saveCardGameData(games);

    // 艾特下一个玩家
    if (ctx) {
        let actionMsg = `\n💬 【机器人主持】\n`;
        actionMsg += `@${nextPlayer.name} 现在轮到你了！\n`;
        actionMsg += `────────────\n`;
        actionMsg += `座位: ${nextPlayer.seat + 1}\n`;
        actionMsg += `你的积分: ${nextPlayer.score}\n`;
        actionMsg += `当前下注额: 0\n`;
        actionMsg += `底池: ${game.pot}\n`;
        actionMsg += `────────────\n`;
        actionMsg += `⏱️ 30秒内未操作将自动弃牌\n`;
        actionMsg += `\n请选择下列之一：\n`;
        actionMsg += `  .跟注          跟当前下注额\n`;
        actionMsg += `  .弃牌          放弃本轮\n`;
        actionMsg += `  .加注 [数额]   加注到指定积分\n`;
        actionMsg += `  .全押          投入所有积分\n`;

        seal.replyToSender(ctx, ctx.message, actionMsg);
    }
}

// 炸金花专用的摊牌函数
function endRoundZhajinhua(game, games, gameId, ctx) {
    const activePlayers = game.players.filter(p => !p.folded && p.status === "active");

    let resultMsg = `\n🏁 【摊牌阶段】\n`;
    resultMsg += `────────────\n`;

    // 显示所有玩家的牌
    const evaluations = [];
    for (const player of game.players) {
        if (player.folded) {
            resultMsg += `${player.name}: 已弃牌 ❌\n`;
        } else {
            const eval_result = evaluateThreeCards(player.holeCards);
            evaluations.push({ player, eval: eval_result });
            resultMsg += `${player.name}: ${cardsToString(player.holeCards)}\n`;
        }
    }

    resultMsg += `\n💰 底池: ${game.pot}\n`;

    if (activePlayers.length === 1) {
        // 只有一个玩家未弃牌
        const winner = activePlayers[0];
        resultMsg += `\n🏆 ${winner.name} 获胜！（其他玩家都已弃牌）\n`;
        resultMsg += `💰 赢得: ${game.pot}糖果\n`;

        winner.score += game.pot;
    } else {
        // 比牌
        evaluations.sort((a, b) => compareThreeCards(b.eval, a.eval));

        const winners = [evaluations[0]];
        for (let i = 1; i < evaluations.length; i++) {
            if (compareThreeCards(evaluations[i].eval, winners[0].eval) === 0) {
                winners.push(evaluations[i]);
            } else {
                break;
            }
        }

        if (winners.length === 1) {
            const winner = winners[0].player;
            resultMsg += `\n🏆 ${winner.name} 获胜！\n`;
            resultMsg += `💰 赢得: ${game.pot}糖果\n`;
            winner.score += game.pot;
        } else {
            // 平局分割底池
            const perWinner = Math.floor(game.pot / winners.length);
            resultMsg += `\n🤝 平局！${winners.map(w => w.player.name).join('、')} 平分底池\n`;
            resultMsg += `💰 每人获得: ${perWinner}糖果\n`;

            winners.forEach(w => {
                w.player.score += perWinner;
            });
        }
    }

    // 显示最终积分
    resultMsg += `\n📊 最终积分：\n`;
    for (const player of game.players) {
        resultMsg += `${player.name}: ${player.score}\n`;
    }

    resultMsg += `\n➡️ 继续下一局: .开始炸金花`;

    // 重置游戏状态为 waiting，准备下一局
    game.status = "waiting";
    game.pot = 0;
    game.deck = [];
    game.communityCards = [];
    for (const p of game.players) {
        p.holeCards = [];
        p.currentBet = 0;
        p.totalBet = 0;
        p.folded = false;
        p.status = "active";
    }

    game.currentBettor = 0;

    saveCardGameData(games);

    if (ctx) seal.replyToSender(ctx, ctx.message, resultMsg);
}
