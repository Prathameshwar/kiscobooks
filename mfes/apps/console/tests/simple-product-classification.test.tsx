import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, SCHEME, CATEGORY, MAKER, SITE, classificationOptions } from './simple-product-ready-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const base = `/v1/companies/${COMPANY}/simple-product-creations`;
const UNIT = '33333333-3333-4333-8333-333333333333';
const JOB = '22222222-2222-4222-8222-222222222222';
const OTHER_MAKER = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
let options = classificationOptions();
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear(); options = classificationOptions();
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/options?')) {
      const kind = new URL(request.path, 'http://test').searchParams.get('kind');
      return (kind === 'SERVICE' ? classificationOptions('OPTIONAL', false, 'SERVICE') : options) as never;
    }
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) {
      const choices = request.path.includes('catalog.category_schemes?') ? [[SCHEME, 'Product range']]
        : request.path.includes('catalog.item_categories?') ? [[CATEGORY, 'Tea']]
        : request.path.includes('catalog.manufacturers?') ? [[MAKER, 'Tea maker'], [OTHER_MAKER, 'Other maker']]
        : request.path.includes('catalog.manufacturer_sites?') ? [[SITE, 'Main plant']]
        : [[UNIT, 'Numbers']];
      return { items: choices.map(([id, label]) => ({ id, value: id, label })), page: { has_more: false } } as never;
    }
    if (request.path === base) return { id: JOB, company_id: COMPANY, code: 'TEA1234567', status: 'RUNNING', step: 'CREATE' } as never;
    if (request.path.endsWith('/advance')) return { id: JOB, company_id: COMPANY, code: 'TEA1234567', status: 'COMPLETE', step: 'COMPLETE' } as never;
    throw new Error('Unexpected classification request ' + request.path);
  });
});
const show = () => render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>);
const user = () => userEvent.setup({ delay: null });
async function choose(label: string, option: string) {
  await user().click(screen.getByRole('combobox', { name: label }));
  await user().click(await screen.findByRole('option', { name: option }));
}
async function fill() {
  await user().type(await screen.findByRole('textbox', { name: 'Product name' }), 'Tea');
  await choose('Base unit', 'Numbers');
}

it('collects enabled optional categories and manufacturer/site through the ready-product save', async () => {
  show(); await fill();
  for (const label of ['Categories', 'Manufacturer']) {
    expect(screen.getByRole('switch', { name: 'Use ' + label })).not.toBeChecked();
    await user().click(screen.getByRole('switch', { name: 'Use ' + label }));
  }
  expect(screen.getByRole('combobox', { name: 'Category 1' })).toBeDisabled();
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('combobox', { name: 'Manufacturer' })).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('combobox', { name: 'Category scheme 1' })).toHaveAttribute('aria-invalid', 'true');
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  await choose('Manufacturer', 'Tea maker'); await choose('Manufacturer site', 'Main plant');
  await choose('Category scheme 1', 'Product range'); await choose('Category 1', 'Tea');
  await user().click(screen.getByRole('switch', { name: 'Primary category 1' }));
  for (const [source, parent] of [['manufacturer_sites', MAKER], ['item_categories', SCHEME]]) {
    const request = api.mock.calls.find(([, request]) => request.path.includes('catalog.' + source + '?'))![1];
    expect(new URL(request.path, 'http://test').searchParams.get('parent_id')).toBe(parent);
  }
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  expect(api.mock.calls.find(([, request]) => request.path === base)![1].body).toMatchObject({
    manufacturer_id: MAKER, manufacturer_site_id: SITE,
    categories: [{ scheme_id: SCHEME, category_id: CATEGORY, is_primary: true }],
  });
});

