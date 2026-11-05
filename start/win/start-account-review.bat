@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0account-review.ps1" -Action start
exit /b %errorlevel%
