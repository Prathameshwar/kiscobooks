/*
 * GroupedBarChart — one cluster of bars per category, one bar per series: "income beside
 * expenses, week by week". Same frame as `BarChart` (fixed 720-unit drawing space, token
 * colours through a series *slot*, a table twin for the data) so the two read as one family.
 *
 * Unlike a single-series chart this one always carries a legend: with two or more series the
 * colour is the only thing saying which bar is which, and colour alone is not an answer
 * (design-system §2.4). The legend is real text beside a swatch; every bar also names its
 * series in its hover readout, and the table twin has a column per series.
 */
import type { ReactElement } from 'react';
import { barPath, clamp, coord as u, toMagnitude } from '../lib/chart-geometry';
import type { BarChartSeries } from './BarChart';

export type GroupedBarSeries = {
  /** Stable identity — the React key, never shown. */
  key: string;
  /** What a reader sees in the legend, the hover readout and the table header. */
  label: string;
  /** A slot in the categorical palette, never a hue picked at the call site. */
  slot: BarChartSeries;
  /** Decimal strings aligned with `categories`; a missing entry is drawn as zero. */
  values: readonly string[];
  /** Already formatted, shown beside the legend label — the series' total for the period. */
  total?: string;
};

export type GroupedBarChartProps = {
  categories: readonly string[];
  series: readonly GroupedBarSeries[];
  /** The chart's accessible name — also the caption of the data table twin. */
  ariaLabel: string;
  /** Applied to every value a reader reads: hover readouts and the table twin. */
  formatValue?: (value: string) => string;
  /** The scale annotation only — usually a compact form of `formatValue`. */
  formatScale?: (value: string) => string;
  height?: number;
  /**
   * The drawing's width in its own units; the SVG still scales to its box. A narrower drawing
   * keeps tick labels and bars legible on a phone, where a 720-unit drawing would shrink its
   * 12px labels to a third. Chosen by the caller (a media query), never measured here.
   */
  width?: number;
};

const DEFAULT_VIEW_W = 720;
const PAD_TOP = 22; // the top gridline; the annotation sits above it
const PAD_BOTTOM = 20; // the x-label band
const PAD_X = 8;
const MIN_HEIGHT = 120;
const BAR_MAX_W = 22;
const BAR_GAP = 2; // surface gap between the bars of one cluster
const CLUSTER_AIR = 0.28; // share of a band left empty between clusters
const GRID_LINES = 4;
const TICK_DROP = 6;

const asGiven = (value: string): string => value;
const ZERO = '0';

