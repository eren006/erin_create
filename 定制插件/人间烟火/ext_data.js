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
