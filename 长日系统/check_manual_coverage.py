#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验长日系统各 JS 插件里注册的 ext.cmdMap[...] 指令，是否都在
生成指令手册.py 的 SECTIONS 里有对应文档条目。

用法：python3 check_manual_coverage.py
退出码：发现未文档化指令时返回 1，否则返回 0（方便接入 pre-commit）。
"""
import glob
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 忽略：一次性脚本目录、已归档目录（见项目记忆：长日extra/、_archive/ 不参与主系统维护）
IGNORE_DIR_PARTS = ("长日extra", "_archive")


def find_cmd_names():
    names = {}  # name -> [file, ...]
    pattern = re.compile(r'ext\.cmdMap\[\s*["\'](.+?)["\']\s*\]\s*=')
    for path in glob.glob(os.path.join(HERE, "*.js")):
        if any(part in path for part in IGNORE_DIR_PARTS):
            continue
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            # 跳过整行注释（// 开头，允许前导空白）；不处理块注释/行内注释等更复杂情况，
            # 这里只需要过滤已知的「合入子命令」注释掉的旧注册行
            if line.strip().startswith("//"):
                continue
            for m in pattern.finditer(line):
                names.setdefault(m.group(1), []).append(os.path.basename(path))
    return names


def load_sections():
    spec = importlib.util.spec_from_file_location(
        "manual_src", os.path.join(HERE, "生成指令手册.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SECTIONS


def documented_names(sections):
    """从每条手册目录项里提取命令名前缀（去掉 [参数] 部分和空格）。
    个别条目用 "A / B" 形式在一条里写了两个别名指令，也一并拆出来。"""
    names = set()
    for _title, entries in sections:
        for entry in entries:
            cmd = entry[0]
            for alias in cmd.split(" / "):
                m = re.match(r'^([^\s\[\(]+)', alias.strip())
                if m:
                    names.add(m.group(1))
    return names


def main():
    cmd_names = find_cmd_names()
    sections = load_sections()
    doc_names = documented_names(sections)

    missing = sorted(n for n in cmd_names if n not in doc_names)

    if not missing:
        print(f"✅ 全部 {len(cmd_names)} 个指令均已在手册中找到对应条目。")
        return 0

    print(f"⚠️ 共 {len(cmd_names)} 个指令，{len(missing)} 个未在手册 SECTIONS 中找到：\n")
    for n in missing:
        files = "、".join(cmd_names[n])
        print(f"  - {n}  (定义于 {files})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
