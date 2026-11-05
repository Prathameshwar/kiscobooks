'use client';

import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { Badge, Button, Card, CardBody, ConfirmDialog, CustomFields, ErrorState,
  DEFAULT_DISPLAY_CONFIG, FieldGrid, FieldLabel, FormActions, FormLayout, ListRow, Notice, PageHeader, PageNavigation, ReviewList, SearchSelect, SectionHeader, Select, Skeleton, TextField, asErrorStatus, formatDate, formatMoney, resolvedDisplay } from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { AutomaticCompanySetup } from './AutomaticCompanySetup';
import { companyCustomFields, companyFieldLabel, companyPatch, type CompanyField } from '../lib/company-form';
import { goTo, stepUpUrl } from '../lib/navigate';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { administrationBackLabel, administrationDirectoryReturn, administrationLink, administrationReturn } from '../lib/administration-navigation';

type Company = components['schemas']['CompanyDetail'];
type Country = components['schemas']['CountryChoice'];
type Currency = components['schemas']['CurrencyChoice'];
type State = components['schemas']['identity__schemas__reference__StateChoice'];
type Classifications = components['schemas']['CompanyClassifications'];
type Option = { value: string; label: string; disabled?: boolean };
const groupNames: Record<string, string> = { identity: 'Business identity', financial: 'Money and calendar', tax: 'Tax defaults', commercial: 'Business and payment defaults', locale: 'Presentation', branding: 'Branding and document text', visibility: 'Visibility and sign-in', custom: 'Additional details' };
const groupDescriptions: Record<string, string> = {
  identity: 'Company names, classification and registered location.',
  financial: 'Currency, financial calendar and number precision.',
  tax: 'The company\u2019s default tax system and treatment.',
  commercial: 'Default payment terms, credit and business preferences.',
  locale: 'Date, time and number formats used to present company data.',
  branding: 'Brand details and text used on company documents.',
  visibility: 'Company listing and additional sign-in requirements.',
  custom: 'Additional fields configured for this company.',
};

function shown(value: unknown): string {
  if (value == null || value === '') return 'Not set';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'None';
  if (typeof value === 'object') {
    const amount = value as { amount?: string; currency?: string };
    return amount.amount != null ? `${amount.amount} ${amount.currency ?? ''}` : JSON.stringify(value);
  }
  return String(value);
}

