$winRoot = Split-Path -Parent $PSScriptRoot

Describe 'Audit recovery during degraded API startup' {
    It 'starts configured audit delivery and still returns failure when an API is unready' {
        $fixture = Join-Path $TestDrive 'services-recovery'
        New-Item -ItemType Directory -Path (Join-Path $fixture 'lib') -Force | Out-Null
        Copy-Item (Join-Path $winRoot 'start-services.ps1') $fixture
        Set-Content (Join-Path $fixture 'lib/_common.ps1') @'
$Global:BILL_WIN_ROOT = Split-Path -Parent $PSScriptRoot
$Global:BILL_ENV_DIR = Join-Path $Global:BILL_WIN_ROOT 'env'
function Get-BillConfig { return @{services=@()} }
function Write-BillLog { param($Message, $Level) }
function Read-BillEnvironment { param($Path) @{IDENTITY_SOURCE_BROKER_URL='configured';CATALOG_IDENTITY_SOURCE='configured'} }
'@
        Set-Content (Join-Path $fixture 'lib/runtime.ps1') '# No API processes in fixture.'
        Set-Content (Join-Path $fixture 'lib/health-check.ps1') @'
function Get-BillHealth { param($Config, [switch]$ApiOnly) [pscustomobject]@{Status='DEGRADED'} }
function Write-BillHealth { param($Rows) }
'@
        Set-Content (Join-Path $fixture 'lib/delivery-workers.ps1') @'
function Get-BillDeliveryWorkers { param($Vouchers, $Accounting) }
'@
        Set-Content (Join-Path $fixture 'lib/audit-workers.ps1') @'
function Update-BillAuditContractsForStart { Add-Content (Join-Path $Global:BILL_WIN_ROOT 'calls.txt') 'prepare' }
function Get-BillAuditWorkers { param($EnvDirectory) 'audit-consumer'; 'design-publisher' }
'@
        Set-Content (Join-Path $fixture 'report-workers.ps1') 'param($Action); exit 0'
        Set-Content (Join-Path $fixture 'audit-workers.ps1') @'
param($Action, $Worker)
Add-Content (Join-Path $PSScriptRoot 'calls.txt') ($Action + ':' + $Worker)
exit 0
'@
        foreach ($script in @('reference-sync', 'account-review', 'tax-review')) {
            Set-Content (Join-Path $fixture ($script + '.ps1')) (
                'param($Action); Add-Content (Join-Path $PSScriptRoot ''calls.txt'') ''' + $script + '''; exit 0'
            )
        }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'start-services.ps1') -TimeoutSeconds 1
        $LASTEXITCODE | Should Be 1
        Test-Path (Join-Path $fixture 'calls.txt') | Should Be $true
        (@(Get-Content (Join-Path $fixture 'calls.txt')) -join ',') | Should Be 'prepare,start:audit-consumer,start:design-publisher,reference-sync,account-review,tax-review,start:identity-catalog-publisher,start:catalog-identity-source'
    }
}
