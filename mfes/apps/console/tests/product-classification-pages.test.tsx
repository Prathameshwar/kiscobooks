import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import { classificationDefinitions, classificationResources } from '../app/lib/product-classification-resources';
import { navigationFor, flattenNavigation } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';
import { COMPANY, RECORD, SOURCE } from './product-classification-fixtures';
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ company: COMPANY, data: { company_id: COMPANY, row_version: 1, policy_generation: 1, product_family_sku_enabled: true }, loading: false, failure: null, refresh: vi.fn() }) }));
vi.mock('../app/components/ProductCreationExperience', () => ({ ProductCreationExperience: ({ company }: { company: string }) => <p>Creation {company}</p> }));
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
vi.mock('../app/components/ProductCatalogDirectory', () => ({
  ProductCatalogDirectory: ({
    company,
    canManage,
  }: {
    company: string;
    canManage: boolean;
  }) => (
    <p>
      Directory {company} {canManage ? 'edit' : 'read'}
    </p>
  ),
}));
vi.mock('../app/components/ProductCatalogEditor', () => ({
  ProductCatalogEditor: ({ company }: { company: string }) => (
    <p>Editor {company}</p>
  ),
}));
vi.mock('../app/components/ProductCatalogDetail', () => ({
  ProductCatalogDetail: ({
    company,
    initialSection,
  }: {
    company: string;
    initialSection?: string;
  }) => (
    <p>
      Detail {company}
      {initialSection ? ' section ' + initialSection : ''}
    </p>
  ),
}));
vi.mock('../app/components/ProductTypeRevision', () => ({
  ProductTypeRevision: ({
    parentId,
    id,
    access,
  }: {
    parentId: string;
    id?: string;
    access: { publish: boolean };
  }) => (
    <p>
      Revision {parentId} {id ?? 'new'} {access.publish ? 'publish' : ''}
    </p>
  ),
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not found');
  },
}));
beforeEach(() => vi.clearAllMocks());
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
it.each(classificationResources)(
  'opens every native %s page for a company-scoped actor',
  async (resource) => {
    const prefix = classificationDefinitions[resource].permission,
      product = prefix === 'item';
    const session = await actor([
      prefix + '.read',
      prefix + (product ? '.update' : '.manage'),
      ...(product ? ['item.create'] : []),
      prefix + '.publish',
    ]);
    for (const [record, label] of [
      [[], 'Directory'],
      [['new'], 'Editor'],
      [[RECORD], 'Detail'],
      [[RECORD, 'edit'], 'Editor'],
    ] as const) {
      const view = render(
        await CatalogMasterPage({ resource, record: [...record] }),
      );
      expect(screen.getByText(new RegExp((product && record[0] === 'new' ? 'Creation' : label) + ' ' + COMPANY))).toBeVisible();
      view.unmount();
    }
    expect(flattenNavigation(navigationFor(session).flatMap(section => section.items)).some(link => link.href === '/masters')).toBe(true);
    const links = companyMastersFor(session).flatMap(section => section.items);
    expect(links.some((link) => link.href === '/masters/' + resource)).toBe(
      true,
    );
  },
);
it.each(classificationResources)(
  'denies %s pages and navigation for a foreign company grant',
  async (resource) => {
    const prefix = classificationDefinitions[resource].permission,
      session = await actor(
        [prefix + '.read', prefix + '.manage', 'item.update'],
        SOURCE,
      );
    render(await CatalogMasterPage({ resource }));
    expect(screen.getByRole('alert')).toBeVisible();
    expect(
      companyMastersFor(session).flatMap(section => section.items).some((link) => link.href === '/masters/' + resource),
    ).toBe(false);
  },
);
it('keeps create and edit permissions separate for product directories', async () => {
  await actor(['item.read', 'item.create']);
  render(await CatalogMasterPage({ resource: 'items' }));
  expect(screen.getByText('Directory ' + COMPANY + ' read')).toBeVisible();
});
it('allows publisher-only type review but blocks creation of a new draft', async () => {
  await actor(['product_type.read', 'product_type.publish']);
  const view = render(
    await CatalogMasterPage({
      resource: 'product-types',
      record: [RECORD, 'revisions', SOURCE],
    }),
  );
  expect(
    screen.getByText(
      new RegExp('Revision ' + RECORD + ' ' + SOURCE + ' publish'),
    ),
  ).toBeVisible();
  view.unmount();
  render(
    await CatalogMasterPage({
      resource: 'product-types',
      record: [RECORD, 'revisions', 'new'],
    }),
  );
  expect(screen.getByRole('alert')).toBeVisible();
});
it('requires company authority even when platform permissions are present', async () => {
  const session = await actor([]);
  session.role = 'platform_admin';
  session.permissions = ['item.read', 'item.create', 'item.update'];
  render(await CatalogMasterPage({ resource: 'items' }));
  expect(screen.getByRole('alert')).toBeVisible();
});
it('validates native route shapes and requires a selected company', async () => {
  const session = await actor(['brand.read']);
  session.company = { name: '' };
  render(await CatalogMasterPage({ resource: 'brands' }));
  expect(screen.getByText('Select a company')).toBeVisible();
  await expect(
    CatalogMasterPage({ resource: 'brands', record: [RECORD, 'delete'] }),
  ).rejects.toThrow('not found');
  await expect(
    CatalogMasterPage({
      resource: 'brand-series',
      record: [RECORD, 'revisions', SOURCE],
    }),
  ).rejects.toThrow('not found');
});
it('rejects completion paths for classification resources or invalid identifiers', async () => {
  await expect(CatalogMasterPage({ resource: 'brands', record: [RECORD, 'created'] })).rejects.toThrow('not found');
  await expect(CatalogMasterPage({ resource: 'items', record: ['invalid', 'created'] })).rejects.toThrow('not found');
});

it.each(['items', 'product-families'])(
  'opens restored %s creation and record routes', async resource => {
    await actor(['item.read', 'item.create', 'item.update', 'item.activate']);
    for (const record of [['new'], [RECORD], [RECORD, 'edit'], [RECORD, 'created']]) {
      expect(await CatalogMasterPage({ resource, record })).toBeTruthy();
    }
    {
      const view = render(await CatalogMasterPage({ resource, record: ['new'] }));
      expect(screen.getByText('Creation ' + COMPANY)).toBeVisible();
      view.unmount();
    }
    render(await CatalogMasterPage({ resource }));
    expect(screen.getByText('Directory ' + COMPANY + ' edit')).toBeVisible();
  },
);
