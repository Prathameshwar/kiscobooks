@echo off
REM Read-only health check for every Bill component.
REM Exit 0 = all UP, 1 = at least one DOWN.

setlocal
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%status.ps1" %*
exit /b %errorlevel%
