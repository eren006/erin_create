// 排单宝 Bot 对接插件 for Seal Dice
// 订单指令：
//   .排单同步            — 拉取新订单到当前群（手动 pull）
//   .未接单              — 列出所有待处理订单
//   .查单 ORD-xxx        — 查询订单状态
//   .接单 ORD-xxx        — 接受订单
//   .完成单 ORD-xxx [说明] — 完成订单（自动删图）
//   .拒单 ORD-xxx [原因]   — 拒绝订单（自动删图）
//   .加急 ORD-xxx        — 标记订单为加急
//   .催单 ORD-xxx        — 记录一次催单
// 卡指令：
//   .同步卡 QQ号 昵称 总数 剩余 — 同步用户卡信息到 UI
//   .查卡 QQ号            — 查询某用户卡余量
//   .用卡 QQ号            — 消耗一张卡
//   .所有卡               — 列出所有用户卡情况

(function () {
    const ext = seal.ext.find('排单宝') || seal.ext.new('排单宝', 'yuca', '1.1.0');
    if (seal.ext.find('排单宝')) return; // 已加载则跳过

    seal.ext.registerStringConfig(ext, '服务器地址', 'http://47.99.64.227:5237', '排单宝服务器地址，结尾不要加 /');
    seal.ext.registerStringConfig(ext, 'API Token', '', '超管后台创建账户时生成的 Token');

    // ── 工具函数 ─────────────────────────────────────────────────────────────

    function cfg() {
        return {
            base:     seal.ext.getStringConfig(ext, '服务器地址').replace(/\/$/, ''),
            token:    seal.ext.getStringConfig(ext, 'API Token'),
            interval: seal.ext.getIntConfig(ext, '自动同步间隔(秒)'),
        };
    }

    async function api(path, method = 'GET', body = null) {
        const { base, token } = cfg();
        const opts = {
            method,
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        };
        if (body) opts.body = JSON.stringify(body);
        try {
            const r = await fetch(`${base}${path}`, opts);
            return await r.json();
        } catch (e) {
            return { ok: false, error: String(e) };
        }
    }

    function fmtOrder(o) {
        let s = `📋 【新订单】\n`;
        s += `回执号：${o.order_no}\n`;
        s += `类型：${o.service_type}\n`;
        s += `标题：${o.title}\n`;
        s += `客户：${o.customer_name}（${o.customer_contact}）\n`;
        if (o.description) s += `说明：${o.description}\n`;
        s += `下单时间：${o.created_fmt}\n`;
        if (o.images && o.images.length > 0) {
            s += `\n附图 ${o.images.length} 张：\n`;
            o.images.forEach(img => {
                s += `[CQ:image,url=${img.url}]\n`;
            });
        }
        s += `\n✅ 接单：.接单 ${o.order_no}\n❌ 拒单：.拒单 ${o.order_no} [原因]`;
        return s;
    }

    // ── 指令：排单同步 ───────────────────────────────────────────────────────
    const cmdSync = seal.ext.newCmdItemInfo();
    cmdSync.name = '排单同步';
    cmdSync.help = '手动拉取并推送新订单到本群';
    cmdSync.solve = async (ctx, msg, cmdArgs) => {
        const data = await api('/api/sync');
        if (!data.ok) {
            seal.replyToSender(ctx, msg, `❌ 同步失败：${data.error}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        if (data.count === 0) {
            seal.replyToSender(ctx, msg, '暂无新订单 ✓');
            return seal.ext.newCmdExecuteResult(true);
        }
        for (const o of data.orders) {
            seal.replyToSender(ctx, msg, fmtOrder(o));
        }
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['排单同步'] = cmdSync;

    // ── 指令：未接单 ─────────────────────────────────────────────────────────
    const cmdPending = seal.ext.newCmdItemInfo();
    cmdPending.name = '未接单';
    cmdPending.help = '列出所有待处理订单';
    cmdPending.solve = async (ctx, msg, cmdArgs) => {
        const data = await api('/api/orders?status=pending&limit=20');
        if (!data.ok || data.count === 0) {
            seal.replyToSender(ctx, msg, '暂无待处理订单 ✓');
            return seal.ext.newCmdExecuteResult(true);
        }
        let text = `📋 待处理订单（${data.count} 条）\n`;
        data.orders.forEach(o => {
            text += `──────────\n${o.order_no}\n${o.title}｜${o.service_type}｜${o.customer_name}\n`;
        });
        text += `──────────\n.接单 <回执号> 接受`;
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['未接单'] = cmdPending;

    // ── 指令：查单 ──────────────────────────────────────────────────────────
    const cmdQuery = seal.ext.newCmdItemInfo();
    cmdQuery.name = '查单';
    cmdQuery.help = '查单 <回执号>';
    cmdQuery.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) {
            seal.replyToSender(ctx, msg, '用法：.查单 ORD-xxxxxxxx-XXXXXX');
            return seal.ext.newCmdExecuteResult(true);
        }
        const data = await api(`/api/orders/${orderNo}`);
        if (!data.ok) {
            seal.replyToSender(ctx, msg, `❌ 找不到订单：${orderNo}`);
            return seal.ext.newCmdExecuteResult(true);
        }
        const o = data.order;
        let text = `📋 订单详情\n`;
        text += `回执号：${o.order_no}\n`;
        text += `状态：${o.status_label}\n`;
        text += `标题：${o.title}\n`;
        text += `类型：${o.service_type}\n`;
        text += `客户：${o.customer_name}（${o.customer_contact}）\n`;
        text += `下单时间：${o.created_fmt}`;
        if (o.result_text) text += `\n完成说明：${o.result_text}`;
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['查单'] = cmdQuery;

    // ── 指令：接单 ──────────────────────────────────────────────────────────
    const cmdAccept = seal.ext.newCmdItemInfo();
    cmdAccept.name = '接单';
    cmdAccept.help = '接单 <回执号>';
    cmdAccept.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) {
            seal.replyToSender(ctx, msg, '用法：.接单 ORD-xxxxxxxx-XXXXXX');
            return seal.ext.newCmdExecuteResult(true);
        }
        const data = await api(`/api/orders/${orderNo}/accept`, 'POST', {
            note: `${ctx.player.name} 通过机器人接单`
        });
        seal.replyToSender(ctx, msg, data.ok
            ? `✅ 已接单：${orderNo}`
            : `❌ 失败：${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['接单'] = cmdAccept;

    // ── 指令：完成单 ─────────────────────────────────────────────────────────
    const cmdComplete = seal.ext.newCmdItemInfo();
    cmdComplete.name = '完成单';
    cmdComplete.help = '完成单 <回执号> [完成说明]';
    cmdComplete.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) {
            seal.replyToSender(ctx, msg, '用法：.完成单 ORD-xxxxxxxx-XXXXXX [说明]');
            return seal.ext.newCmdExecuteResult(true);
        }
        // 第2个参数起拼成说明
        const parts = [];
        for (let i = 2; ; i++) {
            const a = cmdArgs.getArgN(i);
            if (!a) break;
            parts.push(a);
        }
        const resultText = parts.join(' ');
        const data = await api(`/api/orders/${orderNo}/complete`, 'POST', { result_text: resultText });
        if (data.ok) {
            let reply = `✅ 订单已完成：${orderNo}`;
            if (data.notify_message) reply += `\n\n${data.notify_message}`;
            seal.replyToSender(ctx, msg, reply);
        } else {
            seal.replyToSender(ctx, msg, `❌ 失败：${data.error}`);
        }
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['完成单'] = cmdComplete;

    // ── 指令：拒单 ──────────────────────────────────────────────────────────
    const cmdReject = seal.ext.newCmdItemInfo();
    cmdReject.name = '拒单';
    cmdReject.help = '拒单 <回执号> [原因]';
    cmdReject.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) {
            seal.replyToSender(ctx, msg, '用法：.拒单 ORD-xxxxxxxx-XXXXXX [原因]');
            return seal.ext.newCmdExecuteResult(true);
        }
        const parts = [];
        for (let i = 2; ; i++) {
            const a = cmdArgs.getArgN(i);
            if (!a) break;
            parts.push(a);
        }
        const reason = parts.join(' ');
        const data = await api(`/api/orders/${orderNo}/reject`, 'POST', { reason });
        seal.replyToSender(ctx, msg, data.ok
            ? `已拒绝：${orderNo}${reason ? `（${reason}）` : ''}`
            : `❌ 失败：${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['拒单'] = cmdReject;

    // ── 指令：加急 ──────────────────────────────────────────────────────────
    const cmdUrgent = seal.ext.newCmdItemInfo();
    cmdUrgent.name = '加急';
    cmdUrgent.help = '加急 <回执号>';
    cmdUrgent.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) { seal.replyToSender(ctx, msg, '用法：.加急 ORD-xxx'); return seal.ext.newCmdExecuteResult(true); }
        const data = await api(`/api/orders/${orderNo}/urgent`, 'POST', {});
        seal.replyToSender(ctx, msg, data.ok ? `🚨 已标记加急：${orderNo}` : `❌ ${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['加急'] = cmdUrgent;

    // ── 指令：催单 ──────────────────────────────────────────────────────────
    const cmdRush = seal.ext.newCmdItemInfo();
    cmdRush.name = '催单';
    cmdRush.help = '催单 <回执号>';
    cmdRush.solve = async (ctx, msg, cmdArgs) => {
        const orderNo = cmdArgs.getArgN(1);
        if (!orderNo) { seal.replyToSender(ctx, msg, '用法：.催单 ORD-xxx'); return seal.ext.newCmdExecuteResult(true); }
        const data = await api(`/api/orders/${orderNo}/rush`, 'POST', {
            actor: ctx.player.name, note: `${ctx.player.name} 发起催单`
        });
        seal.replyToSender(ctx, msg, data.ok ? `⏰ 已记录催单，累计 ${data.rush_count} 次：${orderNo}` : `❌ ${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['催单'] = cmdRush;

    // ── 指令：同步卡 ─────────────────────────────────────────────────────────
    // 用法：.同步卡 QQ号 昵称 总数 剩余
    const cmdSyncCard = seal.ext.newCmdItemInfo();
    cmdSyncCard.name = '同步卡';
    cmdSyncCard.help = '同步卡 <QQ号> <昵称> <总数> <剩余>';
    cmdSyncCard.solve = async (ctx, msg, cmdArgs) => {
        const uid    = cmdArgs.getArgN(1);
        const dname  = cmdArgs.getArgN(2);
        const total  = parseInt(cmdArgs.getArgN(3)) || 0;
        const rem    = parseInt(cmdArgs.getArgN(4) ?? cmdArgs.getArgN(3)) || total;
        if (!uid) { seal.replyToSender(ctx, msg, '用法：.同步卡 QQ号 昵称 总数 [剩余]'); return seal.ext.newCmdExecuteResult(true); }
        const data = await api('/api/users/sync', 'POST', {
            platform_uid: uid, display_name: dname || uid,
            card_total: total, card_remaining: rem
        });
        seal.replyToSender(ctx, msg, data.ok ? `✅ 已同步：${dname || uid}，剩余 ${data.card_remaining} 张` : `❌ ${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['同步卡'] = cmdSyncCard;

    // ── 指令：查卡 ──────────────────────────────────────────────────────────
    const cmdQueryCard = seal.ext.newCmdItemInfo();
    cmdQueryCard.name = '查卡';
    cmdQueryCard.help = '查卡 <QQ号>';
    cmdQueryCard.solve = async (ctx, msg, cmdArgs) => {
        const uid = cmdArgs.getArgN(1);
        if (!uid) { seal.replyToSender(ctx, msg, '用法：.查卡 QQ号'); return seal.ext.newCmdExecuteResult(true); }
        const data = await api('/api/users');
        if (!data.ok) { seal.replyToSender(ctx, msg, `❌ ${data.error}`); return seal.ext.newCmdExecuteResult(true); }
        const u = data.users.find(x => x.platform_uid === uid);
        if (!u) { seal.replyToSender(ctx, msg, `找不到用户：${uid}`); return seal.ext.newCmdExecuteResult(true); }
        seal.replyToSender(ctx, msg, `🃏 ${u.display_name || u.platform_uid}\n剩余：${u.card_remaining} / ${u.card_total} 张`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['查卡'] = cmdQueryCard;

    // ── 指令：用卡 ──────────────────────────────────────────────────────────
    const cmdUseCard = seal.ext.newCmdItemInfo();
    cmdUseCard.name = '用卡';
    cmdUseCard.help = '用卡 <QQ号>';
    cmdUseCard.solve = async (ctx, msg, cmdArgs) => {
        const uid = cmdArgs.getArgN(1);
        if (!uid) { seal.replyToSender(ctx, msg, '用法：.用卡 QQ号'); return seal.ext.newCmdExecuteResult(true); }
        const data = await api(`/api/users/${uid}/use_card`, 'POST', {});
        seal.replyToSender(ctx, msg, data.ok ? `✅ 已扣卡，剩余 ${data.card_remaining} 张` : `❌ ${data.error}`);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['用卡'] = cmdUseCard;

    // ── 指令：所有卡 ─────────────────────────────────────────────────────────
    const cmdAllCards = seal.ext.newCmdItemInfo();
    cmdAllCards.name = '所有卡';
    cmdAllCards.help = '列出所有用户卡余量';
    cmdAllCards.solve = async (ctx, msg, cmdArgs) => {
        const data = await api('/api/users');
        if (!data.ok || data.count === 0) { seal.replyToSender(ctx, msg, '暂无注册用户'); return seal.ext.newCmdExecuteResult(true); }
        let text = `🃏 卡余量（${data.count} 人）\n`;
        data.users.forEach(u => {
            const bar = '■'.repeat(Math.min(u.card_remaining, 10)) + '□'.repeat(Math.max(0, 10 - Math.min(u.card_remaining, 10)));
            text += `──\n${u.display_name || u.platform_uid}：${u.card_remaining}/${u.card_total}  ${bar}\n`;
        });
        seal.replyToSender(ctx, msg, text);
        return seal.ext.newCmdExecuteResult(true);
    };
    ext.cmdMap['所有卡'] = cmdAllCards;

    seal.ext.register(ext);
})();
