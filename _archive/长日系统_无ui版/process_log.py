#!/usr/bin/env python3
"""
长日系统约会日志处理脚本

使用方式：
  1. 把服务器上的 ZIP 日志下载到本地某个文件夹
  2. 把本脚本也放进那个文件夹（或用 --dir 指定路径）
  3. python3 process_log.py

下载命令（Mac Terminal）：
  mkdir -p ~/Desktop/logs
  scp "Administrator@20.26.120.128:/C/Users/Administrator/Downloads/sealdice-core_1.5.1_windows_amd64/data/default/log-exports/*.zip" ~/Desktop/logs/
  cp process_log.py ~/Desktop/logs/
  cd ~/Desktop/logs && python3 process_log.py
"""

import zipfile, re, os, sys
from pathlib import Path

# ★★★ 在这里修改输出文件夹名称 ★★★
OUTPUT_FOLDER_NAME = '已解压'

# 第一行=角色名，剩余=正文（私约/心愿/官约）
FIRST_LINE_TYPES = {'私约', '心愿', '官约'}
# 角色名：正文（电话/微信）
COLON_TYPES = {'电话', '微信'}


def parse_log_filename(stem):
    """
    从文件名拆出 subtype、角色名列表、地点、日期、时间。
    格式：私约_角色A_角色B_地点_D3_1400-1800
    """
    parts = stem.split('_')
    if not parts:
        return None, set(), '', '', ''
    subtype = parts[0]

    day_idx  = next((i for i, p in enumerate(parts) if re.match(r'^[Dd]\d+$', p)), -1)
    time_idx = next((i for i, p in enumerate(parts) if re.match(r'^\d{3,4}-\d{3,4}$', p)), -1)

    # 有 day：角色名在 [1 : day_idx-1]，place 在 day_idx-1
    if day_idx > 1:
        role_names = set(parts[1:day_idx - 1])
        place = parts[day_idx - 1]
    elif day_idx == 1:
        role_names = set()
        place = ''
    else:
        role_names = set(parts[1:])
        place = ''

    day  = parts[day_idx]  if day_idx  >= 0 else ''
    time = parts[time_idx] if time_idx >= 0 else ''
    return subtype, role_names, place, day, time


def split_messages(text):
    """
    把原始日志文本切成消息列表，每项是消息的完整正文（不含时间戳行头）。

    海豹跑团日志常见格式（如果你的格式不同，只需改这里的正则）：
      [2026-05-14 14:00:00] 昵称(123456): 消息内容
    """
    # 用时间戳行作为分隔符切分
    blocks = re.split(r'\n(?=\[\d{4}-\d{2}-\d{2})', text)
    messages = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 去掉时间戳前缀 [xxxx-xx-xx xx:xx:xx]
        body = re.sub(r'^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*', '', block)
        # 去掉发送者前缀 "昵称(uid): " 或 "昵称: "
        body = re.sub(r'^.*?[（(][^)）]*[)）]\s*[:：]\s*', '', body, count=1)
        body = re.sub(r'^[^:：\n]+[:：]\s*', '', body, count=1)
        body = body.strip()
        if body:
            messages.append(body)
    return messages


def filter_first_line(messages, role_names):
    """
    私约/心愿/官约：第一行必须是角色名，剩余行为正文。
    字数不限。返回格式化后的字符串列表。
    """
    results = []
    for msg in messages:
        lines = msg.split('\n')
        first = lines[0].strip()
        if first in role_names:
            rest = '\n'.join(lines[1:]).strip()
            results.append(f"{first}\n{rest}" if rest else first)
    return results


def filter_colon(messages, role_names):
    """
    电话/微信：格式必须是 角色名：正文 或 角色名:正文（中英文冒号均接受）。
    """
    pattern = re.compile(r'^(.+?)\s*[：:]\s*(.+)', re.DOTALL)
    results = []
    for msg in messages:
        m = pattern.match(msg)
        if m and m.group(1).strip() in role_names:
            results.append(f"{m.group(1).strip()}：{m.group(2).strip()}")
    return results


def process_zip(zip_path, output_dir):
    stem = Path(zip_path).stem
    subtype, role_names, place, day, time_str = parse_log_filename(stem)

    if subtype not in FIRST_LINE_TYPES and subtype not in COLON_TYPES:
        print(f"  跳过（类型不在处理范围）: {stem}")
        return

    if not role_names:
        print(f"  跳过（无法从文件名提取角色名）: {stem}")
        return

    with zipfile.ZipFile(zip_path, 'r') as zf:
        inner = [n for n in zf.namelist() if not n.endswith('/')]
        if not inner:
            print(f"  ZIP 内无文件: {stem}")
            return
        raw = zf.read(inner[0]).decode('utf-8', errors='replace')

    messages = split_messages(raw)
    if not messages:
        # 如果解析结果为空，打印前几行供调试
        print(f"  ⚠️  {stem}：消息解析结果为空，以下是原始前3行，请告知以便调整格式：")
        for line in raw.splitlines()[:3]:
            print(f"    {repr(line)}")
        return

    if subtype in FIRST_LINE_TYPES:
        filtered = filter_first_line(messages, role_names)
    else:
        filtered = filter_colon(messages, role_names)

    if not filtered:
        print(f"  ⚠️  {stem}：共 {len(messages)} 条消息，0 条符合格式（角色名：{role_names}）")
        return

    out_path = Path(output_dir) / f"{stem}.txt"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n\n---\n\n'.join(filtered))
    print(f"  ✅ {stem} → {len(filtered)} 条")


def main():
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    output_dir = target_dir / OUTPUT_FOLDER_NAME
    output_dir.mkdir(exist_ok=True)

    zips = sorted(target_dir.glob('*.zip'))
    if not zips:
        print(f"在 {target_dir} 没有找到 .zip 文件")
        return

    print(f"找到 {len(zips)} 个日志文件，开始处理...\n")
    for z in zips:
        print(f"处理: {z.name}")
        process_zip(z, output_dir)

    print(f"\n完成！输出在：{output_dir}")


if __name__ == '__main__':
    main()
