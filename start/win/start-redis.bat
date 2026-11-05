@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0component.ps1" -Name redis -Action start %*
exit /b %errorlevel%
