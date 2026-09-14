@echo off

rem Scheduled Task / no-desktop context has no console to show output,
rem so failures would otherwise be undiagnosable. When running non-interactively
rem (no SESSIONNAME, e.g. a Scheduled Task running as SYSTEM), relaunch self
rem once with all output redirected into service.log for later inspection.
rem Interactive use (double-click, has SESSIONNAME) is unaffected.
if not defined SESSIONNAME (
  if not defined YUCA_LOGGED (
    set "YUCA_LOGGED=1"
    call "%~f0" >> "%~dp0service.log" 2>&1
    exit /b
  )
)

title yuca image service
cd /d "%~dp0"
echo.
echo ---- %date% %time% ----
echo ============================================
echo   yuca image service - launcher
echo   Ctrl+C or close this window to stop
echo ============================================
echo.
echo Checking port 8855 for a previous instance...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8855 ^| findstr LISTENING') do (
  echo Found old process PID %%a on port 8855, killing it so the latest code runs...
  taskkill /F /PID %%a >nul 2>&1
)
echo.

rem Prefer node on PATH; if this session's PATH has not picked up a Node.js
rem that was just auto-installed earlier in the same deploy run (a normal
rem Windows behavior, not a bug), fall back to the default install path.
set "NODE_EXE=node"
where node >nul 2>&1
if errorlevel 1 (
  if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_EXE=C:\Program Files\nodejs\node.exe"
  ) else (
    echo [ERROR] node not found. Run node -v to confirm Node.js is installed.
    if defined SESSIONNAME (pause)
    exit /b 1
  )
)

"%NODE_EXE%" board_server.js
if errorlevel 1 (
  echo.
  echo [ERROR] Startup failed, check:
  echo  1. Node.js is installed - run node -v
  echo  2. npm install has been run in this folder
  echo.
  if defined SESSIONNAME (pause)
)
