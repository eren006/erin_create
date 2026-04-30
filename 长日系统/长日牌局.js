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
        createdAt: Date.now()
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

    saveCardGameData(games);

    // 发送开始消息
    let startMsg = `🎴 纸牌竞技赛正式开始！\n`;
    startMsg += `════════════════════\n`;
    startMsg += `👥 参赛玩家（${game.players.length}人）:\n`;
    game.players.forEach((p, i) => {
        startMsg += `  ${i+1}. ${p.name} - ${p.score}积分\n`;
    });
    startMsg += `════════════════════\n`;
    startMsg += `📨 底牌已发送给各位玩家（私聊查看）\n`;
    startMsg += `⏳ 等待小盲位玩家操作...\n`;

    seal.replyToSender(ctx, msg, startMsg);

    // 分别给每个玩家私信发底牌
    game.players.forEach((player, idx) => {
        const main = getMainExt();
        if (main) {
            try {
                const a_private = JSON.parse(main.storageGet("a_private_group") || "{}");
                const platform = Object.keys(a_private).find(plat =>
                    a_private[plat]?.[player.name]?.[0]
                );

                if (platform && a_private[platform]?.[player.name]) {
                    const uid = a_private[platform][player.name][0];
                    const groupId = a_private[platform][player.name][1];

                    let cardMsg = `🎴 你的底牌:\n`;
                    cardMsg += `${cardsToString(player.holeCards)}\n`;
                    cardMsg += `\n你的积分: ${player.score}\n`;
                    cardMsg += `座位: ${player.seat + 1}\n`;
                    cardMsg += `\n⏳ 等待游戏继续...`;

                    // 这里需要通过seal.ext的消息系统发送
                    // 实现方式取决于你的seal框架版本
                    console.log(`[私信${player.name}]: ${cardMsg}`);
                }
            } catch (e) {
                console.error(`发牌失败: ${e.message}`);
            }
        }
    });

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

    const needToBet = currentBettingPlayer.currentBet - player.currentBet;
    if (needToBet > player.score) {
        return seal.replyToSender(ctx, msg, `❌ 你的积分不足，只能全押 .全押`);
    }

    // 执行跟注
    player.currentBet += needToBet;
    player.score -= needToBet;
    game.pot += needToBet;

    seal.replyToSender(ctx, msg, `✅ 你跟注了 ${needToBet} 积分\n💰 底池: ${game.pot}`);

    // 轮到下一个玩家
    nextBettor(game, games, gameId);

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

    player.folded = true;
    player.status = "folded";

    seal.replyToSender(ctx, msg, `⚠️ 你已弃牌，退出本轮竞争`);

    nextBettor(game, games, gameId);

    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["弃牌"] = cmd_fold;

// 下一个投注者
function nextBettor(game, games, gameId) {
    const activePlayers = game.players.filter(p => !p.folded && p.status === "active");

    if (activePlayers.length <= 1) {
        // 游戏结束
        endRound(game, games, gameId);
        return;
    }

    game.currentBettor = (game.currentBettor + 1) % game.players.length;
    const nextPlayer = game.players[game.currentBettor];

    if (nextPlayer.folded) {
        nextBettor(game, games, gameId);
        return;
    }

    saveCardGameData(games);
}

function endRound(game, games, gameId) {
    const activePlayers = game.players.filter(p => !p.folded);

    if (activePlayers.length === 1) {
        // 只剩一个人，他赢
        const winner = activePlayers[0];
        winner.score += game.pot;

        let msg = `🏆 ${winner.name} 赢得本轮！\n`;
        msg += `获得积分: ${game.pot}\n`;
        msg += `总积分: ${winner.score}`;

        console.log(msg);
        game.status = "ended";
        saveCardGameData(games);
        return;
    }

    // 多个人存活，显示公牌进行比牌
    if (game.round < 3) {
        dealCommunityCards(game, games, gameId);
    } else {
        // 河牌已出，进行摊牌
        showdown(game, games, gameId);
    }
}

function dealCommunityCards(game, games, gameId) {
    const stages = ["Flop（翻牌）", "Turn（转牌）", "River（河牌）"];
    const stageCounts = [3, 1, 1];

    for (let i = 0; i < stageCounts[game.round]; i++) {
        game.communityCards.push(game.deck.pop());
    }

    game.round++;

    let msg = `\n🎴 ${stages[game.round - 1]} 已出现\n`;
    msg += `公共牌: ${cardsToString(game.communityCards)}\n`;
    msg += `底池: ${game.pot}`;

    console.log(msg);

    // 重置下注
    game.players.forEach(p => p.currentBet = 0);
    game.currentBettor = 0;
    game.pot += game.players[0].currentBet; // 小盲位先下注

    saveCardGameData(games);
}

function showdown(game, games, gameId) {
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

    let resultMsg = `\n🏆 摊牌结果:\n`;
    winners.forEach(winner => {
        winner.score += winnerShare;
        resultMsg += `${winner.name} 获胜 +${winnerShare} 积分\n`;
    });

    console.log(resultMsg);
    game.status = "ended";
    saveCardGameData(games);
}

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
