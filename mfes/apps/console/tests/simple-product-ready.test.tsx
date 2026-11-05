import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { allowedSimpleProductRequest } from '../app/lib/simple-product-policy';

import { COMPANY, GROUP, simpleOptions, configuredSimpleOptions, multiPriceOptions } from './simple-product-ready-fixtures';
const ID = '22222222-2222-4222-8222-222222222222';
const UNIT = '33333333-3333-4333-8333-333333333333';
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const base = `/v1/companies/${COMPANY}/simple-product-creations`;
const saved = { id: ID, company_id: COMPANY, status: 'RUNNING', step: 'CREATE', code: 'AB12345678', row_version: 1, item_id: null, opening_posted: false };
function replies(gst = false) {
  return async (_endpoint: string, request: { path: string; method?: string; body?: unknown }) => {
    if (request.path.includes('/options?')) return simpleOptions(new URL(request.path, 'http://test').searchParams.get('kind')!, gst) as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) return { items: [{ id: UNIT, value: UNIT, label: 'Numbers', code: 'NOS' }], page: { has_more: false } } as never;
    if (request.path === base) return saved as never;
    if (request.path.endsWith('/advance')) return { ...saved, status: 'COMPLETE', step: 'COMPLETE', item_id: UNIT, opening_posted: true } as never;
    throw { status: 404, message: 'Missing fixture ' + request.path };
  };
}
export const renderSimpleProduct = (returnTo?: string) => render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} returnTo={returnTo} /></DisplayConfigProvider>);
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); api.mockImplementation(replies()); });

async function fillProduct() {
  const user = userEvent.setup({ delay: null });
  await user.type(await screen.findByRole('textbox', { name: 'Product name' }), 'Tea');
  await user.click(screen.getByRole('combobox', { name: /Base unit/ }));
  await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  return user;
}

function detailsOptions(mode = 'OPTIONAL', enabled = false) {
  const options = simpleOptions();
  return { ...options, configuration: { ...options.configuration, options: {
    brand_mode: mode, brand_default: enabled, model_mode: mode, model_default: enabled,
    barcode_mode: mode, barcode_default: enabled,
  } }, fields: [...options.fields, ...['series_id', 'barcode_value', 'barcode_symbology'].map(key => ({
    ...options.fields[0]!, key, label: { series_id: 'Brand series', barcode_value: 'Barcode value', barcode_symbology: 'Barcode format' }[key]!,
    ...(key === 'barcode_symbology' ? { control: { kind: 'select', choices: [{ value: 'CODE128', label: 'Code 128' }, { value: 'GTIN', label: 'GTIN' }, { value: 'QR', label: 'QR' }] } } : {}),
  }))] };
}

function withDetails(options = detailsOptions()) {
  const original = replies();
  api.mockImplementation((endpoint, request) => request.path.includes('/options?') ? Promise.resolve(options as never) : original(endpoint, request));
}

it.each(['custom_fields', 'shared_custom_fields'])('validates and saves %s conditional on entered native details', async namespace => {
  const original = replies();
  const options = detailsOptions('OPTIONAL', true);
  api.mockImplementation((endpoint, request) => request.path.includes('/options?') ? Promise.resolve({ ...options,
    configuration: { ...options.configuration, options: { ...options.configuration.options, brand_default: false, barcode_default: false } },
    fields: [...options.fields, { key: namespace + '.cf_note', label: 'Model note', source: 'custom', visible: true, writable: true, required: true, order: 100,
      custom: { key: 'cf_note', data_type: 'text', is_active: true, is_immutable_after_create: false, validation: { required: true }, choices: [], visibility: { field: 'model_code', cmp: 'eq', value: 'Classic' } },
    }],
  } as never) : original(endpoint, request));
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Model' }), 'Classic');
  const note = screen.getByRole('textbox', { name: 'Model note' });
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(api.mock.calls.some(([, request]) => request.path === base)).toBe(false);
  expect(note).toHaveFocus();
  await user.type(note, 'Retain this note');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).toMatchObject({ [namespace]: { cf_note: 'Retain this note' } });
});

