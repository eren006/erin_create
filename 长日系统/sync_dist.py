#!/usr/bin/env python3
"""把源文件同步到 dist/changri_sealpack_src/scripts/（这些是源文件的完整副本，不入库，用到时现生成）。

用法：python3 sync_dist.py          # 同步
      python3 sync_dist.py --check  # 只检查是否一致（不一致返回 1）
bump_version.py 和 deploy_hub_pages.sh 都会先调用它，所以平时不用手动 cp。
"""
import shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE / "dist" / "changri_sealpack_src" / "scripts"
# dist 里的文件名 -> 源文件
MAPPING = {
    "core.js": "长日系统.js", "season.js": "长日季度.js", "social.js": "长日社交.js",
    "settings.js": "长日设置.js", "rpg.js": "长日RPG.js", "letters.js": "长日写信综.js",
    "dinner.js": "长日晚餐.js", "alarm.js": "长日闹钟.js", "auction.js": "长日拍卖.js",
    "entrance.js": "长日出场.js",
}


def main():
    check = "--check" in sys.argv
    DEST.mkdir(parents=True, exist_ok=True)
    stale = []
    for dst_name, src_name in MAPPING.items():
        src, dst = HERE / src_name, DEST / dst_name
        if not src.exists():
            print(f"❌ 源文件不存在：{src_name}"); return 1
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            stale.append(dst_name)
            if not check:
                shutil.copyfile(src, dst)
    if check:
        print("✅ dist 与源文件一致" if not stale else f"⚠️ dist 不同步：{', '.join(stale)}")
        return 1 if stale else 0
    print(f"✅ dist 已同步（更新 {len(stale)} 个：{', '.join(stale) or '无'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
