#!/bin/bash
# 排单宝 — 部署脚本（贾维斯：腾讯云 Ubuntu 124.221.189.86，https://order.changri.work，systemd）
# 用法：bash deploy.sh
#
# 只同步代码：app.py / requirements.txt / templates/ / static/，
# 绝不碰服务器上的 order_data.db、uploads/、logs/、venv/。
# 用 rsync 增量传输——本地到腾讯云的上行只有几 KB/s，整包重传会很慢。
# 服务器上的环境变量（PORT / FLASK_SECRET / SUPERADMIN_PASS）在 /etc/yuca_order.env，不在本仓库。
# 服务配置：/etc/systemd/system/yuca_order.service（waitress :5023），
#           waitress 监听 5023，对外由 nginx 按子域名反代并提供 HTTPS（/etc/nginx/sites-available/changri，
#           本地副本 changri_home/nginx_changri.conf）。
# 旧服务器（奥创，阿里云 Windows）的脚本留在 deploy_ultron.sh，那边服务已停，仅作回滚参考。
set -e

SERVER="jarvis"
REMOTE_DIR="/home/ubuntu/yuca_order"
SERVICE="yuca_order"
PUBLIC_URL="https://order.changri.work"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo " 排单宝部署 → 贾维斯 ($PUBLIC_URL)"
echo "======================================"

# 芭蕾主题的 PNG 原稿不上线（见 AGENTS.md，线上只用压缩后的 webp），部署时会排除；
# 这里先确认没有页面引用它们，免得漏传。
if grep -rqE "ballet-[A-Za-z0-9_-]+\.png" "$LOCAL_DIR/templates" "$LOCAL_DIR/static"/*.css "$LOCAL_DIR/static"/*.js "$LOCAL_DIR/app.py"; then
  echo "有页面引用了 ballet-*.png 原稿，但部署会排除这些文件，请改用压缩版 webp"
  exit 1
fi

# ── 1. 同步代码 ──────────────────────────────────────────────────────────────
echo "[1/3] 同步代码"
rsync -az "$LOCAL_DIR/app.py" "$LOCAL_DIR/requirements.txt" "$SERVER:$REMOTE_DIR/"
rsync -az --delete --exclude='.DS_Store' "$LOCAL_DIR/templates/" "$SERVER:$REMOTE_DIR/templates/"
# static/ 不加 --delete：保留服务器上已有的其他资源
rsync -az --exclude='.DS_Store' --exclude='ballet-*.png' "$LOCAL_DIR/static/" "$SERVER:$REMOTE_DIR/static/"

# ── 2. 装依赖 + 重启 ─────────────────────────────────────────────────────────
echo "[2/3] 安装依赖并重启服务"
ssh "$SERVER" "cd $REMOTE_DIR && venv/bin/pip install -q -r requirements.txt && sudo systemctl restart $SERVICE"
READY=0
for ATTEMPT in $(seq 1 10); do
  sleep 2
  CODE=$(ssh "$SERVER" "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:5023/" || true)
  if [ "$CODE" = "200" ]; then
    READY=1
    break
  fi
done
if [ "$READY" != "1" ]; then
  echo "服务没有正常响应，最近日志："
  ssh "$SERVER" "systemctl status $SERVICE --no-pager | head -15; tail -20 $REMOTE_DIR/logs/err.log"
  exit 1
fi

# ── 3. 外网验证 ──────────────────────────────────────────────────────────────
echo "[3/3] 外网验证"
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 10 "$PUBLIC_URL/" || echo "（外网连不通，检查 nginx 和腾讯云控制台防火墙的 443 端口）"

echo ""
echo "======================================"
echo " 部署完成！"
echo " 访问地址：$PUBLIC_URL"
echo " 管理员入口：$PUBLIC_URL/admin/login"
echo " 超管入口：$PUBLIC_URL/superadmin/login"
echo "======================================"
