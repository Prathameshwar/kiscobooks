import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, simpleOptions } from './simple-product-ready-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
const root = `/v1/companies/${COMPANY}/simple-product-creations`;
const UNIT = '33333333-3333-4333-8333-333333333333';
const saved = { id: UNIT, company_id: COMPANY, status: 'RUNNING', step: 'CREATE', code: 'TEA123', row_version: 1, item_id: null, opening_posted: false };
beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear(); });

it('keeps progress prominent from submission through failure, continuation and confirmed success', async () => {
  let accept: (value: unknown) => void = () => {};
  let fail: (value: unknown) => void = () => {};
  let drives = 0;
  api.mockImplementation(async (_service, request) => {
    if (request.path.includes('/options?')) return simpleOptions(new URL(request.path, 'http://test').searchParams.get('kind')!) as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    if (request.path.includes('/option-sources/')) return { items: [{ id: UNIT, value: UNIT, label: 'Numbers', code: 'NOS' }], page: { has_more: false } } as never;
    if (request.path === root) return new Promise(resolve => { accept = resolve; }) as never;
    if (request.path.endsWith('/drive')) {
      drives += 1;
      if (drives === 1) return new Promise((_resolve, reject) => { fail = reject; }) as never;
      return { ...saved, status: 'COMPLETE', step: 'COMPLETE', item_id: UNIT } as never;
    }
    if (request.path === root + '/' + UNIT) return saved as never;
    throw { status: 404, message: 'Missing fixture' };
  });
  render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>);
  const user = userEvent.setup({ delay: null });
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Type' }), 'SERVICE');
  await user.type(await screen.findByRole('textbox', { name: 'Product name' }), 'Tea service');
  await user.click(screen.getByRole('combobox', { name: /Base unit/ }));
  await user.click(await screen.findByRole('option', { name: /Numbers/ }));
  await user.click(screen.getByRole('button', { name: 'Save product' }));
  const progress = await screen.findByRole('region', { name: 'Product creation progress' });
  expect(progress).toHaveAttribute('data-variant', 'panel');
  expect(within(progress).getByRole('progressbar')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Product name' })).toBeDisabled();
  accept(saved);
  await waitFor(() => expect(drives).toBe(1));
  fail({ status: 503, message: 'Temporarily unavailable. Try again.' });
  await screen.findByText('Creation needs attention');
  expect(within(progress).queryByRole('progressbar')).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Continue creation' }));
  const result = await screen.findByRole('region', { name: 'Product saved' });
  expect(result).toHaveFocus();
  expect(within(result).getByRole('status')).toHaveTextContent('Product TEA123 is active and ready.');
  expect(within(result).getByRole('link', { name: 'Create another product' })).toBeVisible();
  expect(api.mock.calls.filter(([, request]) => request.path === root)).toHaveLength(1);
});
