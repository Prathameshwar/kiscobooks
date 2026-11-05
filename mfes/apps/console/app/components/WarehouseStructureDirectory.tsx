'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardHeader, DataTable, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, type Column } from '@janso/ui';
import { masterBase, masterRequest } from '../lib/catalog-master-api';
import type { MasterConfig, MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import { structureLink, structureReturn, structureTitle, structureVisible, useStructureFields } from '../lib/warehouse-structure';
import { goTo } from '../lib/navigate';
import { masterColumns } from './CatalogMasterDirectory';
import { StructureFailure, StructureNavigation, StructureReference, StructureReferenceLabel, type StructureAccess } from './WarehouseStructureCommon';

export function WarehouseStructureDirectory({ company, config, canManage, access, initialQuery = '' }: { company: string; config: MasterConfig; canManage: boolean; access: StructureAccess; initialQuery?: string }) {
  const root = '/masters/' + config.resource, initial = new URL(structureReturn(root + '?' + initialQuery, root), 'https://console.invalid');
  const [query, setQuery] = useState(new URLSearchParams(initial.search)), metadata = useStructureFields(company, config.entity), fields = metadata.data?.fields ?? [], available = (key: string) => structureVisible(fields, key);
  const filters = new URLSearchParams();
  if (available('code') && available('name') && query.get('q')) filters.set('q', query.get('q')!);
  if (available('is_active') && query.get('is_active')) filters.set('is_active', query.get('is_active')!);
  if (config.resource === 'warehouse-bins' && available('warehouse_id') && query.get('warehouse_id')) filters.set('warehouse_id', query.get('warehouse_id')!);
  const sort = query.get('sort') ?? '-id'; if (sort.endsWith('id') || available(sort.replace(/^-/, ''))) filters.set('sort', sort);
  const list = useServiceList<MasterRow>(masterBase(company, config), filters.toString(), masterRequest);
  useEffect(() => { if (initial.searchParams.get('limit')) list.setLimit(Number(initial.searchParams.get('limit'))); }, [company, config.resource]);
  const here = root + (query.size ? '?' + query : '');
  useEffect(() => { window.history.replaceState(null, '', here); }, [here]);
  function change(key: string, value: string) { setQuery(current => { const next = new URLSearchParams(current); if (value) next.set(key, value); else next.delete(key); return next; }); }
  function clearFilters() { setQuery(new URLSearchParams(query.has('returnTo') ? { returnTo: query.get('returnTo')! } : {})); }
  const columns: Column<MasterRow>[] = masterColumns(config, fields.filter(field => !field.conditional_access), row => structureLink(root + '/' + row.id, here));
  if (config.resource === 'warehouse-bins' && available('warehouse_id')) columns.push({ key: 'warehouse', header: 'Warehouse', type: 'custom', render: row => access.warehouses && typeof row.warehouse_id === 'string' ? <StructureReferenceLabel company={company} resource="warehouses" id={row.warehouse_id} here={here} /> : 'Protected' });
  if (!columns.length) columns.push({ key: 'record', header: 'Record', type: 'custom', render: row => <a className="janso-link" href={structureLink(root + '/' + row.id, here)}>View record</a> });
  return <div className="janso-page"><StructureNavigation title={config.title} access={access} back={query.get('returnTo') ?? undefined} /><PageHeader title={config.title} lede={config.resource === 'warehouse-groups' ? 'Organize warehouses into dated reporting hierarchies.' : 'Maintain bins, racks and shelves within a warehouse.'} actions={canManage && <a className="janso-btn janso-btn--primary" href={structureLink(root + '/new' + (filters.get('warehouse_id') ? '?warehouse_id=' + filters.get('warehouse_id') : ''), here)}>New {config.singular}</a>} />{!canManage && <Notice>Read-only access.</Notice>}<StructureFailure failure={metadata.failure ?? list.failure} retry={() => { metadata.refresh(); list.first(); }} />
    <Card><CardHeader title={config.title + ' directory'} /><FilterBar applied={[...filters].filter(([key]) => key !== 'sort').map(([id, value]) => ({ id, label: id === 'q' ? 'Search' : id === 'warehouse_id' ? 'Warehouse' : 'Status', value: id === 'warehouse_id' ? 'Selected warehouse' : value === 'true' ? 'Active' : value === 'false' ? 'Inactive' : value }))} onRemove={key => change(key, '')} onClearAll={clearFilters} actions={<Button variant="ghost" onClick={list.first} disabled={list.loading}>Refresh</Button>}>
      {available('code') && available('name') && <TableSearch label={'Search ' + config.title.toLowerCase()} value={query.get('q') ?? ''} onChange={value => change('q', value.trim().length >= 2 ? value : '')} hint="At least two characters; search by code or name." />}{available('is_active') && <Select label="Status" placeholder="All statuses" value={query.get('is_active') ?? ''} options={[{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }]} onChange={value => change('is_active', value)} />}{config.resource === 'warehouse-bins' && available('warehouse_id') && access.warehouses && <StructureReference company={company} resource="warehouses" label="Filter by warehouse" value={query.get('warehouse_id')} onChange={value => change('warehouse_id', value ?? '')} activeOnly={false} />}
      <Select label="Sort" value={filters.get('sort') ?? '-id'} options={[{ value: '-id', label: 'Newest first' }, { value: 'id', label: 'Oldest first' }, ...(available('code') ? [{ value: 'code', label: 'Code A to Z' }, { value: '-code', label: 'Code Z to A' }] : []), ...(available('name') ? [{ value: 'name', label: 'Name A to Z' }, { value: '-name', label: 'Name Z to A' }] : [])]} onChange={value => change('sort', value)} />
    </FilterBar><DataTable caption={config.title + ' directory'} columns={columns} rows={list.data?.items ?? []} rowId={row => row.id} rowLabel={structureTitle} loading={metadata.loading || list.loading} filtered={filters.size > 1} emptyTitle={'No ' + config.title.toLowerCase() + ' found'} emptyBody="Create a record or clear the filters." onClearFilters={clearFilters} rowActions={() => [{ id: 'view', label: 'View details' }, ...(canManage ? [{ id: 'edit', label: 'Edit details' }] : [])]} onAction={(action, row) => goTo(structureLink(root + '/' + row.id + (action === 'edit' ? '/edit' : ''), here))} /><Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={value => { list.setLimit(value); change('limit', String(value)); }} noun={config.singular} /></Card></div>;
}
