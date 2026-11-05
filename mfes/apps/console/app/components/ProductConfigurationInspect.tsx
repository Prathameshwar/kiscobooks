'use client';
import { useEffect, useState } from 'react';
import type { components } from '@janso/api-client/catalog';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, Notice, PageHeader, ReviewList, Select, TextField } from '@janso/ui';
import { companyToday, configBack, configLink, configMetadata, configRoot, useConfigCommand, useConfigRead, type ConfigEffective, type ConfigMetadata } from '../lib/product-configuration';
import { validMasterDate } from '../lib/catalog-masters';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import { ConfigurationEffectiveValues, ConfigurationFailure, ConfigurationLoading, ConfigurationNavigation, ConfigurationReference } from './ProductConfigurationCommon';

export function ProductConfigurationEffective({ company, timezone, returnTo, initialItemId, initialFamilyId, initialKind = 'GOODS' }: { company: string; timezone: string; returnTo?: string; initialItemId?: string; initialFamilyId?: string; initialKind?: 'GOODS' | 'SERVICE' }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [date, setDate] = useState(() => companyToday(timezone)), [kind, setKind] = useState<'GOODS' | 'SERVICE'>(initialKind), [path, setPath] = useState<string>(), [error, setError] = useState(''), [metadata, setMetadata] = useState<ConfigMetadata>();
  const result = useConfigRead<ConfigEffective>(path, value => { if (value.company_id !== company || value.as_of !== date || value.kind !== kind || !Array.isArray(value.settings) || !Array.isArray(value.sources)) throw { status: 502, message: 'The effective settings response could not be verified.' }; });
  useEffect(() => { const controller = new AbortController(); configMetadata(company, 'update', controller.signal).then(value => { if (!controller.signal.aborted) setMetadata(value); }).catch(() => {}); return () => controller.abort(); }, [company]);
  const back = configBack(returnTo);
  function clear() { setPath(undefined); setError(''); setErrors({}); }
  function inspect(event: React.FormEvent) {
    event.preventDefault();
    const invalid: Record<string, string> = {};
    if (!validMasterDate(date)) invalid.date = 'Choose a valid inspection date.';
    setErrors(invalid);
    if (Object.keys(invalid).length) { setError('Choose a valid inspection date.'); return; }
    const query = new URLSearchParams({ as_of: date, kind });
    if (initialItemId) query.set('item_id', initialItemId);
    else if (initialFamilyId) query.set('family_id', initialFamilyId);
    const next = `/v1/companies/${company}/product-configuration/effective?${query}`; if (next === path) result.refresh(); else setPath(next); setError('');
  }
  return <div className="janso-page"><ConfigurationNavigation title="Effective product settings" back={back} /><PageHeader title="Effective product settings" lede="Inspect dated defaults, their source revisions, applicability and native restrictions." /><Card><CardHeader title="Inspection context" /><CardBody><form noValidate onSubmit={inspect}><div className="janso-form-grid"><TextField label="As of date" type="date" required value={date} error={errors.date} onChange={event => { clear(); setDate(event.target.value); }} /><Select label="Product kind" disabled={!!(initialItemId || initialFamilyId)} value={kind} options={[{ value: 'GOODS', label: 'Goods' }, { value: 'SERVICE', label: 'Services' }]} onChange={value => { clear(); setKind(value as 'GOODS' | 'SERVICE'); }} /></div>{error && <Notice tone="danger">{error}</Notice>}<div className="janso-form-actions"><Button type="submit" loading={result.loading}>Inspect settings</Button></div></form></CardBody></Card>
    <AccessFocusErrors fields={errors} /><ConfigurationFailure failure={result.failure} retry={result.refresh} />{result.loading ? <ConfigurationLoading /> : result.data && path ? <ConfigurationEffectiveValues value={result.data} metadata={metadata} returnTo={configLink(configRoot + "/effective", back)} /> : !result.failure && <Notice>Inspect company defaults for the selected date. Product links also apply the product’s native restrictions.</Notice>}
  </div>;
}

