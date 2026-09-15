#!/bin/bash
# deploy.sh —— 把语擦助手图片服务一键部署到 Windows 服务器
#
# 前提：
#   1. 服务器上已经开启 OpenSSH Server，并允许密码登录
#      —— 这两项脚本会自动检查（端口能不能连上、密码能不能登录成功），
#         检查不过会直接停下并给出针对性的排查建议，不会往下继续跑
#   2. 服务器上已经装好 Node.js（node -v 能看到版本号，脚本也会检查）
#   3. 本地这台电脑装了 ssh / scp（macOS 自带）
#
# 用法：
#   ./deploy.sh
#   跟着提示输入服务器地址、用户名、目标路径；密码只会被要求输入一次
#   （通过 ssh 自带的连接复用功能，后续所有步骤都复用这一次登录，
#   密码本身不会被这个脚本保存、打印或传递给任何命令行参数）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "===== 语擦助手图片服务 一键部署 ====="
read -p "服务器地址 (只填 IP 或域名，不要带冒号和端口号): " SERVER_HOST
read -p "SSH 用户名: " SERVER_USER
read -p "SSH 端口 (直接回车用默认 22；跟其它服务的端口通常不是一回事): " SERVER_PORT
SERVER_PORT=${SERVER_PORT:-22}
read -p "服务器上要放到哪个路径 (直接回车用默认 C:/yuca_image_server): " REMOTE_DIR
REMOTE_DIR=${REMOTE_DIR:-"C:/yuca_image_server"}

if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_USER" ]; then
  echo "服务器地址和用户名不能为空，退出。"
  exit 1
fi

# 容错：地址里被误填成 "IP:端口" 时，自动只保留地址部分，避免和 SERVER_PORT 拼接出无法解析的地址
if [[ "$SERVER_HOST" == *:* ]]; then
  DETECTED_PORT="${SERVER_HOST##*:}"
  SERVER_HOST="${SERVER_HOST%%:*}"
  echo "⚠️ 检测到服务器地址里带了端口号（$DETECTED_PORT），已自动只保留地址部分：$SERVER_HOST"
  if [ "$DETECTED_PORT" != "$SERVER_PORT" ]; then
    echo "   如果 $DETECTED_PORT 才是真正的 SSH 端口，按 Ctrl+C 退出重跑，SSH 端口那一步填 $DETECTED_PORT。"
    echo "   如果 $DETECTED_PORT 只是别的服务的端口，不用管，继续用 $SERVER_PORT 就对了。"
  fi
fi

CTRL_SOCKET="/tmp/yuca_deploy_ssh_$$"

