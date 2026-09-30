// 网页手机同步（phoneWebSync / phoneWebSendNotice）的模拟测试：从 长日系统.js 里截出这两个函数，mock 掉海豹和存储。
// 用法：node 长日系统/tests/phone_sync_mock.js ，通过时打印 JS OK
const fs = require("fs");
const KV = {
  a_private_group: { QQ: { "111": ["林晚", "g1"], "222": ["周屿", "g2", "阿屿"], "333": ["沈知意", "g3"] } },
  a_npc_list: ["沈知意"], global_feature_toggle: {}, chaos_letter_config: { misdelivery: 10, dailyLimit: 5 },
  feature_user_blocklist: { "222": { enable_general_gift: false } },
  sys_blocklist: { QQ: { "333": { "111": { silent: true } } } },
  global_chaos_letter_counts: { "QQ:111": { day: "D2", count: 2 }, "QQ:222": { day: "D1", count: 4 } },
  global_gift_stats: {}, global_gift_cooldowns: { "QQ:111": 1000 }, extra_accounts: {}, ts_feature_windows: [],
};
const CACHE = { global_days: "D2", "chaos_letter_cooldown_QQ:111": "5000", mailCooldown: "60" };
const kvGet = (k, d) => (k in KV ? JSON.parse(JSON.stringify(KV[k])) : d), kvSet = (k, v) => { KV[k] = v; };
const cachedGet = k => CACHE[k], cachedSet = (k, v) => { CACHE[k] = v; };
const getStorageInt = (k, d) => (CACHE[k] ? parseInt(CACHE[k]) : d);
const isArchiveEnabled = () => true;
const ext = {}; const seal = { ext: { getStringConfig: (e, k) => k === "RP存档服务器地址" ? "https://archive.x/" : "TOK" } };
const getPrimaryUid = (p, u) => u;
const getUidByRoleName = (p, n) => Object.entries(KV.a_private_group.QQ).find(([_, v]) => v[0] === n || v[2] === n)?.[0] || null;
const stats = []; const recordInteractionStat = (...a) => stats.push(a);
let sent;
global.fetch = async (url, opt) => { sent = { url, body: JSON.parse(opt.body) }; return { ok: true, json: async () => ({ web_send: true, events: [
  { id: 41, type: "sms", from_role: "林晚", to_role: "周屿", timestamp: 9000, day_key: "D2", lost: false },
  { id: 42, type: "gift", from_role: "林晚", to_role: "周屿", timestamp: 9500, day_key: "D2", lost: true },
  { id: 43, type: "sms", from_role: "周屿", to_role: "林晚", timestamp: 9600, day_key: "日期2026-10-01", lost: false },
]})}; };
const src = fs.readFileSync(require("path").join(__dirname, "..", "长日系统.js"), "utf8");
const fnSrc = src.slice(src.indexOf("let _phoneSyncBusy = false;"), src.indexOf("let _occupancyHeartbeat = 0;"));
eval(fnSrc + "\n;globalThis.phoneWebSync = phoneWebSync; globalThis.phoneWebSendNotice = phoneWebSendNotice;");
(async () => {
  const assert = require("assert");
  console.log(phoneWebSendNotice("短信"));
  await phoneWebSync();
  const snap = sent.body.snapshot;
  assert.equal(sent.url, "https://archive.x/api/phone/sync"); assert.equal(sent.body.after, 0);
  assert.deepEqual(snap.roster.map(r => r.name), ["林晚", "周屿", "沈知意"]); assert.equal(snap.roster[2].npc, true);
  assert.deepEqual(snap.feature_off, { "周屿": ["gift"] });
  assert.deepEqual(snap.blocks, [{ blocker: "沈知意", blocked: "林晚", silent: true }]);
  assert.deepEqual(snap.counts.sms, { "林晚": 2 });           // 周屿的是 D1 的，不算
  assert.equal(snap.last.sms["林晚"], 5000); assert.equal(snap.last.gift["林晚"], 1000);
  assert.equal(snap.rules.chaos.misdelivery, 10); assert.equal(snap.rules.chaos.tornPage, 0); assert.equal(snap.rules.mail_cooldown_min, 60);
  assert.equal(KV.global_chaos_letter_counts["QQ:111"].count, 3);   // +1 (D2)
  assert.equal(KV.global_chaos_letter_counts["QQ:222"].count, 4);   // 日期 key 不计，D1 旧记录不动
  assert.equal(KV.global_gift_stats["QQ:111"].count, 1);
  assert.equal(CACHE["chaos_letter_cooldown_QQ:111"], "9000"); assert.equal(CACHE["chaos_letter_cooldown_QQ:222"], "9600");
  assert.equal(KV.global_gift_cooldowns["QQ:111"], 9500);
  assert.equal(CACHE.phone_web_cursor, "43");
  assert.deepEqual(stats, [["QQ","林晚","周屿","sms"],["QQ","林晚","周屿","gift",true],["QQ","周屿","林晚","sms"]]);
  assert.equal(KV.phone_web_send.on, true);
  assert.equal(snap.rules.sms_public, false); assert.equal(snap.rules.gift_public_chance, 50); assert.equal(snap.rules.hide_receiver, false);
  assert.ok(phoneWebSendNotice("短信").includes("https://archive.x/p"));
  KV.phone_web_send.at = Date.now() - 11 * 60 * 1000; assert.equal(phoneWebSendNotice("短信"), null);  // 过期当关闭
  await phoneWebSync(); assert.equal(sent.body.after, 43);
  console.log("JS OK", JSON.stringify(sent.body).length, "bytes");
})().catch(e => { console.error(e); process.exit(1); });
