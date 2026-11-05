'use client';

import { useEffect, useMemo, useRef } from 'react';
import { Button, Drawer, SearchSelect, Select, TextField, useDisplayConfig, businessToday } from '@janso/ui';
import type { FiscalYearChoice } from '../lib/company-context';
import { kindOptions, statusLabel, type DayBookFilters as Filters } from '../lib/day-book';
import { reportLookup } from '../lib/report-references';

type Props = {
  company: string; value: Filters; change: (update: Partial<Filters>) => void;
  apply: () => void; advanced: boolean; setAdvanced: (open: boolean) => void;
  busy: boolean; canApply: boolean; typeBusy: boolean; chooseType: (id: string | null, label?: string) => void;
  canReadVouchers: boolean; canReadParties: boolean; canReadAccounts: boolean; year?: FiscalYearChoice | null;
};
export function DayBookFilters({ company, value, change, apply, advanced, setAdvanced, busy, canApply, typeBusy, chooseType, canReadVouchers, canReadParties, canReadAccounts, year }: Props) {
  const config = useDisplayConfig();
  const focusCondition = useRef<number | null>(null);
  const conditionFields = useRef<HTMLFieldSetElement | null>(null);
  useEffect(() => {
    const index = focusCondition.current;
    if (index === null) return;
    focusCondition.current = null;
    const fieldset = conditionFields.current;
    const target = fieldset?.querySelectorAll<HTMLInputElement>('.janso-day-book__condition input')[index] ?? fieldset?.lastElementChild;
    if (target instanceof HTMLElement) target.focus();
  }, [value.conditions.length]);
  const parties = useMemo(() => reportLookup(company, 'parties'), [company]);
  const accounts = useMemo(() => reportLookup(company, 'accounts'), [company]);
  const types = useMemo(() => reportLookup(company, 'voucher-types'), [company]);
  function periodRange(preset: string) {
    const today = businessToday(config.timezone);
    const date = new Date(today + 'T00:00:00Z');
    const iso = (item: Date) => item.toISOString().slice(0, 10);
    let from = today, to = today;
    if (preset === 'yesterday') { date.setUTCDate(date.getUTCDate() - 1); from = to = iso(date); }
    if (preset === 'month') from = today.slice(0, 8) + '01';
    if (preset === 'last-month') { date.setUTCDate(0); to = iso(date); from = to.slice(0, 8) + '01'; }
    if (preset === 'year' && year) { from = year.startDate; to = year.endDate; }
    return { date_from: from, date_to: to };
  }
  const presets = [{ value: 'today', label: 'Today' }, { value: 'yesterday', label: 'Yesterday' }, { value: 'month', label: 'This month' }, { value: 'last-month', label: 'Last month' }, ...(year ? [{ value: 'year', label: year.code }] : [])];
  const selectedPreset = presets.find(item => { const range = periodRange(item.value); return range.date_from === value.date_from && range.date_to === value.date_to; })?.value ?? '';
  const advancedCount = [value.type_id, value.account_id, value.amount_min, value.amount_max, value.basis === 'TRANSACTION', value.conditions.length > 0].filter(Boolean).length;
  return <>
    <form className="janso-day-book__filters" onSubmit={event => { event.preventDefault(); if (canApply && !busy && !typeBusy) apply(); }} aria-label="Day Book filters">
      <div className="janso-day-book__filter-grid">
        <div className="janso-day-book__period">
          <Select label="Period preset" value={selectedPreset} options={[{ value: '', label: 'Custom period' }, ...presets]} onChange={preset => { if (preset) change(periodRange(preset)); }} disabled={busy} />
          <div className="janso-day-book__date-range">
            <TextField label="From date" type="date" value={value.date_from} required disabled={busy} onChange={event => change({ date_from: event.target.value })} />
            <TextField label="To date" type="date" value={value.date_to} required disabled={busy} onChange={event => change({ date_to: event.target.value })} />
          </div>
        </div>
        <SearchSelect label="Voucher kind" options={kindOptions} multiple value={value.kinds} selected={kindOptions.filter(item => value.kinds.includes(item.id))} onChange={kinds => change({ kinds })} placeholder="All voucher kinds" disabled={busy} />
        {canReadParties && <SearchSelect label="Party" scopeKey={company + ':parties'} loadOptions={parties} value={value.party_id || null} selected={value.party_id ? { id: value.party_id, label: value.party_label || 'Selected party' } : null} onChange={(id, option) => change({ party_id: id ?? '', party_label: option?.label ?? '' })} placeholder="All customers and suppliers" disabled={busy} />}
        {value.scope === 'ALL' && <Select label="Document status" value={value.status} onChange={status => change({ status })} disabled={busy} options={[{ value: '', label: 'All statuses' }, ...['DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'ISSUED', 'POSTED', 'REVERSED', 'CANCELLED', 'ACCEPTED', 'DECLINED', 'EXPIRED'].map(status => ({ value: status, label: statusLabel(status) }))]} />}
      </div>
      <div className="janso-day-book__search-row">
        <TextField label="Search transactions" type="search" value={value.q} maxLength={120} placeholder={value.scope === 'ALL' ? 'Voucher number, type or narration…' : 'Voucher number, party, ledger or narration…'} onChange={event => change({ q: event.target.value })} disabled={busy} />
        <Button type="button" variant="ghost" onClick={() => setAdvanced(true)} disabled={busy}>More filters{advancedCount ? ' · ' + advancedCount : ''}</Button>
        <Button type="submit" disabled={busy || typeBusy || !canApply}>Apply</Button>
      </div>
    </form>
    <Drawer open={advanced} title="More filters" onClose={() => setAdvanced(false)} footer={<><Button variant="ghost" disabled={busy || typeBusy} onClick={() => change({ type_id: '', type_label: '', type_revision_ids: [], account_id: '', account_label: '', amount_min: '', amount_max: '', basis: 'BASE', currency: '', conditions: [] })}>Reset advanced</Button><Button disabled={busy || typeBusy || !canApply} onClick={() => { setAdvanced(false); apply(); }}>Apply filters</Button></>}>
      <div className="janso-day-book__drawer-fields">
        {canReadVouchers && <SearchSelect label="Configured voucher type" loadOptions={types} scopeKey={company + ':types'} value={value.type_id || null} selected={value.type_id ? { id: value.type_id, label: value.type_label || 'Selected voucher type' } : null} onChange={(id, option) => chooseType(id, option?.label)} placeholder="Search type code, e.g. PUR" hint="Includes every revision of the selected type." disabled={busy || typeBusy} />}
        {value.scope === 'POSTED' && <>
          {canReadAccounts && <SearchSelect label="Ledger account" loadOptions={accounts} scopeKey={company + ':accounts'} value={value.account_id || null} selected={value.account_id ? { id: value.account_id, label: value.account_label || 'Selected ledger' } : null} onChange={(id, option) => change({ account_id: id ?? '', account_label: option?.label ?? '' })} placeholder="All ledger accounts" hint="Matches complete journals containing this account." />}
          <fieldset><legend>Posting value</legend><p className="janso-day-book__muted">Gross journal debit in the selected currency basis.</p><div className="janso-day-book__date-range"><TextField label="Minimum posting value" inputMode="decimal" value={value.amount_min} onChange={event => change({ amount_min: event.target.value })} /><TextField label="Maximum posting value" inputMode="decimal" value={value.amount_max} onChange={event => change({ amount_max: event.target.value })} /></div></fieldset>
        </>}
        <Select label="Currency basis" value={value.basis} options={[{ value: 'BASE', label: value.scope === 'POSTED' ? 'Company currency' : 'All document currencies' }, { value: 'TRANSACTION', label: 'Selected transaction currency' }]} onChange={basis => change({ basis: basis as Filters['basis'], currency: basis === 'TRANSACTION' ? value.currency || config.currency || '' : '' })} />
        {value.basis === 'TRANSACTION' && <TextField label="Currency code" value={value.currency} maxLength={3} placeholder="INR" onChange={event => change({ currency: event.target.value.toUpperCase() })} hint="Three-letter currency code, such as INR or USD." />}
        <fieldset ref={conditionFields}><legend>Additional conditions</legend>
          <Select label="Match conditions" value={value.match} options={[{ value: 'ALL', label: 'All conditions (AND)' }, { value: 'ANY', label: 'Any condition (OR)' }]} onChange={match => change({ match: match as Filters['match'] })} />
          {value.conditions.map((condition, index) => <div className="janso-day-book__condition" key={index}>
            <Select label={'Condition ' + (index + 1) + ' field'} value={condition.field} options={[{ value: 'number', label: 'Voucher number' }, { value: 'narration', label: 'Narration' }, { value: 'kind', label: 'Voucher kind code' }]} onChange={field => change({ conditions: value.conditions.map((item, at) => at === index ? { ...item, field: field as typeof condition.field } : item) })} />
            <Select label={'Condition ' + (index + 1) + ' operator'} value={condition.operator} options={[{ value: 'contains', label: 'Contains' }, { value: 'equals', label: 'Equals' }, { value: 'not_contains', label: 'Does not contain' }]} onChange={operator => change({ conditions: value.conditions.map((item, at) => at === index ? { ...item, operator: operator as typeof condition.operator } : item) })} />
            <TextField label={'Condition ' + (index + 1) + ' value'} value={condition.value} maxLength={120} onChange={event => change({ conditions: value.conditions.map((item, at) => at === index ? { ...item, value: event.target.value } : item) })} />
            <Button variant="ghost" onClick={() => { focusCondition.current = Math.min(index, value.conditions.length - 2); change({ conditions: value.conditions.filter((_, at) => at !== index) }); }}>Remove condition {index + 1}</Button>
          </div>)}
          <Button variant="ghost" disabled={value.conditions.length >= 8} onClick={() => { focusCondition.current = value.conditions.length; change({ conditions: [...value.conditions, { field: 'narration', operator: 'contains', value: '' }] }); }}>+ Add condition</Button>
        </fieldset>
      </div>
    </Drawer>
  </>;
}
