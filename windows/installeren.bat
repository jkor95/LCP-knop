@echo off
setlocal
cd /d "%~dp0"
set "PY="
py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
if not defined PY py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY (
 echo Python 3.11, 3.12 of 3.13 is nodig.
 echo Installeer Python 3.13 via https://www.python.org/downloads/
 echo Start daarna installeren.bat opnieuw.
 pause
 exit /b 1
)
echo Python-versie controleren...
%PY% -m venv "%~dp0.venv"
if errorlevel 1 (echo Aanmaken virtuele omgeving mislukt. & pause & exit /b 1)
set "VENV=%~dp0.venv"
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements-receiver.txt
if errorlevel 1 (echo Installatie van onderdelen mislukt. & pause & exit /b 1)
"%VENV%\Scripts\python.exe" lcp_receiver.py --setup
if errorlevel 1 (echo Inloggen mislukt. & pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=(Resolve-Path '.\.venv\Scripts\pythonw.exe').Path;$s=(Resolve-Path '.\lcp_receiver.py').Path;$startup=[Environment]::GetFolderPath('Startup');$shell=New-Object -ComObject WScript.Shell;$lnk=$shell.CreateShortcut((Join-Path $startup 'LCP Knop.lnk'));$lnk.TargetPath=$w;$lnk.Arguments='"'+$s+'"';$lnk.WorkingDirectory=(Get-Location).Path;$lnk.Save()"
if errorlevel 1 (echo Automatisch starten instellen mislukt. & pause & exit /b 1)
echo Gereed. LCP Knop start voortaan na aanmelden bij Windows.
start "" "%VENV%\Scripts\pythonw.exe" "%~dp0lcp_receiver.py"
pause
