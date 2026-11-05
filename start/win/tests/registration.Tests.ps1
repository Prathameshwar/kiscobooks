$registrationRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'registration'
Describe 'Manual account registration configuration' {
    It 'creates inactive external users without groups and never executes its review handoff login stage' {
        $blueprint = Get-Content -LiteralPath (Join-Path $registrationRoot 'authentik-enrollment.yaml') -Raw
        $blueprint | Should Match 'create_users_as_inactive: true'
        $blueprint | Should Match 'create_users_group: null'
        $blueprint | Should Match 'user_type: external'
        $blueprint | Should Match 'billing_email_verified.*False'
        $blueprint | Should Match 'bill-registration-review-permissions'
        $blueprint | Should Match 'return False'
        $blueprint | Should Match 'evaluate_on_plan: false'
    }
    It 'enforces the 6–128 provider length policy and forbids client attributes' {
        $blueprint = Get-Content -LiteralPath (Join-Path $registrationRoot 'authentik-enrollment.yaml') -Raw
        $blueprint | Should Match 'check_zxcvbn: false'
        $blueprint | Should Match 'length_min: 6'
        $blueprint | Should Match '6 <= len\(password\) <= 128'
        $blueprint | Should Match 'set\(data\) - allowed'
        $blueprint | Should Match 'execution_logging: false'
    }
    It 'applies the provider before writing the private environment' {
        $prepare = Get-Content -LiteralPath (Join-Path $registrationRoot 'prepare.ps1') -Raw
        $prepare.IndexOf("apply-authentik.ps1") | Should BeLessThan $prepare.IndexOf('Write-BillSetupPrivateFile')
        $prepare | Should Match 'AUTH_REGISTRATION_MODE='
        $prepare | Should Match 'Update-BillSetupEnvironment'
    }
    It 'requires a verified SSH host and reports native application errors' {
        $apply = Get-Content -LiteralPath (Join-Path $registrationRoot 'apply-authentik.ps1') -Raw
        $apply | Should Match 'StrictHostKeyChecking=yes'
        $apply | Should Match 'BatchMode=yes'
        $apply | Should Match 'LASTEXITCODE -ne 0'
        $apply | Should Not Match 'StrictHostKeyChecking=no'
        $apply | Should Match 'set -o pipefail'
    }
    It 'stores only explicit country/state profile defaults without changing verification' {
        $blueprint = Get-Content -LiteralPath (Join-Path $registrationRoot 'authentik-enrollment.yaml') -Raw
        $blueprint | Should Match 'field_key: country_code'
        $blueprint | Should Match 'field_key: state_code'
        $blueprint | Should Match 'billing_registration_region'
        $blueprint | Should Match 're.escape\(country\)'
        $mapping = Get-Content -LiteralPath (Join-Path $registrationRoot '..\platform-setup\authentik-email.yaml') -Raw
        $mapping | Should Match 'billing_registration_region'
        $mapping | Should Match 'billing_email_verified.*is True'
        $apply = Get-Content -LiteralPath (Join-Path $registrationRoot '..\platform-setup\apply-authentik.ps1') -Raw
        $apply | Should Match 'base64 --decode --ignore-garbage'
        $apply | Should Match 'set -o pipefail'
    }
}
