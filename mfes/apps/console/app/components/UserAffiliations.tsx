'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, Notice, Pager, SearchSelect, TextField, asErrorStatus, parseListQuery, useListQuery, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { accessCall, useAccessCommand, useAccessLookup, useAccessSelection, type AccessContext, type AccessPageData } from '../lib/access-directory';
import { organisationPermission } from '../lib/organisation-contract';
import { validAccessDate } from '../lib/access-forms';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { AccessFailure } from './AccessCommon';

type Affiliation = components['schemas']['MembershipItem'];
function DepartmentLabel({ id, context }: { id: string | null; context: AccessContext }) {
  const selected = useAccessSelection('departments', id ?? undefined, context.companyId);
  return <>{id ? selected?.label ?? 'Saved department' : 'Company affiliation'}</>;
}
export function UserAffiliations({ userId, userStatus, context, onDraftChange, onPendingChange }: { userId: string; userStatus: string; context: AccessContext; onDraftChange?: (dirty: boolean) => void; onPendingChange?: (pending: boolean) => void }) {
  const userActive = ['active', 'invited'].includes(userStatus);
  const canRead = !!context.companyId && organisationPermission(context, 'departments', 'read'), canManage = canRead && organisationPermission(context, 'departments', 'manage');
  const [data, setData] = useState<AccessPageData<Affiliation>>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(canRead), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [departmentId, setDepartmentId] = useState<string | null>(null), [startedOn, setStartedOn] = useState(''), [reason, setReason] = useState(''), [error, setError] = useState(''), [message, setMessage] = useState(''), [review, setReview] = useState<{ action: 'add' | 'end' | 'primary'; row?: Affiliation } | null>(null), command = useAccessCommand();
  const departments = useAccessLookup('departments', context.companyId), selected = useAccessSelection('departments', departmentId ?? undefined, context.companyId);
  const query = useListQuery({ initial: parseListQuery(new URLSearchParams()), meta: loading || failure ? null : data.page }), params = query.params.toString(), base = '/v1/companies/' + context.companyId + '/memberships';
  useUnsavedChanges(() => !onDraftChange && (!!review || !!departmentId || !!startedOn || command.pending));
  useEffect(() => { onDraftChange?.(!!review || !!departmentId || !!startedOn || command.pending || command.uncertain); }, [review, departmentId, startedOn, command.pending, command.uncertain, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  useEffect(() => { onPendingChange?.(command.pending); }, [command.pending, onPendingChange]);
  useEffect(() => () => onPendingChange?.(false), [onPendingChange]);
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(canRead); setFailure(null);
    if (canRead) accessCall<AccessPageData<Affiliation>>({ path: base + '?' + params + '&user_id=' + userId, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return; if (!Array.isArray(result.items) || !result.page || result.items.some(row => row.user_id !== userId || row.company_id !== context.companyId)) throw { status: 502, message: 'Unexpected affiliation response.' }; setData(result); setLoading(false);
    }).catch(value => { if (!controller.signal.aborted) { setFailure(requestFailure(value)); setData({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }); setLoading(false); } });
    return () => controller.abort();
  }, [base, canRead, context.companyId, userId, params, revision]);
  function start(action: 'add' | 'end' | 'primary', row?: Affiliation) {
    if (command.pending || command.uncertain) return;
    if (action === 'add' && startedOn && !validAccessDate(startedOn)) { setError('Enter a valid start date.'); return; }
    command.reset(); setError(''); setReason(''); setReview({ action, row });
  }
  async function submit() {
    if (!review || command.pending || command.uncertain || !canManage) return;
    if (review.action !== 'add' && (!reason.trim() || reason.length > 500 || /[\x00-\x1f\x7f]/.test(reason))) { setError('Enter a printable reason of 1–500 characters.'); return; }
    const path = review.action === 'add' ? base : '/v1/memberships/' + review.row?.id + (review.action === 'end' ? '/end' : '/make-primary');
    const body = review.action === 'add' ? { user_id: userId, department_id: departmentId, started_on: startedOn || null, is_primary: false } : { reason: reason.trim() };
    await command.execute<Affiliation>({ path, method: 'POST', body }, row => {
      if (!row?.id || row.user_id !== userId || row.company_id !== context.companyId || review.row && row.id !== review.row.id) throw { status: 502, message: 'Unexpected saved affiliation. Reload before continuing.' };
      setReview(null); setDepartmentId(null); setStartedOn(''); setMessage(review.action === 'add' ? 'Affiliation added. No role access was granted.' : review.action === 'end' ? 'Affiliation ended. Role assignments remain separate.' : 'Primary affiliation updated.'); refresh();
    });
  }
  const columns: Column<Affiliation>[] = [{ key: 'department_id', header: 'Affiliation', type: 'custom', render: row => <DepartmentLabel id={row.department_id} context={context} /> }, { key: 'is_active', header: 'Status', type: 'text', value: row => !row.is_active ? 'Ended' : row.started_on && row.started_on > new Date().toISOString().slice(0, 10) ? 'Scheduled' : 'Current' }, { key: 'is_primary', header: 'Primary', type: 'text', value: row => row.is_primary ? 'Yes' : 'No' }, { key: 'started_on', header: 'Started', type: 'date' }, { key: 'ended_on', header: 'Ended', type: 'date' }];
  if (!canRead) return <Card><CardBody><Notice>Select a company with department read access to review this user’s affiliations.</Notice></CardBody></Card>;
  return <Card><CardHeader title="Company and department affiliations" subtitle={'In ' + (context.companyName ?? 'the selected company') + '. Affiliation is separate from authorization.'} /><CardBody><div className="janso-flow">
    {message && <Notice tone="success">{message}</Notice>}<AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); setReview(null); refresh(); }} />
    {canManage && userActive && <><SearchSelect label="Affiliation department" scopeKey={context.companyId} value={departmentId} selected={selected} loadOptions={departments} disabled={command.pending || command.uncertain || !!review} hint="Optional. Leave empty for a company affiliation." onChange={value => { setDepartmentId(value); setError(''); }} /><TextField label="Affiliation start date" type="date" value={startedOn} disabled={command.pending || command.uncertain || !!review} error={error && !review ? error : undefined} onChange={event => { setStartedOn(event.target.value); setError(''); }} /><Button type="button" disabled={command.pending || command.uncertain || !!review} onClick={() => start('add')}>Review affiliation addition</Button></>}
    <DataTable caption="User affiliations" columns={columns} rows={data.items} rowId={row => row.id} rowLabel={() => 'affiliation'} loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} emptyTitle="No affiliations in this company" emptyBody="Switch companies to inspect another authorized company. Affiliations do not grant role access."
      rowActions={row => canManage && row.is_active ? [{ id: 'end', label: 'End affiliation', destructive: true }, ...(!row.is_primary && userStatus === 'active' && (!row.started_on || row.started_on <= new Date().toISOString().slice(0, 10)) ? [{ id: 'primary', label: 'Make primary' }] : [])] : []} onAction={(action, row) => start(action === 'end' ? 'end' : 'primary', row)} />
    <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading || command.pending} noun="affiliation" />
  </div></CardBody><ConfirmDialog open={!!review} title={review?.action === 'add' ? 'Add affiliation?' : review?.action === 'end' ? 'End affiliation?' : 'Make affiliation primary?'} confirmLabel="Confirm affiliation change" busy={command.pending} tone={review?.action === 'end' ? 'danger' : 'default'} error={command.uncertain ? 'The result is unconfirmed. Cancel and reload the affiliations before changing them again.' : command.failure?.message} onCancel={() => setReview(null)} onConfirm={() => void submit()}>
    <p>{review?.action === 'add' ? 'Add this user to ' + (context.companyName ?? 'the selected company') + (departmentId ? ' / ' + (selected?.label ?? 'the selected department') : '') + '. No roles will be granted.' : review?.action === 'end' ? 'End this affiliation today. A primary default will be cleared. Role assignments must be reviewed separately.' : 'Make this the current primary affiliation and landing preference. The server checks both this and any previous primary company scope.'}</p>
    {review?.action === 'add' ? <p>Start date: {startedOn || 'Not specified'}</p> : <TextField label="Affiliation reason" value={reason} required maxLength={500} error={error || undefined} disabled={command.pending || command.uncertain} onChange={event => { setReason(event.target.value); setError(''); }} />}
  </ConfirmDialog></Card>;
}
