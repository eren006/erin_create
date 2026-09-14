const doc = document;
const body = doc.body;
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
const prefs = {
  motion: localStorage.getItem('jx-motion') !== 'off' && !reduced,
  sound: localStorage.getItem('jx-sound') === 'on',
  theme: localStorage.getItem('jx-theme') || 'jiuxiao'
};

const themeLabels = {jiuxiao:'九霄夜', qinglan:'青岚', chixia:'赤霞', yunque:'云阙'};
function applyTheme(theme = 'jiuxiao') {
  prefs.theme = themeLabels[theme] ? theme : 'jiuxiao';
  body.dataset.theme = prefs.theme;
  localStorage.setItem('jx-theme', prefs.theme);
  doc.querySelectorAll('.theme-option').forEach(option => {
    const active = option.dataset.theme === prefs.theme;
    option.classList.toggle('active', active);
    option.setAttribute('aria-pressed', String(active));
  });
  const current = doc.querySelector('#theme-current');
  if (current) current.textContent = themeLabels[prefs.theme];
}

function applyPrefs() {
  body.classList.toggle('motion-on', prefs.motion);
  body.classList.toggle('motion-off', !prefs.motion);
  const motionBtn = doc.querySelector('#motion-toggle');
  const soundBtn = doc.querySelector('#sound-toggle');
  if (motionBtn) { motionBtn.textContent = prefs.motion ? '动' : '止'; motionBtn.title = prefs.motion ? '关闭动效' : '开启动效'; }
  if (soundBtn) { soundBtn.textContent = prefs.sound ? '音' : '静'; soundBtn.title = prefs.sound ? '关闭音效' : '开启音效'; }
}
applyPrefs();
applyTheme(prefs.theme);

const themePicker = doc.querySelector('#theme-picker');
const themeToggle = doc.querySelector('#theme-toggle');
function setThemePicker(open) {
  if (!themePicker || !themeToggle) return;
  themePicker.classList.toggle('open', open);
  themePicker.setAttribute('aria-hidden', String(!open));
  themeToggle.setAttribute('aria-expanded', String(open));
}
themeToggle?.addEventListener('click', event => { event.stopPropagation(); setThemePicker(!themePicker.classList.contains('open')); });
doc.querySelectorAll('.theme-option').forEach(option => option.addEventListener('click', () => {
  applyTheme(option.dataset.theme);
  playTone('open');
  setThemePicker(false);
}));
doc.addEventListener('click', event => { if (themePicker?.classList.contains('open') && !themePicker.contains(event.target)) setThemePicker(false); });

const mobileMore = doc.querySelector('#mobile-more-panel');
const mobileMoreToggle = doc.querySelector('#mobile-more-toggle');
const mobileMoreBackdrop = doc.querySelector('#mobile-more-backdrop');
function setMobileMore(open) {
  if (!mobileMore || !mobileMoreToggle) return;
  mobileMore.classList.toggle('open', open);
  mobileMoreBackdrop?.classList.toggle('open', open);
  mobileMore.setAttribute('aria-hidden', String(!open));
  mobileMoreToggle.setAttribute('aria-expanded', String(open));
  body.style.overflow = open ? 'hidden' : '';
  if (open) doc.querySelector('#mobile-more-close')?.focus();
}
mobileMoreToggle?.addEventListener('click', () => setMobileMore(!mobileMore.classList.contains('open')));
doc.querySelector('#mobile-more-close')?.addEventListener('click', () => setMobileMore(false));
mobileMoreBackdrop?.addEventListener('click', () => setMobileMore(false));

doc.querySelectorAll('.nav-more').forEach(menu => {
  doc.addEventListener('click', event => { if (menu.open && !menu.contains(event.target)) menu.removeAttribute('open'); });
});

