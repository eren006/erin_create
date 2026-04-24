// ==UserScript==
// @name         修仙界·灵宝寻珍
// @version      1.0
// @author       长日将尽
// @description  修仙主题的灵宝寻宝、赠送和窃取系统，扩展版灵宝池
// ==/UserScript==

var ext = seal.ext.find('修仙界寻宝');
if (!ext) {
  ext = seal.ext.new('修仙界寻宝', '长日将尽', '1.0');
  seal.ext.register(ext);
}

// ==================== 存储配置 ====================
const STORE_KEY = 'song_registry'; // 保持内部key不变

/** 读取与保存 */
function getReg() {
  return JSON.parse(ext.storageGet(STORE_KEY) || '{}');
}

function saveReg(obj) {
  ext.storageSet(STORE_KEY, JSON.stringify(obj || {}));
}

// 获取公告群ID，优先使用存储的值，否则使用默认值
function getAnnounceGroupId() {
    const stored = ext.storageGet('global_announce_group');
    return (stored && stored.trim()) ? stored.trim() : ANNOUNCE_GROUP_ID;
}

// 设置公告群ID
function setAnnounceGroupId(value) {
    ext.storageSet('global_announce_group', value);
}

/** ====== 兼容 & 规范化 ====== */
function normalize(reg) {
  return reg;
}

/** ====== 管理员判定 ====== */
function isUserAdmin(ctx, msg) {
  const platform = msg.platform;
  const uid = msg.sender.userId.replace(`${platform}:`, '');
  if (msg.isMaster || msg.isAdmin) return true;
  try {
    const a_adminList = JSON.parse(ext.storageGet('a_adminList') || '{}');
    return Array.isArray(a_adminList[platform]) && a_adminList[platform].includes(uid);
  } catch(e) { return false; }
}

// ==================== 修仙界·灵宝大全 ====================
// 共计120件灵宝、丹药、法器、功法等

