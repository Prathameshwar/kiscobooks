'use client';
import { useMemo } from 'react';
import { useMediaQuery } from '../lib/use-media-query';
import { ArrowRightIcon, Card, CardBody, CardHeader, EmptyState, GroupedBarChart, InfoIcon } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import type { OverviewFormat } from '../lib/overview-format';
import { GRAIN_NOUN, signOf, type Bucket, type Grain } from '../lib/overview-periods';

export type OverviewLinks = { opening?: string; voucher?: string };

export function hasPostedActivity(series: Overview['series']): boolean {
  return series.some(row => signOf(row.income) !== 0 || signOf(row.expenses) !== 0);
}

/**
 * Income beside expenses, bucketed by posting date. With nothing posted the chart would be an
 * axis of zeros, so the card says so and offers the next step the reader is permitted to take.
 */
export function OverviewActivity({ data, fmt, grain, buckets, links }: { data: Overview; fmt: OverviewFormat; grain: Grain; buckets: readonly Bucket[]; links: OverviewLinks }) {
  const noun = GRAIN_NOUN[grain];
  const range = fmt.range(data.date_from, data.date_to);
  // A phone gets a narrower drawing so tick labels stay legible instead of shrinking with the card.
  const narrow = useMediaQuery('(max-width: 680px)');
  const unit = grain === 'month' ? 'month' : 'day';
  const categories = useMemo(() => buckets.map(bucket => fmt.axisDate(bucket.from, unit)), [buckets, fmt, unit]);
  const series = useMemo(() => [
    { key: 'income', label: 'Income', slot: 1 as const, values: buckets.map(bucket => bucket.income), total: fmt.compact(data.totals.income) },
    { key: 'expenses', label: 'Expenses', slot: 2 as const, values: buckets.map(bucket => bucket.expenses), total: fmt.compact(data.totals.expenses) },
  ], [buckets, fmt, data.totals.income, data.totals.expenses]);
  const active = hasPostedActivity(data.series);
  return <Card>
    <CardHeader title="Income and expenses" subtitle={`Posted ledger activity by ${noun}, ${range}${grain === 'day' ? '' : `. Each ${noun} is labelled by its first day.`}`}
      action={<a className="janso-link janso-overview__more" href="/reports/workspace?report=PROFIT_LOSS">Profit and loss <ArrowRightIcon size={16} /></a>} />
    <CardBody>
      {active
        ? <GroupedBarChart categories={categories} series={series} ariaLabel={`Income and expenses per ${noun}, ${range}`} formatValue={fmt.money} formatScale={fmt.compact} height={narrow ? 240 : 320} width={narrow ? 380 : 720} />
        : <EmptyState icon={<InfoIcon size={20} />} title="Nothing posted in this period"
          body="Income and expenses appear here once vouchers or opening balances are posted to the books."
          action={(links.opening || links.voucher) && <div className="janso-form-actions">
            {links.voucher && <a className="janso-btn janso-btn--primary" href={links.voucher}>Enter a voucher</a>}
            {links.opening && <a className="janso-btn janso-btn--ghost" href={links.opening}>Review opening balances</a>}
          </div>} />}
    </CardBody>
  </Card>;
}
