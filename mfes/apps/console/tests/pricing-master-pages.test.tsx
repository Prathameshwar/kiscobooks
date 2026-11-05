import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import { masterConfig } from '../app/lib/catalog-masters';
import { pricingResources } from '../app/lib/pricing-resources';
import { flattenNavigation, navigationFor } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';
import { COMPANY, RECORD, FRESH } from './pricing-master-fixtures';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/ConsoleShell', () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('../app/components/NoCompany', () => ({
  NoCompany: () => <p>Select a company</p>,
}));
vi.mock('../app/components/PricingMasterDirectory', () => ({
  PricingMasterDirectory: ({
    company,
    canManage,
  }: {
    company: string;
    canManage: boolean;
  }) => (
    <p>
      Directory {company} {canManage ? 'manage' : 'read'}
    </p>
  ),
}));
vi.mock('../app/components/PricingMasterEditor', () => ({
  PricingMasterEditor: ({
    company,
    access,
  }: {
    company: string;
    access: { purchaseRead: boolean; purchaseManage: boolean };
  }) => (
    <p>
      Editor {company} {access.purchaseRead ? 'purchase read' : ''}{' '}
      {access.purchaseManage ? 'purchase manage' : ''}
    </p>
  ),
}));
vi.mock('../app/components/PricingMasterDetail', () => ({
  PricingMasterDetail: ({ company }: { company: string }) => (
    <p>Detail {company}</p>
  ),
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not found');
  },
}));
async function actor(keys: string[], scope = COMPANY, type = 'company') {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'Acme' };
  session.permissions = [];
  session.grants = [
    {
      scope_type: type,
      scope_id: type === 'company' ? scope : null,
      valid_from: '2020-01-01',
      valid_to: null,
      permissions: keys,
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
  return session;
}
beforeEach(() => vi.clearAllMocks());
it.each(pricingResources)('opens all scoped %s pages', async (resource) => {
  const permission = masterConfig(resource)!.permission;
  await actor([permission + '.read', permission + '.manage']);
  for (const [record, label] of [
    [[], 'Directory'],
    [['new'], 'Editor'],
    [[RECORD], 'Detail'],
    [[RECORD, 'edit'], 'Editor'],
  ] as [string[], string][]) {
    const view = render(await CatalogMasterPage({ resource, record }));
    expect(screen.getByText(new RegExp(label + ' ' + COMPANY))).toBeVisible();
    view.unmount();
  }
});
it.each(pricingResources)(
  'denies %s editing to read-only users',
  async (resource) => {
    await actor([masterConfig(resource)!.permission + '.read']);
    render(await CatalogMasterPage({ resource, record: ['new'] }));
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it.each(['flat', 'other-company', 'department'])(
  'does not use %s permissions for company pricing',
  async (mode) => {
    const session = await actor(
      ['price_plan.read', 'price_plan.manage'],
      mode === 'other-company' ? FRESH : COMPANY,
      mode === 'department' ? 'department' : 'company',
    );
    if (mode === 'flat') {
      session.grants = [];
      session.permissions = ['price_plan.read', 'price_plan.manage'];
    }
    render(await CatalogMasterPage({ resource: 'price-plans' }));
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it.each(['tenant', 'company'])(
  'supports scoped %s administrators',
  async (type) => {
    await actor(
      [
        'price_plan.read',
        'price_plan.manage',
        'purchase_price.read',
        'purchase_price.manage',
      ],
      COMPANY,
      type,
    );
    render(
      await CatalogMasterPage({ resource: 'price-plans', record: ['new'] }),
    );
    expect(screen.getByText(/purchase read purchase manage/)).toBeVisible();
  },
);
it('requires tenant or company authority for platform administrators', async () => {
  const session = await actor(
    ['price_plan.read', 'price_plan.manage'],
    COMPANY,
    'platform',
  );
  session.role = 'platform_admin';
  render(await CatalogMasterPage({ resource: 'price-plans', record: ['new'] }));
  expect(screen.getByText(/You need/)).toBeVisible();
});
it('asks for a company before pricing configuration', async () => {
  const session = await actor(['price_plan.read']);
  session.company = { name: '' };
  render(await CatalogMasterPage({ resource: 'price-plans' }));
  expect(screen.getByText('Select a company')).toBeVisible();
});
it.each([
  ['publish'],
  [RECORD, 'publish'],
  [RECORD, 'revisions', FRESH],
  ['bad'],
  [RECORD, 'edit', 'extra'],
])('rejects malformed pricing route %s', async (...record) => {
  await expect(
    CatalogMasterPage({ resource: 'price-plans', record: record.flat() }),
  ).rejects.toThrow('not found');
});
it('exposes three independently authorized cards under the Masters menu', async () => {
  const session = await actor(['sales_channel.read', 'price_plan.read']);
  expect(navigationFor(session).flatMap(section => flattenNavigation(section.items)).some(link => link.href === '/masters')).toBe(true);
  const links = companyMastersFor(session).flatMap(section => section.items);
  for (const resource of pricingResources)
    expect(links.some((link) => link.href === '/masters/' + resource)).toBe(
      true,
    );
  session.grants = [];
  expect(
    companyMastersFor(session)
      .flatMap(section => section.items)
      .some((link) =>
        /\/masters\/(sales-channels|price-levels|price-plans)/.test(
          link.href ?? '',
        ),
      ),
  ).toBe(false);
});
