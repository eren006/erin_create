// ==UserScript==
// @name         人间烟火
// @author       长日将尽
// @version      3.0.0
// @description  起名立家、种地偷菜、科举入仕、婚育子嗣——一部有你参与的发家传奇
// @timestamp    1748563200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

let ext = seal.ext.find("yanghuo_v3");
if (!ext) {
    ext = seal.ext.new("yanghuo_v3", "长日将尽", "3.0.0");
    seal.ext.registerIntConfig(ext, "打猎冷却_分钟",  120);
    seal.ext.registerIntConfig(ext, "偷菜冷却_分钟",   30);
    seal.ext.registerIntConfig(ext, "收租间隔_小时",    8);
    seal.ext.register(ext);
}
// ============================================================
// 人间烟火 v3.0 — 数据常量层
// ============================================================

// ── 姓氏（50个）──
const SURNAMES = [
    "赵","钱","孙","李","周","吴","郑","王","冯","陈",
    "褚","卫","蒋","沈","韩","杨","朱","秦","尤","许",
    "何","吕","施","张","孔","曹","严","华","金","魏",
    "陶","姜","戚","谢","邹","喻","柏","水","窦","章",
    "云","苏","潘","葛","奚","范","彭","郎","鲁","韦",
];

// ── 出生村庄（30个）──
// bonus 类型：crop/shop/sell/steal/anti/exam/hunt/rare/sign/child
const VILLAGES = [
    // 农耕村（8）
    { name:"桃花村",  desc:"桃林成片，地肥水美，春日落英如雨。",              bonus:"crop",  val:0.08 },
    { name:"黑土屯",  desc:"土地肥沃发黑，种啥长啥，是出名的粮仓。",          bonus:"crop",  val:0.12 },
    { name:"五柳村",  desc:"据说陶渊明后人居此，日出而作，日落而息。",         bonus:"crop",  val:0.07 },
    { name:"稻花乡",  desc:"稻田连片，丰收时节稻花香飘十里。",                bonus:"crop",  val:0.10 },
    { name:"向阳坡",  desc:"一年四季朝南向阳，土壤温热，作物生长旺。",         bonus:"crop",  val:0.06 },
    { name:"松鹤村",  desc:"千年古松，白鹤常住，村里人个个长寿知足。",         bonus:"crop",  val:0.05 },
    { name:"荷花湾",  desc:"湖边人家，荷叶田田，夏日清香宜人。",              bonus:"crop",  val:0.05 },
    { name:"泥泞坡",  desc:"路泥坡陡，外人不爱来，但这里人踏实肯干。",         bonus:"crop",  val:0.06 },
    // 商贸村（5）
    { name:"金水镇",  desc:"水陆要道，商队必经，镇上银号比米铺还多。",         bonus:"shop",  val:0.12 },
    { name:"锦绣里",  desc:"绸缎庄云集，商贾往来，繁华热闹。",                bonus:"shop",  val:0.10 },
    { name:"马蹄坳",  desc:"官道旁小村，马队必歇脚，消息最是灵通。",           bonus:"sell",  val:0.08 },
    { name:"清风镇",  desc:"山风徐徐，民风清正，出了名不出奸商。",             bonus:"sell",  val:0.06 },
    { name:"渔湾镇",  desc:"临河而居，渔船排排，以水为生水为家。",             bonus:"sell",  val:0.07 },
    // 武勇村（4）
    { name:"铁骨寨",  desc:"山沟里的汉子个个会打铁，民风彪悍尚武。",           bonus:"steal", val:0.10 },
    { name:"烽火台",  desc:"旧时烽火台下，祖上守边的兵，骨子里有股韧劲。",     bonus:"steal", val:0.08 },
    { name:"石门关",  desc:"两山夹沟，天险雄关，易守难攻，民风强硬。",          bonus:"anti",  val:0.15 },
    { name:"九曲弯",  desc:"九道弯的山路才能到，外人难进，村民自保有方。",      bonus:"anti",  val:0.10 },
    // 书香村（4）
    { name:"文昌里",  desc:"书香门第，笔墨飘香，每届科举都出几个秀才。",        bonus:"exam",  val:0.10 },
    { name:"旧京巷",  desc:"老京城边旧巷，落魄贵族后裔，知书达理。",           bonus:"exam",  val:0.07 },
    { name:"盐碱滩",  desc:"地薄但民精明，读书改变命运是这里的共识。",          bonus:"exam",  val:0.08 },
    { name:"杏花巷",  desc:"一条长巷，两侧杏树，花开时节飘香四里。",           bonus:"exam",  val:0.05 },
    // 山野村（5）
    { name:"山脚村",  desc:"抬头见山，靠山吃山，祖辈都是猎户。",              bonus:"hunt",  val:0.10 },
    { name:"猎户坨",  desc:"家家户户挂弓箭，年年打猎不曾停歇。",              bonus:"hunt",  val:0.08 },
    { name:"药草谷",  desc:"深山背阴处，百草丛生，祖传药方比家谱还厚。",       bonus:"rare",  val:0.12 },
    { name:"青竹林",  desc:"竹林深处有人家，清幽安静，与世无争。",             bonus:"rare",  val:0.08 },
    { name:"惊雷寨",  desc:"山顶常有雷，村民早已习以为常，胆大心细。",          bonus:"rare",  val:0.06 },
    // 特殊村（4）
    { name:"破庙村",  desc:"村头有座破庙，香火不断，据说许愿很灵。",           bonus:"sign",  val:0.25 },
    { name:"狐仙岭",  desc:"岭上据说住着狐仙，村民半信半疑，凡事都谨慎。",     bonus:"child", val:0.20 },
    { name:"碎玉溪",  desc:"溪底有碎玉石，光照下如碎钻，是最美之地。",         bonus:"sell",  val:0.05 },
    { name:"望月坡",  desc:"山坡上能看见最圆的月亮，村民特别重视月圆之夜。",   bonus:"hunt",  val:0.05 },
];

// ── 作物（5级，双重解锁：财富+功名）──
// reqWealth=铜钱数, reqFame=功名等级(0=白身,1=秀才,2=举人,3=进士,4=状元)
const CROPS = {
    // 初阶——无需解锁
    "白菜": { tier:1, seed:"菜种",    cost:5,   h:2,  minY:3, maxY:7,  minP:8,   maxP:15,   reqW:0,      reqF:0, weather:["晴","多云","春雨"] },
    "韭菜": { tier:1, seed:"韭菜种",  cost:6,   h:2,  minY:4, maxY:8,  minP:6,   maxP:12,   reqW:0,      reqF:0, weather:["晴","多云","阴雨"] },
    "萝卜": { tier:1, seed:"萝卜种",  cost:8,   h:3,  minY:2, maxY:5,  minP:18,  maxP:28,   reqW:0,      reqF:0, weather:["晴","多云"] },
    "土豆": { tier:1, seed:"土豆种",  cost:15,  h:4,  minY:2, maxY:5,  minP:28,  maxP:42,   reqW:0,      reqF:0, weather:["晴","大风","旱季"] },
    "玉米": { tier:1, seed:"玉米种",  cost:12,  h:5,  minY:2, maxY:5,  minP:24,  maxP:36,   reqW:0,      reqF:0, weather:["晴","多云","春雨"] },
    // 中阶——小农(1000铜) + 秀才(1)
    "南瓜": { tier:2, seed:"南瓜种",  cost:25,  h:6,  minY:1, maxY:3,  minP:58,  maxP:90,   reqW:1000,   reqF:1, weather:["晴","多云"] },
    "西瓜": { tier:2, seed:"西瓜种",  cost:28,  h:8,  minY:1, maxY:2,  minP:68,  maxP:110,  reqW:1000,   reqF:1, weather:["晴"] },
    "棉花": { tier:2, seed:"棉花种",  cost:30,  h:8,  minY:1, maxY:3,  minP:78,  maxP:120,  reqW:1000,   reqF:1, weather:["晴","多云"] },
    "茶叶": { tier:2, seed:"茶种",    cost:35,  h:10, minY:1, maxY:2,  minP:98,  maxP:150,  reqW:1000,   reqF:1, weather:["阴雨","薄雾","多云"] },
    "桑叶": { tier:2, seed:"桑种",    cost:20,  h:7,  minY:2, maxY:4,  minP:48,  maxP:78,   reqW:1000,   reqF:1, weather:["晴","多云","春雨"] },
    // 进阶——富农(5000铜) + 举人(2)
    "草药": { tier:3, seed:"草药种",  cost:40,  h:8,  minY:1, maxY:3,  minP:78,  maxP:130,  reqW:5000,   reqF:2, weather:["阴雨","薄雾","春雨"] },
    "灵稻": { tier:3, seed:"灵稻种",  cost:120, h:16, minY:1, maxY:2,  minP:290, maxP:500,  reqW:5000,   reqF:2, weather:["春雨","阴雨"] },
    "花椒": { tier:3, seed:"花椒苗",  cost:50,  h:12, minY:1, maxY:3,  minP:118, maxP:180,  reqW:5000,   reqF:2, weather:["晴","多云"] },
    "香料": { tier:3, seed:"香料苗",  cost:60,  h:14, minY:1, maxY:2,  minP:148, maxP:220,  reqW:5000,   reqF:2, weather:["晴","薄雾"] },
    // 高阶——小商人(20000铜) + 进士(3)
    "人参": { tier:4, seed:"参苗",    cost:300, h:24, minY:1, maxY:2,  minP:590, maxP:1000, reqW:20000,  reqF:3, weather:["薄雾","阴雨"] },
    "雪莲": { tier:4, seed:"雪莲苗",  cost:400, h:36, minY:1, maxY:1,  minP:990, maxP:1800, reqW:20000,  reqF:3, weather:["薄雾","大风"] },
    "龙须菜":{ tier:4, seed:"龙须种", cost:250, h:20, minY:1, maxY:2,  minP:490, maxP:800,  reqW:20000,  reqF:3, weather:["春雨","薄雾"] },
    // 仙阶——大商人(100000铜) + 状元(4)
    "仙草": { tier:5, seed:"仙草苗",  cost:1000,h:48, minY:1, maxY:1,  minP:2490,maxP:5000, reqW:100000, reqF:4, weather:["薄雾","春雨"] },
    "神木果":{ tier:5, seed:"神木种", cost:1500,h:72, minY:1, maxY:1,  minP:3990,maxP:8000, reqW:100000, reqF:4, weather:["薄雾"] },
};
const SEED_MAP = {};
for (const [c, i] of Object.entries(CROPS)) SEED_MAP[i.seed] = c;

// ── 上山物品（按类型：animal/herb/rare/special）──
const HUNT_TABLE = [
    // 空手而归
    { w:22, type:"empty", name:null, min:0, max:0, minP:0,    maxP:0,
      desc:["深山雾重，只闻鸟鸣，一无所获","走了半天山路，怀揣空篓子回了家","上山转了一圈，什么也没遇到"] },
    // 普通动物
    { w:18, type:"animal", name:"野兔",    min:1, max:2, minP:35,   maxP:55,   desc:["眼疾手快，套住了一只肥兔子！"] },
    { w:14, type:"animal", name:"野鸡",    min:1, max:2, minP:55,   maxP:80,   desc:["草丛里扑棱棱飞出一只野鸡，逮住了！"] },
    { w:10, type:"animal", name:"野猪肉",  min:2, max:5, minP:45,   maxP:70,   desc:["遭遇野猪，血战后猎人笑到了最后！"] },
    // 普通草木
    { w:16, type:"herb",   name:"野山菌",  min:1, max:4, minP:15,   maxP:28,   desc:["在松树下发现了一片野山菌！"] },
    { w:5,  type:"herb",   name:"野山参",  min:1, max:1, minP:150,  maxP:280,  desc:["发现一株野山参，挖出来！"] },
    // 中等
    { w:6,  type:"animal", name:"狐皮",    min:1, max:1, minP:120,  maxP:200,  desc:["追了半山的狐狸，终于逮到了！"] },
    { w:4,  type:"animal", name:"梅花鹿",  min:1, max:1, minP:180,  maxP:300,  desc:["溪边饮水的梅花鹿，美而值钱！"] },
    { w:3,  type:"herb",   name:"灵芝",    min:1, max:1, minP:250,  maxP:450,  desc:["悬崖边的老松下，赫然生着一朵灵芝！！"] },
    // 稀有
    { w:1.2,type:"rare",   name:"何首乌",  min:1, max:1, minP:500,  maxP:900,  desc:["古树盘根处，挖出了百年何首乌！！！"] },
    { w:0.8,type:"rare",   name:"熊胆",    min:1, max:1, minP:400,  maxP:700,  desc:["与黑熊相搏，终于取得熊胆！！"] },
    { w:0.5,type:"rare",   name:"天山雪莲",min:1, max:1, minP:600,  maxP:1200, desc:["崖壁之上，一株雪莲傲雪而开！！！"] },
    // 极稀
    { w:0.3,type:"rare",   name:"龙骨片",  min:1, max:1, minP:1000, maxP:2000, desc:["【奇遇！】溪底淤泥中露出龙骨！！！"] },
    { w:0.2,type:"rare",   name:"百年山参", min:1, max:1, minP:1500, maxP:3000, desc:["【天降奇遇】云雾散处，百年山参就在眼前——！！！"] },
    { w:0.1,type:"rare",   name:"千年灵芝", min:1, max:1, minP:2000, maxP:4000, desc:["【传说级】山顶古洞内，千年灵芝发出幽光——！！！！"] },
];

// 链式事件（上山12%概率触发，随机结果）
// 每个事件是一个函数，调用后返回 { text, item?, count?, coins? }
const HUNT_CHAINS = [
    () => { // 受伤小鹿
        const r = Math.random();
        if (r < 0.50) return { text:"遇到一只受伤的小鹿，心软放走了……它回头衔来一块玉佩作谢。", item:"玉佩", count:1 };
        if (r < 0.80) return { text:"遇到一只受伤的小鹿，犹豫一下还是带走了。", item:"梅花鹿", count:1 };
        return { text:"遇到一只受伤的小鹿，正要靠近，被它踢了一脚，狼狈而退。", coins:-rand(10,30) };
    },
    () => { // 隐藏陶罐
        const r = Math.random();
        if (r < 0.40) return { text:"林间发现半埋土里的陶罐，挖开一看——铜钱！", coins:rand(80,300) };
        if (r < 0.75) return { text:"陶罐里是陈年老酒，香气扑鼻，带走了。", item:"陈年老酒", count:1 };
        return { text:"陶罐里是一团陈年烂泥，什么都没有。", coins:0 };
    },
    () => { // 山腰老人
        const r = Math.random();
        if (r < 0.55) return { text:"山腰遇见白发老人，原来是隐居药师，赠你几株灵草。", item:"灵芝", count:1 };
        if (r < 0.85) return { text:"是位棋痴隐士，切磋了半天棋，一无所获但开了眼界。", coins:0 };
        return { text:"竟是江湖骗子！趁不备偷走了几枚铜钱！", coins:-rand(30,80) };
    },
    () => { // 野蜂巢
        const r = Math.random();
        if (r < 0.55) return { text:"发现野蜂巢！小心取出野蜂蜜，甜滋滋的。", item:"野蜂蜜", count:rand(1,3) };
        if (r < 0.80) return { text:"想取蜂蜜，却捅了马蜂窝，被蜇得落荒而逃！", coins:-rand(5,20) };
        return { text:"蜂巢是空的，只有些蜂蜡，也值几个钱。", coins:rand(10,40) };
    },
    () => { // 废弃营地
        const r = Math.random();
        if (r < 0.40) return { text:"发现废弃猎人营地，里面留有些风干的肉。", item:"风干肉", count:rand(2,5) };
        if (r < 0.70) return { text:"营地角落里有一块玉石，捡走了。", item:"玉石", count:1 };
        return { text:"营地早已清空，只剩灰烬和寒风。", coins:0 };
    },
    () => { // 神秘石碑
        const r = Math.random();
        if (r < 0.30) return { text:"发现一块古老石碑，碑文记载了一处宝藏方位！\n（意外挖出一包埋藏的铜钱）", coins:rand(150,500) };
        if (r < 0.60) return { text:"石碑上刻着一副药方，按方抓药……旁边恰好有些对应草药。", item:"草药", count:rand(1,2) };
        return { text:"石碑风化严重，看不清字迹。叹了口气，继续走。", coins:0 };
    },
    () => { // 受伤旅人
        const r = Math.random();
        if (r < 0.60) return { text:"遇到一位受伤旅人，救助后对方感激地留下了随身盘缠。", coins:rand(50,200) };
        if (r < 0.85) return { text:"帮助旅人处理了伤口，对方感激但身无长物，只有几句道谢。", coins:0 };
        return { text:"那旅人居然是诈骗惯犯！趁你施救之际，顺走了荷包。", coins:-rand(20,80) };
    },
];

