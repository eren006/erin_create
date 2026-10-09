#!/bin/bash
# 部署"hub 家族"静态页面：
#   主站  贾维斯 https://hub.changri.work（/var/www/hub，nginx 直出；许愿墙 API 反代到本机 rp_archive :5001）
#   旧链接 rp_archive 的 static/docs：2026-09-30 起 rp_archive 也在贾维斯（https://archive.changri.work/static/docs），
#         以前发出去的 http://120.26.120.128:5001/static/docs/... 经奥创转发程序也落到这里。SKIP_LEGACY=1 可跳过
# 三个文件绑在一起部署：改版本号/内容时最容易漏掉 changri_wishes.html，见记忆 feedback_changri_hub_pages_version
set -euo pipefail

# ---------- 主站：贾维斯（rsync 增量，Mac 上传贾维斯很慢） ----------
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
python3 sync_dist.py
ASSETS=$(grep -ohE "assets/[A-Za-z0-9_.-]+" changri_hub.html changri_wishes.html player_guide.html | sort -u)
echo ">>> rsync -> 贾维斯 /var/www/hub"
rsync -az --partial --relative -e ssh changri_hub.html changri_wishes.html player_guide.html $ASSETS jarvis:/var/www/hub/
for p in / /changri_wishes.html /player_guide.html; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://hub.changri.work$p")"
  echo "  hub.changri.work$p -> HTTP $code"
  [ "$code" = "200" ] || { echo "❌ 贾维斯校验失败"; exit 1; }
done

if [ "${SKIP_LEGACY:-0}" = "1" ]; then echo "✅ 已跳过旧站（奥创）"; exit 0; fi

# ---------- 旧链接：贾维斯上 rp_archive 的 static/docs ----------
echo ">>> rsync -> 贾维斯 rp_archive/static/docs（旧链接用）"
rsync -az -e ssh changri_hub.html changri_wishes.html player_guide.html jarvis:/home/ubuntu/rp_archive/static/docs/
for f in changri_hub.html changri_wishes.html player_guide.html; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://archive.changri.work/static/docs/$f")"
  echo "  archive.changri.work/static/docs/$f -> HTTP $code"
  [ "$code" = "200" ] || { echo "❌ 旧链接校验失败"; exit 1; }
done

echo "✅ hub 家族页面（changri_hub / changri_wishes / player_guide）部署完成"
