import { act, fireEvent, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ThemeProvider } from '@janso/ui';
import { AutomaticReportStatus } from '../app/components/AutomaticReportStatus';
import { AutomaticCompanySetup } from '../app/components/AutomaticCompanySetup';
import { overviewRequest } from '../app/lib/company-overview';
import { companyCall } from '../app/lib/company-api';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';
import { allowedReportRequest } from '../app/lib/report-request-policy';

vi.mock('../app/lib/company-overview', () => ({ overviewRequest: vi.fn() }));
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (e: unknown) => e }));
const company = '01990000-0000-7000-8000-000000000001';
const mount = (value: React.ReactNode) => render(<ThemeProvider initial="light">{value}</ThemeProvider>);
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });

it('shows preparation, automatically refreshes a completed generation, and retains the opening choice', async () => {
  vi.useFakeTimers();
  vi.mocked(overviewRequest).mockResolvedValueOnce({ company_id: company, state: 'PREPARING', generation_id: null, business_state: 'PREPARING' })
    .mockResolvedValue({ company_id: company, state: 'CURRENT', generation_id: company, business_state: 'OPENING_REQUIRED' });
  const ready = vi.fn(); mount(<AutomaticReportStatus company={company} onGeneration={ready} />);
  await act(async () => undefined);
  expect(screen.getByText(/Preparing your figures automatically/)).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(ready).toHaveBeenCalledOnce();
  expect(screen.getByRole('link', { name: 'Review opening balances' })).toHaveAttribute('href', '/settings/readiness');
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(ready).toHaveBeenCalledOnce();
});

it('does not expose a different company status and cancels polling on unmount', async () => {
  vi.mocked(overviewRequest).mockResolvedValue({ company_id: 'another', state: 'CURRENT', generation_id: company });
  const ready = vi.fn(); const rendered = mount(<AutomaticReportStatus company={company} onGeneration={ready} />);
  await act(async () => undefined);
  expect(ready).not.toHaveBeenCalled(); expect(screen.queryByText(/up to date/)).toBeNull();
  rendered.unmount();
  expect(vi.mocked(overviewRequest).mock.calls[0][0].signal?.aborted).toBe(true);
});

it('shows saved setup steps and gates retry by current UI permission', async () => {
  vi.mocked(companyCall).mockResolvedValue({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }, { key: 'reports', status: 'NEEDS_ACTION' }] });
  mount(<AutomaticCompanySetup company={company} canRetry={false} openingFinalized={false} />);
  await waitFor(() => expect(screen.getByText(/Your opening-balance choice/)).toBeVisible());
  expect(screen.queryByRole('button', { name: 'Complete remaining setup' })).toBeNull();
});

it('allows only the exact setup and source readiness routes', () => {
  expect(allowedCompanyRequest('identity', 'GET', `/v1/companies/${company}/setup`)).toBe(true);
  expect(allowedCompanyRequest('identity', 'POST', `/v1/companies/${company}/setup/retry`)).toBe(true);
  expect(allowedCompanyRequest('identity', 'GET', `/v1/companies/${company}/setup?other=1`)).toBe(false);
  expect(allowedReportRequest('GET', `/v2/companies/${company}/source-readiness`)).toBe(true);
  expect(allowedReportRequest('POST', `/v2/companies/${company}/source-readiness`)).toBe(false);
});

it('links an incomplete product configuration to its review screen', async () => {
  vi.mocked(companyCall).mockResolvedValue({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'catalog', status: 'NEEDS_ACTION', failure_code: 'PRODUCT_CONFIGURATION_REVIEW_REQUIRED' }] });
  mount(<AutomaticCompanySetup company={company} canRetry />);
  expect(await screen.findByRole('link', { name: 'Review product configuration' })).toHaveAttribute('href', '/products/configuration');
  expect(screen.getByText(/Existing drafts are preserved/)).toBeVisible();
});

