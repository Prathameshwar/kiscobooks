'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Badge, Button, Card, CardBody, CardHeader, Checkbox, ConfirmDialog, FieldGrid, FormActions, Notice, PageHeader, PageNavigation, ReviewList, Select, TextField, formatDateTime, useDisplayConfig } from '@janso/ui';
import { PlatformError, platformCall, platformFailure, type PlatformFailure } from '../../lib/platform-api';
import { useEditorDraft } from '../useEditorDraft';
import { PlatformHistory } from '../../components/PlatformHistory';

type Detail = components['schemas']['AccountReviewDetail'];
type Choices = components['schemas']['TenantChoices'];
export function accountReturnTo(value?: string): string {
  try {
    if (value && value.length > 3000) return '/platform/accounts';
    const url = new URL(value ?? '/platform/accounts', 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || url.pathname !== '/platform/accounts' || url.hash || /[\\\r\n]/.test(value ?? '') || [...url.searchParams.keys()].some(key => !['q','status','sort','limit','cursor'].includes(key))) return '/platform/accounts';
    return url.pathname + url.search;
  } catch { return '/platform/accounts'; }
}
export function AccountDetail({ accountId, permissions, returnTo, draftScope='' }: { accountId: string; permissions: readonly string[]; returnTo?: string; draftScope?:string }) {
  const back = accountReturnTo(returnTo), display = useDisplayConfig();
  const [record, setRecord] = useState<Detail | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<PlatformFailure | null>(null), [reload, setReload] = useState(0);
  const [choices,setChoices] = useState<Choices | null>(null), [reconciling,setReconciling] = useState(false);
  const editor = useEditorDraft('account-review:' + draftScope + ':' + accountId, { action:'approve',reason:'',workspace_name:'' });
  const { action,reason,workspace_name } = editor.draft;
  const setAction = (value:string) => editor.change({action:value});
  const setReason = (value:string) => editor.change({reason:value});
  const setWorkspaceName = (value:string) => editor.change({workspace_name:value});
  const [attested, setAttested] = useState(false), [confirm, setConfirm] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const guard = useRef(false), requestKey = editor.key, reasonRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    Promise.all([platformCall<Detail>('/v1/platform/accounts/' + accountId, 'GET', undefined, undefined, controller.signal), platformCall<Choices>('/v1/platform/accounts/options','GET',undefined,undefined,controller.signal).catch(()=>null)])
      .then(([value,options]) => { if (!controller.signal.aborted) { setRecord(value); setChoices(options); editor.populate({ action:value.status === 'rejected' ? 'reopen' : 'approve',reason:'',workspace_name:'' }); setAttested(false); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setRecord(null); setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [accountId, reload]);
  const queued = record?.history.some(command => command.status === 'queued');
  const canReview = record && record.status !== 'approved' && !record.needs_attention && !queued && permissions.includes('platform.account.review');
  function validate() {
    if (reason.trim().length < 3 || reason.trim().length > 500) { setError({status:422,message:'Enter a reason with 3 to 500 characters.'}); reasonRef.current?.focus(); return; }
    if (action === 'approve' && !attested) { setError({status:422,message:'Confirm that you independently checked the person’s identity and email.'}); return; }
    if (action === 'approve' && record?.workspace_name === null && (!workspace_name.trim() || workspace_name.trim().length > 200 || /[\x00-\x1f\x7f]/.test(workspace_name))) { setError({status:422,message:'Enter a valid workspace name with up to 200 characters.'}); return; }
    setError(null); setConfirm(true);
  }
  async function submit() {
    if (!record || guard.current) return; guard.current = true; setBusy(true); setError(null);
    if (!requestKey.current) requestKey.current = crypto.randomUUID();
    try {
      const updated = await platformCall<Detail>(`/v1/platform/accounts/${accountId}/review`, 'POST', { action, reason:reason.trim(), attested, version:record.version, ...(action === 'approve' && record.workspace_name === null ? {workspace_name:workspace_name.trim()} : {}) }, requestKey.current);
      setRecord(updated); setConfirm(false); setReason(''); setAttested(false); editor.saved(); requestKey.current = crypto.randomUUID();
      const latest = updated.history[0];
      setMessage(latest?.status === 'completed' ? `Account ${updated.status === 'approved' ? latest.workspace_name ? 'approved. The workspace and administrator access are ready.' : 'approved. Invitation access can now be accepted.' : updated.status === 'rejected' ? 'rejected. Sign-in remains disabled.' : 'reopened for review.'}` : 'Decision saved. Provider confirmation and workspace creation are pending; refresh to check status.');
    } catch (value) { setError(platformFailure(value)); setConfirm(false); } finally { guard.current = false; setBusy(false); }
  }
  async function reconcile() {
    if (!record || guard.current) return;
    if (reason.trim().length < 3 || reason.trim().length > 500) {setError({status:422,message:'Enter a reason with 3 to 500 characters.'});reasonRef.current?.focus();return;}
    guard.current=true;setReconciling(true);setError(null);
    try {
      const updated=await platformCall<Detail>(`/v1/platform/accounts/${accountId}/reconcile`,'POST',{version:record.version,reason:reason.trim()});
      setRecord(updated);setAttested(false);editor.saved();editor.change({action:updated.status==='rejected'?'reopen':'approve',reason:''});
      setMessage('Current details reconciled. Review the updated identity and email before making a new decision.');
    } catch(value){setError(platformFailure(value));} finally{guard.current=false;setReconciling(false);}
  }
  const label=(items: readonly {code:string;name:string}[] | undefined,code:string)=>items?.find(item=>item.code===code)?.name ?? (code || 'Not specified');
  const date = (value: string | null) => value ? formatDateTime(value, display) : 'Pending';
  return <div className="janso-page">
    <PageNavigation back={{ href:back,label:'account approvals' }} breadcrumbs={[{label:'Platform administration',href:'/platform'},{label:'Account approvals',href:back},{label:record?.name ?? 'Registration details'}]} />
    <PageHeader title={record?.name ?? 'Registration details'} lede="Account details, manual verification and review history." actions={<Button variant="ghost" onClick={() => setReload(value => value + 1)} disabled={loading || busy}>Refresh status</Button>} />
    <PlatformError value={error} returnTo={`/platform/accounts/${accountId}?returnTo=${encodeURIComponent(back)}`} onNavigate={editor.preserve} />
    {editor.restored ? <Notice>Your decision draft was restored. Review the current account details and confirm your attestation again.</Notice> : null}
    {message ? <Notice tone={record?.history[0]?.status === 'completed' ? 'success' : 'info'}>{message}</Notice> : null}
    {loading ? <p role="status">Loading registration…</p> : null}
    {record ? <>
      {record.needs_attention ? <Notice tone="warning">Provider details changed outside this review. Reconcile the current inactive, unverified registration before recording a new decision. Active or verified provider accounts need correction in Authentik first.</Notice> : null}
      {queued ? <Notice>Processing the saved decision. Sign-in remains subject to provider confirmation. The review worker will retry automatically.</Notice> : null}
      <div className="janso-grid janso-grid--split janso-grid--start">
        <Card><CardHeader title="Account details" subtitle="Check these details independently" /><CardBody><ReviewList items={[
          {label:'Full name',value:record.name},{label:'Username',value:record.username},{label:'Email',value:record.email},
          {label:'Country',value:label(choices?.countries,record.country_code)},{label:'State',value:label(choices?.states,record.state_code)},
          {label:'Workspace request',value:record.workspace_name === null ? 'Earlier registration — enter a workspace name when approving' : record.workspace_name || 'Joining an existing invitation'},
          {label:'Received',value:date(record.created_at)},{label:'Last checked',value:date(record.updated_at)},
        ]} /></CardBody></Card>
        <Card><CardHeader title="Access and verification" /><CardBody><ReviewList items={[
          {label:'Review status',value:<Badge tone={record.status === 'approved' ? 'success' : 'neutral'}>{record.status}</Badge>},
          {label:'Provider account',value:record.provider_active ? 'Active' : 'Inactive'},
          {label:'Email verification',value:record.provider_verified ? 'Verified' : 'Not verified'},
        ]} /><Notice>Approval records manual verification. Public signup approval creates a tenant and its first administrator; invitation signup joins its existing tenant after acceptance. Account-ready details are emailed when delivery is configured, and can always be shared manually.</Notice></CardBody></Card>
      </div>
      {record.handoff ? <Card><CardHeader title="Share account access" subtitle="The account is approved and active" /><CardBody><div className="janso-flow">
        <Notice>{record.handoff.notification_status === 'queued' ? 'Account-ready email is queued. Manual sharing is also available.' : 'Automatic email is not configured. Copy and share these details privately.'}</Notice>
        <TextField label="Sign-in username" readOnly value={record.handoff.username} />
        <TextField label="Account access link" readOnly value={record.handoff.invitation_url ?? record.handoff.sign_in_url} />
        <p>{record.handoff.invitation_url ? 'Open this invitation and sign in with the username and password chosen during signup.' : 'Sign in with the username and password chosen during signup. No further approval or invitation acceptance is needed.'}</p>
        <Button variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(record.handoff!.invitation_url ?? record.handoff!.sign_in_url); setMessage('Access link copied.'); } catch { setMessage('Select and copy the access link above.'); } }}>Copy access link</Button>
        <Button variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(`Access: ${record.handoff!.invitation_url ?? record.handoff!.sign_in_url}\nUsername: ${record.handoff!.username}\nUse the password you chose during signup.`); setMessage('Login details copied.'); } catch { setMessage('Select and copy the login details above.'); } }}>Copy login details</Button>
      </div></CardBody></Card> : null}
      {record.needs_attention && record.status !== 'approved' && !queued && permissions.includes('platform.account.review') ? <form noValidate onSubmit={event=>{event.preventDefault();void reconcile();}}><Card><CardHeader title="Reconcile registration" /><CardBody>
        <FieldGrid><TextField ref={reasonRef} label="Reconciliation reason" value={reason} required minLength={3} maxLength={500} disabled={loading || reconciling} onChange={event=>setReason(event.target.value)} /></FieldGrid>
      </CardBody><FormActions><Button type="submit" disabled={loading || reconciling}>Reconcile current details</Button></FormActions></Card></form> : null}
      {canReview ? <form noValidate onSubmit={event => { event.preventDefault(); validate(); }}><Card><CardHeader title="Review registration" subtitle="Record your decision and supporting reason" /><CardBody>
        <FieldGrid disabled={loading || busy}>
          <Select label="Decision" value={action} onChange={setAction} options={record.status === 'rejected' ? [{value:'reopen',label:'Reopen for review'}] : [{value:'approve',label:'Approve account'},{value:'reject',label:'Reject registration'}]} />
          <TextField ref={reasonRef} label="Review reason" value={reason} minLength={3} maxLength={500} required onChange={event => setReason(event.target.value)} hint="Record the basis of your decision. Avoid passwords or sensitive identity numbers." />
          {action === 'approve' && record.workspace_name === null ? <TextField label="Workspace name" value={workspace_name} required maxLength={200} onChange={event => setWorkspaceName(event.target.value)} hint="This earlier registration did not request a workspace name." /> : null}
          {action === 'approve' ? <Checkbox checked={attested} onChange={event => {setAttested(event.target.checked);requestKey.current=crypto.randomUUID();}}>I independently checked this person’s identity and the displayed email address.</Checkbox> : null}
        </FieldGrid>
      </CardBody><FormActions cancel={{ href: back }}><Button type="submit" disabled={loading || busy}>Review decision</Button></FormActions></Card></form> : null}
      {permissions.includes('platform.account.read') ? <PlatformHistory entityType="account_review" entityId={accountId} revision={record.version} /> : null}
      <Card><CardHeader title="Review history" subtitle="Latest 50 decisions and their provider results" /><CardBody>
        {record.history.length ? record.history.map(command => <div key={command.id} className="janso-flow"><ReviewList items={[{label:'Decision',value:command.action},{label:'Reason',value:command.reason},{label:'Result',value:command.status},{label:'Requested',value:date(command.created_at)},{label:'Completed',value:date(command.completed_at)}]} />{command.error_code ? <Notice tone="warning">{command.error_code === 'provider_unavailable' ? 'Provider unavailable; the saved command will be retried.' : 'Decision needs administrator reconciliation.'}</Notice> : null}</div>) : <p>No decisions recorded yet.</p>}
      </CardBody></Card>
    </> : null}
    <ConfirmDialog open={confirm} title="Confirm account decision?" confirmLabel={action === 'approve' ? 'Approve account' : action === 'reject' ? 'Reject registration' : 'Reopen registration'} tone={action === 'reject' ? 'danger' : 'default'} busy={busy} onCancel={() => setConfirm(false)} onConfirm={submit}>
      <p>{action === 'approve' ? record?.workspace_name === '' ? 'This enables sign-in so the person can accept their existing invitation.' : `This enables sign-in and creates ${record?.workspace_name ?? workspace_name} with this person as its first administrator.` : 'This account remains inactive and unverified.'}</p>
      {action === 'approve' ? <p>Account-ready email is sent when delivery is configured. Manual sharing remains available.</p> : null}
    </ConfirmDialog>
  </div>;
}
