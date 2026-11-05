param([ValidateSet('start','status','stop','test')][string]$Action = 'status')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$runtime = Join-Path $root '.tools/azurite-runtime'
$entry = Join-Path $root '.tools/azurite/node_modules/azurite/dist/src/blob/main.js'
$credentialFile = Join-Path $runtime 'credentials.json'
$processFile = Join-Path $runtime 'process.json'
if (!(Test-Path -LiteralPath $entry)) { throw 'Install pinned Azurite first: npm.cmd install --prefix .tools/azurite --no-audit --no-fund azurite@3.37.0' }
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
if (!(Test-Path -LiteralPath $credentialFile)) {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($bytes)
    $generator.Dispose()
    @{ account = 'billlocal'; key = [Convert]::ToBase64String($bytes) } | ConvertTo-Json | Set-Content -LiteralPath $credentialFile -Encoding ASCII
}
$credential = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json
$env:AZURITE_ACCOUNTS = $credential.account + ':' + $credential.key
$env:IDENTITY_TEST_AZURITE_URL = 'http://127.0.0.1:10000/' + $credential.account
$env:IDENTITY_TEST_AZURITE_KEY = $credential.key
if ($Action -eq 'start') {
    if (Get-NetTCPConnection -LocalPort 10000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 10000 is in use; existing process left untouched.' }
    $inheritedPath = $env:Path
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
    Remove-Item Env:Path -ErrorAction SilentlyContinue
    $env:Path = $inheritedPath
    $node = (Get-Command node.exe).Source
    $process = Start-Process -FilePath $node -ArgumentList @($entry, '--blobHost', '127.0.0.1', '--blobPort', '10000', '--location', $runtime, '--silent') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'stdout.log') -RedirectStandardError (Join-Path $runtime 'stderr.log')
    @{ pid = $process.Id; started = $process.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $processFile -Encoding ASCII
    Write-Output 'Azurite blob service launched on loopback port 10000.'
} elseif ($Action -eq 'stop') {
    if (Test-Path -LiteralPath $processFile) {
        $saved = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
        $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
        if ($process -and $process.ProcessName -eq 'node' -and $process.StartTime.ToUniversalTime().ToString('o') -eq $saved.started) {
            Stop-Process -Id $process.Id
        }
    }
} elseif ($Action -eq 'test') {
    Push-Location (Join-Path $root 'apis/identity')
    try { & '.venv/Scripts/python.exe' -m pytest tests/test_live_azure_blob.py -q --tb=short }
    finally { Pop-Location }
    exit $LASTEXITCODE
} else {
    $listener = Get-NetTCPConnection -LocalPort 10000 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { Write-Output 'A local blob listener is available on 127.0.0.1:10000.' }
    else { Write-Output 'No blob listener on port 10000.' }
}
