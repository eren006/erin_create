#!/bin/bash
# 推送 qq_bot 代码到服务器（不覆盖数据库、不覆盖 venv）
# 用法: ./deploy.sh
set -e

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/qq_bot"
REMOTE_WIN="C:\\Users\\Administrator\\qq_bot"
LOCAL_DIR="$(dirname "$0")"

echo ">>> 推送 qq_bot 到 $SERVER:$REMOTE_DIR"

for f in bot.py \
         newspaper_web.py newspaper_service.py \
         web_app.py web_auth.py submissions.py \
         requirements.txt .env .env.dev; do
  scp "$LOCAL_DIR/$f" "$SERVER:$REMOTE_DIR/$f"
done

# 先删远端目录再整目录推送，否则 scp -r 会把新目录嵌套进旧目录里
echo ">>> 重推 plugins/ 和 templates/"
ssh "$SERVER" "if exist $REMOTE_WIN\\plugins rmdir /S /Q $REMOTE_WIN\\plugins"
ssh "$SERVER" "if exist $REMOTE_WIN\\templates rmdir /S /Q $REMOTE_WIN\\templates"
scp -q -r "$LOCAL_DIR/plugins/"   "$SERVER:$REMOTE_DIR/plugins/"
scp -q -r "$LOCAL_DIR/templates/" "$SERVER:$REMOTE_DIR/templates/"

echo ">>> 安装依赖"
ssh "$SERVER" "cd $REMOTE_WIN && python -m pip install -q -r requirements.txt"

echo ">>> 重启服务..."
ssh "$SERVER" "nssm restart changriqqbot"
ssh "$SERVER" "nssm restart hogwartsnews" || echo "（校报服务未安装，跳过）"
ssh "$SERVER" "nssm restart hogwartsgame" || echo "（游戏网页服务未安装，跳过）"

echo ">>> 完成！"
