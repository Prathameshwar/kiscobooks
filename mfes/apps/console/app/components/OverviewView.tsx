'use client';
import { useMemo } from 'react';
import { Badge, Disclosure, IconButton, InfoIcon, PageHeader, RefreshIcon, ReviewList, Select, Toolbar } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import { useOverviewFormat } from '../lib/overview-format';
import { bucketSeries, overviewLede, PERIOD_KEYS, PERIOD_LABELS, periodRange, type Anchor, type PeriodKey } from '../lib/overview-periods';
import { OverviewActivity, type OverviewLinks } from './OverviewActivity';
import { OverviewKpis } from './OverviewKpis';
import { OverviewAgeing } from './OverviewAgeing';
import { OverviewExpenses } from './OverviewExpenses';
import { OverviewParties } from './OverviewParties';

export type OverviewViewProps = {
  data: Overview;
  /** Presets are only offered once the company's own "today" is known. */
  anchor: Anchor | null;
  period: PeriodKey;
  onPeriod: (period: PeriodKey) => void;
  refreshing: boolean;
  onRefresh: () => void;
  companyName?: string;
  yearLabel?: string;
  company: string;
  canReadCustomers: boolean;
  links: OverviewLinks;
};

/**
 * The overview, given its data. Nothing here fetches: the container resolves one verified
 * snapshot and this lays it out, which is also what lets tests and design review render it from a
 * fixture without any sample data ever living in the application.
 */
export function OverviewView({ data, anchor, period, onPeriod, refreshing, onRefresh, companyName, yearLabel, company, canReadCustomers, links }: OverviewViewProps) {
  const fmt = useOverviewFormat(data.currency);
  const { grain, buckets } = useMemo(() => bucketSeries(data.series), [data.series]);
  const options = PERIOD_KEYS.map(key => {
    const range = anchor ? periodRange(key, anchor) : null;
    return { value: key, label: PERIOD_LABELS[key] + (range?.clamped ? ` · from ${fmt.date(range.from)}` : '') };
  });
  return <div className="janso-page janso-overview" aria-busy={refreshing}>
    <PageHeader title="Business overview" lede={overviewLede(companyName, yearLabel)} />
    <Toolbar
      left={<>
        <Select inline label="Period" value={period} options={options} disabled={!anchor} onChange={value => onPeriod(PERIOD_KEYS.find(key => key === value) ?? 'ytd')} />
        {data.earlier_history_unavailable && <Badge tone="info"><InfoIcon size={14} /> History from {fmt.date(data.coverage_start)}</Badge>}
      </>}
      right={<>
        <Badge variant="mono">{data.currency}</Badge>
        <span className="janso-meta janso-overview__fresh">{refreshing ? 'Updating…' : `As of ${fmt.dateTime(data.source_created_at)}`}</span>
        <span className="janso-visually-hidden" role="status">{refreshing ? 'Updating the overview' : ''}</span>
        {/* aria-disabled, not disabled: a disabled button would drop keyboard focus out from under the person who just pressed it. */}
        <IconButton label="Refresh overview" icon={<RefreshIcon />} variant="outline" aria-disabled={refreshing || undefined} onClick={refreshing ? undefined : onRefresh} />
      </>}
    />
    <Disclosure summary="About these figures">
      <div className="janso-flow janso-overview__about">
        <ReviewList items={[
          { label: 'Balances', value: `${fmt.date(data.date_to)} · includes opening balances.` },
          { label: 'Income and expenses', value: `${fmt.range(data.date_from, data.date_to)}. Excludes opening balances and imported YTD summaries.` },
          { label: 'Receivables and payables', value: 'After credits and advances.' },
        ]} />
        <p className="janso-meta">New postings appear after a source refresh. <a className="janso-link" href="/reports/workspace">Report sources</a></p>
      </div>
    </Disclosure>
    <div className="janso-flow janso-overview__body">
      <h2 className="janso-visually-hidden">Key figures</h2>
      <OverviewKpis data={data} fmt={fmt} grain={grain} buckets={buckets} />
      <h2 className="janso-visually-hidden">Activity and open bills</h2>
      <div className="janso-grid janso-grid--split">
        <OverviewActivity data={data} fmt={fmt} grain={grain} buckets={buckets} links={links} />
        <OverviewAgeing data={data} fmt={fmt} />
      </div>
      <h2 className="janso-visually-hidden">Customers, suppliers and expenses</h2>
      <div className="janso-grid janso-grid--even">
        <OverviewParties data={data} fmt={fmt} company={company} canReadParties={canReadCustomers} />
        <OverviewExpenses data={data} fmt={fmt} />
      </div>
    </div>
  </div>;
}
