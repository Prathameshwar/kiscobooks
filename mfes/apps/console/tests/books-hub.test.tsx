import { beforeEach, expect, it, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import BooksPage from '../app/books/page';
import BookPage from '../app/books/[book]/page';
import { bookEntries } from '../app/lib/book-cards';
import { reportSections } from '../app/lib/report-cards';
import { pageContext } from '../app/lib/page-context';
import { productFieldRequest } from '../app/lib/product-fields';
import {
  flattenNavigation,
  navigationFor,
  navSections,
  sidebarCurrentHref,
} from '../app/nav';
import { sessionFor, companyContextFor } from './helpers';
vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn().mockResolvedValue({ items: [] }) }));
vi.mock('../app/lib/navigate', () => ({
  goTo: vi.fn(),
  authActionUrl: (path: string) => path,
}));
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not found');
  },
}));
const company = '01990000-0000-7000-8000-000000000001';
beforeEach(async () => {
  vi.mocked(productFieldRequest).mockReset();
  vi.mocked(productFieldRequest).mockResolvedValue({ items: [] });
  const session = await sessionFor({ permissions: ['report.read'] });
  session.company = { id: company, name: 'Company A' };
  session.grants = [
    {
      scope_type: 'company',
      scope_id: company,
      permissions: ['report.read'],
      valid_from: '2000-01-01',
      valid_to: null,
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
});
it('routes the available Day Book card into the same direct workspace as the sidebar', async () => {
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => path.endsWith('/report-definitions') ? { items: [{ definition: { code: 'DAY_BOOK', version: 5 }, run_enabled: true }] } : { items: [] });
  render(await BooksPage());
  await waitFor(() => expect(screen.getByRole('heading', { name: 'Day book', level: 3 }).closest('a')).toHaveAttribute('href', '/books/day-book'));
});
it('lists ten native books and registers once under Books alongside Reports', async () => {
  const available = new Set(
    reportSections.flatMap((section) =>
      section.reports.map((report) => report.code),
    ),
  );
  expect(bookEntries).toHaveLength(10);
  expect(new Set(bookEntries.map((book) => book.code)).size).toBe(10);
  for (const book of bookEntries) expect(available.has(book.code)).toBe(true);
  const section = navSections.find(
    (section) => section.label === 'Books and Reports',
  )!;
  expect(section.items.map((item) => item.label)).toEqual(['Books', 'Reports']);
  expect(section.items[0]!.children?.map((item) => item.label)).toEqual(
    bookEntries.map((book) => book.title),
  );
  expect(section.items[0]!.children?.every((item) => !item.children)).toBe(
    true,
  );
});
it('renders searchable unavailable book cards when discovery supplies no definitions', async () => {
  render(await BooksPage());
  expect(
    screen.getByRole('heading', { level: 1, name: 'Books' }),
  ).toBeVisible();
  expect(screen.getAllByRole('article')).toHaveLength(10);
  for (const card of screen.getAllByRole('article'))
    expect(within(card).getByRole('button')).toBeDisabled();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search books' }), {
    target: { value: 'cash bo' },
  });
  await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(1));
  expect(
    screen.getByRole('heading', { level: 3, name: 'Cash book' }),
  ).toBeVisible();
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search books' }), {
    target: { value: 'no matching book' },
  });
  expect(await screen.findByText(/No books match/)).toBeVisible();
});
it('opens Day Book directly into the report filters without another catalogue card', async () => {
  render(await BookPage({ params: Promise.resolve({ book: 'day-book' }) }));
  expect(screen.queryByRole('article')).not.toBeInTheDocument();
  expect(screen.getByRole('searchbox', { name: 'Search transactions' })).toBeVisible();
});
it.each([
  'cash-book',
  'bank-book',
  'sales-book',
  'purchase-book',
  'payment-book',
  'receipt-book',
  'account-ledger',
  'party-ledger',
  'stock-ledger',
])('opens and selects the %s submenu', async (book) => {
  const { session } = await pageContext();
  const items = navigationFor(session).flatMap((section) => section.items);
  expect(sidebarCurrentHref(items, '/books/' + book)).toBe('/books/' + book);
  render(await BookPage({ params: Promise.resolve({ book }) }));
  const entry = bookEntries.find((item) => item.key === book)!;
  expect(
    screen.getByRole('heading', { level: 1, name: new RegExp('^' + entry.title + '$', 'i') }),
  ).toBeVisible();
  expect(screen.queryByRole('article')).not.toBeInTheDocument();
  expect(screen.getByRole('region', { name: new RegExp('^' + entry.title + ' report$', 'i') })).toBeVisible();
  await waitFor(() => expect(screen.queryByText('Loading book…')).not.toBeInTheDocument());
  expect(
    document.querySelector('.janso-rail__nav a[aria-current="page"]'),
  ).toHaveAttribute('href', '/books/' + book);
});
it.each(['wrong company', 'expired', 'department', 'missing'])(
  'denies Books pages and menu with %s authority',
  async (reason) => {
    const { session } = await pageContext();
    if (reason === 'wrong company') session.grants![0].scope_id = 'other';
    if (reason === 'expired') session.grants![0].valid_to = '2000-01-01';
    if (reason === 'department') session.grants![0].scope_type = 'department';
    if (reason === 'missing') session.grants = [];
    render(await BookPage({ params: Promise.resolve({ book: 'cash-book' }) }));
    expect(screen.getByRole('alert')).toBeVisible();
    expect(
      flattenNavigation(
        navigationFor(session).flatMap((section) => section.items),
      ).some(
        (item) => item.href === '/books' || item.href.startsWith('/books/'),
      ),
    ).toBe(false);
  },
);
it.each(['unknown', '../cash-book', 'CASH_BOOK'])(
  'rejects unknown book route %s',
  async (book) => {
    await expect(
      BookPage({ params: Promise.resolve({ book }) }),
    ).rejects.toThrow('not found');
  },
);
