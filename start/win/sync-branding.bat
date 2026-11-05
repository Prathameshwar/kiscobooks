@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-branding.ps1" %*
exit /b %errorlevel%
