$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\lib\_common.ps1')
. (Join-Path $PSScriptRoot '..\lib\runtime.ps1')
. (Join-Path $PSScriptRoot '..\lib\tunnel-supervision.ps1')

$connection = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'connection.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$address = $null
if ($connection.username -notmatch '^[a-z_][a-z0-9_-]*$' -or
    -not [Net.IPAddress]::TryParse([string]$connection.ip_address, [ref]$address)) {
    throw 'Invalid saved Authentik connection; forwarding was not started.'
}
$forwardArguments = @(
    '-F', 'NUL', '-i', (Join-Path $PSScriptRoot 'id_ed25519'), '-o', "UserKnownHostsFile=$(Join-Path $PSScriptRoot 'known_hosts')",
    '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
    '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=2', '-N',
    '-L', '127.0.0.1:9443:127.0.0.1:9443', '-L', '127.0.0.1:9000:127.0.0.1:9000', "$($connection.username)@$($connection.ip_address)"
)
Invoke-BillTunnelSupervisor -StopPath (Join-Path $Global:BILL_WIN_ROOT 'runtime\authentik-tunnel.stop') -StartForward {
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = (Get-Command ssh.exe).Source
    $start.Arguments = ($forwardArguments | ForEach-Object { ConvertTo-BillArgument $_ }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    [System.Diagnostics.Process]::Start($start)
}
