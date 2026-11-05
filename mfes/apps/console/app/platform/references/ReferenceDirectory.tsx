'use client';
import { useEffect, useRef, useState } from 'react';
import { Card, CardHeader, DataTable, FilterBar, IconButton, PageHeader, PageNavigation, Pager, RefreshIcon, SearchSelect, Select, TableSearch, useListQuery, parseListQuery, type Column, type ErrorStatus, type MenuItem } from '@janso/ui';
import { platformCall as call, platformFailure, PlatformSignIn } from '../../lib/platform-api';
import type { PlatformFailure } from '../../lib/platform-api';
import { goTo } from '../../lib/navigate';
import { catalogConfig, type Catalog, type ReferenceItem, type ReferenceOptions, type ReferencePage } from './reference-config';

const empty: ReferencePage = { items: [], page: { next_cursor: null, has_more: false } };
export function ReferenceDirectory({ catalog }: { catalog: Catalog }) {
  const config = catalogConfig[catalog], base = '/platform/references/' + catalog;
  const [data, setData] = useState(empty), [loading, setLoading] = useState(true), [error, setError] = useState<PlatformFailure | null>(null), [reload, setReload] = useState(0);
  const [options, setOptions] = useState<ReferenceOptions>({ countries: [], currencies: [] });
  const query = useListQuery({ initial: { sort: [{ key: 'name', direction: 'asc' }] }, meta: loading || error ? null : { ...data.page, limit: 50 }, onQueryChange: value => window.history.replaceState(null, '', base + (value ? '?' + value : '')) });
  const adopted = useRef(false);
  useEffect(() => { if (adopted.current) return; adopted.current = true;
    const input = parseListQuery(new URLSearchParams(window.location.search), { filterKeys: catalog === 'states' ? ['status', 'country_code'] : ['status'] });
    const sort = input.sort.filter(item => ['name', 'code'].includes(item.key)).slice(0, 1);
    query.adopt({ ...input, q: input.q.trim().length >= 2 && input.q.length <= 100 ? input.q : '', sort: sort.length ? sort : [{ key: 'name', direction: 'asc' }], filters: Object.fromEntries(Object.entries(input.filters).filter(([key, value]) => key === 'status' ? ['active', 'archived'].includes(String(value)) : /^[A-Z]{2}$/.test(String(value)))) });
  }, [catalog, query.adopt]);
  const params = query.params.toString();
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    Promise.all([call<ReferencePage>('/v1/platform/references/' + catalog + '?' + params, 'GET', undefined, undefined, controller.signal), catalog === 'states' ? call<ReferenceOptions>('/v1/platform/references/options', 'GET', undefined, undefined, controller.signal) : Promise.resolve({ countries: [], currencies: [] })])
      .then(([rows, choices]) => { if (!controller.signal.aborted) { setData(rows); setOptions(choices); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setData(empty); setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [catalog, params, reload]);
  const href = (path: string) => path + '?returnTo=' + encodeURIComponent(base + '?' + params);
  const create = <a className="janso-btn janso-btn--primary" href={href(base + '/new')}>New {config.singular}</a>;
  const status = String(query.filters.status ?? ''), country = String(query.filters.country_code ?? '');
  const columns: Column<ReferenceItem>[] = [{ key: 'name', header: 'Name', sortable: true, locked: true }, { key: 'code', header: catalog === 'states' ? 'State code (GST for India)' : 'Code', type: 'code', value: row => row.display_code ?? row.code, sortable: catalog !== 'states' }, ...(catalog === 'states' ? [{ key: 'parent_code', header: 'Country', value: (row: ReferenceItem) => options.countries.find(item => item.code === row.parent_code)?.name ?? row.parent_code }] : []), { key: 'is_active', header: 'Status', type: 'status', value: row => row.is_active ? 'active' : 'archived', label: value => value === 'active' ? 'Active' : 'Archived', tone: value => value === 'active' ? 'success' : 'neutral' }];
  function actions(row: ReferenceItem): MenuItem[] { return [{ id: 'view', label: 'View details' }, { id: 'edit', label: 'Edit details' }, ...(catalog === 'countries' ? [{ id: 'states', label: 'Manage states' }] : []), { id: row.is_active ? 'archive' : 'restore', label: row.is_active ? 'Delete (archive)' : 'Restore', destructive: row.is_active }]; }
  return <div className="janso-page">
    <PageNavigation back={{ href: '/platform/references', label: 'reference data' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Reference data', href: '/platform/references' }, { label: config.title }]} />
    <a className="janso-link" href="/platform/history?entity_type=reference_revision">View reference administration history</a>
    <PageHeader title={config.title} lede={config.description} actions={create} />
    <Card><CardHeader title={config.title + ' directory'} subtitle="Reference changes are audited. Delete archives a record and preserves its history." />
      <FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...(status ? [{ id: 'status', label: 'Status', value: status }] : []), ...(country ? [{ id: 'country_code', label: 'Country', value: country }] : [])]} onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, null)} onClearAll={query.clearFilters} actions={<IconButton label={'Refresh ' + catalog} icon={<RefreshIcon />} disabled={loading} onClick={() => { query.restart(); setReload(value => value + 1); }} />}>
        <TableSearch value={query.q} onChange={query.setSearch} label={'Search ' + catalog} placeholder="Search name or code" maxLength={100} hint={catalog === 'states' ? 'Search by name, GST state code (for example 27), or ISO reference.' : 'Enter at least 2 characters. Matches the beginning of a name or code.'} busy={loading} />
        {catalog === 'states' ? <SearchSelect label="Country" placeholder="All countries" value={country || null} scopeKey="reference-states-countries" selected={country ? { id: country, label: options.countries.find(item => item.code === country)?.name ?? country + ' (unavailable)' } : null} onChange={value => query.setFilter('country_code', value || null)} options={options.countries.map(row => ({ id: row.code, label: row.name, meta: row.code }))} /> : null}
        <Select label="Status" value={status} onChange={value => query.setFilter('status', value || null)} options={[{ value: '', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'archived', label: 'Archived' }]} />
      </FilterBar>
      <DataTable caption={config.title} columns={columns} rows={data.items} rowId={row => row.code} rowLabel={row => row.name} sort={query.sort} onSortChange={query.setSort} loading={loading} error={error ? ([401, 403, 422].includes(error.status) ? error.status as ErrorStatus : 500) : null} errorDetail={error ? <>{error.message}{error.status === 401 ? <PlatformSignIn returnTo={base + '?' + params} /> : null}</> : undefined} onRetry={error?.status === 403 ? undefined : () => { query.restart(); setReload(value => value + 1); }} filtered={query.filtered} emptyTitle={'No ' + catalog + ' yet'} emptyBody={'Add a ' + config.singular + ' reference to get started.'} emptyAction={create} onClearFilters={query.clearFilters} rowActions={actions} onAction={(id, row) => goTo(id === 'states' ? '/platform/references/states?country_code=' + encodeURIComponent(row.code) : href(base + '/' + row.code + (id === 'edit' ? '/edit' : '')) + (['archive', 'restore'].includes(id) ? '&action=' + id : ''))} />
      <Pager noun={config.singular} count={data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={!error && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} />
    </Card>
  </div>;
}
