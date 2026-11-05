$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')
Describe 'Tax impact review lifecycle' {
    It 'stops a worker without probing a listening port' {
        Mock Get-BillManagedProcess { return $null }
        Mock Wait-ForPort { throw 'A worker has no listening port' }
        Mock Write-BillLog {}
        { Stop-BillComponent -Name catalog-tax-review } | Should Not Throw
        Assert-MockCalled Wait-ForPort -Times 0 -Exactly
    }
    It 'includes the existing worker in backend start and stop' {
        Get-Content (Join-Path $winRoot 'start-services.ps1') -Raw | Should Match 'tax-review.ps1'
        Get-Content (Join-Path $winRoot 'stop-all.ps1') -Raw | Should Match 'tax-review.ps1'
    }
    It 'requires private source configuration and uses managed process ownership' {
        $script = Get-Content (Join-Path $winRoot 'tax-review.ps1') -Raw
        $script | Should Match 'CATALOG_IDENTITY_SOURCE'
        $script | Should Match 'CATALOG_SOURCE_SUBSCRIPTIONS'
        $script | Should Match 'Stop-BillComponent -Name'
        $script | Should Not Match '/IM|Stop-Process -Name'
    }
}
