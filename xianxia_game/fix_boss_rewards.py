"""
修复妖兽补发奖励混乱问题
将受影响玩家的灵石/灵符/修为回滚到补发之前的状态

用法：
  python fix_boss_rewards.py              # 只打印计划，不执行
  python fix_boss_rewards.py --apply      # 确认执行
"""
import sys, json, sqlite3, time

DB_PATH = "xianxia.db"
BOSS_HIT_ENERGY = 15

# ── 从事件日志推算操作历史 ────────────────────────────────────────────────────

def get_event():
    """找最近一次结束的妖兽事件"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # 最近一次发过安慰奖的事件
    ev = conn.execute(
        "SELECT * FROM world_events WHERE is_active=0 ORDER BY ends_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(ev) if ev else None

def get_participants(event_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT eh.char_id, eh.damage, eh.hits, c.name, c.spirit_stones, c.lingfu, c.exp "
        "FROM event_hits eh JOIN characters c ON c.id=eh.char_id "
        "WHERE eh.event_id=?", (event_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def calc_consolation(event, participants):
    """计算每人一次安慰奖金额（30%）"""
    total_dmg = sum(p['damage'] for p in participants) or 1
    total_en  = sum(p['hits'] * BOSS_HIT_ENERGY for p in participants) or 1
    c_stones  = int(event['clear_bonus_stones'] * 0.30)
    c_lingfu  = int(event['clear_bonus_lingfu']  * 0.30)
    n = len(participants)
    result = {}
    for p in participants:
        dr = p['damage'] / total_dmg
        er = (p['hits'] * BOSS_HIT_ENERGY) / total_en
        ratio = (dr + er) / 2
        result[p['char_id']] = {
            'stones': int(c_stones * n * ratio),
            'lingfu': int(c_lingfu * n * ratio),
        }
    return result

def calc_wrong_revoke(event, participants):
    """计算错误撤回公式（用了满额奖励的公式）"""
    total_dmg = sum(p['damage'] for p in participants) or 1
    total_en  = sum(p['hits'] * BOSS_HIT_ENERGY for p in participants) or 1
    b_stones  = event['clear_bonus_stones']
    b_lingfu  = event['clear_bonus_lingfu']
    ex_stones = b_stones * len(participants)
    ex_lingfu = b_lingfu * len(participants)
    result = {}
    for p in participants:
        dr = p['damage'] / total_dmg
        er = (p['hits'] * BOSS_HIT_ENERGY) / total_en
        ratio = (dr + er) / 2
        result[p['char_id']] = {
            'stones': int((b_stones + ex_stones * ratio)),
            'lingfu': int((b_lingfu + ex_lingfu * ratio)),
        }
    return result

def get_recent_logs(char_id, since_ts):
    """获取某时间点之后的系统日志"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT content, created_at FROM char_logs "
        "WHERE char_id=? AND created_at>=? AND type='system' "
        "ORDER BY created_at", (char_id, since_ts)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── 主逻辑 ────────────────────────────────────────────────────────────────────

def main():
    apply_mode = '--apply' in sys.argv

    event = get_event()
    if not event:
        print("找不到事件！")
        return

    print(f"\n事件：{event['name']}  ID={event['id']}")
    print(f"通关奖励：{event['clear_bonus_stones']}石 / {event['clear_bonus_lingfu']}符\n")

    participants = get_participants(event['id'])
    if not participants:
        print("无参与者记录")
        return

    consolation  = calc_consolation(event, participants)
    wrong_revoke = calc_wrong_revoke(event, participants)

    # 事件结束时间作为起点
    since_ts = event['ends_at'] - 60  # 稍微往前一点

    print(f"{'玩家':<12} {'当前灵石':>10} {'当前灵符':>8} {'调整灵石':>12} {'调整灵符':>10} {'修为':>12} {'目标灵石':>12}")
    print("-" * 90)

    adjustments = []
    for p in participants:
        cid   = p['char_id']
        c1    = consolation.get(cid, {})
        c_st  = c1.get('stones', 0)
        c_lf  = c1.get('lingfu', 0)
        wk    = wrong_revoke.get(cid, {})
        wk_st = wk.get('stones', 0)
        wk_lf = wk.get('lingfu', 0)

        # 操作历史重建：
        # 1. +3×consolation  2. -wrong_revoke（可能被cap）  3. +wrong_restore（无exp）
        # 净效果 = 3×c - min(wk, balance_at_revoke_time) + wk
        # 如果被cap：净 = 3c - cap + wk = 3c + (wk - cap)  ← 偏多
        # 如果未cap：净 = 3c - wk + wk = 3c                ← 干净

        # 看日志里有无撤回记录（判断是否被cap）
        logs = get_recent_logs(cid, since_ts)
        revoked_stones = 0
        revoked_lingfu = 0
        exp_lost       = 0
        for lg in logs:
            t = lg['content']
            if '撤回' in t and '重复奖励' in t:
                # 解析：灵石 -XXXXX
                import re
                m = re.search(r'灵石 -(\d+)', t)
                if m: revoked_stones += int(m.group(1))
                m = re.search(r'灵符 -(\d+)', t)
                if m: revoked_lingfu += int(m.group(1))
                m = re.search(r'修为 -(\d+)', t)
                if m: exp_lost += int(m.group(1))

        # 净调整 = 当前 → 补发前
        # 现在的多余量 = 3×consolation + restore - revoked_actual
        # restore ≈ wrong_revoke_formula（stones only）
        net_stone_excess  = c_st * 3 + wk_st - revoked_stones
        net_lingfu_excess = c_lf * 3 + wk_lf - revoked_lingfu

        target_stones = max(0, p['spirit_stones'] - net_stone_excess)
        target_lingfu = max(0, p['lingfu'] - net_lingfu_excess)
        exp_add       = exp_lost  # 补回被错扣的修为

        stone_delta  = target_stones - p['spirit_stones']
        lingfu_delta = target_lingfu - (p['lingfu'] or 0)

        print(f"{p['name']:<12} {p['spirit_stones']:>10,} {p['lingfu'] or 0:>8,} "
              f"{stone_delta:>+12,} {lingfu_delta:>+10,} {'(不动)':>12} {target_stones:>12,}")

        adjustments.append({
            'char_id': cid, 'name': p['name'],
            'target_stones': target_stones,
            'target_lingfu': target_lingfu,
            'exp_add': 0,  # 修为不自动调整，避免误算
        })

    print("\n" + ("=" * 90))
    if not apply_mode:
        print("\n⚠  以上为预览。确认无误后运行：  python fix_boss_rewards.py --apply")
        return

    print("\n正在执行...")
    conn = sqlite3.connect(DB_PATH)
    ts = int(time.time())
    for adj in adjustments:
        conn.execute(
            "UPDATE characters SET spirit_stones=?, lingfu=?, exp=exp+? WHERE id=?",
            (adj['target_stones'], adj['target_lingfu'], adj['exp_add'], adj['char_id'])
        )
        msg = (f"[管理修复] 回滚补发奖励：灵石→{adj['target_stones']}，"
               f"灵符→{adj['target_lingfu']}")
        if adj['exp_add']:
            msg += f"，补回修为+{adj['exp_add']}"
        conn.execute(
            "INSERT INTO char_logs (char_id,type,content,created_at) VALUES (?,?,?,?)",
            (adj['char_id'], 'system', msg, ts)
        )
    conn.commit()
    conn.close()
    print("✓ 完成！")

if __name__ == '__main__':
    main()
