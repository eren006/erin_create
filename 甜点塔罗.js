// ==UserScript==
// @name         甜点塔罗
// @author       长日将尽
// @version      2.1.0
// @description  甜点主题的虚拟塔罗牌占卜，支持单张占卜、时间牌阵（过去·现在·未来）和决定牌阵（选择A·选择B）。仅供娱乐。
// @timestamp    2025-03-17
// @license      CC BY-NC-SA
// ==/UserScript//

/**
 * 甜点塔罗：随机抽取甜点主题的塔罗牌，含牌面场景、关键词、正逆位解读。
 * 新增决定牌阵，用于辅助二选一决策。
 * 牌义纯属虚构，仅供娱乐。
 */

let ext = seal.ext.find('dessert_tarot');
if (!ext) {
    ext = seal.ext.new('dessert_tarot', '长日将尽', '2.1.0');
    seal.ext.register(ext);
}

// 甜点塔罗牌组（扩充至30张）
const TAROT_DECK = [
    { 
        name: '提拉米苏',
        scene: '深夜咖啡馆，一位女子用银勺轻轻挖起一块提拉米苏，窗外霓虹灯闪烁，她的眼神迷离，仿佛沉浸在往事的涟漪中。',
        keywords: '爱情·回忆·层次',
        upright: '往日的甜蜜浮现，一段关系迎来转机，学会在苦甜交织中找到平衡。',
        reversed: '被过去的回忆困住，难以向前；情感上的自我欺骗。'
    },
    { 
        name: '马卡龙',
        scene: '阳光明媚的下午茶会，五颜六色的马卡龙堆叠成塔，贵妇们轻言浅笑，一只蝴蝶停留在粉色的马卡龙上。',
        keywords: '社交·精致·短暂',
        upright: '愉快的社交聚会，结识新朋友，享受当下的美好。',
        reversed: '表面功夫，虚伪的社交；过于追求形式而忽略本质。'
    },
    { 
        name: '黑森林蛋糕',
        scene: '幽暗的森林深处，月光透过树梢洒在布满樱桃的蛋糕上，一只黑猫蹲坐在旁，琥珀色的眼睛闪烁着神秘的光芒。',
        keywords: '神秘·诱惑·深度',
        upright: '探索内心深处的欲望，直面自己的阴影面，获得深度转化。',
        reversed: '被欲望控制，陷入混乱；隐藏的秘密即将暴露。'
    },
    { 
        name: '芝士蛋糕',
        scene: '老式烘焙坊的橱窗里，一块纽约芝士蛋糕放在木托盘上，旁边是一杯冒着热气的黑咖啡，墙上挂着泛黄的菜单。',
        keywords: '醇厚·稳定·满足',
        upright: '生活安稳，内心充实，享受简单而持久的幸福。',
        reversed: '过于固执，缺乏变化；情感上的腻烦。'
    },
    { 
        name: '泡芙',
        scene: '热闹的集市摊位上，刚出炉的泡芙散发着奶油香气，一个小女孩踮起脚尖，眼中满是期待，摊主慈祥地递给她一个。',
        keywords: '惊喜·机遇·空灵',
        upright: '意外之喜即将到来，抓住转瞬即逝的机会。',
        reversed: '期待落空，计划流产；内心空虚。'
    },
    { 
        name: '甜甜圈',
        scene: '清晨的街角，一个跑步的人停下来，从纸袋中拿出一个撒满糖霜的甜甜圈，阳光在他身后拉出长长的影子。',
        keywords: '循环·圆满·节制',
        upright: '事物进入良性循环，需要保持平衡，避免过度。',
        reversed: '陷入重复的困境，无法突破；放纵后的空虚。'
    },
    { 
        name: '拿破仑蛋糕',
        scene: '华丽的宴会厅里，侍者托着多层拿破仑蛋糕走向贵宾，金色烛台映照着层层酥皮，仿佛在诉说着奋斗的故事。',
        keywords: '成就·层次·努力',
        upright: '经过层层努力，终于获得成功，地位提升。',
        reversed: '努力白费，计划混乱；骄傲自满导致失败。'
    },
    { 
        name: '芒果慕斯',
        scene: '夏日海滩边，一个女孩捧着芒果慕斯杯，海浪轻拍她的脚踝，远处夕阳将天空染成橙粉色。',
        keywords: '阳光·活力·清新',
        upright: '充满活力与创造力，新开始，心情愉悦。',
        reversed: '能量低迷，缺乏动力；过度乐观导致忽视细节。'
    },
    { 
        name: '焦糖布丁',
        scene: '昏暗的爵士酒吧，台上的歌手低吟浅唱，台下一位男士用勺子敲开焦糖壳，露出嫩滑的布丁。',
        keywords: '甜蜜·伪装·本质',
        upright: '看清事物本质，甜蜜背后是真实的情感。',
        reversed: '被表面现象迷惑，虚伪的关系。'
    },
    { 
        name: '舒芙蕾',
        scene: '高级餐厅的后厨，主厨紧张地盯着烤箱，舒芙蕾正在膨胀，成败在此一举，学徒们屏息以待。',
        keywords: '短暂·膨胀·消逝',
        upright: '珍惜当下的美好，它稍纵即逝；勇敢表达情感。',
        reversed: '期待过高而失望，感情迅速冷却。'
    },
    { 
        name: '华夫饼',
        scene: '圣诞集市的热气中，一个华夫饼摊前排着长队，情侣们分享着淋满枫糖浆的华夫饼，雪花落在他们的肩头。',
        keywords: '网格·选择·日常',
        upright: '面临多个选择，需要理性分析；日常生活的小确幸。',
        reversed: '选择困难，犹豫不决；生活陷入单调。'
    },
    { 
        name: '冰淇淋',
        scene: '炎热的夏日公园，孩子们围着冰淇淋车，一位老人坐在长椅上，慢慢舔着甜筒，嘴角浮现出孩童般的笑容。',
        keywords: '清凉·融化·释放',
        upright: '释放压力，放松心情，享受片刻清凉。',
        reversed: '情绪冷漠，关系降温；过于急躁导致失控。'
    },
    { 
        name: '巧克力熔岩',
        scene: '情人节夜晚，烛光晚餐的桌上，巧克力熔岩蛋糕被切开，热巧克力缓缓流出，映照着爱人对视的眼眸。',
        keywords: '热情·爆发·内在',
        upright: '压抑的情感即将爆发，真诚面对内心。',
        reversed: '情绪失控，伤害他人；内在的冰冷。'
    },
    { 
        name: '班戟',
        scene: '宁静的庭院里，一位少女正在学习制作班戟，她小心翼翼地将芒果包裹进软皮，阳光透过树叶洒在她的手上。',
        keywords: '包裹·柔软·包容',
        upright: '包容他人，接纳不同；用柔软的方式处理问题。',
        reversed: '过度包容失去自我，内心脆弱。'
    },
    { 
        name: '果仁糖',
        scene: '复古糖果店的玻璃罐里，装满五彩的果仁糖，一只戴着白手套的手伸入罐中，挑选着最亮的那一颗。',
        keywords: '坚硬·内核·保护',
        upright: '保护好自己的核心，坚韧不拔；内在的智慧。',
        reversed: '外壳过厚，拒绝沟通；内心的脆弱被击碎。'
    },
    // 新增牌（以下为扩充）
    { 
        name: '抹茶千层',
        scene: '日式茶室里，一壶抹茶旁边放着切好的抹茶千层蛋糕，竹帘外是微缩庭院，石灯笼旁落着几片枫叶。',
        keywords: '宁静·和谐·沉淀',
        upright: '内心归于平静，需要沉淀思考，和谐的人际关系。',
        reversed: '烦躁不安，关系失衡；过度追求完美。'
    },
    { 
        name: '红丝绒蛋糕',
        scene: '复古剧院的后台，一位芭蕾舞者在休息时切开红丝绒蛋糕，鲜红的蛋糕层如同她的舞鞋，白色奶酪霜如裙摆。',
        keywords: '热情·艺术·展现',
        upright: '展现自我，释放激情，在艺术或创作中获得成就。',
        reversed: '表演过度，虚伪做作；隐藏真实情感。'
    },
    { 
        name: '可丽露',
        scene: '波尔多清晨的酒窖，橡木桶旁放着几个铜模可丽露，焦脆的外壳与柔软的内里，如同这座城市的历史与现代交融。',
        keywords: '传统·反差·底蕴',
        upright: '尊重传统，在反差中找到平衡，深厚的底蕴带来好运。',
        reversed: '守旧不变，内外不一；流于表面。'
    },
    { 
        name: '椰丝小方',
        scene: '海南的椰林里，一位阿婆正在制作椰丝小方，椰丝洒落在竹匾上，远处的海浪声和着椰风。',
        keywords: '纯真·自然·质朴',
        upright: '回归本真，享受简单质朴的快乐，自然之力护佑。',
        reversed: '过于幼稚，逃避现实；被世俗污染。'
    },
    { 
        name: '蒙布朗',
        scene: '阿尔卑斯山脚下的甜点店，橱窗里的蒙布朗如同勃朗峰，栗子泥条条分明，糖粉似山顶积雪。',
        keywords: '攀登·收获·满足',
        upright: '经过努力攀登，即将收获丰硕成果，内心满足。',
        reversed: '目标过高难以实现，贪多嚼不烂。'
    },
    { 
        name: '巧克力脆筒',
        scene: '嘉年华的摩天轮下，孩子们举着巧克力脆筒，彩色的糖针洒落，笑声随着摩天轮旋转升空。',
        keywords: '童真·欢乐·冒险',
        upright: '保持童心，勇敢尝试新事物，欢乐常伴。',
        reversed: '冒险过度，玩世不恭；内心空虚。'
    },
    { 
        name: '果挞',
        scene: '普罗旺斯的果园里，新鲜水果铺满挞皮，阳光把水果染得透亮，蜜蜂在周围嗡嗡作响。',
        keywords: '丰饶·分享·当下',
        upright: '生活丰饶，与亲友分享喜悦，享受当下的美好。',
        reversed: '贪得无厌，不愿分享；错失良机。'
    },
    { 
        name: '麻薯',
        scene: '京都的祭典上，穿着浴衣的少女排队买麻薯，软糯的团子在竹签上旋转，豆粉飘香。',
        keywords: '柔软·韧性·粘合',
        upright: '以柔克刚，韧性带来机遇，人际关系粘合。',
        reversed: '缺乏原则，过度依赖；无法独立。'
    },
    { 
        name: '姜饼人',
        scene: '圣诞夜的壁炉前，孩子们在装饰姜饼人，窗外的雪静静落下，姜饼人的微笑仿佛在祝福。',
        keywords: '传统·祝福·守护',
        upright: '家庭和睦，传统带来祝福，有守护者陪伴。',
        reversed: '孤独无依，传统束缚；祝福变诅咒。'
    },
    // 新增6张牌（共30张）
    { 
        name: '杏仁豆腐',
        scene: '江南水乡的茶馆里，一碗杏仁豆腐放在雕花木窗边，桂花飘落，倒映着白墙黛瓦。',
        keywords: '清雅·温润·恬淡',
        upright: '心境恬淡，生活如流水般温润，小事中见真谛。',
        reversed: '过于寡淡，缺乏激情；情感上的冷漠。'
    },
    { 
        name: '芋泥蛋糕',
        scene: '夜市的小摊上，老板切开一块芋泥蛋糕，紫色的芋泥层层叠叠，蒸汽中混杂着香芋的甜香。',
        keywords: '朴实·乡愁·温暖',
        upright: '回归本心，家庭温暖，旧友重逢带来慰藉。',
        reversed: '沉溺过去，无法向前；被旧物束缚。'
    },
    { 
        name: '蝴蝶酥',
        scene: '巴黎街头的面包店，刚出炉的蝴蝶酥金黄酥脆，一位老绅士买了两只，一只给自己，一只给身旁的老伴。',
        keywords: '分享·轻盈·陪伴',
        upright: '与他人分享快乐，轻松的陪伴带来灵感。',
        reversed: '形单影只，孤独感；过于轻浮不踏实。'
    },
    { 
        name: '闪电泡芙',
        scene: '赛马场的观众席，一位贵妇人优雅地咬了一口闪电泡芙，巧克力的光泽与她的珍珠项链相映成趣。',
        keywords: '速度·机遇·果断',
        upright: '抓住稍纵即逝的机遇，果断决策带来成功。',
        reversed: '犹豫不决错失良机；行动过快反招失败。'
    },
    { 
        name: '年轮蛋糕',
        scene: '德国黑森林的木屋里，壁炉火苗跳动，桌上放着一块切开的年轮蛋糕，一圈圈如岁月刻度。',
        keywords: '时光·积累·耐心',
        upright: '岁月沉淀带来智慧，耐心积累终有回报。',
        reversed: '虚度光阴，积累不足；急于求成。'
    },
    { 
        name: '棉花糖',
        scene: '游乐园的摩天轮下，小女孩举着一大团粉蓝色的棉花糖，糖丝在阳光下闪闪发光，仿佛握着一朵云。',
        keywords: '梦幻·轻盈·纯真',
        upright: '梦想即将实现，保持纯真之心，轻盈前行。',
        reversed: '过于梦幻不切实际，被虚假美好迷惑。'
    }
];