const SONG_GIFTS = {
    "S001": {
        name: "青莲剑意残卷",
        description: "上古剑修所留，竹简上刻有凌厉剑痕，观摩可悟青莲剑意。剑痕如莲绽放，隐隐有剑鸣之声，蕴藏一丝不灭剑意。",
        value: 25,
        rarity: "稀有"
    },
    "S002": {
        name: "鎏金护脉丹",
        description: "四品灵丹，丹纹如鎏金流转。可稳固经脉，突破时服用能增加三成成功率，对筑基以下修士效果显著，丹香清幽。",
        value: 35,
        rarity: "珍贵"
    },
    "S003": {
        name: "万法归宗图摹本",
        description: "绢本画卷，绘有三千大道缩影，每一笔都蕴含微弱道韵。参悟可提升功法领悟力，虽非真迹，亦是难得的悟道之物。",
        value: 80,
        rarity: "传奇"
    },
    "S004": {
        name: "玄冰寒铁",
        description: "极北深渊所产玄铁，触之冰寒彻骨，可锻造法宝胚胎。其色如墨，隐隐有冰晶纹路，是炼制冰属性飞剑的上佳材料。",
        value: 18,
        rarity: "精致"
    },
    "S005": {
        name: "蟠龙玉佩",
        description: "古玉雕琢，内蕴一丝真龙之气。佩之可辟邪静心，加快灵气吸收。玉中蟠龙若隐若现，温养日久可化出龙威。",
        value: 45,
        rarity: "神圣"
    },
    "S006": {
        name: "灵羽拂尘",
        description: "以五阶灵鹤尾羽炼制，拂尘轻扫可驱散低级煞气。尘丝柔韧，灌注灵力后可化作千丝束缚敌人，是修士随身雅器。",
        value: 22,
        rarity: "优雅"
    },
    "S007": {
        name: "铜雀衔丹炉",
        description: "黄铜所铸，炉身丹雀回首，口衔炉盖。炼丹时火力均匀，可提升一成熟丹率。炉内自带中和法阵，减少炸炉风险。",
        value: 38,
        rarity: "雅致"
    },
    "S008": {
        name: "紫竹简·逍遥游",
        description: "紫竹片所制，刻有逍遥宗心法残篇。阅之如临云海，心旷神怡，可助修士明心见性，突破心境瓶颈。",
        value: 32,
        rarity: "文雅"
    },
    "S009": {
        name: "金丝楠木棋盘",
        description: "整块万年金丝楠木制成，木纹如灵脉流动。棋盘刻有周天星斗阵图，对弈时可推演阵法变化，乃阵修至宝。",
        value: 65,
        rarity: "贵重"
    },
    "S010": {
        name: "血玉灵酒杯",
        description: "血色灵玉雕琢，注入灵酒会泛起霞光。杯底天生莲花纹，可过滤酒中毒素，饮之可增益修为，为修士宴饮珍品。",
        value: 42,
        rarity: "华丽"
    },
    "S011": {
        name: "云锦天蚕衣",
        description: "天蚕丝织就，轻如云霞，可挡筑基全力一击。衣上绣有聚灵阵，行走间自动吸纳灵气，乃法袍中的上品。",
        value: 48,
        rarity: "华服"
    },
    "S012": {
        name: "龙尾砚",
        description: "深海龙尾石所制，砚堂中有天然龙形纹理。研墨时墨汁含微薄灵气，所书符箓威力增强一成，文修最爱。",
        value: 28,
        rarity: "文房"
    },
    "S013": {
        name: "玉骨梳",
        description: "五阶妖兽腿骨炼化，梳齿如白玉。梳理头发时可滋养神识，长期使用能壮大神魂，亦是一件辅助修炼法器。",
        value: 52,
        rarity: "梳妆"
    },
    "S014": {
        name: "青瓷净瓶",
        description: "龙泉窑所出，瓶身有天青釉色。可储存灵液，保持灵气不散，亦可作为法器施展“甘露术”，滋养灵植。",
        value: 38,
        rarity: "瓷器"
    },
    "S015": {
        name: "犀角解毒杯",
        description: "通天犀角雕成，饮任何毒酒皆可化解。杯身有天然纹路，注入灵水会变红以示警示，是行走江湖必备。",
        value: 45,
        rarity: "珍玩"
    },
    "S016": {
        name: "绣云履",
        description: "云锦软底，绣有祥云纹，穿着可踏水而行。鞋底镶嵌轻身石，使修士身法更加灵动，为外门弟子所喜。",
        value: 20,
        rarity: "服饰"
    },
    "S017": {
        name: "灵犀簪",
        description: "千年灵犀角所制，簪头镶嵌月华石。可安神定魂，佩戴后不易被幻术所迷，且能增进夫妻修士默契。",
        value: 25,
        rarity: "首饰"
    },
    "S018": {
        name: "紫砂悟道壶",
        description: "宜兴灵泥烧制，壶身刻有“道法自然”。泡灵茶可凝聚茶香灵气，品之有助于悟道，是茶修至宝。",
        value: 40,
        rarity: "茶具"
    },
    "S019": {
        name: "竹编储物篓",
        description: "灵竹所编，内刻简易空间阵法。可容纳三尺见方物品，虽简陋却实用，为散修常用储物法器。",
        value: 12,
        rarity: "实用"
    },
    "S020": {
        name: "朱漆妆盒",
        description: "百年朱漆，盒面描金绘仙鹤灵芝。内分九格，可存放丹药、灵石等，盒盖设有防神识窥探的禁制。",
        value: 18,
        rarity: "妆匣"
    },
    "S021": {
        name: "素绢团扇",
        description: "冰蚕丝扇面，湘妃竹扇骨。扇面绘有云海仙山，摇动时可生清风，驱散暑气，亦能微扰低阶灵虫。",
        value: 22,
        rarity: "纳凉"
    },
    "S022": {
        name: "灵果蜜饯礼盒",
        description: "紫檀木盒内分十二格，盛有朱果、青灵果、玉枣等灵果蜜饯。食之可恢复少量灵力，甜而不腻。",
        value: 15,
        rarity: "食品"
    },
    "S023": {
        name: "文房四宝·灵韵套",
        description: "灵狐毫笔、松烟灵墨、玉版宣纸、龙尾砚。皆为修士书画专用，所书符箓灵气充沛，是入门符师必备。",
        value: 14,
        rarity: "文具"
    },
    "S024": {
        name: "福字灵符",
        description: "朱砂绘于金纸，内含微薄福缘之气。贴于洞府可保平安，也有极低几率带来好运，常作为见面礼。",
        value: 8,
        rarity: "装饰"
    },
    "S025": {
        name: "青竹笛",
        description: "百年灵竹所制，音色清越。吹奏时可施展安神曲，辅助修炼，亦能驭使低阶灵兽，为乐修喜爱。",
        value: 16,
        rarity: "乐器"
    },
    "S026": {
        name: "阴阳照妖镜",
        description: "青铜铸造，镜背刻有太极八卦。可照出隐匿的邪祟，灌注灵力能发出一道破邪之光，克制阴魂鬼物。",
        value: 30,
        rarity: "梳妆"
    },
    "S027": {
        name: "灵香囊",
        description: "绣有丁香花，内装安息香、沉香等。佩戴可提神醒脑，驱赶低阶毒虫，香气有助凝神修炼。",
        value: 18,
        rarity: "佩饰"
    },
    "S028": {
        name: "木雕碧落像",
        description: "万年檀香木雕，仙人端坐莲台，面容慈悲。可供奉于洞府，日日参拜可静心除魔，乃佛修至宝。",
        value: 35,
        rarity: "宗教"
    },
    "S029": {
        name: "九连环锁",
        description: "玄铁所制，环环相扣。内嵌灵力锁芯，需要以特定灵力顺序解开，常用来考验弟子悟性。",
        value: 28,
        rarity: "玩具"
    },
    "S030": {
        name: "油纸伞·烟雨",
        description: "灵竹伞骨，桐油伞面绘有江南雨景。撑开可避风雨，亦能抵挡练气期法术，为行走江湖良伴。",
        value: 10,
        rarity: "雨具"
    },
    "S031": {
        name: "青白玉带钩",
        description: "青白玉雕螭龙，玉质温润。系于腰间可聚拢灵气，辅助修炼，且能辟邪，为筑基修士常佩之物。",
        value: 40,
        rarity: "雅致"
    },
    "S032": {
        name: "剔红山水盒",
        description: "层层朱漆雕刻山水人物。内衬暗花绸，可珍藏丹药秘籍，漆盒本身亦是精美法器，可略微抵御神识探查。",
        value: 38,
        rarity: "华丽"
    },
    "S033": {
        name: "铜麒麟镇纸",
        description: "铜铸麒麟，腹中藏有灵珠，移动时叮当响可提醒主人。镇压书卷同时，也能镇住书房煞气。",
        value: 22,
        rarity: "文房"
    },
    "S034": {
        name: "鸳鸯戏水枕套",
        description: "锦缎枕套，绣有鸳鸯戏水。内填安神草，入睡可增长神识，适合双修道侣使用。",
        value: 16,
        rarity: "家居"
    },
    "S035": {
        name: "青花灵纹碗",
        description: "瓷胎细腻，绘有缠枝莲纹。注入灵米粥可保温三日，碗底有微小聚灵阵，长期使用滋养身体。",
        value: 30,
        rarity: "瓷器"
    },
    "S036": {
        name: "玛瑙念珠",
        description: "一百零八颗火玛瑙，每颗内含一丝火灵之力。持之修炼火系功法可增益，拨动时能静心驱魔。",
        value: 42,
        rarity: "宗教"
    },
    "S037": {
        name: "灵竹凉席",
        description: "三百年灵竹篾编成，触感清凉，可隔绝地煞之气。夏夜卧于其上，灵气自动温养经脉，助益睡眠。",
        value: 14,
        rarity: "实用"
    },
    "S038": {
        name: "金漆百鸟盒",
        description: "黑漆底描金百鸟朝凤，内分多格，可存放灵符、丹药。漆盒本身有禁制，可防止孩童误开。",
        value: 26,
        rarity: "收纳"
    },
    "S039": {
        name: "白玉兰花簪",
        description: "羊脂白玉雕成兰花，花瓣薄如蝉翼。插入发髻可汇聚灵气于百会穴，辅助突破瓶颈。",
        value: 34,
        rarity: "首饰"
    },
    "S040": {
        name: "铜暖炉·凝火",
        description: "黄铜手炉，内刻凝火阵。放入灵石可发热三日，冬日修炼必备，且能散发淡淡灵香，安抚心神。",
        value: 20,
        rarity: "暖具"
    },
    "S041": {
        name: "梅花手帕",
        description: "素罗帕，四角绣梅，一角绣“暗香浮动”。可用来擦拭法器，本身有净尘效果，是女修雅物。",
        value: 10,
        rarity: "佩饰"
    },
    "S042": {
        name: "粉青茶盏",
        description: "斗笠盏，釉色粉青如春水。注茶时可见茶汤中灵气旋绕，品茗能涤荡经脉杂质。",
        value: 18,
        rarity: "茶具"
    },
    "S043": {
        name: "紫檀笔架",
        description: "紫檀雕五峰山形，峰间有高士论道。架笔时可温养笔中灵气，使符笔更加灵验。",
        value: 15,
        rarity: "文房"
    },
    "S044": {
        name: "云纹腰带",
        description: "锦缎腰带，金线绣云纹，带扣为螭龙衔珠。系上可提升半成身法速度，为低阶修士实用装备。",
        value: 22,
        rarity: "服饰"
    },
    "S045": {
        name: "铜莲香插",
        description: "黄铜铸莲叶托莲花，花心有孔插香。焚香时烟雾如莲开，可净化洞府灵气。",
        value: 12,
        rarity: "香具"
    },
    "S046": {
        name: "竹编提篮",
        description: "六角眼编法，轻便结实。内衬防漏灵油纸，可携带灵果灵酒，是外出访友佳具。",
        value: 10,
        rarity: "实用"
    },
    "S047": {
        name: "天青鼎炉",
        description: "鼎式香炉，釉色天青，炉盖镂云纹。焚香时烟气如云海，可用于供奉或辅助冥想。",
        value: 28,
        rarity: "香具"
    },
    "S048": {
        name: "步步生莲鞋垫",
        description: "千层布绣莲花，穿上后行走无声，且能略微增加敏捷，是修士长途跋涉的好帮手。",
        value: 8,
        rarity: "服饰"
    },
    "S049": {
        name: "红木算盘",
        description: "红木边框，乌木象牙珠。可用来计算灵石收支，亦可作为法器施展“数术·灵爆”，较为少见。",
        value: 20,
        rarity: "工具"
    },
    "S050": {
        name: "铜豆灯",
        description: "青铜豆形灯，点燃灵油可照明十二时辰。灯焰不受风吹，适合洞府夜读。",
        value: 16,
        rarity: "照明"
    },
    "S051": {
        name: "玉壶春灵瓶",
        description: "粉青釉，器形优美。可插灵花或存放灵酒，瓶颈有微缩聚灵阵，保持内容物新鲜。",
        value: 24,
        rarity: "瓷器"
    },
    "S052": {
        name: "喜鹊登梅门帘",
        description: "棉布绣喜鹊梅花，有阻隔蚊虫和低阶灵虫之效，同时添喜气，为洞府常用。",
        value: 18,
        rarity: "家居"
    },
    "S053": {
        name: "竹制书架",
        description: "灵竹榫卯结构，三层可调节。放置功法玉简，可保持玉简灵气不散，方便取用。",
        value: 22,
        rarity: "文房"
    },
    "S054": {
        name: "虎头铜铃",
        description: "青铜虎头铃，铃声清脆。可挂于洞府门口预警，亦可作乐器，震慑低阶妖兽。",
        value: 12,
        rarity: "装饰"
    },
    "S055": {
        name: "梅子青酒壶",
        description: "执壶式，釉色如青梅。斟酒时酒线不断，可温酒且保持灵酒灵气，适合宴饮。",
        value: 26,
        rarity: "酒具"
    },
    "S056": {
        name: "莲纹坐垫",
        description: "圆形棉垫，内填荞麦壳。绣有莲花，坐之可隔绝地气湿寒，辅助长时间打坐。",
        value: 14,
        rarity: "家居"
    },
    "S057": {
        name: "榉木棋盒",
        description: "内含黑白灵石子，棋盘刻星斗阵。对弈可锻炼神识，是弟子课余消遣。",
        value: 20,
        rarity: "玩具"
    },
    "S058": {
        name: "铜盆架",
        description: "黄铜三足架，雕缠枝莲。可放置铜盆洗漱，也可作为临时灯架，实用稳重。",
        value: 18,
        rarity: "家居"
    },
    "S059": {
        name: "天青餐具套",
        description: "碗碟汤盆六件，釉面光洁。日常使用可净化食物中微量杂质，长期有益健康。",
        value: 16,
        rarity: "餐具"
    },
    "S060": {
        name: "银线竹帘",
        description: "素纱绣银线竹林，透光保隐私。微风拂过竹影摇曳，有助修士静心。",
        value: 20,
        rarity: "家居"
    },
    "S061": {
        name: "竹根茶盘",
        description: "整块竹根雕琢，有导流槽。不吸水，茶席上可汇集灵茶余香，提升品茗体验。",
        value: 18,
        rarity: "茶具"
    },
    "S062": {
        name: "仙鹤衔芝烛台",
        description: "一对青铜烛台，鹤颈修长，嘴衔烛盘。点燃灵烛，鹤影投墙如活物，极具意境。",
        value: 16,
        rarity: "照明"
    },
    "S063": {
        name: "葵口笔洗",
        description: "粉青釉葵口形，内底平坦。洗笔时可滋养笔毫，亦可用于养小型灵植菖蒲。",
        value: 15,
        rarity: "文房"
    },
    "S064": {
        name: "鱼戏莲荷包",
        description: "锦缎心形荷包，盘金绣金鱼。可存放灵石碎银，开口有抽绳，系于腰间防遗失。",
        value: 10,
        rarity: "佩饰"
    },
    "S065": {
        name: "紫檀衣架",
        description: "紫檀木制，横梁雕如意云头。可挂法袍，散发淡淡木香，防虫防潮。",
        value: 12,
        rarity: "家居"
    },
    "S066": {
        name: "黄铜汤婆子",
        description: "暖壶形，内可装热水或灵液。冬日置于被中保暖，也可温养丹药，方便实用。",
        value: 22,
        rarity: "暖具"
    },
    "S067": {
        name: "莲蓬香插",
        description: "粉青釉莲蓬形，莲子孔可插线香。焚香时如莲生香，小巧便携，可随身静心。",
        value: 14,
        rarity: "香具"
    },
    "S068": {
        name: "牡丹桌布",
        description: "棉布绣缠枝牡丹，铺于石桌可隔绝寒湿，增添雅致，适合待客。",
        value: 16,
        rarity: "家居"
    },
    "S069": {
        name: "灵竹躺椅",
        description: "老竹制成，椅背可调角度。夏日置于庭院，纳凉小憩，竹香淡淡，有助恢复神识。",
        value: 25,
        rarity: "家具"
    },
    "S070": {
        name: "饕餮门环",
        description: "青铜铺首，叩击声浑厚。可震慑宵小，门环内藏微型预警阵法，保洞府平安。",
        value: 18,
        rarity: "装饰"
    },
    "S071": {
        name: "荷叶盖罐",
        description: "梅子青釉，罐盖荷叶形。密封性好，可存放灵茶或丹药，保持药效不散。",
        value: 20,
        rarity: "茶具"
    },
    "S072": {
        name: "四季山水屏风",
        description: "四扇绢本，绣春夏秋冬。可分隔洞府空间，屏风本身有微薄灵气，调节室内气候。",
        value: 45,
        rarity: "家居"
    },
    "S073": {
        name: "紫檀浮雕屏风",
        description: "六扇紫檀，浮雕溪山行旅图。可作大型隔断，木香浓郁，有助凝神修炼。",
        value: 38,
        rarity: "家居"
    },
    "S074": {
        name: "铜火盆·暖阳",
        description: "青铜炭火盆，盆沿可暖手。冬日置于厅堂，可供多人取暖，亦可温酒煮茶。",
        value: 24,
        rarity: "暖具"
    },
    "S075": {
        name: "青瓷油灯",
        description: "油灯式，灯盘浅平。注入灵油点燃，光晕柔和，不伤眼，适合夜读。",
        value: 14,
        rarity: "照明"
    },
    "S076": {
        name: "百子嬉戏被面",
        description: "大红锦缎，金线绣百子图。喜庆吉祥，新婚或添丁贺礼，蕴含多子多福之意。",
        value: 30,
        rarity: "家居"
    },
    "S077": {
        name: "三层花架",
        description: "灵竹制，阶梯状。可摆灵植，错落有致，竹子经过炭化防虫。",
        value: 16,
        rarity: "家居"
    },
    "S078": {
        name: "铜壶·烹泉",
        description: "黄铜水壶，藤条缠柄。烧灵泉水快速，煮茶时发出轻鸣，可辨水温。",
        value: 20,
        rarity: "厨具"
    },
    "S079": {
        name: "荷叶边果盘",
        description: "天青釉，盘沿荷叶翻卷。盛放灵果，视觉清凉，亦可用于待客。",
        value: 18,
        rarity: "餐具"
    },
    "S080": {
        name: "蝶恋花床帐",
        description: "素纱绣银线蝶恋花，防蚊虫且浪漫。夜晚点灯，蝶影投帐，如梦似幻。",
        value: 35,
        rarity: "家居"
    },
    "S081": {
        name: "柏木浴桶",
        description: "柏木打造，铁箍加固。沐浴时加入灵草，可洗髓伐毛，消除疲劳。",
        value: 28,
        rarity: "卫浴"
    },
    "S082": {
        name: "黄铜脸盆",
        description: "铜盆，盆外錾刻连年有余。导热快，冬日热水不易凉，洗漱实用。",
        value: 18,
        rarity: "卫浴"
    },
    "S083": {
        name: "博山香薰炉",
        description: "粉青釉，盖雕山峦，烟从孔出如云雾。焚香丸可模拟仙境氛围，辅助冥想。",
        value: 26,
        rarity: "香具"
    },
    "S084": {
        name: "如意窗帘钩",
        description: "铜制鎏金，如意形。钩住窗帘，美观且实用，雕刻云纹。",
        value: 12,
        rarity: "家居"
    },
    "S085": {
        name: "竹簸箕",
        description: "细竹篾编，前薄后宽。清扫庭院落叶，轻便耐用，也可用于收集灵草残渣。",
        value: 8,
        rarity: "工具"
    },
    "S086": {
        name: "广锁·灵钥",
        description: "黄铜广锁，锁面铺首衔环。钥匙需灵力催动，可防普通人开启，保护私物。",
        value: 15,
        rarity: "工具"
    },
    "S087": {
        name: "六方花盆",
        description: "粉青釉六方盆，透气性好。栽种灵兰、菖蒲，与青瓷相得益彰，文人雅物。",
        value: 16,
        rarity: "园艺"
    },
    "S088": {
        name: "针线包·慈母线",
        description: "锦缎书册形，内藏针线灵布。可修补法袍，线中掺有灵蚕丝，缝补后更结实。",
        value: 10,
        rarity: "工具"
    },
    "S089": {
        name: "柏木米缸",
        description: "柏木制，防虫防潮。储存灵米可保持灵气不散，盖雕五谷丰登。",
        value: 20,
        rarity: "厨具"
    },
    "S090": {
        name: "铜茶匙",
        description: "黄铜贝壳形匙头，舀取灵茶。避免手触，保持茶叶品质，茶道小器。",
        value: 8,
        rarity: "茶具"
    },
    "S091": {
        name: "斗笠酒盅",
        description: "天青釉一对，盅身斜直。品灵酒时感受灵气温度，青瓷与酒香交融。",
        value: 14,
        rarity: "酒具"
    },
    "S092": {
        name: "荞壳安神枕",
        description: "长条枕，内填荞麦壳，绣鸳鸯。助眠安神，可调节头型，修士必备。",
        value: 16,
        rarity: "家居"
    },
    "S093": {
        name: "三层蒸笼",
        description: "灵竹蒸笼，透气性好。蒸制灵膳时可保留灵气，竹香渗入食物，别有风味。",
        value: 18,
        rarity: "厨具"
    },
    "S094": {
        name: "铜锅铲",
        description: "黄铜铲，导热快。翻炒灵膳时均匀受热，铜离子有益健康。",
        value: 12,
        rarity: "厨具"
    },
    "S095": {
        name: "四味调料罐",
        description: "青瓷小坛，分别刻盐、糖、酱、醋。罐内微缩保鲜阵，厨房必备。",
        value: 14,
        rarity: "厨具"
    },
    "S096": {
        name: "连年有余围裙",
        description: "棉布围裙，绣鲤鱼莲花。防油污，下厨时增添烟火气，实用美观。",
        value: 10,
        rarity: "服饰"
    },
    "S097": {
        name: "银杏砧板",
        description: "整块银杏木，天然抗菌。切灵菜不伤刀刃，使用日久包浆温润。",
        value: 8,
        rarity: "厨具"
    },
    "S098": {
        name: "铜水瓢",
        description: "黄铜深瓢，舀灵泉水。耐用不生锈，铜离子抑菌，水缸边必备。",
        value: 10,
        rarity: "厨具"
    },
    "S099": {
        name: "天青饭钵",
        description: "敛口钵，釉色天青。盛灵米饭可保温，手感稳重，日常餐具。",
        value: 12,
        rarity: "餐具"
    },
    "S100": {
        name: "岁岁平安抹布",
        description: "双层棉布，绣岁岁平安。吸水性强，可擦拭法器桌面，虽小却精致。",
        value: 6,
        rarity: "工具"
    },
    // 新增灵宝101-120 寓意祥瑞、道侣、前程等
    "S101": {
        name: "龙凤呈祥佩",
        description: "和田白玉雕龙凤，中间同心结。定情信物，佩戴可增进双修默契，受天道庇佑。",
        value: 55,
        rarity: "定情"
    },
    "S102": {
        name: "松鹤延年图",
        description: "绢本设色，九鹤翱翔古松间。祝寿佳礼，蕴含长寿道韵，挂于洞府可添福瑞。",
        value: 60,
        rarity: "祝寿"
    },
    "S103": {
        name: "锦绣前程囊",
        description: "蜀锦香囊，金线绣前程似锦。赠予后辈，寓意仙途光明，内含桂花丁香，香气励志。",
        value: 25,
        rarity: "前程"
    },
    "S104": {
        name: "莲生贵子锁",
        description: "纯金长命锁，浮雕莲花童子。赠新生儿，护佑平安健康，金光温润。",
        value: 45,
        rarity: "诞辰"
    },
    "S105": {
        name: "和合二仙玉雕",
        description: "青玉雕和合二仙，一人持荷，一人捧盒。贺新婚，祝福琴瑟和鸣。",
        value: 48,
        rarity: "婚庆"
    },
    "S106": {
        name: "鲤鱼跃龙门笔架",
        description: "紫檀雕鲤鱼跃龙门，三鲤逆流。勉励学子金榜题名，可架三支符笔。",
        value: 35,
        rarity: "科考"
    },
    "S107": {
        name: "福禄寿三星瓷",
        description: "青瓷塑福禄寿三星，笑容可掬。摆放家中可添吉祥气运，受散修喜爱。",
        value: 42,
        rarity: "祥瑞"
    },
    "S108": {
        name: "八宝食盒",
        description: "红漆描金八边形，内分八格装灵点。盖面八吉祥图案，节日馈赠佳品。",
        value: 30,
        rarity: "吉祥"
    },
    "S109": {
        name: "四君子团扇",
        description: "四柄一组，绘梅兰竹菊，配咏物诗。赠文人雅士，志趣相投。",
        value: 38,
        rarity: "雅赠"
    },
    "S110": {
        name: "平安如意佩",
        description: "白玉如意头，刻“平安”二字。赠远行亲友，祈愿一路顺遂，玉质莹润。",
        value: 32,
        rarity: "平安"
    },
    "S111": {
        name: "花开富贵屏",
        description: "四扇绢本绘牡丹芍药等富贵花。乔迁或开张贺礼，寓意富贵荣华。",
        value: 52,
        rarity: "富贵"
    },
    "S112": {
        name: "岁寒三友轴",
        description: "纸本水墨松竹梅，象征君子品格。赠挚友，喻友谊经霜不凋。",
        value: 40,
        rarity: "友谊"
    },
    "S113": {
        name: "麒麟送子钗",
        description: "金钗雕麒麟背驮童子，嵌红宝石眼。赠新婚妇人，祝早生贵子。",
        value: 50,
        rarity: "子嗣"
    },
    "S114": {
        name: "一团和气瓷塑",
        description: "白瓷笑面僧人，圆融可爱。赠同僚，寓意和气生财，和睦相处。",
        value: 28,
        rarity: "和气"
    },
    "S115": {
        name: "金玉满堂摆件",
        description: "青玉鱼缸，三条金鱼嵌金片。商贾贺礼，象征财源广进。",
        value: 65,
        rarity: "财源"
    },
    "S116": {
        name: "琴瑟和鸣炉",
        description: "一对青铜炉，一雕琴纹一雕瑟纹。贺新婚，寓意夫妻恩爱。",
        value: 46,
        rarity: "姻缘"
    },
    "S117": {
        name: "步步高升带",
        description: "锦缎腰带绣云梯纹，银扣官帽形。赠仕途中人，祝愿平步青云。",
        value: 36,
        rarity: "仕途"
    },
    "S118": {
        name: "福如东海寿桃盘",
        description: "青瓷寿桃形盘，塑九颗寿桃。长者寿辰贺礼，祈长寿安康。",
        value: 34,
        rarity: "长寿"
    },
    "S119": {
        name: "喜上眉梢盒",
        description: "漆器妆盒，螺钿喜鹊登梅。赠待嫁女子，寓意喜事临门。",
        value: 42,
        rarity: "喜庆"
    },
    "S120": {
        name: "一帆风顺船模",
        description: "红木雕三桅帆船，张满风帆。赠远行或经商者，祝一帆风顺。",
        value: 44,
        rarity: "远行"
    },
    // 青云剑冢专属 (S121~S140)
    "S121": { name: "青锋残剑", description: "剑冢中出土的残破古剑，剑刃虽缺，剑气犹存。可熔炼入本命飞剑，增加锋芒。", value: 12, rarity: "凡品" },
    "S122": { name: "剑意晶石", description: "蕴含剑修毕生剑意的结晶，捏碎可短暂领悟一道凌厉剑意。", value: 28, rarity: "精品" },
    "S123": { name: "铸剑灵砂", description: "极北寒铁砂，加入剑胚中可使飞剑更加锋利耐久。", value: 8, rarity: "凡品" },
    "S124": { name: "剑鞘残片", description: "上古剑鞘碎片，可修复破损剑器，或用作炼器辅料。", value: 15, rarity: "精品" },
    "S125": { name: "剑灵珠", description: "剑灵凝聚的宝珠，佩戴可增加剑道悟性。", value: 35, rarity: "灵品" },
    "S126": { name: "破甲剑诀残页", description: "记载着破甲剑气的口诀，习之可克制护体灵光。", value: 22, rarity: "精品" },
    "S127": { name: "剑痕石", description: "刻有剑道宗师剑痕的奇石，观摩可提升剑术修为。", value: 18, rarity: "精品" },
    "S128": { name: "剑气竹筒", description: "封印着三道剑气的竹筒，对敌时可释放伤敌。", value: 30, rarity: "灵品" },
    "S129": { name: "剑穗玉坠", description: "系于剑柄的玉坠，可略微提升飞剑速度。", value: 10, rarity: "凡品" },
    "S130": { name: "万剑归宗令", description: "一次性法器，捏碎可召唤万剑虚影震慑敌人。", value: 45, rarity: "玄品" },
    "S131": { name: "剑心草", description: "形似小剑的灵草，服之可涤荡剑心，破除心魔。", value: 25, rarity: "精品" },
    "S132": { name: "剑匣残件", description: "古剑匣的一部分，可温养飞剑，缓慢提升剑器灵性。", value: 20, rarity: "精品" },
    "S133": { name: "剑意丹", description: "三品丹药，服用后短暂进入剑意通明状态。", value: 32, rarity: "灵品" },
    "S134": { name: "剑侍傀儡", description: "小型傀儡，可演练基础剑法供修士参悟。", value: 18, rarity: "精品" },
    "S135": { name: "剑鸣石", description: "敲击可发出清越剑鸣，震慑低阶妖兽。", value: 14, rarity: "凡品" },
    "S136": { name: "剑符", description: "封印一道剑气的符箓，捏碎即可激发。", value: 16, rarity: "精品" },
    "S137": { name: "剑道总纲残章", description: "上古剑道总纲的残页，蕴含深奥剑理。", value: 55, rarity: "圣品" },
    "S138": { name: "剑鞘灵玉", description: "镶嵌在剑鞘上的灵玉，可温养剑器。", value: 12, rarity: "凡品" },
    "S139": { name: "剑阵图录", description: "记载小周天剑阵的图谱，可布简易剑阵。", value: 28, rarity: "灵品" },
    "S140": { name: "剑意灵酒", description: "以剑意入酒，饮后可暂时提升剑术威力。", value: 24, rarity: "精品" },
    
    // 天机阁专属 (S141~S160)
    "S141": { name: "推演玉简", description: "可用于推演功法的玉简，消耗神识推算后续功法。", value: 26, rarity: "精品" },
    "S142": { name: "天机罗盘", description: "小型推演法器，可预测吉凶，探知灵脉。", value: 38, rarity: "灵品" },
    "S143": { name: "算术灵珠", description: "蕴含算术规则的灵珠，可辅助计算阵法节点。", value: 15, rarity: "精品" },
    "S144": { name: "藏经密钥", description: "可开启天机阁外层藏经阁的钥匙，使用一次后消失。", value: 20, rarity: "精品" },
    "S145": { name: "灵感香", description: "点燃后可暂时提升悟性，更易参悟功法。", value: 22, rarity: "精品" },
    "S146": { name: "预知符", description: "贴于眉心可短暂预见未来三息，危机时刻救命。", value: 48, rarity: "玄品" },
    "S147": { name: "阵法残图", description: "上古阵法的残图，可从中领悟禁制知识。", value: 18, rarity: "精品" },
    "S148": { name: "天机笔", description: "推演阵法时使用，可减少神识消耗。", value: 14, rarity: "凡品" },
    "S149": { name: "问天签", description: "占卜法器，可问一事之吉凶。", value: 10, rarity: "凡品" },
    "S150": { name: "八卦镜", description: "可反射低级幻术，亦可窥探微弱灵光。", value: 25, rarity: "精品" },
    "S151": { name: "命理沙", description: "用于推演命理的灵沙，可短暂窥见未来片段。", value: 32, rarity: "灵品" },
    "S152": { name: "天机符", description: "激发后可短暂洞察敌人弱点。", value: 30, rarity: "灵品" },
    "S153": { name: "算筹", description: "灵玉所制算筹，用于复杂阵法计算。", value: 12, rarity: "凡品" },
    "S154": { name: "天机石", description: "蕴含天道机密的奇石，参悟可提升智慧。", value: 42, rarity: "玄品" },
    "S155": { name: "占卜龟甲", description: "刻有甲骨文的龟甲，可用于占卜问卦。", value: 18, rarity: "精品" },
    "S156": { name: "天机图残卷", description: "描绘天道运转的图卷，参悟可得机缘。", value: 60, rarity: "圣品" },
    "S157": { name: "避劫符", description: "可抵挡一次必死之劫的符箓，用完即毁。", value: 50, rarity: "玄品" },
    "S158": { name: "灵眼玉", description: "佩戴可增强神识感知，看清灵气流动。", value: 28, rarity: "灵品" },
    "S159": { name: "天机丹", description: "五品丹药，服用后短时间内神识倍增。", value: 35, rarity: "灵品" },
    "S160": { name: "推演棋盘", description: "黑白子可推演阵法变化，阵修至宝。", value: 40, rarity: "玄品" },
    
    // 醉仙楼专属 (S161~S180)
    "S161": { name: "醉仙酿", description: "灵酒一壶，饮后可恢复大量灵力，微醺中悟性提升。", value: 20, rarity: "精品" },
    "S162": { name: "酒虫玉", description: "嗜酒灵虫所化的美玉，泡酒可提升酒液品质。", value: 15, rarity: "精品" },
    "S163": { name: "千日醉", description: "饮一杯可醉千日的灵酒，常用于闭关炼体。", value: 25, rarity: "精品" },
    "S164": { name: "解忧果", description: "食之可忘却烦恼，破除低级心魔。", value: 12, rarity: "凡品" },
    "S165": { name: "酒仙令", description: "醉仙楼信物，出示可换取一份灵酒。", value: 10, rarity: "凡品" },
    "S166": { name: "灵果拼盘", description: "八种灵果，可恢复体力与少量灵力。", value: 14, rarity: "凡品" },
    "S167": { name: "醉拳谱", description: "记载醉拳的玉简，习之可于醉酒中战斗。", value: 28, rarity: "灵品" },
    "S168": { name: "酒鼎", description: "小型炼丹炉，专用于酿制灵酒。", value: 22, rarity: "精品" },
    "S169": { name: "醒酒石", description: "含在口中可解千日醉，恢复清明。", value: 8, rarity: "凡品" },
    "S170": { name: "酒灵珠", description: "酒中精灵所化的灵珠，可提升灵酒品质。", value: 32, rarity: "灵品" },
    "S171": { name: "醉仙葫", description: "可储存灵酒的葫芦，内刻保鲜阵法。", value: 18, rarity: "精品" },
    "S172": { name: "五谷灵米", description: "灵田所产，煮食可滋养身体，辟谷修士偶尔享用。", value: 6, rarity: "凡品" },
    "S173": { name: "酒令旗", description: "摇动可召集酒友，实为传讯法器。", value: 16, rarity: "精品" },
    "S174": { name: "醉剑符", description: "封印醉剑意境的符箓，激发后剑法飘忽不定。", value: 24, rarity: "精品" },
    "S175": { name: "酒神咒残篇", description: "上古酒修咒法残篇，可借酒施咒。", value: 45, rarity: "玄品" },
    "S176": { name: "醉仙糕", description: "以灵酒和面制成的糕点，食之微醺增益。", value: 12, rarity: "凡品" },
    "S177": { name: "酒泉石", description: "可渗出灵泉酒的奇石，每日可取一杯。", value: 35, rarity: "灵品" },
    "S178": { name: "醉心丹", description: "四品丹药，服用后可短暂进入忘我战斗状态。", value: 30, rarity: "灵品" },
    "S179": { name: "酒符笔", description: "以酒代墨画符的符笔，所画符箓带有醉意效果。", value: 20, rarity: "精品" },
    "S180": { name: "醉仙图", description: "画卷中醉仙姿态各异，参悟可得醉道真意。", value: 50, rarity: "玄品" },
    
    // 珍宝阁专属 (S181~S200)
    "S181": { name: "聚灵珠", description: "可缓慢聚集灵气的宝珠，放置洞府可提升修炼速度。", value: 30, rarity: "灵品" },
    "S182": { name: "灵石母", description: "能够缓慢生产下品灵石的奇石，百年可产一块。", value: 55, rarity: "圣品" },
    "S183": { name: "鉴宝镜", description: "可鉴定灵宝品阶与功用的古镜。", value: 25, rarity: "精品" },
    "S184": { name: "储物戒指", description: "一立方空间的储物法器，修士必备。", value: 40, rarity: "玄品" },
    "S185": { name: "拍卖锤", description: "珍宝阁信物，可参与一次内部拍卖。", value: 10, rarity: "凡品" },
    "S186": { name: "灵石袋", description: "可存放五百灵石的袋子，防神识探查。", value: 18, rarity: "精品" },
    "S187": { name: "鉴宝录", description: "记载天下灵宝图鉴的书籍，可识别宝物来历。", value: 22, rarity: "精品" },
    "S188": { name: "珍珑匣", description: "精巧木匣，内藏机关，可保管重要物品。", value: 16, rarity: "精品" },
    "S189": { name: "灵石秤", description: "称量灵石纯度的法器，防止交易被骗。", value: 12, rarity: "凡品" },
    "S190": { name: "宝光符", description: "激发后可使普通物品短暂散发宝光，用于装饰或欺诈。", value: 8, rarity: "凡品" },
    "S191": { name: "聚宝盆", description: "放入灵石可缓慢增值，但每日仅限一枚。", value: 48, rarity: "玄品" },
    "S192": { name: "藏宝图", description: "记载一处秘境藏宝点的地图，需自行探索。", value: 20, rarity: "精品" },
    "S193": { name: "灵石精粹", description: "高纯度灵石，可用于阵法核心或炼丹。", value: 35, rarity: "灵品" },
    "S194": { name: "宝箱钥匙", description: "可开启珍宝阁随机宝箱的钥匙。", value: 15, rarity: "精品" },
    "S195": { name: "估价玉", description: "触碰物品即可估算其价值。", value: 18, rarity: "精品" },
    "S196": { name: "珍宝架", description: "小型洞府家具，可展示灵宝，缓慢温养。", value: 25, rarity: "精品" },
    "S197": { name: "灵石矿镐", description: "挖矿法器，可提高挖出灵石的几率。", value: 22, rarity: "精品" },
    "S198": { name: "宝光丹", description: "服用后周身散发宝光，吸引注意或用于交易展示。", value: 14, rarity: "凡品" },
    "S199": { name: "珍宝令", description: "珍宝阁贵宾令牌，购物可打九折。", value: 30, rarity: "灵品" },
    "S200": { name: "聚宝灵阵图", description: "布置后可聚集财运的阵图，需灵石驱动。", value: 42, rarity: "玄品" },
    
    // 演武擂台专属 (S201~S220)
    "S201": { name: "擂台令", description: "可参与一次擂台挑战的令牌，获胜有奖。", value: 10, rarity: "凡品" },
    "S202": { name: "斗战丹", description: "三品丹药，服用后战力短暂提升三成。", value: 28, rarity: "灵品" },
    "S203": { name: "擂主金牌", description: "擂台连胜奖励，佩戴可略微震慑对手。", value: 18, rarity: "精品" },
    "S204": { name: "战意珠", description: "蕴含战意的宝珠，激发后进入亢奋战斗状态。", value: 25, rarity: "精品" },
    "S205": { name: "护体灵符", description: "激发后生成护体灵光，可抵挡筑基一击。", value: 20, rarity: "精品" },
    "S206": { name: "挑战书", description: "对指定修士发出挑战，受规则保护。", value: 8, rarity: "凡品" },
    "S207": { name: "战斗傀儡", description: "练气期战斗傀儡，可陪练功法。", value: 32, rarity: "灵品" },
    "S208": { name: "擂鼓石", description: "敲击可发出战鼓之声，鼓舞士气。", value: 15, rarity: "精品" },
    "S209": { name: "破障拳套", description: "穿戴后拳劲可破护体灵光。", value: 24, rarity: "精品" },
    "S210": { name: "闪避符", description: "激发后身法暴增，短暂躲避攻击。", value: 18, rarity: "精品" },
    "S211": { name: "斗气丹", description: "四品丹药，服用后气血翻涌，力量大增。", value: 30, rarity: "灵品" },
    "S212": { name: "擂台护腕", description: "减轻战斗中的手腕负担，提升出招速度。", value: 14, rarity: "凡品" },
    "S213": { name: "战意酒", description: "饮后战意高昂，不畏伤痛。", value: 16, rarity: "精品" },
    "S214": { name: "斗技玉简", description: "记载一种斗战技法的玉简，习之可增战力。", value: 35, rarity: "灵品" },
    "S215": { name: "回气丹", description: "战斗中快速恢复灵气的丹药。", value: 22, rarity: "精品" },
    "S216": { name: "擂台阵旗", description: "布置简易擂台法阵，防止战斗波及外界。", value: 26, rarity: "精品" },
    "S217": { name: "斗篷", description: "战斗时可隐藏面容的斗篷，防神识探查。", value: 18, rarity: "精品" },
    "S218": { name: "战吼符", description: "激发后发出战吼，震慑低阶妖兽。", value: 12, rarity: "凡品" },
    "S219": { name: "连胜令", description: "擂台十连胜奖励，可兑换功法。", value: 40, rarity: "玄品" },
    "S220": { name: "斗战圣诀残篇", description: "上古斗战圣法残篇，修习可大幅提升战力。", value: 65, rarity: "圣品" },
    
    // 灵药坊市专属 (S221~S240)
    "S221": { name: "培元丹", description: "二品丹药，巩固修为，适合筑基前服用。", value: 12, rarity: "凡品" },
    "S222": { name: "灵药锄", description: "挖药法器，可完整挖取灵药根茎。", value: 10, rarity: "凡品" },
    "S223": { name: "药方残页", description: "记载某灵丹配方的残页，可尝试炼制。", value: 18, rarity: "精品" },
    "S224": { name: "灵药种子", description: "随机灵药种子，可种植于灵田。", value: 8, rarity: "凡品" },
    "S225": { name: "炼丹炉", description: "小型炼丹炉，适合初学者。", value: 25, rarity: "精品" },
    "S226": { name: "灵药篮", description: "可保鲜灵药的篮子，内刻保鲜阵法。", value: 14, rarity: "凡品" },
    "S227": { name: "丹药瓶", description: "可储存丹药防止药力流失的玉瓶。", value: 6, rarity: "凡品" },
    "S228": { name: "解毒丹", description: "二品解毒丹，可解大部分常见毒素。", value: 16, rarity: "精品" },
    "S229": { name: "灵药铲", description: "小型灵药铲，便于移植灵药。", value: 8, rarity: "凡品" },
    "S230": { name: "炼丹心得", description: "某炼丹师笔记，可提升炼丹成功率。", value: 22, rarity: "精品" },
    "S231": { name: "回灵丹", description: "快速恢复灵气的丹药，战斗必备。", value: 20, rarity: "精品" },
    "S232": { name: "灵药架", description: "洞府家具，可放置灵药瓶，防潮防虫。", value: 15, rarity: "精品" },
    "S233": { name: "丹方", description: "完整的一张丹方，可炼制一种灵丹。", value: 30, rarity: "灵品" },
    "S234": { name: "灵药秤", description: "称量灵药精确到毫的秤。", value: 10, rarity: "凡品" },
    "S235": { name: "养魂丹", description: "三品丹药，滋养神魂，修复神识损伤。", value: 35, rarity: "灵品" },
    "S236": { name: "灵药剪", description: "修剪灵药的剪刀，可促进再生。", value: 8, rarity: "凡品" },
    "S237": { name: "炼丹服", description: "防火防毒的炼丹专用法袍。", value: 18, rarity: "精品" },
    "S238": { name: "灵药谱", description: "记载数百种灵药药性的图谱。", value: 25, rarity: "精品" },
    "S239": { name: "丹火符", description: "激发后产生丹火，用于临时炼丹。", value: 14, rarity: "凡品" },
    "S240": { name: "炼丹总纲", description: "炼丹宗师心得，可大幅提升炼丹术。", value: 58, rarity: "圣品" },
    
    // 碧波寒潭专属 (S241~S260)
    "S241": { name: "寒潭灵液", description: "碧波寒潭底的灵液，可淬炼肉身。", value: 20, rarity: "精品" },
    "S242": { name: "避水珠", description: "佩戴后可水下呼吸，如履平地。", value: 25, rarity: "精品" },
    "S243": { name: "冰晶石", description: "极寒灵石，可用于炼制冰属性法宝。", value: 15, rarity: "精品" },
    "S244": { name: "寒玉床", description: "小型寒玉床，修炼冰属性功法事半功倍。", value: 45, rarity: "玄品" },
    "S245": { name: "冰魄丹", description: "四品丹药，服用后可短暂获得冰灵根效果。", value: 32, rarity: "灵品" },
    "S246": { name: "寒铁鱼钩", description: "钓取寒潭灵鱼的钩子，不易被鱼察觉。", value: 12, rarity: "凡品" },
    "S247": { name: "冰蚕丝", description: "冰蚕所吐丝线，可用于炼制法袍。", value: 18, rarity: "精品" },
    "S248": { name: "寒潭珠", description: "寒潭灵气凝结的宝珠，佩戴可清凉静心。", value: 22, rarity: "精品" },
    "S249": { name: "冰晶剑", description: "寒潭冰晶所铸短剑，自带冰寒特效。", value: 28, rarity: "灵品" },
    "S250": { name: "避寒符", description: "抵御严寒的符箓，极地探险必备。", value: 10, rarity: "凡品" },
    "S251": { name: "冰灵根种子", description: "可使修士短暂拥有冰灵根的一次性宝物。", value: 55, rarity: "圣品" },
    "S252": { name: "寒潭灵龟壳", description: "千年灵龟壳，可用于炼制防御法器。", value: 35, rarity: "灵品" },
    "S253": { name: "冰魄珠", description: "蕴含冰魄之力的宝珠，可冻结低阶妖兽。", value: 30, rarity: "灵品" },
    "S254": { name: "寒铁砂", description: "寒潭底部的铁砂，炼器时加入可增寒意。", value: 14, rarity: "凡品" },
    "S255": { name: "冰晶簪", description: "冰晶雕琢的发簪，佩戴可提神醒脑。", value: 16, rarity: "精品" },
    "S256": { name: "寒潭玉液", description: "百年寒潭玉液，可洗髓伐毛。", value: 40, rarity: "玄品" },
    "S257": { name: "冰符笔", description: "以寒潭水为墨画符的笔，所画符箓带冰寒效果。", value: 24, rarity: "精品" },
    "S258": { name: "避水符", description: "激发后可在水下行动，持续一个时辰。", value: 12, rarity: "凡品" },
    "S259": { name: "冰晶盏", description: "盛放灵液可保千年不腐的冰晶杯。", value: 28, rarity: "灵品" },
    "S260": { name: "寒潭真解", description: "记载寒潭秘法的玉简，可修习寒系神通。", value: 50, rarity: "玄品" },
    
    // 藏书峰专属 (S261~S280)
    "S261": { name: "悟道茶", description: "采自藏书峰灵茶树的茶叶，泡饮可助悟道。", value: 18, rarity: "精品" },
    "S262": { name: "书签玉", description: "可标记功法玉简阅读进度的法器。", value: 8, rarity: "凡品" },
    "S263": { name: "功法拓印石", description: "可复制玉简内容的奇石，限用三次。", value: 25, rarity: "精品" },
    "S264": { name: "藏书匣", description: "可存放百枚玉简的匣子，防虫防潮。", value: 20, rarity: "精品" },
    "S265": { name: "灵墨", description: "用于书写符箓或功法的灵墨，不易褪色。", value: 12, rarity: "凡品" },
    "S266": { name: "悟道蒲团", description: "打坐时使用可提升悟性，参悟功法更快。", value: 30, rarity: "灵品" },
    "S267": { name: "灵纸", description: "可承载灵气的纸张，用于绘制符箓。", value: 6, rarity: "凡品" },
    "S268": { name: "书童傀儡", description: "可帮忙整理玉简的小傀儡。", value: 15, rarity: "精品" },
    "S269": { name: "明心丹", description: "三品丹药，服用后心智清明，破除迷障。", value: 28, rarity: "灵品" },
    "S270": { name: "灵笔", description: "灵兽毫所制符笔，画符成功率提升。", value: 22, rarity: "精品" },
    "S271": { name: "藏书峰地图", description: "标注了藏书峰各层藏书的分布图。", value: 10, rarity: "凡品" },
    "S272": { name: "悟道香", description: "点燃后进入悟道状态，持续一个时辰。", value: 24, rarity: "精品" },
    "S273": { name: "玉简架", description: "放置玉简的架子，可分类整理。", value: 14, rarity: "凡品" },
    "S274": { name: "破障丹", description: "四品丹药，突破瓶颈时服用可增三成几率。", value: 38, rarity: "灵品" },
    "S275": { name: "灵砚", description: "研墨可生成灵气的砚台。", value: 18, rarity: "精品" },
    "S276": { name: "藏书令", description: "可进入藏书峰内层借阅功法的令牌。", value: 35, rarity: "灵品" },
    "S277": { name: "灵纸镇", description: "镇压灵纸的镇纸，可防止灵气逸散。", value: 12, rarity: "凡品" },
    "S278": { name: "悟道珠", description: "蕴含一丝道韵的宝珠，可辅助领悟功法。", value: 32, rarity: "灵品" },
    "S279": { name: "灵书匣", description: "可存放纸质功法的木匣，防火防水。", value: 16, rarity: "精品" },
    "S280": { name: "万法归宗残卷", description: "记载三千大道简纲的残卷，触类旁通。", value: 60, rarity: "圣品" },
    
    // 百炼谷专属 (S281~S300)
    "S281": { name: "百炼锤", description: "炼器用的锤子，可提升锻造成功率。", value: 20, rarity: "精品" },
    "S282": { name: "玄铁母", description: "玄铁之母，炼器时加入可提升法器品阶。", value: 35, rarity: "灵品" },
    "S283": { name: "熔火石", description: "可产生高温的石头，用于熔炼矿石。", value: 15, rarity: "精品" },
    "S284": { name: "炼器炉", description: "便携炼器炉，适合野外炼器。", value: 28, rarity: "灵品" },
    "S285": { name: "矿镐", description: "普通矿镐，挖矿效率提升。", value: 8, rarity: "凡品" },
    "S286": { name: "淬火液", description: "灵液，用于法器淬火，增加韧性。", value: 18, rarity: "精品" },
    "S287": { name: "百炼钢", description: "百炼精钢，可炼制飞剑胚体。", value: 12, rarity: "凡品" },
    "S288": { name: "炼器心得", description: "炼器宗师的笔记，可提升炼器术。", value: 25, rarity: "精品" },
    "S289": { name: "模具", description: "用于浇铸法器胚体的模具。", value: 10, rarity: "凡品" },
    "S290": { name: "灵矿图", description: "标注灵矿分布的地图，便于开采。", value: 22, rarity: "精品" },
    "S291": { name: "锻打台", description: "小型锻打台，方便炼器。", value: 18, rarity: "精品" },
    "S292": { name: "灵炭", description: "高热灵炭，用于炼器炉燃料。", value: 6, rarity: "凡品" },
    "S293": { name: "炼器护目镜", description: "保护眼睛免受强光伤害，可看穿材料杂质。", value: 16, rarity: "精品" },
    "S294": { name: "百炼令", description: "百炼谷信物，可换取一次炼器指导。", value: 20, rarity: "精品" },
    "S295": { name: "灵矿锄", description: "灵器级矿锄，可挖掘高阶灵矿。", value: 30, rarity: "灵品" },
    "S296": { name: "炼器服", description: "防火防尘的炼器专用法袍。", value: 14, rarity: "凡品" },
    "S297": { name: "器胚", description: "半成品法器胚体，可继续炼制。", value: 25, rarity: "精品" },
    "S298": { name: "淬火油", description: "特殊灵油，淬火可增加法器锋利度。", value: 18, rarity: "精品" },
    "S299": { name: "百炼诀残篇", description: "百炼谷炼器秘诀残篇，可提升炼器术。", value: 45, rarity: "玄品" },
    "S300": { name: "天工锤", description: "传说级炼器锤，可大幅提升炼器成功率。", value: 65, rarity: "圣品" },
    
    // 凌霄殿专属 (S301~S320)
    "S301": { name: "凌霄令", description: "凌霄殿信物，可进入殿中参悟。", value: 30, rarity: "灵品" },
    "S302": { name: "天子剑", description: "皇室佩剑，蕴含王者之气，对妖邪有克制。", value: 40, rarity: "玄品" },
    "S303": { name: "龙气丹", description: "蕴含一丝真龙之气的丹药，服用可强化肉身。", value: 35, rarity: "灵品" },
    "S304": { name: "御座蒲团", description: "凌霄殿御座所用蒲团，打坐可吸纳龙气。", value: 28, rarity: "灵品" },
    "S305": { name: "朝珠", description: "凌霄殿朝珠，佩戴可辟邪，受百官气运庇佑。", value: 22, rarity: "精品" },
    "S306": { name: "圣旨卷轴", description: "空白圣旨，可书写命令，对下属有约束力。", value: 18, rarity: "精品" },
    "S307": { name: "龙袍残片", description: "真龙天子龙袍碎片，可炼制防御法器。", value: 25, rarity: "精品" },
    "S308": { name: "玉玺印", description: "小型玉玺，可加持公文或符箓权威。", value: 32, rarity: "灵品" },
    "S309": { name: "凌霄丹", description: "五品丹药，服用后可短暂获得皇道威压。", value: 38, rarity: "灵品" },
    "S310": { name: "金銮灯", description: "凌霄殿金灯，点燃可照亮黑暗，驱散邪祟。", value: 20, rarity: "精品" },
    "S311": { name: "御林军令", description: "可召唤两名练气期护卫的令牌，限用一次。", value: 24, rarity: "精品" },
    "S312": { name: "龙椅碎片", description: "龙椅残片，蕴含龙气，可炼入法宝。", value: 28, rarity: "灵品" },
    "S313": { name: "天子笔", description: "御用毛笔，所书符箓威力增强。", value: 26, rarity: "精品" },
    "S314": { name: "凌霄图", description: "绘有凌霄殿全景的画卷，可从中领悟皇道意境。", value: 42, rarity: "玄品" },
    "S315": { name: "龙袍", description: "仿制龙袍，穿戴可提升威严，对下属有压制。", value: 35, rarity: "灵品" },
    "S316": { name: "御酒", description: "皇家御酒，饮后可恢复灵力，并短暂提升气势。", value: 18, rarity: "精品" },
    "S317": { name: "金印", description: "官员金印，可用于官府事务，或有特殊用途。", value: 22, rarity: "精品" },
    "S318": { name: "凌霄宝鉴", description: "可照出他人气运的宝镜，对修士有效。", value: 48, rarity: "玄品" },
    "S319": { name: "龙灵珠", description: "蕴含龙魂之力的宝珠，可召唤龙灵虚影。", value: 55, rarity: "圣品" },
    "S320": { name: "凌霄真解", description: "凌霄殿不传之秘，记载皇道修仙法门。", value: 70, rarity: "圣品" }
};

