@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0authentik-vm.ps1" -Action create
exit /b %errorlevel%
