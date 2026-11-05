'use client';
import { useEffect, useId, useRef, useState, type MouseEventHandler } from 'react';
import { Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, Disclosure, Drawer, FieldGrid, FieldGroup, FieldPair, Notice, Select, Skeleton, TextField, Toolbar } from '@janso/ui';
import { companyCall, companyFailure } from '../lib/company-api';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import type { TaxFormActivity } from './CompanyGstRegistration';

type Profile = { id: string; registration_id: string; annual_turnover: string; rule_14a: boolean; valid_from: string; valid_to: string | null; reference: string; evidence_hash: string };
type Setup = { can_manage: boolean; create_schema: { properties?: Record<string, { maxLength?: number }> } };
export function CompanyGstOutwardProfile({ company, registrations, canOpenReports = false, onActivity, onNavigate }: { company: string; registrations: { id: string; number: string; regime: string }[]; canOpenReports?: boolean; onActivity?: (activity: TaxFormActivity) => void; onNavigate?: MouseEventHandler<HTMLAnchorElement> }) {
  const base = '/v1/companies/' + company;
  const [setup, setSetup] = useState<Setup | null>(null), [rows, setRows] = useState<Profile[]>([]), [next, setNext] = useState<string | null>(null);
  const [registration, setRegistration] = useState(''), [turnover, setTurnover] = useState(''), [rule, setRule] = useState(''), [from, setFrom] = useState(''), [close, setClose] = useState(''), [reference, setReference] = useState(''), [hash, setHash] = useState(''), [proof, setProof] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [show, setShow] = useState(false);
  const [loading, setLoading] = useState(true), [revision, setRevision] = useState(0);
  const inFlight = useRef(false), retry = useRef<{ payload: string; key: string } | null>(null);
  const formId = useId();
  const [dismissal, setDismissal] = useState<'confirm' | 'discard' | null>(null);
  // Restore the confirmation's focus and scroll lock before closing its drawer.
  useEffect(() => { if (dismissal === 'discard') reset(); }, [dismissal]);
  const dirty = show && !!(registration || turnover || rule || from || reference || proof);
  useEffect(() => { onActivity?.({ dirty, pending: busy }); }, [onActivity, dirty, busy]);
  useUnsavedChanges(() => !onActivity && (inFlight.current || dirty));
  const eligible = registrations.filter(row => ['regular', 'sez_unit', 'sez_developer', 'casual_taxable_person'].includes(row.regime));
  async function read(cursor?: string, signal?: AbortSignal) {
    const page = await companyCall<{ items: Profile[]; page: { next_cursor: string | null } }>('identity', base + '/gst-outward-profiles?limit=50' + (cursor ? '&cursor=' + encodeURIComponent(cursor) : ''), { signal });
    if (!signal?.aborted) { setRows(page.items); setNext(page.page.next_cursor); }
  }
  async function act(work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); setMessage('');
    try { await work(); } catch (value) { setError(value instanceof Error ? value.message : companyFailure(value).message); }
    finally { inFlight.current = false; setBusy(false); }
  }
  useEffect(() => {
    const abort = new AbortController(); setSetup(null); setRows([]); setNext(null); setError(''); setLoading(true);
    void companyCall<Setup>('identity', base + '/gst-outward-profile-setup', { signal: abort.signal }).then(async value => {
      if (abort.signal.aborted) return;
      await read(undefined, abort.signal);
      if (!abort.signal.aborted) { setSetup(value); setLoading(false); }
    }).catch(value => { if (!abort.signal.aborted) { setError(companyFailure(value).message); setLoading(false); } });
    return () => abort.abort();
  }, [base, revision]);
  function reset() { setShow(false); setDismissal(null); setError(''); setRegistration(''); setTurnover(''); setRule(''); setFrom(''); setReference(''); setHash(''); setProof(''); retry.current = null; }
  function requestClose() { if (inFlight.current) return; if (dirty) setDismissal('confirm'); else reset(); }
  async function save() {
    if (!/^\d+(?:\.\d{1,4})?$/.test(turnover)) throw new Error('Enter a non-negative turnover with up to four decimal places.');
    const body = { registration_id: registration, annual_turnover: turnover, currency: 'INR', rule_14a: rule === 'YES', valid_from: from, reference: reference.trim(), evidence_hash: hash };
    const payload = JSON.stringify(body);
    if (retry.current?.payload !== payload) retry.current = { payload, key: crypto.randomUUID() };
    await companyCall('identity', base + '/gst-outward-profiles', { method: 'POST', body, key: retry.current.key });
    reset(); await read(); setMessage('Dated GST outward reporting profile saved. Refresh GST data before preparing a return.');
  }
  return <section aria-label="GST outward reporting profiles">
    <Card className="janso-card--compact"><CardHeader title="GST outward reporting profiles" subtitle="Dated turnover and Rule 14A evidence for eligible GST registrations." />
      <CardBody><div className="janso-flow">
        {loading ? <div role="status" aria-label="Loading GST outward reporting profiles"><Skeleton /></div> : error && !setup ? <Notice tone="warning">{error} <Button variant="ghost" onClick={() => setRevision(value => value + 1)}>Reload outward reporting profiles</Button></Notice> : <>
        <p className="janso-meta">Previous financial-year aggregate turnover determines HSN/SAC digits. Confirm Rule 14A applicability from registration evidence. History is retained.</p>
        {setup?.can_manage && <Toolbar right={<Button variant="ghost" disabled={busy || show || !eligible.length} onClick={() => { setError(''); setMessage(''); setShow(true); }}>Add outward reporting profile</Button>} />}
        {error && !show && <Notice tone="warning">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
        {setup?.can_manage && !eligible.length && <Notice>Add an eligible GST registration, or open its registration page above, before adding an outward reporting profile. Composition and unregistered businesses do not use this profile.</Notice>}
        {show && setup?.can_manage && <Drawer open title="Add outward reporting profile" size="lg" busy={busy} onClose={requestClose} footer={<>
          <Button type="button" variant="ghost" disabled={busy} onClick={requestClose}>Cancel</Button>
          <Button type="submit" form={formId} loading={busy} disabled={busy || !registration || !turnover || !rule || !from || !reference.trim() || !/^[a-f0-9]{64}$/.test(hash)}>Save outward reporting profile</Button>
        </>}>
        <form id={formId} className="janso-flow" aria-label="Add outward reporting profile" onSubmit={event => { event.preventDefault(); void act(save); }}>
          {error && <Notice tone="warning">{error}</Notice>}
          <FieldGrid disabled={busy}>
          <FieldGroup title="Turnover and registration status">
            <Select label="Reporting profile GSTIN" required value={registration} onChange={setRegistration} options={[{ value: '', label: 'Choose GSTIN' }, ...eligible.map(row => ({ value: row.id, label: row.number }))]} />
            <TextField label="Previous GST financial-year aggregate turnover (INR)" value={turnover} onChange={event => setTurnover(event.target.value)} required inputMode="decimal" />
            <FieldPair>
              <Select label="Registered under Rule 14A" required value={rule} onChange={setRule} options={[{ value: '', label: 'Confirm registration status' }, { value: 'NO', label: 'No' }, { value: 'YES', label: 'Yes, confirmed from registration' }]} />
              <TextField label="Reporting profile effective from" type="date" value={from} onChange={event => setFrom(event.target.value)} required />
            </FieldPair>
          </FieldGroup>
          <FieldGroup title="Supporting evidence" hint="Retain the original document with the return workings.">
            <TextField label="Reporting profile evidence reference" maxLength={setup.create_schema.properties?.reference?.maxLength} value={reference} onChange={event => setReference(event.target.value)} required />
            <TextField label="Reporting profile evidence file" type="file" required onChange={event => {
              const file = event.target.files?.[0]; setHash(''); setProof('');
              if (!file) return;
              void act(async () => { if (file.size > 10 * 1024 * 1024) throw new Error('Choose evidence up to 10 MB.'); const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer()); setHash(Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('')); setProof(file.name); });
            }} />
            {proof && <p className="janso-meta">Evidence: {proof}. Retain the original document with the return workings.</p>}
          </FieldGroup>
        </FieldGrid></form></Drawer>}
        <ConfirmDialog open={dismissal === 'confirm'} title="Discard unsaved outward reporting profile?" confirmLabel="Discard" cancelLabel="Keep editing" onCancel={() => setDismissal(null)} onConfirm={() => setDismissal('discard')}>The reporting profile has not been saved.</ConfirmDialog>
        <DataTable caption="Dated GST outward reporting profiles" rows={rows} rowId={row => row.id} emptyTitle="No outward reporting profiles" emptyBody="Add a dated profile only when it applies to an eligible GST registration." columns={[{ key: 'registration_id', header: 'GSTIN', type: 'custom', render: row => registrations.find(item => item.id === row.registration_id)?.number ?? 'Registration not on this page' }, { key: 'annual_turnover', header: 'Previous FY turnover (INR)', type: 'text' }, { key: 'rule_14a', header: 'Rule 14A', type: 'custom', render: row => row.rule_14a ? 'Yes' : 'No' }, { key: 'valid_from', header: 'From', type: 'date' }, { key: 'valid_to', header: 'To', type: 'date' }]} rowActions={row => setup?.can_manage && !row.valid_to ? [{ id: 'close', label: 'Close at selected date', disabledReason: busy ? 'Wait for the current request.' : close ? undefined : 'Choose a closing date.' }] : []} onAction={(_action, row) => void act(async () => { await companyCall('identity', base + '/gst-outward-profiles/' + row.id, { method: 'PATCH', body: { valid_to: close }, key: crypto.randomUUID() }); await read(); setMessage('Reporting profile closed. Save the next profile from the same exclusive boundary.'); })} />
        <Toolbar right={<><Button variant="ghost" disabled={busy} onClick={() => void act(() => read())}>First profile page</Button><Button variant="ghost" disabled={busy || !next} onClick={() => void act(() => read(next!))}>Next profile page</Button></>} />
        {setup?.can_manage && rows.some(row => !row.valid_to) && <Disclosure summary="Close an outward reporting profile"><FieldGrid disabled={busy}><TextField label="Reporting profile closing date" type="date" value={close} onChange={event => setClose(event.target.value)} /><p className="janso-meta">Choose the exclusive end date, then use the profile's row action. Save the next profile from the same boundary.</p></FieldGrid></Disclosure>}
        {canOpenReports && <a className="janso-link" href="/reports/workspace?report=GSTR1" onClick={onNavigate}>GSTR-1 preparation</a>}
        </>}
      </div></CardBody>
    </Card>
  </section>;
}
