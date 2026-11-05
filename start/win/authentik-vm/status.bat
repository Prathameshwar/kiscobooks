@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\authentik-vm.ps1" -Action status
exit /b %errorlevel%
