'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { masterReturn } from '../lib/master-navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, Notice, PageHeader, PageNavigation, ReviewList, SearchSelect, SectionHeader, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { assertMaster, masterRequest, type MasterPage } from '../lib/catalog-master-api';
import type { MasterRow } from '../lib/catalog-masters';
import { defaultLabels, useWarehouseCommand, useWarehouseRead, type WarehouseConfiguration } from '../lib/warehouse-ui';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CatalogMasterError } from './CatalogMasterDirectory';
import { WarehousePolicyReleases } from './WarehousePolicyReleases';

export function WarehouseSettings({ company, canManage, canPublish, canReadReleases = false, returnTo }: { company: string; canManage: boolean; canPublish: boolean; canReadReleases?: boolean; returnTo?: string }) {
  const root = `/v1/companies/${company}`, read = useWarehouseRead<WarehouseConfiguration>(company, root + '/warehouse-configuration', 'catalog.company_warehouse_configuration', canPublish), command = useWarehouseCommand();
  const [draft, setDraft] = useState<Record<string, string | null>>({}), [labels, setLabels] = useState<Record<string, SearchSelectOption>>({}), [confirm, setConfirm] = useState<'bootstrap' | 'defaults' | null>(null), [message, setMessage] = useState('');
  const dirty = useRef(false);
  const [dialogOpen, setDialogOpen] = useState(true);
  useEffect(() => {
    if (!read.data || read.data.company_id !== company) return;
    const controller = new AbortController(), config = read.data;
    setDraft(Object.fromEntries(Object.keys(defaultLabels).filter(key => Object.hasOwn(config, key)).map(key => [key, config[key as keyof typeof defaultLabels] ?? null]))); dirty.current = false;
    setLabels({});
    const ids = [...new Set(Object.keys(defaultLabels).map(key => config[key as keyof typeof defaultLabels]).filter((id): id is string => typeof id === 'string'))];
    Promise.all(ids.map(async id => {
      try { const row = assertMaster(await masterRequest<MasterRow>({ path: root + '/warehouses/' + id, signal: controller.signal }), company, id); return { id, label: row.name ?? row.code ?? 'Saved warehouse', meta: row.code }; }
      catch { return { id, label: 'Saved warehouse (unavailable)' }; }
    })).then(options => { if (!controller.signal.aborted) setLabels(Object.fromEntries(options.map(option => [option.id, option]))); });
    return () => controller.abort();
  }, [read.data, company, root]);
  useUnsavedChanges(() => dirty.current || command.pending);
  const lookup = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ is_active: 'true', limit: '50' }); if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await masterRequest<MasterPage>({ path: root + '/warehouses?' + params, signal });
    return { items: page.items.filter(row => ['STORE', 'GODOWN'].includes(String(row.kind)) && (read.data?.location_mode === 'MULTI_LOCATION' || row.id === read.data?.main_warehouse_id)).map(row => ({ id: row.id, label: row.name ?? row.code ?? 'Warehouse', meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [root, read.data?.location_mode, read.data?.main_warehouse_id]);
  const fields = read.fields.filter(field => field.visible && field.key in defaultLabels);
  const complete = read.data?.company_id === company && Object.keys(defaultLabels).every(key => key in draft) && Number.isSafeInteger(read.data.policy_generation) && read.data.policy_generation > 0 && Number.isSafeInteger(read.data.source_version) && read.data.source_version > 0;
  const editable = canPublish && complete && fields.some(field => field.writable);
  const back = masterReturn(returnTo, '/masters/warehouses');
  const reload = () => { if (!dirty.current || window.confirm('Discard unsaved warehouse defaults?')) { dirty.current = false; command.clear(); read.refresh(); } };
  return <div className="janso-page"><PageNavigation back={{ href: back, label: back === '/settings' ? 'Company settings' : 'warehouses' }} onNavigate={event => { if (command.pending || dirty.current && !window.confirm('Discard unsaved warehouse defaults?')) event.preventDefault(); }} breadcrumbs={[...inventoryBreadcrumbs('warehouses', 'Warehouse settings').slice(0, -1), { label: 'Warehouses', href: '/masters/warehouses' }, { label: 'Warehouse settings' }]} />
    <PageHeader title="Warehouse settings" lede="Review the company location mode and defaults used by future stock operations." />
    <CatalogMasterError failure={read.failure} retry={read.refresh} />
    {message ? <Notice tone="success">{message}</Notice> : null}
    {command.uncertain && !dialogOpen ? <Notice tone="warning">The change could not be confirmed. The reviewed values are retained. <Button variant="ghost" onClick={() => setDialogOpen(true)}>Recover default change</Button></Notice> : null}
    {read.loading ? <p role="status">Loading warehouse settings...</p> : read.failure?.status === 404 ? <Card><CardBody><SectionHeader title="Initialize warehouse locations" /><p>Main and internal transit have not been provisioned for this company.</p>{canManage ? <Button onClick={() => setConfirm('bootstrap')}>Initialize Main warehouse</Button> : <Notice>Ask a company administrator with warehouse management access to initialize the locations.</Notice>}</CardBody></Card> : read.data?.company_id === company ? <Card><CardBody><div className="janso-flow">
      <SectionHeader title="Company location mode" /><Notice>{read.data.location_mode === 'MULTI_LOCATION' ? 'Multiple warehouses are enabled.' : read.data.location_mode === 'SINGLE_LOCATION' ? 'Only Main is selectable. Enable multiple godowns in company features to use additional locations.' : 'Inventory is disabled. Main remains available as location metadata.'}</Notice>
      <SectionHeader title="Activity defaults" description="Clearing a default uses Main as the fallback. A configured but ineligible warehouse is rejected; stock never moves when a default changes." />
      <div className="janso-form-grid">{fields.map(field => <SearchSelect key={field.key} label={defaultLabels[field.key as keyof typeof defaultLabels]} name={field.key} value={draft[field.key] ?? null} selected={draft[field.key] ? labels[draft[field.key]!] ?? { id: draft[field.key]!, label: 'Saved warehouse' } : null}
        scopeKey={company + ':' + read.data!.location_mode} loadOptions={lookup} minQueryLength={0} disabled={!canPublish || !field.writable || !complete || command.pending || command.uncertain} hint="Optional. Leave empty to resolve to Main." onChange={(value, option) => { dirty.current = true; setDraft(current => ({ ...current, [field.key]: value })); if (option) setLabels(current => ({ ...current, [option.id]: option })); command.clear(); }} />)}</div>
      {!editable ? <Notice>These settings are read-only with your current access or the available configuration.</Notice> : null}
      <div className="janso-form-actions">{canPublish ? <Button disabled={!editable || !dirty.current} onClick={() => setConfirm('defaults')}>Review default changes</Button> : null}<Button variant="ghost" disabled={command.pending || command.uncertain} onClick={reload}>Reload settings</Button></div>
    </div></CardBody></Card> : null}
    {read.data?.company_id === company && (canReadReleases ? <WarehousePolicyReleases company={company} canPublish={canManage && canPublish} generation={read.data.policy_generation} /> : <Notice>Company policy release management requires Catalog release read access. Ask an administrator to review that access before warehouse retirement.</Notice>)}
    <ConfirmDialog open={!!confirm && dialogOpen} title={confirm === 'bootstrap' ? 'Initialize company warehouses?' : 'Save reviewed warehouse defaults?'} confirmLabel={command.uncertain ? 'Retry same change' : confirm === 'bootstrap' ? 'Initialize locations' : 'Save defaults'} busy={command.pending} error={command.failure ? command.failure.message + (command.failure.status === 409 ? ' Cancel and reload settings to review the latest configuration before trying again.' : '') : null} onCancel={() => { if (command.uncertain) setDialogOpen(false); else { setConfirm(null); command.clear(); } }} onConfirm={async () => {
      if (!confirm || confirm === 'bootstrap' && !canManage || confirm === 'defaults' && !editable) return;
      const body = confirm === 'bootstrap' ? {} : { ...draft, expected_generation: read.data!.policy_generation, expected_source_version: read.data!.source_version };
      if (await command.execute(root + '/warehouse-configuration/' + (confirm === 'bootstrap' ? 'bootstrap' : 'defaults'), body)) { dirty.current = false; setMessage(confirm === 'bootstrap' ? 'Company warehouse locations initialized.' : 'Warehouse defaults saved. No stock was moved.'); setConfirm(null); read.refresh(); }
    }}>
      {confirm === 'bootstrap' ? <p>The service creates the protected Main and internal transit locations and the initial company defaults. Repeated initialization preserves their stable identities.</p> : <ReviewList items={Object.keys(defaultLabels).map(key => ({ label: defaultLabels[key as keyof typeof defaultLabels], value: draft[key] ? labels[draft[key]!]?.label ?? 'Saved warehouse' : 'Main fallback' }))} />}
      {command.uncertain ? <Notice tone="warning">The change could not be confirmed. Retry the same change to recover its result.</Notice> : null}
    </ConfirmDialog>
  </div>;
}
