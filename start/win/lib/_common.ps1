# Shared helpers for the Bill dev-env scripts. Dot-sourced by every step in lib\.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Paths + globals
# ---------------------------------------------------------------------------

$Global:BILL_WIN_ROOT  = Split-Path -Parent $PSScriptRoot
$Global:BILL_REPO_ROOT = (Get-Item $Global:BILL_WIN_ROOT).Parent.Parent.FullName
$Global:BILL_LOG_DIR   = Join-Path $Global:BILL_WIN_ROOT 'logs'
$Global:BILL_CONF_DIR  = Join-Path $Global:BILL_WIN_ROOT 'conf'
$Global:BILL_ENV_DIR   = Join-Path $Global:BILL_WIN_ROOT 'env'

if (-not (Test-Path $Global:BILL_LOG_DIR)) {
    New-Item -ItemType Directory -Path $Global:BILL_LOG_DIR -Force | Out-Null
}

$Global:BILL_LOG_FILE = Join-Path $Global:BILL_LOG_DIR (
    'setup-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss')
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

function Write-BillLog {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'OK', 'SKIP', 'STEP')][string]$Level = 'INFO'
    )
    $ts = Get-Date -Format 'HH:mm:ss'
    $line = "[{0}] [{1,-5}] {2}" -f $ts, $Level, $Message

    Add-Content -Path $Global:BILL_LOG_FILE -Value $line

    $color = switch ($Level) {
        'INFO'  { 'Gray' }
        'WARN'  { 'Yellow' }
        'ERROR' { 'Red' }
        'OK'    { 'Green' }
        'SKIP'  { 'DarkGray' }
        'STEP'  { 'Cyan' }
        default { 'White' }
    }
    Write-Host $line -ForegroundColor $color
}

function Write-BillStep {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host ""
    Write-BillLog "=== $Message ===" 'STEP'
}

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

