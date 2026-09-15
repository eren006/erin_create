#!/bin/bash
# ⚠️ 已停用：2026-09-10 排单宝已迁到贾维斯（腾讯云 Ubuntu），日常部署用 deploy.sh。
#    本文件只留作回滚参考；奥创上的 yucaorder 服务已停止并改为手动启动。
# 排单宝 — 部署脚本（奥创：阿里云 Windows 服务器 120.26.120.128，nssm 管理）
# 用法：bash deploy.sh [first|update]
#   first  — 首次部署（建目录、装 nssm 服务、开防火墙）
#   update — 仅同步代码并重启服务（默认，日常用这个）
#
# templates/ 用 tar.gz 打包成单文件传输，而不是 scp -r 逐个小文件传
# （Windows OpenSSH 对着一堆小文件走 scp -r 很慢，远端已确认装了 bsdtar）
set -e

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/yuca_order"
WIN_DIR="C:\Users\Administrator\yuca_order"
SERVICE="yucaorder"
PORT=5023
PYTHON_EXE="C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
MODE="${1:-update}"
LOCAL_DIR="$(dirname "$0")"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "======================================"
echo " 排单宝部署  mode=$MODE  port=$PORT"
echo "======================================"

# ── 1. 首次部署：建目录 ──────────────────────────────────────────────────────
if [ "$MODE" = "first" ]; then
  echo "[1/4] 创建远端目录"
  ssh "$SERVER" "mkdir $WIN_DIR & mkdir $WIN_DIR\\logs & mkdir $WIN_DIR\\uploads" || true
fi

# ── 2. 同步代码（绝不 scp order_data.db，首次启动自动建表）─────────────────────
echo "[2/4] 同步 app.py / requirements.txt"
scp "$LOCAL_DIR/app.py" "$LOCAL_DIR/requirements.txt" "$SERVER:$REMOTE_DIR/"

echo ">>> 推送 templates/（打包 tar.gz 传输，再原地改名替换）..."
COPYFILE_DISABLE=1 tar czf "$TMP_DIR/templates.tar.gz" -C "$LOCAL_DIR/templates" .
scp "$TMP_DIR/templates.tar.gz" "$SERVER:$REMOTE_DIR/templates.tar.gz"
ssh "$SERVER" "(if exist $WIN_DIR\\templates_new rmdir /s /q $WIN_DIR\\templates_new) & mkdir $WIN_DIR\\templates_new & tar xzf $WIN_DIR\\templates.tar.gz -C $WIN_DIR\\templates_new & del $WIN_DIR\\templates.tar.gz & (if exist $WIN_DIR\\templates_old rmdir /s /q $WIN_DIR\\templates_old) & (if exist $WIN_DIR\\templates ren $WIN_DIR\\templates templates_old) & ren $WIN_DIR\\templates_new templates & (if exist $WIN_DIR\\templates_old rmdir /s /q $WIN_DIR\\templates_old)"

# 同步主题静态资源，保留服务器上已有的其他资源。
if [ -d "$LOCAL_DIR/static" ]; then
  echo ">>> 推送 static/ ..."
  COPYFILE_DISABLE=1 tar czf "$TMP_DIR/static.tar.gz" -C "$LOCAL_DIR/static" .
  scp "$TMP_DIR/static.tar.gz" "$SERVER:$REMOTE_DIR/static.tar.gz"
  ssh "$SERVER" "(if not exist $WIN_DIR\\static mkdir $WIN_DIR\\static) & tar xzf $WIN_DIR\\static.tar.gz -C $WIN_DIR\\static && del $WIN_DIR\\static.tar.gz"
fi

# ── 3. 首次部署：注册 nssm 服务 + 防火墙 ────────────────────────────────────
if [ "$MODE" = "first" ]; then
  echo "[3/4] 注册 nssm 服务并开防火墙"

  FLASK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(40))")
  SUPER_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

  echo ""
  echo "  ⚠️  请立即记录以下凭据，部署完成后不再显示："
  echo "  FLASK_SECRET  : $FLASK_SECRET"
  echo "  SUPERADMIN密码 : $SUPER_PASS"
  echo ""

  ssh "$SERVER" "nssm install $SERVICE \"$PYTHON_EXE\" \"$WIN_DIR\\app.py\""
  ssh "$SERVER" "nssm set $SERVICE AppDirectory $WIN_DIR"
  ssh "$SERVER" "nssm set $SERVICE AppStdout $WIN_DIR\\logs\\out.log"
  ssh "$SERVER" "nssm set $SERVICE AppStderr $WIN_DIR\\logs\\err.log"
  ssh "$SERVER" "nssm set $SERVICE AppEnvironmentExtra PORT=$PORT FLASK_SECRET=$FLASK_SECRET SUPERADMIN_PASS=$SUPER_PASS"
  ssh "$SERVER" "nssm set $SERVICE Start SERVICE_AUTO_START"
  ssh "$SERVER" "netsh advfirewall firewall add rule name=\"$SERVICE $PORT\" dir=in action=allow protocol=TCP localport=$PORT"
  ssh "$SERVER" "nssm start $SERVICE"
else
  echo "[3/4] 跳过 nssm 注册（update 模式），重启服务"
  ssh "$SERVER" "nssm restart $SERVICE" || echo ">>> 等待服务状态稳定"
  READY=0
  for ATTEMPT in $(seq 1 24); do
    SERVICE_STATE=$(ssh "$SERVER" "sc query $SERVICE")
    if [[ "$SERVICE_STATE" == *"RUNNING"* ]]; then
      READY=1
      break
    elif [[ "$SERVICE_STATE" == *"STOPPED"* ]]; then
      ssh "$SERVER" "nssm start $SERVICE" || true
    fi
    sleep 3
  done
  if [ "$READY" != "1" ]; then
    echo "服务未能进入 RUNNING 状态，请检查服务器日志"
    exit 1
  fi
fi

# ── 4. 验证 ──────────────────────────────────────────────────────────────────
echo "[4/4] 验证服务"
sleep 2
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 "http://120.26.120.128:${PORT}/" || echo "（本机连不通，去服务器上用 curl 127.0.0.1:$PORT 确认）"

echo ""
echo "======================================"
echo " 部署完成！"
echo " 访问地址：http://120.26.120.128:${PORT}"
echo " 管理员入口：http://120.26.120.128:${PORT}/admin/login"
echo " 超管入口：http://120.26.120.128:${PORT}/superadmin/login"
echo "======================================"
