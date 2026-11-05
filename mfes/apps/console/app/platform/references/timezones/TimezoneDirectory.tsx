'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardHeader, DataTable, FilterBar, Notice, PageHeader, PageNavigation, Pager, Select, TableSearch, asErrorStatus, parseListQuery, useListQuery, type Column } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { platformCall, platformFailure, PlatformSignIn, type PlatformFailure } from '../../../lib/platform-api';

type Row = components['schemas']['TimezoneChoice'];
type Page = components['schemas']['Page_TimezoneChoice_'];
const empty: Page = { items: [], page: { has_more: false, next_cursor: null } };
export function TimezoneDirectory() {
  const base = '/platform/references/timezones';
  const [data, setData] = useState(empty), [loading, setLoading] = useState(true), [error, setError] = useState<PlatformFailure | null>(null), [revision, setRevision] = useState(0);
  const query = useListQuery({ initial: { sort: [{ key: 'code', direction: 'asc' }] }, meta: loading || error ? null : { ...data.page, limit: 50 }, onQueryChange: value => window.history.replaceState(null, '', base + (value ? '?' + value : '')) });
  const adopted = useRef(false), params = query.params.toString();
  useEffect(() => {
    if (adopted.current) return; adopted.current = true;
    const input = parseListQuery(new URLSearchParams(window.location.search), { filterKeys: ['status'] }), sort = input.sort.filter(item => ['code', 'name'].includes(item.key)).slice(0, 1);
    query.adopt({ ...input, q: input.q.length >= 2 && input.q.length <= 100 ? input.q : '', sort: sort.length ? sort : [{ key: 'code', direction: 'asc' }], filters: Object.fromEntries(Object.entries(input.filters).filter(([, value]) => ['active', 'archived'].includes(String(value)))) });
  }, [query.adopt]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null); setData(empty);
    platformCall<Page>('/v1/platform/references/timezones?' + params, 'GET', undefined, undefined, controller.signal)
      .then(page => { if (!controller.signal.aborted) { setData(page); setLoading(false); } })
      .catch(error => { if (!controller.signal.aborted) { setError(platformFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [params, revision]);
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  const columns: Column<Row>[] = [{ key: 'code', header: 'IANA identifier', type: 'code', sortable: true, locked: true }, { key: 'name', header: 'Name', sortable: true }, { key: 'is_active', header: 'Availability', type: 'boolean', words: ['Active', 'Archived'] }];
  return <div className="janso-page"><PageNavigation back={{ href: '/platform/references', label: 'reference data' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Reference data', href: '/platform/references' }, { label: 'Timezones' }]} />
    <PageHeader title="Timezones" lede="Browse the IANA timezone identifiers available for workspace, company and warehouse settings." />
    <Notice>Timezone identifiers and daylight-saving rules are maintained with the installed IANA data. UTC offsets depend on the date and are not editable reference fields.</Notice>
    <Card><CardHeader title="Timezone directory" /><FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...(query.filters.status ? [{ id: 'status', label: 'Availability', value: String(query.filters.status) }] : [])]} onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, null)} onClearAll={query.clearFilters} actions={<Button variant="ghost" disabled={loading} onClick={refresh}>Refresh</Button>}>
      <TableSearch label="Search timezones" value={query.q} onChange={query.setSearch} maxLength={100} busy={loading} placeholder="Search identifier or name" hint="Enter at least two characters, for example Asia or Europe." />
      <Select label="Availability" value={String(query.filters.status ?? '')} placeholder="All statuses" options={[{ value: 'active', label: 'Active' }, { value: 'archived', label: 'Archived' }]} onChange={value => query.setFilter('status', value || null)} />
    </FilterBar><DataTable caption="Timezone directory" columns={columns} rows={data.items} rowId={row => row.code} rowLabel={row => row.name} sort={query.sort} onSortChange={query.setSort} loading={loading} error={error ? asErrorStatus(error.status) : null} errorDetail={error ? <>{error.message}{error.status === 401 ? <PlatformSignIn returnTo={base + '?' + params} /> : null}</> : undefined} onRetry={error?.status === 403 ? undefined : refresh} filtered={query.filtered} onClearFilters={query.clearFilters} emptyTitle="No timezones available" emptyBody="The installation timezone catalogue is unavailable or has no matching entries. Check the installation data if clearing filters does not help." />
      <Pager count={loading || error ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={!error && query.page.hasPrevious} hasNext={!error && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} noun="timezone" nounPlural="timezones" />
    </Card></div>;
}
