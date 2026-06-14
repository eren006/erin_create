"use strict";
// ==UserScript==
// @name         后宫晋升录
// @author       长日将尽
// @version      1.0.0
// @description  后宫争宠晋升游戏，支持侍寝/子嗣/陷害/夺嫡
// @timestamp    1749999999
// @license      Apache-2
// ==/UserScript==

let ext = seal.ext.find("HougongV1");
if (!ext) {
    ext = seal.ext.new("HougongV1", "长日将尽", "1.0.0");
    seal.ext.register(ext);
    seal.ext.registerStringConfig(ext, "后宫_Flask地址", "http://localhost:5004", "Flask后端地址，末尾不带/");
    seal.ext.registerStringConfig(ext, "后宫_Sync密钥", "hougong_sync_key", "与Flask后端SYNC_KEY一致");
    seal.ext.registerStringConfig(ext, "后宫_播报群号", "", "日结算播报群的群号（留空则只回复当前群）");
    seal.ext.registerStringConfig(ext, "ws地址", "", "OneBot正向WS地址（用于跨群播报）");
    seal.ext.registerStringConfig(ext, "ws Access token", "", "OneBot WS Token");
}

// ============================================================
// 存储键
// ============================================================
const KEY_PLAYER     = "hg_player_";
const KEY_GAME_STATE = "hg_game_state";
const KEY_NPC        = "hg_npc_data";
const KEY_REGISTER   = "hg_register_";
const KEY_HEIRS      = "hg_heirs_";
const KEY_LIST       = "hg_player_list";

// ============================================================
// 常量
// ============================================================
const RANK_ORDER = {
    "秀女":0,"答应":1,"常在":2,"贵人":3,
    "嫔":4,"妃":5,"贵妃":6,"皇贵妃":7,"皇后":8
};
const RANK_NAMES = ["秀女","答应","常在","贵人","嫔","妃","贵妃","皇贵妃","皇后"];
const RANK_SLOTS = {
    "秀女":999,"答应":20,"常在":15,"贵人":10,
    "嫔":6,"妃":4,"贵妃":2,"皇贵妃":1,"皇后":1
};
const RANK_FAVOR_THRESHOLD = {
    "答应":200,"常在":500,"贵人":1000,
    "嫔":2000,"妃":4000,"贵妃":8000,"皇贵妃":15000,"皇后":30000
};
const RANK_MIN_VIRTUE = {
    "答应":10,"常在":20,"贵人":30,"嫔":45,
    "妃":60,"贵妃":75,"皇贵妃":85,"皇后":90
};
const PRESTIGE_THRESHOLD = {
    "答应":15,"常在":25,"贵人":35,"嫔":50,
    "妃":70,"贵妃":90,"皇贵妃":120,"皇后":200
};
const PRESTIGE_BASE = {
    "秀女":10,"答应":30,"常在":50,"贵人":70,
    "嫔":100,"妃":140,"贵妃":190,"皇贵妃":250,"皇后":360
};
const RANK_SILVER_COST = {
    "答应":100,"常在":200,"贵人":400,"嫔":800,
    "妃":1500,"贵妃":3000,"皇贵妃":6000,"皇后":12000
};
const LOVE_STAGES = [
    {name:"陌路",min:0},{name:"有印象",min:21},{name:"垂青",min:41},
    {name:"心悦",min:61},{name:"专宠",min:81},{name:"执念",min:100}
];
const FESTIVAL_SCHEDULE = {5:"花朝节",10:"皇帝寿辰",16:"中秋宴",22:"冬至祭典",28:"太后寿宴"};
const ENDINGS = {
    8:"权倾天下",7:"帘后摄政",6:"贵妃终老",
    5:"妃位安享",4:"嫔居深宫",3:"常在湮没",
    2:"贵人飘零",1:"答应潦倒",0:"秀女出宫"
};

// ============================================================
// 家世数据（15种，5档×3）
// ============================================================
const FAMILY_TYPES = {
    1:[
        {name:"农户之女",desc:"父亲种地，母亲织布，入宫那天全村送行。",
         bonus:{health:10,talent:-3},silver:30,startRank:"秀女"},
        {name:"落魄书香之女",desc:"祖上做过官，到父亲这代家道中落，书倒是还读着。",
         bonus:{talent:8,virtue:5,silverRate:-0.1},silver:60,startRank:"秀女"},
        {name:"小吏之女",desc:"父亲在县衙跑腿，见多了人情冷暖，你也跟着学了眼力见。",
         bonus:{scheme:8,virtue:-5},silver:80,startRank:"秀女"}
    ],
    2:[
        {name:"富商之女",desc:"家里金银满库，就是买不来一个体面出身。",
         bonus:{virtue:-5,silverRate:0.25},silver:350,startRank:"秀女"},
        {name:"七品县令之女",desc:"父亲管着一方小民，你从小跟着断案，知道什么叫规矩。",
         bonus:{virtue:8,scheme:5},silver:150,startRank:"秀女"},
        {name:"御医之女",desc:"父亲见惯了生死，教你的第一件事是：什么人能活到最后。",
         bonus:{health:12,scheme:5},silver:180,startRank:"秀女"}
    ],
    3:[
        {name:"翰林学士之女",desc:"家中藏书三千卷，才华是真的，傲气也是真的。",
         bonus:{talent:15,virtue:8,scheme:-8},silver:200,startRank:"秀女"},
        {name:"御史之女",desc:"父亲的职责是挑人毛病，你从小耳濡目染，看谁都像在找把柄。",
         bonus:{scheme:10,virtue:10,loveRate:-0.05},silver:180,startRank:"秀女"},
        {name:"外省总督之女",desc:"父亲封疆一方，你在任上长大，见过权柄是什么味道。",
         bonus:{prestige:20,silverPassive:0.3},silver:280,startRank:"秀女"}
    ],
    4:[
        {name:"镇边将军之女",desc:"父亲镇守北境，兄长接了他的刀。你入宫时回头看见的是旌旗。",
         bonus:{health:15,scheme:5,talent:-5},silver:300,startRank:"答应"},
        {name:"开国勋贵之后",desc:"祖上跟太祖打天下，铁券丹书还锁在祖宅里，只是都是上一辈的事了。",
         bonus:{prestige:25,virtue:5},silver:350,startRank:"答应"},
        {name:"锦衣卫指挥使之女",desc:"父亲是皇帝的眼睛，什么都知道，什么都不能说。你学会的叫：藏。",
         bonus:{scheme:15,health:5,virtue:-8},silver:250,startRank:"答应"}
    ],
    5:[
        {name:"异姓王之女",desc:"父亲封王却非皇室，这份荣耀里藏着多少忌惮，你从来心里清楚。",
         bonus:{prestige:30,sacredFavor:100},silver:600,startRank:"贵人"},
        {name:"宗室郡主（降格参选）",desc:"本是郡主，因家族获罪降格入选。骨子里的傲，改不了。",
         bonus:{prestige:40,virtue:10,loveRate:-0.1},silver:500,startRank:"答应"},
        {name:"外戚世家之女",desc:"祖母是先帝贵妃，你流着皇家半边血，却要用另一半去挣地位。",
         bonus:{loveRate:0.1,sacredFavor:80,prestige:25},silver:700,startRank:"贵人"}
    ]
};

// ============================================================
// 性格数据（8种）
// ============================================================
const PERSONALITIES = {
    "温柔":{loveRate:0.1,scheme:-5,desc:"以柔克刚，皇帝容易心软"},
    "刚烈":{prestige:15,loveRate:-0.08,desc:"不低头，但也不太讨喜"},
    "心机":{scheme:12,virtue:-8,desc:"工于算计，但容易被看穿"},
    "天真":{virtue:12,scheme:-8,desc:"人缘好，但宫斗吃亏"},
    "风流":{attendBonus:8,virtue:-10,desc:"擅长周旋，名声有损"},
    "清冷":{prestige:10,loveDailyLoss:3,desc:"有气场，但皇帝容易忘"},
    "坚韧":{healthMax:10,healthRecovery:5,desc:"死不了，但没什么特别的光彩"},
    "多才":{talent:12,health:-8,desc:"节庆表现优异，身子骨弱"}
};

// ============================================================
// 秘密池
// ============================================================
const SECRET_POOL = [
    {type:"出身造假",penalty:"直接降档，威严归零",weight:10},
    {type:"入宫前有婚约",penalty:"德行-50，宠爱归零",weight:15},
    {type:"暗中信奉邪教",penalty:"出局（皇帝震怒）",weight:5},
    {type:"家族曾谋反",penalty:"威严-80，圣宠-500",weight:8},
    {type:"身有隐疾",penalty:"健康上限永久-20",weight:12},
    {type:"无秘密",penalty:"",weight:50}
];

// ============================================================
// 工具函数
// ============================================================
function randInt(min,max){return Math.floor(Math.random()*(max-min+1))+min;}
function randFloat(min,max){return parseFloat((Math.random()*(max-min)+min).toFixed(1));}
function weightedRandom(pool){
    const total=pool.reduce((s,i)=>s+i.weight,0);
    let r=Math.random()*total;
    for(const item of pool){r-=item.weight;if(r<=0)return item;}
    return pool[pool.length-1];
}
function buildBar(val,max,len){
    const filled=Math.round(Math.max(0,Math.min(1,val/max))*len);
    return "█".repeat(filled)+"░".repeat(len-filled);
}
function getLoveStage(love){
    let s="陌路";
    for(const x of LOVE_STAGES){if(love>=x.min)s=x.name;}
    return s;
}
function getCurrentFestival(day){return FESTIVAL_SCHEDULE[day]||null;}