cleanup() {
  ssh -S "$CTRL_SOCKET" -O exit "$SERVER_USER@$SERVER_HOST" 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "==> 建立连接并测试密码登录，接下来会提示你输入一次密码（后续步骤都复用这次登录，不会再问）"
SSH_ERR_LOG="/tmp/yuca_deploy_ssherr_$$"
if ! ssh -M -S "$CTRL_SOCKET" -p "$SERVER_PORT" -o ControlPersist=10m -o ConnectTimeout=10 \
     -o PreferredAuthentications=password -o PubkeyAuthentication=no \
     -fN "$SERVER_USER@$SERVER_HOST" 2>"$SSH_ERR_LOG"; then
  ERR_MSG="$(cat "$SSH_ERR_LOG")"
  echo "$ERR_MSG"
  echo ""
  if echo "$ERR_MSG" | grep -qiE "refused|timed out|timeout|no route|unreachable|could not resolve"; then
    echo "❌ 连不上 $SERVER_HOST:$SERVER_PORT，SSH 服务大概率没在监听。常见原因："
    echo "  1. 服务器没装/没启动 OpenSSH Server"
    echo "     （Windows：设置 -> 应用 -> 可选功能，看有没有装「OpenSSH 服务器」；"
    echo "      装好后还要确认 sshd 服务是「正在运行」，可选自启动）"
    echo "  2. 服务器安全组/防火墙没放行这个端口"
    echo "  3. 地址或端口填错了"
  elif echo "$ERR_MSG" | grep -qiE "permission denied|authentication"; then
    echo "❌ 密码登录失败。端口是通的，问题大概率是："
    echo "  1. 用户名或密码输错了"
    echo "  2. 服务器上禁用了密码登录（只认密钥）"
    echo "     检查方法：登录服务器看 C:\\ProgramData\\ssh\\sshd_config，"
    echo "     确认里面有一行 PasswordAuthentication yes（不是 no，也没被注释掉），"
    echo "     改完要重启 sshd 服务：net stop sshd && net start sshd"
  else
    echo "❌ SSH 连接失败，具体原因看上面这行报错信息。"
  fi
  rm -f "$SSH_ERR_LOG"
  exit 1
fi
rm -f "$SSH_ERR_LOG"
echo "密码登录成功，开始部署。"

SSH() { ssh -S "$CTRL_SOCKET" "$SERVER_USER@$SERVER_HOST" "$@"; }
SCP_UPLOAD() { scp -o ControlPath="$CTRL_SOCKET" -P "$SERVER_PORT" "$@" "$SERVER_USER@$SERVER_HOST:$REMOTE_DIR/"; }

# 远端自动装 Node.js / 跑 npm install 用的 PowerShell 脚本，通过 -EncodedCommand（base64）
# 传给 ssh，绕开 cmd.exe / ssh 参数里嵌套引号的转义问题。
NODE_INSTALL_PS1='$ProgressPreference = "SilentlyContinue"
$nodeExe = $null
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeExe = "node"
} elseif (Test-Path "C:\Program Files\nodejs\node.exe") {
    $nodeExe = "C:\Program Files\nodejs\node.exe"
}
if (-not $nodeExe) {
    Write-Output "Node.js not found, downloading LTS installer..."
    try {
        $releases = Invoke-RestMethod -Uri "https://nodejs.org/dist/index.json" -UseBasicParsing
        $lts = $releases | Where-Object { $_.lts -ne $false } | Select-Object -First 1
        $ver = $lts.version
        $msiUrl = "https://nodejs.org/dist/$ver/node-$ver-x64.msi"
        $msiPath = Join-Path $env:TEMP "node_installer.msi"
        Invoke-WebRequest -Uri $msiUrl -OutFile $msiPath -UseBasicParsing
        Start-Process msiexec.exe -ArgumentList "/i `"$msiPath`" /quiet /norestart" -Wait
        Remove-Item $msiPath -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Output ("Install failed: " + $_.Exception.Message)
        exit 1
    }
    if (Test-Path "C:\Program Files\nodejs\node.exe") {
        $nodeExe = "C:\Program Files\nodejs\node.exe"
        Write-Output ("Installed: " + $ver)
    } else {
        Write-Output "Install seems to have failed, node.exe not found afterwards"
        exit 1
    }
}
& $nodeExe -v
'
NODE_INSTALL_ENCODED=$(printf '%s' "$NODE_INSTALL_PS1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

NPM_INSTALL_PS1_TEMPLATE='$ProgressPreference = "SilentlyContinue"
$npmCmd = $null
if (Get-Command npm -ErrorAction SilentlyContinue) {
    $npmCmd = "npm"
} elseif (Test-Path "C:\Program Files\nodejs\npm.cmd") {
    $npmCmd = "C:\Program Files\nodejs\npm.cmd"
}
if (-not $npmCmd) {
    Write-Output "npm not found"
    exit 1
}
& $npmCmd install --prefix "__REMOTE_DIR__"
'
NPM_INSTALL_PS1="${NPM_INSTALL_PS1_TEMPLATE//__REMOTE_DIR__/$REMOTE_DIR}"
NPM_INSTALL_ENCODED=$(printf '%s' "$NPM_INSTALL_PS1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

echo "==> 检查 / 自动安装服务器上的 Node.js（没装会自动下载 LTS 版安装，可能要等一会）..."
if ! SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $NODE_INSTALL_ENCODED"; then
  echo ""
  echo "Node.js 检查/安装失败，或者刚才的连接失败了。可以去服务器上手动跑 node -v 看看具体报错。"
  exit 1
fi

# 目标目录用 New-Item -Force 创建：已存在时不会报错，也不会有中文报错噪音
# （之前直接用 mkdir，目录已存在时 Windows 会用系统语言打印一行"命令语法不正确"）
MKDIR_PS1_TEMPLATE='$ProgressPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force -Path "__REMOTE_DIR__" | Out-Null
Write-Output "Target directory ready"
'
MKDIR_PS1="${MKDIR_PS1_TEMPLATE//__REMOTE_DIR__/$REMOTE_DIR}"
MKDIR_ENCODED=$(printf '%s' "$MKDIR_PS1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

echo "==> 在服务器上创建目标目录..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $MKDIR_ENCODED"

echo "==> 上传文件（board_server.js / draw.js / package.json / start_service.bat）..."
SCP_UPLOAD "$SCRIPT_DIR/board_server.js" "$SCRIPT_DIR/draw.js" "$SCRIPT_DIR/package.json" "$SCRIPT_DIR/start_service.bat"

echo "==> 在服务器上安装依赖（npm install，会自动拉取匹配服务器系统的原生绑定包）..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $NPM_INSTALL_ENCODED"

# 用 Windows 计划任务而不是 start /min 启动服务：OpenSSH 会话跑在没有桌面的
# 窗口站里，start 起的进程经常在会话结束后就没了、或者干脆起不来，这正是最容易
# 出现"部署完 ping 不通"的原因。计划任务不依赖任何会话，还顺带解决了"服务器
# 重启后图片服务不会自动恢复"的问题——注册成开机自启了。
SCHTASK_PS1_TEMPLATE='$ProgressPreference = "SilentlyContinue"
$taskName = "YucaImageService"
$batPath = "__REMOTE_DIR__\start_service.bat"
$workDir = "__REMOTE_DIR__"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

# 关键点：不能直接把 -Execute 指向 .bat 文件——不同 Windows 版本对计划任务里
# 直接执行 .bat 的文件关联解析并不总是可靠，实测会出现"任务注册成功但从没真正
# 跑起来"的情况。显式用 cmd.exe /c 调用就没有这个歧义。
$cmdArgs = "/c `"$batPath`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmdArgs -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Start-Sleep -Seconds 3
$task = Get-ScheduledTask -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskName $taskName
Write-Output ("Task state: " + $task.State)
Write-Output ("Last run time: " + $info.LastRunTime)
Write-Output ("Last task result: " + $info.LastTaskResult)
'
SCHTASK_PS1="${SCHTASK_PS1_TEMPLATE//__REMOTE_DIR__/$REMOTE_DIR}"
SCHTASK_ENCODED=$(printf '%s' "$SCHTASK_PS1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

echo "==> 注册并启动计划任务（同时会设置成开机自启）..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $SCHTASK_ENCODED"

echo "==> 等待 2 秒后检查服务状态..."
sleep 2
if SSH "curl -s http://127.0.0.1:8855/ping"; then
  echo ""
  echo "===== 部署完成，服务已启动 ====="
else
  echo ""
  echo "⚠️ 没能连上服务，可能还在启动或者启动失败了。可以远程桌面上去看一眼标题为「语擦助手图片服务」的窗口，或查看 $REMOTE_DIR\\board_server.log。"
fi

echo "海豹那边加载语擦助手_合并版.js 之后，「月历图」「结局分布图」两个指令就能用了。"