it('uses optional detail switches, requires enabled inputs, and omits switched-off values', async () => {
  withDetails(); renderSimpleProduct(); const user = await fillProduct();
  for (const label of ['Brand', 'Model', 'Barcode']) expect(screen.getByRole('switch', { name: 'Use ' + label })).not.toBeChecked();
  expect(screen.queryByRole('textbox', { name: 'Model' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Barcode value' })).toBeNull();
  await user.click(screen.getByRole('switch', { name: 'Use Model' }));
  await user.click(screen.getByRole('switch', { name: 'Use Barcode' }));
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Model' })).toHaveFocus();
  expect(screen.getByRole('textbox', { name: 'Barcode value' })).toHaveAttribute('aria-invalid', 'true');
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  await user.type(screen.getByRole('textbox', { name: 'Model' }), 'Classic');
  await user.type(screen.getByRole('textbox', { name: 'Barcode value' }), '0012345678905');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Barcode format' }), 'GTIN');
  await user.click(screen.getByRole('switch', { name: 'Use Model' }));
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === base)![1].body;
  expect(body).toMatchObject({ barcode: { value: '0012345678905', symbology: 'GTIN' } });
  expect(body).not.toHaveProperty('model_code'); expect(body).not.toHaveProperty('brand_id');
});

it('honors optional detail defaults and keeps required switches enabled', async () => {
  withDetails(detailsOptions('OPTIONAL', true)); const view = renderSimpleProduct(); await screen.findByDisplayValue('Default');
  for (const label of ['Brand', 'Model', 'Barcode']) expect(screen.getByRole('switch', { name: 'Use ' + label })).toBeChecked();
  view.unmount(); withDetails(detailsOptions('REQUIRED')); renderSimpleProduct(); await screen.findByDisplayValue('Default');
  for (const label of ['Brand', 'Model', 'Barcode']) {
    expect(screen.getByRole('switch', { name: 'Use ' + label })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Use ' + label })).toBeDisabled();
  }
});

it('omits Brand and its series when switched off and keeps Model independent', async () => {
  withDetails(); renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('switch', { name: 'Use Brand' }));
  for (const label of ['Brand', 'Brand series']) {
    await user.click(screen.getByRole('combobox', { name: label }));
    await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  }
  await user.click(screen.getByRole('switch', { name: 'Use Brand' }));
  expect(screen.queryByRole('combobox', { name: 'Brand series' })).toBeNull();
  await user.click(screen.getByRole('switch', { name: 'Use Model' }));
  await user.type(screen.getByRole('textbox', { name: 'Model' }), 'Independent');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === base)![1].body;
  expect(body).toMatchObject({ model_code: 'Independent' });
  for (const key of ['brand_id', 'series_id', 'barcode']) expect(body).not.toHaveProperty(key);
});

it('respects protected barcode fields and blocks inaccessible required barcode entry', async () => {
  const options = detailsOptions(); options.fields.find(field => field.key === 'barcode_value')!.writable = false;
  withDetails(options); const view = renderSimpleProduct(); await screen.findByDisplayValue('Default');
  expect(screen.getByRole('switch', { name: 'Use Barcode' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
  view.unmount(); options.configuration.options.barcode_mode = 'REQUIRED'; withDetails(options);
  renderSimpleProduct(); await screen.findByText(/field access does not allow all required/);
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
});

it('focuses native barcode errors beside the entered value', async () => {
  const original = replies(); let rejected = false;
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) return Promise.resolve(detailsOptions() as never);
    if (request.path === base && !rejected) { rejected = true; return Promise.reject({ status: 422, message: 'Invalid barcode', fields: { 'barcode.value': 'GTIN check digit is invalid' } }); }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('switch', { name: 'Use Barcode' }));
  await user.type(screen.getByRole('textbox', { name: 'Barcode value' }), '0012345678900');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('GTIN check digit is invalid')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Barcode value' })).toHaveFocus();
});

it('locks detail switches during uncertain saves and retries the exact barcode command', async () => {
  const original = replies(); let failed = false;
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) return Promise.resolve(detailsOptions() as never);
    if (request.path === base && !failed) { failed = true; return Promise.reject({ status: 503, message: 'Save response lost' }); }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('switch', { name: 'Use Barcode' }));
  await user.type(screen.getByRole('textbox', { name: 'Barcode value' }), '0000123');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText('Save response lost');
  expect(screen.getByRole('switch', { name: 'Use Barcode' })).toBeDisabled();
  expect(screen.getByRole('textbox', { name: 'Barcode value' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Retry Save' }));
  await screen.findByText(/active and ready/);
  const writes = api.mock.calls.filter(([, request]) => request.path === base).map(([, request]) => request);
  expect(writes).toHaveLength(2); expect(writes[0]).toEqual(writes[1]);
  expect(writes[1]!.body).toMatchObject({ barcode: { value: '0000123', symbology: 'CODE128' } });
});

it('keeps entered optional details visible when refreshed field access prevents saving them', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = detailsOptions(); options.kind = new URL(request.path, 'http://test').searchParams.get('kind')!;
      if (options.kind === 'SERVICE') options.fields.find(field => field.key === 'barcode_value')!.writable = false;
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('switch', { name: 'Use Barcode' }));
  await user.type(screen.getByRole('textbox', { name: 'Barcode value' }), '0000123');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  await screen.findByText(/field access does not allow all required/);
  expect(screen.getByRole('textbox', { name: 'Barcode value' })).toHaveValue('0000123');
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  await user.click(screen.getByRole('switch', { name: 'Use Barcode' }));
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
});

it('requires an explicit clear when refreshed configuration would omit entered prices and details', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = detailsOptions(); options.kind = new URL(request.path, 'http://test').searchParams.get('kind')!;
      if (options.kind === 'SERVICE') {
        options.configuration.options.model_mode = 'DISABLED';
        options.configuration.pricing.purchase_reference_mode = 'DISABLED';
        options.fields = options.fields.filter(field => field.key !== 'purchase_price');
      }
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Purchase price' }), '12.50');
  await user.click(screen.getByRole('switch', { name: 'Use Model' }));
  await user.type(screen.getByRole('textbox', { name: 'Model' }), 'Classic');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  await screen.findByText(/Some entered details are no longer available/);
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  await user.click(screen.getByRole('button', { name: 'Clear unavailable details' }));
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
  await user.click(screen.getByRole('combobox', { name: 'Base unit' }));
  await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === base)![1].body;
  expect(body).not.toHaveProperty('model_code'); expect(body).not.toHaveProperty('purchase_price');
});

