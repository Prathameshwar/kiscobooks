[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../platform-setup/configuration.ps1')
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$credential = Get-Content -LiteralPath (Join-Path $workspace '.tools/rabbitmq-runtime/credentials.json') -Raw | ConvertFrom-Json
$identityPath = Join-Path $workspace 'start/win/env/identity.env'
$auditPath = Join-Path $workspace 'start/win/env/audit.env'
$identity = [IO.File]::ReadAllText($identityPath)
$audit = [IO.File]::ReadAllText($auditPath)
$existing = [regex]::Match($identity, '(?m)^IDENTITY_AUDIT_EVENT_SECRET=([^\r\n]+)').Groups[1].Value
if (!$existing) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $existing = [Convert]::ToBase64String($bytes)
}
$broker = 'amqp://' + [Uri]::EscapeDataString($credential.user) + ':' + [Uri]::EscapeDataString($credential.password) + '@127.0.0.1:5672/bill_identity_test'
$events = @(& (Join-Path $workspace 'apis/identity/.venv/Scripts/python.exe') -c 'import json; from identity.events.audit_contract import AUDIT_EVENT_TYPES; print(json.dumps(sorted(AUDIT_EVENT_TYPES)))')
if ($LASTEXITCODE -ne 0 -or $events.Count -ne 1) { throw 'Cannot read the Identity audit contract.' }
$sources = @{}
$configured = [regex]::Match($audit, '(?m)^AUDIT_SOURCE_CREDENTIALS=([^\r\n]+)').Groups[1].Value
if ($configured) { ($configured | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $sources[$_.Name]=$_.Value } }
if ($sources['identity.current'] -and $sources['identity.current'].issuer -ne 'identity') { throw 'Identity audit key belongs to another source.' }
Add-Type -AssemblyName System.Web.Extensions
$serializer = New-Object System.Web.Script.Serialization.JavaScriptSerializer
$eventNames = @($serializer.DeserializeObject([string]$events[0]) | ForEach-Object { [string]$_ })
if ($eventNames.Count -lt 5 -or @($eventNames | Where-Object { $_ -notmatch '^[a-z][a-z0-9_.-]+$' }).Count) { throw 'Invalid Identity audit event list.' }
$sources['identity.current'] = @{issuer='identity';broker_user=$credential.user;secret=$existing;event_types=$eventNames}
$values = @{IDENTITY_AUDIT_BROKER_URL=$broker;IDENTITY_AUDIT_BROKER_USER=$credential.user;IDENTITY_AUDIT_EVENT_SECRET=$existing}
# Preserve the initial rollout boundary; historical personal data stays held.
if ($identity -notmatch '(?m)^IDENTITY_AUDIT_PUBLISH_AFTER=') { $values['IDENTITY_AUDIT_PUBLISH_AFTER']=[DateTime]::UtcNow.ToString('o') }
Write-BillSetupPrivateFile $identityPath (Update-BillSetupEnvironment $identity $values)
Write-BillSetupPrivateFile $auditPath (Update-BillSetupEnvironment $audit @{AUDIT_BROKER_URL=$broker;AUDIT_SOURCE_CREDENTIALS=($sources | ConvertTo-Json -Depth 8 -Compress)})
Write-Output 'Local signed Identity audit delivery configured; historical events remain held.'
