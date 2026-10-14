@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%\lcp_receiver.py"
if exist "%PY%" goto found
echo Python-omgeving niet in deze map. Zoeken in Downloads...
for /d %%D in ("%USERPROFILE%\Downloads\LCP-knop-main*") do (
  if exist "%%~fD\windows\.venv\Scripts\python.exe" (
    set "ROOT=%%~fD\windows"
    set "PY=%%~fD\windows\.venv\Scripts\python.exe"
    set "SCRIPT=%%~fD\windows\lcp_receiver.py"
    goto found
  )
  for /d %%E in ("%%~fD\LCP-knop-main*") do (
    if exist "%%~fE\windows\.venv\Scripts\python.exe" (
      set "ROOT=%%~fE\windows"
      set "PY=%%~fE\windows\.venv\Scripts\python.exe"
      set "SCRIPT=%%~fE\windows\lcp_receiver.py"
      goto found
    )
  )
)
echo.
echo Geen bestaande LCP Python-omgeving gevonden.
echo Gebruik de windows-map waarin installeren.bat eerder werkte.
echo Of voer installeren.bat opnieuw uit in een vaste map, bijvoorbeeld C:\LCPKnop\windows.
pause
exit /b 1
:found
echo Installatiemap: %ROOT%
if not exist "%SCRIPT%" goto missingscript
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=$env:ROOT;$w=Join-Path $root '.venv\Scripts\pythonw.exe';$s=Join-Path $root 'lcp_receiver.py';$startup=[Environment]::GetFolderPath('Startup');$sh=New-Object -ComObject WScript.Shell;$lnk=$sh.CreateShortcut((Join-Path $startup 'LCP Knop.lnk'));$lnk.TargetPath=$w;$lnk.Arguments='"'+$s+'"';$lnk.WorkingDirectory=$root;$lnk.Save();Write-Host 'Opstartsnelkoppeling hersteld.'"
if errorlevel 1 goto failed
echo.
echo Starten van LCP Knop ter controle...
"%PY%" "%SCRIPT%"
pause
exit /b 0
:missingscript
echo LCP-script ontbreekt in gevonden map.
pause
exit /b 1
:failed
echo Opstartsnelkoppeling kon niet worden gemaakt.
pause
exit /b 1
