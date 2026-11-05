. (Join-Path $PSScriptRoot '..\platform-setup\configuration.ps1')

Describe 'Platform setup preparation' {
    BeforeEach {
        $fixtureRoot = Join-Path $TestDrive ([Guid]::NewGuid().ToString('N'))
        foreach ($relative in @('start\win\platform-setup', 'start\win\env', 'start\win\conf', 'mfes\apps\auth')) {
            New-Item -ItemType Directory -Path (Join-Path $fixtureRoot $relative) -Force | Out-Null
        }
        $identity = Join-Path $fixtureRoot 'start\win\env\identity.env'
        $auth = Join-Path $fixtureRoot 'mfes\apps\auth\.env.local'
        $keyFile = Join-Path $fixtureRoot 'start\win\platform-setup\setup-key.txt'
        [IO.File]::WriteAllText($identity, "# preserved`nOTHER=a:b/#% & value`n")
        [IO.File]::WriteAllText($auth, "NEXTAUTH_URL=http://localhost:4310`n")
        [IO.File]::WriteAllText((Join-Path $fixtureRoot 'start\win\conf\services.json'),
            '{"services":[{"code":"identity","port":8001},{"code":"audit","port":8002},{"code":"notification","port":8010}]}')
    }
    It 'preserves the key and unrelated configuration across repeated preparations' {
        Initialize-BillPlatformSetup $fixtureRoot
        $firstKey = [IO.File]::ReadAllText($keyFile)
        $firstIdentity = [IO.File]::ReadAllText($identity)
        $firstAuth = [IO.File]::ReadAllText($auth)
        Initialize-BillPlatformSetup $fixtureRoot
        [IO.File]::ReadAllText($keyFile) | Should Be $firstKey
        [IO.File]::ReadAllText($identity) | Should Be $firstIdentity
        [IO.File]::ReadAllText($auth) | Should Be $firstAuth
        $firstIdentity | Should Match 'OTHER=a:b/#% & value'
        $firstAuth | Should Match '"Notification":"http://127.0.0.1:8010"'
        (Get-Acl -LiteralPath $keyFile).AreAccessRulesProtected | Should Be $true
    }
    It 'restores an existing environment key instead of rotating it when the key file is absent' {
        $existingKey = [Convert]::ToBase64String([Guid]::NewGuid().ToByteArray() + [Guid]::NewGuid().ToByteArray()).TrimEnd('=')
        $existingKey = $existingKey.Replace('+', '-').Replace('/', '_')
        Add-Content -LiteralPath $identity -Value "IDENTITY_SETUP_KEY=$existingKey"
        Add-Content -LiteralPath $auth -Value "IDENTITY_SETUP_KEY=$existingKey"
        Initialize-BillPlatformSetup $fixtureRoot
        [IO.File]::ReadAllText($keyFile) | Should Be $existingKey
    }
    It 'refuses conflicting keys without changing either environment' {
        Add-Content -LiteralPath $identity -Value ('IDENTITY_SETUP_KEY=' + ('a' * 43))
        Add-Content -LiteralPath $auth -Value ('IDENTITY_SETUP_KEY=' + ('b' * 43))
        $before = [IO.File]::ReadAllText($identity)
        { Initialize-BillPlatformSetup $fixtureRoot } | Should Throw
        [IO.File]::ReadAllText($identity) | Should Be $before
        Test-Path -LiteralPath $keyFile | Should Be $false
    }
    It 'restores both environment contents if a write fails' {
        $beforeIdentity = [IO.File]::ReadAllText($identity)
        $beforeAuth = [IO.File]::ReadAllText($auth)
        $script:failedOnce = $false
        Mock Write-BillSetupPrivateFile {
            param($Path, $Content)
            if ($Path -eq $auth -and -not $script:failedOnce) { $script:failedOnce = $true; throw 'simulated write failure' }
            [IO.File]::WriteAllText($Path, $Content)
        }
        { Initialize-BillPlatformSetup $fixtureRoot } | Should Throw
        [IO.File]::ReadAllText($identity) | Should Be $beforeIdentity
        [IO.File]::ReadAllText($auth) | Should Be $beforeAuth
    }
}
