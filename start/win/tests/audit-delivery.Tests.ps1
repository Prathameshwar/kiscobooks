$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib/_common.ps1')
. (Join-Path $winRoot 'lib/runtime.ps1')
. (Join-Path $winRoot 'lib/audit-workers.ps1')

Describe 'Complete audit delivery lifecycle' {
    It 'starts the consumer before all configured publishers, including Design and exports' {
        $directory = Join-Path $TestDrive 'audit-workers'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        foreach ($service in @('identity','catalog','accounting','vouchers','reports','notification','design')) {
            ($service.ToUpperInvariant() + '_AUDIT_BROKER_URL=amqp://isolated.invalid') | Set-Content (Join-Path $directory ($service + '.env'))
        }
        'AUDIT_PUBLISHER_BROKER_URL=amqp://isolated.invalid' | Set-Content (Join-Path $directory 'audit-publisher.env')
        @('AUDIT_BROKER_URL=amqp://isolated.invalid','AUDIT_SOURCE_CREDENTIALS={"test":{}}') | Set-Content (Join-Path $directory 'audit.env')
        $workers = @(Get-BillAuditWorkers -EnvDirectory $directory)
        $workers[0] | Should Be 'audit-consumer'
        $workers.Count | Should Be 9
        ($workers -contains 'design-publisher') | Should Be $true
        ($workers -contains 'audit-publisher') | Should Be $true
        Get-Content (Join-Path $winRoot 'audit-workers.ps1') -Raw | Should Match 'design.tasks.audit_publisher'
    }
    It 'prepares every producer idempotently without releasing the historical cutoff' {
        $directory = Join-Path $TestDrive 'audit-prepare'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        foreach ($service in @('identity','catalog','accounting','vouchers','reports','notification','design')) {
            ($service.ToUpperInvariant() + '_DATABASE_URL=unchanged') | Set-Content (Join-Path $directory ($service + '.env'))
        }
        @('IDENTITY_AUDIT_BROKER_USER=test-publisher','IDENTITY_AUDIT_PUBLISH_AFTER=2026-10-22T00:00:00Z') | Add-Content (Join-Path $directory 'identity.env')
        @('AUDIT_BROKER_URL=amqp://isolated.invalid','AUDIT_DATABASE_URL=unchanged') | Set-Content (Join-Path $directory 'audit.env')
        & (Join-Path $winRoot 'audit-prepare.ps1') -EnvDirectory $directory -WhatIf
        Test-Path (Join-Path $directory 'audit-publisher.env') | Should Be $false
        & (Join-Path $winRoot 'audit-prepare.ps1') -EnvDirectory $directory
        $first = Read-BillEnvironment (Join-Path $directory 'audit.env')
        & (Join-Path $winRoot 'audit-prepare.ps1') -EnvDirectory $directory
        $second = Read-BillEnvironment (Join-Path $directory 'audit.env')
        ($second['AUDIT_SOURCE_CREDENTIALS'] -eq $first['AUDIT_SOURCE_CREDENTIALS']) | Should Be $true
        $sources = $second['AUDIT_SOURCE_CREDENTIALS'] | ConvertFrom-Json
        @($sources.PSObject.Properties).Count | Should Be 8
        ($sources.'identity.current'.event_types -contains 'voucher_source.discovery_read') | Should Be $true
        ($sources.'identity.current'.event_types -contains 'company.setup_requested') | Should Be $true
        ($sources.'identity.current'.event_types -contains 'company.setup_retried') | Should Be $true
        ($sources.'identity.current'.event_types -contains 'company.setup_progressed') | Should Be $true
        ($sources.'identity.current'.event_types -contains 'report_source.discovery_read') | Should Be $true
        ($sources.'identity.current'.event_types -contains 'report_source.enrolled') | Should Be $true
        ($sources.'accounting.current'.event_types -contains 'accounting.bank_statement_mapping.publish') | Should Be $true
        $identity = Read-BillEnvironment (Join-Path $directory 'identity.env')
        $identity['IDENTITY_AUDIT_PUBLISH_AFTER'] | Should Be '2026-10-22T00:00:00Z'
        $identity['IDENTITY_DATABASE_URL'] | Should Be 'unchanged'
    }
    It 'keeps sensitive queries and referers out of the gateway log format' {
        $nginx = Get-Content (Join-Path $winRoot 'conf/nginx.conf') -Raw
        $nginx | Should Not Match '\$http_referer'
        $nginx | Should Not Match '"\$request"'
        $nginx | Should Match 'trace=\$bill_trace_id'
    }
}

