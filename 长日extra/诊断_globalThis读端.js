// ==UserScript==
// @name         诊断_globalThis读端
// @author       长日将尽
// @version      1.0.0
// @description  诊断插件B：读取「写端」插件写入的 globalThis 值，判断插件间是否共享运行时。
//               用法：加载本插件后执行 .诊断读，结果直接回复到聊天。
// @timestamp    1750000000
// @license      MIT
// ==/UserScript==

let ext = seal.ext.find('diag_reader');
if (!ext) {
    ext = seal.ext.new("diag_reader", "长日诊断", "1.0.0");
    seal.ext.register(ext);
}
ext.autoActive = true;

let cmd = seal.ext.newCmdItemInfo();
cmd.name = "诊断读";
cmd.help = "检测 globalThis 是否跨插件共享，输出详细结果";
cmd.solve = function(ctx, msg, cmdArgs) {
    const lines = ["=== globalThis 跨插件共享诊断 ===\n"];

    // 1. 原始值
    const flag = globalThis.__diagFlag;
    if (flag === undefined) {
        lines.push("❌ __diagFlag：undefined（写端未加载 或 globalThis 不共享）");
    } else {
        lines.push("✅ __diagFlag：" + flag);
    }

    // 2. 函数是否可见
    const fn = globalThis.__diagFunc;
    if (typeof fn !== "function") {
        lines.push("❌ __diagFunc：不是函数（类型=" + typeof fn + "）");
    } else {
        try {
            const result = fn("test");
            lines.push("✅ __diagFunc 调用成功：" + result);
        } catch(e) {
            lines.push("⚠️ __diagFunc 可见但调用报错：" + e);
        }
    }

    // 3. 对象及方法
    const api = globalThis.__diagApi;
    if (!api || typeof api !== "object") {
        lines.push("❌ __diagApi：不可见（类型=" + typeof api + "）");
    } else {
        lines.push("✅ __diagApi 可见，version=" + api.version);
        try {
            lines.push("✅ __diagApi.ping()=" + api.ping());
            lines.push("✅ __diagApi.add(1,2)=" + api.add(1, 2));
        } catch(e) {
            lines.push("⚠️ __diagApi 方法调用报错：" + e);
        }
    }

    // 4. __changriApi（顺便检测真实主插件）
    const changriApi = globalThis.__changriApi;
    if (!changriApi) {
        lines.push("\n⚠️ __changriApi：未找到（主插件未加载 或 globalThis 不共享）");
    } else {
        lines.push("\n✅ __changriApi：已挂载");
        try {
            const v = typeof changriApi.kvGet === "function" ? "kvGet=function" : "kvGet=" + typeof changriApi.kvGet;
            lines.push("   " + v);
        } catch(e) {
            lines.push("   读取报错：" + e);
        }
    }

    lines.push("\n--- 结论 ---");
    if (flag !== undefined && typeof fn === "function" && api && typeof api.ping === "function") {
        lines.push("✅ globalThis 跨插件共享正常，changriApi 模式可用");
    } else if (flag !== undefined) {
        lines.push("⚠️ 原始值可见但函数/对象不可用，需进一步排查");
    } else {
        lines.push("❌ globalThis 不共享，changriApi 模式不可用，需改为其他方案");
    }

    seal.replyToSender(ctx, msg, lines.join("\n"));
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["诊断读"] = cmd;

console.log("[诊断读端] 已加载，发送 .诊断读 开始检测");
