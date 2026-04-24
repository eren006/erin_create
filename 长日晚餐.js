// ==UserScript==
// @name         晚餐系统
// @author       长日将尽
// @version      2.4.0
// @description  独立的晚餐系统。自动读取“changriV1”插件中的角色名与管理列表。支持多游戏框架，俄罗斯轮盘可自定义弹巢数和子弹数。
// @timestamp    1740292337
// @license      CC BY-NC-SA
// ==/UserScript==

/**
 * 说明：
 * 1. 核心依赖：通过 seal.ext.find('changriV1') 寻找主插件。
 * 2. 角色读取：从主插件的 'Character_Platform' 存储中匹配当前 UID 对应的角色名。
 * 3. 权限控制：从主插件的 'a_adminList' 存储中读取管理员列表。
 * 4. 游戏框架：晚餐数据新增 game 字段，存放当前进行的游戏（type + state）。
 * 5. 新增游戏：俄罗斯轮盘（roulette）支持自定义总弹巢数和子弹数。
 */

let ext = seal.ext.find('dinner_system');
if (!ext) {
    ext = seal.ext.new("dinner_system", "长日将尽", "2.4.0");
    seal.ext.register(ext);
}

// 菜谱数据库
const DINNER_MENUS = {
    "现代中餐": ["东坡肉", "宫保鸡丁", "清蒸鲈鱼", "麻婆豆腐", "蒜蓉西兰花", "腌笃鲜", "扬州炒饭", "北京烤鸭", "佛跳墙", "松鼠鳜鱼", "辣子鸡丁", "回锅肉", "地三鲜", "西湖牛肉羹", "糖醋排骨", "荷叶粉蒸肉", "白灼虾", "蚝油生菜", "黑椒牛柳", "赛螃蟹", "开水白菜", "虫草花炖鸡汤", "蜜汁叉烧", "金汤肥牛", "蒜泥白肉", "响油鳝糊", "四喜丸子", "大煮干丝", "避风塘炒蟹", "文思豆腐", "酸菜鱼", "老鸭汤", "麻辣小龙虾", "西湖醋鱼", "金牌脆皮乳鸽", "剁椒鱼头", "上汤娃娃菜", "干炒牛河", "XO酱爆龙虾", "陈皮红豆沙", "杨枝甘露"],
    "现代西餐": ["惠灵顿牛排", "法式洋葱汤", "香煎干贝", "松露意面", "凯撒沙拉", "波士顿龙虾", "红酒炖牛肉", "提拉米苏", "奶油蘑菇汤", "战斧牛排", "芝士焗蜗牛", "玛格丽特披萨", "西班牙海鲜饭", "意式生牛肉片", "法式烤春鸡", "香煎三文鱼", "芦笋培根卷", "南瓜浓汤", "墨鱼汁面", "托斯卡纳炖鸡", "班尼迪克蛋", "维也纳炸牛排", "澳洲和牛配芦笋", "海鲜周打汤", "法式油封鸭", "德式脆皮猪肘", "炭烤羊排", "英式炸鱼薯条", "马赛鱼汤", "慢煮低温鲑鱼", "法式鹅肝配烤面包", "黑松露烩饭", "纽约芝士蛋糕", "舒芙蕾", "波尔多炖羊腱", "香煎比目鱼", "意式番茄罗勒浓汤", "生蚝拼盘", "焦糖布丁"],
    "古代中餐": ["花炊鹌子", "炙金肠", "洗手蟹", "羹腊兔", "莲花鸭签", "拨鱼儿", "玉灌肺", "金乳酥", "鹅鸭排蒸", "山煮羊", "螃蟹酿橙", "胡炮肉", "广利肉", "五味杏酪鹅", "荔枝白腰子", "绣球乾贝", "黄金鸡", "白云猪手", "瑞雪汤", "珍珠糜", "麒麟脯", "二十四桥明月夜", "剔缕鸡", "雪霞羹", "羊皮太极软脂", "假蛤蜊", "酒炊淮白", "煿金煮玉", "拨霞供", "槐叶冷淘", "广寒糕", "煨芋头", "暗香汤", "蜜饯雕花", "胡饼", "驼蹄羹", "过门香", "通花软牛肠", "光明虾炙", "玉笛谁家听落梅"],
    "古代西餐": ["烤野猪肉", "蜂蜜炖鹅", "香料葡萄酒", "中世纪黑面包", "麦芽糊", "盐渍鹿肉", "肉豆蔻烤鱼", "无花果挞", "炖孔雀", "孔雀开屏肉馅饼", "杏仁牛奶粥", "藏红花炖鸡", "肉桂烤苹果", "野味肉冻", "姜汁炖梨", "烤鲟鱼", "蜂蜜柠檬酒", "公鸡汤", "黄油烤野兔", "香草羊排", "烤大天鹅", "芜菁炖肉", "大麦浓汤", "鼠尾草烤猪", "香草醋渍鲱鱼", "燕麦饼干", "杜松子烤肉", "黑布丁", "苹果酒炖蹄髈", "盐烤整头公牛", "玫瑰水炖雏鸡", "龙涎香布丁", "香料馅饼", "酸葡萄汁煎肉", "欧当归炖鲜鱼", "藏红花杏仁奶油", "烤白鹭", "松露灰烬煨蛋"],
    "诡秘深渊": ["不可名状的触手羹", "深潜者之卵", "米戈真菌刺身", "发光的紫色浓汤", "蠕动的肉块饼", "拉莱耶深海藻泥", "旧日支配者的低语吐司", "黄衣之王的祭礼酒", "混乱无序的炖煮", "疯狂的眼球果冻", "虚空行者的心脏", "纳克亚之影的蛛丝糖", "修格斯半流体慕斯", "远古种族的遗迹罐头", "格拉基的尖刺烤串", "冷之高原的冻肉"],
    "赛博未来": ["合成蛋白块", "营养液胶囊(草莓味)", "人造合成和牛", "霓虹酒精饮料", "增强现实全息布丁", "高浓缩能量棒", "实验室培植细胞肉", "电子羊肉串", "0卡路里数字汽水", "金属味觉感官调节片", "深度冻结脱水蔬菜", "仿生鳗鱼冻", "垃圾场回收零件餐(装饰用)", "神经连接感应咖啡", "纳米机器人清洁餐", "低层区大杂烩"]
};

