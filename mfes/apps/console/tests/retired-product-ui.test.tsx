import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import InventoryPage from '../app/inventory/[[...segments]]/page';
import { ProductExperience } from '../app/components/ProductExperience';
import { useProductMode } from '../app/components/ProductModeProvider';
import { companyMastersFor } from '../app/lib/company-masters';
import { masterReferencePath, masterReturnQuery } from '../app/lib/master-navigation';
import { productImportProfile } from '../app/lib/master-import-profiles';
import { COMPANY, RECORD, access } from './product-classification-fixtures';
import { sessionFor } from './helpers';

vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/SimpleProductDirectory', () => ({ SimpleProductDirectory: () => <p>Simple product list</p> }));
beforeEach(() => vi.clearAllMocks());

it.each([false, true])('preserves the directory in product mode %s', advanced => {
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: { company_id: COMPANY, product_family_sku_enabled: advanced, row_version: 1, policy_generation: 1 }, loading: false, failure: null, refresh: vi.fn() });
  render(<ProductExperience company={COMPANY} access={access} initialQuery="" canImport><p>SKU product list</p></ProductExperience>);
  expect(screen.getByText(advanced ? 'SKU product list' : 'Simple product list')).toBeVisible();
  expect(screen.queryByRole('link', { name: /New product|Edit|View product/ })).toBeNull();
});

it.each(['batches', 'serials'])('rejects retired %s pages through the inventory catch-all', async kind => {
  for (const tail of [[], ['new'], [RECORD], [RECORD, 'edit'], [RECORD, 'history']]) {
    await expect(InventoryPage({ params: Promise.resolve({ segments: [kind, ...tail] }) })).rejects.toThrow('not found');
  }
});

it('omits tracking pages from the company master navigation even with read access', async () => {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'Company' };
  session.grants = [{ scope_type: 'company', scope_id: COMPANY, valid_from: '2020-01-01', valid_to: null, permissions: ['item.read', 'accounting.batch.read', 'accounting.serial.read', 'accounting.stock.read'] }];
  const links = companyMastersFor(session).flatMap(group => group.items);
  expect(links.some(link => link.href === '/inventory/stock')).toBe(true);
  expect(links.some(link => /^\/inventory\/(batches|serials)/.test(link.href))).toBe(false);
});

it('does not generate product record links from references, return paths or import results', () => {
  for (const source of ['items', 'product-families']) {
    expect(masterReferencePath(source, RECORD)).toBeNull();
    for (const tail of ['new', RECORD, RECORD + '/edit', RECORD + '/created']) {
      const result = masterReturnQuery(new URL('/masters/' + source + '/' + tail, 'https://console.invalid'));
      if (source === 'items' && tail === 'new') expect(result).not.toBeNull();
      else expect(result).toBeNull();
    }
    expect(masterReturnQuery(new URL('/masters/' + source, 'https://console.invalid'))).not.toBeNull();
  }
  for (const resource of ['item', 'product_family', 'simple_product']) expect(productImportProfile.destination(resource, RECORD, '/masters/items')).toBeNull();
  expect(masterReferencePath('brands', RECORD)).toBe('/masters/brands/' + RECORD);
});
