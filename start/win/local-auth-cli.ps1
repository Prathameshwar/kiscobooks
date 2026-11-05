<#
.SYNOPSIS
  Operator commands for the local sign-in provider (docs/local-auth.md §6, §9).

.DESCRIPTION
  Loads start\win\env\identity.env into this process only (nothing is printed or written) and runs
  `python -m identity.local_auth.cli`. Commands:
    rotate-key | retire-keys | purge | reset-setup-administrator
    adopt-users [--email ADDRESS ...] [--all]   move existing accounts from Authentik to local sign-in

.EXAMPLE
  .\local-auth-cli.ps1 adopt-users
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateSet('rotate-key', 'retire-keys', 'purge', 'reset-setup-administrator', 'adopt-users')]
    [string]$Command,
    [Parameter(ValueFromRemainingArguments)][string[]]$Arguments
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
$values = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'identity.env')
foreach ($name in $values.Keys) { [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process') }
$python = Join-Path $Global:BILL_REPO_ROOT 'apis\identity\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Identity has no virtual environment yet; run setup.bat -Component python.' }
& $python -m identity.local_auth.cli $Command @Arguments
exit $LASTEXITCODE
