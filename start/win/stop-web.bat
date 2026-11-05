@echo off
rem Stop only UI processes managed by this workspace.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-web.ps1" %*
set "BILL_STOP_EXIT=%errorlevel%"
if not "%BILL_STOP_EXIT%"=="0" (
  echo.
  echo UI shutdown incomplete. Review the errors above and logs in "%~dp0logs".
)
if "%BILL_NO_PAUSE%"=="1" exit /b %BILL_STOP_EXIT%
echo.
echo Press any key to close this window.
pause >nul
exit /b %BILL_STOP_EXIT%
