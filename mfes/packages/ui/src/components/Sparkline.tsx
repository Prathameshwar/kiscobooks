import type { ReactElement } from 'react';
import { coord as u, toMagnitude } from '../lib/chart-geometry';

/*
 * The viewBox is fixed and the SVG scales to its box, so the geometry below never depends on a
 * layout read — the same reason `BarChart` renders identically under test.
 */
const VIEW_W = 120;
const VIEW_H = 32;
const PAD = 2; // keeps the stroke's own width inside the box at the extremes

export type SparklineProps = {
  /** The series, oldest first, as the decimal strings the API returns. */
  values: readonly string[];
  /**
   * What the line shows, in words — "Invoiced per week, 1 Jul to 9 Sep". A sparkline has no axes
   * and no labels, so this is its whole accessible content; the figures themselves belong in the
   * tile's value or in a table elsewhere on the page.
   */
  label: string;
  /** Series slot from the chart palette, assigned by index like `BarChart`'s. */
  series?: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
};

/**
 * A word-sized trend line: the shape of a series, without a scale.
 *
 * It answers "which way, and how steadily" beside a figure that already answers "how much". It
 * draws nothing for fewer than two points — a single dot is not a trend, and an empty box beside a
 * figure would read as a chart that failed to load.
 */
export function Sparkline({ values, label, series = 1 }: SparklineProps): ReactElement | null {
  if (values.length < 2) return null;

  const magnitudes = values.map(toMagnitude);
  const low = Math.min(...magnitudes);
  const high = Math.max(...magnitudes);
  const span = high - low;
  const step = (VIEW_W - PAD * 2) / (magnitudes.length - 1);

  /* A flat series draws a level line through the middle rather than dividing by zero. */
  const yOf = (value: number): number =>
    span > 0 ? VIEW_H - PAD - ((value - low) / span) * (VIEW_H - PAD * 2) : VIEW_H / 2;

  const points = magnitudes.map((value, i) => [PAD + step * i, yOf(value)] as const);
  const line = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'} ${u(x)} ${u(y)}`).join(' ');
  const first = points[0];
  const last = points[points.length - 1];
  const area =
    first && last ? `${line} L ${u(last[0])} ${u(VIEW_H)} L ${u(first[0])} ${u(VIEW_H)} Z` : '';

  return (
    <svg
      className="janso-sparkline"
      data-series={series}
      role="img"
      aria-label={label}
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      focusable="false"
    >
      <title>{label}</title>
      <path className="janso-sparkline__area" d={area} />
      <path className="janso-sparkline__line" d={line} />
    </svg>
  );
}