// ========================
// 核心逻辑：读取主插件存储
// ========================
function getChangriRoleName(ctx, msg) {
    let crExt = seal.ext.find('changriV1');
    if (!crExt) { 
        return msg.sender.nickname;
    }

    try {
        let rawData = crExt.storageGet("a_private_group");
        if (!rawData) return msg.sender.nickname;

        let charPlatform = JSON.parse(rawData);
        // 去除平台前缀，得到纯 uid
        const currentUid = msg.sender.userId.replace(/^[a-z]+:/i, ""); // 匹配 "qq:"、"wx:" 等并移除

        for (let platform in charPlatform) {
            let platformData = charPlatform[platform];
            for (let name in platformData) {
                if (Array.isArray(platformData[name]) && platformData[name][0] === currentUid) {
                    console.log(name);
                    return name;
                }
            }
        }
    } catch (e) {
        console.log("晚餐系统读取主插件数据失败: " + e.message);
    }
    return msg.sender.nickname;
}

// 权限检查
function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;

    let crExt = seal.ext.find('changriV1');
    if (!crExt) return false;

    try {
        let rawAdmin = crExt.storageGet("a_adminList");
        if (!rawAdmin) return false;

        let a_adminList = JSON.parse(rawAdmin);
        const parts = msg.sender.userId.split(':');
        const platform = parts[0];
        const pureUid = parts[1];

        return a_adminList[platform] && a_adminList[platform].includes(pureUid);
    } catch (e) {
        return false;
    }
}

// ========================
// 晚餐数据存取（支持兼容旧版）
// ========================

function getDinnerData() {
    const raw = ext.storageGet("dinner_system_data");
    if (!raw) return null;
    let data = JSON.parse(raw);
    // 兼容旧版：若存在 bubbleGame 且无 game，则迁移
    if (data.bubbleGame && !data.game) {
        data.game = {
            type: "bubble",
            state: data.bubbleGame
        };
        delete data.bubbleGame;
        // 立即保存迁移后的数据
        ext.storageSet("dinner_system_data", JSON.stringify(data));
    }
    return data;
}

function saveDinnerData(data) {
    ext.storageSet("dinner_system_data", JSON.stringify(data));
}

// ========================
// 辅助函数
// ========================

/**
 * 将一组数字转换为区间表示（如 [1,2,3,5,7,8,9] => "1-3,5,7-9"）
 */
function numbersToInterval(nums) {
    if (!nums.length) return "";
    nums.sort((a, b) => a - b);
    const ranges = [];
    let start = nums[0], end = nums[0];
    for (let i = 1; i <= nums.length; i++) {
        if (i < nums.length && nums[i] === end + 1) {
            end = nums[i];
        } else {
            ranges.push(start === end ? `${start}` : `${start}-${end}`);
            if (i < nums.length) {
                start = end = nums[i];
            }
        }
    }
    return ranges.join(",");
}

/**
 * 获取下一个有效座位的索引（循环），跳过null
 * @param {Array} list 座位列表（可能含 null）
 * @param {number} current 当前索引
 * @returns {number} 下一个有效索引，若没有有效座位返回 -1
 */
