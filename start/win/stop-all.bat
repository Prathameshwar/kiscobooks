@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1" %*
set "BILL_STOP_EXIT=%errorlevel%"
if not "%BILL_STOP_EXIT%"=="0" (
  echo.
  echo Shutdown incomplete. Review the component errors above.
)
if "%BILL_NO_PAUSE%"=="1" exit /b %BILL_STOP_EXIT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %BILL_STOP_EXIT%
