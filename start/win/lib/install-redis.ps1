# Redis (Windows port by tporadowski) installer.
# Downloads a pinned ZIP from GitHub releases, verifies SHA-256, extracts to
# start\win\bin\redis\. Runs as a foreground process via start-redis.bat.
# Redis here is cache-only (docs/tech-stack.md) -- RabbitMQ is the broker.

$Script:BILL_REDIS_VERSION = '5.0.14.1'
$Script:BILL_REDIS_URL     = "https://github.com/tporadowski/redis/releases/download/v$Script:BILL_REDIS_VERSION/Redis-x64-$Script:BILL_REDIS_VERSION.zip"
$Script:BILL_REDIS_BYTES   = 12617669
$Script:BILL_REDIS_SHA256  = '018EA18A35876383CBB5F4CD0258ADFC87747CF9D619BCE1CF73A2E36F720CCF'

function Install-BillRedis {
    param(
        [Parameter(Mandatory)][string]$RedisHost,
        [Parameter(Mandatory)][int]$RedisPort,
        [switch]$Force
    )
    Write-BillStep 'Redis (Windows port)'

    $installDir = Join-Path $Global:BILL_WIN_ROOT 'bin\redis'
    $redisExe   = Join-Path $installDir 'redis-server.exe'
    Assert-BillChildPath -Path $installDir -Root $Global:BILL_WIN_ROOT

    if ((Test-Path $redisExe) -and -not $Force) {
        Write-BillLog "Redis already at $installDir" 'SKIP'
        Add-BillSummary 'Redis' 'SKIP' $installDir
        return
    }

    if ((Test-Path $installDir) -and $Force) {
        Write-BillLog "-Force: removing $installDir" 'WARN'
        Remove-Item -Recurse -Force $installDir
    }

    New-Item -ItemType Directory -Force -Path $installDir | Out-Null

    try {
        [Net.ServicePointManager]::SecurityProtocol = (
            [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        )
    } catch {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    }

    $tempZip = Join-Path $env:TEMP ("redis-{0}-{1}.zip" -f $Script:BILL_REDIS_VERSION, [guid]::NewGuid())
    Write-BillLog "Downloading Redis $Script:BILL_REDIS_VERSION" 'INFO'
    Write-BillLog "  $Script:BILL_REDIS_URL" 'INFO'
    try {
        Invoke-WebRequest -Uri $Script:BILL_REDIS_URL -OutFile $tempZip -UseBasicParsing -TimeoutSec 120 -MaximumRedirection 5
    } catch {
        Add-BillSummary 'Redis' 'FAIL' ("download failed: {0}" -f $_)
        throw "Redis download failed: $_"
    }

    $actualBytes = (Get-Item $tempZip).Length
    if ($actualBytes -ne $Script:BILL_REDIS_BYTES) {
        Write-BillLog "size mismatch (expected $Script:BILL_REDIS_BYTES, got $actualBytes)" 'WARN'
    }

    $actualSha = (Get-FileHash -Algorithm SHA256 $tempZip).Hash.ToUpperInvariant()
    if ($actualSha -ne $Script:BILL_REDIS_SHA256) {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
        Add-BillSummary 'Redis' 'FAIL' 'SHA-256 mismatch'
        throw ("Redis SHA-256 mismatch (expected {0}, got {1})" -f $Script:BILL_REDIS_SHA256, $actualSha)
    }
    Write-BillLog "SHA-256 OK" 'OK'

    # tporadowski/redis zip is flat -- extract directly into installDir.
    try {
        Expand-Archive -LiteralPath $tempZip -DestinationPath $installDir -Force
    } catch {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
        Add-BillSummary 'Redis' 'FAIL' ("extract failed: {0}" -f $_)
        throw "Redis extract failed: $_"
    }
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path $redisExe)) {
        Add-BillSummary 'Redis' 'FAIL' 'redis-server.exe missing after extract'
        throw "Redis install broken -- no redis-server.exe at $redisExe"
    }

    $installInfo = [ordered]@{
        installedAt = (Get-Date).ToUniversalTime().ToString('o')
        version     = $Script:BILL_REDIS_VERSION
        source      = $Script:BILL_REDIS_URL
        sha256      = $actualSha
        installDir  = $installDir
    }
    $installInfo | ConvertTo-Json | Out-File -FilePath (Join-Path $installDir 'InstallInfo.json') -Encoding utf8

    Write-BillLog "Redis installed at $installDir" 'OK'
    Write-BillLog "Launch with: start\win\start-redis.bat" 'INFO'
    Add-BillSummary 'Redis' 'OK' $installDir
}
