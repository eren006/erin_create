#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复盘打包触发服务（长日系统无ui版）
POST /pack  - 解压 → 打包 → 上传群文件
POST /clean - 清理原始zip，只保留已解压txt
GET  /ping  - 健康检查
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, sys, zipfile, shutil, subprocess
from datetime import datetime

# ====== ⚙️ 配置区域（启动前必填）======

# LLOneBot / NapCat / Lagrange 的 HTTP API 端口
LLONEBOT_PORT = 3000

# HTTP Token（无则留空）
LLONEBOT_TOKEN = ""

# 海豹所在文件夹的完整路径
# Windows 示例：r"C:\sealdice"  或  "C:/sealdice"
# macOS/Linux 示例："/home/user/sealdice"
SEAL_DIR = "/path/to/sealdice"

# 本服务监听端口（与 长日系统.js 中「复盘打包服务地址」端口保持一致）
TRIGGER_PORT = 9999

# ======================================

SCRIPT_PATH       = os.path.join(SEAL_DIR, "解压日志.py")
LOG_EXPORTS_DIR   = os.path.join(SEAL_DIR, "data", "default", "log-exports")
OUTPUT_FOLDER_NAME = "已解压"
OUTPUT_FOLDER     = os.path.join(LOG_EXPORTS_DIR, OUTPUT_FOLDER_NAME)

# 临时 zip 存放位置：macOS/Linux 用 /tmp，Windows 用 %TEMP%
ZIP_OUTPUT_DIR = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"

try:
    import requests
except ImportError:
    print("需要安装 requests：pip install requests")
    sys.exit(1)


def safe_filename(name):
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(ch, '_')
    return name.strip()


def run_pack_and_upload(group_id, custom_name=""):
    clean_name = safe_filename(custom_name) if custom_name else OUTPUT_FOLDER_NAME
    output_folder = os.path.join(LOG_EXPORTS_DIR, clean_name)

    # 1. 清理上次的输出文件夹
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    # 2. 执行解压脚本
    my_env = os.environ.copy()
    my_env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, SCRIPT_PATH, '--auto']
    if custom_name:
        cmd += ['--name', clean_name]

    result = subprocess.run(
        cmd, capture_output=True, encoding='utf-8', errors='replace',
        timeout=180, cwd=SEAL_DIR, env=my_env
    )
    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "未知错误"
        return False, "脚本执行出错: " + err[:200]

    # 3. 检查输出
    if not os.path.exists(output_folder):
        return False, "解压完成但未找到输出目录"

    # 4. 生成 zip 文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"{clean_name}.zip" if custom_name else f"复盘结果_{timestamp}.zip"
    zip_path = os.path.join(ZIP_OUTPUT_DIR, zip_filename)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    # 5. 打包
    file_count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_folder):
            for file in files:
                fp = os.path.join(root, file)
                zf.write(fp, os.path.relpath(fp, output_folder))
                file_count += 1

    if file_count == 0:
        return False, "没有找到任何文件可以打包"

    # 6. 上传到群文件
    url = f"http://127.0.0.1:{LLONEBOT_PORT}/upload_group_file"
    payload = {
        "group_id": int(group_id),
        "file": os.path.abspath(zip_path).replace("\\", "/"),
        "name": zip_filename
    }
    headers = {"Content-Type": "application/json"}
    if LLONEBOT_TOKEN:
        headers["Authorization"] = f"Bearer {LLONEBOT_TOKEN}"

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except Exception as e:
        return False, f"连接LLOneBot失败: {e}"

    if resp.status_code == 200:
        try:
            rd = resp.json()
        except:
            return False, f"LLOneBot返回非JSON: {resp.text[:200]}"
        if rd.get("retcode") == 0:
            size_mb = os.path.getsize(zip_path) / (1024 * 1024)
            return True, f"上传成功！文件名：{zip_filename}，共{file_count}个文件，{size_mb:.1f}MB"
        else:
            return False, f"上传失败: {rd.get('msg', rd.get('wording', '未知错误'))}"
    else:
        return False, f"LLOneBot请求失败，状态码: {resp.status_code}"


def run_clean():
    if not os.path.exists(LOG_EXPORTS_DIR):
        return False, "日志目录不存在：" + LOG_EXPORTS_DIR

    deleted = 0
    errors = []
    for item in os.listdir(LOG_EXPORTS_DIR):
        path = os.path.join(LOG_EXPORTS_DIR, item)
        if os.path.isfile(path) and item.lower().endswith('.zip'):
            try:
                os.remove(path)
                deleted += 1
            except Exception as e:
                errors.append(f"{item}: {e}")

    kept = [i for i in os.listdir(LOG_EXPORTS_DIR)
            if os.path.isdir(os.path.join(LOG_EXPORTS_DIR, i))]

    parts = [f"已删除 {deleted} 个原始zip日志" if deleted else "没有需要清理的zip文件"]
    if kept:
        parts.append(f"保留 {len(kept)} 个文件夹：{', '.join(kept)}")
    if errors:
        parts.append(f"清理时出错 {len(errors)} 项：" + "; ".join(errors[:5]))
        return False, "\n".join(parts)
    return True, "\n".join(parts)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length) if length > 0 else b'{}'
            try:
                body = json.loads(raw)
            except:
                body = {}

            if self.path == '/pack':
                gid = body.get('group_id', '')
                if not gid:
                    self._respond(400, {'status': 'error', 'message': '缺少 group_id'})
                    return
                ok, msg = run_pack_and_upload(gid, body.get('custom_name', '').strip())
                self._respond(200, {'status': 'ok' if ok else 'error', 'message': msg})

            elif self.path == '/clean':
                ok, msg = run_clean()
                self._respond(200, {'status': 'ok' if ok else 'error', 'message': msg})

            else:
                self._respond(200, {'status': 'error', 'message': '未知路径'})

        except subprocess.TimeoutExpired:
            self._respond(200, {'status': 'error', 'message': '脚本执行超时（超过3分钟）'})
        except Exception as e:
            self._respond(200, {'status': 'error', 'message': '内部错误: ' + str(e)})

    def do_GET(self):
        if self.path == '/ping':
            self._respond(200, {'status': 'ok', 'message': '服务正在运行'})
        else:
            self._respond(200, {'status': 'ok', 'message': '请使用POST访问 /pack 或 /clean'})

    def _respond(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        try:
            print(f"[触发器] {args[0]}")
        except:
            pass


if __name__ == '__main__':
    print("=" * 55)
    print("  复盘打包触发服务（长日系统无ui版）")
    print("=" * 55)
    print(f"  监听地址: http://127.0.0.1:{TRIGGER_PORT}")
    print(f"  解压脚本: {SCRIPT_PATH}")
    print(f"  日志目录: {LOG_EXPORTS_DIR}")
    print(f"  LLOneBot: http://127.0.0.1:{LLONEBOT_PORT}")
    print()
    print("  POST /pack  - 打包并上传群文件")
    print("  POST /clean - 清理原始日志zip")
    print("  GET  /ping  - 健康检查")
    print("=" * 55)

    if SEAL_DIR == "/path/to/sealdice":
        print("\n⚠️  警告：SEAL_DIR 尚未配置，请编辑本文件后再启动！\n")

    server = HTTPServer(('127.0.0.1', TRIGGER_PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
