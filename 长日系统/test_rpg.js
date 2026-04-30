// 测试：长日RPG.js 核心逻辑（osascript -l JavaScript 兼容）
// 运行：osascript -l JavaScript 长日系统/test_rpg.js

// ===== Mock 存储 =====
const _store = {};
const mockMain = {
    storageGet: function(key) { return _store[key] || null; },
    storageSet: function(key, val) { _store[key] = val; },
};
function getMainExt() { return mockMain; }
function resetStore() { var keys = Object.keys(_store); for (var i = 0; i < keys.length; i++) delete _store[keys[i]]; }

// ===== 被测函数（从 长日RPG.js 复制）=====
function getAttrDefs() {
    var main = getMainExt();
    if (!main) return {};
    var defs = {};
    try { defs = JSON.parse(main.storageGet("rpg_attr_defs") || "{}"); } catch(e) {}
    if (!Object.keys(defs).length) {
        var migrated = false;
        var keys = ["sys_attr_presets", "item_valid_attrs"];
        for (var i = 0; i < keys.length; i++) {
            try {
                var arr = JSON.parse(main.storageGet(keys[i]) || "[]");
                if (Array.isArray(arr)) arr.forEach(function(n) { if (n && !defs[n]) { defs[n] = { min: null, max: null, default: 0, desc: "" }; migrated = true; } });
            } catch(e) {}
        }
        if (migrated) {
            main.storageSet("rpg_attr_defs", JSON.stringify(defs));
            main.storageSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
        }
    }
    return defs;
}
function saveAttrDefs(defs) {
    var main = getMainExt();
    if (!main) return;
    main.storageSet("rpg_attr_defs", JSON.stringify(defs));
    main.storageSet("sys_attr_presets", JSON.stringify(Object.keys(defs)));
}
function getCharAttrs() {
    var main = getMainExt();
    return main ? JSON.parse(main.storageGet("sys_character_attrs") || "{}") : {};
}
function saveCharAttrs(attrs) {
    var main = getMainExt();
    if (main) main.storageSet("sys_character_attrs", JSON.stringify(attrs));
}
function clampAttr(def, value) {
    if (!def) return value;
    if (def.min !== null && def.min !== undefined && value < def.min) return def.min;
    if (def.max !== null && def.max !== undefined && value > def.max) return def.max;
    return value;
}
function getValidAttrs() {
    return Object.keys(getAttrDefs());
}
function saveValidAttrs(attrs) {
    var defs = getAttrDefs();
    var newDefs = {};
    for (var i = 0; i < attrs.length; i++) {
        var a = attrs[i];
        newDefs[a] = defs[a] || { min: null, max: null, default: 0, desc: "" };
    }
    saveAttrDefs(newDefs);
}
function modCharAttrs(platform, roleName, attrEffectStr) {
    if (!attrEffectStr) return;
    var charAttrs = getCharAttrs();
    var defs = getAttrDefs();
    if (!charAttrs[roleName]) charAttrs[roleName] = {};
    var effects = attrEffectStr.split(/[,，]/);
    effects.forEach(function(eff) {
        var m = eff.trim().match(/^(.+?)([+\-]{1,2})(\d+)$/);
        if (m) {
            var aName = m[1], op = m[2], val = parseInt(m[3]);
            var def = defs[aName];
            var currentVal = charAttrs[roleName][aName] !== undefined ? charAttrs[roleName][aName] : (def ? def.default : 0);
            var change = op.indexOf('-') >= 0 ? -val : val;
            charAttrs[roleName][aName] = clampAttr(def, currentVal + change);
        }
    });
    saveCharAttrs(charAttrs);
}
function formatItemEntry(entry, info) {
    var name = info.name || entry.code;
    var shortName = name.length > 8 ? name.slice(0, 8) : name;
    var codeShort = entry.code.slice(-3);
    var desc = (info.desc || "").slice(0, 15);
    var uses = entry.remainingUses !== undefined ? entry.remainingUses : (info.maxUses !== undefined ? info.maxUses : -1);
    var usesStr = uses === -1 ? "∞次" : ("余" + uses + "次");
    var tags = "";
    if (info.type === "preset") tags += "🎯";
    if (info.canResell === false) tags += "🔒";
    if (info.canResell === true) tags += "✨";
    var line1 = "·" + shortName + "[" + codeShort + "]" + tags;
    var line2 = "数量×" + entry.count + "|" + usesStr;
    var line3 = desc || "无描述";
    var result = line1 + "\n" + line2 + "\n" + line3;
    if (info.attrs) result += "\n" + info.attrs.slice(0, 22);
    return result;
}

// ===== 测试框架 =====
var passed = 0, failed = 0;
function assert(desc, condition) {
    if (condition) { console.log("  ✅ " + desc); passed++; }
    else           { console.log("  ❌ " + desc); failed++; }
}
function section(title) { console.log("\n【" + title + "】"); }

