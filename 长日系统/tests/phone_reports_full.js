// 网页手机报告（buildPhoneReports）与重构后的「时间线」「我的数量」：加载整个 长日系统.js（海豹 API 用桩），灌数据后直接调用。
// 用法：node 长日系统/tests/phone_reports_full.js ，通过时打印 REPORTS OK
const fs = require("fs"), path = require("path"), assert = require("assert");
const STORE = {};
const noop = new Proxy(function () {}, { get: (t, k) => (k === Symbol.toPrimitive ? () => "" : noop), apply: () => noop });
const extObj = new Proxy({ storageGet: k => STORE[k] ?? "", storageSet: (k, v) => { STORE[k] = v; }, cmdMap: {}, onNotCommandReceived: null },
                         { get: (t, k) => (k in t ? t[k] : noop), set: (t, k, v) => { t[k] = v; return true; } });
const replies = [];
global.seal = new Proxy({
  ext: new Proxy({ find: () => extObj, new: () => extObj, register: () => {}, newCmdItemInfo: () => ({}), newCmdExecuteResult: () => ({}),
                   getStringConfig: () => "", getBoolConfig: () => false, getIntConfig: () => 0, getOptionConfig: () => "" },
                 { get: (t, k) => (k in t ? t[k] : noop) }),
  replyToSender: (ctx, msg, text) => replies.push(text), newMessage: () => ({}), createTempCtx: () => ({}),
}, { get: (t, k) => (k in t ? t[k] : noop) });
global.setInterval = () => 0; global.setTimeout = () => 0; global.WebSocket = function () {};
const src = fs.readFileSync(path.join(__dirname, "..", "长日系统.js"), "utf8");
const set = (k, v) => { STORE[k] = typeof v === "string" ? v : JSON.stringify(v); };
set("a_private_group", { QQ: { "111": ["林晚", "9001"], "222": ["周屿", "9002"], "333": ["沈知意", "9003"] } });
set("global_days", "D2");
const now = Date.now();
set("b_confirmedSchedule", { "QQ:111": [
  { day: "D2", time: "20:00", subtype: "私约", place: "天台", partner: "周屿", status: "active", group: "5001" },
  { day: "D1", time: "14:00", subtype: "电话", place: "", partner: "沈知意", status: "ended", group: "5002", finalProgress: { "111": 12, "333": 10 } } ] });
set("group_timers", { "5001": { platform: "QQ", subtype: "私约", timerMode: "turn_taking", participants: ["林晚", "周屿"], timeoutDuration: 3600000,
  timerStatus: { "林晚": { status: "timing", startTime: now - 2 * 3600000, sessionReplies: 3, sessionWords: 1240, sessionTimedReplies: 2, sessionReplyTimeMs: 30 * 60000 },
                 "周屿": { status: "replied", startTime: now, sessionReplies: 4, sessionWords: 999 } } } });
set("user_stats", { "QQ:111": { totalReplies: 86, totalWords: 12345, avgWords: 143.5, avgReplyTimeMin: 18.2, subtypeStats: { QQ: { "111": { fastestReply: 3, slowestReply: 240 } } } } });
set("group_write_progress", { "5001": { "111": 3, "222": 4 } });
set("wechat_groups", { QQ: { "6001": { status: "active", participants: ["林晚", "沈知意"], topic: "夜宵" } } });
eval(src + "\n;globalThis.__t = { buildPhoneReports, cmd_view_schedule, cmdMyCounts, kvSet };");
const build = globalThis.__t.buildPhoneReports;

const r = build("QQ");
assert.deepEqual(Object.keys(r).sort(), ["周屿", "林晚", "沈知意"]);
const lin = r["林晚"];
assert.equal(lin.day, "D2");
assert.ok(lin.counts.startsWith("📊 我的数量（D2）"), lin.counts);
assert.ok(lin.arc.includes("林晚 的弧长") && lin.arc.includes("5001"), lin.arc);
// 时间线：按游戏日排序，微信群在最后；进行中那场带当前进度，已完结那场带最终段数
assert.deepEqual(lin.timeline.map(e => e.day), ["D1", "D2", "微信群"]);
assert.equal(lin.timeline[0].progress, "✍️ 最终段数：12v10");
assert.ok(lin.timeline[1].tag.startsWith("进行中") && lin.timeline[1].tag.includes("未回") && lin.timeline[1].progress.includes("3v4"), JSON.stringify(lin.timeline[1]));
assert.equal(lin.timeline[1].icon, "🎭"); assert.equal(lin.timeline[2].wechat, true);
// 字数统计：本季累计来自 user_stats；进行中的场次带我自己的本场字数，别人的字数不上报
assert.deepEqual(lin.stats, { replies: 86, words: 12345, avg_words: 143.5, avg_min: 18.2, fastest: 3, slowest: 240 });
assert.equal(r["周屿"].stats, null);
const ss = lin.sessions[0];
assert.equal(ss.gid, "5001"); assert.equal(ss.my_replies, 3); assert.equal(ss.my_words, 1240); assert.equal(ss.my_avg_words, 413); assert.equal(ss.my_avg_min, 15); assert.equal(ss.my_timed, 2);
assert.deepEqual(ss.members.map(m => [m.name, m.me, m.replies, m.status]), [["林晚", true, 3, "timing"], ["周屿", false, 4, "replied"]]);
assert.ok(ss.members[0].wait_min >= 119 && ss.members[1].wait_min === null);
assert.ok(!JSON.stringify(ss).includes("999"), "partner's words must not be uploaded");
// 待回：5001 在等林晚、已超过 1 小时 → 超时
assert.deepEqual(lin.pending.pending.map(p => [p.gid, p.over]), [["5001", true]]);
assert.ok(lin.pending.pending[0].elapsed_min >= 119);
assert.deepEqual(r["周屿"].pending.pending, []);
assert.deepEqual(r["沈知意"].timeline.map(e => e.day), ["微信群"]);   // 电话那场只在林晚的日程里

// 群指令照旧：「我的数量」回同样的文字；「时间线」走合并转发（这里 ws 是桩），没有日程时回「暂无行程」
const ctx = { endPoint: { userId: "QQ:10000" } }, mk = uid => ({ platform: "QQ", sender: { userId: "QQ:" + uid }, groupId: "QQ-Group:9001", message: "" });
globalThis.__t.cmdMyCounts.solve(ctx, mk("111"));
assert.ok(replies.includes(lin.counts), "counts command same text"); replies.length = 0;
globalThis.__t.cmd_view_schedule.solve(ctx, mk("111"));
assert.equal(replies.length, 0, "林晚 goes to forward: " + replies.join());
globalThis.__t.kvSet("wechat_groups", {});
globalThis.__t.cmd_view_schedule.solve(ctx, mk("333"));
assert.ok(replies.pop().includes("当前暂无行程安排"), "empty schedule reply");

// 某个人的数据坏了只影响他自己（经插件 kvSet 写，绕过缓存）
globalThis.__t.kvSet("b_confirmedSchedule", { "QQ:111": [{ day: null, time: null }, { day: "D1", time: null }] });
const r2 = (() => { try { return build("QQ"); } catch (e) { return e; } })();
assert.ok(!(r2 instanceof Error), "must not throw");
assert.ok(!("林晚" in r2) && "周屿" in r2 && "沈知意" in r2, Object.keys(r2).join());
console.log("REPORTS OK", Object.keys(r2).join(","));
process.exit(0);
