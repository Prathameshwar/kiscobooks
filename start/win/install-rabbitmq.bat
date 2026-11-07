@echo off
REM Download and install the pinned portable RabbitMQ and Erlang archives.

setlocal
set SCRIPT_DIR=%~dp0

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-rabbitmq.ps1" %*
set "INSTALL_EXIT=%errorlevel%"
if not "%INSTALL_EXIT%"=="0" (
  echo.
  echo RabbitMQ installation failed. Review the error above.
)
exit /b %INSTALL_EXIT%
