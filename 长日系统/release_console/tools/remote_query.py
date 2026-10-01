#!/usr/bin/env python3
"""对服务器上的 sqlite 数据库跑一条只读查询，不用再手动拼 base64 绕开 Windows 的引号坑，
输出保证是干净的 UTF-8（之前直接 ssh 跑起来，中文字段偶尔会被 Windows 控制台代码页搅成乱码，
必须再接一道 `iconv -f GBK -t UTF-8`才能看；这里在远端强制把 stdout 编码锁死成 utf-8，从根上解决）。

用法：
  python3 remote_query.py "select count(*) from sessions"
  python3 remote_query.py --alias ultron --db "C:/Users/Administrator/rp_archive/rp_data.db" "select name from shows limit 5"

默认目标是 ultron 上 rp_archive 的主库（rp_data.db）——这是目前唯一会被这样查的库；
换库/换机器用 --alias / --db 覆盖。

只读：连接用 sqlite3 的 `mode=ro` URI 打开，就算查询语句写成 INSERT/UPDATE 也会被 sqlite 拒绝，
不会误改线上数据。
"""
import argparse
import base64
import json
import subprocess
import sys

REMOTE_PYTHON = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
DEFAULT_ALIAS = "ultron"
DEFAULT_DB = "C:/Users/Administrator/rp_archive/rp_data.db"


def build_remote_script(db_path: str, sql: str) -> str:
    # repr() 里的引号/反斜杠交给 Python 自己转义，不用在这一层手工处理 Windows 的转义规则
    return (
        "import sqlite3, json\n"
        f"conn = sqlite3.connect('file:{db_path}?mode=ro', uri=True)\n"
        "conn.row_factory = sqlite3.Row\n"
        f"rows = [dict(r) for r in conn.execute({sql!r}).fetchall()]\n"
        "print(json.dumps(rows, ensure_ascii=False, default=str, indent=2))\n"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sql", help="SQL 查询语句（整段用引号包起来）")
    ap.add_argument("--alias", default=DEFAULT_ALIAS, help=f"ssh 别名，默认 {DEFAULT_ALIAS}")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"服务器上的数据库路径，默认 {DEFAULT_DB}")
    args = ap.parse_args()

    remote_script = build_remote_script(args.db, args.sql)
    b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    # subprocess.run(list) 不经过本地 shell，这个字符串会原样交给 ssh，再由 Windows 上的 sshd
    # 转手给 cmd.exe /c 执行——所以这里只用一层给 python -c 参数的双引号就够了，不要在外面再套
    # 一层 cmd /c "..."，套了反而会因为 Windows 的引号转义规则把这段命令拆断（曾经这么写炸过）。
    # PYTHONIOENCODING 锁死远端 Python 的 stdout 编码，不受 Windows 控制台代码页（默认 GBK）影响，
    # 这是相比"跑完再 iconv -f GBK -t UTF-8"更靠谱的做法——从源头保证输出就是 UTF-8。
    remote_cmd = (
        f"set PYTHONIOENCODING=utf-8 && "
        f"{REMOTE_PYTHON} -c \"import base64;exec(base64.b64decode('{b64}'))\""
    )

    result = subprocess.run(
        ["ssh", args.alias, remote_cmd],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or f"（远端命令返回码 {result.returncode}，无 stderr 输出）\n")
        sys.exit(result.returncode or 1)

    out = result.stdout.strip()
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        # 查询本身在远端报了 Python 异常（比如 SQL 写错），原样打印方便排查
        print(out)
        sys.exit(1)

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\n({len(rows)} 行)", file=sys.stderr)


if __name__ == "__main__":
    main()
