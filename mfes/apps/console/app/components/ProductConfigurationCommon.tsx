'use client';
import { masterLink, masterReferencePath } from '../lib/master-navigation';
import { useCallback, useEffect, useState } from 'react';
import type { components } from '@janso/api-client/catalog';
import { Badge, Button, Card, CardBody, CardHeader, DataTable, ErrorState, Notice, PageNavigation, ReviewList, SearchSelect, Select, Skeleton, TextField, asErrorStatus, useFormatters, type Column, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { configBack, configLabel, configLink, configRoot, type ConfigEffective, type ConfigField, type ConfigMetadata, type ConfigPage, type ConfigSections, type ConfigValues } from '../lib/product-configuration';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { signInUrl } from '../lib/navigate';
import { configurationTrail } from '../lib/configuration-navigation';
import { inventoryGroupForPath } from '../lib/inventory-navigation';
import { administrationBackLabel } from '../lib/administration-navigation';

export function ConfigurationNavigation({ title, back = configRoot, onLeave }: { title: string; back?: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const target = configBack(back), path = new URL(target, 'https://console.invalid').pathname, trail = configurationTrail(target);
  const label = path.startsWith('/inventory') ? (inventoryGroupForPath(path)?.label.toLowerCase() ?? 'inventory masters') : path === '/settings' || path.startsWith('/companies/') ? administrationBackLabel(target) : path === '/products/custom-fields' ? 'product fields' : path === configRoot ? 'product configuration' : path === configRoot + '/effective' ? 'effective product settings' : path === configRoot + '/adopt' ? 'product adoption' : path.includes('/scopes/') ? 'configuration scope' : path.includes('/drafts/') ? 'configuration draft' : path.includes('/revisions/') ? 'published configuration' : 'product configuration';
  const directory = trail.find(value => new URL(value, 'https://console.invalid').pathname === configRoot) ?? configLink(configRoot, trail.at(-1) ?? configRoot);
  return <PageNavigation back={{ href: target, label }} breadcrumbs={[{ label: 'Business overview', href: '/' }, ...(trail.includes('/inventory/products') ? [{ label: 'Inventory masters', href: '/inventory' }, { label: 'Products and classification', href: '/inventory/products' }] : []), ...(trail.includes('/settings') ? [{ label: 'Company settings', href: '/settings' }] : []), ...(title !== 'Product configuration' ? [{ label: 'Product configuration', href: directory }] : []), { label: title }]} onNavigate={onLeave} />;
}
export function ConfigurationFailure({ failure, retry, write = false, onLeave }: { failure: RequestFailure | null; retry?: () => void; write?: boolean; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  if (!failure) return null;
  if (failure.status === 409 || failure.status === 422 || write && failure.status >= 500) return <Notice tone="danger">{failure.message}{failure.status === 409 && <p>The review is out of date. Reload and review before submitting a new change.</p>}{write && failure.status >= 500 && <p>The result is unconfirmed. Keep the same change when retrying to avoid duplicates.</p>}{retry && <Button variant="ghost" onClick={retry}>Reload and review</Button>}</Notice>;
  const auth = signInUrl(), login = auth + (auth.includes('?') ? '&' : '?') + new URLSearchParams({ returnTo: typeof window === 'undefined' ? configRoot : window.location.pathname + window.location.search });
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={failure.status === 401 ? <a className="janso-link" href={login} onClick={onLeave}>Sign in again</a> : retry && failure.status !== 403 ? <Button onClick={retry}>Reload configuration</Button> : undefined} />;
}
export function ConfigurationLoading() { return <div role="status" aria-label="Loading product configuration"><Skeleton /></div>; }
type Option = components['schemas']['ConfigurationOptionItem'];
export function ConfigurationReference({ company, source, kind, value, label, onChange, disabled, required, error, hint, returnTo, onLeave }: { company: string; source: string; kind?: 'GOODS' | 'SERVICE' | null; value: string | null; label: string; onChange: (value: string | null) => void; disabled?: boolean; required?: boolean; error?: string; hint?: string; returnTo?: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const [selected, setSelected] = useState<SearchSelectOption | null>(null), [lookupError, setLookupError] = useState(''), [referencePath, setReferencePath] = useState<string | null>(null);
  const path = `/v1/companies/${company}/product-configuration/options/${encodeURIComponent(source)}`;
  const load = useCallback<SearchSelectLoader>(async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({ limit: '50' }); if (kind) params.set('kind', kind); if (q.trim().length >= 2) params.set('q', q.trim()); if (cursor) params.set('cursor', cursor);
    const page = await masterRequest<ConfigPage<Option>>({ path: path + '?' + params, signal });
    if (!Array.isArray(page.items) || !page.page) throw new Error('Invalid reference choices');
    return { items: page.items.map(option => ({ id: option.value, label: option.label, meta: option.code })), nextCursor: page.page.has_more ? page.page.next_cursor : null };
  }, [path, kind]);
  useEffect(() => {
    const controller = new AbortController(); setSelected(null); setLookupError(''); setReferencePath(null);
    if (value) {
      const params = new URLSearchParams({ value, limit: '1' }); if (kind) params.set('kind', kind);
      masterRequest<ConfigPage<Option>>({ path: path + '?' + params, signal: controller.signal }).then(page => {
        if (controller.signal.aborted) return;
        const option = page.items.find(row => row.value === value);
        if (option) { setSelected({ id: option.value, label: option.label, meta: option.code }); setReferencePath(masterReferencePath(source, option.value, option.parent_id)); } else setLookupError('This reference is unavailable. Choose an available reference or clear the default.');
      }).catch(problem => { if (!controller.signal.aborted) setLookupError(requestFailure(problem).message); });
    }
    return () => controller.abort();
  }, [path, kind, value]);
  const display = selected?.id === value ? selected : value ? { id: value, label: lookupError ? 'Reference unavailable' : 'Loading reference…', disabled: true } : null;
  return <div className="janso-flow"><SearchSelect label={label} value={value} selected={display} loadOptions={load} scopeKey={company + ':' + source + ':' + (kind ?? '')} minQueryLength={0} required={required} disabled={disabled} clearable={!required} error={error ?? (lookupError || undefined)} hint={hint ?? 'Search by name or code. Only available references in this company are offered.'} onChange={(id, option) => { setSelected(option); setReferencePath(null); setLookupError(''); onChange(id); }} />{disabled && returnTo && referencePath && selected?.id === value && <a className="janso-link janso-fine" href={masterLink(referencePath, returnTo)} onClick={onLeave}>Open {label.toLowerCase()}</a>}</div>;
}
export function ConfigurationField({ company, field, values, onChange, disabled = false, error, unavailableChoices = [] }: { company: string; field: ConfigField; values: ConfigValues; onChange: (key: string, value: unknown) => void; disabled?: boolean; error?: string; unavailableChoices?: string[] }) {
  const control = field.control; if (!field.visible || !control || control.depends_on && String(values[control.depends_on]) !== control.show_when) return null;
  const value = values[field.key], locked = disabled || !field.writable || field.conditional_access, label = configLabel(field);
  const hint = locked && !disabled ? 'This field is protected by your current access.' : field.help_text ?? (control.kind === 'decimal' ? 'Use an exact decimal with up to 4 places. Values are never rounded.' : control.kind === 'integer' && control.nullable ? 'Leave empty to inherit the default.' : undefined);
  if (control.kind === 'reference') return <ConfigurationReference company={company} source={control.reference_source ?? ''} kind={control.reference_kind} label={label} value={typeof value === 'string' && value ? value : null} disabled={locked} required={!control.nullable || !!control.depends_on} hint={hint} error={error} onChange={next => onChange(field.key, next)} />;
  if (control.kind === 'select' || control.kind === 'boolean') return <Select label={label} value={value == null ? '' : String(value)} disabled={locked} required={!control.nullable || !!control.depends_on} options={control.kind === 'select' ? control.choices.map(choice => ({ ...choice, disabled: unavailableChoices.includes(choice.value) })) : [{ value: 'false', label: 'No' }, { value: 'true', label: 'Yes' }]} placeholder={control.nullable ? 'Choose an option' : undefined} hint={unavailableChoices.length ? 'Some choices require a dependent field that is hidden or protected.' : hint} error={error} onChange={next => onChange(field.key, control.kind === 'boolean' ? next === '' ? null : next === 'true' : next)} />;
  return <TextField label={label} value={value == null ? '' : String(value)} type={control.kind === 'date' ? 'date' : 'text'} inputMode={control.kind === 'integer' ? 'numeric' : control.kind === 'decimal' ? 'decimal' : undefined} required={!control.nullable} maxLength={control.max_length ?? (control.kind === 'decimal' ? 20 : undefined)} disabled={locked} hint={hint} error={error} onChange={event => onChange(field.key, event.target.value === '' && control.nullable ? null : event.target.value)} />;
}
export function ConfigurationFields({ company, fields, values, setValues, disabled, errors, prefix = '' }: { company: string; fields: ConfigField[]; values: ConfigValues; setValues: (values: ConfigValues) => void; disabled?: boolean; errors: Record<string, string>; prefix?: string }) {
  function change(key: string, value: unknown) {
    const next = { ...values, [key]: value };
    for (const pair of fields.filter(field => field.control?.depends_on === key && field.writable && !field.conditional_access)) {
      if (String(value) !== pair.control!.show_when) next[pair.key] = null;
      else if (pair.control!.kind === 'boolean' && typeof next[pair.key] !== 'boolean') next[pair.key] = false;
    }
    setValues(next);
  }
  return <div className="janso-form-grid janso-config-fields">{fields.filter(field => !field.control?.depends_on || !fields.some(parent => parent.key === field.control!.depends_on)).map(field => {
    const pair = fields.find(dependent => dependent.control?.depends_on === field.key);
    const protectedPair = pair && (!pair.visible || !pair.writable || pair.conditional_access);
    const unavailableChoices = protectedPair ? field.control?.choices.filter(choice => choice.value !== values[field.key] && (values[pair.key] != null || choice.value === pair.control!.show_when)).map(choice => choice.value) ?? [] : [];
    if (!field.visible || !field.control) return null;
    return <div key={field.key} className="janso-config-fields__option"><ConfigurationField company={company} field={field} values={values} disabled={disabled} unavailableChoices={unavailableChoices} error={errors[prefix + field.key]} onChange={change} />{fields.filter(dependent => dependent.control?.depends_on === field.key).map(dependent => <ConfigurationField key={dependent.key} company={company} field={dependent} values={values} disabled={disabled} error={errors[prefix + dependent.key]} onChange={change} />)}</div>;
  })}</div>;
}

export function ConfigurationSectionNavigation({ conversion = false, details = true, numeric = true }: { conversion?: boolean; details?: boolean; numeric?: boolean }) {
  return <nav className="janso-config-nav" aria-label="Configuration sections"><span className="janso-fine">Jump to</span>{[
    ...(details ? [['details', 'Draft details']] : []), ['options', 'Entry options'],
    ...(conversion ? [['unit-conversion', 'Unit conversion']] : []),
    ['profiles', 'Profile defaults'], ['pricing', 'Pricing requirements'],
    ...(numeric ? [['numeric', 'Numeric defaults']] : []),
  ].map(([id, title]) => <a key={id} className="janso-link" href={'#configuration-' + id}>{title}</a>)}</nav>;
}
function ReferenceText({ company, field, value, returnTo, onLeave }: { company: string; field: ConfigField; value: string; returnTo: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const [reference, setReference] = useState<{ label: string; path: string | null }>({ label: 'Loading reference...', path: null });
  useEffect(() => {
    const controller = new AbortController(); setReference({ label: 'Loading reference...', path: null });
    const query = new URLSearchParams({ value, limit: '1' }); if (field.control?.reference_kind) query.set('kind', field.control.reference_kind);
    masterRequest<ConfigPage<Option>>({ path: `/v1/companies/${company}/product-configuration/options/${field.control!.reference_source}?${query}`, signal: controller.signal }).then(page => {
      if (controller.signal.aborted) return;
      const option = page.items.find(row => row.value === value);
      setReference(option ? { label: option.label, path: masterReferencePath(field.control!.reference_source!, option.value, option.parent_id) } : { label: 'Reference unavailable', path: null });
    }).catch(() => { if (!controller.signal.aborted) setReference({ label: 'Reference unavailable within your access', path: null }); });
    return () => controller.abort();
  }, [company, value, field.control?.reference_source, field.control?.reference_kind]);
  return reference.path ? <a className="janso-link" href={masterLink(reference.path, returnTo)} onClick={onLeave}>{reference.label}</a> : <span>{reference.label}</span>;
}

export function ConfigurationValues({ title, fields, values, company, returnTo = configRoot, onLeave }: { title: string; fields: ConfigField[]; values: ConfigValues; company?: string; returnTo?: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const format = useFormatters();
  const items = fields.filter(field => field.visible && field.control && field.key in values && (!field.control.depends_on || String(values[field.control.depends_on]) === field.control.show_when)).map(field => {
    const value = values[field.key], control = field.control!;
    return { label: configLabel(field), value: value == null ? 'Inherit / not set' : company && control.kind === 'reference' ? <ReferenceText company={company} returnTo={returnTo} onLeave={onLeave} field={field} value={String(value)} /> : control.kind === 'date' ? format.date(String(value)) : typeof value === 'boolean' ? value ? 'Yes' : 'No' : control.choices.find(choice => choice.value === value)?.label ?? String(value) };
  });
  return <Card><CardHeader title={title} /><CardBody>{items.length ? <ReviewList items={items} /> : <Notice>No readable settings in this section.</Notice>}</CardBody></Card>;
}
export function ConfigurationEffectiveValues({ value, metadata, returnTo = configRoot, onLeave }: { value: ConfigEffective; metadata?: ConfigMetadata; returnTo?: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const format = useFormatters();
  const titles = { options: 'Entry options', pricing: 'Pricing requirements', profiles: 'Profile defaults' } as const;
  type Setting = components['schemas']['ConfigurationSetting'];
  const columns: Column<Setting>[] = [{ key: 'field', header: 'Setting', type: 'text' }, { key: 'applicable', header: 'Applicability', type: 'custom', render: row => row.applicable ? 'Applicable' : 'Not applicable' }, { key: 'overrideable', header: 'Protection', type: 'custom', render: row => row.reason ? row.reason.replaceAll('_', ' ') : row.overrideable ? 'May be overridden within access' : 'Protected' }, { key: 'origins', header: 'Source', type: 'custom', render: row => row.origins.map(origin => origin.kind.toLowerCase()).join(', ') || 'Native default' }];
  return <>
    {Object.entries(titles).map(([section, title]) => <ConfigurationGroupedValues key={section} company={value.company_id} returnTo={returnTo} onLeave={onLeave} title={title} fields={metadata?.[section as keyof typeof titles] ?? Object.keys(value[section as keyof typeof titles]).map((key, order) => ({ key, label: key.replaceAll('_', ' '), source: 'native', visible: true, writable: false, required: false, conditional_access: false, order, control: { kind: 'text', label: key.replaceAll('_', ' '), choices: [], nullable: true } }))} values={value[section as keyof typeof titles] as ConfigValues} />)}
    <Card><CardHeader title="Numeric defaults" /><CardBody>{value.numeric_defaults.length ? value.numeric_defaults.map(row => <ReviewList key={row.dimension} items={Object.entries(row).filter(([, entry]) => entry != null).map(([key, entry]) => ({ label: key.replaceAll('_', ' '), value: String(entry) }))} />) : <p>No configured numeric defaults. Native unit rules apply.</p>}</CardBody></Card>
    <Card><CardHeader title="Inheritance and protection" /><DataTable caption="Effective configuration protection" columns={columns} rows={value.settings} rowId={row => row.field} emptyTitle="No additional protection details" /></Card>
    <Card><CardHeader title="Source revisions" /><CardBody>{value.sources.length ? <ReviewList items={value.sources.map(source => ({ label: source.scope_kind.toLowerCase() + ' · revision ' + source.revision, value: <a className="janso-link" href={configLink(configRoot + '/revisions/' + source.revision_id, returnTo)} onClick={onLeave}>View revision effective {format.date(source.effective_from)}</a> }))} /> : <p>Native defaults; no published configuration revisions apply.</p>}</CardBody></Card>
    <Notice>These settings describe product defaults and restrictions. Saved product settings, price history and company capabilities remain authoritative. Publication does not change active products automatically.</Notice>
  </>;
}

export function ConfigurationGroupedValues({ anchor, ...props }: React.ComponentProps<typeof ConfigurationValues> & { anchor?: string }) {
  const groups = [{ key: 'unit_conversion', title: 'Unit conversion' }, { key: 'pricing_options', title: 'Additional pricing options' }];
  const main = props.fields.filter(field => !groups.some(group => group.key === field.display_group));
  return <><section id={anchor ? 'configuration-' + anchor : undefined} tabIndex={anchor ? -1 : undefined} className="janso-config-section"><ConfigurationValues {...props} fields={main} /></section>{groups.filter(group => props.fields.some(field => field.visible && field.control && field.display_group === group.key)).map(group => <section key={group.key} id={anchor ? 'configuration-' + group.key.replaceAll('_', '-') : undefined} tabIndex={anchor ? -1 : undefined} className="janso-config-section"><ConfigurationValues {...props} title={group.title} fields={props.fields.filter(field => field.display_group === group.key)} /></section>)}</>;
}
