import type { components } from '@janso/api-client/catalog';
import { serialCasefold, serialNonprintable } from './serial-casefold';

export type SerialIdentifier = components['schemas']['IdentifierInput'];
export type SerialRequirement = components['schemas']['IdentifierRequirement'];
// Python str.strip() whitespace, including the C0 separators and NEL.
const whitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g;
export const trimSerialIdentifier = (value: string) => value.replace(whitespace, '');
function nativeNonprintable(char: string): boolean {
  const point = char.codePointAt(0)!;
  let low = 0, high = serialNonprintable.length - 1;
  while (low <= high) {
    const middle = (low + high) >>> 1, [start, end] = serialNonprintable[middle]!;
    if (point < start) high = middle - 1;
    else if (point > end) low = middle + 1;
    else return true;
  }
  return false;
}
export function normalizedSerialIdentifier(value: string): string {
  const normalized = trimSerialIdentifier(value.normalize('NFKC'));
  const folded = [...normalized].map(char => serialCasefold[char] ?? char).join('');
  if (!normalized || [...value].length > 120 || [...normalized].length > 120 || [...folded].length > 120 || [...trimSerialIdentifier(value)].some(nativeNonprintable) || [...normalized].some(nativeNonprintable)) {
    throw new Error('Enter a printable identifier up to 120 characters after normalization.');
  }
  return folded;
}
export function validateSerialIdentifiers(values: readonly SerialIdentifier[], requirements: readonly SerialRequirement[], {
  prefix = 'identifiers', seen = new Set<string>(), skuKey = '', omitEmpty = false,
}: { prefix?: string; seen?: Set<string>; skuKey?: string; omitEmpty?: boolean } = {}) {
  const errors: Record<string, string> = {};
  const identifiers: SerialIdentifier[] = [];
  const slots = new Set<string>();
  const local = new Set<string>();
  if (!requirements.length || requirements.length > 2 || new Set(requirements.map(rule => rule.identifier_type)).size !== requirements.length) errors[prefix] = 'A complete identifier profile is required.';
  for (const [index, item] of values.entries()) {
    const path = `${prefix}.${index}.value`;
    if (omitEmpty && !trimSerialIdentifier(item.value)) continue;
    const rule = requirements.find(rule => rule.identifier_type === item.identifier_type);
    const slot = item.slot ?? 1;
    identifiers.push(item);
    if (!rule || !Number.isInteger(slot) || slot < 1 || slot > rule.max_count || (!rule.requires_slot && slot !== 1)) {
      errors[path] = 'Use an identifier type and slot allowed by the profile.';
      continue;
    }
    const slotKey = `${item.identifier_type}:${slot}`;
    if (slots.has(slotKey)) errors[path] = 'This identifier slot is already entered for this unit.';
    slots.add(slotKey);
    try {
      const key = normalizedSerialIdentifier(item.value);
      const localKey = `${item.identifier_type}:${key}`;
      const scopeKey = `${rule.namespace_rule === 'COMPANY' ? 'COMPANY' : 'SKU:' + skuKey}:${localKey}`;
      if (local.has(localKey) || seen.has(scopeKey)) errors[path] = 'This identifier is already entered for another unit.';
      local.add(localKey); seen.add(scopeKey);
      if (item.identifier_type === 'IMEI') {
        const checksum = [...key].reduce((sum, digit, index) => {
          const number = Number(digit) * (index % 2 ? 2 : 1);
          return sum + Math.floor(number / 10) + number % 10;
        }, 0);
        if (!/^\d{15}$/.test(key) || checksum % 10) errors[path] = 'Enter a valid 15-digit IMEI with a correct checksum.';
      }
    } catch (error) { errors[path] = (error as Error).message; }
  }
  if (!identifiers.length) errors[prefix] = 'Enter an identifier for this unit or remove the row.';
  for (const rule of requirements) {
    const count = identifiers.filter(item => item.identifier_type === rule.identifier_type).length;
    if (count < rule.min_count || count > rule.max_count) errors[prefix] = `Enter ${rule.min_count} to ${rule.max_count} ${rule.identifier_type} identifiers for this unit.`;
  }
  return { identifiers, errors };
}
