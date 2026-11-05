import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { TaxReleaseEditor } from '../app/components/TaxReleaseEditor';
import { serviceCall } from '../app/lib/service-call';
import { allowedTaxRequest } from '../app/lib/tax-request-policy';
import { COMPANY, FRESH, RULE, context, evidence, fixtureResponse, page, rate, series } from './tax-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));
const contexts = ['INTRA_STATE', 'INTRA_UT', 'INTER_STATE'];
const seriesRows = contexts.map((applicability, index) => ({ ...series, id: series.id.slice(0, -2) + String(40 + index), applicability }));
const report = { id: FRESH, status: 'PENDING', change_reason: 'Official revision', change_count: 3, input_digest: 'ab'.repeat(32), policy_generation: 10, source_version: 50, business_date: context.business_date, item_count: 300, checked_count: 0, finding_count: 0, blocking_count: 0, row_version: 1 };
function reply(request: Parameters<typeof serviceCall>[1]) {
  if (request.path.includes('/tax-rate-series?')) return { items: seriesRows, page };
  if (request.path.includes('/tax-rates?')) return { items: [], page };
  if (request.path.endsWith('/tax-release-previews')) return { valid: true, policy_generation: 10, source_version: 50, affected_item_ids: [], checked_dates: [context.business_date], impact: [], preview_token: 'reviewed-token' };
  if (request.path.endsWith('/tax-impact-reviews')) return report;
  if (request.path.endsWith('/tax-impact-reviews/' + FRESH)) return { ...report, status: 'COMPLETE', checked_count: 300, row_version: 2 };
  return fixtureResponse(request);
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => reply(request) as never); });
function open() { render(<PermissionProvider permissions={[]}><DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}><TaxReleaseEditor company={COMPANY} ruleId={RULE} /></DisplayConfigProvider></PermissionProvider>); }
async function fill() {
  await userEvent.type(await screen.findByRole('textbox', { name: 'Reason for publication' }), 'Official revision');
  for (const [name, value] of [['Official source reference', evidence.source_reference], ['Official document URL', evidence.source_url], ['Document SHA-256', evidence.source_sha256]]) await userEvent.type(screen.getByRole('textbox', { name: name! }), value!);
  await waitFor(() => expect(screen.getAllByRole('textbox', { name: 'Percentage' })).toHaveLength(5));
  const values = ['2.5', '2.5', '2.5', '2.5', '5'];
  for (const [i, input] of screen.getAllByRole('textbox', { name: 'Percentage' }).entries()) await userEvent.type(input, values[i]!);
}
const writes = () => vi.mocked(serviceCall).mock.calls.filter(([, request]) => request.method === 'POST');
it('publishes all contexts atomically against the reviewed token and retries the exact command', async () => {
  let fail = true; vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.path.endsWith('/tax-releases') && fail) { fail = false; throw { status: 503 }; } return reply(request) as never; });
  open(); await fill(); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Publish all three rates' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Retry same coordinated publication' }));
  expect(await screen.findByText('All three rate definitions published successfully.')).toBeVisible();
  const commands = writes().filter(([, request]) => request.path.endsWith('/tax-releases')); expect(commands[0]![1].key).toBe(commands[1]![1].key); expect(commands[0]![1].body).toEqual(commands[1]![1].body);
  expect(commands[0]![1].body).toMatchObject({ preview_token: 'reviewed-token', changes: contexts.map(key => ({ kind: 'RATE', key })) });
}, 20000);
it('keeps background publication blocked until a complete report is verified', async () => {
  open(); await fill(); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Impact review' }), 'background'); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' }));
  expect(await screen.findByRole('button', { name: 'Publish all three rates' })).toBeDisabled(); await userEvent.click(screen.getByRole('button', { name: 'Refresh review progress' })); await waitFor(() => expect(screen.getByRole('button', { name: 'Publish all three rates' })).toBeEnabled()); await userEvent.click(screen.getByRole('button', { name: 'Publish all three rates' }));
  expect(await screen.findByText('All three rate definitions published successfully.')).toBeVisible(); expect(writes().at(-1)![1].body).toMatchObject({ impact_review_id: FRESH }); expect(writes().at(-1)![1].body).not.toHaveProperty('preview_token');
}, 20000);
it('requires explicit replacement of every overlapping rate and pins previous versions', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/tax-rates?') ? { items: [{ ...rate, series_id: new URL(request.path, 'https://api.invalid').searchParams.get('series_id'), valid_from: '2026-01-01' }], page } as never : reply(request) as never);
  open(); await fill(); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' })); expect(await screen.findAllByText('An existing rate covers this start date. Confirm its replacement or choose another date.')).toHaveLength(3); expect(writes()).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('Effective from'), { target: { value: '2026-12-01' } });
  await waitFor(() => expect(screen.queryByText('Checking existing rate periods...')).not.toBeInTheDocument());
  for (const field of screen.getAllByRole('combobox', { name: /Replace existing rate:/ })) { await userEvent.selectOptions(field, 'yes'); }
  await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' })); await screen.findByRole('button', { name: 'Publish all three rates' }); const body = writes()[0]![1].body as { changes: { definition: object }[] }; body.changes.forEach(change => expect(change.definition).toMatchObject({ supersedes_id: rate.id, expected_previous_version: 4 }));
}, 20000);
it('does not enable incomplete or foreign-company supply contexts', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.includes('/tax-rate-series?') ? { items: seriesRows.slice(0, 2), page } as never : reply(request) as never); open(); expect(await screen.findByRole('link', { name: 'Create missing rate series' })).toBeVisible(); expect(screen.getByRole('button', { name: 'Review coordinated publication' })).toBeDisabled();
});
it('retains the same background review request after an interrupted response', async () => {
  let fail = true; vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.path.endsWith('/tax-impact-reviews') && fail) { fail = false; throw { status: 503 }; } return reply(request) as never; });
  open(); await fill(); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Impact review' }), 'background'); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' })); await userEvent.click(await screen.findByRole('button', { name: 'Retry same impact review' }));
  await screen.findByRole('button', { name: 'Refresh review progress' }); const requests = writes().filter(([, request]) => request.path.endsWith('/tax-impact-reviews')); expect(requests).toHaveLength(2); expect(requests[0]![1].key).toBe(requests[1]![1].key); expect(requests[0]![1].body).toEqual(requests[1]![1].body); expect(screen.getByRole('button', { name: 'Publish all three rates' })).toBeDisabled();
}, 20000);
it('blocks a completed background report with blocking findings', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.endsWith('/tax-impact-reviews/' + FRESH) ? { ...report, status: 'COMPLETE', checked_count: 300, blocking_count: 1, finding_count: 0 } as never : reply(request) as never);
  open(); await fill(); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Impact review' }), 'background'); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' })); await userEvent.click(await screen.findByRole('button', { name: 'Refresh review progress' })); await screen.findByText(/1 blocking findings/); expect(screen.getByRole('button', { name: 'Publish all three rates' })).toBeDisabled(); expect(writes().some(([, request]) => request.path.endsWith('/tax-releases'))).toBe(false);
}, 20000);
it('keeps failed existing-period reads blocked even when evidence is edited', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => { if (request.path.includes('/tax-rates?')) throw { status: 503 }; return reply(request) as never; });
  open(); await screen.findByRole('textbox', { name: 'Reason for publication' }); await waitFor(() => expect(screen.getByRole('button', { name: 'Review coordinated publication' })).toBeDisabled()); await userEvent.type(screen.getByRole('textbox', { name: 'Official source reference' }), 'Retained'); expect(screen.getByRole('button', { name: 'Review coordinated publication' })).toBeDisabled(); expect(writes()).toHaveLength(0);
});
it('rejects a background report returned for a different review', async () => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => request.path.endsWith('/tax-impact-reviews/' + FRESH) ? { ...report, id: RULE, status: 'COMPLETE', checked_count: 300 } as never : reply(request) as never);
  open(); await fill(); await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Impact review' }), 'background'); await userEvent.click(screen.getByRole('button', { name: 'Review coordinated publication' })); await userEvent.click(await screen.findByRole('button', { name: 'Refresh review progress' })); expect(screen.getByRole('button', { name: 'Publish all three rates' })).toBeDisabled(); expect(writes().some(([, request]) => request.path.endsWith('/tax-releases'))).toBe(false);
}, 20000);
it.each(['tax-release-previews', 'tax-releases', 'tax-impact-reviews'])('allows only the native publication command %s', endpoint => { const path = '/v1/companies/' + COMPANY + '/' + endpoint; expect(allowedTaxRequest('POST', path)).toBe(true); expect(allowedTaxRequest('GET', path)).toBe(false); expect(allowedTaxRequest('POST', path + '?untrusted=true')).toBe(false); });
