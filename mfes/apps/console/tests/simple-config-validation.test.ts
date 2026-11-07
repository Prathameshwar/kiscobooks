import { describe, expect, it } from 'vitest';
import type { components } from '@janso/api-client/catalog';
import { batchInputs, type BatchRow } from '../app/components/SimpleProductBatches';
import { serialInputs, type SerialRow } from '../app/components/SimpleProductSerials';
import { simpleOptions } from './simple-product-ready-fixtures';

type Options = components['schemas']['SimpleCreationOptions'];
function settings(): Options {
  const base = simpleOptions();
  return { ...base, batch: { available: true, required: true, expiry_enabled: true, expiry_required: true, manufacture_date_required: true },
    fields: [...base.fields, ...['batch_enabled', 'batch_code', 'batch_manufactured_on', 'batch_expires_on', 'batch_mrp_amount'].map(key => ({ ...base.fields[0]!, key }))],
  } as unknown as Options;
}
const row = (values: Record<string, string> = {}): BatchRow => ({ key: 'one', values: {
  code: 'LOT-A', opening_quantity: '10', opening_unit_cost: '50', purchase_price: '60', sale_price: '90',
  manufactured_on: '2026-03-01', expires_on: '2027-03-01', ...values,
} });
const serial = (value: string, key = value): SerialRow => ({ key, values: { 'SERIAL.1': value } });
function serialized(): Options {
  return { ...settings(), serial: { enabled: true, requirements: [{ identifier_type: 'SERIAL', namespace_rule: 'COMPANY', min_count: 1, max_count: 1, requires_slot: false }] } };
}

describe('S07 batch compatibility and negative cases', () => {
  it('preserves separate purchase reference and opening costs for exact native valuation', () => {
    const result = batchInputs([row(), row({ code: 'LOT-B', opening_quantity: '20', opening_unit_cost: '55', purchase_price: '65' })], settings());
    expect(result.errors).toEqual({});
    expect(result.batches).toMatchObject([{ opening_quantity: '10', opening_unit_cost: '50', purchase_price: '60' }, { opening_quantity: '20', opening_unit_cost: '55', purchase_price: '65' }]);
  });
  it.each(['2026-02-30', '2026-13-01', '999-01-01'])('rejects invalid manufacture date %s before a request', date => {
    expect(batchInputs([row({ manufactured_on: date })], settings()).errors['batches.0.manufactured_on']).toBeTruthy();
  });
  it('rejects invalid expiry even when manufacture is omitted', () => {
    const options = settings(); options.batch!.manufacture_date_required = false;
    expect(batchInputs([row({ manufactured_on: '', expires_on: '2026-02-30' })], options).errors['batches.0.expires_on']).toBeTruthy();
  });
  it('rejects expiry preceding manufacture and missing required dates', () => {
    expect(batchInputs([row({ expires_on: '2025-03-01' })], settings()).errors['batches.0.expires_on']).toBeTruthy();
    expect(batchInputs([row({ manufactured_on: '' })], settings()).errors['batches.0.manufactured_on']).toBeTruthy();
  });
  it('matches native casefold for duplicate batch identifiers', () => {
    expect(batchInputs([row({ code: 'Straße' }), row({ code: 'STRASSE' })], settings()).errors['batches.1.code']).toBeTruthy();
  });
  it('accepts printable batch spacing supported by the native batch schema', () => {
    expect(batchInputs([row({ code: 'LOT\u00a0A' })], settings()).errors).toEqual({});
  });
  it.each(['A\u0000B', 'x'.repeat(101)])('rejects invalid batch number', code => {
    expect(batchInputs([row({ code })], settings()).errors['batches.0.code']).toBeTruthy();
  });
  it('rejects a 65th batch before sending', () => {
    expect(batchInputs(Array.from({ length: 65 }, (_, i) => row({ code: 'LOT-' + i })), settings()).errors.batches).toBeTruthy();
  });
  it('blocks retained disabled expiry and negative or zero valuation costs', () => {
    const options = settings(); options.batch!.expiry_enabled = false;
    expect(batchInputs([row()], options).errors['batches.0.expires_on']).toBeTruthy();
    for (const cost of ['-1', '0', '1.00001']) expect(batchInputs([row({ opening_unit_cost: cost })], settings()).errors['batches.0.opening_unit_cost']).toBeTruthy();
  });
});

describe('S08 serial limits and batch combination', () => {
  it('rejects more than 200 serial units', () => {
    expect(serialInputs(Array.from({ length: 201 }, (_, i) => serial('A' + i)), serialized()).errors.serials).toBeTruthy();
  });
  it('rejects aggregate overflow across batches', () => {
    const rows = [0, 1].map(index => ({ ...row({ code: 'LOT-' + index }), serials: Array.from({ length: 101 }, (_, i) => serial(index + '-' + i)) }));
    expect(batchInputs(rows, serialized()).errors.batches).toBeTruthy();
  });
  it('derives batch quantity from identifiers and rejects cross-batch duplicates', () => {
    const rows = [{ ...row(), serials: [serial('A'), serial('B')] }, { ...row({ code: 'LOT-B' }), serials: [serial('a')] }];
    const result = batchInputs(rows, serialized());
    expect(result.batches[0].opening_quantity).toBe('2');
    expect(Object.values(result.errors)).toContain('This identifier is already entered for another unit.');
  });
});
