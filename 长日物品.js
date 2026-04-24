// ==UserScript==
// @name         物品系统
// @author       长日将尽
// @version      1.0.1
// @description  独立的物品系统（抽奖池、背包、赠送、使用）。所有数据统一存储在主插件 changriV1 中，依赖其角色识别与管理权限。
// @timestamp    1743292800
// @license      MIT
// ==/UserScript==

/**
 * 说明：
 * 1. 核心依赖：通过 seal.ext.find('changriV1') 寻找主插件，获取角色绑定数据和管理员权限。
 * 2. 功能模块：物资自由放、玩家抽取、背包管理、赠送物品、使用物品、特殊道具发放。
 * 3. 数据存储：所有数据（池子、背包、抽取记录）均存储在主插件 changriV1 的存储空间中。
 * 4. 特殊物品：硬编码列表，发放时标记 special = true，背包中单独分类展示。
 * 5. 每日抽取上限：可通过插件配置项 dailyDrawLimit 调节（默认2次）。
 */

let ext = seal.ext.find('item_system');
if (!ext) {
    ext = seal.ext.new("item_system", "长日将尽", "1.0.1");
    seal.ext.register(ext);
}

seal.ext.registerIntConfig(ext, "dailyDrawLimit", 2, "每日抽取上限", "每位玩家每天最多可抽取的次数");

// ========================
// 核心依赖：读取主插件存储
// ========================

function getMainExt() {
    const main = seal.ext.find('changriV1');
    if (!main) {
        console.error("❌ 物品系统错误：未找到主插件 changriV1，请检查主插件是否已加载");
        return null;
    }
    return main;
}

/**
 * 获取当前发送者的角色名（依赖 changriV1 的角色绑定）
 */
function getRoleName(ctx, msg) {
    const main = getMainExt();
    if (!main) return null;

    try {
        let rawData = main.storageGet("a_private_group");
        if (!rawData) return null;

        let charPlatform = JSON.parse(rawData);
        const platform = msg.platform;
        const uid = msg.sender.userId.replace(/^[a-z]+:/i, "");

        if (!charPlatform[platform]) return null;
        for (let name in charPlatform[platform]) {
            if (Array.isArray(charPlatform[platform][name]) && charPlatform[platform][name][0] === uid) {
                return name;
            }
        }
    } catch (e) {
        console.log("物品系统读取主插件数据失败: " + e.message);
    }
    return null;
}

/**
 * 权限检查（依赖 changriV1 的管理员列表）
 */
function isUserAdmin(ctx, msg) {
    if (ctx.privilegeLevel === 100) return true;

    const main = getMainExt();
    if (!main) return false;

    try {
        let rawAdmin = main.storageGet("a_adminList");
        if (!rawAdmin) return false;

        let a_adminList = JSON.parse(rawAdmin);
        const parts = msg.sender.userId.split(':');
        const platform = parts[0];
        const pureUid = parts[1];

        return a_adminList[platform] && a_adminList[platform].includes(pureUid);
    } catch (e) {
        return false;
    }
}

function timeOverlap(t1, t2) {
    const parseStartEnd = (t) => {
        const [s, e] = t.split("-");
        const toMin = (time) => {
            const [h, m] = time.split(":").map(Number);
            return h * 60 + m;
        };
        return [toMin(s), toMin(e)];
    };
    const [start1, end1] = parseStartEnd(t1);
    const [start2, end2] = parseStartEnd(t2);
    return !(end1 <= start2 || end2 <= start1);
}

// ========================
// 物品系统工具函数（存储统一使用主插件）
// ========================

const ItemRoleUtils = {
    // 获取主插件实例（内部缓存，避免重复查找）
    _main: null,
    _getMain: function() {
        if (!this._main) {
            this._main = getMainExt();
        }
        return this._main;
    },

    // 获取角色标识 (平台+角色名)
    getRoleKey: (ctx, msg) => {
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return null;
        return `${msg.platform}:${roleName}`;
    },

    // 获取池子数据（从主插件读取）
    getPool: function() {
        const main = this._getMain();
        if (!main) return [];
        return JSON.parse(main.storageGet("sys_item_pool") || "[]");
    },
    setPool: function(data) {
        const main = this._getMain();
        if (!main) return;
        main.storageSet("sys_item_pool", JSON.stringify(data));
    },

    // 全服背包管理（从主插件读写）
    getGlobalInvs: function() {
        const main = this._getMain();
        if (!main) return {};
        return JSON.parse(main.storageGet("global_inventories") || "{}");
    },
    setGlobalInvs: function(data) {
        const main = this._getMain();
        if (!main) return;
        main.storageSet("global_inventories", JSON.stringify(data));
    },

    // 获取特定角色的背包
    getInv: function(roleKey) {
        const invs = this.getGlobalInvs();
        return invs[roleKey] || [];
    },
    // 保存特定角色的背包
    setInv: function(roleKey, inv) {
        const invs = this.getGlobalInvs();
        invs[roleKey] = inv;
        this.setGlobalInvs(invs);
    },

    // 抽取记录（从主插件读写）
    getGlobalRecords: function() {
        const main = this._getMain();
        if (!main) return {};
        return JSON.parse(main.storageGet("global_draw_records") || "{}");
    },
    setGlobalRecords: function(data) {
        const main = this._getMain();
        if (!main) return;
        main.storageSet("global_draw_records", JSON.stringify(data));
    },

    getToday: () => {
        const d = new Date();
        return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
    }
};

// 固定池管理工具
const FixedPoolUtils = {
    getPool: function() {
        const main = getMainExt();
        if (!main) return [];
        return JSON.parse(main.storageGet("fixed_item_pool") || "[]");
    },
    setPool: function(data) {
        const main = getMainExt();
        if (!main) return;
        main.storageSet("fixed_item_pool", JSON.stringify(data));
    },
    drawItem: function() {
        const pool = this.getPool();
        if (pool.length === 0) return null;
        const totalWeight = pool.reduce((sum, item) => sum + (item.weight || 1), 0);
        let random = Math.random() * totalWeight;
        for (const item of pool) {
            const w = item.weight || 1;
            if (random < w) {
                return { ...item };
            }
            random -= w;
        }
        return null;
    }
};

// 获取当前抽取池模式（"自由池" 或 "固定池"）
function getItemPoolMode() {
    const main = getMainExt();
    if (!main) return "自由池";
    return main.storageGet("item_pool_mode") || "自由池";
}

