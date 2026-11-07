function Find-BillVerifiedArchive {
    param(
        [Parameter(Mandatory)][string[]]$CandidatePaths,
        [Parameter(Mandatory)][string]$Sha256
    )

    foreach ($path in $CandidatePaths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $actualHash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($actualHash -eq $Sha256) {
            Write-Host "Using verified local archive: $path"
            return $path
        }
        Write-Warning "Ignoring cached archive with unexpected SHA-256: $path"
    }
    return $null
}

function Resolve-BillRabbitArchiveSourceRoot {
    param(
        [Parameter(Mandatory)][string]$StagingRoot,
        [Parameter(Mandatory)][AllowEmptyString()][string]$ArchiveRoot,
        [Parameter(Mandatory)][string]$RequiredFile,
        [Parameter(Mandatory)][string]$PackageName
    )

    $sourceRoot = if ($ArchiveRoot) {
        Join-Path $StagingRoot $ArchiveRoot
    } else {
        $StagingRoot
    }
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $RequiredFile) -PathType Leaf)) {
        throw "$PackageName archive is missing the expected $RequiredFile path."
    }
    return $sourceRoot
}
