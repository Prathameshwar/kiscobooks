/**
 * Exact decimal arithmetic for the provisional invoice preview.
 *
 * Every amount and quantity in the platform is `DECIMAL(19,4)` (CLAUDE.md §4), and the preview
 * has to add, multiply and divide them. A JavaScript `number` cannot do that honestly —
 * `0.1 + 0.2` is `0.30000000000000004`, and a 2.5% tax on a ₹1,23,456.78 line accumulates exactly
 * the kind of error that makes a preview disagree with the accepted invoice by a paisa. So values
 * here are `bigint`s scaled by 10⁴: the storage scale, held as integers, with rounding happening
 * only where the calculation contract says it does and only in the mode it names.
 *
 * This is **the preview's** arithmetic, not the invoice's. The service owns the accepted
 * calculation; this exists so the rail can show a figure while someone types, and it is exact so
 * that when the two differ it is because of a rule, never because of floating point.
 */

/** The storage scale. Never narrowed: MySQL re-scales a smaller scale silently. */
export const SCALE = 4;
const FACTOR = 10n ** BigInt(SCALE);

/** A value at the storage scale: `1.5` is `15000n`. */
export type Fixed = bigint;

export const ZERO: Fixed = 0n;
/** One, at the storage scale — for cross-multiplying a ratio without rounding it. */
export const ONE: Fixed = FACTOR;

/** Canonical decimal text to a scaled integer. Unparseable text is `null`, never zero. */
export function parse(text: string): Fixed | null {
  const trimmed = text.trim();
  const match = /^(-?)(\d+)(?:\.(\d{1,4}))?$/.exec(trimmed);
  if (!match) return null;
  const [, sign, integer, fraction = ''] = match;
  const value = BigInt(integer!) * FACTOR + BigInt(fraction.padEnd(SCALE, '0'));
  return sign === '-' ? -value : value;
}

/** Back to canonical text at the storage scale: `15000n` is `"1.5000"`. */
export function format(value: Fixed, places = SCALE): string {
  const rounded = places < SCALE ? round(value, places) : value;
  const negative = rounded < 0n;
  const magnitude = negative ? -rounded : rounded;
  const integer = magnitude / FACTOR;
  const fraction = (magnitude % FACTOR).toString().padStart(SCALE, '0').slice(0, places);
  return (negative ? '-' : '') + integer.toString() + (places > 0 ? '.' + fraction : '');
}

export function add(...values: Fixed[]): Fixed {
  return values.reduce((sum, value) => sum + value, ZERO);
}

export function sub(a: Fixed, b: Fixed): Fixed {
  return a - b;
}

/**
 * `a × b`, back at the storage scale, rounded half-up at the fifth place.
 *
 * Multiplying two scale-4 values gives scale 8; the product is brought back to 4 here and
 * *only* here, so a chain of multiplications cannot drift by repeated truncation.
 */
export function mul(a: Fixed, b: Fixed): Fixed {
  return divideRounded(a * b, FACTOR);
}

/** `a ÷ b`, half-up at the storage scale. Division by zero is the caller's bug, and loud. */
export function div(a: Fixed, b: Fixed): Fixed {
  if (b === 0n) throw new RangeError('division by zero in an invoice preview');
  return divideRounded(a * FACTOR, b);
}

/** A percentage of a value: `percent(1000, 18)` is 180. */
export function percent(value: Fixed, rate: Fixed): Fixed {
  return divideRounded(value * rate, 100n * FACTOR);
}

/**
 * Round to `places` decimals, half-up away from zero, staying at the storage scale.
 *
 * Half-up is the platform default and what India GST practice expects for component amounts.
 * The company's configured `rounding_mode` governs the *accepted* invoice; the preview states
 * which mode it used rather than pretending to know the company's.
 */
export function round(value: Fixed, places: number): Fixed {
  if (places >= SCALE) return value;
  const step = 10n ** BigInt(SCALE - places);
  return divideRounded(value, step) * step;
}

/** Round to the nearest multiple of `increment` (e.g. 1 rupee), half-up. */
export function roundTo(value: Fixed, increment: Fixed): Fixed {
  if (increment <= 0n) return value;
  return divideRounded(value, increment) * increment;
}

export function compare(a: Fixed, b: Fixed): -1 | 0 | 1 {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function min(a: Fixed, b: Fixed): Fixed {
  return a < b ? a : b;
}

export function isZero(value: Fixed): boolean {
  return value === 0n;
}

/** Integer division rounded half-up away from zero. The single place rounding happens. */
function divideRounded(numerator: bigint, denominator: bigint): bigint {
  const negative = numerator < 0n !== denominator < 0n;
  const n = numerator < 0n ? -numerator : numerator;
  const d = denominator < 0n ? -denominator : denominator;
  const quotient = n / d;
  const remainder = n % d;
  const rounded = remainder * 2n >= d ? quotient + 1n : quotient;
  return negative ? -rounded : rounded;
}

/**
 * Split `total` across `weights` so the parts sum to `total` exactly, at `places` decimals.
 *
 * The **largest-remainder** method, which is the calculation contract's default for
 * apportioning a document discount across eligible lines. Rounding each share independently
 * would leave the parts a paisa away from the whole — and an allocation that does not reconcile
 * to its source is something the contract explicitly rejects. Ties break by position, so the
 * result is stable: the same invoice always allocates the same way.
 */
export function allocate(total: Fixed, weights: readonly Fixed[], places: number): Fixed[] {
  const sum = weights.reduce((acc, weight) => acc + weight, 0n);
  if (sum === 0n || weights.length === 0) return weights.map(() => 0n);
  const unit = 10n ** BigInt(SCALE - Math.min(places, SCALE));
  const units = total / unit; // whole minor units to hand out
  const raw = weights.map((weight) => units * weight);
  const floors = raw.map((value) => value / sum);
  let left = units - floors.reduce((acc, value) => acc + value, 0n);
  const order = raw
    .map((value, index) => ({ index, remainder: value % sum }))
    .sort((a, b) => (a.remainder === b.remainder ? a.index - b.index : a.remainder > b.remainder ? -1 : 1));
  const shares = [...floors];
  for (const { index } of order) {
    if (left <= 0n) break;
    shares[index]! += 1n;
    left -= 1n;
  }
  return shares.map((share) => share * unit);
}
