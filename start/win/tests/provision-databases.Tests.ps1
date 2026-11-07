$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\database-provisioning.ps1')
. (Join-Path $winRoot 'lib\database-setup-prompt.ps1')

Describe 'Database provisioning command' {
    It 'leaves provisioning optional when the setup prompt is declined' {
        Mock Read-Host { 'n' }

        $result = Invoke-BillOfferDatabaseProvisioning -ProvisionScriptPath 'unused.ps1'

        $result | Should Be $false
    }

    It 'runs the separate provisioner only after explicit confirmation' {
        $fixture = Join-Path $TestDrive 'database-provision-confirmed'
        New-Item -ItemType Directory -Path $fixture -Force | Out-Null
        $marker = Join-Path $fixture 'invoked.txt'
        $provisioner = Join-Path $fixture 'provision.ps1'
        Set-Content -LiteralPath $provisioner -Value "Set-Content -LiteralPath '$marker' -Value 'invoked'"
        Mock Read-Host { 'yes' }

        $result = Invoke-BillOfferDatabaseProvisioning -ProvisionScriptPath $provisioner

        $result | Should Be $true
        (Get-Content -LiteralPath $marker -Raw).Trim() | Should Be 'invoked'
    }

    It 'propagates a provisioner failure' {
        $fixture = Join-Path $TestDrive 'database-provision-prompt'
        New-Item -ItemType Directory -Path $fixture -Force | Out-Null
        $provisioner = Join-Path $fixture 'provision.ps1'
        Set-Content -LiteralPath $provisioner -Value 'exit 7'

        { Invoke-BillDatabaseProvisioner -ScriptPath $provisioner } | Should Throw
    }

    It 'builds a safely escaped URL and changes only the requested local environment entry' {
        $url = New-BillDatabaseUrl -Username 'root' -Password 'test@:/+ value' `
            -HostName 'localhost' -Port 3306 -Database 'identity'
        $url | Should Be 'mysql+asyncmy://root:test%40%3A%2F%2B%20value@localhost:3306/identity'

        $content = "# local settings`r`nIDENTITY_DATABASE_URL=mysql+asyncmy://root@localhost:3306/identity`r`nOTHER=value`r`n"
        $updated = Set-BillEnvironmentValue -Content $content -Name 'IDENTITY_DATABASE_URL' -Value $url
        $updated | Should Match 'IDENTITY_DATABASE_URL=mysql\+asyncmy://root:test%40%3A%2F%2B%20value@localhost:3306/identity'
        $updated | Should Match 'OTHER=value'
        { Set-BillEnvironmentValue -Content $content -Name 'MISSING_URL' -Value $url } | Should Throw
    }

    It 'shows the configured database and migration plan without connecting or changing anything in WhatIf mode' {
        $fixture = Join-Path $TestDrive 'provision-databases'
        $fixtureWin = Join-Path $fixture 'start\win'
        $fixtureLib = Join-Path $fixtureWin 'lib'
        $migrationDirectory = Join-Path $fixture 'dbs\identity'
        New-Item -ItemType Directory -Path $fixtureLib, (Join-Path $fixtureWin 'conf'), (Join-Path $fixtureWin 'env'), $migrationDirectory -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $migrationDirectory 'alembic.ini') -Value '[alembic]'
        Copy-Item -LiteralPath (Join-Path $winRoot 'provision-databases.ps1') -Destination $fixtureWin
        Copy-Item -LiteralPath (Join-Path $winRoot 'lib\database-provisioning.ps1') -Destination $fixtureLib
        Set-Content -LiteralPath (Join-Path $fixtureLib '_common.ps1') -Value @'
$Global:BILL_REPO_ROOT = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$Global:BILL_WIN_ROOT = Split-Path -Parent $PSScriptRoot
$Global:BILL_ENV_DIR = Join-Path $Global:BILL_WIN_ROOT 'env'
$Global:BILL_CONF_DIR = Join-Path $Global:BILL_WIN_ROOT 'conf'
function Get-BillConfig {
    return @{
        infra = @{mysql = @{host='127.0.0.1'; port=3306; superuser='root'; password=''}}
        services = @(@{
            code='identity'; db='identity'; alembic='dbs/identity/alembic.ini'
            project='apis/identity'; env_prefix='IDENTITY_'
        })
    }
}
'@
        Set-Content -LiteralPath (Join-Path $fixtureLib 'runtime.ps1') -Value @'
function Read-BillEnvironment {
    param([string]$Path)
    return @{IDENTITY_DATABASE_URL='mysql+asyncmy://root@127.0.0.1:3306/identity'}
}
'@

        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixtureWin 'provision-databases.ps1') -WhatIf

        $LASTEXITCODE | Should Be 0
        ($output -join "`n") | Should Match 'Service databases: identity'
        ($output -join "`n") | Should Match 'Upgrade Alembic migrations to head'
        ($output -join "`n") | Should Match 'no databases or schemas were changed'
    }

    It 'passes a Python file path rather than inline code to avoid Windows argument rewriting' {
        $script = Get-Content -LiteralPath (Join-Path $winRoot 'provision-databases.ps1') -Raw
        $script | Should Match '& \$identityPython \$databaseScript'
        $script | Should Not Match '& \$identityPython -c'
        Test-Path -LiteralPath (Join-Path $winRoot 'create_databases.py') | Should Be $true
    }
}
