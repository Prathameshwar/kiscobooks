import { describe, expect, it } from 'vitest';
import { normalizedSerialIdentifier, validateSerialIdentifiers, type SerialRequirement } from '../app/lib/serial-identity';

const rule = (type: 'SERIAL' | 'IMEI' = 'SERIAL', namespace: 'COMPANY' | 'MANUFACTURER_SKU' = 'COMPANY'): SerialRequirement => ({ identifier_type: type, namespace_rule: namespace, min_count: 1, max_count: 2, requires_slot: true });
describe('native serial identity contract', () => {
  it.each([['SS', 'ß'], [' ABC ', 'abc'], ['ΟΣ', 'οσ'], ['Ꭰ', 'ꭰ'], ['ＳＥＲＩＡＬ', 'serial']])('normalizes %s and %s to one identity', (left, right) => {
    expect(normalizedSerialIdentifier(left)).toBe(normalizedSerialIdentifier(right));
  });
  it('counts Unicode characters and rejects normalization overflow and controls', () => {
    expect(normalizedSerialIdentifier('😀'.repeat(120))).toHaveLength(240);
    expect(() => normalizedSerialIdentifier('ﬃ'.repeat(41))).toThrow(/normalization/);
    expect(() => normalizedSerialIdentifier('A\u200bB')).toThrow(/printable/);
    expect(() => normalizedSerialIdentifier('\u{1CCD6}')).toThrow(/printable/);
  });
  it('accepts a minimum count in the second slot', () => {
    expect(validateSerialIdentifiers([{ identifier_type: 'SERIAL', slot: 2, value: 'S2' }], [rule()]).errors).toEqual({});
  });
  it('rejects invalid IMEI and repeated slots with exact fields', () => {
    expect(Object.keys(validateSerialIdentifiers([{ identifier_type: 'IMEI', value: '123456789012345' }], [rule('IMEI')], { prefix: 'serials.0.identifiers' }).errors)).toContain('serials.0.identifiers.0.value');
    const errors = validateSerialIdentifiers([{ identifier_type: 'SERIAL', slot: 1, value: 'A' }, { identifier_type: 'SERIAL', slot: 1, value: 'B' }], [rule()]).errors;
    expect(Object.keys(errors)).toContain('identifiers.1.value');
  });
  it('checks COMPANY identities across SKUs and preserves SKU namespaces', () => {
    const values = [{ identifier_type: 'SERIAL' as const, value: 'SAME' }];
    const seen = new Set<string>();
    validateSerialIdentifiers(values, [rule()], { seen, skuKey: 'A' });
    expect(Object.keys(validateSerialIdentifiers(values, [rule()], { seen, skuKey: 'B' }).errors)).not.toHaveLength(0);
    const skuSeen = new Set<string>();
    validateSerialIdentifiers(values, [rule('SERIAL', 'MANUFACTURER_SKU')], { seen: skuSeen, skuKey: 'A' });
    expect(validateSerialIdentifiers(values, [rule('SERIAL', 'MANUFACTURER_SKU')], { seen: skuSeen, skuKey: 'B' }).errors).toEqual({});
  });
  it('omits empty optional slots but requires one physical identifier overall', () => {
    const optional = { ...rule(), min_count: 0 };
    expect(validateSerialIdentifiers([{ identifier_type: 'SERIAL', value: '' }], [optional], { omitEmpty: true }).errors).toHaveProperty('identifiers');
    expect(validateSerialIdentifiers([{ identifier_type: 'SERIAL', slot: 1, value: '' }, { identifier_type: 'SERIAL', slot: 2, value: 'S2' }], [rule()], { omitEmpty: true }).identifiers).toHaveLength(1);
  });
});
