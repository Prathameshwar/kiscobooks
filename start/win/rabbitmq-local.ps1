param([ValidateSet('start','stop','status','environment')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $workspace '.tools/rabbitmq-runtime'
$erlang = Join-Path $workspace '.tools/erlang'
$rabbit = Join-Path $workspace '.tools/rabbitmq/rabbitmq_server-4.3.5/sbin'
# A repeated stop succeeds even when binaries were never installed. Never create runtime
# credentials or rewrite configuration during status/stop.
$listener = @(Get-NetTCPConnection -State Listen -LocalPort 5672 -ErrorAction SilentlyContinue)
if ($Action -eq 'stop' -and $listener.Count -eq 0) { Write-Output 'Local RabbitMQ already stopped.'; return }
if (!(Test-Path (Join-Path $erlang 'bin/erl.exe')) -or !(Test-Path (Join-Path $rabbit 'rabbitmq-server.bat'))) {
    throw 'Install the verified RabbitMQ 4.3.5 and Erlang 27 archives as documented in docs/local-rabbitmq.md.'
}
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$credentialPath = Join-Path $runtime 'credentials.json'
if (!(Test-Path $credentialPath) -and $Action -in @('status','stop')) { throw 'Local RabbitMQ credentials missing; no process was changed.' }
if (!(Test-Path $credentialPath)) {
    $random = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($random)
    $rng.Dispose()
    @{user='bill_local'; password=([Convert]::ToBase64String($random).TrimEnd('=').Replace('+','-').Replace('/','_'))} | ConvertTo-Json | Set-Content -LiteralPath $credentialPath -Encoding ASCII
}
# OTP 27 checks an existing home cookie before its platform configuration directory.
$cookiePath = Join-Path $runtime '.erlang.cookie'
if (!(Test-Path $cookiePath) -and $Action -in @('status','stop')) { throw 'Local RabbitMQ node cookie missing; no process was changed.' }
if (!(Test-Path $cookiePath)) {
    $cookieBytes = New-Object byte[] 32
    $cookieRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $cookieRng.GetBytes($cookieBytes)
    $cookieRng.Dispose()
    [BitConverter]::ToString($cookieBytes).Replace('-','') | Set-Content -LiteralPath $cookiePath -Encoding ASCII
}
$credential = Get-Content -LiteralPath $credentialPath -Raw | ConvertFrom-Json
$config = @"
listeners.tcp.local = 127.0.0.1:5672
distribution.listener.interface = 127.0.0.1
distribution.listener.port_range.min = 25672
distribution.listener.port_range.max = 25672
default_user = $($credential.user)
default_pass = $($credential.password)
default_vhost = bill_identity_test
loopback_users.bill_local = true
log.console = false
log.file.level = info
"@
if ($Action -in @('start','environment')) {
    $config | Set-Content -LiteralPath (Join-Path $runtime 'rabbitmq.conf') -Encoding ASCII
}
$env:ERLANG_HOME = $erlang
# The portable Windows launcher sets its own home argument; OTP's config path is explicit.
$env:APPDATA = $runtime
New-Item -ItemType Directory -Force -Path (Join-Path $runtime 'erlang') | Out-Null
if ($Action -in @('start','environment')) {
    Copy-Item -LiteralPath $cookiePath -Destination (Join-Path $runtime 'erlang/.erlang.cookie') -Force
}
$env:ERL_EPMD_ADDRESS = '127.0.0.1'
$env:RABBITMQ_BASE = $runtime
$env:RABBITMQ_CONFIG_FILE = Join-Path $runtime 'rabbitmq'
$env:RABBITMQ_LOG_BASE = Join-Path $runtime 'log'
$env:RABBITMQ_MNESIA_BASE = Join-Path $runtime 'data'
$env:RABBITMQ_NODENAME = 'bill_identity@localhost'
$env:RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS = '-kernel inet_dist_use_interface {127,0,0,1} +S 2:2'
$env:RABBITMQ_CTL_ERL_ARGS = '+S 1:1'
$env:IDENTITY_TEST_BROKER_URL = 'amqp://' + $credential.user + ':' + $credential.password + '@127.0.0.1:5672/bill_identity_test'
$env:IDENTITY_TEST_BROKER_USER = $credential.user
if ($Action -eq 'environment') { return }
if ($Action -eq 'start') {
    $listener = Get-NetTCPConnection -State Listen -LocalPort 5672 -ErrorAction SilentlyContinue
    if ($listener) {
        & (Join-Path $rabbit 'rabbitmq-diagnostics.bat') -t 10 -q ping
        if ($LASTEXITCODE -ne 0) { throw 'Port 5672 belongs to another process; it was left untouched.' }
        return
    }
    # Normalize inherited PATH casing; Windows PowerShell Start-Process rejects duplicate keys.
    $inheritedPath = $env:Path
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
    Remove-Item Env:Path -ErrorAction SilentlyContinue
    $env:Path = $inheritedPath
    Start-Process -FilePath (Join-Path $rabbit 'rabbitmq-server.bat') -WorkingDirectory $runtime -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'startup.stdout.log') -RedirectStandardError (Join-Path $runtime 'startup.stderr.log')
    $deadline = (Get-Date).AddSeconds(60)
    do {
        $listener = Get-NetTCPConnection -State Listen -LocalPort 5672 -ErrorAction SilentlyContinue
        if ($listener) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    if (-not $listener) { throw 'Local RabbitMQ did not listen within 60s. Check .tools/rabbitmq-runtime/startup.stderr.log.' }
    & (Join-Path $rabbit 'rabbitmq-diagnostics.bat') -t 10 -q ping
    if ($LASTEXITCODE -ne 0) { throw 'Local RabbitMQ did not become ready.' }
    Write-Output 'Local RabbitMQ ready.'
} elseif ($Action -eq 'stop') {
    & (Join-Path $rabbit 'rabbitmq-diagnostics.bat') -t 10 -q ping
    if ($LASTEXITCODE -ne 0) { throw 'Port 5672 is not the local RabbitMQ node; it was left untouched.' }
    & (Join-Path $rabbit 'rabbitmqctl.bat') -t 15 stop
    if ($LASTEXITCODE -ne 0) { throw 'RabbitMQ stop failed.' }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $listener = Get-NetTCPConnection -State Listen -LocalPort 5672 -ErrorAction SilentlyContinue
        if (-not $listener) { Write-Output 'Local RabbitMQ stopped.'; return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw 'Port 5672 remains occupied after local RabbitMQ stop.'
} else {
    & (Join-Path $rabbit 'rabbitmq-diagnostics.bat') -t 10 -q status
    if ($LASTEXITCODE -ne 0) { throw 'RabbitMQ is not ready.' }
}
