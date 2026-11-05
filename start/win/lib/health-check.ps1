# Single-attempt bounded probes; readiness is stronger than a listening port.
function Test-BillHttp {
    param([string]$Url, [string]$Status)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -MaximumRedirection 0
        if ($response.StatusCode -ne 200) { return $false }
        $content = if ($response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($response.Content) } else { [string]$response.Content }
        if ($Status -eq 'nginx') { return $content.Trim() -eq 'ok' }
        return ($content | ConvertFrom-Json).status -eq $Status
    } catch { return $false }
}
function Test-BillRedis {
    param([string]$HostName, [int]$Port)
    $client = New-Object Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($connect)
        $stream = $client.GetStream(); $stream.ReadTimeout = 1000; $stream.WriteTimeout = 1000
        $bytes = [Text.Encoding]::ASCII.GetBytes("PING`r`n")
        $stream.Write($bytes, 0, $bytes.Length)
        $reader = New-Object IO.StreamReader($stream)
        return $reader.ReadLine() -eq '+PONG'
    } catch { return $false } finally { $client.Dispose() }
}
function Test-BillAmqp {
    param([string]$HostName, [int]$Port)
    $client = New-Object Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(500)) { return $false }
        $client.EndConnect($connect)
        $stream = $client.GetStream(); $stream.ReadTimeout=1000; $stream.WriteTimeout=1000
        # AMQP 0-9-1 protocol negotiation, no credentials or queue declarations.
        $header = [byte[]]@(65,77,81,80,0,0,9,1)
        $stream.Write($header, 0, $header.Length)
        $reply = New-Object byte[] 11
        $read = 0
        while ($read -lt $reply.Length) {
            $count = $stream.Read($reply, $read, $reply.Length - $read)
            if ($count -eq 0) { return $false }; $read += $count
        }
        # Method frame, channel 0, connection.start (class 10 / method 10).
        return $reply[0] -eq 1 -and $reply[1] -eq 0 -and $reply[2] -eq 0 -and
            $reply[7] -eq 0 -and $reply[8] -eq 10 -and $reply[9] -eq 0 -and $reply[10] -eq 10
    } catch { return $false } finally { $client.Dispose() }
}
function Get-BillHealth {
    param([Parameter(Mandatory)]$Config, [switch]$ApiOnly)
    $infra = $Config.infra
    $rows = @()
    $probes = @(
        @{code='MySQL'; host=$infra.mysql.host; port=$infra.mysql.port; kind='database'},
        @{code='Redis'; host=$infra.redis.host; port=$infra.redis.port; kind='cache'},
        @{code='RabbitMQ'; host=$infra.rabbitmq.host; port=$infra.rabbitmq.port; kind='broker'},
        @{code='nginx'; host='127.0.0.1'; port=$infra.nginx.listen_port; kind='proxy'}
    )
    if ($ApiOnly) { $probes = @() }
    foreach ($probe in $probes) {
        $up = Wait-ForPort -HostName $probe.host -Port $probe.port -TimeoutSeconds 1
        $status = if ($up) { 'UP' } else { 'DOWN' }
        $detail = if ($up) { 'TCP reachable' } else { 'No listener' }
        if ($up -and $probe.code -eq 'Redis') {
            if (-not (Test-BillRedis -HostName $probe.host -Port $probe.port)) { $status='DEGRADED'; $detail='PING failed' }
            else { $detail='PONG' }
        }
        if ($up -and $probe.code -eq 'nginx') {
            if (-not (Test-BillHttp -Url "http://127.0.0.1:$($probe.port)/nginx-health" -Status nginx)) { $status='DEGRADED'; $detail='Gateway health failed' }
            else { $detail='Gateway ready' }
        }
        if ($up -and $probe.code -eq 'RabbitMQ') {
            if (-not (Test-BillAmqp -HostName $probe.host -Port $probe.port)) { $status='DEGRADED'; $detail='AMQP negotiation failed' }
            else { $detail='AMQP ready' }
        }
        $rows += [pscustomobject]@{Component=$probe.code; Endpoint="$($probe.host):$($probe.port)"; Status=$status; Kind=$probe.kind; Detail=$detail}
    }
    foreach ($svc in $Config.services) {
        $base = "http://127.0.0.1:$($svc.port)"
        $up = Wait-ForPort -HostName '127.0.0.1' -Port $svc.port -TimeoutSeconds 1
        $status='DOWN'; $detail='No listener'
        if ($up) {
            $status='DEGRADED'; $detail='Liveness failed'
            if (Test-BillHttp -Url "$base/health/live" -Status ok) {
                $detail='Database/schema not ready'
                if (Test-BillHttp -Url "$base/health/ready" -Status ready) { $status='UP'; $detail='API ready' }
            }
        }
        $rows += [pscustomobject]@{Component=$svc.code; Endpoint="127.0.0.1:$($svc.port)"; Status=$status; Kind='api'; Detail=$detail}
    }
    if (!$ApiOnly) {
        . (Join-Path $Global:BILL_WIN_ROOT 'lib/audit-workers.ps1')
        $rows += Get-BillAuditHealth
    }
    return $rows
}
function Write-BillHealth {
    param([Parameter(Mandatory)]$Rows)
    Write-Host ('{0,-16} {1,-24} {2,-10} {3}' -f 'Component','Endpoint','Status','Check')
    foreach ($row in $Rows) {
        $color = if ($row.Status -eq 'UP') { 'Green' } elseif ($row.Status -eq 'DEGRADED') { 'Yellow' } else { 'Red' }
        Write-Host ('{0,-16} {1,-24} {2,-10} {3}' -f $row.Component,$row.Endpoint,$row.Status,$row.Detail) -ForegroundColor $color
    }
}
function Start-BillInfrastructure {
    param([ValidateSet('nginx','redis')][string]$Name, [Parameter(Mandatory)]$Config)
    $port = if ($Name -eq 'nginx') { $Config.infra.nginx.listen_port } else { $Config.infra.redis.port }
    if (Get-BillManagedProcess $Name -ForStart) {
        $ready = if ($Name -eq 'nginx') { Test-BillHttp -Url "http://127.0.0.1:$port/nginx-health" -Status nginx } else { Test-BillRedis -HostName '127.0.0.1' -Port $port }
        if (-not $ready) { throw "$Name is running but not ready; check its log before restarting." }
        Write-BillLog "$Name already ready" 'SKIP'; return
    }
    if (Wait-ForPort -HostName '127.0.0.1' -Port $port -TimeoutSeconds 1) { throw "$Name port $port is occupied outside this launcher." }
    if ($Name -eq 'nginx') {
        $root = Get-BillNginxRoot
        $exe = Join-Path $root 'nginx.exe'
        $prefix = ($root -replace '\\', '/') + '/'
        if (-not (Test-Path -LiteralPath $exe)) { throw 'nginx missing. Run setup.bat -Component nginx.' }
        if (-not (Invoke-BillCommand -FilePath $exe -Arguments @('-p',$prefix,'-c','conf/nginx.conf','-t') -WorkingDirectory $root)) { throw 'nginx configuration check failed.' }
        [void](Start-BillProcess -Name $Name -Executable $exe -WorkingDirectory $root -Arguments @('-p',$prefix,'-c','conf/nginx.conf','-g','daemon off;'))
    } else {
        if ($Config.infra.redis.host -ne '127.0.0.1') { throw 'Local Redis launcher requires infra.redis.host=127.0.0.1.' }
        $root = Join-Path $Global:BILL_WIN_ROOT 'bin\redis'
        $exe = Join-Path $root 'redis-server.exe'
        if (-not (Test-Path -LiteralPath $exe)) { throw 'Redis missing. Run setup.bat -Component redis.' }
        [void](Start-BillProcess -Name $Name -Executable $exe -WorkingDirectory $root -Arguments @(
            '--bind','127.0.0.1','--port',[string]$port,'--protected-mode','yes',
            '--save','','--appendonly','no','--maxmemory','512mb','--maxmemory-policy','allkeys-lru'
        ))
    }
    $deadline = (Get-Date).AddSeconds(15)
    do {
        $ready = if ($Name -eq 'nginx') { Test-BillHttp -Url "http://127.0.0.1:$port/nginx-health" -Status nginx } else { Test-BillRedis -HostName '127.0.0.1' -Port $port }
        if ($ready) { Write-BillLog "$Name ready on port $port" 'OK'; return }
        if (-not (Get-BillManagedProcess $Name)) { break }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    throw "$Name failed startup. Check logs/$Name.stderr.log."
}
