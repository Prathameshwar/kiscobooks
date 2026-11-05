[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('nginx', 'redis')][string]$Name, [ValidateSet('start', 'stop')][string]$Action)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\health-check.ps1')
try {
    $cfg = Get-BillConfig
    if (-not $PSCmdlet.ShouldProcess($Name, $Action)) { exit 0 }
    if ($Action -eq 'start') { Start-BillInfrastructure -Name $Name -Config $cfg }
    else {
        $port = if ($Name -eq 'nginx') { $cfg.infra.nginx.listen_port } else { $cfg.infra.redis.port }
        $address = if ($Name -eq 'nginx') { '127.0.0.1' } else { $cfg.infra.redis.host }
        Stop-BillComponent -Name $Name -Port $port -HostName $address
    }
    exit 0
} catch { Write-BillLog $_.Exception.Message 'ERROR'; exit 1 }