it('shows completion only after the server reports complete', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'PENDING', steps: [] })
    .mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] });
  const complete = vi.fn();
  mount(<AutomaticCompanySetup company={company} canRetry={false} onComplete={complete} openingFinalized={false} />);
  await act(async () => undefined);
  expect(screen.getByText('Company saved. Setup is still running in the background.')).toBeVisible();
  expect(screen.queryByText('Automatic setup is complete.')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.getByText('Automatic preparation is complete. Opening balances still need your decision.')).toBeVisible();
  expect(screen.getByText(/Your opening-balance choice/)).toBeVisible();
  expect(complete).toHaveBeenCalledOnce();
});

it('refreshes a needs-review panel when setup completes elsewhere without resubmitting it', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'books', status: 'NEEDS_ACTION' }] })
    .mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'books', status: 'READY' }, { key: 'opening', status: 'AWAITING_OPENING' }] });
  const complete = vi.fn();
  mount(<AutomaticCompanySetup company={company} canRetry onComplete={complete} openingFinalized={false} />);
  await act(async () => undefined);
  expect(screen.getByText('Books: Needs review')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Complete remaining setup' })).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.getByText('Books: Ready')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Complete remaining setup' })).toBeNull();
  expect(screen.getByText('Opening balances: Your opening-balance choice is still needed')).toBeVisible();
  expect(complete).toHaveBeenCalledOnce();
  expect(vi.mocked(companyCall).mock.calls.every(([, , options]) => !options?.method)).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(companyCall).toHaveBeenCalledTimes(2);
});

it('uses current Accounting evidence after a deferred opening is finalised', async () => {
  vi.mocked(companyCall).mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] });
  mount(<AutomaticCompanySetup company={company} canRetry={false} openingFinalized />);
  expect(await screen.findByText('Opening balances: Finalised')).toBeVisible();
  expect(screen.getByText('Automatic setup is complete.')).toBeVisible();
  expect(screen.queryByText(/Opening balances still need your decision/)).toBeNull();
});

it('does not claim a deferred opening is still pending when current accounting evidence is unavailable', async () => {
  vi.mocked(companyCall).mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] });
  mount(<AutomaticCompanySetup company={company} canRetry={false} />);
  expect(await screen.findByText('Opening balances: Deferred during setup')).toBeVisible();
  expect(screen.queryByText(/Opening balances still need your decision/)).toBeNull();
});

it.each([401, 403])('explains setup access failure %s and clears stale progress', async status => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'PENDING', steps: [{ key: 'books', status: 'READY' }] })
    .mockRejectedValue({ status });
  mount(<AutomaticCompanySetup company={company} canRetry />);
  await act(async () => undefined);
  expect(screen.getByText('Books: Ready')).toBeVisible();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.getByText(status === 401 ? 'Sign in again to check company setup.' : 'Your access does not permit checking company setup.')).toBeVisible();
  expect(screen.queryByText('Books: Ready')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(companyCall).toHaveBeenCalledTimes(2);
});
it('shows a status check while the first setup read is pending', async () => {
  vi.mocked(companyCall).mockReturnValue(new Promise(() => {}));
  mount(<AutomaticCompanySetup company={company} canRetry={false} />);
  expect(screen.getByRole('status')).toHaveTextContent('Checking company setup');
  expect(screen.getByRole('progressbar', { name: 'Checking company setup…' })).not.toHaveAttribute('aria-valuenow');
});

