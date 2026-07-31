// ==UserScript==
// @name         长日闹钟
// @author       长日将尽
// @version      2.0.0
// @description  天使加百列的提醒服务，附好感度与礼物图鉴
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

/**
 * 数据存储（key 前缀 alarm_）
 *   alarm_list        Reminder[]
 *   alarm_last_fired  { "platform:uid": { content, groupId } }
 *   alarm_affection   { "platform:uid": number }        好感度 0~100
 *   alarm_catalog     { "platform:uid": string[] }      已获得礼物ID列表
 *   alarm_thank_date  { "platform:uid": string }        上次谢谢的日期 YYYY-MM-DD
 *   alarm_remind_date { "platform:uid": { date, count } } 今日设置提醒次数
 *
 * Reminder:
 *   id, platform, uid, roleName, groupId
 *   triggerAt  number
 *   content    string
 *   repeat     "none" | "daily" | "weekly:N"
 */

let ext = seal.ext.find('changri_alarm');
if (!ext) {
    ext = seal.ext.new('changri_alarm', '长日将尽', '2.0.0');
    seal.ext.register(ext);
}

// ========================
// 核心依赖：主插件共享 API
// ========================
// 本文件自身数据（提醒/好感度/图鉴）仍存于 changri_alarm 本地 ext，只在
// 需要跨插件一致性的地方（角色名解析、辅助账号→主账号）委托主插件。
function getApi()                          { return globalThis.__changriApi || null; }
function getPrimaryUid(platform, uid)      { return getApi()?.getPrimaryUid(platform, uid) ?? uid; }
function getRoleNameByApi(ctx, msg)        { return getApi()?.getRoleName(ctx, msg) ?? null; }

const MAX_REMINDERS_PER_USER = 20;

// ========================
// 礼物图鉴（100件）
// ========================

