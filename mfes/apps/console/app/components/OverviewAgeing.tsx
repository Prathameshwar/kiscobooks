'use client';
import { useState } from 'react';
import { ArrowRightIcon, Card, CardBody, CardFooter, CardHeader, ListRow, SegmentedControl, type Tone } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import type { OverviewFormat } from '../lib/overview-format';
import { isPositive, shareOf } from '../lib/overview-shares';

export type OpenItemsRole = 'receivables' | 'payables';
const ROLES = [{ value: 'receivables' as const, label: 'Receivables' }, { value: 'payables' as const, label: 'Payables' }];

const BUCKETS = [
  { key: 'current', label: 'Not yet due', tone: 'success' },
  { key: 'days_1_30', label: '1–30 days overdue', tone: 'warn' },
  { key: 'days_31_60', label: '31–60 days overdue', tone: 'warn' },
  { key: 'days_61_90', label: '61–90 days overdue', tone: 'danger' },
  { key: 'days_over_90', label: 'Over 90 days overdue', tone: 'danger' },
  { key: 'unknown', label: 'No due date', tone: 'neutral' },
] as const satisfies readonly { key: keyof Overview['receivables']['buckets']; label: string; tone: Tone }[];

/**
 * How old the open bills are, as at the end of the period. Rows are labelled with their own
 * meaning ("31–60 days overdue"), so the tone is a reinforcement and never the only signal.
 * Advances and credits are shown apart so the rows reconcile to the figure on the tile.
 */
export function OverviewAgeing({ data, fmt }: { data: Overview; fmt: OverviewFormat }) {
  const [role, setRole] = useState<OpenItemsRole>('receivables');
  const items = data[role];
  const bills = role === 'receivables' ? 'open customer bills' : 'open supplier bills';
  return <Card>
    <CardHeader title="Bills by age" subtitle={`As at ${fmt.date(data.date_to)}`}
      action={<SegmentedControl label="Bills to show" value={role} options={ROLES} onChange={setRole} />} />
    <CardBody>
      {isPositive(items.gross)
        ? <div className="janso-flow">
          <p className="janso-overview__summary">
            <strong className="janso-figure">{fmt.money(items.overdue)}</strong> overdue of <span className="janso-figure">{fmt.money(items.gross)}</span> in {bills}
          </p>
          <div className="janso-overview__rows">
            {BUCKETS.filter(bucket => bucket.key !== 'unknown' || isPositive(items.buckets.unknown)).map(bucket =>
              <ListRow key={bucket.key} primary={bucket.label} figure={fmt.money(items.buckets[bucket.key])} share={shareOf(items.buckets[bucket.key], items.gross)} tone={bucket.tone} />)}
          </div>
          {isPositive(items.advances) && <p className="janso-meta">
            Less advances and credits {fmt.money(items.advances)}, leaving <span className="janso-figure">{fmt.money(items.net)}</span> net.
          </p>}
        </div>
        : <p className="janso-overview__quiet">{isPositive(items.advances)
          ? `No open bills. Advances and credits of ${fmt.money(items.advances)} are unapplied.`
          : role === 'receivables' ? 'Nothing is owed to you right now.' : 'You do not owe any supplier right now.'}</p>}
    </CardBody>
    <CardFooter>
      <span>Open bills at the period end</span>
      <a className="janso-link janso-overview__more" href="/reports/workspace?report=OUTSTANDING_BILLS">Outstanding bills <ArrowRightIcon size={16} /></a>
    </CardFooter>
  </Card>;
}
