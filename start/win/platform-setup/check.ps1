[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\_common.ps1')
. (Join-Path $PSScriptRoot '..\lib\runtime.ps1')
$values = Read-BillEnvironment (Join-Path $Global:BILL_REPO_ROOT 'mfes\apps\auth\.env.local')
$origin = [Uri]$values.NEXTAUTH_URL
if ($origin.Scheme -notin @('http', 'https') -or $origin.UserInfo -or
    ($origin.Scheme -eq 'http' -and -not $origin.IsLoopback)) { throw 'Invalid Auth setup origin.' }
$endpoint = $origin.GetLeftPart([UriPartial]::Authority) + '/api/setup'
$state = Invoke-RestMethod -Uri $endpoint -TimeoutSec 15
if ($state.completed) { Write-Output 'Platform setup has completed and is closed.'; exit 0 }
if (-not $state.available) { throw 'Setup is unavailable. Check Identity migration/defaults and existing tenants.' }
$setupKey = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'setup-key.txt')).Trim()
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = @{action='unlock'; key=$setupKey} | ConvertTo-Json -Compress
$null = Invoke-RestMethod -Uri $endpoint -Method Post -ContentType 'application/json' -Body $body `
    -Headers @{Origin=$origin.GetLeftPart([UriPartial]::Authority)} -WebSession $session -TimeoutSec 15
$checks = Invoke-RestMethod -Uri ($endpoint + '?action=checks') -WebSession $session -TimeoutSec 30
$checks.checks | Select-Object name, status, message | Format-Table -AutoSize
if (-not $checks.ready) { throw 'Required setup connections need attention.' }
Write-Output 'Setup connections are ready. Continue in the browser to authenticate the intended administrator.'
