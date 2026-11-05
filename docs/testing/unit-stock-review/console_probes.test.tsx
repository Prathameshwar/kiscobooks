/** High-finding regressions plus diagnostics for the still-open Medium findings. */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { DisplayConfigProvider } from '@janso/ui';
import { beforeEach, expect, it, vi } from 'vitest';
import { StockDirectory } from '../app/components/StockDirectory';
import { VoucherItems } from '../app/components/VoucherItems';
import { buildProductSetup, emptyProductSetup } from '../app/lib/product-creation';
import { serviceCall } from '../app/lib/service-call';
import { productFieldRequest } from '../app/lib/product-fields';
import { entryConfiguration } from './product-entry-fixtures';

vi.mock('../app/lib/service-call', async original => ({
  ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn(),
}));
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
vi.mock('../app/components/StockTrackingCommon', () => ({ TrackingReference: () => null }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
beforeEach(() => { vi.clearAllMocks(); });

it('reproduces nonzero stock rendered as zero without an exact quantity', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/configuration')) return { posting_enabled: true } as never;
    if (request.path.endsWith('/field-set')) return {
      resource: 'stock-cost-pools', fields: ['item_id', 'quantity', 'value', 'currency'].map(key => ({key, readable: true, visible: true})),
    } as never;
    return { items: [{id: id(3), item_id: id(2), quantity: '0.0010', value: '1', currency: 'INR'}],
      page: {limit: 25, has_more: false, next_cursor: null} } as never;
  });
  render(<DisplayConfigProvider config={{quantityPrecision: 2}}><StockDirectory company={id(1)} view="cost-pools" canConfigure={false}/></DisplayConfigProvider>);
  await screen.findByRole('link', {name: 'View product'});
  expect(screen.getByRole('cell', {name: '0.00'})).toBeInTheDocument();
  expect(screen.queryByText(/0\.001/)).not.toBeInTheDocument();
  expect(screen.queryByRole('columnheader', {name: /unit/i})).not.toBeInTheDocument();
});

it('reproduces company quantity defaults ignored by product creation', () => {
  const configuration = entryConfiguration('2026-10-31');
  configuration.numeric_defaults = [{dimension: 'COUNT', quantity_decimal_places: 0, quantity_increment: '5'}] as never;
  const built = buildProductSetup(emptyProductSetup('2026-10-31'), {
    enabled: true, configuration, baseUnit: {id: id(4), decimal_places: 0, quantity_increment: '1', dimension: 'COUNT'},
    requireGroup: false, taxAllowed: false, pricingAllowed: false,
  });
  expect(built.errors).toEqual({});
  expect(built.setup?.units[0]?.quantity_increment).toBe('1');
});

it('reproduces a required alternate conversion omitted without a creation error', () => {
  const configuration = entryConfiguration('2026-10-31');
  configuration.options.alternate_units_mode = 'REQUIRED';
  configuration.options.alternate_units_default = null;
  const built = buildProductSetup(emptyProductSetup('2026-10-31'), {
    enabled: true, configuration, baseUnit: {id: id(4), decimal_places: 0, quantity_increment: '1', dimension: 'COUNT'},
    requireGroup: false, taxAllowed: false, pricingAllowed: false,
  });
  expect(built.errors).toEqual({});
  expect(built.setup?.units).toHaveLength(1);
});

it('refuses a pack scan before changing the stock item or unit', async () => {
  const metadata = {native: {properties: {stock: {}, lines: {items: {properties: {item: {properties: {
    item_id: {}, unit_id: {}, actual_quantity: {}, billed_quantity: {},
  }}}}}}}, custom: [], configuration: {kind: 'RECEIPT_NOTE', profile: 'STANDARD', policy: {stock: {}, max_lines: 100}}} as never;
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => {
    if (path.endsWith('/barcodes/resolve')) return {barcode_id: id(8), item_id: id(2), item_version: 1,
      unit_id: id(5), binding_id: id(6), unit_revision_id: id(7), usage_role: 'PACK', numerator: '12', denominator: '1',
      name: 'Tea', sku: 'TEA', lot_hint: null, expiry_yymmdd_hint: null, serial_hint: null} as never;
    if (path.endsWith('/units/' + id(5))) return {id: id(5), company_id: id(1), name: 'Boxes', code: 'BOX'} as never;
    return {items: [], page: {has_more: false}} as never;
  });
  function Form() {
    const [lines, setLines] = useState<any[]>([]);
    return <><VoucherItems company={id(1)} currency="INR" metadata={metadata} lines={lines} onChange={setLines}
      disabled={false} asOf="2026-10-31" canScan/><output data-testid="lines">{JSON.stringify(lines)}</output></>;
  }
  render(<Form/>);
  fireEvent.click(screen.getByRole('button', {name: 'Add item'}));
  fireEvent.change(screen.getByLabelText('Scan barcode 1'), {target: {value: 'REVIEW-PACK'}});
  fireEvent.click(screen.getByRole('button', {name: 'Resolve barcode 1'}));
  await screen.findByText(/base-unit barcode/i);
  expect(screen.getByTestId('lines').textContent).not.toContain(id(5));
  expect(screen.getByTestId('lines').textContent).not.toContain(id(2));
});

it('preserves BIGINT ratios from the string barcode API contract', () => {
  const parsed = JSON.parse('{"numerator":"9007199254740993","denominator":"9007199254740995"}');
  expect(BigInt(parsed.numerator)).toBe(9007199254740993n);
  expect(BigInt(parsed.denominator)).toBe(9007199254740995n);
});