export function CompanyProfile({ companyId, editing = false, canEdit = false, returnTo }: { companyId: string; editing?: boolean; canEdit?: boolean; returnTo?: string }) {
  const [company, setCompany] = useState<Company | null>(null), [fields, setFields] = useState<CompanyField[]>([]);
  const [draft, setDraft] = useState<Record<string, unknown>>({}), [failure, setFailure] = useState<CompanyFailure | null>(null);
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [saved, setSaved] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({}), [revision, setRevision] = useState(0);
  const [leave, setLeave] = useState<string | null>(null);
  const [countries, setCountries] = useState<Country[]>([]), [currencies, setCurrencies] = useState<Currency[]>([]), [states, setStates] = useState<State[]>([]);
  const [classifications, setClassifications] = useState<Classifications | null>(null);
  const [referenceFailure, setReferenceFailure] = useState(false), [referencesLoading, setReferencesLoading] = useState(editing);
  const [choiceRevision, setChoiceRevision] = useState(0);
  const [stateFailure, setStateFailure] = useState(false), [statesLoading, setStatesLoading] = useState(false);
  const form = useRef<HTMLFormElement>(null), busy = useRef(false);
  const discarded = useRef(false);
  const inputPrefix = useId();
  const dirty = !!company && JSON.stringify(draft) !== JSON.stringify(company);
  useUnsavedChanges(useCallback(() => !discarded.current && (dirty || busy.current), [dirty]));
  const base = '/companies/' + companyId;
  const back = returnTo ? administrationReturn('companies', returnTo) : editing ? base : '/companies/manage';
  const directory = administrationDirectoryReturn('companies', back), detail = administrationLink(base, directory);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(null); setCompany(null);
    Promise.all([
      companyCall<Company>('identity', '/v1/companies/' + companyId, { signal: controller.signal }),
      companyCall<components['schemas']['FieldSet']>('identity', '/v1/entities/identity.company/field-set?company_id=' + companyId, { signal: controller.signal }),
    ]).then(([data, metadata]) => {
      if (controller.signal.aborted) return;
      if (data.id !== companyId) throw new Error('Company response mismatch');
      setCompany(data); setDraft(data); setFields(metadata.fields); setErrors({}); setLoading(false);
    }).catch(error => { if (!controller.signal.aborted) { setFailure(companyFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [companyId, revision]);
  useEffect(() => {
    if (!editing) return;
    const controller = new AbortController(); setReferencesLoading(true); setReferenceFailure(false);
    Promise.all([
      companyCall<Country[]>('identity', '/v1/reference/countries', { signal: controller.signal }),
      companyCall<Currency[]>('identity', '/v1/reference/currencies', { signal: controller.signal }),
      companyCall<Classifications>('identity', '/v1/company-classifications', { signal: controller.signal }),
    ]).then(([country, currency, classification]) => {
      if (!controller.signal.aborted) { setCountries(country); setCurrencies(currency); setClassifications(classification); setReferencesLoading(false); }
    }).catch(() => { if (!controller.signal.aborted) { setReferenceFailure(true); setReferencesLoading(false); } });
    return () => controller.abort();
  }, [editing, choiceRevision]);
  const country = String(draft.country_code ?? '');
  useEffect(() => {
    if (!editing || !country) return;
    const controller = new AbortController(); setStates([]); setStateFailure(false); setStatesLoading(true);
    companyCall<State[]>('identity', '/v1/reference/countries/' + country + '/states', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) { setStates(data); setStatesLoading(false); } })
      .catch(() => { if (!controller.signal.aborted) { setStateFailure(true); setStatesLoading(false); } });
    return () => controller.abort();
  }, [country, editing, choiceRevision]);

  function change(key: string, value: unknown) {
    discarded.current = false;
    setSaved(false); setErrors(previous => ({ ...previous, [key]: '' }));
    setDraft(previous => ({ ...previous, [key]: value,
      ...(key === 'country_code' && fields.some(field => field.key === 'state_code' && field.writable) ? { state_code: '' } : {}),
    }));
  }
  function options(field: CompanyField): Option[] | null {
    const key = field.key;
    if (key === 'country_code') return countries.filter(item => item.jurisdiction_supported).map(item => ({ value: item.code, label: `${item.name} (${item.code})` }));
    if (key === 'state_code') return states.map(item => ({ value: item.code, label: `${item.name} (${item.code})` }));
    if (key === 'base_currency' || key === 'reporting_currency') return currencies.map(item => ({ value: item.code, label: `${item.code} · ${item.name}` }));
    if (key === 'default_tax_system') return (countries.find(item => item.code === country)?.tax_systems ?? []).map(value => ({ value, label: value }));
    const classification = key === 'business_category_code' ? classifications?.business_categories : key === 'store_format_code' ? classifications?.store_formats : undefined;
    if (classification) return classification.map(item => ({ value: item.code, label: item.label }));
    return field.choices?.map(item => ({ value: String(item.value), label: String(item.label) })) ?? null;
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!company || busy.current || !canEdit || referencesLoading || referenceFailure || statesLoading || stateFailure) return;
    const result = companyPatch(fields, draft, company);
    setErrors(result.errors); setFailure(null); setSaved(false);
    if (Object.keys(result.errors).length) { requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return; }
    if (!Object.keys(result.patch).length) { setSaved(true); return; }
    busy.current = true; setSaving(true);
    try {
      const data = await companyCall<Company>('identity', '/v1/companies/' + companyId, {
        method: 'PATCH', body: { ...result.patch, expected_updated_at: company.updated_at },
      });
      if (data.id !== companyId) throw new Error('Company response mismatch');
      setCompany(data); setDraft(data); setSaved(true); setRevision(value => value + 1);
    } catch (error) { const refused = companyFailure(error); setFailure(refused); setErrors(refused.fields ?? {});
      requestAnimationFrame(() => form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); }
    finally { busy.current = false; setSaving(false); }
  }
  function navigate(href: string) { if (dirty) setLeave(href); else goTo(href); }
  const visible = fields.filter(field => field.is_visible && (field.source === 'custom' || field.key in draft));
  const groups = [...new Set(visible.map(field => field.group))];
  const writable = canEdit && company?.status === 'active' && fields.some(field => field.writable && field.is_visible);
  function displayValue(field: CompanyField) {
    const value = field.source === 'custom' ? (company?.custom_fields ?? {})[field.key.replace(/^custom_field:/, '')] : draft[field.key];
    if (value == null || value === '') return shown(value);
    const display = { ...DEFAULT_DISPLAY_CONFIG, ...Object.fromEntries(
      Object.entries(resolvedDisplay(company ?? {})).filter(([, value]) => value !== undefined),
    ) };
    if (field.data_type === 'date' && typeof value === 'string') return formatDate(value, display);
    if (['credit_limit_default', 'cash_receipt_limit'].includes(field.key) && company?.base_currency) return formatMoney(String(value), display, { display: 'code' });
    return shown(value);
  }
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }}
      onNavigate={event => { if (saving || dirty) { event.preventDefault(); if (!saving) navigate(event.currentTarget.getAttribute('href')!); } }}
      breadcrumbs={[{ label: 'Administration', href: '/organisation' }, { label: 'Companies', href: directory }, ...(editing ? [{ label: company?.display_name ?? 'Company details', href: detail }] : []), { label: editing ? 'Edit company' : company?.display_name ?? 'Company details' }]} />
    <PageHeader title={editing ? 'Edit company' : company?.display_name ?? 'Company details'}
      lede={editing ? 'Update company details and defaults. Required fields are marked; locked fields keep their saved values.' : 'Business identity, financial defaults and presentation settings.'}
      actions={!editing && company ? <div className="janso-form-actions"><a className="janso-btn" href={administrationLink(base + '/configuration', administrationLink(base, back))}>Company configuration</a>{company.status === 'active' && canEdit && <a className="janso-btn janso-btn--primary" href={administrationLink(base + '/edit', administrationLink(base, back))}>Edit company</a>}</div> : undefined} />
    {!loading && company && !editing && <AutomaticCompanySetup company={companyId} canRetry={canEdit} />}
    {loading ? <div role="status" aria-label="Loading company"><Skeleton /><Skeleton /></div>
      : !company ? <>{failure?.status === 404 ? <Notice tone="warning">This company was not found in your workspace. Return to the company directory to choose another company.</Notice>
        : <ErrorState status={asErrorStatus(failure?.status ?? 503)} detail={failure?.message} />}
        {failure?.code === 'step_up_required' ? <a className="janso-btn janso-btn--primary" href={stepUpUrl(companyId)}>Verify sign-in</a>
          : failure?.status !== 403 && failure?.status !== 404 && <Button onClick={() => setRevision(value => value + 1)}>Retry loading company</Button>}</>
        : <>
          {!editing && <Notice><Badge tone={company.status === 'active' ? 'success' : 'neutral'}>{company.status}</Badge> {company.code ?? 'Company'}
            {company.first_posted_at ? ' · Financial identity and calendar settings are locked after posting.' : ' · Field access and posting reservations determine which settings can be changed.'}</Notice>}
          {failure && <Notice tone="danger">{failure.message}{failure.status === 409 && <Button variant="ghost" onClick={() => dirty ? setLeave('reload') : setRevision(value => value + 1)}>Reload company</Button>}</Notice>}
          {saved && <Notice tone="success">Company saved. <a className="janso-link" href={administrationLink(base, back)}>View company</a></Notice>}
          {editing && !writable && <Notice>This company is read-only for your current access or status.</Notice>}
          {editing && (referenceFailure || stateFailure) && <Notice tone="danger">Company choices could not be loaded. Your changes are retained. <Button variant="ghost" disabled={saving} onClick={() => setChoiceRevision(value => value + 1)}>Reload choices</Button></Notice>}
          <FormLayout aside={editing ? <aside aria-label="Before you save" className="janso-flow">
            <SectionHeader title="Before you save" />
            <ListRow primary={company.display_name} meta={'Code: ' + (company.code ?? 'Not set')}
              figure={<Badge tone={company.status === 'active' ? 'success' : 'neutral'}>{company.status}</Badge>} />
            <p className="janso-fine">{company.first_posted_at ? 'Financial identity and calendar settings are locked after posting.' : 'Field access and posting reservations determine which settings can be changed.'}</p>
            <p className="janso-fine">Only fields you can change are enabled. Save applies your changes to this company; Cancel returns without saving.</p>
          </aside> : undefined}>
          <form ref={form} onSubmit={save} noValidate aria-label={editing ? 'Company editor' : 'Company details'}><Card><CardBody><div className="janso-flow">
            {groups.map(group => {
              const groupFields = visible.filter(field => field.group === group);
              const customFields = companyCustomFields(groupFields);
              return <section key={group} className="janso-flow" aria-label={groupNames[group] ?? group}>
                <SectionHeader title={groupNames[group] ?? group} description={editing ? groupDescriptions[group] : undefined} />
                {!editing ? <ReviewList items={groupFields.map(field => ({ label: companyFieldLabel(field), value: displayValue(field) }))} />
                  : <FieldGrid disabled={saving}>{groupFields.some(field => field.source !== 'custom') && <div className="janso-form-grid">
                    {groupFields.filter(field => field.source !== 'custom').map(field => {
                      const key = field.key, value = draft[key], locked = !writable || !field.writable;
                      const common = { label: companyFieldLabel(field), disabled: locked, required: field.required && !locked, error: errors[key],
                        hint: !field.writable ? 'Read-only: access policy, company status or posting protection.' : field.help_text ?? undefined };
                      if (field.data_type === 'long_text') return <div className="janso-field janso-form-grid__full" key={key}>
                        <FieldLabel htmlFor={inputPrefix + key} required={common.required}>{common.label}</FieldLabel>
                        <textarea id={inputPrefix + key} className="janso-input" rows={4} disabled={locked} required={common.required}
                          maxLength={typeof field.validation?.max_length === 'number' ? field.validation.max_length : undefined}
                          value={String(value ?? '')} aria-invalid={errors[key] ? true : undefined}
                          aria-describedby={[errors[key] ? inputPrefix + key + '-error' : '', common.hint ? inputPrefix + key + '-hint' : ''].filter(Boolean).join(' ') || undefined}
                          onChange={event => change(key, event.target.value)} />
                        {errors[key] && <p className="janso-error" role="alert" id={inputPrefix + key + '-error'}>{errors[key]}</p>}
                        {common.hint && <p className="janso-hint" id={inputPrefix + key + '-hint'}>{common.hint}</p>}
                      </div>;
                      if (field.data_type === 'boolean') return <Select key={key} {...common} value={String(value)} options={[{ value: 'true', label: 'Yes' }, { value: 'false', label: 'No' }]} onChange={next => change(key, next === 'true')} />;
                      if (key === 'business_roles') {
                        const choices = (classifications?.business_roles ?? []).map(item => ({ id: item.code, label: item.label }));
                        const selected = (Array.isArray(value) ? value as string[] : []).map(id => choices.find(option => option.id === id) ?? { id, label: id });
                        return <SearchSelect key={key} {...common} multiple options={choices} value={selected.map(item => item.id)} selected={selected} onChange={next => change(key, [...next].sort())} />;
                      }
                      const choices = options(field);
                      if (choices) {
                        const current = value == null ? '' : String(value);
                        const available = current && !choices.some(option => option.value === current) ? [{ value: current, label: current + ' (saved value)' }, ...choices] : choices;
                        return <Select key={key} {...common} disabled={locked || referencesLoading || (key === 'state_code' && statesLoading)} value={current}
                          placeholder={field.required ? 'Choose an option' : 'Not set'} options={available} onChange={next => change(key, next)} />;
                      }
                      return <TextField key={key} {...common} type={field.data_type === 'date' ? 'date' : 'text'} inputMode={['integer', 'decimal'].includes(field.data_type ?? '') ? 'decimal' : 'text'}
                        maxLength={typeof field.validation?.max_length === 'number' ? field.validation.max_length : undefined}
                        value={value == null ? '' : String(value)} onChange={event => change(key, event.target.value)} />;
                    })}
                    </div>}{customFields.length > 0 && <CustomFields fields={customFields} values={(draft.custom_fields ?? {}) as Record<string, unknown>} nativeValues={draft}
                      currencies={currencies.map(item => item.code)} disabled={saving || !writable} errors={errors} onChange={value => change('custom_fields', value)} />}
                  </FieldGrid>}
              </section>;
            })}
            {errors.custom_fields && <Notice tone="danger">{errors.custom_fields}</Notice>}
            </div></CardBody>
            {editing && <FormActions cancel={{ href: back, onClick: event => { if (dirty || saving) { event.preventDefault(); if (!saving) navigate(back); } } }}>
              <Button type="submit" disabled={!writable || referencesLoading || referenceFailure || statesLoading || stateFailure || !dirty} loading={saving} loadingLabel="Saving company…">Save company</Button>
            </FormActions>}
          </Card></form></FormLayout>
        </>}
    <ConfirmDialog open={leave !== null} title="Discard unsaved company changes?" confirmLabel="Discard changes" cancelLabel="Keep editing" onCancel={() => setLeave(null)}
      onConfirm={() => { const target = leave; setLeave(null); setDraft(company ?? {}); if (target === 'reload') setRevision(value => value + 1); else if (target) { discarded.current = true; goTo(target); } }}>
      Your unsaved changes will be lost. The saved company will be retained.
    </ConfirmDialog>
  </div>;
}
