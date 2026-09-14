#!/bin/bash
# Yuca Helper Image Service - GUI one-click deploy (Mac version)
# Double-click this file to run (it will open a Terminal window and a few small
# dialog boxes asking for info).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_TITLE="Yuca Helper Image Service - One-Click Deploy"

notify() {
  osascript -e "display dialog \"$1\" with title \"$APP_TITLE\" buttons {\"OK\"} default button \"OK\"" >/dev/null 2>&1
}

if ! command -v expect >/dev/null 2>&1; then
  echo "This Mac doesn't have 'expect' installed (used to auto-send the password to ssh in the popup)."
  echo "Install it and re-run this file:"
  echo "  brew install expect"
  notify "Missing the 'expect' tool. Run 'brew install expect' in Terminal, then double-click this file again."
  exit 1
fi

# $1=prompt text $2=default value $3=hidden(true/false)
ask() {
  local prompt="$1" default="$2" hidden="$3"
  local hidden_clause=""
  [ "$hidden" = "true" ] && hidden_clause="with hidden answer"
  local result
  result=$(osascript -e "
  try
    set theResult to text returned of (display dialog \"$prompt\" default answer \"$default\" with title \"$APP_TITLE\" $hidden_clause buttons {\"Cancel\", \"Next\"} default button \"Next\")
    return theResult
  on error number -128
    return \"__CANCELLED__\"
  end try
  ")
  if [ "$result" = "__CANCELLED__" ]; then
    echo "Deploy cancelled."
    exit 1
  fi
  echo "$result"
}

echo "===== $APP_TITLE ====="
echo "A few small dialog boxes will pop up asking for information."
echo ""

SERVER_HOST=$(ask "Server address:\nIP or domain only, no colon or port number (e.g. 123.45.67.89) - the port is entered separately next" "" false)
SERVER_USER=$(ask "SSH username:\nThe account you log in to the server with, usually the same as your Remote Desktop login" "" false)
SERVER_PORT=$(ask "SSH port:\nLeave the default 22 if unsure - this is usually different from ports used by your other services (e.g. a web service port)" "22" false)
REMOTE_DIR=$(ask "Target path on the server:\nThis is a folder path on the Windows server" "C:/yuca_image_server" false)
SERVER_PASS=$(ask "SSH password:\nThe password you log in to the server with, usually the same as your Remote Desktop password" "" true)

if [ -z "$SERVER_HOST" ] || [ -z "$SERVER_USER" ]; then
  notify "Server address and username cannot be empty. Deploy cancelled."
  exit 1
fi

# Fallback: if the address was mistakenly entered as "IP:port" (e.g. mixing up a
# web service port with the SSH port), auto-strip to just the address part so it
# doesn't get concatenated with the separately-entered SSH port into an
# unparseable address.
if [[ "$SERVER_HOST" == *:* ]]; then
  DETECTED_PORT="${SERVER_HOST##*:}"
  SERVER_HOST="${SERVER_HOST%%:*}"
  echo "⚠️ Detected a port number in the server address ($DETECTED_PORT); automatically kept only the address part: $SERVER_HOST"
  if [ "$DETECTED_PORT" != "$SERVER_PORT" ]; then
    echo "   Note: $DETECTED_PORT is different from the SSH port you just entered ($SERVER_PORT)."
    echo "   If $DETECTED_PORT is actually some other service's port (e.g. a web server), ignore this and continue with $SERVER_PORT."
    echo "   If $DETECTED_PORT is the real SSH port, press Ctrl+C to quit and re-run, entering $DETECTED_PORT as the SSH port."
  fi
fi

echo "Server: $SERVER_USER@$SERVER_HOST:$SERVER_PORT"
echo "Target path: $REMOTE_DIR"
echo "Starting connect / upload / install deps / start service - progress will print in this window."
echo ""

CTRL_SOCKET="/tmp/yuca_deploy_ssh_$$"
cleanup() {
  ssh -S "$CTRL_SOCKET" -O exit "$SERVER_USER@$SERVER_HOST" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Connecting..."
EXPECT_LOG="/tmp/yuca_deploy_expect_$$.log"
SERVER_HOST="$SERVER_HOST" SERVER_USER="$SERVER_USER" SERVER_PORT="$SERVER_PORT" \
CTRL_SOCKET="$CTRL_SOCKET" SERVER_PASS="$SERVER_PASS" \
expect -c '
  log_user 0
  set host $env(SERVER_HOST)
  set user $env(SERVER_USER)
  set port $env(SERVER_PORT)
  set sock $env(CTRL_SOCKET)
  set pass $env(SERVER_PASS)
  spawn ssh -M -S $sock -p $port -o ControlPersist=10m -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -fN "$user@$host"
  expect {
    "*assword:*" { send "$pass\r"; exp_continue }
    "*yes/no*" { send "yes\r"; exp_continue }
    eof
  }
  catch wait result
  exit [lindex $result 3]
' > "$EXPECT_LOG" 2>&1
EXPECT_STATUS=$?
SERVER_PASS=""

if [ $EXPECT_STATUS -ne 0 ] || ! ssh -S "$CTRL_SOCKET" -O check "$SERVER_USER@$SERVER_HOST" 2>/dev/null; then
  echo "❌ Connection or password authentication failed."
  echo "Common causes: wrong password, wrong username, SSH password login not enabled on the server, wrong address/port."
  rm -f "$EXPECT_LOG"
  notify "Connection failed - possibly a wrong password/username, or the server doesn't have SSH password login enabled. See the Terminal window for details."
  exit 1
fi
rm -f "$EXPECT_LOG"
echo "Connected."

SSH() { ssh -S "$CTRL_SOCKET" "$SERVER_USER@$SERVER_HOST" "$@"; }
SCP_UPLOAD() { scp -o ControlPath="$CTRL_SOCKET" -P "$SERVER_PORT" "$@" "$SERVER_USER@$SERVER_HOST:$REMOTE_DIR/"; }

# PowerShell script that auto-installs Node.js / runs npm install on the remote
# end, passed to ssh via -EncodedCommand (base64) to fully sidestep nested-quote
# escaping issues in cmd.exe / ssh arguments (the same lesson learned from the
# Windows version once getting mangled by nested-quote + encoding issues - this
# uses the same, more reliable approach from the start).
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

echo "==> Checking / auto-installing Node.js on the server (if missing, it will download and install the LTS build - this may take a bit)..."
if ! SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $NODE_INSTALL_ENCODED"; then
  echo "Node.js check/install failed, or the connection above failed."
  notify "Node.js check/install failed. You can SSH into the server and run 'node -v' manually to see the error, or install it manually from nodejs.org."
  exit 1
fi

# Create the target directory with New-Item -Force: doesn't error if it already
# exists, and doesn't print any locale-dependent error noise (a plain "mkdir" on
# an existing directory used to print a localized "command syntax is incorrect"
# line depending on the server's system language).
MKDIR_PS1_TEMPLATE='$ProgressPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force -Path "__REMOTE_DIR__" | Out-Null
Write-Output "Target directory ready"
'
MKDIR_PS1="${MKDIR_PS1_TEMPLATE//__REMOTE_DIR__/$REMOTE_DIR}"
MKDIR_ENCODED=$(printf '%s' "$MKDIR_PS1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n')

echo "==> Creating the target directory on the server..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $MKDIR_ENCODED"

echo "==> Uploading files (board_server.js / draw.js / package.json / start_service.bat)..."
SCP_UPLOAD "$SCRIPT_DIR/board_server.js" "$SCRIPT_DIR/draw.js" "$SCRIPT_DIR/package.json" "$SCRIPT_DIR/start_service.bat"

echo "==> Installing dependencies on the server (npm install - this pulls native bindings matching the server's platform)..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $NPM_INSTALL_ENCODED"

# Use a Windows Scheduled Task instead of "start /min" to launch the service: an
# OpenSSH session runs in a desktop-less window station, so processes started
# with "start" often die when the session ends, or never really start at all -
# this is exactly what causes "deployed but ping doesn't respond" reports. A
# Scheduled Task doesn't depend on any session, and also fixes "image service
# doesn't come back after a server reboot" by registering it to auto-start at boot.
SCHTASK_PS1_TEMPLATE='$ProgressPreference = "SilentlyContinue"
$taskName = "YucaImageService"
$batPath = "__REMOTE_DIR__\start_service.bat"
$workDir = "__REMOTE_DIR__"

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

# Important: do not point -Execute directly at the .bat file - file-association
# resolution for directly executing a .bat from a Scheduled Task is not reliable
# across all Windows versions; in practice this produced tasks that "registered
# successfully" but never actually ran. Calling cmd.exe /c explicitly removes
# that ambiguity.
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

echo "==> Registering + starting the Scheduled Task (also sets it to auto-start on boot)..."
SSH "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $SCHTASK_ENCODED"

echo "==> Waiting 2 seconds then checking service status..."
sleep 2
if SSH "curl -s http://127.0.0.1:8855/ping"; then
  echo ""
  echo "===== Deploy complete, service is running ====="
  notify "Deploy complete! The image service is now running on the server."
else
  echo ""
  echo "⚠️ Files were uploaded, but could not confirm the service started successfully."
  notify "Files were uploaded, but could not confirm the service started successfully. Check the window titled 'yuca image service' on the server, or check $REMOTE_DIR\\service.log."
fi

echo ""
echo "Once you load 语擦助手_合并版.js in SealDice, the 月历图/结局分布图/年度总览图 commands will work."
echo ""
read -p "You can close this window now - press Enter to exit... " _