Describe 'Audit contract refresh during startup' {
    It 'refreshes drifted contracts before stopping publishers then the consumer, and leaves unchanged workers alone' {
        $originalRoot = $Global:BILL_WIN_ROOT
        $originalEnv = $Global:BILL_ENV_DIR
        try {
            $Global:BILL_WIN_ROOT = Join-Path $TestDrive 'audit-refresh'
            $Global:BILL_ENV_DIR = Join-Path $Global:BILL_WIN_ROOT 'env'
            New-Item -ItemType Directory -Path $Global:BILL_ENV_DIR -Force | Out-Null
            @('AUDIT_BROKER_URL=amqp://isolated.invalid','AUDIT_SOURCE_CREDENTIALS={"old":{}}') | Set-Content (Join-Path $Global:BILL_ENV_DIR 'audit.env')
            'IDENTITY_AUDIT_BROKER_URL=amqp://isolated.invalid' | Set-Content (Join-Path $Global:BILL_ENV_DIR 'identity.env')
            Set-Content (Join-Path $Global:BILL_WIN_ROOT 'audit-prepare.ps1') @'
param($EnvDirectory)
Add-Content (Join-Path $PSScriptRoot 'calls.txt') 'prepare'
$path = Join-Path $EnvDirectory 'audit.env'
(Get-Content $path -Raw).Replace('"old"','"new"').TrimEnd() | Set-Content $path
exit 0
'@
            Set-Content (Join-Path $Global:BILL_WIN_ROOT 'audit-workers.ps1') @'
param($Action, $Worker)
Add-Content (Join-Path $PSScriptRoot 'calls.txt') ($Action + ':' + $Worker)
exit 0
'@
            Update-BillAuditContractsForStart
            $calls = @(Get-Content (Join-Path $Global:BILL_WIN_ROOT 'calls.txt'))
            ($calls -join ',') | Should Be 'prepare,stop:identity-publisher,stop:audit-consumer'
            Update-BillAuditContractsForStart
            $calls = @(Get-Content (Join-Path $Global:BILL_WIN_ROOT 'calls.txt'))
            ($calls -join ',') | Should Be 'prepare,stop:identity-publisher,stop:audit-consumer,prepare'
            Set-Content (Join-Path $Global:BILL_WIN_ROOT 'audit-prepare.ps1') 'exit 7'
            { Update-BillAuditContractsForStart } | Should Throw
            (@(Get-Content (Join-Path $Global:BILL_WIN_ROOT 'calls.txt')) -join ',') | Should Be ($calls -join ',')
            'AUDIT_BROKER_URL=amqp://isolated.invalid' | Set-Content (Join-Path $Global:BILL_ENV_DIR 'audit.env')
            Update-BillAuditContractsForStart  # Unconfigured delivery is not implicitly enabled.
            @('AUDIT_BROKER_URL=amqp://isolated.invalid','AUDIT_SOURCE_CREDENTIALS={"new":{}}') | Set-Content (Join-Path $Global:BILL_ENV_DIR 'audit.env')
            Set-Content (Join-Path $Global:BILL_WIN_ROOT 'audit-prepare.ps1') 'param($EnvDirectory); exit 0'
            $stamp = Join-Path $Global:BILL_WIN_ROOT 'runtime/audit-contracts.sha256'
            Remove-Item -LiteralPath $stamp
            $workerScript = Join-Path $Global:BILL_WIN_ROOT 'audit-workers.ps1'
            $workerText = Get-Content $workerScript -Raw
            Set-Content $workerScript 'param($Action, $Worker); exit 7'
            { Update-BillAuditContractsForStart } | Should Throw
            Test-Path -LiteralPath $stamp | Should Be $false
            Set-Content $workerScript $workerText
            Update-BillAuditContractsForStart
            Test-Path -LiteralPath $stamp | Should Be $true
            $start = Get-Content (Join-Path $originalRoot 'start-services.ps1') -Raw
            ($start.IndexOf('Update-BillAuditContractsForStart') -lt $start.IndexOf('Get-BillAuditWorkers -EnvDirectory')) | Should Be $true
        } finally {
            $Global:BILL_WIN_ROOT = $originalRoot
            $Global:BILL_ENV_DIR = $originalEnv
        }
    }

    It 'names the unconfigured and stalled producers without showing private configuration' {
        $states = @(
            [pscustomobject]@{service='identity';configured=$false;pending=18949;exhausted=0;oldest_age_seconds=600},
            [pscustomobject]@{service='audit';configured=$true;pending=0;exhausted=0;oldest_age_seconds=0},
            [pscustomobject]@{service='broker';broker=@{ready=$true}}
        )
        $detail = Format-BillAuditDeliveryDetail -States $states -Missing 0
        $detail | Should Match 'unconfigured=1 \(identity\)'
        $detail | Should Match 'stalled=identity'
        $detail | Should Match 'pending=18949'
        $states[0] = [pscustomobject]@{service='identity';configured=$false;error_type='ConnectionError'}
        (Format-BillAuditDeliveryDetail -States $states -Missing 1) | Should Match 'unconfigured=1 \(identity\)'
    }
}
