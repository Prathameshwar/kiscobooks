'use client';

import { Fragment, useId, useState } from 'react';
import { Badge, Button, useFormatters } from '@janso/ui';
import { dayBookHref, kindLabel, statusLabel, type DayBookFilters, type DayBookRow, type DayBookSummary } from '../lib/day-book';

export type DayBookColumns = { date: boolean; kind: boolean; narration: boolean; status: boolean };
export const defaultColumns: DayBookColumns = { date: true, kind: true, narration: false, status: true };

export function DayBookSummaryStrip({ summary, scope }: { summary: DayBookSummary | null; scope: DayBookFilters['scope'] }) {
  const format = useFormatters();
  const figures = scope === 'POSTED' ? [
    { label: 'Vouchers', value: summary?.voucher_count, note: 'Distinct source documents' },
    { label: 'Journal postings', value: summary?.journal_count, note: summary?.line_count !== undefined ? summary.line_count + ' accounting lines' : 'Committed accounting events' },
    { label: 'Total debit', value: summary?.debit ? format.money(summary.debit, { display: 'none' }) : undefined, note: summary?.currency ?? 'Company currency' },
    { label: 'Total credit', value: summary?.credit ? format.money(summary.credit, { display: 'none' }) : undefined, note: summary?.currency ?? 'Company currency' },
  ] : [
    { label: 'Vouchers', value: summary?.voucher_count, note: 'All matching documents' },
    { label: 'Draft', value: summary ? summary.by_status?.DRAFT ?? 0 : undefined, note: 'Saved, awaiting submission' },
    { label: 'Submitted', value: summary ? summary.by_status?.SUBMITTED ?? 0 : undefined, note: 'Awaiting review' },
    { label: 'Other statuses', value: summary ? summary.voucher_count - (summary.by_status?.DRAFT ?? 0) - (summary.by_status?.SUBMITTED ?? 0) : undefined, note: 'Issued, executed and other states' },
  ];
  return <dl className="janso-day-book__summary" aria-label="Report totals">{figures.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value ?? '—'}</dd><span>{item.note}</span></div>)}</dl>;
}

