$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot
$file=Join-Path $repo 'windows\Update-LCP-Deursensoren.ps1'
$tokens=$null;$errors=$null
[System.Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors) | Out-Null
if ($errors.Count) { throw ('PowerShell-syntaxfout: '+$errors[0].Message) }
. $file
function Assert-True($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$root=Join-Path $env:TEMP ('LCP update test '+[guid]::NewGuid().ToString('N'))
$package=Join-Path $root 'bundle'
$install=Join-Path $root 'Werklaptop met spaties'
New-Item -ItemType Directory -Path $package,$install | Out-Null
$PackageDir=$package
$script:TestInstall=$install
$script:Starts=0;$script:Stops=0;$script:SimulateFailure=$false;$script:RefuseStop=$false
$python=(Get-Command python.exe).Source
$worker=Join-Path $install 'lcp_worker.py'
$original=@'
import paho.mqtt.client as mqtt
import os
MQTT_HOST='127.0.0.1'
MQTT_PORT=1883
TOPIC_PREFIX='zigbee2mqtt/'
a=os.environ['LCP_EMAIL']
b=os.environ['LCP_PASSWORD']
c=os.environ['LCP_PUBLISHABLE_KEY']
'@
[IO.File]::WriteAllText($worker,$original)
[IO.File]::WriteAllText((Join-Path $install 'start_lcp.py'),"# Bestaande DPAPI-starter voor lcp_worker.py")
$runtime=Join-Path $install 'lcp_sensor_runtime.json'
[IO.File]::WriteAllText($runtime,'{"bestaand":"bewaren"}')
$zigbee=Join-Path $install 'zigbee2mqtt\data'
New-Item -ItemType Directory -Path $zigbee -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $zigbee 'database.db'),'bestaande zigbee database')
[IO.File]::WriteAllText((Join-Path $zigbee 'configuration.yaml'),"serial: COM3")
$dbHash=(Get-FileHash (Join-Path $zigbee 'database.db')).Hash
$configHash=(Get-FileHash (Join-Path $zigbee 'configuration.yaml')).Hash
foreach($name in @('lcp_worker_zigbee_v2.py','check_lcp_installation.py')) { Copy-Item (Join-Path $repo "windows\$name") (Join-Path $package $name) }
$hashes=@{}
foreach($name in @('lcp_worker_zigbee_v2.py','check_lcp_installation.py')) { $hashes[$name]=(Get-FileHash (Join-Path $package $name)).Hash }
@{version='3.1.0';files=$hashes} | ConvertTo-Json | Set-Content (Join-Path $package 'manifest.json')
$script:FakeTask=[pscustomobject]@{TaskName='LCP bestaande worker';TaskPath='\';Settings=[pscustomobject]@{Enabled=$true};Actions=@([pscustomobject]@{Execute=$python;Arguments=('"'+(Join-Path $install 'start_lcp.py')+'"');WorkingDirectory=$install})}
$script:UnrelatedTasks=@(
 [pscustomobject]@{TaskName='COM-systeemtaak';Actions=@([pscustomobject]@{Execute=$null;Arguments=$null;WorkingDirectory=$null})},
 [pscustomobject]@{TaskName='Lege opdracht';Actions=@([pscustomobject]@{Execute='';Arguments='';WorkingDirectory=''})},
 [pscustomobject]@{TaskName='Taakvariabele';Actions=@([pscustomobject]@{Execute='$(Arg0)';Arguments='';WorkingDirectory='$(Arg1)'})},
 [pscustomobject]@{TaskName='Ander ongeldig pad';Actions=@([pscustomobject]@{Execute='C:\ongeldig"pad\tool.exe';Arguments='';WorkingDirectory=''})},
 [pscustomobject]@{TaskName='Onbekende omgevingsvariabele';Actions=@([pscustomobject]@{Execute='%LCP_ONBEKENDE_TAAKVARIABELE%\tool.exe';Arguments='';WorkingDirectory=''})},
 [pscustomobject]@{TaskName='Opdracht zonder volledig pad';Actions=@([pscustomobject]@{Execute='cmd.exe';Arguments='/c echo voorbeeld';WorkingDirectory=''})},
 [pscustomobject]@{TaskName='Ongekoppelde schijf';Actions=@([pscustomobject]@{Execute='cmd.exe';Arguments='/c echo voorbeeld';WorkingDirectory='Z:\niet-bestaande-map'})},
 [pscustomobject]@{TaskName='Lege actie';Actions=@($null)}
)
function Get-ScheduledTask { return @($script:UnrelatedTasks) + @($script:FakeTask) }
function Disable-ScheduledTask { param($TaskName,$TaskPath);$script:FakeTask.Settings.Enabled=$false }
function Enable-ScheduledTask { param($TaskName,$TaskPath);$script:FakeTask.Settings.Enabled=$true }
function Stop-ScheduledTask { param($TaskName,$TaskPath);$script:Stops++;if($script:RefuseStop){$script:RefuseStop=$false;throw 'Gesimuleerde taakweigering'} }
function Export-ScheduledTask { param($TaskName,$TaskPath);return '<Task>ongewijzigde starttaak</Task>' }
function Get-CimInstance { param($ClassName,$Filter);return @() }
function Start-ScheduledTask {
 param($TaskName,$TaskPath)
 $script:Starts++
 @{version='3.1.0';heartbeat=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);started_at=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);last_config_sync=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);mqtt_connected=$true;devices=@('LCP_knop','LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve')} | ConvertTo-Json | Set-Content (Join-Path $script:TestInstall 'sensor_worker_health.json')
}
$script:RealWait=(Get-Item Function:\Wait-LcpHealth).ScriptBlock
function Wait-LcpHealth($Plan,$Started) {
 if ($script:SimulateFailure) { throw 'Gesimuleerde startfout' }
 & $script:RealWait $Plan $Started
}
# GetFullPath mag nooit de volledige taakdetectie onderbreken voor andere taken.
foreach($invalid in @('', ' ', 'C:\ongeldig"pad\tool.exe', '$(Arg0)', '%LCP_ONBEKENDE_TAAKVARIABELE%\tool.exe', ('C:\nul'+[char]0+'\file.py'), 'https://voorbeeld.invalid/script.py', 'C:script.py')) {
 Assert-True (-not (Test-LcpInside $invalid $install)) 'Ongeldig of onopgelost taakpad moet worden overgeslagen'
}
Assert-True (Test-LcpInside ('"'+$worker+'"') ('"'+$install+'"')) 'Paden met aanhalingstekens en spaties moeten worden herkend'
Assert-True (-not (Test-LcpInside ($install+'-ander\worker.py') $install)) 'Een map met dezelfde naam als prefix is geen onderdeel van de installatie'
$quotedAction=[pscustomobject]@{Execute=('"'+$python+'"');Arguments=('"'+(Join-Path $install 'start_lcp.py')+'"');WorkingDirectory=('"'+$install+'"')}
Assert-True (Test-LcpAction $quotedAction $worker $install) 'Geldige starter met aanhalingstekens moet herkend worden'
$script:FakeTask.Actions=@($quotedAction)
try {
 Invoke-LcpUpdate -Root $install
 Assert-True ((Get-FileHash $worker).Hash -eq $hashes['lcp_worker_zigbee_v2.py']) 'Nieuwe worker is niet geplaatst'
 Assert-True ($script:Starts -eq 1 -and $script:Stops -eq 1) 'Alleen de bestaande taak mag herstart worden'
 Assert-True ((Get-FileHash (Join-Path $zigbee 'database.db')).Hash -eq $dbHash) 'Zigbee-database gewijzigd'
 Assert-True ((Get-FileHash (Join-Path $zigbee 'configuration.yaml')).Hash -eq $configHash) 'COM3-configuratie gewijzigd'
 Invoke-LcpUpdate -Root $install -Restore
 Assert-True ([IO.File]::ReadAllText($worker) -eq $original) 'Handmatig herstel heeft de oude worker niet hersteld'
 Assert-True ([IO.File]::ReadAllText($runtime) -eq '{"bestaand":"bewaren"}') 'Runtime niet hersteld'
 $script:SimulateFailure=$true
 $failed=$false
 try { Invoke-LcpUpdate -Root $install } catch { $failed=$true }
 Assert-True $failed 'Een mislukte start moet de update laten mislukken'
 Assert-True ([IO.File]::ReadAllText($worker) -eq $original) 'Automatisch herstel na startfout werkt niet'
 Assert-True ([IO.File]::ReadAllText($runtime) -eq '{"bestaand":"bewaren"}') 'Automatisch herstel heeft runtime veranderd'
 Assert-True $script:FakeTask.Settings.Enabled 'Bestaande taak is uitgeschakeld achtergelaten'
 $script:SimulateFailure=$false
 $script:RefuseStop=$true
 $denied=$false
 try { Invoke-LcpUpdate -Root $install } catch { $denied=$true }
 Assert-True ($denied -and $script:FakeTask.Settings.Enabled) 'Taakweigering mag de bestaande taak niet uitgeschakeld achterlaten'
 Assert-True ([IO.File]::ReadAllText($worker) -eq $original) 'Taakweigering mag geen worker vervangen'
 Assert-True ((Get-FileHash (Join-Path $zigbee 'database.db')).Hash -eq $dbHash) 'Herstel heeft Zigbee-database gewijzigd'
 $before=$script:Stops
 $empty=Join-Path $root 'Onbekend'
 New-Item -ItemType Directory -Path $empty | Out-Null
 $refused=$false
 try { Invoke-LcpUpdate -Root $empty } catch { $refused=$true }
 Assert-True ($refused -and $script:Stops -eq $before) 'Onbekende installatie moet stoppen voordat taken worden gewijzigd'
 # De aangetroffen Werklaptop gebruikt account.py en een Opstarten-snelkoppeling.
 $startup=Join-Path $root 'Opstarten installatie'
 New-Item -ItemType Directory -Path (Join-Path $startup 'support'),(Join-Path $startup 'private') -Force | Out-Null
 & $python -m venv --system-site-packages (Join-Path $startup '.venv')
 if ($LASTEXITCODE -ne 0) { throw 'Testvenv kon niet worden gemaakt' }
 $startupWorker=Join-Path $startup 'support\upstream_worker.py'
 [IO.File]::WriteAllText($startupWorker,$original)
 $account=Join-Path $startup 'support\account.py'
 [IO.File]::WriteAllText($account,@'
import os, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
def worker():
    account=read_account()
    os.environ.update(LCP_EMAIL=account['email'],LCP_PASSWORD=account['password'],LCP_PUBLISHABLE_KEY=KEY)
    spec=importlib.util.spec_from_file_location('lcp',ROOT / 'support' / 'upstream_worker.py')
    impl=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(impl)
    class LocalWorker(impl.LCPWorker):
        def login(self):
            super().login()
    w=LocalWorker()
    w.client.username_pw_set('lcp',local['password'])
    w.run()
'@)
 $accountHash=(Get-FileHash $account).Hash
 $oldState=Join-Path $startup 'private\old-state.json'
 [IO.File]::WriteAllText($oldState,'{"bestaand":"bewaren"}')
 $vbs=Join-Path $startup 'LCP-background.vbs'
 [IO.File]::WriteAllText($vbs,'bestaande ouder start Zigbee en account.py; niet wijzigen')
 $shortcut=Join-Path $startup 'LCP Werklaptop.lnk'
 [IO.File]::WriteAllText($shortcut,'bestaande snelkoppeling; niet wijzigen')
 $vbsHash=(Get-FileHash $vbs).Hash
 $link=[pscustomobject]@{TargetPath='C:\Windows\System32\wscript.exe';WorkingDirectory=$startup;Arguments=('"'+$vbs+'"')}
 $linkTarget=Resolve-LcpPath ([string]$link.TargetPath)
 $linkWorking=Resolve-LcpPath ([string]$link.WorkingDirectory)
 $linkMatches=@([regex]::Matches([string]$link.Arguments,'"([^"\r\n]+\.vbs)"|([^\s"]+\.vbs)'))
 $linkScript=Resolve-LcpPath $linkMatches[0].Groups[1].Value $linkWorking
 Assert-True (Test-LcpStartupLink $link $startup) ('Bestaande Opstarten-snelkoppeling moet herkend worden; doel='+$linkTarget+'; map='+$linkWorking+'; root='+$startup+'; matches='+$linkMatches.Count+'; script='+$linkScript+'; bestaat='+(Test-Path -LiteralPath $vbs -PathType Leaf))
 $link.Arguments='"C:\andere map\LCP-background.vbs"'
 Assert-True (-not (Test-LcpStartupLink $link $startup)) 'Snelkoppeling naar andere installatie mag niet worden gebruikt'
 function Get-LcpStartupShortcut { param($Root);if($Root -eq $startup){return $shortcut} }
 $script:FakeTask=$null
 $startsBefore=$script:Starts;$stopsBefore=$script:Stops
 Invoke-LcpUpdate -Root $startup
 Assert-True ((Get-FileHash $startupWorker).Hash -eq $hashes['lcp_worker_zigbee_v2.py']) 'Opstarten-worker niet geplaatst'
 Assert-True ($script:Starts -eq $startsBefore -and $script:Stops -eq $stopsBefore) 'Opstarten-update mag geen taken of processen herstarten'
 Assert-True ((Get-FileHash $account).Hash -eq $accountHash) 'DPAPI-starter gewijzigd'
 Assert-True ((Get-FileHash $vbs).Hash -eq $vbsHash) 'Achtergrondstarter gewijzigd'
 Assert-True ([IO.File]::ReadAllText($oldState) -eq '{"bestaand":"bewaren"}') 'Oud statusbestand gewijzigd'
 $startupRuntime=Join-Path $startup 'support\lcp_sensor_runtime.json'
 Assert-True ((Get-Content $startupRuntime -Raw | ConvertFrom-Json).launcher_state_isolated) 'v3 moet een eigen statusbestand gebruiken'
 $backupCount=@(Get-ChildItem (Join-Path $startup 'worker-backups') -Directory).Count
 Invoke-LcpUpdate -Root $startup
 Assert-True (@(Get-ChildItem (Join-Path $startup 'worker-backups') -Directory).Count -eq $backupCount) 'Een tweede klik mag de oude back-up niet verdringen'
 Assert-True (-not (Test-LcpHealth ([pscustomobject]@{Root=$startup}) 0)) 'Voor herstart mag update niet gezond worden verklaard'
 Invoke-LcpUpdate -Root $startup -Restore
 Assert-True ([IO.File]::ReadAllText($startupWorker) -eq $original) 'Opstarten-herstel heeft oude worker niet teruggezet'
 Assert-True (-not (Test-Path $startupRuntime)) 'Herstel moet nieuw runtimebestand verwijderen'
 Assert-True ($script:Starts -eq $startsBefore -and $script:Stops -eq $stopsBefore) 'Opstarten-herstel mag geen taken of processen herstarten'
 # Een oude status, zelfs met alle namen, is geen bewijs van een actieve worker.
 $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
 $health=@{version='3.1.0';heartbeat=$now-120;started_at=$now-600;last_config_sync=$now; mqtt_connected=$true;devices=@('LCP_knop','LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve')}
 $health | ConvertTo-Json | Set-Content (Join-Path $startup 'sensor_worker_health.json')
 Assert-True (-not (Test-LcpHealth ([pscustomobject]@{Root=$startup}) 0)) 'Verouderde hartslag mag niet goedgekeurd worden'
 $health.heartbeat=$now
 $health | ConvertTo-Json | Set-Content (Join-Path $startup 'sensor_worker_health.json')
 Assert-True (Test-LcpHealth ([pscustomobject]@{Root=$startup}) 0) 'Verse MQTT-status met alle sensoren moet worden herkend'
 Write-Host 'Windows-update, taakdetectie, back-up, herstel, startfout en behoud Zigbee-database: geslaagd.'
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
