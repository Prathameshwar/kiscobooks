/**
 * Geometry helpers shared by the hand-rolled SVG charts (`BarChart`, `GroupedBarChart`, `Sparkline`).
 *
 * `toMagnitude` is the **one** place a decimal string becomes a JS number on the client, and it is
 * geometry only: bar heights and line points are pixel maths. Nothing derived from it is ever
 * rendered as a value — every figure a reader sees comes from the caller's original string.
 * Crossing that line reintroduces exactly the float coercion the string-money rule exists to
 * prevent (CLAUDE.md §4, design-system decision 10). One copy, so a guard added here holds for
 * every chart.
 */
export function toMagnitude(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Round to 2dp so coordinate strings stay short and free of float dust. */
export const coord = (value: number): string => String(Math.round(value * 100) / 100);

export function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

const CAP_RADIUS = 4; // rounded data-end, square at the baseline

/**
 * A bar as a path rather than a rect: a rect's `rx` would round the baseline end too,
 * which reads as a floating mark. Grows either way from the zero line, so a negative
 * value is drawn rather than dropped.
 */
export function barPath(x: number, width: number, base: number, end: number): string {
  const reach = Math.abs(end - base);
  const radius = Math.min(CAP_RADIUS, width / 2, reach);
  const towards = end <= base ? 1 : -1; // 1 = grows up out of the baseline
  const cap = end + towards * radius;
  const right = x + width;
  return [
    `M ${coord(x)} ${coord(base)}`,
    `L ${coord(x)} ${coord(cap)}`,
    `Q ${coord(x)} ${coord(end)} ${coord(x + radius)} ${coord(end)}`,
    `L ${coord(right - radius)} ${coord(end)}`,
    `Q ${coord(right)} ${coord(end)} ${coord(right)} ${coord(cap)}`,
    `L ${coord(right)} ${coord(base)}`,
    'Z',
  ].join(' ');
}
