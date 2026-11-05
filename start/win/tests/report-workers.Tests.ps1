$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
. (Join-Path $workspace 'start/win/lib/report-workers.ps1')

Describe 'Configured report worker selection' {
    BeforeEach {
        $reports = @{
            REPORTS_SOURCE_VERSIONS_ENABLED='true'; REPORTS_OWNERS='scoped-owner';
            REPORTS_FRAMEWORK_ENABLED='true'; REPORTS_JOB_BROKER_URL='configured';
            REPORTS_AUTHORITY_SOURCES='scoped-authority'; REPORTS_EXPORTS_ENABLED='true';
            REPORTS_ARTIFACT_ROOT='private-folder'
        }
        $accounting = @{ACCOUNTING_REPORT_SNAPSHOT_ENABLED='true'; ACCOUNTING_REPORT_CREDENTIALS='scoped-credential'}
    }
    It 'keeps default admission disabled' {
        @(Get-BillReportWorkers).Count | Should Be 0
    }
    It 'selects the six existing v2 lanes with Windows solo execution' {
        $workers = @(Get-BillReportWorkers -Reports $reports -Accounting $accounting)
        $workers.Count | Should Be 6
        ($workers.Name -contains 'accounting-report-snapshots') | Should Be $true
        ($workers.Name -contains 'reports-sources') | Should Be $true
        ($workers.Name -contains 'reports-dispatcher') | Should Be $true
        ($workers.Name -contains 'reports-short') | Should Be $true
        ($workers.Name -contains 'reports-bulk') | Should Be $true
        ($workers.Name -contains 'reports-render') | Should Be $true
        (($workers | Where-Object Name -eq 'reports-render').Arguments -contains 'solo') | Should Be $true
    }
    It 'starts only the source lanes before run admission' {
        $reports.REPORTS_FRAMEWORK_ENABLED='false'; $reports.REPORTS_EXPORTS_ENABLED='false'
        @(Get-BillReportWorkers -Reports $reports -Accounting $accounting).Count | Should Be 2
    }
    It 'does not start rendering when exports are disabled' {
        $reports.REPORTS_EXPORTS_ENABLED='false'
        @(Get-BillReportWorkers -Reports $reports -Accounting $accounting).Count | Should Be 5
    }
    It 'refuses incomplete source credentials' {
        $accounting.Remove('ACCOUNTING_REPORT_CREDENTIALS')
        { @(Get-BillReportWorkers -Reports $reports -Accounting $accounting) } | Should Throw
    }
    It 'refuses runs without fresh authority' {
        $reports.Remove('REPORTS_AUTHORITY_SOURCES')
        { @(Get-BillReportWorkers -Reports $reports -Accounting $accounting) } | Should Throw
    }
    It 'refuses exports without private storage' {
        $reports.Remove('REPORTS_ARTIFACT_ROOT')
        { @(Get-BillReportWorkers -Reports $reports -Accounting $accounting) } | Should Throw
    }
    It 'starts company setup only with signed automatic report discovery' {
        $identity = @{IDENTITY_COMPANY_SETUP_ORIGINS='configured'; IDENTITY_REPORT_ENROLLMENT_CREDENTIALS='configured'}
        $reports.REPORTS_AUTOMATIC_SOURCES_ENABLED='true'
        $reports.REPORTS_ENROLLMENT_SOURCE='configured'
        $accounting.ACCOUNTING_REPORT_ENROLLMENT_SOURCE='configured'
        $workers = @(Get-BillReportWorkers -Reports $reports -Accounting $accounting -Identity $identity)
        ($workers.Name -contains 'identity-company-setup') | Should Be $true
        $workers.Count | Should Be 7
    }
    It 'rejects setup when reporting is disabled instead of silently omitting its worker' {
        { @(Get-BillReportWorkers -Identity @{IDENTITY_COMPANY_SETUP_ORIGINS='configured'}) } | Should Throw
    }
}