it('starts with simple Goods and switches GST HSN to SAC without opening stock', async () => {
  api.mockImplementation(replies(true)); renderSimpleProduct();
  expect(await screen.findByRole('combobox', { name: 'Type' })).toHaveValue('GOODS');
  expect(screen.getByRole('combobox', { name: /HSN/ })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveValue('0');
  expect(screen.getByLabelText('Opening date')).toHaveAttribute('readonly');
  expect(screen.queryByRole('textbox', { name: 'MRP' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Model' })).toBeNull();
  expect(screen.queryByRole('switch')).toBeNull();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  expect(await screen.findByRole('combobox', { name: /SAC/ })).toBeVisible();
  expect(screen.queryByRole('combobox', { name: /HSN/ })).toBeNull();
  expect(screen.queryByRole('group', { name: 'Opening stock' })).toBeNull();
});

it('captures named selling levels with required coverage and exact amounts in one Save', async () => {
  const options = multiPriceOptions(); const original = replies();
  api.mockImplementation((endpoint, request) => request.path.includes('/options?') ? Promise.resolve(options as never) : original(endpoint, request));
  renderSimpleProduct(); const user = await fillProduct();
  expect(screen.queryByRole('textbox', { name: 'Selling price' })).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Retail' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Wholesale' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Distributor' })).not.toBeRequired();
  await user.type(screen.getByRole('textbox', { name: 'Retail' }), '20.1234');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Wholesale' })).toHaveFocus();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  await user.type(screen.getByRole('textbox', { name: 'Wholesale' }), '0.0000');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).toMatchObject({
    sale_prices: [
      { price_level_id: options.sale_price_levels[0]!.price_level_id, amount: '20.1234' },
      { price_level_id: options.sale_price_levels[1]!.price_level_id, amount: '0.0000' },
    ],
  });
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).not.toHaveProperty('sale_price');
});

it('blocks silent loss of entered selling levels after refreshed settings remove them', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => request.path.includes('/options?')
    ? Promise.resolve((request.path.includes('kind=SERVICE') ? simpleOptions('SERVICE') : multiPriceOptions()) as never)
    : original(endpoint, request));
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Retail' }), '20.1234');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  await screen.findByRole('button', { name: 'Clear unavailable details' });
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Clear unavailable details' }));
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
});

