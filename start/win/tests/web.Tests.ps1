$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')
. (Join-Path $winRoot 'lib\web.ps1')

Describe 'Windows UI launcher regressions' {
    It 'starts both apps by default and supports selecting only one' {
        $targets = @(Get-BillWebApps)
        $targets.Count | Should Be 2
        $targets[0].Port | Should Be 4310
        $targets[1].Port | Should Be 4320
        @(Get-BillWebApps console).Count | Should Be 1
        (Get-BillWebApps console).Name | Should Be 'web-console'
    }
    It 'reports an unmanaged listener without claiming it is healthy' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $true }
        Mock Test-BillWebHttp { throw 'must not probe external server' }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'EXTERNAL'
        Assert-MockCalled Test-BillWebHttp -Times 0 -Exactly -Scope It
    }
    It 'reports an exited process immediately instead of waiting the full timeout' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Test-Path { return $true }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'EXITED'
    }
    It 'reports stopped when there is no process or state' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Test-Path { return $false }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'DOWN'
    }
    It 'reports a process identity mismatch as an error' {
        Mock Get-BillManagedProcess { throw 'Process identity changed' }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'ERROR'
    }
    It 'reports a server still starting when the process has no listener' {
        Mock Get-BillManagedProcess { return (Get-Process -Id $PID) }
        Mock Wait-ForPort { return $false }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'STARTING'
    }
    It 'requires ownership of the listening process even when a managed host exists' {
        Mock Get-BillManagedProcess { return (Get-Process -Id $PID) }
        Mock Wait-ForPort { return $true }
        Mock Test-BillWebListenerOwned { return $false }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'EXTERNAL'
    }
    It 'requires a valid HTTP response after confirming ownership' {
        Mock Get-BillManagedProcess { return (Get-Process -Id $PID) }
        Mock Wait-ForPort { return $true }
        Mock Test-BillWebListenerOwned { return $true }
        Mock Test-BillWebHttp { return $false }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'DEGRADED'
    }
    It 'reports a managed server with its expected HTTP response as up' {
        Mock Get-BillManagedProcess { return (Get-Process -Id $PID) }
        Mock Wait-ForPort { return $true }
        Mock Test-BillWebListenerOwned { return $true }
        Mock Test-BillWebHttp { return $true }
        (Get-BillWebStatus (Get-BillWebApps auth)).Status | Should Be 'UP'
    }
    It 'rejects generic HTTP success and accepts the expected SVG as bytes' {
        . (Join-Path $winRoot 'lib\web.ps1')
        Mock Invoke-WebRequest { [pscustomobject]@{StatusCode=200;Content='unrelated app'} }
        Test-BillWebHttp 4310 | Should Be $false
        Mock Invoke-WebRequest {
            [pscustomobject]@{StatusCode=200;Content=[Text.Encoding]::UTF8.GetBytes('<svg aria-label="KiscoBooks"></svg>')}
        }
        Test-BillWebHttp 4310 | Should Be $true
    }
    It 'reports HTTP failures without exposing a response body' {
        . (Join-Path $winRoot 'lib\web.ps1')
        Mock Invoke-WebRequest { throw 'unavailable' }
        Test-BillWebHttp 4310 | Should Be $false
    }
    It 'starts the official CLI directly with localhost binding and the inherited stop preload' {
        Mock Test-Path { return $true }
        Mock Write-BillLog {}
        Mock Start-BillProcess {}
        Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe'
        Assert-MockCalled Start-BillProcess -Times 1 -Exactly -Scope It -ParameterFilter {
            $Name -eq 'web-auth' -and $Executable -eq 'node.exe' -and
            $Arguments[0] -eq '--require' -and $Arguments[5] -eq '127.0.0.1' -and
            $Arguments[7] -eq '4310' -and $Environment.BILL_WEB_STOP_PATH -like '*web-auth.stop'
        }
    }
    It 'fails when app dependencies remain missing' {
        Mock Test-Path { return $false }
        Mock Start-BillProcess {}
        { Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe' } | Should Throw
        Assert-MockCalled Start-BillProcess -Times 0 -Exactly -Scope It
    }
    It 'propagates dependency installation failures and restores the working directory' {
        function pnpm.cmd { $global:LASTEXITCODE = 23 }
        Mock Get-Command { [pscustomobject]@{Source='pnpm.cmd'} }
        $originalDirectory = (Get-Location).Path
        try {
            { Install-BillWebDependencies } | Should Throw
            (Get-Location).Path | Should Be $originalDirectory
        } finally { Remove-Item -LiteralPath Function:\pnpm.cmd }
    }
    It 'refuses an external UI listener during stop without killing any process' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $true }
        Mock Stop-Process { throw 'must never kill' }
        { Stop-BillComponent -Name web-auth -Port 4310 } | Should Throw
        Assert-MockCalled Stop-Process -Times 0 -Exactly -Scope It
    }
    It 'recognizes a listener in a nested child of the managed host' {
        . (Join-Path $winRoot 'lib\web.ps1')
        Mock Get-NetTCPConnection { [pscustomobject]@{OwningProcess=123456789} }
        Mock Get-CimInstance {
            [pscustomobject]@{ProcessId=123456788;ParentProcessId=$PID}
            [pscustomobject]@{ProcessId=123456789;ParentProcessId=123456788}
        }
        Test-BillWebListenerOwned -Process (Get-Process -Id $PID) -Port 4310 | Should Be $true
    }
    It 'rejects unrelated listeners even when a managed child also listens' {
        . (Join-Path $winRoot 'lib\web.ps1')
        Mock Get-NetTCPConnection {
            [pscustomobject]@{OwningProcess=123456788}
            [pscustomobject]@{OwningProcess=123456789}
        }
        Mock Get-CimInstance { [pscustomobject]@{ProcessId=123456788;ParentProcessId=$PID} }
        Test-BillWebListenerOwned -Process (Get-Process -Id $PID) -Port 4310 | Should Be $false
    }
    It 'clears stale state after a successful repeated stop' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { return $false }
        Mock Write-BillLog {}
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -ItemType Directory -Path (Join-Path $TestDrive 'runtime') -Force | Out-Null
            $statePath = Get-BillRuntimePath web-auth
            Set-Content -LiteralPath $statePath -Value '{}'
            Stop-BillWebApp (Get-BillWebApps auth)
            Test-Path -LiteralPath $statePath | Should Be $false
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
    It 'preserves state when ownership verification refuses a stop' {
        Mock Stop-BillComponent { throw 'identity changed' }
        Mock Remove-Item {}
        { Stop-BillWebApp (Get-BillWebApps auth) } | Should Throw
        Assert-MockCalled Remove-Item -Times 0 -Exactly -Scope It
    }
    It 'treats a process that exits during lookup as stopped rather than a PID identity mismatch' {
        . (Join-Path $winRoot 'lib\runtime.ps1')
        $savedRoot = $Global:BILL_WIN_ROOT
        try {
            $Global:BILL_WIN_ROOT = $TestDrive
            New-Item -ItemType Directory -Path (Join-Path $TestDrive 'runtime') -Force | Out-Null
            @{process_id=123456789} | ConvertTo-Json | Set-Content -LiteralPath (Get-BillRuntimePath web-auth)
            Mock Get-Process {
                $exited = [pscustomobject]@{HasExited=$true}
                $exited | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
                return $exited
            }
            Get-BillManagedProcess web-auth | Should Be $null
        } finally { $Global:BILL_WIN_ROOT = $savedRoot }
    }
}

