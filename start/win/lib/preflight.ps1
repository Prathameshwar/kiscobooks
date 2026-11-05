# Preflight checks -- verify prerequisites before any mutation.
# Requires _common.ps1 dot-sourced by the caller.

function Invoke-BillPreflight {
    param(
        [Parameter(Mandatory)]$Config
    )
    Write-BillStep 'Preflight'

    $failures = @()

    if ($PSVersionTable.PSVersion.Major -lt 5) {
        $failures += "PowerShell 5.1+ required (found $($PSVersionTable.PSVersion))."
    } else {
        Write-BillLog ("PowerShell {0}" -f $PSVersionTable.PSVersion) 'OK'
    }

    # uv -- the project uses uv for every Python environment.
    if (-not (Test-Command 'uv')) {
        $failures += "uv not on PATH. Install it (winget install astral-sh.uv) and re-open your shell."
    } else {
        Write-BillLog ("uv {0}" -f ((& uv --version 2>&1 | Out-String).Trim())) 'OK'
    }

    # pnpm is only needed for the web MFEs; warn, do not fail.
    if (Test-Command 'pnpm') {
        Write-BillLog ("pnpm {0}" -f ((& pnpm --version 2>&1 | Out-String).Trim())) 'OK'
    } else {
        Write-BillLog "pnpm not on PATH (only needed for start-web; skip if backend-only)." 'WARN'
    }

    # MySQL reachability is advisory: setup can run before the DB is up, but the
    # services will not boot until it is.
    $mysql = $Config.infra.mysql
    if (Wait-ForPort -HostName $mysql.host -Port ([int]$mysql.port) -TimeoutSeconds 3) {
        Write-BillLog "MySQL reachable at $($mysql.host):$($mysql.port)" 'OK'
    } else {
        Write-BillLog "MySQL NOT reachable at $($mysql.host):$($mysql.port). Services will fail to start until it is up." 'WARN'
    }

    if (-not $Config.services -or $Config.services.Count -eq 0) {
        $failures += "services.json parsed but has zero services."
    } else {
        Write-BillLog ("services.json OK ({0} services)" -f $Config.services.Count) 'OK'
    }

    if ($failures.Count -gt 0) {
        Write-Host ""
        Write-BillLog "Preflight failed:" 'ERROR'
        foreach ($f in $failures) { Write-BillLog "  - $f" 'ERROR' }
        throw "Preflight failed. See above."
    }

    Write-BillLog "Preflight passed." 'OK'
}
