@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0reference-sync.ps1" -Action stop %*
exit /b %errorlevel%