/** ====== 公告功能 ====== */
const ANNOUNCE_GROUP_ID = '867710242';

function sendToAnnouncement(ctx, msg, text, overrideGroupId) {
  if (!text) return;
  try {
    const platform = msg.platform;
    // 优先使用传入的覆盖值，否则使用存储的公告群ID
    const gid = String(overrideGroupId || getAnnounceGroupId());
    
    let gmsg = seal.newMessage();
    gmsg.messageType = "group";
    gmsg.sender = {};
    gmsg.sender.userId = msg.sender.userId;
    
    if (gid.includes('&&')) {
      const [guildId, groupId] = gid.split('&&');
      gmsg.guildId = guildId;
      gmsg.groupId = groupId;
    } else {
      gmsg.groupId = `${platform}-Group:${gid}`;
    }
    
    const gctx = seal.createTempCtx(ctx.endPoint, gmsg);
    seal.replyToSender(gctx, gmsg, text);
  } catch(e) { /* 静默失败 */ }
}

function buildTargetMessage(ctx, platform, targetName, reg) {
  const targetUid = reg[platform][targetName][0];
  const targetGid = reg[platform][targetName][1];
  const newmsg = seal.newMessage();
  newmsg.messageType = "group";
  newmsg.sender = {};
  newmsg.sender.userId = `${platform}:${targetUid}`;
  if (targetGid.includes('&&')) {
    const [guildId, groupId] = targetGid.split('&&');
    newmsg.guildId = guildId;
    newmsg.groupId = groupId;
  } else {
    newmsg.groupId = `${platform}-Group:${targetGid}`;
  }
  return seal.createTempCtx(ctx.endPoint, newmsg);
}

