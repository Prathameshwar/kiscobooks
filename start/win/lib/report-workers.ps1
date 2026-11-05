function Get-BillReportWorkers {
    param([hashtable]$Reports = @{}, [hashtable]$Accounting = @{}, [hashtable]$Identity = @{})
    $source = $Reports['REPORTS_SOURCE_VERSIONS_ENABLED'] -eq 'true'
    $runs = $Reports['REPORTS_FRAMEWORK_ENABLED'] -eq 'true'
    $exports = $Reports['REPORTS_EXPORTS_ENABLED'] -eq 'true'
    if (!$source -and !$runs -and !$exports -and !$Identity['IDENTITY_COMPANY_SETUP_ORIGINS']) { return }
    if ($Identity['IDENTITY_COMPANY_SETUP_ORIGINS']) {
        if ($Reports['REPORTS_AUTOMATIC_SOURCES_ENABLED'] -ne 'true' -or !$Reports['REPORTS_ENROLLMENT_SOURCE'] -or
            !$Accounting['ACCOUNTING_REPORT_ENROLLMENT_SOURCE'] -or !$Identity['IDENTITY_REPORT_ENROLLMENT_CREDENTIALS']) {
            throw 'Automatic company setup requires signed report enrollment and automatic source reconciliation.'
        }
        @{Name='identity-company-setup'; Project='identity'; Module='identity.tasks.company_setup'; Environment='identity'; Arguments=@()}
    }
    if (!$source -or !$Reports['REPORTS_OWNERS'] -or
        $Accounting['ACCOUNTING_REPORT_SNAPSHOT_ENABLED'] -ne 'true' -or
        !$Accounting['ACCOUNTING_REPORT_CREDENTIALS']) {
        throw 'Reports require configured versioned sources and Accounting snapshot credentials.'
    }
    @{Name='accounting-report-snapshots'; Project='accounting'; Module='accounting.tasks.reporting_snapshot'; Environment='accounting'; Arguments=@()}
    @{Name='reports-sources'; Project='reports'; Module='reports.tasks.source_worker'; Environment='reports'; Arguments=@()}
    if ($runs) {
        if (!$Reports['REPORTS_JOB_BROKER_URL'] -or !$Reports['REPORTS_AUTHORITY_SOURCES']) {
            throw 'Report runs require a broker and fresh scoped Identity authority.'
        }
        @{Name='reports-dispatcher'; Project='reports'; Module='reports.tasks.job_dispatcher'; Environment='reports'; Arguments=@()}
        foreach ($lane in @('short','bulk')) {
            @{Name=('reports-' + $lane); Project='reports'; Module='reports.tasks.job_dispatcher'; Environment='reports'; Arguments=@('--worker',$lane,'--pool','solo','--concurrency','1')}
        }
    }
    if ($exports) {
        if (!$runs -or !$Reports['REPORTS_ARTIFACT_ROOT']) {
            throw 'Report exports require run admission and private artifact storage.'
        }
        @{Name='reports-render'; Project='reports'; Module='reports.tasks.job_dispatcher'; Environment='reports'; Arguments=@('--worker','render','--pool','solo','--concurrency','1')}
    }
}
