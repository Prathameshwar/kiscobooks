'use client';
import { useState } from 'react';
import { Button, Card, CardBody, DataTable, FormActions, Notice, ReviewList, SearchSelect, SectionHeader, Select, TextField, useFormatters, type Column } from '@janso/ui';
import { entryError, sum, type Declaration, type Entry, type Document, type CaptureMetadata, type FieldSet } from '../lib/financial-opening';
import { lookup } from '../lib/voucher-fields';
import { accountingRequest } from '../lib/accounting-configuration';
import { useServiceRead } from '../lib/service-resource';
import { AccountingFailure } from './AccountingConfigurationCommon';

export function FinancialOpeningEntry({ company, declaration, initial, metadata, native, disabled, onSave, onCancel, onDirty }: {
  company: string; declaration: Declaration; initial: Entry; metadata: CaptureMetadata; native: FieldSet[];
  disabled: boolean; onSave: (entry: Entry) => void; onCancel: () => void; onDirty: () => void;
}) {
  const [entry, setEntry] = useState<Entry>(initial), [error, setError] = useState(''), [documentEditing, setDocumentEditing] = useState(false);
  const account = useServiceRead<{ id: string; company_id: string; name?: string; code?: string; kind?: string; party_role?: string; currency?: string; currency_mode?: string; status?: string }>(
    entry.account_id ? `/v1/companies/${company}/accounts/${entry.account_id}` : undefined, accountingRequest,
    row => { if (row.company_id !== company || row.id !== entry.account_id) throw { status: 502, message: 'Account ownership could not be verified.' }; },
  );
  const fields = metadata.capture.$defs?.OpeningEntry?.properties ?? {};
  const permitted = (key: string, nativeKey = key) => !!fields[key] && !!metadata.capture_permissions.journal_lines[nativeKey];
  const patch = (change: Partial<Entry>) => { setEntry(value => ({ ...value, ...change })); setError(''); onDirty(); };
  const party = account.data?.kind === 'PARTY', documents = entry.documents ?? [];
  const canWriteDocuments = ['account_id', 'party_id', 'role', 'direction', 'reference', 'currency', 'amount', 'base_currency', 'base_amount', 'document_date', 'due_date', 'posting_date', 'terms'].every(key =>
    metadata.capture_permissions.open_items[key]);
  const canEdit = !disabled && !account.failure;
  function save() {
    const problem = entryError(entry, declaration) ?? (account.data?.status !== 'ACTIVE' ? 'Choose an active, readable account.' : party && !documents.length ? 'Add outstanding documents or an explicit on-account balance for this party account.' : !party && documents.length ? 'Only a party ledger can carry outstanding documents.' : null);
    if (problem) { setError(problem); return; }
    onSave(entry);
  }
  return <Card><CardBody><div className="janso-flow">
    <SectionHeader title="Account opening line" description="Use the balance at books begin. Historical bill balances belong to the selected party ledger." />
    {error && <Notice tone="danger"><span role="alert">{error}</span></Notice>}
    <AccountingFailure failure={account.failure} retry={account.refresh} />
    <div className="janso-form-grid">
      {fields.account_id && <SearchSelect label="Ledger account" scopeKey={company + ':opening-accounts'} loadOptions={lookup(company, 'accounts')} value={entry.account_id || null}
        selected={account.data ? { id: account.data.id, label: account.data.name ?? account.data.code ?? 'Selected account' } : undefined}
        disabled={!canEdit || documentEditing || !!documents.length || !permitted('account_id')} onChange={value => patch({ account_id: value ?? '' })} />}
      {fields.side && <Select label="Balance side" value={entry.side} disabled={!canEdit || documentEditing || !!documents.length || !permitted('side')} options={[{ value: 'DEBIT', label: 'Debit' }, { value: 'CREDIT', label: 'Credit' }]} onChange={side => patch({ side: side as Entry['side'] })} />}
      {fields.currency && <TextField label="Currency" value={entry.currency} maxLength={3} disabled={!canEdit || documentEditing || !!documents.length || !permitted('currency')} onChange={event => patch({ currency: event.target.value.toUpperCase(), ...(event.target.value.toUpperCase() === declaration.currency ? { exchange_rate: '1', base_amount: entry.amount } : {}) })} />}
      {fields.amount && <TextField label="Opening amount" inputMode="decimal" value={entry.amount} disabled={!canEdit || !permitted('amount')} onChange={event => patch({ amount: event.target.value, ...(entry.currency === declaration.currency ? { base_amount: event.target.value } : {}) })} />}
      {entry.currency !== declaration.currency && fields.exchange_rate && <TextField label="Historical exchange rate" inputMode="decimal" value={entry.exchange_rate} disabled={!canEdit || !permitted('exchange_rate')} hint="Use the migration rate, not today’s quote. The historical base carrying value is preserved separately." onChange={event => patch({ exchange_rate: event.target.value })} />}
      {fields.base_amount && <TextField label={`Base carrying value (${declaration.currency})`} inputMode="decimal" value={entry.base_amount ?? ''} disabled={!canEdit || entry.currency === declaration.currency || !permitted('base_amount', 'opening_base_amount')} onChange={event => patch({ base_amount: event.target.value })} />}
      {fields.source_key && <TextField label="Line source reference" value={entry.source_key} maxLength={100} disabled={!canEdit} hint="A stable, unique migration reference. Generated for a new line." onChange={event => patch({ source_key: event.target.value })} />}
      {fields.description && <TextField label="Line description" value={entry.description ?? ''} maxLength={500} disabled={!canEdit || !permitted('description')} onChange={event => patch({ description: event.target.value || null })} />}
    </div>
    {account.loading && <Notice>Loading the selected account…</Notice>}
    {party && <><Notice>{account.data?.party_role === 'SUPPLIER' ? 'Supplier credit normally represents bills payable; debit normally represents advances or credits.' : 'Customer debit normally represents invoices receivable; credit normally represents advances or credits.'} Use separate lines for opposite-side balances. Remove existing documents before changing their ledger, side or currency.</Notice>
      {!canWriteDocuments && <Notice>Outstanding document fields are restricted by your current permissions. Ask an authorized controller to capture or revise these documents.</Notice>}
      <FinancialOpeningDocuments key={entry.account_id + ':' + entry.side} documents={documents} currency={entry.currency} baseCurrency={declaration.currency} coveredThrough={declaration.covered_through}
        role={account.data?.party_role ?? ''} side={entry.side} disabled={!canEdit || !canWriteDocuments} onEditing={setDocumentEditing} onChange={rows => patch({ documents: rows })} />
    </>}
    {documents.length > 0 && <ReviewList items={[{ label: 'Outstanding document total', value: safeTotal(documents.map(row => row.amount)) + ' ' + entry.currency }, { label: 'Document carrying total', value: safeTotal(documents.map(row => row.base_amount ?? '')) + ' ' + declaration.currency }]} />}
  </div></CardBody><FormActions cancel={{ onCancel, disabled }}><Button type="button" disabled={!canEdit || account.loading || documentEditing} onClick={save}>Keep account line</Button></FormActions></Card>;
}
function safeTotal(values: string[]) { try { return sum(values); } catch { return 'Incomplete'; } }

