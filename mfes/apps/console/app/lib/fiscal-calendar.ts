import type { components } from '@janso/api-client/accounting';

type Period = components['schemas']['FiscalPeriodListItem'];
export function completeFiscalCalendar(company: string, year: string, start: string | null | undefined,
  end: string | null | undefined, periods: readonly Period[], hasMore = false): boolean {
  const rows = [...periods].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  return !hasMore && rows.length === 12 && new Set(rows.map(row => row.sequence)).size === 12
    && rows.every((row, index) => row.company_id === company && row.fiscal_year_id === year && row.status
      && row.sequence === index + 1 && row.start_date && row.end_date && row.start_date <= row.end_date
      && (index === 0 ? row.start_date === start
        : new Date(row.start_date + 'T00:00:00Z').getTime() - new Date(rows[index - 1]!.end_date + 'T00:00:00Z').getTime() === 86400000))
    && rows.at(-1)?.end_date === end;
}
