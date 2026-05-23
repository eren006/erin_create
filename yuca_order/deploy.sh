#!/bin/bash
# 排单宝 — 部署脚本
# 用法：bash deploy.sh [first|update]
#   first  — 首次部署（生成密钥、创建 systemd 服务）
#   update — 仅同步代码并重启（默认）

set -e

SERVER="administrator@47.99.64.227"
REMOTE="/opt/yuca_order"
SERVICE="yuca_order"
PORT=5003
MODE="${1:-update}"

echo "======================================"
echo " 排单宝部署  mode=$MODE  port=$PORT"
echo "======================================"

# ── 1. 同步文件 ──────────────────────────────────────────────────────────────
echo "[1/4] 同步文件到 ${SERVER}:${REMOTE}"
ssh "$SERVER" "mkdir -p ${REMOTE}/logs ${REMOTE}/uploads"
rsync -avz --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'order_data.db' \
  --exclude 'uploads/' \
  --exclude 'logs/' \
  --exclude '.DS_Store' \
  ./ "${SERVER}:${REMOTE}/"

# ── 2. 安装依赖 ──────────────────────────────────────────────────────────────
echo "[2/4] 安装 Python 依赖"
ssh "$SERVER" "pip3 install -q -r ${REMOTE}/requirements.txt"

# ── 3. 首次部署：创建 systemd 服务 ───────────────────────────────────────────
if [ "$MODE" = "first" ]; then
  echo "[3/4] 生成密钥并创建 systemd 服务"

  # 生成随机密钥（仅首次，存在则跳过）
  FLASK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(40))")
  SUPER_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

  echo ""
  echo "  ⚠️  请立即记录以下凭据，部署完成后不再显示："
  echo "  FLASK_SECRET : $FLASK_SECRET"
  echo "  SUPERADMIN密码: $SUPER_PASS"
  echo ""

  ssh "$SERVER" "sudo tee /etc/systemd/system/${SERVICE}.service > /dev/null << 'UNIT'
[Unit]
Description=排单宝 Order Portal
After=network.target

[Service]
Type=simple
User=administrator
WorkingDirectory=${REMOTE}
Environment=FLASK_SECRET=${FLASK_SECRET}
Environment=SUPERADMIN_PASS=${SUPER_PASS}
ExecStart=/usr/bin/python3 -m gunicorn -w 2 -b 0.0.0.0:${PORT} --timeout 60 --access-logfile ${REMOTE}/logs/access.log app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE}"

else
  echo "[3/4] 跳过 systemd 配置（update 模式）"
fi

# ── 4. 重启服务 ──────────────────────────────────────────────────────────────
echo "[4/4] 重启服务"
ssh "$SERVER" "sudo systemctl restart ${SERVICE} && sleep 2 && sudo systemctl status ${SERVICE} --no-pager -l"

echo ""
echo "======================================"
echo " 部署完成！"
echo " 访问地址：http://47.99.64.227:${PORT}"
echo " 管理员入口：http://47.99.64.227:${PORT}/admin/login"
echo " 超管入口：http://47.99.64.227:${PORT}/superadmin/login"
echo " API 文档："
echo "   GET  /api/orders?token=<token>&status=pending"
echo "   GET  /api/orders/<order_no>?token=<token>"
echo "   POST /api/orders/<order_no>/accept"
echo "   POST /api/orders/<order_no>/complete  {result_text}"
echo "   POST /api/orders/<order_no>/note       {note}"
echo "   GET  /api/stats?token=<token>"
echo "======================================"
