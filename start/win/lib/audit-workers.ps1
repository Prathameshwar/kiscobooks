function Get-BillAuditWorkers {
    param([Parameter(Mandatory)][string]$EnvDirectory)
    $configured = @()
    foreach ($service in @('identity','catalog','accounting','vouchers','reports','notification','design','audit')) {
        $file = if ($service -eq 'audit') { 'audit-publisher.env' } else { $service + '.env' }
        $path = Join-Path $EnvDirectory $file
        if (!(Test-Path -LiteralPath $path)) { continue }
        $values = Read-BillEnvironment $path
        $key = if ($service -eq 'audit') { 'AUDIT_PUBLISHER_BROKER_URL' } else { $service.ToUpperInvariant() + '_AUDIT_BROKER_URL' }
        if ($values[$key]) { $configured += $service + '-publisher' }
    }
    $auditFile = Join-Path $EnvDirectory 'audit.env'
    if (Test-Path -LiteralPath $auditFile) {
        $values = Read-BillEnvironment $auditFile
        if ($values['AUDIT_BROKER_URL'] -and $values['AUDIT_SOURCE_CREDENTIALS']) { 'audit-consumer' }
    }
    $configured
}

function Update-BillAuditContractsForStart {
    # Only refresh an already configured pipeline. Native contracts stay explicit;
    # audit-prepare preserves signing identities and historical privacy cutoffs.
    $path = Join-Path $Global:BILL_ENV_DIR 'audit.env'
    if (!(Test-Path -LiteralPath $path)) { return }
    $before = Read-BillEnvironment $path
    if (!$before['AUDIT_BROKER_URL'] -or !$before['AUDIT_SOURCE_CREDENTIALS']) { return }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Global:BILL_WIN_ROOT 'audit-prepare.ps1') -EnvDirectory $Global:BILL_ENV_DIR
    if ($LASTEXITCODE -ne 0) { throw 'Audit contract synchronization failed; review private configuration.' }
    $after = Read-BillEnvironment $path
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $fingerprint = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($after['AUDIT_SOURCE_CREDENTIALS']))).Replace('-', '') }
    finally { $sha.Dispose() }
    $stamp = Join-Path $Global:BILL_WIN_ROOT 'runtime/audit-contracts.sha256'
    if ((Test-Path -LiteralPath $stamp) -and (Get-Content -LiteralPath $stamp -Raw).Trim() -ceq $fingerprint) { return }
    # Running workers retain their old allowlists. Stop producers first; the caller
    # then uses Get-BillAuditWorkers to start the refreshed consumer before producers.
    $workers = @(Get-BillAuditWorkers -EnvDirectory $Global:BILL_ENV_DIR)
    [array]::Reverse($workers)
    foreach ($worker in $workers) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Global:BILL_WIN_ROOT 'audit-workers.ps1') -Action stop -Worker $worker
        if ($LASTEXITCODE -ne 0) { throw ('Could not reload changed audit contracts: ' + $worker) }
    }
    # Commit the reload marker only after every stop succeeds. A crash/failure after
    # configuration was written must still force reload on the next startup.
    New-Item -ItemType Directory -Path (Split-Path -Parent $stamp) -Force | Out-Null
    Set-Content -LiteralPath $stamp -Value $fingerprint -Encoding ASCII
    Write-BillLog 'Audit contracts changed; delivery workers will reload the explicit allowlists.' 'INFO'
}

function Format-BillAuditDeliveryDetail {
    param([Parameter(Mandatory)]$States, [int]$Missing)
    $producers = @($States | Where-Object { $_.service -ne 'broker' })
    $pending = ($producers | Where-Object { $_.PSObject.Properties['pending'] } | Measure-Object -Property pending -Sum).Sum
    $exhausted = ($producers | Where-Object { $_.PSObject.Properties['exhausted'] } | Measure-Object -Property exhausted -Sum).Sum
    $unconfigured = @($producers | Where-Object { !$_.configured } | ForEach-Object service)
    $stalled = @($producers | Where-Object { $_.PSObject.Properties['oldest_age_seconds'] -and $_.oldest_age_seconds -gt 300 } | ForEach-Object service)
    $broker = @($States | Where-Object { $_.service -eq 'broker' })[0].broker
    $detail = 'pending={0}; exhausted={1}; unconfigured={2}' -f $pending,$exhausted,$unconfigured.Count
    if ($unconfigured.Count) { $detail += ' (' + ($unconfigured -join ',') + ')' }
    if ($stalled.Count) { $detail += '; stalled=' + ($stalled -join ',') }
    $detail += '; stopped workers=' + $Missing
    $detail += $(if ($broker.ready) { '; broker ready' } else { '; broker delivery unhealthy; inspect delivery_state.py --broker' })
    return $detail
}

function Get-BillAuditHealth {
    . (Join-Path $Global:BILL_WIN_ROOT 'lib/runtime.ps1')
    $missing = 0
    foreach ($worker in @(Get-BillAuditWorkers -EnvDirectory $Global:BILL_ENV_DIR)) {
        try {
            $state = & (Join-Path $Global:BILL_WIN_ROOT 'audit-workers.ps1') -Action status -Worker $worker
            if (!$state.Running) { $missing++ }
        } catch { $missing++ }
    }
    $python = Join-Path $Global:BILL_REPO_ROOT 'apis/audit/.venv/Scripts/python.exe'
    $tool = Join-Path $Global:BILL_REPO_ROOT 'apis/audit/tools/delivery_state.py'
    try {
        $json = @(& $python $tool --broker)
        $ok = $LASTEXITCODE -eq 0 -and $missing -eq 0
        $states = $json -join '' | ConvertFrom-Json
        $detail = Format-BillAuditDeliveryDetail -States $states -Missing $missing
    } catch { $ok = $false; $detail = 'Audit delivery inventory unavailable; review private configuration.' }
    [pscustomobject]@{Component='Audit delivery';Endpoint='outbox/broker workers';Status=$(if($ok){'UP'}else{'DEGRADED'});Kind='worker';Detail=$detail}
}