it('prefills required schemes and locks required switches while validating missing selections', async () => {
  options = classificationOptions('REQUIRED'); show(); await fill();
  for (const label of ['Categories', 'Manufacturer']) {
    expect(screen.getByRole('switch', { name: 'Use ' + label })).toBeChecked();
    expect(screen.getByRole('switch', { name: 'Use ' + label })).toBeDisabled();
  }
  expect(screen.getByRole('combobox', { name: 'Category scheme 1' })).toHaveValue('Product range');
  expect(screen.getByRole('combobox', { name: 'Category scheme 1' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Remove category 1' })).toBeDisabled();
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(screen.getByRole('combobox', { name: 'Category 1' })).toHaveAttribute('aria-invalid', 'true');
  await choose('Manufacturer', 'Tea maker'); await choose('Category 1', 'Tea');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
});

it('resets a site when its manufacturer changes and omits details switched off', async () => {
  options = classificationOptions('OPTIONAL', true); show(); await fill();
  await choose('Manufacturer', 'Tea maker'); await choose('Manufacturer site', 'Main plant');
  await choose('Manufacturer', 'Other maker');
  expect(screen.getByRole('combobox', { name: 'Manufacturer site' })).toHaveValue('');
  await choose('Category scheme 1', 'Product range'); await choose('Category 1', 'Tea');
  await user().click(screen.getByRole('button', { name: 'Add category' }));
  await choose('Category scheme 2', 'Product range'); await choose('Category 2', 'Tea');
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  expect(await screen.findByText('This category is already selected.')).toBeVisible();
  await user().click(screen.getByRole('button', { name: 'Remove category 2' }));
  await user().click(screen.getByRole('switch', { name: 'Use Categories' }));
  await user().click(screen.getByRole('switch', { name: 'Use Manufacturer' }));
  await user().click(screen.getByRole('button', { name: 'Save product' }));
  await screen.findByText(/active and ready/);
  const body = api.mock.calls.find(([, request]) => request.path === base)![1].body;
  for (const key of ['categories', 'manufacturer_id', 'manufacturer_site_id']) expect(body).not.toHaveProperty(key);
});

it.each(['category_id', 'category_is_primary', 'manufacturer_id'])('blocks required entry when %s is read-only', async key => {
  options = classificationOptions('REQUIRED'); options.fields.find(field => field.key === key)!.writable = false;
  show(); await screen.findByRole('textbox', { name: 'Product name' });
  expect(screen.getByText(/field access does not allow all required/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
});

it('keeps a required category scheme enabled under an optional category setting', async () => {
  options = classificationOptions(); options.required_category_schemes = classificationOptions('REQUIRED').required_category_schemes;
  show(); await screen.findByDisplayValue('Product range');
  expect(screen.getByRole('switch', { name: 'Use Categories' })).toBeChecked();
  expect(screen.getByRole('switch', { name: 'Use Categories' })).toBeDisabled();
  expect(screen.getByRole('switch', { name: 'Use Manufacturer' })).not.toBeChecked();
});

it('hides category inputs denied for read and prevents optional entry without write access', async () => {
  options = classificationOptions('OPTIONAL', true);
  options.fields = options.fields.filter(field => !field.key.startsWith('category_'));
  options.fields.find(field => field.key === 'manufacturer_id')!.writable = false;
  show(); await screen.findByDisplayValue('Default');
  expect(screen.queryByRole('switch', { name: 'Use Categories' })).toBeNull();
  expect(screen.getByRole('switch', { name: 'Use Manufacturer' })).not.toBeChecked();
  expect(screen.getByRole('switch', { name: 'Use Manufacturer' })).toBeDisabled();
  expect(screen.queryByRole('combobox', { name: 'Manufacturer' })).toBeNull();
});

it('hides disabled sections and asks to clear manufacturer details after changing to Services', async () => {
  options = classificationOptions('DISABLED'); const view = show(); await fill();
  expect(screen.queryByRole('switch', { name: 'Use Categories' })).toBeNull();
  expect(screen.queryByRole('switch', { name: 'Use Manufacturer' })).toBeNull();
  view.unmount(); options = classificationOptions('OPTIONAL', true); show(); await fill();
  await choose('Manufacturer', 'Tea maker');
  await user().selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
  await screen.findByRole('button', { name: 'Clear unavailable details' });
  expect(screen.queryByRole('switch', { name: 'Use Manufacturer' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Save product' })).toBeDisabled();
  await user().click(screen.getByRole('button', { name: 'Clear unavailable details' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save product' })).toBeEnabled());
});
