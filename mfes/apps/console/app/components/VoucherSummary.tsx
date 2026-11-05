'use client';
import { useEffect, useMemo, useState } from 'react';
import { ReviewList, useFormatters } from '@janso/ui';
import type { components } from '@janso/api-client/vouchers';
import { voucherReferenceLabels } from '../lib/voucher-reference-labels';
import { trackingId } from '../lib/stock-tracking-resources';

type Voucher = components['schemas']['VoucherDetail'];
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const rows = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.map(record) : [];
const text = (value: unknown) => typeof value === 'string' ? value : '';

/** Render only readable native capture fields; current master labels supplement captured IDs. */
export function VoucherSummary({ company, voucher }: { company: string; voucher: Voucher }) {
  const format = useFormatters();
  const invoice = record(voucher.invoice), financial = record(voucher.financial);
  const supplies = rows(invoice.supplies), accounts = rows(financial.accounts);
  const parties = rows(voucher.parties), references = rows(voucher.references), items = rows(voucher.lines);
  const targets = useMemo(() => {
    const pairs = [
      ...rows(voucher.parties).map(row => ['parties', text(row.party_id)]),
      ...rows(record(voucher.invoice).supplies).map(row => ['accounts', text(row.account_id)]),
      ...rows(record(voucher.financial).accounts).map(row => ['accounts', text(row.account_id)]),
      ['accounts', text(record(voucher.invoice).party_account_id)],
      ...rows(voucher.lines).map(row => ['items', text(record(row.item).item_id)]),
    ];
    return [...new Map(pairs.filter(([, id]) => trackingId.test(id)).map(([resource, id]) => [resource + '/' + id, { resource, id }])).values()].slice(0, 50);
  }, [voucher]);
  const [labels, setLabels] = useState<{ scope: string; names: Record<string, string> }>({ scope: '', names: {} });
  const scope = company + ':' + voucher.id + ':' + voucher.revision_id;
  useEffect(() => {
    const controller = new AbortController();
    setLabels({ scope, names: {} });
    void voucherReferenceLabels(company,targets,controller.signal,rows=>{
      if(controller.signal.aborted)return;
      const names=Object.fromEntries([...rows].filter(([,row])=>row.name||row.code||row.sku).map(([key,row])=>[key,row.name??row.code??row.sku!]));
      setLabels({scope,names});
    });
    return () => controller.abort();
  }, [company, scope, targets]);
  function reference(resource: string, value: unknown) {
    const id = text(value), name = labels.scope === scope ? labels.names[resource + '/' + id] : undefined;
    return name ? <span>{name} <code>{id}</code></span> : <code>{id || 'Unavailable'}</code>;
  }
  const money = (amount: unknown, currency: unknown = voucher.currency) => format.money(text(amount), { display: 'none' }) + (text(currency) ? ' ' + text(currency) : '');
  return <section className="janso-flow janso-voucher-summary" aria-label="Saved voucher summary">
    <h3>Voucher details</h3>
    <ReviewList items={[
      {label:'Voucher',value:<code>{voucher.id}</code>},
      {label:'Revision',value:voucher.revision_number??'Unavailable'},
      ...(voucher.kind?[{label:'Type',value:voucher.kind.replaceAll('_',' ')+(voucher.profile?' · '+voucher.profile.replaceAll('_',' '):'')}]:[]),
      ...(voucher.document_date?[{label:'Document date',value:format.date(voucher.document_date)}]:[]),
      ...(voucher.posting_date?[{label:'Posting date',value:format.date(voucher.posting_date)}]:[]),
      ...(voucher.currency?[{label:'Currency',value:voucher.currency}]:[]),
      ...(voucher.narration?[{label:'Narration',value:voucher.narration}]:[]),
      ...(text(invoice.bill_reference)?[{label:'Supplier invoice reference',value:text(invoice.bill_reference)}]:[]),
      ...(text(invoice.due_date)?[{label:'Payment due date',value:format.date(text(invoice.due_date))}]:[]),
      ...(text(invoice.party_account_id)?[{label:'Supplier payable account',value:reference('accounts',invoice.party_account_id)}]:[]),
      ...(text(financial.purpose)?[{label:'Transaction purpose',value:text(financial.purpose).replaceAll('_',' ')}]:[]),
    ]}/>

    {parties.length > 0 && <ul aria-label="Voucher parties">{parties.map((row, index) => <li key={index}>{text(row.role)}: {reference('parties', row.party_id)}</li>)}</ul>}
    {references.length > 0 && <ul aria-label="Voucher references">{references.map((row, index) => <li key={index}>{text(row.purpose).replaceAll('_', ' ')}: {text(row.reference)}{text(row.reference_date) ? ' · ' + format.date(text(row.reference_date)) : ''}</li>)}</ul>}
    {supplies.length > 0 && <ol aria-label="Invoice lines">{supplies.map((row, index) => <li key={index}>{text(row.description)} · {reference('accounts', row.account_id)} · {money(row.amount)}</li>)}</ol>}
    {accounts.length > 0 && <ol aria-label="Account entries">{accounts.map((row, index) => <li key={index}>{reference('accounts', row.account_id)} · {text(row.side)} · {money(row.amount, row.currency)}{text(row.description) ? ' · ' + text(row.description) : ''}</li>)}</ol>}
    {items.length > 0 && <ol aria-label="Item lines">{items.map((row, index) => {
      const item = record(row.item);
      return <li key={index}>{text(row.description) || text(row.line_kind)} · {reference('items', item.item_id)}{text(item.actual_quantity) ? ' · Quantity ' + format.quantity(text(item.actual_quantity)) : ''}{text(item.billed_quantity) ? ' · Billed ' + format.quantity(text(item.billed_quantity)) : ''}</li>;
    })}</ol>}
    {voucher.invoice === null || voucher.financial === null || voucher.lines === null ? <p>Some detail fields are unavailable with your current field access.</p> : null}
  </section>;
}
