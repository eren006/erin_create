#!/bin/bash
# 部署"hub 家族"静态页面到 rp_archive 的 static/docs
# 三个文件绑在一起部署：改版本号/内容时最容易漏掉 changri_wishes.html，见记忆 feedback_changri_hub_pages_version
set -euo pipefail

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/rp_archive/static/docs"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_URL="http://120.26.120.128:5001/static/docs"

FILES=(changri_hub.html changri_wishes.html player_guide.html)

for f in "${FILES[@]}"; do
  echo ">>> 上传 $f"
  scp -q "$LOCAL_DIR/$f" "$SERVER:$REMOTE_DIR/$f"
done

echo ">>> 校验线上版本"
FAILED=0
for f in "${FILES[@]}"; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/$f")"
  if [ "$code" = "200" ]; then
    echo "  ✓ $f -> HTTP $code"
  else
    echo "  ✗ $f -> HTTP $code"
    FAILED=1
  fi
done

if [ "$FAILED" -ne 0 ]; then
  echo "❌ 有页面校验失败，请检查"
  exit 1
fi

echo "✅ hub 家族页面（changri_hub / changri_wishes / player_guide）部署完成"