const confirmModal = doc.querySelector('#confirm-modal');
const confirmTitle = doc.querySelector('#confirm-title');
const confirmMessage = doc.querySelector('#confirm-message');
const confirmWarning = doc.querySelector('#confirm-warning');
const confirmSubmit = doc.querySelector('#confirm-submit');
let pendingConfirmForm = null;
let pendingConfirmSubmitter = null;
let confirmReturnFocus = null;
function closeConfirm(restoreFocus = true) {
  if (!confirmModal) return;
  confirmModal.classList.remove('open', 'danger');
  confirmModal.setAttribute('aria-hidden', 'true');
  body.style.overflow = '';
  pendingConfirmForm = null;
  pendingConfirmSubmitter = null;
  if (restoreFocus) confirmReturnFocus?.focus();
}
function openConfirm(form, submitter) {
  if (!confirmModal) return;
  pendingConfirmForm = form;
  pendingConfirmSubmitter = submitter;
  confirmReturnFocus = submitter || doc.activeElement;
  confirmTitle.textContent = form.dataset.confirmTitle || '请再确认';
  confirmMessage.textContent = form.dataset.confirmMessage || '此操作将立即生效。';
  confirmWarning.textContent = form.dataset.confirmWarning || '操作提交后将立即生效，请确认资源消耗与后果。';
  confirmSubmit.textContent = form.dataset.confirmButton || '确认继续';
  confirmModal.classList.toggle('danger', form.dataset.confirmTone === 'danger');
  confirmModal.classList.add('open');
  confirmModal.setAttribute('aria-hidden', 'false');
  body.style.overflow = 'hidden';
  doc.querySelector('#confirm-cancel')?.focus();
}
doc.addEventListener('submit', event => {
  const form = event.target.closest?.('form[data-confirm-message]');
  if (!form) return;
  if (form.dataset.confirmApproved === 'true') {
    delete form.dataset.confirmApproved;
    return;
  }
  event.preventDefault();
  openConfirm(form, event.submitter);
});
doc.querySelector('#confirm-cancel')?.addEventListener('click', () => closeConfirm());
confirmModal?.addEventListener('click', event => { if (event.target === confirmModal) closeConfirm(); });
confirmSubmit?.addEventListener('click', () => {
  const form = pendingConfirmForm;
  const submitter = pendingConfirmSubmitter;
  if (!form) return;
  form.dataset.confirmApproved = 'true';
  closeConfirm(false);
  form.requestSubmit(submitter || undefined);
});
confirmModal?.addEventListener('keydown', event => {
  if (event.key !== 'Tab') return;
  const focusable = [...confirmModal.querySelectorAll('button:not(:disabled)')];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && doc.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && doc.activeElement === last) { event.preventDefault(); first.focus(); }
});

const equipmentTabs = [...doc.querySelectorAll('[data-equipment-tab]')];
const equipmentPanels = [...doc.querySelectorAll('[data-equipment-panel]')];
function setEquipmentTab(tab, updateHash = true) {
  if (!equipmentTabs.length || !equipmentTabs.some(button => button.dataset.equipmentTab === tab)) return;
  equipmentTabs.forEach(button => {
    const active = button.dataset.equipmentTab === tab;
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  equipmentPanels.forEach(panel => { panel.hidden = panel.dataset.equipmentPanel !== tab; });
  localStorage.setItem('jx-equipment-tab', tab);
  if (updateHash) history.replaceState(null, '', `#${tab}`);
}
if (equipmentTabs.length) {
  const hashTab = location.hash.slice(1);
  const initialTab = equipmentTabs.some(button => button.dataset.equipmentTab === hashTab)
    ? hashTab : localStorage.getItem('jx-equipment-tab') || 'loadout';
  setEquipmentTab(initialTab, false);
  equipmentTabs.forEach((button, index) => {
    button.addEventListener('click', () => setEquipmentTab(button.dataset.equipmentTab));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let next = event.key === 'Home' ? 0 : event.key === 'End' ? equipmentTabs.length - 1
        : (index + (event.key === 'ArrowRight' ? 1 : -1) + equipmentTabs.length) % equipmentTabs.length;
      setEquipmentTab(equipmentTabs[next].dataset.equipmentTab);
      equipmentTabs[next].focus();
    });
  });
  doc.querySelectorAll('[data-open-equipment-tab]').forEach(button => button.addEventListener('click', () => {
    const tab = button.dataset.openEquipmentTab;
    setEquipmentTab(tab);
    equipmentTabs.find(item => item.dataset.equipmentTab === tab)?.focus();
  }));
}

const bagTabs = [...doc.querySelectorAll('[data-bag-tab]')];
const bagItems = [...doc.querySelectorAll('[data-bag-kind]')];
function setBagTab(kind) {
  bagTabs.forEach(button => button.setAttribute('aria-selected', String(button.dataset.bagTab === kind)));
  bagItems.forEach(item => { item.hidden = kind !== 'all' && item.dataset.bagKind !== kind; });
}
bagTabs.forEach(button => button.addEventListener('click', () => setBagTab(button.dataset.bagTab)));

