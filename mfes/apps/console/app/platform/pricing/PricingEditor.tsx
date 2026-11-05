'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Button, Card, CardBody, Checkbox, ConfirmDialog, Drawer, Notice, ReviewList, SectionHeader, Select, TextField } from '@janso/ui';
import { platformCall, platformFailure, PlatformError, type PlatformFailure } from '../../lib/platform-api';
import { useEditorDraft } from '../useEditorDraft';
import { categories, draftFrom, initial, units, usePricingMoney, type Price, type PriceInput } from './pricing-types';
import { PriceRevisions } from './PriceRevisions';

export function PricingEditor({ id, scope, onClose, onSaved }: { id: string; scope: string; onClose: () => void; onSaved: (message: string) => void }) {
  const editor = useEditorDraft(`${scope}:pricing:${id}`, initial), { draft } = editor;
  const [price, setPrice] = useState<Price | null>(null), [loading, setLoading] = useState(id !== 'new');
  const [pending, setPending] = useState(false), [error, setError] = useState<PlatformFailure | null>(null);
  const [confirm, setConfirm] = useState<'delete' | 'restore' | null>(null), [reload, setReload] = useState(0);
  const busy = useRef(false), formId = useId();
  const money = usePricingMoney();
  useEffect(() => {
    if (id === 'new') return;
    const controller = new AbortController(); setLoading(true); setError(null);
    platformCall<Price>('/v1/platform/pricing/' + id, 'GET', undefined, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setPrice(value); editor.populate(draftFrom(value)); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
    // A recovered draft retains its original version so a stale save fails safely.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reload]);
  const change = (field: keyof typeof draft, value: string) => { editor.change({ [field]: value }); setError(null); };
  const close = () => { if (!pending && (!editor.touched.current || window.confirm('Discard your unsaved pricing changes?'))) { editor.saved(); onClose(); } };
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy.current || loading || !event.currentTarget.reportValidity()) return;
    busy.current = true; setPending(true); setError(null);
    const category = draft.category as PriceInput['category'];
    const body: PriceInput = { code: draft.code, name: draft.name, category, description: draft.description, term_months: Number(draft.term_months) as 1 | 12 | 36, unit: units[category], monthly_fee: draft.monthly_fee,
      unit_price: draft.unit_price, output_unit_price: draft.output_unit_price, tax_percent: draft.tax_percent, fx_inr_per_usd: draft.fx_inr_per_usd, provider: draft.provider, model: draft.model, is_active: draft.is_active === 'true' };
    try {
      const value = await platformCall<Price>('/v1/platform/pricing' + (price ? '/' + price.id : ''), price ? 'PATCH' : 'POST', { ...body, ...(price ? { expected_version: Number(draft.version) } : {}) });
      setPrice(value); editor.saved(); editor.populate(draftFrom(value)); onSaved('Pricing saved. INR and USD prices are up to date.');
    } catch (value) { setError(platformFailure(value)); }
    finally { busy.current = false; setPending(false); }
  }
  async function lifecycle() {
    if (!price || !confirm || busy.current) return;
    busy.current = true; setPending(true); setError(null);
    try {
      const value = await platformCall<Price>(`/v1/platform/pricing/${price.id}/${confirm}`, 'POST', { expected_version: price.version });
      setPrice(value); editor.saved(); editor.populate(draftFrom(value)); setConfirm(null);
      onSaved(confirm === 'delete' ? 'Offering deleted. Its price history is retained.' : 'Offering restored as inactive. Review it before activating.');
    } catch (value) { setError(platformFailure(value)); }
    finally { busy.current = false; setPending(false); }
  }
  const canEdit = !loading && !price?.deleted_at && (id === 'new' || !!price);
  return <Drawer open title={price ? 'Manage offering' : id === 'new' ? 'Add offering' : 'Loading offering'} size="lg" busy={pending} onClose={close}
    footer={<><Button variant="ghost" disabled={pending} onClick={close}>Close</Button>{canEdit ? <Button form={formId} type="submit" loading={pending} loadingLabel="Saving pricing…">Save pricing</Button> : null}</>}>
    <div className="janso-flow">
      <PlatformError value={confirm ? null : error} returnTo="/platform/pricing" onNavigate={() => { editor.preserve(); editor.touched.current = false; }} />
      {editor.restored ? <Notice>Your unsaved pricing draft was restored. Its original version will be checked when saving.</Notice> : null}
      {loading ? <p role="status">Loading offering…</p> : null}
      {!loading && !canEdit && !price ? <Button onClick={() => setReload(value => value + 1)}>Retry loading offering</Button> : null}
      {price?.deleted_at ? <Notice>This offering is deleted. Restore it to edit or activate it.</Notice> : null}
      {canEdit ? <form id={formId} onSubmit={save}><fieldset className="janso-registration__section" disabled={pending}>
        <SectionHeader title="Offering details" description="INR is the base price. USD is derived on the server with a 20% premium." />
        <div className="janso-form-grid janso-form-grid--pair">
          <TextField label="Offering code" required value={draft.code} disabled={!!price} maxLength={40} pattern="[a-z][a-z0-9-]{1,39}" hint="Stable lowercase code, for example sms-india." onChange={event => change('code', event.target.value)} />
          <TextField label="Offering name" required value={draft.name} maxLength={100} onChange={event => change('name', event.target.value)} />
          <Select label="Offering category" value={draft.category} options={categories} onChange={value => editor.change({ category: value, term_months: value === 'platform' ? '12' : '1', unit_price: '0', output_unit_price: '0', provider: '', model: '' })} />
          <Select label="Billing term" value={draft.term_months} disabled={draft.category !== 'platform'} options={draft.category === 'platform' ? [{ value: '12', label: '1 year · billed upfront' }, { value: '36', label: '3 years · billed upfront' }] : [{ value: '1', label: 'Monthly add-on' }]} onChange={value => change('term_months', value)} />
          <TextField label="Monthly fee (INR)" type="number" inputMode="decimal" required min="0" max="999999999.99" step="0.01" value={draft.monthly_fee} onChange={event => change('monthly_fee', event.target.value)} />
          <TextField label="Tax (%)" type="number" inputMode="decimal" required min="0" max="100" step="0.0001" value={draft.tax_percent} onChange={event => change('tax_percent', event.target.value)} />
          <TextField label="INR per USD" type="number" inputMode="decimal" required min="1" max="1000" step="0.0001" value={draft.fx_inr_per_usd} hint="Saved conversion basis, not a live exchange rate." onChange={event => change('fx_inr_per_usd', event.target.value)} />
          {draft.category !== 'platform' ? <TextField label={draft.category === 'llm' ? 'INR per 1,000 input tokens' : `INR per 1,000 ${units[draft.category as keyof typeof units]}`} type="number" inputMode="decimal" required min="0.0001" step="0.0001" value={draft.unit_price} onChange={event => change('unit_price', event.target.value)} /> : null}
          {draft.category === 'llm' ? <TextField label="INR per 1,000 output tokens" type="number" inputMode="decimal" required min="0.0001" step="0.0001" value={draft.output_unit_price} onChange={event => change('output_unit_price', event.target.value)} /> : null}
          {['llm', 'document'].includes(draft.category) ? <><TextField label="AI provider" required={draft.category === 'llm'} maxLength={60} value={draft.provider} onChange={event => change('provider', event.target.value)} /><TextField label="Model identifier" required={draft.category === 'llm'} maxLength={100} value={draft.model} onChange={event => change('model', event.target.value)} /></> : null}
        </div>
        <TextField label="Description and usage limits" maxLength={1000} value={draft.description} onChange={event => change('description', event.target.value)} />
        <Checkbox checked={draft.is_active === 'true'} onChange={event => change('is_active', String(event.target.checked))}>Active for new subscriptions</Checkbox>
        <p className="janso-fine">Save to refresh the price preview below. Existing subscriptions must retain their agreed price revision.</p>
      </fieldset></form> : null}
      {price ? <>
        <SectionHeader title={`Saved price · version ${price.version}`} description={`Tax ${price.tax_percent}%, excluded from listed fees. Usage rates are per 1,000 units.`} />
        <div className="janso-form-grid janso-form-grid--pair">{price.prices.map(value => <Card key={value.currency}><CardBody><SectionHeader title={value.currency} /><ReviewList items={[
          { label: 'Monthly equivalent', value: money(value.monthly_fee, value.currency) },
          { label: `${price.term_months}-month net fee`, value: money(value.term_net, value.currency) },
          { label: 'Tax on subscription fee', value: money(value.term_tax, value.currency) },
          { label: 'Subscription fee incl. tax', value: money(value.term_total, value.currency) },
          ...(price.unit !== 'none' ? [{ label: price.unit === 'tokens' ? 'Per 1,000 input tokens, excl. tax' : `Per 1,000 ${price.unit}, excl. tax`, value: money(value.unit_price, value.currency, 4) }] : []),
          ...(price.unit === 'tokens' ? [{ label: 'Per 1,000 output tokens, excl. tax', value: money(value.output_unit_price, value.currency, 4) }] : []),
        ]} /></CardBody></Card>)}</div>
        <Button variant="ghost" disabled={pending || editor.touched.current} onClick={() => { setError(null); setConfirm(price.deleted_at ? 'restore' : 'delete'); }}>{price.deleted_at ? 'Restore offering' : 'Delete offering'}</Button>
        {id !== 'new' ? <Button variant="ghost" disabled={pending || loading} onClick={() => { if (!editor.touched.current || window.confirm('Discard your draft and reload the saved offering?')) { editor.saved(); setReload(value => value + 1); } }}>Reload saved offering</Button> : null}
        <PriceRevisions id={price.id} version={price.version} />
      </> : null}
    </div>
    <ConfirmDialog open={!!confirm} title={confirm === 'delete' ? 'Delete this offering?' : 'Restore this offering?'} confirmLabel={confirm === 'delete' ? 'Delete offering' : 'Restore offering'} busy={pending} tone={confirm === 'delete' ? 'danger' : 'default'} onCancel={() => { setConfirm(null); setError(null); }} onConfirm={() => void lifecycle()}>
      <p>{confirm === 'delete' ? 'Remove it from new subscriptions. Its code and historical prices are retained.' : 'Restore it as inactive so you can review its prices before activation.'}</p>
      <PlatformError value={error} returnTo="/platform/pricing" onNavigate={() => editor.preserve()} />
    </ConfirmDialog>
  </Drawer>;
}
