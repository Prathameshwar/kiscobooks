[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $PSScriptRoot '../platform-setup/configuration.ps1')
& (Join-Path $PSScriptRoot 'apply-authentik.ps1') -Blueprint 'authentik-administrator-recovery.yaml'
if ($LASTEXITCODE -ne 0) { throw 'Recovery blueprint could not be applied.' }
$folder = Join-Path $PSScriptRoot '../authentik-vm'
$connection = Get-Content -LiteralPath (Join-Path $folder 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection.' }
$arguments = @('-F','NUL','-i',(Join-Path $folder 'id_ed25519'),'-o',"UserKnownHostsFile=$(Join-Path $folder 'known_hosts')",'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=10',"$($connection.username)@$($connection.ip_address)")
$result = @(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'prepare-administrator-recovery.py') -Raw | & ssh.exe @arguments 'sudo docker compose --project-directory /opt/bill-authentik exec -T server ak shell 2>/dev/null')
if ($LASTEXITCODE -ne 0) { throw 'Restricted Authentik recovery preparation failed.' }
$tokens = @($result | Where-Object { $_ -match '^BILL_RECOVERY_TOKEN=[A-Za-z0-9_-]{32,}$' })
$stages = @($result | Where-Object { $_ -match '^BILL_RECOVERY_EMAIL_STAGE=(disabled|[0-9a-f-]{36})$' })
if ($tokens.Count -ne 1 -or $stages.Count -ne 1) { throw 'Provider did not return the expected private configuration.' }
$issuer = [regex]::Match([IO.File]::ReadAllText((Join-Path $workspace 'mfes/apps/auth/.env.local')), '(?m)^AUTHENTIK_ISSUER=([^\r\n]+)').Groups[1].Value.Trim()
$uri = [Uri]$issuer
if ($uri.Scheme -ne 'https' -or $uri.UserInfo) { throw 'Configure a trusted HTTPS Authentik issuer first.' }
$envFile = Join-Path $workspace 'start/win/env/identity.env'
$values = @{ IDENTITY_AUTHENTIK_RECOVERY_URL=$uri.GetLeftPart([UriPartial]::Authority); IDENTITY_AUTHENTIK_RECOVERY_TOKEN=$tokens[0].Substring('BILL_RECOVERY_TOKEN='.Length) }
$stage = $stages[0].Substring('BILL_RECOVERY_EMAIL_STAGE='.Length)
$content = [IO.File]::ReadAllText($envFile)
if ($stage -ne 'disabled') { $values.IDENTITY_AUTHENTIK_RECOVERY_EMAIL_STAGE=$stage }
else { $content = [regex]::Replace($content, '(?m)^IDENTITY_AUTHENTIK_RECOVERY_EMAIL_STAGE=[^\r\n]*\r?\n?', '') }
Write-BillSetupPrivateFile $envFile (Update-BillSetupEnvironment $content $values)
& (Join-Path $PSScriptRoot 'apply-authentik.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Registration recovery handoff could not be applied.' }
Write-Output 'Restricted recovery link service configured in the private Identity environment.'
if ($stage -eq 'disabled') { Write-Output 'Recovery email is disabled until Authentik SMTP host and sender are configured. Rerun this script after configuration, then restart Identity.' }
else { Write-Output 'Recovery email stage enabled. Delivery is handled by Authentik.' }
