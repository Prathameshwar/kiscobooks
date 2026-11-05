@echo off
rem Operator commands for the local sign-in provider; see local-auth-cli.ps1.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-auth-cli.ps1" %*
exit /b %errorlevel%
