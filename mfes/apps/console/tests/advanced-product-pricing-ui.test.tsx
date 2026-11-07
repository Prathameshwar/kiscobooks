import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { AdvancedSetupStep } from '../app/components/AdvancedSetupStep';
import { AdvancedPriceInput } from '../app/components/AdvancedPriceInput';
import { AdvancedProductWizard } from '../app/components/AdvancedProductWizard';
import { businessErrors, putBusiness, emptyBusiness } from '../app/lib/advanced-product-business';
import { newWork, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { masterRequest } from '../app/lib/catalog-master-api';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
const PLAN = '55555555-5555-4555-8555-555555555555';
const configuration = { source_version: 1, pricing: { sale_price_mode: 'OPTIONAL', purchase_reference_mode: 'OPTIONAL', mrp_mode: 'OPTIONAL' }, profiles: {} };
const options = { company_id: COMPANY, today: '2026-11-07', currency: 'INR', defaults: { configuration }, sale_price_levels: [{ plan_id: PLAN, price_level_id: PLAN, name: 'Retail', tax_basis: 'INCLUSIVE', required: true }], price_levels_accessible: true } as unknown as AdvancedOptions;

it('marks conditional reference requirements and explains sale tax basis beside the amount', () => {
  const initial = newWork();
  const work = putBusiness(initial, initial.skus[0]!, { ...emptyBusiness(), purchase_amount: '10', mrp_amount: '20' });
  render(<AdvancedSetupStep company={COMPANY} work={work} options={options} errors={{}} disabled={false} onChange={vi.fn()} />);
  expect(screen.getByRole('textbox', { name: 'Purchase source reference' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'MRP jurisdiction' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'MRP source reference' })).toBeRequired();
  expect(screen.getByRole('textbox', { name: 'Retail selling price' })).toBeRequired();
  expect(screen.getByText(/Includes tax/)).toBeVisible();
});

it('explains an unavailable optional selling price instead of leaving an empty grid', () => {
  render(<AdvancedSetupStep company={COMPANY} work={newWork()} options={{ ...options, sale_price_levels: [], price_levels_accessible: false }} errors={{}} disabled={false} onChange={vi.fn()} />);
  expect(screen.getByText(/Selling prices are unavailable with your current access/)).toBeVisible();
});

it('reports reference errors on the actual missing source and jurisdiction fields', () => {
  const initial = newWork();
  const work = putBusiness(initial, initial.skus[0]!, { ...emptyBusiness(), purchase_amount: '10', mrp_amount: '20' });
  const errors = businessErrors(work, options);
  expect(errors['business.skus.0.purchase_source']).toMatch(/source/i);
  expect(errors['business.skus.0.mrp_source']).toMatch(/source/i);
  expect(errors['business.skus.0.mrp_jurisdiction']).toMatch(/jurisdiction/i);
  expect(errors['business.skus.0.purchase_amount']).toBeUndefined();
});

it('reports an unstorable visible amount so the wizard cannot submit an earlier valid value', async () => {
  const report = vi.fn(), change = vi.fn();
  render(<AdvancedPriceInput label="Test amount" path="business.skus.0.purchase_amount" value="" unit="INR" onChange={change} onNumericProblem={report} />);
  await userEvent.type(screen.getByRole('textbox', { name: 'Test amount' }), '12.34567');
  await waitFor(() => expect(report).toHaveBeenCalledWith('business.skus.0.purchase_amount', 'Up to 4 decimal places.'));
  expect(change).not.toHaveBeenCalledWith('12.34567');
});

it('blocks draft saving and step navigation until an invalid visible price is corrected', async () => {
  sessionStorage.clear();
  const mode = { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true };
  const work = newWork(); work.profile.name = 'Tea';
  const draft = { id: PLAN, company_id: COMPANY, step: 3, row_version: 1, updated_at: '', needs_review: false, content: { profile: work.profile, skus: work.skus } };
  const rootOptions = { ...options, kind: 'GOODS', mode, defaults: { ...options.defaults, configuration: { ...configuration, options: { category_mode: 'DISABLED', manufacturer_mode: 'DISABLED' } } },
    family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', fields: [], source_version: 1 }, sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', fields: [], source_version: 1 } };
  vi.mocked(masterRequest).mockImplementation(async request => request.path.includes('/options?') ? rootOptions as never : request.path.endsWith('/drafts') ? [draft] as never : draft as never);
  render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Open latest draft' }));
  const amount = await screen.findByRole('textbox', { name: 'Purchase reference amount' });
  await user.type(amount, '12.34567');
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Continue to opening and review' })).toBeDisabled();
  await user.clear(amount);
  await user.type(amount, '12.3456');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled());
});
