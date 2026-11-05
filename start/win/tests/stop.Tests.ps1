$winRoot = Split-Path -Parent $PSScriptRoot

Describe 'Backend shutdown orchestration' {
    function New-StopFixture {
        $fixture = Join-Path $TestDrive 'stop-fixture'
        New-Item -ItemType Directory -Path (Join-Path $fixture 'lib') -Force | Out-Null
        Remove-Item -LiteralPath (Join-Path $fixture 'calls.txt') -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath (Join-Path $winRoot 'stop-all.ps1') -Destination $fixture
        Set-Content -LiteralPath (Join-Path $fixture 'lib\_common.ps1') -Value @'
$Global:BILL_STOP_TEST_CALLS = Join-Path $PSScriptRoot '..\calls.txt'
function Write-BillLog { param($Message, $Level) Write-Output $Message }
function Get-BillConfig {
    $services = @('identity','audit','catalog','notification','accounting','vouchers','reports','design') |
        ForEach-Object { [pscustomobject]@{code=$_;port=8000} }
    return [pscustomobject]@{services=@($services);infra=[pscustomobject]@{
        nginx=[pscustomobject]@{listen_port=8090};redis=[pscustomobject]@{port=6379;host='127.0.0.1'}}}
}
'@
        Set-Content -LiteralPath (Join-Path $fixture 'lib\runtime.ps1') -Value @'
function Stop-BillComponent {
    param($Name, $Port, $HostName)
    Add-Content -LiteralPath $Global:BILL_STOP_TEST_CALLS -Value $Name
    if ($Name -eq 'identity') { throw 'intentional API stop failure' }
}
'@
        foreach ($name in @('report-workers','audit-workers','account-review','tax-review','reference-sync','rabbitmq-local')) {
            $body = @'
param($Action, $Worker)
Add-Content -LiteralPath (Join-Path $PSScriptRoot 'calls.txt') -Value ((Split-Path -Leaf $PSCommandPath) + ':' + $Action + ':' + $Worker)
if ($Worker) { exit 7 }
exit 0
'@
            Set-Content -LiteralPath (Join-Path $fixture "$name.ps1") -Value $body
        }
        return $fixture
    }
    It 'stops every supported delivery worker and continues after worker and API failures' {
        $fixture = New-StopFixture
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'stop-all.ps1')
        $LASTEXITCODE | Should Be 1
        $calls = Get-Content -LiteralPath (Join-Path $fixture 'calls.txt')
        ($calls -contains 'audit-workers.ps1:stop:all') | Should Be $true
        ($calls -contains 'report-workers.ps1:stop:all') | Should Be $true
        foreach ($component in @('nginx','identity','audit','catalog','notification','accounting','vouchers','reports','design','redis')) {
            ($calls -contains $component) | Should Be $true
        }
        foreach ($worker in @('account-review','tax-review','reference-sync','rabbitmq-local')) {
            ($calls -contains ($worker + '.ps1:stop:')) | Should Be $true
        }
        ($output -join "`n") | Should Not Match 'All launcher-managed backend components stopped'
    }
    It 'continues stopping APIs if launching a worker stop command throws' {
        $fixture = New-StopFixture
        Add-Content -LiteralPath (Join-Path $fixture 'lib\_common.ps1') -Value 'function powershell.exe { throw "intentional child launch failure" }'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'stop-all.ps1') 2>&1 | Out-Null
        $LASTEXITCODE | Should Be 1
        ((Get-Content -LiteralPath (Join-Path $fixture 'calls.txt')) -contains 'redis') | Should Be $true
    }
    It 'does not stop anything or report completion during WhatIf' {
        $fixture = New-StopFixture
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'stop-all.ps1') -WhatIf
        $LASTEXITCODE | Should Be 0
        Test-Path -LiteralPath (Join-Path $fixture 'calls.txt') | Should Be $false
        ($output -join "`n") | Should Not Match 'All launcher-managed backend components stopped'
    }
}

Describe 'All delivery worker shutdown' {
    It 'preserves a reused PID, reports failure, and still clears other stopped workers' {
        $workspace = Join-Path $TestDrive 'worker-workspace'
        $fixture = Join-Path $workspace 'start\win'
        $runtime = Join-Path $workspace 'runtime'
        New-Item -ItemType Directory -Path (Join-Path $fixture 'lib'), $runtime -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $winRoot 'audit-workers.ps1') -Destination $fixture
        Copy-Item -LiteralPath (Join-Path $winRoot 'lib\runtime.ps1') -Destination (Join-Path $fixture 'lib')
        @{pid=$PID;started=0} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'identity-publisher.json')
        @{pid=123456789;started=0} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'reports-worker.json')
        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixture 'audit-workers.ps1') -Action stop -Worker all -RuntimeDirectory $runtime 2>&1
        $LASTEXITCODE | Should Be 1
        Test-Path -LiteralPath (Join-Path $runtime 'identity-publisher.json') | Should Be $true
        Test-Path -LiteralPath (Join-Path $runtime 'reports-worker.json') | Should Be $false
        ($output -join "`n") | Should Match 'Stopped owned worker: notification-scheduler'
        foreach ($worker in @('vouchers-sources', 'vouchers-executions', 'accounting-posting-delivery')) {
            ($output -join "`n") | Should Match ('Stopped owned worker: ' + $worker)
        }
        @($output | Where-Object { $_ -like 'Stopped owned worker: *' }).Count | Should Be 24
        Get-Process -Id $PID | Should Not Be $null
    }
}
