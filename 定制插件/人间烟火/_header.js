// ==UserScript==
// @name         人间烟火
// @author       长日将尽
// @version      3.0.0
// @description  起名立家、种地偷菜、科举入仕、婚育子嗣——一部有你参与的发家传奇
// @timestamp    1748563200
// @license      MIT
// @homepageURL  https://github.com/eren006/erin_create
// ==/UserScript==

let ext = seal.ext.find("yanghuo_v3");
if (!ext) {
    ext = seal.ext.new("yanghuo_v3", "长日将尽", "3.0.0");
    seal.ext.registerIntConfig(ext, "打猎冷却_分钟",  120);
    seal.ext.registerIntConfig(ext, "偷菜冷却_分钟",   30);
    seal.ext.registerIntConfig(ext, "收租间隔_小时",    8);
    seal.ext.register(ext);
}