function getPlayer(qq){
    const raw=seal.ext.storageGet(ext,KEY_PLAYER+qq);
    if(!raw)return null;
    try{return JSON.parse(raw);}catch{return null;}
}
function savePlayer(qq,data){
    data.updated_at=new Date().toISOString();
    seal.ext.storageSet(ext,KEY_PLAYER+qq,JSON.stringify(data));
}
function getGameState(){
    const raw=seal.ext.storageGet(ext,KEY_GAME_STATE);
    if(!raw)return makeDefaultGS();
    try{return JSON.parse(raw);}catch{return makeDefaultGS();}
}
function saveGameState(gs){
    gs.updated_at=new Date().toISOString();
    seal.ext.storageSet(ext,KEY_GAME_STATE,JSON.stringify(gs));
}
function makeDefaultGS(){
    return{day_num:0,emperor_health:100,emperor_stage:"龙体康健",
           emperor_mood:"平和",emperor_pref:"",favored_qq:null,favored_name:null,
           game_phase:"active",attend_slots:5,attend_slots_max:5,
           season:"春",last_settlement:null,updated_at:new Date().toISOString()};
}
function getAllPlayers(){
    const raw=seal.ext.storageGet(ext,KEY_LIST);
    if(!raw)return[];
    try{return JSON.parse(raw);}catch{return[];}
}
function addPlayerToList(qq){
    const list=getAllPlayers();
    if(!list.includes(qq)){list.push(qq);seal.ext.storageSet(ext,KEY_LIST,JSON.stringify(list));}
}
function getRegState(qq){
    const raw=seal.ext.storageGet(ext,KEY_REGISTER+qq);
    if(!raw)return null;try{return JSON.parse(raw);}catch{return null;}
}
function saveRegState(qq,s){seal.ext.storageSet(ext,KEY_REGISTER+qq,JSON.stringify(s));}
function clearRegState(qq){seal.ext.storageSet(ext,KEY_REGISTER+qq,"");}
function getHeirs(qq){
    const raw=seal.ext.storageGet(ext,KEY_HEIRS+qq);
    if(!raw)return[];try{return JSON.parse(raw);}catch{return[];}
}
function saveHeirs(qq,h){seal.ext.storageSet(ext,KEY_HEIRS+qq,JSON.stringify(h));}
function getNPCs(){
    const raw=seal.ext.storageGet(ext,KEY_NPC);
    if(!raw)return initNPCs();try{return JSON.parse(raw);}catch{return initNPCs();}
}
function saveNPCs(npcs){seal.ext.storageSet(ext,KEY_NPC,JSON.stringify(npcs));}

function getRankSlotUsed(rankName){
    let count=0;
    for(const qq of getAllPlayers()){
        const p=getPlayer(qq);
        if(p&&p.rank===rankName&&p.status!=="dead"&&p.status!=="eliminated")count++;
    }
    for(const n of getNPCs()){if(n.rank===rankName&&n.is_alive)count++;}
    return count;
}

function getPassiveSilver(player){
    const base=[0,0,20,40,70,100][player.family_tier]||0;
    return Math.floor(base*(1+(player.silver_passive_bonus||0)));
}

function getEmperorStage(hp){
    if(hp>=80)return"龙体康健";if(hp>=50)return"偶感不适";
    if(hp>=30)return"龙体欠安";if(hp>=10)return"病重";return"弥留";
}
function getAttendSlotsMax(hp){
    if(hp>=80)return 5;if(hp>=50)return 4;if(hp>=30)return 3;if(hp>=10)return 2;return 1;
}

// ============================================================
// NPC 初始化
// ============================================================
function initNPCs(){
    const npcs=[
        {id:1,name:"慕容瑾",title:"皇后",rank:"皇后",rank_order:8,age:28,
         appearance:72,talent:65,scheme:70,health:85,virtue:75,
         love:60,prestige:360,sacred_favor:0,
         behavior:"defensive",attend_priority:7,intrigue_chance:15,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:2,name:"沈玉珠",title:"皇贵妃",rank:"皇贵妃",rank_order:7,age:24,
         appearance:88,talent:55,scheme:55,health:78,virtue:55,
         love:85,prestige:260,sacred_favor:0,
         behavior:"love_type",attend_priority:1,intrigue_chance:15,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:3,name:"容华",title:"贵妃",rank:"贵妃",rank_order:6,age:26,
         appearance:75,talent:60,scheme:90,health:70,virtue:45,
         love:55,prestige:198,sacred_favor:0,
         behavior:"aggressive",attend_priority:3,intrigue_chance:40,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:4,name:"顾婉",title:"德妃",rank:"妃",rank_order:5,age:30,
         appearance:65,talent:70,scheme:45,health:80,virtue:70,
         love:40,prestige:158,sacred_favor:0,
         behavior:"heir_type",attend_priority:6,intrigue_chance:5,
         is_alive:true,pregnant_day:0,sons_count:1,_warned:false},
        {id:5,name:"苏锦",title:"宸妃",rank:"妃",rank_order:5,age:25,
         appearance:70,talent:95,scheme:40,health:75,virtue:65,
         love:50,prestige:148,sacred_favor:0,
         behavior:"talent_type",attend_priority:5,intrigue_chance:8,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:6,name:"林薇",title:"昭嫔",rank:"嫔",rank_order:4,age:19,
         appearance:92,talent:45,scheme:50,health:90,virtue:50,
         love:70,prestige:108,sacred_favor:0,
         behavior:"love_type",attend_priority:2,intrigue_chance:10,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:7,name:"白露",title:"静嫔",rank:"嫔",rank_order:4,age:23,
         appearance:60,talent:55,scheme:85,health:65,virtue:40,
         love:45,prestige:102,sacred_favor:0,
         behavior:"schemer",attend_priority:4,intrigue_chance:35,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false},
        {id:8,name:"小桃",title:"顺常在",rank:"常在",rank_order:2,age:17,
         appearance:55,talent:35,scheme:25,health:60,virtue:35,
         love:25,prestige:73,sacred_favor:0,
         behavior:"follower",attend_priority:8,intrigue_chance:5,
         is_alive:true,pregnant_day:0,sons_count:0,_warned:false}
    ];
    saveNPCs(npcs);return npcs;
}

// ============================================================
// 创建角色
// ============================================================
function createPlayer(qq,playerName,familyTier,familyTypeName,personalityName){
    const fData=FAMILY_TYPES[familyTier].find(f=>f.name===familyTypeName);
    const pData=PERSONALITIES[personalityName];
    if(!fData||!pData)return null;

    let ap=randFloat(40,80),ta=randFloat(10,35),sc=randFloat(10,35),
        he=randFloat(60,85),vi=randFloat(20,45);
    let prestige=PRESTIGE_BASE[fData.startRank]||10;
    let silver=fData.silver,sacredFavor=0;
    let silverRate=1,loveRate=1,loveDailyLoss=0,attendBonus=0,
        healthMax=100,healthRecovery=0,silverPassive=0;

    const fb=fData.bonus;
    if(fb.appearance) ap+=fb.appearance;
    if(fb.talent)     ta+=fb.talent;
    if(fb.scheme)     sc+=fb.scheme;
    if(fb.health)     he+=fb.health;
    if(fb.virtue)     vi+=fb.virtue;
    if(fb.prestige)   prestige+=fb.prestige;
    if(fb.sacredFavor) sacredFavor+=fb.sacredFavor;
    if(fb.silverRate)  silverRate+=fb.silverRate;
    if(fb.loveRate)    loveRate+=fb.loveRate;
    if(fb.silverPassive) silverPassive+=fb.silverPassive;

    const pb=pData;
    if(pb.talent)         ta+=pb.talent;
    if(pb.scheme)         sc+=pb.scheme;
    if(pb.virtue)         vi+=pb.virtue;
    if(pb.health)         he+=pb.health;
    if(pb.prestige)       prestige+=pb.prestige;
    if(pb.loveRate)       loveRate+=pb.loveRate;
    if(pb.loveDailyLoss)  loveDailyLoss+=pb.loveDailyLoss;
    if(pb.attendBonus)    attendBonus+=pb.attendBonus;
    if(pb.healthMax)      healthMax+=pb.healthMax;
    if(pb.healthRecovery) healthRecovery+=pb.healthRecovery;

    ap=Math.max(10,Math.min(100,ap));
    ta=Math.max(1,Math.min(100,ta));
    sc=Math.max(1,Math.min(100,sc));
    he=Math.max(10,Math.min(healthMax,he));
    vi=Math.max(1,Math.min(100,vi));

    const secret=weightedRandom(SECRET_POOL);
    const now=new Date().toISOString();

    return{
        qq,name:playerName,title:"",
        rank:fData.startRank,rank_order:RANK_ORDER[fData.startRank],
        family_tier:familyTier,family_type:familyTypeName,personality:personalityName,
        age:randInt(13,16),
        appearance:parseFloat(ap.toFixed(1)),talent:parseFloat(ta.toFixed(1)),
        scheme:parseFloat(sc.toFixed(1)),health:parseFloat(he.toFixed(1)),
        virtue:parseFloat(vi.toFixed(1)),health_max:healthMax,
        sacred_favor:sacredFavor,love:0,prestige:parseFloat(prestige.toFixed(1)),silver,
        stamina:100,stamina_max:100,status:"normal",pregnant_day:0,
        silver_rate:silverRate,love_rate:loveRate,love_daily_loss_bonus:loveDailyLoss,
        attend_bonus:attendBonus,health_recovery_bonus:healthRecovery,silver_passive_bonus:silverPassive,
        last_attend_day:0,greet_day:0,greet_count:0,
        last_study_day:0,study_type:"",last_stroll_day:0,
        last_spy_day:0,last_apply_day:0,
        love_stage:"陌路",low_love_days:0,bedridden_days:0,prestige_warning:0,
        mastered_arts:[],items_held:[],servants:[],rank_queue:null,
        secret_type:secret.type,secret_penalty:secret.penalty,secret_revealed:false,
        attended_today:false,festival_score:0,
        created_at:now,updated_at:now
    };
}

