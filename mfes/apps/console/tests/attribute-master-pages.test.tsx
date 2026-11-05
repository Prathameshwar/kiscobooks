import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import { masterConfig } from '../app/lib/catalog-masters';
import { attributeResources } from '../app/lib/attribute-resources';
import { flattenNavigation, navigationFor } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';
import { COMPANY, RECORD, FRESH } from './attribute-master-fixtures';
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
vi.mock('../app/components/AttributeMasterDirectory', () => ({
  AttributeMasterDirectory: ({ company }: { company: string }) => (
    <p>Directory {company}</p>
  ),
}));
vi.mock('../app/components/AttributeMasterEditor', () => ({
  AttributeMasterEditor: ({ company }: { company: string }) => (
    <p>Editor {company}</p>
  ),
}));
vi.mock('../app/components/AttributeMasterDetail', () => ({
  AttributeMasterDetail: ({ company }: { company: string }) => (
    <p>Detail {company}</p>
  ),
}));
vi.mock('../app/components/AttributeSetRevision', () => ({
  AttributeSetRevision: ({
    canManage,
    access,
  }: {
    canManage: boolean;
    access: { publish: boolean };
  }) => (
    <p>
      Revision {canManage ? 'manage' : 'read'} {access.publish ? 'publish' : ''}
    </p>
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
it.each(attributeResources)(
  'opens every %s route with scoped access',
  async (resource) => {
    const permission = masterConfig(resource)!.permission;
    await actor([permission + '.read', permission + '.manage']);
    for (const [record, label] of [
      [[], 'Directory'],
      [['new'], 'Editor'],
      [[RECORD], 'Detail'],
      [[RECORD, 'edit'], 'Editor'],
    ] as [string[], string][]) {
      const view = render(await CatalogMasterPage({ resource, record }));
      expect(screen.getByText(label + ' ' + COMPANY)).toBeVisible();
      view.unmount();
    }
  },
);
it.each(attributeResources)(
  'withholds %s edits from readers',
  async (resource) => {
    await actor([masterConfig(resource)!.permission + '.read']);
    render(await CatalogMasterPage({ resource, record: ['new'] }));
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it.each(attributeResources)(
  'rejects %s grants for other companies',
  async (resource) => {
    await actor([masterConfig(resource)!.permission + '.read'], RECORD);
    render(await CatalogMasterPage({ resource }));
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it('permits explicit tenant administration within the open company', async () => {
  await actor(['attribute_set.read'], COMPANY, 'tenant');
  render(await CatalogMasterPage({ resource: 'attribute-sets' }));
  expect(screen.getByText('Directory ' + COMPANY)).toBeVisible();
});
it('requires tenant or company authority for platform administrators', async () => {
  const session = await actor(['attribute_set.read'], COMPANY, 'platform');
  session.role = 'platform_admin';
  render(await CatalogMasterPage({ resource: 'attribute-sets' }));
  expect(screen.getByText(/You need/)).toBeVisible();
});
it('shows independently authorized cards under the Masters menu', async () => {
  const session = await actor(['attribute_option.read']);
  const links = flattenNavigation(
    navigationFor(session).flatMap((section) => section.items),
  ).map((item) => item.href);
  expect(links).toContain('/masters');
  const cards = companyMastersFor(session).flatMap(section => section.items).map(item => item.href);
  expect(cards).toContain('/masters/attribute-options');
  expect(cards).not.toContain('/masters/attribute-definitions');
  expect(cards).not.toContain('/masters/attribute-sets');
  expect(links).not.toContain('/masters/attribute-definitions');
  expect(links).not.toContain('/masters/attribute-sets');
});
it('opens publication separately from draft management', async () => {
  await actor(['attribute_set.read', 'attribute_set.publish']);
  const view = render(
    await CatalogMasterPage({
      resource: 'attribute-sets',
      record: [RECORD, 'revisions', FRESH],
    }),
  );
  expect(screen.getByText('Revision read publish')).toBeVisible();
  view.unmount();
  render(
    await CatalogMasterPage({
      resource: 'attribute-sets',
      record: [RECORD, 'revisions', 'new'],
    }),
  );
  expect(screen.getByText(/You need/)).toBeVisible();
});
it('requires an open company', async () => {
  const session = await actor(['attribute_set.read']);
  session.company = { name: 'Select company' };
  render(await CatalogMasterPage({ resource: 'attribute-sets' }));
  expect(screen.getByText('Select a company')).toBeVisible();
});
it.each([
  [RECORD, 'revisions'],
  [RECORD, 'revisions', 'bad'],
  [RECORD, 'revisions', FRESH, 'edit'],
  ['bad'],
  [RECORD, 'unknown'],
])('rejects malformed record route %j', async (...record) => {
  await actor(['attribute_set.read']);
  await expect(
    CatalogMasterPage({
      resource: 'attribute-sets',
      record: record as string[],
    }),
  ).rejects.toThrow('not found');
});
