function Invoke-BillDatabaseProvisioner {
    param([Parameter(Mandatory)][string]$ScriptPath)

    $powershell = Get-Command powershell.exe -ErrorAction Stop
    & $powershell.Source -NoProfile -ExecutionPolicy Bypass -File $ScriptPath |
        ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "Database provisioning failed (exit code $LASTEXITCODE)."
    }
}

function Invoke-BillOfferDatabaseProvisioning {
    param([Parameter(Mandatory)][string]$ProvisionScriptPath)

    $answer = Read-Host -Prompt 'Create the service databases and apply migrations now? [y/N]'
    if ($answer -notmatch '^(?i:y|yes)$') {
        Write-Host 'Database provisioning skipped. Run start\win\provision-databases.bat whenever you are ready.'
        return $false
    }

    Invoke-BillDatabaseProvisioner -ScriptPath $ProvisionScriptPath
    return $true
}
