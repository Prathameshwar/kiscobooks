[CmdletBinding()]
param([ValidateSet('authentik-enrollment.yaml', 'authentik-password-change.yaml', 'authentik-administrator-recovery.yaml', 'authentik-self-service-recovery.yaml')][string]$Blueprint = 'authentik-enrollment.yaml')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$vmFolder = Join-Path $PSScriptRoot '..\authentik-vm'
$connection = Get-Content -LiteralPath (Join-Path $vmFolder 'connection.json') -Raw | ConvertFrom-Json
if ($connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or
    $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Invalid VM connection details.' }
$arguments = @('-F', 'NUL', '-i', (Join-Path $vmFolder 'id_ed25519'), '-o',
    "UserKnownHostsFile=$(Join-Path $vmFolder 'known_hosts')", '-o', 'StrictHostKeyChecking=yes',
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', "$($connection.username)@$($connection.ip_address)")
$blueprintContent = [IO.File]::ReadAllText((Join-Path $PSScriptRoot $Blueprint))
if ($Blueprint -eq 'authentik-self-service-recovery.yaml') {
    $workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
    $authContent = [IO.File]::ReadAllText((Join-Path $workspace 'mfes/apps/auth/.env.local'))
    $authUrl = [Uri][regex]::Match($authContent, '(?m)^NEXTAUTH_URL=([^\r\n]+)').Groups[1].Value.Trim()
    if (!$authUrl.IsAbsoluteUri -or $authUrl.UserInfo -or $authUrl.Query -or $authUrl.Fragment -or $authUrl.AbsolutePath -ne '/' -or
        ($authUrl.Scheme -ne 'https' -and !($authUrl.Scheme -eq 'http' -and $authUrl.IsLoopback))) { throw 'Configure a trusted KiscoBooks sign-in URL first.' }
    $returnUrl = $authUrl.GetLeftPart([UriPartial]::Authority) + '/login?recovery=complete'
    # A JSON string is also a quoted YAML scalar. It is never interpolated into shell code.
    $blueprintContent = $blueprintContent.Replace('__BILL_RECOVERY_RETURN_URL__', ($returnUrl | ConvertTo-Json -Compress))
}
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($blueprintContent))
$target = switch ($Blueprint) { 'authentik-password-change.yaml' { 'bill-password-change.yaml' }; 'authentik-administrator-recovery.yaml' { 'bill-administrator-recovery.yaml' }; 'authentik-self-service-recovery.yaml' { 'bill-self-service-recovery.yaml' }; default { 'bill-registration.yaml' } }
$upload = "set -o pipefail; sudo install -o 1000 -g 1000 -m 600 /dev/null /opt/bill-authentik/blueprints/$target.pending && base64 --decode --ignore-garbage | sudo tee /opt/bill-authentik/blueprints/$target.pending >/dev/null && sudo mv /opt/bill-authentik/blueprints/$target.pending /opt/bill-authentik/blueprints/$target"
$encoded | & ssh.exe @arguments $upload
if ($LASTEXITCODE -ne 0) { throw 'Could not install the Authentik enrollment blueprint.' }
$previousPreference = $ErrorActionPreference
try {
    # Authentik logs startup diagnostics to stderr even on successful application.
    # Capture them privately and use the native exit code as the outcome.
    $ErrorActionPreference = 'Continue'
    $applyOutput = @(& ssh.exe @arguments "sudo docker compose --project-directory /opt/bill-authentik exec -T server ak apply_blueprint /blueprints/custom/$target" 2>&1)
    $applyExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousPreference }
if ($applyExit -ne 0) { throw 'Authentik rejected the blueprint. Check the provider deployment logs.' }
Write-Output "Authentik blueprint applied: $Blueprint"