// ===== 测试用例 =====

section("clampAttr — 修复：!def 安全检查（旧版本会崩溃）");
assert("def=null 时直接返回原值，不崩溃", clampAttr(null, 42) === 42);
assert("def=undefined 时直接返回原值", clampAttr(undefined, 99) === 99);
assert("value 在范围内不变", clampAttr({ min: 0, max: 100, default: 0, desc: "" }, 50) === 50);
assert("value 超过 max 被截断到 100", clampAttr({ min: 0, max: 100, default: 0, desc: "" }, 150) === 100);
assert("value 低于 min 被截断到 0", clampAttr({ min: 0, max: 100, default: 0, desc: "" }, -5) === 0);
assert("min/max 均为 null 时原样返回", clampAttr({ min: null, max: null, default: 0, desc: "" }, 999) === 999);

section("getAttrDefs / saveAttrDefs — 存储读写");
resetStore();
assert("空存储返回 {}", Object.keys(getAttrDefs()).length === 0);
saveAttrDefs({ "体力": { min: 0, max: 100, default: 50, desc: "体力值" } });
var defs = getAttrDefs();
assert("保存后能读取", defs["体力"] !== undefined);
assert("max 值正确", defs["体力"].max === 100);
assert("sys_attr_presets 同步更新", JSON.parse(_store["sys_attr_presets"]).indexOf("体力") >= 0);

section("getAttrDefs — 旧格式迁移");
resetStore();
_store["item_valid_attrs"] = JSON.stringify(["魅力", "力量"]);
var migrated = getAttrDefs();
assert("从 item_valid_attrs 迁移属性", migrated["魅力"] !== undefined);
assert("迁移后写入 rpg_attr_defs", _store["rpg_attr_defs"] !== undefined);
assert("迁移后的属性有默认 default=0", migrated["力量"]["default"] === 0);

section("getValidAttrs / saveValidAttrs — 修复：函数之前未定义，调用必崩溃");
resetStore();
assert("空时返回空数组", getValidAttrs().length === 0);
saveValidAttrs(["魅力", "力量", "智力"]);
var attrs = getValidAttrs();
assert("saveValidAttrs 后能读取全部属性（共3个）", attrs.length === 3);
assert("包含「魅力」", attrs.indexOf("魅力") >= 0);
assert("属性有默认结构（max=null）", getAttrDefs()["力量"].max === null);
saveValidAttrs(attrs.concat(["体力"]));
assert("追加新属性后共4个", getValidAttrs().length === 4);
assert("旧属性结构仍在", getAttrDefs()["魅力"] !== undefined);

section("modCharAttrs — 属性加减与 clamp 联动");
resetStore();
saveAttrDefs({ "体力": { min: 0, max: 100, default: 50, desc: "" } });
modCharAttrs("qq", "张三", "体力+30");
var ca = getCharAttrs();
assert("初始值=default(50) 加 30 = 80", ca["张三"]["体力"] === 80);
modCharAttrs("qq", "张三", "体力+50");
ca = getCharAttrs();
assert("超过 max=100 被截断到 100", ca["张三"]["体力"] === 100);
modCharAttrs("qq", "张三", "体力-200");
ca = getCharAttrs();
assert("低于 min=0 被截断到 0", ca["张三"]["体力"] === 0);
modCharAttrs("qq", "张三", "未知属性+10");
ca = getCharAttrs();
assert("未注册属性也能加（无 clamp）", ca["张三"]["未知属性"] === 10);

section("formatItemEntry — 修复：之前错误地被调用为 formatItemEntryMobile");
var entry = { code: "ITEM_001", count: 3, remainingUses: 2 };
var info  = { name: "神秘药水", type: "preset", desc: "恢复体力", canResell: false };
var output = formatItemEntry(entry, info);
assert("返回字符串", typeof output === "string");
assert("包含物品名", output.indexOf("神秘药水") >= 0);
assert("包含数量 ×3", output.indexOf("×3") >= 0);
assert("preset 显示 🎯", output.indexOf("🎯") >= 0);
assert("canResell=false 显示 🔒", output.indexOf("🔒") >= 0);
assert("剩余次数显示 余2次", output.indexOf("余2次") >= 0);
var longEntry = { code: "X", count: 1 };
var longInfo  = { name: "这是一个超长的物品名称超出限制", type: "item", desc: "", canResell: true };
var longOut = formatItemEntry(longEntry, longInfo);
assert("名称超过8字被截断", longOut.indexOf("这是一个超长的物品名称超出限制") < 0);
assert("canResell=true 显示 ✨", longOut.indexOf("✨") >= 0);
assert("无 remainingUses 时显示 ∞次", longOut.indexOf("∞次") >= 0);

// ===== 汇总 =====
console.log("\n" + "=".repeat(40));
console.log("结果：" + passed + " 通过 / " + failed + " 失败");
failed > 0 ? "FAILED" : "ALL PASSED";
