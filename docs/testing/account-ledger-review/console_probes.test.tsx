/** Reusable acceptance checks for resolved opening UI findings AO-B01 and AO-B02. */
import { fireEvent, render, screen } from '@testing-library/react';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinancialOpeningDocumentEvidence } from '../app/components/FinancialOpeningCommon';
import { FinancialOpeningHistory } from '../app/components/FinancialOpeningHistory';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, BATCH, COMPANY, access, declaration, page, workspace } from './financial-opening-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
beforeEach(() => vi.clearAllMocks());

it('uses the configured date format for opening evidence', () => {
  render(<DisplayConfigProvider config={{ ...DEFAULT_DISPLAY_CONFIG, dateFormat: 'dd/MM/yyyy' }}><FinancialOpeningDocumentEvidence currency="INR" documents={[{
    reference: 'REVIEW-BILL', document_kind: 'BILL', document_date: '2026-03-25', due_date: '2026-04-05', amount: '100', base_amount: '100',
  }]} /></DisplayConfigProvider>);
  expect(screen.getByText('25/03/2026 / 05/04/2026')).toBeVisible();
  expect(screen.queryByText('2026-03-25 / 2026-04-05')).not.toBeInTheDocument();
});

it('labels a failed posting lookup unavailable without inventing an unprepared draft', async () => {
  const entry = { ...declaration().entries[0], id: ACCOUNT, document_count: 0 };
  vi.mocked(serviceCall).mockImplementation(async (_service, req) => {
    const url = new URL(req.path, 'https://review.invalid');
    if (url.pathname.endsWith('/posting-link')) throw { status: 503, message: 'Review fixture metadata unavailable.' };
    if (url.pathname.endsWith('/entries/' + ACCOUNT)) return entry as never;
    if (url.pathname.endsWith('/entries')) return { items: [entry], page } as never;
    if (url.pathname.includes('/accounts/')) return { id: ACCOUNT, company_id: COMPANY, name: 'Review account' } as never;
    if (url.pathname.endsWith('/revisions')) return { items: [], page } as never;
    return { items: [{ id: BATCH, company_id: COMPANY, status: 'FINALIZED', posting_date: '2026-04-01' }], page } as never;
  });
  render(<FinancialOpeningHistory company={COMPANY} workspace={{ ...workspace, status: 'FINALIZED', posted_journals: 1 }} access={access} onDirty={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: entry.source_key }, { timeout: 10000 }));
  await screen.findByText('Posting information unavailable');
  expect(screen.queryByText('Draft not prepared')).not.toBeInTheDocument();
  expect(await screen.findByText(/metadata unavailable/)).toBeVisible();
});
