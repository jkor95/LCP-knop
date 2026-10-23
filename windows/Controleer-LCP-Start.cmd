@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Controleer-LCP-Start.ps1" -VraagMap
echo.
pause
