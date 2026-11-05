# Resolve each service's dependencies with uv.
# Unlike the single shared venv in some projects, this repo uses one uv
# environment per service project (apis/<name>/.venv), created by `uv sync`.
# The services are launched later with `uv run --project apis/<name> ...`.

function Invoke-BillSetupPython {
    param(
        [Parameter(Mandatory)]$Services,
        [switch]$Recreate
    )
    Write-BillStep 'Python environments (uv)'
    $failed = $false

    if (-not (Test-Command 'uv')) {
        Add-BillSummary 'uv' 'FAIL' 'uv not on PATH'
        throw "uv is not on PATH. Install it: https://docs.astral.sh/uv/ (winget install astral-sh.uv)"
    }
    Write-BillLog ("uv: {0}" -f ((& uv --version 2>&1 | Out-String).Trim())) 'OK'

    # The shared platform library is a workspace member; sync it first so the
    # service syncs resolve against a built copy.
    $platform = Join-Path $Global:BILL_REPO_ROOT 'libs\platform'
    if (Test-Path (Join-Path $platform 'pyproject.toml')) {
        Write-BillLog 'uv sync libs/platform' 'INFO'
        $ok = Invoke-BillCommand -FilePath 'uv' -Arguments @('sync') -WorkingDirectory $platform
        if ($ok) { Add-BillSummary 'uv:platform' 'OK' $platform }
        else     { Add-BillSummary 'uv:platform' 'FAIL' 'uv sync failed'; $failed = $true }
    }

    foreach ($svc in $Services) {
        $projectDir = Join-Path $Global:BILL_REPO_ROOT ([string]$svc.project)
        if (-not (Test-Path (Join-Path $projectDir 'pyproject.toml'))) {
            Write-BillLog "pyproject.toml missing for $($svc.code) ($projectDir)" 'WARN'
            Add-BillSummary "uv:$($svc.code)" 'FAIL' 'pyproject.toml missing'
            $failed = $true
            continue
        }

        if ($Recreate) {
            $venv = Join-Path $projectDir '.venv'
            Assert-BillChildPath -Path $venv -Root $Global:BILL_REPO_ROOT
            if (Test-Path $venv) {
                Write-BillLog "-Recreate: removing $venv" 'WARN'
                Remove-Item -Recurse -Force $venv
            }
        }

        Write-BillLog "uv sync $($svc.project)" 'INFO'
        $ok = Invoke-BillCommand -FilePath 'uv' -Arguments @('sync') -WorkingDirectory $projectDir
        if ($ok) {
            Write-BillLog "synced $($svc.code)" 'OK'
            Add-BillSummary "uv:$($svc.code)" 'OK' $projectDir
        } else {
            Add-BillSummary "uv:$($svc.code)" 'FAIL' 'uv sync failed'
            $failed = $true
        }
    }
    if ($failed) { throw 'One or more Python environments failed setup.' }
}