it('enforces selling-level field access and preserves the complete uncertain price request', async () => {
  const options = multiPriceOptions(); const original = replies(); let attempts = 0;
  options.fields.find(field => field.label === 'Wholesale')!.writable = false;
  api.mockImplementation((endpoint, request) => request.path.includes('/options?') ? Promise.resolve(options as never) : original(endpoint, request));
  const view = renderSimpleProduct(); await screen.findByDisplayValue('Default');
  expect(screen.getByRole('textbox', { name: 'Wholesale' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  view.unmount(); options.fields.find(field => field.label === 'Wholesale')!.writable = true;
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) return Promise.resolve(options as never);
    if (request.path === base && attempts++ === 0) return Promise.reject({ status: 503, message: 'Connection lost' });
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Retail' }), '20.1234');
  await user.type(screen.getByRole('textbox', { name: 'Wholesale' }), '18.50');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  const retry = await screen.findByRole('button', { name: 'Retry Save' });
  expect(screen.getByRole('textbox', { name: 'Retail' })).toBeDisabled();
  await user.click(retry); await screen.findByText(/active and ready/);
  const requests = api.mock.calls.filter(([, request]) => request.path === base).map(([, request]) => request);
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
});

it('one Save sends exact opening quantity and purchase price and finishes ready', async () => {
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Purchase price' }), '12.50');
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '3');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText(/Product AB12345678 is active and ready/)).toBeVisible();
  const create = api.mock.calls.find(([, request]) => request.path === base)![1];
  expect(create.body).toMatchObject({ kind: 'GOODS', code: null, purchase_price: '12.50', opening_quantity: '3', opening_date: '2026-04-01' });
  expect(create.body).not.toHaveProperty('opening_cost');
  expect(screen.queryByRole('button', { name: /Approve|Submit|Activate/ })).toBeNull();
  expect(sessionStorage.getItem('simple-product-save:' + COMPANY)).toBeNull();
});

it('requires purchase price for positive opening quantity before any write', async () => {
  renderSimpleProduct(); const user = await fillProduct();
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '3');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('Enter Purchase price to value opening stock.')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Purchase price' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Purchase price' })).toHaveFocus();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});

it('retries an uncertain Save with the original body and key', async () => {
  const original = replies(); let count = 0;
  api.mockImplementation(async (endpoint, request) => {
    if (request.path === base && ++count === 1) throw { status: 503, message: 'Connection interrupted' };
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('Connection interrupted')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Product name' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Retry Save' }));
  await screen.findByText(/active and ready/);
  const writes = api.mock.calls.filter(([, request]) => request.path === base).map(([, request]) => request);
  expect(writes).toHaveLength(2); expect(writes[0]).toEqual(writes[1]);
});

it('resumes the saved job after a reload without creating another product', async () => {
  sessionStorage.setItem('simple-product-save:' + COMPANY, ID);
  const original = replies(); api.mockImplementation((endpoint, request) => request.path.endsWith('/by-key/' + ID) ? Promise.resolve(saved as never) : original(endpoint, request));
  renderSimpleProduct(); await screen.findByText(/active and ready/);
  expect(api.mock.calls.some(([, request]) => request.path === base)).toBe(false);
});

