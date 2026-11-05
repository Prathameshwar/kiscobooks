'use client';
import {useRef, useState} from 'react';
import {Button, Select, TextField, useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/accounting';
import {productFieldRequest as request} from '../lib/product-fields';

type Instrument = components['schemas']['BankInstrumentListItem'];
type Event = components['schemas']['BankEventDetail'];
type FieldSet = components['schemas']['FieldSet'];

export function BankingHistory({company, permissions}: {company: string; permissions: readonly string[]}) {
  const base = '/v1/companies/' + company;
  const format = useFormatters();
  const [items, setItems] = useState<Instrument[]>([]), [cursor, setCursor] = useState<string | null>(null);
  const [instrument, setInstrument] = useState(''), [events, setEvents] = useState<Event[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null), [fields, setFields] = useState<FieldSet | null>(null);
  const [action, setAction] = useState(''), [date, setDate] = useState(''), [reference, setReference] = useState(''), [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const retry = useRef<{payload: string; key: string} | null>(null);
  if (!permissions.includes('accounting.bank.read')) return null;
  const writable = (key: string) => fields?.fields.some(field => field.key === key && field.writable && field.readable);
  const actions = fields?.fields.find(field => field.key === 'action')?.definition.enum;
  const latest = events.at(-1);
  async function act(work: () => Promise<void>) {
    setBusy(true); setMessage('');
    try { await work(); } catch (error) { setMessage(error instanceof Error ? error.message : 'Unable to load bank history'); }
    finally { setBusy(false); }
  }
  async function load(next: string | null) {
    const page = await request<components['schemas']['BankInstrumentPage']>('accounting', 'GET', base + '/bank-instruments?limit=50' + (next ? '&cursor=' + encodeURIComponent(next) : ''));
    setItems(previous => next ? [...previous, ...page.items] : page.items); setCursor(page.page.next_cursor);
  }
  async function history(id: string, next: string | null) {
    const page = await request<components['schemas']['BankEventPage']>('accounting', 'GET', base + '/bank-instruments/' + id + '/events?limit=50' + (next ? '&cursor=' + encodeURIComponent(next) : ''));
    setEvents(previous => next ? [...previous, ...page.items] : page.items); setHistoryCursor(page.page.next_cursor);
  }
  return <section aria-label="Banking history"><h2>Banking history</h2>
    <Button disabled={busy} onClick={() => void act(() => load(null))}>Load payment instruments</Button>
    <ul>{items.map(row => <li key={row.id}><Button disabled={busy} onClick={() => void act(async () => {
      setInstrument(''); setFields(null); setEvents([]);
      await history(row.id, null);
      setFields(await request<FieldSet>('accounting', 'GET', base + '/finance/field-sets/bank-instrument-events'));
      setInstrument(row.id); setAction(''); setDate(''); setReference(''); setReason('');
    })}>{row.mode ?? 'Payment'} {row.booking_date ? format.date(row.booking_date) : ''} {row.amount != null ? format.money(row.amount, {display: 'none'}) : ''} {row.currency}</Button></li>)}</ul>
    {cursor && <Button disabled={busy} onClick={() => void act(() => load(cursor))}>More payment instruments</Button>}
    {instrument && <><p>Instrument: {instrument}</p><ol>{events.map(row => <li key={row.id}>{row.action} {row.event_date ? format.date(row.event_date) : ''} {row.reference}</li>)}</ol>
      {historyCursor && <Button disabled={busy} onClick={() => void act(() => history(instrument, historyCursor))}>More instrument history</Button>}
      <Button disabled={busy} onClick={() => void act(() => history(instrument, null))}>Refresh instrument history</Button>
      {permissions.includes('accounting.bank.manage') && fields && <form onSubmit={event => {
        event.preventDefault(); void act(async () => {
          const body = {expected_event_id: latest?.id, action, event_date: date, reason, ...(writable('reference') && reference ? {reference} : {})};
          const path = base + '/bank-instruments/' + instrument + '/events', payload = JSON.stringify({path, body});
          if (retry.current?.payload !== payload) retry.current = {payload, key: crypto.randomUUID()};
          const result = await request<Event>('accounting', 'POST', path, body, retry.current.key);
          retry.current = null; setEvents(previous => [...previous, result]); setMessage('Bank history recorded.');
        });
      }}>
        {writable('action') && <Select label="Bank action" value={action} options={Array.isArray(actions) ? actions.filter((value): value is string => typeof value === 'string').map(value => ({value, label: value.replaceAll('_', ' ')})) : []} disabled={busy} onChange={setAction}/>}
        {writable('event_date') && <TextField label="Bank event date" type="date" value={date} required disabled={busy} onChange={event => setDate(event.target.value)}/>}
        {writable('reference') && <TextField label="Bank evidence reference" value={reference} maxLength={120} required={action === 'RECONCILED'} disabled={busy} onChange={event => setReference(event.target.value)}/>}
        {writable('reason') && <TextField label="Bank event reason" value={reason} minLength={3} maxLength={500} required disabled={busy} onChange={event => setReason(event.target.value)}/>}
        <Button type="submit" disabled={busy || !!historyCursor || !latest || !action || !date || reason.trim().length < 3 || !['action','event_date','reason','expected_event_id'].every(writable)}>Record bank event</Button>
      </form>}
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
