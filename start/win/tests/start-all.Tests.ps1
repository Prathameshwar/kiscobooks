$winRoot = Split-Path -Parent $PSScriptRoot

Describe 'Backend startup with Authentik tunnel' {
    function New-StartAllFixture {
        $fixture = Join-Path $TestDrive 'start-all-fixture'
        New-Item -ItemType Directory -Path (Join-Path $fixture 'lib'), (Join-Path $fixture 'authentik-vm') -Force | Out-Null
        Remove-Item -LiteralPath (Join-Path $fixture 'calls.txt') -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath (Join-Path $winRoot 'start-all.ps1') -Destination $fixture
        Set-Content -LiteralPath (Join-Path $fixture 'lib\_common.ps1') -Value @'
$Global:BILL_START_TEST_CALLS = Join-Path $PSScriptRoot '..\calls.txt'
function Get-BillConfig { return @{} }
function Get-BillAuthProvider { return 'authentik' }
function Write-BillLog { param($Message, $Level) Write-Output $Message }
'@
        Set-Content -LiteralPath (Join-Path $fixture 'lib\runtime.ps1') -Value @'
function Start-BillInfrastructure {
    param($Name, $Config)
    Add-Content -LiteralPath $Global:BILL_START_TEST_CALLS -Value $Name
}

'@
        Set-Content -LiteralPath (Join-Path $fixture 'lib\health-check.ps1') -Value @'
function Get-BillHealth {
    param($Config)
    return [pscustomobject]@{Component='identity';Status='UP'}
}
function Write-BillHealth { param($Rows) }
'@
        foreach ($name in @('rabbitmq-local','start-services')) {
            Set-Content -LiteralPath (Join-Path $fixture "$name.ps1") -Value @'
param($Action)
Add-Content -LiteralPath (Join-Path $PSScriptRoot 'calls.txt') -Value ((Split-Path -Leaf $PSCommandPath) + ':' + $Action)
exit 0
'@
        }
        Set-Content -LiteralPath (Join-Path $fixture 'authentik-vm\tunnel.ps1') -Value @'
param($Action)
Add-Content -LiteralPath (Join-Path $PSScriptRoot '..\calls.txt') -Value ('authentik-tunnel:' + $Action)
exit 0
'@
        return $fixture
    }
    It 'starts the managed tunnel before APIs and continues the backend startup' {
        $fixture = New-StartAllFixture
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'start-all.ps1') | Out-Null
        $LASTEXITCODE | Should Be 0
        $calls = @(Get-Content -LiteralPath (Join-Path $fixture 'calls.txt'))
        $calls[0] | Should Be 'authentik-tunnel:start'
        ($calls -contains 'redis') | Should Be $true
        ($calls -contains 'rabbitmq-local.ps1:start') | Should Be $true
        ($calls -contains 'start-services.ps1:') | Should Be $true
        ($calls -contains 'nginx') | Should Be $true
    }
    It 'reports startup failure when the tunnel fails even when APIs are healthy' {
        $fixture = New-StartAllFixture
        $tunnelText = Get-Content -LiteralPath (Join-Path $fixture 'authentik-vm\tunnel.ps1') -Raw
        Set-Content -LiteralPath (Join-Path $fixture 'authentik-vm\tunnel.ps1') -Value ($tunnelText -replace 'exit 0', 'exit 7')
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'start-all.ps1')
        $LASTEXITCODE | Should Be 1
        ((Get-Content -LiteralPath (Join-Path $fixture 'calls.txt')) -contains 'nginx') | Should Be $true
        ($output -join "`n") | Should Match 'Authentik.*tunnel.*failed'
        ($output -join "`n") | Should Not Match 'Backend components ready'
    }
    It 'does not start the tunnel or backend during WhatIf' {
        $fixture = New-StartAllFixture
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'start-all.ps1') -WhatIf | Out-Null
        $LASTEXITCODE | Should Be 0
        Test-Path -LiteralPath (Join-Path $fixture 'calls.txt') | Should Be $false
    }
    It 'identifies audit delivery when APIs are ready but delivery is degraded' {
        $fixture = New-StartAllFixture
        $health = Join-Path $fixture 'lib/health-check.ps1'
        $text = Get-Content $health -Raw
        Set-Content $health ($text.Replace("Component='identity';Status='UP'", "Component='Audit delivery';Status='DEGRADED'"))
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'start-all.ps1')
        $LASTEXITCODE | Should Be 1
        ($output -join "`n") | Should Match 'Unhealthy components: Audit delivery'
        ($output -join "`n") | Should Not Match 'database migrations'
    }
}

Describe 'Authentik tunnel reuse readiness' {
    function New-TunnelFixture {
        $fixture = Join-Path $TestDrive 'tunnel-fixture'
        New-Item -ItemType Directory -Path (Join-Path $fixture 'lib'), (Join-Path $fixture 'authentik-vm') -Force | Out-Null
        Remove-Item -LiteralPath (Join-Path $fixture 'missing-listener') -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath (Join-Path $winRoot 'authentik-vm\tunnel.ps1') -Destination (Join-Path $fixture 'authentik-vm')
        Set-Content -LiteralPath (Join-Path $fixture 'lib\_common.ps1') -Value @'
$Global:BILL_TUNNEL_TEST_ROOT = Split-Path -Parent $PSScriptRoot
function Wait-ForPort {
    param($HostName, $Port, $TimeoutSeconds)
    return -not (Test-Path -LiteralPath (Join-Path $Global:BILL_TUNNEL_TEST_ROOT 'missing-listener'))
}
'@
        Set-Content -LiteralPath (Join-Path $fixture 'lib\runtime.ps1') -Value @'
function Get-BillManagedProcess { param($Name, [switch]$ForStart) return [pscustomobject]@{HasExited=$false} }
function Start-BillProcess { throw 'Must not launch a duplicate tunnel.' }
'@
        return $fixture
    }
    It 'reuses an existing managed tunnel without starting another process' {
        $fixture = New-TunnelFixture
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'authentik-vm\tunnel.ps1') -Action start
        $LASTEXITCODE | Should Be 0
        ($output -join "`n") | Should Match 'already running'
    }
    It 'does not report success when a managed tunnel has no listening ports' {
        $fixture = New-TunnelFixture
        Set-Content -LiteralPath (Join-Path $fixture 'missing-listener') -Value 'test'
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'authentik-vm\tunnel.ps1') -Action start
        $LASTEXITCODE | Should Be 1
        ($output -join "`n") | Should Not Match 'already running'
        ($output -join "`n") | Should Not Match 'duplicate tunnel'
    }
}
