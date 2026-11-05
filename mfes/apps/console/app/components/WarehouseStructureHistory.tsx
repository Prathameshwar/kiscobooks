'use client';
import { useState } from 'react';
import { Card, CardHeader, DataTable, Pager, TextField, useFormatters, type Column } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { masterConfig, validMasterDate, type MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import { structureBase, structureLink, structureVisible, useStructureContext, useStructureFields } from '../lib/warehouse-structure';
import { masterColumns } from './CatalogMasterDirectory';
import { StructureFailure, StructureReferenceLabel, type StructureAccess } from './WarehouseStructureCommon';

export function WarehouseStructureHistory({ company, id, assignment = false, here }: { company: string; id: string; assignment?: boolean; here: string }) {
  const metadata = useStructureFields(company, assignment ? 'catalog.warehouse_group_assignment' : 'catalog.warehouse_group_parent'), fields = metadata.data?.fields ?? [], format = useFormatters();
  const list = useServiceList<MasterRow>(structureBase(company, (assignment ? 'warehouses/' : 'warehouse-groups/') + id + (assignment ? '/group-history' : '/parents')), 'sort=-id', masterRequest);
  const target = assignment ? 'group_id' : 'parent_group_id';
  const columns: Column<MasterRow>[] = [target, 'valid_from', 'valid_to'].filter(key => structureVisible(fields, key)).map(key => ({ key, header: key === target ? assignment ? 'Primary group' : 'Parent group' : key === 'valid_from' ? 'Effective from' : 'Effective through', type: 'custom', render: row => key === target ? typeof row[key] === 'string' ? <StructureReferenceLabel company={company} resource="warehouse-groups" id={String(row[key])} here={here} /> : 'Top level' : row[key] ? format.date(String(row[key])) : key === 'valid_to' ? 'Open ended' : 'Protected' }));
  if (!columns.length) columns.push({ key: 'record', header: 'History', type: 'custom', render: () => 'Fields protected' });
  return <Card><CardHeader title={assignment ? 'Primary group history' : 'Parent group history'} /><StructureFailure failure={metadata.failure ?? list.failure} retry={() => { metadata.refresh(); list.first(); }} /><DataTable caption={assignment ? 'Primary group history' : 'Parent group history'} columns={columns} rows={list.data?.items ?? []} rowId={row => row.id} loading={metadata.loading || list.loading} emptyTitle={assignment ? 'No primary group history' : 'No readable parent history'} /><Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun="interval" /></Card>;
}
function StructureRelatedList({ company, id, members, date, here }: { company: string; id: string; members: boolean; date: string; here: string }) {
  const config = masterConfig(members ? 'warehouses' : 'warehouse-groups')!, metadata = useStructureFields(company, config.entity), fields = metadata.data?.fields ?? [];
  const list = useServiceList<MasterRow>(structureBase(company, 'warehouse-groups/' + id + (members ? '/members' : '/children')), new URLSearchParams({ valid_at: date }).toString(), masterRequest);
  let columns = masterColumns(config, fields.filter(field => !field.conditional_access), row => structureLink('/masters/' + config.resource + '/' + row.id, here));
  if (!columns.length) columns = [{ key: 'record', header: 'Record', type: 'custom', render: row => <a className="janso-link" href={structureLink('/masters/' + config.resource + '/' + row.id, here)}>View record</a> }];
  return <Card><CardHeader title={members ? 'Warehouses in this group and descendants' : 'Direct child groups'} /><StructureFailure failure={metadata.failure ?? list.failure} retry={() => { metadata.refresh(); list.first(); }} /><DataTable caption={members ? 'Warehouse group members' : 'Child warehouse groups'} columns={columns} rows={list.data?.items ?? []} rowId={row => row.id} loading={metadata.loading || list.loading} emptyTitle={members ? 'No readable warehouse members on this date' : 'No child groups on this date'} /><Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun={members ? 'warehouse' : 'group'} /></Card>;
}
export function WarehouseGroupComposition({ company, id, here, access }: { company: string; id: string; here: string; access: StructureAccess }) {
  const context = useStructureContext(company), [selectedDate, setDate] = useState(''), date = selectedDate || context.data?.business_date || '';
  return <><StructureFailure failure={context.failure} retry={context.refresh} /><TextField label="View structure on date" type="date" min="1000-01-01" value={date} error={date && !validMasterDate(date) ? 'Enter a valid date.' : undefined} onChange={event => setDate(event.target.value)} />{validMasterDate(date) && <><StructureRelatedList key={'children:' + date} company={company} id={id} members={false} date={date} here={here} />{access.warehouses && <StructureRelatedList key={'members:' + date} company={company} id={id} members date={date} here={here} />}</>}</>;
}
