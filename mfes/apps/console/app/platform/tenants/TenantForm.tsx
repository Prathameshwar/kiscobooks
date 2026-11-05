'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, FormActions, FormLayout, Notice, PageHeader, PageNavigation, SectionHeader, Select, TextField } from '@janso/ui';
import { administrationBackLabel, administrationDirectoryReturn, administrationLink, administrationReturn } from '../../lib/administration-navigation';
import { PlatformError, platformCall, platformFailure, type PlatformFailure } from '../../lib/platform-api';
import { useEditorDraft } from '../useEditorDraft';
import { platformHistoryHref } from '../../components/PlatformHistory';
import { TenantCreateWizard } from './TenantCreateWizard';

type Detail = components['schemas']['PlatformTenantDetail'];
type Choices = components['schemas']['TenantChoices'];
type Draft = { name: string; state_code: string; administrator_name: string; administrator_email: string; country_code: string; currency_code: string; timezone: string; locale: string };
const initial: Draft = { name: '', state_code: '', administrator_name: '', administrator_email: '', country_code: 'IN', currency_code: 'INR', timezone: 'Asia/Kolkata', locale: 'en' };

export function TenantForm({ scope, tenantId, returnTo }: { scope: string; tenantId?: string; returnTo?: string }) {
  return tenantId ? <TenantEditor scope={scope} tenantId={tenantId} returnTo={returnTo} /> : <TenantCreateWizard scope={scope} returnTo={returnTo} />;
}

