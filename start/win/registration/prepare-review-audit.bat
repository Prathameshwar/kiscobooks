@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-review-audit.ps1" %*
exit /b %errorlevel%