export function GroupedBarChart({
  categories,
  series,
  ariaLabel,
  formatValue,
  formatScale,
  height = 260,
  width = DEFAULT_VIEW_W,
}: GroupedBarChartProps): ReactElement {
  const viewWidth = Math.max(280, width);
  const show = formatValue ?? asGiven;
  const scale = formatScale ?? show;

  if (categories.length === 0 || series.length === 0) {
    return (
      <div className="janso-chart">
        <p className="janso-visually-hidden">{ariaLabel}</p>
        <p className="janso-chart__empty">No data to display</p>
      </div>
    );
  }

  const valueAt = (s: GroupedBarSeries, i: number): string => s.values[i] ?? ZERO;

  const boxHeight = Math.max(MIN_HEIGHT, height);
  const plotTop = PAD_TOP;
  const plotBottom = boxHeight - PAD_BOTTOM;
  const plotHeight = plotBottom - plotTop;
  const plotLeft = PAD_X;
  const plotWidth = viewWidth - PAD_X * 2;

  /* The peak is tracked as the caller's own string: the scale annotation is a value a reader
   * reads, so it must never be re-rendered from pixel arithmetic. */
  let scaleTop = 0;
  let scaleBottom = 0;
  let peakText = ZERO;
  for (const s of series) {
    categories.forEach((_, i) => {
      const text = valueAt(s, i);
      const magnitude = toMagnitude(text);
      if (magnitude > scaleTop) {
        scaleTop = magnitude;
        peakText = text;
      }
      scaleBottom = Math.min(scaleBottom, magnitude);
    });
  }
  const span = scaleTop - scaleBottom;
  const yOf = (value: number): number =>
    span > 0
      ? plotBottom - ((clamp(value, scaleBottom, scaleTop) - scaleBottom) / span) * plotHeight
      : plotBottom;
  const zeroY = yOf(0);

  const band = plotWidth / categories.length;
  const count = series.length;
  const clusterRoom = band * (1 - CLUSTER_AIR);
  const barWidth = Math.max(1, Math.min(BAR_MAX_W, (clusterRoom - BAR_GAP * (count - 1)) / count));
  const clusterWidth = barWidth * count + BAR_GAP * (count - 1);

  /* Thin crowded labels from the start so the most recent period always keeps its label; every
   * label stays in the table twin. */
  const longestLabel = categories.reduce((longest, label) => Math.max(longest, label.length), 0);
  const labelSlot = Math.max(28, longestLabel * 6.2);
  const tickStep = Math.max(
    1,
    Math.ceil(categories.length / Math.max(1, Math.floor(plotWidth / labelSlot))),
  );

  const gridYs = Array.from({ length: GRID_LINES + 1 }, (_, i) => plotTop + (plotHeight / GRID_LINES) * i)
    .filter((y) => Math.abs(y - zeroY) > 1);

  return (
    <div className="janso-chart">
      <svg
        className="janso-chart__svg"
        role="img"
        aria-label={ariaLabel}
        width={viewWidth}
        height={boxHeight}
        viewBox={`0 0 ${viewWidth} ${boxHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <title>{ariaLabel}</title>

        {gridYs.map((y) => (
          <line
            key={`grid-${u(y)}`}
            className="janso-chart__gridline"
            x1={u(plotLeft)}
            x2={u(plotLeft + plotWidth)}
            y1={u(y)}
            y2={u(y)}
          />
        ))}
        <line
          className="janso-chart__axis"
          x1={u(plotLeft)}
          x2={u(plotLeft + plotWidth)}
          y1={u(zeroY)}
          y2={u(zeroY)}
        />

        {categories.map((category, i) =>
          series.map((s, j) => (
            <path
              key={`bar-${i}-${s.key}`}
              className="janso-chart__bar"
              data-series={s.slot}
              d={barPath(
                plotLeft + band * i + (band - clusterWidth) / 2 + j * (barWidth + BAR_GAP),
                barWidth,
                zeroY,
                yOf(toMagnitude(valueAt(s, i))),
              )}
            >
              <title>{`${category} · ${s.label}: ${show(valueAt(s, i))}`}</title>
            </path>
          )),
        )}

        <text
          className="janso-chart__annotation janso-figure"
          x={u(plotLeft + plotWidth)}
          y={u(plotTop - 7)}
          textAnchor="end"
        >
          {scale(peakText)}
        </text>

        {categories.map((category, i) =>
          (categories.length - 1 - i) % tickStep === 0 ? (
            <text
              key={`tick-${i}-${category}`}
              className="janso-chart__tick"
              x={u(plotLeft + band * i + band / 2)}
              y={u(boxHeight - TICK_DROP)}
              textAnchor="middle"
            >
              {category}
            </text>
          ) : null,
        )}
      </svg>

      <ul className="janso-chart__legend" aria-label="Legend">
        {series.map((s) => (
          <li key={s.key} className="janso-chart__legend-item">
            <span className="janso-chart__swatch" data-series={s.slot} aria-hidden="true" />
            {s.label}
            {s.total === undefined ? null : <span className="janso-chart__legend-total janso-figure">{s.total}</span>}
          </li>
        ))}
      </ul>

      <table className="janso-visually-hidden">
        <caption>{ariaLabel}</caption>
        <thead>
          <tr>
            <th scope="col">Label</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category, i) => (
            <tr key={`row-${i}-${category}`}>
              <th scope="row">{category}</th>
              {series.map((s) => (
                <td key={s.key} className="janso-figure">
                  {show(valueAt(s, i))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
