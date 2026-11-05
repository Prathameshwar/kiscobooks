# The caller launches only its pinned SSH command. Never stop an unrelated listener.
function Test-BillTunnelPorts {
    return (Wait-ForPort -HostName '127.0.0.1' -Port 9000 -TimeoutSeconds 1) -or
        (Wait-ForPort -HostName '127.0.0.1' -Port 9443 -TimeoutSeconds 1)
}

function Invoke-BillTunnelSupervisor {
    param([Parameter(Mandatory)][scriptblock]$StartForward,
          [Parameter(Mandatory)][string]$StopPath)
    $delay = 1
    while (-not (Test-Path -LiteralPath $StopPath)) {
        if (Test-BillTunnelPorts) {
            throw 'Authentik forwarding ports are owned outside this connection; reconnect refused.'
        }
        $child = $null
        $connectedAt = [DateTime]::UtcNow
        try {
            $child = & $StartForward
            while (-not $child.WaitForExit(1000)) {
                if (Test-Path -LiteralPath $StopPath) { break }
            }
        } catch {
            Write-BillLog 'Authentik forwarding launch failed; retrying the saved pinned connection.' 'WARN'
        } finally {
            if ($child -and -not $child.HasExited) { Stop-BillProcessTree $child }
            if ($child) { $child.Dispose() }
        }
        if (Test-Path -LiteralPath $StopPath) { break }
        if (([DateTime]::UtcNow - $connectedAt).TotalSeconds -ge 30) { $delay = 1 }
        Write-BillLog "Authentik connection ended; retrying in $delay seconds." 'WARN'
        for ($tick = 0; $tick -lt $delay * 4; $tick++) {
            if (Test-Path -LiteralPath $StopPath) { break }
            Start-Sleep -Milliseconds 250
        }
        $delay = [Math]::Min(15, $delay * 2)
    }
}
