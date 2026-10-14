@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
 echo Python ontbreekt. Installeer Python 3.11 of nieuwer van python.org.
 pause
 exit /b 1
)
py -m pip install -r requirements-receiver.txt
if errorlevel 1 (pause & exit /b 1)
py lcp_receiver.py --setup
if errorlevel 1 (pause & exit /b 1)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=(py -c 'import sys;print(sys.executable)' | Select-Object -First 1);$w=Join-Path (Split-Path $p) 'pythonw.exe';$s=(Resolve-Path './lcp_receiver.py').Path;$startup=[Environment]::GetFolderPath('Startup');$shell=New-Object -ComObject WScript.Shell;$lnk=$shell.CreateShortcut((Join-Path $startup 'LCP Knop.lnk'));$lnk.TargetPath=$w;$lnk.Arguments='"'+$s+'"';$lnk.WorkingDirectory=(Get-Location).Path;$lnk.Save()"
if errorlevel 1 (echo Automatisch starten instellen mislukt. & pause & exit /b 1)
echo Gereed. LCP Knop start voortaan na aanmelden bij Windows.
start "" /b pyw "%~dp0lcp_receiver.py"
pause
