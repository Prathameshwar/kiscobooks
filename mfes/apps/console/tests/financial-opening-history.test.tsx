import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinancialOpeningHistory } from '../app/components/FinancialOpeningHistory';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, BATCH, COMPANY, JOB, JOURNAL, access, declaration, page, workspace } from './financial-opening-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
type Link = components['schemas']['OpeningEntryPostingLink'];
const api = vi.mocked(serviceCall);
const source = declaration().entries[0].source_key;
const notPrepared: Link = { entry_id: ACCOUNT, source_key: source, chunk_id: JOB, journal_id: null, journal_status: 'NOT_PREPARED', line_sequence: 1 };
let readLink: () => Promise<Link>;
let batches: unknown[];
beforeEach(() => {
  readLink = async () => notPrepared;
  batches = [{ id: BATCH, company_id: COMPANY, status: 'FINALIZED', posting_date: '2026-04-01', finalized_at: '2026-04-01T00:20:00Z' }];
  api.mockReset();
  api.mockImplementation(async (_service, req) => {
    const url = new URL(req.path, 'https://review.invalid');
    if (url.pathname.endsWith('/posting-link')) return await readLink() as never;
    if (url.pathname.endsWith('/entries/' + ACCOUNT)) return declaration().entries[0] as never;
    if (url.pathname.endsWith('/entries')) return { items: [{ ...declaration().entries[0], id: ACCOUNT, document_count: 0 }], page } as never;
    if (url.pathname.includes('/accounts/')) return { id: ACCOUNT, company_id: COMPANY, name: 'Review account' } as never;
    if (url.pathname.endsWith('/revisions/' + JOB)) return declaration() as never;
    if (url.pathname.endsWith('/revisions')) return { items: [{ id: JOB, revision: 1, manifest_hash: 'a'.repeat(64), created_at: '2026-03-31T20:15:00Z' }], page } as never;
    return { items: batches, page } as never;
  });
});
function view() {
  return render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy', datetimeFormat: 'dd/MM/yyyy HH:mm', timezone: 'Asia/Kolkata', locale: 'hi-IN' }}><FinancialOpeningHistory company={COMPANY} workspace={{ ...workspace, status: 'FINALIZED', posted_journals: 1 }} access={access} onDirty={vi.fn()} /></DisplayConfigProvider>);
}
async function selectEntry() {
  fireEvent.click(await screen.findByRole('button', { name: source }));
  await screen.findByRole('heading', { name: 'Source ' + source });
}
it('formats retained opening and revision dates and UTC timestamps through the company configuration', async () => {
  view();
  const history = within(await screen.findByRole('table', { name: 'Company opening history' }));
  expect(await history.findByRole('link', { name: '01/04/2026' })).toHaveAttribute('href', '/accounting/opening?batch_id=' + BATCH);
  expect(await history.findByText('01/04/2026 05:50')).toBeVisible();
  expect(await screen.findByText('01/04/2026 01:45')).toBeVisible();
  fireEvent.click(await screen.findByRole('button', { name: 'Review revision 1' }));
  expect(await screen.findByText('01/04/2026 / 31/03/2026')).toBeVisible();
});
it('preserves restricted dates and genuinely unfinalized batches', async () => {
  batches = [{ id: BATCH, company_id: COMPANY, status: 'DRAFT', posting_date: null, finalized_at: null }];
  view();
  expect(await screen.findByRole('link', { name: 'Date restricted' })).toBeVisible();
  expect(await screen.findByText('Not finalized')).toBeVisible();
});
it('does not label a field-denied finalization date as unfinalized', async () => {
  batches = [{ id: BATCH, company_id: COMPANY, status: 'FINALIZED', posting_date: '2026-04-01' }];
  view();
  expect(await screen.findByText('Finalization date restricted')).toBeVisible();
  expect(screen.queryByText('Not finalized')).not.toBeInTheDocument();
});
it.each([401, 403, 422, 503])('does not invent a draft status after posting-link returns %s', async status => {
  readLink = async () => { throw { status, message: 'Posting lookup failed.' }; };
  view();
  await selectEntry();
  expect(await screen.findByText('Posting lookup failed.')).toBeVisible();
  expect(screen.getByText('Posting information unavailable')).toBeVisible();
  expect(screen.queryByText('Draft not prepared')).not.toBeInTheDocument();
  expect(screen.queryByText('Loading')).not.toBeInTheDocument();
  if (status === 401) expect(screen.getByRole('link', { name: 'Sign in again' })).toBeVisible();
  if (status === 403) expect(screen.queryByRole('button', { name: 'Reload configuration' })).not.toBeInTheDocument();
  expect(api.mock.calls.every(([, req]) => !req.method || req.method === 'GET')).toBe(true);
});
it('shows a pending lookup until the native posted journal is confirmed', async () => {
  let resolve!: (link: Link) => void;
  readLink = () => new Promise<Link>(done => { resolve = done; });
  view();
  await selectEntry();
  expect(screen.getByText('Loading posting information')).toBeVisible();
  expect(screen.queryByText('Draft not prepared')).not.toBeInTheDocument();
  resolve({ ...notPrepared, journal_id: JOURNAL, journal_status: 'POSTED' });
  expect(await screen.findByText(JOURNAL)).toBeVisible();
  expect(screen.getByText('POSTED / 1')).toBeVisible();
});
it('retries a failed lookup and displays the recovered native journal status', async () => {
  readLink = async () => { throw { status: 503, message: 'Posting lookup failed.' }; };
  view();
  await selectEntry();
  await screen.findByText('Posting lookup failed.');
  readLink = async () => ({ ...notPrepared, journal_id: JOURNAL, journal_status: 'POSTED' });
  fireEvent.click(screen.getByRole('button', { name: 'Reload configuration' }));
  expect(await screen.findByText(JOURNAL)).toBeVisible();
  expect(screen.getByText('POSTED / 1')).toBeVisible();
  await waitFor(() => expect(screen.queryByText('Posting lookup failed.')).not.toBeInTheDocument());
});
it('labels an unprepared draft only when the successful response explicitly confirms it', async () => {
  view(); await selectEntry();
  expect(await screen.findByText('Draft not prepared')).toBeVisible();
  expect(screen.getByText('Not prepared')).toBeVisible();
});
it('does not label a journal-less unexpected status as an unprepared draft', async () => {
  readLink = async () => ({ ...notPrepared, journal_status: 'POSTED' });
  view(); await selectEntry();
  expect(await screen.findByText('Posting information unavailable')).toBeVisible();
  expect(screen.queryByText('Draft not prepared')).not.toBeInTheDocument();
});
it('does not display posting metadata belonging to a different entry', async () => {
  readLink = async () => ({ ...notPrepared, entry_id: JOB, journal_id: JOURNAL, journal_status: 'POSTED' });
  view(); await selectEntry();
  expect(await screen.findByText('Posting information unavailable')).toBeVisible();
  expect(screen.queryByText(JOURNAL)).not.toBeInTheDocument();
});
it.each(['DRAFT', 'POSTED', 'VOID'])('displays the native %s journal and line when available', async journal_status => {
  readLink = async () => ({ ...notPrepared, journal_id: JOURNAL, journal_status, line_sequence: 2 });
  view(); await selectEntry();
  expect(await screen.findByText(JOURNAL)).toBeVisible();
  expect(screen.getByText(journal_status + ' / 2')).toBeVisible();
});
