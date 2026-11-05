'use client';
import { PaymentsIcon, ReceiptIcon, Sparkline, StatRow, StatTile, TrendUpIcon, WalletIcon, WarnTriangleIcon, type StatTone } from '@janso/ui';
import type { Overview } from '../lib/company-overview';
import type { OverviewFormat } from '../lib/overview-format';
import { cumulativeNet, GRAIN_NOUN, signOf, sumMoney, type Bucket, type Grain } from '../lib/overview-periods';
import { isPositive } from '../lib/overview-shares';

/**
 * The tile's second line: who the money is with, and — when something is late — how much. When
 * advances outweigh the bills the net is negative, and "owed by customers" would be false.
 */
function owedBy(who: string, advances: string, net: string, overdue: string, fmt: OverviewFormat) {
  if (signOf(net) < 0) return advances;
  return isPositive(overdue)
    ? <>{who} · <span className="janso-overview__overdue"><WarnTriangleIcon size={13} /> {fmt.compact(overdue)} overdue bills</span></>
    : who;
}

/**
 * The four figures the page exists to answer: how much cash, who owes us, whom do we owe, are we
 * making money. Exactly one tile (cash) is emphasised. Every tone is paired with a glyph or a
 * word, and a figure that could not be computed is an em-dash, never a zero.
 */
export function OverviewKpis({ data, fmt, grain, buckets }: { data: Overview; fmt: OverviewFormat; grain: Grain; buckets: readonly Bucket[] }) {
  const { totals } = data;
  const cashAndBank = sumMoney(totals.cash, totals.bank);
  const net = signOf(totals.net_income);
  const active = signOf(totals.income) !== 0 || signOf(totals.expenses) !== 0;
  const tone: StatTone = net > 0 ? 'success' : net < 0 ? 'danger' : 'default';
  const verdict = net > 0 ? 'Surplus' : net < 0 ? 'Deficit' : active ? 'Break-even' : null;
  const period = fmt.range(data.date_from, data.date_to);
  return <StatRow columns={4}>
    <StatTile emphasis tone="brand" icon={<WalletIcon />} label="Cash and bank" value={cashAndBank && fmt.money(cashAndBank)}
      footnote={`Cash ${fmt.compact(totals.cash)} · Bank ${fmt.compact(totals.bank)}`}
      trend={<Sparkline values={data.position.map(point => point.cash_and_bank)} label={`Cash and bank balance by day, ${period}`} />} />
    <StatTile icon={<ReceiptIcon />} label="Receivables" value={fmt.money(totals.net_receivable)} footnote={owedBy('Owed by customers', 'Customer advances exceed bills', totals.net_receivable, data.receivables.overdue, fmt)} />
    <StatTile icon={<PaymentsIcon />} label="Payables" value={fmt.money(totals.net_payable)} footnote={owedBy('Owed to suppliers', 'Supplier advances exceed bills', totals.net_payable, data.payables.overdue, fmt)} />
    <StatTile tone={tone} icon={net < 0 ? <WarnTriangleIcon /> : <TrendUpIcon />} label="Net result" value={fmt.money(totals.net_income)}
      footnote={verdict ? `${verdict} · income less expenses` : 'No activity posted in this period'}
      trend={active ? <Sparkline values={cumulativeNet(buckets)} label={`Cumulative net result by ${GRAIN_NOUN[grain]}, ${period}`} /> : undefined} />
  </StatRow>;
}
