#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import zipfile
import shutil
import re
from pathlib import Path

# ★★★ 在这里修改输出文件夹名称 ★★★
# 如果通过命令行传了自定义名字，就用那个；否则用默认值
import sys
_custom_name_arg = None
for _i, _arg in enumerate(sys.argv):
    if _arg == '--name' and _i + 1 < len(sys.argv):
        _custom_name_arg = sys.argv[_i + 1]
        break
OUTPUT_FOLDER_NAME = _custom_name_arg if _custom_name_arg else '已解压'

def remove_prefix(filename):
    """去掉 QQ-Group 前缀"""
    pattern = r'^QQ-Group\d+_'
    return re.sub(pattern, '', filename)

def clean_log_name(log_name):
    """清理日志名称"""
    log_name = log_name.replace('.zip', '')
    # 去掉末尾的时间戳
    log_name = re.sub(r'\.\d+$', '', log_name)
    # 把下划线还原成空格
    log_name = log_name.replace('_', ' ')
    return log_name.strip()

def extract_day_prefix(log_name):
    """提取日期前缀"""
    match = re.match(r'^(D\d+)', log_name)
    if match:
        return match.group(1)
    return '其他'

def extract_event_type(log_name):
    """提取事件类型"""
    without_day = re.sub(r'^D\d+', '', log_name)
    match = re.match(r'^([^：:]+)', without_day)
    if match:
        event_type = match.group(1)
        if event_type and len(event_type) <= 10:
            return event_type
    return '其他'

def is_timestamp_line(line):
    """检查是否是时间戳行"""
    pattern = r'^.+\(\d+\)\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$'
    return bool(re.match(pattern, line.strip()))

# 恋综插件可能发到备用小群（或在小群内由机器人直接回复）的自动化文案关键词／整行特征
# 来源：开源恋综插件中 seal.replyToSender(vctx)/sendGroupMsg 等到 u.groupId / 备用群 的文案
LIANGA_BACKUP_SKIP_SUBSTRINGS = (
    '【后台催戏】',
    '强结收群，请退出备用',
    '【备用群超时',
    '备用群占用已超过设定时限',
    '请在宽限期内发送【结戏】',
    '请在宽限分钟内发送【结戏】',
    '因超时未结戏，系统已强制释出本备用群占用',
    '小群取消，备用群已解除占用',
    '备用群已解除占用，请尽快退群',
    '退出本群，群名已更改：',  # 有人退群后机器人改群名提示
    '本群时间线已修改。',
    '备用群解除占用成功',
    '备用群解除占用失败',
    '检测到你没有正确配置指令前缀',
    '已结戏：D',  # 结戏后系统发到群/个人群的提示（避免误杀普通「已结戏：」叙述）
    '结戏自动加成：',
    '结戏自动加成计算失败',
    '不在备用群内，请自助或联系管理',
    '复盘已开：下皮请用（）包裹',
    '发送后骰子自动结戏、日志与复盘并释出备用',
    '引用自己的戏@',
    '修改群名：',  # 开私约等提示块首行（与嘉宾戏文区分：整行仅为提示时）
    '二维码图片不显示请发送：',
)


def is_lianga_variety_backup_bot_line(line):
    """恋综插件发往备用群（或群内机器人提示）的常见行"""
    stripped = line.strip()
    if not stripped:
        return False
    if any(s in stripped for s in LIANGA_BACKUP_SKIP_SUBSTRINGS):
        return True
    # 仅一行且为「修改群名：」无后续戏文时去掉
    if stripped == '修改群名：':
        return True
    return False


def is_command_line(line):
    """检查是否是指令行"""
    # 检查以 . 或 。 开头的指令
    pattern1 = r'^[.。]+(开始记录|结束记录|log|Log|LOG)'
    if re.match(pattern1, line.strip()):
        return True

    # ★ 修改：过滤特定的指令行，增加 '备用群超时' ★
    commands = ['绑定', '解绑', '结戏', '取消', '备用', '备用群超时', '催戏', '收群']
    pattern2 = r'^【(.+?)】'
    match = re.match(pattern2, line.strip())
    if match:
        command_name = match.group(1)
        # ★ 前缀匹配：【备用群超时·测试】、【备用群超时·正式】等都会命中 ★
        if any(command_name.startswith(cmd) for cmd in commands):
            return True

    # ★ 新增：过滤【结束】开头的行，如【结束】D1私约：饮月光×琪格格 20:13-20:14 ★
    pattern3 = r'^【结束】'
    if re.match(pattern3, line.strip()):
        return True

    # ★ 新增：过滤 .ext 相关指令行，如 .ext all on 已开启所有未激活的扩展 ★
    pattern4 = r'^[.。]\s*ext\s'
    if re.match(pattern4, line.strip(), re.IGNORECASE):
        return True

    return False

