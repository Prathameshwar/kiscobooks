param([switch]$Restart)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'rabbitmq-local.ps1') -Action environment
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Restart) { $env:IDENTITY_TEST_ALLOW_BROKER_RESTART = '1' }
Push-Location (Join-Path $workspace 'apis/audit')
try {
    & .venv/Scripts/python.exe -m pytest tests/test_live_rabbitmq.py -q
    if ($LASTEXITCODE -ne 0) { throw 'Live RabbitMQ/Audit verification failed.' }
} finally { Pop-Location }
