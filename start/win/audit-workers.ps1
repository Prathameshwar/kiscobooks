[CmdletBinding()]
param(
    [ValidateSet('start','stop','status')][string]$Action = 'status',
    [ValidateSet('all','identity-catalog-publisher','catalog-identity-source','identity-publisher','reports-publisher','reports-worker','accounting-publisher','accounting-posting-delivery','catalog-publisher','design-publisher','vouchers-publisher','vouchers-artifacts','vouchers-sources','vouchers-executions','audit-consumer','audit-publisher','vouchers-notification-publisher','accounting-notification-publisher','notification-vouchers','notification-accounting','notification-dispatch','notification-scheduler','notification-platform','notification-identity','identity-notification-publisher','notification-publisher')][string]$Worker = 'all',
    [string]$EnvDirectory = '',
    [string]$RuntimeDirectory = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Action -eq 'stop') { . (Join-Path $PSScriptRoot 'lib/runtime.ps1') }
if (!$EnvDirectory) { $EnvDirectory = Join-Path $PSScriptRoot 'env' }
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtime = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else { Join-Path $workspace '.tools/audit-workers' }
if (!$runtime.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Worker state directory must be inside this workspace.'
}
# Normalize PATH casing for Windows PowerShell's Start-Process environment handling.
$workerPath = $env:Path
Remove-Item Env:PATH -ErrorAction SilentlyContinue
Remove-Item Env:Path -ErrorAction SilentlyContinue
$env:Path = $workerPath
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$definitions = @(
    @{Name='identity-catalog-publisher'; Project='identity'; Module='identity.tasks.catalog_publisher'; Env='identity.env'},
    @{Name='catalog-identity-source'; Project='catalog'; Module='catalog.tasks.source_worker'; Env='catalog.env'},
    @{Name='identity-publisher'; Project='identity'; Module='identity.tasks.audit_publisher'; Env='identity.env'},
    @{Name='reports-worker'; Project='reports'; Module='reports.tasks.worker'; Env='reports.env'},
    @{Name='reports-publisher'; Project='reports'; Module='reports.tasks.audit_publisher'; Env='reports.env'},
    @{Name='vouchers-executions'; Project='vouchers'; Module='vouchers.tasks.execution_worker'; Env='vouchers.env'},
    @{Name='vouchers-artifacts'; Project='vouchers'; Module='vouchers.tasks.artifact_worker'; Env='vouchers.env'},
    @{Name='vouchers-sources'; Project='vouchers'; Module='vouchers.tasks.source_worker'; Env='vouchers.env'},
    @{Name='vouchers-publisher'; Project='vouchers'; Module='vouchers.tasks.audit_publisher'; Env='vouchers.env'},
    @{Name='vouchers-notification-publisher'; Project='vouchers'; Module='vouchers.tasks.notification_publisher'; Env='vouchers.env'},
    @{Name='accounting-notification-publisher'; Project='accounting'; Module='accounting.tasks.notification_publisher'; Env='accounting.env'},
    @{Name='notification-vouchers'; Project='notification'; Module='notification.tasks.vouchers'; Env='notification.env'},
    @{Name='notification-accounting'; Project='notification'; Module='notification.tasks.party_contacts'; Env='notification.env'},
    @{Name='notification-dispatch'; Project='notification'; Module='notification.tasks.delivery_worker'; Env='notification.env'},
    @{Name='notification-platform'; Project='notification'; Module='notification.tasks.platform'; Env='notification.env'},
    @{Name='notification-identity'; Project='notification'; Module='notification.tasks.identity'; Env='notification.env'},
    @{Name='identity-notification-publisher'; Project='identity'; Module='identity.tasks.notification_publisher'; Env='identity.env'},
    @{Name='notification-publisher'; Project='notification'; Module='notification.tasks.audit_publisher'; Env='notification.env'},
    @{Name='notification-scheduler'; Project='notification'; Module='notification.tasks.scheduler'; Env='notification.env'},
    @{Name='catalog-publisher'; Project='catalog'; Module='catalog.tasks.audit_publisher'; Env='catalog.env'},
    @{Name='design-publisher'; Project='design'; Module='design.tasks.audit_publisher'; Env='design.env'},
    @{Name='accounting-publisher'; Project='accounting'; Module='accounting.tasks.audit_publisher'; Env='accounting.env'},
    @{Name='accounting-posting-delivery'; Project='accounting'; Module='accounting.tasks.posting_delivery'; Env='accounting.env'},
    @{Name='audit-consumer'; Project='audit'; Module='audit.tasks.consume'; Env='audit.env'},
    @{Name='audit-publisher'; Project='audit'; Module='audit.tasks.publish'; Env='audit-publisher.env'}
)
$failed = 0
foreach ($definition in $definitions) {
    if ($Worker -ne 'all' -and $Worker -ne $definition.Name) { continue }
    try {
        $statePath = Join-Path $runtime ($definition.Name + '.json')
        $python = Join-Path $workspace ('apis/' + $definition.Project + '/.venv/Scripts/python.exe')
        $envFile = Join-Path $EnvDirectory $definition.Env
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -in @('identity-catalog-publisher','catalog-identity-source')) {
            $required = if ($definition.Name -eq 'identity-catalog-publisher') { '^IDENTITY_SOURCE_BROKER_URL=' } else { '^CATALOG_IDENTITY_SOURCE=' }
            if (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern $required -Quiet)) {
                Write-Host ('Skipping ' + $definition.Name + ': Catalog source delivery is not configured.')
                continue
            }
        }
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -eq 'identity-publisher' -and
            (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern '^IDENTITY_AUDIT_BROKER_URL=' -Quiet))) {
            Write-Host 'Skipping identity-publisher: audit delivery is not configured.'
            continue
        }
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -in @('vouchers-notification-publisher','accounting-notification-publisher','notification-vouchers','notification-accounting','notification-dispatch','notification-platform','notification-identity','identity-notification-publisher','notification-publisher')) {
            $required = switch ($definition.Name) {
                'vouchers-notification-publisher' { '^VOUCHERS_NOTIFICATION_BROKER_URL=' }
                'accounting-notification-publisher' { '^ACCOUNTING_NOTIFICATION_BROKER_URL=' }
                'notification-vouchers' { '^NOTIFICATION_VOUCHER_SOURCES=' }
                'notification-accounting' { '^NOTIFICATION_ACCOUNTING_SOURCES=' }
                'notification-dispatch' { '^NOTIFICATION_DISPATCH_ENABLED=true$' }
                'notification-platform' { '^NOTIFICATION_PLATFORM_SOURCES=' }
                'notification-identity' { '^NOTIFICATION_IDENTITY_SOURCES=' }
                'identity-notification-publisher' { '^IDENTITY_NOTIFICATION_BROKER_URL=' }
                'notification-publisher' { '^NOTIFICATION_AUDIT_BROKER_URL=' }
            }
            if (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern $required -Quiet)) {
                Write-Host ('Skipping ' + $definition.Name + ': notification source is not configured.')
                continue
            }
        }
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -eq 'vouchers-executions') {
            if (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern '^VOUCHERS_(STOCK_)?EXECUTION_OWNER=' -Quiet)) {
                Write-Host 'Skipping vouchers-executions: no execution owner configured.'
                continue
            }
        }
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -eq 'accounting-posting-delivery') {
            if (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern '^ACCOUNTING_(STOCK_)?IDENTITY_(POSTING_)?URL=' -Quiet)) {
                Write-Host 'Skipping accounting-posting-delivery: no Identity posting connection configured.'
                continue
            }
        }
        if ($Action -eq 'start' -and $Worker -eq 'all' -and $definition.Name -eq 'reports-worker') {
            if (!(Test-Path -LiteralPath $envFile) -or !(Select-String -LiteralPath $envFile -Pattern '^REPORTS_OWNERS=' -Quiet)) {
                Write-Host 'Skipping reports-worker: no source owner configured.'
                continue
            }
        }
        $running = $null
        if (Test-Path -LiteralPath $statePath) {
            $record = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
            $candidate = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
            if ($candidate) {
                $command = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $record.pid)
                if ($candidate.StartTime.ToUniversalTime().Ticks -ne $record.started -or
                    $candidate.Path -ne $python -or
                    !$command.CommandLine.Contains($definition.Module)) {
                    throw ('Worker PID identity changed; process left untouched: ' + $definition.Name)
                }
                $running = $candidate
            }
        }
        if ($Action -eq 'status') {
            [pscustomobject]@{Worker=$definition.Name; Running=($null -ne $running); Delivery='Use publisher --status and broker queue checks'}
            continue
        }
        if ($Action -eq 'stop') {
            if ($running) {
                # The venv launcher owns a child interpreter; stop the verified process tree.
                Stop-BillProcessTree $running
                if (-not $running.WaitForExit(5000)) { throw ('Could not stop worker: ' + $definition.Name) }
            }
            if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath }
            Write-Output ('Stopped owned worker: ' + $definition.Name)
            continue
        }
        if ($running) {
            Write-Output ('Already running: ' + $definition.Name)
            continue
        }
        if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $envFile)) {
            throw ('Worker interpreter or private environment missing: ' + $definition.Name)
        }
        if ($definition.Name -in @('vouchers-sources', 'vouchers-executions', 'accounting-posting-delivery')) {
            & $python -m $definition.Module --env-file $envFile --check-config
            if ($LASTEXITCODE -ne 0) { throw ('Review private delivery configuration: ' + $definition.Name) }
        }
        # Secrets remain in the private env file, never in command arguments or a batch file.
        $process = Start-Process -FilePath $python -ArgumentList @(
            '-m', $definition.Module, '--env-file', ('"' + $envFile + '"')
        ) -WorkingDirectory (Join-Path $workspace ('apis/' + $definition.Project)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime ($definition.Name + '.stdout.log')) -RedirectStandardError (Join-Path $runtime ($definition.Name + '.stderr.log'))
        @{pid=$process.Id; started=$process.StartTime.ToUniversalTime().Ticks} |
            ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding ASCII
        if ($definition.Name -like '*-publisher' -or $definition.Name -eq 'audit-consumer') {
            Start-Sleep -Milliseconds 500
            if (!(Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                throw ('Audit worker exited during startup; review private configuration: ' + $definition.Name)
            }
        }
        Write-Output ('Started: ' + $definition.Name)
    } catch {
        if ($Action -ne 'stop') { throw }
        Write-Warning ($definition.Name + ' stop failed: ' + $_.Exception.Message)
        $failed++
    }
}
if ($failed) { exit 1 }
