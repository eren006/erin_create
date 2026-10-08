// 网页关系线（插件一侧）：从源码截出社交卫星的 relWebApplyOp / relWebSnapshot / relWebNotice 和主插件的 phoneApplyRelOps，用桩环境跑。
// 用法：node 长日系统/tests/rel_web_test.js ，通过时打印 REL WEB OK
// 覆盖：新补充内容建线并写进副本 / 追加 / 修改只改自己写的那条 / 确认 / 通知文案与发送对象 / 重复下发不重复处理 / 网页开着时群里指令改成提示（过期不提示）/
//       整份副本指纹（同样的数据同样的指纹、改一个字就变、两个方向的同一条线只算一条）
const fs = require("fs"), path = require("path");
const soc = fs.readFileSync(path.join(__dirname, "..", "长日社交.js"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "..", "长日系统.js"), "utf8");
const slice = (src, a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); if (i < 0 || j < 0) throw new Error("截取失败：" + a); return src.slice(i, j); };
const SOC_SRC = slice(soc, "const REL_WEB_STALE_MS", "globalThis.__changriRelWeb = ");
const MAIN_SRC = slice(main, "function phoneApplyRelOps", "function phoneApplyWishOps");
const code = `
const store = { relationship_lines: {}, phone_rel_ops_done: [], phone_rel_web: {}, a_private_group: { QQ: { "1": ["林晚", "1001"], "2": ["周屿", "1002"], "3": ["沈知意", "1003"] } } };
const clone = x => JSON.parse(JSON.stringify(x));
const mainKvGet = (k, d) => store[k] !== undefined ? clone(store[k]) : d, mainKvSet = (k, v) => { store[k] = clone(v) };
const kvGet = mainKvGet, kvSet = mainKvSet;
const uids = { "林晚": "1", "周屿": "2", "沈知意": "3" }, names = { "1": "林晚", "2": "周屿", "3": "沈知意" };
const getUidByRoleName = (pf, n) => uids[n] || null, resolveUidToName = (pf, u) => names[u] || u;
const getSafeEndPoint = () => ({});
const sent = [];
const seal = { newMessage: () => ({}), createTempCtx: () => ({}), replyToSender: (c, m, t) => sent.push({ gid: m.groupId, t }) };
const RelationshipUtils = { getData: k => mainKvGet(k, {}), setData: (k, v) => mainKvSet(k, v) };
function getTargetAddr(platform, name) { const u = getUidByRoleName(platform, name); const e = u && store.a_private_group[platform][u]; return e ? [u, e[1]] : null; }
` + SOC_SRC + `
globalThis.__changriRelWeb = { applyOp: relWebApplyOp, snapshot: relWebSnapshot };
` + MAIN_SRC + `
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(m + "：" + JSON.stringify(a) + " ≠ " + JSON.stringify(b)); };
const rel = () => store.relationship_lines.QQ["1"]["2"];
// 新补充内容建线
phoneApplyRelOps("QQ", [{ id: 1, kind: "detail_add", p: { frm: "林晚", to: "周屿", text: "青梅竹马", is_new: true } }]);
eq(rel().initiator, "林晚", "initiator"); eq(rel().details, [{ text: "青梅竹马", from: "林晚" }], "first detail");
eq(store.relationship_lines.QQ["2"]["1"], store.relationship_lines.QQ["1"]["2"], "both directions hold the same data");
eq(sent.length, 1, "notified once"); eq(sent[0].gid, "QQ-Group:1002", "notify target is the other's group"); if (!/发起了关系线/.test(sent[0].t) || !/青梅竹马/.test(sent[0].t) || !/CQ:at,qq=2/.test(sent[0].t)) throw new Error("new-line text");
// 追加 + 修改（只改自己写的那条）
phoneApplyRelOps("QQ", [{ id: 2, kind: "detail_add", p: { frm: "周屿", to: "林晚", text: "同桌三年", is_new: false } }]);
eq(rel().details.length, 2, "appended");
phoneApplyRelOps("QQ", [{ id: 3, kind: "detail_edit", p: { frm: "周屿", to: "林晚", old: "青梅竹马", new: "被篡改" } }]);
eq(rel().details[0].text, "青梅竹马", "cannot edit other's detail");
phoneApplyRelOps("QQ", [{ id: 4, kind: "detail_edit", p: { frm: "周屿", to: "林晚", old: "同桌三年", new: "同桌三年半" } }]);
eq(rel().details[1].text, "同桌三年半", "edit own");
const last = sent[sent.length - 1]; if (!/修改了一条/.test(last.t) || !/同桌三年半/.test(last.t) || last.gid !== "QQ-Group:1001") throw new Error("edit notice");
// 确认；交流 / 时间点只通知不动副本
phoneApplyRelOps("QQ", [{ id: 5, kind: "confirm", p: { frm: "周屿", to: "林晚" } }, { id: 6, kind: "chat", p: { frm: "林晚", to: "周屿" } },
  { id: 7, kind: "time_add", p: { frm: "林晚", to: "周屿", label: "D3 夜里", text: "牵手" } }, { id: 8, kind: "time_del", p: { frm: "林晚", to: "周屿", label: "D3 夜里", text: "牵手" } }]);
eq(rel().confirmed, true, "confirmed"); eq(rel().details.length, 2, "chat/time do not touch details");
if (!/D3 夜里｜牵手/.test(sent[sent.length - 2].t) || !/删除了/.test(sent[sent.length - 1].t)) throw new Error("time notices");
// 重复下发不重复处理 / 乱序按 id 先后
const n = sent.length;
phoneApplyRelOps("QQ", [{ id: 6, kind: "chat", p: { frm: "林晚", to: "周屿" } }, { id: 5, kind: "confirm", p: { frm: "周屿", to: "林晚" } }]);
eq(sent.length, n, "already-done ops are not replayed");
eq(store.phone_rel_ops_done.slice().sort((a, b) => a - b), [1, 2, 3, 4, 5, 6, 7, 8], "done ids recorded");
// 角色不在插件里：不报错，也不写副本
phoneApplyRelOps("QQ", [{ id: 9, kind: "detail_add", p: { frm: "路人", to: "周屿", text: "x", is_new: true } }]);
eq(Object.keys(store.relationship_lines.QQ).length, 2, "unknown role leaves copy alone");
// 网页开着时群里指令改成提示；过期不提示
eq(relWebNotice("拉线"), null, "off by default");
store.phone_rel_web = { on: true, url: "https://x/p", at: Date.now() };
if (!/拉线现在改在网页手机里/.test(relWebNotice("拉线")) || !/https:\\/\\/x\\/p/.test(relWebNotice("拉线"))) throw new Error("notice text");
store.phone_rel_web.at = Date.now() - 11 * 60 * 1000;
eq(relWebNotice("拉线"), null, "stale → ignored");
// 副本指纹
const s1 = relWebSnapshot("QQ"), s2 = relWebSnapshot("QQ");
eq(s1.hash, s2.hash, "stable hash"); eq(s1.lines.length, 1, "one line, not two directions");
eq(s1.lines[0], { a: "林晚", b: "周屿", initiator: "林晚", confirmed: true, details: [{ from: "林晚", text: "青梅竹马" }, { from: "周屿", text: "同桌三年半" }] }, "snapshot shape");
store.relationship_lines.QQ["1"]["2"].details[0].text = "青梅竹马。";
if (relWebSnapshot("QQ").hash === s1.hash) throw new Error("hash must change");
console.log("REL WEB OK");
`;
const vm = require("vm");
vm.runInNewContext(code, { console, JSON, Date, Object, Set, String, Array, Error, RegExp });
