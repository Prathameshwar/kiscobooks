# Add scoped local secrets without replacing other environment settings.
[CmdletBinding(SupportsShouldProcess = $true)]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
$identityPath = Join-Path $Global:BILL_ENV_DIR 'identity.env'
$identity = Read-BillEnvironment $identityPath
$credentials = @{}
if ($identity.ContainsKey('IDENTITY_REFERENCE_SYNC_CREDENTIALS')) {
    $existing = $identity['IDENTITY_REFERENCE_SYNC_CREDENTIALS'] | ConvertFrom-Json
    foreach ($property in $existing.PSObject.Properties) { $credentials[$property.Name] = [string]$property.Value }
}
if (@($credentials.Keys | Where-Object { $_ -notin @('catalog', 'accounting') }).Count) {
    throw 'Unknown reference delivery credentials; configuration left untouched.'
}
$updates = @()
foreach ($service in @('catalog', 'accounting')) {
    $path = Join-Path $Global:BILL_ENV_DIR "$service.env"
    $values = Read-BillEnvironment $path
    if (-not $credentials.ContainsKey($service)) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $credentials[$service] = [Convert]::ToBase64String($bytes)
    }
    if ($credentials[$service].Length -lt 32) { throw 'Invalid reference credential; configuration left untouched.' }
    if ($values.ContainsKey('REFERENCE_SYNC_SECRET') -and $values['REFERENCE_SYNC_SECRET'] -ne $credentials[$service]) {
        throw "$service credential differs from Identity; configuration left untouched."
    }
    $lines = @(Get-Content -LiteralPath $path -Encoding UTF8 | Where-Object { $_ -notmatch '^REFERENCE_SYNC_(SECRET|IDENTITY_URL|SERVICE)=' })
    $lines += @("REFERENCE_SYNC_SERVICE=$service", 'REFERENCE_SYNC_IDENTITY_URL=http://127.0.0.1:8001', "REFERENCE_SYNC_SECRET=$($credentials[$service])")
    $updates += [pscustomobject]@{ Path = $path; Lines = $lines }
}
$lines = @(Get-Content -LiteralPath $identityPath -Encoding UTF8 | Where-Object { $_ -notmatch '^IDENTITY_REFERENCE_SYNC_CREDENTIALS=' })
$lines += 'IDENTITY_REFERENCE_SYNC_CREDENTIALS=' + ($credentials | ConvertTo-Json -Compress)
$updates += [pscustomobject]@{ Path = $identityPath; Lines = $lines }
foreach ($update in $updates) {
    if ($PSCmdlet.ShouldProcess($update.Path, 'Write scoped reference synchronization configuration')) {
        Set-Content -LiteralPath $update.Path -Value $update.Lines -Encoding UTF8
    }
}
Write-BillLog 'Reference delivery configuration prepared. Restart Identity and start the workers after migrations.' 'OK'
