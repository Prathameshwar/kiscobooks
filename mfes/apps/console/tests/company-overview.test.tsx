vi.mock('../app/components/AutomaticReportStatus', () => ({ AutomaticReportStatus: () => null }));
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OverviewPage from '../app/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor, renderWithProviders } from './helpers';
import { CompanyOverview } from '../app/components/CompanyOverview';
import { OverviewView } from '../app/components/OverviewView';
import { anchorOf } from '../app/lib/overview-periods';
import { allowedReportRequest } from '../app/lib/report-request-policy';
import { serviceCall } from '../app/lib/service-call';
import { overviewFixture, type FixtureOptions } from './overview-fixture';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<object>(), serviceCall: vi.fn() }));
const company = '01234567-89ab-4cde-8fab-0123456789ab';
const fixtureFor = (params: URLSearchParams, options: Partial<FixtureOptions> = {}) =>
  overviewFixture({ company, from: params.get('date_from') ?? undefined, to: params.get('date_to') ?? undefined, ...options });

function serve(options: Partial<FixtureOptions> = {}) {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    const url = new URL(request.path, 'http://test.invalid');
    if (url.pathname.endsWith('/parties')) return { items: [{ id: company, company_id: company, name: 'QA customer' }], page: { next_cursor: null, limit: 50 } };
    return fixtureFor(url.searchParams, options);
  });
}
const overviewCalls = () => vi.mocked(serviceCall).mock.calls.map(call => new URL(call[1].path, 'http://test.invalid')).filter(url => url.pathname.endsWith('/overview'));

beforeEach(() => { vi.mocked(serviceCall).mockReset(); window.history.replaceState(null, '', '/'); });
afterEach(() => window.history.replaceState(null, '', '/'));

it('allows only a scoped GET overview through the product proxy', () => {
  expect(allowedReportRequest('GET', `/v2/companies/${company}/overview?fiscal_year_id=${company}`)).toBe(true);
  expect(allowedReportRequest('GET', `/v2/companies/${company}/overview?fiscal_year_id=${company}&date_from=2026-10-01&date_to=2026-11-01`)).toBe(true);
  expect(allowedReportRequest('POST', `/v2/companies/${company}/overview`)).toBe(false);
  expect(allowedReportRequest('GET', `/v2/companies/${company}/overview/other`)).toBe(false);
});

describe('the finished page', () => {
  it('leads with the four figures a business owner asks about, from verified totals', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers companyName="Janso Retail" yearLabel="FY 2026-27" />);
    expect(await screen.findByText('Cash and bank')).toBeVisible();
    const tile = (label: string) => within(screen.getByText(label, { selector: '.janso-stat__label-text' }).closest('.janso-stat') as HTMLElement);
    expect(tile('Cash and bank').getByText('₹5,000.00')).toBeVisible();
    expect(tile('Receivables').getByText('₹3,000.00')).toBeVisible();
    expect(tile('Payables').getByText('₹500.00')).toBeVisible();
    expect(tile('Net result').getByText('₹1,600.00')).toBeVisible();
    expect(screen.getByText('Surplus · income less expenses')).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Business overview' })).toBeVisible();
    expect(screen.getByText('Janso Retail · FY 2026-27')).toBeVisible();
  });

  it('draws income beside expenses by week, with a legend and a table twin', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    const chart = await screen.findByRole('img', { name: /Income and expenses per week, 01 Oct 2026/ });
    expect(chart).toBeVisible();
    const legend = screen.getByRole('list', { name: 'Legend' });
    expect(within(legend).getByText('Income')).toBeVisible();
    expect(within(legend).getByText('Expenses')).toBeVisible();
    expect(screen.getAllByRole('table', { hidden: true }).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: /Profit and loss/ })).toHaveAttribute('href', '/reports/workspace?report=PROFIT_LOSS');
  });

  it('keeps concise figure definitions collapsed and flags a late history start once', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText(/History from 01 Oct 2026/)).toBeVisible();
    expect(screen.getByText('About these figures')).toBeVisible();
    const details = screen.getByText('About these figures').closest('details')!;
    expect(details).not.toHaveAttribute('open');
    expect(within(details).getByText('01 Nov 2026 · includes opening balances.')).toBeInTheDocument();
    expect(within(details).getByText(/Excludes opening balances and imported YTD summaries/)).toBeInTheDocument();
    expect(within(details).getByText('After credits and advances.')).toBeInTheDocument();
    expect(within(details).getByRole('link', { name: 'Report sources', hidden: true })).toHaveAttribute('href', '/reports/workspace');
    expect(within(details).queryByText(/These figures come from|Ledger history in this snapshot|Invoicing, stock and risk/)).not.toBeInTheDocument();
    expect(screen.getByText(/As of 01 Nov 2026, 09:14/)).toBeVisible();
  });

  it('omits the history chip when the whole year is covered', async () => {
    serve({ change: { coverage_start: '2026-04-01', earlier_history_unavailable: false } });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    await screen.findByText('Cash and bank');
    expect(screen.queryByText(/History from/)).not.toBeInTheDocument();
  });

  it('formats money from the company display config, including a western grouping and another currency', async () => {
    serve({ change: { currency: 'EUR' } });
    const display = { ...(await sessionFor()).display, currency: 'EUR', currencySymbol: '€', digitGrouping: 'western' as const };
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />, { display });
    expect(await screen.findByText('€5,000.00')).toBeVisible();
  });

  it('never prints a symbol the source currency does not match', async () => {
    serve({ change: { currency: 'USD' } });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText('5,000.00 USD')).toBeVisible();
    expect(screen.queryByText(/₹/)).not.toBeInTheDocument();
  });

  it('shows a deficit with its own word and glyph, not colour alone', async () => {
    serve({ from: '2026-10-01', to: '2026-10-01', daily: () => ({ income: 0, expenses: 10_000 }) });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText('-₹100.00')).toBeVisible();
    expect(screen.getByText('Deficit · income less expenses')).toBeVisible();
  });
});

