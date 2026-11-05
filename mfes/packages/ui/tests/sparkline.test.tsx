/**
 * Sparkline (design-system §5.3).
 *
 * The load-bearing properties: it is an image with a sentence for a name (it has no axes, so the
 * name is its whole accessible content), it never renders a value, and it draws nothing rather
 * than a misleading shape when there is no trend to show.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Sparkline } from '../src/components/Sparkline';
import { StatTile } from '../src/components/StatTile';

const CHART_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'chart.css'), 'utf8');

function pathOf(container: HTMLElement, cls: string): string {
  return container.querySelector(`.${cls}`)?.getAttribute('d') ?? '';
}

describe('Sparkline', () => {
  it('is a labelled image, named by the caller’s sentence', () => {
    render(<Sparkline values={['10', '20', '15']} label="Invoiced per week, 1 Jul to 9 Sep" />);
    const img = screen.getByRole('img', { name: 'Invoiced per week, 1 Jul to 9 Sep' });
    expect(img).toHaveClass('janso-sparkline');
    expect(img.querySelector('title')).toHaveTextContent('Invoiced per week, 1 Jul to 9 Sep');
  });

  it('draws one move and a line segment per remaining point', () => {
    const { container } = render(<Sparkline values={['1', '3', '2', '5']} label="t" />);
    const d = pathOf(container, 'janso-sparkline__line');
    expect(d.match(/M /g)).toHaveLength(1);
    expect(d.match(/L /g)).toHaveLength(3);
  });

  it('puts the highest value at the top and the lowest at the bottom of the box', () => {
    const { container } = render(<Sparkline values={['5', '1', '9']} label="t" />);
    const ys = [...pathOf(container, 'janso-sparkline__line').matchAll(/[ML] [\d.]+ ([\d.]+)/g)].map(
      (m) => Number(m[1]),
    );
    expect(ys[2]).toBeLessThan(ys[0] as number); // 9 above 5
    expect(ys[1]).toBeGreaterThan(ys[0] as number); // 1 below 5
  });

  it('closes the area under the line down to the baseline', () => {
    const { container } = render(<Sparkline values={['1', '2']} label="t" />);
    expect(pathOf(container, 'janso-sparkline__area')).toMatch(/ Z$/);
  });

  it('draws a level line through the middle for a flat series, not NaN', () => {
    const { container } = render(<Sparkline values={['4', '4', '4']} label="t" />);
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
    const ys = [...pathOf(container, 'janso-sparkline__line').matchAll(/[ML] [\d.]+ ([\d.]+)/g)].map(
      (m) => m[1],
    );
    expect(new Set(ys)).toEqual(new Set(['16']));
  });

  it('treats an unparseable entry as zero rather than breaking the path', () => {
    const { container } = render(<Sparkline values={['10', 'n/a', '20']} label="t" />);
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });

  it.each([[[]], [['42']]])('renders nothing for %j — a single point is not a trend', (values) => {
    const { container } = render(<Sparkline values={values} label="t" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('never renders a value as text', () => {
    const { container } = render(<Sparkline values={['1234.5600', '99.0000']} label="trend" />);
    expect(container.textContent).toBe('trend');
  });

  it('takes its colour from the series slot, defaulting to the first', () => {
    const { container, rerender } = render(<Sparkline values={['1', '2']} label="t" />);
    expect(container.querySelector('svg')).toHaveAttribute('data-series', '1');
    rerender(<Sparkline values={['1', '2']} label="t" series={3} />);
    expect(container.querySelector('svg')).toHaveAttribute('data-series', '3');
    expect(CHART_CSS).toMatch(/\.janso-sparkline\[data-series='3'\] \{ color: var\(--janso-chart-3\); \}/);
  });

  it('keeps the stroke weight when the box stretches it', () => {
    expect(CHART_CSS).toMatch(/\.janso-sparkline__line\s*\{[^}]*vector-effect: non-scaling-stroke/);
  });
});

describe('StatTile trend slot', () => {
  it('sets the trend beside the footnote in one row', () => {
    const { container } = render(
      <StatTile
        label="Invoiced"
        value="₹1,00,000.00"
        footnote="12 posted invoices"
        trend={<Sparkline values={['1', '2']} label="Invoiced per week" />}
      />,
    );
    const foot = container.querySelector('.janso-stat__foot');
    expect(foot?.querySelector('.janso-stat__footnote')).toHaveTextContent('12 posted invoices');
    expect(foot?.querySelector('.janso-stat__trend')).toContainElement(
      screen.getByRole('img', { name: 'Invoiced per week' }),
    );
  });

  it('renders the trend without a footnote, and neither row when both are absent', () => {
    const { container, rerender } = render(
      <StatTile label="Invoiced" value="1" trend={<Sparkline values={['1', '2']} label="t" />} />,
    );
    expect(container.querySelector('.janso-stat__footnote')).toBeNull();
    expect(container.querySelector('.janso-stat__trend')).not.toBeNull();
    rerender(<StatTile label="Invoiced" value="1" />);
    expect(container.querySelector('.janso-stat__foot')).toBeNull();
  });
});
