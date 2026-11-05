param([switch]$Tunnel)
$ErrorActionPreference = 'Stop'
$connection = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'connection.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$arguments = @('-F', 'NUL', '-i', (Join-Path $PSScriptRoot 'id_ed25519'), '-o', "UserKnownHostsFile=$(Join-Path $PSScriptRoot 'known_hosts')", '-o', 'StrictHostKeyChecking=accept-new')
if ($Tunnel) {
    $arguments += @('-N', '-o', 'ExitOnForwardFailure=yes', '-L', '127.0.0.1:9443:127.0.0.1:9443', '-L', '127.0.0.1:9000:127.0.0.1:9000')
    Write-Host 'Forwarding Authentik to https://localhost:9443 and http://localhost:9000. Keep this terminal open; Ctrl+C closes it.'
}
& ssh.exe @arguments "$($connection.username)@$($connection.ip_address)"
exit $LASTEXITCODE
