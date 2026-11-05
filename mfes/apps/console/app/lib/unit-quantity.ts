/** UI grid validation/defaults only. Catalog remains the quantity authority. */
const scale = 10000n;
const maximumTicks = 10n ** 19n - 1n;
export function quantityTicks(value: unknown): bigint | null {
  if (typeof value !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(value))
    return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole!) * scale + BigInt(fraction.padEnd(4, '0'));
}
function gcd(a: bigint, b: bigint): bigint {
  while (b) {
    const remainder = a % b;
    a = b;
    b = remainder;
  }
  return a;
}
function lcm(a: bigint, b: bigint) {
  return (a / gcd(a, b)) * b;
}
export function unitGrid(precision: unknown, increment: unknown) {
  const step = quantityTicks(increment);
  if (
    typeof precision !== 'number' ||
    !Number.isInteger(precision) ||
    precision < 0 ||
    precision > 4 ||
    step === null ||
    step <= 0n ||
    step % 10n ** BigInt(4 - precision) !== 0n
  )
    return null;
  return { precision, step };
}
export function gridText(step: bigint): string {
  const fraction = (step % scale)
    .toString()
    .padStart(4, '0')
    .replace(/0+$/, '');
  return (step / scale).toString() + (fraction ? '.' + fraction : '');
}
/** Smallest allowed entered step whose exact ratio falls on the base grid. */
export function convertedGridStep(
  enteredStep: bigint,
  baseStep: bigint,
  numerator: bigint,
  denominator: bigint,
) {
  if (
    enteredStep <= 0n ||
    baseStep <= 0n ||
    numerator <= 0n ||
    denominator <= 0n
  )
    return null;
  const required =
    (denominator * baseStep) / gcd(numerator, denominator * baseStep);
  const result = lcm(enteredStep, required);
  return result <= maximumTicks ? result : null;
}
