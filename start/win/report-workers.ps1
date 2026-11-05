[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('start','stop','status')][string]$Action = 'status',
    [ValidateSet('all','identity-company-setup','accounting-report-snapshots','reports-sources','reports-dispatcher','reports-short','reports-bulk','reports-render')][string]$Worker = 'all'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/_common.ps1')
. (Join-Path $PSScriptRoot 'lib/runtime.ps1')
. (Join-Path $PSScriptRoot 'lib/report-workers.ps1')
$names = @('identity-company-setup','accounting-report-snapshots','reports-sources','reports-dispatcher','reports-short','reports-bulk','reports-render')
if ($Action -ne 'start') {
    foreach ($name in $names) {
        if ($Worker -ne 'all' -and $Worker -ne $name) { continue }
        if ($Action -eq 'stop') {
            if ($PSCmdlet.ShouldProcess($name, 'Stop report worker')) { Stop-BillComponent -Name $name }
        } else {
            [pscustomobject]@{Worker=$name; Running=($null -ne (Get-BillManagedProcess -Name $name))}
        }
    }
    return
}
$reports = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'reports.env')
$accounting = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'accounting.env')
$identity = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'identity.env')
# Materialize/validate the entire selection before starting any process.
$definitions = @(Get-BillReportWorkers -Reports $reports -Accounting $accounting -Identity $identity)
if (!$definitions.Count) { Write-Output 'Report execution admission is disabled; no workers requested.'; return }
foreach ($definition in $definitions) {
    if ($Worker -ne 'all' -and $Worker -ne $definition.Name) { continue }
    if (Get-BillManagedProcess -Name $definition.Name -ForStart) {
        Write-Output ('Already running: ' + $definition.Name)
        continue
    }
    $environment = switch ($definition.Environment) { 'reports' { $reports }; 'identity' { $identity }; default { $accounting } }
    $project = Join-Path $Global:BILL_REPO_ROOT ('apis/' + $definition.Project)
    $python = Join-Path $project '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $python)) { throw ('Missing interpreter for ' + $definition.Name) }
    if ($PSCmdlet.ShouldProcess($definition.Name, 'Start report worker')) {
        $process = Start-BillProcess -Name $definition.Name -Executable $python -WorkingDirectory $project -Environment $environment -Arguments (@('-m', $definition.Module) + $definition.Arguments)
        Write-Output ('Started: ' + $definition.Name + ' (managed PID ' + $process.Id + ')')
    }
}