// ==================== 辅助函数 ====================
function autoGid(msg) {
  return msg.guildId || '';
}

function isDigits(str) {
  return /^\d+$/.test(str);
}

function currentPlatform(msg) {
  return msg.platform || 'default';
}

function currentUid(msg) {
  return msg.sender.userId || msg.author?.id || 'unknown';
}

function ensurePlatformMap(reg, platform) {
  if (!reg[platform]) {
    reg[platform] = {};
  }
}

// ==================== 天数管理 ====================
function dayKey() {
  return ext.storageGet("global_days") || "D1";
}

/***** 修仙界·仙门管理 *****/
const DEFAULT_ADMIN_SECRET = 'rootpass';

function getAdminList(){
  try { return JSON.parse(ext.storageGet('a_adminList') || '{}'); }
  catch(e){ return {}; }
}
function saveAdminList(obj){
  ext.storageSet('a_adminList', JSON.stringify(obj || {}));
}
function getAdminSecret(){
  const s = ext.storageGet('a_adminSecret');
  return (s && s.trim()) ? s.trim() : DEFAULT_ADMIN_SECRET;
}

function _logAdmin(ctx, msg, text){
  try { 
    sendToAnnouncement(ctx, msg, `📜 ${text}`);
  } catch(e){}
}

/* ========== 1) 授予仙门执事 ========== */
let cmd_grant_admin = seal.ext.newCmdItemInfo();
cmd_grant_admin.name = '授予仙门执事';
cmd_grant_admin.help = '。授予仙门执事 账号 密钥（输入正确密钥后将该账号加入执事名单）';

