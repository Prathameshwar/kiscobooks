function Test-BillDeliverySetting {
    param([object]$Value)
    if ($null -eq $Value) { return $false }
    $text = ([string]$Value).Trim()
    return $text -and $text -notin @('null', '{}') -and $text -notmatch '^\[\s*\]$'
}

function Get-BillDeliveryWorkers {
    param(
        [System.Collections.IDictionary]$Vouchers = @{},
        [System.Collections.IDictionary]$Accounting = @{}
    )
    if (Test-BillDeliverySetting $Vouchers['VOUCHERS_SNAPSHOT_OWNERS']) { 'vouchers-sources' }
    if ((Test-BillDeliverySetting $Vouchers['VOUCHERS_EXECUTION_OWNER']) -or
        (Test-BillDeliverySetting $Vouchers['VOUCHERS_STOCK_EXECUTION_OWNER'])) { 'vouchers-executions' }
    if ((Test-BillDeliverySetting $Accounting['ACCOUNTING_IDENTITY_POSTING_URL']) -or
        (Test-BillDeliverySetting $Accounting['ACCOUNTING_STOCK_IDENTITY_URL'])) { 'accounting-posting-delivery' }
}
