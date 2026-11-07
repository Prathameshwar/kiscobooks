'use client';
import { masterLink, masterReturn } from '../lib/master-navigation';
import { inventoryBreadcrumbs, inventoryGroupForPath } from '../lib/inventory-navigation';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardHeader, DataTable, ErrorState, FilterBar, Notice, PageHeader, PageNavigation, Pager, Select, TableSearch, asErrorStatus, columnsFromFieldSet, parseListQuery, useListQuery, type Column } from '@janso/ui';
import { dimensions, kinds, masterLabel, type MasterConfig, type MasterField, type MasterRow } from '../lib/catalog-masters';
import { assertMasterFields, masterBase, masterRequest, type MasterPage } from '../lib/catalog-master-api';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { identifierReturn, identifierResources } from '../lib/units-identifiers';
import { IdentifierNavigation, type IdentifierAccess } from './UnitsIdentifiersCommon';

export function masterReturnTo(config: MasterConfig, value?: string) {
  const base = '/masters/' + config.resource;
  if (config.resource === 'units' && identifierResources.some(resource => value?.startsWith('/masters/' + resource))) return identifierReturn(value, base);
  try {
  if (value && new URL(value, 'https://console.invalid').pathname !== base) return masterReturn(value, base);
    if (!value || !value.startsWith(base) || value.includes('\\')) return base;
    const url = new URL(value, 'https://console.invalid');
    if (url.origin !== 'https://console.invalid' || url.pathname !== base || url.hash) return base;
    const query = parseListQuery(url.searchParams, { filterKeys: ['is_active', config.resource === 'units' ? 'dimension' : 'allowed_kind'] });
    const params = new URLSearchParams();
    if (query.q.length >= 2) params.set('q', query.q);
    params.set('limit', String(query.limit));
    const sort = query.sort.filter(item => ['code', 'name'].includes(item.key));
    if (sort.length) params.set('sort', (sort[0]!.direction === 'desc' ? '-' : '') + sort[0]!.key);
    for (const [key, options] of [['is_active', ['true', 'false']], ['dimension', dimensions], ['allowed_kind', kinds]] as const) {
      const filter = query.filters[key]; if (typeof filter === 'string' && (options as readonly string[]).includes(filter)) params.set(key, filter);
    }
    const parent = masterReturn(url.searchParams.get('returnTo') ?? undefined, '');
    if (parent) params.set('returnTo', parent);
    return base + '?' + params;
  } catch { return base; }
}
export function CatalogMasterError({ failure, retry, write = false }: { failure: RequestFailure | null; retry?: () => void; write?: boolean }) {
  if (!failure) return null;
  if (failure.status === 409 || failure.status === 422) return <Notice tone="danger">{failure.message}{failure.status === 409 ? ' Your changes are retained. Reload the record to review the latest values before saving again.' : ''}{retry ? <Button variant="ghost" onClick={retry}>Reload record</Button> : null}</Notice>;
  if (failure.status === 404) return <Notice tone="warning">This record was not found in the open company. Return to the directory to find an available record.</Notice>;
  if (write && failure.status >= 500) return <Notice tone="danger"><p>{failure.message}</p><p>The save could not be confirmed. Your values are retained. Retry without changing them to recover the same request.</p></Notice>;
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={retry && failure.status !== 401 && failure.status !== 403 ? <Button variant="ghost" onClick={retry}>Retry loading</Button> : undefined} />;
}
export function masterColumns(config: MasterConfig, fields: readonly MasterField[], href?: (row: MasterRow) => string): Column<MasterRow>[] {
  const listKeys = ['code', 'name', 'symbol', 'dimension', 'decimal_places', 'quantity_increment', 'allowed_kind', 'is_active', ...(config.resource === 'warehouses' ? ['kind', 'is_system', 'city', 'country_code', 'state_code'] : [])];
  return columnsFromFieldSet<MasterRow>(fields.filter(field => field.source === 'native' && field.visible && listKeys.includes(field.key)).map(field => ({ ...field, label: masterLabel(config, field) })), {
    sortable: ['code', 'name'], overrides: { name: href ? { type: 'link', href } : { type: 'text' }, code: { type: 'code' }, is_active: { type: 'boolean', header: 'Active', words: ['Active', 'Inactive'] }, decimal_places: { type: 'quantity', precision: 0 }, quantity_increment: { type: 'quantity', precision: 4 } },
  });
}
export function CatalogMasterDirectory({ company, config, canManage, initialQuery = '', canReadWarehouseGroups = false, canReadWarehouseBins = false, identifierAccess }: { company: string; config: MasterConfig; canManage: boolean; initialQuery?: string; canReadWarehouseGroups?: boolean; canReadWarehouseBins?: boolean; identifierAccess?: IdentifierAccess }) {
  const [warehouseCreateAllowed, setWarehouseCreateAllowed] = useState(false);
  const canCreate = canManage && (config.resource !== 'warehouses' || warehouseCreateAllowed);
  const [data, setData] = useState<MasterPage>({ items: [], page: { limit: 50, has_more: false, next_cursor: null } });
  const [fields, setFields] = useState<MasterField[]>([]), [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [accessMessage, setAccessMessage] = useState('');
  const root = '/masters/' + config.resource;
  const start = new URL(masterReturnTo(config, root + (initialQuery ? '?' + initialQuery : '')), 'https://console.invalid');
  const group = inventoryGroupForPath(root)!;
  const origin = masterReturn(start.searchParams.get('returnTo') ?? undefined, group.href);
  const address = (value: string) => masterLink(root + (value ? '?' + value : ''), origin);
  const initial = parseListQuery(start.searchParams, { filterKeys: ['is_active', config.resource === 'units' ? 'dimension' : 'allowed_kind'] });
  const query = useListQuery({ initial, meta: loading || failure ? null : data.page,
    onQueryChange: value => window.history.replaceState(null, '', address(value)) });
  const params = query.params.toString(), requestNumber = useRef(0);
  const back = address(query.queryString), href = (path: string) => masterLink(path, back);
  const create = <a className="janso-btn janso-btn--primary" href={href(root + '/new')}>New {config.singular}</a>;
  useEffect(() => {
    const controller = new AbortController(), number = ++requestNumber.current; setLoading(true); setFailure(null); setWarehouseCreateAllowed(false);
    masterRequest<import('../lib/catalog-masters').MasterFieldSet>({ path: `/v1/companies/${company}/entities/${config.entity}/field-set`, signal: controller.signal })
      .then(async metadata => {
        if (controller.signal.aborted || number !== requestNumber.current) return;
        const resolved = assertMasterFields(metadata, company, config.entity);
        setFields(resolved);
        if (config.resource === 'warehouses' && canManage) {
          const creation = await masterRequest<import('../lib/catalog-masters').MasterFieldSet>({ path: `/v1/companies/${company}/entities/${config.entity}/field-set?operation=create`, signal: controller.signal });
          if (controller.signal.aborted || number !== requestNumber.current) return;
          setWarehouseCreateAllowed(assertMasterFields(creation, company, config.entity).some(field => field.visible && field.writable && field.source === 'native'));
        }
        const available = new Set(resolved.filter(field => field.source === 'native' && field.visible).map(field => field.key));
        const requested = parseListQuery(new URLSearchParams(params), { filterKeys: ['is_active', config.resource === 'units' ? 'dimension' : 'allowed_kind'] });
        const allowed = { ...requested, q: available.has('code') && available.has('name') ? requested.q : '',
          sort: requested.sort.filter(item => available.has(item.key)), filters: Object.fromEntries(Object.entries(requested.filters).filter(([key]) => available.has(key))) };
        if (allowed.q !== requested.q || allowed.sort.length !== requested.sort.length || Object.keys(allowed.filters).length !== Object.keys(requested.filters).length) {
          setAccessMessage('Some search, filter or sort settings were removed because those fields are unavailable with your current access. The remaining records are shown.');
          query.adopt(allowed); return;
        }
        const page = await masterRequest<MasterPage>({ path: masterBase(company, config) + '?' + params, signal: controller.signal });
        if (controller.signal.aborted || number !== requestNumber.current) return;
        if (!Array.isArray(page.items) || !page.page) throw { status: 502, message: 'Unable to load the directory for this company.' };
        setData(page); setLoading(false);
      }).catch(error => { if (!controller.signal.aborted && number === requestNumber.current) { setData({ items: [], page: { limit: 50, has_more: false, next_cursor: null } }); setFailure(requestFailure(error, 'master service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, config, params, revision, query.adopt, canManage]);
  const refresh = () => { query.restart(); setRevision(value => value + 1); };
  const available = (key: string) => fields.some(field => field.source === 'native' && field.visible && field.key === key);
  return <div className="janso-page">
    {config.resource === 'units' && identifierAccess && <IdentifierNavigation title={config.title} back={origin} access={identifierAccess} />}
    {config.resource === 'warehouses' && <nav className="janso-page-navigation" aria-label="Warehouse structure">{canReadWarehouseGroups && <a className="janso-link" href="/masters/warehouse-groups">Warehouse groups</a>}{canReadWarehouseBins && <a className="janso-link" href="/masters/warehouse-bins">Bins / racks</a>}</nav>}
    {!(config.resource === 'units' && identifierAccess) && <PageNavigation back={{ href: origin, label: 'previous page' }} breadcrumbs={inventoryBreadcrumbs(group.key, config.title)} />}
    <PageHeader title={config.title} lede={`Find and maintain ${config.title.toLowerCase()} in the company currently open.`} actions={<>{config.resource === 'warehouses' ? <a className="janso-btn janso-btn--ghost" href={masterLink('/masters/warehouses/settings', back)}>Warehouse settings</a> : null}{canCreate ? create : null}</>} />
    {config.resource === 'warehouses' ? <Notice>Warehouses describe physical stock locations. Main is maintained by the system; internal transit is reserved for transfers. Stock quantities and movements are managed through their own workflows.</Notice> : null}
    {!canManage ? <Notice>Read-only access. Ask a company administrator if you need to maintain these records.</Notice> : null}
    {config.resource === 'warehouses' && canManage && !loading && !failure && !warehouseCreateAllowed ? <Notice>Creating additional warehouses requires inventory, multiple godowns and writable warehouse fields. Review company features and field access.</Notice> : null}
    {accessMessage ? <Notice tone="warning">{accessMessage}</Notice> : null}
    {failure?.fields?.cursor ? <Notice tone="warning">Your page position has expired. <Button variant="ghost" onClick={refresh}>Return to first page</Button></Notice> : null}
    <Card><CardHeader title={config.title + ' directory'} />
      <FilterBar applied={[...(query.q ? [{ id: 'q', label: 'Search', value: query.q }] : []), ...Object.entries(query.filters).map(([key, value]) => ({ id: key, label: key === 'is_active' ? 'Status' : key.replaceAll('_', ' '), value: key === 'is_active' ? value === 'true' ? 'Active' : 'Inactive' : String(value) }))]}
        onRemove={key => key === 'q' ? query.setSearch('') : query.setFilter(key, null)} onClearAll={query.clearFilters}
        actions={<Button variant="ghost" disabled={loading} onClick={refresh}>Refresh</Button>}>
        {available('code') && available('name') ? <TableSearch label={`Search ${config.title.toLowerCase()}`} value={query.q} onChange={query.setSearch} hint="Search by code or name (at least two characters)." busy={loading} /> : null}
        {available('is_active') ? <Select label="Status" value={String(query.filters.is_active ?? '')} placeholder="All statuses" options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]} onChange={value => query.setFilter('is_active', value || null)} /> : null}
        {(config.resource === 'units' || config.resource === 'item-groups') && available(config.resource === 'units' ? 'dimension' : 'allowed_kind') ? <Select label={config.resource === 'units' ? 'Dimension' : 'Allowed item kind'} value={String(query.filters[config.resource === 'units' ? 'dimension' : 'allowed_kind'] ?? '')} placeholder="All kinds"
          options={(config.resource === 'units' ? dimensions : kinds).map(value => ({ value, label: value }))} onChange={value => query.setFilter(config.resource === 'units' ? 'dimension' : 'allowed_kind', value || null)} /> : null}
      </FilterBar>
      <DataTable caption={config.title + ' directory'} columns={masterColumns(config, fields, row => href(root + '/' + row.id))} rows={data.items} rowId={row => row.id} rowLabel={row => row.name ?? row.code ?? config.singular}
        loading={loading} error={failure ? asErrorStatus(failure.status) : null} errorDetail={failure?.message} onRetry={refresh} sort={query.sort} onSortChange={query.setSort}
        filtered={query.filtered} onClearFilters={query.clearFilters} emptyTitle={query.filtered ? `No ${config.title.toLowerCase()} match these filters` : `No ${config.title.toLowerCase()} yet`} emptyBody={query.filtered ? 'Clear the search or filters to see other records in this company.' : canCreate ? `Create a ${config.singular} to start using it in this company.` : `Ask a company administrator to review features and access for ${config.title.toLowerCase()}.`} emptyAction={canCreate ? create : undefined}
        rowActions={row => [{ id: 'view', label: 'View details', href: href(root + '/' + row.id) }, ...(canManage ? [{ id: 'edit', label: 'Edit details', href: href(root + '/' + row.id + '/edit') }] : [])]} />
      <Pager count={loading || failure ? 0 : data.items.length} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={query.page.hasNext} onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={loading} noun={config.singular} nounPlural={config.title.toLowerCase()} />
    </Card>
  </div>;
}
