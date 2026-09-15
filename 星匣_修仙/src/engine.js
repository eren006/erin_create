/* 《云京弃子》引擎 —— 场景机 / 数值 / 判定 / 存档 */

// ── 境界阶梯 ───────────────────────────────────────────
// exp 为「升入下一境所需」。凡人段不修炼，故为 Infinity（须由剧情推进）。
const REALMS = [
  { n: '凡人',     need: Infinity, life: 80  },
  { n: '炼气一层', need: 100,  life: 120 },
  { n: '炼气二层', need: 160,  life: 120 },
  { n: '炼气三层', need: 240,  life: 120 },
  { n: '炼气四层', need: 360,  life: 120 },
  { n: '炼气五层', need: 520,  life: 120 },
  { n: '炼气六层', need: 740,  life: 120 },
  { n: '炼气七层', need: 1040, life: 120 },
  { n: '炼气八层', need: 1450, life: 120 },
  { n: '炼气九层', need: 2000, life: 120 },
  { n: '筑基初期', need: 3200, life: 200 },
  { n: '筑基中期', need: 4800, life: 200 },
  { n: '筑基后期', need: 7000, life: 200 },
  { n: '金丹初期', need: 12000, life: 500 },
  { n: '金丹中期', need: 18000, life: 500 },
  { n: '金丹后期', need: 26000, life: 500 },
  { n: '元婴初期', need: 45000, life: 1000 },
  { n: '元婴中期', need: 66000, life: 1000 },
  { n: '元婴后期', need: 95000, life: 1000 },
  { n: '化神',     need: 180000, life: 2000 },
  { n: '合体',     need: 400000, life: 5000 },
  { n: '大乘',     need: Infinity, life: 10000 },
];

const GRADES = ['丁下','丁上','丙下','丙上','乙下','乙上','甲下','甲上'];

// ── 状态 ───────────────────────────────────────────────
const S0 = () => ({
  name: '', gender: '', nature: '',
  realm: 0, exp: 0,
  age: 16, months: 0,          // months = 当年内累计月数
  mind: 60,
  wits: 5, body: 2,            // GRADES 下标
  stones: 0,
  items: {}, npc: {}, flags: {},
  chapter: '楔子', scene: 'p_start',
  turns: 0, log: [],
});

let state = S0();
const SCENES = {};

/** 注册场景 */
function S(id, def) { SCENES[id] = def; def.id = id; }

// ── 取值助手 ───────────────────────────────────────────
const realmName = () => REALMS[state.realm].n;
const lifespan   = () => REALMS[state.realm].life;
const expNeed    = () => REALMS[state.realm].need;
const witsName   = () => GRADES[state.wits];
const bodyName   = () => GRADES[state.body];
const has        = (k, n = 1) => (state.items[k] || 0) >= n;
const fav        = (k) => state.npc[k] || 0;
const flag       = (k) => !!state.flags[k];

/** 文本插值：{name} {realm} {ta}（他/她） */
function fill(t) {
  if (typeof t === 'function') t = t(state);
  return String(t)
    .replace(/\{name\}/g, state.name || '你')
    .replace(/\{realm\}/g, realmName())
    .replace(/\{ta\}/g, state.gender === '女' ? '她' : '他')
    .replace(/\{xiong\}/g, state.gender === '女' ? '姑娘' : '小子');
}

