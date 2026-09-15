# Checks whether OpenSSH Server (sshd) is installed, running, set to auto-start,
# and allowed through the Windows Firewall on port 22 - and fixes anything that
# isn't. Safe to run multiple times (every step is idempotent).
#
# This only handles the OS side (this server). It does NOT touch your cloud
# provider's own firewall/security group - that's a separate, second layer you
# still need to open yourself in your cloud console. See README.txt, section
# "开始之前：确保服务器的 22 端口是打开的" for both layers.

Write-Output "===== Checking OpenSSH Server (sshd) ====="
$svc = Get-Service sshd -ErrorAction SilentlyContinue
if (-not $svc) {
    Write-Output "sshd service not found - installing OpenSSH Server..."
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
} else {
    Write-Output "sshd is already installed."
}

Write-Output ""
Write-Output "===== Making sure sshd is running and set to auto-start ====="
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd -ErrorAction SilentlyContinue

Write-Output ""
Write-Output "===== Adding a firewall rule for TCP 22 (safe to run even if one already exists) ====="
New-NetFirewallRule -DisplayName "OpenSSH Server (sshd)" -Direction Inbound -Protocol TCP -LocalPort 22 -Action Allow -ErrorAction SilentlyContinue | Out-Null

Write-Output ""
Write-Output "===== Verify ====="
Get-Service sshd | Format-List Name, Status, StartType
Write-Output "Listening on port 22:"
netstat -ano | findstr ":22"
Write-Output ""
Write-Output "Firewall rules matching OpenSSH:"
Get-NetFirewallRule -DisplayName "*OpenSSH*" | Format-Table DisplayName, Enabled, Direction, Action

Write-Output ""
Write-Output "If Status above is Running, StartType is Automatic, port 22 shows LISTENING, and"
Write-Output "at least one firewall rule shows Enabled=True / Action=Allow, this server's own OS"
Write-Output "side is ready. If you still can't connect from outside, the remaining thing to"
Write-Output "check is your cloud provider's own firewall / security group for this instance -"
Write-Output "that's a separate setting in your cloud console, not something this script can see."
