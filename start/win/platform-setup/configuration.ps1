Set-StrictMode -Version Latest

function Set-BillSetupPrivateAcl([string]$Path) {
    $acl = [IO.File]::GetAccessControl($Path, [Security.AccessControl.AccessControlSections]::Access)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($rule) }
    $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($account, 'FullControl', 'Allow')))
    [IO.File]::SetAccessControl($Path, $acl)
}

function Write-BillSetupPrivateFile([string]$Path, [string]$Content) {
    $temporary = Join-Path (Split-Path -Parent $Path) ([Guid]::NewGuid().ToString('N') + '.tmp')
    $backup = $temporary + '.backup'
    try {
        [IO.File]::WriteAllText($temporary, '')
        Set-BillSetupPrivateAcl $temporary
        [IO.File]::WriteAllText($temporary, $Content, (New-Object Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $Path) {
            Set-BillSetupPrivateAcl $Path
            [IO.File]::Replace($temporary, $Path, $backup)
        }
        else { [IO.File]::Move($temporary, $Path) }
        Set-BillSetupPrivateAcl $Path
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Update-BillSetupEnvironment([string]$Content, [hashtable]$Values) {
    $lines = @($Content -split '\r?\n' | Where-Object {
        $line = $_
        -not @($Values.Keys | Where-Object { $line -match ('^\s*' + [regex]::Escape($_) + '\s*=') }).Count
    })
    while ($lines.Count -gt 0 -and $lines[-1] -eq '') { $lines = @($lines | Select-Object -SkipLast 1) }
    foreach ($name in @($Values.Keys | Sort-Object)) { $lines += "$name=$($Values[$name])" }
    return ($lines -join [Environment]::NewLine) + [Environment]::NewLine
}

function Initialize-BillPlatformSetup([string]$RepositoryRoot) {
    $keyPath = Join-Path $RepositoryRoot 'start\win\platform-setup\setup-key.txt'
    $identityPath = Join-Path $RepositoryRoot 'start\win\env\identity.env'
    $authPath = Join-Path $RepositoryRoot 'mfes\apps\auth\.env.local'
    $original = @{}
    foreach ($path in @($identityPath, $authPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing configuration file: $path" }
        $original[$path] = [IO.File]::ReadAllText($path)
    }
    $registry = Get-Content -LiteralPath (Join-Path $RepositoryRoot 'start\win\conf\services.json') -Raw | ConvertFrom-Json
    $services = @{}
    foreach ($entry in $registry.services) {
        if ($entry.code -eq 'identity') { continue }
        $label = (Get-Culture).TextInfo.ToTitleCase([string]$entry.code)
        $services[$label] = "http://127.0.0.1:$($entry.port)"
    }
    if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
        Set-BillSetupPrivateAcl $keyPath
        $setupKey = [IO.File]::ReadAllText($keyPath).Trim()
    } else {
        $existing = @($original.Values | ForEach-Object {
            foreach ($match in [regex]::Matches($_, '(?m)^IDENTITY_SETUP_KEY=([^\r\n]+)')) { $match.Groups[1].Value.Trim() }
        } | Select-Object -Unique)
        if ($existing.Count -gt 1) { throw 'Identity and Auth setup keys differ. Resolve the configuration locally before preparing.' }
        if ($existing.Count -eq 1) { $setupKey = $existing[0] }
        else {
            $random = New-Object byte[] 32
            $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
            try { $generator.GetBytes($random) } finally { $generator.Dispose() }
            $setupKey = [Convert]::ToBase64String($random).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        }
        if ($setupKey -notmatch '^[A-Za-z0-9_-]{32,128}$') { throw 'Existing setup key is invalid; inspect it locally.' }
        Write-BillSetupPrivateFile $keyPath $setupKey
    }
    if ($setupKey -notmatch '^[A-Za-z0-9_-]{32,128}$') { throw 'Existing setup key is invalid; inspect it locally.' }
    $updated = @{}
    $updated[$identityPath] = Update-BillSetupEnvironment $original[$identityPath] @{IDENTITY_SETUP_KEY=$setupKey}
    $updated[$authPath] = Update-BillSetupEnvironment $original[$authPath] @{
        IDENTITY_SETUP_KEY=$setupKey; SETUP_SERVICE_URLS=($services | ConvertTo-Json -Compress)
    }
    $written = @()
    try {
        foreach ($path in @($identityPath, $authPath)) {
            $written += $path
            Write-BillSetupPrivateFile $path $updated[$path]
        }
    } catch {
        foreach ($path in $written) { Write-BillSetupPrivateFile $path $original[$path] }
        throw 'Setup configuration could not be written. Original environment contents were restored.'
    }
}
