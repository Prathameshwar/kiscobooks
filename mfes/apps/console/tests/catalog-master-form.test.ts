import { describe, expect, it } from 'vitest';
import { masterBody, masterConfig, type MasterField } from '../app/lib/catalog-masters';
const fields = (keys: string[]): MasterField[] => keys.map((key, order) => ({ key, order, label: key, source: 'native', required: true, visible: true, writable: true, conditional_access: false }));
describe('Catalog master form contracts', () => {
  it('uses exact numeric conditions and defaults consistently with the rendered custom controls', () => {
    const metadata: MasterField[] = ['cf_count', 'cf_note'].map((key, order) => ({ key: 'custom_field:' + key, label: key === 'cf_note' ? 'Note' : 'Count', source: 'custom', order, visible: true, writable: true, required: key === 'cf_note', conditional_access: false,
      custom: { key, data_type: key === 'cf_count' ? 'integer' : 'text', is_active: true, is_immutable_after_create: false, default_value: key === 'cf_count' ? '10' : null,
        visibility: key === 'cf_note' ? { field: 'cf_count', cmp: 'gte', value: '2' } : null, validation: { required: key === 'cf_note', max_length: 20 }, choices: [] } }));
    const config = masterConfig('manufacturers')!;
    expect(masterBody(config, metadata, { custom_fields: { cf_count: '10', cf_note: 'Entered' } }).body.custom_fields).toEqual({ cf_count: 10, cf_note: 'Entered' });
    expect(masterBody(config, metadata, { custom_fields: {} }).errors['custom_fields.cf_note']).toBe('Note is required.');
  });
  it('retains immutable custom values during an edit and leaves generated values to the service', () => {
    const metadata: MasterField[] = ['cf_immutable', 'cf_generated'].map((key, order) => ({ key: 'custom_field:' + key, label: key, source: 'custom', order, visible: true, writable: true, required: false, conditional_access: false,
      custom: { key, data_type: key === 'cf_generated' ? 'auto_number' : 'text', is_active: true, is_immutable_after_create: key === 'cf_immutable', validation: { required: false, max_length: 20 }, choices: [] } }));
    const previous = { id: 'id', row_version: 4, custom_fields: { cf_immutable: 'Saved', cf_generated: '1' } };
    expect(masterBody(masterConfig('manufacturers')!, metadata, { ...previous, custom_fields: { cf_immutable: null, cf_generated: '2' } }, previous).body)
      .toEqual({ expected_version: 4 });
  });
  it('validates authorized unit changes without inventing unreadable precision or increment values', () => {
    const config = masterConfig('units')!, previous = { id: 'id', row_version: 4 };
    expect(masterBody(config, fields(['quantity_increment']), { ...previous, quantity_increment: '0.001' }, previous))
      .toEqual({ body: { expected_version: 4, quantity_increment: '0.001' }, errors: {} });
    expect(masterBody(config, fields(['decimal_places']), { ...previous, decimal_places: '3' }, previous))
      .toEqual({ body: { expected_version: 4, decimal_places: 3 }, errors: {} });
    expect(masterBody(config, fields(['quantity_increment']), { ...previous, quantity_increment: '0' }, previous).errors.quantity_increment).toBeTruthy();
  });
  it('checks group parent identifiers before creating a dated assignment', () => {
    expect(masterBody(masterConfig('item-groups')!, [], { valid_from: '2026-10-24', parent_group_id: 'invalid' }).errors.parent_group_id).toBeTruthy();
  });
  it('keeps increments exact and rejects precision mismatches', () => {
    const metadata = fields(['code', 'name', 'symbol', 'dimension', 'decimal_places', 'quantity_increment']);
    const draft = { code: 'KG', name: 'Kilogram', symbol: 'kg', dimension: 'MASS', decimal_places: '3', quantity_increment: '0.001' };
    expect(masterBody(masterConfig('units')!, metadata, draft).body.quantity_increment).toBe('0.001');
    expect(masterBody(masterConfig('units')!, metadata, { ...draft, decimal_places: '2' }).errors.quantity_increment).toBeTruthy();
    expect(masterBody(masterConfig('units')!, metadata, { ...draft, quantity_increment: '0' }).errors.quantity_increment).toBeTruthy();
    expect(masterBody(masterConfig('units')!, metadata, { ...draft, quantity_increment: 0.001 }).errors.quantity_increment).toBeTruthy();
  });
  it('omits protected values and patches only changed writable fields with a version', () => {
    const metadata = fields(['code', 'name', 'is_active', 'row_version']); metadata[0]!.writable = false;
    const previous = { id: 'id', code: 'A', name: 'Before', row_version: 4, is_active: true };
    expect(masterBody(masterConfig('manufacturers')!, metadata, { ...previous, code: 'B', name: 'After', is_active: false }, previous).body)
      .toEqual({ expected_version: 4, name: 'After' });
  });
  it('validates labels, choices and real effective dates', () => {
    const result = masterBody(masterConfig('item-groups')!, fields(['code', 'name', 'allowed_kind']), { code: 'bad code', name: ' ', allowed_kind: 'INVALID', valid_from: '2026-02-30' });
    expect(Object.keys(result.errors)).toEqual(expect.arrayContaining(['code', 'name', 'allowed_kind', 'valid_from']));
  });
});
