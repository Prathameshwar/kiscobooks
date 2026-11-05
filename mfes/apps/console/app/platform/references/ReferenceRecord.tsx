'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Badge, Button, Card, CardBody, ConfirmDialog, FormActions, FormLayout, Notice, PageHeader, PageNavigation, ReviewList, SectionHeader, SearchSelect, TextField } from '@janso/ui';
import { platformCall as call, platformFailure, PlatformError, type PlatformFailure } from '../../lib/platform-api';
import { catalogConfig, catalogReturnTo, type Catalog, type ReferenceDetail, type ReferenceOptions } from './reference-config';
import { PlatformHistory } from '../../components/PlatformHistory';
import { useUnsavedChanges } from '../../lib/use-unsaved-changes';

type Draft = Record<string, string>;
export function ReferenceRecord({ catalog, code, mode, returnTo, action }: { catalog: Catalog; code?: string; mode: 'new' | 'view' | 'edit'; returnTo?: string; action?: string }) {
  const config = catalogConfig[catalog], base = '/platform/references/' + catalog, back = catalogReturnTo(catalog, returnTo), creating = mode === 'new', viewing = mode === 'view';
  const [record, setRecord] = useState<ReferenceDetail | null>(null), [draft, setDraft] = useState<Draft>({}), [options, setOptions] = useState<ReferenceOptions>({ countries: [], currencies: [] });
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(false), [error, setError] = useState<PlatformFailure | null>(null), [fields, setFields] = useState<Record<string, string>>({}), [message, setMessage] = useState(''), [reload, setReload] = useState(0);
  const [confirmation, setConfirmation] = useState<'archive' | 'restore' | null>(null), [reason, setReason] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const busy = useRef(false);
  const createdCode = useRef<string | undefined>(undefined);
  const initial = useRef(''), dirty = !viewing && initial.current !== JSON.stringify(draft);
  const path = '/v1/platform/references/' + catalog + (code ? '/' + code : '');
  const currentHref = code ? base + '/' + code + (mode === 'edit' ? '/edit' : '') : base + '/new';
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null); setLoadFailed(false);
    const readPath = creating && createdCode.current ? path + '/' + createdCode.current : path;
    Promise.all([creating && !createdCode.current ? Promise.resolve(null) : call<ReferenceDetail>(readPath, 'GET', undefined, undefined, controller.signal), call<ReferenceOptions>('/v1/platform/references/options', 'GET', undefined, undefined, controller.signal)])
      .then(([value, choices]) => { if (controller.signal.aborted) return;
        const next: Draft = Object.fromEntries(config.fields.map(field => [field.key, value ? String(value.data[field.key as keyof typeof value.data] ?? '') : field.key === 'minor_unit' ? '2' : '']));
        setRecord(value); setDraft(next); initial.current = JSON.stringify(next); setOptions(choices); setLoading(false);
        if (viewing && ['archive', 'restore'].includes(action ?? '')) setConfirmation(action as 'archive' | 'restore');
      }).catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoadFailed(true); setLoading(false); } });
    return () => controller.abort();
  }, [path, reload, creating, viewing, action, config]);
  useUnsavedChanges(() => dirty || busy.current);
  const reloadRecord = () => { if (!busy.current && (!dirty || window.confirm('Discard unsaved changes and load the latest record?'))) setReload(value => value + 1); };
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy.current || uncertain || loadFailed || loading || (creating && record)) return;
    const errors: Record<string, string> = {};
    for (const field of config.fields) { const value = (draft[field.key] ?? '').trim();
      if (!value && !field.optional) errors[field.key] = 'Enter ' + field.label.toLowerCase() + '.';
      else if (value && (value.length > field.max || /[\x00-\x1f\x7f]/.test(value) || (field.pattern && !new RegExp('^(?:' + field.pattern + ')$').test(value)))) errors[field.key] = 'Enter a valid ' + field.label.toLowerCase() + '.';
    }
    if (catalog === 'states' && !draft.code?.startsWith(draft.country_code + '-')) errors.code = 'The state code must start with its country code.';
    if (catalog === 'states' && draft.tax_jurisdiction_code && draft.country_code !== 'IN') errors.tax_jurisdiction_code = 'GST jurisdiction codes apply only to India.';
    if (Object.keys(errors).length) { setFields(errors); setError({ status: 422, message: 'Check the highlighted fields.' }); document.querySelector<HTMLInputElement>('[name="' + Object.keys(errors)[0] + '"]')?.focus(); return; }
    busy.current = true; setPending(true); setError(null); setFields({}); setMessage('');
    const data = { kind: config.kind, is_active: record?.is_active ?? true, ...Object.fromEntries(config.fields.map(field => [field.key, field.numeric ? Number(draft[field.key]) : (draft[field.key] ?? '').trim() || (field.optional ? null : '')])) };
    try { const result = await call<ReferenceDetail>(path, creating ? 'POST' : 'PATCH', creating ? data : { version: record!.version, data });
      const next = Object.fromEntries(config.fields.map(field => [field.key, String(result.data[field.key as keyof typeof result.data] ?? '')]));
      setRecord(result); setDraft(next); if (creating) createdCode.current = result.code; initial.current = JSON.stringify(next); setMessage(creating ? config.singular.charAt(0).toUpperCase() + config.singular.slice(1) + ' created.' : 'Changes saved.');
    } catch (value) { const failure = platformFailure(value); setError(failure); if (failure.status >= 500) setUncertain(true); setFields(Object.fromEntries(Object.entries(failure.fields ?? {}).map(([key, value]) => [key.split('.').at(-1) ?? key, value]))); } finally { busy.current = false; setPending(false); }
  }
  async function changeAvailability() {
    if (!record || !confirmation || busy.current || uncertain) return;
    if (reason.trim().length < 3) { setError({ status: 422, message: 'Enter a reason with at least 3 characters.' }); return; }
    busy.current = true; setPending(true); setError(null);
    try { const value = await call<ReferenceDetail>('/v1/platform/references/' + catalog + '/' + record.code + '/' + confirmation, 'POST', { version: record.version, reason: reason.trim() });
      setRecord(value); setConfirmation(null); setMessage(confirmation === 'archive' ? 'Record archived. Existing records and history are retained.' : 'Record restored.');
    } catch (value) { const failure = platformFailure(value); setError(failure); if (failure.status >= 500) setUncertain(true); } finally { busy.current = false; setPending(false); }
  }
  const fieldsDisabled = viewing || pending || uncertain || (creating && !!record);
  const indianState = catalog === 'states' && draft.country_code === 'IN';
  const displayFields = config.fields.map(field => indianState && field.key === 'code' ? { ...field, label: 'ISO reference code' }
    : indianState && field.key === 'tax_jurisdiction_code' ? { ...field, label: 'GST state code', hint: 'Official GST state code. Assigned automatically and permanently fixed for this state.' } : field);
  // One guard for the back chevron, the crumbs and Cancel alike.
  const leave = (event: React.MouseEvent<HTMLAnchorElement>) => { if (busy.current || dirty && !window.confirm('Discard unsaved changes?')) event.preventDefault(); };
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: config.title.toLowerCase() }} onNavigate={leave} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Reference data', href: '/platform/references' }, { label: config.title, href: back }, { label: creating ? 'New ' + config.singular : record?.name ?? (viewing ? 'Details' : 'Edit ' + config.singular) }]} />
    <PageHeader title={creating ? 'New ' + config.singular : viewing ? record?.name ?? config.title + ' details' : 'Edit ' + config.singular} lede={config.description} actions={viewing && record ? <a className="janso-btn janso-btn--primary" href={base + '/' + record.code + '/edit?returnTo=' + encodeURIComponent(back)}>Edit details</a> : undefined} />
    {message ? <Notice tone="success">{message}</Notice> : null}<PlatformError value={error} returnTo={currentHref + '?returnTo=' + encodeURIComponent(back)} />
    {uncertain ? <Notice tone="warning">The change could not be confirmed. Your values are retained. Return to the directory and review the saved record before starting another change.</Notice> : null}
    {error?.status === 409 ? <Button variant="ghost" onClick={reloadRecord}>Reload latest record</Button> : null}
    {loading ? <p role="status">Loading reference details…</p> : loadFailed || (!record && !creating) ? <Button variant="ghost" onClick={() => setReload(value => value + 1)}>Retry</Button> : <>
      {record ? <Notice tone={record.sync_ready ? 'info' : 'warning'}>{record.sync_ready ? 'Synchronized with service reference catalogs.' : <>Sync pending. New selections become available after Catalog and Accounting confirm delivery. <Button variant="ghost" disabled={pending || uncertain} onClick={reloadRecord}>Check synchronization</Button></>} <Badge tone={record.is_active ? 'success' : 'neutral'}>{record.is_active ? 'Active' : 'Archived'}</Badge></Notice> : null}
      <FormLayout aside={<><SectionHeader title={creating ? 'Before you add a reference' : 'Changes and availability'} />
        <p className="janso-fine">{creating ? 'A new reference becomes selectable once Catalog and Accounting confirm delivery. Its code and financial identifiers stay fixed once created.' : 'Codes and protected financial identifiers cannot change after creation. Archiving withdraws a reference from new configuration and retains every existing record.'}</p>
        <p className="janso-fine">Reference changes are platform-wide, are audited, and require a recent sign-in.</p></>}>
        <form noValidate onSubmit={save}><Card><CardBody><div className="janso-flow"><SectionHeader title="Reference details" description="Codes and protected financial identifiers stay fixed after creation. Changes are audited." />
        {viewing ? <ReviewList items={[...displayFields.map(field => ({ label: field.label,
          value: field.options ? options[field.options].find(item => item.code === draft[field.key])?.name ?? draft[field.key] : draft[field.key] || 'Not specified' })),
          { label: 'Revision', value: record?.version }]} /> : <div className="janso-form-grid">{displayFields.map(field => {
          const protectedField = (indianState && field.key === 'tax_jurisdiction_code') || (!creating && record?.protected_fields.includes(field.key));

          return field.options ? <SearchSelect key={field.key} label={field.label} name={field.key} required value={draft[field.key] || null} scopeKey={catalog + ':' + field.key} selected={draft[field.key] ? { id: draft[field.key], label: options[field.options].find(item => item.code === draft[field.key])?.name ?? draft[field.key] + ' (unavailable)' } : null} placeholder={'Choose ' + field.label.toLowerCase()} disabled={fieldsDisabled || !!protectedField} error={fields[field.key]} options={options[field.options].map(item => ({ id: item.code, label: item.name, meta: item.code }))} onChange={value => { setDraft(current => ({ ...current, [field.key]: value ?? '' })); setFields({}); }} />
            : <TextField key={field.key} label={field.label} name={field.key} value={draft[field.key] ?? ''} required={!field.optional} readOnly={!!protectedField} disabled={fieldsDisabled} maxLength={field.max} pattern={field.pattern} inputMode={field.numeric ? 'numeric' : undefined} hint={indianState && field.key === 'tax_jurisdiction_code' ? field.hint : protectedField ? 'This identifier is protected after creation.' : field.hint} error={fields[field.key]} onChange={event => { setDraft(current => ({ ...current, [field.key]: event.target.value })); setFields({}); }} />;
        })}</div>}
      </div></CardBody><FormActions cancel={{ href: back, label: viewing || message ? 'Back to ' + config.title.toLowerCase() : 'Cancel', onClick: leave }}>
        {!viewing && !(creating && record) ? <Button type="submit" loading={pending} disabled={uncertain}>{creating ? 'Create ' + config.singular : 'Save changes'}</Button> : null}
        {creating && record ? <a className="janso-btn janso-btn--primary" href={base + '/' + record.code + '?returnTo=' + encodeURIComponent(back)}>View details</a> : null}
      </FormActions></Card></form></FormLayout>
      {record && viewing ? <Card><CardBody><SectionHeader title="Availability" description="Delete archives this reference and retains all existing records. Active dependencies can prevent archiving." /><Button variant={record.is_active ? 'danger' : 'ghost'} disabled={pending} onClick={() => { setReason(''); setError(null); setConfirmation(record.is_active ? 'archive' : 'restore'); }}>{record.is_active ? 'Delete (archive)' : 'Restore'}</Button></CardBody></Card> : null}
      {record ? <PlatformHistory entityType="reference_revision" entityId={record.id} revision={record.version} /> : null}
    </>}
    <ConfirmDialog open={confirmation !== null} title={confirmation === 'archive' ? 'Archive this ' + config.singular + '?' : 'Restore this ' + config.singular + '?'} confirmLabel={confirmation === 'archive' ? 'Archive record' : 'Restore record'} tone={confirmation === 'archive' ? 'danger' : 'default'} busy={pending} onCancel={() => { setConfirmation(null); setError(null); }} onConfirm={changeAvailability}>
      <p>{confirmation === 'archive' ? 'This record will no longer be selectable for new configuration. Its code and existing history are retained.' : 'This record will become selectable once its active dependencies and service synchronization are ready.'}</p>
      <TextField label="Reason" required minLength={3} maxLength={500} value={reason} disabled={pending} onChange={event => setReason(event.target.value)} /><PlatformError value={error} returnTo={currentHref + '?returnTo=' + encodeURIComponent(back)} />
    </ConfirmDialog>
  </div>;
}
