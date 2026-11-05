@echo off
REM Registry-driven launcher. Starts only API services whose ports are not bound.

setlocal
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-services.ps1" %*
exit /b %errorlevel%
