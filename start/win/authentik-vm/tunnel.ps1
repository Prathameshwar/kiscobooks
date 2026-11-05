param([ValidateSet('start', 'stop', 'status')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\_common.ps1')
. (Join-Path $PSScriptRoot '..\lib\runtime.ps1')
$name = 'authentik-tunnel'
try {
    $process = Get-BillManagedProcess $name -ForStart:($Action -eq 'start')
    switch ($Action) {
        'start' {
            if ($process) {
                foreach ($port in @(9000, 9443)) {
                    if (-not (Wait-ForPort -HostName '127.0.0.1' -Port $port -TimeoutSeconds 1)) {
                        throw "The managed Authentik tunnel has no listener on port $port. Check logs/authentik-tunnel.stderr.log."
                    }
                }
                Write-Host 'The managed Authentik tunnel is already running.'; exit 0
            }
            foreach ($port in @(9000, 9443)) {
                if (Wait-ForPort -HostName '127.0.0.1' -Port $port -TimeoutSeconds 1) {
                    throw "Local port $port is occupied outside this tunnel; it was preserved."
                }
            }
            $process = Start-BillProcess -Name $name -Executable (Get-Command powershell.exe).Source -Arguments @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'tunnel-host.ps1')
            )
            if (-not (Wait-ForPort -HostName '127.0.0.1' -Port 9443 -TimeoutSeconds 10) -or
                -not (Wait-ForPort -HostName '127.0.0.1' -Port 9000 -TimeoutSeconds 1) -or $process.HasExited) {
                throw 'Tunnel startup failed. Check logs/authentik-tunnel.stderr.log and the VM connection details.'
            }
            Write-Host 'Managed SSH tunnel ready: https://localhost:9443. Provider readiness is separate.'
        }
        'stop' {
            $runtimeLock = Enter-BillRuntimeLock $name
            try {
                $process = Get-BillManagedProcess $name
                if ($process) {
                    $stopPath = Join-Path $Global:BILL_WIN_ROOT 'runtime\authentik-tunnel.stop'
                    Set-Content -LiteralPath $stopPath -Value stop -Encoding ASCII
                    if (-not $process.WaitForExit(5000)) { Stop-BillProcessTree $process }
                    Remove-Item -LiteralPath $stopPath -Force -ErrorAction SilentlyContinue
                }
                Remove-Item -LiteralPath (Get-BillRuntimePath $name) -Force -ErrorAction SilentlyContinue
                Write-Host 'Managed Authentik tunnel stopped. VM and other listeners were preserved.'
            } finally { $runtimeLock.Dispose() }
        }
        'status' {
            if (-not $process) { Write-Host 'Managed Authentik tunnel is stopped.' }
            elseif ((Wait-ForPort -HostName '127.0.0.1' -Port 9000 -TimeoutSeconds 1) -and
                    (Wait-ForPort -HostName '127.0.0.1' -Port 9443 -TimeoutSeconds 1)) {
                Write-Host 'Managed Authentik tunnel is running. Provider readiness is separate.'
            } else { Write-Host 'Managed Authentik supervisor is running; forwarding is reconnecting or unavailable.' }
        }
    }
    exit 0
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
