'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, CustomFields, FormActions, FormLayout, Notice, PageHeader, PageNavigation, SearchSelect, SectionHeader, Select, TextField, businessToday, useDisplayConfig } from '@janso/ui';
import { masterBody, masterCustomDraft, masterCustomFields, masterLabel, type MasterConfig } from '../lib/catalog-masters';
import { assertMaster, masterBase, masterRequest, useMasterLookup, useMasterRecord } from '../lib/catalog-master-api';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { goTo } from '../lib/navigate';
import { CatalogMasterError, masterReturnTo } from './CatalogMasterDirectory';
import { WarehouseRegionalField } from './WarehouseRegionalField';
import { WarehouseCompanyField } from './WarehouseCompanyField';
import { masterDirectoryReturn, masterLink } from '../lib/master-navigation';
import { inventoryBreadcrumbs, inventoryGroupForPath } from '../lib/inventory-navigation';
import type { EmbeddedMasterEditor } from '../lib/embedded-master-editor';

export function CatalogMasterEditor({ company, config, id, returnTo, canReadParty = false, canReadDepartments = false, canReadCompany = false, embedded }: { company: string; config: MasterConfig; id?: string; returnTo?: string; canReadParty?: boolean; canReadDepartments?: boolean; canReadCompany?: boolean; embedded?: EmbeddedMasterEditor }) {
  const record = useMasterRecord(company, config, id, true), display = useDisplayConfig();
  const [draft, setDraft] = useState<Record<string, unknown>>(() => ({ ...config.initial, ...(config.resource === 'item-groups' ? { valid_from: businessToday(display.timezone) } : {}), ...embedded?.initialValues }));
  const [saving, setSaving] = useState(false), [savedId, setSavedId] = useState<string | null>(null), [saved, setSaved] = useState(false);
  const [unchanged, setUnchanged] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({}), [failure, setFailure] = useState<RequestFailure | null>(null), [leave, setLeave] = useState<string | null>(null);
  const busy = useRef(false), form = useRef<HTMLFormElement>(null), changed = useRef(false), retry = useRef<{ payload: string; key: string } | null>(null);
  const parentLookup = useMasterLookup(company, 'item-groups'), parties = useMasterLookup(company, 'parties');
  const back = masterReturnTo(config, returnTo), directory = masterDirectoryReturn(config.resource, back), detailHref = (masterId: string) => masterLink(`/masters/${config.resource}/${masterId}`, back);
  useEffect(() => { if (record.row && !changed.current) setDraft(record.row); }, [record.row]);
  useUnsavedChanges(() => changed.current || busy.current);
  const uncertain = !!embedded && !!retry.current && !!failure && (failure.status >= 500 || failure.status === 0);
  useEffect(() => { embedded?.onStateChange({ dirty: changed.current, busy: saving || uncertain }); }, [embedded?.onStateChange, draft, saving, uncertain]);
  const change = (key: string, value: unknown) => { if (uncertain) return; changed.current = true; setDraft(current => ({ ...current, [key]: value })); setErrors({}); setFailure(null); setSaved(false); setUnchanged(false); };
  const navigate = (href: string) => { if (busy.current) return; if (changed.current) setLeave(href); else goTo(href); };
  const onNavigate = (event: React.MouseEvent<HTMLAnchorElement>) => { if (busy.current || changed.current) { event.preventDefault(); navigate(event.currentTarget.getAttribute('href')!); } };
  const focusError = () => requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
  async function save() {
    if (busy.current || record.loading || record.failure || savedId || (id && !record.row)) return;
    const result = masterBody(config, record.fields, draft, record.row ?? undefined);
    setErrors(result.errors); setFailure(null); setSaved(false); setUnchanged(false);
    if (Object.keys(result.errors).length) { focusError(); return; }
    if (id && Object.keys(result.body).length === 1) { setUnchanged(true); setDraft(record.row!); changed.current = false; return; }
    busy.current = true; setSaving(true);
    const path = masterBase(company, config) + (id ? '/' + id : ''), method = id ? 'PATCH' : 'POST';
    const payload = JSON.stringify({ path, method, body: result.body });
    if (retry.current?.payload !== payload) retry.current = { payload, key: crypto.randomUUID() };
    try {
      const row = assertMaster(await masterRequest<import('../lib/catalog-masters').MasterRow>({ path, method, body: result.body, key: retry.current!.key }), company, id);
      retry.current = null; changed.current = false; setSaved(true);
      if (id) { record.setRow(row); setDraft(row); } else setSavedId(row.id);
      embedded?.onSaved(row);
    } catch (error) { const value = requestFailure(error, 'master service'); setFailure(value); setErrors(value.fields ?? {}); focusError(); }
    finally { busy.current = false; setSaving(false); }
  }
  const visible = record.fields.filter(field => field.visible && field.source === 'native' && config.inputs[field.key]);
  const hasWritable = visible.some(field => field.writable && !(id && config.resource === 'warehouses' && ['code', 'kind'].includes(field.key))
    && (config.inputs[field.key]?.type !== 'party' || canReadParty)
    && (config.inputs[field.key]?.type !== 'department' || canReadDepartments)
    && (config.inputs[field.key]?.type !== 'tax-registration' || canReadCompany))
    || masterCustomDraft(config, record.fields, draft, !id).fields.length > 0;
  return <div className="janso-page">
    {!embedded && <><PageNavigation back={{ href: id ? detailHref(id) : back, label: id ? `${config.singular} details` : config.title.toLowerCase() }} onNavigate={onNavigate}
      breadcrumbs={[...inventoryBreadcrumbs(inventoryGroupForPath('/masters/' + config.resource)!.key, '').slice(0, -1), { label: config.title, href: directory }, ...(id ? [{ label: record.row?.name ?? 'Details', href: detailHref(id) }] : []), { label: id ? `Edit ${config.singular}` : `New ${config.singular}` }]} />
    <PageHeader title={id ? `Edit ${config.singular}` : `New ${config.singular}`} lede="Changes apply to the company currently open. Required fields are marked." /></>}
    <CatalogMasterError failure={record.failure ?? failure} write={!record.failure} retry={record.failure ? record.refresh : failure?.status === 409 ? () => setLeave('reload') : undefined} />
    {record.row?.is_active === false ? <Notice tone="warning">This {config.singular} is inactive. Saving details does not activate it.</Notice> : null}
    {saved ? <Notice tone="success">{config.singular.charAt(0).toUpperCase() + config.singular.slice(1)} {id ? 'updated.' : 'created.'}</Notice> : null}
    {unchanged ? <Notice>No changes to save.</Notice> : null}
    {record.loading ? <p role="status">Loading {config.singular} form…</p> : record.failure ? null : savedId ? <Card><CardBody><div className="janso-flow">
      <a className="janso-btn janso-btn--primary" href={detailHref(savedId)}>View {config.singular}</a>
      <a className="janso-link" href={`/masters/${config.resource}/new?returnTo=${encodeURIComponent(back)}`}>Create another {config.singular}</a>
      <a className="janso-link" href={back}>Return to {config.title.toLowerCase()}</a>
    </div></CardBody></Card> : <FormLayout aside={<><SectionHeader title="Before you save" /><p className="janso-fine">Codes must be unique within this company. Locked fields keep their existing values. Changes are checked and audited by the service.</p>
      {config.resource === 'units' ? <p className="janso-fine">Changing quantity rules may be restricted when a unit is already in use.</p> : null}
      {!hasWritable ? <Notice tone="warning">Your field access does not allow changes to this record.</Notice> : null}</>}>
      <form ref={form} noValidate onSubmit={event => { event.preventDefault(); void save(); }}><Card><CardBody><div className="janso-flow">
        <SectionHeader title="Details" />
        <div className="janso-form-grid">{visible.map(field => {
          const input = config.inputs[field.key]!, label = masterLabel(config, field), disabled = saving || uncertain || !field.writable || !!id && config.resource === 'warehouses' && ['code', 'kind'].includes(field.key);
          const common = { label, required: field.required && !disabled, disabled, error: errors[field.key], hint: disabled && !saving ? 'This field is read-only.' : field.help_text ?? input.hint, name: field.key };
          if (input.type === 'department' || input.type === 'tax-registration') return <WarehouseCompanyField key={field.key} {...common} company={company} type={input.type} value={typeof draft[field.key] === 'string' ? draft[field.key] as string : null} canRead={input.type === 'department' ? canReadDepartments : canReadCompany} onChange={value => change(field.key, value)} />;
          if (input.type === 'country' || input.type === 'state' || input.type === 'timezone') return <WarehouseRegionalField key={field.key} {...common} company={company} type={input.type} value={typeof draft[field.key] === 'string' ? draft[field.key] as string : null} country={typeof draft.country_code === 'string' ? draft.country_code : null} onChange={value => {
            change(field.key, value);
            if (field.key === 'country_code' && value !== draft.country_code && record.fields.some(item => item.key === 'state_code' && item.visible && item.writable)) change('state_code', null);
          }} />;
          if (input.type === 'party') return <SearchSelect key={field.key} {...common} disabled={disabled || !canReadParty} hint={!canReadParty ? 'Party read access is needed to change this optional link. The saved link is retained.' : common.hint}
            value={typeof draft.party_id === 'string' ? draft.party_id : null} loadOptions={parties} minQueryLength={0} onChange={value => change('party_id', value)} />;
          if (input.choices) return <Select key={field.key} {...common} placeholder="Choose an option" value={String(draft[field.key] ?? '')} options={input.choices.map(value => ({ value, label: value }))} onChange={value => change(field.key, value)} />;
          return <TextField key={field.key} {...common} value={String(draft[field.key] ?? '')} maxLength={input.max ?? 20} inputMode={input.type === 'decimal' ? 'decimal' : 'text'} placeholder={field.placeholder ?? undefined} onChange={event => change(field.key, event.target.value)} />;
        })}</div>
        {!id && config.resource === 'item-groups' ? <><SectionHeader title="Hierarchy" description="Leave the parent empty for a top-level group. The effective date starts its history." />
          <SearchSelect label="Parent group" name="parent_group_id" error={errors.parent_group_id} value={typeof draft.parent_group_id === 'string' ? draft.parent_group_id : null} loadOptions={parentLookup} minQueryLength={0} disabled={saving || uncertain} onChange={value => change('parent_group_id', value)} />
          <TextField label="Effective from" name="valid_from" type="date" min="1000-01-01" required disabled={saving || uncertain} value={String(draft.valid_from ?? '')} error={errors.valid_from} onChange={event => change('valid_from', event.target.value)} />
        </> : null}
        <CustomFields fields={masterCustomFields(record.fields)} values={draft.custom_fields as Record<string, unknown> ?? {}} nativeValues={draft} creating={!id} disabled={saving || uncertain} currencies={display.currency ? [display.currency] : []} errors={errors}
          onChange={value => change('custom_fields', value)} loadOptions={(source, parent) => async ({ q, cursor, signal }) => {
            const params = new URLSearchParams({ limit: '50', as_of: businessToday(display.timezone) }); if (q.length >= 2) params.set('q', q); if (cursor) params.set('cursor', cursor); if (parent) params.set('parent_id', parent);
            const page = await masterRequest<{ items: { value: string; label: string; code: string }[]; page: { has_more: boolean; next_cursor: string | null } }>({ path: `/v1/companies/${company}/option-sources/${encodeURIComponent(source)}?${params}`, signal });
            return { items: page.items.map(option => ({ id: option.value, label: option.label, meta: option.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
          }} />
        {errors.custom_fields ? <Notice tone="danger">{errors.custom_fields}</Notice> : null}
        {errors.row_version ? <Notice tone="danger">{errors.row_version}</Notice> : null}
      </div></CardBody><FormActions cancel={embedded ? { onCancel: embedded.onCancel, disabled: saving || uncertain } : { href: id ? detailHref(id) : back, onClick: onNavigate }}><Button type="submit" disabled={!hasWritable} loading={saving} loadingLabel="Saving…">{uncertain ? 'Retry same save' : id ? 'Save changes' : `Create ${config.singular}`}</Button></FormActions></Card></form>
    </FormLayout>}
    <ConfirmDialog open={!!leave} title="Discard unsaved changes?" confirmLabel={leave === 'reload' ? 'Discard and reload' : 'Discard changes'} onCancel={() => setLeave(null)} onConfirm={() => {
      changed.current = false; const target = leave; setLeave(null);
      if (target === 'reload') { retry.current = null; setFailure(null); setErrors({}); record.refresh(); } else if (target) goTo(target);
    }}>Your changes have not been saved.{leave === 'reload' ? ' Reloading replaces them with the latest saved values.' : ''}</ConfirmDialog>
  </div>;
}
