/**
 * 转发复盘 —— 归档代码（已停用，保留备查）
 *
 * 原功能：在约会小群内回复合并转发消息并发送「转发复盘」，
 * 机器人将合并转发自动路由至后台群（或按天数分流），
 * 并将对应场次标记为 fupan=true。
 * 若 require_fupan_before_end 开启，结束私约前必须先完成此步骤。
 *
 * 停用原因：存档已迁移至 rparchive，无需手动转发。
 * 当前处理：有人触发时回复提示，直接结束私约即可。
 */

// ── 触发块（原位置：长日系统.js 消息监听 replyMatch 段内）────────────────
//
//   if (raw.includes("转发复盘")) {
//       // 防重复：检查当前群是否已复盘
//       const bSchedCheck = getS("b_confirmedSchedule");
//       const alreadyFupan = Object.values(bSchedCheck).flat().some(
//           ev => ev.group === groupId && ev.status === "active" && ev.fupan
//       );
//       if (alreadyFupan) return seal.replyToSender(ctx, msg, "⚠️ 当前群已完成复盘，请勿重复转发");
//
//       const fupanRouting = ext.storageGet("fupan_routing_enabled") === "true";
//       let targetId;
//       if (fupanRouting) {
//           let routingMap = {};
//           try { routingMap = JSON.parse(ext.storageGet("fupan_routing_groups") || "{}"); } catch (e) {}
//           const firstRoutingId = Object.values(routingMap)[0];
//           if (!firstRoutingId) return seal.replyToSender(ctx, msg, "❌ 未配置复盘群分流群，请先用「。复盘群分流群」配置");
//           // 找当前群对应约会的天数，然后查路由表
//           let appointmentDay = null;
//           for (const evList of Object.values(bSchedCheck)) {
//               for (const ev of evList) {
//                   if (ev.group === groupId && ev.status === "active") {
//                       appointmentDay = ev.day || null;
//                       break;
//                   }
//               }
//               if (appointmentDay !== null) break;
//           }
//           const dayKey = appointmentDay ? appointmentDay.toUpperCase() : null;
//           targetId = (dayKey && routingMap[dayKey]) ? routingMap[dayKey] : firstRoutingId;
//       } else {
//           targetId = ext.storageGet("background_group_id");
//           if (!targetId) return seal.replyToSender(ctx, msg, "未配置目标群");
//       }
//       const sourceName = ctx.group?.groupName || "未知群聊";
//       ext.storageSet("temp_target_gid", targetId);
//       ext.storageSet("temp_task_type", "forward");
//       ext.storageSet("temp_source_group_name", sourceName);
//       let bSched = getS("b_confirmedSchedule");
//       Object.values(bSched).flat().forEach(ev => {
//           if (ev.group === groupId && ev.status === "active") ev.fupan = true;
//       });
//       ext.storageSet("b_confirmedSchedule", JSON.stringify(bSched));
//       ws({ action: "get_msg", params: { message_id: wdId } }, ctx, msg);
//       return seal.replyToSender(ctx, msg, `已复盘至后台，请尽快结戏退群！`);
//   }


// ── 结束私约前的强制复盘检查（原位置：结束私约逻辑开头）──────────────────
//
//   // ----- 读取"复盘强制结束"开关 -----
//   const requireFupan = JSON.parse(ext.storageGet("require_fupan_before_end") || "false");
//   if (requireFupan) {
//       // ----- 复盘检查（参照更新 status 的遍历方式）-----
//       const b_confirmedSchedule = JSON.parse(ext.storageGet("b_confirmedSchedule") || "{}");
//       let needFupan = false;
//
//       for (let uidKey in b_confirmedSchedule) {
//           for (let ev of b_confirmedSchedule[uidKey]) {
//               if (ev.group === gid && ev.status === "active") {
//                   if (!ev.fupan) {
//                       needFupan = true;
//                       break;
//                   }
//               }
//           }
//           if (needFupan) break;
//       }
//
//       if (needFupan) {
//           seal.replyToSender(ctx, msg, `⚠️ 请先转发复盘，再结束私约。`);
//           return seal.ext.newCmdExecuteResult(true);
//       }
//   }
//   // 如果开关关闭，直接跳过复盘检查，继续结束流程


// ── 相关 rparchive 配置字段（原位置：app.py CONFIG_SCHEMA "复盘群"分区）──
//
//   {"key": "require_fupan_before_end", "label": "强制转发复盘", "type": "bool",    "default": "false"},
//   {"key": "fupan_routing_enabled",    "label": "复盘群分流",   "type": "bool",    "default": "false"},
//   {"key": "fupan_routing_groups",     "label": "分流群配置",   "type": "routing", "default": ""},
