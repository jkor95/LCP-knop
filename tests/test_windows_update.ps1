$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot
$file=Join-Path $repo 'windows\Update-LCP-Deursensoren.ps1'
$tokens=$null;$errors=$null
[System.Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors) | Out-Null
if ($errors.Count) { throw ('PowerShell-syntaxfout: '+$errors[0].Message) }
. $file
function Assert-True($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$root=Join-Path $env:TEMP ('LCP-update-test-'+[guid]::NewGuid().ToString('N'))
$package=Join-Path $root 'bundle'
$install=Join-Path $root 'Werklaptop'
New-Item -ItemType Directory -Path $package,$install | Out-Null
$PackageDir=$package
$script:TestInstall=$install
$script:Starts=0;$script:Stops=0;$script:SimulateFailure=$false
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
@{version='3.0.0';files=$hashes} | ConvertTo-Json | Set-Content (Join-Path $package 'manifest.json')
$script:FakeTask=[pscustomobject]@{TaskName='LCP bestaande worker';TaskPath='\';Settings=[pscustomobject]@{Enabled=$true};Actions=@([pscustomobject]@{Execute=$python;Arguments=('"'+(Join-Path $install 'start_lcp.py')+'"');WorkingDirectory=$install})}
function Get-ScheduledTask { return $script:FakeTask }
function Disable-ScheduledTask { param($TaskName,$TaskPath);$script:FakeTask.Settings.Enabled=$false }
function Enable-ScheduledTask { param($TaskName,$TaskPath);$script:FakeTask.Settings.Enabled=$true }
function Stop-ScheduledTask { param($TaskName,$TaskPath);$script:Stops++ }
function Export-ScheduledTask { param($TaskName,$TaskPath);return '<Task>ongewijzigde starttaak</Task>' }
function Get-CimInstance { param($ClassName,$Filter);return @() }
function Start-ScheduledTask {
 param($TaskName,$TaskPath)
 $script:Starts++
 @{version='3.0.0';started_at=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);last_config_sync=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);mqtt_connected=$true;devices=@('LCP_knop','LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve')} | ConvertTo-Json | Set-Content (Join-Path $script:TestInstall 'sensor_worker_health.json')
}
$script:RealWait=(Get-Item Function:\Wait-LcpHealth).ScriptBlock
function Wait-LcpHealth($Plan,$Started) {
 if ($script:SimulateFailure) { throw 'Gesimuleerde startfout' }
 & $script:RealWait $Plan $Started
}
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
 $before=$script:Stops
 $empty=Join-Path $root 'Onbekend'
 New-Item -ItemType Directory -Path $empty | Out-Null
 $refused=$false
 try { Invoke-LcpUpdate -Root $empty } catch { $refused=$true }
 Assert-True ($refused -and $script:Stops -eq $before) 'Onbekende installatie moet stoppen voordat taken worden gewijzigd'
 Write-Host 'Windows-update, taakdetectie, back-up, herstel, startfout en behoud Zigbee-database: geslaagd.'
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
