#!/usr/bin/env python3
"""
修复 sessions 统计数据的一次性脚本。

背景：sessions.total_words / total_replies / stats 正常由 bot 推送的
/api/session_stats、/api/session_end 覆盖写入（countWords 口径：汉字+英文单词）。
如果覆盖没落地（档期 pre 期误判、网络失败），该行会停留在 /api/rp 的
entry 累加值（len() 字符数、每条 entry 算一段），数字是错的。

本脚本从 rp_entries 按 bot 同款 countWords 算法重算 stats：
- 默认只修 stats 为空的场次（即覆盖从未落地的）
- --all 重算所有场次（配合后台把闲聊 entry 标记为"排除"后，可把闲聊从统计中剔除）
- is_excluded=1 的 entry 不计入统计
- NPC 角色（players.is_npc=1）不计入 stats，与 bot 行为一致
- 修完后重算 players 表的累计字数/段数/场次数

用法：
    python3 repair_stats.py                # 只修 stats 为空的场次
    python3 repair_stats.py --all          # 重算全部场次
    python3 repair_stats.py --show-id 3    # 只处理指定季
    python3 repair_stats.py --dry-run      # 只打印将要修改的内容，不写库
"""
import argparse, json, os, re, sqlite3, sys

DB_PATH = os.path.join(os.path.dirname(__file__), "rp_data.db")

CQ_RE      = re.compile(r"\[CQ:[^\]]*\]")
CHINESE_RE = re.compile(r"[一-龥]")


def count_words(text):
    """与 长日系统.js 的 countWords 完全同口径：汉字数 + 英文单词数（空格分割）。"""
    if not text:
        return 0
    clean = CQ_RE.sub("", text)
    chinese = len(CHINESE_RE.findall(clean))
    english = CHINESE_RE.sub("", clean)
    words = len([w for w in english.split() if w])
    return chinese + words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="重算所有场次（默认只修 stats 为空的）")
    ap.add_argument("--show-id", type=int, default=None, help="只处理指定 show_id")
    ap.add_argument("--dry-run", action="store_true", help="只打印不写库")
    ap.add_argument("--db", default=DB_PATH, help="数据库路径")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"找不到数据库：{args.db}")

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row

    # 旧版库（未经当前 app.py 迁移）可能缺 show_id / is_npc / is_excluded 列，自动降级
    def has_col(table, col):
        return any(r["name"] == col for r in db.execute(f"PRAGMA table_info({table})"))

    has_show_id    = has_col("sessions", "show_id")
    has_is_npc     = has_col("players", "is_npc")
    has_is_excluded = has_col("rp_entries", "is_excluded")
    sid_of = (lambda row: row["show_id"]) if has_show_id else (lambda row: 0)

    where, params = "1=1", []
    if args.show_id is not None and has_show_id:
        where += " AND show_id=?"
        params.append(args.show_id)
    sessions = db.execute(f"SELECT * FROM sessions WHERE {where}", params).fetchall()

    # show_id → NPC 角色名集合
    npc_by_show = {}
    if has_is_npc:
        sid_expr = "show_id" if has_show_id else "0 AS show_id"
        for r in db.execute(f"SELECT {sid_expr}, role_name FROM players WHERE is_npc=1"):
            npc_by_show.setdefault(r["show_id"], set()).add(r["role_name"])

    fixed, touched_shows = 0, set()
    for s in sessions:
        old_stats = {}
        try:
            old_stats = json.loads(s["stats"] or "{}")
        except Exception:
            pass
        if old_stats and not args.all:
            continue  # 覆盖已落地，无需修

        cond, eparams = "session_id=?", [s["id"]]
        if has_show_id:
            cond += " AND show_id=?"
            eparams.append(s["show_id"])
        if has_is_excluded:
            cond += " AND is_excluded=0"
        entries = db.execute(
            f"SELECT role_name, content FROM rp_entries WHERE {cond} ORDER BY seq", eparams
        ).fetchall()
        if not entries:
            continue

        npcs = npc_by_show.get(sid_of(s), set())
        stats = {}
        for e in entries:
            rn = e["role_name"]
            if not rn or rn in npcs:
                continue
            st = stats.setdefault(rn, {"replies": 0, "words": 0})
            st["replies"] += 1
            st["words"]   += count_words(e["content"])

        total_replies = sum(v["replies"] for v in stats.values())
        total_words   = sum(v["words"]   for v in stats.values())
        if (json.dumps(stats, ensure_ascii=False, sort_keys=True)
                == json.dumps(old_stats, ensure_ascii=False, sort_keys=True)
                and total_replies == s["total_replies"] and total_words == s["total_words"]):
            continue  # 已一致

        print(f"[修复] session={s['id']} subtype={s['subtype']} "
              f"段数 {s['total_replies']}→{total_replies}  字数 {s['total_words']}→{total_words}")
        fixed += 1
        touched_shows.add(sid_of(s))
        if not args.dry_run:
            upd = "UPDATE sessions SET stats=?, total_replies=?, total_words=? WHERE id=?"
            uparams = [json.dumps(stats, ensure_ascii=False), total_replies, total_words, s["id"]]
            if has_show_id:
                upd += " AND show_id=?"
                uparams.append(s["show_id"])
            db.execute(upd, uparams)

    # 重算受影响季的 players 累计（与 app.py 的 _compute_player_totals 同逻辑）
    for show_id in touched_shows:
        sess_where  = "show_id=?" if has_show_id else "1=1"
        sess_params = (show_id,) if has_show_id else ()
        all_sessions = db.execute(
            f"SELECT stats, participants FROM sessions WHERE {sess_where}", sess_params
        ).fetchall()
        pl_where = sess_where + (" AND (is_npc IS NULL OR is_npc=0)" if has_is_npc else "")
        players = db.execute(
            f"SELECT qq, role_name FROM players WHERE {pl_where}", sess_params
        ).fetchall()
        for p in players:
            tr = tw = sc = 0
            for ss in all_sessions:
                try:
                    st = json.loads(ss["stats"] or "{}")
                    parts = json.loads(ss["participants"] or "[]")
                except Exception:
                    continue
                if p["role_name"] in st:
                    tr += st[p["role_name"]].get("replies", 0)
                    tw += st[p["role_name"]].get("words", 0)
                if p["role_name"] in parts:
                    sc += 1
            if not args.dry_run:
                upd = ("UPDATE players SET total_replies=?, total_words=?, sessions_count=? "
                       "WHERE qq=?")
                uparams = [tr, tw, sc, p["qq"]]
                if has_show_id:
                    upd += " AND show_id=?"
                    uparams.append(show_id)
                db.execute(upd, uparams)

    if not args.dry_run:
        db.commit()
    print(f"\n完成：修复 {fixed} 个场次，重算 {len(touched_shows)} 个季的玩家累计。"
          + ("（dry-run 未写库）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
