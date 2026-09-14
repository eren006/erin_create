@echo off
chcp 65001 >nul
rem Just double-click this file - it only launches the PowerShell GUI form
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_windows.ps1"
