# Prepare automatic enrollment using the installation's existing local broker.
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$EnvDirectory = '')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
if (!$EnvDirectory) { $EnvDirectory = $Global:BILL_ENV_DIR }
$identityPath = Join-Path $EnvDirectory 'identity.env'
$catalogPath = Join-Path $EnvDirectory 'catalog.env'
$identity = Read-BillEnvironment $identityPath
$catalog = Read-BillEnvironment $catalogPath
if (!$identity['IDENTITY_AUDIT_BROKER_URL'] -or !$identity['IDENTITY_AUDIT_BROKER_USER']) {
    throw 'Configure the local broker first; no environment files were changed.'
}
if (@($identity.Keys | Where-Object { $_ -match '^IDENTITY_(CATALOG_SOURCE_|SOURCE_)' }).Count -or
    @($catalog.Keys | Where-Object { $_ -match '^CATALOG_(IDENTITY_SOURCE|SOURCE_)' }).Count) {
    throw 'Catalog source configuration already exists. Review it rather than replace credentials.'
}
function New-EnrollmentSecret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes)
}
$requestSecret = New-EnrollmentSecret
$responseSecret = New-EnrollmentSecret
$eventSecret = New-EnrollmentSecret
$credentials = @{current=@{secret=$requestSecret;scopes=@();allow_actor_authorization=$true;allow_enrolled_companies=$true}}
$source = @{base_url='http://127.0.0.1:8001';request_key_id='current';request_secret=$requestSecret;response_secrets=@{current=$responseSecret}}
$identityAdd = @(
    ('IDENTITY_CATALOG_SOURCE_CREDENTIALS=' + ($credentials | ConvertTo-Json -Depth 5 -Compress)),
    ('IDENTITY_CATALOG_SOURCE_RESPONSE_SECRET=' + $responseSecret),
    ('IDENTITY_SOURCE_EVENT_SECRET=' + $eventSecret),
    ('IDENTITY_SOURCE_BROKER_URL=' + $identity['IDENTITY_AUDIT_BROKER_URL']),
    ('IDENTITY_SOURCE_BROKER_USER=' + $identity['IDENTITY_AUDIT_BROKER_USER'])
)
$catalogAdd = @(
    ('CATALOG_IDENTITY_SOURCE=' + ($source | ConvertTo-Json -Depth 5 -Compress)),
    'CATALOG_SOURCE_DISCOVERY=true',
    ('CATALOG_SOURCE_EVENT_SECRET=' + $eventSecret),
    ('CATALOG_SOURCE_BROKER_URL=' + $identity['IDENTITY_AUDIT_BROKER_URL']),
    ('CATALOG_SOURCE_BROKER_USER=' + $identity['IDENTITY_AUDIT_BROKER_USER'])
)
if ($PSCmdlet.ShouldProcess('Identity and Catalog private environment files', 'Configure enrolled-company source delivery')) {
    Add-Content -LiteralPath $identityPath -Value (@('') + $identityAdd) -Encoding UTF8
    Add-Content -LiteralPath $catalogPath -Value (@('') + $catalogAdd) -Encoding UTF8
}
Write-BillLog 'Enrollment configuration prepared. Apply migrations and enrollment backfill, then restart Identity/Catalog and start their source workers.' 'OK'