// 链式事件道具可出售价格
const SPECIAL_ITEMS = {
    "玉佩":    { minP:300, maxP:800  },
    "陈年老酒":{ minP:150, maxP:300  },
    "野蜂蜜":  { minP:30,  maxP:60   },
    "风干肉":  { minP:25,  maxP:45   },
    "玉石":    { minP:200, maxP:500  },

};

// ── 天气（8种）──
const WEATHERS = [
    { name:"艳阳高照", emoji:"☀️",  cropMod:1.10, huntMod:1.05, herbMod:0.8,  desc:"万里无云，庄稼长势喜人，出行顺畅。",   rec:["白菜","萝卜","土豆","玉米","南瓜","西瓜"]  },
    { name:"阴雨绵绵", emoji:"🌧️",  cropMod:0.90, huntMod:0.75, herbMod:1.4,  desc:"细雨滋润，药材格外茂盛，动物少见。",   rec:["草药","茶叶","灵稻","人参","龙须菜"]       },
    { name:"多云转晴", emoji:"⛅",  cropMod:1.00, huntMod:1.00, herbMod:1.0,  desc:"云开雾散，适合外出，各有所得。",        rec:["萝卜","南瓜","棉花","桑叶","花椒"]         },
    { name:"大风呼啸", emoji:"💨",  cropMod:0.80, huntMod:0.85, herbMod:0.9,  desc:"风大伤苗，庄稼有损，谨慎出行。",        rec:["土豆","南瓜","雪莲"]                       },
    { name:"干旱少雨", emoji:"🌵",  cropMod:0.75, huntMod:1.20, herbMod:0.7,  desc:"地旱裂缝，动物下山觅水，易于捕猎。",   rec:["土豆","人参"]                              },
    { name:"雷暴交加", emoji:"⛈️",  cropMod:0.65, huntMod:0.50, herbMod:0.8,  desc:"雷雨大作，不宜外出，在家种耐涝作物。", rec:["灵稻","仙草"]                              },
    { name:"春雨如油", emoji:"🌦️",  cropMod:1.25, huntMod:1.00, herbMod:1.2,  desc:"春雨贵如油，今日大丰收！",              rec:["白菜","草药","灵稻","龙须菜","仙草"]        },
    { name:"薄雾蒙蒙", emoji:"🌫️",  cropMod:1.05, huntMod:0.90, herbMod:1.3,  desc:"晨雾轻绕，药草沾露更珍贵。",            rec:["草药","人参","雪莲","仙草","神木果"]        },
];

// ── 每日事件（12种，每天随机抽1-3个）──
const DAILY_EVENTS = [
    { name:"游商过境",  emoji:"🛒", desc:"有商队路过，今日所有出售价格上浮20%！",           type:"sell_up",    val:1.20 },
    { name:"蝗灾袭来",  emoji:"🦗", desc:"蝗虫铺天盖地！今日所有作物收成减少30%！",          type:"crop_down",  val:0.70 },
    { name:"官府摊派",  emoji:"📜", desc:"官府派人收税，今日出售所得额外扣除15%。",           type:"tax",        val:0.85 },
    { name:"山中有异",  emoji:"⛰️", desc:"山里今日风平浪静，上山必有所获！",                 type:"hunt_buff",  val:1.00 },
    { name:"天降甘霖",  emoji:"🌧", desc:"及时雨！今日所有成熟作物额外增产20%！",            type:"crop_up",    val:1.20 },
    { name:"神医问诊",  emoji:"💊", desc:"游方神医过境，草药/灵芝/山参收购价今日翻倍！",     type:"herb_x2",    val:2.00 },
    { name:"贼人入村",  emoji:"🌙", desc:"村中来了贼，偷菜冷却减半，但被偷概率也更高！",     type:"steal_chaos",val:0.50 },
    { name:"大集赶市",  emoji:"🏪", desc:"百年一遇大集！所有种子今日八折出售！",              type:"seed_disc",  val:0.80 },
    { name:"冬日封山",  emoji:"❄️", desc:"大雪封山，今日上山无论如何都空手而归。",            type:"hunt_ban",   val:0.00 },
    { name:"春耕动员",  emoji:"🌱", desc:"里正号召春耕！今日种地一次不消耗种子！",            type:"free_plant", val:1.00 },
    { name:"丰年庆典",  emoji:"🎉", desc:"今年大丰年！签到额外奖励翻倍！",                    type:"signin_x2",  val:2.00 },
    { name:"山匪横行",  emoji:"⚔️", desc:"山匪为祸！今日上山有40%概率被抢走一部分铜钱！",    type:"hunt_bandit",val:0.40 },
];

// ── 科举体系 ──
const FAME = [
    { title:"白身", examCost:500,   examRate:0.60, cdH:4  },
    { title:"秀才", examCost:2000,  examRate:0.40, cdH:6  },
    { title:"举人", examCost:10000, examRate:0.25, cdH:12 },
    { title:"进士", examCost:50000, examRate:0.10, cdH:24 },
    { title:"状元", examCost:0,     examRate:0,    cdH:0  },
];

// ── 铺子 ──
// 扩地费用：第3块→第4→5→6→7块
const LAND_COSTS = [500, 2000, 8000, 30000, 100000];

const SHOPS = {
    "小铺子": { req:1, cost:1000,   minI:50,   maxI:100  },
    "酒楼":   { req:2, cost:8000,   minI:200,  maxI:400  },
    "商行":   { req:3, cost:50000,  minI:800,  maxI:1600 },
    "钱庄":   { req:4, cost:200000, minI:3000, maxI:6000 },
};

// ── 财富身份 ──
const IDENTITIES = [
    { name:"穷苦流民",  threshold:0        },
    { name:"普通村民",  threshold:200      },
    { name:"小农",      threshold:1000     },
    { name:"富农",      threshold:5000     },
    { name:"小商人",    threshold:20000    },
    { name:"大商人",    threshold:100000   },
    { name:"富甲乡里",  threshold:500000   },
    { name:"大富豪",    threshold:2000000  },
];
function getIdentity(coins) {
    let id = IDENTITIES[0];
    for (const i of IDENTITIES) { if (coins >= i.threshold) id = i; else break; }
    return id;
}

// ── 运势 ──
const FORTUNES = [
    { label:"大吉", emoji:"🌟", poem:"鸿运当头，万事大吉。",      sellM:1.15, stealM:1.15, cropM:1.20 },
    { label:"上吉", emoji:"✨", poem:"诸事顺遂，小有所得。",      sellM:1.10, stealM:1.10, cropM:1.10 },
    { label:"中吉", emoji:"🌤", poem:"平稳之日，踏实经营。",      sellM:1.05, stealM:1.00, cropM:1.05 },
    { label:"小吉", emoji:"🍀", poem:"平平之日，守成为上。",      sellM:1.00, stealM:1.00, cropM:1.00 },
    { label:"平",   emoji:"☁️", poem:"不好不坏，量力而行。",      sellM:1.00, stealM:1.00, cropM:1.00 },
    { label:"小凶", emoji:"🌧", poem:"小有阻碍，谨慎行事。",      sellM:0.92, stealM:0.90, cropM:0.95 },
    { label:"凶",   emoji:"⛈", poem:"诸事不顺，宜静不宜动。",    sellM:0.85, stealM:0.80, cropM:0.85 },
];
function getDailyFortune(userId) {
    const d = new Date();
    const seed = `${userId}_${d.getFullYear()}${d.getMonth()}${d.getDate()}`;
    let h = 5381;
    for (let i = 0; i < seed.length; i++) h = (h * 33 ^ seed.charCodeAt(i)) >>> 0;
    return FORTUNES[h % FORTUNES.length];
}

// ── 佳人花名册（50人）──
// [名字, 基础价格, 性别m/f, 描述, 加成类型, 加成值]
const CHARS = [
    ["云逸",   500,"m","寒门书生，眼神清冽，腹有诗书气自华",               null,      0    ],
    ["墨寒",   600,"m","江湖杀手，冷面冷心，却只对你低眉",                  null,      0    ],
    ["季白",   550,"m","浪迹天涯的游侠，轻功绝顶，笑起来无拘无束",           null,      0    ],
    ["沈昀",   700,"m","太子侍读，温润如玉，志在天下",                      "exam",    0.08 ],
    ["裴珩",   650,"m","将军之子，英武不凡，护短到了骨子里",                "steal",   0.08 ],
    ["叶临风", 800,"m","药谷门主，医术通神，性情淡漠却妙手仁心",             "rare",    0.10 ],
    ["顾长宁", 900,"m","京城第一美男子，家世显赫却最厌富贵",                 null,      0    ],
    ["陆辞",   750,"m","本届探花郎，才高八斗，笑起来有梨涡",                "exam",    0.05 ],
    ["傅深",   850,"m","皇商世家，手段狠辣，只对你温柔",                    "shop",    0.10 ],
    ["祁景",   700,"m","边关守将，铁汉柔情，三十年未娶",                    null,      0    ],
    ["夏侯临", 500,"m","宗室旁支，天生神力，憨厚可爱",                      null,      0    ],
    ["容绪",   600,"m","茶馆说书人，知晓天下秘事",                          null,      0    ],
    ["周晋",   550,"m","捕快头领，断案如神，嫉恶如仇",                      "anti",    0.12 ],
    ["苏慕",   650,"m","落魄世子，风骨傲然，宁折不弯",                      null,      0    ],
    ["明珩",   900,"m","国师之徒，身负异术，唯你一人例外",                   null,      0    ],
    ["贺云亭", 700,"m","御前侍卫，忠义两全，沉默寡言",                      "anti",    0.08 ],
    ["晏九",   800,"m","江湖盟主，三分醉意七分清醒",                        null,      0    ],
    ["程锦",   550,"m","绸缎商人，儒雅随和，最善经营",                      "shop",    0.08 ],
    ["薛行",   600,"m","钦天监副监，推算命数，自言命硬",                    null,      0    ],
    ["庄澜",   700,"m","水军都督，在海上长大，眼里有星辰大海",               null,      0    ],
    ["石泽",   450,"m","铁匠之子，粗犷憨实，打出的剑天下一绝",               null,      0    ],
    ["卫临",   750,"m","太医院院判，救死扶伤，手若春风",                    "rare",    0.06 ],
    ["崔远",   600,"m","藏书楼主，博闻强记，从不藏私",                      null,      0    ],
    ["阮江",   500,"m","茶馆伙计，笑容暖如朝阳，人缘极好",                  null,      0    ],
    ["林凌",   550,"m","前任捕快，归隐后只想种地，却总被江湖找上门",          "crop",    0.05 ],
    ["苏锦年", 600,"f","将门之女，上马能打仗，下马能绣花",                   "steal",   0.10 ],
    ["白鹭",   550,"f","江湖女侠，剑法凌厉，最看不惯伪君子",                "steal",   0.05 ],
    ["霍晴川", 700,"f","名门闺秀，才情出众，心思细腻",                      null,      0    ],
    ["凤瑶",   850,"f","异域公主，性格烈如骄阳，认定的事九头牛拉不回",        null,      0    ],
    ["谢明月", 800,"f","太师之女，温婉贤淑，藏着一腔不让须眉的抱负",          "exam",    0.05 ],
    ["沈素素", 500,"f","村姑出身，厨艺绝佳，悟性极高",                      "crop",    0.10 ],
    ["孟青竹", 650,"f","道观小道姑，超凡脱俗，心清如水",                    null,      0    ],
    ["李春花", 700,"f","繁花楼头牌，歌舞无双，心中早有归处",                 null,      0    ],
    ["崔颜",   750,"f","翰林千金，博览群书，擅长辩论，输了也不认",           "exam",    0.03 ],
    ["宋佳期", 800,"f","商贾之女，精于算术，眼光毒辣，不做亏本买卖",          "sell",    0.08 ],
    ["顾婵娟", 600,"f","织锦坊主，手艺天下一绝，性子温和",                   null,      0    ],
    ["云梦",   700,"f","宫中御厨，做的每道菜都是极品",                      "crop",    0.05 ],
    ["华锦",   500,"f","布衣百姓，勤劳善良，内心比任何人都要强大",            "crop",    0.05 ],
    ["秦暮雪", 650,"f","女捕快，胆大心细，连大老爷都让她三分",               "anti",    0.10 ],
    ["周婉如", 600,"f","大儒孙女，知书达理，从不争抢却处处受人敬",            null,      0    ],
    ["乔盈盈", 450,"f","养猪姑娘，豪爽可爱，力气出奇大",                    null,      0    ],
    ["陆瑶",   850,"f","前朝公主遗孤，隐于市井，心有大志",                   null,      0    ],
    ["沈云裳", 700,"f","绣娘出身，后成宫廷画师，最爱红色",                   null,      0    ],
    ["司马婵", 750,"f","商行账房，天生算账奇才，一双眼什么都逃不过",          "sell",    0.07 ],
    ["赵小鱼", 550,"f","渔家女儿，爽朗自在，说话直来直去",                   null,      0    ],
    ["柳如是", 800,"f","才女，诗画双绝，最恨虚伪",                          null,      0    ],
    ["夏初",   650,"f","桃园女主人，酿得一手好酒，喝醉才说真心话",            null,      0    ],
    ["江琴",   700,"f","云游郎中，医术精湛，走遍千山万水",                   "rare",    0.08 ],
    ["聂小倩", 750,"f","书院山长，管理严格，内心有最柔软的一块",              null,      0    ],
    ["霓裳",   900,"f","舞姬出身，身世成谜，一舞倾城",                      null,      0    ],
];

// 孩子名字池
const CHILD_NAMES_M = ["小虎","大郎","铁蛋","石头","阿福","麦子","根生","金生","水生","明","亮","旭","晨","杰","强","远","志","诚","勇","安"];
const CHILD_NAMES_F = ["小花","翠儿","春花","秋菊","夏荷","冬梅","兰","菊","梅","莲","桃","杏","柳","燕","莺","凤","雪","云","月","霞"];

// 加成类型说明（用于显示）
const BONUS_DESC = {
    crop:"农作物+", shop:"铺子收入+", sell:"售价+", steal:"偷菜+",
    anti:"防盗+", exam:"科举+", hunt:"打猎+", rare:"稀有+",
    sign:"签到+", child:"子嗣+",
};
// ============================================================
// 人间烟火 v3.0 — 工具函数 & 每日系统
// ============================================================

// ── 基础工具 ──
function rand(a, b)  { return a + Math.floor(Math.random() * (b - a + 1)); }
function pick(arr)   { return arr[Math.floor(Math.random() * arr.length)]; }
function now()       { return Date.now(); }
function atUser(uid) { const n = uid.includes(":") ? uid.split(":")[1] : uid; return `[CQ:at,qq=${n}]`; }

function fmtMs(ms) {
    if (ms <= 0) return "不到1分钟";
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000);
    if (h > 0) return m > 0 ? `${h}小时${m}分` : `${h}小时`;
    return `${m}分`;
}
function fmtCoins(n) {
    n = Math.floor(n);
    if (n >= 100) { const l = Math.floor(n / 100), t = n % 100; return t ? `${l}两${t}铜` : `${l}两`; }
    return `${n}铜`;
}

// ── 日期工具 ──
function getDateStr(offset = 0) {
    const d = new Date(Date.now() + offset * 86400000);
    return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}
function todayStr()     { return getDateStr(0);  }
function yesterdayStr() { return getDateStr(-1); }

// ── 数据存取 ──
function getData()          { try { return JSON.parse(ext.storageGet("yh3_players") || "{}"); } catch { return {}; } }
function saveData(d)        { ext.storageSet("yh3_players", JSON.stringify(d)); }
function getAttr(gid)       { try { return JSON.parse(ext.storageGet(`yh3_attr_${gid}`) || "{}"); } catch { return {}; } }
function saveAttr(gid, d)   { ext.storageSet(`yh3_attr_${gid}`, JSON.stringify(d)); }
function getDailyRaw(gid)   { try { return JSON.parse(ext.storageGet(`yh3_daily_${gid}`) || "{}"); } catch { return {}; } }
function saveDailyRaw(gid,d){ ext.storageSet(`yh3_daily_${gid}`, JSON.stringify(d)); }