describe('open bills, customers and expenses', () => {
  const open = async (options: Partial<FixtureOptions> = {}, canReadCustomers = true) => {
    serve(options);
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={canReadCustomers} />);
    await screen.findByText('Cash and bank');
  };

  it('shows the cash trend and what is late beside the receivable and payable figures', async () => {
    await open();
    expect(screen.getByRole('img', { name: /Cash and bank balance by day, 01 Oct 2026/ })).toBeInTheDocument();
    expect(screen.getByText(/Owed by customers/)).toBeVisible();
    expect(screen.getByText('2.0K overdue bills')).toBeVisible();
    expect(screen.getByText('300.00 overdue bills')).toBeVisible();
  });

  it('ages receivables into labelled rows that reconcile to the figure on the tile', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 3, name: 'Bills by age' })).toBeVisible();
    expect(screen.getByText(/overdue of/)).toHaveTextContent('₹2,000.00 overdue of ₹3,500.00 in open customer bills');
    for (const [label, amount] of [['Not yet due', '₹1,500.00'], ['1–30 days overdue', '₹1,000.00'], ['31–60 days overdue', '₹600.00'], ['61–90 days overdue', '₹400.00'], ['Over 90 days overdue', '₹0.00']]) {
      const row = screen.getByText(label).closest('.janso-list-row') as HTMLElement;
      expect(within(row).getByText(amount)).toBeVisible();
    }
    expect(screen.queryByText('No due date')).not.toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Share — Not yet due' })).toHaveAttribute('aria-valuetext', '43%');
    expect(screen.getByText(/Less advances and credits/)).toHaveTextContent('Less advances and credits ₹500.00, leaving ₹3,000.00 net');
  });

  it('switches the ageing card to payables on a radiogroup that arrow keys also drive', async () => {
    await open();
    const group = screen.getByRole('radiogroup', { name: 'Bills to show' });
    const payables = within(group).getByRole('radio', { name: 'Payables' });
    fireEvent.click(payables);
    expect(screen.getByText(/overdue of/)).toHaveTextContent('₹300.00 overdue of ₹700.00 in open supplier bills');
    expect(payables).toBeChecked();
    fireEvent.keyDown(group, { key: 'ArrowLeft' });
    expect(screen.getByText(/overdue of/)).toHaveTextContent('open customer bills');
  });

  it('lists the largest balances, each linking to the native party ledger, with lateness as text', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 3, name: 'Who owes you' })).toBeVisible();
    const link = screen.getByRole('link', { name: 'Meridian Wholesale' });
    expect(link).toHaveAttribute('href', '/reports/workspace?report=PARTY_LEDGER&party_id=01234561-89ab-4cde-8fab-0123456789ab');
    const row = link.closest('.janso-list-row') as HTMLElement;
    expect(within(row).getByText('₹2,000.00')).toBeVisible();
    expect(within(row).getByText(/₹1,400\.00 in overdue bills/)).toBeVisible();
    expect(screen.getByRole('link', { name: /Customer directory/ })).toHaveAttribute('href', '/accounting/parties?role=CUSTOMER');
    expect(screen.getByRole('combobox', { name: 'Find customer ledger' })).toBeVisible();
  });

  it('switches the people card to suppliers and drops the customer-only search', async () => {
    await open();
    const group = screen.getByRole('radiogroup', { name: 'Balances to show' });
    fireEvent.click(within(group).getByRole('radio', { name: 'Suppliers' }));
    expect(screen.getByRole('heading', { level: 3, name: 'Whom you owe' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Sunridge Packaging' })).toBeVisible();
    expect(screen.getByRole('link', { name: /Supplier directory/ })).toHaveAttribute('href', '/accounting/suppliers');
    expect(screen.queryByRole('combobox', { name: 'Find customer ledger' })).not.toBeInTheDocument();
  });

  it('keeps party tools behind party access while the balances still show', async () => {
    await open({}, false);
    expect(screen.getByRole('link', { name: 'Meridian Wholesale' })).toBeVisible();
    expect(screen.queryByRole('combobox', { name: 'Find customer ledger' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Customer directory/ })).not.toBeInTheDocument();
  });

  it('shows where money went with the rest as one line, so the rows add up', async () => {
    await open();
    expect(screen.getByRole('heading', { level: 3, name: 'Where money went' })).toBeVisible();
    const rent = screen.getByText('Rent').closest('.janso-list-row') as HTMLElement;
    expect(within(rent).getByText('₹420.00')).toBeVisible();
    const other = screen.getByText('All other expenses').closest('.janso-list-row') as HTMLElement;
    expect(within(other).getByText('₹322.00')).toBeVisible();
  });

  it('keeps a negative "all other expenses" so the rows still add up, and bases the shares on the positive rows', async () => {
    const total = 1400;
    await open({ change: { top_expenses: [{ account_id: '01234561-89ab-4cde-8fab-0123456789ab', name: 'Purchases', amount: (total + 100).toFixed(4) }], other_expenses: '-100.0000' } });
    const purchases = screen.getByText('Purchases').closest('.janso-list-row') as HTMLElement;
    expect(within(purchases).getByText('₹1,500.00')).toBeVisible();
    expect(within(purchases).getByRole('progressbar')).toHaveAttribute('aria-valuetext', '100%');
    const other = screen.getByText('All other expenses').closest('.janso-list-row') as HTMLElement;
    expect(within(other).getByText('-₹100.00')).toBeVisible();
    expect(within(other).queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('does not say "owed by customers" when advances outweigh the bills', async () => {
    const base = overviewFixture({ company });
    const zero = '0.0000';
    await open({ change: {
      totals: { ...base.totals, net_receivable: '-50.0000' },
      receivables: { ...base.receivables, gross: '100.0000', advances: '150.0000', net: '-50.0000', overdue: zero, parties: [],
        buckets: { current: '100.0000', days_1_30: zero, days_31_60: zero, days_61_90: zero, days_over_90: zero, unknown: zero } },
    } });
    const tile = within(screen.getByText('Receivables', { selector: '.janso-stat__label-text' }).closest('.janso-stat') as HTMLElement);
    expect(tile.getByText('-₹50.00')).toBeVisible();
    expect(tile.getByText('Customer advances exceed bills')).toBeVisible();
    expect(tile.queryByText(/Owed by customers/)).not.toBeInTheDocument();
  });

  it('says so plainly when there is nothing outstanding or spent', async () => {
    await open({ quiet: true });
    expect(screen.getByText('Nothing is owed to you right now.')).toBeVisible();
    expect(screen.getByText('No customer has an open balance.')).toBeVisible();
    expect(screen.getByText('No expenses were posted in this period.')).toBeVisible();
    expect(screen.queryByText(/overdue of/)).not.toBeInTheDocument();
    // nothing is late, so the tiles say who owes whom and nothing about lateness
    expect(screen.getByText('Owed by customers')).toBeVisible();
    expect(screen.getByText('Owed to suppliers')).toBeVisible();
    expect(screen.queryByText(/overdue bills/)).not.toBeInTheDocument();
  });
});

describe('safety of what the page links and says', () => {
  it.each([
    ['surplus', {}, 'success'],
    ['deficit', { from: '2026-10-01', to: '2026-10-01', daily: () => ({ income: 0, expenses: 10_000 }) }, 'danger'],
    ['break-even', { from: '2026-10-01', to: '2026-10-01', daily: () => ({ income: 5_000, expenses: 5_000 }) }, 'default'],
  ] as const)('marks a %s net result with its own tone', async (_name, options, tone) => {
    serve(options as Partial<FixtureOptions>);
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    await screen.findByText('Cash and bank');
    const tile = screen.getByText('Net result', { selector: '.janso-stat__label-text' }).closest('.janso-stat');
    expect(tile).toHaveAttribute('data-tone', tone);
  });

  it('encodes a party identifier into its ledger link, whatever the view is handed', async () => {
    // the verifier refuses such an identifier before the view ever sees it; this is the view's own defence
    const data = overviewFixture({ company });
    data.receivables.parties[0]!.party_id = 'a&b c#d';
    await renderWithProviders(<OverviewView data={data} anchor={anchorOf(data)} period="ytd" onPeriod={() => undefined} refreshing={false}
      onRefresh={() => undefined} company={company} canReadCustomers links={{}} />);
    expect(screen.getByRole('link', { name: 'Meridian Wholesale' })).toHaveAttribute('href', '/reports/workspace?report=PARTY_LEDGER&party_id=a%26b%20c%23d');
  });
});

describe('choosing a period', () => {
  it('offers the presets, clamped to retained history, and starts on year to date', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    const select = await screen.findByRole('combobox', { name: 'Period' });
    await waitFor(() => expect(select).toBeEnabled());
    expect(select).toHaveValue('ytd');
    expect(within(select).getByRole('option', { name: 'Year to date · from 01 Oct 2026' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'This quarter' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'This month' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'Last 30 days' })).toBeInTheDocument();
    expect(overviewCalls()).toHaveLength(1);
    expect(overviewCalls()[0]!.searchParams.has('date_from')).toBe(false);
  });

  it('requests the preset range from the company’s own today, keeps the figures meanwhile and records the choice in the URL', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    const select = await screen.findByRole('combobox', { name: 'Period' });
    await waitFor(() => expect(select).toBeEnabled());
    let release: () => void = () => undefined;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const original = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => { await gate; return original(...args); });
    fireEvent.change(select, { target: { value: '30d' } });
    // previous figures stay on screen while the next period loads
    expect(screen.getByText('₹5,000.00')).toBeVisible();
    // refreshing says so in words, and the control is aria-disabled rather than disabled so focus stays on it
    expect(screen.getByText('Updating…')).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('Updating the overview');
    expect(screen.getByRole('button', { name: 'Refresh overview' })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: 'Refresh overview' })).toBeEnabled();
    await act(async () => { release(); await gate; });
    await waitFor(() => expect(screen.getByRole('img', { name: /Income and expenses per day, 03 Oct 2026/ })).toBeVisible());
    const last = overviewCalls().at(-1)!;
    expect(last.searchParams.get('date_from')).toBe('2026-10-03');
    expect(last.searchParams.get('date_to')).toBe('2026-11-01');
    expect(window.location.search).toBe('?period=30d');
    fireEvent.change(select, { target: { value: 'ytd' } });
    await waitFor(() => expect(window.location.search).toBe(''));
  });

  it('changes only the period in the URL, keeping other parameters and the hash', async () => {
    serve();
    window.history.replaceState(null, '', '/?tab=a#top');
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    const select = await screen.findByRole('combobox', { name: 'Period' });
    await waitFor(() => expect(select).toBeEnabled());
    fireEvent.change(select, { target: { value: '30d' } });
    await waitFor(() => expect(window.location.search).toBe('?tab=a&period=30d'));
    expect(window.location.hash).toBe('#top');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh overview' })).not.toHaveAttribute('aria-disabled', 'true'));
    fireEvent.change(select, { target: { value: 'ytd' } });
    await waitFor(() => expect(window.location.search).toBe('?tab=a'));
  });

  it('resolves a non-default period from the URL after one default read', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} initialPeriod="30d" />);
    await screen.findByText('Cash and bank');
    const calls = overviewCalls();
    expect(calls).toHaveLength(2);
    expect(calls[0]!.searchParams.has('date_from')).toBe(false);
    expect(calls[1]!.searchParams.get('date_from')).toBe('2026-10-03');
    expect(calls[1]!.searchParams.get('date_to')).toBe('2026-11-01');
    expect(screen.getByRole('combobox', { name: 'Period' })).toHaveValue('30d');
  });

  it('treats an unrecognised period as the default', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} initialPeriod="<script>" />);
    await screen.findByText('Cash and bank');
    expect(overviewCalls()).toHaveLength(1);
    expect(screen.getByRole('combobox', { name: 'Period' })).toHaveValue('ytd');
  });

  it('refreshes the same scoped view on request', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    await screen.findByText('Cash and bank');
    fireEvent.click(screen.getByRole('button', { name: 'Refresh overview' }));
    await waitFor(() => expect(overviewCalls()).toHaveLength(2));
    expect(await screen.findByText('Cash and bank')).toBeVisible();
  });

  it.each([401, 403, 404])('clears retained figures when refreshed access is refused with %i', async status => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    await screen.findByText('Cash and bank');
    vi.mocked(serviceCall).mockRejectedValue({ status, message: 'Access is no longer available' });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh overview' }));
    await waitFor(() => expect(screen.queryByText('Cash and bank')).not.toBeInTheDocument());
  });

  it('keeps verified figures and discloses a temporary refresh failure', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    await screen.findByText('Cash and bank');
    vi.mocked(serviceCall).mockRejectedValue({ status: 503, message: 'Temporarily unavailable' });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh overview' }));
    expect(await screen.findByText(/figures below show the last verified period/)).toBeVisible();
    expect(screen.getByText('Cash and bank')).toBeVisible();
  });

  it('refuses a response that is not the range that was asked for', async () => {
    vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
      const params = new URL(request.path, 'http://test.invalid').searchParams;
      return params.has('date_from') ? fixtureFor(new URLSearchParams()) : fixtureFor(params);
    });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} initialPeriod="month" />);
    expect(await screen.findByText(/overview could not be verified/)).toBeVisible();
    expect(screen.queryByText('Cash and bank')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show year to date' })).toBeVisible();
  });
});

