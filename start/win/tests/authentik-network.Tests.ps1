$networkHelper = Join-Path $PSScriptRoot '..\lib\authentik-network.ps1'
if (Test-Path -LiteralPath $networkHelper) { . $networkHelper }

Describe 'Stable Authentik host link' {
    It 'prefers the fixed host link over a changing Default Switch address' {
        $adapters = @(
            [pscustomobject]@{Name='Network Adapter'; SwitchName='Default Switch'; IPAddresses=@('172.23.133.84')},
            [pscustomobject]@{Name='BillHostLink'; SwitchName='Bill-HostLink'; IPAddresses=@('192.168.247.2')}
        )
        Get-BillAuthentikAddress -Adapters $adapters | Should Be '192.168.247.2'
    }
    It 'preserves the last saved address while the fixed adapter starts' {
        $adapters = @(
            [pscustomobject]@{Name='Network Adapter'; SwitchName='Default Switch'; IPAddresses=@('172.23.133.84')},
            [pscustomobject]@{Name='BillHostLink'; SwitchName='Bill-HostLink'; IPAddresses=@()}
        )
        Get-BillAuthentikAddress -Adapters $adapters | Should Be $null
    }
    It 'supports an existing VM before the fixed link is installed' {
        $adapter = [pscustomobject]@{Name='Network Adapter'; SwitchName='Default Switch'; IPAddresses=@('fe80::1','172.23.133.84')}
        Get-BillAuthentikAddress -Adapters @($adapter) | Should Be '172.23.133.84'
    }
    It 'detects subnet conflicts including a broader VPN route' {
        Test-BillIPv4Overlap '192.168.247.0/30' '192.168.0.0/16' | Should Be $true
        Test-BillIPv4Overlap '192.168.247.0/30' '192.168.247.2/32' | Should Be $true
        Test-BillIPv4Overlap '192.168.247.0/30' '192.168.247.4/30' | Should Be $false
        Test-BillIPv4Overlap '192.168.247.0/30' '172.23.128.0/20' | Should Be $false
    }
    It 'makes only the dedicated MAC static without adding a gateway or DNS server' {
        $yaml = Get-BillAuthentikNetplan -MacAddress '00155D012501'
        $yaml | Should Match 'macaddress: "00:15:5d:01:25:01"'
        $yaml | Should Match '192.168.247.2/30'
        $yaml | Should Match 'dhcp4: false'
        $yaml | Should Match 'set-name: billhost0'
        $yaml | Should Not Match 'gateway|nameservers|routes:'
    }
    It 'rejects invalid MAC addresses before constructing guest configuration' {
        { Get-BillAuthentikNetplan -MacAddress 'invalid;command' } | Should Throw
    }
    It 'preserves a conflicting pinned SSH key and the existing connection' {
        $directory = Join-Path $TestDrive 'trust-conflict'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $connection = Join-Path $directory 'connection.json'
        @{vm_name='Bill-Authentik-Ubuntu'; username='billvm'; ip_address='172.23.133.84'} |
            ConvertTo-Json | Set-Content -LiteralPath $connection -Encoding UTF8
        $hosts = Join-Path $directory 'known_hosts'
        Set-Content -LiteralPath $hosts -Value @(
            '172.23.133.84 ssh-ed25519 old-public-key',
            '192.168.247.2 ssh-ed25519 different-public-key'
        )
        $before = Get-Content -LiteralPath $hosts -Raw
        { Set-BillAuthentikGuestHostLink -Directory $directory -MacAddress '00155D012501' } | Should Throw
        Get-Content -LiteralPath $hosts -Raw | Should Be $before
        (Get-Content -LiteralPath $connection -Raw | ConvertFrom-Json).ip_address | Should Be '172.23.133.84'
    }
    It 'refuses guest setup without a previously trusted VM key' {
        $directory = Join-Path $TestDrive 'missing-trust'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        @{vm_name='Bill-Authentik-Ubuntu'; username='billvm'; ip_address='172.23.133.84'} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'connection.json') -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $directory 'known_hosts') -Value ''
        { Set-BillAuthentikGuestHostLink -Directory $directory -MacAddress '00155D012501' } | Should Throw
        Test-Path -LiteralPath (Join-Path $directory 'id_ed25519') | Should Be $false
    }
    It 'accepts a DHCP-session disconnect only after verifying the pinned fixed link' {
        $directory = Join-Path $TestDrive 'ssh-transition'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $connection = Join-Path $directory 'connection.json'
        @{vm_name='Bill-Authentik-Ubuntu'; username='billvm'; ip_address='172.23.133.84'} |
            ConvertTo-Json | Set-Content -LiteralPath $connection -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $directory 'known_hosts') -Value '172.23.133.84 ssh-ed25519 trusted-public-key'
        $script:sshCalls = 0
        Mock ssh.exe {
            $script:sshCalls++
            $global:LASTEXITCODE = if ($script:sshCalls -eq 2) { 255 } else { 0 }
        }
        Set-BillAuthentikGuestHostLink -Directory $directory -MacAddress '00155D012501'
        Assert-MockCalled ssh.exe -Times 3 -Exactly -Scope It
        (Get-Content -LiteralPath $connection -Raw | ConvertFrom-Json).ip_address | Should Be '192.168.247.2'
    }
    It 'does not reapply a matching guest profile through an already-working fixed link' {
        $directory = Join-Path $TestDrive 'unchanged-profile'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        @{vm_name='Bill-Authentik-Ubuntu'; username='billvm'; ip_address='192.168.247.2'} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'connection.json') -Encoding UTF8
        Set-Content -LiteralPath (Join-Path $directory 'known_hosts') -Value '192.168.247.2 ssh-ed25519 trusted-public-key'
        $script:existingProfile = Get-BillAuthentikNetplan '00155D012501'
        $script:sshCalls = 0
        Mock ssh.exe {
            $script:sshCalls++
            $global:LASTEXITCODE = 0
            if ($script:sshCalls -eq 1) { return $script:existingProfile }
        }
        Set-BillAuthentikGuestHostLink -Directory $directory -MacAddress '00155D012501'
        Assert-MockCalled ssh.exe -Times 2 -Exactly -Scope It
    }
}
