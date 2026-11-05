'use client';
import { companyAccess } from '../lib/access-permissions';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardHeader, DataTable, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, asErrorStatus, parseListQuery, useListQuery, type Column } from '@janso/ui';
import { accessCall, labelKey, safeAccessReturn, userStatuses, userTypes, type AccessContext, type AccessPageData } from '../lib/access-directory';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { goTo } from '../lib/navigate';
import { AccessNavigation } from './AccessCommon';
import { administrationLink, administrationReturn } from '../lib/administration-navigation';

type DirectoryRow = { id: string; display_name?: string; name?: string; key?: string; email?: string; status?: string; user_type?: string; is_system?: boolean; is_active?: boolean; updated_at?: string };
export function AccessDirectory({ resource, context, initialQuery = '', companyScoped = false }: { resource: 'users' | 'roles'; context: AccessContext; initialQuery?: string; companyScoped?: boolean }) {
  const source = new URLSearchParams(initialQuery).get('returnTo') ?? undefined;
  const requestedOrigin = source ? administrationReturn(resource, source) : undefined;
  const origin = requestedOrigin && new URL(requestedOrigin, 'https://console.invalid').pathname !== '/' + resource ? requestedOrigin : undefined;
  const directoryLink = (value: string) => origin ? administrationLink('/' + resource + (value ? '?' + value : ''), origin) : '/' + resource + (value ? '?' + value : '');
  const title = resource === 'users' ? 'Users' : 'Roles', singular = resource === 'users' ? 'user' : 'role';
  const canCreate = (resource === 'users' ? companyScoped ? companyAccess(context, 'user.invite') : context.tenantPermissions.includes('user.invite') : context.tenantPermissions.includes('role.manage'));
  const canEdit = !companyScoped && context.tenantPermissions.includes(resource === 'users' ? 'user.update' : 'role.manage');
  const initial = parseListQuery(new URL(safeAccessReturn(resource, '/' + resource + (initialQuery ? '?' + initialQuery : '')), 'https://console.invalid').searchParams, { filterKeys: resource === 'users' ? companyScoped ? ['status'] : ['status', 'user_type'] : ['scope_hint'] });
  const [data, setData] = useState<AccessPageData<DirectoryRow>>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const query = useListQuery({ initial, meta: loading || failure ? null : data.page, onQueryChange: value => window.history.replaceState(null, '', directoryLink(value)) });
  const params = query.params.toString(), requestId = useRef(0);
  const back = directoryLink(query.queryString), href = (suffix: string) => administrationLink('/' + resource + suffix, back);
  const create = <a className="janso-btn janso-btn--primary" href={href('/new')}>{resource === 'users' ? 'Invite user' : 'New role'}</a>;
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(), number = ++requestId.current; setLoading(true); setFailure(null);
    const search = new URLSearchParams(params); if ((search.get('q') ?? '').trim().length < 2) search.delete('q');
    if (companyScoped) search.delete('user_type');
    accessCall<AccessPageData<DirectoryRow>>({ path: (companyScoped ? '/v1/companies/' + context.companyId + '/users' : '/v1/' + resource) + '?' + search, signal: controller.signal }).then(page => {
      if (controller.signal.aborted || number !== requestId.current) return;
      if (!Array.isArray(page.items) || !page.page) throw { status: 502, message: 'Unexpected directory response. Retry loading.' };
      setData(page); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted && number === requestId.current) { setFailure(requestFailure(error, 'access service')); setData({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }); setLoading(false); } });
    return () => controller.abort();
  }, [resource, params, revision, context.tenantId, context.companyId, companyScoped]);
  const columns: Column<DirectoryRow>[] = resource === 'users' ? [
    { key: 'display_name', header: 'Name', type: 'link', href: row => href('/' + row.id), sortable: true }, { key: 'email', header: 'Email', type: 'text', sortable: true },
    { key: 'user_type', header: 'User type', type: 'text', value: row => labelKey(row.user_type ?? '') }, { key: 'status', header: 'Status', type: 'text', value: row => labelKey(row.status ?? '') },
  ] : [{ key: 'name', header: 'Name', type: 'link', href: row => href('/' + row.id), sortable: true }, { key: 'key', header: 'Key', type: 'code', sortable: true },
    { key: 'is_system', header: 'Type', type: 'text', value: row => row.is_system ? 'System role' : 'Custom role' }, { key: 'is_active', header: 'Status', type: 'text', value: row => row.is_active ? 'Active' : 'Inactive' }];
  return <div className="janso-page"><AccessNavigation context={context} resource={resource} back={origin} />
    <PageHeader title={companyScoped ? 'Company users' : title} lede={companyScoped ? 'Current affiliated people in ' + (context.companyName ?? 'the selected company') + '. Account-wide profile and lifecycle changes are managed by a tenant administrator.' : resource === 'users' ? 'People in this tenant. User profiles and company affiliation are separate from role grants.' : 'Reusable permission bundles. System roles are read-only; clone a role to customise it.'} actions={canCreate ? create : undefined} />
    {companyScoped && <Notice tone="info">Invitations add a company affiliation without granting access. Use role assignments to grant permissions you hold in this company. Switch companies to review another authorized workplace.</Notice>}
    <Card><CardHeader title={title + ' directory'} />
      <FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...Object.entries(query.filters).map(([id, value]) => ({ id, label: labelKey(id), value: labelKey(String(value)) }))]} onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, null)} onClearAll={query.clearFilters} actions={<Button type="button" variant="ghost" disabled={loading} onClick={refresh}>Refresh</Button>}>
        <TableSearch label={'Search ' + title.toLowerCase()} value={query.q} onChange={value => query.setSearch(value.slice(0, 100))} hint={resource === 'users' ? 'Search by name or email; enter at least two characters.' : 'Search by name or key; enter at least two characters.'} busy={loading} />
        {resource === 'users' ? <><Select label="Status" value={String(query.filters.status ?? '')} placeholder="All statuses" options={userStatuses.map(value => ({ value, label: labelKey(value) }))} onChange={value => query.setFilter('status', value || null)} />
          {!companyScoped && <Select label="User type" value={String(query.filters.user_type ?? '')} placeholder="All user types" options={userTypes.map(value => ({ value, label: labelKey(value) }))} onChange={value => query.setFilter('user_type', value || null)} />}</> :
          <Select label="Scope hint" value={String(query.filters.scope_hint ?? '')} placeholder="All scopes" options={['platform', 'tenant', 'company', 'department'].map(value => ({ value, label: labelKey(value) }))} onChange={value => query.setFilter('scope_hint', value || null)} />}
      </FilterBar>
      {query.q.length === 1 && <Notice tone="info">Enter at least two characters to apply the search. Other filters still apply.</Notice>}
      <DataTable caption={title + ' directory'} columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.display_name ?? row.name ?? singular}
        loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} sort={query.sort} onSortChange={query.setSort} filtered={query.filtered} onClearFilters={query.clearFilters}
        emptyTitle={query.filtered ? 'No matching ' + title.toLowerCase() : 'No ' + title.toLowerCase() + ' yet'} emptyBody={query.filtered ? 'Clear the search or filters to see other records.' : 'Records will appear here when added to this tenant.'} emptyAction={canCreate ? create : undefined}
        rowActions={row => [{ id: 'view', label: 'View details' }, ...(canEdit && !row.is_system && row.status !== 'deactivated' ? [{ id: 'edit', label: 'Edit details' }] : []), ...(resource === 'roles' && canCreate ? [{ id: 'clone', label: 'Clone role' }] : []),
          ...(resource === 'roles' ? [{ id: 'permissions', label: 'View role permissions', href: href('/' + row.id) + '#role-permissions' }] : []),
          ...(context.permissions.includes('role.read') ? [{ id: 'assignments', label: context.permissions.includes('role.assign') ? 'Manage role assignments' : 'View role assignments', href: administrationLink('/assignments?' + new URLSearchParams(resource === 'users' ? { subject_type: 'user', subject_id: row.id } : { role_id: row.id }), back) }] : []),
        ]}
        onAction={(action, row) => goTo(href('/' + row.id + (action === 'view' ? '' : '/' + action)))} />
      <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} noun={singular} />
    </Card>
  </div>;
}
