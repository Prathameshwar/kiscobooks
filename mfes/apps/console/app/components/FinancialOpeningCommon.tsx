'use client';
import { useState } from 'react';
import { Button, DataTable, Notice, useFormatters, type Column } from '@janso/ui';
import type { RequestFailure } from '../lib/service-call';
import type { Document } from '../lib/financial-opening';
import { accountingRequest } from '../lib/accounting-configuration';
import { useServiceRead } from '../lib/service-resource';

/** Resolve names through the existing scoped, field-protected master owner. */
export function FinancialOpeningAccount({ company, id, onLeave }: { company: string; id: string; onLeave?: React.MouseEventHandler<HTMLAnchorElement> }) {
  const read = useServiceRead<{ company_id: string; id: string; name?: string; code?: string }>(`/v1/companies/${company}/accounts/${id}`, accountingRequest, row => {
    if (row.company_id !== company || row.id !== id) throw { status: 502, message: 'Account ownership could not be verified.' };
  });
  if (!read.data || read.failure) return <span className="janso-caption">{read.loading ? 'Loading account…' : 'Account name unavailable'}</span>;
  return <a className="janso-link" href={`/accounting/accounts/${id}`} onClick={onLeave}>{read.data.name ?? read.data.code ?? 'Account details'}</a>;
}

export function FinancialOpeningMoney({ value, currency }: { value: string | null | undefined; currency?: string }) {
  const format = useFormatters();
  return <span className="janso-figure">{format.money(value, { display: 'none' })}{value && currency ? ' ' + currency : ''}</span>;
}

export function FinancialOpeningFieldErrors({ failure }: { failure: RequestFailure | null }) {
  if (!failure?.fields || !Object.keys(failure.fields).length) return null;
  return <Notice tone="danger"><ul>{Object.entries(failure.fields).map(([field, message]) => <li key={field}><strong>{field.replace(/entries\.(\d+)/g, (_, index: string) => 'Opening line ' + (+index + 1)).replaceAll('_', ' ')}:</strong> {message}</li>)}</ul></Notice>;
}

export function FinancialOpeningDocumentEvidence({ documents, currency }: { documents: Document[]; currency: string }) {
  const format = useFormatters();
  const [page, setPage] = useState(0);
  const columns: Column<Document & { id: string }>[] = [
    { type: 'custom', key: 'reference', header: 'Reference', render: row => row.reference },
    { type: 'custom', key: 'kind', header: 'Type', render: row => row.document_kind?.replaceAll('_', ' ') ?? 'Document' },
    { type: 'custom', key: 'dates', header: 'Document / due date', render: row => `${row.document_date ? format.date(row.document_date) : 'Unknown'} / ${row.due_date ? format.date(row.due_date) : 'Unknown'}` },
    { type: 'custom', key: 'original', header: 'Original amount', render: row => row.original_amount ? <FinancialOpeningMoney value={row.original_amount} /> : 'Not supplied' },
    { type: 'custom', key: 'amount', header: `Outstanding (${currency})`, render: row => <FinancialOpeningMoney value={row.amount} /> },
    { type: 'custom', key: 'base', header: 'Base carrying value', render: row => row.base_amount ? <FinancialOpeningMoney value={row.base_amount} /> : 'Derived in validation' },
  ];
  return <div className="janso-flow"><DataTable caption="Captured outstanding documents" columns={columns} rows={documents.slice(page * 25, (page + 1) * 25).map((row, i) => ({ ...row, id: String(page * 25 + i) }))} rowId={row => row.id} rowLabel={row => row.reference} emptyTitle="No outstanding documents" />
    <div className="janso-form-actions"><Button variant="ghost" disabled={!page} onClick={() => setPage(n => n - 1)}>Previous documents</Button><span className="janso-caption">Page {page + 1} of {Math.max(1, Math.ceil(documents.length / 25))}</span><Button variant="ghost" disabled={(page + 1) * 25 >= documents.length} onClick={() => setPage(n => n + 1)}>Next documents</Button></div>
  </div>;
}