def is_standalone_at_line(line):
    """
    ★ 新增：检查是否是独立的 @ 行 ★
    匹配只包含一个或多个 @昵称 的行，如 "@饮月光" 或 "@张三 @李四"
    """
    stripped = line.strip()
    if not stripped:
        return False
    # 去掉所有 @昵称 后，如果剩余内容为空，说明这行只有 @ 提及
    cleaned = re.sub(r'@\S+', '', stripped).strip()
    return len(cleaned) == 0 and stripped.startswith('@')

def remove_brackets(text):
    """删除括号内的内容"""
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'（[^）]*）', '', text)
    return text

def clean_log_content(content):
    """清理日志内容"""
    lines = content.split('\n')
    result = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. 跳过特定的系统提示语
        if "这是来自后台一键发送的回戏提示" in line:
            i += 1
            continue
        
        # ★ 跳过备用群退群提示 ★
        if "备用群已解除占用，请尽快退群" in line:
            i += 1
            continue

        # ★ 新增：跳过备用群超时相关提示（兜底） ★
        if "备用群超时" in line:
            i += 1
            continue

        # ★ 新增：跳过超时提示变体（兜底） ★
        if "已超过" in line and "分钟数" in line and "宽限" in line:
            i += 1
            continue

        # ★ 新增：跳过"完成结戏"系统通知行 ★
        if re.search(r'\d{2}:\d{2}-\d{2}:\d{2}\s*完成结戏', line):
            i += 1
            continue
            
        # ★ 新增：跳过"已开启所有未激活的扩展"等扩展操作提示 ★
        if "已开启所有未激活的扩展" in line or "已关闭所有扩展" in line:
            i += 1
            continue

        # ★ 新增：跳过"输入有误"等错误提示 ★
        if "输入有误" in line:
            i += 1
            continue

        # 2. 跳过指令行（包含【结戏】、【备用群超时·测试】等）
        if is_command_line(line):
            i += 1
            continue

        # ★ 新增：跳过独立的 @昵称 行 ★
        if is_standalone_at_line(line):
            i += 1
            continue
        
        # 3. 处理时间戳行
        if is_timestamp_line(line):
            # 预读下一行，看是否有有效内容
            has_content = False
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not is_timestamp_line(next_line) and not is_command_line(next_line):
                    # ★ 新增：预读时也排除独立@行和系统提示 ★
                    if is_standalone_at_line(next_line):
                        i += 1
                        continue
                    if "这是来自后台一键发送的回戏提示" in next_line:
                        i += 1
                        continue
                    if "备用群超时" in next_line:
                        i += 1
                        continue
                    
                    next_cleaned = remove_brackets(next_line).strip()
                    next_cleaned = re.sub(r'\[CQ:image,file=[^\]]+\]', '', next_cleaned)
                    next_cleaned = re.sub(r'\[CQ:reply,[^\]]+\]', '', next_cleaned)
                    next_cleaned = re.sub(r'@\S+', '', next_cleaned)  # ★ 新增：预读时也去除@提及 ★
                    
                    if next_cleaned.strip():
                        has_content = True
            
            if has_content:
                result.append("")
        else:
            # 4. 处理普通内容行
            cleaned_line = line
            
            # 删除图片 CQ 码
            cleaned_line = re.sub(r'\[CQ:image,file=[^\]]+\]', '', cleaned_line)
            
            # 删除回复 CQ 码
            cleaned_line = re.sub(r'\[CQ:reply,[^\]]+\]', '', cleaned_line)
            
            # 删除 @ 的 CQ 码
            cleaned_line = re.sub(r'\[CQ:at,qq=\d+\]\s*', '', cleaned_line)
            
            # 删除括号内容
            cleaned_line = remove_brackets(cleaned_line)
            
            if cleaned_line.strip():
                result.append(cleaned_line)
        
        i += 1
    
    return '\n'.join(result)

