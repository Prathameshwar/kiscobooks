[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$vmFolder = Join-Path $PSScriptRoot '..\authentik-vm'
$connection = Get-Content -LiteralPath (Join-Path $vmFolder 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or
    $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection details.' }
$arguments = @('-F', 'NUL', '-i', (Join-Path $vmFolder 'id_ed25519'), '-o',
    "UserKnownHostsFile=$(Join-Path $vmFolder 'known_hosts')", '-o', 'StrictHostKeyChecking=yes',
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', "$($connection.username)@$($connection.ip_address)")
$encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'authentik-email.yaml')))
# Fixed destination, no credentials in the blueprint or shell command. SSH verifies its known host.
$upload = 'set -o pipefail; sudo install -o 1000 -g 1000 -m 600 /dev/null /opt/bill-authentik/blueprints/bill-verified-email.yaml.pending && base64 --decode --ignore-garbage | sudo tee /opt/bill-authentik/blueprints/bill-verified-email.yaml.pending >/dev/null && sudo mv /opt/bill-authentik/blueprints/bill-verified-email.yaml.pending /opt/bill-authentik/blueprints/bill-verified-email.yaml'
$encoded | & ssh.exe @arguments $upload
if ($LASTEXITCODE -ne 0) { throw 'Could not install the local Authentik blueprint.' }
& ssh.exe @arguments 'sudo docker compose --project-directory /opt/bill-authentik exec -T server ak apply_blueprint /blueprints/custom/bill-verified-email.yaml'
if ($LASTEXITCODE -ne 0) { throw 'Authentik rejected the blueprint. Review the reported error.' }
Write-Output 'Local Bill OAuth grants and verified-email mapping applied. No users were promoted.'
