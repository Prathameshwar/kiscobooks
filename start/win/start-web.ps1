# Start detached, workspace-owned Next.js development servers.
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Position = 0)][ValidateSet('all', 'auth', 'console')][string]$App = 'all',
    [ValidateRange(1, 180)][int]$TimeoutSeconds = 60
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\web.ps1')
$started = @()
$lifecycleLock = $null
$failed = $false
try {
    $targets = @(Get-BillWebApps $App)
    if ($WhatIfPreference) {
        foreach ($target in $targets) { [void]$PSCmdlet.ShouldProcess($target.Name, 'Start UI development server') }
    } else {
        # Serialize installation, probes and rollback as well as process launches.
        $lifecycleLock = Enter-BillRuntimeLock 'web-lifecycle'
        foreach ($target in $targets) {
            if (-not (Get-BillManagedProcess $target.Name) -and
                (Wait-ForPort -HostName '127.0.0.1' -Port $target.Port -TimeoutSeconds 1)) {
                throw "$($target.Name) port $($target.Port) is occupied outside this launcher."
            }
        }
        $node = Get-BillWebNode
        if (@($targets | Where-Object { -not (Test-Path -LiteralPath $_.Cli) }).Count -gt 0) {
            if ($PSCmdlet.ShouldProcess('mfes', 'Install locked UI dependencies')) { Install-BillWebDependencies }
        }
        foreach ($target in $targets) {
            if (Get-BillManagedProcess $target.Name) {
                Write-BillLog "$($target.Name) already launched; checking web-server readiness" 'SKIP'
            } elseif ($PSCmdlet.ShouldProcess($target.Name, 'Start UI development server')) {
                Start-BillWebApp -Target $target -Node $node
                $started += $target
            }
        }
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        do {
            $rows = @($targets | ForEach-Object { Get-BillWebStatus $_ })
            if (@($rows | Where-Object Status -ne 'UP').Count -eq 0) { break }
            if (@($rows | Where-Object Status -in @('EXITED', 'EXTERNAL', 'ERROR')).Count -gt 0) { break }
            if ((Get-Date) -ge $deadline) { break }
            Start-Sleep -Milliseconds 500
        } while ($true)
        Write-BillWebStatus $rows
        if (@($rows | Where-Object Status -ne 'UP').Count -gt 0) {
            throw 'UI startup failed. See logs/web-<app>.stdout.log and .stderr.log.'
        }
        Write-BillLog 'Web servers ready. Sign-in and business pages also require the sign-in provider and API settings; see README.md.' 'OK'
    }
} catch {
    $failed = $true
    Write-BillLog $_.Exception.Message 'ERROR'
    # Roll back this invocation's launches while preserving pre-existing servers.
    foreach ($target in $started) {
        try { Stop-BillWebApp $target }
        catch { Write-BillLog "Rollback failed for $($target.Name): $($_.Exception.Message)" 'ERROR' }
    }
} finally { if ($lifecycleLock) { $lifecycleLock.Dispose() } }
if ($failed) { exit 1 }
exit 0
