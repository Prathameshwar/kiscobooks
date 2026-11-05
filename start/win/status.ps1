<#
.SYNOPSIS
  Read-only health check for every Bill component.
  Prints a status table. Exit 0 if everything UP, 1 if anything DOWN.

.EXAMPLE
  .\status.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\health-check.ps1')

$cfg  = Get-BillConfig
$rows = Get-BillHealth -Config $cfg
Write-BillHealth -Rows $rows

$down = @($rows | Where-Object { $_.Status -ne 'UP' })
if ($down.Count -gt 0) {
    Write-Host ""
    Write-Host ("{0} component(s) unhealthy. Run .\start\win\start-all.bat to launch them." -f $down.Count) -ForegroundColor Yellow
    exit 1
}
Write-Host ""
Write-Host "All components UP." -ForegroundColor Green
exit 0
