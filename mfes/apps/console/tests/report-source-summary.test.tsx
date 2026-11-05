import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ReportSources } from '../app/components/ReportSources';
import { reportSourceSummary } from '../app/lib/report-source-summary';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const id = '10000000-0000-7000-8000-000000000001', company = '10000000-0000-7000-8000-000000000002';
const detail = { id, status: 'READY', applied_sequence: 10, target_sequence: 10, failure_code: null, manifest: { company_id: company, control: { coverage_start: '2026-10-29', coverage_kind: 'RETAINED_LEDGER' } } };
beforeEach(() => vi.clearAllMocks());
it('shows native ledger coverage while keeping stock compatibility explicit', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue(detail);
  render(<ReportSources company={company} sources={[{ id, status: 'READY', applied_sequence: 10 }]} value={id} onChange={vi.fn()} disabled={false} inventory />);
  expect(await screen.findByRole('option', { name: /Ledger from/ })).toBeInTheDocument();
  expect(screen.getByText(/Ready financial snapshots do not certify stock history/)).toBeVisible();
});
it('states unknown coverage and offers recovery after a source read fails', async () => {
  vi.mocked(productFieldRequest).mockRejectedValue(new Error('Source unavailable'));
  render(<ReportSources company={company} sources={[{ id, status: 'READY' }]} value={id} onChange={vi.fn()} disabled={false} inventory={false} />);
  expect(await screen.findByText(/selected snapshot could not be verified/)).toBeVisible();
  expect(screen.getByRole('option', { name: /Coverage unavailable/ })).toBeInTheDocument();
});
it.each([{ ...detail, id: company }, { ...detail, manifest: { ...detail.manifest, company_id: id } }, { ...detail, status: 'BUILDING' }])('refuses foreign or unfinished source evidence', bad => {
  expect(() => reportSourceSummary(company, id, bad)).toThrow(/could not be verified/);
});
