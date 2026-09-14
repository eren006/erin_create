/* Keep the silk's gentle flex in sync with the shared motion controls. */
(() => {
  const stage = document.querySelector('.ink-stage');
  const displacement = document.querySelector('[data-silk-displace]');
  const offset = document.querySelector('[data-silk-offset]');
  if (!stage || !displacement || !offset) return;
  const preference = matchMedia('(prefers-reduced-motion: no-preference)');
  let frame = 0, previous = 0, elapsed = 0, lastPaint = 0;
  function allowed() {
    return preference.matches && !document.hidden && document.documentElement.dataset.theme === 'ballet' &&
      stage.classList.contains('motion-enabled') && !stage.classList.contains('motion-paused');
  }
  function draw(now) {
    frame = 0;
    if (!allowed()) { previous = 0; return; }
    if (previous) elapsed += Math.min(now - previous, 50);
    previous = now;
    if (now - lastPaint > 40) {
      const phase = elapsed / 2400;
      offset.setAttribute('dy', (Math.sin(phase) * 12).toFixed(2));
      displacement.setAttribute('scale', (4 + Math.sin(phase * .8) * 2).toFixed(2));
      lastPaint = now;
    }
    frame = requestAnimationFrame(draw);
  }
  function sync() {
    if (!allowed()) { cancelAnimationFrame(frame); frame = 0; previous = 0; }
    else if (!frame) frame = requestAnimationFrame(draw);
  }
  new MutationObserver(sync).observe(stage, {attributes:true, attributeFilter:['class']});
  new MutationObserver(sync).observe(document.documentElement, {attributes:true, attributeFilter:['data-theme']});
  preference.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
  sync();
})();
