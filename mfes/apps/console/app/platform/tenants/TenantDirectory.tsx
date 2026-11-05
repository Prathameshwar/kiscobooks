'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardHeader, DataTable, Drawer, FilterBar, IconButton, Notice, PageHeader, Pager, RefreshIcon,
  PageNavigation, ReviewList, Select, TableSearch, useListQuery, parseListQuery, type Column, type ErrorStatus, type MenuItem } from '@janso/ui';
import { goTo } from '../../lib/navigate';
import { platformCall as call, platformFailure as failure, PlatformSignIn as SignInAgain, PlatformError as RequestError, type PlatformFailure as Failure } from '../../lib/platform-api';
import { TenantLifecycleDialog } from './TenantLifecycleDialog';

type Tenant = components['schemas']['PlatformTenantItem'];
type Detail = components['schemas']['PlatformTenantDetail'];
type TenantPage = components['schemas']['Page_PlatformTenantItem_'];
const empty: TenantPage = { items: [], page: { has_more: false, next_cursor: null } };
const columns: readonly Column<Tenant>[] = [
  { key: 'name', header: 'Tenant', sortable: true, locked: true },
  { key: 'status', header: 'Status', type: 'status', label: value => value.charAt(0).toUpperCase() + value.slice(1),
    tone: value => value === 'active' ? 'success' : value === 'suspended' ? 'warn' : 'neutral' },
  { key: 'created_at', header: 'Created', type: 'datetime', sortable: true },
];

