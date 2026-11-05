# Opt-in live regression: requires installed mfes dependencies and free UI ports.
$ErrorActionPreference = 'Stop'
$winRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $winRoot 'lib\_common.ps1')
. (Join-Path $winRoot 'lib\runtime.ps1')
. (Join-Path $winRoot 'lib\web.ps1')
$targets = @(Get-BillWebApps)
foreach ($target in $targets) {
    if ((Get-BillManagedProcess $target.Name) -or (Wait-ForPort -HostName '127.0.0.1' -Port $target.Port -TimeoutSeconds 1)) {
        throw "Live tests require $($target.Name) to be stopped first."
    }
}
function Invoke-WebBat {
    param([string]$Name, [string[]]$Arguments = @(), [int]$Expected = 0)
    & (Join-Path $winRoot "$Name.bat") @Arguments
    if ($LASTEXITCODE -ne $Expected) { throw "$Name returned $LASTEXITCODE; expected $Expected." }
}
$external = $null
$originalNodeOptions = $env:NODE_OPTIONS
$originalNoPause = $env:BILL_NO_PAUSE
$testDirectory = Join-Path ([IO.Path]::GetTempPath()) ('bill ui lifecycle ' + [guid]::NewGuid().ToString('N'))
New-Item -Path $testDirectory -ItemType Directory | Out-Null
Push-Location $testDirectory
try {
    $env:BILL_NO_PAUSE = '1'
    Invoke-WebBat start-web
    $before = @($targets | ForEach-Object { (Get-BillManagedProcess $_.Name).Id })
    Invoke-WebBat start-web
    $after = @($targets | ForEach-Object { (Get-BillManagedProcess $_.Name).Id })
    if (($before -join ',') -ne ($after -join ',')) { throw 'Repeated start created new processes.' }
    Invoke-WebBat status-web
    Invoke-WebBat stop-web -Arguments @('auth')
    if (-not (Get-BillManagedProcess web-console)) { throw 'Stopping auth also stopped console.' }
    Invoke-WebBat status-web -Arguments @('console')
    Invoke-WebBat start-web -Arguments @('auth')
    Invoke-WebBat stop-web
    Invoke-WebBat stop-web
    Invoke-WebBat status-web -Expected 1

    # A real child startup failure must be detected and rolled back, including stale state.
    $failurePreload = Join-Path $testDirectory 'fail-next.cjs'
    Set-Content -LiteralPath $failurePreload -Encoding ASCII -Value 'if ((process.argv[1] || "").endsWith("next")) throw new Error("intentional startup failure");'
    $env:NODE_OPTIONS = '--require="' + $failurePreload + '"'
    try { Invoke-WebBat start-web -Arguments @('auth') -Expected 1 }
    finally { $env:NODE_OPTIONS = $originalNodeOptions }
    if (Get-BillManagedProcess web-auth) { throw 'Failed launch left a managed host running.' }
    if (Test-Path -LiteralPath (Get-BillRuntimePath web-auth)) { throw 'Failed launch left stale process state.' }

    # Occupy auth's port with a separately created process; start/stop must preserve it.
    $node = Get-BillWebNode
    $source = 'require("node:http").createServer((q,s)=>s.end("external")).listen(4310,"127.0.0.1");'
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $node
    $psi.Arguments = '-e ' + (ConvertTo-BillArgument $source)
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $external = [Diagnostics.Process]::Start($psi)
    if (-not (Wait-ForPort -HostName '127.0.0.1' -Port 4310 -TimeoutSeconds 10)) { throw 'External test listener failed to start.' }
    Invoke-WebBat start-web -Expected 1
    Invoke-WebBat stop-web -Arguments @('auth') -Expected 1
    Invoke-WebBat status-web -Arguments @('auth') -Expected 1
    if ($external.HasExited) { throw 'Launcher killed the external listener.' }
    if (Get-BillManagedProcess web-console) { throw 'Port conflict partially launched console.' }
    Write-BillLog 'Live UI lifecycle regressions passed.' 'OK'
} finally {
    $env:BILL_NO_PAUSE = $originalNoPause
    $env:NODE_OPTIONS = $originalNodeOptions
    if ($external -and -not $external.HasExited) { $external.Kill(); $external.WaitForExit() }
    foreach ($target in $targets) {
        if (Get-BillManagedProcess $target.Name) { Stop-BillWebApp $target }
    }
    Pop-Location
    if (Test-Path -LiteralPath (Join-Path $testDirectory 'fail-next.cjs')) {
        Remove-Item -LiteralPath (Join-Path $testDirectory 'fail-next.cjs')
    }
    # Only this test-created empty directory; no recursive deletion of computed targets.
    Remove-Item -LiteralPath $testDirectory
}