function pk(ctx) { return `${ctx.group.groupId}|${ctx.player.userId}`; }

// ── 每日数据（天气 + 事件）——按群，每天刷新 ──
function getDailyData(gid) {
    const today = todayStr();
    const raw = getDailyRaw(gid);
    if (raw.date === today) return raw;

    // 生成新一天
    const weather = WEATHERS[Math.floor(Math.random() * WEATHERS.length)];
    const numEvents = rand(1, 3);
    const shuffled = [...DAILY_EVENTS].sort(() => Math.random() - 0.5);
    const events = shuffled.slice(0, numEvents);

    // 推荐作物（天气偏好 + 当前可种）
    const rec = weather.rec.filter(c => CROPS[c]);

    const festival = getTodayFestival();
    const daily = { date: today, weather, events, rec, festival };
    saveDailyRaw(gid, daily);
    return daily;
}

function hasEvent(daily, type) {
    return daily.events.some(e => e.type === type);
}
function getEvent(daily, type) {
    return daily.events.find(e => e.type === type) || null;
}

// ── 佳人初始化 ──
function getAttrInit(gid) {
    let ad = getAttr(gid);
    let changed = false;
    for (const [name, price] of CHARS) {
        if (!ad[name]) { ad[name] = { owner: null, ownerName: null, price, married: false }; changed = true; }
    }
    if (changed) saveAttr(gid, ad);
    return ad;
}

// ── 加成计算（佳人 + 村庄）──
function getCharBonuses(userId, gid) {
    const ad = getAttr(gid);
    const b = {};
    for (const [name,,, , type, val] of CHARS) {
        if (type && ad[name] && ad[name].owner === userId) b[type] = (b[type] || 0) + val;
    }
    return b;
}
function getVillageBonus(player) {
    const v = VILLAGES[player.villageIdx ?? 0];
    return v && v.bonus ? { [v.bonus]: v.val } : {};
}
function getAllBonuses(player, gid) {
    const cb = getCharBonuses(player.userId, gid);
    const vb = getVillageBonus(player);
    const result = { ...cb };
    for (const [k, v] of Object.entries(vb)) result[k] = (result[k] || 0) + v;
    return result;
}

// ── 解锁检查 ──
function canPlantCrop(player, cropName) {
    const c = CROPS[cropName];
    if (!c) return { ok: false, reason: `不存在的作物"${cropName}"` };
    if (player.coins < c.reqW)
        return { ok: false, reason: `需要身家 ${fmtCoins(c.reqW)}（当前 ${fmtCoins(player.coins)}）` };
    if ((player.fame || 0) < c.reqF)
        return { ok: false, reason: `需要功名【${FAME[c.reqF].title}】（当前【${FAME[player.fame || 0].title}】）` };
    return { ok: true };
}

// ── 端点缓存 & 消息发送 ──
const epCache = new Map();

function cacheEp(ctx) {
    if (!ctx.endPoint || !ctx.group) return;
    const key = `${ctx.endPoint.platform}:${ctx.endPoint.userId}:${ctx.group.groupId}`;
    epCache.set(key, ctx.endPoint);
}

function sendGroupMsg(player, text) {
    if (!player.groupId || !player.userId) return;
    const ep = epCache.get(`${player.epPlat}:${player.epBot}:${player.groupId}`);
    if (!ep) return;
    try {
        const m = seal.newMessage(); m.messageType = "group"; m.groupId = player.groupId;
        const c = seal.createTempCtx(ep, m);
        seal.replyToSender(c, m, text);
    } catch(e) { console.error("[人间烟火] sendGroupMsg error:", e.message); }
}

// ── 定时检查：庄稼成熟通知 ──
try {
    setInterval(() => {
        const data = getData();
        let changed = false;
        for (const [, p] of Object.entries(data)) {
            if (!p || !p.plots) continue;
            const ready = p.plots.filter(pl => pl && !pl.notified && pl.readyAt <= now());
            if (!ready.length) continue;
            const crops = ready.map(pl => `【${pl.crop}】`).join("、");
            sendGroupMsg(p, `${atUser(p.userId)} 主人！${crops}成熟了，快去 .烟火 收 吧！`);
            for (const pl of p.plots) { if (pl && !pl.notified && pl.readyAt <= now()) pl.notified = true; }
            changed = true;
        }
        if (changed) saveData(data);
    }, 120000);
} catch(e) { console.error("[人间烟火] 定时器失败:", e.message); }

// ── 玩家初始化 & 迁移 ──
function ensurePlayer(ctx) {
    cacheEp(ctx);
    const data = getData();
    const key = pk(ctx);
    if (data[key]) {
        const p = data[key];
        p.epPlat  = ctx.endPoint ? ctx.endPoint.platform : "";
        p.epBot   = ctx.endPoint ? ctx.endPoint.userId   : "";
        p.groupId = ctx.group ? ctx.group.groupId : "";
        p.userId  = ctx.player.userId;
        p.userName = ctx.player.name;
        // 迁移旧字段
        if (!p.children)   p.children   = [];
        if (!p.shops)      p.shops      = {};
        if (!p.bag)        p.bag        = {};
        if (p.villageIdx === undefined) p.villageIdx = Math.floor(Math.random() * VILLAGES.length);
        saveData(data);
    }
    return data;
}

// ── 子嗣成长阶段 ──
function childStage(bornAt) {
    const days = (now() - bornAt) / 86400000;
    if (days < 3)  return { name:"婴儿", emoji:"👶", days, canTask: false };
    if (days < 7)  return { name:"幼童", emoji:"🧒", days, canTask: false, canEdu: true };
    if (days < 15) return { name:"少年", emoji:"🧑", days, canTask: true,  tasks:["收地"] };
    return                 { name:"成年", emoji:"👨", days, canTask: true,  tasks:["收地","上山","经商"] };
}

// ── 签到系统 ──
function doSignIn(ctx, msg, data, key) {
    const p = data[key];
    const today  = todayStr();
    const yester = yesterdayStr();
    if (p.signInDate === today) {
        seal.replyToSender(ctx, msg, `今日已签到，明日再来！（连续 ${p.signInStreak || 1} 天）`);
        return;
    }

    const streak  = (p.signInDate === yester) ? (p.signInStreak || 0) + 1 : 1;
    p.signInStreak = streak;
    p.signInDate   = today;

    // 基础奖励
    let coins = rand(20, 60);
    const bonuses = getAllBonuses(p, ctx.group.groupId);
    if (bonuses.sign) coins = Math.round(coins * (1 + bonuses.sign));

    // 检查每日事件 & 节日
    const daily = getDailyData(ctx.group.groupId);
    if (hasEvent(daily, "signin_x2")) coins *= 2;
    const fest = daily.festival;
    if (fest && fest.signMod > 1) coins = Math.round(coins * fest.signMod);

    // 连签额外奖励
    let streakBonus = 0, streakGift = null, streakMsg = "";
    if (streak >= 30)      { streakBonus = 300; streakGift = { seed:"参苗",   count:1 }; streakMsg = "🎊 连续签到30天！"; }
    else if (streak >= 14) { streakBonus = 150; streakGift = { seed:"草药种", count:3 }; streakMsg = "🎁 连续签到14天！"; }
    else if (streak >= 7)  { streakBonus = 80;  streakGift = { seed:"萝卜种", count:5 }; streakMsg = "✨ 连续签到7天！"; }
    else if (streak >= 3)  { streakBonus = 25;  streakMsg  = "🌱 连续签到3天！"; }

    const total = coins + streakBonus;
    p.coins += total;
    if (streakGift) p.bag[streakGift.seed] = (p.bag[streakGift.seed] || 0) + streakGift.count;

    // 子嗣触发检查（已婚 + 子女 < 3）
    let childMsg = "";
    if (p.spouse && (p.children || []).length < 3) {
        const childRate = 0.15 + (bonuses.child || 0);
        if (Math.random() < childRate) {
            const gender = Math.random() < 0.5 ? "m" : "f";
            const namePool = gender === "m" ? CHILD_NAMES_M : CHILD_NAMES_F;
            const childName = (p.surname || "张") + pick(namePool);
            const child = { name: childName, gender, bornAt: now(), eduLevel: 0, lastTaskAt: 0 };
            if (!p.children) p.children = [];
            p.children.push(child);
            childMsg = `\n\n🍼 【喜事！】你的孩子 ${childName} 降生了！用 .烟火 孩子 查看。`;
        }
    }

    // 节日礼品
    let festMsg = "";
    if (fest) {
        festMsg = `\n${fest.emoji} 节日快乐【${fest.name}】！签到×${fest.signMod}`;
        if (fest.giftItem) {
            p.bag[fest.giftItem] = (p.bag[fest.giftItem] || 0) + (fest.giftCount || 1);
            festMsg += `，赠送${fest.giftItem}×${fest.giftCount || 1}`;
        }
    }

    // 成就检查
    const newAchs = checkAchievements(p, ctx.group.groupId);
    saveData(data);

    const flavor = ["鸡鸣三声，天色未明已起身。","晨光熹微，又是新的一天。","睁开眼，今天又是充满希望的一天。"];
    let reply = `☀️ 签到成功！（连续 ${streak} 天）\n${pick(flavor)}\n获得：${fmtCoins(total)}${festMsg}`;
    if (hasEvent(daily, "signin_x2")) reply += "（丰年庆典翻倍！）";
    if (streakMsg) { reply += `\n${streakMsg}额外获得 ${fmtCoins(streakBonus)}`; }
    if (streakGift) reply += `+ ${streakGift.seed}×${streakGift.count}`;
    reply += `\n当前身家：${fmtCoins(p.coins)}${childMsg}`;
    if (newAchs.length) reply += `\n\n${fmtNewAchievements(newAchs)}`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 随机事件辅助 ──
function rollPlantEvent(fort) {
    const r = Math.random();
    if (r < 0.04) return { tag:"bonanza", text:"翻地时竟挖出一枚古钱！", coins: rand(20, 80) };
    if (r < 0.14) return { tag:"pest",    text:"地里发现些虫迹，可能影响收成。", yieldMod: 0.75 };
    if (r < 0.24) return { tag:"fertile", text:"土地格外肥沃，预计丰收！", yieldMod: 1.3 * fort.cropM };
    return { tag:"normal", text: null, yieldMod: 1.0 };
}

function rollHarvestEvent(fort, daily) {
    let base = 1.0 * fort.cropM;
    if (hasEvent(daily, "crop_up"))   base *= getEvent(daily, "crop_up").val;
    if (hasEvent(daily, "crop_down")) base *= getEvent(daily, "crop_down").val;
    if (daily.festival && daily.festival.harvestBoost) base *= daily.festival.harvestBoost;
    const r = Math.random();
    if (r < 0.03) return { tag:"gift",   yieldMod: base, text:"收获时发现地头有个包袱，里有散碎银两！", coins: rand(30,100) };
    if (r < 0.10) return { tag:"bumper", yieldMod: base * 1.5, text:"天公作美，今日大丰收！" };
    if (r < 0.20) return { tag:"damage", yieldMod: base * 0.8, text:"昨夜风雨，略有损失。" };
    return { tag:"normal", yieldMod: base, text: null };
}

const HERB_ITEMS = new Set(["草药","灵芝","何首乌","野山参","百年山参","天山雪莲","千年灵芝","龙须菜","人参","雪莲","龙骨片"]);

function rollSellMod(fort, daily, itemName) {
    let mod = fort.sellM;
    if (hasEvent(daily, "sell_up")) mod *= getEvent(daily, "sell_up").val;
    if (hasEvent(daily, "tax"))     mod *= getEvent(daily, "tax").val;
    // 神医问诊 & 节日清明/端午：药材涨价
    if (hasEvent(daily, "herb_x2") && HERB_ITEMS.has(itemName)) mod *= 2;
    if (daily.festival && daily.festival.herbBoost && HERB_ITEMS.has(itemName)) mod *= daily.festival.herbBoost;
    return mod;
}

// 上山结果计算（含时段/天气/日事件/加成）
function rollHuntResult(player, bonus, daily) {
    // 冬日封山
    if (hasEvent(daily, "hunt_ban")) return { empty: true, desc: "大雪封山，无功而返。" };

    const h = new Date().getHours();
    let timeMod = { animal:1.0, herb:1.0, rare:1.0, label:"" };
    if      (h >= 5  && h < 9)  timeMod = { animal:1.3, herb:0.7, rare:0.8,  label:"清晨" };
    else if (h >= 17 && h < 21) timeMod = { animal:1.2, herb:1.0, rare:1.3,  label:"傍晚" };
    else if (h >= 21 || h < 5)  timeMod = { animal:0.8, herb:1.2, rare:1.5,  label:"深夜" };

    const weather  = daily.weather;
    const huntMod  = weather.huntMod;
    const herbMod  = weather.herbMod * (daily.festival && daily.festival.herbBoost ? daily.festival.herbBoost * 0.5 + 0.5 : 1);
    const rareMod  = (1 + (bonus.rare || 0)) * (daily.festival && daily.festival.rareBoost ? daily.festival.rareBoost : 1);
    const huntBuff = bonus.hunt || 0;

    // 构建权重表
    const table = HUNT_TABLE.map(h => {
        let w = h.w;
        if (h.type === "empty")  w *= (1 - huntBuff * 0.5) * (hasEvent(daily, "hunt_buff") ? 0.3 : 1);
        if (h.type === "animal") w *= huntMod * timeMod.animal;
        if (h.type === "herb")   w *= huntMod * herbMod * timeMod.herb;
        if (h.type === "rare")   w *= huntMod * rareMod * timeMod.rare;
        return { ...h, w: Math.max(0.01, w) };
    });

    const total = table.reduce((s, h) => s + h.w, 0);
    let r = Math.random() * total;
    let result = table[0];
    for (const h of table) { r -= h.w; if (r <= 0) { result = h; break; } }

    // 山匪事件
    let banditLoss = 0;
    if (hasEvent(daily, "hunt_bandit") && result.type !== "empty" && Math.random() < 0.40) {
        banditLoss = rand(20, 80);
    }

    // 链式事件
    let chain = null;
    if (Math.random() < 0.12) chain = pick(HUNT_CHAINS)();

    return { result, chain, banditLoss, timeMod };
}
// ============================================================
// 人间烟火 v3.0 — 指令处理：种地 / 上山 / 偷菜
// ============================================================

// ── 种地 ──
function doPlant(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus) {
    const cropName = (cmdArgs.getArgN(2) || "").trim();
    if (!cropName) {
        const unlocked = Object.entries(CROPS).filter(([, c]) =>
            p.coins >= c.reqW && (p.fame || 0) >= c.reqF
        );
        const locked = Object.entries(CROPS).filter(([, c]) =>
            p.coins < c.reqW || (p.fame || 0) < c.reqF
        );
        const ul = unlocked.map(([name, c]) => `${name}(${c.h}h)`).join("、");
        const lk = locked.map(([name, c]) =>
            `${name}[需${fmtCoins(c.reqW)}+${FAME[c.reqF].title}]`
        ).join("、");
        let reply = `📋 可种作物：${ul || "（无）"}`;
        if (lk) reply += `\n🔒 未解锁：${lk}`;
        reply += `\n今日天气推荐：${daily.rec.join("、") || "无特别推荐"}`;
        reply += `\n用法：.烟火 种 [作物名]`;
        seal.replyToSender(ctx, msg, reply);
        return;
    }

    const check = canPlantCrop(p, cropName);
    if (!check.ok) { seal.replyToSender(ctx, msg, `不能种【${cropName}】：${check.reason}`); return; }

    const emptyIdx = p.plots.findIndex(pl => pl === null);
    if (emptyIdx === -1) { seal.replyToSender(ctx, msg, "田地全满！先 .烟火 收 腾出空地，或 .烟火 扩地 扩大田园。"); return; }

    const crop = CROPS[cropName];

    // 春耕动员：本日一次免费
    const useFree = hasEvent(daily, "free_plant") && p.freePlantDate !== todayStr();
    if (!useFree) {
        const seeds = p.bag[crop.seed] || 0;
        if (seeds <= 0) {
            seal.replyToSender(ctx, msg, `没有【${crop.seed}】！先去 .烟火 买 ${crop.seed} 5 购入。`);
            return;
        }
        p.bag[crop.seed] = seeds - 1;
        if (!p.bag[crop.seed]) delete p.bag[crop.seed];
    } else {
        p.freePlantDate = todayStr();
    }

    const event = rollPlantEvent(fort);
    const cropMod = 1 + (bonus.crop || 0);
    const readyAt = now() + crop.h * 3600000;
    p.plots[emptyIdx] = {
        crop: cropName, plantedAt: now(), readyAt, notified: false,
        yieldMod: (event.yieldMod || 1.0) * cropMod,
    };
    if (event.coins) p.coins += event.coins;
    // 统计种过的作物（用于成就）
    if (!p.stat) p.stat = {};
    if (!p.stat.cropsPlanted) p.stat.cropsPlanted = {};
    p.stat.cropsPlanted[cropName] = true;
    saveData(data);

    const weatherHint = daily.rec.includes(cropName) ? "☀️ 今日天气适宜此作物，预计增产！" : "";
    let reply = `🌱 第${emptyIdx + 1}块地种下了【${cropName}】`;
    if (useFree) reply += "（春耕动员：本次免消耗种子）";
    reply += `\n⏳ ${fmtMs(crop.h * 3600000)}后成熟，届时会@你提醒！`;
    if (weatherHint) reply += `\n${weatherHint}`;
    if (event.text) reply += `\n✨ ${event.text}`;
    if (event.coins) reply += `（挖出了 ${fmtCoins(event.coins)}）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 收地 ──
function doHarvest(ctx, msg, data, key, p, daily, fort, bonus) {
    const harvested = []; let unready = 0;
    const hEvent = rollHarvestEvent(fort, daily);

    for (let i = 0; i < p.plots.length; i++) {
        const pl = p.plots[i]; if (!pl) continue;
        if (pl.readyAt - now() > 0) { unready++; continue; }
        const cr = CROPS[pl.crop];
        const raw = rand(cr.minY, cr.maxY);
        const count = Math.max(1, Math.round(raw * (pl.yieldMod || 1.0) * hEvent.yieldMod));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + count;
        harvested.push({ name: pl.crop, count });
        p.plots[i] = null;
    }
    if (hEvent.coins) p.coins += hEvent.coins;
    // 统计收获次数（用于成就）
    if (harvested.length > 0) {
        if (!p.stat) p.stat = {};
        p.stat.harvests = (p.stat.harvests || 0) + harvested.length;
    }
    saveData(data);

    if (!harvested.length && !unready) { seal.replyToSender(ctx, msg, "田地是空的，先用 .烟火 种 [作物] 播种！"); return; }
    if (!harvested.length) { seal.replyToSender(ctx, msg, `${unready} 块地还没熟，再等等吧！`); return; }

    const list = harvested.map(h => `【${h.name}】×${h.count}`).join("、");
    const flavor = ["擦了把汗，嘴角不自觉地往上扬。","一筐一筐装进背篓，满满当当。","看着丰收，心里头那点愁也散了。"];
    let reply = `🌾 ${ctx.player.name} 收获：${list}\n${pick(flavor)}`;
    if (hEvent.text) reply += `\n✨ ${hEvent.text}`;
    if (hEvent.coins) reply += `（意外得 ${fmtCoins(hEvent.coins)}）`;
    if (unready) reply += `\n（还有 ${unready} 块未成熟）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 田地状态 ──
function doViewFarm(ctx, msg, p, daily) {
    const lines = p.plots.map((pl, i) => {
        if (!pl) return `第${i + 1}块：【空地】`;
        const left = pl.readyAt - now();
        if (left <= 0) return `第${i + 1}块：【${pl.crop}】✅ 已成熟！`;
        const pct = Math.floor((1 - left / (CROPS[pl.crop].h * 3600000)) * 100);
        const bar = "█".repeat(Math.floor(pct / 10)) + "░".repeat(10 - Math.floor(pct / 10));
        return `第${i + 1}块：【${pl.crop}】[${bar}]${pct}% 剩${fmtMs(left)}`;
    });
    const nextCost = LAND_COSTS[p.plots.length - 2];
    seal.replyToSender(ctx, msg,
        `🌾 ${ctx.player.name} 的田地（${p.plots.length}块）：\n` +
        lines.join("\n") +
        (nextCost ? `\n扩地费：${fmtCoins(nextCost)}（.烟火 扩地）` : "") +
        `\n今日天气推荐：${daily.rec.join("、") || "无特别推荐"}`
    );
}

// ── 扩地 ──
function doExpandFarm(ctx, msg, data, key, p) {
    const max = 2 + LAND_COSTS.length;
    if (p.plots.length >= max) { seal.replyToSender(ctx, msg, `田地已达上限（${max}块）！`); return; }
    const cost = LAND_COSTS[p.plots.length - 2];
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `扩地需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`); return; }
    p.coins -= cost; p.plots.push(null);
    saveData(data);
    seal.replyToSender(ctx, msg, `🏡 扩地成功！花费 ${fmtCoins(cost)}，现有 ${p.plots.length} 块田地。`);
}

