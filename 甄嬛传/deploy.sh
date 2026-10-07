#!/bin/bash
# 甄嬛传·紫禁城 — 部署到贾维斯（腾讯云 Ubuntu 124.221.189.86，https://zhenhuan.changri.work，systemd）
# 用法：bash deploy.sh
#
# 只同步代码：app.py / run.py / schema.sql / blocklist.txt / requirements.txt / templates/，
# 绝不碰服务器上的 zhenhuan.db、db_backups/、logs/、venv/。
# 本地到腾讯云上行只有几 KB/s，所以用 rsync 增量传。
# 环境变量（PORT / FLASK_SECRET / ADMIN_PASSWORD / SETTLE_HOUR）在服务器 /etc/zhenhuan.env，不在仓库里。
# 服务配置：/etc/systemd/system/zhenhuan.service（waitress 监听 5024），对外由 nginx 按子域名反代并提供 HTTPS
# （/etc/nginx/sites-available/changri，本地副本 changri_home/nginx_changri.conf）。
set -e

SERVER="jarvis"
REMOTE_DIR="/home/ubuntu/zhenhuan"
SERVICE="zhenhuan"
PORT=5024
PUBLIC_URL="https://zhenhuan.changri.work"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo " 甄嬛传部署 → 贾维斯 ($PUBLIC_URL)"
echo "======================================"

echo "[1/3] 同步代码"
ssh "$SERVER" "mkdir -p $REMOTE_DIR/logs"
rsync -az "$LOCAL_DIR/app.py" "$LOCAL_DIR/run.py" "$LOCAL_DIR/schema.sql" "$LOCAL_DIR/blocklist.txt" "$LOCAL_DIR/requirements.txt" "$SERVER:$REMOTE_DIR/"
rsync -az --delete --exclude='.DS_Store' "$LOCAL_DIR/templates/" "$SERVER:$REMOTE_DIR/templates/"

rsync -az "$LOCAL_DIR/static/" "$SERVER:$REMOTE_DIR/static/"

echo "[2/3] 安装依赖并重启服务"
ssh "$SERVER" "cd $REMOTE_DIR && ( [ -d venv ] || python3 -m venv venv ) && venv/bin/pip install -q -r requirements.txt && sudo sed -i 's/^SETTLE_HOUR=.*/SETTLE_HOUR=0/' /etc/zhenhuan.env && sudo systemctl restart $SERVICE"
READY=0
for ATTEMPT in $(seq 1 10); do
  sleep 2
  CODE=$(ssh "$SERVER" "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:$PORT/login" || true)
  if [ "$CODE" = "200" ]; then READY=1; break; fi
done
if [ "$READY" != "1" ]; then
  echo "服务没有正常响应，最近日志："
  ssh "$SERVER" "systemctl status $SERVICE --no-pager | head -15; tail -20 $REMOTE_DIR/logs/err.log"
  exit 1
fi

echo "[3/3] 外网验证"
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 10 "$PUBLIC_URL/login" || echo "（外网连不通，检查 nginx 和腾讯云控制台防火墙的 443 端口）"
echo "完成：$PUBLIC_URL"