Describe 'Local Authentik TLS trust' {
    It 'preserves an explicitly configured TLS trust file' {
        $previousCa = $env:NODE_EXTRA_CA_CERTS
        try {
            $env:NODE_EXTRA_CA_CERTS = 'existing-ca.pem'
            Mock Get-BillAuthProvider { throw 'Explicit trust must not read private provider settings' }
            Mock Test-Path { return $true }
            Mock Write-BillLog {}
            Mock Start-BillProcess {}
            Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe'
            Assert-MockCalled Start-BillProcess -Times 1 -Exactly -Scope It -ParameterFilter {
                -not $Environment.ContainsKey('NODE_EXTRA_CA_CERTS')
            }
        } finally { $env:NODE_EXTRA_CA_CERTS = $previousCa }
    }
    It 'adds the local Authentik CA when no trust file was supplied' {
        $previousCa = $env:NODE_EXTRA_CA_CERTS
        try {
            $env:NODE_EXTRA_CA_CERTS = $null
            Mock Get-BillAuthProvider { return 'authentik' }
            Mock Test-Path { return $true }
            Mock Write-BillLog {}
            Mock Start-BillProcess {}
            Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe'
            Assert-MockCalled Start-BillProcess -Times 1 -Exactly -Scope It -ParameterFilter {
                $Environment.NODE_EXTRA_CA_CERTS -like '*authentik\tls\ca.crt'
            }
        } finally { $env:NODE_EXTRA_CA_CERTS = $previousCa }
    }
    It 'keeps local authentication independent of the Authentik CA' {
        $previousCa = $env:NODE_EXTRA_CA_CERTS
        try {
            $env:NODE_EXTRA_CA_CERTS = $null
            Mock Get-BillAuthProvider { return 'local' }
            Mock Test-Path { return $true }
            Mock Write-BillLog {}
            Mock Start-BillProcess {}
            Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe'
            Assert-MockCalled Start-BillProcess -Times 1 -Exactly -Scope It -ParameterFilter {
                -not $Environment.ContainsKey('NODE_EXTRA_CA_CERTS')
            }
        } finally { $env:NODE_EXTRA_CA_CERTS = $previousCa }
    }
    It 'starts without extra trust when the Authentik CA is absent' {
        $previousCa = $env:NODE_EXTRA_CA_CERTS
        try {
            $env:NODE_EXTRA_CA_CERTS = $null
            Mock Get-BillAuthProvider { return 'authentik' }
            Mock Test-Path { return $true }
            Mock Test-Path { return $false } -ParameterFilter { $LiteralPath -like '*authentik\tls\ca.crt' }
            Mock Write-BillLog {}
            Mock Start-BillProcess {}
            Start-BillWebApp -Target (Get-BillWebApps auth) -Node 'node.exe'
            Assert-MockCalled Start-BillProcess -Times 1 -Exactly -Scope It -ParameterFilter {
                -not $Environment.ContainsKey('NODE_EXTRA_CA_CERTS')
            }
        } finally { $env:NODE_EXTRA_CA_CERTS = $previousCa }
    }
}
