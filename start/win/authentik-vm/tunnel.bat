@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tunnel.ps1" -Action start
exit /b %errorlevel%
