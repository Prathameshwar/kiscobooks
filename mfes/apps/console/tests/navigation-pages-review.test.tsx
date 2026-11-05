import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import InventoryPage from '../app/inventory/[[...segments]]/page';
import CustomersPage from '../app/customers/page';
import SettingsPage from '../app/settings/page';
import PlatformHistoryPage from '../app/platform/history/page';
import PlatformPage from '../app/platform/page';
import PlatformAccessPage from '../app/platform/access/[[...segments]]/page';
import ProductFieldsPage from '../app/products/custom-fields/page';
import { TaxPage } from '../app/components/TaxPage';
import { NotificationPage } from '../app/components/NotificationPage';
import { CompanyYearPage } from '../app/components/CompanyYearPage';
import { redirect, notFound } from 'next/navigation';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('next/navigation', () => ({
  notFound: vi.fn(() => {
    throw new Error('404');
  }),
  redirect: vi.fn((path: string) => {
    throw new Error(path);
  }),
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({
    children,
    activeHref,
  }: {
    children: ReactNode;
    activeHref: string;
  }) => (
    <div data-testid="shell" data-active={activeHref}>
      {children}
    </div>
  ),
}));
vi.mock('../app/components/AuditEvents', () => ({
  AuditEvents: () => <p>Authorized history</p>,
}));
vi.mock('../app/components/NotificationAdmin', () => ({
  NotificationAdmin: () => <p>Notifications</p>,
}));
vi.mock('../app/components/ProductFields', () => ({
  ProductFields: () => <p>Product field controls</p>,
}));
const id = '01990000-0000-7000-8000-000000000001';
async function context(keys: string[] = []) {
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
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
  return session;
}
it.each([
  { segments: [] },
  { segments: ['products'] },
  { segments: ['warehouses'] },
])('renders a working inventory overview route %j', async ({ segments }) => {
  await context(['brand.read', 'warehouse_bin.read']);
  render(await InventoryPage({ params: Promise.resolve({ segments }) }));
  expect(screen.getByTestId('shell')).toHaveAttribute(
    'data-active',
    '/inventory' + (segments.length ? '/' + segments[0] : ''),
  );
  expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
});
it.each([{ segments: ['missing'] }, { segments: ['products', 'new'] }])(
  'rejects unsupported overview routes %j',
  async ({ segments }) => {
    await expect(
      InventoryPage({ params: Promise.resolve({ segments }) }),
    ).rejects.toThrow('404');
    expect(notFound).toHaveBeenCalled();
  },
);
it.each(['accounting.finance.read', 'accounting.charges.read'])(
  'keeps accounting settings reachable with only %s',
  async (key) => {
    await context([key]);
    render(await SettingsPage());
    expect(
      screen.getByRole('link', {
        name: 'Accounting configuration',
      }),
    ).toHaveAttribute('href', '/accounting?returnTo=%2Fsettings');
  },
);
it.each(['platform.tenant_access.read', 'platform.notification_template.read'])(
  'aligns platform overview and history for %s',
  async (key) => {
    await context([key]);
    const view = render(await PlatformPage());
    expect(
      screen.getByRole('link', { name: 'View platform history' }),
    ).toHaveAttribute('href', '/platform/history');
    view.unmount();
    render(await PlatformHistoryPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText('Authorized history')).toBeInTheDocument();
  },
);
it('does not render platform history without a platform event permission', async () => {
  await context(['audit.read']);
  render(await PlatformHistoryPage({ searchParams: Promise.resolve({}) }));
  expect(screen.queryByText('Authorized history')).not.toBeInTheDocument();
});
it.each(['role', 'permissions', 'administrators'])(
  'passes the actual platform access submenu %s to the shell',
  async (part) => {
    await context();
    render(
      await PlatformAccessPage({
        params: Promise.resolve({ segments: [part] }),
        searchParams: Promise.resolve({}),
      }),
    );
    expect(screen.getByTestId('shell')).toHaveAttribute(
      'data-active',
      '/platform/access/' + part,
    );
  },
);
it('passes a deep tax workflow to the shell for the rates submenu', async () => {
  await context();
  render(await TaxPage({ segments: ['rates', 'series', 'new'] }));
  expect(screen.getByTestId('shell')).toHaveAttribute(
    'data-active',
    '/tax/rates/series/new',
  );
});
it.each(['tenant', 'platform'] as const)(
  'passes a supplementary %s notification route to the shell',
  async (owner) => {
    await context();
    render(await NotificationPage({ owner, route: ['templates', id] }));
    expect(screen.getByTestId('shell')).toHaveAttribute(
      'data-active',
      (owner === 'platform' ? '/platform' : '/settings') +
        '/notifications/templates/' +
        id,
    );
  },
);
it('passes financial years to the shell under company settings', async () => {
  await context();
  render(await CompanyYearPage({ companyId: id }));
  expect(screen.getByTestId('shell')).toHaveAttribute(
    'data-active',
    '/companies/' + id + '/years',
  );
});
it('withholds product field controls when the permission belongs to a different company', async () => {
  const session = await context(['item.read']);
  session.grants![0]!.scope_id = 'other';
  render(await ProductFieldsPage({}));
  expect(screen.queryByText('Product field controls')).not.toBeInTheDocument();
});
it.each([
  [{}, '/accounting/parties?role=CUSTOMER'],
  [
    { name: 'Acme Limited' },
    '/accounting/parties?role=CUSTOMER&q=Acme+Limited',
  ],
  [
    { q: ['invalid', 'duplicate'], name: 'A' },
    '/accounting/parties?role=CUSTOMER',
  ],
])(
  'routes legacy customers to the implemented party directory',
  async (query, target) => {
    await expect(
      CustomersPage({ searchParams: Promise.resolve(query) }),
    ).rejects.toThrow(target);
    expect(redirect).toHaveBeenCalledWith(target);
  },
);
