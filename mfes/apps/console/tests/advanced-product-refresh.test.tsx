import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AdvancedProductWizard } from '../app/components/AdvancedProductWizard';
import { masterRequest } from '../app/lib/catalog-master-api';
import { useProductMode } from '../app/components/ProductModeProvider';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/ProductCatalogCustomFields', () => ({ ProductCatalogCustomFields: () => null }));
const GROUP = '55555555-5555-4555-8555-555555555555';
const REVISION = '44444444-4444-4444-8444-444444444444';
const mode = { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true };
const options = { company_id: COMPANY, kind: 'GOODS', mode, default_group_id: null, selected_type: null,
  defaults: { product_type_revision_id: null, configuration: { source_version: 9, options: { category_mode: 'DISABLED', manufacturer_mode: 'DISABLED' } } },
  family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', source_version: 7, fields: [{ key: 'name', label: 'Profile name', visible: true, writable: true }] },
  sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', source_version: 8, fields: [] } };

beforeEach(() => {
  sessionStorage.clear(); vi.clearAllMocks();
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: mode, loading: false, failure: null, refresh: vi.fn() });
});

it('retains the form, focus and entered text while a kind change refreshes options', async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.includes('/options?kind=SERVICE')) return await new Promise<unknown>(resolve => { finish = resolve; }) as never;
    if (request.path.includes('/options?')) return options as never;
    return [] as never;
  });
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  const user = userEvent.setup();
  const name = await screen.findByRole('textbox', { name: 'Profile name' });
  await user.type(name, 'Retained product');
  const kind = screen.getByRole('combobox', { name: 'Product kind' });
  await user.selectOptions(kind, 'SERVICE');
  await waitFor(() => expect(finish).toBeDefined());
  expect(screen.getByRole('textbox', { name: 'Profile name' })).toBe(name);
  expect(name).toHaveValue('Retained product');
  expect(kind).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Continue to SKUs' })).toBeDisabled();
  finish({ ...options, kind: 'SERVICE' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to SKUs' })).toBeEnabled());
  expect(kind).toHaveFocus();
});

it('applies defaults from the initial resolved options without requesting them again', async () => {
  vi.mocked(masterRequest).mockImplementation(async request => request.path.includes('/options?')
    ? { ...options, default_group_id: GROUP, defaults: { ...options.defaults, product_type_revision_id: REVISION } } as never
    : [] as never);
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('textbox', { name: 'Profile name' });
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Published Type revision' })).toHaveValue(REVISION));
  expect(vi.mocked(masterRequest).mock.calls.filter(([request]) => request.path.includes('/options?'))).toHaveLength(1);
});

it('cancels a pending change when returning to the already resolved kind', async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.includes('/options?kind=SERVICE')) return await new Promise<unknown>(resolve => { finish = resolve; }) as never;
    return request.path.includes('/options?') ? options as never : [] as never;
  });
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('textbox', { name: 'Profile name' });
  const user = userEvent.setup(), kind = screen.getByRole('combobox', { name: 'Product kind' });
  await user.selectOptions(kind, 'SERVICE');
  await waitFor(() => expect(finish).toBeDefined());
  await user.selectOptions(kind, 'GOODS');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to SKUs' })).toBeEnabled());
  finish({ ...options, kind: 'SERVICE' });
  expect(kind).toHaveValue('GOODS');
});

it('keeps access locked if company mode changes during an options refresh', async () => {
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.includes('/options?kind=SERVICE')) return await new Promise<never>(() => {}) as never;
    return request.path.includes('/options?') ? options as never : [] as never;
  });
  const view = render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('textbox', { name: 'Profile name' });
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Product kind' }), 'SERVICE');
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: { ...mode, row_version: 3 }, loading: false, failure: null, refresh: vi.fn() });
  view.rerender(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  expect(screen.getByRole('combobox', { name: 'Product kind' })).toBeDisabled();
  expect(screen.getByRole('combobox', { name: 'Product Type' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
});
