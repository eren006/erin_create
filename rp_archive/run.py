"""贾维斯上的正式启动入口：waitress 代替 Flask 开发服务器，只听本机，外面经 nginx 访问。"""
from waitress import serve
from app import app, init_db

init_db()
serve(app, host="127.0.0.1", port=5001, threads=8)
