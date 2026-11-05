import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { FinancialOpeningImports } from '../app/components/FinancialOpeningImports';
import { FinancialOpeningHistory } from '../app/components/FinancialOpeningHistory';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, BATCH, COMPANY, JOB, access, declaration, page, workspace } from './financial-opening-fixtures';
vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
let state = 'STAGED';
const job = () => ({ id: JOB, company_id: COMPANY, row_version: state === 'STAGED' ? 1 : 2, source_key: 'migration-import', state, input_hash: 'a'.repeat(64), review_hash: state === 'READY' ? 'b'.repeat(64) : null, batch_id: state === 'COMMITTED' ? BATCH : null, issues: [], journal_ids: [], drafts_complete: false, effect_kind: 'DECLARATION_AND_DRAFTS_ONLY', posting_required: state === 'COMMITTED', opening_status: state === 'COMMITTED' ? 'DRAFT' : null });
beforeEach(() => {
  state = 'STAGED'; api.mockReset();
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/opening-batches?')) return { items: [], page } as never;
    if (request.path.endsWith('/template')) return { marker: '_financial_opening_schema_version', version: 1, required_columns: ['account_id', 'amount'], optional_columns: ['document_kind'], maximum_file_bytes: 2097152, maximum_file_rows: 2000, reference_policy: 'Exact native IDs only.' } as never;
    if (request.path.includes('/financial-opening-imports?')) return { items: [{ id: JOB, source_key: 'migration-import', state, row_version: 1, batch_id: null }], page } as never;
    if (request.path.endsWith('/validate')) state = 'READY';
    if (request.path.endsWith('/commit')) state = 'COMMITTED';
    if (request.path.endsWith('/cancel')) state = 'CANCELLED';
    if (request.path.endsWith('/declaration')) return declaration() as never;
    if (request.path.includes('/financial-opening-imports/')) return job() as never;
    if (request.path.includes('/entries?')) return { items: [{ id: ACCOUNT, source_key: 'invoice-source', account_id: ACCOUNT, party_id: null, role: 'CUSTOMER', side: 'DEBIT', currency: 'INR', amount: '100', base_amount: '100', document_count: 1 }], page } as never;
    if (request.path.includes('/revisions?')) return { items: [{ id: JOB, revision: 1, manifest_hash: 'a'.repeat(64), created_at: '2026-10-28T10:00:00Z' }], page } as never;
    if (request.path.endsWith('/posting-link')) return { entry_id: ACCOUNT, source_key: 'invoice-source', journal_id: null, journal_status: 'NOT_PREPARED', line_sequence: 1 } as never;
    if (request.path.endsWith('/entries/' + ACCOUNT)) return { ...declaration().entries[0], documents: [{ reference: 'On account', amount: '100', base_amount: '100', document_kind: 'ON_ACCOUNT', document_date: null, due_date: null }] } as never;
    if (request.path.endsWith('/revisions/' + JOB)) return declaration() as never;
    return job() as never;
  });
});
it('loads durable history, validates and explicitly commits without posting', async () => {
  const onChanged = vi.fn(); render(<FinancialOpeningImports company={COMPANY} access={access} onDirty={vi.fn()} onChanged={onChanged} />);
  await userEvent.click(await screen.findByRole('button', { name: 'migration-import' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Validate import' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Commit reviewed import' })).toBeEnabled());
  await userEvent.click(screen.getByRole('button', { name: 'Commit reviewed import' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create declaration and drafts' }));
  await waitFor(() => expect(screen.getAllByText('COMMITTED').length).toBeGreaterThan(0));
  expect(onChanged).toHaveBeenCalledWith(BATCH);
  expect(api.mock.calls.find(([, request]) => request.path.endsWith('/commit'))![1]).toMatchObject({ body: { expected_version: 2, review_hash: 'b'.repeat(64) }, key: expect.any(String) });
  expect(api.mock.calls.some(([, request]) => request.path.endsWith('/post') || request.path.endsWith('/finalize'))).toBe(false);
});
it('keeps cancellation separate from financial effects and hides import capture from readers', async () => {
  render(<FinancialOpeningImports company={COMPANY} access={{ ...access, manage: false }} onDirty={vi.fn()} onChanged={vi.fn()} />);
  expect(await screen.findByText(/Finance management access is required/)).toBeVisible();
  expect(screen.queryByLabelText('Import reference')).not.toBeInTheDocument();
  await userEvent.click(await screen.findByRole('button', { name: 'migration-import' }));
  expect(await screen.findByRole('button', { name: 'Cancel import job' })).toBeDisabled();
});
it('shows captured document evidence and immutable revision summaries', async () => {
  render(<FinancialOpeningHistory company={COMPANY} workspace={workspace} access={access} onDirty={vi.fn()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'invoice-source' }));
  await screen.findByText('Unknown / Unknown');
  await userEvent.click(await screen.findByRole('button', { name: 'Review revision 1' }));
  await screen.findByRole('heading', { name: 'Captured revision' });
  expect(screen.getByText('Reviewed migration balances')).toBeVisible();
  fireEvent.change(screen.getByLabelText('Exact line source reference'), { target: { value: 'bad source' } });
  await userEvent.click(screen.getByRole('button', { name: 'Filter evidence' }));
  await screen.findByText('Enter a valid exact source reference.');
});
it('formats the captured import opening and coverage dates', async () => {
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy' }}><FinancialOpeningImports company={COMPANY} access={access} onDirty={vi.fn()} onChanged={vi.fn()} /></DisplayConfigProvider>);
  fireEvent.click(await screen.findByRole('button', { name: 'migration-import' }));
  expect(await screen.findByText('01/04/2026 / 31/03/2026')).toBeVisible();
});
it('stages a JSON declaration only after an explicit upload action', async () => {
  render(<FinancialOpeningImports company={COMPANY} access={access} onDirty={vi.fn()} onChanged={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText('Import reference'), { target: { value: 'manual-file' } });
  const file = new File([JSON.stringify(declaration())], 'opening.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => JSON.stringify(declaration()) });
  await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Stage file for validation' }));
  await screen.findByRole('heading', { name: 'Import migration-import' });
  expect(api.mock.calls.find(([, request]) => request.method === 'POST')![1]).toMatchObject({ key: expect.any(String), body: { format: 'JSON', source_key: 'manual-file', document: declaration() } });
});
it('retains an invalid JSON file with an actionable message and never submits it', async () => {
  render(<FinancialOpeningImports company={COMPANY} access={access} onDirty={vi.fn()} onChanged={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText('Import reference'), { target: { value: 'manual-file' } });
  const file = new File(['{'], 'invalid.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => '{' });
  await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
  await userEvent.click(screen.getByRole('button', { name: 'Stage file for validation' }));
  await screen.findByText(/The JSON file is invalid/);
  expect(api.mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
});
