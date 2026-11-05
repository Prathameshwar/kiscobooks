'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, DataTable, Notice, ReviewList, SectionHeader, TextField, useFormatters, type Column } from '@janso/ui';
import { request, type Access, type Entry } from '../lib/financial-opening';
import { addable, heldEntry, heldPath, heldTotals, pendingQuery, verifyHeld, withdrawLabel, type HeldBalance, type HeldPage } from '../lib/party-opening';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { FinancialOpeningAccount, FinancialOpeningMoney } from './FinancialOpeningCommon';

const SHOWN = 25;

/**
 * Opening balances that arrived with a supplier or customer import. They are held, not posted: this
 * panel copies the ones the person chooses into the worksheet they are building, where the whole
 * declaration is still reviewed, balanced and previewed before anything is saved.
 */
export function FinancialOpeningHeldBalances({ company, rows, access, editable, onAdd, onDirty, onLeave }: {
  company: string; rows: Entry[]; access: Access; editable: boolean;
  onAdd: (entries: Entry[]) => void; onDirty: (dirty: boolean) => void;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const format = useFormatters();
  const held = useServiceRead<HeldPage>(pendingQuery(company), request, verifyHeld);
  const [targetId, setTargetId] = useState<string | null>(null), [reason, setReason] = useState(''), [error, setError] = useState(''), [message, setMessage] = useState('');
  const command = useServiceCommand(request, 'held party balance');
  const frozen = useRef<Parameters<typeof command.execute>[0] | null>(null);
  useEffect(() => { onDirty(!!targetId || command.pending || command.uncertain); return () => onDirty(false); }, [targetId, command.pending, command.uncertain, onDirty]);

  const open = addable(held.data?.items ?? [], rows);
  // Always the latest row, so a refresh after a conflict supplies the current version.
  const target = open.find(item => item.id === targetId) ?? null;
  // If the line left the list (withdrawn elsewhere, or now in the worksheet), the dialog has no subject.
  useEffect(() => { if (targetId && !target && !held.loading && !command.pending) setTargetId(null); }, [targetId, target, held.loading, command.pending]);
  // A reader without opening access gets no panel; any other failure is shown with a retry.
  if (held.failure?.status === 403) return null;
  if (!held.failure && (held.loading || (!open.length && !message))) return null;

  async function withdraw() {
    if (command.pending || !access.manage) return;
    let payload = frozen.current;
    if (!command.uncertain) {
      if (!target) return;
      if (reason.trim().length < 3 || reason.trim().length > 500 || /[\x00-\x1f\x7f]/.test(reason)) { setError('Enter a printable reason between 3 and 500 characters.'); return; }
      payload = { path: `${heldPath(company)}/${target.id}/withdraw`, method: 'POST', body: { expected_version: target.row_version, reason: reason.trim() } };
      frozen.current = payload;
    }
    if (!payload) return;
    const done = await command.execute<HeldBalance>(payload, value => {
      if (value.id !== targetId || value.status !== 'WITHDRAWN') throw { status: 502, message: 'The withdrawal could not be verified. Reload the held balances.' };
    });
    if (done) { setTargetId(null); setReason(''); setError(''); frozen.current = null; command.clear(); setMessage('Held balance withdrawn. The party and its ledger account are unchanged.'); held.refresh(); }
    // A definite refusal means the line changed; reload it so the next attempt carries its version.
    else held.refresh();
  }

  const totals = open.length ? (() => { try { return heldTotals(open); } catch { return null; } })() : null;
  const columns: Column<HeldBalance>[] = [
    { type: 'custom', key: 'account', header: 'Party ledger', render: row => <><FinancialOpeningAccount company={company} id={row.account_id} onLeave={onLeave} /><div className="janso-caption">{row.role === 'SUPPLIER' ? 'Supplier' : 'Customer'}</div></> },
    { type: 'custom', key: 'side', header: 'Side', render: row => row.side === 'DEBIT' ? 'Debit · to receive' : 'Credit · to pay' },
    { type: 'custom', key: 'amount', header: 'Amount', render: row => <FinancialOpeningMoney value={row.amount} currency={row.currency} /> },
    { type: 'custom', key: 'document', header: 'Bill', render: row => row.document_kind === 'ON_ACCOUNT' ? 'On account · dates unknown' : `${row.document_reference} · due ${format.date(row.due_date!)}` },
    { type: 'custom', key: 'actions', header: 'Actions', render: row => <Button variant="ghost" disabled={!access.manage || command.pending || !!targetId} aria-label={withdrawLabel(row, open.indexOf(row) + 1)} onClick={() => { setTargetId(row.id); setReason(''); setError(''); setMessage(''); command.clear(); }}>Withdraw</Button> },
  ];
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Balances held from party imports" description="These came with imported suppliers and customers. Nothing is posted. Add them to this worksheet, then record the opposite balances so debits equal credits." />
    <AccountingFailure failure={held.failure} retry={held.refresh} />
    {message && <Notice tone="success"><span role="status">{message}</span></Notice>}
    {open.length > 0 && <>
      <ReviewList items={[
        { label: 'Held balances', value: String(open.length) },
        { label: 'Debit base total', value: totals?.debit ?? 'Incomplete' },
        { label: 'Credit base total', value: totals?.credit ?? 'Incomplete' },
      ]} />
      <DataTable caption="Held party opening balances" columns={columns} rows={open.slice(0, SHOWN)} rowId={row => row.id} rowLabel={row => row.source_key} emptyTitle="No held balances" emptyBody="Import suppliers or customers with opening balances to see them here." />
      {open.length > SHOWN && <p className="janso-fine">Showing the first {SHOWN} of {open.length}. Adding takes all {open.length}.</p>}
      {held.data?.page.has_more && <p className="janso-fine">More held balances exist beyond this list. Add these, save the worksheet and reload to continue.</p>}
      <div className="janso-form-actions"><Button disabled={!editable || !!targetId} onClick={() => { onAdd(open.map(heldEntry)); setMessage(''); }}>Add {open.length} held {open.length === 1 ? 'balance' : 'balances'} to this worksheet</Button></div>
      {!editable && <p className="janso-fine">The worksheet is not editable now. Check the opening status above.</p>}
    </>}
    <ConfirmDialog open={!!target} busy={command.pending} title="Withdraw this held balance?" confirmLabel={command.uncertain ? 'Retry the same request' : 'Withdraw balance'}
      onCancel={() => { if (!command.uncertain) { setTargetId(null); setError(''); } }} onConfirm={() => void withdraw()}>
      {target && <ReviewList items={[
        { label: 'Party ledger', value: <FinancialOpeningAccount company={company} id={target.account_id} /> },
        { label: 'Balance', value: <>{target.side === 'DEBIT' ? 'Debit · to receive' : 'Credit · to pay'} <FinancialOpeningMoney value={target.amount} currency={target.currency} /></> },
        { label: 'Bill', value: target.document_kind === 'ON_ACCOUNT' ? 'On account · dates unknown' : `${target.document_reference} · due ${format.date(target.due_date!)}` },
      ]} />}
      <p>The balance will no longer be offered to the opening worksheet, and this cannot be undone. The party and its ledger account stay, and the balance can still be entered in the worksheet by hand.</p>
      <TextField label="Withdrawal reason" value={reason} maxLength={500} disabled={command.pending || command.uncertain} onChange={event => setReason(event.target.value)} />
      {error && <p role="alert">{error}</p>}
      {command.failure && <p role="alert">{command.failure.message}{command.uncertain ? ' Retry preserves the exact request and idempotency key.' : ''}</p>}
    </ConfirmDialog>
  </div></CardBody></Card>;
}
