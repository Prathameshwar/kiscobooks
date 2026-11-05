@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply-authentik.ps1"
exit /b %errorlevel%
