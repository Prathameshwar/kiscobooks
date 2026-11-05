[CmdletBinding()]
param([ValidateSet('create', 'start', 'stop', 'status', 'configure-network')][string]$Action = 'status')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib\authentik-network.ps1')
$name = 'Bill-Authentik-Ubuntu'
$directory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\.tools\authentik-vm'))
$resultFile = Join-Path $directory 'vm-result.json'
try {
    if (-not (Get-Module -ListAvailable Hyper-V)) {
        if ($Action -ne 'create') { throw 'Hyper-V PowerShell management tools are missing. Run create as administrator first.' }
        $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
        if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'VM creation needs an elevated PowerShell session.'
        }
        $feature = Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-Management-PowerShell -All -NoRestart
        if ($feature.RestartNeeded) { throw 'Hyper-V management tools were enabled. Restart Windows, then rerun this command.' }
    }
    Import-Module Hyper-V -ErrorAction Stop
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Hyper-V management requires an administrator PowerShell session.' }
    $vm = Get-VM -Name $name -ErrorAction SilentlyContinue
    switch ($Action) {
        'configure-network' {
            if (-not $vm) { throw 'The Authentik VM has not been created.' }
            $nic = Initialize-BillAuthentikHostLink -VM $vm
            @{link=(Get-BillAuthentikLink); mac_address=$nic.MacAddress; netplan=(Get-BillAuthentikNetplan $nic.MacAddress)} |
                ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $directory 'host-link.json') -Encoding UTF8
            Set-BillAuthentikGuestHostLink -Directory (Join-Path $PSScriptRoot 'authentik-vm') -MacAddress $nic.MacAddress
        }
        'create' {
            if ($vm) { throw 'The named VM already exists; it was preserved. Use start or status.' }
            $source = Join-Path $directory 'ubuntu.vhd'
            $seed = Join-Path $directory 'seed.iso'
            if (Test-Path -LiteralPath (Join-Path $directory 'seed-corrected.iso')) { $seed = Join-Path $directory 'seed-corrected.iso' }
            if (Test-Path -LiteralPath (Join-Path $directory 'seed-setup-updated.iso')) { $seed = Join-Path $directory 'seed-setup-updated.iso' }
            if (-not (Test-Path -LiteralPath $source) -or -not (Test-Path -LiteralPath $seed)) {
                throw 'Prepared Ubuntu disk or cloud-init ISO is missing. See docs/local-login-setup.md.'
            }
            $switch = Get-VMSwitch -Name 'Default Switch' -ErrorAction Stop
            $disk = Join-Path $directory 'ubuntu.vhdx'
            if (Test-Path -LiteralPath $disk) { throw 'A target VM disk already exists; it was preserved.' }
            Convert-VHD -Path $source -DestinationPath $disk -VHDType Dynamic
            Resize-VHD -Path $disk -SizeBytes 32GB
            $vm = New-VM -Name $name -Generation 2 -MemoryStartupBytes 4GB -VHDPath $disk -Path $directory -SwitchName $switch.Name
            Set-VMMemory -VM $vm -DynamicMemoryEnabled $false
            Set-VMProcessor -VM $vm -Count 2
            Set-VMFirmware -VM $vm -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority
            Set-VM -VM $vm -AutomaticStartAction Nothing -AutomaticStopAction ShutDown -AutomaticCheckpointsEnabled $false
            Add-VMDvdDrive -VM $vm -Path $seed
            Start-VM -VM $vm
            Write-Host 'Created and started Bill-Authentik-Ubuntu: 4 GB RAM, 2 CPUs, 32 GB disk. Cloud-init installs Authentik inside Ubuntu.'
        }
        'start' { if (-not $vm) { throw 'The Authentik VM has not been created.' }; Start-VM -VM $vm }
        'stop' { if (-not $vm) { throw 'The Authentik VM has not been created.' }; Stop-VM -VM $vm }
        'status' {
            if (-not $vm) { throw 'The Authentik VM has not been created.' }
            $vm | Select-Object Name, State, MemoryAssigned, ProcessorCount | Format-Table | Out-Host
            Get-VMNetworkAdapter -VM $vm | Select-Object Name, IPAddresses | Format-List | Out-Host
        }
    }
    $vm = Get-VM -Name $name
    $address = Get-BillAuthentikAddress -Adapters @(Get-VMNetworkAdapter -VM $vm)
    if ($address) {
        $connectionFile = Join-Path $PSScriptRoot 'authentik-vm\connection.json'
        $connection = @{vm_name=$name; username='billvm'; ip_address=$address; ssh_port=22; state=[string]$vm.State}
        $connection | ConvertTo-Json | Set-Content -LiteralPath $connectionFile -Encoding UTF8
    }
    @{ok=$true; action=$Action; vm=$name} | ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding UTF8
    exit 0
} catch {
    $message = $_.Exception.Message
    if (Test-Path -LiteralPath $directory) {
        @{ok=$false; action=$Action; vm=$name; error=$message} | ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding UTF8
    }
    Write-Host $message -ForegroundColor Red
    exit 1
}
