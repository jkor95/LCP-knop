@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
set "SCRIPT=%ROOT%\lcp_receiver.py"
if not exist "%PY%" (
 echo FOUT: Python-omgeving ontbreekt in %ROOT%
 echo Gebruik de originele uitgepakte windows-map en voer installeren.bat opnieuw uit.
 pause
 exit /b 1
)
if not exist "%SCRIPT%" (
 echo FOUT: lcp_receiver.py ontbreekt.
 pause
 exit /b 1
)
echo Snelkoppeling opnieuw instellen...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=$env:ROOT;$w=Join-Path $root '.venv\Scripts\pythonw.exe';$s=Join-Path $root 'lcp_receiver.py';$startup=[Environment]::GetFolderPath('Startup');$sh=New-Object -ComObject WScript.Shell;$lnk=$sh.CreateShortcut((Join-Path $startup 'LCP Knop.lnk'));$lnk.TargetPath=$w;$lnk.Arguments='"'+$s+'"';$lnk.WorkingDirectory=$root;$lnk.Description='LCP Knop Windows ontvanger';$lnk.Save();Write-Host ('Doel: '+$w);Write-Host ('Script: '+$s)"
if errorlevel 1 (echo Snelkoppeling aanmaken mislukt. & pause & exit /b 1)
echo.
echo Test: programma starten met zichtbaar foutvenster...
"%PY%" "%SCRIPT%"
echo.
echo Programma gestopt. Als hierboven een fout staat, maak een foto van deze fout.
pause
