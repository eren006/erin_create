"use strict";

// ==UserScript==
// @name         假面舞会
// @author       长日将尽
// @version      1.0.0
// @description  匿名假面舞会和一些小游戏
// @license      Apache-2
// @homepageURL  https://github.com/sealdice/javascript
// ==/UserScript==

// 查找/创建扩展
var ext = seal.ext.find('假面舞会');
if (!ext) {
    ext = seal.ext["new"]('假面舞会', '长日将尽', '1.0.0');
    seal.ext.register(ext);
}

function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;

    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");

    let crExt = seal.ext.find('changri');
    if (!crExt) return false;

    try {
        let rawAdmin = crExt.storageGet("a_adminList");
        if (!rawAdmin) return false;

        let a_adminList = JSON.parse(rawAdmin);
        return a_adminList[platform] && a_adminList[platform].includes(uid);
    } catch (e) {
        return false;
    }
}

let cmd_grant_admin = seal.ext.newCmdItemInfo();
cmd_grant_admin.name = "授予假面管理员";
cmd_grant_admin.help = "。授予假面管理员 —— 管理员授权已统一由长日系统管理";

cmd_grant_admin.solve = (ctx, msg, cmdArgs) => {
  seal.replyToSender(ctx, msg, "ℹ️ 假面舞会的管理员权限已与长日系统打通，请在长日系统中使用「。授予管理员」指令授权。");
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["授予假面管理员"] = cmd_grant_admin;

const cmd_masquerade = seal.ext.newCmdItemInfo();
cmd_masquerade.name = "假面舞会";
cmd_masquerade.help = "。假面舞会 留言内容 —— 使用已注册的假面名匿名发言";

cmd_masquerade.solve = function(ctx, msg, argv) {
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const content = argv.getRestArgsFrom(1)?.trim();

  if (!content) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const alias = stored[uid];

  if (!alias) {
    seal.replyToSender(ctx, msg, `⚠️ 您尚未注册假面名，请先使用「。注册假面 假面名」`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 冷却机制
  const cooldownKey = `masquerade_cooldown_${uid}`;
  const cooldownSeconds = 30;
  const now = Math.floor(Date.now() / 1000);
  const lastUsed = parseInt(ext.storageGet(cooldownKey) || "0");

  if (now - lastUsed < cooldownSeconds) {
    const wait = cooldownSeconds - (now - lastUsed);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再发言~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  ext.storageSet(cooldownKey, now.toString());

  const groupId = `QQ-Group:1097345718`; // 请替换成假面舞会真实群号
  const fullText = `「${alias}」：\n\n${content}`;
//244765560 测试
//778136193 正式
  const outMsg = seal.newMessage();
  outMsg.messageType = "group";
  outMsg.sender = {};
  outMsg.groupId = groupId;

  const tempCtx = seal.createTempCtx(ctx.endPoint, outMsg);
  seal.replyToSender(ctx, msg, `✅ 留言已投入假面舞会。`);
  seal.replyToSender(tempCtx, outMsg, fullText);

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["假面舞会"] = cmd_masquerade;


const cmd_registerAlias = seal.ext.newCmdItemInfo();
cmd_registerAlias.name = "注册假面";
cmd_registerAlias.help = "。注册假面 假面名 —— 设定您的假面昵称，仅限一次";

cmd_registerAlias.solve = function(ctx, msg, argv) {
  const platform = msg.platform;
  const uid = msg.sender.userId; // 直接使用完整 userId
  const alias = argv.getArgN(1)?.trim();

  if (!alias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");

  if (stored[uid]) {
    seal.replyToSender(ctx, msg, `❌ 您已注册为「${stored[uid]}」，无法重复注册。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  if (Object.values(stored).includes(alias)) {
    seal.replyToSender(ctx, msg, `⚠️ 假面名「${alias}」已被他人使用，请更换一个独特的名号。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  stored[uid] = alias;
  ext.storageSet("masquerade_map", JSON.stringify(stored));

  seal.replyToSender(ctx, msg, `🎭 假面名「${alias}」注册成功，欢迎步入舞会。`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["注册假面"] = cmd_registerAlias;

const cmd_randomQuestion = seal.ext.newCmdItemInfo();
cmd_randomQuestion.name = "假面抽问";
cmd_randomQuestion.help = "。假面抽问 —— 从舞会密题中抽出一道问题，仅限每日 19:00 后使用";

cmd_randomQuestion.solve = function(ctx, msg, argv) {
  const now = new Date();
  const currentHour = now.getHours();

  // ⏰ 限定只能在18:00以后使用
  if (currentHour < 19) {
    seal.replyToSender(ctx, msg, `🕰️ 假面之问尚未揭晓，请待夜幕降临。\n⏳ 当前时间尚早，请在19:00 后再试。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const questionPool = [
    "若你能与一人独处于葡萄廊下，你希望是谁？",
    "若你今晚必须与一人接吻才能离场，你的唇会向谁靠近？",
    "你认为这里的谁会第一个死亡？",
    "谁最有可能曾暗恋一位今晚出席的人，并将这秘密埋藏多年？",
    "谁最有可能与另一位宾客私奔？",
    "若你的面具被谁亲手揭下，你会不反抗？",
    "若要你与一位宾客共同撒下一个谎，你最愿与谁并肩沉默？",
    "若你必须在祷告时直视一双眼睛，你会选谁来承受你的坦白？",
    "若你能与某人交换命运一夜，你愿意成为谁？",
    "若你醒来发现自己不小心与某人一同度过整夜，你希望是谁躺在你身旁？",
    "若你今晚能杀死一个人并永远不被揭发，你会选谁？",
    "若今晚最后有人从钟楼上坠落，你觉得会是谁推的？",
    "若有一位宾客今夜会死于情伤，而你可能是原因，你希望是谁因你而亡？",
    "若你能挑起两位宾客间的嫉妒，让他们反目成仇，你会选择哪两人？",
    "若你能设计一个意外，在舞会中令一位强者跌入丑闻的深渊，你最想针对谁？",
    "若你与某人必须一同接受审判，你最希望与谁绑在同一根绞索上？",
    "若你能将一次心跳错认成爱情，你希望是因谁而起？",
    "若你能看穿一人心底的秘密，却永远拥有另一个的身体，你愿看谁的灵魂？留谁的肉身？",
    "若你必须和一位宾客共用一个马桶盖一整晚，你选谁？（注：请想象这是惩罚，不是奖赏）",
    "若你今晚必须选一人共骑毛驴穿过市集——你愿谁与君并肩？",
    "谁最有可能在修道院藏了一头走私来的猪？",
    "谁最有可能在夜里假扮修士听人告解只为收集八卦？",
    "谁最有可能在大主教的面前念了一整首写给面包的情诗？",
    "谁最有可能不小心把忏悔写成了菜谱还抄送给主教？",
    "谁最有可能在舞会中藏了一只猫并谎称那是他转世的叔祖母？",
    "谁最有可能参加舞会只是为了偷回他上次丢的袜子？",
    "若你今夜必须选一人承担你的罪行，你会把罪名栽在谁头上？",
    "谁最有可能把祷告词改成了情诗还自己念到哭？",
    "谁最有可能把家族纹章刺在屁股上，并自称“忠诚之臀”？",
    "谁最有可能在布道时念错拉丁文，把“主在天上”说成了“鹅在井底”？",
    "若你今夜必须成为谋杀案的共犯，你希望谁是你的搭档？",
    "若你被罚在街头卖唱赎罪，你最希望谁来与你合奏？",
    "谁最有可能误把毒药喝成开胃酒，第二天还夸它口感特别？"
  ];

  const randomQuestion = questionPool[Math.floor(Math.random() * questionPool.length)];
  seal.replyToSender(ctx, msg, `🎭 假面之问：\n\n${randomQuestion}`);
  return seal.ext.newCmdExecuteResult(true);
};

//ext.cmdMap["假面抽问"] = cmd_randomQuestion;

// =========================
// 🍇 获取毒果游戏指令（全局唯一甜点名）
// =========================
const cmd_getFruit = seal.ext.newCmdItemInfo();
cmd_getFruit.name = "获取毒果";
cmd_getFruit.help = "。获取毒果 —— 获得 3 枚果实（2 毒果 + 1 真果），佛罗伦萨甜点风格，全局不重复";

cmd_getFruit.solve = function (ctx, msg) {
  const uid = msg.sender.userId; // 完整 userId
  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const alias = stored[uid];

  let inventoryMap = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");
  if (inventoryMap[alias]) {
    seal.replyToSender(ctx, msg, `🍇 你已经领取过毒果，当前库存：\n` +
      inventoryMap[alias].map(f => `· ${f.name}（${f.type}）`).join("\n"));
    return seal.ext.newCmdExecuteResult(true);
  }

  // 甜点池（扩充版）
  const fruitPool = [
  "柠檬杏仁塔","石榴蜜饼","橙花芝士卷","无花果蜂蜜派","樱桃酒浸蛋糕",
  "葡萄干蜜酥卷","草莓奶油小盏","榅桲果馅饼","覆盆子玫瑰慕斯","栗子松露球",
  "杏仁蜜梨挞","蜜渍无花果芝士杯","橄榄油柑橘蛋糕","葡萄酒炖梨派","西西里柠檬奶油卷",
  "蜂蜜苹果布丁","蓝莓迷迭香塔","杏仁橙花蛋糕","马斯卡彭樱桃杯","葡萄柚糖渍片",
  "开心果蜜橙挞","甜酒浸提拉米苏","黑莓奶油泡芙","糖渍玫瑰梨盏","杏桃果酱千层酥",
  "蜜渍橄榄杏仁卷","葡萄干朗姆蛋糕","蜂蜜无花果派","柑橘杏仁布朗尼","玫瑰荔枝慕斯",
  "香草杏仁奶冻","烤梨杏仁塔","酒渍樱桃巧克力球","无花果杏仁挞","柠檬马鞭草小蛋糕",
  "榛子覆盆子蛋糕","橄榄油葡萄干饼","焦糖苹果小塔","白葡萄酒梨子冻","百香果奶油泡芙",
  "青提杏仁布丁","红醋栗芝士慕斯","佛手柑杏仁酥","金橘蜜酱卷","香料苹果蜂蜜塔",
  "樱桃开心果奶酥塔","无花果香草奶油卷","橙酒蜜渍草莓杯","焦糖柠檬蛋白派",
  "白兰地苹果干酥饼","蜂蜜石榴奶冻盏","蓝莓薰衣草慕斯","酒渍葡萄奶油泡芙",
  "蜜渍杏仁葡萄干卷","香料梨焦糖布丁", "白桃香草慕斯盏",      
  "黑樱桃杏仁奶酥卷",   
  "覆盆子柠檬芝士塔",     
  "无花果红酒果冻杯",     
  "杏梨蜂蜜酥皮卷",     
  "百香果椰奶奶冻",     
  "桑葚玫瑰奶油派",     
  "青苹果薄荷蛋白饼",      
  "李子肉桂奶酥盏",       
  "蜜橙香草奶酪卷" 
];


  // 已用甜点名
  let usedNames = JSON.parse(ext.storageGet("a_fruit_game_usedNames") || "[]");

  // 可用甜点名
  let available = fruitPool.filter(name => !usedNames.includes(name));

  // 不足则重置
  if (available.length < 3) {
    usedNames = [];
    available = [...fruitPool];
  }

  // 随机取 3 个
  const chosenNames = [];
  for (let i = 0; i < 3; i++) {
    const idx = Math.floor(Math.random() * available.length);
    chosenNames.push(available[idx]);
    usedNames.push(available[idx]);
    available.splice(idx, 1);
  }

  // 分配 2 毒 + 1 真
  let fruits = [
    { name: chosenNames[0], type: "毒果" },
    { name: chosenNames[1], type: "毒果" },
    { name: chosenNames[2], type: "真果" }
  ].sort(() => Math.random() - 0.5);

  inventoryMap[alias] = fruits;
  ext.storageSet("a_fruit_game_inventory", JSON.stringify(inventoryMap));
  ext.storageSet("a_fruit_game_usedNames", JSON.stringify(usedNames));

  seal.replyToSender(ctx, msg,
    `🎁 你获得了三枚果实：\n${fruits.map(f => `· ${f.name}（${f.type}）`).join("\n")}\n\n` +
    `🍷 有些甜美，有些致命——你能分辨吗？`
  );

  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["获取毒果"] = cmd_getFruit;

// ========== 赠予果实 ==========
let cmd_give_fruit = seal.ext.newCmdItemInfo();
cmd_give_fruit.name = "赠予果实";
cmd_give_fruit.help = "。赠予果实 赠送者 接受者 果实名字 —— 将赠送者的指定果实转给接受者（仅管理员可用）";

cmd_give_fruit.solve = (ctx, msg, cmdArgs) => {
  // 仅管理员可执行
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  const giver = cmdArgs.getArgN(1);
  const receiver = cmdArgs.getArgN(2);
  const fruitName = cmdArgs.getArgN(3);

  if (!giver || !receiver || !fruitName) {
    seal.replyToSender(ctx, msg, "❌ 格式错误，请使用：。赠予果实 赠送者 接受者 果实名字");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 读取库存
  const fruitInventory = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");
  if (!fruitInventory[giver] || fruitInventory[giver].length === 0) {
    seal.replyToSender(ctx, msg, `📭 ${giver} 的库存为空。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 查找果实
  const fruitIndex = fruitInventory[giver].findIndex(f => f.name === fruitName);
  if (fruitIndex === -1) {
    seal.replyToSender(ctx, msg, `❌ ${giver} 的库存中没有名为“${fruitName}”的果实。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 转移果实
  const fruitObj = fruitInventory[giver].splice(fruitIndex, 1)[0];
  // 记录赠送人（保留最初来源可选：如果不存在 from 就添加）
  fruitObj.from = giver;

  if (!fruitInventory[receiver]) fruitInventory[receiver] = [];
  fruitInventory[receiver].push(fruitObj);

  // 保存
  ext.storageSet("a_fruit_game_inventory", JSON.stringify(fruitInventory));

  seal.replyToSender(ctx, msg, `🎁 ${giver} 将「${fruitName}」赠予了 ${receiver}。`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["赠予果实"] = cmd_give_fruit;

// ========== 查看全部果实 ==========
let cmd_view_all_fruit = seal.ext.newCmdItemInfo();
cmd_view_all_fruit.name = "查看全部果实";
cmd_view_all_fruit.help = "。查看全部果实 —— 显示所有人的库存及果实属性与来源";

cmd_view_all_fruit.solve = (ctx, msg) => {
  const fruitInventory = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");

  if (Object.keys(fruitInventory).length === 0) {
    seal.replyToSender(ctx, msg, "📭 当前没有任何库存记录。");
    return seal.ext.newCmdExecuteResult(true);
  }

  let lines = ["📦 全部果实库存："];
  for (const player in fruitInventory) {
    const fruits = fruitInventory[player];
    if (fruits.length === 0) continue;
    lines.push(`\n👤 ${player}：`);
    for (const f of fruits) {
      lines.push(`- ${f.name}（属性：${f.type || "无"}｜来自：${f.from || "未知"}）`);
    }
  }

  seal.replyToSender(ctx, msg, lines.join("\n"));
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看全部果实"] = cmd_view_all_fruit;

// 清空所有假面注册（仅管理员可用）
const cmd_clearAlias = seal.ext.newCmdItemInfo();
cmd_clearAlias.name = "清空假面";
cmd_clearAlias.help = "。清空假面 —— 清空所有假面昵称，让所有人重新注册（仅管理员可用）";

cmd_clearAlias.solve = function (ctx, msg, argv) {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用。");
    return seal.ext.newCmdExecuteResult(true);
  }

  ext.storageSet("masquerade_map", JSON.stringify({}));
  seal.replyToSender(ctx, msg, "🗑️ 所有假面昵称已被清空，所有人需重新注册。");
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["清空假面"] = cmd_clearAlias;

// ========== 赠送果实（根据假面名找人 + 群内广播 + 冷却） ==========
let cmd_give_fruit_by_alias = seal.ext.newCmdItemInfo();
cmd_give_fruit_by_alias.name = "赠送果实";
cmd_give_fruit_by_alias.help = "。赠送果实 接受者假面名 果实名字 —— 将你的指定果实转给对方（通过假面名识别，90秒冷却）";

cmd_give_fruit_by_alias.solve = (ctx, msg, cmdArgs) => {
  const platform = msg.platform;
  const giverUid = msg.sender.userId; // 发起者 UID
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const giverAlias = aliasMap[giverUid]; // 发起者假面名

  if (!giverAlias) {
    seal.replyToSender(ctx, msg, "⚠️ 您尚未注册假面名，无法赠送果实。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const receiverAlias = cmdArgs.getArgN(1)?.trim();
  const fruitName = cmdArgs.getArgN(2)?.trim();

  if (!receiverAlias || !fruitName) {
    seal.replyToSender(ctx, msg, "❌ 格式错误，请使用：。赠送果实 接受者假面名 果实名字");
    return seal.ext.newCmdExecuteResult(true);
  }

  // ===== 冷却检测（180秒） =====
  const cooldownKey = `give_fruit_cooldown_${giverUid}`;
  const cooldownSeconds = 180;
  const now = Math.floor(Date.now() / 1000);
  const lastUsed = parseInt(ext.storageGet(cooldownKey) || "0");

  if (now - lastUsed < cooldownSeconds) {
    const wait = cooldownSeconds - (now - lastUsed);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再赠送果实~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 根据假面名找接收者 UID
  const receiverUid = Object.keys(aliasMap).find(uid => aliasMap[uid] === receiverAlias);
  if (!receiverUid) {
    seal.replyToSender(ctx, msg, `❌ 未找到假面名为「${receiverAlias}」的玩家。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 读取库存（注意：此版本以”假面名”作为 key）
  const inventory = JSON.parse(ext.storageGet(“a_fruit_game_inventory”) || “{}”);
  if (!inventory[giverAlias] || inventory[giverAlias].length === 0) {
    seal.replyToSender(ctx, msg, `📭 您（${giverAlias}）的库存为空。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 查找果实
  const fruitIndex = inventory[giverAlias].findIndex(f => f.name === fruitName);
  if (fruitIndex === -1) {
    seal.replyToSender(ctx, msg, `❌ 您的库存中没有名为「${fruitName}」的果实。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 验证通过后才记录冷却
  ext.storageSet(cooldownKey, now.toString());

  // 转移果实
  const fruitObj = inventory[giverAlias].splice(fruitIndex, 1)[0];
  fruitObj.from = giverAlias; // 记录赠送者的假面名

  if (!inventory[receiverAlias]) inventory[receiverAlias] = [];
  inventory[receiverAlias].push(fruitObj);

  // 保存
  ext.storageSet("a_fruit_game_inventory", JSON.stringify(inventory));

  // —— 群内广播 ——
  const groupId = `${platform}-Group:1097345718`; 
  const fullText = `「${giverAlias}」将「${fruitName}」赠予了「${receiverAlias}」。`;

  const outMsg = seal.newMessage();
  outMsg.messageType = "group";
  outMsg.sender = {};
  outMsg.sender.userId = `匿名-${giverAlias}`;
  outMsg.groupId = groupId;

  const tempCtx = seal.createTempCtx(ctx.endPoint, outMsg);

  // 回执与广播
  seal.replyToSender(ctx, msg, `🎁 ${giverAlias} 将「${fruitName}」赠予了 ${receiverAlias}。`);
  seal.replyToSender(tempCtx, outMsg, fullText);

  return seal.ext.newCmdExecuteResult(true);
};

//ext.cmdMap["赠送果实"] = cmd_give_fruit_by_alias;

// ========== 查看果实库存（支持查看自己 / 管理员可查他人） ==========
let cmd_view_my_fruit = seal.ext.newCmdItemInfo();
cmd_view_my_fruit.name = "查看果实";
cmd_view_my_fruit.help = "。查看果实 —— 显示你自己的库存及果实属性与来源";

cmd_view_my_fruit.solve = (ctx, msg) => {
  const uid = msg.sender.userId;

  // 假面名映射（用于优雅显示）
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const alias = aliasMap[uid];

  // 读取库存
  const fruitInventory = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");
  const myFruits = fruitInventory[alias] || [];

  if (myFruits.length === 0) {
    const who = alias ? `「${alias}」` : uid;
    seal.replyToSender(ctx, msg, `📭 ${who} 的库存为空。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  const who = alias ? `「${alias}」` : uid;
  let lines = [
    `📦 个人果实库存：${who}`,
    `（数量：${myFruits.length}）`
  ];

  for (const f of myFruits) {
    lines.push(`- ${f.name}`);
  }

  seal.replyToSender(ctx, msg, lines.join("\n"));
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["查看果实"] = cmd_view_my_fruit;


// ========== 查看果实统计（管理员专用） ==========
const cmd_fruit_stats = seal.ext.newCmdItemInfo();
cmd_fruit_stats.name = "果实统计";
cmd_fruit_stats.help = "。果实统计 —— 查看所有玩家的真果与毒果数量统计（仅管理员可用）";

cmd_fruit_stats.solve = (ctx, msg) => {
  // 仅管理员可执行
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  const fruitInventory = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");

  if (Object.keys(fruitInventory).length === 0) {
    seal.replyToSender(ctx, msg, "📭 当前没有任何果实库存记录。");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 统计每个玩家的果实
  const stats = [];
  let totalGood = 0;
  let totalPoison = 0;
  let totalFruits = 0;

  for (const [alias, fruits] of Object.entries(fruitInventory)) {
    if (!fruits || fruits.length === 0) continue;
    
    let goodCount = 0;
    let poisonCount = 0;
    
    fruits.forEach(fruit => {
      if (fruit.type === "真果") {
        goodCount++;
        totalGood++;
      } else if (fruit.type === "毒果") {
        poisonCount++;
        totalPoison++;
      }
    });
    
    const totalCount = goodCount + poisonCount;
    totalFruits += totalCount;
    
    // 查找用户ID（可选显示）
    const userId = Object.keys(aliasMap).find(uid => aliasMap[uid] === alias);
    const shortUserId = userId ? userId.split(':').pop().slice(0, 8) + '...' : '未知';
    
    stats.push({
      alias,
      userId: shortUserId,
      goodCount,
      poisonCount,
      totalCount
    });
  }

  // 按真果数量降序排序
  stats.sort((a, b) => {
    // 先按真果数量，再按总数，最后按毒果数量
    if (b.goodCount !== a.goodCount) return b.goodCount - a.goodCount;
    if (b.totalCount !== a.totalCount) return b.totalCount - a.totalCount;
    return b.poisonCount - a.poisonCount;
  });

  // 构建输出
  let lines = ["🍇 果实统计报表 🍇", ""];
  lines.push("┌─────────────────────────────────────────────┐");
  lines.push("│ 玩家            │ 真果 │ 毒果 │ 总计 │");
  lines.push("├─────────────────────────────────────────────┤");

  stats.forEach((stat, index) => {
    const rankIcon = index < 3 ? ["🥇", "🥈", "🥉"][index] : ` ${index + 1}.`;
    const aliasDisplay = stat.alias.length > 6 ? stat.alias.slice(0, 6) + "…" : stat.alias.padEnd(6, '　');
    
    lines.push(`│ ${rankIcon} ${aliasDisplay} │ ${stat.goodCount.toString().padStart(2, ' ')}  │ ${stat.poisonCount.toString().padStart(2, ' ')}  │ ${stat.totalCount.toString().padStart(2, ' ')}  │`);
  });

  lines.push("├─────────────────────────────────────────────┤");
  lines.push(`│ 全局统计        │ ${totalGood.toString().padStart(2, ' ')}  │ ${totalPoison.toString().padStart(2, ' ')}  │ ${totalFruits.toString().padStart(2, ' ')}  │`);
  lines.push("└─────────────────────────────────────────────┘");
  lines.push("");
  
  // 添加一些分析
  if (stats.length > 0) {
    const topGoodHolder = stats[0];
    const topPoisonHolder = [...stats].sort((a, b) => b.poisonCount - a.poisonCount)[0];
    const mostFruitsHolder = [...stats].sort((a, b) => b.totalCount - a.totalCount)[0];
    
    lines.push("📊 数据分析：");
    lines.push(`🎖️  真果最多：${topGoodHolder.alias}（${topGoodHolder.goodCount}枚真果）`);
    lines.push(`☠️  毒果最多：${topPoisonHolder.alias}（${topPoisonHolder.poisonCount}枚毒果）`);
    lines.push(`📦  果实最多：${mostFruitsHolder.alias}（${mostFruitsHolder.totalCount}枚果实）`);
    
    // 计算平均值
    const avgGood = (totalGood / stats.length).toFixed(1);
    const avgPoison = (totalPoison / stats.length).toFixed(1);
    lines.push(`📈  人均真果：${avgGood}枚，人均毒果：${avgPoison}枚`);
    
    // 真果毒果比例
    const goodRatio = totalFruits > 0 ? ((totalGood / totalFruits) * 100).toFixed(1) : 0;
    lines.push(`⚖️  真果比例：${goodRatio}%`);
  }

  seal.replyToSender(ctx, msg, lines.join("\n"));
  return seal.ext.newCmdExecuteResult(true);
};

// 注册指令
ext.cmdMap["果实统计"] = cmd_fruit_stats;


// ========== 管理员修改假面名 ==========
const cmd_modify_alias = seal.ext.newCmdItemInfo();
cmd_modify_alias.name = "修改假面";
cmd_modify_alias.help = "。修改假面 原假面名 新假面名 —— 修改任意用户的假面名（仅管理员可用）";

cmd_modify_alias.solve = function(ctx, msg, argv) {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const oldAlias = argv.getArgN(1)?.trim();
  const newAlias = argv.getArgN(2)?.trim();

  if (!oldAlias || !newAlias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");

  // 查找原假面名对应的用户ID
  const userId = Object.keys(stored).find(uid => stored[uid] === oldAlias);
  
  if (!userId) {
    seal.replyToSender(ctx, msg, `❌ 未找到使用假面名「${oldAlias}」的用户。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查新假面名是否已被使用
  if (Object.values(stored).includes(newAlias)) {
    seal.replyToSender(ctx, msg, `⚠️ 假面名「${newAlias}」已被他人使用，请更换一个独特的名号。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 更新假面名
  stored[userId] = newAlias;
  ext.storageSet("masquerade_map", JSON.stringify(stored));

  seal.replyToSender(ctx, msg, `🎭 成功将「${oldAlias}」的假面名修改为「${newAlias}」。`);
  return seal.ext.newCmdExecuteResult(true);
};

// 注册指令（取消注释以启用）
ext.cmdMap["修改假面"] = cmd_modify_alias;

// ========== 查看假面名单 ==========
const cmd_list_masquerade = seal.ext.newCmdItemInfo();
cmd_list_masquerade.name = "假面名单";
cmd_list_masquerade.help = "。假面名单 —— 查看所有已注册的假面名";

cmd_list_masquerade.solve = function(ctx, msg, argv) {
  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  
  if (Object.keys(stored).length === 0) {
    seal.replyToSender(ctx, msg, "📭 目前还没有任何人注册假面名。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const aliases = Object.values(stored);
  const totalCount = aliases.length;
  
  // 按字母顺序排序
  aliases.sort();
  
  let replyText = `🎭 假面名单（共 ${totalCount} 位）\n\n`;
  
  // 每行显示3个，整齐排列
  const chunkSize = 3;
  for (let i = 0; i < aliases.length; i += chunkSize) {
    const chunk = aliases.slice(i, i + chunkSize);
    const line = chunk.map(name => `「${name}」`).join("    ");
    replyText += line + "\n";
  }
  
  seal.replyToSender(ctx, msg, replyText);
  return seal.ext.newCmdExecuteResult(true);
};

// 注册指令（取消注释以启用）
ext.cmdMap["假面名单"] = cmd_list_masquerade;

// ========== 献花功能 ==========

// 献花指令
const cmd_give_flower = seal.ext.newCmdItemInfo();
cmd_give_flower.name = "献花";
cmd_give_flower.help = "。献花 目标假面名 —— 向指定的假面角色献花（每日限3次）";

cmd_give_flower.solve = function(ctx, msg, argv) {
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const targetAlias = argv.getArgN(1)?.trim();
  
  // 获取献花者假面名
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const giverAlias = aliasMap[uid];
  
  if (!giverAlias) {
    seal.replyToSender(ctx, msg, "⚠️ 您尚未注册假面名，无法献花。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  if (!targetAlias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }
  
  // 检查是否给自己献花
  if (giverAlias === targetAlias) {
    seal.replyToSender(ctx, msg, "❌ 不能给自己献花哦~");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 检查目标是否存在
  const targetExists = Object.values(aliasMap).includes(targetAlias);
  if (!targetExists) {
    seal.replyToSender(ctx, msg, `❌ 未找到假面名为「${targetAlias}」的角色。`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 冷却机制（60秒）
  const cooldownKey = `flower_cooldown_${uid}`;
  const cooldownSeconds = 60;
  const now = Math.floor(Date.now() / 1000);
  const lastUsed = parseInt(ext.storageGet(cooldownKey) || "0");
  
  if (now - lastUsed < cooldownSeconds) {
    const wait = cooldownSeconds - (now - lastUsed);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再献花~`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 每日限制检查
  const today = new Date().toDateString();
  const dailyKey = `flower_daily_${uid}_${today}`;
  const dailyCount = parseInt(ext.storageGet(dailyKey) || "0");
  const dailyLimit = 1000;
  
  if (dailyCount >= dailyLimit) {
    seal.replyToSender(ctx, msg, `💐 今日献花次数已用尽（${dailyLimit}次/日），明天再来吧~`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 更新献花记录
  ext.storageSet(cooldownKey, now.toString());
  ext.storageSet(dailyKey, (dailyCount + 1).toString());
  
  // 更新收花统计
  const flowerStats = JSON.parse(ext.storageGet("flower_stats") || "{}");
  if (!flowerStats[targetAlias]) {
    flowerStats[targetAlias] = 0;
  }
  flowerStats[targetAlias] += 1;
  ext.storageSet("flower_stats", JSON.stringify(flowerStats));
  
  // 记录献花历史（可选）
  const flowerHistory = JSON.parse(ext.storageGet("flower_history") || "[]");
  flowerHistory.push({
    giver: giverAlias,
    receiver: targetAlias,
    timestamp: now
  });
  ext.storageSet("flower_history", JSON.stringify(flowerHistory));
  
  // 群内广播
  const groupId = `${platform}-Group:1097345718`;
  const flowerMessages = [
    `💐 ${giverAlias} 向 ${targetAlias} 献上一朵玫瑰，芬芳满堂~`,
    `🌹 ${giverAlias} 为 ${targetAlias} 戴上一朵鲜花，优雅动人~`,
    `🌸 ${giverAlias} 向 ${targetAlias} 抛洒花瓣，浪漫满溢~`,
    `💮 ${giverAlias} 赠予 ${targetAlias} 一束鲜花，情意绵绵~`
  ];
  const randomMessage = flowerMessages[Math.floor(Math.random() * flowerMessages.length)];
  
  const outMsg = seal.newMessage();
  outMsg.messageType = "group";
  outMsg.sender = {};
  outMsg.groupId = groupId;
  
  const tempCtx = seal.createTempCtx(ctx.endPoint, outMsg);
  
  // 回复发送者和群内广播
  seal.replyToSender(ctx, msg, `💐 成功向「${targetAlias}」献花！今日剩余次数：${dailyLimit - dailyCount - 1}次`);
  seal.replyToSender(tempCtx, outMsg, randomMessage);
  
  return seal.ext.newCmdExecuteResult(true);
};

// 查看花榜指令
const cmd_flower_rank = seal.ext.newCmdItemInfo();
cmd_flower_rank.name = "花榜";
cmd_flower_rank.help = "。花榜 —— 查看收到鲜花最多的假面角色排行榜";

cmd_flower_rank.solve = function(ctx, msg, argv) {
  const flowerStats = JSON.parse(ext.storageGet("flower_stats") || "{}");
  
  if (Object.keys(flowerStats).length === 0) {
    seal.replyToSender(ctx, msg, "📭 暂无献花记录，快来向心仪的假面献花吧~");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 转换为数组并排序
  const rankList = Object.entries(flowerStats)
    .map(([alias, count]) => ({ alias, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10); // 取前10名
  
  let replyText = "🏆 假面舞会·花榜 🏆\n\n";
  
  rankList.forEach((item, index) => {
    const rankIcons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"];
    const rankIcon = rankIcons[index] || `${index + 1}.`;
    replyText += `${rankIcon} 「${item.alias}」 - ${item.count} 朵花\n`;
  });
  
  seal.replyToSender(ctx, msg, replyText);
  return seal.ext.newCmdExecuteResult(true);
};

// 查看我的花数指令
const cmd_my_flowers = seal.ext.newCmdItemInfo();
cmd_my_flowers.name = "我的花数";
cmd_my_flowers.help = "。我的花数 —— 查看自己收到的鲜花数量";

cmd_my_flowers.solve = function(ctx, msg, argv) {
  const uid = msg.sender.userId;
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const myAlias = aliasMap[uid];
  
  if (!myAlias) {
    seal.replyToSender(ctx, msg, "⚠️ 您尚未注册假面名。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  const flowerStats = JSON.parse(ext.storageGet("flower_stats") || "{}");
  const myFlowers = flowerStats[myAlias] || 0;
  
  let message = `💐 「${myAlias}」共收到 ${myFlowers} 朵鲜花`;
  
  if (myFlowers === 0) {
    message += "\n🎭 继续在舞会中展现魅力吧~";
  } else if (myFlowers < 5) {
    message += "\n🌷 初绽芬芳，继续闪耀~";
  } else if (myFlowers < 10) {
    message += "\n🌹 花香四溢，备受青睐~";
  } else {
    message += "\n💮 花团锦簇，万众瞩目~";
  }
  
  seal.replyToSender(ctx, msg, message);
  return seal.ext.newCmdExecuteResult(true);
};

// 清空花榜指令（仅管理员）
const cmd_clear_flowers = seal.ext.newCmdItemInfo();
cmd_clear_flowers.name = "清空花榜";
cmd_clear_flowers.help = "。清空花榜 —— 清空所有献花记录（仅管理员可用）";

cmd_clear_flowers.solve = function(ctx, msg, argv) {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  ext.storageSet("flower_stats", JSON.stringify({}));
  ext.storageSet("flower_history", JSON.stringify([]));
  
  seal.replyToSender(ctx, msg, "🗑️ 所有献花记录已被清空，花榜重置。");
  return seal.ext.newCmdExecuteResult(true);
};

// 注册指令（取消注释以启用）
 ext.cmdMap["献花"] = cmd_give_flower;
 ext.cmdMap["花榜"] = cmd_flower_rank;
// ext.cmdMap["我的花数"] = cmd_my_flowers;
// ext.cmdMap["清空花榜"] = cmd_clear_flowers;

// ========== 送鸡蛋功能 ==========

// 送鸡蛋指令
const cmd_give_egg = seal.ext.newCmdItemInfo();
cmd_give_egg.name = "送鸡蛋";
cmd_give_egg.help = "。送鸡蛋 目标假面名 —— 向指定的假面角色送鸡蛋（每日限3次）";

cmd_give_egg.solve = function(ctx, msg, argv) {
  const platform = msg.platform;
  const uid = msg.sender.userId;
  const targetAlias = argv.getArgN(1)?.trim();
  
  // 获取送鸡蛋者假面名
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const giverAlias = aliasMap[uid];
  
  if (!giverAlias) {
    seal.replyToSender(ctx, msg, "⚠️ 您尚未注册假面名，无法送鸡蛋。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  if (!targetAlias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }
  
  // 检查是否给自己送鸡蛋
  if (giverAlias === targetAlias) {
    seal.replyToSender(ctx, msg, "❌ 不能给自己送鸡蛋哦~");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 检查目标是否存在
  const targetExists = Object.values(aliasMap).includes(targetAlias);
  if (!targetExists) {
    seal.replyToSender(ctx, msg, `❌ 未找到假面名为「${targetAlias}」的角色。`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 冷却机制（60秒）
  const cooldownKey = `egg_cooldown_${uid}`;
  const cooldownSeconds = 60;
  const now = Math.floor(Date.now() / 1000);
  const lastUsed = parseInt(ext.storageGet(cooldownKey) || "0");
  
  if (now - lastUsed < cooldownSeconds) {
    const wait = cooldownSeconds - (now - lastUsed);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再送鸡蛋~`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 每日限制检查
  const today = new Date().toDateString();
  const dailyKey = `egg_daily_${uid}_${today}`;
  const dailyCount = parseInt(ext.storageGet(dailyKey) || "0");
  const dailyLimit = 1000;
  
  if (dailyCount >= dailyLimit) {
    seal.replyToSender(ctx, msg, `🥚 今日送鸡蛋次数已用尽（${dailyLimit}次/日），明天再来吧~`);
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 更新送鸡蛋记录
  ext.storageSet(cooldownKey, now.toString());
  ext.storageSet(dailyKey, (dailyCount + 1).toString());
  
  // 更新收鸡蛋统计
  const eggStats = JSON.parse(ext.storageGet("egg_stats") || "{}");
  if (!eggStats[targetAlias]) {
    eggStats[targetAlias] = 0;
  }
  eggStats[targetAlias] += 1;
  ext.storageSet("egg_stats", JSON.stringify(eggStats));
  
  // 记录送鸡蛋历史（可选）
  const eggHistory = JSON.parse(ext.storageGet("egg_history") || "[]");
  eggHistory.push({
    giver: giverAlias,
    receiver: targetAlias,
    timestamp: now
  });
  ext.storageSet("egg_history", JSON.stringify(eggHistory));
  
  // 群内广播
  const groupId = `${platform}-Group:1097345718`;
  const eggMessages = [
    `🥚 ${giverAlias} 向 ${targetAlias} 扔了一个鸡蛋，蛋花四溅~`,
    `🍳 ${giverAlias} 给 ${targetAlias} 煎了个荷包蛋，香气扑鼻~`,
    `💥 ${giverAlias} 对 ${targetAlias} 发动鸡蛋攻击，精准命中~`,
    `🎯 ${giverAlias} 用鸡蛋砸中了 ${targetAlias}，蛋清横飞~`,
    `🤡 ${giverAlias} 送给 ${targetAlias} 一篮鸡蛋，意味深长~`,
    `🍌 ${giverAlias} 向 ${targetAlias} 投掷鸡蛋，滑倒警告~`
  ];
  const randomMessage = eggMessages[Math.floor(Math.random() * eggMessages.length)];
  
  const outMsg = seal.newMessage();
  outMsg.messageType = "group";
  outMsg.sender = {};
  outMsg.groupId = groupId;
  
  const tempCtx = seal.createTempCtx(ctx.endPoint, outMsg);
  
  // 回复发送者和群内广播
  seal.replyToSender(ctx, msg, `🥚 成功向「${targetAlias}」送鸡蛋！今日剩余次数：${dailyLimit - dailyCount - 1}次`);
  seal.replyToSender(tempCtx, outMsg, randomMessage);
  
  return seal.ext.newCmdExecuteResult(true);
};

// 查看蛋榜指令
const cmd_egg_rank = seal.ext.newCmdItemInfo();
cmd_egg_rank.name = "蛋榜";
cmd_egg_rank.help = "。蛋榜 —— 查看收到鸡蛋最多的假面角色排行榜";

cmd_egg_rank.solve = function(ctx, msg, argv) {
  const eggStats = JSON.parse(ext.storageGet("egg_stats") || "{}");
  
  if (Object.keys(eggStats).length === 0) {
    seal.replyToSender(ctx, msg, "📭 暂无送鸡蛋记录，舞会氛围很和谐呢~");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  // 转换为数组并排序
  const rankList = Object.entries(eggStats)
    .map(([alias, count]) => ({ alias, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 10); // 取前10名
  
  let replyText = "🥚 假面舞会·蛋榜 🥚\n\n";
  
  rankList.forEach((item, index) => {
    const rankIcons = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"];
    const rankIcon = rankIcons[index] || `${index + 1}.`;
    replyText += `${rankIcon} 「${item.alias}」 - ${item.count} 个蛋\n`;
  });
  
  seal.replyToSender(ctx, msg, replyText);
  return seal.ext.newCmdExecuteResult(true);
};

// 查看我的蛋数指令
const cmd_my_eggs = seal.ext.newCmdItemInfo();
cmd_my_eggs.name = "我的蛋数";
cmd_my_eggs.help = "。我的蛋数 —— 查看自己收到的鸡蛋数量";

cmd_my_eggs.solve = function(ctx, msg, argv) {
  const uid = msg.sender.userId;
  const aliasMap = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  const myAlias = aliasMap[uid];
  
  if (!myAlias) {
    seal.replyToSender(ctx, msg, "⚠️ 您尚未注册假面名。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  const eggStats = JSON.parse(ext.storageGet("egg_stats") || "{}");
  const myEggs = eggStats[myAlias] || 0;
  
  let message = `🥚 「${myAlias}」共收到 ${myEggs} 个鸡蛋`;
  
  if (myEggs === 0) {
    message += "\n🎭 舞会中表现不错，继续保持~";
  } else if (myEggs < 5) {
    message += "\n😅 有点小争议，但无伤大雅~";
  } else if (myEggs < 10) {
    message += "\n🤔 似乎引起了一些讨论~";
  } else {
    message += "\n💢 真是引人注目呢~";
  }
  
  seal.replyToSender(ctx, msg, message);
  return seal.ext.newCmdExecuteResult(true);
};

// 清空蛋榜指令（仅管理员）
const cmd_clear_eggs = seal.ext.newCmdItemInfo();
cmd_clear_eggs.name = "清空蛋榜";
cmd_clear_eggs.help = "。清空蛋榜 —— 清空所有送鸡蛋记录（仅管理员可用）";

cmd_clear_eggs.solve = function(ctx, msg, argv) {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用。");
    return seal.ext.newCmdExecuteResult(true);
  }
  
  ext.storageSet("egg_stats", JSON.stringify({}));
  ext.storageSet("egg_history", JSON.stringify([]));
  
  seal.replyToSender(ctx, msg, "🗑️ 所有送鸡蛋记录已被清空，蛋榜重置。");
  return seal.ext.newCmdExecuteResult(true);
};

// 更新移除假面功能，同时清理鸡蛋记录
const cmd_remove_alias = seal.ext.newCmdItemInfo();
cmd_remove_alias.name = "移除假面";
cmd_remove_alias.help = "。移除假面 假面名 —— 移除指定假面名的注册（仅管理员可用）";

cmd_remove_alias.solve = function(ctx, msg, argv) {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 此指令仅限管理员使用。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const targetAlias = argv.getArgN(1)?.trim();

  if (!targetAlias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const stored = JSON.parse(ext.storageGet("masquerade_map") || "{}");

  // 查找目标假面名对应的用户ID
  const userId = Object.keys(stored).find(uid => stored[uid] === targetAlias);
  
  if (!userId) {
    seal.replyToSender(ctx, msg, `❌ 未找到假面名为「${targetAlias}」的用户。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 移除假面名
  delete stored[userId];
  ext.storageSet("masquerade_map", JSON.stringify(stored));

  // 同时移除该用户的果实库存
  const inventory = JSON.parse(ext.storageGet("a_fruit_game_inventory") || "{}");
  if (inventory[targetAlias]) {
    delete inventory[targetAlias];
    ext.storageSet("a_fruit_game_inventory", JSON.stringify(inventory));
  }

  // 同时移除该用户的花数记录
  const flowerStats = JSON.parse(ext.storageGet("flower_stats") || "{}");
  if (flowerStats[targetAlias]) {
    delete flowerStats[targetAlias];
    ext.storageSet("flower_stats", JSON.stringify(flowerStats));
  }
  
  // 同时移除该用户的鸡蛋记录
  const eggStats = JSON.parse(ext.storageGet("egg_stats") || "{}");
  if (eggStats[targetAlias]) {
    delete eggStats[targetAlias];
    ext.storageSet("egg_stats", JSON.stringify(eggStats));
  }

  seal.replyToSender(ctx, msg, `🗑️ 已成功移除假面「${targetAlias}」，相关数据已清理。`);
  return seal.ext.newCmdExecuteResult(true);
};

// 注册指令（取消注释以启用）
ext.cmdMap["送鸡蛋"] = cmd_give_egg;
ext.cmdMap["蛋榜"] = cmd_egg_rank;
// ext.cmdMap["我的蛋数"] = cmd_my_eggs;
// ext.cmdMap["清空蛋榜"] = cmd_clear_eggs;
ext.cmdMap["移除假面"] = cmd_remove_alias; // 替换原有的移除假面指令


// =========================
// 🕵️ 密电风云 - 民国情报战（推理版）
// =========================

/** 游戏状态管理 */
function _mg_getState() {
  return JSON.parse(ext.storageGet("message_game_state") || "{}");
}
function _mg_saveState(s) {
  ext.storageSet("message_game_state", JSON.stringify(s || {}));
}
function _mg_aliasOf(uid) {
  const m = JSON.parse(ext.storageGet("masquerade_map") || "{}");
  return m[uid] || uid;
}

/** 扩展民国主题密电码 */
const codeWords = {
  // 基础词汇
  "夜莺": "情报", "玫瑰": "武器", "月光": "安全", "暴雨": "危险",
  "茶馆": "会面点", "码头": "撤离点", "老鹰": "监视", "信鸽": "信使",
  "钟声": "时间", "迷雾": "掩护", "钥匙": "密码本", "影子": "卧底",
  "火焰": "销毁", "琴弦": "联络", "落叶": "信号",
  
  // 扩展词汇
  "白鸽": "我方特工", "黑猫": "敌方特工", "青蛇": "双面间谍", 
  "灰狼": "行动组长", "金鱼": "内线人员", "银狐": "情报贩子",
  "黄雀": "狙击手", "紫蝶": "女特工", "赤虎": "激进分子",
  "蓝鲸": "海军联络", "启明星": "开始行动", "长夜": "暂停行动",
  "黎明": "行动成功", "黄昏": "行动失败", "春风": "传递情报",
  "冬雪": "隐藏踪迹", "秋雨": "清理现场", "夏雷": "紧急撤离"
};

/** 干扰词汇（这些词不在密电码中） */
const distractionWords = [
  "蝴蝶", "麻雀", "鲤鱼", "蟋蟀", "蝉鸣", "雪花", "露珠", 
  "霜降", "冰雹", "闪电", "石桥", "小巷", "阁楼", "庭院", 
  "城墙", "胭脂", "折扇", "旗袍", "怀表", "烟斗", "琵琶", 
  "二胡", "笛声", "古琴", "锣鼓", "围棋", "麻将", "风筝", 
  "灯笼", "剪纸"
];

/** 初始化游戏 */
const cmd_message_init = seal.ext.newCmdItemInfo();
cmd_message_init.name = "密电开局";
cmd_message_init.help = "。密电开局 —— 开启新一轮密电风云（仅管理员）";
cmd_message_init.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 仅管理员可开局。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const state = {
    active: true,
    round: 1,
    players: {},
    currentCode: null,
    codeHistory: [],
    scores: {},
    discoveredWords: {}, // 玩家发现的词汇映射
    lastActionTime: Date.now()
  };

  _mg_saveState(state);
  
  seal.replyToSender(ctx, msg, 
    `📻 密电风云·民国情报战 开启！\n\n` +
    `🎯 游戏规则：\n` +
    `· 每轮会发布一段加密情报，你需要破译其中的暗语\n` +
    `· 通过「密电试探」指令来猜测词汇含义\n` +
    `· 成功破译完整情报可获得高分\n` +
    `· 干扰他人破译可获得「干扰点」\n` +
    `· 最终根据总积分排名\n\n` +
    `💡 可用指令：\n` +
    `· 密电报名 - 加入游戏\n` +
    `· 密电试探 - 猜测单个词汇含义\n` +
    `· 密电破译 - 尝试破译完整密电\n` +
    `· 密电干扰 - 干扰其他玩家\n` +
    `· 密电词库 - 查看你已破译的词汇\n` +
    `· 密电状态 - 查看当前战况\n` +
    `· 密电结算 - 结束本轮（管理员）`
  );
  
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电开局"] = cmd_message_init;

/** 生成随机密电（包含干扰词） */
function generateEncodedMessage() {
  const words = Object.keys(codeWords);
  const selectedWords = [];
  
  // 随机选择3-4个真实密电词
  const realCount = 3 + Math.floor(Math.random() * 2);
  for (let i = 0; i < realCount; i++) {
    const word = words[Math.floor(Math.random() * words.length)];
    if (!selectedWords.includes(word)) {
      selectedWords.push(word);
    }
  }
  
  // 随机添加0-2个干扰词
  const distractionCount = Math.floor(Math.random() * 3);
  for (let i = 0; i < distractionCount; i++) {
    const distraction = distractionWords[Math.floor(Math.random() * distractionWords.length)];
    if (!selectedWords.includes(distraction)) {
      // 随机插入位置
      const insertPos = Math.floor(Math.random() * (selectedWords.length + 1));
      selectedWords.splice(insertPos, 0, distraction);
    }
  }
  
  // 构建密电格式
  const timeCodes = ["子时", "丑时", "寅时", "卯时", "辰时", "巳时"];
  const locations = ["霞飞路", "外滩", "城隍庙", "百乐门", "码头", "报馆"];
  const contacts = ["夜莺", "信鸽", "影子", "老鹰"];
  const priorities = ["加急", "特急", "普通", "密件"];
  
  const time = timeCodes[Math.floor(Math.random() * timeCodes.length)];
  const location = locations[Math.floor(Math.random() * locations.length)];
  const contact = contacts[Math.floor(Math.random() * contacts.length)];
  const priority = priorities[Math.floor(Math.random() * priorities.length)];
  
  return {
    encoded: `【${priority}】「${time}」「${location}」「${contact}」${selectedWords.map(w => `「${w}」`).join("")}`,
    solution: `${priority}级别：${time}在${location}与${contact}联络 - ${selectedWords.filter(w => codeWords[w]).map(w => codeWords[w]).join("、")}`,
    keywords: selectedWords.filter(w => codeWords[w]), // 只包含真实密电词
    distractions: selectedWords.filter(w => !codeWords[w]), // 干扰词
    allWords: selectedWords // 所有词汇（包括干扰词）
  };
}

/** 报名参赛 */
const cmd_message_join = seal.ext.newCmdItemInfo();
cmd_message_join.name = "密电报名";
cmd_message_join.help = "。密电报名 —— 加入密电风云游戏";
cmd_message_join.solve = (ctx, msg) => {
  const uid = msg.sender.userId;
  const alias = _mg_aliasOf(uid);
  const state = _mg_getState();

  if (!state.active) {
    seal.replyToSender(ctx, msg, "📭 尚未开局，请等待管理员「。密电开局」。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!state.players[uid]) {
    state.players[uid] = {
      alias: alias,
      score: 0,
      decoded: 0,
      interfered: 0,
      discoveredWords: {}, // 个人词库
      lastAction: 0
    };
    state.scores[alias] = state.scores[alias] || 0;
    state.discoveredWords[uid] = {};
  }

  // 如果当前没有密电，生成一个
  if (!state.currentCode) {
    state.currentCode = generateEncodedMessage();
    state.codeHistory.push(state.currentCode);
  }

  _mg_saveState(state);
  
  seal.replyToSender(ctx, msg, 
    `🎭 ${alias} 已加入密电风云！\n\n` +
    `📜 当前密电：\n${state.currentCode.encoded}\n\n` +
    `💡 使用「。密电试探 词汇 猜测含义」来猜测单个词汇\n` +
    `💡 使用「。密电破译 完整译文」来破译整个情报\n` +
    `⚡ 使用「。密电干扰 目标假面名」来干扰他人`
  );
  
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电报名"] = cmd_message_join;

/** 试探单个词汇含义 */
const cmd_message_try = seal.ext.newCmdItemInfo();
cmd_message_try.name = "密电试探";
cmd_message_try.help = "。密电试探 词汇 猜测含义 —— 猜测单个词汇的含义";
cmd_message_try.solve = (ctx, msg, args) => {
  const uid = msg.sender.userId;
  const alias = _mg_aliasOf(uid);
  const word = args.getArgN(1)?.trim();
  const guess = args.getArgN(2)?.trim();
  const state = _mg_getState();

  if (!state.active) {
    seal.replyToSender(ctx, msg, "📭 游戏未进行中。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!state.players[uid]) {
    seal.replyToSender(ctx, msg, "⚠️ 请先使用「。密电报名」加入游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!word || !guess) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const player = state.players[uid];
  const now = Date.now();
  
  // 冷却检测（20秒）
  if (now - player.lastAction < 20000) {
    const wait = Math.ceil((20000 - (now - player.lastAction)) / 1000);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再行动~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  player.lastAction = now;
  state.lastActionTime = now;

  // 检查词汇是否在当前密电中
  if (!state.currentCode.allWords.includes(word)) {
    seal.replyToSender(ctx, msg, `❌ 「${word}」不在当前密电中。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查是否是干扰词
  if (state.currentCode.distractions.includes(word)) {
    player.score += 1; // 发现干扰词也有奖励
    _mg_saveState(state);
    
    seal.replyToSender(ctx, msg, 
      `🔍 试探结果：「${word}」是干扰词，没有实际含义！\n` +
      `✅ 获得 1 分奖励（发现干扰词）`
    );
    return seal.ext.newCmdExecuteResult(true);
  }

  // 检查猜测是否正确
  const correctMeaning = codeWords[word];
  let resultText = "";
  
  if (guess === correctMeaning) {
    // 正确猜测
    player.score += 3;
    player.discoveredWords[word] = correctMeaning;
    state.discoveredWords[uid] = state.discoveredWords[uid] || {};
    state.discoveredWords[uid][word] = correctMeaning;
    
    resultText = `🎉 正确！「${word}」的含义是：「${correctMeaning}」\n` +
                `✅ 获得 3 分奖励，该词汇已加入你的词库`;
  } else {
    // 错误猜测
    resultText = `❌ 错误！「${word}」的含义不是「${guess}」\n` +
                `💡 继续努力，你可以通过上下文推理词汇含义`;
    
    // 给一点提示（相似度提示）
    const similarity = calculateSimilarity(guess, correctMeaning);
    if (similarity > 0.3) {
      resultText += `\n🔍 提示：你的猜测「${guess}」与正确答案有一定关联`;
    }
  }

  _mg_saveState(state);
  seal.replyToSender(ctx, msg, resultText);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电试探"] = cmd_message_try;

/** 简单相似度计算 */
function calculateSimilarity(str1, str2) {
  const set1 = new Set(str1);
  const set2 = new Set(str2);
  const intersection = new Set([...set1].filter(x => set2.has(x)));
  const union = new Set([...set1, ...set2]);
  return intersection.size / union.size;
}

/** 查看个人词库 */
const cmd_message_vocab = seal.ext.newCmdItemInfo();
cmd_message_vocab.name = "密电词库";
cmd_message_vocab.help = "。密电词库 —— 查看你已经破译的词汇";
cmd_message_vocab.solve = (ctx, msg) => {
  const uid = msg.sender.userId;
  const state = _mg_getState();

  if (!state.players[uid]) {
    seal.replyToSender(ctx, msg, "⚠️ 请先使用「。密电报名」加入游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const player = state.players[uid];
  const discovered = player.discoveredWords || {};
  const wordCount = Object.keys(discovered).length;

  let resultText = `📚 ${player.alias} 的密电词库\n\n`;
  
  if (wordCount === 0) {
    resultText += "📭 尚未破译任何词汇\n";
    resultText += "💡 使用「。密电试探 词汇 猜测含义」来破译词汇";
  } else {
    resultText += `🔍 已破译 ${wordCount} 个词汇：\n`;
    Object.entries(discovered).forEach(([word, meaning]) => {
      resultText += `· 「${word}」→ ${meaning}\n`;
    });
    resultText += `\n💡 使用已知词汇来破译完整密电吧！`;
  }

  seal.replyToSender(ctx, msg, resultText);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电词库"] = cmd_message_vocab;

/** 破译完整密电 */
const cmd_message_decode = seal.ext.newCmdItemInfo();
cmd_message_decode.name = "密电破译";
cmd_message_decode.help = "。密电破译 完整译文 —— 尝试破译当前密电";
cmd_message_decode.solve = (ctx, msg, args) => {
  const uid = msg.sender.userId;
  const alias = _mg_aliasOf(uid);
  const guess = args.getRestArgsFrom(1)?.trim();
  const state = _mg_getState();

  if (!state.active) {
    seal.replyToSender(ctx, msg, "📭 游戏未进行中。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!state.players[uid]) {
    seal.replyToSender(ctx, msg, "⚠️ 请先使用「。密电报名」加入游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!guess) {
    seal.replyToSender(ctx, msg, 
      `📜 当前密电：\n${state.currentCode.encoded}\n\n` +
      `💡 使用「。密电试探」猜测词汇含义\n` +
      `💡 使用「。密电词库」查看已破译词汇\n` +
      `📝 破译格式：完整翻译整个密电内容`
    );
    return seal.ext.newCmdExecuteResult(true);
  }

  const player = state.players[uid];
  const now = Date.now();
  
  // 冷却检测（30秒）
  if (now - player.lastAction < 30000) {
    const wait = Math.ceil((30000 - (now - player.lastAction)) / 1000);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再行动~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  player.lastAction = now;
  state.lastActionTime = now;

  // 计算破译准确度
  const accuracy = calculateDecodeAccuracy(guess, state.currentCode.solution, player.discoveredWords);
  
  let resultText = "";
  if (accuracy >= 0.8) {
    // 成功破译
    const baseScore = 15;
    const bonus = Math.floor(Object.keys(player.discoveredWords).length * 0.5); // 词库奖励
    const totalScore = baseScore + bonus;
    
    player.score += totalScore;
    player.decoded++;
    state.scores[alias] = (state.scores[alias] || 0) + totalScore;
    
    resultText = `🎉 破译成功！${alias} 获得 ${totalScore} 情报点\n`;
    if (bonus > 0) resultText += `📚 词库奖励：+${bonus}分\n`;
    resultText += `\n📖 正确译文：${state.currentCode.solution}`;
    
    // 生成新密电
    state.currentCode = generateEncodedMessage();
    state.codeHistory.push(state.currentCode);
    
    resultText += `\n\n📜 新密电已发布：\n${state.currentCode.encoded}`;
    
  } else if (accuracy >= 0.5) {
    // 部分正确
    const score = 8;
    player.score += score;
    state.scores[alias] = (state.scores[alias] || 0) + score;
    
    resultText = `⚠️ 部分破译！${alias} 获得 ${score} 情报点\n`;
    resultText += `💡 准确度：${Math.floor(accuracy * 100)}%，继续努力！`;
    
    // 给一个提示
    const unknownWords = state.currentCode.keywords.filter(word => !player.discoveredWords[word]);
    if (unknownWords.length > 0) {
      resultText += `\n🔍 提示：关注「${unknownWords[0]}」的含义`;
    }
  } else {
    resultText = `❌ 破译失败！准确度：${Math.floor(accuracy * 100)}%\n`;
    resultText += `💡 建议先使用「。密电试探」猜测更多词汇含义`;
  }

  _mg_saveState(state);
  seal.replyToSender(ctx, msg, resultText);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电破译"] = cmd_message_decode;

/** 计算破译准确度 */
function calculateDecodeAccuracy(guess, solution, discoveredWords) {
  const solutionWords = solution.split(/[，：\s]/).filter(w => w);
  const guessWords = guess.split(/[，：\s]/).filter(w => w);
  
  let matchCount = 0;
  solutionWords.forEach(word => {
    if (guessWords.some(g => g.includes(word) || word.includes(g))) {
      matchCount++;
    }
  });
  
  return matchCount / solutionWords.length;
}

/** 干扰其他玩家 */
const cmd_message_interfere = seal.ext.newCmdItemInfo();
cmd_message_interfere.name = "密电干扰";
cmd_message_interfere.help = "。密电干扰 目标假面名 —— 干扰指定玩家的破译行动";
cmd_message_interfere.solve = (ctx, msg, args) => {
  const uid = msg.sender.userId;
  const alias = _mg_aliasOf(uid);
  const targetAlias = args.getArgN(1)?.trim();
  const state = _mg_getState();

  if (!state.active) {
    seal.replyToSender(ctx, msg, "📭 游戏未进行中。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!state.players[uid]) {
    seal.replyToSender(ctx, msg, "⚠️ 请先使用「。密电报名」加入游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!targetAlias) {
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
  }

  const player = state.players[uid];
  const now = Date.now();
  
  // 冷却检测（60秒）
  if (now - player.lastAction < 60000) {
    const wait = Math.ceil((60000 - (now - player.lastAction)) / 1000);
    seal.replyToSender(ctx, msg, `🕰️ 请等待 ${wait} 秒后再行动~`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 查找目标玩家
  const targetUid = Object.keys(state.players).find(
    u => state.players[u].alias === targetAlias
  );

  if (!targetUid || targetUid === uid) {
    seal.replyToSender(ctx, msg, `❌ 未找到玩家「${targetAlias}」或不能干扰自己。`);
    return seal.ext.newCmdExecuteResult(true);
  }

  player.lastAction = now;
  state.lastActionTime = now;

  // 干扰成功
  player.score += 3;
  player.interfered++;
  state.scores[alias] = (state.scores[alias] || 0) + 3;

  // 目标玩家扣分
  state.players[targetUid].score = Math.max(0, state.players[targetUid].score - 2);
  state.scores[targetAlias] = Math.max(0, (state.scores[targetAlias] || 0) - 2);

  _mg_saveState(state);

  // 干扰效果描述
  const interfereMessages = [
    `📻 你成功干扰了 ${targetAlias} 的电台信号！`,
    `💥 你切断了 ${targetAlias} 的电话线路！`, 
    `🕵️ 你向 ${targetAlias} 发送了假情报！`,
    `🔦 你用手电筒干扰了 ${targetAlias} 的暗号接收！`,
    `📮 你拦截了 ${targetAlias} 的密信！`
  ];

  const randomMessage = interfereMessages[Math.floor(Math.random() * interfereMessages.length)];
  
  seal.replyToSender(ctx, msg, 
    `${randomMessage}\n\n` +
    `✅ ${alias} 获得 3 干扰点\n` +
    `❌ ${targetAlias} 被扣除 2 情报点`
  );
  
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电干扰"] = cmd_message_interfere;

/** 查看游戏状态 */
const cmd_message_status = seal.ext.newCmdItemInfo();
cmd_message_status.name = "密电状态";
cmd_message_status.help = "。密电状态 —— 查看当前密电风云战况";
cmd_message_status.solve = (ctx, msg) => {
  const state = _mg_getState();

  if (!state.active || Object.keys(state.players).length === 0) {
    seal.replyToSender(ctx, msg, "📭 密电风云尚未开始或无人参与。");
    return seal.ext.newCmdExecuteResult(true);
  }

  let statusText = `📻 密电风云·第 ${state.round} 轮\n\n`;
  
  if (state.currentCode) {
    statusText += `📜 当前密电：\n${state.currentCode.encoded}\n\n`;
  }

  // 玩家排名
  const players = Object.values(state.players);
  players.sort((a, b) => b.score - a.score);
  
  statusText += "🏆 玩家排名：\n";
  players.forEach((player, index) => {
    const rankIcons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"];
    const rankIcon = rankIcons[index] || `${index + 1}.`;
    const wordCount = Object.keys(player.discoveredWords || {}).length;
    statusText += `${rankIcon} ${player.alias} - ${player.score}分`;
    statusText += ` (词汇:${wordCount} 破译:${player.decoded} 干扰:${player.interfered})\n`;
  });

  statusText += `\n💡 可用指令：密电试探 | 密电破译 | 密电干扰 | 密电词库`;

  seal.replyToSender(ctx, msg, statusText);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电状态"] = cmd_message_status;

/** 结算本轮游戏 */
const cmd_message_end = seal.ext.newCmdItemInfo();
cmd_message_end.name = "密电结算";
cmd_message_end.help = "。密电结算 —— 结束本轮密电风云并公布结果（仅管理员）";
cmd_message_end.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 仅管理员可结算游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  const state = _mg_getState();

  if (!state.active) {
    seal.replyToSender(ctx, msg, "📭 游戏未进行中。");
    return seal.ext.newCmdExecuteResult(true);
  }

  // 计算最终排名
  const players = Object.values(state.players);
  players.sort((a, b) => b.score - a.score);
  
  let resultText = `🎊 密电风云·最终结算 🎊\n\n`;
  
  // 前三名特殊奖励
  const winners = players.slice(0, 3);
  if (winners.length > 0) {
    resultText += "🏆 优胜者：\n";
    const winnerIcons = ["🥇", "🥈", "🥉"];
    winners.forEach((player, index) => {
      resultText += `${winnerIcons[index]} ${player.alias} - ${player.score}分\n`;
    });
    resultText += "\n";
  }

  // 所有玩家成绩
  resultText += "📊 完整成绩：\n";
  players.forEach((player, index) => {
    const wordCount = Object.keys(player.discoveredWords || {}).length;
    resultText += `${index + 1}. ${player.alias} - ${player.score}分`;
    resultText += ` (词汇:${wordCount} 破译:${player.decoded} 干扰:${player.interfered})\n`;
  });

  // 特殊成就
  const bestDecoder = [...players].sort((a, b) => b.decoded - a.decoded)[0];
  const bestInterferer = [...players].sort((a, b) => b.interfered - a.interfered)[0];
  const bestVocab = [...players].sort((a, b) => Object.keys(b.discoveredWords || {}).length - Object.keys(a.discoveredWords || {}).length)[0];
  
  resultText += `\n🎯 特殊成就：\n`;
  resultText += `🔍 破译专家：${bestDecoder.alias} (${bestDecoder.decoded}次)\n`;
  resultText += `⚡ 干扰大师：${bestInterferer.alias} (${bestInterferer.interfered}次)\n`;
  resultText += `📚 词汇大师：${bestVocab.alias} (${Object.keys(bestVocab.discoveredWords || {}).length}个词汇)\n`;

  resultText += `\n感谢各位特工的参与！民国风云，暗流涌动...`;

  // 重置游戏状态
  state.active = false;
  state.round++;
  _mg_saveState(state);

  seal.replyToSender(ctx, msg, resultText);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电结算"] = cmd_message_end;

/** 强制结束游戏 */
const cmd_message_force_end = seal.ext.newCmdItemInfo();
cmd_message_force_end.name = "密电结束";
cmd_message_force_end.help = "。密电结束 —— 强制结束游戏并清空数据（仅管理员）";
cmd_message_force_end.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "⚠️ 仅管理员可结束游戏。");
    return seal.ext.newCmdExecuteResult(true);
  }

  _mg_saveState({});
  seal.replyToSender(ctx, msg, "🧹 密电风云数据已清空。");
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["密电结束"] = cmd_message_force_end;
ext.cmdMap["密电结束"] = cmd_message_force_end;