function FinancialOpeningDocuments({ documents, currency, baseCurrency, coveredThrough, role, side, disabled, onChange, onEditing }: {
  documents: Document[]; currency: string; baseCurrency: string; coveredThrough: string; role: string; side: string; disabled: boolean; onChange: (rows: Document[]) => void; onEditing: (editing: boolean) => void;
}) {
  const format = useFormatters();
  const [draft, setDraft] = useState<Document | null>(null), [index, setIndex] = useState<number | null>(null), [error, setError] = useState('');
  const ordinary = role === 'SUPPLIER' ? side === 'CREDIT' : side === 'DEBIT';
  const defaultKind = ordinary ? role === 'SUPPLIER' ? 'BILL' : 'INVOICE' : 'ADVANCE';
  function add() { setIndex(null); setError(''); onEditing(true); setDraft({ line_sequence: 1, source_key: crypto.randomUUID(), document_kind: defaultKind, reference: '', amount: '', base_amount: '', document_date: coveredThrough, due_date: coveredThrough }); }
  function patch(change: Partial<Document>) { setDraft(value => value ? { ...value, ...change } as Document : value); setError(''); }
  function keep() {
    if (!draft) return;
    if (documents.some((row, i) => i !== index && (row.reference.trim().toLowerCase() === draft.reference.trim().toLowerCase() || !!draft.source_key && row.source_key?.toLowerCase() === draft.source_key.toLowerCase()))) {
      setError('Each outstanding document needs a unique reference and source key.'); return;
    }
    const probe: Entry = { source_key: 'document-check', account_id: '0199abcd-abcd-7000-8000-000000000001', side: 'DEBIT', currency, amount: draft.amount, base_amount: draft.base_amount, exchange_rate: '1', documents: [draft] };
    const problem = entryError(probe, { currency: baseCurrency, covered_through: coveredThrough } as Declaration);
    // Foreign lines can use a distinct historical carrying value; all document checks still apply.
    if (problem) { setError(problem); return; }
    const rows = [...documents]; if (index === null) rows.push(draft); else rows[index] = draft;
    onChange(rows); setDraft(null); onEditing(false);
  }
  const columns: Column<Document & { id: string }>[] = [
    { type: 'custom', key: 'reference', header: 'Reference', render: row => row.reference },
    { type: 'custom', key: 'kind', header: 'Type', render: row => row.document_kind === 'ON_ACCOUNT' ? 'On account · dates unknown' : row.document_kind?.replaceAll('_', ' ') ?? 'Document' },
    { type: 'custom', key: 'due', header: 'Due', render: row => row.due_date ? format.date(row.due_date) : 'Unknown' },
    { type: 'custom', key: 'amount', header: `Outstanding (${currency})`, render: row => row.amount },
    { type: 'custom', key: 'actions', header: 'Actions', render: row => <div className="janso-form-actions"><Button variant="ghost" disabled={disabled || !!draft} onClick={() => { setIndex(+row.id); setDraft(documents[+row.id]!); onEditing(true); setError(''); }}>Edit {row.reference}</Button><Button variant="ghost" disabled={disabled || !!draft} onClick={() => onChange(documents.filter((_, i) => i !== +row.id))}>Remove {row.reference}</Button></div> },
  ];
  return <section className="janso-flow" aria-label="Opening documents"><SectionHeader title="Outstanding documents" description="Enter only the amount still unpaid at cutover. Use on account when old document dates are genuinely unknown." />
    <DataTable caption="Party opening documents" columns={columns} rows={documents.map((row, i) => ({ ...row, id: String(i) }))} rowId={row => row.id} rowLabel={row => row.reference} emptyTitle="No outstanding documents" emptyBody="Add bills, invoices, credits or an explicitly labelled on-account balance." />
    {!draft && <Button type="button" variant="ghost" disabled={disabled || documents.length >= 1000} onClick={add}>Add outstanding document</Button>}
    {draft && <Card><CardBody><div className="janso-flow"><SectionHeader title={index === null ? 'New outstanding document' : 'Edit outstanding document'} />
      {error && <Notice tone="danger"><span role="alert">{error}</span></Notice>}
      <div className="janso-form-grid"><Select label="Document type" value={draft.document_kind ?? defaultKind} disabled={disabled} options={[
        ...(ordinary ? [{ value: role === 'SUPPLIER' ? 'BILL' : 'INVOICE', label: role === 'SUPPLIER' ? 'Supplier bill' : 'Customer invoice' }] : [{ value: 'ADVANCE', label: 'Advance' }, { value: 'CREDIT_NOTE', label: 'Credit note' }]),
        { value: 'ON_ACCOUNT', label: 'On account — dates unknown' },
      ]} onChange={value => patch(value === 'ON_ACCOUNT' ? { document_kind: 'ON_ACCOUNT', document_date: null, due_date: null } : { document_kind: value as 'INVOICE' | 'BILL' | 'ADVANCE' | 'CREDIT_NOTE', document_date: coveredThrough, due_date: coveredThrough })} />
      <TextField label="Document reference" value={draft.reference} maxLength={120} disabled={disabled} onChange={event => patch({ reference: event.target.value })} />
      <TextField label={`Outstanding amount (${currency})`} inputMode="decimal" value={draft.amount} disabled={disabled} onChange={event => patch({ amount: event.target.value, ...(currency === baseCurrency ? { base_amount: event.target.value } : {}) })} />
      <TextField label="Original face amount" optionalNote="Optional" inputMode="decimal" value={draft.original_amount ?? ''} disabled={disabled} onChange={event => patch({ original_amount: event.target.value || null })} />
      <TextField label={`Document base carrying value (${baseCurrency})`} inputMode="decimal" value={draft.base_amount ?? ''} disabled={disabled || currency === baseCurrency} onChange={event => patch({ base_amount: event.target.value })} />
      {draft.document_kind !== 'ON_ACCOUNT' && <><TextField label="Document date" type="date" max={coveredThrough} value={draft.document_date ?? ''} disabled={disabled} onChange={event => patch({ document_date: event.target.value })} /><TextField label="Due date" type="date" min={draft.document_date ?? undefined} value={draft.due_date ?? ''} disabled={disabled} onChange={event => patch({ due_date: event.target.value })} /></>}
      </div>{draft.document_kind === 'ON_ACCOUNT' && <Notice>Dates remain unknown. This balance counts toward exposure, but cannot establish overdue age or automatic interest.</Notice>}
      <div className="janso-form-actions"><Button type="button" variant="ghost" disabled={disabled} onClick={() => { setDraft(null); onEditing(false); }}>Cancel document</Button><Button type="button" disabled={disabled} onClick={keep}>Keep document</Button></div>
    </div></CardBody></Card>}
  </section>;
}
