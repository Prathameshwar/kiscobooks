import { describe, expect, it } from 'vitest';
import { bomBody, bomComponentFields, bomFraction, bomNumber, newBomLine, verifyBomLines } from '../app/lib/boms';
import type { MasterRow } from '../app/lib/catalog-masters';
const id = '01900000-0000-7000-8000-000000000001';
const other = '01900000-0000-7000-8000-000000000002';
describe('BOM native authoring data', () => {
  it('keeps exact strings, stable business keys and strips response-only fields', () => {
    const line = { ...newBomLine('components', 1), id: other, item_id: id, quantity: '12.2500', unit_revision_id: other };
    expect(line.line_key).toMatch(/^[0-9a-f-]{14}7[0-9a-f-]{4}[89ab]/);
    const result = bomBody({ specification: 'Mix', change_reason: 'Initial', definition_date: '2090-01-01', components: [line], outputs: [] });
    expect(result.errors).toEqual({});
    expect(result.body.components).toEqual([{ line_key: line.line_key, sequence: 1, item_id: id, unit_revision_id: other, quantity: '12.2500', basis: 'GROSS_INPUT', loss_fraction: '0', timing: 'PER_BASIS', route_step_id: null }]);
  });
  it('rejects floats, imprecise quantities, duplicate outputs and implicit loss', () => {
    expect(bomNumber(1.5)).toBe(false);
    expect(bomNumber('1.00001')).toBe(false);
    expect(bomNumber('1000000000000000')).toBe(false);
    expect(bomFraction('0.12345678', true)).toBe(true);
    expect(bomFraction('0.123456789', true)).toBe(false);
    const input = { ...newBomLine('components', 1), item_id: id, loss_fraction: '0.2' };
    const output = { ...newBomLine('outputs', 1), item_id: id };
    const result = bomBody({ specification: 'Mix', change_reason: 'Initial', definition_date: '2090-01-01', components: [input], outputs: [output] });
    expect(result.errors['components.0.loss_fraction']).toBeDefined();
    expect(result.errors.outputs).toBeDefined();
  });
  it('requires every page, scope, identity, sequence and native field before replacement', () => {
    const child = { ...newBomLine('components', 1), id: other, draft_id: id, item_id: other } as MasterRow;
    const page = { items: [child], page: { limit: 200, has_more: false, next_cursor: null } };
    expect(verifyBomLines([page], id, 'draft_id', 1, bomComponentFields)[0]!.line_key).toBe(child.line_key);
    expect(() => verifyBomLines([{ ...page, page: { ...page.page, has_more: true, next_cursor: 'next' } }], id, 'draft_id', 1, bomComponentFields)).toThrow();
    expect(() => verifyBomLines([page], other, 'draft_id', 1, bomComponentFields)).toThrow();
    expect(() => verifyBomLines([page], id, 'draft_id', 2, bomComponentFields)).toThrow();
    expect(() => verifyBomLines([{ ...page, items: [{ ...child, sequence: 2 }] }], id, 'draft_id', 1, bomComponentFields)).toThrow();
    const missing = { ...child }; delete missing.quantity;
    expect(() => verifyBomLines([{ ...page, items: [missing] }], id, 'draft_id', 1, bomComponentFields)).toThrow();
  });
});
