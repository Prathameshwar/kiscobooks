'use client';
import { useCallback, useRef, useState } from 'react';
import { Button, ConfirmDialog, Notice, ReviewList, TextField } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { companyCall, companyFailure, type CompanyFailure } from '../lib/company-api';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';

type Review = components['schemas']['FinancialSetupReview'];
export function CompanyBooksRecovery({ companyId, onSaved }: { companyId: string; onSaved: () => void }) {
  const [review, setReview] = useState<Review | null>(null), [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState<CompanyFailure | null>(null), [reasonError, setReasonError] = useState('');
  const pending = useRef(false), keys = useRef(new Map<string, string>());
  useUnsavedChanges(useCallback(() => !!reason || busy || pending.current, [reason, busy]));
  const api = '/v1/companies/' + companyId + '/financial-setup';
  async function load() {
    if (pending.current) return; pending.current = true; setBusy(true); setFailure(null);
    try { setReview(await companyCall<Review>('accounting', api + '/reconciliation-review')); }
    catch (error) { setFailure(companyFailure(error)); }
    finally { pending.current = false; setBusy(false); }
  }
  async function reconcile() {
    if (!review || pending.current) return;
    if (!review.changes.length) { setReview(null); return; }
    if (reason.trim().length < 3) { setReasonError('Give a reason using 3 to 500 characters.'); return; }
    const body = { expected_version: review.expected_version, configuration_hash: review.configuration_hash, reason: reason.trim() };
    const signature = JSON.stringify(body);
    let key = keys.current.get(signature); if (!key) { key = crypto.randomUUID(); keys.current.set(signature, key); }
    pending.current = true; setBusy(true); setFailure(null);
    try {
      await companyCall('accounting', api + '/reconcile', { method: 'POST', body, key });
      setReview(null); setReason(''); onSaved();
    } catch (error) { setFailure(companyFailure(error)); }
    finally { pending.current = false; setBusy(false); }
  }
  return <>
    <Notice>Company settings and unused books can be reconciled after review. Posted or financially used books remain protected.
      <Button variant="ghost" loading={busy && !review} onClick={() => void load()}>Review books setup</Button>
    </Notice>
    {failure && !review && <Notice tone="danger">{failure.message}</Notice>}
    <ConfirmDialog open={review !== null} title="Review books setup" confirmLabel={review?.changes.length ? 'Reconcile unused books' : 'Done'} busy={busy}
      error={failure?.message} onCancel={() => { setReview(null); setReason(''); setFailure(null); }} onConfirm={() => void reconcile()}>
      {review?.changes.length ? <>
        <p>Apply the reviewed company settings to unused books. Existing calendar identities and statuses are retained. Accounting refuses changes that could reinterpret financial history.</p>
        <ReviewList items={review.changes.filter(change => change.field !== 'configuration_hash').map(change => ({
          label: change.field.replaceAll('_', ' '), value: `${change.before} → ${change.after}`,
        }))} />
        <TextField label="Reason for books reconciliation" value={reason} required maxLength={500} disabled={busy} error={reasonError || failure?.fields?.reason}
          onChange={event => { setReason(event.target.value); setReasonError(''); }} />
        {failure?.status === 409 && <Button variant="ghost" disabled={busy} onClick={() => void load()}>Refresh books review</Button>}
      </> : <p>Stored books settings already match the current company settings.</p>}
    </ConfirmDialog>
  </>;
}
