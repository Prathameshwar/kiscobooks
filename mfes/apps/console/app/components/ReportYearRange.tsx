'use client';

import { useEffect, useState } from 'react';
import { Notice, Select, useFormatters } from '@janso/ui';
import type { FiscalYearChoice } from '../lib/company-context';

type Mode = 'selected' | 'previous' | 'custom';
type Dates = { owner: string; mode: Mode; from: string; to: string };
function validDate(value: unknown): value is string {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
export function useReportYearDates(company: string, year?: FiscalYearChoice | null, years: readonly FiscalYearChoice[] = []) {
  const previous = [...years].filter(item => year && item.endDate < year.startDate)
    .sort((a, b) => b.endDate.localeCompare(a.endDate))[0];
  const defaults: Dates = { owner: company, mode: year ? 'selected' : 'custom', from: year?.startDate ?? '', to: year?.endDate ?? '' };
  const [state, setState] = useState<Dates>(defaults);
  const storageKey = 'janso:report-dates:' + company;
  useEffect(() => {
    let restored: Dates | null = null;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null');
      if (saved?.mode === 'custom' && validDate(saved.from) && validDate(saved.to) && saved.from <= saved.to)
        restored = { owner: company, mode: 'custom', from: saved.from, to: saved.to };
    } catch { /* Date preferences are optional when browser storage is unavailable. */ }
    setState(restored ?? { owner: company, mode: year ? 'selected' : 'custom', from: year?.startDate ?? '', to: year?.endDate ?? '' });
  }, [company, storageKey]);
  useEffect(() => {
    setState(current => {
      if (current.owner !== company || current.mode === 'custom') return current;
      const target = current.mode === 'previous' ? previous : year;
      return target ? { ...current, from: target.startDate, to: target.endDate }
        : { ...current, mode: 'custom' };
    });
  }, [company, year?.id, year?.startDate, year?.endDate, previous?.id, previous?.startDate, previous?.endDate]);
  const dates = state.owner === company ? state : defaults;
  function remember(next: Dates) {
    try {
      if (next.mode === 'custom' && validDate(next.from) && validDate(next.to) && next.from <= next.to)
        sessionStorage.setItem(storageKey, JSON.stringify({ mode: next.mode, from: next.from, to: next.to }));
      else if (next.mode !== 'custom') sessionStorage.removeItem(storageKey);
    } catch { /* Reports remain usable without persisted preferences. */ }
  }
  function choose(mode: Mode) {
    const target = mode === 'previous' ? previous : year;
    const next: Dates = mode === 'custom' ? { ...dates, mode } : target ? { ...dates, mode, from: target.startDate, to: target.endDate } : { ...dates, mode: 'custom' };
    remember(next); setState(next);
  }
  function custom(field: 'from' | 'to', value: string) {
    setState(current => { const next: Dates = { ...current, owner: company, mode: 'custom', [field]: value }; remember(next); return next; });
  }
  function restore(from: string, to: string) {
    setState({ owner: company, mode: 'custom', from, to });
  }
  return { ...dates, year, previous, choose, custom, restore };
}
export function ReportYearRange({ range, disabled = false }: { range: ReturnType<typeof useReportYearDates>; disabled?: boolean }) {
  const format = useFormatters();
  const target = range.mode === 'previous' ? range.previous : range.year;
  return <div className="janso-flow">
    <Select label="Report period" value={range.mode} disabled={disabled} options={[
      ...(range.year ? [{ value: 'selected', label: 'Selected financial year' }] : []),
      ...(range.previous ? [{ value: 'previous', label: 'Previous financial year' }] : []),
      { value: 'custom', label: 'Custom dates' },
    ]} onChange={value => range.choose(value as Mode)} />
    {range.mode === 'custom' ? <Notice>Custom dates are in use. Switching the financial year preserves this company’s custom date range. Choose Selected financial year to follow the year switcher.</Notice>
      : target && <p>{target.code}: {format.date(target.startDate)} to {format.date(target.endDate)}</p>}
  </div>;
}
