[CmdletBinding()]
param([Parameter(Position = 0)][ValidateSet('all', 'auth', 'console')][string]$App = 'all')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\web.ps1')
try {
    $rows = @(Get-BillWebApps $App | ForEach-Object { Get-BillWebStatus $_ })
    Write-BillWebStatus $rows
    if (@($rows | Where-Object Status -ne 'UP').Count -gt 0) { exit 1 }
    exit 0
} catch { Write-BillLog $_.Exception.Message 'ERROR'; exit 1 }
