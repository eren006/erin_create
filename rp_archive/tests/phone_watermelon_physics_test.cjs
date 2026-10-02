const assert = require('node:assert/strict');
const {World, RADII} = require('../static/phone-watermelon.js');
function advance(w, seconds) { for (let i = 0; i < seconds * 120; i++) w.step(1 / 120); }
let w = new World(() => 0);
assert(w.drop(-100)); assert.equal(w.balls[0].x, RADII[0] + 2);
assert.equal(w.drop(100), false, 'rapid drops are throttled');
advance(w, 2); assert.equal(w.over, false, 'a falling fruit does not end the game');
assert(Math.abs(w.balls[0].y - (478 - RADII[0])) < 1, 'fruit settles on floor');
w.drop(14); advance(w, 3);
assert.equal(w.balls.length, 1); assert.equal(w.balls[0].level, 1); assert.equal(w.score, 4);
w = new World(); w.add(0, 100, 400); w.add(1, 110, 400); advance(w, 2);
assert.equal(w.balls.length, 2, 'different fruits do not merge');
assert(w.balls.every(b => Number.isFinite(b.x) && b.x >= b.r && b.x <= 360 - b.r));
w = new World(); w.add(9, 140, 400); w.add(9, 240, 400); w.step(1 / 120);
assert.equal(w.watermelons, 1); assert.equal(w.balls[0].level, 10); assert.equal(w.score, 121);
w.add(10, 180, 400); advance(w, 2); assert.equal(w.balls.length, 2, 'watermelons stay as final fruit');
w = new World(); for (let i = 0; i < 6; i++) { let b = w.add(10, 180, 470 - i * 140); b.born = -10; }
advance(w, 5); assert(w.over, 'overflow ends a packed game');
assert.equal(w.drop(180), false); w.reset(); assert.equal(w.over, false); assert.equal(w.score, 0); assert.equal(w.balls.length, 0);
let seed = 5; w = new World(() => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296));
for (let i = 0; i < 200 && !w.over; i++) { w.drop(20 + w.random() * 320); advance(w, .75); }
assert(w.balls.every(b => [b.x,b.y,b.vx,b.vy].every(Number.isFinite)), 'long play remains finite');
console.log('Watermelon drop, merge, scoring, walls, overflow, restart and long simulation: ALL OK');
