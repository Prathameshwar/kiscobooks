param([ValidateSet('start','status','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = Join-Path $workspace '.tools/identity-mysql'
$server = 'C:/Program Files/MySQL/MySQL Server 9.6/bin/mysqld.exe'
$client = 'C:/Program Files/MySQL/MySQL Server 9.6/bin/mysql.exe'
$admin = 'C:/Program Files/MySQL/MySQL Server 9.6/bin/mysqladmin.exe'
if (!(Test-Path $server)) { throw 'MySQL 9.6 executable is required.' }
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$configPath = Join-Path $runtime 'my.ini'
$data = Join-Path $runtime 'data'
$portableData = $data.Replace('\','/')
$config = @"
[mysqld]
datadir=$portableData
port=13396
bind-address=127.0.0.1
mysqlx=OFF
skip-log-bin
innodb_buffer_pool_size=128M
max_connections=40
log-error=$($runtime.Replace('\','/'))/server.log
"@
$config | Set-Content -LiteralPath $configPath -Encoding ASCII
if ($Action -eq 'start') {
    $listener = Get-NetTCPConnection -LocalPort 13396 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw 'Port 13396 is already in use; existing processes were left untouched.' }
    if (!(Test-Path (Join-Path $data 'mysql'))) {
        & $server "--defaults-file=$configPath" --initialize-insecure
        if ($LASTEXITCODE -ne 0) { throw 'Disposable MySQL initialization failed.' }
    }
    $inheritedPath = $env:Path
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
    Remove-Item Env:Path -ErrorAction SilentlyContinue
    $env:Path = $inheritedPath
    Start-Process -FilePath $server -ArgumentList "--defaults-file=$configPath" -WorkingDirectory $runtime -WindowStyle Hidden
    Write-Output 'Disposable loopback MySQL launch requested on 13396. Check status before tests.'
} elseif ($Action -eq 'stop') {
    & $admin --host=127.0.0.1 --port=13396 --user=root shutdown
} else {
    & $client --host=127.0.0.1 --port=13396 --user=root --execute='SELECT VERSION();'
}
