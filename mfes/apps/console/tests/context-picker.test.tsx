/**
 * The rail's company and financial-year context, as the console wires it.
 *
 * The switcher itself is unit-tested in `@janso/ui`. What matters here is the wiring: that a
 * selection goes through the one selection route, that a company demanding verification is
 * handed to auth instead of failing, that the year selector is absent for an actor who cannot
 * read the calendar, and that the rail never claims a default the user has not set.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PermissionProvider } from '@janso/ui';
import { ContextPicker } from '../app/components/ContextPicker';
import { companyCall, openCompany, setDefaultCompany } from '../app/lib/company-api';
import { goTo } from '../app/lib/navigate';
import type { CompanyContext } from '../app/lib/company-context';
import type { Session } from '../app/session';

/*
 * `openCompany` is mocked rather than re-implemented: it owns the selection, the step-up
 * hand-off and the reload, and has its own tests (`company-api.test.ts`). What matters here is
 * that the rail calls it with the right company and year, and renders what it hands back.
 */
vi.mock('../app/lib/company-api', () => ({
  companyCall: vi.fn(),
  setDefaultCompany: vi.fn(),
  openCompany: vi.fn(),
  companyFailure: (value: unknown) =>
    value && typeof value === 'object' && 'status' in value ? value : { status: 503, message: 'The company service is unavailable. Try again.' },
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));

const ACME = '01990000-0000-7000-8000-000000000001';
const NORTHWIND = '01990000-0000-7000-8000-000000000002';
const Y2026 = '01990000-0000-7000-8000-00000000000a';

function session(overrides: Partial<Session> = {}): Session {
  return {
    user: { name: 'Admin', secondary: 'Tenant', theme: null, defaultCompanyId: ACME },
    organisation: { name: 'Tenant', code: 'TENANT' },
    company: { name: 'Acme Manufacturing', id: ACME, code: 'ACME-01' },
    companySource: 'default',
    stepUpCompanyId: null,
    companyScopes: [],
    role: 'tenant admin',
    permissions: ['company.read', 'company.create', 'period.read'],
    grants: [{ permissions: overrides.permissions ?? ['company.read', 'company.create', 'period.read'], scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null }],
    display: { currency: 'INR' },
    ...overrides,
  };
}

function context(overrides: Partial<CompanyContext> = {}): CompanyContext {
  return {
    companies: [
      { id: ACME, name: 'Acme Manufacturing', code: 'ACME-01', isDefault: true, requiresStepUp: false },
      { id: NORTHWIND, name: 'Northwind Retail', code: 'NW-01', isDefault: false, requiresStepUp: false },
    ],
    companiesNote: null,
    fiscalYears: [{ id: Y2026, code: 'FY2026-2027', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true }],
    fiscalYear: { id: Y2026, code: 'FY2026-2027', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true },
    fiscalNote: null,
    ...overrides,
  };
}

function mount(value = session(), ctx = context()) {
  return render(
    <PermissionProvider permissions={value.permissions}>
      <ContextPicker session={value} context={ctx} />
    </PermissionProvider>,
  );
}

beforeEach(() => {
  vi.mocked(openCompany).mockResolvedValue(null);
  vi.mocked(setDefaultCompany).mockResolvedValue(undefined);
  vi.mocked(companyCall).mockResolvedValue({ items: [] } as never);
});
afterEach(() => vi.clearAllMocks());

it('names the open company and its financial year on the two triggers', () => {
  mount();
  expect(screen.getByRole('button', { name: /Switch company/ })).toHaveAccessibleName(/Acme Manufacturing/);
  expect(screen.getByRole('button', { name: /Switch company/ })).toHaveAccessibleName(/ACME-01/);
  expect(screen.getByRole('button', { name: /Switch financial year/ })).toHaveAccessibleName(/FY2026-2027/);
});

it('records the chosen company through the one selection path', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.click(screen.getByRole('option', { name: /Northwind Retail/ }));

  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(NORTHWIND, undefined));
});

it('records a financial year against the open company', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch financial year/ }));
  await user.click(screen.getByRole('option', { name: /FY2026-2027/ }));

  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(ACME, Y2026));
});

it('shows a refused switch in the rail instead of silently staying put', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(openCompany).mockResolvedValue({ status: 403, message: 'This company is unavailable.' });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.click(screen.getByRole('option', { name: /Northwind Retail/ }));

  // In the rail, not in the panel: choosing an option closes the panel.
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('This company is unavailable.'));
});

it('searches the server once the query is long enough, and not before', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(companyCall).mockResolvedValue({ items: [{ id: NORTHWIND, code: 'NW-01', display_name: 'Northwind Retail' }] } as never);
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'n');
  expect(companyCall).not.toHaveBeenCalled();

  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'orth');
  await waitFor(() => expect(companyCall).toHaveBeenCalledTimes(1));
  expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('q=north');
  expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('limit=20');
  await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(1));
});

it('searches the session’s own company list, not the company list', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north');
  // `/v1/companies` needs `company.read`, which a clerk does not hold: searching it is what
  // emptied their switcher.
  await waitFor(() => expect(vi.mocked(companyCall).mock.calls[0][1]).toContain('/v1/session/companies'));
});

