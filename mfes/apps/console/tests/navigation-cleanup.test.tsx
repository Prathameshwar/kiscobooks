import { screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ConsoleShell } from '../app/components/ConsoleShell';
import { ProductCatalogNavigation } from '../app/components/ProductCatalogCommon';
import { flattenNavigation, navigationFor, navSections } from '../app/nav';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  authActionUrl: (path: string) => path,
}));
const companyId = '01990000-0000-7000-8000-000000000001';
async function scoped(
  keys: string[],
  scope: 'tenant' | 'company' | 'department' = 'company',
) {
  const session = await sessionFor({ permissions: keys });
  session.company = { id: companyId, name: 'Retail' };
  session.grants = [
    {
      scope_type: scope,
      scope_id: scope === 'tenant' ? null : companyId,
      permissions: keys,
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  return session;
}
it('removes unimplemented destinations from the menu catalogue', () => {
  for (const path of [
    '/invoices',
    '/payments',
    '/ledgers',
    '/stock',
    '/customers',
  ]) {
    expect(
      flattenNavigation(navSections.flatMap((section) => section.items)).some(
        (item) => item.href === path,
      ),
    ).toBe(false);
  }
});
it('offers a single Masters entry for a narrowly authorized inventory reader', async () => {
  const session = await scoped(['brand.read']);
  const items = navigationFor(session).find(
    (section) => section.label === 'Administer',
  )!.items;
  expect(items.find(item => item.href === '/masters')?.children).toBeUndefined();
  expect(items.find(item => item.href === '/masters')?.label).toBe('Masters');
  expect(flattenNavigation(items).map((item) => item.href)).not.toContain(
    '/masters/items',
  );
  expect(items.some((item) => item.href === '/inventory/pricing')).toBe(false);
});
it('labels the organisation entry Administration and preserves its access gate', async () => {
  const session = await scoped(['company.read']);
  const entry = navigationFor(session).flatMap(section => section.items).find(item => item.href === '/organisation');
  expect(entry?.label).toBe('Administration');
  expect(entry?.children?.some(item => item.href === '/companies/manage')).toBe(true);
  expect(navigationFor(await scoped([])).flatMap(section => section.items).some(item => item.href === '/organisation')).toBe(false);
});
it('opens the Reports submenu and highlights the selected category', async () => {
  const session = await scoped(['report.read', 'brand.read']);
  await renderWithProviders(<ConsoleShell session={session} context={companyContextFor()} activeHref="/reports/inventory"><p>Inventory reports landing</p></ConsoleShell>);
  expect(screen.getByRole('link', { name: 'Inventory reports' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: 'Finance reports' })).toHaveAttribute('href', '/reports/finance');
  expect(screen.getByRole('link', { name: 'Masters' })).toHaveAttribute('href', '/masters');
});
it('offers tenant notifications without an open company and rejects company or department delegation', async () => {
  const tenant = await scoped(['notification.template.read'], 'tenant');
  tenant.company = { name: 'Select company' };
  expect(flattenNavigation(navigationFor(tenant).flatMap(section => section.items)).find(item => item.href === '/settings/notifications')?.label).toBe('Notifications');
  expect(
    flattenNavigation(
      navigationFor(tenant).flatMap((section) => section.items),
    ).map((item) => item.href),
  ).toContain('/settings/notifications');
  for (const scope of ['company', 'department'] as const) {
    const session = await scoped(['notification.template.read'], scope);
    expect(
      flattenNavigation(
        navigationFor(session).flatMap((section) => section.items),
      ).map((item) => item.href),
    ).not.toContain('/settings/notifications');
  }
});
it.each(['platform.tenant_access.read', 'platform.notification_delivery.read'])(
  'makes platform history reachable for %s',
  async (key) => {
    const session = await sessionFor({ permissions: [key] });
    expect(
      flattenNavigation(
        navigationFor(session).flatMap((section) => section.items),
      ).map((item) => item.href),
    ).toContain('/platform/history');
  },
);
it.each(['/masters/items', '/masters/items?status=ACTIVE'])(
  'highlights Masters on product directory route %s',
  async (activeHref) => {
    const session = await scoped(['item.read', 'attribute_definition.read']);
    await renderWithProviders(
      <ConsoleShell
        session={session}
        context={companyContextFor()}
        activeHref={activeHref}
      >
        <p>Attributes</p>
      </ConsoleShell>,
    );
    expect(
      screen.getByRole('link', { name: 'Masters' }),
    ).toHaveAttribute('aria-current', 'page');
  },
);
it('highlights company settings on a supplementary setup page', async () => {
  const session = await scoped(['company.read']);
  await renderWithProviders(
    <ConsoleShell
      session={session}
      context={companyContextFor()}
      activeHref="/settings/readiness"
    >
      <p>Setup</p>
    </ConsoleShell>,
  );
  expect(
    screen.getByRole('link', { name: 'Company settings' }),
  ).toHaveAttribute('aria-current', 'page');
});
it('links a main catalog directory to the Masters hub and preserves its previous-page destination', async () => {
  await renderWithProviders(
    <ProductCatalogNavigation title="Brands" access={{} as never} />,
  );
  expect(
    screen.getByRole('link', { name: 'Back to previous page' }),
  ).toHaveAttribute('href', '/inventory/products');
  expect(
    screen.getByRole('link', { name: 'Masters' }),
  ).toHaveAttribute('href', '/masters');
});
