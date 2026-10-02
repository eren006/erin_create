#!/bin/bash
# 推送 rp_archive 代码到贾维斯（不覆盖数据库、图片、日志、备份）
# 2026-09-30 起 rp_archive 跑在贾维斯：systemd 服务 rp_archive（waitress 127.0.0.1:5001），
# nginx 反代 https://archive.changri.work；环境变量在 /etc/rp_archive.env。
# 奥创 120.26.120.128:5001 上现在只是转发程序（nssm 服务 RPForward），别再往奥创部署。
# 用法: ./deploy.sh
set -e

LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE="jarvis:/home/ubuntu/rp_archive/"

echo ">>> 推送代码到 $REMOTE"
rsync -az --delete \
  --exclude 'venv/' --exclude '*.db' --exclude '*.db-*' --exclude 'static/' --exclude 'moment_images/' \
  --exclude 'logs/' --exclude 'backups/' --exclude 'error.log' --exclude '__pycache__/' \
  --exclude 'deploy.sh' --exclude 'start.bat' --exclude '.gitignore' --exclude 'backup_daily.sh' \
  "$LOCAL_DIR/app.py" "$LOCAL_DIR/backup.py" "$LOCAL_DIR/schema.sql" "$LOCAL_DIR/requirements.txt" \
  "$LOCAL_DIR/run.py" "$LOCAL_DIR/blocklist.txt" "$LOCAL_DIR/templates" "$LOCAL_DIR/tools" "$REMOTE"

echo ">>> 推送主题素材 static/themes（只加不删，不动 static 里的其它东西）"
ssh jarvis 'mkdir -p /home/ubuntu/rp_archive/static/themes'
rsync -az "$LOCAL_DIR/static/themes/" jarvis:/home/ubuntu/rp_archive/static/themes/

echo ">>> 推送 static 根目录下的 js/css（小游戏等页面脚本，如 phone-watermelon.js；只加不删）"
rsync -az --include='*.js' --include='*.css' --exclude='*' "$LOCAL_DIR/static/" jarvis:/home/ubuntu/rp_archive/static/

echo ">>> 安装依赖并重启..."
ssh jarvis 'cd /home/ubuntu/rp_archive && venv/bin/pip install -q -r requirements.txt && sudo systemctl restart rp_archive && sleep 3 && systemctl is-active rp_archive'

echo ">>> 自检..."
code=$(curl -s -o /dev/null -w "%{http_code}" https://archive.changri.work/login)
[ "$code" = "200" ] || { echo "❌ /login 返回 $code，去看 ssh jarvis 'sudo journalctl -u rp_archive -n 50'"; exit 1; }
echo ">>> 完成！https://archive.changri.work 正常"
