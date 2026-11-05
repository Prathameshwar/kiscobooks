import { act, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { InventoryOverview } from '../app/components/InventoryOverview';
import { inventoryGroups } from '../app/lib/inventory-navigation';
import { masterLink, masterReturn } from '../app/lib/master-navigation';
import { structureLink, structureReturn } from '../app/lib/warehouse-structure';
import { configBack } from '../app/lib/product-configuration';
import {
  CatalogMasterDirectory,
  masterReturnTo,
} from '../app/components/CatalogMasterDirectory';
import { masterConfig } from '../app/lib/catalog-masters';
import { masterRequest } from '../app/lib/catalog-master-api';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/catalog-master-api', async (importActual) => ({
  ...(await importActual<typeof import('../app/lib/catalog-master-api')>()),
  masterRequest: vi.fn(),
}));
const id = '01990000-0000-7000-8000-000000000001';
async function reader(keys: string[]) {
  const session = await sessionFor({ permissions: keys });
  session.company = { id, name: 'Retail' };
  session.grants = [
    {
      scope_type: 'company',
      scope_id: id,
      permissions: keys,
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  return session;
}
it.each(inventoryGroups)(
  'opens permitted cards and explicit parent navigation for $label',
  async (group) => {
    const session = await reader([group.items[0]!.permission]);
    await renderWithProviders(
      <InventoryOverview
        session={session}
        context={companyContextFor()}
        groupKey={group.key}
      />,
    );
    expect(
      screen.getByRole('heading', { name: group.label }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Back to inventory masters' }),
    ).toHaveAttribute('href', '/inventory');
    const links = within(
      document.querySelector('.janso-action-card-grid') as HTMLElement,
    ).getAllByRole('link');
    expect(links).toHaveLength(
      group.items.filter(
        (item) => item.permission === group.items[0]!.permission && item.href !== '/masters/product-families',
      ).length,
    );
    for (const link of links)
      expect(
        new URL(
          link.getAttribute('href')!,
          'https://console.invalid',
        ).searchParams.get('returnTo'),
      ).toBe(group.href);
  },
);
it('shows only readable groups on the inventory overview', async () => {
  const session = await reader(['brand.read', 'unit.read']);
  await renderWithProviders(
    <InventoryOverview session={session} context={companyContextFor()} />,
  );
  expect(
    screen.getByRole('link', { name: 'Products and classification' }),
  ).toHaveAttribute('href', '/inventory/products');
  expect(
    screen.getByRole('link', { name: 'Units and identifiers' }),
  ).toHaveAttribute('href', '/inventory/units-identifiers');
  expect(
    screen.queryByRole('link', { name: 'Pricing' }),
  ).not.toBeInTheDocument();
});
it.each(['other-company', 'department', 'expired', 'none'])(
  'withholds master cards under %s authority',
  async (authority) => {
    const session = await reader(['brand.read']);
    if (authority === 'other-company') session.grants![0]!.scope_id = 'other';
    if (authority === 'department')
      session.grants![0]!.scope_type = 'department';
    if (authority === 'expired') session.grants![0]!.valid_to = '2020-01-01';
    if (authority === 'none') session.grants = [];
    await renderWithProviders(
      <InventoryOverview
        session={session}
        context={companyContextFor()}
        groupKey="products"
      />,
    );
    expect(document.querySelector('.janso-action-card-grid')).toBeNull();
  },
);
it('offers the existing company picker when no company is open', async () => {
  const session = await reader(['brand.read']);
  session.company = { name: 'Select company' };
  await renderWithProviders(
    <InventoryOverview session={session} context={companyContextFor()} />,
  );
  expect(
    screen.getByRole('link', { name: 'See the companies you can open' }),
  ).toHaveAttribute('href', '/companies');
});
it.each(inventoryGroups)(
  'preserves the $label overview through filtered record links',
  (group) => {
    const directory = masterLink(group.items[0]!.href + '?q=Re', group.href);
    const detail = masterLink(group.items[0]!.href + '/' + id, directory);
    expect(
      masterReturn(
        new URL(detail, 'https://console.invalid').searchParams.get(
          'returnTo',
        )!,
      ),
    ).toBe(directory);
  },
);
it.each([
  '/inventory/missing',
  '/inventory/products/new',
  '/inventory/products?redirect=bad',
  '//evil.example',
  '/inventory/%2e%2e/settings',
])('rejects an unsupported inventory return %s', (value) => {
  expect(masterReturn(value, '/settings')).toBe('/settings');
  expect(structureReturn(value, '/settings')).toBe('/settings');
});
it('retains overview returns through warehouse structure and product configuration', () => {
  const link = structureLink(
    '/masters/warehouse-bins?warehouse_id=' + id,
    '/inventory/warehouses',
  );
  expect(
    structureReturn(
      new URL(link, 'https://console.invalid').searchParams.get('returnTo')!,
    ),
  ).toBe('/inventory/warehouses');
  expect(configBack('/inventory/products')).toBe('/inventory/products');
});
it('retains filters and the overview when normalizing a legacy master directory', () => {
  expect(
    masterReturnTo(
      masterConfig('manufacturers')!,
      '/masters/manufacturers?q=Re&returnTo=%2Finventory%2Fproducts',
    ),
  ).toContain('returnTo=%2Finventory%2Fproducts');
});
it('opens a generic master record with its directory and overview retained', async () => {
  vi.mocked(masterRequest).mockImplementation(
    async ({ path }) =>
      (path.includes('field-set')
        ? {
            fields: [{ key: 'name', source: 'native', visible: true }],
            entity_type: 'catalog.manufacturer',
            company_id: id,
          }
        : {
            items: [{ id, name: 'Acme' }],
            page: { limit: 50, has_more: false, next_cursor: null },
          }) as never,
  );
  await act(async () => {
    await renderWithProviders(
      <CatalogMasterDirectory
        company={id}
        config={masterConfig('manufacturers')!}
        canManage
        initialQuery="q=Ac&returnTo=%2Finventory%2Fproducts"
      />,
    );
  });
  const link = await screen.findByRole('link', { name: 'Acme' });
  const back = new URL(
    link.getAttribute('href')!,
    'https://console.invalid',
  ).searchParams.get('returnTo')!;
  expect(
    new URL(back, 'https://console.invalid').searchParams.get('returnTo'),
  ).toBe('/inventory/products');
  expect(
    screen.getByRole('link', { name: 'Back to previous page' }),
  ).toHaveAttribute('href', '/inventory/products');
});
