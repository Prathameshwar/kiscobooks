import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AdvancedOpeningReviewStep } from '../app/components/AdvancedOpeningReviewStep';
import { newWork, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { emptyBusiness, putBusiness } from '../app/lib/advanced-product-business';
import { emptyOpening, putOpening } from '../app/lib/advanced-product-opening';
import { masterRequest } from '../app/lib/catalog-master-api';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
const ID = '55555555-5555-4555-8555-555555555555';
const options = { company_id: COMPANY, today: '2026-11-07', currency: 'INR', books_begin_date: '2026-04-01', inventory_enabled: true,
  selected_type: { inventory_modes: ['STOCK'] }, batch: { available: true, required: false },
  defaults: { configuration: { pricing: { purchase_reference_mode: 'OPTIONAL', sale_price_mode: 'OPTIONAL', mrp_mode: 'OPTIONAL' }, profiles: { inventory_template_revision_id: ID } } },
  family_fields: { fields: [{ key: 'name', visible: true }, { key: 'code', visible: true }, { key: 'brand_id', visible: true }] }, sku_fields: { fields: [{ key: 'base_unit_id', visible: true }] },
  attribute_members: [{ definition_id: ID, name: 'Weight', value_type: 'DECIMAL' }], sale_price_levels: [] } as unknown as AdvancedOptions;

it('shows readable references, typed variants and all captured batch pricing facts', async () => {
  vi.mocked(masterRequest).mockImplementation(async request => request.path.includes('/product-configuration/options/')
    ? { items: [{ value: ID, label: 'Stock policy revision 1' }] } as never
    : { id: ID, company_id: COMPANY, name: 'Beverages', code: 'BEV' } as never);
  const initial = newWork();
  initial.profile.name = 'Tea'; initial.profile.group_id = ID;
  initial.skus[0]!.attributes = [{ definition_id: ID, value_type: 'DECIMAL', value_decimal: '12.5' }];
  let work = putBusiness(initial, initial.skus[0]!, { ...emptyBusiness(), batch_enabled: true });
  work = putOpening(work, work.skus[0]!, { ...emptyOpening(), decision: 'OPEN', opening_date: '2026-04-01', batches: [{ key: 'batch', code: 'LOT1', opening_quantity: '2', purchase_price: '10', purchase_reference: '11', sale_prices: {}, manufactured_on: '', expires_on: '', mrp: '20', serials: [] }] });
  render(<AdvancedOpeningReviewStep company={COMPANY} work={work} options={options} errors={{}} disabled={false} onChange={vi.fn()} onEdit={vi.fn()} />);
  expect(await screen.findByText('Beverages')).toBeVisible();
  expect(await screen.findByText('Stock policy revision 1')).toBeVisible();
  expect(screen.getByText(/Weight: 12.5/)).toBeVisible();
  expect(screen.getByText(/Purchase reference: INR 11/)).toBeVisible();
  expect(screen.getByText(/Physical MRP: INR 20/)).toBeVisible();
  expect(document.body.textContent).not.toContain(ID);
});

it('does not duplicate an inline opening quantity error', async () => {
  const initial = newWork();
  const work = putOpening(initial, initial.skus[0]!, { ...emptyOpening(), decision: 'OPEN', opening_date: '2026-04-01' });
  render(<AdvancedOpeningReviewStep company={COMPANY} work={work} options={options} errors={{ 'opening.skus.0.opening_quantity': 'Enter a positive opening quantity.' }} disabled={false} onChange={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getAllByText('Enter a positive opening quantity.')).toHaveLength(1);
  await screen.findByText('Stock policy revision 1');
});

it('keeps batch errors visible when they do not belong to an individual input', async () => {
  const initial = newWork();
  let work = putBusiness(initial, initial.skus[0]!, { ...emptyBusiness(), batch_enabled: true });
  work = putOpening(work, work.skus[0]!, { ...emptyOpening(), decision: 'OPEN', batches: [{ key: 'batch', code: 'LOT1', opening_quantity: '2', purchase_price: '10', sale_prices: {}, manufactured_on: '', expires_on: '', mrp: '', serials: [] }] });
  render(<AdvancedOpeningReviewStep company={COMPANY} work={work} options={options} errors={{ 'opening.skus.0.batches.0': 'This batch could not be prepared.' }} disabled={false} onChange={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getByText('This batch could not be prepared.')).toBeVisible();
  await screen.findByText('Stock policy revision 1');
});

it('reviews a Service with no opening stock and preserves a typed false variant', () => {
  const work = newWork(); work.profile.kind = 'SERVICE';
  work.skus[0]!.attributes = [{ definition_id: ID, value_type: 'BOOLEAN', value_boolean: false }];
  const serviceOptions = { ...options, defaults: { ...options.defaults, configuration: { ...options.defaults.configuration, profiles: {} } }, attribute_members: [{ definition_id: ID, name: 'On site', value_type: 'BOOLEAN' }] } as unknown as AdvancedOptions;
  render(<AdvancedOpeningReviewStep company={COMPANY} work={work} options={serviceOptions} errors={{}} disabled={false} onChange={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.getByText(/Opening stock is unavailable for this Service/)).toBeVisible();
  expect(screen.getByText('On site: No')).toBeVisible();
  expect(screen.getAllByText('Not applicable')).toHaveLength(2);
});

it('omits a hidden Profile field from review even when an older draft retains its value', () => {
  const work = newWork(); work.profile.description = 'Previously entered description';
  const hiddenOptions = { ...options, defaults: { ...options.defaults, configuration: { ...options.defaults.configuration, profiles: {} } } } as AdvancedOptions;
  render(<AdvancedOpeningReviewStep company={COMPANY} work={work} options={hiddenOptions} errors={{}} disabled={false} onChange={vi.fn()} onEdit={vi.fn()} />);
  expect(screen.queryByText(/Previously entered description/)).not.toBeInTheDocument();
});
