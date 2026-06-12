#!/bin/bash
# 推送 rp_archive 代码到服务器（不覆盖数据库）
# 用法: ./deploy.sh [服务器IP]

SERVER="120.26.120.128"
USER="Administrator"
REMOTE_DIR="C:/Users/Administrator/rp_archive"
LOCAL_DIR="$(dirname "$0")"

echo ">>> 推送 rp_archive 到 $USER@$SERVER:$REMOTE_DIR"

scp "$LOCAL_DIR/app.py"           "$USER@$SERVER:$REMOTE_DIR/app.py"
scp "$LOCAL_DIR/backup.py"        "$USER@$SERVER:$REMOTE_DIR/backup.py"
scp "$LOCAL_DIR/requirements.txt" "$USER@$SERVER:$REMOTE_DIR/requirements.txt"
scp "$LOCAL_DIR/schema.sql"       "$USER@$SERVER:$REMOTE_DIR/schema.sql"
scp "$LOCAL_DIR/start.bat"        "$USER@$SERVER:$REMOTE_DIR/start.bat"

echo ">>> 推送 templates/"
scp -r "$LOCAL_DIR/templates/"    "$USER@$SERVER:$REMOTE_DIR/templates/"

echo ">>> 重启服务..."
ssh "$USER@$SERVER" "nssm restart RPArchive"

echo ">>> 完成！"
