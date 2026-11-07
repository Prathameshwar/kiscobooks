@echo off
REM Create configured service databases and apply their Alembic migrations.

setlocal
set SCRIPT_DIR=%~dp0

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%provision-databases.ps1" %*
set "PROVISION_EXIT=%errorlevel%"
if not "%PROVISION_EXIT%"=="0" (
  echo.
  echo Database provisioning failed. Review the error above.
)
if "%BILL_NO_PAUSE%"=="1" exit /b %PROVISION_EXIT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %PROVISION_EXIT%
