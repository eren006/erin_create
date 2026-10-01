#!/bin/bash
# 上传前先看本地文件和线上文件有没有差异，避免线上有本地不知道的改动被静默覆盖掉。
#
# 用法：
#   ./remote_diff.sh <本地文件路径> <远端完整路径> [ssh别名，默认 ultron]
#
# 例：
#   ./remote_diff.sh ../../rp_archive/app.py "C:/Users/Administrator/rp_archive/app.py"
#   ./remote_diff.sh ../../长日系统.js "C:/Users/Administrator/qq_bot/长日系统.js" jarvis
#
# 退出码：0 = 一致，1 = 有差异，2 = 用法错误/拉取失败。差异会打印成 unified diff（< 本地 / > 线上）。
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "用法：$0 <本地文件> <远端完整路径> [ssh别名，默认 ultron]" >&2
  exit 2
fi

LOCAL="$1"
REMOTE="$2"
ALIAS="${3:-ultron}"

if [ ! -f "$LOCAL" ]; then
  echo "❌ 本地文件不存在：$LOCAL" >&2
  exit 2
fi

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

if ! scp -q "$ALIAS:$REMOTE" "$TMP" 2>/tmp/remote_diff_scp_err; then
  echo "❌ 拉取线上文件失败（$ALIAS:$REMOTE）：" >&2
  cat /tmp/remote_diff_scp_err >&2
  exit 2
fi

if diff -q "$LOCAL" "$TMP" >/dev/null; then
  echo "✅ 一致：本地 $LOCAL  ==  线上 $ALIAS:$REMOTE"
  exit 0
else
  echo "⚠️ 有差异（< 本地 $LOCAL / > 线上 $ALIAS:$REMOTE）："
  diff -u "$LOCAL" "$TMP" || true
  exit 1
fi
