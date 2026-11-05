[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $PSScriptRoot '../platform-setup/configuration.ps1')
$authFile = Join-Path $workspace 'mfes/apps/auth/.env.local'
$authContent = [IO.File]::ReadAllText($authFile)
$issuer = [Uri][regex]::Match($authContent, '(?m)^AUTHENTIK_ISSUER=([^\r\n]+)').Groups[1].Value.Trim()
$authUrl = [Uri][regex]::Match($authContent, '(?m)^NEXTAUTH_URL=([^\r\n]+)').Groups[1].Value.Trim()
$slugMatch = [regex]::Match($issuer.AbsolutePath, '^/application/o/([a-zA-Z0-9_-]+)/?$')
if (!$issuer.IsAbsoluteUri -or $issuer.Scheme -ne 'https' -or $issuer.UserInfo -or $issuer.Query -or $issuer.Fragment -or
    !$slugMatch.Success) { throw 'Configure a trusted Authentik issuer first.' }
$applicationSlug = $slugMatch.Groups[1].Value
if (!$authUrl.IsAbsoluteUri -or $authUrl.UserInfo -or $authUrl.Query -or $authUrl.Fragment -or $authUrl.AbsolutePath -ne '/' -or
    ($authUrl.Scheme -ne 'https' -and !($authUrl.Scheme -eq 'http' -and $authUrl.IsLoopback))) { throw 'Configure a trusted KiscoBooks sign-in URL first.' }
Write-BillSetupPrivateFile $authFile (Update-BillSetupEnvironment $authContent @{ AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED='false' })
# This also enables administrator email when the same SMTP settings are present.
& (Join-Path $PSScriptRoot 'prepare-administrator-recovery.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Administrator recovery preparation failed.' }
& (Join-Path $PSScriptRoot 'apply-authentik.ps1') -Blueprint 'authentik-self-service-recovery.yaml'
if ($LASTEXITCODE -ne 0) { throw 'Self-service recovery blueprint could not be applied.' }
$folder = Join-Path $PSScriptRoot '../authentik-vm'
$connection = Get-Content -LiteralPath (Join-Path $folder 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection.' }
$arguments = @('-F','NUL','-i',(Join-Path $folder 'id_ed25519'),'-o',"UserKnownHostsFile=$(Join-Path $folder 'known_hosts')",'-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=10',"$($connection.username)@$($connection.ip_address)")
$returnUrl = $authUrl.GetLeftPart([UriPartial]::Authority) + '/login?recovery=complete'
$encodedUrl = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($returnUrl))
$source = "import base64`nBILL_RECOVERY_RETURN_URL=base64.b64decode('$encodedUrl').decode()`nBILL_RECOVERY_APPLICATION_SLUG='$applicationSlug'`n" + [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'prepare-password-recovery.py'))
$result = @($source | & ssh.exe @arguments 'sudo docker compose --project-directory /opt/bill-authentik exec -T server ak shell 2>/dev/null')
if ($LASTEXITCODE -ne 0) { throw 'Native self-service recovery preparation failed.' }
$flags = @($result | Where-Object { $_ -match '^BILL_SELF_SERVICE_RECOVERY_ENABLED=(true|false)$' })
if ($flags.Count -ne 1) { throw 'Provider did not return the expected recovery status.' }
$enabled = $flags[0].Substring('BILL_SELF_SERVICE_RECOVERY_ENABLED='.Length)
Write-BillSetupPrivateFile $authFile (Update-BillSetupEnvironment ([IO.File]::ReadAllText($authFile)) @{ AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED=$enabled })
Write-Output "Self-service recovery enabled: $enabled. Restart Auth and Identity to load the configuration."
if ($enabled -eq 'false') { Write-Output 'No SMTP is configured. The forgot-password page offers administrator assistance. Rerun this script after configuring Authentik email.' }