it.each([401, 403, 500])('fails closed when form configuration cannot load (%s)', async status => {
  api.mockRejectedValue({ status, message: 'Product access is denied' });
  renderSimpleProduct(); expect(await screen.findByText('Product access is denied')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Save product' })).toBeNull();
});

it('allows only the bounded creation routes through the proxy', () => {
  expect(allowedSimpleProductRequest('GET', base + '/options?kind=SERVICE')).toBe(true);
  expect(allowedSimpleProductRequest('GET', base + '/options?kind=OTHER')).toBe(false);
  expect(allowedSimpleProductRequest('POST', base)).toBe(true);
  expect(allowedSimpleProductRequest('POST', base + '/' + ID + '/advance')).toBe(true);
  expect(allowedSimpleProductRequest('GET', base + '/by-key/' + ID)).toBe(true);
  expect(allowedSimpleProductRequest('DELETE', base + '/' + ID)).toBe(false);
  expect(allowedSimpleProductRequest('POST', base + '/' + ID + '/advance?company_id=' + COMPANY)).toBe(false);
});

it('keeps the form locked when recovery is unavailable and resumes the same saved job', async () => {
  sessionStorage.setItem('simple-product-save:' + COMPANY, ID);
  const original = replies(); let recovered = false;
  api.mockImplementation((endpoint, request) => {
    if (request.path.endsWith('/by-key/' + ID)) {
      if (!recovered) { recovered = true; return Promise.reject({ status: 503, message: 'Recovery temporarily unavailable' }); }
      return Promise.resolve(saved as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); await screen.findByText('Recovery temporarily unavailable');
  expect(await screen.findByRole('textbox', { name: 'Product name' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Retry Save' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.some(([, request]) => request.path === base)).toBe(false);
});

it('allows correction only when the owner confirms no product was created', async () => {
  const original = replies(); let corrected = false;
  api.mockImplementation((endpoint, request) => {
    if (request.path.endsWith('/advance') && !corrected) return Promise.reject({ status: 422, message: 'Check the product name' });
    if (request.path.includes('/by-key/')) return Promise.resolve({ ...saved, can_edit: true, row_version: 2 } as never);
    if (request.method === 'PATCH') { corrected = true; return Promise.resolve({ ...saved, row_version: 3 } as never); }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await user.click(await screen.findByRole('button', { name: 'Correct details' }));
  await user.clear(screen.getByRole('textbox', { name: 'Product name' }));
  await user.type(screen.getByRole('textbox', { name: 'Product name' }), 'Corrected tea');
  await user.click(screen.getByRole('button', { name: 'Save corrected product' }));
  await screen.findByText(/active and ready/);
  const correction = api.mock.calls.find(([, request]) => request.method === 'PATCH')![1];
  expect(correction.body).toMatchObject({ expected_version: 2, product: { name: 'Corrected tea' } });
  expect(api.mock.calls.filter(([, request]) => request.path === base)).toHaveLength(1);
});

it('disables Save when a required native field is protected', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions();
      options.fields.find(field => field.key === 'name')!.writable = false;
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); await screen.findByText(/field access does not allow all required/);
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
});

it('requires configured Brand before sending a product', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(); options.configuration.options.brand_mode = 'REQUIRED';
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('Brand is required.')).toBeVisible();
  expect(screen.getByRole('combobox', { name: /Brand/ })).toHaveFocus();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});

it('blocks a required Model that field access does not allow editing', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(); options.configuration.options.model_mode = 'REQUIRED';
      options.fields.find(field => field.key === 'model_code')!.writable = false;
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); await screen.findByRole('textbox', { name: 'Model' });
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  expect(screen.getByText(/field access does not allow all required/)).toBeVisible();
});

it('explains positive opening stock when Purchase price is unavailable', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(); options.fields = options.fields.filter(field => field.key !== 'purchase_price');
      options.configuration.pricing.purchase_reference_mode = 'DISABLED';
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '2');
  expect(await screen.findByText(/Opening stock needs an editable Purchase price/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '0');
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
});

it('protects code-only changes without marking the suggested group dirty', async () => {
  renderSimpleProduct(); await screen.findByDisplayValue('Default');
  const initial = new Event('janso:before-company-change', { cancelable: true });
  window.dispatchEvent(initial); expect(initial.defaultPrevented).toBe(false);
  await userEvent.type(screen.getByRole('textbox', { name: 'Product code' }), 'TEA001');
  const changed = new Event('janso:before-company-change', { cancelable: true });
  window.dispatchEvent(changed); expect(changed.defaultPrevented).toBe(true);
});

it('disables Type when its field has conditional access', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(); options.fields.find(field => field.key === 'kind')!.conditional_access = true;
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); expect(await screen.findByRole('combobox', { name: 'Type' })).toBeDisabled();
});

it('preserves return navigation after saving and when creating another product', async () => {
  renderSimpleProduct('/masters'); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  for (const link of screen.getAllByRole('link', { name: 'Back to products' })) expect(link).toHaveAttribute('href', '/masters');
  expect(screen.getByRole('link', { name: 'Create another product' })).toHaveAttribute('href', '/masters/items/new?returnTo=%2Fmasters');
  expect(screen.getByRole('region', { name: 'Product saved' })).toHaveFocus();
});

it('shows custom field server errors beside the input and focuses it', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions();
      return Promise.resolve({ ...options, fields: [...options.fields, {
        key: 'custom_fields.cf_note', label: 'Product note', source: 'custom', visible: true, writable: true, required: false, order: 100,
        custom: { key: 'cf_note', data_type: 'text', is_active: true, is_immutable_after_create: false, validation: { required: false }, choices: [] },
      }] } as never);
    }
    if (request.path === base) return Promise.reject({ status: 422, message: 'Check additional information', fields: { 'custom_fields.cf_note': 'Use a shorter product note.' } });
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Product note' }), 'A note');
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('Use a shorter product note.')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Product note' })).toHaveFocus();
});