// ── 上山 ──
function doHunt(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = seal.ext.getIntConfig(ext, "打猎冷却_分钟") * 60000;
    const cdLeft = (p.huntCd || 0) - now();
    if (cdLeft > 0 && !p.huntBuff) {
        seal.replyToSender(ctx, msg, `精力未复，${fmtMs(cdLeft)} 后才能再上山。`);
        return;
    }
    if (p.huntBuff) p.huntBuff = false; // 消耗buff

    p.huntCd = now() + cdMs;
    if (!p.stat) p.stat = {};
    p.stat.hunts = (p.stat.hunts || 0) + 1;

    const { result, chain, banditLoss, timeMod } = rollHuntResult(p, bonus, daily);

    // 空手
    if (!result.name) {
        if (banditLoss) p.coins = Math.max(0, p.coins - banditLoss);
        // 链式事件效果（空手时也要实际生效）
        if (chain) {
            p.stat.chains = (p.stat.chains || 0) + 1;
            if (chain.item) p.bag[chain.item] = (p.bag[chain.item] || 0) + (chain.count || 1);
            if (chain.coins) p.coins = Math.max(0, p.coins + chain.coins);
        }
        saveData(data);
        seal.replyToSender(ctx, msg,
            `🏔️ ${timeMod.label ? `[${timeMod.label}]` : ""}${ctx.player.name} 上山归来……\n` +
            `${pick(result.desc)}` +
            (banditLoss ? `\n⚔️ 遭遇山匪，损失了 ${fmtCoins(banditLoss)}！` : "") +
            (chain ? `\n\n📖 途中奇遇：\n${chain.text}` +
                (chain.item ? `（获得【${chain.item}】×${chain.count || 1}）` : "") +
                (chain.coins ? `（${chain.coins > 0 ? "+" : ""}${fmtCoins(chain.coins)}）` : "") : "") +
            `\n（${fmtMs(cdMs)} 后可再上山）`
        );
        return;
    }

    const count = rand(result.min, result.max);
    p.bag[result.name] = (p.bag[result.name] || 0) + count;
    if (banditLoss) p.coins = Math.max(0, p.coins - banditLoss);

    // 链式事件道具
    if (chain && chain.item) {
        p.bag[chain.item] = (p.bag[chain.item] || 0) + (chain.count || 1);
    }
    if (chain && chain.coins) {
        p.coins = Math.max(0, p.coins + chain.coins);
    }
    // 统计：链式奇遇 + 稀有发现
    if (chain) p.stat.chains = (p.stat.chains || 0) + 1;
    if (!p.stat.huntFinds) p.stat.huntFinds = [];
    if (!p.stat.huntFinds.includes(result.name)) p.stat.huntFinds.push(result.name);

    saveData(data);
    const estVal = rand(result.minP, result.maxP) * count;
    let reply = `🏔️ ${timeMod.label ? `[${timeMod.label}] ` : ""}${ctx.player.name} 上山归来！\n`;
    reply += `${pick(result.desc)}\n`;
    reply += `获得：【${result.name}】×${count}（约值 ${fmtCoins(estVal)}）`;
    if (banditLoss) reply += `\n⚔️ 遭山匪打劫，损失 ${fmtCoins(banditLoss)}！`;
    if (chain && chain.text) {
        reply += `\n\n📖 途中奇遇：\n${chain.text}`;
        if (chain.item) reply += `（获得【${chain.item}】×${chain.count || 1}）`;
        if (chain.coins) reply += `（${chain.coins > 0 ? "+" : ""}${fmtCoins(chain.coins)}）`;
    }
    reply += `\n（${fmtMs(cdMs)} 后可再上山）`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 偷菜（@目标，公开）──
function doSteal(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = seal.ext.getIntConfig(ext, "偷菜冷却_分钟") * 60000;
    // 贼人入村事件：冷却减半
    const effectiveCd = hasEvent(daily, "steal_chaos") ? cdMs * 0.5 : cdMs;
    const cdLeft = (p.stealCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `上次偷菜风头还没过，${fmtMs(cdLeft)} 后再出手！`);
        return;
    }

    const atList = msg.atUsersId || [];
    if (!atList.length) { seal.replyToSender(ctx, msg, "请@一个目标！用法：.烟火 偷 @某人"); return; }
    if (atList[0] === ctx.player.userId) { seal.replyToSender(ctx, msg, "偷自己的菜？这合理吗？"); return; }

    const gid = ctx.group.groupId;
    const tKey = `${gid}|${atList[0]}`;
    const target = data[tKey];
    if (!target || !target.plots || !target.plots.some(pl => pl)) {
        seal.replyToSender(ctx, msg, "对方田里空空如也，没什么可偷！");
        return;
    }

    p.stealCd = now() + effectiveCd;

    // 成功率 = 55% + 偷菜加成 - 对方防盗加成，运势修正
    const targetBonus = getAllBonuses(target, gid);
    const rate = Math.min(0.90, Math.max(0.10,
        (0.55 + (bonus.steal || 0) - (targetBonus.anti || 0)) * fort.stealM
    ));

    const success = Math.random() <= rate;
    const filledIdxArr = target.plots.map((pl, i) => pl ? i : -1).filter(i => i >= 0);

    if (success && filledIdxArr.length) {
        const si = pick(filledIdxArr);
        const pl = target.plots[si];
        const cr = CROPS[pl.crop];
        const stolen = Math.max(1, Math.floor(rand(cr.minY, cr.maxY) * 0.4));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + stolen;
        if (!p.stat) p.stat = {};
        p.stat.steals = (p.stat.steals || 0) + 1;
        target.wasStolen = true; // 被偷成就标记
        saveData(data);

        const ok = ["月黑风高，手脚麻利摘了几个就跑！","趁主人不在，飞快摘了几颗揣进怀里！","动作轻柔，连露水都没惊动——"];
        seal.replyToSender(ctx, msg, `🌙 ${pick(ok)}\n偷到：【${pl.crop}】×${stolen}（冷却 ${fmtMs(effectiveCd)}）`);
        sendGroupMsg(target, `${atUser(target.userId)} 你的【${pl.crop}】被 ${ctx.player.name} 偷走了 ${stolen} 个！快 .烟火 收 防止损失！`);
    } else {
        saveData(data);
        const fail = ["脚下一滑，踩断树枝，邻居的狗叫了起来，狼狈逃窜！","正要下手，猛地想起这家主人会武功，腿一软跑了！","手还没伸过去，就被路过老伯盯住了。"];
        seal.replyToSender(ctx, msg, `😅 ${pick(fail)}\n（冷却 ${fmtMs(effectiveCd)}）`);
        sendGroupMsg(target, `${atUser(target.userId)} ${ctx.player.name} 刚才想偷你的菜，没得手——不过要注意！`);
    }
}

// ── 夜袭（随机匿名偷菜）──
function doNightRaid(ctx, msg, data, key, p, daily, fort, bonus) {
    const cdMs = 1800000; // 30分钟固定
    const effectiveCd = hasEvent(daily, "steal_chaos") ? cdMs * 0.5 : cdMs;
    const cdLeft = (p.nightRaidCd || 0) - now();
    if (cdLeft > 0) {
        seal.replyToSender(ctx, msg, `刚才的风声还没散，${fmtMs(cdLeft)} 后再行动！`);
        return;
    }

    const gid = ctx.group.groupId;
    // 找群内有庄稼的其他玩家
    const victims = Object.entries(data).filter(([k, v]) => {
        if (!k.startsWith(gid + "|") || k === key) return false;
        return v.plots && v.plots.some(pl => pl !== null);
    }).map(([, v]) => v);

    if (!victims.length) {
        seal.replyToSender(ctx, msg, "🌙 夜色中四处张望……村里暂时没有可偷的庄稼。");
        return;
    }

    p.nightRaidCd = now() + effectiveCd;
    const target = pick(victims);
    const filledIdxArr = target.plots.map((pl, i) => pl ? i : -1).filter(i => i >= 0);

    // 成功率（匿名，基础略低）
    const targetBonus = getAllBonuses(target, gid);
    const rate = Math.min(0.80, Math.max(0.10,
        (0.48 + (bonus.steal || 0) - (targetBonus.anti || 0)) * fort.stealM
    ));
    const success = Math.random() <= rate;

    if (success) {
        const si = pick(filledIdxArr);
        const pl = target.plots[si];
        const cr = CROPS[pl.crop];
        const stolen = Math.max(1, Math.floor(rand(cr.minY, cr.maxY) * 0.35));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + stolen;
        if (!p.stat) p.stat = {};
        p.stat.steals = (p.stat.steals || 0) + 1;
        target.wasStolen = true;
        saveData(data);
        const ok = [
            "趁着月色，悄悄潜入……无声无息地摘走了几颗。",
            "夜幕掩护之下，手脚轻巧，对方浑然不知。",
            "月上柳梢头，人定了，这才出手——干净利落。",
        ];
        seal.replyToSender(ctx, msg,
            `🌙 ${pick(ok)}\n偷到：【${pl.crop}】×${stolen}，对方不知道是谁干的。\n（冷却 ${fmtMs(effectiveCd)}）`
        );
        // 匿名通知——只说有贼，不说是谁
        sendGroupMsg(target, `${atUser(target.userId)} 夜里有人偷了你的【${pl.crop}】${stolen}个！小心门户！`);
    } else {
        saveData(data);
        const fail = [
            "脚踩到了一块空罐子，「铛」的一声，赶紧跑路！",
            "刚翻过篱笆，里面的狗突然叫了起来——落荒而逃。",
            "黑暗中一脚踩空，摔了个跟头，什么没拿到就跑了。",
        ];
        seal.replyToSender(ctx, msg,
            `😅 ${pick(fail)}\n（冷却 ${fmtMs(effectiveCd)}）`
        );
        // 不通知对方（失败了，对方不知道）
    }
}
// ============================================================
// 人间烟火 v3.0 — 指令处理：集市 / 科举 / 铺子 / 佳人
// ============================================================

// ── 集市 ──
function doMarket(ctx, msg, p, daily) {
    // 只显示玩家已解锁的种子
    const unlockedSeeds = Object.entries(CROPS)
        .filter(([, c]) => p.coins >= c.reqW && (p.fame || 0) >= c.reqF)
        .map(([name, c]) => {
            const disc = hasEvent(daily, "seed_disc") ? Math.round(c.cost * getEvent(daily, "seed_disc").val) : c.cost;
            const discStr = disc !== c.cost ? `~~${fmtCoins(c.cost)}~~ → ${fmtCoins(disc)}` : fmtCoins(c.cost);
            return `  ${c.seed} ${discStr}/个 → 种${name}（${c.h}h，售${fmtCoins(c.minP)}~${fmtCoins(c.maxP)}）`;
        });

    const huntLines = HUNT_TABLE.filter(h => h.name).map(h =>
        `  ${h.name}：${fmtCoins(h.minP)}~${fmtCoins(h.maxP)}/个`
    );

    const specialLines = Object.entries(SPECIAL_ITEMS).map(([name, s]) =>
        `  ${name}：${fmtCoins(s.minP)}~${fmtCoins(s.maxP)}/个`
    );

    // 节日道具（当日有节日时才展示）
    const festLines = daily.festival
        ? Object.entries(FESTIVAL_ITEMS).map(([name, s]) =>
            `  ${name}：${fmtCoins(s.minP)}~${fmtCoins(s.maxP)}/个`)
        : [];

    const evtStr = daily.events.length
        ? daily.events.map(e => `${e.emoji}${e.name}`).join(" | ")
        : "（今日无特殊事件）";

    const festHeader = daily.festival
        ? `\n━━【节日道具·${daily.festival.emoji}${daily.festival.name}】━━\n${festLines.join("\n")}`
        : "";

    seal.replyToSender(ctx, msg,
        `🏪 今日集市（物价浮动）\n今日事件：${evtStr}\n` +
        `━━【种子】━━\n${unlockedSeeds.join("\n") || "  （暂无可购种子）"}\n` +
        `━━【收购·山货】━━\n${huntLines.join("\n")}\n` +
        `━━【收购·特殊】━━\n${specialLines.join("\n")}${festHeader}\n` +
        `.烟火 买 [种子] [数量] | .烟火 卖 [物品] [数量/全部]`
    );
}

