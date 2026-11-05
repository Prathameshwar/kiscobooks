import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompanyTaxContext } from '../app/components/CompanyTaxContext';
import { companyCall } from '../app/lib/company-api';
vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (value: unknown) => value }));
const company = '01990000-0000-7000-8000-000000000001';
const row = { id: company, tax_system: 'vat_gb', number: 'GB123456789', jurisdiction_code: 'GB', regime: 'standard', valid_from: '2026-04-01', valid_to: null };
beforeEach(() => {
  vi.mocked(companyCall).mockReset();
  vi.mocked(companyCall).mockResolvedValue({ items: [row], page: { next_cursor: null } });
});
it('shows saved VAT facts without offering India GST controls or writes', async () => {
  render(<CompanyTaxContext company={company} taxSystem="vat_gb" />);
  await screen.findByText(row.number);
  expect(screen.getByText(/VAT registration editing is not yet available/)).toBeVisible();
  expect(companyCall).toHaveBeenCalledWith('identity', '/v1/companies/' + company + '/tax-registrations?limit=50', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  expect(screen.queryByRole('button', { name: /Add GST/ })).not.toBeInTheDocument();
});
it('keeps registration history visible even when the default is none', async () => {
  render(<CompanyTaxContext company={company} taxSystem="none" />);
  await screen.findByText(row.number);
  expect(screen.getByText('No indirect tax registration')).toBeVisible();
  expect(screen.getByText(/does not certify exemption/)).toBeVisible();
});
it('does not fetch registration facts when the tax default is unreadable', () => {
  render(<CompanyTaxContext company={company} />);
  expect(screen.getByText(/not readable with your current field access/)).toBeVisible();
  expect(companyCall).not.toHaveBeenCalled();
});
it('uses bounded cursor paging and can return to the first page', async () => {
  vi.mocked(companyCall).mockResolvedValueOnce({ items: [row], page: { next_cursor: 'signed+cursor' } });
  render(<CompanyTaxContext company={company} taxSystem="vat_gb" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Next tax registration page' }));
  await waitFor(() => expect(companyCall).toHaveBeenCalledWith('identity', expect.stringContaining('cursor=signed%2Bcursor'), expect.anything()));
  await screen.findByText(row.number);
  fireEvent.click(screen.getByRole('button', { name: 'First tax registration page' }));
  await waitFor(() => expect(companyCall).toHaveBeenCalledTimes(3));
  expect(vi.mocked(companyCall).mock.lastCall?.[1]).toBe('/v1/companies/' + company + '/tax-registrations?limit=50');
});
it.each([401, 403, 422, 500])('shows a %s read failure without suggesting the company is unregistered', async status => {
  vi.mocked(companyCall).mockRejectedValue({ status, message: 'Registration access unavailable' });
  render(<CompanyTaxContext company={company} taxSystem="vat_gb" />);
  await screen.findByText('Registration access unavailable');
  expect(screen.queryByText('No saved tax registrations')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Reload tax registrations' }) !== null).toBe(status >= 422);
});
it('reloads a recoverable failure without a mutation', async () => {
  vi.mocked(companyCall).mockRejectedValueOnce({ status: 500, message: 'Read failed' });
  render(<CompanyTaxContext company={company} taxSystem="vat_gb" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Reload tax registrations' }));
  await screen.findByText(row.number);
  expect(vi.mocked(companyCall).mock.calls.every(call => !call[2]?.method)).toBe(true);
});
