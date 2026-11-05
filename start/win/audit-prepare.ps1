<# Synchronize private local publisher/consumer credentials from native contracts. #>
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$EnvDirectory = '')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/_common.ps1')
. (Join-Path $PSScriptRoot 'lib/runtime.ps1')
. (Join-Path $PSScriptRoot 'platform-setup/configuration.ps1')
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (!$EnvDirectory) { $EnvDirectory = Join-Path $PSScriptRoot 'env' }
$python = Join-Path $workspace 'apis/audit/.venv/Scripts/python.exe'
$contractJson = @(& $python (Join-Path $PSScriptRoot 'audit-contracts.py'))
if ($LASTEXITCODE -ne 0 -or $contractJson.Count -ne 1) { throw 'Cannot read native audit contracts.' }
$contracts = $contractJson[0] | ConvertFrom-Json
$auditPath = Join-Path $EnvDirectory 'audit.env'
$auditValues = Read-BillEnvironment $auditPath
if (!$auditValues['AUDIT_BROKER_URL']) { throw 'Configure the private Audit broker connection first.' }
$broker = $auditValues['AUDIT_BROKER_URL']
$sources = @{}
if ($auditValues['AUDIT_SOURCE_CREDENTIALS']) {
    ($auditValues['AUDIT_SOURCE_CREDENTIALS'] | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $sources[$_.Name] = $_.Value }
}
$original = @{}
$updated = @{}
foreach ($contract in $contracts.PSObject.Properties) {
    $service = $contract.Name
    $file = if ($service -eq 'audit') { 'audit-publisher.env' } else { $service + '.env' }
    $path = Join-Path $EnvDirectory $file
    $content = if (Test-Path -LiteralPath $path) { [IO.File]::ReadAllText($path) } else { '' }
    $original[$path] = $content
    $values = if ($content) { Read-BillEnvironment $path } else { @{} }
    $prefix = if ($service -eq 'audit') { 'AUDIT_PUBLISHER_' } else { $service.ToUpperInvariant() + '_AUDIT_' }
    $keyName = if ($service -eq 'audit') { 'KEY_ID' } else { 'EVENT_KEY_ID' }
    $keyId = $values[$prefix + $keyName]
    if (!$keyId) { $keyId = $service + '.current' }
    $existing = $sources[$keyId]
    if ($existing -and $existing.issuer -ne $service) { throw ('Audit key belongs to another issuer: ' + $service) }
    $secret = $values[$prefix + 'EVENT_SECRET']
    if (!$secret -and $existing) { $secret = $existing.secret }
    if (!$secret) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $secret = [Convert]::ToBase64String($bytes)
    }
    if ($existing -and $existing.secret -ne $secret) { throw ('Publisher/consumer secret mismatch: ' + $service) }
    if ($values[$prefix + 'BROKER_URL'] -and $values[$prefix + 'BROKER_URL'] -ne $broker) { throw ('Publisher uses another broker: ' + $service) }
    $user = $values[$prefix + 'BROKER_USER']
    if (!$user) { $user = (Read-BillEnvironment (Join-Path $EnvDirectory 'identity.env'))['IDENTITY_AUDIT_BROKER_USER'] }
    if (!$user) { throw ('Private publisher broker identity missing: ' + $service) }
    $sourceEvents = @($contract.Value | ForEach-Object { [string]$_ })
    $sources[$keyId] = [ordered]@{issuer=$service; broker_user=$user; secret=$secret; event_types=$sourceEvents}
    $settings = @{}
    $settings[$prefix + 'BROKER_URL'] = $broker
    $settings[$prefix + 'BROKER_USER'] = $user
    $settings[$prefix + 'EVENT_SECRET'] = $secret
    $settings[$prefix + $keyName] = $keyId
    if ($service -eq 'audit') { $settings['AUDIT_PUBLISHER_DATABASE_URL'] = $auditValues['AUDIT_DATABASE_URL'] }
    if ($service -in @('identity','notification') -and !$values[$prefix + 'PUBLISH_AFTER']) {
        $settings[$prefix + 'PUBLISH_AFTER'] = [DateTime]::UtcNow.ToString('o')
    }
    $updated[$path] = Update-BillSetupEnvironment $content $settings
}
$original[$auditPath] = [IO.File]::ReadAllText($auditPath)
$orderedSources = [ordered]@{}
foreach ($key in @($sources.Keys | Sort-Object)) { $orderedSources[$key] = $sources[$key] }
$updated[$auditPath] = Update-BillSetupEnvironment $original[$auditPath] @{
    AUDIT_SOURCE_CREDENTIALS=($orderedSources | ConvertTo-Json -Depth 8 -Compress)
}
if (!$PSCmdlet.ShouldProcess('Local audit pipeline', 'Synchronize eight explicit producer contracts and private credentials')) { return }
$written = @()
try {
    foreach ($path in $updated.Keys) {
        $written += $path
        Write-BillSetupPrivateFile $path $updated[$path]
    }
} catch {
    foreach ($path in $written) { Write-BillSetupPrivateFile $path $original[$path] }
    throw 'Audit setup failed; original private environment contents restored.'
}
Write-Output 'Audit credentials synchronized for eight producers. Existing historical cutoffs preserved.'
