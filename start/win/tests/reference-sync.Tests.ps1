$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')
Describe 'Reference worker lifecycle' {
    It 'does not probe a port for a stopped worker' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { throw 'A worker has no listening port' }
        Mock Write-BillLog {}
        { Stop-BillComponent -Name catalog-reference-sync } | Should Not Throw
        Assert-MockCalled Wait-ForPort -Times 0 -Exactly
    }
    It 'includes service-local workers in backend start and stop' {
        Get-Content (Join-Path $winRoot 'start-services.ps1') -Raw | Should Match 'reference-sync.ps1'
        Get-Content (Join-Path $winRoot 'stop-all.ps1') -Raw | Should Match 'reference-sync.ps1'
    }
    It 'supports safe managed stop and never selects a process image' {
        $script = Get-Content (Join-Path $winRoot 'reference-sync.ps1') -Raw
        $script | Should Match 'Stop-BillComponent -Name'
        $script | Should Match 'REFERENCE_SYNC_STOP_FILE'
        $script | Should Not Match '/IM|Stop-Process -Name'
    }
}
