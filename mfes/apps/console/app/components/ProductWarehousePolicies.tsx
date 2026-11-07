'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, Checkbox, ConfirmDialog, Notice, PageHeader, PageNavigation, ReviewList, SearchSelect, SectionHeader, Select, TextField, type SearchSelectLoader } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';
import { assertMasterFields, masterRequest, type MasterPage } from '../lib/catalog-master-api';
import type { MasterFieldSet } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { operationLabels, useWarehouseCommand, type WarehouseConfiguration } from '../lib/warehouse-ui';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CatalogMasterError } from './CatalogMasterDirectory';

type S = components['schemas'];
type Policy = S['ItemWarehousePolicyView'];
type Bands = S['ItemReplenishmentPolicyView'];
type Location = S['LocationPermissionInput'];
type Band = S['ReplenishmentScopeInput'];
type Flags = keyof typeof operationLabels;
const defaults = { default_sale_warehouse_id: 'Sale default', default_purchase_warehouse_id: 'Purchase default', default_customer_return_warehouse_id: 'Customer return default', default_opening_warehouse_id: 'Opening stock default' } as const;
const quantities = { safety_quantity: 'Safety quantity', reorder_quantity: 'Reorder quantity', target_quantity: 'Target quantity', min_order_quantity: 'Minimum order', max_order_quantity: 'Maximum order', order_multiple: 'Order multiple' } as const;
const initialBand = (): Band => ({ warehouse_id: null, purchase_binding_id: '', safety_quantity: '0', reorder_quantity: '0', target_quantity: '1', min_order_quantity: '1', max_order_quantity: null, order_multiple: '1', lead_time_days: 0 });

