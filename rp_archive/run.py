"""贾维斯上的正式启动入口：waitress 代替 Flask 开发服务器，只听本机，外面经 nginx 访问。"""
from waitress import serve
from app import app, init_db

init_db()
# waitress 3 默认会清掉「不可信代理」发来的 X-Forwarded-* 头（clear_untrusted_proxy_headers=True），
# 不声明 nginx 可信的话，程序永远以为是 http、来访 IP 全是 127.0.0.1：/p 的强制 https 会无限 301，
# 按 IP 的限流也变成全站共用一个计数。nginx 就在本机、只有这一层，它的两个头照用。
serve(app, host="127.0.0.1", port=5001, threads=8,
      trusted_proxy="127.0.0.1", trusted_proxy_count=1,
      trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"})
