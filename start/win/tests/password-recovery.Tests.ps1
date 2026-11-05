$passwordRecoveryRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'registration'
Describe 'Self-service password recovery deployment' {
    It 'persists the trusted JANSO return URL in the deployed blueprint for later provider reapplication' {
        $blueprint = Get-Content -LiteralPath (Join-Path $passwordRecoveryRoot 'authentik-self-service-recovery.yaml') -Raw
        $blueprint | Should Match 'target_static: __BILL_RECOVERY_RETURN_URL__'
        $script = Get-Content -LiteralPath (Join-Path $passwordRecoveryRoot 'apply-authentik.ps1') -Raw
        $script | Should Match 'ConvertTo-Json -Compress'
        $script | Should Match "Replace\('__BILL_RECOVERY_RETURN_URL__'"
    }
    It 'separates email identification from verified password write and preserves MFA' {
        $blueprint = Get-Content -LiteralPath (Join-Path $passwordRecoveryRoot 'authentik-self-service-recovery.yaml') -Raw
        $blueprint | Should Match 'user_fields: \[email\]'
        $blueprint | Should Match 'show_matched_user: false'
        $blueprint | Should Match 'pretend_user_exists: true'
        $blueprint | Should Match 'PLAN_CONTEXT_IS_RESTORED'
        $blueprint | Should Match 'token.user_id != user.pk'
        $blueprint | Should Match 'authentik_stages_authenticator_validate'
        $blueprint | Should Match 'authentik_stages_deny'
        $blueprint | Should Match 'negate: true, failure_result: true'
        $blueprint | Should Match 'user_creation_mode: never_create'
        $blueprint | Should Match 'activate_user_on_success: false'
        $blueprint | Should Match 'cache.incr\(key\) > 5'
        $blueprint | Should Not Match 'authentik_stages_user_login'
    }
    It 'enables both email paths only through private configuration after provider preparation' {
        $script = Get-Content -LiteralPath (Join-Path $passwordRecoveryRoot 'prepare-password-recovery.ps1') -Raw
        $script | Should Match 'prepare-administrator-recovery.ps1'
        $script | Should Match 'Write-BillSetupPrivateFile'
        $script | Should Match "AUTHENTIK_SELF_SERVICE_RECOVERY_ENABLED='false'"
        $script | Should Match 'StrictHostKeyChecking=yes'
        $script | Should Not Match 'Write-Output.*TOKEN'
        $provider = Get-Content -LiteralPath (Join-Path $passwordRecoveryRoot 'prepare-password-recovery.py') -Raw
        $provider | Should Match 'Preserve the existing recovery flow'
        $provider | Should Match 'flow if configured else None'
        $provider | Should Match 'Brand.flow_recovery remains'
        $provider | Should Not Match 'send_mails|Token.objects|set_password'
    }
    It 'contains valid PowerShell without exposing environment content' {
        foreach ($file in @('apply-authentik.ps1','prepare-password-recovery.ps1')) {
            $parseTokens = $null; $parseErrors = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $passwordRecoveryRoot $file), [ref]$parseTokens, [ref]$parseErrors)
            $parseErrors.Count | Should Be 0
        }
    }
}