describe('when there is nothing to show', () => {
  it('says nothing is posted, keeps verified balances, and offers only permitted next steps', async () => {
    serve({ daily: () => ({ income: 0, expenses: 0 }) });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} links={{ voucher: '/vouchers/new/sales', opening: '/accounting/opening' }} />);
    expect(await screen.findByText('Nothing posted in this period')).toBeVisible();
    expect(screen.getByText('₹5,000.00')).toBeVisible();
    expect(screen.getByText('No activity posted in this period')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Enter a voucher' })).toHaveAttribute('href', '/vouchers/new/sales');
    expect(screen.getByRole('link', { name: 'Review opening balances' })).toHaveAttribute('href', '/accounting/opening');
    expect(screen.queryByRole('img', { name: /Income and expenses per/ })).not.toBeInTheDocument();
  });

  it('offers no next step the reader may not take', async () => {
    serve({ quiet: true });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText('Nothing posted in this period')).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Enter a voucher' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Review opening balances' })).not.toBeInTheDocument();
  });

  it('shows a loading placeholder first', async () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(screen.getByRole('status', { name: 'Loading company overview' })).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Business overview' })).toBeVisible();
  });

  it('explains an unprepared source as a step to take, then recovers on retry', async () => {
    vi.mocked(serviceCall).mockRejectedValueOnce({ status: 409, message: 'refresh and verify a company source before opening the overview' });
    serveAfterFailure();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText('Preparing your figures')).toBeVisible();
    expect(screen.getByText(/verify a company source/)).toBeVisible();
    expect(screen.getByRole('link', { name: 'View company readiness' })).toHaveAttribute('href', '/settings/readiness');
    expect(screen.queryByRole('button', { name: 'Show year to date' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry overview' }));
    expect(await screen.findByText('Cash and bank')).toBeVisible();
  });

  it('does not tell the reader to refresh sources for a conflict a refresh cannot cure', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 409, message: 'party open items do not reconcile to the as-of general ledger' });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText('Something went wrong')).toBeVisible();
    expect(screen.getByText(/do not reconcile/)).toBeVisible();
    expect(screen.queryByText('Preparing your figures')).not.toBeInTheDocument();
  });

  it.each([[500, 'Something went wrong'], [403, "You don't have access to this"]])('renders a %i as the intended state, never a blank page', async (status, title) => {
    vi.mocked(serviceCall).mockRejectedValue({ status, message: 'upstream detail' });
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText(title)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Retry overview' })).toBeVisible();
  });

  it('refuses a wrong-company payload and recovers on retry', async () => {
    vi.mocked(serviceCall).mockResolvedValueOnce({ ...fixtureFor(new URLSearchParams()), company_id: '11234567-89ab-4cde-8fab-0123456789ab' });
    serveAfterFailure();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers={false} />);
    expect(await screen.findByText(/overview could not be verified/)).toBeVisible();
    expect(screen.queryByText('Cash and bank')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry overview' }));
    expect(await screen.findByText('Cash and bank')).toBeVisible();
  });
});

