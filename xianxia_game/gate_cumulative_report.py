"""
只读统计脚本：不按活动(event)分段估算，而是直接扫描 char_logs / mail 里
所有"异世门击败鬼魔获得灵石"的原始记录，按时间顺序逐条累加，
得到每个人从有记录以来一共应该撤回多少灵石。不修改任何数据。

匹配规则（与 app.py 里写日志的原文一致）：
  - 自行击败：char_logs, type='combat', content 形如 "击败【XX】，获得灵石 N 枚..."
  - 被援助结算：mail, body 形如 "...已为你结算奖励：灵石 N 枚..."

注意：char_logs 里非 encounter/system 类型的记录会被定时任务在 3 天后清理
（见 app.py 的 run_snapshot），所以"从0点开始"实际上只能累加到当前数据库
里还留存的部分，更早的部分已经物理删除、无法找回。

用法（服务器上，与 xianxia.db 同目录执行）：
    python3 gate_cumulative_report.py
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
        "SELECT id, char_id, content, created_at FROM char_logs "
        "WHERE type='combat' AND content LIKE '%获得灵石%' ORDER BY created_at"
    ).fetchall()
    mails = conn.execute(
        "SELECT id, to_char, body, created_at FROM mail "
        "WHERE body LIKE '%已为你结算奖励：灵石%' ORDER BY created_at"
    ).fetchall()

    # 合并成统一的事件流，按时间排序
    stream = []
    for r in events:
        m = SELF_KILL_RE.search(r['content'])
        if m:
            stream.append((r['created_at'], r['char_id'], int(m.group(1)), '自行击败'))
    for r in mails:
        m = ASSIST_RE.search(r['body'])
        if m:
            stream.append((r['created_at'], r['to_char'], int(m.group(1)), '援助结算'))
    stream.sort(key=lambda x: x[0])

    if not stream:
        print("char_logs / mail 中没有找到任何异世门灵石记录"
              "（可能日志已超过3天保留期被清理，或异世门尚未产生过击杀）。")
        return

    name_cache = {}
    def get_name(cid):
        if cid not in name_cache:
            row = conn.execute("SELECT name FROM characters WHERE id=?", (cid,)).fetchone()
            name_cache[cid] = row['name'] if row else f'#{cid}'
        return name_cache[cid]

    running = {}  # char_id -> running total
    print("=" * 70)
    print(f"异世门灵石累计明细（共 {len(stream)} 条记录，按时间顺序累加）")
    print("=" * 70)
    for ts, cid, stones, kind in stream:
        running[cid] = running.get(cid, 0) + stones
        print(f"{fmt_ts(ts)}  {get_name(cid):<10}  +{stones:<5} 灵石  [{kind}]  "
              f"-> 累计 {running[cid]}")

    print("\n" + "=" * 70)
    print("每人总计应撤回灵石")
    print("=" * 70)
    for cid, total in sorted(running.items(), key=lambda x: -x[1]):
        print(f"  {get_name(cid)}: {total} 灵石")
    print(f"\n  共 {len(running)} 人，合计 {sum(running.values())} 灵石")

    conn.close()


if __name__ == '__main__':
    main()
