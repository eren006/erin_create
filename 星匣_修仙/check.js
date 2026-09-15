/* 校验：场景连通性 —— 所有跳转目标必须存在，且无孤岛 */
const SCENES = {};
global.S = (id, def) => { SCENES[id] = def; def.id = id; };
global.state = { flags: {}, npc: {}, items: {}, wits: 5, body: 2, mind: 60, realm: 1 };
['./src/engine.js','./src/story/prologue.js','./src/story/ch1.js','./src/story/ch2.js']
  .forEach(f => { const c = require('fs').readFileSync(f,'utf8'); eval(c); });

const targets = new Set(), bad = [];
for (const id in SCENES) {
  const sc = SCENES[id];
  const add = (t, from) => {
    if (t == null || typeof t === 'function') return;
    targets.add(t);
    if (!SCENES[t]) bad.push(from + ' → 缺失场景 ' + t);
  };
  add(sc.next, id); add(sc.to, id);
  (sc.choices || []).forEach((c, i) => {
    add(c.to, id + '.choice[' + i + ']');
    add(c.win, id + '.choice[' + i + '].win');
    add(c.lose, id + '.choice[' + i + '].lose');
    if (!c.to && !c.win && !c.roll) bad.push(id + '.choice[' + i + '] 没有去处');
  });
  if (!sc.next && !sc.to && !sc.choices && !sc.input && !sc.ending)
    bad.push(id + ' 是死胡同（无 next/choices/ending）');
}
const orphans = Object.keys(SCENES).filter(id => !targets.has(id) && id !== 'p_start');

console.log('场景总数：' + Object.keys(SCENES).length);
if (bad.length) { console.log('\n[断链]'); bad.forEach(b => console.log('  ✗ ' + b)); }
if (orphans.length) { console.log('\n[无人抵达]'); orphans.forEach(o => console.log('  ? ' + o)); }
if (!bad.length && !orphans.length) console.log('✓ 所有场景连通，无断链');
