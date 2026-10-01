// 网页手机管理员快速设置（phoneApplyAdminOps / PHONE_ADMIN_PARAMS）的模拟测试：截出这一段，mock 掉海豹和存储。
// 用法：node 长日系统/tests/phone_admin_ops_mock.js ，通过时打印 JS OK
const fs = require("fs"), assert = require("assert");
const KV = {
  a_private_group: { QQ: { "111": ["林晚", "g1"], "222": ["周屿", "g2"], "333": ["沈知意", "g3"] } }, a_npc_list: ["沈知意"], a_generic_npc_list: [],
  rpg_attr_defs: { 体力: { min: 0, max: 10, default: 5 } }, sys_character_attrs: { "111": { 体力: 9 } },
  global_inventories: { "QQ:111": [{ code: "G1", count: 2, remainingUses: -1 }] }, feature_user_blocklist: {},
  global_feature_toggle: {}, chaos_letter_config: { misdelivery: 10 }, item_registry: { G1: { name: "金币", type: "currency" }, K1: { name: "钥匙", type: "item" } }, equipment_registry: {},
};
const CACHE = { mailCooldown: "60" };
const kvGet = (k, d) => (k in KV ? JSON.parse(JSON.stringify(KV[k])) : d), kvSet = (k, v) => { KV[k] = v; };
const cachedGet = k => CACHE[k], cachedSet = (k, v) => { CACHE[k] = String(v); };
const getStorageInt = (k, d) => (CACHE[k] ? parseInt(CACHE[k]) : d);
const getPrimaryUid = (p, u) => u;
const getUidByRoleName = (p, n) => Object.entries(KV.a_private_group.QQ).find(([_, v]) => v[0] === n)?.[0] || null;
const getRegistry_rpg = () => Object.assign({}, KV.item_registry, KV.equipment_registry);
const getInvCount_rpg = (rk, code) => (KV.global_inventories[rk] || []).filter(e => e.code === code).reduce((s, e) => s + e.count, 0);
const addToInv_system = (rk, code, n) => { const inv = KV.global_inventories[rk] || (KV.global_inventories[rk] = []); const e = inv.find(x => x.code === code); if (e) e.count += n; else inv.push({ code, count: n, remainingUses: -1 }); return true; };
const removeFromInv_rpg = (rk, code, n) => { const inv = KV.global_inventories[rk] || []; const e = inv.find(x => x.code === code); e.count -= n; KV.global_inventories[rk] = inv.filter(x => x.count > 0); };
const src = fs.readFileSync(require("path").join(__dirname, "..", "长日系统.js"), "utf8");
const a = src.indexOf("const PHONE_ADMIN_PARAMS"), b = src.indexOf("// 网页礼品店的变化写回图鉴");
eval(src.slice(a, b) + "\n;globalThis.phoneApplyAdminOps = phoneApplyAdminOps; globalThis.buildPhoneAdminParams = buildPhoneAdminParams;");

const params = buildPhoneAdminParams(), P = id => params.find(p => p.id === id);
assert.equal(P("misdelivery").value, 10); assert.equal(P("dailyLimit").value, 5); assert.equal(P("mailCooldown").value, 60);
assert.equal(P("t_sms").value, true); assert.equal(P("t_lovemail").value, false); assert.equal(P("lovemail_delivery_time").value, "22:00");
assert.ok(params.every(p => p.label && p.section && ["num", "bool", "time"].includes(p.type)));

const op = (id, kind, name, value, role = "*") => ({ id, kind, name, value, role });
const done = () => kvGet("phone_admin_ops_done", []);
phoneApplyAdminOps("QQ", [
  op(1, "param", "misdelivery", "30"), op(2, "param", "misdelivery", "101"), op(3, "param", "t_sms", "off"), op(4, "param", "giftCooldown", "15"),
  op(5, "param", "lovemail_delivery_time", "21:30"), op(6, "param", "lovemail_delivery_time", "25:00"), op(7, "param", "nope", "1"),
  op(8, "param", "letter_public_send", "on"), op(9, "param", "drop_hide_receiver", "on"),
]);
assert.equal(KV.chaos_letter_config.misdelivery, 30); assert.equal(KV.global_feature_toggle.enable_chaos_letter, false);
assert.equal(CACHE.giftCooldown, "15"); assert.equal(CACHE.lovemail_delivery_time, "21:30"); assert.equal(KV.letter_public_send, true); assert.equal(CACHE.drop_hide_receiver, "true");
assert.deepEqual(done().map(d => [d.id, d.ok]), [[1, true], [2, false], [3, true], [4, true], [5, true], [6, false], [7, false], [8, true], [9, true]]);
assert.ok(done()[1].msg.includes("不合法") && done()[0].msg.includes("10 → 30"));

// 批量：仅玩家（不含 NPC 沈知意）；金币 +5；钥匙新增；属性 +3 按上限 10 夹住，没有记录的按默认值 5 算
phoneApplyAdminOps("QQ", [op(20, "bulk_item", "金币", "5", "*player"), op(21, "bulk_item", "钥匙", "1", "*all"), op(22, "bulk_attr", "体力", "3", "*player"),
                          op(23, "bulk_item", "不存在", "1", "*all"), op(24, "bulk_item", "金币", "-3", "*player"), op(25, "bulk_attr", "没有", "1", "*all")]);
assert.equal(getInvCount_rpg("QQ:111", "G1"), 4);   // 2 + 5 - 3
assert.equal(getInvCount_rpg("QQ:222", "G1"), 2);   // 0 + 5 - 3
assert.equal(getInvCount_rpg("QQ:333", "G1"), 0);   // NPC 没发
assert.equal(getInvCount_rpg("QQ:333", "K1"), 1); assert.equal(getInvCount_rpg("QQ:111", "K1"), 1);   // 含 NPC
assert.equal(KV.sys_character_attrs["111"].体力, 10); assert.equal(KV.sys_character_attrs["222"].体力, 8); assert.equal(KV.sys_character_attrs["333"], undefined);
const r = Object.fromEntries(done().filter(d => d.id >= 20).map(d => [d.id, d]));
assert.equal(r[20].ok, true); assert.ok(r[20].msg.includes("2/2")); assert.ok(r[21].msg.includes("3/3")); assert.equal(r[23].ok, false); assert.equal(r[25].ok, false);

// 同一条重复收到（回报还没送达）不重复执行
const before = getInvCount_rpg("QQ:111", "G1");
phoneApplyAdminOps("QQ", [op(20, "bulk_item", "金币", "5", "*player")]); assert.equal(getInvCount_rpg("QQ:111", "G1"), before);

// 单角色三种仍然可用
phoneApplyAdminOps("QQ", [op(30, "attr", "体力", "99", "林晚"), op(31, "item", "金币", "-100", "周屿"), op(32, "feature", "sms", "off", "周屿"), op(33, "attr", "体力", "1", "不存在的人")]);
assert.equal(KV.sys_character_attrs["111"].体力, 10); assert.equal(getInvCount_rpg("QQ:222", "G1"), 0); assert.equal(KV.feature_user_blocklist["222"].enable_chaos_letter, false);
assert.equal(done().find(d => d.id === 33).ok, false);
console.log("JS OK");