it('shows verified step progress and stops the activity indicator when setup needs attention', async () => {
  vi.useFakeTimers();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'RUNNING', steps: [{ key: 'chart', status: 'READY' }, { key: 'books', status: 'RUNNING' }, { key: 'opening', status: 'AWAITING_OPENING' }] })
    .mockResolvedValue({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'chart', status: 'READY' }, { key: 'books', status: 'NEEDS_ACTION' }, { key: 'opening', status: 'AWAITING_OPENING' }] });
  mount(<AutomaticCompanySetup company={company} canRetry openingFinalized={false} />);
  await act(async () => undefined);
  const progress = screen.getByRole('progressbar', { name: 'Preparing books' });
  expect(progress).toHaveAttribute('aria-valuetext', '1 of 3 setup steps ready. You can open your company while setup continues.');
  expect(progress).not.toHaveAttribute('aria-valuenow');
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.queryByRole('progressbar')).toBeNull();
  expect(screen.getByRole('button', { name: 'Complete remaining setup' })).toBeEnabled();
});
it('distinguishes completed preparation from an outstanding opening decision', async () => {
  vi.mocked(companyCall).mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'opening', status: 'AWAITING_OPENING' }] });
  const complete = vi.fn();
  mount(<AutomaticCompanySetup company={company} canRetry={false} onComplete={complete} openingFinalized={false} />);
  expect(await screen.findByText('Automatic preparation is complete. Opening balances still need your decision.')).toBeVisible();
  expect(screen.queryByText('Automatic setup is complete.')).toBeNull();
  expect(complete).not.toHaveBeenCalled();
});

it.each(['NEEDS_ACTION', 'RETRY_WAIT'])('resumes %s setup once and refreshes the page after completion', async state => {
  vi.useFakeTimers();
  let release!: (value: unknown) => void;
  const pending = new Promise(resolve => { release = resolve; });
  const complete = vi.fn();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: state, steps: [] })
    .mockImplementationOnce(() => pending as never)
    .mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [] });
  mount(<AutomaticCompanySetup company={company} canRetry onComplete={complete} />);
  await act(async () => undefined);
  const button = screen.getByRole('button', { name: 'Complete remaining setup' });
  fireEvent.click(button);
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(companyCall).toHaveBeenCalledTimes(2);
  expect(vi.mocked(companyCall).mock.calls[1]).toEqual(['identity', `/v1/companies/${company}/setup/retry`, { method: 'POST' }]);
  await act(async () => { release({}); });
  expect(complete).toHaveBeenCalledOnce();
});

it('keeps a failed retry actionable without reporting completion', async () => {
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'calendar', status: 'PENDING' }] })
    .mockRejectedValue({ status: 503, message: 'Service temporarily unavailable.' });
  const complete = vi.fn(); mount(<AutomaticCompanySetup company={company} canRetry onComplete={complete} />);
  const button = await screen.findByRole('button', { name: 'Complete remaining setup' });
  expect(screen.getByText('Financial year: Waiting')).toBeVisible();
  fireEvent.click(button);
  expect(await screen.findByText('Service temporarily unavailable.')).toBeVisible();
  expect(button).toBeEnabled(); expect(complete).not.toHaveBeenCalled();
});

it('observes completed setup after the retry response is lost without sending the command twice', async () => {
  vi.useFakeTimers();
  const complete = vi.fn();
  vi.mocked(companyCall).mockResolvedValueOnce({ company_id: company, status: 'NEEDS_ACTION', steps: [{ key: 'books', status: 'NEEDS_ACTION' }] })
    .mockRejectedValueOnce({ status: 503, message: 'Retry could not be confirmed.' })
    .mockResolvedValue({ company_id: company, status: 'COMPLETE', steps: [{ key: 'books', status: 'READY' }] });
  mount(<AutomaticCompanySetup company={company} canRetry onComplete={complete} />);
  await act(async () => undefined);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Complete remaining setup' })); });
  expect(screen.getByText('Retry could not be confirmed.')).toBeVisible();
  expect(complete).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(screen.getByText('Books: Ready')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Complete remaining setup' })).toBeNull();
  expect(screen.queryByText('Retry could not be confirmed.')).toBeNull();
  expect(complete).toHaveBeenCalledOnce();
  expect(vi.mocked(companyCall).mock.calls.filter(([, , options]) => options?.method === 'POST')).toHaveLength(1);
});