it('marks a company that will ask for a fresh sign-in before it is chosen', async () => {
  const user = userEvent.setup({ delay: null });
  mount(session(), context({
    companies: [
      { id: ACME, name: 'Acme Manufacturing', code: 'ACME-01', isDefault: true, requiresStepUp: false },
      { id: NORTHWIND, name: 'Northwind Retail', code: 'NW-01', isDefault: false, requiresStepUp: true },
    ],
  }));

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.getByRole('option', { name: /Northwind Retail/ })).toHaveAccessibleName(/sign in again/);
  expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).not.toHaveAccessibleName(/sign in again/);
});

it('offers a company awaiting verification instead of showing no company', async () => {
  const user = userEvent.setup({ delay: null });
  mount(session({ company: { name: 'Select a company' }, stepUpCompanyId: NORTHWIND, companySource: 'default' }));

  // Routed through the same `openCompany`, which is the one place that recognises
  // `step_up_required` and hands the browser to auth.
  await user.click(screen.getByRole('button', { name: 'Verify to open it' }));
  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(NORTHWIND, undefined));
});

it('stores the open company as the default, and stops offering it once stored', async () => {
  const user = userEvent.setup({ delay: null });
  mount(session(), context({
    companies: [{ id: ACME, name: 'Acme Manufacturing', code: 'ACME-01', isDefault: false, requiresStepUp: false }],
  }));

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.click(screen.getByRole('button', { name: 'Set as my default' }));

  await waitFor(() => expect(setDefaultCompany).toHaveBeenCalledWith(ACME));
  // Nothing reloads: the page already shows that company, and only the *next* session changes.
  expect(openCompany).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.queryByRole('button', { name: 'Set as my default' })).not.toBeInTheDocument();
  expect(screen.getByRole('option', { name: /Acme Manufacturing/ })).toHaveAccessibleName(/Default/);
});

it('does not offer to store a default that is already stored, or when nothing is open', async () => {
  const user = userEvent.setup({ delay: null });
  const first = mount();
  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.queryByRole('button', { name: 'Set as my default' })).not.toBeInTheDocument();
  first.unmount();

  mount(session({ company: { name: 'Select a company' }, companySource: 'none' }));
  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.queryByRole('button', { name: 'Set as my default' })).not.toBeInTheDocument();
});

it('reports a refused default in the rail rather than appearing to have saved', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(setDefaultCompany).mockRejectedValue({ status: 422, message: 'Choose a company you can open.' });
  mount(session(), context({
    companies: [{ id: ACME, name: 'Acme Manufacturing', code: 'ACME-01', isDefault: false, requiresStepUp: false }],
  }));

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.click(screen.getByRole('button', { name: 'Set as my default' }));

  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Choose a company you can open.'));
});

it('says which rule opened the company, and never claims a default nobody set', async () => {
  const first = mount(session({ companySource: 'membership' }));
  expect(screen.getByText('Opened the company you work in')).toBeInTheDocument();
  first.unmount();

  const second = mount(session({ companySource: 'first' }));
  expect(screen.getByText('Opened your first company')).toBeInTheDocument();
  second.unmount();

  // A stored default needs no explanation: the badge in the panel already says so.
  mount(session({ companySource: 'default' }));
  expect(screen.queryByText(/^Opened/)).not.toBeInTheDocument();
});

it('reports a failed search in the panel', async () => {
  const user = userEvent.setup({ delay: null });
  vi.mocked(companyCall).mockRejectedValue({ status: 503, message: 'Companies are unavailable.' });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.type(screen.getByRole('searchbox', { name: 'Search companies' }), 'north');
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Companies are unavailable.'));
});

it('offers creation only to an actor who may create a company', async () => {
  const user = userEvent.setup({ delay: null });
  mount(session({ permissions: ['company.read'] }));

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.queryByRole('button', { name: 'Create company' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Manage companies' })).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: 'Manage companies' }));
  expect(goTo).toHaveBeenCalledWith('/companies');
});

it('leads a permitted actor to the creation wizard', async () => {
  const user = userEvent.setup({ delay: null });
  mount();

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  await user.click(screen.getByRole('button', { name: 'Create company' }));
  expect(goTo).toHaveBeenCalledWith('/companies/new');
});

it('omits the year selector entirely when the calendar cannot be read', () => {
  mount(session(), context({ fiscalYears: [], fiscalYear: null }));
  expect(screen.queryByRole('button', { name: /Switch financial year/ })).not.toBeInTheDocument();
});

it('explains an empty company list rather than looking broken', async () => {
  const user = userEvent.setup({ delay: null });
  mount(
    session({ company: { name: 'Select a company' }, companySource: 'none', permissions: ['company.read'] }),
    context({ companies: [], companiesNote: 'No company has been assigned to you yet. Ask your administrator.' }),
  );

  await user.click(screen.getByRole('button', { name: /Switch company/ }));
  expect(screen.getByText(/No company has been assigned to you yet/)).toBeInTheDocument();
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});

it('owns up to opening a company the user never chose', () => {
  mount(session({ companySource: 'first' }));
  expect(screen.getByText('Opened your first company')).toBeInTheDocument();
});

it('claims nothing when the company came from a stored default or a selection', () => {
  mount(session({ companySource: 'default' }));
  expect(screen.queryByText('Opened your first company')).not.toBeInTheDocument();
});
it('hides a previously resolved fiscal calendar after calendar permission is removed', () => {
  mount(session({ permissions: [] }), context());
  expect(screen.queryByRole('button', { name: /Switch financial year/ })).not.toBeInTheDocument();
});
