$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')

Describe 'The sign-in provider the scripts act on (docs/local-auth.md §2)' {
    $previous = $Global:BILL_ENV_DIR
    function Use-Provider([string]$Content) {
        $Global:BILL_ENV_DIR = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $Global:BILL_ENV_DIR | Out-Null
        if ($null -ne $Content) { Set-Content -LiteralPath (Join-Path $Global:BILL_ENV_DIR 'identity.env') -Value $Content -Encoding UTF8 }
    }
    AfterEach { $Global:BILL_ENV_DIR = $previous }

    It 'defaults to local when there is no environment file yet' {
        Use-Provider $null
        Get-BillAuthProvider | Should Be 'local'
    }
    It 'defaults to local when the file does not choose a provider' {
        Use-Provider "IDENTITY_DATABASE_URL=mysql://x`nIDENTITY_REDIS_URL=redis://r"
        Get-BillAuthProvider | Should Be 'local'
    }
    It 'follows an explicit choice, exactly as Identity reads it' {
        Use-Provider "IDENTITY_AUTH_PROVIDER=authentik"
        Get-BillAuthProvider | Should Be 'authentik'
        Use-Provider "IDENTITY_AUTH_PROVIDER=local"
        Get-BillAuthProvider | Should Be 'local'
    }
    It 'refuses a value Identity would refuse, rather than guessing' {
        foreach ($bad in @('Authentik', 'LOCAL', 'saml', ' ')) {
            Use-Provider "IDENTITY_AUTH_PROVIDER=$bad"
            { Get-BillAuthProvider } | Should Throw
        }
    }
}

Describe 'Scripts that used to assume Authentik' {
    It 'start-all only opens the Authentik tunnel when Authentik is the provider' {
        $text = Get-Content (Join-Path $winRoot 'start-all.ps1') -Raw
        $guard = $text.IndexOf("(Get-BillAuthProvider) -ne 'authentik'")
        $tunnel = $text.IndexOf("authentik-vm\tunnel.ps1")
        $guard | Should BeGreaterThan -1
        $tunnel | Should BeGreaterThan $guard
    }
    It 'the web servers trust the Authentik VM certificate authority only for Authentik' {
        $text = Get-Content (Join-Path $winRoot 'lib\web.ps1') -Raw
        $text.Contains("(Get-BillAuthProvider) -eq 'authentik' -and (Test-Path -LiteralPath `$localCa)") | Should Be $true
    }
    It 'the account review worker needs the local settings, or the Authentik token, by provider' {
        $text = Get-Content (Join-Path $winRoot 'account-review.ps1') -Raw
        $text | Should Match "Get-BillAuthProvider"
        $text | Should Match "IDENTITY_LOCAL_AUTH"
        $text | Should Match "IDENTITY_AUTHENTIK_REVIEW_TOKEN"
    }
}

Describe 'Regenerating development environment files' {
    It 'keeps the provider choice and the local provider settings, whose key-encryption key protects stored signing keys' {
        $original = $Global:BILL_ENV_DIR
        try {
            $Global:BILL_ENV_DIR = Join-Path $TestDrive 'provider-env'
            . (Join-Path $winRoot 'lib\write-envs.ps1')
            $config = [pscustomobject]@{
                infra = @{ mysql = @{ password = ''; superuser = 'local'; host = '127.0.0.1'; port = 3306 }; redis = @{ host = '127.0.0.1'; port = 6379 } }
                services = @(@{ code = 'identity'; env_prefix = 'IDENTITY_'; db = 'identity' })
            }
            Invoke-BillWriteEnvs -Config $config
            $path = Join-Path $Global:BILL_ENV_DIR 'identity.env'
            $kept = @('IDENTITY_AUTH_PROVIDER=local', 'IDENTITY_LOCAL_AUTH={"key_encryption_key":"keep-me"}')
            Add-Content -LiteralPath $path -Value $kept -Encoding UTF8
            Invoke-BillWriteEnvs -Config $config -Force
            $after = @(Get-Content -LiteralPath $path)
            foreach ($line in $kept) { ($after -contains $line) | Should Be $true }
            # Everything else is regenerated, so only the lines that must survive do.
            @($after | Where-Object { $_.StartsWith('IDENTITY_LOCAL_AUTH=') }).Count | Should Be 1
        } finally { $Global:BILL_ENV_DIR = $original }
    }
    It 'setup configures local sign-in after writing the environment files' {
        $text = Get-Content (Join-Path $winRoot 'setup.ps1') -Raw
        $text | Should Match 'Invoke-BillWriteEnvs -Config \$cfg -Force:\$Recreate; Invoke-BillConfigureLocalAuth'
    }
}

Describe 'The operator command wrapper' {
    It 'accepts only the provider commands, loads the private env into the process and never prints it' {
        $text = Get-Content (Join-Path $winRoot 'local-auth-cli.ps1') -Raw
        $text | Should Match "ValidateSet\('rotate-key', 'retire-keys', 'purge', 'reset-setup-administrator', 'adopt-users'\)"
        $text.Contains("SetEnvironmentVariable(`$name, `$values[`$name], 'Process')") | Should Be $true
        $text | Should Not Match 'Write-Host|Write-Output|Out-File|Set-Content'
    }
    It 'refuses a command that is not one of them' {
        { & (Join-Path $winRoot 'local-auth-cli.ps1') 'drop-everything' } | Should Throw
    }
}
