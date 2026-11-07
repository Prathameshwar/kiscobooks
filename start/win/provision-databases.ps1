[CmdletBinding(SupportsShouldProcess = $true)]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
. (Join-Path $PSScriptRoot 'lib\database-provisioning.ps1')

$config = Get-BillConfig
$mysql = $config.infra.mysql
if (-not $mysql.host -or [int]$mysql.port -lt 1 -or [int]$mysql.port -gt 65535 -or -not $mysql.superuser) {
    throw 'MySQL host, port, or administrative username is invalid in start\win\conf\services.json.'
}
if ([string]$mysql.superuser -cne 'root') {
    throw 'Local database provisioning currently requires the configured MySQL administrator to be root.'
}

$services = @($config.services)
if ($services.Count -eq 0) { throw 'No services are configured in services.json.' }

$databaseNames = @()
$migrations = @()
foreach ($service in $services) {
    $code = [string]$service.code
    $database = [string]$service.db
    if ($code -notmatch '^[a-z][a-z0-9-]*$' -or $database -notmatch '^[a-z][a-z0-9_]*$') {
        throw "Invalid service code or database name in services.json: $code."
    }
    if ($database -in $databaseNames) { throw "Duplicate service database configured: $database." }
    $databaseNames += $database

    $expectedAlembic = "dbs/$code/alembic.ini"
    if ([string]$service.alembic -ne $expectedAlembic) {
        throw "Unexpected Alembic path for $code; expected $expectedAlembic."
    }
    $migrationDirectory = Join-Path $Global:BILL_REPO_ROOT "dbs\$code"
    $alembicIni = Join-Path $migrationDirectory 'alembic.ini'
    if (-not (Test-Path -LiteralPath $alembicIni -PathType Leaf)) {
        throw "Alembic configuration not found for $code at $alembicIni."
    }

    $project = Join-Path $Global:BILL_REPO_ROOT ([string]$service.project)
    $python = Join-Path $project '.venv\Scripts\python.exe'
    $environmentPath = Join-Path $Global:BILL_ENV_DIR "$code.env"
    $environment = Read-BillEnvironment -Path $environmentPath
    $databaseUrlName = ([string]$service.env_prefix) + 'DATABASE_URL'
    $databaseUrl = [string]$environment[$databaseUrlName]
    $urlMatch = [regex]::Match($databaseUrl, '^mysql\+asyncmy://[^/]+/([A-Za-z][A-Za-z0-9_]*)(?:\?.*)?$')
    if (-not $urlMatch.Success -or $urlMatch.Groups[1].Value -cne $database) {
        throw "$environmentPath must configure $databaseUrlName to the $database database."
    }
    if (-not $WhatIfPreference) {
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw "Python environment for $code is missing. Run setup.bat -Component python."
        }
    }

    $migrations += @{
        Code = $code
        Database = $database
        Python = $python
        Directory = $migrationDirectory
        DatabaseUrlName = $databaseUrlName
        DatabaseUrl = $databaseUrl
    }
}

Write-Output ("MySQL target: {0}:{1}" -f $mysql.host, $mysql.port)
Write-Output ("Service databases: {0}" -f ($databaseNames -join ', '))

$identityProject = Join-Path $Global:BILL_REPO_ROOT 'apis\identity'
$identityPython = Join-Path $identityProject '.venv\Scripts\python.exe'
if (-not $WhatIfPreference -and -not (Test-Path -LiteralPath $identityPython -PathType Leaf)) {
    throw 'Identity Python environment is missing. Run setup.bat -Component python.'
}

if ($WhatIfPreference) {
    [void]$PSCmdlet.ShouldProcess("$($mysql.host):$($mysql.port)", 'Create any missing service databases')
    foreach ($migration in $migrations) {
        [void]$PSCmdlet.ShouldProcess($migration.Code, 'Upgrade Alembic migrations to head')
    }
    Write-Output 'WhatIf: no databases or schemas were changed.'
    exit 0
}

