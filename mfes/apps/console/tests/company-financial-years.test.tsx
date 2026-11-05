import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyFinancialYears } from '../app/components/CompanyFinancialYears';
import { CompanyDirectory } from '../app/components/CompanyDirectory';
import { Companies } from '../app/components/Companies';
import { CompanyYearPage } from '../app/components/CompanyYearPage';
import { CompanyBooksRecovery } from '../app/components/CompanyBooksRecovery';
import ContinuityPage from '../app/companies/[companyId]/years/[yearId]/continuity/page';
import NextYearPage from '../app/companies/[companyId]/years/next/page';
import { administrationReturn } from '../app/lib/administration-navigation';
import { companyCall } from '../app/lib/company-api';
import { pageContext } from '../app/lib/page-context';
import { goTo } from '../app/lib/navigate';
import { companyContextFor, sessionFor } from './helpers';
import type { Session } from '../app/session';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), openCompany: vi.fn(), companyFailure: (error: unknown) => error }));
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), stepUpUrl: (id: string) => '/verify/' + id }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
const COMPANY = '01990000-0000-7000-8000-000000000001', YEAR = '01990000-0000-7000-8000-000000000002';
const permissions = ['company.read', 'company.update', 'period.read', 'period.manage', 'period.close', 'period.reopen', 'period.lock', 'accounting.finance.read', 'accounting.finance.initialize'];
const year = { id: YEAR, company_id: COMPANY, code: 'FY2026-2027', start_date: '2026-04-01', end_date: '2027-03-31', row_version: 1 };
let session: Session;
const periods = Array.from({ length: 12 }, (_, index) => ({ id: `period-${index + 1}`, company_id: COMPANY, fiscal_year_id: YEAR,
  code: `P${index + 1}`, sequence: index + 1, start_date: new Date(Date.UTC(2026, 3 + index, 1)).toISOString().slice(0, 10),
  end_date: new Date(Date.UTC(2026, 4 + index, 0)).toISOString().slice(0, 10), status: 'FUTURE', row_version: 1 }));
