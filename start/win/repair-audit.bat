@echo off
REM Refresh local audit contracts after adding producer event types.
setlocal

set "BILL_AUDIT_STEP=synchronize audit registrations"
echo Synchronizing audit registrations...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit-prepare.ps1"
set "BILL_AUDIT_EXIT=%errorlevel%"
if not "%BILL_AUDIT_EXIT%"=="0" goto done

set "BILL_AUDIT_STEP=stop the Audit consumer"
echo Restarting the Audit consumer...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit-workers.ps1" -Action stop -Worker audit-consumer
set "BILL_AUDIT_EXIT=%errorlevel%"
if not "%BILL_AUDIT_EXIT%"=="0" goto done

set "BILL_AUDIT_STEP=start the Audit consumer"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0audit-workers.ps1" -Action start -Worker audit-consumer
set "BILL_AUDIT_EXIT=%errorlevel%"
if not "%BILL_AUDIT_EXIT%"=="0" goto done

set "BILL_AUDIT_STEP=verify backend and audit delivery health"
call "%~dp0status.bat"
set "BILL_AUDIT_EXIT=%errorlevel%"

:done
echo.
if "%BILL_AUDIT_EXIT%"=="0" (
  echo Audit repair completed; backend health checks passed.
) else (
  echo Audit repair failed during: %BILL_AUDIT_STEP%. Review the errors above.
)
if "%BILL_NO_PAUSE%"=="1" exit /b %BILL_AUDIT_EXIT%
echo Press any key to close this window.
pause >nul
exit /b %BILL_AUDIT_EXIT%
