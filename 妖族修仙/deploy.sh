#!/bin/bash
# 推送 妖族修仙 代码到服务器（不覆盖数据库）
# 用法: ./deploy.sh
set -e

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/yaozu_xiuxian"
WIN_DIR="C:\Users\Administrator\yaozu_xiuxian"
LOCAL_DIR="$(dirname "$0")"

echo ">>> 推送 妖族修仙 到 $SERVER:$REMOTE_DIR"

scp "$LOCAL_DIR/app.py" "$LOCAL_DIR/game_data.py" "$LOCAL_DIR/run.py" \
    "$LOCAL_DIR/requirements.txt" "$LOCAL_DIR/schema.sql" "$SERVER:$REMOTE_DIR/"

echo ">>> 清理远端旧 templates 目录(避免 scp -r 嵌套成 templates/templates)..."
ssh "$SERVER" "if exist $WIN_DIR\\templates rmdir /s /q $WIN_DIR\\templates"

echo ">>> 推送 templates/"
scp -r "$LOCAL_DIR/templates"     "$SERVER:$REMOTE_DIR/"

echo ">>> 重启服务..."
ssh "$SERVER" "nssm restart yaozu"

echo ">>> 完成！"
