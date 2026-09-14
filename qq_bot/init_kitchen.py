#!/usr/bin/env python3
"""
厨房系统数据库初始化脚本。
在部署后运行此脚本以初始化kitchen表。

用法：python init_kitchen.py
"""

import sys
import types
import importlib.util
from pathlib import Path

# Windows 控制台默认 GBK 编码，打印 emoji/中文会报错，强制切到 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from plugins.hp_core import storage as core_storage

def _load_kitchen_module():
    """直接从文件加载 kitchen.py，绕开 hp_school/__init__.py
    （后者会 require() nonebot 插件，脱离机器人进程运行会报错）。
    """
    hp_school_dir = project_root / "plugins" / "hp_school"

    # 注册一个不执行 __init__.py 的伪 hp_school 包，
    # 这样 kitchen.py 里的 `from . import storage` 能正常解析。
    fake_pkg = types.ModuleType("plugins.hp_school")
    fake_pkg.__path__ = [str(hp_school_dir)]
    sys.modules.setdefault("plugins.hp_school", fake_pkg)

    spec = importlib.util.spec_from_file_location(
        "plugins.hp_school.kitchen", hp_school_dir / "kitchen.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugins.hp_school.kitchen"] = module
    spec.loader.exec_module(module)
    return module


def main():
    print("=" * 60)
    print("厨房系统数据库初始化")
    print("=" * 60)

    try:
        # 初始化数据库（创建所有kitchen表）
        print("\n📝 初始化数据库表...")
        core_storage.init_db()
        print("✅ 数据库表初始化完成")

        kitchen = _load_kitchen_module()

        print("\n📊 厨房系统信息：")
        print(f"  • 配方总数：{len(kitchen.RECIPES)}")
        print(f"  • 节日配方：{len(kitchen.FESTIVAL_RECIPES)}")
        print(f"  • 材料种类：{len(kitchen.KITCHEN_MATERIALS)}")
        print(f"  • 成就数量：{len(kitchen.TITLE_NAMES)}")

        print("\n✨ 初始化成功！")
        print("\n接下来的步骤：")
        print("  1. 重启QQ机器人服务")
        print("  2. 测试 /烹饪配方 命令")
        print("  3. 新玩家入学时会自动获得初始材料包")

        return 0

    except Exception as e:
        print(f"\n❌ 初始化失败：{e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
