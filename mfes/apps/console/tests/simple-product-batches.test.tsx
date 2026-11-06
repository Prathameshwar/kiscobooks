import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, simpleOptions, multiPriceOptions } from './simple-product-ready-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const root = `/v1/companies/${COMPANY}/simple-product-creations`;
const UNIT = '33333333-3333-4333-8333-333333333333';
let options: ReturnType<typeof setup>;
function setup(multiple = false) {
  const value = multiple ? multiPriceOptions() : simpleOptions();
  return { ...value, batch: { available: true, required: false, expiry_enabled: true, expiry_required: false, manufacture_date_required: false },
    fields: [...value.fields, ...['batch_enabled', 'batch_code', 'batch_expires_on', 'batch_mrp_amount'].map(key => ({ key, label: key, source: 'native', visible: true, writable: true, required: false, conditional_access: false, order: 0 }))] };
}
beforeEach(() => {
  sessionStorage.clear(); options = setup(); api.mockReset();
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/options?')) return options as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) return { items: [{ id: UNIT, label: 'Numbers' }], page: { has_more: false } } as never;
    if (request.path === root || request.path.endsWith('/advance')) return { id: 'job', company_id: COMPANY, code: 'BATCH12345', status: 'COMPLETE', step: 'COMPLETE', opening_posted: true } as never;
    throw new Error(request.path);
  });
});
const user = () => userEvent.setup({ delay: null });
async function show() {
  render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>);
  await user().type(await screen.findByRole('textbox', { name: 'Product name' }), 'Tea');
  await user().click(screen.getByRole('combobox', { name: 'Base unit' }));
  await user().click(await screen.findByRole('option', { name: 'Numbers' }));
  await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
}
it('uses a second step and saves exact row prices and quantities with one final save', async () => {
  await show();
  expect(screen.getByRole('switch', { name: 'Allow batch' })).not.toBeChecked();
  await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  expect(screen.queryByRole('textbox', { name: 'Purchase price' })).not.toBeInTheDocument();
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'LOT-A');
  await user().clear(screen.getByRole('textbox', { name: 'Opening quantity 1' }));
  await user().type(screen.getByRole('textbox', { name: 'Opening quantity 1' }), '3');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Purchase price 1' })).toHaveAttribute('aria-invalid', 'true');
  await user().type(screen.getByRole('textbox', { name: 'Purchase price 1' }), '12.50');
  await user().type(screen.getByRole('textbox', { name: 'Selling price 1' }), '20');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === root)![1].body;
  expect(body).toMatchObject({ batch_enabled: true, batches: [{ code: 'LOT-A', opening_quantity: '3', purchase_price: '12.50', sale_price: '20' }], opening_date: '2026-04-01' });
  expect(body).not.toHaveProperty('purchase_price');
});
it('rejects zero Purchase price for a batch opening before any write', async () => {
  await show(); await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'LOT-100');
  await user().clear(screen.getByRole('textbox', { name: 'Opening quantity 1' }));
  await user().type(screen.getByRole('textbox', { name: 'Opening quantity 1' }), '100');
  await user().type(screen.getByRole('textbox', { name: 'Purchase price 1' }), '0');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('Enter a positive Purchase price with up to four decimal places.')).toBeVisible();
  expect(api.mock.calls.some(([, request]) => request.path === root)).toBe(false);
});
it('preserves rows when moving back and uses ordinary prices when switched off', async () => {
  await show(); await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'Keep');
  await user().click(screen.getByRole('button', { name: 'Back to product details' }));
  await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
  expect(screen.getByRole('textbox', { name: 'Batch 1' })).toHaveValue('Keep');
  await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === root)![1].body;
  expect(body).toMatchObject({ batch_enabled: false, opening_quantity: '0' });
  expect(body).not.toHaveProperty('batches');
});
it('uses configured sale levels and hides expiry when disabled', async () => {
  options = setup(true); options.batch.expiry_enabled = false;
  await show(); await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  expect(screen.queryByLabelText('Expiry date 1')).not.toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: 'Retail (excl. tax) 1' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Wholesale (excl. tax) 1' })).toBeRequired();
  await user().click(screen.getByRole('button', { name: 'Add batch' }));
  expect(screen.getByRole('textbox', { name: 'Batch 2' })).toBeVisible();
  await user().click(screen.getByRole('button', { name: 'Remove batch 1' }));
  expect(screen.queryByRole('textbox', { name: 'Batch 2' })).not.toBeInTheDocument();
});

it('opens product details and focuses a server error returned from the stock step', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, subject) => {
    if (request.path === root) return Promise.reject({ status: 422, message: 'Check product details', fields: { name: 'Choose a distinct product name.' } });
    if (request.path.includes('/by-key/')) return Promise.reject({ status: 404, message: 'Not saved' });
    return original(endpoint, request, subject);
  });
  await show();
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  const name = await screen.findByRole('textbox', { name: 'Product name' });
  expect(name).toBeVisible();
  await waitFor(() => expect(name).toHaveFocus());
  expect(screen.getByText('Choose a distinct product name.')).toBeVisible();
  await user().clear(name); await user().type(name, 'New name');
  await user().click(screen.getByRole('button', { name: 'Next: Stock and prices' }));
  expect(screen.getByRole('switch', { name: 'Allow batch' })).toBeVisible();
  expect(screen.queryByText('Choose a distinct product name.')).not.toBeInTheDocument();
});

it('attaches indexed sale-price errors to the correct batch price input', async () => {
  options = setup(true);
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, subject) => {
    if (request.path === root) return Promise.reject({ status: 422, message: 'Check prices', fields: { 'batches.0.sale_prices.1.amount': 'Wholesale price exceeds the configured limit.' } });
    if (request.path.includes('/by-key/')) return Promise.reject({ status: 404, message: 'Not saved' });
    return original(endpoint, request, subject);
  });
  await show(); await user().click(screen.getByRole('switch', { name: 'Allow batch' }));
  await user().type(screen.getByRole('textbox', { name: 'Batch 1' }), 'LOT-A');
  await user().type(screen.getByRole('textbox', { name: 'Retail (excl. tax) 1' }), '20');
  const wholesale = screen.getByRole('textbox', { name: 'Wholesale (excl. tax) 1' });
  await user().type(wholesale, '25');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText('Wholesale price exceeds the configured limit.');
  expect(wholesale).toHaveAttribute('aria-invalid', 'true');
  await waitFor(() => expect(wholesale).toHaveFocus());
});
