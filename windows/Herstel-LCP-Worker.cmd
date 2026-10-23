@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-LCP-Deursensoren.ps1" -RestoreLatest
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
