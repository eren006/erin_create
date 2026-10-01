// 重复规则的对照测试：从 长日系统.js 里截出 repeatsPhrase / isTooRepetitive，跟存档站 _too_repetitive 同一张用例表，结果必须一致。
// 用法：node 长日系统/tests/repeat_rule_test.js ，通过时打印 REPEAT OK
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "长日系统.js"), "utf8");
const i = src.indexOf("function repeatsPhrase"), j = src.indexOf("// ── 寄信 · 前置校验", i);
if (i < 0 || j < 0) throw new Error("截取失败");
const isTooRepetitive = new Function(src.slice(i, j) + "; return isTooRepetitive;")();
const cases = [
  ["还没找到，还没找到，还没找到", true], ["还没找到，我要炸掉房间，还没找到，后来又说还没找到", true], ["我要炸掉房间".repeat(5), true], ["（性情言论）".repeat(5), true],
  ["还没找到，还没找到", false], ["还没找到还没找到", false], ["哈哈哈哈哈", false], ["我不知道，真的不知道，谁来告诉我", false],
  ["今天的排练很辛苦，大家都累坏了。你昨天帮我占了座位，我一直想谢谢你，却又不好意思开口。明天晚上如果有空，我们去天台吹吹风吧，听说那里能看到很亮的星星。", false],
  ["啊".repeat(12), true], ["啊".repeat(11), false],
];
for (const [t, want] of cases) if (isTooRepetitive(t) !== want) throw new Error("规则不一致：" + t.slice(0, 14) + " 期望 " + want);
console.log("REPEAT OK");
