[CmdletBinding()]
param([switch]$DryRun)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/_common.ps1')
$python = Join-Path $Global:BILL_REPO_ROOT 'apis/identity/.venv/Scripts/python.exe'
$environment = Join-Path $Global:BILL_ENV_DIR 'identity.env'
try {
    if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $environment)) {
        throw 'Prepare the Identity runtime and private environment first.'
    }
    $arguments = @('-m', 'identity.seeds.branding', '--env-file', $environment)
    if ($DryRun) { $arguments += '--dry-run' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Branding synchronization failed.' }
    exit 0
} catch {
    Write-BillLog 'Branding synchronization failed. Check the private Identity deployment configuration.' 'ERROR'
    exit 1
}
