'use client';
import { useState } from 'react';
import { Badge, Button, Card, DataTable, FilterBar, Notice, PageHeader, PageNavigation, Pager, useFormatters, type Column } from '@janso/ui';
import { useServiceList, useServiceRead } from '../lib/service-resource';
import { stockBase, stockRequest, useStockFields, verifyStockRow, type StockConfiguration, type StockRow, type StockView } from '../lib/stock';
import { trackingId } from '../lib/stock-tracking-resources';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { TrackingReference } from './StockTrackingCommon';
import { StockAccountConfiguration } from './StockAccountConfiguration';

const tabs = [{ value: 'cost-pools', label: 'Warehouse balances' }, { value: 'positions', label: 'Batches and locations' }, { value: 'movements', label: 'Stock movements' }, { value: 'account-policies', label: 'Stock accounts' }] as const;
export function StockDirectory({ company, view, initialQuery = '', canConfigure }: { company: string; view: StockView; initialQuery?: string; canConfigure: boolean }) {
  const [query, setQuery] = useState(new URLSearchParams(initialQuery)), metadata = useStockFields(company, view), format = useFormatters();
  const configuration = useServiceRead<StockConfiguration>(stockBase(company) + '/configuration', stockRequest);
  const allowed = (key: string) => metadata.data?.fields.some(field => field.key === key && field.readable && field.visible);
  const filters = new URLSearchParams({ sort: '-id' });
  for (const key of ['item_id', 'warehouse_id', 'bin_id', 'lot_id', 'posting_id']) if (allowed(key) && trackingId.test(query.get(key) ?? '')) filters.set(key, query.get(key)!);
  const list = useServiceList<StockRow>(stockBase(company) + '/' + view, filters.toString(), stockRequest, verifyStockRow, !!metadata.data && view !== 'account-policies');
  function href(target: StockView) { const params = new URLSearchParams(filters); params.delete('sort'); params.set('view', target); return '/inventory/stock?' + params; }
  const allColumns: Column<StockRow>[] = [
    { key: 'item_id', header: 'Product', type: 'custom', render: row => row.item_id ? <a className="janso-link" href={'/inventory/stock?item_id=' + row.item_id}>View stock</a> : 'Protected' },
    { key: 'warehouse_id', header: 'Warehouse', type: 'custom', render: row => row.warehouse_id ? <a className="janso-link" href={'/masters/warehouses/' + row.warehouse_id}>View warehouse</a> : 'Protected' },
    { key: 'lot_id', header: 'Batch', type: 'custom', render: row => row.lot_id ? 'Batch assigned' : 'No batch' },
    { key: 'quantity', header: view === 'movements' ? 'Quantity change' : 'On hand', type: 'custom', render: row => row.quantity == null ? 'Protected' : format.quantity(row.quantity) },
    { key: 'value', header: view === 'movements' ? 'Value change' : 'Carrying value', type: 'custom', render: row => row.value == null || !row.currency ? 'Protected' : format.money(row.value, { display: 'none' }) + ' ' + row.currency },
    { key: 'method', header: 'Cost method', type: 'custom', render: row => row.method === 'MOVING_AVERAGE' ? 'Moving average' : row.method === 'FIFO' ? 'FIFO' : 'Protected' },
    { key: 'stock_date', header: 'Stock date', type: 'custom', render: row => row.stock_date ? format.date(row.stock_date) : 'Protected' },
    { key: 'custody_kind', header: 'Location', type: 'custom', render: row => <Badge tone={row.custody_kind === 'TRANSIT' ? 'warn' : 'neutral'}>{row.custody_kind === 'TRANSIT' ? 'In transit' : row.custody_kind === 'WAREHOUSE' ? 'In warehouse' : 'Protected'}</Badge> },
  ];
  const columns = allColumns.filter(column => allowed(column.key) && (column.key !== 'value' || allowed('currency')));
  return <div className="janso-page">
    <PageNavigation back={{ href: '/masters', label: 'Masters' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Masters', href: '/masters' }, { label: 'Stock' }]} />
    <PageHeader title="Stock" lede="Review physical quantities, warehouse costs and the movement history for this company." />
    <a className="janso-link" href="/inventory/stock/opening">Product opening stock</a>
    <nav className="janso-tabs" aria-label="Stock views">{tabs.map(tab => <a key={tab.value} className="janso-tabs__tab" href={href(tab.value)} aria-current={view === tab.value ? 'page' : undefined}>{tab.label}</a>)}</nav>
    <AccountingFailure failure={metadata.failure ?? configuration.failure ?? list.failure} retry={() => { metadata.refresh(); configuration.refresh(); list.first(); }} />
    {configuration.data && !configuration.data.posting_enabled && <Notice tone="warning">Stock posting is awaiting installation activation. Prepared batches and serials have no on-hand quantity until a stock voucher is posted.</Notice>}
    {view === 'account-policies' ? <StockAccountConfiguration company={company} canConfigure={canConfigure && !!configuration.data?.can_configure} generation={configuration.data?.generation} correctablePolicyId={configuration.data?.correctable_policy_id} onSaved={configuration.refresh} /> : <Card>
      <FilterBar>{allowed('item_id') && <TrackingReference company={company} resource="items" label="Product filter" value={query.get('item_id')} onChange={value => setQuery(current => { const next = new URLSearchParams(current); if (value) next.set('item_id', value); else next.delete('item_id'); return next; })} />}
        <Button variant="ghost" onClick={() => setQuery(new URLSearchParams())}>Clear filters</Button><Button variant="ghost" onClick={list.first}>Refresh</Button>
      </FilterBar>
      <DataTable caption={tabs.find(tab => tab.value === view)!.label} columns={columns} rows={list.data?.items ?? []} rowId={row => row.id} rowLabel={() => 'Stock record'} loading={metadata.loading || list.loading} filtered={query.size > 0} emptyTitle="No posted stock found" emptyBody="Post an approved stock voucher to record physical quantities and carrying value." onClearFilters={() => setQuery(new URLSearchParams())} />
      <Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun="stock record" />
    </Card>}
  </div>;
}
