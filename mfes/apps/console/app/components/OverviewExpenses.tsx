'use client';
import { Card, CardBody, CardHeader, ListRow } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import type { OverviewFormat } from '../lib/overview-format';
import { isPositive, shareOf, sumPositive } from '../lib/overview-shares';
import { signOf } from '../lib/overview-periods';

/**
 * Where the period's expenses went: the five largest expense ledgers and everything else as one
 * line, so the rows add up to the expense figure on the tiles. Posted ledger activity only.
 *
 * "Everything else" is net of any credit-balance ledger (purchase returns, refunds), so it can be
 * negative; it is still shown, because dropping it would leave the rows short of the tile. Shares
 * are shares of the positive rows, which is what the bars can honestly add up to.
 */
export function OverviewExpenses({ data, fmt }: { data: Overview; fmt: OverviewFormat }) {
  const whole = sumPositive([...data.top_expenses.map(ledger => ledger.amount), data.other_expenses]);
  return <Card>
    <CardHeader title="Where money went" subtitle={`Largest expense ledgers, ${fmt.range(data.date_from, data.date_to)}`} />
    <CardBody>
      {data.top_expenses.length > 0
        ? <div className="janso-overview__rows">
          {data.top_expenses.map((ledger, index) => <ListRow key={ledger.account_id} rank={index + 1} primary={ledger.name}
            figure={fmt.money(ledger.amount)} share={shareOf(ledger.amount, whole)} tone="brand" />)}
          {signOf(data.other_expenses) !== 0 && <ListRow primary="All other expenses" figure={fmt.money(data.other_expenses)}
            share={isPositive(data.other_expenses) ? shareOf(data.other_expenses, whole) : undefined} tone="neutral" />}
        </div>
        : <p className="janso-overview__quiet">No expenses were posted in this period.</p>}
    </CardBody>
  </Card>;
}
