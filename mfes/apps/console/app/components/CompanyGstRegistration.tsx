'use client';
import { useEffect, useId, useRef, useState, type MouseEventHandler } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, Disclosure, Drawer, FieldGrid, FieldGroup, FieldPair, Notice, Select, Skeleton, TextField, Toolbar } from '@janso/ui';
import { companyCall, companyFailure } from '../lib/company-api';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CompanyGstOutwardProfile } from './CompanyGstOutwardProfile';

type Schemas = components['schemas'];
export type TaxFormActivity = { dirty: boolean; pending: boolean };
type Setup = Omit<Schemas['GstRegistrationSetup'], 'create_schema'> & { create_schema: { properties?: Record<string, { maxLength?: number }> } };
export function CompanyGstRegistration({ company, canOpenReports = false, onActivity, onNavigate }: { company: string; canOpenReports?: boolean; onActivity?: (activity: TaxFormActivity) => void; onNavigate?: MouseEventHandler<HTMLAnchorElement> }) {
  const base = '/v1/companies/' + company;
  const [setup, setSetup] = useState<Setup | null>(null), [rows, setRows] = useState<Schemas['TaxRegistrationItem'][]>([]), [next, setNext] = useState<string | null>(null);
  const [number, setNumber] = useState(''), [name, setName] = useState(''), [state, setState] = useState(''), [regime, setRegime] = useState(''), [from, setFrom] = useState(''), [close, setClose] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [show, setShow] = useState(false), [loading, setLoading] = useState(true), [revision, setRevision] = useState(0);
  const inFlight = useRef(false), key = useRef<{ payload: string; value: string } | null>(null);
  const formId = useId();
  const [dismissal, setDismissal] = useState<'confirm' | 'discard' | null>(null);
  // Close confirmation first so its focus and scroll lock restore before the drawer closes.
  useEffect(() => { if (dismissal === 'discard') reset(); }, [dismissal]);
  const [profileActivity, setProfileActivity] = useState<TaxFormActivity>({ dirty: false, pending: false });
  const dirty = show && !!(number || name || state || regime || from);
  useEffect(() => { onActivity?.({ dirty: dirty || profileActivity.dirty, pending: busy || profileActivity.pending }); }, [onActivity, dirty, busy, profileActivity.dirty, profileActivity.pending]);
  // A containing page owns confirmation when it receives the aggregate activity.
  useUnsavedChanges(() => !onActivity && (inFlight.current || dirty || profileActivity.dirty || profileActivity.pending));
  async function read(cursor?: string, signal?: AbortSignal) {
    const page = await companyCall<Schemas['Page_TaxRegistrationItem_']>('identity', base + '/tax-registrations?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { signal });
    if (!signal?.aborted) { setRows(page.items.filter(row => row.tax_system === 'gst_in')); setNext(page.page.next_cursor); }
  }
  useEffect(() => {
    const abort = new AbortController(); setSetup(null); setRows([]); setNext(null); setError(''); setLoading(true);
    void companyCall<Setup>('identity', base + '/gst-registration-setup', { signal: abort.signal }).then(async value => {
      if (abort.signal.aborted) return;
      if (value.country_code === 'IN' && value.default_tax_system === 'gst_in') await read(undefined, abort.signal);
      if (!abort.signal.aborted) { setSetup(value); setLoading(false); }
    }).catch(value => { if (!abort.signal.aborted) { setError(companyFailure(value).message); setLoading(false); } });
    return () => abort.abort();
  }, [base, revision]);
  async function act(work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); setMessage('');
    try { await work(); } catch (value) { setError(companyFailure(value).message); }
    finally { inFlight.current = false; setBusy(false); }
  }
  function reset() { setShow(false); setDismissal(null); setError(''); setNumber(''); setName(''); setState(''); setRegime(''); setFrom(''); key.current = null; }
  function requestClose() { if (inFlight.current) return; if (dirty) setDismissal('confirm'); else reset(); }
  async function save() {
    const body: Schemas['TaxRegistrationCreate'] = { tax_system: 'gst_in', regime, number: number.trim().toUpperCase(), jurisdiction_code: state, legal_name_on_registration: name.trim() || null, valid_from: from };
    const payload = JSON.stringify(body);
    if (key.current?.payload !== payload) key.current = { payload, value: crypto.randomUUID() };
    await companyCall('identity', base + '/tax-registrations', { method: 'POST', body, key: key.current.value });
    reset(); await read(); setMessage('GST registration saved. Configure its confirmed filing preference in GSTR-3B.');
  }
  if (loading) return <div role="status" aria-label="Loading GST registrations"><Skeleton /></div>;
  if (error && !setup) return <Notice tone="warning">{error} <Button variant="ghost" onClick={() => setRevision(value => value + 1)}>Reload GST registrations</Button></Notice>;
  if (!setup || setup.country_code !== 'IN' || setup.default_tax_system !== 'gst_in') return null;
  return <section className="janso-flow" aria-label="GST configuration">
    <Card className="janso-card--compact"><CardHeader title="GST registrations" subtitle="Each GSTIN keeps its own state, regime and validity history." />
      <CardBody><div className="janso-flow">
        <p className="janso-meta">GST (India) is the company default, not proof of registration. Businesses without a GSTIN can leave this list empty. Add a record only for an actual registration; composition and other regimes retain their own tax treatment.</p>
        {setup.can_manage && <Toolbar right={<Button variant="ghost" disabled={busy || show} onClick={() => { setError(''); setMessage(''); setShow(true); }}>Add GST registration</Button>} />}
        {error && !show && <Notice tone="warning">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
        {show && setup.can_manage && <Drawer open title="Add GST registration" size="lg" busy={busy} onClose={requestClose} footer={<>
          <Button type="button" variant="ghost" disabled={busy} onClick={requestClose}>Cancel</Button>
          <Button type="submit" form={formId} loading={busy} disabled={busy || !number.trim() || !state || !regime || !from}>Save GST registration</Button>
        </>}>
        <form id={formId} className="janso-flow" aria-label="Add GST registration" onSubmit={event => { event.preventDefault(); void act(save); }}>
          {error && <Notice tone="warning">{error}</Notice>}
          <FieldGrid disabled={busy}>
          <FieldGroup title="Registration details">
            <TextField label="GSTIN" required maxLength={setup.create_schema.properties?.number?.maxLength} value={number} onChange={event => setNumber(event.target.value)} />
            <TextField label="Legal name on GST registration" maxLength={setup.create_schema.properties?.legal_name_on_registration?.maxLength} value={name} onChange={event => setName(event.target.value)} />
          </FieldGroup>
          <FieldGroup title="Jurisdiction and validity" hint="Use the state and start date shown on the registration. Regime changes create a new dated record.">
            <FieldPair>
              <Select label="GST registration state / UT" required value={state} onChange={setState} options={[{ value: '', label: 'Choose state / UT' }, ...setup.states.map(row => ({ value: row.code, label: row.name }))]} />
              <Select label="GST regime" required value={regime} onChange={setRegime} options={[{ value: '', label: 'Choose registered regime' }, ...Object.entries(setup.regimes).map(([value, label]) => ({ value, label }))]} />
            </FieldPair>
            <TextField label="GST registration valid from" type="date" required value={from} onChange={event => setFrom(event.target.value)} />
          </FieldGroup>
        </FieldGrid></form></Drawer>}
        <ConfirmDialog open={dismissal === 'confirm'} title="Discard unsaved GST registration?" confirmLabel="Discard" cancelLabel="Keep editing" onCancel={() => setDismissal(null)} onConfirm={() => setDismissal('discard')}>The registration has not been saved.</ConfirmDialog>
        <DataTable caption="Company GST registrations" columns={[{ key: 'number', header: 'GSTIN', type: 'text' }, { key: 'jurisdiction_code', header: 'State / UT', type: 'custom', render: row => setup.states.find(state => state.code === row.jurisdiction_code)?.name ?? row.jurisdiction_code }, { key: 'regime', header: 'Regime', type: 'custom', render: row => setup.regimes[row.regime] ?? row.regime }, { key: 'valid_from', header: 'Valid from', type: 'date' }, { key: 'valid_to', header: 'Valid to', type: 'date' }]} rows={rows} rowId={row => row.id} rowLabel={row => row.number} emptyTitle="No GST registrations" emptyBody="No saved GST registration records were returned. You do not need to invent a GSTIN to configure company details." rowActions={row => setup.can_manage && !row.valid_to ? [{ id: 'close', label: 'Close registration at selected date', disabledReason: busy ? 'Wait for the current request.' : !close ? 'Choose a closing date first.' : undefined }] : []} onAction={(_action, row) => void act(async () => { await companyCall('identity', base + '/tax-registrations/' + row.id, { method: 'PATCH', body: { valid_to: close }, key: crypto.randomUUID() }); await read(); setMessage('GST registration closed. Its historical returns remain available.'); })} />
        <Toolbar right={<><Button variant="ghost" disabled={busy} onClick={() => void act(() => read())}>First page</Button><Button variant="ghost" disabled={busy || !next} onClick={() => void act(() => read(next!))}>Next page</Button></>} />
        {setup.can_manage && rows.some(row => !row.valid_to) && <Disclosure summary="Close a GST registration"><FieldGrid disabled={busy}><TextField label="Registration closing date" type="date" value={close} onChange={event => setClose(event.target.value)} /><p className="janso-meta">Choose the exclusive end date, then use the registration's row action. The historical record is retained.</p></FieldGrid></Disclosure>}
        {canOpenReports && <a className="janso-link" href="/reports/workspace?report=GSTR3B" onClick={onNavigate}>GST filing preferences and GSTR-3B</a>}
      </div></CardBody>
    </Card>
    <CompanyGstOutwardProfile company={company} registrations={rows} canOpenReports={canOpenReports} onActivity={setProfileActivity} onNavigate={onNavigate} />
  </section>;
}
