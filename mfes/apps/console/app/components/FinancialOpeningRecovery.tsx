'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, ConfirmDialog, Notice, SectionHeader, TextField } from '@janso/ui';
import { base, blockerLabel, owned, request, type Access } from '../lib/financial-opening';
import { trackingId } from '../lib/stock-tracking-resources';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { OpeningJournal } from './FinancialOpeningJournal';

type Recovery = components['schemas']['OpeningJournalRecovery'];
type Journal = components['schemas']['JournalDetail'];
export function FinancialOpeningRecovery({ company, batch, journal, date, access, disabled, blocked, onDirty, onChanged, revision }: {
  company: string; batch: string; journal: string; date: string; access: Access; disabled: boolean; blocked: boolean;
  onDirty: (dirty: boolean) => void; onChanged: () => void; revision: number;
}) {
  const path = `/v1/companies/${company}/journals/${journal}`;
  const read = useServiceRead<Recovery>(`${base(company)}/workspaces/${batch}/journals/${journal}/recovery`, request, value => {
    owned(company)(value);
    if (value.batch_id !== batch || value.journal_id !== journal || !Number.isSafeInteger(value.expected_version) || !Array.isArray(value.reversal_blockers) || value.reversal_journal_id && !trackingId.test(value.reversal_journal_id))
      throw { status: 502, message: 'Journal recovery ownership could not be verified.' };
  });
  const [reason, setReason] = useState(''), [action, setAction] = useState<'void' | 'reversal' | 'cancel-reversal' | null>(null),
    [reviewReversal, setReviewReversal] = useState(false), [reversalBusy, setReversalBusy] = useState(false), [error, setError] = useState('');
  const command = useServiceCommand(request, 'opening correction');
  const frozen = useRef<Parameters<typeof command.execute>[0] | null>(null), previous = useRef(revision);
  const locked = command.pending || command.uncertain || reversalBusy;
  const canCancel = access.manage && (access.cancel ?? access.post);
  useEffect(() => { onDirty(locked || !!action); return () => onDirty(false); }, [locked, action, onDirty]);
  useEffect(() => { if (previous.current !== revision) { previous.current = revision; read.refresh(); } }, [revision]);
  async function apply() {
    if (command.pending || disabled || !access.manage || (action !== 'reversal' ? !canCancel : !access.post)) return;
    let payload = frozen.current;
    if (!command.uncertain) {
      if (!action || !read.data || read.loading || read.failure) return;
      if (reason.trim().length < 3 || reason.trim().length > 500 || /[\x00-\x1f\x7f]/.test(reason)) { setError('Enter a printable correction reason between 3 and 500 characters.'); return; }
      if (action === 'void' ? !read.data.can_cancel : action === 'cancel-reversal' ? !read.data.can_cancel_reversal || !read.data.reversal_journal_id : !read.data.can_reverse || blocked) return;
      const target = action === 'cancel-reversal' ? `/v1/companies/${company}/journals/${read.data.reversal_journal_id}` : path;
      payload = { path: target + '/' + (action === 'cancel-reversal' ? 'void' : action), method: 'POST', body: action !== 'reversal'
        ? { expected_version: action === 'cancel-reversal' ? read.data.reversal_expected_version : read.data.expected_version, reason: reason.trim() }
        : { posting_date: date, reason: reason.trim() } };
      frozen.current = payload;
    }
    if (!payload) return;
    const cancelling = payload.path.endsWith('/void');
    const result = await command.execute<Journal>(payload, value => {
      owned(company)(value);
      if (!trackingId.test(value.id) || (cancelling ? value.id !== payload!.path.split('/').at(-2) || value.status !== 'VOID' : value.kind !== 'REVERSAL' || value.reversal_of_id !== journal))
        throw { status: 502, message: 'The correction receipt could not be verified. Retry the same request.' };
    });
    if (result) { setAction(null); setReason(''); setError(''); read.refresh(); onChanged(); }
  }
  return <section className="janso-flow" aria-label="Opening journal recovery">
    <SectionHeader title="Correction and recovery" description="Resolve settlements, charges, linked stock and finalized bank reconciliations before reversing. Native checks run again on every command." />
    <AccountingFailure failure={read.failure} retry={read.refresh} />
    {error && <Notice tone="danger"><span role="alert">{error}</span></Notice>}
    <Button variant="ghost" disabled={locked || disabled} onClick={() => { read.refresh(); onChanged(); }}>Refresh journal recovery</Button>
    {read.data && <>
      {!!read.data.reversal_blockers.length && <Notice>{read.data.reversal_blockers.map(code => <p key={code}>{blockerLabel(code)}</p>)}</Notice>}
      <TextField label="Correction reason" value={reason} maxLength={500} disabled={locked || disabled || !access.manage || !access.post && !canCancel} onChange={event => setReason(event.target.value)} />
      <div className="janso-form-actions">
        <Button variant="ghost" disabled={locked || disabled || read.loading || !!read.failure || !read.data.can_cancel || !canCancel || reason.trim().length < 3} onClick={() => setAction('void')}>Cancel unposted journal</Button>
        <Button variant="ghost" disabled={locked || disabled || blocked || read.loading || !!read.failure || !read.data.can_reverse || !access.manage || !access.post || reason.trim().length < 3} onClick={() => setAction('reversal')}>Prepare reversal draft</Button>
      </div>
      {read.data.reversal_journal_id && <>
        <Notice>Retained reversal: {read.data.reversal_status}. Draft creation and posting are separate actions.</Notice>
        <Button variant="ghost" disabled={locked || disabled || read.loading || !!read.failure || !read.data.can_cancel_reversal || !canCancel || reason.trim().length < 3} onClick={() => setAction('cancel-reversal')}>Cancel unposted reversal</Button>
        <Button variant="ghost" disabled={locked || disabled} onClick={() => setReviewReversal(value => !value)}>{reviewReversal ? 'Hide reversal journal' : 'Review reversal journal'}</Button>
        {reviewReversal && <OpeningJournal key={read.data.reversal_journal_id} company={company} id={read.data.reversal_journal_id} originalId={journal}
          access={{ ...access, post: access.manage && access.post && !blocked && !disabled && !command.pending && !command.uncertain }} onDirty={setReversalBusy} onChanged={onChanged} revision={revision} />}
      </>}
    </>}
    <ConfirmDialog open={!!action} busy={command.pending} title={action !== 'reversal' ? 'Cancel this unposted journal?' : 'Prepare a reversal draft?'}
      confirmLabel={command.uncertain ? 'Retry the same correction' : action !== 'reversal' ? 'Cancel journal' : 'Create reversal draft'}
      onCancel={() => { if (!locked) setAction(null); }} onConfirm={() => void apply().catch(() => setError('Recovery status could not be read. Refresh and review before retrying.'))}>
      {command.failure && <p role="alert">{command.failure.message}</p>}
      {action !== 'reversal' ? 'This cancels an unposted intent and queues any required Identity abort. Existing posted facts and evidence remain. Refresh after delivery before preparing another correction.' : 'This creates a native reversal draft. Review and explicitly post it, wait for confirmation, then close any remaining unposted plan and prepare a replacement.'}
    </ConfirmDialog>
  </section>;
}
