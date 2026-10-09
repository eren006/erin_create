#!/usr/bin/env python3
"""一次改完版本号 + 更新日志 + dist 同步，免得漏改某个页面。

用法：
  python3 bump_version.py 1.11.2 --feat "新增xxx" --fix "修复yyy" --improve "优化zzz"
  python3 bump_version.py 1.11.1 --fix "又一条"      # 版本号已是 1.11.1：只往当前版本的日志里追加条目（并入未上传版本）
  python3 bump_version.py --sync-only                  # 只同步 dist

会改：长日系统.js（@version 与 ext.new）、dist/info.toml、changri_hub.html（顶栏/首屏版本 + CHANGELOG）、
changri_wishes.html（顶栏版本），最后跑 sync_dist.py。--feat/--fix/--improve 可重复多次。
"""
import argparse, json, re, subprocess, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN = HERE / "长日系统.js"
HUB = HERE / "changri_hub.html"
WISHES = HERE / "changri_wishes.html"
INFO = HERE / "dist" / "changri_sealpack_src" / "info.toml"
GROUPS = [("feat", "新功能"), ("fix", "修复"), ("improve", "调整与优化")]


def sub1(text, pattern, repl, what):
    new, n = re.subn(pattern, repl, text, count=1)
    if n != 1:
        sys.exit(f"❌ 没找到要改的位置：{what}")
    return new


def current_version():
    m = re.search(r"// @version\s+(\S+)", MAIN.read_text(encoding="utf-8"))
    return m.group(1)


def js_str(x):
    return json.dumps(x, ensure_ascii=False)


def add_changelog(hub, ver, items, day):
    entry_at = hub.find(f'    version: "{ver}",')
    if entry_at < 0:  # 新版本：插到最前面，旧的 latest 改 false
        hub = hub.replace("    latest: true,", "    latest: false,")
        groups = "".join(
            f'      {{ type: "{t}", title: "{title}", items: [\n'
            + ",\n".join(f"        {js_str(x)}" for x in items[t]) + "\n      ]},\n"
            for t, title in GROUPS if items[t])
        groups = groups.rstrip(",\n") + "\n" if groups else ""
        groups = re.sub(r"\]\},\n(?=      \{ type)", "]},\n", groups)
        block = (f'  {{\n    version: "{ver}",\n    date: "{day}",\n    latest: true,\n    groups: [\n{groups}    ]\n  }},\n')
        return sub1(hub, r"const CHANGELOG = \[\n", lambda m: m.group(0) + block, "CHANGELOG 开头")
    # 已有该版本：往对应分组追加；没有该分组就新建
    end = hub.index("\n  },", entry_at)
    for t, title in GROUPS:
        if not items[t]:
            continue
        seg = hub[entry_at:end]
        added = ",\n".join(f"        {js_str(x)}" for x in items[t])
        m = re.search(rf'type: "{t}", title: "[^"]*", items: \[\n(.*?)\n      \]\}}', seg, re.S)
        if m:
            at = entry_at + m.end(1)
            hub = hub[:at] + ",\n" + added + hub[at:]
        else:
            at = entry_at + seg.rindex("    ]")
            hub = hub[:at] + f'      {{ type: "{t}", title: "{title}", items: [\n{added}\n      ]}}\n' + hub[at:]
            hub = hub.replace("      ]}\n      { type", "      ]},\n      { type")
        end = hub.index("\n  },", entry_at)
    return hub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", nargs="?")
    ap.add_argument("--date", default=str(date.today()))
    for t, _ in GROUPS:
        ap.add_argument(f"--{t}", action="append", default=[])
    ap.add_argument("--sync-only", action="store_true")
    a = ap.parse_args()
    if a.sync_only:
        return subprocess.call([sys.executable, str(HERE / "sync_dist.py")])
    if not a.version:
        ap.error("需要版本号，如 1.11.2")
    ver, old = a.version, current_version()
    items = {t: getattr(a, t) for t, _ in GROUPS}

    if ver != old:
        s = MAIN.read_text(encoding="utf-8")
        s = sub1(s, r"(// @version\s+)\S+", rf"\g<1>{ver}", "@version")
        s = sub1(s, r'(ext = seal\.ext\.new\("changri", "长日将尽", ")[^"]+(")', rf"\g<1>{ver}\g<2>", "ext.new 版本")
        MAIN.write_text(s, encoding="utf-8")
        t = INFO.read_text(encoding="utf-8")
        INFO.write_text(sub1(t, r'(?m)^version = "[^"]+"', f'version = "{ver}"', "info.toml"), encoding="utf-8")
        h = HUB.read_text(encoding="utf-8")
        h = sub1(h, r"SYSTEM · v[\d.]+", f"SYSTEM · v{ver}", "hub 顶栏版本")
        h = sub1(h, r"<b>v[\d.]+</b><span>当前版本", f"<b>v{ver}</b><span>当前版本", "hub 首屏版本")
        HUB.write_text(h, encoding="utf-8")
        w = WISHES.read_text(encoding="utf-8")
        WISHES.write_text(sub1(w, r"SYSTEM · v[\d.]+", f"SYSTEM · v{ver}", "wishes 顶栏版本"), encoding="utf-8")
        print(f"版本号 {old} -> {ver}")
    else:
        print(f"版本号已是 {ver}，只追加日志条目")

    if any(items.values()):
        h = HUB.read_text(encoding="utf-8")
        HUB.write_text(add_changelog(h, ver, items, a.date), encoding="utf-8")
        print("已写入 hub 更新日志")
    elif ver != old:
        print("⚠️ 没有给任何 --feat/--fix/--improve，hub 更新日志没有新条目")
    rc = subprocess.call([sys.executable, str(HERE / "sync_dist.py")])
    print("\n还需要：python3 check_clear_keys_coverage.py；改了页面后跑 ./deploy_hub_pages.sh；插件手动上传。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
