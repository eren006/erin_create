"""
修正脚本：reconstruct_gate_rollback.py 用活动的 started_at~ends_at 时间窗口
去匹配 char_logs/mail，但由于这几个异世门活动是连续快速开启/手动结束的，
ends_at 是固定的"开启时+72小时"，并不是真实结束时间，导致窗口互相重叠，
同一条击杀记录被重复算进了多个活动，得出的"撤回记录"总额虚高。

本脚本改用正确的归属规则：一条击杀记录属于"发生时刻之前最近一次开启
的活动"（因为同一时间只能有一个活动 is_active=1，活动之间不会真正重叠），
重新计算每个活动的逐人灵石，并替换掉 gate_rollback_log 里之前算错的记录。

执行前会自动把旧的 gate_rollback_log 整表备份到 gate_rollback_log_bak_<时间戳>，
不会直接删数据，可随时回滚。

用法（服务器上，与 xianxia.db 同目录执行）：
    python3 gate_fix_rollback_log.py
"""
import os
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "xianxia.db")

SELF_KILL_RE = re.compile(r'击败.*获得灵石\s*(\d+)\s*枚')
ASSIST_RE    = re.compile(r'已为你结算奖励：灵石\s*(\d+)\s*枚')


def fmt_ts(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    events = conn.execute(
        "SELECT id, started_at, ends_at FROM gate_event ORDER BY started_at"
    ).fetchall()
    if not events:
        print("没有任何异世门活动记录。")
        return

    # 备份旧表
    bak_name = f"gate_rollback_log_bak_{int(time.time())}"
    conn.execute(f"CREATE TABLE {bak_name} AS SELECT * FROM gate_rollback_log")
    old_cnt = conn.execute("SELECT COUNT(*) c FROM gate_rollback_log").fetchone()['c']
    print(f"旧 gate_rollback_log 共 {old_cnt} 条，已备份到表 {bak_name}（未删除，可回滚）。")

    def assign_event(ts):
        """返回 ts 这个时间点应该归属的活动 id：取开始时间 <= ts 的最近一个活动"""
        target = None
        for ev in events:
            if ev['started_at'] <= ts:
                target = ev['id']
            else:
                break
        return target

    # 拉取全部原始记录，按正确活动重新分组
    stream = []
    rows = conn.execute(
        """SELECT char_id, content, created_at FROM char_logs
           WHERE type='combat' AND content LIKE '%获得灵石%' ORDER BY created_at"""
    ).fetchall()
    for r in rows:
        m = SELF_KILL_RE.search(r['content'])
        if m:
            stream.append((r['created_at'], r['char_id'], int(m.group(1))))
    rows = conn.execute(
        """SELECT to_char, body, created_at FROM mail
           WHERE body LIKE '%已为你结算奖励：灵石%' ORDER BY created_at"""
    ).fetchall()
    for r in rows:
        m = ASSIST_RE.search(r['body'])
        if m:
            stream.append((r['created_at'], r['to_char'], int(m.group(1))))
    stream.sort(key=lambda x: x[0])

    per_event = {}  # event_id -> {char_id: stones}
    for ts, cid, stones in stream:
        ev_id = assign_event(ts)
        if ev_id is None:
            continue  # 早于第一个活动开启，理论上不该有
        per_event.setdefault(ev_id, {})
        per_event[ev_id][cid] = per_event[ev_id].get(cid, 0) + stones

    name_cache = {}
    def get_name(cid):
        if cid not in name_cache:
            row = conn.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()
            name_cache[cid] = row['name'] if row else f'#{cid}'
        return name_cache[cid]

    # 清空旧记录，写入修正后的记录
    conn.execute("DELETE FROM gate_rollback_log")
    grand_total = 0
    print("\n修正后的撤回记录：")
    for ev in events:
        ev_id = ev['id']
        debt = per_event.get(ev_id, {})
        if not debt:
            continue
        total = sum(debt.values())
        grand_total += total
        print(f"\n活动 #{ev_id}（开启于 {fmt_ts(ev['started_at'])}）：{len(debt)} 人，合计 {total} 灵石")
        for cid, stones in sorted(debt.items(), key=lambda x: -x[1]):
            name = get_name(cid)
            print(f"  - {name}: {stones} 灵石")
            conn.execute(
                """INSERT INTO gate_rollback_log (event_id, char_id, char_name, stones, created_at)
                   VALUES (?,?,?,?,?)""",
                (ev_id, cid, name, stones, ev['ends_at'])
            )

    conn.commit()
    print(f"\n修正完成，4 个活动合计 {grand_total} 灵石（之前错误显示的总数已被替换）。")
    conn.close()


if __name__ == '__main__':
    main()