// ── 购买种子 ──
function doBuy(ctx, msg, cmdArgs, data, key, p, daily) {
    const itemName = (cmdArgs.getArgN(2) || "").trim();
    const countArg = (cmdArgs.getArgN(3) || "1").trim();
    if (!itemName) {
        const list = Object.entries(CROPS)
            .filter(([, c]) => p.coins >= c.reqW && (p.fame || 0) >= c.reqF)
            .map(([, c]) => c.seed).join("、");
        seal.replyToSender(ctx, msg, `已解锁种子：${list || "（无）"}\n用法：.烟火 买 菜种 5`);
        return;
    }
    const cropName = SEED_MAP[itemName];
    if (!cropName) { seal.replyToSender(ctx, msg, `"${itemName}"不是种子！`); return; }
    const check = canPlantCrop(p, cropName);
    if (!check.ok) { seal.replyToSender(ctx, msg, `种子未解锁：${check.reason}`); return; }

    const count = Math.max(1, parseInt(countArg) || 1);
    const crop = CROPS[cropName];
    const disc = hasEvent(daily, "seed_disc") ? getEvent(daily, "seed_disc").val : 1;
    const unitCost = Math.round(crop.cost * disc);
    const total = unitCost * count;
    if (p.coins < total) { seal.replyToSender(ctx, msg, `需要 ${fmtCoins(total)}，持有 ${fmtCoins(p.coins)}，差 ${fmtCoins(total - p.coins)}`); return; }

    p.coins -= total;
    p.bag[itemName] = (p.bag[itemName] || 0) + count;
    saveData(data);
    const discHint = disc < 1 ? "（大集打折！）" : "";
    seal.replyToSender(ctx, msg, `🛒 买入 ${itemName}×${count}，花费 ${fmtCoins(total)}${discHint}，剩余 ${fmtCoins(p.coins)}`);
}

// ── 出售 ──
function doSell(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus) {
    const itemName = (cmdArgs.getArgN(2) || "").trim();
    const countArg = (cmdArgs.getArgN(3) || "").trim();
    if (!itemName) { seal.replyToSender(ctx, msg, "用法：.烟火 卖 [物品] [数量/全部]\n先用 .烟火 背包 查看持有物品。"); return; }

    const have = p.bag[itemName] || 0;
    if (!have) { seal.replyToSender(ctx, msg, `背包里没有【${itemName}】！`); return; }
    const sellCount = countArg === "全部" ? have : Math.min(parseInt(countArg) || 1, have);
    if (sellCount <= 0) { seal.replyToSender(ctx, msg, "数量有误！"); return; }

    // 查单价
    let unitPrice = 0;
    const cr = CROPS[itemName];
    if (cr) unitPrice = rand(cr.minP, cr.maxP);
    else {
        const ht = HUNT_TABLE.find(h => h.name === itemName);
        if (ht) unitPrice = rand(ht.minP, ht.maxP);
        else if (SPECIAL_ITEMS[itemName])   unitPrice = rand(SPECIAL_ITEMS[itemName].minP,   SPECIAL_ITEMS[itemName].maxP);
        else if (FESTIVAL_ITEMS[itemName])  unitPrice = rand(FESTIVAL_ITEMS[itemName].minP,  FESTIVAL_ITEMS[itemName].maxP);
    }
    if (!unitPrice) { seal.replyToSender(ctx, msg, `【${itemName}】无法在集市出售！`); return; }

    const sellMod = rollSellMod(fort, daily, itemName) * (1 + (bonus.sell || 0));
    const finalUnit = Math.round(unitPrice * sellMod);
    const total = finalUnit * sellCount;
    const coinsBefore = p.coins;

    p.bag[itemName] = have - sellCount;
    if (!p.bag[itemName]) delete p.bag[itemName];
    p.coins += total;

    const idBefore = getIdentity(coinsBefore);
    const idAfter  = getIdentity(p.coins);
    saveData(data);

    let reply = `💰 【${itemName}】×${sellCount}，今日单价 ${fmtCoins(finalUnit)}，共得 ${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}`;
    if (idAfter.name !== idBefore.name) {
        reply += `\n\n🎉 身份晋升为【${idAfter.name}】！`;
        const ni = IDENTITIES[IDENTITIES.indexOf(idAfter) + 1];
        if (ni) reply += `\n距【${ni.name}】还差 ${fmtCoins(ni.threshold - p.coins)}`;
    }
    seal.replyToSender(ctx, msg, reply);
}

// ── 科举 ──
function doExam(ctx, msg, data, key, p, fort, bonus) {
    const fame = p.fame || 0;
    if (fame >= FAME.length - 1) { seal.replyToSender(ctx, msg, "已是【状元】，科举之路已至极峰！"); return; }
    const lv = FAME[fame];
    const cdLeft = (p.examCd || 0) - now();
    if (cdLeft > 0) { seal.replyToSender(ctx, msg, `上次考试后还需休整，${fmtMs(cdLeft)} 后再考！`); return; }
    if (p.coins < lv.examCost) { seal.replyToSender(ctx, msg, `参考需盘缠 ${fmtCoins(lv.examCost)}，还差 ${fmtCoins(lv.examCost - p.coins)}！`); return; }

    p.coins -= lv.examCost;
    p.examCd = now() + lv.cdH * 3600000;
    const rate = Math.min(0.95, lv.examRate + (bonus.exam || 0));
    const success = Math.random() <= rate;

    if (success) {
        p.fame = fame + 1;
        saveData(data);
        const nextTitle = FAME[fame + 1].title;
        const f = ["金榜题名，鞭炮声中，邻里皆来道贺！","看榜时心如擂鼓，找到自己名字，泪水不争气地流了下来。","先生说：十年寒窗苦，今日终有报。"];
        let reply = `📜【科举揭榜】金榜有名！\n${ctx.player.name} 一举高中【${nextTitle}】！\n${pick(f)}`;
        // 解锁提示
        const su = Object.entries(SHOPS).find(([, s]) => s.req === p.fame);
        if (su) reply += `\n🎊 已解锁铺子：【${su[0]}】（.烟火 开铺 ${su[0]}）`;
        // 解锁作物提示
        const newCrops = Object.keys(CROPS).filter(c => CROPS[c].reqF === p.fame);
        if (newCrops.length) reply += `\n🌱 已解锁新作物：${newCrops.join("、")}（还需达到对应财富）`;
        seal.replyToSender(ctx, msg, reply);
    } else {
        saveData(data);
        const f = ["答到一半手心发抖，出了考场才知道写错了。","文章洋洋洒洒，偏偏偏了题意，名落孙山。","主考官看了半天，摇头，落笔打了个叉。"];
        seal.replyToSender(ctx, msg, `📜【科举揭榜】榜上无名。\n${pick(f)}\n花费盘缠 ${fmtCoins(lv.examCost)}，${fmtMs(lv.cdH * 3600000)} 后可再考。`);
    }
}

// ── 开铺 ──
function doOpenShop(ctx, msg, cmdArgs, data, key, p) {
    const shopName = (cmdArgs.getArgN(2) || "").trim();
    if (!shopName) {
        const list = Object.entries(SHOPS).map(([n, s]) =>
            `  ${n}：需${FAME[s.req].title}+${fmtCoins(s.cost)}，每${seal.ext.getIntConfig(ext,"收租间隔_小时")}h收${fmtCoins(s.minI)}~${fmtCoins(s.maxI)}`
        );
        seal.replyToSender(ctx, msg, `可开铺子：\n${list.join("\n")}\n用法：.烟火 开铺 小铺子`);
        return;
    }
    const shop = SHOPS[shopName];
    if (!shop) { seal.replyToSender(ctx, msg, `不认识"${shopName}"，可开：${Object.keys(SHOPS).join("、")}`); return; }
    if ((p.fame || 0) < shop.req) { seal.replyToSender(ctx, msg, `开${shopName}需【${FAME[shop.req].title}】以上，当前【${FAME[p.fame || 0].title}】！`); return; }
    if (!p.shops) p.shops = {};
    if ((p.shops[shopName] || 0) >= 3) { seal.replyToSender(ctx, msg, `${shopName}最多开3家！`); return; }
    if (p.coins < shop.cost) { seal.replyToSender(ctx, msg, `开${shopName}需 ${fmtCoins(shop.cost)}，还差 ${fmtCoins(shop.cost - p.coins)}！`); return; }
    p.coins -= shop.cost;
    p.shops[shopName] = (p.shops[shopName] || 0) + 1;
    saveData(data);
    seal.replyToSender(ctx, msg, `🏪 ${shopName}开张大吉！花费 ${fmtCoins(shop.cost)}，现有 ${p.shops[shopName]} 家。每${seal.ext.getIntConfig(ext,"收租间隔_小时")}h可 .烟火 收租！`);
}

// ── 查看铺子 ──
function doViewShops(ctx, msg, p) {
    const owned = Object.entries(p.shops || {}).filter(([, v]) => v > 0);
    if (!owned.length) { seal.replyToSender(ctx, msg, "还没有铺子！先 .烟火 科举 获取功名再 .烟火 开铺。"); return; }
    const itvH = seal.ext.getIntConfig(ext, "收租间隔_小时");
    const cdLeft = (p.shopCd || 0) - now();
    const lines = owned.map(([n, c]) => { const s = SHOPS[n]; return `  ${n}×${c}，每次 ${fmtCoins(s.minI * c)}~${fmtCoins(s.maxI * c)}`; });
    seal.replyToSender(ctx, msg,
        `🏪 ${ctx.player.name} 的铺子：\n${lines.join("\n")}\n` +
        `下次收租：${cdLeft > 0 ? fmtMs(cdLeft) + "后" : "现在可收（.烟火 收租）"}`
    );
}

// ── 收租 ──
function doCollectRent(ctx, msg, data, key, p, bonus) {
    const owned = Object.entries(p.shops || {}).filter(([, v]) => v > 0);
    if (!owned.length) { seal.replyToSender(ctx, msg, "没有铺子！先 .烟火 开铺 开设。"); return; }
    const itvMs = seal.ext.getIntConfig(ext, "收租间隔_小时") * 3600000;
    const cdLeft = (p.shopCd || 0) - now();
    if (cdLeft > 0) { seal.replyToSender(ctx, msg, `账房说账还没结好，${fmtMs(cdLeft)} 后再来！`); return; }
    const shopBonus = 1 + (bonus.shop || 0);
    let total = 0; const details = [];
    for (const [n, c] of owned) {
        const s = SHOPS[n];
        const inc = Math.round(rand(s.minI, s.maxI) * c * shopBonus);
        total += inc; details.push(`${n}×${c}：${fmtCoins(inc)}`);
    }
    p.coins += total; p.shopCd = now() + itvMs;
    saveData(data);
    seal.replyToSender(ctx, msg, `💼 账房送来了账册——\n${details.join("\n")}\n合计入账：${fmtCoins(total)}\n当前身家：${fmtCoins(p.coins)}\n下次收租：${fmtMs(itvMs)} 后`);
}

// ── 花名册 ──
function doCharList(ctx, msg, cmdArgs, p, gid) {
    const ad = getAttrInit(gid);
    const filter = (cmdArgs.getArgN(2) || "").trim();
    let chars = CHARS.map(([name, price, gender, desc, bt, bv]) => ({
        name, price, gender, desc, bt, bv, ...ad[name]
    }));
    if (filter === "男") chars = chars.filter(c => c.gender === "m");
    else if (filter === "女") chars = chars.filter(c => c.gender === "f");
    else if (filter === "空闲") chars = chars.filter(c => !c.owner);
    else if (filter === "我的") chars = chars.filter(c => c.owner === ctx.player.userId);

    const pageSize = 10;
    const pageNum  = parseInt(filter) || 1;
    const total    = Math.ceil(chars.length / pageSize);
    const page     = isNaN(parseInt(filter)) ? 1 : Math.max(1, Math.min(pageNum, total));
    const paged    = chars.slice((page - 1) * pageSize, page * pageSize);

    const lines = paged.map(c => {
        const bn = c.bt ? `[${BONUS_DESC[c.bt]}${Math.round(c.bv * 100)}%]` : "";
        const own = c.owner
            ? `（归 ${c.ownerName}${c.married ? "·已婚" : ""}，出价 ${fmtCoins(Math.ceil(c.price * (c.married ? 3 : 1.5)))} 争抢）`
            : `（无主，${fmtCoins(c.price)}）`;
        return `【${c.name}】${bn}${own}`;
    });
    seal.replyToSender(ctx, msg,
        `💐 花名册（${page}/${total}页，共50人）\n筛选：男/女/空闲/我的/页码\n━━━━━━\n${lines.join("\n")}\n━━━━━━\n追求：.烟火 追求 [姓名] | 详情：.烟火 佳人 [姓名]`
    );
}

