. (Join-Path $PSScriptRoot '..\lib\_common.ps1')
. (Join-Path $PSScriptRoot '..\lib\runtime.ps1')
. (Join-Path $PSScriptRoot '..\lib\tunnel-supervision.ps1')

Describe 'Pinned Authentik tunnel supervision' {
    BeforeEach {
        Mock Test-BillTunnelPorts { $false }
        Mock Start-Sleep { }
        Mock Write-BillLog { }
        Mock Stop-BillProcessTree { }
    }
    It 'reconnects after an exited forwarder and respects explicit stop' {
        $stop = Join-Path $TestDrive 'retry.stop'
        $script:starts = 0
        Invoke-BillTunnelSupervisor -StopPath $stop -StartForward {
            $script:starts++
            if ($script:starts -eq 2) { Set-Content -LiteralPath $stop -Value stop }
            $child = [pscustomobject]@{ HasExited = $true }
            $child | Add-Member ScriptMethod WaitForExit { param($timeout) return $true }
            $child | Add-Member ScriptMethod Dispose { }
            return $child
        }
        $script:starts | Should Be 2
        Assert-MockCalled Stop-BillProcessTree -Times 0 -Exactly
    }
    It 'refuses a foreign port owner without launching or stopping any process' {
        Mock Test-BillTunnelPorts { $true }
        { Invoke-BillTunnelSupervisor -StopPath (Join-Path $TestDrive 'foreign.stop') -StartForward { throw 'must not launch' } } | Should Throw 'owned outside'
        Assert-MockCalled Stop-BillProcessTree -Times 0 -Exactly
    }
    It 'retries a transient launch exception without leaking the exception' {
        $stop = Join-Path $TestDrive 'launch.stop'
        $script:attempts = 0
        Invoke-BillTunnelSupervisor -StopPath $stop -StartForward {
            $script:attempts++
            if ($script:attempts -eq 1) { throw 'private launch details' }
            Set-Content -LiteralPath $stop -Value stop
            $child = [pscustomobject]@{ HasExited = $true }
            $child | Add-Member ScriptMethod WaitForExit { param($timeout) return $true }
            $child | Add-Member ScriptMethod Dispose { }
            return $child
        }
        $script:attempts | Should Be 2
        Assert-MockCalled Write-BillLog -ParameterFilter { $Message -match 'private' } -Times 0 -Exactly
    }
    It 'cleans up its still-running child when a stop request arrives' {
        $stop = Join-Path $TestDrive 'child.stop'
        Invoke-BillTunnelSupervisor -StopPath $stop -StartForward {
            $child = [System.Diagnostics.Process]::GetCurrentProcess()
            $child | Add-Member NoteProperty StopFile $stop
            $child | Add-Member ScriptMethod WaitForExit { param($timeout) Set-Content -LiteralPath $this.StopFile -Value stop; return $false } -Force
            return $child
        }
        Assert-MockCalled Stop-BillProcessTree -Times 1 -Exactly
    }
}