const GABRIEL_GIFTS = [
    // 羽毛 G001~G010
    { id: 'G001', name: '初羽', content: '脱落自加百列翅膀边缘的一根细小羽毛，洁白，几乎透明。' },
    { id: 'G002', name: '晨光羽', content: '沾染了清晨第一缕阳光的羽毛，轻触时有微微暖意。' },
    { id: 'G003', name: '银翎', content: '天使卫队的银色飞翎，据说能辟邪。' },
    { id: 'G004', name: '星屑羽', content: '羽轴中封存了细碎的星光，夜里会发出幽微的光。' },
    { id: 'G005', name: '雪翼羽', content: '来自高天的羽毛，触感像新雪，不会融化。' },
    { id: 'G006', name: '朝霞羽', content: '染了朝霞颜色的羽毛，橙金相间。' },
    { id: 'G007', name: '暮色翎', content: '沾着黄昏色泽的羽毛，带着淡淡的橙紫。' },
    { id: 'G008', name: '风信羽', content: '加百列传递消息时常用的羽毛，经过了千山万水。' },
    { id: 'G009', name: '虹翎', content: '雨后天晴时偶然落下的彩翎，七色俱全。' },
    { id: 'G010', name: '主翎', content: '加百列翅膀正中的一根大翎，极为罕见。' },
    // 花与植物 G011~G020
    { id: 'G011', name: '天园玫瑰', content: '伊甸园边缘采来的玫瑰，永不凋谢。' },
    { id: 'G012', name: '白百合', content: '纯洁的象征，加百列最常持的花。' },
    { id: 'G013', name: '星光茉莉', content: '只在星空下盛开的茉莉，香气沁人。' },
    { id: 'G014', name: '银铃草', content: '轻轻摇动时会发出细微的铃声。' },
    { id: 'G015', name: '云雾草', content: '采自云层之上的草，触感像轻雾。' },
    { id: 'G016', name: '晨露苔', content: '每天清晨会重新凝结晨露的小苔藓球。' },
    { id: 'G017', name: '天堂果', content: '结在天堂树上的小果子，甜蜜而不腻。' },
    { id: 'G018', name: '圣橄榄枝', content: '和平的象征，加百列出使时携带的橄榄枝。' },
    { id: 'G019', name: '月见草', content: '只在满月时开放，加百列专程为你摘下的。' },
    { id: 'G020', name: '光之花', content: '没有实体，只是一团温柔的光，握在手心不散。' },
    // 天体与自然 G021~G030
    { id: 'G021', name: '流星碎片', content: '加百列接住的一颗流星，冷却后变成小石子大小。' },
    { id: 'G022', name: '月牙切片', content: '据说是月亮边缘薄薄的一片，银白发光。' },
    { id: 'G023', name: '初雪', content: '封存在玻璃瓶里的第一场雪，不会融化。' },
    { id: 'G024', name: '彩虹线', content: '从彩虹上剪下的一段，软软的，五色交织。' },
    { id: 'G025', name: '极光粉', content: '研磨自极光的粉末，装在小瓶里，轻轻晃动会变色。' },
    { id: 'G026', name: '雷云棉', content: '加百列从雷雨云里摘下的一团棉絮，偶尔会静电。' },
    { id: 'G027', name: '日晕碎片', content: '太阳光晕破碎后散落的碎片，暖洋洋的。' },
    { id: 'G028', name: '风的形状', content: '一个密封的小盒子，打开时会涌出某处山顶的风。' },
    { id: 'G029', name: '星河水', content: '取自银河的水，装在细颈小瓶里，蓝紫色，微微发光。' },
    { id: 'G030', name: '夜幕角', content: '夜空的一角，折叠成手掌大小，展开时是满天星。' },
    // 食物与饮品 G031~G040
    { id: 'G031', name: '天使蛋糕', content: '加百列亲手烤的白色蛋糕，口感极轻盈。' },
    { id: 'G032', name: '蜂蜜小饼', content: '用天堂花园蜜蜂的蜜做的小饼干，心形。' },
    { id: 'G033', name: '圣泉水', content: '装在小瓶里的圣泉水，据说喝了会好眠。' },
    { id: 'G034', name: '星光奶糖', content: '含在嘴里会慢慢化开，留下清甜的余味。' },
    { id: 'G035', name: '云朵马卡龙', content: '质地轻如云朵，加百列带来时还是温的。' },
    { id: 'G036', name: '晨光果酱', content: '加百列亲手熬的果酱，装在小罐子里，抹面包很香。' },
    { id: 'G037', name: '天堂茶', content: '一小包茶叶，泡开后有花香与蜜香，让人平静。' },
    { id: 'G038', name: '月光饼', content: '月圆之夜制作的小饼，吃了会做好梦。' },
    { id: 'G039', name: '彩虹糖串', content: '七种颜色的糖，穿在一根细线上。' },
    { id: 'G040', name: '加百列的便当', content: '加百列特意为你准备的，用翅膀保着温带来的。' },
    // 手工与书信 G041~G050
    { id: 'G041', name: '手折星星', content: '加百列用金纸折的小星星，一颗颗装在玻璃瓶里。' },
    { id: 'G042', name: '刺绣手帕', content: '加百列亲手绣的，角上有一只小天使。' },
    { id: 'G043', name: '羽毛书签', content: '用细羽毛制成的书签，附有加百列的祝福语。' },
    { id: 'G044', name: '天使来信', content: '加百列用金色墨水写的一封短信，内容是对你的祝福。' },
    { id: 'G045', name: '手绘明信片', content: '加百列画的天堂一角，色彩很淡，很轻。' },
    { id: 'G046', name: '蜡封信', content: '用圣焰蜡封口的信件，蜡印是展翅的天使。' },
    { id: 'G047', name: '祈愿纸鸢', content: '加百列折的纸鸢，附有一根看不见终点的细线。' },
    { id: 'G048', name: '心愿瓶', content: '一个空的小瓶子。加百列说：写下心愿放进去，我会转达。' },
    { id: 'G049', name: '编织手环', content: '用银线和白线编的手环，戴上后会微微发光。' },
    { id: 'G050', name: '圣约羊皮卷', content: '记载了加百列对你承诺的小羊皮卷，内容只有你们知道。' },
    // 织物与首饰 G051~G060
    { id: 'G051', name: '云织围巾', content: '用云纤维织成的围巾，轻到几乎没有重量，却很暖。' },
    { id: 'G052', name: '天使发圈', content: '细细的，像光环一样的发圈，白色透明。' },
    { id: 'G053', name: '羽翼胸针', content: '银质的翅膀形胸针，加百列自己戴过的。' },
    { id: 'G054', name: '星光发带', content: '镶着细碎星光的发带，夜里会微微亮。' },
    { id: 'G055', name: '圣光戒指', content: '纯白的细戒，套在指尖，带来平静。' },
    { id: 'G056', name: '天堂棉手套', content: '极柔软的白手套，据说戴上后手会变暖。' },
    { id: 'G057', name: '月牙耳坠', content: '银色月牙形状的耳坠，对称的两只。' },
    { id: 'G058', name: '晨曦披肩', content: '薄薄的金白色披肩，清晨的颜色。' },
    { id: 'G059', name: '天使铃铛', content: '细小的银铃，声音很轻，加百列说是用来联络的。' },
    { id: 'G060', name: '羽冠', content: '用细羽毛编成的小冠，只有手掌大，戴上刚好合适。' },
    // 书籍与语言 G061~G070
    { id: 'G061', name: '天使语入门', content: '加百列亲手写的天使语入门小册，只有几页，字很好看。' },
    { id: 'G062', name: '星图手册', content: '加百列整理的星座手册，每颗星都有名字和故事。' },
    { id: 'G063', name: '梦境记录本', content: '加百列记录下的你的好梦，用淡金色墨水写成。' },
    { id: 'G064', name: '圣歌谱', content: '天使合唱团的曲谱，加百列说只给特别的人看。' },
    { id: 'G065', name: '诗集', content: '加百列收集的关于人间的诗，附有她自己写的注记。' },
    { id: 'G066', name: '祈祷书签', content: '书签上印着一段祈祷文，据说能带来平静。' },
    { id: 'G067', name: '天堂地图', content: '加百列手绘的天堂示意图，有点歪，像是第一次画的。' },
    { id: 'G068', name: '时光日记', content: '加百列帮你记录的日记，写的都是你做过的好事。' },
    { id: 'G069', name: '秘密词典', content: '收录了只有加百列才知道含义的词语，解释很认真。' },
    { id: 'G070', name: '羽书', content: '用羽毛制成的书页，空白的。加百列说：写下你想说的话吧。' },
    // 光与影 G071~G080
    { id: 'G071', name: '烛光', content: '一根永不熄灭的细蜡烛，加百列说点着它就不会黑暗。' },
    { id: 'G072', name: '光影相框', content: '相框里装的是一段美好时光的光影，晃动时会动。' },
    { id: 'G073', name: '晨光瓶', content: '装着某个清晨第一缕阳光的玻璃瓶，橙金色。' },
    { id: 'G074', name: '温柔灯', content: '一盏小灯，光线极柔和，不刺眼，适合睡前看书。' },
    { id: 'G075', name: '星灯', content: '用星光做的小灯，悬在空中，会慢慢转动。' },
    { id: 'G076', name: '极光镜', content: '一面小镜子，映出的不是自己，而是极光。' },
    { id: 'G077', name: '光丝线团', content: '一团发光的细线，加百列说：用来缝补破损的东西吧。' },
    { id: 'G078', name: '影子礼物', content: '一个装着某人影子的信封，打开时会有人陪着你。' },
    { id: 'G079', name: '日落快门', content: '加百列用翅膀挡住的某个日落瞬间，定格在一张光片里。' },
    { id: 'G080', name: '第一颗星', content: '每晚最先出现的那颗星。加百列说，它一直在等你抬头。' },
    // 特殊 G081~G090
    { id: 'G081', name: '平安符', content: '加百列亲自祝福过的平安符，会在你危险时发热。' },
    { id: 'G082', name: '好梦石', content: '一颗圆润的小石头，放在枕边，会带来好梦。' },
    { id: 'G083', name: '幸运羽签', content: '一根带着签文的小羽毛，签文只对你有意义。' },
    { id: 'G084', name: '遗忘药水', content: '加百列调配的，让你忘掉一件想忘的事，只有一滴。' },
    { id: 'G085', name: '时光沙漏', content: '流动的沙是金色的，翻转时会感到时间慢下来。' },
    { id: 'G086', name: '心愿灯', content: '一盏小灯笼，点燃后许愿，加百列说她听得见。' },
    { id: 'G087', name: '勇气糖', content: '加百列说：如果害怕，就把它含在嘴里。苦的，但会有力气。' },
    { id: 'G088', name: '秘密锁', content: '一把没有钥匙的锁。加百列说：你最重要的秘密，锁进去。' },
    { id: 'G089', name: '陪伴石', content: '一颗普通的小石头，但加百列摸过。她说：带着它，我就陪着你。' },
    { id: 'G090', name: '天使眼泪', content: '一滴凝固的泪，封在水晶里。加百列说：这是我唯一流过的。' },
    // 传说级 G091~G100
    { id: 'G091', name: '神谕碎片', content: '从神谕中脱落的一小块，持有者会偶尔感知到模糊的未来。' },
    { id: 'G092', name: '初始之光', content: '最初的光被切下的一小块，温热，永恒。' },
    { id: 'G093', name: '天使之心', content: '加百列心脏跳动时脱落的光粒，封在小瓶里，会一直跳动。' },
    { id: 'G094', name: '永恒蜡烛', content: '据说点燃后永不熄灭，哪怕在风中、在水里。' },
    { id: 'G095', name: '加百列的名字', content: '一张纸，上面用金字写着"Gabriel"，据说持有者受她庇护。' },
    { id: 'G096', name: '誓约羽毛', content: '加百列立誓时落下的羽毛，带着不可违背的约定。' },
    { id: 'G097', name: '神圣光晕', content: '加百列头顶光环碎裂时落下的碎片，携带者不会迷路。' },
    { id: 'G098', name: '天使之吻', content: '加百列落在你额头的一吻，封存在一片薄如蝉翼的透明片里。' },
    { id: 'G099', name: '加百列的日记', content: '记录了加百列对你的一切记忆，用你从未见过的文字写成。' },
    { id: 'G100', name: '永恒契约', content: '加百列与你签订的契约，盖着她的翅膀印，有效期：永远。' },
];

