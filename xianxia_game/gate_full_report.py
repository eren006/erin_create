"""
只读统计脚本：汇总异世门(gate_event)所有历史活动的"每人应撤回灵石"，
并检测是否存在重复撤回的迹象。不修改任何数据。

判断逻辑：
  - 若该活动的 gate_ghost_pool 仍有数据 -> 说明还没被点过"撤回收益"，
    这是"现在点撤回会扣多少"的实时计算（与 app.py 里 rollback 逻辑一致）。
  - 若 gate_ghost_pool 已空 -> 说明已经被撤回过（或活动期间无人参与），
    退而从 char_logs / mail 重建当时的灵石数（可能因日志3天清理而不完整）。
  - 若同一个 event_id 在 gate_rollback_log 表里出现多次 -> 标记为"重复撤回"。
    （注：app.py 的撤回逻辑是从 gate_ghost_pool 实时计算的，pool 被清空后
    再次点击只会算出 0，所以灵石不会被重复扣，但日志表里出现多条记录仍值得核实。）

用法（服务器上，与 xianxia.db 同目录执行）：
    python3 gate_full_report.py
"""
import os
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "xianxia.db")

SELF_KILL_RE = re.compile(r'获得灵石\s*(\d+)\s*枚')
ASSIST_RE    = re.compile(r'已为你结算奖励：灵石\s*(\d+)\s*枚')


def fmt_ts(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))


def live_pool_debt(conn, ev_id):
    pools = conn.execute(
        "SELECT char_id, ghosts_json, defeated_ids FROM gate_ghost_pool WHERE event_id=?",
        (ev_id,)
    ).fetchall()
    if not pools:
        return None  # 已无活体数据
    debt = {}
    import json
    for p in pools:
        ghosts = json.loads(p['ghosts_json'] or '[]')
        defeated = set(json.loads(p['defeated_ids'] or '[]'))
        earned = sum(g['stones'] for g in ghosts if g['idx'] in defeated)
        if earned:
            debt[p['char_id']] = debt.get(p['char_id'], 0) + earned
    return debt


def reconstructed_debt(conn, start, end):
    debt = {}
    rows = conn.execute(
        """SELECT char_id, content FROM char_logs
           WHERE type='combat' AND created_at BETWEEN ? AND ?
             AND content LIKE '%获得灵石%'""",
        (start, end)
    ).fetchall()
    for r in rows:
        m = SELF_KILL_RE.search(r['content'])
        if m:
            debt[r['char_id']] = debt.get(r['char_id'], 0) + int(m.group(1))
    rows = conn.execute(
        """SELECT to_char, body FROM mail
           WHERE created_at BETWEEN ? AND ?
             AND body LIKE '%已为你结算奖励：灵石%'""",
        (start, end)
    ).fetchall()
    for r in rows:
        m = ASSIST_RE.search(r['body'])
        if m:
            debt[r['to_char']] = debt.get(r['to_char'], 0) + int(m.group(1))
    return debt


def char_name(conn, char_id):
    row = conn.execute("SELECT name FROM characters WHERE id=?", (char_id,)).fetchone()
    return row['name'] if row else f'#{char_id}'


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    has_log_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='gate_rollback_log'"
    ).fetchone()

    events = conn.execute("SELECT * FROM gate_event ORDER BY id").fetchall()
    if not events:
        print("没有任何异世门活动记录。")
        return

    print("=" * 60)
    print("异世门活动 灵石撤回统计")
    print("=" * 60)

    grand_total_per_player = {}

    for ev in events:
        ev_id = ev['id']
        print(f"\n活动 #{ev_id}  {fmt_ts(ev['started_at'])} ~ {fmt_ts(ev['ends_at'])}"
              f"  [{'进行中' if ev['is_active'] else '已结束'}]")

        debt = live_pool_debt(conn, ev_id)
        if debt is not None:
            source = '实时数据（尚未撤回，现在点"撤回收益"会扣这些）'
        else:
            end_bound = ev['actual_ended_at'] if ev['actual_ended_at'] else ev['ends_at']
            debt = reconstructed_debt(conn, ev['started_at'], end_bound)
            source = '已无 ghost_pool 数据，从日志/邮件重建（可能已撤回过，或日志已被清理）'
        print(f"  来源：{source}")

        if not debt:
            print("  （无灵石记录）")
        else:
            for cid, stones in sorted(debt.items(), key=lambda x: -x[1]):
                name = char_name(conn, cid)
                print(f"  - {name}: {stones} 灵石")
                grand_total_per_player[name] = grand_total_per_player.get(name, 0) + stones
            print(f"  小计：{len(debt)} 人，共 {sum(debt.values())} 灵石")

        # 重复撤回检测
        if has_log_table:
            log_rows = conn.execute(
                "SELECT char_name, stones, created_at FROM gate_rollback_log WHERE event_id=? ORDER BY created_at",
                (ev_id,)
            ).fetchall()
            if log_rows:
                batches = sorted(set(r['created_at'] for r in log_rows))
                if len(batches) > 1:
                    print(f"  ⚠ 检测到 gate_rollback_log 中该活动有 {len(batches)} 批不同时间的记录，"
                          f"可能被重复执行过撤回/重建：{[fmt_ts(b) for b in batches]}")
                else:
                    total_logged = sum(r['stones'] for r in log_rows)
                    print(f"  （gate_rollback_log 已有记录：{len(log_rows)} 条，合计 {total_logged} 灵石，正常单批）")

    print("\n" + "=" * 60)
    print("全部活动 - 每人累计应撤回灵石")
    print("=" * 60)
    if not grand_total_per_player:
        print("（无数据）")
    else:
        for name, total in sorted(grand_total_per_player.items(), key=lambda x: -x[1]):
            print(f"  {name}: {total} 灵石")
        print(f"\n  总计：{len(grand_total_per_player)} 人，{sum(grand_total_per_player.values())} 灵石")

    conn.close()


if __name__ == '__main__':
    main()
