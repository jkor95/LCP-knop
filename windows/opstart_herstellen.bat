@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"
set "SCRIPT=%ROOT%\lcp_receiver.py"
if not exist "%PY%" goto missingpython
if not exist "%SCRIPT%" goto missingscript
echo Snelkoppeling opnieuw instellen...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=$env:ROOT; $w=Join-Path $root '.venv\Scripts\pythonw.exe'; $s=Join-Path $root 'lcp_receiver.py'; $startup=[Environment]::GetFolderPath('Startup'); $sh=New-Object -ComObject WScript.Shell; $lnk=$sh.CreateShortcut((Join-Path $startup 'LCP Knop.lnk')); $lnk.TargetPath=$w; $lnk.Arguments='"'+$s+'"'; $lnk.WorkingDirectory=$root; $lnk.Description='LCP Knop Windows ontvanger'; $lnk.Save(); Write-Host ('Doel: '+$w); Write-Host ('Script: '+$s)"
if errorlevel 1 goto repairfailed
echo.
echo Snelkoppeling hersteld.
echo Test: programma starten met zichtbaar foutvenster...
"%PY%" "%SCRIPT%"
echo.
echo Programma gestopt.
pause
exit /b 0
:missingpython
echo FOUT: Python-omgeving ontbreekt.
echo Controleer of dit de oorspronkelijke installatiemap is.
pause
exit /b 1
:missingscript
echo FOUT: lcp_receiver.py ontbreekt.
pause
exit /b 1
:repairfailed
echo FOUT: Snelkoppeling aanmaken mislukt.
pause
exit /b 1
