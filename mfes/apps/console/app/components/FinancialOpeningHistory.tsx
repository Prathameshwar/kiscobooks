'use client';
import { useEffect, useState } from 'react';
import type { components } from '@janso/api-client/accounting';
import { Button, Card, CardBody, DataTable, Notice, Pager, ReviewList, SectionHeader, TextField, useFormatters, type Column } from '@janso/ui';
import { base, download, owned, request, type Access, type Declaration, type Entry, type Workspace } from '../lib/financial-opening';
import { useServiceList, useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { FinancialOpeningAccount, FinancialOpeningDocumentEvidence, FinancialOpeningMoney } from './FinancialOpeningCommon';
type EntryItem = components['schemas']['OpeningEntryItem'];
type Revision = components['schemas']['FinancialOpeningRevisionItem'];
export function FinancialOpeningHistory({ company, workspace, access, initialAccountId, initialPartyId, onDirty }: { company: string; workspace: Workspace | null; access: Access; initialAccountId?: string; initialPartyId?: string; onDirty: (dirty: boolean) => void }) {
  const format = useFormatters();
  const root = base(company) + '/workspaces/' + workspace?.id;
  const [source, setSource] = useState(''), [filter, setFilter] = useState(''), [entryId, setEntryId] = useState<string | null>(null), [revisionId, setRevisionId] = useState<string | null>(null), [working, setWorking] = useState(false), [error, setError] = useState('');
  const params = new URLSearchParams(); if (initialAccountId) params.set('account_id', initialAccountId); if (initialPartyId) params.set('party_id', initialPartyId); if (filter) params.set('source_key', filter);
  const entries = useServiceList<EntryItem>(root + '/entries', params.toString(), request, undefined, !!workspace);
  const revisions = useServiceList<Revision>(root + '/revisions', '', request, undefined, !!workspace);
  const entry = useServiceRead<Entry>(workspace && entryId ? root + '/entries/' + entryId : undefined, request);
  const link = useServiceRead<components['schemas']['OpeningEntryPostingLink']>(workspace && entryId ? root + '/entries/' + entryId + '/posting-link' : undefined, request);
  const revision = useServiceRead<Declaration>(workspace && revisionId ? root + '/revisions/' + revisionId : undefined, request);
  const posting = !link.loading && !link.failure && link.data?.entry_id === entryId ? link.data : null;
  const unprepared = posting?.journal_status === 'NOT_PREPARED' && !posting.journal_id;
  const postingJournal = link.loading ? 'Loading posting information' : posting?.journal_id ?? (unprepared ? 'Draft not prepared' : 'Posting information unavailable');
  const postingStatus = link.loading ? 'Loading' : posting?.journal_id ? posting.journal_status + ' / ' + posting.line_sequence : unprepared ? 'Not prepared' : 'Unavailable';
  useEffect(() => { onDirty(working); return () => onDirty(false); }, [working, onDirty]);
  const entryColumns: Column<EntryItem>[] = [
    { type: 'custom', key: 'source', header: 'Source reference', render: row => <Button variant="ghost" onClick={() => setEntryId(row.id)}>{row.source_key}</Button> },
    { type: 'custom', key: 'account', header: 'Ledger', render: row => <FinancialOpeningAccount company={company} id={row.account_id} /> },
    { type: 'custom', key: 'role', header: 'Role / side', render: row => `${row.role ?? 'General'} · ${row.side}` },
    { type: 'custom', key: 'amount', header: 'Amount', render: row => <FinancialOpeningMoney value={row.amount} currency={row.currency} /> },
    { type: 'custom', key: 'base', header: 'Base value', render: row => <FinancialOpeningMoney value={row.base_amount} /> },
    { type: 'custom', key: 'documents', header: 'Documents', render: row => String(row.document_count) },
  ];
  const revisionColumns: Column<Revision>[] = [
    { type: 'custom', key: 'revision', header: 'Revision', render: row => <Button variant="ghost" onClick={() => setRevisionId(row.id)}>Review revision {row.revision}</Button> },
    { type: 'custom', key: 'created', header: 'Captured', render: row => format.dateTime(row.created_at) },
    { type: 'custom', key: 'hash', header: 'Manifest', render: row => <span className="janso-caption">{row.manifest_hash.slice(0, 12)}…</span> },
  ];
  if (!workspace) return <div className="janso-flow"><FinancialOpeningBatches company={company} /><Notice>Select a retained opening above to review its source or original setup status.</Notice></div>;
  return <div className="janso-flow">
    <FinancialOpeningBatches company={company} />
    <SectionHeader title="Opening evidence and history" description="Captured source records and revisions are retained. Posted corrections use the existing reversal workflow." />
    {error && <Notice tone="danger"><span role="alert">{error}</span></Notice>}
    <div className="janso-form-actions"><TextField label="Exact line source reference" value={source} maxLength={100} onChange={event => setSource(event.target.value)} /><Button variant="ghost" disabled={working} onClick={() => { if (source && !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/.test(source)) { setError('Enter a valid exact source reference.'); return; } setError(''); setFilter(source); setEntryId(null); }}>Filter evidence</Button>
      {access.export && <Button loading={working} disabled={working} onClick={async () => { setWorking(true); setError(''); try { await download(root + '/export-ticket', company); } catch { setError('The private export is unavailable or access changed. Reload and try again.'); } finally { setWorking(false); } }}>Export opening evidence</Button>}
    </div>
    {[entries, revisions, entry, link, revision].map((read, i) => <AccountingFailure key={i} failure={read.failure} retry={'first' in read ? read.first : read.refresh} />)}
    <Card><DataTable caption="Captured opening entries" columns={entryColumns} rows={entries.data?.items ?? []} loading={entries.loading} rowId={row => row.id} rowLabel={row => row.source_key} emptyTitle="No matching opening entries" /><Pager count={entries.data?.items.length ?? 0} limit={entries.limit} busy={entries.loading || working} hasPrevious={entries.hasPrevious} hasNext={!!entries.data?.page.has_more} onPrevious={entries.previous} onNext={entries.next} onLimitChange={entries.setLimit} noun="entry" /></Card>
    {entry.data && <Card><CardBody><div className="janso-flow"><SectionHeader title={'Source ' + entry.data.source_key} />
      <ReviewList items={[{ label: 'Amount', value: entry.data.amount + ' ' + entry.data.currency }, { label: 'Base value', value: entry.data.base_amount ?? '' }, { label: 'Posting journal', value: postingJournal }, { label: 'Journal status / line', value: postingStatus }]} />
      <FinancialOpeningDocumentEvidence key={entry.data.source_key} documents={entry.data.documents ?? []} currency={entry.data.currency} />
    </div></CardBody></Card>}
    <Card><DataTable caption="Immutable opening revisions" columns={revisionColumns} rows={revisions.data?.items ?? []} loading={revisions.loading} rowId={row => row.id} rowLabel={row => 'Revision ' + row.revision} emptyTitle="No opening revisions" /><Pager count={revisions.data?.items.length ?? 0} limit={revisions.limit} busy={revisions.loading || working} hasPrevious={revisions.hasPrevious} hasNext={!!revisions.data?.page.has_more} onPrevious={revisions.previous} onNext={revisions.next} onLimitChange={revisions.setLimit} noun="revision" /></Card>
    {revision.data && <Card><CardBody><SectionHeader title="Captured revision" /><ReviewList items={[{ label: 'Source', value: revision.data.source_system + ' / ' + revision.data.source_id }, { label: 'Reason', value: revision.data.reason }, { label: 'Opening / coverage date', value: format.date(revision.data.posting_date) + ' / ' + format.date(revision.data.covered_through) }, { label: 'Account lines', value: String(revision.data.entries.length) }, { label: 'Reporting mode', value: revision.data.coverage_mode ?? 'POST_CUTOVER_ONLY' }]} /></CardBody></Card>}
  </div>;
}

function FinancialOpeningBatches({ company }: { company: string }) {
  const format = useFormatters();
  type Batch = components['schemas']['OpeningBatchListItem'];
  const list = useServiceList<Batch>(base(company), '', request, owned(company));
  const columns: Column<Batch>[] = [
    { type: 'custom', key: 'date', header: 'Opening date', render: row => <a className="janso-link" href={'/accounting/opening?batch_id=' + row.id}>{row.posting_date ? format.date(row.posting_date) : 'Date restricted'}</a> },
    { type: 'custom', key: 'status', header: 'Status', render: row => row.status ?? 'Restricted' },
    { type: 'custom', key: 'completed', header: 'Finalized', render: row => row.finalized_at === undefined ? 'Finalization date restricted' : row.finalized_at ? format.dateTime(row.finalized_at) : 'Not finalized' },
  ];
  return <div className="janso-flow"><SectionHeader title="Retained company openings" description="Closed and replaced preparations stay available alongside current and earlier company setup openings." /><AccountingFailure failure={list.failure} retry={list.first} />
    <Card><DataTable caption="Company opening history" columns={columns} rows={list.data?.items ?? []} loading={list.loading} rowId={row => row.id} rowLabel={row => row.posting_date ? format.date(row.posting_date) : row.id} emptyTitle="No retained openings" /><Pager count={list.data?.items.length ?? 0} limit={list.limit} busy={list.loading} hasPrevious={list.hasPrevious} hasNext={!!list.data?.page.has_more} onPrevious={list.previous} onNext={list.next} onLimitChange={list.setLimit} noun="opening" /></Card>
  </div>;
}
