'use client';
import { permissionAuthority } from '../lib/access-permissions';
import { useState } from 'react';
import { Card, DataTable, FilterBar, Notice, PageHeader, Pager, Select, TableSearch, asErrorStatus, type Column } from '@janso/ui';
import { usePermissionCatalogue, type AccessContext } from '../lib/access-directory';
import { AccessNavigation } from './AccessCommon';
import { administrationReturn } from '../lib/administration-navigation';

export function PermissionDirectory({ context, keys, embedded = false, returnTo }: { context: AccessContext; keys?: readonly string[]; embedded?: boolean; returnTo?: string }) {
  const requestedBack = returnTo ? administrationReturn('permissions', returnTo) : undefined;
  const back = requestedBack && new URL(requestedBack, 'https://console.invalid').pathname !== '/permissions' ? requestedBack : undefined;
  const catalogue = usePermissionCatalogue(), [q, setQ] = useState(''), [resource, setResource] = useState(''), [offset, setOffset] = useState(0), [limit, setLimit] = useState(50);
  const all = keys ?? catalogue.permissions, resources = [...new Set(all.map(key => key.split('.')[0]!))].sort();
  const filtered = all.filter(key => key.toLowerCase().includes(q.trim().toLowerCase()) && (!resource || key.split('.')[0] === resource)).map(key => ({ key, resource: key.split('.')[0], held: permissionAuthority(context, key) }));
  const columns: Column<(typeof filtered)[number]>[] = [{ key: 'key', header: 'Permission key', type: 'code' }, { key: 'resource', header: 'Resource', type: 'text' }, { key: 'held', header: 'Your authority', type: 'text' }];
  return <div className={embedded ? 'janso-flow' : 'janso-page'}>{!embedded && <><AccessNavigation context={context} resource="permissions" back={back} /><PageHeader title="Permissions" lede="The application defines permission keys. Roles combine them and assignments apply them to a tenant, company or department." /><Notice tone="info">This catalogue is read-only. Authority is shown for the selected company and your active grants. Department grants apply only within their department; a permission held elsewhere cannot be delegated here.</Notice></>}
    <Card><FilterBar applied={[]} onClearAll={() => { setQ(''); setResource(''); setOffset(0); }}><TableSearch label="Search permissions" value={q} onChange={value => { setQ(value.slice(0, 100)); setOffset(0); }} /><Select label="Resource" value={resource} placeholder="All resources" options={resources.map(value => ({ value, label: value }))} onChange={value => { setResource(value); setOffset(0); }} /></FilterBar>
      <DataTable caption={embedded ? 'Role permissions' : 'Permission catalogue'} columns={columns} rows={filtered.slice(offset, offset + limit)} rowId={row => row.key} loading={!keys && catalogue.loading} error={!keys && catalogue.failure ? asErrorStatus(catalogue.failure.status) : null} errorDetail={catalogue.failure?.message} onRetry={catalogue.refresh} emptyTitle="No matching permissions" filtered={!!q || !!resource} onClearFilters={() => { setQ(''); setResource(''); setOffset(0); }} />
      <Pager count={filtered.slice(offset, offset + limit).length} from={offset + 1} limit={limit} hasPrevious={offset > 0} hasNext={offset + limit < filtered.length} onPrevious={() => setOffset(Math.max(0, offset - limit))} onNext={() => setOffset(offset + limit)} onLimitChange={value => { setLimit(value); setOffset(0); }} noun="permission" />
    </Card>
  </div>;
}
