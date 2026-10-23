[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'LCP\Werklaptop'),
    [string]$WorkerPath,
    [switch]$RestoreLatest
)
$ErrorActionPreference = 'Stop'
$PackageDir = $PSScriptRoot

function Test-LcpInside([string]$Path, [string]$Root) {
    return [IO.Path]::GetFullPath($Path).StartsWith([IO.Path]::GetFullPath($Root).TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-LcpAction($Action, [string]$Worker, [string]$Root) {
    $leaf = [IO.Path]::GetFileName($Worker)
    $command = "$($Action.Execute) $($Action.Arguments)"
    if ($command.IndexOf($Worker, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    $working = [Environment]::ExpandEnvironmentVariables([string]$Action.WorkingDirectory)
    if (-not $working) { $working = $Root }
    if ((Test-LcpInside (Join-Path $working 'placeholder') $Root) -and $command.IndexOf($leaf, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    $scripts = @([Environment]::ExpandEnvironmentVariables([string]$Action.Execute))
    foreach ($m in [regex]::Matches([string]$Action.Arguments, '"([^"\r\n]+\.(?:py|ps1|cmd|bat))"|([^\s"]+\.(?:py|ps1|cmd|bat))')) {
        $value = if ($m.Groups[1].Success) { $m.Groups[1].Value } else { $m.Groups[2].Value }
        $value = [Environment]::ExpandEnvironmentVariables($value)
        if (-not [IO.Path]::IsPathRooted($value)) { $value = Join-Path $working $value }
        $scripts += $value
    }
    foreach ($script in $scripts) {
        if ((Test-LcpInside $script $Root) -and (Test-Path -LiteralPath $script -PathType Leaf) -and [IO.Path]::GetExtension($script) -in @('.py','.ps1','.cmd','.bat')) {
            if ([IO.File]::ReadAllText($script).IndexOf($leaf, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
        }
    }
    return $false
}

function Get-LcpPlan([string]$Root, [string]$RequestedWorker) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw 'De bestaande map %LOCALAPPDATA%\LCP\Werklaptop is niet gevonden. Er is niets aangepast.' }
    $Root = (Resolve-Path -LiteralPath $Root).Path
    if ($RequestedWorker) {
        if (-not [IO.Path]::IsPathRooted($RequestedWorker)) { $RequestedWorker = Join-Path $Root $RequestedWorker }
        $candidates = @(Get-Item -LiteralPath $RequestedWorker)
    } else {
        $folders = @($Root) + @(Get-ChildItem -LiteralPath $Root -Directory | Where-Object { $_.Name -notmatch '^(\.|back|backup|node_modules|venv)' } | Select-Object -ExpandProperty FullName)
        $candidates = @(foreach ($folder in $folders) {
            Get-ChildItem -LiteralPath $folder -Filter '*.py' -File | Where-Object {
                $_.FullName -ne (Join-Path $PackageDir 'lcp_worker_zigbee_v2.py') -and
                [IO.File]::ReadAllText($_.FullName).Contains('paho.mqtt.client') -and
                [IO.File]::ReadAllText($_.FullName).Contains('LCP_EMAIL') -and
                $_.Name -notmatch '(backup|voor_|nieuw|old|test|check_lcp_installation)'
            }
        })
    }
    if ($candidates.Count -ne 1) { throw 'De actieve MQTT-worker is niet eenduidig gevonden. Er is niets vervangen. Bewaar deze melding en laat de installatiemap controleren.' }
    $worker = $candidates[0].FullName
    if (-not (Test-LcpInside $worker $Root)) { throw 'De worker valt buiten de bestaande LCP-installatie.' }
    $tasks = @(Get-ScheduledTask | Where-Object {
        $task = $_
        @($task.Actions | Where-Object { Test-LcpAction $_ $worker $Root }).Count -gt 0
    })
    if ($tasks.Count -ne 1) { throw 'Er is niet precies een bestaande achtergrondtaak voor deze worker gevonden. De update stopt zonder de installatie te wijzigen.' }
    if (-not $tasks[0].Settings.Enabled) { throw 'De bestaande achtergrondtaak is uitgeschakeld. De update verandert die keuze niet.' }
    $pythonCandidates = @((Join-Path $Root '.venv\Scripts\python.exe'), (Join-Path $Root 'venv\Scripts\python.exe'))
    foreach ($action in $tasks[0].Actions) {
        $exe = [Environment]::ExpandEnvironmentVariables([string]$action.Execute).Trim('"')
        if ($exe -match 'pythonw?\.exe$' -and [IO.Path]::IsPathRooted($exe)) { $pythonCandidates = @((Join-Path (Split-Path $exe) 'python.exe')) + $pythonCandidates }
    }
    $python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) { throw 'De bestaande Python-omgeving is niet gevonden. Er is niets vervangen.' }
    return [pscustomobject]@{ Root=$Root; Worker=$worker; Python=$python; Task=$tasks[0]; Runtime=(Join-Path (Split-Path $worker) 'lcp_sensor_runtime.json') }
}

function Stop-LcpWorker($Plan) {
    Disable-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath | Out-Null
    Stop-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath
    foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'")) {
        $command = [string]$process.CommandLine
        $full = $command.IndexOf($Plan.Worker, [StringComparison]::OrdinalIgnoreCase) -ge 0
        $relative = $process.ExecutablePath -and (Split-Path $process.ExecutablePath) -eq (Split-Path $Plan.Python) -and $command.IndexOf([IO.Path]::GetFileName($Plan.Worker), [StringComparison]::OrdinalIgnoreCase) -ge 0
        if ($full -or $relative) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}

function Start-LcpWorker($Plan) {
    Enable-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath | Out-Null
    Start-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath
}

function Wait-LcpHealth($Plan, [double]$Started) {
    $health = Join-Path $Plan.Root 'sensor_worker_health.json'
    $deadline = (Get-Date).AddSeconds(60)
    do {
        if (Test-Path -LiteralPath $health) {
            try {
                $status = Get-Content -LiteralPath $health -Raw | ConvertFrom-Json
                $names = @('LCP_knop','LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve')
                if ($status.version -eq '3.0.0' -and $status.started_at -ge $Started -and $status.mqtt_connected -and $status.last_config_sync -ge $Started -and @($names | Where-Object { $_ -notin $status.devices }).Count -eq 0) { return }
            } catch { }
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw 'De bijgewerkte worker heeft MQTT en de vier sensorinstellingen niet bevestigd. De oude worker wordt teruggezet.'
}

function Restore-LcpFiles($Plan, [string]$Backup) {
    Copy-Item -LiteralPath (Join-Path $Backup 'worker.py') -Destination $Plan.Worker -Force
    $oldRuntime = Join-Path $Backup 'runtime.json'
    if (Test-Path -LiteralPath $oldRuntime) { Copy-Item -LiteralPath $oldRuntime -Destination $Plan.Runtime -Force }
    elseif (Test-Path -LiteralPath $Plan.Runtime) { Remove-Item -LiteralPath $Plan.Runtime -Force }
}

function Invoke-LcpUpdateCore([string]$Root, [string]$RequestedWorker, [switch]$Restore) {
    if ($env:OS -ne 'Windows_NT') { throw 'Voer dit updatebestand uit op de bestaande Windows-werklaptop.' }
    $plan = Get-LcpPlan $Root $RequestedWorker
    $backupRoot = Join-Path $plan.Root 'worker-backups'
    if ($Restore) {
        $latest = Get-ChildItem -LiteralPath $backupRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'worker.py') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (-not $latest) { throw 'Er is geen workerback-up gevonden.' }
        $metadata = Get-Content -LiteralPath (Join-Path $latest.FullName 'backup.json') -Raw | ConvertFrom-Json
        if ($metadata.worker -ne $plan.Worker -or (Get-FileHash -LiteralPath (Join-Path $latest.FullName 'worker.py') -Algorithm SHA256).Hash -ne $metadata.sha256) { throw 'De back-up hoort niet bij deze worker of is gewijzigd.' }
        Stop-LcpWorker $plan
        try { Restore-LcpFiles $plan $latest.FullName } finally { Start-LcpWorker $plan }
        Write-Host 'Vorige worker teruggezet. Test de bestaande oproepknop.'
        return
    }
    $manifest = Get-Content -LiteralPath (Join-Path $PackageDir 'manifest.json') -Raw | ConvertFrom-Json
    if (@($manifest.files.PSObject.Properties).Count -ne 2) { throw 'Het updatepakket is onvolledig.' }
    foreach ($item in $manifest.files.PSObject.Properties) {
        if ($item.Name -notin @('lcp_worker_zigbee_v2.py','check_lcp_installation.py')) { throw 'Het pakket bevat een onverwacht updatebestand.' }
        if ((Get-FileHash -LiteralPath (Join-Path $PackageDir $item.Name) -Algorithm SHA256).Hash -ne $item.Value) { throw 'Een updatebestand is beschadigd. Download het pakket opnieuw.' }
    }
    $stage = Join-Path $plan.Root ('.lcp-update-' + [guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $stage | Out-Null
    $stopped = $false
    $backup = $null
    try {
        $newRuntime = Join-Path $stage 'runtime.json'
        & $plan.Python (Join-Path $PackageDir 'check_lcp_installation.py') --worker $plan.Worker --install-dir $plan.Root --output $newRuntime
        if ($LASTEXITCODE -ne 0) { throw 'De bestaande worker is niet veilig compatibel. Er is niets vervangen.' }
        $payload = Join-Path $PackageDir 'lcp_worker_zigbee_v2.py'
        Copy-Item -LiteralPath $payload -Destination (Join-Path $stage 'worker.py')
        & $plan.Python -m py_compile (Join-Path $stage 'worker.py')
        if ($LASTEXITCODE -ne 0) { throw 'De nieuwe worker heeft een syntaxfout.' }
        & $plan.Python (Join-Path $stage 'worker.py') --self-test
        if ($LASTEXITCODE -ne 0) { throw 'Bestaande Python-onderdelen ontbreken. Er is niets vervangen.' }
        $backup = Join-Path $backupRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetAccessRuleProtection($true,$false)
        $acl.SetOwner($sid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')))
        Set-Acl -LiteralPath $backup -AclObject $acl
        Copy-Item -LiteralPath $plan.Worker -Destination (Join-Path $backup 'worker.py')
        if (Test-Path -LiteralPath $plan.Runtime) { Copy-Item -LiteralPath $plan.Runtime -Destination (Join-Path $backup 'runtime.json') }
        Export-ScheduledTask -TaskName $plan.Task.TaskName -TaskPath $plan.Task.TaskPath | Set-Content -LiteralPath (Join-Path $backup 'taak.xml') -Encoding UTF8
        @{ worker=$plan.Worker;sha256=(Get-FileHash -LiteralPath $plan.Worker -Algorithm SHA256).Hash;task=$plan.Task.TaskName;taskPath=$plan.Task.TaskPath } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'backup.json') -Encoding UTF8
        if ((Get-FileHash -LiteralPath (Join-Path $backup 'worker.py') -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $plan.Worker -Algorithm SHA256).Hash) { throw 'De back-upcontrole is mislukt. De bestaande worker blijft actief.' }
        Write-Host 'Back-up gemaakt. Alleen de bestaande LCP-worker wordt kort herstart.'
        $stopped = $true
        Stop-LcpWorker $plan
        Copy-Item -LiteralPath (Join-Path $stage 'worker.py') -Destination $plan.Worker -Force
        Copy-Item -LiteralPath $newRuntime -Destination $plan.Runtime -Force
        $started = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
        Start-LcpWorker $plan
        Wait-LcpHealth $plan $started
        $stopped = $false
        Write-Host 'Update voltooid: MQTT verbonden en de vier deursensoren geladen.'
        Write-Host "Back-up: $backup"
        Write-Host 'Test nu de fysieke oproepknop en daarna openen/sluiten van iedere actieve deur.'
    } catch {
        if ($stopped -and $backup) {
            try {
                Stop-LcpWorker $plan
                Restore-LcpFiles $plan $backup
                Start-LcpWorker $plan
                Write-Host 'De vorige worker is teruggezet en de bestaande taak is opnieuw gestart.'
            } catch { Write-Host "Automatisch herstel niet voltooid. Bewaar de back-up: $backup" }
        }
        throw
    } finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
}

function Invoke-LcpUpdate([string]$Root, [string]$RequestedWorker, [switch]$Restore) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $mutex = New-Object Threading.Mutex($false, ('Local\LCP-door-update-' + $sid))
    $locked = $false
    try {
        $locked = $mutex.WaitOne(0)
        if (-not $locked) { throw 'Er wordt al een LCP-update uitgevoerd. Wacht tot die klaar is.' }
        Invoke-LcpUpdateCore -Root $Root -RequestedWorker $RequestedWorker -Restore:$Restore
    } finally { if ($locked) { $mutex.ReleaseMutex() };$mutex.Dispose() }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Invoke-LcpUpdate -Root $InstallDir -RequestedWorker $WorkerPath -Restore:$RestoreLatest }
    catch { Write-Host ('Update gestopt: ' + $_.Exception.Message) -ForegroundColor Red;exit 1 }
}
