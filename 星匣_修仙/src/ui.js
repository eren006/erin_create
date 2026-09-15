/* 《云京弃子》渲染层 */

const $scroll  = () => document.getElementById('scroll');
const $choices = () => document.getElementById('choices');
const $hud     = () => document.getElementById('hud');

let delayStep = 0;   // 当前场景内的淡入节拍

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

/** 滚到底部（元素在淡入，故多补几拍） */
function scrollToEnd() {
  [60, 260, 560].forEach(d => setTimeout(() => {
    const s = $scroll();
    s.scrollTo({ top: s.scrollHeight, behavior: 'instant' });
  }, d));
}

/** 按节拍淡入追加 */
function appear(node) {
  node.style.animationDelay = Math.min(delayStep * 0.13, 1.3) + 's';
  delayStep++;
  $scroll().appendChild(node);
  return node;
}

// ── HUD ────────────────────────────────────────────────
function updateHUD() {
  const hud = $hud();
  if (!state.name) { hud.classList.remove('on'); return; }
  hud.classList.add('on');

  const need = expNeed();
  const pct = need === Infinity ? 0 : Math.min(100, state.exp / need * 100);
  const mindWarn = state.mind < 30 ? ' warn' : '';
  const ageWarn  = state.age > lifespan() * 0.8 ? ' warn' : '';

  hud.innerHTML =
    '<div class="chapter">' + state.chapter + '</div>' +
    '<div class="row" style="margin-top:6px">' +
      '<span class="stat">境界 <b>' + realmName() + '</b></span>' +
      '<span class="stat' + ageWarn + '">年岁 <b>' + state.age + '</b> / ' + lifespan() + '</span>' +
      '<span class="stat' + mindWarn + '">心境 <b>' + state.mind + '</b></span>' +
      '<span class="stat">灵石 <b>' + state.stones + '</b></span>' +
    '</div>' +
    '<div id="expbar"><i style="width:' + pct + '%"></i></div>';
}

// ── 场景渲染 ───────────────────────────────────────────
function goto(id) {
  const sc = SCENES[id];
  if (!sc) { console.error('缺少场景：' + id); return; }

  state.scene = id;
  state.turns++;
  delayStep = 0;

  const sr = $scroll();
  sr.innerHTML = '';
  $choices().innerHTML = '';
  sr.scrollTo({ top: 0, behavior: 'instant' });

  // 进场效果
  if (sc.onEnter) {
    const deltas = applyEff(sc.onEnter);
    if (deltas.length) pendingDeltas = deltas;
  }

  if (sc.title) appear(el('div', 'scene-title', fill(sc.title)));

  // 正文
  (sc.text || []).forEach(t => {
    let cls = 'para', body = t;
    if (Array.isArray(t)) { cls = 'para ' + t[0]; body = t[1]; }
    appear(el('p', cls, fill(body)));
  });

  // 进场数值变动
  if (pendingDeltas) { showDeltas(pendingDeltas); pendingDeltas = null; }

  updateHUD();
  saveGame('auto');

  // 交互区
  if (sc.input)        renderInput(sc);
  else if (sc.choices) renderChoices(sc);
  else if (sc.next)    renderNext(sc);
  else if (sc.ending)  renderEnding(sc);
}

let pendingDeltas = null;

function showDeltas(deltas) {
  if (!deltas || !deltas.length) return;
  const html = deltas.map(d => '<span class="' + d.cls + '">' + d.txt + '</span>').join('　');
  appear(el('div', 'delta', html));
}

// ── 选项 ───────────────────────────────────────────────
function renderChoices(sc) {
  const box = $choices();
  const base = Math.min(delayStep * 0.13, 1.3) + 0.15;

  sc.choices.forEach((c, i) => {
    if (c.hide && c.hide(state)) return;             // 完全不显示
    const ok = !c.cond || c.cond(state);
    const b = el('button', 'choice' + (ok ? '' : ' locked'));
    b.innerHTML = '<span>' + fill(c.t) + '</span>' +
      (c.hint ? '<span class="hint">' + fill(c.hint) + '</span>'
              : (!ok && c.lock ? '<span class="hint">' + fill(c.lock) + '</span>' : ''));
    b.style.animationDelay = (base + i * 0.08) + 's';
    if (ok) b.onclick = () => pick(c);
    box.appendChild(b);
  });
}

