"use strict";
// ==UserScript==
// @name         喝酒游戏（醉酒名单版）
// @author       长日将尽
// @version      4.4.0
// @description  玩家醉酒后加入醉酒名单，管理员手动结束游戏并展示结果
// @timestamp    1710027890
// @license      Apache-2
// ==/UserScript==

exports.__esModule = true;

// 查找/创建扩展
var ext = seal.ext.find('喝酒v1');
if (!ext) {
    ext = seal.ext.new('喝酒v1', '长日将尽', '1.1.1');
    seal.ext.register(ext);
}

// 每个群独立一份游戏状态
var gameStates = {};

function getState(ctx) {
    var gid = ctx.group.groupId;
    if (!gameStates[gid]) {
        gameStates[gid] = {
            players: {},
            group: [],
            drunkPlayers: [],
            drinkedPositions: [],
            gameActive: false,
            drunkThreshold: 500
        };
    }
    return gameStates[gid];
}

// 每种酒的类型和子种类
const alcoholTypes = [
    { type: '啤酒', subType: '拉格', value: 10, description: '一种清爽的淡色啤酒，适合夏天畅饮。' },
    { type: '啤酒', subType: '艾尔', value: 10, description: '一款稍微浓烈的啤酒，味道偏重。' },
    { type: '啤酒', subType: '白啤', value: 15, description: '一种浓郁的啤酒，口感更加顺滑，适合搭配小吃。' },
    { type: '啤酒', subType: '帝国 Stout', value: 20, description: '深色浓烈的啤酒，带有咖啡和巧克力的香气。' },
    { type: '啤酒', subType: '小麦啤酒', value: 15, description: '使用小麦酿造，口感轻盈，带有香气。' },
    { type: '啤酒', subType: '苦啤', value: 18, description: '非常苦的啤酒，适合喜欢浓烈味道的饮酒者。' },

    { type: '红酒', subType: '赤霞珠', value: 20, description: '经典的红酒，带有浓郁的果香和单宁味。' },
    { type: '红酒', subType: '梅洛', value: 20, description: '温和口感，适合搭配大多数食物。' },
    { type: '红酒', subType: '黑皮诺', value: 25, description: '柔顺的红酒，果香浓郁，口感极为顺滑。' },
    { type: '红酒', subType: '桑娇维塞', value: 22, description: '带有酸度和草本香气的红酒，适合搭配烧烤。' },
    { type: '红酒', subType: '意大利巴罗洛', value: 30, description: '来自意大利的高端红酒，带有坚果和玫瑰的香气。' },

    { type: '白葡萄酒', subType: '冰酒', value: 70, description: '甜美的酒，带有浓郁的果香，适合餐后享用。' },
    { type: '白葡萄酒', subType: '霞多丽', value: 55, description: '具有丰富的果香和微妙的橡木味，口感圆润。' },
    { type: '白葡萄酒', subType: '长相思', value: 50, description: '清新、爽口，带有柑橘和青草的香气。' },
    { type: '白葡萄酒', subType: '雷司令', value: 60, description: '带有较强的果香，适合与辛辣食物搭配。' },
    { type: '白葡萄酒', subType: '灰比诺', value: 50, description: '带有蜂蜜和苹果的香气，口感清新。' },

    { type: '烈酒', subType: '伏特加 - 斯托尔', value: 40, description: '无色无味的烈酒，适合与其他饮品调配，口感干净且清爽。' },
    { type: '烈酒', subType: '伏特加 - 绝对伏特加', value: 45, description: '瑞典生产的高端伏特加，口感纯净，适合调制鸡尾酒。' },
    { type: '烈酒', subType: '威士忌 - 苏格兰单一麦芽', value: 50, description: '由单一麦芽酿造，带有浓烈的烟熏味和木桶味。' },
    { type: '烈酒', subType: '威士忌 - 美国波本', value: 45, description: '甜味浓郁，带有香草、焦糖和橡木的香气。' },
    { type: '烈酒', subType: '威士忌 - 加拿大混合', value: 38, description: '更加顺滑，香气优雅，适合饮用或调制鸡尾酒。' },
    { type: '烈酒', subType: '龙舌兰 - 白龙舌兰', value: 35, description: '透明、浓烈且带有辛辣感的酒，可直接饮用或调制鸡尾酒。' },
    { type: '烈酒', subType: '龙舌兰 - 金龙舌兰', value: 40, description: '金黄色的龙舌兰，经过橡木桶熟成，味道更加柔和且富有层次感。' },
    { type: '烈酒', subType: '龙舌兰 - 额尔多斯', value: 42, description: '顶级龙舌兰，口感极其细腻，适合纯饮。' },
    { type: '烈酒', subType: '朗姆酒 - 白朗姆', value: 35, description: '无色的朗姆酒，口感清爽，适合调配鸡尾酒。' },
    { type: '烈酒', subType: '朗姆酒 - 黑朗姆', value: 45, description: '深色朗姆酒，带有浓烈的焦糖和香料味。' },
    { type: '烈酒', subType: '朗姆酒 - 椰子朗姆', value: 40, description: '带有浓郁椰子香气的朗姆酒，适合制作热带鸡尾酒。' },

    { type: '白酒', subType: '茅台', value: 50, description: '浓烈的中国白酒，具有深厚的酒香和辛辣的味道。' },
    { type: '白酒', subType: '五粮液', value: 45, description: '中国传统白酒，以五种粮食酿成，风味独特。' },
    { type: '白酒', subType: '泸州老窖', value: 48, description: '带有酒香和果香的中国传统白酒，口感顺滑。' },

    { type: '鸡尾酒', subType: '马提尼', value: 30, description: '经典鸡尾酒，通常用金酒和苦艾酒调制而成。' },
    { type: '鸡尾酒', subType: '长岛冰茶', value: 25, description: '口感清新，甜中带点酸，适合聚会时饮用。' },
    { type: '鸡尾酒', subType: '血腥玛丽', value: 30, description: '含有番茄汁、伏特加、香料等，味道辛辣、酸爽。' },
    { type: '鸡尾酒', subType: '龙舌兰日出', value: 28, description: '由龙舌兰、橙汁和石榴糖浆调制而成，色彩鲜艳，口感甘甜。' },
    { type: '鸡尾酒', subType: '老式鸡尾酒', value: 35, description: '经典的威士忌鸡尾酒，加入糖和苦精，味道浓郁。' },

    { type: '香槟', subType: '干型', value: 30, description: '酒体清新，适合庆祝场合，味道略带辛辣。' },
    { type: '香槟', subType: '甜型', value: 35, description: '带有甜味，口感柔和，适合搭配甜点。' },
    { type: '香槟', subType: '年份香槟', value: 60, description: '高端香槟，年份较长，带有更加丰富的香气和口感。' },

    { type: '清酒', subType: '吟酿', value: 25, description: '日本传统的米酒，味道柔和，适合品尝。' },
    { type: '清酒', subType: '大吟酿', value: 40, description: '最高级的清酒，口感丰富，带有花香和米香。' },
    { type: '清酒', subType: '普通清酒', value: 15, description: '传统的日本清酒，适合餐桌上享用。' },

    { type: '果酒', subType: '苹果酒', value: 12, description: '由苹果酿造的果酒，口感酸甜，适合开胃。' },
    { type: '果酒', subType: '樱桃酒', value: 18, description: '由樱桃酿成的果酒，带有浓郁的果香和甜美的味道。' },
    { type: '果酒', subType: '蓝莓酒', value: 20, description: '使用蓝莓酿成的果酒，带有蓝莓的浓郁果香。' },

    { type: '无酒精', subType: '橙汁', value: -10, description: '富含维生素C，清爽又健康的果汁。' },
    { type: '无酒精', subType: '白水', value: -5, description: '最基础的饮品，解渴的最佳选择。' },
    { type: '无酒精', subType: '苏打水', value: -8, description: '气泡丰富的饮料，清爽解渴。' },
    { type: '无酒精', subType: '咖啡', value: -5, description: '苦香醇厚的咖啡，提神醒脑。' },
    { type: '无酒精', subType: '抹茶拿铁', value: -7, description: '融合了抹茶和牛奶的饮品，口感顺滑。' },
    { type: '无酒精', subType: '椰子水', value: -6, description: '天然的电解质饮品，适合补充水分。' },
    { type: '无酒精', subType: '奶昔', value: -9, description: '甜美的奶昔，通常搭配巧克力、香草或草莓口味。' },
    { type: '无酒精', subType: '热巧克力', value: -6, description: '香浓的热巧克力，适合寒冷天气饮用。' },
    { type: '无酒精', subType: '蜂蜜柠檬水', value: -7, description: '富含维生素C的健康饮品，甜酸可口。' },
    { type: '无酒精', subType: '冰红茶', value: -8, description: '清凉的冰红茶，略带甜味，适合解暑。' }
];

