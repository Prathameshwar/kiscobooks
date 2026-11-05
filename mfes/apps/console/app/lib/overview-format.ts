'use client';
import { useMemo } from 'react';
import { useDisplayConfig, useFormatters } from '@janso/ui';

export type OverviewFormat = {
  money: (value: string) => string;
  compact: (value: string) => string;
  date: (iso: string) => string;
  axisDate: (iso: string, unit: 'day' | 'month') => string;
  range: (from: string, to: string) => string;
  dateTime: (iso: string) => string;
};

/**
 * The overview's formatters, bound to the company's display config.
 *
 * The figures' currency comes from the verified source, the symbol from the display config. When
 * the two disagree (a config that has not resolved to this company yet) a symbol would mislabel
 * real money, so the figure falls back to the ISO code of the source's own currency.
 */
export function useOverviewFormat(currency: string): OverviewFormat {
  const format = useFormatters();
  const config = useDisplayConfig();
  return useMemo(() => {
    const same = config.currency === currency;
    return {
      money: (value: string) => (same ? format.money(value) : format.money(value, { display: 'none' }) + ' ' + currency),
      compact: format.compact,
      date: format.date,
      axisDate: format.axisDate,
      range: format.range,
      dateTime: format.dateTime,
    };
  }, [config.currency, currency, format]);
}
