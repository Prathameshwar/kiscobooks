@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0reference-sync.ps1" -Action start %*
exit /b %errorlevel%
