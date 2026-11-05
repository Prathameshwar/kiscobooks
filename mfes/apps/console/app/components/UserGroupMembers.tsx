'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, Notice, Pager, SearchSelect, asErrorStatus, parseListQuery, useListQuery, type Column, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { accessCall, useAccessCommand, type AccessContext, type AccessPageData, type UserRow } from '../lib/access-directory';
import { organisationPermission, type GroupMember } from '../lib/organisation-ui';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { AccessFailure } from './AccessCommon';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';

export function UserGroupMembers({ groupId, active, context, onDraftChange, onPendingChange }: { groupId: string; active: boolean; context: AccessContext; onDraftChange?: (dirty: boolean) => void; onPendingChange?: (pending: boolean) => void }) {
  const [data, setData] = useState<AccessPageData<GroupMember>>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState<SearchSelectOption | null>(null), [review, setReview] = useState<{ mode: 'add' | 'remove'; userId: string; label: string } | null>(null), [message, setMessage] = useState(''), command = useAccessCommand();
  const query = useListQuery({ initial: parseListQuery(new URLSearchParams()), meta: loading || failure ? null : data.page }), params = query.params.toString(), base = '/v1/user-groups/' + groupId + '/members';
  const manage = organisationPermission(context, 'user-groups', 'manage'), canSearch = context.tenantPermissions.includes('user.read');
  useUnsavedChanges(() => !onDraftChange && (!!review || !!selected || command.pending));
  useEffect(() => { onDraftChange?.(!!review || !!selected || command.pending || command.uncertain); }, [review, selected, command.pending, command.uncertain, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  useEffect(() => { onPendingChange?.(command.pending); }, [command.pending, onPendingChange]);
  useEffect(() => () => onPendingChange?.(false), [onPendingChange]);
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null);
    accessCall<AccessPageData<GroupMember>>({ path: base + '?' + params, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return; if (!Array.isArray(result.items) || !result.page) throw { status: 502, message: 'Unexpected member directory response.' }; setData(result); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error)); setData({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }); setLoading(false); } });
    return () => controller.abort();
  }, [base, params, revision]);
  const users: SearchSelectLoader = useCallback(async ({ q, cursor, signal }) => {
    const search = new URLSearchParams({ limit: '50' }); if (q.trim().length >= 2) search.set('q', q.trim().slice(0, 100)); if (cursor) search.set('cursor', cursor);
    const result = await accessCall<AccessPageData<UserRow>>({ path: '/v1/users?' + search, signal });
    return { items: result.items.map(row => ({ id: row.id, label: row.display_name, meta: row.email, disabled: row.id === context.userId || !['active', 'invited'].includes(row.status) })), nextCursor: result.page.has_more ? result.page.next_cursor : null };
  }, [context.userId]);
  async function submit() {
    if (!review || command.pending || command.uncertain || !manage) return;
    const decision = review;
    await command.execute({ path: base + (decision.mode === 'remove' ? '/' + decision.userId : ''), method: decision.mode === 'remove' ? 'DELETE' : 'POST', ...(decision.mode === 'add' ? { body: { user_id: decision.userId } } : {}) }, () => { setReview(null); setSelected(null); setMessage(decision.mode === 'add' ? 'Member added. Group-derived access takes effect after authorization refresh.' : 'Member removed. The user account and audit history are retained.'); refresh(); });
  }
  const columns: Column<GroupMember>[] = [{ key: 'display_name', header: 'User', type: 'text', value: row => row.display_name ?? 'User details restricted' }, { key: 'user_id', header: 'User reference', type: 'code' }];
  return <Card><CardHeader title="Group members" subtitle="Changing membership can change effective permissions." /><CardBody><div className="janso-flow">
    {message && <Notice tone="success">{message}</Notice>}<AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); setReview(null); setSelected(null); refresh(); }} />
    {manage && active && canSearch ? <><SearchSelect label="User to add" scopeKey={context.tenantId} value={selected?.id ?? null} selected={selected} loadOptions={users} disabled={command.pending || command.uncertain || !!review} hint="Choose an active or invited tenant user. You cannot change your own group membership." onChange={(_value, option) => { setSelected(option); setMessage(''); }} /><Button type="button" disabled={!selected || command.pending || command.uncertain || !!review} onClick={() => selected && setReview({ mode: 'add', userId: selected.id, label: selected.label })}>Review member addition</Button></>
      : manage && active && !canSearch ? <Notice>Tenant-wide user read permission is required to choose a member. Ask a tenant administrator to add members.</Notice> : !active ? <Notice>This group is inactive. Reactivate it before adding members.</Notice> : null}
    <DataTable caption="Group members" columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.display_name ?? 'group member'} loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} emptyTitle="No group members" emptyBody="Adding a member does not change company affiliation. Role assignments determine group-derived access."
      rowActions={row => manage && row.user_id !== context.userId ? [{ id: 'remove', label: 'Remove member', destructive: true }] : []} onAction={(_action, row) => { if (command.pending || command.uncertain) return; setReview({ mode: 'remove', userId: row.user_id, label: row.display_name ?? 'this user' }); }} />
    <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading || command.pending} noun="member" />
  </div></CardBody><ConfirmDialog open={!!review} title={review?.mode === 'remove' ? 'Remove group member?' : 'Add group member?'} confirmLabel={review?.mode === 'remove' ? 'Remove member' : 'Add member'} tone={review?.mode === 'remove' ? 'danger' : 'default'} busy={command.pending} error={command.uncertain ? 'The result is unconfirmed. Cancel and reload the member list before any further change.' : command.failure?.message} onCancel={() => setReview(null)} onConfirm={() => void submit()}>
    <p>{review?.label}</p><p>{review?.mode === 'remove' ? 'This removes group-derived permissions. The user account, other assignments and company affiliations are retained.' : 'This user will receive permissions from applicable assignments to this group. The server checks your held authority and prevents self-escalation.'}</p>
  </ConfirmDialog></Card>;
}
