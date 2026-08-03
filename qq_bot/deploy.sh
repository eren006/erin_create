#!/bin/bash
# 推送 qq_bot 代码到服务器（不覆盖数据库、不覆盖 venv）
# 用法: ./deploy.sh

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/qq_bot"
LOCAL_DIR="$(dirname "$0")"

echo ">>> 推送 qq_bot 到 $SERVER:$REMOTE_DIR"

scp "$LOCAL_DIR/bot.py"           "$SERVER:$REMOTE_DIR/bot.py"
scp "$LOCAL_DIR/newspaper_web.py" "$SERVER:$REMOTE_DIR/newspaper_web.py"
scp "$LOCAL_DIR/newspaper_service.py" "$SERVER:$REMOTE_DIR/newspaper_service.py"
scp "$LOCAL_DIR/requirements.txt" "$SERVER:$REMOTE_DIR/requirements.txt"
scp "$LOCAL_DIR/.env"             "$SERVER:$REMOTE_DIR/.env"
scp "$LOCAL_DIR/.env.dev"         "$SERVER:$REMOTE_DIR/.env.dev"

echo ">>> 清空远端 plugins/（防止 scp -r 把新文件夹嵌套进旧目录）"
ssh "$SERVER" "rmdir /S /Q C:\\Users\\Administrator\\qq_bot\\plugins"

echo ">>> 推送 plugins/"
scp -r "$LOCAL_DIR/plugins/"      "$SERVER:$REMOTE_DIR/plugins/"
scp -r "$LOCAL_DIR/templates/"    "$SERVER:$REMOTE_DIR/templates/"

echo ">>> 重启服务..."
ssh "$SERVER" "nssm restart changriqqbot"

echo ">>> 完成！"
