#!/usr/bin/env python3
"""
约会日志接收器 - 在 Sealdice 服务器上运行
接收长日系统插件的 POST 请求，追加写入 appointments.json
GET /download 可直接下载完整日志文件

启动方式：python3 appointment_logger.py
后台运行：nohup python3 appointment_logger.py > logger.log 2>&1 &

在 Mac terminal 下载：
  curl http://服务器IP:5678/download -o appointments.json
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, datetime

PORT = 5678
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appointments.json")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/log":
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            data["received_at"] = datetime.datetime.now().isoformat()
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def do_GET(self):
        if self.path == "/download":
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="appointments.json"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"no log yet")
        elif self.path == "/count":
            count = 0
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    count = sum(1 for line in f if line.strip())
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"{count} records".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 不在终端刷日志


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[约会日志] 监听 0.0.0.0:{PORT}")
    print(f"[约会日志] 日志文件: {LOG_FILE}")
    print(f"[约会日志] 下载命令: curl http://服务器IP:{PORT}/download -o appointments.json")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[约会日志] 已停止")
