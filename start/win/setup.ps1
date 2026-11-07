<#
.SYNOPSIS
  Bill platform local Windows dev setup: nginx + Redis binaries, per-service uv
  environments, and per-service dev .env files.

.DESCRIPTION
  Idempotent one-shot bootstrap. Re-running only fills gaps. nginx and Redis are
  fetched as SHA-256-verified ZIPs into start\win\bin\ (no service install, no
  admin). Python dependencies are resolved with `uv sync` per service. Dev env
  files are generated once and preserved across runs. After a successful full
  setup, you can optionally provision databases and apply migrations.

  MySQL, RabbitMQ and Azurite are NOT installed here. MySQL is expected to be an
  installed instance; RabbitMQ and Azurite have their own launchers in this
  folder (rabbitmq-local.ps1, azurite-local.ps1). start-all starts RabbitMQ;
  Azurite and background workers are separately managed.

.PARAMETER Component
  Which step(s) to run. Comma-separated: all,nginx,redis,python,envs.

.PARAMETER Recreate
  nginx/redis: remove and re-download. python: remove and rebuild each .venv.
  envs: regenerate .env files (new secrets).

.EXAMPLE
  .\setup.ps1

.EXAMPLE
  .\setup.ps1 -Component python,envs -Recreate
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'nginx', 'redis', 'python', 'envs')]
    [string[]]$Component = @('all'),
    [switch]$Recreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\preflight.ps1')
. (Join-Path $PSScriptRoot 'lib\install-nginx.ps1')
. (Join-Path $PSScriptRoot 'lib\install-redis.ps1')
. (Join-Path $PSScriptRoot 'lib\setup-python.ps1')
. (Join-Path $PSScriptRoot 'lib\write-envs.ps1')
. (Join-Path $PSScriptRoot 'lib\database-setup-prompt.ps1')

Write-Host ""
Write-Host "==================== Bill dev-env setup ====================" -ForegroundColor Cyan
Write-BillLog ("repo root  : {0}" -f $Global:BILL_REPO_ROOT) 'INFO'
Write-BillLog ("log file   : {0}" -f $Global:BILL_LOG_FILE) 'INFO'
Write-BillLog ("components : {0}" -f ($Component -join ',')) 'INFO'
Write-BillLog ("recreate   : {0}" -f $Recreate.IsPresent) 'INFO'

$cfg = Get-BillConfig

try {
    Invoke-BillPreflight -Config $cfg
} catch {
    Write-BillLog $_ 'ERROR'
    exit 2
}

$services = $cfg.services
$redisCfg = $cfg.infra.redis
$nginxCfg = $cfg.infra.nginx

$components = if ($Component -contains 'all') { @('nginx', 'redis', 'python', 'envs') } else { $Component }

$hadError = $false

foreach ($step in $components) {
    try {
        switch ($step) {
            'nginx'  { Install-BillNginx -Force:$Recreate }
            'redis'  { Install-BillRedis -RedisHost $redisCfg.host -RedisPort $redisCfg.port -Force:$Recreate }
            'python' { Invoke-BillSetupPython -Services $services -Recreate:$Recreate }
            'envs'   { Invoke-BillWriteEnvs -Config $cfg -Force:$Recreate; Invoke-BillConfigureLocalAuth }
        }
    } catch {
        Write-BillLog ("step '{0}' failed: {1}" -f $step, $_) 'ERROR'
        Add-BillSummary $step 'FAIL' "$_"
        $hadError = $true
    }
}

Write-BillSummary

Write-Host ""
Write-Host "Ports:" -ForegroundColor DarkGray
Write-Host ("  nginx={0}  mysql={1}  redis={2}  rabbitmq={3}" -f `
    $nginxCfg.listen_port, $cfg.infra.mysql.port, $redisCfg.port, $cfg.infra.rabbitmq.port) -ForegroundColor DarkGray
$portsLine = ($services | ForEach-Object { "$($_.code)=$($_.port)" }) -join '  '
Write-Host "  $portsLine" -ForegroundColor DarkGray

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Ensure MySQL is running." -ForegroundColor White
Write-Host "  2. Start everything:   .\start\win\start-all.bat" -ForegroundColor White
Write-Host "  3. Check status:       .\start\win\status.bat" -ForegroundColor White
Write-Host "  4. Nginx health:       curl http://localhost:8090/nginx-health" -ForegroundColor White
Write-Host ""

if (-not $hadError -and $components -contains 'python' -and $components -contains 'envs') {
    try {
        $provisionScript = Join-Path $PSScriptRoot 'provision-databases.ps1'
        [void](Invoke-BillOfferDatabaseProvisioning -ProvisionScriptPath $provisionScript)
    } catch {
        Write-BillLog $_ 'ERROR'
        exit 1
    }
} elseif (-not $hadError) {
    Write-Host 'To provision databases later, run: .\start\win\provision-databases.bat' -ForegroundColor White
}

if ($hadError) { exit 1 } else { exit 0 }
