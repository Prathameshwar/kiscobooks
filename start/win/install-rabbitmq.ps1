$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'lib\rabbitmq-installer.ps1')

$workspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$tools = Join-Path $workspace '.tools'
$archiveCache = Join-Path $tools 'downloads'
$erlangRoot = Join-Path $tools 'erlang'
$erlangExe = Join-Path $erlangRoot 'bin\erl.exe'
$rabbitRoot = Join-Path $tools 'rabbitmq\rabbitmq_server-4.3.5'
$rabbitServer = Join-Path $rabbitRoot 'sbin\rabbitmq-server.bat'
$downloads = @(
    @{
        Name = 'Erlang/OTP 27.3.4.17'
        FileName = 'otp_win64_27.3.4.17.zip'
        Url = 'https://github.com/erlang/otp/releases/download/OTP-27.3.4.17/otp_win64_27.3.4.17.zip'
        Sha256 = 'D0C9F030909EED5484A803F8A9E9E3A2D2275D3E531A4E0891CB61FD1F88697F'
        Destination = $erlangRoot
        RequiredFile = 'bin\erl.exe'
        ArchiveRoot = ''
    },
    @{
        Name = 'RabbitMQ 4.3.5'
        FileName = 'rabbitmq-server-windows-4.3.5.zip'
        Url = 'https://github.com/rabbitmq/rabbitmq-server/releases/download/v4.3.5/rabbitmq-server-windows-4.3.5.zip'
        Sha256 = '462E626E276F1D670C0C45E96B36298E20C13D3EFDD0F3F35E879E9868B4C9AB'
        Destination = $rabbitRoot
        RequiredFile = 'sbin\rabbitmq-server.bat'
        ArchiveRoot = 'rabbitmq_server-4.3.5'
    }
)

if ((Test-Path -LiteralPath $erlangExe) -and (Test-Path -LiteralPath $rabbitServer)) {
    Write-Output 'RabbitMQ and Erlang installation paths already exist; nothing to do.'
    exit 0
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$progressPreference = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
$work = Join-Path $env:TEMP ("rabbitmq-install-{0}" -f [guid]::NewGuid())
New-Item -ItemType Directory -Path $work -Force | Out-Null

try {
    New-Item -ItemType Directory -Path $archiveCache -Force | Out-Null
    foreach ($package in $downloads) {
        $requiredPath = Join-Path $package.Destination $package.RequiredFile
        if (Test-Path -LiteralPath $requiredPath) {
            Write-Output "$($package.Name) already installed."
            continue
        }

        $cachePath = Join-Path $archiveCache $package.FileName
        $candidatePaths = @(
            $cachePath,
            (Join-Path (Join-Path $env:USERPROFILE 'Downloads') $package.FileName),
            (Join-Path $env:TEMP $package.FileName)
        )
        $archive = Find-BillVerifiedArchive -CandidatePaths $candidatePaths -Sha256 $package.Sha256
        if (-not $archive) {
            $partialArchive = Join-Path $archiveCache ($package.FileName + '.' + [guid]::NewGuid() + '.download')
            Write-Output "Downloading $($package.Name)..."
            try {
                Invoke-WebRequest -Uri $package.Url -OutFile $partialArchive -UseBasicParsing -TimeoutSec 300 -MaximumRedirection 5
            } catch {
                Remove-Item -LiteralPath $partialArchive -Force -ErrorAction SilentlyContinue
                throw "$($package.Name) download failed: $_"
            }

            $actualHash = (Get-FileHash -LiteralPath $partialArchive -Algorithm SHA256).Hash.ToUpperInvariant()
            if ($actualHash -ne $package.Sha256) {
                Remove-Item -LiteralPath $partialArchive -Force
                throw "$($package.Name) archive SHA-256 mismatch (expected $($package.Sha256), got $actualHash)."
            }
            Move-Item -LiteralPath $partialArchive -Destination $cachePath -Force
            $archive = $cachePath
            Write-Output "$($package.Name) archive SHA-256 verified and cached."
        } else {
            Write-Output "$($package.Name) archive SHA-256 verified."
        }

        $staging = Join-Path $work ($package.Name.Replace('/', '-') + '-extract')
        Expand-Archive -LiteralPath $archive -DestinationPath $staging
        $sourceRoot = Resolve-BillRabbitArchiveSourceRoot `
            -StagingRoot $staging `
            -ArchiveRoot $package.ArchiveRoot `
            -RequiredFile $package.RequiredFile `
            -PackageName $package.Name

        New-Item -ItemType Directory -Path $package.Destination -Force | Out-Null
        Get-ChildItem -LiteralPath $sourceRoot -Force | Copy-Item -Destination $package.Destination -Recurse -Force
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "$($package.Name) installation is incomplete; expected $requiredPath."
        }
        Write-Output "$($package.Name) installed."
    }
} finally {
    if (Test-Path -LiteralPath $work) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
    $ProgressPreference = $progressPreference
}

Write-Output 'RabbitMQ and Erlang are ready. Start the local broker with start\win\start-all.bat.'
