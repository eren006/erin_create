# Yuca Helper Image Service - GUI one-click deploy (Windows)
# Right-click -> Run with PowerShell; if double-clicking does nothing, right-click
# and choose "Run with PowerShell".
#
# This window collects server address / username / port / password / path, then
# uses PuTTY's plink/pscp (auto-downloaded next to this script if missing) to log
# in and run everything non-interactively - you should NOT have to type the
# password again in the black console window that opens. The one thing that can
# still show up there is a one-time "trust this server's host key?" prompt on the
# very first connection to a given server - that's ssh's own security check and
# can't be skipped from here, just answer it once.
#
# Security note: the password you type below is passed to plink/pscp as a
# command-line argument, which briefly makes it visible to other processes on
# this machine that inspect running process command lines (e.g. Task Manager's
# "Command line" column). It is never written to any file on disk and is cleared
# from this script's memory right after the deploy starts. If that's not
# acceptable for your situation, leave the password field blank and type it
# manually when the console window asks for it instead.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ScriptDir = $PSScriptRoot

$form = New-Object System.Windows.Forms.Form
$form.Text = "Yuca Helper Image Service - One-Click Deploy"
$form.Size = New-Object System.Drawing.Size(480, 460)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

function Add-FieldLabel([string]$text, [int]$y) {
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $text
    $lbl.Location = New-Object System.Drawing.Point(20, $y)
    $lbl.Size = New-Object System.Drawing.Size(430, 32)
    $form.Controls.Add($lbl)
}

function Add-FieldBox([int]$y, [string]$default, [bool]$masked = $false) {
    $tb = New-Object System.Windows.Forms.TextBox
    $tb.Location = New-Object System.Drawing.Point(20, $y)
    $tb.Size = New-Object System.Drawing.Size(420, 24)
    $tb.Text = $default
    if ($masked) { $tb.PasswordChar = '*' }
    $form.Controls.Add($tb)
    return $tb
}

Add-FieldLabel "Server address (IP or domain only, no colon/port, e.g. 123.45.67.89):" 10
$tbHost = Add-FieldBox 42 ""

Add-FieldLabel "SSH username (the account you log in with, usually same as Remote Desktop):" 74
$tbUser = Add-FieldBox 106 ""

Add-FieldLabel "SSH port (leave the default 22 if unsure):" 138
$tbPort = Add-FieldBox 170 "22"

Add-FieldLabel "SSH password (leave blank to type it manually in the console window instead):" 202
$tbPass = Add-FieldBox 234 "" $true

Add-FieldLabel "Target path on the server (no spaces in the path):" 266
$tbPath = Add-FieldBox 298 "C:\yuca_image_server"

$lblNote = New-Object System.Windows.Forms.Label
$lblNote.Text = "First-time connections still show a one-time host key trust prompt in the console window - just answer it. plink.exe/pscp.exe will be auto-downloaded next to this script the first time you deploy."
$lblNote.Location = New-Object System.Drawing.Point(20, 328)
$lblNote.Size = New-Object System.Drawing.Size(430, 44)
$lblNote.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($lblNote)

$btnDeploy = New-Object System.Windows.Forms.Button
$btnDeploy.Text = "Start Deploy"
$btnDeploy.Location = New-Object System.Drawing.Point(20, 378)
$btnDeploy.Size = New-Object System.Drawing.Size(420, 36)
$form.Controls.Add($btnDeploy)

function Ensure-PuttyTools {
    $plinkPath = Join-Path $ScriptDir "plink.exe"
    $pscpPath = Join-Path $ScriptDir "pscp.exe"
    foreach ($pair in @(@{Path = $plinkPath; Url = "https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe"; Name = "plink.exe"},
                        @{Path = $pscpPath; Url = "https://the.earth.li/~sgtatham/putty/latest/w64/pscp.exe"; Name = "pscp.exe"})) {
        if (-not (Test-Path $pair.Path)) {
            try {
                Invoke-WebRequest -Uri $pair.Url -OutFile $pair.Path -UseBasicParsing
            } catch {
                [System.Windows.Forms.MessageBox]::Show(("Failed to download " + $pair.Name + " from the official PuTTY mirror: " + $_.Exception.Message + "`n`nCheck your internet connection, or manually download it from https://www.chiark.greenend.org.uk/~sgtatham/putty/latest.html and place it next to this script."), "Yuca Helper Image Service") | Out-Null
                return $false
            }
        }
    }
    return $true
}

