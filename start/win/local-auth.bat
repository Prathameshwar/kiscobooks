@echo off
rem Prepare local sign-in (docs/local-auth.md). Safe to run again; existing secrets are kept.
rem Restart Identity and the Auth app afterwards: stop-all.bat / start-all.bat, stop-web.bat / start-web.bat.
set "ROOT=%~dp0..\.."
"%ROOT%\apis\identity\.venv\Scripts\python.exe" "%~dp0configure-local-auth.py" --env-dir "%~dp0env" --auth-env "%ROOT%\mfes\apps\auth\.env.local"
exit /b %errorlevel%
