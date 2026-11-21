@echo off
cd /d "%~dp0"
where npm.cmd >nul 2>&1
if errorlevel 1 (
  py -3 server.py
) else (
  call npm.cmd start
)
pause
