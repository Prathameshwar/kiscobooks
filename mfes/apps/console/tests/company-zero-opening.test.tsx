import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyZeroOpening } from '../app/components/CompanyZeroOpening';
import { companyCall } from '../app/lib/company-api';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';

vi.mock('../app/lib/company-api', async original => ({ ...await original<typeof import('../app/lib/company-api')>(), companyCall: vi.fn() }));
const company = '10000000-0000-7000-8000-000000000001', id = '10000000-0000-7000-8000-000000000002';
const base = '/v1/companies/' + company + '/financial-setup';
const review = { company_id: company, expected_setup_version: 1, books_begin_date: '2026-04-01', eligible: true, blocker: null };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(companyCall).mockResolvedValue(review as never); });
it('requires explicit confirmation and replays the exact request after an uncertain outcome', async () => {
  const onSaved = vi.fn(); let attempts = 0, completed = false;
  vi.mocked(companyCall).mockImplementation(async (_service, _path, request) => {
    if (request?.method === 'POST') {
      if (++attempts === 1) throw { status: 503, message: 'Connection interrupted' };
      completed = true; return { id, company_id: company, status: 'FINALIZED', journal_id: null } as never;
    }
    return { ...review, eligible: !completed, blocker: completed ? 'OPENING_ALREADY_FINALIZED' : null } as never;
  });
  render(<CompanyZeroOpening company={company} canConfirm onSaved={onSaved} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review zero opening' }));
  expect(attempts).toBe(0);
  expect(screen.getByRole('dialog', { name: 'Confirm no opening balances?' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm zero opening' }));
  const retry = await screen.findByRole('button', { name: 'Retry the same confirmation' });
  expect(screen.getByLabelText('Reason for zero opening')).toBeDisabled();
  fireEvent.click(retry);
  await screen.findByText('Zero opening confirmed. Other posting prerequisites still apply.');
  const writes = vi.mocked(companyCall).mock.calls.filter(([, , request]) => request?.method === 'POST');
  expect(writes).toHaveLength(2); expect(writes[1]?.[2]?.key).toBe(writes[0]?.[2]?.key);
  expect(writes[1]?.[2]?.body).toEqual(writes[0]?.[2]?.body);
  expect(writes[0]?.[2]?.body).toEqual({ expected_setup_version: 1, reason: 'Starting with no opening balances' });
  expect(onSaved).toHaveBeenCalledOnce();
  await screen.findByText(/Opening balances are finalised/);
});
it('validates a reason before offering confirmation and makes no write', async () => {
  render(<CompanyZeroOpening company={company} canConfirm onSaved={vi.fn()} />);
  const input = await screen.findByLabelText('Reason for zero opening');
  fireEvent.change(input, { target: { value: 'ab' } }); fireEvent.submit(input.closest('form')!);
  expect(await screen.findByText('Explain why the company has no opening balances.')).toBeVisible();
  expect(screen.queryByRole('dialog', { name: 'Confirm no opening balances?' })).not.toBeInTheDocument();
  expect(vi.mocked(companyCall).mock.calls.every(([, , request]) => request?.method !== 'POST')).toBe(true);
});
it('fetches nothing without the action permission', () => {
  render(<CompanyZeroOpening company={company} canConfirm={false} onSaved={vi.fn()} />);
  expect(companyCall).not.toHaveBeenCalled(); expect(screen.queryByRole('button')).not.toBeInTheDocument();
});
it.each(['OPENING_ALREADY_FINALIZED', 'EXISTING_OPENING_OR_ACTIVITY', 'BOOKS_PERIOD_NOT_OPEN'])('does not offer confirmation when %s', async blocker => {
  vi.mocked(companyCall).mockResolvedValue({ ...review, eligible: false, blocker } as never);
  render(<CompanyZeroOpening company={company} canConfirm onSaved={vi.fn()} />);
  await screen.findByText(blocker === 'OPENING_ALREADY_FINALIZED' ? /Opening balances are finalised/
    : blocker === 'EXISTING_OPENING_OR_ACTIVITY' ? /Opening history or recorded activity/
    : /Open the period containing the books begin date/);
  expect(screen.queryByRole('button', { name: 'Review zero opening' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Reason for zero opening')).not.toBeInTheDocument();
});
it('rejects a review belonging to another company', async () => {
  vi.mocked(companyCall).mockResolvedValue({ ...review, company_id: id } as never);
  render(<CompanyZeroOpening company={company} canConfirm onSaved={vi.fn()} />);
  await screen.findByText('The opening review could not be verified for this company.');
  expect(screen.queryByLabelText('Reason for zero opening')).not.toBeInTheDocument();
});
it('allows only the exact company review and confirmation routes', () => {
  expect(allowedCompanyRequest('accounting', 'GET', base + '/zero-opening-review')).toBe(true);
  expect(allowedCompanyRequest('accounting', 'POST', base + '/confirm-zero-opening')).toBe(true);
  expect(allowedCompanyRequest('accounting', 'GET', base + '/confirm-zero-opening')).toBe(false);
  expect(allowedCompanyRequest('accounting', 'POST', base + '/confirm-zero-opening?amount=1')).toBe(false);
  expect(allowedCompanyRequest('catalog', 'POST', base + '/confirm-zero-opening')).toBe(false);
});
