# A separate internal adapter keeps host-to-guest traffic independent of Wi-Fi/DHCP.
function Get-BillAuthentikLink {
    return @{SwitchName='Bill-HostLink'; AdapterName='BillHostLink';
        HostAddress='192.168.247.1'; GuestAddress='192.168.247.2'; Prefix='192.168.247.0/30'}
}

function Get-BillAuthentikAddress {
    param([object[]]$Adapters)
    $link = Get-BillAuthentikLink
    $fixed = @($Adapters | Where-Object { $_.Name -eq $link.AdapterName })
    if ($fixed.Count) {
        if ($fixed.Count -ne 1 -or $fixed[0].SwitchName -ne $link.SwitchName) { throw 'The Authentik host-link adapter has an unexpected switch.' }
        if ($fixed[0].IPAddresses -contains $link.GuestAddress) { return $link.GuestAddress }
        return $null # Do not replace a saved fixed address with DHCP during guest boot.
    }
    return $Adapters | ForEach-Object IPAddresses | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
}

function Test-BillIPv4Overlap {
    param([string]$First, [string]$Second)
    $ranges = foreach ($prefix in @($First, $Second)) {
        $parts = $prefix.Split('/')
        $ip = [Net.IPAddress]::Parse($parts[0])
        $bits = [int]$parts[1]
        if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or $bits -lt 0 -or $bits -gt 32) { throw 'Invalid IPv4 prefix.' }
        $bytes = $ip.GetAddressBytes()
        $number = [uint64]$bytes[0] * 16777216 + [uint64]$bytes[1] * 65536 + [uint64]$bytes[2] * 256 + $bytes[3]
        $size = [Math]::Pow(2, 32 - $bits)
        $start = [uint64]([Math]::Floor($number / $size) * $size)
        [pscustomobject]@{Start=$start; End=$start + [uint64]$size - 1}
    }
    return $ranges[0].Start -le $ranges[1].End -and $ranges[1].Start -le $ranges[0].End
}

function Get-BillAuthentikNetplan {
    param([Parameter(Mandatory)][string]$MacAddress)
    if ($MacAddress -notmatch '^[0-9a-fA-F]{12}$' -or $MacAddress -eq '000000000000') { throw 'Invalid host-link MAC address.' }
    $mac = ([regex]::Matches($MacAddress.ToLowerInvariant(), '..') | ForEach-Object Value) -join ':'
    $link = Get-BillAuthentikLink
    return @"
network:
  version: 2
  ethernets:
    billhost:
      match:
        macaddress: "$mac"
      set-name: billhost0
      dhcp4: false
      dhcp6: false
      accept-ra: false
      link-local: []
      addresses: [$($link.GuestAddress)/30]
      optional: true
"@
}

