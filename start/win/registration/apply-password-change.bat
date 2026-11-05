@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply-authentik.ps1" -Blueprint authentik-password-change.yaml
exit /b %errorlevel%
