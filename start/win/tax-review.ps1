[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('start', 'stop', 'status')][string]$Action = 'start')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
$name = 'catalog-tax-review'
try {
    if ($Action -eq 'status') {
        $state = if (Get-BillManagedProcess $name) { 'RUNNING' } else { 'STOPPED' }
        Write-BillLog "$name $state" 'INFO'
    } elseif ($Action -eq 'stop') {
        if ($PSCmdlet.ShouldProcess($name, 'Stop tax impact review worker')) { Stop-BillComponent -Name $name }
    } elseif (!(Get-BillManagedProcess $name)) {
        $project = Join-Path $Global:BILL_REPO_ROOT 'apis/catalog'
        $values = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'catalog.env')
        if (!$values['CATALOG_IDENTITY_SOURCE'] -or !$values['CATALOG_SOURCE_SUBSCRIPTIONS']) {
            Write-BillLog 'Background tax review is not configured; worker skipped.' 'SKIP'
            exit 0
        }
        $uv = Get-Command uv -ErrorAction Stop
        if ($PSCmdlet.ShouldProcess($name, 'Start tax impact review worker')) {
            [void](Start-BillProcess -Name $name -Executable $uv.Source -Environment $values -Arguments @(
                'run', '--no-sync', '--project', $project, 'python', '-m', 'catalog.tasks.tax_review_worker'
            ))
            Start-Sleep -Milliseconds 500
            if (!(Get-BillManagedProcess $name)) { throw 'Tax review worker exited during startup.' }
            Write-BillLog 'Background tax review worker started.' 'OK'
        }
    }
    exit 0
} catch { Write-BillLog 'Tax review worker lifecycle failed. Inspect its private local configuration and logs.' 'ERROR'; exit 1 }
