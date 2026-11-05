@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-account-review.ps1"
exit /b %errorlevel%
