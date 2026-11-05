# Generate per-service dev .env files under start\win\env\<code>.env.
#
# These carry DEVELOPMENT-ONLY defaults: a local MySQL DATABASE_URL and freshly
# generated signing/encryption secrets. They are NOT committed and NOT for any
# shared or production environment -- real secrets come from the secret manager
# (CLAUDE.md 5.9). start-services.ps1 reads these files and injects the values
# into each uvicorn child process (pydantic BaseSettings reads process env).
#
# Existing files preserve database and encryption settings. Gateway verification
# keys are aligned to Identity; -Force regenerates defaults but retains bank
# encryption keys so persisted company-bank details remain readable.

function _BillMysqlUrl {
    param(
        [Parameter(Mandatory)]$Mysql,
        [Parameter(Mandatory)][string]$DbName
    )
    $auth = if ([string]$Mysql.password -ne '') {
        "$([Uri]::EscapeDataString([string]$Mysql.superuser)):$([Uri]::EscapeDataString([string]$Mysql.password))@"
    } else {
        "$([Uri]::EscapeDataString([string]$Mysql.superuser))@"
    }
    return "mysql+asyncmy://$auth$($Mysql.host):$($Mysql.port)/$DbName"
}

function Add-BillAccountingTaxJurisdictions {
    param([Parameter(Mandatory)][AllowEmptyString()][string[]]$Lines)
    # Keep explicit installation choices, including an intentionally empty list.
    if (@($Lines | Where-Object { $_.StartsWith('ACCOUNTING_UTGST_STATES=') }).Count) {
        return $Lines
    }
    $reference = Get-Content (Join-Path $Global:BILL_CONF_DIR 'utgst-states.json') -Raw | ConvertFrom-Json
    $states = ConvertTo-Json -InputObject @($reference.states) -Compress
    return @($Lines) + @("ACCOUNTING_UTGST_STATES=$states")
}

function Add-BillIdentityBankEncryption {
    # Development-only bootstrap. Existing keys are retained byte for byte:
    # replacing them would make existing company-bank details unreadable.
    param([Parameter(Mandatory)][AllowEmptyString()][string[]]$Lines)
    $active = @($Lines | Where-Object { $_.StartsWith('IDENTITY_BANK_ACTIVE_KEY_ID=') })
    $rings = @($Lines | Where-Object { $_.StartsWith('IDENTITY_BANK_ENCRYPTION_KEYS=') })
    if ($active.Count -eq 0 -and $rings.Count -eq 0) {
        # New-BillSecret returns unpadded base64url; AES configuration requires
        # standard padded base64. Exactly 32 bytes has one padding character.
        $key = (New-BillSecret -Bytes 32).Replace('-', '+').Replace('_', '/') + '='
        $ring = @{ 'development-v1' = $key } | ConvertTo-Json -Compress
        return @($Lines) + @('IDENTITY_BANK_ACTIVE_KEY_ID=development-v1', "IDENTITY_BANK_ENCRYPTION_KEYS=$ring")
    }
    if ($active.Count -ne 1 -or $rings.Count -ne 1) {
        throw 'Identity bank encryption is partially configured. Restore the matching active key and key ring; existing keys were not changed.'
    }
    try {
        $identifier = ($active[0] -split '=', 2)[1]
        $configured = (($rings[0] -split '=', 2)[1] | ConvertFrom-Json)
        $property = $configured.PSObject.Properties[$identifier]
        if (-not $identifier -or $null -eq $property -or [Convert]::FromBase64String([string]$property.Value).Length -ne 32) {
            throw 'Invalid active bank key.'
        }
    } catch {
        throw 'Identity bank encryption configuration is invalid. Restore the existing key ring; no key was replaced.'
    }
    return $Lines
}

function Invoke-BillConfigureLocalAuth {
    # With the default (local) sign-in provider the installation needs its own client, BFF and
    # key-encryption secrets in identity.env and the Auth app's .env.local. The helper is idempotent,
    # keeps what exists, leaves an installation that chose Authentik alone, and never prints a secret.
    # It is not part of Invoke-BillWriteEnvs so that writing a sandbox env directory never touches
    # the real Auth app file.
    $identityEnv = Join-Path $Global:BILL_ENV_DIR 'identity.env'
    if (-not (Test-Path -LiteralPath $identityEnv)) { return }
    $python = Join-Path $Global:BILL_REPO_ROOT 'apis/identity/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python -ErrorAction Stop).Source }
    $helper = Join-Path $Global:BILL_WIN_ROOT 'configure-local-auth.py'
    $authEnv = Join-Path $Global:BILL_REPO_ROOT 'mfes/apps/auth/.env.local'
    & $python $helper --env-dir $Global:BILL_ENV_DIR --auth-env $authEnv
    if ($LASTEXITCODE -ne 0) { throw 'Local sign-in setup failed; existing settings were not changed.' }
}

