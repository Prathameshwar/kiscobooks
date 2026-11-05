import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PartyImportPage } from '../app/components/PartyImportPage';
import { PartyImport } from '../app/components/PartyImport';
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
vi.mock('../app/components/PartyImport', () => ({
  PartyImport: vi.fn(() => <p>Scoped party import</p>),
}));
beforeEach(async () => {
  vi.clearAllMocks();
  const session = await sessionFor({
    permissions: [
      'accounting.party.read',
      'accounting.party.manage',
      'accounting.import.manage',
    ],
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
it.each([false, true])(
  'opens the party/supplier entry point using scoped Accounting authority (%s)',
  async (supplier) => {
    render(
      await PartyImportPage({
        supplier,
        query: { job: JOB, returnTo: '/accounting/suppliers' },
      }),
    );
    expect(vi.mocked(PartyImport).mock.calls[0]![0]).toMatchObject({
      company: companyId,
      supplier,
      canManage: true,
      initialJob: JOB,
    });
  },
);
it.each([
  'catalog_only',
  'other_company',
  'expired',
  'label_only',
  'no_party_read',
])('denies party import data for %s', async (reason) => {
  const data = await pageContext(),
    grant = data.session.grants![0]!;
  if (reason === 'catalog_only')
    grant.permissions = [
      'item.read',
      'catalog.bulk.read',
      'catalog.bulk.manage',
    ];
  if (reason === 'other_company') grant.scope_id = userId;
  if (reason === 'expired') grant.valid_to = '2020-01-01';
  if (reason === 'label_only') {
    data.session.role = 'platform_admin';
    data.session.grants = [];
  }
  if (reason === 'no_party_read')
    grant.permissions = ['accounting.import.manage'];
  render(await PartyImportPage({}));
  expect(PartyImport).not.toHaveBeenCalled();
  expect(
    screen.getByText(
      'Party read and Accounting import access are required for this company.',
    ),
  ).toBeVisible();
});
it('shows retained history without write controls after party manage is removed', async () => {
  (await pageContext()).session.grants![0]!.permissions = [
    'accounting.party.read',
    'accounting.import.manage',
  ];
  render(await PartyImportPage({ query: { view: 'history' } }));
  expect(vi.mocked(PartyImport).mock.calls[0]![0]).toMatchObject({
    canManage: false,
    initialHistory: true,
  });
});
it('rejects malformed job identifiers before resolving the session', async () => {
  await expect(PartyImportPage({ query: { job: 'bad' } })).rejects.toThrow(
    'not found',
  );
  expect(pageContext).not.toHaveBeenCalled();
});
