# Nginx (Windows build) installer.
# Downloads a pinned ZIP from nginx.org, verifies SHA-256, extracts to
# start\win\bin\nginx\. Runs as a foreground process via start-nginx.bat.
# No Windows service.

$Script:BILL_NGINX_VERSION = '1.26.2'
$Script:BILL_NGINX_URL     = "https://nginx.org/download/nginx-$Script:BILL_NGINX_VERSION.zip"
$Script:BILL_NGINX_BYTES   = 2081815
$Script:BILL_NGINX_SHA256  = '942638CC31C836FE429FDE22E4C46E497F89D3C2BBCE46CD2C8800854FD71409'

function Install-BillNginx {
    param([switch]$Force)
    Write-BillStep 'Nginx'

    $installDir = [IO.Path]::GetFullPath((Join-Path $Global:BILL_REPO_ROOT (Get-BillConfig).infra.nginx.root_relative))
    $nginxExe   = Join-Path $installDir 'nginx.exe'
    Assert-BillChildPath -Path $installDir -Root $Global:BILL_WIN_ROOT

    if ((Test-Path $nginxExe) -and -not $Force) {
        Write-BillLog "Nginx already at $installDir" 'SKIP'
        Deploy-BillNginxConf -InstallRoot $installDir
        Add-BillSummary 'Nginx' 'SKIP' $installDir
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

    $tempZip = Join-Path $env:TEMP ("nginx-{0}-{1}.zip" -f $Script:BILL_NGINX_VERSION, [guid]::NewGuid())
    Write-BillLog "Downloading nginx $Script:BILL_NGINX_VERSION" 'INFO'
    Write-BillLog "  $Script:BILL_NGINX_URL" 'INFO'
    try {
        Invoke-WebRequest -Uri $Script:BILL_NGINX_URL -OutFile $tempZip -UseBasicParsing -TimeoutSec 120
    } catch {
        Add-BillSummary 'Nginx' 'FAIL' ("download failed: {0}" -f $_)
        throw "Nginx download failed: $_"
    }

    $actualBytes = (Get-Item $tempZip).Length
    if ($actualBytes -ne $Script:BILL_NGINX_BYTES) {
        Write-BillLog "size mismatch (expected $Script:BILL_NGINX_BYTES, got $actualBytes)" 'WARN'
    }

    $actualSha = (Get-FileHash -Algorithm SHA256 $tempZip).Hash.ToUpperInvariant()
    if ($actualSha -ne $Script:BILL_NGINX_SHA256) {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
        Add-BillSummary 'Nginx' 'FAIL' 'SHA-256 mismatch'
        throw ("Nginx SHA-256 mismatch (expected {0}, got {1})" -f $Script:BILL_NGINX_SHA256, $actualSha)
    }
    Write-BillLog "SHA-256 OK" 'OK'

    # nginx.org zip layout: nginx-<version>/... at root. Un-nest.
    $staging = Join-Path $env:TEMP ("nginx-stage-{0}" -f [guid]::NewGuid())
    Assert-BillChildPath -Path $staging -Root $env:TEMP
    try {
        Expand-Archive -LiteralPath $tempZip -DestinationPath $staging -Force
        $nested = Join-Path $staging "nginx-$Script:BILL_NGINX_VERSION"
        Assert-BillChildPath -Path $nested -Root $staging
        if (-not (Test-Path $nested)) {
            throw "archive layout unexpected -- no nginx-$Script:BILL_NGINX_VERSION dir inside zip"
        }
        Get-ChildItem -LiteralPath $nested -Force | Move-Item -Destination $installDir -Force
    } catch {
        Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
        if (Test-Path $staging) { Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue }
        Add-BillSummary 'Nginx' 'FAIL' ("extract failed: {0}" -f $_)
        throw "Nginx extract failed: $_"
    }
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue

    if (-not (Test-Path $nginxExe)) {
        Add-BillSummary 'Nginx' 'FAIL' 'nginx.exe missing after extract'
        throw "Nginx install broken -- no nginx.exe at $nginxExe"
    }

    Deploy-BillNginxConf -InstallRoot $installDir

    $installInfo = [ordered]@{
        installedAt = (Get-Date).ToUniversalTime().ToString('o')
        version     = $Script:BILL_NGINX_VERSION
        source      = $Script:BILL_NGINX_URL
        sha256      = $actualSha
        installDir  = $installDir
    }
    $installInfo | ConvertTo-Json | Out-File -FilePath (Join-Path $installDir 'InstallInfo.json') -Encoding utf8

    Write-BillLog "Nginx installed at $installDir" 'OK'
    Write-BillLog "Launch with: start\win\start-nginx.bat" 'INFO'
    Add-BillSummary 'Nginx' 'OK' $installDir
}

function Deploy-BillNginxConf {
    param([Parameter(Mandatory)][string]$InstallRoot)

    $confDir  = Join-Path $InstallRoot 'conf'
    $confDDir = Join-Path $confDir 'conf.d'
    $logsDir  = Join-Path $InstallRoot 'logs'
    $tempDir  = Join-Path $InstallRoot 'temp'

    foreach ($d in @($confDir, $confDDir, $logsDir, $tempDir)) {
        if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    }

    Copy-Item (Join-Path $Global:BILL_CONF_DIR 'nginx.conf')    (Join-Path $confDir 'nginx.conf')     -Force
    $config = Get-BillConfig
    $routing = Get-Content -LiteralPath (Join-Path $Global:BILL_CONF_DIR 'bill.conf') -Raw
    $routing = $routing -replace 'listen\s+127\.0\.0\.1:8090\s+default_server;', ("listen 127.0.0.1:{0} default_server;" -f $config.infra.nginx.listen_port)
    foreach ($service in $config.services) {
        $pattern = '(upstream\s+' + [regex]::Escape([string]$service.code) + '_upstream\s*\{\s*server\s+127\.0\.0\.1:)\d+'
        if ($routing -notmatch $pattern) { throw "nginx routing template missing upstream for $($service.code)." }
        $routing = [regex]::Replace($routing, $pattern, ('${1}' + [string]$service.port))
    }
    Set-Content -LiteralPath (Join-Path $confDDir 'bill.conf') -Value $routing -Encoding ASCII
    Copy-Item (Join-Path $Global:BILL_CONF_DIR 'proxy.include') (Join-Path $confDDir 'proxy.include') -Force

    Write-BillLog "Deployed nginx.conf + conf.d/bill.conf + proxy.include" 'OK'
}
