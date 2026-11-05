@echo off
REM Thin wrapper around setup.ps1 so you can double-click or run from cmd.
REM All arguments are passed through verbatim.
REM
REM Examples:
REM   setup.bat
REM   setup.bat -Component python
REM   setup.bat -Component envs -Recreate

setlocal
set SCRIPT_DIR=%~dp0

where powershell >nul 2>&1
if not errorlevel 1 (
  set PS_EXE=powershell
) else (
  where pwsh >nul 2>&1
  if not errorlevel 1 (
    set PS_EXE=pwsh
  ) else (
    echo ERROR: neither powershell.exe nor pwsh.exe found on PATH.
    echo Install PowerShell 5.1+ ^(built into Windows 10/11^) or PowerShell 7.
    exit /b 1
  )
)

%PS_EXE% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup.ps1" %*
set RC=%errorlevel%

if %RC%==0 (
  echo.
  echo Setup finished. Next: .\start\win\start-all.bat
) else (
  echo.
  echo Setup exited with code %RC%. Check start\win\logs\ for details.
)
exit /b %RC%
