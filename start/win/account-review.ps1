[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('start','stop','status')][string]$Action = 'status')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/_common.ps1')
. (Join-Path $PSScriptRoot 'lib/runtime.ps1')
$name = 'identity-account-review'
try {
    if ($Action -eq 'status') {
        $state = if (Get-BillManagedProcess $name) { 'RUNNING' } else { 'STOPPED' }
        Write-BillLog "$name $state" 'INFO'
    } elseif ($Action -eq 'stop') {
        if ($PSCmdlet.ShouldProcess($name, 'Stop account review worker')) { Stop-BillComponent -Name $name }
    } elseif (!(Get-BillManagedProcess $name)) {
        $project = Join-Path $Global:BILL_REPO_ROOT 'apis/identity'
        $values = Read-BillEnvironment (Join-Path $Global:BILL_ENV_DIR 'identity.env')
        # The worker applies review decisions through whichever provider owns the credentials.
        $configured = if ((Get-BillAuthProvider) -eq 'local') { [bool]$values['IDENTITY_LOCAL_AUTH'] } else { [bool]$values['IDENTITY_AUTHENTIK_REVIEW_TOKEN'] }
        if (!$configured) { Write-BillLog 'Account review is not configured; worker skipped.' 'SKIP'; exit 0 }
        $uv = Get-Command uv -ErrorAction Stop
        if ($PSCmdlet.ShouldProcess($name, 'Start account review worker')) {
            [void](Start-BillProcess -Name $name -Executable $uv.Source -Environment $values -Arguments @(
                'run','--no-sync','--project',$project,'python','-m','identity.tasks.account_review_worker',
                '--env-file',(Join-Path $Global:BILL_ENV_DIR 'identity.env'),
                '--stop-file',(Join-Path (Split-Path -Parent (Get-BillRuntimePath $name)) "$name.stop")
            ))
            Start-Sleep -Milliseconds 500
            if (!(Get-BillManagedProcess $name)) { throw 'Account review worker exited during startup.' }
            Write-BillLog 'Account review worker started; decisions are confirmed by provider read-back.' 'OK'
        }
    }
    exit 0
} catch { Write-BillLog 'Account review worker lifecycle failed. Inspect the private local configuration.' 'ERROR'; exit 1 }