// ============================================================
// 角色卡
// ============================================================
function buildProfileCard(p){
    const nextIdx=p.rank_order+1;
    const nextRank=RANK_NAMES[nextIdx];
    const nextThr=nextRank?RANK_FAVOR_THRESHOLD[nextRank]:null;
    const prog=nextRank?`→${nextRank} 差${Math.max(0,nextThr-p.sacred_favor)}圣宠`:"已登顶";
    const status={normal:"正常",pregnant:`孕期第${p.pregnant_day}天`,
                  bedridden:`卧床第${p.bedridden_days}天`,
                  eliminated:"已出局",dead:"已薨逝"}[p.status]||p.status;
    return `【${p.name}·档案】
━━━━━━━━━━━━━━━
位份：${p.rank}${p.title?"·"+p.title:""}　年岁：${p.age}岁
出身：${p.family_type}　性格：${p.personality}
状态：${status}
━━━━━━━━━━━━━━━
容貌 ${buildBar(p.appearance,100,8)} ${p.appearance.toFixed(1)}
才华 ${buildBar(p.talent,100,8)} ${p.talent.toFixed(1)}
心计 ${buildBar(p.scheme,100,8)} ${p.scheme.toFixed(1)}
健康 ${buildBar(p.health,p.health_max,8)} ${p.health.toFixed(1)}/${p.health_max}
德行 ${buildBar(p.virtue,100,8)} ${p.virtue.toFixed(1)}
━━━━━━━━━━━━━━━
圣宠：${p.sacred_favor}　${prog}
宠爱：${p.love.toFixed(1)}（${p.love_stage}）
威严：${p.prestige.toFixed(1)}${p.prestige_warning?" ⚠️预警":""}
银两：${p.silver}两　精力：${p.stamina}/${p.stamina_max}
━━━━━━━━━━━━━━━
${p.items_held.length?"信物："+p.items_held.join("、"):"信物：无"}
${p.servants.length?"随从："+p.servants.join("、"):"随从：无"}`;
}

// ============================================================
// 检查行动条件
// ============================================================
function canAct(player,cost,ctx,msg){
    if(!player){seal.replyToSender(ctx,msg,"你还未注册，请先输入 .注册");return false;}
    if(player.status==="dead"||player.status==="eliminated"){seal.replyToSender(ctx,msg,"你已出局，无法行动。");return false;}
    if(player.status==="bedridden"){seal.replyToSender(ctx,msg,"你正在卧床养病，只能 .静养、.请御医 或 .重金调养。");return false;}
    if(player.stamina<cost){seal.replyToSender(ctx,msg,`精力不足（当前${player.stamina}，需要${cost}）。`);return false;}
    return true;
}

// ============================================================
// 指令：.注册
// ============================================================
const cmdRegister=seal.ext.newCmdItemInfo();
cmdRegister.name="注册";
cmdRegister.help="注册后宫角色";
cmdRegister.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");

    if(getPlayer(qq)){seal.replyToSender(ctx,msg,"你已注册过了～输入 .我的档案 查看角色。");return ret;}
    const gs=getGameState();
    if(gs.game_phase==="ended"){seal.replyToSender(ctx,msg,"游戏已结束，无法注册。");return ret;}

    let state=getRegState(qq);
    const input=(cmdArgs.getArgN(1)||"").trim();

    if(input==="取消"){clearRegState(qq);seal.replyToSender(ctx,msg,"已取消注册。");return ret;}

    if(!state){
        saveRegState(qq,{step:1});
        seal.replyToSender(ctx,msg,
`【后宫晋升录·入宫注册】
━━━━━━━━━━━━━━━━
永和三年，天子广开选秀之门。
你即将踏入这深深宫墙。

第一步：请输入你的闺名（2~6个字）
输入 .注册取消 可随时中止`);
        return ret;
    }

    if(state.step===1){
        if(!input||input.length<2||input.length>6){seal.replyToSender(ctx,msg,"闺名需2~6个字，请重新输入。");return ret;}
        for(const q of getAllPlayers()){const p=getPlayer(q);if(p&&p.name===input){seal.replyToSender(ctx,msg,"该名字已被使用，请换一个。");return ret;}}
        state.name=input;state.step=2;saveRegState(qq,state);
        seal.replyToSender(ctx,msg,
`闺名「${input}」已定。

第二步：选择家世档位
━━━━━━━━━━━━
1档·寒门　　　2档·小官商贾
3档·世家仕宦　4档·勋贵将门
5档·皇亲权贵
━━━━━━━━━━━━
请输入 .注册 [1~5]`);
        return ret;
    }

    if(state.step===2){
        const tier=parseInt(input);
        if(!tier||tier<1||tier>5){seal.replyToSender(ctx,msg,"请输入1~5选择档位。");return ret;}
        state.tier=tier;state.step=3;saveRegState(qq,state);
        const opts=FAMILY_TYPES[tier];
        const lines=opts.map((o,i)=>`${i+1}. ${o.name}\n   「${o.desc}」\n   银两：${o.silver}两 起始位份：${o.startRank}`);
        seal.replyToSender(ctx,msg,`第三步：选择出身\n━━━━━━━━━━━━\n${lines.join("\n\n")}\n━━━━━━━━━━━━\n请输入 .注册 [1~3]`);
        return ret;
    }

    if(state.step===3){
        const idx=parseInt(input)-1;
        const opts=FAMILY_TYPES[state.tier];
        if(isNaN(idx)||idx<0||idx>=opts.length){seal.replyToSender(ctx,msg,"请输入1~3选择出身。");return ret;}
        state.familyType=opts[idx].name;state.step=4;saveRegState(qq,state);
        const pList=Object.entries(PERSONALITIES).map(([n,d],i)=>`${i+1}. ${n}：${d.desc}`).join("\n");
        seal.replyToSender(ctx,msg,`第四步：选择性格\n━━━━━━━━━━━━\n${pList}\n━━━━━━━━━━━━\n请输入 .注册 [1~8]`);
        return ret;
    }

    if(state.step===4){
        const pNames=Object.keys(PERSONALITIES);
        const idx=parseInt(input)-1;
        if(isNaN(idx)||idx<0||idx>=pNames.length){seal.replyToSender(ctx,msg,"请输入1~8选择性格。");return ret;}
        state.personality=pNames[idx];state.step=5;saveRegState(qq,state);
        const fData=FAMILY_TYPES[state.tier].find(f=>f.name===state.familyType);
        seal.replyToSender(ctx,msg,
`确认信息
━━━━━━━━━━━━
闺名：${state.name}
出身：${state.familyType}（${state.tier}档）
性格：${state.personality}
起始位份：${fData.startRank}　银两：${fData.silver}两
━━━━━━━━━━━━
输入 .注册 确认　完成注册
输入 .注册 取消　重新开始`);
        return ret;
    }

    if(state.step===5){
        if(input!=="确认"){seal.replyToSender(ctx,msg,"请输入 .注册 确认 完成注册。");return ret;}
        const player=createPlayer(qq,state.name,state.tier,state.familyType,state.personality);
        if(!player){seal.replyToSender(ctx,msg,"注册失败，请重试。");clearRegState(qq);return ret;}
        savePlayer(qq,player);addPlayerToList(qq);clearRegState(qq);
        seal.replyToSender(ctx,msg,
`🎊 ${player.name} 入宫！

${buildProfileCard(player)}

${player.secret_type!=="无秘密"?`【私密】你藏着一个秘密：${player.secret_type}`:"【私密】你此番入宫，问心无愧。"}

输入 .帮助 查看所有指令`);
        return ret;
    }
    return ret;
};
ext.cmdMap["注册"]=cmdRegister;

// ============================================================
// 指令：.帮助
// ============================================================
const cmdHelp=seal.ext.newCmdItemInfo();
cmdHelp.name="帮助";
cmdHelp.help="查看指令列表";
cmdHelp.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    seal.replyToSender(ctx,msg,
`【后宫晋升录·指令一览】
━━━━━━━━━━━━━━━━
📋 基础
.注册　　　注册后宫角色
.我的档案　全部属性
.我的子嗣　皇子/公主
.宫廷状态　当日全局信息
━━━━━━━━━━━━━━━━
⚡ 日常行动（消耗精力）
.侍寝　　　　　　每日限一次，主要获宠途径
.请安　　　　　　每日2次，稳定圣宠
.习艺 [琴/棋/书/画/诗]　提升才华
.闲逛　　　　　　花园随机事件，每日1次
.交际 [目标名]　 与他人互动，每日1次
.打探　　　　　　获取情报，每日1次
.静养　　　　　　恢复健康（当日封锁其他行动）
━━━━━━━━━━━━━━━━
💊 养病
.请御医　　花300两，健康+30
.重金调养　花600两，健康+60
━━━━━━━━━━━━━━━━
🎪 节日
.献礼 [金额]　皇帝寿辰专属
━━━━━━━━━━━━━━━━
📈 晋升
.申请晋升　消耗银两，有成功率
━━━━━━━━━━━━━━━━
🌐 网页端（私密操作）
陷害·夺嫡·秘密`);
    return ret;
};
ext.cmdMap["帮助"]=cmdHelp;

// ============================================================
// 指令：.我的档案
// ============================================================
const cmdProfile=seal.ext.newCmdItemInfo();
cmdProfile.name="我的档案";
cmdProfile.help="查看角色属性";
cmdProfile.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册，请先输入 .注册");return ret;}
    const gs=getGameState();
    seal.replyToSender(ctx,msg,`第${gs.day_num}天\n${buildProfileCard(p)}`);
    return ret;
};
ext.cmdMap["我的档案"]=cmdProfile;
ext.cmdMap["档案"]=cmdProfile;

// ============================================================
// 指令：.宫廷状态
// ============================================================
const cmdState=seal.ext.newCmdItemInfo();
cmdState.name="宫廷状态";
cmdState.help="查看当日皇帝与名额";
cmdState.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const gs=getGameState();
    const hpBar=buildBar(gs.emperor_health,100,12);
    const slot="◆".repeat(gs.attend_slots)+"◇".repeat(Math.max(0,gs.attend_slots_max-gs.attend_slots));
    seal.replyToSender(ctx,msg,
`【宫廷状态·第${gs.day_num}天】${gs.season}
━━━━━━━━━━━━━━━
🏯 龙体：${hpBar} ${gs.emperor_health.toFixed(0)}%
   ${gs.emperor_stage}　心情：${gs.emperor_mood}
━━━━━━━━━━━━━━━
侍寝名额：${slot} 剩余${gs.attend_slots}/${gs.attend_slots_max}
${gs.favored_name?"专宠："+gs.favored_name:"专宠：暂无"}
${gs.emperor_pref?"本周皇上："+gs.emperor_pref:""}
━━━━━━━━━━━━━━━
${gs.game_phase==="active"?"游戏进行中":gs.game_phase==="dying"?"⚠️皇帝弥留，夺嫡已开始":"已结束"}`);
    return ret;
};
ext.cmdMap["宫廷状态"]=cmdState;
ext.cmdMap["状态"]=cmdState;