// ── 效果结算 ───────────────────────────────────────────
// eff: { exp, mind, stones, age(月), wits, body, items:{}, npc:{}, flags:{}, realm:+1 }
// 返回可展示的变动列表 [{txt, cls}]
function applyEff(eff) {
  if (!eff) return [];
  if (typeof eff === 'function') eff = eff(state) || {};
  const out = [];
  const push = (txt, cls) => out.push({ txt, cls });

  if (eff.months) {
    state.months += eff.months;
    while (state.months >= 12) { state.months -= 12; state.age++; }
  }
  if (eff.exp) {
    state.exp += eff.exp;
    push(`修为 ${eff.exp > 0 ? '+' : ''}${eff.exp}`, eff.exp > 0 ? 'up' : 'down');
    // 自动进阶：仅炼气段内自动，大境界须走剧情/闭关
    while (state.exp >= expNeed() && REALMS[state.realm + 1] && !REALMS[state.realm + 1].n.startsWith('筑基')) {
      state.exp -= expNeed();
      state.realm++;
      push(`境界提升 —— ${realmName()}`, 'item');
    }
  }
  if (eff.mind) {
    state.mind = Math.max(0, Math.min(100, state.mind + eff.mind));
    push(`心境 ${eff.mind > 0 ? '+' : ''}${eff.mind}`, eff.mind > 0 ? 'up' : 'down');
  }
  if (eff.stones) {
    state.stones = Math.max(0, state.stones + eff.stones);
    push(`灵石 ${eff.stones > 0 ? '+' : ''}${eff.stones}`, eff.stones > 0 ? 'up' : 'down');
  }
  if (eff.wits) { state.wits = Math.min(GRADES.length - 1, state.wits + eff.wits); push(`悟性 → ${witsName()}`, 'up'); }
  if (eff.body) { state.body = Math.min(GRADES.length - 1, state.body + eff.body); push(`体魄 → ${bodyName()}`, 'up'); }
  if (eff.realm) { state.realm += eff.realm; state.exp = 0; push(`境界提升 —— ${realmName()}`, 'item'); }

  for (const k in eff.items || {}) {
    const n = eff.items[k];
    state.items[k] = (state.items[k] || 0) + n;
    if (state.items[k] <= 0) { delete state.items[k]; push(`失去 ${k}`, 'down'); }
    else push(n > 0 ? `获得 ${k}` : `失去 ${k}`, n > 0 ? 'item' : 'down');
  }
  for (const k in eff.npc || {}) {
    const n = eff.npc[k];
    if (!n) continue;
    state.npc[k] = (state.npc[k] || 0) + n;
    push(`${k} ${n > 0 ? '好感+' : '好感'}${n}`, n > 0 ? 'up' : 'down');
  }
  for (const k in eff.flags || {}) state.flags[k] = eff.flags[k];
  if (eff.chapter) state.chapter = eff.chapter;

  return out;
}

// ── 判定 ───────────────────────────────────────────────
// roll: { label, dc, base:(s)=>num, bonus:[[名,值]|(s)=>[名,值]|null] }
// 明骰：过程全部展示给玩家
function doRoll(r) {
  const base = typeof r.base === 'function' ? r.base(state) : (r.base || 0);
  const parts = [];
  let total = base;
  (r.bonus || []).forEach(b => {
    const item = typeof b === 'function' ? b(state) : b;
    if (!item) return;
    const [label, val] = item;
    if (!val) return;
    total += val;
    parts.push([label, val]);
  });
  const luck = 1 + Math.floor(Math.random() * 20);   // 天意 1–20
  total += luck;
  parts.push(['天意', luck]);
  return { dc: r.dc, base, parts, total, win: total >= r.dc, label: r.label };
}

// ── 存档 ───────────────────────────────────────────────
const SAVE_KEY = 'yunjing_qizi_save_v1';

function saveGame(slot = 'auto') {
  try {
    const all = JSON.parse(localStorage.getItem(SAVE_KEY) || '{}');
    all[slot] = { s: state, t: Date.now() };
    localStorage.setItem(SAVE_KEY, JSON.stringify(all));
    return true;
  } catch (e) { return false; }
}

function loadGame(slot = 'auto') {
  try {
    const all = JSON.parse(localStorage.getItem(SAVE_KEY) || '{}');
    if (!all[slot]) return false;
    state = Object.assign(S0(), all[slot].s);
    return true;
  } catch (e) { return false; }
}

function hasSave(slot = 'auto') {
  try {
    const all = JSON.parse(localStorage.getItem(SAVE_KEY) || '{}');
    return !!all[slot];
  } catch (e) { return false; }
}
