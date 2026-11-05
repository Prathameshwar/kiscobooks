import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import NewCompanyBankPage from '../app/companies/[companyId]/bank-accounts/new/page';
import { CompanyBankCreate } from '../app/components/CompanyBankCreate';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
import { companyId, userId } from './access-fixtures';
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
vi.mock('../app/components/CompanyBankCreate', () => ({
  CompanyBankCreate: vi.fn(({ company }: { company: string }) => (
    <p>Bank for {company}</p>
  )),
}));
const props = (id = companyId) => ({
  params: Promise.resolve({ companyId: id }),
  searchParams: Promise.resolve({
    returnTo: '/accounting/account-bank-profiles/new',
  }),
});
beforeEach(async () => {
  vi.clearAllMocks();
  const session = await sessionFor({
    permissions: ['company.read', 'company.update'],
  });
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
it('opens the scoped company-bank form and retains bank setup navigation', async () => {
  render(await NewCompanyBankPage(props()));
  expect(CompanyBankCreate).toHaveBeenCalledWith(
    expect.objectContaining({
      company: companyId,
      returnTo: '/accounting/account-bank-profiles/new',
    }),
    undefined,
  );
});
it('rejects malformed company identifiers before resolving context', async () => {
  await expect(NewCompanyBankPage(props('bad'))).rejects.toThrow('not found');
  expect(pageContext).not.toHaveBeenCalled();
});
it.each(['read_only', 'update_only', 'other_company', 'expired', 'role_label'])(
  'denies bank creation for %s',
  async (authority) => {
    const data = await pageContext(),
      grant = data.session.grants![0]!;
    if (authority === 'read_only') grant.permissions = ['company.read'];
    if (authority === 'update_only') grant.permissions = ['company.update'];
    if (authority === 'other_company') grant.scope_id = userId;
    if (authority === 'expired') grant.valid_to = '2020-01-01';
    if (authority === 'role_label') {
      data.session.role = 'platform_admin';
      data.session.grants = [];
    }
    render(await NewCompanyBankPage(props()));
    expect(
      screen.getByText(
        'Company read and update access are required to add company bank details.',
      ),
    ).toBeVisible();
    expect(CompanyBankCreate).not.toHaveBeenCalled();
  },
);
