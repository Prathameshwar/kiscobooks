'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, DataTable, Notice, PageHeader, Pager, ReviewList, TextField, asErrorStatus, useFormatters, type Column } from '@janso/ui';
import { accessCall, labelKey, useAccessCommand, useAccessRecord, type AccessContext, type AccessPageData, type Invitation, type UserRecord } from '../lib/access-directory';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessNavigation, useAccessDraft } from './AccessCommon';
import { UserAffiliations } from './UserAffiliations';
import { UserPasswordRecovery } from './UserPasswordRecovery';

export function UserDetail({ context, id, returnTo }: { context: AccessContext; id: string; returnTo?: string }) {
  const record = useAccessRecord<UserRecord>('/v1/users/' + id, context.tenantId), command = useAccessCommand(), format = useFormatters();
  const [action, setAction] = useState<string | null>(null), [reason, setReason] = useState(''), [reasonError, setReasonError] = useState(''), [message, setMessage] = useState(''), [affiliationDirty, setAffiliationDirty] = useState(false);
  const [invitations, setInvitations] = useState<AccessPageData<Invitation>>({ items: [], page: { limit: 25, has_more: false, next_cursor: null } }), [historyError, setHistoryError] = useState<RequestFailure | null>(null), [historyLoading, setHistoryLoading] = useState(false), [revision, setRevision] = useState(0), [cursor, setCursor] = useState<string | null>(null), [cursorStack, setCursorStack] = useState<(string | null)[]>([]);
  const resendKey = useRef<string | undefined>(undefined), canInvite = context.tenantPermissions.includes('user.invite'), canChange = context.tenantPermissions.includes('user.deactivate') && id.toLowerCase() !== context.userId?.toLowerCase(), canRecover = context.tenantPermissions.includes('user.update') && id.toLowerCase() !== context.userId?.toLowerCase();
  const row = record.data, back = administrationReturn('users', returnTo), busy = command.pending || command.uncertain || affiliationDirty;
  const [affiliationPending, setAffiliationPending] = useState(false);
  const guard = useAccessDraft(!!action || affiliationDirty, command.pending || affiliationPending);
  useEffect(() => {
    if (!context.tenantPermissions.includes('user.read')) return; const controller = new AbortController(); setHistoryLoading(true); setHistoryError(null);
    accessCall<AccessPageData<Invitation>>({ path: `/v1/users/${id}/invitations?limit=25` + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), signal: controller.signal }).then(page => { if (!controller.signal.aborted) { setInvitations(page); setHistoryLoading(false); } }).catch(error => { if (!controller.signal.aborted) { setHistoryError(requestFailure(error)); setHistoryLoading(false); } });
    return () => controller.abort();
  }, [id, cursor, revision, context.tenantPermissions]);
  function start(value: string) { setAction(value); setReason(''); setReasonError(''); command.reset(); }
  async function run() {
    if (!action || !row) return;
    if (action !== 'resend' && (!reason.trim() || reason.length > 500)) { setReasonError('Enter a reason of no more than 500 characters.'); return; }
    const resend = action === 'resend', cancel = action.startsWith('cancel:');
    if (resend && !resendKey.current) resendKey.current = crypto.randomUUID();
    const path = resend ? `/v1/users/${id}/invitations` : cancel ? '/v1/invitations/' + action.slice(7) + '/cancel' : `/v1/users/${id}/${action === 'deactivate' ? 'deactivate' : 'lifecycle'}`;
    await command.execute({ path, method: 'POST', ...(resend ? { key: resendKey.current } : { body: { reason: reason.trim(), ...(action === 'suspend' ? { status: 'suspended' } : action === 'resume' ? { status: 'active' } : {}) } }) }, () => {
      setMessage(resend ? 'Invitation resend requested.' : cancel ? 'Invitation cancelled.' : action === 'deactivate' ? 'User deactivated and personal details anonymized.' : action === 'suspend' ? 'User suspended.' : 'User resumed.');
      resendKey.current = undefined; setAction(null); record.refresh(); setRevision(value => value + 1);
    });
  }
  const columns: Column<Invitation>[] = [{ key: 'status', header: 'Status', type: 'text' }, { key: 'created_at', header: 'Issued', type: 'datetime' }, { key: 'expires_at', header: 'Expires', type: 'datetime' }];
  const detail = administrationLink('/users/' + id, back);
  return <div className="janso-page"><AccessNavigation context={context} resource="users" mode="detail" id={id} title={row?.display_name} back={back} backLabel="users" onLeave={guard.leave} /><PageHeader title={row?.display_name ?? 'User details'} lede="Review the profile, invitation history and separate role assignments." actions={row && row.status !== 'deactivated' && context.tenantPermissions.includes('user.update') ? <a className="janso-btn janso-btn--primary" href={`/users/${id}/edit?returnTo=${encodeURIComponent(detail)}`} onClick={guard.leave}>Edit user</a> : undefined} />
    <AccessFailure failure={record.failure} refresh={record.refresh} />{!action && <AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); record.refresh(); }} />}{message && <Notice tone="success">{message}</Notice>}
    {record.loading ? <p role="status">Loading user…</p> : row && <Card><CardBody><ReviewList items={[
      { label: 'Email', value: row.email }, { label: 'Status', value: labelKey(row.status) }, { label: 'User type', value: labelKey(row.user_type) }, { label: 'Job title', value: row.job_title ?? 'Not set' }, { label: 'Employee code', value: row.employee_code ?? 'Not set' },
      { label: 'Phone', value: [row.phone_country_code, row.phone].filter(Boolean).join(' ') || 'Not set' }, { label: 'Joining date', value: row.date_of_joining ? format.date(row.date_of_joining) : 'Not set' }, { label: 'Updated', value: format.dateTime(row.updated_at) },
    ]} /><div className="janso-form-actions">{context.permissions.includes('role.read') && <a className="janso-link" href={administrationLink('/assignments?subject_type=user&subject_id=' + id, detail)} onClick={guard.leave}>View role assignments</a>}
      {context.permissions.includes('role.read') && context.permissions.includes('role.assign') && id.toLowerCase() !== context.userId?.toLowerCase() && ['active', 'invited'].includes(row.status) && <a className="janso-link" href={administrationLink('/assignments/new?subject_id=' + id, detail)} onClick={guard.leave}>Assign role</a>}
      {canInvite && row.status === 'invited' && <Button type="button" disabled={busy} onClick={() => start('resend')}>Resend invitation</Button>}
      {canChange && row.status === 'active' && <Button type="button" disabled={busy} onClick={() => start('suspend')}>Suspend user</Button>}
      {canChange && row.status === 'suspended' && <Button type="button" disabled={busy} onClick={() => start('resume')}>Resume user</Button>}
      {canChange && row.status !== 'deactivated' && <Button type="button" variant="danger" disabled={busy} onClick={() => start('deactivate')}>Deactivate and anonymize</Button>}
      {canRecover && row.status === 'active' && <UserPasswordRecovery userId={id} name={row.display_name} email={row.email} />}
    </div></CardBody></Card>}
    {row && <UserAffiliations key={context.companyId + ':' + id} userId={id} userStatus={row.status} context={context} onDraftChange={setAffiliationDirty} onPendingChange={setAffiliationPending} />}
    {context.tenantPermissions.includes('user.read') && <Card><CardBody><h2>Invitation history</h2><DataTable caption="Invitation history" columns={columns} rows={invitations.items} rowId={invitation => invitation.id} rowLabel={() => 'invitation'} loading={historyLoading} error={historyError ? asErrorStatus(historyError.status) : null} errorDetail={historyError?.message} onRetry={() => setRevision(value => value + 1)}
      rowActions={invitation => canInvite && invitation.status === 'pending' ? [{ id: 'cancel', label: 'Cancel invitation', tone: 'danger' }] : []} onAction={(_, invitation) => start('cancel:' + invitation.id)} />
      <Pager count={historyLoading || historyError ? 0 : invitations.items.length} from={cursorStack.length * 25 + 1} limit={25} hasPrevious={cursorStack.length > 0} hasNext={invitations.page.has_more} onPrevious={() => { setCursor(cursorStack.at(-1) ?? null); setCursorStack(prior => prior.slice(0, -1)); }} onNext={() => { setCursorStack(prior => [...prior, cursor]); setCursor(invitations.page.next_cursor); }} busy={historyLoading} noun="invitation" /></CardBody></Card>}
    <ConfirmDialog open={!!action} title={action === 'deactivate' ? 'Deactivate and anonymize user?' : action === 'resend' ? 'Resend invitation?' : action?.startsWith('cancel:') ? 'Cancel invitation?' : action === 'suspend' ? 'Suspend user?' : 'Resume user?'} confirmLabel="Confirm change" tone={action === 'deactivate' || action === 'suspend' ? 'danger' : 'default'} confirmPhrase={action === 'deactivate' ? 'DEACTIVATE' : undefined} busy={command.pending} onCancel={() => { if (!busy) setAction(null); }} onConfirm={() => void run()}>
      <p>{action === 'deactivate' ? 'This permanently anonymizes personal details and prevents sign-in. Historical references remain. This cannot be undone.' : 'This action is checked by Identity and recorded in the audit trail.'}</p>
      {action !== 'resend' && <TextField label="Action reason" value={reason} onChange={event => { setReason(event.target.value); setReasonError(''); }} error={reasonError} maxLength={500} required disabled={busy} />}
      <AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); setAction(null); record.refresh(); setRevision(value => value + 1); }} />
    </ConfirmDialog>{guard.confirmation}
  </div>;
}
