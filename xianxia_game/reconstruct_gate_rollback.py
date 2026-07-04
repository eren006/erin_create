"""
一次性脚本：从 char_logs / mail 重建已撤回的异世门活动(#1~#4)的逐人灵石明细，
写入 gate_rollback_log 表，使其能在 /admin/gate 的"撤回记录"里显示。

用法（在服务器上，xianxia.db 同目录下执行）：
    python3 reconstruct_gate_rollback.py

只读 char_logs 和 mail 重建，幂等：已存在记录的活动会被跳过，不会重复插入。
"""
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "xianxia.db")

SELF_KILL_RE = re.compile(r'获得灵石\s*(\d+)\s*枚')
ASSIST_RE    = re.compile(r'已为你结算奖励：灵石\s*(\d+)\s*枚')


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 确保表存在（与 app.py 中定义一致）
    conn.execute("""CREATE TABLE IF NOT EXISTS gate_rollback_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id   INTEGER NOT NULL,
        char_id    INTEGER NOT NULL,
        char_name  TEXT NOT NULL,
        stones     INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )""")

    events = conn.execute(
        "SELECT * FROM gate_event WHERE is_active=0 ORDER BY id"
    ).fetchall()

    if not events:
        print("没有找到任何已结束的异世门活动。")
        return

    for ev in events:
        ev_id = ev['id']
        existing = conn.execute(
            "SELECT COUNT(*) c FROM gate_rollback_log WHERE event_id=?", (ev_id,)
        ).fetchone()['c']
        if existing:
            print(f"活动 #{ev_id}：已有 {existing} 条记录，跳过。")
            continue

        start, end = ev['started_at'], ev['ends_at']
        stone_debt = {}  # char_id -> stones

        # 1. 自行击败鬼魔的战斗日志
        rows = conn.execute(
            """SELECT char_id, content FROM char_logs
               WHERE type='combat' AND created_at BETWEEN ? AND ?
                 AND content LIKE '%获得灵石%'""",
            (start, end)
        ).fetchall()
        for r in rows:
            m = SELF_KILL_RE.search(r['content'])
            if m:
                stone_debt[r['char_id']] = stone_debt.get(r['char_id'], 0) + int(m.group(1))

        # 2. 求救帖被援助后通过系统邮件结算的灵石
        rows = conn.execute(
            """SELECT to_char, body FROM mail
               WHERE created_at BETWEEN ? AND ?
                 AND body LIKE '%已为你结算奖励：灵石%'""",
            (start, end)
        ).fetchall()
        for r in rows:
            m = ASSIST_RE.search(r['body'])
            if m:
                stone_debt[r['to_char']] = stone_debt.get(r['to_char'], 0) + int(m.group(1))

        if not stone_debt:
            print(f"活动 #{ev_id}：未在日志/邮件中找到任何灵石记录（可能已超过3天日志保留期被清理）。")
            continue

        for char_id, stones in stone_debt.items():
            name_row = conn.execute(
                "SELECT name FROM characters WHERE id=?", (char_id,)
            ).fetchone()
            char_name = name_row['name'] if name_row else f'#{char_id}'
            conn.execute(
                """INSERT INTO gate_rollback_log (event_id, char_id, char_name, stones, created_at)
                   VALUES (?,?,?,?,?)""",
                (ev_id, char_id, char_name, stones, end)
            )

        total = sum(stone_debt.values())
        print(f"活动 #{ev_id}：重建 {len(stone_debt)} 名玩家，共 {total} 灵石。")

    conn.commit()
    conn.close()
    print("完成。刷新 /admin/gate 页面查看撤回记录。")


if __name__ == '__main__':
    main()