function nextValidSeat(list, current) {
    const len = list.length;
    for (let i = 1; i <= len; i++) {
        const idx = (current + i) % len;
        if (list[idx] !== null) return idx;
    }
    return -1;
}

/**
 * 获取下一个存活玩家的座位索引（基于存活列表）
 * @param {Array} alive 存活玩家的座位索引数组（已排序）
 * @param {number} current 当前索引（在alive中的位置）
 * @returns {number} 下一个存活玩家的座位索引，如果alive为空返回-1
 */
function nextAliveSeat(alive, currentSeat) {
    if (alive.length === 0) return -1;
    // 找到currentSeat在alive中的位置
    let pos = alive.indexOf(currentSeat);
    if (pos === -1) {
        // 如果当前座位不在存活列表中（理论上不应发生），返回第一个
        return alive[0];
    }
    // 循环下一个
    return alive[(pos + 1) % alive.length];
}

// ========================
// 指令逻辑
// ========================

// 1. 开始晚餐
let cmd_start = seal.ext.newCmdItemInfo();
cmd_start.name = "开始晚餐";
cmd_start.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);

    let num = parseInt(cmdArgs.getArgN(1));
    let era = cmdArgs.getArgN(2) || "现代中餐";
    if (isNaN(num) || num <= 0) {
        seal.replyToSender(ctx, msg, "请输入正确的座位数，例如：.开始晚餐 5 现代西餐");
        return seal.ext.newCmdExecuteResult(true);
    }

    let dishes = (era === "无菜") ? [] : (DINNER_MENUS[era] || ["家常小菜"]).sort(() => 0.5 - Math.random()).slice(0, 5 + Math.floor(num / 3));

    let data = {
        status: "开始",
        max: num,
        era: era,
        dishes: dishes,
        list: new Array(num).fill(null),
        game: null // 清空可能残留的游戏
    };
    saveDinnerData(data);

    let text = `🍽️ 【晚餐开始】\n风格：${era}\n`;
    if (dishes.length > 0) text += `菜谱：${dishes.join("、")}\n`;
    text += "────────────\n";
    for (let i = 0; i < num; i++) text += `${i + 1}. （空位）\n`;
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始晚餐"] = cmd_start;

