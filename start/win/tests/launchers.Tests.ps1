$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\health-check.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')

Describe 'Windows backend launcher regressions' {
    foreach ($launcherName in @('start-all.bat', 'start-web.bat', 'stop-all.bat', 'stop-web.bat')) {
        It "$launcherName waits after success and failure and preserves the exit code" {
            $launcher = Get-Content (Join-Path $winRoot $launcherName) -Raw
            # Exercise the batch control flow without starting services or waiting for input.
            $fixture = $launcher -replace '(?m)^powershell[^\r\n]*', 'cmd.exe /c exit 7'
            $fixture = $fixture -replace '(?im)^\s*pause[^\r\n]*', 'echo PAUSE_REQUESTED'
            $path = Join-Path $TestDrive 'start-failure.bat'
            Set-Content -LiteralPath $path -Value $fixture -Encoding ASCII
            $previous = $env:BILL_NO_PAUSE
            try {
                Remove-Item Env:BILL_NO_PAUSE -ErrorAction SilentlyContinue
                $output = & cmd.exe /d /c $path
                $LASTEXITCODE | Should Be 7
                ($output -join "`n") | Should Match 'PAUSE_REQUESTED'
                $env:BILL_NO_PAUSE = '1'
                $output = & cmd.exe /d /c $path
                $LASTEXITCODE | Should Be 7
                ($output -join "`n") | Should Not Match 'PAUSE_REQUESTED'
                Set-Content -LiteralPath $path -Value ($fixture -replace 'exit 7', 'exit 0') -Encoding ASCII
                Remove-Item Env:BILL_NO_PAUSE
                $output = & cmd.exe /d /c $path
                $LASTEXITCODE | Should Be 0
                ($output -join "`n") | Should Match 'PAUSE_REQUESTED'
                $env:BILL_NO_PAUSE = '1'
                $output = & cmd.exe /d /c $path
                $LASTEXITCODE | Should Be 0
                ($output -join "`n") | Should Not Match 'PAUSE_REQUESTED'
            } finally { $env:BILL_NO_PAUSE = $previous }
        }
    }
    It 'the web compatibility alias shares the batch pause and preserves arguments and exit code' {
        $alias = Get-Content (Join-Path $winRoot 'start-web.cmd') -Raw
        $alias | Should Match 'call "%~dp0start-web.bat" %\*'
        $aliasPath = Join-Path $TestDrive 'start-web.cmd'
        Set-Content -LiteralPath $aliasPath -Value $alias -Encoding ASCII
        Set-Content -LiteralPath (Join-Path $TestDrive 'start-web.bat') -Value @('@echo off', 'echo WEB_ARGS=%*', 'echo PAUSE_REQUESTED', 'exit /b 7') -Encoding ASCII
        $output = & cmd.exe /d /c $aliasPath console -WhatIf
        $LASTEXITCODE | Should Be 7
        ($output -join "`n") | Should Match 'WEB_ARGS=console -WhatIf'
        @($output | Where-Object { $_ -eq 'PAUSE_REQUESTED' }).Count | Should Be 1
    }
    It 'strips untrusted actor context and rate limits public Identity requests' {
        $routing = Get-Content (Join-Path $winRoot 'conf\bill.conf') -Raw
        $identity = [regex]::Match($routing, 'location /identity/ \{(?<body>.*?)\}', [System.Text.RegularExpressions.RegexOptions]::Singleline).Groups['body'].Value
        $identity | Should Match 'limit_req zone=identity_auth'
        $identity | Should Match 'proxy_set_header X-Actor-Context ""'
        $identity | Should Match 'proxy_set_header X-Actor-Signature ""'
        $identity | Should Match 'proxy_set_header X-Original-URI ""'
    }
    It 'stops APIs through the registry, including vouchers and reports' {
        $text = Get-Content (Join-Path $winRoot 'stop-all.bat') -Raw
        $text | Should Match 'stop-all.ps1'
        $text | Should Not Match 'WINDOWTITLE'
    }
    It 'never kills nginx or Redis globally by image name' {
        foreach ($name in @('stop-nginx.bat', 'stop-redis.bat')) {
            Get-Content (Join-Path $winRoot $name) -Raw | Should Not Match '/IM '
        }
    }
    It 'does not put environment secrets into generated batch launchers' {
        Get-Content (Join-Path $winRoot 'start-services.ps1') -Raw | Should Not Match 'setLines|bill-run-'
    }
    It 'does not treat an open API port with failed readiness as healthy' {
        Mock Wait-ForPort { return $true }
        Mock Invoke-WebRequest { throw 'not ready' }
        $rows = Get-BillHealth -Config (Get-BillConfig)
        @($rows | Where-Object { $_.Kind -eq 'api' -and $_.Status -eq 'UP' }).Count | Should Be 0
    }
    It 'propagates failed Python dependency setup' {
        . (Join-Path $winRoot 'lib\setup-python.ps1')
        Mock Test-Command { return $true }
        Mock Invoke-BillCommand { return $false }
        Mock Write-BillLog {}
        Mock Write-BillStep {}
        Mock Add-BillSummary {}
        Mock uv { 'test uv' }
        { Invoke-BillSetupPython -Services (Get-BillConfig).services } | Should Throw
    }
    It 'preserves special characters and Unicode in environment values' {
        $path = Join-Path $TestDrive 'service.env'
        $value = 'quoted="yes" & %PATH% !value! = ' + [char]0x03A9
        Set-Content -LiteralPath $path -Encoding UTF8 -Value @('# ignored', ('APP_VALUE=' + $value), 'EMPTY=')
        $values = Read-BillEnvironment $path
        $values.APP_VALUE | Should Be $value
        $values.EMPTY | Should Be ''
    }
    It 'rejects malformed and duplicate environment keys without echoing values' {
        $path = Join-Path $TestDrive 'service.env'
        Set-Content -LiteralPath $path -Value @('APP=one','APP=two')
        { Read-BillEnvironment $path } | Should Throw
    }
    It 'refuses to stop a listener without launcher ownership' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $true }
        Mock Stop-Process { throw 'should never stop' }
        { Stop-BillComponent -Name redis -Port 6379 } | Should Throw
        Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It
    }
    It 'makes a repeated stop succeed without launching anything' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Write-BillLog {}
        { Stop-BillComponent -Name reports -Port 8013 } | Should Not Throw
    }
    It 'clears stale backend state and stop markers when already stopped' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Write-BillLog {}
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -ItemType Directory -Path (Join-Path $TestDrive 'runtime') -Force | Out-Null
            $state = Get-BillRuntimePath reports
            $marker = Join-Path $TestDrive 'runtime\reports.stop'
            Set-Content -LiteralPath $state -Value '{}'
            Set-Content -LiteralPath $marker -Value 'stop'
            Stop-BillComponent -Name reports -Port 8013
            Test-Path -LiteralPath $state | Should Be $false
            Test-Path -LiteralPath $marker | Should Be $false
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'preserves process state when a listener remains after shutdown' {
        Mock Get-BillManagedProcess {
            $process = New-Object PSObject
            $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { param($timeout) return $true }
            return $process
        } -ParameterFilter { $Name -eq 'reports' }
        Mock Wait-ForPort { return $true }
        Mock Write-BillLog {}
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -ItemType Directory -Path (Join-Path $TestDrive 'runtime') -Force | Out-Null
            $state = Get-BillRuntimePath reports
            Set-Content -LiteralPath $state -Value '{}'
            { Stop-BillComponent -Name reports -Port 8013 } | Should Throw
            Test-Path -LiteralPath $state | Should Be $true
            Test-Path -LiteralPath (Join-Path $TestDrive 'runtime\reports.stop') | Should Be $true
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'checks the payload, not just HTTP 200' {
        Mock Invoke-WebRequest { [pscustomobject]@{StatusCode=200; Content='{"status":"wrong"}'} }
        Test-BillHttp -Url http://127.0.0.1/health/ready -Status ready | Should Be $false
    }
    It 'reports APIs ready when their liveness and readiness contracts pass' {
        Mock Wait-ForPort { return $true }
        Mock Invoke-WebRequest {
            param($Uri)
            $status = if ($Uri -like '*/health/live') { 'ok' } else { 'ready' }
            [pscustomobject]@{StatusCode=200; Content=('{"status":"' + $status + '"}')}
        }
        $rows = @(Get-BillHealth -Config (Get-BillConfig) -ApiOnly)
        $rows.Count | Should Be 8
        @($rows | Where-Object { $_.Component -eq 'design' }).Count | Should Be 1
        @($rows | Where-Object Status -ne 'UP').Count | Should Be 0
    }
    It 'accepts nginx health responses returned as bytes by Windows PowerShell' {
        Mock Invoke-WebRequest { [pscustomobject]@{StatusCode=200; Content=[Text.Encoding]::UTF8.GetBytes("ok`n")} }
        Test-BillHttp -Url http://127.0.0.1/nginx-health -Status nginx | Should Be $true
    }
    It 'quotes empty arguments and trailing slashes correctly for Windows' {
        ConvertTo-BillArgument '' | Should Be '""'
        ConvertTo-BillArgument 'C:\path with spaces\' | Should Be '"C:\path with spaces\\"'
        ConvertTo-BillArgument 'a"b' | Should Be '"a\"b"'
    }
    It 'rejects recursive setup targets outside the intended root' {
        { Assert-BillChildPath -Path $winRoot -Root $winRoot } | Should Throw
        { Assert-BillChildPath -Path (Join-Path $winRoot '..\..\outside') -Root $winRoot } | Should Throw
        { Assert-BillChildPath -Path (Join-Path $winRoot 'bin\nginx') -Root $winRoot } | Should Not Throw
    }
    It 'encodes special characters in MySQL connection credentials' {
        . (Join-Path $winRoot 'lib\write-envs.ps1')
        $mysql = [pscustomobject]@{superuser='dev@local';password='a:b/#%';host='127.0.0.1';port=3306}
        _BillMysqlUrl -Mysql $mysql -DbName identity | Should Be 'mysql+asyncmy://dev%40local:a%3Ab%2F%23%25@127.0.0.1:3306/identity'
    }
    It 'ignores a stale process record rather than stopping any process' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            @{process_id=123456789; workspace=$Global:BILL_REPO_ROOT; started_ticks='0'; executable='x'} |
                ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
            Get-BillManagedProcess smoke | Should Be $null
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'refuses reused process IDs with a changed start time' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            $process = Get-Process -Id $PID
            @{process_id=$PID; workspace=$Global:BILL_REPO_ROOT; started_ticks='0'; executable=$process.Path} |
                ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
            { Get-BillManagedProcess smoke } | Should Throw
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'allows a fresh start after PID reuse without stopping the unrelated process' {
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            $process = Get-Process -Id $PID
            @{process_id=$PID; workspace=$Global:BILL_REPO_ROOT; started_ticks='0'; executable=$process.Path} |
                ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
            Mock Write-BillLog {}
            Mock Stop-Process { throw 'must not stop a reused PID' }
            Get-BillManagedProcess smoke -ForStart | Should Be $null
            Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'allows a fresh start when a stale PID has no readable start time' {
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            @{process_id=123456789; workspace=$Global:BILL_REPO_ROOT; started_ticks='0'; executable='x'} |
                ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
            $fixture = Join-Path $TestDrive 'missing-start-time.ps1'
            Set-Content -LiteralPath $fixture -Value @'
param($WinRoot, $RuntimeRoot)
. (Join-Path $WinRoot 'lib\_common.ps1')
. (Join-Path $WinRoot 'lib\runtime.ps1')
$Global:BILL_WIN_ROOT = $RuntimeRoot
function Get-Process {
    param($Id, $ErrorAction)
    $staleProcess = [pscustomobject]@{HasExited=$false; StartTime=$null; Path='x'}
    $staleProcess | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
    return $staleProcess
}
Get-BillManagedProcess smoke -ForStart | Out-Null
'@
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $fixture $winRoot $TestDrive 2>&1 | Out-Null
            $LASTEXITCODE | Should Be 0
            Test-Path -LiteralPath (Get-BillRuntimePath smoke) | Should Be $true
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'allows only graceful shutdown when Windows hides the executable but process identity matches' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            $started = [datetime]::UtcNow
            @{process_id=123456789; workspace=$Global:BILL_REPO_ROOT; started_ticks=[string]$started.Ticks; executable='private.exe'} |
                ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
            $script:hiddenProcessFixture = [pscustomobject]@{HasExited=$false; StartTime=$started; Path=$null}
            $script:hiddenProcessFixture | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
            Mock Get-Process { return $script:hiddenProcessFixture }
            Mock Write-BillLog {}
            Get-BillManagedProcess smoke -ForGracefulStop | Should Be $script:hiddenProcessFixture
            # Forced termination must still require the full executable identity.
            { Get-BillManagedProcess smoke } | Should Throw
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'refuses graceful shutdown for a reused PID or a record from another workspace' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -Path (Join-Path $TestDrive 'runtime') -ItemType Directory -Force | Out-Null
            $started = [datetime]::UtcNow
            $script:hiddenProcessFixture = [pscustomobject]@{HasExited=$false; StartTime=$started; Path=$null}
            $script:hiddenProcessFixture | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
            Mock Get-Process { return $script:hiddenProcessFixture }
            foreach ($record in @(
                @{process_id=123456789; workspace=$Global:BILL_REPO_ROOT; started_ticks='0'; executable='private.exe'},
                @{process_id=123456789; workspace='another-workspace'; started_ticks=[string]$started.Ticks; executable='private.exe'}
            )) {
                $record | ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath smoke)
                { Get-BillManagedProcess smoke -ForGracefulStop } | Should Throw
            }
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'uses the graceful identity check for APIs but not endpoint-based infrastructure shutdown' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Write-BillLog {}
        Stop-BillComponent -Name identity -Port 8001
        Stop-BillComponent -Name redis -Port 6379
        Assert-MockCalled Get-BillManagedProcess -Times 1 -Exactly -Scope It -ParameterFilter { $Name -eq 'identity' -and $ForGracefulStop }
        Assert-MockCalled Get-BillManagedProcess -Times 1 -Exactly -Scope It -ParameterFilter { $Name -eq 'redis' -and !$ForGracefulStop }
    }
    It 'serializes start and stop for the same component' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            $lock = Enter-BillRuntimeLock smoke
            try { { Enter-BillRuntimeLock smoke } | Should Throw }
            finally { $lock.Dispose() }
            $second = Enter-BillRuntimeLock smoke
            $second.Dispose()
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'accepts a managed descendant exiting between lookup and termination' {
        $process = [Diagnostics.Process]::GetCurrentProcess()
        $script:processLookups = 0
        Mock Get-CimInstance { [pscustomobject]@{ ProcessId=$process.Id; ParentProcessId=0; CreationDate=$process.StartTime } }
        Mock Get-Process {
            $script:processLookups++
            if ($script:processLookups -eq 1) { return $process }
            return $null
        }
        Mock Stop-Process { throw 'process already exited' }
        { Stop-BillProcessTree $process } | Should Not Throw
        Assert-MockCalled Stop-Process -Times 1 -Exactly
    }
    It 'still reports a stop failure when the managed process remains running' {
        $process = [Diagnostics.Process]::GetCurrentProcess()
        Mock Get-CimInstance { [pscustomobject]@{ ProcessId=$process.Id; ParentProcessId=0; CreationDate=$process.StartTime } }
        Mock Get-Process { return $process }
        Mock Stop-Process { throw 'access denied' }
        { Stop-BillProcessTree $process } | Should Throw
    }
    It 'does not signal a descendant whose creation timestamp is unavailable' {
        $process = [Diagnostics.Process]::GetCurrentProcess()
        Mock Get-CimInstance { [pscustomobject]@{ ProcessId=$process.Id; ParentProcessId=0; CreationDate=$null } }
        Mock Get-Process { return $process }
        Mock Stop-Process {}
        { Stop-BillProcessTree $process } | Should Not Throw
        Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It
    }
    It 'preserves an unrelated replacement when the root PID is reused before the snapshot' {
        $process = [Diagnostics.Process]::GetCurrentProcess()
        $replacementTime = $process.StartTime.AddMinutes(1)
        Mock Get-CimInstance { [pscustomobject]@{ProcessId=$process.Id;ParentProcessId=0;CreationDate=$replacementTime} }
        Mock Get-Process { [pscustomobject]@{StartTime=$replacementTime} }
        Mock Stop-Process {}
        Stop-BillProcessTree $process
        Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It
    }
    It 'excludes old orphans whose parent PID was reused by the managed host' {
        $process = [Diagnostics.Process]::GetCurrentProcess()
        $orphanTime = $process.StartTime.AddMinutes(-1)
        Mock Get-CimInstance {
            [pscustomobject]@{ProcessId=$process.Id;ParentProcessId=0;CreationDate=$process.StartTime}
            [pscustomobject]@{ProcessId=123456788;ParentProcessId=$process.Id;CreationDate=$orphanTime}
        }
        Mock Get-Process {
            param($Id)
            if ($Id -eq 123456788) { return [pscustomobject]@{StartTime=$orphanTime} }
            return $process
        }
        Mock Stop-Process {}
        Stop-BillProcessTree $process
        Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It -ParameterFilter { $Id -eq 123456788 }
        Assert-MockCalled Stop-Process -Times 1 -Exactly -Scope It -ParameterFilter { $Id -eq $process.Id }
    }
}
