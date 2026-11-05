# Start all registry APIs, injecting environment values without shell evaluation.
[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateRange(1, 120)][int]$TimeoutSeconds = 45)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\health-check.ps1')
$cfg = Get-BillConfig
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { Write-BillLog 'uv is missing. Run setup.bat first.' 'ERROR'; exit 1 }
$failed = 0
foreach ($svc in $cfg.services) {
    $code = [string]$svc.code
    try {
        $project = Join-Path $Global:BILL_REPO_ROOT ([string]$svc.project)
        if (-not (Test-Path -LiteralPath (Join-Path $project '.venv\Scripts\python.exe'))) {
            throw "Missing Python environment for $code. Run setup.bat -Component python."
        }
        if (Get-BillManagedProcess $code -ForStart) { Write-BillLog "$code already launched; checking readiness" 'SKIP'; continue }
        if (Wait-ForPort -HostName '127.0.0.1' -Port $svc.port -TimeoutSeconds 1) {
            throw "$code port $($svc.port) is occupied outside this launcher."
        }
        $values = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR "$code.env")
        if (-not $PSCmdlet.ShouldProcess($code, 'Start API process')) { continue }
        [void](Start-BillProcess -Name $code -Executable $uv.Source -Environment $values -Arguments @(
            'run', '--no-sync', '--project', $project, 'python', (Join-Path $PSScriptRoot 'service-host.py'), '--code', $code
        ))
        Write-BillLog "$code launch requested; logs/$code.stderr.log" 'INFO'
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
if (-not $WhatIfPreference) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $rows = @(Get-BillHealth -Config $cfg -ApiOnly)
        if (@($rows | Where-Object Status -ne 'UP').Count -eq 0 -or (Get-Date) -ge $deadline) { break }
        Start-Sleep -Milliseconds 500
    } while ($true)
    Write-BillHealth $rows
    if (@($rows | Where-Object Status -ne 'UP').Count -gt 0) { $failed++ }
}
# Retained execution and first-use confirmation must recover even when a different
# API is not ready. Starting these workers does not enable new posting admission.
if (-not $WhatIfPreference) {
    . (Join-Path $PSScriptRoot 'lib/delivery-workers.ps1')
    $deliveryVouchers = @{}
    $deliveryAccounting = @{}
    foreach ($deliveryService in @('vouchers', 'accounting')) {
        $deliveryFile = Join-Path $Global:BILL_ENV_DIR ($deliveryService + '.env')
        if (Test-Path -LiteralPath $deliveryFile) {
            if ($deliveryService -eq 'vouchers') { $deliveryVouchers = Read-BillEnvironment $deliveryFile }
            else { $deliveryAccounting = Read-BillEnvironment $deliveryFile }
        }
    }
    foreach ($worker in @(Get-BillDeliveryWorkers -Vouchers $deliveryVouchers -Accounting $deliveryAccounting)) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'audit-workers.ps1') -Action start -Worker $worker
        if ($LASTEXITCODE -ne 0) { Write-BillLog ('Delivery worker could not start: ' + $worker) 'ERROR'; $failed++ }
    }
    # Report source/calculate/export lanes are selected only by their explicit configuration.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'report-workers.ps1') -Action start
    if ($LASTEXITCODE -ne 0) { Write-BillLog 'Report workers could not start; review their private configuration.' 'ERROR'; $failed++ }
    # Existing outboxes must drain even when an unrelated API needs a migration.
    try {
        . (Join-Path $PSScriptRoot 'lib/audit-workers.ps1')
        Update-BillAuditContractsForStart
        foreach ($worker in @(Get-BillAuditWorkers -EnvDirectory $Global:BILL_ENV_DIR)) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'audit-workers.ps1') -Action start -Worker $worker
            if ($LASTEXITCODE -ne 0) { throw ('Audit worker could not start: ' + $worker) }
        }
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
# Company setup depends on these workers even when an unrelated API is degraded.
if (-not $WhatIfPreference) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'reference-sync.ps1') -Action start
    if ($LASTEXITCODE -ne 0) { $failed++ }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'account-review.ps1') -Action start
    if ($LASTEXITCODE -ne 0) { $failed++ }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'tax-review.ps1') -Action start
    if ($LASTEXITCODE -ne 0) { $failed++ }
    $identityValues = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'identity.env')
    $catalogValues = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'catalog.env')
    if ($identityValues['IDENTITY_SOURCE_BROKER_URL'] -and $catalogValues['CATALOG_IDENTITY_SOURCE']) {
        foreach ($worker in @('identity-catalog-publisher', 'catalog-identity-source')) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'audit-workers.ps1') -Action start -Worker $worker
            if ($LASTEXITCODE -ne 0) { $failed++ }
        }
    }

}
if ($failed) { exit 1 }
exit 0
