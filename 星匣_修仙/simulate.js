/* 无 DOM 模拟：随机走完全程，验证无死循环、数值合理 */
const fs = require('fs');
const src = ['./src/engine.js','./src/story/prologue.js','./src/story/ch1.js','./src/story/ch2.js']
  .map(f => fs.readFileSync(f, 'utf8')).join('\n');

const body = `
function run() {
  state = S0(); state.name = '苏铁'; state.gender = '男';
  let id = 'p_start', steps = 0, path = [];
  while (steps++ < 300) {
    const sc = SCENES[id];
    if (!sc) return { err: '缺失场景 ' + id, path: path.slice(-5) };
    path.push(id);
    if (sc.ending) return { ok: true, steps, end: id,
      realm: realmName(), age: state.age, mind: state.mind,
      stones: state.stones, exp: state.exp, npc: state.npc,
      flags: Object.keys(state.flags).length };
    if (sc.onEnter) applyEff(sc.onEnter);
    if (sc.input) { id = sc.to; continue; }
    if (sc.choices) {
      const ok = sc.choices.filter(c => (!c.cond || c.cond(state)) && !(c.hide && c.hide(state)));
      if (!ok.length) return { err: '无可选项 ' + id };
      const c = ok[Math.floor(Math.random() * ok.length)];
      if (c.roll) {
        const r = doRoll(c.roll);
        applyEff(c.eff); applyEff(r.win ? c.winEff : c.loseEff);
        id = r.win ? c.win : c.lose;
      } else { applyEff(c.eff); id = c.to; }
      continue;
    }
    if (sc.next) { id = typeof sc.next === 'function' ? sc.next(state) : sc.next; continue; }
    return { err: '死胡同 ' + id };
  }
  return { err: '疑似死循环', path: path.slice(-12) };
}

let bad = 0; const rows = [];
for (let i = 0; i < 400; i++) {
  const r = run();
  if (r.err) { bad++; if (bad <= 3) console.log('✗', r.err, r.path || ''); }
  else rows.push(r);
}
console.log('通关 ' + rows.length + ' / 400 ，失败 ' + bad);
if (rows.length) {
  const avg = k => (rows.reduce((a,b)=>a+b[k],0)/rows.length).toFixed(1);
  const rng = k => Math.min(...rows.map(r=>r[k])) + ' ~ ' + Math.max(...rows.map(r=>r[k]));
  console.log('步数   平均 ' + avg('steps') + '　区间 ' + rng('steps'));
  console.log('年岁   平均 ' + avg('age')   + '　区间 ' + rng('age'));
  console.log('心境   平均 ' + avg('mind')  + '　区间 ' + rng('mind'));
  console.log('修为   平均 ' + avg('exp')   + '　区间 ' + rng('exp'));
  console.log('灵石   平均 ' + avg('stones')+ '　区间 ' + rng('stones'));
  const realms = {}; rows.forEach(r => realms[r.realm] = (realms[r.realm]||0)+1);
  console.log('终局境界：', realms);
  const mindLow = rows.filter(r => r.mind < 20).length;
  console.log('心境跌破 20 的比例：' + (mindLow / rows.length * 100).toFixed(1) + '%');
}
`;
eval(src + body);
