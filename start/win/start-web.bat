@echo off
rem Start both UI apps, or select auth / console. Wait for a key after readiness checks.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-web.ps1" %*
set "BILL_START_EXIT=%errorlevel%"
if not "%BILL_START_EXIT%"=="0" (
  echo.
  echo UI startup failed. Review the errors above and logs in "%~dp0logs".
)
if "%BILL_NO_PAUSE%"=="1" exit /b %BILL_START_EXIT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %BILL_START_EXIT%
