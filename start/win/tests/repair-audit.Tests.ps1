$winRoot = Split-Path -Parent $PSScriptRoot

Describe 'Audit repair batch launcher' {
    It 'handles <Failure> with pause=<Pause> and preserves the result' -TestCases @(
        @{Failure='none'; Pause=$false; Code=0; Calls='prepare,stop:audit-consumer,start:audit-consumer,status'},
        @{Failure='prepare'; Pause=$false; Code=7; Calls='prepare'},
        @{Failure='stop'; Pause=$false; Code=7; Calls='prepare,stop:audit-consumer'},
        @{Failure='start'; Pause=$false; Code=7; Calls='prepare,stop:audit-consumer,start:audit-consumer'},
        @{Failure='status'; Pause=$false; Code=7; Calls='prepare,stop:audit-consumer,start:audit-consumer,status'},
        @{Failure='none'; Pause=$true; Code=0; Calls='prepare,stop:audit-consumer,start:audit-consumer,status'},
        @{Failure='prepare'; Pause=$true; Code=7; Calls='prepare'}
    ) {
        param($Failure, $Pause, $Code, $Calls)
        $fixture = Join-Path $TestDrive ('repair audit ' + $Failure + ' ' + $Pause)
        New-Item -ItemType Directory -Path $fixture -Force | Out-Null
        $batch = Get-Content (Join-Path $winRoot 'repair-audit.bat') -Raw
        $batch = $batch -replace '(?im)^\s*pause[^\r\n]*', 'echo PAUSE_REQUESTED'
        Set-Content (Join-Path $fixture 'repair-audit.bat') $batch -Encoding ASCII
        Set-Content (Join-Path $fixture 'audit-prepare.ps1') @'
Add-Content (Join-Path $PSScriptRoot 'calls.txt') 'prepare'
if ($env:BILL_AUDIT_TEST_FAIL -eq 'prepare') { exit 7 }
exit 0
'@
        Set-Content (Join-Path $fixture 'audit-workers.ps1') @'
param($Action, $Worker)
Add-Content (Join-Path $PSScriptRoot 'calls.txt') ($Action + ':' + $Worker)
if ($env:BILL_AUDIT_TEST_FAIL -eq $Action) { exit 7 }
exit 0
'@
        Set-Content (Join-Path $fixture 'status.bat') @(
            '@echo off', 'echo status>> "%~dp0calls.txt"',
            'if "%BILL_AUDIT_TEST_FAIL%"=="status" exit /b 7', 'exit /b 0'
        ) -Encoding ASCII
        $previousPause = $env:BILL_NO_PAUSE
        $previousFailure = $env:BILL_AUDIT_TEST_FAIL
        try {
            $env:BILL_NO_PAUSE = if ($Pause) { '' } else { '1' }
            $env:BILL_AUDIT_TEST_FAIL = $Failure
            $output = & cmd.exe /d /c ('"' + (Join-Path $fixture 'repair-audit.bat') + '"')
            $LASTEXITCODE | Should Be $Code
            ((Get-Content (Join-Path $fixture 'calls.txt')) -join ',') | Should Be $Calls
            @($output | Where-Object { $_ -eq 'PAUSE_REQUESTED' }).Count | Should Be ([int]$Pause)
            if ($Code) { ($output -join "`n") | Should Match 'Audit repair failed' }
            else { ($output -join "`n") | Should Match 'Audit repair completed' }
        } finally {
            $env:BILL_NO_PAUSE = $previousPause
            $env:BILL_AUDIT_TEST_FAIL = $previousFailure
        }
    }
}