const GIFT_MAP = {};
GABRIEL_GIFTS.forEach(g => { GIFT_MAP[g.id] = g; });

// ========================
// 好感度配置
// ========================

const AFFECTION_LEVELS = [
    { min: 0,   max: 19,  label: '陌生·使者',   giftChance: 0 },
    { min: 20,  max: 39,  label: '初识·天使',   giftChance: 0 },
    { min: 40,  max: 59,  label: '友好·羽翼',   giftChance: 0.15 },
    { min: 60,  max: 79,  label: '亲密·光晕',   giftChance: 0.25 },
    { min: 80,  max: 99,  label: '挚友·圣约',   giftChance: 0.40 },
    { min: 100, max: 100, label: '羁绊·永恒',   giftChance: 0.60 },
];

function getAffectionLevel(aff) {
    return AFFECTION_LEVELS.find(l => aff >= l.min && aff <= l.max) || AFFECTION_LEVELS[0];
}

// 加百列台词，按好感度段索引（0~5）
const GABRIEL_LINES = {
    // 设置提醒成功时
    setOk: [
        '好。我会记住的。',
        '嗯，记下了。时间到了我会来的。',
        '好的，交给我吧～',
        '放心，加百列一定记得。',
        '嗯嗯！加百列一定不会忘的！',
        '只要你说的话，我都记在心里。',
    ],
    // 提醒触发时（name 和 content 由调用方拼接）
    remind: [
        (name, content) => `${name}，你委托我记住的事情，时间到了。\n「${content}」`,
        (name, content) => `${name}，你好。你之前说要提醒的事，时间到了。\n「${content}」`,
        (name, content) => `${name}，我来啦。你之前说的——\n「${content}」\n时间到了哦。`,
        (name, content) => `${name}！我记得呢——\n「${content}」\n快去做吧！`,
        (name, content) => `${name}，加百列来啦～\n「${content}」\n时间到了。我一直在等着提醒你。`,
        (name, content) => `${name}……\n「${content}」\n我一直记着的。无论何时，只要你需要，加百列都在。`,
    ],
    // 再提醒我
    snooze: [
        min => `好。${min} 分钟后我再来。`,
        min => `嗯，我再等 ${min} 分钟。`,
        min => `好～加百列再等你 ${min} 分钟！`,
        min => `哎呀，那我再去转 ${min} 圈。`,
        min => `……小懒虫。好，再等你 ${min} 分钟。`,
        min => `……加百列不会嫌烦的。${min} 分钟后再来。`,
    ],
    // 谢谢加百列
    thanks: [
        '这是应当的。',
        '不客气。能帮到你就好。',
        '嗯……谢谢你这么说。',
        '嗯！加百列很高兴～',
        '（翅膀微微收拢）……谢谢你。',
        '能陪着你……加百列觉得很幸福。',
    ],
    // 重复提醒续期提示
    repeatHint: [
        '（每次时间到了我都会来。）',
        '（下次我还会来的。）',
        '（每次都会来找你哦。）',
        '（我一直都在，不用担心。）',
        '（只要你还在，加百列就还会来。）',
        '（永远都会来的。）',
    ],
};