function Invoke-BillWriteEnvs {
    param(
        [Parameter(Mandatory)]$Config,
        [switch]$Force
    )
    Write-BillStep 'Service env files'

    if (-not (Test-Path $Global:BILL_ENV_DIR)) {
        New-Item -ItemType Directory -Path $Global:BILL_ENV_DIR -Force | Out-Null
    }

    $mysql = $Config.infra.mysql
    $identityEnv = Join-Path $Global:BILL_ENV_DIR 'identity.env'
    $gatewaySigningSecret = $null
    if ((Test-Path -LiteralPath $identityEnv) -and -not $Force) {
        $signerLines = @(Get-Content -LiteralPath $identityEnv -Encoding UTF8 | Where-Object {
            $_ -match '^IDENTITY_ACTOR_SIGNING_SECRET='
        })
        if ($signerLines.Count -ne 1) { throw 'Identity environment needs one gateway signing key.' }
        $gatewaySigningSecret = $signerLines[0].Substring($signerLines[0].IndexOf('=') + 1)
        if ($gatewaySigningSecret.Length -lt 32) { throw 'Identity gateway signing key is invalid.' }
    } else {
        $gatewaySigningSecret = New-BillSecret
    }

    foreach ($svc in $Config.services) {
        $prefix  = [string]$svc.env_prefix
        $envFile = Join-Path $Global:BILL_ENV_DIR ("{0}.env" -f $svc.code)

        if ((Test-Path $envFile) -and -not $Force) {
            $signerName = "${prefix}ACTOR_SIGNING_SECRET"
            $existingLines = @(Get-Content -LiteralPath $envFile -Encoding UTF8)
            $existingSigners = @($existingLines | Where-Object { $_.StartsWith("${signerName}=") })
            $updatedLines = @($existingLines | Where-Object { -not $_.StartsWith("${signerName}=") })
            $updatedLines += "${signerName}=$gatewaySigningSecret"
            if ([string]$svc.code -eq 'identity') {
                $updatedLines = @(Add-BillIdentityBankEncryption -Lines $updatedLines)
            }
            if ([string]$svc.code -eq 'accounting') {
                $updatedLines = @(Add-BillAccountingTaxJurisdictions -Lines $updatedLines)
            }
            if ([string]$svc.code -eq 'accounting' -and -not @($updatedLines | Where-Object { $_.StartsWith('ACCOUNTING_STOCK_CATALOG_URL=') }).Count) {
                # Browser-authorized published tracking definitions; no service credential.
                $updatedLines += 'ACCOUNTING_STOCK_CATALOG_URL=http://127.0.0.1:8090/catalog'
            }
            if ([string]$svc.code -eq 'catalog' -and -not @($updatedLines | Where-Object { $_.StartsWith('CATALOG_SIMPLE_CREATION_ORIGINS=') }).Count) {
                $updatedLines += 'CATALOG_SIMPLE_CREATION_ORIGINS={"accounting":"http://127.0.0.1:8011","vouchers":"http://127.0.0.1:8012"}'
            }
            if ($existingSigners.Count -ne 1 -or $existingSigners[0] -cne "${signerName}=$gatewaySigningSecret" -or $updatedLines.Count -ne $existingLines.Count) {
                [System.IO.File]::WriteAllLines($envFile, $updatedLines, [System.Text.UTF8Encoding]::new($false))
                Write-BillLog "aligned gateway verification and required development settings: $($svc.code).env" 'OK'
            }
            Write-BillLog "env exists: $($svc.code).env (preserving database and encryption)" 'SKIP'
            Add-BillSummary "env:$($svc.code)" 'SKIP' $envFile
            continue
        }

        # Base: every service needs a database URL and an actor signing secret.
        $pairs = [ordered]@{}
        $pairs["${prefix}DATABASE_URL"]        = _BillMysqlUrl -Mysql $mysql -DbName ([string]$svc.db)
        $pairs["${prefix}ACTOR_SIGNING_SECRET"] = $gatewaySigningSecret

        # Per-service required/optional extras, matched to each config.py.
        switch ([string]$svc.code) {
            'identity' {
                $pairs["${prefix}CURSOR_SIGNING_SECRET"] = New-BillSecret
                $pairs["${prefix}REDIS_URL"] = "redis://$($Config.infra.redis.host):$($Config.infra.redis.port)/0"
            }
            'audit' {
                $pairs["${prefix}CURSOR_SIGNING_SECRET"] = New-BillSecret
            }
            'notification' {
                $pairs["${prefix}CURSOR_SIGNING_SECRET"] = New-BillSecret
                $pairs["${prefix}DATA_ENCRYPTION_KEY"]   = New-BillSecret
            }
            'reports' {
                $pairs["${prefix}ARTIFACT_SIGNING_SECRET"] = New-BillSecret
            }
            'design' {
                $pairs["${prefix}CURSOR_SIGNING_SECRET"] = New-BillSecret
            }
            'vouchers' {
                $pairs["${prefix}ARTIFACT_SIGNING_SECRET"] = New-BillSecret
            }
            'catalog' {
                $pairs["${prefix}SIMPLE_CREATION_ORIGINS"] = '{"accounting":"http://127.0.0.1:8011","vouchers":"http://127.0.0.1:8012"}'
            }
            'accounting' {
                # Optional; 32 hex-encoded bytes per the encryption_key validator.
                $pairs["${prefix}ENCRYPTION_KEY"] = New-BillHexKey
                $pairs["${prefix}STOCK_CATALOG_URL"] = 'http://127.0.0.1:8090/catalog'
            }
            default { }
        }

        $lines = @(
            "# Dev-only environment for the $($svc.code) service. Generated by setup.ps1.",
            "# NOT for shared/production use. Real secrets come from the secret manager.",
            "# Regenerate with: setup.ps1 -Component envs -Recreate"
        )
        foreach ($k in $pairs.Keys) {
            $lines += ("{0}={1}" -f $k, $pairs[$k])
        }
        if ([string]$svc.code -eq 'accounting') {
            if (Test-Path -LiteralPath $envFile) {
                $lines += @(Get-Content -LiteralPath $envFile -Encoding UTF8 | Where-Object {
                    $_.StartsWith('ACCOUNTING_UTGST_STATES=')
                })
            }
            $lines = @(Add-BillAccountingTaxJurisdictions -Lines $lines)
        }
        if ([string]$svc.code -eq 'identity') {
            if (Test-Path -LiteralPath $envFile) {
                # Even an explicit dev-env regeneration must retain data keys.
                # Rotation belongs to Identity's audited encryption workflow.
                # The same goes for the sign-in provider choice and the local provider's settings: the
                # key-encryption key inside IDENTITY_LOCAL_AUTH protects stored signing keys, so
                # replacing it would make every one of them unreadable.
                $lines += @(Get-Content -LiteralPath $envFile -Encoding UTF8 | Where-Object {
                    $_.StartsWith('IDENTITY_BANK_ACTIVE_KEY_ID=') -or $_.StartsWith('IDENTITY_BANK_ENCRYPTION_KEYS=') -or
                    $_.StartsWith('IDENTITY_AUTH_PROVIDER=') -or $_.StartsWith('IDENTITY_LOCAL_AUTH=')
                })
            }
            $lines = @(Add-BillIdentityBankEncryption -Lines $lines)
        }

        Set-Content -LiteralPath $envFile -Value $lines -Encoding ascii
        Write-BillLog "wrote $($svc.code).env" 'OK'
        Add-BillSummary "env:$($svc.code)" 'OK' $envFile
    }

    # Pair native stock/source credentials after every service environment exists.
    # The helper preserves existing values and does not activate stock posting.
    $stockEnvironments = @('identity','catalog','accounting','vouchers' | Where-Object {
        Test-Path -LiteralPath (Join-Path $Global:BILL_ENV_DIR ($_ + '.env'))
    })
    if ($stockEnvironments.Count -eq 4) {
        $stockConnections = Join-Path $Global:BILL_WIN_ROOT 'configure-stock-connections.py'
        $stockPython = Join-Path $Global:BILL_REPO_ROOT 'apis/accounting/.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $stockPython)) {
            $stockPython = (Get-Command python -ErrorAction Stop).Source
        }
        & $stockPython $stockConnections --env-dir $Global:BILL_ENV_DIR
        if ($LASTEXITCODE -ne 0) { throw 'Stock connection setup failed; existing credentials require review.' }
    }
    Write-BillLog "Env files under $Global:BILL_ENV_DIR" 'INFO'
}
