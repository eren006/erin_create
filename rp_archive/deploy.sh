#!/bin/bash
# 推送 rp_archive 代码到服务器（不覆盖数据库）
# 用法: ./deploy.sh [服务器IP]
set -e

SERVER="120.26.120.128"
USER="Administrator"
REMOTE_DIR="C:/Users/Administrator/rp_archive"
LOCAL_DIR="$(dirname "$0")"

echo ">>> 推送 rp_archive 到 $USER@$SERVER:$REMOTE_DIR"

scp "$LOCAL_DIR/app.py"           "ultron:$REMOTE_DIR/app.py"
scp "$LOCAL_DIR/backup.py"        "ultron:$REMOTE_DIR/backup.py"
scp "$LOCAL_DIR/requirements.txt" "ultron:$REMOTE_DIR/requirements.txt"
scp "$LOCAL_DIR/schema.sql"       "ultron:$REMOTE_DIR/schema.sql"
scp "$LOCAL_DIR/start.bat"        "ultron:$REMOTE_DIR/start.bat"

echo ">>> 清理远端旧 templates/（scp -r 遇到已存在的同名目录会嵌套成 templates/templates）"
ssh ultron "rmdir /S /Q \"$REMOTE_DIR/templates\" 2>nul & exit 0"

echo ">>> 推送 templates/"
scp -r "$LOCAL_DIR/templates/"    "ultron:$REMOTE_DIR/templates/"

echo ">>> 重启服务..."
ssh ultron "nssm restart RPArchive"

echo ">>> 完成！"
