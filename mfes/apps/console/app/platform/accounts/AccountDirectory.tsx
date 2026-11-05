'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Badge, Card, CardHeader, DataTable, FilterBar, IconButton, Notice, PageHeader, PageNavigation, Pager, RefreshIcon, Select, TableSearch, useListQuery, parseListQuery, type Column, type ErrorStatus } from '@janso/ui';
import { platformCall, platformFailure, PlatformSignIn, type PlatformFailure } from '../../lib/platform-api';
import { goTo } from '../../lib/navigate';

type Account = components['schemas']['AccountReviewItem'];
type Result = components['schemas']['Page_AccountReviewItem_'];
const empty: Result = { items: [], page: { next_cursor: null, has_more: false } };
const columns: Column<Account>[] = [{ key: 'name', header: 'Name', sortable: true }, { key: 'username', header: 'Username', sortable: true },
  { key: 'email', header: 'Email', sortable: true }, { key: 'status', header: 'Review status', render: row => <Badge tone={row.needs_attention ? 'warn' : row.status === 'approved' ? 'success' : 'neutral'}>{row.needs_attention ? 'Needs attention' : row.status}</Badge> },
  { key: 'created_at', header: 'Received', type: 'datetime', sortable: true }];

export function AccountDirectory({permissions=[]}: {permissions?: readonly string[]}) {
  const initialImport = useRef<Promise<components['schemas']['AccountSyncResult']> | null>(null);
  const initialImportApplied = useRef(false);
  const [syncWarning, setSyncWarning] = useState('');
  const [nextImportPage,setNextImportPage] = useState<number | null>(null);
  const [data, setData] = useState<Result>(empty), [error, setError] = useState<PlatformFailure | null>(null), [loading, setLoading] = useState(true), [reload, setReload] = useState(0), [syncing, setSyncing] = useState(false);
  const query = useListQuery({ initial: { sort: [{ key: 'created_at', direction: 'desc' }] }, meta: loading ? null : {...data.page,limit:50}, onQueryChange: value => window.history.replaceState(null, '', '/platform/accounts' + (value ? '?' + value : '')) });
  useEffect(() => { const initial = parseListQuery(window.location.search, { filterKeys: ['status'] }); query.adopt({ ...initial, sort: initial.sort.length ? initial.sort : [{ key: 'created_at', direction: 'desc' }] }); }, [query.adopt]);
  const params = query.params.toString();
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    if (!initialImport.current) initialImport.current = platformCall('/v1/platform/accounts/sync?page=1', 'POST');
    initialImport.current.catch(value => {
      initialImport.current = null;
      if (!controller.signal.aborted) setSyncWarning('New registrations could not be checked. Showing saved records. ' + platformFailure(value).message);
      return null;
    }).then(result => {
      if (controller.signal.aborted) return empty;
      if (result && !initialImportApplied.current) { setNextImportPage(result.next_page); initialImportApplied.current = true; }
      return platformCall<Result>('/v1/platform/accounts?' + params, 'GET', undefined, undefined, controller.signal);
    })
      .then(value => { if (!controller.signal.aborted) { setData(value); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { initialImport.current = null; setData(empty); setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
  }, [params, reload]);
  async function refresh() {
    if (syncing) return; setSyncing(true); setError(null); setSyncWarning('');
    try {
      let page: number | null = nextImportPage ?? 1;
      // Each request is a bounded provider page. Avoid one unbounded blocking request.
      for (let count = 0; page && count < 20; count++) {
        const result: components['schemas']['AccountSyncResult'] = await platformCall('/v1/platform/accounts/sync?page=' + page, 'POST'); page = result.next_page;
      }
      setNextImportPage(page);
      query.restart(); setReload(value => value + 1);
    } catch (value) { setSyncWarning('New registrations could not be checked. Showing saved records. ' + platformFailure(value).message); } finally { setSyncing(false); }
  }
  const status = String(query.filters.status ?? '');
  return <div className="janso-page">
    <PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Account approvals' }]} />
    <a className="janso-link" href="/platform/history?entity_type=account_review">View account administration history</a>
    <PageHeader title="Account approvals" lede="Review new accounts and independently verify their identity and email before enabling sign-in." />
    <Notice>Approval creates the workspace and enables its administrator. Invitation registrations join their existing tenant. Account-ready details are emailed when configured, and manual sharing is always available.</Notice>
    {syncWarning ? <Notice tone="warning">{syncWarning}</Notice> : null}
    {nextImportPage ? <Notice>More registrations remain to be imported. Select Refresh accounts to continue.</Notice> : null}
    <Card><CardHeader title="Registration directory" subtitle="New registrations are checked when you open this page. Refresh to check again." />
      <FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...(status ? [{ id: 'status', label: 'Status', value: status }] : [])]} onRemove={id => id === 'q' ? query.setSearch('') : query.setFilter('status', null)} onClearAll={query.clearFilters}
        actions={<IconButton label="Refresh accounts" icon={<RefreshIcon />} onClick={refresh} disabled={syncing} aria-busy={syncing} />}>
        <TableSearch label="Search accounts" value={query.q} onChange={query.setSearch} maxLength={100} placeholder="Name, username or email" hint="Enter at least 2 characters. Matches the beginning." busy={loading} />
        <Select label="Review status" value={status} onChange={value => query.setFilter('status', value || null)} options={[{ value: '', label: 'All statuses' }, { value: 'pending', label: 'Pending' }, { value: 'approved', label: 'Approved' }, { value: 'rejected', label: 'Rejected' }]} />
      </FilterBar>
      <DataTable caption="Account registrations" columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.name} sort={query.sort} onSortChange={query.setSort} loading={loading || syncing}
        error={error ? ([401,403,422].includes(error.status) ? error.status as ErrorStatus : 500) : null} errorDetail={error ? <>{error.message}{error.status === 401 ? <PlatformSignIn returnTo="/platform/accounts" /> : null}</> : undefined}
        onRetry={error?.status === 403 ? undefined : () => setReload(value => value + 1)} filtered={query.filtered} onClearFilters={query.clearFilters} emptyTitle="No account registrations" emptyBody="Refresh to check for new registrations."
        rowActions={row => [{ id: 'view', label: 'View registration' }, ...(permissions.includes('platform.account.review') && row.status !== 'approved' && !row.needs_attention ? [{id:'review',label:row.status === 'rejected' ? 'Reopen registration' : 'Review account'}] : [])]} onAction={(_, row) => goTo(`/platform/accounts/${row.id}?returnTo=${encodeURIComponent('/platform/accounts?' + params)}`)} />
      <Pager noun="account" count={data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading || syncing} />
    </Card>
  </div>;
}