cmd_grant_admin.solve = (ctx, msg, cmdArgs) => {
  const platform = msg.platform;
  const targetUID = (cmdArgs.getArgN(1) || '').trim();
  const inputPass = (cmdArgs.getArgN(2) || '').trim();

  if (!targetUID || !inputPass){
    seal.replyToSender(ctx, msg, '请输入：。授予仙门执事 账号 密钥');
    return seal.ext.newCmdExecuteResult(true);
  }

  const secret = getAdminSecret();
  if (inputPass !== secret){
    seal.replyToSender(ctx, msg, '❌ 密钥错误，无法授权。');
    return seal.ext.newCmdExecuteResult(true);
  }

  const list = getAdminList();
  if (!Array.isArray(list[platform])) list[platform] = [];

  if (!list[platform].includes(targetUID)){
    list[platform].push(targetUID);
    saveAdminList(list);
    const ok = `✅ 已将 ${targetUID} 设为 ${platform} 平台仙门执事`;
    seal.replyToSender(ctx, msg, ok);
    _logAdmin(ctx, msg, `【仙门任命】授予 → ${targetUID}（平台：${platform}）`);
  } else {
    seal.replyToSender(ctx, msg, `⚠️ ${targetUID} 已在执事名单中`);
  }
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['授予仙门执事'] = cmd_grant_admin;

/* ========== 2) 撤销仙门执事 ========== */
let cmd_revoke_admin = seal.ext.newCmdItemInfo();
cmd_revoke_admin.name = '撤销仙门执事';
cmd_revoke_admin.help = '。撤销仙门执事 账号 密钥（或由仙尊/平台管执行可省略密钥）';

cmd_revoke_admin.solve = (ctx, msg, cmdArgs) => {
  const platform = msg.platform;
  const targetUID = (cmdArgs.getArgN(1) || '').trim();
  const inputPass = (cmdArgs.getArgN(2) || '').trim();
  if (!targetUID){
    seal.replyToSender(ctx, msg, '请输入：。撤销仙门执事 账号 [密钥]');
    return seal.ext.newCmdExecuteResult(true);
  }

  const byMaster = (msg.isMaster || msg.isAdmin);
  if (!byMaster){
    const secret = getAdminSecret();
    if (inputPass !== secret){
      seal.replyToSender(ctx, msg, '❌ 无权限：需仙尊/平台管执行，或提供正确密钥。');
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  const list = getAdminList();
  if (!Array.isArray(list[platform])) list[platform] = [];
  const idx = list[platform].indexOf(targetUID);
  if (idx < 0){
    seal.replyToSender(ctx, msg, `未在 ${platform} 执事名单中找到：${targetUID}`);
    return seal.ext.newCmdExecuteResult(true);
  }

  list[platform].splice(idx, 1);
  saveAdminList(list);
  const ok = `🗑 已撤销 ${platform} 平台仙门执事：${targetUID}`;
  seal.replyToSender(ctx, msg, ok);
  _logAdmin(ctx, msg, `【仙门罢黜】撤销 ← ${targetUID}（平台：${platform}）`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['撤销仙门执事'] = cmd_revoke_admin;

/* ========== 3) 仙门执事名单 ========== */
let cmd_list_admin = seal.ext.newCmdItemInfo();
cmd_list_admin.name = '仙门执事名单';
cmd_list_admin.help = '。仙门执事名单（仅执事可用）';

cmd_list_admin.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)){
    seal.replyToSender(ctx, msg, '该指令仅限仙门执事使用');
    return seal.ext.newCmdExecuteResult(true);
  }
  const platform = msg.platform;
  const list = getAdminList();
  const arr = Array.isArray(list[platform]) ? list[platform] : [];
  const rep = [
    `【仙门执事名单】平台：${platform}`,
    arr.length ? arr.map((x,i)=>`${i+1}. ${x}`).join('\n') : '（暂无其他执事）'
  ].join('\n');
  seal.replyToSender(ctx, msg, rep);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['仙门执事名单'] = cmd_list_admin;

/* ========== 4) 设置仙门密钥 ========== */
let cmd_set_secret = seal.ext.newCmdItemInfo();
cmd_set_secret.name = '设置仙门密钥';
cmd_set_secret.help = '。设置仙门密钥 新密钥（仅仙尊/平台管理员可用）';

cmd_set_secret.solve = (ctx, msg, cmdArgs) => {
  if (!(msg.isMaster || msg.isAdmin)){
    seal.replyToSender(ctx, msg, '该指令仅限仙尊/平台管理员使用');
    return seal.ext.newCmdExecuteResult(true);
  }
  const newSecret = (cmdArgs.getArgN(1) || '').trim();
  if (!newSecret){
    seal.replyToSender(ctx, msg, '请输入：。设置仙门密钥 新密钥');
    return seal.ext.newCmdExecuteResult(true);
  }
  ext.storageSet('a_adminSecret', newSecret);
  seal.replyToSender(ctx, msg, '✅ 已更新仙门密钥（请妥善保管）');
  _logAdmin(ctx, msg, `【仙门密钥已更新】由仙尊/平台管操作`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['设置仙门密钥'] = cmd_set_secret;

// ========= 设置修仙历天数 =========
let cmd_set_days = seal.ext.newCmdItemInfo();
cmd_set_days.name = "设置修仙历天数";
cmd_set_days.help = "。设置修仙历天数 D1（或 D2、D3 等）";

cmd_set_days.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, `⚠️ 该指令仅限仙门执事使用`);
    return seal.ext.newCmdExecuteResult(true);
  }

  let dayStr = (cmdArgs.getArgN(1) || '').trim();
  if (!dayStr || !/^D\d+$/i.test(dayStr)) {
    seal.replyToSender(ctx, msg, `⚠️ 请输入正确格式，例如：。设置修仙历天数 D1`);
    return seal.ext.newCmdExecuteResult(true);
  }

  dayStr = dayStr.toUpperCase();
  ext.storageSet("global_days", dayStr);
  seal.replyToSender(ctx, msg, `✅ 已将修仙历天数设置为：${dayStr}（当前生效日键：${dayKey()}）`);

  _logAdmin(ctx, msg, `【修仙历变更】全局天数 → ${dayStr}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置修仙历天数"] = cmd_set_days;

/** =========================================================
 * 指令一：踏入仙途 —— 记录道号与群号
 * 用法：
 *   。踏入仙途 道号 群号
 * 频道类平台可省略群号，自动绑定当前频道
 * ========================================================= */
let cmd_enter = seal.ext.newCmdItemInfo();
cmd_enter.name = '踏入仙途';
cmd_enter.help = '。踏入仙途 道号 群号（频道类平台可省略群号，将自动绑定当前频道）';

cmd_enter.solve = (ctx, msg, args) => {
  let name = (args.getArgN(1) || '').trim();
  let gid  = (args.getArgN(2) || '').trim();

  if (!name || name === 'help') {
    const tip = msg.guildId
      ? '频道类平台无需指定群号，请直接在目标频道发送：\n。踏入仙途 道号'
      : '用法：\n。踏入仙途 道号 群号\n示例：。踏入仙途 青云子 123456';
    seal.replyToSender(ctx, msg, tip);
    return seal.ext.newCmdExecuteResult(true);
  }

  if (!gid) {
    const auto = autoGid(msg);
    if (auto) gid = auto;
  }

  if (!msg.guildId) {
    if (!gid) {
      seal.replyToSender(ctx, msg, '请填写群号：。踏入仙途 道号 群号');
      return seal.ext.newCmdExecuteResult(true);
    }
    if (!isDigits(gid)) {
      seal.replyToSender(ctx, msg, '群号必须为纯数字，请重新录入');
      return seal.ext.newCmdExecuteResult(true);
    }
  }

  const platform = currentPlatform(msg);
  const uid = currentUid(msg);
  let reg = normalize(getReg());
  ensurePlatformMap(reg, platform);

  if (reg[platform][name] && reg[platform][name][0] !== uid) {
    seal.replyToSender(ctx, msg, '该道号已被其他修士占用，请更换道号');
    return seal.ext.newCmdExecuteResult(true);
  }

  let oldName = '';
  for (const k in reg[platform]) {
    const rec = reg[platform][k];
    if (Array.isArray(rec) && rec[0] === uid) { oldName = k; break; }
  }
  if (oldName) delete reg[platform][oldName];

  reg[platform][name] = [uid, gid || '0'];
  saveReg(reg);

  const hintGid = (gid && gid !== '0') ? gid : '未录入';
  const renamed = oldName ? `（原道号「${oldName}」已替换）` : '';
  seal.replyToSender(ctx, msg, `✅ 入籍仙门成功${renamed}\n道号：${name}\nID：${uid}\n群号：${hintGid}`);
  
  sendToAnnouncement(ctx, msg, `🏯 新的修士「${name}」踏入了修仙界`);
  
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['踏入仙途'] = cmd_enter;

/** =========================================================
 * 指令二：仙门名录 —— 执事查看当前平台所有登记
 * 用法：。仙门名录
 * ========================================================= */
let cmd_list = seal.ext.newCmdItemInfo();
cmd_list.name = '仙门名录';
cmd_list.help = '。仙门名录（仅执事可用）';

cmd_list.solve = (ctx, msg) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, '该指令仅限仙门执事使用');
    return seal.ext.newCmdExecuteResult(true);
  }
  const platform = currentPlatform(msg);
  const reg = normalize(getReg());
  if (!reg[platform] || Object.keys(reg[platform]).length === 0) {
    seal.replyToSender(ctx, msg, '当前平台暂无修士登记');
    return seal.ext.newCmdExecuteResult(true);
  }
  const lines = ['📜【仙门名录·修士】'];
  for (const name in reg[platform]) {
    const [uid, gid] = reg[platform][name];
    lines.push(`道号：${name}\nID：${uid}\n群号：${gid === '0' ? '未录入' : gid}\n`);
  }
  seal.replyToSender(ctx, msg, lines.join('\n').trim());
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['仙门名录'] = cmd_list;

/** =========================================================
 * 指令三：逐出仙门 —— 执事按道号移除登记
 * 用法：。逐出仙门 道号
 * ========================================================= */
let cmd_remove = seal.ext.newCmdItemInfo();
cmd_remove.name = '逐出仙门';
cmd_remove.help = '。逐出仙门 道号（仅执事可用）';

cmd_remove.solve = (ctx, msg, args) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, '该指令仅限仙门执事使用');
    return seal.ext.newCmdExecuteResult(true);
  }
  const name = (args.getArgN(1) || '').trim();
  if (!name) {
    seal.replyToSender(ctx, msg, '请输入要逐出的道号：。逐出仙门 张三');
    return seal.ext.newCmdExecuteResult(true);
  }

  const platform = currentPlatform(msg);
  const reg = normalize(getReg());
  if (!reg[platform] || !reg[platform][name]) {
    seal.replyToSender(ctx, msg, '未找到该修士，请检查道号是否正确');
    return seal.ext.newCmdExecuteResult(true);
  }

  delete reg[platform][name];
  saveReg(reg);
  seal.replyToSender(ctx, msg, `🗑 已从仙门名录中逐出「${name}」`);
  
  sendToAnnouncement(ctx, msg, `💨 修士「${name}」离开了修仙界`);
  
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['逐出仙门'] = cmd_remove;

/** ====== 迁移仙籍（执事便捷修正） ====== */
let cmd_soul_move = seal.ext.newCmdItemInfo();
cmd_soul_move.name = '迁移仙籍';
cmd_soul_move.help = '。迁移仙籍 道号 新群号（执事修改绑定群号）';
cmd_soul_move.solve = (ctx, msg, args) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, '该指令仅限仙门执事使用');
    return seal.ext.newCmdExecuteResult(true);
  }
  const name = (args.getArgN(1) || '').trim();
  const newGid = (args.getArgN(2) || '').trim();
  if (!name || !newGid) {
    seal.replyToSender(ctx, msg, '用法：。迁移仙籍 道号 新群号');
    return seal.ext.newCmdExecuteResult(true);
  }
  if (!isDigits(newGid) && !msg.guildId) {
    seal.replyToSender(ctx, msg, '群号必须为纯数字');
    return seal.ext.newCmdExecuteResult(true);
  }
  const platform = currentPlatform(msg);
  const reg = normalize(getReg());
  if (!reg[platform] || !reg[platform][name]) {
    seal.replyToSender(ctx, msg, `未找到「${name}」`);
    return seal.ext.newCmdExecuteResult(true);
  }
  reg[platform][name][1] = newGid;
  saveReg(reg);
  seal.replyToSender(ctx, msg, `✅ 已为「${name}」更新仙籍群号 → ${newGid}`);
  return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap['迁移仙籍'] = cmd_soul_move;

// 修仙界秘境地点
const BIANJING_LOCATIONS = {
    "L001": "青云剑冢",
    "L002": "天机阁", 
    "L003": "醉仙楼",
    "L004": "珍宝阁",
    "L005": "演武擂台",
    "L006": "灵药坊市",
    "L007": "碧波寒潭",
    "L008": "藏书峰",
    "L009": "百炼谷",
    "L010": "凌霄殿"
};

// 初始化存储
function initGiftStorage() {
    if (!ext.storageGet("song_inventory")) {
        ext.storageSet("song_inventory", "{}");
    }
    if (!ext.storageGet("dig_cooldowns")) {
        ext.storageSet("dig_cooldowns", "{}");
    }
    if (!ext.storageGet("steal_cooldowns")) {
        ext.storageSet("steal_cooldowns", "{}");
    }
    if (!ext.storageGet("gift_logs")) {
        ext.storageSet("gift_logs", "[]");
    }
}

function getUserInventory(platform, characterName) {
    const inventory = JSON.parse(ext.storageGet("song_inventory") || "{}");
    if (!inventory[platform]) inventory[platform] = {};
    if (!inventory[platform][characterName]) inventory[platform][characterName] = {};
    return inventory[platform][characterName];
}

function getUserTotalItems(platform, characterName) {
    const inventory = getUserInventory(platform, characterName);
    return Object.values(inventory).reduce((sum, count) => sum + count, 0);
}

function saveUserInventory(platform, characterName, inventory) {
    const allInventory = JSON.parse(ext.storageGet("song_inventory") || "{}");
    if (!allInventory[platform]) allInventory[platform] = {};
    allInventory[platform][characterName] = inventory;
    ext.storageSet("song_inventory", JSON.stringify(allInventory));
}

function checkCooldown(cooldownType, platform, characterName, cooldownMinutes) {
    const cooldowns = JSON.parse(ext.storageGet(cooldownType) || "{}");
    const key = `${platform}_${characterName}`;
    const lastTime = cooldowns[key] || 0;
    const currentTime = Date.now();
    const cooldownMs = cooldownMinutes * 60 * 1000;
    
    if (currentTime - lastTime < cooldownMs) {
        const remaining = Math.ceil((cooldownMs - (currentTime - lastTime)) / 60000);
        return { onCooldown: true, remaining };
    }
    
    cooldowns[key] = currentTime;
    ext.storageSet(cooldownType, JSON.stringify(cooldowns));
    return { onCooldown: false };
}

function logGiftAction(action, from, to, giftId, success = true) {
    const logs = JSON.parse(ext.storageGet("gift_logs") || "[]");
    logs.push({
        action,
        from,
        to,
        giftId,
        giftName: SONG_GIFTS[giftId]?.name || "未知灵宝",
        success,
        timestamp: Date.now()
    });
    if (logs.length > 100) {
        logs.splice(0, logs.length - 100);
    }
    ext.storageSet("gift_logs", JSON.stringify(logs));
}

// 秘境灵宝池（沿用原ID池，内容已改为修仙物品）
const LOCATION_GIFT_POOLS = {
    // 青云剑冢：原22件 + S121~S140
    "L001": ["S001","S004","S008","S014","S018","S019","S030","S031","S035","S039",
             "S042","S047","S051","S055","S059","S063","S071","S079","S087","S099",
             "S101","S111", "S121","S122","S123","S124","S125","S126","S127","S128",
             "S129","S130","S131","S132","S133","S134","S135","S136","S137","S138","S139","S140"],
    // 天机阁：原22件 + S141~S160
    "L002": ["S003","S005","S028","S012","S015","S027","S029","S033","S036","S043",
             "S049","S053","S057","S062","S066","S070","S074","S083","S086","S091",
             "S102","S112", "S141","S142","S143","S144","S145","S146","S147","S148",
             "S149","S150","S151","S152","S153","S154","S155","S156","S157","S158","S159","S160"],
    // 醉仙楼：原22件 + S161~S180
    "L003": ["S010","S018","S022","S025","S019","S011","S020","S032","S038","S045",
             "S050","S054","S058","S061","S067","S072","S075","S078","S090","S094",
             "S103","S113", "S161","S162","S163","S164","S165","S166","S167","S168",
             "S169","S170","S171","S172","S173","S174","S175","S176","S177","S178","S179","S180"],
    // 珍宝阁：原22件 + S181~S200
    "L004": ["S002","S006","S011","S013","S017","S021","S023","S034","S040","S044",
             "S048","S052","S056","S064","S068","S073","S076","S080","S084","S092",
             "S104","S114", "S181","S182","S183","S184","S185","S186","S187","S188",
             "S189","S190","S191","S192","S193","S194","S195","S196","S197","S198","S199","S200"],
    // 演武擂台：原22件 + S201~S220
    "L005": ["S025","S021","S006","S022","S029","S019","S030","S037","S041","S046",
             "S049","S054","S057","S060","S065","S069","S072","S077","S081","S085",
             "S105","S115", "S201","S202","S203","S204","S205","S206","S207","S208",
             "S209","S210","S211","S212","S213","S214","S215","S216","S217","S218","S219","S220"],
    // 灵药坊市：原22件 + S221~S240
    "L006": ["S022","S019","S024","S030","S018","S008","S027","S032","S037","S042",
             "S047","S052","S057","S062","S067","S072","S077","S082","S087","S092",
             "S106","S116", "S221","S222","S223","S224","S225","S226","S227","S228",
             "S229","S230","S231","S232","S233","S234","S235","S236","S237","S238","S239","S240"],
    // 碧波寒潭：原22件 + S241~S260
    "L007": ["S006","S021","S008","S027","S019","S025","S030","S034","S039","S044",
             "S049","S054","S059","S064","S069","S074","S079","S084","S089","S094",
             "S107","S117", "S241","S242","S243","S244","S245","S246","S247","S248",
             "S249","S250","S251","S252","S253","S254","S255","S256","S257","S258","S259","S260"],
    // 藏书峰：原22件 + S261~S280
    "L008": ["S009","S012","S023","S008","S021","S025","S027","S033","S038","S043",
             "S048","S053","S058","S063","S068","S073","S078","S083","S088","S093",
             "S108","S118", "S261","S262","S263","S264","S265","S266","S267","S268",
             "S269","S270","S271","S272","S273","S274","S275","S276","S277","S278","S279","S280"],
    // 百炼谷：原22件 + S281~S300
    "L009": ["S024","S030","S019","S027","S008","S022","S006","S031","S036","S041",
             "S046","S051","S056","S061","S066","S071","S076","S081","S086","S091",
             "S109","S119", "S281","S282","S283","S284","S285","S286","S287","S288",
             "S289","S290","S291","S292","S293","S294","S295","S296","S297","S298","S299","S300"],
    // 凌霄殿：原22件 + S301~S320
    "L010": ["S001","S002","S005","S009","S013","S015","S023","S032","S037","S042",
             "S047","S052","S057","S062","S067","S072","S077","S082","S087","S092",
             "S110","S120", "S301","S302","S303","S304","S305","S306","S307","S308",
             "S309","S310","S311","S312","S313","S314","S315","S316","S317","S318","S319","S320"]
};


// ========= 秘境探宝指令 =========
let cmd_dig_treasure = seal.ext.newCmdItemInfo();
cmd_dig_treasure.name = "秘境探宝";
cmd_dig_treasure.help = "。秘境探宝 [地点编号] - 在修仙界秘境中寻找灵宝，不同地点有不同宝物（10分钟冷却）";

cmd_dig_treasure.solve = (ctx, msg, cmdArgs) => {
    initGiftStorage();
    
    const platform = msg.platform;
    const uid = msg.sender.userId;
    
    const reg = normalize(getReg());
    if (!reg[platform]) reg[platform] = {};
    
    let characterName = '';
    for (const name in reg[platform]) {
        const rec = reg[platform][name];
        if (Array.isArray(rec) && rec[0] === uid) {
            characterName = name;
            break;
        }
    }
    
    if (!characterName) {
        seal.replyToSender(ctx, msg, "请先使用。踏入仙途 创建道号后再来探宝");
        return seal.ext.newCmdExecuteResult(true);
    }

    const locationId = (cmdArgs.getArgN(1) || "").trim().toUpperCase();
    
    if (!locationId || locationId === "HELP") {
        let locationList = ["🏮【修仙界秘境地点】"];
        for (const [id, name] of Object.entries(BIANJING_LOCATIONS)) {
            locationList.push(`${id}: ${name}`);
        }
        locationList.push("\n💡 不同秘境出产的灵宝不同，自行探索");
        locationList.push("使用：。秘境探宝 L001");
        seal.replyToSender(ctx, msg, locationList.join("\n"));
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!BIANJING_LOCATIONS[locationId]) {
        seal.replyToSender(ctx, msg, "❌ 未知的秘境，请查看地点列表");
        return seal.ext.newCmdExecuteResult(true);
    }

    const cooldownCheck = checkCooldown("dig_cooldowns", platform, characterName, 10);
    if (cooldownCheck.onCooldown) {
        seal.replyToSender(ctx, msg, `⏳ 在${BIANJING_LOCATIONS[locationId]}探宝后需调息，${cooldownCheck.remaining}分钟后再来`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const giftPool = LOCATION_GIFT_POOLS[locationId];
    if (!giftPool || giftPool.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 该秘境暂无灵宝");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const weights = giftPool.map(id => {
        const gift = SONG_GIFTS[id];
        return gift ? Math.max(1, 50 - gift.value) : 1;
    });
    
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0);
    let randomWeight = Math.random() * totalWeight;
    
    let selectedGiftId = giftPool[0];
    for (let i = 0; i < giftPool.length; i++) {
        randomWeight -= weights[i];
        if (randomWeight <= 0) {
            selectedGiftId = giftPool[i];
            break;
        }
    }

    const gift = SONG_GIFTS[selectedGiftId];
    if (!gift) {
        seal.replyToSender(ctx, msg, "❌ 探宝出错，请稍后再试");
        return seal.ext.newCmdExecuteResult(true);
    }

    const inventory = getUserInventory(platform, characterName);
    inventory[selectedGiftId] = (inventory[selectedGiftId] || 0) + 1;
    saveUserInventory(platform, characterName, inventory);

    const locationEvents = {
        "L001": [
            `在青云剑冢的残剑堆中，你发现了一缕剑意凝聚成的灵宝！`,
            `剑冢深处传来剑鸣，你循声找到了一件前人遗留的宝物！`,
            `一柄断剑上附着此物，似有灵性！`
        ],
        "L002": [
            `在天机阁的藏经架角落，你发现了一件被遗忘的灵宝！`,
            `阁中长老遗留的锦囊中，竟有这等宝物！`,
            `机关暗格里藏着一件古朴的灵物！`
        ],
        "L003": [
            `醉仙楼的酒窖里，你找到了一件醉仙遗留的法器！`,
            `酒桌下滚出一枚丹药瓶，打开竟是灵宝！`,
            `掌柜拿出珍藏多年的宝物与你结缘！`
        ],
        "L004": [
            `珍宝阁的货架上，你相中了这件灵力充沛的灵宝！`,
            `摊主展示了一件祖传之物，你以机缘获得！`,
            `阁中宝光闪烁，你眼疾手快取下一件！`
        ],
        "L005": [
            `演武擂台的地砖下，埋藏着一件昔年冠军的灵宝！`,
            `擂台边一位老修士赠你一件防身法器！`,
            `观众席座椅下，你发现了遗失的宝物！`
        ],
        "L006": [
            `灵药坊市的摊位中，你淘到了这株罕见的灵药！`,
            `药贩向你推荐了他的镇摊之宝！`,
            `在坊市角落，你发现了这枚被忽视的灵丹！`
        ],
        "L007": [
            `碧波寒潭的水底，你捞起了一件寒属性灵宝！`,
            `潭边石缝中藏着一件避水法器！`,
            `寒潭中的灵龟吐出一颗灵珠，你迅速收起！`
        ],
        "L008": [
            `藏书峰的书架缝隙中，你发现了一枚功法玉简！`,
            `峰中前辈的洞府遗物里，有这件灵宝！`,
            `翻阅古籍时掉出一件小巧法器！`
        ],
        "L009": [
            `百炼谷的废弃炉膛中，你找到了一件炼器半成品！`,
            `谷中铁匠赠你一件亲手打造的灵宝！`,
            `矿石堆里藏着一块稀有灵材！`
        ],
        "L010": [
            `凌霄殿的偏殿宝匣中，你发现了一件皇家灵宝！`,
            `殿中仙侍悄悄塞给你一件珍藏！`,
            `玉阶之下，你拾得一枚上古灵佩！`
        ]
    };

    const events = locationEvents[locationId] || [
        `在${BIANJING_LOCATIONS[locationId]}，你意外发现了一件灵宝！`,
        `机缘巧合下，你得到了此物！`
    ];
    
    const randomEvent = events[Math.floor(Math.random() * events.length)];

    seal.replyToSender(ctx, msg, 
        `🏯 ${randomEvent}\n` +
        `📍 秘境：${BIANJING_LOCATIONS[locationId]}\n` +
        `🎁 获得：${gift.name} (${selectedGiftId})\n` +
        `📝 ${gift.description}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `🏷️ 品阶：${gift.rarity}\n` +
        `📦 已存入你的储物袋\n` +
        `⏰ 下次探宝需等待10分钟`
    );

    logGiftAction("探宝", characterName, null, selectedGiftId);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["秘境探宝"] = cmd_dig_treasure;

function getCharacterName(platform, uid) {
    const reg = normalize(getReg());
    if (!reg[platform]) return null;
    for (const name in reg[platform]) {
        const rec = reg[platform][name];
        if (Array.isArray(rec) && rec[0] === uid) {
            return name;
        }
    }
    return null;
}

// ========= 灵宝图鉴 =========
let cmd_gift_list = seal.ext.newCmdItemInfo();
cmd_gift_list.name = "灵宝图鉴";
cmd_gift_list.help = "。灵宝图鉴 - 查看所有灵宝的编号和名称";

cmd_gift_list.solve = (ctx, msg) => {
    let giftList = ["🎁【灵宝图鉴】"];
    let count = 0;
    for (const [id, gift] of Object.entries(SONG_GIFTS)) {
        count++;
        giftList.push(`${id}: ${gift.name} (${gift.value}灵石)`);
        if (count % 10 === 0) giftList.push("");
    }
    giftList.push(`\n📊 总计：${count}件灵宝`);
    giftList.push("💡 使用编号进行赠送或窃取");
    seal.replyToSender(ctx, msg, giftList.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["灵宝图鉴"] = cmd_gift_list;

// ========= 我的储物袋 =========
let cmd_my_inventory = seal.ext.newCmdItemInfo();
cmd_my_inventory.name = "我的储物袋";
cmd_my_inventory.help = "。我的储物袋 - 查看自己拥有的灵宝";

cmd_my_inventory.solve = (ctx, msg) => {
    initGiftStorage();
    
    const platform = msg.platform;
    const uid = msg.sender.userId;
    const characterName = getCharacterName(platform, uid);
    
    if (!characterName) {
        seal.replyToSender(ctx, msg, "请先使用。踏入仙途 创建道号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const inventory = getUserInventory(platform, characterName);
    
    if (Object.keys(inventory).length === 0) {
        seal.replyToSender(ctx, msg, "📭 你的储物袋空空如也，快去。秘境探宝 寻找灵宝吧！");
        return seal.ext.newCmdExecuteResult(true);
    }

    let inventoryList = [`📦【${characterName}的储物袋】`];
    let totalValue = 0;
    let totalItems = 0;
    
    for (const [giftId, count] of Object.entries(inventory)) {
        const gift = SONG_GIFTS[giftId];
        if (gift) {
            inventoryList.push(`${giftId}: ${gift.name} × ${count} (${gift.value}灵石)`);
            totalValue += gift.value * count;
            totalItems += count;
        }
    }
    
    inventoryList.push(`\n💎 灵宝总数：${totalItems}件`);
    inventoryList.push(`💰 总价值：${totalValue}灵石`);
    inventoryList.push(`🛡️ ${totalItems <= 5 ? "储物袋单薄，邪修不会觊觎" : "小心邪修！"}`);
    inventoryList.push(`💡 赠予灵宝时请使用对应的编号`);
    
    seal.replyToSender(ctx, msg, inventoryList.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["我的储物袋"] = cmd_my_inventory;

// ========= 赠予灵宝 =========
let cmd_send_gift = seal.ext.newCmdItemInfo();
cmd_send_gift.name = "赠予灵宝";
cmd_send_gift.help = "。赠予灵宝 对方道号 灵宝编号 - 从储物袋中赠予灵宝";

cmd_send_gift.solve = (ctx, msg, cmdArgs) => {
    initGiftStorage();
    
    const platform = msg.platform;
    const uid = msg.sender.userId;
    const senderName = getCharacterName(platform, uid);
    
    if (!senderName) {
        seal.replyToSender(ctx, msg, "请先使用。踏入仙途 创建道号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const receiverName = (cmdArgs.getArgN(1) || "").trim();
    const giftId = (cmdArgs.getArgN(2) || "").trim().toUpperCase();

    if (!receiverName || !giftId) {
        seal.replyToSender(ctx, msg, "用法：。赠予灵宝 对方道号 灵宝编号\n使用。我的储物袋 查看编号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const gift = SONG_GIFTS[giftId];
    if (!gift) {
        seal.replyToSender(ctx, msg, "❌ 未知的灵宝编号，使用。灵宝图鉴 查看正确编号");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (receiverName === senderName) {
        seal.replyToSender(ctx, msg, "🌸 灵宝不可自赠，当赠予有缘人。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const reg = normalize(getReg());
    if (!reg[platform] || !reg[platform][receiverName]) {
        seal.replyToSender(ctx, msg, "❌ 未找到该道号，请确认对方已使用。踏入仙途");
        return seal.ext.newCmdExecuteResult(true);
    }

    const senderInventory = getUserInventory(platform, senderName);
    if (!senderInventory[giftId] || senderInventory[giftId] <= 0) {
        seal.replyToSender(ctx, msg, `❌ 你的储物袋中没有 ${gift.name}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    senderInventory[giftId]--;
    if (senderInventory[giftId] <= 0) {
        delete senderInventory[giftId];
    }
    saveUserInventory(platform, senderName, senderInventory);

    const receiverInventory = getUserInventory(platform, receiverName);
    receiverInventory[giftId] = (receiverInventory[giftId] || 0) + 1;
    saveUserInventory(platform, receiverName, receiverInventory);

    let senderMessage = `🎁 你已赠出 ${gift.name} 给「${receiverName}」\n` +
        `📝 ${gift.description}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `🗳️ 灵宝已送达对方的储物袋`;
    
    seal.replyToSender(ctx, msg, senderMessage);

    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${reg[platform][receiverName][0]}`;
    newmsg.groupId = `${platform}-Group:${reg[platform][receiverName][1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    let receiverMessage = `🎀 有修士赠你灵宝\n` +
        `来自「${senderName}」——\n` +
        `🏮 ${gift.name} (${giftId})\n` +
        `📝 ${gift.description}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `💫 已存入你的储物袋`;

    seal.replyToSender(newctx, newmsg, receiverMessage);

    logGiftAction("赠予", senderName, receiverName, giftId);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["赠予灵宝"] = cmd_send_gift;

// ========= 窃取灵宝 =========
let cmd_steal_gift = seal.ext.newCmdItemInfo();
cmd_steal_gift.name = "窃取灵宝";
cmd_steal_gift.help = "。窃取灵宝 对方道号 - 尝试从对方储物袋窃取一件灵宝（30分钟冷却）";

cmd_steal_gift.solve = (ctx, msg, cmdArgs) => {
    initGiftStorage();
    
    const platform = msg.platform;
    const uid = msg.sender.userId;
    const thiefName = getCharacterName(platform, uid);
    
    if (!thiefName) {
        seal.replyToSender(ctx, msg, "请先使用。踏入仙途 创建道号");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetName = (cmdArgs.getArgN(1) || "").trim();

    if (!targetName) {
        seal.replyToSender(ctx, msg, "用法：。窃取灵宝 对方道号");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (targetName === thiefName) {
        seal.replyToSender(ctx, msg, "🤨 窃取自己的灵宝？有违道心");
        return seal.ext.newCmdExecuteResult(true);
    }

    const reg = normalize(getReg());
    if (!reg[platform] || !reg[platform][targetName]) {
        seal.replyToSender(ctx, msg, "❌ 未找到该道号，请确认对方已使用。踏入仙途");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetTotalItems = getUserTotalItems(platform, targetName);
    if (targetTotalItems <= 5) {
        seal.replyToSender(ctx, msg, `❌ 「${targetName}」的储物袋只有${targetTotalItems}件灵宝，太过寒酸，邪修都懒得动手`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const cooldownCheck = checkCooldown("steal_cooldowns", platform, thiefName, 30);
    if (cooldownCheck.onCooldown) {
        seal.replyToSender(ctx, msg, `⏳ 上次窃取后需低调行事，${cooldownCheck.remaining}分钟后再尝试`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetInventory = getUserInventory(platform, targetName);
    const targetItems = Object.keys(targetInventory).filter(giftId => {
        return targetInventory[giftId] > 0 && SONG_GIFTS[giftId];
    });
    
    if (targetItems.length === 0) {
        seal.replyToSender(ctx, msg, `❌ 「${targetName}」的储物袋中没有可窃取的有效灵宝`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const baseChance = 40;
    const bonusChance = Math.min(targetItems.length * 3, 30);
    
    const weightedItems = [];
    for (const giftId of targetItems) {
        const gift = SONG_GIFTS[giftId];
        if (gift) {
            const weight = Math.max(1, 50 - gift.value);
            for (let i = 0; i < weight; i++) {
                weightedItems.push(giftId);
            }
        }
    }
    
    if (weightedItems.length === 0) {
        seal.replyToSender(ctx, msg, `❌ 「${targetName}」的储物袋中没有可窃取的有效灵宝`);
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const randomGiftId = weightedItems[Math.floor(Math.random() * weightedItems.length)];
    const gift = SONG_GIFTS[randomGiftId];
    
    const valuePenalty = Math.min(gift.value * 0.5, 30);
    const successChance = baseChance + bonusChance - valuePenalty;
    const isSuccess = Math.random() * 100 < successChance;

    if (!isSuccess) {
        seal.replyToSender(ctx, msg,
            `🕵️ 你试图潜入「${targetName}」的储物袋...\n` +
            `🚨 触发了禁制！窃取失败\n` +
            `⏰ 下次窃取需等待30分钟`
        );
        
        const targetMsg = seal.newMessage();
        targetMsg.messageType = "group";
        targetMsg.sender = {};
        targetMsg.sender.userId = `${platform}:${reg[platform][targetName][0]}`;
        targetMsg.groupId = `${platform}-Group:${reg[platform][targetName][1]}`;
        const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);
        
        seal.replyToSender(targetCtx, targetMsg,
            `🚨 有邪修试图闯入你的储物袋！\n` +
            `🛡️ 幸好禁制生效，灵宝安然无恙\n` +
            `💡 提示：储物袋灵宝少于5件时，邪修不会觊觎`
        );
        
        logGiftAction("窃取失败", thiefName, targetName, randomGiftId, false);
        return seal.ext.newCmdExecuteResult(true);
    }

    targetInventory[randomGiftId]--;
    if (targetInventory[randomGiftId] <= 0) {
        delete targetInventory[randomGiftId];
    }
    saveUserInventory(platform, targetName, targetInventory);

    const thiefInventory = getUserInventory(platform, thiefName);
    thiefInventory[randomGiftId] = (thiefInventory[randomGiftId] || 0) + 1;
    saveUserInventory(platform, thiefName, thiefInventory);

    const successMessages = [
        `你悄然潜入，如入无人之境...`,
        `月黑风高夜，窃宝成功时...`,
        `你避开了所有禁制，满载而归...`,
        `趁其闭关，你顺利得手...`,
        `你化形为灵鹤，叼走了灵宝...`
    ];
    const randomMessage = successMessages[Math.floor(Math.random() * successMessages.length)];

    seal.replyToSender(ctx, msg,
        `🕵️ ${randomMessage}\n` +
        `🎁 成功窃取：${gift.name} (${randomGiftId})\n` +
        `📝 ${gift.description}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `🗳️ 已存入你的储物袋\n` +
        `⏰ 下次窃取需等待30分钟`
    );

    const targetMsg = seal.newMessage();
    targetMsg.messageType = "group";
    targetMsg.sender = {};
    targetMsg.sender.userId = `${platform}:${reg[platform][targetName][0]}`;
    targetMsg.groupId = `${platform}-Group:${reg[platform][targetName][1]}`;
    const targetCtx = seal.createTempCtx(ctx.endPoint, targetMsg);
    
    seal.replyToSender(targetCtx, targetMsg,
        `🚨 你的储物袋遭窃！\n` +
        `📦 丢失：${gift.name}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `🕵️ 贼人身份不明，已逃之夭夭\n` +
        `💡 提示：储物袋灵宝少于5件时，邪修不会觊觎`
    );

    logGiftAction("窃取成功", thiefName, targetName, randomGiftId, true);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["窃取灵宝"] = cmd_steal_gift;

// ========= 修仙财富榜 =========
let cmd_wealth_rank = seal.ext.newCmdItemInfo();
cmd_wealth_rank.name = "修仙财富榜";
cmd_wealth_rank.help = "。修仙财富榜 - 查看最富有的修士排名（仅执事可用）";

cmd_wealth_rank.solve = (ctx, msg) => {
    initGiftStorage();

    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 该指令仅限仙门执事使用");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const platform = msg.platform;
    const allInventory = JSON.parse(ext.storageGet("song_inventory") || "{}");
    const platformInventory = allInventory[platform] || {};
    
    const wealthList = [];
    
    for (const [characterName, inventory] of Object.entries(platformInventory)) {
        let totalWealth = 0;
        let totalItems = 0;
        
        for (const [giftId, count] of Object.entries(inventory)) {
            let giftValue = SONG_GIFTS[giftId]?.value || 0;
            totalWealth += giftValue * count;
            totalItems += count;
        }
        
        if (totalItems > 0) {
            wealthList.push({
                name: characterName,
                wealth: totalWealth,
                items: totalItems
            });
        }
    }
    
    wealthList.sort((a, b) => b.wealth - a.wealth);
    
    let rankList = ["💰【修仙财富榜】"];
    
    if (wealthList.length === 0) {
        rankList.push("暂无拥有灵宝的修士");
    } else {
        for (let i = 0; i < Math.min(wealthList.length, 10); i++) {
            const person = wealthList[i];
            rankList.push(`${i + 1}. ${person.name} - ${person.wealth}灵石 (${person.items}件灵宝)`);
        }
    }
    
    seal.replyToSender(ctx, msg, rankList.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["修仙财富榜"] = cmd_wealth_rank;

// ========= 执事赠予预设灵宝 =========
let cmd_admin_give_preset_gift = seal.ext.newCmdItemInfo();
cmd_admin_give_preset_gift.name = "执事赠予灵宝";
cmd_admin_give_preset_gift.help = "。执事赠予灵宝 目标道号 灵宝编号 [数量] - 执事直接赠予预设灵宝给修士";

cmd_admin_give_preset_gift.solve = (ctx, msg, cmdArgs) => {
    initGiftStorage();
    
    const platform = msg.platform;
    
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 该指令仅限仙门执事使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetName = (cmdArgs.getArgN(1) || "").trim();
    const giftId = (cmdArgs.getArgN(2) || "").trim().toUpperCase();
    const quantityStr = (cmdArgs.getArgN(3) || "1").trim();

    if (!targetName || !giftId) {
        seal.replyToSender(ctx, msg, 
            "用法：。执事赠予灵宝 目标道号 灵宝编号 [数量]\n\n" +
            "示例：\n" +
            "。执事赠予灵宝 青云子 S001\n" +
            "。执事赠予灵宝 青云子 S001 3\n\n" +
            "💡 数量默认为1，最大为10\n" +
            "🎁 使用。灵宝图鉴 查看所有编号"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    if (!SONG_GIFTS[giftId]) {
        seal.replyToSender(ctx, msg, 
            `❌ 灵宝编号 "${giftId}" 不存在\n\n` +
            `💡 使用。灵宝图鉴 查看所有可用编号`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    let quantity = parseInt(quantityStr);
    if (isNaN(quantity) || quantity < 1) quantity = 1;
    if (quantity > 10) {
        seal.replyToSender(ctx, msg, "❌ 单次赠予数量不能超过10个");
        return seal.ext.newCmdExecuteResult(true);
    }

    const reg = normalize(getReg());
    if (!reg[platform] || !reg[platform][targetName]) {
        seal.replyToSender(ctx, msg, 
            `❌ 未找到道号 "${targetName}"\n\n` +
            `💡 请确认对方已使用。踏入仙途 创建道号\n` +
            `📜 使用。仙门名录 查看所有已登记修士`
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const gift = SONG_GIFTS[giftId];
    const operator = getCharacterName(platform, msg.sender.userId) || "执事";

    const targetInventory = getUserInventory(platform, targetName);
    targetInventory[giftId] = (targetInventory[giftId] || 0) + quantity;
    saveUserInventory(platform, targetName, targetInventory);

    seal.replyToSender(ctx, msg,
        `✨ 执事赠予成功！\n\n` +
        `👤 目标修士：${targetName}\n` +
        `🎁 灵宝名称：${gift.name} (${giftId})\n` +
        `📦 赠予数量：${quantity}个\n` +
        `📝 灵宝描述：${gift.description}\n` +
        `💎 价值：${gift.value} 灵石\n` +
        `🏷️ 品阶：${gift.rarity}\n` +
        `👤 操作者：${operator}\n\n` +
        `🗳️ 已存入对方的储物袋`
    );

    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${reg[platform][targetName][0]}`;
    newmsg.groupId = `${platform}-Group:${reg[platform][targetName][1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    seal.replyToSender(newctx, newmsg,
        `🎁 仙门恩赐降临！\n\n` +
        `✨ 你收到了来自 ${operator} 的珍贵灵宝\n` +
        `🏷️ 灵宝名称：${gift.name}\n` +
        `📦 获得数量：${quantity}个\n` +
        `📝 ${gift.description}\n` +
        `💎 价值：${gift.value} 灵石/个\n` +
        `🏷️ 品阶：${gift.rarity}\n\n` +
        `💫 已存入你的储物袋\n` +
        `📦 使用。我的储物袋 查看所有灵宝`
    );

    const adminLogs = JSON.parse(ext.storageGet("admin_preset_gift_logs") || "[]");
    adminLogs.push({
        operator: operator,
        target: targetName,
        giftId: giftId,
        giftName: gift.name,
        quantity: quantity,
        totalValue: gift.value * quantity,
        timestamp: Date.now()
    });
    if (adminLogs.length > 50) adminLogs.splice(0, adminLogs.length - 50);
    ext.storageSet("admin_preset_gift_logs", JSON.stringify(adminLogs));

    for (let i = 0; i < quantity; i++) {
        logGiftAction("执事赠予", operator, targetName, giftId, true);
    }

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["执事赠予灵宝"] = cmd_admin_give_preset_gift;

// ========= 批量赠予灵宝 =========
let cmd_admin_batch_give_gifts = seal.ext.newCmdItemInfo();
cmd_admin_batch_give_gifts.name = "批量赠予灵宝";
cmd_admin_batch_give_gifts.help = "。批量赠予灵宝 目标道号 灵宝编号列表 - 批量赠予多个灵宝";

cmd_admin_batch_give_gifts.solve = (ctx, msg, cmdArgs) => {
    initGiftStorage();
    
    const platform = msg.platform;
    
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 该指令仅限仙门执事使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetName = (cmdArgs.getArgN(1) || "").trim();
    const giftIdsStr = (cmdArgs.getArgN(2) || "").trim();

    if (!targetName || !giftIdsStr) {
        seal.replyToSender(ctx, msg, 
            "用法：。批量赠予灵宝 目标道号 灵宝编号列表\n\n" +
            "示例：\n" +
            "。批量赠予灵宝 青云子 S001,S002,S003\n" +
            "。批量赠予灵宝 青云子 S001 S002 S003\n\n" +
            "💡 支持逗号或空格分隔\n" +
            "🎁 单次最多10种不同灵宝"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    const giftIds = giftIdsStr.split(/[,，\s]+/).map(id => id.trim().toUpperCase()).filter(id => id);
    
    if (giftIds.length === 0) {
        seal.replyToSender(ctx, msg, "❌ 未提供有效的灵宝编号");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (giftIds.length > 10) {
        seal.replyToSender(ctx, msg, "❌ 单次批量赠予不能超过10种灵宝");
        return seal.ext.newCmdExecuteResult(true);
    }

    const reg = normalize(getReg());
    if (!reg[platform] || !reg[platform][targetName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到道号 "${targetName}"`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const operator = getCharacterName(platform, msg.sender.userId) || "执事";
    const targetInventory = getUserInventory(platform, targetName);

    const results = [];
    const failedGifts = [];
    let totalValue = 0;

    for (const giftId of giftIds) {
        if (SONG_GIFTS[giftId]) {
            const gift = SONG_GIFTS[giftId];
            targetInventory[giftId] = (targetInventory[giftId] || 0) + 1;
            results.push({
                id: giftId,
                name: gift.name,
                value: gift.value,
                rarity: gift.rarity
            });
            totalValue += gift.value;
            logGiftAction("批量赠予", operator, targetName, giftId, true);
        } else {
            failedGifts.push(giftId);
        }
    }

    saveUserInventory(platform, targetName, targetInventory);

    const adminLogs = JSON.parse(ext.storageGet("admin_batch_gift_logs") || "[]");
    adminLogs.push({
        operator: operator,
        target: targetName,
        giftCount: results.length,
        gifts: results.map(g => ({id: g.id, name: g.name})),
        totalValue: totalValue,
        failedGifts: failedGifts,
        timestamp: Date.now()
    });
    if (adminLogs.length > 50) adminLogs.splice(0, adminLogs.length - 50);
    ext.storageSet("admin_batch_gift_logs", JSON.stringify(adminLogs));

    let resultMessage = 
        `✨ 批量赠予完成！\n\n` +
        `👤 目标修士：${targetName}\n` +
        `👤 操作者：${operator}\n\n` +
        `✅ 成功赠予 ${results.length} 件灵宝：\n`;

    for (const gift of results) {
        resultMessage += `• ${gift.id}: ${gift.name} (${gift.value}灵石, ${gift.rarity})\n`;
    }

    resultMessage += `\n💰 总价值：${totalValue} 灵石\n`;
    resultMessage += `🗳️ 已存入对方的储物袋`;

    if (failedGifts.length > 0) {
        resultMessage += `\n\n❌ 以下灵宝编号无效：${failedGifts.join(', ')}`;
    }

    seal.replyToSender(ctx, msg, resultMessage);

    const newmsg = seal.newMessage();
    newmsg.messageType = "group";
    newmsg.sender = {};
    newmsg.sender.userId = `${platform}:${reg[platform][targetName][0]}`;
    newmsg.groupId = `${platform}-Group:${reg[platform][targetName][1]}`;
    const newctx = seal.createTempCtx(ctx.endPoint, newmsg);

    let targetMessage = 
        `🎁 仙门大礼包送达！\n\n` +
        `✨ 你收到了来自 ${operator} 的批量灵宝\n` +
        `📦 获得 ${results.length} 件珍贵灵宝：\n`;

    for (const gift of results.slice(0, 5)) {
        targetMessage += `• ${gift.name} (${gift.value}灵石)\n`;
    }

    if (results.length > 5) {
        targetMessage += `• ... 还有 ${results.length - 5} 件灵宝\n`;
    }

    targetMessage += 
        `\n💰 总价值：${totalValue} 灵石\n` +
        `💫 已存入你的储物袋\n` +
        `📦 使用。我的储物袋 查看所有灵宝`;

    seal.replyToSender(newctx, newmsg, targetMessage);

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["批量赠予灵宝"] = cmd_admin_batch_give_gifts;

// ========= 重置系统（执事） =========
let cmd_reset_system = seal.ext.newCmdItemInfo();
cmd_reset_system.name = "重置修仙界";
cmd_reset_system.help = "。重置修仙界 确认密码 - 完全清空所有数据（危险操作）";

cmd_reset_system.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 该指令仅限仙门执事使用");
        return seal.ext.newCmdExecuteResult(true);
    }

    const confirmation = (cmdArgs.getArgN(1) || "").trim();
    
    if (confirmation !== "确认重置") {
        seal.replyToSender(ctx, msg,
            "⚠️【危险操作警告】\n\n" +
            "此操作将永久删除所有修仙界数据：\n\n" +
            "🗑️ 清空内容：\n" +
            "• 所有修士登记\n" +
            "• 所有灵宝库存\n" +
            "• 所有游戏记录\n\n" +
            "💀 此操作不可撤销！\n\n" +
            "✅ 如果确定要重置，请使用：\n" +
            "。重置修仙界 确认重置\n\n" +
            "📜 安全提示：建议先备份重要数据"
        );
        return seal.ext.newCmdExecuteResult(true);
    }

    ext.storageSet(STORE_KEY, "{}");
    ext.storageSet("song_inventory", "{}");
    ext.storageSet("dig_cooldowns", "{}");
    ext.storageSet("steal_cooldowns", "{}");
    ext.storageSet("gift_logs", "[]");
    ext.storageSet("admin_preset_gift_logs", "[]");
    ext.storageSet("admin_batch_gift_logs", "[]");

    seal.replyToSender(ctx, msg,
        "♻️【修仙界已重置】\n\n" +
        "✅ 所有数据已被清空\n" +
        "🌺 天地重开，万物复苏\n" +
        "💫 现在可以使用。踏入仙途 开始全新的修仙之旅"
    );

    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["重置修仙界"] = cmd_reset_system;

// ========= 设置修仙公告群 =========
let cmd_set_announce_group = seal.ext.newCmdItemInfo();
cmd_set_announce_group.name = "设置修仙公告群";
cmd_set_announce_group.help = "。设置修仙公告群 群号 或 。设置修仙公告群 guildId&&groupId（仅执事可用）";

cmd_set_announce_group.solve = (ctx, msg, cmdArgs) => {
  if (!isUserAdmin(ctx, msg)) {
    seal.replyToSender(ctx, msg, "❌ 该指令仅限仙门执事使用");
    return seal.ext.newCmdExecuteResult(true);
  }

  let newGroupId = (cmdArgs.getArgN(1) || '').trim();
  if (!newGroupId) {
    const current = getAnnounceGroupId();
    seal.replyToSender(ctx, msg, `📢 当前公告群设置为：${current}\n使用 。设置修仙公告群 新群号 来修改`);
    return seal.ext.newCmdExecuteResult(true);
  }

  // 简单验证格式：支持纯数字 或 包含&&的字符串
  if (!/^\d+$/.test(newGroupId) && !newGroupId.includes('&&')) {
    seal.replyToSender(ctx, msg, "❌ 群号格式错误，应为纯数字 或 guildId&&groupId 格式");
    return seal.ext.newCmdExecuteResult(true);
  }

  setAnnounceGroupId(newGroupId);
  seal.replyToSender(ctx, msg, `✅ 公告群已更新为：${newGroupId}\n今后所有系统公告将发送至此群`);
  _logAdmin(ctx, msg, `【公告群变更】新群号 → ${newGroupId}`);
  return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["设置修仙公告群"] = cmd_set_announce_group;