'use client';
import { useCallback, useEffect, useState } from 'react';
import { Button, ErrorState, Notice, PageNavigation, SearchSelect, Select, TextField, asErrorStatus, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { taxBase, taxRequest, assertTaxRow } from '../lib/tax-api';
import { taxConfigs, taxLabel, taxReturn, taxRoot, taxTitle, type TaxField, type TaxRow } from '../lib/tax-masters';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import type { ServicePage } from '../lib/service-resource';
import { signInUrl } from '../lib/navigate';
import { accountingBackLabel } from '../lib/accounting-configuration-resources';

export function TaxNavigation({ title, back = '/', onLeave }: { title: string; back?: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const target = back === '/' ? '/' : taxReturn(back), path = new URL(target, 'https://console.invalid').pathname;
  const config = taxConfigs.find(value => path.startsWith(taxRoot + '/' + value.key));
  return <PageNavigation back={{ href: target, label: target === '/masters' ? 'masters' : target === '/' ? 'business overview' : path === '/accounting' || path.startsWith('/accounting/') ? accountingBackLabel(target) : config ? path.split('/').length === 3 ? config.title.toLowerCase() : config.singular + ' details' : 'tax masters' }} onNavigate={onLeave}
    breadcrumbs={[{ label: 'Business overview', href: '/' }, ...(title !== 'Tax masters' ? [{ label: 'Tax masters', href: taxRoot }] : []), { label: title }]} />;
}
export function TaxFailure({ failure, retry, write = false }: { failure: RequestFailure | null; retry?: () => void; write?: boolean }) {
  if (!failure) return null;
  if ([409, 422].includes(failure.status) || write && failure.status >= 500) return <Notice tone="danger"><p>{failure.message}</p>{failure.status === 409 && <p>The saved record, tax policy or source changed. Your values are retained; reload and review before trying again.</p>}{write && failure.status >= 500 && <p>The save is unconfirmed. Your values are retained and locked. Retry the same request to recover its result.</p>}{retry && <Button variant="ghost" onClick={retry}>Reload and review</Button>}</Notice>;
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={failure.status === 401 ? <a className="janso-link" href={signInUrl()}>Sign in again</a> : retry && failure.status !== 403 ? <Button onClick={retry}>Retry loading</Button> : undefined} />;
}
export function TaxReference({ company, resource, label, value, onChange, disabled = false, required = false, error, onRecord }: { company: string; resource: 'tax-categories' | 'tax-rules' | 'units'; label: string; value: string | null; onChange: (value: string | null) => void; disabled?: boolean; required?: boolean; error?: string; onRecord?: (row: TaxRow | null) => void }) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null), [problem, setProblem] = useState('');
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const query = new URLSearchParams({ limit: '50', is_active: 'true' }); if (q.trim().length >= 2) query.set('q', q.trim()); if (cursor) query.set('cursor', cursor);
    const page = await taxRequest<ServicePage<TaxRow>>({ path: taxBase(company, resource) + '?' + query, signal });
    return { items: page.items.map(row => ({ id: row.id, label: taxTitle(row), meta: row.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [company, resource]);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null); setProblem('');
    onRecord?.(null);
    if (value) taxRequest<TaxRow>({ path: taxBase(company, resource) + '/' + value, signal: controller.signal }).then(row => {
      assertTaxRow(row, company, value); if (!controller.signal.aborted) { setSelected({ id: row.id, label: taxTitle(row), meta: row.code }); onRecord?.(row); }
    }).catch(error => { if (!controller.signal.aborted) { setProblem(requestFailure(error, 'tax references').message); onRecord?.(null); } });
    else onRecord?.(null);
    return () => controller.abort();
  }, [company, resource, value, onRecord]);
  return <SearchSelect label={label} name={resource === 'tax-categories' ? 'tax_category_id' : resource === 'tax-rules' ? 'rule_id' : 'unit_id'} value={value} selected={selected ?? (value ? { id: value, label: problem ? 'Reference unavailable' : 'Loading reference...', disabled: true } : null)} loadOptions={load} minQueryLength={0} scopeKey={company + ':' + resource} required={required} clearable={!required} disabled={disabled} error={error ?? (problem || undefined)} hint="Search available records by code or name." onChange={(id, option) => { setSelected(option); setProblem(''); onChange(id); }} />;
}
export function TaxField({ company, field, value, onChange, disabled, error }: { company: string; field: TaxField; value: unknown; onChange: (value: unknown) => void; disabled?: boolean; error?: string }) {
  const c = field.control; if (!field.visible || !c) return null;
  const locked = !!disabled || !field.writable || field.conditional_access;
  const common = { label: taxLabel(field), name: field.key, required: !c.nullable && !locked, disabled: locked, error, hint: locked && !disabled ? 'This field is protected by your access.' : field.help_text ?? undefined };
  if (c.kind === 'reference' && ['tax-categories', 'tax-rules', 'units'].includes(c.reference_source ?? '')) return <TaxReference {...common} company={company} resource={c.reference_source as 'tax-categories' | 'tax-rules' | 'units'} value={typeof value === 'string' ? value : null} onChange={onChange} />;
  if (c.kind === 'select' || c.kind === 'boolean') return <Select {...common} placeholder="Choose an option" value={value == null ? '' : String(value)} options={c.kind === 'boolean' ? [{ value: 'true', label: 'Active' }, { value: 'false', label: 'Inactive' }] : c.choices ?? []} onChange={next => onChange(c.kind === 'boolean' ? next === 'true' : next)} />;
  return <TextField {...common} type={c.kind === 'date' ? 'date' : 'text'} min={c.kind === 'date' ? '1000-01-01' : undefined} inputMode={c.kind === 'decimal' ? 'decimal' : c.kind === 'integer' ? 'numeric' : undefined} maxLength={c.max_length ?? undefined} value={value == null ? '' : String(value)} onChange={event => onChange(event.target.value === '' && c.nullable ? null : event.target.value)} />;
}
