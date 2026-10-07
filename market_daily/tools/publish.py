#!/usr/bin/env python3
"""校验所有期刊 JSON → 重建 issues/index.json → rsync 到贾维斯 → git 提交期刊。

用法：
  python3 tools/publish.py            # 校验 + 重建目录 + 部署 + 提交
  python3 tools/publish.py --check    # 只校验、重建目录，不部署
校验不过就非零退出，不会部署半成品。
部署成功后只提交 site/issues/ 下的改动，不碰仓库里其他项目的暂存或未提交内容；
提交失败只打印警告，不影响已上线的结果。
"""
import json
import re
from datetime import datetime
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ISSUES = SITE / "issues"
REMOTE = "jarvis:/var/www/market_daily/"
PUBLIC_URL = "https://news.changri.work/"

MAG7 = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"}
# 写稿时最常见的套话，出现就打回重写
BANNED = ["值得注意的是", "值得一提的是", "总的来说", "综上所述", "不难发现", "与此同时，", "在这一背景下", "赋能", "首先，", "其次，", "最后，"]
ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(am|pm)$")


def walk_text(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k != "sources":
                yield from walk_text(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_text(v)


def validate(path: Path, d: dict) -> list:
    errs = []
    m = ID_RE.match(path.stem)
    if not m:
        return [f"文件名必须是 YYYY-MM-DD-am|pm.json"]
    date, ed = m.groups()
    if d.get("id") != path.stem:
        errs.append(f"id 应为 {path.stem}")
    if d.get("date") != date or d.get("edition") != ed:
        errs.append("date/edition 与文件名不一致")
    if not d.get("headline"):
        errs.append("缺 headline")
    if not d.get("published_at"):
        errs.append("缺 published_at")
    if len(d.get("tape") or []) < 6:
        errs.append("tape 至少 6 项（三大指数、VIX、10年期美债、美元、原油、黄金等）")
    if len(d.get("brief") or []) < 3:
        errs.append("brief 至少 3 条")
    for key in ("markets", "ai", "china", "policy"):
        sec = d.get(key)
        if not isinstance(sec, dict):
            errs.append(f"缺版面 {key}")
            continue
        if sum(len(p) for p in sec.get("body") or []) < 500:
            errs.append(f"{key}.body 太短（正文至少 500 字）")
    if date >= "2026-10-06":
        an = d.get("ainews")
        if not isinstance(an, dict):
            errs.append("缺版面 ainews（AI动态）")
        else:
            regs = {r.get("name"): r for r in an.get("regions") or []}
            for nm in ("美国", "中国", "全球其他地区"):
                if len((regs.get(nm) or {}).get("items") or []) < 2:
                    errs.append(f"ainews.{nm} 至少 2 条")
            for r in regs.values():
                for it in r.get("items") or []:
                    if len(it.get("take") or "") < 40:
                        errs.append(f"ainews 条目缺 take（我的看法，至少 40 字）：{it.get('title')}")
                    if not str(it.get("src", "")).startswith("http"):
                        errs.append(f"ainews 条目缺 src：{it.get('title')}")
    ai = d.get("ai") or {}
    syms = {s.get("symbol", "").upper() for s in ai.get("stocks") or []}
    if not MAG7 <= syms:
        errs.append(f"ai.stocks 必须覆盖七姐妹，缺 {sorted(MAG7 - syms)}")
    if len((d.get("markets") or {}).get("catalysts") or []) < 3:
        errs.append("markets.catalysts 至少 3 条")
    if len((d.get("markets") or {}).get("sectors") or []) < 3:
        errs.append("markets.sectors 至少 3 个板块")
    if len((d.get("china") or {}).get("mapping") or []) < 3:
        errs.append("china.mapping 至少 3 条")
    if len((d.get("policy") or {}).get("outlook") or []) < 3:
        errs.append("policy.outlook 至少 3 条")
    if len(d.get("sources") or []) < 5:
        errs.append("sources 至少 5 条真实来源")
    for s in d.get("sources") or []:
        if not str(s.get("url", "")).startswith("http"):
            errs.append(f"来源缺 url：{s.get('title')}")

    ups = d.get("upcoming") or []
    if len(ups) < 3:
        errs.append("upcoming（大事预告）至少 3 条，覆盖未来重要财报/数据/政策日")
    pub = None
    try:
        pub = datetime.fromisoformat(d.get("published_at", ""))
    except Exception:
        errs.append("published_at 不是合法的带时区 ISO 时间")
    last_at = None
    for u in ups:
        name = u.get("title", "?")
        try:
            at = datetime.fromisoformat(u.get("at", ""))
            if at.tzinfo is None:
                raise ValueError
        except Exception:
            errs.append(f"upcoming「{name}」的 at 必须是带时区偏移的 ISO 时间")
            continue
        if pub and at <= pub:
            errs.append(f"upcoming「{name}」的时间早于发布时间，已经不是「即将」了")
        if last_at and at < last_at:
            errs.append("upcoming 必须按时间从近到远排序")
        last_at = at
        if u.get("kind") not in ("财报", "数据", "政策", "美联储", "其他"):
            errs.append(f"upcoming「{name}」的 kind 只能是 财报/数据/政策/美联储/其他")
        if u.get("importance") not in ("high", "normal"):
            errs.append(f"upcoming「{name}」的 importance 只能是 high/normal")
        if not str(u.get("src", "")).startswith("http"):
            errs.append(f"upcoming「{name}」缺 src（日期时间的依据链接）")
    blob = "\n".join(walk_text(d))
    for w in BANNED:
        if w in blob:
            errs.append(f"出现套话「{w}」，请改写")
    if re.search(r"(TODO|待补|XX|占位|示例)", blob):
        errs.append("含占位文字")
    return errs


def main():
    check_only = "--check" in sys.argv
    files = sorted(p for p in ISSUES.glob("*.json") if p.name != "index.json")
    entries, bad = [], False
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"✗ {p.name}: JSON 解析失败 {e}")
            bad = True
            continue
        errs = validate(p, d)
        if errs:
            bad = True
            print(f"✗ {p.name}")
            for e in errs:
                print("   -", e)
        else:
            entries.append({
                "id": d["id"], "date": d["date"], "edition": d["edition"],
                "headline": d["headline"], "published_at": d["published_at"],
            })
    if bad:
        print("校验未通过，未部署。")
        sys.exit(1)

    # 同一天晚报在早报之后；整体新到旧
    entries.sort(key=lambda e: (e["date"], 1 if e["edition"] == "pm" else 0), reverse=True)
    (ISSUES / "index.json").write_text(
        json.dumps({"issues": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ {len(entries)} 期校验通过，目录已重建")

    if check_only:
        return
    r = subprocess.run(
        ["rsync", "-az", "--timeout=120", f"{SITE}/", REMOTE], capture_output=True, text=True)
    if r.returncode != 0:
        print("✗ rsync 失败：", r.stderr.strip())
        sys.exit(2)
    print(f"✓ 已部署 {PUBLIC_URL}")
    git_commit_issues()


def git_commit_issues():
    """把 site/issues/ 的新增和改动提交进 git；commit 带 pathspec，别的已暂存文件不会被带进来。"""
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    git("add", "--", str(ISSUES))
    changed = git("diff", "--cached", "--name-only", "--", str(ISSUES)).stdout.split()
    if not changed:
        print("✓ 期刊没有新改动，无需提交")
        return
    ids = sorted(Path(p).stem for p in changed if ID_RE.match(Path(p).stem))
    msg = f"纽约晨昏：发布 {'、'.join(ids)}" if ids else "纽约晨昏：更新期刊目录"
    msg += "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    r = git("commit", "-q", "-m", msg, "--", str(ISSUES))
    if r.returncode != 0:
        print("⚠ git 提交失败（已上线不受影响）：", (r.stderr or r.stdout).strip())
        return
    print("✓ 已提交 git：", git("log", "-1", "--format=%h %s").stdout.strip())


if __name__ == "__main__":
    main()
