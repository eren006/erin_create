#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验各 JS 插件里通过 kvGet/kvSet/cachedGet/cachedSet 读写过的 changri 存储 key，
是否都在 长日系统.js 的 CLEAR_KEYS 常量里有对应条目——「清空季度数据」按这份清单清空存储，
漏加新 key 就意味着清空季度后这个 key 的数据会跨季度残留（这个坑本 session 已经踩过至少两次：
a_generic_npc_list、season_created_at、sys_info_private_projects）。

用法：python3 check_clear_keys_coverage.py
退出码：发现未纳入 CLEAR_KEYS 的 key 时返回 1，否则返回 0（方便接入 pre-commit）。
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 忽略：一次性脚本目录、已归档目录（见项目记忆：长日extra/、_archive/ 不参与主系统维护）
IGNORE_DIR_PARTS = ("长日extra", "_archive")

# 跨季度持续生效的机器人级配置项，不是本季度 RP 数据，清空季度时不应该清——
# 对应 长日设置.js 的 SYNC_DIRECT_KEYS / SYNC_JSON_PARENT_KEYS / PUSH_ALL_BLOB_KEYS
# （这些都是「推送全部」会同步到网页端的机器人配置，跟季度生命周期无关）。
# 新增一个持续生效的配置 key 时，把它加进这份白名单，而不是加进 CLEAR_KEYS。
INTENTIONALLY_PERSISTENT = {
    # 2026-09-30 补：跨季保留的配置/标记
    "appointment_form_labels",            # 网页「邀约表单标签」配置
    "private_resources",                  # 私约资源注册表（resetPrivateDefaultResourceName 单独处理）
    "a_meetingCount_private_res:",        # 私约资源计数前缀（resetPrivateResourceCounts 单独清）
    "a_meetingCount_private_res_migrated",# 一次性迁移标记
    "sys_blocklist",                      # 玩家拉黑名单，按 QQ 记，视为跨季保留

    "a_adminList", "adminPassword",  # 清空季度时明确保留：管理员列表、密令
    "custom_type_labels", "force_end_grant_reward", "private_appointment_aliases",
    "sms_aliases", "gift_aliases",
    "stakeout_allow_solo", "ts_slot_mode",
    # 目前代码里只有读没有写，大概率是尚未接完的功能，暂按持续配置对待
    "ts_reality_slot_size",
    # 网页手机同步的记账数据，全部以存档站为准、不属于某一季：
    #  · *_ops_done / *_ops_started / *_done / *_seen：已处理的网页操作 id（防回报丢了重复执行），清了反而会重放
    #  · *_cursor：存档站表自增 id 的游标，只往前走，清了会把旧消息重新计一遍
    #  · *_web / phone_web_send / phone_rel_need：网页后台功能开关，每次同步整体重写
    "phone_admin_ops_done",
    "phone_admin_ops_started",
    "phone_block_ops_done",
    "phone_bottle_ops_done",
    "phone_rel_ops_done",
    "phone_wish_ops_done",
    "phone_wish_ops_started",
    "phone_lovemail_done",
    "phone_lovemail_revoke_done",
    "phone_lovemail_seen",
    "phone_songs_done",
    "phone_songs_seen",
    "phone_group_cursor",
    "phone_shop_cursor",
    "phone_web_cursor",
    "phone_bottle_web",
    "phone_rel_web",
    "phone_web_send",
    "phone_wish_web",
    "phone_rel_need",
    # 长日晚餐.js 是独立的 dinner_system 扩展，跟 changri 不是同一个存储命名空间，
    # 这两个 key 由 cmd_reset_season_data 里单独的 dinnerExt.storageSet(...) 循环清空，
    # 不归 changri 自己的 CLEAR_KEYS 管
    "guard_game_state", "guard_game_locations",
}

KEY_CALL_RE = re.compile(r'\b(?:kvGet|kvSet|cachedGet|cachedSet)\(\s*["\']([^"\']+)["\']')
CLEAR_KEYS_RE = re.compile(r'const CLEAR_KEYS = \[(.*?)\];', re.S)


def find_used_keys():
    keys = {}  # key -> [file, ...]
    for path in glob.glob(os.path.join(HERE, "*.js")):
        if any(part in path for part in IGNORE_DIR_PARTS):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for m in KEY_CALL_RE.finditer(text):
            keys.setdefault(m.group(1), set()).add(os.path.basename(path))
    return keys


def load_clear_keys():
    path = os.path.join(HERE, "长日系统.js")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = CLEAR_KEYS_RE.search(text)
    if not m:
        print("❌ 没在 长日系统.js 里找到 CLEAR_KEYS 常量，脚本假设失效，请检查。")
        sys.exit(2)
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def main():
    used_keys = find_used_keys()
    clear_keys = load_clear_keys()

    missing = sorted(
        k for k in used_keys
        if k not in clear_keys and k not in INTENTIONALLY_PERSISTENT
    )

    if not missing:
        print(f"✅ 全部 {len(used_keys)} 个存储 key 均已在 CLEAR_KEYS 或白名单中找到对应处理。")
        return 0

    print(f"⚠️ 共 {len(used_keys)} 个存储 key，{len(missing)} 个既不在 CLEAR_KEYS 也不在白名单中：\n")
    for k in missing:
        files = "、".join(sorted(used_keys[k]))
        print(f"  - {k}  (使用于 {files})")
    print("\n如果是本季度数据，请加进 长日系统.js 的 CLEAR_KEYS；如果是跨季度持续生效的配置，"
          "请加进本脚本的 INTENTIONALLY_PERSISTENT 白名单。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
