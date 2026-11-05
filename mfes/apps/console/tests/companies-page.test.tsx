/**
 * The company directory: the list, the search, and opening a company from it.
 *
 * Opening goes through the same selection route as the rail's switcher — one way to change
 * company context — so the assertions here are about wiring and about what the reader is told
 * when it refuses.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { Companies } from '../app/components/Companies';
import { companyCall, openCompany } from '../app/lib/company-api';
import type { CompanyChoice } from '../app/lib/company-context';

/*
 * `openCompany` is mocked, not re-implemented: it owns the selection, the step-up hand-off and
 * the reload, and it has its own tests (`company-api.test.ts`). What matters here is that the
 * directory calls it and renders what it hands back.
 */
vi.mock('../app/lib/company-api', () => ({
  companyCall: vi.fn(),
  openCompany: vi.fn(),
  companyFailure: (value: unknown) =>
    value && typeof value === 'object' && 'status' in value ? value : { status: 503, message: 'The company service is unavailable. Try again.' },
}));

const ACME = '01990000-0000-7000-8000-000000000001';
const NORTHWIND = '01990000-0000-7000-8000-000000000002';
const COMPANIES: CompanyChoice[] = [
  { id: ACME, name: 'Acme Manufacturing', code: 'ACME-01', isDefault: true, requiresStepUp: false },
  { id: NORTHWIND, name: 'Northwind Retail', code: 'NW-01', isDefault: false, requiresStepUp: true },
];

function mount({
  companies = COMPANIES,
  note = null as string | null,
  open = ACME as string | undefined,
  canCreate = true,
  initialPage = undefined as { limit: number; has_more: boolean; next_cursor: string | null } | undefined,
} = {}) {
  return render(
    <PermissionProvider permissions={canCreate ? ['company.read', 'company.create'] : ['company.read']}>
      <DisplayConfigProvider config={{}}>
        <Companies companies={companies} note={note} openCompanyId={open} canCreate={canCreate} initialPage={initialPage} />
      </DisplayConfigProvider>
    </PermissionProvider>,
  );
}

beforeEach(() => {
  vi.mocked(openCompany).mockResolvedValue(null);
  vi.mocked(companyCall).mockResolvedValue({ items: [], page: { has_more: false, next_cursor: null } } as never);
});
afterEach(() => vi.clearAllMocks());

it('preserves the first-page continuation and requests it when browsing next', async () => {
  const user = userEvent.setup(); mount({ initialPage: { limit: 50, has_more: true, next_cursor: 'company-page-two' } });
  await user.click(screen.getByRole('button', { name: /Next page/ }));
  await waitFor(() => expect(companyCall).toHaveBeenCalledWith('identity', expect.stringContaining('cursor=company-page-two'), expect.anything()));
});

it('lists every company with its code, marking the open one and the stored default', () => {
  mount();

  const table = screen.getByRole('table', { name: 'Companies you can open' });
  expect(within(table).getByText('ACME-01')).toBeInTheDocument();
  expect(within(table).getByText('Northwind Retail')).toBeInTheDocument();
  expect(within(table).getByText('Open')).toBeInTheDocument();
  expect(within(table).getByText('Default')).toBeInTheDocument();
});

it('opens another company through the one selection path', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Northwind Retail/ }));
  await user.click(screen.getByRole('menuitem', { name: 'Open this company' }));

  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(NORTHWIND));
});

it('refuses to re-open the company already in hand, and says why', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Acme Manufacturing/ }));
  const item = screen.getByRole('menuitem', { name: /Already open/ });
  expect(item).toHaveAttribute('aria-disabled', 'true');
  expect(item).toHaveTextContent('This is the company you are working in');

  await user.click(item);
  expect(openCompany).not.toHaveBeenCalled();
});

it('shows a refusal instead of appearing to do nothing', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(openCompany).mockResolvedValue({ status: 403, message: 'This company is unavailable.' });
  mount();

  await user.click(screen.getByRole('button', { name: /Northwind Retail/ }));
  await user.click(screen.getByRole('menuitem', { name: 'Open this company' }));

  await waitFor(() => expect(screen.getByText('This company is unavailable.')).toBeInTheDocument());
});

it('searches the server and shows what came back', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(companyCall).mockResolvedValue({ items: [{ id: NORTHWIND, code: 'NW-01', display_name: 'Northwind Retail' }] } as never);
  mount();

  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north');
  await waitFor(() => expect(companyCall).toHaveBeenCalled());
  expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('q=north');
  expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('limit=50');
  await waitFor(() => expect(screen.queryByText('Acme Manufacturing')).not.toBeInTheDocument());
});

it('tells a search apart from an outage when the list comes back empty', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'zzzz');
  await waitFor(() => expect(screen.getByText('No company matches that search')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /Clear filters/i })).toBeInTheDocument();
});

it('reports a failed search with the status’s own copy, not an outage', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(companyCall).mockRejectedValue({ status: 403, message: 'Denied' });
  mount();

  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north');
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("You don't have access to this"));
});

it('offers creation to a permitted actor, in the header and in the empty state', () => {
  const { unmount } = mount({ companies: [], note: 'No company has been created yet.' });
  expect(screen.getByRole('link', { name: 'Create company' })).toHaveAttribute('href', '/companies/new');
  expect(screen.getByRole('link', { name: 'Create the first company' })).toBeInTheDocument();
  expect(screen.getByText('No company has been created yet.')).toBeInTheDocument();
  unmount();

  mount({ companies: [], note: 'No company has been assigned to you yet. Ask your administrator.', canCreate: false });
  expect(screen.queryByRole('link', { name: /Create/ })).not.toBeInTheDocument();
  expect(screen.getByText(/Ask your administrator/)).toBeInTheDocument();
});
