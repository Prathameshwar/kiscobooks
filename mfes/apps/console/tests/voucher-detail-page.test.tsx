import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Page from '../app/vouchers/[voucherId]/page';
import { pageContext } from '../app/lib/page-context';
import { companyContextFor, sessionFor } from './helpers';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/VoucherWorkflow', () => ({ VoucherWorkflow: () => <p>Saved workflow</p> }));
it('returns any reviewed voucher to the voucher directory', async () => {
  vi.mocked(pageContext).mockResolvedValue({ session: await sessionFor(), context: companyContextFor() });
  render(await Page({ params: Promise.resolve({ voucherId: '10000000-0000-7000-8000-000000000001' }) }));
  expect(screen.getByRole('link', { name: /Back to voucher drafts/ })).toHaveAttribute('href', '/vouchers');
});


it('returns a Day Book drill-through to the same company report and filters', async () => {
  const session = { ...await sessionFor(), company: { id: '01990000-0000-7000-8000-000000000001', name: 'Example Traders' } };
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() });
  const returnTo = '/books/day-book?' + new URLSearchParams({ company: session.company.id!, filters: '{}' });
  render(await Page({ params: Promise.resolve({ voucherId: '10000000-0000-7000-8000-000000000001' }), searchParams: Promise.resolve({ returnTo }) }));
  expect(screen.getByRole('link', { name: /Back to Day Book/ })).toHaveAttribute('href', returnTo);
});

it.each(['https://evil.invalid', '//evil.invalid/books/day-book', '/books/day-book?company=other', '/books/day-book?company=other#bad'])('rejects an unsafe or different-company return target %s', async returnTo => {
  vi.mocked(pageContext).mockResolvedValue({ session: await sessionFor(), context: companyContextFor() });
  render(await Page({ params: Promise.resolve({ voucherId: '10000000-0000-7000-8000-000000000001' }), searchParams: Promise.resolve({ returnTo }) }));
  expect(screen.getByRole('link', { name: /Back to voucher drafts/ })).toHaveAttribute('href', '/vouchers');
});
