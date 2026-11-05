@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-time.ps1"
exit /b %errorlevel%
