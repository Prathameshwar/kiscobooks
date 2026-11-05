'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardHeader, ConfirmDialog, DataTable, FilterBar, Notice, PageHeader, Pager, ReviewList, SearchSelect, Select, TextField, asErrorStatus, parseListQuery, useListQuery, type Column } from '@janso/ui';
import { accessCall, assignmentStatus, labelKey, safeAccessReturn, useAccessCommand, useAccessLookup, type AccessContext, type AccessPageData, type Assignment } from '../lib/access-directory';
import { validateAssignment } from '../lib/access-forms';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { AccessFailure, AccessNavigation, useAccessDraft } from './AccessCommon';
import { administrationLink, administrationReturn } from '../lib/administration-navigation';
import { organisationPermission } from '../lib/organisation-contract';

export function AssignmentDirectory({ context, initialQuery = '', returnTo }: { context: AccessContext; initialQuery?: string; returnTo?: string }) {
  const source = returnTo ?? new URLSearchParams(initialQuery).get('returnTo') ?? undefined;
  const origin = source ? administrationReturn('assignments', source) : undefined;
  const directoryLink = (value: string) => origin ? administrationLink('/assignments' + (value ? '?' + value : ''), origin) : '/assignments' + (value ? '?' + value : '');
  const initial = parseListQuery(new URL(safeAccessReturn('assignments', '/assignments?' + initialQuery), 'https://console.invalid').searchParams, { filterKeys: ['subject_type', 'subject_id', 'role_id', 'scope_type', 'active'] });
  if (!initial.sort.length) initial.sort = [{ key: 'created_at', direction: 'desc' }];
  const [data, setData] = useState<AccessPageData<Assignment>>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<Assignment | null>(null), [reason, setReason] = useState(''), [from, setFrom] = useState(''), [to, setTo] = useState(''), [errors, setErrors] = useState<Record<string, string>>({}), [message, setMessage] = useState(''), [retryLocked, setRetryLocked] = useState(false);
  const command = useAccessCommand(), key = useRef<string | undefined>(undefined);
  const users = useAccessLookup('users'), groups = useAccessLookup('groups'), roles = useAccessLookup('roles');
  const query = useListQuery({ initial, meta: loading || failure ? null : data.page, onQueryChange: value => window.history.replaceState(null, '', directoryLink(value)) });
  const params = query.params.toString(), today = new Date().toISOString().slice(0, 10), back = directoryLink(query.queryString);
  const canAssign = context.permissions.includes('role.assign'), locked = command.pending || command.uncertain;
  const guard = useAccessDraft(!!selected, command.pending);
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null);
    accessCall<AccessPageData<Assignment>>({ path: '/v1/role-assignments?' + params, signal: controller.signal }).then(page => { if (!controller.signal.aborted) { if (!Array.isArray(page.items) || !page.page) throw { status: 502, message: 'Unexpected assignment response.' }; setData(page); setLoading(false); } }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error)); setData({ items: [], page: { limit: query.limit, has_more: false, next_cursor: null } }); setLoading(false); } });
    return () => controller.abort();
  }, [params, revision, context.tenantId]);
  useEffect(() => { if (command.failure && command.failure.status < 500) { key.current = undefined; setRetryLocked(false); } }, [command.failure]);
  function start(row: Assignment) { if (locked) return; setSelected(row); setReason(''); setFrom(''); setTo(''); setErrors({}); setRetryLocked(false); key.current = undefined; command.reset(); }
  async function change() {
    if (!selected || locked || !canAssign || selected.subject_type === 'user' && selected.subject_id.toLowerCase() === context.userId?.toLowerCase()) return;
    const regrant = !selected.is_active;
    const next = validateAssignment({ role_id: selected.role_id, subject_type: selected.subject_type, subject_id: selected.subject_id, scope_type: selected.scope_type, scope_id: selected.scope_id ?? '', reason, ...(regrant ? { valid_from: from, valid_to: to } : {}) }, context.userId);
    setErrors(next); if (Object.keys(next).length) return;
    if (regrant && !key.current) key.current = crypto.randomUUID();
    if (regrant) setRetryLocked(true);
    await command.execute({ path: `/v1/role-assignments/${selected.id}/${regrant ? 'regrant' : 'revoke'}`, method: 'POST', ...(regrant ? { key: key.current } : {}), body: { reason: reason.trim(), ...(regrant ? { valid_from: from || null, valid_to: to || null } : {}) } }, () => { setMessage(regrant ? 'Assignment regranted.' : 'Assignment revoked. Other grants may still provide access.'); setSelected(null); setRetryLocked(false); key.current = undefined; refresh(); });
  }
  const columns: Column<Assignment>[] = [
    { key: 'role_id', header: 'Role', type: 'custom', render: row => <a className="janso-link" href={administrationLink('/roles/' + row.role_id, back)} onClick={guard.leave}>{row.role_name ?? row.role_id}</a> },
    { key: 'subject_id', header: 'Subject', type: 'custom', render: row => row.subject_type === 'user' && context.tenantPermissions.includes('user.read') || row.subject_type === 'user_group' && organisationPermission(context, 'user-groups', 'read') ? <a className="janso-link" href={administrationLink((row.subject_type === 'user' ? '/users/' : '/user-groups/') + row.subject_id, back)} onClick={guard.leave}>{row.subject_label ?? row.subject_id}</a> : <>{labelKey(row.subject_type)}: {row.subject_label ?? row.subject_id}</> },
    { key: 'scope_type', header: 'Scope', type: 'text', value: row => row.scope_type === 'tenant' ? 'Whole tenant' : labelKey(row.scope_type) + ': ' + (row.scope_label ?? row.scope_id) },
    { key: 'is_active', header: 'Status', type: 'text', value: row => assignmentStatus(row, today) }, { key: 'valid_from', header: 'Starts', type: 'date' }, { key: 'valid_to', header: 'Expires', type: 'date' }, { key: 'created_at', header: 'Created', type: 'datetime', sortable: true },
  ];
  const create = <a className="janso-btn janso-btn--primary" href={administrationLink('/assignments/new', back)} onClick={guard.leave}>Assign role</a>;
  return <div className="janso-page"><AccessNavigation context={context} resource="assignments" back={origin} onLeave={guard.leave} /><PageHeader title="Role assignments" lede="Review who receives a role, its scope and validity. This directory includes only assignments your read authority covers." actions={canAssign ? create : undefined} />
    {message && <Notice tone="success">{message}</Notice>}<Notice tone="info">Expiry dates are inclusive. Expired active grants must be revoked before regranting. Subject and scope labels appear only when their directory read permissions allow them.</Notice>
    <Card><CardHeader title="Assignment directory" /><FilterBar applied={Object.entries(query.filters).map(([id, value]) => ({ id, label: labelKey(id), value: String(value) }))} onRemove={name => { query.setFilter(name, null); if (name === 'subject_type') query.setFilter('subject_id', null); }} onClearAll={query.clearFilters} actions={<Button type="button" variant="ghost" disabled={loading} onClick={refresh}>Refresh</Button>}>
      <SearchSelect label="Filter role" value={String(query.filters.role_id ?? '') || null} selected={data.items.find(row => row.role_id === query.filters.role_id)?.role_name ? { id: String(query.filters.role_id), label: data.items.find(row => row.role_id === query.filters.role_id)!.role_name! } : undefined} loadOptions={roles} minQueryLength={0} onChange={value => query.setFilter('role_id', value)} />
      <Select label="Subject type" value={String(query.filters.subject_type ?? '')} placeholder="All subjects" options={[{ value: 'user', label: 'User' }, { value: 'user_group', label: 'User group' }]} onChange={value => { query.setFilter('subject_id', null); query.setFilter('subject_type', value || null); }} />
      {query.filters.subject_type === 'user' && context.tenantPermissions.includes('user.read') && <SearchSelect label="Filter user" value={String(query.filters.subject_id ?? '') || null} loadOptions={users} selected={data.items.find(row => row.subject_id === query.filters.subject_id)?.subject_label ? { id: String(query.filters.subject_id), label: data.items.find(row => row.subject_id === query.filters.subject_id)!.subject_label! } : undefined} onChange={value => query.setFilter('subject_id', value)} />}
      {query.filters.subject_type === 'user_group' && context.tenantPermissions.includes('group.read') && <SearchSelect label="Filter user group" value={String(query.filters.subject_id ?? '') || null} loadOptions={groups} selected={data.items.find(row => row.subject_id === query.filters.subject_id)?.subject_label ? { id: String(query.filters.subject_id), label: data.items.find(row => row.subject_id === query.filters.subject_id)!.subject_label! } : undefined} hint="Search by group code prefix." onChange={value => query.setFilter('subject_id', value)} />}
      <Select label="Scope type" value={String(query.filters.scope_type ?? '')} placeholder="All scopes" options={['tenant', 'company', 'department'].map(value => ({ value, label: labelKey(value) }))} onChange={value => query.setFilter('scope_type', value || null)} /><Select label="Grant state" value={String(query.filters.active ?? '')} placeholder="All states" options={[{ value: 'true', label: 'Active grants' }, { value: 'false', label: 'Revoked grants' }]} onChange={value => query.setFilter('active', value || null)} />
    </FilterBar><DataTable caption="Assignment directory" columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.role_name ?? 'role assignment'} loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} sort={query.sort} onSortChange={query.setSort} filtered={query.filtered} onClearFilters={query.clearFilters} emptyTitle="No assignments found" emptyAction={canAssign ? create : undefined} rowActions={row => canAssign && !(row.subject_type === 'user' && row.subject_id.toLowerCase() === context.userId?.toLowerCase()) ? [{ id: row.is_active ? 'revoke' : 'regrant', label: row.is_active ? 'Revoke access' : 'Regrant access', tone: row.is_active ? 'danger' : undefined, disabled: locked }] : []} onAction={(_, row) => start(row)} />
      <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} noun="assignment" />
    </Card>
    <ConfirmDialog open={!!selected} title={selected?.is_active ? 'Revoke role access?' : 'Regrant role access?'} confirmLabel={selected?.is_active ? 'Revoke access' : 'Regrant access'} tone={selected?.is_active ? 'danger' : 'default'} busy={command.pending} onCancel={() => { if (!command.pending) { setSelected(null); if (retryLocked) refresh(); } }} onConfirm={() => void change()}>
      {selected && <ReviewList items={[{ label: 'Role', value: selected.role_name ?? selected.role_id }, { label: 'Subject', value: selected.subject_label ?? selected.subject_id }, { label: 'Scope', value: selected.scope_label ?? selected.scope_id ?? 'Whole tenant' }]} />}
      <TextField label="Action reason" value={reason} onChange={event => { setReason(event.target.value); setErrors({}); }} required maxLength={500} error={errors.reason} disabled={locked || retryLocked} />
      {selected && !selected.is_active && <><TextField label="Start date" type="date" value={from} onChange={event => { setFrom(event.target.value); setErrors({}); }} error={errors.valid_from} disabled={locked || retryLocked} /><TextField label="Expiry date" type="date" value={to} onChange={event => { setTo(event.target.value); setErrors({}); }} error={errors.valid_to} disabled={locked || retryLocked} /></>}
      {retryLocked && command.failure && <Notice tone="info">Retry sends this same request with its original idempotency key.</Notice>}
      <AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); setSelected(null); refresh(); }} />
    </ConfirmDialog>{!selected && <AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); refresh(); }} />}
    {guard.confirmation}
  </div>;
}