export function ProductWarehousePolicies({ company, item, canManage }: { company: string; item: string; canManage: boolean }) {
  const root = `/v1/companies/${company}`, base = root + '/items/' + item;
  const command = useWarehouseCommand(), dirty = useRef(false), locationDirty = useRef(false), bandDirty = useRef(false), historyRead = useRef(0);
  const [policy, setPolicy] = useState<Policy | null>(null), [bands, setBands] = useState<Bands | null>(null), [config, setConfig] = useState<WarehouseConfiguration | null>(null);
  const [loading, setLoading] = useState(true), [failure, setFailure] = useState<RequestFailure | null>(null), [revision, setRevision] = useState(0);
  const [editable, setEditable] = useState(false), [bandsEditable, setBandsEditable] = useState(false);
  const [mode, setMode] = useState<'ALLOW_ALL_ACTIVE' | 'ALLOW_LIST'>('ALLOW_ALL_ACTIVE'), [locations, setLocations] = useState<Location[]>([]), [scopes, setScopes] = useState<Band[]>([]);
  const [pointers, setPointers] = useState<Record<keyof typeof defaults, string | null>>({ default_sale_warehouse_id: null, default_purchase_warehouse_id: null, default_customer_return_warehouse_id: null, default_opening_warehouse_id: null });
  const [bindings, setBindings] = useState<S['ItemUnitBindingListItem'][]>([]), [selected, setSelected] = useState<string | null>(null), [names, setNames] = useState<Record<string, string>>({});
  const [review, setReview] = useState<{ path: string; body: unknown; kind: 'locations' | 'bands' } | null>(null), [message, setMessage] = useState('');
  useUnsavedChanges(() => dirty.current || command.pending || command.uncertain);
  useEffect(() => {
    const controller = new AbortController(), ticket = ++historyRead.current; setLoading(true); setFailure(null); setEditable(false); setBandsEditable(false);
    const metadata = (entity: string) => masterRequest<MasterFieldSet>({ path: root + '/entities/' + entity + '/field-set?operation=update', signal: controller.signal });
    Promise.all([
      masterRequest<Policy>({ path: base + '/warehouse-policy', signal: controller.signal }),
      masterRequest<Bands>({ path: base + '/replenishment-policy', signal: controller.signal }),
      masterRequest<WarehouseConfiguration>({ path: root + '/warehouse-configuration', signal: controller.signal }),
      metadata('catalog.item_warehouse_policy'), metadata('catalog.item_warehouse_permission'), metadata('catalog.item_replenishment_policy'),
      masterRequest<{ items: S['ItemUnitBindingListItem'][]; page: { has_more: boolean } }>({ path: base + '/unit-bindings?limit=200', signal: controller.signal }),
    ]).then(async ([p, b, c, pm, lm, bm, units]) => {
      if (controller.signal.aborted || ticket !== historyRead.current) return;
      if (p.item_id !== item || b.item_id !== item || c.company_id !== company || ![p.policy_generation, b.policy_generation, p.source_version, b.source_version].every(value => Number.isSafeInteger(value) && value >= 0) || units.page.has_more) throw { status: 502, message: 'The complete product policy could not be verified. Reload before editing.' };
      const all = (entity: string, value: MasterFieldSet, keys: string[]) => { const fields = assertMasterFields(value, company, entity); return keys.every(key => fields.some(field => field.key === key && field.visible && field.writable)); };
      const activeLocations = (p.locations ?? []).filter(row => row.is_active !== false);
      const activeBands = (b.scopes ?? []).filter(row => row.is_active !== false);
      const ids = [...new Set([...activeLocations.map(row => row.warehouse_id), ...activeBands.map(row => row.warehouse_id)].filter((id): id is string => !!id))];
      const labels = await Promise.all(ids.map(async id => {
        try { const row = await masterRequest<import('../lib/catalog-masters').MasterRow>({ path: root + '/warehouses/' + id, signal: controller.signal }); if (row.id !== id || row.company_id !== company) throw new Error('Warehouse scope changed'); return [id, row.name ?? row.code ?? 'Saved warehouse'] as const; }
        catch { return [id, 'Warehouse unavailable'] as const; }
      }));
      if (controller.signal.aborted) return;
      setNames(Object.fromEntries(labels));
      setEditable(all('catalog.item_warehouse_policy', pm, ['selection_mode', ...Object.keys(defaults)]) && all('catalog.item_warehouse_permission', lm, ['warehouse_id', ...Object.keys(operationLabels)]) && activeLocations.every(row => row.is_active === true && row.warehouse_id && Object.keys(operationLabels).every(key => typeof row[key as Flags] === 'boolean')));
      setBandsEditable(all('catalog.item_replenishment_policy', bm, ['warehouse_id', 'purchase_binding_id', ...Object.keys(quantities), 'lead_time_days']) && activeBands.every(row => row.is_active === true && row.purchase_binding_id && Object.keys(quantities).every(key => row[key as keyof typeof quantities] !== undefined) && row.lead_time_days !== undefined));
      // Keep a dirty editor's generation so concurrent edits still fail the owner guard.
      setPolicy(previous => locationDirty.current && previous ? { ...previous, source_version: p.source_version } : p);
      setBands(previous => bandDirty.current && previous ? { ...previous, source_version: b.source_version } : b);
      setConfig(c);
      if (!locationDirty.current) {
      setMode(p.selection_mode === 'ALLOW_LIST' ? 'ALLOW_LIST' : 'ALLOW_ALL_ACTIVE');
      setPointers(Object.fromEntries(Object.keys(defaults).map(key => [key, p[key as keyof typeof defaults] ?? null])) as typeof pointers);
      setLocations(activeLocations.map(row => ({ warehouse_id: row.warehouse_id ?? '', ...Object.fromEntries(Object.keys(operationLabels).map(key => [key, row[key as Flags] === true])) })) as Location[]);
      }
      if (!bandDirty.current) {
      setScopes(activeBands.map(row => ({ warehouse_id: row.warehouse_id ?? null, purchase_binding_id: row.purchase_binding_id ?? '', ...Object.fromEntries(Object.keys(quantities).map(key => [key, row[key as keyof typeof quantities] ?? null])), lead_time_days: row.lead_time_days ?? 0 })) as Band[]);
      }
      setBindings(units.items.filter(row => row.item_id === item && ['BASE', 'PURCHASE', 'BOTH'].includes(row.usage_role ?? ''))); dirty.current = locationDirty.current || bandDirty.current; setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(requestFailure(error, 'warehouse service')); setLoading(false); } });
    return () => controller.abort();
  }, [company, item, root, base, revision]);
  const lookup = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ is_active: 'true', limit: '50' }); if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await masterRequest<MasterPage>({ path: root + '/warehouses?' + params, signal });
    return { items: page.items.filter(row => ['STORE', 'GODOWN'].includes(String(row.kind)) && (config?.location_mode === 'MULTI_LOCATION' || row.id === config?.main_warehouse_id)).map(row => ({ id: row.id, label: row.name ?? row.code ?? 'Warehouse', meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [root, config]);
  const locked = loading || !!failure || command.pending || command.uncertain || !!review;
  const change = (kind: 'locations' | 'bands' = 'locations') => { (kind === 'locations' ? locationDirty : bandDirty).current = true; dirty.current = true; setMessage(''); command.clear(); };
  const updateBand = (index: number, key: keyof Band, value: unknown) => { change('bands'); setScopes(rows => rows.map((row, at) => at === index ? { ...row, [key]: value } : row)); };
  return <div className="janso-page"><PageNavigation back={{ href: '/masters/items/' + item, label: 'product' }} /><PageHeader title="Product warehouse policies" lede="Maintain permitted locations, activity defaults and exact replenishment quantities. Saving policies moves no stock." />
    <CatalogMasterError failure={failure} retry={() => setRevision(value => value + 1)} />{message && <Notice tone="success">{message}</Notice>}
    {loading ? <p role="status">Loading product warehouse policies...</p> : policy && bands && <>
      <Card><CardBody><div className="janso-flow"><SectionHeader title="Location selection and activity defaults" />
        {!canManage || !editable ? <Notice>Location policy is read-only. Complete field access and product warehouse policy management are required to replace it.</Notice> : null}
        <Select label="Location selection" value={mode} disabled={locked || !canManage || !editable} options={[{ value: 'ALLOW_ALL_ACTIVE', label: 'All active locations' }, { value: 'ALLOW_LIST', label: 'Only listed locations' }]} onChange={value => { change(); setMode(value as typeof mode); }} />
        <Notice>Listed operation flags narrow the warehouse's own permissions. Every product default must name a listed location.</Notice>
        <div className="janso-form-grid">{Object.entries(defaults).map(([key, label]) => <Select key={key} label={label} value={pointers[key as keyof typeof defaults] ?? ''} disabled={locked || !canManage || !editable} options={[{ value: '', label: 'Company default / Main fallback' }, ...locations.map(row => ({ value: row.warehouse_id, label: names[row.warehouse_id] ?? 'Saved warehouse' }))]} onChange={selected => { change(); setPointers(value => ({ ...value, [key]: selected || null })); }} />)}</div>
        {locations.map(row => <section key={row.warehouse_id}><SectionHeader title={names[row.warehouse_id] ?? 'Saved location'} /><div className="janso-form-grid">{Object.entries(operationLabels).map(([key, label]) => <Checkbox key={key} checked={row[key as Flags]} disabled={locked || !canManage || !editable} onChange={event => { change(); setLocations(values => values.map(value => value.warehouse_id === row.warehouse_id ? { ...value, [key]: event.target.checked } : value)); }}>{label}</Checkbox>)}</div><Button variant="ghost" disabled={locked || !canManage || !editable} onClick={() => { change(); setLocations(values => values.filter(value => value.warehouse_id !== row.warehouse_id)); setPointers(values => Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value === row.warehouse_id ? null : value])) as typeof pointers); }}>Remove location</Button></section>)}
        <SearchSelect label="Add permitted warehouse" value={selected} loadOptions={lookup} minQueryLength={0} disabled={locked || !canManage || !editable || locations.length >= 200} onChange={(value, option) => {
          setSelected(null); if (!value || locations.some(row => row.warehouse_id === value)) return;
          change(); if (option) setNames(values => ({ ...values, [value]: option.label }));
          setLocations(values => [...values, { warehouse_id: value, ...Object.fromEntries(Object.keys(operationLabels).map(key => [key, false])) } as Location]);
        }} />
        <Button disabled={locked || !canManage || !editable || mode === 'ALLOW_LIST' && !locations.length} onClick={() => setReview({ kind: 'locations', path: base + '/warehouse-policy', body: { selection_mode: mode, ...pointers, locations, expected_generation: policy.policy_generation, expected_source_version: policy.source_version } })}>Review location policy</Button>
      </div></CardBody></Card>
      <Card><CardBody><div className="janso-flow"><SectionHeader title="Replenishment bands" description="Quantities use the selected purchase unit. Safety, reorder, target and order constraints are validated by the native owner." />
        {!canManage || !bandsEditable ? <Notice>Replenishment is read-only because its complete field access or management authority is unavailable.</Notice> : null}
        {scopes.map((row, index) => <section key={index} aria-label={`Replenishment band ${index + 1}`}><SearchSelect label="Band warehouse (empty means whole product)" value={row.warehouse_id} loadOptions={lookup} minQueryLength={0} disabled={locked || !canManage || !bandsEditable} onChange={value => updateBand(index, 'warehouse_id', value)} />
          <Select label="Purchase unit binding" value={row.purchase_binding_id} disabled={locked || !canManage || !bandsEditable} options={[{ value: '', label: 'Choose purchase unit' }, ...bindings.map(binding => ({ value: binding.id, label: binding.code ?? binding.usage_role ?? 'Purchase unit' }))]} onChange={value => updateBand(index, 'purchase_binding_id', value)} />
          <div className="janso-form-grid">{Object.entries(quantities).map(([key, label]) => <TextField key={key} label={label} inputMode="decimal" maxLength={24} value={String(row[key as keyof typeof quantities] ?? '')} required={key !== 'max_order_quantity'} disabled={locked || !canManage || !bandsEditable} onChange={event => updateBand(index, key as keyof Band, key === 'max_order_quantity' && !event.target.value ? null : event.target.value)} />)}
            <TextField label="Lead time days" type="number" min="0" max="36500" step="1" value={String(row.lead_time_days)} disabled={locked || !canManage || !bandsEditable} onChange={event => updateBand(index, 'lead_time_days', Number(event.target.value))} />
          </div><Button variant="ghost" disabled={locked || !canManage || !bandsEditable} onClick={() => { change('bands'); setScopes(values => values.filter((_, at) => at !== index)); }}>Remove band</Button></section>)}
        <Button variant="ghost" disabled={locked || !canManage || !bandsEditable || !bindings.length || scopes.length >= 200} onClick={() => { change('bands'); setScopes(values => [...values, initialBand()]); }}>Add replenishment band</Button>
        <Button disabled={locked || !canManage || !bandsEditable || scopes.some(row => !row.purchase_binding_id)} onClick={() => setReview({ kind: 'bands', path: base + '/replenishment-policy', body: { scopes, expected_generation: bands.policy_generation, expected_source_version: bands.source_version } })}>Review replenishment</Button>
      </div></CardBody></Card>
      <Button variant="ghost" disabled={locked} onClick={() => { if (!dirty.current || window.confirm('Discard unsaved product warehouse policies?')) { dirty.current = false; locationDirty.current = false; bandDirty.current = false; setRevision(value => value + 1); } }}>Reload policies</Button>
    </>}
    <ConfirmDialog open={!!review} title="Save reviewed product warehouse policy?" confirmLabel={command.uncertain ? 'Retry same policy' : 'Save policy'} busy={command.pending} error={command.failure?.message} onCancel={() => { if (!command.uncertain) { setReview(null); command.clear(); } }} onConfirm={async () => {
      if (!review || !canManage) return;
      if (await command.execute(review.path, review.body, 'PUT')) { (review.kind === 'locations' ? locationDirty : bandDirty).current = false; setReview(null); dirty.current = locationDirty.current || bandDirty.current; setMessage('Product warehouse policy saved. No stock was moved.'); setRevision(value => value + 1); }
    }}><ReviewList items={review?.kind === 'locations' ? [
      { label: 'Selection', value: mode === 'ALLOW_LIST' ? 'Only listed locations' : 'All active locations' },
      ...Object.entries(defaults).map(([key, label]) => ({ label, value: names[pointers[key as keyof typeof defaults] ?? ''] ?? 'Company default / Main fallback' })),
      ...locations.map(row => ({ label: names[row.warehouse_id] ?? 'Saved warehouse', value: Object.entries(operationLabels).filter(([key]) => row[key as Flags]).map(([, label]) => label).join(', ') || 'No operations allowed' })),
    ] : scopes.flatMap((row, index) => [
      { label: `Band ${index + 1}`, value: row.warehouse_id ? names[row.warehouse_id] ?? 'Saved warehouse' : 'Whole product' },
      { label: 'Purchase unit', value: bindings.find(binding => binding.id === row.purchase_binding_id)?.code ?? 'Unavailable' },
      ...Object.entries(quantities).map(([key, label]) => ({ label, value: String(row[key as keyof typeof quantities] ?? 'No maximum') })),
      { label: 'Lead time days', value: String(row.lead_time_days) },
    ])} /><p>Omitted locations or bands are retired in the native owner. Existing stock and history remain recorded.</p>{command.uncertain && <Notice tone="warning">The result is uncertain. Retry this same policy to recover the original command.</Notice>}</ConfirmDialog>
  </div>;
}
