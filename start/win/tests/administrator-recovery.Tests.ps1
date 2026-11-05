$recoveryRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'registration'
Describe 'Administrator recovery deployment' {
    It 'keeps recovery provider-owned and preserves MFA without creating accounts' {
        $blueprint = Get-Content -LiteralPath (Join-Path $recoveryRoot 'authentik-administrator-recovery.yaml') -Raw
        $blueprint | Should Match 'designation: recovery'
        $blueprint | Should Match 'PLAN_CONTEXT_PENDING_USER'
        $blueprint | Should Match 'authentik_stages_authenticator_validate'
        $blueprint | Should Match 'user_creation_mode: never_create'
        $blueprint | Should Match 'set\(data\) -'
        $blueprint | Should Not Match 'authentik_stages_user_login'
    }
    It 'withholds email configuration when SMTP is absent and captures credentials privately' {
        $script = Get-Content -LiteralPath (Join-Path $recoveryRoot 'prepare-administrator-recovery.ps1') -Raw
        $script | Should Match 'Write-BillSetupPrivateFile'
        $script | Should Match "stage -ne 'disabled'"
        $script | Should Match 'IDENTITY_AUTHENTIK_RECOVERY_EMAIL_STAGE'
        $script | Should Not Match 'Write-Output.*RECOVERY_TOKEN'
        $provider = Get-Content -LiteralPath (Join-Path $recoveryRoot 'prepare-administrator-recovery.py') -Raw
        $provider | Should Match 'get_perms\(service\)'
        $provider | Should Match 'get_perms\(role\)'
        $provider | Should Match 'reset_user_password.*user'
        $provider | Should Not Match 'change_user'
    }
    It 'uses the actual blueprint exit status despite startup stderr diagnostics' {
        $script = Get-Content -LiteralPath (Join-Path $recoveryRoot 'apply-authentik.ps1') -Raw
        $script | Should Match 'StrictHostKeyChecking=yes'
        $script | Should Match 'applyExit = \$LASTEXITCODE'
        $script | Should Match 'applyExit -ne 0'
    }
}
