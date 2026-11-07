import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AdvancedProfileStep } from '../app/components/AdvancedProfileStep';
import { AdvancedProductChoice } from '../app/components/AdvancedProductChoice';
import { masterRequest } from '../app/lib/catalog-master-api';
import { newWork, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/components/ProductCatalogCustomFields', () => ({ ProductCatalogCustomFields: () => null }));
const ID = '55555555-5555-4555-8555-555555555555';
it('uses readable native labels, preserves custom labels and gives Description multiple lines', () => {
  const work = newWork();
  const options = { family_fields: { fields: ['name', 'brand_id', 'model_code', 'description'].map(key => ({ key, label: key === 'model_code' ? 'Supplier model' : key, visible: true, writable: true })) },
    defaults: { configuration: { options: { category_mode: 'DISABLED', manufacturer_mode: 'DISABLED' } } } } as unknown as AdvancedOptions;
  render(<AdvancedProfileStep company={COMPANY} value={work.profile} options={options} errors={{}} disabled={false} onChange={vi.fn()} />);
  expect(screen.getByRole('textbox', { name: 'Profile name' })).toBeVisible();
  expect(screen.getByRole('combobox', { name: 'Brand' })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Supplier model' })).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Description' }).tagName).toBe('TEXTAREA');
});

it('resolves a restored selection through a scoped detail read instead of displaying its ID', async () => {
  vi.mocked(masterRequest).mockResolvedValue({ id: ID, company_id: COMPANY, name: 'Beverages' } as never);
  render(<AdvancedProductChoice company={COMPANY} resource="item_groups" label="Product group" value={ID} onChange={vi.fn()} />);
  expect(await screen.findByDisplayValue('Beverages')).toBeVisible();
  expect(masterRequest).toHaveBeenCalledWith(expect.objectContaining({ path: `/v1/companies/${COMPANY}/item-groups/${ID}` }));
});

it('does not display a label returned for another company', async () => {
  vi.mocked(masterRequest).mockResolvedValue({ id: ID, company_id: 'other-company', name: 'Private brand' } as never);
  render(<AdvancedProductChoice company={COMPANY} resource="brands" label="Brand" value={ID} onChange={vi.fn()} />);
  expect(await screen.findByDisplayValue('Selection unavailable')).toBeVisible();
  expect(screen.queryByDisplayValue('Private brand')).not.toBeInTheDocument();
});
