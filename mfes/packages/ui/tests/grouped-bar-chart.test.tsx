/*
 * GroupedBarChart — a hand-rolled SVG, so correctness is structural: cluster geometry, the
 * legend, slot attributes and the accessible table twin. jsdom does no layout.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GroupedBarChart, type GroupedBarSeries } from '../src/components/GroupedBarChart';

const CATEGORIES = ['5 Oct', '12 Oct', '19 Oct'];
const SERIES: GroupedBarSeries[] = [
  { key: 'income', label: 'Income', slot: 1, values: ['1000.0000', '2000.0000', '500.0000'] },
  { key: 'expenses', label: 'Expenses', slot: 2, values: ['400.0000', '1000.0000', '0.0000'] },
];

function bars(container: HTMLElement): SVGPathElement[] {
  return [...container.querySelectorAll<SVGPathElement>('.janso-chart__bar')];
}
const baseY = (bar: Element): number => Number(/^M (-?[\d.]+) (-?[\d.]+)/.exec(bar.getAttribute('d') ?? '')?.[2]);
const endY = (bar: Element): number => Number(/Q (-?[\d.]+) (-?[\d.]+) /.exec(bar.getAttribute('d') ?? '')?.[2]);
const leftX = (bar: Element): number => Number(/^M (-?[\d.]+)/.exec(bar.getAttribute('d') ?? '')?.[1]);
const reach = (bar: Element): number => baseY(bar) - endY(bar);
const everyAttribute = (container: HTMLElement): string[] =>
  [...container.querySelectorAll('*')].flatMap((el) => [...el.attributes].map((a) => a.value));

describe('GroupedBarChart', () => {
  it('draws one bar per series per category, in category-then-series order', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );
    const drawn = bars(container);

    expect(drawn).toHaveLength(6);
    expect(drawn.map((bar) => bar.getAttribute('data-series'))).toEqual(['1', '2', '1', '2', '1', '2']);
  });

  it('sets the two bars of a cluster side by side, income left of expenses', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );
    const [income, expenses, nextIncome] = bars(container);

    expect(leftX(expenses!)).toBeGreaterThan(leftX(income!));
    expect(leftX(nextIncome!)).toBeGreaterThan(leftX(expenses!));
  });

  it('scales every bar against one shared peak', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );
    const [income1, expenses1, income2] = bars(container);

    expect(reach(income2!) / reach(income1!)).toBeCloseTo(2, 5);
    expect(reach(expenses1!) / reach(income1!)).toBeCloseTo(0.4, 5);
    expect(container.querySelector('.janso-chart__annotation')?.textContent).toBe('2000.0000');
  });

  it('always carries a legend with a swatch per series, labelled in text', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );
    const items = [...container.querySelectorAll('.janso-chart__legend-item')];

    expect(items.map((item) => item.textContent)).toEqual(['Income', 'Expenses']);
    expect(container.querySelectorAll('.janso-chart__swatch[aria-hidden="true"]')).toHaveLength(2);
    expect(screen.getByRole('list', { name: 'Legend' })).toBeInTheDocument();
  });

  it('shows a series total beside its legend label when one is given, and nothing otherwise', () => {
    const withTotals: GroupedBarSeries[] = [
      { ...SERIES[0]!, total: '3.5K' },
      SERIES[1]!,
    ];
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={withTotals} ariaLabel="Income and expenses" />,
    );
    const items = [...container.querySelectorAll('.janso-chart__legend-item')];

    expect(items[0]?.querySelector('.janso-chart__legend-total')?.textContent).toBe('3.5K');
    expect(items[1]?.querySelector('.janso-chart__legend-total')).toBeNull();
  });

  it('draws in a narrower coordinate space on request, never below a readable minimum', () => {
    const narrow = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Narrow" width={380} />,
    );
    expect(narrow.container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 380 260');
    narrow.unmount();

    const tiny = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Tiny" width={10} />,
    );
    expect(tiny.container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 280 260');
  });

  it('names every bar and its series in the hover readout, through formatValue', () => {
    const { container } = render(
      <GroupedBarChart
        categories={CATEGORIES}
        series={SERIES}
        ariaLabel="Income and expenses"
        formatValue={(value) => `₹${value}`}
      />,
    );

    expect(bars(container)[1]?.querySelector('title')?.textContent).toBe('5 Oct · Expenses: ₹400.0000');
  });

  it('renders a table twin with a column per series and a row per category', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );
    const table = container.querySelector('table');

    expect(table).toHaveClass('janso-visually-hidden');
    expect(table?.querySelector('caption')?.textContent).toBe('Income and expenses');
    expect([...table!.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual(['Label', 'Income', 'Expenses']);
    expect(table?.querySelectorAll('tbody tr')).toHaveLength(3);
    expect(screen.getByRole('rowheader', { name: '12 Oct' })).toBeInTheDocument();
  });

  it('keeps displayed values as the caller’s strings, never a parsed float', () => {
    const precise: GroupedBarSeries[] = [
      { key: 'a', label: 'Income', slot: 1, values: ['1234567.8912'] },
      { key: 'b', label: 'Expenses', slot: 2, values: ['0.1000'] },
    ];
    const { container } = render(
      <GroupedBarChart
        categories={['Q1']}
        series={precise}
        ariaLabel="Spend"
        formatValue={(value) => `${value} INR`}
      />,
    );

    expect(container.querySelector('tbody td')?.textContent).toBe('1234567.8912 INR');
    expect(container.querySelector('.janso-chart__annotation')?.textContent).toBe('1234567.8912 INR');
    expect(container.textContent).not.toContain('1234568');
  });

  it('uses formatScale for the scale annotation only', () => {
    const { container } = render(
      <GroupedBarChart
        categories={CATEGORIES}
        series={SERIES}
        ariaLabel="Income and expenses"
        formatValue={(value) => `full ${value}`}
        formatScale={() => '2.0K'}
      />,
    );

    expect(container.querySelector('.janso-chart__annotation')?.textContent).toBe('2.0K');
    expect(container.querySelector('tbody td')?.textContent).toBe('full 1000.0000');
  });

  it('names itself by role and <title>', () => {
    const { container } = render(
      <GroupedBarChart categories={CATEGORIES} series={SERIES} ariaLabel="Income and expenses" />,
    );

    expect(screen.getByRole('img', { name: 'Income and expenses' })).toBeInTheDocument();
    expect(container.querySelector('svg > title')?.textContent).toBe('Income and expenses');
  });

  it('draws a short series as zero rather than dropping the bar', () => {
    const short: GroupedBarSeries[] = [{ key: 'a', label: 'Income', slot: 1, values: ['10'] }];
    const { container } = render(
      <GroupedBarChart categories={['a', 'b']} series={short} ariaLabel="Short" />,
    );

    expect(bars(container)).toHaveLength(2);
    expect(reach(bars(container)[1]!)).toBe(0);
    expect(everyAttribute(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
  });

  it('survives an all-zero dataset with no NaN', () => {
    const zeros: GroupedBarSeries[] = [
      { key: 'a', label: 'Income', slot: 1, values: ['0.0000', '0.0000'] },
      { key: 'b', label: 'Expenses', slot: 2, values: ['0.0000', '0.0000'] },
    ];
    const { container } = render(
      <GroupedBarChart categories={['a', 'b']} series={zeros} ariaLabel="Zero" />,
    );

    expect(everyAttribute(container).some((v) => /NaN|Infinity/.test(v))).toBe(false);
    expect(bars(container).every((bar) => reach(bar) === 0)).toBe(true);
  });

  it('draws negatives below a zero baseline that sits inside the plot', () => {
    const mixed: GroupedBarSeries[] = [{ key: 'net', label: 'Net', slot: 1, values: ['100', '-50'] }];
    const { container } = render(
      <GroupedBarChart categories={['a', 'b']} series={mixed} ariaLabel="Net" />,
    );
    const [up, down] = bars(container);

    expect(reach(up!)).toBeGreaterThan(0);
    expect(reach(down!)).toBeLessThan(0);
    // coordinates are rounded to 2dp, so the ratio is exact only to about 3 places
    expect(reach(down!) / reach(up!)).toBeCloseTo(-0.5, 3);
  });

  it('renders an empty state without an SVG when there is nothing to plot', () => {
    const { container } = render(
      <GroupedBarChart categories={[]} series={SERIES} ariaLabel="Income and expenses" />,
    );

    expect(screen.getByText('No data to display')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(screen.getByText('Income and expenses')).toHaveClass('janso-visually-hidden');
  });

  it('thins crowded x labels from the start and keeps the last', () => {
    const days = Array.from({ length: 31 }, (_, i) => `2026-01-${String(i + 1).padStart(2, '0')}`);
    const values = days.map((_, i) => String(i + 1));
    const { container } = render(
      <GroupedBarChart
        categories={days}
        series={[{ key: 'a', label: 'Income', slot: 1, values }]}
        ariaLabel="Daily"
      />,
    );
    const ticks = [...container.querySelectorAll('.janso-chart__tick')].map((tick) => tick.textContent);

    expect(ticks.length).toBeLessThan(days.length);
    expect(ticks.at(-1)).toBe('2026-01-31');
    expect(container.querySelectorAll('tbody tr')).toHaveLength(31);
  });

  it('clips its own hidden table twin, so it cannot widen the page on a phone', () => {
    const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'chart.css'), 'utf8');

    expect(css).toMatch(/\.janso-chart\s*\{[^}]*position:\s*relative[^}]*overflow:\s*hidden/);
  });

  it('keeps every slot and the legend swatch colours in chart.css tokens, not in TSX', () => {
    const css = readFileSync(join(__dirname, '..', 'src', 'styles', 'chart.css'), 'utf8');

    for (const n of [2, 3, 4, 5, 6, 7, 8]) {
      expect(css).toMatch(new RegExp(`\\.janso-chart__bar\\[data-series='${n}'\\][^{]*\\{[^}]*var\\(--janso-chart-${n}\\)`));
      expect(css).toMatch(new RegExp(`\\.janso-chart__swatch\\[data-series='${n}'\\][^{]*\\{[^}]*var\\(--janso-chart-${n}\\)`));
    }
  });
});