var cmd_joinGame = seal.ext.newCmdItemInfo();
cmd_joinGame.name = '加入喝酒游戏';
cmd_joinGame.help = '加入喝酒游戏，格式：.加入喝酒游戏';
cmd_joinGame.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏已经开始，无法加入！");
        return seal.ext.newCmdExecuteResult(true);
    }

    let uid = msg.sender.userId;
    let nickname = msg.sender.nickname;

    if (s.players[uid]) {
        seal.replyToSender(ctx, msg, "❌ 你已经加入过游戏了！");
        return seal.ext.newCmdExecuteResult(true);
    }

    let isDrunk = s.drunkPlayers.some(p => p.userId === uid);
    if (isDrunk) {
        seal.replyToSender(ctx, msg, "❌ 你已经在醉酒名单中，无法再次加入！");
        return seal.ext.newCmdExecuteResult(true);
    }

    s.players[uid] = {
        nickname: nickname,
        drunkValue: 0,
        userId: uid,
        joinTime: Date.now()
    };

    seal.replyToSender(ctx, msg, `✅ ${nickname} 成功加入喝酒游戏！当前玩家数：${Object.keys(s.players).length}`);
    return seal.ext.newCmdExecuteResult(true);
};

// 开始喝酒游戏指令
var cmd_startGame = seal.ext.newCmdItemInfo();
cmd_startGame.name = '开始喝酒游戏';
cmd_startGame.help = '开始喝酒游戏，格式：.开始喝酒游戏';
cmd_startGame.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏已经开始！");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (Object.keys(s.players).length < 1) {
        seal.replyToSender(ctx, msg, "❌ 必须至少有1个玩家才能开始喝酒游戏！");
        return seal.ext.newCmdExecuteResult(true);
    }

    s.gameActive = true;
    seal.replyToSender(ctx, msg, `🎮 喝酒游戏开始！当前玩家：${Object.keys(s.players).length}人\n醉酒阈值：${s.drunkThreshold}点`);
    return seal.ext.newCmdExecuteResult(true);
};