$securePassword = Read-Host -Prompt "MySQL password for $($mysql.superuser)@$($mysql.host):$($mysql.port)" -AsSecureString
if ($securePassword.Length -eq 0) { throw 'A non-empty MySQL password is required.' }
$passwordPointer = [IntPtr]::Zero
try {
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $mysqlPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
} finally {
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
    $securePassword.Dispose()
}
$databaseUrls = @{}
$pendingEnvironmentUpdates = @()
foreach ($migration in $migrations) {
    $url = New-BillDatabaseUrl -Username ([string]$mysql.superuser) -Password $mysqlPassword `
        -HostName ([string]$mysql.host) -Port ([int]$mysql.port) -Database $migration.Database
    $databaseUrls[$migration.Code] = $url

    $environmentPath = Join-Path $Global:BILL_ENV_DIR ($migration.Code + '.env')
    $originalContent = [IO.File]::ReadAllText($environmentPath, [Text.Encoding]::UTF8)
    $updatedContent = Set-BillEnvironmentValue -Content $originalContent `
        -Name $migration.DatabaseUrlName -Value $url
    $pendingEnvironmentUpdates += @{
        Path = $environmentPath
        Content = $updatedContent
        OriginalContent = $originalContent
    }
}

$databaseScript = Join-Path $PSScriptRoot 'create_databases.py'
if (-not (Test-Path -LiteralPath $databaseScript -PathType Leaf)) {
    throw "Database creation script not found: $databaseScript."
}

$databaseCreationApproved = $PSCmdlet.ShouldProcess(
    "$($mysql.host):$($mysql.port)",
    'Create any missing service databases'
)
if ($databaseCreationApproved) {
    $processVariables = @{
        BILL_PROVISION_MYSQL_HOST = [string]$mysql.host
        BILL_PROVISION_MYSQL_PORT = [string]$mysql.port
        BILL_PROVISION_MYSQL_USER = [string]$mysql.superuser
        BILL_PROVISION_MYSQL_PASSWORD = $mysqlPassword
        BILL_PROVISION_DATABASE_NAMES = ConvertTo-Json -InputObject $databaseNames -Compress
    }
    $previousVariables = @{}
    try {
        foreach ($name in $processVariables.Keys) {
            $previousVariables[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, [string]$processVariables[$name], 'Process')
        }
        & $identityPython $databaseScript
        if ($LASTEXITCODE -ne 0) { throw "Database creation failed (exit code $LASTEXITCODE)." }
    } finally {
        foreach ($name in $processVariables.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previousVariables[$name], 'Process')
        }
    }
} else {
    Write-Output 'Database creation was not approved; migrations and local environment files were left unchanged.'
    exit 0
}

$allMigrationsApproved = $true
foreach ($migration in $migrations) {
    if (-not $PSCmdlet.ShouldProcess($migration.Code, 'Upgrade Alembic migrations to head')) {
        $allMigrationsApproved = $false
        continue
    }

    $previousUrl = [Environment]::GetEnvironmentVariable($migration.DatabaseUrlName, 'Process')
    [Environment]::SetEnvironmentVariable($migration.DatabaseUrlName, $databaseUrls[$migration.Code], 'Process')
    try {
        Push-Location -LiteralPath $migration.Directory
        try {
            Write-Output "Applying $($migration.Code) migrations..."
            & $migration.Python -m alembic -c alembic.ini upgrade head
            if ($LASTEXITCODE -ne 0) {
                throw "$($migration.Code) migrations failed (exit code $LASTEXITCODE)."
            }
        } finally {
            Pop-Location
        }
    } finally {
        [Environment]::SetEnvironmentVariable($migration.DatabaseUrlName, $previousUrl, 'Process')
    }
}

if (-not $allMigrationsApproved) {
    throw 'Not all migrations were approved; service environment files were left unchanged.'
}

$tempFiles = @()
try {
    foreach ($update in $pendingEnvironmentUpdates) {
        $tempPath = $update.Path + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
        [IO.File]::WriteAllText($tempPath, $update.Content, [Text.UTF8Encoding]::new($false))
        $tempFiles += @{ Path = $tempPath; Destination = $update.Path }
    }
    foreach ($tempFile in $tempFiles) {
        Move-Item -LiteralPath $tempFile.Path -Destination $tempFile.Destination -Force
    }
} catch {
    foreach ($update in $pendingEnvironmentUpdates) {
        [IO.File]::WriteAllText($update.Path, $update.OriginalContent, [Text.UTF8Encoding]::new($false))
    }
    throw
} finally {
    foreach ($tempFile in $tempFiles) {
        if (Test-Path -LiteralPath $tempFile.Path) {
            Remove-Item -LiteralPath $tempFile.Path -Force
        }
    }
}

$mysqlPassword = $null
Write-Output 'Configured databases are ready and migrations are at head.'