function Initialize-BillAuthentikHostLink {
    param([Parameter(Mandatory)]$VM)
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Host-link setup requires an administrator PowerShell session.' }
    $link = Get-BillAuthentikLink
    $alias = "vEthernet ($($link.SwitchName))"
    foreach ($route in @(Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop)) {
        if ($route.DestinationPrefix -eq '0.0.0.0/0' -or $route.InterfaceAlias -eq $alias) { continue }
        if (Test-BillIPv4Overlap $link.Prefix $route.DestinationPrefix) { throw "The host-link subnet overlaps $($route.DestinationPrefix) on $($route.InterfaceAlias); existing networks were preserved." }
    }
    $switch = Get-VMSwitch -Name $link.SwitchName -ErrorAction SilentlyContinue
    if ($switch -and $switch.SwitchType -ne 'Internal') { throw 'The named host-link switch exists with another type; it was preserved.' }
    if (-not $switch) { New-VMSwitch -Name $link.SwitchName -SwitchType Internal -ErrorAction Stop | Out-Null }
    $hostNic = Get-NetAdapter -Name $alias -ErrorAction Stop
    $addresses = @(Get-NetIPAddress -InterfaceIndex $hostNic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    if (@($addresses | Where-Object { $_.IPAddress -ne $link.HostAddress -and $_.IPAddress -notlike '169.254.*' }).Count) { throw 'The host-link interface has unexpected addresses; they were preserved.' }
    if (-not @($addresses | Where-Object IPAddress -eq $link.HostAddress).Count) {
        New-NetIPAddress -InterfaceIndex $hostNic.ifIndex -IPAddress $link.HostAddress -PrefixLength 30 -ErrorAction Stop | Out-Null
    } elseif (@($addresses | Where-Object { $_.IPAddress -eq $link.HostAddress -and $_.PrefixLength -ne 30 }).Count) { throw 'The existing host-link address has an unexpected prefix; it was preserved.' }
    $nic = Get-VMNetworkAdapter -VM $VM -Name $link.AdapterName -ErrorAction SilentlyContinue
    if ($nic -and $nic.SwitchName -ne $link.SwitchName) { throw 'The named VM adapter is attached to another switch; it was preserved.' }
    if (-not $nic) {
        Add-VMNetworkAdapter -VM $VM -Name $link.AdapterName -SwitchName $link.SwitchName -ErrorAction Stop
        $nic = Get-VMNetworkAdapter -VM $VM -Name $link.AdapterName -ErrorAction Stop
    }
    if ($nic.MacAddress -notmatch '^[0-9a-fA-F]{12}$' -or $nic.MacAddress -eq '000000000000') { throw 'The VM must be running to assign its host-link MAC address.' }
    if ($nic.DynamicMacAddressEnabled) {
        if ($nic.IPAddresses -contains $link.GuestAddress) { throw 'The host link is already in use with a dynamic MAC; shut down the VM before changing its MAC setting.' }
        # Hyper-V can hot-add a static adapter but cannot change that property live.
        # Reuse the unique MAC it allocated; replace only our as-yet-unused adapter.
        $mac = $nic.MacAddress
        Remove-VMNetworkAdapter -VMNetworkAdapter $nic -ErrorAction Stop
        Add-VMNetworkAdapter -VM $VM -Name $link.AdapterName -SwitchName $link.SwitchName -StaticMacAddress $mac -ErrorAction Stop
        $nic = Get-VMNetworkAdapter -VM $VM -Name $link.AdapterName -ErrorAction Stop
    }
    return $nic
}

function Set-BillAuthentikGuestHostLink {
    param([Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)][string]$MacAddress)
    $link = Get-BillAuthentikLink
    $yaml = Get-BillAuthentikNetplan $MacAddress
    $connectionPath = Join-Path $Directory 'connection.json'
    $connection = Get-Content -LiteralPath $connectionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($connection.vm_name -ne 'Bill-Authentik-Ubuntu' -or $connection.username -notmatch '^[a-z][a-z0-9_-]*$' -or
        $connection.ip_address -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'Unexpected VM connection details.' }
    $knownHosts = Join-Path $Directory 'known_hosts'
    $trusted = @(Get-Content -LiteralPath $knownHosts | Where-Object { ($_ -split '\s+')[0] -eq $connection.ip_address })
    if (-not $trusted.Count) { throw 'The current VM address has no pinned SSH host key; no trust settings were changed.' }
    foreach ($entry in $trusted) {
        $fields = $entry -split '\s+'
        if ($fields.Count -lt 3) { throw 'Invalid pinned SSH host key.' }
        $fixed = "$($link.GuestAddress) $($fields[1]) $($fields[2])"
        $existing = @(Get-Content -LiteralPath $knownHosts | Where-Object { ($_ -split '\s+')[0] -eq $link.GuestAddress -and ($_ -split '\s+')[1] -eq $fields[1] })
        if ($existing.Count -and @($existing | Where-Object { ((($_ -split '\s+')[0..2]) -join ' ') -ne $fixed }).Count) { throw 'The fixed address has a different pinned SSH host key; it was preserved.' }
        if (-not $existing.Count) { Add-Content -LiteralPath $knownHosts -Value $fixed -Encoding ASCII }
    }
    $ssh = @('-F','NUL','-i',(Join-Path $Directory 'id_ed25519'),'-o',"UserKnownHostsFile=$knownHosts",
        '-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ConnectTimeout=5',
        '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2')
    $target = "$($connection.username)@$($connection.ip_address)"
    $readProfile = 'if test -e /etc/netplan/99-bill-host-link.yaml; then sudo cat /etc/netplan/99-bill-host-link.yaml; fi'
    $old = & ssh.exe @ssh $target $readProfile
    if ($LASTEXITCODE -eq 255 -and $connection.ip_address -ne $link.GuestAddress) {
        # Resume after netplan changed the old DHCP lease during a previous attempt.
        $target = "$($connection.username)@$($link.GuestAddress)"
        $old = & ssh.exe @ssh $target $readProfile
    }
    if ($LASTEXITCODE -ne 0) { throw 'Cannot reach the VM through its currently trusted address.' }
    if ($old -and (($old -join "`n").Trim() -ne $yaml.Trim())) { throw 'An existing guest host-link profile differs; it was preserved.' }
    if (-not $old -or $target -ne "$($connection.username)@$($link.GuestAddress)") {
        $yaml | & ssh.exe @ssh $target 'sudo install -m 600 /dev/stdin /etc/netplan/99-bill-host-link.yaml && sudo netplan generate && sudo timeout 25s netplan apply'
        if ($LASTEXITCODE -notin @(0,255)) { throw 'Guest network configuration did not complete; the saved connection address was preserved.' }
    }
    # netplan can disconnect the bootstrap SSH session while renewing DHCP. Accept
    # that transition only after the pinned VM answers on the actual fixed address.
    $deadline = (Get-Date).AddSeconds(25)
    do {
        & ssh.exe @ssh "$($connection.username)@$($link.GuestAddress)" "sudo netplan generate && ip -4 -o address show dev billhost0 | grep -F ' $($link.GuestAddress)/30 '"
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    if ($LASTEXITCODE -ne 0) { throw 'The fixed VM address did not pass pinned-key SSH verification; the saved connection was preserved.' }
    $connection.ip_address = $link.GuestAddress
    $connection | ConvertTo-Json | Set-Content -LiteralPath $connectionPath -Encoding UTF8
}
