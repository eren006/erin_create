/* Local, fixed-step circle physics. No remote assets or runtime dependencies. */
(function (root) {
  'use strict';
  var FRUITS = ['🍒', '🍓', '🍇', '🍋', '🍊', '🍎', '🍐', '🍑', '🍍', '🍈', '🍉'];
  var RADII = [12, 16, 21, 26, 31, 37, 43, 49, 56, 64, 73];
  function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }
  function World(random) { this.random = random || Math.random; this.reset(); }
  World.prototype.reset = function () {
    this.balls = []; this.score = 0; this.time = 0; this.cooldown = 0;
    this.danger = 0; this.over = false; this.watermelons = 0;
    this.current = this.roll(); this.next = this.roll();
  };
  World.prototype.roll = function () { return Math.min(4, Math.floor(this.random() * 5)); };
  World.prototype.add = function (level, x, y) {
    var ball = { level: level, r: RADII[level], x: x, y: y, vx: 0, vy: 0, born: this.time };
    this.balls.push(ball); return ball;
  };
  World.prototype.drop = function (x) {
    if (this.over || this.cooldown > 0) return false;
    var r = RADII[this.current];
    this.add(this.current, clamp(x, r + 2, 358 - r), 32);
    this.current = this.next; this.next = this.roll(); this.cooldown = .65;
    return true;
  };
  World.prototype.bounds = function (b) {
    if (b.x < b.r + 2) { b.x = b.r + 2; b.vx = Math.abs(b.vx) * .15; }
    if (b.x > 358 - b.r) { b.x = 358 - b.r; b.vx = -Math.abs(b.vx) * .15; }
    if (b.y > 478 - b.r) { b.y = 478 - b.r; b.vy = b.vy > 25 ? -b.vy * .12 : 0; b.vx *= .94; }
  };
  World.prototype.step = function (dt) {
    if (this.over) return;
    this.time += dt; this.cooldown = Math.max(0, this.cooldown - dt);
    var self = this;
    this.balls.forEach(function (b) {
      b.vy = Math.min(520, b.vy + 760 * dt); b.vx *= .998;
      b.x += b.vx * dt; b.y += b.vy * dt; self.bounds(b);
    });
    // Several contact passes keep piles stable, even on a slow display.
    for (var pass = 0; pass < 6; pass++) {
      for (var i = 0; i < this.balls.length; i++) {
        var a = this.balls[i];
        for (var j = i + 1; j < this.balls.length; j++) {
          var b = this.balls[j], dx = b.x - a.x, dy = b.y - a.y;
          var dist = Math.hypot(dx, dy), contact = a.r + b.r;
          if (dist > contact) continue;
          if (a.level === b.level && a.level < RADII.length - 1) {
            var level = a.level + 1, x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
            var vx = (a.vx + b.vx) / 2, vy = (a.vy + b.vy) / 2;
            this.balls.splice(j, 1); this.balls.splice(i, 1);
            var merged = this.add(level, x, y); merged.vx = vx; merged.vy = vy;
            this.bounds(merged); this.score += (level + 1) * (level + 1);
            if (level === RADII.length - 1) this.watermelons++;
            i--; break;
          }
          var nx = dist > .001 ? dx / dist : 1, ny = dist > .001 ? dy / dist : 0;
          var ia = 1 / (a.r * a.r), ib = 1 / (b.r * b.r), sum = ia + ib;
          var push = Math.max(0, contact - dist - .02) * .85;
          a.x -= nx * push * ia / sum; a.y -= ny * push * ia / sum;
          b.x += nx * push * ib / sum; b.y += ny * push * ib / sum;
          var speed = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
          if (speed < 0) {
            var impulse = -speed * 1.08 / sum;
            a.vx -= impulse * nx * ia; a.vy -= impulse * ny * ia;
            b.vx += impulse * nx * ib; b.vy += impulse * ny * ib;
          }
        }
      }
      this.balls.forEach(function (b) { self.bounds(b); });
    }
    var high = this.balls.some(function (b) { return self.time - b.born > 1.3 && b.y - b.r < 76; });
    this.danger = high ? this.danger + dt : 0;
    if (this.danger >= 2) this.over = true;
  };

  function mount(options) {
    var board = options.board, cv = document.createElement('canvas');
    cv.className = 'gm-canvas'; cv.tabIndex = 0; cv.setAttribute('role', 'button');
    cv.setAttribute('aria-label', '拖动顶部水果，松手丢下'); cv.setAttribute('aria-describedby', 'wmGuide');
    board.insertBefore(cv, options.over);
    var ctx = cv.getContext('2d'), world = new World(), active = false, paused = false;
    var pauseButton = document.getElementById('wmPause'), endButton = document.getElementById('wmEnd');
    var nextEl = document.getElementById('wmNext'), status = document.getElementById('wmStatus');
    var x = 180, frame = 0, last = 0, accumulator = 0, pointer = null, seenScore = -1, colors = {};
    function palette() {
      var source = getComputedStyle(document.querySelector('.phone'));
      ['--bg', '--theirs', '--text', '--muted', '--line', '--gift-bg', '--gift-line'].forEach(function (key) {
        // Resolve color-mix and variable references before passing them to canvas.
        cv.style.color = source.getPropertyValue(key); colors[key] = getComputedStyle(cv).color;
      });
    }
    function resize() {
      var ratio = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = Math.round(360 * ratio); cv.height = Math.round(480 * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0); palette(); draw();
    }
    function fruit(level, px, py, alpha) {
      var r = RADII[level]; ctx.globalAlpha = alpha;
      ctx.fillStyle = level % 2 ? colors['--gift-bg'] : colors['--bg'];
      ctx.strokeStyle = colors['--gift-line']; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.font = Math.round(r * 1.5) + 'px "Apple Color Emoji", "Segoe UI Emoji", sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = colors['--text'];
      ctx.fillText(FRUITS[level], px, py + 1); ctx.globalAlpha = 1;
    }
    function draw() {
      ctx.clearRect(0, 0, 360, 480); ctx.fillStyle = colors['--theirs']; ctx.fillRect(0, 0, 360, 480);
      ctx.strokeStyle = world.danger ? colors['--text'] : colors['--muted']; ctx.lineWidth = world.danger ? 2 : 1;
      ctx.setLineDash([5, 6]); ctx.beginPath(); ctx.moveTo(8, 76); ctx.lineTo(352, 76); ctx.stroke(); ctx.setLineDash([]);
      world.balls.forEach(function (b) { fruit(b.level, b.x, b.y, 1); });
      if (active && !world.over) {
        var r = RADII[world.current], px = clamp(x, r + 2, 358 - r);
        if (pointer !== null) {
          ctx.globalAlpha = .3; ctx.strokeStyle = colors['--muted']; ctx.beginPath(); ctx.moveTo(px, 76); ctx.lineTo(px, 468); ctx.stroke(); ctx.globalAlpha = 1;
        }
        if (!world.cooldown) {
          ctx.strokeStyle = colors['--muted']; ctx.lineWidth = 1; ctx.setLineDash([3, 4]);
          ctx.beginPath(); ctx.arc(px, 32, Math.max(r + 5, 25), 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
          fruit(world.current, px, 32, 1);
        }
      }
    }
    function hud() {
      if (seenScore !== world.score) { seenScore = world.score; options.setScore(world.score); }
      nextEl.textContent = FRUITS[world.next];
      cv.setAttribute('aria-disabled', String(!active || paused || world.cooldown > 0));
      pauseButton.disabled = endButton.disabled = !active;
      pauseButton.textContent = paused ? '继续' : '暂停';
      var message = paused ? '已暂停，准备好再继续。' : world.danger ? '快到顶了，等一等合成。' : pointer !== null ? '松手，水果就落下。' : world.watermelons ? '合成大西瓜了！继续挑战吧。' : '按住顶部水果，拖动后松手。';
      if (status.textContent !== message) status.textContent = message;
    }
    function tick(now) {
      if (!active || paused) return;
      accumulator += Math.min((now - (last || now)) / 1000, .1); last = now;
      while (accumulator >= 1 / 120 && !world.over) { world.step(1 / 120); accumulator -= 1 / 120; }
      hud(); draw();
      if (world.over) { status.textContent = '水果堆到顶了。'; options.finish('水果堆到顶了'); return; }
      frame = requestAnimationFrame(tick);
    }
    function cancelDrag() { var id = pointer; pointer = null; cv.classList.remove('is-dragging'); if (id !== null && cv.hasPointerCapture(id)) cv.releasePointerCapture(id); }
    function stop() { active = false; cancelAnimationFrame(frame); cancelDrag(); hud(); }
    function pause(value) { if (!active) return; paused = value; cancelDrag(); cancelAnimationFrame(frame); last = 0; accumulator = 0; hud(); draw(); if (!paused) frame = requestAnimationFrame(tick); }
    function drop() { if (!active || paused) return; if (world.drop(x)) { hud(); draw(); } }
    function point(e) { var rect = cv.getBoundingClientRect(), r = RADII[world.current]; x = clamp((e.clientX - rect.left) * 360 / rect.width, r + 2, 358 - r); draw(); }
    cv.addEventListener('pointerdown', function (e) {
      if (!active || paused || world.cooldown > 0 || pointer !== null || e.button !== 0) return;
      var rect = cv.getBoundingClientRect(), px = (e.clientX - rect.left) * 360 / rect.width, py = (e.clientY - rect.top) * 480 / rect.height;
      var r = RADII[world.current], center = clamp(x, r + 2, 358 - r);
      if (Math.hypot(px - center, py - 32) > Math.max(r + 8, 30)) return;
      e.preventDefault(); cv.focus({preventScroll: true}); pointer = e.pointerId;
      cv.setPointerCapture(pointer); cv.classList.add('is-dragging'); point(e); hud();
    });
    cv.addEventListener('pointermove', function (e) { if (e.pointerId === pointer) point(e); });
    cv.addEventListener('pointerup', function (e) { if (e.pointerId !== pointer) return; point(e); cancelDrag(); drop(); });
    cv.addEventListener('pointercancel', function () { cancelDrag(); hud(); draw(); });
    cv.addEventListener('lostpointercapture', function () { if (pointer !== null) { cancelDrag(); hud(); draw(); } });
    cv.addEventListener('keydown', function (e) { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); drop(); } });
    pauseButton.addEventListener('click', function () { pause(!paused); });
    endButton.addEventListener('click', function () { if (!active) return; pause(true); if (window.confirm('结束这一局，记录当前分数？')) options.finish('本局完成'); });
    document.addEventListener('visibilitychange', function () { if (document.hidden) pause(true); });
    window.addEventListener('pagehide', stop);
    var media = window.matchMedia('(prefers-color-scheme: dark)'); media.addEventListener('change', function () { palette(); draw(); });
    resize(); hud();
    return {
      start: function () { cancelAnimationFrame(frame); cancelDrag(); world.reset(); active = true; paused = false; last = 0; accumulator = 0; x = 180; seenScore = -1; hud(); draw(); frame = requestAnimationFrame(tick); },
      stop: stop,
      move: function (d) { if (!active || paused) return; if (d === 'l' || d === 'r') { var r = RADII[world.current]; x = clamp(x + (d === 'l' ? -12 : 12), r + 2, 358 - r); draw(); } }
    };
  }
  var api = { World: World, RADII: RADII, mount: mount };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PhoneWatermelon = api;
}(typeof window !== 'undefined' ? window : globalThis));
