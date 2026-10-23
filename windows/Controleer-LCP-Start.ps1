[CmdletBinding()]
param([string]$ExtraMap, [switch]$VraagMap)

# Alleen lezen: geen taken, processen, scripts of LCP-instellingen wijzigen.
function Get-LcpScriptPaths([string]$Text) {
    foreach ($match in [regex]::Matches($Text, '(?i)"([^"\r\n]+\.(?:pyw?|ps1|cmd|bat|vbs))"|([^\s"=]+\.(?:pyw?|ps1|cmd|bat|vbs))')) {
        $value = if ($match.Groups[1].Success) { $match.Groups[1].Value } else { $match.Groups[2].Value }
        # Alleen bestandsnamen/paden; nooit overige opdrachtargumenten opnemen.
        $value
    }
}

function Get-LcpStartReport([string[]]$Roots) {
    'LCP-startcontrole - alleen gelezen, niets aan LCP gewijzigd'
    'Datum: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    foreach ($root in @($Roots | Where-Object { $_ } | Select-Object -Unique)) {
        'Map: ' + $root
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { '  Niet gevonden of niet toegankelijk'; continue }
        $folders = @($root) + @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '^(\.|back|backup|node_modules|venv)' } | Select-Object -ExpandProperty FullName)
        foreach ($folder in $folders) {
            Get-ChildItem -LiteralPath $folder -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -in @('.py','.pyw','.ps1','.cmd','.bat','.vbs') } | ForEach-Object { '  Script: ' + $_.FullName }
        }
    }
    'Achtergrondtaken met een LCP-verwijzing:'
    try {
        $count = 0
        foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
            $text = $task.TaskName + ' ' + $task.TaskPath
            foreach ($action in $task.Actions) { $text += ' ' + $action.Execute + ' ' + $action.Arguments + ' ' + $action.WorkingDirectory }
            $related = $text -match '(?i)LCP'
            foreach ($root in $Roots) { if ($root -and $text.IndexOf($root, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $related = $true } }
            if (-not $related) { continue }
            $count++
            '  Taak: ' + $task.TaskPath + $task.TaskName + ' | status: ' + $task.State
            foreach ($action in $task.Actions) {
                '    Programma: ' + $action.Execute
                '    Startmap: ' + $action.WorkingDirectory
                foreach ($path in @(Get-LcpScriptPaths ([string]$action.Arguments))) { '    Startbestand: ' + $path }
            }
        }
        '  Aantal: ' + $count
    } catch { '  Taakplanner kon niet worden gelezen; probeer hetzelfde Windows-account met beheerdersrechten.' }
    'Actieve Python-startbestanden (zonder overige argumenten):'
    try {
        foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction Stop)) {
            foreach ($path in @(Get-LcpScriptPaths ([string]$process.CommandLine))) { '  Script: ' + $path + ' | Python: ' + $process.ExecutablePath }
        }
    } catch { '  Actieve processen konden niet worden gelezen.' }
    'LCP-snelkoppelingen in Opstarten:'
    try {
        $shell = New-Object -ComObject WScript.Shell
        foreach ($folder in @([Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup'))) {
            if (-not $folder) { continue }
            foreach ($file in @(Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -ErrorAction SilentlyContinue)) {
                $link = $shell.CreateShortcut($file.FullName)
                if (($file.Name + ' ' + $link.TargetPath + ' ' + $link.Arguments) -notmatch '(?i)LCP') { continue }
                '  Snelkoppeling: ' + $file.Name + ' | Doel: ' + $link.TargetPath + ' | Startmap: ' + $link.WorkingDirectory
                foreach ($path in @(Get-LcpScriptPaths ([string]$link.Arguments))) { '    Startbestand: ' + $path }
            }
        }
    } catch { '  Opstartsnelkoppelingen konden niet worden gelezen.' }
    'LCP-vermeldingen in automatisch starten (alleen namen):'
    foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Run', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run')) {
        if (-not (Test-Path $key)) { continue }
        $values = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
        foreach ($property in $values.PSObject.Properties) {
            if ($property.Name -notmatch '^PS' -and ($property.Name + ' ' + [string]$property.Value) -match '(?i)LCP') { '  ' + $key + ' : ' + $property.Name }
        }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    if ($VraagMap) { $ExtraMap = Read-Host 'Pad van je andere LCP-map (of Enter als je dit niet weet)' }
    if ($ExtraMap) { $ExtraMap = [Environment]::ExpandEnvironmentVariables($ExtraMap.Trim().Trim('"')) }
    $roots = @((Join-Path $env:LOCALAPPDATA 'LCP\Werklaptop'), $ExtraMap)
    $report = @(Get-LcpStartReport $roots)
    $output = Join-Path $PSScriptRoot 'LCP-startcontrole.txt'
    $report | Set-Content -LiteralPath $output -Encoding UTF8
    $report | ForEach-Object { Write-Host $_ }
    Write-Host "Controle klaar. Deel de tekst uit: $output"
}
