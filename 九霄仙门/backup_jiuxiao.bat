@echo off
setlocal enabledelayedexpansion
set "APP_DIR=C:\Users\Administrator\jiuxiao_xianmen"
set "BACKUP_DIR=%APP_DIR%\backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set "YYYY=%DATE:~0,4%"
set "MM=%DATE:~5,2%"
set "DD=%DATE:~8,2%"
set "HH=%TIME:~0,2%"
set "HH=%HH: =0%"
set "MIN=%TIME:~3,2%"
set "SS=%TIME:~6,2%"
set "STAMP=%YYYY%%MM%%DD%_%HH%%MIN%%SS%"

copy /y "%APP_DIR%\jiuxiao.db" "%BACKUP_DIR%\jiuxiao_daily_%STAMP%.db" >nul

forfiles /p "%BACKUP_DIR%" /m jiuxiao_daily_*.db /d -14 /c "cmd /c del @path" 2>nul

endlocal