it('explains a retained posting that takes longer than the foreground wait', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  try {
    const original = replies();
    api.mockImplementation((endpoint, request) => request.path.endsWith('/advance')
      ? Promise.resolve({ ...saved, step: 'FINALIZE' } as never) : original(endpoint, request));
    renderSimpleProduct(); const user = await fillProduct();
    await user.click(screen.getByRole('button', { name: 'Save product' }));
    await screen.findByText('Posting opening stock…');
    vi.setSystemTime(Date.now() + 61000);
    expect(await screen.findByText(/Product setup is saved and still processing/, {}, { timeout: 3000 })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry Save' })).toBeEnabled();
    expect(api.mock.calls.filter(([, request]) => request.path === base)).toHaveLength(1);
  } finally { vi.useRealTimers(); }
});

it('shows all missing basic and GST fields before any write', async () => {
  api.mockImplementation(replies(true)); renderSimpleProduct();
  await screen.findByDisplayValue('Default');
  await userEvent.click(screen.getByRole('button', { name: 'Save product' }));
  for (const label of ['Product name', 'Base unit', 'HSN', 'GST treatment / rate']) expect(screen.getByLabelText(label)).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('textbox', { name: 'Product name' })).toHaveFocus();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});

it('saves configured Brand, series, Model, MRP and GST in the one Save', async () => {
  const original = replies(true);
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) return Promise.resolve(configuredSimpleOptions() as never);
    const label = request.path.includes('/tax-classifications?') ? 'Tea classification'
      : request.path.includes('/tax-rules?') ? 'GST 18 percent'
      : request.path.includes('catalog.brand_series?') ? 'Tea series'
      : request.path.includes('catalog.brands?') ? 'Tea brand' : null;
    if (label) return Promise.resolve({ items: [{ id: ID, label, code: 'TEA' }], page: { has_more: false } } as never);
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  for (const [field, option] of [['Brand', 'Tea brand'], ['Brand series', 'Tea series'], ['HSN', 'Tea classification'], ['GST treatment / rate', 'GST 18 percent']]) {
    await user.click(screen.getByRole('combobox', { name: field! }));
    await user.click(await screen.findByRole('option', { name: new RegExp(option!) }));
  }
  expect(screen.getByRole('combobox', { name: 'HSN' })).toHaveValue('TEA · Tea classification');
  expect(screen.getByRole('combobox', { name: 'GST treatment / rate' })).toHaveValue('TEA · GST 18 percent');
  for (const [field, value] of [['Model', 'Classic'], ['Purchase price', '12.50'], ['Selling price', '20.00'], ['MRP', '25.00']]) await user.type(screen.getByRole('textbox', { name: field! }), value!);
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).toMatchObject({
    brand_id: ID, series_id: ID, model_code: 'Classic', mrp: '25.00', purchase_price: '12.50', sale_price: '20.00',
    tax: { classification_id: ID, rule_id: ID, directions: ['SALE', 'PURCHASE'] },
  });
  const series = api.mock.calls.find(([, request]) => request.path.includes('catalog.brand_series?'))![1];
  expect(new URL(series.path, 'http://test').searchParams.get('parent_id')).toBe(ID);
  const tax = api.mock.calls.find(([, request]) => request.path.includes('/tax-rules?'))![1];
  expect(new URL(tax.path, 'http://test').searchParams.get('item_kind')).toBe('GOODS');
});

it('validates exact decimal amounts and opening quantity together', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(); options.configuration.pricing.mrp_mode = 'OPTIONAL';
      options.fields.push({ ...options.fields[0]!, key: 'mrp', label: 'MRP' });
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  for (const [field, value] of [['Purchase price', '12.34567'], ['Selling price', '-1'], ['MRP', '0'], ['Opening quantity', '2.00001']]) {
    await user.clear(screen.getByRole('textbox', { name: field! }));
    await user.type(screen.getByRole('textbox', { name: field! }), value!);
  }
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  for (const label of ['Purchase price', 'Selling price', 'MRP', 'Opening quantity']) expect(screen.getByLabelText(label)).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('textbox', { name: 'Purchase price' })).toHaveFocus();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});

