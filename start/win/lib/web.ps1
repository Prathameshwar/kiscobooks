# UI uses the same process ownership and bounded stop mechanism as the APIs.
function Get-BillWebApps {
    param([ValidateSet('all', 'auth', 'console')][string]$App = 'all')
    foreach ($entry in @(@{Code='auth'; Port=4310; Path='/login'}, @{Code='console'; Port=4320; Path='/'})) {
        if ($App -ne 'all' -and $App -ne $entry.Code) { continue }
        $directory = Join-Path $Global:BILL_REPO_ROOT "mfes\apps\$($entry.Code)"
        [pscustomobject]@{
            Name = "web-$($entry.Code)"; Port = $entry.Port; Directory = $directory
            Url = "http://localhost:$($entry.Port)$($entry.Path)"
            Cli = Join-Path $directory 'node_modules\next\dist\bin\next'
        }
    }
}

function Get-BillWebNode {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $node) { throw 'Node.js 20 or newer is required on PATH.' }
    $version = & $node.Source --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^v(\d+)\.' -or [int]$Matches[1] -lt 20) {
        throw 'Node.js 20 or newer is required on PATH.'
    }
    return $node.Source
}

function Install-BillWebDependencies {
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if (-not $pnpm) { throw 'pnpm is required on PATH to install UI dependencies. Enable Corepack or install pnpm.' }
    Push-Location (Join-Path $Global:BILL_REPO_ROOT 'mfes')
    try {
        & $pnpm.Source install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed (exit $LASTEXITCODE)." }
    } finally { Pop-Location }
}

function Start-BillWebApp {
    param([Parameter(Mandatory)]$Target, [Parameter(Mandatory)][string]$Node)
    if (-not (Test-Path -LiteralPath $Target.Cli)) { throw "Next.js is missing for $($Target.Name); install mfes dependencies." }
    $stopPath = Join-Path (Split-Path -Parent (Get-BillRuntimePath $Target.Name)) "$($Target.Name).stop"
    $environment = @{BILL_WEB_STOP_PATH=$stopPath}
    $localCa = Join-Path $Global:BILL_REPO_ROOT '.tools\authentik\tls\ca.crt'
    # The Authentik VM's CA matters only to an installation that signs in through Authentik.
    if (-not $env:NODE_EXTRA_CA_CERTS -and (Get-BillAuthProvider) -eq 'authentik' -and (Test-Path -LiteralPath $localCa)) {
        $environment.NODE_EXTRA_CA_CERTS = $localCa
    }
    # The preload is inherited by Next's forked worker. No cmd.exe shell or env interpolation.
    [void](Start-BillProcess -Name $Target.Name -Executable $Node -WorkingDirectory $Target.Directory `
        -Environment $environment -Arguments @(
            '--require', (Join-Path $Global:BILL_WIN_ROOT 'web-stop.cjs'), $Target.Cli,
            'dev', '--hostname', '127.0.0.1', '--port', [string]$Target.Port
        ))
    Write-BillLog "$($Target.Name) launch requested; logs/$($Target.Name).stdout.log" 'INFO'
}

function Stop-BillWebApp {
    param([Parameter(Mandatory)]$Target)
    Stop-BillComponent -Name $Target.Name -Port $Target.Port
}

function Test-BillWebListenerOwned {
    param([Parameter(Mandatory)][System.Diagnostics.Process]$Process, [Parameter(Mandatory)][int]$Port)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    if ($listeners.Count -eq 0) { return $false }
    $snapshot = @(Get-CimInstance Win32_Process)
    $ids = @([int]$Process.Id)
    for ($index = 0; $index -lt $ids.Count; $index++) {
        $ids += @($snapshot | Where-Object { $_.ParentProcessId -eq $ids[$index] } | ForEach-Object { [int]$_.ProcessId })
    }
    return @($listeners | Where-Object { $_.OwningProcess -notin $ids }).Count -eq 0
}

function Test-BillWebHttp {
    param([Parameter(Mandatory)][int]$Port)
    try {
        # Public asset exercises Next's HTTP server without needing a signed-in session.
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/favicon.svg" -TimeoutSec 3
        $content = $response.Content
        if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
        return $response.StatusCode -eq 200 -and $content -match '<svg\b' -and $content -match 'aria-label="KiscoBooks"'
    } catch { return $false }
}

function Get-BillWebStatus {
    param([Parameter(Mandatory)]$Target)
    $status = 'DOWN'
    $detail = 'No managed server or listener.'
    try {
        $process = Get-BillManagedProcess $Target.Name
        if (-not $process) {
            if (Wait-ForPort -HostName '127.0.0.1' -Port $Target.Port -TimeoutSeconds 1) {
                $status = 'EXTERNAL'; $detail = 'Port occupied outside this launcher; left untouched.'
            } elseif (Test-Path -LiteralPath (Get-BillRuntimePath $Target.Name)) {
                $status = 'EXITED'; $detail = 'Managed process exited. Check its stdout/stderr logs.'
            }
        } elseif (-not (Wait-ForPort -HostName '127.0.0.1' -Port $Target.Port -TimeoutSeconds 1)) {
            $status = 'STARTING'; $detail = 'Managed process running; HTTP listener not ready.'
        } elseif (-not (Test-BillWebListenerOwned -Process $process -Port $Target.Port)) {
            $status = 'EXTERNAL'; $detail = 'Listener is outside the managed process tree; left untouched.'
        } elseif (Test-BillWebHttp $Target.Port) {
            $status = 'UP'; $detail = 'Web server ready; login/backend configuration is separate.'
        } else { $status = 'DEGRADED'; $detail = 'Managed listener failed the expected HTTP asset probe.' }
    } catch { $status = 'ERROR'; $detail = $_.Exception.Message }
    return [pscustomobject]@{App=$Target.Name; Port=$Target.Port; Status=$status; Url=$Target.Url; Detail=$detail}
}

function Write-BillWebStatus {
    param([Parameter(Mandatory)][object[]]$Rows)
    $Rows | Format-Table App, Port, Status, Url -AutoSize | Out-Host
    foreach ($row in $Rows) {
        if ($row.Status -ne 'UP') { Write-BillLog "$($row.App): $($row.Detail)" 'WARN' }
    }
}