function pick(c) {
  $choices().innerHTML = '';

  // 有判定：先展示明骰，再走分支
  if (c.roll) {
    const r = doRoll(c.roll);
    const parts = r.parts.map(p => p[0] + ' ' + (p[1] >= 0 ? '+' : '') + p[1]).join('　');
    appear(el('div', 'roll',
      '〔<span class="label">判定 · ' + r.label + '</span>〕难度 ' + r.dc + '<br>' +
      '底子 ' + r.base + '　' + parts + '　＝ <b>' + r.total + '</b><br>' +
      (r.win ? '<span class="win">— 成 —</span>'
             : '<span class="lose">— 败（差 ' + (r.dc - r.total) + '）—</span>')
    ));
    const branch = r.win ? c.win : c.lose;
    const eff = r.win ? c.winEff : c.loseEff;
    showDeltas(applyEff(c.eff));
    showDeltas(applyEff(eff));
    updateHUD();
    scrollToEnd();
    renderNext({ next: branch, nextLabel: '继 续' });
    return;
  }

  const deltas = applyEff(c.eff);
  showDeltas(deltas);
  updateHUD();

  if (deltas.length) {
    // 让变动被看见，再进入下一幕
    scrollToEnd();
    renderNext({ next: c.to, nextLabel: '继 续' });
  } else {
    goto(c.to);
  }
}

// ── 继续 ───────────────────────────────────────────────
function renderNext(sc) {
  const b = el('button', 'next', sc.nextLabel || '继 续');
  b.style.animationDelay = Math.min(delayStep * 0.13, 1.3) + 0.2 + 's';
  b.onclick = () => goto(typeof sc.next === 'function' ? sc.next(state) : sc.next);
  $choices().appendChild(b);
}

// ── 输入（捏人）─────────────────────────────────────────
function renderInput(sc) {
  const box = $choices();
  const wrap = el('div');
  wrap.innerHTML =
    '<input id="ipt" maxlength="' + (sc.input.max || 8) + '" placeholder="' + sc.input.ph + '" ' +
    'style="width:100%;padding:13px 14px;background:var(--paper-2);border:1px solid var(--line);' +
    'border-left:2px solid var(--gold-dim);color:var(--text);font-family:var(--serif);font-size:16px;' +
    'outline:none;border-radius:0">';
  box.appendChild(wrap);

  const b = el('button', 'next', '定 名');
  b.style.animationDelay = '0.1s';
  b.onclick = () => {
    const v = document.getElementById('ipt').value.trim();
    if (!v) { document.getElementById('ipt').focus(); return; }
    state[sc.input.key] = v;
    goto(sc.to);
  };
  box.appendChild(b);
  document.getElementById('ipt').addEventListener('keydown', e => {
    if (e.key === 'Enter') b.click();
  });
}

// ── 结局 ───────────────────────────────────────────────
function renderEnding(sc) {
  const b = el('button', 'next', '此生已尽 · 重来');
  b.style.animationDelay = Math.min(delayStep * 0.13, 1.3) + 0.4 + 's';
  b.onclick = () => location.reload();
  $choices().appendChild(b);
}

// ── 档案弹层 ───────────────────────────────────────────
function openProfile() {
  const m = document.getElementById('modal');
  const items = Object.keys(state.items).length
    ? Object.entries(state.items).map(([k, v]) => k + (v > 1 ? ' ×' + v : '')).join('、')
    : '身无长物';
  const npcs = Object.keys(state.npc).length
    ? Object.entries(state.npc).map(([k, v]) => '<div class="kv"><span>' + k + '</span>' + v + '</div>').join('')
    : '<div class="note">尚无深交之人。</div>';

  m.innerHTML =
    '<h3>生 平</h3>' +
    '<div class="kv"><span>姓名</span>' + state.name + '（' + state.gender + '）</div>' +
    '<div class="kv"><span>性情</span>' + state.nature + '</div>' +
    '<div class="kv"><span>境界</span>' + realmName() +
      (expNeed() === Infinity ? '' : '　修为 ' + state.exp + '/' + expNeed()) + '</div>' +
    '<div class="kv"><span>年岁</span>' + state.age + ' 岁　寿元 ' + lifespan() + '</div>' +
    '<div class="kv"><span>心境</span>' + state.mind + ' / 100</div>' +
    '<div class="kv"><span>悟性</span>' + witsName() + '</div>' +
    '<div class="kv"><span>体魄</span>' + bodyName() + '</div>' +
    '<div class="kv"><span>灵石</span>' + state.stones + ' 枚</div>' +
    '<div class="sect">随 身</div><div class="note">' + items + '</div>' +
    '<div class="sect">羁 绊</div>' + npcs +
    '<button class="close">合 上</button>';
  m.classList.add('on');
  m.querySelector('.close').onclick = () => m.classList.remove('on');
}

// ── 启动 ───────────────────────────────────────────────
function startNew() {
  state = S0();
  document.getElementById('title').classList.add('gone');
  goto('p_start');
}

function continueGame() {
  if (!loadGame('auto')) return;
  document.getElementById('title').classList.add('gone');
  goto(state.scene);
}

window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-new').onclick = startNew;
  const bc = document.getElementById('btn-continue');
  if (hasSave('auto')) bc.onclick = continueGame;
  else bc.disabled = true;
  document.getElementById('btn-profile').onclick = openProfile;
});
