$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\write-envs.ps1')
Describe 'Identity development bank encryption' {
    It 'adds a valid durable key without changing unrelated environment settings' {
        $lines = @(Add-BillIdentityBankEncryption @('IDENTITY_DATABASE_URL=preserved',''))
        ($lines -contains 'IDENTITY_DATABASE_URL=preserved') | Should Be $true
        $ring = (($lines | Where-Object { $_.StartsWith('IDENTITY_BANK_ENCRYPTION_KEYS=') }) -split '=',2)[1] | ConvertFrom-Json
        [Convert]::FromBase64String($ring.'development-v1').Length | Should Be 32
        $again = @(Add-BillIdentityBankEncryption $lines)
        (($again -join "`n") -ceq ($lines -join "`n")) | Should Be $true
    }
    It 'refuses partial or invalid configuration instead of replacing encryption keys' {
        { Add-BillIdentityBankEncryption @('IDENTITY_BANK_ACTIVE_KEY_ID=existing') } | Should Throw
        { Add-BillIdentityBankEncryption @('IDENTITY_BANK_ENCRYPTION_KEYS={}') } | Should Throw
        { Add-BillIdentityBankEncryption @('IDENTITY_BANK_ACTIVE_KEY_ID=missing','IDENTITY_BANK_ENCRYPTION_KEYS={"other":"invalid"}') } | Should Throw
    }
    It 'initializes bank encryption for both fresh and existing development env files' {
        $original = $Global:BILL_ENV_DIR
        try {
            $Global:BILL_ENV_DIR = Join-Path $TestDrive 'bank-env'
            $config = [pscustomobject]@{
                infra = @{ mysql = @{ password = ''; superuser = 'local'; host = '127.0.0.1'; port = 3306 }; redis = @{ host = '127.0.0.1'; port = 6379 } }
                services = @(@{ code = 'identity'; env_prefix = 'IDENTITY_'; db = 'identity' })
            }
            Invoke-BillWriteEnvs -Config $config
            $path = Join-Path $Global:BILL_ENV_DIR 'identity.env'
            $fresh = @(Get-Content -LiteralPath $path)
            @($fresh | Where-Object { $_.StartsWith('IDENTITY_BANK_ACTIVE_KEY_ID=') }).Count | Should Be 1
            Invoke-BillWriteEnvs -Config $config
            ((Get-Content -LiteralPath $path -Raw) -ceq ($fresh -join "`r`n") + "`r`n") | Should Be $true
            Invoke-BillWriteEnvs -Config $config -Force
            $afterForce = @(Get-Content -LiteralPath $path | Where-Object { $_.StartsWith('IDENTITY_BANK_') })
            (($afterForce -join "`n") -ceq (@($fresh | Where-Object { $_.StartsWith('IDENTITY_BANK_') }) -join "`n")) | Should Be $true
            $legacy = @($fresh | Where-Object { -not $_.StartsWith('IDENTITY_BANK_') })
            $legacy | Set-Content -LiteralPath $path -Encoding UTF8
            Invoke-BillWriteEnvs -Config $config
            $upgraded = @(Get-Content -LiteralPath $path)
            @($upgraded | Where-Object { $_.StartsWith('IDENTITY_BANK_ENCRYPTION_KEYS=') }).Count | Should Be 1
            @($upgraded | Where-Object { $_.StartsWith('IDENTITY_DATABASE_URL=') })[0] -ceq @($fresh | Where-Object { $_.StartsWith('IDENTITY_DATABASE_URL=') })[0] | Should Be $true
        } finally { $Global:BILL_ENV_DIR = $original }
    }
}
