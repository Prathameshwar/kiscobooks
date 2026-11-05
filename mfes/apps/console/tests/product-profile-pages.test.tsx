import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import {
  productProfileResources,
  profileDefinitions,
} from '../app/lib/product-profile-resources';
import { navigationFor, flattenNavigation } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';
import { COMPANY, RECORD, SOURCE, FRESH } from './product-profile-fixtures';
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
vi.mock('../app/components/ProductProfileDirectory', () => ({
  ProductProfileDirectory: ({ company }: { company: string }) => (
    <p>Directory {company}</p>
  ),
}));
vi.mock('../app/components/ProductProfileEditor', () => ({
  ProductProfileEditor: ({ company }: { company: string }) => (
    <p>Editor {company}</p>
  ),
}));
vi.mock('../app/components/ProductProfileDetail', () => ({
  ProductProfileDetail: ({ company }: { company: string }) => (
    <p>Detail {company}</p>
  ),
}));
vi.mock('../app/components/ProductProfileRevision', () => ({
  ProductProfileRevision: ({
    parentId,
    id,
    canManage,
    access,
  }: {
    parentId: string;
    id?: string;
    canManage: boolean;
    access: { publish: boolean };
  }) => (
    <p>
      Revision {parentId} {id ?? 'new'} {canManage ? 'manage' : 'read'}{' '}
      {access.publish ? 'publish' : ''}
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
it.each(productProfileResources)(
  'opens every scoped %s page',
  async (resource) => {
    const prefix = profileDefinitions[resource].permission;
    await actor([prefix + '.read', prefix + '.manage', prefix + '.publish']);
    for (const [record, label] of [
      [[], 'Directory'],
      [['new'], 'Editor'],
      [[RECORD], 'Detail'],
      [[RECORD, 'edit'], 'Editor'],
      [[RECORD, 'revisions', 'new'], 'Revision'],
      [[RECORD, 'revisions', SOURCE], 'Revision'],
    ] as [string[], string][]) {
      const view = render(await CatalogMasterPage({ resource, record }));
      expect(screen.getByText(new RegExp(label))).toBeVisible();
      view.unmount();
    }
  },
);
it.each(productProfileResources)(
  'allows publisher-only %s revision review and publication',
  async (resource) => {
    const prefix = profileDefinitions[resource].permission;
    await actor([prefix + '.read', prefix + '.publish']);
    render(
      await CatalogMasterPage({
        resource,
        record: [RECORD, 'revisions', SOURCE],
      }),
    );
    expect(screen.getByText(/read publish/)).toBeVisible();
  },
);
it.each(productProfileResources)(
  'denies a %s new draft to read-only users',
  async (resource) => {
    await actor([profileDefinitions[resource].permission + '.read']);
    render(
      await CatalogMasterPage({
        resource,
        record: [RECORD, 'revisions', 'new'],
      }),
    );
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it.each(['tenant', 'company'])(
  'supports %s administrator company authority',
  async (type) => {
    await actor(
      ['handling_profile.read', 'handling_profile.manage'],
      COMPANY,
      type,
    );
    render(
      await CatalogMasterPage({
        resource: 'handling-profiles',
        record: ['new'],
      }),
    );
    expect(screen.getByText(/Editor/)).toBeVisible();
  },
);
it.each(['flat', 'platform', 'department', 'other-company'])(
  'rejects %s authority for company profile management',
  async (mode) => {
    const session = await actor(
      ['handling_profile.read', 'handling_profile.manage'],
      mode === 'other-company' ? FRESH : COMPANY,
      ['platform', 'department'].includes(mode) ? mode : 'company',
    );
    if (mode === 'platform') session.role = 'platform_admin';
    if (mode === 'flat') {
      session.grants = [];
      session.permissions = [
        'handling_profile.read',
        'handling_profile.manage',
      ];
    }
    render(
      await CatalogMasterPage({
        resource: 'handling-profiles',
        record: ['new'],
      }),
    );
    expect(screen.getByText(/You need/)).toBeVisible();
  },
);
it('requires a company before opening profiles', async () => {
  const session = await actor(['handling_profile.read']);
  session.company = { name: '' };
  render(await CatalogMasterPage({ resource: 'handling-profiles' }));
  expect(screen.getByText('Select a company')).toBeVisible();
});
it.each([
  ['bad'],
  [RECORD, 'publish'],
  [RECORD, 'revisions'],
  [RECORD, 'revisions', 'bad'],
  [RECORD, 'edit', 'extra'],
  ['new', 'revisions', SOURCE],
  [RECORD, 'revisions', SOURCE, 'edit'],
])('rejects malformed profile route %s', async (...record) => {
  await expect(
    CatalogMasterPage({ resource: 'handling-profiles', record: record.flat() }),
  ).rejects.toThrow('not found');
});
it('exposes only separately authorized profile cards under the Masters menu', async () => {
  const session = await actor([
    'handling_profile.read',
    'warranty_policy.read',
  ]);
  expect(navigationFor(session).flatMap(section => flattenNavigation(section.items)).some(link => link.href === '/masters')).toBe(true);
  const links = companyMastersFor(session).flatMap(section => section.items);
  for (const resource of productProfileResources)
    expect(links.some((link) => link.href === '/masters/' + resource)).toBe(
      ['handling-profiles', 'warranty-policies'].includes(resource),
    );
  session.company = { name: '' };
  expect(
    companyMastersFor(session)
      .flatMap(section => section.items)
      .some((link) =>
        productProfileResources.some(
          (resource) => link.href === '/masters/' + resource,
        ),
      ),
  ).toBe(false);
});