function lineByAff(key, aff, ...args) {
    const idx = Math.min(AFFECTION_LEVELS.findIndex(l => aff >= l.min && aff <= l.max), 5);
    const lines = GABRIEL_LINES[key];
    const line = lines[Math.max(0, idx)];
    return typeof line === 'function' ? line(...args) : line;
}

// ========================
// 工具
// ========================

function getList() {
    try { return JSON.parse(ext.storageGet('alarm_list') || '[]'); } catch { return []; }
}
function saveList(list) { ext.storageSet('alarm_list', JSON.stringify(list)); }

function getLastFired() {
    try { return JSON.parse(ext.storageGet('alarm_last_fired') || '{}'); } catch { return {}; }
}
function saveLastFired(obj) { ext.storageSet('alarm_last_fired', JSON.stringify(obj)); }

function getAffections() {
    try { return JSON.parse(ext.storageGet('alarm_affection') || '{}'); } catch { return {}; }
}
function saveAffections(obj) { ext.storageSet('alarm_affection', JSON.stringify(obj)); }

function getCatalog() {
    try { return JSON.parse(ext.storageGet('alarm_catalog') || '{}'); } catch { return {}; }
}
function saveCatalog(obj) { ext.storageSet('alarm_catalog', JSON.stringify(obj)); }

function getAff(userKey) {
    return Math.min(100, Math.max(0, getAffections()[userKey] || 0));
}
function addAff(userKey, delta) {
    const affs = getAffections();
    affs[userKey] = Math.min(100, Math.max(0, (affs[userKey] || 0) + delta));
    saveAffections(affs);
    return affs[userKey];
}

function todayStr() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}

// 今日设置提醒次数（每天最多获得3点好感，避免刷）
function canGainFromRemind(userKey) {
    try {
        const raw = ext.storageGet('alarm_remind_date') || '{}';
        const obj = JSON.parse(raw);
        const today = todayStr();
        if (!obj[userKey] || obj[userKey].date !== today) return true;
        return obj[userKey].count < 3;
    } catch { return true; }
}
function recordRemindGain(userKey) {
    try {
        const raw = ext.storageGet('alarm_remind_date') || '{}';
        const obj = JSON.parse(raw);
        const today = todayStr();
        if (!obj[userKey] || obj[userKey].date !== today) obj[userKey] = { date: today, count: 0 };
        obj[userKey].count++;
        ext.storageSet('alarm_remind_date', JSON.stringify(obj));
    } catch (e) { console.error("[闹钟] recordRemindGain 保存失败:", e.message); }
}

// 谢谢每天最多触发1次好感
function canGainFromThanks(userKey) {
    try {
        const raw = ext.storageGet('alarm_thank_date') || '{}';
        const obj = JSON.parse(raw);
        return obj[userKey] !== todayStr();
    } catch { return true; }
}
function recordThanksGain(userKey) {
    try {
        const raw = ext.storageGet('alarm_thank_date') || '{}';
        const obj = JSON.parse(raw);
        obj[userKey] = todayStr();
        ext.storageSet('alarm_thank_date', JSON.stringify(obj));
    } catch (e) { console.error("[闹钟] recordThanksGain 保存失败:", e.message); }
}

// 尝试给收件人随机一件未拥有的礼物，返回礼物对象或null
function tryGiveGift(userKey) {
    const catalog = getCatalog();
    const owned = new Set(catalog[userKey] || []);
    const remaining = GABRIEL_GIFTS.filter(g => !owned.has(g.id));
    if (remaining.length === 0) return null;
    const gift = remaining[Math.floor(Math.random() * remaining.length)];
    if (!catalog[userKey]) catalog[userKey] = [];
    catalog[userKey].push(gift.id);
    saveCatalog(catalog);
    return gift;
}

