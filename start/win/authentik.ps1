[CmdletBinding()]
param([ValidateSet('start', 'stop', 'status')][string]$Action = 'status')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$directory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\.tools\authentik'))
$compose = Join-Path $directory 'compose.yml'
try {
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (-not $docker) { throw 'Install Docker Desktop with WSL 2, then start Docker Desktop. See docs/local-login-setup.md.' }
    if (-not (Test-Path -LiteralPath $compose) -or -not (Test-Path -LiteralPath (Join-Path $directory '.env'))) {
        throw 'Local Authentik configuration is missing. See docs/local-login-setup.md.'
    }
    & $docker.Source info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Docker is unavailable. Start Docker Desktop in Linux container mode.' }
    $arguments = @('compose', '--project-name', 'bill-authentik', '--project-directory', $directory, '--file', $compose)
    switch ($Action) {
        'start' {
            & $docker.Source @arguments up --detach --wait --wait-timeout 180
            if ($LASTEXITCODE -ne 0) { throw 'Authentik startup failed. Inspect the bill-authentik container logs.' }
            Write-Host 'Authentik containers started. Open https://localhost:9443; finish provider/TLS setup in docs/local-login-setup.md.'
        }
        'stop' {
            & $docker.Source @arguments stop --timeout 30
            if ($LASTEXITCODE -ne 0) { throw 'Authentik stop failed.' }
            Write-Host 'Authentik containers stopped. Database, configuration and uploaded files were preserved.'
        }
        'status' {
            & $docker.Source @arguments ps --all
            if ($LASTEXITCODE -ne 0) { throw 'Authentik container status failed.' }
            Write-Host 'Container status does not certify provider configuration or browser login.'
        }
    }
    exit 0
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
