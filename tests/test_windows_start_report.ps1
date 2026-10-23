$ErrorActionPreference = 'Stop'
$file = Join-Path (Split-Path $PSScriptRoot) 'windows\Controleer-LCP-Start.ps1'
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors) | Out-Null
if ($errors.Count) { throw $errors[0].Message }
. $file
function Get-ScheduledTask {
    [CmdletBinding()]param()
    @(
        [pscustomobject]@{TaskName='LCP worker'; TaskPath='\'; State='Running'; Actions=@([pscustomobject]@{Execute='C:\Python\python.exe'; WorkingDirectory='C:\LCP'; Arguments='"\\server\share\LCP map\start.py" --password SECRET_DO_NOT_REPORT'})},
        [pscustomobject]@{TaskName='Andere taak'; TaskPath='\'; State='Ready'; Actions=@([pscustomobject]@{Execute='C:\tool.exe'; Arguments='--token OTHER_SECRET'})}
    )
}
function Get-CimInstance {
    [CmdletBinding()]param($ClassName, $Filter)
    [pscustomobject]@{ExecutablePath='C:\Python\python.exe'; CommandLine='"C:\Python\python.exe" "C:\LCP\worker.py" --password PROCESS_SECRET'}
}
function New-Object { param($ComObject); throw 'COM niet nodig voor deze test' }
foreach ($name in @('Stop-Process','Stop-ScheduledTask','Start-ScheduledTask','Disable-ScheduledTask','Enable-ScheduledTask','Copy-Item','Remove-Item')) {
    Set-Item -Path ('Function:\'+$name) -Value { throw 'De controle mag de installatie niet wijzigen' }
}
$report = (Get-LcpStartReport @('C:\LCP-niet-bestaand')) -join "`n"
foreach ($secret in @('SECRET_DO_NOT_REPORT','OTHER_SECRET','PROCESS_SECRET','--password','--token')) {
    if ($report.Contains($secret)) { throw 'Geheim of overige argumenten in verslag opgenomen' }
}
foreach ($expected in @('LCP worker','\\server\share\LCP map\start.py','C:\LCP\worker.py','Aantal: 1')) {
    if (-not $report.Contains($expected)) { throw ('Ontbrekende diagnose: '+$expected) }
}
if ($report.Contains('Andere taak')) { throw 'Onverwante taak opgenomen' }
Write-Host 'Startcontrole: netwerkpad, starttaak, actief script en afschermen overige argumenten geslaagd.'