function getRoleName(ctx, msg) {
    const api = getRoleNameByApi(ctx, msg);
    if (api !== null) return api;
    // 兼容独立运行：主插件未加载时走本地实现（不做辅助账号解析）
    const main = seal.ext.find('changri');
    if (!main) return null;
    const platform = msg.platform;
    const uid = msg.sender.userId.replace(/^[a-z]+:/i, '');
    try {
        const storage = JSON.parse(main.storageGet('a_private_group') || '{}');
        return storage[platform]?.[uid]?.[0] || null;
    } catch (e) { console.error('[闹钟] getRoleName 本地回退失败:', e.message); return null; }
}

function genId() {
    return Math.random().toString(36).slice(2, 6).toUpperCase();
}

function formatTime(ts) {
    const d = new Date(ts);
    const pad = n => String(n).padStart(2, '0');
    const today = new Date();
    const tmr = new Date(today); tmr.setDate(tmr.getDate() + 1);
    const timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    if (d.toDateString() === today.toDateString()) return `今天 ${timeStr}`;
    if (d.toDateString() === tmr.toDateString()) return `明天 ${timeStr}`;
    return `${d.getMonth() + 1}/${d.getDate()} ${timeStr}`;
}

const WEEKDAY_NAMES = ['日', '一', '二', '三', '四', '五', '六'];
const WEEKDAY_MAP   = { '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 0, '天': 0 };

function repeatLabel(repeat) {
    if (repeat === 'none') return '';
    if (repeat === 'daily') return '每天';
    if (repeat.startsWith('weekly:')) return `每周${WEEKDAY_NAMES[parseInt(repeat.slice(7))]}`;
    return '';
}

function nextTrigger(repeat, fromTs) {
    if (repeat === 'daily')            return fromTs + 86400000;
    if (repeat.startsWith('weekly:')) return fromTs + 7 * 86400000;
    return null;
}

// ========================
// 时间解析
// ========================

function parseTime(input) {
    const now = Date.now();
    let m;

    m = input.match(/^(\d+)\s*分钟后$/);
    if (m) return { triggerAt: now + parseInt(m[1]) * 60000, repeat: 'none' };

    m = input.match(/^(\d+)\s*小时后$/);
    if (m) return { triggerAt: now + parseInt(m[1]) * 3600000, repeat: 'none' };

    m = input.match(/^(\d+)\s*天后$/);
    if (m) return { triggerAt: now + parseInt(m[1]) * 86400000, repeat: 'none' };

    m = input.match(/^每天\s*(\d{1,2})[：:.](\d{2})$/);
    if (m) {
        const d = new Date(); d.setHours(parseInt(m[1]), parseInt(m[2]), 0, 0);
        if (d.getTime() <= now) d.setDate(d.getDate() + 1);
        return { triggerAt: d.getTime(), repeat: 'daily' };
    }

    m = input.match(/^每周([一二三四五六日天])\s*(\d{1,2})[：:.](\d{2})$/);
    if (m) {
        const targetDay = WEEKDAY_MAP[m[1]];
        const d = new Date(); d.setHours(parseInt(m[2]), parseInt(m[3]), 0, 0);
        let diff = targetDay - d.getDay();
        if (diff < 0 || (diff === 0 && d.getTime() <= now)) diff += 7;
        d.setDate(d.getDate() + diff);
        return { triggerAt: d.getTime(), repeat: `weekly:${targetDay}` };
    }

    m = input.match(/^(明天|后天)\s*(\d{1,2})[：:.](\d{2})/);
    if (m) {
        const d = new Date(); d.setDate(d.getDate() + (m[1] === '明天' ? 1 : 2));
        d.setHours(parseInt(m[2]), parseInt(m[3]), 0, 0);
        return { triggerAt: d.getTime(), repeat: 'none' };
    }

    m = input.match(/^(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[：:.](\d{2})/);
    if (m) {
        const d = new Date(); d.setMonth(parseInt(m[1]) - 1, parseInt(m[2]));
        d.setHours(parseInt(m[3]), parseInt(m[4]), 0, 0);
        if (d.getTime() <= now) d.setFullYear(d.getFullYear() + 1);
        return { triggerAt: d.getTime(), repeat: 'none' };
    }

    m = input.match(/^(\d{1,2})[：:.](\d{2})$/);
    if (m) {
        const d = new Date(); d.setHours(parseInt(m[1]), parseInt(m[2]), 0, 0);
        if (d.getTime() <= now) d.setDate(d.getDate() + 1);
        return { triggerAt: d.getTime(), repeat: 'none' };
    }

    return null;
}

// ========================
// 指令：提醒
// ========================

let cmd_alarm_set = seal.ext.newCmdItemInfo();
cmd_alarm_set.name = '提醒';
cmd_alarm_set.help = '提醒 时间 内容\n时间：X分钟后 / HH:MM / 明天HH:MM / 每天HH:MM / 每周一HH:MM';
cmd_alarm_set.solve = (ctx, msg, cmdArgs) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const raw = msg.message.replace(/^[。.]\S+\s*/, '').trim();
    if (!raw) {
        seal.replyToSender(ctx, msg,
            '格式：提醒 时间 内容\n' +
            '一次性：提醒 30分钟后 记得喝水\n' +
            '　　　  提醒 14:30 下午茶\n' +
            '　　　  提醒 明天09:00 早安\n' +
            '重复：  提醒 每天20:00 记得推日报\n' +
            '　　　  提醒 每周一09:00 周会'
        );
        return ret;
    }

    const spaceIdx = raw.search(/\s/);
    if (spaceIdx === -1) {
        seal.replyToSender(ctx, msg, '加百列需要知道你想被提醒什么……请在时间后面加上提醒内容。');
        return ret;
    }

    const timePart = raw.slice(0, spaceIdx).trim();
    const content  = raw.slice(spaceIdx).trim();
    const parsed   = parseTime(timePart);

    if (!parsed) {
        seal.replyToSender(ctx, msg, `加百列没能理解这个时间：「${timePart}」\n支持：X分钟后、X小时后、HH:MM、明天HH:MM、每天HH:MM、每周一HH:MM`);
        return ret;
    }
    if (parsed.triggerAt <= Date.now()) {
        seal.replyToSender(ctx, msg, '那个时间已经过了……可以告诉加百列另一个时间吗？');
        return ret;
    }

    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const groupId  = msg.groupId.replace(/^[a-z]+-Group:/i, '');
    const roleName = getRoleName(ctx, msg) || msg.sender.nickname || uid;
    const userKey  = `${platform}:${uid}`;

    const list = getList();
    if (list.filter(r => r.uid === uid && r.platform === platform).length >= MAX_REMINDERS_PER_USER) {
        seal.replyToSender(ctx, msg, `加百列记不了这么多了……已有 ${MAX_REMINDERS_PER_USER} 条提醒，请先删除一些旧的。`);
        return ret;
    }

    const id  = genId();
    list.push({ id, platform, uid, roleName, groupId, triggerAt: parsed.triggerAt, content, repeat: parsed.repeat });
    saveList(list);

    // 好感度：每日最多+3
    let affGainHint = '';
    if (canGainFromRemind(userKey)) {
        const newAff = addAff(userKey, 1);
        recordRemindGain(userKey);
        const lvl = getAffectionLevel(newAff);
        affGainHint = `\n（好感度 +1，当前 ${newAff}/100·${lvl.label}）`;
    }

    const aff       = getAff(userKey);
    const diff      = parsed.triggerAt - Date.now();
    const diffMin   = Math.round(diff / 60000);
    const diffHint  = diffMin < 60 ? `${diffMin} 分钟后` : `约 ${Math.floor(diffMin/60)} 小时 ${diffMin%60} 分钟后`;
    const rptHint   = parsed.repeat !== 'none' ? `\n🔁 ${repeatLabel(parsed.repeat)}重复` : '';
    const gabLine   = lineByAff('setOk', aff);

    seal.replyToSender(ctx, msg,
        `🔔 加百列记住了（${id}）\n⏰ ${formatTime(parsed.triggerAt)}（${diffHint}）${rptHint}\n📝 ${content}\n\n${gabLine}${affGainHint}`
    );
    return ret;
};
ext.cmdMap['提醒'] = cmd_alarm_set;

// ========================
// 指令：我的提醒
// ========================

let cmd_alarm_list = seal.ext.newCmdItemInfo();
cmd_alarm_list.name = '我的提醒';
cmd_alarm_list.help = '查看所有提醒';
cmd_alarm_list.solve = (ctx, msg) => {
    const ret  = seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid  = getPrimaryUid(platform, rawUid);
    const list = getList().filter(r => r.platform === platform && r.uid === uid);

    if (list.length === 0) {
        seal.replyToSender(ctx, msg, '加百列这里还没有你的提醒。\n发送「提醒 时间 内容」，我会记住的。');
        return ret;
    }

    list.sort((a, b) => a.triggerAt - b.triggerAt);
    const lines = list.map(r => {
        const rLabel = r.repeat !== 'none' ? ` 🔁${repeatLabel(r.repeat)}` : '';
        return `[${r.id}] ${formatTime(r.triggerAt)}${rLabel}\n　　${r.content}`;
    });
    seal.replyToSender(ctx, msg, `🔔 加百列记住的事（${list.length} 条）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n删除：发送「删除提醒 编号」`);
    return ret;
};
ext.cmdMap['我的提醒'] = cmd_alarm_list;

// ========================
// 指令：删除提醒
// ========================

let cmd_alarm_del = seal.ext.newCmdItemInfo();
cmd_alarm_del.name = '删除提醒';
cmd_alarm_del.help = '删除提醒 编号';
cmd_alarm_del.solve = (ctx, msg, cmdArgs) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    const id  = msg.message.replace(/^[。.]\S+\s*/, '').trim().toUpperCase();
    if (!id) {
        seal.replyToSender(ctx, msg, '格式：删除提醒 编号\n编号见「我的提醒」');
        return ret;
    }

    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const list     = getList();
    const idx      = list.findIndex(r => r.id === id && r.platform === platform && r.uid === uid);

    if (idx === -1) {
        seal.replyToSender(ctx, msg, `加百列没有找到编号「${id}」……请发送「我的提醒」确认一下。`);
        return ret;
    }

    const removed = list.splice(idx, 1)[0];
    saveList(list);
    const rptHint = removed.repeat !== 'none' ? `（${repeatLabel(removed.repeat)}重复）` : '';
    seal.replyToSender(ctx, msg, `好，加百列把「${removed.content}」${rptHint}从记忆里划掉了。`);
    return ret;
};
ext.cmdMap['删除提醒'] = cmd_alarm_del;

