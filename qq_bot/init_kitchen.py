#!/usr/bin/env python3
"""
厨房系统数据库初始化脚本。
在部署后运行此脚本以初始化kitchen表。

用法：python init_kitchen.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from plugins.hp_core import storage as core_storage
from plugins.hp_school import kitchen

def main():
    print("=" * 60)
    print("厨房系统数据库初始化")
    print("=" * 60)

    try:
        # 初始化数据库（创建所有kitchen表）
        print("\n📝 初始化数据库表...")
        core_storage.init_db()
        print("✅ 数据库表初始化完成")

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
