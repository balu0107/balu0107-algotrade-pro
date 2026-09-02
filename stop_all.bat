@echo off
setlocal
cd /d "%~dp0"

echo Stopping AlgoTradePro (backend + frontend)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_all.ps1"

REM start_all.bat's own console windows are titled exactly this - closing
REM them here too, on top of the actual server processes above, so no dead
REM "Terminate batch job (Y/N)?" windows are left behind.
taskkill /FI "WINDOWTITLE eq Backend (port 9999)*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Frontend (port 3000)*" /F >nul 2>&1

echo.
echo Done.
pause
endlocal