function Test-Command {
    param([Parameter(Mandatory)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $client = $null
        try {
            $client = New-Object Net.Sockets.TcpClient
            $iar = $client.BeginConnect($HostName, $Port, $null, $null)
            if ($iar.AsyncWaitHandle.WaitOne(1000, $false) -and $client.Connected) {
                $client.EndConnect($iar)
                return $true
            }
        } catch { } finally {
            if ($client) { $client.Close() }
        }
        if ((Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-BillConfig {
    $path = Join-Path $Global:BILL_CONF_DIR 'services.json'
    if (-not (Test-Path $path)) {
        throw "services.json not found at $path"
    }
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    $codes = @(); $ports = @()
    foreach ($service in $config.services) {
        if ($service.code -notmatch '^[a-z][a-z0-9-]*$' -or $service.code -in $codes) { throw 'Invalid or duplicate service code.' }
        if ($service.port -lt 1 -or $service.port -gt 65535 -or $service.port -in $ports) { throw 'Invalid or duplicate API port.' }
        if ($service.module -notmatch '^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$') { throw 'Invalid service factory module.' }
        $projectPath = [IO.Path]::GetFullPath((Join-Path $Global:BILL_REPO_ROOT ([string]$service.project)))
        if (-not $projectPath.StartsWith($Global:BILL_REPO_ROOT + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Service project must stay inside this workspace.'
        }
        $codes += $service.code; $ports += $service.port
    }
    return $config
}

function Assert-BillChildPath {
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Root)
    $resolved = [IO.Path]::GetFullPath($Path)
    $parent = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    if (-not $resolved.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Filesystem target must be a child of its intended root.'
    }
    # Refuse junction/symlink traversal for setup's recursive removals and moves.
    $cursor = $resolved
    while ($cursor -and $cursor.StartsWith($parent, [StringComparison]::OrdinalIgnoreCase)) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Setup target traverses a junction or symbolic link.'
        }
        if ($cursor -eq $parent) { break }
        $cursor = Split-Path -Parent $cursor
    }
}

function New-BillSecret {
    <#
    A URL-safe base64 secret of at least 32 characters. Used for the dev
    signing/encryption keys written into start\win\env\<code>.env. These are
    development-only values; production secrets come from the secret manager
    (CLAUDE.md 5.9), never this repo.
    #>
    param([int]$Bytes = 48)
    $buffer = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-BillHexKey {
    # 32 random bytes, hex-encoded -- the format accounting's encryption_key
    # validator expects (32 hex-encoded bytes).
    param([int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    return -join ($buffer | ForEach-Object { $_.ToString('x2') })
}

function Invoke-BillCommand {
    <#
    Runs a native command, captures stdout+stderr, logs everything.
    Returns $true on exit code 0. Never throws unless -ThrowOnFailure.
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = $null,
        [hashtable]$EnvironmentOverrides = $null,
        [switch]$ThrowOnFailure
    )
    Write-BillLog ("run: {0} {1}" -f $FilePath, ($Arguments -join ' ')) 'INFO'

    $quoted = foreach ($a in $Arguments) {
        if ($a -match '[\s"]') {
            $esc = ($a -replace '"', '\"')
            '"' + $esc + '"'
        } else { $a }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $FilePath
    $psi.Arguments              = ($quoted -join ' ')
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    if ($WorkingDirectory) { $psi.WorkingDirectory = $WorkingDirectory }

    # PS 5.1's ProcessStartInfo.Environment can be null. Apply overrides to the
    # parent process only for Start(), then restore; the child inherits its own
    # copy at that point.
    $previousEnvironment = @{}
    if ($EnvironmentOverrides) {
        foreach ($k in $EnvironmentOverrides.Keys) {
            $envName = [string]$k
            $previousEnvironment.Add(
                $envName,
                [System.Environment]::GetEnvironmentVariable($envName, 'Process')
            )
            [System.Environment]::SetEnvironmentVariable(
                $envName, [string]$EnvironmentOverrides.Item($k), 'Process'
            )
        }
    }
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } finally {
        foreach ($k in $previousEnvironment.Keys) {
            [System.Environment]::SetEnvironmentVariable(
                [string]$k, $previousEnvironment.Item($k), 'Process'
            )
        }
    }
    # Drain both pipes concurrently to avoid a full-buffer deadlock.
    $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
    $stderrTask = $proc.StandardError.ReadToEndAsync()
    $proc.WaitForExit()
    [System.Threading.Tasks.Task]::WaitAll(
        [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
    )
    $stdout = [string]$stdoutTask.GetAwaiter().GetResult()
    $stderr = [string]$stderrTask.GetAwaiter().GetResult()

    if ($stdout) { Add-Content -Path $Global:BILL_LOG_FILE -Value $stdout }
    if ($stderr) { Add-Content -Path $Global:BILL_LOG_FILE -Value $stderr }

    if ($proc.ExitCode -ne 0) {
        $errLines = @()
        foreach ($ln in ($stderr -split "`r?`n")) {
            if ($ln.Trim() -eq '') { continue }
            $errLines += $ln
            if ($errLines.Count -ge 5) { break }
        }
        if (-not $errLines) { $errLines = @('(no error text; check full log file)') }
        Write-BillLog ("exit {0}:" -f $proc.ExitCode) 'WARN'
        foreach ($l in $errLines) { Write-BillLog ("  {0}" -f $l) 'WARN' }
        if ($ThrowOnFailure) {
            throw ("Command failed ({0}): {1} {2}" -f $proc.ExitCode, $FilePath, ($Arguments -join ' '))
        }
        return $false
    }
    return $true
}

# ---------------------------------------------------------------------------
# Summary tracking
# ---------------------------------------------------------------------------

$Global:BILL_SUMMARY = @()

function Add-BillSummary {
    param(
        [Parameter(Mandatory)][string]$Component,
        [ValidateSet('OK', 'SKIP', 'FAIL')][string]$Status,
        [string]$Detail = ''
    )
    $Global:BILL_SUMMARY += [pscustomobject]@{
        Component = $Component
        Status    = $Status
        Detail    = $Detail
    }
}

function Write-BillSummary {
    Write-Host ""
    Write-Host "================== Bill dev-env setup summary ==================" -ForegroundColor Cyan
    foreach ($row in $Global:BILL_SUMMARY) {
        $color = switch ($row.Status) {
            'OK'    { 'Green' }
            'SKIP'  { 'DarkGray' }
            'FAIL'  { 'Red' }
            default { 'White' }
        }
        $line = "  [{0,-4}]  {1,-24} {2}" -f $row.Status, $row.Component, $row.Detail
        Write-Host $line -ForegroundColor $color
    }
    Write-Host ""
    Write-Host ("Log: {0}" -f $Global:BILL_LOG_FILE) -ForegroundColor DarkGray
    Write-Host "===============================================================" -ForegroundColor Cyan
}
