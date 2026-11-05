[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$connection = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or
    $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection details.' }
$arguments = @('-F', 'NUL', '-i', (Join-Path $PSScriptRoot 'id_ed25519'), '-o',
    "UserKnownHostsFile=$(Join-Path $PSScriptRoot 'known_hosts')", '-o', 'StrictHostKeyChecking=yes',
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', "$($connection.username)@$($connection.ip_address)")
& ssh.exe @arguments 'sudo chronyc makestep && chronyc tracking && date -u'
if ($LASTEXITCODE -ne 0) { throw 'VM clock synchronization failed. Check chrony and the Hyper-V time source.' }
