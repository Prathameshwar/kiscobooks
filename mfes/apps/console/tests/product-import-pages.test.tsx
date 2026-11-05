import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import ProductImportPage from '../app/masters/items/import/page';
import { ProductImport } from '../app/components/ProductImport';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { companyId, userId } from './access-fixtures';
import { JOB } from './product-import-fixtures';
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not found');
  },
}));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ProductImport', () => ({
  ProductImport: vi.fn(() => <p>Scoped product import</p>),
}));
beforeEach(async () => {
  vi.clearAllMocks();
  const session = await sessionFor({
    permissions: ['item.read', 'catalog.bulk.read', 'catalog.bulk.manage'],
  });
  session.company = { id: companyId, name: 'Test company' };
  session.grants = [
    {
      scope_type: 'company',
      scope_id: companyId,
      permissions: session.permissions,
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
});
it('opens product import using current scoped grants and a resumable job', async () => {
  render(
    await ProductImportPage({
      searchParams: Promise.resolve({
        job: JOB,
        returnTo: '/masters/items?q=Part',
      }),
    }),
  );
  expect(vi.mocked(ProductImport).mock.calls[0]![0]).toMatchObject({
    company: companyId,
    canManage: true,
    initialJob: JOB,
    returnTo: '/masters/items?q=Part',
  });
});
it('offers history without write controls for an import reader', async () => {
  (await pageContext()).session.grants![0]!.permissions = [
    'item.read',
    'catalog.bulk.read',
  ];
  render(
    await ProductImportPage({
      searchParams: Promise.resolve({ view: 'history' }),
    }),
  );
  expect(vi.mocked(ProductImport).mock.calls[0]![0]).toMatchObject({
    canManage: false,
    initialHistory: true,
  });
});
it.each([
  'other_company',
  'no_import_read',
  'no_product_read',
  'expired',
  'label_only',
])('denies import data for %s', async (reason) => {
  const data = await pageContext(),
    grant = data.session.grants![0]!;
  if (reason === 'other_company') grant.scope_id = userId;
  if (reason === 'no_import_read') grant.permissions = ['item.read'];
  if (reason === 'no_product_read') grant.permissions = ['catalog.bulk.read'];
  if (reason === 'expired') grant.valid_to = '2020-01-01';
  if (reason === 'label_only') {
    data.session.role = 'platform_admin';
    data.session.grants = [];
  }
  render(await ProductImportPage({}));
  expect(ProductImport).not.toHaveBeenCalled();
  expect(
    screen.getByText(
      'Product read and import read access are required for this company.',
    ),
  ).toBeVisible();
});
it('rejects an invalid import identifier before loading session data', async () => {
  await expect(
    ProductImportPage({ searchParams: Promise.resolve({ job: 'not-a-job' }) }),
  ).rejects.toThrow('not found');
  expect(pageContext).not.toHaveBeenCalled();
});
