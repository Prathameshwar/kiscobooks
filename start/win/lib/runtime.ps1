# Workspace-owned runtime processes. State contains identity only, never environment values.
function ConvertTo-BillArgument {
    param([AllowEmptyString()][string]$Value)
    # Windows CommandLineToArgvW quoting. This is passed directly to an executable, not cmd.exe.
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Get-BillRuntimePath {
    param([Parameter(Mandatory)][string]$Name)
    if ($Name -notmatch '^[a-z][a-z0-9-]*$') { throw 'Invalid runtime name.' }
    return Join-Path $Global:BILL_WIN_ROOT "runtime\$Name.json"
}

function Get-BillNginxRoot {
    $root = [IO.Path]::GetFullPath((Join-Path $Global:BILL_REPO_ROOT (Get-BillConfig).infra.nginx.root_relative))
    Assert-BillChildPath -Path $root -Root $Global:BILL_WIN_ROOT
    return $root
}

function Enter-BillRuntimeLock {
    param([Parameter(Mandatory)][string]$Name)
    $statePath = Get-BillRuntimePath $Name
    New-Item -ItemType Directory -Path (Split-Path -Parent $statePath) -Force | Out-Null
    try {
        return [IO.File]::Open(($statePath + '.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw "$Name has another start/stop command in progress. Retry when it finishes." }
}

function Read-BillEnvironment {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Missing environment file: $Path. Run setup.bat -Component envs." }
    $values = @{}
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ($line.Trim() -eq '' -or $line.TrimStart().StartsWith('#')) { continue }
        if ($line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$' -or $values.ContainsKey($Matches[1])) {
            throw "Invalid or duplicate environment key in $Path."
        }
        # Do not interpolate or shell-evaluate values, including %, quotes, JSON, & and Unicode.
        $values[$Matches[1]] = $Matches[2]
    }
    return $values
}

function Get-BillAuthProvider {
    # Who owns credentials: 'local' (the default; Identity is the OIDC provider) or 'authentik'.
    # Read from the private identity.env the services themselves start with, so a script can never
    # disagree with Identity about which provider is running.
    $path = Join-Path $Global:BILL_ENV_DIR 'identity.env'
    if (-not (Test-Path -LiteralPath $path)) { return 'local' }
    $provider = (Read-BillEnvironment $path)['IDENTITY_AUTH_PROVIDER']
    if (-not $provider) { return 'local' }
    if ($provider -cnotin @('local', 'authentik')) { throw 'IDENTITY_AUTH_PROVIDER must be local or authentik.' }
    return $provider
}

function Get-BillManagedProcess {
    param([Parameter(Mandatory)][string]$Name, [switch]$ForStart, [switch]$ForGracefulStop)
    $path = Get-BillRuntimePath $Name
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $record = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $process = Get-Process -Id ([int]$record.process_id) -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    $process.Refresh()
    if ($process.HasExited) { return $null }
    $startedAt = $process.StartTime
    if (-not $startedAt) {
        # A process can exit between Refresh() and reading StartTime. Never
        # dereference a missing timestamp or claim ownership of that PID.
        $process.Refresh()
        if ($process.HasExited) { return $null }
        if ($ForStart -and $record.workspace -eq $Global:BILL_REPO_ROOT) {
            Write-BillLog "$Name has a stale process record; its previous PID cannot be verified. The process was preserved." 'WARN'
            return $null
        }
        throw "Process start time unavailable for $Name; it was left untouched."
    }
    # Windows can hide Path for an elevated process even when its creation time is
    # readable. The workspace-local stop marker can still request graceful exit;
    # forced termination and endpoint shutdown must retain full verification.
    $executable = $process.Path
    if ($ForGracefulStop -and -not $executable -and
        $record.workspace -eq $Global:BILL_REPO_ROOT -and
        $record.started_ticks -eq [string]$startedAt.ToUniversalTime().Ticks) {
        Write-BillLog "$Name executable path is unavailable; requesting graceful shutdown only." 'WARN'
        return $process
    }
    # Reject reused PIDs and state copied from another checkout before sending any signal.
    if ($record.workspace -ne $Global:BILL_REPO_ROOT -or
        $record.started_ticks -ne [string]$startedAt.ToUniversalTime().Ticks -or
        $record.executable -ne $executable) {
        # A fast startup failure can exit between Get-Process and identity inspection.
        $process.Refresh()
        if ($process.HasExited) { return $null }
        if ($ForStart -and $record.workspace -eq $Global:BILL_REPO_ROOT) {
            Write-BillLog "$Name has a stale process record; its previous PID was reused. The unrelated process was preserved." 'WARN'
            return $null
        }
        if (-not $executable) { throw "Executable path unavailable for $Name; forced shutdown was refused. Run stop-all from the same Windows account and elevation used to start it." }
        throw "Process identity changed for $Name; it was left untouched."
    }
    return $process
}

function Start-BillProcess {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Executable,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $Global:BILL_REPO_ROOT,
        [hashtable]$Environment = @{}
    )
    $runtimeLock = Enter-BillRuntimeLock $Name
    try {
        if (Get-BillManagedProcess $Name -ForStart) { throw "$Name already has a running managed process." }
        $statePath = Get-BillRuntimePath $Name
        New-Item -ItemType Directory -Path (Split-Path -Parent $statePath) -Force | Out-Null
        $stopPath = Join-Path (Split-Path -Parent $statePath) "$Name.stop"
        Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
        # A small host redirects logs itself; no unconsumed stdout/stderr pipes can block a server.
        $hostScript = Join-Path $Global:BILL_WIN_ROOT 'process-host.ps1'
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = (Get-Command powershell.exe).Source
        $psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File ' + (ConvertTo-BillArgument $hostScript) + ' -Name ' + (ConvertTo-BillArgument $Name)
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.WorkingDirectory = $WorkingDirectory
        # EnvironmentVariables is supported by .NET Framework / Windows PowerShell 5.1.
        foreach ($key in $Environment.Keys) { $psi.EnvironmentVariables[[string]$key] = [string]$Environment[$key] }
        $psi.EnvironmentVariables['BILL_CHILD_EXECUTABLE'] = $Executable
        $psi.EnvironmentVariables['BILL_CHILD_ARGUMENTS'] = ($Arguments | ForEach-Object { ConvertTo-BillArgument $_ }) -join ' '
        $process = [System.Diagnostics.Process]::Start($psi)
        $record = [ordered]@{ workspace = $Global:BILL_REPO_ROOT; process_id = $process.Id;
            started_ticks = [string]$process.StartTime.ToUniversalTime().Ticks; executable = $psi.FileName }
        try { $record | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8 }
        catch {
            Stop-BillProcessTree $process
            throw "Unable to save $Name process state; launch was stopped."
        }
        return $process
    } finally { $runtimeLock.Dispose() }
}

function Stop-BillProcessTree {
    param([Parameter(Mandatory)][System.Diagnostics.Process]$Process)
    # Capture descendants before terminating the supervisor. Never select by image or window title.
    $snapshot = @(Get-CimInstance Win32_Process)
    $root = $snapshot | Where-Object ProcessId -eq $Process.Id | Select-Object -First 1
    if (-not $root -or -not $root.CreationDate -or
        [Math]::Abs(($Process.StartTime.ToUniversalTime() - $root.CreationDate.ToUniversalTime()).TotalMilliseconds) -ge 1) { return }
    $ids = @([int]$Process.Id)
    for ($index = 0; $index -lt $ids.Count; $index++) {
        $parent = $snapshot | Where-Object ProcessId -eq $ids[$index] | Select-Object -First 1
        # An old orphan can retain a parent PID later reused by this host.
        $ids += @($snapshot | Where-Object {
            $_.ParentProcessId -eq $ids[$index] -and $_.ProcessId -notin $ids -and
            $_.CreationDate -and $_.CreationDate -ge $parent.CreationDate
        } | ForEach-Object { [int]$_.ProcessId })
    }
    [array]::Reverse($ids)
    foreach ($processId in $ids) {
        $entry = $snapshot | Where-Object ProcessId -eq $processId | Select-Object -First 1
        $current = Get-Process -Id $processId -ErrorAction SilentlyContinue
        # CIM's timestamps have microsecond precision; Process.StartTime has 100ns precision.
        if ($current -and $entry -and $entry.CreationDate -and $current.StartTime -and [Math]::Abs(($current.StartTime.ToUniversalTime() - $entry.CreationDate.ToUniversalTime()).TotalMilliseconds) -lt 1) {
            try { Stop-Process -Id $processId -Force -ErrorAction Stop }
            catch {
                # A descendant may exit between lookup and stop; preserve real stop failures.
                if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { throw }
            }
        }
    }
}

function Stop-BillComponent {
    param([Parameter(Mandatory)][string]$Name, [int]$Port, [string]$HostName = '127.0.0.1')
    $runtimeLock = Enter-BillRuntimeLock $Name
    try {
        $process = Get-BillManagedProcess $Name -ForGracefulStop:($Name -notin @('nginx', 'redis'))
        $statePath = Get-BillRuntimePath $Name
        $stopPath = Join-Path (Split-Path -Parent $statePath) "$Name.stop"
        if (-not $process) {
            if ($Port -gt 0 -and (Wait-ForPort -HostName $HostName -Port $Port -TimeoutSeconds 1)) {
                throw "$Name port $Port is owned outside this launcher; it was left untouched."
            }
            foreach ($path in @($statePath, $stopPath)) {
                if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction Stop }
            }
            Write-BillLog "$Name already stopped" 'SKIP'
            return
        }
        if ($Name -eq 'nginx') {
            $root = Get-BillNginxRoot
            $pidFile = Join-Path $root 'logs\nginx.pid'
            if (-not (Test-Path -LiteralPath $pidFile)) { throw 'nginx PID file missing; stop refused until its ownership can be verified.' }
            $masterId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
            $master = Get-CimInstance Win32_Process -Filter "ProcessId=$masterId"
            if (-not $master -or $master.ParentProcessId -ne $process.Id -or $master.ExecutablePath -ne (Join-Path $root 'nginx.exe')) {
                throw 'nginx PID file does not identify the managed master; it was left untouched.'
            }
            $ok = Invoke-BillCommand -FilePath (Join-Path $root 'nginx.exe') -Arguments @('-p', (($root -replace '\\', '/') + '/'), '-c', 'conf/nginx.conf', '-s', 'quit') -WorkingDirectory $root
            if (-not $ok) { Write-BillLog 'nginx graceful quit failed; stopping only its managed process tree.' 'WARN' }
        } elseif ($Name -eq 'redis') {
            $cli = Join-Path $Global:BILL_WIN_ROOT 'bin\redis\redis-cli.exe'
            # Check listener ownership before an endpoint-based shutdown command.
            $listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
            $ownedIds = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $process.Id } | ForEach-Object ProcessId)
            if ($listener.Count -gt 0 -and @($listener | Where-Object { $_.OwningProcess -notin $ownedIds }).Count -eq 0) {
                [void](Invoke-BillCommand -FilePath $cli -Arguments @('-h', $HostName, '-p', [string]$Port, 'SHUTDOWN', 'NOSAVE'))
            } elseif ($listener.Count -gt 0) { throw 'Redis listener ownership changed; it was left untouched.' }
        } else {
            # service-host.py asks Uvicorn to finish active requests and run lifespan shutdown.
            Set-Content -LiteralPath $stopPath -Value 'stop' -Encoding ASCII
        }
        if (-not $process.WaitForExit(15000)) {
            Write-BillLog "$Name did not stop within 15s; stopping its managed process tree." 'WARN'
            # Revalidate identity before the fallback.
            $current = Get-BillManagedProcess $Name
            if ($current) { Stop-BillProcessTree $current }
            if (-not $process.WaitForExit(5000)) { throw "$Name did not stop." }
        }
        if ($Port -gt 0 -and (Wait-ForPort -HostName $HostName -Port $Port -TimeoutSeconds 1)) { throw "$Name port $Port remains occupied after stop." }
        Remove-Item -LiteralPath $statePath -Force
        if (Test-Path -LiteralPath $stopPath) { Remove-Item -LiteralPath $stopPath -Force -ErrorAction Stop }
        Write-BillLog "$Name stopped" 'OK'
    } finally { $runtimeLock.Dispose() }
}
