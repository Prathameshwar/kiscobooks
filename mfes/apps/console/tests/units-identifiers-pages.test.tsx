import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CatalogMasterPage } from '../app/components/CatalogMasterPage';
import { pageContext } from '../app/lib/page-context';
import { masterConfig } from '../app/lib/catalog-masters';
import { identifierResources } from '../app/lib/units-identifiers';
import { flattenNavigation, navigationFor } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { sessionFor, companyContextFor } from './helpers';
import { COMPANY, RECORD } from './units-identifiers-fixtures';

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
vi.mock('../app/components/UnitsIdentifiersDirectory', () => ({
  UnitsIdentifiersDirectory: ({
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
vi.mock('../app/components/UnitsIdentifiersEditor', () => ({
  UnitsIdentifiersEditor: ({ company }: { company: string }) => (
    <p>Editor {company}</p>
  ),
}));
vi.mock('../app/components/UnitsIdentifiersDetail', () => ({
  UnitsIdentifiersDetail: ({ company }: { company: string }) => (
    <p>Detail {company}</p>
  ),
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not found');
  },
}));

async function actor(keys: string[], scope = COMPANY, scopeType = 'company') {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: 'Acme' };
  session.permissions = [];
  session.grants = [
    {
      scope_type: scopeType,
      scope_id: scopeType === 'company' ? scope : null,
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

describe('company-scoped master pages and menu navigation', () => {
  it.each(identifierResources)(
    'opens every supported %s page',
    async (resource) => {
      const permission = masterConfig(resource)!.permission;
      await actor([permission + '.read', permission + '.manage']);
      const paths = [
        [[], 'Directory'],
        [['new'], 'Editor'],
        [[RECORD], 'Detail'],
        ...(resource === 'unit-conversions'
          ? []
          : [[[RECORD, 'edit'], 'Editor']]),
      ] as [string[], string][];
      for (const [record, text] of paths) {
        const view = render(await CatalogMasterPage({ resource, record }));
        expect(
          screen.getByText(new RegExp(text + ' ' + COMPANY)),
        ).toBeVisible();
        view.unmount();
      }
    },
  );
  it.each(identifierResources)(
    'allows %s browsing while withholding unauthorized edits',
    async (resource) => {
      await actor([masterConfig(resource)!.permission + '.read']);
      const view = render(await CatalogMasterPage({ resource }));
      expect(screen.getByText(new RegExp('Directory .* read'))).toBeVisible();
      view.unmount();
      render(await CatalogMasterPage({ resource, record: ['new'] }));
      expect(screen.getByText(/You need/)).toBeVisible();
    },
  );
  it.each(identifierResources)(
    'rejects %s grants for another company',
    async (resource) => {
      const permission = masterConfig(resource)!.permission;
      await actor([permission + '.read', permission + '.manage'], RECORD);
      render(await CatalogMasterPage({ resource }));
      expect(screen.getByText(/You need/)).toBeVisible();
    },
  );
  it('does not hide profiles behind unrelated unit read authority', async () => {
    const session = await actor(['identifier_profile.read']);
    const links = flattenNavigation(
      navigationFor(session).flatMap((section) => section.items),
    ).map((item) => item.href);
    expect(links).toContain('/masters');
    const cards = companyMastersFor(session).flatMap(section => section.items).map(item => item.href);
    expect(cards).toContain('/masters/identifier-profiles');
    expect(cards).not.toContain('/masters/units');
    expect(cards).not.toContain('/masters/unit-conversions');
    expect(links).not.toContain('/masters/units');
    expect(links).not.toContain('/masters/unit-conversions');
  });
  it('uses explicit tenant grants within the open company', async () => {
    await actor(['identifier_type.read'], COMPANY, 'tenant');
    render(await CatalogMasterPage({ resource: 'identifier-types' }));
    expect(screen.getByText(new RegExp('Directory .* read'))).toBeVisible();
  });
  it('requires company or tenant authority even for a platform administrator', async () => {
    const session = await actor(['identifier_type.read'], COMPANY, 'platform');
    session.role = 'platform_admin';
    render(await CatalogMasterPage({ resource: 'identifier-types' }));
    expect(screen.getByText(/You need/)).toBeVisible();
  });
  it('requires an open company even when an administrator has grants', async () => {
    const session = await actor(['pack_type.read'], COMPANY, 'tenant');
    session.company = { name: 'Select company' };
    render(await CatalogMasterPage({ resource: 'pack-types' }));
    expect(screen.getByText('Select a company')).toBeVisible();
  });
  it.each([
    ['unit-conversions', [RECORD, 'edit']],
    ['identifier-types', ['bad']],
    ['identifier-profiles', [RECORD, 'delete']],
    ['identifier-namespaces', [RECORD, 'requirements']],
    ['pack-types', [RECORD, 'edit', 'extra']],
  ])('rejects unsupported %s routes', async (resource, record) =>
    expect(CatalogMasterPage({ resource, record })).rejects.toThrow(
      'not found',
    ),
  );
});