it('validates shared custom fields and saves a searched custom reference', async () => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions();
      const field = { source: 'custom', visible: true, writable: true, required: false, order: 100 };
      const custom = { is_active: true, is_immutable_after_create: false, validation: { required: false }, choices: [] };
      return Promise.resolve({ ...options, fields: [...options.fields,
        { ...field, key: 'custom_fields.cf_group', label: 'Custom group', custom: { ...custom, key: 'cf_group', data_type: 'dynamic_select', option_source_key: 'catalog.item_group' } },
        { ...field, key: 'shared_custom_fields.cf_note', label: 'Shared note', required: true, custom: { ...custom, key: 'cf_note', data_type: 'text', validation: { required: true } } },
      ] } as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('textbox', { name: 'Shared note' })).toHaveFocus();
  await user.type(screen.getByRole('textbox', { name: 'Shared note' }), 'Organic');
  await user.type(screen.getByRole('combobox', { name: 'Custom group' }), 'Nu');
  await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).toMatchObject({ custom_fields: { cf_group: UNIT }, shared_custom_fields: { cf_note: 'Organic' } });
  const lookup = api.mock.calls.find(([, request]) => request.path.includes('/option-sources/catalog.item_group?'))![1];
  expect(new URL(lookup.path, 'http://test').searchParams.get('as_of')).toBe('2026-11-04');
});

it('recovers configuration loading without losing the creation screen', async () => {
  const original = replies(); let failed = false;
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?') && !failed) { failed = true; return Promise.reject({ status: 500, message: 'Settings temporarily unavailable' }); }
    return original(endpoint, request);
  });
  renderSimpleProduct(); await screen.findByText('Settings temporarily unavailable');
  await userEvent.click(screen.getByRole('button', { name: 'Retry loading settings' }));
  expect(await screen.findByRole('textbox', { name: 'Product name' })).toBeEnabled();
  expect(screen.queryByText('Settings temporarily unavailable')).toBeNull();
});

it('keeps a rejected Save locked until its recovery lookup succeeds', async () => {
  const original = replies(); let lookup = 0;
  api.mockImplementation((endpoint, request) => {
    if (request.path === base) return Promise.reject({ status: 409, message: 'Check saved progress' });
    if (request.path.includes('/by-key/')) return ++lookup === 1
      ? Promise.reject({ status: 503, message: 'Recovery unavailable' }) : Promise.resolve(saved as never);
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText('Check saved progress');
  expect(screen.getByRole('textbox', { name: 'Product name' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Retry Save' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.filter(([, request]) => request.path === base)).toHaveLength(1);
});

it.each([true, false])('does not silently discard entered opening stock after field access changes (visible=%s)', async visible => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions();
      if (new URL(request.path, 'http://test').searchParams.get('group_id') === UNIT) Object.assign(options.fields.find(field => field.key === 'opening_quantity')!, { writable: false, visible });
      return Promise.resolve(options as never);
    }
    return original(endpoint, request);
  });
  renderSimpleProduct(); const user = await fillProduct();
  await user.type(screen.getByRole('textbox', { name: 'Purchase price' }), '12.50');
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '3');
  await user.click(screen.getByRole('combobox', { name: 'Product group' }));
  await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  if (visible) {
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toBeDisabled());
    expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveValue('3');
  } else await waitFor(() => expect(screen.queryByRole('textbox', { name: 'Opening quantity' })).toBeNull());
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  expect(screen.getByText(/field access does not allow all required/)).toBeVisible();
});

it.each(['SERVICE', 'NO_INVENTORY'])('does not send opening stock for %s', async scenario => {
  const original = replies();
  api.mockImplementation((endpoint, request) => {
    if (request.path.includes('/options?')) {
      const options = simpleOptions(new URL(request.path, 'http://test').searchParams.get('kind')!);
      options.inventory_enabled = scenario !== 'NO_INVENTORY';
      return Promise.resolve(options as never);
    }
    if (request.path.endsWith('/advance')) return Promise.resolve({ ...saved, status: 'COMPLETE', step: 'COMPLETE', opening_posted: false } as never);
    return original(endpoint, request);
  });
  renderSimpleProduct();
  if (scenario === 'SERVICE') {
    await userEvent.clear(await screen.findByRole('textbox', { name: 'Opening quantity' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '3');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  }
  const user = await fillProduct();
  expect(screen.queryByRole('group', { name: 'Opening stock' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === base)![1].body;
  expect(body).not.toHaveProperty('opening_quantity');
  expect(body).not.toHaveProperty('opening_date');
  expect(screen.queryByText(/Opening stock has been posted/)).toBeNull();
});
