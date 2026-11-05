@echo off
rem Compatibility alias: start-web.cmd [all ^| auth ^| console]
setlocal
call "%~dp0start-web.bat" %*
exit /b %errorlevel%