$btnDeploy.Add_Click({
    $ServerHost = $tbHost.Text.Trim()
    $ServerUser = $tbUser.Text.Trim()
    $ServerPort = $tbPort.Text.Trim()
    if ([string]::IsNullOrEmpty($ServerPort)) { $ServerPort = "22" }
    $ServerPass = $tbPass.Text
    $RemoteDir = $tbPath.Text.Trim()
    if ([string]::IsNullOrEmpty($RemoteDir)) { $RemoteDir = "C:\yuca_image_server" }

    if ([string]::IsNullOrEmpty($ServerHost) -or [string]::IsNullOrEmpty($ServerUser)) {
        [System.Windows.Forms.MessageBox]::Show("Server address and username cannot be empty.", "Yuca Helper Image Service") | Out-Null
        return
    }

    # Fallback: if the address was mistakenly entered as "IP:port" (e.g. mixing up
    # a web service port with the SSH port), auto-strip to just the address part
    # so it doesn't get concatenated with the separate SSH port field into an
    # unparseable address.
    if ($ServerHost -match "^(.+):(\d+)$") {
        $DetectedPort = $Matches[2]
        $ServerHost = $Matches[1]
        $NoteText = "Detected a port number in the server address ($DetectedPort); automatically kept only the address part: $ServerHost`n`n"
        if ($DetectedPort -ne $ServerPort) {
            $NoteText += "If $DetectedPort is actually the real SSH port, click `"Cancel`" and re-enter, changing the SSH port field to $DetectedPort.`nIf $DetectedPort is just some other service's port (e.g. a web server), click `"OK`" to keep using $ServerPort."
            $Result = [System.Windows.Forms.MessageBox]::Show($NoteText, "Yuca Helper Image Service", [System.Windows.Forms.MessageBoxButtons]::OKCancel)
            if ($Result -eq [System.Windows.Forms.DialogResult]::Cancel) { return }
        } else {
            [System.Windows.Forms.MessageBox]::Show($NoteText, "Yuca Helper Image Service") | Out-Null
        }
    }

    if ($RemoteDir -match "\s") {
        [System.Windows.Forms.MessageBox]::Show("The server path cannot contain spaces. Try another path, e.g. C:\yuca_image_server", "Yuca Helper Image Service") | Out-Null
        return
    }

    if (-not (Ensure-PuttyTools)) { return }

    # -pw is only added when a password was actually entered; if the field was
    # left blank, plink/pscp fall back to their normal behavior (try cached key
    # auth, else prompt interactively in the console) - same as the old ssh/scp
    # based flow. The password itself is passed through an environment variable
    # rather than being written literally into the generated .bat file, so it
    # never sits on disk as plain text; it's still visible in plink/pscp's own
    # process command line while they run (a plink/pscp limitation, not
    # something this script can avoid - see the note at the top of this file).
    $pwArg = ""
    if (-not [string]::IsNullOrEmpty($ServerPass)) {
        $pwArg = '-pw "%YUCA_SSH_PASS%"'
    }

    $RunnerPath = Join-Path $env:TEMP ("yuca_deploy_runner_" + [guid]::NewGuid().ToString("N") + ".bat")
    $PlinkPath = Join-Path $ScriptDir "plink.exe"
    $PscpPath = Join-Path $ScriptDir "pscp.exe"

    # PowerShell script that auto-installs Node.js on the remote server, passed to
    # plink via -EncodedCommand (base64) to fully sidestep nested-quote escaping
    # issues in cmd.exe / plink arguments. This script only runs on the server and
    # is entirely in English - no Chinese encoding involved anywhere in it.
    $nodeInstallScript = @'
$ProgressPreference = "SilentlyContinue"
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
'@
    $nodeInstallEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($nodeInstallScript))

    # Same idea for the npm install step: run via -EncodedCommand and locate npm
    # ourselves instead of relying on PATH having picked up the just-installed
    # Node.js (PATH doesn't auto-refresh within the same session - normal
    # Windows service-process behavior, not a bug).
    $npmInstallScript = @"
`$ProgressPreference = "SilentlyContinue"
`$npmCmd = `$null
if (Get-Command npm -ErrorAction SilentlyContinue) {
    `$npmCmd = "npm"
} elseif (Test-Path "C:\Program Files\nodejs\npm.cmd") {
    `$npmCmd = "C:\Program Files\nodejs\npm.cmd"
}
if (-not `$npmCmd) {
    Write-Output "npm not found"
    exit 1
}
& `$npmCmd install --prefix "$RemoteDir"
"@
    $npmInstallEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($npmInstallScript))

    # Use a Windows Scheduled Task instead of "start /min" to launch the service:
    # an SSH session runs in a desktop-less window station, so processes started
    # with "start" often die when the session ends, or never really start at all
    # (this was the exact cause of past "deployed but ping fails" reports). A
    # Scheduled Task doesn't depend on any session, and also fixes "image service
    # doesn't come back after a server reboot" by registering it to auto-start
    # at boot.
    $schtaskScript = @"
`$ProgressPreference = "SilentlyContinue"
`$taskName = "YucaImageService"
`$batPath = "$RemoteDir\start_service.bat"
`$workDir = "$RemoteDir"

`$existing = Get-ScheduledTask -TaskName `$taskName -ErrorAction SilentlyContinue
if (`$existing) {
    Stop-ScheduledTask -TaskName `$taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName `$taskName -Confirm:`$false -ErrorAction SilentlyContinue
}

# Important: don't point -Execute directly at the .bat file - file-association
# resolution for directly executing a .bat from a Scheduled Task isn't reliable
# across all Windows versions; in practice this produced tasks that "registered
# successfully" but never actually ran. Calling cmd.exe /c explicitly removes
# that ambiguity.
`$cmdArgs = '/c "' + `$batPath + '"'
`$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument `$cmdArgs -WorkingDirectory `$workDir
`$trigger = New-ScheduledTaskTrigger -AtStartup
`$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
`$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName `$taskName -Action `$action -Trigger `$trigger -Principal `$principal -Settings `$settings -Force | Out-Null
Start-ScheduledTask -TaskName `$taskName

Start-Sleep -Seconds 3
`$task = Get-ScheduledTask -TaskName `$taskName
`$info = Get-ScheduledTaskInfo -TaskName `$taskName
Write-Output ("Task state: " + `$task.State)
Write-Output ("Last run time: " + `$info.LastRunTime)
Write-Output ("Last task result: " + `$info.LastTaskResult + " (0 = ran and exited; a persistent server should NOT show 0 here after a few seconds - if it does, node exited/crashed right away, check service.log)")
"@
    # Create the target directory with New-Item -Force: doesn't error if it
    # already exists, and doesn't print any locale-dependent error noise (a
    # plain "mkdir" on an existing directory used to print a localized
    # "command syntax is incorrect" line depending on system language).
    $mkdirScript = @"