type AdoptionPreview = components['schemas']['AdoptionPreview'];
type AdoptionResult = components['schemas']['AuthoringResult'];
const adoptionReason = (reason: string) => reason === 'active_structural_adoption_unsupported' ? 'This product or family is active. Structural adoption is supported only for drafts.' : reason.replaceAll('_', ' ');
export function ProductConfigurationAdoption({ company, timezone, canAdopt, returnTo, initialItemId }: { company: string; timezone: string; canAdopt: boolean; returnTo?: string; initialItemId?: string }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [item, setItem] = useState<string | null>(initialItemId ?? null), [date, setDate] = useState(() => companyToday(timezone)), [path, setPath] = useState<string>(), [reviewing, setReviewing] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState('');
  const command = useConfigCommand(), guard = useAccessDraft(reviewing || command.uncertain, command.pending), back = configBack(returnTo);
  const preview = useConfigRead<AdoptionPreview>(path, value => { if (value.resolution_version !== 2 || value.item_id !== item || value.purpose !== 'DRAFT_CONFIGURATION' || value.active_adoption_supported !== false || !Number.isSafeInteger(value.expected_version) || typeof value.preview_token !== 'string' || !value.preview_token || !Array.isArray(value.blocked_reasons) || !Array.isArray(value.missing)) throw { status: 502, message: 'The product adoption review could not be verified.' }; });
  function clear() { if (command.pending || command.uncertain) return; setPath(undefined); setReviewing(false); setMessage(''); setError(''); setErrors({}); command.clear(); }
  function inspect(event: React.FormEvent) {
    event.preventDefault(); if (!canAdopt || command.pending || command.uncertain) return;
    const invalid: Record<string, string> = {};
    if (!item) invalid.item = 'Choose a product to review.';
    if (!validMasterDate(date)) invalid.date = 'Choose a valid adoption date.';
    setErrors(invalid);
    if (Object.keys(invalid).length) { setError('Choose a product and a valid date before reviewing adoption.'); return; }
    const next = `/v1/companies/${company}/items/${item}/configuration-adoption/preview?${new URLSearchParams({ as_of: date })}`;
    command.clear(); setReviewing(false); setMessage(''); setError(''); if (path === next) preview.refresh(); else setPath(next);
  }
  async function adopt() {
    if (!canAdopt || !preview.data?.eligible || preview.data.blocked_reasons?.length || preview.data.missing.length || !item || command.pending || command.blocked && !command.uncertain) return;
    const current = preview.data;
    const result = await command.execute<AdoptionResult>({ path: `/v1/companies/${company}/items/${item}/configuration-adoption`, method: 'POST', body: { expected_version: current.expected_version, as_of: date, preview_token: current.preview_token } }, value => { if (value.item_id !== item || !Number.isSafeInteger(value.item_version) || Number(value.item_version) <= current.expected_version) throw { status: 502, message: 'The adoption result could not be verified.' }; });
    if (result) { setReviewing(false); setPath(undefined); setMessage('Draft product defaults adopted successfully. Review the product definition before activation.'); }
  }
  const links = (ids: string[]) => ids.length ? <ul>{ids.map((id, index) => <li key={id}><a className="janso-link" href={configLink(configRoot + '/revisions/' + id, configLink(configRoot + '/adopt', back))} onClick={guard.leave}>View source revision {index + 1}</a></li>)}</ul> : 'Native defaults';
  return <div className="janso-page"><ConfigurationNavigation title="Product configuration adoption" back={back} onLeave={guard.leave} /><PageHeader title="Product configuration adoption" lede="Review and explicitly adopt published defaults for a draft product. Existing active products are protected." />
    {!canAdopt ? <Notice>Product configuration adopt permission in this company is required to inspect and apply adoption.</Notice> : <>
      <Card><CardHeader title="Draft product context" /><CardBody><form noValidate onSubmit={inspect}><div className="janso-form-grid"><ConfigurationReference company={company} source="items" label="Product / SKU" value={item} required error={errors.item} disabled={command.pending || command.uncertain} onChange={value => { clear(); setItem(value); }} /><TextField label="As of date" type="date" required value={date} error={errors.date} disabled={command.pending || command.uncertain} onChange={event => { clear(); setDate(event.target.value); }} /></div>{error && <Notice tone="danger">{error}</Notice>}<div className="janso-form-actions"><Button type="submit" loading={preview.loading} disabled={command.pending || command.uncertain}>Review adoption</Button></div></form></CardBody></Card>
      <AccessFocusErrors fields={errors} /><ConfigurationFailure failure={preview.failure} retry={preview.refresh} />{preview.loading ? <ConfigurationLoading /> : preview.data && <Card><CardHeader title="Adoption preview" /><CardBody><ReviewList items={[{ label: 'Eligibility', value: preview.data.eligible ? 'Eligible draft' : 'Blocked' }, { label: 'Current defaults', value: links(preview.data.current_revision_ids) }, { label: 'Proposed defaults', value: links(preview.data.proposed_revision_ids) }]} />{preview.data.missing.length > 0 && <Notice tone="warning">Complete the product requirements first: {preview.data.missing.map(adoptionReason).join(', ')}.</Notice>}{preview.data.blocked_reasons?.map(reason => <Notice key={reason} tone="warning">{adoptionReason(reason)}</Notice>)}{preview.data.eligible && <Button onClick={() => setReviewing(true)} disabled={command.pending}>Adopt reviewed draft defaults</Button>}</CardBody></Card>}
      {message && <Notice tone="success">{message}</Notice>}<Notice>Reviews expire after 15 minutes. A changed product, published default or company policy requires a fresh review. Adoption does not activate a product or change price history.</Notice>
    </>}
    {!reviewing && command.uncertain && <Notice tone="warning">Adoption is unconfirmed. Reopen the retained preview and retry the same request before changing its context.</Notice>}
    <ConfirmDialog open={reviewing} title="Adopt these defaults for this draft product?" confirmLabel={command.uncertain ? 'Retry same adoption' : command.blocked ? 'Review again' : 'Adopt draft defaults'} busy={command.pending} onCancel={() => { if (!command.pending) setReviewing(false); }} onConfirm={() => { if (command.blocked && !command.uncertain) { clear(); } else void adopt(); }}><p>Applies the reviewed source revisions to this draft product. Existing price history is retained. Product activation remains a separate action.</p><ConfigurationFailure failure={command.failure} write />{command.uncertain && <Notice tone="warning">The result is unconfirmed. Retry this exact request to recover its result.</Notice>}</ConfirmDialog>{guard.confirmation}</div>;
}
