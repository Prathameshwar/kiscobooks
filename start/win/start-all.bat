@echo off
REM Check + launch Authentik SSH tunnel, Redis, RabbitMQ, nginx and API services.
REM MySQL must already be running. Idempotent -- safe to run any time.

setlocal
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-all.ps1" %*
set "BILL_START_EXIT=%errorlevel%"
if not "%BILL_START_EXIT%"=="0" (
  echo.
  echo Startup failed. Review the errors above and logs in "%SCRIPT_DIR%logs".
)
if "%BILL_NO_PAUSE%"=="1" exit /b %BILL_START_EXIT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %BILL_START_EXIT%