`$ProgressPreference = "SilentlyContinue"
New-Item -ItemType Directory -Force -Path "$RemoteDir" | Out-Null
Write-Output "Target directory ready"
"@
    $mkdirEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($mkdirScript))

    $schtaskEncoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($schtaskScript))

    # The generated runner .bat is a one-off temp file used only for this single
    # deploy run, not something meant to be read/maintained long-term. Its own
    # visible text is deliberately all-English to avoid any chance of Chinese
    # text getting mangled by inconsistent console codepage handling across
    # different systems (this is exactly the bug that used to produce garbled
    # console output). However $ScriptDir/$RemoteDir (the paths plink.exe is
    # invoked from and the deploy target path) can legitimately contain
    # non-ASCII characters - e.g. if the user extracted this tool into a
    # Chinese-named folder like "桌面\新建文件夹" - so the file itself is saved
    # as UTF-8 (no BOM, chcp 65001 set as the very first thing it does) rather
    # than plain ASCII, which would silently corrupt any such path into "?"
    # characters and produce a "cannot find the specified path" failure right
    # at the first plink.exe call. It self-deletes at the end and never
    # contains the password itself (that's passed via an environment variable
    # set by this PowerShell process instead) - see the note at the top of
    # this file about what plink/pscp themselves still expose.
    $batLines = @(
        '@echo off'
        'chcp 65001 >nul'
        'title yuca_image_service deploy'
        'echo ============================================'
        'echo   Connecting, uploading, installing deps, starting service'
        'echo   First-time connections still show a one-time host key trust prompt - just answer it'
        'echo ============================================'
        'echo.'
        'echo ==^> Checking / installing Node.js on the server...'
        "`"$PlinkPath`" -ssh -T -no-antispoof -P $ServerPort $pwArg $ServerUser@$ServerHost `"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $nodeInstallEncoded`""
        'if errorlevel 1 ('
        '  echo.'
        '  echo Node.js check/install failed, or the connection failed.'
        '  echo Check address/port/username/password, and whether OpenSSH Server is running.'
        '  goto :cleanup_fail'
        ')'
        'echo.'
        'echo ==^> Creating target directory on the server...'
        "`"$PlinkPath`" -ssh -T -no-antispoof -P $ServerPort $pwArg $ServerUser@$ServerHost `"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $mkdirEncoded`""
        'echo.'
        'echo ==^> Uploading files: board_server.js draw.js package.json start_service.bat'
        "`"$PscpPath`" -P $ServerPort $pwArg `"$ScriptDir\board_server.js`" `"$ScriptDir\draw.js`" `"$ScriptDir\package.json`" `"$ScriptDir\start_service.bat`" ${ServerUser}@${ServerHost}:`"$RemoteDir/`""
        'if errorlevel 1 ('
        '  echo.'
        '  echo File upload failed, check the error above.'
        '  goto :cleanup_fail'
        ')'
        'echo.'
        'echo ==^> Installing dependencies on the server via npm install...'
        "`"$PlinkPath`" -ssh -T -no-antispoof -P $ServerPort $pwArg $ServerUser@$ServerHost `"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $npmInstallEncoded`""
        'echo.'
        'echo ==^> Registering + starting the service as a Scheduled Task, also auto-starts on reboot...'
        "`"$PlinkPath`" -ssh -T -no-antispoof -P $ServerPort $pwArg $ServerUser@$ServerHost `"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand $schtaskEncoded`""
        'echo.'
        'echo ==^> Waiting 2 seconds then checking service status...'
        'timeout /t 2 /nobreak >nul'
        "`"$PlinkPath`" -ssh -T -no-antispoof -P $ServerPort $pwArg $ServerUser@$ServerHost `"curl -s http://127.0.0.1:8855/ping`""
        'echo.'
        'echo ===== Deploy complete ====='
        'echo Now load the plugin script in SealDice - see README.txt for the last step.'
        'echo.'
        'set "YUCA_SSH_PASS="'
        'pause'
        '(goto) 2>nul & del "%~f0"'
        'exit /b 0'
        ':cleanup_fail'
        'set "YUCA_SSH_PASS="'
        'pause'
        '(goto) 2>nul & del "%~f0"'
        'exit /b 1'
    )
    $batContent = ($batLines -join "`r`n")
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($RunnerPath, $batContent, $Utf8NoBom)

    if (-not [string]::IsNullOrEmpty($ServerPass)) {
        $env:YUCA_SSH_PASS = $ServerPass
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$RunnerPath`""
    $env:YUCA_SSH_PASS = $null
    $ServerPass = $null
    $tbPass.Text = ""
})

[void]$form.ShowDialog()
