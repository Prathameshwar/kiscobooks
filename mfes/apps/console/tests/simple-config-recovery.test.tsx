import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, simpleOptions } from './simple-product-ready-fixtures';

const mode = vi.hoisted(() => ({ enabled: false }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: mode.enabled } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const root = `/v1/companies/${COMPANY}/simple-product-creations`;
const UNIT = '33333333-3333-4333-8333-333333333333';
const ID = '22222222-2222-4222-8222-222222222222';
const saved = { id: ID, company_id: COMPANY, status: 'RUNNING', step: 'CREATE', row_version: 1, code: 'SIMCONFIG1', opening_posted: false };
let options: ReturnType<typeof simpleOptions>;
beforeEach(() => {
  sessionStorage.clear(); mode.enabled = false; options = simpleOptions(); api.mockReset();
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/options?')) return options as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) return { items: [{ id: UNIT, label: 'Piece' }], page: { has_more: false } } as never;
    if (request.path === root || request.path.includes('/by-key/')) return saved as never;
    if (request.path.endsWith('/drive')) return { ...saved, status: 'COMPLETE', step: 'COMPLETE' } as never;
    throw { status: 404, message: 'No command' };
  });
});
function show() { return render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>); }
it('gates Simple creation when Advanced mode is enabled', async () => {
  mode.enabled = true; show();
  expect(screen.getByText(/Simple product creation is available when that mode is disabled/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Save product' })).toBeNull();
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});
async function fill() {
  const user = userEvent.setup({ delay: null });
  await user.type(await screen.findByRole('textbox', { name: 'Product name' }), 'Simulation');
  await user.click(screen.getByRole('combobox', { name: 'Base unit' }));
  await user.click(await screen.findByRole('option', { name: 'Piece' }));
  return user;
}
it('does not drive an unverified recovered company', async () => {
  sessionStorage.setItem('simple-product-save:' + COMPANY, ID);
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, init) => request.path.includes('/by-key/')
    ? Promise.resolve({ ...saved, company_id: GROUP } as never) : original(endpoint, request, init));
  show();
  await screen.findByText(/could not be verified/);
  expect(api.mock.calls.some(([, request]) => request.path.endsWith('/drive'))).toBe(false);
  expect(sessionStorage.getItem('simple-product-save:' + COMPANY)).toBe(ID);
});
it('does not drive an unverified initial company response', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, init) => request.path === root
    ? Promise.resolve({ ...saved, company_id: GROUP } as never) : original(endpoint, request, init));
  show(); const user = await fill(); await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/could not be verified/);
  expect(api.mock.calls.some(([, request]) => request.path.endsWith('/drive'))).toBe(false);
});
it('does not retry posting an editable rejected command on reload', async () => {
  sessionStorage.setItem('simple-product-save:' + COMPANY, ID);
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, init) => request.path.includes('/by-key/')
    ? Promise.resolve({ ...saved, can_edit: true } as never) : original(endpoint, request, init));
  show();
  await screen.findByRole('button', { name: 'Correct details' });
  expect(api.mock.calls.some(([, request]) => request.path.endsWith('/drive'))).toBe(false);
});
it.each([false, true])('S10 blocks required inaccessible custom data (conditional %s)', async conditional => {
  options.fields.push({ ...options.fields[0]!, key: 'custom_fields.cf_private', label: 'Required private note', source: 'custom', required: true,
    writable: conditional, conditional_access: conditional,
    custom: { key: 'cf_private', data_type: 'text', is_active: true, validation: { required: true }, choices: [] },
  } as never);
  show(); const user = await fill(); await user.click(screen.getByRole('button', { name: 'Save product' }));
  expect(api.mock.calls.some(([, request]) => request.path === root)).toBe(false);
  await waitFor(() => expect(screen.getByText(/access is required to continue/)).toBeVisible());
});
it('clears retained opening quantity when refreshed inventory settings disable stock', async () => {
  show(); const user = await fill();
  await user.type(screen.getByRole('textbox', { name: 'Opening unit cost' }), '80');
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '20');
  options = { ...options, inventory_enabled: false, fields: options.fields.filter(field => !['opening_quantity', 'opening_unit_cost'].includes(field.key)) };
  await user.click(screen.getByRole('combobox', { name: 'Product group' }));
  await user.click(await screen.findByRole('option', { name: 'Piece' }));
  await user.click(await screen.findByRole('button', { name: 'Clear unavailable details' }));
  await user.click(screen.getByRole('combobox', { name: 'Base unit' }));
  await user.click(await screen.findByRole('option', { name: 'Piece' }));
  expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === root)![1].body).not.toHaveProperty('opening_quantity');
});
it('reselecting the current group preserves the unit and does not refresh configuration', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, init) => request.path.includes('/option-sources/catalog.item_groups?')
    ? Promise.resolve({ items: [{ id: GROUP, label: 'Default' }], page: { has_more: false } } as never) : original(endpoint, request, init));
  show(); const user = await fill();
  const requests = api.mock.calls.filter(([, request]) => request.path.includes('/options?')).length;
  await user.click(screen.getByRole('combobox', { name: 'Product group' }));
  await user.click(await screen.findByRole('option', { name: /Default/ }));
  expect(screen.getByRole('combobox', { name: 'Base unit' })).toHaveValue('Piece');
  expect(api.mock.calls.filter(([, request]) => request.path.includes('/options?'))).toHaveLength(requests);
});
it('changing to Services preserves incompatible Goods stock until explicitly cleared', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((endpoint, request, init) => {
    if (request.path.includes('/options?') && request.path.includes('kind=SERVICE')) return Promise.resolve({ ...options, kind: 'SERVICE',
      fields: options.fields.filter(field => !['opening_quantity', 'opening_unit_cost'].includes(field.key)),
    } as never);
    return original(endpoint, request, init);
  });
  show(); const user = await fill();
  await user.clear(screen.getByRole('textbox', { name: 'Opening quantity' }));
  await user.type(screen.getByRole('textbox', { name: 'Opening quantity' }), '20');
  await user.type(screen.getByRole('textbox', { name: 'Opening unit cost' }), '80');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  await screen.findByRole('button', { name: 'Clear unavailable details' });
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Type' })).toBeEnabled());
  await user.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'GOODS');
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Opening quantity' })).toHaveValue('20'));
  expect(screen.getByRole('textbox', { name: 'Opening unit cost' })).toHaveValue('80');
});
