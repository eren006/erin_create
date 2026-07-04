// ==UserScript==
// @name         诊断_globalThis写端
// @author       长日将尽
// @version      1.0.0
// @description  诊断插件A：向 globalThis 写入标记值和一个函数，供「读端」检测是否可见。
//               用法：先加载本插件，再加载「诊断_globalThis读端.js」，执行 .诊断读 查看结果。
// @timestamp    1750000000
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find('diag_writer');
if (!ext) {
    ext = seal.ext.new("diag_writer", "长日诊断", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

// 写入三种东西，读端逐一检测：
// 1. 原始值
globalThis.__diagFlag = "WRITER_LOADED_" + Date.now();

// 2. 函数（最关键：能调用才说明 changriApi 模式可行）
globalThis.__diagFunc = function(x) { return "hello_from_writer:" + x; };

// 3. 对象（模拟 changriApi 结构）
globalThis.__diagApi = {
    version: "1.0.0",
    ping: function() { return "pong"; },
    add: function(a, b) { return a + b; },
};

console.log("[诊断写端] globalThis 写入完毕：__diagFlag / __diagFunc / __diagApi");

// 指令：.诊断写 —— 随时重新写入（测试热重载后是否丢失）
let cmd = seal.ext.newCmdItemInfo();
cmd.name = "诊断写";
cmd.help = "重新向 globalThis 写入诊断标记，配合 .诊断读 使用";
cmd.solve = function(ctx, msg, cmdArgs) {
    globalThis.__diagFlag = "WRITER_REWRITTEN_" + Date.now();
    globalThis.__diagFunc = function(x) { return "hello_from_writer:" + x; };
    globalThis.__diagApi = {
        version: "1.0.0",
        ping: function() { return "pong"; },
        add: function(a, b) { return a + b; },
    };
    seal.replyToSender(ctx, msg, "✅ 已重新写入 globalThis.__diagFlag / __diagFunc / __diagApi");
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["诊断写"] = cmd;