// ========================
// 指令：再提醒我 [X分钟]
// ========================

let cmd_alarm_snooze = seal.ext.newCmdItemInfo();
cmd_alarm_snooze.name = '再提醒我';
cmd_alarm_snooze.help = '再提醒我 [X分钟]\n延迟再提醒一次，默认 10 分钟';
cmd_alarm_snooze.solve = (ctx, msg, cmdArgs) => {
    const ret      = seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const userKey  = `${platform}:${uid}`;

    const lastFired = getLastFired();
    const last      = lastFired[userKey];
    if (!last) {
        seal.replyToSender(ctx, msg, '加百列还没有提醒过你什么……等到提醒触发后再试吧。');
        return ret;
    }

    const rawMin   = msg.message.replace(/^[。.]\S+\s*/, '').trim().replace(/分钟?$/, '');
    const delayMin = rawMin ? Math.min(Math.max(parseInt(rawMin) || 10, 1), 1440) : 10;
    const triggerAt = Date.now() + delayMin * 60000;
    const groupId   = msg.groupId.replace(/^[a-z]+-Group:/i, '');
    const roleName  = getRoleName(ctx, msg) || msg.sender.nickname || uid;

    const list = getList();
    list.push({ id: genId(), platform, uid, roleName, groupId, triggerAt, content: last.content, repeat: 'none' });
    saveList(list);

    const aff    = getAff(userKey);
    const gabLine = lineByAff('snooze', aff, delayMin);
    seal.replyToSender(ctx, msg, gabLine);
    return ret;
};
ext.cmdMap['再提醒我'] = cmd_alarm_snooze;

