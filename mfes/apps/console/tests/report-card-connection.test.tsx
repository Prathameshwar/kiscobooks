import { render, screen, within, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ReportsHub } from '../app/components/ReportsHub';
import { BooksHub } from '../app/components/BooksHub';
import { productFieldRequest } from '../app/lib/product-fields';

vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001';
const definition = (code: string, run_enabled = true) => ({ definition: { code, version: 1 }, run_enabled });
beforeEach(() => { vi.mocked(productFieldRequest).mockReset(); });

it('opens only a discovered permitted report in the existing workspace', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [definition('TRIAL_BALANCE')] });
  render(<ReportsHub company={company} />);
  expect(await screen.findByRole('link', { name: 'Trial balance' })).toHaveAttribute('href', '/reports/workspace?report=TRIAL_BALANCE');
  expect(screen.queryByRole('link', { name: 'Stock summary' })).not.toBeInTheDocument();
  expect(productFieldRequest).toHaveBeenCalledWith('reports', 'GET', '/v2/companies/' + company + '/report-definitions', undefined, undefined, expect.any(AbortSignal));
});

it('keeps retained result navigation available while new runs are disabled', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [definition('TRIAL_BALANCE', false)] });
  render(<ReportsHub company={company} />);
  expect(await screen.findByRole('link', { name: 'Trial balance' })).toHaveTextContent('View completed reports');
});

it('maps a discovered book to its native report without a second execution flow', async () => {
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [definition('CASH_BOOK')] });
  render(<BooksHub company={company} book="cash-book" />);
  await waitFor(() => expect(screen.getByRole('heading', { level: 3, name: 'Cash book' }).closest('a')).toHaveAttribute('href', '/reports/workspace?report=CASH_BOOK'));
});

it.each([401, 403, 500])('fails closed when discovery returns %s', async status => {
  vi.mocked(productFieldRequest).mockRejectedValue({ status, message: 'Discovery unavailable' });
  render(<ReportsHub company={company} />);
  await screen.findByRole('button', { name: 'Retry report availability' });
  for (const card of screen.getAllByRole('article')) expect(within(card).getByRole('button')).toBeDisabled();
  expect(screen.queryByRole('link', { name: 'Trial balance' })).not.toBeInTheDocument();
});

it.each([
  { items: [definition('TRIAL_BALANCE'), definition('TRIAL_BALANCE')] },
  { items: [definition('../other')] },
  { items: [{ definition: { code: 'TRIAL_BALANCE', version: 1 }, run_enabled: 'true' }] },
  { items: [{ definition: { code: 'TRIAL_BALANCE', version: 0 }, run_enabled: true }] },
])('rejects malformed catalogue facts without enabling navigation', async value => {
  vi.mocked(productFieldRequest).mockResolvedValue(value);
  render(<ReportsHub company={company} />);
  await screen.findByRole('button', { name: 'Retry report availability' });
  expect(screen.queryByRole('link', { name: 'Trial balance' })).not.toBeInTheDocument();
});

it('clears previous-company availability immediately while the next company loads', async () => {
  vi.mocked(productFieldRequest).mockResolvedValueOnce({ items: [definition('TRIAL_BALANCE')] }).mockImplementationOnce(() => new Promise(() => {}));
  const view = render(<ReportsHub company={company} />);
  await screen.findByRole('link', { name: 'Trial balance' });
  view.rerender(<ReportsHub company="01990000-0000-7000-8000-000000000002" />);
  expect(screen.queryByRole('link', { name: 'Trial balance' })).not.toBeInTheDocument();
  await waitFor(() => expect(productFieldRequest).toHaveBeenCalledTimes(2));
});
