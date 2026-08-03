#!/bin/bash
# 增量推送 qq_bot 到 Windows 服务器，不覆盖 data/、venv/ 和服务器密钥。
# 用法：./deploy.sh          只部署上次成功后发生变化的文件
#       ./deploy.sh --full   强制全量部署
#       ./deploy.sh --dry-run 仅显示将要部署的文件
set -euo pipefail

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/qq_bot"
REMOTE_WIN="C:\\Users\\Administrator\\qq_bot"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$LOCAL_DIR/.deploy-manifest"
MODE="${1:-}"

case "$MODE" in
  ""|--full|--dry-run|--record-current) ;;
  *) echo "用法：$0 [--full|--dry-run]" >&2; exit 2 ;;
esac

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
CURRENT="$STAGE/current.tsv"
CHANGED="$STAGE/changed.txt"
DELETED="$STAGE/deleted.txt"

cd "$LOCAL_DIR"

collect_files() {
  for file in \
    bot.py newspaper_web.py newspaper_service.py \
    web_app.py web_auth.py submissions.py requirements.txt .env .env.dev; do
    [ ! -f "$file" ] || printf '%s\n' "$file"
  done
  find plugins templates static -type f \
    ! -path '*/__pycache__/*' ! -name '*.pyc' ! -name '.DS_Store' -print
}

build_manifest() {
  collect_files | LC_ALL=C sort | while IFS= read -r file; do
    printf '%s\t%s\n' "$(shasum -a 256 "$file" | awk '{print $1}')" "$file"
  done
}

build_manifest > "$CURRENT"

if [ "$MODE" = "--record-current" ]; then
  cp "$CURRENT" "$MANIFEST"
  echo ">>> 已把当前文件状态记为部署基线。"
  exit 0
fi

if [ "$MODE" = "--full" ] || [ ! -f "$MANIFEST" ]; then
  cut -f2- "$CURRENT" > "$CHANGED"
  : > "$DELETED"
  FULL_DEPLOY=1
else
  awk -F '\t' 'NR==FNR { old[$2]=$1; next }
    !($2 in old) || old[$2] != $1 { print $2 }' "$MANIFEST" "$CURRENT" > "$CHANGED"
  awk -F '\t' 'NR==FNR { current[$2]=1; next }
    !($2 in current) { print $2 }' "$CURRENT" "$MANIFEST" > "$DELETED"
  FULL_DEPLOY=0
fi

CHANGE_COUNT="$(awk 'END {print NR+0}' "$CHANGED")"
DELETE_COUNT="$(awk 'END {print NR+0}' "$DELETED")"

if [ "$CHANGE_COUNT" -eq 0 ] && [ "$DELETE_COUNT" -eq 0 ]; then
  echo ">>> 没有文件变化，无需部署。"
  exit 0
fi

echo ">>> 增量部署：上传 $CHANGE_COUNT 个文件，删除 $DELETE_COUNT 个远端旧文件"
[ "$CHANGE_COUNT" -eq 0 ] || sed 's/^/  + /' "$CHANGED"
[ "$DELETE_COUNT" -eq 0 ] || sed 's/^/  - /' "$DELETED"

if [ "$MODE" = "--dry-run" ]; then
  exit 0
fi

# 变化文件先摊进临时目录，再压成一个 ZIP；只建立一次 SCP 连接。
PAYLOAD="$STAGE/payload"
mkdir -p "$PAYLOAD"
while IFS= read -r file; do
  [ -z "$file" ] && continue
  mkdir -p "$PAYLOAD/$(dirname "$file")"
  cp -p "$file" "$PAYLOAD/$file"
done < "$CHANGED"
cp "$DELETED" "$PAYLOAD/__deploy_delete__.txt"
cp "$LOCAL_DIR/deploy_remote_apply.py" "$PAYLOAD/__deploy_remote_apply.py"

BUNDLE="$STAGE/qq_bot_incremental.zip"
(cd "$PAYLOAD" && zip -q -r "$BUNDLE" .)

echo ">>> 上传压缩包（$(du -h "$BUNDLE" | awk '{print $1}')）"
scp -q "$BUNDLE" "$SERVER:$REMOTE_DIR/__deploy_bundle.zip"

echo ">>> 在服务器应用文件变化"
ssh "$SERVER" "powershell -NoProfile -Command \"Expand-Archive -LiteralPath '$REMOTE_WIN\\__deploy_bundle.zip' -DestinationPath '$REMOTE_WIN' -Force\""
ssh "$SERVER" "cd $REMOTE_WIN && python __deploy_remote_apply.py"
ssh "$SERVER" "del /Q $REMOTE_WIN\\__deploy_bundle.zip $REMOTE_WIN\\__deploy_remote_apply.py"

ALL_CHANGES="$STAGE/all_changes.txt"
cat "$CHANGED" "$DELETED" > "$ALL_CHANGES"

if [ "$FULL_DEPLOY" -eq 1 ] || grep -qx 'requirements.txt' "$ALL_CHANGES"; then
  echo ">>> requirements.txt 有变化，安装依赖"
  ssh "$SERVER" "cd $REMOTE_WIN && python -m pip install -q -r requirements.txt"
fi

BOT_CHANGED=0
NEWS_CHANGED=0
WEB_CHANGED=0
grep -Eq '^(bot\.py|plugins/|\.env($|\.))' "$ALL_CHANGES" && BOT_CHANGED=1 || true
grep -Eq '^(newspaper_(web|service)\.py|templates/newspaper|plugins/hp_|\.env($|\.))' "$ALL_CHANGES" && NEWS_CHANGED=1 || true
grep -Eq '^(web_app\.py|web_auth\.py|submissions\.py|templates/web/|static/|plugins/hp_|\.env($|\.))' "$ALL_CHANGES" && WEB_CHANGED=1 || true

restart_service() {
  service="$1"
  if ! ssh "$SERVER" "nssm restart $service"; then
    echo ">>> $service 正在停止，等待后重新启动"
    ssh "$SERVER" "powershell -NoProfile -Command \"Start-Sleep -Seconds 4\" & nssm start $service"
  fi
}

echo ">>> 按需重启服务"
[ "$BOT_CHANGED" -eq 0 ] || restart_service changriqqbot
[ "$NEWS_CHANGED" -eq 0 ] || restart_service hogwartsnews
[ "$WEB_CHANGED" -eq 0 ] || restart_service hogwartsgame

# 只有全部上传、应用和重启成功后才更新基线；失败时下次仍会重试这些文件。
cp "$CURRENT" "$MANIFEST"
echo ">>> 部署完成。"
