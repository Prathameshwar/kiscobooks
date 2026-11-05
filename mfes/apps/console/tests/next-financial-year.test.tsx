import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { NextFinancialYear } from '../app/components/NextFinancialYear';
import { companyCall, openCompany } from '../app/lib/company-api';
import { goTo } from '../app/lib/navigate';
import { sessionFor } from './helpers';
import type { Session } from '../app/session';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), openCompany: vi.fn(), companyFailure: (error: unknown) => error }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), stepUpUrl: (id: string) => '/verify/' + id }));
const COMPANY = '01990000-0000-7000-8000-000000000001', YEAR = '01990000-0000-7000-8000-000000000002';
const permissions = ['period.read', 'period.manage', 'accounting.finance.read', 'ledger.read', 'report.read'];
const preview = { company_id: COMPANY, start_year: 2027, code: 'FY2027-2028', start_date: '2027-04-01', end_date: '2028-03-31',
  source_year: { id: 'source', code: 'FY2026-2027' }, existing_year_id: null, can_generate: true, blockers: [], periods: [] };
let session: Session, rows: Array<{ id: string; company_id: string; fiscal_year_id: string; code: string; sequence: number; start_date: string; end_date: string; status: string; row_version: number }>;
const api = vi.mocked(companyCall);
beforeEach(async () => {
  vi.clearAllMocks(); session = await sessionFor({ permissions });
  session.grants = [{ scope_type: 'company', scope_id: COMPANY, permissions, valid_from: '2020-01-01', valid_to: null }];
  rows = Array.from({ length: 12 }, (_, index) => ({ id: 'period-' + index, company_id: COMPANY, fiscal_year_id: YEAR,
    sequence: index + 1, code: 'P' + String(index + 1).padStart(2, '0'), status: 'FUTURE', row_version: 1,
    start_date: new Date(Date.UTC(2027, 3 + index, 1)).toISOString().slice(0, 10), end_date: new Date(Date.UTC(2027, 4 + index, 0)).toISOString().slice(0, 10) }));
  api.mockImplementation(async (_service, path, request) => {
    if (path.includes('/next-preview')) return preview as never;
    if (path.endsWith('/generate')) return { id: YEAR, company_id: COMPANY, start_date: preview.start_date, end_date: preview.end_date } as never;
    if (path.endsWith('/readiness')) return { fiscal_year_id: YEAR, blockers: [], ready_for_posting: rows.some(row => row.status === 'OPEN') } as never;
    if (path.includes('/fiscal-periods?')) return { items: structuredClone(rows), page: { has_more: false } } as never;
    if (path.includes('/field-sets')) return { fields: ['status', 'reason', 'expected_version'].map(key => ({ key, visible: true, readable: true, writable: true })) } as never;
    if (path.endsWith('/transition')) {
      const row = rows.find(row => path.includes('/' + row.id + '/'))!;
      row.status = 'OPEN'; row.row_version += 1; return structuredClone(row) as never;
    }
    throw new Error('Unexpected path: ' + path + String(request));
  });
  vi.mocked(openCompany).mockResolvedValue(null);
});
function view() { return render(<NextFinancialYear session={session} companyId={COMPANY} companyName="Acme" />); }
async function prepare() { view(); await screen.findByText('Review the calendar'); fireEvent.click(screen.getByText('Generate and check year')); await screen.findByText('Check prerequisites and opening periods'); }
it('generates, validates the reason, opens the chosen period and explicitly switches year', async () => {
  await prepare(); expect(openCompany).not.toHaveBeenCalled();
  expect(screen.getByRole('checkbox', { name: 'Open P01' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Open P02' })).not.toBeChecked();
  fireEvent.click(screen.getByText('Open 1 selected period')); await screen.findByText(/Give a reason using/);
  expect(screen.getByLabelText('Reason for opening periods')).toHaveFocus();
  fireEvent.change(screen.getByLabelText('Reason for opening periods'), { target: { value: 'New year approved' } });
  fireEvent.click(screen.getByText('Open 1 selected period')); await screen.findByText('Your next year is ready');
  expect(rows.filter(row => row.status === 'OPEN')).toHaveLength(1);
  expect(openCompany).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('Use this year'));
  await waitFor(() => expect(openCompany).toHaveBeenCalledWith(COMPANY, YEAR));
  expect(screen.getByRole('link', { name: 'Review opening balances' })).toHaveAttribute('href', expect.stringContaining('/' + YEAR + '/continuity'));
});
it('reuses an existing next year and preserves all older period statuses', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[1].includes('/next-preview') ? Promise.resolve({ ...preview, existing_year_id: YEAR } as never) : original(...args));
  rows[0].status = 'LOCKED'; rows[1].status = 'OPEN';
  view(); await screen.findByText(/This next year already exists/); fireEvent.click(screen.getByText('Review existing year'));
  await screen.findByText('Check prerequisites and opening periods');
  expect(api.mock.calls.some(call => call[2]?.method === 'POST')).toBe(false);
  expect(screen.queryByRole('checkbox', { name: 'Open P01' })).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: 'Open P02' })).not.toBeInTheDocument();
});
it('retains the generation request identity after an unconfirmed response', async () => {
  const original = api.getMockImplementation()!; let attempts = 0;
  api.mockImplementation((...args) => args[1].endsWith('/generate') && attempts++ === 0 ? Promise.reject({ status: 503, message: 'Lost response' }) : original(...args));
  view(); await screen.findByText('Review the calendar'); fireEvent.click(screen.getByText('Generate and check year'));
  await screen.findByText('Lost response'); fireEvent.click(screen.getByText('Retry year preparation'));
  await screen.findByText('Check prerequisites and opening periods');
  const calls = api.mock.calls.filter(call => call[1].endsWith('/generate'));
  expect(calls).toHaveLength(2); expect(calls[0][2]?.key).toBe(calls[1][2]?.key);
});
it('recovers a partially completed period sequence without repeating its confirmed first step', async () => {
  const original = api.getMockImplementation()!; let failed = false;
  api.mockImplementation((...args) => args[1].includes('/period-1/transition') && !failed ? (failed = true, Promise.reject({ status: 503, message: 'Second response lost' })) : original(...args));
  await prepare(); fireEvent.click(screen.getByRole('checkbox', { name: 'Open P02' }));
  fireEvent.change(screen.getByLabelText('Reason for opening periods'), { target: { value: 'Approve two months' } });
  fireEvent.click(screen.getByText('Open 2 selected periods')); await screen.findByText('Second response lost');
  expect(screen.getByLabelText('Reason for opening periods')).toBeDisabled();
  fireEvent.click(screen.getByText('Retry period opening')); await screen.findByText('Your next year is ready');
  const first = api.mock.calls.filter(call => call[1].includes('/period-0/transition'));
  const second = api.mock.calls.filter(call => call[1].includes('/period-1/transition'));
  expect(first).toHaveLength(1); expect(second).toHaveLength(2); expect(second[0][2]?.key).toBe(second[1][2]?.key);
});
it('blocks opening when initial company openings are unfinished', async () => {
  const original = api.getMockImplementation()!;
  api.mockImplementation((...args) => args[1].endsWith('/readiness') ? Promise.resolve({ fiscal_year_id: YEAR, blockers: ['OPENING_NOT_FINALIZED'], ready_for_posting: false } as never) : original(...args));
  await prepare(); expect(screen.getByText(/Finalise the original/)).toBeVisible();
  expect(screen.getByText('Open 1 selected period')).toBeDisabled();
  expect(api.mock.calls.filter(call => call[1].endsWith('/transition'))).toHaveLength(0);
});
it('guards breadcrumb navigation with unsaved period choices and permits an explicit discard', async () => {
  await prepare();fireEvent.click(screen.getByRole('link',{name:'Companies'}));
  expect(await screen.findByRole('dialog')).toHaveTextContent('Leave financial-year setup?');
  expect(goTo).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Leave setup'}));
  expect(goTo).toHaveBeenCalledWith(expect.stringContaining('/companies'));
});
it('disables period opening when its writable field policy is denied', async () => {
  const original=api.getMockImplementation()!;
  api.mockImplementation((...args)=>args[1].includes('/field-sets')?Promise.resolve({fields:[]} as never):original(...args));
  await prepare();expect(screen.getByText(/Your field policy/)).toBeVisible();expect(screen.getByText('Open 1 selected period')).toBeDisabled();
  expect(api.mock.calls.filter(call=>call[1].endsWith('/transition'))).toHaveLength(0);
});
it('denies malformed or foreign calendar responses before any period writes', async () => {
  rows[1].company_id = 'another-company'; await prepare().catch(() => undefined);
  expect(await screen.findByText(/complete next-year calendar could not be verified/)).toBeVisible();
  expect(api.mock.calls.filter(call => call[1].endsWith('/transition'))).toHaveLength(0);
});
it('provides a read-access handoff when prerequisite checks are not authorised', async () => {
  session.grants![0].permissions = permissions.filter(key => key !== 'ledger.read');
  await prepare(); expect(screen.getByText(/Posting prerequisite checks need/)).toBeVisible();
  expect(screen.getByRole('link', { name: 'View year and manage periods' })).toBeInTheDocument();
  expect(api.mock.calls.some(call => call[1].endsWith('/readiness'))).toBe(false);
});
it('shows recoverable preview failures and blocks calendar writes for configured blockers', async () => {
  api.mockResolvedValue({ ...preview, blockers: ['COMPANY_INACTIVE'], can_generate: false } as never);
  view(); expect(await screen.findByText(/Activate the company/)).toBeVisible();
  expect(screen.getByText('Generate and check year')).toBeDisabled();
});