doc.querySelector('#motion-toggle')?.addEventListener('click', () => {
  prefs.motion = !prefs.motion;
  localStorage.setItem('jx-motion', prefs.motion ? 'on' : 'off');
  applyPrefs();
});
doc.querySelector('#sound-toggle')?.addEventListener('click', () => {
  prefs.sound = !prefs.sound;
  localStorage.setItem('jx-sound', prefs.sound ? 'on' : 'off');
  applyPrefs();
  if (prefs.sound) playTone('open');
});

let audioContext;
function playTone(kind = 'success') {
  if (!prefs.sound) return;
  audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
  const now = audioContext.currentTime;
  const notes = kind === 'rare' ? [392, 523.25, 659.25, 783.99] : kind === 'error' ? [220, 164.81] : [329.63, 440, 523.25];
  notes.forEach((frequency, i) => {
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = kind === 'rare' ? 'sine' : 'triangle';
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(0, now + i * .07);
    gain.gain.linearRampToValueAtTime(.055, now + i * .07 + .018);
    gain.gain.exponentialRampToValueAtTime(.001, now + i * .07 + .42);
    osc.connect(gain).connect(audioContext.destination);
    osc.start(now + i * .07); osc.stop(now + i * .07 + .45);
  });
}

const canvas = doc.querySelector('#qi-canvas');
const orbit = doc.querySelector('#realm-orbit');
let ctx, particles = [], frame;
function sizeCanvas() {
  if (!canvas) return;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  canvas.width = 220 * dpr; canvas.height = 220 * dpr;
  ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function seedParticles(count = 28) {
  particles = Array.from({length: count}, () => ({
    angle: Math.random() * Math.PI * 2, radius: 48 + Math.random() * 50,
    speed: .002 + Math.random() * .006, size: .7 + Math.random() * 1.8,
    alpha: .25 + Math.random() * .65, hue: Math.random() > .35 ? 43 : 270
  }));
}
function drawParticles() {
  if (!canvas || !ctx) return;
  ctx.clearRect(0, 0, 220, 220);
  if (prefs.motion) particles.forEach(p => {
    p.angle += p.speed;
    const wobble = Math.sin(p.angle * 3) * 5;
    const x = 110 + Math.cos(p.angle) * (p.radius + wobble);
    const y = 110 + Math.sin(p.angle) * p.radius * .66;
    ctx.beginPath(); ctx.arc(x, y, p.size, 0, Math.PI * 2);
    ctx.fillStyle = p.hue === 43 ? `rgba(255,220,145,${p.alpha})` : `rgba(178,143,245,${p.alpha})`;
    ctx.shadowBlur = 9; ctx.shadowColor = ctx.fillStyle; ctx.fill();
  });
  frame = requestAnimationFrame(drawParticles);
}
if (canvas) { sizeCanvas(); seedParticles(); drawParticles(); }

function animateNumber(el, target) {
  const start = Number((el.textContent || '').replace(/[^0-9.-]/g, '')) || 0;
  const duration = prefs.motion ? 650 : 0;
  const begun = performance.now();
  const tick = now => {
    const t = duration ? Math.min(1, (now - begun) / duration) : 1;
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = String(Math.round(start + (target - start) * eased));
    if (t < 1) requestAnimationFrame(tick); else { el.classList.add('value-bump'); setTimeout(() => el.classList.remove('value-bump'), 650); }
  };
  requestAnimationFrame(tick);
}
function updateStats(stats = {}) {
  for (const [key, value] of Object.entries(stats)) {
    if (typeof value === 'number') doc.querySelectorAll(`[data-stat="${key}"]`).forEach(el => animateNumber(el, value));
  }
  if (stats.realm) doc.querySelectorAll('[data-stat-text="realm"]').forEach(el => el.textContent = stats.realm);
  if (Number.isFinite(stats.stamina)) doc.querySelectorAll('[data-bar="stamina"]').forEach(el => el.style.width = `${Math.min(100, stats.stamina / Number(el.dataset.max || 100) * 100)}%`);
  if (Number.isFinite(stats.mind)) doc.querySelectorAll('[data-bar="mind"]').forEach(el => el.style.width = `${stats.mind}%`);
  if (Number.isFinite(stats.realm_progress)) doc.querySelectorAll('[data-bar="realm"]').forEach(el => el.style.width = `${stats.realm_progress}%`);
}

function floatingGain(text) {
  if (!prefs.motion || !orbit) return;
  const rect = orbit.getBoundingClientRect();
  const el = doc.createElement('div'); el.className = 'float-gain'; el.textContent = text;
  el.style.left = `${rect.left + rect.width / 2 - 25 + (Math.random() - .5) * 70}px`;
  el.style.top = `${rect.top + rect.height / 2}px`; body.append(el); setTimeout(() => el.remove(), 1400);
}
function showResult(data) {
  const modal = doc.querySelector('#game-result-modal'); if (!modal) return;
  modal.classList.toggle('rare', !!data.rare);
  doc.querySelector('#result-title').textContent = data.kind === 'error' ? '灵息未平' : data.rare ? (data.breakthrough ? '破境成功' : data.epiphany ? '顿悟降临' : '机缘显现') : data.kind === 'rest' ? '调息圆满' : '修行有成';
  doc.querySelector('#result-message').textContent = data.message || '';
  const gains = doc.querySelector('#result-gains'); gains.innerHTML = '';
  const labels = {exp:'修为', contribution:'贡献', mind:'心境', stamina:'体力'};
  Object.entries(data.gained || {}).forEach(([key, value]) => {
    if (!value) return; const pill = doc.createElement('span'); pill.className = 'gain-pill'; pill.textContent = `${labels[key] || key} ${value > 0 ? '+' : ''}${value}`; gains.append(pill);
  });
  modal.classList.add('open');
  if (data.rare && prefs.motion) { const flash = doc.createElement('div'); flash.className = 'rare-flash'; body.append(flash); setTimeout(() => flash.remove(), 1200); }
  playTone(data.rare ? 'rare' : 'success');
}
function closeResult() { doc.querySelector('#game-result-modal')?.classList.remove('open', 'rare'); }
doc.querySelector('#result-close')?.addEventListener('click', closeResult);
doc.querySelector('#game-result-modal')?.addEventListener('click', e => { if (e.target.id === 'game-result-modal') closeResult(); });
addEventListener('keydown', e => { if (e.key === 'Escape') { closeResult(); closeConfirm(); setMobileMore(false); setThemePicker(false); } });

const cooldowns = new Map();
function startCooldown(baseSeconds) {
  doc.querySelectorAll('.js-cultivate').forEach(form => {
    const button = form.querySelector('button'); const mult = Number(form.dataset.cooldownMult || 1);
    cooldowns.set(button, Date.now() + baseSeconds * mult * 1000);
  });
}
function resumeCooldown(remainingBaseSeconds) {
  if (!remainingBaseSeconds) return;
  startCooldown(remainingBaseSeconds);
}
function setButtonCooldown(button, seconds) {
  if (button) cooldowns.set(button, Date.now() + seconds * 1000);
}
setInterval(() => cooldowns.forEach((end, button) => {
  const remaining = Math.max(0, Math.ceil((end - Date.now()) / 1000));
  if (remaining) { button.disabled = true; button.textContent = `调息中 · ${remaining}s`; }
  else { button.disabled = false; button.textContent = button.dataset.label || '打坐'; cooldowns.delete(button); }
}), 250);

doc.querySelectorAll('.js-game-action').forEach(form => form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button'); if (!button || button.disabled) return;
  const oldText = button.textContent; button.disabled = true; button.textContent = form.dataset.action === 'cultivate' ? '引气入体…' : '调息养神…';
  orbit?.classList.add('is-channeling'); playTone('open');
  try {
    const response = await fetch(form.action, {method:'POST', body:new FormData(form), headers:{Accept:'application/json', 'X-Requested-With':'fetch'}});
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (data.cooldown_remaining) setButtonCooldown(button, data.cooldown_remaining);
      showResult({kind:'error', message:data.message || '灵息紊乱，请稍后再试', gained:{}}); playTone('error'); return;
    }
    updateStats(data.stats); showResult(data);
    if (data.kind === 'cultivate') {
      startCooldown(data.cooldown_base || 5);
      floatingGain(`修为 +${data.gained?.exp || 0}`);
      if (data.gained?.contribution) setTimeout(() => floatingGain(`贡献 +${data.gained.contribution}`), 160);
      orbit?.classList.add(data.rare ? 'is-rare' : 'is-channeling');
    } else { button.disabled = false; button.textContent = oldText; }
  } catch (error) {
    showResult({kind:'error', message:'灵讯暂时中断，已保留原有操作方式，请刷新后重试', gained:{}}); playTone('error');
    button.disabled = false; button.textContent = oldText;
  } finally {
    setTimeout(() => orbit?.classList.remove('is-channeling', 'is-rare'), 1900);
  }
}));

window.showResult = showResult;
window.resumeCooldown = resumeCooldown;