// 工具函数：随机抽取一张牌（包含正逆位）
function drawOneCard() {
    const card = TAROT_DECK[Math.floor(Math.random() * TAROT_DECK.length)];
    const isReversed = Math.random() < 0.5;
    return {
        card,
        isReversed,
        orientation: isReversed ? '逆位' : '正位',
        interpretation: isReversed ? card.reversed : card.upright
    };
}

// 工具函数：抽取指定数量的不重复牌（用于牌阵）
function drawCardsWithoutReplacement(count) {
    if (count > TAROT_DECK.length) {
        throw new Error(`牌组数量不足，最多可抽取 ${TAROT_DECK.length} 张`);
    }
    // 复制牌组并打乱
    const shuffled = [...TAROT_DECK];
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    // 取前 count 张并随机决定正逆位
    const selected = shuffled.slice(0, count);
    return selected.map(card => {
        const isReversed = Math.random() < 0.5;
        return {
            card,
            isReversed,
            orientation: isReversed ? '逆位' : '正位',
            interpretation: isReversed ? card.reversed : card.upright
        };
    });
}


// 格式化单张牌输出
function formatCard(cardData, position = null) {
    const { card, orientation, interpretation } = cardData;
    let result = `🍰 ${card.name}（${orientation}）\n`;
    if (position) result = `【${position}】\n` + result;
    result += `─────────────\n`;
    result += `✨ 场景：${card.scene}\n\n`;
    result += `✨ ${card.keywords}\n\n`;
    result += `${interpretation}\n`;
    return result;
}

