#!/bin/bash
# 部署"hub 家族"静态页面：
#   主站  贾维斯 https://hub.changri.work（/var/www/hub，nginx 直出；许愿墙 API 反代回奥创 rp_archive :5001）
#   旧站  奥创 rp_archive 的 static/docs（暂时保留；SKIP_LEGACY=1 可跳过）
# 三个文件绑在一起部署：改版本号/内容时最容易漏掉 changri_wishes.html，见记忆 feedback_changri_hub_pages_version
set -euo pipefail

# ---------- 主站：贾维斯（rsync 增量，Mac 上传贾维斯很慢） ----------
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
ASSETS=$(grep -ohE "assets/[A-Za-z0-9_.-]+" changri_hub.html changri_wishes.html player_guide.html | sort -u)
echo ">>> rsync -> 贾维斯 /var/www/hub"
rsync -az --partial --relative -e ssh changri_hub.html changri_wishes.html player_guide.html $ASSETS jarvis:/var/www/hub/
for p in / /changri_wishes.html /player_guide.html; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://hub.changri.work$p")"
  echo "  hub.changri.work$p -> HTTP $code"
  [ "$code" = "200" ] || { echo "❌ 贾维斯校验失败"; exit 1; }
done

if [ "${SKIP_LEGACY:-0}" = "1" ]; then echo "✅ 已跳过旧站（奥创）"; exit 0; fi

# ---------- 旧站：奥创 ----------
SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/rp_archive/static/docs"
LOCAL_DIR="$HERE"
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