const metadata = { fields: ['start_year', 'status', 'reason', 'expected_version'].map(key => ({ key, label: key === 'start_year' ? 'Starting year' : key, visible: true, readable: true, writable: true, required: true, definition: {} })) };
async function answer(_service: string, path: string, request?: { method?: string; body?: unknown }) {
  if (path.endsWith('display-config')) return { base_currency: 'INR', date_format: 'dd MMM yyyy' };
  if (path.includes('field-sets')) return metadata;
  if (path.endsWith('/fiscal-years/next-preview')) return { company_id: COMPANY, start_year: 2027 };
  if (path.endsWith('/financial-setup')) return { company_id: COMPANY, fiscal_year_start_month: 4, fiscal_year_start_day: 1, books_begin_date: '2026-10-23' };
  if (path.endsWith('/financial-setup/initialize')) return {};
  if (path.endsWith('/fiscal-years/generate')) return year;
  if (path.endsWith('/transition')) return { ...periods[0], status: 'OPEN', row_version: 2 };
  if (path.includes('/fiscal-periods?')) return { items: periods, page: { has_more: false, next_cursor: null } };
  if (path.includes('/fiscal-years?')) return { items: [year], page: { has_more: false, next_cursor: null } };
  if (path.includes('/v1/companies?')) return { items: [{ id: COMPANY, code: 'ACME', display_name: 'Acme', status: 'active' }], page: { has_more: false, next_cursor: null } };
  return year;
}
beforeEach(async () => {
  vi.clearAllMocks(); session = await sessionFor({ permissions });
  session.grants = [{ scope_type: 'company', scope_id: COMPANY, permissions, valid_from: '2020-01-01', valid_to: null }];
  vi.mocked(companyCall).mockImplementation(answer as never);
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
});
function mount(extra: { mode?: 'new'; yearId?: string; returnTo?: string } = {}) { return render(<CompanyFinancialYears session={session} companyId={COMPANY} companyName="Acme" {...extra} />); }
it('has real scoped company kebab links to view, edit and manage years', async () => {
  const user = userEvent.setup(); render(<CompanyDirectory session={session} />);
  await screen.findByRole('link', { name: 'Acme' }); await user.click(screen.getByRole('button', { name: /Actions for Acme/ }));
  expect(screen.getByRole('menuitem', { name: 'View company' })).toHaveAttribute('href', '/companies/' + COMPANY + '?returnTo=%2Fcompanies%2Fmanage');
  expect(screen.getByRole('menuitem', { name: 'Edit company' })).toHaveAttribute('href', '/companies/' + COMPANY + '/edit' + '?returnTo=%2Fcompanies%2Fmanage');
  expect(screen.getByRole('menuitem', { name: 'Manage years' })).toHaveAttribute('href', '/companies/' + COMPANY + '/years' + '?returnTo=%2Fcompanies%2Fmanage');
});
it('offers manage years from the working-company chooser without company.read', async () => {
  const user = userEvent.setup(); session.grants![0].permissions = ['period.read'];
  render(<Companies companies={[{ id: COMPANY, name: 'Acme', code: 'ACME', requiresStepUp: false, isDefault: false }]} canCreate={false} note={null} openCompanyId={COMPANY} grants={session.grants} />);
  await user.click(screen.getByRole('button', { name: /Actions for Acme/ }));
  expect(screen.getByRole('menuitem', { name: 'Manage years' })).toHaveAttribute('href', '/companies/' + COMPANY + '/years');
  expect(screen.queryByRole('menuitem', { name: 'View company' })).not.toBeInTheDocument();
});
it('refuses company/year routes outside the grant and direct generation by readers', async () => {
  session.grants![0].scope_id = YEAR;
  const first = render(await CompanyYearPage({ companyId: COMPANY }));
  expect(screen.getByText(/needs period.read for this company/)).toBeVisible(); expect(companyCall).not.toHaveBeenCalled(); first.unmount();
  session.grants![0].scope_id = COMPANY; session.grants![0].permissions = ['period.read'];
  render(await CompanyYearPage({ companyId: COMPANY, mode: 'new' }));
  expect(screen.getByText(/Generating years needs/)).toBeVisible();
});
it('lists years with a durable kebab destination and a separate generation page', async () => {
  const user = userEvent.setup(); mount();
  expect(await screen.findByRole('link', { name: 'FY2026-2027' })).toHaveAttribute('href', `/companies/${COMPANY}/years/${YEAR}?returnTo=` + encodeURIComponent(`/companies/${COMPANY}/years?returnTo=` + encodeURIComponent(`/companies/${COMPANY}`)));
  expect(screen.getByRole('link', { name: 'Generate year' })).toHaveAttribute('href', `/companies/${COMPANY}/years/new?returnTo=` + encodeURIComponent(`/companies/${COMPANY}/years?returnTo=` + encodeURIComponent(`/companies/${COMPANY}`)));
  await user.click(screen.getByRole('button', { name: /Actions for FY2026/ }));
  expect(screen.getByRole('menuitem', { name: 'View year and manage periods' })).toHaveAttribute('href', `/companies/${COMPANY}/years/${YEAR}?returnTo=` + encodeURIComponent(`/companies/${COMPANY}/years?returnTo=` + encodeURIComponent(`/companies/${COMPANY}`)));
});
it('keeps next-year and continuity destinations within safe administration navigation', () => {
  const next=`/companies/${COMPANY}/years/next?sourceYear=${YEAR}`;
  expect(administrationReturn('companies',next)).toBe(next);
  expect(administrationReturn('companies',`/companies/${COMPANY}/years/${YEAR}/continuity`)).toBe(`/companies/${COMPANY}/years/${YEAR}/continuity`);
  expect(administrationReturn('companies',next+'&returnTo=https://outside.invalid')).toBe(next);
});
it('guards direct next-year and continuity pages against missing and wrong-company grants', async () => {
  session.grants![0].permissions=['period.read'];
  const first=render(await NextYearPage({params:Promise.resolve({companyId:COMPANY})}));
  expect(screen.getByText(/Generating years needs/)).toBeVisible();expect(companyCall).not.toHaveBeenCalled();first.unmount();
  session.grants![0].permissions=['report.read','period.read'];session.grants![0].scope_id=YEAR;
  render(await ContinuityPage({params:Promise.resolve({companyId:COMPANY,yearId:YEAR})}));
  expect(screen.getByText(/Opening-balance review needs/)).toBeVisible();expect(companyCall).not.toHaveBeenCalled();
});
it('rejects malformed next-year source identifiers before reading company data',async()=>{
  render(await NextYearPage({params:Promise.resolve({companyId:COMPANY}),searchParams:Promise.resolve({sourceYear:'bad'})}));
  expect(screen.getByText(/Company or financial year not found/)).toBeVisible();expect(companyCall).not.toHaveBeenCalled();
});
it('returns to company settings and preserves that origin for year details and generation', async () => {
  mount({ returnTo: '/settings' });
  expect(screen.getByRole('link', { name: 'Back to company settings' })).toHaveAttribute('href', '/settings');
  const parent = `/companies/${COMPANY}/years?returnTo=%2Fsettings`;
  expect(await screen.findByRole('link', { name: 'FY2026-2027' })).toHaveAttribute('href', `/companies/${COMPANY}/years/${YEAR}?returnTo=` + encodeURIComponent(parent));
  expect(screen.getByRole('link', { name: 'Generate year' })).toHaveAttribute('href', `/companies/${COMPANY}/years/new?returnTo=` + encodeURIComponent(parent));
});
it('previews company-derived dates and rejects invalid years before mutation', async () => {
  const user = userEvent.setup(); mount({ mode: 'new' });
  const input = await screen.findByRole('textbox', { name: 'Starting year' });
  await waitFor(() => expect(input).toHaveValue('2027'));
  expect(screen.getByText('01 Apr 2027')).toBeVisible(); expect(screen.getByText('31 Mar 2028')).toBeVisible();
  await user.clear(input); await user.type(input, '1899'); await user.click(screen.getByRole('button', { name: 'Generate year' }));
  expect(screen.getByText(/Enter a whole starting year/)).toBeVisible();
  expect(input).toHaveFocus();
  expect(vi.mocked(companyCall).mock.calls.some(call => call[2]?.method === 'POST')).toBe(false);
});
it('keeps the same generation key after a lost response and follows the returned year', async () => {
  const user = userEvent.setup(); let commands = 0;
  vi.mocked(companyCall).mockImplementation(async (service, path, request) => {
    if (path.endsWith('/generate') && ++commands === 1) throw { status: 503, message: 'Response unavailable.' };
    return answer(service, path, request) as never;
  }); mount({ mode: 'new' });
  await screen.findByRole('textbox', { name: 'Starting year' });
  await user.click(screen.getByRole('button', { name: 'Generate year' })); await screen.findByText('Response unavailable.');
  expect(screen.getByRole('textbox', { name: 'Starting year' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Retry same year generation' }));
  await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/companies/${COMPANY}/years/${YEAR}?returnTo=` + encodeURIComponent(`/companies/${COMPANY}/years`)));
  const calls = vi.mocked(companyCall).mock.calls.filter(call => call[1].endsWith('/generate'));
  expect(calls[0][2]?.key).toBeTruthy(); expect(calls[1][2]?.key).toBe(calls[0][2]?.key);
  expect(calls[0][2]?.body).toEqual({ start_year: 2027 });
});
it('retains an interrupted period change across closing and reopening the review', async () => {
  const answer = vi.mocked(companyCall).getMockImplementation()!; let attempts = 0;
  vi.mocked(companyCall).mockImplementation((service, path, request) => path.endsWith('/transition') && attempts++ === 0
    ? Promise.reject({ status: 503, message: 'Period change unconfirmed' }) : answer(service, path, request));
  const user = userEvent.setup(); mount({ yearId: YEAR });
  await user.click(await screen.findByRole('button', { name: 'Actions for P1' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open period' }));
  await user.type(screen.getByRole('textbox', { name: 'Reason for status change' }), 'Ready for posting');
  await user.click(screen.getByRole('button', { name: 'Open period' }));
  await screen.findByText('Period change unconfirmed');
  expect(screen.getByRole('textbox', { name: 'Reason for status change' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Cancel' }));
  await user.click(screen.getByRole('button', { name: 'Recover period change' }));
  await user.click(screen.getByRole('button', { name: 'Retry same period change' }));
  expect(await screen.findByText('Open period completed.')).toBeVisible();
  const calls = vi.mocked(companyCall).mock.calls.filter(call => call[1].endsWith('/transition'));
  expect(calls[0][2]?.key).toBe(calls[1][2]?.key); expect(calls[0][2]?.body).toEqual(calls[1][2]?.body);
});
it('views twelve periods and validates the reason before opening with the displayed version', async () => {
  const user = userEvent.setup(); mount({ yearId: YEAR });
  await screen.findByText('P1'); await user.click(screen.getByRole('button', { name: 'Actions for P1' }));
  await user.click(screen.getByRole('menuitem', { name: 'Open period' }));
  await user.click(screen.getByRole('button', { name: 'Open period' }));
  expect(screen.getByText(/Give a reason/)).toBeVisible();
  await user.type(screen.getByRole('textbox', { name: 'Reason for status change' }), 'Ready for entries');
  await user.click(screen.getByRole('button', { name: 'Open period' }));
  expect(await screen.findByText('Open period completed.')).toBeVisible();
  expect(companyCall).toHaveBeenCalledWith('accounting', `/v1/companies/${COMPANY}/fiscal-periods/period-1/transition`, expect.objectContaining({
    method: 'POST', body: { status: 'OPEN', reason: 'Ready for entries', expected_version: 1 }, key: expect.any(String),
  }));
});
it('disables changes when calendar/status fields are incomplete', async () => {
  vi.mocked(companyCall).mockImplementation(async (service, path, request) => path.includes('fiscal-periods?')
    ? { items: periods.slice(0, 2), page: { has_more: false, next_cursor: null } } as never : answer(service, path, request) as never);
  mount({ yearId: YEAR }); expect(await screen.findByText(/complete twelve-period calendar/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Actions for P1' })).not.toBeInTheDocument();
});
it('does not expose generation or mutation controls to readers', async () => {
  session.grants![0].permissions = ['period.read']; mount({ yearId: YEAR }); await screen.findByText('P1');
  expect(screen.queryByRole('link', { name: 'Generate year' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Actions for P1' })).not.toBeInTheDocument();
});
it.each([403, 404, 503])('shows a clear year error (%s) without period changes', async status => {
  vi.mocked(companyCall).mockImplementation(async (service, path, request) => path.endsWith('/fiscal-years/' + YEAR)
    ? Promise.reject({ status, message: 'Year unavailable.' }) : answer(service, path, request) as never);
  mount({ yearId: YEAR });
  expect(await screen.findByText(status === 404 ? /not found for this company/ : 'Year unavailable.')).toBeVisible();
  expect(screen.queryByText('P1')).not.toBeInTheDocument();
});

it('reviews changed books settings before a version/hash protected reconciliation', async () => {
  const user = userEvent.setup(), saved = vi.fn();
  vi.mocked(companyCall).mockImplementation(async (_service, path) => path.endsWith('/reconciliation-review') ? {
    expected_version: 3, configuration_hash: 'b'.repeat(64), changes: [{ field: 'books_begin_date', before: '2026-04-01', after: '2026-10-23' }],
  } as never : {} as never);
  render(<CompanyBooksRecovery companyId={COMPANY} onSaved={saved} />);
  await user.click(screen.getByRole('button', { name: 'Review books setup' }));
  expect(await screen.findByText('2026-04-01 → 2026-10-23')).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Reconcile unused books' }));
  expect(screen.getByText(/Give a reason/)).toBeVisible();
  await user.type(screen.getByRole('textbox', { name: 'Reason for books reconciliation' }), 'Correct starting books date');
  await user.click(screen.getByRole('button', { name: 'Reconcile unused books' }));
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
  expect(companyCall).toHaveBeenCalledWith('accounting', `/v1/companies/${COMPANY}/financial-setup/reconcile`, expect.objectContaining({
    method: 'POST', body: { expected_version: 3, configuration_hash: 'b'.repeat(64), reason: 'Correct starting books date' }, key: expect.any(String),
  }));
});
it('keeps a failed reconciliation review and reason available for correction', async () => {
  const user = userEvent.setup(); vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path.endsWith('/reconcile')) throw { status: 409, message: 'Posted books cannot be reconciled.' };
    return { expected_version: 1, configuration_hash: 'a'.repeat(64), changes: [{ field: 'books_begin_date', before: '2026-04-01', after: '2026-10-23' }] } as never;
  });
  render(<CompanyBooksRecovery companyId={COMPANY} onSaved={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Review books setup' }));
  await user.type(await screen.findByRole('textbox', { name: 'Reason for books reconciliation' }), 'Review unused setup');
  await user.click(screen.getByRole('button', { name: 'Reconcile unused books' }));
  expect(await screen.findByText('Posted books cannot be reconciled.')).toBeVisible();
  expect(screen.getByRole('textbox', { name: 'Reason for books reconciliation' })).toHaveValue('Review unused setup');
});
it('requires the explicit LOCK phrase for terminal locks', async () => {
  const user = userEvent.setup(); vi.mocked(companyCall).mockImplementation(async (service, path, request) => path.includes('/fiscal-periods?')
    ? { items: periods.map(period => ({ ...period, status: 'CLOSED' })), page: { has_more: false, next_cursor: null } } as never : answer(service, path, request) as never);
  mount({ yearId: YEAR }); await screen.findByText('P1');
  await user.click(screen.getByRole('button', { name: 'Actions for P1' }));
  await user.click(screen.getByRole('menuitem', { name: 'Lock period permanently' }));
  expect(screen.getByRole('button', { name: 'Lock period permanently' })).toBeDisabled();
  expect(screen.getByText(/Locking is permanent/)).toBeVisible();
});

it('keeps the filtered company origin after successful year generation', async () => {
  const user = userEvent.setup(), origin = `/companies/${COMPANY}/years?returnTo=` + encodeURIComponent('/companies/manage?q=Ac');
  mount({ mode: 'new', returnTo: origin });
  await screen.findByRole('textbox', { name: 'Starting year' });
  await user.click(screen.getByRole('button', { name: 'Generate year' }));
  await waitFor(() => expect(goTo).toHaveBeenCalledWith(`/companies/${COMPANY}/years/${YEAR}?returnTo=` + encodeURIComponent(origin)));
});
it('seats the financial-year search in the card’s filter bar so it shares the card gutter', async () => {
  mount(); await screen.findByRole('link', { name: 'FY2026-2027' });
  const bar = screen.getByLabelText('Search financial years').closest('.janso-filter-bar');
  expect(bar).not.toBeNull(); expect(bar!.parentElement).toHaveClass('janso-card');
});