// ========================
// 指令：谢谢加百列
// ========================

let cmd_alarm_thanks = seal.ext.newCmdItemInfo();
cmd_alarm_thanks.name = '谢谢加百列';
cmd_alarm_thanks.help = '向加百列表示感谢，提升好感度（每天一次）';
cmd_alarm_thanks.solve = (ctx, msg) => {
    const ret      = seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const userKey  = `${platform}:${uid}`;

    const aff     = getAff(userKey);
    const gabLine = lineByAff('thanks', aff);

    if (canGainFromThanks(userKey)) {
        const newAff = addAff(userKey, 3);
        recordThanksGain(userKey);
        const lvl = getAffectionLevel(newAff);
        const lvlUp = getAffectionLevel(aff).label !== lvl.label
            ? `\n\n——好感度提升了！现在是「${lvl.label}」。`
            : '';
        seal.replyToSender(ctx, msg, `${gabLine}\n（好感度 +3，当前 ${newAff}/100·${lvl.label}）${lvlUp}`);
    } else {
        seal.replyToSender(ctx, msg, `${gabLine}\n（今天已经谢过加百列了哦～）`);
    }
    return ret;
};
ext.cmdMap['谢谢加百列'] = cmd_alarm_thanks;

// ========================
// 指令：加百列好感度
// ========================

let cmd_alarm_aff = seal.ext.newCmdItemInfo();
cmd_alarm_aff.name = '加百列好感度';
cmd_alarm_aff.help = '查看与加百列的好感度';
cmd_alarm_aff.solve = (ctx, msg) => {
    const ret      = seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const userKey  = `${platform}:${uid}`;
    const aff      = getAff(userKey);
    const lvl      = getAffectionLevel(aff);
    const catalog  = getCatalog()[userKey] || [];

    const bar = '█'.repeat(Math.floor(aff / 5)) + '░'.repeat(20 - Math.floor(aff / 5));
    seal.replyToSender(ctx, msg,
        `天使加百列\n${'─'.repeat(16)}\n好感度：${aff}/100\n${bar}\n阶段：${lvl.label}\n已获礼物：${catalog.length}/100\n\n提升好感度：每天发送「谢谢加百列」或设置提醒`
    );
    return ret;
};
ext.cmdMap['加百列好感度'] = cmd_alarm_aff;

// ========================
// 指令：加百列图鉴
// ========================

let cmd_alarm_catalog = seal.ext.newCmdItemInfo();
cmd_alarm_catalog.name = '加百列图鉴';
cmd_alarm_catalog.help = '查看从加百列处获得的礼物';
cmd_alarm_catalog.solve = (ctx, msg, cmdArgs) => {
    const ret      = seal.ext.newCmdExecuteResult(true);
    const platform = msg.platform;
    const rawUid   = msg.sender.userId.replace(/^[a-z]+:/i, '');
    const uid      = getPrimaryUid(platform, rawUid);
    const userKey  = `${platform}:${uid}`;
    const catalog  = getCatalog()[userKey] || [];
    const queryId  = msg.message.replace(/^[。.]\S+\s*/, '').trim().toUpperCase();

    if (queryId) {
        const gift = GIFT_MAP[queryId];
        if (!gift) { seal.replyToSender(ctx, msg, `没有编号为「${queryId}」的礼物。`); return ret; }
        if (!catalog.includes(queryId)) { seal.replyToSender(ctx, msg, `🔒 ${queryId}「${gift.name}」还没有获得。`); return ret; }
        seal.replyToSender(ctx, msg, `${queryId}「${gift.name}」\n${gift.content}`);
        return ret;
    }

    if (catalog.length === 0) {
        seal.replyToSender(ctx, msg, '图鉴里还空着。\n好感度达到 40 后，加百列提醒你时可能会附上礼物哦。');
        return ret;
    }

    if (catalog.length >= 100) {
        seal.replyToSender(ctx, msg, `🎊 全部 100 件礼物都收集到了！\n加百列非常高兴。`);
        return ret;
    }

    const lines = catalog.map(id => {
        const g = GIFT_MAP[id];
        return g ? `${id} 「${g.name}」` : id;
    });
    seal.replyToSender(ctx, msg, `加百列的礼物（${catalog.length}/100）\n${'─'.repeat(16)}\n${lines.join('\n')}\n\n发送「加百列图鉴 编号」查看详情`);
    return ret;
};
ext.cmdMap['加百列图鉴'] = cmd_alarm_catalog;