export function DayBookResults({ rows, summary, filters, columns, returnTo, canOpen }: {
  rows: DayBookRow[]; summary: DayBookSummary | null; filters: DayBookFilters; columns: DayBookColumns; returnTo: string; canOpen: boolean;
}) {
  const format = useFormatters();
  const prefix = useId();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const posted = filters.scope === 'POSTED', accounting = posted && filters.mode === 'ACCOUNTING';
  const cols = 3 + Number(columns.date) + Number(columns.kind) + Number(columns.status) + Number(columns.narration) + (posted ? 2 : 1) + Number(accounting);
  const keyOf = (row: DayBookRow) => row.line_id ?? row.id;
  const toggle = (key: string) => setExpanded(previous => { const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  function link(row: DayBookRow) {
    const href = canOpen ? dayBookHref(row, returnTo) : null;
    return href ? <a className="janso-day-book__number" href={href}>{row.number || 'Unnumbered'}</a> : <span className="janso-day-book__number">{row.number || 'Unnumbered'}</span>;
  }
  const money = (value?: string) => value === undefined ? '—' : format.money(value, { display: 'none' });
  const badge = (row: DayBookRow) => <Badge tone={row.status === 'POSTED' || row.status === 'EXECUTED' ? 'success' : row.status === 'REJECTED' || row.status === 'CANCELLED' ? 'neutral' : 'info'}>{statusLabel(row.status)}</Badge>;
  function detail(row: DayBookRow) {
    return <div className="janso-day-book__expanded">
      <div className="janso-day-book__detail-head"><strong>{kindLabel(row.kind)} · {row.number || 'Unnumbered'}</strong><span>{row.type_name ?? row.profile?.replaceAll('_', ' ').toLowerCase()}</span></div>
      {row.narration && <p className="janso-day-book__narration">{row.narration}</p>}
      {(row.journals ?? []).map(journal => <section key={journal.journal_id} aria-label={'Journal ' + (journal.number || 'Unnumbered')}>
        <p className="janso-day-book__journal-label">{format.date(journal.date)} · {journal.number}{journal.reversal_of_id ? ' · Reversal entry' : ''}</p>
        <div className="janso-day-book__entry-scroll" tabIndex={0} role="region" aria-label="Accounting entries">
          <table className="janso-day-book__entries"><caption className="janso-visually-hidden">Journal accounting entries</caption><thead><tr><th scope="col">Account</th><th scope="col">Debit</th><th scope="col">Credit</th></tr></thead>
            <tbody>{journal.entries.map((entry, index) => <tr key={entry.line_id ?? index}><td><span className="janso-day-book__account-code">{entry.account_code}</span>{entry.account_name}</td><td>{money(entry.debit)}</td><td>{money(entry.credit)}</td></tr>)}</tbody>
            <tfoot><tr><th scope="row">Journal total · {journal.currency}</th><td>{money(journal.debit)}</td><td>{money(journal.credit)}</td></tr></tfoot>
          </table>
        </div>
      </section>)}
      {canOpen && dayBookHref(row, returnTo) && <a className="janso-link" href={dayBookHref(row, returnTo)!}>Open voucher →</a>}
      {!row.voucher_id && <p className="janso-day-book__muted">Standalone accounting journal. Its complete entries are shown above.</p>}
    </div>;
  }
  const groupKey = (row: DayBookRow) => filters.group_by === 'none' ? '' : String(row[filters.group_by] ?? 'Other');
  function groupLabel(key: string) { return filters.group_by === 'date' ? format.date(key) : filters.group_by === 'kind' ? kindLabel(key) : key; }
  return <>
    <div className="janso-day-book__table-scroll" tabIndex={0} role="region" aria-label="Day Book transactions">
      <table className="janso-day-book__table"><caption className="janso-visually-hidden">{accounting ? 'Day Book accounting entries' : 'Day Book vouchers'}</caption>
        <thead><tr><th scope="col"><span className="janso-visually-hidden">Details</span></th>{columns.date && <th scope="col">{posted ? 'Posting date' : 'Document date'}</th>}{columns.kind && <th scope="col">Type</th>}<th scope="col">Voucher no.</th><th scope="col">Particulars</th>{accounting && <th scope="col">Ledger account</th>}{posted ? <><th scope="col" className="janso-day-book__amount">Debit</th><th scope="col" className="janso-day-book__amount">Credit</th></> : <th scope="col">Currency</th>}{columns.status && <th scope="col">Status</th>}{columns.narration && <th scope="col">Narration</th>}</tr></thead>
        <tbody>{rows.map((row, index) => {
          const key = keyOf(row), open = expanded.has(key), group = groupKey(row), newGroup = group && (index === 0 || groupKey(rows[index - 1]) !== group);
          const subtotal = summary?.groups?.[group];
          return <Fragment key={key}>
            {newGroup && <tr className="janso-day-book__group"><th colSpan={cols} scope="rowgroup"><span>{groupLabel(group)}</span><span>{subtotal ? subtotal.count + ' voucher entries · Debit ' + money(subtotal.debit) + ' · Credit ' + money(subtotal.credit) : 'Document activity'}</span></th></tr>}
            <tr className="janso-day-book__row" data-expanded={open || undefined}>
              <td>{!accounting && <button className="janso-day-book__expand" aria-label={(open ? 'Collapse ' : 'Expand ') + (row.number || kindLabel(row.kind))} aria-expanded={open} aria-controls={prefix + key} onClick={() => toggle(key)}>{open ? '▾' : '▸'}</button>}</td>
              {columns.date && <td className="janso-day-book__date">{format.date(row.date)}</td>}
              {columns.kind && <td><span className="janso-day-book__kind">{kindLabel(row.kind)}</span>{row.type_code && <small>{row.type_code}</small>}</td>}
              <td>{link(row)}</td><td className="janso-day-book__particulars">{row.particulars}{!accounting && !!row.journal_count && row.journal_count > 1 && <small>{row.journal_count} journal postings</small>}</td>
              {accounting && <td><small>{row.account_code}</small>{row.account_name}</td>}
              {posted ? <><td className="janso-day-book__amount">{money(row.debit)}</td><td className="janso-day-book__amount">{money(row.credit)}</td></> : <td>{row.currency}</td>}
              {columns.status && <td>{badge(row)}</td>}{columns.narration && <td className="janso-day-book__narration-cell">{row.narration || '—'}</td>}
            </tr>
            {!accounting && open && <tr id={prefix + key}><td colSpan={cols}>{detail(row)}</td></tr>}
          </Fragment>;
        })}</tbody>
      </table>
    </div>
    {!accounting && <div className="janso-day-book__mobile-list" aria-label="Day Book voucher list">{rows.map(row => {
      const key = keyOf(row), open = expanded.has(key);
      return <section className="janso-day-book__mobile-row" key={key}><div><strong>{kindLabel(row.kind)}</strong>{badge(row)}</div><div>{link(row)}<span>{format.date(row.date)}</span></div><p>{row.particulars}</p>{posted ? <div><span>Debit {money(row.debit)}</span><span>Credit {money(row.credit)}</span></div> : <p className="janso-day-book__muted">Document currency: {row.currency}</p>}<Button variant="ghost" aria-expanded={open} aria-controls={prefix + 'mobile-' + key} onClick={() => toggle(key)}>{open ? 'Hide details' : 'View details'}</Button>{open && <div id={prefix + 'mobile-' + key}>{detail(row)}</div>}</section>;
    })}</div>}
  </>;
}
