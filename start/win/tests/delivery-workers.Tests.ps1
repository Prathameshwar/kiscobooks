$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib/delivery-workers.ps1')
Describe 'Required delivery worker selection' {
    It 'does not launch unconfigured connections' {
        @(Get-BillDeliveryWorkers -Vouchers @{} -Accounting @{}).Count | Should Be 0
        @(Get-BillDeliveryWorkers -Vouchers @{
            VOUCHERS_SNAPSHOT_OWNERS='[ ]'; VOUCHERS_EXECUTION_OWNER='{}'; VOUCHERS_STOCK_EXECUTION_OWNER=''
        } -Accounting @{}).Count | Should Be 0
    }
    It 'recovers stock execution and confirmation independently of admission flags' {
        $workers = @(Get-BillDeliveryWorkers -Vouchers @{
            VOUCHERS_STOCK_EXECUTION_OWNER='{"origin":"http://127.0.0.1:8011"}'
            VOUCHERS_STOCK_EXECUTION_ENABLED='false'
        } -Accounting @{
            ACCOUNTING_STOCK_IDENTITY_URL='http://127.0.0.1:8001'
            ACCOUNTING_VOUCHER_STOCK_ENABLED='false'
        })
        ($workers -join ',') | Should Be 'vouchers-executions,accounting-posting-delivery'
    }
    It 'starts sources before execution and supports existing financial connections' {
        $workers = @(Get-BillDeliveryWorkers -Vouchers @{
            VOUCHERS_SNAPSHOT_OWNERS='[{"owner":"identity"}]'
            VOUCHERS_EXECUTION_OWNER='{"owner":"accounting"}'
        } -Accounting @{ACCOUNTING_IDENTITY_POSTING_URL='https://identity.example'})
        ($workers -join ',') | Should Be 'vouchers-sources,vouchers-executions,accounting-posting-delivery'
    }
}
