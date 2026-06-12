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
    "草药":    { minP:80,  maxP:130  }, // 同上山草药
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
