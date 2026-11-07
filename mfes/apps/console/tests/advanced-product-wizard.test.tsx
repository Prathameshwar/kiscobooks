import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { AdvancedProductWizard } from '../app/components/AdvancedProductWizard';
import { AdvancedProductChoice } from '../app/components/AdvancedProductChoice';
import { masterRequest } from '../app/lib/catalog-master-api';
import { useProductMode } from '../app/components/ProductModeProvider';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/ProductCatalogCustomFields', () => ({ ProductCatalogCustomFields: () => null }));
const mode = { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true };
const TYPE = '33333333-3333-4333-8333-333333333333';
const REVISION = '44444444-4444-4444-8444-444444444444';
const GROUP = '55555555-5555-4555-8555-555555555555';
const UNIT = '66666666-6666-4666-8666-666666666666';
const field = (key: string, label: string) => ({ key, label, source: 'native', visible: true, writable: true, conditional_access: false, required: ['name', 'code', 'sku', 'base_unit_id'].includes(key), order: 1 });
const options = { company_id: COMPANY, kind: 'GOODS', today: '2026-11-05', currency: 'INR', mode, default_group_id: null, selected_type: null, max_skus_per_draft: 64, defaults: { product_type_revision_id: null, configuration: { source_version: 9, options: { variants_mode: 'OPTIONAL' } } }, family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', source_version: 7, fields: [field('name', 'Profile name'), field('code', 'Profile code')] }, sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', source_version: 8, fields: [field('sku', 'SKU code'), field('name', 'SKU name'), field('base_unit_id', 'Base unit'), field('sellable', 'Sellable'), field('purchasable', 'Purchasable')] } };
const saved = { id: '22222222-2222-4222-8222-222222222222', company_id: COMPANY, row_version: 1, step: 1, updated_at: '2026-11-05T00:00:00Z', created_at: '2026-11-05T00:00:00Z', mode_version: 2, policy_generation: 4, source_version: 9, family_field_version: 7, sku_field_version: 8, needs_review: false, content: {} };
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: mode, loading: false, failure: null, refresh: vi.fn() });
  vi.mocked(masterRequest).mockImplementation(async request => {
    if (request.path.includes('/options?')) return { ...options, selected_type: request.path.includes('product_type_revision_id=') ? { id: REVISION, kind: 'GOODS', allow_variants: true, require_brand: false } : null } as never;
    if (request.path.endsWith('/drafts') && request.method === 'POST') return { ...saved, content: (request.body as { content: unknown }).content } as never;
    if (request.path.endsWith('/drafts')) return [] as never;
    if (request.path.includes('/product-types/' + TYPE + '/revisions?')) return { items: [{ id: REVISION, product_type_id: TYPE, revision: 1, status: 'PUBLISHED' }], page: { has_more: false } } as never;
    if (request.path.includes('/product-types?')) return { items: [{ id: TYPE, name: 'Tea goods', kind: 'GOODS', is_active: true }], page: { has_more: false } } as never;
    if (request.path.includes('/option-sources/catalog.item_groups?')) return { items: [{ id: GROUP, value: GROUP, label: 'Beverages' }], page: { has_more: false } } as never;
    if (request.path.includes('/option-sources/catalog.units?')) return { items: [{ id: UNIT, value: UNIT, label: 'Pieces' }], page: { has_more: false } } as never;
    throw new Error('Unexpected request: ' + request.path);
  });
});

it('shows four steps, focuses validation and saves incomplete work as a private draft', async () => {
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  expect(await screen.findByRole('heading', { name: 'Product Profile', level: 2 })).toBeVisible();
  expect(screen.getByText(/A SKU is one version/)).toBeVisible();
  expect(screen.getByRole('navigation', { name: 'Product creation steps' })).toBeVisible();
  expect(screen.getByRole('button', { name: /Business setup/ })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: 'Continue to SKUs' }));
  expect(screen.getByText('Check these fields before continuing')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Product Profile', level: 2 })).toBeVisible();
  await userEvent.type(screen.getByRole('textbox', { name: 'Profile name' }), 'Tea');
  await userEvent.type(screen.getByRole('textbox', { name: 'Profile code' }), 'TEA');
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(screen.getByText('Draft version 1')).toBeVisible());
  const request = vi.mocked(masterRequest).mock.calls.find(([input]) => input.method === 'POST')![0];
  expect(request.key).toBeTruthy();
  expect(request.body).toMatchObject({ mode_version: 2, source_version: 9, content: { profile: { name: 'Tea', code: 'TEA' }, skus: [{ sku: '' }] } });
});

it('freezes the mounted draft after a mode change', async () => {
  const view = render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('heading', { name: 'Product Profile', level: 2 });
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: { ...mode, row_version: 3, product_family_sku_enabled: false }, loading: false, failure: null, refresh: vi.fn() });
  view.rerender(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  expect(screen.getByText(/Product setup changed/)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
});

it('announces draft saving without describing it as product creation', async () => {
  const original = vi.mocked(masterRequest).getMockImplementation()!;
  let finish: () => void = () => {};
  vi.mocked(masterRequest).mockImplementation(request => request.path.endsWith('/drafts') && request.method === 'POST'
    ? new Promise(resolve => { finish = () => resolve({ ...saved, content: (request.body as { content: unknown }).content } as never); })
    : original(request));
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await userEvent.type(await screen.findByRole('textbox', { name: 'Profile name' }), 'Tea');
  await userEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(screen.getByRole('progressbar', { name: 'Saving your draft' })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Profile name' })).toBeDisabled();
  finish();
  await waitFor(() => expect(screen.queryByRole('progressbar')).toBeNull());
  expect(screen.getByRole('textbox', { name: 'Profile name' })).toHaveValue('Tea');
});

it('moves from a published Type and group to the explicit default SKU editor', async () => {
  const user = userEvent.setup();
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await user.type(await screen.findByRole('textbox', { name: 'Profile name' }), 'Tea');
  await user.type(screen.getByRole('textbox', { name: 'Profile code' }), 'TEA');
  await user.click(screen.getByRole('combobox', { name: 'Product Type' }));
  await user.click(await screen.findByRole('option', { name: 'Tea goods' }));
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Published Type revision' }), REVISION);
  await user.click(screen.getByRole('combobox', { name: 'Product group' }));
  await user.click(await screen.findByRole('option', { name: 'Beverages' }));
  await user.click(screen.getByRole('button', { name: 'Continue to SKUs' }));
  expect(await screen.findByRole('heading', { name: 'SKUs and units', level: 2 })).toBeVisible();
  expect(screen.getByRole('button', { name: /Default SKU/ })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'SKU code' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Add SKU' })).toBeDisabled();
  await user.click(screen.getByRole('combobox', { name: 'Base unit' }));
  await waitFor(() => expect(vi.mocked(masterRequest).mock.calls.some(([request]) =>
    request.path.includes('/option-sources/catalog.units?') &&
    request.path.includes(`product_type_revision_id=${REVISION}`)
  )).toBe(true));
});

it('asks Catalog for units permitted by the selected Product Type', async () => {
  render(<AdvancedProductChoice company={COMPANY} resource="units" label="Base unit" value="" productTypeRevisionId={REVISION} onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole('combobox', { name: 'Base unit' }));
  await waitFor(() => expect(vi.mocked(masterRequest).mock.calls.some(([request]) =>
    request.path.includes(`/option-sources/catalog.units?`) &&
    request.path.includes(`product_type_revision_id=${REVISION}`)
  )).toBe(true));
});