def safe_filename(name):
    """将文件名中的非法字符替换为安全字符"""
    replacements = {
        ':': '：',
        '/': '／',
        '\\': '＼',
        '*': '＊',
        '?': '？',
        '"': '＂',
        '<': '＜',
        '>': '＞',
        '|': '｜'
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name

def get_unique_filepath(directory, filename):
    """获取唯一的文件路径，避免覆盖"""
    base_name = filename.rsplit('.', 1)[0]
    ext = '.txt'
    
    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath):
        return filepath
    
    counter = 2
    while True:
        new_filename = f"{base_name} ({counter}){ext}"
        filepath = os.path.join(directory, new_filename)
        if not os.path.exists(filepath):
            return filepath
        counter += 1

def process_logs():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(script_dir, 'data', 'default', 'log-exports')
    output_dir = os.path.join(log_dir, OUTPUT_FOLDER_NAME)

    if not os.path.exists(log_dir):
        print(f"❌ 错误：找不到日志目录")
        print(f"期望位置：{log_dir}")
        print()
        input("按任意键退出...")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    
    print()
    print("=" * 70)
    print("  海豹日志批量解压工具 (最终优化版)")
    print("=" * 70)
    print()
    print(f"日志目录：{log_dir}")
    print(f"输出目录：{output_dir}")
    print()
    
    zip_files = list(Path(log_dir).glob('*.zip'))
    
    if not zip_files:
        print("❌ 未找到任何zip文件")
        print()
        input("按任意键退出...")
        return
    
    zip_count = len(zip_files)
    success_count = 0
    fail_count = 0
    category_count = {}
    
    for idx, zip_file in enumerate(zip_files, 1):
        zip_name = zip_file.stem
        
        print(f"[{idx}/{zip_count}] 正在处理")
        print(f"    文件：{zip_file.name}")
        
        log_name_raw = remove_prefix(zip_name)
        log_name = clean_log_name(log_name_raw)
        print(f"    名称：{log_name}")
        
        day_prefix = extract_day_prefix(log_name)
        event_type = extract_event_type(log_name)
        
        print(f"    分类：{day_prefix} → {event_type}")
        
        category_dir = os.path.join(output_dir, day_prefix, event_type)
        os.makedirs(category_dir, exist_ok=True)
        
        try:
            temp_extract_dir = os.path.join(category_dir, f"_temp_{idx}")
            os.makedirs(temp_extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            
            raw_log_path = os.path.join(temp_extract_dir, 'raw-log.txt')
            if os.path.exists(raw_log_path):
                with open(raw_log_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                cleaned_content = clean_log_content(original_content)
                
                safe_log_name = safe_filename(log_name)
                new_name = f"{safe_log_name}.txt"
                new_path = get_unique_filepath(category_dir, new_name)
                
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                
                final_name = os.path.basename(new_path)
                print(f"    ✓ 保存为：{final_name}")
            
            shutil.rmtree(temp_extract_dir)
            success_count += 1
            
            category_key = f"{day_prefix}/{event_type}"
            if category_key not in category_count:
                category_count[category_key] = 0
            category_count[category_key] += 1
            
        except Exception as e:
            print(f"    ✗ 失败：{e}")
            fail_count += 1
        
        print()
    
    print("=" * 70)
    print("  处理完成！")
    print("=" * 70)
    print()
    print(f"总计：{zip_count} 个 | 成功：{success_count} 个 | 失败：{fail_count} 个")
    print()
    print("分类统计：")
    for category in sorted(category_count.keys()):
        print(f"  {category}：{category_count[category]} 个")
    print()
    
    import sys
    if '--auto' in sys.argv:
        print(f"输出目录：{output_dir}")
    else:
        # 手动双击运行时，还是正常打开文件夹
        try:
            os.startfile(output_dir)
        except Exception:
            pass
        input("按任意键退出...")

if __name__ == '__main__':
    process_logs()