// ============================================================
// 指令：.侍寝
// ============================================================
const cmdAttend=seal.ext.newCmdItemInfo();
cmdAttend.name="侍寝";
cmdAttend.help="争取皇帝宠幸";
cmdAttend.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,30,ctx,msg))return ret;
    const gs=getGameState();

    if(p.last_attend_day>=gs.day_num){seal.replyToSender(ctx,msg,"今日已侍寝，明日方可再行。");return ret;}
    if(p.status==="pregnant"){seal.replyToSender(ctx,msg,"你正值孕期，不宜侍寝。");return ret;}
    if(gs.attend_slots<=0){seal.replyToSender(ctx,msg,"今日侍寝名额已满，明日再来。");return ret;}

    // 冬至禁令（前后各1天+当天）
    const fd=gs.day_num;const czDay=22;
    if(fd>=czDay-1&&fd<=czDay+1){
        p.virtue=Math.max(0,p.virtue-20);savePlayer(qq,p);
        seal.replyToSender(ctx,msg,"冬至斋戒期间，侍寝之事暂停。-德行20");return ret;
    }

    // 骰点
    let roll=randInt(1,100);
    let bonus=Math.floor(p.appearance/10)+Math.floor(p.talent/20)+Math.floor(p.love/30)+(p.attend_bonus||0);
    // 皇帝喜好
    const pref=gs.emperor_pref;
    if(pref==="喜静"&&p.virtue>=60)bonus+=15;
    else if(pref==="爱才"&&p.talent>=70)bonus+=15;
    else if(pref==="重颜"&&p.appearance>=75)bonus+=15;
    else if(pref==="好武"&&p.family_tier===4)bonus+=15;
    if(gs.emperor_health<30)bonus-=10;
    if(gs.favored_qq&&gs.favored_qq!==qq)bonus-=10;
    // 花草信物
    if(p.items_held.includes("稀罕花草")){bonus+=20;p.items_held.splice(p.items_held.indexOf("稀罕花草"),1);}
    const total=Math.min(100,Math.max(1,roll+bonus));

    p.stamina-=30;p.last_attend_day=gs.day_num;p.attended_today=true;
    gs.attend_slots=Math.max(0,gs.attend_slots-1);saveGameState(gs);

    let text="",loveGain=0,favorGain=0,silverGain=0,pregnant=false;
    if(total>=90){
        loveGain=randInt(40,80);favorGain=randInt(40,60);silverGain=randInt(60,80);
        const gs2=getGameState();gs2.emperor_health=Math.min(100,gs2.emperor_health+2);saveGameState(gs2);
        pregnant=Math.random()<0.35;
        text=`✨ 大成功！皇上龙颜大悦，夜留至天明。\n+宠爱${loveGain} +圣宠${favorGain} +银两${silverGain}`;
    }else if(total>=60){
        loveGain=randInt(15,40);favorGain=randInt(15,30);silverGain=randInt(30,50);
        pregnant=Math.random()<0.15;
        text=`✓ 侍寝顺遂，皇上略显欢颜。\n+宠爱${loveGain} +圣宠${favorGain} +银两${silverGain}`;
    }else if(total>=30){
        loveGain=randInt(5,10);favorGain=randInt(5,10);
        text=`△ 皇上只是应付了事。\n+宠爱${loveGain} +圣宠${favorGain}`;
    }else{
        p.love=Math.max(0,p.love-15);p.prestige=Math.max(0,p.prestige-5);
        text=`✗ 大失败，皇上拂袖而去。\n-宠爱15 -威严5`;
    }

    if(loveGain>0)p.love=Math.min(100,p.love+loveGain*(p.love_rate||1));
    p.sacred_favor+=favorGain;p.silver+=silverGain;
    p.love_stage=getLoveStage(p.love);

    // 专宠更新
    if(p.love>=81){const gs2=getGameState();gs2.favored_qq=qq;gs2.favored_name=p.name;saveGameState(gs2);}
    else if(gs.favored_qq===qq&&p.love<81){const gs2=getGameState();gs2.favored_qq=null;gs2.favored_name=null;saveGameState(gs2);}

    if(pregnant&&p.status==="normal"){
        p.status="pregnant";p.pregnant_day=1;
        text+="\n\n🌸 似乎有喜了……（已进入孕期）";
    }
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【侍寝】${p.name}\n${text}\n\n宠爱：${p.love.toFixed(1)} 圣宠：${p.sacred_favor}`);
    return ret;
};
ext.cmdMap["侍寝"]=cmdAttend;

// ============================================================
// 指令：.请安
// ============================================================
const cmdGreet=seal.ext.newCmdItemInfo();
cmdGreet.name="请安";
cmdGreet.help="请安获取圣宠（每日2次）";
cmdGreet.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册。");return ret;}
    if(p.status==="dead"||p.status==="eliminated"){seal.replyToSender(ctx,msg,"你已出局。");return ret;}
    if(p.stamina<10&&p.status!=="bedridden"){seal.replyToSender(ctx,msg,"精力不足。");return ret;}
    const gs=getGameState();
    if(p.greet_day<gs.day_num){p.greet_day=gs.day_num;p.greet_count=0;}
    if(p.greet_count>=2){seal.replyToSender(ctx,msg,"今日请安次数已用完。");return ret;}
    if(p.status!=="bedridden")p.stamina-=10;
    p.greet_count+=1;
    const fg=randInt(5,15),sg=randInt(10,20);
    p.sacred_favor+=fg;p.silver+=sg;p.virtue=Math.min(100,p.virtue+1);
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【请安】${p.name}（今日第${p.greet_count}次）\n+圣宠${fg}　+银两${sg}　+德行1\n圣宠：${p.sacred_favor}`);
    return ret;
};
ext.cmdMap["请安"]=cmdGreet;

// ============================================================
// 指令：.习艺
// ============================================================
const ARTS=["琴","棋","书","画","诗"];
const cmdStudy=seal.ext.newCmdItemInfo();
cmdStudy.name="习艺";
cmdStudy.help="习艺 [琴/棋/书/画/诗]";
cmdStudy.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,20,ctx,msg))return ret;
    const gs=getGameState();
    if(p.last_study_day>=gs.day_num){seal.replyToSender(ctx,msg,"今日已习艺，明日再来。");return ret;}
    const art=(cmdArgs.getArgN(1)||"").trim();
    if(!ARTS.includes(art)){seal.replyToSender(ctx,msg,"请指定才艺：.习艺 [琴/棋/书/画/诗]");return ret;}
    p.stamina-=20;p.last_study_day=gs.day_num;p.study_type=art;
    const festival=getCurrentFestival(gs.day_num);
    const mult=festival?2:1;
    const gain=parseFloat((randFloat(2,5)*mult).toFixed(1));
    const cap=p.family_type==="翰林学士之女"?120:100;
    p.talent=Math.min(cap,p.talent+gain);
    if(!p.mastered_arts.includes(art))p.mastered_arts.push(art);
    if(festival==="花朝节"||festival==="太后寿宴")p.festival_score+=p.talent*0.5+gain*10;
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,
`【习艺·${art}】${p.name}
${festival?"🎊 "+festival+"期间，效果×2！":""}
+才华${gain}${mult>1?"（节日加成）":""}
才华：${p.talent.toFixed(1)}　掌握：${p.mastered_arts.join("、")||"无"}`);
    return ret;
};
ext.cmdMap["习艺"]=cmdStudy;

