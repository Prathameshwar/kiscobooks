import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ProductCatalogDirectory } from '../app/components/ProductCatalogDirectory';
import { allowedClassificationRequest } from '../app/lib/product-classification-policy';
import { masterConfig } from '../app/lib/catalog-masters';
import { serviceCall } from '../app/lib/service-call';
import {
  access,
  COMPANY,
  SOURCE,
  RECORD,
  resetFixtures,
  response,
} from './product-classification-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const api = vi.mocked(serviceCall);
beforeEach(() => {
  vi.clearAllMocks();
  resetFixtures();
  window.history.replaceState(null, '', '/');
  api.mockImplementation(
    async (_endpoint, request) => response(request) as never,
  );
});
it('uses the native product type revision filter on product family lists', async () => {
  render(
    <ProductCatalogDirectory
      company={COMPANY}
      config={masterConfig('product-families')!}
      canManage
      access={access}
      initialQuery={'product_type_revision_id=' + SOURCE}
    />,
  );
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.includes('/product-families?') &&
          request.path.includes('product_type_revision_id=' + SOURCE),
      ),
    ).toBe(true),
  );
  expect(
    allowedClassificationRequest(
      'GET',
      `/v1/companies/${COMPANY}/product-families?type_revision_id=${SOURCE}`,
    ),
  ).toBe(false);
});
it('loads draft product families with their native status lifecycle for SKU filtering', async () => {
  api.mockImplementation(async (_endpoint, request) => {
    if (
      request.path.includes('/product-families?') &&
      request.path.includes('is_active=')
    )
      throw { status: 422, message: 'Unknown native family query field' };
    return response(request) as never;
  });
  render(
    <ProductCatalogDirectory
      company={COMPANY}
      config={masterConfig('items')!}
      canManage
      access={access}
    />,
  );
  await userEvent.click(
    await screen.findByRole('combobox', { name: 'Product family' }),
  );
  const option = await screen.findByRole('option', {
    name: /Standard product family/,
  });
  expect(option).not.toHaveAttribute('aria-disabled', 'true');
  await userEvent.click(option);
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.includes('/items?') &&
          request.path.includes('family_id=' + RECORD),
      ),
    ).toBe(true),
  );
});
it('rejects unsupported path casing and mixed family kinds without throwing', () => {
  expect(
    allowedClassificationRequest('GET', `/v1/companies/${COMPANY}/ITEMS`),
  ).toBe(false);
  expect(
    allowedClassificationRequest(
      'GET',
      `/v1/companies/${COMPANY}/product-families?kind=BOTH`,
    ),
  ).toBe(false);
});
