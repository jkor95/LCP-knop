@echo off
setlocal EnableExtensions
title LCP sensoruitbreiding installeren
set "ROOT=C:\LCP"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "TASK=LCP - Achtergrondworker"
set "TARGET=%ROOT%\lcp_worker.py"
set "NEW=%ROOT%\lcp_worker_nieuw.py"
set "BACKUP=%ROOT%\lcp_worker_voor_sensoren.py"
set "URL=https://raw.githubusercontent.com/jkor95/LCP-knop/main/windows/lcp_worker_zigbee_v2.py"

echo.
echo  LCP - Veilige installatie van sensoruitbreiding
echo  -------------------------------------------------
echo  De originele LCP-knop wordt eerst veiliggesteld.
echo.
if not exist "%PY%" goto missing
if not exist "%TARGET%" goto missing
echo [1/5] Nieuwe worker downloaden...
curl.exe --fail --location --silent --show-error --retry 2 --output "%NEW%" "%URL%"
if errorlevel 1 goto downloaderror
for %%F in ("%NEW%") do if %%~zF LSS 3000 goto downloaderror
echo [2/5] Python-code controleren...
"%PY%" -m py_compile "%NEW%"
if errorlevel 1 goto invalid
if not exist "%BACKUP%" (
    echo [3/5] Back-up van bestaande worker maken...
    copy /Y "%TARGET%" "%BACKUP%" >nul
    if errorlevel 1 goto backupfailed
) else (
    echo [3/5] Bestaande back-up behouden: "%BACKUP%"
)
echo [4/5] Alleen LCP-achtergrondworker herstarten...
schtasks /end /tn "%TASK%" >nul 2>&1
timeout /t 3 /nobreak >nul
copy /Y "%NEW%" "%TARGET%" >nul
if errorlevel 1 goto restore
schtasks /run /tn "%TASK%"
if errorlevel 1 goto restore
echo [5/5] Klaar!
echo.
echo De taak is gestart. Test nu de SONOFF-knop en je iPhone-melding.
echo Andere LCP-, Supabase- en Zigbee-instellingen zijn niet gewijzigd.
echo Belangrijk: de deursensor blijft UIT totdat je hem in de webapp activeert.
echo.
pause
exit /b 0

:restore
echo LET OP: installatie niet voltooid. Probeer de back-up terug te zetten.
copy /Y "%BACKUP%" "%TARGET%" >nul
schtasks /run /tn "%TASK%" >nul 2>&1
echo Controleer Taakplanner en test de fysieke knop.
pause
exit /b 1

:missing
echo FOUT: de bestaande LCP-installatie in C:\LCP is niet aangetroffen.
echo Er is niets aangepast.
pause
exit /b 1

:downloaderror
echo FOUT: de download is niet gelukt. De bestaande worker is niet gewijzigd.
pause
exit /b 1

:invalid
echo FOUT: Python-code is niet geldig. De bestaande worker is niet gewijzigd.
pause
exit /b 1

:backupfailed
echo FOUT: back-up maken is niet gelukt. De bestaande worker is niet gewijzigd.
pause
exit /b 1