export function TenantDirectory({ permissions, ownTenantId }: { permissions: readonly string[]; ownTenantId?: string }) {
  const [data, setData] = useState<TenantPage>(empty);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<Failure | null>(null);
  const [reload, setReload] = useState(0);
  const query = useListQuery({ initial: { sort: [{ key: 'name', direction: 'asc' }] }, meta: loading ? null : { ...data.page, limit: 50 },
    onQueryChange: value => window.history.replaceState(null, '', '/platform/tenants' + (value ? '?' + value : '')) });
  const adopted = useRef(false);
  useEffect(() => {
    if (adopted.current) return; adopted.current = true;
    const fromUrl = parseListQuery(new URLSearchParams(window.location.search), { filterKeys: ['status'] });
    query.adopt({ ...fromUrl, sort: fromUrl.sort.length ? fromUrl.sort : [{ key: 'name', direction: 'asc' }] });
  }, [query.adopt]);
  const params = query.params.toString();
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setLoadError(null);
    call<TenantPage>('/v1/platform/tenants?' + params, 'GET', undefined, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setLoading(false); } })
      .catch(error => { if (!controller.signal.aborted) { setData(empty); setLoadError(failure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [params, reload]);
  const [panel, setPanel] = useState<'view' | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<Failure | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [lifecycle, setLifecycle] = useState<Tenant | null>(null);
  const canCreate = permissions.includes('platform.tenant.create');
  const canEdit = permissions.includes('platform.config.manage');
  const canSuspend = permissions.includes('platform.tenant.suspend');
  const refresh = () => { query.restart(); setReload(value => value + 1); };
  const formHref = (path: string) => path + '?returnTo=' + encodeURIComponent('/platform/tenants' + (params ? '?' + params : ''));
  const newTenant = <a className="janso-btn janso-btn--primary" href={formHref('/platform/tenants/new')}>New tenant</a>;
  async function action(id: string, row: Tenant) {
    if (pending) return;
    if (id === 'view') { goTo(formHref(`/platform/tenants/${row.id}`)); return; }
    if (id === 'edit') { goTo(formHref(`/platform/tenants/${row.id}/edit`)); return; }
    if (id === 'administrators') { goTo('/platform/access/administrators?tenant=' + row.id); return; }
    setActionError(null); setMessage(null);
    if (id === 'suspend' || id === 'restore') { setLifecycle(row); return; }
    setPanel('view'); setDetail(null); setPending(true);
    try { setDetail(await call<Detail>(`/v1/platform/tenants/${row.id}`)); }
    catch (error) { setActionError(failure(error)); } finally { setPending(false); }
  }
  function rowActions(row: Tenant): MenuItem[] {
    const actions: MenuItem[] = [{ id: 'view', label: 'View details' }];
    if (permissions.includes('platform.tenant_access.read') && row.id !== ownTenantId) actions.push({ id: 'administrators', label: 'Manage tenant administrators' });
    if (canEdit && row.status !== 'closed') actions.push({ id: 'edit', label: 'Edit details' });
    if (canSuspend && row.status !== 'closed') actions.push({ id: row.status === 'active' ? 'suspend' : 'restore', label: row.status === 'active' ? 'Deactivate tenant' : 'Activate tenant',
      destructive: row.status === 'active', disabledReason: row.id === ownTenantId ? 'Your operating workspace cannot be suspended.' : undefined });
    return actions;
  }
  const errorStatus: ErrorStatus | null = loadError ? ([401, 403, 422].includes(loadError.status) ? loadError.status as ErrorStatus : 500) : null;
  const status = String(query.filters.status ?? '');
  return <div className="janso-page">
    <PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants' }]} />
    <a className="janso-link" href="/platform/history?entity_type=tenant">View tenant administration history</a>
    <PageHeader title="Tenants" lede="Manage workspace details and administrator access across your platform."
      actions={canCreate ? newTenant : undefined} />
    {message ? <Notice tone="success">{message}</Notice> : null}
    <Card>
      <CardHeader title="Tenant directory" subtitle="Find tenants and manage workspace access. All changes are audited." />
      <FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...(status ? [{ id: 'status', label: 'Status', value: status }] : [])]}
        onRemove={id => id === 'q' ? query.setSearch('') : query.setFilter('status', null)} onClearAll={query.clearFilters}
        actions={<IconButton label="Refresh tenants" icon={<RefreshIcon />} onClick={() => setReload(value => value + 1)} disabled={loading} aria-busy={loading} />}>
        <TableSearch value={query.q} onChange={query.setSearch} maxLength={100} label="Search tenants" placeholder="Search tenant name" hint="Enter at least 2 characters. Matches the beginning of the name." busy={loading} />
        <Select label="Status" value={status} onChange={value => query.setFilter('status', value || null)} options={[
          { value: '', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'suspended', label: 'Suspended' }, { value: 'closed', label: 'Closed' }]} />
      </FilterBar>
      <DataTable caption="Platform tenants" columns={columns} rows={data.items} rowId={row => row.id} rowLabel={row => row.name}
        sort={query.sort} onSortChange={query.setSort} loading={loading} error={errorStatus}
        errorDetail={loadError ? <>{loadError.message}{loadError.status === 401 ? <> <SignInAgain /></> : null}</> : undefined}
        onRetry={loadError?.status === 403 ? undefined : () => { query.restart(); setReload(value => value + 1); }}
        filtered={query.filtered} emptyTitle="No tenants yet" emptyBody="Create a workspace with its first administrator ready to sign in."
        emptyAction={canCreate ? newTenant : undefined} onClearFilters={query.clearFilters}
        rowActions={rowActions} onAction={action} />
      <Pager noun="tenant" count={data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious}
        hasNext={!loadError && query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} />
    </Card>
    <Drawer open={panel !== null} title="Tenant details" busy={pending} onClose={() => setPanel(null)} size="md"
      footer={<Button variant="ghost" disabled={pending} onClick={() => setPanel(null)}>Close</Button>}>
      <RequestError value={actionError} />
      {pending && !detail ? <p role="status">Loading tenant details…</p> : null}
      {detail ? <ReviewList items={[
        { label: 'Tenant', value: detail.name }, { label: 'Status', value: detail.status }, { label: 'Primary contact', value: detail.primary_contact_email },
        { label: 'Country', value: detail.default_country_code }, { label: 'Currency', value: detail.default_currency_code },
        { label: 'Timezone', value: detail.default_timezone }, { label: 'Language', value: detail.default_locale },
        ...(detail.default_state_code ? [{ label: 'State', value: detail.default_state_code }] : []),
        ...(detail.suspended_reason ? [{ label: 'Suspension reason', value: detail.suspended_reason }] : []),
      ]} /> : null}
    </Drawer>
    {lifecycle && <TenantLifecycleDialog tenant={lifecycle} returnTo={'/platform/tenants' + (params ? '?' + params : '')}
      onClose={() => setLifecycle(null)} onChanged={value => { setMessage(value); refresh(); }} onReview={refresh} />}
  </div>;
}
