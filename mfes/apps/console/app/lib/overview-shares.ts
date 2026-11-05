import * as fx from './fixed-decimal';

/**
 * A part of a whole as a 0–1 fraction, for a meter's width and its percentage label — geometry
 * and a share, never a money figure. The division is exact (scaled integers); only the final
 * fraction becomes a JS number, which is the same one-way boundary the charts keep. An unreadable
 * amount, a non-positive whole, or a negative part has no share, so it draws as empty.
 */
export function shareOf(part: string, whole: string): number {
  const numerator = fx.parse(part);
  const denominator = fx.parse(whole);
  if (numerator === null || denominator === null || denominator <= 0n || numerator <= 0n) return 0;
  return Math.min(1, Number(fx.div(numerator, denominator)) / Number(fx.ONE));
}

export const isPositive = (amount: string): boolean => (fx.parse(amount) ?? 0n) > 0n;

/** The sum of the positive amounts among `values`, as a decimal string: the whole a set of shares is a share of. */
export function sumPositive(values: readonly string[]): string {
  return fx.format(values.reduce((sum, value) => { const amount = fx.parse(value) ?? 0n; return amount > 0n ? sum + amount : sum; }, 0n));
}
