@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\authentik-vm.ps1" -Action stop
exit /b %errorlevel%
