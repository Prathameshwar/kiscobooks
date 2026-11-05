@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0component.ps1" -Name nginx -Action stop %*
exit /b %errorlevel%