// ==================== 单张占卜指令 ====================
let cmd_draw = seal.ext.newCmdItemInfo();
cmd_draw.name = '甜点占卜';
cmd_draw.help = '。甜点占卜 —— 抽取一张甜点塔罗牌，获取今日启示（仅供娱乐）';
cmd_draw.solve = (ctx, msg, cmdArgs) => {
    const cardData = drawOneCard();
    let reply = formatCard(cardData);
    reply += `─────────────\n`;
    reply += `✨ 仅供娱乐，愿生活如甜点般甜美 ✨`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['甜点占卜'] = cmd_draw;

// 别名
let cmd_tarot = seal.ext.newCmdItemInfo();
cmd_tarot.name = '甜点塔罗';
cmd_tarot.help = '。甜点塔罗 —— 同“甜点占卜”指令';
cmd_tarot.solve = (ctx, msg, cmdArgs) => {
    return cmd_draw.solve(ctx, msg, cmdArgs);
};
ext.cmdMap['甜点塔罗'] = cmd_tarot;

// ==================== 牌阵指令（支持时间和决定，且保证牌不重复） ====================
let cmd_spread = seal.ext.newCmdItemInfo();
cmd_spread.name = '甜点牌阵';
cmd_spread.help = '。甜点牌阵 [类型] —— 类型：时间（默认）/决定。\n· 时间：三张牌代表过去、现在、未来。\n· 决定：两张牌分别代表选择A和选择B。';
cmd_spread.solve = (ctx, msg, cmdArgs) => {
    const type = cmdArgs.getArgN(1) || '时间'; // 默认时间
    const typeLower = type.toLowerCase();

    if (typeLower === '时间' || typeLower === 'time' || typeLower === '') {
        // 时间牌阵：三张牌（不重复）
        try {
            const [past, present, future] = drawCardsWithoutReplacement(3);
            let reply = `🍰 甜点塔罗 · 时间牌阵（过去·现在·未来）\n`;
            reply += `════════════\n\n`;
            reply += formatCard(past, '过去');
            reply += `\n`;
            reply += formatCard(present, '现在');
            reply += `\n`;
            reply += formatCard(future, '未来');
            reply += `════════════\n`;
            reply += `✨ 仅供娱乐，愿你的过去、现在、未来皆有甜蜜相伴 ✨`;
            seal.replyToSender(ctx, msg, reply);
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 牌组数量不足，请联系作者增加牌组。`);
        }
        return seal.ext.newCmdExecuteResult(true);
    } 
    else if (typeLower === '决定' || typeLower === 'choice' || typeLower === 'decision') {
        // 决定牌阵：两张牌（不重复）
        try {
            const [choiceA, choiceB] = drawCardsWithoutReplacement(2);
            let reply = `🍰 甜点塔罗 · 决定牌阵（选择A vs 选择B）\n`;
            reply += `════════════\n\n`;
            reply += formatCard(choiceA, '选择A');
            reply += `\n`;
            reply += formatCard(choiceB, '选择B');
            reply += `════════════\n`;
            reply += `✨ 两张牌分别代表不同选择的启示，请用心感受。\n✨ 仅供娱乐，最终决定还需听从内心 ✨`;
            seal.replyToSender(ctx, msg, reply);
        } catch (e) {
            seal.replyToSender(ctx, msg, `❌ 牌组数量不足，请联系作者增加牌组。`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }
    else {
        seal.replyToSender(ctx, msg, `❌ 未知牌阵类型“${type}”，可用类型：时间 / 决定`);
        return seal.ext.newCmdExecuteResult(true);
    }
};
ext.cmdMap['甜点牌阵'] = cmd_spread;