function serveAfterFailure() {
  const fallback = (_endpoint: string, request: { path: string }) => Promise.resolve(fixtureFor(new URL(request.path, 'http://test.invalid').searchParams));
  vi.mocked(serviceCall).mockImplementation(fallback as never);
}

describe('customer ledger', () => {
  it('opens the selected customer in the native party ledger workspace', async () => {
    serve();
    await renderWithProviders(<CompanyOverview company={company} yearId={company} canReadCustomers />);
    const control = await screen.findByRole('combobox', { name: 'Find customer ledger' });
    fireEvent.focus(control);
    fireEvent.click(await screen.findByRole('option', { name: /QA customer/ }));
    expect(screen.getByRole('link', { name: 'Open customer ledger' })).toHaveAttribute('href', '/reports/workspace?report=PARTY_LEDGER&party_id=' + company);
    expect(screen.getByRole('link', { name: 'Customer directory' })).toHaveAttribute('href', '/accounting/parties?role=CUSTOMER');
  });
});

describe('the page', () => {
  async function open(permissions: string[], query: { period?: string } = {}) {
    const session = await sessionFor({ permissions: ['report.read'] }); session.company = { id: company, name: 'Current company' };
    session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2020-01-01', valid_to: null }];
    vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor({ fiscalYear: { id: company, code: 'FY 2026-27', startDate: '2026-04-01', endDate: '2027-03-31', current: true, open: true } }) });
    render(await OverviewPage({ searchParams: Promise.resolve(query) }));
  }

  it('uses company-scoped overview access, naming the company and year', async () => {
    serve();
    await open(['report.read']);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Business overview' })).toBeVisible());
    expect(await screen.findByText('Current company · FY 2026-27')).toBeVisible();
    expect(overviewCalls()[0]!.searchParams.get('fiscal_year_id')).toBe(company);
  });

  it('opens on the period named in the URL', async () => {
    serve();
    await open(['report.read'], { period: 'month' });
    await screen.findByText('Cash and bank');
    expect(overviewCalls().at(-1)!.searchParams.get('date_from')).toBe('2026-11-01');
  });

  it('offers next steps only for permissions the reader holds', async () => {
    serve({ quiet: true });
    await open(['report.read', 'vouchers.create']);
    expect(await screen.findByRole('link', { name: 'Enter a voucher' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Review opening balances' })).not.toBeInTheDocument();
  });

  it('explains missing report access instead of loading anything', async () => {
    serve();
    await open([]);
    expect(await screen.findByText('Company figures need report access')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Business overview' })).toBeVisible();
    expect(overviewCalls()).toHaveLength(0);
  });
});
