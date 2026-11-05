'use client';
import { useRef, useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, ConfirmDialog, FormActions, Notice, SectionHeader, Skeleton, TextField, useFormatters } from '@janso/ui';
import { companyCall } from '../lib/company-api';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import type { ServiceRequest } from '../lib/service-call';
import { validMasterDate } from '../lib/catalog-masters';
import { trackingId } from '../lib/stock-tracking-resources';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { useAccessDraft } from './AccessCommon';

type Review = components['schemas']['ZeroOpeningReview'];
type Input = components['schemas']['ZeroOpeningConfirm'];
type Opening = components['schemas']['OpeningBatchDetail'];
const request = <T,>(command: ServiceRequest) => companyCall<T>('accounting', command.path, command);

export function CompanyZeroOpening({ company, canConfirm, onSaved }: { company: string; canConfirm: boolean; onSaved: () => void }) {
  const base = '/v1/companies/' + company + '/financial-setup', format = useFormatters();
  const read = useServiceRead<Review>(canConfirm ? base + '/zero-opening-review' : undefined, request, row => {
    if (row.company_id !== company || !Number.isSafeInteger(row.expected_setup_version) || row.expected_setup_version < 1 || !validMasterDate(row.books_begin_date) || typeof row.eligible !== 'boolean' || row.eligible !== (row.blocker === null)) throw { status: 502, message: 'The opening review could not be verified for this company.' };
  });
  const [reason, setReason] = useState('Starting with no opening balances'), [dirty, setDirty] = useState(false), [confirming, setConfirming] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
  const retained = useRef<Input | null>(null), command = useServiceCommand(request, 'zero opening'), guard = useAccessDraft(dirty || command.uncertain, command.pending);
  if (!canConfirm) return null;
  const current = read.data?.company_id === company ? read.data : null, locked = command.pending || command.uncertain;
  function begin() {
    if (!current?.eligible || command.blocked) return;
    if (reason.trim().length < 3) { setError('Explain why the company has no opening balances.'); return; }
    retained.current = { expected_setup_version: current.expected_setup_version, reason: reason.trim() };
    setError(''); setConfirming(true);
  }
  async function apply() {
    if (!retained.current || command.pending) return;
    setConfirming(false);
    const result = await command.execute<Opening>({ path: base + '/confirm-zero-opening', method: 'POST', body: retained.current }, row => {
      if (row.company_id !== company || !trackingId.test(row.id) || row.status !== 'FINALIZED' || row.journal_id != null) throw { status: 502, message: 'The zero-opening confirmation could not be verified.' };
    });
    if (result) { setDirty(false); setSaved(true); read.refresh(); onSaved(); }
  }
  return <section className="janso-flow" aria-label="Zero opening confirmation">
    <SectionHeader title="Opening balances" description="If this is a new business with no money, assets, liabilities or outstanding bills to bring forward, explicitly confirm a zero opening." />
    <AccountingFailure failure={read.failure} retry={read.refresh} />
    <AccountingFailure failure={command.failure} write retry={command.uncertain ? undefined : () => { command.clear(); read.refresh(); }} />
    {saved && <Notice tone="success">Zero opening confirmed. Other posting prerequisites still apply.</Notice>}
    {read.loading ? <Skeleton /> : current?.blocker === 'OPENING_ALREADY_FINALIZED' ? <Notice tone="success">Opening balances are finalised. Any correction requires an authorised financial controller.</Notice>
      : current?.blocker === 'EXISTING_OPENING_OR_ACTIVITY' ? <Notice>Opening history or recorded activity requires an authorised financial controller.</Notice>
      : current?.blocker === 'BOOKS_PERIOD_NOT_OPEN' ? <Notice tone="warning">Open the period containing the books begin date before confirming a zero opening. <a className="janso-link" href={'/companies/' + company + '/years'} onClick={guard.leave}>Review financial periods</a></Notice>
      : current?.eligible && <form onSubmit={event => { event.preventDefault(); begin(); }}>
        <fieldset disabled={locked} className="janso-fieldgroup janso-flow"><p>Books begin: {format.date(current.books_begin_date)}</p><TextField label="Reason for zero opening" value={reason} required minLength={3} maxLength={500} error={error || command.failure?.fields?.reason} onChange={event => { setReason(event.target.value); setDirty(true); setError(''); command.clear(); }} hint="Use opening-balance entry with your accountant if any balance or outstanding bill exists." /></fieldset>
        <FormActions>{command.uncertain ? <Button type="button" loading={command.pending} onClick={() => void apply()}>Retry the same confirmation</Button> : <Button type="submit" loading={command.pending} disabled={command.blocked}>Review zero opening</Button>}</FormActions>
      </form>}
    {command.uncertain && <Notice tone="warning">The result is unconfirmed. Retry the same confirmation before making another change.</Notice>}
    <ConfirmDialog open={confirming} title="Confirm no opening balances?" confirmLabel="Confirm zero opening" onCancel={() => setConfirming(false)} onConfirm={() => void apply()}>
      <p>You are confirming that this company has no opening account balances, inventory value or outstanding bills at {current ? format.date(current.books_begin_date) : 'the books begin date'}. A financial controller must review any later correction.</p>
    </ConfirmDialog>{guard.confirmation}
  </section>;
}
