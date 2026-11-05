[CmdletBinding(SupportsShouldProcess = $true)]
param([Parameter(Position = 0)][ValidateSet('all', 'auth', 'console')][string]$App = 'all')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\web.ps1')
$failed = $false
$lifecycleLock = $null
try {
    if (-not $WhatIfPreference) { $lifecycleLock = Enter-BillRuntimeLock 'web-lifecycle' }
    foreach ($target in @(Get-BillWebApps $App)) {
        if (-not $PSCmdlet.ShouldProcess($target.Name, 'Stop UI development server')) { continue }
        try { Stop-BillWebApp $target }
        catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed = $true }
    }
} catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed = $true }
finally { if ($lifecycleLock) { $lifecycleLock.Dispose() } }
if ($failed) { Write-BillLog 'UI shutdown incomplete; see the component errors above.' 'ERROR'; exit 1 }
if (-not $WhatIfPreference) { Write-BillLog 'All selected launcher-managed UI servers stopped.' 'OK' }
exit 0