// ============================================================
// 指令：.闲逛
// ============================================================
const cmdStroll=seal.ext.newCmdItemInfo();
cmdStroll.name="闲逛";
cmdStroll.help="花园随机事件（每日1次）";
cmdStroll.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,10,ctx,msg))return ret;
    const gs=getGameState();
    if(p.last_stroll_day>=gs.day_num){seal.replyToSender(ctx,msg,"今日已闲逛，明日再来。");return ret;}
    p.stamina-=10;p.last_stroll_day=gs.day_num;
    const r=Math.random();const npcs=getNPCs().filter(n=>n.is_alive);
    let text="";
    if(r<0.10){
        const pool=[
            {t:`🌟 偶遇皇上，赐步辇同游。\n+宠爱60 +圣宠80 +威严20`,
             a:(p)=>{p.love=Math.min(100,p.love+60);p.sacred_favor+=80;p.prestige+=20;}},
            {t:`🔍 撞破某位娘娘的秘密，握在手中备用。\n（获得NPC弱点把柄）`,
             a:(p)=>{p.items_held.push("秘密把柄×1");}},
            {t:`👵 太后赐座赏识。\n+威严40 +圣宠60`,
             a:(p)=>{p.prestige+=40;p.sacred_favor+=60;}}
        ];
        const e=pool[randInt(0,pool.length-1)];e.a(p);text=e.t;
    }else if(r<0.30){
        const pool=[
            {t:`😰 冲撞贵人，失了礼数。\n-德行10 -威严10`,a:(p)=>{p.virtue=Math.max(0,p.virtue-10);p.prestige=Math.max(0,p.prestige-10);}},
            {t:`🤒 中暑崴脚。\n-健康15，明日精力上限-20`,a:(p)=>{p.health=Math.max(1,p.health-15);p.stamina_max=Math.max(50,p.stamina_max-20);}},
            {t:`😨 被人窥见行踪……\n（下次被陷害成功率+20%）`,a:(p)=>{p.items_held.push("行踪暴露");}}
        ];
        const e=pool[randInt(0,pool.length-1)];e.a(p);text=e.t;
    }else if(r<0.60){
        const sg=randInt(50,150);
        const pool=[
            {t:`💰 拾到遗落饰品。\n+银两${sg}`,a:(p)=>{p.silver+=sg;}},
            {t:`🌸 发现稀罕花草。\n+健康15（可作礼物，下次侍寝+20%）`,a:(p)=>{p.health=Math.min(p.health_max,p.health+15);p.items_held.push("稀罕花草");}},
            {t:`👂 偶听八卦，得了些有用消息。\n（使用 .打探 可查看情报）`,a:()=>{}}
        ];
        const e=pool[randInt(0,pool.length-1)];e.a(p);text=e.t;
    }else{
        const npc=npcs.length?npcs[randInt(0,npcs.length-1)]:null;
        const lg=randInt(20,40);
        const pool=[
            {t:`💫 偶遇皇上，皇上与你说了几句话。\n+宠爱${lg} +圣宠30`,a:(p)=>{p.love=Math.min(100,p.love+lg);p.sacred_favor+=30;}},
            {t:`🌹 路遇${npc?npc.name+npc.title:"某位娘娘"}，闲叙片刻。\n关系+10`,a:()=>{}},
            {t:`👸 遇见太后散步，恭敬行礼获赞许。\n+德行5 +威严10`,a:(p)=>{p.virtue=Math.min(100,p.virtue+5);p.prestige+=10;}}
        ];
        const e=pool[randInt(0,pool.length-1)];e.a(p);text=e.t;
    }
    p.love_stage=getLoveStage(p.love);
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【闲逛·御花园】${p.name}\n\n${text}`);
    return ret;
};
ext.cmdMap["闲逛"]=cmdStroll;

// ============================================================
// 指令：.打探
// ============================================================
const cmdSpy=seal.ext.newCmdItemInfo();
cmdSpy.name="打探";
cmdSpy.help="获取宫中情报";
cmdSpy.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,20,ctx,msg))return ret;
    const gs=getGameState();
    if(p.last_spy_day>=gs.day_num){seal.replyToSender(ctx,msg,"今日已打探，明日再来。");return ret;}
    p.stamina-=20;p.last_spy_day=gs.day_num;p.scheme=Math.min(100,p.scheme+1);
    const quality=p.scheme>=70?"高":p.scheme>=40?"中":"低";
    const players=getAllPlayers().map(q=>getPlayer(q)).filter(q=>q&&q.qq!==qq&&q.status!=="dead");
    const npcs=getNPCs().filter(n=>n.is_alive);
    const all=[...players.map(x=>({name:x.name,type:"player",d:x})),
               ...npcs.map(x=>({name:x.name,type:"npc",d:x}))];
    let intel="宫中暂无消息……";
    if(all.length){
        const t=all[randInt(0,all.length-1)];
        const d=t.d;
        if(quality==="高"){
            if(t.type==="player")intel=`探得「${t.name}」：位份${d.rank}，宠爱${d.love.toFixed(0)}，威严${d.prestige.toFixed(0)}，健康${d.health.toFixed(0)}，圣宠${d.sacred_favor}`;
            else intel=`探得「${t.name}${d.title}」：位份${d.rank}，宠爱${d.love.toFixed(0)}，威严${d.prestige.toFixed(0)}`;
        }else if(quality==="中"){
            intel=`探得「${t.name}」片段：宠爱约${Math.round(d.love/10)*10}，威严${d.prestige>100?"较高":"偏低"}`;
        }else{
            intel=`打探到模糊消息：宫中有人近日${Math.random()>0.5?"圣宠见涨":"宠爱下滑"}，具体不详……`;
        }
    }
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【打探】${p.name}　情报质量：${quality}\n\n${intel}`);
    return ret;
};
ext.cmdMap["打探"]=cmdSpy;

// ============================================================
// 指令：.交际
// ============================================================
const cmdSocial=seal.ext.newCmdItemInfo();
cmdSocial.name="交际";cmdSocial.help="交际 [目标名]，与他人互动（每日1次）";
cmdSocial.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,15,ctx,msg))return ret;
    const gs=getGameState();
    const KEY_SOCIAL=`hg_social_${qq}`;
    const lastDay=parseInt(seal.ext.storageGet(ext,KEY_SOCIAL)||"0");
    if(lastDay>=gs.day_num){seal.replyToSender(ctx,msg,"今日已交际，明日再来。");return ret;}
    const target=(cmdArgs.getArgN(1)||"").trim();
    if(!target){seal.replyToSender(ctx,msg,"请输入目标名：.交际 [对方名字]");return ret;}

    p.stamina-=15;
    seal.ext.storageSet(ext,KEY_SOCIAL,String(gs.day_num));

    // 查找玩家目标
    const allQQs=getAllPlayers();
    let tPlayer=null,tQQ=null;
    for(const q of allQQs){
        const tp=getPlayer(q);
        if(tp&&tp.name===target&&q!==qq&&tp.status!=="dead"&&tp.status!=="eliminated"){tPlayer=tp;tQQ=q;break;}
    }

    // 查找NPC目标
    const npcs=getNPCs();
    const tNPC=npcs.find(n=>n.is_alive&&(n.name===target||n.name+n.title===target));

    if(tPlayer&&tQQ){
        // 与玩家互动
        const fg=randInt(15,30);
        p.sacred_favor+=fg;p.prestige=Math.min(500,p.prestige+5);
        tPlayer.prestige=Math.min(500,tPlayer.prestige+5);tPlayer.sacred_favor+=10;
        savePlayer(tQQ,tPlayer);savePlayer(qq,p);
        seal.replyToSender(ctx,msg,
`【交际】${p.name} × ${tPlayer.name}
相互寒暄，谈笑风生。
+圣宠${fg} +威严5
（${tPlayer.name} 也获得 +圣宠10 +威严5）`);
    }else if(tNPC){
        // 与NPC互动
        const fg=randInt(20,40);
        p.sacred_favor+=fg;p.prestige=Math.min(500,p.prestige+8);
        // 部分NPC互动有额外效果
        let extra="";
        if(tNPC.behavior==="talent_type"){p.talent=Math.min(100,p.talent+2);extra="\n（精通才艺，耳濡目染 +才华2）";}
        else if(tNPC.behavior==="heir_type"&&p.status==="pregnant"){p.health=Math.min(p.health_max||100,p.health+5);extra="\n（聊起子嗣经验，心情放松 +健康5）";}
        else if(tNPC.behavior==="defensive"||tNPC.rank_order>=7){p.virtue=Math.min(100,p.virtue+3);extra="\n（与位尊者交谈，举止愈发端庄 +德行3）";}
        savePlayer(qq,p);
        seal.replyToSender(ctx,msg,
`【交际】${p.name} × ${tNPC.name}${tNPC.title}
相谈甚欢，颇有收获。${extra}
+圣宠${fg} +威严8`);
    }else{
        p.stamina+=15;savePlayer(qq,p);
        seal.replyToSender(ctx,msg,`找不到「${target}」，请确认名字是否正确（不含封号）。`);
    }
    return ret;
};
ext.cmdMap["交际"]=cmdSocial;

// ============================================================
// 指令：.静养
// ============================================================
const cmdRest=seal.ext.newCmdItemInfo();
cmdRest.name="静养";
cmdRest.help="静养恢复健康";
cmdRest.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册。");return ret;}
    if(p.status==="dead"||p.status==="eliminated"){seal.replyToSender(ctx,msg,"你已出局。");return ret;}
    const gain=randInt(10,20)+(p.health_recovery_bonus||0);
    p.health=Math.min(p.health_max,p.health+gain);
    p.stamina=0;
    if(p.status==="bedridden"){
        if(p.health>=30){p.status="normal";p.bedridden_days=0;savePlayer(qq,p);seal.replyToSender(ctx,msg,`【静养】+健康${gain}\n🌿 气色好转，已解除卧床！健康：${p.health.toFixed(1)}`);return ret;}
        p.bedridden_days+=1;
    }
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【静养】${p.name}\n+健康${gain}\n健康：${p.health.toFixed(1)}${p.status==="bedridden"?`（卧床第${p.bedridden_days}天）`:""}`);
    return ret;
};
ext.cmdMap["静养"]=cmdRest;

// ============================================================
// 指令：.请御医 / .重金调养
// ============================================================
const cmdDoc=seal.ext.newCmdItemInfo();
cmdDoc.name="请御医";cmdDoc.help="花300两，健康+30";
cmdDoc.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册。");return ret;}
    if(p.silver<300){seal.replyToSender(ctx,msg,`银两不足，需300两（当前${p.silver}两）。`);return ret;}
    p.silver-=300;p.health=Math.min(p.health_max,p.health+30);
    if(p.status==="bedridden"&&p.health>=30){p.status="normal";p.bedridden_days=0;}
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【请御医】-300两　+健康30\n健康：${p.health.toFixed(1)}　银两：${p.silver}两`);
    return ret;
};
ext.cmdMap["请御医"]=cmdDoc;

