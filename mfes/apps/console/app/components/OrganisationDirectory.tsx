'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardHeader, DataTable, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, asErrorStatus, parseListQuery, useListQuery, type Column } from '@janso/ui';
import { accessCall, type AccessContext, type AccessPageData } from '../lib/access-directory';
import { organisationBase, organisationPermission, organisationReturn, organisationTitle, type OrganisationRow, type OrganisationResource } from '../lib/organisation-ui';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { goTo } from '../lib/navigate';
import { AccessNavigation } from './AccessCommon';

export function OrganisationDirectory({ resource, context, initialQuery = '' }: { resource: OrganisationResource; context: AccessContext; initialQuery?: string }) {
  const title = organisationTitle(resource), base = '/' + resource;
  const initialParams = new URL(organisationReturn(resource, base + '?' + initialQuery), 'https://console.invalid').searchParams;
  if (!initialParams.has('sort')) initialParams.set('sort', resource === 'departments' ? 'path' : 'code');
  const initial = parseListQuery(initialParams, { filterKeys: ['is_active'] });
  const [data, setData] = useState<AccessPageData<OrganisationRow>>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const query = useListQuery({ initial, meta: loading || failure ? null : data.page, onQueryChange: value => window.history.replaceState(null, '', base + (value ? '?' + value : '')) });
  const params = query.params.toString(), canCreate = organisationPermission(context, resource, 'manage'), back = base + (query.queryString ? '?' + query.queryString : '');
  const href = (suffix: string) => base + suffix + '?returnTo=' + encodeURIComponent(back), create = <a className="janso-btn janso-btn--primary" href={href('/new')}>{resource === 'departments' ? 'New department' : 'New user group'}</a>;
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null);
    const search = new URLSearchParams(params); if ((search.get('q') ?? '').length < 2) search.delete('q');
    accessCall<AccessPageData<OrganisationRow>>({ path: organisationBase(resource, context) + '?' + search, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (!Array.isArray(result.items) || !result.page) throw { status: 502, message: 'Unexpected directory response.' };
      setData(result); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setData({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }); setFailure(requestFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [resource, context.companyId, context.tenantId, params, revision]);
  const columns: Column<OrganisationRow>[] = [
    { key: 'code', header: 'Code', type: 'code', sortable: true }, { key: 'name', header: 'Name', type: 'link', href: row => href('/' + row.id) },
    ...(resource === 'departments' ? [{ key: 'parent_id', header: 'Level', type: 'text' as const, value: (row: OrganisationRow) => 'parent_id' in row && row.parent_id ? 'Child department' : 'Root department' }] : []),
    { key: 'is_active', header: 'Status', type: 'text', value: row => row.is_active ? 'Active' : 'Inactive' },
  ];
  return <div className="janso-page"><AccessNavigation context={context} resource={resource} /><PageHeader title={title} lede={resource === 'departments' ? 'Departments in ' + (context.companyName ?? 'the selected company') + '. Parent changes affect department-scoped access.' : 'Tenant-wide collections of users. Group membership can grant permissions through separately reviewed role assignments.'} actions={canCreate ? create : undefined} />
    {resource === 'departments' && !canCreate && <Notice>Department-scoped administrators can add children from an authorized department’s detail page.</Notice>}
    <Card><CardHeader title={title + ' directory'} /><FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Code', value: query.q }] : []), ...(query.filters.is_active ? [{ id: 'is_active', label: 'Status', value: query.filters.is_active === 'true' ? 'Active' : 'Inactive' }] : [])]} onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, null)} onClearAll={query.clearFilters} actions={<Button type="button" variant="ghost" onClick={refresh} disabled={loading}>Refresh</Button>}>
      <TableSearch label={'Search ' + title.toLowerCase()} value={query.q} onChange={value => query.setSearch(value.slice(0, resource === 'departments' ? 20 : 40))} hint="Search by code prefix; enter at least two characters." busy={loading} />
      <Select label="Status" value={String(query.filters.is_active ?? '')} placeholder="All statuses" options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]} onChange={value => query.setFilter('is_active', value || null)} />
    </FilterBar>{query.q.length === 1 && <Notice>Enter at least two characters to apply the code search.</Notice>}
      <DataTable caption={title + ' directory'} columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.name} loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} sort={query.sort} onSortChange={query.setSort} filtered={query.filtered} onClearFilters={query.clearFilters} emptyTitle={'No ' + title.toLowerCase() + (query.filtered ? ' match' : ' yet')} emptyBody={query.filtered ? 'Clear the search or filters to see other records.' : canCreate ? 'Add the first record to get started.' : 'Ask an authorized administrator to add records.'} emptyAction={canCreate ? create : undefined}
        rowActions={row => [{ id: 'view', label: 'View details' }, ...(organisationPermission(context, resource, 'manage', row) && (resource === 'user-groups' || row.is_active) ? [{ id: 'edit', label: 'Edit details' }] : [])]} onAction={(action, row) => goTo(href('/' + row.id + (action === 'edit' ? '/edit' : '')))} />
      <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} noun={resource === 'departments' ? 'department' : 'group'} />
    </Card>
  </div>;
}