function TenantEditor({ scope, tenantId, returnTo }: { scope: string; tenantId: string; returnTo?: string }) {
  const back = returnTo ? administrationReturn('tenants', returnTo) : '/platform/tenants/' + tenantId;
  const directory = administrationDirectoryReturn('tenants', back);
  const returnPath = '/platform/tenants/' + tenantId + '/edit' + (back !== '/platform/tenants' ? '?returnTo=' + encodeURIComponent(back) : '');
  const editor = useEditorDraft(scope + ':' + tenantId, initial), { draft } = editor;
  const [choices, setChoices] = useState<Choices | null>(null), [detail, setDetail] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(false), [reload, setReload] = useState(0);
  const [error, setError] = useState<PlatformFailure | null>(null), [fields, setFields] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false), busy = useRef(false), form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    Promise.all([platformCall<Choices>('/v1/platform/tenant-options', 'GET', undefined, undefined, controller.signal),
      platformCall<Detail>('/v1/platform/tenants/' + tenantId, 'GET', undefined, undefined, controller.signal)])
      .then(([options, record]) => {
        if (controller.signal.aborted) return;
        if (![options.countries, options.currencies, options.languages, options.timezones].every(items => items?.length) || !Array.isArray(options.states)) throw { status: 503, message: 'Regional choices are unavailable. Try loading the form again.' };
        setChoices(options); setDetail(record);
        editor.populate({ name: record.name, state_code: record.default_state_code ?? '', administrator_name: '', administrator_email: record.primary_contact_email,
          country_code: record.default_country_code, currency_code: record.default_currency_code, timezone: record.default_timezone, locale: record.default_locale });
        setLoading(false);
      }).catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setChoices(null); setLoading(false); } });
    return () => controller.abort();
    // Population preserves recovered or entered drafts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, reload]);
  function change(field: keyof Draft, value: string) {
    editor.change({ [field]: value, ...(field === 'country_code' ? { state_code: '' } : {}) });
    setFields(current => ({ ...current, [field]: '', ...(field === 'country_code' ? { state_code: '' } : {}) })); setError(null); setSaved(false);
  }
  function validate() {
    const invalid: Record<string, string> = {};
    if (!draft.name.trim() || draft.name.length > 200 || /[\x00-\x1f\x7f]/.test(draft.name)) invalid.name = 'Enter a valid name with up to 200 characters.';
    if (draft.administrator_email.length > 320 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.administrator_email.trim())) invalid.administrator_email = 'Enter a valid email address.';
    for (const [field, items] of [['country_code', choices?.countries], ['currency_code', choices?.currencies], ['timezone', choices?.timezones], ['locale', choices?.languages]] as [keyof Draft, Choices['countries'] | undefined][]) {
      if (!items?.some(item => item.code === draft[field])) invalid[field] = 'Choose an available option.';
    }
    if (draft.state_code && !choices?.states.some(item => item.code === draft.state_code && item.country_code === draft.country_code)) invalid.state_code = 'Choose an available state for this country.';
    setFields(invalid);
    const first = Object.keys(invalid)[0];
    if (first) { (form.current?.elements.namedItem(first) as HTMLInputElement | null)?.focus(); return false; }
    return !!form.current?.reportValidity();
  }
  async function save() {
    if (busy.current || loading || !choices || detail?.status === 'closed' || !validate()) return;
    busy.current = true; setPending(true); setError(null); setSaved(false);
    try {
      const value = await platformCall<Detail>('/v1/platform/tenants/' + tenantId, 'PATCH', {
        name: draft.name.trim(), primary_contact_email: draft.administrator_email.trim(), default_country_code: draft.country_code,
        default_state_code: draft.state_code || null, default_currency_code: draft.currency_code, default_timezone: draft.timezone, default_locale: draft.locale,
      });
      setDetail(value); setSaved(true); editor.saved();
      editor.populate({ ...draft, name: value.name, state_code: value.default_state_code ?? '', administrator_email: value.primary_contact_email,
        country_code: value.default_country_code, currency_code: value.default_currency_code, timezone: value.default_timezone, locale: value.default_locale });
    } catch (value) {
      const failure = platformFailure(value); setError(failure);
      const mapping: Record<string, string> = { primary_contact_email: 'administrator_email', default_country_code: 'country_code', default_state_code: 'state_code', default_currency_code: 'currency_code', default_timezone: 'timezone', default_locale: 'locale' };
      const invalid = Object.fromEntries(Object.entries(failure.fields ?? {}).map(([field, message]) => [mapping[field] ?? field, message || 'Check this value and try again.'])); setFields(invalid);
      requestAnimationFrame(() => (form.current?.elements.namedItem(Object.keys(invalid)[0]) as HTMLInputElement | null)?.focus());
    } finally { busy.current = false; setPending(false); }
  }
  function cancel(event: React.MouseEvent<HTMLAnchorElement>) {
    if (pending || editor.touched.current && !window.confirm('Discard your unsaved changes?')) event.preventDefault(); else editor.saved();
  }
  const regional = (name: keyof Draft, label: string, items: Choices['countries']) => <Select name={name} label={label} required placeholder={'Choose ' + label.toLowerCase().replace('default ', '')} value={draft[name]} error={fields[name]} disabled={pending} options={items.map(item => ({ value: item.code, label: item.name === item.code ? item.name : item.name + ' (' + item.code + ')' }))} onChange={value => change(name, value)} />;
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants', href: directory }, { label: detail?.name ?? 'Tenant details', href: administrationLink('/platform/tenants/' + tenantId, directory) }, { label: 'Edit tenant' }]} onNavigate={cancel} />
    {detail ? <a className="janso-link" href={administrationLink(platformHistoryHref('tenant', detail.id), administrationLink('/platform/tenants/' + tenantId, directory))} onClick={cancel}>View tenant history</a> : null}
    <PageHeader title="Edit tenant" lede="Update workspace details and regional defaults." />
    <PlatformError value={error} returnTo={returnPath} onNavigate={() => { editor.preserve(); editor.touched.current = false; }} />
    {editor.restored && !saved ? <Notice>Your draft has been restored. Review it before saving.</Notice> : null}
    {saved ? <Notice tone="success">Tenant details updated.</Notice> : null}
    {loading ? <p role="status">Loading tenant form…</p> : !choices ? ([401, 403, 404].includes(error?.status ?? 0) ? null : <Button variant="ghost" onClick={() => setReload(value => value + 1)}>Retry loading form</Button>)
      : detail?.status === 'closed' ? <Notice tone="warning">A closed tenant cannot be changed.</Notice>
      : <FormLayout aside={<><SectionHeader title="Changes and access" /><p className="janso-fine">These changes update workspace metadata and defaults. Tenant suspension and restoration are managed from the directory.</p><p className="janso-fine">Administrative changes are audited and require a recent sign-in.</p></>}>
        <form ref={form} noValidate onSubmit={event => { event.preventDefault(); void save(); }}>
          <Card><CardBody><div className="janso-flow">
            <SectionHeader title="Workspace" />
            <TextField label="Tenant name" name="name" required maxLength={200} autoComplete="organization" value={draft.name} error={fields.name} disabled={pending} onChange={event => change('name', event.target.value)} />
            <SectionHeader title="Primary contact" description="Changing the contact does not replace the workspace administrator." />
            <TextField label="Primary contact email" name="administrator_email" type="email" required maxLength={320} autoComplete="email" value={draft.administrator_email} error={fields.administrator_email} disabled={pending} onChange={event => change('administrator_email', event.target.value)} />
            <SectionHeader title="Regional defaults" description="Defaults for new companies; existing company settings and posted records retain their own values." />
            <div className="janso-form-grid janso-form-grid--pair">{regional('country_code', 'Default country', choices.countries)}
              <Select name="state_code" label="State" value={draft.state_code} disabled={pending || !choices.states.some(item => item.country_code === draft.country_code)} placeholder="Choose a state" error={fields.state_code} options={choices.states.filter(item => item.country_code === draft.country_code).map(item => ({ value: item.code, label: item.name }))} onChange={value => change('state_code', value)} />
            </div>
            <div className="janso-form-grid">{regional('currency_code', 'Default currency', choices.currencies)}{regional('timezone', 'Default timezone', choices.timezones)}{regional('locale', 'Default language', choices.languages)}</div>
          </div></CardBody><FormActions cancel={{ href: back, onClick: cancel }}><Button type="submit" loading={pending} loadingLabel="Saving…">Save changes</Button></FormActions></Card>
        </form>
      </FormLayout>}
  </div>;
}
