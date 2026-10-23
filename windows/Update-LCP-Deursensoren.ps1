[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'LCP\Werklaptop'),
    [string]$WorkerPath,
    [switch]$RestoreLatest,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$PackageDir = $PSScriptRoot

function Resolve-LcpPath([AllowNull()][string]$Path, [string]$BasePath) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    $value = [Environment]::ExpandEnvironmentVariables($Path).Trim()
    # Taakplanner kan een pad inclusief buitenste aanhalingstekens teruggeven.
    if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
        $value = $value.Substring(1, $value.Length - 2).Trim()
    }
    # COM-acties, URI's en onopgeloste taakvariabelen zijn geen bestandspaden.
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[<>"|?*\x00-\x1f]' -or $value -match '%[^%]+%|\$\(') { return $null }
    try {
        if ($value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))') {
            # Geen drive-relatieve paden zoals C:script.py of \script.py.
            if ($value -match '[:\\]' -and ($value.Contains(':') -or $value.StartsWith('\'))) { return $null }
            $base = Resolve-LcpPath $BasePath
            if (-not $base) { return $null }
            $value = [IO.Path]::Combine($base, $value)
        }
        return [IO.Path]::GetFullPath($value)
    } catch {
        return $null
    }
}

function Test-LcpInside([string]$Path, [string]$Root) {
    $full = Resolve-LcpPath $Path
    $base = Resolve-LcpPath $Root
    if (-not $full -or -not $base) { return $false }
    return $full.StartsWith($base.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-LcpAction($Action, [string]$Worker, [string]$Root) {
    if (-not $Action -or [string]::IsNullOrWhiteSpace([string]$Action.Execute)) { return $false }
    $workerPath = Resolve-LcpPath $Worker
    $rootPath = Resolve-LcpPath $Root
    if (-not $workerPath -or -not $rootPath) { return $false }
    if ([string]::IsNullOrWhiteSpace([string]$Action.WorkingDirectory)) {
        $working = $rootPath
    } else {
        $working = Resolve-LcpPath ([string]$Action.WorkingDirectory) $rootPath
        if (-not $working) { return $false }
    }
    $execute = Resolve-LcpPath ([string]$Action.Execute) $working
    if (-not $execute) { return $false }
    $leaf = [IO.Path]::GetFileName($workerPath)
    $command = [Environment]::ExpandEnvironmentVariables("$($Action.Execute) $($Action.Arguments)")
    if ($command.IndexOf($workerPath, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    if ((Test-LcpInside ([IO.Path]::Combine($working, 'placeholder')) $rootPath) -and $command.IndexOf($leaf, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    $scripts = @($execute)
    foreach ($m in [regex]::Matches([string]$Action.Arguments, '"([^"\r\n]+\.(?:py|ps1|cmd|bat))"|([^\s"]+\.(?:py|ps1|cmd|bat))')) {
        $value = if ($m.Groups[1].Success) { $m.Groups[1].Value } else { $m.Groups[2].Value }
        $resolved = Resolve-LcpPath $value $working
        if ($resolved) { $scripts += $resolved }
    }
    foreach ($script in $scripts) {
        if ((Test-LcpInside $script $rootPath) -and [IO.Path]::GetExtension($script) -in @('.py','.ps1','.cmd','.bat')) {
            try {
                if ((Test-Path -LiteralPath $script -PathType Leaf) -and [IO.File]::ReadAllText($script).IndexOf($leaf, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
            } catch {
                # Een niet-leesbare, andere Windows-taak mag de update niet blokkeren.
            }
        }
    }
    return $false
}

function Test-LcpStartupLink($Link, [string]$Root) {
    # Windows kan dezelfde map als RUNNER~1 of als volledige gebruikersnaam geven.
    $Root = Resolve-LcpPath $Root
    if (-not $Root) { return $false }
    $target = Resolve-LcpPath ([string]$Link.TargetPath)
    $working = Resolve-LcpPath ([string]$Link.WorkingDirectory)
    $scripts = @([regex]::Matches([string]$Link.Arguments, '"([^"\r\n]+\.vbs)"|([^\s"]+\.vbs)'))
    if (-not $target -or [IO.Path]::GetFileName($target) -ine 'wscript.exe' -or $working -ine $Root -or $scripts.Count -ne 1) { return $false }
    $value = if ($scripts[0].Groups[1].Success) { $scripts[0].Groups[1].Value } else { $scripts[0].Groups[2].Value }
    $script = Resolve-LcpPath $value $working
    return ($script -ieq (Join-Path $Root 'LCP-background.vbs') -and (Test-Path -LiteralPath $script -PathType Leaf))
}

function Get-LcpStartupShortcut([string]$Root) {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('Startup'), [Environment]::GetFolderPath('CommonStartup'))) {
        if (-not $folder) { continue }
        $path = Join-Path $folder 'LCP Werklaptop.lnk'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $link = $shell.CreateShortcut($path)
        if (Test-LcpStartupLink $link $Root) { $path }
    }
}

function Get-LcpPlan([string]$Root, [string]$RequestedWorker) {
    $Root = Resolve-LcpPath $Root
    if (-not $Root -or -not (Test-Path -LiteralPath $Root -PathType Container)) { throw 'De bestaande map %LOCALAPPDATA%\LCP\Werklaptop is niet gevonden. Er is niets aangepast.' }
    $Root = (Resolve-Path -LiteralPath $Root).Path
    if ($RequestedWorker) {
        $RequestedWorker = Resolve-LcpPath $RequestedWorker $Root
        if (-not $RequestedWorker) { throw 'Het opgegeven workerpad is niet geldig. Er is niets vervangen.' }
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
    if ($tasks.Count -eq 0 -and $worker -ieq (Join-Path $Root 'support\upstream_worker.py')) {
        $launcher = Join-Path $Root 'support\account.py'
        $python = Join-Path $Root '.venv\Scripts\python.exe'
        $shortcuts = @(Get-LcpStartupShortcut $Root)
        if ($shortcuts.Count -eq 1 -and (Test-Path -LiteralPath $launcher -PathType Leaf) -and (Test-Path -LiteralPath $python -PathType Leaf)) {
            return [pscustomobject]@{ Mode='Startup';Root=$Root;Worker=$worker;Python=$python;Task=$null;Launcher=$launcher;Shortcut=$shortcuts[0];Runtime=(Join-Path (Split-Path $worker) 'lcp_sensor_runtime.json') }
        }
    }
    if ($tasks.Count -ne 1) { throw 'De bestaande starttaak of Opstarten-snelkoppeling is niet eenduidig herkend. De update stopt zonder de installatie te wijzigen.' }
    if (-not $tasks[0].Settings.Enabled) { throw 'De bestaande achtergrondtaak is uitgeschakeld. De update verandert die keuze niet.' }
    $pythonCandidates = @((Join-Path $Root '.venv\Scripts\python.exe'), (Join-Path $Root 'venv\Scripts\python.exe'))
    foreach ($action in $tasks[0].Actions) {
        $exe = Resolve-LcpPath ([string]$action.Execute) $Root
        if ($exe -and $exe -match 'pythonw?\.exe$') { $pythonCandidates = @((Join-Path (Split-Path $exe) 'python.exe')) + $pythonCandidates }
    }
    $python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) { throw 'De bestaande Python-omgeving is niet gevonden. Er is niets vervangen.' }
    return [pscustomobject]@{ Mode='Task';Root=$Root; Worker=$worker; Python=$python; Task=$tasks[0]; Runtime=(Join-Path (Split-Path $worker) 'lcp_sensor_runtime.json') }
}

function Stop-LcpWorker($Plan) {
    if ($Plan.Mode -eq 'Startup') { throw 'Deze installatie gebruikt Opstarten. De update mag haar processen niet stoppen.' }
    $disabled = $false
    try {
        Disable-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath | Out-Null
        $disabled = $true
        Stop-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath
        foreach ($process in @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'")) {
            $command = [string]$process.CommandLine
            $full = $command.IndexOf($Plan.Worker, [StringComparison]::OrdinalIgnoreCase) -ge 0
            $relative = $process.ExecutablePath -and (Split-Path $process.ExecutablePath) -eq (Split-Path $Plan.Python) -and $command.IndexOf([IO.Path]::GetFileName($Plan.Worker), [StringComparison]::OrdinalIgnoreCase) -ge 0
            if ($full -or $relative) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
        }
    } catch {
        if ($disabled) {
            Enable-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath | Out-Null
            Start-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath
        }
        throw 'De bestaande taak kon niet veilig worden gestopt. Er is geen worker vervangen. Start de update zo nodig als beheerder met hetzelfde Windows-account.'
    }
}

function Start-LcpWorker($Plan) {
    if ($Plan.Mode -eq 'Startup') { throw 'Herstart Windows om de bestaande Opstarten-snelkoppeling te gebruiken.' }
    Enable-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath | Out-Null
    Start-ScheduledTask -TaskName $Plan.Task.TaskName -TaskPath $Plan.Task.TaskPath
}

function Test-LcpHealth($Plan, [double]$Started) {
    $health = Join-Path $Plan.Root 'sensor_worker_health.json'
    if (-not (Test-Path -LiteralPath $health)) { return $false }
    try {
        $status = Get-Content -LiteralPath $health -Raw | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
        $names = @('LCP_knop','LCP kantoor','LCP nooddeur','TRAP nooddeur','LCP reserve')
        return ($status.version -eq '3.1.0' -and $status.started_at -ge $Started -and $status.mqtt_connected -and $status.last_config_sync -ge $Started -and $status.last_config_sync -ge ($now - 90) -and $status.heartbeat -ge ($now - 30) -and $status.heartbeat -le ($now + 10) -and @($names | Where-Object { $_ -notin $status.devices }).Count -eq 0)
    } catch { return $false }
}

function Wait-LcpHealth($Plan, [double]$Started) {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        if (Test-LcpHealth $Plan $Started) { return }
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
    if (Test-Path -LiteralPath $plan.Runtime -PathType Container) { throw 'Het runtimepad is een map in plaats van een bestand. Er is niets vervangen.' }
    $backupRoot = Join-Path $plan.Root 'worker-backups'
    if ($Restore) {
        $latest = Get-ChildItem -LiteralPath $backupRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'worker.py') } | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if (-not $latest) { throw 'Er is geen workerback-up gevonden.' }
        $metadata = Get-Content -LiteralPath (Join-Path $latest.FullName 'backup.json') -Raw | ConvertFrom-Json
        if ($metadata.worker -ne $plan.Worker -or (Get-FileHash -LiteralPath (Join-Path $latest.FullName 'worker.py') -Algorithm SHA256).Hash -ne $metadata.sha256) { throw 'De back-up hoort niet bij deze worker of is gewijzigd.' }
        if ($plan.Mode -eq 'Startup') {
            Restore-LcpFiles $plan $latest.FullName
            Write-Host 'Vorige worker teruggezet. Herstart Windows en test daarna de oproepknop.'
            return
        }
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
    $prepared = $false
    if ($plan.Mode -eq 'Startup' -and (Test-Path -LiteralPath $plan.Runtime -PathType Leaf)) {
        try {
            $runtime = Get-Content -LiteralPath $plan.Runtime -Raw | ConvertFrom-Json
            $prepared = $runtime.launcher_state_isolated -eq $true -and $runtime.state_file -eq (Join-Path $plan.Root 'sensor_state_v3.json') -and $runtime.health_file -eq (Join-Path $plan.Root 'sensor_worker_health.json')
        } catch { $prepared = $false }
    }
    if ($prepared -and (Get-FileHash -LiteralPath $plan.Worker -Algorithm SHA256).Hash -eq $manifest.files.'lcp_worker_zigbee_v2.py') {
        # Een tweede klik mag de echte oude back-up niet verdringen.
        Write-Host 'Deze workerupdate is al geplaatst. Herstart Windows als dat nog niet is gebeurd en open daarna Controleer-LCP-Deursensoren.cmd.'
        return
    }
    $stage = Join-Path $plan.Root ('.lcp-update-' + [guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $stage | Out-Null
    $stopped = $false
    $backup = $null
    try {
        $newRuntime = Join-Path $stage 'runtime.json'
        $checkArgs = @('--worker', $plan.Worker, '--install-dir', $plan.Root, '--output', $newRuntime)
        if ($plan.Mode -eq 'Startup') { $checkArgs += @('--launcher', $plan.Launcher) }
        & $plan.Python (Join-Path $PackageDir 'check_lcp_installation.py') @checkArgs
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
        if ($plan.Mode -eq 'Task') { Export-ScheduledTask -TaskName $plan.Task.TaskName -TaskPath $plan.Task.TaskPath | Set-Content -LiteralPath (Join-Path $backup 'taak.xml') -Encoding Unicode }
        @{ worker=$plan.Worker;sha256=(Get-FileHash -LiteralPath $plan.Worker -Algorithm SHA256).Hash;task=$plan.Task.TaskName;taskPath=$plan.Task.TaskPath } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'backup.json') -Encoding UTF8
        if ((Get-FileHash -LiteralPath (Join-Path $backup 'worker.py') -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $plan.Worker -Algorithm SHA256).Hash) { throw 'De back-upcontrole is mislukt. De bestaande worker blijft actief.' }
        if ($plan.Mode -eq 'Startup') {
            try {
                # Niet stoppen/starten: de bestaande ouder verzorgt stdin en MQTT.
                Copy-Item -LiteralPath $newRuntime -Destination $plan.Runtime -Force
                [IO.File]::Replace((Join-Path $stage 'worker.py'), $plan.Worker, (Join-Path $stage 'replaced-worker.py'))
            } catch {
                Restore-LcpFiles $plan $backup
                throw 'Plaatsen mislukt; vorige bestanden teruggezet. Er zijn geen processen gestopt.'
            }
            Write-Host 'Update voorbereid. Herstart Windows om de vier deursensoren te activeren.'
            Write-Host "Back-up: $backup"
            Write-Host 'Na aanmelden: wacht een minuut en open Controleer-LCP-Deursensoren.cmd uit dit pakket.'
            return
        }
        Write-Host 'Back-up gemaakt. Alleen de bestaande LCP-worker wordt kort herstart.'
        Stop-LcpWorker $plan
        $stopped = $true
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
    try {
        if ($CheckOnly) {
            if (Test-LcpHealth ([pscustomobject]@{Root=$InstallDir}) 0) { Write-Host 'Actief: nieuwe sensorworker, MQTT verbonden en alle vier deursensoren geladen. Test nu de fysieke knop en deuren.' }
            else { throw 'De nieuwe sensorworker is nog niet gezond bevestigd. Herstart Windows, meld je aan en wacht een minuut. Gebruik bij aanhoudende problemen Herstel-LCP-Worker.cmd en herstart daarna Windows.' }
        } else { Invoke-LcpUpdate -Root $InstallDir -RequestedWorker $WorkerPath -Restore:$RestoreLatest }
    }
    catch { Write-Host ('Update gestopt: ' + $_.Exception.Message) -ForegroundColor Red;exit 1 }
}
