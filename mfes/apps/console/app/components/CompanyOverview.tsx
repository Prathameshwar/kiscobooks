'use client';
import { useState } from 'react';
import { Notice, PageHeader } from '@janso/ui';
import { overviewLede, parsePeriod, type PeriodKey } from '../lib/overview-periods';
import { useOverview } from '../lib/use-overview';
import type { OverviewLinks } from './OverviewActivity';
import { OverviewFailure, OverviewSkeleton } from './OverviewStates';
import { OverviewView } from './OverviewView';
import { AutomaticReportStatus } from './AutomaticReportStatus';

type CompanyOverviewProps = {
  company: string;
  yearId?: string;
  canReadCustomers: boolean;
  companyName?: string;
  yearLabel?: string;
  /** The `?period=` value from the URL; anything unrecognised is the default period. */
  initialPeriod?: string;
  links?: OverviewLinks;
};

/**
 * The container: reads one verified company overview for the chosen period and hands it to the
 * view. The period lives in the URL (`?period=`) so a link and a reload reproduce the same page.
 */
export function CompanyOverview({ company, yearId, canReadCustomers, companyName, yearLabel, initialPeriod, links = {} }: CompanyOverviewProps) {
  const [period, setPeriod] = useState<PeriodKey>(() => parsePeriod(initialPeriod));
  const read = useOverview(company, yearId, period);
  const choose = (next: PeriodKey) => {
    setPeriod(next);
    // Only `period` changes: any other query parameter and the hash stay as they were.
    const url = new URL(window.location.href);
    if (next === 'ytd') url.searchParams.delete('period'); else url.searchParams.set('period', next);
    window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash);
  };
  if (read.data) {
    return <><AutomaticReportStatus company={company} onGeneration={read.refresh} />{read.failure && <Notice tone="warning">The overview could not be updated. The figures below show the last verified period.</Notice>}<OverviewView data={read.data} anchor={read.anchor} period={period} onPeriod={choose} refreshing={read.refreshing} onRefresh={read.refresh}
      companyName={companyName} yearLabel={yearLabel} company={company} canReadCustomers={canReadCustomers} links={links} /></>;
  }
  return <div className="janso-page janso-overview" aria-busy={read.loading}>
    <PageHeader title="Business overview" lede={overviewLede(companyName, yearLabel)} />
    <AutomaticReportStatus company={company} onGeneration={read.refresh} />
    {read.loading && <OverviewSkeleton />}
    {read.failure && <OverviewFailure failure={read.failure} onRetry={read.refresh} onDefault={period === 'ytd' ? undefined : () => choose('ytd')} />}
  </div>;
}
