param([Parameter(Mandatory)][string]$Name)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\_common.ps1')
. (Join-Path $PSScriptRoot 'lib\runtime.ps1')
[void](Get-BillRuntimePath $Name) # Validate before constructing log paths.
try {
    $child = Start-Process -FilePath $env:BILL_CHILD_EXECUTABLE -ArgumentList $env:BILL_CHILD_ARGUMENTS `
        -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Global:BILL_LOG_DIR "$Name.stdout.log") `
        -RedirectStandardError (Join-Path $Global:BILL_LOG_DIR "$Name.stderr.log")
    $child.WaitForExit()
    exit $child.ExitCode
} catch {
    Write-BillLog "$Name process launch failed. Check its executable and environment settings." 'ERROR'
    exit 1
}
