/**
 * The two company routes as pages: what each resolves, and who each refuses.
 *
 * Hiding a link is a courtesy; the page itself must refuse, and the API refuses again
 * (CLAUDE.md §5.1). That is what these assert — not the screens themselves, which have their
 * own tests.
 */
import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import CompaniesPage from '../app/companies/page';
import NewCompanyPage from '../app/companies/new/page';
import { getCompanyContext, getCompanyList } from '../app/lib/company-context';
import { pageContext } from '../app/lib/page-context';
import { getSession } from '../app/session';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/session', () => ({ getSession: vi.fn() }));
vi.mock('../app/lib/company-context', () => ({ getCompanyList: vi.fn(), getCompanyContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: ReactNode }) => children }));
vi.mock('../app/components/Companies', () => ({
  Companies: ({ openCompanyId, canCreate }: { openCompanyId?: string; canCreate: boolean }) => (
    <p>directory {openCompanyId ?? 'none'} {canCreate ? 'can-create' : 'read-only'}</p>
  ),
}));
vi.mock('../app/components/CompanyWizard', () => ({
  CompanyWizard: ({ canBootstrapBooks }: { canBootstrapBooks: boolean }) => <p>wizard {canBootstrapBooks ? 'with-books' : 'without-books'}</p>,
}));

const COMPANY = '01990000-0000-7000-8000-000000000001';
/** The keys the books step needs besides one of the two finance-write keys. */
const BOOKS = ['accounting.finance.read', 'period.read', 'period.manage'];
const CONTEXT = { companies: [], companiesNote: null, fiscalYears: [], fiscalYear: null, fiscalNote: null };

function resolve(permissions: string[], company: string | undefined = COMPANY) {
  const session = { permissions, company: { name: 'Acme', id: company }, display: {}, user: { defaultCompanyId: null },
    grants: [{ permissions, scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }] };
  vi.mocked(getSession).mockResolvedValue(session as unknown as Awaited<ReturnType<typeof getSession>>);
  vi.mocked(getCompanyList).mockResolvedValue({ companies: [], refused: false });
  vi.mocked(getCompanyContext).mockResolvedValue(CONTEXT);
  vi.mocked(pageContext).mockResolvedValue({ session, context: CONTEXT } as unknown as Awaited<ReturnType<typeof pageContext>>);
}

beforeEach(() => resolve(['company.read']));
afterEach(() => vi.clearAllMocks());

it('opens the directory to anyone who can read a company, marking what they may do', async () => {
  const first = render(await CompaniesPage());
  expect(screen.getByText(/directory/)).toHaveTextContent(`directory ${COMPANY} read-only`);
  first.unmount();

  resolve(['company.read', 'company.create']);
  render(await CompaniesPage());
  expect(screen.getByText(/can-create/)).toBeInTheDocument();
});

it('refuses the wizard without the authority to create a company', async () => {
  render(await NewCompanyPage({}));
  expect(screen.getByRole('alert')).toHaveTextContent("You don't have access to this");
  expect(screen.queryByText(/wizard/)).not.toBeInTheDocument();
  // The refusal renders a rail, so that path is the only one that pays for the context.
  expect(getCompanyContext).toHaveBeenCalled();
});
it('does not offer tenant company creation from a company-only create grant', async () => {
  resolve(['company.create']);
  const session = await getSession(); session.grants![0].scope_type = 'company';
  render(await NewCompanyPage({})); expect(screen.queryByText(/wizard/)).not.toBeInTheDocument();
});
it('plans books through the new owner grant without borrowing another company grant', async () => {
  resolve(['company.create', ...BOOKS, 'accounting.finance.initialize']);
  const session = await getSession();
  session.grants = [
    { permissions: ['company.create'], scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null },
    { permissions: [...BOOKS, 'accounting.finance.initialize'], scope_type: 'company', scope_id: COMPANY, valid_from: '2020-01-01', valid_to: null },
  ];
  render(await NewCompanyPage({})); expect(screen.getByText(/wizard/)).toHaveTextContent('with-books');
});

it('does not resolve the company context for the wizard itself', async () => {
  resolve(['company.create']);
  render(await NewCompanyPage({}));
  expect(screen.getByText(/wizard/)).toBeInTheDocument();
  expect(getCompanyContext).not.toHaveBeenCalled();
});

it.each([
  [['company.create'], 'with-books'],
  // The new company-scoped owner grant supplies setup permissions after creation.
  [['company.create', ...BOOKS.slice(1), 'accounting.finance.initialize'], 'with-books'],
  // Existing tenant permissions do not need to include financial writes.
  [['company.create', ...BOOKS], 'with-books'],
  /*
   * Either finance-write key satisfies `financial-setup/initialize`. `initialize` is the narrow
   * bootstrap key the administrator roles hold; `manage` is the controller's wider
   * opening-balance key. Requiring `manage` is what kept showing administrators the hand-off
   * after they had been granted the key that actually works.
   */
  [['company.create', ...BOOKS, 'accounting.finance.initialize'], 'with-books'],
  [['company.create', ...BOOKS, 'accounting.finance.manage'], 'with-books'],
])('plans company-scoped owner setup for each authorised creator: %j', async (permissions, expected) => {
  resolve(permissions);
  render(await NewCompanyPage({}));
  expect(screen.getByText(/wizard/)).toHaveTextContent(expected);
});
