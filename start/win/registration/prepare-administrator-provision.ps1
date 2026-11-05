[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $PSScriptRoot '../platform-setup/configuration.ps1')
$folder = Join-Path $PSScriptRoot '../authentik-vm'
$connection = Get-Content -LiteralPath (Join-Path $folder 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection.' }
$arguments = @('-F','NUL','-i',(Join-Path $folder 'id_ed25519'),'-o',"UserKnownHostsFile=$(Join-Path $folder 'known_hosts')",'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=10',"$($connection.username)@$($connection.ip_address)")
$result = @(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'prepare-administrator-provision.py') -Raw | & ssh.exe @arguments 'sudo docker compose --project-directory /opt/bill-authentik exec -T server ak shell 2>/dev/null')
if ($LASTEXITCODE -ne 0) { throw 'Authentik administrator provisioning setup failed.' }
$tokens = @($result | Where-Object { $_ -match '^BILL_PROVISION_TOKEN=[A-Za-z0-9_-]{32,}$' })
if ($tokens.Count -ne 1) { throw 'Provider did not return the expected private credential.' }
$issuer = [regex]::Match([IO.File]::ReadAllText((Join-Path $workspace 'mfes/apps/auth/.env.local')), '(?m)^AUTHENTIK_ISSUER=([^\r\n]+)').Groups[1].Value.Trim()
$uri = [Uri]$issuer
if ($uri.Scheme -ne 'https' -or $uri.UserInfo) { throw 'Configure a trusted HTTPS Authentik issuer first.' }
$envFile = Join-Path $workspace 'start/win/env/identity.env'
$updated = Update-BillSetupEnvironment ([IO.File]::ReadAllText($envFile)) @{
    IDENTITY_AUTHENTIK_PROVISION_URL=$uri.GetLeftPart([UriPartial]::Authority)
    IDENTITY_AUTHENTIK_PROVISION_TOKEN=$tokens[0].Substring('BILL_PROVISION_TOKEN='.Length)
    IDENTITY_AUTHENTIK_CA_FILE=(Join-Path $workspace '.tools/authentik/tls/ca.crt')
}
Write-BillSetupPrivateFile $envFile $updated
Write-Output 'Administrator provisioning configured in the private Identity environment.'
