[CmdletBinding(SupportsShouldProcess = $true)]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
$cfg = Get-BillConfig
$failed = 0
$workerStops = @(
    @{Name='Report and company setup workers'; Script='report-workers.ps1'; Arguments=@('-Worker','all')},
    @{Name='Delivery workers'; Script='audit-workers.ps1'; Arguments=@('-Worker','all')},
    @{Name='Account review'; Script='account-review.ps1'; Arguments=@()},
    @{Name='Tax impact review'; Script='tax-review.ps1'; Arguments=@()},
    @{Name='Reference delivery'; Script='reference-sync.ps1'; Arguments=@()}
)
foreach ($worker in $workerStops) {
    if (-not $PSCmdlet.ShouldProcess($worker.Name, 'Stop owned background workers')) { continue }
    try {
        $arguments = $worker.Arguments
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $worker.Script) -Action stop @arguments
        if ($LASTEXITCODE -ne 0) { throw "$($worker.Name) stop failed." }
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
# Stop gateway traffic, then APIs, then cache/broker. MySQL is separately managed.
$targets = @([pscustomobject]@{code='nginx'; port=$cfg.infra.nginx.listen_port; host='127.0.0.1'})
$targets += @($cfg.services | ForEach-Object { [pscustomobject]@{code=$_.code; port=$_.port; host='127.0.0.1'} })
$targets += [pscustomobject]@{code='redis'; port=$cfg.infra.redis.port; host=$cfg.infra.redis.host}
foreach ($target in $targets) {
    if (-not $PSCmdlet.ShouldProcess($target.code, 'Stop workspace runtime')) { continue }
    try { Stop-BillComponent -Name $target.code -Port $target.port -HostName $target.host }
    catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
if ($PSCmdlet.ShouldProcess('RabbitMQ', 'Stop local node')) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'rabbitmq-local.ps1') -Action stop
        if ($LASTEXITCODE -ne 0) { throw 'Local RabbitMQ stop failed.' }
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
Write-Host 'MySQL was left running.'
Write-Host 'UI servers and the Authentik VM/tunnel are managed separately.'
if ($failed) { Write-BillLog "$failed component(s) could not be stopped; see above." 'ERROR'; exit 1 }
if ($WhatIfPreference) { exit 0 }
Write-BillLog 'All launcher-managed backend components stopped.' 'OK'
exit 0
