# Lifecycle of the two service-local reference delivery workers.
[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('start', 'stop', 'status')][string]$Action = 'status')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
$failed = 0
foreach ($service in @('catalog', 'accounting')) {
    $name = "$service-reference-sync"
    try {
        if ($Action -eq 'status') {
            $state = if (Get-BillManagedProcess $name) { 'RUNNING' } else { 'STOPPED' }
            Write-BillLog "$name $state" 'INFO'
        } elseif ($Action -eq 'stop') {
            if ($PSCmdlet.ShouldProcess($name, 'Stop reference delivery worker')) {
                Stop-BillComponent -Name $name
            }
        } else {
            if (Get-BillManagedProcess $name) { Write-BillLog "$name already started" 'SKIP'; continue }
            $values = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR "$service.env")
            if (-not $values.ContainsKey('REFERENCE_SYNC_SECRET') -or
                -not $values.ContainsKey('REFERENCE_SYNC_IDENTITY_URL') -or
                $values['REFERENCE_SYNC_SECRET'].Length -lt 32) {
                throw "$name credentials are missing. Run reference-sync-prepare.ps1."
            }
            $values['REFERENCE_SYNC_SERVICE'] = $service
            $values['REFERENCE_SYNC_STOP_FILE'] = Join-Path $Global:BILL_WIN_ROOT "runtime\$name.stop"
            $project = Join-Path $Global:BILL_REPO_ROOT "apis\$service"
            $python = Join-Path $project '.venv\Scripts\python.exe'
            if (-not (Test-Path -LiteralPath $python)) { throw "$service Python environment is missing." }
            if ($PSCmdlet.ShouldProcess($name, 'Start reference delivery worker')) {
                [void](Start-BillProcess -Name $name -Executable $python -WorkingDirectory $project `
                    -Environment $values -Arguments @('-m', 'billing_platform.reference.worker'))
                Start-Sleep -Milliseconds 300
                if (-not (Get-BillManagedProcess $name)) { throw "$name exited; check its stderr log." }
                Write-BillLog "$name started" 'OK'
            }
        }
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
if ($failed) { exit 1 }
exit 0
