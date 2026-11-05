@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare.ps1" %*
exit /b %ERRORLEVEL%