// 2. 入座
// 2. 入座（修改版：禁止抢占他人座位）
let cmd_sit = seal.ext.newCmdItemInfo();
cmd_sit.name = "入座";
cmd_sit.solve = (ctx, msg, cmdArgs) => {
    let data = getDinnerData();
    if (!data || data.status !== "开始") return seal.ext.newCmdExecuteResult(true);

    let index = parseInt(cmdArgs.getArgN(1)) - 1;
    if (isNaN(index) || index < 0 || index >= data.max) {
        seal.replyToSender(ctx, msg, `请输入有效的座位号 (1-${data.max})`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const roleName = getChangriRoleName(ctx, msg);

    // 查找玩家当前座位（如果有）
    let currentSeat = -1;
    for (let i = 0; i < data.list.length; i++) {
        if (data.list[i] === roleName) {
            currentSeat = i;
            break;
        }
    }

    // 检查目标座位是否已被他人占据
    if (data.list[index] !== null && data.list[index] !== roleName) {
        seal.replyToSender(ctx, msg, `❌ 座位 ${index+1} 已被 ${data.list[index]} 占据，请选择其他空位。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 如果目标座位就是自己当前座位，可提示或不操作
    if (currentSeat === index) {
        seal.replyToSender(ctx, msg, `你已经在座位 ${index+1} 上了。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 否则，进行换座（从旧座位移除，坐到新座位）
    if (currentSeat !== -1) {
        data.list[currentSeat] = null;
    }
    data.list[index] = roleName;
    saveDinnerData(data);

    let text = `🍽️ 【晚餐席位 - ${data.era}】\n`;
    text += "────────────\n";
    for (let i = 0; i < data.max; i++) {
        text += `${i + 1}. ${data.list[i] || "（空位）"}\n`;
    }
    seal.replyToSender(ctx, msg, text);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["入座"] = cmd_sit;

// 3. 结束晚餐（同时结束游戏）
let cmd_end = seal.ext.newCmdItemInfo();
cmd_end.name = "结束晚餐";
cmd_end.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) return seal.ext.newCmdExecuteResult(true);
    // 直接重置为结束状态，清除所有游戏
    saveDinnerData({ status: "结束" });
    seal.replyToSender(ctx, msg, "🏁 晚餐已结束。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束晚餐"] = cmd_end;

// 4. 重置晚餐（清空状态）
let cmd_reset_dinner = seal.ext.newCmdItemInfo();
cmd_reset_dinner.name = "重置晚餐";
cmd_reset_dinner.help = "。重置晚餐 - 管理员重置晚餐系统状态（清空当前晚餐和游戏）";
cmd_reset_dinner.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, `该指令仅限管理员使用`);
        return seal.ext.newCmdExecuteResult(true);
    }
    saveDinnerData({ status: "结束" });
    seal.replyToSender(ctx, msg, "🍽️ 晚餐系统已重置，当前无进行中的晚餐。");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["重置晚餐"] = cmd_reset_dinner;

// ========================
// 泡泡游戏
// ========================

// 5. 开始泡泡（管理员）
let cmd_start_bubble = seal.ext.newCmdItemInfo();
cmd_start_bubble.name = "开始泡泡";
cmd_start_bubble.help = "。开始泡泡 总数量 珊瑚数量 —— 管理员开启戳泡泡游戏，总数量≤100，珊瑚数量＜总数量";

cmd_start_bubble.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const total = parseInt(cmdArgs.getArgN(1));
    const coral = parseInt(cmdArgs.getArgN(2));

    if (isNaN(total) || isNaN(coral) || total <= 0 || coral <= 0 || coral >= total) {
        seal.replyToSender(ctx, msg, "❌ 参数错误！格式：。开始泡泡 总数量 珊瑚数量\n要求：总数量≤100，珊瑚数量＜总数量且＞0");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (total > 100) {
        seal.replyToSender(ctx, msg, "❌ 总数量不能超过100");
        return seal.ext.newCmdExecuteResult(true);
    }

    const data = getDinnerData();
    if (!data || data.status !== "开始") {
        seal.replyToSender(ctx, msg, "❌ 晚餐尚未开始，请先使用「开始晚餐」");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (data.game) {
        seal.replyToSender(ctx, msg, "❌ 已有游戏在进行中，请先结束当前游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查是否有有效座位
    const validSeats = data.list.filter(name => name !== null);
    if (validSeats.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 晚餐席位上没有任何玩家，无法开始游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 初始化泡泡数组
    const bubbles = new Array(total).fill(null).map(() => ({ hasCoral: false, popped: false }));

    // 随机放置珊瑚
    let coralIndices = new Set();
    while (coralIndices.size < coral) {
        const idx = Math.floor(Math.random() * total);
        coralIndices.add(idx);
    }
    coralIndices.forEach(idx => { bubbles[idx].hasCoral = true; });

    // 找到第一个有效座位索引
    const firstSeatIndex = data.list.findIndex(name => name !== null);

    // 构建泡泡游戏状态
    const bubbleState = {
        active: true,
        totalBubbles: total,
        coralCount: coral,
        coralsFound: 0,
        bubbles: bubbles,
        currentIndex: firstSeatIndex,
        remainingBubbles: numbersToInterval(Array.from({ length: total }, (_, i) => i + 1))
    };

    data.game = {
        type: "bubble",
        state: bubbleState
    };
    saveDinnerData(data);

    let reply = `🫧 戳泡泡游戏开始！\n总泡泡数：${total}，其中藏着 ${coral} 个珊瑚✨\n当前剩余泡泡：${bubbleState.remainingBubbles}\n`;
    reply += `请按座位顺序依次戳泡泡（当前轮到：${data.list[firstSeatIndex]}）`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始泡泡"] = cmd_start_bubble;

// 6. 戳泡泡（玩家）
let cmd_pop_bubble = seal.ext.newCmdItemInfo();
cmd_pop_bubble.name = "戳泡泡";
cmd_pop_bubble.help = "。戳泡泡 编号 —— 按顺序戳破泡泡，戳中珊瑚有惊喜";

cmd_pop_bubble.solve = (ctx, msg, cmdArgs) => {
    const roleName = getChangriRoleName(ctx, msg);
    const num = parseInt(cmdArgs.getArgN(1));
    if (isNaN(num) || num <= 0) {
        seal.replyToSender(ctx, msg, "❌ 请输入正确的泡泡编号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const data = getDinnerData();
    if (!data || data.status !== "开始" || !data.game || data.game.type !== "bubble") {
        seal.replyToSender(ctx, msg, "❌ 当前没有进行中的戳泡泡游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    const game = data.game.state;
    if (!game.active) {
        seal.replyToSender(ctx, msg, "❌ 游戏已结束");
        return seal.ext.newCmdExecuteResult(true);
    }

    const bubbleIndex = num - 1;
    if (bubbleIndex < 0 || bubbleIndex >= game.totalBubbles) {
        seal.replyToSender(ctx, msg, `❌ 泡泡编号无效，应在 1-${game.totalBubbles} 之间`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查轮次
    const currentSeatName = data.list[game.currentIndex];
    if (!currentSeatName) {
        seal.replyToSender(ctx, msg, "❌ 游戏状态异常：当前座位无人");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (roleName !== currentSeatName) {
        seal.replyToSender(ctx, msg, `❌ 现在轮到 ${currentSeatName} 戳泡泡，请等待`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查泡泡是否已破
    if (game.bubbles[bubbleIndex].popped) {
        seal.replyToSender(ctx, msg, "❌ 这个泡泡已经被戳破了");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 戳破泡泡
    game.bubbles[bubbleIndex].popped = true;
    const hasCoral = game.bubbles[bubbleIndex].hasCoral;
    let message = "";

    if (hasCoral) {
        game.coralsFound++;
        message = `✨ 哇！你戳到了一个珊瑚！ (${game.coralsFound}/${game.coralCount})`;
        if (game.coralsFound === game.coralCount) {
            game.active = false;
            data.game = null; // 游戏结束，清除游戏
            message += `\n🎉 恭喜！所有珊瑚都被找到了！游戏结束！`;
        }
    } else {
        message = `💧 噗～只是个普通泡泡。`;
    }

    // 如果游戏还在进行，更新剩余泡泡区间并移动轮次
    if (game.active) {
        const remainingIndices = [];
        for (let i = 0; i < game.totalBubbles; i++) {
            if (!game.bubbles[i].popped) remainingIndices.push(i + 1);
        }
        game.remainingBubbles = numbersToInterval(remainingIndices);

        const nextIdx = nextValidSeat(data.list, game.currentIndex);
        if (nextIdx === -1) {
            game.active = false;
            data.game = null;
            message += `\n⚠️ 所有座位已空，游戏提前结束。`;
        } else {
            game.currentIndex = nextIdx;
        }
    }

    saveDinnerData(data);

    let reply = `🫧 你戳破了 ${num} 号泡泡！\n${message}\n`;
    if (game.active) {
        reply += `当前剩余泡泡：${game.remainingBubbles}\n`;
        reply += `现在轮到：${data.list[game.currentIndex]}`;
    } else {
        reply += `游戏已结束。`;
    }
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["戳泡泡"] = cmd_pop_bubble;

// ========================
// 俄罗斯轮盘游戏（支持自定义弹巢数和子弹数）
// ========================

// 7. 开始轮盘（管理员）
let cmd_start_roulette = seal.ext.newCmdItemInfo();
cmd_start_roulette.name = "开始轮盘";
cmd_start_roulette.help = "。开始轮盘 [总弹巢数=6] [子弹数=1] —— 管理员开启俄罗斯轮盘，总弹巢数≥1，子弹数≤总弹巢数且≥1";

cmd_start_roulette.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    let totalChambers = parseInt(cmdArgs.getArgN(1));
    let bulletCount = parseInt(cmdArgs.getArgN(2));

    // 参数解析：支持 0、1、2 个参数
    if (isNaN(totalChambers) || totalChambers <= 0) {
        // 无参数或无效：默认总弹巢6，子弹1
        totalChambers = 6;
        bulletCount = 1;
    } else if (isNaN(bulletCount) || bulletCount <= 0) {
        // 只有一个有效参数：视为子弹数，总弹巢默认为6
        bulletCount = totalChambers;
        totalChambers = 6;
        // 确保子弹数不超过总弹巢
        if (bulletCount > totalChambers) bulletCount = totalChambers;
    } else {
        // 两个参数都提供了，进行范围校验
        if (bulletCount > totalChambers) bulletCount = totalChambers; // 自动修正
    }

    // 确保子弹数至少为1
    if (bulletCount < 1) bulletCount = 1;

    const data = getDinnerData();
    if (!data || data.status !== "开始") {
        seal.replyToSender(ctx, msg, "❌ 晚餐尚未开始，请先使用「开始晚餐」");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (data.game) {
        seal.replyToSender(ctx, msg, "❌ 已有游戏在进行中，请先结束当前游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取所有有人的座位索引
    const aliveSeats = [];
    for (let i = 0; i < data.list.length; i++) {
        if (data.list[i] !== null) aliveSeats.push(i);
    }
    if (aliveSeats.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 晚餐席位上没有任何玩家，无法开始游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 初始化弹巢，随机放置子弹
    const chambers = new Array(totalChambers).fill(false);
    let placed = 0;
    while (placed < bulletCount) {
        const idx = Math.floor(Math.random() * totalChambers);
        if (!chambers[idx]) {
            chambers[idx] = true;
            placed++;
        }
    }

    // 随机选择一个起始弹膛（模拟旋转弹仓）
    const startChamber = Math.floor(Math.random() * totalChambers);

    // 游戏状态
    const rouletteState = {
        active: true,
        totalChambers: totalChambers,
        chambers: chambers,           // 布尔数组，true表示有子弹
        currentChamber: startChamber, // 当前要击发的弹膛索引
        aliveSeats: aliveSeats,       // 存活玩家的座位索引数组（按原顺序）
        currentSeat: aliveSeats[0]     // 从第一个存活玩家开始
    };

    data.game = {
        type: "roulette",
        state: rouletteState
    };
    saveDinnerData(data);

    // 构建回复
    let reply = `🔫 俄罗斯轮盘开始！\n`;
    reply += `总弹巢：${totalChambers}，子弹数：${bulletCount}\n`;
    reply += `────────────\n`;
    reply += `当前存活玩家：\n`;
    aliveSeats.forEach(idx => {
        reply += `座位 ${idx+1}：${data.list[idx]}\n`;
    });
    reply += `────────────\n`;
    reply += `第一枪由 ${data.list[rouletteState.currentSeat]} 开始，请使用「开枪」指令。`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开始轮盘"] = cmd_start_roulette;

// 8. 开枪（玩家）
let cmd_shoot = seal.ext.newCmdItemInfo();
cmd_shoot.name = "开枪";
cmd_shoot.help = "。开枪 —— 当前玩家对自己扣动扳机";

cmd_shoot.solve = (ctx, msg, cmdArgs) => {
    const roleName = getChangriRoleName(ctx, msg);

    const data = getDinnerData();
    if (!data || data.status !== "开始" || !data.game || data.game.type !== "roulette") {
        seal.replyToSender(ctx, msg, "❌ 当前没有进行中的俄罗斯轮盘游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    const game = data.game.state;
    if (!game.active) {
        seal.replyToSender(ctx, msg, "❌ 游戏已结束");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查当前玩家是否轮到
    const currentSeatIdx = game.currentSeat;
    const currentPlayer = data.list[currentSeatIdx];
    if (!currentPlayer) {
        // 理论上不应发生，但以防万一
        seal.replyToSender(ctx, msg, "❌ 游戏状态异常：当前座位无人");
        return seal.ext.newCmdExecuteResult(true);
    }
    if (roleName !== currentPlayer) {
        seal.replyToSender(ctx, msg, `❌ 现在轮到 ${currentPlayer} 开枪，请等待`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 扣动扳机
    const chamberIdx = game.currentChamber;
    const hasBullet = game.chambers[chamberIdx];
    let message = "";

    if (hasBullet) {
        // 中弹死亡
        message = `💥 砰！你中弹了... 玩家 ${currentPlayer} 死亡。`;
        // 从座位列表中移除
        data.list[currentSeatIdx] = null;
        // 从存活列表中移除
        game.aliveSeats = game.aliveSeats.filter(idx => idx !== currentSeatIdx);
        // 标记该弹膛已使用（其实可以不管，但为了逻辑清晰，我们可标记为false）
        game.chambers[chamberIdx] = false; // 子弹已击发
    } else {
        // 安全
        message = `😮‍💨 咔嚓～是空枪，你活下来了。`;
        // 该弹膛已使用，标记为false（即使原来是false）
        game.chambers[chamberIdx] = false; // 其实本来也是false，但显式标记一下无妨
    }

    // 移动弹膛到下一个位置（基于总弹巢数取模）
    game.currentChamber = (game.currentChamber + 1) % game.totalChambers;

    // 检查游戏是否结束
    let gameEnded = false;
    if (game.aliveSeats.length === 0) {
        gameEnded = true;
        message += `\n💀 所有玩家都死了... 游戏结束。`;
    } else if (game.aliveSeats.length === 1) {
        gameEnded = true;
        const winnerIdx = game.aliveSeats[0];
        message += `\n🏆 恭喜 ${data.list[winnerIdx]} 成为最后的幸存者！`;
    } else {
        // 还有多人存活，检查是否所有子弹都已击发（即所有有子弹的位置都已变成false）
        const remainingBullets = game.chambers.filter(b => b === true).length;
        if (remainingBullets === 0) {
            gameEnded = true;
            message += `\n🎉 所有子弹都已打空，所有存活玩家均幸存！游戏结束。`;
        }
    }

    if (gameEnded) {
        game.active = false;
        data.game = null; // 清除游戏
        saveDinnerData(data);
        seal.replyToSender(ctx, msg, message);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 游戏继续，确定下一个开枪的玩家
    if (hasBullet) {
        // 如果当前玩家死亡，下一个从存活列表中取第一个（按原座位顺序）
        // 注意：当前玩家已从aliveSeats中移除，所以下一个就是aliveSeats[0]（如果还有的话）
        game.currentSeat = game.aliveSeats[0];
    } else {
        // 安全，按顺序取下一个存活玩家
        game.currentSeat = nextAliveSeat(game.aliveSeats, currentSeatIdx);
    }

    saveDinnerData(data);

    // 构建回复
    let nextPlayer = data.list[game.currentSeat];
    let reply = `🔫 你扣动了扳机...\n${message}\n`;
    reply += `────────────\n`;
    reply += `当前存活玩家：\n`;
    game.aliveSeats.forEach(idx => {
        reply += `座位 ${idx+1}：${data.list[idx]}\n`;
    });
    reply += `───────────\n`;
    reply += `现在轮到 ${nextPlayer} 开枪。`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["开枪"] = cmd_shoot;

// ========================
// 通用游戏指令
// ========================

// 9. 结束游戏（管理员）
let cmd_end_game = seal.ext.newCmdItemInfo();
cmd_end_game.name = "结束游戏";
cmd_end_game.help = "。结束游戏 - 管理员强制结束当前进行的游戏（保留晚餐）";
cmd_end_game.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const data = getDinnerData();
    if (!data || !data.game) {
        seal.replyToSender(ctx, msg, "❌ 当前没有进行中的游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    const gameType = data.game.type;
    data.game = null;
    saveDinnerData(data);

    seal.replyToSender(ctx, msg, `🏁 已强制结束 ${gameType} 游戏。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["结束游戏"] = cmd_end_game;

// 10. 跳过（管理员）- 根据游戏类型执行跳过逻辑
let cmd_skip = seal.ext.newCmdItemInfo();
cmd_skip.name = "跳过";
cmd_skip.help = "。跳过 - 管理员跳过当前玩家的回合（仅支持带轮次的游戏）";
cmd_skip.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "该指令仅限管理员使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const data = getDinnerData();
    if (!data || data.status !== "开始" || !data.game) {
        seal.replyToSender(ctx, msg, "❌ 当前没有进行中的游戏");
        return seal.ext.newCmdExecuteResult(true);
    }

    const game = data.game;
    if (game.type === "bubble") {
        // 泡泡游戏的跳过逻辑
        const state = game.state;
        if (!state.active) {
            seal.replyToSender(ctx, msg, "❌ 游戏已结束");
            return seal.ext.newCmdExecuteResult(true);
        }

        const nextIdx = nextValidSeat(data.list, state.currentIndex);
        if (nextIdx === -1) {
            state.active = false;
            data.game = null;
            saveDinnerData(data);
            seal.replyToSender(ctx, msg, "⚠️ 所有座位已空，游戏结束");
            return seal.ext.newCmdExecuteResult(true);
        }

        const skippedName = data.list[state.currentIndex];
        state.currentIndex = nextIdx;
        saveDinnerData(data);
        seal.replyToSender(ctx, msg, `⏭️ 已跳过 ${skippedName}，现在轮到 ${data.list[nextIdx]}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    else if (game.type === "roulette") {
        // 俄罗斯轮盘的跳过逻辑
        const state = game.state;
        if (!state.active) {
            seal.replyToSender(ctx, msg, "❌ 游戏已结束");
            return seal.ext.newCmdExecuteResult(true);
        }

        const currentSeat = state.currentSeat;
        const currentPlayer = data.list[currentSeat];
        // 跳过当前玩家：直接切换到下一个存活玩家，不扣扳机，弹膛不移动
        const nextSeat = nextAliveSeat(state.aliveSeats, currentSeat);
        if (nextSeat === -1) {
            // 理论上不应发生，因为至少还有当前玩家存活
            state.active = false;
            data.game = null;
            saveDinnerData(data);
            seal.replyToSender(ctx, msg, "⚠️ 没有其他存活玩家，游戏结束");
            return seal.ext.newCmdExecuteResult(true);
        }

        state.currentSeat = nextSeat;
        saveDinnerData(data);

        seal.replyToSender(ctx, msg, `⏭️ 已跳过 ${currentPlayer}，现在轮到 ${data.list[nextSeat]}`);
        return seal.ext.newCmdExecuteResult(true);
    }
    else {
        // 其他游戏类型，如果支持跳过则添加分支，否则提示不支持
        seal.replyToSender(ctx, msg, `❌ 当前游戏（${game.type}）不支持跳过指令`);
        return seal.ext.newCmdExecuteResult(true);
    }
};
ext.cmdMap["跳过"] = cmd_skip;

// ========================
// 11. 戳你一下（玩家互动，支持首尾循环相邻）
// ========================
let cmd_poke = seal.ext.newCmdItemInfo();
cmd_poke.name = "戳你一下";
cmd_poke.help = "。戳你一下 对方角色名 —— 对相邻座位的玩家戳一下（座位首尾也算相邻，需在晚餐进行中，冷却5分钟）";

cmd_poke.solve = (ctx, msg, cmdArgs) => {
    const targetName = cmdArgs.getArgN(1);
    if (!targetName) {
        seal.replyToSender(ctx, msg, "❌ 格式错误：。戳你一下 对方角色名");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取平台和发送者纯UID
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(`${platform}:`, "");

    // 读取主插件的角色绑定数据
    let crExt = seal.ext.find('changriV1');
    if (!crExt) {
        seal.replyToSender(ctx, msg, "❌ 未找到主插件 changriV1，无法使用此功能");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取 a_private_group
    let rawData = crExt.storageGet("a_private_group");
    if (!rawData) {
        seal.replyToSender(ctx, msg, "❌ 未找到角色绑定数据，请先使用「创建新角色」");
        return seal.ext.newCmdExecuteResult(true);
    }

    let charPlatform;
    try {
        charPlatform = JSON.parse(rawData);
    } catch (e) {
        seal.replyToSender(ctx, msg, "❌ 角色数据解析失败");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!charPlatform[platform]) charPlatform[platform] = {};

    // 获取发送者角色名
    const sendName = Object.entries(charPlatform[platform])
        .find(([_, val]) => val[0] === uid)?.[0];
    if (!sendName) {
        seal.replyToSender(ctx, msg, `❌ 你还没有绑定角色，请先使用「创建新角色」`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查目标是否存在
    const targetEntry = charPlatform[platform][targetName];
    if (!targetEntry) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetName}」的绑定信息`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ⏳ 冷却检查（5分钟）
    const cooldownKey = `poke_cooldown_${platform}:${uid}`;
    const lastPoke = parseInt(ext.storageGet(cooldownKey) || "0");
    const now = Date.now();
    const cooldownDuration = 1 * 60 * 1000; // 5分钟

    if (now - lastPoke < cooldownDuration) {
        const remaining = Math.ceil((cooldownDuration - (now - lastPoke)) / 60000);
        seal.replyToSender(ctx, msg, `⏳ 你戳得太快了，请等待 ${remaining} 分钟后再试`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取当前晚餐数据
    const data = getDinnerData();
    if (!data || data.status !== "开始") {
        seal.replyToSender(ctx, msg, "❌ 当前没有进行中的晚餐，无法戳人");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 座位数量必须至少为2才能进行相邻互动
    if (data.max < 2) {
        seal.replyToSender(ctx, msg, "❌ 当前晚餐只有1个座位，无法戳相邻的人");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 查找发送者和目标在座位列表中的索引
    let senderIdx = -1, targetIdx = -1;
    for (let i = 0; i < data.list.length; i++) {
        if (data.list[i] === sendName) senderIdx = i;
        if (data.list[i] === targetName) targetIdx = i;
    }

    if (senderIdx === -1) {
        seal.replyToSender(ctx, msg, `❌ 你还没有入座，请先「入座」`);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (targetIdx === -1) {
        seal.replyToSender(ctx, msg, `❌ 目标「${targetName}」不在晚餐座位上`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 禁止戳自己
    if (senderIdx === targetIdx) {
        seal.replyToSender(ctx, msg, `❌ 不能戳自己哦～`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 判断是否相邻（支持首尾循环）
    const isAdjacent = 
        Math.abs(senderIdx - targetIdx) === 1 || 
        (senderIdx === 0 && targetIdx === data.max - 1) || 
        (senderIdx === data.max - 1 && targetIdx === 0);

    if (!isAdjacent) {
        seal.replyToSender(ctx, msg, `❌ 你只能戳相邻座位的人（当前座位 ${senderIdx+1}，目标座位 ${targetIdx+1}）`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 更新冷却
    ext.storageSet(cooldownKey, now.toString());

    // 获取目标私密群信息
    const targetUid = targetEntry[0];
    const targetGroupId = targetEntry[1];

    // 构造发送给目标群的消息
    const pokeMsg = seal.newMessage();
    pokeMsg.messageType = "group";
    pokeMsg.sender = {};
    pokeMsg.sender.userId = `${platform}:${targetUid}`;
    pokeMsg.groupId = `${platform}-Group:${targetGroupId}`;
    const targetCtx = seal.createTempCtx(ctx.endPoint, pokeMsg);

    // 发送戳一下提醒
    const notice = `👆 ${sendName} 戳了你一下`;
    seal.replyToSender(targetCtx, pokeMsg, notice);

    // 回复发送者成功
    seal.replyToSender(ctx, msg, `✅ 你戳了 ${targetName} 一下，消息已送达。`);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["戳你一下"] = cmd_poke;