// 上酒指令
var cmd_addAlcohol = seal.ext.newCmdItemInfo();
cmd_addAlcohol.name = '上酒';
cmd_addAlcohol.help = '上酒并展示酒池，格式：.上酒';
cmd_addAlcohol.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (!s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏未开始！请先使用 .开始喝酒游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (Object.keys(s.players).length === 0) {
        seal.replyToSender(ctx, msg, "❌ 所有玩家都已醉酒！游戏结束！");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (s.drinkedPositions.includes(false)) {
        seal.replyToSender(ctx, msg, "❌ 还有未喝完的酒，不能再次上酒！");
        return seal.ext.newCmdExecuteResult(true);
    }

    s.group = [];
    s.drinkedPositions = [];

    let tempPool = [];
    for (let i = 0; i < 24; i++) {
        const randomDrink = alcoholTypes[Math.floor(Math.random() * alcoholTypes.length)];
        tempPool.push(randomDrink);
    }

    let displayPool = [...tempPool].sort(() => Math.random() - 0.5);

    s.group = [...tempPool];
    s.drinkedPositions = new Array(24).fill(false);

    let drinkInfo = '🥂 新酒池已上桌！\n';
    drinkInfo += '🔸 提示：使用 .喝酒 位置 来喝酒\n';
    drinkInfo += '🔸 使用 .可喝酒 查看剩余的酒\n';
    drinkInfo += '🔸 醉酒阈值：' + s.drunkThreshold + '点\n\n';

    let byType = {};
    displayPool.forEach(drink => {
        if (!byType[drink.type]) byType[drink.type] = [];
        byType[drink.type].push(drink);
    });

    for (let type in byType) {
        drinkInfo += `【${type}】\n`;
        byType[type].forEach(drink => {
            drinkInfo += `  🔹 ${drink.subType} - ${drink.description} (${drink.value > 0 ? '+' : ''}${drink.value}点)\n`;
        });
    }

    seal.replyToSender(ctx, msg, drinkInfo);
    return seal.ext.newCmdExecuteResult(true);
};

// 喝酒指令
var cmd_drink = seal.ext.newCmdItemInfo();
cmd_drink.name = '喝酒';
cmd_drink.help = '喝酒并增加醉酒值，格式：.喝酒 位置';
cmd_drink.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (!s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏未开始！");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (Object.keys(s.players).length === 0) {
        seal.replyToSender(ctx, msg, "❌ 所有玩家都已醉酒！游戏结束！");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (s.group.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 还没有上酒！请先使用 .上酒");
        return seal.ext.newCmdExecuteResult(true);
    }

    var position = Number(argv.getArgN(1)) - 1;

    if (typeof position !== 'number' || !Number.isInteger(position) || position < 0 || position >= 24) {
        seal.replyToSender(ctx, msg, "❌ 无效的酒杯位置！位置必须是 1 到 24 之间的整数。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (s.drinkedPositions[position]) {
        seal.replyToSender(ctx, msg, "❌ 这个酒已经被喝过了，请选择其他酒！");
        return seal.ext.newCmdExecuteResult(true);
    }

    var uid = msg.sender.userId;
    var player = s.players[uid];
    if (!player) {
        let isDrunk = s.drunkPlayers.some(p => p.userId === uid);
        if (isDrunk) {
            seal.replyToSender(ctx, msg, "❌ 你已经喝醉了，不能再喝酒了！");
        } else {
            seal.replyToSender(ctx, msg, "❌ 你还没有加入喝酒游戏！");
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    var selectedDrink = s.group[position];
    player.drunkValue += selectedDrink.value;
    s.drinkedPositions[position] = true;

    let message = `🍻 ${player.nickname} 喝了 ${selectedDrink.type}(${selectedDrink.subType})\n`;
    message += `📝 ${selectedDrink.description}\n`;
    message += `📊 醉酒值 ${selectedDrink.value > 0 ? '+' : ''}${selectedDrink.value}，当前：${player.drunkValue}/${s.drunkThreshold}`;

    if (player.drunkValue >= s.drunkThreshold) {
        s.drunkPlayers.push({
            userId: player.userId,
            nickname: player.nickname,
            drunkValue: player.drunkValue,
            drunkTime: Date.now()
        });

        delete s.players[uid];

        message += `\n\n💀 ${player.nickname} 喝醉了！已加入醉酒名单。\n`;
        message += `剩余玩家：${Object.keys(s.players).length}人`;

        if (Object.keys(s.players).length === 0) {
            message += `\n\n🎉 所有玩家都喝醉了！游戏自然结束！\n`;
            message += `请使用 .结束游戏 查看最终结果`;
        }
    }

    seal.replyToSender(ctx, msg, message);

    if (s.drinkedPositions.every(pos => pos === true)) {
        seal.replyToSender(ctx, msg, "🍶 所有酒都喝完了！请使用 .上酒 继续游戏！");
    }

    return seal.ext.newCmdExecuteResult(true);
};

// 查看未喝的酒（只显示位置，不暴露具体酒的信息）
var cmd_viewAvailable = seal.ext.newCmdItemInfo();
cmd_viewAvailable.name = '可喝酒';
cmd_viewAvailable.help = '查看当前酒池中还未被喝的酒，格式：.可喝酒';
cmd_viewAvailable.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (!s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏未开始！");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (s.group.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 还没有上酒！请先使用 .上酒");
        return seal.ext.newCmdExecuteResult(true);
    }

    let availablePositions = [];
    for (let i = 0; i < s.drinkedPositions.length; i++) {
        if (!s.drinkedPositions[i]) {
            availablePositions.push(i + 1);
        }
    }

    if (availablePositions.length === 0) {
        seal.replyToSender(ctx, msg, "✅ 所有酒都已喝完！请使用 .上酒 开启新回合。");
    } else {
        let reply = `🥂 当前可喝的位置（共 ${availablePositions.length} 杯）：\n`;

        let rows = [];
        for (let i = 0; i < availablePositions.length; i += 6) {
            let rowPositions = availablePositions.slice(i, i + 6);
            let rowText = rowPositions.map(pos => {
                if (pos < 10) return `  ${pos}`;
                return `${pos}`;
            }).join('  ');
            rows.push(rowText);
        }

        reply += rows.join('\n');
        reply += `\n\n📌 使用命令：.喝酒 [位置号]`;
        reply += `\n例如：.喝酒 ${availablePositions[0]}`;

        seal.replyToSender(ctx, msg, reply);
    }

    return seal.ext.newCmdExecuteResult(true);
};

// 查看当前状态
var cmd_viewStatus = seal.ext.newCmdItemInfo();
cmd_viewStatus.name = '游戏状态';
cmd_viewStatus.help = '查看当前游戏状态，格式：.游戏状态';
cmd_viewStatus.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    let reply = '🎮 喝酒游戏状态\n';
    reply += '================\n\n';

    reply += `🏃 幸存玩家：${Object.keys(s.players).length}人\n`;
    if (Object.keys(s.players).length > 0) {
        for (let uid in s.players) {
            let player = s.players[uid];
            let progress = Math.max(0, Math.min(100, Math.floor((player.drunkValue / s.drunkThreshold) * 100)));
            let progressBar = '█'.repeat(Math.floor(progress/10)) + '░'.repeat(10 - Math.floor(progress/10));
            reply += `  ${player.nickname}: ${player.drunkValue}/${s.drunkThreshold} [${progressBar}] ${progress}%\n`;
        }
    }

    reply += `\n💀 醉酒玩家：${s.drunkPlayers.length}人\n`;
    if (s.drunkPlayers.length > 0) {
        let sorted = [...s.drunkPlayers].sort((a, b) => b.drunkValue - a.drunkValue);
        sorted.forEach((player, index) => {
            reply += `  ${index + 1}. ${player.nickname}: ${player.drunkValue}点\n`;
        });
    }

    if (s.group.length > 0) {
        let remaining = s.drinkedPositions.filter(pos => !pos).length;
        reply += `\n🥂 酒池状态：${remaining}/${s.group.length} 杯剩余\n`;
    } else {
        reply += `\n🥂 酒池状态：未上酒\n`;
    }

    reply += `\n🎯 醉酒阈值：${s.drunkThreshold}点`;
    reply += `\n📊 游戏状态：${s.gameActive ? '进行中' : '未开始'}`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 结束游戏指令
var cmd_endGame = seal.ext.newCmdItemInfo();
cmd_endGame.name = '结束游戏';
cmd_endGame.help = '结束游戏并展示结果，格式：.结束游戏';
cmd_endGame.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (!s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏未开始！");
        return seal.ext.newCmdExecuteResult(true);
    }

    s.gameActive = false;

    let reply = '🎮 喝酒游戏结束！\n';
    reply += '================\n\n';

    reply += '💀 【醉酒名单】\n';
    if (s.drunkPlayers.length > 0) {
        let sortedDrunk = [...s.drunkPlayers].sort((a, b) => b.drunkValue - a.drunkValue);
        sortedDrunk.forEach((player, index) => {
            let rank = '';
            if (index === 0) rank = '🏆 ';
            else if (index === 1) rank = '🥈 ';
            else if (index === 2) rank = '🥉 ';
            reply += `${rank}${index + 1}. ${player.nickname}: ${player.drunkValue}点\n`;
        });
    } else {
        reply += '  暂无醉酒玩家\n';
    }

    reply += '\n🏃 【幸存者】\n';
    if (Object.keys(s.players).length > 0) {
        let playerArray = Object.values(s.players);
        playerArray.sort((a, b) => b.drunkValue - a.drunkValue);
        playerArray.forEach((player, index) => {
            reply += `  ${index + 1}. ${player.nickname}: ${player.drunkValue}点\n`;
        });
    } else {
        reply += '  无幸存者\n';
    }

    reply += '\n📊 【游戏统计】\n';
    reply += `  总参与玩家：${s.drunkPlayers.length + Object.keys(s.players).length}人\n`;
    reply += `  醉酒人数：${s.drunkPlayers.length}人\n`;
    reply += `  幸存人数：${Object.keys(s.players).length}人\n`;

    if (s.drunkPlayers.length > 0) {
        let highest = s.drunkPlayers.reduce((max, p) => p.drunkValue > max ? p.drunkValue : max, 0);
        let lowest = s.drunkPlayers.reduce((min, p) => p.drunkValue < min ? p.drunkValue : min, Infinity);
        reply += `  最高醉酒值：${highest}点\n`;
        reply += `  最低醉酒值：${lowest}点\n`;
    }

    reply += '\n🎉 游戏已结束，感谢参与！';
    reply += '\n使用 .加入喝酒游戏 重新开始新游戏。';

    s.players = {};
    s.group = [];
    s.drunkPlayers = [];
    s.drinkedPositions = [];

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 重置游戏指令（管理员用）
var cmd_resetGame = seal.ext.newCmdItemInfo();
cmd_resetGame.name = '重置游戏';
cmd_resetGame.help = '强制重置游戏，格式：.重置游戏';
cmd_resetGame.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    s.players = {};
    s.group = [];
    s.drunkPlayers = [];
    s.drinkedPositions = [];
    s.gameActive = false;

    seal.replyToSender(ctx, msg, "✅ 游戏已重置！可以重新开始新游戏。");
    return seal.ext.newCmdExecuteResult(true);
};

// 查看醉酒名单指令
var cmd_viewDrunkList = seal.ext.newCmdItemInfo();
cmd_viewDrunkList.name = '醉酒名单';
cmd_viewDrunkList.help = '查看当前醉酒名单，格式：.醉酒名单';
cmd_viewDrunkList.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (s.drunkPlayers.length === 0) {
        seal.replyToSender(ctx, msg, "💀 当前没有玩家醉酒。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let reply = '💀 醉酒名单\n';
    reply += '==========\n\n';

    let sorted = [...s.drunkPlayers].sort((a, b) => b.drunkValue - a.drunkValue);

    sorted.forEach((player, index) => {
        let emoji = '';
        if (player.drunkValue >= s.drunkThreshold * 1.6) emoji = '🤮 ';
        else if (player.drunkValue >= s.drunkThreshold * 1.2) emoji = '😵 ';
        else emoji = '🤢 ';

        reply += `${emoji}${index + 1}. ${player.nickname}: ${player.drunkValue}点\n`;
    });

    reply += `\n总计：${s.drunkPlayers.length}人`;

    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

// 设定醉酒阈值指令
var cmd_setThreshold = seal.ext.newCmdItemInfo();
cmd_setThreshold.name = '设定醉酒阈值';
cmd_setThreshold.help = '设定醉酒阈值，格式：.设定醉酒阈值 数值';
cmd_setThreshold.solve = function (ctx, msg, argv) {
    var s = getState(ctx);
    if (s.gameActive) {
        seal.replyToSender(ctx, msg, "❌ 游戏进行中不能修改阈值！");
        return seal.ext.newCmdExecuteResult(true);
    }

    var newThreshold = Number(argv.getArgN(1));
    if (isNaN(newThreshold) || newThreshold <= 0) {
        seal.replyToSender(ctx, msg, "❌ 请输入有效的正数阈值！");
        return seal.ext.newCmdExecuteResult(true);
    }

    s.drunkThreshold = newThreshold;
    seal.replyToSender(ctx, msg, `✅ 醉酒阈值已设置为 ${s.drunkThreshold} 点`);
    return seal.ext.newCmdExecuteResult(true);
};

// 注册指令
ext.cmdMap['加入喝酒游戏'] = cmd_joinGame;
ext.cmdMap['开始喝酒游戏'] = cmd_startGame;
ext.cmdMap['上酒'] = cmd_addAlcohol;
ext.cmdMap['喝酒'] = cmd_drink;
ext.cmdMap['可喝酒'] = cmd_viewAvailable;
ext.cmdMap['游戏状态'] = cmd_viewStatus;
ext.cmdMap['结束游戏'] = cmd_endGame;
ext.cmdMap['重置游戏'] = cmd_resetGame;
ext.cmdMap['醉酒名单'] = cmd_viewDrunkList;
ext.cmdMap['设定醉酒阈值'] = cmd_setThreshold;
