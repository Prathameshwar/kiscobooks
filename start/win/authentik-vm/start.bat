@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\authentik-vm.ps1" -Action start
exit /b %errorlevel%
