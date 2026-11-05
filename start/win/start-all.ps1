[CmdletBinding(SupportsShouldProcess = $true)]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\health-check.ps1')
$cfg = Get-BillConfig
$failed = 0
foreach ($name in @('Authentik tunnel','redis','RabbitMQ','APIs','nginx')) {
    if (-not $PSCmdlet.ShouldProcess($name, 'Start backend component')) { continue }
    try {
        switch ($name) {
            'Authentik tunnel' {
                # Only an installation that chose Authentik has a VM to tunnel to.
                if ((Get-BillAuthProvider) -ne 'authentik') {
                    Write-BillLog 'Local sign-in: no Authentik tunnel is needed.' 'SKIP'
                    continue
                }
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'authentik-vm\tunnel.ps1') -Action start
                if ($LASTEXITCODE -ne 0) { throw 'Authentik SSH tunnel failed. Ensure the VM is running; see logs/authentik-tunnel.stderr.log.' }
            }
            'RabbitMQ' {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'rabbitmq-local.ps1') -Action start
                if ($LASTEXITCODE -ne 0) { throw 'RabbitMQ failed startup.' }
            }
            'APIs' {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-services.ps1')
                if ($LASTEXITCODE -ne 0) { throw 'One or more APIs failed startup/readiness.' }
            }
            default { Start-BillInfrastructure -Name $name -Config $cfg }
        }
    } catch { Write-BillLog $_.Exception.Message 'ERROR'; $failed++ }
}
if ($WhatIfPreference) { exit 0 }
$rows = Get-BillHealth $cfg
Write-BillHealth $rows
if (@($rows | Where-Object Status -ne 'UP').Count -gt 0) { $failed++ }
if ($failed) {
    $unhealthy = @($rows | Where-Object Status -ne 'UP' | ForEach-Object Component)
    $detail = if ($unhealthy.Count) { 'Unhealthy components: ' + ($unhealthy -join ', ') + '. See their checks above.' } else { 'A launch step failed; see its error above.' }
    Write-BillLog ('Startup incomplete. ' + $detail + ' Existing processes were preserved.') 'ERROR'
    exit 1
}
Write-BillLog 'Backend components ready; the Authentik tunnel was started or reused only if Authentik is the sign-in provider. MySQL reports TCP reachability; broker/cache/gateway and API probes passed.' 'OK'
exit 0
