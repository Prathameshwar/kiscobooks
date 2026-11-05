$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib/_common.ps1')
. (Join-Path $winRoot 'lib/write-envs.ps1')

Describe 'Accounting tax jurisdiction configuration' {
    It 'supplies reference-backed UTGST territories while preserving existing settings' {
        $lines = @(Add-BillAccountingTaxJurisdictions @('ACCOUNTING_DATABASE_URL=unchanged'))
        $value = @($lines | Where-Object { $_.StartsWith('ACCOUNTING_UTGST_STATES=') })
        $value.Count | Should Be 1
        $states = ($value[0] -split '=', 2)[1] | ConvertFrom-Json
        ($states -join ',') | Should Be 'IN-AN,IN-CH,IN-DH,IN-LA,IN-LD'
        $references = Get-Content (Join-Path $Global:BILL_REPO_ROOT 'libs/platform/src/billing_platform/reference/data/state.json') -Raw | ConvertFrom-Json
        foreach ($code in $states) {
            @($references | Where-Object { $_.code -eq $code -and $_.country_code -eq 'IN' }).Count | Should Be 1
        }
        ($lines -contains 'ACCOUNTING_DATABASE_URL=unchanged') | Should Be $true
        (@(Add-BillAccountingTaxJurisdictions $lines) -join "`n") | Should Be ($lines -join "`n")
        $override = @('ACCOUNTING_UTGST_STATES=[]', 'KEEP=value')
        (@(Add-BillAccountingTaxJurisdictions $override) -join "`n") | Should Be ($override -join "`n")
    }

    It 'writes the setting for fresh and existing development environments' {
        $original = $Global:BILL_ENV_DIR
        try {
            $Global:BILL_ENV_DIR = Join-Path $TestDrive 'tax-env'
            $config = [pscustomobject]@{
                infra = @{ mysql = @{ password = ''; superuser = 'local'; host = '127.0.0.1'; port = 3306 } }
                services = @(@{ code = 'accounting'; env_prefix = 'ACCOUNTING_'; db = 'accounting' })
            }
            Invoke-BillWriteEnvs -Config $config
            $path = Join-Path $Global:BILL_ENV_DIR 'accounting.env'
            $fresh = @(Get-Content -LiteralPath $path)
            @($fresh | Where-Object { $_.StartsWith('ACCOUNTING_UTGST_STATES=') }).Count | Should Be 1
            $legacy = @($fresh | Where-Object { -not $_.StartsWith('ACCOUNTING_UTGST_STATES=') })
            [IO.File]::WriteAllLines($path, $legacy)
            Invoke-BillWriteEnvs -Config $config
            $updated = @(Get-Content -LiteralPath $path)
            @($updated | Where-Object { $_.StartsWith('ACCOUNTING_UTGST_STATES=') }).Count | Should Be 1
            ($updated | Where-Object { $_.StartsWith('ACCOUNTING_DATABASE_URL=') }) | Should Be ($fresh | Where-Object { $_.StartsWith('ACCOUNTING_DATABASE_URL=') })
            $custom = @($updated | Where-Object { -not $_.StartsWith('ACCOUNTING_UTGST_STATES=') }) + @('ACCOUNTING_UTGST_STATES=[]')
            [IO.File]::WriteAllLines($path, $custom)
            Invoke-BillWriteEnvs -Config $config -Force
            @(Get-Content -LiteralPath $path | Where-Object { $_.StartsWith('ACCOUNTING_UTGST_STATES=') })[0] | Should Be 'ACCOUNTING_UTGST_STATES=[]'
        } finally { $Global:BILL_ENV_DIR = $original }
    }
}
