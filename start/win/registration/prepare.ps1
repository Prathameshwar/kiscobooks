[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$authPath = Join-Path $repository 'mfes\apps\auth\.env.local'
if (-not (Test-Path -LiteralPath $authPath -PathType Leaf)) { throw 'Configure the private Auth environment first.' }
. (Join-Path $PSScriptRoot '..\platform-setup\configuration.ps1')
$original = [IO.File]::ReadAllText($authPath)
foreach ($name in @('AUTHENTIK_ISSUER', 'NEXTAUTH_URL', 'AUTH_REDIS_URL')) {
    if ($original -notmatch ('(?m)^' + $name + '=\S+')) { throw "Configure $name before enabling registration." }
}
& (Join-Path $PSScriptRoot 'apply-authentik.ps1')
$updated = Update-BillSetupEnvironment $original @{AUTH_REGISTRATION_MODE='manual-review'}
Write-BillSetupPrivateFile $authPath $updated
Write-Output 'Manual-review registration enabled. Restart Auth using stop-web.bat auth and start-web.bat auth.'
