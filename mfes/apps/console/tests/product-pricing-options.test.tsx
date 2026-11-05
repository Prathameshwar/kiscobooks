import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductPricingOptions } from '../app/components/ProductPricingOptions';
import { serviceCall } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';
import type { ConfigField } from '../app/lib/product-configuration';
import { COMPANY, DRAFT, REVISION, draft, revision, metadata, response } from './product-configuration-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const names = { multiple_price_levels_mode: 'Multiple selling-price levels', unit_prices_mode: 'Separate unit/pack prices', quantity_tiers_mode: 'Quantity-slab prices', channel_prices_mode: 'Sales-channel prices', additional_currencies_mode: 'Additional pricing currencies', formula_prices_mode: 'Formula prices' };
const starter = Object.fromEntries(Object.keys(names).map(key => [key, 'DISABLED']));
const fields: ConfigField[] = Object.entries(names).map(([key, label], order) => ({ key, label, source: 'native', visible: true, writable: true, required: true, conditional_access: false, order, display_group: 'pricing_options', control: { kind: 'select', label, choices: ['INHERIT', 'DISABLED', 'ENABLED'].map(value => ({ value, label: value === 'INHERIT' ? 'Use system default' : value === 'ENABLED' ? 'Enabled' : 'Disabled' })) } }));
function wrap(node: React.ReactNode) { return render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{node}</DisplayConfigProvider></PermissionProvider>); }
function reply(path: string, method?: string) {
  if (path.includes('/entities/catalog.product_pricing_policy/')) return { company_id: COMPANY, entity_type: 'catalog.product_pricing_policy', source_version: 7, configuration_complete: true, fields: [...metadata.pricing, ...fields] };
  if (path.includes('/product-configuration-revisions/')) return { ...revision, pricing: { ...revision.pricing, ...starter } };
  if (path.includes('/product-configurations/')) return { ...draft, row_version: method === 'PATCH' ? 4 : 3, pricing: { ...draft.pricing, ...starter } };
  return response(path, method);
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => reply(request.path, request.method) as never); });

it('shows the six published pricing options using native labels and saved values', async () => {
  wrap(<ProductPricingOptions company={COMPANY} revisionId={REVISION} />);
  expect(await screen.findByText('Quantity-slab prices')).toBeVisible();
  expect(screen.getAllByText('Disabled')).toHaveLength(6);
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
});

it('edits a pricing option while preserving the other starter settings', async () => {
  wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />);
  const tiers = await screen.findByRole('combobox', { name: 'Quantity-slab prices' });
  expect(tiers).toHaveValue('DISABLED');
  expect(screen.getByText('Additional pricing options')).toBeVisible();
  await userEvent.selectOptions(tiers, 'ENABLED');
  await userEvent.click(screen.getByRole('button', { name: 'Save draft changes' }));
  await waitFor(() => expect(goTo).toHaveBeenCalled());
  const write = vi.mocked(serviceCall).mock.calls.find(([, request]) => request.method === 'PATCH');
  expect(write?.[1].body).toMatchObject({ pricing: { quantity_tiers_mode: 'ENABLED' } });
  expect((write?.[1].body as { pricing: object }).pricing).toEqual({ quantity_tiers_mode: 'ENABLED' });
});

it('keeps a protected pricing option visible but disabled', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    const value = reply(request.path, request.method);
    return request.path.includes('/entities/catalog.product_pricing_policy/') ? { ...value, fields: [...metadata.pricing, ...fields.map(field => ({ ...field, writable: field.key !== 'formula_prices_mode' }))] } as never : value as never;
  });
  wrap(<ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" />);
  expect(await screen.findByRole('combobox', { name: 'Formula prices' })).toBeDisabled();
});

it('does not describe protected or absent saved values as disabled', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/product-configuration-revisions/') ? revision as never : reply(request.path, request.method) as never);
  wrap(<ProductPricingOptions company={COMPANY} revisionId={REVISION} />);
  expect(await screen.findByText('No readable pricing options in this revision.')).toBeVisible();
  expect(screen.queryByText('Disabled')).not.toBeInTheDocument();
});
