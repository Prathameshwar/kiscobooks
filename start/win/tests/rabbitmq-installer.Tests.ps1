$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\rabbitmq-installer.ps1')

Describe 'RabbitMQ installer' {
    It 'uses the Erlang archive root and ignores its duplicate runtime erl.exe' {
        $staging = Join-Path $TestDrive 'otp-archive'
        New-Item -ItemType Directory -Path `
            (Join-Path $staging 'bin'),
            (Join-Path $staging 'erts-15.2.7.13\bin'),
            (Join-Path $staging 'lib') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $staging 'bin\erl.exe') -Value 'launcher'
        Set-Content -LiteralPath (Join-Path $staging 'erts-15.2.7.13\bin\erl.exe') -Value 'runtime'

        $root = Resolve-BillRabbitArchiveSourceRoot -StagingRoot $staging `
            -ArchiveRoot '' -RequiredFile 'bin\erl.exe' -PackageName 'Erlang'

        $root | Should Be $staging
    }

    It 'reuses a cached archive only when its checksum matches' {
        $archive = Join-Path $TestDrive 'verified.zip'
        Set-Content -LiteralPath $archive -Value 'verified archive'
        $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash

        $found = Find-BillVerifiedArchive -CandidatePaths @($archive) -Sha256 $hash

        $found | Should Be $archive
        (Find-BillVerifiedArchive -CandidatePaths @($archive) -Sha256 ('0' * 64)) | Should Be $null
    }

    It 'does not download or modify files when both pinned install paths already exist' {
        $fixture = Join-Path $TestDrive 'rabbitmq-install-fixture'
        $fixtureWin = Join-Path $fixture 'start\win'
        $erlangBin = Join-Path $fixture '.tools\erlang\bin'
        $rabbitSbin = Join-Path $fixture '.tools\rabbitmq\rabbitmq_server-4.3.5\sbin'
        $fixtureLib = Join-Path $fixtureWin 'lib'
        New-Item -ItemType Directory -Path $fixtureWin, $fixtureLib, $erlangBin, $rabbitSbin -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $winRoot 'install-rabbitmq.ps1') -Destination $fixtureWin
        Copy-Item -LiteralPath (Join-Path $winRoot 'lib\rabbitmq-installer.ps1') -Destination $fixtureLib
        Set-Content -LiteralPath (Join-Path $erlangBin 'erl.exe') -Value 'existing Erlang'
        Set-Content -LiteralPath (Join-Path $rabbitSbin 'rabbitmq-server.bat') -Value 'existing RabbitMQ'

        $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $fixtureWin 'install-rabbitmq.ps1')

        $LASTEXITCODE | Should Be 0
        ($output -join "`n") | Should Match 'already exist; nothing to do'
        [IO.File]::ReadAllText((Join-Path $erlangBin 'erl.exe')).TrimEnd() | Should Be 'existing Erlang'
        [IO.File]::ReadAllText((Join-Path $rabbitSbin 'rabbitmq-server.bat')).TrimEnd() | Should Be 'existing RabbitMQ'
    }
}
