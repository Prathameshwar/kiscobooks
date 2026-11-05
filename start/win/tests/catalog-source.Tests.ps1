$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')
Describe 'Catalog source connection lifecycle' {
    It 'prepares matching scoped credentials and preserves unrelated private settings' {
        $directory = Join-Path $TestDrive 'source-env'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $identityPath = Join-Path $directory 'identity.env'
        $catalogPath = Join-Path $directory 'catalog.env'
        @('IDENTITY_DATABASE_URL=unchanged','IDENTITY_AUDIT_BROKER_URL=amqp://ephemeral.invalid','IDENTITY_AUDIT_BROKER_USER=identity') | Set-Content $identityPath
        'CATALOG_DATABASE_URL=unchanged' | Set-Content $catalogPath
        & (Join-Path $winRoot 'catalog-enrollment-prepare.ps1') -EnvDirectory $directory -WhatIf
        (Read-BillEnvironment $identityPath).ContainsKey('IDENTITY_CATALOG_SOURCE_CREDENTIALS') | Should Be $false
        & (Join-Path $winRoot 'catalog-enrollment-prepare.ps1') -EnvDirectory $directory
        $identity = Read-BillEnvironment $identityPath
        $catalog = Read-BillEnvironment $catalogPath
        $credentials = $identity['IDENTITY_CATALOG_SOURCE_CREDENTIALS'] | ConvertFrom-Json
        $source = $catalog['CATALOG_IDENTITY_SOURCE'] | ConvertFrom-Json
        $identity['IDENTITY_DATABASE_URL'] | Should Be 'unchanged'
        $catalog['CATALOG_DATABASE_URL'] | Should Be 'unchanged'
        $credentials.current.allow_enrolled_companies | Should Be $true
        $credentials.current.allow_actor_authorization | Should Be $true
        @($credentials.current.scopes).Count | Should Be 0
        $source.request_secret | Should Be $credentials.current.secret
        $source.response_secrets.current | Should Be $identity['IDENTITY_CATALOG_SOURCE_RESPONSE_SECRET']
        $identity['IDENTITY_SOURCE_EVENT_SECRET'] | Should Be $catalog['CATALOG_SOURCE_EVENT_SECRET']
        $catalog['CATALOG_SOURCE_DISCOVERY'] | Should Be 'true'
        { & (Join-Path $winRoot 'catalog-enrollment-prepare.ps1') -EnvDirectory $directory } | Should Throw
    }
    It 'starts and stops both workers with the existing managed lifecycle' {
        $workers = Get-Content (Join-Path $winRoot 'audit-workers.ps1') -Raw
        $workers | Should Match 'identity.tasks.catalog_publisher'
        $workers | Should Match 'catalog.tasks.source_worker'
        $workers | Should Match 'WindowStyle Hidden'
        $start = Get-Content (Join-Path $winRoot 'start-services.ps1') -Raw
        $start | Should Match 'identity-catalog-publisher'
        $start | Should Match 'catalog-identity-source'
        Get-Content (Join-Path $winRoot 'stop-all.ps1') -Raw | Should Match 'audit-workers.ps1'
        foreach ($file in @('catalog-enrollment-prepare.ps1','audit-workers.ps1','start-services.ps1')) {
            $tokens = $null
            $errors = $null
            [Management.Automation.Language.Parser]::ParseFile((Join-Path $winRoot $file), [ref]$tokens, [ref]$errors) | Out-Null
            @($errors).Count | Should Be 0
        }
    }
}
