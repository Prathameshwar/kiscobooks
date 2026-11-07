import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { AdvancedProfileStep } from '../app/components/AdvancedProfileStep';
import { AdvancedSetupStep } from '../app/components/AdvancedSetupStep';
import { AdvancedSkuStep } from '../app/components/AdvancedSkuStep';
import { AdvancedOpeningReviewStep } from '../app/components/AdvancedOpeningReviewStep';
import { fixture, id, PLAN } from './advanced-config-scenarios-fixtures';
import { businessSku } from '../app/lib/advanced-product-business';
import { openingSku } from '../app/lib/advanced-product-opening';
import { masterRequest } from '../app/lib/catalog-master-api';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
beforeEach(() => { vi.clearAllMocks(); vi.mocked(masterRequest).mockImplementation(async () => { throw { status: 403, message: 'Unavailable' }; }); });

it('shows configured requirements and removes only unavailable Profile values explicitly', async () => {
  const { work, options } = fixture(8), change = vi.fn();
  const view = render(<AdvancedProfileStep company={options.company_id} value={work.profile} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(screen.getByRole('combobox', { name: 'Brand' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Model code' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Profile code' })).toBeRequired();
  options.defaults.configuration.options.brand_mode = 'DISABLED';
  view.rerender(<AdvancedProfileStep company={options.company_id} value={work.profile} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(screen.getByRole('combobox', { name: 'Brand' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Remove unavailable Profile details' }));
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ brand_id: '', name: work.profile.name, model_code: 'MODEL-01', manufacturer_id: id(41) }));
});

it('preserves Goods details during a deliberate kind change until reviewed', async () => {
  const { work, options } = fixture(8), change = vi.fn();
  render(<AdvancedProfileStep company={options.company_id} value={work.profile} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  fireEvent.change(screen.getByRole('combobox', { name: 'Product kind' }), { target: { value: 'SERVICE' } });
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ kind: 'SERVICE', brand_id: id(40), manufacturer_id: id(41), model_code: 'MODEL-01' }));
});

it('allows explicit removal of disabled references while preserving allowed selling prices', async () => {
  const { work, options } = fixture(2), change = vi.fn();
  options.defaults.configuration.pricing.mrp_mode = 'DISABLED';
  render(<AdvancedSetupStep company={options.company_id} work={work} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(screen.queryByRole('textbox', { name: 'MRP' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Remove unavailable SKU details' }));
  const next = change.mock.calls[0]![0];
  expect(businessSku(next, next.skus[0])).toMatchObject({ mrp_amount: '', mrp_source: '', mrp_jurisdiction: '', purchase_amount: '85.00', sale_prices: { [PLAN]: '120.00' } });
});

it('refreshes per-unit defaults when the published source version changes', async () => {
  const { work, options } = fixture(7);
  vi.mocked(masterRequest).mockImplementation(async () => structuredClone(options.defaults) as never);
  const view = render(<AdvancedSetupStep company={options.company_id} work={work} options={options} onChange={vi.fn()} errors={{}} disabled={false} />);
  await act(async () => {});
  const count = () => vi.mocked(masterRequest).mock.calls.filter(([request]) => request.path.includes('/authoring-defaults?')).length;
  expect(count()).toBe(1);
  options.defaults.configuration.source_version++;
  view.rerender(<AdvancedSetupStep company={options.company_id} work={work} options={structuredClone(options)} onChange={vi.fn()} errors={{}} disabled={false} />);
  await waitFor(() => expect(count()).toBe(2));
});

it('rejects mismatched unit defaults and offers retry while keeping completed setup available', async () => {
  const { work, options } = fixture(7), ready = vi.fn();
  vi.mocked(masterRequest).mockImplementation(async () => ({ ...options.defaults, quantity: { ...options.defaults.quantity, unit_id: id(999) } }) as never);
  const view = render(<AdvancedSetupStep company={options.company_id} work={work} options={options} onChange={vi.fn()} onReadyChange={ready} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(ready).toHaveBeenLastCalledWith(false);
  expect(screen.getByRole('button', { name: 'Reload unit rules' })).toBeVisible();
  vi.mocked(masterRequest).mockImplementation(async () => structuredClone(options.defaults) as never);
  fireEvent.click(screen.getByRole('button', { name: 'Reload unit rules' }));
  await act(async () => {});
  expect(ready).toHaveBeenLastCalledWith(true);
  view.rerender(<AdvancedSetupStep company={options.company_id} work={work} options={options} onChange={vi.fn()} onReadyChange={ready} locked={[true]} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(ready).toHaveBeenLastCalledWith(true);
});

it('lets a single retained SKU remove its unavailable variant structure', async () => {
  const { work, options } = fixture(3), change = vi.fn();
  work.skus = [work.skus[0]!]; options.defaults.configuration.options.variants_mode = 'DISABLED';
  render(<AdvancedSkuStep company={options.company_id} work={work} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Remove unavailable variant structure' }));
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ axes: [], skus: [expect.objectContaining({ sku: 'SHIRT-0', attributes: [] })] }));
});

it('removes disabled batch MRP explicitly while preserving opening valuation', async () => {
  const { work, options } = fixture(5), change = vi.fn();
  options.defaults.configuration.pricing.mrp_mode = 'DISABLED';
  render(<AdvancedOpeningReviewStep company={options.company_id} work={work} options={options} onChange={change} onEdit={vi.fn()} errors={{}} disabled={false} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Remove unavailable opening details' }));
  const next = change.mock.calls[0]![0];
  expect(openingSku(next, next.skus[0]).batches[0]).toMatchObject({ mrp: '', opening_quantity: '10', purchase_price: '50.00', purchase_reference: '60.00' });
});

it('explains enabled extended pricing without inventing additional authoring inputs or values', async () => {
  const { work, options } = fixture(10);
  render(<AdvancedSetupStep company={options.company_id} work={work} options={options} onChange={vi.fn()} errors={{}} disabled={false} />);
  await act(async () => {});
  expect(screen.getByText(/Enabled options outside this creation form/)).toHaveTextContent('quantity tiers, channel prices, additional currencies, price formulas');
  expect(screen.getByText(/Enabled options outside this creation form/)).toHaveTextContent('creation does not generate them');
});

it('lets retained alternate units be cleared when unit capture becomes disabled', async () => {
  const { work, options } = fixture(7), change = vi.fn();
  options.defaults.configuration.options.alternate_units_mode = 'DISABLED';
  render(<AdvancedSkuStep company={options.company_id} work={work} options={options} onChange={change} errors={{}} disabled={false} />);
  await act(async () => {});
  fireEvent.click(screen.getByRole('button', { name: 'Clear unavailable units' }));
  expect(change).toHaveBeenCalledWith(expect.objectContaining({ skus: [expect.objectContaining({ base_unit_id: work.skus[0]!.base_unit_id, units: [] })] }));
});
