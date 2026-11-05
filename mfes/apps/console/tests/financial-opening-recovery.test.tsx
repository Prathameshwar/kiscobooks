import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinancialOpeningPosting } from '../app/components/FinancialOpeningPosting';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, BATCH, COMPANY, JOURNAL, OTHER, access, page, workspace } from './financial-opening-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
let status = 'POSTED', reverse: string | null = null, reverseStatus = 'DRAFT', uncertain = false;
const api = vi.mocked(serviceCall);
beforeEach(() => {
  status = 'POSTED'; reverse = null; reverseStatus = 'DRAFT'; uncertain = false; api.mockReset();
  api.mockImplementation(async (_endpoint, req) => {
    if (req.path.endsWith('/recovery')) return { company_id: COMPANY, batch_id: BATCH, journal_id: JOURNAL,
      expected_version: 2, journal_status: status, can_cancel: status === 'PREPARED', can_reverse: status === 'POSTED' && !reverse,
      reversal_blockers: [], reversal_journal_id: reverse, reversal_status: reverse ? reverseStatus : null,
      reversal_expected_version: reverse ? 2 : null, can_cancel_reversal: !!reverse && ['DRAFT', 'PREPARED'].includes(reverseStatus) } as never;
    if (req.path.endsWith('/reversal')) { reverse = OTHER; if (uncertain) { uncertain = false; throw { status: 503, message: 'Lost response' }; } }
    if (req.path.endsWith('/void')) { if (req.path.includes(OTHER)) { reverseStatus = 'VOID'; reverse = null; } else status = 'VOID'; }
    if (req.path.endsWith('/post')) reverseStatus = 'POSTED';
    if (req.path.includes('/journal-lines?')) return { items: [{ id: ACCOUNT, journal_id: req.path.includes(OTHER) ? OTHER : JOURNAL, company_id: COMPANY, sequence: 1, side: 'CREDIT', amount: '100', currency: 'INR' }], page } as never;
    const reversal = req.path.includes(OTHER) || req.path.endsWith('/reversal');
    return { id: reversal ? OTHER : JOURNAL, company_id: COMPANY, row_version: 2, kind: reversal ? 'REVERSAL' : 'OPENING',
      source_type: reversal ? 'reversal' : 'financial_opening_chunk', reversal_of_id: reversal ? JOURNAL : null,
      status: reversal ? reverseStatus : status, posting_date: '2026-04-01' } as never;
  });
});

it('can cancel a prepared reversal without posting it', async () => {
  reverse = OTHER; reverseStatus = 'PREPARED'; mount();
  await userEvent.click(screen.getByRole('button', { name: 'Review journal 1' }));
  fireEvent.change(await screen.findByLabelText('Correction reason'), { target: { value: 'Cancel interrupted reversal' } });
  await userEvent.click(screen.getByRole('button', { name: 'Cancel unposted reversal' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel journal' }));
  await waitFor(() => expect(api.mock.calls.some(([, req]) => req.path === `/v1/companies/${COMPANY}/journals/${OTHER}/void`)).toBe(true));
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/void'))![1].body).toEqual({ expected_version: 2, reason: 'Cancel interrupted reversal' });
});
function mount() { return render(<FinancialOpeningPosting company={COMPANY} workspace={{ ...workspace, journal_ids: [JOURNAL] }} access={access} onDirty={vi.fn()} onChanged={vi.fn()} />); }

it('reviews cancellation of a prepared intent', async () => {
  status = 'PREPARED'; mount();
  await userEvent.click(screen.getByRole('button', { name: 'Review journal 1' }));
  fireEvent.change(await screen.findByLabelText('Correction reason'), { target: { value: 'Cancel blocked posting intent' } });
  await userEvent.click(screen.getByRole('button', { name: 'Cancel unposted journal' }));
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/void'))).toBe(false);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel journal' }));
  await waitFor(() => expect(api.mock.calls.some(([, req]) => req.path.endsWith('/void'))).toBe(true));
  expect(api.mock.calls.find(([, req]) => req.path.endsWith('/void'))![1].body).toEqual({ expected_version: 2, reason: 'Cancel blocked posting intent' });
});

it('retries reversal creation exactly and separately reviews its native posting', async () => {
  uncertain = true; mount();
  await userEvent.click(screen.getByRole('button', { name: 'Review journal 1' }));
  fireEvent.change(await screen.findByLabelText('Correction reason'), { target: { value: 'Correct reviewed migration' } });
  await userEvent.click(screen.getByRole('button', { name: 'Prepare reversal draft' }));
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create reversal draft' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Retry the same correction' }));
  await screen.findByText(/Retained reversal/);
  const calls = api.mock.calls.filter(([, req]) => req.path.endsWith('/reversal'));
  expect(calls).toHaveLength(2); expect(calls[1]![1]).toEqual(calls[0]![1]);
  await userEvent.click(screen.getByRole('button', { name: 'Review reversal journal' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Post this reversal journal' }));
  expect(screen.getByRole('dialog', { name: 'Post this reversal journal?' })).toBeVisible();
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Post journal' }));
  await waitFor(() => expect(api.mock.calls.some(([, req]) => req.path === `/v1/companies/${COMPANY}/journals/${OTHER}/post`)).toBe(true));
});

it('finds an existing reversal after reload without creating another', async () => {
  reverse = OTHER; mount();
  await userEvent.click(screen.getByRole('button', { name: 'Review journal 1' }));
  expect(await screen.findByRole('button', { name: 'Review reversal journal' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Prepare reversal draft' })).toBeDisabled();
  expect(api.mock.calls.some(([, req]) => req.path.endsWith('/reversal'))).toBe(false);
});
