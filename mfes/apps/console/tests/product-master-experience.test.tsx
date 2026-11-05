import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCatalogDirectory } from '../app/components/ProductCatalogDirectory';
import { ProductCatalogDetail } from '../app/components/ProductCatalogDetail';

import { ProductCatalogField } from '../app/components/ProductCatalogCommon';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, RECORD, SOURCE, access, fields, record, response, resetFixtures } from './product-classification-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/masters/items');
  api.mockImplementation(async (_, request) => response(request) as never);
});
const directory = (props = {}) =>
  render(
    <ProductCatalogDirectory
      company={COMPANY}
      config={masterConfig('items')!}
      canManage
      access={access}
      {...props}
    />,
  );
it('does not offer product merging on classification detail pages', async () => {
  render(
    <ProductCatalogDetail
      company={COMPANY}
      config={masterConfig('brands')!}
      id={RECORD}
      canManage
      access={access}
    />,
  );
  await screen.findByRole('heading', { level: 1, name: record('brands').name });
  expect(
    screen.queryByRole('button', { name: 'Merge products' }),
  ).not.toBeInTheDocument();
});
it('keeps permitted product imports and directory context without a create action', async () => {
  directory({ canImport: true, initialQuery: 'q=Part' });
  await screen.findByRole('heading', { level: 1, name: 'Products / SKUs' });
  const link = screen.getByRole('link', { name: 'Import products' });
  expect(screen.queryByRole('link', { name: 'New product' })).toBeNull();
  expect(link).not.toHaveAttribute('aria-disabled');
  const url = new URL(link.getAttribute('href')!, 'https://console.invalid');
  expect(url.pathname).toBe('/masters/items/import');
  expect(url.searchParams.get('returnTo')).toContain('q=Part');
});
it('marks the current product area using routed navigation styling', async () => {
  directory();
  await screen.findByRole('button', { name: 'Actions for Standard SKU' });
  const navigation = screen.getByRole('navigation', {
    name: 'Products and classification',
  });
  expect(
    within(navigation).getByRole('link', { name: 'Products / SKUs' }),
  ).toHaveAttribute('aria-current', 'page');
  expect(navigation).toHaveClass('janso-tabs');
});
it('does not load the directory until field authority is available', async () => {
  api.mockImplementation(async (_, request) =>
    request.path.includes('/field-set')
      ? await new Promise<never>(() => {})
      : (response(request) as never),
  );
  directory();
  await screen.findByRole('table');
  expect(
    api.mock.calls.filter(([, request]) => request.path.includes('/items?')),
  ).toHaveLength(0);
  expect(screen.queryByText('No records')).not.toBeInTheDocument();
});
it('shows directory failure without suggesting that the company has no products', async () => {
  api.mockImplementation(async (_, request) => {
    if (request.path.includes('/items?'))
      throw { status: 503, message: 'Product directory unavailable' };
    return response(request) as never;
  });
  directory();
  await screen.findByText('Product directory unavailable');
  expect(
    screen.queryByRole('link', { name: 'Create first record' }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText('No products / skus')).not.toBeInTheDocument();
  expect(screen.queryByText('No records')).not.toBeInTheDocument();
});
it('rejects a returned directory record from another company', async () => {
  api.mockImplementation(async (_, request) => {
    const value = response(request);
    return request.path.includes('/items?')
      ? ({
          ...(value as object),
          items: [{ ...record('items'), company_id: SOURCE }],
        } as never)
      : (value as never);
  });
  directory();
  await screen.findByText('The directory record could not be verified.');
  expect(
    screen.queryByRole('link', { name: 'Standard SKU' }),
  ).not.toBeInTheDocument();
});
it('does not offer editing for discontinued products', async () => {
  api.mockImplementation(async (_, request) => {
    const value = response(request);
    return request.path.includes('/items?')
      ? ({
          ...(value as object),
          items: [{ ...record('items'), status: 'DISCONTINUED' }],
        } as never)
      : (value as never);
  });
  directory();
  await userEvent.click(
    await screen.findByRole('button', { name: 'Actions for Standard SKU' }),
  );
  expect(
    screen.queryByRole('menuitem', { name: 'Edit details' }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: 'View details' })).toBeNull();
});
it('offers secondary reference filters without crowding the main toolbar', async () => {
  directory();
  const summary = await screen.findByText('More filters');
  expect(summary.closest('details')).not.toHaveAttribute('open');
  await userEvent.click(summary);
  expect(
    screen.getByRole('combobox', { name: 'Product family' }),
  ).toBeVisible();
});
it('associates description guidance and requiredness with the textarea', () => {
  const field = fields('catalog.product_family', 'create').find(
    (field) => field.key === 'description',
  )!;
  render(
    <ProductCatalogField
      company={COMPANY}
      field={{
        ...field,
        required: true,
        help_text: 'Describe this product for your team.',
      }}
      values={{ description: '' }}
      access={access}
      onChange={vi.fn()}
    />,
  );
  const input = screen.getByRole('textbox', { name: 'Description' });
  expect(input).toBeRequired();
  expect(input).toHaveAccessibleDescription(
    'Describe this product for your team.',
  );
});
it('explains the product code format before a validation error occurs', () => {
  const field = fields('catalog.product_family', 'create').find(
    (field) => field.key === 'code',
  )!;
  render(
    <ProductCatalogField
      company={COMPANY}
      field={field}
      values={{ code: '' }}
      access={access}
      onChange={vi.fn()}
    />,
  );
  expect(
    screen.getByRole('textbox', { name: 'Code' }),
  ).toHaveAccessibleDescription(expect.stringContaining('uppercase'));
});
it('associates checkbox help with its control', () => {
  const field = fields('catalog.item', 'create').find(
    (field) => field.key === 'sellable',
  )!;
  render(
    <ProductCatalogField
      company={COMPANY}
      field={{ ...field, help_text: 'Allow this SKU on sales documents.' }}
      values={{ sellable: true }}
      access={access}
      onChange={vi.fn()}
    />,
  );
  expect(
    screen.getByRole('checkbox', { name: 'Sellable' }),
  ).toHaveAccessibleDescription('Allow this SKU on sales documents.');
});
