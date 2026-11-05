@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare-password-recovery.ps1"
exit /b %errorlevel%