const cmdHeal=seal.ext.newCmdItemInfo();
cmdHeal.name="重金调养";cmdHeal.help="花600两，健康+60，解除卧床";
cmdHeal.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册。");return ret;}
    if(p.silver<600){seal.replyToSender(ctx,msg,`银两不足，需600两（当前${p.silver}两）。`);return ret;}
    p.silver-=600;p.health=Math.min(p.health_max,p.health+60);
    if(p.status==="bedridden"){p.status="normal";p.bedridden_days=0;}
    p.stamina_max=100;
    savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【重金调养】-600两　+健康60\n健康：${p.health.toFixed(1)}　银两：${p.silver}两`);
    return ret;
};
ext.cmdMap["重金调养"]=cmdHeal;

// ============================================================
// 指令：.我的子嗣
// ============================================================
const cmdHeirs=seal.ext.newCmdItemInfo();
cmdHeirs.name="我的子嗣";cmdHeirs.help="查看子嗣列表";
cmdHeirs.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!p){seal.replyToSender(ctx,msg,"你还未注册。");return ret;}
    const list=getHeirs(qq);
    if(!list.length){seal.replyToSender(ctx,msg,`【子嗣】${p.name}\n膝下尚无子嗣。`);return ret;}
    const lines=list.map(h=>{
        const alive=h.is_alive?"":"（已薨）";
        return h.gender==="皇子"
            ?`👑 ${h.name}皇子${alive} 年岁${h.age} 才能${h.talent.toFixed(0)} 声望${h.prestige_score.toFixed(0)} ${h.stage}`
            :`🌸 ${h.name}公主${alive} 年岁${h.age}`;
    });
    seal.replyToSender(ctx,msg,`【子嗣】${p.name}\n━━━━━━━━\n${lines.join("\n")}`);
    return ret;
};
ext.cmdMap["我的子嗣"]=cmdHeirs;
ext.cmdMap["子嗣"]=cmdHeirs;

// ============================================================
// 指令：.申请晋升
// ============================================================
const cmdApply=seal.ext.newCmdItemInfo();
cmdApply.name="申请晋升";cmdApply.help="消耗银两申请晋升";
cmdApply.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,0,ctx,msg))return ret;
    const gs=getGameState();
    if(p.last_apply_day>=gs.day_num){seal.replyToSender(ctx,msg,"申请晋升每天只能一次，明日再来。");return ret;}
    const ni=p.rank_order+1;
    if(ni>8){seal.replyToSender(ctx,msg,"你已是皇后，无处可晋。");return ret;}
    const nr=RANK_NAMES[ni];
    const cost=RANK_SILVER_COST[nr];
    const minV=RANK_MIN_VIRTUE[nr];
    const minF=RANK_FAVOR_THRESHOLD[nr];
    if(nr==="皇后"&&(p.prestige<350||p.love<50)){
        seal.replyToSender(ctx,msg,`晋升皇后需威严≥350（当前${p.prestige.toFixed(0)}）且宠爱≥50（当前${p.love.toFixed(0)}）。`);return ret;
    }
    if(p.sacred_favor<minF){seal.replyToSender(ctx,msg,`圣宠不足，需${minF}（当前${p.sacred_favor}，差${minF-p.sacred_favor}）。`);return ret;}
    if(getRankSlotUsed(nr)>=RANK_SLOTS[nr]){
        p.rank_queue=nr;savePlayer(qq,p);
        seal.replyToSender(ctx,msg,`${nr}位额已满，已加入等待队列，有空位时可再申请。`);return ret;
    }
    if(p.virtue<minV){seal.replyToSender(ctx,msg,`德行不足，需${minV}（当前${p.virtue.toFixed(0)}）。`);return ret;}
    if(p.prestige_warning){seal.replyToSender(ctx,msg,"威严预警中，无法申请晋升。请先稳固威严。");return ret;}
    if(p.silver<cost){seal.replyToSender(ctx,msg,`银两不足，需${cost}两（当前${p.silver}两）。`);return ret;}
    p.silver-=cost;p.last_apply_day=gs.day_num;
    let rate=50;
    rate+=Math.min(20,Math.floor((p.sacred_favor-minF)/minF*50));
    rate+=[0,0,3,6,10,15][p.family_tier]||0;
    rate+=Math.min(15,Math.floor((p.virtue-minV)/10)*3);
    rate=Math.max(5,Math.min(90,rate));
    const roll=randInt(1,100);
    if(roll<=rate){
        p.rank=nr;p.rank_order=ni;
        p.prestige=PRESTIGE_BASE[nr]+(p.family_tier>=5?20:0);
        p.rank_queue=null;savePlayer(qq,p);
        seal.replyToSender(ctx,msg,`🎊 【晋升成功】\n${p.name} 晋升为 ${nr}！\n威严重置为 ${p.prestige.toFixed(0)}\n银两余额：${p.silver}两`);
    }else if(roll<=10){
        p.virtue=Math.max(0,p.virtue-5);p.prestige=Math.max(0,p.prestige-10);savePlayer(qq,p);
        seal.replyToSender(ctx,msg,`✗ 晋升失败且举止失仪。\n-德行5 -威严10\n银两余额：${p.silver}两`);
    }else{
        savePlayer(qq,p);
        seal.replyToSender(ctx,msg,`△ 晋升失败。银两已扣，明日可再试。\n银两余额：${p.silver}两`);
    }
    return ret;
};
ext.cmdMap["申请晋升"]=cmdApply;
ext.cmdMap["晋升"]=cmdApply;

// ============================================================
// 指令：.献礼
// ============================================================
const cmdGift=seal.ext.newCmdItemInfo();
cmdGift.name="献礼";cmdGift.help="献礼 [金额]，皇帝寿辰专属";
cmdGift.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    const qq=msg.sender.userId.replace(/\D/g,"");
    const p=getPlayer(qq);
    if(!canAct(p,0,ctx,msg))return ret;
    const gs=getGameState();
    if(getCurrentFestival(gs.day_num)!=="皇帝寿辰"){seal.replyToSender(ctx,msg,"献礼仅在皇帝寿辰（第10天）开放。");return ret;}
    const amount=parseInt(cmdArgs.getArgN(1)||"0");
    if(isNaN(amount)||amount<0){seal.replyToSender(ctx,msg,"请输入献礼金额（可为0）。");return ret;}
    if(amount>p.silver){seal.replyToSender(ctx,msg,`银两不足，当前${p.silver}两。`);return ret;}
    p.silver-=amount;p.festival_score+=amount;
    let lg=0,fg=0;
    if(amount>=500){lg=40;fg=60;}else if(amount>=200){lg=25;fg=30;}else if(amount>=1){lg=10;fg=10;}
    p.love=Math.min(100,p.love+lg);p.sacred_favor+=fg;
    p.love_stage=getLoveStage(p.love);savePlayer(qq,p);
    seal.replyToSender(ctx,msg,`【献礼】${p.name}　献${amount}两\n${lg>0?"+宠爱"+lg+" +圣宠"+fg:"礼轻情意……"}\n银两余额：${p.silver}两`);
    return ret;
};
ext.cmdMap["献礼"]=cmdGift;

// ============================================================
// 日结算主函数
// ============================================================
function runDailySettlement(ctx,msg){
    const gs=getGameState();
    gs.day_num+=1;const day=gs.day_num;
    const report=[];
    report.push(`📅 【永和三年·第${day}天】${gs.season}\n━━━━━━━━━━━━━━━━`);

    // 皇帝健康-5
    gs.emperor_health=Math.max(0,gs.emperor_health-5);
    gs.emperor_stage=getEmperorStage(gs.emperor_health);
    gs.attend_slots_max=getAttendSlotsMax(gs.emperor_health);

    // 皇帝喜好轮换（每5天）
    if(day%5===0){
        const prefs=["喜静","好武","爱才","重颜"];
        gs.emperor_pref=prefs[randInt(0,prefs.length-1)];
        report.push(`👁 皇上近日喜好有变：${gs.emperor_pref}`);
    }

    // 四季轮换（每8天）
    if(day%8===1&&day>1){
        const ss=["春","夏","秋","冬"];gs.season=ss[Math.floor((day-1)/8)%4];
        report.push(`🍃 季节更替：${gs.season}`);
    }

    const allQQs=getAllPlayers();
    const warned=[],demoted=[];

    for(const qq of allQQs){
        const p=getPlayer(qq);
        if(!p||p.status==="dead"||p.status==="eliminated")continue;

        // 年龄+2，容貌变化
        p.age+=2;
        if(p.age<=18)p.appearance=Math.min(100,p.appearance+0.5);
        else if(p.age>25&&p.age<=35)p.appearance=Math.max(0,p.appearance-0.3);
        else if(p.age>35&&p.age<=50)p.appearance=Math.max(0,p.appearance-0.5);
        else if(p.age>50)p.appearance=Math.max(0,p.appearance-0.8);

        // 宠爱衰减
        const loss=8+(p.love_daily_loss_bonus||0)+(p.status==="bedridden"?4:0)-(p.status==="pregnant"?4:0);
        p.love=Math.max(0,p.love-loss);p.love_stage=getLoveStage(p.love);

        // 专宠失效
        if(gs.favored_qq===qq&&p.love<81){gs.favored_qq=null;gs.favored_name=null;}

        // 低宠爱统计
        if(p.love<15){p.low_love_days+=1;if(p.low_love_days>=3)p.prestige=Math.max(0,p.prestige-20);}
        else{p.low_love_days=0;}

        // 精力恢复
        p.stamina=Math.min(p.stamina_max,p.stamina+50);
        if(p.stamina_max<100)p.stamina_max=Math.min(100,p.stamina_max+20);

        // 银两被动
        p.silver+=getPassiveSilver(p);

        // 孕期推进
        if(p.status==="pregnant"){
            p.pregnant_day+=1;p.health=Math.max(1,p.health-3);
            if(p.pregnant_day>=3){
                const br=processBirth(p,qq);report.push(br.text);
            }
        }

        // 卧床判定
        if(p.health<30&&p.status==="normal"){p.status="bedridden";p.bedridden_days=1;report.push(`🛌 ${p.name}健康告急，已卧床养病。`);}
        else if(p.status==="bedridden"){
            p.bedridden_days+=1;
            if(p.bedridden_days>=5&&p.bedridden_days%5===0){p.health=Math.min(p.health_max,p.health+20);p.silver=Math.max(0,p.silver-200);report.push(`👨‍⚕️ 太医强制为${p.name}诊治，-200两，+健康20。`);}
            if(p.bedridden_days===3){
                if(Math.random()>0.5){p.love=Math.min(100,p.love+20);report.push(`💭 皇上得知${p.name}卧床，怜悯，+宠爱20。`);}
                else{p.love=Math.max(0,p.love-20);report.push(`💭 皇上似乎已淡忘${p.name}……-宠爱20。`);}
            }
        }

        // 子嗣年龄+1，幼年夭折判定
        const heirs=getHeirs(qq);
        let heirChanged=false;
        for(const h of heirs){
            if(!h.is_alive)continue;
            h.age+=1;
            if(h.stage==="幼年"&&h.age>3)h.stage="童年";
            else if(h.stage==="童年"&&h.age>10)h.stage="少年";
            else if(h.stage==="少年"&&h.age>15)h.stage="成年";
            if(h.stage==="幼年"&&Math.random()<0.01){
                h.is_alive=false;
                p.love=Math.max(0,p.love-40);p.prestige=Math.max(0,p.prestige-50);p.sacred_favor=Math.max(0,p.sacred_favor-100);
                report.push(`💔 ${p.name}膝下${h.name}夭折……`);heirChanged=true;
            }
        }
        if(heirChanged)saveHeirs(qq,heirs);

        // 威严阈值检查
        const thr=PRESTIGE_THRESHOLD[p.rank];
        if(thr&&p.prestige<thr){
            if(!p.prestige_warning){p.prestige_warning=1;warned.push(p.name);}
            else{demotePlayer(p);demoted.push(p.name);}
        }else{p.prestige_warning=0;}

        p.attended_today=false;p.festival_score=0;
        savePlayer(qq,p);
    }

    // NPC行为
    runNPCBehaviors(gs,report);

    // 随机事件
    const events=genDailyEvents(gs,day);
    for(const e of events){report.push(e.text);if(e.apply)e.apply(allQQs);}

    // 节日预告/结算
    const todayFest=getCurrentFestival(day);
    const tmrFest=getCurrentFestival(day+1);
    if(tmrFest)report.push(`\n🎊 明日${tmrFest}！请提前准备。`);
    if(todayFest&&day>1){const fr=settleFestival(todayFest,allQQs);if(fr)report.push(fr);}

    // 威严播报
    if(warned.length)report.push(`\n⚠️ 威严预警：${warned.join("、")} 若明日不改善将降位！`);
    if(demoted.length)report.push(`\n📉 降位：${demoted.join("、")} 因威严不足已被降位。`);

    // 皇帝状态
    const hpBar=buildBar(gs.emperor_health,100,12);
    report.push(`\n🏯 龙体：${hpBar} ${gs.emperor_health.toFixed(0)}%（${gs.emperor_stage}）`);
    report.push(`今日侍寝名额：${gs.attend_slots_max}人`);

    // 传言3条
    const rumors=genRumors(allQQs);
    report.push("\n📰 今日宫廷传言\n━━━━━━━━");
    rumors.forEach((r,i)=>report.push(`${i+1}. ${r}`));

    gs.attend_slots=gs.attend_slots_max;
    gs.last_settlement=new Date().toISOString();

    // 驾崩检查
    if(gs.emperor_health<=0){
        gs.game_phase="ended";
        report.push("\n💀 ══════════════\n  皇上龙御归天……\n══════════════");
        const fr=doFinalSettlement(allQQs);report.push(fr);
    }else if(gs.emperor_health<=9&&gs.game_phase==="active"){
        gs.game_phase="dying";
        report.push("\n⚠️ 皇上弥留之际，夺嫡正式开始！\n请前往网页端参与。");
    }
    saveGameState(gs);

    // 播报结算报告
    broadcastToGroup(report.join("\n"),ctx,msg);

    // 异步：拉取网页端陷害队列、应用效果、同步到Flask
    const capturedGS={...gs};
    const capturedQQs=[...allQQs];
    const capturedReport=[...report];
    const capturedDay=day;
    setTimeout(async()=>{
        try{
            const intResults=await fetchAndApplyIntrigues(capturedDay);
            if(intResults.length){
                const intReport=intResults.map(r=>r.detail).filter(Boolean);
                if(intReport.length){
                    const msg2="【宫廷暗流（陷害结算）】\n"+intReport.join("\n");
                    broadcastToGroup(msg2,ctx,msg);
                }
            }
            await syncToFlask(capturedGS,capturedQQs,capturedDay,capturedReport);
        }catch(e){console.error("[HG] 异步结算任务失败:",e);}
    },500);
}

function demotePlayer(p){
    if(p.rank_order<=0)return;
    p.rank_order-=1;p.rank=RANK_NAMES[p.rank_order];
    p.prestige=PRESTIGE_BASE[p.rank];
    p.sacred_favor=Math.floor(p.sacred_favor*0.8);
    p.silver=Math.floor(p.silver*0.9);p.prestige_warning=0;
}

function processBirth(p,qq){
    const hr=p.health/p.health_max;
    p.status="normal";p.pregnant_day=0;
    let outcome="顺产";
    if(hr<0.25){const r=Math.random();if(r<0.25)outcome="大出血";else if(r<0.60)outcome="难产";}
    else if(hr<0.5){const r=Math.random();if(r<0.08)outcome="大出血";else if(r<0.30)outcome="难产";}
    const gender=Math.random()<0.5?"皇子":"公主";
    const hName=p.name.slice(-1)+(gender==="皇子"?"儿":"姐");
    const heir={id:Date.now(),mother_qq:qq,mother_name:p.name,name:hName,gender,
                age:0,talent:randFloat(10,30),prestige_score:0,support_silver:0,
                health:80,is_alive:true,stage:"幼年",born_day:getGameState().day_num};
    if(outcome==="大出血"){
        p.health=Math.max(1,p.health-60);
        if(Math.random()<0.2){p.status="dead";return{text:`💔 ${p.name}产后大出血，香消玉殒……`};}
    }else if(outcome==="难产"){p.health=Math.max(1,p.health-30);}
    p.love+=gender==="皇子"?40:20;p.sacred_favor+=gender==="皇子"?200:80;p.prestige+=gender==="皇子"?80:30;
    const hs=getHeirs(qq);hs.push(heir);saveHeirs(qq,hs);
    const icon=gender==="皇子"?"👑":"🌸";
    return{text:`${icon} ${p.name}${outcome==="顺产"?"顺利诞下":outcome+"诞下"}${gender}！`};
}

function runNPCBehaviors(gs,report){
    const npcs=getNPCs();const allQQs=getAllPlayers();
    for(const npc of npcs){
        if(!npc.is_alive)continue;
        npc.love=Math.max(0,npc.love-8);
        npc.love=Math.min(100,npc.love+randInt(5,10));
        // NPC侍寝
        const aps={1:0.3,2:0.8,3:0.5,4:0.2,5:0.4,6:0.7,7:0.3,8:0.1};
        if(gs.attend_slots>0&&Math.random()<(aps[npc.id]||0.3)){
            gs.attend_slots=Math.max(0,gs.attend_slots-1);
            npc.love=Math.min(100,npc.love+randInt(10,20));
        }
        // NPC陷害
        if(Math.random()*100<npc.intrigue_chance&&allQQs.length>0){
            let tqq=null;
            if(npc.behavior==="aggressive")tqq=getTopFavor(allQQs);
            else if(npc.behavior==="schemer")tqq=getClosestPrestige(allQQs,npc.prestige);
            else if(npc.behavior==="love_type"&&npc.love<30)tqq=getTopLove(allQQs);
            if(tqq){const tp=getPlayer(tqq);if(tp){applyIntrigue(tp,npc.scheme,"诬告");savePlayer(tqq,tp);report.push(`🗡 宫中有人遭遇算计……`);}}
        }
        // NPC威严检查
        const thr=PRESTIGE_THRESHOLD[npc.rank];
        if(thr&&npc.prestige<thr){
            if(!npc._warned){npc._warned=true;}
            else{demoteNPC(npc);report.push(`📉 ${npc.name}${npc.title}威严不足，被降为${npc.rank}。`);npc._warned=false;}
        }else{npc._warned=false;}
    }
    saveNPCs(npcs);saveGameState(gs);
}

function applyIntrigue(target,attackerScheme,method){
    const disc=Math.max(0.05,0.35-(attackerScheme-target.scheme)*0.003);
    if(Math.random()>=disc){
        if(method==="诬告"){target.virtue=Math.max(0,target.virtue-20);target.prestige=Math.max(0,target.prestige-30);}
        else if(method==="构陷失宠"){target.love=0;target.prestige=Math.max(0,target.prestige-40);}
        else if(method==="下毒"){target.health=Math.max(1,target.health-randInt(30,50));}
        else if(method==="吹枕边风"){target.love=Math.max(0,target.love-30);}
    }
}

function demoteNPC(npc){
    if(npc.rank_order<=0)return;
    npc.rank_order-=1;npc.rank=RANK_NAMES[npc.rank_order];npc.prestige=PRESTIGE_BASE[npc.rank];
}
function getTopFavor(qs){let b=null,bf=-1;for(const q of qs){const p=getPlayer(q);if(p&&p.sacred_favor>bf&&p.status!=="dead"){b=q;bf=p.sacred_favor;}}return b;}
function getTopLove(qs){let b=null,bf=-1;for(const q of qs){const p=getPlayer(q);if(p&&p.love>bf&&p.status!=="dead"){b=q;bf=p.love;}}return b;}
function getClosestPrestige(qs,ref){let b=null,bd=Infinity;for(const q of qs){const p=getPlayer(q);if(p&&p.status!=="dead"){const d=Math.abs(p.prestige-ref);if(d<bd){b=q;bd=d;}}}return b;}

function genDailyEvents(gs,day){
    const pool=[
        {text:"边关捷报传来，皇上龙颜大悦！今日侍寝成功率+10",apply:null},
        {text:"宫中宣布斋戒一日，众妃嫔皆闭门静修。",apply:null},
        {text:"御花园盛开奇花，皇上心情颇佳。",apply:null},
        {text:"太医院提醒近日气候变换，注意保暖。",apply:null},
        {text:"宫中不知从哪传出谣言，人心惶惶。",apply:null},
        {text:"节庆将至，尚膳司加紧备膳。",apply:null},
        {text:`皇上赏赐全后宫银两！`,
         apply:(qs)=>{for(const q of qs){const p=getPlayer(q);if(p&&p.status!=="dead"){p.silver+=randInt(50,150);savePlayer(q,p);}}}},
    ];
    const count=randInt(1,3);
    const result=[];const used=new Set();
    while(result.length<count){const i=randInt(0,pool.length-1);if(!used.has(i)){used.add(i);result.push(pool[i]);}}
    return result;
}

function settleFestival(name,qs){
    const players=qs.map(q=>getPlayer(q)).filter(p=>p&&p.status!=="dead");
    if(!players.length)return null;
    let r=`\n🎊 【${name}结算】`;
    if(name==="花朝节"||name==="太后寿宴"){
        const s=[...players].sort((a,b)=>b.festival_score-a.festival_score);
        const gains=[{f:200,l:50,p:20},{f:100,l:30,p:0},{f:50,l:10,p:0}];
        s.forEach((p,i)=>{const g=gains[i]||{f:20,l:0,p:0};p.sacred_favor+=g.f;p.love=Math.min(100,p.love+g.l);p.prestige+=g.p;savePlayer(p.qq,p);if(i<3)r+=`\n${["🥇","🥈","🥉"][i]} ${p.name} +圣宠${g.f}${g.l?" +宠爱"+g.l:""}`;});
    }else if(name==="冬至祭典"){
        const s=[...players].sort((a,b)=>b.virtue-a.virtue);
        [[50,40],[30,25],[20,15]].forEach(([sf,pp],i)=>{if(s[i]){s[i].sacred_favor+=sf;s[i].prestige+=pp;savePlayer(s[i].qq,s[i]);r+=`\n${["🥇","🥈","🥉"][i]} ${s[i].name} +圣宠${sf} +威严${pp}`;}});
    }else if(name==="中秋宴"){
        players.forEach(p=>{p.silver+=200;p.love=Math.min(100,p.love+5);savePlayer(p.qq,p);});r+="\n全员：+银两200 +宠爱5";
    }else if(name==="皇帝寿辰"){
        const s=[...players].sort((a,b)=>b.festival_score-a.festival_score);
        if(s[0]){s[0].prestige+=30;s[0].love=Math.min(100,s[0].love+20);savePlayer(s[0].qq,s[0]);r+=`\n🥇 献礼最丰：${s[0].name} +威严30 +宠爱20`;}
    }
    return r;
}

function genRumors(qs){
    const players=qs.map(q=>getPlayer(q)).filter(p=>p&&p.status!=="dead");
    const r=[];
    const isFake=Math.random()<0.2;
    if(!players.length)return["宫中暂无动静……","万籁俱寂。","夜深灯火渐灭。"];
    const top=([...players].sort((a,b)=>b.love-a.love)[0]);
    r.push(isFake?"「据闻某位娘娘近日失宠，夜夜落泪……」（真假未知）":`「近日有位娘娘颇得圣心，频繁蒙召，令旁人侧目。」`);
    const top2=[...players].sort((a,b)=>b.sacred_favor-a.sacred_favor)[0];
    r.push(`「有人说，某位${top2?.rank||"妃嫔"}近来圣宠见涨，地位不可小觑。」`);
    const misc=["「后宫某处昨夜灯火彻夜未熄，不知是喜是忧……」","「听说有人四处打探，用意不明。」","「某位娘娘身子欠安，皇上遣太医探视。」","「两位娘娘在花园密谈，神情甚为隐秘。」"];
    r.push(misc[randInt(0,misc.length-1)]);
    return r;
}

function doFinalSettlement(qs){
    const players=qs.map(q=>getPlayer(q)).filter(p=>p);
    const scored=players.map(p=>({name:p.name,rank:p.rank,ro:p.rank_order,status:p.status,
        score:p.rank_order*100+Math.floor(p.sacred_favor/100)+p.rank_order*50}))
        .sort((a,b)=>b.score-a.score);
    let r="👑 【最终排行】\n━━━━━━━━━━";
    scored.forEach((p,i)=>{
        const e=p.status==="dead"?"香消玉殒":(ENDINGS[p.ro]||"湮没红尘");
        r+=`\n${i+1}. ${p.name}（${p.rank}）· ${e}`;
    });
    return r;
}

// ============================================================
// 播报到指定群
// ============================================================
function broadcastToGroup(text,ctx,msg){
    const gid=seal.ext.getStringConfig(ext,"后宫_播报群号")||"";
    if(!gid){seal.replyToSender(ctx,msg,text);return;}
    // 先回复当前群
    seal.replyToSender(ctx,msg,text);
    // 再用WS推到播报群
    const wsUrl=seal.ext.getStringConfig(ext,"ws地址")||"";
    if(!wsUrl)return;
    const token=seal.ext.getStringConfig(ext,"ws Access token")||"";
    let url=wsUrl+(token?((wsUrl.includes("?")?"&":"?")+`access_token=${encodeURIComponent(token)}`):``);
    try{
        const ws=new WebSocket(url);
        ws.onopen=()=>{
            ws.send(JSON.stringify({action:"send_group_msg",params:{group_id:parseInt(gid),message:text},echo:"hg_broadcast"}));
            setTimeout(()=>ws.close(),1000);
        };
        ws.onerror=e=>console.error("[HG] 播报WS错误:",e);
    }catch(e){console.error("[HG] 播报失败:",e);}
}

// ============================================================
// 从Flask拉取并执行陷害队列（在海豹端应用效果）
// ============================================================
async function fetchAndApplyIntrigues(dayNum){
    const base=(seal.ext.getStringConfig(ext,"后宫_Flask地址")||"").replace(/\/$/,"");
    const key=seal.ext.getStringConfig(ext,"后宫_Sync密钥")||"hougong_sync_key";
    if(!base)return[];
    const results=[];
    try{
        const r=await fetch(`${base}/api/pending_intrigue/${dayNum}`,{
            headers:{"X-Sync-Key":key}
        });
        if(!r.ok)return results;
        const queue=await r.json();
        for(const item of queue){
            const result=applyWebIntrigue(item,dayNum);
            results.push(result);
        }
    }catch(e){console.error("[HG] 拉取陷害队列失败:",e);}
    return results;
}

function applyWebIntrigue(item,dayNum){
    const method=item.method;
    const tqq=item.target_qq;
    const attackerName=item.attacker_name;
    const targetName=item.target_name;
    // 获取攻击者心计
    const attacker=getPlayer(item.attacker_qq);
    const attackerScheme=attacker?attacker.scheme:20;

    let resultText="";
    if(tqq){
        const target=getPlayer(tqq);
        if(!target||target.status==="dead"||target.status==="eliminated"){
            return{id:item.id,result:"fail",detail:"目标已不存在"};
        }
        const discoverP=Math.max(0.05,0.35-(attackerScheme-target.scheme)*0.003);
        const discovered=Math.random()<discoverP;
        if(discovered){
            // 攻击者受罚
            const att=attacker;
            if(att){
                if(method==="诬告")att.prestige=Math.max(0,att.prestige-40);
                else if(method==="吹枕边风")att.sacred_favor=Math.max(0,att.sacred_favor-30);
                else if(method==="下毒")att.health=Math.max(1,att.health-20);
                else if(method==="构陷失宠")att.sacred_favor=Math.max(0,att.sacred_favor-200);
                else if(method==="落胎")att.health=Math.max(1,att.health-30);
                else att.sacred_favor=Math.max(0,att.sacred_favor-30);
                savePlayer(item.attacker_qq,att);
            }
            resultText=`${attackerName}对${targetName}使用「${method}」被发现！`;
            return{id:item.id,result:"found",detail:resultText};
        }
        // 应用效果
        if(method==="吹枕边风")target.love=Math.max(0,target.love-30);
        else if(method==="诬告"){target.virtue=Math.max(0,target.virtue-20);target.prestige=Math.max(0,target.prestige-30);}
        else if(method==="下毒")target.health=Math.max(1,target.health-randInt(30,50));
        else if(method==="构陷失宠"){target.love=0;target.prestige=Math.max(0,target.prestige-40);}
        else if(method==="落胎"&&target.status==="pregnant"){
            target.status="normal";target.pregnant_day=0;
            target.health=Math.max(1,target.health-50);target.love=Math.max(0,target.love-40);target.prestige=Math.max(0,target.prestige-50);
        }
        target.love_stage=getLoveStage(target.love);
        savePlayer(tqq,target);
        resultText=`${attackerName}对${targetName}施计「${method}」成功。`;
        return{id:item.id,result:"success",detail:resultText};
    }
    return{id:item.id,result:"fail",detail:"无效目标"};
}

// ============================================================
// 同步所有数据到Flask
// ============================================================
async function syncToFlask(gs,allQQs,dayNum,reportLines){
    const base=(seal.ext.getStringConfig(ext,"后宫_Flask地址")||"").replace(/\/$/,"");
    const key=seal.ext.getStringConfig(ext,"后宫_Sync密钥")||"hougong_sync_key";
    if(!base){console.log("[HG] 未配置Flask地址，跳过同步");return;}

    const players=allQQs.map(q=>getPlayer(q)).filter(Boolean);
    const npcs=getNPCs();
    // 收集所有子嗣
    const allHeirs=[];
    for(const qq of allQQs){for(const h of getHeirs(qq))allHeirs.push(h);}
    const logs=[{day_num:dayNum,log_type:"settlement",title:`第${dayNum}天结算`,
                 content:reportLines.join("\n"),affected:"",is_major:1}];
    try{
        await fetch(`${base}/api/sync`,{
            method:"POST",
            headers:{"Content-Type":"application/json","X-Sync-Key":key},
            body:JSON.stringify({
                players:players.map(p=>({...p})),
                npcs,heirs:allHeirs,
                game_state:{...gs},logs,
                execute_intrigue:false
            })
        });
        console.log("[HG] Flask同步完成");
    }catch(e){console.error("[HG] Flask同步失败:",e);}
}

// ============================================================
// 指令：.触发结算（管理员）
// ============================================================
const cmdSettle=seal.ext.newCmdItemInfo();
cmdSettle.name="触发结算";cmdSettle.help="（管理员）手动触发日结算";
cmdSettle.solve=(ctx,msg,cmdArgs)=>{
    const ret=seal.newCmdExecuteResult(true);
    runDailySettlement(ctx,msg);return ret;
};
ext.cmdMap["触发结算"]=cmdSettle;
ext.cmdMap["结算"]=cmdSettle;