// ── 佳人详情 ──
function doCharDetail(ctx, msg, cmdArgs, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) {
        const ad = getAttrInit(gid);
        const mine = CHARS.filter(([n]) => ad[n] && ad[n].owner === ctx.player.userId);
        if (!mine.length) { seal.replyToSender(ctx, msg, "你还没有佳人，用 .烟火 追求 [姓名] 去追！"); return; }
        const lines = mine.map(([n,,,,bt,bv]) => {
            const c = ad[n];
            const bn = bt ? `  加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "";
            return `【${n}】身价 ${fmtCoins(c.price)}${c.married ? " ·已婚" : ""}${bn}`;
        });
        seal.replyToSender(ctx, msg, `${ctx.player.name} 的佳人们：\n${lines.join("\n")}`);
        return;
    }
    const entry = CHARS.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"！`); return; }
    const ad = getAttrInit(gid);
    const [, baseP, gender, desc, bt, bv] = entry;
    const c = ad[name] || { owner: null, ownerName: null, price: baseP, married: false };
    const statusLine = c.owner
        ? `归属：${c.ownerName}${c.married ? "（已婚）" : ""}，出价 ${fmtCoins(Math.ceil(c.price * (c.married ? 3 : 1.5)))} 可争抢`
        : `尚无归属，只需 ${fmtCoins(c.price)} 即可追求`;
    const bLine = bt ? `\n🌟 被动加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "";
    seal.replyToSender(ctx, msg,
        `💌 【${name}】（${gender === "m" ? "美男" : "美女"}）\n${desc}${bLine}\n━━━━\n${statusLine}\n\n用 .烟火 迎娶 ${name} 可正式成婚（需先追求到ta）`
    );
}

// ── 追求 ──
function doPursue(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 追求 [姓名]"); return; }
    const entry = CHARS.find(([n]) => n === name);
    if (!entry) { seal.replyToSender(ctx, msg, `花名册里没有"${name}"！`); return; }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (c.owner === ctx.player.userId) { seal.replyToSender(ctx, msg, `${name} 早已在你身边，何必再追？`); return; }

    const factor = c.married ? 3 : 1.5;
    const festData = getDailyData(gid).festival || {};
    const festDisc = festData.charDisc || 1;
    const cost = Math.floor((c.owner ? Math.ceil(c.price * factor) : c.price) * festDisc);
    const festHint = festDisc < 1 ? `（${festData.emoji || ""}${festData.name}折扣！原价${fmtCoins(Math.ceil((c.owner ? c.price * factor : c.price)))}）` : "";
    if (p.coins < cost) {
        seal.replyToSender(ctx, msg,
            c.owner
                ? `争抢【${name}】需出价 ${fmtCoins(cost)}（已婚价×${factor}），还差 ${fmtCoins(cost - p.coins)}！`
                : `追求【${name}】需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`
        );
        return;
    }

    p.coins -= cost;
    if (c.owner) {
        // 被争抢：原主人退款+10%
        const prevKey = `${gid}|${c.owner}`;
        const prev = data[prevKey];
        const refund = Math.floor(c.price * 1.1);
        if (prev) {
            // 如果是婚配关系，解除
            if (prev.spouse && prev.spouse.type === "npc" && prev.spouse.id === name) {
                prev.spouse = null;
            }
            prev.coins += refund;
        }
        const prevName = c.ownerName;
        c.owner = ctx.player.userId; c.ownerName = ctx.player.name;
        c.price = cost; c.married = false; // 争夺后婚姻关系解除
        saveData(data); saveAttr(gid, ad);
        seal.replyToSender(ctx, msg, `💘 ${ctx.player.name} 以 ${fmtCoins(cost)}${festHint} 将【${name}】从 ${prevName} 身边带走了！\n（${prevName} 获退款 ${fmtCoins(refund)}）`);
        if (prev) sendGroupMsg(prev, `${atUser(prev.userId)} 【${name}】被 ${ctx.player.name} 以 ${fmtCoins(cost)} 争走了！退款 ${fmtCoins(refund)}。`);
    } else {
        c.owner = ctx.player.userId; c.ownerName = ctx.player.name; c.price = cost;
        saveData(data); saveAttr(gid, ad);
        const f = ["鸿雁传书，情意已通，缘分自此而始。","心悦之人终归己，此后相伴左右。","一见倾心，万两黄金也值得。"];
        const [,,,,bt,bv] = entry;
        seal.replyToSender(ctx, msg,
            `💕 ${ctx.player.name} 以 ${fmtCoins(cost)}${festHint} 追到了【${name}】！\n${pick(f)}\n${entry[3]}` +
            (bt ? `\n🌟 被动加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%` : "") +
            `\n\n可用 .烟火 迎娶 ${name} 正式成婚！`
        );
    }
}

// ── 放手 ──
function doRelease(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 放手 [姓名]"); return; }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (!c || c.owner !== ctx.player.userId) { seal.replyToSender(ctx, msg, `【${name}】不在你身边。`); return; }
    const refund = Math.floor(c.price * 0.5);
    p.coins += refund;
    if (p.spouse && p.spouse.type === "npc" && p.spouse.id === name) p.spouse = null;
    const origEntry = CHARS.find(([n]) => n === name);
    c.owner = null; c.ownerName = null; c.price = origEntry ? origEntry[1] : c.price; c.married = false;
    saveData(data); saveAttr(gid, ad);
    seal.replyToSender(ctx, msg, `【${name}】已放手，重回自由身。退还 ${fmtCoins(refund)}，身价恢复初始。`);
}
// ============================================================
// 人间烟火 v3.0 — 指令处理：婚姻 / 子嗣
// ============================================================

// ── 迎娶佳人（NPC婚姻）──
function doMarryNPC(ctx, msg, cmdArgs, data, key, p, gid) {
    const name = (cmdArgs.getArgN(2) || "").trim();
    if (!name) { seal.replyToSender(ctx, msg, "用法：.烟火 迎娶 [佳人姓名]"); return; }
    if (p.spouse) {
        seal.replyToSender(ctx, msg, `你已与【${p.spouse.name}】成婚，无法再娶/嫁。若要改变，请先 .烟火 离婚。`);
        return;
    }
    const ad = getAttrInit(gid);
    const c = ad[name];
    if (!c || c.owner !== ctx.player.userId) {
        seal.replyToSender(ctx, msg, `你还没有追求到【${name}】！先用 .烟火 追求 ${name}。`);
        return;
    }
    if (c.married) { seal.replyToSender(ctx, msg, `【${name}】已是你的配偶！`); return; }

    const cost = 1000; // 婚礼费用
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `办婚礼需要 ${fmtCoins(cost)} 盘缠，还差 ${fmtCoins(cost - p.coins)}！`); return; }

    p.coins -= cost;
    p.spouse = { type: "npc", id: name, name };
    c.married = true;
    saveData(data); saveAttr(gid, ad);

    const entry = CHARS.find(([n]) => n === name);
    const [,,gender,,bt,bv] = entry || [];
    const gStr = gender === "m" ? "他" : "她";
    const f = [
        `红烛高照，宾客盈门，${name}${gStr}今日盛装而来，眼中含笑。`,
        `拜了天地，入了洞房，此后便是一家人了。`,
        `婚书一签，便是一生。愿此后风雨同路，岁月静好。`,
    ];
    let reply = `🎊 ${ctx.player.name} 与【${name}】正式成婚！\n${pick(f)}\n花费婚礼盘缠：${fmtCoins(cost)}`;
    if (bt) reply += `\n\n💑 配偶加成：${BONUS_DESC[bt]}${Math.round(bv * 100)}%（已包含在佳人加成中）`;
    reply += `\n\n婚后每日签到有概率迎来新成员，用 .烟火 孩子 查看子嗣！`;
    seal.replyToSender(ctx, msg, reply);
}

// ── 向玩家求婚 ──
function doProposePlayer(ctx, msg, cmdArgs, data, key, p, gid) {
    if (p.spouse) {
        seal.replyToSender(ctx, msg, `你已与【${p.spouse.name}】成婚，无法再求婚。若要改变，请先 .烟火 离婚。`);
        return;
    }
    const atList = msg.atUsersId || [];
    if (!atList.length) { seal.replyToSender(ctx, msg, "用法：.烟火 求婚 @目标"); return; }
    if (atList[0] === ctx.player.userId) { seal.replyToSender(ctx, msg, "不能向自己求婚！"); return; }

    const tKey = `${gid}|${atList[0]}`;
    const target = data[tKey];
    if (!target) { seal.replyToSender(ctx, msg, "对方还没立业！"); return; }
    if (target.spouse) { seal.replyToSender(ctx, msg, "对方已成婚，不可打扰！"); return; }

    // 存储求婚请求到目标玩家
    target.proposeFrom = { id: ctx.player.userId, name: p.fullName || ctx.player.name, expire: now() + 86400000 };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `💍 ${p.fullName || ctx.player.name} 向 ${target.fullName || target.userName} 送去了婚帖！\n` +
        `对方可在24小时内用 .烟火 答应 或 .烟火 拒绝 来回应。`
    );
    sendGroupMsg(target, `${atUser(target.userId)} 💍 ${p.fullName || ctx.player.name} 向你求婚了！\n用 .烟火 答应 接受，或 .烟火 拒绝 婉拒。（24小时内有效）`);
}

// ── 答应求婚 ──
function doAccept(ctx, msg, data, key, p, gid) {
    if (p.spouse) { seal.replyToSender(ctx, msg, "你已成婚，无法再答应求婚。"); return; }
    const prop = p.proposeFrom;
    if (!prop || prop.expire < now()) { seal.replyToSender(ctx, msg, "没有待回应的婚帖，或已过期。"); return; }

    const sKey = `${gid}|${prop.id}`;
    const suitor = data[sKey];
    if (!suitor) { seal.replyToSender(ctx, msg, "求婚者已不在此处。"); return; }
    if (suitor.spouse) { seal.replyToSender(ctx, msg, "对方已另有婚配，婚帖作废。"); p.proposeFrom = null; saveData(data); return; }

    // 双方成婚
    p.spouse = { type: "player", id: prop.id, name: prop.name };
    suitor.spouse = { type: "player", id: ctx.player.userId, name: p.fullName || ctx.player.name };
    p.proposeFrom = null;
    saveData(data);

    const f = ["红烛高照，宾客盈门，此后便是一家人了。","拜了天地，入了洞房，愿此后风雨同路。","婚书一签，便是一生，岁月静好。"];
    seal.replyToSender(ctx, msg,
        `🎊 ${p.fullName || ctx.player.name} 与 ${prop.name} 正式成婚！\n${pick(f)}\n\n婚后每日签到有概率迎来子嗣！\n配偶可每天互相用 .烟火 帮忙 帮对方收一块地。`
    );
    sendGroupMsg(suitor, `${atUser(suitor.userId)} 🎊 ${p.fullName || ctx.player.name} 答应了你的求婚！你们成婚了！`);
}

// ── 拒绝求婚 ──
function doReject(ctx, msg, data, key, p) {
    if (!p.proposeFrom || p.proposeFrom.expire < now()) {
        seal.replyToSender(ctx, msg, "没有待回应的婚帖。");
        return;
    }
    const name = p.proposeFrom.name;
    p.proposeFrom = null;
    saveData(data);
    seal.replyToSender(ctx, msg, `已婉拒了 ${name} 的婚帖。`);
}

// ── 离婚 ──
function doDivorce(ctx, msg, data, key, p, gid) {
    if (!p.spouse) { seal.replyToSender(ctx, msg, "你尚未成婚。"); return; }
    const spouse = p.spouse;
    // 离婚代价：损失10%财富
    const penalty = Math.floor(p.coins * 0.1);
    p.coins = Math.max(0, p.coins - penalty);

    // 若配偶是玩家，通知并解除
    if (spouse.type === "player") {
        const sKey = `${gid}|${spouse.id}`;
        const s = data[sKey];
        if (s) { s.spouse = null; }
    } else {
        // NPC婚姻：佳人重回可争抢状态
        const ad = getAttrInit(gid);
        if (ad[spouse.id]) { ad[spouse.id].married = false; saveAttr(gid, ad); }
    }

    p.spouse = null;
    saveData(data);

    seal.replyToSender(ctx, msg,
        `💔 ${ctx.player.name} 与 ${spouse.name} 和离。\n` +
        `离婚代价：损失 ${fmtCoins(penalty)}（财富的10%）。\n` +
        `当前身家：${fmtCoins(p.coins)}`
    );
    if (spouse.type === "player") {
        const sKey = `${gid}|${spouse.id}`;
        const s = data[sKey];
        if (s) sendGroupMsg(s, `${atUser(s.userId)} ${ctx.player.name} 提出和离，你们已解除婚约。`);
    }
}

// ── 配偶帮忙（帮助收地，每天1次）──
function doSpouseHelp(ctx, msg, cmdArgs, data, key, p, gid) {
    if (!p.spouse || p.spouse.type !== "player") {
        seal.replyToSender(ctx, msg, "只有与玩家成婚才能互相帮忙！");
        return;
    }
    const today = todayStr();
    if (p.helpDate === today) { seal.replyToSender(ctx, msg, "今天已经帮忙过了，明天再来！"); return; }

    // 帮哪方？看@目标，默认帮配偶
    const atList = msg.atUsersId || [];
    const targetId = atList.length ? atList[0] : p.spouse.id;
    if (targetId !== p.spouse.id) { seal.replyToSender(ctx, msg, "只能帮配偶！"); return; }

    const tKey = `${gid}|${targetId}`;
    const target = data[tKey];
    if (!target || !target.spouse || target.spouse.id !== ctx.player.userId) {
        seal.replyToSender(ctx, msg, "对方婚姻状态有变，无法帮忙。");
        return;
    }

    // 帮助收取一块成熟的地
    const readyIdx = target.plots.findIndex(pl => pl && pl.readyAt <= now());
    if (readyIdx === -1) { seal.replyToSender(ctx, msg, `${target.fullName || target.userName} 暂时没有成熟的庄稼。`); return; }

    const pl = target.plots[readyIdx];
    const cr = CROPS[pl.crop];
    const count = Math.max(1, rand(cr.minY, cr.maxY));
    target.bag[pl.crop] = (target.bag[pl.crop] || 0) + count;
    target.plots[readyIdx] = null;
    p.helpDate = today;
    saveData(data);

    seal.replyToSender(ctx, msg, `💑 帮配偶收获了【${pl.crop}】×${count}！`);
    sendGroupMsg(target, `${atUser(target.userId)} 你的配偶 ${p.fullName || ctx.player.name} 帮你收了【${pl.crop}】×${count}！`);
}

// ── 查看子嗣 ──
function doViewChildren(ctx, msg, p) {
    const children = p.children || [];
    if (!children.length) {
        const hint = p.spouse ? "每日签到有机会迎来新生儿！" : "先成婚（.烟火 求婚/@目标 或 .烟火 迎娶 佳人名）才能有孩子！";
        seal.replyToSender(ctx, msg, `${ctx.player.name} 膝下尚无子女。\n${hint}`);
        return;
    }
    const lines = children.map(child => {
        const st = childStage(child.bornAt);
        const taskReady = child.lastTaskAt < now() - 43200000; // 12h冷却
        let line = `${st.emoji}【${child.name}】${st.name}（已出生${Math.floor(st.days)}天）`;
        if (st.canEdu) line += `  学识:${child.eduLevel || 0}/10`;
        if (st.canTask) line += `  ${taskReady ? "✅可差遣" : "⏳差遣冷却中"}`;
        return line;
    });
    const maxChildren = 3;
    seal.replyToSender(ctx, msg,
        `👨‍👩‍👧 ${ctx.player.name} 的子嗣（${children.length}/${maxChildren}）：\n${lines.join("\n")}\n` +
        `\n.烟火 教导 [孩子名]  /  .烟火 差遣 [孩子名] [收地/上山/经商]`
    );
}

// ── 教导孩子 ──
function doTeachChild(ctx, msg, cmdArgs, data, key, p) {
    const cname = (cmdArgs.getArgN(2) || "").trim();
    if (!cname) { seal.replyToSender(ctx, msg, "用法：.烟火 教导 [孩子名]"); return; }
    const child = (p.children || []).find(c => c.name === cname);
    if (!child) { seal.replyToSender(ctx, msg, `找不到孩子"${cname}"！用 .烟火 孩子 查看。`); return; }
    const st = childStage(child.bornAt);
    if (!st.canEdu) { seal.replyToSender(ctx, msg, `${child.name}还是婴儿，等长大一点再教导！`); return; }
    if ((child.eduLevel || 0) >= 10) { seal.replyToSender(ctx, msg, `${child.name}的学识已满！`); return; }

    const cost = 50 * ((child.eduLevel || 0) + 1);
    if (p.coins < cost) { seal.replyToSender(ctx, msg, `教导 ${child.name} 需 ${fmtCoins(cost)}，还差 ${fmtCoins(cost - p.coins)}！`); return; }

    p.coins -= cost;
    child.eduLevel = (child.eduLevel || 0) + 1;
    saveData(data);

    const f = [
        "手把手教导，孩子认真地点头，眼里闪着光。",
        "给他讲了一下午的道理，似懂非懂，但终究有所得。",
        "不知不觉天色暗了，回过神来，孩子已安静地在旁边练习。",
    ];
    seal.replyToSender(ctx, msg,
        `📚 教导${child.name}……\n${pick(f)}\n学识提升至 ${child.eduLevel}/10，花费 ${fmtCoins(cost)}`
    );
}

// ── 差遣孩子 ──
function doDispatchChild(ctx, msg, cmdArgs, data, key, p, bonus) {
    const cname  = (cmdArgs.getArgN(2) || "").trim();
    const task   = (cmdArgs.getArgN(3) || "").trim();
    if (!cname || !task) { seal.replyToSender(ctx, msg, "用法：.烟火 差遣 [孩子名] [收地/上山/经商]"); return; }

    const child = (p.children || []).find(c => c.name === cname);
    if (!child) { seal.replyToSender(ctx, msg, `找不到孩子"${cname}"！`); return; }
    const st = childStage(child.bornAt);
    if (!st.canTask) { seal.replyToSender(ctx, msg, `${child.name}还太小，等长到少年再差遣！`); return; }
    if (!st.tasks.includes(task)) {
        seal.replyToSender(ctx, msg, `${child.name}目前只能：${st.tasks.join("、")}（成年后解锁更多）`);
        return;
    }

    const taskCdMs = 43200000; // 12小时
    if (child.lastTaskAt + taskCdMs > now()) {
        seal.replyToSender(ctx, msg, `${child.name}还在休息，${fmtMs(child.lastTaskAt + taskCdMs - now())} 后再差遣！`);
        return;
    }

    child.lastTaskAt = now();
    const eduBonus = (child.eduLevel || 0) * 0.05; // 学识每级+5%效率

    if (task === "收地") {
        const readyIdx = p.plots.findIndex(pl => pl && pl.readyAt <= now());
        if (readyIdx === -1) { child.lastTaskAt = 0; seal.replyToSender(ctx, msg, `没有成熟的庄稼，差遣无效。`); return; }
        const pl = p.plots[readyIdx];
        const cr = CROPS[pl.crop];
        const count = Math.max(1, Math.round(rand(cr.minY, cr.maxY) * (0.6 + eduBonus)));
        p.bag[pl.crop] = (p.bag[pl.crop] || 0) + count;
        p.plots[readyIdx] = null;
        saveData(data);
        seal.replyToSender(ctx, msg, `🧑 ${child.name} 去田里收了【${pl.crop}】×${count}！（学识加成 +${Math.round(eduBonus * 100)}%）`);

    } else if (task === "上山") {
        // 孩子上山，成功率和收获均低于父母
        const huntRate = 0.5 + eduBonus;
        if (Math.random() > huntRate) {
            saveData(data);
            seal.replyToSender(ctx, msg, `🏔️ ${child.name}上山转了一圈，空手而归……`);
            return;
        }
        const commonItems = HUNT_TABLE.filter(h => h.name && h.w >= 5);
        const item = pick(commonItems);
        const count = rand(item.min, item.max);
        p.bag[item.name] = (p.bag[item.name] || 0) + count;
        saveData(data);
        seal.replyToSender(ctx, msg, `🏔️ ${child.name} 上山带回了【${item.name}】×${count}！`);

    } else if (task === "经商") {
        if (!p.shops || !Object.values(p.shops).some(v => v > 0)) {
            child.lastTaskAt = 0; seal.replyToSender(ctx, msg, "你还没有铺子，无法差遣经商！"); return;
        }
        const income = Math.round(rand(30, 80) * (1 + eduBonus) * (1 + (bonus.shop || 0)));
        p.coins += income;
        saveData(data);
        seal.replyToSender(ctx, msg, `💼 ${child.name} 在铺子里帮忙，带回了额外收入 ${fmtCoins(income)}！`);
    }
}
// ============================================================
// 人间烟火 v3.0 — 主路由 + 剩余子命令
// ============================================================

// ── 立业 ──
function doInit(ctx, msg, cmdArgs, data, key) {
    cacheEp(ctx);
    if (data[key]) {
        const p = data[key];
        seal.replyToSender(ctx, msg,
            `${p.fullName || ctx.player.name} 早已在此扎根，无需重建。\n` +
            `身份：${getIdentity(p.coins).name}（${FAME[p.fame || 0].title}）| 身家：${fmtCoins(p.coins)}`
        );
        return;
    }

    const givenName = (cmdArgs.getArgN(2) || "").trim();
    if (!givenName) {
        seal.replyToSender(ctx, msg,
            `请告诉我你的名字！\n用法：.烟火 立业 [名字]\n例如：.烟火 立业 小明`
        );
        return;
    }
    if (givenName.length > 4) {
        seal.replyToSender(ctx, msg, "名字最多4个字！");
        return;
    }

    const surname    = pick(SURNAMES);
    const villageIdx = Math.floor(Math.random() * VILLAGES.length);
    const village    = VILLAGES[villageIdx];
    const fullName   = surname + givenName;

    data[key] = {
        coins: 50, plots: [null, null], huntCd: 0, stealCd: 0,
        nightRaidCd: 0, examCd: 0, shopCd: 0, helpDate: "",
        fame: 0, shops: {}, bag: { "菜种": 3 },
        signInDate: "", signInStreak: 0, freePlantDate: "",
        huntBuff: false, children: [], spouse: null, proposeFrom: null,
        surname, givenName, fullName, villageIdx,
        epPlat:  ctx.endPoint ? ctx.endPoint.platform : "",
        epBot:   ctx.endPoint ? ctx.endPoint.userId   : "",
        groupId: ctx.group ? ctx.group.groupId : "",
        userId: ctx.player.userId, userName: ctx.player.name,
    };
    saveData(data);

    seal.replyToSender(ctx, msg,
        `📖【序章】\n` +
        `${fullName}拍了拍空瘪的钱袋，望向脚下这两亩薄田，长出一口气——\n` +
        `"总得从哪里开始。"\n\n` +
        `姓名：${fullName}\n` +
        `出身：${village.name}（${village.desc}）\n` +
        `村庄加成：${BONUS_DESC[village.bonus] || "无"}${Math.round(village.val * 100)}%\n\n` +
        `初始家当：50铜 · 田地×2 · 菜种×3\n` +
        `庄稼成熟时会@你提醒！\n` +
        `输入 .烟火 帮助 查看所有玩法`
    );
}

// ── 状态 ──
function doStatus(ctx, msg, p, gid) {
    const id      = getIdentity(p.coins);
    const idIdx   = IDENTITIES.indexOf(id);
    const nextId  = IDENTITIES[idIdx + 1];
    const fort    = getDailyFortune(ctx.player.userId);
    const daily   = getDailyData(gid);
    const bonus   = getAllBonuses(p, gid);
    const village = VILLAGES[p.villageIdx ?? 0];

    const huntLeft  = (p.huntCd   || 0) - now();
    const examLeft  = (p.examCd   || 0) - now();
    const shopLeft  = (p.shopCd   || 0) - now();
    const readyCnt  = p.plots.filter(pl => pl && pl.readyAt <= now()).length;
    const shopList  = Object.entries(p.shops || {}).filter(([, v]) => v > 0).map(([n, v]) => `${n}×${v}`);
    const children  = p.children || [];

    // 加成汇总（村庄 + 佳人）
    const bonusLines = [];
    if (bonus.crop)  bonusLines.push(`作物+${Math.round(bonus.crop * 100)}%`);
    if (bonus.sell)  bonusLines.push(`售价+${Math.round(bonus.sell * 100)}%`);
    if (bonus.shop)  bonusLines.push(`铺子+${Math.round(bonus.shop * 100)}%`);
    if (bonus.exam)  bonusLines.push(`科举+${Math.round(bonus.exam * 100)}%`);
    if (bonus.steal) bonusLines.push(`偷菜+${Math.round(bonus.steal * 100)}%`);
    if (bonus.anti)  bonusLines.push(`防盗+${Math.round(bonus.anti * 100)}%`);
    if (bonus.rare)  bonusLines.push(`稀有+${Math.round(bonus.rare * 100)}%`);
    if (bonus.hunt)  bonusLines.push(`打猎+${Math.round(bonus.hunt * 100)}%`);

    const achTitle = getPlayerTitle(p);
    const lines = [
        `📜 ${p.fullName || ctx.player.name}${achTitle ? `【${achTitle}】` : ""} 的发家档案`,
        `━━━━━━━━━━`,
        `身份：${id.name} | 功名：${FAME[p.fame || 0].title}`,
        `出身：${village.name}`,
        `身家：${fmtCoins(p.coins)}`,
        `今日运势：${fort.emoji}${fort.label}`,
        `田地：${p.plots.length}块${readyCnt ? `（${readyCnt}块已熟！）` : ""}`,
    ];
    if (shopList.length) lines.push(`铺子：${shopList.join("、")} | 收租：${shopLeft > 0 ? fmtMs(shopLeft) + "后" : "可收"}`);
    lines.push(`上山：${huntLeft > 0 ? fmtMs(huntLeft) + "后可出发" : "可出发"}`);
    if ((p.fame || 0) < FAME.length - 1) {
        const fl = FAME[p.fame || 0];
        lines.push(`科举：${examLeft > 0 ? fmtMs(examLeft) + "后可考" : `可参考（需${fmtCoins(fl.examCost)}，升${FAME[(p.fame||0)+1].title}）`}`);
    }
    if (p.spouse) lines.push(`配偶：${p.spouse.name}（${p.spouse.type === "npc" ? "佳人" : "玩家"}）`);
    if (children.length) lines.push(`子嗣：${children.map(c => c.name).join("、")}`);
    if (bonusLines.length) lines.push(`当前加成：${bonusLines.join(" | ")}`);
    lines.push(`━━━━━━━━━━`);
    lines.push(nextId ? `距【${nextId.name}】还差 ${fmtCoins(nextId.threshold - p.coins)}` : "富甲天下，已至巅峰！");

    // 今日事件提示
    if (daily.events.length) {
        lines.push(`\n今日事件：${daily.events.map(e => `${e.emoji}${e.name}`).join(" | ")}`);
    }
    seal.replyToSender(ctx, msg, lines.join("\n"));
}

// ── 背包 ──
function doBackpack(ctx, msg, p) {
    const bag = p.bag || {};
    const items = Object.entries(bag).filter(([, v]) => v > 0);
    if (!items.length) { seal.replyToSender(ctx, msg, `${p.fullName || ctx.player.name} 的背包空空如也！`); return; }

    const seeds = [], crops = [], hunts = [], special = [];
    for (const [name, count] of items) {
        if (SEED_MAP[name])             seeds.push(`${name}×${count}`);
        else if (CROPS[name])           crops.push(`${name}×${count}`);
        else if (SPECIAL_ITEMS[name] || FESTIVAL_ITEMS[name])   special.push(`${name}×${count}`);
        else                            hunts.push(`${name}×${count}`);
    }
    const lines = [];
    if (seeds.length)   lines.push(`【种子】${seeds.join("、")}`);
    if (crops.length)   lines.push(`【农产】${crops.join("、")}`);
    if (hunts.length)   lines.push(`【山货】${hunts.join("、")}`);
    if (special.length) lines.push(`【特殊】${special.join("、")}`);
    seal.replyToSender(ctx, msg, `🎒 ${p.fullName || ctx.player.name} 的背包：\n${lines.join("\n")}`);
}

// ── 天气 ──
function doWeather(ctx, msg, gid, p) {
    const daily = getDailyData(gid);
    const w = daily.weather;
    const tierLines = [];
    // 只显示玩家已解锁的推荐作物
    const recUnlocked = (daily.rec || []).filter(c =>
        CROPS[c] && p.coins >= CROPS[c].reqW && (p.fame || 0) >= CROPS[c].reqF
    );
    const recLocked = (daily.rec || []).filter(c =>
        CROPS[c] && (p.coins < CROPS[c].reqW || (p.fame || 0) < CROPS[c].reqF)
    );

    let reply = `${w.emoji} 今日天气：${w.name}\n"${w.desc}"\n\n`;
    reply += `作物收成：×${w.cropMod.toFixed(2)} | 打猎：×${w.huntMod.toFixed(2)} | 药材：×${w.herbMod.toFixed(2)}\n`;
    reply += `\n今日适合种植：${recUnlocked.length ? recUnlocked.join("、") : "（已解锁作物无特别推荐）"}`;
    if (recLocked.length) reply += `\n（未解锁推荐：${recLocked.join("、")}）`;
    if (daily.events.length) {
        reply += `\n\n今日事件：\n` + daily.events.map(e => `${e.emoji}【${e.name}】${e.desc}`).join("\n");
    }
    seal.replyToSender(ctx, msg, reply);
}

// ── 每日事件 ──
function doEvents(ctx, msg, gid) {
    const daily = getDailyData(gid);
    if (!daily.events.length) { seal.replyToSender(ctx, msg, "今日无特殊事件，平平安安。"); return; }
    const lines = daily.events.map(e => `${e.emoji}【${e.name}】\n${e.desc}`);
    seal.replyToSender(ctx, msg, `📰 今日事件（共${daily.events.length}个）：\n\n${lines.join("\n\n")}`);
}

// ── 运势 ──
function doFortune(ctx, msg) {
    const f = getDailyFortune(ctx.player.userId);
    seal.replyToSender(ctx, msg,
        `${f.emoji}【今日运势：${f.label}】\n"${f.poem}"\n\n` +
        `出售价格 ×${f.sellM.toFixed(2)} | 偷菜成功 ×${f.stealM.toFixed(2)} | 作物收获 ×${f.cropM.toFixed(2)}\n` +
        `（运势每日一换，${ctx.player.name}明日自会不同）`
    );
}

// ── 村子信息 ──
function doVillage(ctx, msg, p, gid) {
    const village = VILLAGES[p.villageIdx ?? 0];
    // 统计群内同村人数
    const data = getData();
    const villagers = Object.values(data).filter(
        v => v.groupId === ctx.group.groupId && v.villageIdx === p.villageIdx && v.userId !== ctx.player.userId
    );
    const names = villagers.slice(0, 5).map(v => v.fullName || v.userName);

    seal.replyToSender(ctx, msg,
        `🏘️ ${p.fullName || ctx.player.name} 的出身地\n` +
        `━━━━━━\n` +
        `【${village.name}】\n${village.desc}\n\n` +
        `村庄加成：${BONUS_DESC[village.bonus] || "无"}${Math.round(village.val * 100)}%\n` +
        `群内同村人：${names.length ? names.join("、") + (villagers.length > 5 ? `等${villagers.length}人` : "") : "暂无"}\n` +
        `（村庄随机分配，永久固定，无法更改）`
    );
}

// ── 帮助 ──
function doHelp(ctx, msg, p) {
    seal.replyToSender(ctx, msg,
        `🌾【人间烟火】全指令一览\n` +
        `━━【每日必做】━━\n` +
        `  签到 / 天气 / 事件 / 运势\n` +
        `━━【田地种植】━━\n` +
        `  种 [作物] / 收 / 田地 / 扩地\n` +
        `  （成熟自动@提醒｜天气影响收成）\n` +
        `━━【山野】━━\n` +
        `  上山 / 偷 @目标 / 夜袭\n` +
        `━━【买卖】━━\n` +
        `  集市 / 买 [种子] [数量] / 卖 [物品] [数量/全部]\n` +
        `━━【仕途】━━\n` +
        `  科举 / 开铺 [铺名] / 铺子 / 收租\n` +
        `━━【佳人】━━\n` +
        `  花名册 [男/女/空闲/页码] / 佳人 [姓名]\n` +
        `  追求 [姓名] / 放手 [姓名]\n` +
        `━━【婚育】━━\n` +
        `  求婚 @目标 / 迎娶 [佳人名]\n` +
        `  答应 / 拒绝 / 离婚 / 帮忙\n` +
        `  孩子 / 教导 [孩子名] / 差遣 [孩子名] [任务]\n` +
        `━━【其他】━━\n` +
        `  状态 / 背包 / 村子 / 排行 / 成就 / 节日\n` +
        `━━【作物解锁】━━\n` +
        `  初阶：无需条件 | 中阶：小农+秀才\n` +
        `  进阶：富农+举人 | 高阶：小商人+进士 | 仙阶：大商人+状元`
    );
}

// ============================================================
// 主指令路由
// ============================================================
let cmdMain = seal.ext.newCmdItemInfo();
cmdMain.name = "烟火";
cmdMain.help = "人间烟火系统。输入 .烟火 帮助 查看所有指令。";

cmdMain.solve = (ctx, msg, cmdArgs) => {
    const sub  = (cmdArgs.getArgN(1) || "").trim();
    const gid  = ctx.group ? ctx.group.groupId : "";

    // ── 不需要立业的指令 ──
    if (!sub || sub === "帮助" || sub === "help") {
        const data = getData();
        doHelp(ctx, msg, data[pk(ctx)]);
        return seal.ext.newCmdExecuteResult(true);
    }
    if (sub === "立业" || sub === "开始") {
        const data = getData();
        doInit(ctx, msg, cmdArgs, data, pk(ctx));
        return seal.ext.newCmdExecuteResult(true);
    }

    // ── 需要立业的指令 ──
    const data = ensurePlayer(ctx);
    const key  = pk(ctx);
    if (!data[key]) {
        seal.replyToSender(ctx, msg, "请先输入 .烟火 立业 [名字] 开始游戏！");
        return seal.ext.newCmdExecuteResult(true);
    }
    const p     = data[key];
    const daily = getDailyData(gid);
    const fort  = getDailyFortune(ctx.player.userId);
    const bonus = getAllBonuses(p, gid);

    switch (sub) {
        // 每日
        case "签到":                 doSignIn(ctx, msg, data, key); break;
        case "天气":                 doWeather(ctx, msg, gid, p); break;
        case "事件": case "每日事件": doEvents(ctx, msg, gid); break;
        case "运势": case "天命":    doFortune(ctx, msg); break;

        // 信息
        case "状态": case "身家":    doStatus(ctx, msg, p, gid); break;
        case "背包": case "仓库":    doBackpack(ctx, msg, p); break;
        case "村子": case "出身":    doVillage(ctx, msg, p, gid); break;

        // ── 新增：排行 / 成就 / 节日 ──
        case "排行": case "排行榜":  doLeaderboard(ctx, msg, gid); break;
        case "成就":                 doAchievementList(ctx, msg, p); break;
        case "节日": case "节气":    doFestivalInfo(ctx, msg); break;

        // 种地（附成就检查）
        case "种": case "种地":
            doPlant(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;
        case "收": case "收地":
            doHarvest(ctx, msg, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;
        case "田": case "田地":      doViewFarm(ctx, msg, p, daily); break;
        case "扩地": case "买地":    doExpandFarm(ctx, msg, data, key, p); break;

        // 山野（附成就检查）
        case "上山": case "打猎":
            doHunt(ctx, msg, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;
        case "偷":  case "偷菜":
            doSteal(ctx, msg, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;
        case "夜袭":
            doNightRaid(ctx, msg, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;

        // 买卖（成就检查在卖出后）
        case "集市": case "市":      doMarket(ctx, msg, p, daily); break;
        case "买":  case "购买":     doBuy(ctx, msg, cmdArgs, data, key, p, daily); break;
        case "卖":  case "出售":
            doSell(ctx, msg, cmdArgs, data, key, p, daily, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;

        // 科举 & 铺子（附成就检查）
        case "科举": case "考试":
            doExam(ctx, msg, data, key, p, fort, bonus);
            { const na = checkAchievements(p, gid); if (na.length) { seal.replyToSender(ctx, msg, fmtNewAchievements(na)); saveData(data); } }
            break;
        case "开铺":                 doOpenShop(ctx, msg, cmdArgs, data, key, p); break;
        case "铺子": case "我的铺子":doViewShops(ctx, msg, p); break;
        case "收租": case "租":      doCollectRent(ctx, msg, data, key, p, bonus); break;

        // 佳人
        case "花名册": case "册":    doCharList(ctx, msg, cmdArgs, p, gid); break;
        case "佳人": case "我的佳人":doCharDetail(ctx, msg, cmdArgs, gid); break;
        case "追求": case "争抢":    doPursue(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "放手": case "放弃":    doRelease(ctx, msg, cmdArgs, data, key, p, gid); break;

        // 婚育
        case "迎娶":                 doMarryNPC(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "求婚":                 doProposePlayer(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "答应":                 doAccept(ctx, msg, data, key, p, gid); break;
        case "拒绝":                 doReject(ctx, msg, data, key, p); break;
        case "离婚":                 doDivorce(ctx, msg, data, key, p, gid); break;
        case "帮忙": case "帮帮":    doSpouseHelp(ctx, msg, cmdArgs, data, key, p, gid); break;
        case "孩子": case "子嗣":    doViewChildren(ctx, msg, p); break;
        case "教导":                 doTeachChild(ctx, msg, cmdArgs, data, key, p); break;
        case "差遣":                 doDispatchChild(ctx, msg, cmdArgs, data, key, p, bonus); break;

        default:
            seal.replyToSender(ctx, msg, `不认识"${sub}"，输入 .烟火 帮助 查看所有指令。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["烟火"] = cmdMain;
// ============================================================
// 人间烟火 v3.1 扩展数据 — 节日 / 成就
// ============================================================

// ── 节日道具（可出售）──
const FESTIVAL_ITEMS = {
    "爆竹": { minP:30,  maxP:60  },
    "花灯": { minP:35,  maxP:70  },
    "粽子": { minP:25,  maxP:45  },
    "月饼": { minP:40,  maxP:80  },
    "汤圆": { minP:20,  maxP:40  },
};

// ── 节日日历 ──
// signMod:签到倍率, harvestBoost:收成倍率, rareBoost:稀有品倍率
// herbBoost:药材价格倍率, charDisc:佳人追求折扣, giftItem:签到礼品
const FESTIVALS = [
    { month:1,  day:1,  name:"元旦",   emoji:"🎆", duration:1,
      signMod:2.0, special:"新年伊始，万象更新！签到奖励翻倍！" },
    { month:2,  day:5,  name:"春节",   emoji:"🧨", duration:3,
      signMod:5.0, special:"爆竹声中一岁除，春风送暖入屠苏！",
      giftItem:"爆竹", giftCount:3, harvestBoost:1.3 },
    { month:2,  day:19, name:"元宵节", emoji:"🏮", duration:1,
      signMod:2.0, special:"月上柳梢头，人约黄昏后。佳人追求八折！",
      charDisc:0.8, giftItem:"花灯", giftCount:1 },
    { month:4,  day:5,  name:"清明",   emoji:"🌿", duration:1,
      signMod:1.5, special:"草木萌生，山间药材格外茂盛。",
      herbBoost:2.0, rareBoost:1.5 },
    { month:6,  day:1,  name:"端午节", emoji:"🎋", duration:1,
      signMod:2.0, special:"五月五，是端午！粽子飘香，驱邪避秽！",
      giftItem:"粽子", giftCount:2, herbBoost:1.5 },
    { month:8,  day:10, name:"七夕",   emoji:"💫", duration:1,
      signMod:2.0, special:"天上鹊桥相会，今日佳人追求七折！",
      charDisc:0.7 },
    { month:9,  day:17, name:"中秋节", emoji:"🌕", duration:1,
      signMod:3.0, special:"但愿人长久，千里共婵娟。今日大丰收！",
      giftItem:"月饼", giftCount:2, harvestBoost:1.5 },
    { month:10, day:4,  name:"重阳节", emoji:"🍂", duration:1,
      signMod:2.0, special:"遥知兄弟登高处，今日上山稀有大增！",
      rareBoost:2.0 },
    { month:12, day:22, name:"冬至",   emoji:"❄️", duration:1,
      signMod:2.5, special:"冬至大如年！今日签到送汤圆！",
      giftItem:"汤圆", giftCount:2 },
];

function getTodayFestival() {
    const d = new Date();
    const m = d.getMonth() + 1, day = d.getDate(), yr = d.getFullYear();
    for (const f of FESTIVALS) {
        const start = new Date(yr, f.month - 1, f.day);
        const today = new Date(yr, m - 1, day);
        const diff  = (today - start) / 86400000;
        if (diff >= 0 && diff < f.duration) return f;
    }
    return null;
}

// ── 成就定义（25个）──
const ACHIEVEMENTS = [
    // 农耕
    { id:"first_harvest", name:"初耕",     title:"田野新人", desc:"完成第一次收获",           hidden:false },
    { id:"harvest_50",    name:"百收老农",  title:"老农",     desc:"累计收获50次作物",         hidden:false },
    { id:"plant_t2",      name:"中阶园丁",  title:"园丁",     desc:"种过全部5种中阶作物",      hidden:false },
    { id:"plant_t4",      name:"名贵农夫",  title:"人参翁",   desc:"成功种出人参、雪莲或龙须菜",hidden:false },
    { id:"plant_t5",      name:"仙圃主人",  title:"仙农",     desc:"成功种出仙草或神木果",     hidden:true  },
    // 财富
    { id:"rich_100",      name:"小有积蓄",  title:"有钱人",   desc:"身家达到100两",            hidden:false },
    { id:"rich_1000",     name:"千两富翁",  title:"富翁",     desc:"身家达到1000两",           hidden:false },
    { id:"rich_10000",    name:"万贯家财",  title:"豪商",     desc:"身家达到1万两",            hidden:false },
    { id:"rich_100000",   name:"富甲天下",  title:"天下首富", desc:"身家达到10万两",           hidden:true  },
    // 功名
    { id:"fame_1",        name:"金榜题名",  title:"读书人",   desc:"考中秀才",                 hidden:false },
    { id:"fame_2",        name:"举人及第",  title:"举人",     desc:"考中举人",                 hidden:false },
    { id:"fame_3",        name:"进士出身",  title:"进士",     desc:"考中进士",                 hidden:false },
    { id:"fame_4",        name:"状元及第",  title:"状元郎",   desc:"高中状元",                 hidden:true  },
    // 山野
    { id:"first_hunt",    name:"初入山林",  title:"猎手新丁", desc:"第一次上山",               hidden:false },
    { id:"hunt_30",       name:"老猎户",    title:"老猎户",   desc:"累计上山30次",             hidden:false },
    { id:"find_ginseng",  name:"参王出世",  title:"寻参人",   desc:"找到百年山参",             hidden:true  },
    { id:"chain_3",       name:"奇遇人生",  title:"奇遇者",   desc:"触发3次上山链式奇遇",      hidden:false },
    // 社交
    { id:"first_steal",   name:"顺手牵羊",  title:"小贼",     desc:"第一次偷菜/夜袭成功",      hidden:false },
    { id:"steal_10",      name:"惯犯",      title:"神偷",     desc:"偷菜/夜袭累计成功10次",    hidden:false },
    { id:"first_stolen",  name:"被人惦记",  title:"受害者",   desc:"第一次被人偷了菜",         hidden:true  },
    { id:"char_5",        name:"左拥右抱",  title:"风流客",   desc:"同时拥有5位佳人",          hidden:false },
    // 婚育
    { id:"married",       name:"洞房花烛",  title:"新婚燕尔", desc:"与人成婚",                 hidden:false },
    { id:"first_child",   name:"弄璋弄瓦",  title:"为人父母", desc:"迎来第一个孩子",           hidden:false },
    { id:"child_adult",   name:"望子成龙",  title:"好父母",   desc:"孩子成长至成年",           hidden:false },
    { id:"signin_30",     name:"持之以恒",  title:"铁杆",     desc:"连续签到30天",             hidden:false },
];

function getPlayerTitle(p) {
    const list = p.achievements || [];
    for (let i = list.length - 1; i >= 0; i--) {
        const a = ACHIEVEMENTS.find(x => x.id === list[i]);
        if (a && a.title) return a.title;
    }
    return "";
}

// 检查全部成就，返回本次新解锁列表
function checkAchievements(p, gid) {
    if (!p.stat)        p.stat = {};
    if (!p.achievements) p.achievements = [];
    const have   = new Set(p.achievements);
    const newIds = [];
    const unlock = (id) => { if (!have.has(id)) { have.add(id); p.achievements.push(id); newIds.push(id); } };

    const s     = p.stat;
    const coins = p.coins || 0;
    const fame  = p.fame  || 0;

    // 农耕
    if ((s.harvests || 0) >= 1)  unlock("first_harvest");
    if ((s.harvests || 0) >= 50) unlock("harvest_50");
    const t2all = ["南瓜","西瓜","棉花","茶叶","桑叶"].every(c => (s.cropsPlanted || {})[c]);
    if (t2all) unlock("plant_t2");
    if (["人参","雪莲","龙须菜"].some(c => (s.cropsPlanted || {})[c])) unlock("plant_t4");
    if (["仙草","神木果"].some(c => (s.cropsPlanted || {})[c])) unlock("plant_t5");
    // 财富（100铜=1两）
    if (coins >= 10000)    unlock("rich_100");
    if (coins >= 100000)   unlock("rich_1000");
    if (coins >= 1000000)  unlock("rich_10000");
    if (coins >= 10000000) unlock("rich_100000");
    // 功名
    if (fame >= 1) unlock("fame_1");
    if (fame >= 2) unlock("fame_2");
    if (fame >= 3) unlock("fame_3");
    if (fame >= 4) unlock("fame_4");
    // 山野
    if ((s.hunts || 0) >= 1)  unlock("first_hunt");
    if ((s.hunts || 0) >= 30) unlock("hunt_30");
    if ((s.huntFinds || []).includes("百年山参")) unlock("find_ginseng");
    if ((s.chains || 0) >= 3) unlock("chain_3");
    // 社交
    if ((s.steals || 0) >= 1)  unlock("first_steal");
    if ((s.steals || 0) >= 10) unlock("steal_10");
    if (p.wasStolen) unlock("first_stolen");
    const ad = getAttr(gid);
    const charCnt = CHARS.filter(([n]) => ad[n] && ad[n].owner === p.userId).length;
    if (charCnt >= 5) unlock("char_5");
    // 婚育
    if (p.spouse)                        unlock("married");
    if ((p.children || []).length >= 1)  unlock("first_child");
    if ((p.children || []).some(c => childStage(c.bornAt).name === "成年")) unlock("child_adult");
    if ((p.signInStreak || 0) >= 30)     unlock("signin_30");

    return newIds;
}

// 格式化成就解锁通知
function fmtNewAchievements(ids) {
    return ids.map(id => {
        const a = ACHIEVEMENTS.find(x => x.id === id);
        return a ? `🏅 成就解锁【${a.name}】！获得称号「${a.title}」` : "";
    }).filter(Boolean).join("\n");
}
// ============================================================
// 人间烟火 v3.1 扩展指令 — 排行榜 / 成就查看 / 节日查看
// ============================================================

// ── 排行榜 ──
function doLeaderboard(ctx, msg, gid) {
    const data  = getData();
    const all   = Object.entries(data)
        .filter(([k]) => k.startsWith(gid + "|"))
        .map(([, p]) => p)
        .filter(p => p && p.coins !== undefined);

    if (all.length < 2) {
        seal.replyToSender(ctx, msg, "群内立业的人还不够多，排行榜等人气旺了再看！");
        return;
    }

    // 财富榜
    const wealthTop = [...all].sort((a, b) => b.coins - a.coins).slice(0, 10);
    const wealthLines = wealthTop.map((p, i) => {
        const medal  = ["🥇","🥈","🥉"][i] || `${i + 1}.`;
        const title  = getPlayerTitle(p);
        const name   = p.fullName || p.userName;
        return `${medal} ${name}${title ? `【${title}】` : ""}  ${fmtCoins(p.coins)}`;
    });

    // 功名榜
    const fameTop = [...all].sort((a, b) => (b.fame || 0) - (a.fame || 0)).slice(0, 5);
    const fameLines = fameTop.map((p, i) => {
        const name = p.fullName || p.userName;
        return `${i + 1}. ${name}：${FAME[p.fame || 0].title}`;
    });

    // 成就榜
    const achTop = [...all]
        .sort((a, b) => (b.achievements || []).length - (a.achievements || []).length)
        .slice(0, 5);
    const achLines = achTop.map((p, i) => {
        const name = p.fullName || p.userName;
        return `${i + 1}. ${name}：${(p.achievements || []).length} 个成就`;
    });

    seal.replyToSender(ctx, msg,
        `🏆 人间烟火 · 群内排行\n` +
        `━━【财富榜】━━\n${wealthLines.join("\n")}\n` +
        `━━【功名榜】━━\n${fameLines.join("\n")}\n` +
        `━━【成就榜】━━\n${achLines.join("\n")}`
    );
}

// ── 成就列表 ──
function doAchievementList(ctx, msg, p) {
    const unlocked = new Set(p.achievements || []);
    const title    = getPlayerTitle(p);

    const lines = ACHIEVEMENTS.map(a => {
        if (unlocked.has(a.id)) {
            return `✅ 【${a.name}】${a.desc}  称号：「${a.title}」`;
        }
        if (a.hidden) {
            return `🔒 ??? （隐藏成就）`;
        }
        return `⬜ 【${a.name}】${a.desc}`;
    });

    const total = ACHIEVEMENTS.length;
    const done  = unlocked.size;
    const pct   = Math.floor(done / total * 100);

    seal.replyToSender(ctx, msg,
        `🏅 ${p.fullName || ctx.player.name} 的成就\n` +
        `当前称号：${title ? `「${title}」` : "（无）"}\n` +
        `完成进度：${done}/${total}（${pct}%）\n` +
        `━━━━━━\n` +
        lines.join("\n")
    );
}

// ── 节日信息 ──
function doFestivalInfo(ctx, msg) {
    const today = getTodayFestival();
    const d = new Date();
    const m = d.getMonth() + 1, day = d.getDate();

    // 找下一个节日
    let next = null;
    for (const f of FESTIVALS) {
        const fDate = new Date(d.getFullYear(), f.month - 1, f.day);
        if (fDate >= d) { next = f; break; }
    }
    if (!next) next = FESTIVALS[0]; // wrap to next year

    if (today) {
        const effects = [];
        if (today.signMod  > 1)  effects.push(`签到×${today.signMod}`);
        if (today.harvestBoost)  effects.push(`收成×${today.harvestBoost}`);
        if (today.rareBoost)     effects.push(`稀有×${today.rareBoost}`);
        if (today.herbBoost)     effects.push(`药材价×${today.herbBoost}`);
        if (today.charDisc)      effects.push(`佳人${today.charDisc * 10}折`);
        if (today.giftItem)      effects.push(`签到送${today.giftItem}×${today.giftCount || 1}`);

        seal.replyToSender(ctx, msg,
            `${today.emoji} 今日节日：【${today.name}】\n` +
            `"${today.special}"\n\n` +
            `节日效果：${effects.join("、")}\n` +
            `（还有 ${today.duration - ((new Date(d.getFullYear(), m - 1, day) - new Date(d.getFullYear(), today.month - 1, today.day)) / 86400000)} 天结束）`
        );
    } else {
        seal.replyToSender(ctx, msg,
            `当前无节日。\n下一个节日：${next.emoji}【${next.name}】（${next.month}月${next.day}日）\n${next.special}`
        );
    }
}
