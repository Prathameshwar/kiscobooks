import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, simpleOptions } from './simple-product-ready-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const UNIT = '019b0000-0000-7000-8000-000000000012';
const root = `/v1/companies/${COMPANY}/simple-product-creations`;
function settings() {
  const value = simpleOptions();
  return { ...value, serial: { enabled: true, requirements: [{ identifier_type: 'SERIAL' as 'SERIAL' | 'IMEI', namespace_rule: 'COMPANY' as const, min_count: 1, max_count: 1, requires_slot: false }] },
    batch: { available: false, required: false, expiry_enabled: false, expiry_required: false, manufacture_date_required: false },
    fields: [...value.fields, ...['serial_identifiers', 'batch_enabled', 'batch_code'].map(key => ({ key, label: key, source: 'native', visible: true, writable: true, required: false, conditional_access: false, order: 0 }))] };
}
let options = settings();
const user = () => userEvent.setup({ delay: null });
beforeEach(() => {
  sessionStorage.clear(); options = settings(); api.mockReset();
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/options?')) return options as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) return { items: [{ id: UNIT, label: 'Numbers' }], page: { has_more: false } } as never;
    if (request.path === root) return { id: 'saved', company_id: COMPANY, code: 'SERIAL1234', status: 'COMPLETE', step: 'COMPLETE', opening_posted: true } as never;
    throw new Error(request.path);
  });
});
async function show() {
  render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>);
  await user().type(await screen.findByRole('textbox', { name: 'Product name' }), 'Device');
  await user().click(screen.getByRole('combobox', { name: 'Base unit' }));
  await user().click(await screen.findByRole('option', { name: 'Numbers' }));
  await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
}
it('derives whole opening quantity and saves configured serial inputs with product prices', async () => {
  await show();
  await user().type(screen.getByRole('textbox', { name: 'Purchase price' }), '12.50');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  await user().type(screen.getByRole('textbox', { name: 'Serial number, unit 1' }), 'A001');
  expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveValue('1');
  expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveAttribute('readonly');
  await user().click(screen.getByRole('button', { name: 'Back to product details' }));
  await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
  expect(screen.getByRole('textbox', { name: 'Serial number, unit 1' })).toHaveValue('A001');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === root)![1].body).toMatchObject({
    purchase_price: '12.50', opening_quantity: '1', serials: [{ identifiers: [{ identifier_type: 'SERIAL', slot: 1, value: 'A001' }] }],
  });
});
it('blocks blank and duplicate serials before submitting and supports removing units', async () => {
  await show(); await user().type(screen.getByRole('textbox', { name: 'Purchase price' }), '10');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Serial number, unit 1' })).toHaveAttribute('aria-invalid', 'true');
  await user().type(screen.getByRole('textbox', { name: 'Serial number, unit 1' }), 'ABC');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  await user().type(screen.getByRole('textbox', { name: 'Serial number, unit 2' }), 'abc');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByText('This identifier is already entered for another unit.')).toBeVisible();
  expect(api.mock.calls.some(([, request]) => request.path === root)).toBe(false);
  await user().click(screen.getByRole('button', { name: 'Remove unit 2' }));
  expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveValue('1');
});
it('keeps serials on the required batch and derives its row quantity', async () => {
  options.batch.available = true; options.batch.required = true;
  await show();
  expect(screen.getByRole('switch', { name: 'Allow batch' })).toBeDisabled();
  await user().click(screen.getByRole('button', { name: 'Add batch' }));
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'LOT-A');
  await user().type(screen.getByRole('textbox', { name: 'Purchase price 1' }), '20');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  await user().type(screen.getByRole('textbox', { name: 'Serial number, unit 1' }), 'B001');
  expect(screen.getByRole('textbox', { name: 'Opening quantity 1' })).toHaveValue('1');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === root)![1].body;
  expect(body).toMatchObject({ batch_enabled: true, batches: [{ code: 'LOT-A', opening_quantity: '1', serials: [{ identifiers: [{ value: 'B001' }] }] }] });
  expect(body).not.toHaveProperty('serials');
});
it('keeps serial capture disabled without native field access', async () => {
  options.fields.find(field => field.key === 'serial_identifiers')!.writable = false;
  await show();
  expect(screen.getByRole('button', { name: 'Add serial unit' })).toBeDisabled();
  expect(screen.getByText('Your field access does not allow serial entry.')).toBeVisible();
});

it('shows a batch serial validation error once next to the identifier', async () => {
  options.batch.available = true; options.batch.required = true;
  await show(); await user().click(screen.getByRole('button', { name: 'Add batch' }));
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'LOT-A');
  await user().type(screen.getByRole('textbox', { name: 'Purchase price 1' }), '10');
  for (const index of [1, 2]) {
    await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
    await user().type(screen.getByRole('textbox', { name: `Serial number, unit ${index}` }), 'DUPLICATE');
  }
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getAllByText('This identifier is already entered for another unit.')).toHaveLength(1);
  expect(screen.getByRole('textbox', { name: 'Serial number, unit 2' })).toHaveFocus();
});

it('validates IMEI and accepts the configured minimum count in either allowed slot', async () => {
  options.serial.requirements = [{ identifier_type: 'IMEI', namespace_rule: 'COMPANY', min_count: 1, max_count: 2, requires_slot: true }];
  await show(); await user().type(screen.getByRole('textbox', { name: 'Purchase price' }), '10');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  const input = screen.getByRole('textbox', { name: 'IMEI 2, unit 1' });
  await user().type(input, '490154203237519');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(input).toHaveAttribute('aria-invalid', 'true');
  await user().clear(input); await user().type(input, '490154203237518');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === root)![1].body).toMatchObject({ serials: [{ identifiers: [{ identifier_type: 'IMEI', slot: 2, value: '490154203237518' }] }] });
});

it('continues the same serial save after temporary throttling', async () => {
  const original = api.getMockImplementation()!; let attempts = 0;
  const saved = { id: '33333333-3333-4333-8333-333333333333', company_id: COMPANY, code: 'SERIAL1234', status: 'RUNNING', step: 'SERIAL', opening_posted: false };
  api.mockImplementation((endpoint, request, init) => {
    if (request.path === root) return Promise.resolve(saved as never);
    if (request.path.endsWith('/advance')) {
      if (attempts++ === 0) return Promise.reject({ status: 429, message: 'Try again shortly' });
      return Promise.resolve({ ...saved, status: 'COMPLETE', step: 'COMPLETE', opening_posted: true } as never);
    }
    return original(endpoint, request, init);
  });
  await show(); await user().type(screen.getByRole('textbox', { name: 'Purchase price' }), '10');
  await user().click(screen.getByRole('button', { name: 'Add serial unit' }));
  await user().type(screen.getByRole('textbox', { name: 'Serial number, unit 1' }), 'RETRY');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/, {}, { timeout: 5000 });
  expect(attempts).toBe(2);
  expect(api.mock.calls.filter(([, request]) => request.path === root)).toHaveLength(1);
}, 10000);
