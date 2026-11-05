'use client';
import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, ConfirmDialog, DataTable, Notice, Pager, ReviewList, useFormatters, type Column } from '@janso/ui';
import { owned, request, type Access } from '../lib/financial-opening';
import { useServiceCommand, useServiceList, useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { FinancialOpeningAccount, FinancialOpeningMoney } from './FinancialOpeningCommon';
type Journal = components['schemas']['JournalDetail'];
type Line = components['schemas']['JournalLineListItem'];
export function OpeningJournal({ company, id, access, onDirty, onChanged, originalId, revision = 0 }: { company: string; id: string; access: Access; onDirty: (dirty: boolean) => void; onChanged: () => void; originalId?: string; revision?: number }) {
  const format = useFormatters();
  const path = `/v1/companies/${company}/journals/${id}`;
  function verify(row: Journal) {
    owned(company)(row);
    if (row.id !== id || (originalId ? row.kind !== 'REVERSAL' || row.reversal_of_id !== originalId : row.kind !== 'OPENING' || row.source_type !== 'financial_opening_chunk') || !Number.isSafeInteger(row.row_version) || !row.status) throw { status: 502, message: 'The native opening journal could not be verified.' };
  }
  const read = useServiceRead<Journal>(path, request, verify);
  const [confirm, setConfirm] = useState(false), [message, setMessage] = useState('');
  const command = useServiceCommand(request, 'native opening journal');
  const frozen = useRef<Parameters<typeof command.execute>[0] | null>(null);
  const lines = useServiceList<Line>(`/v1/companies/${company}/journal-lines`, new URLSearchParams({ journal_id: id }).toString(), request, row => {
    owned(company)(row); if (row.journal_id !== id) throw { status: 502, message: 'Journal line ownership could not be verified.' };
  });
  const previous = useRef(revision);
  useEffect(() => { if (previous.current !== revision) { previous.current = revision; read.refresh(); lines.first(); } }, [revision]);
  const locked = command.pending || command.uncertain;
  useEffect(() => { onDirty(locked || confirm); return () => onDirty(false); }, [locked, confirm, onDirty]);
  async function post() {
    if (!access.post || !read.data || command.pending) return;
    const payload = command.uncertain && frozen.current ? frozen.current : { path: path + '/post', method: 'POST', body: { expected_version: read.data.row_version } };
    frozen.current = payload;
    const result = await command.execute<Journal>(payload, verify);
    if (result) { setConfirm(false); setMessage(originalId ? 'Reversal posted. Refresh confirmation status before preparing a replacement.' : 'Journal posted. Completion waits for its native confirmation.'); read.refresh(); lines.first(); onChanged(); }
  }
  const columns: Column<Line>[] = [
    { type: 'custom', key: 'sequence', header: 'Line', render: row => String(row.sequence ?? '') },
    { type: 'custom', key: 'account', header: 'Account', render: row => row.account_id ? <FinancialOpeningAccount company={company} id={row.account_id} /> : 'Restricted' },
    { type: 'custom', key: 'side', header: 'Side', render: row => row.side ?? 'Restricted' },
    { type: 'custom', key: 'amount', header: 'Amount', render: row => row.amount && row.currency ? <FinancialOpeningMoney value={row.amount} currency={row.currency} /> : 'Restricted' },
    { type: 'custom', key: 'base', header: 'Base value', render: row => row.base_amount && row.base_currency ? <FinancialOpeningMoney value={row.base_amount} currency={row.base_currency} /> : 'Restricted' },
  ];
  return <div className="janso-flow">
    <AccountingFailure failure={read.failure} retry={read.refresh} /><AccountingFailure failure={lines.failure} retry={lines.first} /><AccountingFailure failure={command.failure} retry={read.refresh} write />
    {message && <Notice tone="success"><span role="status">{message}</span></Notice>}
    {read.data && <><ReviewList items={[{ label: 'Journal', value: read.data.number ?? 'Unnumbered opening draft' }, { label: 'Status', value: read.data.status ?? 'Restricted' }, { label: 'Posting date', value: read.data.posting_date ? format.date(read.data.posting_date) : 'Restricted' }, { label: 'Base debit / credit', value: `${read.data.total_debit ?? 'Restricted'} / ${read.data.total_credit ?? 'Restricted'}` }]} />
      <DataTable caption="Native opening journal lines" columns={columns} rows={lines.data?.items ?? []} loading={lines.loading} rowId={row => row.id} rowLabel={row => String(row.sequence ?? row.id)} emptyTitle="No readable lines" />
      <Pager count={lines.data?.items.length ?? 0} limit={lines.limit} busy={lines.loading || locked} hasPrevious={lines.hasPrevious} hasNext={!!lines.data?.page.has_more} onPrevious={lines.previous} onNext={lines.next} onLimitChange={lines.setLimit} noun="line" />
      {!access.post && <Notice>Posting requires journal posting and period access. Preparation does not grant that authority.</Notice>}
      <Button disabled={!access.post || locked || read.loading || !!read.failure || !!lines.failure || !lines.data?.items.length || !['DRAFT', 'PREPARED'].includes(read.data.status ?? '')} onClick={() => setConfirm(true)}>{originalId ? 'Post this reversal journal' : 'Post this opening journal'}</Button>
    </>}
    <ConfirmDialog open={confirm} busy={command.pending} title={originalId ? 'Post this reversal journal?' : 'Post this opening journal?'} confirmLabel={command.uncertain ? 'Retry the same posting' : 'Post journal'} onCancel={() => { if (!locked) setConfirm(false); }} onConfirm={() => void post()}>
      {command.uncertain ? 'The outcome is unconfirmed. Retry sends the exact same body and idempotency key, preserving one financial effect.' : originalId ? 'This posts the reviewed reversal of the original opening journal. After confirmation, close any remaining unposted opening drafts before preparing the replacement.' : 'This records the reviewed opening amounts and party outstanding documents. Posted effects require a native reversal to correct. The company opening is finalized separately.'}
      {command.failure && <p role="alert">{command.failure.message}</p>}
    </ConfirmDialog>
  </div>;
}
