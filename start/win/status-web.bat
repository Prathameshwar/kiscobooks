@echo off
rem Report ownership and HTTP readiness of both UI apps.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0status-web.ps1" %*
exit /b %errorlevel%