// ========================
// 管理员指令：自由放（自由池管理）
// ========================

let cmd_item_admin = seal.ext.newCmdItemInfo();
cmd_item_admin.name = "自由放";
cmd_item_admin.help = "【管理员指令】自由池管理\n" +
    "。自由放 添加 物品名*描述*数量、物品名*描述*数量…… —— 向自由池自由放物资（支持批量，用顿号分隔）\n" +
    "。自由放 查看池子 —— 查看自由池内剩余物资统计\n" +
    "。自由放 移除 物品名 —— 从自由池里删掉一个特定物品\n" +
    "。自由放 清空池子 —— 彻底清空自由池\n" +
    "。自由放 给予 角色名*物品名*描述、角色名*物品名*描述…… —— 向指定角色背包发放物品（支持批量）\n" +
    "💡 星号支持中文全角（＊）和英文半角（*），批量仅支持中文顿号（、）分隔\n" +
    "示例：\n" +
    "。自由放 添加 肾上腺素*急救用药品*5、巧克力*补充能量*3\n" +
    "。自由放 给予 张三*神秘钥匙*一把发光的钥匙、李四*月光宝盒*可以回到过去";

cmd_item_admin.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可操作物资池。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const subCmd = cmdArgs.getArgN(1);
    let pool = ItemRoleUtils.getPool();

    // 1. 添加物品
    if (subCmd === '添加') {
        const rawInput = cmdArgs.getArgN(2);
        if (!rawInput) {
            seal.replyToSender(ctx, msg, "❌ 请提供物品信息，格式：。自由放 添加 物品名*描述*数量、物品名*描述*数量");
            return seal.ext.newCmdExecuteResult(true);
        }

        const entries = rawInput.split(/[、]/);
        let addedCount = 0;
        let errorList = [];

        for (const entry of entries) {
            const trimmed = entry.trim();
            if (!trimmed) continue;

            const parts = trimmed.split(/[*＊]/);
            const name = (parts[0] || "").trim();
            const desc = (parts[1] || "").trim() || "该物品没有任何描述";
            const count = parseInt(parts[2]) || 1;

            if (!name) {
                errorList.push(`物品名不能为空: ${trimmed}`);
                continue;
            }

            for (let i = 0; i < count; i++) {
                pool.push({
                    name: name,
                    desc: desc,
                    used: false,
                    createTime: new Date().getTime()
                });
            }
            addedCount++;
        }

        if (addedCount > 0) {
            ItemRoleUtils.setPool(pool);
            let reply = `✅ 批量自由放完成！成功添加 ${addedCount} 种物品，池内总计 ${pool.length} 件物资。`;
            if (errorList.length) {
                reply += `\n⚠️ 失败项：\n${errorList.map(e => `· ${e}`).join('\n')}`;
            }
            seal.replyToSender(ctx, msg, reply);
        } else {
            seal.replyToSender(ctx, msg, `❌ 没有成功添加任何物品。${errorList.length ? `\n错误：${errorList.join(';')}` : ''}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    // 2. 查看池子
    if (subCmd === '查看池子' || subCmd === '查看') {
        if (pool.length === 0) {
            seal.replyToSender(ctx, msg, "📋 当前物资池空空如也，请先使用「。自由放 添加」放入物资。");
            return seal.ext.newCmdExecuteResult(true);
        }

        const stats = pool.reduce((acc, item) => {
            acc[item.name] = (acc[item.name] || 0) + 1;
            return acc;
        }, {});

        let text = `📋 物资池状态 (总计: ${pool.length} 件)：\n`;
        for (let name in stats) {
            text += `· ${name}：共 ${stats[name]} 件\n`;
        }
        text += `\n💡 玩家使用「。抽取」指令时将从中随机获得一件。`;
        seal.replyToSender(ctx, msg, text.trim());
        return seal.ext.newCmdExecuteResult(true);
    }

    // 3. 移除特定物品
    if (subCmd === '移除') {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) {
            seal.replyToSender(ctx, msg, "❌ 请提供要移除的物品名，格式：。自由放 移除 物品名");
            return seal.ext.newCmdExecuteResult(true);
        }

        const index = pool.findIndex(i => i.name === targetName);
        if (index > -1) {
            pool.splice(index, 1);
            ItemRoleUtils.setPool(pool);
            seal.replyToSender(ctx, msg, `🗑️ 已从池子中移除一件【${targetName}】。剩余：${pool.length} 件。`);
        } else {
            seal.replyToSender(ctx, msg, `❌ 池子中没有名为【${targetName}】的物品。`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    // 4. 清空池子
    if (subCmd === '清空池子') {
        ItemRoleUtils.setPool([]);
        seal.replyToSender(ctx, msg, "☢️ 物资池已彻底清空。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 5. 批量给予
    if (subCmd === '给予' || subCmd === '发放') {
        const rawInput = cmdArgs.getArgN(2);
        if (!rawInput) {
            seal.replyToSender(ctx, msg, "❌ 请提供给予信息，格式：。自由放 给予 角色名*物品名*描述、角色名*物品名*描述");
            return seal.ext.newCmdExecuteResult(true);
        }

        const entries = rawInput.split(/[、]/);
        let successCount = 0;
        let errorList = [];

        for (const entry of entries) {
            const trimmed = entry.trim();
            if (!trimmed) continue;

            const parts = trimmed.split(/[*＊]/);
            const targetRoleName = (parts[0] || "").trim();
            const itemName = (parts[1] || "").trim();
            const itemDesc = (parts[2] || "管理员发放的物品").trim();

            if (!targetRoleName || !itemName) {
                errorList.push(`格式错误: ${trimmed} (缺少角色名或物品名)`);
                continue;
            }

            const platform = msg.platform;
            const targetKey = `${platform}:${targetRoleName}`;

            // 检查目标角色是否存在（使用主插件存储）
            const main = getMainExt();
            if (!main) {
                errorList.push(`无法连接主插件，操作失败`);
                continue;
            }
            const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
            if (!a_private_group[platform]?.[targetRoleName]) {
                errorList.push(`角色「${targetRoleName}」未登记`);
                continue;
            }

            let inv = ItemRoleUtils.getInv(targetKey);
            inv.push({
                name: itemName,
                desc: itemDesc,
                used: false,
                createTime: new Date().getTime(),
                source: "Admin"
            });
            ItemRoleUtils.setInv(targetKey, inv);
            successCount++;
        }

        let reply = `✅ 批量发放完成！成功：${successCount} 项。`;
        if (errorList.length) {
            reply += `\n⚠️ 失败项：\n${errorList.map(e => `· ${e}`).join('\n')}`;
        }
        seal.replyToSender(ctx, msg, reply);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 无匹配子命令，显示帮助
    const ret = seal.ext.newCmdExecuteResult(true);
    ret.showHelp = true;
    return ret;
};

ext.cmdMap["自由放"] = cmd_item_admin;

// ========================
// 管理员指令：固定放（固定池管理）
// ========================

let cmd_fixed_item = seal.ext.newCmdItemInfo();
cmd_fixed_item.name = "固定放";
cmd_fixed_item.help = "【管理员指令】固定池管理\n" +
    "。固定放 添加 —— 发送多行消息，每行格式：物品名*描述*权重（换行分隔，一次添加多个）\n" +
    "。固定放 查看 —— 查看固定池物品及概率\n" +
    "。固定放 删除 物品名 —— 从固定池删除物品\n" +
    "💡 权重为整数，范围 1-999，系统自动按比例计算概率\n" +
    "💡 星号支持中文全角（＊）和英文半角（*）\n" +
    "示例：\n" +
    "。固定放 添加\n" +
    "手机*一部智能手机*10\n" +
    "电脑*一台笔记本电脑*5\n" +
    "耳机*无线耳机*3\n" +
    "（发送后系统会逐条处理）\n" +
    "。固定放 查看\n" +
    "。固定放 删除 手机";

cmd_fixed_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可操作固定池。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const action = cmdArgs.getArgN(1); // 添加/查看/删除
    if (!action) {
        seal.replyToSender(ctx, msg, "📦 固定池管理：\n" +
            "。固定放 添加 （发送多行物品，每行格式：物品名*描述*权重，换行分隔）\n" +
            "。固定放 查看\n" +
            "。固定放 删除 物品名\n" +
            "💡 权重为整数，范围 1-999，系统会自动按比例计算概率。");
        return seal.ext.newCmdExecuteResult(true);
    }

    if (action === '添加') {
        // 获取整个消息内容（去除指令部分）
        const rawMessage = msg.message.trim();
        let content = rawMessage.replace(/^[。.]固定放\s+添加\s*/, '');
        if (!content) {
            seal.replyToSender(ctx, msg, "❌ 请提供物品列表，每行格式：物品名*描述*权重。示例：\n固定放 添加\n手机*一部智能手机*10\n电脑*一台笔记本电脑*5");
            return seal.ext.newCmdExecuteResult(true);
        }

        // 按行分割，过滤空行
        const lines = content.split(/\r?\n/).filter(line => line.trim().length > 0);
        if (lines.length === 0) {
            seal.replyToSender(ctx, msg, "❌ 未检测到有效的物品行。");
            return seal.ext.newCmdExecuteResult(true);
        }

        let fixedPool = FixedPoolUtils.getPool();
        let addedCount = 0;
        let updatedCount = 0;
        let errorList = [];

        for (const line of lines) {
            const parts = line.split(/[*＊]/);
            if (parts.length < 3) {
                errorList.push(`格式错误: ${line} (缺少星号分隔)`);
                continue;
            }
            const name = (parts[0] || "").trim();
            const desc = (parts[1] || "").trim() || "无描述";
            const weight = parseFloat(parts[2]);
            // 校验：必须是正整数且 1 <= weight <= 999
            if (!name || isNaN(weight) || !Number.isInteger(weight) || weight <= 0 || weight >= 1000) {
                errorList.push(`格式错误: ${line} (物品名、描述、1-999的整数权重三项必填)`);
                continue;
            }

            const existing = fixedPool.find(i => i.name === name);
            if (existing) {
                existing.desc = desc;
                existing.weight = weight;
                updatedCount++;
            } else {
                fixedPool.push({ name, desc, weight });
                addedCount++;
            }
        }

        if (addedCount + updatedCount > 0) {
            FixedPoolUtils.setPool(fixedPool);
            let reply = `✅ 固定池更新完成！新增 ${addedCount} 项，更新 ${updatedCount} 项。`;
            if (errorList.length) {
                reply += `\n⚠️ 失败项（${errorList.length}）：\n${errorList.map(e => `· ${e}`).join('\n')}`;
            }
            seal.replyToSender(ctx, msg, reply);
        } else {
            seal.replyToSender(ctx, msg, `❌ 没有成功添加或更新任何物品。${errorList.length ? `\n错误：${errorList.join(';')}` : ''}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    }

    if (action === '查看') {
        const fixedPool = FixedPoolUtils.getPool();
        if (fixedPool.length === 0) {
            seal.replyToSender(ctx, msg, "📦 固定池暂无物品。");
            return seal.ext.newCmdExecuteResult(true);
        }
        const totalWeight = fixedPool.reduce((s, i) => s + i.weight, 0);
        let text = "📦 固定池物品列表：\n";
        fixedPool.forEach(item => {
            const percent = (item.weight / totalWeight * 100).toFixed(1);
            text += `· ${item.name} (权重 ${item.weight}, 概率 ${percent}%)\n   └ ${item.desc}\n`;
        });
        seal.replyToSender(ctx, msg, text.trim());
        return seal.ext.newCmdExecuteResult(true);
    }

    if (action === '删除') {
        const targetName = cmdArgs.getArgN(2);
        if (!targetName) {
            seal.replyToSender(ctx, msg, "❌ 请指定要删除的物品名，格式：。固定放 删除 物品名");
            return seal.ext.newCmdExecuteResult(true);
        }
        let fixedPool = FixedPoolUtils.getPool();
        const index = fixedPool.findIndex(i => i.name === targetName);
        if (index === -1) {
            seal.replyToSender(ctx, msg, `❌ 固定池中没有名为【${targetName}】的物品。`);
            return seal.ext.newCmdExecuteResult(true);
        }
        fixedPool.splice(index, 1);
        FixedPoolUtils.setPool(fixedPool);
        seal.replyToSender(ctx, msg, `🗑️ 已从固定池删除【${targetName}】。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    seal.replyToSender(ctx, msg, "❌ 未知操作，请使用：添加、查看、删除");
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["固定放"] = cmd_fixed_item;

// === 玩家指令：抽取 ===
let cmd_item_draw = seal.ext.newCmdItemInfo();
cmd_item_draw.name = "抽取";
cmd_item_draw.solve = (ctx, msg) => {
    const roleKey = ItemRoleUtils.getRoleKey(ctx, msg);
    if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先创建并绑定角色。");

    const today = ItemRoleUtils.getToday();
    const limit = seal.ext.getIntConfig(ext, "dailyDrawLimit");

    let records = ItemRoleUtils.getGlobalRecords();
    let myRec = records[roleKey] || { date: "", count: 0 };
    if (myRec.date !== today) myRec = { date: today, count: 0 };

    if (myRec.count >= limit) {
        seal.replyToSender(ctx, msg, `⚠️ 你今日抽取次数已达上限(${limit})。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    let item = null;
    let source = "";

    // 根据模式选择抽取来源
    if (getItemPoolMode() === "固定池") {
        // 固定池模式：从固定池按权重抽取，不修改池子
        item = FixedPoolUtils.drawItem();
        if (!item) {
            seal.replyToSender(ctx, msg, "❌ 固定池为空，请管理员先配置物品。");
            return seal.ext.newCmdExecuteResult(true);
        }
        source = "固定池";
    } else {
        // 自由池模式：从自由池随机抽取一件并移除
        let pool = ItemRoleUtils.getPool();
        if (pool.length === 0) {
            seal.replyToSender(ctx, msg, "❌ 物资池已空。");
            return seal.ext.newCmdExecuteResult(true);
        }
        const index = Math.floor(Math.random() * pool.length);
        item = pool.splice(index, 1)[0];
        ItemRoleUtils.setPool(pool);
        source = "物资池";
    }

    // 添加到玩家背包
    let inv = ItemRoleUtils.getInv(roleKey);
    inv.push({
        name: item.name,
        desc: item.desc,
        used: false,
        type: "普通",
        createTime: new Date().getTime(),
        source: source
    });
    ItemRoleUtils.setInv(roleKey, inv);

    myRec.count += 1;
    records[roleKey] = myRec;
    ItemRoleUtils.setGlobalRecords(records);

    const name = roleKey.split(":")[1];
    seal.replyToSender(ctx, msg, `🎁 【${name}】获得了：【${item.name}】\n描述：${item.desc}\n(今日进度: ${myRec.count}/${limit})`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["抽取"] = cmd_item_draw;

// 背包指令已移至长日系统.js（使用 ws 合并转发显示）

// === 玩家指令：赠送 ===
let cmd_item_give = seal.ext.newCmdItemInfo();
cmd_item_give.name = "赠送";
cmd_item_give.solve = (ctx, msg, cmdArgs) => {
    const myKey = ItemRoleUtils.getRoleKey(ctx, msg);
    const targetName = cmdArgs.getArgN(1);
    const itemName = cmdArgs.getArgN(2);
    const platform = msg.platform;

    if (!myKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");
    const targetKey = `${platform}:${targetName}`;

    // 检查目标是否存在（使用主插件）
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]?.[targetName]) return seal.replyToSender(ctx, msg, `❌ 角色「${targetName}」不存在。`);
    if (myKey === targetKey) return seal.replyToSender(ctx, msg, "⚠️ 不能送给自己。");

    let myInv = ItemRoleUtils.getInv(myKey);

    const idx = myInv.findIndex(i => i.name === itemName);

    if (idx > -1) {
        const item = myInv.splice(idx, 1)[0];
        ItemRoleUtils.setInv(myKey, myInv);

        let tInv = ItemRoleUtils.getInv(targetKey);
        tInv.push(item);
        ItemRoleUtils.setInv(targetKey, tInv);

        const senderName = myKey.split(":")[1];
        const isSpecial = item.special === true || item.type === "道具";
        if (isSpecial) {
            seal.replyToSender(ctx, msg, `⚙️ 【${senderName}】将道具「${item.name}」移交给了【${targetName}】。`);
        } else {
            seal.replyToSender(ctx, msg, `🎁 【${senderName}】将「${item.name}」赠给了【${targetName}】，它已放入对方背包。`);
        }
    } else {
        seal.replyToSender(ctx, msg, `❌ 背包里没有【${itemName}】。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["赠送"] = cmd_item_give;

// ========================
// 🎯 使用物品
// ========================
let cmd_item_use = seal.ext.newCmdItemInfo();
cmd_item_use.name = "使用";
cmd_item_use.solve = (ctx, msg, cmdArgs) => {
        const roleKey = ItemRoleUtils.getRoleKey(ctx, msg);
        if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");

        const itemName = cmdArgs.getArgN(1);
        if (!itemName) return seal.replyToSender(ctx, msg, "用法：。使用 物品名 [参数]");

        if (itemName === "追踪器") {
        const targetRole = cmdArgs.getArgN(2);
        if (!targetRole) return seal.replyToSender(ctx, msg, "🔍 请指定要追踪的角色：。使用 追踪器 角色名");

        const platform = msg.platform;
        const main = getMainExt();
        if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

        // 获取目标角色信息
        const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
        const targetInfo = a_private_group[platform]?.[targetRole];
        if (!targetInfo) return seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetRole}」。`);
        const targetKey = `${platform}:${targetInfo[0]}`;

        // 获取游戏天数
        const globalDay = main.storageGet("global_days");
        if (!globalDay) return seal.replyToSender(ctx, msg, "⚠️ 未设置游戏天数。");

        // 时间范围构建
        const timeRestrict = main.storageGet("item_tracker_time_restrict") !== "false"; // 默认 true
        let timeRange;
        if (timeRestrict) {
            // 限制模式：使用当前小时
            const now = new Date();
            const h = now.getHours();
            timeRange = `${h.toString().padStart(2,'0')}:00-${h === 23 ? "23:59" : (h+1).toString().padStart(2,'0')+":00"}`;
        } else {
            // 自由模式：从参数读取时间
            const timeArg = cmdArgs.getArgN(3);
            if (!timeArg) return seal.replyToSender(ctx, msg, "🔍 请指定要追踪的时间：。使用 追踪器 角色名 时间（如 14 或 14:30）");
            let hour, minute = 0;
            if (/^\d{1,2}$/.test(timeArg)) hour = parseInt(timeArg);
            else if (/^\d{1,2}:\d{2}$/.test(timeArg)) {
                const [h, m] = timeArg.split(':').map(Number);
                hour = h; minute = m;
                if (minute < 0 || minute > 59) return seal.replyToSender(ctx, msg, "⚠️ 分钟应在 00-59 之间");
            } else return seal.replyToSender(ctx, msg, "⚠️ 时间格式错误，请使用：14 或 14:30");
            if (hour < 0 || hour > 23) return seal.replyToSender(ctx, msg, "⚠️ 小时应在 0-23 之间");
            const start = `${hour.toString().padStart(2,'0')}:${minute.toString().padStart(2,'0')}`;
            let endHour = hour, endMin = minute + 60;
            if (endMin >= 60) { endHour += Math.floor(endMin/60); endMin %= 60; }
            if (endHour >= 24) { endHour = 23; endMin = 59; }
            timeRange = `${start}-${endHour.toString().padStart(2,'0')}:${endMin.toString().padStart(2,'0')}`;
        }

        // 查找日程
        const b_confirmedSchedule = JSON.parse(main.storageGet("b_confirmedSchedule") || "{}");
        const matchingEvent = (b_confirmedSchedule[targetKey] || []).find(ev => ev.day === globalDay && timeOverlap(ev.time, timeRange));

        // 成功率 & 显示配置
        const successRate = parseInt(main.storageGet("item_tracker_success_rate") || "70");
        const showPartner = main.storageGet("item_tracker_show_partner") !== "false";
        const isSuccess = Math.random() * 100 < successRate;

        if (!matchingEvent) return seal.replyToSender(ctx, msg, `🔍 未能发现「${targetRole}」的行踪。\n（追踪器未消耗）`);
        if (!isSuccess) {
            let inv = ItemRoleUtils.getInv(roleKey);
            const idx = inv.findIndex(i => i.name === "追踪器" && !i.used);
            if (idx !== -1) inv.splice(idx, 1);
            ItemRoleUtils.setInv(roleKey, inv);
            return seal.replyToSender(ctx, msg, `🔍 信号干扰，定位失败。\n（追踪器已消耗）`);
        }

        // 成功追踪：消耗追踪器
        let inv = ItemRoleUtils.getInv(roleKey);
        const idx = inv.findIndex(i => i.name === "追踪器" && !i.used);
        if (idx === -1) return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的追踪器。");
        inv.splice(idx, 1);
        ItemRoleUtils.setInv(roleKey, inv);

        // 简洁报告
        let resultMsg = `🔍 追踪到「${targetRole}」在 ${globalDay} ${matchingEvent.time} 出现在「${matchingEvent.place || "某处"}」`;
        if (showPartner && matchingEvent.partner && matchingEvent.partner !== "独自一人") resultMsg += `，与 ${matchingEvent.partner} 一起`;
        resultMsg += `。\n（追踪器已消耗）`;

        return seal.replyToSender(ctx, msg, resultMsg);
    }

    // ---------- 万能钥匙处理 ----------
    else if (itemName === "万能钥匙") {
        // 获取地点名（支持空格）
        const placeName = cmdArgs.args.slice(1).join(' ').trim();
        if (!placeName) {
            return seal.replyToSender(ctx, msg, "🔑 请指定要兑换钥匙的地点：。使用 万能钥匙 地点名");
        }

        const platform = msg.platform;
        const main = getMainExt();
        if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

        // 获取当前角色名
        const roleName = getRoleName(ctx, msg);
        if (!roleName) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");

        // 获取可用地点列表，检查地点是否存在
        const availablePlaces = JSON.parse(main.storageGet("available_places") || "{}");
        if (!availablePlaces[placeName]) {
            return seal.replyToSender(ctx, msg, `❌ 未找到地点「${placeName}」，请确认地点名称。\n📍 可用地点：${Object.keys(availablePlaces).join("、")}`);
        }

        // 获取当前角色的钥匙列表
        let placeKeys = JSON.parse(main.storageGet("place_keys") || "{}");
        if (!placeKeys[platform]) placeKeys[platform] = {};
        if (!placeKeys[platform][roleName]) placeKeys[platform][roleName] = [];

        // 检查是否已拥有该钥匙
        if (placeKeys[platform][roleName].includes(placeName)) {
            return seal.replyToSender(ctx, msg, `🔑 你已经拥有「${placeName}」的钥匙了，无需重复兑换。`);
        }

        // 先消耗万能钥匙，再发放权限（避免道具不存在时仍写入权限）
        let inv = ItemRoleUtils.getInv(roleKey);
        const idx = inv.findIndex(i => i.name === "万能钥匙" && !i.used);
        if (idx === -1) {
            return seal.replyToSender(ctx, msg, "❌ 背包中没有可用的万能钥匙。");
        }
        inv.splice(idx, 1);
        ItemRoleUtils.setInv(roleKey, inv);

        // 发放地点权限
        placeKeys[platform][roleName].push(placeName);
        main.storageSet("place_keys", JSON.stringify(placeKeys));

        // 回复成功
        seal.replyToSender(ctx, msg, `🔓 万能钥匙化作一缕金光，为你开启了「${placeName}」的门锁！\n你获得了该地点的钥匙。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // ---------- 普通物品使用逻辑 ----------
    const roleName = roleKey.split(":")[1];
    let inv = ItemRoleUtils.getInv(roleKey);
    const item = inv.find(i => i.name === itemName && !i.used);

    if (item) {
        item.used = true;
        logItemUsage(roleKey, itemName, item.desc, msg.platform);
        ItemRoleUtils.setInv(roleKey, inv);
        seal.replyToSender(ctx, msg, `⚙️ 【${roleName}】使用了【${itemName}】。`);
    } else {
        seal.replyToSender(ctx, msg, `❌ 背包中没有未使用的【${itemName}】。`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["使用"] = cmd_item_use;

// ========================
// 特殊物品列表中添加追踪器
// ========================
const SPECIAL_ITEMS = {
    "追踪器": "一枚散发着微光的微型追踪器，轻轻按动便能感知目标此刻的行踪。",
    "万能钥匙": "一把泛着银光的万能钥匙，据说能开启世间任何一扇被锁住的门。"
};

let cmd_issue_special = seal.ext.newCmdItemInfo();
cmd_issue_special.name = "发放";
cmd_issue_special.help = "【管理员指令】批量发放/扣除物品\n" +
    "。发放 物品1[*数量] 物品2[*数量] ... 角色名\n" +
    "数量默认为1，可为负数表示扣除。\n" +
    "示例：\n" +
    "。发放 手机 张三               # 给张三1个手机\n" +
    "。发放 手机*2 电脑*1 李四       # 给李四2个手机和1个电脑\n" +
    "。发放 手机*-1 王五             # 从王五背包扣除1个手机";

cmd_issue_special.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足：该指令仅限管理员使用。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 获取所有参数
    const args = [];
    for (let i = 1; i <= cmdArgs.args.length; i++) {
        args.push(cmdArgs.getArgN(i));
    }
    if (args.length < 2) {
        seal.replyToSender(ctx, msg, "❌ 参数不足，格式：。发放 物品1[*数量] 物品2[*数量] ... 角色名");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 最后一个参数是目标角色名
    const targetRoleName = args.pop();
    // 剩下的都是物品项
    const itemsRaw = args;

    // 解析物品项
    const operations = []; // { name, delta, desc, special }
    let errorList = [];

    for (const raw of itemsRaw) {
        let name, delta = 1;
        if (raw.includes('*') || raw.includes('＊')) {
            const parts = raw.split(/[*＊]/);
            name = parts[0].trim();
            const deltaStr = parts[1].trim();
            if (deltaStr) {
                delta = parseInt(deltaStr);
                if (isNaN(delta)) {
                    errorList.push(`数量格式错误: ${raw}`);
                    continue;
                }
            }
        } else {
            name = raw.trim();
        }
        if (!name) {
            errorList.push(`物品名不能为空: ${raw}`);
            continue;
        }

        let desc = "管理员发放的物品";
        let special = false;
        if (SPECIAL_ITEMS[name]) {
            desc = SPECIAL_ITEMS[name];
            special = true;
        }

        operations.push({ name, delta, desc, special });
    }

    if (errorList.length > 0) {
        seal.replyToSender(ctx, msg, `❌ 解析错误：\n${errorList.join('\n')}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查目标角色是否存在
    const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]?.[targetRoleName]) {
        seal.replyToSender(ctx, msg, `❌ 未找到角色「${targetRoleName}」，请确认其已注册。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetKey = `${platform}:${targetRoleName}`;
    let inv = ItemRoleUtils.getInv(targetKey); // 当前背包

    // 验证所有扣除操作是否足够
    for (const op of operations) {
        if (op.delta < 0) {
            const currentCount = inv.filter(i => i.name === op.name && !i.used).length;
            if (currentCount + op.delta < 0) {
                errorList.push(`角色「${targetRoleName}」背包中 ${op.name} 不足 ${-op.delta} 个（当前有 ${currentCount} 个）`);
            }
        }
    }
    if (errorList.length > 0) {
        seal.replyToSender(ctx, msg, `❌ 扣除失败：\n${errorList.join('\n')}`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 执行操作
    let addedCount = 0;
    let removedCount = 0;
    for (const op of operations) {
        if (op.delta > 0) {
            for (let i = 0; i < op.delta; i++) {
                inv.push({
                    name: op.name,
                    desc: op.desc,
                    used: false,
                    type: op.special ? "道具" : "普通",
                    createTime: Date.now(),
                    source: "Admin",
                    special: op.special
                });
            }
            addedCount += op.delta;
        } else if (op.delta < 0) {
            // 扣除：删除指定数量的未使用物品
            let toRemove = -op.delta;
            const newInv = [];
            for (const item of inv) {
                if (item.name === op.name && !item.used && toRemove > 0) {
                    toRemove--;
                    removedCount++;
                    continue;
                }
                newInv.push(item);
            }
            inv = newInv;
        }
    }

    ItemRoleUtils.setInv(targetKey, inv);

    let reply = `✅ 操作完成！`;
    if (addedCount > 0) reply += ` 发放 ${addedCount} 件物品。`;
    if (removedCount > 0) reply += ` 扣除 ${removedCount} 件物品。`;
    if (addedCount === 0 && removedCount === 0) reply += ` 无变化。`;
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};

ext.cmdMap["发放"] = cmd_issue_special;

// ========================
// 📜 物品使用记录系统
// ========================

/**
 * 记录一次物品使用
 * @param {string} roleKey - 角色标识 (platform:roleName)
 * @param {string} itemName - 物品名
 * @param {string} itemDesc - 物品描述
 * @param {string} platform - 平台
 */
function logItemUsage(roleKey, itemName, itemDesc, platform) {
    const main = getMainExt();
    if (!main) return;
    
    const roleName = roleKey.split(':')[1];
    const log = JSON.parse(main.storageGet("item_usage_log") || "[]");
    log.push({
        timestamp: Date.now(),
        platform: platform,
        roleName: roleName,
        itemName: itemName,
        itemDesc: itemDesc
    });
    main.storageSet("item_usage_log", JSON.stringify(log));
}

// ========================
// 📜 查看今日物品使用记录
// ========================
let cmd_item_usage_log = seal.ext.newCmdItemInfo();
cmd_item_usage_log.name = "物品使用记录";
cmd_item_usage_log.help = "查看今天 0 点以来所有玩家使用物品的顺序（按时间先后）";
cmd_item_usage_log.solve = (ctx, msg) => {
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    
    const log = JSON.parse(main.storageGet("item_usage_log") || "[]");
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayLog = log.filter(entry => entry.timestamp >= todayStart.getTime());
    
    if (todayLog.length === 0) {
        seal.replyToSender(ctx, msg, "📭 今天还没有人使用过物品。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    // 按时间顺序排列（升序）
    todayLog.sort((a, b) => a.timestamp - b.timestamp);
    
    let reply = "📜 今日物品使用记录（按时间顺序）：\n━━━━━━━━━━━━━━━\n";
    todayLog.forEach((entry, idx) => {
        const time = new Date(entry.timestamp).toLocaleTimeString("zh-CN", { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        reply += `${idx + 1}. ${time} | ${entry.roleName} 使用了「${entry.itemName}」\n`;
    });
    seal.replyToSender(ctx, msg, reply);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["物品使用记录"] = cmd_item_usage_log;

let cmd_clear_unused_items = seal.ext.newCmdItemInfo();
cmd_clear_unused_items.name = "清空物品";
cmd_clear_unused_items.help = "【管理员指令】清空所有玩家背包中未使用的物品（已使用的物品保留）";
cmd_clear_unused_items.solve = (ctx, msg) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可清空物品。");
        return seal.ext.newCmdExecuteResult(true);
    }
    
    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
    
    const globalInvs = ItemRoleUtils.getGlobalInvs();
    let totalRemoved = 0;
    let totalKept = 0;
    let details = []; // 存储每个玩家的清理详情
    
    for (const [roleKey, inv] of Object.entries(globalInvs)) {
        const before = inv.length;
        // 分离未使用和已使用
        const unusedItems = inv.filter(item => item.used !== true);
        const usedItems = inv.filter(item => item.used === true);
        const removed = unusedItems.length;
        if (removed > 0) {
            // 记录被清理的物品名称（或id）
            const itemNames = unusedItems.map(item => item.name || item.id || '未知物品').join('、');
            details.push(`${roleKey}: 清理了 ${removed} 件物品（${itemNames}）`);
        }
        totalRemoved += removed;
        totalKept += usedItems.length;
        globalInvs[roleKey] = usedItems;
    }
    
    ItemRoleUtils.setGlobalInvs(globalInvs);
    
    let replyMsg = `🧹 清空完成！\n共清理未使用物品：${totalRemoved} 件\n保留已使用物品：${totalKept} 件`;
    if (details.length > 0) {
        replyMsg += `\n\n📋 清理详情：\n${details.join('\n')}`;
        // 如果消息过长，截断并提示
        if (replyMsg.length > 2000) {
            replyMsg = replyMsg.substring(0, 1900) + '\n...(内容过长，已截断)';
        }
    } else {
        replyMsg += '\n没有未使用的物品需要清理。';
    }
    
    seal.replyToSender(ctx, msg, replyMsg);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["清空物品"] = cmd_clear_unused_items;

// ========================
// 管理员指令：移除物品（从指定角色背包中删除未使用物品）
// ========================
let cmd_admin_remove_item = seal.ext.newCmdItemInfo();
cmd_admin_remove_item.name = "移除物品";
cmd_admin_remove_item.help = "【管理员指令】从指定角色的背包中移除指定数量的未使用物品\n" +
    "。移除物品 角色名 物品名 [数量] —— 默认移除1件\n" +
    "示例：。移除物品 张三 手机 2";
cmd_admin_remove_item.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可移除物品。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetRoleName = cmdArgs.getArgN(1);
    const itemName = cmdArgs.getArgN(2);
    let quantity = parseInt(cmdArgs.getArgN(3));
    if (isNaN(quantity) || quantity <= 0) quantity = 1;

    if (!targetRoleName || !itemName) {
        seal.replyToSender(ctx, msg, "❌ 用法：。移除物品 角色名 物品名 [数量]");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const main = getMainExt();
    if (!main) {
        seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查角色是否存在
    const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]?.[targetRoleName]) {
        seal.replyToSender(ctx, msg, `❌ 角色「${targetRoleName}」不存在。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetKey = `${platform}:${targetRoleName}`;
    let inv = ItemRoleUtils.getInv(targetKey);

    // 统计未使用的匹配物品数量
    const availableCount = inv.filter(i => i.name === itemName && !i.used).length;
    if (availableCount === 0) {
        seal.replyToSender(ctx, msg, `❌ 角色「${targetRoleName}」背包中没有未使用的【${itemName}】。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    const toRemove = Math.min(quantity, availableCount);
    let removed = 0;
    const newInv = [];
    for (const item of inv) {
        if (removed < toRemove && item.name === itemName && !item.used) {
            removed++;
            continue;
        }
        newInv.push(item);
    }

    ItemRoleUtils.setInv(targetKey, newInv);
    seal.replyToSender(ctx, msg, `🗑️ 已从角色「${targetRoleName}」背包中移除 ${removed} 个【${itemName}】。`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["移除物品"] = cmd_admin_remove_item;

// ========================
// 管理员指令：删除使用记录（按序号删除单条）
// ========================
let cmd_delete_usage_log = seal.ext.newCmdItemInfo();
cmd_delete_usage_log.name = "删除使用记录";
cmd_delete_usage_log.help = "【管理员指令】删除某一条物品使用记录\n" +
    "。删除使用记录 序号 —— 删除指定序号的记录（序号通过「。物品使用记录」查看）\n" +
    "示例：。删除使用记录 3";
cmd_delete_usage_log.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可删除使用记录。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const idxStr = cmdArgs.getArgN(1);
    if (!idxStr) {
        seal.replyToSender(ctx, msg, "❌ 请提供要删除的记录序号，例如：。删除使用记录 2");
        return seal.ext.newCmdExecuteResult(true);
    }
    const idx = parseInt(idxStr);
    if (isNaN(idx) || idx <= 0) {
        seal.replyToSender(ctx, msg, "❌ 序号必须是正整数。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const main = getMainExt();
    if (!main) return seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");

    // 获取今天的记录（与「物品使用记录」保持一致范围：今天0点至今）
    const log = JSON.parse(main.storageGet("item_usage_log") || "[]");
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayLog = log.filter(entry => entry.timestamp >= todayStart.getTime());
    // 按时间升序排序
    todayLog.sort((a, b) => a.timestamp - b.timestamp);

    if (idx > todayLog.length) {
        seal.replyToSender(ctx, msg, `❌ 序号超出范围，当前共有 ${todayLog.length} 条记录。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 找到要删除的原始记录（在原log中的索引）
    const targetEntry = todayLog[idx - 1];
    const originalIndex = log.findIndex(entry =>
        entry.timestamp === targetEntry.timestamp &&
        entry.roleName === targetEntry.roleName &&
        entry.itemName === targetEntry.itemName
    );
    if (originalIndex === -1) {
        seal.replyToSender(ctx, msg, "❌ 未找到对应记录，可能已被删除。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 删除该条记录
    log.splice(originalIndex, 1);
    main.storageSet("item_usage_log", JSON.stringify(log));

    // 格式化被删记录的信息
    const time = new Date(targetEntry.timestamp).toLocaleTimeString("zh-CN", { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    seal.replyToSender(ctx, msg, `🗑️ 已删除记录：${time} | ${targetEntry.roleName} 使用了「${targetEntry.itemName}」`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["删除使用记录"] = cmd_delete_usage_log;

// ========================
// 管理员指令：查看任意玩家背包
// ========================
let cmd_admin_view_bag = seal.ext.newCmdItemInfo();
cmd_admin_view_bag.name = "查看背包";
cmd_admin_view_bag.help = "【管理员指令】查看指定角色的背包内容\n" +
    "。查看背包 角色名\n" +
    "示例：。查看背包 张三";
cmd_admin_view_bag.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) return seal.replyToSender(ctx, msg, "❌ 权限不足。");

    const targetRoleName = cmdArgs.getArgN(1);
    if (!targetRoleName) return seal.replyToSender(ctx, msg, "❌ 请提供角色名。");

    const platform = msg.platform;
    const targetKey = `${platform}:${targetRoleName}`;
    // 直接借用 changriV1 的背包指令显示（合并转发格式）
    const main = getMainExt();
    if (main && typeof main._showBackpack === "function") {
        return main._showBackpack(ctx, msg, targetRoleName);
    }
    // fallback：纯文本列表
    const inv = ItemRoleUtils.getInv(targetKey).filter(i => !i.used);
    if (!inv.length) {
        seal.replyToSender(ctx, msg, `🎒 【${targetRoleName}】背包空空如也。`);
    } else {
        const lines = inv.map((it, i) => `${i + 1}. ${it.name} — ${it.desc}`);
        seal.replyToSender(ctx, msg, `🎒 【${targetRoleName}】的背包：\n${lines.join("\n")}`);
    }
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["查看背包"] = cmd_admin_view_bag;

// ========================
// 管理员指令：固定发放（从固定池中选取物品直接发给玩家）
// ========================
let cmd_fixed_give = seal.ext.newCmdItemInfo();
cmd_fixed_give.name = "固定发放";
cmd_fixed_give.help = "【管理员指令】从固定池中选择物品直接发放给指定角色\n" +
    "。固定发放 角色名 物品名 [数量] —— 数量默认为1，可选\n" +
    "示例：。固定发放 张三 手机 2\n" +
    "💡 物品名必须是固定池中已存在的物品，发放时不会从固定池中移除。";
cmd_fixed_give.solve = (ctx, msg, cmdArgs) => {
    if (!isUserAdmin(ctx, msg)) {
        seal.replyToSender(ctx, msg, "❌ 权限不足，仅管理员可操作。");
        return seal.ext.newCmdExecuteResult(true);
    }

    const targetRoleName = cmdArgs.getArgN(1);
    const itemName = cmdArgs.getArgN(2);
    let quantity = parseInt(cmdArgs.getArgN(3));
    if (isNaN(quantity) || quantity <= 0) quantity = 1;

    if (!targetRoleName || !itemName) {
        seal.replyToSender(ctx, msg, "❌ 用法：。固定发放 角色名 物品名 [数量]");
        return seal.ext.newCmdExecuteResult(true);
    }

    const platform = msg.platform;
    const main = getMainExt();
    if (!main) {
        seal.replyToSender(ctx, msg, "❌ 无法连接主插件。");
        return seal.ext.newCmdExecuteResult(true);
    }

    // 检查目标角色是否存在
    const a_private_group = JSON.parse(main.storageGet("a_private_group") || "{}");
    if (!a_private_group[platform]?.[targetRoleName]) {
        seal.replyToSender(ctx, msg, `❌ 角色「${targetRoleName}」未登记。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 从固定池中查找物品
    const fixedPool = FixedPoolUtils.getPool();
    const fixedItem = fixedPool.find(item => item.name === itemName);
    if (!fixedItem) {
        seal.replyToSender(ctx, msg, `❌ 固定池中没有名为「${itemName}」的物品。\n可使用「。固定放 查看」查看当前固定池内容。`);
        return seal.ext.newCmdExecuteResult(true);
    }

    // 获取目标背包
    const targetKey = `${platform}:${targetRoleName}`;
    let inv = ItemRoleUtils.getInv(targetKey);

    // 发放指定数量
    for (let i = 0; i < quantity; i++) {
        inv.push({
            name: fixedItem.name,
            desc: fixedItem.desc,
            used: false,
            createTime: Date.now(),
            source: "Admin (固定发放)",
            special: false   // 固定池物品通常不算特殊物品，如需特殊可自行修改
        });
    }

    ItemRoleUtils.setInv(targetKey, inv);
    seal.replyToSender(ctx, msg, `✅ 已从固定池发放 ${quantity} 个【${fixedItem.name}】给角色「${targetRoleName}」。\n描述：${fixedItem.desc}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["固定发放"] = cmd_fixed_give;

// ========================
// 🎲 查看今日抽取次数
// ========================
let cmd_draw_count = seal.ext.newCmdItemInfo();
cmd_draw_count.name = "抽取次数";
cmd_draw_count.help = "抽取次数 — 查看今日剩余抽取次数，不消耗机会";
cmd_draw_count.solve = (ctx, msg) => {
    const roleKey = ItemRoleUtils.getRoleKey(ctx, msg);
    if (!roleKey) return seal.replyToSender(ctx, msg, "⚠️ 请先绑定角色。");

    const today = ItemRoleUtils.getToday();
    const limit = seal.ext.getIntConfig(ext, "dailyDrawLimit");
    const records = ItemRoleUtils.getGlobalRecords();
    const myRec = records[roleKey] || { date: "", count: 0 };
    const todayCount = myRec.date === today ? myRec.count : 0;
    const remaining = limit - todayCount;

    const bar = "█".repeat(todayCount) + "░".repeat(remaining);
    seal.replyToSender(ctx, msg, `🎲 今日抽取进度 [${bar}] ${todayCount}/${limit}\n剩余 ${remaining} 次机会${remaining === 0 ? "，明日再来~" : "，发送「抽取」获得物品！"}`);
    return seal.ext.newCmdExecuteResult(true);
};
ext.cmdMap["抽取次数"] = cmd_draw_count;

// ========================
// 💬 无前缀指令触发
// ========================
ext.onNotCommandReceived = (ctx, msg) => {
    const raw = msg.message.trim();
    const makeFakeCmdArgs = (parts) => ({
        getArgN: (n) => parts[n - 1] || "",
        args: parts
    });

    if (raw === "抽取") return cmd_item_draw.solve(ctx, msg, makeFakeCmdArgs([]));
    if (raw === "抽取次数") return cmd_draw_count.solve(ctx, msg, makeFakeCmdArgs([]));

    // 使用：支持「使用 物品名」及「使用 物品名 参数」
    // 注意：赠送 由长日系统.js 的 onNotCommandReceived 统一处理，此处不重复响应
    if (raw.startsWith("使用")) {
        const rest = raw.slice(2).trim();
        if (rest) return cmd_item_use.solve(ctx, msg, makeFakeCmdArgs(rest.split(/\s+/)));
    }
};