'use client';
import { inventoryBreadcrumbs } from '../lib/inventory-navigation';
import { useCallback, useEffect, useState } from 'react';
import { Button, ErrorState, Notice, PageNavigation, SearchSelect, TextField, asErrorStatus, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { assertMaster, masterRequest } from '../lib/catalog-master-api';
import type { MasterField, MasterRow } from '../lib/catalog-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import type { ServicePage } from '../lib/service-resource';
import { signInUrl } from '../lib/navigate';
import { structureBase, structureLink, structureReturn, structureTitle } from '../lib/warehouse-structure';

export type StructureAccess = { groups: boolean; bins: boolean; warehouses: boolean };
export function StructureNavigation({ title, back, access, onLeave }: { title: string; back?: string; access: StructureAccess; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const target = back === '/' ? '/' : structureReturn(back, '/inventory/warehouses');
  return <><PageNavigation back={{ href: target, label: target === '/masters' ? 'masters' : target === '/' ? 'business overview' : target === '/inventory/warehouses' ? 'warehouses and structure' : target.includes('/warehouse-bins') ? 'bins / racks' : target.includes('/warehouse-groups') ? 'warehouse groups' : 'warehouses' }} breadcrumbs={inventoryBreadcrumbs('warehouses', title)} onNavigate={onLeave} /><nav className="janso-page-navigation" aria-label="Warehouse structure">{access.warehouses && <a className="janso-link" onClick={onLeave} href="/masters/warehouses">Warehouses</a>}{access.groups && <a className="janso-link" onClick={onLeave} href="/masters/warehouse-groups">Warehouse groups</a>}{access.bins && <a className="janso-link" onClick={onLeave} href="/masters/warehouse-bins">Bins / racks</a>}</nav></>;
}
export function StructureFailure({ failure, retry, write = false }: { failure: RequestFailure | null; retry?: () => void; write?: boolean }) {
  if (!failure) return null;
  if ([409, 422].includes(failure.status) || write && failure.status >= 500) return <Notice tone="danger"><p>{failure.message}</p>{failure.status === 409 && <p>The record or warehouse policy changed. Your values are retained. Reload and review before saving again.</p>}{write && failure.status >= 500 && <p>The save is unconfirmed. Your values are locked; retry the same save to recover its result.</p>}{retry && <Button variant="ghost" onClick={retry}>Reload and review</Button>}</Notice>;
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={failure.status === 401 ? <a className="janso-link" href={signInUrl()}>Sign in again</a> : retry && failure.status !== 403 ? <Button onClick={retry}>Retry loading</Button> : undefined} />;
}
export function StructureReference({ company, resource, label, name, value, onChange, required = false, disabled = false, error, excludeId, activeOnly = true }: { company: string; resource: 'warehouses' | 'warehouse-groups'; label: string; name?: string; value: string | null; onChange: (id: string | null) => void; required?: boolean; disabled?: boolean; error?: string; excludeId?: string; activeOnly?: boolean }) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null), [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' }); if (activeOnly) params.set('is_active', 'true'); if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await masterRequest<ServicePage<MasterRow>>({ path: structureBase(company, resource) + '?' + params, signal });
    if (!Array.isArray(page.items) || !page.page) throw { status: 502, message: 'Reference list could not be verified.' };
    return { items: page.items.filter(row => row.id !== excludeId && (resource !== 'warehouses' || typeof row.kind === 'string' && row.kind !== 'INTERNAL_TRANSIT')).map(row => ({ id: row.id, label: structureTitle(row), meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, resource, excludeId, activeOnly]);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null); setProblem('');
    if (value) masterRequest<MasterRow>({ path: structureBase(company, resource) + '/' + value, signal: controller.signal }).then(row => { assertMaster(row, company, value); if (!controller.signal.aborted) setSelected({ id: row.id, label: structureTitle(row), meta: row.code }); }).catch(error => { if (!controller.signal.aborted) setProblem(requestFailure(error, 'warehouse references').message); });
    return () => controller.abort();
  }, [company, resource, value]);
  return <SearchSelect label={label} name={name} value={value} selected={selected ?? (value ? { id: value, label: problem ? 'Reference unavailable' : 'Loading reference...', disabled: true } : null)} loadOptions={load} scopeKey={company + ':' + resource + ':' + activeOnly + ':' + excludeId} minQueryLength={0} required={required} clearable={!required} disabled={disabled} error={error ?? (problem || undefined)} hint="Search by code or name. Available records are scoped to this company." onChange={(id, option) => { setSelected(option); setProblem(''); onChange(id); }} />;
}
export function StructureField({ company, field, value, onChange, disabled, error, canReadWarehouses = true, excludeId }: { company: string; field: MasterField; value: unknown; onChange: (value: unknown) => void; disabled?: boolean; error?: string; canReadWarehouses?: boolean; excludeId?: string }) {
  const c = field.control; if (!field.visible || !c || field.conditional_access) return null;
  const locked = !!disabled || !field.writable;
  const common = { label: field.label !== field.key ? field.label : c.label, name: field.key, required: !locked && !c.nullable, disabled: locked, error, hint: field.help_text ?? (field.key === 'code' ? 'Use uppercase letters, numbers, dots, hyphens or underscores.' : undefined) };
  if (c.kind === 'reference') {
    if (c.reference_source === 'warehouses' && !canReadWarehouses) return <Notice>Warehouse details require warehouse read permission.</Notice>;
    if (c.reference_source !== 'warehouses' && c.reference_source !== 'warehouse-groups') return null;
    return <StructureReference {...common} company={company} resource={c.reference_source} value={typeof value === 'string' ? value : null} onChange={onChange} excludeId={excludeId} />;
  }
  if (c.kind === 'boolean') return <TextField {...common} value={value === true ? 'Active' : value === false ? 'Inactive' : 'Protected'} disabled />;
  return <TextField {...common} type={c.kind === 'date' ? 'date' : 'text'} min={c.kind === 'date' ? '1000-01-01' : undefined} maxLength={c.max_length ?? undefined} value={value == null ? '' : String(value)} onChange={event => onChange(event.target.value === '' && c.nullable ? null : event.target.value)} />;
}
export function StructureReferenceLabel({ company, resource, id, here, onLeave }: { company: string; resource: 'warehouses' | 'warehouse-groups'; id: string; here: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const [label, setLabel] = useState('Loading reference...');
  useEffect(() => { const controller = new AbortController(); setLabel('Loading reference...'); masterRequest<MasterRow>({ path: structureBase(company, resource) + '/' + id, signal: controller.signal }).then(row => { assertMaster(row, company, id); if (!controller.signal.aborted) setLabel(structureTitle(row)); }).catch(() => { if (!controller.signal.aborted) setLabel('Reference unavailable'); }); return () => controller.abort(); }, [company, resource, id]);
  return <a className="janso-link" onClick={onLeave} href={structureLink('/masters/' + resource + '/' + id, here)}>{label}</a>;
}