// ========================
// 指令：加百列帮助
// ========================

let cmd_alarm_help = seal.ext.newCmdItemInfo();
cmd_alarm_help.name = '加百列闹钟帮助';
cmd_alarm_help.help = '查看所有可用指令';
cmd_alarm_help.solve = (ctx, msg) => {
    const ret = seal.ext.newCmdExecuteResult(true);
    seal.replyToSender(ctx, msg,
        `天使加百列·指令一览\n${'─'.repeat(20)}\n` +
        `📌 提醒管理\n` +
        `  提醒 时间 内容     设置一条提醒\n` +
        `  我的提醒           查看所有提醒\n` +
        `  删除提醒 编号      删除指定提醒\n` +
        `  再提醒我 [X分钟]   延迟再提醒（默认10分钟）\n` +
        `\n` +
        `⏰ 时间格式\n` +
        `  30分钟后 / 2小时后 / 3天后\n` +
        `  14:30（今天，已过则明天）\n` +
        `  明天09:00 / 后天20:00\n` +
        `  6月15日18:00\n` +
        `  每天20:00（每日重复）\n` +
        `  每周一09:00（每周重复）\n` +
        `\n` +
        `💛 好感度\n` +
        `  谢谢加百列         感谢加百列（每天+3）\n` +
        `  加百列好感度       查看当前好感度与阶段\n` +
        `  加百列图鉴         查看已获得的礼物\n` +
        `  加百列图鉴 编号    查看指定礼物详情\n` +
        `\n` +
        `好感度 40 起，提醒触发时加百列有概率附赠礼物。\n` +
        `礼物共 100 件，全部收集可达成特别羁绊。`
    );
    return ret;
};
ext.cmdMap['加百列闹钟帮助'] = cmd_alarm_help;

// ========================
// 定时检查（每分钟一次）
// ========================

let _alarmTimer = null;

function startAlarmTimer() {
    if (_alarmTimer) clearInterval(_alarmTimer);
    _alarmTimer = setInterval(() => {
        const now  = Date.now();
        const list = getList();
        const due  = list.filter(r => r.triggerAt <= now);
        if (due.length === 0) return;

        const remaining  = list.filter(r => r.triggerAt > now);
        const lastFired  = getLastFired();
        // 提前读取，避免每条提醒各读一次存储
        const affections = getAffections();
        const catalog    = getCatalog();
        let   catalogDirty = false;

        due.forEach(r => {
            const userKey = `${r.platform}:${r.uid}`;
            const aff     = Math.min(100, Math.max(0, affections[userKey] || 0));

            if (r.repeat !== 'none') {
                const nextTs = nextTrigger(r.repeat, r.triggerAt);
                if (nextTs) remaining.push({ ...r, triggerAt: nextTs });
            }

            lastFired[userKey] = { content: r.content, groupId: r.groupId };

            const atStr    = `[CQ:at,qq=${r.uid}] `;
            const mainLine = atStr + lineByAff('remind', aff, r.roleName, r.content);
            const rptLine  = r.repeat !== 'none' ? `\n${lineByAff('repeatHint', aff)}` : '';

            // 赠礼（直接操作已提升的 catalog，循环结束后统一写回）
            let giftLine = '';
            const lvl = getAffectionLevel(aff);
            if (lvl.giftChance > 0 && Math.random() < lvl.giftChance) {
                const owned     = new Set(catalog[userKey] || []);
                const available = GABRIEL_GIFTS.filter(g => !owned.has(g.id));
                if (available.length > 0) {
                    const gift = available[Math.floor(Math.random() * available.length)];
                    if (!catalog[userKey]) catalog[userKey] = [];
                    catalog[userKey].push(gift.id);
                    catalogDirty = true;
                    giftLine = `\n\n🎁 ——对了，这个给你。\n${gift.id}「${gift.name}」\n${gift.content}\n（图鉴 ${catalog[userKey].length}/100）`;
                }
            }

            const snoozeHint = '\n\n发送「再提醒我」可延迟 10 分钟。';

            try {
                const eps = seal.getEndPoints();
                let ep = eps.find(e => e.platform === r.platform && e.state === 1);
                if (!ep) ep = eps.find(e => e.state === 1);
                if (!ep) ep = eps[0];
                if (!ep) { console.error('[长日闹钟] 找不到可用端点'); return; }
                const m = seal.newMessage();
                m.messageType = 'group';
                m.groupId     = `${r.platform}-Group:${r.groupId}`;
                const tempCtx = seal.createTempCtx(ep, m);
                seal.replyToSender(tempCtx, m, `${mainLine}${rptLine}${giftLine}${snoozeHint}`);
            } catch (e) {
                console.error('[长日闹钟] 发送提醒失败:', e);
            }
        });

        // 统一写回，减少存储序列化次数
        saveList(remaining);
        saveLastFired(lastFired);
        if (catalogDirty) saveCatalog(catalog);
    }, 60 * 1000);
}

startAlarmTimer();
