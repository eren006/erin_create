#!/bin/bash
# 一键启动：发布控制台需要部署控制台在跑（代理转发部署请求），所以两个一起拉起来。
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../.." && pwd)"

if ! lsof -i :5064 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo ">>> 启动部署控制台 (5064)"
  (cd "$ROOT/deploy_dashboard" && python3 app.py) &
  sleep 1
else
  echo ">>> 部署控制台已经在跑了 (5064)"
fi

echo ">>> 启动发布控制台 (5098)"
python3 "$DIR/app.py" &
sleep 1

open "http://127.0.0.1:5098" 2>/dev/null || true

echo ">>> 都起来了：发布控制台 http://127.0.0.1:5098 ｜ 部署控制台 http://127.0.0.1:5064"
echo ">>> tools/ 下还有两个命令行小工具（不用起服务）："
echo "      tools/remote_diff.sh   上传前对比本地和线上文件"
echo "      tools/remote_query.py  对线上 sqlite 库跑只读查询，输出干净 UTF-8"
echo ">>> 按 Ctrl+C 结束（会停掉这次启动的两个进程）"
wait
