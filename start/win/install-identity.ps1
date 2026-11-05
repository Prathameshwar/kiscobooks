# Platform installation: Identity schema plus all shipped default values.
# IDENTITY_DATABASE_URL must point to an existing MySQL database.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if (-not $env:IDENTITY_DATABASE_URL) {
    throw 'Set IDENTITY_DATABASE_URL before installing Identity.'
}
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$identityProject = Join-Path $projectRoot 'apis\identity'
& uv run --locked --project $identityProject python -m identity.install
if ($LASTEXITCODE -ne 0) {
    throw "Identity installation failed (exit code $LASTEXITCODE)."
}
