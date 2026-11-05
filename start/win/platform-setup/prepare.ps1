[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'configuration.ps1')
$taskRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
Initialize-BillPlatformSetup $taskRoot
Write-Output 'First-run setup configured. Restart Identity and Auth, then open http://localhost:4310/setup.'
Write-Output 'The setup key is saved privately in start/win/platform-setup/setup-key.txt.'
