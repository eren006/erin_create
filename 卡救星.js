// ==UserScript==
// @name         卡救星 (Card Savior) - 修复版
// @author       长日将尽
// @version      3.3.1
// @description  纯文本分段版，修复 Object has no member 'makeMessageArticleView' 报错。
// @timestamp    1742205760
// @license      MIT
// ==/UserScript//

let ext = seal.ext.find('card_savior');
if (!ext) {
    ext = seal.ext.new('card_savior', '长日将尽', '3.3.1');
    seal.ext.register(ext);
}

const STORAGE_KEY = 'card_savior_fixed_data';
const VALID_TYPES = ['板写', '溶图', '溶写', '其他'];

// ======================== 工具函数 ========================

function getData() {
    let raw = ext.storageGet(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
}

function saveData(data) {
    ext.storageSet(STORAGE_KEY, JSON.stringify(data));
}

function getDaysDiff(dateStr) {
    const target = new Date(dateStr);
    const now = new Date();
    now.setHours(0, 0, 0, 0); 
    const diffTime = target - now;
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

function formatTime(timestamp) {
    if (!timestamp) return '尚未下单';
    const d = new Date(timestamp);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`;
}

// ======================== 指令模块 ========================

// 1. 录入卡片
let cmdAdd = seal.ext.newCmdItemInfo();
cmdAdd.name = '录入卡片';
cmdAdd.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let date = cmdArgs.getArgN(2);
    let num = parseInt(cmdArgs.getArgN(3));

    if (!name || !date || isNaN(num)) {
        seal.replyToSender(ctx, msg, ".录入卡片 <名称> <日期:YYYY-MM-DD> <数量>");
        return seal.ext.newCmdExecuteResult(true);
    }

    let data = getData();
    let uid = msg.sender.userId;
    if (!data[uid]) data[uid] = {};

    if (data[uid][name]) {
        seal.replyToSender(ctx, msg, `❌ 名称「${name}」已存在。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    data[uid][name] = {
        name: name, expiry: date, quantity: num,
        price: 0, type: '其他', orderGroup: msg.groupId || '',
        lastOrder: null, reminded: []
    };

    saveData(data);
    seal.replyToSender(ctx, msg, `✨ 录入成功\n📌 名称：${name}\n⏳ 到期：${date}\n📦 库存：${num}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['录入卡片'] = cmdAdd;

// 2. 修改卡片
let cmdMod = seal.ext.newCmdItemInfo();
cmdMod.name = '修改卡片';
cmdMod.solve = (ctx, msg, cmdArgs) => {
    let oldName = cmdArgs.getArgN(1);
    let attr = cmdArgs.getArgN(2);
    let value = cmdArgs.getArgN(3);

    let data = getData();
    let userCards = data[msg.sender.userId];

    if (!userCards || !userCards[oldName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到卡片「${oldName}」`);
        return seal.ext.newCmdExecuteResult(true);
    }

    if (attr === '名称') {
        if (userCards[value]) {
            seal.replyToSender(ctx, msg, "❌ 新名称已被占用");
            return seal.ext.newCmdExecuteResult(true);
        }
        userCards[value] = userCards[oldName];
        userCards[value].name = value;
        delete userCards[oldName];
    } else {
        switch (attr) {
            case '数量': userCards[oldName].quantity = parseInt(value); break;
            case '价格': userCards[oldName].price = parseFloat(value); break;
            case '群号': userCards[oldName].orderGroup = value; break;
            case '类型':
                if (!VALID_TYPES.includes(value)) {
                    seal.replyToSender(ctx, msg, `❌ 可选类型：${VALID_TYPES.join('/')}`);
                    return seal.ext.newCmdExecuteResult(true);
                }
                userCards[oldName].type = value;
                break;
            default:
                seal.replyToSender(ctx, msg, "❌ 属性可选：名称/数量/价格/类型/群号");
                return seal.ext.newCmdExecuteResult(true);
        }
    }
    saveData(data);
    seal.replyToSender(ctx, msg, `✅ 已修改「${oldName}」的 ${attr}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['修改卡片'] = cmdMod;

// 3. 已下单
let cmdOrder = seal.ext.newCmdItemInfo();
cmdOrder.name = '已下单';
cmdOrder.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let count = parseInt(cmdArgs.getArgN(2)) || 1;
    let data = getData();
    let card = data[msg.sender.userId]?.[name];
    if (!card) return seal.replyToSender(ctx, msg, "❌ 卡片不存在");

    card.quantity -= count;
    card.lastOrder = new Date().getTime();
    saveData(data);
    seal.replyToSender(ctx, msg, `📉 消耗成功\n📌 名称：${name}\n📦 剩余：${card.quantity}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['已下单'] = cmdOrder;

// 4. 删除卡片
let cmdDel = seal.ext.newCmdItemInfo();
cmdDel.name = '删除卡片';
cmdDel.solve = (ctx, msg, cmdArgs) => {
    let name = cmdArgs.getArgN(1);
    let data = getData();
    if (data[msg.sender.userId]?.[name]) {
        delete data[msg.sender.userId][name];
        saveData(data);
        seal.replyToSender(ctx, msg, `🗑️ 已删除：${name}`);
    } else {
        seal.replyToSender(ctx, msg, "❌ 未找到该卡片");
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['删除卡片'] = cmdDel;

// 5. 卡片列表 (纯文本分段核心逻辑)
let cmdList = seal.ext.newCmdItemInfo();
cmdList.name = '卡片列表';
cmdList.solve = (ctx, msg, cmdArgs) => {
    let data = getData();
    let userCards = data[msg.sender.userId];

    if (!userCards || Object.keys(userCards).length === 0) {
        seal.replyToSender(ctx, msg, "📭 卡包空空如也。");
        return seal.ext.newCmdExecuteResult(true);
    }

    let cardNames = Object.keys(userCards);
    let total = cardNames.length;
    
    // 发送页眉
    seal.replyToSender(ctx, msg, `🛡️ 【卡片救星 · 资产总览】\n共计 ${total} 张卡片，正在分段展示：`);

    let text = "";
    let count = 0;

    for (let i = 0; i < total; i++) {
        let card = userCards[cardNames[i]];
        let days = getDaysDiff(card.expiry);
        let status = days > 0 ? `剩 ${days} 天` : "⚠️ 已过期";

        text += `📌 【${card.name}】 (${card.type})\n`;
        text += `⏳ 状态：${status} | 📦 库存：${card.quantity}\n`;
        text += `💰 价格：${card.price} | 🕓 上次：${formatTime(card.lastOrder)}\n`;
        text += "————————————\n";

        count++;

        // 每 5 张发送一次，防止消息过长
        if (count >= 5 || i === total - 1) {
            seal.replyToSender(ctx, msg, text.trim());
            text = "";
            count = 0;
        }
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['卡片列表'] = cmdList;

// ======================== 自动预警模块 ========================
function runReminder() {
    let data = getData();
    let modified = false;
    for (let uid in data) {
        for (let name in data[uid]) {
            let card = data[uid][name];
            let days = getDaysDiff(card.expiry);
            let milestones = [10, 5, 3]; 
            
            for (let m of milestones) {
                if (days === m && !card.reminded.includes(m)) {
                    let text = `📢 【过期预警】\n您的「${name}」还有 ${days} 天就要到期了。\n当前库存：${card.quantity}\n请记得及时使用。`;
                    let eps = seal.getEndPoints();
                    if (eps.length > 0) {
                        let fakeMsg = seal.newMessage();
                        if (card.orderGroup && (card.orderGroup.includes('Group') || card.orderGroup.includes('-'))) {
                            fakeMsg.groupId = card.orderGroup;
                            fakeMsg.messageType = 'group';
                        } else {
                            fakeMsg.sender.userId = uid;
                            fakeMsg.messageType = 'private';
                        }
                        let targetCtx = seal.createTempCtx(eps[0], fakeMsg);
                        seal.replyToSender(targetCtx, fakeMsg, text);
                    }
                    card.reminded.push(m);
                    modified = true;
                }
            }
        }
    }
    if (modified) saveData(data);
    setTimeout(runReminder, 6 * 60 * 60 * 1000); 
}
setTimeout(runReminder, 20000);